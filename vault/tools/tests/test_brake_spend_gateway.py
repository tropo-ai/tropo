# v1.71 S1 loop-primitive brake test — SPEND (AC2).
# Body authored by argus-a114 (2026-06-16) from the Argus ad-hoc verification battery,
# per Metis G81 cut-bar decision (event 3900, option a). Talos owns/adjusts to suit the
# engine test conventions. Verifies vault/tools/1edbee15.py (the brakes watchdog).
import hashlib
import json
import shutil
import socket
import sys
import tempfile
import unittest
import importlib.util
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

vault_tools_dir = Path(__file__).resolve().parent.parent
if str(vault_tools_dir) not in sys.path:
    sys.path.insert(0, str(vault_tools_dir))

from lib import daily_spend, llm, loop_metering, metered_model
from lib.distiller_model_policy import (
    DAILY_CEILING_NANO_USD,
    POLICY_VERSION,
    DistillerModelPolicy,
    MODEL_ROUTES,
    ModelRoute,
    claim_canary_authority,
)

spec = importlib.util.spec_from_file_location("watchdog", str(vault_tools_dir / "1edbee15.py"))
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)
gateway_spec = importlib.util.spec_from_file_location(
    "loop_metering_gateway",
    str(vault_tools_dir / "loop_metering_gateway.py"),
)
gateway = importlib.util.module_from_spec(gateway_spec)


class _FixtureResponse:
    @staticmethod
    def make(*args, **kwargs):
        return (args, kwargs)


fake_mitmproxy = ModuleType("mitmproxy")
fake_mitmproxy.http = SimpleNamespace(
    HTTPFlow=object,
    Response=_FixtureResponse,
)
with mock.patch.dict("sys.modules", {"mitmproxy": fake_mitmproxy}):
    gateway_spec.loader.exec_module(gateway)


RUN_UID = "abcd1234"
VIRTUAL_KEY = f"sk-virtual-tropo-{RUN_UID}"
DISTILLER_DAY = daily_spend.utc_day()
_SOCKET_PATCHERS = (
    mock.patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket.socket,
        "connect",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket.socket,
        "connect_ex",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket,
        "socket",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
)


def setUpModule():
    for patcher in _SOCKET_PATCHERS:
        patcher.start()


def tearDownModule():
    for patcher in reversed(_SOCKET_PATCHERS):
        patcher.stop()


def _seed(run_dir: Path, brakes: dict, iters: int = 1):
    with open(run_dir / "run.jsonl", "w") as f:
        f.write(
            json.dumps({"event": "run_created", "run_uid": RUN_UID}) + "\n"
        )
        f.write(json.dumps({"event": "loop_contract_locked", "brakes": brakes}) + "\n")
        for n in range(1, iters + 1):
            f.write(json.dumps({"event": "iteration_completed", "iteration_n": n}) + "\n")


def _seed_distiller(run_dir: Path, admission_mode: str, budget: float):
    if admission_mode == "canary":
        created, contract = metered_model.canary_run_events(RUN_UID)
        contract["brakes"]["max_budget_usd"] = budget
        (run_dir / "run.jsonl").write_text(
            json.dumps(created, sort_keys=True, separators=(",", ":"))
            + "\n"
            + json.dumps(contract, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        return
    created = {
        "event": "run_created",
        "run_uid": RUN_UID,
        "loop": "0c938a95",
        "loop_version": POLICY_VERSION,
    }
    contract = {
        "event": "loop_contract_locked",
        "loop": "0c938a95",
        "loop_version": POLICY_VERSION,
        "policy": {"kind": "agentic-tool", "ref": "6389dcd4"},
        "admission_mode": admission_mode,
        "brakes": {
            "max_iterations": 2,
            "max_budget_usd": budget,
            "max_wall_clock_min": 5,
        },
    }
    (run_dir / "run.jsonl").write_text(
        json.dumps(created, sort_keys=True, separators=(",", ":"))
        + "\n"
        + json.dumps(contract, sort_keys=True, separators=(",", ":"))
        + "\n"
    )


def _events(run_dir: Path):
    with open(run_dir / "run.jsonl") as handle:
        return [json.loads(line) for line in handle]


class TestSpendBrake(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.run_dir = self.root / "vault" / "loop-runs" / "r"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def _reset_run_dir(self):
        loop_runs = self.root / "vault" / "loop-runs"
        if loop_runs.exists():
            shutil.rmtree(loop_runs)
        self.run_dir.mkdir(parents=True)

    def test_spend_over_budget_trips(self):
        """A run past its per-run $ budget is hard-killed (gateway ground-truth)."""
        _seed(self.run_dir, {"max_budget_usd": 1.0})
        (self.run_dir / "gateway_spend.json").write_text(json.dumps({"spent_usd": 2.5}))
        watchdog.watchdog_scan(self.root)
        self.assertTrue((self.run_dir / ".poison_sentinel").exists())
        ev = _events(self.run_dir)
        self.assertEqual(ev[-2]["event"], "brake_tripped")
        self.assertEqual(ev[-2]["brake"], "max_budget_usd")

    def test_spend_failclosed_on_missing_file(self):
        """FAIL-CLOSED: a missing gateway_spend.json trips, not fail-open."""
        _seed(self.run_dir, {"max_budget_usd": 1.0})
        watchdog.watchdog_scan(self.root)
        self.assertTrue((self.run_dir / ".poison_sentinel").exists(),
                        "missing spend file must fail-closed (trip), not pass")
        self.assertEqual(_events(self.run_dir)[-2]["brake"], "max_budget_usd")

    def test_spend_failclosed_on_unreadable_file(self):
        """FAIL-CLOSED: an unreadable/garbage gateway_spend.json trips."""
        _seed(self.run_dir, {"max_budget_usd": 1.0})
        (self.run_dir / "gateway_spend.json").write_text("{not valid json")
        watchdog.watchdog_scan(self.root)
        self.assertTrue((self.run_dir / ".poison_sentinel").exists())

    def test_persisted_spend_domain_errors_trip_watchdog_failclosed(self):
        invalid_values = (
            float("nan"),
            float("inf"),
            True,
            -0.01,
            "not-a-number",
        )
        for value in invalid_values:
            with self.subTest(value=repr(value)):
                shutil.rmtree(self.run_dir)
                self.run_dir.mkdir(parents=True)
                _seed(self.run_dir, {"max_budget_usd": 5.0})
                (self.run_dir / "gateway_spend.json").write_text(
                    json.dumps({"spent_usd": value})
                )
                watchdog.watchdog_scan(self.root)
                self.assertTrue(
                    (self.run_dir / ".poison_sentinel").exists()
                )
                trip = _events(self.run_dir)[-2]
                self.assertEqual(trip["brake"], "max_budget_usd")
                self.assertEqual(trip["ground_truth_value"], "UNREADABLE")

    def test_persisted_spend_domain_errors_block_gateway_failclosed(self):
        invalid_values = (
            float("nan"),
            float("inf"),
            True,
            -0.01,
            "not-a-number",
        )
        for value in invalid_values:
            with self.subTest(value=repr(value)):
                shutil.rmtree(self.run_dir)
                self.run_dir.mkdir(parents=True)
                _seed(self.run_dir, {"max_budget_usd": 5.0})
                (self.run_dir / "gateway_spend.json").write_text(
                    json.dumps({"spent_usd": value})
                )
                meter = gateway.LoopMeteringGateway()
                meter.run_dir = self.run_dir
                meter._load_contract()
                meter._load_persisted_spend()
                self.assertFalse(meter.persisted_spend_readable)

                flow = SimpleNamespace(
                    id=f"invalid-{value!r}",
                    request=SimpleNamespace(
                        pretty_host=gateway.GATEWAY_INGRESS_HOST,
                        headers={"x-api-key": VIRTUAL_KEY},
                        content=b'{"model":"claude-3-opus-20240229"}',
                    ),
                    response=None,
                )
                sentinel = object()
                with mock.patch.object(
                    gateway.http.Response,
                    "make",
                    return_value=sentinel,
                ) as response_make:
                    meter.request(flow)
                self.assertIs(flow.response, sentinel)
                self.assertEqual(response_make.call_args.args[0], 429)
                self.assertNotIn(flow.id, meter.req_models)

    def test_invalid_budget_domains_trip_watchdog_failclosed(self):
        invalid_values = (
            float("nan"),
            float("inf"),
            True,
            -0.01,
            "not-a-number",
        )
        for value in invalid_values:
            with self.subTest(value=repr(value)):
                shutil.rmtree(self.run_dir)
                self.run_dir.mkdir(parents=True)
                _seed(self.run_dir, {"max_budget_usd": value})
                (self.run_dir / "gateway_spend.json").write_text(
                    json.dumps({"spent_usd": 0.0})
                )
                watchdog.watchdog_scan(self.root)
                self.assertTrue(
                    (self.run_dir / ".poison_sentinel").exists()
                )
                trip = _events(self.run_dir)[-2]
                self.assertEqual(trip["brake"], "max_budget_usd")
                self.assertEqual(
                    trip["ground_truth_value"],
                    "INVALID_LIMIT",
                )
                self.assertIn(
                    "run.jsonl_contract_error",
                    trip["source"],
                )

    def test_invalid_budget_domains_block_gateway_failclosed(self):
        invalid_values = (
            float("nan"),
            float("inf"),
            True,
            -0.01,
            "not-a-number",
        )
        for value in invalid_values:
            with self.subTest(value=repr(value)):
                shutil.rmtree(self.run_dir)
                self.run_dir.mkdir(parents=True)
                _seed(self.run_dir, {"max_budget_usd": value})
                meter = gateway.LoopMeteringGateway()
                meter.run_dir = self.run_dir
                meter._load_contract()
                self.assertFalse(meter.budget_readable)

                flow = SimpleNamespace(
                    id=f"invalid-budget-{value!r}",
                    request=SimpleNamespace(
                        pretty_host=gateway.GATEWAY_INGRESS_HOST,
                        headers={"x-api-key": VIRTUAL_KEY},
                        content=b'{"model":"claude-3-opus-20240229"}',
                    ),
                    response=None,
                )
                sentinel = object()
                with mock.patch.object(
                    gateway.http.Response,
                    "make",
                    return_value=sentinel,
                ) as response_make:
                    meter.request(flow)
                self.assertIs(flow.response, sentinel)
                self.assertEqual(response_make.call_args.args[0], 429)
                self.assertNotIn(flow.id, meter.req_models)

    def test_spend_under_budget_no_trip(self):
        """A run under budget is NOT killed (no spurious trip)."""
        _seed(self.run_dir, {"max_budget_usd": 5.0})
        (self.run_dir / "gateway_spend.json").write_text(json.dumps({"spent_usd": 1.0}))
        watchdog.watchdog_scan(self.root)
        self.assertFalse((self.run_dir / ".poison_sentinel").exists())

    def test_zero_budget_trips_at_zero_ground_truth_spend(self):
        _seed(self.run_dir, {"max_budget_usd": 0.0})
        (self.run_dir / "gateway_spend.json").write_text(
            json.dumps({"spent_usd": 0.0})
        )
        watchdog.watchdog_scan(self.root)
        self.assertTrue((self.run_dir / ".poison_sentinel").exists())
        self.assertEqual(_events(self.run_dir)[-2]["brake"], "max_budget_usd")

    def test_zero_budget_refuses_gateway_call_before_upstream(self):
        _seed(self.run_dir, {"max_budget_usd": 0.0})
        meter = gateway.LoopMeteringGateway()
        meter.run_dir = self.run_dir
        meter._load_contract()
        self.assertEqual(meter.budget_usd, 0.0)
        meter.spent_usd = 0.0
        flow = SimpleNamespace(
            id="zero-budget",
            request=SimpleNamespace(
                pretty_host=gateway.GATEWAY_INGRESS_HOST,
                headers={"x-api-key": VIRTUAL_KEY},
                content=b'{"model":"claude-3-opus-20240229"}',
            ),
            response=None,
        )
        sentinel = object()
        with mock.patch.object(
            gateway.http.Response,
            "make",
            return_value=sentinel,
        ) as response_make:
            meter.request(flow)
        self.assertIs(flow.response, sentinel)
        self.assertEqual(response_make.call_args.args[0], 429)
        self.assertNotIn(flow.id, meter.req_models)

    def test_null_and_missing_budget_preserve_no_spend_check(self):
        for brakes in ({}, {"max_budget_usd": None}):
            with self.subTest(brakes=brakes):
                shutil.rmtree(self.run_dir)
                self.run_dir.mkdir(parents=True)
                _seed(self.run_dir, brakes)
                watchdog.watchdog_scan(self.root)
                self.assertFalse(
                    (self.run_dir / ".poison_sentinel").exists()
                )

    def _metered_flow(self, *, model="claude-opus-4-8", max_tokens=256):
        return SimpleNamespace(
            id=f"flow-{model}",
            request=SimpleNamespace(
                pretty_host=gateway.GATEWAY_INGRESS_HOST,
                path=gateway.ANTHROPIC_MESSAGES_PATH,
                scheme="http",
                host=gateway.GATEWAY_INGRESS_HOST,
                port=8080,
                headers={"x-api-key": VIRTUAL_KEY},
                content=json.dumps(
                    {"model": model, "max_tokens": max_tokens}
                ).encode(),
            ),
            response=None,
        )

    def _ready_meter(self, budget=5.0):
        _seed(self.run_dir, {"max_budget_usd": budget})
        (self.run_dir / "gateway_spend.json").write_text(
            json.dumps({"spent_usd": 0.0})
        )
        meter = gateway.LoopMeteringGateway()
        meter.real_api_key = "sk-real-fixture"
        meter.run_dir = self.run_dir
        meter._load_contract()
        meter._load_persisted_spend()
        return meter

    def test_opus_48_exact_pricing_including_cache_usage(self):
        meter = self._ready_meter()
        flow = self._metered_flow()
        meter.request(flow)
        self.assertIsNone(flow.response)
        self.assertEqual(flow.request.headers["x-api-key"], "sk-real-fixture")
        self.assertEqual(flow.request.scheme, "https")
        self.assertEqual(flow.request.host, "api.anthropic.com")
        self.assertEqual(flow.request.port, 443)
        self.assertEqual(flow.request.headers["host"], "api.anthropic.com")
        flow.response = SimpleNamespace(
            status_code=200,
            content=json.dumps(
                {
                    "model": "claude-opus-4-8",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "cache_read_input_tokens": 10,
                        "cache_creation_input_tokens": 10,
                        "cache_creation": {
                            "ephemeral_5m_input_tokens": 4,
                            "ephemeral_1h_input_tokens": 6,
                        },
                    },
                }
            ).encode(),
        )
        meter.response(flow)
        expected = (
            100 * 5.00
            + 20 * 25.00
            + 10 * 0.50
            + 4 * 6.25
            + 6 * 10.00
        ) / 1_000_000
        self.assertAlmostEqual(meter.spent_usd, expected)
        self.assertEqual(
            json.loads((self.run_dir / "gateway_spend.json").read_text()),
            {"spent_usd": meter.spent_usd},
        )

    def test_unknown_model_and_worst_case_overshoot_block_before_upstream(self):
        meter = self._ready_meter()
        unknown = self._metered_flow(model="unknown-model")
        meter.request(unknown)
        self.assertEqual(unknown.response[0][0], 429)
        self.assertNotIn(unknown.id, meter.req_models)

        shutil.rmtree(self.run_dir)
        self.run_dir.mkdir(parents=True)
        meter = self._ready_meter(budget=0.001)
        overshoot = self._metered_flow(max_tokens=256)
        meter.request(overshoot)
        self.assertEqual(overshoot.response[0][0], 429)
        self.assertNotIn(overshoot.id, meter.req_models)

    def test_unknown_or_malformed_usage_fails_closed_and_poison_spend(self):
        invalid_usage = (
            {
                "input_tokens": 1,
                "output_tokens": 1,
                "unknown_usage": 1,
            },
            {
                "input_tokens": True,
                "output_tokens": 1,
            },
            {
                "input_tokens": 1,
                "output_tokens": 1,
                "cache_creation_input_tokens": 2,
            },
        )
        for usage in invalid_usage:
            with self.subTest(usage=usage):
                shutil.rmtree(self.run_dir)
                self.run_dir.mkdir(parents=True)
                meter = self._ready_meter()
                flow = self._metered_flow()
                meter.request(flow)
                self.assertIsNone(flow.response)
                flow.response = SimpleNamespace(
                    status_code=200,
                    content=json.dumps(
                        {"model": "claude-opus-4-8", "usage": usage}
                    ).encode(),
                )
                meter.response(flow)
                self.assertEqual(flow.response[0][0], 502)
                self.assertFalse(meter.persisted_spend_readable)
                poison = json.loads(
                    (self.run_dir / "gateway_spend.json").read_text()
                )
                self.assertEqual(set(poison), {"metering_error"})

    def test_missing_ambiguous_contract_and_run_key_mismatch_block(self):
        meter = gateway.LoopMeteringGateway()
        meter.real_api_key = "sk-real-fixture"
        meter.run_dir = self.run_dir
        meter._load_contract()
        missing = self._metered_flow()
        meter.request(missing)
        self.assertIsNotNone(missing.response)

        _seed(self.run_dir, {"max_budget_usd": 5.0})
        with (self.run_dir / "run.jsonl").open("a") as handle:
            handle.write(
                json.dumps(
                    {
                        "event": "loop_contract_locked",
                        "brakes": {"max_budget_usd": 5.0},
                    }
                )
                + "\n"
            )
        meter._load_contract()
        self.assertFalse(meter.contract_readable)

        shutil.rmtree(self.run_dir)
        self.run_dir.mkdir(parents=True)
        meter = self._ready_meter()
        mismatch = self._metered_flow()
        mismatch.request.headers["x-api-key"] = "sk-virtual-tropo-deadbeef"
        meter.request(mismatch)
        self.assertEqual(mismatch.response[0][0], 401)

    def test_ingress_host_and_upstream_path_are_exact_fail_closed(self):
        meter = self._ready_meter()
        for spoofed in (
            "api.anthropic.com.evil.example",
            "evil-api.anthropic.com",
            "localhost",
            "127.0.0.1.evil",
        ):
            with self.subTest(host=spoofed):
                flow = self._metered_flow()
                flow.request.pretty_host = spoofed
                meter.request(flow)
                self.assertEqual(flow.response[0][0], 421)
                self.assertNotIn(flow.id, meter.req_models)

        wrong_path = self._metered_flow()
        wrong_path.request.path = "/v1/complete"
        meter.request(wrong_path)
        self.assertEqual(wrong_path.response[0][0], 502)
        self.assertNotIn(wrong_path.id, meter.req_models)


class TestDistillerReservationBinding(unittest.TestCase):
    setUp = TestSpendBrake.setUp
    tearDown = TestSpendBrake.tearDown
    _reset_run_dir = TestSpendBrake._reset_run_dir
    _metered_flow = TestSpendBrake._metered_flow
    _ready_meter = TestSpendBrake._ready_meter

    def _policy(self, admission_mode="production"):
        production = admission_mode == "production"
        return DistillerModelPolicy(
            uid="0c938a95",
            version=POLICY_VERSION,
            status="active" if production else "draft",
            state="active",
            runner_name="distiller-model-edge",
            runner_uid="6389dcd4",
            routes={
                task: ModelRoute(task, model, ceiling)
                for task, (model, ceiling) in MODEL_ROUTES.items()
            },
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            segment_egress=(
                {"os": "auto", "team": "ask", "private": "ask"}
                if production
                else {"os": "ask", "team": "ask", "private": "ask"}
            ),
            consent_mode="auto" if production else "ask",
            egress_approved=production,
            production_enabled=production,
            disabled_reasons=() if production else ("policy is not active",),
            source_path=Path("vault/files/0c938a95.md"),
            index_path=Path("vault/00-index.jsonl"),
            canary_admissible=not production,
            canary_disabled_reasons=(
                ("production authority is not fully closed",)
                if production
                else ()
            ),
        )

    def _distiller_meter(self, admission_mode="production", budget=None):
        selected_budget = (
            0.26 if admission_mode == "canary" else 5.0
        ) if budget is None else budget
        _seed_distiller(self.run_dir, admission_mode, selected_budget)
        (self.run_dir / "gateway_spend.json").write_text(
            json.dumps({"spent_usd": 0.0})
        )
        meter = gateway.LoopMeteringGateway()
        meter.real_api_key = "sk-real-fixture"
        meter.run_dir = self.run_dir
        meter.daily_spend_root = self.root / "vault/loop-runs/.model-spend"
        meter.daily_spend_root.mkdir(parents=True, exist_ok=True)
        selected_policy = self._policy(admission_mode)
        meter.policy_resolver = lambda: selected_policy
        meter._load_contract()
        meter._load_persisted_spend()
        ledger = daily_spend._ledger_path(
            meter.daily_spend_root,
            DISTILLER_DAY,
            selected_policy.version,
        )
        if admission_mode == "canary" and selected_budget == 0.26:
            contract = metered_model.canary_run_events(RUN_UID)[1]
            contract_hash = metered_model.canary_contract_sha256(contract)
            claim_canary_authority(
                meter.daily_spend_root,
                policy=selected_policy,
                run_uid=RUN_UID,
                run_dir=self.run_dir,
                contract_sha256=contract_hash,
            )
            preparation = {
                "schema_version": 1,
                "status": "prepared",
                "policy_uid": selected_policy.uid,
                "policy_version": selected_policy.version,
                "runner_uid": selected_policy.runner_uid,
                "run_uid": RUN_UID,
                "contract_sha256": contract_hash,
                "request_sha256": metered_model.canary_request_hashes(),
                "admission_mode": "canary",
                "segment_classes": ["os"],
                "tasks": list(metered_model.CANARY_TASKS),
                "max_iterations": 2,
                "max_reserved_nano_usd": 260_000_000,
                "preparation_day": DISTILLER_DAY,
                "execution_ledger_required": True,
            }
            (self.run_dir / metered_model.CANARY_PREPARATION_NAME).write_text(
                json.dumps(preparation, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
            self.assertFalse(ledger.exists())
            self.assertFalse(
                (meter.daily_spend_root / f"{DISTILLER_DAY}.lock").exists()
            )
            meter._write_readiness_if_safe()
            self.assertTrue(
                (self.run_dir / metered_model.CANARY_READINESS_NAME).is_file()
            )
            self.assertFalse(ledger.exists())
            daily_spend.initialize_ledger(
                meter.daily_spend_root,
                policy_uid="0c938a95",
                policy_version=POLICY_VERSION,
                daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
                day=DISTILLER_DAY,
            )
            execution_receipt = metered_model.canary_execution_ledger_receipt(
                run_uid=RUN_UID,
                contract_sha256=contract_hash,
                preparation_day=DISTILLER_DAY,
                execution_day=DISTILLER_DAY,
                initial_ledger_sha256=hashlib.sha256(
                    ledger.read_bytes()
                ).hexdigest(),
            )
            (self.run_dir / metered_model.CANARY_EXECUTION_LEDGER_NAME).write_text(
                json.dumps(
                    execution_receipt,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
        elif not ledger.exists():
            daily_spend.initialize_ledger(
                meter.daily_spend_root,
                policy_uid="0c938a95",
                policy_version=POLICY_VERSION,
                daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
                day=DISTILLER_DAY,
            )
        return meter

    def _distiller_flow(
        self,
        reservation_id="a1b2c3d4",
        segment_classes=("os",),
        admission_mode="production",
        task="parse-query",
    ):
        model = {
            "parse-query": "claude-haiku-4-5-20251001",
            "distill": "claude-sonnet-4-6",
        }[task]
        if admission_mode == "canary":
            projection = metered_model.canary_request_projection(task)
            flow = self._metered_flow(
                model=model,
                max_tokens=projection["max_tokens"],
            )
            flow.request.content = json.dumps(
                projection,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        else:
            flow = self._metered_flow(model=model, max_tokens=32)
            projection = json.loads(
                llm.serialize_locked_request(
                    task,
                    [{"role": "user", "content": "{}"}],
                    max_tokens=32,
                )
            )
            flow.request.content = json.dumps(
                projection,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        flow.id = f"distiller-{reservation_id}"
        flow.request.headers.update(
            {
                "x-tropo-policy-uid": "0c938a95",
                "x-tropo-policy-version": POLICY_VERSION,
                "x-tropo-task": task,
                "x-tropo-model": model,
                "x-tropo-admission-mode": admission_mode,
                "x-tropo-day": DISTILLER_DAY,
                "x-tropo-reservation-id": reservation_id,
                "x-tropo-run-uid": RUN_UID,
                "x-tropo-segment-classes": ",".join(segment_classes),
            }
        )
        return flow

    def _reserve(self, meter, flow):
        request = json.loads(flow.request.content)
        task = flow.request.headers["x-tropo-task"]
        model = request["model"]
        amount = gateway.worst_case_request_cost_nano_usd(
            model,
            request_bytes=len(flow.request.content),
            max_tokens=request["max_tokens"],
            cache_mode="none",
        )
        daily_spend.reserve(
            meter.daily_spend_root,
            day=DISTILLER_DAY,
            policy_uid="0c938a95",
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            reservation_id=flow.request.headers["x-tropo-reservation-id"],
            run_uid=RUN_UID,
            task=task,
            model=model,
            segment_classes=tuple(
                flow.request.headers["x-tropo-segment-classes"].split(",")
            ),
            worst_case_nano_usd=amount,
        )

    def _replace_execution_receipt(self, meter, execution_day):
        ledger_path = daily_spend._ledger_path(
            meter.daily_spend_root,
            execution_day,
            POLICY_VERSION,
        )
        if not ledger_path.exists():
            daily_spend.initialize_ledger(
                meter.daily_spend_root,
                policy_uid="0c938a95",
                policy_version=POLICY_VERSION,
                daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
                day=execution_day,
            )
        preparation = json.loads(
            (self.run_dir / metered_model.CANARY_PREPARATION_NAME).read_text()
        )
        receipt = metered_model.canary_execution_ledger_receipt(
            run_uid=RUN_UID,
            contract_sha256=preparation["contract_sha256"],
            preparation_day=preparation["preparation_day"],
            execution_day=execution_day,
            initial_ledger_sha256=hashlib.sha256(
                ledger_path.read_bytes()
            ).hexdigest(),
        )
        (self.run_dir / metered_model.CANARY_EXECUTION_LEDGER_NAME).write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
        )
        return receipt

    def _assert_reservation_stays_unclaimed(self, meter, reservation_id):
        record = daily_spend.read_ledger(
            meter.daily_spend_root,
            day=DISTILLER_DAY,
            policy_version=POLICY_VERSION,
        )["reservations"][reservation_id]
        self.assertEqual(record["status"], "reserved")
        self.assertIsNone(record["gateway_request_id"])

    def _assert_distiller_flow_refused_before_upstream(self, meter, flow):
        original_key = flow.request.headers["x-api-key"]
        with mock.patch.object(
            meter,
            "_route_upstream",
            wraps=meter._route_upstream,
        ) as route:
            meter.request(flow)
        route.assert_not_called()
        self.assertEqual(flow.response[0][0], 429)
        self.assertEqual(flow.request.headers["x-api-key"], original_key)
        self.assertNotIn(flow.id, meter.req_models)

    def test_valid_binding_claims_once_before_real_key_upstream(self):
        meter = self._distiller_meter()
        flow = self._distiller_flow()
        body = json.loads(flow.request.content)
        self.assertEqual(body["service_tier"], "standard_only")
        self.assertNotIn("inference_geo", body)
        self._reserve(meter, flow)
        meter.request(flow)
        self.assertIsNone(flow.response)
        self.assertEqual(flow.request.headers["x-api-key"], "sk-real-fixture")
        record = daily_spend.read_ledger(
            meter.daily_spend_root,
            day=DISTILLER_DAY,
            policy_version=POLICY_VERSION,
        )["reservations"]["a1b2c3d4"]
        self.assertEqual(record["status"], "claimed")
        self.assertEqual(record["gateway_request_id"], flow.id)

        replay = self._distiller_flow()
        replay.id = "distiller-replay-a1b2c3d4"
        meter.request(replay)
        self.assertEqual(replay.response[0][0], 429)
        self.assertEqual(replay.request.headers["x-api-key"], VIRTUAL_KEY)
        self.assertNotIn(replay.id, meter.req_models)

    def test_canary_uses_separate_policy_gate_and_exact_os_contract(self):
        meter = self._distiller_meter("canary")
        self.assertFalse(meter.policy_resolver().production_enabled)
        self.assertTrue(meter.policy_resolver().canary_admissible)
        flow = self._distiller_flow(admission_mode="canary")
        self.assertNotIn("inference_geo", json.loads(flow.request.content))
        self._reserve(meter, flow)
        meter.request(flow)
        self.assertIsNone(flow.response)
        self.assertEqual(flow.request.headers["x-api-key"], "sk-real-fixture")
        record = daily_spend.read_ledger(
            meter.daily_spend_root,
            day=DISTILLER_DAY,
            policy_version=POLICY_VERSION,
        )["reservations"]["a1b2c3d4"]
        self.assertEqual(record["status"], "claimed")

        distill = self._distiller_flow(
            "a1b2c3d5",
            admission_mode="canary",
            task="distill",
        )
        self.assertEqual(
            json.loads(distill.request.content)["inference_geo"],
            "global",
        )
        self._reserve(meter, distill)
        meter.request(distill)
        self.assertIsNone(distill.response)
        self.assertEqual(
            daily_spend.read_ledger(
                meter.daily_spend_root,
                day=DISTILLER_DAY,
                policy_version=POLICY_VERSION,
            )["reservations"]["a1b2c3d5"]["status"],
            "claimed",
        )

    def test_canary_stale_d1_receipt_cannot_claim_current_d2_reservation(self):
        meter = self._distiller_meter("canary")
        stale_day = (
            date.fromisoformat(DISTILLER_DAY) - timedelta(days=1)
        ).isoformat()
        stale_receipt = self._replace_execution_receipt(meter, stale_day)
        self.assertEqual(
            meter._validate_distiller_contract(
                meter.policy_resolver(),
                "canary",
            ),
            stale_receipt,
        )
        flow = self._distiller_flow(
            "d1000001",
            admission_mode="canary",
        )
        self._reserve(meter, flow)

        self._assert_distiller_flow_refused_before_upstream(meter, flow)
        self._assert_reservation_stays_unclaimed(meter, "d1000001")

    def test_canary_future_receipt_refuses_before_claim_or_upstream(self):
        meter = self._distiller_meter("canary")
        future_day = (
            date.fromisoformat(DISTILLER_DAY) + timedelta(days=1)
        ).isoformat()
        future_receipt = self._replace_execution_receipt(meter, future_day)
        self.assertEqual(
            meter._validate_distiller_contract(
                meter.policy_resolver(),
                "canary",
            ),
            future_receipt,
        )
        flow = self._distiller_flow(
            "d1000002",
            admission_mode="canary",
        )
        self._reserve(meter, flow)

        self._assert_distiller_flow_refused_before_upstream(meter, flow)
        self._assert_reservation_stays_unclaimed(meter, "d1000002")

    def test_canary_header_day_drift_refuses_before_claim_or_upstream(self):
        meter = self._distiller_meter("canary")
        flow = self._distiller_flow(
            "d1000003",
            admission_mode="canary",
        )
        self._reserve(meter, flow)
        flow.request.headers["x-tropo-day"] = (
            date.fromisoformat(DISTILLER_DAY) - timedelta(days=1)
        ).isoformat()

        self._assert_distiller_flow_refused_before_upstream(meter, flow)
        self._assert_reservation_stays_unclaimed(meter, "d1000003")

    def test_canary_exact_same_day_receipt_claims_then_routes(self):
        meter = self._distiller_meter("canary")
        receipt = meter._validate_distiller_contract(
            meter.policy_resolver(),
            "canary",
        )
        self.assertEqual(receipt["execution_day"], DISTILLER_DAY)
        flow = self._distiller_flow(
            "d1000004",
            admission_mode="canary",
        )
        self._reserve(meter, flow)

        with mock.patch.object(
            meter,
            "_route_upstream",
            wraps=meter._route_upstream,
        ) as route:
            meter.request(flow)

        route.assert_called_once_with(flow)
        self.assertIsNone(flow.response)
        self.assertEqual(flow.request.headers["x-api-key"], "sk-real-fixture")
        self.assertIn(flow.id, meter.req_models)
        record = daily_spend.read_ledger(
            meter.daily_spend_root,
            day=DISTILLER_DAY,
            policy_version=POLICY_VERSION,
        )["reservations"]["d1000004"]
        self.assertEqual(record["status"], "claimed")
        self.assertEqual(record["gateway_request_id"], flow.id)

    def test_canary_team_private_mixed_and_second_task_replay_refuse(self):
        for index, segments in enumerate(
            (("team",), ("private",), ("os", "team")),
            1,
        ):
            with self.subTest(segments=segments):
                if index > 1:
                    self._reset_run_dir()
                meter = self._distiller_meter("canary")
                reservation_id = f"c{index:07x}"
                flow = self._distiller_flow(
                    reservation_id,
                    segments,
                    admission_mode="canary",
                )
                self._reserve(meter, flow)
                meter.request(flow)
                self.assertEqual(flow.response[0][0], 429)
                self.assertEqual(flow.request.headers["x-api-key"], VIRTUAL_KEY)
                self.assertNotIn(flow.id, meter.req_models)

        self._reset_run_dir()
        meter = self._distiller_meter("canary")
        first = self._distiller_flow("c1000001", admission_mode="canary")
        self._reserve(meter, first)
        meter.request(first)
        self.assertIsNone(first.response)
        duplicate = self._distiller_flow(
            "c1000002",
            admission_mode="canary",
        )
        self._reserve(meter, duplicate)
        meter.request(duplicate)
        self.assertEqual(duplicate.response[0][0], 429)
        self.assertEqual(duplicate.request.headers["x-api-key"], VIRTUAL_KEY)

    def test_canary_policy_attestation_and_contract_drift_refuse(self):
        meter = self._distiller_meter("canary")
        passed = replace(
            self._policy("canary"),
            canary_admissible=False,
            canary_disabled_reasons=(
                "a passed metered canary is already recorded",
            ),
        )
        meter.policy_resolver = lambda: passed
        flow = self._distiller_flow(admission_mode="canary")
        self._reserve(meter, flow)
        meter.request(flow)
        self.assertEqual(flow.response[0][0], 429)
        self.assertEqual(flow.request.headers["x-api-key"], VIRTUAL_KEY)

        mutations = (
            lambda contract: contract.__setitem__("loop_version", "1.2.1"),
            lambda contract: contract.__setitem__("admission_mode", "production"),
            lambda contract: contract.__setitem__(
                "segment_classes", ["os", "team"]
            ),
            lambda contract: contract.__setitem__(
                "tasks", ["distill", "parse-query"]
            ),
            lambda contract: contract["policy"].__setitem__(
                "ref", "deadbeef"
            ),
            lambda contract: contract["brakes"].__setitem__(
                "max_budget_usd", 0.27
            ),
            lambda contract: contract["brakes"].__setitem__(
                "max_iterations", 3
            ),
            lambda contract: contract.__setitem__("override", True),
        )
        for index, mutation in enumerate(mutations, 1):
            with self.subTest(mutation=mutation):
                self._reset_run_dir()
                meter = self._distiller_meter("canary")
                mutation(meter.loop_contract)
                flow = self._distiller_flow(
                    f"d{index:07x}",
                    admission_mode="canary",
                )
                self._reserve(meter, flow)
                meter.request(flow)
                self.assertEqual(flow.response[0][0], 429)
                self.assertEqual(flow.request.headers["x-api-key"], VIRTUAL_KEY)
                self.assertNotIn(flow.id, meter.req_models)

    def test_canary_arbitrary_request_content_and_contract_hash_refuse(self):
        meter = self._distiller_meter("canary")
        arbitrary = self._distiller_flow(
            "e1000001",
            admission_mode="canary",
        )
        body = json.loads(arbitrary.request.content)
        body["messages"][0]["content"] = "caller-authored OS label"
        arbitrary.request.content = json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self._reserve(meter, arbitrary)
        meter.request(arbitrary)
        self.assertEqual(arbitrary.response[0][0], 429)
        self.assertEqual(arbitrary.request.headers["x-api-key"], VIRTUAL_KEY)
        self.assertNotIn(arbitrary.id, meter.req_models)

        self._reset_run_dir()
        meter = self._distiller_meter("canary")
        meter.loop_contract["request_sha256"]["parse-query"] = "a" * 64
        forged = self._distiller_flow(
            "e1000002",
            admission_mode="canary",
        )
        self._reserve(meter, forged)
        meter.request(forged)
        self.assertEqual(forged.response[0][0], 429)
        self.assertEqual(forged.request.headers["x-api-key"], VIRTUAL_KEY)
        self.assertNotIn(forged.id, meter.req_models)

    def test_locked_request_control_drift_refuses_before_upstream(self):
        cases = (
            ("parse-query", lambda body: body.pop("service_tier")),
            (
                "parse-query",
                lambda body: body.__setitem__("service_tier", "priority"),
            ),
            (
                "parse-query",
                lambda body: body.__setitem__("inference_geo", "global"),
            ),
            ("distill", lambda body: body.pop("service_tier")),
            (
                "distill",
                lambda body: body.__setitem__("service_tier", "priority"),
            ),
            ("distill", lambda body: body.pop("inference_geo")),
            (
                "distill",
                lambda body: body.__setitem__("inference_geo", "us"),
            ),
            ("distill", lambda body: body.__setitem__("override", True)),
        )
        for index, (task, mutation) in enumerate(cases, 1):
            with self.subTest(index=index, task=task):
                if index > 1:
                    self._reset_run_dir()
                meter = self._distiller_meter("canary")
                flow = self._distiller_flow(
                    f"e11{index:05x}",
                    admission_mode="canary",
                    task=task,
                )
                self._reserve(meter, flow)
                body = json.loads(flow.request.content)
                mutation(body)
                flow.request.content = json.dumps(
                    body,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                self._assert_distiller_flow_refused_before_upstream(meter, flow)

    def test_short_haiku_alias_request_refuses_before_upstream(self):
        meter = self._distiller_meter("canary")
        flow = self._distiller_flow(
            "e1500001",
            admission_mode="canary",
        )
        self._reserve(meter, flow)
        body = json.loads(flow.request.content)
        body["model"] = "claude-haiku-4-5"
        flow.request.content = json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        flow.request.headers["x-tropo-model"] = "claude-haiku-4-5"
        self._assert_distiller_flow_refused_before_upstream(meter, flow)

    def test_v11_and_malformed_gateway_attempts_never_claim_or_reach_upstream(self):
        meter = self._distiller_meter()
        daily_spend.initialize_ledger(
            meter.daily_spend_root,
            policy_uid="0c938a95",
            policy_version="1.1.0",
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            day=DISTILLER_DAY,
        )
        daily_spend.reserve(
            meter.daily_spend_root,
            day=DISTILLER_DAY,
            policy_uid="0c938a95",
            policy_version="1.1.0",
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            reservation_id="e1600001",
            run_uid=RUN_UID,
            task="parse-query",
            model="claude-haiku-4-5-20251001",
            segment_classes=("os",),
            worst_case_nano_usd=10_000_000,
        )
        events = [
            json.loads(line)
            for line in (self.run_dir / "run.jsonl").read_text().splitlines()
        ]
        for event in events:
            event["loop_version"] = "1.1.0"
        (self.run_dir / "run.jsonl").write_text(
            "".join(
                json.dumps(event, sort_keys=True, separators=(",", ":"))
                + "\n"
                for event in events
            )
        )
        meter._load_contract()
        legacy_path = daily_spend._ledger_path(
            meter.daily_spend_root,
            DISTILLER_DAY,
            "1.1.0",
        )
        legacy_before = legacy_path.read_bytes()
        current_path = daily_spend._ledger_path(
            meter.daily_spend_root,
            DISTILLER_DAY,
            POLICY_VERSION,
        )
        current_before = current_path.read_bytes()

        cases = (
            ("all-v11", "1.1.0"),
            ("v11-run-current-header", POLICY_VERSION),
            ("malformed-version", "1.1"),
            ("missing-version", None),
        )
        with mock.patch.object(
            daily_spend,
            "claim_reservation",
            wraps=daily_spend.claim_reservation,
        ) as claim:
            for label, header_version in cases:
                with self.subTest(label=label):
                    flow = self._distiller_flow(
                        "e1600001",
                        admission_mode="production",
                    )
                    flow.id = f"legacy-{label}"
                    if header_version is None:
                        flow.request.headers.pop(
                            "x-tropo-policy-version",
                            None,
                        )
                    else:
                        flow.request.headers[
                            "x-tropo-policy-version"
                        ] = header_version
                    self._assert_distiller_flow_refused_before_upstream(
                        meter,
                        flow,
                    )
            claim.assert_not_called()

        legacy = daily_spend.read_ledger(
            meter.daily_spend_root,
            day=DISTILLER_DAY,
            policy_uid="0c938a95",
            policy_version="1.1.0",
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
        )
        self.assertEqual(
            legacy["reservations"]["e1600001"]["status"],
            "reserved",
        )
        self.assertEqual(legacy_path.read_bytes(), legacy_before)
        self.assertEqual(current_path.read_bytes(), current_before)

    def test_canary_receipts_preserve_arbitrary_geo_and_price_sonnet_us_exactly(self):
        meter = self._distiller_meter("canary")
        arbitrary_geo = "EU West / 東京?! #1"
        usage = {
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "service_tier": "standard",
            "inference_geo": "global",
            "output_tokens_details": {"thinking_tokens": 0},
            "server_tool_use": {
                "web_search_requests": 0,
                "web_fetch_requests": 0,
            },
        }
        fixtures = (
            (
                "parse-query",
                "e2000001",
                "claude-haiku-4-5-20251001",
                '```json\n{"uids":["0c938a95"]}\n```',
            ),
            (
                "distill",
                "e2000002",
                "claude-sonnet-4-6",
                (
                    '{"selections":[{"source_uid":"0c938a95",'
                    '"span_anchor":"frontmatter:uid=0c938a95",'
                    '"reorder_note":null}]}'
                ),
            ),
        )
        expected = []
        for task, reservation_id, model, text in fixtures:
            response_usage = {
                **usage,
                "inference_geo": arbitrary_geo if task == "parse-query" else "us",
            }
            flow = self._distiller_flow(
                reservation_id,
                admission_mode="canary",
                task=task,
            )
            body = json.loads(flow.request.content)
            if task == "parse-query":
                self.assertNotIn("inference_geo", body)
            else:
                self.assertEqual(body["inference_geo"], "global")
            self._reserve(meter, flow)
            meter.request(flow)
            self.assertIsNone(flow.response)
            flow.response = SimpleNamespace(
                status_code=200,
                content=json.dumps(
                    {
                        "model": model,
                        "content": [{"type": "text", "text": text}],
                        "usage": response_usage,
                    }
                ).encode(),
            )
            meter.response(flow)
            self.assertEqual(flow.response.status_code, 200)
            expected.append(
                {
                    "reservation_id": reservation_id,
                    "task": task,
                    "model": model,
                    "actual_nano_usd": gateway.price_locked_usage_nano_usd(
                        model,
                        response_usage,
                        task=task,
                    ),
                    "response_sha256": __import__("hashlib").sha256(
                        text.encode()
                    ).hexdigest(),
                    "response_text": text,
                    "service_tier": "standard",
                    "inference_geo": response_usage["inference_geo"],
                }
            )
        receipt_path = (
            self.run_dir
            / metered_model.CANARY_GATEWAY_RECEIPTS_NAME
        )
        receipt_bytes = receipt_path.read_bytes()
        surface = json.loads(receipt_bytes)
        self.assertEqual(
            surface["receipts"],
            expected,
        )

    def test_canary_receipt_tier_geo_schema_tampering_refuses(self):
        mutations = (
            lambda receipt: receipt.pop("service_tier"),
            lambda receipt: receipt.pop("inference_geo"),
            lambda receipt: receipt.pop("response_text"),
            lambda receipt: receipt.__setitem__("extra", True),
            lambda receipt: receipt.__setitem__("service_tier", "priority"),
            lambda receipt: receipt.__setitem__("inference_geo", ""),
            lambda receipt: receipt.__setitem__(
                "inference_geo",
                "x" * (loop_metering.INFERENCE_GEO_MAX_LENGTH + 1),
            ),
            lambda receipt: receipt.__setitem__("inference_geo", 7),
            lambda receipt: receipt.__setitem__("response_text", '{"uids":[]}'),
            lambda receipt: receipt.__setitem__("response_text", 7),
            lambda receipt: receipt.__setitem__("response_sha256", "a" * 64),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                if index:
                    self._reset_run_dir()
                meter = self._distiller_meter("canary")
                selected_policy = meter.policy_resolver()
                contract_hash = meter._canary_contract_hash(selected_policy)
                path = (
                    self.run_dir
                    / metered_model.CANARY_GATEWAY_RECEIPTS_NAME
                )
                surface = json.loads(path.read_text())
                response_text = '{"uids":["0c938a95"]}'
                receipt = {
                    "reservation_id": "e2200001",
                    "task": "parse-query",
                    "model": "claude-haiku-4-5-20251001",
                    "actual_nano_usd": 1,
                    "response_sha256": __import__("hashlib").sha256(
                        response_text.encode()
                    ).hexdigest(),
                    "response_text": response_text,
                    "service_tier": "standard",
                    "inference_geo": "eu-west_1",
                }
                mutation(receipt)
                surface["receipts"] = [receipt]
                path.write_text(
                    json.dumps(surface, sort_keys=True, separators=(",", ":"))
                    + "\n"
                )
                with self.assertRaisesRegex(
                    gateway.MeteringContractError,
                    "receipt",
                ):
                    meter._verify_readiness(selected_policy, contract_hash)

    def test_sonnet_us_response_uses_exact_eleven_tenths_gateway_price(self):
        meter = self._distiller_meter("canary")
        base_usage = {
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "service_tier": "standard",
        }
        parse = self._distiller_flow(
            "e2100001",
            admission_mode="canary",
            task="parse-query",
        )
        self._reserve(meter, parse)
        meter.request(parse)
        parse.response = SimpleNamespace(
            status_code=200,
            content=json.dumps(
                {
                    "model": "claude-haiku-4-5-20251001",
                    "content": [
                        {"type": "text", "text": '{"uids":["0c938a95"]}'}
                    ],
                    "usage": {**base_usage, "inference_geo": "us"},
                }
            ).encode(),
        )
        meter.response(parse)
        self.assertEqual(parse.response.status_code, 200)

        distill = self._distiller_flow(
            "e2100002",
            admission_mode="canary",
            task="distill",
        )
        self._reserve(meter, distill)
        meter.request(distill)
        distill.response = SimpleNamespace(
            status_code=200,
            content=json.dumps(
                {
                    "model": "claude-sonnet-4-6",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                '{"selections":[{"source_uid":"0c938a95",'
                                '"span_anchor":"frontmatter:uid=0c938a95",'
                                '"reorder_note":null}]}'
                            ),
                        }
                    ],
                    "usage": {**base_usage, "inference_geo": "us"},
                }
            ).encode(),
        )
        meter.response(distill)
        self.assertEqual(distill.response.status_code, 200)
        ledger = daily_spend.read_ledger(
            meter.daily_spend_root,
            day=DISTILLER_DAY,
            policy_version=POLICY_VERSION,
        )
        self.assertEqual(
            ledger["reservations"]["e2100002"]["status"],
            "claimed",
        )
        self.assertEqual(
            json.loads(
                (
                    self.run_dir
                    / metered_model.CANARY_GATEWAY_RECEIPTS_NAME
                ).read_text()
            )["receipts"][1],
            {
                "reservation_id": "e2100002",
                "task": "distill",
                "model": "claude-sonnet-4-6",
                "actual_nano_usd": 66_000,
                "response_sha256": __import__("hashlib").sha256(
                    (
                        '{"selections":[{"source_uid":"0c938a95",'
                        '"span_anchor":"frontmatter:uid=0c938a95",'
                        '"reorder_note":null}]}'
                    ).encode()
                ).hexdigest(),
                "response_text": (
                    '{"selections":[{"source_uid":"0c938a95",'
                    '"span_anchor":"frontmatter:uid=0c938a95",'
                    '"reorder_note":null}]}'
                ),
                "service_tier": "standard",
                "inference_geo": "us",
            },
        )

    def test_canary_response_usage_drift_refuses_exact_metering(self):
        base = {
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "service_tier": "standard",
            "inference_geo": "global",
        }
        invalid = []
        for field, value in (
            ("service_tier", "priority"),
            ("service_tier", "batch"),
            ("inference_geo", ""),
            (
                "inference_geo",
                "a" * (loop_metering.INFERENCE_GEO_MAX_LENGTH + 1),
            ),
            ("inference_geo", 7),
        ):
            candidate = dict(base)
            candidate[field] = value
            invalid.append(candidate)
        for missing in ("service_tier", "inference_geo"):
            candidate = dict(base)
            candidate.pop(missing)
            invalid.append(candidate)
        invalid.extend(
            (
                {**base, "output_tokens_details": {"thinking_tokens": 1}},
                {**base, "output_tokens_details": {"thinking_tokens": 0, "extra": 0}},
                {
                    **base,
                    "server_tool_use": {
                        "web_search_requests": 1,
                        "web_fetch_requests": 0,
                    },
                },
                {
                    **base,
                    "server_tool_use": {
                        "web_search_requests": 0,
                        "web_fetch_requests": 1,
                    },
                },
                {**base, "server_tool_use": {"web_search_requests": 0}},
                {**base, "unknown": 0},
            )
        )
        for index, usage in enumerate(invalid, 1):
            with self.subTest(usage=usage):
                if index > 1:
                    self._reset_run_dir()
                meter = self._distiller_meter("canary")
                flow = self._distiller_flow(
                    f"a{index:07x}",
                    admission_mode="canary",
                )
                self._reserve(meter, flow)
                meter.request(flow)
                self.assertIsNone(flow.response)
                flow.response = SimpleNamespace(
                    status_code=200,
                    content=json.dumps(
                        {
                            "model": "claude-haiku-4-5-20251001",
                            "content": [
                                {
                                    "type": "text",
                                    "text": '{"uids":["0c938a95"]}',
                                }
                            ],
                            "usage": usage,
                        }
                    ).encode(),
                )
                meter.response(flow)
                self.assertEqual(flow.response[0][0], 502)
                ledger = daily_spend.read_ledger(
                    meter.daily_spend_root,
                    day=DISTILLER_DAY,
                    policy_version=POLICY_VERSION,
                )
                self.assertEqual(
                    ledger["reservations"][f"a{index:07x}"]["status"],
                    "claimed",
                )

    def test_short_haiku_alias_response_poison_refuses_accepted_metering(self):
        meter = self._distiller_meter("canary")
        flow = self._distiller_flow(
            "e2200001",
            admission_mode="canary",
        )
        self._reserve(meter, flow)
        meter.request(flow)
        self.assertIsNone(flow.response)
        flow.response = SimpleNamespace(
            status_code=200,
            content=json.dumps(
                {
                    "model": "claude-haiku-4-5",
                    "content": [
                        {"type": "text", "text": '{"uids":["0c938a95"]}'}
                    ],
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 2,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                }
            ).encode(),
        )
        meter.response(flow)
        self.assertEqual(flow.response[0][0], 502)
        self.assertEqual(
            set(
                json.loads(
                    (self.run_dir / "gateway_spend.json").read_text()
                )
            ),
            {"metering_error"},
        )

    def test_gateway_missing_readiness_refuses_before_upstream(self):
        meter = self._distiller_meter("canary")
        (self.run_dir / metered_model.CANARY_READINESS_NAME).unlink()
        flow = self._distiller_flow(
            "e2500001",
            admission_mode="canary",
        )
        self._reserve(meter, flow)
        meter.request(flow)
        self.assertEqual(flow.response[0][0], 429)
        self.assertEqual(flow.request.headers["x-api-key"], VIRTUAL_KEY)
        self.assertNotIn(flow.id, meter.req_models)

    def test_gateway_readiness_requires_exact_preparation_without_v17_ledger(self):
        meter = self._distiller_meter("canary")
        ledger_path = daily_spend._ledger_path(
            meter.daily_spend_root,
            DISTILLER_DAY,
            POLICY_VERSION,
        )
        ledger_path.unlink()
        (self.run_dir / metered_model.CANARY_EXECUTION_LEDGER_NAME).unlink()
        (self.run_dir / metered_model.CANARY_READINESS_NAME).unlink()
        (self.run_dir / metered_model.CANARY_GATEWAY_RECEIPTS_NAME).unlink()
        preparation_path = self.run_dir / metered_model.CANARY_PREPARATION_NAME
        preparation = json.loads(preparation_path.read_text())
        preparation["unexpected"] = True
        preparation_path.write_text(
            json.dumps(preparation, sort_keys=True, separators=(",", ":")) + "\n"
        )

        with self.assertRaisesRegex(
            gateway.MeteringContractError,
            "preparation receipt drifted",
        ):
            meter._write_readiness_if_safe()
        self.assertFalse(ledger_path.exists())
        self.assertFalse(
            (self.run_dir / metered_model.CANARY_READINESS_NAME).exists()
        )
        self.assertFalse(
            (self.run_dir / metered_model.CANARY_GATEWAY_RECEIPTS_NAME).exists()
        )

    def test_gateway_writes_no_readiness_without_real_key(self):
        _seed_distiller(self.run_dir, "canary", 0.26)
        (self.run_dir / "gateway_spend.json").write_text('{"spent_usd":0.0}')
        meter = gateway.LoopMeteringGateway()
        meter.real_api_key = ""
        meter.run_dir = self.run_dir
        meter.daily_spend_root = self.root / "vault/loop-runs/.model-spend"
        meter.daily_spend_root.mkdir(parents=True)
        selected_policy = self._policy("canary")
        meter.policy_resolver = lambda: selected_policy
        daily_spend.initialize_ledger(
            meter.daily_spend_root,
            policy_uid="0c938a95",
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            day=DISTILLER_DAY,
        )
        locked = metered_model.canary_run_events(RUN_UID)[1]
        claim_canary_authority(
            meter.daily_spend_root,
            policy=selected_policy,
            run_uid=RUN_UID,
            run_dir=self.run_dir,
            contract_sha256=metered_model.canary_contract_sha256(locked),
        )
        meter._load_contract()
        meter._load_persisted_spend()
        with self.assertRaisesRegex(Exception, "real key"):
            meter._write_readiness_if_safe()
        self.assertFalse(
            (self.run_dir / metered_model.CANARY_READINESS_NAME).exists()
        )

    def test_gateway_refuses_combined_canary_reservation_over_nano_cap(self):
        meter = self._distiller_meter("canary")
        first = self._distiller_flow(
            "e3000001",
            admission_mode="canary",
        )
        daily_spend.reserve(
            meter.daily_spend_root,
            day=DISTILLER_DAY,
            policy_uid="0c938a95",
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            reservation_id="e3000001",
            run_uid=RUN_UID,
            task="parse-query",
            model="claude-haiku-4-5-20251001",
            segment_classes=("os",),
            worst_case_nano_usd=259_999_999,
        )
        meter.request(first)
        self.assertIsNone(first.response)

        second = self._distiller_flow(
            "e3000002",
            admission_mode="canary",
            task="distill",
        )
        self._reserve(meter, second)
        meter.request(second)
        self.assertEqual(second.response[0][0], 429)
        self.assertEqual(second.request.headers["x-api-key"], VIRTUAL_KEY)
        self.assertNotIn(second.id, meter.req_models)

    def test_segment_scoped_consent_refuses_ask_and_mixed_classes(self):
        for index, segments in enumerate(
            (("team",), ("private",), ("os", "team")),
            1,
        ):
            with self.subTest(segments=segments):
                if index > 1:
                    shutil.rmtree(self.run_dir)
                    self.run_dir.mkdir(parents=True)
                meter = self._distiller_meter()
                reservation_id = f"b{index:07x}"
                flow = self._distiller_flow(reservation_id, segments)
                self._reserve(meter, flow)
                original_key = flow.request.headers["x-api-key"]
                meter.request(flow)
                self.assertEqual(flow.response[0][0], 429)
                self.assertEqual(flow.request.headers["x-api-key"], original_key)
                self.assertNotIn(flow.id, meter.req_models)
                record = daily_spend.read_ledger(
                    meter.daily_spend_root,
                    day=DISTILLER_DAY,
                    policy_version=POLICY_VERSION,
                )["reservations"][reservation_id]
                self.assertEqual(record["status"], "reserved")

    def test_each_policy_task_model_day_run_and_segment_mismatch_refuses(self):
        mutations = (
            ("x-tropo-policy-uid", "deadbeef"),
            ("x-tropo-policy-version", "1.2.1"),
            ("x-tropo-task", "distill"),
            ("x-tropo-model", "claude-sonnet-4-6"),
            ("x-tropo-admission-mode", "canary"),
            ("x-tropo-day", "2026-07-22"),
            ("x-tropo-run-uid", "deadbeef"),
            ("x-tropo-segment-classes", "team"),
            ("x-tropo-reservation-id", "deadbeef"),
        )
        for index, (field, value) in enumerate(mutations, 1):
            with self.subTest(field=field):
                shutil.rmtree(self.run_dir)
                self.run_dir.mkdir(parents=True)
                meter = self._distiller_meter()
                flow = self._distiller_flow(f"{index:08x}")
                self._reserve(meter, flow)
                flow.request.headers[field] = value
                original_key = flow.request.headers["x-api-key"]
                meter.request(flow)
                self.assertEqual(flow.response[0][0], 429)
                self.assertEqual(flow.request.headers["x-api-key"], original_key)
                self.assertNotIn(flow.id, meter.req_models)

    def test_partial_headers_and_under_reserved_request_refuse(self):
        meter = self._distiller_meter()
        headerless = self._metered_flow(
            model="claude-haiku-4-5-20251001",
            max_tokens=32,
        )
        meter.policy_resolver = mock.Mock(side_effect=meter.policy_resolver)
        meter.request(headerless)
        self.assertEqual(headerless.response[0][0], 429)
        self.assertEqual(headerless.request.headers["x-api-key"], VIRTUAL_KEY)
        self.assertNotIn(headerless.id, meter.req_models)
        meter.policy_resolver.assert_not_called()

        partial = self._metered_flow(
            model="claude-haiku-4-5-20251001",
            max_tokens=32,
        )
        partial.request.headers["x-tropo-task"] = "parse-query"
        meter.request(partial)
        self.assertEqual(partial.response[0][0], 429)
        self.assertEqual(partial.request.headers["x-api-key"], VIRTUAL_KEY)
        self.assertNotIn(partial.id, meter.req_models)

        self._reset_run_dir()
        canary_meter = self._distiller_meter("canary")
        canary_headerless = self._distiller_flow(admission_mode="canary")
        for name in gateway.METERING_HEADERS:
            canary_headerless.request.headers.pop(name, None)
        canary_meter.request(canary_headerless)
        self.assertEqual(canary_headerless.response[0][0], 429)
        self.assertEqual(
            canary_headerless.request.headers["x-api-key"],
            VIRTUAL_KEY,
        )
        self.assertNotIn(canary_headerless.id, canary_meter.req_models)

        under = self._distiller_flow("deadbeef")
        daily_spend.reserve(
            meter.daily_spend_root,
            day=DISTILLER_DAY,
            policy_uid="0c938a95",
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            reservation_id="deadbeef",
            run_uid=RUN_UID,
            task="parse-query",
            model="claude-haiku-4-5-20251001",
            segment_classes=("os",),
            worst_case_nano_usd=1,
        )
        meter.request(under)
        self.assertEqual(under.response[0][0], 429)
        self.assertEqual(under.request.headers["x-api-key"], VIRTUAL_KEY)

    def test_malformed_distiller_identity_never_falls_back_to_generic_routing(self):
        mutations = (
            (
                "missing-admission",
                lambda meter: meter.loop_contract.pop("admission_mode"),
            ),
            (
                "invalid-admission",
                lambda meter: meter.loop_contract.__setitem__(
                    "admission_mode",
                    "preview",
                ),
            ),
            (
                "only-run-created",
                lambda meter: meter.loop_contract.pop("loop"),
            ),
            (
                "only-loop-contract",
                lambda meter: meter.run_created.pop("loop"),
            ),
            (
                "disagreeing-loop-ids",
                lambda meter: meter.loop_contract.__setitem__(
                    "loop",
                    "deadbeef",
                ),
            ),
        )
        for index, (label, mutation) in enumerate(mutations, 1):
            with self.subTest(label=label):
                if index > 1:
                    self._reset_run_dir()
                meter = self._distiller_meter()
                mutation(meter)

                headerless = self._metered_flow(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=32,
                )
                headerless.id = f"malformed-headerless-{index}"
                self._assert_distiller_flow_refused_before_upstream(
                    meter,
                    headerless,
                )

                complete = self._distiller_flow(
                    f"f{index:07x}",
                    admission_mode="production",
                )
                complete.id = f"malformed-complete-{index}"
                self._assert_distiller_flow_refused_before_upstream(
                    meter,
                    complete,
                )

    def test_partial_distiller_markers_force_all_flows_fail_closed(self):
        def remove_distiller_markers(meter):
            meter.run_created.pop("loop", None)
            meter.loop_contract.pop("loop", None)
            for field in (
                "policy",
                "admission_mode",
                "tasks",
                "request_sha256",
                "segment_classes",
            ):
                meter.loop_contract.pop(field, None)

        def policy_and_admission(meter):
            meter.run_created.pop("loop", None)
            meter.loop_contract.pop("loop", None)

        def policy_only(meter):
            meter.run_created.pop("loop", None)
            meter.loop_contract.pop("loop", None)
            meter.loop_contract.pop("admission_mode", None)

        def artifact_only(meter):
            remove_distiller_markers(meter)
            (meter.run_dir / metered_model.CANARY_PREPARATION_NAME).write_text(
                "{}\n"
            )

        def task_only(meter, task):
            remove_distiller_markers(meter)
            meter.loop_contract["tasks"] = [task]

        def one_hash(meter):
            remove_distiller_markers(meter)
            meter.loop_contract["request_sha256"] = {"parse-query": "not-a-hash"}

        def partial_segment(meter):
            remove_distiller_markers(meter)
            meter.loop_contract["segment_classes"] = ["os", 7]

        def segment_only(meter, value):
            remove_distiller_markers(meter)
            meter.loop_contract["segment_classes"] = value

        def malformed_segment(meter):
            remove_distiller_markers(meter)
            meter.loop_contract["admission_mode"] = None
            meter.loop_contract["segment_classes"] = {"broken": True}

        def invalid_admission(meter):
            remove_distiller_markers(meter)
            meter.loop_contract["admission_mode"] = "preview"

        cases = (
            ("both-loop-ids-absent-policy-admission-remain", policy_and_admission),
            ("loop-ids-admission-absent-policy-ref-remains", policy_only),
            ("ids-ref-shape-absent-distiller-artifact-remains", artifact_only),
            ("task-only-parse-query", lambda meter: task_only(meter, "parse-query")),
            ("task-only-distill", lambda meter: task_only(meter, "distill")),
            ("one-request-hash", one_hash),
            ("partial-segment", partial_segment),
            ("malformed-segment", malformed_segment),
            ("segment-only-object", lambda meter: segment_only(meter, {})),
            ("segment-only-empty-list", lambda meter: segment_only(meter, [])),
            ("segment-only-number-list", lambda meter: segment_only(meter, [7])),
            ("segment-only-string", lambda meter: segment_only(meter, "broken")),
            ("segment-only-null", lambda meter: segment_only(meter, None)),
            ("invalid-admission", invalid_admission),
        )
        for index, (label, mutation) in enumerate(cases, 1):
            with self.subTest(label=label):
                if index > 1:
                    self._reset_run_dir()
                meter = self._distiller_meter()
                mutation(meter)
                self.assertTrue(meter._is_distiller_contract())
                flow = self._metered_flow(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=32,
                )
                flow.id = f"distiller-marker-{index}"
                original_key = flow.request.headers["x-api-key"]
                self._assert_distiller_flow_refused_before_upstream(meter, flow)
                self.assertEqual(flow.response[0][0], 429)
                self.assertEqual(flow.request.headers["x-api-key"], original_key)
                self.assertNotEqual(
                    flow.request.headers["x-api-key"],
                    meter.real_api_key,
                )
                self.assertNotIn(flow.id, meter.req_models)

                complete = self._distiller_flow(
                    f"e{index:07x}",
                    admission_mode="production",
                )
                complete.id = f"distiller-marker-complete-{index}"
                self._assert_distiller_flow_refused_before_upstream(
                    meter,
                    complete,
                )
                self.assertEqual(complete.response[0][0], 429)
                self.assertEqual(
                    complete.request.headers["x-api-key"],
                    VIRTUAL_KEY,
                )
                self.assertNotEqual(
                    complete.request.headers["x-api-key"],
                    meter.real_api_key,
                )
                self.assertNotIn(complete.id, meter.req_models)

    def test_non_distiller_contract_preserves_legacy_headerless_routing(self):
        meter = self._ready_meter()
        flow = self._metered_flow(
            model="claude-haiku-4-5-20251001",
            max_tokens=32,
        )
        meter.request(flow)
        self.assertIsNone(flow.response)
        self.assertEqual(flow.request.headers["x-api-key"], "sk-real-fixture")
        self.assertIn(flow.id, meter.req_models)


if __name__ == "__main__":
    unittest.main()
