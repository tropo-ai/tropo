#!/usr/bin/env python3
"""Governed-skips v2 — d9ca03fd / d7db77d8.

AC1: authorized skip closes terminal criteria that reference the skipped producer.
AC2: unauthorized skip still refuses (gate does not widen).
AC3: sandboxed native replay of historical run 635b62b7 re-verifies without
     synthetic pass receipts or rewriting the source log.
Control: all-verified behavior unchanged.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[3]
TOOLS = STUDIO / "vault" / "tools"
HIST_RUN = STUDIO / "vault" / "pipeline-runs" / "dev-pipeline-635b62b7-2026-08-08"
HIST_ACTIVATION = "ff6f762e"
TERMINAL_STEP = "3e0bb81e"
TEST_TRIGGER = "4f64ec3c"


def _load_engine(sandbox: Path):
    sys.path.insert(0, str(sandbox / "vault" / "tools"))
    for mod in [m for m in list(sys.modules) if m == "lib" or m.startswith("lib.")]:
        del sys.modules[mod]
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "engine_under_test", sandbox / "vault" / "tools" / "9e7003b1.py"
    )
    eng = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eng)
    eng.VAULT_ROOT = sandbox
    eng.VAULT_FILES = sandbox / "vault" / "files"
    eng.PIPELINE_RUNS_FOLDER = sandbox / "vault" / "pipeline-runs"
    eng.VAULT_INDEX = sandbox / "vault" / "00-index.jsonl"
    return eng


def _scaffold(tmp: Path) -> Path:
    root = tmp / "studio"
    (root / "vault" / "tools" / "lib").mkdir(parents=True)
    (root / "vault" / "files").mkdir(parents=True)
    (root / "vault" / "pipeline-runs").mkdir(parents=True)
    (root / ".tropo-studio").mkdir(parents=True)
    for name in ("9e7003b1.py", "tropo-mint-id.py", "tropo-lineage.py"):
        src = TOOLS / name
        if src.is_file():
            (root / "vault" / "tools" / name).write_bytes(src.read_bytes())
    for lib in (TOOLS / "lib").glob("*.py"):
        (root / "vault" / "tools" / "lib" / lib.name).write_bytes(lib.read_bytes())
    ks = root / ".tropo" / "scripts" / "lib"
    ks.mkdir(parents=True)
    for lib in (STUDIO / ".tropo" / "scripts" / "lib").glob("*.py"):
        (ks / lib.name).write_bytes(lib.read_bytes())
    # Minimal capsules the engine may read.
    cap_src = STUDIO / "vault" / "capsules"
    if cap_src.is_dir():
        d = root / "vault" / "capsules"
        d.mkdir(parents=True, exist_ok=True)
        for name in ("tropo-pipeline-run.capsule.md",):
            src = cap_src / name
            if src.is_file():
                (d / name).write_bytes(src.read_bytes())
    os.environ["TROPO_PIPELINE_RUNTIME_SANDBOX"] = str(root / "sandbox-events.jsonl")
    return root


def _copy_historical(root: Path) -> Path:
    dest = root / "vault" / "pipeline-runs" / HIST_RUN.name
    shutil.copytree(HIST_RUN, dest)
    # Activation + principals + migration manifest (Stage-8 emptied the freeze;
    # load_run still requires the manifest file to exist so it can read {}).
    for uid in (
        HIST_ACTIVATION, "43125c54", "635b62b7", "882887c7", "ff6f762e",
        # Principals named by human_signoff actors on the historical run.
        "7c017d1f", "d70ae4cb",
    ):
        src = STUDIO / "vault" / "files" / f"{uid}.md"
        if src.is_file():
            (root / "vault" / "files" / f"{uid}.md").write_bytes(src.read_bytes())
    return dest


class GovernedSkipsObligationUnit(unittest.TestCase):
    def test_producer_ownership_from_creation_criteria(self):
        from lib import pipeline_obligations as ob

        decls = {
            "aaaa0001": {
                "exit_criteria": [
                    "triggered_test_spec.uid exists",
                    "dev_spec.triggered_test_spec_uids contains <x>",
                ]
            },
            "bbbb0002": {
                "exit_criteria": ["triggered_doc_spec.uid exists"]
            },
        }
        ownership, ambiguous = ob.build_producer_ownership(decls)
        self.assertEqual(ownership["triggered_test_spec"], "aaaa0001")
        self.assertEqual(ownership["dev_spec.triggered_test_spec_uids"], "aaaa0001")
        self.assertEqual(ownership["triggered_doc_spec"], "bbbb0002")
        self.assertEqual(ambiguous, set())

    def test_ambiguous_producer_ownership_refuses(self):
        """d7db77d8: two distinct steps claiming the same handle fail closed."""
        from lib import pipeline_obligations as ob

        decls = {
            "aaaa0001": {"exit_criteria": ["triggered_test_spec.uid exists"]},
            "cccc0003": {"exit_criteria": ["triggered_test_spec.uid exists"]},
            "dddd0004": {
                "exit_criteria": ["triggered_test_spec.stage == done"]
            },
        }
        ownership, ambiguous = ob.build_producer_ownership(decls)
        self.assertIn("triggered_test_spec", ambiguous)
        self.assertNotIn("triggered_test_spec", ownership)

        replay = ob.build_activation_replay_index([], decls, "act00001")
        self.assertIn("triggered_test_spec", replay["ambiguous_producers"])
        obl = ob.resolve_obligation(
            kind="criterion",
            replay=replay,
            step_status={},
            consumer_step="dddd0004",
            criterion="triggered_test_spec.stage == done",
            raw_verdict="fail",
        )
        self.assertEqual(obl["disposition"], ob.UNSATISFIED)
        self.assertIn("ambiguous producer ownership", obl["rationale"])

    def test_resolve_criterion_waives_on_authorized_skip(self):
        from lib import pipeline_obligations as ob

        decls = {
            TEST_TRIGGER: {
                "exit_criteria": ["triggered_test_spec.uid exists"]
            },
            TERMINAL_STEP: {
                "exit_criteria": ["triggered_test_spec.stage == done"]
            },
        }
        events = [
            {
                "event": "skip_request",
                "step": TEST_TRIGGER,
                "trace_id": "act00001",
                "span_id": "req1",
                "data": {"step_id": TEST_TRIGGER, "requested_by": "user", "reason": "x"},
            },
            {
                "event": "skip_authorization",
                "step": TEST_TRIGGER,
                "trace_id": "act00001",
                "span_id": "auth1",
                "parent_span_id": "req1",
                "data": {"step_id": TEST_TRIGGER, "authorized_by": "mike", "conditions": ""},
            },
            {
                "event": "step_skipped",
                "step": TEST_TRIGGER,
                "trace_id": "act00001",
                "span_id": "skip1",
                "parent_span_id": "auth1",
                "data": {
                    "disposition": "skip_with_authorization",
                    "skip_authorization_span_id": "auth1",
                },
            },
        ]
        replay = ob.build_activation_replay_index(events, decls, "act00001")
        obl = ob.resolve_obligation(
            kind="criterion",
            replay=replay,
            step_status={TEST_TRIGGER: "skipped", TERMINAL_STEP: "completed"},
            consumer_step=TERMINAL_STEP,
            criterion="triggered_test_spec.stage == done",
            raw_verdict="error",
        )
        self.assertEqual(obl["disposition"], ob.WAIVED_BY_SKIP)
        self.assertEqual(obl["producer_step"], TEST_TRIGGER)
        self.assertEqual(obl["authorization_span_id"], "auth1")

    def test_unauthorized_skip_refuses(self):
        from lib import pipeline_obligations as ob

        decls = {
            TEST_TRIGGER: {"exit_criteria": ["triggered_test_spec.uid exists"]},
        }
        events = [
            {
                "event": "step_skipped",
                "step": TEST_TRIGGER,
                "trace_id": "act00001",
                "span_id": "skip1",
                "data": {"disposition": "skip_with_authorization"},
            }
        ]
        replay = ob.build_activation_replay_index(events, decls, "act00001")
        obl = ob.resolve_obligation(
            kind="criterion",
            replay=replay,
            step_status={TEST_TRIGGER: "skipped"},
            consumer_step=TERMINAL_STEP,
            criterion="triggered_test_spec.stage == done",
            raw_verdict="error",
        )
        self.assertEqual(obl["disposition"], ob.UNAUTHORIZED_SKIP)


@unittest.skipUnless(HIST_RUN.is_dir(), "historical run 635b62b7 not present")
class GovernedSkipsHistoricalReplay(unittest.TestCase):
    def test_ac1_ac3_sandbox_revalidate_and_terminal_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _scaffold(Path(tmp))
            run_copy = _copy_historical(root)
            src_before = (HIST_RUN / "run.jsonl").read_text()
            eng = _load_engine(root)

            # Append-only on the sandbox copy — never touch the live historical log.
            verdict = eng.action_verify_step(
                HIST_ACTIVATION, TERMINAL_STEP, "talos-t41", dry_run=False
            )
            self.assertEqual(
                verdict, "pass",
                f"AC1: authorized-skip terminal criteria must pass, got {verdict!r}",
            )

            # Terminal-verify: historical v1 receipts lack tested_commit_sha, so the
            # v2 weld's provenance gate would refuse independently of the skip fix.
            # Stub only that gate; the skip revalidation path under test must still
            # clear gaps and return complete. Live reconciliation of provenance on
            # 635b62b7 remains append-only and separately authorized (d7db77d8 #3).
            import subprocess
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "sandbox"], cwd=root, check=True)
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            eng.assert_one_unchanged_tested_sha = lambda *a, **k: sha

            tv = eng.action_terminal_verify(
                HIST_ACTIVATION, "talos-t41", dry_run=False, tested_sha=sha
            )
            self.assertEqual(
                tv, "complete",
                f"AC3: sandboxed historical re-verify must complete, got {tv!r}",
            )

            # Live historical log must be byte-identical (sandbox only was mutated).
            self.assertEqual(src_before, (HIST_RUN / "run.jsonl").read_text())
            # Sandbox log grew append-only.
            self.assertGreater(
                len((run_copy / "run.jsonl").read_text()),
                len(src_before),
            )

    def test_ac2_strip_authorization_refuses_apply_and_criterion(self):
        """Same shape minus skip_authorization → apply-skip and criterion refuse."""
        from lib import pipeline_obligations as ob

        decls = {
            TEST_TRIGGER: {"exit_criteria": ["triggered_test_spec.uid exists"]},
        }
        # Request present, authorization absent.
        events = [
            {
                "event": "skip_request",
                "step": TEST_TRIGGER,
                "trace_id": "act00001",
                "span_id": "req1",
                "data": {"step_id": TEST_TRIGGER, "requested_by": "user", "reason": "x"},
            },
        ]
        replay = ob.build_activation_replay_index(events, decls, "act00001")
        with self.assertRaises(ValueError):
            ob.require_ordered_skip_chain(replay, TEST_TRIGGER)

        # Skipped without auth chain → unauthorized at criterion resolve.
        events.append(
            {
                "event": "step_skipped",
                "step": TEST_TRIGGER,
                "trace_id": "act00001",
                "span_id": "skip1",
                "data": {"disposition": "skip_with_authorization"},
            }
        )
        replay = ob.build_activation_replay_index(events, decls, "act00001")
        obl = ob.resolve_obligation(
            kind="criterion",
            replay=replay,
            step_status={TEST_TRIGGER: "skipped"},
            consumer_step=TERMINAL_STEP,
            criterion="triggered_test_spec.stage == done",
            raw_verdict="error",
        )
        self.assertEqual(obl["disposition"], ob.UNAUTHORIZED_SKIP)
        row = ob.criterion_result_from_obligation(obl)
        self.assertEqual(row["verdict"], "error")


if __name__ == "__main__":
    unittest.main()
