"""Shared decay and lifecycle gate for live graph authority sources.

This module is the sole owner of the gardener-aligned terminal vocabulary and
the distiller's 0.8 decay-confidence boundary. Consumers import these names so
circle membership, gardener lifecycle policy, and viewer authority cannot
silently drift.
"""
from __future__ import annotations

from typing import Mapping


DECAY_GATE_CONFIDENCE = 0.8

TERMINAL_STATUSES = frozenset(
    {
        "closed",
        "done",
        "shipped",
        "retired",
        "superseded",
        "complete",
        "archived",
        "cancelled",
        "deprecated",
        "tested",
        "failed",
    }
)

TERMINAL_STATES = frozenset({"archived", "deprecated", "cancelled", "retired"})


def is_decayed(decay: object) -> bool:
    """Return true only for stale decay at or above the shared boundary.

    Missing, malformed, clean, and below-threshold metadata is neutral.
    """

    if not isinstance(decay, dict) or decay.get("stale") is not True:
        return False
    try:
        confidence = float(decay.get("confidence", 0.0))
    except (TypeError, ValueError):
        return False
    return confidence >= DECAY_GATE_CONFIDENCE


def _normalise_lifecycle(value: object) -> str:
    return str(value).strip().casefold() if value is not None else ""


def is_live_authority_source(record: Mapping[str, object]) -> bool:
    """Whether an existing source record may confer graph authority.

    Unknown or absent lifecycle metadata remains neutral. Callers exclude a
    missing record before invoking this helper.
    """

    if is_decayed(record.get("decay")):
        return False
    if _normalise_lifecycle(record.get("status")) in TERMINAL_STATUSES:
        return False
    if _normalise_lifecycle(record.get("state")) in TERMINAL_STATES:
        return False
    return True


__all__ = [
    "DECAY_GATE_CONFIDENCE",
    "TERMINAL_STATUSES",
    "TERMINAL_STATES",
    "is_decayed",
    "is_live_authority_source",
]
