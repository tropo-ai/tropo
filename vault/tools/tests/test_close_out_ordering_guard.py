"""close-out ordering guard — the wall behind the one-way door.

close-out STAMPS final_commit. Run before complete-workflow, that stamp binds a
SECOND tested tree onto a run whose evidence already named one; the run then
reads as `theatre` to the release fan-in and can be superseded but never
repaired. On 2026-08-21 seven of eight v1.90 close candidates were wedged this
way in one afternoon, by two executives independently, an hour apart, each
doing the obvious thing.

Every test here is MUTATION-SENSITIVE by design: delete the guard in
action_close_out and test_the_guard_refuses_an_uncompleted_run goes RED. A test
that passes with the mechanism removed is decoration — this file exists because
documentation was not enough.

The guard is deliberately SCOPED (deb77758): it refuses only when a live run
exists and has not completed. The standalone release-ship invocation, which has
no run folder and therefore no evidence to corrupt, must keep working — a
refusal that also blocked it would be the same over-scoping defect one layer up.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def _load_runtime():
    spec = importlib.util.spec_from_file_location(
        "pipeline_runtime_guard", TOOLS / "9e7003b1.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["pipeline_runtime_guard"] = module
    spec.loader.exec_module(module)
    return module


class CloseOutOrderingGuardTests(unittest.TestCase):

    def setUp(self):
        self.rt = _load_runtime()

    def test_the_guard_refuses_an_uncompleted_run(self):
        """THE CAUSAL TEST. Remove the guard and this goes green — which is
        exactly the state that wedged seven runs."""
        self.rt._workflow_completed = lambda uid: False
        with self.assertRaises(self.rt.ValidationError) as caught:
            self.rt.action_close_out("aaaaaaaa", "test-actor",
                                     final_commit="0" * 40, dry_run=True)
        message = str(caught.exception)
        self.assertIn("CLOSE-OUT REFUSED", message)
        self.assertIn("complete-workflow", message,
                      "the refusal must name its cure, not merely refuse")

    def test_a_completed_run_is_not_blocked(self):
        """The guard must not become a blanket refusal."""
        self.rt._workflow_completed = lambda uid: True
        self.rt.read_vault_entry = lambda uid: None      # short-circuit after the guard
        result = self.rt.action_close_out("bbbbbbbb", "test-actor",
                                          final_commit="0" * 40, dry_run=True)
        self.assertFalse(result["found"])

    def test_the_standalone_path_survives(self):
        """No run at all -> proceed. This is the release-ship invocation the
        tool exists to serve; blocking it would over-scope the refusal."""
        self.rt._workflow_completed = lambda uid: None
        self.rt.read_vault_entry = lambda uid: None
        result = self.rt.action_close_out("cccccccc", "test-actor",
                                          final_commit="0" * 40, dry_run=True)
        self.assertFalse(result["found"])

    def test_absent_run_reports_none_not_false(self):
        """None and False must stay distinct: 'no run' is not 'incomplete run'.
        Collapsing them is how a scoped refusal becomes a blanket one."""
        self.assertIsNone(self.rt._workflow_completed("zzzzzzzz"))


if __name__ == "__main__":
    unittest.main()
