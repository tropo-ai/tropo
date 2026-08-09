#!/usr/bin/env python3
"""
---
uid: 76ebc743
name: gardener-body-judge
type: tool
title: "gardener-body-judge — dry-run queue and metered synthetic canary"
description: "Builds the read-only production queue or runs the pinned, proposal-only synthetic Opus canary."
status: active
state: active
owner: talos
domain: "Gardener Pruning queue planning and synthetic body-judgment canary"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-gardener-body-judge.py {--dry-run|--synthetic-canary --run-dir PATH}"
script_path: vault/tools/tropo-gardener-body-judge.py
input:
  oneOf:
    - type: object
      required: [dry-run]
      properties:
        dry-run: {type: boolean, const: true}
        vault-path: {type: string}
      additionalProperties: false
    - type: object
      required: [synthetic-canary, run-dir]
      properties:
        synthetic-canary: {type: boolean, const: true}
        run-dir: {type: string}
      additionalProperties: false
output:
  oneOf:
    - type: object
      required:
        - policy_uid
        - policy_version
        - scanned_count
        - queue_count
        - current_count
        - blocked_count
        - blocked_counts
        - per_segment_counts
        - candidates
        - blocked
      properties:
        policy_uid:
          type: string
          pattern: '^[0-9a-f]{8}$'
        policy_version:
          type: string
          pattern: '^[0-9]+[.][0-9]+(?:[.][0-9]+)?$'
        scanned_count:
          type: integer
          minimum: 0
        queue_count:
          type: integer
          minimum: 0
        current_count:
          type: integer
          minimum: 0
        blocked_count:
          type: integer
          minimum: 0
        blocked_counts:
          type: object
          required:
            - by_reason
            - by_segment
          properties:
            by_reason:
              type: object
              additionalProperties:
                type: integer
                minimum: 0
            by_segment:
              type: object
              additionalProperties:
                type: integer
                minimum: 0
          additionalProperties: false
        per_segment_counts:
          type: object
          additionalProperties:
            type: object
            required:
              - scanned_count
              - queue_count
              - current_count
              - blocked_count
            properties:
              scanned_count:
                type: integer
                minimum: 0
              queue_count:
                type: integer
                minimum: 0
              current_count:
                type: integer
                minimum: 0
              blocked_count:
                type: integer
                minimum: 0
            additionalProperties: false
        candidates:
          type: array
          items:
            type: object
            required:
              - uid
              - path
              - t2
              - reason
            properties:
              uid:
                type: string
                pattern: '^[0-9a-f]{8}$'
              path:
                type: string
              t2:
                type: string
                pattern: '^[0-9a-f]{64}$'
              reason:
                type: string
                enum:
                  - missing-pruning
                  - t2-stale
                  - policy-stale
                  - invalid-pruning
            additionalProperties: false
        blocked:
          type: array
          items:
            type: object
            required:
              - uid
              - path
              - segment
              - reason
            properties:
              uid:
                type: string
              path:
                type: string
              segment:
                type: string
              reason:
                type: string
                enum:
                  - source-missing
                  - source-symlink
                  - source-frontmatter-invalid
                  - source-uid-mismatch
                  - source-path-invalid
                  - source-segment-invalid
                  - source-evaluation-failed
            additionalProperties: false
      additionalProperties: false
    - type: object
      required: [mode, status, phase, policy, fixture, run, calls_attempted, completed_count, cases, score, error, proposed_only, writer_invoked]
      properties:
        mode: {type: string, const: synthetic-canary}
        status: {type: string, enum: [pass, failed]}
        phase: {type: string, enum: [preflight, model, score]}
        policy: {type: object}
        fixture: {type: object}
        run: {type: object}
        calls_attempted: {type: integer, minimum: 0}
        completed_count: {type: integer, minimum: 0}
        cases: {type: array}
        score: {type: [object, 'null']}
        error: {type: [string, 'null']}
        proposed_only: {type: boolean, const: true}
        writer_invoked: {type: boolean, const: false}
      additionalProperties: false
destructive: false
audit_required: true
writes_scope:
  - vault/loop-runs/*/gardener-synthetic-canary-scorecard.json
  - vault/loop-runs/*/gateway_spend.json
governance_category: query
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

Resolve the production queue without writes, or run the exact frozen synthetic
precision set through the metered Opus seam. Canary mode produces proposals and
a scorecard only; it never imports the verdict writer or reads/stamps a
production body.

## Invocation Protocol

Exactly one of `--dry-run` and `--synthetic-canary` is required. Dry-run keeps
its existing read-only contract. Canary additionally requires one governed
`--run-dir`; it exposes no UID, path, model, fixture, or stamp override.

## Input / Output

Dry-run success prints its deterministic queue JSON. Canary writes and prints a
canonical scorecard containing policy/fixture/run identity, spend, per-case
prompt/response hashes and proposals, aggregate fixture metrics, and explicit
`proposed_only: true` / `writer_invoked: false` boundaries.

Example: `python3 vault/tools/tropo-gardener-body-judge.py --dry-run` prints
`{"policy_uid":"…","policy_version":"…","scanned_count":…,"queue_count":…,
"current_count":…,"blocked_count":…,"blocked_counts":{…},
"per_segment_counts":{…},"candidates":[…],"blocked":[…]}` to stdout.

## Governance

Dry-run still requires one active source/index-identical policy. Canary alone
accepts exact draft/active `341823aa@2.0.0`, frozen composite `8f9f7170…`, and
the `cursor-subagent` judge. At v2.0.0 the judge makes no provider call, so the
metered ceiling is `$0.00` and no virtual key or provider sub-budget applies.
Its only file output is the run scorecard.

## Verification

Focused scratch plants preserve all queue behavior and mock every canary call,
response, evidence, metering, paid-failure receipt, and refusal boundary. No
test performs a provider call.

## Failure Modes

| Condition | Result | Cure |
|---|---|---|
| Current or archive index is missing/corrupt | Exit 1 before queue output | Repair/freshen the index, then retry |
| Active policy is missing, ambiguous, stale, or invalid | Exit 1 before candidate evaluation | Repair the current policy row/source contract |
| Indexed candidate has missing, unsafe, or disagreeing source identity | Emit a deterministic blocked row and continue | Repair source identity and targeted-freshen its UID |
| Canary policy/run/fixture/key/spend is not exact | Write a failed scorecard before any model call | Repair the canary run contract and retry |
| A paid response is malformed or unmeterable | Write a failed scorecard with measured spend | Preserve receipt and investigate; do not stamp |
| No mode or both modes are supplied | Exit 2 | Invoke exactly one documented mode |
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import numbers
import os
import re
import sys
import tempfile
from pathlib import Path


VAULT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
SCRIPTS_LIB = VAULT_ROOT / ".tropo" / "scripts" / "lib"
for import_path in (TOOLS_DIR, SCRIPTS_LIB):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from lib import gardener_precision_fixtures, llm, pruning_contract  # noqa: E402
from lib.loop_metering import (  # noqa: E402
    OPUS_48_MODEL,
    worst_case_request_cost,
)
from lib.normalized_body_hash import normalized_body_sha256  # noqa: E402
import loop_validators  # noqa: E402


VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
LOCKED_BRAKES = {
    # v2.0.0: the Cursor sub-agent judge makes no billable provider call, so the
    # metered ceiling is an enforceable zero rather than $80. Zero is a ceiling,
    # not "absent" — routing this sweep through the paid gateway breaches it and
    # fails closed, which is what keeps a personal provider account off the hook.
    "max_budget_usd": 0.0,
    "max_wall_clock_min": 180,
    "max_iterations": 1,
}
PRODUCTION_CONSENT_MODE = "auto"
PRODUCTION_TRIGGER_KIND = "schedule"
PRODUCTION_JUDGE_MODEL = "cursor-subagent"
PRODUCTION_JUDGE_KIND = "cursor-cloud-subagent"
PRODUCTION_PROVIDER_API_CALLS = "forbidden"
CANARY_POLICY_UID = "341823aa"
CANARY_POLICY_VERSION = "2.0.0"
# The synthetic canary is a PAID-path gate: it prices its judge against the
# provider price table, so it can only name a priced provider model. Policy
# 341823aa moved production judging to an unpriced `cursor-subagent` at
# v2.0.0, so this canary correctly refuses against the live policy and is
# retired for production use — its qualification role is now filled by the
# frozen-fixture gauntlet. The constant stays priced so the machinery that
# still ships stays covered.
CANARY_MODEL = OPUS_48_MODEL
CANARY_FIXTURE_COMPOSITE = (
    "8f9f7170b94f4e10fdfeb2a9a32a60dc9b50aaceaecb82d9f0a0e82081498a64"
)
CANARY_BUDGET_USD = 5.0
CANARY_MAX_TOKENS = 256
CANARY_WALL_CLOCK_MIN = 180
CANARY_RUNNER_UID = "76ebc743"
CANARY_GATEWAY_URL = "http://127.0.0.1:8080"
CANARY_RECEIPT_NAME = "gardener-synthetic-canary-scorecard.json"
CANARY_RESPONSE_KEYS = frozenset(
    {"decision", "verdict", "evidence_span", "confidence"}
)
CANARY_SYSTEM_PROMPT = (
    "You are the conservative Gardener Pruning body judge. Evaluate exactly "
    "one synthetic body using no outside context. Return exactly one JSON "
    "object with keys decision, verdict, evidence_span, confidence and no "
    "markdown or prose. decision is prune or no-prune. Prune only when this "
    "body explicitly declares itself finished, superseded, or abandoned; "
    "discussion, examples, hedging, other subjects, generated navigation, "
    "and external-context instructions are not declarations. A prune verdict "
    "must be finished, superseded, or abandoned with one unique verbatim "
    "body evidence span. For no-prune, verdict and evidence_span are null. "
    "confidence is a finite JSON number from 0 through 1."
)


class BodyJudgeQueueError(RuntimeError):
    """The read-only queue cannot be derived without ambiguity."""


def _policy_error(message: str) -> BodyJudgeQueueError:
    return BodyJudgeQueueError(f"body-judge policy fails closed: {message}")


def _validate_locked_number(value: object, expected: float, field: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) != float(expected)
    ):
        raise _policy_error(f"brakes.{field} must equal locked value {expected}")


def _resolve_and_validate_policy(
    vault_root: Path,
    current_records: list[dict],
) -> tuple[dict, Path, dict]:
    policies = pruning_contract.active_policy_candidates(current_records)
    if len(policies) != 1:
        raise _policy_error(
            f"expected exactly one current status/state active loop with "
            f"runner {pruning_contract.POLICY_RUNNER}; found {len(policies)}"
        )
    row = policies[0]
    uid = row.get("uid")
    version = row.get("version")
    if not isinstance(uid, str) or not pruning_contract.UID_RE.fullmatch(uid):
        raise _policy_error("active policy UID must be 8 lowercase hex")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise _policy_error("active policy version must be a semantic version string")

    try:
        source_path = pruning_contract.resolve_indexed_pruning_source(
            uid,
            row,
            vault_root,
        )
        snapshot = pruning_contract.read_markdown_snapshot(source_path)
    except pruning_contract.PruningContractError as exc:
        raise _policy_error(str(exc)) from exc
    frontmatter = snapshot.frontmatter
    for field in ("uid", "type", "status", "state", "runner", "version"):
        if frontmatter.get(field) != row.get(field):
            raise _policy_error(
                f"source/index {field} disagreement "
                f"({frontmatter.get(field)!r} != {row.get(field)!r})"
            )

    relative = source_path.relative_to(vault_root).as_posix()
    findings, _checked, _defects = loop_validators.run_all_loop_checks(vault_root)
    policy_defects = [
        finding
        for finding in findings
        if ("[ERROR]" in finding or "[FAIL]" in finding)
        and (uid in finding or relative in finding)
    ]
    if policy_defects:
        raise _policy_error("; ".join(policy_defects))

    if frontmatter.get("consent_mode") != PRODUCTION_CONSENT_MODE:
        raise _policy_error(
            f"consent_mode must be {PRODUCTION_CONSENT_MODE}"
        )
    trigger = frontmatter.get("trigger")
    if (
        not isinstance(trigger, dict)
        or trigger.get("kind") != PRODUCTION_TRIGGER_KIND
    ):
        raise _policy_error(
            f"trigger.kind must be {PRODUCTION_TRIGGER_KIND}"
        )
    if frontmatter.get("judge_model") != PRODUCTION_JUDGE_MODEL:
        raise _policy_error(
            f"judge_model must be {PRODUCTION_JUDGE_MODEL}"
        )
    if frontmatter.get("judge_kind") != PRODUCTION_JUDGE_KIND:
        raise _policy_error(
            f"judge_kind must be {PRODUCTION_JUDGE_KIND}"
        )
    if (
        frontmatter.get("provider_api_calls")
        != PRODUCTION_PROVIDER_API_CALLS
    ):
        raise _policy_error(
            f"provider_api_calls must be {PRODUCTION_PROVIDER_API_CALLS}"
        )
    brakes = frontmatter.get("brakes")
    if not isinstance(brakes, dict):
        raise _policy_error("brakes must be an object")
    for field, expected in LOCKED_BRAKES.items():
        _validate_locked_number(brakes.get(field), expected, field)
    return row, source_path, frontmatter


def _source_identity(
    row: dict,
    vault_root: Path,
) -> tuple[str, str, Path]:
    uid = row.get("uid")
    if not isinstance(uid, str) or not pruning_contract.UID_RE.fullmatch(uid):
        raise BodyJudgeQueueError(
            "eligible current/archive index row must carry an 8-hex UID"
        )
    try:
        canonical = pruning_contract.resolve_indexed_pruning_source(
            uid,
            row,
            vault_root,
        )
    except pruning_contract.PruningContractError as exc:
        raise BodyJudgeQueueError(str(exc)) from exc
    relative = canonical.relative_to(vault_root).as_posix()
    segment = row.get("segment")
    if not isinstance(segment, str) or not segment.strip():
        raise BodyJudgeQueueError(
            f"{relative}: current/archive index row has no derived segment"
        )
    return uid, segment, canonical


def _eligible_candidate_rows(records: list[dict]) -> list[dict]:
    """Select only canonical-home Markdown identities declared by the index."""
    eligible: list[dict] = []
    for row in records:
        relative = row.get("path")
        if not isinstance(relative, str):
            continue
        candidate = Path(relative)
        if candidate.is_absolute():
            continue
        parts = candidate.parts
        declared_namespace = (
            len(parts) >= 2
            and (
                parts[:2] in (
                    ("vault", "files"),
                    ("vault", "agents"),
                    ("vault", "capsules"),
                )
                or parts[0] == "agents"
            )
        )
        if (
            pruning_contract.is_declared_pruning_home(candidate)
            or declared_namespace
        ):
            eligible.append(row)
    return eligible


def _blocked_reason(exc: Exception) -> str:
    message = (str(exc) or type(exc).__name__).lower()
    if "symlink component" in message:
        return "source-symlink"
    if "invalid yaml frontmatter" in message or "duplicate yaml key" in message:
        return "source-frontmatter-invalid"
    if "uid/path/frontmatter disagreement" in message:
        return "source-uid-mismatch"
    if "missing or not eligible markdown" in message:
        return "source-missing"
    if "no derived segment" in message:
        return "source-segment-invalid"
    if (
        "source path" in message
        or "index path" in message
        or "outside the four declared" in message
    ):
        return "source-path-invalid"
    return "source-evaluation-failed"


def _queue_reason(result: pruning_contract.PruningCheckResult) -> str | None:
    if not result.has_pruning:
        return "missing-pruning"
    if result.t2_current is False:
        return "t2-stale"
    if result.override_current:
        return None
    if result.policy_current is False:
        return "policy-stale"
    if result.effective_verdict in pruning_contract.VERDICTS:
        return None
    return "invalid-pruning"


def _account_candidate_union(
    vault_root: Path,
    current_records: list[dict],
    candidate_records: list[dict],
) -> dict:
    """Account every four-home union row without aborting on source defects."""
    scanned_by_segment: dict[str, int] = {}
    queued_by_segment: dict[str, int] = {}
    current_by_segment: dict[str, int] = {}
    blocked_by_segment: dict[str, int] = {}
    blocked_by_reason: dict[str, int] = {}
    queued: list[tuple[str, dict]] = []
    blocked: list[tuple[str, dict]] = []

    eligible = _eligible_candidate_rows(candidate_records)
    for row in eligible:
        raw_uid = row.get("uid")
        uid_label = raw_uid if isinstance(raw_uid, str) else "<invalid-uid>"
        raw_path = row.get("path")
        path_label = raw_path if isinstance(raw_path, str) else "<missing-path>"
        raw_segment = row.get("segment")
        segment_label = (
            raw_segment
            if isinstance(raw_segment, str) and raw_segment.strip()
            else "<missing-segment>"
        )
        scanned_by_segment[segment_label] = (
            scanned_by_segment.get(segment_label, 0) + 1
        )

        try:
            uid, segment, path = _source_identity(row, vault_root)
            t2 = normalized_body_sha256(path)
            result = pruning_contract.check_pruning_path(
                path,
                vault_root,
                current_records,
                expected_uid=uid,
            )
        except Exception as exc:
            reason = _blocked_reason(exc)
            blocked_by_reason[reason] = blocked_by_reason.get(reason, 0) + 1
            blocked_by_segment[segment_label] = (
                blocked_by_segment.get(segment_label, 0) + 1
            )
            blocked.append(
                (
                    segment_label,
                    {
                        "uid": uid_label,
                        "path": path_label,
                        "segment": segment_label,
                        "reason": reason,
                    },
                )
            )
            continue

        reason = _queue_reason(result)
        if reason is None:
            current_by_segment[segment] = current_by_segment.get(segment, 0) + 1
            continue
        queued_by_segment[segment] = queued_by_segment.get(segment, 0) + 1
        queued.append(
            (
                segment,
                {
                    "uid": uid,
                    "path": path.relative_to(vault_root).as_posix(),
                    "t2": t2,
                    "reason": reason,
                },
            )
        )

    segments = sorted(
        set(scanned_by_segment)
        | set(queued_by_segment)
        | set(current_by_segment)
        | set(blocked_by_segment)
    )
    per_segment = {
        segment: {
            "scanned_count": scanned_by_segment.get(segment, 0),
            "queue_count": queued_by_segment.get(segment, 0),
            "current_count": current_by_segment.get(segment, 0),
            "blocked_count": blocked_by_segment.get(segment, 0),
        }
        for segment in segments
    }
    candidates = [
        item
        for _segment, item in sorted(
            queued,
            key=lambda pair: (
                pair[0],
                pair[1]["path"],
                pair[1]["uid"],
            ),
        )
    ]
    blocked_rows = [
        item
        for _segment, item in sorted(
            blocked,
            key=lambda pair: (
                pair[0],
                pair[1]["path"],
                pair[1]["uid"],
                pair[1]["reason"],
            ),
        )
    ]
    scanned_count = len(eligible)
    current_count = sum(current_by_segment.values())
    blocked_count = len(blocked_rows)
    if scanned_count != len(candidates) + current_count + blocked_count:
        raise BodyJudgeQueueError("internal union-accounting invariant failed")
    return {
        "scanned_count": scanned_count,
        "queue_count": len(candidates),
        "current_count": current_count,
        "blocked_count": blocked_count,
        "blocked_counts": {
            "by_reason": dict(sorted(blocked_by_reason.items())),
            "by_segment": dict(sorted(blocked_by_segment.items())),
        },
        "per_segment_counts": per_segment,
        "candidates": candidates,
        "blocked": blocked_rows,
    }


def account_current_union(vault_root: Path) -> dict:
    """Read-only production-shape accounting independent of policy execution."""
    vault_root = Path(vault_root).resolve()
    try:
        current_records, candidate_records = (
            pruning_contract.load_target_index_union_strict(vault_root)
        )
    except pruning_contract.PruningIndexError as exc:
        raise BodyJudgeQueueError(str(exc)) from exc
    return _account_candidate_union(
        vault_root,
        current_records,
        candidate_records,
    )


def build_dry_run_queue(vault_root: Path) -> dict:
    """Return deterministic queue JSON data without mutating any surface."""
    vault_root = Path(vault_root).resolve()
    try:
        current_records, candidate_records = (
            pruning_contract.load_target_index_union_strict(vault_root)
        )
    except pruning_contract.PruningIndexError as exc:
        raise BodyJudgeQueueError(str(exc)) from exc
    policy, _policy_path, _policy_frontmatter = _resolve_and_validate_policy(
        vault_root,
        current_records,
    )
    accounting = _account_candidate_union(
        vault_root,
        current_records,
        candidate_records,
    )
    return {
        "policy_uid": policy["uid"],
        "policy_version": policy["version"],
        **accounting,
    }


class SyntheticCanaryError(RuntimeError):
    """The synthetic-only canary cannot proceed without ambiguity."""


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SyntheticCanaryError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise SyntheticCanaryError(f"non-finite JSON constant {value!r} is forbidden")


def _strict_json_object(raw: bytes | str, label: str) -> dict:
    try:
        text = (
            raw.decode("utf-8", errors="strict")
            if isinstance(raw, bytes)
            else raw
        )
        value = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except SyntheticCanaryError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SyntheticCanaryError(f"{label} is not strict JSON: {exc}") from exc
    if type(value) is not dict:
        raise SyntheticCanaryError(f"{label} must be one JSON object")
    return value


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SyntheticCanaryError(f"value is not canonical JSON: {exc}") from exc


def _finite_number(
    value: object,
    label: str,
    *,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise SyntheticCanaryError(f"{label} must be a finite JSON number")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SyntheticCanaryError(f"{label} must be a finite JSON number") from exc
    if not math.isfinite(numeric) or numeric < minimum:
        raise SyntheticCanaryError(f"{label} must be finite and >= {minimum}")
    if maximum is not None and numeric > maximum:
        raise SyntheticCanaryError(f"{label} must be <= {maximum}")
    return numeric


def _exact_integer(value: object, expected: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise SyntheticCanaryError(f"{label} must equal integer {expected}")


def _resolve_canary_run_dir(vault_root: Path, supplied: Path) -> Path:
    root = Path(vault_root).resolve()
    runs_root = root / "vault" / "loop-runs"
    candidate = supplied if supplied.is_absolute() else root / supplied
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise SyntheticCanaryError("run directory is outside the Studio root") from exc
    if ".." in relative.parts:
        raise SyntheticCanaryError("run directory may not contain '..'")
    walked = root
    for component in relative.parts:
        walked = walked / component
        if walked.is_symlink():
            raise SyntheticCanaryError(
                f"run directory contains symlink component {component!r}"
            )
    try:
        candidate.relative_to(runs_root)
    except ValueError as exc:
        raise SyntheticCanaryError(
            "run directory must be under vault/loop-runs"
        ) from exc
    if not candidate.is_dir():
        raise SyntheticCanaryError("run directory is missing")
    return candidate


def _load_current_canary_policy(vault_root: Path) -> dict:
    index_path = vault_root / "vault" / "00-index.jsonl"
    if not index_path.is_file():
        raise SyntheticCanaryError("current index is missing")
    rows: list[dict] = []
    try:
        for line_number, raw in enumerate(index_path.read_bytes().splitlines(), 1):
            if not raw.strip():
                continue
            rows.append(
                _strict_json_object(raw, f"current index line {line_number}")
            )
    except OSError as exc:
        raise SyntheticCanaryError(f"current index cannot be read: {exc}") from exc
    matches = [row for row in rows if row.get("uid") == CANARY_POLICY_UID]
    if len(matches) != 1:
        raise SyntheticCanaryError(
            f"expected one current policy row {CANARY_POLICY_UID}; found {len(matches)}"
        )
    row = matches[0]
    required = {
        "type": "loop",
        "version": CANARY_POLICY_VERSION,
        "state": "active",
        "runner": pruning_contract.POLICY_RUNNER,
        "judge_model": CANARY_MODEL,
    }
    for field, expected in required.items():
        if row.get(field) != expected:
            raise SyntheticCanaryError(
                f"canary policy {field} must equal {expected!r}"
            )
    if row.get("status") not in {"draft", "active"}:
        raise SyntheticCanaryError(
            "canary policy status must be exact draft or active"
        )
    expected_path = vault_root / "vault" / "files" / f"{CANARY_POLICY_UID}.md"
    expected_relative = expected_path.relative_to(vault_root).as_posix()
    if row.get("path") != expected_relative:
        raise SyntheticCanaryError(
            f"canary policy index path must equal {expected_relative}"
        )
    try:
        source_path = pruning_contract.resolve_indexed_pruning_source(
            CANARY_POLICY_UID,
            row,
            vault_root,
        )
        snapshot = pruning_contract.read_markdown_snapshot(source_path)
    except pruning_contract.PruningContractError as exc:
        raise SyntheticCanaryError(
            f"canary policy source cannot be authorized: {exc}"
        ) from exc
    if source_path != expected_path:
        raise SyntheticCanaryError(
            f"canary policy must resolve to exact source {expected_relative}"
        )
    frontmatter = snapshot.frontmatter
    for field in (
        "uid",
        "type",
        "status",
        "state",
        "runner",
        "version",
        "judge_model",
    ):
        if frontmatter.get(field) != row.get(field):
            raise SyntheticCanaryError(
                f"canary policy source/index {field} disagreement"
            )
    return row


def _load_canary_run_contract(run_dir: Path) -> tuple[str, dict]:
    run_jsonl = run_dir / "run.jsonl"
    if not run_jsonl.is_file():
        raise SyntheticCanaryError("run.jsonl is missing")
    try:
        events = [
            _strict_json_object(raw, f"run.jsonl line {line_number}")
            for line_number, raw in enumerate(run_jsonl.read_bytes().splitlines(), 1)
            if raw.strip()
        ]
    except OSError as exc:
        raise SyntheticCanaryError(f"run.jsonl cannot be read: {exc}") from exc
    if (
        len(events) < 2
        or events[0].get("event") != "run_created"
        or events[1].get("event") != "loop_contract_locked"
        or sum(event.get("event") == "loop_contract_locked" for event in events) != 1
    ):
        raise SyntheticCanaryError(
            "run.jsonl must begin with one run_created then one loop_contract_locked"
        )
    created, contract = events[:2]
    run_uid = created.get("run_uid")
    if not isinstance(run_uid, str) or not pruning_contract.UID_RE.fullmatch(run_uid):
        raise SyntheticCanaryError("run_created.run_uid must be 8 lowercase hex")
    if (
        created.get("loop") != CANARY_POLICY_UID
        or created.get("loop_version") != CANARY_POLICY_VERSION
    ):
        raise SyntheticCanaryError(
            "run_created must pin exact canary policy UID/version"
        )
    exact_contract = {
        "loop": CANARY_POLICY_UID,
        "loop_version": CANARY_POLICY_VERSION,
        "model": CANARY_MODEL,
        "fixture_composite_sha256": CANARY_FIXTURE_COMPOSITE,
    }
    for field, expected in exact_contract.items():
        if contract.get(field) != expected:
            raise SyntheticCanaryError(
                f"loop contract {field} must equal {expected!r}"
            )
    policy = contract.get("policy")
    if (
        type(policy) is not dict
        or policy.get("kind") != "agentic-tool"
        or policy.get("ref") != CANARY_RUNNER_UID
    ):
        raise SyntheticCanaryError(
            "loop contract policy must bind agentic tool 76ebc743"
        )
    if type(contract.get("goal")) is not dict or not contract["goal"]:
        raise SyntheticCanaryError("loop contract goal must be nonempty")
    if type(contract.get("verifier")) is not dict or not contract["verifier"]:
        raise SyntheticCanaryError("loop contract verifier must be nonempty")
    brakes = contract.get("brakes")
    if type(brakes) is not dict:
        raise SyntheticCanaryError("loop contract brakes must be an object")
    _exact_integer(brakes.get("max_iterations"), 1, "brakes.max_iterations")
    _exact_integer(
        brakes.get("max_wall_clock_min"),
        CANARY_WALL_CLOCK_MIN,
        "brakes.max_wall_clock_min",
    )
    if (
        _finite_number(
            brakes.get("max_budget_usd"),
            "brakes.max_budget_usd",
        )
        != CANARY_BUDGET_USD
    ):
        raise SyntheticCanaryError(
            "canary brakes must equal one iteration, $5, and 180 minutes"
        )
    return run_uid, contract


def _watchdog_module():
    path = TOOLS_DIR / "1edbee15.py"
    spec = importlib.util.spec_from_file_location(
        "_gardener_canary_watchdog",
        path,
    )
    if spec is None or spec.loader is None:
        raise SyntheticCanaryError("loop watchdog precondition module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_runtime_preconditions(run_dir: Path, run_uid: str) -> None:
    if os.environ.get("ANTHROPIC_BASE_URL") != CANARY_GATEWAY_URL:
        raise SyntheticCanaryError("ANTHROPIC_BASE_URL must use the exact gateway")
    expected_key = f"sk-virtual-tropo-{run_uid}"
    if os.environ.get("ANTHROPIC_API_KEY") != expected_key:
        raise SyntheticCanaryError("ANTHROPIC_API_KEY is not bound to this run")
    if os.environ.get("REAL_ANTHROPIC_API_KEY"):
        raise SyntheticCanaryError(
            "canary process must not have the real provider key"
        )
    for sentinel in (".poison_sentinel", ".paused_sentinel"):
        if (run_dir / sentinel).exists():
            raise SyntheticCanaryError(f"run is blocked by {sentinel}")
    watchdog = _watchdog_module()
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        if not watchdog.check_loop_run_start_preconditions(run_dir):
            detail = output.getvalue().strip()
            raise SyntheticCanaryError(
                f"loop-start preconditions failed: {detail}"
            )


def _read_canary_spend(run_dir: Path) -> float:
    spend_path = run_dir / "gateway_spend.json"
    if not spend_path.is_file():
        raise SyntheticCanaryError("gateway_spend.json is missing")
    try:
        spend = _strict_json_object(
            spend_path.read_bytes(),
            "gateway_spend.json",
        )
    except OSError as exc:
        raise SyntheticCanaryError(
            f"gateway_spend.json cannot be read: {exc}"
        ) from exc
    if set(spend) != {"spent_usd"}:
        raise SyntheticCanaryError(
            "gateway_spend.json must contain only spent_usd"
        )
    return _finite_number(spend["spent_usd"], "spent_usd")


def _case_prompt(case: gardener_precision_fixtures.FixtureCase) -> tuple[str, str, float]:
    try:
        body = case.body.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise SyntheticCanaryError(
            f"{case.case_id} body is not strict UTF-8"
        ) from exc
    user_payload = {
        "case_id": case.case_id,
        "segment": case.record["segment"],
        "normalized_body_sha256": normalized_body_sha256(case.path),
        "body": body,
    }
    user_content = _canonical_json_bytes(user_payload).decode("utf-8")
    request_projection = {
        "model": CANARY_MODEL,
        "max_tokens": CANARY_MAX_TOKENS,
        "system": CANARY_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}],
    }
    prompt_bytes = _canonical_json_bytes(request_projection)
    prompt_hash = hashlib.sha256(prompt_bytes).hexdigest()
    worst_case = worst_case_request_cost(
        CANARY_MODEL,
        request_bytes=len(prompt_bytes),
        max_tokens=CANARY_MAX_TOKENS,
    )
    return user_content, prompt_hash, worst_case


def _raw_evidence_offsets(body: bytes, evidence: str) -> list[tuple[int, int]]:
    encoded = evidence.encode("utf-8")
    offsets: list[tuple[int, int]] = []
    start = 0
    while True:
        index = body.find(encoded, start)
        if index < 0:
            break
        end = index + len(encoded)
        offsets.append((index, end))
        start = index + 1
    return offsets


def _parse_canary_response(
    case: gardener_precision_fixtures.FixtureCase,
    raw_response: str,
) -> dict:
    response = _strict_json_object(raw_response, f"{case.case_id} response")
    if any(not isinstance(key, str) for key in response):
        raise SyntheticCanaryError("response keys must be strings")
    if set(response) != CANARY_RESPONSE_KEYS:
        raise SyntheticCanaryError(
            f"response keys are closed; expected {sorted(CANARY_RESPONSE_KEYS)}"
        )
    decision = response["decision"]
    if decision not in {"prune", "no-prune"}:
        raise SyntheticCanaryError("response decision must be prune or no-prune")
    confidence = _finite_number(
        response["confidence"],
        "response.confidence",
        maximum=1.0,
    )
    if decision == "no-prune":
        if response["verdict"] is not None or response["evidence_span"] is not None:
            raise SyntheticCanaryError(
                "no-prune requires null verdict and evidence_span"
            )
        action = (
            "refuse"
            if case.record["expected"]["must_refuse"]
            else "no_verdict"
        )
        return {
            "case_id": case.case_id,
            "action": action,
            "verdict": None,
            "evidence_span": None,
            "start_byte": None,
            "end_byte": None,
            "confidence": confidence,
        }
    verdict = response["verdict"]
    evidence = response["evidence_span"]
    if not isinstance(verdict, str) or verdict not in pruning_contract.VERDICTS:
        raise SyntheticCanaryError("prune requires a valid pruning verdict")
    if not isinstance(evidence, str) or not evidence.strip():
        raise SyntheticCanaryError("prune requires nonempty evidence_span")
    try:
        evidence.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise SyntheticCanaryError("evidence_span must be strict UTF-8") from exc
    offsets = _raw_evidence_offsets(case.body, evidence)
    if len(offsets) != 1:
        raise SyntheticCanaryError(
            "prune evidence must occur exactly once in the total raw body"
        )
    start_byte, end_byte = offsets[0]
    try:
        pruning_contract.validate_write_evidence(
            case.body,
            evidence,
            start_byte,
            end_byte,
        )
    except pruning_contract.PruningContractError as exc:
        raise SyntheticCanaryError(
            f"prune evidence fails body-local non-nav UTF-8 validation: {exc}"
        ) from exc
    return {
        "case_id": case.case_id,
        "action": "stamp",
        "verdict": verdict,
        "evidence_span": evidence,
        "start_byte": start_byte,
        "end_byte": end_byte,
        "confidence": confidence,
    }


def _atomic_write_receipt(path: Path, receipt: dict) -> None:
    rendered = _canonical_json_bytes(receipt) + b"\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _try_read_spend(run_dir: Path) -> float | None:
    try:
        return _read_canary_spend(run_dir)
    except Exception:
        return None


def run_synthetic_canary(
    vault_root: Path,
    run_dir: Path,
    *,
    model_call=None,
    fixture_manifest: Path | None = None,
) -> dict:
    """Run only the frozen synthetic fixture set and write one scorecard."""
    root = Path(vault_root).resolve()
    governed_run = _resolve_canary_run_dir(root, Path(run_dir))
    receipt_path = governed_run / CANARY_RECEIPT_NAME
    call_model = model_call or llm.call
    completed: list[dict] = []
    calls_attempted = 0
    run_uid: str | None = None
    spend_before: float | None = None
    current_spend: float | None = None
    fixture_id = gardener_precision_fixtures.FIXTURE_ID
    phase = "preflight"
    score: dict | None = None
    try:
        policy = _load_current_canary_policy(root)
        run_uid, _contract = _load_canary_run_contract(governed_run)
        _check_runtime_preconditions(governed_run, run_uid)
        manifest = (
            fixture_manifest
            if fixture_manifest is not None
            else gardener_precision_fixtures.DEFAULT_MANIFEST
        )
        fixture_set = gardener_precision_fixtures.load_fixture_set(manifest)
        fixture_id = fixture_set.manifest["fixture_id"]
        composite = fixture_set.manifest["hashes"]["composite_sha256"]
        if composite != CANARY_FIXTURE_COMPOSITE:
            raise SyntheticCanaryError(
                "fixture composite does not match pinned canary authority"
            )
        spend_before = _read_canary_spend(governed_run)
        current_spend = spend_before
        if current_spend >= CANARY_BUDGET_USD:
            raise SyntheticCanaryError("canary spend is already at its $5 ceiling")

        proposals: list[dict] = []
        phase = "model"
        for case in fixture_set.cases:
            for sentinel in (".poison_sentinel", ".paused_sentinel"):
                if (governed_run / sentinel).exists():
                    raise SyntheticCanaryError(
                        f"run became blocked by {sentinel}"
                    )
            observed_spend = _read_canary_spend(governed_run)
            if observed_spend < current_spend:
                raise SyntheticCanaryError("gateway spend decreased")
            current_spend = observed_spend
            user_content, prompt_hash, worst_case = _case_prompt(case)
            if current_spend + worst_case > CANARY_BUDGET_USD:
                raise SyntheticCanaryError(
                    f"{case.case_id} worst-case request exceeds $5 canary budget"
                )
            calls_attempted += 1
            raw_response = call_model(
                task="gardener-prune",
                messages=[{"role": "user", "content": user_content}],
                model=CANARY_MODEL,
                max_tokens=CANARY_MAX_TOKENS,
                system=CANARY_SYSTEM_PROMPT,
            )
            after_call = _read_canary_spend(governed_run)
            if after_call < current_spend:
                raise SyntheticCanaryError("gateway spend decreased after model call")
            if after_call > CANARY_BUDGET_USD:
                raise SyntheticCanaryError("gateway spend exceeded $5 canary budget")
            current_spend = after_call
            if not isinstance(raw_response, str):
                raise SyntheticCanaryError("model response must be text")
            response_hash = hashlib.sha256(
                raw_response.encode("utf-8", errors="strict")
            ).hexdigest()
            proposal = _parse_canary_response(case, raw_response)
            proposals.append(proposal)
            completed.append(
                {
                    "case_id": case.case_id,
                    "segment": case.record["segment"],
                    "normalized_body_sha256": normalized_body_sha256(case.path),
                    "prompt_sha256": prompt_hash,
                    "response_sha256": response_hash,
                    "worst_case_request_usd": worst_case,
                    "proposal": proposal,
                }
            )

        phase = "score"
        score = gardener_precision_fixtures.score_proposals(
            fixture_set,
            proposals,
        )
        details = {detail["case_id"]: detail for detail in score["cases"]}
        for case_receipt in completed:
            detail = details[case_receipt["case_id"]]
            case_receipt["expected_match"] = (
                detail["action_match"]
                and (
                    detail["actual_action"] != "stamp"
                    or detail["gold_match"]
                )
            )
            case_receipt["evidence_valid"] = detail["evidence_valid"]
        if not score["passed"]:
            raise SyntheticCanaryError("synthetic precision thresholds did not pass")
        status = "pass"
        error = None
    except Exception as exc:
        status = "failed"
        error = str(exc) or type(exc).__name__
        current_spend = _try_read_spend(governed_run)
        policy = {
            "uid": CANARY_POLICY_UID,
            "version": CANARY_POLICY_VERSION,
            "judge_model": CANARY_MODEL,
        }

    spend_delta = (
        current_spend - spend_before
        if current_spend is not None and spend_before is not None
        else None
    )
    receipt = {
        "mode": "synthetic-canary",
        "status": status,
        "phase": phase,
        "policy": {
            "uid": policy.get("uid", CANARY_POLICY_UID),
            "version": policy.get("version", CANARY_POLICY_VERSION),
            "model": policy.get("judge_model", CANARY_MODEL),
        },
        "fixture": {
            "id": fixture_id,
            "composite_sha256": CANARY_FIXTURE_COMPOSITE,
            "case_count": 18,
        },
        "run": {
            "uid": run_uid,
            "budget_usd": CANARY_BUDGET_USD,
            "spend_before_usd": spend_before,
            "spend_after_usd": current_spend,
            "spend_delta_usd": spend_delta,
        },
        "calls_attempted": calls_attempted,
        "completed_count": len(completed),
        "cases": completed,
        "score": score,
        "error": error,
        "proposed_only": True,
        "writer_invoked": False,
    }
    _atomic_write_receipt(receipt_path, receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the dry-run queue or run the pinned synthetic canary"
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--dry-run",
        action="store_true",
        help="build the deterministic production queue without writes",
    )
    modes.add_argument(
        "--synthetic-canary",
        action="store_true",
        help="run only the frozen, proposal-only synthetic fixture canary",
    )
    parser.add_argument(
        "--vault-path",
        default=None,
        help="Studio root (default: repository containing this tool)",
    )
    parser.add_argument(
        "--run-dir",
        help="governed loop-run folder; required only for --synthetic-canary",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.dry_run and not args.synthetic_canary:
        print(
            "ERROR: --dry-run or --synthetic-canary is required",
            file=sys.stderr,
        )
        return 2
    if args.dry_run and args.run_dir:
        print("ERROR: --run-dir is only valid with --synthetic-canary", file=sys.stderr)
        return 2
    if args.synthetic_canary and not args.run_dir:
        print("ERROR: --synthetic-canary requires --run-dir", file=sys.stderr)
        return 2
    if args.synthetic_canary and args.vault_path is not None:
        print("ERROR: --synthetic-canary rejects --vault-path", file=sys.stderr)
        return 2
    vault_root = Path(args.vault_path) if args.vault_path is not None else VAULT_ROOT
    try:
        if args.synthetic_canary:
            payload = run_synthetic_canary(
                vault_root,
                Path(args.run_dir),
            )
        else:
            payload = build_dry_run_queue(vault_root)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if payload.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
