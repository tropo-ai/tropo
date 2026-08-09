"""Strict loop-run reverse gateway.

Run with:
  mitmdump --listen-host 127.0.0.1 --listen-port 8080 \
    -s vault/tools/loop_metering_gateway.py --set loop_run_dir=<run-dir>

The addon accepts only the local Anthropic SDK ingress, rewrites it to the
exact HTTPS api.anthropic.com messages endpoint, replaces the run-bound
virtual key inside the gateway, and meters the provider response.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import numbers
import os
import re
import stat
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from mitmproxy import http


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib.loop_metering import (  # noqa: E402
    MeteringContractError,
    price_locked_usage_nano_usd,
    price_usage,
    price_usage_nano_usd,
    pricing_for,
    validate_inference_geo,
    worst_case_request_cost,
    worst_case_request_cost_nano_usd,
)
from lib import daily_spend, metered_model  # noqa: E402
from lib.distiller_model_policy import (  # noqa: E402
    CANARY_MAX_CALLS,
    CANARY_MAX_RESERVED_NANO_USD,
    DistillerModelPolicy,
    resolve_policy,
    verify_canary_claim,
)


RUN_UID_RE = re.compile(r"^[0-9a-f]{8}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GATEWAY_INGRESS_HOST = "127.0.0.1"
ANTHROPIC_UPSTREAM_HOST = "api.anthropic.com"
ANTHROPIC_MESSAGES_PATH = "/v1/messages"
METERING_HEADERS = {
    "x-tropo-policy-uid",
    "x-tropo-policy-version",
    "x-tropo-task",
    "x-tropo-model",
    "x-tropo-admission-mode",
    "x-tropo-day",
    "x-tropo-reservation-id",
    "x-tropo-run-uid",
    "x-tropo-segment-classes",
}
DISTILLER_ARTIFACT_NAMES = frozenset(
    {
        metered_model.CANARY_PREPARATION_NAME,
        metered_model.CANARY_READINESS_NAME,
        metered_model.CANARY_GATEWAY_RECEIPTS_NAME,
        metered_model.CANARY_EXECUTION_LEDGER_NAME,
        metered_model.CANARY_SCORECARD_NAME,
    }
)
CANARY_GATEWAY_RECEIPT_FIELDS = frozenset(
    {
        "reservation_id",
        "task",
        "model",
        "actual_nano_usd",
        "response_sha256",
        "response_text",
        "service_tier",
        "inference_geo",
    }
)


def _validate_canary_gateway_receipts(receipts, policy):
    if not isinstance(receipts, list) or len(receipts) > CANARY_MAX_CALLS:
        raise MeteringContractError("gateway receipt surface schema drifted")
    for index, receipt in enumerate(receipts):
        if type(receipt) is not dict or set(receipt) != CANARY_GATEWAY_RECEIPT_FIELDS:
            raise MeteringContractError("gateway receipt surface schema drifted")
        task = metered_model.CANARY_TASKS[index]
        try:
            validate_inference_geo(receipt["inference_geo"])
        except MeteringContractError as exc:
            raise MeteringContractError("gateway receipt evidence drifted") from exc
        if (
            receipt["task"] != task
            or receipt["model"] != policy.route(task).model
            or not isinstance(receipt["reservation_id"], str)
            or RUN_UID_RE.fullmatch(receipt["reservation_id"]) is None
            or isinstance(receipt["actual_nano_usd"], bool)
            or not isinstance(receipt["actual_nano_usd"], int)
            or receipt["actual_nano_usd"] < 0
            or not isinstance(receipt["response_sha256"], str)
            or SHA256_RE.fullmatch(receipt["response_sha256"]) is None
            or not isinstance(receipt["response_text"], str)
            or hashlib.sha256(
                receipt["response_text"].encode("utf-8", errors="strict")
            ).hexdigest()
            != receipt["response_sha256"]
            or receipt["service_tier"] != "standard"
        ):
            raise MeteringContractError("gateway receipt evidence drifted")


def _parse_nonnegative_number(value, field_name):
    """Return one finite nonnegative runtime number or reject it."""
    if isinstance(value, bool) or not isinstance(value, (numbers.Real, Decimal)):
        raise ValueError(
            f"{field_name} must be a finite nonnegative JSON number"
        )
    try:
        numeric = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a finite nonnegative JSON number"
        ) from exc
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(
            f"{field_name} must be a finite nonnegative JSON number"
        )
    return numeric


def _parse_persisted_spend(value):
    return _parse_nonnegative_number(value, "spent_usd")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-finite JSON constant {value!r}")


def _strict_json(value, field_name):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="strict")
    parsed = json.loads(
        value,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
        parse_float=Decimal,
    )
    if type(parsed) is not dict:
        raise ValueError(f"{field_name} must be a JSON object")
    return parsed


def _atomic_write_json(path, value):
    if path.is_symlink():
        raise ValueError(f"{path.name} may not be a symlink")
    rendered = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_new_json(path, value):
    if path.exists() or path.is_symlink():
        raise ValueError(f"{path.name} already exists")
    rendered = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(descriptor)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.close(descriptor)


def _read_closed_json(path, field):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{field} is missing or symlinked")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{field} must be a regular file")
        raw = os.read(descriptor, os.fstat(descriptor).st_size + 1)
    finally:
        os.close(descriptor)
    value = _strict_json(raw, field)
    canonical = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    if canonical != raw:
        raise ValueError(f"{field} is not canonical closed JSON")
    return value


class LoopMeteringGateway:
    def __init__(self):
        self.budget_usd = float("inf")
        self.budget_readable = False
        self.contract_readable = False
        self.spent_usd = 0.0
        self.persisted_spend_readable = True
        self.run_dir = None
        self.run_uid = None
        self.run_created = None
        self.loop_contract = None
        self.real_api_key = os.environ.get("REAL_ANTHROPIC_API_KEY", "")
        self.req_models = {}
        self.daily_spend_root = TOOLS_DIR.parent / "loop-runs" / ".model-spend"
        self.policy_resolver = resolve_policy

    def load(self, loader):
        loader.add_option(
            name="loop_run_dir",
            typespec=str,
            default="",
            help="Loop-run directory for locked contract and ground-truth spend",
        )

    def configure(self, updated):
        if "loop_run_dir" in updated and self.run_dir is None:
            import mitmproxy.ctx as ctx

            run_dir_str = ctx.options.loop_run_dir
            if run_dir_str:
                self.run_dir = Path(run_dir_str)
                self._load_contract()
                self._load_persisted_spend()
                self._write_readiness_if_safe()

    def _load_contract(self):
        self.contract_readable = False
        self.budget_readable = False
        self.run_uid = None
        self.run_created = None
        self.loop_contract = None
        if not self.run_dir:
            return
        run_jsonl = self.run_dir / "run.jsonl"
        if not run_jsonl.is_file():
            return
        try:
            events = [
                _strict_json(line, "run.jsonl event")
                for line in run_jsonl.read_bytes().splitlines()
                if line.strip()
            ]
            if events:
                self.run_created = events[0]
            if len(events) > 1:
                self.loop_contract = events[1]
            if (
                len(events) < 2
                or events[0].get("event") != "run_created"
                or events[1].get("event") != "loop_contract_locked"
                or sum(
                    event.get("event") == "loop_contract_locked"
                    for event in events
                )
                != 1
            ):
                raise ValueError(
                    "run.jsonl must begin with one run_created then one "
                    "loop_contract_locked"
                )
            run_uid = events[0].get("run_uid")
            if not isinstance(run_uid, str) or not RUN_UID_RE.fullmatch(run_uid):
                raise ValueError("run_created.run_uid must be 8 lowercase hex")
            brakes = events[1].get("brakes")
            if type(brakes) is not dict:
                raise ValueError("loop contract brakes must be an object")
            raw_budget = brakes.get("max_budget_usd")
            self.budget_usd = (
                float("inf")
                if raw_budget is None
                else _parse_nonnegative_number(raw_budget, "max_budget_usd")
            )
        except Exception:
            self.budget_usd = float("-inf")
            return
        self.run_uid = run_uid
        self.run_created = events[0]
        self.loop_contract = events[1]
        self.contract_readable = True
        self.budget_readable = True

    def _load_persisted_spend(self):
        """Load persisted spend without ever resetting malformed state to zero."""
        self.persisted_spend_readable = True
        if not self.run_dir:
            self.persisted_spend_readable = False
            self.spent_usd = float("inf")
            return
        spend_file = self.run_dir / "gateway_spend.json"
        if not spend_file.is_file():
            self.persisted_spend_readable = False
            self.spent_usd = float("inf")
            return
        try:
            spend_data = _strict_json(
                spend_file.read_bytes(),
                "gateway_spend.json",
            )
            if set(spend_data) != {"spent_usd"}:
                raise ValueError(
                    "gateway_spend.json must contain only spent_usd"
                )
            self.spent_usd = _parse_persisted_spend(
                spend_data["spent_usd"]
            )
        except Exception:
            self.persisted_spend_readable = False
            self.spent_usd = float("inf")

    def _is_distiller_contract(self):
        """Recognize any surviving Distiller identity marker fail-closed."""
        created = self.run_created if type(self.run_created) is dict else {}
        contract = self.loop_contract if type(self.loop_contract) is dict else {}
        executor = contract.get("policy")
        known_tasks = frozenset(metered_model.CANARY_TASKS)
        tasks = contract.get("tasks")
        if isinstance(tasks, str):
            task_marker = tasks in known_tasks
        elif isinstance(tasks, (list, tuple, set, frozenset, dict)):
            task_marker = any(
                isinstance(task, str) and task in known_tasks
                for task in tasks
            )
        else:
            task_marker = False
        markers_without_segments = (
            created.get("loop") == "0c938a95",
            contract.get("loop") == "0c938a95",
            type(executor) is dict and executor.get("ref") == "6389dcd4",
            "admission_mode" in contract,
            "request_sha256" in contract,
            task_marker,
        )
        if any(markers_without_segments) or "segment_classes" in contract:
            return True
        if self.run_dir is None:
            return False
        return any(
            (self.run_dir / name).exists()
            or (self.run_dir / name).is_symlink()
            for name in DISTILLER_ARTIFACT_NAMES
        )

    def _canary_contract_hash(self, policy):
        expected_created, expected_contract = metered_model.canary_run_events(
            self.run_uid,
            policy.runner_uid,
        )
        parsed_expected = json.loads(
            json.dumps(expected_contract),
            parse_float=Decimal,
        )
        if self.run_created != expected_created or self.loop_contract != parsed_expected:
            raise MeteringContractError(
                "canary run contract does not equal the code-derived contract"
            )
        return metered_model.canary_contract_sha256(expected_contract)

    def _expected_readiness(self, policy, contract_hash):
        return metered_model.canary_readiness_receipt(
            run_uid=self.run_uid,
            runner_uid=policy.runner_uid,
            contract_sha256=contract_hash,
        )

    def _verify_readiness(self, policy, contract_hash):
        if not self.run_dir:
            raise MeteringContractError("canary run directory is unavailable")
        actual = _read_closed_json(
            self.run_dir / metered_model.CANARY_READINESS_NAME,
            metered_model.CANARY_READINESS_NAME,
        )
        if actual != self._expected_readiness(policy, contract_hash):
            raise MeteringContractError("canary readiness receipt drifted")
        receipt_path = self.run_dir / metered_model.CANARY_GATEWAY_RECEIPTS_NAME
        surface = _read_closed_json(receipt_path, receipt_path.name)
        expected = metered_model.empty_canary_gateway_receipts(
            run_uid=self.run_uid,
            contract_sha256=contract_hash,
        )
        if {
            key: value for key, value in surface.items() if key != "receipts"
        } != {
            key: value for key, value in expected.items() if key != "receipts"
        } or not isinstance(surface.get("receipts"), list):
            raise MeteringContractError("gateway receipt surface identity drifted")
        _validate_canary_gateway_receipts(surface["receipts"], policy)

    def _write_readiness_if_safe(self):
        if not self._is_distiller_contract():
            return
        if self.loop_contract.get("admission_mode") != "canary":
            return
        if (
            not self.contract_readable
            or not self.budget_readable
            or not self.persisted_spend_readable
            or self.spent_usd != 0
            or not self.real_api_key
            or not self.run_dir
        ):
            raise MeteringContractError(
                "canary gateway is not ready: contract, spend, or real key is absent"
            )
        policy = self.policy_resolver()
        if not isinstance(policy, DistillerModelPolicy) or not policy.canary_admissible:
            raise MeteringContractError("Distiller policy is not canary-admissible")
        contract_hash = self._canary_contract_hash(policy)
        verify_canary_claim(
            self.daily_spend_root,
            policy=policy,
            run_uid=self.run_uid,
            run_dir=self.run_dir,
            contract_sha256=contract_hash,
        )
        records = metered_model.canary_ledger_records(
            self.daily_spend_root,
            policy=policy,
            run_uid=self.run_uid,
        )
        preparation = _read_closed_json(
            self.run_dir / metered_model.CANARY_PREPARATION_NAME,
            metered_model.CANARY_PREPARATION_NAME,
        )
        try:
            expected_preparation = metered_model.canary_preparation_receipt(
                run_uid=self.run_uid,
                runner_uid=policy.runner_uid,
                contract_sha256=contract_hash,
                preparation_day=preparation.get("preparation_day"),
            )
        except ValueError as exc:
            raise MeteringContractError(
                f"canary preparation receipt drifted: {exc}"
            ) from exc
        if preparation != expected_preparation:
            raise MeteringContractError("canary preparation receipt drifted")
        readiness_path = self.run_dir / metered_model.CANARY_READINESS_NAME
        expected = self._expected_readiness(policy, contract_hash)
        if readiness_path.exists() or readiness_path.is_symlink():
            if _read_closed_json(readiness_path, readiness_path.name) != expected:
                raise MeteringContractError("existing canary readiness receipt drifted")
        else:
            current_ledgers = [
                path
                for path in self.daily_spend_root.iterdir()
                if path.name.endswith(f"@{policy.version}.json")
            ]
            execution_receipt = (
                self.run_dir / metered_model.CANARY_EXECUTION_LEDGER_NAME
            )
            if records or current_ledgers or execution_receipt.exists() or (
                execution_receipt.is_symlink()
            ):
                raise MeteringContractError(
                    "gateway must first declare readiness before the execution ledger"
                )
            _write_new_json(readiness_path, expected)
        receipt_path = self.run_dir / metered_model.CANARY_GATEWAY_RECEIPTS_NAME
        expected_surface = metered_model.empty_canary_gateway_receipts(
            run_uid=self.run_uid,
            contract_sha256=contract_hash,
        )
        if receipt_path.exists() or receipt_path.is_symlink():
            surface = _read_closed_json(receipt_path, receipt_path.name)
            if {
                key: value
                for key, value in surface.items()
                if key != "receipts"
            } != {
                key: value
                for key, value in expected_surface.items()
                if key != "receipts"
            }:
                raise MeteringContractError("gateway receipt surface identity drifted")
        else:
            _write_new_json(receipt_path, expected_surface)

    @staticmethod
    def _respond(flow, status, message):
        flow.response = http.Response.make(
            status,
            message.encode("utf-8"),
            {"Content-Type": "text/plain"},
        )

    @staticmethod
    def _route_upstream(flow):
        if getattr(flow.request, "path", None) != ANTHROPIC_MESSAGES_PATH:
            raise MeteringContractError(
                f"gateway only routes exact path {ANTHROPIC_MESSAGES_PATH}"
            )
        flow.request.scheme = "https"
        flow.request.host = ANTHROPIC_UPSTREAM_HOST
        flow.request.port = 443
        flow.request.headers["host"] = ANTHROPIC_UPSTREAM_HOST
        if (
            flow.request.scheme != "https"
            or flow.request.host != ANTHROPIC_UPSTREAM_HOST
            or flow.request.port != 443
            or flow.request.headers.get("host") != ANTHROPIC_UPSTREAM_HOST
        ):
            raise MeteringContractError("explicit Anthropic upstream route failed")

    @staticmethod
    def _metering_header_values(flow):
        present = {
            name: flow.request.headers.get(name)
            for name in METERING_HEADERS
            if flow.request.headers.get(name) is not None
        }
        if not present:
            return None
        if set(present) != METERING_HEADERS or any(
            not isinstance(value, str) or not value for value in present.values()
        ):
            raise MeteringContractError(
                "Distiller metering headers must be complete and non-empty"
            )
        segments = present["x-tropo-segment-classes"].split(",")
        if (
            not segments
            or segments != sorted(set(segments))
            or any(value not in {"os", "team", "private"} for value in segments)
        ):
            raise MeteringContractError(
                "Distiller segment headers are not canonical"
            )
        present["segment_classes"] = tuple(segments)
        if present["x-tropo-admission-mode"] not in {"production", "canary"}:
            raise MeteringContractError(
                "Distiller admission mode must be production or canary"
            )
        return present

    def _validate_distiller_contract(self, policy, admission_mode):
        created = self.run_created
        contract = self.loop_contract
        if type(created) is not dict or type(contract) is not dict:
            raise MeteringContractError("Distiller loop contract is unavailable")
        if (
            created.get("run_uid") != self.run_uid
            or created.get("loop") != policy.uid
            or created.get("loop_version") != policy.version
            or contract.get("loop") != policy.uid
            or contract.get("loop_version") != policy.version
        ):
            raise MeteringContractError(
                "Distiller run contract policy/run identity mismatch"
            )
        executor = contract.get("policy")
        if executor != {"kind": "agentic-tool", "ref": policy.runner_uid}:
            raise MeteringContractError(
                "Distiller run contract does not bind the registered runner"
            )
        if contract.get("admission_mode") != admission_mode:
            raise MeteringContractError(
                "Distiller admission header/run contract mismatch"
            )
        if admission_mode != "canary":
            return None
        if not self.run_dir:
            raise MeteringContractError("canary run directory is unavailable")
        contract_hash = self._canary_contract_hash(policy)
        verify_canary_claim(
            self.daily_spend_root,
            policy=policy,
            run_uid=self.run_uid,
            run_dir=self.run_dir,
            contract_sha256=contract_hash,
        )
        execution_ledger = metered_model.verify_canary_execution_ledger(
            run_dir=self.run_dir,
            ledger_root=self.daily_spend_root,
            policy=policy,
            run_uid=self.run_uid,
            contract_sha256=contract_hash,
        )
        self._verify_readiness(policy, contract_hash)
        return execution_ledger

    def _validate_canary_call_count(self, policy, task):
        records_by_task = metered_model.canary_ledger_records(
            self.daily_spend_root,
            policy=policy,
            run_uid=self.run_uid,
        )
        records = [record for _reservation_id, record in records_by_task.values()]
        if len(records) > CANARY_MAX_CALLS:
            raise MeteringContractError("canary call count exceeds the locked maximum")
        tasks = [record["task"] for record in records]
        if any(value not in {"parse-query", "distill"} for value in tasks):
            raise MeteringContractError("canary reservation named an unknown task")
        if tasks.count(task) != 1 or len(set(tasks)) != len(tasks):
            raise MeteringContractError(
                "canary permits at most one reservation for each locked task"
            )
        expected_tasks = set(metered_model.CANARY_TASKS[: len(records)])
        if (
            set(tasks) != expected_tasks
            or task != metered_model.CANARY_TASKS[len(records) - 1]
        ):
            raise MeteringContractError("canary reservation task order drifted")
        if sum(record["worst_case_nano_usd"] for record in records) > (
            CANARY_MAX_RESERVED_NANO_USD
        ):
            raise MeteringContractError(
                "combined canary reservations exceed 260000000 nano-USD"
            )

    def _claim_distiller_reservation(
        self,
        flow,
        request_data,
        *,
        exact_worst_case_nano_usd,
    ):
        headers = self._metering_header_values(flow)
        if headers is None:
            if self._is_distiller_contract():
                raise MeteringContractError(
                    "Distiller run contract requires complete metering headers"
                )
            return None
        if getattr(flow.request, "path", None) != ANTHROPIC_MESSAGES_PATH:
            raise MeteringContractError(
                f"Distiller only routes exact path {ANTHROPIC_MESSAGES_PATH}"
            )
        policy = self.policy_resolver()
        if not isinstance(policy, DistillerModelPolicy):
            raise MeteringContractError("Distiller policy resolver returned wrong type")
        if (
            headers["x-tropo-policy-uid"] != policy.uid
            or headers["x-tropo-policy-version"] != policy.version
        ):
            raise MeteringContractError("Distiller policy UID/version mismatch")
        admission_mode = headers["x-tropo-admission-mode"]
        execution_ledger = self._validate_distiller_contract(policy, admission_mode)
        if admission_mode == "production":
            if not policy.production_enabled:
                raise MeteringContractError(
                    "Distiller policy is not production-enabled"
                )
        elif not policy.canary_admissible:
            raise MeteringContractError("Distiller policy is not canary-admissible")
        task = headers["x-tropo-task"]
        route = policy.route(task)
        metered_model.validate_locked_request_body(task, request_data)
        model = request_data.get("model")
        if (
            headers["x-tropo-model"] != route.model
            or model != route.model
        ):
            raise MeteringContractError("Distiller task/model route mismatch")
        if (
            headers["x-tropo-run-uid"] != self.run_uid
            or headers["x-tropo-day"] != daily_spend.utc_day()
        ):
            raise MeteringContractError("Distiller run/day binding mismatch")
        segments = headers["segment_classes"]
        if segments != ("os",):
            raise MeteringContractError(
                "bounded Distiller response geography is restricted to OS"
            )
        if admission_mode == "production":
            if any(policy.segment_egress.get(value) != "auto" for value in segments):
                raise MeteringContractError("Distiller segment consent is not auto")
        elif segments != ("os",):
            raise MeteringContractError("Distiller canary segment must be exactly OS")
        else:
            metered_model.validate_canary_request_body(task, request_data)
            self._validate_canary_call_count(policy, task)
            current_day = daily_spend.utc_day()
            if (
                type(execution_ledger) is not dict
                or execution_ledger.get("execution_day")
                != headers["x-tropo-day"]
                or execution_ledger["execution_day"] != current_day
            ):
                raise MeteringContractError(
                    "canary execution ledger does not bind the header and current UTC day"
                )
        record = daily_spend.claim_reservation(
            self.daily_spend_root,
            day=headers["x-tropo-day"],
            policy_uid=policy.uid,
            policy_version=policy.version,
            daily_ceiling_nano_usd=policy.daily_ceiling_nano_usd,
            reservation_id=headers["x-tropo-reservation-id"],
            run_uid=self.run_uid,
            task=task,
            model=route.model,
            segment_classes=segments,
            gateway_request_id=str(flow.id),
            minimum_worst_case_nano_usd=exact_worst_case_nano_usd,
        )
        return {
            "record": record,
            "reservation_id": headers["x-tropo-reservation-id"],
            "task": task,
            "model": route.model,
            "admission_mode": admission_mode,
        }

    def request(self, flow: http.HTTPFlow):
        if flow.request.pretty_host != GATEWAY_INGRESS_HOST:
            self._respond(
                flow,
                421,
                "Gateway refuses non-exact ingress host.",
            )
            return
        if not self.contract_readable or not self.budget_readable:
            self._respond(flow, 429, "Loop-run budget contract is unreadable.")
            return
        expected_key = (
            f"sk-virtual-tropo-{self.run_uid}"
            if self.run_uid is not None
            else None
        )
        auth_header = flow.request.headers.get("x-api-key", "")
        if expected_key is None or auth_header != expected_key:
            self._respond(flow, 401, "Unauthorized: virtual key/run binding mismatch.")
            return
        if self._is_distiller_contract():
            try:
                headers = self._metering_header_values(flow)
                if headers is None:
                    raise MeteringContractError(
                        "Distiller run contract requires complete metering headers"
                    )
            except Exception as exc:
                self._respond(
                    flow,
                    429,
                    f"Distiller headers cannot be authorized: {exc}",
                )
                return
        if not self.persisted_spend_readable:
            self._respond(flow, 429, "Loop-run persisted spend is unreadable.")
            return
        if self.spent_usd >= self.budget_usd:
            self._respond(flow, 429, "Loop-run budget exceeded.")
            return
        try:
            request_data = _strict_json(
                flow.request.content,
                "Anthropic request",
            )
            model = request_data.get("model")
            pricing_for(model)
            max_tokens = request_data.get("max_tokens")
            worst_case = worst_case_request_cost(
                model,
                request_bytes=len(flow.request.content or b""),
                max_tokens=max_tokens,
            )
            exact_worst_case_nano_usd = worst_case_request_cost_nano_usd(
                model,
                request_bytes=len(flow.request.content or b""),
                max_tokens=max_tokens,
                cache_mode="none",
            )
            if self.spent_usd + worst_case > self.budget_usd:
                raise MeteringContractError(
                    "worst-case request cost exceeds remaining loop budget"
                )
        except Exception as exc:
            self._respond(flow, 429, f"Request cannot be safely metered: {exc}")
            return
        if not self.real_api_key:
            self._respond(flow, 503, "Gateway real provider key is unavailable.")
            return
        try:
            daily_record = self._claim_distiller_reservation(
                flow,
                request_data,
                exact_worst_case_nano_usd=exact_worst_case_nano_usd,
            )
        except Exception as exc:
            self._respond(
                flow,
                429,
                f"Distiller reservation cannot be authorized: {exc}",
            )
            return
        try:
            self._route_upstream(flow)
        except Exception as exc:
            self._respond(flow, 502, f"Gateway upstream route failed: {exc}")
            return
        self.req_models[flow.id] = {
            "model": model,
            "worst_case_usd": worst_case,
            "distiller_reservation": daily_record,
        }
        flow.request.headers["x-api-key"] = self.real_api_key

    def _append_canary_gateway_receipt(
        self,
        *,
        reservation,
        actual_nano_usd,
        response_sha256,
        response_text,
        service_tier,
        inference_geo,
    ):
        if not self.run_dir:
            raise MeteringContractError("gateway run directory is unavailable")
        policy = self.policy_resolver()
        if not isinstance(policy, DistillerModelPolicy):
            raise MeteringContractError("Distiller policy resolver returned wrong type")
        contract_hash = self._canary_contract_hash(policy)
        verify_canary_claim(
            self.daily_spend_root,
            policy=policy,
            run_uid=self.run_uid,
            run_dir=self.run_dir,
            contract_sha256=contract_hash,
        )
        path = self.run_dir / metered_model.CANARY_GATEWAY_RECEIPTS_NAME
        lock_path = self.run_dir / (
            f".{metered_model.CANARY_GATEWAY_RECEIPTS_NAME}.lock"
        )
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise MeteringContractError(
                    "gateway receipt lock must be a regular file"
                )
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            surface = _read_closed_json(path, path.name)
            expected = metered_model.empty_canary_gateway_receipts(
                run_uid=self.run_uid,
                contract_sha256=contract_hash,
            )
            if {
                key: value for key, value in surface.items() if key != "receipts"
            } != {
                key: value for key, value in expected.items() if key != "receipts"
            } or not isinstance(surface.get("receipts"), list):
                raise MeteringContractError("gateway receipt surface drifted")
            _validate_canary_gateway_receipts(surface["receipts"], policy)
            receipt = {
                "reservation_id": reservation["reservation_id"],
                "task": reservation["task"],
                "model": reservation["model"],
                "actual_nano_usd": actual_nano_usd,
                "response_sha256": response_sha256,
                "response_text": response_text,
                "service_tier": service_tier,
                "inference_geo": inference_geo,
            }
            receipts = surface["receipts"]
            if (
                len(receipts) >= CANARY_MAX_CALLS
                or any(
                    item.get("reservation_id") == receipt["reservation_id"]
                    or item.get("task") == receipt["task"]
                    for item in receipts
                    if type(item) is dict
                )
            ):
                raise MeteringContractError("gateway receipt replay or overflow")
            if receipt["task"] != metered_model.CANARY_TASKS[len(receipts)]:
                raise MeteringContractError("gateway receipt task order drifted")
            surface["receipts"] = [*receipts, receipt]
            _atomic_write_json(path, surface)
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _persist_metering_failure(self, message):
        self.persisted_spend_readable = False
        self.spent_usd = float("inf")
        if self.run_dir:
            _atomic_write_json(
                self.run_dir / "gateway_spend.json",
                {"metering_error": message},
            )

    def response(self, flow: http.HTTPFlow):
        request_meta = self.req_models.pop(flow.id, None)
        if request_meta is None:
            return
        if not flow.response or flow.response.status_code != 200:
            return
        try:
            data = _strict_json(flow.response.content, "Anthropic response")
            model = data.get("model")
            if model != request_meta["model"]:
                raise MeteringContractError(
                    "response model does not match requested model"
                )
            usage = data.get("usage")
            reservation = request_meta["distiller_reservation"]
            if reservation is None:
                cost = price_usage(model, usage)
                exact_cost = price_usage_nano_usd(model, usage)
            else:
                exact_cost = price_locked_usage_nano_usd(
                    model,
                    usage,
                    task=reservation["task"],
                )
                cost = exact_cost / 1_000_000_000
            if (
                reservation is not None
                and reservation.get("admission_mode") == "canary"
            ):
                content = data.get("content")
                if (
                    not isinstance(content, list)
                    or len(content) != 1
                    or type(content[0]) is not dict
                    or set(content[0]) != {"type", "text"}
                    or content[0].get("type") != "text"
                    or not isinstance(content[0].get("text"), str)
                ):
                    raise MeteringContractError(
                        "canary response must contain one closed text block"
                    )
                response_sha256 = hashlib.sha256(
                    content[0]["text"].encode("utf-8", errors="strict")
                ).hexdigest()
                self._append_canary_gateway_receipt(
                    reservation=reservation,
                    actual_nano_usd=exact_cost,
                    response_sha256=response_sha256,
                    response_text=content[0]["text"],
                    service_tier=usage["service_tier"],
                    inference_geo=usage["inference_geo"],
                )
            next_spend = self.spent_usd + cost
            if not math.isfinite(next_spend) or next_spend < self.spent_usd:
                raise MeteringContractError("computed persisted spend is invalid")
            self.spent_usd = next_spend
            if not self.run_dir:
                raise MeteringContractError("gateway run directory is unavailable")
            _atomic_write_json(
                self.run_dir / "gateway_spend.json",
                {"spent_usd": self.spent_usd},
            )
        except Exception as exc:
            self._persist_metering_failure(str(exc) or type(exc).__name__)
            self._respond(flow, 502, "Provider usage could not be safely metered.")


addons = [LoopMeteringGateway()]

