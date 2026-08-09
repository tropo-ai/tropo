"""Append one strict, segment-attested distillation usage event."""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from lib import event_identity
from lib.capture_segment import (
    CaptureSegmentError,
    derive_capture_segment,
)


USAGE_EVENT_TYPE = "tropo.distill.usage.recorded"
_EMITTER_SOURCE = "/tools/emit-event"
_EMITTER_SOURCE_UID = "ca90f098"
_HEX8 = re.compile(r"^[0-9a-f]{8}$")


class CaptureUsageErrorCode(str, Enum):
    IDENTITY_INVALID = "IDENTITY_INVALID"
    SNAPSHOT_INVALID = "SNAPSHOT_INVALID"
    OPERATION_INVALID = "OPERATION_INVALID"
    PARTITION_INVALID = "PARTITION_INVALID"
    SEGMENT_DERIVATION_FAILED = "SEGMENT_DERIVATION_FAILED"
    EMISSION_FAILED = "EMISSION_FAILED"


class CaptureUsageError(ValueError):
    """Typed refusal raised before append unless the emitter itself fails."""

    def __init__(
        self,
        code: CaptureUsageErrorCode,
        message: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.cause = cause


@dataclass(frozen=True)
class CaptureReceipt:
    """Immutable identity of the event appended for this capture."""

    event_uid: str


def _require_uid(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HEX8.fullmatch(value):
        raise CaptureUsageError(
            CaptureUsageErrorCode.IDENTITY_INVALID,
            f"{field} must be an 8-character lowercase hexadecimal UID",
        )
    return value


def _chunk_sequence(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CaptureUsageError(
            CaptureUsageErrorCode.PARTITION_INVALID,
            f"{field} must be a sequence of stable opaque chunk UIDs",
        )
    values = tuple(value)
    for uid in values:
        if not isinstance(uid, str) or not uid or uid.strip() != uid:
            raise CaptureUsageError(
                CaptureUsageErrorCode.PARTITION_INVALID,
                f"{field} contains a malformed chunk UID",
            )
    if len(set(values)) != len(values):
        raise CaptureUsageError(
            CaptureUsageErrorCode.PARTITION_INVALID,
            f"{field} contains a duplicate chunk UID",
        )
    return values


def _validate_partition(
    ranked_chunk_uids: object,
    used_chunk_uids: object,
    unused_chunk_uids: object,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    ranked = _chunk_sequence(ranked_chunk_uids, "ranked_chunk_uids")
    used = _chunk_sequence(used_chunk_uids, "used_chunk_uids")
    unused = _chunk_sequence(unused_chunk_uids, "unused_chunk_uids")
    if not ranked:
        raise CaptureUsageError(
            CaptureUsageErrorCode.PARTITION_INVALID,
            "ranked_chunk_uids must be non-empty",
        )
    if set(used) & set(unused):
        raise CaptureUsageError(
            CaptureUsageErrorCode.PARTITION_INVALID,
            "used and unused chunk UID lists overlap",
        )
    if set(used) | set(unused) != set(ranked):
        raise CaptureUsageError(
            CaptureUsageErrorCode.PARTITION_INVALID,
            "used and unused chunk UID lists must exactly partition ranked_chunk_uids",
        )
    positions = {uid: index for index, uid in enumerate(ranked)}
    for field, classified in (
        ("used_chunk_uids", used),
        ("unused_chunk_uids", unused),
    ):
        indexes = [positions[uid] for uid in classified]
        if indexes != sorted(indexes):
            raise CaptureUsageError(
                CaptureUsageErrorCode.PARTITION_INVALID,
                f"{field} does not preserve relative rank order",
            )
    return ranked, used, unused


def capture_usage(
    task_uid: object,
    viewer_principal_uid: object,
    index_as_of: object,
    operation: object,
    ranked_chunk_uids: object,
    used_chunk_uids: object,
    unused_chunk_uids: object,
    *,
    segment_of_chunk: object,
    resolver: object,
    strict_emitter: Callable[..., dict],
) -> CaptureReceipt:
    """Validate, derive, append exactly one event, and return its identity."""

    task = _require_uid(task_uid, "task_uid")
    viewer = _require_uid(viewer_principal_uid, "viewer_principal_uid")
    if (
        not isinstance(index_as_of, str)
        or not index_as_of
        or not index_as_of.strip()
    ):
        raise CaptureUsageError(
            CaptureUsageErrorCode.SNAPSHOT_INVALID,
            "index_as_of must be a non-empty opaque snapshot token",
        )
    if operation != "distill":
        raise CaptureUsageError(
            CaptureUsageErrorCode.OPERATION_INVALID,
            "operation must be the literal 'distill'",
        )
    ranked, used, unused = _validate_partition(
        ranked_chunk_uids,
        used_chunk_uids,
        unused_chunk_uids,
    )
    try:
        attestation = derive_capture_segment(ranked, segment_of_chunk, resolver)
    except CaptureSegmentError as exc:
        raise CaptureUsageError(
            CaptureUsageErrorCode.SEGMENT_DERIVATION_FAILED,
            str(exc),
            cause=exc,
        ) from exc

    data = {
        "task_uid": task,
        "viewer_principal_uid": viewer,
        "index_as_of": index_as_of,
        "operation": "distill",
        "used_chunk_uids": list(used),
        "unused_chunk_uids": list(unused),
    }
    try:
        emitted = strict_emitter(
            event_type=USAGE_EVENT_TYPE,
            source=_EMITTER_SOURCE,
            source_uid=_EMITTER_SOURCE_UID,
            lifecycle="evergreen",
            subject=task,
            data=data,
            segment=attestation.segment,
            segment_attestation=attestation,
            strict=True,
        )
        event_uid = event_identity.immutable_event_uid(emitted)
    except Exception as exc:
        raise CaptureUsageError(
            CaptureUsageErrorCode.EMISSION_FAILED,
            f"strict usage event emission failed: {exc}",
            cause=exc,
        ) from exc
    if not isinstance(event_uid, str) or not event_uid:
        raise CaptureUsageError(
            CaptureUsageErrorCode.EMISSION_FAILED,
            "strict emitter returned no immutable event UID",
        )
    return CaptureReceipt(event_uid=event_uid)


__all__ = [
    "CaptureReceipt",
    "CaptureUsageError",
    "CaptureUsageErrorCode",
    "USAGE_EVENT_TYPE",
    "capture_usage",
]
