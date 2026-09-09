#!/usr/bin/env python3
"""step-redeclare after a ruled re-open (v1.95 candidate #3, metis-g123, 2026-09-06 16:38Z).

THE WEDGE: reverify-step returned the validator step 4262d5fa to 'declared'
(its release-verification receipt named the retired candidate #2); the re-drive
refused on one studio-side finding and left the step 'started'; step-redeclare
then REFUSED -- "carries 2 completion/receipt event(s)" -- because
_redeclare_scan_active reset only at step_declared and
package_superseded.invalidated_steps, so the 13:10Z completion and receipt from
the retired candidate still counted. reverify-step refused too (not 'verified').
No ruled verb reached a re-driven compare after a refusal.

THE CURE: step_reverify_opened and step_reopened for the same step are resets;
only rows after the latest reset count. Each clause a test, on the frozen
fixture of the real sealed run (vault/tools/tests/fixtures/f015af4a6a0a_sealed):

  1. verified -> reverify_opened -> started -> redeclare ALLOWED (dry run and real).
  2. NEGATIVE CONTROL: the same journal WITHOUT the reverify_opened row (a
     step_started laid over the green) -> redeclare REFUSES naming the 2 rows.
  3. THE REOPEN TWIN: the produce step verified -> candidate_invalidated ->
     step_reopened -> started -> redeclare ALLOWED.
  4. Guardrail 1c still holds: the reset never erases a green -- a completion
     AFTER the reset still refuses.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = STUDIO_ROOT / "vault" / "tools" / "tests" / "fixtures" / "f015af4a6a0a_sealed"
ACTIVATION = "f015637f34b1"
RUN_UID = "f015af4a6a0a"
RUN_FOLDER = "release-pipeline-f015af4a6a0a-2026-09-05"
VALIDATOR = "4262d5fa"
PRODUCE = "8654900a"
SEALED_SHA = "2a480f4c237b4de1ee36a8eb442bdd2e89f9aba761557a60a0f7ca3c28a58021"


def _redeclare_suite():
    spec = importlib.util.spec_from_file_location(
        "_test_step_redeclare_for_reverify", Path(__file__).with_name("test_step_redeclare.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _SealedRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _redeclare_suite()._load_isolated_engine(self.tmp)
        for uid in (ACTIVATION, RUN_UID):
            shutil.copy(FIXTURE / f"{uid}.md", self.tmp / "vault" / "files" / f"{uid}.md")
        self.run_dir = self.tmp / "vault" / "pipeline-runs" / RUN_FOLDER
        self.run_dir.mkdir(parents=True)
        for name in ("run.jsonl", "run.state.json"):
            shutil.copy(FIXTURE / name, self.run_dir / name)
        self.journal = self.run_dir / "run.jsonl"

    def _rows(self):
        return [json.loads(l) for l in self.journal.read_text(encoding="utf-8").splitlines() if l.strip()]

    def _append(self, event, step, data=None, actor="test-driver"):
        base = dict(self._rows()[-1])
        base.update({"event": event, "step": step, "actor": actor, "data": data or {}})
        with self.journal.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(base) + "\n")
        state = self.engine.derive_state(self._rows())
        self.engine.write_run_state_json(self.run_dir, {"uid": RUN_UID}, state, ACTIVATION)
        return state

    def _status(self, step):
        return self.engine.derive_state(self._rows())["step_status"].get(step)


class RedeclareAfterReverify(_SealedRun):
    def test_the_frozen_run_holds_the_validator_verified_with_two_green_rows(self):
        self.assertEqual(self._status(VALIDATOR), "verified")
        greens = [r for r in self._rows() if r.get("step") == VALIDATOR
                  and r.get("event") in ("step_completed", "verification_receipt")]
        self.assertEqual(len(greens), 2)

    def test_reverify_then_started_then_redeclare_is_allowed(self):
        self._append("step_reverify_opened", VALIDATOR, {"reason": "receipt named the retired candidate"})
        self.assertEqual(self._status(VALIDATOR), "declared")
        self._append("step_started", VALIDATOR)
        self.assertEqual(self._status(VALIDATOR), "started")
        dry = self.engine.action_step_redeclare(ACTIVATION, VALIDATOR, "test-driver",
                                                reason="compare refused on a studio-side finding, cured",
                                                failed_invocation="tropo-release-run.py 4262d5fa compare_current fail",
                                                dry_run=True)
        self.assertIn("would emit step_redeclared", dry)
        result = self.engine.action_step_redeclare(ACTIVATION, VALIDATOR, "test-driver",
                                                   reason="compare refused on a studio-side finding, cured",
                                                   failed_invocation="tropo-release-run.py 4262d5fa compare_current fail")
        self.assertEqual(result, f"redeclared:{VALIDATOR}")
        self.assertEqual(self._status(VALIDATOR), "declared")

    def test_negative_control_without_the_reverify_row_still_refuses(self):
        """A step_started laid over a green with no ruled reset is the forgery
        guardrail 1c closes; the widening must not open it."""
        self._append("step_started", VALIDATOR)
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(ACTIVATION, VALIDATOR, "test-driver",
                                              reason="probe", failed_invocation="probe")
        self.assertIn("carries 2 completion/receipt", str(ctx.exception))

    def test_a_green_after_the_reset_still_refuses(self):
        self._append("step_reverify_opened", VALIDATOR, {"reason": "receipt named the retired candidate"})
        self._append("step_started", VALIDATOR)
        self._append("step_completed", VALIDATOR, {"artifact_links": []})
        self._append("step_started", VALIDATOR)
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(ACTIVATION, VALIDATOR, "test-driver",
                                              reason="probe", failed_invocation="probe")
        self.assertIn("completion/receipt", str(ctx.exception))


class RedeclareAfterReopen(_SealedRun):
    def test_reopen_then_started_then_redeclare_is_allowed(self):
        self._append("tropo.release.candidate_invalidated", None,
                     {"release_run_uid": RUN_UID, "candidate_sha256": SEALED_SHA, "reason": "ruling"})
        self._append("step_reopened", PRODUCE,
                     {"step_id": PRODUCE, "previous_status": "verified", "reason": "ruling",
                      "invalidated_candidate_sha256": SEALED_SHA, "reopened_by": "test-driver"})
        self.assertEqual(self._status(PRODUCE), "declared")
        self._append("step_started", PRODUCE)
        result = self.engine.action_step_redeclare(ACTIVATION, PRODUCE, "test-driver",
                                                   reason="build refused at invocation, cured",
                                                   failed_invocation="tropo-build-release.py exit 3")
        self.assertEqual(result, f"redeclared:{PRODUCE}")
        self.assertEqual(self._status(PRODUCE), "declared")


if __name__ == "__main__":
    unittest.main()
