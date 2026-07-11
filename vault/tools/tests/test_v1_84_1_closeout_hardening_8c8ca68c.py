"""Regression gauntlet for the six pipeline-runtime.py bugs surfaced driving the v1.84.1
federation close-out (2026-07-09/10), per Argus A129's hardening-track assignment (event
00006084) after the ceremony was closed by documented attestation (8c8ca68c) rather than the
engine's own complete-workflow — the engine's close machinery had never actually been
exercised end-to-end before this cycle, and rotted silently. Each test constructs the real
fixture shape that triggered its bug and asserts the CURRENT (fixed) engine behaves correctly
against it — if any of these fixes regress, the corresponding test goes red.

Bugs 1/2 (auto-heal field-drop, B5 always-refuse): found + fixed by Talos T27, 2026-07-09.
Bugs 3/4/5 (behaviors_covered wrong context key, test_spec stale reverse-resolution, B3-ext
missing run_events): found + fixed by Talos T28, 2026-07-09/10, driving mount-gate's own
test-pipeline leg through 4 successive re-triggers to get a genuinely clean run.
Bug 6 (dc108622/a69fcab3 broken verification_commands): Vela V64's fixes, 2026-07-09 — the
step-definition DATA was wrong (wrong-repo path, nonexistent script), not engine code; this
test instead covers the engine plumbing that let a broken command silently misreport, so the
same class of drift is caught earlier next time.

Self-running (python3 test_v1_84_1_closeout_hardening_8c8ca68c.py) and pytest-compatible.
"""
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


class _SandboxedVaultTest(unittest.TestCase):
    """Shared sandbox: patches eng's module-level path constants so nothing touches the
    real vault. Mirrors the established pattern in test_b3ext_branch_applicability.py."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="closeout-hardening-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.files.mkdir(parents=True)
        self._orig_vault_root = eng.VAULT_ROOT
        self._orig_vault_files = eng.VAULT_FILES
        eng.VAULT_ROOT = self.tmp
        eng.VAULT_FILES = self.files

    def tearDown(self):
        eng.VAULT_ROOT = self._orig_vault_root
        eng.VAULT_FILES = self._orig_vault_files
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, uid: str, fm: dict, body: str = "body\n"):
        eng.write_vault_entry(uid, fm, body)

    @staticmethod
    def _hex(*parts: str) -> str:
        """Deterministic real-looking 8-hex UID — the engine validates this shape
        (re.fullmatch(r"[0-9a-f]{8}", ...)) at several call sites, so readable test names
        like 'devcycle1' are rejected outright; hash them into something that passes."""
        import hashlib
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:8]


# ─── Bug 1: auto-heal field-drop (verification_command/verdict_cwd) ──────────────────────

class TestAutoHealFieldDrop(_SandboxedVaultTest):
    """Bug: the B1 auto-heal step-data builder (~L1489-1531) was constructed independently
    of the normal declaration path and never picked up verification_command/verdict_cwd — any
    step declared via a mid-run fingerprint-drift auto-heal silently lost both fields
    regardless of what the step's own vault frontmatter declared, so the command never ran
    and a verification_class:true step fell back to same-as-executor self-attestation.
    (Vela V64 diagnosis, event 00006024 -> 974b08ad; fixed by Talos T27.)
    """

    def test_auto_healed_step_carries_verification_command_and_verdict_cwd(self):
        # A pipeline def declaring one step with a real verification_command + verdict_cwd.
        # resolve_workflow_node_tree only queues children matching [0-9a-f]{8} (D2 fix,
        # v1.63) — readable test names are silently filtered out, not just rejected loudly,
        # so this fixture needs real-looking hex UIDs to actually be reachable.
        pipe_uid = self._hex("pipedef")
        step_uid = self._hex("stepnew")
        self._write(pipe_uid, {
            "uid": pipe_uid, "type": "pipeline", "version": "2.0",
            "children": [step_uid],
        })
        self._write(step_uid, {
            "uid": step_uid, "type": "pipeline", "subtype": "workflow-node",
            "step_owner_role": "vela", "step_verifier_role": "same-as-executor",
            "verification_class": True, "depends_on_steps": [], "exit_criteria": [],
            "trust_level": "auto", "verification_command": "python3 -c \"pass\"",
            "verdict_cwd": ".", "member_of": [pipe_uid], "next_steps": [],
        })
        # A pipeline-run whose recorded fingerprint is stale (the def gained a step since
        # bootstrap) — this is exactly the trigger condition for auto-heal to fire.
        pr = {"frontmatter": {"uid": "prun1", "pipeline": pipe_uid,
                               "pipeline_step_fingerprint": "stale-does-not-match"}}
        events = [{"event": "run_created", "trace_id": "act1", "data": {}}]
        run_folder = self.tmp / "run-sandbox-1"
        run_folder.mkdir()

        healed_events, _state = eng._auto_heal_stale_def(pr, run_folder, events, "act1")

        declared = [e for e in healed_events if e.get("event") == "step_declared"
                    and e.get("step") == step_uid]
        self.assertEqual(len(declared), 1, "auto-heal should have declared the new step")
        data = declared[0]["data"]
        self.assertEqual(data.get("verification_command"), "python3 -c \"pass\"",
                          "auto-healed declaration dropped verification_command — bug 1 regressed")
        self.assertEqual(data.get("verdict_cwd"), ".",
                          "auto-healed declaration dropped verdict_cwd — bug 1 regressed")


# ─── Bug 2: B5 single-cascade always-refuse ───────────────────────────────────────────────

class TestB5StatusAwareRetrigger(_SandboxedVaultTest):
    """Bug: the original B5 idempotency check refused a second trigger-step for the same
    pipeline-class FOREVER once fired once, regardless of whether the prior cascade
    activation was still live — its own error message promised a remedy ("retire it first")
    the code never implemented, so a stuck cascade could never actually be unblocked.
    (Argus A129 ruling, event 00006039; fixed by Talos T27/T28 — filter to non-terminal
    activations before refusing.)
    """

    def _seed_dev_run(self, existing_act_uid, existing_act_status):
        self._write("devspec1", {
            "uid": "devspec1", "type": "dev-spec",
            "triggered_test_activation_uids": [existing_act_uid] if existing_act_uid else [],
        })
        self._write("devact1", {"uid": "devact1", "type": "activation",
                                 "activation_class": "pipeline", "dev_spec_uid": "devspec1"})
        if existing_act_uid:
            self._write(existing_act_uid, {"uid": existing_act_uid, "type": "activation",
                                            "status": existing_act_status})

    def test_all_prior_cascades_terminal_allows_retrigger(self):
        """The real bug: prior test-pipeline activation is RETIRED (terminal) — a re-trigger
        for the same dev-run must be ALLOWED, not refused forever."""
        self._seed_dev_run("oldact01", "retired")
        result = eng.action_trigger_step(
            "devact1", "trigstep1", self._hex("spec", "1"), "body", "da3f50dc", "test-pipeline",
            "test-actor", dry_run=True)
        self.assertTrue(result.get("dry_run"), "retrigger over a terminal prior cascade must be allowed")

    def test_live_prior_cascade_still_refused(self):
        """The invariant B5 actually wants: exactly one ACTIVE cascade at a time — a prior
        activation that is still genuinely live must still refuse a second trigger."""
        self._seed_dev_run("liveact1", "active")
        with self.assertRaises(eng.ContractError):
            eng.action_trigger_step(
                "devact1", "trigstep1", self._hex("spec", "2"), "body", "da3f50dc", "test-pipeline",
                "test-actor", dry_run=True)

    def test_no_prior_cascade_allows_first_trigger(self):
        """Sanity: the common case (no prior activation at all) is unaffected."""
        self._seed_dev_run(None, None)
        result = eng.action_trigger_step(
            "devact1", "trigstep1", self._hex("spec", "3"), "body", "da3f50dc", "test-pipeline",
            "test-actor", dry_run=True)
        self.assertTrue(result.get("dry_run"))


# ─── Bugs 3+4: behaviors_covered wrong context key + test_spec stale reverse-resolution ──

class TestTestSpecReverseResolution(_SandboxedVaultTest):
    """Bug 3: the behaviors_covered fallback (~L1725, action_step_complete) queried context
    key 'triggered_test_spec' for a test-pipeline activation's own spec — that key is ONLY
    populated on the forward (dev-pipeline) side, so it always resolved to None and silently
    fell through to a degenerate no-op-command pass instead of executing the real test file.

    Bug 4: the reverse-resolution branch in build_run_context_uids that DOES set 'test_spec'
    (~L1011) always took index [0] of the dev-spec's triggered_test_spec_uids array — since a
    re-triggered dev-spec appends one new (spec, activation) pair per re-fire, this read the
    FIRST-EVER triggered spec (from a prior, unrelated re-trigger) instead of the one paired
    with the CURRENT activation via the parallel triggered_test_activation_uids array.

    Both caught live driving mount-gate's own test-pipeline leg through re-trigger #3, where
    05d9ecc5 (run-test-substrate) reported a fake pass instead of running
    test_mount_gate_409ef1cc.py at all. Fixed by Talos T28, d2f8a91c.
    """

    def _seed_reverse_resolution(self, *, activation_pipeline, target_activation_uid):
        # Dev-cycle chain: a dev-pipeline activation with a dev-spec that has been
        # re-triggered THREE times — triggered_test_spec_uids / triggered_test_activation_uids
        # grow in lockstep, one pair appended per re-fire (the real substrate shape).
        devcycle_uid = self._hex("devcycle")
        self._write(devcycle_uid, {"uid": devcycle_uid, "type": "activation",
                                    "activation_class": "pipeline", "dev_spec_uid": "devspec2"})
        self._write("devspec2", {
            "uid": "devspec2", "type": "dev-spec",
            "triggered_test_spec_uids": ["specfirst", "specsecond", "specthird"],
            "triggered_test_activation_uids": ["actfirst", "actsecond", "actthird"],
        })
        # The activation under test — a test-pipeline activation reverse-resolving its OWN
        # spec via cycle_context, exactly as build_run_context_uids expects.
        self._write(target_activation_uid, {
            "uid": target_activation_uid, "type": "activation",
            "cycle_context": f"triggered-by-dev-cycle:{devcycle_uid}",
        })

    def test_third_retrigger_resolves_its_own_spec_not_the_first(self):
        """Bug 4, precisely: activation 'actthird' (the 3rd re-trigger) must resolve
        test_spec == 'specthird' (its own pair), not 'specfirst' (index [0])."""
        self._seed_reverse_resolution(activation_pipeline=eng._TEST_PIPELINE_UID,
                                       target_activation_uid="actthird")
        pr = {"frontmatter": {"pipeline": eng._TEST_PIPELINE_UID}}
        ctx = eng.build_run_context_uids(pr, "actthird")
        self.assertEqual(ctx.get("test_spec"), "specthird",
                          "reverse-resolution returned the wrong index-paired spec — bug 4 regressed")

    def test_first_retrigger_still_resolves_correctly(self):
        """Symmetry check: the FIRST activation in the array must resolve to its own
        (also-first) spec — the fix must not just shift the bug to a different index."""
        self._seed_reverse_resolution(activation_pipeline=eng._TEST_PIPELINE_UID,
                                       target_activation_uid="actfirst")
        pr = {"frontmatter": {"pipeline": eng._TEST_PIPELINE_UID}}
        ctx = eng.build_run_context_uids(pr, "actfirst")
        self.assertEqual(ctx.get("test_spec"), "specfirst")

    def test_behaviors_covered_fallback_key_is_populated(self):
        """Bug 3, precisely: the key action_step_complete's behaviors_covered fallback reads
        (test_spec, with triggered_test_spec as a secondary fallback) must actually be
        present in the context for a test-pipeline activation's own step — pre-fix this was
        always absent (None), silently degenerating real test execution to a no-op pass."""
        self._seed_reverse_resolution(activation_pipeline=eng._TEST_PIPELINE_UID,
                                       target_activation_uid="actsecond")
        pr = {"frontmatter": {"pipeline": eng._TEST_PIPELINE_UID}}
        ctx = eng.build_run_context_uids(pr, "actsecond")
        _ts_uid = ctx.get("test_spec") or ctx.get("triggered_test_spec")
        self.assertEqual(_ts_uid, "specsecond",
                          "behaviors_covered fallback would resolve to nothing (bug 3) or the "
                          "wrong spec (bug 4) — the exact false-pass mechanism from mount-gate's "
                          "3rd re-trigger")


# ─── Bug 5: B3-extension recompute missing run_events ─────────────────────────────────────

class TestB3ExtRunEventsPassed(_SandboxedVaultTest):
    """Bug: action_complete_workflow's B3-extension recompute loop called
    evaluate_criterion(c, ctx, snapshot) — omitting the 4th positional run_events argument
    that human:/aggregate: criteria require to dispatch. Any verification_class:true step
    whose only receipt was a natural_verdict (auto-promoted via a real
    verification_command_exit_code) and whose exit_criteria used 'aggregate: ...' therefore
    ALWAYS errored at workflow_complete, even though the real, passing test_aggregate event
    already existed in the run's own event log. Caught live: mount-gate's 05d9ecc5 reported
    error instead of reading its own genuine fail_count:0 result. Fixed by Talos T28, d2f8a91c.
    """

    def test_aggregate_criterion_recompute_reads_the_real_result_not_error(self):
        self._write("act2", {"uid": "act2", "type": "activation", "activation_class": "pipeline"})
        self._write("prun2", {
            "uid": "prun2", "type": "pipeline-run", "substrate_authored_by": "act2",
            "pipeline": "da3f50dc", "run_folder": "vault/pipeline-runs/sandbox-run-2",
        })
        run_folder = self.tmp / "vault" / "pipeline-runs" / "sandbox-run-2"
        run_folder.mkdir(parents=True)

        events = [
            eng.make_event("run_created", "test-actor", trace_id="act2", data={}),
            eng.make_event("step_declared", "test-actor", step="s1", trace_id="act2", data={
                "step_id": "s1", "step_owner_role": "talos", "step_verifier_role": "same-as-executor",
                "verification_class": True, "depends_on_steps": [], "trust_level": "auto",
                "exit_criteria": ["aggregate: fail_count == 0"],
                "retry_policy": {"max_retries": 0, "backoff": "linear"}, "timeout_hours": 24,
                "compensation_step_id": None, "instructions_ref": None,
                "verification_command": "python3 -c \"pass\"", "verdict_cwd": ".",
            }),
            # The REAL, passing evidence — exactly what a genuine test run produces.
            eng.make_event("test_aggregate", "test-actor", step="s1", trace_id="act2",
                            data={"pass_count": 1, "fail_count": 0, "total": 1, "verdict": "pass"}),
            # Auto-promoted to 'verified' via verification_command_exit_code presence (the real
            # engine shape for a trust_level:auto step) — only a natural_verdict, no explicit
            # verification_receipt, which is exactly what routes it into the B3-ext recompute.
            eng.make_event("step_completed", "test-actor", step="s1", trace_id="act2", data={
                "natural_verdict": "pass", "verification_command_exit_code": 0,
            }),
        ]
        for ev in events:
            eng.append_event(run_folder, ev)

        result = eng.action_complete_workflow("act2", "test-actor")
        self.assertEqual(result, "workflow_complete",
                          "B3-ext recompute failed/errored on a genuinely-passing aggregate — bug 5 regressed")

        final_events = eng._read_run_events(run_folder) if hasattr(eng, "_read_run_events") else None
        if final_events is None:
            final_events = [__import__("json").loads(l) for l in
                             (run_folder / "run.jsonl").read_text().splitlines() if l.strip()]
        receipts = [e for e in final_events if e.get("event") == "verification_receipt"
                    and e.get("step") == "s1"]
        self.assertTrue(receipts, "expected a B3-ext-written verification_receipt for s1")
        last = receipts[-1]["data"]
        self.assertEqual(last.get("verdict"), "pass")
        crit = last["per_criterion"][0]
        self.assertEqual(crit["verdict"], "pass")
        self.assertNotEqual(crit["verdict"], "error",
                             "aggregate: criterion errored despite real_events containing the "
                             "passing test_aggregate — the run_events omission bug")


# ─── Bug 6: broken verification_commands (dc108622/a69fcab3 class) ───────────────────────

class TestVerificationCommandExecutionReporting(_SandboxedVaultTest):
    """Bug 6 itself (dc108622 pointing at a nonexistent script; a69fcab3 pointing at a
    wrong-repo cwd) was step-definition DATA, fixed by Vela V64 directly on the two vault
    entries — not an engine code bug. What IS engine-owned and worth covering: the
    verification_command execution/reporting path must (a) surface a real nonzero exit code
    as a fail (never silently pass), and (b) never mask a genuinely broken command as
    'nothing to check'. This is the plumbing that let dc108622's dangling path go unnoticed
    for months until this cycle actually exercised it.
    """

    def _seed_single_step(self, verification_command, verdict_cwd="."):
        self._write("act3", {"uid": "act3", "type": "activation", "activation_class": "pipeline"})
        self._write("prun3", {
            "uid": "prun3", "type": "pipeline-run", "substrate_authored_by": "act3",
            "pipeline": "da3f50dc", "run_folder": "vault/pipeline-runs/sandbox-run-3",
        })
        run_folder = self.tmp / "vault" / "pipeline-runs" / "sandbox-run-3"
        run_folder.mkdir(parents=True)
        decl = eng.make_event("step_declared", "test-actor", step="s1", trace_id="act3", data={
            "step_id": "s1", "step_owner_role": "vela", "step_verifier_role": "same-as-executor",
            "verification_class": True, "depends_on_steps": [], "trust_level": "auto",
            "exit_criteria": [], "retry_policy": {"max_retries": 0, "backoff": "linear"},
            "timeout_hours": 24, "compensation_step_id": None, "instructions_ref": None,
            "verification_command": verification_command, "verdict_cwd": verdict_cwd,
        })
        eng.append_event(run_folder, decl)
        started = eng.make_event("step_started", "test-actor", step="s1", trace_id="act3", data={})
        eng.append_event(run_folder, started)
        return run_folder

    def test_dangling_script_path_reports_fail_not_silent_pass(self):
        """The exact dc108622 shape: verification_command points at a script that does not
        exist on disk. Must report a real fail (nonzero exit), never a silent pass."""
        run_folder = self._seed_single_step("python3 vault/tools/this-script-does-not-exist-8c8ca68c.py")
        eng.action_step_complete("act3", "s1", [], "test-actor")
        events = [__import__("json").loads(l) for l in (run_folder / "run.jsonl").read_text().splitlines() if l.strip()]
        completed = [e for e in events if e.get("event") == "step_completed" and e.get("step") == "s1"][-1]
        self.assertNotEqual(completed["data"].get("verification_command_exit_code"), 0,
                             "a dangling script path must not report exit_code 0")
        self.assertEqual(completed["data"].get("natural_verdict"), "fail")

    def test_wrong_cwd_repo_reports_fail_not_silent_pass(self):
        """The exact a69fcab3 shape: verdict_cwd points at a directory that does not exist
        on this machine. Must report a real fail, never silently pass."""
        run_folder = self._seed_single_step("python3 -c \"pass\"",
                                             verdict_cwd="/this/path/does/not/exist/8c8ca68c")
        eng.action_step_complete("act3", "s1", [], "test-actor")
        events = [__import__("json").loads(l) for l in (run_folder / "run.jsonl").read_text().splitlines() if l.strip()]
        completed = [e for e in events if e.get("event") == "step_completed" and e.get("step") == "s1"][-1]
        self.assertNotEqual(completed["data"].get("verification_command_exit_code"), 0,
                             "a nonexistent verdict_cwd must not silently report success")
        # A cwd that doesn't exist at all can't even launch the subprocess (OSError, caught
        # by the engine's generic except -> 'error'), distinct from a command that ran and
        # exited nonzero ('fail') — both are non-blocking-failure states; what matters is
        # neither is 'pass'. The a69fcab3 bug specifically was a silent PASS on a command
        # that never should have been trusted, so that's the one outcome to rule out.
        self.assertIn(completed["data"].get("natural_verdict"), ("fail", "error"),
                       "a broken cwd must not silently report pass")


if __name__ == "__main__":
    unittest.main()
