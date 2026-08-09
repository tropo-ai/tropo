"""Viewer-safe freeform-query resolution for the deterministic distiller edge.

An injected local parse double may propose structural UIDs. Otherwise (or when
its result is unusable) a read-only FTS index supplies UID candidates. Both paths
cross the same total ViewerProjection filter before sorting or limiting.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional

from lib.group_registry import Result
from lib import metered_model
from lib.viewer_projection import Viewer, ViewerProjection


DEFAULT_QUERY_SEED_LIMIT = 16
PARSE_QUERY_MAX_TOKENS = 256
_UID_RE = re.compile(r"^[0-9a-f]{8}$")
_PARSE_SYSTEM = (
    "Return exactly one JSON object with one key, uids. uids must be a list "
    "of at most 16 lowercase 8-hex structural UIDs. Return no prose, scores, "
    "snippets, visibility claims, or extra keys."
)


class QueryErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    BINDING_MISMATCH = "BINDING_MISMATCH"
    INDEX_UNAVAILABLE = "INDEX_UNAVAILABLE"
    MALFORMED_RESULT = "MALFORMED_RESULT"


class QueryError(Exception):
    """Typed query-edge refusal."""

    def __init__(self, code: QueryErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class QueryProposal:
    """The only structured output an injected parse double needs to produce."""

    uids: tuple[str, ...]


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError(f"non-finite JSON constant {value!r}")


class ParseQueryModelAdapter:
    """Closed Haiku proposal adapter; visibility remains projection-owned."""

    def __init__(
        self,
        *,
        run_binding=None,
        segment_class: str = "private",
        call_model=None,
        policy_resolver=None,
        max_tokens: int = PARSE_QUERY_MAX_TOKENS,
    ) -> None:
        if segment_class not in {"os", "team", "private"}:
            raise ValueError("segment_class must be os, team, or private")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise ValueError("max_tokens must be a positive integer")
        self._run_binding = run_binding
        self._segment_class = segment_class
        self._call_model = call_model or metered_model.call
        self._policy_resolver = policy_resolver
        self._max_tokens = max_tokens

    def __call__(self, *, intent: str, viewer: Viewer) -> QueryProposal:
        if not isinstance(intent, str) or not isinstance(viewer, Viewer):
            raise ValueError("parse adapter requires string intent and Viewer")
        payload = json.dumps(
            {"intent": intent},
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        kwargs = {
            "segment_classes": (self._segment_class,),
            "run_binding": self._run_binding,
            "max_tokens": self._max_tokens,
            "system": _PARSE_SYSTEM,
        }
        if self._policy_resolver is not None:
            kwargs["policy_resolver"] = self._policy_resolver
        result = self._call_model(
            "parse-query",
            [{"role": "user", "content": payload}],
            **kwargs,
        )
        if isinstance(result, metered_model.ModelRefusal):
            raise RuntimeError(f"parse-query model refused: {result.code}")
        if not isinstance(result, metered_model.MeteredModelResult):
            raise RuntimeError("parse-query model returned the wrong result type")
        try:
            value = json.loads(
                result.text,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise ValueError(f"parse-query output is not strict JSON: {exc}") from exc
        if type(value) is not dict or set(value) != {"uids"}:
            raise ValueError("parse-query output must be the closed uids object")
        uids = value["uids"]
        if (
            not isinstance(uids, list)
            or len(uids) > DEFAULT_QUERY_SEED_LIMIT
            or any(not isinstance(uid, str) or not _UID_RE.fullmatch(uid) for uid in uids)
        ):
            raise ValueError("parse-query uids must be bounded lowercase 8-hex strings")
        return QueryProposal(tuple(sorted(set(uids))))


@dataclass(frozen=True)
class PrevalidatedQuerySeeds:
    """Immutable visible query seeds bound to one Viewer and index snapshot."""

    viewer: Viewer
    index_as_of: str
    uids: tuple[str, ...]
    fallback_used: bool

    def __post_init__(self) -> None:
        if not isinstance(self.viewer, Viewer):
            raise ValueError("viewer must be a Viewer")
        if not isinstance(self.index_as_of, str) or not self.index_as_of:
            raise ValueError("index_as_of must be non-empty")
        if (
            not isinstance(self.uids, tuple)
            or any(not isinstance(uid, str) or not uid for uid in self.uids)
            or self.uids != tuple(sorted(set(self.uids)))
        ):
            raise ValueError("uids must be a sorted, de-duplicated tuple")
        if not isinstance(self.fallback_used, bool):
            raise ValueError("fallback_used must be bool")

    def canonical(self) -> str:
        return json.dumps(
            {
                "viewer": {
                    "principal_uid": self.viewer.principal_uid,
                    "private_segment_uid": self.viewer.private_segment_uid,
                },
                "index_as_of": self.index_as_of,
                "uids": list(self.uids),
                "fallback_used": self.fallback_used,
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class QueryIndex:
    """Read-only UID-candidate source bound to an opaque index snapshot."""

    index_as_of: str

    def search_uids(self, terms: tuple[str, ...]) -> tuple[str, ...]:
        raise NotImplementedError


class InMemoryQueryIndex(QueryIndex):
    """Deterministic local query fixture over ``uid -> searchable text``."""

    def __init__(self, records: Mapping[str, str], *, index_as_of: str) -> None:
        self._records = dict(records)
        self.index_as_of = index_as_of

    def search_uids(self, terms: tuple[str, ...]) -> tuple[str, ...]:
        if not terms:
            return ()
        matches = []
        for uid, text in self._records.items():
            normalized = unicodedata.normalize("NFKC", str(text)).casefold()
            if any(term in normalized for term in terms):
                matches.append(uid)
        return tuple(matches)


class SqliteQueryIndex(QueryIndex):
    """Read-only FTS5 candidate source over ``entries_fts``.

    The SQL deliberately has no LIMIT, OFFSET, snippet, count, or rank ordering.
    Every matching UID is returned to the projection before any output bound.
    """

    def __init__(self, index_path: "str | Path", *, index_as_of: str) -> None:
        self._index_path = Path(index_path)
        self.index_as_of = index_as_of
        self._conn: Optional[sqlite3.Connection] = None

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            if not self._index_path.exists():
                raise QueryError(
                    QueryErrorCode.INDEX_UNAVAILABLE,
                    f"composed index not found at {self._index_path}",
                )
            self._conn = sqlite3.connect(
                f"file:{self._index_path}?mode=ro", uri=True
            )
        return self._conn

    def search_uids(self, terms: tuple[str, ...]) -> tuple[str, ...]:
        if not terms:
            return ()
        expression = " OR ".join(
            f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms
        )
        try:
            rows = self._connection().execute(
                "SELECT uid FROM entries_fts WHERE entries_fts MATCH ?",
                (expression,),
            ).fetchall()
        except sqlite3.Error as error:
            raise QueryError(
                QueryErrorCode.INDEX_UNAVAILABLE, "FTS query failed"
            ) from error
        return tuple(row[0] for row in rows)


def normalize_query_terms(intent: object) -> tuple[str, ...]:
    """NFKC/casefold freeform prose into sorted, unique FTS-safe terms."""

    if not isinstance(intent, str):
        return ()
    normalized = unicodedata.normalize("NFKC", intent).casefold()
    # Word characters are extracted rather than interpreted as FTS syntax.
    return tuple(sorted(set(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))))


def _parse_proposals(parse_double, intent: str, viewer: Viewer):
    try:
        proposed = parse_double(intent=intent, viewer=viewer)
    except Exception:
        return None
    if isinstance(proposed, QueryProposal):
        proposed = proposed.uids
    if not isinstance(proposed, (tuple, list)):
        return None
    if any(not isinstance(uid, str) or not uid for uid in proposed):
        return None
    return tuple(proposed)


def resolve_query(
    intent: str,
    viewer: Viewer,
    index_as_of: str,
    *,
    projection: ViewerProjection,
    query_index: QueryIndex,
    parse_double=None,
    seed_limit: int = DEFAULT_QUERY_SEED_LIMIT,
) -> Result:
    """Resolve prose to immutable, visible, viewer/snapshot-bound UID seeds."""

    if not isinstance(viewer, Viewer):
        return Result.failure(
            QueryError(QueryErrorCode.INVALID_ARGUMENT, "viewer must be a Viewer")
        )
    if not isinstance(index_as_of, str) or not index_as_of:
        return Result.failure(
            QueryError(
                QueryErrorCode.INVALID_ARGUMENT, "index_as_of must be non-empty"
            )
        )
    if getattr(query_index, "index_as_of", None) != index_as_of:
        return Result.failure(
            QueryError(
                QueryErrorCode.BINDING_MISMATCH,
                "query index is not bound to requested index_as_of",
            )
        )
    if isinstance(seed_limit, bool) or not isinstance(seed_limit, int) or seed_limit <= 0:
        return Result.failure(
            QueryError(QueryErrorCode.INVALID_ARGUMENT, "seed_limit must be positive")
        )

    if not isinstance(intent, str) or not intent.strip():
        return Result.success(
            PrevalidatedQuerySeeds(viewer, index_as_of, (), False)
        )

    if parse_double is not None:
        proposals = _parse_proposals(parse_double, intent, viewer)
        if proposals is not None:
            visible = projection.filter_visible_uids(proposals, viewer)
            if not visible.ok:
                return Result.failure(visible.error)
            if visible.value:
                return Result.success(
                    PrevalidatedQuerySeeds(
                        viewer,
                        index_as_of,
                        tuple(visible.value[:seed_limit]),
                        False,
                    )
                )

    terms = normalize_query_terms(intent)
    try:
        candidates = query_index.search_uids(terms)
    except QueryError as error:
        return Result.failure(error)
    except Exception as error:
        return Result.failure(
            QueryError(QueryErrorCode.INDEX_UNAVAILABLE, "query index failed")
        )
    if not isinstance(candidates, (tuple, list)) or any(
        not isinstance(uid, str) or not uid for uid in candidates
    ):
        return Result.failure(
            QueryError(
                QueryErrorCode.MALFORMED_RESULT,
                "query index must return UID strings only",
            )
        )

    # Load-bearing order: consume all candidates through the total projection,
    # then sort (inside the projection) and bound the visible result.
    visible = projection.filter_visible_uids(tuple(candidates), viewer)
    if not visible.ok:
        return Result.failure(visible.error)
    return Result.success(
        PrevalidatedQuerySeeds(
            viewer,
            index_as_of,
            tuple(visible.value[:seed_limit]),
            True,
        )
    )


__all__ = [
    "DEFAULT_QUERY_SEED_LIMIT",
    "QueryErrorCode",
    "QueryError",
    "QueryProposal",
    "ParseQueryModelAdapter",
    "PARSE_QUERY_MAX_TOKENS",
    "PrevalidatedQuerySeeds",
    "QueryIndex",
    "InMemoryQueryIndex",
    "SqliteQueryIndex",
    "normalize_query_terms",
    "resolve_query",
]
