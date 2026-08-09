#!/usr/bin/env python3
"""Deterministic group-registry rebuild / parity / recovery CLI (B4a).

This tool re-projects the resolver-visible group registry from the authored
active group sources and proves its SQLite acceleration is a faithful mirror of
the canonical JSONL.  It is a **thin wrapper** over :mod:`lib.group_registry`
and :mod:`lib.group_contract`: the projection, wrapper binding, SQLite build,
and field-for-field parity check are all *imported and called*, never
reimplemented (dev-spec ``vault/files/0bfa771d.md``, ``## Registry, resolver,
and contextual audience``).

Locked architecture choice 2 governs the split enforced here: the resolver reads
verified canonical JSONL directly; SQLite is mandatory acceleration and parity
evidence, never a second authority.  A full re-projection drops and rebuilds the
SQLite table, so stale rows never survive; any disagreement between the JSONL and
the SQLite mirror (including a mutated or truncated database) refuses
``PROJECTION_MISMATCH``.

Subcommands:

``rebuild``
    Load the authored active corpus, project it deterministically, and publish
    the revision-tagged JSONL/SQLite/wrapper under one PREPARED->COMMITTED
    journal.  Repeated rebuilds over an unchanged corpus produce byte-identical
    JSONL; a dropped group leaves no stale row.  Authority-revision pins are read
    from the installed authority (``installed.json``) or supplied explicitly.

``verify``
    Re-check the published registry: the JSONL digest/row-count against its
    wrapper, and every logical SQLite field against the parsed JSONL.  A tampered
    database refuses ``PROJECTION_MISMATCH``.

``recover``
    The recovery entrypoint: roll a durable-but-incomplete rebuild forward
    exactly once from verified staged bytes, verify + clean an already-committed
    one, or refuse ``RECOVERY_REQUIRED`` without guessing.

Boundaries: all paths are corpus-root-relative POSIX (the operator passes
``--corpus-root``); the tool hard-codes no absolute path and opens no network
connection.
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

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from lib.group_authority import verify_principal_directory  # noqa: E402
from lib.group_contract import (  # noqa: E402
    GroupContractError,
    GroupErrorCode,
    build_group_corpus,
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
# Layout constants (corpus-root-relative POSIX).                              #
# --------------------------------------------------------------------------- #

PUBLISHED_REGISTRY_RELATIVE = "vault/00-group-registry.jsonl"
PUBLISHED_SQLITE_RELATIVE = "vault/00-group-registry.sqlite"
PUBLISHED_WRAPPER_RELATIVE = "vault/00-group-registry-wrapper.json"

REGISTRY_WORK_DIR = ".tropo-studio/group-registry"
JOURNAL_RELATIVE = REGISTRY_WORK_DIR + "/rebuild-journal.jsonl"
STAGING_DIR = REGISTRY_WORK_DIR + "/staging"
BACKUPS_DIR = REGISTRY_WORK_DIR + "/backups"
LOCK_RELATIVE = REGISTRY_WORK_DIR + "/registry.lock"

# Written by ``tropo-group-authority install`` -- the machine-local authority pin
# that carries the revision context the registry rows must bind.
INSTALLED_RELATIVE = ".tropo-studio/authorities/group-authority/installed.json"

DEFAULT_SOURCE_DIR = "groups"
JOURNAL_GENESIS = "tropo.group-registry.journal.v1:genesis"


# --------------------------------------------------------------------------- #
# Exceptions.                                                                  #
# --------------------------------------------------------------------------- #


class RegistryLockTimeout(TimeoutError):
    """Another writer held the exclusive registry lock past the safety bound."""


class RegistryUsageError(ValueError):
    """A CLI input error distinct from a typed projection refusal."""


def _raise(code: GroupErrorCode, message: str, **kwargs: Any) -> "None":
    raise GroupContractError(code, message, **kwargs)


# --------------------------------------------------------------------------- #
# Byte / digest / fsync / atomic-write primitives (house durability infra).   #
# --------------------------------------------------------------------------- #


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_file(path: Path) -> Optional[str]:
    try:
        return _digest_bytes(path.read_bytes())
    except FileNotFoundError:
        return None


def _read_bytes(path: Path) -> Optional[bytes]:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _read_json_file(path: Path) -> Optional[Any]:
    raw = _read_bytes(path)
    if raw is None:
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
        pass
    finally:
        os.close(fd)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _write_and_fsync(path: Path, data: bytes) -> None:
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
# Exclusive registry lock (process-scoped flock, machine-local).             #
# --------------------------------------------------------------------------- #


@contextmanager
def _registry_lock(root: Path, *, timeout_seconds: float) -> Iterator[Path]:
    lock_path = root / LOCK_RELATIVE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
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
                    raise RegistryLockTimeout(
                        f"timed out after {timeout_seconds:.0f}s waiting for {lock_path}"
                    )
                time.sleep(0.02)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid: {os.getpid()}\n")
        handle.flush()
        os.fsync(handle.fileno())
        yield lock_path
    finally:
        if acquired:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


# --------------------------------------------------------------------------- #
# Hash-chained PREPARED -> COMMITTED rebuild journal.                          #
# --------------------------------------------------------------------------- #


def _row_hash(prev_hash: str, row: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in row.items() if key != "row_hash"}
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    return hashlib.sha256((prev_hash + "\n" + canonical).encode("utf-8")).hexdigest()


def _read_journal(path: Path) -> list[dict[str, Any]]:
    raw = _read_bytes(path)
    if raw is None:
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as error:
            raise GroupContractError(
                GroupErrorCode.RECOVERY_REQUIRED,
                f"rebuild journal line {line_number} is not valid JSON",
            ) from error
        if not isinstance(obj, dict):
            _raise(GroupErrorCode.RECOVERY_REQUIRED, f"rebuild journal line {line_number} is not an object")
        rows.append(obj)
    return rows


def _verify_chain(rows: Sequence[Mapping[str, Any]]) -> None:
    prev = JOURNAL_GENESIS
    for index, row in enumerate(rows):
        expected = _row_hash(prev, row)
        if row.get("prev_hash") != prev or row.get("row_hash") != expected:
            _raise(GroupErrorCode.RECOVERY_REQUIRED, f"rebuild journal hash chain broken at row {index}")
        prev = row["row_hash"]


def _append_row(rows: Sequence[Mapping[str, Any]], row: Mapping[str, Any]) -> list[dict[str, Any]]:
    prev = rows[-1]["row_hash"] if rows else JOURNAL_GENESIS
    new_row = dict(row)
    new_row["prev_hash"] = prev
    new_row["row_hash"] = _row_hash(prev, new_row)
    return [dict(existing) for existing in rows] + [new_row]


def _write_journal_atomic(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    data = b"".join(
        json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
        for row in rows
    )
    _atomic_write_bytes(path, data)


def _last_transaction(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[Optional[Mapping[str, Any]], Optional[Mapping[str, Any]]]:
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
# Plan-based, journaled, roll-forward-only publisher.                          #
# --------------------------------------------------------------------------- #


def _build_plan(root: Path, new_bytes: Mapping[str, bytes], dest_paths: Mapping[str, str]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for name, rel in dest_paths.items():
        old_digest = _digest_file(root / rel)
        plan.append(
            {
                "name": name,
                "path": rel,
                "old": old_digest,
                "new": _digest_bytes(new_bytes[name]),
                "staged": f"{STAGING_DIR}/{name}",
                "backup": f"{BACKUPS_DIR}/{name}" if old_digest is not None else None,
            }
        )
    return plan


def _staged_ok(root: Path, plan: Sequence[Mapping[str, Any]]) -> bool:
    for dest in plan:
        data = _read_bytes(root / dest["staged"])
        if data is None or _digest_bytes(data) != dest["new"]:
            return False
    return True


def _apply_staged(root: Path, dest: Mapping[str, Any]) -> None:
    data = _read_bytes(root / dest["staged"])
    if data is None or _digest_bytes(data) != dest["new"]:
        _raise(
            GroupErrorCode.RECOVERY_REQUIRED,
            f"staged bytes for {dest['name']!r} are missing or do not match the recorded digest",
        )
    _atomic_write_bytes(root / dest["path"], data)


def _verify_dest_digests(root: Path, plan: Sequence[Mapping[str, Any]]) -> None:
    for dest in plan:
        if _digest_file(root / dest["path"]) != dest["new"]:
            _raise(
                GroupErrorCode.PROJECTION_MISMATCH,
                f"published surface {dest['name']!r} does not match its committed digest",
            )


def _commit_plan(
    root: Path,
    plan: Sequence[Mapping[str, Any]],
    new_bytes: Mapping[str, bytes],
    meta: Mapping[str, Any],
    verify_fn,
) -> None:
    staging = root / STAGING_DIR
    backups = root / BACKUPS_DIR
    _clear_dir(staging)
    _clear_dir(backups)

    for dest in plan:
        if dest["old"] is not None:
            current = (root / dest["path"]).read_bytes()
            if _digest_bytes(current) != dest["old"]:
                _raise(
                    GroupErrorCode.RECOVERY_REQUIRED,
                    f"destination {dest['name']!r} changed while preparing the rebuild",
                )
            _write_and_fsync(root / dest["backup"], current)
    _fsync_dir(backups)

    for dest in plan:
        _write_and_fsync(root / dest["staged"], new_bytes[dest["name"]])
    _fsync_dir(staging)

    journal = root / JOURNAL_RELATIVE
    rows = _read_journal(journal)
    txn_id = uuid.uuid4().hex
    prepared = {"type": "PREPARED", "txn_id": txn_id, "plan": list(plan)}
    prepared.update(meta)
    _write_journal_atomic(journal, _append_row(rows, prepared))

    for dest in plan:
        _apply_staged(root, dest)

    verify_fn()
    _verify_dest_digests(root, plan)

    rows = _read_journal(journal)
    committed = {"type": "COMMITTED", "txn_id": txn_id}
    committed.update(meta)
    _write_journal_atomic(journal, _append_row(rows, committed))

    _clear_dir(staging)
    _clear_dir(backups)
    # Retire the journal after a clean commit so the next ``rebuild`` starts from a
    # blank slate and regenerates every surface from source.  A lingering COMMITTED
    # row would otherwise make the following recovery re-verify already-published
    # bytes and wedge an idempotent rebuild behind an externally tampered surface;
    # ongoing tamper detection is ``verify``'s responsibility, not the journal's.
    _remove(journal)


def _recover_locked(root: Path, verify_fn) -> dict[str, Any]:
    """Roll a durable-but-incomplete rebuild forward, or refuse (never guess)."""

    journal = root / JOURNAL_RELATIVE
    staging = root / STAGING_DIR
    backups = root / BACKUPS_DIR
    rows = _read_journal(journal)
    if not rows:
        _clear_dir(staging)
        _clear_dir(backups)
        return {"state": "none"}

    _verify_chain(rows)
    prepared, committed = _last_transaction(rows)
    if prepared is None:
        _raise(GroupErrorCode.RECOVERY_REQUIRED, "rebuild journal has no PREPARED transaction")

    plan = prepared["plan"]
    if committed is not None:
        # A COMMITTED marker means every surface was applied *and* verified before
        # the marker was written, so the only outstanding work is to retire the
        # journal.  Re-verifying published bytes here is deliberately *not* done:
        # external tampering after a clean commit is caught by ``verify``, and
        # re-checking on this path would wedge an idempotent ``rebuild`` behind a
        # mutated surface it is about to overwrite anyway.
        _clear_dir(staging)
        _clear_dir(backups)
        _remove(journal)
        return {"state": "settled", "txn_id": prepared.get("txn_id")}

    if not _staged_ok(root, plan):
        _raise(
            GroupErrorCode.RECOVERY_REQUIRED,
            "a prior rebuild is incomplete and its staged bytes are missing; recovery cannot roll forward",
        )
    for dest in plan:
        _apply_staged(root, dest)
    verify_fn()
    _verify_dest_digests(root, plan)
    rows = _read_journal(journal)
    _write_journal_atomic(journal, _append_row(rows, {"type": "COMMITTED", "txn_id": prepared["txn_id"]}))
    _clear_dir(staging)
    _clear_dir(backups)
    _remove(journal)
    return {"state": "completed", "txn_id": prepared["txn_id"]}


# --------------------------------------------------------------------------- #
# Source / principal / pin loading.                                            #
# --------------------------------------------------------------------------- #


def _load_principals(
    root: Path,
    principals_file: Optional[str],
    installed: Optional[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Resolve the portable principal directory for corpus validation.

    Prefers an explicit ``--principals-file``; otherwise reads the installed
    generation's canonical ``principals.jsonl`` (verified field-for-field).
    """

    if principals_file is not None:
        data = _read_json_file(Path(principals_file))
        if data is None:
            raise RegistryUsageError(f"principals file not found: {principals_file}")
        if isinstance(data, Mapping):
            claims = list(data.values())
        elif isinstance(data, list):
            claims = list(data)
        else:
            raise RegistryUsageError("principals file must be a JSON list of claims or a UID->claim mapping")
        mapping: dict[str, dict[str, Any]] = {}
        for claim in claims:
            if not isinstance(claim, Mapping) or not isinstance(claim.get("principal_uid"), str):
                raise RegistryUsageError("each principal claim needs a string 'principal_uid'")
            mapping[claim["principal_uid"]] = dict(claim)
        return mapping

    if installed is not None:
        generation_dir = installed.get("generation_dir")
        if isinstance(generation_dir, str):
            principals_jsonl = _read_bytes(root / generation_dir / "principals.jsonl")
            if principals_jsonl is not None:
                directory = verify_principal_directory(principals_jsonl)
                return {uid: dict(row) for uid, row in directory.items()}

    raise RegistryUsageError(
        "no principal directory available: pass --principals-file or install an authority first"
    )


def _load_active_corpus(root: Path, source_dir: str, principals_map: Mapping[str, Mapping[str, Any]]):
    source_root = root / source_dir
    if not source_root.is_dir():
        raise RegistryUsageError(f"source directory not found: {source_root}")
    groups: dict[str, dict[str, Any]] = {}
    for entry in sorted(source_root.glob("*.json")):
        obj = _read_json_file(entry)
        if not isinstance(obj, dict):
            _raise(GroupErrorCode.GROUP_SCHEMA_INVALID, f"group source {entry.name} is not a JSON object")
        uid = obj.get("uid")
        if not isinstance(uid, str):
            _raise(GroupErrorCode.GROUP_SCHEMA_INVALID, f"group source {entry.name} has no string uid")
        if uid in groups:
            _raise(GroupErrorCode.GROUP_SCHEMA_INVALID, f"group uid {uid} appears in more than one source file", reference_uid=uid)
        groups[uid] = obj
    return build_group_corpus(groups, principals_map)


def _derived_corpus_sha256(corpus) -> str:
    """SHA-256 over the canonical active groups.jsonl (source-of-truth digest)."""

    from lib.group_authority import build_groups_jsonl  # local import: same lib family

    active = [corpus.resolve_group(uid) for uid in corpus.active_uids]
    return _digest_bytes(build_groups_jsonl(active))


# --------------------------------------------------------------------------- #
# Projection + publication.                                                    #
# --------------------------------------------------------------------------- #


def _projection_sqlite_bytes(projection: RegistryProjection) -> bytes:
    tmp = Path(tempfile.mkdtemp(prefix=".rgr-sqlite-"))
    db_path = tmp / "registry.sqlite"
    try:
        connection = sqlite3.connect(str(db_path))
        try:
            build_parity_database(projection, connection)
            check_sqlite_parity(projection, connection)
        finally:
            connection.close()
        return db_path.read_bytes()
    finally:
        if db_path.exists():
            try:
                db_path.unlink()
            except OSError:
                pass
        try:
            tmp.rmdir()
        except OSError:
            pass


def _reconstruct_wrapper(obj: Mapping[str, Any]) -> RegistryWrapper:
    try:
        return RegistryWrapper(
            jsonl_sha256=obj["jsonl_sha256"],
            row_count=obj["row_count"],
            canonicalization_version=obj["canonicalization_version"],
            source_authority_uid=obj["source_authority_uid"],
            source_revision=obj["source_revision"],
            principal_directory_revision=obj["principal_directory_revision"],
            producers=tuple(obj["producers"]),
            consumers=tuple(obj["consumers"]),
        )
    except (KeyError, TypeError) as error:
        raise GroupContractError(
            GroupErrorCode.PROJECTION_MISMATCH,
            f"published registry wrapper is malformed: {type(error).__name__}",
        ) from error


def _verify_published(root: Path, projection: RegistryProjection) -> None:
    if _read_bytes(root / PUBLISHED_REGISTRY_RELATIVE) != projection.jsonl_bytes:
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "published registry JSONL does not match the projection")
    if _read_bytes(root / PUBLISHED_WRAPPER_RELATIVE) != projection.wrapper.canonical_bytes():
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "published registry wrapper does not match the projection")
    connection = sqlite3.connect(str(root / PUBLISHED_SQLITE_RELATIVE))
    try:
        check_sqlite_parity(projection, connection)
    finally:
        connection.close()


# --------------------------------------------------------------------------- #
# rebuild                                                                      #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RebuildResult:
    status: str
    recovery: str
    source_authority_uid: str
    source_revision: str
    principal_directory_revision: str
    registry_jsonl_sha256: str
    registry_wrapper_sha256: str
    row_count: int
    group_uids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "recovery": self.recovery,
            "source_authority_uid": self.source_authority_uid,
            "source_revision": self.source_revision,
            "principal_directory_revision": self.principal_directory_revision,
            "registry_jsonl_sha256": self.registry_jsonl_sha256,
            "registry_wrapper_sha256": self.registry_wrapper_sha256,
            "row_count": self.row_count,
            "group_uids": list(self.group_uids),
            "registry_jsonl_path": PUBLISHED_REGISTRY_RELATIVE,
            "registry_sqlite_path": PUBLISHED_SQLITE_RELATIVE,
            "registry_wrapper_path": PUBLISHED_WRAPPER_RELATIVE,
        }


def _resolve_pins(
    corpus,
    installed: Optional[Mapping[str, Any]],
    *,
    authority_uid: Optional[str],
    source_revision: Optional[str],
    principal_directory_revision: Optional[str],
    derive_revision: bool,
) -> tuple[str, str, str]:
    """Resolve (source_authority_uid, source_revision, principal_directory_revision).

    Explicit args win; otherwise the installed authority pin supplies them.  When
    ``derive_revision`` is set (standalone use) the source revision is derived
    from the authored corpus digest.  If an installed pin is present, the derived
    corpus digest must match it, else the authored source has drifted stale.
    """

    corpus_sha = _derived_corpus_sha256(corpus)
    derived_revision = f"sha256:{corpus_sha}"

    if installed is not None:
        installed_sha = installed.get("corpus_sha256")
        if isinstance(installed_sha, str) and installed_sha != corpus_sha:
            _raise(
                GroupErrorCode.GROUP_CORPUS_STALE,
                "authored active corpus digest does not match the installed authority corpus_sha256",
            )

    resolved_authority = authority_uid or (installed.get("authority_uid") if installed else None)
    resolved_pdr = principal_directory_revision or (
        installed.get("principal_directory_revision") if installed else None
    )
    if source_revision is not None:
        resolved_revision: Optional[str] = source_revision
    elif installed is not None and isinstance(installed.get("corpus_revision"), str):
        resolved_revision = installed["corpus_revision"]
    elif derive_revision:
        resolved_revision = derived_revision
    else:
        resolved_revision = None

    if not resolved_authority:
        raise RegistryUsageError("no authority UID: pass --authority-uid or install an authority first")
    if not resolved_pdr:
        raise RegistryUsageError(
            "no principal directory revision: pass --principal-directory-revision or install an authority first"
        )
    if not resolved_revision:
        raise RegistryUsageError(
            "no source revision: pass --source-revision, --derive-revision, or install an authority first"
        )
    return resolved_authority, resolved_revision, resolved_pdr


def rebuild_registry(
    root: Path,
    *,
    source_dir: str = DEFAULT_SOURCE_DIR,
    principals_file: Optional[str] = None,
    authority_uid: Optional[str] = None,
    source_revision: Optional[str] = None,
    principal_directory_revision: Optional[str] = None,
    derive_revision: bool = False,
    lock_timeout: float = 60.0,
) -> RebuildResult:
    """Re-project + publish the group registry deterministically under a journal."""

    with _registry_lock(root, timeout_seconds=lock_timeout):
        recovery = _recover_locked(root, verify_fn=lambda: None)

        installed = _read_json_file(root / INSTALLED_RELATIVE)
        if installed is not None and not isinstance(installed, dict):
            installed = None
        principals_map = _load_principals(root, principals_file, installed)
        corpus = _load_active_corpus(root, source_dir, principals_map)
        resolved_authority, resolved_revision, resolved_pdr = _resolve_pins(
            corpus,
            installed,
            authority_uid=authority_uid,
            source_revision=source_revision,
            principal_directory_revision=principal_directory_revision,
            derive_revision=derive_revision,
        )

        context = AuthorityRevisionContext(
            source_authority_uid=resolved_authority,
            source_revision=resolved_revision,
            principal_directory_revision=resolved_pdr,
            source_paths={uid: f"{source_dir}/{uid}.json" for uid in corpus.active_uids},
        )
        projection = project_registry(corpus, context)
        sqlite_bytes = _projection_sqlite_bytes(projection)

        new_bytes: dict[str, bytes] = {
            "registry_jsonl": projection.jsonl_bytes,
            "registry_sqlite": sqlite_bytes,
            "registry_wrapper": projection.wrapper.canonical_bytes(),
        }
        dest_paths: dict[str, str] = {
            "registry_jsonl": PUBLISHED_REGISTRY_RELATIVE,
            "registry_sqlite": PUBLISHED_SQLITE_RELATIVE,
            "registry_wrapper": PUBLISHED_WRAPPER_RELATIVE,
        }
        plan = _build_plan(root, new_bytes, dest_paths)
        meta = {
            "source_authority_uid": resolved_authority,
            "source_revision": resolved_revision,
            "registry_jsonl_sha256": projection.jsonl_sha256,
        }
        _commit_plan(root, plan, new_bytes, meta, verify_fn=lambda: _verify_published(root, projection))

        return RebuildResult(
            status="rebuilt",
            recovery=recovery.get("state", "none"),
            source_authority_uid=resolved_authority,
            source_revision=resolved_revision,
            principal_directory_revision=resolved_pdr,
            registry_jsonl_sha256=projection.jsonl_sha256,
            registry_wrapper_sha256=projection.wrapper.wrapper_sha256,
            row_count=projection.row_count,
            group_uids=projection.group_uids,
        )


# --------------------------------------------------------------------------- #
# verify                                                                       #
# --------------------------------------------------------------------------- #


def verify_registry(root: Path) -> dict[str, Any]:
    """Prove the published JSONL/SQLite/wrapper agree; refuse PROJECTION_MISMATCH."""

    jsonl = _read_bytes(root / PUBLISHED_REGISTRY_RELATIVE)
    if jsonl is None:
        _raise(GroupErrorCode.GROUP_CORPUS_UNAVAILABLE, "no published registry JSONL to verify")
    wrapper_obj = _read_json_file(root / PUBLISHED_WRAPPER_RELATIVE)
    if not isinstance(wrapper_obj, dict):
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "published registry wrapper is missing or malformed")
    wrapper = _reconstruct_wrapper(wrapper_obj)

    rows = parse_registry_jsonl(jsonl)
    if _digest_bytes(jsonl) != wrapper.jsonl_sha256:
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "published registry JSONL digest disagrees with its wrapper")
    if len(rows) != wrapper.row_count:
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "published registry row count disagrees with its wrapper")

    projection = RegistryProjection(
        jsonl_bytes=jsonl,
        rows=tuple(rows),
        wrapper=wrapper,
        source_authority_uid=wrapper.source_authority_uid,
        source_revision=wrapper.source_revision,
        principal_directory_revision=wrapper.principal_directory_revision,
    )
    sqlite_path = root / PUBLISHED_SQLITE_RELATIVE
    if not sqlite_path.exists():
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "published registry SQLite mirror is missing")
    connection = sqlite3.connect(str(sqlite_path))
    try:
        check_sqlite_parity(projection, connection)
    finally:
        connection.close()

    return {
        "status": "verified",
        "row_count": wrapper.row_count,
        "registry_jsonl_sha256": wrapper.jsonl_sha256,
        "registry_wrapper_sha256": wrapper.wrapper_sha256,
        "source_authority_uid": wrapper.source_authority_uid,
        "source_revision": wrapper.source_revision,
    }


# --------------------------------------------------------------------------- #
# recover                                                                      #
# --------------------------------------------------------------------------- #


def recover_registry(root: Path, *, lock_timeout: float = 60.0) -> dict[str, Any]:
    """Recovery entrypoint: roll a durable-but-incomplete rebuild forward or refuse."""

    with _registry_lock(root, timeout_seconds=lock_timeout):
        outcome = _recover_locked(root, verify_fn=lambda: None)
    outcome["status"] = "recovered"
    return outcome


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tropo-rebuild-group-registry",
        description="Deterministic group-registry projection, parity verification, and recovery (B4a).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    rebuild = sub.add_parser("rebuild", help="re-project + publish the registry deterministically")
    rebuild.add_argument("--corpus-root", default=".")
    rebuild.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR)
    rebuild.add_argument("--principals-file", default=None, help="JSON claims (default: installed generation)")
    rebuild.add_argument("--authority-uid", default=None, help="default: installed authority pin")
    rebuild.add_argument("--source-revision", default=None, help="default: installed authority corpus_revision")
    rebuild.add_argument("--principal-directory-revision", default=None, help="default: installed authority pin")
    rebuild.add_argument(
        "--derive-revision",
        action="store_true",
        help="standalone: derive source_revision from the authored corpus digest",
    )

    verify = sub.add_parser("verify", help="verify published JSONL/SQLite/wrapper parity")
    verify.add_argument("--corpus-root", default=".")

    recover = sub.add_parser("recover", help="recovery entrypoint for an incomplete rebuild")
    recover.add_argument("--corpus-root", default=".")

    return parser


def _emit(obj: Mapping[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def _emit_error(code: str, message: str) -> None:
    print(json.dumps({"error": code, "message": message}, ensure_ascii=False), file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    root = Path(args.corpus_root)
    try:
        if args.command == "rebuild":
            result = rebuild_registry(
                root,
                source_dir=args.source_dir,
                principals_file=args.principals_file,
                authority_uid=args.authority_uid,
                source_revision=args.source_revision,
                principal_directory_revision=args.principal_directory_revision,
                derive_revision=args.derive_revision,
            )
            _emit(result.to_dict())
            return 0

        if args.command == "verify":
            _emit(verify_registry(root))
            return 0

        if args.command == "recover":
            _emit(recover_registry(root))
            return 0

        parser.error(f"unknown command {args.command!r}")
        return 2
    except GroupContractError as error:
        _emit_error(error.code.value, error.message)
        return 3
    except RegistryLockTimeout as error:
        _emit_error("REGISTRY_LOCK_TIMEOUT", str(error))
        return 4
    except RegistryUsageError as error:
        _emit_error("USAGE_ERROR", str(error))
        return 2


__all__ = [
    "PUBLISHED_REGISTRY_RELATIVE",
    "PUBLISHED_SQLITE_RELATIVE",
    "PUBLISHED_WRAPPER_RELATIVE",
    "INSTALLED_RELATIVE",
    "RegistryLockTimeout",
    "RegistryUsageError",
    "RebuildResult",
    "main",
    "rebuild_registry",
    "recover_registry",
    "verify_registry",
]


if __name__ == "__main__":
    raise SystemExit(main())
