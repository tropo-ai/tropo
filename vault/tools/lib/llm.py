"""llm.py — Shared inference layer for vault/tools/*.py

Single entry point for all Anthropic LLM calls made by vault tools.
Centralizes: task→model routing, client init, error handling.

Usage:
    from lib.llm import call

    result = call(task="triage", messages=[{"role": "user", "content": "..."}])

Task routing (override with model= kwarg if needed):
    triage      → claude-haiku-4-5   (classification, short lists)
    interpret   → claude-haiku-4-5   (validator output, event log)
    summarize   → claude-sonnet-4-6  (longer synthesis, reports)
    draft       → claude-sonnet-4-6  (content generation, release notes)
    reason      → claude-opus-4-8    (architectural decisions, complex analysis)
    gardener-prune → claude-opus-4-8 (evidence-bound Gardener body judgment)
"""
from __future__ import annotations

import sys
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional

from lib.loop_metering import (
    LOCKED_TASK_MODELS as METERING_LOCKED_TASK_MODELS,
    parse_locked_usage,
)

# Task → model routing table.
# One place to update when models are deprecated or upgraded.
TASK_MODELS: dict[str, str] = {
    "triage":    "claude-haiku-4-5",   # classification, short-list triage
    "interpret": "claude-haiku-4-5",   # reading structured output and summarising
    "summarize": "claude-sonnet-4-6",  # longer synthesis, reports
    "draft":     "claude-sonnet-4-6",  # content generation, release notes
    "reason":    "claude-opus-4-8",    # architectural decisions, complex analysis
    "gardener-prune": "claude-opus-4-8",  # pinned synthetic/production judge route
}
LOCKED_TASK_MODELS: dict[str, str] = dict(METERING_LOCKED_TASK_MODELS)
LOCKED_TASK_REQUEST_CONTROLS = MappingProxyType(
    {
        "parse-query": MappingProxyType(
            {
                "service_tier": "standard_only",
            }
        ),
        "distill": MappingProxyType(
            {
                "service_tier": "standard_only",
                "inference_geo": "global",
            }
        ),
    }
)

_DEFAULT_MODEL = "claude-haiku-4-5"
_DEFAULT_MAX_TOKENS = 1024
_UID_RE = re.compile(r"^[0-9a-f]{8}$")
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_GATEWAY_URL = "http://127.0.0.1:8080"


@dataclass(frozen=True)
class MeteringContext:
    """Gate-issued immutable binding carried to the local metering gateway."""

    reservation_id: str
    policy_uid: str
    policy_version: str
    task: str
    model: str
    admission_mode: str
    segment_classes: tuple[str, ...]
    utc_day: str
    run_uid: str
    gateway_url: str
    virtual_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.reservation_id, str) or not _UID_RE.fullmatch(
            self.reservation_id
        ):
            raise ValueError("reservation_id must be 8 lowercase hex")
        if not isinstance(self.policy_uid, str) or not _UID_RE.fullmatch(
            self.policy_uid
        ):
            raise ValueError("policy_uid must be 8 lowercase hex")
        if not isinstance(self.policy_version, str) or not self.policy_version:
            raise ValueError("policy_version must be non-empty")
        if self.task not in LOCKED_TASK_MODELS:
            raise ValueError("task is not a locked Distiller route")
        if self.model != LOCKED_TASK_MODELS[self.task]:
            raise ValueError("model does not match the locked task route")
        if self.admission_mode not in {"production", "canary"}:
            raise ValueError("admission_mode must be production or canary")
        if (
            not isinstance(self.segment_classes, tuple)
            or not self.segment_classes
            or self.segment_classes
            != tuple(sorted(set(self.segment_classes)))
            or any(value not in {"os", "team", "private"} for value in self.segment_classes)
        ):
            raise ValueError("segment_classes must be canonical and non-empty")
        if not isinstance(self.utc_day, str) or not _DAY_RE.fullmatch(self.utc_day):
            raise ValueError("utc_day must be YYYY-MM-DD")
        if not isinstance(self.run_uid, str) or not _UID_RE.fullmatch(self.run_uid):
            raise ValueError("run_uid must be 8 lowercase hex")
        if self.gateway_url != _GATEWAY_URL:
            raise ValueError("gateway_url must use the exact local gateway")
        expected_key = f"sk-virtual-tropo-{self.run_uid}"
        if self.virtual_key != expected_key:
            raise ValueError("virtual_key is not bound to run_uid")

    def gateway_headers(self) -> dict[str, str]:
        return {
            "x-tropo-policy-uid": self.policy_uid,
            "x-tropo-policy-version": self.policy_version,
            "x-tropo-task": self.task,
            "x-tropo-model": self.model,
            "x-tropo-admission-mode": self.admission_mode,
            "x-tropo-day": self.utc_day,
            "x-tropo-reservation-id": self.reservation_id,
            "x-tropo-run-uid": self.run_uid,
            "x-tropo-segment-classes": ",".join(self.segment_classes),
        }


@dataclass(frozen=True)
class LockedLLMResponse:
    text: str
    model: str
    usage: dict[str, object]


def serialize_locked_request(
    task: str,
    messages: list[dict],
    *,
    max_tokens: int,
    system: Optional[str] = None,
) -> bytes:
    """Return the exact canonical preflight projection for one locked request."""
    if task not in LOCKED_TASK_MODELS:
        raise ValueError(f"unknown locked task: {task!r}")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
        raise ValueError("max_tokens must be a positive integer")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list")
    if system is not None and not isinstance(system, str):
        raise ValueError("system must be a string or None")
    request_controls = LOCKED_TASK_REQUEST_CONTROLS[task]
    projection: dict[str, object] = {
        "model": LOCKED_TASK_MODELS[task],
        "max_tokens": max_tokens,
        "messages": messages,
        **request_controls,
    }
    if system is not None:
        projection["system"] = system
    try:
        return json.dumps(
            projection,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"locked request is not canonical JSON: {exc}") from exc


def validate_locked_request_body(task: str, value: object) -> bytes:
    """Require one wire body to equal the closed locked-request serialization."""
    if type(value) is not dict:
        raise ValueError("locked request body must be an object")
    if task not in LOCKED_TASK_MODELS:
        raise ValueError(f"unknown locked task: {task!r}")
    request_controls = LOCKED_TASK_REQUEST_CONTROLS[task]
    required = {
        "model",
        "max_tokens",
        "messages",
        *request_controls,
    }
    if set(value) not in (required, required | {"system"}):
        raise ValueError("locked request body schema is not closed")
    for field, expected in request_controls.items():
        if value.get(field) != expected:
            raise ValueError(f"locked request {field} must equal {expected!r}")
    rendered = serialize_locked_request(
        task,
        value.get("messages"),
        max_tokens=value.get("max_tokens"),
        system=value.get("system"),
    )
    try:
        expected = json.loads(rendered.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:  # pragma: no cover
        raise ValueError(f"locked request serialization failed: {exc}") from exc
    if value != expected:
        raise ValueError("locked request body does not match its canonical route")
    return rendered


def _plain_mapping(value: object, field: str) -> dict[str, object]:
    if isinstance(value, Mapping):
        result = dict(value)
    elif callable(getattr(value, "model_dump", None)):
        try:
            result = value.model_dump(exclude_unset=True)
        except TypeError:
            result = value.model_dump()
    elif hasattr(value, "__dict__"):
        result = dict(vars(value))
    else:
        raise RuntimeError(f"{field} is not an object")
    if type(result) is not dict or any(not isinstance(key, str) for key in result):
        raise RuntimeError(f"{field} must have string keys")
    for nested_field in (
        "cache_creation",
        "output_tokens_details",
        "server_tool_use",
    ):
        nested = result.get(nested_field)
        if nested is not None and type(nested) is not dict:
            result[nested_field] = _plain_mapping(
                nested,
                f"{field}.{nested_field}",
            )
    return result


def _response_text(task: str, response: object) -> str:
    """Extract response text, with a closed content contract for Gardener."""
    content = getattr(response, "content", None)
    if task == "gardener-prune":
        if not isinstance(content, (list, tuple)) or len(content) != 1:
            raise RuntimeError(
                "Gardener response must contain exactly one content block"
            )
        block = content[0]
        if getattr(block, "type", None) != "text" or not isinstance(
            getattr(block, "text", None),
            str,
        ):
            raise RuntimeError(
                "Gardener response must contain exactly one text block "
                "and no other content"
            )
        return block.text
    if not isinstance(content, (list, tuple)):
        raise RuntimeError("Anthropic response content is not a block list")
    text_blocks = [block for block in content if getattr(block, "type", None) == "text"]
    if not text_blocks:
        raise RuntimeError(
            "No text block in response "
            f"(stop_reason={getattr(response, 'stop_reason', None)})"
        )
    text = getattr(text_blocks[0], "text", None)
    if not isinstance(text, str):
        raise RuntimeError("Anthropic text block has no string text")
    return text


def call(
    task: str,
    messages: list[dict],
    *,
    model: Optional[str] = None,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    system: Optional[str] = None,
) -> str:
    """Call the Anthropic API for a given task.

    Args:
        task:       Key into TASK_MODELS (e.g. "triage", "summarize").
                    Determines the default model unless overridden.
        messages:   Standard Anthropic messages array.
        model:      Override the task-default model.
        max_tokens: Max output tokens (default 1024).
        system:     Optional system prompt.

    Returns:
        The text content of the first response block.

    Raises:
        RuntimeError if the API call fails or no text block is returned.
        The calling tool decides whether to surface or swallow the error.
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install anthropic"
        )

    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("NO_API_KEY")  # sentinel — callers distinguish this from real errors

    resolved_model = model or TASK_MODELS.get(task, _DEFAULT_MODEL)

    kwargs: dict = {
        "model": resolved_model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    try:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        response = client.messages.create(**kwargs)
    except anthropic.AuthenticationError:
        raise RuntimeError(
            "Anthropic API key missing or invalid. "
            "Set ANTHROPIC_API_KEY in your environment."
        )
    except anthropic.RateLimitError as exc:
        raise RuntimeError(f"Anthropic rate limit hit: {exc}")
    except Exception as exc:
        raise RuntimeError(f"Anthropic API error: {exc}")

    return _response_text(task, response)


def call_locked(
    task: str,
    messages: list[dict],
    *,
    max_tokens: int,
    system: Optional[str] = None,
    metering_context: MeteringContext,
) -> LockedLLMResponse:
    """Call one closed Distiller route and return its exact model/usage receipt."""
    if task not in LOCKED_TASK_MODELS:
        raise RuntimeError(f"unknown locked task: {task!r}")
    if not isinstance(metering_context, MeteringContext):
        raise RuntimeError("metering_context must be gate-issued")
    expected_model = LOCKED_TASK_MODELS[task]
    if (
        metering_context.task != task
        or metering_context.model != expected_model
    ):
        raise RuntimeError("metering context route mismatch")
    # Validate/measure the same closed request projection before SDK construction.
    serialize_locked_request(
        task,
        messages,
        max_tokens=max_tokens,
        system=system,
    )
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install anthropic"
        ) from exc

    kwargs: dict[str, object] = {
        "model": expected_model,
        "max_tokens": max_tokens,
        "messages": messages,
        "extra_headers": metering_context.gateway_headers(),
        **LOCKED_TASK_REQUEST_CONTROLS[task],
    }
    if system is not None:
        kwargs["system"] = system
    try:
        client = anthropic.Anthropic(
            api_key=metering_context.virtual_key,
            base_url=metering_context.gateway_url,
            max_retries=0,
            timeout=60.0,
        )
        response = client.messages.create(**kwargs)
    except anthropic.AuthenticationError as exc:
        raise RuntimeError("Anthropic gateway authentication failed") from exc
    except anthropic.RateLimitError as exc:
        raise RuntimeError(f"Anthropic gateway rate limit hit: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Anthropic gateway error: {exc}") from exc

    response_model = getattr(response, "model", None)
    if response_model != expected_model:
        raise RuntimeError("locked response model does not match requested model")
    content = getattr(response, "content", None)
    if not isinstance(content, (list, tuple)) or len(content) != 1:
        raise RuntimeError("locked response must contain exactly one content block")
    block = content[0]
    if (
        getattr(block, "type", None) != "text"
        or not isinstance(getattr(block, "text", None), str)
    ):
        raise RuntimeError(
            "locked response must contain exactly one text block and no tools"
        )
    usage = _plain_mapping(getattr(response, "usage", None), "response.usage")
    try:
        parse_locked_usage(usage, task=task, model=response_model)
    except Exception as exc:
        raise RuntimeError(f"locked response usage is malformed: {exc}") from exc
    return LockedLLMResponse(
        text=block.text,
        model=response_model,
        usage=usage,
    )


def model_for(task: str) -> str:
    """Return the resolved model name for a task — useful for logging."""
    return TASK_MODELS.get(task, _DEFAULT_MODEL)


__all__ = [
    "LOCKED_TASK_REQUEST_CONTROLS",
    "LOCKED_TASK_MODELS",
    "LockedLLMResponse",
    "MeteringContext",
    "TASK_MODELS",
    "call",
    "call_locked",
    "model_for",
    "serialize_locked_request",
    "validate_locked_request_body",
]
