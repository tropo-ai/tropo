#!/usr/bin/env python3
"""tropo-folder.py — mount a folder that is nobody's vault, and keep finding it.

WHAT THIS IS FOR
----------------
A OneDrive or SharePoint sync directory. No manifest, not a git repo, sitting
anywhere on the machine. Until now nothing in this Studio could reach one:
``tropo-mount.py`` mounts *vaults* and requires a manifest, a git repo and a
clean tree, and the import walker's adoption machinery refused any source
outside the Studio tree. That gap is what blocks the stated use case — Mike's
own files, which have to live in SharePoint for work reasons and which he wants
to work on here.

ONE MOUNT, TWO STATES, AND A SWITCH BETWEEN THEM
------------------------------------------------
ATTACHED
    Agents have hands on the folder: they can read it, search it, change files
    in it. No metadata, no governance, no identifiers, and — the part that
    matters — **nothing is written into the folder**. This is day one, and it
    costs nothing.

ADOPTED
    The SAME mount, tooled. Every file gets a sidecar at
    ``<folder>/.tropo-studio/<filename>.tropo.md`` and a governed entry derived
    from it at ``vault/files/<uid>.md``.

``adopt`` mutates the record that is already there. It never mints a second
one, and the ``mount_uid`` survives, because every governed entry that will
ever point at this folder points at that uid. Nobody has to decide up front
what kind of thing a folder is.

Mount lifecycle is separate from source availability. ``state`` remains the
two-position attached/adopted switch; ``availability`` is
available/unavailable/ambiguous. A temporary loss keeps every UID and link
target as an unavailable tombstone. Explicit ``unmount`` retains its existing
recycle-and-forget behavior.

DRIFT, WHICH IS THE PART WITH NO PRIOR ART
------------------------------------------
Cloud folders re-sync and change path. The import walker reconciles *sidecars
against files*, one layer down; ``compose.lock``'s ``mount_path`` is advisory.
Nothing reconciled a mount against a moved folder, so ``fingerprint`` has to
answer "is this the same folder somewhere else?" without the path.

The mechanism, and the argument for each half of it:

**A decisive mark when we are entitled to one.** Adoption already writes into
``<folder>/.tropo-studio/``, so it also writes ``.tropo-mount.json`` carrying
the ``mount_uid``. Finding that is not a guess — it is the folder telling us
who it is. Attach may not use this, because attach writes nothing, which is
why the second half exists and why it is the half that carries the design.

**A content fingerprint when we are not.** At mount time we record, for up to
:data:`ANCHOR_MAX` files spread evenly through the folder, the path within the
folder plus a digest, and the folder's own name. Re-finding scores a candidate
by how many anchors still match. Path-independent by construction, so it
survives the move; layout-aware, so it does not confuse two unrelated folders
that happen to share a file.

Content and name are kept as two signals rather than blended into one number, a
weighted sum being a fudge factor nobody can argue with. A candidate still
called what the folder was called has to match :data:`MATCH_FLOOR` of the
anchors; one called something else has to match :data:`RENAMED_FLOOR`, which is
nearly all of them. The asymmetry is the shape of the actual event: a re-sync
renames the PARENT and leaves the leaf alone, so a differently-named folder is
a weaker claim, and letting a weak claim through is how a deleted mount gets
"re-found" as a similar folder nearby and quietly re-anchors every governed
entry that names it onto somebody else's content.

The two hard cases, answered explicitly rather than by omission:

*Two folders look identical.* Content alone cannot tell them apart, and
choosing one is worse than choosing neither: every governed entry pointing at
the mount would silently re-anchor to the wrong copy, on a path nothing errors
on. So a tie inside :data:`AMBIGUITY_MARGIN` is refused by name — the mount is
reported ``ambiguous``, every candidate is listed with its score, and the
registry is left exactly as it was. The same refusal covers the subtler tie: a
renamed candidate that fits BETTER than the same-named one, which is either a
rename or a stale copy keeping the old name, and is not ours to decide.
Recovery is one gesture, ``reconcile <uid> --resolve <path>``, a human supplying
the one thing the machine does not have. Note the asymmetry that makes this
affordable: an adopted folder carries the anchor, so identical twins are only a
problem while a mount is attached, and adopting is the cure.

*The contents legitimately changed.* A fingerprint that demands exactness turns
an ordinary week of work into a lost mount. So a match is partial —
:data:`MATCH_FLOOR` of the recorded anchors — and, the part that actually does
the work, **every successful locate rewrites the fingerprint**. Drift is
measured against the last time we saw the folder, never against the day it was
mounted, so gradual change never accumulates past the floor. Wholesale change
does fall below it, and that is correct: at that point the folder genuinely is
not distinguishable from a different folder, and the tool says ``lost`` rather
than guessing.

THE ASYMMETRY THIS ALSO FIXES
-----------------------------
Sidecars find their file by ``../<name>``, so they travel inside the folder and
survive a whole-folder move for free. Vault projections stored a path string
and broke — and after a move everything *looks* fine, because the sidecars
still resolve and only the governed entries the rest of the Studio reads are
pointing at nothing. Projections written for a mount carry ``mount_uid`` and
``mount_relpath`` beside the path, which is the pair a move preserves, so
``reconcile`` recomputes the stale handle instead of leaving it dangling.

WHAT THIS DOES NOT DO
---------------------
It never modifies a source file. Publishing back stays additive through
``tropo-export.py``'s ``stem v-NN`` scheme. It never hard-deletes governed
substrate — a moved folder is re-pointed, never recycled, because nothing went
away. And it does not gate READ on anything: an adopted body is ineligible to
cross to a model provider and stays fully readable on disk, because the model
provider is the second party that boundary defends against and there is no
second party inside the Studio (ADR-065).

USAGE
-----
    python3 vault/tools/tropo-folder.py mount <path> --name "Marketing"
    python3 vault/tools/tropo-folder.py adopt <mount-uid>
    python3 vault/tools/tropo-folder.py reconcile [<mount-uid>]
    python3 vault/tools/tropo-folder.py list

Surface frozen by Talos T37 in vault/tools/FOLDER-MOUNT-SURFACE.md; brief is
the checkpoint "the composition model" (5e6652ac).
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import types
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

TOOL_NAME = "tropo-folder"
TOOL_VERSION = "1.0.0"

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_STUDIO_ROOT = SCRIPT_DIR.parents[1]

# --------------------------------------------------------------------------- #
# The frozen surface (FOLDER-MOUNT-SURFACE.md). Neither lane invents a name.   #
# --------------------------------------------------------------------------- #

MOUNT_REGISTRY_REL = ".tropo-studio/folder-mounts.json"
UNMOUNT_MOVE_INTENT_REL = (
    ".tropo-studio/locks/folder-unmount-move.json"
)

STATE_ATTACHED = "attached"     # agents have hands on it. No metadata.
STATE_ADOPTED = "adopted"       # the same mount, tooled.
STATES = (STATE_ATTACHED, STATE_ADOPTED)

REGISTRY_SCHEMA_VERSION = 2

AVAILABILITY_AVAILABLE = "available"
AVAILABILITY_UNAVAILABLE = "unavailable"
AVAILABILITY_AMBIGUOUS = "ambiguous"
AVAILABILITIES = (
    AVAILABILITY_AVAILABLE,
    AVAILABILITY_UNAVAILABLE,
    AVAILABILITY_AMBIGUOUS,
)

#: Written into the mounted folder by ADOPT and never by attach. Adoption has
#: already earned `<folder>/.tropo-studio/`; attachment has not earned anything.
MOUNT_ANCHOR_REL = ".tropo-studio/.tropo-mount.json"

# --------------------------------------------------------------------------- #
# Fingerprint + search constants, gathered so they can be argued with.         #
# --------------------------------------------------------------------------- #

FINGERPRINT_VERSION = 1

#: How many files carry the fingerprint. Sampled evenly across the folder's
#: sorted paths rather than taken from the front, so deleting the alphabetically
#: first handful does not delete the fingerprint.
ANCHOR_MAX = 24

#: Bytes read per anchor. Re-identifying a folder is not an integrity check —
#: the sidecar's own `source_hash` is that, over the whole file — so a prefix is
#: enough and a multi-gigabyte video does not cost a full read to recognise.
ANCHOR_READ_CAP = 1 << 20

#: Ceiling on files walked when fingerprinting. A sync folder can be enormous;
#: past this the census is a sample and says so via `truncated`.
CENSUS_MAX_FILES = 20000

#: Fraction of recorded anchors a candidate STILL CALLED BY THE SAME NAME must
#: match. A third, because the fingerprint is refreshed on every locate, so this
#: is the bar for change since THE LAST SIGHTING rather than since the mount.
MATCH_FLOOR = 1.0 / 3.0

#: The bar for a candidate whose folder name is NOT the recorded one. A re-sync
#: renames the PARENT and leaves the leaf alone, so a differently-named folder
#: is a weaker claim and has to be nearly the same bytes to make it: the failure
#: this stops is a deleted mount being "re-found" as a similar folder nearby,
#: which re-anchors every governed entry onto somebody else's content.
RENAMED_FLOOR = 0.9

#: Two candidates this close are a tie, and a tie is refused rather than broken.
AMBIGUITY_MARGIN = 0.15

#: How deep under a search root to look. Three is one more than the re-sync
#: shape needs (`<grandparent>/<renamed parent>/<leaf>`), so a folder that also
#: gained a level is still found.
SEARCH_DEPTH = 3

#: Ceiling on directories visited per reconcile. A search that walks a whole
#: home directory is a hang, and a hang in a repair tool is worse than a miss.
SEARCH_MAX_DIRS = 4000

#: Never walked into, as candidates or as content.
SKIP_DIR_NAMES = frozenset({
    ".git", ".svn", ".hg", ".obsidian", ".tropo", ".tropo-studio",
    "node_modules", "__pycache__", ".venv", "venv",
})

LOCATED_UNCHANGED = "unchanged"
LOCATED_MOVED = "moved"
LOCATED_AMBIGUOUS = "ambiguous"
LOCATED_LOST = "lost"
#: The walk hit its visit ceiling before it finished. NOT the same as `lost`:
#: nothing was concluded, because the search never completed. Measured on a
#: real run — /tmp held 10,858 directories against a 4,000 ceiling, and the
#: folder was sitting in plain sight beyond the cut.
LOCATED_UNSEARCHED = "unsearched"


class FolderMountError(Exception):
    """Refusal, with a reason a human can act on. Never a bare non-zero exit."""


# --------------------------------------------------------------------------- #
# The import walker, loaded as a library.                                       #
#                                                                               #
# Adoption is not reimplemented here. `scan` / `create-sidecar` / `reconcile` / #
# `ingest` already work, are already the audited write path, and already carry  #
# the ordered-write protocol that keeps a folder mirror and its on-disk marker  #
# from diverging. A second copy of that protocol is a second protocol waiting   #
# to disagree with the first.                                                   #
# --------------------------------------------------------------------------- #

def _load_walker():
    path = SCRIPT_DIR / "tropo-import-walker.py"
    if not path.is_file():
        raise FolderMountError(
            f"the import walker is missing at {path}; folder adoption is its "
            "machinery and this tool does not carry a second copy"
        )
    spec = importlib.util.spec_from_file_location("_tropo_import_walker_for_folder", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


walker = _load_walker()


def _load_index_writer():
    path = SCRIPT_DIR / "tropo-rebuild-index.py"
    spec = importlib.util.spec_from_file_location(
        "_tropo_rebuild_index_for_folder",
        str(path),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


index_writer = _load_index_writer()


# --------------------------------------------------------------------------- #
# The record                                                                    #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FolderMount:
    """One mounted folder. A value, not a handle — the registry is the writable
    surface, and a record a caller can edit in memory without persisting is how
    a `mount_uid` gets lost."""

    mount_uid: str          # 8-hex, minted once, NEVER re-minted on a move
    name: str               # what a human calls it
    path: str               # absolute, as last resolved
    state: str              # one of STATES
    availability: str       # transient source reachability; not unmount lifecycle
    mounted_at: str
    mounted_by: str
    adopted_at: Optional[str]
    fingerprint: dict       # how we re-find this folder when `path` goes stale


@dataclass(frozen=True)
class AdoptReport:
    """What flipping the switch actually did."""

    mount_uid: str
    name: str
    path: str
    state: str
    availability: str
    adopted_at: Optional[str]
    already_adopted: bool
    sidecars_created: int
    sidecars_existing: int
    files_ignored: int
    failures: list = field(default_factory=list)
    created_paths: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReconcileReport:
    """What reconcile found, and what it repaired.

    `mounts` carries one entry per mount examined, each naming the mount and the
    path it was found at, so a repair nobody watched happen is still auditable.
    """

    checked: int = 0
    unchanged: int = 0
    moved: int = 0
    ambiguous: int = 0
    lost: int = 0
    #: The walk ran out of budget before finishing. Counted apart from `lost`
    #: because only `lost` is a conclusion.
    unsearched: int = 0
    #: Pointers that still do not resolve after the pass. The one number
    #: reconcile was missing: it can be non-zero while `projections_repaired`
    #: is zero, which is the state that got reported clean.
    projections_unresolved: list = field(default_factory=list)
    projections_checked: int = 0
    projections_repaired: int = 0
    projections_missing: int = 0
    projections_created: int = 0
    projections_tampered: list = field(default_factory=list)
    orphan_sidecars: list = field(default_factory=list)
    affected_files: list = field(default_factory=list)
    sidecars_created: int = 0
    sidecars_updated: int = 0
    mounts: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Small helpers                                                                 #
# --------------------------------------------------------------------------- #

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _actor(explicit: Optional[str] = None) -> str:
    """Who is doing this. Identity here is a mirror, not a lock: the point is
    that every action carries a name, not that the name cannot be forged."""
    for candidate in (explicit, os.environ.get("TROPO_EXECUTIVE"), os.environ.get("USER")):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return "unknown"


def _registry_path(root: Path) -> Path:
    return Path(root) / MOUNT_REGISTRY_REL


_REGISTRY_LOCKS_GUARD = threading.Lock()
_REGISTRY_LOCKS: dict[Path, threading.RLock] = {}


@contextmanager
def _registry_write_lock(root: Path):
    """Serialize registry read-modify-write across threads and processes."""
    lock_path = Path(root) / ".tropo-studio" / "locks" / "folder-mounts.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    resolved = lock_path.resolve()
    with _REGISTRY_LOCKS_GUARD:
        process_lock = _REGISTRY_LOCKS.setdefault(resolved, threading.RLock())
    with process_lock:
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _registry_operation_lock(root: Path):
    """Recover index state, then serialize registry mutation in one lock order."""
    root = Path(root).resolve()
    with index_writer.index_surfaces.index_write_lock(root):
        with _registry_write_lock(root):
            _recover_unmount_move_intent(root)
            yield


def _load_registry(root: Path) -> dict:
    """Read the registry. A studio with no mounts has no registry, and reading
    one that is not there must not create it — zero mounts is every studio's day
    one and it has to cost nothing."""
    path = _registry_path(root)
    if not path.is_file():
        return {"schema_version": REGISTRY_SCHEMA_VERSION, "mounts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FolderMountError(f"folder-mount registry at {path} is unreadable: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("mounts"), dict):
        raise FolderMountError(
            f"folder-mount registry at {path} does not match the expected shape "
            "(an object with a 'mounts' object)"
        )
    _migrate_legacy_registry_in_memory(Path(root).resolve(), data)
    return data


def _registry_bytes(data: dict) -> bytes:
    data["schema_version"] = REGISTRY_SCHEMA_VERSION
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _save_registry(root: Path, data: dict) -> None:
    path = _registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_registry_bytes(data))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        tmp.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_unmount_move_intent(
    root: Path,
    mount_uid: str,
    moves: list[tuple[Path, Path]],
    recycle_dir: Path,
    *,
    recycle_dir_existed: bool,
) -> Path:
    """Durably record projection moves before the first rename."""
    intent_path = root / UNMOUNT_MOVE_INTENT_REL
    intent_path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for source, destination in moves:
        raw = source.read_bytes()
        entries.append({
            "source": source.relative_to(root).as_posix(),
            "destination": destination.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    payload = {
        "schema_version": 1,
        "mount_uid": mount_uid,
        "recycle_dir": recycle_dir.relative_to(root).as_posix(),
        "recycle_dir_existed": recycle_dir_existed,
        "moves": entries,
    }
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{intent_path.name}.",
        suffix=".tmp",
        dir=str(intent_path.parent),
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(
                (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
                    "utf-8"
                )
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, intent_path)
        _fsync_directory(intent_path.parent)
    finally:
        tmp.unlink(missing_ok=True)
    return intent_path


def _recover_unmount_move_intent(root: Path) -> None:
    """Roll back or finish durable projection moves after process interruption."""
    root = Path(root).resolve()
    intent_path = root / UNMOUNT_MOVE_INTENT_REL
    if not intent_path.exists():
        return
    if intent_path.is_symlink():
        raise FolderMountError(
            f"unmount move intent {intent_path} is a symlink; refusing recovery"
        )
    try:
        payload = json.loads(intent_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FolderMountError(
            f"unmount move intent {intent_path} is unreadable: {exc}"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or not re.fullmatch(r"[0-9a-f]{8}", str(payload.get("mount_uid") or ""))
        or not isinstance(payload.get("moves"), list)
    ):
        raise FolderMountError(f"unmount move intent {intent_path} has invalid shape")
    mount_uid = str(payload["mount_uid"])
    recycle_dir = (root / str(payload.get("recycle_dir") or "")).resolve()
    recycle_root = (root / "recycle" / "agent-deletions").resolve()
    if (
        recycle_dir.parent != recycle_root
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", recycle_dir.name)
    ):
        raise FolderMountError(
            f"unmount move intent escapes recycle root: {recycle_dir}"
        )
    moves: list[tuple[Path, Path, str]] = []
    for entry in payload["moves"]:
        if not isinstance(entry, dict):
            raise FolderMountError("unmount move intent contains malformed move")
        source = (root / str(entry.get("source") or "")).resolve()
        destination = (root / str(entry.get("destination") or "")).resolve()
        digest = str(entry.get("sha256") or "")
        if (
            source.parent != (root / "vault" / "files").resolve()
            or not re.fullmatch(r"[0-9a-f]{8}\.md", source.name)
            or recycle_dir not in destination.parents
            or not destination.name.startswith(source.stem)
            or destination.suffix != ".md"
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise FolderMountError(
                "unmount move intent contains an unauthorized destination"
            )
        moves.append((source, destination, digest))

    registry = _load_registry(root)
    mount_present = mount_uid in (registry.get("mounts") or {})
    ordered = reversed(moves) if mount_present else iter(moves)
    for source, destination, digest in ordered:
        source_exists = source.is_file()
        destination_exists = destination.is_file()
        if source_exists and hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise FolderMountError(
                f"unmount recovery found changed projection {source}"
            )
        if (
            destination_exists
            and hashlib.sha256(destination.read_bytes()).hexdigest() != digest
        ):
            raise FolderMountError(
                f"unmount recovery found changed recycled projection {destination}"
            )
        if source_exists and destination_exists:
            raise FolderMountError(
                f"unmount recovery found both source and destination for {source.name}"
            )
        if mount_present:
            if destination_exists:
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, source)
                _fsync_directory(source.parent)
                _fsync_directory(destination.parent)
        elif source_exists:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            _fsync_directory(source.parent)
            _fsync_directory(destination.parent)

    intent_path.unlink()
    _fsync_directory(intent_path.parent)
    if mount_present and not payload.get("recycle_dir_existed"):
        try:
            recycle_dir.rmdir()
        except OSError:
            pass


def recover_pending_folder_transactions(root: Path) -> None:
    """Recover pending index and unmount move transactions before registry use."""
    root = Path(root).resolve()
    with index_writer.index_surfaces.index_write_lock(root):
        with _registry_write_lock(root):
            _recover_unmount_move_intent(root)


def _record_from_dict(mount_uid: str, raw: dict) -> FolderMount:
    """Rebuild a record from its registry entry.

    The uid is the KEY and is deliberately not repeated inside the value. One
    fact in two places is one fact that can disagree, and the fact this one
    would disagree about is the identity every governed entry pointing at the
    folder resolves through.
    """
    return FolderMount(
        mount_uid=str(mount_uid),
        name=str(raw.get("name", "")),
        path=str(raw.get("path", "")),
        state=str(raw.get("state", STATE_ATTACHED)),
        availability=str(raw.get("availability", AVAILABILITY_AVAILABLE)),
        mounted_at=str(raw.get("mounted_at", "")),
        mounted_by=str(raw.get("mounted_by", "")),
        adopted_at=raw.get("adopted_at") or None,
        fingerprint=raw.get("fingerprint") or {},
    )


def _record_to_dict(record: FolderMount) -> dict:
    """The stored form of a record: everything except the uid, which is the key."""
    stored = asdict(record)
    stored.pop("mount_uid", None)
    return stored


# --------------------------------------------------------------------------- #
# Fingerprinting                                                                #
# --------------------------------------------------------------------------- #

def _walkable(name: str) -> bool:
    return name not in SKIP_DIR_NAMES and not name.startswith(".")


def _census(path: Path) -> tuple[list, bool]:
    """Every ordinary file under `path`, as (relpath, size), plus a truncation flag.

    `.tropo-studio/` is skipped deliberately: adoption writes there, and a
    fingerprint that counted its own sidecars would stop matching the folder the
    moment the folder was adopted.
    """
    entries: list = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(d for d in dirnames if _walkable(d))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            candidate = Path(dirpath) / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            try:
                size = candidate.stat().st_size
            except OSError:
                continue
            entries.append((candidate.relative_to(path).as_posix(), size))
            if len(entries) >= CENSUS_MAX_FILES:
                truncated = True
                return sorted(entries), truncated
    return sorted(entries), truncated


def _anchor_digest(path: Path, size: int) -> Optional[str]:
    """Digest of a file's size and its first :data:`ANCHOR_READ_CAP` bytes."""
    digest = hashlib.sha256()
    digest.update(str(size).encode("ascii"))
    digest.update(b"\0")
    try:
        with path.open("rb") as handle:
            remaining = ANCHOR_READ_CAP
            while remaining > 0:
                chunk = handle.read(min(1 << 16, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _sample(entries: list) -> list:
    """Up to :data:`ANCHOR_MAX` entries spread evenly through the sorted list."""
    if len(entries) <= ANCHOR_MAX:
        return list(entries)
    step = (len(entries) + ANCHOR_MAX - 1) // ANCHOR_MAX
    return entries[::step][:ANCHOR_MAX]


def fingerprint_folder(path: Path) -> dict:
    """Everything we record about a folder so we can find it again without a path."""
    path = Path(path)
    entries, truncated = _census(path)
    anchors = []
    for rel, size in _sample(entries):
        digest = _anchor_digest(path / rel, size)
        if digest is not None:
            anchors.append({"rel": rel, "size": size, "digest": digest})
    census = hashlib.sha256(
        "\n".join(f"{rel}\0{size}" for rel, size in entries).encode("utf-8")
    ).hexdigest()
    return {
        "version": FINGERPRINT_VERSION,
        "taken_at": _now(),
        "folder_name": path.name,
        "file_count": len(entries),
        "total_bytes": sum(size for _rel, size in entries),
        "census": census,
        "truncated": truncated,
        "anchors": anchors,
        # An empty folder has no content to be recognised by. Saying so here is
        # better than inventing a match rule for a folder that could be any
        # empty folder on the machine: such a mount is re-findable only by its
        # anchor file, which means only once adopted.
        "weak": not anchors,
    }


def fingerprint_score(recorded: dict, candidate: Path) -> float:
    """How much of `recorded` is still present at `candidate`, from 0.0 to 1.0."""
    anchors = (recorded or {}).get("anchors") or []
    if not anchors:
        return 0.0
    hits = 0
    for anchor in anchors:
        target = candidate / anchor.get("rel", "")
        try:
            if not target.is_file() or target.stat().st_size != anchor.get("size"):
                continue
        except OSError:
            continue
        if _anchor_digest(target, anchor["size"]) == anchor.get("digest"):
            hits += 1
    return hits / len(anchors)


def read_mount_anchor(path: Path) -> Optional[str]:
    """The mount_uid an adopted folder carries, or None."""
    anchor = Path(path) / MOUNT_ANCHOR_REL
    if not anchor.is_file():
        return None
    try:
        data = json.loads(anchor.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    uid = data.get("mount_uid")
    return str(uid) if uid else None


def write_mount_anchor(path: Path, mount_uid: str, name: str, actor: str) -> Path:
    """Leave the folder able to say who it is. ADOPT only — attach writes nothing."""
    anchor = Path(path) / MOUNT_ANCHOR_REL
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mount_uid": mount_uid,
                "name": name,
                "written_at": _now(),
                "written_by": actor,
                "written_by_tool": f"{TOOL_NAME}-v{TOOL_VERSION}",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return anchor


# --------------------------------------------------------------------------- #
# Locating a mount whose path may have gone stale                               #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class LocateOutcome:
    status: str
    path: Optional[Path] = None
    score: float = 0.0
    by: str = ""
    candidates: list = field(default_factory=list)
    searched: int = 0


def _search_roots_for(record: FolderMount, extra: Optional[Iterable] = None) -> list:
    """Where to look for a folder that is not where we left it.

    The parent and the grandparent of the recorded path, because that is the
    shape a re-sync actually makes: the leaf keeps its name and the parent is
    renamed beside itself, so the folder is still inside the same grandparent.
    Anything wider is the caller's explicit choice via `--search-root`; walking
    up further on our own turns a repair into an unbounded scan of somebody's
    home directory.
    """
    roots: list = []
    # An explicitly named root goes FIRST, not last. The visit ceiling means
    # ordering is not cosmetic: put the defaults ahead of it and a big parent
    # directory burns the whole budget before the operator's own answer is ever
    # looked at. That is not hypothetical — the `unsearched` cure text tells
    # people to narrow the search with this flag, and appending it made that
    # advice false.
    for candidate in extra or ():
        resolved = Path(candidate).resolve()
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    recorded = Path(record.path)
    for candidate in (recorded.parent, recorded.parent.parent):
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return roots


def _candidate_dirs(roots: Iterable, blocked: set,
                    budget: Optional[dict] = None) -> Iterable:
    """Directories under `roots`, bounded by depth and by a visit ceiling.

    `budget` is an optional out-parameter: when the visit ceiling cuts the walk
    short, `budget["truncated"]` is set True so the caller can report "I stopped
    looking" instead of "there is nothing there".
    """
    seen: set = set()
    visited = 0
    for root in roots:
        root = Path(root)
        base_depth = len(root.parts)
        for dirpath, dirnames, _filenames in os.walk(root):
            here = Path(dirpath)
            dirnames[:] = sorted(
                d for d in dirnames
                if _walkable(d) and (here / d) not in blocked
            )
            if len(here.parts) - base_depth >= SEARCH_DEPTH:
                dirnames[:] = []
            if here in blocked or here in seen:
                continue
            seen.add(here)
            visited += 1
            if visited > SEARCH_MAX_DIRS:
                # Tell the caller the walk was CUT SHORT rather than finished.
                # A search that stopped early and one that finished empty are
                # different facts, and reporting the first as the second is a
                # bounded look presented as a conclusion — the failure this
                # Studio has spent the week naming. Signalled through a caller-
                # supplied dict because a generator's return value is invisible
                # to the `for` that drives it.
                if budget is not None:
                    budget["truncated"] = True
                return
            yield here


def locate(root: Path, record: FolderMount, *, registry: Optional[dict] = None,
           search_roots: Optional[Iterable] = None) -> LocateOutcome:
    """Answer "where is this folder now?" without trusting the recorded path."""
    root = Path(root).resolve()
    recorded = Path(record.path)
    registry = registry if registry is not None else _load_registry(root)

    # Other mounts' folders are not candidates for this one. Without this, two
    # mounts of near-identical folders can steal each other's identity the first
    # time either of them moves.
    blocked = {root}
    for uid, raw in (registry.get("mounts") or {}).items():
        if uid != record.mount_uid and raw.get("path"):
            blocked.add(Path(raw["path"]))

    if recorded.is_dir():
        anchor = read_mount_anchor(recorded)
        if anchor is None or anchor == record.mount_uid:
            # The path still holds a folder and nothing there claims to be a
            # different mount. Content may well have changed since the last
            # sighting; that is work happening, not a lost folder.
            return LocateOutcome(
                status=LOCATED_UNCHANGED,
                path=recorded.resolve(),
                score=1.0 if anchor == record.mount_uid else fingerprint_score(record.fingerprint, recorded),
                by="anchor" if anchor == record.mount_uid else "recorded-path",
            )

    # Two signals, kept apart rather than blended into one number: how much of
    # the recorded content is still there, and whether the folder is still
    # called what it was called. A weighted sum of the two would be a fudge
    # factor nobody could argue with; two named groups can be argued with.
    recorded_name = (record.fingerprint or {}).get("folder_name") or recorded.name
    named: list = []
    renamed: list = []
    searched = 0
    budget: dict = {}
    for candidate in _candidate_dirs(
        _search_roots_for(record, search_roots), blocked, budget
    ):
        searched += 1
        if read_mount_anchor(candidate) == record.mount_uid:
            return LocateOutcome(
                status=LOCATED_MOVED if candidate.resolve() != recorded else LOCATED_UNCHANGED,
                path=candidate.resolve(), score=1.0, by="anchor", searched=searched,
            )
        score = fingerprint_score(record.fingerprint, candidate)
        if candidate.name == recorded_name:
            if score >= MATCH_FLOOR:
                named.append((score, candidate.resolve()))
        elif score >= RENAMED_FLOOR:
            renamed.append((score, candidate.resolve()))

    for group in (named, renamed):
        group.sort(key=lambda pair: (-pair[0], str(pair[1])))

    def refuse(pool):
        return LocateOutcome(
            status=LOCATED_AMBIGUOUS,
            score=pool[0][0],
            candidates=[{"path": str(p), "score": round(s, 3)} for s, p in pool],
            searched=searched,
        )

    if not named and not renamed:
        # "I found nothing" and "I stopped looking" are different answers, and
        # only the first is a conclusion. Reporting a truncated walk as LOST
        # would tell an operator their folder is gone when the truth is that
        # the search root was too big — and they would go looking for a folder
        # that is sitting exactly where they left it.
        if budget.get("truncated"):
            return LocateOutcome(status=LOCATED_UNSEARCHED, searched=searched)
        return LocateOutcome(status=LOCATED_LOST, searched=searched)

    # A differently-named folder that fits the fingerprint BETTER than the
    # same-named one is a genuine conflict — the folder may have been renamed
    # while a stale copy kept the old name — and guessing between those two is
    # the guess most likely to be wrong in the way nobody notices.
    if named and renamed and renamed[0][0] - named[0][0] > AMBIGUITY_MARGIN:
        return refuse(named + renamed)

    pool = named or renamed
    best_score, best_path = pool[0]
    if any(best_score - entry[0] <= AMBIGUITY_MARGIN for entry in pool[1:]):
        # Refused rather than broken. Re-pointing a mount at the wrong copy
        # silently re-anchors every governed entry that names it, and nothing
        # downstream can tell.
        return refuse(pool)
    return LocateOutcome(
        status=LOCATED_MOVED if best_path != recorded.resolve() else LOCATED_UNCHANGED,
        path=best_path, score=best_score,
        by="fingerprint" if pool is named else "fingerprint (renamed folder)",
        searched=searched,
    )


# --------------------------------------------------------------------------- #
# mount — attach. No manifest, no git, no write into the folder.                #
# --------------------------------------------------------------------------- #

def _mint_mount_uid(taken: set) -> str:
    for _attempt in range(64):
        candidate = walker.generate_uid()
        if candidate not in taken:
            return candidate
    raise FolderMountError("could not mint a free mount_uid in 64 tries")


def mount(root, path, *, name, mounted_by=None) -> FolderMount:
    """Attach a folder. Requires nothing of it and writes nothing into it."""
    root = Path(root).resolve()
    with _registry_operation_lock(root):
        return _mount_locked(
            root,
            path,
            name=name,
            mounted_by=mounted_by,
        )


def _mount_locked(root, path, *, name, mounted_by=None) -> FolderMount:
    folder = Path(path).resolve()
    if not folder.is_dir():
        raise FolderMountError(f"{folder} does not exist or is not a directory")
    if not str(name or "").strip():
        raise FolderMountError("a mount needs a name — it is what a human calls this folder")

    registry = _load_registry(root)
    mounts_by_uid = registry.setdefault("mounts", {})

    for uid, raw in mounts_by_uid.items():
        if Path(raw.get("path", "")).resolve() == folder:
            raise FolderMountError(
                f"{folder} is already mounted as {uid} ({raw.get('name')!r}). One "
                f"folder is one mount; adopt it or reconcile it rather than "
                f"mounting it twice."
            )

    carried = read_mount_anchor(folder)
    if carried and carried in mounts_by_uid:
        raise FolderMountError(
            f"{folder} already carries the mount anchor for {carried} "
            f"({mounts_by_uid[carried].get('name')!r}), which is recorded at "
            f"{mounts_by_uid[carried].get('path')!r}. This folder MOVED; re-mounting "
            f"it would mint a second uid and orphan every governed entry naming the "
            f"first. Run: reconcile {carried}"
        )

    record = FolderMount(
        mount_uid=_mint_mount_uid(set(mounts_by_uid)),
        name=str(name).strip(),
        path=str(folder),
        state=STATE_ATTACHED,
        availability=AVAILABILITY_AVAILABLE,
        mounted_at=_now(),
        mounted_by=_actor(mounted_by),
        adopted_at=None,
        fingerprint=fingerprint_folder(folder),
    )
    mounts_by_uid[record.mount_uid] = _record_to_dict(record)
    _save_registry(root, registry)
    return record


# --------------------------------------------------------------------------- #
# adopt — the same mount, tooled.                                               #
# --------------------------------------------------------------------------- #

def _ingest(root: Path, folder: Path, mount_uid: str, actor: str) -> dict:
    """Run the import walker's one-gesture ingest over a folder outside the tree.

    Idempotent by the walker's own construction: a file that already has a
    sidecar is skipped, which is what makes re-running `adopt` a recovery rather
    than a duplication.
    """
    args = types.SimpleNamespace(
        root=str(folder),
        dry_run=False,
        json=True,
        run_uid=None,
        executive=actor,
        mount_uid=mount_uid,
        mount_root=str(folder),
    )
    buffer = io.StringIO()
    noise = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(noise):
        walker.cmd_ingest(args, root)
    try:
        return json.loads(buffer.getvalue().strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"created": 0, "already_governed": 0, "ignored": 0,
                "failed": 0, "created_files": [], "failed_files": []}


_TOMBSTONE_METADATA_FIELDS = (
    "uid", "type", "status", "title", "owner", "description",
    "source_filename", "created", "created_by", "modified", "modified_by",
    "schema_version",
)


def _mount_authority_snapshot(folder: Path) -> dict[str, dict]:
    """Derive the offline UID/identity set only from sidecars and markers."""
    snapshot: dict[str, dict] = {}
    authoritative = [
        *sorted(folder.rglob(".tropo-studio/*.tropo.md")),
        *sorted(folder.rglob(".tropo-studio/.tropo-folder.md")),
    ]
    for path in authoritative:
        metadata = walker.parse_frontmatter(path)
        uid = str(metadata.get("uid") or "")
        if not re.fullmatch(r"[0-9a-f]{8}", uid):
            continue
        snapshot[uid] = {
            key: metadata[key]
            for key in _TOMBSTONE_METADATA_FIELDS
            if metadata.get(key) not in (None, "")
        }
    return snapshot


_PROJECTION_OWNERSHIP_METADATA_FIELDS = (
    *_TOMBSTONE_METADATA_FIELDS,
    "mount_uid",
    "mount_relpath",
    "projection_authority",
    "governance",
    "source_path",
    "original_path",
    "source_sidecar",
    "mirror_of",
    "folder_marker_path",
)


def _projection_ownership_metadata(front: dict) -> dict:
    return {
        key: front[key]
        for key in _PROJECTION_OWNERSHIP_METADATA_FIELDS
        if front.get(key) not in (None, "")
    }


def _is_verified_mount_projection(
    projection: Path,
    front: dict,
    mount_uid: str,
    raw: dict,
) -> bool:
    """Accept current derived-only or the complete live legacy projection proof."""
    uid = projection.stem
    if (
        not re.fullmatch(r"[0-9a-f]{8}", uid)
        or str(front.get("uid") or "") != uid
        or str(front.get("mount_uid") or "") != mount_uid
    ):
        return False
    if front.get("projection_authority") == "derived-only":
        return True

    mount_relpath_raw = front.get("mount_relpath")
    mount_relpath = str(mount_relpath_raw or "")
    relative = Path(mount_relpath)
    recorded_path = str(raw.get("path") or "")
    source_path = str(
        front.get("source_path") or front.get("original_path") or ""
    )
    sidecar_path = str(front.get("source_sidecar") or "")
    if (
        mount_relpath_raw is None
        or relative.is_absolute()
        or ".." in relative.parts
        or not recorded_path
    ):
        return False
    sidecar_is_governed = (
        sidecar_path.endswith(".tropo.md")
        or sidecar_path.endswith(".tropo-folder.md")
    )
    if front.get("governance") == "tier-1-projection":
        return (
            bool(source_path)
            and bool(sidecar_path)
            and _is_within(source_path, recorded_path)
            and _is_within(sidecar_path, recorded_path)
            and sidecar_is_governed
            and str(front.get("source_filename") or "") == relative.name
        )
    if front.get("governance") != "tier-1-sidecar":
        return False
    try:
        body = projection.read_text(encoding="utf-8")
    except OSError:
        return False
    if str(front.get("type") or "") == "project":
        marker_path = str(
            front.get("folder_marker_path")
            or front.get("original_path")
            or ""
        )
        return (
            str(front.get("mirror_of") or "") == uid
            and bool(marker_path)
            and _is_within(marker_path, recorded_path)
            and "vault-resident MIRROR" in body
            and "folder-mirror UID-duplication sanctioned exception" in body
        )
    if (
        not source_path
        or not sidecar_path
        or not _is_within(source_path, recorded_path)
        or not _is_within(sidecar_path, recorded_path)
        or not sidecar_is_governed
    ):
        return False
    return (
        "(vault projection)" in body
        and (
            "Projection derived from sidecar" in body
            or "Strictly derived from the authoritative sidecar" in body
        )
    )


def _mount_projection_authority(
    root: Path,
    mount_uid: str,
    raw: dict,
) -> tuple[dict[str, dict], set[str]]:
    """Derive complete ownership from registry, sidecars, and verified projections."""
    authority: dict[str, dict] = {}
    suspects: set[str] = set()
    raw_metadata = raw.get("projection_metadata") or {}
    if isinstance(raw_metadata, dict):
        for uid, metadata in raw_metadata.items():
            uid = str(uid)
            if re.fullmatch(r"[0-9a-f]{8}", uid):
                authority[uid] = metadata if isinstance(metadata, dict) else {}
    for uid in raw.get("projection_uids") or ():
        uid = str(uid)
        if re.fullmatch(r"[0-9a-f]{8}", uid):
            authority.setdefault(uid, {})

    recorded_folder = Path(str(raw.get("path") or ""))
    if recorded_folder.is_dir():
        authority.update(_mount_authority_snapshot(recorded_folder))

    files = root / "vault" / "files"
    if files.is_dir():
        for projection in sorted(files.glob("*.md")):
            try:
                front = walker.parse_frontmatter(projection)
            except OSError:
                continue
            if str(front.get("mount_uid") or "") != mount_uid:
                continue
            uid = projection.stem
            if _is_verified_mount_projection(projection, front, mount_uid, raw):
                authority.setdefault(uid, _projection_ownership_metadata(front))
            else:
                suspects.add(uid)

    for uid in tuple(authority):
        projection = files / f"{uid}.md"
        if not projection.exists():
            continue
        try:
            front = walker.parse_frontmatter(projection)
        except OSError:
            suspects.add(uid)
            continue
        if not _is_verified_mount_projection(projection, front, mount_uid, raw):
            suspects.add(uid)
    return authority, suspects


def _indexed_mount_uids(root: Path, mount_uid: str) -> set[str]:
    """Find residual ownership claims on every canonical index record surface."""
    owned: set[str] = set()
    pair = (
        root / "vault" / "00-index.jsonl",
        root / "vault" / "00-archive-index.jsonl",
    )
    if all(path.is_file() for path in pair):
        for path in pair:
            for row in index_writer.index_surfaces.read_jsonl_strict(path):
                if str(row.get("mount_uid") or "") == mount_uid:
                    uid = str(row.get("uid") or "")
                    if re.fullmatch(r"[0-9a-f]{8}", uid):
                        owned.add(uid)
    sqlite_path = root / "vault" / "00-index.sqlite"
    if sqlite_path.is_file():
        uri = f"file:{sqlite_path.as_posix()}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as connection:
            for uid, fm_json in connection.execute(
                "SELECT uid, fm_json FROM entries"
            ):
                try:
                    front = json.loads(fm_json)
                except (TypeError, json.JSONDecodeError):
                    continue
                if str(front.get("mount_uid") or "") == mount_uid:
                    uid = str(uid)
                    if re.fullmatch(r"[0-9a-f]{8}", uid):
                        owned.add(uid)
    return owned


def _migrate_legacy_registry_in_memory(root: Path, data: dict) -> None:
    """Enrich schema-1 mounts without minting or changing any identity."""
    try:
        schema_version = int(data.get("schema_version", 1))
    except (TypeError, ValueError):
        schema_version = 1
    if schema_version >= REGISTRY_SCHEMA_VERSION:
        return
    for mount_uid, raw in (data.get("mounts") or {}).items():
        if not isinstance(raw, dict):
            continue
        mount_uid = str(mount_uid)
        authority, suspects = _mount_projection_authority(
            root, mount_uid, raw
        )
        indexed = _indexed_mount_uids(root, mount_uid)
        unresolved = suspects | (indexed - set(authority))
        if unresolved:
            raise FolderMountError(
                f"cannot safely migrate legacy mount {mount_uid}: unresolved "
                f"projection ownership for {', '.join(sorted(unresolved))}"
            )
        raw["projection_uids"] = sorted(authority)
        raw["projection_metadata"] = authority


def _projection_hashes(root: Path, uids: Iterable[str]) -> dict[str, str]:
    hashes = {}
    for uid in sorted(set(uids)):
        path = Path(root) / "vault" / "files" / f"{uid}.md"
        if path.is_file():
            hashes[uid] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _capture_file_snapshot(
    snapshots: dict[Path, Optional[bytes]],
    path: Path,
) -> None:
    """Remember created-vs-existing state before a projection transaction."""
    if path not in snapshots:
        snapshots[path] = path.read_bytes() if path.is_file() else None


def _restore_file_snapshots(
    snapshots: dict[Path, Optional[bytes]],
) -> None:
    """Restore every captured path byte-exactly after index refusal."""
    failures = []
    for path, original in reversed(tuple(snapshots.items())):
        try:
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
        except OSError as exc:
            failures.append(f"{path}: {exc}")
    if failures:
        raise FolderMountError(
            "projection rollback was incomplete: " + "; ".join(failures)
        )


def adopt(root, mount_uid, *, executive=None) -> AdoptReport:
    """Flip the SAME mount to adopted. Never mints a second record."""
    root = Path(root).resolve()
    with _registry_operation_lock(root):
        return _adopt_locked(root, mount_uid, executive=executive)


def _adopt_locked(root, mount_uid, *, executive=None) -> AdoptReport:
    registry = _load_registry(root)
    raw = (registry.get("mounts") or {}).get(mount_uid)
    if raw is None:
        raise FolderMountError(
            f"no folder mount {mount_uid!r} in {MOUNT_REGISTRY_REL}. Adoption flips "
            f"a switch on a mount that already exists; it does not create one."
        )
    record = _record_from_dict(mount_uid, raw)
    actor = _actor(executive)

    outcome = locate(root, record, registry=registry)
    if outcome.status in (LOCATED_LOST, LOCATED_AMBIGUOUS, LOCATED_UNSEARCHED):
        raise FolderMountError(
            f"cannot adopt {mount_uid}: its folder is {outcome.status} "
            f"({_outcome_detail(record, outcome)}). Reconcile it first."
        )
    folder = outcome.path

    _preflight_mount_uid_collisions(root, folder, record.mount_uid)
    # The anchor goes down BEFORE the sidecars. A crash halfway through ingest
    # then leaves a folder that can still say who it is, which is the state that
    # makes the retry a retry rather than a rediscovery.
    write_mount_anchor(folder, record.mount_uid, record.name, actor)

    result = _ingest(root, folder, record.mount_uid, actor)
    raw["path"] = str(folder)
    raw["state"] = STATE_ADOPTED
    raw["availability"] = AVAILABILITY_AVAILABLE
    already = bool(record.adopted_at)
    if not already:
        raw["adopted_at"] = _now()
    raw["fingerprint"] = fingerprint_folder(folder)
    authority = _mount_authority_snapshot(folder)
    raw["projection_uids"] = sorted(authority)
    raw["projection_metadata"] = authority
    raw["last_checked"] = _now()
    _repair_projections(
        root,
        folder,
        record.mount_uid,
        registry=registry,
        registry_raw=raw,
    )
    desired_registry = _registry_bytes(registry)
    if (
        not _registry_path(root).is_file()
        or _registry_path(root).read_bytes() != desired_registry
    ):
        _save_registry(root, registry)

    return AdoptReport(
        mount_uid=record.mount_uid,
        name=record.name,
        path=str(folder),
        state=STATE_ADOPTED,
        availability=AVAILABILITY_AVAILABLE,
        adopted_at=raw.get("adopted_at"),
        already_adopted=already,
        sidecars_created=int(result.get("created", 0)),
        sidecars_existing=int(result.get("already_governed", 0)),
        files_ignored=int(result.get("ignored", 0)),
        failures=list(result.get("failed_files", []) or []),
        created_paths=list(result.get("created_files", []) or []),
    )


# --------------------------------------------------------------------------- #
# Projection repair — the derived side of invariant 8                           #
# --------------------------------------------------------------------------- #

def _frontmatter_bounds(text: str) -> Optional[tuple]:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    return 3, end


def _yaml_value(raw: str):
    """Read a frontmatter scalar the way the walker reads one.

    Deliberately the walker's own parser rather than a second one. The values a
    repair compares against come from `walker.parse_frontmatter`, and a reader
    that returns the string "6" where that one returns the integer 6 reports a
    difference on every pass forever.
    """
    return walker._parse_scalar(raw.strip())


def _read_field(text: str, key: str):
    bounds = _frontmatter_bounds(text)
    if bounds is None:
        return None
    block = text[bounds[0]:bounds[1]]
    for line in block.splitlines():
        if line.startswith(f"{key}:"):
            return _yaml_value(line.split(":", 1)[1])
    return None


def _rewrite_frontmatter(path: Path, updates: dict) -> list:
    """Set frontmatter fields on a derived projection. Returns the keys changed.

    Writes nothing when nothing differs. That matters more than it looks: a
    reconcile that rewrites a correct projection churns governed substrate every
    time anybody runs the tool, and it makes every drift case pass for the wrong
    reason.
    """
    text = path.read_text(encoding="utf-8")
    bounds = _frontmatter_bounds(text)
    if bounds is None:
        return []
    start, end = bounds
    block = text[start:end]
    lines = block.splitlines()
    changed: list = []

    for key, value in updates.items():
        if value is None:
            continue
        rendered = f"{key}: {walker._yaml_str(value) if isinstance(value, str) else value}"
        for index, line in enumerate(lines):
            if line.startswith(f"{key}:"):
                if _yaml_value(line.split(":", 1)[1]) != value:
                    lines[index] = rendered
                    changed.append(key)
                break
        else:
            lines.append(rendered)
            changed.append(key)

    if not changed:
        return []
    updated = text[:start] + "\n".join(lines) + text[end:]
    if updated == text:
        # A difference the reader saw and the writer cannot express is not a
        # repair. Counting one would make every reconcile look like it fixed
        # something, which is exactly how a repair that never fires hides.
        return []
    path.write_text(updated, encoding="utf-8")
    return changed


def _refresh_body_links(path: Path, source: Optional[str], sidecar: Optional[str]) -> bool:
    """Keep the two advisory links in a projection body pointing somewhere real."""
    text = path.read_text(encoding="utf-8")
    original = text
    for label, target in (("Source", source), ("Sidecar", sidecar)):
        if not target:
            continue
        quoted = walker._url_quote_path(target)
        replacement = f"**{label}:** [{target}]({quoted})"
        out = []
        for line in text.splitlines(keepends=True):
            if line.startswith(f"**{label}:** "):
                out.append(replacement + ("\n" if line.endswith("\n") else ""))
            else:
                out.append(line)
        text = "".join(out)
    if text == original:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _refresh_marker_mention(path: Path, marker: Optional[str]) -> bool:
    """A folder mirror's body names its on-disk marker in a code span.

    Not a link, so `_refresh_body_links` does not reach it, and stale anyway
    after a move: the mirror would be telling a reader to go look at a path that
    is not there.
    """
    if not marker:
        return False
    text = path.read_text(encoding="utf-8")
    out = []
    changed = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if (stripped.startswith("`") and stripped.rstrip(".").endswith("`")
                and ".tropo-folder.md" in stripped and stripped != f"`{marker}`."):
            out.append(line.replace(stripped, f"`{marker}`."))
            changed = True
        else:
            out.append(line)
    if not changed:
        return False
    path.write_text("".join(out), encoding="utf-8")
    return True


def _frontmatter_from_text(text: str) -> dict:
    bounds = _frontmatter_bounds(text)
    if bounds is None:
        return {}
    return walker._parse_yaml(text[bounds[0]:bounds[1]])


_EXPECTED_DRIFT_FIELDS = {
    "source_sidecar", "source_path", "original_path", "mount_relpath",
    "folder_marker_path", "availability", "projection_authority",
}


def _without_frontmatter_fields(text: str, fields: set[str]) -> str:
    bounds = _frontmatter_bounds(text)
    if bounds is None:
        return text
    block = text[bounds[0]:bounds[1]]
    lines = block.splitlines()
    output = []
    index = 0
    while index < len(lines):
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(?:\s|$)", lines[index])
        if match and match.group(1) in fields:
            index += 1
            while index < len(lines) and (
                not lines[index]
                or lines[index].startswith((" ", "\t"))
            ):
                index += 1
            continue
        output.append(lines[index])
        index += 1
    return "\n".join(output)


def _projection_tamper_reasons(current: str, canonical_current: str) -> list[str]:
    """Report frontmatter and body edits independently of expected drift."""
    current_bounds = _frontmatter_bounds(current)
    canonical_bounds = _frontmatter_bounds(canonical_current)
    if current_bounds is None or canonical_bounds is None:
        return ["frontmatter", "body"]
    reasons = []
    if _without_frontmatter_fields(
        current, _EXPECTED_DRIFT_FIELDS
    ) != _without_frontmatter_fields(
        canonical_current, _EXPECTED_DRIFT_FIELDS
    ):
        # Compare only frontmatter here; body is classified independently below.
        current_front = current[current_bounds[0]:current_bounds[1]]
        canonical_front = canonical_current[
            canonical_bounds[0]:canonical_bounds[1]
        ]
        if _without_frontmatter_fields(
            f"---{current_front}\n---", _EXPECTED_DRIFT_FIELDS
        ) != _without_frontmatter_fields(
            f"---{canonical_front}\n---", _EXPECTED_DRIFT_FIELDS
        ):
            reasons.append("frontmatter")
    current_body = current[current_bounds[1] + 4:].strip()
    canonical_body = canonical_current[canonical_bounds[1] + 4:].strip()
    if current_body != canonical_body:
        reasons.append("body")
    return reasons


def _freshen_projection_index(
    root: Path,
    staged: dict[Path, bytes],
    *,
    registry_bytes: Optional[bytes] = None,
) -> int:
    """Advance all touched UIDs through the canonical cross-surface writer."""
    uids = {
        projection.stem
        for projection in staged
        if re.fullmatch(r"[0-9a-f]{8}", projection.stem)
    }
    if not uids:
        return 0
    vault = Path(root) / "vault"
    canonical_ready = all(
        path.is_file()
        for path in (
            vault / "00-index.jsonl",
            vault / "00-archive-index.jsonl",
            vault / "00-index.sqlite",
        )
    )
    if canonical_ready:
        companions = (
            ((_registry_path(root), registry_bytes),)
            if registry_bytes is not None
            else ()
        )
        code = index_writer.freshen_many(
            uids,
            Path(root),
            source_replacements=staged,
            companion_replacements=companions,
        )
    else:
        current = vault / "00-index.jsonl"
        if (
            current.is_file()
            and current.stat().st_size == 0
            and not (vault / "00-archive-index.jsonl").exists()
            and not (vault / "00-index.sqlite").exists()
        ):
            # Legacy first-gen fixtures install an empty placeholder. It carries
            # no rows or floor evidence; removing it lets the canonical writer
            # perform its explicit initial-surface transaction.
            current.unlink()
        snapshots: dict[Path, Optional[bytes]] = {}
        try:
            for projection, raw in staged.items():
                _capture_file_snapshot(snapshots, projection)
                projection.write_bytes(raw)
            code = index_writer.rebuild_index(Path(root), True)
        except Exception:
            _restore_file_snapshots(snapshots)
            raise
    if code != 0:
        raise FolderMountError(
            "canonical index transaction refused projection batch "
            f"{', '.join(sorted(uids))}; projection files changed but no index "
            "surface was reported current"
        )
    return len(uids)


def _assert_projection_destination(
    projection: Path,
    expected: str,
    mount_uid: str,
    *,
    authoritative_uid: bool = False,
) -> None:
    """Refuse a UID claim that would overwrite unrelated governed content."""
    if not projection.is_file():
        return
    existing = walker.parse_frontmatter(projection)
    desired = walker._parse_yaml(
        expected[_frontmatter_bounds(expected)[0]:_frontmatter_bounds(expected)[1]]
    )
    # `projection_authority: derived-only` is written by the post-migration
    # writer, so requiring it here refuses every LEGACY projection -- the exact
    # population migration converts. Ownership (uid + mount_uid) plus one
    # matching location field is what proves this is the mount's own projection
    # rather than an unrelated entry. See the twin gate in
    # _preflight_mount_uid_collisions (metis-g99 2026-08-02, first real mount).
    same_authority = (
        str(existing.get("uid") or "") == projection.stem
        and str(existing.get("mount_uid") or "") == mount_uid
        and (
            authoritative_uid
            or any(
                existing.get(field)
                and existing.get(field) == desired.get(field)
                for field in (
                    "mount_relpath",
                    "source_sidecar",
                    "folder_marker_path",
                )
            )
        )
    )
    if not same_authority:
        raise FolderMountError(
            "UID_COLLISION: authoritative mount "
            f"{mount_uid} claims {projection.stem}, but {projection} is not its "
            "derived-only projection"
        )


def _preflight_mount_uid_collisions(
    root: Path,
    folder: Path,
    mount_uid: str,
) -> None:
    """Check every existing authoritative UID claim before any mount write."""
    claims: list[tuple[str, str]] = []
    for sidecar in sorted(folder.rglob("*.tropo.md")):
        if sidecar.name == ".tropo-folder.md":
            continue
        front = walker.parse_frontmatter(sidecar)
        uid = str(front.get("uid") or "")
        if re.fullmatch(r"[0-9a-f]{8}", uid):
            source = (
                sidecar.parent / str(front.get("source_path") or "")
            ).resolve()
            try:
                claims.append((uid, source.relative_to(folder).as_posix()))
            except ValueError:
                continue
    for marker in sorted(folder.rglob(".tropo-studio/.tropo-folder.md")):
        front = walker.parse_frontmatter(marker)
        uid = str(front.get("uid") or "")
        if re.fullmatch(r"[0-9a-f]{8}", uid):
            claims.append(
                (
                    uid,
                    marker.parent.parent.relative_to(folder).as_posix(),
                )
            )
    for uid, mount_relpath in claims:
        projection = root / "vault" / "files" / f"{uid}.md"
        if not projection.is_file():
            continue
        existing = walker.parse_frontmatter(projection)
        # This gate asks one question: would the claim replace an UNRELATED
        # entry? Ownership answers that, and `mount_uid` is what carries it.
        #
        # `projection_authority: derived-only` describes a projection's FORMAT,
        # not its owner, and it is written by the post-migration writer. Testing
        # it here made every LEGACY projection look unrelated, so the preflight
        # refused every legacy mount -- and a legacy mount is precisely what
        # migration exists to convert. Same chicken-and-egg as the index-surface
        # seal: the gate demanded the state that only the gated step produces.
        # Found on the studio's first real folder mount, whose 54 projections
        # were all legacy (metis-g99 2026-08-02).
        #
        # The real protection is intact: a projection with a DIFFERENT or
        # MISSING mount_uid still raises, which is correct -- that is an entry
        # this mount cannot prove it owns.
        if not (
            str(existing.get("uid") or "") == uid
            and str(existing.get("mount_uid") or "") == mount_uid
        ):
            raise FolderMountError(
                f"UID_COLLISION: authoritative sidecar/folder claim {uid} "
                f"would replace unrelated governed entry {projection}"
            )


def _repair_projections(
    root: Path,
    folder: Path,
    mount_uid: str,
    *,
    registry: Optional[dict] = None,
    registry_raw: Optional[dict] = None,
) -> dict:
    """Fully regenerate every projection from its authoritative sidecar."""
    files = Path(root) / "vault" / "files"
    stats = {
        "checked": 0, "repaired": 0, "missing": 0, "created": 0,
        "markers_repaired": 0, "repaired_uids": [], "tampered": [],
        "unresolved": [], "orphan_sidecars": [], "index_updated": 0,
    }
    if not files.is_dir():
        return stats
    staged: dict[Path, bytes] = {}
    file_snapshots: dict[Path, Optional[bytes]] = {}
    member_rows: dict[str, list[dict]] = {}

    def record_render(
        uid: str,
        projection: Path,
        expected: str,
        canonical_current: Optional[str] = None,
    ) -> None:
        stats["checked"] += 1
        existed = projection.is_file()
        current = ""
        if existed:
            try:
                current = projection.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                current = ""
        else:
            stats["missing"] += 1
        if current == expected:
            return
        reasons = (
            _projection_tamper_reasons(
                current,
                canonical_current if canonical_current is not None else expected,
            )
            if existed else []
        )
        _assert_projection_destination(
            projection,
            expected,
            mount_uid,
            authoritative_uid=True,
        )
        stats["repaired"] += 1
        stats["repaired_uids"].append(uid)
        if not existed:
            stats["created"] += 1
        if reasons:
            stats["tampered"].append(
                {
                    "uid": uid,
                    "path": str(projection),
                    "repaired": True,
                    "edits": reasons,
                }
            )
        staged[projection] = expected.encode("utf-8")

    for sidecar in sorted(folder.rglob(".tropo-studio/*.tropo.md")):
        front = walker.parse_frontmatter(sidecar)
        uid = str(front.get("uid") or "")
        if not uid:
            continue
        source = (sidecar.parent / str(front.get("source_path", ""))).resolve()
        members = front.get("member_of") or []
        member = members[0] if isinstance(members, list) and members else ""
        availability = (
            AVAILABILITY_AVAILABLE if source.is_file()
            else AVAILABILITY_UNAVAILABLE
        )
        expected = walker.render_projection_from_sidecar(
            sidecar,
            source,
            mount_uid=mount_uid,
            mount_root=folder,
            availability=availability,
        )
        projection = files / f"{uid}.md"
        canonical_current = expected
        if projection.is_file():
            current_front = walker.parse_frontmatter(projection)
            current_availability = str(
                current_front.get("availability") or AVAILABILITY_AVAILABLE
            )
            if current_availability == AVAILABILITY_AVAILABLE:
                current_source = Path(
                    str(current_front.get("source_path") or source)
                )
                canonical_current = walker.render_projection_from_sidecar(
                    sidecar,
                    current_source,
                    mount_uid=mount_uid,
                    mount_root=folder,
                    availability=AVAILABILITY_AVAILABLE,
                    sidecar_reference=str(
                        current_front.get("source_sidecar") or sidecar
                    ),
                )
            else:
                canonical_current = walker.render_unavailable_projection(
                    front,
                    mount_uid,
                    current_availability,
                )
        record_render(uid, projection, expected, canonical_current)
        if member:
            member_rows.setdefault(str(member), []).append({
                "uid": uid,
                "title": str(front.get("title") or front.get("source_filename") or uid),
                "type": str(front.get("type") or "external-artifact"),
                "created": str(front.get("created") or ""),
            })
        if not source.is_file():
            stats["orphan_sidecars"].append({
                "sidecar_path": str(sidecar),
                "uid": uid,
                "missing_source": str(source),
            })

    for marker in sorted(folder.rglob(".tropo-studio/.tropo-folder.md")):
        mirrored = marker.parent.parent
        _capture_file_snapshot(file_snapshots, marker)
        _rewrite_frontmatter(marker, {"original_path": str(mirrored)})
        front = walker.parse_frontmatter(marker)
        uid = str(front.get("uid") or "")
        if not uid:
            continue
        members = front.get("member_of") or []
        member = members[0] if isinstance(members, list) and members else walker.TROPO_WORK_L0_UID
        rows = sorted(
            member_rows.get(uid, []),
            key=lambda row: (row["created"], row["uid"]),
        )
        if rows:
            lines = [
                "\n## Members\n",
                "| UID | Title | Type |",
                "|---|---|---|",
            ]
            for row in rows:
                escaped_title = row["title"].replace("|", "\\|")
                lines.append(
                    f"| [{row['uid']}]({row['uid']}.md) | "
                    f"{escaped_title} | {row['type']} |"
                )
            members_section = "\n".join(lines) + "\n"
        else:
            members_section = "\n## Members\n\n(No governed members yet.)\n"
        expected = walker.render_folder_mirror(
            root, uid, str(front.get("title") or mirrored.name), str(marker),
            str(marker), str(member),
            str(front.get("governance") or "tier-1-sidecar"),
            mount_uid, walker.mount_relative_path(folder, mirrored),
            AVAILABILITY_AVAILABLE, front.get("owner"), front.get("created"),
            front.get("created_by"), front.get("modified"),
            front.get("modified_by"), front.get("schema_version") or 2,
            members_section,
        )
        before_repaired = stats["repaired"]
        try:
            record_render(uid, files / f"{uid}.md", expected)
        except Exception:
            _restore_file_snapshots(file_snapshots)
            raise
        if stats["repaired"] != before_repaired:
            stats["markers_repaired"] += 1

    if registry_raw is not None:
        projected_hashes = _projection_hashes(
            root,
            registry_raw.get("projection_uids") or (),
        )
        for projection, raw in staged.items():
            projected_hashes[projection.stem] = hashlib.sha256(raw).hexdigest()
        registry_raw["projection_hashes"] = projected_hashes
    try:
        stats["index_updated"] = _freshen_projection_index(
            root,
            staged,
            registry_bytes=(
                _registry_bytes(registry) if registry is not None else None
            ),
        )
    except Exception:
        _restore_file_snapshots(file_snapshots)
        raise
    for projection in sorted(files.glob("*.md")):
        if projection.stem not in {
            str(walker.parse_frontmatter(path).get("uid") or "")
            for path in (
                *folder.rglob(".tropo-studio/*.tropo.md"),
                *folder.rglob(".tropo-studio/.tropo-folder.md"),
            )
        }:
            continue
        front = walker.parse_frontmatter(projection)
        if front.get("availability") != AVAILABILITY_AVAILABLE:
            continue
        for field in ("source_path", "source_sidecar", "folder_marker_path"):
            target = front.get(field)
            if target and not Path(str(target)).exists():
                stats["unresolved"].append(
                    {"uid": projection.stem, "field": field, "points_at": str(target)}
                )
    return stats


def _mark_mount_projections_unavailable(
    root: Path,
    record: FolderMount,
    availability: str,
    *,
    authoritative_uids: Iterable[str],
    projection_metadata: dict,
    projection_hashes: dict,
    registry: Optional[dict] = None,
    registry_raw: Optional[dict] = None,
) -> dict:
    """Keep link targets but remove stale source-derived edges and body links."""
    files = Path(root) / "vault" / "files"
    affected = []
    touched = []
    staged: dict[Path, bytes] = {}
    tampered = []
    repaired = 0
    file_snapshots: dict[Path, Optional[bytes]] = {}
    if not files.is_dir():
        return {
            "affected_files": affected, "checked": 0, "repaired": repaired,
            "tampered": [], "projection_hashes": {}, "index_updated": 0,
        }
    owned_uids = {
        str(uid) for uid in authoritative_uids
        if re.fullmatch(r"[0-9a-f]{8}", str(uid))
    }
    for uid in sorted(owned_uids):
        projection = files / f"{uid}.md"
        if not projection.is_file():
            continue
        front = walker.parse_frontmatter(projection)
        if (
            str(front.get("uid") or "") != uid
            or str(front.get("mount_uid") or "") != record.mount_uid
            or front.get("projection_authority") != "derived-only"
        ):
            continue
        current = projection.read_text(encoding="utf-8", errors="replace")
        current_hash = hashlib.sha256(projection.read_bytes()).hexdigest()
        prior_hash = str(projection_hashes.get(uid) or "")
        expected = walker.render_unavailable_projection(
            projection_metadata.get(uid) or front,
            record.mount_uid,
            availability,
        )
        if prior_hash and current_hash != prior_hash:
            edits = ["frontmatter-or-body"]
            if front.get("availability") in (
                AVAILABILITY_UNAVAILABLE,
                AVAILABILITY_AMBIGUOUS,
            ):
                classified = _projection_tamper_reasons(current, expected)
                if classified:
                    edits = classified
            tampered.append({
                "uid": uid,
                "path": str(projection),
                "repaired": True,
                "edits": edits,
            })
        if current != expected:
            _assert_projection_destination(
                projection,
                expected,
                record.mount_uid,
                authoritative_uid=True,
            )
            staged[projection] = expected.encode("utf-8")
            repaired += 1
        affected.append({
            "uid": projection.stem,
            "name": str(
                front.get("source_filename") or front.get("title") or projection.stem
            ),
            "availability": availability,
        })
        touched.append(projection)
    changed = [
        projection
        for projection in touched
        if str(projection.stem) in {
            item["uid"] for item in tampered
        }
        or hashlib.sha256(
            staged.get(projection, projection.read_bytes())
        ).hexdigest()
        != str(projection_hashes.get(projection.stem) or "")
    ]
    staged_changed = {
        projection: staged[projection]
        for projection in changed
        if projection in staged
    }
    projected_hashes = dict(projection_hashes)
    for projection, raw in staged_changed.items():
        projected_hashes[projection.stem] = hashlib.sha256(raw).hexdigest()
    if registry_raw is not None:
        registry_raw["projection_hashes"] = projected_hashes
        registry_raw["availability"] = availability
        registry_raw["last_checked"] = _now()
    try:
        index_updated = _freshen_projection_index(
            root,
            staged_changed,
            registry_bytes=(
                _registry_bytes(registry) if registry is not None else None
            ),
        )
    except Exception:
        _restore_file_snapshots(file_snapshots)
        raise
    return {
        "affected_files": affected,
        "checked": len(touched),
        "repaired": repaired,
        "tampered": tampered,
        "projection_hashes": projected_hashes,
        "index_updated": index_updated,
    }


# --------------------------------------------------------------------------- #
# Sidecar-layer reconcile, for an adopted mount                                 #
# --------------------------------------------------------------------------- #

def _reconcile_sidecars(root: Path, folder: Path, mount_uid: str, actor: str) -> dict:
    """New files get sidecars; changed files get their recorded hash refreshed.

    Both passes are the import walker's, run over a root outside the tree. What
    they are NOT allowed to do is rewrite a sidecar that is already correct: the
    sidecar is canonical substrate, and churning it to fix a derived surface is
    invariant 8 upside down.
    """
    patterns = walker.parse_tropoignore(root)
    events: list = []
    walker._detect_deltas_in_ungoverned_folders(
        root, patterns, events, scan_root=folder,
        mount_uid=mount_uid, mount_root=folder,
    )
    for governed in sorted(folder.rglob(".tropo-studio/.tropo-folder.md")):
        walker._detect_deltas_in_folder(
            governed.parent.parent, root, patterns, events,
            mount_uid=mount_uid, mount_root=folder,
        )

    created = updated = 0
    if any(event.get("action") == "create_sidecar" for event in events):
        result = _ingest(root, folder, mount_uid, actor)
        created = int(result.get("created", 0))
    for event in events:
        if event.get("action") == "update_sidecar_metadata":
            ok, _err = walker._apply_update_sidecar_metadata(root, event)
            updated += 1 if ok else 0
    return {
        "sidecars_created": created,
        "sidecars_updated": updated,
        "deferred": [event for event in events
                     if event.get("action") in ("surface_to_user", "judgment")],
    }


# --------------------------------------------------------------------------- #
# reconcile                                                                     #
# --------------------------------------------------------------------------- #

def _outcome_detail(record: FolderMount, outcome: LocateOutcome) -> str:
    if outcome.status == LOCATED_AMBIGUOUS:
        listed = ", ".join(f"{c['path']} ({c['score']})" for c in outcome.candidates)
        return (
            f"{len(outcome.candidates)} folders match the fingerprint and no one of "
            f"them stands out: {listed}. Nothing was changed. Name the right one with "
            f"`reconcile {record.mount_uid} --resolve <path>`."
        )
    if outcome.status == LOCATED_UNSEARCHED:
        return (
            f"the search stopped after {outcome.searched} directories without "
            f"finishing, so nothing was concluded — the folder may be sitting "
            f"exactly where you left it, just beyond where the walk got to. "
            f"Point the search somewhere smaller with `--search-root <dir>`, or "
            f"name the folder outright with `--resolve <path>`"
        )
    if outcome.status == LOCATED_LOST:
        weak = (record.fingerprint or {}).get("weak")
        return (
            f"nothing under {Path(record.path).parent} or its parent matches the "
            f"fingerprint recorded at {(record.fingerprint or {}).get('taken_at', '?')}"
            + (" (the folder was empty when mounted, so it has no content to be "
               "recognised by)" if weak else "")
            + ". Nothing was changed. Widen the search with `--search-root <dir>`, or "
              "name the folder with `--resolve <path>`."
        )
    return outcome.status


def reconcile(root, mount_uid=None, *, search_roots=None, resolve_path=None,
              executive=None, dry_run=False) -> ReconcileReport:
    """Re-find every mount whose path has gone stale, and repair what it broke."""
    root = Path(root).resolve()
    with _registry_operation_lock(root):
        return _reconcile_locked(
            root,
            mount_uid,
            search_roots=search_roots,
            resolve_path=resolve_path,
            executive=executive,
            dry_run=dry_run,
        )


def _reconcile_locked(root, mount_uid=None, *, search_roots=None, resolve_path=None,
                      executive=None, dry_run=False) -> ReconcileReport:
    registry = _load_registry(root)
    all_mounts = registry.get("mounts") or {}
    if mount_uid is not None and mount_uid not in all_mounts:
        raise FolderMountError(f"no folder mount {mount_uid!r} in {MOUNT_REGISTRY_REL}")
    targets = [mount_uid] if mount_uid else sorted(all_mounts)
    actor = _actor(executive)

    report = {"checked": 0, "unchanged": 0, "moved": 0, "ambiguous": 0, "lost": 0,
              "unsearched": 0,
              "projections_checked": 0, "projections_repaired": 0,
              "projections_unresolved": [],
              "projections_missing": 0, "projections_created": 0,
              "projections_tampered": [], "orphan_sidecars": [],
              "affected_files": [], "sidecars_created": 0,
              "sidecars_updated": 0, "mounts": []}
    dirty = False

    for uid in targets:
        raw = all_mounts[uid]
        record = _record_from_dict(uid, raw)
        report["checked"] += 1

        if resolve_path is not None and mount_uid == uid:
            named = Path(resolve_path).resolve()
            if not named.is_dir():
                raise FolderMountError(f"--resolve {named} is not a directory")
            outcome = LocateOutcome(
                status=LOCATED_UNCHANGED if named == Path(record.path).resolve() else LOCATED_MOVED,
                path=named, score=fingerprint_score(record.fingerprint, named), by="human",
            )
        else:
            outcome = locate(root, record, registry=registry, search_roots=search_roots)

        entry = {
            "mount_uid": uid,
            "name": record.name,
            "state": record.state,
            "availability_before": record.availability,
            "status": outcome.status,
            "recorded_path": record.path,
            "path": str(outcome.path) if outcome.path else None,
            "found_by": outcome.by,
            "match_score": round(outcome.score, 3),
            "drift": round(1.0 - outcome.score, 3),
            "dirs_searched": outcome.searched,
        }

        if outcome.status in (LOCATED_AMBIGUOUS, LOCATED_LOST, LOCATED_UNSEARCHED):
            report[outcome.status] += 1
            entry["candidates"] = outcome.candidates
            # Never recycled, never dropped. Nothing went away; we simply cannot
            # see it from here, and a record removed is a reference destroyed.
            entry["detail"] = _outcome_detail(record, outcome)
            availability = (
                AVAILABILITY_AMBIGUOUS
                if outcome.status in (LOCATED_AMBIGUOUS, LOCATED_UNSEARCHED)
                else AVAILABILITY_UNAVAILABLE
            )
            entry["availability"] = availability
            if record.state == STATE_ADOPTED:
                if dry_run:
                    entry["affected_files"] = []
                else:
                    raw["availability"] = availability
                    raw["last_checked"] = _now()
                    unavailable = _mark_mount_projections_unavailable(
                        root,
                        record,
                        availability,
                        authoritative_uids=raw.get("projection_uids") or (),
                        projection_metadata=raw.get("projection_metadata") or {},
                        projection_hashes=raw.get("projection_hashes") or {},
                        registry=registry,
                        registry_raw=raw,
                    )
                    entry["affected_files"] = unavailable["affected_files"]
                    entry["projections_checked"] = unavailable["checked"]
                    entry["projections_repaired"] = unavailable["repaired"]
                    entry["projections_tampered"] = unavailable["tampered"]
                    report["affected_files"] += unavailable["affected_files"]
                    report["projections_checked"] += unavailable["checked"]
                    report["projections_repaired"] += unavailable["repaired"]
                    report["projections_tampered"] += unavailable["tampered"]
                    dirty = True
            if not dry_run:
                if raw.get("availability") != availability:
                    raw["availability"] = availability
                    dirty = True
                raw["last_checked"] = _now()
                dirty = True
            report["mounts"].append(entry)
            continue

        report[outcome.status] += 1
        folder = outcome.path
        entry["availability"] = AVAILABILITY_AVAILABLE

        if not dry_run:
            if str(folder) != record.path:
                raw["path"] = str(folder)
                dirty = True
            if record.state == STATE_ADOPTED:
                _preflight_mount_uid_collisions(root, folder, uid)
                # Re-stamp the anchor at the new location only if it is missing;
                # the folder carries it through a move.
                if read_mount_anchor(folder) != uid:
                    write_mount_anchor(folder, uid, record.name, actor)
                sidecar_stats = _reconcile_sidecars(root, folder, uid, actor)
                entry.update(sidecar_stats)
                report["sidecars_created"] += sidecar_stats["sidecars_created"]
                report["sidecars_updated"] += sidecar_stats["sidecars_updated"]

                authority = _mount_authority_snapshot(folder)
                raw["projection_uids"] = sorted(authority)
                raw["projection_metadata"] = authority
                raw["fingerprint"] = fingerprint_folder(folder)
                raw["availability"] = AVAILABILITY_AVAILABLE
                raw["last_checked"] = _now()
                projection_stats = _repair_projections(
                    root,
                    folder,
                    uid,
                    registry=registry,
                    registry_raw=raw,
                )
                entry["projections_checked"] = projection_stats["checked"]
                entry["projections_repaired"] = projection_stats["repaired"]
                entry["projections_missing"] = projection_stats["missing"]
                entry["projections_created"] = projection_stats["created"]
                entry["projections_tampered"] = projection_stats["tampered"]
                entry["orphan_sidecars"] = projection_stats["orphan_sidecars"]
                entry["folder_markers_repaired"] = projection_stats["markers_repaired"]
                report["projections_checked"] += projection_stats["checked"]
                report["projections_repaired"] += projection_stats["repaired"]
                report["projections_missing"] += projection_stats["missing"]
                report["projections_created"] += projection_stats["created"]
                report["projections_tampered"] += projection_stats["tampered"]
                report["orphan_sidecars"] += projection_stats["orphan_sidecars"]
                # The residual travels with the entry AND the summary. A count
                # that cannot be non-zero while `repaired` is zero is not a
                # check, and that is exactly the state G99 was reported clean in.
                entry["projections_unresolved"] = projection_stats["unresolved"]
                report["projections_unresolved"] += projection_stats["unresolved"]
                dirty = True

            refreshed = fingerprint_folder(folder)
            if refreshed.get("census") != (record.fingerprint or {}).get("census"):
                dirty = True
            raw["fingerprint"] = refreshed
            if raw.get("availability") != AVAILABILITY_AVAILABLE:
                raw["availability"] = AVAILABILITY_AVAILABLE
                dirty = True
            raw["last_checked"] = _now()
            dirty = True

        report["mounts"].append(entry)

    if dirty and not dry_run:
        desired_registry = _registry_bytes(registry)
        if (
            not _registry_path(root).is_file()
            or _registry_path(root).read_bytes() != desired_registry
        ):
            _save_registry(root, registry)
    return ReconcileReport(**report)


# --------------------------------------------------------------------------- #
# mounts                                                                        #
# --------------------------------------------------------------------------- #

def _is_within(candidate: str, folder: str) -> bool:
    """Is `candidate` the folder itself or something beneath it?

    Compared as resolved paths rather than as strings, so a trailing slash or a
    symlinked parent cannot make a file look like it belongs to a mount it does
    not — the direction that would recycle somebody else's projection.
    """
    try:
        cand = Path(candidate).resolve()
        base = Path(folder).resolve()
    except (OSError, ValueError):
        return False
    return cand == base or base in cand.parents


def unmount(root, mount_uid: str, *, unmounted_by=None) -> dict:
    """Forget a mount. Leave the folder exactly as it is.

    What a mount owns is a REGISTRY RECORD and some DERIVED PROJECTIONS. Those
    go. What it does not own is the folder: attach promised to write nothing
    into it, and unmount keeps the other half of that promise by taking nothing
    out. The sidecars stay too, and that is the interesting call — Invariant 8
    makes them canonical, so they belong to the folder rather than to us. A
    folder unmounted here and mounted somewhere else arrives already knowing
    what it is, which is the same portability argument ADR-065 made for
    identity.

    Projections are RECYCLED, never removed. They are governed substrate, and
    deletion discipline does not get an exception for substrate we happen to
    have generated ourselves.
    """
    root = Path(root).resolve()
    with _registry_operation_lock(root):
        return _unmount_locked(root, mount_uid, unmounted_by=unmounted_by)


def _unmount_locked(root, mount_uid: str, *, unmounted_by=None) -> dict:
    registry = _load_registry(root)
    raw = (registry.get("mounts") or {}).get(mount_uid)
    if raw is None:
        raise FolderMountError(
            f"no mount {mount_uid}. `list` shows every mount this studio has."
        )

    recycled: list = []
    failed: list = []
    files = root / "vault" / "files"
    authority, suspects = _mount_projection_authority(root, mount_uid, raw)
    authoritative_uids = set(authority)
    indexed_mount_uids = _indexed_mount_uids(root, mount_uid)
    unresolved = suspects | (indexed_mount_uids - authoritative_uids)
    if unresolved:
        raise FolderMountError(
            f"cannot unmount {mount_uid}: ownership is not authoritative for "
            f"projection/index UID(s) {', '.join(sorted(unresolved))}; "
            "the registry and all index surfaces are untouched"
        )
    owned_projections: list[Path] = []
    if files.is_dir():
        for uid in sorted(authoritative_uids):
            projection = files / f"{uid}.md"
            if not projection.is_file():
                continue
            try:
                front = walker.parse_frontmatter(projection)
            except OSError:
                raise FolderMountError(
                    f"cannot unmount {mount_uid}: projection {uid} is unreadable"
                )
            if not _is_verified_mount_projection(
                projection, front, mount_uid, raw
            ):
                raise FolderMountError(
                    f"cannot unmount {mount_uid}: projection {uid} does not "
                    "carry verified derived-only ownership metadata"
                )
            owned_projections.append(projection)

    canonical_ready = all(
        path.is_file()
        for path in (
            root / "vault" / "00-index.jsonl",
            root / "vault" / "00-archive-index.jsonl",
            root / "vault" / "00-index.sqlite",
        )
    )
    if canonical_ready and authoritative_uids:
        index_rows = []
        for surface in ("00-index.jsonl", "00-archive-index.jsonl"):
            index_rows.extend(
                index_writer.index_surfaces.read_jsonl_strict(
                    root / "vault" / surface
                )
            )
        inbound: set[tuple[str, str, str, str]] = set()
        titles = {
            str(row.get("uid")): str(row.get("title") or row.get("uid"))
            for row in index_rows
        }
        for row in index_rows:
            src = str(row.get("uid") or "")
            if not src or src in authoritative_uids:
                continue
            for relation, target in index_writer.iter_record_edges(row):
                if target in authoritative_uids:
                    inbound.add((src, relation, target, titles.get(src, src)))
        sqlite_uri = (
            f"file:{(root / 'vault' / '00-index.sqlite').as_posix()}"
            "?mode=ro&immutable=1"
        )
        with sqlite3.connect(sqlite_uri, uri=True) as conn:
            placeholders = ",".join("?" for _ in authoritative_uids)
            if placeholders:
                for src, relation, target in conn.execute(
                    f"SELECT src_uid, rel, dst_uid FROM edges "
                    f"WHERE dst_uid IN ({placeholders})",
                    tuple(sorted(authoritative_uids)),
                ):
                    if str(src) not in authoritative_uids:
                        inbound.add(
                            (
                                str(src),
                                str(relation),
                                str(target),
                                titles.get(str(src), str(src)),
                            )
                        )
        if inbound:
            rendered = ", ".join(
                f"{title} ({src}) --{relation}--> {target}"
                for src, relation, target, title in sorted(inbound)
            )
            raise FolderMountError(
                f"cannot unmount {mount_uid}: mounted projections have surviving "
                f"inbound graph relations: {rendered}"
            )
        recycle_dir = (
            root / "recycle" / "agent-deletions"
            / datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        recycle_dir_existed = recycle_dir.exists()
        planned_moves: list[tuple[Path, Path]] = []
        reserved: set[Path] = set()
        for projection in owned_projections:
            destination = recycle_dir / projection.name
            if destination.exists() or destination in reserved:
                destination = recycle_dir / (
                    f"{projection.stem}."
                    f"{datetime.now(timezone.utc).strftime('%H%M%S%f')}.md"
                )
            reserved.add(destination)
            planned_moves.append((projection, destination))
        intent_path: Optional[Path] = None
        try:
            if planned_moves:
                intent_path = _write_unmount_move_intent(
                    root,
                    mount_uid,
                    planned_moves,
                    recycle_dir,
                    recycle_dir_existed=recycle_dir_existed,
                )
                recycle_dir.mkdir(parents=True, exist_ok=True)
            for projection, destination in planned_moves:
                os.replace(projection, destination)
                _fsync_directory(projection.parent)
                _fsync_directory(destination.parent)
            del registry["mounts"][mount_uid]
            code = index_writer.remove_many(
                authoritative_uids,
                root,
                companion_replacements=(
                    (_registry_path(root), _registry_bytes(registry)),
                ),
            )
            if code != 0:
                raise FolderMountError(
                    f"canonical index removal refused unmount {mount_uid}"
                )
        except Exception:
            if intent_path is not None:
                _recover_unmount_move_intent(root)
            raise
        recycled = [projection.stem for projection in owned_projections]
        if planned_moves:
            with (recycle_dir / "recycle.log").open("a", encoding="utf-8") as log:
                for source, destination in planned_moves:
                    log.write(
                        f"{_now()}\tuid:{source.stem}\treason:unmounted folder "
                        f"{mount_uid} ({raw.get('name', '?')})"
                        f"\tmoved_from:{source.relative_to(root)}"
                        f"\tmoved_to:{destination.relative_to(root)}\n"
                    )
                log.flush()
                os.fsync(log.fileno())
            _fsync_directory(recycle_dir)
            intent_path.unlink()
            _fsync_directory(intent_path.parent)
    else:
        for projection in owned_projections:
            result = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "tropo-recycle.py"), projection.stem,
                 "--reason", f"unmounted folder {mount_uid} ({raw.get('name', '?')})"],
                capture_output=True, text=True, cwd=str(root),
            )
            (recycled if result.returncode == 0 else failed).append(projection.stem)

    # Refuse to half-forget. A registry entry dropped while its projections
    # still point at it leaves governed entries referencing a mount nobody can
    # look up — worse than either state on its own.
    if failed:
        raise FolderMountError(
            f"cannot unmount {mount_uid}: {len(failed)} projection(s) would not "
            f"recycle ({', '.join(failed[:4])}). The mount is untouched. Recycle "
            f"them by hand or say why they refuse, then run this again."
        )

    if not canonical_ready or not authoritative_uids:
        del registry["mounts"][mount_uid]
        _save_registry(root, registry)
    return {"mount_uid": mount_uid, "name": raw.get("name"), "path": raw.get("path"),
            "recycled": recycled, "folder_untouched": True}


def mounts(root) -> list:
    """Every mount this studio has, oldest uid first. A read, and only a read."""
    registry = _load_registry(Path(root))
    return [_record_from_dict(uid, raw)
            for uid, raw in sorted((registry.get("mounts") or {}).items())]


# --------------------------------------------------------------------------- #
# CLI                                                                           #
# --------------------------------------------------------------------------- #

def _print_mount(record: FolderMount) -> None:
    marker = "●" if record.state == STATE_ADOPTED else "○"
    print(f"{marker} {record.mount_uid}  {record.state:<8}  "
          f"{record.availability:<11}  {record.name}")
    print(f"    {record.path}")
    # Stat the path rather than reprinting it on faith. A recorded location and
    # a location that still exists are different facts, and rendering the first
    # as though it were the second is an instrument reporting confidently over a
    # world that changed underneath it — found by Metis G98 the first time she
    # moved a folder and `list` said nothing. Naming the cure here also turns
    # reconcile from something an operator has to remember into something the
    # tool asks for (finding 1f29bcfb, rule 1c).
    if not Path(record.path).is_dir():
        print(f"    ⚠ that path is not there now — run "
              f"`reconcile {record.mount_uid}` to find where it went")
    print(f"    mounted {record.mounted_at} by {record.mounted_by}"
          + (f"; adopted {record.adopted_at}" if record.adopted_at else ""))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="tropo-folder.py",
        description=(
            "Mount an ordinary directory — a OneDrive or SharePoint sync folder — "
            "with no manifest and no git repo. ATTACHED means agents have hands on "
            "it and nothing was written into it; ADOPTED is the same mount with "
            "sidecars and governed entries. One mount, one uid, a switch between."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_STUDIO_ROOT,
                        help=f"studio root (default: {DEFAULT_STUDIO_ROOT})")
    parser.add_argument("--as", dest="executive", default=None,
                        help="who is doing this; recorded on the mount")
    parser.add_argument("--json", action="store_true", help="machine-readable output")

    # The global flags are also accepted AFTER the subcommand. argparse puts
    # them before by default, and `mount <path> --as metis` then dies on an
    # unrecognised argument — Metis got it wrong twice on a tool she had just
    # been briefed on. A stranger loses a minute to that every time, and the
    # ordering carries no meaning worth defending.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=None)
    common.add_argument("--as", dest="executive_post", default=None,
                        help="who is doing this; recorded on the mount")
    common.add_argument("--json", action="store_true", dest="json_post")

    subs = parser.add_subparsers(dest="command", required=True)

    p_mount = subs.add_parser("mount", parents=[common],
                              help="attach a folder (writes nothing into it)")
    p_mount.add_argument("path", type=Path)
    p_mount.add_argument("--name", required=True, help="what a human calls this folder")

    p_adopt = subs.add_parser("adopt", parents=[common], help="flip the same mount to adopted")
    p_adopt.add_argument("mount_uid")

    p_reconcile = subs.add_parser("reconcile", parents=[common], help="re-find moved folders; repair what moved")
    p_reconcile.add_argument("mount_uid", nargs="?", default=None)
    p_reconcile.add_argument("--search-root", action="append", default=None, dest="search_roots",
                             help="also look here (repeatable)")
    p_reconcile.add_argument("--resolve", default=None, dest="resolve_path",
                             help="name the folder yourself, for an ambiguous or lost mount")
    p_reconcile.add_argument("--dry-run", action="store_true", help="report; change nothing")

    subs.add_parser("list", parents=[common], help="every mount this studio has")

    p_unmount = subs.add_parser("unmount", parents=[common],
                                help="forget a mount; the folder is left exactly as it is")
    p_unmount.add_argument("mount_uid")

    args = parser.parse_args(argv)
    # A flag given after the subcommand wins; otherwise the global one stands.
    if getattr(args, 'executive_post', None):
        args.executive = args.executive_post
    if getattr(args, 'json_post', False):
        args.json = True
    if getattr(args, 'root', None) is None:
        args.root = DEFAULT_STUDIO_ROOT
    root = Path(args.root).resolve()

    try:
        if args.command == "mount":
            record = mount(root, args.path, name=args.name, mounted_by=args.executive)
            if args.json:
                print(json.dumps(asdict(record), indent=2, sort_keys=True))
            else:
                print(f"[ATTACHED] {record.mount_uid}  {record.name}")
                print(f"    {record.path}")
                print("    nothing was written into the folder. Agents can read and "
                      "change it now; run `adopt` when you want it tooled.")
            return 0

        if args.command == "adopt":
            report = adopt(root, args.mount_uid, executive=args.executive)
            if args.json:
                print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
            else:
                print(f"[ADOPTED] {report.mount_uid}  {report.name}")
                print(f"    {report.path}")
                print(f"    {report.sidecars_created} sidecar(s) written, "
                      f"{report.sidecars_existing} already governed, "
                      f"{report.files_ignored} ignored")
                if report.already_adopted:
                    print(f"    already adopted {report.adopted_at}; the uid and the "
                          "adoption date are unchanged")
                for path, reason in report.failures:
                    print(f"    ! {path}: {reason}")
            return 1 if report.failures else 0

        if args.command == "reconcile":
            report = reconcile(root, args.mount_uid,
                               search_roots=args.search_roots,
                               resolve_path=args.resolve_path,
                               executive=args.executive,
                               dry_run=args.dry_run)
            if args.json:
                print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
            else:
                print(f"[RECONCILE] {report.checked} mount(s): {report.unchanged} "
                      f"unchanged, {report.moved} moved, {report.ambiguous} ambiguous, "
                      f"{report.lost} lost"
                      + (f", {report.unsearched} not searched to the end"
                         if report.unsearched else ""))
                for entry in report.mounts:
                    print(f"  {entry['mount_uid']}  {entry['status']}  {entry['name']}")
                    if entry["status"] == "moved":
                        print(f"      was: {entry['recorded_path']}")
                        print(f"      now: {entry['path']}  "
                              f"(found by {entry['found_by']}, match "
                              f"{entry['match_score']})")
                    if entry.get("sidecars_created") or entry.get("sidecars_updated"):
                        print(f"      sidecars: {entry['sidecars_created']} written for "
                              f"new files, {entry['sidecars_updated']} refreshed for "
                              f"changed ones")
                    for bad in entry.get("projections_unresolved") or []:
                        print(f"      ⚠ {bad['uid']}: {bad['field']} points at "
                              f"{bad['points_at']} — nothing is there")
                    for affected in entry.get("affected_files") or []:
                        print(f"      unavailable: {affected['name']} "
                              f"({affected['uid']})")
                    for tampered in entry.get("projections_tampered") or []:
                        print(f"      repaired/tampered: {tampered['uid']} "
                              f"({tampered['path']})")
                    for orphan in entry.get("orphan_sidecars") or []:
                        print(f"      orphan sidecar: {orphan['sidecar_path']} "
                              f"(uid {orphan['uid']}; missing "
                              f"{orphan['missing_source']})")
                    if entry.get("projections_checked"):
                        print(f"      projections: {entry['projections_repaired']} "
                              f"repaired of {entry['projections_checked']} checked")
                    if entry.get("detail"):
                        print(f"      {entry['detail']}")
            # A dangling pointer is a failure even when every move resolved.
            # Reporting success beside a projection that points at nothing is
            # the whole defect, and an exit code is the half a script reads.
            return 1 if (report.ambiguous or report.lost
                         or report.unsearched
                         or report.projections_unresolved
                         or report.orphan_sidecars) else 0

        if args.command == "unmount":
            out = unmount(root, args.mount_uid, unmounted_by=args.executive)
            if args.json:
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                print(f"[UNMOUNTED] {out['mount_uid']}  {out['name']}")
                print(f"    {len(out['recycled'])} projection(s) recycled")
                print(f"    the folder at {out['path']} was not touched — "
                      f"its sidecars stay with it, so re-mounting picks up where this left off")
            return 0

        if args.command == "list":
            records = mounts(root)
            if args.json:
                print(json.dumps([asdict(r) for r in records], indent=2, sort_keys=True))
            elif not records:
                print("No folder mounts. `mount <path> --name X` attaches one; it "
                      "requires nothing of the folder and writes nothing into it.")
            else:
                for record in records:
                    _print_mount(record)
            return 0

    except FolderMountError as exc:
        print(f"[REFUSED] {exc}", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
