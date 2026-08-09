"""Deterministic B4a group-registry projector and resolver.

This module is the projection + resolver layer on top of the pure group
semantics in :mod:`lib.group_contract`.  It never parses YAML, never touches
the network, and takes no absolute paths.  Callers inject an already-validated
:class:`~lib.group_contract.GroupCorpus` plus the authority-revision context
that pins it (``source_authority_uid``, ``source_revision`` == corpus
revision, ``principal_directory_revision``, and a per-group ``source_path``).

Locked architecture choice 2 governs the split enforced here: the resolver
reads verified canonical JSONL directly.  SQLite is mandatory acceleration and
parity *evidence*, never a second authority.  :func:`build_parity_database`
projects the JSONL into SQLite and :func:`check_sqlite_parity` reconstructs
*every* listed logical field from SQLite and compares it field-for-field
against the parsed JSONL; a count-only or selected-column comparison is
insufficient and any disagreement (including a mutated database) surfaces as
``PROJECTION_MISMATCH``.

All refusals reuse :class:`~lib.group_contract.GroupContractError` and the
closed :class:`~lib.group_contract.GroupErrorCode` vocabulary.  Errors are
never converted into empty membership or a reason-free ``False``.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from lib.group_contract import (
    GroupContractError,
    GroupCorpus,
    GroupErrorCode,
    semantic_hash,
)


CANONICALIZATION_VERSION = 1
WRAPPER_SCHEMA_ID = "tropo.group-registry-wrapper/v1"
PARITY_TABLE = "group_registry"

# The exact, locked registry JSONL row key order (dev-spec 0bfa771d, section
# "Registry, resolver, and contextual audience").  Row serialization and JSONL
# parsing both assert this order literally; it is never reordered.
REGISTRY_ROW_KEYS: tuple[str, ...] = (
    "group_uid",
    "slug",
    "title",
    "status",
    "version",
    "owner_uid",
    "direct_member_uids",
    "direct_included_group_uids",
    "effective_member_uids",
    "wider_group_uids",
    "source_authority_uid",
    "source_revision",
    "source_path",
    "source_hash",
    "principal_directory_revision",
)

_ROW_STRING_KEYS = (
    "group_uid",
    "slug",
    "title",
    "status",
    "owner_uid",
    "source_authority_uid",
    "source_revision",
    "source_path",
    "source_hash",
    "principal_directory_revision",
)
_ROW_LIST_KEYS = (
    "direct_member_uids",
    "direct_included_group_uids",
    "effective_member_uids",
    "wider_group_uids",
)

# Producers publish the registry (finalize seals, authority install publishes,
# rebuild tools re-project).  Consumers read the single adapter (dev-spec:
# mount, full validation, check-one, Gardener, cross-vault member_of).  Both are
# overridable; the wrapper binds whatever set is used.
DEFAULT_PRODUCERS: tuple[str, ...] = (
    "tropo-finalize-group",
    "tropo-group-authority",
    "tropo-rebuild-group-registry",
    "tropo-rebuild-index",
)
DEFAULT_CONSUMERS: tuple[str, ...] = (
    "tropo-mount",
    "tropo-validate",
    "tropo-check-one",
    "gardener",
    "cross_vault_member_of",
)

T = TypeVar("T")


def _raise(
    code: GroupErrorCode,
    message: str,
    *,
    group_uid: str | None = None,
    field: str | None = None,
    reference_uid: str | None = None,
) -> None:
    raise GroupContractError(
        code,
        message,
        group_uid=group_uid,
        field=field,
        reference_uid=reference_uid,
    )


@dataclass(frozen=True)
class Result(Generic[T]):
    """A ``Result<T, GroupError>`` value as required by the dev-spec.

    A successful result carries ``value`` (which may legitimately be ``False``
    for the boolean operations); a failed result carries a typed
    :class:`~lib.group_contract.GroupContractError`.  A boolean ``False`` is
    therefore never confused with a refusal.
    """

    ok: bool
    value: T | None = None
    error: GroupContractError | None = None

    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(True, value, None)

    @classmethod
    def failure(cls, error: GroupContractError) -> "Result[T]":
        return cls(False, None, error)

    def unwrap(self) -> T:
        """Return the value, or raise the typed error for callers that prefer
        exception style over inspecting :attr:`ok`."""

        if not self.ok:
            assert self.error is not None
            raise self.error
        return self.value  # type: ignore[return-value]


@dataclass(frozen=True)
class AuthorityRevisionContext:
    """Injected authority-revision context that pins one corpus generation.

    ``source_revision`` equals the authority tuple ``corpus_revision`` and
    ``source_authority_uid``/``principal_directory_revision`` equal the tuple
    fields of the same name.  ``source_paths`` maps every active group UID to
    its corpus-root-relative POSIX source path.
    """

    source_authority_uid: str
    source_revision: str
    principal_directory_revision: str
    source_paths: Mapping[str, str]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AuthorityRevisionContext":
        if not isinstance(data, Mapping):
            _raise(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                "authority-revision context must be a mapping",
            )
        return cls(
            source_authority_uid=data.get("source_authority_uid"),  # type: ignore[arg-type]
            source_revision=data.get("source_revision"),  # type: ignore[arg-type]
            principal_directory_revision=data.get(  # type: ignore[arg-type]
                "principal_directory_revision"
            ),
            source_paths=data.get("source_paths", {}),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class RegistryWrapper:
    """Immutable wrapper binding for one projected registry.

    Binds the exact JSONL byte digest, row count, canonicalization version,
    producers, consumers, and the authority revision (authority UID, corpus
    revision, and principal-directory revision).
    """

    jsonl_sha256: str
    row_count: int
    canonicalization_version: int
    source_authority_uid: str
    source_revision: str
    principal_directory_revision: str
    producers: tuple[str, ...]
    consumers: tuple[str, ...]

    def canonical_object(self) -> dict[str, Any]:
        return {
            "schema_id": WRAPPER_SCHEMA_ID,
            "canonicalization_version": self.canonicalization_version,
            "jsonl_sha256": self.jsonl_sha256,
            "row_count": self.row_count,
            "source_authority_uid": self.source_authority_uid,
            "source_revision": self.source_revision,
            "principal_directory_revision": self.principal_directory_revision,
            "producers": list(self.producers),
            "consumers": list(self.consumers),
        }

    def canonical_bytes(self) -> bytes:
        return (
            json.dumps(
                self.canonical_object(),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )

    @property
    def wrapper_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class RegistryProjection:
    """A complete deterministic projection of one corpus generation."""

    jsonl_bytes: bytes
    rows: tuple[Mapping[str, Any], ...]
    wrapper: RegistryWrapper
    source_authority_uid: str
    source_revision: str
    principal_directory_revision: str

    @property
    def jsonl_sha256(self) -> str:
        return hashlib.sha256(self.jsonl_bytes).hexdigest()

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def group_uids(self) -> tuple[str, ...]:
        return tuple(row["group_uid"] for row in self.rows)


def _copy_row(row: Mapping[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = {}
    for key in REGISTRY_ROW_KEYS:
        value = row[key]
        copied[key] = list(value) if isinstance(value, list) else value
    return copied


def _encode_row(row: Mapping[str, Any]) -> bytes:
    ordered = {key: row[key] for key in REGISTRY_ROW_KEYS}
    return (
        json.dumps(
            ordered,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _encode_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    ordered_rows = sorted(rows, key=lambda row: row["group_uid"])
    return b"".join(_encode_row(row) for row in ordered_rows)


def _require_str_tuple(values: object, subject: str) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"registry {subject} must be a sequence of strings",
        )
    result: list[str] = []
    for value in values:  # type: ignore[union-attr]
        if not isinstance(value, str) or not value:
            _raise(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                f"registry {subject} entries must be non-empty strings",
            )
        result.append(value)
    return tuple(result)


def _require_context(context: object) -> AuthorityRevisionContext:
    if not isinstance(context, AuthorityRevisionContext):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            "authority-revision context is unavailable for projection",
        )
    for name in (
        "source_authority_uid",
        "source_revision",
        "principal_directory_revision",
    ):
        value = getattr(context, name)
        if not isinstance(value, str) or not value.strip():
            _raise(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                f"authority-revision context field {name!r} is missing or blank",
            )
    if not isinstance(context.source_paths, Mapping):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            "authority-revision context 'source_paths' must be a mapping",
        )
    return context


def _resolve_source_path(context: AuthorityRevisionContext, group_uid: str) -> str:
    path = context.source_paths.get(group_uid)
    if not isinstance(path, str) or not path:
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"active group {group_uid} has no source_path in the projection context",
            group_uid=group_uid,
            field="source_path",
        )
    if path.startswith("/") or "\\" in path:
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"source_path for {group_uid} must be corpus-root-relative POSIX",
            group_uid=group_uid,
            field="source_path",
        )
    return path


def project_registry(
    corpus: GroupCorpus,
    context: AuthorityRevisionContext,
    *,
    producers: Sequence[str] = DEFAULT_PRODUCERS,
    consumers: Sequence[str] = DEFAULT_CONSUMERS,
) -> RegistryProjection:
    """Project an active corpus into a canonical registry generation.

    Reuses :class:`~lib.group_contract.GroupCorpus` primitives
    (``active_uids``, ``resolve_group``, ``resolve_members``,
    ``strict_wider_ancestors``) and :func:`~lib.group_contract.semantic_hash`.
    Drafts and unsigned candidates never appear because only ``active_uids``
    are projected.
    """

    if corpus is None or not isinstance(corpus, GroupCorpus):
        _raise(
            GroupErrorCode.GROUP_CORPUS_UNAVAILABLE,
            "no active group corpus is available for projection",
        )
    context = _require_context(context)
    producers = _require_str_tuple(producers, "producers")
    consumers = _require_str_tuple(consumers, "consumers")

    rows: list[dict[str, Any]] = []
    for group_uid in corpus.active_uids:
        semantic = corpus.resolve_group(group_uid)
        source_path = _resolve_source_path(context, group_uid)
        rows.append(
            {
                "group_uid": group_uid,
                "slug": semantic["slug"],
                "title": semantic["title"],
                "status": semantic["status"],
                "version": semantic["version"],
                "owner_uid": semantic["owner"],
                "direct_member_uids": sorted(semantic["members"]),
                "direct_included_group_uids": sorted(semantic["includes_groups"]),
                "effective_member_uids": sorted(corpus.resolve_members(group_uid)),
                "wider_group_uids": sorted(
                    corpus.strict_wider_ancestors(group_uid)
                ),
                "source_authority_uid": context.source_authority_uid,
                "source_revision": context.source_revision,
                "source_path": source_path,
                "source_hash": semantic_hash(semantic),
                "principal_directory_revision": context.principal_directory_revision,
            }
        )

    jsonl_bytes = _encode_jsonl(rows)
    wrapper = RegistryWrapper(
        jsonl_sha256=hashlib.sha256(jsonl_bytes).hexdigest(),
        row_count=len(rows),
        canonicalization_version=CANONICALIZATION_VERSION,
        source_authority_uid=context.source_authority_uid,
        source_revision=context.source_revision,
        principal_directory_revision=context.principal_directory_revision,
        producers=producers,
        consumers=consumers,
    )
    frozen_rows = tuple(
        _copy_row(row) for row in sorted(rows, key=lambda row: row["group_uid"])
    )
    return RegistryProjection(
        jsonl_bytes=jsonl_bytes,
        rows=frozen_rows,
        wrapper=wrapper,
        source_authority_uid=context.source_authority_uid,
        source_revision=context.source_revision,
        principal_directory_revision=context.principal_directory_revision,
    )


def _validate_row_shape(obj: object, line_number: int) -> dict[str, Any]:
    if not isinstance(obj, dict):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"registry JSONL line {line_number} is not a JSON object",
        )
    if list(obj.keys()) != list(REGISTRY_ROW_KEYS):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"registry JSONL line {line_number} keys are not the locked row order",
        )
    for key in _ROW_STRING_KEYS:
        if not isinstance(obj[key], str):
            _raise(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                f"registry JSONL line {line_number} field {key!r} must be a string",
            )
    version = obj["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"registry JSONL line {line_number} field 'version' must be an integer",
        )
    for key in _ROW_LIST_KEYS:
        value = obj[key]
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            _raise(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                f"registry JSONL line {line_number} field {key!r} must be a string array",
            )
        if list(value) != sorted(value):
            _raise(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                f"registry JSONL line {line_number} field {key!r} is not lexicographically sorted",
            )
        if len(set(value)) != len(value):
            _raise(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                f"registry JSONL line {line_number} field {key!r} contains duplicates",
            )
    return {key: obj[key] for key in REGISTRY_ROW_KEYS}


def parse_registry_jsonl(jsonl_bytes: object) -> list[dict[str, Any]]:
    """Parse and structurally verify canonical registry JSONL.

    Returns the rows in file order.  Structural violations (bad UTF-8, missing
    trailing LF, blank lines, wrong key order, bad types, unsorted UID lists,
    duplicate rows, or rows not sorted by group UID) refuse with
    ``GROUP_RESOLUTION_UNAVAILABLE``; a missing byte string refuses with
    ``GROUP_CORPUS_UNAVAILABLE``.
    """

    if jsonl_bytes is None or not isinstance(jsonl_bytes, (bytes, bytearray)):
        _raise(
            GroupErrorCode.GROUP_CORPUS_UNAVAILABLE,
            "registry JSONL bytes are unavailable",
        )
    try:
        text = bytes(jsonl_bytes).decode("utf-8")
    except UnicodeDecodeError as error:
        raise GroupContractError(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            "registry JSONL is not valid UTF-8",
        ) from error

    if text == "":
        return []
    if not text.endswith("\n"):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            "registry JSONL must terminate every row with one LF",
        )

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text[:-1].split("\n"), start=1):
        if line == "":
            _raise(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                f"registry JSONL line {line_number} is blank",
            )
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as error:
            raise GroupContractError(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                f"registry JSONL line {line_number} is not valid JSON",
            ) from error
        rows.append(_validate_row_shape(obj, line_number))

    uids = [row["group_uid"] for row in rows]
    if uids != sorted(uids):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            "registry JSONL rows are not sorted by group UID",
        )
    if len(set(uids)) != len(uids):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            "registry JSONL contains duplicate group UIDs",
        )
    return rows


def build_parity_database(
    projection: RegistryProjection,
    connection: sqlite3.Connection,
) -> None:
    """Project the registry JSONL into a fresh SQLite acceleration table.

    The table is dropped and rebuilt so no stale rows survive a re-projection.
    SQLite is derived from the JSONL truth; it is never a writable authority.
    """

    if projection is None or not isinstance(projection, RegistryProjection):
        _raise(
            GroupErrorCode.GROUP_CORPUS_UNAVAILABLE,
            "registry projection is unavailable for SQLite parity",
        )
    rows = parse_registry_jsonl(projection.jsonl_bytes)
    cursor = connection.cursor()
    cursor.execute(f"DROP TABLE IF EXISTS {PARITY_TABLE}")
    cursor.execute(
        f"""
        CREATE TABLE {PARITY_TABLE} (
            group_uid TEXT PRIMARY KEY,
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            version INTEGER NOT NULL,
            owner_uid TEXT NOT NULL,
            direct_member_uids TEXT NOT NULL,
            direct_included_group_uids TEXT NOT NULL,
            effective_member_uids TEXT NOT NULL,
            wider_group_uids TEXT NOT NULL,
            source_authority_uid TEXT NOT NULL,
            source_revision TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            principal_directory_revision TEXT NOT NULL
        )
        """
    )
    cursor.executemany(
        f"INSERT INTO {PARITY_TABLE} VALUES ("
        + ",".join("?" for _ in REGISTRY_ROW_KEYS)
        + ")",
        [
            (
                row["group_uid"],
                row["slug"],
                row["title"],
                row["status"],
                row["version"],
                row["owner_uid"],
                _encode_list(row["direct_member_uids"]),
                _encode_list(row["direct_included_group_uids"]),
                _encode_list(row["effective_member_uids"]),
                _encode_list(row["wider_group_uids"]),
                row["source_authority_uid"],
                row["source_revision"],
                row["source_path"],
                row["source_hash"],
                row["principal_directory_revision"],
            )
            for row in rows
        ],
    )
    connection.commit()


def _encode_list(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _decode_list(raw: object, group_uid: str, column: str) -> list[str]:
    if not isinstance(raw, str):
        _raise(
            GroupErrorCode.PROJECTION_MISMATCH,
            f"SQLite row {group_uid} column {column!r} is not stored text",
            group_uid=group_uid,
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GroupContractError(
            GroupErrorCode.PROJECTION_MISMATCH,
            f"SQLite row {group_uid} column {column!r} is not valid JSON",
            group_uid=group_uid,
        ) from error
    if not isinstance(parsed, list) or any(
        not isinstance(item, str) for item in parsed
    ):
        _raise(
            GroupErrorCode.PROJECTION_MISMATCH,
            f"SQLite row {group_uid} column {column!r} is not a string array",
            group_uid=group_uid,
        )
    return parsed


def check_sqlite_parity(
    projection: RegistryProjection,
    connection: sqlite3.Connection,
) -> None:
    """Reconstruct every logical field from SQLite and prove full parity.

    Every one of the fifteen listed logical fields is reconstructed from the
    acceleration table and compared field-for-field against the parsed JSONL,
    plus row count, the exact UID set, row ordering, and a byte-for-byte
    re-encode of the reconstructed rows.  Any disagreement, including a mutated
    or truncated SQLite database, refuses with ``PROJECTION_MISMATCH``.
    """

    if projection is None or not isinstance(projection, RegistryProjection):
        _raise(
            GroupErrorCode.GROUP_CORPUS_UNAVAILABLE,
            "registry projection is unavailable for SQLite parity",
        )
    expected_rows = parse_registry_jsonl(projection.jsonl_bytes)
    expected_by_uid = {row["group_uid"]: row for row in expected_rows}

    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT "
            + ",".join(REGISTRY_ROW_KEYS)
            + f" FROM {PARITY_TABLE} ORDER BY group_uid"
        )
        sqlite_rows = cursor.fetchall()
    except sqlite3.Error as error:
        raise GroupContractError(
            GroupErrorCode.PROJECTION_MISMATCH,
            f"SQLite acceleration table is unreadable: {error}",
        ) from error

    reconstructed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in sqlite_rows:
        record = dict(zip(REGISTRY_ROW_KEYS, raw))
        group_uid = record["group_uid"]
        if not isinstance(group_uid, str):
            _raise(
                GroupErrorCode.PROJECTION_MISMATCH,
                "SQLite row has a non-string group_uid",
            )
        if group_uid in seen:
            _raise(
                GroupErrorCode.PROJECTION_MISMATCH,
                f"SQLite acceleration repeats group {group_uid}",
                group_uid=group_uid,
            )
        seen.add(group_uid)
        row: dict[str, Any] = {}
        for key in REGISTRY_ROW_KEYS:
            if key in _ROW_LIST_KEYS:
                row[key] = _decode_list(record[key], group_uid, key)
            else:
                row[key] = record[key]
        reconstructed.append(row)

    if len(reconstructed) != len(expected_rows):
        _raise(
            GroupErrorCode.PROJECTION_MISMATCH,
            "SQLite row count disagrees with registry JSONL",
        )
    reconstructed_by_uid = {row["group_uid"]: row for row in reconstructed}
    if set(reconstructed_by_uid) != set(expected_by_uid):
        _raise(
            GroupErrorCode.PROJECTION_MISMATCH,
            "SQLite group UID set disagrees with registry JSONL",
        )

    for group_uid, expected in expected_by_uid.items():
        actual = reconstructed_by_uid[group_uid]
        for key in REGISTRY_ROW_KEYS:
            if actual[key] != expected[key]:
                _raise(
                    GroupErrorCode.PROJECTION_MISMATCH,
                    f"SQLite row {group_uid} field {key!r} disagrees with registry JSONL",
                    group_uid=group_uid,
                    field=key,
                )

    if [row["group_uid"] for row in reconstructed] != [
        row["group_uid"] for row in expected_rows
    ]:
        _raise(
            GroupErrorCode.PROJECTION_MISMATCH,
            "SQLite acceleration is not ordered by group UID",
        )
    if _encode_jsonl(reconstructed) != projection.jsonl_bytes:
        _raise(
            GroupErrorCode.PROJECTION_MISMATCH,
            "SQLite reconstruction does not reproduce the exact registry JSONL bytes",
        )


class GroupResolver:
    """Read-only resolver over verified canonical registry JSONL.

    Constructed from the JSONL bytes (the authority the resolver reads
    directly), not from SQLite.  All four operations return
    :class:`Result`; refusals carry a typed
    :class:`~lib.group_contract.GroupContractError` and are never turned into
    empty membership or a bare ``False``.
    """

    __slots__ = ("_rows_by_uid", "_revision")

    def __init__(
        self,
        rows_by_uid: Mapping[str, Mapping[str, Any]],
        revision: str | None,
    ) -> None:
        self._rows_by_uid = dict(rows_by_uid)
        self._revision = revision

    @classmethod
    def from_jsonl(
        cls,
        jsonl_bytes: object,
        *,
        wrapper: RegistryWrapper | None = None,
        expected_revision: str | None = None,
    ) -> "GroupResolver":
        if jsonl_bytes is None or not isinstance(jsonl_bytes, (bytes, bytearray)):
            _raise(
                GroupErrorCode.GROUP_CORPUS_UNAVAILABLE,
                "registry JSONL bytes are unavailable for resolution",
            )
        rows = parse_registry_jsonl(jsonl_bytes)

        if wrapper is not None:
            digest = hashlib.sha256(bytes(jsonl_bytes)).hexdigest()
            if digest != wrapper.jsonl_sha256:
                _raise(
                    GroupErrorCode.PROJECTION_MISMATCH,
                    "registry JSONL digest disagrees with its wrapper",
                )
            if len(rows) != wrapper.row_count:
                _raise(
                    GroupErrorCode.PROJECTION_MISMATCH,
                    "registry row count disagrees with its wrapper",
                )

        revisions = {row["source_revision"] for row in rows}
        if len(revisions) > 1:
            _raise(
                GroupErrorCode.PROJECTION_MISMATCH,
                "registry rows carry inconsistent source_revision values",
            )
        if revisions:
            revision = next(iter(revisions))
        elif wrapper is not None:
            revision = wrapper.source_revision
        else:
            revision = expected_revision

        if wrapper is not None and revisions and wrapper.source_revision != revision:
            _raise(
                GroupErrorCode.PROJECTION_MISMATCH,
                "wrapper source_revision disagrees with registry rows",
            )
        if expected_revision is not None and revision != expected_revision:
            _raise(
                GroupErrorCode.GROUP_CORPUS_STALE,
                f"registry revision {revision!r} does not match pinned "
                f"{expected_revision!r}",
            )

        return cls({row["group_uid"]: row for row in rows}, revision)

    @classmethod
    def from_projection(
        cls,
        projection: RegistryProjection,
        *,
        expected_revision: str | None = None,
    ) -> "GroupResolver":
        if projection is None or not isinstance(projection, RegistryProjection):
            _raise(
                GroupErrorCode.GROUP_CORPUS_UNAVAILABLE,
                "registry projection is unavailable for resolution",
            )
        return cls.from_jsonl(
            projection.jsonl_bytes,
            wrapper=projection.wrapper,
            expected_revision=expected_revision,
        )

    @property
    def revision(self) -> str | None:
        return self._revision

    @property
    def active_uids(self) -> tuple[str, ...]:
        return tuple(sorted(self._rows_by_uid))

    def _row(self, group_uid: object) -> Mapping[str, Any] | None:
        if not isinstance(group_uid, str):
            return None
        return self._rows_by_uid.get(group_uid)

    def _not_found(self, group_uid: object) -> GroupContractError:
        reference = group_uid if isinstance(group_uid, str) else None
        return GroupContractError(
            GroupErrorCode.GROUP_NOT_FOUND,
            f"group {group_uid!r} is not an active resolver-visible group",
            reference_uid=reference,
        )

    def resolve_group(self, group_uid: object) -> Result[dict[str, Any]]:
        row = self._row(group_uid)
        if row is None:
            return Result.failure(self._not_found(group_uid))
        return Result.success(_copy_row(row))

    def resolve_members(self, group_uid: object) -> Result[tuple[str, ...]]:
        row = self._row(group_uid)
        if row is None:
            return Result.failure(self._not_found(group_uid))
        return Result.success(tuple(row["effective_member_uids"]))

    def is_equal_or_wider(
        self,
        candidate_wider_uid: object,
        candidate_narrower_uid: object,
    ) -> Result[bool]:
        narrower = self._row(candidate_narrower_uid)
        if narrower is None:
            return Result.failure(self._not_found(candidate_narrower_uid))
        wider = self._row(candidate_wider_uid)
        if wider is None:
            return Result.failure(self._not_found(candidate_wider_uid))
        outcome = (
            candidate_wider_uid == candidate_narrower_uid
            or candidate_wider_uid in narrower["wider_group_uids"]
        )
        return Result.success(outcome)

    def can_reference(
        self,
        from_audience_uid: object,
        to_audience_uid: object,
    ) -> Result[bool]:
        # can_reference(A, B) is true exactly when B == A or B is declared
        # wider than A, i.e. is_equal_or_wider(B, A).
        return self.is_equal_or_wider(to_audience_uid, from_audience_uid)


__all__ = [
    "AuthorityRevisionContext",
    "CANONICALIZATION_VERSION",
    "DEFAULT_CONSUMERS",
    "DEFAULT_PRODUCERS",
    "GroupResolver",
    "PARITY_TABLE",
    "REGISTRY_ROW_KEYS",
    "RegistryProjection",
    "RegistryWrapper",
    "Result",
    "WRAPPER_SCHEMA_ID",
    "build_parity_database",
    "check_sqlite_parity",
    "parse_registry_jsonl",
    "project_registry",
]
