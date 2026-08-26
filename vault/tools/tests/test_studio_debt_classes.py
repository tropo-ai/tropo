#!/usr/bin/env python3
"""The per-class debt ratchet: does it actually name what grew?

talos-t40, 2026-08-09, velocity item 3 of the v1.86 retrospective.

The item exists because the gate printed "studio debt UP 5, from 504 to 509" and
nothing else, costing about an hour of archaeology on release night. So the test
that matters is not "does it still refuse" — it always did — but "does the
refusal contain the answer". Every case below is written against that.

Synthetic validator output on purpose. Running the real validator takes ~3
minutes and its findings move under you as the studio changes, which is exactly
the kind of fixture that makes a test look green for reasons unrelated to its
claim.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import studio_debt_classes as sdc  # noqa: E402

SAMPLE = """
--- UID Consistency ---
[PASS] 4000 entries checked

--- Live Template + Body Shape (CURRENT surface only; archived excluded) ---
[FAIL] 2679 current template-governed entries checked; 9 defect(s)
  [ERROR] aaaa1111 (note): INCOMPLETE — required placeholder survived
  [WARN] bbbb2222 (note): cosmetic

--- Inbox Transition Protocol (v1.68 S2; 344607e4; HARD=terminal ERROR) ---
  [INFO] Inbox violations: 0 HARD + 18 SOFT
  [WARN] cccc3333 — SOFT inbox violation
"""


class ClassKeyIsStableAcrossVersionChurn(unittest.TestCase):
    def test_the_version_tag_is_not_part_of_the_key(self) -> None:
        """A curated entry must not unmatch when a heading gets a version bump.

        This is velocity item 4's lesson applied to item 3: if the class key
        included `(v1.68 S2; 344607e4; ...)`, then a human's curated exemption
        would silently stop matching the next time that heading changed, and the
        class would start gating again with no message saying why.
        """
        self.assertEqual(
            sdc.class_key("Inbox Transition Protocol (v1.68 S2; 344607e4; HARD=x)"),
            "Inbox Transition Protocol",
        )
        self.assertEqual(
            sdc.class_key("Inbox Transition Protocol (v9.99 ZZ; deadbeef)"),
            "Inbox Transition Protocol",
        )
        self.assertEqual(sdc.class_key("UID Consistency"), "UID Consistency")


class ClassificationCountsTheRightLines(unittest.TestCase):
    def test_only_fail_and_error_count_as_debt(self) -> None:
        counts = sdc.classify(SAMPLE)
        self.assertEqual(counts.get("Live Template + Body Shape"), 2)
        self.assertNotIn("UID Consistency", counts)
        self.assertNotIn("Inbox Transition Protocol", counts)

    def test_findings_before_any_heading_are_not_dropped(self) -> None:
        """A finding with nowhere to go is the one that slips a per-class gate."""
        counts = sdc.classify("[ERROR] something broke before any section\n")
        self.assertEqual(counts, {"(preamble)": 1})

    def test_a_class_that_vanishes_shows_up_in_the_delta(self) -> None:
        """A check that stops running reports zero and looks like progress.

        This studio has shipped that exact defect more than once — three
        validators reporting "0 rows checked" (T37), and my own canonical-
        reference check going to "[PASS] 0 vault entries checked" earlier today.
        A delta that only reports growth cannot see it.
        """
        moved = sdc.delta({"Gone Check": 4}, {})
        self.assertEqual(moved, {"Gone Check": (4, 0)})


class TheRefusalContainsTheAnswer(unittest.TestCase):
    """End-to-end through the real gate, with the validator stubbed.

    The stub is a two-line script that prints canned output, so these run in
    milliseconds and assert on the gate's REPORT rather than on the studio.
    """

    def _run_gate(self, validator_output: str, baseline: dict, extra_argv=()):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = root / "vault" / "tools"
            tests = tools / "tests"
            tests.mkdir(parents=True)
            (tools / "tropo-validate.py").write_text(
                "print(%r)\n" % validator_output, encoding="utf-8"
            )
            for name in (
                "test_post_migration_release_clean.py",
                "studio_debt_classes.py",
            ):
                (tests / name).write_text(
                    (HERE / name).read_text(encoding="utf-8"), encoding="utf-8"
                )
            # The gate imports `lib.debt_rule` — the ONE predicate that decides.
            # Without it every run in here died at import and these four tests
            # asserted against a ModuleNotFoundError traceback instead of the
            # gate's report: four red tests that could not have gone green for
            # the right reason, and could not have caught a behaviour change in
            # the thing they exist to pin. (argus-a158, 2026-08-25, found while
            # inverting the gating default — the tests covering that exact
            # behaviour were the ones not running.)
            lib_src = HERE.parent / "lib"
            lib_dst = tools / "lib"
            lib_dst.mkdir(parents=True, exist_ok=True)
            for dep in ("__init__.py", "debt_rule.py"):
                src = lib_src / dep
                if src.exists():
                    (lib_dst / dep).write_text(
                        src.read_text(encoding="utf-8"), encoding="utf-8"
                    )
            (tests / "studio-validator-debt-baseline.json").write_text(
                json.dumps(baseline), encoding="utf-8"
            )
            proc = subprocess.run(
                [sys.executable, str(tests / "test_post_migration_release_clean.py"),
                 *extra_argv],
                capture_output=True, text=True, timeout=120,
            )
            return proc.returncode, proc.stdout + proc.stderr

    def test_it_names_the_class_and_prints_the_lines_that_grew(self) -> None:
        output = (
            "--- UID Cross-References (v1.33) ---\n"
            "[FAIL] one\n"
            "[FAIL] two — the brand new one\n"
            "Summary: 85 passed, 12 failed, 0 warnings, 0 normalizable\n"
        )
        baseline = {"failed": 99, "classes": {"UID Cross-References": 1},
                    "non_gating_classes": []}
        code, text = self._run_gate(output, baseline)
        self.assertEqual(code, 1, text)
        self.assertIn("UID Cross-References: 1 -> 2", text)
        self.assertIn("the brand new one", text)   # THE point of the item
        self.assertIn("1 new finding(s) in gating classes", text)
        self.assertNotIn("Run `python3 vault/tools/tropo-validate.py` to see which",
                         text)

    def test_an_excused_class_reports_but_does_not_gate(self) -> None:
        """Mike's inbox ruling, in code: report it, never block on it."""
        output = (
            "--- Inbox Transition Protocol (v1.68 S2) ---\n"
            "[ERROR] aaaa1111 — HARD inbox violation\n"
            "[ERROR] bbbb2222 — HARD inbox violation\n"
            "Summary: 85 passed, 2 failed, 0 warnings, 0 normalizable\n"
        )
        baseline = {"failed": 99, "classes": {"Inbox Transition Protocol": 0},
                    "non_gating_classes": ["Inbox Transition Protocol"]}
        code, text = self._run_gate(output, baseline)
        self.assertEqual(code, 0, text)
        self.assertIn("Inbox Transition Protocol: 0 -> 2", text)
        self.assertIn("non-gating by recorded decision", text)

    # --- the curated gate list (deb77758 applied to validator classes) --------
    # Both directions, because a one-sided control here proves nothing: a gate
    # that never fires passes the "does not block" half trivially.

    def _curated_output(self, heading: str) -> str:
        return (
            f"--- {heading} ---\n"
            "[ERROR] aaaa1111 — a finding\n"
            "[ERROR] bbbb2222 — a second finding\n"
            "Summary: 85 passed, 2 failed, 0 warnings, 0 normalizable\n"
        )

    def test_a_class_not_on_the_gate_list_reports_and_does_not_stop_the_build(self):
        """The negative half: growth in an untriaged class must not refuse.

        This is the case that stopped a release over 663 bytes in a private
        agent memory file whose sibling records are tagged argo-private and
        which no shipped box has ever contained.
        """
        baseline = {
            "failed": 99,
            "classes": {"Agent-Memory Surface Bound Gate": 0},
            "gating_classes": {"UID Consistency": "identity that cannot be resolved"},
        }
        code, text = self._run_gate(
            self._curated_output("Agent-Memory Surface Bound Gate"), baseline)
        self.assertEqual(code, 0, text)
        self.assertIn("Agent-Memory Surface Bound Gate: 0 -> 2", text)
        # Reported, and named as untriaged — the answer to "nobody would notice".
        self.assertIn("reporting-only", text)

    def test_a_class_on_the_gate_list_still_stops_the_build(self):
        """The positive half: the curated list must actually be able to refuse.

        Without this, the inversion could have silently disabled gating
        altogether and the test above would still be green.
        """
        baseline = {
            "failed": 99,
            "classes": {"UID Consistency": 0},
            "gating_classes": {"UID Consistency": "identity that cannot be resolved"},
        }
        code, text = self._run_gate(self._curated_output("UID Consistency"), baseline)
        self.assertEqual(code, 1, text)
        self.assertIn("UID Consistency: 0 -> 2", text)
        self.assertIn("GATING", text)
        self.assertIn("identity that cannot be resolved", text)

    def test_no_gate_list_preserves_the_previous_behaviour_exactly(self):
        """A studio that has not re-recorded keeps the gate it had.

        The inversion may not become a way for other studios' gates to stop
        working the moment they pull this version.
        """
        baseline = {
            "failed": 99,
            "classes": {"UID Cross-References": 0},
            "non_gating_classes": [],
        }
        code, text = self._run_gate(
            self._curated_output("UID Cross-References"), baseline)
        self.assertEqual(code, 1, text)
        self.assertNotIn("reporting-only", text)

    def test_a_total_that_grows_with_no_gating_class_still_refuses(self) -> None:
        """No passing on a technicality.

        If the total rose and the per-class parse saw nothing gating, either the
        growth is excused or the parse missed a shape — and the second is a
        defect in the gate itself. Either way it says so rather than going green.
        """
        output = "Summary: 85 passed, 400 failed, 0 warnings, 0 normalizable\n"
        baseline = {"failed": 99, "classes": {}, "non_gating_classes": []}
        code, text = self._run_gate(output, baseline)
        self.assertEqual(code, 1, text)
        self.assertIn("with no gating class grown", text)
        # The explanation wraps across lines, so match it whitespace-insensitively
        # rather than pinning the wrap point.
        #
        # This assertion pinned "per-class parse missed a finding shape", which
        # `lib.debt_rule.debt_verdict` has never emitted — it says "an
        # unattributed shape". The wording drifted apart at some point and the
        # test could not report it, because the import crash above meant this
        # line was never reached. Pinned to the predicate's real words now; the
        # assertion's intent (say WHY, don't just go green) is unchanged and the
        # message still carries both halves.
        self.assertIn("or an unattributed shape", " ".join(text.split()))

    def test_a_baseline_with_no_classes_still_gates_on_the_total(self) -> None:
        """The upgrade may not become a new way for the gate to break."""
        output = "Summary: 85 passed, 5 failed, 0 warnings, 0 normalizable\n"
        baseline = {"failed": 99}
        code, text = self._run_gate(output, baseline)
        self.assertEqual(code, 0, text)
        self.assertIn("has no `classes` record", text)
        self.assertIn("PASS — studio debt DOWN 94", text)

    def test_mutation_without_the_itemizer_the_refusal_says_nothing(self) -> None:
        """Teeth: prove the itemized report is what carries the answer.

        Strips the per-class record from the baseline — the same refusal, minus
        the itemization — and asserts the growing finding is NOT named. That is
        the behaviour item 3 was raised to end, reproduced deliberately so the
        first test above cannot pass for an unrelated reason.
        """
        output = (
            "--- UID Cross-References (v1.33) ---\n"
            "[FAIL] two — the brand new one\n"
            "Summary: 85 passed, 400 failed, 0 warnings, 0 normalizable\n"
        )
        code, text = self._run_gate(output, {"failed": 99})
        self.assertEqual(code, 1, text)
        self.assertNotIn("the brand new one", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
