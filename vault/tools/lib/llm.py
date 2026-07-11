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
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Task → model routing table.
# One place to update when models are deprecated or upgraded.
TASK_MODELS: dict[str, str] = {
    "triage":    "claude-haiku-4-5",   # classification, short-list triage
    "interpret": "claude-haiku-4-5",   # reading structured output and summarising
    "summarize": "claude-sonnet-4-6",  # longer synthesis, reports
    "draft":     "claude-sonnet-4-6",  # content generation, release notes
    "reason":    "claude-opus-4-8",    # architectural decisions, complex analysis
}

_DEFAULT_MODEL = "claude-haiku-4-5"
_DEFAULT_MAX_TOKENS = 1024


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

    text_blocks = [b for b in response.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"No text block in response (stop_reason={response.stop_reason})"
        )

    return text_blocks[0].text


def model_for(task: str) -> str:
    """Return the resolved model name for a task — useful for logging."""
    return TASK_MODELS.get(task, _DEFAULT_MODEL)
