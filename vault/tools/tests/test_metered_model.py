"""Cut 4C consent, per-call/day, binding, provider, and receipt plants."""
from __future__ import annotations

import hashlib
import inspect
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from lib import daily_spend, llm, loop_metering, metered_model
from lib.distiller_model_policy import (
    DAILY_CEILING_NANO_USD,
    POLICY_VERSION,
    PRIOR_RETAINED_TOTAL_NANO_USD,
    DistillerModelPolicy,
    MODEL_ROUTES,
    ModelRoute,
    claim_canary_authority,
)


DAY = "2026-07-23"
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


def make_studio(parent: Path, name: str = "studio") -> tuple[Path, Path]:
    studio_root = parent / name
    (studio_root / ".tropo").mkdir(parents=True)
    ledger_root = studio_root / "vault/loop-runs/.model-spend"
    ledger_root.mkdir(parents=True)
    return studio_root, ledger_root


def contract(
    *,
    enabled=True,
    canary=False,
    segments=None,
    daily=DAILY_CEILING_NANO_USD,
):
    segment_values = segments or {"os": "auto", "team": "auto", "private": "auto"}
    return DistillerModelPolicy(
        uid="0c938a95",
        version=POLICY_VERSION,
        status="active" if enabled else "draft",
        state="active",
        runner_name="distiller-model-edge",
        runner_uid="6389dcd4",
        routes={
            task: ModelRoute(task, model, ceiling)
            for task, (model, ceiling) in MODEL_ROUTES.items()
        },
        daily_ceiling_nano_usd=daily,
        segment_egress=dict(segment_values),
        consent_mode="auto" if enabled else "ask",
        egress_approved=enabled,
        production_enabled=enabled,
        disabled_reasons=() if enabled else ("policy is not active",),
        source_path=Path("vault/files/0c938a95.md"),
        index_path=Path("vault/00-index.jsonl"),
        canary_admissible=canary,
        canary_disabled_reasons=() if canary else ("canary is disabled",),
    )


def response(task, *, usage=None, model=None):
    return llm.LockedLLMResponse(
        text='{"ok":true}',
        model=model or llm.LOCKED_TASK_MODELS[task],
        usage=usage
        or {
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
        },
    )


class MeteredCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.studio_root, self.root = make_studio(Path(self.temp.name))
        self.policy = contract()
        daily_spend.initialize_ledger(
            self.root,
            policy_uid=self.policy.uid,
            policy_version=self.policy.version,
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
            day=DAY,
        )
        self.binding = metered_model.RunBinding(
            run_uid="abcd1234",
            gateway_url=metered_model.GATEWAY_URL,
            virtual_key="sk-virtual-tropo-abcd1234",
            studio_root=self.studio_root,
        )
        self.run_dir = self.studio_root / "vault/loop-runs/canary"
        self.ids = iter(
            ["a0000001", "a0000002", "a0000003", "a0000004", "a0000005"]
        )
        self.calls = []

    def ledger_path(self):
        return daily_spend._ledger_path(
            self.root,
            DAY,
            self.policy.version,
        )

    def provider(self, task, messages, **kwargs):
        self.calls.append((task, messages, kwargs))
        return response(task)

    def seed_canary_authority(self):
        self.run_dir.mkdir(exist_ok=True)
        created, canary_contract = metered_model.canary_run_events(
            self.binding.run_uid,
            self.policy.runner_uid,
        )
        contract_hash = metered_model.canary_contract_sha256(canary_contract)
        contract_path = self.run_dir / "run.jsonl"
        if not contract_path.exists():
            contract_path.write_text(
                "\n".join(
                    json.dumps(value, sort_keys=True, separators=(",", ":"))
                    for value in (created, canary_contract)
                )
                + "\n"
            )
        self.binding = metered_model.RunBinding(
            run_uid=self.binding.run_uid,
            gateway_url=self.binding.gateway_url,
            virtual_key=self.binding.virtual_key,
            studio_root=self.studio_root,
            run_dir=self.run_dir,
        )
        claim_canary_authority(
            self.root,
            policy=self.policy,
            run_uid=self.binding.run_uid,
            run_dir=self.run_dir,
            contract_sha256=contract_hash,
        )
        preparation_path = self.run_dir / metered_model.CANARY_PREPARATION_NAME
        if not preparation_path.exists():
            preparation = {
                "schema_version": 1,
                "status": "prepared",
                "policy_uid": self.policy.uid,
                "policy_version": self.policy.version,
                "runner_uid": self.policy.runner_uid,
                "run_uid": self.binding.run_uid,
                "contract_sha256": contract_hash,
                "request_sha256": metered_model.canary_request_hashes(),
                "admission_mode": "canary",
                "segment_classes": ["os"],
                "tasks": list(metered_model.CANARY_TASKS),
                "max_iterations": 2,
                "max_reserved_nano_usd": 260_000_000,
                "preparation_day": DAY,
                "execution_ledger_required": True,
            }
            preparation_path.write_text(
                json.dumps(preparation, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
        execution_path = self.run_dir / metered_model.CANARY_EXECUTION_LEDGER_NAME
        if not execution_path.exists():
            receipt = metered_model.canary_execution_ledger_receipt(
                run_uid=self.binding.run_uid,
                contract_sha256=contract_hash,
                preparation_day=DAY,
                execution_day=DAY,
                initial_ledger_sha256=hashlib.sha256(
                    self.ledger_path().read_bytes()
                ).hexdigest(),
            )
            execution_path.write_text(
                json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
            )

    def invoke(self, task="parse-query", **overrides):
        values = {
            "segment_classes": ("os",),
            "run_binding": self.binding,
            "max_tokens": 64,
            "provider_call": self.provider,
            "policy_resolver": lambda: self.policy,
            "clock": lambda: __import__("datetime").datetime.fromisoformat(
                f"{DAY}T12:00:00+00:00"
            ),
            "reservation_id_factory": lambda: next(self.ids),
            "environment": {},
        }
        values.update(overrides)
        return metered_model.call(
            task,
            [{"role": "user", "content": "{}"}],
            **values,
        )

    def invoke_canary(self, task="parse-query", **overrides):
        if self.policy.canary_admissible:
            self.seed_canary_authority()
        values = {
            "run_binding": self.binding,
            "provider_call": self.provider,
            "policy_resolver": lambda: self.policy,
            "clock": lambda: __import__("datetime").datetime.fromisoformat(
                f"{DAY}T12:00:00+00:00"
            ),
            "reservation_id_factory": lambda: next(self.ids),
            "environment": {},
        }
        values.update(overrides)
        return metered_model.call_canary(
            task,
            **values,
        )


class ConsentAndPreflightTests(MeteredCase):
    def test_canary_projection_and_hash_bind_task_specific_controls(self):
        parse = metered_model.canary_request_projection("parse-query")
        distill = metered_model.canary_request_projection("distill")
        self.assertEqual(parse["service_tier"], "standard_only")
        self.assertNotIn("inference_geo", parse)
        self.assertEqual(distill["service_tier"], "standard_only")
        self.assertEqual(distill["inference_geo"], "global")
        for task, projection in (("parse-query", parse), ("distill", distill)):
            with self.subTest(task=task):
                self.assertEqual(
                    metered_model.validate_canary_request_body(task, projection),
                    metered_model.canary_request_sha256(task),
                )
        cases = (
            ("parse-query", parse, lambda value: value.pop("service_tier")),
            (
                "parse-query",
                parse,
                lambda value: value.__setitem__("inference_geo", "global"),
            ),
            ("distill", distill, lambda value: value.pop("inference_geo")),
            (
                "distill",
                distill,
                lambda value: value.__setitem__("inference_geo", "us"),
            ),
            (
                "distill",
                distill,
                lambda value: value.__setitem__("service_tier", "priority"),
            ),
        )
        for task, projection, mutation in cases:
            candidate = dict(projection)
            mutation(candidate)
            with self.subTest(task=task, candidate=candidate):
                with self.assertRaises(ValueError):
                    metered_model.validate_canary_request_body(task, candidate)

    def test_cut4j_prompts_and_request_hashes_are_exact_and_deterministic(self):
        expected_hashes = {
            "parse-query": (
                "0e1f56e65d48d38eb7f8e2d844407752306426613a8cd5ea4289c1a583ff5454"
            ),
            "distill": (
                "1a6765fd1317aeab230546e6d642e724871b939efdcad716b4a028f01aa06b2c"
            ),
        }
        prior_hashes = {
            "parse-query": (
                "671107293d8ea6fedd08d7c8d4a61d169143fca2b391e0772e993453f81d2923"
            ),
            "distill": (
                "79279cdc5677aad1ec24755e18fccfb6ca42c2147526f95aafa097b6ca229584"
            ),
        }
        self.assertEqual(metered_model.canary_request_hashes(), expected_hashes)
        self.assertNotEqual(expected_hashes, prior_hashes)
        for task in metered_model.CANARY_TASKS:
            with self.subTest(task=task):
                _messages, system, _max_tokens = metered_model.canary_request(task)
                self.assertIn("Raw JSON only.", system)
                self.assertIn("Do not use Markdown fences.", system)
                self.assertIn("The first character must be {", system)
                self.assertIn("the final character must be }", system)
                self.assertIn("Do not include prose.", system)
                self.assertEqual(
                    metered_model.canary_request_sha256(task),
                    expected_hashes[task],
                )
                self.assertEqual(
                    metered_model.canary_request_projection(task)["system"],
                    system,
                )

    def test_draft_and_each_ask_segment_refuse_before_provider_or_ledger(self):
        before = self.ledger_path().read_bytes()
        for segment in ("os", "team", "private"):
            with self.subTest(segment=segment):
                self.policy = contract(
                    enabled=False,
                    segments={"os": "ask", "team": "ask", "private": "ask"},
                )
                result = self.invoke(segment_classes=(segment,))
                self.assertIsInstance(result, metered_model.ModelRefusal)
                self.assertEqual(result.code, "POLICY_DISABLED")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.ledger_path().read_bytes(), before)

    def test_segment_scoped_auto_subset_allows_only_requested_os(self):
        self.policy = contract(
            segments={"os": "auto", "team": "ask", "private": "ask"},
        )
        before = self.ledger_path().read_bytes()
        for requested in (("team",), ("private",), ("os", "team")):
            with self.subTest(requested=requested):
                result = self.invoke(segment_classes=requested)
                self.assertIsInstance(result, metered_model.ModelRefusal)
                self.assertEqual(result.code, "CONSENT_DENIED")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.ledger_path().read_bytes(), before)

        allowed = self.invoke(segment_classes=("os",))
        self.assertIsInstance(allowed, metered_model.MeteredModelResult)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(
            self.calls[0][2]["metering_context"].segment_classes,
            ("os",),
        )
        self.assertEqual(
            self.read()["reservations"][allowed.receipt.reservation_id]["status"],
            "reconciled",
        )

    def test_bounded_geo_path_structurally_refuses_team_and_private(self):
        self.policy = contract(
            segments={"os": "auto", "team": "auto", "private": "auto"},
        )
        before = self.ledger_path().read_bytes()
        for requested in (("team",), ("private",), ("os", "team")):
            with self.subTest(requested=requested):
                result = self.invoke(segment_classes=requested)
                self.assertEqual(result.code, "GEO_SCOPE_REFUSED")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.ledger_path().read_bytes(), before)

    def test_canary_admits_os_only_while_same_policy_keeps_production_closed(self):
        self.policy = contract(
            enabled=False,
            canary=True,
            segments={"os": "ask", "team": "ask", "private": "ask"},
        )
        production = self.invoke(segment_classes=("os",))
        self.assertEqual(production.code, "POLICY_DISABLED")
        canary = self.invoke_canary()
        self.assertIsInstance(canary, metered_model.MeteredModelResult)
        self.assertEqual(canary.receipt.admission_mode, "canary")
        context = self.calls[0][2]["metering_context"]
        self.assertEqual(context.admission_mode, "canary")
        self.assertEqual(context.segment_classes, ("os",))

    def test_canary_surface_has_no_segment_or_admission_override(self):
        signature = inspect.signature(metered_model.call_canary)
        for field in (
            "messages",
            "system",
            "max_tokens",
            "segment_classes",
            "admission_mode",
        ):
            self.assertNotIn(field, signature.parameters)
        for override in (
            {"messages": [{"role": "user", "content": "arbitrary"}]},
            {"system": "arbitrary"},
            {"max_tokens": 1},
            {"segment_classes": ("team",)},
            {"segment_classes": ("private",)},
            {"segment_classes": ("os", "team")},
            {"admission_mode": "production"},
        ):
            with self.subTest(override=override):
                with self.assertRaises(TypeError):
                    self.invoke_canary(**override)
        self.assertEqual(self.calls, [])

    def test_second_canary_refuses_before_reservation_or_provider(self):
        self.policy = contract(enabled=False, canary=False)
        before = self.ledger_path().read_bytes()
        result = self.invoke_canary()
        self.assertEqual(result.code, "CANARY_DISABLED")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.ledger_path().read_bytes(), before)

    def test_canary_distill_cannot_reserve_before_fixed_parse(self):
        self.policy = contract(enabled=False, canary=True)
        result = self.invoke_canary("distill")
        self.assertEqual(result.code, "RESERVATION_REFUSED")
        self.assertIn("requires 'parse-query' next", result.message)
        self.assertEqual(self.read()["reservations"], {})
        self.assertEqual(self.calls, [])

    def test_duplicate_task_and_combined_canary_overflow_refuse_pre_reservation(self):
        self.policy = contract(enabled=False, canary=True)
        first = self.invoke_canary()
        self.assertIsInstance(first, metered_model.MeteredModelResult)
        before = self.read()
        duplicate = self.invoke_canary()
        self.assertEqual(duplicate.code, "RESERVATION_REFUSED")
        self.assertIn("exactly one reservation", duplicate.message)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.read(), before)

        other = MeteredCase("runTest")
        other.setUp()
        self.addCleanup(other.doCleanups)
        other.policy = contract(enabled=False, canary=True)
        other.seed_canary_authority()
        daily_spend.reserve(
            other.root,
            day=DAY,
            policy_uid=other.policy.uid,
            policy_version=other.policy.version,
            daily_ceiling_nano_usd=other.policy.daily_ceiling_nano_usd,
            reservation_id="b0000001",
            run_uid=other.binding.run_uid,
            task="parse-query",
            model=other.policy.route("parse-query").model,
            segment_classes=("os",),
            worst_case_nano_usd=259_999_999,
        )
        result = other.invoke_canary("distill")
        self.assertEqual(result.code, "RESERVATION_REFUSED")
        self.assertIn("260000000", result.message)
        ledger = daily_spend.read_ledger(
            other.root,
            day=DAY,
            policy_uid=other.policy.uid,
            policy_version=other.policy.version,
            daily_ceiling_nano_usd=other.policy.daily_ceiling_nano_usd,
        )
        self.assertEqual(len(ledger["reservations"]), 1)
        self.assertEqual(other.calls, [])

    def test_production_and_canary_wrappers_share_one_internal_call_path(self):
        production_policy = self.policy
        canary_policy = contract(enabled=False, canary=True)
        with mock.patch.object(
            metered_model,
            "_call",
            wraps=metered_model._call,
        ) as shared:
            self.policy = canary_policy
            canary = self.invoke_canary()
            self.policy = production_policy
            production = self.invoke()
        self.policy = production_policy
        self.assertIsInstance(production, metered_model.MeteredModelResult)
        self.assertIsInstance(canary, metered_model.MeteredModelResult)
        self.assertEqual(shared.call_count, 2)
        self.assertEqual(
            [call.kwargs["admission_mode"] for call in shared.call_args_list],
            ["canary", "production"],
        )

    def test_unknown_task_and_segment_alias_do_not_escalate(self):
        unknown = self.invoke("summarize")
        alias = self.invoke(segment_classes=("public",))
        self.assertEqual(unknown.code, "UNKNOWN_TASK")
        self.assertEqual(alias.code, "INVALID_SEGMENT")
        self.assertEqual(self.calls, [])

    def test_per_call_oversize_refuses_without_reservation(self):
        result = self.invoke(max_tokens=2_000)
        self.assertEqual(result.code, "PER_CALL_LIMIT")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.read()["reservations"], {})

    def test_sonnet_us_preflight_hits_exact_per_call_and_daily_boundaries(self):
        messages = [{"role": "user", "content": "{}"}]
        request_bytes = llm.serialize_locked_request(
            "distill",
            messages,
            max_tokens=64,
        )
        expected = loop_metering.worst_case_request_cost_nano_usd(
            loop_metering.SONNET_46_MODEL,
            request_bytes=len(request_bytes),
            max_tokens=64,
            cache_mode="none",
        )
        self.assertEqual(
            expected,
            (len(request_bytes) + loop_metering.REQUEST_OVERHEAD_BYTES) * 3_300
            + 64 * 16_500,
        )
        self.policy.routes["distill"] = ModelRoute(
            "distill",
            loop_metering.SONNET_46_MODEL,
            expected - 1,
        )
        refused = self.invoke("distill")
        self.assertEqual(refused.code, "PER_CALL_LIMIT")
        self.assertEqual(self.read()["reservations"], {})

        self.policy.routes["distill"] = ModelRoute(
            "distill",
            loop_metering.SONNET_46_MODEL,
            expected,
        )
        daily_spend.reserve(
            self.root,
            day=DAY,
            policy_uid=self.policy.uid,
            policy_version=self.policy.version,
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
            reservation_id="f9000001",
            run_uid="f9000002",
            task="parse-query",
            model=loop_metering.HAIKU_45_MODEL,
            segment_classes=("os",),
            worst_case_nano_usd=self.policy.daily_ceiling_nano_usd - expected,
        )
        provider_calls = []

        def unknown_paid_outcome(*args, **kwargs):
            provider_calls.append((args, kwargs))
            raise RuntimeError("paid outcome unknown")

        at_boundary = self.invoke("distill", provider_call=unknown_paid_outcome)
        self.assertEqual(at_boundary.code, "PROVIDER_FAILED")
        self.assertTrue(at_boundary.worst_case_retained)
        self.assertEqual(len(provider_calls), 1)
        with daily_spend._locked(self.root, DAY) as locked_root:
            self.assertEqual(
                daily_spend._combined_committed_locked(
                    locked_root,
                    DAY,
                    policy_uid=self.policy.uid,
                    daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
                ),
                self.policy.daily_ceiling_nano_usd,
            )
        over_boundary = self.invoke("distill", provider_call=unknown_paid_outcome)
        self.assertEqual(over_boundary.code, "RESERVATION_REFUSED")
        self.assertEqual(len(provider_calls), 1)

    def test_bad_gateway_key_route_and_real_key_refuse(self):
        bindings = (
            metered_model.RunBinding(
                "abcd1234",
                "https://api.anthropic.com",
                self.binding.virtual_key,
                self.studio_root,
            ),
            metered_model.RunBinding(
                "abcd1234",
                self.binding.gateway_url,
                "sk-virtual-tropo-deadbeef",
                self.studio_root,
            ),
        )
        for binding in bindings:
            with self.subTest(binding=binding):
                result = self.invoke(run_binding=binding)
                self.assertEqual(result.code, "PREFLIGHT_REFUSED")
        result = self.invoke(environment={"REAL_ANTHROPIC_API_KEY": "forbidden"})
        self.assertEqual(result.code, "PREFLIGHT_REFUSED")
        self.assertEqual(self.calls, [])

    def test_studio_binding_rejects_path_escape_and_symlink_surfaces(self):
        parent = Path(self.temp.name)
        before = self.ledger_path().read_bytes()

        outside_root, _outside_ledger = make_studio(parent, "outside")
        lexical_escape = self.studio_root / ".." / outside_root.name

        missing_marker = parent / "missing-marker"
        (missing_marker / "vault/loop-runs/.model-spend").mkdir(parents=True)

        missing_ledger = parent / "missing-ledger"
        (missing_ledger / ".tropo").mkdir(parents=True)

        sibling_ledger = parent / ".model-spend"
        sibling_ledger.mkdir()

        root_link = parent / "studio-link"
        root_link.symlink_to(self.studio_root, target_is_directory=True)

        real_parent = parent / "real-parent"
        make_studio(real_parent, "nested-studio")
        parent_link = parent / "parent-link"
        parent_link.symlink_to(real_parent, target_is_directory=True)

        linked_ledger_parent = parent / "linked-ledger-parent"
        (linked_ledger_parent / ".tropo").mkdir(parents=True)
        (linked_ledger_parent / "vault").mkdir()
        external_loop_runs = parent / "external-loop-runs"
        (external_loop_runs / ".model-spend").mkdir(parents=True)
        (linked_ledger_parent / "vault/loop-runs").symlink_to(
            external_loop_runs,
            target_is_directory=True,
        )

        linked_marker = parent / "linked-marker"
        linked_marker.mkdir()
        (linked_marker / "vault/loop-runs/.model-spend").mkdir(parents=True)
        marker_target = parent / "marker-target"
        marker_target.mkdir()
        (linked_marker / ".tropo").symlink_to(
            marker_target,
            target_is_directory=True,
        )

        invalid_roots = (
            Path("../relative-escape"),
            lexical_escape,
            missing_marker,
            missing_ledger,
            sibling_ledger,
            root_link,
            parent_link / "nested-studio",
            linked_ledger_parent,
            linked_marker,
        )
        for studio_root in invalid_roots:
            with self.subTest(studio_root=studio_root):
                binding = metered_model.RunBinding(
                    "abcd1234",
                    metered_model.GATEWAY_URL,
                    "sk-virtual-tropo-abcd1234",
                    studio_root,
                )
                result = self.invoke(run_binding=binding)
                self.assertEqual(result.code, "PREFLIGHT_REFUSED")

        with self.assertRaises(TypeError):
            metered_model.RunBinding(
                run_uid="abcd1234",
                gateway_url=metered_model.GATEWAY_URL,
                virtual_key="sk-virtual-tropo-abcd1234",
                studio_root=self.studio_root,
                ledger_root=sibling_ledger,
            )
        self.assertEqual(self.calls, [])
        self.assertEqual(self.ledger_path().read_bytes(), before)

        valid = self.invoke()
        self.assertIsInstance(valid, metered_model.MeteredModelResult)
        self.assertEqual(len(self.calls), 1)

    def read(self):
        return daily_spend.read_ledger(
            self.root,
            day=DAY,
            policy_uid=self.policy.uid,
            policy_version=self.policy.version,
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
        )


class ProviderAndReceiptTests(MeteredCase):
    def read(self):
        return daily_spend.read_ledger(
            self.root,
            day=DAY,
            policy_uid=self.policy.uid,
            policy_version=self.policy.version,
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
        )

    def test_success_returns_immutable_receipt_and_reconciles_actual(self):
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network forbidden"),
        ):
            result = self.invoke()
        self.assertIsInstance(result, metered_model.MeteredModelResult)
        self.assertEqual(result.model, "claude-haiku-4-5-20251001")
        self.assertEqual(result.receipt.actual_nano_usd, 20_000)
        self.assertLess(
            result.receipt.actual_nano_usd,
            result.receipt.reserved_nano_usd,
        )
        record = self.read()["reservations"][result.receipt.reservation_id]
        self.assertEqual(record["status"], "reconciled")
        context = self.calls[0][2]["metering_context"]
        self.assertEqual(context.model, "claude-haiku-4-5-20251001")
        self.assertEqual(context.policy_uid, "0c938a95")

    def test_haiku_us_and_sonnet_global_reconcile_exact_task_prices(self):
        base = {
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "service_tier": "standard",
        }
        haiku = self.invoke(
            provider_call=lambda task, *_args, **_kwargs: response(
                task,
                usage={**base, "inference_geo": "us"},
            )
        )
        sonnet = self.invoke(
            "distill",
            provider_call=lambda task, *_args, **_kwargs: response(
                task,
                usage={**base, "inference_geo": "global"},
            ),
        )
        self.assertIsInstance(haiku, metered_model.MeteredModelResult)
        self.assertIsInstance(sonnet, metered_model.MeteredModelResult)
        self.assertEqual(haiku.receipt.actual_nano_usd, 20_000)
        self.assertEqual(sonnet.receipt.actual_nano_usd, 60_000)
        ledger = self.read()
        self.assertEqual(
            {
                reservation_id: record["actual_nano_usd"]
                for reservation_id, record in ledger["reservations"].items()
            },
            {
                haiku.receipt.reservation_id: 20_000,
                sonnet.receipt.reservation_id: 60_000,
            },
        )

    def test_sonnet_us_response_reconciles_at_exact_eleven_tenths(self):
        result = self.invoke(
            "distill",
            provider_call=lambda task, *_args, **_kwargs: response(
                task,
                usage={
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "service_tier": "standard",
                    "inference_geo": "us",
                },
            ),
        )
        self.assertIsInstance(result, metered_model.MeteredModelResult)
        self.assertEqual(result.receipt.actual_nano_usd, 19_800)
        self.assertEqual(
            self.read()["reservations"][result.receipt.reservation_id]["status"],
            "reconciled",
        )

    def test_provider_throw_or_malformed_result_retains_worst_case(self):
        def raises(*_args, **_kwargs):
            raise RuntimeError("provider failed")

        failed = self.invoke(provider_call=raises)
        self.assertEqual(failed.code, "PROVIDER_FAILED")
        self.assertTrue(failed.worst_case_retained)
        record = self.read()["reservations"][failed.reservation_id]
        self.assertEqual(record["status"], "reserved")

        malformed = self.invoke(provider_call=lambda *_args, **_kwargs: "text")
        self.assertEqual(malformed.code, "PROVIDER_RESPONSE_REFUSED")
        self.assertEqual(
            self.read()["reservations"][malformed.reservation_id]["status"],
            "reserved",
        )

    def test_response_model_substitution_never_falls_back_to_another_model(self):
        result = self.invoke(
            provider_call=lambda task, *_args, **_kwargs: response(
                task,
                model="claude-sonnet-4-6",
            )
        )
        self.assertEqual(result.code, "MODEL_SUBSTITUTION")
        self.assertTrue(result.worst_case_retained)
        self.assertEqual(len(self.read()["reservations"]), 1)

    def test_short_haiku_alias_response_is_rejected_before_accepted_metering(self):
        result = self.invoke(
            provider_call=lambda task, *_args, **_kwargs: response(
                task,
                model="claude-haiku-4-5",
            )
        )
        self.assertEqual(result.code, "MODEL_SUBSTITUTION")
        self.assertTrue(result.worst_case_retained)
        record = self.read()["reservations"][result.reservation_id]
        self.assertEqual(record["status"], "reserved")

    def test_missing_ledger_refuses_before_provider(self):
        self.ledger_path().unlink()
        result = self.invoke()
        self.assertEqual(result.code, "RESERVATION_REFUSED")
        self.assertEqual(self.calls, [])
        self.assertFalse(self.ledger_path().exists())

    def test_legacy_committed_spend_blocks_current_version_before_provider(self):
        daily_spend.initialize_ledger(
            self.root,
            policy_uid=self.policy.uid,
            policy_version="1.1.0",
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
            day=DAY,
        )
        daily_spend.reserve(
            self.root,
            day=DAY,
            policy_uid=self.policy.uid,
            policy_version="1.1.0",
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
            reservation_id="f1000001",
            run_uid="f2000001",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("os",),
            worst_case_nano_usd=4_999_000_000,
        )
        current_before = self.ledger_path().read_bytes()
        result = self.invoke()
        self.assertEqual(result.code, "RESERVATION_REFUSED")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.ledger_path().read_bytes(), current_before)

    def test_five_ledgers_count_all_four_prior_retained_amounts(self):
        prior = (
            ("1.1.0", "f1100001", "f1200001", 5_269_000),
            ("1.2.0", "f2100001", "f2200001", 5_281_000),
            ("1.3.0", "f3100001", "f3200001", 5_337_000),
            ("1.4.0", "f4100001", "f4200001", 5_312_000),
        )
        for version, reservation_id, run_uid, retained in prior:
            daily_spend.initialize_ledger(
                self.root,
                policy_uid=self.policy.uid,
                policy_version=version,
                daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
                day=DAY,
            )
            daily_spend.reserve(
                self.root,
                day=DAY,
                policy_uid=self.policy.uid,
                policy_version=version,
                daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
                reservation_id=reservation_id,
                run_uid=run_uid,
                task="parse-query",
                model="claude-haiku-4-5-20251001",
                segment_classes=("os",),
                worst_case_nano_usd=retained,
            )
        with daily_spend._locked(self.root, DAY) as locked_root:
            self.assertEqual(
                daily_spend._combined_committed_locked(
                    locked_root,
                    DAY,
                    policy_uid=self.policy.uid,
                    daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
                ),
                PRIOR_RETAINED_TOTAL_NANO_USD,
            )
        result = self.invoke(segment_classes=("os",))
        self.assertIsInstance(result, metered_model.MeteredModelResult)
        with daily_spend._locked(self.root, DAY) as locked_root:
            combined = daily_spend._combined_committed_locked(
                locked_root,
                DAY,
                policy_uid=self.policy.uid,
                daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
            )
        self.assertEqual(
            combined,
            PRIOR_RETAINED_TOTAL_NANO_USD + result.receipt.actual_nano_usd,
        )

    def test_old_binary_v11_write_after_v12_forces_fail_closed_provider_denial(self):
        daily_spend.reserve(
            self.root,
            day=DAY,
            policy_uid=self.policy.uid,
            policy_version=self.policy.version,
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
            reservation_id="f3000001",
            run_uid="f4000001",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("os",),
            worst_case_nano_usd=4_900_000_000,
        )
        daily_spend.initialize_ledger(
            self.root,
            policy_uid=self.policy.uid,
            policy_version="1.1.0",
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
            day=DAY,
        )

        # Simulate the historical binary's single-ledger RMW. It holds the
        # stable day lock but never discovers the already-present v1.2 file.
        with daily_spend._locked(self.root, DAY) as locked_root:
            legacy_path = daily_spend._ledger_path(
                locked_root,
                DAY,
                "1.1.0",
            )
            legacy = daily_spend._read_locked(
                legacy_path,
                DAY,
                policy_uid=self.policy.uid,
                policy_version="1.1.0",
                daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
            )
            legacy["reservations"]["f3000002"] = {
                "run_uid": "f4000002",
                "task": "distill",
                "model": "claude-sonnet-4-6",
                "segment_classes": ["os"],
                "worst_case_nano_usd": 200_000_000,
                "status": "reserved",
                "actual_nano_usd": None,
                "gateway_request_id": None,
            }
            daily_spend._write_locked(legacy_path, legacy)

        combined = sum(
            daily_spend.effective_committed_nano_usd(
                daily_spend.read_ledger(
                    self.root,
                    day=DAY,
                    policy_uid=self.policy.uid,
                    policy_version=version,
                    daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
                )
            )
            for version in ("1.1.0", self.policy.version)
        )
        self.assertEqual(combined, 5_100_000_000)
        current_before = self.ledger_path().read_bytes()
        for task in ("parse-query", "distill"):
            with self.subTest(task=task):
                result = self.invoke(task)
                self.assertEqual(result.code, "RESERVATION_REFUSED")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.ledger_path().read_bytes(), current_before)
        legacy = daily_spend.read_ledger(
            self.root,
            day=DAY,
            policy_uid=self.policy.uid,
            policy_version="1.1.0",
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
        )
        self.assertEqual(
            legacy["reservations"]["f3000002"]["status"],
            "reserved",
        )

    def test_combined_daily_pool_counts_failed_calls_at_worst_case(self):
        tiny = 6_000_000
        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.studio_root, self.root = make_studio(Path(self.temp.name))
        self.policy = contract(daily=tiny)
        self.binding = metered_model.RunBinding(
            "abcd1234",
            metered_model.GATEWAY_URL,
            "sk-virtual-tropo-abcd1234",
            self.studio_root,
        )
        daily_spend.initialize_ledger(
            self.root,
            policy_uid=self.policy.uid,
            policy_version=self.policy.version,
            daily_ceiling_nano_usd=tiny,
            day=DAY,
        )

        def raises(*_args, **_kwargs):
            raise RuntimeError("paid outcome unknown")

        first = self.invoke(provider_call=raises)
        second = self.invoke(provider_call=raises)
        self.assertEqual(first.code, "PROVIDER_FAILED")
        self.assertEqual(second.code, "RESERVATION_REFUSED")
        ledger = self.read()
        self.assertEqual(len(ledger["reservations"]), 1)
        self.assertLessEqual(
            daily_spend.effective_committed_nano_usd(ledger),
            tiny,
        )


if __name__ == "__main__":
    unittest.main()
