#!/usr/bin/env python3
"""Governed group-authority CLI: build, verify, accept-fingerprint, install (B4a).

This tool is the operator surface for the authenticated group authority defined
in the locked dev-spec ``vault/files/0bfa771d.md`` (see ``## Authority and
trust`` and ``## Finalization and recovery``).  It is a **thin wrapper**: every
piece of authority logic -- canonical artifact serialization, the domain
separated Ed25519 signature over the fixed ``group_authority`` tuple, out-of-band
fingerprint trust, and high-water anti-rollback -- lives in
:mod:`lib.group_authority` and is *imported and called*, never reimplemented.
Deterministic registry projection is likewise delegated to
:mod:`lib.group_registry`, and group semantics to :mod:`lib.group_contract`.

Subcommands (dev-spec ``## Authority and trust``):

``build``
    Derive the canonical authority artifacts (``groups.jsonl``,
    ``principals.jsonl``, ``audience-policy.json``, ``artifact-manifest.json``)
    from the finalized active authored group sources, build the fixed authority
    tuple, and sign it with an **externally supplied** Ed25519 seed.  The signed
    envelope + artifacts are written to a machine-local build bundle.  The
    private key is read from a caller-supplied path and is **never persisted**
    into the Studio (no artifact, journal, or trust row ever contains it).

``accept-fingerprint``
    Record an accepted signing key in the machine-local trust file **only** when
    the recomputed public-key fingerprint equals the exact value the operator
    compared out of band.  There is no trust-on-first-use, ``--yes``, wildcard,
    or self-accept path -- ``accept_authority_key`` enforces that.

``verify``
    Verify a signed envelope + artifacts against the accepted trust and the
    out-of-band fingerprint.  Trust is never manufactured here; a key that was
    not accepted refuses ``AUTHORITY_UNTRUSTED``.

``install``
    Verify, enforce the high-water / rollback rules
    (``install_authority`` / ``evaluate_install``), and -- as the sole publisher
    -- stage and swap the installed immutable generation, the revision-tagged
    registry JSONL/SQLite/wrapper, the machine-local authority pin, and the
    advanced trust high-water under one PREPARED->COMMITTED journal.  Recovery
    after a high-water advance is roll-forward-only.

Boundaries: all paths are corpus-root-relative POSIX (the operator passes
``--corpus-root``); the tool hard-codes no absolute path and opens no network
connection.  The one top-level ``group_authority`` tuple is recorded in a
machine-local install pin
(``.tropo-studio/authorities/group-authority/installed.json``); writing the
integration compose-lock v2 is a separate serialized integration surface and is
deliberately out of this unit slice (see the build report).
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

# ``os.path.dirname(os.path.abspath(__file__))`` is a computed directory (not a
# hard-coded absolute path literal); it mirrors the sibling B4a tools so the
# ``lib`` package resolves however the caller placed ``vault/tools`` on the path.
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# The seed -> public-key derivation for the ``build`` gesture uses the same
# offline Ed25519 backend the authority library already depends on.  Signing
# itself goes through ``lib.group_authority.sign_authority_tuple``.
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)

from lib.group_authority import (  # noqa: E402
    ARTIFACT_MANIFEST_ARTIFACT,
    AUDIENCE_POLICY_ARTIFACT,
    CORPUS_ARTIFACT,
    PRINCIPAL_ARTIFACT,
    SIGNED_ENVELOPE_ARTIFACT,
    GroupAuthorityError,
    GroupContractError,
    GroupErrorCode,
    InstallStatus,
    accept_authority_key,
    build_artifact_manifest,
    build_audience_policy,
    build_authority_tuple,
    build_groups_jsonl,
    build_principals_jsonl,
    build_signed_envelope,
    canonical_envelope_bytes,
    fingerprint,
    install_authority,
    previous_envelope_sha256,
    public_key_base64,
    sha256_hex,
    sign_authority_tuple,
    verify_authority,
    verify_principal_directory,
)
from lib.group_contract import (  # noqa: E402
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
# Layout constants (all corpus-root-relative POSIX; machine-local).           #
# --------------------------------------------------------------------------- #

AUTHORITY_DIR = ".tropo-studio/authorities/group-authority"
BUILD_DIR = AUTHORITY_DIR + "/build"
GENERATIONS_DIR = AUTHORITY_DIR + "/generations"
INSTALLED_RELATIVE = AUTHORITY_DIR + "/installed.json"
INSTALL_JOURNAL_RELATIVE = AUTHORITY_DIR + "/install-journal.jsonl"
INSTALL_STAGING_DIR = AUTHORITY_DIR + "/install-staging"
INSTALL_BACKUPS_DIR = AUTHORITY_DIR + "/install-backups"
LOCK_RELATIVE = AUTHORITY_DIR + "/authority.lock"

# Machine-local trust record: the closed object ``{accepted_keys, high_water}``.
# Never shipped, never overwritten by an update (dev-spec ``## Authority and
# trust``).
TRUST_RELATIVE = ".tropo-studio/trust/group-authorities.json"

# The single resolver-visible registry surface published by ``install``.
PUBLISHED_REGISTRY_RELATIVE = "vault/00-group-registry.jsonl"
PUBLISHED_SQLITE_RELATIVE = "vault/00-group-registry.sqlite"
PUBLISHED_WRAPPER_RELATIVE = "vault/00-group-registry-wrapper.json"

DEFAULT_SOURCE_DIR = "groups"
INSTALLED_SCHEMA_ID = "tropo.group-authority-install/v1"
JOURNAL_GENESIS = "tropo.group-authority.journal.v1:genesis"

ARTIFACT_NAMES = (
    CORPUS_ARTIFACT,
    PRINCIPAL_ARTIFACT,
    AUDIENCE_POLICY_ARTIFACT,
    ARTIFACT_MANIFEST_ARTIFACT,
)


# --------------------------------------------------------------------------- #
# Exceptions / typed refusal helper.                                          #
# --------------------------------------------------------------------------- #


class AuthorityLockTimeout(TimeoutError):
    """Another writer held the exclusive authority lock past the safety bound."""


class AuthorityUsageError(ValueError):
    """A CLI input error (missing file, malformed JSON) distinct from a refusal."""


def _raise(code: GroupErrorCode, message: str, **kwargs: Any) -> "None":
    raise GroupAuthorityError(code, message, **kwargs)


# --------------------------------------------------------------------------- #
# Byte / digest / fsync / atomic-write primitives (house durability infra).   #
# These are I/O plumbing, not authority logic; every cryptographic and         #
# projection decision is delegated to the imported libraries.                  #
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
    """Same-directory temp -> fsync file -> atomic replace -> fsync parent."""

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


def _canonical_json_line(obj: Mapping[str, Any], *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=sort_keys)
        .encode("utf-8")
        + b"\n"
    )


# --------------------------------------------------------------------------- #
# Exclusive authority lock (process-scoped flock, machine-local).             #
# --------------------------------------------------------------------------- #


@contextmanager
def _authority_lock(root: Path, *, timeout_seconds: float) -> Iterator[Path]:
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
                    raise AuthorityLockTimeout(
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
# Hash-chained PREPARED -> COMMITTED install journal.                          #
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
            raise GroupAuthorityError(
                GroupErrorCode.RECOVERY_REQUIRED,
                f"install journal line {line_number} is not valid JSON",
            ) from error
        if not isinstance(obj, dict):
            _raise(GroupErrorCode.RECOVERY_REQUIRED, f"install journal line {line_number} is not an object")
        rows.append(obj)
    return rows


def _verify_chain(rows: Sequence[Mapping[str, Any]]) -> None:
    prev = JOURNAL_GENESIS
    for index, row in enumerate(rows):
        expected = _row_hash(prev, row)
        if row.get("prev_hash") != prev or row.get("row_hash") != expected:
            _raise(GroupErrorCode.RECOVERY_REQUIRED, f"install journal hash chain broken at row {index}")
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
# Generic plan-based, journaled, roll-forward-only publisher.                  #
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
                "staged": f"{INSTALL_STAGING_DIR}/{name}",
                "backup": f"{INSTALL_BACKUPS_DIR}/{name}" if old_digest is not None else None,
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
    """Durably swap every destination under one PREPARED->COMMITTED journal."""

    staging = root / INSTALL_STAGING_DIR
    backups = root / INSTALL_BACKUPS_DIR
    _clear_dir(staging)
    _clear_dir(backups)

    for dest in plan:
        if dest["old"] is not None:
            current = (root / dest["path"]).read_bytes()
            if _digest_bytes(current) != dest["old"]:
                _raise(
                    GroupErrorCode.RECOVERY_REQUIRED,
                    f"destination {dest['name']!r} changed while preparing the install",
                )
            _write_and_fsync(root / dest["backup"], current)
    _fsync_dir(backups)

    for dest in plan:
        _write_and_fsync(root / dest["staged"], new_bytes[dest["name"]])
    _fsync_dir(staging)

    journal = root / INSTALL_JOURNAL_RELATIVE
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
    # Retire the journal after a clean commit so the next ``install`` starts from a
    # blank slate.  The durable high-water mark lives in the trust file and the
    # installed pin, not in the journal; a lingering COMMITTED row would only make
    # the following recovery re-verify already-published bytes and could wedge a
    # legitimate high-water advance behind an externally mutated surface (which is
    # ``verify``'s job to catch, not recovery's).
    _remove(journal)


def _recover_locked(root: Path, verify_fn) -> dict[str, Any]:
    """Roll a durable-but-incomplete install forward, or refuse.

    Recovery after a high-water advance is roll-forward-only (dev-spec): a
    PREPARED transaction whose staged bytes are all intact is completed exactly
    once; anything else refuses ``RECOVERY_REQUIRED`` and never guesses.
    """

    journal = root / INSTALL_JOURNAL_RELATIVE
    staging = root / INSTALL_STAGING_DIR
    backups = root / INSTALL_BACKUPS_DIR
    rows = _read_journal(journal)
    if not rows:
        _clear_dir(staging)
        _clear_dir(backups)
        return {"state": "none"}

    _verify_chain(rows)
    prepared, committed = _last_transaction(rows)
    if prepared is None:
        _raise(GroupErrorCode.RECOVERY_REQUIRED, "install journal has no PREPARED transaction")

    plan = prepared["plan"]
    if committed is not None:
        # A COMMITTED marker means every surface was applied *and* verified before
        # the marker was written; the only outstanding work is to retire the
        # journal.  Re-verifying published bytes here is deliberately *not* done:
        # external tampering after a clean install is caught by ``verify``, and
        # re-checking on this path would wedge a legitimate later install behind a
        # mutated surface.
        _clear_dir(staging)
        _clear_dir(backups)
        _remove(journal)
        return {"state": "settled", "txn_id": prepared.get("txn_id")}

    if not _staged_ok(root, plan):
        _raise(
            GroupErrorCode.RECOVERY_REQUIRED,
            "a prior install is incomplete and its staged bytes are missing; recovery cannot roll forward",
        )
    for dest in plan:
        _apply_staged(root, dest)
    verify_fn()
    _verify_dest_digests(root, plan)
    rows = _read_journal(journal)
    committed_row = {"type": "COMMITTED", "txn_id": prepared["txn_id"]}
    for key in ("authority_uid", "authority_generation", "envelope_sha256"):
        if key in prepared:
            committed_row[key] = prepared[key]
    _write_journal_atomic(journal, _append_row(rows, committed_row))
    _clear_dir(staging)
    _clear_dir(backups)
    _remove(journal)
    return {"state": "completed", "txn_id": prepared["txn_id"]}


# --------------------------------------------------------------------------- #
# Trust file helpers.                                                          #
# --------------------------------------------------------------------------- #


def _empty_trust() -> dict[str, Any]:
    return {"accepted_keys": [], "high_water": {}}


def _load_trust(root: Path) -> dict[str, Any]:
    data = _read_json_file(root / TRUST_RELATIVE)
    if data is None:
        return _empty_trust()
    if not isinstance(data, dict):
        _raise(GroupErrorCode.AUTHORITY_UNTRUSTED, "trust file is not a JSON object")
    data.setdefault("accepted_keys", [])
    data.setdefault("high_water", {})
    if not isinstance(data["accepted_keys"], list) or not isinstance(data["high_water"], dict):
        _raise(GroupErrorCode.AUTHORITY_UNTRUSTED, "trust file is not the closed {accepted_keys, high_water} shape")
    return data


def _trust_bytes(record: Mapping[str, Any]) -> bytes:
    # No ``sort_keys``: the accepted-key rows must preserve the exact
    # design-brief key order that ``group_authority`` re-validates on read.
    return _canonical_json_line(record, sort_keys=False)


# --------------------------------------------------------------------------- #
# Source / principal / artifact loading.                                       #
# --------------------------------------------------------------------------- #


def _load_principal_claims(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Load principal claims as both an ordered list and a UID-keyed mapping."""

    data = _read_json_file(path)
    if data is None:
        raise AuthorityUsageError(f"principals file not found: {path}")
    if isinstance(data, Mapping):
        claims = list(data.values())
    elif isinstance(data, list):
        claims = list(data)
    else:
        raise AuthorityUsageError("principals file must be a JSON list of claims or a UID->claim mapping")
    mapping: dict[str, dict[str, Any]] = {}
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise AuthorityUsageError("each principal claim must be a JSON object")
        uid = claim.get("principal_uid")
        if not isinstance(uid, str):
            raise AuthorityUsageError("each principal claim needs a string 'principal_uid'")
        mapping[uid] = dict(claim)
    return [dict(claim) for claim in claims], mapping


def _load_active_group_sources(
    root: Path,
    source_dir: str,
    principals_map: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate the whole authored corpus and return the active semantic objects.

    The full corpus (drafts included) is validated through
    ``build_group_corpus`` -- slug uniqueness, principal resolution, and the
    complete inclusion graph -- and only active groups are returned for signing.
    """

    source_root = root / source_dir
    if not source_root.is_dir():
        raise AuthorityUsageError(f"source directory not found: {source_root}")
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
    if not groups:
        _raise(GroupErrorCode.GROUP_CORPUS_UNAVAILABLE, f"no group source files under {source_dir}/")
    corpus = build_group_corpus(groups, principals_map)
    return [corpus.resolve_group(uid) for uid in corpus.active_uids]


def _load_signing_seed(path: Path) -> bytes:
    """Load an externally supplied 32-byte Ed25519 seed (hex).  Never persisted."""

    raw = _read_bytes(path)
    if raw is None:
        raise AuthorityUsageError(f"signing key file not found: {path}")
    text = raw.decode("utf-8", errors="strict").strip()
    try:
        seed = bytes.fromhex(text)
    except ValueError as error:
        raise AuthorityUsageError("signing key file must contain a hex-encoded Ed25519 seed") from error
    if len(seed) != 32:
        raise AuthorityUsageError("signing key seed must decode to exactly 32 bytes")
    return seed


def _read_bundle(bundle_dir: Path) -> tuple[bytes, dict[str, bytes]]:
    """Read the signed envelope plus the four canonical artifacts from a bundle."""

    envelope = _read_bytes(bundle_dir / SIGNED_ENVELOPE_ARTIFACT)
    if envelope is None:
        raise AuthorityUsageError(f"signed envelope not found: {bundle_dir / SIGNED_ENVELOPE_ARTIFACT}")
    artifacts: dict[str, bytes] = {}
    for name in ARTIFACT_NAMES:
        data = _read_bytes(bundle_dir / name)
        if data is None:
            raise AuthorityUsageError(f"authority artifact not found: {bundle_dir / name}")
        artifacts[name] = data
    return envelope, artifacts


# --------------------------------------------------------------------------- #
# Registry projection from the signed corpus (delegated to group_registry).    #
# --------------------------------------------------------------------------- #


def _parse_signed_groups(groups_jsonl: bytes) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for line in groups_jsonl.split(b"\n"):
        if not line:
            continue
        obj = json.loads(line.decode("utf-8"))
        if not isinstance(obj, dict) or not isinstance(obj.get("uid"), str):
            _raise(GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH, "signed corpus row is not a group object")
        restored = dict(obj)
        # The registry read model wants the authored source shape (semantic
        # object + semantic_hash); recompute the hash from the signed semantics.
        restored["semantic_hash"] = semantic_hash(obj)
        groups[obj["uid"]] = restored
    return groups


def _project_from_verified(
    verified,
    artifacts: Mapping[str, bytes],
    source_dir: str,
) -> tuple[RegistryProjection, bytes]:
    groups = _parse_signed_groups(artifacts[CORPUS_ARTIFACT])
    principals = verify_principal_directory(artifacts[PRINCIPAL_ARTIFACT])
    corpus = build_group_corpus(groups, principals)
    context = AuthorityRevisionContext(
        source_authority_uid=verified.authority_uid,
        source_revision=verified.corpus_revision,
        principal_directory_revision=verified.principal_directory_revision,
        source_paths={uid: f"{source_dir}/{uid}.json" for uid in corpus.active_uids},
    )
    projection = project_registry(corpus, context)
    sqlite_bytes = _projection_sqlite_bytes(projection)
    return projection, sqlite_bytes


def _projection_sqlite_bytes(projection: RegistryProjection) -> bytes:
    tmp = Path(tempfile.mkdtemp(prefix=".ga-sqlite-"))
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
        raise GroupAuthorityError(
            GroupErrorCode.PROJECTION_MISMATCH,
            f"published registry wrapper is malformed: {type(error).__name__}",
        ) from error


def _verify_published_registry(root: Path, projection: RegistryProjection) -> None:
    """Re-verify that the published JSONL/SQLite/wrapper reproduce the projection."""

    jsonl = _read_bytes(root / PUBLISHED_REGISTRY_RELATIVE)
    wrapper_raw = _read_bytes(root / PUBLISHED_WRAPPER_RELATIVE)
    if jsonl != projection.jsonl_bytes:
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "published registry JSONL does not match the projection")
    if wrapper_raw != projection.wrapper.canonical_bytes():
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "published registry wrapper does not match the projection")
    rows = parse_registry_jsonl(jsonl)
    reconstructed = RegistryProjection(
        jsonl_bytes=jsonl,
        rows=tuple(rows),
        wrapper=projection.wrapper,
        source_authority_uid=projection.source_authority_uid,
        source_revision=projection.source_revision,
        principal_directory_revision=projection.principal_directory_revision,
    )
    connection = sqlite3.connect(str(root / PUBLISHED_SQLITE_RELATIVE))
    try:
        check_sqlite_parity(reconstructed, connection)
    finally:
        connection.close()


# --------------------------------------------------------------------------- #
# build                                                                        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BuildResult:
    authority_uid: str
    authority_generation: int
    signing_key_uid: str
    corpus_sha256: str
    corpus_revision: str
    principal_directory_sha256: str
    principal_directory_revision: str
    audience_policy_sha256: str
    artifact_identity: str
    previous_envelope_sha256: Optional[str]
    envelope_sha256: str
    signature: str
    public_key: str
    sha256_fingerprint: str
    bundle_dir: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "built",
            "authority_uid": self.authority_uid,
            "authority_generation": self.authority_generation,
            "signing_key_uid": self.signing_key_uid,
            "corpus_sha256": self.corpus_sha256,
            "corpus_revision": self.corpus_revision,
            "principal_directory_sha256": self.principal_directory_sha256,
            "principal_directory_revision": self.principal_directory_revision,
            "audience_policy_sha256": self.audience_policy_sha256,
            "artifact_identity": self.artifact_identity,
            "previous_envelope_sha256": self.previous_envelope_sha256,
            "envelope_sha256": self.envelope_sha256,
            "signature": self.signature,
            "public_key": self.public_key,
            "sha256_fingerprint": self.sha256_fingerprint,
            "bundle_dir": self.bundle_dir,
        }


def build_authority(
    root: Path,
    *,
    authority_uid: str,
    signing_key_uid: str,
    authority_generation: int,
    private_group_uid: str,
    signing_seed: bytes,
    principal_claims: Sequence[Mapping[str, Any]],
    principals_map: Mapping[str, Mapping[str, Any]],
    source_dir: str = DEFAULT_SOURCE_DIR,
    prior_envelope: Optional[bytes] = None,
    out_dir: Optional[str] = None,
) -> BuildResult:
    """Derive + sign the authority artifacts; write a machine-local bundle.

    Every artifact/tuple/signature/fingerprint is produced by the imported
    ``group_authority`` primitives.  The private seed is used only to sign and
    to derive the public key for the out-of-band fingerprint; it is never
    written to disk.
    """

    active_groups = _load_active_group_sources(root, source_dir, principals_map)
    groups_jsonl = build_groups_jsonl(active_groups)
    principals_jsonl = build_principals_jsonl(list(principal_claims))
    audience_policy = build_audience_policy(private_group_uid=private_group_uid)
    manifest = build_artifact_manifest(
        {
            CORPUS_ARTIFACT: groups_jsonl,
            PRINCIPAL_ARTIFACT: principals_jsonl,
            AUDIENCE_POLICY_ARTIFACT: audience_policy,
        }
    )
    prev_sha = previous_envelope_sha256(prior_envelope)
    tuple_fields = build_authority_tuple(
        authority_uid=authority_uid,
        groups_jsonl=groups_jsonl,
        principals_jsonl=principals_jsonl,
        audience_policy_json=audience_policy,
        artifact_manifest_json=manifest,
        authority_generation=authority_generation,
        signing_key_uid=signing_key_uid,
        previous_envelope_sha256=prev_sha,
    )
    signature = sign_authority_tuple(tuple_fields, signing_seed)
    envelope = build_signed_envelope(tuple_fields, signature)
    envelope_bytes = canonical_envelope_bytes(envelope)

    public_key = public_key_base64(Ed25519PrivateKey.from_private_bytes(signing_seed).public_key())
    key_fingerprint = fingerprint(public_key)

    bundle_rel = out_dir if out_dir is not None else BUILD_DIR
    bundle_dir = root / bundle_rel
    _clear_dir(bundle_dir)
    _atomic_write_bytes(bundle_dir / CORPUS_ARTIFACT, groups_jsonl)
    _atomic_write_bytes(bundle_dir / PRINCIPAL_ARTIFACT, principals_jsonl)
    _atomic_write_bytes(bundle_dir / AUDIENCE_POLICY_ARTIFACT, audience_policy)
    _atomic_write_bytes(bundle_dir / ARTIFACT_MANIFEST_ARTIFACT, manifest)
    _atomic_write_bytes(bundle_dir / SIGNED_ENVELOPE_ARTIFACT, envelope_bytes)

    return BuildResult(
        authority_uid=tuple_fields["authority_uid"],
        authority_generation=tuple_fields["authority_generation"],
        signing_key_uid=tuple_fields["signing_key_uid"],
        corpus_sha256=tuple_fields["corpus_sha256"],
        corpus_revision=tuple_fields["corpus_revision"],
        principal_directory_sha256=tuple_fields["principal_directory_sha256"],
        principal_directory_revision=tuple_fields["principal_directory_revision"],
        audience_policy_sha256=tuple_fields["audience_policy_sha256"],
        artifact_identity=tuple_fields["artifact_identity"],
        previous_envelope_sha256=prev_sha,
        envelope_sha256=_digest_bytes(envelope_bytes),
        signature=signature,
        public_key=public_key,
        sha256_fingerprint=key_fingerprint,
        bundle_dir=bundle_rel,
    )


# --------------------------------------------------------------------------- #
# accept-fingerprint                                                           #
# --------------------------------------------------------------------------- #


def accept_fingerprint(
    root: Path,
    *,
    authority_uid: str,
    key_uid: str,
    public_key: str,
    expected_fingerprint: str,
    accepted_by: str,
    accepted_at: str,
) -> dict[str, Any]:
    """Record an accepted key iff the out-of-band fingerprint matches exactly."""

    with _authority_lock(root, timeout_seconds=60.0):
        trust = _load_trust(root)
        row = accept_authority_key(
            authority_uid=authority_uid,
            key_uid=key_uid,
            public_key_b64=public_key,
            expected_fingerprint=expected_fingerprint,
            accepted_by=accepted_by,
            accepted_at=accepted_at,
        )
        accepted = trust["accepted_keys"]
        status = "accepted"
        for index, existing in enumerate(accepted):
            if isinstance(existing, Mapping) and existing.get("authority_uid") == authority_uid and existing.get("key_uid") == key_uid:
                if existing.get("public_key") == public_key and existing.get("sha256_fingerprint") == row["sha256_fingerprint"]:
                    status = "already-accepted"
                    break
                _raise(
                    GroupErrorCode.AUTHORITY_UNTRUSTED,
                    f"key {key_uid} for authority {authority_uid} is already accepted with different material",
                    authority_uid=authority_uid,
                    key_uid=key_uid,
                )
        else:
            accepted.append(dict(row))
        _atomic_write_bytes(root / TRUST_RELATIVE, _trust_bytes(trust))
        return {
            "status": status,
            "authority_uid": authority_uid,
            "key_uid": key_uid,
            "sha256_fingerprint": row["sha256_fingerprint"],
            "trust_file": TRUST_RELATIVE,
        }


# --------------------------------------------------------------------------- #
# verify                                                                       #
# --------------------------------------------------------------------------- #


def verify_bundle(root: Path, *, bundle_dir: str, expected_fingerprint: str) -> dict[str, Any]:
    envelope, artifacts = _read_bundle(root / bundle_dir)
    trust = _load_trust(root)
    verified = verify_authority(
        signed_envelope=envelope,
        artifacts=artifacts,
        trust_record=trust,
        expected_fingerprint=expected_fingerprint,
    )
    return {
        "status": "verified",
        "authority_uid": verified.authority_uid,
        "authority_generation": verified.authority_generation,
        "corpus_revision": verified.corpus_revision,
        "corpus_sha256": verified.corpus_sha256,
        "principal_directory_revision": verified.principal_directory_revision,
        "audience_policy_sha256": verified.audience_policy_sha256,
        "artifact_identity": verified.artifact_identity,
        "signing_key_uid": verified.signing_key_uid,
        "envelope_sha256": verified.envelope_sha256,
    }


# --------------------------------------------------------------------------- #
# install                                                                      #
# --------------------------------------------------------------------------- #


def _installed_pin_bytes(verified, projection: RegistryProjection, envelope_bytes: bytes) -> bytes:
    pin = {
        "schema_id": INSTALLED_SCHEMA_ID,
        "authority_uid": verified.authority_uid,
        "authority_generation": verified.authority_generation,
        "corpus_revision": verified.corpus_revision,
        "corpus_sha256": verified.corpus_sha256,
        "principal_directory_revision": verified.principal_directory_revision,
        "principal_directory_sha256": verified.principal_directory_sha256,
        "audience_policy_sha256": verified.audience_policy_sha256,
        "artifact_identity": verified.artifact_identity,
        "previous_envelope_sha256": verified.previous_envelope_sha256,
        "canonicalization_version": verified.canonicalization_version,
        "signing_key_uid": verified.signing_key_uid,
        "signature": verified.signature,
        "envelope_sha256": verified.envelope_sha256,
        "registry_jsonl_sha256": projection.jsonl_sha256,
        "registry_row_count": projection.row_count,
        "registry_wrapper_sha256": projection.wrapper.wrapper_sha256,
        "registry_jsonl_path": PUBLISHED_REGISTRY_RELATIVE,
        "registry_sqlite_path": PUBLISHED_SQLITE_RELATIVE,
        "registry_wrapper_path": PUBLISHED_WRAPPER_RELATIVE,
        "generation_dir": f"{GENERATIONS_DIR}/{verified.authority_uid}/{verified.authority_generation}",
    }
    return _canonical_json_line(pin, sort_keys=True)


def install_authority_bundle(
    root: Path,
    *,
    bundle_dir: str,
    expected_fingerprint: str,
    source_dir: str = DEFAULT_SOURCE_DIR,
    lock_timeout: float = 60.0,
) -> dict[str, Any]:
    """Verify, enforce high-water/rollback, and publish under one journal."""

    with _authority_lock(root, timeout_seconds=lock_timeout):
        # (1) roll any prior incomplete install forward, or refuse.
        recovery = _recover_locked(root, verify_fn=lambda: None)

        envelope, artifacts = _read_bundle(root / bundle_dir)
        trust = _load_trust(root)
        verified = verify_authority(
            signed_envelope=envelope,
            artifacts=artifacts,
            trust_record=trust,
            expected_fingerprint=expected_fingerprint,
        )

        # (2) high-water / rollback decision -- delegated to the library.
        new_trust, status = install_authority(trust, verified, pending_recovery=False)

        # (3) project the revision-tagged registry from the signed corpus.
        projection, sqlite_bytes = _project_from_verified(verified, artifacts, source_dir)

        generation_rel = f"{GENERATIONS_DIR}/{verified.authority_uid}/{verified.authority_generation}"
        new_bytes: dict[str, bytes] = {
            "gen_groups": artifacts[CORPUS_ARTIFACT],
            "gen_principals": artifacts[PRINCIPAL_ARTIFACT],
            "gen_policy": artifacts[AUDIENCE_POLICY_ARTIFACT],
            "gen_manifest": artifacts[ARTIFACT_MANIFEST_ARTIFACT],
            "gen_envelope": envelope,
            "registry_jsonl": projection.jsonl_bytes,
            "registry_sqlite": sqlite_bytes,
            "registry_wrapper": projection.wrapper.canonical_bytes(),
            "installed_pin": _installed_pin_bytes(verified, projection, envelope),
            "trust": _trust_bytes(new_trust),
        }
        dest_paths: dict[str, str] = {
            "gen_groups": f"{generation_rel}/{CORPUS_ARTIFACT}",
            "gen_principals": f"{generation_rel}/{PRINCIPAL_ARTIFACT}",
            "gen_policy": f"{generation_rel}/{AUDIENCE_POLICY_ARTIFACT}",
            "gen_manifest": f"{generation_rel}/{ARTIFACT_MANIFEST_ARTIFACT}",
            "gen_envelope": f"{generation_rel}/{SIGNED_ENVELOPE_ARTIFACT}",
            "registry_jsonl": PUBLISHED_REGISTRY_RELATIVE,
            "registry_sqlite": PUBLISHED_SQLITE_RELATIVE,
            "registry_wrapper": PUBLISHED_WRAPPER_RELATIVE,
            "installed_pin": INSTALLED_RELATIVE,
            "trust": TRUST_RELATIVE,
        }
        plan = _build_plan(root, new_bytes, dest_paths)
        meta = {
            "authority_uid": verified.authority_uid,
            "authority_generation": verified.authority_generation,
            "envelope_sha256": verified.envelope_sha256,
        }
        _commit_plan(
            root,
            plan,
            new_bytes,
            meta,
            verify_fn=lambda: _verify_published_registry(root, projection),
        )

        return {
            "status": status.value if isinstance(status, InstallStatus) else str(status),
            "recovery": recovery.get("state", "none"),
            "authority_uid": verified.authority_uid,
            "authority_generation": verified.authority_generation,
            "corpus_revision": verified.corpus_revision,
            "corpus_sha256": verified.corpus_sha256,
            "principal_directory_revision": verified.principal_directory_revision,
            "envelope_sha256": verified.envelope_sha256,
            "registry_jsonl_sha256": projection.jsonl_sha256,
            "registry_row_count": projection.row_count,
            "registry_wrapper_sha256": projection.wrapper.wrapper_sha256,
            "generation_dir": generation_rel,
            "registry_jsonl_path": PUBLISHED_REGISTRY_RELATIVE,
            "high_water": {
                "authority_generation": verified.authority_generation,
                "envelope_sha256": verified.envelope_sha256,
            },
        }


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tropo-group-authority",
        description="Build, verify, accept, and install the authenticated group authority (B4a).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="derive + sign the authority artifacts (externally supplied key)")
    build.add_argument("--corpus-root", default=".")
    build.add_argument("--authority-uid", required=True)
    build.add_argument("--signing-key-uid", required=True)
    build.add_argument("--authority-generation", type=int, default=1)
    build.add_argument("--private-group-uid", required=True, help="Mike group UID for the legacy 'private' alias")
    build.add_argument("--signing-key-file", required=True, help="path to an externally supplied hex Ed25519 seed")
    build.add_argument("--principals-file", required=True, help="JSON list of portable principal claims (or UID->claim map)")
    build.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR)
    build.add_argument("--previous-envelope-file", default=None, help="prior signed envelope bytes for generation > 1")
    build.add_argument("--out-dir", default=None, help="bundle output dir (default machine-local build dir)")

    accept = sub.add_parser("accept-fingerprint", help="accept a signing key after an out-of-band fingerprint match")
    accept.add_argument("--corpus-root", default=".")
    accept.add_argument("--authority-uid", required=True)
    accept.add_argument("--key-uid", required=True)
    accept.add_argument("--public-key", required=True, help="base64 raw Ed25519 public key")
    accept.add_argument("--expected-fingerprint", required=True, help="the exact out-of-band SHA-256 fingerprint")
    accept.add_argument("--accepted-by", required=True, help="8-hex principal UID recording the acceptance")
    accept.add_argument("--accepted-at", required=True, help="acceptance timestamp")

    verify = sub.add_parser("verify", help="verify a signed envelope + artifacts against accepted trust")
    verify.add_argument("--corpus-root", default=".")
    verify.add_argument("--bundle-dir", default=BUILD_DIR)
    verify.add_argument("--expected-fingerprint", required=True)

    install = sub.add_parser("install", help="verify + publish under the high-water / rollback rules")
    install.add_argument("--corpus-root", default=".")
    install.add_argument("--bundle-dir", default=BUILD_DIR)
    install.add_argument("--expected-fingerprint", required=True)
    install.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR)

    return parser


def _emit(obj: Mapping[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    root = Path(args.corpus_root)
    try:
        if args.command == "build":
            claims, principals_map = _load_principal_claims(Path(args.principals_file))
            seed = _load_signing_seed(Path(args.signing_key_file))
            prior = None
            if args.previous_envelope_file:
                prior = _read_bytes(Path(args.previous_envelope_file))
                if prior is None:
                    raise AuthorityUsageError(f"previous envelope file not found: {args.previous_envelope_file}")
            result = build_authority(
                root,
                authority_uid=args.authority_uid,
                signing_key_uid=args.signing_key_uid,
                authority_generation=args.authority_generation,
                private_group_uid=args.private_group_uid,
                signing_seed=seed,
                principal_claims=claims,
                principals_map=principals_map,
                source_dir=args.source_dir,
                prior_envelope=prior,
                out_dir=args.out_dir,
            )
            _emit(result.to_dict())
            return 0

        if args.command == "accept-fingerprint":
            result = accept_fingerprint(
                root,
                authority_uid=args.authority_uid,
                key_uid=args.key_uid,
                public_key=args.public_key,
                expected_fingerprint=args.expected_fingerprint,
                accepted_by=args.accepted_by,
                accepted_at=args.accepted_at,
            )
            _emit(result)
            return 0

        if args.command == "verify":
            result = verify_bundle(root, bundle_dir=args.bundle_dir, expected_fingerprint=args.expected_fingerprint)
            _emit(result)
            return 0

        if args.command == "install":
            result = install_authority_bundle(
                root,
                bundle_dir=args.bundle_dir,
                expected_fingerprint=args.expected_fingerprint,
                source_dir=args.source_dir,
            )
            _emit(result)
            return 0

        parser.error(f"unknown command {args.command!r}")
        return 2
    except GroupContractError as error:
        _emit_error(error.code.value, error.message)
        return 3
    except AuthorityLockTimeout as error:
        _emit_error("AUTHORITY_LOCK_TIMEOUT", str(error))
        return 4
    except AuthorityUsageError as error:
        _emit_error("USAGE_ERROR", str(error))
        return 2


def _emit_error(code: str, message: str) -> None:
    print(json.dumps({"error": code, "message": message}, ensure_ascii=False), file=sys.stderr)


__all__ = [
    "AUTHORITY_DIR",
    "BUILD_DIR",
    "GENERATIONS_DIR",
    "INSTALLED_RELATIVE",
    "PUBLISHED_REGISTRY_RELATIVE",
    "PUBLISHED_SQLITE_RELATIVE",
    "PUBLISHED_WRAPPER_RELATIVE",
    "TRUST_RELATIVE",
    "AuthorityLockTimeout",
    "AuthorityUsageError",
    "BuildResult",
    "accept_fingerprint",
    "build_authority",
    "install_authority_bundle",
    "main",
    "verify_bundle",
]


if __name__ == "__main__":
    raise SystemExit(main())
