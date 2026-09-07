"""step-complete evidence-passthrough for vc:false instruments (Metis ruling
evt_823a851052454a86_00000020, relayed by argus-a162 evt_..._270, built by
talos-t53 2026-08-29).

vc:false instrument steps route around verify-step entirely (they auto-complete
and auto-receipt inside action_step_complete), so their AC7
release-verification-receipt is earned at step-complete time from named
evidence — same cross-checks as verify-step (_derive_verdict_from_evidence).
Machine mode / no ref: byte-for-byte unchanged, mutation-proven both
directions. Refusals happen BEFORE any journal write.

Fixtures: the frozen d445af8b corpus; bc6b17ec (external-test, vc:false) is
driven back to 'started' through the engine's own reverify/step-start path.
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
EXT_TEST = "bc6b17ec"       # vc:false instrument (external-test)
HARNESS_STEP = "a0f2bea8"   # vc:true instrument (release-harness-gate)
ORDINARY_STEP = "8654900a"  # non-instrument step on the same run
ACTOR = "talos-t53"
EVIDENCE = "eext0001"       # synthetic evidence entry uid (written per-test)

EVIDENCE_TEMPLATE = """---
uid: {uid}
type: test-run
title: synthetic external-test evidence
owner: sa.release-test-harness
executed_by: sa.release-test-harness
verdict: {verdict}
release_pipeline_run_uid: "d445af8b"
package_sha256: {package}
state: active
---

# Synthetic external-test evidence entry

Body for the fixture evidence record.
"""


def _load_isolated_engine(tmp: Path):
    shutil.copytree(STUDIO_ROOT / "vault" / "tools", tmp / "vault" / "tools",
                     ignore=shutil.ignore_patterns("__pycache__", "tests"))
    shutil.copytree(STUDIO_ROOT / ".tropo" / "scripts", tmp / ".tropo" / "scripts",
                     ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / "vault" / "files").mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "sc_engine_%s" % abs(hash(str(tmp))),
        tmp / "vault" / "tools" / "9e7003b1.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module.VAULT_ROOT == tmp
    return module


def _copy_scenario(tmp: Path, evidence: str | None = None) -> Path:
    for name in (REAL_ACTIVATION_UID, "d445af8b", "a0521adf",
                 "3f58b5c5", "7b921d17"):  # + Mike's principal entries (resume signer)
        shutil.copy(FIXTURES / f"{name}.md", tmp / "vault" / "files" / f"{name}.md")
    if evidence is not None:
        (tmp / "vault" / "files" / f"{EVIDENCE}.md").write_text(evidence, encoding="utf-8")
    run_dir = tmp / "vault" / "pipeline-runs" / REAL_RUN_FOLDER
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ("run.jsonl", "run.state.json"):
        shutil.copy(FIXTURES / name, run_dir / name)
    return run_dir


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _drive_to_started(engine, run_dir, step) -> None:
    """Get `step` back to 'started' using the engine's own transitions.

    bc6b17ec depends on a0f2bea8 (the harness gate), so the dep must be green
    first — driven through the evidence passthrough, the very path these
    fixtures exist to exercise."""
    state = engine.derive_state(engine.read_events(run_dir))
    if state["step_status"].get(HARNESS_STEP) != "verified":
        engine.action_verify_step(
            REAL_ACTIVATION_UID, HARNESS_STEP, "argus-a162",
            execution_mode="agent", evidence_ref="a0521adf")
    state = engine.derive_state(engine.read_events(run_dir))
    status = state["step_status"].get(step)
    if status in ("verified", "skipped", "completed"):
        engine.action_reverify_step(REAL_ACTIVATION_UID, step, ACTOR,
                                     reason="fixture reset")
        status = "declared"
    if status == "declared":
        result = engine.action_step_start(REAL_ACTIVATION_UID, step, ACTOR)
        if str(result).startswith("paused:"):
            # approval-required steps pause once; resume clears the gate and
            # the second start actually fires step_started.
            engine.action_resume(REAL_ACTIVATION_UID, "mike", ACTOR)
            engine.action_step_start(REAL_ACTIVATION_UID, step, ACTOR)
    status = engine.derive_state(engine.read_events(run_dir))["step_status"].get(step)
    assert status == "started", f"fixture setup left {step} at {status!r}"


def _receipts(engine, run_dir, instrument):
    from lib import release_verify as _rv  # isolated engine's lib
    rows = engine.read_events(run_dir)
    out = []
    for e in rows:
        d = e.get("data") or {}
        if str(d.get("receipt_kind") or "") == _rv.RECEIPT_KIND \
                and str(d.get("instrument") or "") == instrument:
            out.append(d)
    return out


def _rewind_to_started(run_dir, step) -> None:
    """Fixture surgery for paths _drive_to_started cannot reach: drop the
    journal from the step's first step_completed onward, so it replays as
    'started' with its earlier history (declaration, start) intact."""
    rows = [json.loads(l) for l in
            (run_dir / "run.jsonl").read_text().splitlines() if l.strip()]
    out, cut = [], False
    for r in rows:
        if r.get("event") == "step_completed" and (
                r.get("step") == step or (r.get("data") or {}).get("step_id") == step):
            cut = True
        if not cut:
            out.append(r)
    (run_dir / "run.jsonl").write_text(
        "\n".join(json.dumps(r) for r in out) + "\n")


class StepCompleteEvidenceBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)

    def fresh(self, evidence=None):
        self.run_dir = _copy_scenario(self.tmp, evidence=evidence)
        _drive_to_started(self.engine, self.run_dir, EXT_TEST)
        return self.run_dir


class ThePassthrough(StepCompleteEvidenceBase):
    def test_human_mode_with_valid_evidence_emits_the_ac7_receipt(self):
        self.fresh(evidence=EVIDENCE_TEMPLATE.format(
            uid=EVIDENCE, verdict="pass_with_findings", package=ACTIVE_CANDIDATE))
        result = self.engine.action_step_complete(
            REAL_ACTIVATION_UID, EXT_TEST, ["external-test-result.md"], ACTOR,
            execution_mode="human", evidence_ref=EVIDENCE)
        self.assertIn("completed", result)
        receipts = _receipts(self.engine, self.run_dir, "external-test")
        self.assertEqual(len(receipts), 1)
        r = receipts[0]
        self.assertEqual(r["verdict"], "pass")
        self.assertEqual(r["execution_mode"], "human")
        self.assertEqual(r["evidence_ref"], EVIDENCE)
        self.assertEqual(r["candidate_sha256"], ACTIVE_CANDIDATE)

    def test_failing_evidence_yields_a_fail_receipt_not_a_refusal(self):
        self.fresh(evidence=EVIDENCE_TEMPLATE.format(
            uid=EVIDENCE, verdict="fail", package=ACTIVE_CANDIDATE))
        self.engine.action_step_complete(
            REAL_ACTIVATION_UID, EXT_TEST, ["external-test-result.md"], ACTOR,
            execution_mode="human", evidence_ref=EVIDENCE)
        receipts = _receipts(self.engine, self.run_dir, "external-test")
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["verdict"], "fail")


class MachineUnchanged(StepCompleteEvidenceBase):
    """Mutation-proof direction 1: no flags, no AC7 receipt — ever."""

    def test_machine_mode_emits_no_ac7_receipt_for_the_instrument(self):
        self.fresh()
        self.engine.action_step_complete(
            REAL_ACTIVATION_UID, EXT_TEST, ["external-test-result.md"], ACTOR)
        self.assertEqual(_receipts(self.engine, self.run_dir, "external-test"), [])

    def test_flags_on_an_ordinary_step_are_a_no_op(self):
        self.fresh(evidence=EVIDENCE_TEMPLATE.format(
            uid=EVIDENCE, verdict="pass", package=ACTIVE_CANDIDATE))
        _rewind_to_started(self.run_dir, ORDINARY_STEP)
        result = self.engine.action_step_complete(
            REAL_ACTIVATION_UID, ORDINARY_STEP, ["x.md"], ACTOR,
            execution_mode="agent", evidence_ref=EVIDENCE)
        self.assertIn("completed", result)
        for instrument in ("external-test", "harness", "full-validator", "cold-walk"):
            self.assertEqual(_receipts(self.engine, self.run_dir, instrument), [])


class TheRefusals(StepCompleteEvidenceBase):
    def _refused(self, evidence, **kwargs):
        self.fresh(evidence=evidence)
        before = _md5(self.run_dir / "run.jsonl")
        with self.assertRaises(self.engine.ContractError):
            self.engine.action_step_complete(
                REAL_ACTIVATION_UID, EXT_TEST, ["external-test-result.md"], ACTOR,
                **kwargs)
        self.assertEqual(_md5(self.run_dir / "run.jsonl"), before,
                         "refusal must leave the journal untouched")

    def test_self_signed_evidence_refuses_without_writing(self):
        self._refused(EVIDENCE_TEMPLATE.format(
            uid=EVIDENCE, verdict="pass", package=ACTIVE_CANDIDATE).replace(
            "owner: sa.release-test-harness", f"owner: {ACTOR}"),
            execution_mode="human", evidence_ref=EVIDENCE)

    def test_wrong_package_refuses_without_writing(self):
        self._refused(EVIDENCE_TEMPLATE.format(
            uid=EVIDENCE, verdict="pass", package="a" * 64),
            execution_mode="human", evidence_ref=EVIDENCE)

    def test_mode_without_ref_refuses_without_writing(self):
        self._refused(None, execution_mode="agent", evidence_ref="")

    def test_vc_true_instrument_with_flags_refuses_wrong_lane(self):
        self.run_dir = _copy_scenario(self.tmp)
        _rewind_to_started(self.run_dir, HARNESS_STEP)
        before = _md5(self.run_dir / "run.jsonl")
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_complete(
                REAL_ACTIVATION_UID, HARNESS_STEP, ["x.md"], ACTOR,
                execution_mode="agent", evidence_ref=EVIDENCE)
        self.assertIn("verify-step", str(ctx.exception))
        self.assertEqual(_md5(self.run_dir / "run.jsonl"), before)

    def test_dry_run_writes_nothing_with_evidence(self):
        self.fresh(evidence=EVIDENCE_TEMPLATE.format(
            uid=EVIDENCE, verdict="pass", package=ACTIVE_CANDIDATE))
        before = _md5(self.run_dir / "run.jsonl")
        result = self.engine.action_step_complete(
            REAL_ACTIVATION_UID, EXT_TEST, ["external-test-result.md"], ACTOR,
            dry_run=True, execution_mode="human", evidence_ref=EVIDENCE)
        self.assertIn("step-complete", result)
        self.assertEqual(_md5(self.run_dir / "run.jsonl"), before)


if __name__ == "__main__":
    unittest.main()
