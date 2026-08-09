#!/usr/bin/env python3
"""---
uid: 'e45c7a1d'
name: distiller-metered-canary
type: tool
title: "distiller-metered-canary — fixed OS-only Distiller canary"
description: "Prepares without a ledger, readiness-binds, then runs attempt 7 with exact bounded JSON response normalization and raw evidence."
status: active
state: active
owner: talos
domain: "One pre-activation Distiller canary under the exact 0c938a95@1.8.0 attempt-7 authority"
spawnable_by:
  - all-executives
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-distiller-metered-canary.py --run-dir PATH"
script_path: vault/tools/tropo-distiller-metered-canary.py
input:
  type: object
  required: [run-dir]
  properties:
    run-dir:
      type: string
      description: "Direct governed child of vault/loop-runs."
  additionalProperties: false
output:
  type: object
  description: "Prepared/waiting status or closed pass/fail scorecard with exact gateway evidence."
destructive: false
audit_required: true
writes_scope:
  - vault/loop-runs/*/run.jsonl
  - vault/loop-runs/*/gateway_spend.json
  - vault/loop-runs/*/distiller-metered-canary-preparation.json
  - vault/loop-runs/*/distiller-metered-canary-readiness.json
  - vault/loop-runs/*/distiller-metered-canary-gateway-receipts.json
  - vault/loop-runs/*/.distiller-metered-canary-gateway-receipts.json.lock
  - vault/loop-runs/*/distiller-metered-canary-execution-ledger.json
  - vault/loop-runs/*/distiller-metered-canary-scorecard.json
  - vault/loop-runs/.model-spend/*.json
  - vault/loop-runs/.model-spend/*.lock
  - vault/loop-runs/.model-spend/distiller-canary-0c938a95-1.8.0-claim.json
  - vault/loop-runs/.model-spend/distiller-canary-0c938a95-1.8.0-claim.lock
governance_category: query
created: '2026-07-24'
created_by: talos-t35
modified: '2026-07-24'
modified_by: talos
schema_version: 2
capsule_version: '1.8'
governed_by: d5e1b4a3
member_of:
  - 8dd772a0
extraction_scope: ship
---

## Intent

Prepare, then execute one fixed-snapshot OS `parse-query` and one fixed OS
`distill` through registered runner `6389dcd4`. The first invocation verifies
all seven consumed-authority records, creates the fresh attempt-7 loop-run,
global v1.8 claim, and day-recorded preparation receipt with no daily ledger or
day lock, then exits 3 with zero calls. After the operator starts a gateway and
it writes readiness before any v1.8 ledger exists, the second invocation checks
the local SDK/port, initializes only the current execution-day ledger, binds its
initial hash in a closed receipt, and executes once. Both requests are
code-locked to `service_tier=standard_only`;
only Sonnet `distill` additionally sends `inference_geo=global`. The tool never
edits policy, reuses a prior claim or run UID, stamps a canary attestation,
activates production, retries, or starts a gateway.

The two fixed prompts require raw JSON without Markdown fences or prose, with
`{` first and `}` last; attempt-7 authority is carried by the v1.8 policy, run
contract, claim, execution ledger receipt, and metering headers. Both tasks
accept and record any exact nonempty response geo string through 128 characters
under the OS-only path without normalization or character-set restrictions
while requiring standard service.
The local response parser accepts raw JSON or exactly one lowercase
` ```json\n<body>\n``` ` wrapper within a `4,096` UTF-8-byte original-response
bound. It never trims, searches, repairs, or rewrites `LockedLLMResponse`.

A fresh preparation consumes the claim as its first write, then materializes
the run and preparation receipt. It does not inspect, initialize, or read a
v1.8 daily ledger. A matching prepared continuation first proves the canonical
regular v1.8 claim, run, and preparation exactly without reconstruction. Only
after readiness, SDK, port, key separation, empty gateway receipts, and
zero-reservation proofs pass does execution lock the claim and select the
current UTC day. A preexisting ledger requires an exact empty claim-bound
execution receipt; foreign, malformed, symlinked, or unbound state refuses.
A race-created ledger consumes authority and blocks. Any reservation makes
retry terminal.

Before the first invocation, the operator must stop every prior-version gateway
process. Historical binaries may not enforce the current usage contract. Every
generation uses the same fixed `127.0.0.1:8080` port, and execution accepts only
the exact v1.8 run, policy, contract, request hashes, and readiness receipt. A
missing or different-version gateway therefore remains waiting with no
reservation or provider call.

## Invocation Protocol

The CLI accepts only `--run-dir`. Model, task count, segment, policy, fixture,
ledger, admission mode, and activation are not caller-selectable.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import re
import secrets
import socket
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path


STUDIO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib import daily_spend, metered_model  # noqa: E402
from lib.distiller_model_policy import (  # noqa: E402
    CANARY_CLAIM_NAME,
    CANARY_MAX_RESERVED_NANO_USD,
    POLICY_UID,
    POLICY_VERSION,
    PRIOR_RUN_UIDS,
    DistillerModelPolicy,
    claim_canary_authority,
    locked_canary_claim,
    resolve_policy,
    verify_exact_canary_claim,
)


RUNNER_UID = "6389dcd4"
RUNNER_SOURCE = Path(f"vault/tools/{RUNNER_UID}.py")
LOOP_RUNS_RELATIVE_PATH = Path("vault/loop-runs")
SCORECARD_NAME = metered_model.CANARY_SCORECARD_NAME
PREPARATION_NAME = metered_model.CANARY_PREPARATION_NAME
READINESS_NAME = metered_model.CANARY_READINESS_NAME
GATEWAY_RECEIPTS_NAME = metered_model.CANARY_GATEWAY_RECEIPTS_NAME
EXECUTION_LEDGER_NAME = metered_model.CANARY_EXECUTION_LEDGER_NAME
CANARY_TASKS = metered_model.CANARY_TASKS
CANARY_MAX_BUDGET_USD = Decimal("0.26")
CANARY_MAX_ITERATIONS = 2
CANARY_MAX_WALL_CLOCK_MIN = metered_model.CANARY_MAX_WALL_CLOCK_MIN
RESPONSE_MAX_BYTES = 4096
_JSON_FENCE_PREFIX = "```json\n"
_JSON_FENCE_SUFFIX = "\n```"
_UID_RE = re.compile(r"^[0-9a-f]{8}$")


class DistillerCanaryError(RuntimeError):
    """The fixed canary cannot continue without weakening a closed gate."""


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DistillerCanaryError(f"value is not canonical JSON: {exc}") from exc


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DistillerCanaryError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value):
    raise DistillerCanaryError(f"non-finite JSON constant {value!r}")


def _strict_object(raw: bytes | str, field: str) -> dict:
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="strict")
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=Decimal,
        )
    except DistillerCanaryError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise DistillerCanaryError(f"{field} is malformed: {exc}") from exc
    if type(value) is not dict:
        raise DistillerCanaryError(f"{field} must be a JSON object")
    return value


def normalize_response_text(text: str, field: str) -> str:
    """Return raw JSON or remove one exact fence within a 4096-byte response."""
    if not isinstance(text, str):
        raise DistillerCanaryError(f"{field} must be text")
    try:
        raw_size = len(text.encode("utf-8", errors="strict"))
    except UnicodeError as exc:
        raise DistillerCanaryError(f"{field} is not valid UTF-8 text") from exc
    if raw_size == 0 or raw_size > RESPONSE_MAX_BYTES:
        raise DistillerCanaryError(
            f"{field} must be 1 through {RESPONSE_MAX_BYTES} UTF-8 bytes"
        )

    if text.startswith(_JSON_FENCE_PREFIX):
        if not text.endswith(_JSON_FENCE_SUFFIX):
            raise DistillerCanaryError(
                f"{field} exact lowercase json fence is incomplete"
            )
        body = text[len(_JSON_FENCE_PREFIX) : -len(_JSON_FENCE_SUFFIX)]
        if not body or body[0] != "{" or body[-1] != "}":
            raise DistillerCanaryError(
                f"{field} fenced body must begin with {{ and end with }}"
            )
        if "```" in body:
            raise DistillerCanaryError(
                f"{field} fenced body contains a nested or additional fence"
            )
        return body

    if text[0] != "{" or text[-1] != "}":
        raise DistillerCanaryError(
            f"{field} raw form must begin with {{ and end with }}"
        )
    if "```" in text:
        raise DistillerCanaryError(f"{field} raw form may not contain a fence")
    return text


def _path_has_symlink(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _studio_root() -> Path:
    root = Path(STUDIO_ROOT)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise DistillerCanaryError("Studio root must be canonical and absolute")
    if _path_has_symlink(root):
        raise DistillerCanaryError("Studio root has a symlinked path component")
    marker = root / ".tropo"
    if marker.is_symlink() or not marker.is_dir():
        raise DistillerCanaryError("Studio root lacks a regular .tropo marker")
    if not (root / "vault").is_dir():
        raise DistillerCanaryError("Studio root lacks the vault directory")
    return root


def _resolve_run_dir(root: Path, value: Path | str) -> Path:
    supplied = Path(value)
    candidate = supplied if supplied.is_absolute() else root / supplied
    loop_root = root / LOOP_RUNS_RELATIVE_PATH
    if candidate.parent != loop_root or candidate.name in {"", ".", ".."}:
        raise DistillerCanaryError(
            "run directory must be one direct child of vault/loop-runs"
        )
    if _path_has_symlink(candidate) or candidate.is_symlink():
        raise DistillerCanaryError("run directory path is symlinked")
    if loop_root.exists() and (
        loop_root.is_symlink() or not loop_root.is_dir()
    ):
        raise DistillerCanaryError("vault/loop-runs is not a regular directory")
    return candidate


def _run_events(run_uid: str) -> tuple[dict, dict]:
    return metered_model.canary_run_events(run_uid, RUNNER_UID)


def _require_fresh_run_uid(run_uid: str) -> None:
    if run_uid in PRIOR_RUN_UIDS:
        raise DistillerCanaryError(
            "attempt-7 canary requires a fresh run_uid distinct from all seven "
            "prior authority records"
        )


def _write_new(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise DistillerCanaryError(f"refused to create {path.name}: {exc}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _validate_events(events: list[dict]) -> str:
    if len(events) != 2:
        raise DistillerCanaryError("run.jsonl must contain exactly two lock events")
    created, contract = events
    run_uid = created.get("run_uid")
    if not isinstance(run_uid, str) or not _UID_RE.fullmatch(run_uid):
        raise DistillerCanaryError("run_created.run_uid must be 8 lowercase hex")
    _require_fresh_run_uid(run_uid)
    expected_created, expected_contract = _run_events(run_uid)
    expected_contract["brakes"]["max_budget_usd"] = CANARY_MAX_BUDGET_USD
    if created != expected_created or contract != expected_contract:
        raise DistillerCanaryError("run.jsonl does not match the exact canary contract")
    return run_uid


def _read_run(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise DistillerCanaryError("run.jsonl is missing or symlinked")
    try:
        events = [
            _strict_object(line, "run.jsonl event")
            for line in path.read_bytes().splitlines()
            if line.strip()
        ]
    except OSError as exc:
        raise DistillerCanaryError(f"run.jsonl is unreadable: {exc}") from exc
    return _validate_events(events)


def _spend_nano(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise DistillerCanaryError(f"{field} must be a finite nonnegative number")
    try:
        decimal = Decimal(str(value))
        nano = decimal * Decimal(1_000_000_000)
    except (InvalidOperation, ValueError) as exc:
        raise DistillerCanaryError(f"{field} must be exact USD") from exc
    if (
        not decimal.is_finite()
        or decimal < 0
        or nano != nano.to_integral_value()
        or nano > CANARY_MAX_RESERVED_NANO_USD
    ):
        raise DistillerCanaryError(f"{field} exceeds the exact $0.26 domain")
    return int(nano)


def _read_gateway_spend(run_dir: Path) -> tuple[object, int]:
    path = run_dir / "gateway_spend.json"
    if path.is_symlink() or not path.is_file():
        raise DistillerCanaryError("gateway_spend.json is missing or symlinked")
    try:
        value = _strict_object(path.read_bytes(), "gateway_spend.json")
    except OSError as exc:
        raise DistillerCanaryError(f"gateway_spend.json is unreadable: {exc}") from exc
    if set(value) != {"spent_usd"}:
        raise DistillerCanaryError(
            "gateway_spend.json must contain only spent_usd"
        )
    return value["spent_usd"], _spend_nano(
        value["spent_usd"],
        "gateway_spend.spent_usd",
    )


def _ensure_run(root: Path, run_dir: Path) -> tuple[str, dict, bool, bool]:
    """Plan a fresh run entirely in memory or verify existing run state."""
    if not run_dir.exists():
        run_uid = secrets.token_hex(4)
        _require_fresh_run_uid(run_uid)
        return run_uid, _run_events(run_uid)[1], True, True
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise DistillerCanaryError("governed run path is not a regular directory")
    entries = {path.name for path in run_dir.iterdir()}
    if SCORECARD_NAME in entries:
        raise DistillerCanaryError("this canary run already has a scorecard")
    preparation_pending = PREPARATION_NAME not in entries
    if not entries:
        run_uid = secrets.token_hex(4)
        _require_fresh_run_uid(run_uid)
        return run_uid, _run_events(run_uid)[1], True, True
    allowed = {
        "run.jsonl",
        "gateway_spend.json",
        PREPARATION_NAME,
        READINESS_NAME,
        GATEWAY_RECEIPTS_NAME,
        EXECUTION_LEDGER_NAME,
        f".{GATEWAY_RECEIPTS_NAME}.lock",
    }
    if not {"run.jsonl", "gateway_spend.json"}.issubset(entries) or not (
        entries <= allowed
    ):
        raise DistillerCanaryError(
            "existing run directory has unknown or incomplete state"
        )
    run_uid = _read_run(run_dir / "run.jsonl")
    spend, spend_nano = _read_gateway_spend(run_dir)
    if spend_nano != 0 or Decimal(str(spend)) != Decimal("0"):
        raise DistillerCanaryError(
            "existing canary spend is nonzero; automatic retry is forbidden"
        )
    return run_uid, _run_events(run_uid)[1], preparation_pending, False


def _materialize_run(
    root: Path,
    run_dir: Path,
    *,
    run_uid: str,
    contract: dict,
) -> None:
    """Create claim-bound run files only after authority is consumed."""
    loop_root = root / LOOP_RUNS_RELATIVE_PATH
    if not loop_root.exists():
        loop_root.mkdir(mode=0o700)
    if not run_dir.exists():
        run_dir.mkdir(mode=0o700)
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise DistillerCanaryError("governed run path is not a regular directory")
    if any(run_dir.iterdir()):
        raise DistillerCanaryError(
            "claim-bound run directory changed before materialization"
        )
    created, expected_contract = _run_events(run_uid)
    if contract != expected_contract:
        raise DistillerCanaryError("in-memory canary contract drifted")
    _write_new(
        run_dir / "run.jsonl",
        _canonical_bytes(created) + b"\n" + _canonical_bytes(contract) + b"\n",
    )
    _write_new(
        run_dir / "gateway_spend.json",
        _canonical_bytes({"spent_usd": 0.0}) + b"\n",
    )


def _initialize_or_verify_execution_ledger(
    root: Path,
    policy: DistillerModelPolicy,
    *,
    run_dir: Path,
    preparation_day: str,
    execution_day: str,
    run_uid: str,
    contract_sha256: str,
) -> tuple[Path, dict, str]:
    ledger_root = root / metered_model.LEDGER_RELATIVE_PATH
    ledger_path = daily_spend._ledger_path(
        ledger_root,
        execution_day,
        policy.version,
    )
    receipt_path = run_dir / EXECUTION_LEDGER_NAME
    ledger_exists = ledger_path.exists() or ledger_path.is_symlink()
    receipt_exists = receipt_path.exists() or receipt_path.is_symlink()
    if not ledger_exists:
        if receipt_exists:
            raise DistillerCanaryError(
                "execution-ledger receipt exists without its bound ledger"
            )
        daily_spend.initialize_ledger(
            ledger_root,
            policy_uid=policy.uid,
            policy_version=policy.version,
            daily_ceiling_nano_usd=policy.daily_ceiling_nano_usd,
            day=execution_day,
        )
        if ledger_path.is_symlink() or not ledger_path.is_file():
            raise DistillerCanaryError(
                "execution-day ledger was not atomically materialized"
            )
        try:
            ledger_sha256 = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise DistillerCanaryError(
                f"execution-day ledger is unreadable: {exc}"
            ) from exc
        receipt = metered_model.canary_execution_ledger_receipt(
            run_uid=run_uid,
            contract_sha256=contract_sha256,
            preparation_day=preparation_day,
            execution_day=execution_day,
            initial_ledger_sha256=ledger_sha256,
        )
        _write_new(receipt_path, _canonical_bytes(receipt) + b"\n")
    elif not receipt_exists:
        raise DistillerCanaryError(
            "preexisting execution-day ledger has no exact execution-ledger receipt"
        )
    try:
        receipt = metered_model.verify_canary_execution_ledger(
            run_dir=run_dir,
            ledger_root=ledger_root,
            policy=policy,
            run_uid=run_uid,
            contract_sha256=contract_sha256,
        )
        ledger = daily_spend.read_ledger(
            ledger_root,
            day=execution_day,
            policy_uid=policy.uid,
            policy_version=policy.version,
            daily_ceiling_nano_usd=policy.daily_ceiling_nano_usd,
        )
    except (ValueError, daily_spend.DailySpendError) as exc:
        raise DistillerCanaryError(str(exc)) from exc
    if ledger["reservations"]:
        raise DistillerCanaryError(
            "execution-day ledger is no longer empty; retry is forbidden"
        )
    if receipt["preparation_day"] != preparation_day:
        raise DistillerCanaryError("execution-ledger preparation day drifted")
    if receipt["execution_day"] != execution_day:
        raise DistillerCanaryError("execution-ledger execution day drifted")
    try:
        receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise DistillerCanaryError(
            f"execution-ledger receipt is unreadable: {exc}"
        ) from exc
    return ledger_root, receipt, receipt_sha256


def _load_runner(root: Path):
    source = root / RUNNER_SOURCE
    if _path_has_symlink(source) or source.is_symlink() or not source.is_file():
        raise DistillerCanaryError("registered runner source is missing or symlinked")
    if source.resolve() != root / RUNNER_SOURCE:
        raise DistillerCanaryError("registered runner source path drifted")
    spec = importlib.util.spec_from_file_location(
        "_distiller_metered_canary_runner",
        source,
    )
    if spec is None or spec.loader is None:
        raise DistillerCanaryError("registered runner cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "call_canary", None)):
        raise DistillerCanaryError("registered runner has no call_canary delegate")
    return module


def _parse_response(task: str, text: str) -> None:
    field = f"{task} response"
    normalized = normalize_response_text(text, field)
    response = _strict_object(normalized, field)
    try:
        expected_text, expected = metered_model.canary_expected_response(task)
    except ValueError as exc:
        raise DistillerCanaryError(str(exc)) from exc
    if normalized != expected_text or response != expected:
        raise DistillerCanaryError(
            f"{task} response must equal the sole fixed expected selection"
        )


def _write_scorecard(path: Path, value: dict) -> None:
    _write_new(path, _canonical_bytes(value) + b"\n")


def _read_canonical_file(path: Path, field: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise DistillerCanaryError(f"{field} is missing or symlinked")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DistillerCanaryError(f"{field} is unreadable: {exc}") from exc
    value = _strict_object(raw, field)
    if _canonical_bytes(value) + b"\n" != raw:
        raise DistillerCanaryError(f"{field} is not canonical closed JSON")
    return value


def _preparation_receipt(
    *,
    policy: DistillerModelPolicy,
    run_uid: str,
    contract_sha256: str,
    preparation_day: str,
) -> dict:
    if (
        policy.uid != POLICY_UID
        or policy.version != POLICY_VERSION
        or policy.runner_uid != RUNNER_UID
    ):
        raise DistillerCanaryError("canary preparation policy identity drifted")
    try:
        return metered_model.canary_preparation_receipt(
            run_uid=run_uid,
            runner_uid=policy.runner_uid,
            contract_sha256=contract_sha256,
            preparation_day=preparation_day,
        )
    except ValueError as exc:
        raise DistillerCanaryError(str(exc)) from exc


def _default_sdk_check() -> None:
    try:
        importlib.import_module("anthropic")
    except ImportError as exc:
        raise DistillerCanaryError("anthropic package is not importable") from exc


def _default_gateway_check() -> None:
    try:
        connection = socket.create_connection(("127.0.0.1", 8080), timeout=1.0)
    except OSError as exc:
        raise DistillerCanaryError(
            "local metering gateway is not accepting on 127.0.0.1:8080"
        ) from exc
    connection.close()


def _waiting(run_uid: str | None, error: str) -> dict:
    return {
        "schema_version": 1,
        "mode": "distiller-metered-canary",
        "status": "waiting",
        "phase": "readiness",
        "run_uid": run_uid,
        "error": error,
    }


def _gateway_receipts(
    run_dir: Path,
    *,
    run_uid: str,
    contract_sha256: str,
) -> list[dict]:
    value = _read_canonical_file(
        run_dir / GATEWAY_RECEIPTS_NAME,
        GATEWAY_RECEIPTS_NAME,
    )
    expected = metered_model.empty_canary_gateway_receipts(
        run_uid=run_uid,
        contract_sha256=contract_sha256,
    )
    identity = {key: item for key, item in value.items() if key != "receipts"}
    expected_identity = {
        key: item for key, item in expected.items() if key != "receipts"
    }
    if identity != expected_identity or not isinstance(value.get("receipts"), list):
        raise DistillerCanaryError("exact gateway receipt surface drifted")
    receipts = value["receipts"]
    if len(receipts) > CANARY_MAX_ITERATIONS:
        raise DistillerCanaryError("gateway emitted too many canary receipts")
    expected_fields = {
        "reservation_id",
        "task",
        "model",
        "actual_nano_usd",
        "response_sha256",
        "response_text",
        "service_tier",
        "inference_geo",
    }
    for receipt in receipts:
        if type(receipt) is not dict or set(receipt) != expected_fields:
            raise DistillerCanaryError("gateway receipt schema is not closed")
        response_text = receipt["response_text"]
        response_sha256 = receipt["response_sha256"]
        if (
            not isinstance(response_text, str)
            or not isinstance(response_sha256, str)
            or hashlib.sha256(
                response_text.encode("utf-8", errors="strict")
            ).hexdigest()
            != response_sha256
        ):
            raise DistillerCanaryError("gateway response evidence drifted")
    return receipts


def _empty_scorecard(
    error: str,
    phase: str,
    *,
    preparation_day: str | None = None,
    execution_day: str | None = None,
    execution_ledger: dict | None = None,
    execution_ledger_receipt_sha256: str | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "mode": "distiller-metered-canary",
        "status": "failed",
        "phase": phase,
        "policy": {
            "uid": POLICY_UID,
            "version": POLICY_VERSION,
            "runner_uid": RUNNER_UID,
            "production_enabled": False,
            "canary_admissible": False,
        },
        "run": {
            "uid": None,
            "request_sha256": metered_model.canary_request_hashes(),
            "admission_mode": "canary",
            "segment_classes": ["os"],
            "tasks": list(CANARY_TASKS),
            "max_iterations": CANARY_MAX_ITERATIONS,
            "max_budget_usd": float(CANARY_MAX_BUDGET_USD),
        },
        "receipts": [],
        "reserved_nano_usd": 0,
        "actual_nano_usd": 0,
        "gateway_spend_usd": None,
        "gateway_receipts": [],
        "preparation_day": preparation_day,
        "execution_day": execution_day,
        "execution_ledger": execution_ledger,
        "execution_ledger_receipt_sha256": execution_ledger_receipt_sha256,
        "error": error,
    }


def run_canary(
    run_dir: Path | str,
    *,
    sdk_check=None,
    gateway_check=None,
    monotonic=None,
    environment=None,
    clock=None,
) -> dict:
    """Prepare on first invocation; execute once after gateway readiness."""
    root = _studio_root()
    governed_run = _resolve_run_dir(root, run_dir)
    scorecard_path = governed_run / SCORECARD_NAME
    policy: DistillerModelPolicy | None = None
    run_uid: str | None = None
    ledger_root: Path | None = None
    contract_hash: str | None = None
    preparation_day: str | None = None
    execution_day: str | None = None
    execution_ledger: dict | None = None
    execution_ledger_receipt_sha256: str | None = None
    calls: list[dict] = []
    env = environment if environment is not None else os.environ

    def current_day() -> str:
        return daily_spend.utc_day(clock() if clock is not None else None)

    try:
        policy = resolve_policy(studio_root=root)
        if not policy.canary_admissible:
            detail = "; ".join(policy.canary_disabled_reasons)
            raise DistillerCanaryError(detail or "policy is not canary-admissible")
        if policy.production_enabled:
            raise DistillerCanaryError("production must remain disabled for the canary")
        (
            run_uid,
            contract,
            preparation_pending,
            materialization_pending,
        ) = _ensure_run(root, governed_run)
        _require_fresh_run_uid(run_uid)
        contract_hash = metered_model.canary_contract_sha256(contract)
        ledger_root = root / metered_model.LEDGER_RELATIVE_PATH
        if materialization_pending:
            preparation_day = current_day()
            claim_path = ledger_root / CANARY_CLAIM_NAME
            claim_preexisting = claim_path.exists() or claim_path.is_symlink()
            claim_canary_authority(
                ledger_root,
                policy=policy,
                run_uid=run_uid,
                run_dir=governed_run,
                contract_sha256=contract_hash,
            )
            if claim_preexisting:
                raise DistillerCanaryError(
                    "attempt-7 authority was consumed without a completed "
                    "preparation; automatic retry is forbidden"
                )
            _materialize_run(
                root,
                governed_run,
                run_uid=run_uid,
                contract=contract,
            )
            preparation = _preparation_receipt(
                policy=policy,
                run_uid=run_uid,
                contract_sha256=contract_hash,
                preparation_day=preparation_day,
            )
            _write_new(
                governed_run / PREPARATION_NAME,
                _canonical_bytes(preparation) + b"\n",
            )
            return preparation
        else:
            verify_exact_canary_claim(
                ledger_root,
                policy=policy,
                run_uid=run_uid,
                run_dir=governed_run,
                contract_sha256=contract_hash,
            )
            if preparation_pending:
                raise DistillerCanaryError(
                    "attempt-7 authority was consumed without a completed "
                    "preparation; automatic retry is forbidden"
                )
        preparation_path = governed_run / PREPARATION_NAME
        actual_preparation = _read_canonical_file(
            preparation_path,
            PREPARATION_NAME,
        )
        preparation_day = actual_preparation.get("preparation_day")
        preparation = _preparation_receipt(
            policy=policy,
            run_uid=run_uid,
            contract_sha256=contract_hash,
            preparation_day=preparation_day,
        )
        if actual_preparation != preparation:
            raise DistillerCanaryError("canary preparation receipt drifted")
    except Exception as exc:
        return {
            "schema_version": 1,
            "mode": "distiller-metered-canary",
            "status": "blocked",
            "phase": "preflight",
            "run_uid": run_uid,
            "error": str(exc) or type(exc).__name__,
        }

    expected_readiness = metered_model.canary_readiness_receipt(
        run_uid=run_uid,
        runner_uid=policy.runner_uid,
        contract_sha256=contract_hash,
    )
    try:
        readiness = _read_canonical_file(
            governed_run / READINESS_NAME,
            READINESS_NAME,
        )
        if readiness != expected_readiness:
            raise DistillerCanaryError("canary readiness receipt drifted")
        if env.get("REAL_ANTHROPIC_API_KEY"):
            raise DistillerCanaryError(
                "caller environment may not contain REAL_ANTHROPIC_API_KEY"
            )
        (sdk_check or _default_sdk_check)()
        (gateway_check or _default_gateway_check)()
        if _gateway_receipts(
            governed_run,
            run_uid=run_uid,
            contract_sha256=contract_hash,
        ):
            raise DistillerCanaryError(
                "gateway receipt surface is not empty before execution"
            )
    except Exception as exc:
        return _waiting(run_uid, str(exc) or type(exc).__name__)

    try:
        runner = _load_runner(root)
    except Exception as exc:
        return _waiting(run_uid, str(exc) or type(exc).__name__)

    try:
        existing = metered_model.canary_ledger_records(
            ledger_root,
            policy=policy,
            run_uid=run_uid,
        )
        if existing:
            execution_ledger = metered_model.verify_canary_execution_ledger(
                run_dir=governed_run,
                ledger_root=ledger_root,
                policy=policy,
                run_uid=run_uid,
                contract_sha256=contract_hash,
            )
            execution_day = execution_ledger["execution_day"]
            receipt_path = governed_run / EXECUTION_LEDGER_NAME
            execution_ledger_receipt_sha256 = hashlib.sha256(
                receipt_path.read_bytes()
            ).hexdigest()
            scorecard = _empty_scorecard(
                "this canary already has a reservation; retry is forbidden",
                "preflight",
                preparation_day=preparation_day,
                execution_day=execution_day,
                execution_ledger=execution_ledger,
                execution_ledger_receipt_sha256=(
                    execution_ledger_receipt_sha256
                ),
            )
            scorecard["run"]["uid"] = run_uid
            scorecard["run"]["contract_sha256"] = contract_hash
            scorecard["reserved_nano_usd"] = sum(
                record["worst_case_nano_usd"]
                for _reservation_id, record in existing.values()
            )
            scorecard["actual_nano_usd"] = sum(
                record["actual_nano_usd"] or 0
                for _reservation_id, record in existing.values()
            )
            _write_scorecard(scorecard_path, scorecard)
            return scorecard

        execution_day = current_day()
        execution_path = daily_spend._ledger_path(
            ledger_root,
            execution_day,
            policy.version,
        )
        execution_receipt_path = governed_run / EXECUTION_LEDGER_NAME
        if (
            execution_path.exists()
            or execution_path.is_symlink()
            or execution_receipt_path.exists()
            or execution_receipt_path.is_symlink()
        ):
            (
                _verified_root,
                execution_ledger,
                execution_ledger_receipt_sha256,
            ) = _initialize_or_verify_execution_ledger(
                root,
                policy,
                run_dir=governed_run,
                preparation_day=preparation_day,
                execution_day=execution_day,
                run_uid=run_uid,
                contract_sha256=contract_hash,
            )

        with locked_canary_claim(
            ledger_root,
            policy=policy,
            run_uid=run_uid,
            run_dir=governed_run,
            contract_sha256=contract_hash,
        ):
            raced = metered_model.canary_ledger_records(
                ledger_root,
                policy=policy,
                run_uid=run_uid,
            )
            if raced:
                raise DistillerCanaryError(
                    "canary reservation appeared during execution-ledger "
                    "initialization; retry is forbidden"
                )
            if current_day() != execution_day:
                raise DistillerCanaryError(
                    "UTC day rolled over before execution-ledger initialization"
                )
            (
                ledger_root,
                execution_ledger,
                execution_ledger_receipt_sha256,
            ) = _initialize_or_verify_execution_ledger(
                root,
                policy,
                run_dir=governed_run,
                preparation_day=preparation_day,
                execution_day=execution_day,
                run_uid=run_uid,
                contract_sha256=contract_hash,
            )
    except Exception as exc:
        return {
            "schema_version": 1,
            "mode": "distiller-metered-canary",
            "status": "blocked",
            "phase": "execution-ledger",
            "run_uid": run_uid,
            "preparation_day": preparation_day,
            "execution_day": execution_day,
            "error": str(exc) or type(exc).__name__,
        }

    binding = metered_model.RunBinding(
        run_uid=run_uid,
        gateway_url=metered_model.GATEWAY_URL,
        virtual_key=f"sk-virtual-tropo-{run_uid}",
        studio_root=root,
        run_dir=governed_run,
    )
    timer = monotonic or time.monotonic
    started_at = timer()
    try:
        for task in CANARY_TASKS:
            if current_day() != execution_day:
                raise DistillerCanaryError(
                    "UTC day rolled over before the next canary reservation"
                )
            if timer() - started_at > CANARY_MAX_WALL_CLOCK_MIN * 60:
                raise DistillerCanaryError("five-minute canary deadline exceeded")
            entry = {
                "task": task,
                "status": "failed",
                "reservation_id": None,
                "reserved_nano_usd": None,
                "actual_nano_usd": None,
                "reservation_status": None,
                "worst_case_retained": False,
                "response_sha256": None,
                "response_text": None,
                "response_service_tier": None,
                "response_inference_geo": None,
                "error": None,
            }
            try:
                result = runner.call_canary(task, run_binding=binding)
                if isinstance(result, metered_model.MeteredModelResult):
                    entry["response_text"] = result.text
                    entry["response_sha256"] = hashlib.sha256(
                        result.text.encode("utf-8", errors="strict")
                    ).hexdigest()
                    entry["response_service_tier"] = result.usage["service_tier"]
                    entry["response_inference_geo"] = result.usage["inference_geo"]
                    _parse_response(task, result.text)
                    entry["status"] = "pass"
                elif isinstance(result, metered_model.ModelRefusal):
                    entry["reservation_id"] = result.reservation_id
                    entry["worst_case_retained"] = result.worst_case_retained
                    entry["error"] = f"{result.code}: {result.message}"
                else:
                    entry["error"] = (
                        f"{task} runner returned an unknown result type"
                    )
            except Exception as exc:
                entry["error"] = str(exc) or type(exc).__name__
            calls.append(entry)
            if timer() - started_at > CANARY_MAX_WALL_CLOCK_MIN * 60:
                entry["status"] = "failed"
                entry["error"] = "five-minute canary deadline exceeded"
            if entry["status"] != "pass":
                break

        records = metered_model.canary_ledger_records(
            ledger_root,
            policy=policy,
            run_uid=run_uid,
        )
        receipts = {}
        for task, (reservation_id, record) in records.items():
            receipts[task] = {
                "reservation_id": reservation_id,
                "reserved_nano_usd": record["worst_case_nano_usd"],
                "actual_nano_usd": (
                    record["actual_nano_usd"]
                    if record["status"] == "reconciled"
                    else None
                ),
                "reservation_status": record["status"],
                "worst_case_retained": record["status"] != "reconciled",
            }
        for entry in calls:
            if entry["task"] in receipts:
                entry.update(receipts[entry["task"]])
        if not records:
            error = "; ".join(
                entry["error"] for entry in calls if entry["error"]
            ) or "canary refused before reservation"
            raise DistillerCanaryError(error)

        reserved_total = sum(
            receipt["reserved_nano_usd"] for receipt in receipts.values()
        )
        actual_total = sum(
            receipt["actual_nano_usd"] or 0 for receipt in receipts.values()
        )
        if reserved_total > CANARY_MAX_RESERVED_NANO_USD:
            raise DistillerCanaryError("combined reservations exceed $0.26")
        exact_gateway_receipts = _gateway_receipts(
            governed_run,
            run_uid=run_uid,
            contract_sha256=contract_hash,
        )
        expected_gateway = [
            {
                "reservation_id": entry["reservation_id"],
                "task": entry["task"],
                "model": policy.route(entry["task"]).model,
                "actual_nano_usd": entry["actual_nano_usd"],
                "response_sha256": entry["response_sha256"],
                "response_text": entry["response_text"],
                "service_tier": entry["response_service_tier"],
                "inference_geo": entry["response_inference_geo"],
            }
            for entry in calls
            if entry["status"] == "pass"
        ]
        gateway_spend, _legacy_gateway_nano = _read_gateway_spend(governed_run)
        passed = (
            [entry["task"] for entry in calls] == list(CANARY_TASKS)
            and all(entry["status"] == "pass" for entry in calls)
            and set(receipts) == set(CANARY_TASKS)
            and all(
                receipt["reservation_status"] == "reconciled"
                for receipt in receipts.values()
            )
            and exact_gateway_receipts == expected_gateway
            and sum(
                receipt["actual_nano_usd"]
                for receipt in exact_gateway_receipts
            )
            == actual_total
        )
        if not passed:
            errors = [entry["error"] for entry in calls if entry["error"]]
            raise DistillerCanaryError(
                "; ".join(errors)
                or "canary responses, ledger, or exact gateway receipts did not close"
            )
        scorecard = {
            "schema_version": 1,
            "mode": "distiller-metered-canary",
            "status": "pass",
            "phase": "score",
            "policy": {
                "uid": policy.uid,
                "version": policy.version,
                "runner_uid": policy.runner_uid,
                "production_enabled": policy.production_enabled,
                "canary_admissible": policy.canary_admissible,
            },
            "run": {
                "uid": run_uid,
                "contract_sha256": contract_hash,
                "request_sha256": metered_model.canary_request_hashes(),
                "admission_mode": "canary",
                "segment_classes": ["os"],
                "tasks": list(CANARY_TASKS),
                "max_iterations": CANARY_MAX_ITERATIONS,
                "max_budget_usd": float(CANARY_MAX_BUDGET_USD),
            },
            "receipts": calls,
            "gateway_receipts": exact_gateway_receipts,
            "reserved_nano_usd": reserved_total,
            "actual_nano_usd": actual_total,
            "gateway_spend_usd": float(gateway_spend),
            "preparation_day": preparation_day,
            "execution_day": execution_day,
            "execution_ledger": execution_ledger,
            "execution_ledger_receipt_sha256": (
                execution_ledger_receipt_sha256
            ),
            "error": None,
        }
    except Exception as exc:
        scorecard = _empty_scorecard(
            str(exc) or type(exc).__name__,
            "calls",
            preparation_day=preparation_day,
            execution_day=execution_day,
            execution_ledger=execution_ledger,
            execution_ledger_receipt_sha256=(
                execution_ledger_receipt_sha256
            ),
        )
        scorecard["receipts"] = calls
        scorecard["run"]["uid"] = run_uid
        scorecard["run"]["contract_sha256"] = contract_hash
        scorecard["policy"] = {
            "uid": policy.uid,
            "version": policy.version,
            "runner_uid": policy.runner_uid,
            "production_enabled": policy.production_enabled,
            "canary_admissible": policy.canary_admissible,
        }
        try:
            records = metered_model.canary_ledger_records(
                ledger_root,
                policy=policy,
                run_uid=run_uid,
            )
            scorecard["reserved_nano_usd"] = sum(
                record["worst_case_nano_usd"]
                for _reservation_id, record in records.values()
            )
            scorecard["actual_nano_usd"] = sum(
                record["actual_nano_usd"] or 0
                for _reservation_id, record in records.values()
            )
            scorecard["gateway_receipts"] = _gateway_receipts(
                governed_run,
                run_uid=run_uid,
                contract_sha256=contract_hash,
            )
        except Exception:
            pass
    if not scorecard_path.exists():
        _write_scorecard(scorecard_path, scorecard)
    return scorecard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the fixed OS-only Distiller metered canary"
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="direct governed child of vault/loop-runs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scorecard = run_canary(Path(args.run_dir))
    print(json.dumps(scorecard, sort_keys=True, separators=(",", ":")))
    if scorecard["status"] == "pass":
        return 0
    if scorecard["status"] == "prepared":
        return 3
    if scorecard["status"] == "waiting":
        return 4
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
