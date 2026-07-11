"""Tests for the B3-ext branch-applicability fix (event 00005650, Talos 2026-07-05).

Bug: `evaluate_criterion` treated `<ref>.triggered_doc_spec_uids == []` as a literal
"nothing was ever triggered" check. That's correct for cycles with no doc leg, but
fails a cycle that legitimately triggered a doc leg which ran to completion (v1.77
dev-spec ba454e56 -> triggered_doc_spec_uids: [06552e01], 06552e01 status:archived).
The recompute needs to treat "leg triggered AND completed cleanly" as an equally
valid pass, not just "leg never triggered".

Fix: `_evaluate_triggered_leg_criterion` generalizes this for both
triggered_doc_spec_uids and triggered_test_spec_uids: empty list passes (no-leg
branch); non-empty list passes iff every referenced spec resolved to a terminal
(done/archived) status (leg-completed branch); otherwise fails with a clear
"still pending" rationale.
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

_CRITERION = "dev_spec.triggered_doc_spec_uids == []"


class TestBranchApplicabilityFix(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b3ext-branch-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.files.mkdir(parents=True)
        self._orig_vault_files = eng.VAULT_FILES
        eng.VAULT_FILES = self.files

    def tearDown(self):
        eng.VAULT_FILES = self._orig_vault_files
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, uid: str, fm: dict, body: str = "body\n"):
        eng.write_vault_entry(uid, fm, body)

    def test_real_v1_77_case_passes(self):
        """Exact real substrate shape: dev-spec with a completed (archived) doc leg."""
        self._write("dead0001", {"uid": "dead0001", "type": "dev-spec",
                                  "triggered_doc_spec_uids": ["dead0002"]})
        self._write("dead0002", {"uid": "dead0002", "type": "doc-spec", "status": "archived"})
        snapshot = eng.build_snapshot([_CRITERION], {"dev_spec": "dead0001"})
        result = eng.evaluate_criterion(_CRITERION, {"dev_spec": "dead0001"}, snapshot)
        self.assertEqual(result["verdict"], "pass")

    def test_no_leg_triggered_still_passes(self):
        """Pre-fix behavior preserved: empty list still passes (no-leg branch)."""
        self._write("dead0003", {"uid": "dead0003", "type": "dev-spec",
                                  "triggered_doc_spec_uids": []})
        snapshot = eng.build_snapshot([_CRITERION], {"dev_spec": "dead0003"})
        result = eng.evaluate_criterion(_CRITERION, {"dev_spec": "dead0003"}, snapshot)
        self.assertEqual(result["verdict"], "pass")

    def test_leg_triggered_but_still_open_fails(self):
        """Leg triggered but doc-spec is still active/draft — must FAIL, not silently pass."""
        self._write("dead0004", {"uid": "dead0004", "type": "dev-spec",
                                  "triggered_doc_spec_uids": ["dead0005"]})
        self._write("dead0005", {"uid": "dead0005", "type": "doc-spec", "status": "active"})
        snapshot = eng.build_snapshot([_CRITERION], {"dev_spec": "dead0004"})
        result = eng.evaluate_criterion(_CRITERION, {"dev_spec": "dead0004"}, snapshot)
        self.assertEqual(result["verdict"], "fail")
        self.assertIn("not cleanly complete", result["rationale"])

    def test_leg_triggered_done_status_also_passes(self):
        """'done' is the other terminal status (alongside 'archived')."""
        self._write("dead0006", {"uid": "dead0006", "type": "dev-spec",
                                  "triggered_doc_spec_uids": ["dead0007"]})
        self._write("dead0007", {"uid": "dead0007", "type": "doc-spec", "status": "done"})
        snapshot = eng.build_snapshot([_CRITERION], {"dev_spec": "dead0006"})
        result = eng.evaluate_criterion(_CRITERION, {"dev_spec": "dead0006"}, snapshot)
        self.assertEqual(result["verdict"], "pass")

    def test_multiple_triggered_specs_all_must_be_terminal(self):
        """Two triggered specs, one still open -> overall FAIL (not a majority vote)."""
        self._write("dead0008", {"uid": "dead0008", "type": "dev-spec",
                                  "triggered_doc_spec_uids": ["dead0009", "dead000a"]})
        self._write("dead0009", {"uid": "dead0009", "type": "doc-spec", "status": "archived"})
        self._write("dead000a", {"uid": "dead000a", "type": "doc-spec", "status": "active"})
        snapshot = eng.build_snapshot([_CRITERION], {"dev_spec": "dead0008"})
        result = eng.evaluate_criterion(_CRITERION, {"dev_spec": "dead0008"}, snapshot)
        self.assertEqual(result["verdict"], "fail")

    def test_generalizes_symmetrically_to_test_spec_field(self):
        """The fix is field-generic — triggered_test_spec_uids gets the same treatment."""
        criterion = "dev_spec.triggered_test_spec_uids == []"
        self._write("dead000b", {"uid": "dead000b", "type": "dev-spec",
                                  "triggered_test_spec_uids": ["dead000c"]})
        self._write("dead000c", {"uid": "dead000c", "type": "test-spec", "status": "done"})
        snapshot = eng.build_snapshot([criterion], {"dev_spec": "dead000b"})
        result = eng.evaluate_criterion(criterion, {"dev_spec": "dead000b"}, snapshot)
        self.assertEqual(result["verdict"], "pass")

    def test_unrelated_field_equals_empty_list_unaffected(self):
        """Only the two known triggered-leg fields get branch-aware treatment — an
        unrelated field compared to '[]' keeps the original literal-equality semantics."""
        criterion = "dev_spec.some_other_list_field == []"
        self._write("dead000d", {"uid": "dead000d", "type": "dev-spec",
                                  "some_other_list_field": ["not-empty"]})
        snapshot = eng.build_snapshot([criterion], {"dev_spec": "dead000d"})
        result = eng.evaluate_criterion(criterion, {"dev_spec": "dead000d"}, snapshot)
        self.assertEqual(result["verdict"], "fail")
        self.assertNotIn("leg", result["rationale"])


if __name__ == "__main__":
    unittest.main()
