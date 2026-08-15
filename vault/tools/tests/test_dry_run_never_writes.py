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
import json
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

    def test_authorize_skip_hard_errors_without_request_or_principal(self):
        """d7db77d8: 8-hex authorized_by must resolve; prior skip_request required.

        Fixture call shape uses a phantom 8-hex authorizer and has no prior
        skip_request for this step — clean SkipAuthError before any write is
        the correct dry-run outcome (aaf96178 case b).
        """
        outcome, err = self.assert_dry_run_never_writes(
            eng.action_authorize_skip, _ACT_1, "9d4f7e21", "deadbeef", "", "argus",
        )
        self.assertEqual(outcome, "hard_error")
        self.assertIsInstance(err, eng.SkipAuthError)

    def test_authorize_skip_banner_path_with_prior_request(self):
        """Banner path: prior skip_request + non-UID authorizer label (historical form)."""
        activation, pr, run_folder, events, state = eng.load_run(_ACT_1)
        parent = events[-1]["span_id"] if events else None
        req = eng.make_event(
            "skip_request", "argus", step="9d4f7e21",
            trace_id=_ACT_1, parent_span_id=parent,
            data={"step_id": "9d4f7e21", "reason": "dry-run-gauntlet-seed"},
        )
        eng.append_event(run_folder, req)
        eng.write_run_state_json(
            run_folder, pr["frontmatter"],
            eng.derive_state(eng.read_events(run_folder)), _ACT_1,
        )
        outcome, _ = self.assert_dry_run_never_writes(
            eng.action_authorize_skip, _ACT_1, "9d4f7e21", "mike", "", "argus",
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

    def test_terminal_verify_hard_errors_on_complete_without_tested_sha(self):
        """d7db77d8 revalidation can clear stuck completed steps on this fixture.

        When the obligation-aware walk reaches a complete verdict, AC3 still
        requires --tested-sha before any write. Missing SHA is a clean
        ValidationError — aaf96178 case b, not a silent write.
        """
        outcome, err = self.assert_dry_run_never_writes(
            eng.action_terminal_verify, _ACT_1, "argus",
        )
        self.assertEqual(outcome, "hard_error")
        self.assertIsInstance(err, eng.ValidationError)
        self.assertIn("tested-tree SHA", str(err))

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

    def _establish_canonical_provenance(self, activation_uid: str) -> None:
        """Write the dev-close receipt terminal-verify would have written.

        Planted rather than produced by running terminal-verify, because this
        suite's contract is "dry run writes nothing" and terminal-verify writes
        a great deal. The receipt names the same chain the real one does, so the
        gate is exercised on the shape it actually reads.
        """
        import json as _json

        activation = eng.read_vault_entry(activation_uid)
        afm = activation["frontmatter"]
        run_uid = _PR_2
        run = eng.read_vault_entry(run_uid)
        folder = eng.run_folder_for(run["frontmatter"])
        folder.mkdir(parents=True, exist_ok=True)
        try:
            head = eng._git(eng.VAULT_ROOT, "rev-parse", "HEAD").strip()
        except Exception:
            # This tmp vault is a file copy, not a repository. The gate compares
            # the receipt's tree to HEAD only when there IS a HEAD, so a fixed
            # SHA exercises the same path a repository-less studio takes.
            head = "c" * 40
        receipt = {
            "event": "dev_closed",
            "trace_id": activation_uid,
            "span_id": "provenance-fixture",
            "data": {
                "receipt_kind": "canonical-dev-close",
                "tested_sha": head,
                "tested_commit_sha": head,
                "dev_spec_uid": afm.get("dev_spec_uid"),
                "activation_uid": activation_uid,
                "pipeline_run_uid": run_uid,
                "activation_root_uid": (afm.get("activation_root_project")
                                        or afm.get("activation_root_uid")),
                "verdict": "complete",
            },
        }
        with (folder / "run.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(_json.dumps(receipt) + "\n")

    def test_complete_workflow_banner_path_and_b3ext_passes(self):
        """The item-2 regression case: complete-workflow --dry-run on ad02f944 must
        now pass B3-ext (9d4f7e21's real doc-leg-completed substrate) and reach the
        terminal banner — not BLOCKED, and not a silent write.

        Provenance is established first since 2175f969: complete-workflow refuses
        before a canonical dev-close receipt exists, and a dry run has to fail
        exactly where the real close would. Without this the case would be
        asserting a banner the production path can no longer reach."""
        self._establish_canonical_provenance(_ACT_2)
        before = _tree_hash(self.tmp)
        result = eng.action_complete_workflow(_ACT_2, "talos", dry_run=True)
        after = _tree_hash(self.tmp)
        self.assertEqual(before, after, "complete-workflow --dry-run must write nothing")
        self.assertIn("[DRY-RUN]", result)
        self.assertIn("would emit workflow_complete", result,
                      "all close gates (including the fixed B3-ext branch-applicability "
                      "check on 9d4f7e21) must pass for the dry-run banner to be reached")

    def _seed_release_trigger_parent(
        self, activation_uid: str, run_uid: str, plan_uid: str,
        *, dev_spec_uid: str | None = None,
    ) -> None:
        activation_fm = {
            "uid": activation_uid, "type": "activation",
            "activation_class": "pipeline", "status": "active", "state": "active",
            "pipeline_uid": "634913c2", "pipeline_run_uid": run_uid,
            "release_plan_uid": plan_uid,
        }
        if dev_spec_uid:
            activation_fm["dev_spec_uid"] = dev_spec_uid
        eng.write_vault_entry(activation_uid, activation_fm, "release activation fixture\n")
        eng.write_vault_entry(
            run_uid,
            {
                "uid": run_uid, "type": "pipeline-run", "status": "active",
                "state": "active", "pipeline": "634913c2",
                "activation": activation_uid,
                "substrate_authored_by": activation_uid,
                "release_plan_uid": plan_uid,
                "run_folder": f"vault/pipeline-runs/{run_uid}",
            },
            "release run fixture\n",
        )
        eng.write_vault_entry(
            plan_uid,
            {
                "uid": plan_uid, "type": "release-plan", "status": "locked",
                "release_activation_uid": activation_uid,
                "release_pipeline_run_uid": run_uid,
            },
            "release plan fixture\n",
        )
        folder = self.tmp / "vault" / "pipeline-runs" / run_uid
        folder.mkdir(parents=True, exist_ok=True)
        event = eng.make_event(
            "step_declared", "fixture", trace_id=activation_uid,
            parent_span_id=None, data={
                "step_id": "0cf86ea5", "depends_on_steps": [],
                "trust_level": "auto-with-verification",
            },
        )
        (folder / "run.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

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
        # Parented to a RELEASE run since 2026-08-10 (0a0a6777 AC6): doc/test
        # legs are opened from release-run provenance and action_trigger_step
        # refuses a dev parent outright, so a dev-parented fixture would never
        # reach the O_EXCL file-create path this test exists to cover.
        synth_run_uid = "0e1c0002"
        self._seed_release_trigger_parent(
            synth_activation_uid, synth_run_uid, "b1a00002",
            dev_spec_uid=synth_dev_spec_uid,
        )
        eng.write_vault_entry(synth_dev_spec_uid,
                              {"uid": synth_dev_spec_uid, "type": "dev-spec"},
                              "synthetic fixture — dry-run trigger-step test\n")

        fresh_uid = "abcdef12"
        spec_path = eng.VAULT_FILES / f"{fresh_uid}.md"
        self.assertFalse(spec_path.exists(), "test precondition: fresh UID must not pre-exist")

        before = _tree_hash(self.tmp)
        result = eng.action_trigger_step(
            synth_activation_uid, "0cf86ea5", fresh_uid,
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
        """A dev-spec that already has a LIVE (non-terminal) triggered doc leg must
        still refuse a second trigger-step (cleanly, zero writes) even under --dry-run;
        preview must not paper over a real contract violation.

        Synthetic fixture (not the real ad02f944/5a4337ff pair): this test originally
        relied on a real dev-spec whose triggered doc-pipeline leg was still live at
        the time of writing. That real activation has since reached a terminal status
        through ordinary Studio operation (the B5 check is status-aware by design —
        see the STATUS-AWARE FIX comment on action_trigger_step), so the collision it
        exercised stopped reproducing — the test started silently falling through to
        the success path instead of catching a real regression. A synthetic dev-spec
        with an explicitly non-terminal "already triggered" activation makes the
        precondition this test needs independent of how far real Studio work has
        progressed by the time it runs.
        """
        synth_activation_uid = "55556666"
        synth_dev_spec_uid = "77778888"
        synth_live_cascade_uid = "99990000"
        eng.write_vault_entry(synth_live_cascade_uid,
                              {"uid": synth_live_cascade_uid, "type": "activation",
                               "activation_class": "pipeline", "status": "active"},
                              "synthetic fixture — B5 collision test; deliberately non-terminal\n")
        eng.write_vault_entry(synth_dev_spec_uid,
                              {"uid": synth_dev_spec_uid, "type": "dev-spec",
                               "triggered_doc_activation_uids": [synth_live_cascade_uid]},
                              "synthetic fixture — B5 collision test\n")
        # Release-parented for the same reason as the test above: the B5 claim
        # is about one live cascade per run, and a dev parent is now refused
        # before B5 is ever consulted.
        b5_run_uid = "0e1c0003"
        self._seed_release_trigger_parent(
            synth_activation_uid, b5_run_uid, "b1a00003",
            dev_spec_uid=synth_dev_spec_uid,
        )

        outcome, error = self.assert_dry_run_never_writes(
            eng.action_trigger_step, synth_activation_uid, "0cf86ea5", "abcdef34",
            "---\nuid: abcdef34\ntype: doc-spec\n---\nbody\n",
            "5a4337ff", "doc-pipeline", "talos",
        )
        self.assertEqual(outcome, "hard_error")
        self.assertIn("B5 single-cascade refused", str(error))


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
