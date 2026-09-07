"""b3f620fc — verify-step evidence-passthrough (argus-a162 spec, talos-t53 build).

The flags choose the code path: verify-step --execution-mode agent/human
--evidence-ref <uid> derives its verdict from the resolved evidence record
(resolve_evidence-mirroring cross-checks) instead of executing the declared
verification_command. Machine mode is byte-for-byte unchanged.

These tests run against an isolated engine + a frozen copy of the REAL blocked
scenario (pipeline run d445af8b, step a0f2bea8 release-harness-gate, active
candidate f4e569ec..., evidence a0521adf — frozen 2026-08-29 in
fixtures/d445af8b_verify/ straight from the live run while it was blocked).
The live run is never touched.
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
STEP = "a0f2bea8"
EVIDENCE = "a0521adf"
CANDIDATE = "f4e569ec3822079f3ff46ba1c5a63120cfbbb50490158aa1f0f1369d184bfc1f"
ACTOR = "argus-a162"  # the step's declared verifier role; NOT the evidence owner


def _load_isolated_engine(tmp: Path):
    """Copy the engine's sibling-import surface into tmp and load the COPY —
    never the real vault/tools/9e7003b1.py — so VAULT_ROOT resolves to the
    isolated studio. (tmp pre-resolved for macOS /var symlink parity.)"""
    shutil.copytree(STUDIO_ROOT / "vault" / "tools", tmp / "vault" / "tools",
                     ignore=shutil.ignore_patterns("__pycache__", "tests"))
    shutil.copytree(STUDIO_ROOT / ".tropo" / "scripts", tmp / ".tropo" / "scripts",
                     ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / "vault" / "files").mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "verify_ev_engine_%s" % abs(hash(str(tmp))),
        tmp / "vault" / "tools" / "9e7003b1.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module.VAULT_ROOT == tmp, "engine did not resolve to the isolated copy"
    return module


def _copy_blocked_scenario(tmp: Path, mutate_evidence=None) -> Path:
    """Frozen copy of the real blocked run + evidence. mutate_evidence, when
    given, receives the evidence file's text and returns edited text."""
    for name in (REAL_ACTIVATION_UID, "d445af8b", EVIDENCE):
        text = (FIXTURES / f"{name}.md").read_text(encoding="utf-8")
        if name == EVIDENCE and mutate_evidence:
            text = mutate_evidence(text)
        (tmp / "vault" / "files" / f"{name}.md").write_text(text, encoding="utf-8")
    run_dir = tmp / "vault" / "pipeline-runs" / REAL_RUN_FOLDER
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ("run.jsonl", "run.state.json"):
        shutil.copy(FIXTURES / name, run_dir / name)
    return run_dir


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _last_journal_rows(run_dir: Path, event_type: str, n=1):
    rows = [json.loads(l) for l in
            (run_dir / "run.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    hits = [r for r in rows if r.get("event") == event_type]
    return hits[-n:]


class EvidencePassthroughBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)
        self.run_dir = _copy_blocked_scenario(self.tmp)


class TheHappyPath(EvidencePassthroughBase):
    def test_agent_mode_with_valid_evidence_derives_pass(self):
        """AC1 shape, on the frozen copy: pass_with_findings evidence from a
        third-party instrument agent, run+package matching the active
        candidate, becomes a passing receipt WITHOUT running the command."""
        verdict = self.engine.action_verify_step(
            REAL_ACTIVATION_UID, STEP, ACTOR,
            execution_mode="agent", evidence_ref=EVIDENCE)
        self.assertEqual(verdict, "pass")
        receipt = _last_journal_rows(self.run_dir, "verification_receipt")[0]
        data = receipt["data"]
        self.assertEqual(data["verifier_role_resolved"], "agent-evidence")
        self.assertEqual(data["verdict"], "pass")
        self.assertEqual(data["evidence"]["ref"], EVIDENCE)
        self.assertEqual(data["evidence"]["package_sha256"], CANDIDATE)
        release = _last_journal_rows(self.run_dir, "release-verification-receipt")[0]
        self.assertEqual(release["data"]["verdict"], "pass")
        self.assertEqual(release["data"]["candidate_sha256"], CANDIDATE)
        self.assertEqual(release["data"]["evidence_ref"], EVIDENCE)

    def test_the_step_reads_verified_after_a_real_evidence_receipt(self):
        state = self.engine.derive_state(self.engine.read_events(self.run_dir))
        self.assertEqual(state["step_status"][STEP], "completed")
        self.engine.action_verify_step(
            REAL_ACTIVATION_UID, STEP, ACTOR,
            execution_mode="agent", evidence_ref=EVIDENCE)
        state = self.engine.derive_state(self.engine.read_events(self.run_dir))
        self.assertEqual(state["step_status"][STEP], "verified")

    def test_dry_run_with_evidence_derives_but_writes_nothing(self):
        before = _md5(self.run_dir / "run.jsonl")
        result = self.engine.action_verify_step(
            REAL_ACTIVATION_UID, STEP, ACTOR,
            execution_mode="agent", evidence_ref=EVIDENCE, dry_run=True)
        self.assertIn("verdict='pass'", result)
        self.assertEqual(_md5(self.run_dir / "run.jsonl"), before)

    def test_machine_mode_still_takes_the_command_branch(self):
        """No flags, no command executed under dry-run — the exact pre-fix
        preview text, proving the auto-run path is untouched (AC2)."""
        before = _md5(self.run_dir / "run.jsonl")
        result = self.engine.action_verify_step(
            REAL_ACTIVATION_UID, STEP, ACTOR, dry_run=True)
        self.assertIn("would run verification_command", result)
        self.assertEqual(_md5(self.run_dir / "run.jsonl"), before)


class TheRefusals(EvidencePassthroughBase):
    """Cross-check failures refuse, exactly as the checker script does."""

    def _with_mutated_evidence(self, fn):
        """Re-copy the scenario with mutated evidence, replacing the first copy."""
        self.run_dir = _copy_blocked_scenario(self.tmp, mutate_evidence=fn)

    def test_self_signed_evidence_is_refused(self):
        self._with_mutated_evidence(lambda t: t.replace(
                "owner: sa.release-test-harness", f"owner: {ACTOR}"))
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_verify_step(
                REAL_ACTIVATION_UID, STEP, ACTOR,
                execution_mode="agent", evidence_ref=EVIDENCE)
        self.assertIn("signer themselves", str(ctx.exception))

    def test_ownerless_evidence_is_refused(self):
        self._with_mutated_evidence(lambda t: t.replace(
                "owner: sa.release-test-harness", "owner: \"\"").replace(
                "executed_by: sa.release-test-harness", "executed_by: \"\""))
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_verify_step(
                REAL_ACTIVATION_UID, STEP, ACTOR,
                execution_mode="agent", evidence_ref=EVIDENCE)
        self.assertIn("names no owner", str(ctx.exception))

    def test_run_mismatch_is_refused(self):
        self._with_mutated_evidence(lambda t: t.replace(
                'release_pipeline_run_uid: "d445af8b"',
                'release_pipeline_run_uid: "deadbeef"'))
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_verify_step(
                REAL_ACTIVATION_UID, STEP, ACTOR,
                execution_mode="agent", evidence_ref=EVIDENCE)
        self.assertIn("do not describe the same run", str(ctx.exception))

    def test_package_mismatch_is_refused(self):
        # "a"*64, not "0"*64: a 64-zero string parses as a YAML octal int 0
        # (falsy) and would exercise the ABSENCE branch instead — a real
        # mismatched sha is never all-zero.
        self._with_mutated_evidence(lambda t: t.replace(
                f"package_sha256: {CANDIDATE}",
                "package_sha256: " + "a" * 64))
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_verify_step(
                REAL_ACTIVATION_UID, STEP, ACTOR,
                execution_mode="agent", evidence_ref=EVIDENCE)
        self.assertIn("do not describe the same run", str(ctx.exception))

    def test_absent_fields_are_not_agreement(self):
        self._with_mutated_evidence(lambda t: "\n".join(
                line for line in t.splitlines()
                if not line.startswith("package_sha256:")))
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_verify_step(
                REAL_ACTIVATION_UID, STEP, ACTOR,
                execution_mode="agent", evidence_ref=EVIDENCE)
        self.assertIn("absence is not agreement", str(ctx.exception))

    def test_unresolvable_ref_is_refused(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_verify_step(
                REAL_ACTIVATION_UID, STEP, ACTOR,
                execution_mode="agent", evidence_ref="deadbeef")
        self.assertIn("resolves to nothing", str(ctx.exception))


class TheHonestFail(unittest.TestCase):
    """A present-but-failing instrument run is a real result: the receipt
    records fail rather than refusing to speak."""

    def test_failing_evidence_yields_fail_receipt_not_refusal(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        engine = _load_isolated_engine(tmp)
        run_dir = _copy_blocked_scenario(
            tmp, mutate_evidence=lambda t: t.replace(
                "verdict: pass_with_findings", "verdict: fail"))
        verdict = engine.action_verify_step(
            REAL_ACTIVATION_UID, STEP, ACTOR,
            execution_mode="agent", evidence_ref=EVIDENCE)
        self.assertEqual(verdict, "fail")
        receipt = _last_journal_rows(run_dir, "verification_receipt")[0]
        self.assertEqual(receipt["data"]["verdict"], "fail")
        self.assertEqual(receipt["data"]["verifier_role_resolved"], "agent-evidence")


if __name__ == "__main__":
    unittest.main()
