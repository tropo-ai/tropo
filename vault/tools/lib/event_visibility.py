"""Viewer-safe filtering for segment-stamped distillation usage events."""
from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from lib.distiller_capture import USAGE_EVENT_TYPE


class EventVisibilityErrorCode(str, Enum):
    AUTHORITY_UNRESOLVED = "AUTHORITY_UNRESOLVED"
    EVENT_SEGMENT_INVALID = "EVENT_SEGMENT_INVALID"


class EventVisibilityError(ValueError):
    """Typed refusal; query callers must never fall back to allow-all."""

    def __init__(
        self,
        code: EventVisibilityErrorCode,
        message: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.cause = cause


def filter_usage_events(
    events: Iterable[dict],
    *,
    viewer: object,
    projection: object,
) -> list[dict]:
    """Filter one event sequence after resolving viewer visibility exactly once.

    Historical unsegmented events pass through unchanged.  A segment-stamped
    event is retained only when its exact segment is visible.  A usage event
    without its mandatory segment is malformed and fails closed.
    """

    try:
        resolution = projection.visible_segments(viewer)
    except Exception as exc:
        raise EventVisibilityError(
            EventVisibilityErrorCode.AUTHORITY_UNRESOLVED,
            f"viewer segment authority raised: {exc}",
            cause=exc,
        ) from exc
    if not getattr(resolution, "ok", False):
        error = getattr(resolution, "error", None)
        raise EventVisibilityError(
            EventVisibilityErrorCode.AUTHORITY_UNRESOLVED,
            f"viewer segment authority refused: {error}",
            cause=error if isinstance(error, Exception) else None,
        ) from (error if isinstance(error, Exception) else None)
    try:
        visible_segments = frozenset(resolution.value)
    except Exception as exc:
        raise EventVisibilityError(
            EventVisibilityErrorCode.AUTHORITY_UNRESOLVED,
            "viewer segment authority returned a malformed visible set",
            cause=exc,
        ) from exc

    kept: list[dict] = []
    for event in events:
        segment = event.get("segment")
        if segment is None:
            if event.get("type") == USAGE_EVENT_TYPE:
                raise EventVisibilityError(
                    EventVisibilityErrorCode.EVENT_SEGMENT_INVALID,
                    "usage event is missing its mandatory derived segment",
                )
            kept.append(event)
            continue
        if (
            not isinstance(segment, str)
            or not segment
            or segment.strip() != segment
        ):
            raise EventVisibilityError(
                EventVisibilityErrorCode.EVENT_SEGMENT_INVALID,
                "event carries a malformed segment",
            )
        if segment in visible_segments:
            kept.append(event)
    return kept


__all__ = [
    "EventVisibilityError",
    "EventVisibilityErrorCode",
    "filter_usage_events",
]
