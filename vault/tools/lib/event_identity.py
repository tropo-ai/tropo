"""Distributed Event Ledger identity + per-writer stream primitives.

Legacy numeric events remain immutable epoch-1 input.  New events (when the
cutover feature flag is enabled) use globally unique writer-instance identity,
writer-local sequence, and one canonical JSONL stream per writer.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator


LEGACY_EVENTS_REL = Path("vault") / "events" / "00-events.jsonl"
STREAMS_REL = Path("vault") / "events" / "streams"
SQLITE_PROJECTION_REL = Path("vault") / "events" / "00-events-index.sqlite"
AUTOHEAL_COOLDOWN_REL = Path("vault") / "events" / ".sqlite-autorebuild-cooldown.json"
REBUILD_SCRIPT_REL = Path("vault") / "tools" / "tropo-rebuild-events-sqlite.py"
AUTOHEAL_COOLDOWN_SECONDS = 300
AUTOHEAL_TIMEOUT_SECONDS = 120
# Set in the rebuild subprocess's environment so a nested import can never
# re-enter the heal and fork a rebuild storm.
AUTOHEAL_ACTIVE_ENV = "TROPO_SQLITE_AUTOHEAL_ACTIVE"
# Operator escape hatch for a read with provably zero side effects.
AUTOHEAL_DISABLE_ENV = "TROPO_NO_SQLITE_AUTOHEAL"
WRITER_INSTANCE_REL = Path(".tropo-studio") / "event-writer-instance.json"
CUTOVER_MARKER_REL = Path(".tropo") / "event-streams-v2.enabled"
CUTOVER_SCHEMA_ID = "tropo.event-streams-v2-cutover/v1"
CUTOVER_MAIN_REFS = (
    "refs/remotes/origin/main",
    "refs/heads/main",
)
HEX8_RE = re.compile(r"^[0-9a-f]{8}$")
LOCAL_INSTANCE_RE = re.compile(r"^[0-9a-f]{16}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

CUTOVER_MARKER_KEYS = frozenset(
    {
        "schema_id",
        "enabled",
        "enabled_at",
        "enabled_by",
        "dev_spec_uid",
        "dev_spec_sha256",
        "test_spec_uid",
        "test_spec_sha256",
        "audit_uid",
        "audit_sha256",
        "legacy_epoch_path",
        "legacy_epoch_sha256",
        "legacy_physical_rows",
        "legacy_unique_events",
        "baseline_main_commit",
    }
)


def terminal_reply_has_renderable_content(
    vault_root: Path,
    data: object,
) -> bool:
    """Return whether a terminal reply has renderable inline or companion content."""
    payload = data if isinstance(data, dict) else {}
    body = payload.get("body")
    if isinstance(body, str) and bool(body.strip()):
        return True

    body_file = payload.get("body_file")
    if not isinstance(body_file, str) or not body_file.strip():
        return False

    companion_root = (vault_root / "vault" / "events" / "files").resolve()
    try:
        candidate = (vault_root / body_file).resolve(strict=True)
        candidate.relative_to(companion_root)
        return candidate.is_file() and candidate.stat().st_size > 0
    except (OSError, ValueError):
        return False


def _json_no_duplicates(raw: str, *, source: str) -> dict:
    def no_duplicates(pairs):
        value = {}
        for key, child in pairs:
            if key in value:
                raise RuntimeError(f"duplicate marker key {key!r} ({source})")
            value[key] = child
        return value

    try:
        value = json.loads(raw, object_pairs_hook=no_duplicates)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"invalid cutover marker JSON ({source}): {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"cutover marker root must be an object ({source})")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_bound_file_sha256(vault_root: Path, path: Path) -> str:
    """Hash canonical committed bytes when the Studio is a Git checkout.

    Governed Markdown can be hydrated in the working tree by a clean/smudge
    filter while the cutover marker intentionally binds the stripped Git blob.
    Comparing raw working bytes therefore produces a false mismatch.  Git's
    ``hash-object --path`` applies the configured clean filter; matching that
    blob to ``HEAD:<path>`` proves the working source is canonically unchanged.
    Scratch fixtures without Git keep the strict raw-file behavior.
    """
    try:
        relative = path.resolve().relative_to(vault_root.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"cutover evidence escapes the Studio root: {path}") from exc

    git_env = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    git_env["GIT_OPTIONAL_LOCKS"] = "0"
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=vault_root,
        capture_output=True,
        text=True,
        env=git_env,
        timeout=10,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return file_sha256(path)

    head_blob = subprocess.run(
        ["git", "rev-parse", f"HEAD:{relative}"],
        cwd=vault_root,
        capture_output=True,
        text=True,
        env=git_env,
        timeout=10,
    )
    working_blob = subprocess.run(
        ["git", "hash-object", f"--path={relative}", str(path)],
        cwd=vault_root,
        capture_output=True,
        text=True,
        env=git_env,
        timeout=10,
    )
    if head_blob.returncode != 0 or working_blob.returncode != 0:
        raise RuntimeError(f"cutover evidence is not committed at HEAD: {relative}")
    if head_blob.stdout.strip() != working_blob.stdout.strip():
        raise RuntimeError(f"cutover evidence has canonical working-tree drift: {relative}")

    committed = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=vault_root,
        capture_output=True,
        env=git_env,
        timeout=10,
    )
    if committed.returncode != 0:
        raise RuntimeError(f"cutover evidence blob cannot be read: {relative}")
    return hashlib.sha256(committed.stdout).hexdigest()


def _main_ref_contains_cutover_marker(vault_root: Path) -> bool:
    """Detect a cutover that this stale worktree has not merged yet.

    Legacy mode remains valid for standalone/pre-cutover Studios. In a Git
    checkout, however, a marker on local or fetched main means the shared
    repository has already cut over. A stale branch must merge that marker
    before emitting; otherwise its valid local legacy append can later corrupt
    the hash-frozen epoch when merged into main.
    """

    marker_path = CUTOVER_MARKER_REL.as_posix()
    for ref in CUTOVER_MAIN_REFS:
        try:
            result = subprocess.run(
                ["git", "-C", str(vault_root), "cat-file", "-e", f"{ref}:{marker_path}"],
                check=False,
                capture_output=True,
                timeout=2,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            return False
        if result.returncode == 0:
            return True
    return False


def load_cutover_marker(vault_root: Path) -> dict | None:
    """Load and verify the production cutover marker.

    Absence means legacy mode. Presence is an authenticated local contract:
    malformed, stale, symlinked, or hash-mismatched markers raise and therefore
    block emission instead of falling back to the legacy writer.
    """

    path = vault_root / CUTOVER_MARKER_REL
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        streams_dir = vault_root / STREAMS_REL
        if streams_dir.exists():
            if streams_dir.is_symlink() or not streams_dir.is_dir():
                raise RuntimeError(
                    "stream history path exists but is not a regular directory; "
                    "legacy fallback is forbidden"
                )
            for stream in streams_dir.glob("*.jsonl"):
                if stream.is_symlink() or not stream.is_file():
                    raise RuntimeError(
                        f"stream history contains a nonregular entry: {stream}"
                    )
                if stream.read_bytes().strip():
                    raise RuntimeError(
                        "stream history exists but the cutover marker is absent; "
                        "cutover is forward-only and legacy fallback is forbidden"
                    )
        if _main_ref_contains_cutover_marker(vault_root):
            raise RuntimeError(
                "cutover marker exists on main but is absent from this worktree; "
                "merge current main before emitting; legacy fallback is forbidden"
            )
        return None
    if not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
        raise RuntimeError(f"cutover marker must be a regular non-symlink file: {path}")

    marker = _json_no_duplicates(path.read_text(encoding="utf-8"), source=str(path))
    keys = frozenset(marker)
    if keys != CUTOVER_MARKER_KEYS:
        raise RuntimeError(
            "cutover marker keys mismatch: "
            f"missing={sorted(CUTOVER_MARKER_KEYS - keys)} "
            f"unknown={sorted(keys - CUTOVER_MARKER_KEYS)}"
        )
    if marker["schema_id"] != CUTOVER_SCHEMA_ID or marker["enabled"] is not True:
        raise RuntimeError("cutover marker schema/enabled fields are invalid")
    if not isinstance(marker["enabled_by"], str) or not marker["enabled_by"].strip():
        raise RuntimeError("cutover marker enabled_by must be non-empty")
    if not ISO_UTC_RE.fullmatch(str(marker["enabled_at"])):
        raise RuntimeError("cutover marker enabled_at must be UTC second precision")
    if not COMMIT_RE.fullmatch(str(marker["baseline_main_commit"])):
        raise RuntimeError("cutover marker baseline_main_commit must be 40-hex")

    evidence = (
        ("dev_spec_uid", "dev_spec_sha256", "f15a9b85"),
        ("test_spec_uid", "test_spec_sha256", "5a195c76"),
        ("audit_uid", "audit_sha256", "de9ac53c"),
    )
    for uid_key, hash_key, required_uid in evidence:
        uid = str(marker[uid_key])
        expected_hash = str(marker[hash_key])
        if uid != required_uid or not SHA256_RE.fullmatch(expected_hash):
            raise RuntimeError(f"cutover marker {uid_key}/{hash_key} is invalid")
        evidence_path = vault_root / "vault" / "files" / f"{uid}.md"
        if not evidence_path.is_file() or evidence_path.is_symlink():
            raise RuntimeError(f"cutover evidence is missing/nonregular: {evidence_path}")
        if git_bound_file_sha256(vault_root, evidence_path) != expected_hash:
            raise RuntimeError(f"cutover evidence hash mismatch: {evidence_path}")

    if marker["legacy_epoch_path"] != LEGACY_EVENTS_REL.as_posix():
        raise RuntimeError("cutover marker legacy_epoch_path is invalid")
    legacy_path = vault_root / LEGACY_EVENTS_REL
    expected_legacy_hash = str(marker["legacy_epoch_sha256"])
    if not SHA256_RE.fullmatch(expected_legacy_hash):
        raise RuntimeError("cutover marker legacy_epoch_sha256 is invalid")
    if not legacy_path.is_file() or legacy_path.is_symlink():
        raise RuntimeError(f"legacy epoch is missing/nonregular: {legacy_path}")
    if file_sha256(legacy_path) != expected_legacy_hash:
        raise RuntimeError("legacy epoch hash no longer matches the cutover marker")
    physical_rows = len(legacy_path.read_text(encoding="utf-8").splitlines())
    if (
        isinstance(marker["legacy_physical_rows"], bool)
        or not isinstance(marker["legacy_physical_rows"], int)
        or marker["legacy_physical_rows"] != physical_rows
    ):
        raise RuntimeError("legacy physical row count no longer matches the cutover marker")
    if (
        isinstance(marker["legacy_unique_events"], bool)
        or not isinstance(marker["legacy_unique_events"], int)
        or marker["legacy_unique_events"] < 1
        or marker["legacy_unique_events"] > marker["legacy_physical_rows"]
    ):
        raise RuntimeError("cutover marker legacy_unique_events is invalid")
    return marker


def streams_enabled(vault_root: Path) -> bool:
    return load_cutover_marker(vault_root) is not None


def _write_json_exclusive(path: Path, data: dict) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return True


def load_or_create_clone_instance_uid(vault_root: Path) -> str:
    """Return a machine-local clone nonce; never committed or synced."""
    path = vault_root / WRITER_INSTANCE_REL
    for _ in range(4):
        if path.is_file():
            try:
                value = str(json.loads(path.read_text()).get("writer_instance_seed", ""))
                if LOCAL_INSTANCE_RE.fullmatch(value):
                    return value
            except Exception:
                pass
        candidate = secrets.token_hex(8)
        if _write_json_exclusive(path, {"writer_instance_seed": candidate}):
            return candidate
    raise RuntimeError(f"could not establish clone-local writer identity at {path}")


def current_activation_for_source(vault_root: Path, source_uid: str) -> str:
    """Resolve party UID to current activation; tools/runs may return empty."""
    agents_dir = vault_root / "vault" / "agents"
    if not agents_dir.is_dir():
        return ""
    for path in agents_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        party = re.search(r"^party_uid:\s*([0-9a-f]{8})", text, re.MULTILINE)
        if not party or party.group(1) != source_uid:
            continue
        activation = re.search(
            r"^current_activation_uid:\s*['\"]?([0-9a-f]{8})",
            text,
            re.MULTILINE,
        )
        return activation.group(1) if activation else ""
    return ""


def derive_writer_instance_uid(
    vault_root: Path,
    source_uid: str,
    *,
    activation_uid: str = "",
) -> str:
    clone_uid = load_or_create_clone_instance_uid(vault_root)
    activation_uid = activation_uid or current_activation_for_source(vault_root, source_uid)
    material = f"{clone_uid}:{source_uid}:{activation_uid or 'no-activation'}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def stream_path(vault_root: Path, writer_instance_uid: str) -> Path:
    if not LOCAL_INSTANCE_RE.fullmatch(writer_instance_uid):
        raise ValueError(f"writer_instance_uid must be 16-hex; got {writer_instance_uid!r}")
    return vault_root / STREAMS_REL / f"{writer_instance_uid}.jsonl"


def _max_local_seq(lines: list[str]) -> int:
    maximum = 0
    for line in lines:
        try:
            event = json.loads(line)
            maximum = max(maximum, int(event.get("local_seq", 0)))
        except Exception:
            continue
    return maximum


def append_stream_event(
    vault_root: Path,
    writer_instance_uid: str,
    event: dict,
) -> dict:
    """Assign local sequence + immutable UID and append under stream flock."""
    path = stream_path(vault_root, writer_instance_uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            lines = handle.readlines()
            local_seq = _max_local_seq(lines) + 1
            event_uid = f"evt_{writer_instance_uid}_{local_seq:08d}"
            event["id"] = event_uid
            event["event_uid"] = event_uid
            event["writer_instance_uid"] = writer_instance_uid
            event["stream_uid"] = writer_instance_uid
            event["local_seq"] = local_seq
            raw = json.dumps(event, ensure_ascii=False)
            handle.seek(0, os.SEEK_END)
            handle.write(raw + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return event


def legacy_event_uid(event: dict) -> str:
    return f"legacy_{str(event.get('id', '')).zfill(8)}"


def immutable_event_uid(event: dict) -> str:
    return str(event.get("event_uid") or legacy_event_uid(event))


def sqlite_projection_complete(
    sqlite_path: Path,
    canonical_events: list[dict],
) -> bool:
    """Return whether SQLite exactly covers the canonical immutable identities.

    The projection is derived and carries no trusted completeness marker.  A
    reader may use it only when every projected row has one unique immutable
    identity and that identity set exactly equals the legacy-plus-stream union.
    Missing, unreadable, partially initialized, and divergent databases all
    fail closed so callers can fall back to canonical JSONL.
    """
    canonical_uids = {
        immutable_event_uid(event)
        for event in canonical_events
    }
    try:
        conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False

    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        if "event_uid" in columns:
            rows = [row[0] for row in conn.execute("SELECT event_uid FROM events")]
            if any(value is None for value in rows):
                return False
            projected_uids = [str(value) for value in rows]
        elif "id" in columns:
            rows = [row[0] for row in conn.execute("SELECT id FROM events")]
            if any(value is None for value in rows):
                return False
            projected_uids = [
                legacy_event_uid({"id": value})
                for value in rows
            ]
        else:
            return False
    except sqlite3.Error:
        return False
    finally:
        conn.close()

    projected_set = set(projected_uids)
    return (
        len(projected_uids) == len(projected_set)
        and projected_set == canonical_uids
    )


def autoheal_disabled() -> bool:
    """Whether projection self-heal is suppressed for this process.

    Two suppression sources: the operator escape hatch, and the guard the heal
    itself sets in the rebuild subprocess so a nested import cannot re-enter.
    """
    return bool(
        os.environ.get(AUTOHEAL_DISABLE_ENV)
        or os.environ.get(AUTOHEAL_ACTIVE_ENV)
    )


def _autoheal_cooldown_active(
    cooldown_path: Path,
    now: datetime,
    log: Callable[[str], None],
) -> bool:
    if not cooldown_path.is_file():
        return False
    try:
        last = datetime.fromisoformat(
            json.loads(cooldown_path.read_text())["last_attempt"]
        )
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return False  # an unreadable marker never blocks a repair attempt
    elapsed = (now - last).total_seconds()
    if elapsed >= AUTOHEAL_COOLDOWN_SECONDS:
        return False
    log(
        f"INFO: SQLite auto-rebuild skipped (cooldown active, last attempt "
        f"{elapsed:.0f}s ago; {AUTOHEAL_COOLDOWN_SECONDS}s window)"
    )
    return True


def heal_sqlite_projection(
    vault_root: Path,
    *,
    log: Callable[[str], None] | None = None,
) -> bool:
    """Repair the derived SQLite projection via the sanctioned full rebuild.

    Only ever invokes ``tropo-rebuild-events-sqlite.py`` — never an incremental
    patch, matching the fail-closed posture of ``sqlite_projection_complete``.
    Rate-limited by a cooldown marker shared by every caller, so a persistent
    divergence cause cannot trigger a rebuild storm across concurrent agents.

    Returns True only when a rebuild was attempted AND exited 0.
    """
    emit = log or (lambda message: print(message, file=sys.stderr))
    if autoheal_disabled():
        return False

    cooldown_path = vault_root / AUTOHEAL_COOLDOWN_REL
    now = datetime.now(timezone.utc)
    if _autoheal_cooldown_active(cooldown_path, now, emit):
        return False

    try:
        cooldown_path.parent.mkdir(parents=True, exist_ok=True)
        cooldown_path.write_text(
            json.dumps({"last_attempt": now.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")})
        )
    except OSError as exc:
        emit(f"WARN: SQLite auto-rebuild could not record its cooldown marker: {exc}")

    env = dict(os.environ)
    env[AUTOHEAL_ACTIVE_ENV] = "1"
    try:
        result = subprocess.run(
            [sys.executable, str(vault_root / REBUILD_SCRIPT_REL)],
            capture_output=True,
            text=True,
            timeout=AUTOHEAL_TIMEOUT_SECONDS,
            env=env,
        )
    except Exception as exc:
        emit(f"WARN: SQLite auto-rebuild failed to launch: {exc}")
        return False

    if result.returncode == 0:
        emit(f"INFO: SQLite auto-rebuild succeeded ({result.stdout.strip()})")
        return True
    emit(
        f"WARN: SQLite auto-rebuild exited {result.returncode}: "
        f"{result.stderr.strip()}"
    )
    return False


def ensure_sqlite_projection(
    vault_root: Path,
    canonical_events: list[dict],
    *,
    sqlite_path: Path | None = None,
    context: str = "",
    log: Callable[[str], None] | None = None,
) -> bool:
    """Detect projection divergence, repair it once, and report the outcome.

    This is the single entry point every caller — read path and write path
    alike — should use instead of pairing a bare ``sqlite_projection_complete``
    check with its own private repair. Healing is triggered by DETECTION, not
    by any one command, so a divergence introduced by ``git merge``, a fresh
    clone, or a manual file copy repairs itself at the next touch of the log.

    Returns the projection's completeness AFTER any repair. Callers must keep
    treating the canonical JSONL union as delivery truth: a healed projection
    is a faster cache, never a new source of authority.
    """
    emit = log or (lambda message: print(message, file=sys.stderr))
    path = sqlite_path if sqlite_path is not None else vault_root / SQLITE_PROJECTION_REL
    if not path.exists():
        return False
    if sqlite_projection_complete(path, canonical_events):
        return True

    where = f" ({context})" if context else ""
    if autoheal_disabled():
        emit(
            f"WARN: SQLite event projection is incomplete, divergent, or "
            f"unreadable{where}; self-heal suppressed by environment, falling "
            f"back to the canonical JSONL union"
        )
        return False

    emit(
        f"WARN: SQLite event projection is incomplete, divergent, or "
        f"unreadable{where}; attempting one rate-limited auto-rebuild "
        f"(tropo-rebuild-events-sqlite.py). The canonical JSONL union remains "
        f"delivery truth either way."
    )
    if not heal_sqlite_projection(vault_root, log=emit):
        return False
    return sqlite_projection_complete(
        path,
        load_event_union(vault_root),
    )


def strict_event_json(raw: str, *, source_path: str) -> dict:
    """Parse one raw event line while refusing duplicate keys at any depth."""
    def no_duplicates(pairs):
        value = {}
        for key, child in pairs:
            if key in value:
                raise ValueError(
                    f"event JSON contains duplicate key {key!r} ({source_path})"
                )
            value[key] = child
        return value

    event = json.loads(raw, object_pairs_hook=no_duplicates)
    if not isinstance(event, dict):
        raise ValueError(f"event JSON root is not an object ({source_path})")
    return event


def iter_raw_event_lines(vault_root: Path) -> Iterator[tuple[str, str]]:
    """Yield (source-relative-path, raw-line) across legacy + writer streams."""
    legacy = vault_root / LEGACY_EVENTS_REL
    if legacy.is_file():
        for line in legacy.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                yield LEGACY_EVENTS_REL.as_posix(), line
    streams_dir = vault_root / STREAMS_REL
    if streams_dir.is_dir():
        for path in sorted(streams_dir.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    yield path.relative_to(vault_root).as_posix(), line


def load_event_union_records(vault_root: Path) -> list[dict]:
    """Load lossless records, refusing identity/content conflicts.

    ``raw`` preserves the exact canonical line bytes (minus newline) for
    forensic SQLite projection. ``canonical`` is used only to decide whether
    a repeated event_uid is semantically identical or conflicting.
    """
    by_uid: dict[str, dict] = {}
    for source_path, raw in iter_raw_event_lines(vault_root):
        event = strict_event_json(raw, source_path=source_path)
        event_uid = immutable_event_uid(event)
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
        existing = by_uid.get(event_uid)
        if existing:
            if existing["canonical"] != canonical:
                raise ValueError(
                    f"event identity conflict {event_uid}: same identity, different content "
                    f"({source_path})"
                )
            data = event.get("data")
            if isinstance(data, dict) and "receipt_sha256" in data:
                raise ValueError(
                    f"duplicate release receipt pointer event {event_uid} "
                    f"({source_path})"
                )
            continue
        by_uid[event_uid] = {
            "event_uid": event_uid,
            "event": event,
            "raw": raw,
            "source_path": source_path,
            "canonical": canonical,
        }
    return list(by_uid.values())


def load_event_union(vault_root: Path) -> list[dict]:
    """Load legacy + streams as event objects for query/validation consumers."""
    return [record["event"] for record in load_event_union_records(vault_root)]


def derive_display_order(events: list[dict]) -> list[tuple[int, dict]]:
    """Deterministic display projection; never mutates event identity/content."""
    ordered = sorted(
        events,
        key=lambda event: (
            str(event.get("time", "")),
            immutable_event_uid(event),
        ),
    )
    return list(enumerate(ordered, 1))


def derive_display_record_order(records: list[dict]) -> list[tuple[int, dict]]:
    ordered = sorted(
        records,
        key=lambda record: (
            str(record["event"].get("time", "")),
            record["event_uid"],
        ),
    )
    return list(enumerate(ordered, 1))
