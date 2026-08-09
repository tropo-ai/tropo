#!/usr/bin/env python3
"""Mock-only plants for the metered synthetic Gardener canary."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


body_judge = _load(
    "gardener_synthetic_canary_test_target",
    TOOLS / "tropo-gardener-body-judge.py",
)
from lib import gardener_precision_fixtures as fixtures  # noqa: E402


RUN_UID = "abcd1234"
FIXTURE_SOURCE = TOOLS / "fixtures" / "gardener-pruning"


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class SyntheticCanaryScratch:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="gardener_canary_")
        self.root = Path(self.temp.name)
        self.fixture_root = (
            self.root / "vault" / "tools" / "fixtures" / "gardener-pruning"
        )
        self.fixture_root.parent.mkdir(parents=True)
        shutil.copytree(FIXTURE_SOURCE, self.fixture_root)
        self.manifest = self.fixture_root / "manifest.json"
        self.run_dir = self.root / "vault" / "loop-runs" / "canary"
        self.run_dir.mkdir(parents=True)
        self.policy = {
            "uid": body_judge.CANARY_POLICY_UID,
            "type": "loop",
            "status": "draft",
            "state": "active",
            "runner": "gardener-body-judge",
            "version": body_judge.CANARY_POLICY_VERSION,
            "judge_model": body_judge.CANARY_MODEL,
            "path": "vault/files/341823aa.md",
        }
        self.write_policy_source()
        self.contract = {
            "event": "loop_contract_locked",
            "loop": body_judge.CANARY_POLICY_UID,
            "loop_version": body_judge.CANARY_POLICY_VERSION,
            "model": body_judge.CANARY_MODEL,
            "fixture_composite_sha256": body_judge.CANARY_FIXTURE_COMPOSITE,
            "goal": {"authored_by": "human-fixture"},
            "verifier": {"kind": "gauntlet"},
            "policy": {
                "kind": "agentic-tool",
                "ref": body_judge.CANARY_RUNNER_UID,
            },
            "brakes": {
                "max_iterations": 1,
                "max_budget_usd": body_judge.CANARY_BUDGET_USD,
                "max_wall_clock_min": body_judge.CANARY_WALL_CLOCK_MIN,
            },
        }
        self.write_index()
        self.write_run()
        self.write_spend(0.0)
        self.fixture_set = fixtures.load_fixture_set(self.manifest)

    def close(self) -> None:
        self.temp.cleanup()

    def write_index(self, rows: list[dict] | None = None) -> None:
        path = self.root / "vault" / "00-index.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [self.policy] if rows is None else rows
        path.write_text(
            "".join(_canonical(row) + "\n" for row in rows),
            encoding="utf-8",
        )

    def write_policy_source(self, overrides: dict | None = None) -> None:
        frontmatter = {
            field: self.policy[field]
            for field in (
                "uid",
                "type",
                "status",
                "state",
                "runner",
                "version",
                "judge_model",
            )
        }
        if overrides:
            frontmatter.update(overrides)
        path = self.root / "vault" / "files" / "341823aa.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            + "\n".join(
                f"{field}: {json.dumps(value)}"
                for field, value in frontmatter.items()
            )
            + "\n---\n# Synthetic policy authority\n",
            encoding="utf-8",
        )

    def write_run(self) -> None:
        created = {
            "event": "run_created",
            "run_uid": RUN_UID,
            "loop": body_judge.CANARY_POLICY_UID,
            "loop_version": body_judge.CANARY_POLICY_VERSION,
        }
        (self.run_dir / "run.jsonl").write_text(
            _canonical(created) + "\n" + _canonical(self.contract) + "\n",
            encoding="utf-8",
        )

    def write_spend(self, value: object) -> None:
        (self.run_dir / "gateway_spend.json").write_text(
            _canonical({"spent_usd": value}) + "\n",
            encoding="utf-8",
        )

    def environment(self) -> dict[str, str]:
        return {
            "ANTHROPIC_BASE_URL": body_judge.CANARY_GATEWAY_URL,
            "ANTHROPIC_API_KEY": f"sk-virtual-tropo-{RUN_UID}",
        }

    def gold_response(self, case_id: str) -> str:
        case = next(case for case in self.fixture_set.cases if case.case_id == case_id)
        expected = case.record["expected"]
        if expected["action"] == "stamp":
            return _canonical(
                {
                    "decision": "prune",
                    "verdict": expected["verdict"],
                    "evidence_span": expected["evidence"],
                    "confidence": 1.0,
                }
            )
        return _canonical(
            {
                "decision": "no-prune",
                "verdict": None,
                "evidence_span": None,
                "confidence": 1.0,
            }
        )

    def gold_model(self, *, spend_increment: float = 0.01):
        calls: list[dict] = []

        def invoke(**kwargs):
            calls.append(kwargs)
            user = json.loads(kwargs["messages"][0]["content"])
            spend = json.loads(
                (self.run_dir / "gateway_spend.json").read_text()
            )["spent_usd"]
            self.write_spend(spend + spend_increment)
            return self.gold_response(user["case_id"])

        return mock.Mock(side_effect=invoke), calls

    def run(self, model_call) -> dict:
        with mock.patch.dict(os.environ, self.environment(), clear=True):
            return body_judge.run_synthetic_canary(
                self.root,
                self.run_dir,
                model_call=model_call,
                fixture_manifest=self.manifest,
            )


class GardenerSyntheticCanaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = SyntheticCanaryScratch()
        self.addCleanup(self.scratch.close)

    def test_success_is_isolated_exactly_routed_and_scored(self) -> None:
        model, calls = self.scratch.gold_model()
        self.assertEqual(
            body_judge.llm.model_for("gardener-prune"),
            "claude-opus-4-8",
        )
        watched = [
            ROOT / "vault" / "00-index.jsonl",
            ROOT / "vault" / "events" / "00-events.jsonl",
            self.scratch.root / "vault" / "00-index.jsonl",
        ]
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in watched
        }
        receipt = self.scratch.run(model)
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in watched
        }

        self.assertEqual(before, after)
        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(receipt["completed_count"], 18)
        self.assertEqual(receipt["calls_attempted"], 18)
        self.assertTrue(receipt["score"]["passed"])
        self.assertTrue(receipt["proposed_only"])
        self.assertFalse(receipt["writer_invoked"])
        self.assertEqual(receipt["fixture"]["composite_sha256"], body_judge.CANARY_FIXTURE_COMPOSITE)
        self.assertEqual(receipt["run"]["spend_before_usd"], 0.0)
        self.assertAlmostEqual(receipt["run"]["spend_after_usd"], 0.18)
        self.assertEqual(len(calls), 18)
        self.assertEqual(
            json.loads(
                (self.scratch.run_dir / body_judge.CANARY_RECEIPT_NAME).read_text()
            ),
            receipt,
        )

        all_bodies = {
            case.case_id: case.body.decode("utf-8")
            for case in self.scratch.fixture_set.cases
        }
        for case, call in zip(self.scratch.fixture_set.cases, calls):
            self.assertEqual(call["task"], "gardener-prune")
            self.assertEqual(call["model"], "claude-opus-4-8")
            self.assertEqual(call["max_tokens"], 256)
            self.assertEqual(call["system"], body_judge.CANARY_SYSTEM_PROMPT)
            self.assertEqual(len(call["messages"]), 1)
            prompt = json.loads(call["messages"][0]["content"])
            self.assertEqual(
                set(prompt),
                {"case_id", "segment", "normalized_body_sha256", "body"},
            )
            self.assertEqual(prompt["case_id"], case.case_id)
            self.assertEqual(prompt["segment"], case.record["segment"])
            self.assertEqual(prompt["body"], all_bodies[case.case_id])
            self.assertNotIn("expected", call["messages"][0]["content"])
            self.assertNotIn("human_mark", call["messages"][0]["content"])
            self.assertNotIn("synthetic_fixture:", prompt["body"])
            for other_id, other_body in all_bodies.items():
                if other_id != case.case_id:
                    self.assertNotIn(other_body, call["messages"][0]["content"])

    def test_fixture_drift_refuses_before_model_and_writes_failure_receipt(self) -> None:
        first_body = self.scratch.fixture_set.cases[0].path
        first_body.write_bytes(first_body.read_bytes() + b"\nDRIFT\n")
        model = mock.Mock(side_effect=AssertionError("must not call model"))
        receipt = self.scratch.run(model)
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["phase"], "preflight")
        self.assertEqual(receipt["calls_attempted"], 0)
        model.assert_not_called()

    def test_exact_policy_authority_and_version_fail_closed(self) -> None:
        variants = [
            [],
            [{**self.scratch.policy, "status": "archived"}],
            [{**self.scratch.policy, "version": "1.0.1"}],
            [{**self.scratch.policy, "uid": "deadbeef", "status": "draft"}],
        ]
        for rows in variants:
            with self.subTest(rows=rows):
                self.scratch.write_index(rows)
                model = mock.Mock()
                receipt = self.scratch.run(model)
                self.assertEqual(receipt["status"], "failed")
                self.assertEqual(receipt["calls_attempted"], 0)
                model.assert_not_called()
        self.scratch.write_index()

        for field, value in (
            ("loop", "deadbeef"),
            ("loop_version", "1.0.1"),
            ("model", "claude-sonnet-4-6"),
            ("fixture_composite_sha256", "0" * 64),
        ):
            with self.subTest(contract_field=field):
                original = self.scratch.contract[field]
                self.scratch.contract[field] = value
                self.scratch.write_run()
                model = mock.Mock()
                receipt = self.scratch.run(model)
                self.assertEqual(receipt["status"], "failed")
                model.assert_not_called()
                self.scratch.contract[field] = original
        self.scratch.write_run()

    def test_policy_source_must_be_exact_and_match_current_index(self) -> None:
        source = self.scratch.root / "vault" / "files" / "341823aa.md"
        for field, value in (
            ("uid", "deadbeef"),
            ("version", "1.0.1"),
            ("judge_model", "claude-sonnet-4-6"),
            ("status", "archived"),
        ):
            with self.subTest(field=field):
                self.scratch.write_policy_source({field: value})
                model = mock.Mock()
                receipt = self.scratch.run(model)
                self.assertEqual(receipt["status"], "failed")
                self.assertEqual(receipt["calls_attempted"], 0)
                model.assert_not_called()
        self.scratch.write_policy_source()

        source.unlink()
        model = mock.Mock()
        receipt = self.scratch.run(model)
        self.assertEqual(receipt["status"], "failed")
        model.assert_not_called()
        self.scratch.write_policy_source()

        source_bytes = source.read_bytes()
        alternate = source.with_name("policy-target.md")
        alternate.write_bytes(source_bytes)
        source.unlink()
        source.symlink_to(alternate.name)
        model = mock.Mock()
        receipt = self.scratch.run(model)
        self.assertEqual(receipt["status"], "failed")
        model.assert_not_called()
        source.unlink()
        source.write_bytes(source_bytes)
        alternate.unlink()

        self.scratch.policy["path"] = "vault/files/deadbeef.md"
        self.scratch.write_index()
        receipt = self.scratch.run(mock.Mock())
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("index path", receipt["error"])
        self.scratch.policy["path"] = "vault/files/341823aa.md"
        self.scratch.write_index()

    def test_budget_spend_gateway_key_and_sentinels_fail_closed(self) -> None:
        for value in (0.0, -1.0, True, "5", 5.01, 80.0):
            with self.subTest(contract_budget=value):
                self.scratch.contract["brakes"]["max_budget_usd"] = value
                self.scratch.write_run()
                receipt = self.scratch.run(mock.Mock())
                self.assertEqual(receipt["status"], "failed")
                self.assertEqual(receipt["calls_attempted"], 0)
        self.scratch.contract["brakes"]["max_budget_usd"] = 5.0
        self.scratch.write_run()

        spend_path = self.scratch.run_dir / "gateway_spend.json"
        invalid_spend = (
            b'{"spent_usd":NaN}\n',
            b'{"spent_usd":Infinity}\n',
            b'{"spent_usd":true}\n',
            b'{"spent_usd":-0.1}\n',
            b'{"spent_usd":"0"}\n',
            b'{"spent_usd":0,"extra":1}\n',
            b'{"spent_usd":0,"spent_usd":1}\n',
            b'{"spent_usd":null}\n',
            b'{}\n',
            b'not-json\n',
        )
        for raw in invalid_spend:
            with self.subTest(spend=raw):
                spend_path.write_bytes(raw)
                receipt = self.scratch.run(mock.Mock())
                self.assertEqual(receipt["status"], "failed")
                self.assertEqual(receipt["calls_attempted"], 0)
        spend_path.unlink()
        receipt = self.scratch.run(mock.Mock())
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["calls_attempted"], 0)
        self.scratch.write_spend(0.0)

        environments = [
            {
                "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
                "ANTHROPIC_API_KEY": f"sk-virtual-tropo-{RUN_UID}",
            },
            {
                "ANTHROPIC_BASE_URL": body_judge.CANARY_GATEWAY_URL,
                "ANTHROPIC_API_KEY": "sk-virtual-tropo-deadbeef",
            },
            {
                **self.scratch.environment(),
                "REAL_ANTHROPIC_API_KEY": "forbidden-real-key",
            },
        ]
        for environment in environments:
            with self.subTest(environment=environment):
                with mock.patch.dict(os.environ, environment, clear=True):
                    receipt = body_judge.run_synthetic_canary(
                        self.scratch.root,
                        self.scratch.run_dir,
                        model_call=mock.Mock(),
                        fixture_manifest=self.scratch.manifest,
                    )
                self.assertEqual(receipt["status"], "failed")
                self.assertEqual(receipt["calls_attempted"], 0)

        for sentinel in (".poison_sentinel", ".paused_sentinel"):
            with self.subTest(sentinel=sentinel):
                path = self.scratch.run_dir / sentinel
                path.write_text("stop")
                receipt = self.scratch.run(mock.Mock())
                self.assertEqual(receipt["status"], "failed")
                self.assertEqual(receipt["calls_attempted"], 0)
                path.unlink()

    def test_spend_decrease_and_worst_case_overshoot_refuse(self) -> None:
        def decrease(**_kwargs):
            self.scratch.write_spend(0.4)
            return self.scratch.gold_response("live-01-published-active")

        self.scratch.write_spend(0.5)
        receipt = self.scratch.run(mock.Mock(side_effect=decrease))
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("decreased", receipt["error"])

        self.scratch.write_spend(4.999)
        model = mock.Mock()
        receipt = self.scratch.run(model)
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("worst-case", receipt["error"])
        model.assert_not_called()

    def test_paid_model_failure_receipt_measures_spend(self) -> None:
        def paid_failure(**_kwargs):
            self.scratch.write_spend(0.25)
            raise RuntimeError("mock provider failure after charge")

        receipt = self.scratch.run(mock.Mock(side_effect=paid_failure))
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["phase"], "model")
        self.assertEqual(receipt["calls_attempted"], 1)
        self.assertEqual(receipt["completed_count"], 0)
        self.assertEqual(receipt["run"]["spend_before_usd"], 0.0)
        self.assertEqual(receipt["run"]["spend_after_usd"], 0.25)
        self.assertEqual(receipt["run"]["spend_delta_usd"], 0.25)
        self.assertIn("mock provider failure", receipt["error"])

    def test_malformed_closed_responses_are_total(self) -> None:
        live = self.scratch.fixture_set.cases[0]
        spent = next(
            case for case in self.scratch.fixture_set.cases
            if case.case_id == "spent-01-superseded"
        )
        nav = next(
            case for case in self.scratch.fixture_set.cases
            if case.case_id == "adv-01-nav-evidence"
        )
        invalid = [
            (live, "prose"),
            (live, "```json\n{}\n```"),
            (live, "[]"),
            (
                live,
                '{"decision":"no-prune","verdict":null,'
                '"evidence_span":null,"confidence":1,"extra":1}',
            ),
            (
                live,
                '{"decision":"no-prune","decision":"prune","verdict":null,'
                '"evidence_span":null,"confidence":1}',
            ),
            (
                live,
                '{"decision":"no-prune","verdict":null,'
                '"evidence_span":null,"confidence":true}',
            ),
            (
                live,
                '{"decision":"no-prune","verdict":null,'
                '"evidence_span":null,"confidence":NaN}',
            ),
            (
                live,
                _canonical(
                    {
                        "decision": "other",
                        "verdict": None,
                        "evidence_span": None,
                        "confidence": 1,
                    }
                ),
            ),
            (
                live,
                _canonical(
                    {
                        "decision": "no-prune",
                        "verdict": "finished",
                        "evidence_span": None,
                        "confidence": 1,
                    }
                ),
            ),
            (
                spent,
                _canonical(
                    {
                        "decision": "prune",
                        "verdict": None,
                        "evidence_span": None,
                        "confidence": 1,
                    }
                ),
            ),
            (
                spent,
                _canonical(
                    {
                        "decision": "prune",
                        "verdict": "finished",
                        "evidence_span": "not in this body",
                        "confidence": 1,
                    }
                ),
            ),
            (
                spent,
                _canonical(
                    {
                        "decision": "prune",
                        "verdict": "superseded",
                        "evidence_span": "the",
                        "confidence": 1,
                    }
                ),
            ),
            (
                nav,
                _canonical(
                    {
                        "decision": "prune",
                        "verdict": "superseded",
                        "evidence_span": (
                            "This synthetic page is superseded by a hidden "
                            "replacement."
                        ),
                        "confidence": 1,
                    }
                ),
            ),
            (
                spent,
                _canonical(
                    {
                        "decision": "prune",
                        "verdict": "superseded",
                        "evidence_span": "\ud800",
                        "confidence": 1,
                    }
                ),
            ),
        ]
        for case, raw in invalid:
            with self.subTest(case=case.case_id, raw=repr(raw)):
                with self.assertRaises(body_judge.SyntheticCanaryError):
                    body_judge._parse_canary_response(case, raw)

    def test_llm_route_requires_one_text_block_and_no_other_content(self) -> None:
        fake_anthropic = ModuleType("anthropic")
        fake_anthropic.AuthenticationError = type("AuthenticationError", (Exception,), {})
        fake_anthropic.RateLimitError = type("RateLimitError", (Exception,), {})
        create = mock.Mock()
        client = SimpleNamespace(messages=SimpleNamespace(create=create))
        fake_anthropic.Anthropic = mock.Mock(return_value=client)
        kwargs = {
            "task": "gardener-prune",
            "messages": [{"role": "user", "content": "{}"}],
            "model": "claude-opus-4-8",
            "max_tokens": 256,
        }
        with mock.patch.dict("sys.modules", {"anthropic": fake_anthropic}):
            with mock.patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "sk-virtual-tropo-abcd1234"},
                clear=True,
            ):
                create.return_value = SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="{}")],
                    stop_reason="end_turn",
                )
                self.assertEqual(body_judge.llm.call(**kwargs), "{}")
                self.assertEqual(
                    create.call_args.kwargs,
                    {
                        "model": "claude-opus-4-8",
                        "max_tokens": 256,
                        "messages": [{"role": "user", "content": "{}"}],
                    },
                )

                invalid_content = (
                    [],
                    [
                        SimpleNamespace(type="text", text="{}"),
                        SimpleNamespace(type="text", text="{}"),
                    ],
                    [SimpleNamespace(type="tool_use", text=None)],
                    [
                        SimpleNamespace(type="text", text="{}"),
                        SimpleNamespace(type="tool_use", text=None),
                    ],
                    [SimpleNamespace(type="text", text=[])],
                )
                for content in invalid_content:
                    with self.subTest(content=content):
                        create.return_value = SimpleNamespace(
                            content=content,
                            stop_reason="end_turn",
                        )
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "exactly one",
                        ):
                            body_judge.llm.call(**kwargs)

    def test_evidence_uniqueness_counts_nav_and_prose_raw_occurrences(self) -> None:
        spent = next(
            case for case in self.scratch.fixture_set.cases
            if case.case_id == "spent-01-superseded"
        )
        evidence = "This synthetic body is finished."
        duplicate = fixtures.FixtureCase(
            record=spent.record,
            path=spent.path,
            body=(
                b"# Duplicate raw evidence\n\n"
                b"<!-- nav-block:start -->\n"
                + evidence.encode()
                + b"\n<!-- nav-block:end -->\n\n"
                + evidence.encode()
                + b"\n"
            ),
        )
        raw = _canonical(
            {
                "decision": "prune",
                "verdict": "finished",
                "evidence_span": evidence,
                "confidence": 1,
            }
        )
        with self.assertRaisesRegex(
            body_judge.SyntheticCanaryError,
            "total raw body",
        ):
            body_judge._parse_canary_response(duplicate, raw)

        nav_only = fixtures.FixtureCase(
            record=spent.record,
            path=spent.path,
            body=(
                b"<!-- nav-block:start -->\n"
                + evidence.encode()
                + b"\n<!-- nav-block:end -->\n"
            ),
        )
        with self.assertRaisesRegex(
            body_judge.SyntheticCanaryError,
            "non-nav",
        ):
            body_judge._parse_canary_response(nav_only, raw)

    def test_wrong_live_prune_and_missed_spent_fail_locked_score(self) -> None:
        responses = {
            "live-01-published-active": _canonical(
                {
                    "decision": "prune",
                    "verdict": "finished",
                    "evidence_span": (
                        "This synthetic guide is the current published "
                        "procedure for the rehearsal service."
                    ),
                    "confidence": 1,
                }
            ),
            "spent-01-superseded": _canonical(
                {
                    "decision": "no-prune",
                    "verdict": None,
                    "evidence_span": None,
                    "confidence": 1,
                }
            ),
        }

        def invoke(**kwargs):
            case_id = json.loads(kwargs["messages"][0]["content"])["case_id"]
            spend = json.loads(
                (self.scratch.run_dir / "gateway_spend.json").read_text()
            )["spent_usd"]
            self.scratch.write_spend(spend + 0.01)
            return responses.get(case_id, self.scratch.gold_response(case_id))

        receipt = self.scratch.run(mock.Mock(side_effect=invoke))
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["phase"], "score")
        self.assertFalse(receipt["score"]["passed"])
        self.assertEqual(receipt["score"]["metrics"]["live_false_prunes"], 1)
        self.assertLess(receipt["score"]["metrics"]["spent_recall"], 1.0)

    def test_cli_modes_are_closed_and_dry_run_remains_distinct(self) -> None:
        parser = body_judge.build_parser()
        self.assertTrue(parser.parse_args(["--dry-run"]).dry_run)
        self.assertTrue(
            parser.parse_args(
                ["--synthetic-canary", "--run-dir", "vault/loop-runs/x"]
            ).synthetic_canary
        )
        with self.assertRaises(SystemExit):
            parser.parse_args(["--dry-run", "--synthetic-canary"])
        self.assertEqual(
            body_judge.main(
                [
                    "--synthetic-canary",
                    "--run-dir",
                    "vault/loop-runs/x",
                    "--vault-path",
                    str(self.scratch.root),
                ]
            ),
            2,
        )

        model_source = (TOOLS / "tropo-gardener-body-judge.py").read_text()
        self.assertNotIn("import tropo-gardener-verdict", model_source)
        self.assertNotIn("import tropo_gardener_verdict", model_source)
        self.assertNotIn("subprocess", model_source)


if __name__ == "__main__":
    unittest.main()
