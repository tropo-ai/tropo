"""Gauntlet tests for engine defect aaf96178 — `--dry-run` silently no-ops on most actions.

Incident (2026-07-04): a prep agent ran `9e7003b1.py --dry-run ... mark-superseded ...`
as a "safe preview" and it WROTE to disk for real — no [DRY-RUN] banner, exit 0, no
signal the write happened. Root cause: the global --dry-run argparse flag was only
wired into bootstrap + trigger-step; every other mutating action ignored it outright.

Invariant under test (per aaf96178 + Talos's fix, 2026-07-05):
    --dry-run must NEVER silently no-op. For every mutating action, --dry-run must
    either:
      (a) produce ZERO on-disk writes + print/return a "[DRY-RUN]" banner, or
      (b) hard-error cleanly (ValidationError / ContractError / SkipAuthError)
          BEFORE any write happens.
    It must never reach exit 0 having written something without saying so.

This suite exercises EVERY entry in the CLI dispatch table's mutating-action set:
bootstrap, step-start, step-complete, verify-step, step-fail, skip-request,
authorize-skip, apply-skip, pause, resume, terminal-verify, amend-step-criteria,
trigger-step, complete-workflow, mark-superseded.

Uses temp copies of real vault/files + real pipeline-run folders (never touches the
live vault). Two fixtures are used:
  - b6a8cd32 / 896e6c9b (v1.78 test-pipeline close-attempt run) — general action coverage.
  - ad02f944 / 8917bc56 (v1.77 dev-pipeline run; the actual B3-ext/9d4f7e21 case) —
    complete-workflow + trigger-step (the action whose OWN "canonical" dry-run pattern
    had the unconditional-O_EXCL-write bug fixed here).
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_VAULT_TOOLS = Path(__file__).resolve().parent.parent
_TROPO_SCRIPTS = Path(__file__).resolve().parents[3] / ".tropo" / "scripts"
sys.path.insert(0, str(_TROPO_SCRIPTS))

spec = importlib.util.spec_from_file_location("eng", str(_VAULT_TOOLS / "9e7003b1.py"))
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

_REAL_VAULT_ROOT = Path(__file__).resolve().parents[3]
_REAL_FILES = _REAL_VAULT_ROOT / "vault" / "files"
_REAL_RUNS = _REAL_VAULT_ROOT / "vault" / "pipeline-runs"

# Fixture 1: v1.78 test-pipeline close-attempt run — broad action-surface coverage.
_ACT_1, _PR_1, _RUN_1 = "b6a8cd32", "896e6c9b", "dev-pipeline-896e6c9b-2026-07-02"
# Fixture 2: v1.77 dev-pipeline run — the real 9d4f7e21 / B3-ext case + trigger-step.
_ACT_2, _PR_2, _RUN_2 = "ad02f944", "8917bc56", "dev-pipeline-8917bc56-2026-07-01"


def _tree_hash(root: Path) -> dict:
    """Map relative path -> sha256 for every file under root."""
    out = {}
    for f in sorted(root.rglob("*")):
        if f.is_file():
            out[str(f.relative_to(root))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


class DryRunNeverWritesTestCase(unittest.TestCase):
    """Base class: builds one shared tmp-vault copy for all test methods.

    Dry-run must write nothing, so reusing one class-scoped tmp copy across every
    test method is safe (and ~30x cheaper than re-copying vault/files per test).
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dry-run-gauntlet-")).resolve()
        dest_files = cls.tmp / "vault" / "files"
        shutil.copytree(_REAL_FILES, dest_files)
        dest_runs = cls.tmp / "vault" / "pipeline-runs"
        dest_runs.mkdir(parents=True, exist_ok=True)
        for run_name in (_RUN_1, _RUN_2):
            shutil.copytree(_REAL_RUNS / run_name, dest_runs / run_name)

        cls._orig = {
            "VAULT_ROOT": eng.VAULT_ROOT,
            "VAULT_FILES": eng.VAULT_FILES,
            "PIPELINE_RUNS_FOLDER": eng.PIPELINE_RUNS_FOLDER,
        }
        eng.VAULT_ROOT = cls.tmp
        eng.VAULT_FILES = dest_files
        eng.PIPELINE_RUNS_FOLDER = dest_runs

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._orig.items():
            setattr(eng, k, v)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def assert_dry_run_never_writes(self, fn, *args, **kwargs):
        """Call fn(*args, dry_run=True, **kwargs); assert zero writes regardless of outcome.

        Either fn returns a string containing "[DRY-RUN]" (case a), or it raises one
        of the recognized clean-error types (case b). Any other outcome — including a
        silent successful return with no banner — fails the test (that IS the
        aaf96178 defect class).
        """
        before = _tree_hash(self.tmp)
        try:
            result = fn(*args, dry_run=True, **kwargs)
        except (eng.ValidationError, eng.ContractError, eng.SkipAuthError) as e:
            after = _tree_hash(self.tmp)
            self.assertEqual(before, after,
                             f"{fn.__name__}: hard-error path still wrote files: {e}")
            return ("hard_error", e)
        after = _tree_hash(self.tmp)
        self.assertEqual(before, after,
                         f"{fn.__name__}: dry_run=True produced on-disk writes — "
                         f"the exact aaf96178 defect class (silent write, no banner)")
        result_str = result if isinstance(result, str) else str(result)
        self.assertIn("[DRY-RUN]", result_str,
                      f"{fn.__name__}: dry_run=True wrote nothing (good) but produced no "
                      f"[DRY-RUN] banner — caller has no signal this was a preview")
        return ("dry_run_banner", result)


class TestMutatingActionsNeverWriteUnderDryRun(DryRunNeverWritesTestCase):
    """One test per mutating CLI action. Fixture: b6a8cd32 / 896e6c9b."""

    def test_mark_superseded_banner_path(self):
        """THE headline incident action: exact command shape from the aaf96178 report."""
        outcome, result = self.assert_dry_run_never_writes(
            eng.action_mark_superseded, _ACT_1, "ad02f944", "other", "argus",
        )
        self.assertEqual(outcome, "dry_run_banner",
                         "mark-superseded with a valid owner+reason must reach the banner path")

    def test_step_fail_banner_path(self):
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_step_fail, _ACT_1, "9d4f7e21", "argus",
            "E", "test-failure", "retry", "synthetic-test-detail", 0,
        )
        self.assertEqual(outcome, "dry_run_banner")

    def test_skip_request_banner_path(self):
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_skip_request, _ACT_1, "9d4f7e21", "argus", "synthetic-test-reason",
        )
        self.assertEqual(outcome, "dry_run_banner")

    def test_authorize_skip_banner_path(self):
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_authorize_skip, _ACT_1, "9d4f7e21", "deadbeef", "", "argus",
        )
        self.assertEqual(outcome, "dry_run_banner")

    def test_apply_skip_hard_errors_cleanly(self):
        """No prior skip_authorization for this step in the fixture -> SkipAuthError."""
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_apply_skip, _ACT_1, "9d4f7e21", "argus",
        )
        self.assertEqual(outcome, "hard_error")

    def test_pause_scopeless_banner_path(self):
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_pause, _ACT_1, "synthetic-test-pause", "argus",
        )
        self.assertEqual(outcome, "dry_run_banner")

    def test_resume_hard_errors_when_not_paused(self):
        """Fixture run_status is 'active', not 'paused' -> ContractError."""
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_resume, _ACT_1, "some-principal", "argus",
        )
        self.assertEqual(outcome, "hard_error")

    def test_terminal_verify_banner_path(self):
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_terminal_verify, _ACT_1, "argus",
        )
        self.assertEqual(outcome, "dry_run_banner")

    def test_amend_step_criteria_banner_path(self):
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_amend_step_criteria, _ACT_1, "3e0bb81e", ["file:README.md.exists"], "argus",
        )
        self.assertEqual(outcome, "dry_run_banner")

    def test_verify_step_banner_path(self):
        """3e0bb81e is 'completed' (not yet verified) in this fixture — real banner path,
        exercising the actual DSL criteria recompute (read-only) without writing the receipt."""
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_verify_step, _ACT_1, "3e0bb81e", "argus",
        )
        self.assertEqual(outcome, "dry_run_banner")

    def test_step_start_hard_errors_when_not_eligible(self):
        """No step is currently eligible in this fixture -> ContractError."""
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_step_start, _ACT_1, "9d4f7e21", "argus",
        )
        self.assertEqual(outcome, "hard_error")

    def test_step_complete_hard_errors_when_not_started(self):
        """No step is currently 'started' in this fixture -> ContractError."""
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_step_complete, _ACT_1, "9d4f7e21", ["synthetic:artifact"], "argus",
        )
        self.assertEqual(outcome, "hard_error")

    def test_bootstrap_hard_errors_when_already_bootstrapped(self):
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_bootstrap, _ACT_1, None,
        )
        self.assertEqual(outcome, "hard_error")


class TestCompleteWorkflowAndTriggerStep(DryRunNeverWritesTestCase):
    """Fixture: ad02f944 / 8917bc56 — the real v1.77 B3-ext / 9d4f7e21 case."""

    def test_complete_workflow_banner_path_and_b3ext_passes(self):
        """The item-2 regression case: complete-workflow --dry-run on ad02f944 must
        now pass B3-ext (9d4f7e21's real doc-leg-completed substrate) and reach the
        terminal banner — not BLOCKED, and not a silent write."""
        before = _tree_hash(self.tmp)
        result = eng.action_complete_workflow(_ACT_2, "talos", dry_run=True)
        after = _tree_hash(self.tmp)
        self.assertEqual(before, after, "complete-workflow --dry-run must write nothing")
        self.assertIn("[DRY-RUN]", result)
        self.assertIn("would emit workflow_complete", result,
                      "all close gates (including the fixed B3-ext branch-applicability "
                      "check on 9d4f7e21) must pass for the dry-run banner to be reached")

    def test_trigger_step_does_not_create_spec_file_under_dry_run(self):
        """THE trigger-step bug this ticket also fixed: pre-fix, this unconditionally
        O_EXCL-created the triggered-spec file for real even under --dry-run, as long
        as the UID didn't already exist on disk.

        ad02f944's real dev-spec (ba454e56) already has a triggered doc-pipeline leg
        (B5 single-cascade idempotency would refuse a second one before reaching the
        file-create code at all), so this uses a synthetic activation + dev-spec pair
        with NO prior triggered legs — the actual precondition the O_EXCL bug fires
        under — to exercise the real file-create code path.
        """
        synth_activation_uid = "11112222"
        synth_dev_spec_uid = "33334444"
        eng.write_vault_entry(synth_activation_uid,
                              {"uid": synth_activation_uid, "type": "activation",
                               "activation_class": "pipeline", "dev_spec_uid": synth_dev_spec_uid},
                              "synthetic fixture — dry-run trigger-step test\n")
        eng.write_vault_entry(synth_dev_spec_uid,
                              {"uid": synth_dev_spec_uid, "type": "dev-spec"},
                              "synthetic fixture — dry-run trigger-step test\n")

        fresh_uid = "abcdef12"
        spec_path = eng.VAULT_FILES / f"{fresh_uid}.md"
        self.assertFalse(spec_path.exists(), "test precondition: fresh UID must not pre-exist")

        before = _tree_hash(self.tmp)
        result = eng.action_trigger_step(
            synth_activation_uid, "9d4f7e21", fresh_uid,
            "---\nuid: abcdef12\ntype: doc-spec\n---\nbody\n",
            "5a4337ff", "doc-pipeline", "talos", dry_run=True,
        )
        after = _tree_hash(self.tmp)
        self.assertFalse(spec_path.exists(),
                         "trigger-step --dry-run must NOT create the triggered-spec file "
                         "(the exact pre-fix TOCTOU/unconditional-O_EXCL bug)")
        self.assertEqual(before, after, "trigger-step --dry-run must write nothing at all")
        self.assertTrue(result.get("dry_run"))

    def test_trigger_step_hard_errors_on_real_b5_collision(self):
        """ad02f944's real dev-spec already triggered a doc leg — B5 single-cascade
        idempotency must still refuse (cleanly, zero writes) even under --dry-run;
        preview must not paper over a real contract violation."""
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_trigger_step, _ACT_2, "9d4f7e21", "abcdef34",
            "---\nuid: abcdef34\n---\nbody\n", "5a4337ff", "doc-pipeline", "talos",
        )
        self.assertEqual(outcome, "hard_error")


class TestHarnessSanityControl(unittest.TestCase):
    """Positive control: proves _tree_hash actually detects a real write.

    Without this, a bug in the comparison helper could make every test above pass
    vacuously (e.g. if _tree_hash always returned {}). Uses its own private tmp
    copy (not the shared class-level fixture) since this test deliberately writes.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dry-run-control-")).resolve()
        dest_files = self.tmp / "vault" / "files"
        shutil.copytree(_REAL_FILES, dest_files)
        dest_runs = self.tmp / "vault" / "pipeline-runs"
        dest_runs.mkdir(parents=True, exist_ok=True)
        shutil.copytree(_REAL_RUNS / _RUN_1, dest_runs / _RUN_1)
        self._orig = {
            "VAULT_ROOT": eng.VAULT_ROOT,
            "VAULT_FILES": eng.VAULT_FILES,
            "PIPELINE_RUNS_FOLDER": eng.PIPELINE_RUNS_FOLDER,
        }
        eng.VAULT_ROOT = self.tmp
        eng.VAULT_FILES = dest_files
        eng.PIPELINE_RUNS_FOLDER = dest_runs

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(eng, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mark_superseded_without_dry_run_actually_writes(self):
        """Sanity control: the SAME call as the headline banner-path test, but with
        dry_run=False, must actually write (proves the harness can tell the difference)."""
        before = _tree_hash(self.tmp)
        result = eng.action_mark_superseded(_ACT_1, "ad02f944", "other", "argus", dry_run=False)
        after = _tree_hash(self.tmp)
        self.assertNotEqual(before, after,
                            "control failed: mark-superseded without --dry-run wrote nothing — "
                            "the tree-hash comparison method itself may be broken")
        self.assertNotIn("[DRY-RUN]", result)


if __name__ == "__main__":
    unittest.main()
