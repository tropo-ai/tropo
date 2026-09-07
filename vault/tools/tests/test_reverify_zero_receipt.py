"""reverify-step zero-receipt extension (argus-a162 request, 2026-08-29, built by
talos-t53; thread evt_b51c083be28ac6fe_00000265).

A VERIFIED instrument step with ZERO release-verification-receipt events on its
run may now be re-opened — alongside the pre-existing superseded-candidate case.
The invariant that must not move: a receipt naming the ACTIVE candidate refuses
untouched. Full-validator / external-test / cold-walk on the v1.93 run all
genuinely passed through paths that never called emit_release_verification_
receipt; zero receipts means "no green was ever recorded", not "nothing was
invalidated".

Fixtures build on the frozen d445af8b corpus (see test_verify_step_evidence_
passthrough_b3f620fc) and synthesize the needed states with the isolated
engine's own event primitives — nothing is hand-forged.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "d445af8b_verify"
REAL_ACTIVATION_UID = "2e9f4dcd"
REAL_RUN_FOLDER = "release-pipeline-d445af8b-2026-08-27"
ACTIVE_CANDIDATE = "f4e569ec3822079f3ff46ba1c5a63120cfbbb50490158aa1f0f1369d184bfc1f"
HARNESS_STEP = "a0f2bea8"      # release-harness-gate instrument node
ACTOR = "talos-t53"


def _load_isolated_engine(tmp: Path):
    shutil.copytree(STUDIO_ROOT / "vault" / "tools", tmp / "vault" / "tools",
                     ignore=shutil.ignore_patterns("__pycache__", "tests"))
    shutil.copytree(STUDIO_ROOT / ".tropo" / "scripts", tmp / ".tropo" / "scripts",
                     ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / "vault" / "files").mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "reverify_engine_%s" % abs(hash(str(tmp))),
        tmp / "vault" / "tools" / "9e7003b1.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module.VAULT_ROOT == tmp, "engine did not resolve to the isolated copy"
    return module


def _copy_scenario(tmp: Path) -> Path:
    for name in (REAL_ACTIVATION_UID, "d445af8b"):
        shutil.copy(FIXTURES / f"{name}.md", tmp / "vault" / "files" / f"{name}.md")
    run_dir = tmp / "vault" / "pipeline-runs" / REAL_RUN_FOLDER
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ("run.jsonl", "run.state.json"):
        shutil.copy(FIXTURES / name, run_dir / name)
    return run_dir


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


class ReverifyBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)
        self.run_dir = _copy_scenario(self.tmp)

    def make_verified(self, engine, run_dir, step, with_receipt=None):
        """Drive the step to 'verified' through the engine's own primitives.
        with_receipt: None -> no release-verification-receipt on the run;
        a sha string -> one harness receipt naming that candidate sha."""
        # The frozen scenario has a0f2bea8 at 'completed' with FAIL receipts on
        # the journal; strip the journal back to before its first receipt so we
        # control the receipt state precisely.
        rows = [json.loads(l) for l in
                (run_dir / "run.jsonl").read_text().splitlines() if l.strip()]
        kept, dropped = [], False
        for r in rows:
            if r.get("event") == "verification_receipt" and (r.get("step") == step or (r.get("data") or {}).get("step_id") == step):
                dropped = True
            if not dropped:
                kept.append(r)
        (run_dir / "run.jsonl").write_text(
            "\n".join(json.dumps(r) for r in kept) + "\n")
        ev = engine.make_event(
            "verification_receipt", ACTOR, step=step, trace_id=REAL_ACTIVATION_UID,
            data={"verifier_role_resolved": "verification_command",
                  "verdict": "pass", "per_criterion": [],
                  "rubric_scores": {"exit_criteria_coverage": 1.0},
                  "overall_rationale": "synthetic green for fixture"})
        engine.append_event(run_dir, ev)
        if with_receipt is not None:
            from lib import release_verify as _rv  # engine's own lib copy
            receipt = engine.make_event(
                _rv.RECEIPT_KIND, ACTOR, step=step, trace_id=REAL_ACTIVATION_UID,
                data={"receipt_kind": _rv.RECEIPT_KIND,
                      "instrument": _rv.instrument_for_node(step),
                      "release_run_uid": "d445af8b",
                      "candidate_sha256": with_receipt,
                      "verdict": "pass",
                      "executor_or_attester": ACTOR,
                      "execution_mode": "machine",
                      "evidence_ref": f"{step}@fixture",
                      "started_at": "2026-08-29T00:00:00Z",
                      "completed_at": "2026-08-29T00:00:00Z"})
            engine.append_event(run_dir, receipt)


class ZeroPriorReceiptsMayReopen(ReverifyBase):
    def test_a_verified_instrument_step_with_no_receipt_reopens(self):
        self.make_verified(self.engine, self.run_dir, HARNESS_STEP, with_receipt=None)
        state = self.engine.derive_state(self.engine.read_events(self.run_dir))
        self.assertEqual(state["step_status"][HARNESS_STEP], "verified")
        result = self.engine.action_reverify_step(
            REAL_ACTIVATION_UID, HARNESS_STEP, ACTOR, reason="never recorded")
        self.assertIn("reverify_opened", result)
        state = self.engine.derive_state(self.engine.read_events(self.run_dir))
        self.assertEqual(state["step_status"][HARNESS_STEP], "declared")

    def test_a_skipped_instrument_step_with_no_receipt_reopens(self):
        """The live-run case this extension exists for: cold-walk (c6b61fb9) is
        'skipped', not 'verified' — found by dry-running against the real run,
        not by reading. Skipped is not a green; reopening it erases nothing."""
        self.make_verified(self.engine, self.run_dir, HARNESS_STEP, with_receipt=None)
        run_dir = self.run_dir
        self.engine.append_event(run_dir, self.engine.make_event(
            "skip_request", ACTOR, step=HARNESS_STEP, trace_id=REAL_ACTIVATION_UID,
            data={"step_id": HARNESS_STEP, "requested_by": ACTOR,
                  "reason": "fixture: enter skipped"}))
        self.engine.append_event(run_dir, self.engine.make_event(
            "step_skipped", ACTOR, step=HARNESS_STEP, trace_id=REAL_ACTIVATION_UID,
            data={"step_id": HARNESS_STEP, "authorized_by": ACTOR}))
        state = self.engine.derive_state(self.engine.read_events(run_dir))
        self.assertEqual(state["step_status"][HARNESS_STEP], "skipped")
        result = self.engine.action_reverify_step(
            REAL_ACTIVATION_UID, HARNESS_STEP, ACTOR, reason="never recorded")
        self.assertIn("reverify_opened", result)
        state = self.engine.derive_state(self.engine.read_events(run_dir))
        self.assertEqual(state["step_status"][HARNESS_STEP], "declared")

    def test_zero_receipt_dry_run_writes_nothing(self):
        self.make_verified(self.engine, self.run_dir, HARNESS_STEP, with_receipt=None)
        before = _md5(self.run_dir / "run.jsonl")
        result = self.engine.action_reverify_step(
            REAL_ACTIVATION_UID, HARNESS_STEP, ACTOR, reason="never recorded",
            dry_run=True)
        self.assertIn("would reopen", result)
        self.assertEqual(_md5(self.run_dir / "run.jsonl"), before)


class SupersededStillReopens(ReverifyBase):
    def test_superseded_only_receipt_reopens_as_before(self):
        stale = "4d0d7fd9" + "0" * 56
        self.make_verified(self.engine, self.run_dir, HARNESS_STEP,
                           with_receipt=stale)
        result = self.engine.action_reverify_step(
            REAL_ACTIVATION_UID, HARNESS_STEP, ACTOR, reason="superseded candidate")
        self.assertIn("reverify_opened", result)
        self.assertIn("4d0d7fd9", result)


class ActiveGreenStillRefuses(ReverifyBase):
    def test_receipt_naming_the_active_candidate_refuses(self):
        self.make_verified(self.engine, self.run_dir, HARNESS_STEP,
                           with_receipt=ACTIVE_CANDIDATE)
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_reverify_step(
                REAL_ACTIVATION_UID, HARNESS_STEP, ACTOR, reason="must refuse")
        self.assertIn("ACTIVE", str(ctx.exception))
        state = self.engine.derive_state(self.engine.read_events(self.run_dir))
        self.assertEqual(state["step_status"][HARNESS_STEP], "verified")


class PreconditionsStillRefuse(ReverifyBase):
    def test_non_verified_step_refuses(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_reverify_step(
                REAL_ACTIVATION_UID, HARNESS_STEP, ACTOR, reason="x")
        self.assertIn("not 'verified'", str(ctx.exception))

    def test_non_instrument_step_refuses(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_reverify_step(
                REAL_ACTIVATION_UID, "8654900a", ACTOR, reason="x")
        self.assertIn("not one of the AC7 instrument nodes", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
