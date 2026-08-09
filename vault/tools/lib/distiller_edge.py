"""Immutable content-seam binding and deterministic distillation fallback."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from lib import metered_model
from lib.distiller_model_policy import resolve_policy
from lib.distiller_content import ContentError, ContentLoader, ContentSpan, SpanAnchor
from lib.distiller_query import PrevalidatedQuerySeeds
from lib.group_registry import Result
from lib.viewer_projection import Viewer

if TYPE_CHECKING:
    from lib.distiller import DeterministicOrientation, OrientedItem


FRESHNESS_UNKNOWN = "UNKNOWN"
CAPTURE_STATUS_PENDING = "pending"
DISTILL_MAX_TOKENS = 1024
_UID_RE = re.compile(r"^[0-9a-f]{8}$")
_DISTILL_SYSTEM = (
    "Return exactly one JSON object with key selections. Each selection must "
    "contain exactly source_uid, span_anchor, reorder_note. Select only supplied "
    "identities; reorder_note is null unless a lower-ranked source is promoted. "
    "Return no source text, new identity, score, or extra key."
)


class DistillErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    BINDING_MISMATCH = "BINDING_MISMATCH"
    CONTENT_UNAVAILABLE = "CONTENT_UNAVAILABLE"


class DistillError(Exception):
    def __init__(self, code: DistillErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class BoundOrientation:
    deterministic: "DeterministicOrientation"
    viewer: Viewer
    index_as_of: str

    def __post_init__(self) -> None:
        if not isinstance(self.viewer, Viewer):
            raise ValueError("viewer must be a Viewer")
        if not isinstance(self.index_as_of, str) or not self.index_as_of:
            raise ValueError("index_as_of must be non-empty")


@dataclass(frozen=True)
class SpanSelection:
    """A double selects identity only; source text never comes from the double."""

    source_uid: str
    span_anchor: SpanAnchor
    reorder_note: Optional[str] = None


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError(f"non-finite JSON constant {value!r}")


class DistillModelAdapter:
    """Closed Sonnet identity adapter over already viewer-safe candidate spans."""

    def __init__(
        self,
        *,
        run_binding=None,
        segment_resolver=None,
        call_model=None,
        policy_resolver=None,
        max_tokens: int = DISTILL_MAX_TOKENS,
    ) -> None:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise ValueError("max_tokens must be a positive integer")
        self._run_binding = run_binding
        self._segment_resolver = segment_resolver
        self._call_model = call_model or metered_model.call
        self._policy_resolver = policy_resolver or resolve_policy
        self._max_tokens = max_tokens

    def __call__(self, *, intent: str, candidates, chunk_budget: int):
        # Resolve policy before classification so the canonical draft/all-ask
        # state refuses without treating a missing classifier as authority.
        policy = self._policy_resolver()
        if not policy.production_enabled:
            raise RuntimeError("distill model policy is not production-enabled")
        if (
            not isinstance(intent, str)
            or not isinstance(candidates, tuple)
            or not candidates
            or any(not isinstance(span, ContentSpan) for span in candidates)
            or isinstance(chunk_budget, bool)
            or not isinstance(chunk_budget, int)
            or chunk_budget < 1
        ):
            raise ValueError("distill adapter arguments are malformed")
        identities = {}
        for span in candidates:
            if not _UID_RE.fullmatch(span.source_uid):
                raise ValueError("candidate source_uid must be lowercase 8-hex")
            key = (span.source_uid, span.span_anchor.canonical())
            if key in identities:
                raise ValueError("candidate identities must be unique")
            identities[key] = span
        if self._segment_resolver is None:
            raise RuntimeError("trusted segment resolver is unavailable")
        classes = []
        for uid in sorted({span.source_uid for span in candidates}):
            resolved = self._segment_resolver(uid)
            if resolved not in {"os", "team", "private"}:
                raise RuntimeError(f"trusted segment classification missing for {uid}")
            classes.append(resolved)
        payload = {
            "intent": intent,
            "chunk_budget": chunk_budget,
            "candidates": [
                {
                    "source_uid": span.source_uid,
                    "span_anchor": span.span_anchor.canonical(),
                    "text": span.text,
                }
                for span in candidates
            ],
        }
        user_content = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        result = self._call_model(
            "distill",
            [{"role": "user", "content": user_content}],
            segment_classes=tuple(sorted(set(classes))),
            run_binding=self._run_binding,
            max_tokens=self._max_tokens,
            system=_DISTILL_SYSTEM,
            policy_resolver=self._policy_resolver,
        )
        if isinstance(result, metered_model.ModelRefusal):
            raise RuntimeError(f"distill model refused: {result.code}")
        if not isinstance(result, metered_model.MeteredModelResult):
            raise RuntimeError("distill model returned the wrong result type")
        try:
            value = json.loads(
                result.text,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise ValueError(f"distill output is not strict JSON: {exc}") from exc
        if type(value) is not dict or set(value) != {"selections"}:
            raise ValueError("distill output must be the closed selections object")
        raw = value["selections"]
        if (
            not isinstance(raw, list)
            or not raw
            or len(raw) > chunk_budget
        ):
            raise ValueError("distill selections are empty or over budget")
        selections = []
        seen = set()
        for item in raw:
            if type(item) is not dict or set(item) != {
                "source_uid",
                "span_anchor",
                "reorder_note",
            }:
                raise ValueError("distill selection has unknown or missing fields")
            key = (item["source_uid"], item["span_anchor"])
            if key not in identities or key in seen:
                raise ValueError("distill selection is unknown or duplicated")
            note = item["reorder_note"]
            if note is not None and (
                not isinstance(note, str)
                or not note.strip()
                or len(note) > 512
            ):
                raise ValueError("distill reorder_note is malformed")
            seen.add(key)
            span = identities[key]
            selections.append(
                SpanSelection(span.source_uid, span.span_anchor, note)
            )
        return tuple(selections)


@dataclass(frozen=True)
class Chunk:
    source_uid: str
    span_anchor: SpanAnchor
    text: str
    why: "OrientedItem"
    freshness: str
    reorder_note: Optional[str] = None


@dataclass(frozen=True)
class ShownCircle:
    seeds: tuple[str, ...]
    members: tuple


@dataclass(frozen=True)
class Distillation:
    chunks: tuple[Chunk, ...]
    shown_circle: ShownCircle
    fallback_used: bool
    viewer: Viewer
    index_as_of: str
    capture_id: None = None
    capture_status: str = CAPTURE_STATUS_PENDING


@dataclass(frozen=True)
class Orientation:
    query_seeds: PrevalidatedQuerySeeds
    bound_deterministic: BoundOrientation
    distillation: Distillation


def _shown(bound: BoundOrientation, seeds: PrevalidatedQuerySeeds) -> ShownCircle:
    return ShownCircle(
        seeds=seeds.uids,
        members=tuple(bound.deterministic.circle.members),
    )


def _chunks_from_spans(
    spans: tuple[ContentSpan, ...],
    *,
    items_by_uid: dict,
    reorder_notes: Optional[dict] = None,
) -> tuple[Chunk, ...]:
    notes = reorder_notes or {}
    return tuple(
        Chunk(
            source_uid=span.source_uid,
            span_anchor=span.span_anchor,
            text=span.text,
            why=items_by_uid[span.source_uid],
            freshness=FRESHNESS_UNKNOWN,
            reorder_note=notes.get((span.source_uid, span.span_anchor)),
        )
        for span in spans
    )


def _validated_double_spans(
    proposed,
    candidates_by_key: dict,
    rank_position: dict[str, int],
    chunk_budget: int,
):
    if not isinstance(proposed, (tuple, list)) or not proposed:
        return None
    if len(proposed) > chunk_budget or any(
        not isinstance(selection, SpanSelection) for selection in proposed
    ):
        return None

    keys = []
    notes = {}
    for selection in proposed:
        if selection.reorder_note is not None and (
            not isinstance(selection.reorder_note, str)
            or not selection.reorder_note.strip()
        ):
            return None
        key = (selection.source_uid, selection.span_anchor)
        if key not in candidates_by_key or key in keys:
            return None
        keys.append(key)
        if selection.reorder_note is not None:
            notes[key] = selection.reorder_note

    # If a lower-ranked source appears before a selected higher-ranked source,
    # the lower-ranked selection itself must explain that inversion.
    positions = [rank_position[key[0]] for key in keys]
    for index, position in enumerate(positions):
        if any(later < position for later in positions[index + 1 :]):
            if keys[index] not in notes:
                return None

    return tuple(candidates_by_key[key] for key in keys), notes


def distill(
    bound: BoundOrientation,
    viewer: Viewer,
    index_as_of: str,
    chunk_budget: int,
    *,
    intent: str,
    query_seeds: PrevalidatedQuerySeeds,
    content_loader: ContentLoader,
    distill_double=None,
) -> Result:
    """Select exact ranked-member spans or fall back rank-first deterministically.

    Every binding check occurs before ``content_loader.load_spans`` is invoked.
    """

    if not isinstance(bound, BoundOrientation):
        return Result.failure(
            DistillError(
                DistillErrorCode.INVALID_ARGUMENT,
                "bound must be a BoundOrientation",
            )
        )
    if (
        not isinstance(viewer, Viewer)
        or viewer != bound.viewer
        or not isinstance(index_as_of, str)
        or not index_as_of
        or index_as_of != bound.index_as_of
        or getattr(content_loader, "index_as_of", None) != bound.index_as_of
        or not isinstance(query_seeds, PrevalidatedQuerySeeds)
        or query_seeds.viewer != bound.viewer
        or query_seeds.index_as_of != bound.index_as_of
    ):
        return Result.failure(
            DistillError(
                DistillErrorCode.BINDING_MISMATCH,
                "viewer/index_as_of binding mismatch",
            )
        )
    if (
        isinstance(chunk_budget, bool)
        or not isinstance(chunk_budget, int)
        or chunk_budget < 0
    ):
        return Result.failure(
            DistillError(
                DistillErrorCode.INVALID_ARGUMENT,
                "chunk_budget must be a non-negative int",
            )
        )

    items = tuple(bound.deterministic.items)
    items_by_uid = {item.uid: item for item in items}
    rank_position = {item.uid: index for index, item in enumerate(items)}
    candidates: list[ContentSpan] = []
    candidates_by_key = {}
    try:
        for item in items:
            loaded = content_loader.load_spans(item.uid)
            if not isinstance(loaded, tuple):
                return Result.failure(
                    DistillError(
                        DistillErrorCode.CONTENT_UNAVAILABLE,
                        "loader returned malformed spans",
                    )
                )
            for span in loaded:
                if not isinstance(span, ContentSpan) or span.source_uid != item.uid:
                    return Result.failure(
                        DistillError(
                            DistillErrorCode.CONTENT_UNAVAILABLE,
                            "loader returned a malformed or mismatched span",
                        )
                    )
                key = (span.source_uid, span.span_anchor)
                if key in candidates_by_key:
                    return Result.failure(
                        DistillError(
                            DistillErrorCode.CONTENT_UNAVAILABLE,
                            "loader returned a duplicate span identity",
                        )
                    )
                candidates.append(span)
                candidates_by_key[key] = span
    except ContentError as error:
        return Result.failure(
            DistillError(DistillErrorCode.CONTENT_UNAVAILABLE, str(error))
        )
    except Exception:
        return Result.failure(
            DistillError(
                DistillErrorCode.CONTENT_UNAVAILABLE, "content loader failed"
            )
        )

    fallback_spans = tuple(candidates[:chunk_budget])
    chosen = None
    if distill_double is not None and chunk_budget > 0:
        try:
            proposed = distill_double(
                intent=intent,
                candidates=tuple(candidates),
                chunk_budget=chunk_budget,
            )
        except Exception:
            proposed = None
        chosen = _validated_double_spans(
            proposed, candidates_by_key, rank_position, chunk_budget
        )

    if chosen is None:
        chunks = _chunks_from_spans(fallback_spans, items_by_uid=items_by_uid)
        fallback_used = True
    else:
        selected_spans, notes = chosen
        chunks = _chunks_from_spans(
            selected_spans, items_by_uid=items_by_uid, reorder_notes=notes
        )
        fallback_used = False

    return Result.success(
        Distillation(
            chunks=chunks,
            shown_circle=_shown(bound, query_seeds),
            fallback_used=fallback_used,
            viewer=bound.viewer,
            index_as_of=bound.index_as_of,
        )
    )


__all__ = [
    "FRESHNESS_UNKNOWN",
    "CAPTURE_STATUS_PENDING",
    "DistillErrorCode",
    "DistillError",
    "BoundOrientation",
    "SpanSelection",
    "DistillModelAdapter",
    "DISTILL_MAX_TOKENS",
    "Chunk",
    "ShownCircle",
    "Distillation",
    "Orientation",
    "distill",
]
