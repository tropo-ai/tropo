#!/usr/bin/env python3
"""
---
uid: 7bf6187d
name: gardener-verdict
type: tool
title: "gardener-verdict — canonical Gardener Pruning verdict writer"
description: "Writes evidence-bound pruning verdicts and human keep overrides, then incrementally verifies their derived index projection."
status: active
state: active
owner: talos
domain: "Gardener Pruning governed frontmatter writes"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-gardener-verdict.py {stamp|override} <uid> ..."
script_path: vault/tools/tropo-gardener-verdict.py
input:
  type: object
  required:
    - operation
    - uid
  properties:
    operation:
      type: string
      enum:
        - stamp
        - override
    uid:
      type: string
      pattern: "^[0-9a-f]{8}$"
    verdict:
      type: string
      enum:
        - finished
        - superseded
        - abandoned
    evidence-span:
      type: string
      minLength: 1
    start-byte:
      type: integer
      minimum: 0
    end-byte:
      type: integer
      minimum: 1
    expected-body-sha256:
      type: string
      pattern: "^[0-9a-f]{64}$"
    expected-normalized-body-sha256:
      type: string
      pattern: "^[0-9a-f]{64}$"
    judge-policy-uid:
      type: string
      pattern: "^[0-9a-f]{8}$"
    judge-version:
      type: string
      minLength: 1
    confidence:
      type: number
      minimum: 0.0
      maximum: 1.0
    actor:
      type: string
      minLength: 1
    action:
      type: string
      enum:
        - keep
    by:
      type: string
      pattern: "^[0-9a-f]{8}$"
    reason:
      type: string
      minLength: 1
  allOf:
    - if:
        properties:
          operation:
            const: stamp
      then:
        required:
          - verdict
          - evidence-span
          - start-byte
          - end-byte
          - expected-body-sha256
          - expected-normalized-body-sha256
          - judge-policy-uid
          - judge-version
          - confidence
          - actor
    - if:
        properties:
          operation:
            const: override
      then:
        required:
          - action
          - by
          - reason
  additionalProperties: false
output:
  type: object
  required:
    - uid
    - operation
    - source_changed
    - projection
  properties:
    uid:
      type: string
    operation:
      type: string
    source_changed:
      type: boolean
    projection:
      type: string
      enum:
        - verified
destructive: false
audit_required: false
writes_scope:
  - vault/files/*.md
  - vault/agents/*.md
  - agents/**/*.md
  - vault/capsules/*.md
  - vault/00-index.jsonl
  - vault/00-archive-index.jsonl
  - vault/00-index.sqlite
  - .tropo-studio/locks/gardener-verdict-*.lock
  - .tropo-studio/dirty-counter.json
  - .tropo-studio/locks/index-write.lock
governance_category: update
spawnable_by:
  - all-executives
created: '2026-07-17'
created_by: talos-t33
modified: '2026-07-17'
modified_by: talos-t33
schema_version: 2
extraction_scope: ship
governed_by: d5e1b4a3
member_of:
  - 8dd772a0
---

## Intent

Write or repair the core v1.7 `pruning` frontmatter contract for one governed
Markdown UID. Invoke it for an evidence-bound machine verdict or an interactive
human `keep` override; do not use it as a judge, sweep engine, or validator.

## Invocation Protocol

Run `stamp` with the expected raw and normalized body hashes, byte-exact
evidence, active judge policy identity/version, confidence, and actor. Run
`override` only from an interactive TTY with `--action keep`, a human-principal
UID, and a reason. The target is always resolved by UID; callers never pass a
source path and there is no noninteractive confirmation bypass.

## Input / Output

The frontmatter `input` schema is canonical. Success reports the UID, applied
operation, whether source changed, and `projection=verified`. A no-op exact
retry still repairs and verifies the derived JSONL and SQLite projection.

## Governance

The self-contained pruning contract is `tropo-core.capsule.md`, Pruning Block
Contract v1.7. Live mutation uses a stable per-UID lock, complete-snapshot CAS,
same-directory fsynced atomic replacement, body/hash invariants, and
source-first incremental index convergence. Human override is limited to
interactive `keep` by a current human principal.

## Verification

Success requires re-reading the source to prove body bytes, raw-body hash, and
normalized-body hash are unchanged, then matching the complete nested pruning
mapping in the exact current/archive JSONL row and SQLite `fm_json`.

## Failure Modes

The command refuses ambiguous UID/path/frontmatter identity, unsafe or
non-Markdown paths, stale hashes, invalid or generated-nav evidence, inactive
or mismatched judge policy, malformed/replacement-forbidden blocks, nonhuman or
unconfirmed overrides, CAS races, atomic-write errors, and stale index
projection. Index convergence errors name the single-UID repair command.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import importlib.util
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterator, Optional

import yaml


VAULT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib import index_surfaces, pruning_contract  # noqa: E402
from lib.normalized_body_hash import (  # noqa: E402
    normalized_body_sha256,
    raw_body_sha256,
)


UID_RE = pruning_contract.UID_RE
TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):")
VERDICTS = pruning_contract.VERDICTS
LOCK_TIMEOUT_SECONDS = 60.0
EXACT_RETRY_KEYS = (
    "verdict",
    "evidence_span",
    "evidence_locator",
    "judge_policy_uid",
    "judge_version",
    "confidence",
    "normalized_body_hash_judged",
)


GardenerVerdictError = pruning_contract.PruningContractError
SourceSnapshot = pruning_contract.MarkdownSnapshot


@dataclass(frozen=True)
class StampRequest:
    uid: str
    verdict: str
    evidence_span: str
    start_byte: int
    end_byte: int
    expected_body_sha256: str
    expected_normalized_body_sha256: str
    judge_policy_uid: str
    judge_version: str
    confidence: float
    actor: str


@dataclass(frozen=True)
class WriteResult:
    uid: str
    path: Path
    operation: str
    source_changed: bool
    pruning: dict


FreshenCallback = Callable[[str, Path], int]
AtomicWriteCallback = Callable[[Path, bytes], None]
BeforeCasCallback = Callable[[Path], None]
ConfirmCallback = Callable[[str], bool]
NowCallback = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_datetime(now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise GardenerVerdictError("internal clock returned a timezone-naive datetime")
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


_trimmed_string = pruning_contract.validate_trimmed_string
_validate_hash = pruning_contract.validate_hash
_validate_confidence = pruning_contract.validate_confidence
_validate_pruning_block = pruning_contract.validate_pruning_block


def _resolve_judge_prompt_sha256(vault_root, judge_policy_uid: str):
    """Read the prompt hash the judge policy itself pins; never trust a caller.

    Returns ``None`` when the policy declares no prompt — a model-only judge has
    no prompt to hash, and inventing one would be a lie on the stamp. Absent is
    honest; wrong is not. Fail-closed on a malformed value.
    """
    path = Path(vault_root) / "vault" / "files" / f"{judge_policy_uid}.md"
    if path.is_symlink() or not path.is_file():
        raise pruning_contract.PruningContractError(
            f"judge policy {judge_policy_uid} source is missing or symlinked"
        )
    snapshot = pruning_contract.read_markdown_snapshot(path)
    value = snapshot.frontmatter.get("judge_prompt_sha256")
    if value is None:
        return None
    if not isinstance(value, str) or not pruning_contract.HASH_RE.fullmatch(value):
        raise pruning_contract.PruningContractError(
            f"judge policy {judge_policy_uid} declares a malformed judge_prompt_sha256"
        )
    return value
_read_snapshot = pruning_contract.read_markdown_snapshot


def _surface_rows(vault_root: Path, *, include_archive: bool) -> list[dict]:
    names = [index_surfaces.CURRENT_INDEX_NAME]
    if include_archive:
        names.append(index_surfaces.ARCHIVE_INDEX_NAME)
    rows: list[dict] = []
    for name in names:
        rows.extend(index_surfaces.iter_jsonl(vault_root / "vault" / name))
    return rows


_source_scalar = pruning_contract.source_scalar
_is_declared_pruning_home = pruning_contract.is_declared_pruning_home


def _resolve_target(uid: str, vault_root: Path) -> tuple[Path, dict]:
    if not UID_RE.fullmatch(uid):
        raise GardenerVerdictError(f"UID {uid!r} must be 8 lowercase hex")
    matches = [
        row for row in _surface_rows(vault_root, include_archive=True)
        if row.get("uid") == uid
    ]
    if len(matches) != 1:
        raise GardenerVerdictError(
            f"UID {uid} must resolve to exactly one current/archive index row; "
            f"found {len(matches)}"
        )
    row = matches[0]
    path = pruning_contract.resolve_indexed_pruning_source(
        uid,
        row,
        vault_root,
    )
    return path, row


def _validate_locked_snapshot_identity(
    uid: str,
    path: Path,
    row: dict,
    snapshot: SourceSnapshot,
    vault_root: Path,
) -> None:
    pruning_contract.validate_locked_snapshot_identity(
        uid,
        path,
        row,
        snapshot,
        vault_root,
    )


def _resolve_active_policy(
    policy_uid: str,
    judge_version: str,
    vault_root: Path,
) -> dict:
    return pruning_contract.resolve_active_policy(
        policy_uid,
        judge_version,
        _surface_rows(vault_root, include_archive=False),
    )


def _resolve_human_principal(uid: str, vault_root: Path) -> dict:
    return pruning_contract.resolve_human_principal(
        uid,
        _surface_rows(vault_root, include_archive=False),
    )


def _validate_evidence(
    snapshot: SourceSnapshot,
    evidence_span: object,
    start_byte: object,
    end_byte: object,
) -> None:
    pruning_contract.validate_write_evidence(
        snapshot.body,
        evidence_span,
        start_byte,
        end_byte,
    )


def _top_level_indices(lines: list[str], key: str) -> list[int]:
    return [
        index
        for index, line in enumerate(lines)
        if (match := TOP_LEVEL_KEY_RE.match(line)) and match.group(1) == key
    ]


def _replace_scalar(lines: list[str], key: str, rendered_value: str) -> list[str]:
    indices = _top_level_indices(lines, key)
    if len(indices) > 1:
        raise GardenerVerdictError(f"duplicate top-level {key}: fields are ambiguous")
    replacement = f"{key}: {rendered_value}"
    if indices:
        lines[indices[0]] = replacement
    else:
        lines.append(replacement)
    return lines


def _render_candidate(
    snapshot: SourceSnapshot,
    pruning: dict,
    modified_by: str,
    now: datetime,
) -> bytes:
    lines = snapshot.frontmatter_text.split("\n")
    lines = _replace_scalar(lines, "modified", f"'{now.date().isoformat()}'")
    lines = _replace_scalar(lines, "modified_by", json.dumps(modified_by))

    pruning_indices = _top_level_indices(lines, "pruning")
    if len(pruning_indices) > 1:
        raise GardenerVerdictError("duplicate top-level pruning blocks are ambiguous")
    rendered_block = yaml.safe_dump(
        {"pruning": pruning},
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=200,
    ).rstrip("\n").split("\n")
    if pruning_indices:
        start = pruning_indices[0]
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if TOP_LEVEL_KEY_RE.match(lines[index]):
                end = index
                break
        lines[start:end] = rendered_block
    else:
        lines.extend(rendered_block)

    candidate = (
        b"---\n"
        + "\n".join(lines).encode("utf-8")
        + b"\n---\n"
        + snapshot.body
    )
    reparsed = _read_snapshot_bytes(candidate)
    _validate_pruning_block(reparsed.frontmatter.get("pruning"))
    if reparsed.body != snapshot.body:
        raise GardenerVerdictError("candidate construction changed body bytes")
    return candidate


def _read_snapshot_bytes(raw: bytes) -> SourceSnapshot:
    return pruning_contract.parse_markdown_bytes(raw, "<candidate>")


@contextmanager
def _uid_lock(
    vault_root: Path,
    uid: str,
    *,
    timeout_seconds: float = LOCK_TIMEOUT_SECONDS,
) -> Iterator[None]:
    lock_path = (
        vault_root
        / ".tropo-studio"
        / "locks"
        / f"gardener-verdict-{uid}.lock"
    )
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
                    raise GardenerVerdictError(
                        f"timed out waiting for stable verdict lock {lock_path}"
                    )
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    mode = path.stat().st_mode & 0o7777
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        directory_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@lru_cache(maxsize=1)
def _rebuild_module() -> ModuleType:
    path = TOOLS_DIR / "tropo-rebuild-index.py"
    spec = importlib.util.spec_from_file_location(
        "_tropo_rebuild_for_gardener_verdict",
        path,
    )
    if spec is None or spec.loader is None:
        raise GardenerVerdictError(f"cannot load incremental index writer at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _freshen(uid: str, vault_root: Path) -> int:
    return int(_rebuild_module().freshen_one(uid, vault_root))


def _verify_projection(uid: str, pruning: dict, vault_root: Path) -> None:
    rows = [
        row for row in _surface_rows(vault_root, include_archive=True)
        if row.get("uid") == uid
    ]
    if len(rows) != 1 or rows[0].get("pruning") != pruning:
        raise GardenerVerdictError(
            f"incremental projection verification failed for {uid}: "
            "JSONL pruning block is missing or differs"
        )
    sqlite_path = vault_root / "vault" / "00-index.sqlite"
    if not sqlite_path.is_file():
        raise GardenerVerdictError(
            f"incremental projection verification failed: {sqlite_path} is absent"
        )
    with sqlite3.connect(sqlite_path) as conn:
        row = conn.execute(
            "SELECT fm_json FROM entries WHERE uid=?",
            (uid,),
        ).fetchone()
    if not row:
        raise GardenerVerdictError(
            f"incremental projection verification failed for {uid}: SQLite row absent"
        )
    try:
        sqlite_record = json.loads(row[0])
    except (TypeError, json.JSONDecodeError) as exc:
        raise GardenerVerdictError(
            f"incremental projection verification failed for {uid}: invalid fm_json"
        ) from exc
    if sqlite_record.get("pruning") != pruning:
        raise GardenerVerdictError(
            f"incremental projection verification failed for {uid}: "
            "SQLite pruning block differs"
        )


def _freshen_and_verify(
    uid: str,
    pruning: dict,
    vault_root: Path,
    freshen: FreshenCallback,
) -> None:
    try:
        return_code = freshen(uid, vault_root)
    except Exception as exc:
        raise GardenerVerdictError(
            f"source is canonical but index freshen crashed for {uid}: {exc}; "
            f"repair with `python3 vault/tools/tropo-rebuild-index.py --only {uid}`"
        ) from exc
    if return_code != 0:
        raise GardenerVerdictError(
            f"source is canonical but index freshen failed for {uid} "
            f"(exit {return_code}); repair with "
            f"`python3 vault/tools/tropo-rebuild-index.py --only {uid}`"
        )
    _verify_projection(uid, pruning, vault_root)


def _hashes_for_snapshot(path: Path, snapshot: SourceSnapshot) -> tuple[str, str]:
    before_hash_read = path.read_bytes()
    if before_hash_read != snapshot.raw:
        raise GardenerVerdictError("source changed after snapshot; refusing stale judgment")
    t1 = raw_body_sha256(path)
    t2 = normalized_body_sha256(path)
    if path.read_bytes() != snapshot.raw:
        raise GardenerVerdictError("source changed during hash read; refusing stale judgment")
    return t1, t2


def _exact_retry(existing: dict, proposed: dict) -> bool:
    return all(existing.get(key) == proposed.get(key) for key in EXACT_RETRY_KEYS)


def _select_stamp_disposition(
    existing: object,
    proposed: dict,
    current_t2: str,
) -> tuple[str, dict]:
    if existing is None:
        return "stamp", proposed
    existing_block = _validate_pruning_block(existing)
    if existing_block["judge_policy_uid"] != proposed["judge_policy_uid"]:
        raise GardenerVerdictError(
            "existing pruning block uses a different judge_policy_uid; "
            "governed policy migration is required"
        )
    if _exact_retry(existing_block, proposed):
        return "exact-retry", existing_block

    same_t2 = existing_block["normalized_body_hash_judged"] == current_t2
    same_version = existing_block["judge_version"] == proposed["judge_version"]
    if same_t2 and same_version:
        raise GardenerVerdictError(
            "non-identical payload on the same T2, policy UID, and judge version is refused"
        )
    if same_t2:
        if "override" in existing_block:
            raise GardenerVerdictError(
                "current human keep override blocks same-T2 judge-version replacement"
            )
        return "judge-version-replacement", proposed

    return "new-body-replacement", proposed


def _apply_under_lock(
    *,
    uid: str,
    path: Path,
    snapshot: SourceSnapshot,
    pruning: dict,
    operation: str,
    candidate: Optional[bytes],
    vault_root: Path,
    freshen: FreshenCallback,
    atomic_write: AtomicWriteCallback,
    before_compare_and_swap: Optional[BeforeCasCallback],
) -> WriteResult:
    if before_compare_and_swap is not None:
        before_compare_and_swap(path)
    if path.read_bytes() != snapshot.raw:
        raise GardenerVerdictError(
            "compare-and-swap refused: complete source snapshot changed"
        )

    source_changed = candidate is not None
    before_t1, before_t2 = _hashes_for_snapshot(path, snapshot)
    if candidate is not None:
        try:
            atomic_write(path, candidate)
        except Exception as exc:
            raise GardenerVerdictError(
                f"atomic source write failed for {uid}: {exc}"
            ) from exc
        after_snapshot = _read_snapshot(path)
        after_t1 = raw_body_sha256(path)
        after_t2 = normalized_body_sha256(path)
        if (
            after_snapshot.body != snapshot.body
            or after_t1 != before_t1
            or after_t2 != before_t2
        ):
            raise GardenerVerdictError(
                "post-write invariant failed: body bytes/T1/T2 changed"
            )

    _freshen_and_verify(uid, pruning, vault_root, freshen)
    return WriteResult(uid, path, operation, source_changed, pruning)


def stamp_verdict(
    request: StampRequest,
    *,
    vault_root: Path = VAULT_ROOT,
    freshen: FreshenCallback = _freshen,
    atomic_write: AtomicWriteCallback = _atomic_write_bytes,
    before_compare_and_swap: Optional[BeforeCasCallback] = None,
    now: NowCallback = _utc_now,
) -> WriteResult:
    vault_root = Path(vault_root)
    _trimmed_string(request.actor, "actor")
    if request.verdict not in VERDICTS:
        raise GardenerVerdictError(f"verdict must be one of {sorted(VERDICTS)}")
    _validate_hash(request.expected_body_sha256, "expected_body_sha256")
    _validate_hash(
        request.expected_normalized_body_sha256,
        "expected_normalized_body_sha256",
    )
    _validate_confidence(request.confidence)

    with _uid_lock(vault_root, request.uid):
        path, _row = _resolve_target(request.uid, vault_root)
        _resolve_active_policy(
            request.judge_policy_uid,
            request.judge_version,
            vault_root,
        )
        snapshot = _read_snapshot(path)
        _validate_locked_snapshot_identity(
            request.uid,
            path,
            _row,
            snapshot,
            vault_root,
        )
        t1, t2 = _hashes_for_snapshot(path, snapshot)
        if t1 != request.expected_body_sha256:
            raise GardenerVerdictError(
                f"expected T1 {request.expected_body_sha256} does not match current {t1}"
            )
        if t2 != request.expected_normalized_body_sha256:
            raise GardenerVerdictError(
                f"expected T2 {request.expected_normalized_body_sha256} "
                f"does not match current {t2}"
            )
        _validate_evidence(
            snapshot,
            request.evidence_span,
            request.start_byte,
            request.end_byte,
        )
        timestamp = now()
        proposed = {
            "verdict": request.verdict,
            "evidence_span": request.evidence_span,
            "evidence_locator": {
                "body_sha256": t1,
                "start_byte": request.start_byte,
                "end_byte": request.end_byte,
            },
            "judge_policy_uid": request.judge_policy_uid,
            "judge_version": request.judge_version,
            # Both derived, never caller-supplied: origin_studio is a provenance
            # claim, and the prompt sha must match the policy actually in force.
            # A caller able to hand in either could mint a stamp that lies about
            # who judged it — which is precisely what a federation boundary reads.
            "judge_prompt_sha256": _resolve_judge_prompt_sha256(
                vault_root, request.judge_policy_uid
            ),
            "origin_studio": pruning_contract.resolve_origin_studio(vault_root),
            "judged_at": _iso_datetime(timestamp),
            "confidence": float(request.confidence),
            "normalized_body_hash_judged": t2,
        }
        _validate_pruning_block(proposed)
        operation, effective = _select_stamp_disposition(
            snapshot.frontmatter.get("pruning"),
            proposed,
            t2,
        )
        candidate = None
        if operation != "exact-retry":
            candidate = _render_candidate(snapshot, effective, request.actor, timestamp)
        return _apply_under_lock(
            uid=request.uid,
            path=path,
            snapshot=snapshot,
            pruning=effective,
            operation=operation,
            candidate=candidate,
            vault_root=vault_root,
            freshen=freshen,
            atomic_write=atomic_write,
            before_compare_and_swap=before_compare_and_swap,
        )


def _confirm_human(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        answer = input(f"{prompt}\nType YES to write keep override [default NO]: ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip() == "YES"


def add_keep_override(
    uid: str,
    *,
    by: str,
    reason: str,
    vault_root: Path = VAULT_ROOT,
    confirm: ConfirmCallback = _confirm_human,
    freshen: FreshenCallback = _freshen,
    atomic_write: AtomicWriteCallback = _atomic_write_bytes,
    before_compare_and_swap: Optional[BeforeCasCallback] = None,
    now: NowCallback = _utc_now,
) -> WriteResult:
    vault_root = Path(vault_root)
    _trimmed_string(reason, "override reason")
    prelock_path, prelock_row = _resolve_target(uid, vault_root)

    with _uid_lock(vault_root, uid):
        path, _row = _resolve_target(uid, vault_root)
        if (
            path != prelock_path
            or _row.get("path") != prelock_row.get("path")
        ):
            raise GardenerVerdictError(
                "override target changed between pre-resolution and locked resolution"
            )
        _resolve_human_principal(by, vault_root)
        snapshot = _read_snapshot(path)
        _validate_locked_snapshot_identity(uid, path, _row, snapshot, vault_root)
        existing = _validate_pruning_block(snapshot.frontmatter.get("pruning"))
        if "override" in existing:
            raise GardenerVerdictError("pruning block already carries a human override")
        _resolve_active_policy(
            existing["judge_policy_uid"],
            existing["judge_version"],
            vault_root,
        )
        _t1, current_t2 = _hashes_for_snapshot(path, snapshot)
        if existing["normalized_body_hash_judged"] != current_t2:
            raise GardenerVerdictError(
                "cannot override a stale body version; current T2 differs from the verdict"
            )
        prompt = (
            f"Override pruning verdict with action keep?\n"
            f"UID: {uid}\n"
            f"Current T2: {current_t2}\n"
            f"Verdict: {existing['verdict']}"
        )
        if not confirm(prompt):
            raise GardenerVerdictError(
                "human keep override refused: interactive confirmation defaulted to NO"
            )
        timestamp = now()
        updated = copy.deepcopy(existing)
        updated["override"] = {
            "action": "keep",
            "by": by,
            "at": _iso_datetime(timestamp),
            "reason": reason,
        }
        _validate_pruning_block(updated)
        candidate = _render_candidate(snapshot, updated, by, timestamp)
        return _apply_under_lock(
            uid=uid,
            path=path,
            snapshot=snapshot,
            pruning=updated,
            operation="human-keep-override",
            candidate=candidate,
            vault_root=vault_root,
            freshen=freshen,
            atomic_write=atomic_write,
            before_compare_and_swap=before_compare_and_swap,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Canonical Gardener Pruning verdict/override writer"
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    stamp = subparsers.add_parser("stamp", help="stamp a machine-proposed pruning verdict")
    stamp.add_argument("uid")
    stamp.add_argument("--verdict", required=True, choices=sorted(VERDICTS))
    stamp.add_argument("--evidence-span", required=True)
    stamp.add_argument("--start-byte", required=True, type=int)
    stamp.add_argument("--end-byte", required=True, type=int)
    stamp.add_argument("--expected-body-sha256", required=True)
    stamp.add_argument("--expected-normalized-body-sha256", required=True)
    stamp.add_argument("--judge-policy-uid", required=True)
    stamp.add_argument("--judge-version", required=True)
    stamp.add_argument("--confidence", required=True, type=float)
    stamp.add_argument("--actor", required=True)

    override = subparsers.add_parser(
        "override",
        help="interactively add the sole human override action: keep",
    )
    override.add_argument("uid")
    override.add_argument("--action", required=True, choices=("keep",))
    override.add_argument("--by", required=True, help="human principal UID")
    override.add_argument("--reason", required=True)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "stamp":
            result = stamp_verdict(
                StampRequest(
                    uid=args.uid,
                    verdict=args.verdict,
                    evidence_span=args.evidence_span,
                    start_byte=args.start_byte,
                    end_byte=args.end_byte,
                    expected_body_sha256=args.expected_body_sha256,
                    expected_normalized_body_sha256=args.expected_normalized_body_sha256,
                    judge_policy_uid=args.judge_policy_uid,
                    judge_version=args.judge_version,
                    confidence=args.confidence,
                    actor=args.actor,
                )
            )
        else:
            result = add_keep_override(
                args.uid,
                by=args.by,
                reason=args.reason,
            )
    except GardenerVerdictError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        f"[DONE] {result.uid} {result.operation}; "
        f"source_changed={str(result.source_changed).lower()}; "
        "projection=verified"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
