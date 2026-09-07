"""f015ef8ff398: `tropo-lock-release-plan.py --check` names EVERY unmet lock
precondition in one run and writes nothing. Three plants on the lock suite's
own fixture must surface together; cured, the check passes; the plan tree is
byte-identical before and after either run. Composes the e2e fixture rather
than inheriting it, so its eighty tests do not re-run here. argus-a172."""
import hashlib
import unittest

import importlib.util
from pathlib import Path

# The e2e fixture module, loaded by PATH so this file imports under both shapes:
# `python3 -m unittest vault.tools.tests.test_release_lock_check_flag` and as a
# script from the tests dir (G122's second read, 2026-09-06: the bare sibling
# import resolved only as a script -- the f01558e51a8f invocation-shape class).
_E2E_PATH = Path(__file__).resolve().parent / "test_release_plan_lock_end_to_end.py"
_spec = importlib.util.spec_from_file_location("test_release_plan_lock_end_to_end", _E2E_PATH)
_e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_e2e)
rl = _e2e.rl


class CheckFlagListsEveryProblem(unittest.TestCase):
    def setUp(self):
        self.fx = _e2e.ReleaseLockEndToEnd("setUp")
        self.fx.setUp()
        self.files, self.runs = self.fx.files, self.fx.runs

    def tearDown(self):
        self.fx.tearDown()

    def _plan_text(self):
        return (self.files / "b1a00001.md").read_text(encoding="utf-8")

    def _digest_tree(self):
        return hashlib.sha256(b"".join(sorted(p.read_bytes() for p in self.files.glob("*.md")))).hexdigest()

    def test_clean_fixture_passes_and_writes_nothing(self):
        before = self._digest_tree()
        problems = rl.check_release_lock("b1a00001", "tester", self.files, self.runs)
        self.assertEqual(problems, [], problems)
        self.assertEqual(before, self._digest_tree())

    def test_three_plants_are_named_together(self):
        text = self._plan_text().replace("status: specify", "status: active")          # 1. status the lock rejects
        text = text.replace("foundation:\n  - fnd00001\n", "")                        # 2. a lock-time field gone
        (self.files / "b1a00001.md").write_text(text, encoding="utf-8")
        self.fx._write("e0000002", "---\nuid: e0000002\ntype: completion-report\ntitle: evidence two\nstatus: done\nverdict: fail\n---\n")  # 3. a FAIL report as evidence
        before = self._digest_tree()
        problems = rl.check_release_lock("b1a00001", "tester", self.files, self.runs)
        joined = "\n".join(problems)
        self.assertIn("status 'active'", joined, joined)
        self.assertIn("5ec00002", joined, joined)
        self.assertIn("foundation", joined, joined)
        self.assertGreaterEqual(len(problems), 3, joined)
        self.assertEqual(before, self._digest_tree(), "--check must write nothing")

    def test_the_lock_itself_still_stops_at_the_first(self):
        text = self._plan_text().replace("status: specify", "status: active")
        (self.files / "b1a00001.md").write_text(text, encoding="utf-8")
        with self.assertRaises(rl.LockRefused):
            rl.plan_release_lock("b1a00001", "tester", self.files, self.runs, mint=lambda *a, **k: "f015aaaaaaaa")


if __name__ == "__main__":
    unittest.main()
