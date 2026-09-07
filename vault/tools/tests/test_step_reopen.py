#!/usr/bin/env python3
"""`9e7003b1.py reopen-step` — the narrow verb (Metis G123's ruling, v1.95
candidate #3, 2026-09-06): return the produce step (mint+build, 8654900a) to
DECLARED after the run's sealed candidate was INVALIDATED on the record.

THE GAP: candidate #2 sealed at the candidate phase (12/12) and was then
blocked by Vela's AC5 walk; Mike ruled "cure and cut #3". The produce step
read 'verified'; step-redeclare refuses (not 'started'); reverify-step
refuses (not an AC7 instrument node); the standalone build is the rehearsal
door; the runner skips terminal steps. The runner path had never rebuilt
after a seal. Two dry probes on the clone measured every refusal.

FIXTURE: the real sealed run, frozen — vault/tools/tests/fixtures/
f015af4a6a0a_sealed/ carries the activation entry, the run entry, and the
journal + state exactly as they stood after candidate #2 sealed (journal
rows through the harness step start; 8654900a 'verified'; one
tropo.release.candidate_built, digest 2a480f4c…; no invalidation). The
engine is loaded as an ISOLATED COPY (test_step_redeclare's loader) so its
VAULT_ROOT resolves to a temp studio, never the live one.

THE CONTRACT, each clause a test:
  1. REFUSES WHILE A CANDIDATE IS ACTIVE (negative control) — on the frozen
     run as it stands, naming the supersede command.
  2. REOPENS AFTER INVALIDATION — the invalidation is written by the REAL
     tool (tropo-supersede-release-package.py --candidate-only
     --invalidate-candidate), then reopen-step: status verified -> declared,
     run.state.json agrees, no completion/receipt row removed, the
     step_reopened row carries previous status, reason, digest, actor.
  3. RED WITHOUT THE VERB — the same journal with the invalidation row but
     no step_reopened row still reads 'verified' (the fold does nothing on
     candidate_invalidated alone).
  4. REPLAY GUARD — a hand-authored step_reopened over a LIVE candidate
     leaves the step 'verified'.
  5. ONLY THE PRODUCE STEP — 4262d5fa (verified) refuses by name.
  6. THE RUNNER DOOR — after the reopen, resume-from-log lists 8654900a
     eligible again; before, it does not.
  7. DRY RUN writes nothing (md5 of journal and state before/after).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = STUDIO_ROOT / "vault" / "tools" / "tests" / "fixtures" / "f015af4a6a0a_sealed"
ACTIVATION = "f015637f34b1"
RUN_UID = "f015af4a6a0a"
RUN_FOLDER = "release-pipeline-f015af4a6a0a-2026-09-05"
PRODUCE = "8654900a"
VALIDATOR = "4262d5fa"
SEALED_SHA = "2a480f4c237b4de1ee36a8eb442bdd2e89f9aba761557a60a0f7ca3c28a58021"
REASON = "Mike ruled 2026-09-06 13:40Z: cure and cut candidate #3 (Vela's AC5 walk f0157550b31b failed both arms)"


def _redeclare_suite():
    spec = importlib.util.spec_from_file_location(
        "_test_step_redeclare_for_reopen", Path(__file__).with_name("test_step_redeclare.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


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
        self.state = self.run_dir / "run.state.json"

    def _status(self, step: str) -> str:
        return json.loads(self.state.read_text())["step_status"].get(step)

    def _invalidate(self) -> None:
        """The ruled path: the real supersede tool retires the sealed candidate."""
        tool = self.tmp / "vault" / "tools" / "tropo-supersede-release-package.py"
        proc = subprocess.run(
            [sys.executable, str(tool), "--run-dir", str(self.run_dir), "--candidate-only",
             "--invalidate-candidate", SEALED_SHA, "--reason", REASON, "--actor", "test-driver"],
            capture_output=True, text=True, cwd=str(self.tmp))
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:] + proc.stdout[-400:])
        self.assertTrue(any(r.get("event") == "tropo.release.candidate_invalidated" for r in _rows(self.journal)))


class RefusesWhileACandidateIsActive(_SealedRun):
    def test_the_frozen_run_reads_verified_with_a_live_candidate(self):
        self.assertEqual(self._status(PRODUCE), "verified")
        pkg = self.engine.derive_state(_rows(self.journal))
        self.assertEqual(pkg["step_status"][PRODUCE], "verified")

    def test_reopen_refuses_and_names_the_invalidation_command(self):
        before = (_md5(self.journal), _md5(self.state))
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_reopen_step(ACTIVATION, PRODUCE, "test-driver", REASON)
        self.assertIn("still has an active candidate", str(ctx.exception))
        self.assertIn(SEALED_SHA[:12], str(ctx.exception))
        self.assertIn("--invalidate-candidate", str(ctx.exception))
        self.assertEqual(before, (_md5(self.journal), _md5(self.state)))

    def test_dry_run_refuses_the_same_way_and_writes_nothing(self):
        before = (_md5(self.journal), _md5(self.state))
        with self.assertRaises(self.engine.ContractError):
            self.engine.action_reopen_step(ACTIVATION, PRODUCE, "test-driver", REASON, dry_run=True)
        self.assertEqual(before, (_md5(self.journal), _md5(self.state)))


class ReopensAfterInvalidation(_SealedRun):
    def test_verified_returns_to_declared_and_no_green_is_erased(self):
        self._invalidate()
        greens_before = [r for r in _rows(self.journal)
                         if r.get("step") == PRODUCE and r.get("event") in ("step_completed", "verification_receipt")]
        self.assertTrue(greens_before)
        result = self.engine.action_reopen_step(ACTIVATION, PRODUCE, "test-driver", REASON)
        self.assertEqual(result, f"reopened:{PRODUCE}")
        self.assertEqual(self._status(PRODUCE), "declared")
        rows = _rows(self.journal)
        greens_after = [r for r in rows
                        if r.get("step") == PRODUCE and r.get("event") in ("step_completed", "verification_receipt")]
        self.assertEqual(greens_before, greens_after, "a completion or receipt row was removed")
        reopened = [r for r in rows if r.get("event") == "step_reopened"]
        self.assertEqual(len(reopened), 1)
        data = reopened[0]["data"]
        self.assertEqual(data["step_id"], PRODUCE)
        self.assertEqual(data["previous_status"], "verified")
        self.assertEqual(data["invalidated_candidate_sha256"], SEALED_SHA)
        self.assertEqual(data["reason"], REASON)
        self.assertEqual(data["reopened_by"], "test-driver")
        self.assertEqual(reopened[0]["actor"], "test-driver")

    def test_dry_run_after_invalidation_would_proceed_and_writes_nothing(self):
        self._invalidate()
        before = (_md5(self.journal), _md5(self.state))
        result = self.engine.action_reopen_step(ACTIVATION, PRODUCE, "test-driver", REASON, dry_run=True)
        self.assertIn("would emit step_reopened", result)
        self.assertIn("'verified' -> 'declared'", result)
        self.assertEqual(before, (_md5(self.journal), _md5(self.state)))

    def test_the_reopen_is_idempotent_by_refusal(self):
        self._invalidate()
        self.engine.action_reopen_step(ACTIVATION, PRODUCE, "test-driver", REASON)
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_reopen_step(ACTIVATION, PRODUCE, "test-driver", REASON)
        self.assertIn("'declared'", str(ctx.exception))

    def test_reason_and_actor_are_required(self):
        self._invalidate()
        with self.assertRaises(self.engine.ContractError):
            self.engine.action_reopen_step(ACTIVATION, PRODUCE, "test-driver", "   ")
        with self.assertRaises(self.engine.ContractError):
            self.engine.action_reopen_step(ACTIVATION, PRODUCE, "", REASON)
        self.assertEqual(self._status(PRODUCE), "verified")


class RedWithoutTheVerb(_SealedRun):
    def test_the_invalidation_alone_does_not_reopen(self):
        """The fold has no branch for candidate_invalidated: without the verb's
        row the step stays 'verified'. This is the gap the verb closes."""
        self._invalidate()
        state = self.engine.derive_state(_rows(self.journal))
        self.assertEqual(state["step_status"][PRODUCE], "verified")


class ReplayGuard(_SealedRun):
    def _hand_author_reopen(self):
        rows = _rows(self.journal)
        forged = dict(rows[-1])
        forged.update({"event": "step_reopened", "step": PRODUCE, "actor": "forger",
                       "data": {"step_id": PRODUCE, "previous_status": "verified",
                                "reason": "forged", "invalidated_candidate_sha256": SEALED_SHA,
                                "reopened_by": "forger"}})
        with self.journal.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(forged) + "\n")

    def test_a_hand_authored_reopen_over_a_live_candidate_leaves_verified(self):
        self._hand_author_reopen()
        state = self.engine.derive_state(_rows(self.journal))
        self.assertEqual(state["step_status"][PRODUCE], "verified")

    def test_the_same_row_after_a_real_invalidation_reopens(self):
        self._invalidate()
        self._hand_author_reopen()
        state = self.engine.derive_state(_rows(self.journal))
        self.assertEqual(state["step_status"][PRODUCE], "declared")


class OnlyTheProduceStep(_SealedRun):
    def test_the_validator_step_refuses_by_name(self):
        self._invalidate()
        self.assertEqual(self._status(VALIDATOR), "verified")
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_reopen_step(ACTIVATION, VALIDATOR, "test-driver", REASON)
        self.assertIn("not the produce step", str(ctx.exception))
        self.assertEqual(self._status(VALIDATOR), "verified")


class TheRunnerDoor(_SealedRun):
    def test_resume_from_log_lists_the_produce_step_eligible_only_after_reopen(self):
        before = self.engine.action_resume_from_log(ACTIVATION)
        self.assertNotIn(PRODUCE, [str(s) for s in before.get("eligible_steps") or []])
        self._invalidate()
        self.engine.action_reopen_step(ACTIVATION, PRODUCE, "test-driver", REASON)
        after = self.engine.action_resume_from_log(ACTIVATION)
        eligible = [str(s) for s in after.get("eligible_steps") or []]
        self.assertIn(PRODUCE, eligible, after)


class TheCliShape(unittest.TestCase):
    def test_reopen_step_is_a_subcommand_with_reason_and_actor_required(self):
        proc = subprocess.run([sys.executable, str(STUDIO_ROOT / "vault" / "tools" / "9e7003b1.py"),
                               "reopen-step", "--help"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--reason", proc.stdout)
        self.assertIn("--actor", proc.stdout)


if __name__ == "__main__":
    unittest.main()
