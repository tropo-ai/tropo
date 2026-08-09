#!/usr/bin/env python3
"""One-shot draft->active group finalizer with journaled recovery (B4a).

This tool implements the ``finalize-group`` operation from the locked dev-spec
``vault/files/0bfa771d.md`` (see ``## Finalization and recovery`` and
``## Group contract``).  It *seals authored source but does not publish
policy*: it transitions exactly one ``draft`` group to ``active`` and derives a
complete, immutable **candidate** corpus generation plus candidate registry
projection.  The candidate is deliberately **not resolver-visible** -- it lives
under machine-local ``.tropo-studio/group-candidate/`` and becomes visible only
after a later signed ``group-authority install`` (out of scope for this slice).

The module is importable as a library (the testable core is
:func:`finalize_group` / :func:`recover_candidate`) and runnable as a thin CLI.

It composes -- and does not reimplement -- the locked pure primitives:

* :mod:`lib.group_contract`: ``canonical_semantic_object`` / ``_bytes``,
  ``semantic_hash``, ``validate_group``, ``assert_group_transition`` (the
  transition-once rule), ``build_group_corpus`` (draft verification, principal
  directory, slug uniqueness, and the complete inclusion graph), plus the closed
  ``GroupErrorCode`` / ``GroupContractError`` refusal vocabulary.
* :mod:`lib.group_registry`: ``project_registry`` (candidate projection),
  ``RegistryWrapper`` / ``RegistryProjection`` (the wrapper binding), and the
  SQLite parity pair ``build_parity_database`` / ``check_sqlite_parity``.

Durability model (dev-spec locked choice 7): observable atomicity is a journaled
multi-surface transaction, not a false claim that POSIX renames several files
plus a database as one syscall.  Under one exclusive transaction lock, the
finalizer:

  1. recovers or refuses any prior incomplete candidate transaction;
  2. verifies the draft, principal directory, slug uniqueness, and graph;
  3. computes the semantic hash and stages the active source;
  4. derives the immutable candidate corpus generation + candidate projection;
  5. fsyncs verified old backups and all new staged bytes;
  6. fsyncs a PREPARED journal row carrying every old/new digest;
  7. commits every destination, verifies them, marks COMMITTED, then returns.

Every writer uses a same-directory exclusive temporary, an fsync of the file, an
atomic ``os.replace``, and an fsync of the parent directory.  The journal is a
hash-chained PREPARED->COMMITTED log.  Recovery CAS-checks every destination
against the recorded old/new digests, then rolls forward from verified staged
bytes or restores verified backups; it never guesses.  Unrecoverable state
returns a typed ``PROJECTION_MISMATCH`` / ``RECOVERY_REQUIRED`` /
``GROUP_CORPUS_STALE`` refusal with authored sources left intact.

No absolute paths and no network access: only the Python standard library and
the two sibling ``lib`` modules are imported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Sequence

import fcntl

# The tool lives in ``vault/tools`` and imports the sibling ``lib`` package.
# ``os.path.dirname(os.path.abspath(__file__))`` is a computed directory, not a
# hard-coded absolute path literal, and mirrors the sibling test harness.
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from lib.group_contract import (  # noqa: E402
    GroupContractError,
    GroupErrorCode,
    SEMANTIC_KEYS,
    assert_group_transition,
    build_group_corpus,
    canonical_semantic_bytes,
    canonical_semantic_object,
    semantic_hash,
)
from lib.group_registry import (  # noqa: E402
    AuthorityRevisionContext,
    RegistryProjection,
    RegistryWrapper,
    build_parity_database,
    check_sqlite_parity,
    parse_registry_jsonl,
    project_registry,
)


# --------------------------------------------------------------------------- #
# Layout constants (all corpus-root-relative POSIX; never resolver-visible).   #
# --------------------------------------------------------------------------- #

CANDIDATE_DIR = ".tropo-studio/group-candidate"
GENERATION_DIR = CANDIDATE_DIR + "/generation"
STAGING_DIR = CANDIDATE_DIR + "/staging"
BACKUPS_DIR = CANDIDATE_DIR + "/backups"
SCRATCH_DIR = CANDIDATE_DIR + "/scratch"
JOURNAL_RELATIVE = CANDIDATE_DIR + "/journal.jsonl"
LOCK_RELATIVE = CANDIDATE_DIR + "/finalize.lock"

GEN_GROUPS_RELATIVE = GENERATION_DIR + "/groups.jsonl"
GEN_REGISTRY_RELATIVE = GENERATION_DIR + "/registry.jsonl"
GEN_SQLITE_RELATIVE = GENERATION_DIR + "/registry.sqlite"
GEN_WRAPPER_RELATIVE = GENERATION_DIR + "/registry-wrapper.json"
GEN_INDEX_RELATIVE = GENERATION_DIR + "/candidate.json"

# The single resolver-visible registry surface.  The finalizer NEVER writes it;
# only a later signed ``group-authority install`` publishes here.
PUBLISHED_REGISTRY_RELATIVE = "vault/00-group-registry.jsonl"

DEFAULT_SOURCE_DIR = "groups"
CANDIDATE_SCHEMA_ID = "tropo.group-candidate/v1"
JOURNAL_GENESIS = "tropo.group-finalize.journal.v1:genesis"

# Ordered destination names; the commit swap order is exactly this order.
DEST_SOURCE = "source"
DEST_GENERATION = "generation"
DEST_JSONL = "jsonl"
DEST_SQLITE = "sqlite"
DEST_WRAPPER = "wrapper"
DEST_INDEX = "index"
DEST_ORDER = (
    DEST_SOURCE,
    DEST_GENERATION,
    DEST_JSONL,
    DEST_SQLITE,
    DEST_WRAPPER,
    DEST_INDEX,
)

# CAS classifications of a destination against its recorded old/new digests.
_APPLIED = "applied"
_PENDING = "pending"
_UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Exceptions.                                                                  #
# --------------------------------------------------------------------------- #


class SimulatedProcessLoss(BaseException):
    """Raised at a named failpoint to model abrupt process loss in tests.

    It subclasses :class:`BaseException` (not :class:`Exception`) so that no
    ordinary ``except Exception`` handler inside the transaction can swallow it
    and thereby hide a partial on-disk state.  Production callers never pass a
    ``failpoint`` and so never see it.
    """

    def __init__(self, failpoint: str) -> None:
        super().__init__(f"simulated process loss at {failpoint!r}")
        self.failpoint = failpoint


class FinalizeLockTimeout(TimeoutError):
    """Another writer held the exclusive finalize lock past the safety bound."""


def _raise(
    code: GroupErrorCode,
    message: str,
    *,
    group_uid: Optional[str] = None,
    field_name: Optional[str] = None,
    reference_uid: Optional[str] = None,
) -> "None":
    raise GroupContractError(
        code,
        message,
        group_uid=group_uid,
        field=field_name,
        reference_uid=reference_uid,
    )


def _trip(failpoint: Optional[str], name: str) -> None:
    """Raise :class:`SimulatedProcessLoss` iff ``failpoint`` names ``name``."""

    if failpoint is not None and failpoint == name:
        raise SimulatedProcessLoss(name)


# --------------------------------------------------------------------------- #
# Result / recovery value objects.                                            #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FinalizeResult:
    """Outcome of a completed (or idempotently re-observed) finalization."""

    status: str  # "committed" | "recovered" | "idempotent"
    group_uid: str
    candidate_revision: str
    corpus_sha256: str
    registry_jsonl_sha256: str
    registry_wrapper_sha256: str
    principal_directory_revision: str
    source_authority_uid: str
    finalized_group_uids: tuple[str, ...]
    generation_dir: str = GENERATION_DIR
    resolver_visible: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "group_uid": self.group_uid,
            "candidate_revision": self.candidate_revision,
            "corpus_sha256": self.corpus_sha256,
            "registry_jsonl_sha256": self.registry_jsonl_sha256,
            "registry_wrapper_sha256": self.registry_wrapper_sha256,
            "principal_directory_revision": self.principal_directory_revision,
            "source_authority_uid": self.source_authority_uid,
            "finalized_group_uids": list(self.finalized_group_uids),
            "generation_dir": self.generation_dir,
            "resolver_visible": self.resolver_visible,
        }


@dataclass(frozen=True)
class RecoveryOutcome:
    """Outcome of :func:`recover_candidate` for a non-refusing state.

    ``state`` is one of ``"none"`` (no journaled transaction), ``"completed"``
    (an incomplete transaction was rolled forward exactly once), or
    ``"settled"`` (an already-COMMITTED transaction was verified and cleaned).
    Refusals are raised as :class:`GroupContractError`, never returned here.
    """

    state: str
    group_uid: Optional[str] = None
    candidate_revision: Optional[str] = None
    txn_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "group_uid": self.group_uid,
            "candidate_revision": self.candidate_revision,
            "txn_id": self.txn_id,
        }


@dataclass(frozen=True)
class _Paths:
    """Resolved corpus-root-relative paths for one corpus root."""

    root: Path
    source_dir: str

    @property
    def journal(self) -> Path:
        return self.root / JOURNAL_RELATIVE

    @property
    def lock(self) -> Path:
        return self.root / LOCK_RELATIVE

    @property
    def staging(self) -> Path:
        return self.root / STAGING_DIR

    @property
    def backups(self) -> Path:
        return self.root / BACKUPS_DIR

    @property
    def scratch(self) -> Path:
        return self.root / SCRATCH_DIR

    @property
    def generation(self) -> Path:
        return self.root / GENERATION_DIR

    def source_path(self, group_uid: str) -> Path:
        return self.root / self.source_rel(group_uid)

    def source_rel(self, group_uid: str) -> str:
        return f"{self.source_dir}/{group_uid}.json"


def _paths(corpus_root: Any, source_dir: str) -> _Paths:
    return _Paths(root=Path(corpus_root), source_dir=source_dir)


# --------------------------------------------------------------------------- #
# Low-level byte / digest / fsync helpers.                                    #
# --------------------------------------------------------------------------- #


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_file(path: Path) -> Optional[str]:
    try:
        return _digest_bytes(path.read_bytes())
    except FileNotFoundError:
        return None


def _canonical_json_bytes(obj: Mapping[str, Any]) -> bytes:
    """Compact UTF-8 JSON plus exactly one LF, preserving insertion order."""

    return (
        json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        .encode("utf-8")
        + b"\n"
    )


def _read_json_file(path: Path) -> Optional[Any]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    return json.loads(raw.decode("utf-8"))


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        # Some filesystems reject directory fsync; the rename is still durable
        # enough for the transaction's recovery guarantees on real hardware.
        pass
    finally:
        os.close(fd)


def _atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    failpoint: Optional[str] = None,
    before: Optional[str] = None,
    after: Optional[str] = None,
) -> None:
    """Same-directory temp -> fsync file -> atomic replace -> fsync parent.

    ``before`` fires before anything is written (destination untouched);
    ``after`` fires only once the destination is durably swapped.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    if before is not None:
        _trip(failpoint, before)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _fsync_dir(path.parent)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    if after is not None:
        _trip(failpoint, after)


def _write_and_fsync(path: Path, data: bytes) -> None:
    """Directly write an internal (staging/backup) file and fsync it + parent."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_dir(path.parent)


def _clear_dir(path: Path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_file() or child.is_symlink():
            try:
                child.unlink()
            except OSError:
                pass
    _fsync_dir(path)


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_dir(path.parent)


# --------------------------------------------------------------------------- #
# Exclusive transaction lock (process-scoped flock, clone-local).             #
# --------------------------------------------------------------------------- #


@contextmanager
def _finalize_lock(paths: _Paths, *, timeout_seconds: float) -> Iterator[Path]:
    """Hold the exclusive finalize transaction lock through COMMITTED cleanup.

    Mirrors ``lib.index_surfaces.index_write_lock``: process-scoped ``flock``,
    machine-local, and ignored coordination state.  ``_locked`` helpers never
    reacquire (dev-spec locked choice 8).
    """

    paths.lock.parent.mkdir(parents=True, exist_ok=True)
    handle = paths.lock.open("a+", encoding="utf-8")
    deadline = time.monotonic() + timeout_seconds
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise FinalizeLockTimeout(
                        f"timed out after {timeout_seconds:.0f}s waiting for {paths.lock}"
                    )
                time.sleep(0.02)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid: {os.getpid()}\n")
        handle.flush()
        os.fsync(handle.fileno())
        yield paths.lock
    finally:
        if acquired:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


# --------------------------------------------------------------------------- #
# Hash-chained PREPARED -> COMMITTED journal.                                  #
# --------------------------------------------------------------------------- #


def _row_hash(prev_hash: str, row: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in row.items() if key != "row_hash"}
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    return hashlib.sha256((prev_hash + "\n" + canonical).encode("utf-8")).hexdigest()


def _read_journal(paths: _Paths) -> list[dict[str, Any]]:
    try:
        raw = paths.journal.read_bytes()
    except FileNotFoundError:
        return []
    rows: list[dict[str, Any]] = []
    text = raw.decode("utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as error:
            raise GroupContractError(
                GroupErrorCode.RECOVERY_REQUIRED,
                f"finalize journal line {line_number} is not valid JSON",
            ) from error
        if not isinstance(obj, dict):
            _raise(
                GroupErrorCode.RECOVERY_REQUIRED,
                f"finalize journal line {line_number} is not a JSON object",
            )
        rows.append(obj)
    return rows


def _verify_chain(rows: Sequence[Mapping[str, Any]]) -> None:
    prev = JOURNAL_GENESIS
    for index, row in enumerate(rows):
        expected = _row_hash(prev, row)
        if row.get("prev_hash") != prev or row.get("row_hash") != expected:
            _raise(
                GroupErrorCode.RECOVERY_REQUIRED,
                f"finalize journal hash chain broken at row {index}",
            )
        prev = row["row_hash"]


def _append_row(rows: Sequence[Mapping[str, Any]], row: Mapping[str, Any]) -> list[dict[str, Any]]:
    prev = rows[-1]["row_hash"] if rows else JOURNAL_GENESIS
    new_row = dict(row)
    new_row["prev_hash"] = prev
    new_row["row_hash"] = _row_hash(prev, new_row)
    return [dict(existing) for existing in rows] + [new_row]


def _write_journal_atomic(paths: _Paths, rows: Sequence[Mapping[str, Any]]) -> None:
    data = b"".join(
        json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        + b"\n"
        for row in rows
    )
    _atomic_write_bytes(paths.journal, data)


def _last_transaction(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[Optional[Mapping[str, Any]], Optional[Mapping[str, Any]]]:
    """Return ``(prepared, committed_or_None)`` for the most recent txn."""

    if not rows:
        return None, None
    last = rows[-1]
    if last.get("type") == "COMMITTED":
        txn_id = last.get("txn_id")
        for row in reversed(rows[:-1]):
            if row.get("type") == "PREPARED" and row.get("txn_id") == txn_id:
                return row, last
        return None, last
    if last.get("type") == "PREPARED":
        return last, None
    return None, None


# --------------------------------------------------------------------------- #
# Candidate consistency verification (reused by finalize + recovery).         #
# --------------------------------------------------------------------------- #


def _reconstruct_wrapper(wrapper_obj: Mapping[str, Any]) -> RegistryWrapper:
    try:
        return RegistryWrapper(
            jsonl_sha256=wrapper_obj["jsonl_sha256"],
            row_count=wrapper_obj["row_count"],
            canonicalization_version=wrapper_obj["canonicalization_version"],
            source_authority_uid=wrapper_obj["source_authority_uid"],
            source_revision=wrapper_obj["source_revision"],
            principal_directory_revision=wrapper_obj["principal_directory_revision"],
            producers=tuple(wrapper_obj["producers"]),
            consumers=tuple(wrapper_obj["consumers"]),
        )
    except (KeyError, TypeError) as error:
        raise GroupContractError(
            GroupErrorCode.PROJECTION_MISMATCH,
            f"candidate registry wrapper is malformed: {type(error).__name__}",
        ) from error


def _verify_candidate_consistency(paths: _Paths) -> dict[str, Any]:
    """Prove the on-disk candidate generation is internally self-consistent.

    Reuses ``parse_registry_jsonl``, ``RegistryWrapper`` and
    ``check_sqlite_parity`` so a corrupt or partially-written generation is
    caught as ``PROJECTION_MISMATCH`` -- never accepted as truth.  Returns the
    parsed candidate index on success.
    """

    for relative in (
        GEN_GROUPS_RELATIVE,
        GEN_REGISTRY_RELATIVE,
        GEN_SQLITE_RELATIVE,
        GEN_WRAPPER_RELATIVE,
        GEN_INDEX_RELATIVE,
    ):
        if not (paths.root / relative).exists():
            _raise(
                GroupErrorCode.PROJECTION_MISMATCH,
                f"candidate generation is missing {relative}",
            )

    groups_bytes = (paths.root / GEN_GROUPS_RELATIVE).read_bytes()
    registry_bytes = (paths.root / GEN_REGISTRY_RELATIVE).read_bytes()
    wrapper_bytes = (paths.root / GEN_WRAPPER_RELATIVE).read_bytes()

    index = _read_json_file(paths.root / GEN_INDEX_RELATIVE)
    if not isinstance(index, dict):
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "candidate index is not a JSON object")

    corpus_sha = _digest_bytes(groups_bytes)
    if index.get("groups_jsonl_sha256") != corpus_sha:
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "candidate groups.jsonl digest disagrees with index")
    if index.get("corpus_sha256") != corpus_sha:
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "candidate corpus_sha256 disagrees with groups.jsonl")
    if index.get("candidate_revision") != f"sha256:{corpus_sha}":
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "candidate_revision is not sha256:<corpus_sha256>")

    try:
        rows = parse_registry_jsonl(registry_bytes)
    except GroupContractError as error:
        raise GroupContractError(
            GroupErrorCode.PROJECTION_MISMATCH,
            f"candidate registry JSONL is not canonical: {error.code.value}",
        ) from error

    if _digest_bytes(registry_bytes) != index.get("registry_jsonl_sha256"):
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "candidate registry JSONL digest disagrees with index")

    try:
        wrapper_obj = json.loads(wrapper_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise GroupContractError(
            GroupErrorCode.PROJECTION_MISMATCH,
            "candidate registry wrapper is not valid JSON",
        ) from error
    wrapper = _reconstruct_wrapper(wrapper_obj)
    if wrapper.canonical_bytes() != wrapper_bytes:
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "candidate wrapper bytes are not canonical")
    if wrapper.jsonl_sha256 != _digest_bytes(registry_bytes):
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "candidate wrapper jsonl digest disagrees with registry")
    if wrapper.row_count != len(rows):
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "candidate wrapper row count disagrees with registry")
    if wrapper.wrapper_sha256 != index.get("registry_wrapper_sha256"):
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "candidate wrapper digest disagrees with index")

    projection = RegistryProjection(
        jsonl_bytes=registry_bytes,
        rows=tuple(rows),
        wrapper=wrapper,
        source_authority_uid=wrapper.source_authority_uid,
        source_revision=wrapper.source_revision,
        principal_directory_revision=wrapper.principal_directory_revision,
    )
    connection = sqlite3.connect(str(paths.root / GEN_SQLITE_RELATIVE))
    try:
        check_sqlite_parity(projection, connection)
    finally:
        connection.close()
    return index


def _verify_dest_digests(paths: _Paths, plan: Sequence[Mapping[str, Any]]) -> None:
    for dest in plan:
        current = _digest_file(paths.root / dest["path"])
        if current != dest["new"]:
            _raise(
                GroupErrorCode.PROJECTION_MISMATCH,
                f"destination {dest['name']!r} does not match its committed digest",
            )


# --------------------------------------------------------------------------- #
# CAS classification, staged roll-forward, backup roll-back.                   #
# --------------------------------------------------------------------------- #


def _classify(current: Optional[str], old: Optional[str], new: str) -> str:
    if current == new:
        return _APPLIED
    if current == old:
        return _PENDING
    return _UNKNOWN


def _staged_bytes(paths: _Paths, dest: Mapping[str, Any]) -> Optional[bytes]:
    staged = paths.root / dest["staged"]
    try:
        return staged.read_bytes()
    except FileNotFoundError:
        return None


def _staging_ok(paths: _Paths, plan: Sequence[Mapping[str, Any]]) -> bool:
    for dest in plan:
        data = _staged_bytes(paths, dest)
        if data is None or _digest_bytes(data) != dest["new"]:
            return False
    return True


def _apply_staged(
    paths: _Paths,
    dest: Mapping[str, Any],
    *,
    failpoint: Optional[str] = None,
    before: Optional[str] = None,
    after: Optional[str] = None,
) -> None:
    data = _staged_bytes(paths, dest)
    if data is None or _digest_bytes(data) != dest["new"]:
        _raise(
            GroupErrorCode.RECOVERY_REQUIRED,
            f"staged bytes for {dest['name']!r} are missing or do not match the recorded digest",
        )
    _atomic_write_bytes(
        paths.root / dest["path"], data, failpoint=failpoint, before=before, after=after
    )


def _restore_or_remove(paths: _Paths, dest: Mapping[str, Any]) -> None:
    target = paths.root / dest["path"]
    if dest["old"] is None:
        _remove(target)
        return
    backup_rel = dest.get("backup")
    if not backup_rel:
        return
    backup = paths.root / backup_rel
    try:
        data = backup.read_bytes()
    except FileNotFoundError:
        return
    if _digest_bytes(data) == dest["old"]:
        _atomic_write_bytes(target, data)


def _rollback(paths: _Paths, plan: Sequence[Mapping[str, Any]], states: Mapping[str, str]) -> None:
    """Restore already-applied destinations to their verified old bytes.

    UNKNOWN destinations are left untouched: a mutated authored source stays as
    the user left it, and a corrupt candidate file stays corrupt so a second
    resume re-refuses deterministically.  PENDING destinations are already old.
    """

    for dest in plan:
        if states[dest["name"]] == _APPLIED:
            _restore_or_remove(paths, dest)


# --------------------------------------------------------------------------- #
# Recovery (assumes the exclusive lock is held).                              #
# --------------------------------------------------------------------------- #


def _settle(paths: _Paths, prepared: Mapping[str, Any]) -> None:
    _verify_candidate_consistency(paths)
    _verify_dest_digests(paths, prepared["plan"])
    _clear_dir(paths.staging)
    _clear_dir(paths.backups)


def _rollforward_finish(paths: _Paths, prepared: Mapping[str, Any]) -> None:
    _verify_candidate_consistency(paths)
    _verify_dest_digests(paths, prepared["plan"])
    rows = _read_journal(paths)
    committed = {
        "type": "COMMITTED",
        "txn_id": prepared["txn_id"],
        "group_uid": prepared["group_uid"],
        "candidate_revision": prepared["candidate_revision"],
    }
    _write_journal_atomic(paths, _append_row(rows, committed))
    _clear_dir(paths.staging)
    _clear_dir(paths.backups)


def _recover_locked(paths: _Paths) -> RecoveryOutcome:
    rows = _read_journal(paths)
    if not rows:
        # No journaled transaction: clear any orphaned pre-durability staging.
        _clear_dir(paths.staging)
        _clear_dir(paths.backups)
        return RecoveryOutcome("none")

    _verify_chain(rows)
    prepared, committed = _last_transaction(rows)
    if prepared is None:
        _raise(GroupErrorCode.RECOVERY_REQUIRED, "finalize journal has no PREPARED transaction")

    plan = prepared["plan"]
    if committed is not None:
        _settle(paths, prepared)
        return RecoveryOutcome(
            "settled",
            group_uid=prepared["group_uid"],
            candidate_revision=prepared["candidate_revision"],
            txn_id=prepared["txn_id"],
        )

    states = {
        dest["name"]: _classify(_digest_file(paths.root / dest["path"]), dest["old"], dest["new"])
        for dest in plan
    }
    unknown = [dest for dest in plan if states[dest["name"]] == _UNKNOWN]
    if unknown:
        source_unknown = any(dest.get("is_source") for dest in unknown)
        _rollback(paths, plan, states)
        if source_unknown:
            _raise(
                GroupErrorCode.GROUP_CORPUS_STALE,
                "authored source changed under a prepared finalize (stale migration)",
                group_uid=prepared.get("group_uid"),
            )
        _raise(
            GroupErrorCode.PROJECTION_MISMATCH,
            "a candidate projection destination is corrupt; recovery cannot roll forward",
            group_uid=prepared.get("group_uid"),
        )

    if not _staging_ok(paths, plan):
        _rollback(paths, plan, states)
        _raise(
            GroupErrorCode.RECOVERY_REQUIRED,
            "staged bytes are missing or corrupt; rolled back to pre-transaction state",
            group_uid=prepared.get("group_uid"),
        )

    for dest in plan:
        if states[dest["name"]] == _PENDING:
            _apply_staged(paths, dest)
    _rollforward_finish(paths, prepared)
    return RecoveryOutcome(
        "completed",
        group_uid=prepared["group_uid"],
        candidate_revision=prepared["candidate_revision"],
        txn_id=prepared["txn_id"],
    )


def recover_candidate(
    corpus_root: Any,
    *,
    source_dir: str = DEFAULT_SOURCE_DIR,
    lock_timeout: float = 60.0,
) -> RecoveryOutcome:
    """Recover or refuse any prior incomplete candidate transaction.

    Acquires the exclusive transaction lock and drives the recovery state
    machine.  Completes an incomplete-but-durable transaction exactly once,
    verifies+cleans an already-COMMITTED one, or refuses with a typed error
    (``PROJECTION_MISMATCH`` / ``GROUP_CORPUS_STALE`` / ``RECOVERY_REQUIRED``)
    while leaving authored sources intact.
    """

    paths = _paths(corpus_root, source_dir)
    with _finalize_lock(paths, timeout_seconds=lock_timeout):
        return _recover_locked(paths)


# --------------------------------------------------------------------------- #
# Source loading + candidate derivation.                                      #
# --------------------------------------------------------------------------- #


def _load_all_sources(paths: _Paths) -> dict[str, dict[str, Any]]:
    source_root = paths.root / paths.source_dir
    groups: dict[str, dict[str, Any]] = {}
    if not source_root.is_dir():
        return groups
    for entry in sorted(source_root.glob("*.json")):
        obj = _read_json_file(entry)
        if not isinstance(obj, dict):
            _raise(
                GroupErrorCode.GROUP_SCHEMA_INVALID,
                f"group source {entry.name} is not a JSON object",
            )
        uid = obj.get("uid")
        if not isinstance(uid, str):
            _raise(
                GroupErrorCode.GROUP_SCHEMA_INVALID,
                f"group source {entry.name} has no string uid",
            )
        if uid in groups:
            _raise(
                GroupErrorCode.GROUP_SCHEMA_INVALID,
                f"group uid {uid} appears in more than one source file",
                group_uid=uid,
            )
        groups[uid] = obj
    return groups


def _active_source_object(active_semantic: Mapping[str, Any], digest: str) -> dict[str, Any]:
    """Canonical active source: the 10 semantic keys plus ``semantic_hash``."""

    ordered = {key: active_semantic[key] for key in SEMANTIC_KEYS}
    ordered["semantic_hash"] = digest
    return ordered


@dataclass
class _CandidateBytes:
    group_uid: str
    corpus_sha256: str
    corpus_revision: str
    active_uids: tuple[str, ...]
    active_source: bytes
    groups_jsonl: bytes
    registry_jsonl: bytes
    registry_wrapper: bytes
    registry_sqlite: bytes
    candidate_index: bytes
    registry_jsonl_sha256: str = ""
    registry_wrapper_sha256: str = ""


def _derive_candidate(
    paths: _Paths,
    draft_uid: str,
    principals: Mapping[str, Mapping[str, Any]],
    authority_uid: str,
    principal_directory_revision: str,
) -> _CandidateBytes:
    """Verify the draft/corpus and derive every immutable candidate byte string.

    Steps 2-4 of the dev-spec: verify draft + principal directory + slug
    uniqueness + complete graph (``build_group_corpus``), transition once
    (``assert_group_transition``), compute the semantic hash, and project the
    candidate corpus generation + registry projection.
    """

    groups = _load_all_sources(paths)
    if draft_uid not in groups:
        _raise(
            GroupErrorCode.GROUP_NOT_FOUND,
            f"draft group {draft_uid} has no source file under {paths.source_dir}/",
            reference_uid=draft_uid,
        )

    # Verify the *complete* corpus (drafts participate in slug uniqueness and
    # graph checks; they remain resolver-invisible).
    build_group_corpus(groups, principals)

    draft_obj = groups[draft_uid]
    draft_semantic = canonical_semantic_object(draft_obj)
    if draft_semantic["status"] != "draft":
        _raise(
            GroupErrorCode.GROUP_INACTIVE,
            f"group {draft_uid} is not a draft (status={draft_semantic['status']!r})",
            group_uid=draft_uid,
            field_name="status",
        )

    active_semantic = canonical_semantic_object({**draft_semantic, "status": "active"})
    digest = semantic_hash(active_semantic)
    active_source_obj = _active_source_object(active_semantic, digest)

    # Enforce the single lawful lifecycle transition (draft -> active, no other
    # semantic field mutated) against the injected principal directory.
    assert_group_transition(draft_obj, active_source_obj, principals)

    post_groups = dict(groups)
    post_groups[draft_uid] = active_source_obj
    active_corpus = build_group_corpus(post_groups, principals)
    active_uids = active_corpus.active_uids

    groups_jsonl = b"".join(
        canonical_semantic_bytes(active_corpus.resolve_group(uid)) for uid in active_uids
    )
    corpus_sha256 = _digest_bytes(groups_jsonl)
    corpus_revision = f"sha256:{corpus_sha256}"

    context = AuthorityRevisionContext(
        source_authority_uid=authority_uid,
        source_revision=corpus_revision,
        principal_directory_revision=principal_directory_revision,
        source_paths={uid: paths.source_rel(uid) for uid in active_uids},
    )
    projection = project_registry(active_corpus, context)

    registry_jsonl = projection.jsonl_bytes
    registry_wrapper = projection.wrapper.canonical_bytes()
    registry_sqlite = _build_sqlite_bytes(paths, projection)

    candidate_index = _canonical_json_bytes(
        {
            "schema_id": CANDIDATE_SCHEMA_ID,
            "canonicalization_version": projection.wrapper.canonicalization_version,
            "candidate_revision": corpus_revision,
            "corpus_sha256": corpus_sha256,
            "groups_jsonl_sha256": corpus_sha256,
            "registry_jsonl_sha256": projection.jsonl_sha256,
            "registry_wrapper_sha256": projection.wrapper.wrapper_sha256,
            "source_authority_uid": authority_uid,
            "principal_directory_revision": principal_directory_revision,
            "finalized_group_uids": list(active_uids),
            "resolver_visible": False,
        }
    )

    return _CandidateBytes(
        group_uid=draft_uid,
        corpus_sha256=corpus_sha256,
        corpus_revision=corpus_revision,
        active_uids=active_uids,
        active_source=_canonical_json_bytes(active_source_obj),
        groups_jsonl=groups_jsonl,
        registry_jsonl=registry_jsonl,
        registry_wrapper=registry_wrapper,
        registry_sqlite=registry_sqlite,
        candidate_index=candidate_index,
        registry_jsonl_sha256=projection.jsonl_sha256,
        registry_wrapper_sha256=projection.wrapper.wrapper_sha256,
    )


def _build_sqlite_bytes(paths: _Paths, projection: RegistryProjection) -> bytes:
    paths.scratch.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".sqlite-build.", suffix=".db", dir=str(paths.scratch))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        connection = sqlite3.connect(str(tmp_path))
        try:
            build_parity_database(projection, connection)
        finally:
            connection.close()
        return tmp_path.read_bytes()
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Plan construction + the new-transaction commit.                             #
# --------------------------------------------------------------------------- #


def _build_plan(paths: _Paths, candidate: _CandidateBytes) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    new_bytes: dict[str, bytes] = {
        DEST_SOURCE: candidate.active_source,
        DEST_GENERATION: candidate.groups_jsonl,
        DEST_JSONL: candidate.registry_jsonl,
        DEST_SQLITE: candidate.registry_sqlite,
        DEST_WRAPPER: candidate.registry_wrapper,
        DEST_INDEX: candidate.candidate_index,
    }
    dest_paths: dict[str, str] = {
        DEST_SOURCE: paths.source_rel(candidate.group_uid),
        DEST_GENERATION: GEN_GROUPS_RELATIVE,
        DEST_JSONL: GEN_REGISTRY_RELATIVE,
        DEST_SQLITE: GEN_SQLITE_RELATIVE,
        DEST_WRAPPER: GEN_WRAPPER_RELATIVE,
        DEST_INDEX: GEN_INDEX_RELATIVE,
    }
    plan: list[dict[str, Any]] = []
    for name in DEST_ORDER:
        rel = dest_paths[name]
        old_digest = _digest_file(paths.root / rel)
        plan.append(
            {
                "name": name,
                "path": rel,
                "old": old_digest,
                "new": _digest_bytes(new_bytes[name]),
                "staged": f"{STAGING_DIR}/{name}",
                "backup": f"{BACKUPS_DIR}/{name}" if old_digest is not None else None,
                "is_source": name == DEST_SOURCE,
            }
        )
    return plan, new_bytes


def _commit_new_transaction(
    paths: _Paths,
    candidate: _CandidateBytes,
    *,
    failpoint: Optional[str],
) -> None:
    plan, new_bytes = _build_plan(paths, candidate)
    by_name = {dest["name"]: dest for dest in plan}

    # Sanity: the in-memory candidate must be internally consistent before we
    # make anything durable (reuses the same registry-parity verifier).
    _verify_new_candidate(paths, candidate)

    # Fresh staging + backups for this transaction.
    _clear_dir(paths.staging)
    _clear_dir(paths.backups)
    paths.generation.mkdir(parents=True, exist_ok=True)

    # (5a) verified OLD backups.
    _trip(failpoint, "backup_write:before")
    for dest in plan:
        if dest["old"] is not None:
            current = (paths.root / dest["path"]).read_bytes()
            if _digest_bytes(current) != dest["old"]:
                _raise(
                    GroupErrorCode.GROUP_CORPUS_STALE,
                    f"destination {dest['name']!r} changed while preparing the finalize",
                )
            _write_and_fsync(paths.root / dest["backup"], current)
    _fsync_dir(paths.backups)
    _trip(failpoint, "backup_write:after")

    # (5b) all NEW staged bytes.
    _trip(failpoint, "stage_write:before")
    for dest in plan:
        _write_and_fsync(paths.root / dest["staged"], new_bytes[dest["name"]])
    _fsync_dir(paths.staging)
    _trip(failpoint, "stage_write:after")

    # (6) PREPARED journal row carrying every old/new digest.
    _trip(failpoint, "journal_fsync:before")
    txn_id = uuid.uuid4().hex
    rows = _read_journal(paths)
    prepared = {
        "type": "PREPARED",
        "txn_id": txn_id,
        "group_uid": candidate.group_uid,
        "candidate_revision": candidate.corpus_revision,
        "plan": plan,
    }
    _write_journal_atomic(paths, _append_row(rows, prepared))
    _trip(failpoint, "journal_fsync:after")

    # (7) commit swaps in the fixed order, each from verified staged bytes.
    _apply_staged(paths, by_name[DEST_SOURCE], failpoint=failpoint,
                  before="source_swap:before", after="source_swap:after")
    _apply_staged(paths, by_name[DEST_GENERATION], failpoint=failpoint,
                  before="generation_swap:before", after="generation_swap:after")
    _apply_staged(paths, by_name[DEST_JSONL], failpoint=failpoint,
                  before="jsonl_swap:before", after="jsonl_swap:after")
    _apply_staged(paths, by_name[DEST_SQLITE], failpoint=failpoint,
                  before="sqlite_swap:before", after="sqlite_swap:after")
    _apply_staged(paths, by_name[DEST_WRAPPER], failpoint=failpoint,
                  before="wrapper_index:before", after="wrapper_index:mid")
    _apply_staged(paths, by_name[DEST_INDEX], failpoint=failpoint,
                  before=None, after="wrapper_index:after")

    # verify published surfaces, then mark COMMITTED, then clean up.
    _trip(failpoint, "verification:before")
    _verify_candidate_consistency(paths)
    _verify_dest_digests(paths, plan)
    _trip(failpoint, "verification:after")

    _trip(failpoint, "committed_record:before")
    rows = _read_journal(paths)
    committed = {
        "type": "COMMITTED",
        "txn_id": txn_id,
        "group_uid": candidate.group_uid,
        "candidate_revision": candidate.corpus_revision,
    }
    _write_journal_atomic(paths, _append_row(rows, committed))
    _trip(failpoint, "committed_record:after")

    _trip(failpoint, "cleanup:before")
    _clear_dir(paths.staging)
    _clear_dir(paths.backups)
    _clear_dir(paths.scratch)
    _trip(failpoint, "cleanup:after")


def _verify_new_candidate(paths: _Paths, candidate: _CandidateBytes) -> None:
    """Verify the freshly-derived candidate bytes before staging anything."""

    if _digest_bytes(candidate.groups_jsonl) != candidate.corpus_sha256:
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "derived groups.jsonl digest is inconsistent")
    try:
        rows = parse_registry_jsonl(candidate.registry_jsonl)
    except GroupContractError as error:
        raise GroupContractError(
            GroupErrorCode.PROJECTION_MISMATCH,
            f"derived registry JSONL is not canonical: {error.code.value}",
        ) from error
    wrapper_obj = json.loads(candidate.registry_wrapper.decode("utf-8"))
    wrapper = _reconstruct_wrapper(wrapper_obj)
    if wrapper.jsonl_sha256 != candidate.registry_jsonl_sha256 or wrapper.row_count != len(rows):
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "derived wrapper disagrees with derived registry")
    projection = RegistryProjection(
        jsonl_bytes=candidate.registry_jsonl,
        rows=tuple(rows),
        wrapper=wrapper,
        source_authority_uid=wrapper.source_authority_uid,
        source_revision=wrapper.source_revision,
        principal_directory_revision=wrapper.principal_directory_revision,
    )
    paths.scratch.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".sqlite-verify.", suffix=".db", dir=str(paths.scratch))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_bytes(candidate.registry_sqlite)
        connection = sqlite3.connect(str(tmp_path))
        try:
            check_sqlite_parity(projection, connection)
        finally:
            connection.close()
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Result builders + the public finalize entrypoint.                           #
# --------------------------------------------------------------------------- #


def _result_from_index(paths: _Paths, status: str, group_uid: str) -> FinalizeResult:
    index = _verify_candidate_consistency(paths)
    return FinalizeResult(
        status=status,
        group_uid=group_uid,
        candidate_revision=index["candidate_revision"],
        corpus_sha256=index["corpus_sha256"],
        registry_jsonl_sha256=index["registry_jsonl_sha256"],
        registry_wrapper_sha256=index["registry_wrapper_sha256"],
        principal_directory_revision=index["principal_directory_revision"],
        source_authority_uid=index["source_authority_uid"],
        finalized_group_uids=tuple(index["finalized_group_uids"]),
    )


def _finalize_locked(
    paths: _Paths,
    draft_uid: str,
    principals: Mapping[str, Mapping[str, Any]],
    authority_uid: str,
    principal_directory_revision: str,
    *,
    failpoint: Optional[str],
) -> FinalizeResult:
    # (1) recover or refuse any prior incomplete candidate transaction.
    outcome = _recover_locked(paths)
    if outcome.state == "completed" and outcome.group_uid == draft_uid:
        return _result_from_index(paths, "recovered", draft_uid)

    # Idempotent re-observation: the draft is already sealed into the candidate.
    source_obj = _read_json_file(paths.source_path(draft_uid))
    if isinstance(source_obj, dict) and source_obj.get("status") == "active":
        index = _read_json_file(paths.root / GEN_INDEX_RELATIVE)
        if not isinstance(index, dict) or draft_uid not in index.get("finalized_group_uids", []):
            _raise(
                GroupErrorCode.PROJECTION_MISMATCH,
                f"group {draft_uid} source is active but absent from the candidate generation",
                group_uid=draft_uid,
            )
        return _result_from_index(paths, "idempotent", draft_uid)

    # (2-7) derive and commit a brand-new candidate transaction.
    candidate = _derive_candidate(
        paths, draft_uid, principals, authority_uid, principal_directory_revision
    )
    _commit_new_transaction(paths, candidate, failpoint=failpoint)
    return _result_from_index(paths, "committed", draft_uid)


def finalize_group(
    corpus_root: Any,
    draft_uid: str,
    *,
    principals: Mapping[str, Mapping[str, Any]],
    authority_uid: str,
    principal_directory_revision: str,
    source_dir: str = DEFAULT_SOURCE_DIR,
    failpoint: Optional[str] = None,
    lock_timeout: float = 60.0,
) -> FinalizeResult:
    """Finalize one draft group into a sealed, resolver-invisible candidate.

    See the module docstring for the full ordered-lock contract.  ``failpoint``
    is a test-only hook that raises :class:`SimulatedProcessLoss` at a named
    boundary; production callers leave it ``None``.  Returns a
    :class:`FinalizeResult`; refuses with a typed
    :class:`~lib.group_contract.GroupContractError`.
    """

    paths = _paths(corpus_root, source_dir)
    with _finalize_lock(paths, timeout_seconds=lock_timeout):
        return _finalize_locked(
            paths,
            draft_uid,
            principals,
            authority_uid,
            principal_directory_revision,
            failpoint=failpoint,
        )


# --------------------------------------------------------------------------- #
# Thin CLI.                                                                    #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tropo-finalize-group",
        description="Seal one draft group into a resolver-invisible candidate generation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    finalize = sub.add_parser("finalize", help="finalize one draft group")
    finalize.add_argument("--corpus-root", required=True)
    finalize.add_argument("--draft-uid", required=True)
    finalize.add_argument("--authority-uid", required=True)
    finalize.add_argument("--principal-directory-revision", required=True)
    finalize.add_argument(
        "--principals-file",
        required=True,
        help="JSON file mapping principal_uid -> portable claim mapping",
    )
    finalize.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR)

    recover = sub.add_parser("recover", help="recover or refuse a prior incomplete finalize")
    recover.add_argument("--corpus-root", required=True)
    recover.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        if args.command == "finalize":
            principals = json.loads(Path(args.principals_file).read_text(encoding="utf-8"))
            result = finalize_group(
                args.corpus_root,
                args.draft_uid,
                principals=principals,
                authority_uid=args.authority_uid,
                principal_directory_revision=args.principal_directory_revision,
                source_dir=args.source_dir,
            )
            print(json.dumps(result.to_dict(), ensure_ascii=False))
            return 0
        outcome = recover_candidate(args.corpus_root, source_dir=args.source_dir)
        print(json.dumps(outcome.to_dict(), ensure_ascii=False))
        return 0
    except GroupContractError as error:
        print(
            json.dumps({"error": error.code.value, "message": error.message}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 3
    except FinalizeLockTimeout as error:
        print(
            json.dumps({"error": "FINALIZE_LOCK_TIMEOUT", "message": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 4


__all__ = [
    "CANDIDATE_DIR",
    "GENERATION_DIR",
    "GEN_GROUPS_RELATIVE",
    "GEN_INDEX_RELATIVE",
    "GEN_REGISTRY_RELATIVE",
    "GEN_SQLITE_RELATIVE",
    "GEN_WRAPPER_RELATIVE",
    "JOURNAL_RELATIVE",
    "PUBLISHED_REGISTRY_RELATIVE",
    "FinalizeLockTimeout",
    "FinalizeResult",
    "RecoveryOutcome",
    "SimulatedProcessLoss",
    "finalize_group",
    "main",
    "recover_candidate",
]


if __name__ == "__main__":
    raise SystemExit(main())
