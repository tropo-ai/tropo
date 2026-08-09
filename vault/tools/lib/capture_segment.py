"""Derive the visibility segment for one distillation usage capture.

The derivation delegates every ordering decision to the installed
``GroupResolver``.  It has no string-, first-seen-, or private-segment
fallback.  The returned frozen attestation is process-internal evidence for
the strict event emitter; callers never supply an event segment directly.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CaptureSegmentErrorCode(str, Enum):
    EMPTY_CAPTURE = "EMPTY_CAPTURE"
    CHUNK_UID_INVALID = "CHUNK_UID_INVALID"
    CHUNK_UID_DUPLICATE = "CHUNK_UID_DUPLICATE"
    SEGMENT_LOOKUP_FAILED = "SEGMENT_LOOKUP_FAILED"
    SEGMENT_INVALID = "SEGMENT_INVALID"
    RESOLVER_FAILED = "RESOLVER_FAILED"
    MOST_RESTRICTED_NOT_UNIQUE = "MOST_RESTRICTED_NOT_UNIQUE"
    ATTESTATION_INVALID = "ATTESTATION_INVALID"


class CaptureSegmentError(ValueError):
    """Typed, fail-closed segment-derivation refusal."""

    def __init__(
        self,
        code: CaptureSegmentErrorCode,
        message: str,
        *,
        chunk_uid: str | None = None,
        segment: str | None = None,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.chunk_uid = chunk_uid
        self.segment = segment


_ATTESTATION_ISSUER = object()


@dataclass(frozen=True, init=False)
class SegmentAttestation:
    """Internal proof binding one ranked UID sequence to its derived segment."""

    ranked_chunk_uids: tuple[str, ...]
    segment: str
    _issuer: object = field(repr=False, compare=False)

    def __new__(cls, *args: object, **kwargs: object) -> "SegmentAttestation":
        raise TypeError("SegmentAttestation values are created only by derivation")

    @classmethod
    def _create(
        cls,
        ranked_chunk_uids: tuple[str, ...],
        segment: str,
    ) -> "SegmentAttestation":
        value = object.__new__(cls)
        object.__setattr__(value, "ranked_chunk_uids", ranked_chunk_uids)
        object.__setattr__(value, "segment", segment)
        object.__setattr__(value, "_issuer", _ATTESTATION_ISSUER)
        return value


def _uid_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.CHUNK_UID_INVALID,
            "ranked_chunk_uids must be a sequence of stable opaque strings",
        )
    uids = tuple(value)
    if not uids:
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.EMPTY_CAPTURE,
            "at least one ranked chunk UID is required",
        )
    seen: set[str] = set()
    for uid in uids:
        if not isinstance(uid, str) or not uid or uid.strip() != uid:
            raise CaptureSegmentError(
                CaptureSegmentErrorCode.CHUNK_UID_INVALID,
                "chunk UIDs must be non-empty, unmodified opaque strings",
                chunk_uid=uid if isinstance(uid, str) else None,
            )
        if uid in seen:
            raise CaptureSegmentError(
                CaptureSegmentErrorCode.CHUNK_UID_DUPLICATE,
                f"duplicate ranked chunk UID {uid!r}",
                chunk_uid=uid,
            )
        seen.add(uid)
    return uids


def _lookup_segment(
    lookup: Mapping[str, str] | Callable[[str], str],
    chunk_uid: str,
) -> str:
    try:
        if isinstance(lookup, Mapping):
            segment = lookup[chunk_uid]
        elif callable(lookup):
            segment = lookup(chunk_uid)
        else:
            raise TypeError("segment_of_chunk is neither a mapping nor callable")
    except Exception as exc:
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.SEGMENT_LOOKUP_FAILED,
            f"segment lookup failed for chunk UID {chunk_uid!r}: {exc}",
            chunk_uid=chunk_uid,
        ) from exc
    if (
        not isinstance(segment, str)
        or not segment
        or segment.strip() != segment
    ):
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.SEGMENT_INVALID,
            f"chunk UID {chunk_uid!r} resolved to a malformed segment",
            chunk_uid=chunk_uid,
            segment=segment if isinstance(segment, str) else None,
        )
    return segment


def _resolver_answer(resolver: object, wider: str, narrower: str) -> bool:
    try:
        answer = resolver.is_equal_or_wider(wider, narrower)
    except Exception as exc:
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.RESOLVER_FAILED,
            f"resolver failed comparing {wider!r} to {narrower!r}: {exc}",
            segment=narrower,
        ) from exc
    if not getattr(answer, "ok", False):
        error = getattr(answer, "error", None)
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.RESOLVER_FAILED,
            f"resolver refused comparing {wider!r} to {narrower!r}: {error}",
            segment=narrower,
        ) from error
    value = getattr(answer, "value", None)
    if not isinstance(value, bool):
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.RESOLVER_FAILED,
            "resolver returned a non-boolean relation",
            segment=narrower,
        )
    return value


def derive_capture_segment(
    ranked_chunk_uids: object,
    segment_of_chunk: Mapping[str, str] | Callable[[str], str],
    resolver: object,
) -> SegmentAttestation:
    """Return the sole all-others-equal-or-wider segment attestation.

    Every unique chunk UID is resolved before comparison.  Candidate ``s`` is
    accepted exactly when ``resolver.is_equal_or_wider(t, s)`` is true for
    every derived segment ``t``.  Zero or multiple candidates are refusals.
    """

    ranked = _uid_sequence(ranked_chunk_uids)
    segments_by_uid = {
        uid: _lookup_segment(segment_of_chunk, uid)
        for uid in ranked
    }
    candidates = tuple(dict.fromkeys(segments_by_uid.values()))
    most_restricted: list[str] = []
    for candidate in candidates:
        if all(
            _resolver_answer(resolver, other, candidate)
            for other in candidates
        ):
            most_restricted.append(candidate)
    if len(most_restricted) != 1:
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.MOST_RESTRICTED_NOT_UNIQUE,
            "derived segments have no unique most-restricted candidate",
        )
    return SegmentAttestation._create(ranked, most_restricted[0])


def verify_segment_attestation(
    attestation: object,
    *,
    segment: object,
    used_chunk_uids: object,
    unused_chunk_uids: object,
) -> None:
    """Verify internal provenance and the exact attested ranked partition."""

    if (
        type(attestation) is not SegmentAttestation
        or getattr(attestation, "_issuer", None) is not _ATTESTATION_ISSUER
    ):
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.ATTESTATION_INVALID,
            "segment attestation was not issued by derive_capture_segment",
        )
    if segment != attestation.segment:
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.ATTESTATION_INVALID,
            "event segment does not match the derived attestation",
            segment=segment if isinstance(segment, str) else None,
        )
    if not isinstance(used_chunk_uids, list) or not isinstance(unused_chunk_uids, list):
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.ATTESTATION_INVALID,
            "attested usage payload must carry chunk UID lists",
        )
    used = tuple(used_chunk_uids)
    unused = tuple(unused_chunk_uids)
    ranked = attestation.ranked_chunk_uids
    if (
        len(set(used)) != len(used)
        or len(set(unused)) != len(unused)
        or set(used) & set(unused)
        or set(used) | set(unused) != set(ranked)
    ):
        raise CaptureSegmentError(
            CaptureSegmentErrorCode.ATTESTATION_INVALID,
            "usage payload is not the exact attested chunk UID partition",
        )
    positions = {uid: index for index, uid in enumerate(ranked)}
    for classified in (used, unused):
        try:
            indexes = [positions[uid] for uid in classified]
        except (KeyError, TypeError) as exc:
            raise CaptureSegmentError(
                CaptureSegmentErrorCode.ATTESTATION_INVALID,
                "usage payload contains a chunk UID outside the attestation",
            ) from exc
        if indexes != sorted(indexes):
            raise CaptureSegmentError(
                CaptureSegmentErrorCode.ATTESTATION_INVALID,
                "usage payload order differs from the attested rank order",
            )


__all__ = [
    "CaptureSegmentError",
    "CaptureSegmentErrorCode",
    "SegmentAttestation",
    "derive_capture_segment",
    "verify_segment_attestation",
]
