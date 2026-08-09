"""Fail-closed Distiller model gate with exact policy and spend binding."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional

from lib import daily_spend, llm
from lib.distiller_model_policy import (
    CANARY_MAX_CALLS,
    CANARY_MAX_RESERVED_NANO_USD,
    POLICY_UID,
    POLICY_VERSION,
    DistillerModelPolicy,
    PolicyError,
    locked_canary_claim,
    resolve_policy,
)
from lib.loop_metering import (
    MeteringContractError,
    price_locked_usage_nano_usd,
    worst_case_request_cost_nano_usd,
)


GATEWAY_URL = "http://127.0.0.1:8080"
LEDGER_RELATIVE_PATH = Path("vault/loop-runs/.model-spend")
PRODUCTION_ADMISSION = "production"
CANARY_ADMISSION = "canary"
CANARY_TASKS = ("parse-query", "distill")
CANARY_MAX_WALL_CLOCK_MIN = 5
CANARY_MAX_BUDGET_USD = 0.26
CANARY_PREPARATION_NAME = "distiller-metered-canary-preparation.json"
CANARY_READINESS_NAME = "distiller-metered-canary-readiness.json"
CANARY_GATEWAY_RECEIPTS_NAME = "distiller-metered-canary-gateway-receipts.json"
CANARY_EXECUTION_LEDGER_NAME = "distiller-metered-canary-execution-ledger.json"
CANARY_SCORECARD_NAME = "distiller-metered-canary-scorecard.json"
_UID_RE = re.compile(r"^[0-9a-f]{8}$")
_VERSIONED_DAY_FILE_RE = re.compile(
    r"^(?P<day>\d{4}-\d{2}-\d{2})@"
    r"(?P<version>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))\.json$"
)

_CANARY_REQUESTS = {
    "parse-query": {
        "messages": [
            {
                "role": "user",
                "content": (
                    '{"candidates":[{"context":"Authoritative OS loop policy for '
                    "the two Distiller model edges; production remains closed and "
                    'attempt-4 authority is separate.","title":"Distiller Cut 4G — '
                    'Metered Model Runtime Policy","uid":"0c938a95"}],"intent":'
                    '"Select the authoritative Distiller metered-model policy from '
                    'this closed OS candidate set."}'
                ),
            }
        ],
        "system": (
            'Return exactly {"uids":["0c938a95"]}. Raw JSON only. Do not use '
            "Markdown fences. The first character must be { and the final "
            "character must be }. Do not include prose."
        ),
        "max_tokens": 128,
    },
    "distill": {
        "messages": [
            {
                "role": "user",
                "content": (
                    '{"candidates":[{"source_uid":"0c938a95",'
                    '"span_anchor":"frontmatter:uid=0c938a95",'
                    '"text":"Distiller policy 0c938a95 keeps production closed '
                    "and authorizes only model-capability-shaped OS canary "
                    'attempt 4."}]}'
                ),
            }
        ],
        "system": (
            'Return exactly one JSON object {"selections":[{"source_uid":'
            '"0c938a95","span_anchor":"frontmatter:uid=0c938a95",'
            '"reorder_note":null}]}. Raw JSON only. Do not use Markdown fences. '
            "The first character must be { and the final character must be }. "
            "Do not include prose."
        ),
        "max_tokens": 256,
    },
}
_CANARY_EXPECTED_RESPONSE_TEXT = {
    "parse-query": '{"uids":["0c938a95"]}',
    "distill": (
        '{"selections":[{"source_uid":"0c938a95",'
        '"span_anchor":"frontmatter:uid=0c938a95","reorder_note":null}]}'
    ),
}
_CANARY_EXPECTED_RESPONSES = {
    "parse-query": {"uids": [POLICY_UID]},
    "distill": {
        "selections": [
            {
                "source_uid": POLICY_UID,
                "span_anchor": f"frontmatter:uid={POLICY_UID}",
                "reorder_note": None,
            }
        ]
    },
}


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canary_request(task: str) -> tuple[list[dict], str, int]:
    """Return a detached copy of one code-locked canary request."""
    try:
        value = _CANARY_REQUESTS[task]
    except KeyError as exc:
        raise ValueError(f"unknown fixed canary task {task!r}") from exc
    messages = json.loads(_canonical_json_bytes(value["messages"]))
    return messages, str(value["system"]), int(value["max_tokens"])


def canary_expected_response(task: str) -> tuple[str, dict]:
    try:
        text = _CANARY_EXPECTED_RESPONSE_TEXT[task]
        value = _CANARY_EXPECTED_RESPONSES[task]
    except KeyError as exc:
        raise ValueError(f"unknown fixed canary task {task!r}") from exc
    return text, json.loads(_canonical_json_bytes(value))


def canary_request_projection(task: str) -> dict:
    messages, system, max_tokens = canary_request(task)
    return json.loads(
        llm.serialize_locked_request(
            task,
            messages,
            max_tokens=max_tokens,
            system=system,
        ).decode("utf-8")
    )


def canary_request_sha256(task: str) -> str:
    return hashlib.sha256(_canonical_json_bytes(canary_request_projection(task))).hexdigest()


def canary_request_hashes() -> dict[str, str]:
    return {task: canary_request_sha256(task) for task in CANARY_TASKS}


def canary_run_events(run_uid: str, runner_uid: str = "6389dcd4") -> tuple[dict, dict]:
    if not isinstance(run_uid, str) or not _UID_RE.fullmatch(run_uid):
        raise ValueError("canary run_uid must be 8 lowercase hex")
    if runner_uid != "6389dcd4":
        raise ValueError("canary runner UID drifted")
    return (
        {
            "event": "run_created",
            "run_uid": run_uid,
            "loop": POLICY_UID,
            "loop_version": POLICY_VERSION,
        },
        {
            "event": "loop_contract_locked",
            "loop": POLICY_UID,
            "loop_version": POLICY_VERSION,
            "policy": {"kind": "agentic-tool", "ref": runner_uid},
            "admission_mode": CANARY_ADMISSION,
            "segment_classes": ["os"],
            "tasks": list(CANARY_TASKS),
            "request_sha256": canary_request_hashes(),
            "brakes": {
                "max_iterations": CANARY_MAX_CALLS,
                "max_budget_usd": CANARY_MAX_BUDGET_USD,
                "max_wall_clock_min": CANARY_MAX_WALL_CLOCK_MIN,
            },
        },
    )


def canary_contract_sha256(contract: dict) -> str:
    return hashlib.sha256(_canonical_json_bytes(contract)).hexdigest()


def canary_readiness_receipt(
    *,
    run_uid: str,
    runner_uid: str,
    contract_sha256: str,
) -> dict:
    if runner_uid != "6389dcd4":
        raise ValueError("canary readiness runner drifted")
    return {
        "schema_version": 1,
        "status": "ready",
        "policy_uid": POLICY_UID,
        "policy_version": POLICY_VERSION,
        "runner_uid": runner_uid,
        "run_uid": run_uid,
        "contract_sha256": contract_sha256,
        "request_sha256": canary_request_hashes(),
        "admission_mode": CANARY_ADMISSION,
        "gateway_url": GATEWAY_URL,
        "gateway_spend_nano_usd": 0,
        "real_key_present": True,
    }


def empty_canary_gateway_receipts(
    *,
    run_uid: str,
    contract_sha256: str,
) -> dict:
    return {
        "schema_version": 1,
        "policy_uid": POLICY_UID,
        "policy_version": POLICY_VERSION,
        "run_uid": run_uid,
        "contract_sha256": contract_sha256,
        "receipts": [],
    }


def canary_preparation_receipt(
    *,
    run_uid: str,
    runner_uid: str,
    contract_sha256: str,
    preparation_day: str,
) -> dict:
    if not isinstance(run_uid, str) or not _UID_RE.fullmatch(run_uid):
        raise ValueError("preparation run_uid must be 8 lowercase hex")
    if runner_uid != "6389dcd4":
        raise ValueError("preparation runner UID drifted")
    if (
        not isinstance(contract_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", contract_sha256) is None
    ):
        raise ValueError("preparation contract_sha256 must be lowercase SHA-256")
    try:
        prepared = daily_spend._validate_day(preparation_day)
    except daily_spend.DailySpendError as exc:
        raise ValueError(str(exc)) from exc
    return {
        "schema_version": 1,
        "status": "prepared",
        "policy_uid": POLICY_UID,
        "policy_version": POLICY_VERSION,
        "runner_uid": runner_uid,
        "run_uid": run_uid,
        "contract_sha256": contract_sha256,
        "request_sha256": canary_request_hashes(),
        "admission_mode": CANARY_ADMISSION,
        "segment_classes": ["os"],
        "tasks": list(CANARY_TASKS),
        "max_iterations": CANARY_MAX_CALLS,
        "max_reserved_nano_usd": CANARY_MAX_RESERVED_NANO_USD,
        "preparation_day": prepared,
        "execution_ledger_required": True,
    }


def canary_execution_ledger_receipt(
    *,
    run_uid: str,
    contract_sha256: str,
    preparation_day: str,
    execution_day: str,
    initial_ledger_sha256: str,
) -> dict:
    if not isinstance(run_uid, str) or not _UID_RE.fullmatch(run_uid):
        raise ValueError("execution-ledger run_uid must be 8 lowercase hex")
    if (
        not isinstance(contract_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", contract_sha256) is None
    ):
        raise ValueError("execution-ledger contract_sha256 must be lowercase SHA-256")
    if (
        not isinstance(initial_ledger_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", initial_ledger_sha256) is None
    ):
        raise ValueError(
            "execution-ledger initial_ledger_sha256 must be lowercase SHA-256"
        )
    try:
        prepared = daily_spend._validate_day(preparation_day)
        executed = daily_spend._validate_day(execution_day)
    except daily_spend.DailySpendError as exc:
        raise ValueError(str(exc)) from exc
    ledger_relative_path = (
        LEDGER_RELATIVE_PATH / f"{executed}@{POLICY_VERSION}.json"
    ).as_posix()
    return {
        "schema_version": 1,
        "status": "initialized",
        "policy_uid": POLICY_UID,
        "policy_version": POLICY_VERSION,
        "run_uid": run_uid,
        "contract_sha256": contract_sha256,
        "preparation_day": prepared,
        "execution_day": executed,
        "ledger_relative_path": ledger_relative_path,
        "initial_ledger_sha256": initial_ledger_sha256,
    }


def validate_canary_request_body(task: str, value: object) -> str:
    """Require the gateway request to equal the code-locked projection."""
    llm.validate_locked_request_body(task, value)
    actual = hashlib.sha256(_canonical_json_bytes(value)).hexdigest()
    expected = canary_request_sha256(task)
    if actual != expected or value != canary_request_projection(task):
        raise ValueError("canary request body does not match the fixed fixture")
    return actual


def validate_locked_request_body(task: str, value: object) -> bytes:
    """Validate every production/canary Distiller wire body."""
    return llm.validate_locked_request_body(task, value)


@dataclass(frozen=True)
class RunBinding:
    run_uid: str
    gateway_url: str
    virtual_key: str
    studio_root: Path
    run_dir: Path | None = None


@dataclass(frozen=True)
class ModelReceipt:
    reservation_id: str
    utc_day: str
    policy_uid: str
    policy_version: str
    run_uid: str
    task: str
    model: str
    segment_classes: tuple[str, ...]
    reserved_nano_usd: int
    actual_nano_usd: int
    admission_mode: str = PRODUCTION_ADMISSION


@dataclass(frozen=True)
class MeteredModelResult:
    text: str
    model: str
    usage: dict[str, object]
    receipt: ModelReceipt


@dataclass(frozen=True)
class ModelRefusal:
    code: str
    message: str
    reservation_id: Optional[str] = None
    worst_case_retained: bool = False


def _refusal(
    code: str,
    message: str,
    *,
    reservation_id: str | None = None,
    retained: bool = False,
) -> ModelRefusal:
    return ModelRefusal(code, message, reservation_id, retained)


def _segments(value: object) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or not value:
        raise ValueError("segment_classes must be a non-empty tuple/list")
    if any(item not in {"os", "team", "private"} for item in value):
        raise ValueError("segment_classes contain an unknown class")
    return tuple(sorted(set(value)))


def _path_has_symlink(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _binding(
    value: object,
    environment: Mapping[str, str],
) -> tuple[RunBinding, Path]:
    if not isinstance(value, RunBinding):
        raise ValueError("run_binding must be a RunBinding")
    if not isinstance(value.run_uid, str) or not _UID_RE.fullmatch(value.run_uid):
        raise ValueError("run_binding.run_uid must be 8 lowercase hex")
    if value.gateway_url != GATEWAY_URL:
        raise ValueError("run_binding.gateway_url must use the exact local gateway")
    if value.virtual_key != f"sk-virtual-tropo-{value.run_uid}":
        raise ValueError("run_binding.virtual_key is not bound to run_uid")
    if environment.get("REAL_ANTHROPIC_API_KEY"):
        raise ValueError("caller environment may not contain the real provider key")
    if not isinstance(value.studio_root, (str, os.PathLike)):
        raise ValueError("run_binding.studio_root must be a filesystem path")
    studio_root = Path(value.studio_root)
    if not studio_root.is_absolute():
        raise ValueError("run_binding.studio_root must be absolute")
    if _path_has_symlink(studio_root):
        raise ValueError("run_binding.studio_root has a symlinked path component")
    if not studio_root.is_dir():
        raise ValueError("run_binding.studio_root must be an existing directory")
    try:
        resolved_studio = studio_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"run_binding.studio_root is not canonical: {exc}") from exc
    if resolved_studio != studio_root:
        raise ValueError("run_binding.studio_root must be a canonical absolute path")

    marker = studio_root / ".tropo"
    if marker.is_symlink() or not marker.is_dir():
        raise ValueError(
            "run_binding.studio_root must contain a regular non-symlink .tropo"
        )

    ledger_root = studio_root / LEDGER_RELATIVE_PATH
    if _path_has_symlink(ledger_root):
        raise ValueError("canonical ledger path has a symlinked component")
    if not ledger_root.is_dir():
        raise ValueError("canonical Studio ledger folder is missing")
    try:
        resolved_ledger = ledger_root.resolve(strict=True)
        resolved_ledger.relative_to(resolved_studio)
    except (OSError, ValueError) as exc:
        raise ValueError("canonical ledger path escapes the Studio root") from exc
    if resolved_ledger != resolved_studio / LEDGER_RELATIVE_PATH:
        raise ValueError("canonical ledger path is not the exact Studio ledger folder")
    return value, ledger_root


def _canary_run_binding(
    binding: RunBinding,
    policy: DistillerModelPolicy,
) -> tuple[Path, str]:
    if not isinstance(binding.run_dir, (str, os.PathLike)):
        raise ValueError("canary run_binding.run_dir must be a filesystem path")
    run_dir = Path(binding.run_dir)
    expected_parent = Path(binding.studio_root) / "vault" / "loop-runs"
    if (
        not run_dir.is_absolute()
        or run_dir.parent != expected_parent
        or _path_has_symlink(run_dir)
        or run_dir.is_symlink()
        or not run_dir.is_dir()
    ):
        raise ValueError(
            "canary run_binding.run_dir must be one canonical governed run directory"
        )
    try:
        if run_dir.resolve(strict=True) != run_dir:
            raise ValueError("canary run_binding.run_dir is not canonical")
        raw_lines = (run_dir / "run.jsonl").read_bytes().splitlines()
        events = [
            json.loads(
                line.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
            for line in raw_lines
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"canary run contract is unreadable: {exc}") from exc
    expected = list(canary_run_events(binding.run_uid, policy.runner_uid))
    if events != expected:
        raise ValueError("canary run contract does not equal the code-derived contract")
    contract_hash = canary_contract_sha256(events[1])
    return run_dir, contract_hash


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError(f"non-finite JSON constant {value!r}")


def canary_ledger_records(
    ledger_root: Path,
    *,
    policy: DistillerModelPolicy,
    run_uid: str,
) -> dict[str, tuple[str, dict]]:
    """Return this run's records; reject any foreign current-version authority."""
    result: dict[str, tuple[str, dict]] = {}
    for path in sorted(ledger_root.iterdir()):
        match = _VERSIONED_DAY_FILE_RE.fullmatch(path.name)
        if match is None or match.group("version") != policy.version:
            continue
        day = match.group("day")
        if path != daily_spend._ledger_path(
            ledger_root,
            day,
            policy.version,
        ):
            raise ValueError("current-version canary ledger path drifted")
        ledger = daily_spend.read_ledger(
            ledger_root,
            day=day,
            policy_uid=policy.uid,
            policy_version=policy.version,
            daily_ceiling_nano_usd=policy.daily_ceiling_nano_usd,
        )
        for reservation_id, record in ledger["reservations"].items():
            if record["run_uid"] != run_uid:
                raise ValueError(
                    "current-version canary ledger contains a foreign run"
                )
            task = record["task"]
            if task not in CANARY_TASKS or task in result:
                raise ValueError("canary ledger has duplicate or unknown task state")
            result[task] = (reservation_id, dict(record))
    return result


def _read_canary_json(path: Path, field: str) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{field} is missing or symlinked")
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{field} is malformed: {exc}") from exc
    if type(value) is not dict or _canonical_json_bytes(value) + b"\n" != raw:
        raise ValueError(f"{field} is not canonical closed JSON")
    return value, raw


def verify_canary_execution_ledger(
    *,
    run_dir: Path,
    ledger_root: Path,
    policy: DistillerModelPolicy,
    run_uid: str,
    contract_sha256: str,
) -> dict:
    """Verify the immutable receipt against the execution ledger's initial state."""
    preparation, _preparation_raw = _read_canary_json(
        run_dir / CANARY_PREPARATION_NAME,
        CANARY_PREPARATION_NAME,
    )
    preparation_day = preparation.get("preparation_day")
    try:
        expected_preparation = canary_preparation_receipt(
            run_uid=run_uid,
            runner_uid=policy.runner_uid,
            contract_sha256=contract_sha256,
            preparation_day=preparation_day,
        )
    except ValueError as exc:
        raise ValueError(f"canary preparation identity drifted: {exc}") from exc
    if preparation != expected_preparation:
        raise ValueError("canary preparation identity drifted")
    receipt, _receipt_raw = _read_canary_json(
        run_dir / CANARY_EXECUTION_LEDGER_NAME,
        CANARY_EXECUTION_LEDGER_NAME,
    )
    execution_day = receipt.get("execution_day")
    try:
        expected_path = daily_spend._ledger_path(
            ledger_root,
            execution_day,
            policy.version,
        )
        ledger = daily_spend.read_ledger(
            ledger_root,
            day=execution_day,
            policy_uid=policy.uid,
            policy_version=policy.version,
            daily_ceiling_nano_usd=policy.daily_ceiling_nano_usd,
        )
    except daily_spend.DailySpendError as exc:
        raise ValueError(f"execution ledger is invalid: {exc}") from exc
    if ledger["poisoned"]:
        raise ValueError("execution ledger is poisoned")
    if any(record["run_uid"] != run_uid for record in ledger["reservations"].values()):
        raise ValueError("execution ledger contains a foreign run")
    initial = dict(ledger)
    initial["actual_total_nano_usd"] = 0
    initial["poisoned"] = False
    initial["poison_reason"] = None
    initial["reservations"] = {}
    initial["checksum"] = daily_spend._checksum(initial)
    initial_sha256 = hashlib.sha256(
        _canonical_json_bytes(initial) + b"\n"
    ).hexdigest()
    expected = canary_execution_ledger_receipt(
        run_uid=run_uid,
        contract_sha256=contract_sha256,
        preparation_day=preparation_day,
        execution_day=execution_day,
        initial_ledger_sha256=initial_sha256,
    )
    studio_root = ledger_root.parents[2]
    if (
        receipt != expected
        or expected_path != studio_root / receipt["ledger_relative_path"]
    ):
        raise ValueError("execution-ledger receipt identity or hash drifted")
    return dict(receipt)


def _now(clock: Callable[[], datetime] | None) -> datetime:
    value = clock() if clock is not None else datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value


def _call(
    task: str,
    messages: list[dict],
    *,
    admission_mode: str,
    segment_classes,
    run_binding,
    max_tokens: int,
    system: str | None = None,
    provider_call=None,
    policy_resolver=None,
    clock: Callable[[], datetime] | None = None,
    reservation_id_factory: Callable[[], str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> MeteredModelResult | ModelRefusal:
    """Shared reserve/call/reconcile implementation for both admission modes."""
    if admission_mode not in {PRODUCTION_ADMISSION, CANARY_ADMISSION}:
        return _refusal("ADMISSION_REFUSED", "unknown admission mode")
    try:
        canonical_segments = _segments(segment_classes)
    except ValueError as exc:
        return _refusal("INVALID_SEGMENT", str(exc))

    resolver = policy_resolver or resolve_policy
    try:
        policy = resolver()
    except Exception as exc:
        return _refusal("POLICY_REFUSED", str(exc) or type(exc).__name__)
    if not isinstance(policy, DistillerModelPolicy):
        return _refusal("POLICY_REFUSED", "policy resolver returned the wrong type")
    try:
        route = policy.route(task)
    except PolicyError as exc:
        return _refusal("UNKNOWN_TASK", str(exc))
    if admission_mode == PRODUCTION_ADMISSION:
        if not policy.production_enabled:
            detail = "; ".join(policy.disabled_reasons) or "production is disabled"
            return _refusal("POLICY_DISABLED", detail)
        denied = [
            segment
            for segment in canonical_segments
            if policy.segment_egress.get(segment) != "auto"
        ]
        if denied or not policy.egress_approved:
            return _refusal(
                "CONSENT_DENIED",
                f"segment egress is not auto-approved for {denied or canonical_segments}",
            )
    else:
        if canonical_segments != ("os",):
            return _refusal(
                "CANARY_SCOPE_REFUSED",
                "canary admission is hard-coded to the OS segment",
            )
        if not policy.canary_admissible:
            detail = (
                "; ".join(policy.canary_disabled_reasons)
                or "canary admission is disabled"
            )
            return _refusal("CANARY_DISABLED", detail)
    if canonical_segments != ("os",):
        return _refusal(
            "GEO_SCOPE_REFUSED",
            "bounded response geography is hard-coded to the OS segment",
        )

    env = environment if environment is not None else os.environ
    canary_run_dir: Path | None = None
    canary_contract_hash: str | None = None
    canary_execution_receipt: dict | None = None
    try:
        binding, ledger_root = _binding(run_binding, env)
        if admission_mode == CANARY_ADMISSION:
            canary_run_dir, canary_contract_hash = _canary_run_binding(
                binding,
                policy,
            )
            canary_execution_receipt = verify_canary_execution_ledger(
                run_dir=canary_run_dir,
                ledger_root=ledger_root,
                policy=policy,
                run_uid=binding.run_uid,
                contract_sha256=canary_contract_hash,
            )
        request_bytes = llm.serialize_locked_request(
            task,
            messages,
            max_tokens=max_tokens,
            system=system,
        )
        worst_case = worst_case_request_cost_nano_usd(
            route.model,
            request_bytes=len(request_bytes),
            max_tokens=max_tokens,
            cache_mode="none",
        )
    except (ValueError, MeteringContractError) as exc:
        return _refusal("PREFLIGHT_REFUSED", str(exc))
    if worst_case > route.per_call_ceiling_nano_usd:
        return _refusal(
            "PER_CALL_LIMIT",
            "exact worst-case request cost exceeds the locked per-call ceiling",
        )

    try:
        day = daily_spend.utc_day(_now(clock))
        if (
            admission_mode == CANARY_ADMISSION
            and (
                canary_execution_receipt is None
                or canary_execution_receipt["execution_day"] != day
            )
        ):
            raise ValueError("canary execution day rolled over before reservation")
        reservation_id = (
            reservation_id_factory()
            if reservation_id_factory is not None
            else secrets.token_hex(4)
        )

        def reserve() -> None:
            daily_spend.reserve(
                ledger_root,
                day=day,
                policy_uid=policy.uid,
                policy_version=policy.version,
                daily_ceiling_nano_usd=policy.daily_ceiling_nano_usd,
                reservation_id=reservation_id,
                run_uid=binding.run_uid,
                task=task,
                model=route.model,
                segment_classes=canonical_segments,
                worst_case_nano_usd=worst_case,
                monthly_ceiling_nano_usd=policy.monthly_ceiling_nano_usd,
            )

        if admission_mode == CANARY_ADMISSION:
            if canary_run_dir is None or canary_contract_hash is None:
                raise ValueError("canary run binding was not resolved")
            with locked_canary_claim(
                ledger_root,
                policy=policy,
                run_uid=binding.run_uid,
                run_dir=canary_run_dir,
                contract_sha256=canary_contract_hash,
            ):
                records = canary_ledger_records(
                    ledger_root,
                    policy=policy,
                    run_uid=binding.run_uid,
                )
                if task in records:
                    raise ValueError(
                        "canary permits exactly one reservation for each locked task"
                    )
                if len(records) >= CANARY_MAX_CALLS:
                    raise ValueError("canary already has two reservations")
                expected_task = CANARY_TASKS[len(records)]
                if task != expected_task:
                    raise ValueError(
                        f"canary task order requires {expected_task!r} next"
                    )
                reserved = sum(
                    record["worst_case_nano_usd"]
                    for _reservation_id, record in records.values()
                )
                if reserved + worst_case > CANARY_MAX_RESERVED_NANO_USD:
                    raise ValueError(
                        "combined canary reservations exceed 260000000 nano-USD"
                    )
                reserve()
        else:
            reserve()
        context = llm.MeteringContext(
            reservation_id=reservation_id,
            policy_uid=policy.uid,
            policy_version=policy.version,
            task=task,
            model=route.model,
            admission_mode=admission_mode,
            segment_classes=canonical_segments,
            utc_day=day,
            run_uid=binding.run_uid,
            gateway_url=binding.gateway_url,
            virtual_key=binding.virtual_key,
        )
    except Exception as exc:
        return _refusal("RESERVATION_REFUSED", str(exc) or type(exc).__name__)

    invoke = provider_call or llm.call_locked
    try:
        response = invoke(
            task,
            messages,
            max_tokens=max_tokens,
            system=system,
            metering_context=context,
        )
    except Exception as exc:
        return _refusal(
            "PROVIDER_FAILED",
            str(exc) or type(exc).__name__,
            reservation_id=reservation_id,
            retained=True,
        )
    if not isinstance(response, llm.LockedLLMResponse):
        return _refusal(
            "PROVIDER_RESPONSE_REFUSED",
            "provider returned no locked usage-bearing response",
            reservation_id=reservation_id,
            retained=True,
        )
    if response.model != route.model:
        return _refusal(
            "MODEL_SUBSTITUTION",
            "provider response model does not match the locked route",
            reservation_id=reservation_id,
            retained=True,
        )
    try:
        actual = price_locked_usage_nano_usd(
            response.model,
            response.usage,
            task=task,
        )
        # Any impossible overage is passed to reconciliation so the ledger is
        # poisoned rather than silently retaining a merely clean reservation.
        if actual > route.per_call_ceiling_nano_usd:
            actual = max(actual, worst_case + 1)
        daily_spend.reconcile(
            ledger_root,
            day=day,
            policy_uid=policy.uid,
            policy_version=policy.version,
            daily_ceiling_nano_usd=policy.daily_ceiling_nano_usd,
            reservation_id=reservation_id,
            run_uid=binding.run_uid,
            task=task,
            model=route.model,
            segment_classes=canonical_segments,
            actual_nano_usd=actual,
        )
    except Exception as exc:
        return _refusal(
            "RECONCILIATION_REFUSED",
            str(exc) or type(exc).__name__,
            reservation_id=reservation_id,
            retained=True,
        )
    return MeteredModelResult(
        text=response.text,
        model=response.model,
        usage=dict(response.usage),
        receipt=ModelReceipt(
            reservation_id=reservation_id,
            utc_day=day,
            policy_uid=policy.uid,
            policy_version=policy.version,
            run_uid=binding.run_uid,
            task=task,
            model=route.model,
            admission_mode=admission_mode,
            segment_classes=canonical_segments,
            reserved_nano_usd=worst_case,
            actual_nano_usd=actual,
        ),
    )


def call(
    task: str,
    messages: list[dict],
    *,
    segment_classes,
    run_binding,
    max_tokens: int,
    system: str | None = None,
    provider_call=None,
    policy_resolver=None,
    clock: Callable[[], datetime] | None = None,
    reservation_id_factory: Callable[[], str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> MeteredModelResult | ModelRefusal:
    """Attempt one production route or return a typed, non-escalating refusal."""
    return _call(
        task,
        messages,
        admission_mode=PRODUCTION_ADMISSION,
        segment_classes=segment_classes,
        run_binding=run_binding,
        max_tokens=max_tokens,
        system=system,
        provider_call=provider_call,
        policy_resolver=policy_resolver,
        clock=clock,
        reservation_id_factory=reservation_id_factory,
        environment=environment,
    )


def call_canary(
    task: str,
    *,
    run_binding,
    provider_call=None,
    policy_resolver=None,
    clock: Callable[[], datetime] | None = None,
    reservation_id_factory: Callable[[], str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> MeteredModelResult | ModelRefusal:
    """Attempt one code-fixed OS-only canary route through the shared path."""
    try:
        messages, system, max_tokens = canary_request(task)
    except ValueError as exc:
        return _refusal("UNKNOWN_TASK", str(exc))
    return _call(
        task,
        messages,
        admission_mode=CANARY_ADMISSION,
        segment_classes=("os",),
        run_binding=run_binding,
        max_tokens=max_tokens,
        system=system,
        provider_call=provider_call,
        policy_resolver=policy_resolver,
        clock=clock,
        reservation_id_factory=reservation_id_factory,
        environment=environment,
    )


__all__ = [
    "CANARY_ADMISSION",
    "CANARY_MAX_BUDGET_USD",
    "CANARY_MAX_WALL_CLOCK_MIN",
    "CANARY_GATEWAY_RECEIPTS_NAME",
    "CANARY_EXECUTION_LEDGER_NAME",
    "CANARY_PREPARATION_NAME",
    "CANARY_READINESS_NAME",
    "CANARY_SCORECARD_NAME",
    "CANARY_TASKS",
    "GATEWAY_URL",
    "LEDGER_RELATIVE_PATH",
    "MeteredModelResult",
    "ModelReceipt",
    "ModelRefusal",
    "PRODUCTION_ADMISSION",
    "RunBinding",
    "canary_contract_sha256",
    "canary_execution_ledger_receipt",
    "canary_expected_response",
    "canary_preparation_receipt",
    "canary_readiness_receipt",
    "canary_ledger_records",
    "canary_request",
    "canary_request_hashes",
    "canary_request_projection",
    "canary_request_sha256",
    "canary_run_events",
    "call",
    "call_canary",
    "empty_canary_gateway_receipts",
    "validate_canary_request_body",
    "validate_locked_request_body",
    "verify_canary_execution_ledger",
]
