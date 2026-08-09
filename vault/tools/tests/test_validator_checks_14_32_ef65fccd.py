"""Governed Autonomy S1 (ef65fccd) — adversarial gauntlet for the two validator checks
named in the dev-spec as fakeable: check_step_completion_has_verification (Check 14) and
check_completion_recording (Check 32). Per the spec: "Fix/replace the two fakeable
validator checks (step-completion + completion-recording) with engine-written receipts.
Rule codified: self-authored events never satisfy a gate."

Each test plants the forged/stale shape and confirms the rewritten check catches it,
then confirms the honest equivalent passes clean. Self-running and pytest-compatible.
"""
from __future__ import annotations
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_VAULT_TOOLS = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("val", str(_VAULT_TOOLS / "tropo-validate.py"))
val = importlib.util.module_from_spec(spec)
spec.loader.exec_module(val)


class _SandboxedValidatorTest(unittest.TestCase):
    def setUp(self):
        self.vault = Path(tempfile.mkdtemp(prefix="validate-s1-")).resolve()
        (self.vault / "vault" / "files").mkdir(parents=True)
        (self.vault / "vault" / "pipeline-runs").mkdir(parents=True)
        (self.vault / "vault" / "events").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def _write_events(self, events: list[dict]):
        p = self.vault / "vault" / "pipeline-runs" / "run1" / "run.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    def _write_stream_event(self, event: dict):
        streams = self.vault / "vault" / "events" / "streams"
        streams.mkdir(parents=True, exist_ok=True)
        event_uid = event["event_uid"]
        (streams / "1111111111111111.jsonl").write_text(
            json.dumps(event) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(event["id"], event_uid)


class TestCheck14Provenance(_SandboxedValidatorTest):
    """T-1 (validator side): a receipt claiming verification_command provenance without
    the forensic shape to back it up must FAIL, not pass silently."""

    def test_forged_command_receipt_no_forensics_fails(self):
        # A129-class forgery: claim verifier_role_resolved:verification_command (the
        # provenance label that says "the engine ran a real command") but never actually
        # carry the forensic shape a real execution produces.
        self._write_events([
            {"event": "activation_contract_locked"},
            {"event": "step_completed", "step": "s1", "data": {}},
            {"event": "verification_receipt", "step": "s1", "data": {
                "verifier_role_resolved": "verification_command",
                "verdict": "pass",
                # no forensics — this is the forgery
            }},
        ])
        findings, checked, defects = val.check_step_completion_has_verification(self.vault)
        self.assertGreater(defects, 0, "a command-claiming receipt with no forensics must FAIL")
        self.assertTrue(any("structurally impossible post-S1" in f for f in findings))

    def test_honest_no_command_receipt_still_passes(self):
        # The legitimate no-forensics shape: verification_class:false auto-receipt,
        # never claims verification_command provenance in the first place.
        self._write_events([
            {"event": "activation_contract_locked"},
            {"event": "step_completed", "step": "s1", "data": {}},
            {"event": "verification_receipt", "step": "s1", "data": {
                "verifier_role_resolved": "same-as-executor",
                "verdict": "pass",
                "per_criterion": [],
            }},
        ])
        findings, checked, defects = val.check_step_completion_has_verification(self.vault)
        self.assertEqual(defects, 0, f"a legitimate no-command receipt must not be flagged; got {findings}")

    def test_missing_receipt_still_fails_baseline(self):
        # The original, pre-S1 check must still work — this is not a regression test
        # for a NEW behavior, just confirming the rewrite didn't drop the baseline.
        self._write_events([
            {"event": "activation_contract_locked"},
            {"event": "step_completed", "step": "s1", "data": {}},
        ])
        findings, checked, defects = val.check_step_completion_has_verification(self.vault)
        self.assertGreater(defects, 0)
        self.assertTrue(any("without a matching" in f for f in findings))


class TestCheck14SpotRederivation(_SandboxedValidatorTest):
    """T-2 (validator side): --thorough re-runs the recorded command and catches a
    receipt whose recorded exit_code/output no longer matches reality."""

    def test_thorough_catches_tampered_exit_code(self):
        # A real, executable command (genuinely exits 0) but the RECORDED exit_code in
        # the receipt has been tampered to claim a different result than the command
        # actually produces — exactly what spot re-derivation exists to catch.
        self._write_events([
            {"event": "activation_contract_locked"},
            {"event": "step_completed", "step": "s1", "data": {}},
            {"event": "verification_receipt", "step": "s1", "data": {
                "verifier_role_resolved": "verification_command",
                "verdict": "pass",
                "forensics": {
                    "command": 'python3 -c "import sys; sys.exit(0)"',
                    "cwd": str(self.vault),
                    "exit_code": 1,  # tampered — the real command actually exits 0
                    "output_sha256": "0" * 64,  # tampered — will not match live output
                    "started_at": "2026-01-01T00:00:00Z",
                    "finished_at": "2026-01-01T00:00:01Z",
                    "runtime_version": "v1.46.0",
                },
            }},
        ])
        findings, checked, defects = val.check_step_completion_has_verification(
            self.vault, thorough=True)
        self.assertGreater(defects, 0, "a tampered receipt must fail under --thorough")
        self.assertTrue(any("SPOT RE-DERIVATION mismatch" in f for f in findings))

    def test_thorough_passes_honest_matching_receipt(self):
        # Build the honest receipt the SAME way the engine does: run once to record the
        # true shape, then verify --thorough agrees with itself.
        import subprocess as _sp, hashlib as _hl
        cmd = 'python3 -c "print(1)"'
        result = _sp.run(["python3", "-c", "print(1)"], capture_output=True, text=True)
        real_hash = _hl.sha256(((result.stdout or "") + (result.stderr or "")).encode()).hexdigest()
        self._write_events([
            {"event": "activation_contract_locked"},
            {"event": "step_completed", "step": "s1", "data": {}},
            {"event": "verification_receipt", "step": "s1", "data": {
                "verifier_role_resolved": "verification_command",
                "verdict": "pass",
                "forensics": {
                    "command": cmd,
                    "cwd": str(self.vault),
                    "exit_code": 0,
                    "output_sha256": real_hash,
                    "started_at": "2026-01-01T00:00:00Z",
                    "finished_at": "2026-01-01T00:00:01Z",
                    "runtime_version": "v1.46.0",
                },
            }},
        ])
        findings, checked, defects = val.check_step_completion_has_verification(
            self.vault, thorough=True)
        self.assertEqual(defects, 0, f"an honest, matching receipt must pass under --thorough; got {findings}")

    def test_not_thorough_skips_reexecution(self):
        """Off by default: the same tampered receipt from test 1 does NOT fail without
        --thorough (real command re-execution is opt-in, not a routine-pass default)."""
        self._write_events([
            {"event": "activation_contract_locked"},
            {"event": "step_completed", "step": "s1", "data": {}},
            {"event": "verification_receipt", "step": "s1", "data": {
                "verifier_role_resolved": "verification_command",
                "verdict": "pass",
                "forensics": {
                    "command": 'python3 -c "import sys; sys.exit(0)"',
                    "cwd": str(self.vault),
                    "exit_code": 1,
                    "output_sha256": "0" * 64,
                    "started_at": "2026-01-01T00:00:00Z",
                    "finished_at": "2026-01-01T00:00:01Z",
                    "runtime_version": "v1.46.0",
                },
            }},
        ])
        findings, checked, defects = val.check_step_completion_has_verification(
            self.vault, thorough=False)
        self.assertEqual(defects, 0, "spot re-derivation must be opt-in, not automatic")


class TestCheck32FreshSurfaces(_SandboxedValidatorTest):
    """T-3 (validator side): a correlated completion event alone is not enough if the
    index never caught up — the fresh-surfaces gap."""

    def _write_terminal_item(self, uid: str, state: str = "done"):
        (self.vault / "vault" / "files" / f"{uid}.md").write_text(
            f"---\nuid: {uid}\nstate: {state}\n---\n\n# item\n"
        )

    def _write_correlated_event(self, uid: str):
        (self.vault / "vault" / "events" / "00-events.jsonl").write_text(
            json.dumps({"type": "tropo.cycle.closed", "correlationid": uid, "data": {}}) + "\n"
        )

    def test_correlated_but_index_missing_flags_info(self):
        self._write_terminal_item("aaaaaaaa")
        self._write_correlated_event("aaaaaaaa")
        # No 00-index.jsonl at all — the index has never caught up.
        findings, checked, defects = val.check_completion_recording(self.vault)
        self.assertTrue(any("fresh-surfaces gap" in f for f in findings))

    def test_correlated_but_index_disagrees_flags_info(self):
        self._write_terminal_item("bbbbbbbb")
        self._write_correlated_event("bbbbbbbb")
        (self.vault / "vault" / "00-index.jsonl").write_text(
            json.dumps({"uid": "bbbbbbbb", "state": "active"}) + "\n"
        )
        findings, checked, defects = val.check_completion_recording(self.vault)
        self.assertTrue(any("fresh-surfaces mismatch" in f for f in findings))

    def test_correlated_and_index_agrees_clean(self):
        self._write_terminal_item("cccccccc")
        self._write_correlated_event("cccccccc")
        (self.vault / "vault" / "00-index.jsonl").write_text(
            json.dumps({"uid": "cccccccc", "state": "done"}) + "\n"
        )
        findings, checked, defects = val.check_completion_recording(self.vault)
        self.assertFalse(any("fresh-surfaces" in f for f in findings),
                          f"a genuinely fresh, agreeing index must not be flagged; got {findings}")

    def test_no_correlated_event_still_fails_baseline(self):
        self._write_terminal_item("dddddddd")
        # No event at all — baseline check must still catch this (unchanged behavior).
        findings, checked, defects = val.check_completion_recording(self.vault)
        self.assertTrue(any("NO correlated completion event found" in f for f in findings))

    def test_stream_only_correlated_completion_is_accepted(self):
        self._write_terminal_item("eeeeeeee")
        (self.vault / "vault" / "00-index.jsonl").write_text(
            json.dumps({"uid": "eeeeeeee", "state": "done"}) + "\n"
        )
        event_uid = "evt_1111111111111111_00000001"
        self._write_stream_event({
            "id": event_uid,
            "event_uid": event_uid,
            "type": "tropo.cycle.closed",
            "correlationid": "eeeeeeee",
            "data": {},
        })
        findings, checked, defects = val.check_completion_recording(self.vault)
        self.assertEqual(checked, 1)
        self.assertEqual(defects, 0, findings)
        self.assertFalse(
            any("NO correlated completion event found" in finding for finding in findings),
            findings,
        )


class TestPostCutoverValidatorEventUnion(_SandboxedValidatorTest):
    def test_stream_only_agent_root_source_is_rejected(self):
        agents = self.vault / "vault" / "agents"
        agents.mkdir()
        (agents / "talos.md").write_text(
            "---\n"
            "uid: 76f0219f\n"
            "agent: talos\n"
            "party_uid: 34cf0f1c\n"
            "agent_root_uid: 123e12e7\n"
            "---\n",
            encoding="utf-8",
        )
        event_uid = "evt_1111111111111111_00000001"
        self._write_stream_event({
            "id": event_uid,
            "event_uid": event_uid,
            "type": "tropo.message.sent",
            "source": "/agents/talos",
            "source_uid": "123e12e7",
            "data": {"body": "wrong identity axis"},
        })
        findings, checked, defects = val.check_no_agent_emit_from_root_uid(self.vault)
        self.assertEqual(checked, 1)
        self.assertEqual(defects, 1)
        self.assertTrue(
            any(event_uid in finding and "MUST use party UID" in finding for finding in findings),
            findings,
        )

    def test_stream_only_pipeline_fixture_pollution_is_rejected(self):
        event_uid = "evt_1111111111111111_00000001"
        self._write_stream_event({
            "id": event_uid,
            "event_uid": event_uid,
            "type": "tropo.pipeline.activated",
            "source": "/pipeline-runtime",
            "source_uid": "9e7003b1",
            "data": {"activation_uid": "act2"},
        })
        findings, checked, defects = val.check_pipeline_event_fixture_pollution(
            self.vault
        )
        self.assertEqual(checked, 1)
        self.assertEqual(defects, 1)
        self.assertTrue(
            any(event_uid in finding and "fixture-shaped" in finding for finding in findings),
            findings,
        )


if __name__ == "__main__":
    unittest.main()
