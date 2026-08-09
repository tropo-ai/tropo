"""ADR-047 Layer-1 current/archive index surface primitives.

The governed files remain canonical.  Both JSONL files are disposable
projections over the same records:

* ``00-index.jsonl`` contains current truth.
* ``00-archive-index.jsonl`` contains ``state: archived`` or
  ``status: superseded`` history.

Keep routing and union reads here so the full rebuild, incremental freshen,
retrieval tools, and validators cannot grow sibling predicates.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple, Optional, Sequence

import fcntl


CURRENT_INDEX_NAME = "00-index.jsonl"
ARCHIVE_INDEX_NAME = "00-archive-index.jsonl"
INDEX_LOCK_RELATIVE_PATH = Path(".tropo-studio") / "locks" / "index-write.lock"
INDEX_TRANSACTION_RELATIVE_PATH = (
    Path(".tropo-studio") / "locks" / "index-surfaces.transaction.json"
)
INDEX_SURFACE_META_RELATIVE_PATH = (
    Path(".tropo-studio") / "locks" / "index-surfaces.meta.json"
)
INDEX_RATCHET_RELATIVE_PATH = (
    Path(".tropo-studio") / "locks" / "index-surfaces.ratchet.json"
)
INDEX_TRANSACTION_COMPANION_RELATIVE_PATHS = {
    Path("vault") / "00-index.sqlite",
    Path(".tropo-studio") / "dirty-counter.json",
    Path(".tropo-studio") / "folder-mounts.json",
    Path(".tropo-studio") / "shards" / "local-archive-index.jsonl",
    Path(".tropo-studio") / "shards" / "local-archive-index.meta",
}
#: Per-machine record of legacy-digest-door use.  Sits beside the meta it
#: describes, under the same gitignored directory, because it describes THIS
#: machine's seal and nobody else's.
INDEX_LEGACY_DOOR_RELATIVE_PATH = (
    Path(".tropo-studio") / "locks" / "index-surfaces.legacy-door.json"
)
DEFAULT_MAX_SHRINK_FRACTION = 0.10
_PROCESS_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[Path, threading.Lock] = {}
_LOCK_LOCAL = threading.local()


class IndexLockTimeout(TimeoutError):
    """Another process held the index transaction lock past the safety bound."""


class IndexSurfaceRefusal(RuntimeError):
    """A derived index replacement failed a fail-closed safety precondition."""


class FullSourceDerivationProof(NamedTuple):
    """Replacement identity minted only after a complete source derivation."""

    current_sha256: str
    current_record_count: int
    archive_sha256: str
    archive_record_count: int
    source_inventory: tuple[tuple[str, str, str], ...]
    source_inventory_sha256: str
    derivation_provenance: "SurfaceDerivationProvenance"


class SurfaceDerivationProvenance(NamedTuple):
    """Exact, content-addressed inputs used to derive one surface pair."""

    current_sha256: str
    current_record_count: int
    archive_sha256: str
    archive_record_count: int
    manifest: tuple[tuple[str, str, str, str], ...]
    manifest_sha256: str
    source_paths: tuple[str, ...]
    uncommitted_inputs: tuple[tuple[str, str, str, str], ...]


class GovernedFloorRecovery(NamedTuple):
    """Explicit authority for restoring all lost cumulative-floor copies."""

    current_protected_record_count: int
    archive_protected_record_count: int
    evidence_uid: str


class GovernedShrinkAuthorization(NamedTuple):
    """Independent authorization and evidence for lowering a protected floor."""

    authorization_uid: str
    evidence_uid: str


class RecordRoutePlan(NamedTuple):
    """Strictly-read before/after state for one incremental cross-surface route."""

    uid: str
    target_name: str
    action: str
    current_path: Path
    archive_path: Path
    current_before: list[dict]
    archive_before: list[dict]
    current_after: list[dict]
    archive_after: list[dict]


class RecordBatchRoutePlan(NamedTuple):
    """Strictly-read before/after state for one multi-UID incremental route."""

    uids: tuple[str, ...]
    current_path: Path
    archive_path: Path
    current_before: list[dict]
    archive_before: list[dict]
    current_after: list[dict]
    archive_after: list[dict]
    destinations: tuple[tuple[str, str, str], ...]


class RecordRemovalPlan(NamedTuple):
    """Strictly-read before/after state for one incremental union removal."""

    uid: str
    current_path: Path
    archive_path: Path
    current_before: list[dict]
    archive_before: list[dict]
    current_after: list[dict]
    archive_after: list[dict]
    removed_from: list[str]


class RecordBatchRemovalPlan(NamedTuple):
    """Strictly-read before/after state for one multi-UID union removal."""

    uids: tuple[str, ...]
    current_path: Path
    archive_path: Path
    current_before: list[dict]
    archive_before: list[dict]
    current_after: list[dict]
    archive_after: list[dict]
    removed_from: tuple[tuple[str, tuple[str, ...]], ...]


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _process_lock(path: Path) -> threading.Lock:
    with _PROCESS_LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(path, threading.Lock())


@contextmanager
def index_write_lock(
    vault_root: Path,
    *,
    timeout_seconds: float = 60.0,
    recover: bool = True,
):
    """Serialize the complete cross-surface index mutation transaction.

    ``flock`` serializes processes; a clone-local mutex serializes threads.
    Re-entry by the owning thread is explicit so helpers can enforce the same
    canonical lock without deadlocking callers that already hold it.

    Mutating entries recover a prior interrupted transaction before yielding.
    Read-only entries set ``recover=False`` and refuse a pending transaction
    rather than writing during a query/dry-run.
    """
    vault_root = _resolved(vault_root)
    lock_path = vault_root / INDEX_LOCK_RELATIVE_PATH
    depths = getattr(_LOCK_LOCAL, "depths", None)
    if depths is None:
        depths = {}
        _LOCK_LOCAL.depths = depths
    if depths.get(lock_path, 0):
        depths[lock_path] += 1
        try:
            if recover:
                _recover_pending_pair_transaction(vault_root)
            else:
                _refuse_pending_pair_transaction(vault_root)
            yield lock_path
        finally:
            depths[lock_path] -= 1
        return

    process_lock = _process_lock(lock_path)
    if not process_lock.acquire(timeout=timeout_seconds):
        raise IndexLockTimeout(
            f"timed out after {timeout_seconds:.0f}s waiting for {lock_path}"
        )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    acquired = False
    try:
        handle = lock_path.open("a+", encoding="utf-8")
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise IndexLockTimeout(
                        f"timed out after {timeout_seconds:.0f}s waiting for {lock_path}"
                    )
                time.sleep(0.05)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid: {os.getpid()}\n")
        handle.flush()
        os.fsync(handle.fileno())
        depths[lock_path] = 1
        if recover:
            _recover_pending_pair_transaction(vault_root)
        else:
            _refuse_pending_pair_transaction(vault_root)
        yield lock_path
    finally:
        depths.pop(lock_path, None)
        if acquired:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        if handle is not None:
            handle.close()
        process_lock.release()


def is_archive_record(record: dict) -> bool:
    """Return the exact ADR-047 Layer-1 archive predicate."""
    return (
        record.get("state") == "archived"
        or record.get("status") == "superseded"
    )


def partition_records(records: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """Partition records losslessly into current and archive surfaces."""
    current: list[dict] = []
    archive: list[dict] = []
    for record in records:
        (archive if is_archive_record(record) else current).append(record)
    return current, archive


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield valid rows for legacy read-only consumers.

    Mutation, preflight, and union-requiring code must use
    :func:`read_jsonl_strict`; this tolerant iterator is intentionally unable
    to establish completeness.
    """
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def _infer_vault_root(paths: Sequence[Path]) -> Path:
    if not paths:
        raise ValueError("at least one index path is required")
    parents = [_resolved(path).parent for path in paths]
    common = Path(os.path.commonpath([str(parent) for parent in parents]))
    return common.parent if common.name == "vault" else common


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _source_inventory_sha256(
    source_inventory: Sequence[tuple[str, str, str]],
) -> str:
    return _sha256(
        "".join(
            f"{path}\0{mode}\0{blob_oid}\0"
            for path, mode, blob_oid in source_inventory
        ).encode("utf-8")
    )


def _validated_source_inventory(
    source_inventory: Iterable[tuple[str, str, str]],
) -> tuple[tuple[str, str, str], ...]:
    inventory = tuple(sorted(source_inventory))
    if len(set(inventory)) != len(inventory):
        raise IndexSurfaceRefusal(
            "REFUSAL: full source derivation inventory contains duplicate entries"
        )
    seen_paths: set[str] = set()
    for entry in inventory:
        if len(entry) != 3:
            raise IndexSurfaceRefusal(
                "REFUSAL: full source derivation inventory has a malformed entry"
            )
        path, mode, blob_oid = entry
        relative = Path(path)
        if (
            not path
            or relative.is_absolute()
            or ".." in relative.parts
            or path in seen_paths
            or mode not in {"100644", "100755", "120000"}
            or len(blob_oid) not in {40, 64}
            or any(char not in "0123456789abcdef" for char in blob_oid)
        ):
            raise IndexSurfaceRefusal(
                "REFUSAL: full source derivation inventory contains an unsafe "
                f"or invalid entry: {entry!r}"
            )
        seen_paths.add(path)
    return inventory


def _derivation_manifest_sha256(
    manifest: Sequence[tuple[str, str, str, str]],
) -> str:
    return _sha256(
        "".join(
            f"{kind}\0{path}\0{mode}\0{content_sha256}\0"
            for kind, path, mode, content_sha256 in manifest
        ).encode("utf-8")
    )


#: Validated-manifest memo. Small on purpose: within one operation there are
#: only ever one or two distinct manifests, and the cost being removed is
#: re-validating the SAME one dozens of times.
_VALIDATED_MANIFEST_MEMO: "dict[tuple, tuple]" = {}
_VALIDATED_MANIFEST_MEMO_MAX = 8


def _validated_derivation_manifest(
    manifest: Iterable[tuple[str, str, str, str]],
) -> tuple[tuple[str, str, str, str], ...]:
    """Validate a derivation manifest. Pure, and memoized because it is.

    MEASURED 2026-08-06 (metis-g103): a single `rebuild --only` called this
    **90 times** with **one** distinct manifest, walking all 6,248 entries and
    building ~715,000 Path objects each pass. The manifest cannot change during
    the call -- the write lock is held -- so every pass after the first is pure
    ceremony. Memoizing took a governed write from 3.50s to 2.46s.

    WHY THE FIRST TWO ATTEMPTS AT THIS BROKE, because the trap is subtle and
    the next person will hit it. Callers pass a GENERATOR EXPRESSION. My memo
    did `key = tuple(manifest)` to build the cache key, which CONSUMES the
    generator, and then called the real validator with the exhausted one -- so
    it validated an empty manifest and the caller refused with "forged or
    inconsistent parser-canonical manifest". The function was never the
    problem. Materialize FIRST, then use that tuple for both the key and the
    work, which is what this does.

    Only successes are cached: a raise must stay a raise on every call.
    """
    normalized = tuple(sorted(manifest))
    memoized = _VALIDATED_MANIFEST_MEMO.get(normalized)
    if memoized is not None:
        return memoized
    if len(set(normalized)) != len(normalized):
        raise IndexSurfaceRefusal(
            "REFUSAL: derivation manifest contains duplicate entries"
        )
    seen_keys: set[tuple[str, str]] = set()
    allowed_kinds = {
        "cache",
        "input",
        "mounted-record",
        "source",
        "source-absence",
        "symlink-target",
        "virtual",
    }
    allowed_modes = {"100644", "100755", "120000", "absent", "virtual"}
    for entry in normalized:
        if len(entry) != 4:
            raise IndexSurfaceRefusal(
                "REFUSAL: derivation manifest has a malformed entry"
            )
        kind, path, mode, content_sha256 = entry
        relative = Path(path)
        key = (kind, path)
        virtual_path = path.startswith("@")
        if (
            kind not in allowed_kinds
            or not path
            or (
                not virtual_path
                and (relative.is_absolute() or ".." in relative.parts)
            )
            or (virtual_path and kind not in {"mounted-record", "virtual"})
            or mode not in allowed_modes
            or len(content_sha256) != 64
            or any(char not in "0123456789abcdef" for char in content_sha256)
            or key in seen_keys
        ):
            raise IndexSurfaceRefusal(
                "REFUSAL: derivation manifest contains an unsafe or invalid "
                f"entry: {entry!r}"
            )
        seen_keys.add(key)
    # Cache only on success -- a manifest that fails validation must fail every
    # time it is presented, not once.
    if len(_VALIDATED_MANIFEST_MEMO) >= _VALIDATED_MANIFEST_MEMO_MAX:
        _VALIDATED_MANIFEST_MEMO.clear()
    _VALIDATED_MANIFEST_MEMO[normalized] = normalized
    return normalized


def _validated_uncommitted_inputs(
    entries: Iterable[tuple[str, str, str, str]],
) -> tuple[tuple[str, str, str, str], ...]:
    normalized = tuple(sorted(entries))
    seen_paths: set[str] = set()
    for entry in normalized:
        if len(entry) != 4:
            raise IndexSurfaceRefusal(
                "REFUSAL: uncommitted derivation provenance is malformed"
            )
        path, mode, content_sha256, symlink_target_sha256 = entry
        relative = Path(path)
        if (
            not path
            or relative.is_absolute()
            or ".." in relative.parts
            or path in seen_paths
            or mode not in {"100644", "100755", "120000", "absent"}
            or len(content_sha256) != 64
            or any(char not in "0123456789abcdef" for char in content_sha256)
            or (
                symlink_target_sha256
                and (
                    len(symlink_target_sha256) != 64
                    or any(
                        char not in "0123456789abcdef"
                        for char in symlink_target_sha256
                    )
                )
            )
        ):
            raise IndexSurfaceRefusal(
                "REFUSAL: uncommitted derivation provenance contains an "
                f"unsafe or invalid entry: {entry!r}"
            )
        seen_paths.add(path)
    return normalized


def prove_surface_derivation(
    current_records: Iterable[dict],
    archive_records: Iterable[dict],
    *,
    manifest: Iterable[tuple[str, str, str, str]],
    source_paths: Iterable[str],
    uncommitted_inputs: Iterable[tuple[str, str, str, str]] = (),
) -> SurfaceDerivationProvenance:
    """Bind exact content hashes—not source text—to one derived pair."""
    current_rows = list(current_records)
    archive_rows = list(archive_records)
    if not all(
        isinstance(row, dict) for row in (*current_rows, *archive_rows)
    ):
        raise IndexSurfaceRefusal(
            "REFUSAL: surface derivation contains a non-object row"
        )
    normalized_manifest = _validated_derivation_manifest(manifest)
    normalized_sources = tuple(sorted(set(source_paths)))
    for path in normalized_sources:
        relative = Path(path)
        if not path or relative.is_absolute() or ".." in relative.parts:
            raise IndexSurfaceRefusal(
                f"REFUSAL: derivation provenance has unsafe source path {path!r}"
            )
    normalized_uncommitted = _validated_uncommitted_inputs(
        uncommitted_inputs
    )
    manifest_source_paths = {
        path
        for kind, path, _mode, _sha256_value in normalized_manifest
        if kind in {"source", "source-absence"}
    }
    if not set(normalized_sources).issubset(manifest_source_paths):
        raise IndexSurfaceRefusal(
            "REFUSAL: derivation manifest omits a collected source path"
        )
    manifest_paths = {
        path for _kind, path, _mode, _sha256_value in normalized_manifest
    }
    if any(path not in manifest_paths for path, *_rest in normalized_uncommitted):
        raise IndexSurfaceRefusal(
            "REFUSAL: uncommitted provenance names an input absent from the "
            "derivation manifest"
        )
    current_raw = _encode_jsonl_rows(current_rows)
    archive_raw = _encode_jsonl_rows(archive_rows)
    return SurfaceDerivationProvenance(
        current_sha256=_sha256(current_raw),
        current_record_count=len(current_rows),
        archive_sha256=_sha256(archive_raw),
        archive_record_count=len(archive_rows),
        manifest=normalized_manifest,
        manifest_sha256=_derivation_manifest_sha256(normalized_manifest),
        source_paths=normalized_sources,
        uncommitted_inputs=normalized_uncommitted,
    )


def _provenance_matches_surface(
    provenance: Optional[SurfaceDerivationProvenance],
    path: Path,
    rows: list[dict],
) -> bool:
    if provenance is None:
        return False
    raw = _encode_jsonl_rows(rows)
    if path.name == CURRENT_INDEX_NAME:
        return (
            provenance.current_record_count == len(rows)
            and provenance.current_sha256 == _sha256(raw)
        )
    if path.name == ARCHIVE_INDEX_NAME:
        return (
            provenance.archive_record_count == len(rows)
            and provenance.archive_sha256 == _sha256(raw)
        )
    return False


def _has_valid_derivation_provenance(
    provenance: SurfaceDerivationProvenance,
) -> bool:
    try:
        manifest = _validated_derivation_manifest(provenance.manifest)
        uncommitted = _validated_uncommitted_inputs(
            provenance.uncommitted_inputs
        )
    except IndexSurfaceRefusal:
        return False
    return (
        manifest == provenance.manifest
        and uncommitted == provenance.uncommitted_inputs
        and provenance.manifest_sha256
        == _derivation_manifest_sha256(manifest)
        and tuple(sorted(set(provenance.source_paths)))
        == provenance.source_paths
    )


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _surface_meta_path_for(path: Path) -> Path:
    return _infer_vault_root([path]) / INDEX_SURFACE_META_RELATIVE_PATH


#: The `source-inventory` digest tag as it stood before 2dcadf62 widened the
#: branch from `schema_version == 2` to `in {2, 3}` and relabelled the tag. The
#: tag is the ONLY thing that changed — the bytes fed to the hash are otherwise
#: identical — so a meta sealed by the previous writer is a correct seal in an
#: older format, not a wrong one. Pinned as a literal rather than derived, so a
#: future tag change cannot silently widen what counts as "legacy".
_LEGACY_SOURCE_INVENTORY_TAG = "source-inventory-v2"

#: The dated close of the bootstrap door below (ADR-063 consequence 3).
#:
#: The door heals a machine automatically: the next ordinary full rebuild
#: re-stamps the seal in the current format, so an ACTIVE machine needs no
#: human action and no window at all.  The window exists only for machines
#: that are dark, so it is sized against absence rather than against work: one
#: full quarter from the 2026-07-31 ratification covers a paused project, a
#: laptop on leave, and a runner rebuilt from a cold cache.  A machine dark
#: longer than a quarter is being resurrected rather than recovering, and a
#: resurrection can afford one documented ``--apply --reconcile``.
#:
#: The ceiling matters as much as the floor.  ADR-063's stated failure mode is
#: a bootstrap becoming a format, and that happens when the window outlives the
#: crew that knows why the door is there.  A quarter is inside that memory, and
#: the close is not silent: on the day it lands, every machine that still needs
#: the door says so by name and prints the cure.
LEGACY_DIGEST_DOOR_SUNSET = datetime.date(2026, 10, 31)

#: The one command that re-stamps a superseded seal forward.  It is the
#: reconcile form deliberately: a meta the door no longer admits reads as
#: ``corrupt`` to the writer, and metadata recovery is authorized only by a
#: full source re-derivation, so a bare ``--apply`` would refuse again.  Naming
#: a command that does not cure is how an operator learns to stop reading the
#: cure line.
LEGACY_DIGEST_DOOR_CURE = (
    "python3 vault/tools/tropo-rebuild-index.py --apply --reconcile"
)


def _utc_today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


def legacy_digest_door_is_open() -> bool:
    """Is the pinned-prior-format bootstrap still admitting reads?

    One predicate, used by both the door and the instrument that reports on
    it.  Two predicates would let the report say "closed" on a day the door
    still opens, which is the ADR-063 defect (an instrument aimed one gate off
    from the mechanism it claims to measure) reintroduced in the reporting
    direction.
    """
    return _utc_today() < LEGACY_DIGEST_DOOR_SUNSET


def _note_legacy_digest_door_admission(meta_path: Path) -> None:
    """Record, on THIS machine, that the bootstrap door carried a real read.

    ``.tropo-studio/locks/`` is gitignored, so no machine's meta is visible to
    any other machine and there is no bus on which door use could be counted
    centrally.  What can be made observable is local: the door writes down that
    it fired, and :func:`legacy_digest_door_report` reads that back.

    Three properties this write must have, in order:

    * **Cold.** It sits inside the door's own branch, which is only reached
      when the current-format digest has already failed to match.  A machine
      whose seal is current pays nothing — not a stat, not a write.  Putting
      any of this on the matching path would be a write per surface read, in a
      library that read-only tools and validators import.
    * **Silent on failure.** A read must never fail because its own telemetry
      could not be written.  Read-only checkouts, a full disk, and a
      permission-stripped lock directory all leave the read succeeding and the
      count unchanged.
    * **Not authoritative.** The counter is advanced without the index write
      lock, so two concurrent readers can lose an increment.  It is reported as
      ``observed`` for that reason: a lower bound on door use, never a total.
      The load-bearing measurement is the live one in the report, which reads
      the seal itself.
    """
    log_path = meta_path.parent / INDEX_LEGACY_DOOR_RELATIVE_PATH.name
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    prior: dict = {}
    try:
        parsed = json.loads(log_path.read_bytes().decode("utf-8"))
        if isinstance(parsed, dict):
            prior = parsed
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        prior = {}
    observed = prior.get("admissions_observed")
    first_seen = prior.get("first_admitted_at")
    record = {
        "schema_version": 1,
        "legacy_tag": _LEGACY_SOURCE_INVENTORY_TAG,
        "sunset": LEGACY_DIGEST_DOOR_SUNSET.isoformat(),
        "cure": LEGACY_DIGEST_DOOR_CURE,
        "meta_path": str(meta_path),
        "first_admitted_at": (
            first_seen if isinstance(first_seen, str) else now
        ),
        "last_admitted_at": now,
        "admissions_observed": (
            observed if isinstance(observed, int) and observed >= 0 else 0
        ) + 1,
    }
    scratch = log_path.with_name(f"{log_path.name}.{os.getpid()}.tmp")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        scratch.write_bytes(_json_bytes(record))
        os.replace(scratch, log_path)
    except OSError:
        try:
            scratch.unlink()
        except OSError:
            pass


def _surface_meta_digest(data: dict, *, legacy_inventory_tag: bool = False) -> str:
    surfaces = data.get("surfaces")
    if not isinstance(surfaces, dict):
        raise ValueError("metadata has no surfaces")
    schema_version = data.get("schema_version")
    digest_parts: list[str] = []
    for name, entry in sorted(surfaces.items()):
        if not isinstance(name, str) or not isinstance(entry, dict):
            raise ValueError("metadata contains a malformed surface entry")
        if schema_version == 2:
            digest_parts.append(
                f"{name}\0{entry.get('sha256')}\0"
                f"{entry.get('record_count')}\0"
            )
        else:
            digest_parts.append(
                f"{name}\0{entry.get('sha256')}\0"
                f"{entry.get('record_count')}\0"
                f"{entry.get('protected_record_count')}\0"
            )
    if schema_version == 3:
        source_inventory = data.get("source_inventory")
        if source_inventory is None:
            digest_parts.append("source-inventory\0none\0")
        elif isinstance(source_inventory, dict):
            if source_inventory.get("schema_version") in {2, 3}:
                digest_parts.append(
                    (
                        f"{_LEGACY_SOURCE_INVENTORY_TAG}\0"
                        if legacy_inventory_tag
                        else "source-inventory-v2+\0"
                    )
                    + json.dumps(
                        source_inventory,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\0"
                )
                digest_parts.append(
                    "derived-from-uncommitted\0"
                    f"{data.get('derived_from_uncommitted')}\0"
                )
            else:
                digest_parts.append(
                    "source-inventory\0"
                    f"{source_inventory.get('sha256')}\0"
                    f"{source_inventory.get('tracked_source_count')}\0"
                )
        else:
            raise ValueError("metadata source inventory is malformed")
        metadata_recovery = data.get("metadata_recovery")
        if metadata_recovery is not None:
            if not isinstance(metadata_recovery, dict):
                raise ValueError("metadata recovery evidence is malformed")
            digest_parts.append(
                "metadata-recovery\0"
                + json.dumps(
                    metadata_recovery,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\0"
            )
    return _sha256("".join(digest_parts).encode("utf-8"))


def _validate_source_inventory_metadata(data: dict, label: str) -> None:
    source_inventory = data.get("source_inventory")
    if not isinstance(source_inventory, dict):
        return
    provenance_schema = source_inventory.get("schema_version")
    if provenance_schema not in {2, 3}:
        return
    uncommitted_raw = source_inventory.get("uncommitted_inputs")
    if not isinstance(uncommitted_raw, list):
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index provenance {label} omits exact "
            "uncommitted input evidence"
        )
    try:
        uncommitted = _validated_uncommitted_inputs(
            (
                str(entry["path"]),
                str(entry["mode"]),
                str(entry["content_sha256"]),
                str(entry.get("symlink_target_sha256") or ""),
            )
            for entry in uncommitted_raw
            if isinstance(entry, dict)
        )
    except (IndexSurfaceRefusal, KeyError, TypeError) as exc:
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index provenance {label} has malformed "
            "uncommitted input evidence"
        ) from exc
    derived_from_uncommitted = bool(uncommitted)
    authorities = source_inventory.get("authoritative_for")
    expected_authorities = {
        "federation": not derived_from_uncommitted,
        "local": True,
        "ratchet_baseline": not derived_from_uncommitted,
        "release": not derived_from_uncommitted,
    }
    if (
        len(uncommitted) != len(uncommitted_raw)
        or [
            {
                "content_sha256": content_sha256,
                "mode": mode,
                "path": path,
                "symlink_target_sha256": symlink_target_sha256 or None,
            }
            for path, mode, content_sha256, symlink_target_sha256 in uncommitted
        ]
        != uncommitted_raw
        or source_inventory.get("derived_from_uncommitted")
        is not derived_from_uncommitted
        or data.get("derived_from_uncommitted")
        is not derived_from_uncommitted
        or authorities != expected_authorities
        or not isinstance(source_inventory.get("manifest_entry_count"), int)
        or source_inventory["manifest_entry_count"] < 0
        or not isinstance(source_inventory.get("source_path_count"), int)
        or source_inventory["source_path_count"] < 0
    ):
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index provenance {label} has an omitted, "
            "forged, or inconsistent uncommitted marker"
        )
    if provenance_schema == 3:
        manifest_raw = source_inventory.get("manifest")
        if not isinstance(manifest_raw, list):
            raise IndexSurfaceRefusal(
                f"REFUSAL: trusted index provenance {label} omits the "
                "parser-canonical derivation manifest"
            )
        try:
            manifest = _validated_derivation_manifest(
                (
                    str(entry["kind"]),
                    str(entry["path"]),
                    str(entry["mode"]),
                    str(entry["content_sha256"]),
                )
                for entry in manifest_raw
                if isinstance(entry, dict)
            )
        except (IndexSurfaceRefusal, KeyError, TypeError) as exc:
            raise IndexSurfaceRefusal(
                f"REFUSAL: trusted index provenance {label} has a malformed "
                "parser-canonical derivation manifest"
            ) from exc
        expected_manifest = [
            {
                "content_sha256": content_sha256,
                "kind": kind,
                "mode": mode,
                "path": path,
            }
            for kind, path, mode, content_sha256 in manifest
        ]
        collected_paths = source_inventory.get("collected_source_paths")
        manifest_source_paths = {
            path
            for kind, path, _mode, _content_sha256 in manifest
            if kind in {"source", "source-absence"}
        }
        if (
            len(manifest) != len(manifest_raw)
            or expected_manifest != manifest_raw
            or source_inventory.get("manifest_entry_count") != len(manifest)
            or source_inventory.get("sha256")
            != _derivation_manifest_sha256(manifest)
            or not isinstance(collected_paths, list)
            or not all(isinstance(path, str) for path in collected_paths)
            or collected_paths != sorted(set(collected_paths))
            or any(
                Path(path).is_absolute()
                or ".." in Path(path).parts
                or path not in manifest_source_paths
                for path in collected_paths
            )
            or source_inventory.get("source_path_count")
            != len(collected_paths)
            or source_inventory.get("tracked_source_count")
            != len(collected_paths)
        ):
            raise IndexSurfaceRefusal(
                f"REFUSAL: trusted index provenance {label} has a forged or "
                "inconsistent parser-canonical manifest"
            )


#: Surface-metadata memo, keyed on the SHA-256 OF THE BYTES that were validated.
#: The key is the content itself, not a proxy for it, so "same key" and "same
#: bytes" are the same statement and a stale entry cannot be served. Successes
#: only.
_SURFACE_META_MEMO: "dict[str, dict]" = {}
_SURFACE_META_MEMO_MAX = 16


def _load_surface_meta(path: Path) -> Optional[dict]:
    """Read and validate one surface's trusted metadata. Memoized on content hash.

    MEASURED 2026-08-06 (metis-g103): a single `rebuild --only` called this 41
    times for the same file, and each call re-read it AND re-ran
    `_validate_source_inventory_metadata`, which walks every collected source
    path building two `Path` objects apiece -- 440,000 Path constructions per
    write. The write lock is held throughout, so the file cannot change under us.

    THE KEY IS A HASH OF THE BYTES, because the question the memo asks is "are
    these the same bytes I already validated" and only the bytes answer it.

    The original key was (st_dev, st_ino, st_size, st_mtime_ns), on the stated
    invariant that any write changes at least one of the four. It does not.
    ``pair_sha256`` is fixed-width, so swapping a digest -- a re-seal, or a
    corruption -- rewrites the file at IDENTICAL length; device and inode do not
    move either, leaving mtime as the sole discriminator, and mtime is quantised
    to ~4ms. Two writes inside one tick collided, and the second read was served
    from the cache unvalidated: measured 12/12 at 2KB-512KB and 6/12 on the live
    1.5MB seal (talos-t40, 2026-08-08). The one write the key could not see was
    the only write the seal exists to notice. A cache key that is a PROXY for
    identity has to be correct; a key that IS the identity cannot be wrong.

    Cost of soundness, measured on the live 1,562,880-byte seal: read + sha256
    is 0.906ms against 0.001ms for the bare stat and 28.6ms for a full cold
    revalidate (18.4ms of which is the source-inventory walk). Across
    metis-g103's 41 calls that is ~37ms instead of ~1,173ms -- 96.8% of the
    benefit, with the collision class removed rather than guarded.

    Note what this does NOT claim. ``pair_sha256`` is unkeyed, so it is a
    self-consistency and staleness checksum, never authentication (argus-a146,
    ruling on 39fe41c3; the same distinction A143 drew for T37). Hashing the
    bytes makes the memo tell the truth about what it validated. It does not
    make the seal a tamper seal, and nothing here should be read as saying so.

    Verified no caller mutates the returned dict; it is handed back by reference
    deliberately, because the manifest inside it can carry thousands of entries
    and copying it would reintroduce the cost being removed.

    Failures are never cached: corrupt metadata must refuse on every call.
    """
    meta_path = _surface_meta_path_for(path)
    if not meta_path.is_file():
        return None
    try:
        raw = meta_path.read_bytes()
    except OSError as exc:
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index-surface metadata {meta_path} is unreadable: {exc}"
        ) from exc
    memo_key = hashlib.sha256(raw).hexdigest()
    cached = _SURFACE_META_MEMO.get(memo_key)
    if cached is not None:
        return cached
    try:
        if not raw or not raw.endswith(b"\n"):
            raise ValueError("metadata is empty or lacks its writer newline")
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index-surface metadata {meta_path} is corrupt: {exc}"
        ) from exc
    if not isinstance(data, dict) or data.get("schema_version") not in {2, 3}:
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index-surface metadata {meta_path} has "
            "an unsupported shape"
        )
    surfaces = data.get("surfaces")
    if not isinstance(surfaces, dict):
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index-surface metadata {meta_path} has no surfaces"
        )
    for name, entry in sorted(surfaces.items()):
        if not isinstance(name, str) or not isinstance(entry, dict):
            raise IndexSurfaceRefusal(
                f"REFUSAL: trusted index-surface metadata {meta_path} "
                "contains a malformed surface entry"
            )
        if data["schema_version"] == 3:
            record_count = entry.get("record_count")
            protected_count = entry.get("protected_record_count")
            if (
                not isinstance(record_count, int)
                or not isinstance(protected_count, int)
                or record_count < 0
                or protected_count < record_count
            ):
                raise IndexSurfaceRefusal(
                    f"REFUSAL: trusted index-surface metadata {meta_path} "
                    "contains an invalid shrink ratchet"
                )
    if data["schema_version"] == 3:
        source_inventory = data.get("source_inventory")
        if source_inventory is not None and (
            not isinstance(source_inventory, dict)
            or not isinstance(source_inventory.get("sha256"), str)
            or len(source_inventory["sha256"]) != 64
            or not isinstance(
                source_inventory.get("tracked_source_count"),
                int,
            )
            or source_inventory["tracked_source_count"] < 0
        ):
            raise IndexSurfaceRefusal(
                f"REFUSAL: trusted index-surface metadata {meta_path} "
                "contains an invalid source inventory identity"
            )
        _validate_source_inventory_metadata(data, str(meta_path))
    expected_digest = data.get("pair_sha256")
    try:
        actual_digest = _surface_meta_digest(data)
    except ValueError as exc:
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index-surface metadata {meta_path} is malformed: "
            f"{exc}"
        ) from exc
    if not isinstance(expected_digest, str) or actual_digest != expected_digest:
        # Upgrade-day bootstrap. A meta sealed by the writer that shipped before
        # the digest tag changed is a VALID seal in a superseded format, and
        # refusing it deadlocks the Studio: every reader refuses, and the
        # rebuild that would re-stamp the meta is itself gated behind this same
        # check, so the only sanctioned repair path cannot run. Recognising one
        # pinned prior format costs no tamper resistance — a forger must still
        # produce a correct hash over the same bytes under a real algorithm,
        # which is exactly the work the current format demands. What stays
        # refused is what should: an absent digest, a malformed one, or one that
        # matches no format this writer has ever emitted.
        legacy_match = False
        if isinstance(expected_digest, str):
            try:
                legacy_match = expected_digest == _surface_meta_digest(
                    data, legacy_inventory_tag=True
                )
            except ValueError:
                legacy_match = False
        if not legacy_match:
            raise IndexSurfaceRefusal(
                f"REFUSAL: trusted index-surface metadata {meta_path} "
                "has a pair digest mismatch"
            )
        # The dated close. A bootstrap with no end date is a format, so the
        # door stops admitting on LEGACY_DIGEST_DOOR_SUNSET and says exactly
        # what to run. The refusal is deliberately NOT the "pair digest
        # mismatch" text: this meta is a correct seal in a known superseded
        # format, and telling the operator it is corrupt would send them
        # looking for damage that is not there.
        if not legacy_digest_door_is_open():
            raise IndexSurfaceRefusal(
                f"REFUSAL: trusted index-surface metadata {meta_path} is "
                f"sealed in the superseded {_LEGACY_SOURCE_INVENTORY_TAG} "
                "digest format, and the bootstrap that admitted it closed on "
                f"{LEGACY_DIGEST_DOOR_SUNSET.isoformat()}. Re-stamp the seal "
                f"forward: {LEGACY_DIGEST_DOOR_CURE}"
            )
        _note_legacy_digest_door_admission(meta_path)
        # NOT MEMOIZED ON THIS BRANCH, and this is the interesting half.
        #
        # This function is not pure: the legacy-digest door RECORDS each
        # admission so its use can be counted later. A cache hit skips that
        # side effect, so admissions stop being counted -- caught immediately by
        # test_the_door_records_its_own_use_so_it_can_be_counted_later, which
        # went 2 -> 1. Every seal in the superseded digest format therefore
        # takes the slow path deliberately; it is a bootstrap branch with a
        # dated sunset, not the steady state, and counting it correctly is the
        # entire reason it exists. (metis-g103 2026-08-06)
        return data
    # Success only, and only on the pure branch. Every raise above must raise
    # again on the next call.
    if len(_SURFACE_META_MEMO) >= _SURFACE_META_MEMO_MAX:
        _SURFACE_META_MEMO.clear()
    _SURFACE_META_MEMO[memo_key] = data
    return data


def legacy_digest_door_report(vault_root: Path) -> dict:
    """Does THIS machine still need the legacy digest door?

    ADR-063 owes an instrument that reports how many metas still need the
    door, so the door can be closed on evidence rather than on a guess.  The
    obvious shape — count them centrally — cannot be built: the meta lives
    under gitignored ``.tropo-studio/locks/``, is written per machine, and is
    never pushed.  There is no bus.  What exists instead is this: a reading any
    machine can take of itself, cheap enough to hang off every liveness run, so
    the crew's count is the union of reported readings and a machine that has
    not reported is visibly absent rather than silently counted as clean.

    The reading is LIVE.  It re-derives both digests from the seal on disk
    rather than trusting the admission log, because a log can be stale (the
    machine healed since), absent (the door has not fired yet on a meta that
    still needs it), or lost (the directory it lives in is disposable).  An
    instrument that reports "clean" from missing data is the exact failure
    ADR-063 is a case of.

    It also aims at the digest specifically, and not through
    :func:`_load_surface_meta`, for the same reason ADR-063 exists: that
    function refuses at the shrink ratchet before the digest branch, so asking
    it would answer a different question on a meta that fails both — and after
    the sunset it refuses on the door itself, which would make the instrument
    go blind on precisely the machines it is there to find.

    ``needs_door`` is deliberately three-valued.  ``True``/``False`` answer
    "would closing the door change this machine's verdict"; ``None`` means the
    seal could not be read, which is an unknown and must never be summed as a
    zero.
    """
    meta_path = vault_root / INDEX_SURFACE_META_RELATIVE_PATH
    log_path = vault_root / INDEX_LEGACY_DOOR_RELATIVE_PATH
    today = _utc_today()
    door_open = legacy_digest_door_is_open()
    report: dict = {
        "schema_version": 1,
        "legacy_tag": _LEGACY_SOURCE_INVENTORY_TAG,
        "sunset": LEGACY_DIGEST_DOOR_SUNSET.isoformat(),
        "today": today.isoformat(),
        "door_open": door_open,
        "days_until_sunset": (LEGACY_DIGEST_DOOR_SUNSET - today).days,
        "cure": LEGACY_DIGEST_DOOR_CURE,
        "meta_path": INDEX_SURFACE_META_RELATIVE_PATH.as_posix(),
        "meta_present": meta_path.is_file(),
    }
    if not report["meta_present"]:
        report.update({
            "verdict": "no-meta",
            "needs_door": False,
            "reason": (
                "this machine holds no trusted index-surface seal at all, so "
                "there is nothing for the door to carry; the next rebuild "
                "will stamp one in the current format"
            ),
        })
    else:
        try:
            data = json.loads(meta_path.read_bytes().decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("metadata is not a JSON object")
            sealed = data.get("pair_sha256")
            current_digest = _surface_meta_digest(data)
            legacy_digest = _surface_meta_digest(
                data, legacy_inventory_tag=True
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            report.update({
                "verdict": "unreadable-meta",
                "needs_door": None,
                "reason": (
                    "this machine's seal could not be read or digested "
                    f"({exc}), so whether the door is carrying it is UNKNOWN "
                    "— do not count this machine as clear"
                ),
            })
        else:
            report["seal_matches_current_format"] = sealed == current_digest
            report["seal_matches_legacy_format"] = sealed == legacy_digest
            # False for a schema-2 meta and for any schema-3 meta with no
            # tagged source inventory: the two formats hash identically there,
            # so the door is unreachable for this seal by construction rather
            # than by luck. Reported so a `False` verdict can be told apart
            # from one taken on a meta that could actually have differed.
            report["formats_are_distinguishable"] = (
                current_digest != legacy_digest
            )
            if sealed == current_digest:
                report.update({
                    "verdict": "current-sealed",
                    "needs_door": False,
                    "reason": (
                        "the seal verifies under the current digest format; "
                        "the door is not load-bearing on this machine"
                    ),
                })
            elif sealed == legacy_digest:
                report.update({
                    "verdict": "legacy-sealed",
                    "needs_door": True,
                    "reason": (
                        "the seal verifies ONLY under the superseded "
                        f"{_LEGACY_SOURCE_INVENTORY_TAG} format; removing the "
                        "door today would deadlock this machine's index"
                    ),
                })
            else:
                report.update({
                    "verdict": "unrecognised-seal",
                    "needs_door": False,
                    "reason": (
                        "the seal matches no format this writer has ever "
                        "emitted, so it is refused with the door and without "
                        "it; this machine is broken in a different way"
                    ),
                })

    admissions: dict = {
        "log_path": INDEX_LEGACY_DOOR_RELATIVE_PATH.as_posix(),
        "log_present": log_path.is_file(),
        "observed": 0,
        "first_admitted_at": None,
        "last_admitted_at": None,
        "note": (
            "a local LOWER BOUND on door use, not a total: the log lives in a "
            "gitignored, disposable directory and is advanced outside the "
            "index write lock"
        ),
    }
    if admissions["log_present"]:
        try:
            logged = json.loads(log_path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            logged = None
        if isinstance(logged, dict):
            observed = logged.get("admissions_observed")
            if isinstance(observed, int) and observed >= 0:
                admissions["observed"] = observed
            for key in ("first_admitted_at", "last_admitted_at"):
                if isinstance(logged.get(key), str):
                    admissions[key] = logged[key]
        else:
            admissions["unreadable"] = True
    report["admissions"] = admissions
    report["stranded"] = report["needs_door"] is True and not door_open
    return report


def _ratchet_evidence_digest(data: dict) -> str:
    payload = {
        key: value
        for key, value in data.items()
        if key != "evidence_sha256"
    }
    return _sha256(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _validate_ratchet_evidence(data: object, label: str) -> dict:
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("generation"), int)
        or data["generation"] < 1
        or not isinstance(data.get("recovery_count"), int)
        or data["recovery_count"] < 0
        or not isinstance(data.get("surface_meta_pair_sha256"), str)
        or len(data["surface_meta_pair_sha256"]) != 64
    ):
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index ratchet evidence {label} has "
            "an unsupported shape"
        )
    surfaces = data.get("surfaces")
    if (
        not isinstance(surfaces, dict)
        or set(surfaces) != {CURRENT_INDEX_NAME, ARCHIVE_INDEX_NAME}
    ):
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index ratchet evidence {label} does "
            "not cover exactly the canonical surface pair"
        )
    for name, entry in sorted(surfaces.items()):
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("sha256"), str)
            or len(entry["sha256"]) != 64
            or not isinstance(entry.get("record_count"), int)
            or not isinstance(entry.get("protected_record_count"), int)
            or entry["record_count"] < 0
            or entry["protected_record_count"] < entry["record_count"]
        ):
            raise IndexSurfaceRefusal(
                f"REFUSAL: trusted index ratchet evidence {label} "
                f"contains an invalid {name} floor"
            )
    source_inventory = data.get("source_inventory")
    if isinstance(source_inventory, dict) and (
        source_inventory.get("schema_version") in {2, 3}
    ):
        _validate_source_inventory_metadata(
            {
                "source_inventory": source_inventory,
                "derived_from_uncommitted": source_inventory.get(
                    "derived_from_uncommitted"
                ),
            },
            label,
        )
    expected_digest = data.get("evidence_sha256")
    actual_digest = _ratchet_evidence_digest(data)
    if not isinstance(expected_digest, str) or expected_digest != actual_digest:
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index ratchet evidence {label} has "
            "a digest mismatch"
        )
    return data


def _load_ratchet_evidence(vault_root: Path) -> Optional[dict]:
    """Load the independently duplicated cumulative-floor evidence."""
    evidence_path = _resolved(vault_root) / INDEX_RATCHET_RELATIVE_PATH
    if not evidence_path.is_file():
        return None
    try:
        raw = evidence_path.read_bytes()
        if not raw or not raw.endswith(b"\n"):
            raise ValueError("evidence is empty or lacks its writer newline")
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted index ratchet evidence {evidence_path} is "
            f"corrupt: {exc}"
        ) from exc
    return _validate_ratchet_evidence(data, str(evidence_path))


def _load_sqlite_ratchet_evidence(vault_root: Path) -> Optional[dict]:
    """Read the third floor copy from the live SQLite projection, read-only."""
    sqlite_path = _resolved(vault_root) / "vault" / "00-index.sqlite"
    if not sqlite_path.is_file():
        return None
    connection = None
    try:
        connection = sqlite3.connect(
            f"{sqlite_path.as_uri()}?mode=ro&immutable=1",
            uri=True,
        )
        connection.execute("PRAGMA query_only=ON")
        table = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='index_ratchet_metadata'"
        ).fetchone()
        if table is None:
            return None
        row = connection.execute(
            "SELECT evidence_json FROM index_ratchet_metadata "
            "WHERE singleton = 1"
        ).fetchone()
        if row is None or not isinstance(row[0], str):
            raise ValueError("metadata table has no singleton evidence row")
        data = json.loads(row[0])
    except (OSError, sqlite3.Error, json.JSONDecodeError, ValueError) as exc:
        raise IndexSurfaceRefusal(
            f"REFUSAL: trusted SQLite ratchet evidence {sqlite_path} is "
            f"unreadable: {exc}"
        ) from exc
    finally:
        if connection is not None:
            connection.close()
    return _validate_ratchet_evidence(
        data,
        f"{sqlite_path}::index_ratchet_metadata",
    )


def _verify_surface_metadata(path: Path, raw: bytes) -> None:
    """Verify pair metadata when present; require it for an empty surface."""
    is_index_surface = path.name in {CURRENT_INDEX_NAME, ARCHIVE_INDEX_NAME}
    if not is_index_surface:
        if not raw:
            raise IndexSurfaceRefusal(
                f"REFUSAL: empty JSONL {path} has no trusted empty-output metadata"
            )
        return

    meta = _load_surface_meta(path)
    entry = None
    if meta is not None:
        entry = meta["surfaces"].get(path.name)
        if not isinstance(entry, dict):
            raise IndexSurfaceRefusal(
                f"REFUSAL: trusted index-surface metadata does not cover {path}"
            )
        actual_hash = _sha256(raw)
        if (
            entry.get("sha256") != actual_hash
            or not isinstance(entry.get("record_count"), int)
        ):
            raise IndexSurfaceRefusal(
                f"REFUSAL: {path} does not match trusted index-surface metadata"
            )

    has_json_content = any(line.strip() for line in raw.splitlines())
    if not has_json_content and (
        entry is None
        or entry.get("record_count") != 0
        or entry.get("sha256") != _sha256(raw)
    ):
        raise IndexSurfaceRefusal(
            f"REFUSAL: {path} is empty/newline-only without trusted metadata "
            "proving a legitimate zero-row output"
        )


def read_jsonl_strict(
    path: Path,
    *,
    verify_surface_metadata: bool = True,
) -> list[dict]:
    """Read one complete JSONL surface or refuse the whole input.

    ``iter_jsonl`` is intentionally tolerant for legacy query consumers.  A
    writer must not use that tolerance: treating one truncated/corrupt row as
    absent turns a damaged surface into an apparently legitimate shrink.

    A full source-complete rebuild may set ``verify_surface_metadata=False``
    while assessing the replaceable before-image.  This keeps JSONL syntax,
    object-shape, and final-newline checks strict while allowing that named
    repair operation to replace stale pair metadata.  Incremental mutations
    and ordinary readers must retain the default.
    """
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise IndexSurfaceRefusal(
            f"REFUSAL: existing index surface {path} is unreadable: {exc}"
        ) from exc
    if raw_bytes and not raw_bytes.endswith(b"\n"):
        raise IndexSurfaceRefusal(
            f"REFUSAL: {path} is truncated (non-empty JSONL lacks final newline)"
        )
    if verify_surface_metadata:
        _verify_surface_metadata(path, raw_bytes)
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise IndexSurfaceRefusal(
            f"REFUSAL: existing index surface {path} is unreadable: {exc}"
        ) from exc

    records: list[dict] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IndexSurfaceRefusal(
                f"REFUSAL: {path} is not valid JSONL at line "
                f"{line_number}: {exc.msg}"
            ) from exc
        if not isinstance(record, dict):
            raise IndexSurfaceRefusal(
                f"REFUSAL: {path} line {line_number} is "
                f"{type(record).__name__}, not a JSON object"
            )
        records.append(record)
    meta = _load_surface_meta(path) if verify_surface_metadata and path.name in {
        CURRENT_INDEX_NAME,
        ARCHIVE_INDEX_NAME,
    } else None
    if meta is not None:
        entry = meta["surfaces"][path.name]
        if (
            meta.get("schema_version") != 2
            and entry.get("record_count") != len(records)
        ):
            raise IndexSurfaceRefusal(
                f"REFUSAL: {path} row count does not match trusted "
                "index-surface metadata"
            )
    return records


def load_index_records(
    vault_root: Path,
    *,
    include_archive: bool = False,
    require_complete_union: bool = False,
    require_authoritative: bool = False,
    authority_purpose: str = "release",
) -> list[dict]:
    """Load current records, optionally unioning the opt-in archive surface.

    The compatibility default is a tolerant read for retrieval and diagnostic
    consumers: missing surfaces and malformed rows are skipped as before
    ADR-047 lifecycle hardening. Governance mutations and invariants that must
    prove a complete current+archive input opt into ``require_complete_union``;
    that mode requires both files and parses every row strictly under the index
    lock.

    Current rows win on an impossible cross-surface duplicate so a malformed
    projection cannot make one UID appear twice to a consumer.  The validator
    separately plants and reports that invariant.
    """
    if require_complete_union and not include_archive:
        raise ValueError(
            "require_complete_union=True requires include_archive=True"
        )
    if require_authoritative and (
        not include_archive or not require_complete_union
    ):
        raise ValueError(
            "require_authoritative=True requires include_archive=True and "
            "require_complete_union=True"
        )
    if authority_purpose not in {"federation", "ratchet_baseline", "release"}:
        raise ValueError(
            "authority_purpose must be release, federation, or "
            "ratchet_baseline"
        )
    vault_root = _resolved(vault_root)
    vault_dir = vault_root / "vault"
    paths = [vault_dir / CURRENT_INDEX_NAME]
    if include_archive:
        paths.append(vault_dir / ARCHIVE_INDEX_NAME)

    def collect(reader) -> list[dict]:
        records: list[dict] = []
        seen: set[str] = set()
        for path in paths:
            for record in reader(path):
                uid = record.get("uid")
                if uid and uid in seen:
                    continue
                if uid:
                    seen.add(uid)
                records.append(record)
        return records

    if require_complete_union:
        with index_write_lock(vault_root, recover=False):
            for path in paths:
                if not path.is_file():
                    raise IndexSurfaceRefusal(
                        "REFUSAL: required current + archive union surface "
                        f"{path} is missing"
                    )
            records = collect(read_jsonl_strict)
            if require_authoritative:
                meta = _load_surface_meta(paths[0])
                source_inventory = (
                    meta.get("source_inventory")
                    if isinstance(meta, dict)
                    else None
                )
                authorities = (
                    source_inventory.get("authoritative_for")
                    if isinstance(source_inventory, dict)
                    else None
                )
                if (
                    not isinstance(source_inventory, dict)
                    or source_inventory.get("schema_version") != 3
                    or source_inventory.get("derived_from_uncommitted")
                    is not False
                    or not isinstance(authorities, dict)
                    or authorities.get(authority_purpose) is not True
                ):
                    raise IndexSurfaceRefusal(
                        "REFUSAL: authority consumer requires an "
                        "authoritative clean-tree index surface; trusted "
                        f"provenance does not authorize {authority_purpose}"
                    )
                for evidence_name, evidence in (
                    ("ratchet", _load_ratchet_evidence(vault_root)),
                    ("SQLite", _load_sqlite_ratchet_evidence(vault_root)),
                ):
                    if (
                        not isinstance(evidence, dict)
                        or evidence.get("source_inventory")
                        != source_inventory
                    ):
                        raise IndexSurfaceRefusal(
                            "REFUSAL: authority consumer requires matching "
                            "transaction-bound provenance in sidecar, ratchet, "
                            f"and SQLite; {evidence_name} evidence disagrees"
                        )
            return records

    return collect(iter_jsonl)


def load_trusted_derivation_manifest(
    vault_root: Path,
) -> tuple[tuple[str, str, str, str], ...]:
    """Load the transaction-bound parser-canonical manifest for incrementals."""
    vault_root = _resolved(vault_root)
    paths = (
        vault_root / "vault" / CURRENT_INDEX_NAME,
        vault_root / "vault" / ARCHIVE_INDEX_NAME,
    )
    with index_write_lock(vault_root, recover=False):
        for path in paths:
            if not path.is_file():
                raise IndexSurfaceRefusal(
                    "REFUSAL: incremental authority requires both canonical "
                    "index surfaces; run a full --apply"
                )
            read_jsonl_strict(path)
        meta = _load_surface_meta(paths[0])
        source_inventory = (
            meta.get("source_inventory")
            if isinstance(meta, dict)
            else None
        )
        if (
            not isinstance(source_inventory, dict)
            or source_inventory.get("schema_version") != 3
            or not isinstance(source_inventory.get("manifest"), list)
        ):
            raise IndexSurfaceRefusal(
                "REFUSAL: prior trusted parser-canonical source manifest is "
                "absent; run a full --apply before --only/--remove"
            )
        # _load_surface_meta validated shape, ordering, digest, and pair binding.
        return tuple(
            (
                entry["kind"],
                entry["path"],
                entry["mode"],
                entry["content_sha256"],
            )
            for entry in source_inventory["manifest"]
        )


def trusted_index_provenance_schema(vault_root: Path) -> int:
    """Return verified provenance generation, or 0 when metadata is absent."""
    vault_root = _resolved(vault_root)
    paths = (
        vault_root / "vault" / CURRENT_INDEX_NAME,
        vault_root / "vault" / ARCHIVE_INDEX_NAME,
    )
    with index_write_lock(vault_root, recover=False):
        for path in paths:
            if not path.is_file():
                raise IndexSurfaceRefusal(
                    "REFUSAL: incremental authority requires both canonical "
                    "index surfaces; run a full --apply"
                )
            read_jsonl_strict(path)
        meta = _load_surface_meta(paths[0])
        if not isinstance(meta, dict):
            return 0
        source_inventory = meta.get("source_inventory")
        if (
            meta.get("schema_version") == 3
            and isinstance(source_inventory, dict)
            and source_inventory.get("schema_version") == 3
        ):
            return 3
        if meta.get("schema_version") == 2:
            return 2
        if meta.get("schema_version") == 3:
            # Early schema3 sidecars can predate the global path manifest.
            # They require the same full bootstrap as schema2; cleanliness
            # alone cannot prove every prior row is current.
            return 2
        raise IndexSurfaceRefusal(
            "REFUSAL: trusted index provenance generation is unsupported; "
            "run a full --apply"
        )


def prove_full_source_derivation(
    current_records: Iterable[dict],
    archive_records: Iterable[dict],
    *,
    source_complete: bool,
    source_inventory: Iterable[tuple[str, str, str]],
    derivation_provenance: Optional[SurfaceDerivationProvenance] = None,
) -> FullSourceDerivationProof:
    """Bind a canonical pair to an explicitly source-complete derivation.

    The caller may assert ``source_complete`` only after proving that no local
    archive source or mounted source was skipped/reused, no parse failed, and
    every expected canonical source has an exact path/mode/content identity.
    Pair writers verify that inventory digest, the complete derivation
    manifest, and both proposed byte images.  The proof is therefore
    unavailable to a partial/cache-backed or truncated-tree incident that
    would otherwise mint trusted metadata for an accidental empty archive.
    """
    if not source_complete:
        raise IndexSurfaceRefusal(
            "REFUSAL: cannot prove an index replacement from a partial, "
            "cache-backed, skipped, or parse-failed derivation"
        )
    current_rows = list(current_records)
    archive_rows = list(archive_records)
    inventory = _validated_source_inventory(source_inventory)
    if not all(
        isinstance(row, dict) for row in (*current_rows, *archive_rows)
    ):
        raise IndexSurfaceRefusal(
            "REFUSAL: full source derivation contains a non-object row"
        )
    local_rows = [
        row
        for row in (*current_rows, *archive_rows)
        if not str(row.get("path") or "").startswith("mounted/")
    ]
    if local_rows and not inventory:
        raise IndexSurfaceRefusal(
            "REFUSAL: a non-empty full source derivation requires an exact "
            "source inventory"
        )
    current_raw = _encode_jsonl_rows(current_rows)
    archive_raw = _encode_jsonl_rows(archive_rows)
    if derivation_provenance is None:
        derivation_provenance = prove_surface_derivation(
            current_rows,
            archive_rows,
            manifest=(
                (
                    "source",
                    path,
                    mode,
                    (
                        blob_oid
                        if len(blob_oid) == 64
                        else _sha256(blob_oid.encode("ascii"))
                    ),
                )
                for path, mode, blob_oid in inventory
            ),
            source_paths=(path for path, _mode, _oid in inventory),
        )
    if (
        not _has_valid_derivation_provenance(derivation_provenance)
        or not all(
            _provenance_matches_surface(
                derivation_provenance,
                path,
                rows,
            )
            for path, rows in (
                (Path(CURRENT_INDEX_NAME), current_rows),
                (Path(ARCHIVE_INDEX_NAME), archive_rows),
            )
        )
    ):
        raise IndexSurfaceRefusal(
            "REFUSAL: full source proof does not match its exact derivation "
            "manifest and proposed surface bytes"
        )
    return FullSourceDerivationProof(
        current_sha256=_sha256(current_raw),
        current_record_count=len(current_rows),
        archive_sha256=_sha256(archive_raw),
        archive_record_count=len(archive_rows),
        source_inventory=inventory,
        source_inventory_sha256=_source_inventory_sha256(inventory),
        derivation_provenance=derivation_provenance,
    )


def _proof_matches_surface(
    proof: Optional[FullSourceDerivationProof],
    path: Path,
    rows: list[dict],
) -> bool:
    if proof is None:
        return False
    raw = _encode_jsonl_rows(rows)
    if path.name == CURRENT_INDEX_NAME:
        return (
            proof.current_record_count == len(rows)
            and proof.current_sha256 == _sha256(raw)
        )
    if path.name == ARCHIVE_INDEX_NAME:
        return (
            proof.archive_record_count == len(rows)
            and proof.archive_sha256 == _sha256(raw)
        )
    return False


def _proof_has_valid_source_inventory(
    proof: FullSourceDerivationProof,
) -> bool:
    try:
        inventory = _validated_source_inventory(proof.source_inventory)
    except IndexSurfaceRefusal:
        return False
    return (
        inventory == proof.source_inventory
        and proof.source_inventory_sha256
        == _source_inventory_sha256(inventory)
        and _has_valid_derivation_provenance(
            proof.derivation_provenance
        )
        and proof.current_sha256
        == proof.derivation_provenance.current_sha256
        and proof.current_record_count
        == proof.derivation_provenance.current_record_count
        and proof.archive_sha256
        == proof.derivation_provenance.archive_sha256
        and proof.archive_record_count
        == proof.derivation_provenance.archive_record_count
    )


def preflight_jsonl_replacement(
    path: Path,
    records: Iterable[dict],
    *,
    max_shrink_fraction: float = DEFAULT_MAX_SHRINK_FRACTION,
    allow_shrink: bool = False,
    full_source_derivation_proof: Optional[FullSourceDerivationProof] = None,
    protected_record_count: Optional[int] = None,
    allow_surface_metadata_recovery: bool = False,
) -> list[dict]:
    """Materialize and validate one proposed replacement without writing.

    Existing content is parsed strictly before its row count can establish the
    shrink floor.  A corrupt/truncated surface is therefore a refusal, never an
    implicit zero-row baseline.
    """
    if not 0.0 <= max_shrink_fraction <= 1.0:
        raise ValueError("max_shrink_fraction must be between 0.0 and 1.0")
    rows = list(records)
    if not all(isinstance(row, dict) for row in rows):
        raise IndexSurfaceRefusal(
            f"REFUSAL: proposed replacement for {path} contains a non-object row"
        )
    canonical_surface = path.name in {
        CURRENT_INDEX_NAME,
        ARCHIVE_INDEX_NAME,
    }
    proof_matches = _proof_matches_surface(
        full_source_derivation_proof,
        path,
        rows,
    )
    if (
        full_source_derivation_proof is not None
        and not _proof_has_valid_source_inventory(full_source_derivation_proof)
    ):
        raise IndexSurfaceRefusal(
            "REFUSAL: full source derivation proof has an invalid tracked "
            "source inventory"
        )
    if full_source_derivation_proof is not None and canonical_surface:
        if not proof_matches:
            raise IndexSurfaceRefusal(
                f"REFUSAL: full source derivation proof does not match {path.name}"
            )
    if not path.exists():
        if canonical_surface and not proof_matches:
            raise IndexSurfaceRefusal(
                f"REFUSAL: canonical index surface {path} is absent; creation "
                "requires a matching full source-complete derivation proof"
            )
        return rows

    existing_count = len(read_jsonl_strict(
        path,
        verify_surface_metadata=not proof_matches,
    ))
    if protected_record_count is None and canonical_surface:
        try:
            meta = _load_surface_meta(path)
        except IndexSurfaceRefusal:
            if not (allow_surface_metadata_recovery and proof_matches):
                raise
            meta = None
        if meta is not None:
            entry = meta["surfaces"].get(path.name)
            if isinstance(entry, dict):
                protected_record_count = (
                    entry.get("protected_record_count")
                    if meta.get("schema_version") == 3
                    else entry.get("record_count")
                )
        elif not (allow_surface_metadata_recovery and proof_matches):
            raise IndexSurfaceRefusal(
                f"REFUSAL: nonempty canonical index surface {path} has no "
                "trusted index-surface metadata; run an explicit "
                "source-complete reconcile to recover the cumulative floor"
            )
    if protected_record_count is None:
        protected_record_count = existing_count
    if not isinstance(protected_record_count, int):
        raise IndexSurfaceRefusal(
            f"REFUSAL: {path.name} has an invalid protected shrink baseline"
        )
    protected_record_count = max(existing_count, protected_record_count)
    new_count = len(rows)
    if (
        protected_record_count
        and new_count < protected_record_count
        and new_count < existing_count
        and not allow_shrink
    ):
        shrink_fraction = (
            protected_record_count - new_count
        ) / protected_record_count
        if shrink_fraction >= max_shrink_fraction:
            raise IndexSurfaceRefusal(
                f"REFUSAL: {path.name} would shrink from protected baseline "
                f"{protected_record_count} to "
                f"{new_count} rows ({shrink_fraction:.1%}), meeting or exceeding "
                f"the configured {max_shrink_fraction:.1%} safety boundary; "
                "rerun the full rebuild with --allow-index-shrink, "
                "--shrink-authorization-uid <UID>, and "
                "--shrink-evidence-uid <UID> after adjudication"
            )
    return rows


def _encode_jsonl_rows(rows: list[dict]) -> bytes:
    return b"".join(
        (json.dumps(record, separators=(",", ":")) + "\n").encode("utf-8")
        for record in rows
    )


def _stage_bytes(path: Path, raw: bytes, *, suffix: str = ".tmp") -> Path:
    """Fsync bytes beside their destination without replacing it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=suffix,
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    _fsync_dir(path.parent)
    return tmp_path


def _write_bytes_atomic(path: Path, raw: bytes) -> None:
    tmp_path = _stage_bytes(path, raw)
    try:
        os.replace(tmp_path, path)
        _fsync_dir(path.parent)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _write_jsonl_rows_atomic(path: Path, rows: list[dict]) -> int:
    """Write already-preflighted rows through a temp file + atomic swap."""
    _write_bytes_atomic(path, _encode_jsonl_rows(rows))
    return len(rows)


def _json_bytes(data: dict) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _pair_meta_bytes(
    prepared: list[tuple[Path, list[dict], bytes]],
    *,
    prior_meta: Optional[dict],
    prior_protected_counts: dict[Path, int],
    existing_counts: dict[Path, int],
    baseline_advance_reasons: dict[Path, str],
    full_source_derivation_proof: Optional[FullSourceDerivationProof],
    derivation_provenance: Optional[SurfaceDerivationProvenance],
    metadata_recovery: Optional[dict],
) -> bytes:
    derived_from_uncommitted = bool(
        derivation_provenance
        and derivation_provenance.uncommitted_inputs
    )
    surfaces: dict[str, dict] = {}
    for path, rows, raw in prepared:
        new_count = len(rows)
        prior_entry = (
            prior_meta.get("surfaces", {}).get(path.name)
            if isinstance(prior_meta, dict)
            else None
        )
        prior_protected = prior_protected_counts[path]
        prior_advance = None
        if isinstance(prior_entry, dict):
            prior_advance = prior_entry.get("baseline_advance")

        advance_reason = baseline_advance_reasons.get(path)
        if new_count > prior_protected:
            protected_count = new_count
            baseline_advance = {
                "from": prior_protected,
                "to": new_count,
                "reason": (
                    "non-authoritative-observed-safety-high-water"
                    if derived_from_uncommitted
                    else "growth-high-water"
                ),
            }
        elif new_count < prior_protected and advance_reason:
            protected_count = new_count
            baseline_advance = {
                "from": prior_protected,
                "to": new_count,
                "reason": advance_reason,
            }
        else:
            protected_count = prior_protected
            baseline_advance = prior_advance
        if baseline_advance is None:
            baseline_advance = {
                "from": None,
                "to": protected_count,
                "reason": (
                    "full-source-initialization"
                    if full_source_derivation_proof is not None
                    else "initialization"
                ),
            }
        surfaces[path.name] = {
            "sha256": _sha256(raw),
            "record_count": new_count,
            "protected_record_count": protected_count,
            "baseline_advance": baseline_advance,
        }

    source_inventory = None
    if derivation_provenance is not None:
        source_inventory = {
            "schema_version": 3,
            "sha256": derivation_provenance.manifest_sha256,
            "manifest_entry_count": len(derivation_provenance.manifest),
            "source_path_count": len(derivation_provenance.source_paths),
            "tracked_source_count": len(
                derivation_provenance.source_paths
            ),
            "collected_source_paths": list(
                derivation_provenance.source_paths
            ),
            "manifest": [
                {
                    "content_sha256": content_sha256,
                    "kind": kind,
                    "mode": mode,
                    "path": path,
                }
                for kind, path, mode, content_sha256 in (
                    derivation_provenance.manifest
                )
            ],
            "derived_from_uncommitted": derived_from_uncommitted,
            "uncommitted_inputs": [
                {
                    "content_sha256": content_sha256,
                    "mode": mode,
                    "path": path,
                    "symlink_target_sha256": symlink_target_sha256 or None,
                }
                for (
                    path,
                    mode,
                    content_sha256,
                    symlink_target_sha256,
                ) in derivation_provenance.uncommitted_inputs
            ],
            "authoritative_for": {
                "federation": not derived_from_uncommitted,
                "local": True,
                "ratchet_baseline": not derived_from_uncommitted,
                "release": not derived_from_uncommitted,
            },
        }
    elif isinstance(prior_meta, dict):
        prior_inventory = prior_meta.get("source_inventory")
        if isinstance(prior_inventory, dict):
            source_inventory = prior_inventory

    data = {
        "schema_version": 3,
        "surfaces": surfaces,
        "source_inventory": source_inventory,
    }
    if isinstance(source_inventory, dict) and (
        source_inventory.get("schema_version") in {2, 3}
    ):
        data["derived_from_uncommitted"] = bool(
            source_inventory.get("derived_from_uncommitted")
        )
    if metadata_recovery is not None:
        data["metadata_recovery"] = metadata_recovery
    data["pair_sha256"] = _surface_meta_digest(data)
    return _json_bytes(data)


def _ratchet_evidence_bytes(
    meta_data: dict,
    *,
    prior_evidences: Sequence[dict],
    metadata_recovery: Optional[dict],
) -> bytes:
    """Duplicate protected floors outside the replaceable sidecar.

    The evidence is a transaction participant, so a crash cannot commit new
    surfaces without committing both floor copies.  It is generated only by
    the index writer and is never a governed, hand-maintained file.
    """
    prior_generation = max(
        (evidence.get("generation", 0) for evidence in prior_evidences),
        default=0,
    )
    prior_recovery_count = max(
        (evidence.get("recovery_count", 0) for evidence in prior_evidences),
        default=0,
    )
    latest_evidence = max(
        prior_evidences,
        key=lambda evidence: (
            evidence.get("recovery_count", 0),
            evidence.get("generation", 0),
        ),
        default=None,
    )
    last_recovery = (
        metadata_recovery
        if metadata_recovery is not None
        else (
            latest_evidence.get("last_metadata_recovery")
            if isinstance(latest_evidence, dict)
            else None
        )
    )
    data = {
        "schema_version": 1,
        "generation": prior_generation + 1,
        "surfaces": {
            name: {
                "sha256": entry["sha256"],
                "record_count": entry["record_count"],
                "protected_record_count": entry["protected_record_count"],
            }
            for name, entry in sorted(meta_data["surfaces"].items())
        },
        "source_inventory": meta_data.get("source_inventory"),
        "surface_meta_pair_sha256": meta_data["pair_sha256"],
        "recovery_count": (
            prior_recovery_count + (1 if metadata_recovery is not None else 0)
        ),
        "last_metadata_recovery": last_recovery,
    }
    data["evidence_sha256"] = _ratchet_evidence_digest(data)
    return _json_bytes(data)


def _sqlite_with_ratchet_evidence(
    sqlite_raw: bytes,
    ratchet_data: dict,
) -> bytes:
    """Embed the third signed floor copy in an isolated SQLite image."""
    fd, tmp_name = tempfile.mkstemp(prefix=".index-ratchet.", suffix=".sqlite")
    tmp_path = Path(tmp_name)
    connection = None
    sidecars = [
        Path(f"{tmp_path}-wal"),
        Path(f"{tmp_path}-shm"),
        Path(f"{tmp_path}-journal"),
    ]
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(sqlite_raw)
            handle.flush()
            os.fsync(handle.fileno())
        connection = sqlite3.connect(str(tmp_path))
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS index_ratchet_metadata ("
            "singleton INTEGER PRIMARY KEY CHECK (singleton = 1), "
            "evidence_json TEXT NOT NULL"
            ")"
        )
        connection.execute("DELETE FROM index_ratchet_metadata")
        connection.execute(
            "INSERT INTO index_ratchet_metadata(singleton, evidence_json) "
            "VALUES (1, ?)",
            (
                json.dumps(
                    ratchet_data,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            ),
        )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.close()
        connection = None
        with tmp_path.open("rb") as handle:
            raw = handle.read()
        if not raw:
            raise sqlite3.DatabaseError("embedded SQLite image is empty")
        return raw
    finally:
        if connection is not None:
            connection.close()
        tmp_path.unlink(missing_ok=True)
        for sidecar in sidecars:
            sidecar.unlink(missing_ok=True)


def _transaction_path(vault_root: Path) -> Path:
    return _resolved(vault_root) / INDEX_TRANSACTION_RELATIVE_PATH


def _refuse_pending_pair_transaction(vault_root: Path) -> None:
    journal = _transaction_path(vault_root)
    if journal.exists():
        raise IndexSurfaceRefusal(
            f"REFUSAL: interrupted index transaction pending at {journal}; "
            "a mutating index entry must recover it before read-only use"
        )


def _cleanup_transaction(journal_path: Path, entries: list[dict]) -> None:
    directories = {journal_path.parent}
    for entry in entries:
        for field in ("before_backup", "after_stage"):
            raw_path = entry.get(field)
            if not raw_path:
                continue
            path = Path(raw_path)
            directories.add(path.parent)
            path.unlink(missing_ok=True)
    journal_path.unlink(missing_ok=True)
    for directory in directories:
        if directory.is_dir():
            _fsync_dir(directory)


def _restore_transaction_before(journal_path: Path, entries: list[dict]) -> None:
    unknown: list[str] = []
    for entry in entries:
        path = Path(entry["path"])
        exists = path.exists()
        current_hash = _sha256(path.read_bytes()) if exists else None
        before_hash = entry.get("before_sha256")
        after_hash = entry.get("after_sha256")
        before_exists = bool(entry.get("before_exists"))
        if exists == before_exists and current_hash == before_hash:
            continue
        if current_hash != after_hash:
            unknown.append(str(path))
    if unknown:
        raise IndexSurfaceRefusal(
            "REFUSAL: interrupted index transaction found externally changed "
            f"destination(s), preserving journal for adjudication: {unknown}"
        )

    rollback_errors: list[str] = []
    for entry in reversed(entries):
        path = Path(entry["path"])
        exists = path.exists()
        current_hash = _sha256(path.read_bytes()) if exists else None
        before_hash = entry.get("before_sha256")
        before_exists = bool(entry.get("before_exists"))
        if exists == before_exists and current_hash == before_hash:
            continue
        try:
            if before_exists:
                backup_path = Path(entry["before_backup"])
                if not backup_path.is_file():
                    raise OSError(f"missing transaction backup {backup_path}")
                if _sha256(backup_path.read_bytes()) != before_hash:
                    raise OSError(f"transaction backup hash mismatch {backup_path}")
                os.replace(backup_path, path)
                _fsync_dir(path.parent)
                if _sha256(path.read_bytes()) != before_hash:
                    raise OSError(f"restored destination hash mismatch {path}")
            else:
                path.unlink(missing_ok=True)
                _fsync_dir(path.parent)
        except OSError as exc:
            rollback_errors.append(f"{path}: {exc}")
    if rollback_errors:
        raise IndexSurfaceRefusal(
            "REFUSAL: interrupted index transaction rollback incomplete; "
            f"journal retained: {'; '.join(rollback_errors)}"
        )
    _cleanup_transaction(journal_path, entries)


def _recover_pending_pair_transaction(vault_root: Path) -> None:
    """Deterministically finish or roll back one interrupted index transaction."""
    journal_path = _transaction_path(vault_root)
    if not journal_path.exists():
        return
    try:
        raw = journal_path.read_bytes()
        if not raw or not raw.endswith(b"\n"):
            raise ValueError("journal is empty or lacks its writer newline")
        journal = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise IndexSurfaceRefusal(
            f"REFUSAL: index transaction journal {journal_path} is corrupt: {exc}"
        ) from exc
    entries = journal.get("entries") if isinstance(journal, dict) else None
    if (
        not isinstance(entries, list)
        or not entries
        or journal.get("schema_version") != 1
    ):
        raise IndexSurfaceRefusal(
            f"REFUSAL: index transaction journal {journal_path} has "
            "an unsupported shape"
        )

    vault_root = _resolved(vault_root)
    expected_jsonl_names = {CURRENT_INDEX_NAME, ARCHIVE_INDEX_NAME}
    seen_jsonl_names: set[str] = set()
    seen_meta = 0
    seen_ratchet = 0
    seen_companions = 0
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise IndexSurfaceRefusal(
                f"REFUSAL: index transaction journal {journal_path} "
                "contains a malformed entry"
            )
        path = _resolved(Path(entry["path"]))
        entry["path"] = str(path)
        try:
            path.relative_to(vault_root)
        except ValueError as exc:
            raise IndexSurfaceRefusal(
                f"REFUSAL: transaction destination {path} escapes {vault_root}"
            ) from exc
        kind = entry.get("kind")
        if kind == "jsonl" and path.name in expected_jsonl_names:
            seen_jsonl_names.add(path.name)
        elif (
            kind == "surface-meta"
            and path == vault_root / INDEX_SURFACE_META_RELATIVE_PATH
        ):
            seen_meta += 1
        elif (
            kind == "ratchet-evidence"
            and path == vault_root / INDEX_RATCHET_RELATIVE_PATH
        ):
            seen_ratchet += 1
        elif (
            kind == "companion"
            and path.relative_to(vault_root)
            in INDEX_TRANSACTION_COMPANION_RELATIVE_PATHS
        ):
            seen_companions += 1
        elif (
            kind == "source"
            and path.parent == vault_root / "vault" / "files"
            and path.suffix == ".md"
            and len(path.stem) == 8
            and all(char in "0123456789abcdef" for char in path.stem)
        ):
            pass
        else:
            raise IndexSurfaceRefusal(
                f"REFUSAL: transaction journal contains unauthorized "
                f"destination {path} ({kind!r})"
            )
        for field in ("before_backup", "after_stage"):
            auxiliary = entry.get(field)
            if auxiliary is None and field == "before_backup":
                continue
            if not isinstance(auxiliary, str):
                raise IndexSurfaceRefusal(
                    f"REFUSAL: transaction entry for {path} has malformed {field}"
                )
            auxiliary_path = _resolved(Path(auxiliary))
            if auxiliary_path.parent != path.parent:
                raise IndexSurfaceRefusal(
                    f"REFUSAL: transaction auxiliary {auxiliary_path} is not "
                    f"beside destination {path}"
                )
            entry[field] = str(auxiliary_path)
    if (
        seen_jsonl_names != expected_jsonl_names
        or seen_meta != 1
        or seen_ratchet > 1
        or seen_companions > len(INDEX_TRANSACTION_COMPANION_RELATIVE_PATHS)
    ):
        raise IndexSurfaceRefusal(
            f"REFUSAL: index transaction journal {journal_path} does not "
            "describe exactly one current/archive pair"
        )

    all_after = True
    all_before = True
    for entry in entries:
        path = Path(entry["path"])
        exists = path.exists()
        current_hash = _sha256(path.read_bytes()) if exists else None
        before_matches = (
            exists == bool(entry.get("before_exists"))
            and current_hash == entry.get("before_sha256")
        )
        after_matches = exists and current_hash == entry.get("after_sha256")
        all_before = all_before and before_matches
        all_after = all_after and after_matches

    if all_after or all_before:
        _cleanup_transaction(journal_path, entries)
        return
    _restore_transaction_before(journal_path, entries)


def recover_pending_index_transaction(vault_root: Path) -> None:
    """Public recovery entry for startup/maintenance and adversarial tests."""
    with index_write_lock(vault_root, recover=True):
        return


def write_jsonl_atomic(
    path: Path,
    records: Iterable[dict],
    *,
    max_shrink_fraction: float = DEFAULT_MAX_SHRINK_FRACTION,
    allow_shrink: bool = False,
) -> int:
    """Safely replace one JSONL surface and return its row count.

    The shrink refusal is enforced here, at the final write boundary, so a
    caller cannot accidentally bypass it by changing collection strategy.
    """
    vault_root = _infer_vault_root([path])
    with index_write_lock(vault_root):
        if path.name in {CURRENT_INDEX_NAME, ARCHIVE_INDEX_NAME}:
            other_name = (
                ARCHIVE_INDEX_NAME
                if path.name == CURRENT_INDEX_NAME
                else CURRENT_INDEX_NAME
            )
            other_path = path.with_name(other_name)
            if not path.is_file() or not other_path.is_file():
                raise IndexSurfaceRefusal(
                    "REFUSAL: a canonical index mutation requires both "
                    f"{CURRENT_INDEX_NAME} and {ARCHIVE_INDEX_NAME}"
                )
            rows = list(records)
            other_rows = read_jsonl_strict(other_path)
            counts = write_jsonl_pair_atomic(
                (
                    (path, rows),
                    (other_path, other_rows),
                ),
                max_shrink_fraction=max_shrink_fraction,
                allow_shrink=allow_shrink,
            )
            return counts[0]
        rows = preflight_jsonl_replacement(
            path,
            records,
            max_shrink_fraction=max_shrink_fraction,
            allow_shrink=allow_shrink,
        )
        return _write_jsonl_rows_atomic(path, rows)


def write_jsonl_pair_atomic(
    replacements: Iterable[tuple[Path, Iterable[dict]]],
    *,
    max_shrink_fraction: float = DEFAULT_MAX_SHRINK_FRACTION,
    allow_shrink: bool = False,
    allow_shrink_paths: Optional[set[Path]] = None,
    shrink_baseline_advance_reason: Optional[str] = None,
    shrink_baseline_advance_paths: Optional[dict[Path, str]] = None,
    companion_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
    source_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
    full_source_derivation_proof: Optional[FullSourceDerivationProof] = None,
    derivation_provenance: Optional[SurfaceDerivationProvenance] = None,
    surface_metadata_recovery_reason: Optional[str] = None,
    governed_floor_recovery: Optional[GovernedFloorRecovery] = None,
    governed_shrink_authorization: Optional[
        GovernedShrinkAuthorization
    ] = None,
    incremental_owned_route_uid: Optional[str] = None,
    incremental_owned_route_uids: Optional[Iterable[str]] = None,
    incremental_owned_removal_uids: Optional[Iterable[str]] = None,
) -> list[int]:
    """Journal, fsync, and recoverably replace the surface pair plus companions."""
    replacement_list = list(replacements)
    paths = [_resolved(path) for path, _records in replacement_list]
    if (
        len(paths) != 2
        or {path.name for path in paths} != {
            CURRENT_INDEX_NAME,
            ARCHIVE_INDEX_NAME,
        }
        or paths[0].parent != paths[1].parent
        or paths[0].parent.name != "vault"
    ):
        raise IndexSurfaceRefusal(
            "REFUSAL: recoverable pair destinations must be the canonical "
            "current/archive files in one vault directory"
        )
    vault_root = paths[0].parent.parent
    if set(paths) != {
        vault_root / "vault" / CURRENT_INDEX_NAME,
        vault_root / "vault" / ARCHIVE_INDEX_NAME,
    }:
        raise IndexSurfaceRefusal(
            "REFUSAL: recoverable pair destinations escaped the canonical vault"
        )
    companion_inputs = [
        (Path(path).expanduser().absolute(), raw)
        for path, raw in (companion_replacements or ())
    ]
    companion_list = [
        (_resolved(path), raw) for path, raw in companion_inputs
    ]
    source_inputs = [
        (Path(path).expanduser().absolute(), raw)
        for path, raw in (source_replacements or ())
    ]
    source_list = [
        (_resolved(path), raw) for path, raw in source_inputs
    ]
    allowed_companions = {
        vault_root / relative
        for relative in INDEX_TRANSACTION_COMPANION_RELATIVE_PATHS
    }
    invalid_companions = [
        resolved
        for (lexical, _raw), (resolved, _resolved_raw) in zip(
            companion_inputs,
            companion_list,
        )
        if lexical not in allowed_companions or resolved != lexical
    ]
    if invalid_companions:
        raise IndexSurfaceRefusal(
            "REFUSAL: unauthorized index transaction companion destination(s): "
            + ", ".join(str(path) for path in invalid_companions)
        )
    if len({path for path, _raw in companion_list}) != len(companion_list):
        raise IndexSurfaceRefusal(
            "REFUSAL: duplicate index transaction companion destination"
        )
    for (lexical, _raw), (path, _resolved_raw) in zip(
        source_inputs,
        source_list,
    ):
        if (
            lexical != path
            or path.parent != vault_root / "vault" / "files"
            or path.suffix != ".md"
            or len(path.stem) != 8
            or any(char not in "0123456789abcdef" for char in path.stem)
        ):
            raise IndexSurfaceRefusal(
                f"REFUSAL: invalid governed source transaction path {path}"
            )
    if len({path for path, _raw in source_list}) != len(source_list):
        raise IndexSurfaceRefusal(
            "REFUSAL: duplicate governed source transaction destination"
        )
    if set(paths).intersection(
        {path for path, _raw in companion_list + source_list}
    ):
        raise IndexSurfaceRefusal(
            "REFUSAL: index surface cannot also be a companion/source destination"
        )

    with index_write_lock(vault_root):
        prepared: list[tuple[Path, list[dict], bytes]] = []
        allowed = {_resolved(path) for path in (allow_shrink_paths or set())}
        path_advance_reasons = {
            _resolved(path): reason
            for path, reason in (shrink_baseline_advance_paths or {}).items()
        }
        materialized = [
            (path, list(records))
            for (_original_path, records), path in zip(replacement_list, paths)
        ]
        if full_source_derivation_proof is not None:
            proof_provenance = (
                full_source_derivation_proof.derivation_provenance
            )
            if (
                derivation_provenance is not None
                and derivation_provenance != proof_provenance
            ):
                raise IndexSurfaceRefusal(
                    "REFUSAL: full source proof and derivation provenance "
                    "disagree"
                )
            derivation_provenance = proof_provenance
        if derivation_provenance is not None and (
            not _has_valid_derivation_provenance(derivation_provenance)
            or not all(
                _provenance_matches_surface(
                    derivation_provenance,
                    path,
                    rows,
                )
                for path, rows in materialized
            )
        ):
            raise IndexSurfaceRefusal(
                "REFUSAL: derivation provenance does not match the exact "
                "manifest and proposed current/archive bytes"
            )
        if full_source_derivation_proof is not None:
            if (
                not _proof_has_valid_source_inventory(
                    full_source_derivation_proof
                )
                or not all(
                    _proof_matches_surface(
                        full_source_derivation_proof,
                        path,
                        rows,
                    )
                    for path, rows in materialized
                )
            ):
                raise IndexSurfaceRefusal(
                    "REFUSAL: full source derivation proof does not match the "
                    "canonical current/archive replacement pair and exact "
                    "tracked source inventory"
                )
        meta_path = vault_root / INDEX_SURFACE_META_RELATIVE_PATH
        ratchet_path = vault_root / INDEX_RATCHET_RELATIVE_PATH
        meta_state = "missing"
        ratchet_state = "missing"
        sqlite_state = "missing"
        try:
            prior_meta = _load_surface_meta(paths[0])
            if prior_meta is not None:
                meta_state = "valid"
        except IndexSurfaceRefusal:
            prior_meta = None
            meta_state = "corrupt"
        try:
            prior_ratchet = _load_ratchet_evidence(vault_root)
            if prior_ratchet is not None:
                ratchet_state = "valid"
        except IndexSurfaceRefusal:
            prior_ratchet = None
            ratchet_state = "corrupt"
        try:
            prior_sqlite_ratchet = _load_sqlite_ratchet_evidence(vault_root)
            if prior_sqlite_ratchet is not None:
                sqlite_state = "valid"
        except IndexSurfaceRefusal:
            prior_sqlite_ratchet = None
            sqlite_state = "corrupt"

        existing_counts: dict[Path, int] = {}
        existing_hashes: dict[Path, str] = {}
        existing_rows_by_path: dict[Path, list[dict]] = {}
        for path, _rows in materialized:
            if path.is_file():
                existing_rows = read_jsonl_strict(
                    path,
                    verify_surface_metadata=False,
                )
                existing_rows_by_path[path] = existing_rows
                existing_counts[path] = len(existing_rows)
                existing_hashes[path] = _sha256(path.read_bytes())
            else:
                existing_rows_by_path[path] = []
                existing_counts[path] = 0

        def evidence_matches_actual(evidence: Optional[dict]) -> bool:
            if evidence is None:
                return False
            evidence_surfaces = evidence.get("surfaces", {})
            for path in paths:
                entry = evidence_surfaces.get(path.name)
                if (
                    not path.is_file()
                    or not isinstance(entry, dict)
                    or entry.get("sha256") != existing_hashes.get(path)
                    or entry.get("record_count") != existing_counts[path]
                ):
                    return False
            return True

        meta_matches_actual = evidence_matches_actual(prior_meta)
        ratchet_matches_actual = evidence_matches_actual(prior_ratchet)
        sqlite_matches_actual = evidence_matches_actual(prior_sqlite_ratchet)
        schema2_bytes_match_actual = (
            isinstance(prior_meta, dict)
            and prior_meta.get("schema_version") == 2
            and all(
                isinstance(
                    prior_meta.get("surfaces", {}).get(path.name),
                    dict,
                )
                and prior_meta["surfaces"][path.name].get("sha256")
                == existing_hashes.get(path)
                and isinstance(
                    prior_meta["surfaces"][path.name].get("record_count"),
                    int,
                )
                and prior_meta["surfaces"][path.name]["record_count"] >= 0
                for path in paths
            )
        )

        def evidence_signature(evidence: dict) -> tuple:
            return (
                evidence.get(
                    "surface_meta_pair_sha256",
                    evidence.get("pair_sha256"),
                ),
                json.dumps(
                    evidence.get("source_inventory"),
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                tuple(
                    evidence.get("surfaces", {}).get(path.name, {}).get(
                        "protected_record_count",
                        evidence.get("surfaces", {}).get(path.name, {}).get(
                            "record_count"
                        ),
                    )
                    for path in paths
                ),
            )

        parsed_evidences = [
            evidence
            for evidence in (
                prior_meta,
                prior_ratchet,
                prior_sqlite_ratchet,
            )
            if isinstance(evidence, dict)
        ]
        evidence_copies_agree = (
            len(parsed_evidences) == 3
            and len({
                evidence_signature(evidence)
                for evidence in parsed_evidences
            }) == 1
        )
        if schema2_bytes_match_actual:
            meta_state = "valid-schema2-bootstrap"
        elif prior_meta is not None and not meta_matches_actual:
            meta_state = "stale-surface-mismatch"
        if prior_ratchet is not None and not ratchet_matches_actual:
            ratchet_state = "stale-surface-mismatch"
        if prior_sqlite_ratchet is not None and not sqlite_matches_actual:
            sqlite_state = "stale-surface-mismatch"
        if len(parsed_evidences) == 3 and not evidence_copies_agree:
            if ratchet_state == "valid":
                ratchet_state = "copy-mismatch"
            if sqlite_state == "valid":
                sqlite_state = "copy-mismatch"

        complete_floor_evidence = (
            meta_state == "valid"
            and ratchet_state == "valid"
            and sqlite_state == "valid"
            and evidence_copies_agree
        )
        existing_surface_present = any(path.is_file() for path in paths)
        unmanaged_legacy_pair = (
            not (vault_root / ".tropo").exists()
            and not (vault_root / ".git").exists()
        )
        schema2_bootstrap = (
            isinstance(prior_meta, dict)
            and prior_meta.get("schema_version") == 2
            and schema2_bytes_match_actual
            and ratchet_state == "missing"
            and sqlite_state == "missing"
            and all(path.is_file() for path in paths)
            and sum(existing_counts.values()) > 0
        )
        # Keep the low-level ADR-047 primitive usable in intentionally
        # ungoverned, repository-free library fixtures.  A real Studio carries
        # .tropo and/or Git identity, so its nonempty surfaces can never enter
        # this compatibility branch or silently mint a new floor.
        recovery_required = (
            existing_surface_present
            and not complete_floor_evidence
            and not unmanaged_legacy_pair
        )
        source_recovery_authorized = (
            surface_metadata_recovery_reason is not None
            and full_source_derivation_proof is not None
            and not derivation_provenance.uncommitted_inputs
        )
        recovery_authorized = (
            source_recovery_authorized or schema2_bootstrap
        )
        total_evidence_loss = not parsed_evidences
        if governed_floor_recovery is not None:
            if not existing_surface_present:
                raise IndexSurfaceRefusal(
                    "REFUSAL: governed floor recovery is only valid for "
                    "existing canonical surfaces; fresh absent surfaces "
                    "initialize from the full source-complete proof"
                )
            recovery_uid = governed_floor_recovery.evidence_uid
            if (
                not source_recovery_authorized
                or not isinstance(
                    governed_floor_recovery.current_protected_record_count,
                    int,
                )
                or not isinstance(
                    governed_floor_recovery.archive_protected_record_count,
                    int,
                )
                or governed_floor_recovery.current_protected_record_count < 0
                or governed_floor_recovery.archive_protected_record_count < 0
                or len(recovery_uid) != 8
                or any(char not in "0123456789abcdef" for char in recovery_uid)
            ):
                raise IndexSurfaceRefusal(
                    "REFUSAL: governed floor recovery requires a matching "
                    "source-complete reconcile proof, nonnegative current and "
                    "archive floors, and an 8-hex authorization/evidence UID"
                )
            supplied_floors = {
                CURRENT_INDEX_NAME: (
                    governed_floor_recovery.current_protected_record_count
                ),
                ARCHIVE_INDEX_NAME: (
                    governed_floor_recovery.archive_protected_record_count
                ),
            }
            for path in paths:
                if supplied_floors[path.name] < existing_counts[path]:
                    raise IndexSurfaceRefusal(
                        "REFUSAL: governed recovery floor for "
                        f"{path.name} ({supplied_floors[path.name]}) is below "
                        f"the observed {existing_counts[path]} rows"
                    )
        else:
            supplied_floors = {}
        if (
            recovery_required
            and total_evidence_loss
            and governed_floor_recovery is None
        ):
            raise IndexSurfaceRefusal(
                "REFUSAL: all cumulative index shrink-floor evidence is "
                "absent or unreadable for nonempty surfaces; ordinary apply "
                "and reconcile cannot infer a replacement baseline. Use the "
                "explicit governed floor-recovery flags with caller-supplied "
                "current/archive floors and an authorization/evidence UID"
            )
        if recovery_required and not recovery_authorized:
            raise IndexSurfaceRefusal(
                "REFUSAL: cumulative index shrink-floor evidence is incomplete "
                f"(sidecar={meta_state}, ratchet={ratchet_state}, "
                f"sqlite={sqlite_state}); ordinary "
                "apply/incremental mutation cannot reset the protected "
                "baseline. Run an explicit source-complete reconcile to "
                "recover all evidence copies"
            )

        protected_counts: dict[Path, int] = {}
        for path, _rows in materialized:
            candidates = [existing_counts[path]]
            for evidence in parsed_evidences:
                if not isinstance(evidence, dict):
                    continue
                entry = evidence.get("surfaces", {}).get(path.name)
                if not isinstance(entry, dict):
                    continue
                protected = (
                    entry.get("protected_record_count")
                    if evidence.get("schema_version") in {1, 3}
                    else entry.get("record_count")
                )
                if isinstance(protected, int) and protected >= 0:
                    candidates.append(protected)
            supplied = supplied_floors.get(path.name)
            if isinstance(supplied, int):
                candidates.append(supplied)
            protected_counts[path] = max(candidates)

        floor_lowering_paths = {
            path
            for path, rows in materialized
            if len(rows) < protected_counts[path]
        }
        def union_by_uid(
            row_groups: Iterable[list[dict]],
        ) -> Optional[dict[str, dict]]:
            union: dict[str, dict] = {}
            for rows in row_groups:
                for row in rows:
                    uid = row.get("uid")
                    if not isinstance(uid, str) or uid in union:
                        return None
                    union[uid] = row
            return union

        lossless_owned_route = False
        owned_route_uids = set(incremental_owned_route_uids or ())
        if incremental_owned_route_uid is not None:
            owned_route_uids.add(incremental_owned_route_uid)
        if owned_route_uids:
            if any(
                len(uid) != 8
                or any(char not in "0123456789abcdef" for char in uid)
                for uid in owned_route_uids
            ):
                raise IndexSurfaceRefusal(
                    "REFUSAL: incremental route ownership requires only "
                    "8-hex target UIDs"
                )

            before_union = union_by_uid(existing_rows_by_path.values())
            after_union = union_by_uid(
                [rows for _path, rows in materialized]
            )
            if before_union is not None and after_union is not None:
                changed_uids = {
                    uid
                    for uid in set(before_union) | set(after_union)
                    if before_union.get(uid) != after_union.get(uid)
                }
                lossless_owned_route = (
                    set(before_union) == set(after_union)
                    and changed_uids == owned_route_uids
                )
        owned_removal_uids = set(incremental_owned_removal_uids or ())
        if any(
            len(uid) != 8
            or any(char not in "0123456789abcdef" for char in uid)
            for uid in owned_removal_uids
        ):
            raise IndexSurfaceRefusal(
                "REFUSAL: incremental removal ownership requires only "
                "8-hex target UIDs"
            )
        lossless_owned_removal = False
        if owned_removal_uids:
            before_union = union_by_uid(existing_rows_by_path.values())
            after_union = union_by_uid(
                [rows for _path, rows in materialized]
            )
            if before_union is not None and after_union is not None:
                removed_uids = set(before_union) - set(after_union)
                lossless_owned_removal = (
                    removed_uids == owned_removal_uids
                    and set(after_union).issubset(before_union)
                    and all(
                        before_union[uid] == after_union[uid]
                        for uid in after_union
                    )
                )
        if governed_shrink_authorization is not None and not allow_shrink:
            raise IndexSurfaceRefusal(
                "REFUSAL: governed shrink authorization was supplied without "
                "an explicit shrink override"
            )
        if (
            derivation_provenance is not None
            and derivation_provenance.uncommitted_inputs
            and (
                governed_floor_recovery is not None
                or (
                    allow_shrink
                    and floor_lowering_paths
                    and not lossless_owned_route
                    and not lossless_owned_removal
                )
            )
        ):
            uncommitted_paths = ", ".join(
                path
                for path, _mode, _content_sha, _link_sha in (
                    derivation_provenance.uncommitted_inputs
                )
            )
            raise IndexSurfaceRefusal(
                "REFUSAL: a surface derived from uncommitted inputs is "
                "non-authoritative for ratchet recovery or floor lowering; "
                "land/revert/isolate the recorded paths and rederive first: "
                + uncommitted_paths
            )
        if (
            allow_shrink
            and floor_lowering_paths
            and not unmanaged_legacy_pair
            and not lossless_owned_route
            and not lossless_owned_removal
        ):
            authorization = governed_shrink_authorization
            if (
                authorization is None
                or len(authorization.authorization_uid) != 8
                or any(
                    char not in "0123456789abcdef"
                    for char in authorization.authorization_uid
                )
                or len(authorization.evidence_uid) != 8
                or any(
                    char not in "0123456789abcdef"
                    for char in authorization.evidence_uid
                )
            ):
                raise IndexSurfaceRefusal(
                    "REFUSAL: lowering a protected index floor requires "
                    "--allow-index-shrink with "
                    "--shrink-authorization-uid <UID> and "
                    "--shrink-evidence-uid <UID> "
                    "(8 lowercase hex each)"
                )

        metadata_recovery = None
        if recovery_required or governed_floor_recovery is not None:
            evidence_sources = []
            if prior_meta is not None:
                evidence_sources.append("index-surface-sidecar")
            if prior_ratchet is not None:
                evidence_sources.append("duplicated-ratchet")
            if prior_sqlite_ratchet is not None:
                evidence_sources.append("sqlite-ratchet")
            evidence_sources.append("existing-surface-counts")
            if full_source_derivation_proof is not None:
                evidence_sources.append("full-source-inventory")
            metadata_recovery = {
                "reason": (
                    "schema2-to-schema3-bootstrap"
                    if schema2_bootstrap
                    else surface_metadata_recovery_reason
                ),
                "sidecar_state": meta_state,
                "ratchet_state": ratchet_state,
                "sqlite_state": sqlite_state,
                "evidence": evidence_sources,
                "source_inventory_sha256": (
                    full_source_derivation_proof.source_inventory_sha256
                    if full_source_derivation_proof is not None
                    else None
                ),
                "recovered_protected_record_counts": {
                    path.name: protected_counts[path]
                    for path in paths
                },
            }
            if schema2_bootstrap:
                metadata_recovery["schema_migration"] = {
                    "from": 2,
                    "to": 3,
                    "basis": (
                        "max(schema2-recorded-count,"
                        "verified-current-surface-count)"
                    ),
                }
            if governed_floor_recovery is not None:
                metadata_recovery["governed_floor_recovery"] = {
                    "authorization_evidence_uid": (
                        governed_floor_recovery.evidence_uid
                    ),
                    "caller_supplied_protected_record_counts": supplied_floors,
                }
        for path, rows in materialized:
            rows = preflight_jsonl_replacement(
                path,
                rows,
                max_shrink_fraction=max_shrink_fraction,
                allow_shrink=(
                    allow_shrink
                    or lossless_owned_removal
                    or path in allowed
                ),
                full_source_derivation_proof=full_source_derivation_proof,
                protected_record_count=protected_counts[path],
                allow_surface_metadata_recovery=recovery_authorized,
            )
            prepared.append((path, rows, _encode_jsonl_rows(rows)))

        baseline_advance_reasons = dict(path_advance_reasons)
        if allow_shrink or lossless_owned_removal:
            reason = (
                "incremental-owned-lossless-route"
                if lossless_owned_route
                else (
                    "incremental-owned-removal"
                    if lossless_owned_removal
                    else (
                        shrink_baseline_advance_reason
                        or "explicit-adjudicated-shrink-override"
                    )
                )
            )
            if governed_shrink_authorization is not None:
                reason = (
                    f"{reason};authorization_uid="
                    f"{governed_shrink_authorization.authorization_uid};"
                    f"evidence_uid="
                    f"{governed_shrink_authorization.evidence_uid}"
                )
            baseline_advance_reasons.update({path: reason for path in paths})
        for path in allowed:
            baseline_advance_reasons.setdefault(
                path,
                "compose-lock-mounted-retirement",
            )
        if governed_floor_recovery is not None:
            # A floor-restoration transaction may heal projections but is
            # never itself authority to lower the caller-supplied/historical
            # maximum, even when reconcile derives fewer rows.
            for path in paths:
                baseline_advance_reasons.pop(path, None)
        if (
            derivation_provenance is not None
            and derivation_provenance.uncommitted_inputs
            and not lossless_owned_removal
        ):
            # Dirty provenance may conservatively raise an observed safety
            # high-water, but can never lower or adjudicate a protected floor.
            baseline_advance_reasons.clear()
        meta_raw = _pair_meta_bytes(
            prepared,
            prior_meta=prior_meta,
            prior_protected_counts=protected_counts,
            existing_counts=existing_counts,
            baseline_advance_reasons=baseline_advance_reasons,
            full_source_derivation_proof=(
                full_source_derivation_proof
            ),
            derivation_provenance=derivation_provenance,
            metadata_recovery=metadata_recovery,
        )
        meta_data = json.loads(meta_raw.decode("utf-8"))
        ratchet_raw = _ratchet_evidence_bytes(
            meta_data,
            prior_evidences=[
                evidence
                for evidence in (prior_ratchet, prior_sqlite_ratchet)
                if isinstance(evidence, dict)
            ],
            metadata_recovery=metadata_recovery,
        )
        ratchet_data = json.loads(ratchet_raw.decode("utf-8"))

        sqlite_path = vault_root / "vault" / "00-index.sqlite"
        sqlite_companions = [
            (path, raw)
            for path, raw in companion_list
            if path == sqlite_path
        ]
        if len(sqlite_companions) > 1:
            raise ValueError("one SQLite image cannot appear twice")
        non_sqlite_companions = [
            (path, raw)
            for path, raw in companion_list
            if path != sqlite_path
        ]
        sqlite_source_raw = (
            sqlite_companions[0][1]
            if sqlite_companions
            else (sqlite_path.read_bytes() if sqlite_path.is_file() else None)
        )
        if sqlite_source_raw is not None:
            try:
                embedded_sqlite_raw = _sqlite_with_ratchet_evidence(
                    sqlite_source_raw,
                    ratchet_data,
                )
            except (OSError, sqlite3.Error) as exc:
                raise IndexSurfaceRefusal(
                    "REFUSAL: could not embed transaction-bound SQLite "
                    f"ratchet evidence: {exc}"
                ) from exc
            non_sqlite_companions.append(
                (sqlite_path, embedded_sqlite_raw)
            )
        elif not unmanaged_legacy_pair:
            raise IndexSurfaceRefusal(
                "REFUSAL: governed index transaction has no SQLite image for "
                "the required third cumulative-floor evidence copy"
            )

        byte_replacements = [
            (path, raw, "jsonl") for path, _rows, raw in prepared
        ]
        byte_replacements.extend(
            (path, raw, "companion")
            for path, raw in non_sqlite_companions
        )
        byte_replacements.extend(
            (path, raw, "source")
            for path, raw in source_list
        )
        byte_replacements.append(
            (
                meta_path,
                meta_raw,
                "surface-meta",
            )
        )
        byte_replacements.append(
            (
                ratchet_path,
                ratchet_raw,
                "ratchet-evidence",
            )
        )
        if len({path for path, _raw, _kind in byte_replacements}) != len(
            byte_replacements
        ):
            raise ValueError("one path cannot appear twice in an index transaction")

        transaction_id = uuid.uuid4().hex
        journal_path = _transaction_path(vault_root)
        entries: list[dict] = []
        created_paths: list[Path] = []
        try:
            for path, after_raw, kind in byte_replacements:
                before_exists = path.exists()
                before_raw = path.read_bytes() if before_exists else b""
                before_backup = (
                    _stage_bytes(
                        path,
                        before_raw,
                        suffix=f".{transaction_id}.before",
                    )
                    if before_exists
                    else None
                )
                after_stage = _stage_bytes(
                    path,
                    after_raw,
                    suffix=f".{transaction_id}.after",
                )
                if before_backup is not None:
                    created_paths.append(before_backup)
                created_paths.append(after_stage)
                entries.append({
                    "path": str(path),
                    "kind": kind,
                    "before_exists": before_exists,
                    "before_sha256": _sha256(before_raw) if before_exists else None,
                    "after_sha256": _sha256(after_raw),
                    "before_backup": (
                        str(before_backup) if before_backup is not None else None
                    ),
                    "after_stage": str(after_stage),
                })
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            _write_bytes_atomic(journal_path, _json_bytes({
                "schema_version": 1,
                "transaction_id": transaction_id,
                "entries": entries,
            }))
        except OSError as exc:
            if not journal_path.exists():
                for path in created_paths:
                    path.unlink(missing_ok=True)
            raise IndexSurfaceRefusal(
                f"REFUSAL: could not prepare recoverable index transaction: {exc}"
            ) from exc

        try:
            for entry in entries:
                path = Path(entry["path"])
                after_stage = Path(entry["after_stage"])
                if _sha256(after_stage.read_bytes()) != entry["after_sha256"]:
                    raise OSError(
                        f"staged destination hash mismatch {after_stage}"
                    )
                os.replace(after_stage, path)
                _fsync_dir(path.parent)
        except OSError as exc:
            try:
                _restore_transaction_before(journal_path, entries)
            except IndexSurfaceRefusal as rollback_exc:
                raise IndexSurfaceRefusal(
                    f"REFUSAL: index transaction failed at {path}: {exc}; "
                    f"{rollback_exc}"
                ) from exc
            raise IndexSurfaceRefusal(
                f"REFUSAL: index transaction failed at {path}: {exc}; "
                "all destinations restored byte-identically"
            ) from exc

        _cleanup_transaction(journal_path, entries)
        return [len(rows) for _path, rows, _raw in prepared]


def write_json_atomic(path: Path, data: dict) -> None:
    """Atomically replace one JSON object with fsync + unique temp file."""
    _write_bytes_atomic(path, _json_bytes(data))


def plan_record_route(vault_root: Path, record: dict) -> RecordRoutePlan:
    """Strictly read and plan an incremental route without writing anything."""
    uid = record.get("uid")
    if not uid:
        raise ValueError("cannot route an index record without uid")

    vault_dir = vault_root / "vault"
    target_name = ARCHIVE_INDEX_NAME if is_archive_record(record) else CURRENT_INDEX_NAME
    current_path = vault_dir / CURRENT_INDEX_NAME
    archive_path = vault_dir / ARCHIVE_INDEX_NAME
    for path in (current_path, archive_path):
        if not path.is_file():
            raise IndexSurfaceRefusal(
                f"REFUSAL: incremental route requires both index surfaces; "
                f"{path} is missing"
            )
    current_before = read_jsonl_strict(current_path)
    archive_before = read_jsonl_strict(archive_path)

    target_rows = (
        archive_before if target_name == ARCHIVE_INDEX_NAME else current_before
    )
    replaced = False
    routed: list[dict] = []
    for row in target_rows:
        if row.get("uid") == uid:
            routed.append(record)
            replaced = True
        else:
            routed.append(row)
    if not replaced:
        routed.append(record)
    if target_name == ARCHIVE_INDEX_NAME:
        current_after = [
            row for row in current_before if row.get("uid") != uid
        ]
        archive_after = routed
    else:
        current_after = routed
        archive_after = [
            row for row in archive_before if row.get("uid") != uid
        ]

    return RecordRoutePlan(
        uid=str(uid),
        target_name=target_name,
        action="updated" if replaced else "inserted (new)",
        current_path=current_path,
        archive_path=archive_path,
        current_before=current_before,
        archive_before=archive_before,
        current_after=current_after,
        archive_after=archive_after,
    )


def plan_records_route(
    vault_root: Path,
    records: Iterable[dict],
) -> RecordBatchRoutePlan:
    """Strictly read once and plan a lossless multi-UID route in memory."""
    by_uid: dict[str, dict] = {}
    for record in records:
        uid = record.get("uid")
        if not isinstance(uid, str) or not uid:
            raise ValueError("cannot route an index record without uid")
        if uid in by_uid:
            raise ValueError(f"cannot route duplicate index UID {uid}")
        by_uid[uid] = record
    if not by_uid:
        raise ValueError("cannot route an empty index-record batch")

    vault_dir = vault_root / "vault"
    current_path = vault_dir / CURRENT_INDEX_NAME
    archive_path = vault_dir / ARCHIVE_INDEX_NAME
    for path in (current_path, archive_path):
        if not path.is_file():
            raise IndexSurfaceRefusal(
                "REFUSAL: incremental batch route requires both index "
                f"surfaces; {path} is missing"
            )
    current_before = read_jsonl_strict(current_path)
    archive_before = read_jsonl_strict(archive_path)
    before_by_uid = {
        str(row.get("uid")): row
        for row in current_before + archive_before
        if row.get("uid")
    }
    touched = set(by_uid)
    retained = [
        row
        for row in current_before + archive_before
        if row.get("uid") not in touched
    ]
    routed = retained + [by_uid[uid] for uid in sorted(by_uid)]
    current_after, archive_after = partition_records(routed)
    destinations = tuple(
        (
            uid,
            ARCHIVE_INDEX_NAME
            if is_archive_record(by_uid[uid])
            else CURRENT_INDEX_NAME,
            "updated" if uid in before_by_uid else "inserted (new)",
        )
        for uid in sorted(by_uid)
    )
    return RecordBatchRoutePlan(
        uids=tuple(sorted(by_uid)),
        current_path=current_path,
        archive_path=archive_path,
        current_before=current_before,
        archive_before=archive_before,
        current_after=current_after,
        archive_after=archive_after,
        destinations=destinations,
    )


def write_records_route(
    plan: RecordBatchRoutePlan,
    *,
    companion_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
    source_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
    derivation_provenance: Optional[SurfaceDerivationProvenance] = None,
    incremental_owned_route_uids: Optional[Iterable[str]] = None,
) -> tuple[tuple[str, str, str], ...]:
    """Commit one preplanned multi-UID route and companions atomically."""
    route_moves_between_surfaces = (
        len(plan.current_after) < len(plan.current_before)
        or len(plan.archive_after) < len(plan.archive_before)
    )
    write_jsonl_pair_atomic(
        (
            (plan.current_path, plan.current_after),
            (plan.archive_path, plan.archive_after),
        ),
        allow_shrink=route_moves_between_surfaces,
        companion_replacements=companion_replacements,
        source_replacements=source_replacements,
        derivation_provenance=derivation_provenance,
        incremental_owned_route_uids=(
            plan.uids
            if incremental_owned_route_uids is None
            else incremental_owned_route_uids
        ),
    )
    return plan.destinations


def write_record_route(
    plan: RecordRoutePlan,
    *,
    companion_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
    derivation_provenance: Optional[SurfaceDerivationProvenance] = None,
) -> tuple[str, str]:
    """Commit one preplanned route and optional SQLite image transactionally."""
    route_moves_between_surfaces = (
        len(plan.current_after) < len(plan.current_before)
        or len(plan.archive_after) < len(plan.archive_before)
    )
    write_jsonl_pair_atomic(
        (
            (plan.current_path, plan.current_after),
            (plan.archive_path, plan.archive_after),
        ),
        allow_shrink=route_moves_between_surfaces,
        companion_replacements=companion_replacements,
        derivation_provenance=derivation_provenance,
        incremental_owned_route_uid=plan.uid,
    )
    return plan.target_name, plan.action


def restore_record_route(plan: RecordRoutePlan) -> None:
    """Restore exact pre-route rows after a downstream derived-write failure."""
    write_jsonl_pair_atomic(
        (
            (plan.current_path, plan.current_before),
            (plan.archive_path, plan.archive_before),
        ),
        allow_shrink=True,
        incremental_owned_route_uid=plan.uid,
    )


def route_record(vault_root: Path, record: dict) -> tuple[str, str]:
    """Upsert one record into its ADR-047 surface and remove it from the other.

    Returns ``(surface_name, action)`` where action is ``updated`` or
    ``inserted (new)``.  This is the incremental counterpart of
    :func:`partition_records`; both call the same archive predicate.
    """
    with index_write_lock(vault_root):
        plan = plan_record_route(vault_root, record)
        return write_record_route(plan)


def plan_uid_removal(vault_root: Path, uid: str) -> RecordRemovalPlan:
    """Strictly read and plan removal from both surfaces without mutation."""
    vault_dir = vault_root / "vault"
    current_path = vault_dir / CURRENT_INDEX_NAME
    archive_path = vault_dir / ARCHIVE_INDEX_NAME
    for path in (current_path, archive_path):
        if not path.is_file():
            raise IndexSurfaceRefusal(
                f"REFUSAL: incremental removal requires both index surfaces; "
                f"{path} is missing"
            )
    current_before = read_jsonl_strict(current_path)
    archive_before = read_jsonl_strict(archive_path)
    current_after = [
        row for row in current_before if row.get("uid") != uid
    ]
    archive_after = [
        row for row in archive_before if row.get("uid") != uid
    ]
    removed_from = []
    if len(current_after) != len(current_before):
        removed_from.append(CURRENT_INDEX_NAME)
    if len(archive_after) != len(archive_before):
        removed_from.append(ARCHIVE_INDEX_NAME)
    return RecordRemovalPlan(
        uid=uid,
        current_path=current_path,
        archive_path=archive_path,
        current_before=current_before,
        archive_before=archive_before,
        current_after=current_after,
        archive_after=archive_after,
        removed_from=removed_from,
    )


def plan_uids_removal(
    vault_root: Path,
    uids: Iterable[str],
) -> RecordBatchRemovalPlan:
    """Strictly read once and plan a multi-UID union removal."""
    normalized = tuple(sorted(set(uids)))
    if not normalized:
        raise ValueError("cannot plan an empty UID removal batch")
    uid_set = set(normalized)
    vault_dir = vault_root / "vault"
    current_path = vault_dir / CURRENT_INDEX_NAME
    archive_path = vault_dir / ARCHIVE_INDEX_NAME
    for path in (current_path, archive_path):
        if not path.is_file():
            raise IndexSurfaceRefusal(
                "REFUSAL: incremental batch removal requires both index "
                f"surfaces; {path} is missing"
            )
    current_before = read_jsonl_strict(current_path)
    archive_before = read_jsonl_strict(archive_path)
    current_after = [
        row for row in current_before if row.get("uid") not in uid_set
    ]
    archive_after = [
        row for row in archive_before if row.get("uid") not in uid_set
    ]
    removed_from = tuple(
        (
            uid,
            tuple(
                name
                for name, rows in (
                    (CURRENT_INDEX_NAME, current_before),
                    (ARCHIVE_INDEX_NAME, archive_before),
                )
                if any(row.get("uid") == uid for row in rows)
            ),
        )
        for uid in normalized
    )
    return RecordBatchRemovalPlan(
        uids=normalized,
        current_path=current_path,
        archive_path=archive_path,
        current_before=current_before,
        archive_before=archive_before,
        current_after=current_after,
        archive_after=archive_after,
        removed_from=removed_from,
    )


def write_uids_removal(
    plan: RecordBatchRemovalPlan,
    *,
    companion_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
    source_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
    derivation_provenance: Optional[SurfaceDerivationProvenance] = None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Commit one planned multi-UID removal and companions atomically."""
    write_jsonl_pair_atomic(
        (
            (plan.current_path, plan.current_after),
            (plan.archive_path, plan.archive_after),
        ),
        companion_replacements=companion_replacements,
        source_replacements=source_replacements,
        derivation_provenance=derivation_provenance,
        incremental_owned_removal_uids=plan.uids,
    )
    return plan.removed_from


def write_uid_removal(
    plan: RecordRemovalPlan,
    *,
    companion_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
    derivation_provenance: Optional[SurfaceDerivationProvenance] = None,
) -> list[str]:
    """Commit one planned union removal and optional SQLite image atomically."""
    vault_root = _infer_vault_root([
        plan.current_path,
        plan.archive_path,
    ])
    unmanaged_compatibility = (
        not (vault_root / ".tropo").exists()
        and not (vault_root / ".git").exists()
    )
    write_jsonl_pair_atomic(
        (
            (plan.current_path, plan.current_after),
            (plan.archive_path, plan.archive_after),
        ),
        allow_shrink=unmanaged_compatibility,
        companion_replacements=companion_replacements,
        derivation_provenance=derivation_provenance,
    )
    return plan.removed_from


def remove_uid(vault_root: Path, uid: str) -> list[str]:
    """Remove one UID from both disposable JSONL surfaces.

    Returns the surface names from which a row was removed.
    """
    with index_write_lock(vault_root):
        plan = plan_uid_removal(vault_root, uid)
        if not plan.removed_from:
            return []
        return write_uid_removal(plan)


def _format_legacy_digest_door_report(report: dict) -> str:
    needs = report["needs_door"]
    answer = {
        True: "YES — this machine still needs the door",
        False: "no — this machine does not need the door",
        None: "UNKNOWN — this machine cannot answer",
    }[needs]
    door = (
        f"OPEN until {report['sunset']} "
        f"({report['days_until_sunset']} day(s) left)"
        if report["door_open"]
        else f"CLOSED since {report['sunset']}"
    )
    admissions = report["admissions"]
    lines = [
        f"legacy digest door ({report['legacy_tag']}): {door}",
        f"this machine:      {answer}",
        f"  verdict:         {report['verdict']}",
        f"  because:         {report['reason']}",
        f"  seal:            {report['meta_path']}",
        f"  admissions seen: {admissions['observed']}"
        + (
            f" (first {admissions['first_admitted_at']}, "
            f"last {admissions['last_admitted_at']})"
            if admissions["observed"]
            else " — lower bound; see --json for why"
        ),
    ]
    if report["stranded"]:
        lines.append(
            "  STRANDED:        the door has closed and this machine's index "
            "is deadlocked until the seal is re-stamped"
        )
    if needs is not False:
        lines.append(f"  cure:            {report['cure']}")
    return "\n".join(lines)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """Report whether this machine still needs the legacy digest door.

    Exit codes are the report, not a gate:

    * ``0`` — measured, and nothing is owed on this machine.
    * ``1`` — this machine still needs the door, or could not answer.  An
      unknown is not a pass; summing unknowns as zeroes is how the door would
      get closed on a guess.
    * ``2`` — usage error.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="index_surfaces.py",
        description=(
            "Report whether this machine's trusted index-surface seal is "
            "still being carried by the superseded-format bootstrap door "
            "(ADR-063). Read-only."
        ),
    )
    parser.add_argument(
        "--studio",
        default=None,
        help="studio root (default: the root this library ships under)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the full reading as JSON",
    )
    args = parser.parse_args(argv)

    root = (
        Path(args.studio).expanduser().resolve()
        if args.studio
        else Path(__file__).resolve().parents[3]
    )
    if not root.is_dir():
        parser.error(f"no such studio root: {root}")
    report = legacy_digest_door_report(root)
    print(
        json.dumps(report, indent=2, sort_keys=True)
        if args.json
        else _format_legacy_digest_door_report(report)
    )
    return 0 if report["needs_door"] is False else 1


if __name__ == "__main__":
    raise SystemExit(_main())
