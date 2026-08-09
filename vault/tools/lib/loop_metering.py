"""Strict pricing and usage accounting shared by loop metering surfaces."""
from __future__ import annotations

import math
import numbers
from types import MappingProxyType
from typing import Any


OPUS_48_MODEL = "claude-opus-4-8"
HAIKU_45_MODEL = "claude-haiku-4-5-20251001"
SONNET_46_MODEL = "claude-sonnet-4-6"
REQUEST_OVERHEAD_BYTES = 4096
# Signed 64-bit storage bound used by the runtime ledgers.
MAX_NANO_USD = (1 << 63) - 1
# Anthropic standard pricing. Opus was verified for the locked Gardener canary
# on 2026-07-17; Haiku/Sonnet were verified for Distiller on 2026-07-23.
MODEL_PRICING_USD_PER_MTOK = {
    OPUS_48_MODEL: {
        "input_tokens": 5.00,
        "output_tokens": 25.00,
        "cache_read_input_tokens": 0.50,
        "cache_creation_5m_input_tokens": 6.25,
        "cache_creation_1h_input_tokens": 10.00,
    },
    HAIKU_45_MODEL: {
        "input_tokens": 1.00,
        "output_tokens": 5.00,
        "cache_read_input_tokens": 0.10,
        "cache_creation_5m_input_tokens": 1.25,
        "cache_creation_1h_input_tokens": 2.00,
    },
    SONNET_46_MODEL: {
        "input_tokens": 3.00,
        "output_tokens": 15.00,
        "cache_read_input_tokens": 0.30,
        "cache_creation_5m_input_tokens": 3.75,
        "cache_creation_1h_input_tokens": 6.00,
    },
}
# One token at one USD/MTok costs exactly 1,000 nano-USD. This table is
# intentionally literal: no float participates in admission or reconciliation.
MODEL_PRICING_NANO_USD_PER_TOKEN = {
    OPUS_48_MODEL: {
        "input_tokens": 5_000,
        "output_tokens": 25_000,
        "cache_read_input_tokens": 500,
        "cache_creation_5m_input_tokens": 6_250,
        "cache_creation_1h_input_tokens": 10_000,
    },
    HAIKU_45_MODEL: {
        "input_tokens": 1_000,
        "output_tokens": 5_000,
        "cache_read_input_tokens": 100,
        "cache_creation_5m_input_tokens": 1_250,
        "cache_creation_1h_input_tokens": 2_000,
    },
    SONNET_46_MODEL: {
        "input_tokens": 3_000,
        "output_tokens": 15_000,
        "cache_read_input_tokens": 300,
        "cache_creation_5m_input_tokens": 3_750,
        "cache_creation_1h_input_tokens": 6_000,
    },
}
SONNET_US_MULTIPLIER_NUMERATOR = 11
SONNET_US_MULTIPLIER_DENOMINATOR = 10


def _exact_scaled_pricing(
    pricing: dict[str, int],
    *,
    numerator: int,
    denominator: int,
) -> dict[str, int]:
    """Scale every exact rate or fail module initialization."""
    result = {}
    for field, rate in pricing.items():
        product = rate * numerator
        if product % denominator:
            raise AssertionError(f"{field} geo pricing is not exact integer nano-USD")
        result[field] = product // denominator
    return result


SONNET_US_PRICING_NANO_USD_PER_TOKEN = _exact_scaled_pricing(
    MODEL_PRICING_NANO_USD_PER_TOKEN[SONNET_46_MODEL],
    numerator=SONNET_US_MULTIPLIER_NUMERATOR,
    denominator=SONNET_US_MULTIPLIER_DENOMINATOR,
)
CACHE_MODES = {
    "none": "input_tokens",
    "5m": "cache_creation_5m_input_tokens",
    "1h": "cache_creation_1h_input_tokens",
    "read": "cache_read_input_tokens",
}
GENERIC_USAGE_KEYS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "cache_creation",
    }
)
LOCKED_USAGE_KEYS = GENERIC_USAGE_KEYS | {
    "service_tier",
    "inference_geo",
    "output_tokens_details",
    "server_tool_use",
}
USAGE_KEYS = GENERIC_USAGE_KEYS
CACHE_CREATION_KEYS = frozenset(
    {
        "ephemeral_5m_input_tokens",
        "ephemeral_1h_input_tokens",
    }
)
OUTPUT_TOKEN_DETAIL_KEYS = frozenset({"thinking_tokens"})
SERVER_TOOL_USE_KEYS = frozenset(
    {
        "web_search_requests",
        "web_fetch_requests",
    }
)
LOCKED_TASK_MODELS = MappingProxyType(
    {
        "parse-query": HAIKU_45_MODEL,
        "distill": SONNET_46_MODEL,
    }
)
LOCKED_RESPONSE_USAGE_CONTROLS = MappingProxyType(
    {
        "parse-query": MappingProxyType(
            {
                "service_tier": "standard",
                "inference_geo_policy": "bounded-any-recorded",
            }
        ),
        "distill": MappingProxyType(
            {
                "service_tier": "standard",
                "inference_geo_policy": "bounded-any-recorded",
            }
        ),
    }
)
INFERENCE_GEO_MAX_LENGTH = 128


class MeteringContractError(ValueError):
    """Pricing, request, or provider usage is not safely meterable."""


def _token_count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise MeteringContractError(f"{field} must be a nonnegative integer")
    numeric = int(value)
    if numeric < 0:
        raise MeteringContractError(f"{field} must be a nonnegative integer")
    return numeric


def _closed_string_object(
    value: Any,
    allowed: frozenset[str],
    field: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise MeteringContractError(f"{field} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise MeteringContractError(f"{field} keys must be strings")
    extra = sorted(set(value) - allowed)
    if extra:
        raise MeteringContractError(f"{field} has unknown fields: {extra}")
    return value


def _exact_zero(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value != 0:
        raise MeteringContractError(f"{field} must equal integer 0")


def validate_inference_geo(value: Any) -> str:
    """Return one exact bounded provider geo string without normalization."""
    if type(value) is not str or not 1 <= len(value) <= INFERENCE_GEO_MAX_LENGTH:
        raise MeteringContractError(
            "usage.inference_geo must be a string with length in [1, 128]"
        )
    return value


def pricing_for(model: Any) -> dict[str, float]:
    if not isinstance(model, str) or model not in MODEL_PRICING_USD_PER_MTOK:
        raise MeteringContractError(f"unknown model pricing: {model!r}")
    return MODEL_PRICING_USD_PER_MTOK[model]


def pricing_nano_usd_for(model: Any) -> dict[str, int]:
    if not isinstance(model, str) or model not in MODEL_PRICING_NANO_USD_PER_TOKEN:
        raise MeteringContractError(f"unknown model pricing: {model!r}")
    return MODEL_PRICING_NANO_USD_PER_TOKEN[model]


def _locked_response_controls(
    *,
    task: Any = None,
    model: Any = None,
) -> dict[str, Any]:
    """Resolve one exact task/model response contract or refuse aliases."""
    if task is None and model is None:
        raise MeteringContractError(
            "locked usage requires an exact task or model identity"
        )
    if task is not None:
        if not isinstance(task, str) or task not in LOCKED_TASK_MODELS:
            raise MeteringContractError(f"unknown locked response task: {task!r}")
        resolved_task = task
    else:
        matches = [
            candidate
            for candidate, candidate_model in LOCKED_TASK_MODELS.items()
            if candidate_model == model
        ]
        if len(matches) != 1:
            raise MeteringContractError(f"unknown locked response model: {model!r}")
        resolved_task = matches[0]
    expected_model = LOCKED_TASK_MODELS[resolved_task]
    if model is not None and (
        not isinstance(model, str) or model != expected_model
    ):
        raise MeteringContractError(
            "locked response task/model identity does not match"
        )
    return dict(LOCKED_RESPONSE_USAGE_CONTROLS[resolved_task])


def _normalize_usage(
    usage: Any,
    *,
    locked_controls: dict[str, Any] | None,
) -> dict[str, int]:
    """Normalize shared token counts after entrypoint-specific metadata checks."""
    locked = locked_controls is not None
    allowed = LOCKED_USAGE_KEYS if locked else GENERIC_USAGE_KEYS
    usage = _closed_string_object(usage, allowed, "usage")
    if locked:
        if "service_tier" not in usage:
            raise MeteringContractError("usage.service_tier is required")
        expected_tier = locked_controls["service_tier"]
        if usage["service_tier"] != expected_tier:
            raise MeteringContractError(
                f"usage.service_tier must equal {expected_tier!r}"
            )
        if "inference_geo" not in usage:
            raise MeteringContractError("usage.inference_geo is required")
        if locked_controls["inference_geo_policy"] != "bounded-any-recorded":
            raise MeteringContractError("locked inference geo policy is unknown")
        validate_inference_geo(usage["inference_geo"])

        if "output_tokens_details" in usage:
            output_details = _closed_string_object(
                usage["output_tokens_details"],
                OUTPUT_TOKEN_DETAIL_KEYS,
                "usage.output_tokens_details",
            )
            if set(output_details) != OUTPUT_TOKEN_DETAIL_KEYS:
                raise MeteringContractError(
                    "usage.output_tokens_details fields must equal "
                    "['thinking_tokens']"
                )
            _exact_zero(
                output_details["thinking_tokens"],
                "usage.output_tokens_details.thinking_tokens",
            )

        if "server_tool_use" in usage:
            server_tools = _closed_string_object(
                usage["server_tool_use"],
                SERVER_TOOL_USE_KEYS,
                "usage.server_tool_use",
            )
            if set(server_tools) != SERVER_TOOL_USE_KEYS:
                raise MeteringContractError(
                    "usage.server_tool_use fields must equal "
                    "['web_fetch_requests', 'web_search_requests']"
                )
            for field in sorted(SERVER_TOOL_USE_KEYS):
                _exact_zero(
                    server_tools[field],
                    f"usage.server_tool_use.{field}",
                )

    input_tokens = _token_count(usage.get("input_tokens"), "usage.input_tokens")
    output_tokens = _token_count(usage.get("output_tokens"), "usage.output_tokens")
    cache_read = _token_count(
        usage.get("cache_read_input_tokens", 0),
        "usage.cache_read_input_tokens",
    )
    cache_total = _token_count(
        usage.get("cache_creation_input_tokens", 0),
        "usage.cache_creation_input_tokens",
    )
    cache_detail = usage.get("cache_creation")
    if cache_detail is None:
        if cache_total:
            raise MeteringContractError(
                "usage.cache_creation is required when cache creation tokens are nonzero"
            )
        cache_5m = cache_1h = 0
    else:
        cache_detail = _closed_string_object(
            cache_detail,
            CACHE_CREATION_KEYS,
            "usage.cache_creation",
        )
        cache_5m = _token_count(
            cache_detail.get("ephemeral_5m_input_tokens", 0),
            "usage.cache_creation.ephemeral_5m_input_tokens",
        )
        cache_1h = _token_count(
            cache_detail.get("ephemeral_1h_input_tokens", 0),
            "usage.cache_creation.ephemeral_1h_input_tokens",
        )
        if cache_5m + cache_1h != cache_total:
            raise MeteringContractError(
                "usage cache creation detail must sum to cache_creation_input_tokens"
            )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_input_tokens": cache_read,
        "cache_creation_5m_input_tokens": cache_5m,
        "cache_creation_1h_input_tokens": cache_1h,
    }


def parse_usage(usage: Any) -> dict[str, int]:
    """Normalize the legacy token/cache usage shape without pricing metadata."""
    return _normalize_usage(usage, locked_controls=None)


def parse_locked_usage(
    usage: Any,
    *,
    task: Any = None,
    model: Any = None,
) -> dict[str, int]:
    """Normalize usage under one exact locked task/model response policy."""
    controls = _locked_response_controls(task=task, model=model)
    return _normalize_usage(usage, locked_controls=controls)


def _checked_nano_usd(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MeteringContractError(f"{field} must be exact integer nano-USD")
    if value < 0 or value > MAX_NANO_USD:
        raise MeteringContractError(f"{field} exceeds the nano-USD storage domain")
    return value


def _price_normalized_usage_nano_usd(
    model: Any,
    normalized: dict[str, int],
    *,
    pricing: dict[str, int] | None = None,
) -> int:
    selected_pricing = pricing if pricing is not None else pricing_nano_usd_for(model)
    cost = sum(
        normalized[field] * selected_pricing[field]
        for field in normalized
    )
    return _checked_nano_usd(cost, "computed usage cost")


def price_usage_nano_usd(model: Any, usage: Any) -> int:
    return _price_normalized_usage_nano_usd(model, parse_usage(usage))


def price_locked_usage_nano_usd(
    model: Any,
    usage: Any,
    *,
    task: Any = None,
) -> int:
    """Price only after exact task/model tier and geo validation."""
    normalized = parse_locked_usage(usage, task=task, model=model)
    inference_geo = usage["inference_geo"]
    pricing = (
        SONNET_US_PRICING_NANO_USD_PER_TOKEN
        if model == SONNET_46_MODEL and inference_geo == "us"
        else pricing_nano_usd_for(model)
    )
    return _price_normalized_usage_nano_usd(
        model,
        normalized,
        pricing=pricing,
    )


def price_usage(model: Any, usage: Any) -> float:
    """Compatibility float surface derived from exact integer nano-USD."""
    return price_usage_nano_usd(model, usage) / 1_000_000_000


def worst_case_request_cost_nano_usd(
    model: Any,
    *,
    request_bytes: Any,
    max_tokens: Any,
    cache_mode: Any = "none",
) -> int:
    """Conservative preflight: one UTF-8 byte per input token plus overhead."""
    pricing = (
        SONNET_US_PRICING_NANO_USD_PER_TOKEN
        if model == SONNET_46_MODEL
        else pricing_nano_usd_for(model)
    )
    byte_count = _token_count(request_bytes, "request_bytes")
    output_tokens = _token_count(max_tokens, "max_tokens")
    if output_tokens < 1:
        raise MeteringContractError("max_tokens must be >= 1")
    if not isinstance(cache_mode, str) or cache_mode not in CACHE_MODES:
        raise MeteringContractError(
            f"cache_mode must be one of {sorted(CACHE_MODES)}"
        )
    input_upper_bound = byte_count + REQUEST_OVERHEAD_BYTES
    input_price = pricing[CACHE_MODES[cache_mode]]
    cost = (
        input_upper_bound * input_price
        + output_tokens * pricing["output_tokens"]
    )
    return _checked_nano_usd(cost, "worst-case request cost")


def worst_case_request_cost(
    model: Any,
    *,
    request_bytes: Any,
    max_tokens: Any,
) -> float:
    """Legacy conservative surface, retaining the highest input-rate behavior."""
    pricing = pricing_nano_usd_for(model)
    byte_count = _token_count(request_bytes, "request_bytes")
    output_tokens = _token_count(max_tokens, "max_tokens")
    if output_tokens < 1:
        raise MeteringContractError("max_tokens must be >= 1")
    input_upper_bound = byte_count + REQUEST_OVERHEAD_BYTES
    highest_input_price = max(
        pricing["input_tokens"],
        pricing["cache_read_input_tokens"],
        pricing["cache_creation_5m_input_tokens"],
        pricing["cache_creation_1h_input_tokens"],
    )
    cost = (
        input_upper_bound * highest_input_price
        + output_tokens * pricing["output_tokens"]
    )
    return _checked_nano_usd(cost, "worst-case request cost") / 1_000_000_000


__all__ = [
    "CACHE_CREATION_KEYS",
    "CACHE_MODES",
    "GENERIC_USAGE_KEYS",
    "HAIKU_45_MODEL",
    "INFERENCE_GEO_MAX_LENGTH",
    "LOCKED_RESPONSE_USAGE_CONTROLS",
    "LOCKED_TASK_MODELS",
    "LOCKED_USAGE_KEYS",
    "MAX_NANO_USD",
    "MODEL_PRICING_USD_PER_MTOK",
    "MODEL_PRICING_NANO_USD_PER_TOKEN",
    "MeteringContractError",
    "OPUS_48_MODEL",
    "OUTPUT_TOKEN_DETAIL_KEYS",
    "REQUEST_OVERHEAD_BYTES",
    "SERVER_TOOL_USE_KEYS",
    "SONNET_46_MODEL",
    "SONNET_US_MULTIPLIER_DENOMINATOR",
    "SONNET_US_MULTIPLIER_NUMERATOR",
    "SONNET_US_PRICING_NANO_USD_PER_TOKEN",
    "USAGE_KEYS",
    "parse_locked_usage",
    "parse_usage",
    "price_locked_usage_nano_usd",
    "price_usage",
    "price_usage_nano_usd",
    "pricing_for",
    "pricing_nano_usd_for",
    "worst_case_request_cost",
    "worst_case_request_cost_nano_usd",
    "validate_inference_geo",
]
