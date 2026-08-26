"""AC6 (v1.92 Stream 2, 1a478c48): the dev-pipeline terminal step's verdict
is dev-scoped -- it must not depend on release-pipeline machinery being green.

`0b6b244c` (verify-dev-spec, dev-pipeline's TERMINAL step) declared
`pytest -q vault/tools/tests/test_two_pipeline_split_0a0a6777.py` as its
verification_command. That suite is the executable contract for BOTH
pipelines' split (0a0a6777) -- it also asserts AC4-AC8 and Stage 9, which are
release-plan fan-in, package digest, publication receipts, and release-graph
activation: substrate a stranger studio that has never cut a release does not
have and should never need to satisfy in order to close a DEV cycle
(A156's finding 2026-08-24, evt_b51c083be28ac6fe_00000145 -- exactly the
"constitutional coupling the 0a0a6777 split was supposed to remove").

THE CURE, per AC6's own text: "0b6b244c's verification command exercises
dev-scope substrate only (the run's own evidence completeness and close
integrity), with the split-contract suite remaining a studio/release-side
check where it belongs."

This file IS that dev-scope substrate. It is the CLOSE-INTEGRITY half of
`test_two_pipeline_split_0a0a6777.py`'s `AC3TerminalTestedShaClose` class,
extracted rather than re-imported -- AC3 there tests
`engine.assert_one_unchanged_tested_sha` and the terminal step's own weld
shape (`action_terminal_verify`), both of which are dev-pipeline substrate on
their face (0a0a6777 §3 is the terminal contract of dev-pipeline v2
specifically) and carry no release-pipeline dependency. AC4-AC8/Stage 9 stay
in the original file, unmoved, where the release-pipeline actually lives.

`0b6b244c.md`'s verification_command is repointed at this file's fully
qualified selector as part of this same change:
    python3 -m unittest vault.tools.tests.test_dev_terminal_step_dev_scope_only_v192

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_dev_terminal_step_dev_scope_only_v192
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location(
    "dev_terminal_engine_v192", TOOLS / "9e7003b1.py")
assert _spec and _spec.loader
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)


class NoReleasePipelineSubstrateIsReferenced(unittest.TestCase):
    """AC6's own verify command, run against ITSELF: the declared command
    must reference no release-pipeline test or substrate. Checked against the
    live frontmatter, not a hardcoded string, so a future hand-edit of
    0b6b244c.md that reintroduces the coupling is caught here too."""

    def test_0b6b244c_declares_this_file_not_the_split_suite(self) -> None:
        text = (ROOT / "vault" / "files" / "0b6b244c.md").read_text(encoding="utf-8")
        m = None
        for line in text.splitlines():
            if line.startswith("verification_command:"):
                m = line.split(":", 1)[1].strip()
                break
        self.assertIsNotNone(m, "0b6b244c.md declares no verification_command")
        self.assertNotIn(
            "test_two_pipeline_split_0a0a6777", m,
            "0b6b244c still declares the coupled split-contract suite",
        )
        self.assertIn(
            "test_dev_terminal_step_dev_scope_only_v192", m,
            "0b6b244c does not declare this dev-scoped file",
        )
        # Names no other known release-pipeline test file either -- narrower
        # than string-matching just the one suite this AC was filed against.
        for release_marker in ("release_saga", "release_events", "publish",
                                "fan_in", "tropo-lock-release-plan",
                                "tropo-publish-release"):
            self.assertNotIn(
                release_marker, m,
                f"declared verification_command references release-side "
                f"marker {release_marker!r}",
            )

    def test_the_declared_command_executes_at_head_and_returns_a_verdict(self) -> None:
        """Not a selector error (the 0c6518ef class A156 repaired): the
        command must actually RUN and produce a real pass/fail verdict, not
        die on an import or collection error that a naive exit-code check
        would misreport as a legitimate failing verdict.

        Targets the two dev-scope classes directly rather than this whole
        module -- invoking the whole module here would spawn this very test
        again inside the subprocess, recursively, forever. Those two classes
        ARE the substance 0b6b244c's verdict actually depends on; this
        class's own two tests are the meta-check ABOUT the declared command,
        not part of what the command needs to re-verify about itself.
        """
        result = subprocess.run(
            [sys.executable, "-m", "unittest",
             "vault.tools.tests.test_dev_terminal_step_dev_scope_only_v192"
             ".TerminalVerdictBindsToOneUnchangedTestedSha",
             "vault.tools.tests.test_dev_terminal_step_dev_scope_only_v192"
             ".CloseIsWeldedNotASkippableStep"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )
        combined = result.stdout + result.stderr
        self.assertNotIn("ModuleNotFoundError", combined)
        self.assertNotIn("ImportError", combined)
        self.assertRegex(
            combined, r"Ran \d+ tests?",
            "command did not report a real test run (selector/collection "
            "error) -- this is the exact class A156 repaired at 0c6518ef",
        )


class TerminalVerdictBindsToOneUnchangedTestedSha(unittest.TestCase):
    """The close-integrity half of the original AC3TerminalTestedShaClose,
    extracted verbatim in substance (adapted import path only). Missing,
    abbreviated, stale, and "theatre" (multi-tree) evidence all refuse; a
    single clean SHA is accepted. This is `engine.assert_one_unchanged_
    tested_sha` -- 0b6b244c's own binding mechanism, not release substrate.
    """

    FORTY_HEX = "a" * 40
    OTHER_HEX = "b" * 40

    def test_missing_tested_sha_refuses(self) -> None:
        with self.assertRaises(Exception) as caught:
            engine.assert_one_unchanged_tested_sha(ROOT, [], None)
        self.assertIn("no tested-tree SHA supplied", str(caught.exception))

    def test_an_abbreviated_sha_is_not_a_tree_identity(self) -> None:
        with self.assertRaises(Exception) as caught:
            engine.assert_one_unchanged_tested_sha(ROOT, [], "a1b2c3d")
        self.assertIn("not 40 hex", str(caught.exception))

    def test_stale_sha_refuses_because_it_describes_another_tree(self) -> None:
        with self.assertRaises(Exception) as caught:
            engine.assert_one_unchanged_tested_sha(ROOT, [], self.FORTY_HEX)
        message = str(caught.exception)
        self.assertIn("stale", message)
        self.assertIn("describes a different tree", message)

    def test_theatre_two_trees_in_one_run_refuses(self) -> None:
        """The failure that looks most like success: every AC passed --
        against different trees. Evidence completeness means the ACs bind to
        the SAME tree, not merely that each has a passing receipt."""
        head = engine._git(ROOT, "rev-parse", "HEAD")
        events = [{"event": "verification_receipt",
                   "data": {"verdict": "pass", "tested_sha": self.OTHER_HEX}}]
        with self.assertRaises(Exception) as caught:
            engine.assert_one_unchanged_tested_sha(ROOT, events, head)
        message = str(caught.exception)
        self.assertIn("theatre", message)
        self.assertIn(self.OTHER_HEX, message)

    def test_control_a_clean_single_sha_is_accepted(self) -> None:
        """Without this, every refusal above passes for a function that
        always raises -- which is a refusal machine, not a gate."""
        head = engine._git(ROOT, "rev-parse", "HEAD")
        dirty = engine._git(ROOT, "status", "--porcelain", "--untracked-files=no")
        if dirty:
            self.skipTest("working tree has tracked modifications; run on a clean tree")
        events = [{"event": "verification_receipt",
                   "data": {"verdict": "pass", "tested_sha": head}}]
        self.assertEqual(engine.assert_one_unchanged_tested_sha(ROOT, events, head), head)

    def test_mutation_removing_the_binding_admits_a_stale_close(self) -> None:
        """Teeth: prove the binding is what refuses. Re-implements the check
        with the head comparison removed and asserts the stale SHA sails
        through -- if this ever passes with the binding still in place, the
        refusals above are firing for some other reason."""
        def without_binding(vault_root, events, tested_sha):
            if not tested_sha or not engine.TESTED_SHA_RE.match(tested_sha):
                raise ValueError("still malformed")
            return tested_sha  # the head/dirty comparison deliberately absent
        self.assertEqual(without_binding(ROOT, [], self.FORTY_HEX), self.FORTY_HEX)
        with self.assertRaises(Exception):
            engine.assert_one_unchanged_tested_sha(ROOT, [], self.FORTY_HEX)


class CloseIsWeldedNotASkippableStep(unittest.TestCase):
    """0a0a6777 §3's whole justification: a close step is skippable, so
    there is no close WorkflowNode -- closure is a side effect of a COMPLETE
    terminal verdict, welded in the engine itself. Dev-pipeline substrate:
    this is 0b6b244c's own action, not anything release-side."""

    def test_terminal_verify_welds_closure_only_on_a_complete_verdict(self) -> None:
        source = (TOOLS / "9e7003b1.py").read_text(encoding="utf-8")
        body = source[source.index("def action_terminal_verify("):]
        # Bound the slice to the function body, matching the original test's
        # approach of stopping before the next top-level marker rather than
        # relying on indentation parsing.
        next_marker = source.index(
            "\n#: Local, gitignored journal", source.index("def action_terminal_verify(")
        )
        body = source[source.index("def action_terminal_verify("):next_marker]
        self.assertIn("run_close_out_hook", body,
                      "closure is not welded to the terminal step")
        self.assertIn("_write_close_journal", body,
                      "the close transaction has no journal")
        self.assertIn('if verdict != "complete":', body,
                      "an incomplete verdict must weld nothing")


if __name__ == "__main__":
    unittest.main()
