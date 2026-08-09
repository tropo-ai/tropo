"""Gauntlet tests for engine gap 8275c814 — retro-scoped pause signoff.

Validates two scenarios per the 8275c814 build scope:
  G1: scope-less pause+resume does NOT emit a human_signoff (existing behavior preserved)
  G2: pause --step <uid> + resume --confirmation-granted-by <non-executor> emits the
      scoped human_signoff and verify-step subsequently returns 'pass'

Uses the real vault for principal resolution but operates on a temp copy of the run
folder so the live run is never modified.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# ── module under test ────────────────────────────────────────────────────────
_VAULT_TOOLS = Path(__file__).resolve().parent.parent
_TROPO_SCRIPTS = Path(__file__).resolve().parents[3] / ".tropo" / "scripts"
sys.path.insert(0, str(_TROPO_SCRIPTS))

spec = importlib.util.spec_from_file_location("eng", str(_VAULT_TOOLS / "9e7003b1.py"))
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

# ── real vault locations ─────────────────────────────────────────────────────
_REAL_VAULT_ROOT = Path(__file__).resolve().parents[3]
_REAL_RUN_FOLDER = _REAL_VAULT_ROOT / "vault" / "pipeline-runs" / "dev-pipeline-896e6c9b-2026-07-02"
_ACTIVATION_UID = "b6a8cd32"
_PR_UID = "896e6c9b"
_STEP_UID = "c6b61fb9"    # vc:true, exit_criteria:["human: c6b61fb9"], auto-with-verification
_EXECUTOR = "argus-a123"  # completed c6b61fb9 in the run
_SIGNER = "mike-maziarz"  # non-executor registered human principal (7b921d17)


def _make_temp_run(tmp: Path) -> Path:
    """Copy the live run folder into tmp/vault/pipeline-runs/, return its path."""
    dest_runs = tmp / "vault" / "pipeline-runs"
    dest_runs.mkdir(parents=True, exist_ok=True)
    dest_folder = dest_runs / _REAL_RUN_FOLDER.name
    shutil.copytree(_REAL_RUN_FOLDER, dest_folder)
    _freeze_pre_ceremony_state(dest_folder)
    return dest_folder


def _freeze_pre_ceremony_state(run_folder: Path) -> None:
    """Rewind the copied run.jsonl to just before c6b61fb9's retro-signoff ceremony.

    dev-pipeline-896e6c9b-2026-07-02 is a REAL, still-active pipeline run — this
    fixture points at its live history rather than a synthetic one so principal
    resolution + load_run exercise real substrate (see module docstring). c6b61fb9's
    retro-signoff ceremony (pause_started -> human_signoff -> pause_resumed ->
    verification_receipt:pass) already happened for real on 2026-07-03 (that's the
    actual historical event this gauntlet was written to regression-guard). Copying
    the run folder as-is therefore starts every test AFTER that ceremony already
    completed: c6b61fb9 reads back as 'verified' (not 'completed') and a signoff for
    it already exists — both preconditions this suite's G1/G2 cases need false. Left
    unfrozen, this suite silently stops testing anything the moment the real run
    passes that point (exactly what happened: it sat green for weeks, then broke the
    instant something else advanced state.json, not because the ceremony logic
    regressed). Truncating to just before the first pause_started(step=c6b61fb9)
    restores the documented baseline ('vc:true, exit_criteria:["human: c6b61fb9"],
    completed, no signoff yet') regardless of how much further the live run
    progresses in the future.
    """
    run_jsonl = run_folder / "run.jsonl"
    lines = run_jsonl.read_text().splitlines()
    cut = None
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        ev = json.loads(line)
        if ev.get("event") == "pause_started" and (ev.get("data") or {}).get("step") == _STEP_UID:
            cut = i
            break
    if cut is None:
        raise AssertionError(
            f"fixture assumption broken: no pause_started(step={_STEP_UID!r}) event found in "
            f"{run_jsonl} — the real run's history changed shape; this freeze helper needs "
            f"re-anchoring, not a silent no-op."
        )
    run_jsonl.write_text("\n".join(lines[:cut]) + "\n")


def _copy_vault_files(tmp: Path) -> None:
    """Copy required vault/files entries to tmp so principal resolution + load_run work."""
    src_files = _REAL_VAULT_ROOT / "vault" / "files"
    dest_files = tmp / "vault" / "files"
    dest_files.mkdir(parents=True, exist_ok=True)
    for uid in (_PR_UID, _ACTIVATION_UID, "7b921d17", "cdf9b3ad", "cd1fcd25"):
        src = src_files / f"{uid}.md"
        if src.exists():
            shutil.copy2(src, dest_files / src.name)


def _patch_vault(tmp: Path):
    """Redirect engine module globals to tmp vault; return a restore function."""
    orig = {
        "VAULT_ROOT": eng.VAULT_ROOT,
        "VAULT_FILES": eng.VAULT_FILES,
        "PIPELINE_RUNS_FOLDER": eng.PIPELINE_RUNS_FOLDER,
    }
    run_folder_tmp = tmp / "vault" / "pipeline-runs" / _REAL_RUN_FOLDER.name
    # Rewrite the pipeline-run entry to point at the tmp run_folder
    pr_file = tmp / "vault" / "files" / f"{_PR_UID}.md"
    if pr_file.exists():
        text = pr_file.read_text()
        relative_run_path = str(run_folder_tmp.relative_to(tmp))
        text = text.replace(
            f"run_folder: vault/pipeline-runs/{_REAL_RUN_FOLDER.name}",
            f"run_folder: {relative_run_path}",
        )
        pr_file.write_text(text)
    eng.VAULT_ROOT = tmp
    eng.VAULT_FILES = tmp / "vault" / "files"
    eng.PIPELINE_RUNS_FOLDER = tmp / "vault" / "pipeline-runs"

    def restore():
        for k, v in orig.items():
            setattr(eng, k, v)

    return restore


def _events(run_folder: Path) -> list[dict]:
    path = run_folder / "run.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


class TestRetroPauseSignoff(unittest.TestCase):
    def setUp(self):
        # resolve() to canonicalize /var → /private/var on macOS (avoids relative_to errors)
        self.tmp = Path(tempfile.mkdtemp(prefix="retro-pause-gauntlet-")).resolve()
        self.run_folder = _make_temp_run(self.tmp)
        _copy_vault_files(self.tmp)
        self.restore = _patch_vault(self.tmp)

    def tearDown(self):
        self.restore()
        shutil.rmtree(self.tmp)

    # ── unit: helper function ────────────────────────────────────────────────

    def test_pending_human_criterion_helper_detects_unsatisfied(self):
        """_step_has_pending_human_criterion returns True when no signoff exists."""
        decl = {"verification_class": True, "exit_criteria": [f"human: {_STEP_UID}"]}
        events: list[dict] = []
        self.assertTrue(eng._step_has_pending_human_criterion(_STEP_UID, decl, events))

    def test_pending_human_criterion_helper_satisfied(self):
        """_step_has_pending_human_criterion returns False when a valid signoff exists."""
        decl = {"verification_class": True, "exit_criteria": [f"human: {_STEP_UID}"]}
        events = [{"event": "human_signoff", "step": _STEP_UID,
                   "data": {"verdict": "accepted", "step": _STEP_UID}}]
        self.assertFalse(eng._step_has_pending_human_criterion(_STEP_UID, decl, events))

    def test_pending_human_criterion_helper_vc_false(self):
        """_step_has_pending_human_criterion returns False for vc:false steps."""
        decl = {"verification_class": False, "exit_criteria": [f"human: {_STEP_UID}"]}
        self.assertFalse(eng._step_has_pending_human_criterion(_STEP_UID, decl, []))

    def test_pending_human_criterion_helper_no_human_criterion(self):
        """_step_has_pending_human_criterion returns False when no human: criterion exists."""
        decl = {"verification_class": True, "exit_criteria": ["some_other_criterion exists"]}
        self.assertFalse(eng._step_has_pending_human_criterion(_STEP_UID, decl, []))

    # ── G1: scope-less retro-signoff must NOT produce a valid human_signoff ──

    def test_g1_scopeless_pause_resume_does_not_emit_signoff(self):
        """G1: scope-less pause + resume --confirmation-granted-by emits no human_signoff.

        The run resumes (pause_resumed recorded) but no human_signoff is written
        because pause_started carries no data.step. verify-step must therefore fail.
        """
        eng.action_pause(_ACTIVATION_UID, "retro-attempt-no-step", "argus-a123")
        eng.action_resume(_ACTIVATION_UID, _SIGNER, "argus-a123")
        evs = _events(self.run_folder)
        signoffs = [e for e in evs if e.get("event") == "human_signoff"
                    and (e.get("data") or {}).get("step") == _STEP_UID]
        self.assertEqual(len(signoffs), 0,
                         "scope-less pause must not produce a scoped human_signoff")
        # verify-step should still FAIL (the human: criterion is unsatisfied)
        verdict = eng.action_verify_step(_ACTIVATION_UID, _STEP_UID, "argus-a123")
        self.assertNotEqual(verdict, "pass",
                            "verify-step must not pass without a scoped signoff (G1 regression guard)")

    # ── G2: retro-scoped pause → resume → verify-step passes ─────────────────

    def test_g2_pause_with_step_validates_non_completed_rejection(self):
        """pause --step on a non-completed step must raise ContractError."""
        with self.assertRaises(eng.ContractError):
            # 3e0bb81e is declared (not completed) in this run
            eng.action_pause(_ACTIVATION_UID, "bad-test", "argus-a123",
                             step_uid="3e0bb81e")

    def test_g2_pause_with_step_validates_missing_step_rejection(self):
        """pause --step with a non-existent step UID must raise ContractError."""
        with self.assertRaises(eng.ContractError):
            eng.action_pause(_ACTIVATION_UID, "bad-test", "argus-a123",
                             step_uid="deadbeef")

    def test_g2_scoped_pause_records_data_step(self):
        """pause --step c6b61fb9 writes pause_started with data.step set."""
        eng.action_pause(_ACTIVATION_UID, "retro-signoff", "argus-a123",
                         step_uid=_STEP_UID)
        evs = _events(self.run_folder)
        pause_ev = next((e for e in reversed(evs) if e.get("event") == "pause_started"), None)
        self.assertIsNotNone(pause_ev, "pause_started event must be written")
        self.assertEqual((pause_ev.get("data") or {}).get("step"), _STEP_UID,
                         "pause_started data.step must be set to the retro step UID")

    def test_g2_full_retro_signoff_flow_verify_step_passes(self):
        """G2 full flow: pause --step → resume --confirmation-granted-by → verify-step = pass."""
        # Step 1: retro-scoped pause
        result = eng.action_pause(_ACTIVATION_UID, "retro-signoff-c6b61fb9",
                                  "argus-a123", step_uid=_STEP_UID)
        self.assertEqual(result, "paused")

        # Step 2: resume with non-executor signer
        result = eng.action_resume(_ACTIVATION_UID, _SIGNER, "argus-a123")
        self.assertEqual(result, "resumed")

        # Confirm human_signoff was emitted, scoped to the right step, by the right actor
        evs = _events(self.run_folder)
        signoff = next(
            (e for e in evs
             if e.get("event") == "human_signoff"
             and (e.get("data") or {}).get("step") == _STEP_UID
             and (e.get("data") or {}).get("verdict") == "accepted"),
            None,
        )
        self.assertIsNotNone(signoff, "human_signoff event must be recorded for the step")
        self.assertEqual(signoff.get("actor"), _SIGNER,
                         "human_signoff actor must be the confirmation_granted_by principal")

        # Step 3: verify-step must pass
        verdict = eng.action_verify_step(_ACTIVATION_UID, _STEP_UID, "argus-a123")
        self.assertEqual(verdict, "pass",
                         "verify-step must return 'pass' after scoped signoff")


if __name__ == "__main__":
    unittest.main()
