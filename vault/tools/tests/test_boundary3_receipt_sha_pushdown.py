"""Receipt-level tested-SHA binding (0a0a6777 AC3; argus-a147 boundary-3 ruling).

The ruling: terminal-only stamping is weaker than locked AC3, because it lets
different ACs pass on different trees without the terminal having the provenance
to detect it. So the binding moves down to the emitter and the terminal only
aggregates.

Required controls, all present below: missing, mixed, and stale — each refusing
false success, each with a control proving it is not a function that refuses
everything.

Selectors are fully qualified because pytest is absent in this environment:
    python3 -m unittest vault.tools.tests.test_boundary3_receipt_sha_pushdown
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from lib import tested_tree as tt  # noqa: E402

_spec = importlib.util.spec_from_file_location("eng", TOOLS / "9e7003b1.py")
eng = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eng)

SHA_A = "a" * 40
SHA_B = "b" * 40


def _receipt(sha, event="verification_receipt", step="1234abcd", state="clean"):
    return {"event": event, "step": step,
            "data": {"tested_commit_sha": sha, "tested_tree_state": state,
                     "tested_tree_detail": ""}}


class TreeIdentityIsHonestAboutWhatItCannotSay(unittest.TestCase):
    """Three different failures, kept distinct.

    Folding dirty / moved / unknown into one "no SHA" would lose the difference
    between "I cannot see" and "you are wrong", which doctrine treats as
    different verdicts.
    """

    def test_a_clean_tree_binds(self) -> None:
        """Control, run against a real repo so the happy path is real."""
        with tempfile.TemporaryDirectory() as tmp:
            self._git_init(tmp)
            identity = tt.read_tree_identity(tmp)
            self.assertEqual(identity.state, "clean", identity.detail)
            self.assertTrue(identity.is_bindable)
            self.assertEqual(len(identity.commit_sha), 40)

    def test_a_dirty_tree_refuses_to_name_a_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._git_init(tmp)
            (Path(tmp) / "seed.txt").write_text("changed\n")
            identity = tt.read_tree_identity(tmp)
            self.assertEqual(identity.state, "dirty")
            self.assertIsNone(identity.commit_sha,
                              "a dirty tree was given a commit it cannot substantiate")
            self.assertFalse(identity.is_bindable)

    def test_a_non_repo_is_unknown_and_not_dirty(self) -> None:
        """"I cannot see" must not be reported as "you are wrong"."""
        with tempfile.TemporaryDirectory() as tmp:
            identity = tt.read_tree_identity(tmp)
            self.assertEqual(identity.state, "unknown")
            self.assertIsNone(identity.commit_sha)

    def test_a_tree_that_moves_during_execution_binds_nothing(self) -> None:
        """The case a single before-reading cannot see.

        Both endpoints are individually CLEAN here, so any check that sampled
        once would happily stamp a SHA for a run that spanned two trees.
        """
        moved = tt.bind_execution(tt.TreeIdentity(SHA_A, "clean"),
                                  tt.TreeIdentity(SHA_B, "clean"))
        self.assertEqual(moved.state, "moved")
        self.assertIsNone(moved.commit_sha)

    def test_the_control_an_unmoved_tree_still_binds(self) -> None:
        same = tt.bind_execution(tt.TreeIdentity(SHA_A, "clean"),
                                 tt.TreeIdentity(SHA_A, "clean"))
        self.assertTrue(same.is_bindable)
        self.assertEqual(same.commit_sha, SHA_A)

    def test_provenance_is_an_explicit_null_not_an_absent_key(self) -> None:
        """An absent key reads as an old emitter; a null is this one saying it looked."""
        fields = tt.provenance_fields(tt.TreeIdentity(None, "dirty", "why"))
        self.assertIn("tested_commit_sha", fields)
        self.assertIsNone(fields["tested_commit_sha"])
        self.assertEqual(fields["tested_tree_state"], "dirty")

    @staticmethod
    def _git_init(path: str) -> None:
        run = lambda *a: subprocess.run(a, cwd=path, capture_output=True, check=True)
        run("git", "init", "-q")
        run("git", "config", "user.email", "t@example.com")
        run("git", "config", "user.name", "t")
        (Path(path) / "seed.txt").write_text("seed\n")
        run("git", "add", "-A")
        run("git", "commit", "-qm", "seed")


class TheEmitterStampsAndNeverInvents(unittest.TestCase):

    def test_a_receipt_from_a_real_clean_repo_carries_the_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            TreeIdentityIsHonestAboutWhatItCannotSay._git_init(tmp)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp,
                                  capture_output=True, text=True).stdout.strip()
            receipt = eng._run_verification_command("python3 -c pass", cwd=tmp)
            self.assertEqual(receipt["tested_commit_sha"], head)
            self.assertEqual(receipt["tested_tree_state"], "clean")

    def test_a_command_that_dirties_the_tree_while_running_gets_no_sha(self) -> None:
        """The post-execution reading, exercised at the EMITTER.

        Added after a mutation survived: dropping the second tree reading and
        stamping `_tree_before` alone left every test green, because the unit
        test for `bind_execution` covers the reconciliation while nothing
        covered the emitter actually taking two readings. A command that starts
        on a clean tree and modifies it as a side effect is the real shape of
        that failure — the before-reading is clean and honestly says so, and a
        single-sample emitter would stamp a commit for a run whose subject moved
        underneath it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            TreeIdentityIsHonestAboutWhatItCannotSay._git_init(tmp)
            script = Path(tmp) / "dirty_it.py"
            script.write_text(
                "from pathlib import Path\n"
                "Path(__file__).parent.joinpath('seed.txt').write_text('moved\\n')\n"
            )
            subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-qm", "add script"], cwd=tmp,
                           capture_output=True, check=True)

            receipt = eng._run_verification_command("python3 dirty_it.py", cwd=tmp)

            self.assertEqual(receipt["verdict"], "pass", "the command itself should succeed")
            self.assertIsNone(
                receipt["tested_commit_sha"],
                "the tree moved during execution but the receipt still named a commit",
            )

    def test_a_receipt_from_a_dirty_repo_carries_null_and_the_command_still_runs(self) -> None:
        """Warn-safe (deb77758): the work proceeds, the claim is not made.

        Refusing to run here would sit on the hottest path in the studio and
        prevent nothing at that moment — nobody has believed anything yet. The
        harm is a mixed-provenance close, and that is where the refusal fires.
        """
        with tempfile.TemporaryDirectory() as tmp:
            TreeIdentityIsHonestAboutWhatItCannotSay._git_init(tmp)
            (Path(tmp) / "seed.txt").write_text("dirty\n")
            receipt = eng._run_verification_command("python3 -c pass", cwd=tmp)
            self.assertIsNone(receipt["tested_commit_sha"])
            self.assertEqual(receipt["tested_tree_state"], "dirty")
            self.assertEqual(receipt["verdict"], "pass",
                             "the command must still run; only the claim is withheld")


class TheTerminalAggregatesAndNeverInvents(unittest.TestCase):
    """Missing / mixed / stale, in the ruling's required order."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="b3-terminal-")).resolve()
        TreeIdentityIsHonestAboutWhatItCannotSay._git_init(str(self.tmp))
        self.head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.tmp,
                                   capture_output=True, text=True).stdout.strip()

    def test_missing_provenance_refuses_even_though_nothing_conflicts(self) -> None:
        """THE HOLE. A null-SHA receipt never disagrees, so the conflict check is
        blind to it — this is the exact case boundary 3 was raised about."""
        events = [_receipt(self.head), _receipt(None, step="beefcafe", state="dirty")]
        with self.assertRaises(eng.ValidationError) as caught:
            eng.assert_one_unchanged_tested_sha(self.tmp, events, self.head)
        self.assertIn("missing provenance", str(caught.exception))
        self.assertIn("beefcafe", str(caught.exception))

    def test_the_control_all_receipts_provenanced_is_accepted(self) -> None:
        """Without this, the missing-provenance test passes for a gate that
        refuses every run."""
        events = [_receipt(self.head), _receipt(self.head, step="beefcafe")]
        self.assertEqual(
            eng.assert_one_unchanged_tested_sha(self.tmp, events, self.head), self.head)

    def test_mixed_provenance_is_theatre(self) -> None:
        events = [_receipt(self.head), _receipt(SHA_B, step="beefcafe")]
        with self.assertRaises(eng.ValidationError) as caught:
            eng.assert_one_unchanged_tested_sha(self.tmp, events, self.head)
        self.assertIn("theatre", str(caught.exception))

    def test_missing_is_checked_before_mixed_and_both_before_stale(self) -> None:
        """Ordering is the ruling's, and it is load-bearing.

        A dirty working tree is an ENVIRONMENTAL fact. An unprovenanced or mixed
        receipt is a defect in the run itself, true no matter what the tree looks
        like now. Checking the environment first lets a dirty tree mask a real
        one — the same ordering bug I already fixed once between theatre and
        stale, reappearing one layer up.
        """
        (self.tmp / "seed.txt").write_text("now dirty\n")  # environmental staleness
        events = [_receipt(None, step="beefcafe", state="dirty")]
        with self.assertRaises(eng.ValidationError) as caught:
            eng.assert_one_unchanged_tested_sha(self.tmp, events, self.head)
        self.assertIn("missing provenance", str(caught.exception))
        self.assertNotIn("(stale)", str(caught.exception))

    def test_stale_still_refuses_once_provenance_is_sound(self) -> None:
        (self.tmp / "seed.txt").write_text("now dirty\n")
        events = [_receipt(self.head)]
        with self.assertRaises(eng.ValidationError) as caught:
            eng.assert_one_unchanged_tested_sha(self.tmp, events, self.head)
        self.assertIn("stale", str(caught.exception))

    def test_only_required_receipt_kinds_are_policed(self) -> None:
        """A step_started event has no tree to name and must not be demanded one.

        Without this the gate would refuse every run for events that were never
        evidence, which is the permanently-red check deb77758 warns teaches the
        crew to ignore all checks.
        """
        events = [_receipt(self.head), {"event": "step_started", "data": {}}]
        self.assertEqual(
            eng.assert_one_unchanged_tested_sha(self.tmp, events, self.head), self.head)


class MutationEvidenceBindsOneTree(unittest.TestCase):

    def test_a_sound_proof_binds_baseline_and_green_to_the_same_tree(self) -> None:
        fields = tt.mutation_evidence_fields(
            tt.TreeIdentity(SHA_A, "clean"), "diff --git a b", "fail", "pass", SHA_A)
        self.assertTrue(fields["binds_one_tree"])
        self.assertEqual(len(fields["mutant_diff_sha256"]), 64)
        self.assertEqual(fields["red_verdict"], "fail")
        self.assertEqual(fields["green_after_verdict"], "pass")

    def test_a_proof_whose_green_ran_on_another_tree_does_not_bind(self) -> None:
        """Red on one tree and green on another proves nothing about either."""
        fields = tt.mutation_evidence_fields(
            tt.TreeIdentity(SHA_A, "clean"), "diff", "fail", "pass", SHA_B)
        self.assertFalse(fields["binds_one_tree"])

    def test_an_unbindable_baseline_does_not_bind(self) -> None:
        fields = tt.mutation_evidence_fields(
            tt.TreeIdentity(None, "dirty"), "diff", "fail", "pass", SHA_A)
        self.assertFalse(fields["binds_one_tree"])

    def test_the_mutant_diff_identifies_what_was_planted(self) -> None:
        """So a proof cannot later be re-described as having planted something else."""
        one = tt.mutation_evidence_fields(
            tt.TreeIdentity(SHA_A, "clean"), "planted X", "fail", "pass", SHA_A)
        two = tt.mutation_evidence_fields(
            tt.TreeIdentity(SHA_A, "clean"), "planted Y", "fail", "pass", SHA_A)
        self.assertNotEqual(one["mutant_diff_sha256"], two["mutant_diff_sha256"])


if __name__ == "__main__":
    unittest.main()
