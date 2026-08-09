"""Cut 4C structured adapters and orient end-to-end fallback plants."""
from __future__ import annotations

import ast
import json
import socket
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib import daily_spend, distiller as di, llm, metered_model
from lib import distiller_content as dc
from lib import distiller_query as dq
from lib import task_circle as tc
from lib.distiller_model_policy import (
    DAILY_CEILING_NANO_USD,
    DistillerModelPolicy,
    MODEL_ROUTES,
    ModelRoute,
    POLICY_VERSION,
)
from vault.tools.tests import test_distiller as legacy


DAY = "2026-07-23"
SNAPSHOT = "snapshot-model-runtime"


def active_policy():
    return DistillerModelPolicy(
        uid="0c938a95",
        version=POLICY_VERSION,
        status="active",
        state="active",
        runner_name="distiller-model-edge",
        runner_uid="6389dcd4",
        routes={
            task: ModelRoute(task, model, ceiling)
            for task, (model, ceiling) in MODEL_ROUTES.items()
        },
        daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
        segment_egress={"os": "auto", "team": "ask", "private": "ask"},
        consent_mode="auto",
        egress_approved=True,
        production_enabled=True,
        disabled_reasons=(),
        source_path=Path("vault/files/0c938a95.md"),
        index_path=Path("vault/00-index.jsonl"),
    )


class RuntimeCase(unittest.TestCase):
    def setUp(self):
        self.roots = legacy._RootFactory()
        self.addCleanup(self.roots.cleanup)
        self.fx = legacy._OrientFixture(self.roots)
        self.task_uid = "a0000001"
        self.capsule_uid = "b0000001"
        self.query_uid = "c0000001"
        self.fx.node(self.task_uid, legacy.OS, type_="task", status="active")
        self.fx.node(self.capsule_uid, legacy.OS, type_="capsule", status="locked")
        self.fx.node(self.query_uid, legacy.OS, type_="note", status="active")
        self.fx.rel(self.task_uid, self.capsule_uid, "governed_by")
        self.viewer = legacy.bob()
        self.query_index = dq.InMemoryQueryIndex(
            {self.query_uid: "needle model edge"},
            index_as_of=SNAPSHOT,
        )
        self.circle_index = tc.InMemoryStructuralIndex(
            self.fx._structures,
            index_as_of=SNAPSHOT,
        )
        self.loader = dc.InMemoryContentLoader(
            {
                self.capsule_uid: "# Capsule\n\ncapsule truth",
                self.query_uid: "# Query\n\nquery truth",
            },
            index_as_of=SNAPSHOT,
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.studio_root = Path(self.temp.name) / "studio"
        (self.studio_root / ".tropo").mkdir(parents=True)
        self.ledger_root = self.studio_root / "vault/loop-runs/.model-spend"
        self.ledger_root.mkdir(parents=True)
        self.policy = active_policy()
        daily_spend.initialize_ledger(
            self.ledger_root,
            policy_uid=self.policy.uid,
            policy_version=self.policy.version,
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
            day=DAY,
        )
        self.binding = metered_model.RunBinding(
            "abcd1234",
            metered_model.GATEWAY_URL,
            "sk-virtual-tropo-abcd1234",
            self.studio_root,
        )
        self.ids = iter(
            [
                "d0000001",
                "d0000002",
                "d0000003",
                "d0000004",
                "d0000005",
                "d0000006",
            ]
        )
        self.provider_tasks = []

    def provider(self, task, messages, **_kwargs):
        self.provider_tasks.append(task)
        if task == "parse-query":
            text = json.dumps({"uids": [self.query_uid]})
        else:
            payload = json.loads(messages[0]["content"])
            selected = payload["candidates"][0]
            text = json.dumps(
                {
                    "selections": [
                        {
                            "source_uid": selected["source_uid"],
                            "span_anchor": selected["span_anchor"],
                            "reorder_note": None,
                        }
                    ]
                }
            )
        return llm.LockedLLMResponse(
            text=text,
            model=llm.LOCKED_TASK_MODELS[task],
            usage={
                "input_tokens": 10,
                "output_tokens": 2,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "service_tier": "standard",
                "inference_geo": "global",
            },
        )

    def gated_call(self, task, messages, **kwargs):
        return metered_model.call(
            task,
            messages,
            provider_call=self.provider,
            clock=lambda: datetime.fromisoformat("2026-07-23T12:00:00+00:00"),
            reservation_id_factory=lambda: next(self.ids),
            environment={},
            **kwargs,
        )

    def orient(self, **overrides):
        values = {
            "intent": "needle",
            "index_as_of": SNAPSHOT,
            "chunk_budget": 2,
            "projection": self.fx.projection(),
            "query_index": self.query_index,
            "circle_index": self.circle_index,
            "rank_index": self.fx.rank_index(),
            "content_loader": self.loader,
        }
        values.update(overrides)
        return di.orient(
            self.task_uid,
            self.viewer,
            16,
            **values,
        )


class EndToEndRuntimeTests(RuntimeCase):
    def test_active_fixture_uses_both_locked_structured_adapters(self):
        result = self.orient(
            model_run_binding=self.binding,
            model_call=self.gated_call,
            model_policy_resolver=lambda: self.policy,
            parse_segment_class="os",
            segment_resolver=lambda _uid: "os",
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(self.provider_tasks, ["parse-query", "distill"])
        orientation = result.value
        self.assertEqual(orientation.query_seeds.uids, (self.query_uid,))
        self.assertFalse(orientation.query_seeds.fallback_used)
        self.assertFalse(orientation.distillation.fallback_used)
        self.assertEqual(len(orientation.distillation.chunks), 1)
        self.assertIn(
            orientation.distillation.chunks[0].source_uid,
            orientation.bound_deterministic.deterministic.uids(),
        )
        ledger = daily_spend.read_ledger(
            self.ledger_root,
            day=DAY,
            policy_uid=self.policy.uid,
            policy_version=self.policy.version,
            daily_ceiling_nano_usd=self.policy.daily_ceiling_nano_usd,
        )
        self.assertEqual(
            {record["status"] for record in ledger["reservations"].values()},
            {"reconciled"},
        )
        self.assertEqual(
            {
                record["task"]: record["actual_nano_usd"]
                for record in ledger["reservations"].values()
            },
            {
                "parse-query": 20_000,
                "distill": 60_000,
            },
        )

    def test_provider_failure_is_byte_equal_to_deterministic_fallback(self):
        baseline = self.orient(
            parse_double=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError()),
            distill_double=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError()),
        )

        def failed_provider(*_args, **_kwargs):
            raise RuntimeError("synthetic provider failure")

        def gated_failure(task, messages, **kwargs):
            return metered_model.call(
                task,
                messages,
                provider_call=failed_provider,
                clock=lambda: datetime.fromisoformat("2026-07-23T12:00:00+00:00"),
                reservation_id_factory=lambda: next(self.ids),
                environment={},
                **kwargs,
            )

        failed = self.orient(
            model_run_binding=self.binding,
            model_call=gated_failure,
            model_policy_resolver=lambda: self.policy,
            parse_segment_class="os",
            segment_resolver=lambda _uid: "os",
        )
        self.assertTrue(baseline.ok, msg=baseline.error)
        self.assertTrue(failed.ok, msg=failed.error)
        self.assertEqual(failed.value, baseline.value)
        self.assertTrue(failed.value.query_seeds.fallback_used)
        self.assertTrue(failed.value.distillation.fallback_used)

    def test_default_canonical_draft_policy_calls_zero_provider_and_succeeds(self):
        self.assertEqual(POLICY_VERSION, "1.9.0")
        for task in metered_model.CANARY_TASKS:
            _messages, system, _max_tokens = metered_model.canary_request(task)
            self.assertIn("Raw JSON only.", system)
            self.assertIn("Do not use Markdown fences.", system)
            self.assertIn("The first character must be {", system)
            self.assertIn("the final character must be }", system)
            self.assertIn("Do not include prose.", system)
        with mock.patch.object(
            llm,
            "call_locked",
            side_effect=AssertionError("provider construction forbidden"),
        ) as provider:
            with mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network forbidden"),
            ):
                first = self.orient()
                second = self.orient()
        provider.assert_not_called()
        self.assertTrue(first.ok, msg=first.error)
        self.assertEqual(first.value, second.value)
        self.assertTrue(first.value.query_seeds.fallback_used)
        self.assertTrue(first.value.distillation.fallback_used)
        self.assertIsNone(first.value.distillation.capture_id)
        self.assertEqual(first.value.distillation.capture_status, "pending")


class SourceBoundaryTests(unittest.TestCase):
    def test_owned_runtime_has_no_direct_network_event_capture_or_legacy_llm_call(self):
        paths = (
            TOOLS_DIR / "lib/distiller_model_policy.py",
            TOOLS_DIR / "lib/daily_spend.py",
            TOOLS_DIR / "lib/metered_model.py",
            TOOLS_DIR / "lib/distiller_query.py",
            TOOLS_DIR / "lib/distiller_edge.py",
            TOOLS_DIR / "lib/distiller.py",
            TOOLS_DIR / "6389dcd4.py",
        )
        forbidden_imports = {"requests", "httpx", "anthropic", "socket"}
        forbidden_names = {"emit_event", "capture_write"}
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = set()
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
                elif isinstance(node, ast.Name):
                    names.add(node.id)
            self.assertEqual(imports & forbidden_imports, set(), msg=path.name)
            self.assertEqual(names & forbidden_names, set(), msg=path.name)
            if path.name in {"distiller_query.py", "distiller_edge.py", "distiller.py"}:
                self.assertNotIn("llm.call(", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
