#!/usr/bin/env python3
"""Not-initialized, healthy and aborted are three things, and the gate can tell.

Record: f0152b4c4ef4. Two measured faces of one defect, both reproduced against
the shipped v1.95.0 zip before this suite was written:

  FACE 1, false RED  — a correct un-indexed box printed "ERROR: validator
      subprocess failed (path missing or crash)" and exited 5, swallowing the
      validator's own answer and the one command that fixes it.
  FACE 2, false GREEN — a validator that died mid-run at exit 1 with no Summary
      parsed to all-zero counts and reported "GREEN — substrate healthy", exit 0.
      Reproduced verbatim against HEAD: a PermissionError became a clean bill of
      health.

Face 2 is the worse one and it is the one the build gate could not see at all:
that gate judged `returncode >= 2` and read nothing else, so an exit 0 whose
stdout contained "RED" passed.

WHAT THIS SUITE PROTECTS THAT A COUNT CANNOT. Every assertion below is written so
that removing the mechanism it names turns it red — the controls at the bottom
are the ones that make the rest mean anything. In particular the gate must key on
TEXT, not on the not-initialized exit code: that code is decision 4 on the v1.96
board and is Mike's to settle, and no gate may depend on which way he rules.

talos-t65, 2026-09-08, under argus-a175's direction.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
TROPO_TEST = TOOLS / "tropo-test.py"

_spec = importlib.util.spec_from_file_location(
    "build_guards_under_test", TOOLS / "lib" / "build_guards.py")
assert _spec and _spec.loader
guards = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guards)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


tt = _module(TROPO_TEST, "tropo_test_under_test")


class _Fixture(unittest.TestCase):
    """A minimal Studio whose validator we control."""

    VALIDATOR = ""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="three-outcomes-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.studio = self.tmp / "studio"
        (self.studio / ".tropo").mkdir(parents=True)
        (self.studio / "vault" / "tools").mkdir(parents=True)
        shutil.copy2(TROPO_TEST, self.studio / "vault" / "tools" / "tropo-test.py")
        (self.studio / "vault" / "tools" / "tropo-validate.py").write_text(
            self.VALIDATOR, encoding="utf-8")

    def run_self_test(self, *flags: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.studio / "vault" / "tools" / "tropo-test.py"), *flags],
            cwd=str(self.studio), capture_output=True, text=True, timeout=120)


# ── FACE 1: not initialized ──────────────────────────────────────────────────

NOT_INITIALIZED_VALIDATOR = '''#!/usr/bin/env python3
import sys
print("=" * 70)
print("This Studio has no index yet - nothing is wrong.")
print("=" * 70)
print("    python3 vault/tools/tropo-rebuild-index.py --apply --vault-path .")
sys.exit(2)
'''


class ANotInitialisedStudioSaysSo(_Fixture):
    VALIDATOR = NOT_INITIALIZED_VALIDATOR

    def run_self_test(self, *flags: str) -> subprocess.CompletedProcess:
        """Every test in this class asserts the RENDERING of not-initialized.

        Since Mike's 2026-09-08 ruling a human never sees that rendering — the
        index is built and the question is asked again. The rendering is now the
        --no-auto-init path, and it is emphatically still live: every build gate
        opts out and reads exactly these strings (build_guards keys on
        NOT_INITIALIZED_STATUS to detect it has been aimed at shipped bytes).
        So these assertions still protect a real consumer, just not the human
        one. Auto-init's own behaviour is tested in AutoInitialisation below.
        """
        return super().run_self_test("--no-auto-init", *flags)

    def test_the_status_line_is_present_for_machines(self) -> None:
        """The gate reads THIS, not the exit code. If the line changes, the gate
        must change with it — which is why both name the same constant."""
        r = self.run_self_test("--quick")
        self.assertIn(tt.NOT_INITIALIZED_STATUS, r.stdout)
        self.assertEqual(tt.NOT_INITIALIZED_STATUS, guards._NOT_INITIALIZED_STATUS)

    def test_the_human_is_told_no_verdict_was_produced(self) -> None:
        """Argus's direction verbatim: 'make clear no health verdict has been
        produced'. A stranger must not read this as a clean bill of health."""
        r = self.run_self_test("--quick")
        self.assertIn("NO HEALTH VERDICT HAS BEEN PRODUCED", r.stdout)

    def test_the_one_command_is_printed_verbatim(self) -> None:
        r = self.run_self_test("--quick")
        self.assertIn(tt.NOT_INITIALIZED_CURE, r.stdout)

    def test_it_does_not_claim_the_box_is_defective(self) -> None:
        """'This is a user-facing diagnostic, not a claim that the pristine box
        is defective' — argus-a175. The old text said the validator crashed."""
        r = self.run_self_test("--quick")
        self.assertIn("Nothing is wrong", r.stdout)
        self.assertNotIn("path missing or crash", r.stdout + r.stderr)

    def test_the_exit_code_is_the_declared_one(self) -> None:
        """DECISION 4 lives here and nowhere else. If Mike rules the other way,
        NOT_INITIALIZED_EXIT changes and this test follows it — and nothing in
        build_guards moves, because that gate reads the status line."""
        r = self.run_self_test("--quick")
        self.assertEqual(r.returncode, tt.NOT_INITIALIZED_EXIT)

    def test_json_consumers_get_a_status_field_not_a_verdict(self) -> None:
        r = self.run_self_test("--quick", "--json")
        payload = json.loads(r.stdout)
        self.assertEqual(payload["status"], "not-initialized")
        self.assertFalse(payload["health_verdict_produced"])
        self.assertEqual(payload["cure"], tt.NOT_INITIALIZED_CURE)


# ── FACE 2: aborted ──────────────────────────────────────────────────────────

CRASHING_VALIDATOR = '''#!/usr/bin/env python3
print("--- Some Check ---")
print("[PASS] a few things looked fine")
raise PermissionError(13, "Permission denied", "/an/unreadable/sibling")
'''


class AnAbortedValidatorIsNeverGreen(_Fixture):
    VALIDATOR = CRASHING_VALIDATOR

    def test_it_does_not_report_green(self) -> None:
        """THE REGRESSION. Against HEAD this exact fixture printed 'GREEN -
        substrate healthy' and exited 0, because an uncaught exception exits 1,
        which the wrapper accepted as a verdict, and no Summary parsed to
        all-zero counts."""
        r = self.run_self_test("--quick")
        self.assertNotIn("GREEN", r.stdout)
        self.assertNotEqual(r.returncode, 0)

    def test_it_says_no_verdict_was_produced(self) -> None:
        r = self.run_self_test("--quick")
        self.assertIn("NO HEALTH VERDICT HAS BEEN PRODUCED", r.stderr)

    def test_the_discarded_stderr_is_shown(self) -> None:
        """The traceback was thrown away on this path. It is the only thing that
        tells a reader WHICH crash they have."""
        r = self.run_self_test("--quick")
        self.assertIn("PermissionError", r.stderr)

    def test_it_is_not_confused_with_not_initialized(self) -> None:
        """The record's own done-when: 'a box with a genuinely broken validator
        must not read as the no-index state'. No such control existed before."""
        r = self.run_self_test("--quick")
        self.assertNotIn(tt.NOT_INITIALIZED_STATUS, r.stdout)
        self.assertNotEqual(r.returncode, tt.NOT_INITIALIZED_EXIT)


# ── The unit that decides it ─────────────────────────────────────────────────

class GreenRequiresACompletedCheck(unittest.TestCase):
    def test_no_summary_is_not_a_verdict(self) -> None:
        parsed = tt.parse_validator_output("[PASS] something\nno summary here\n")
        self.assertFalse(parsed["summary_present"])
        self.assertEqual(tt.compute_verdict(parsed), ("aborted", 5))

    def test_a_real_summary_still_computes_normally(self) -> None:
        for body, expected in (
            ("Summary: 10 passed, 0 failed, 0 warnings", ("green", 0)),
            ("Summary: 10 passed, 0 failed, 3 warnings", ("yellow", 1)),
            ("Summary: 10 passed, 2 failed, 0 warnings", ("red", 2)),
        ):
            with self.subTest(body=body):
                self.assertEqual(tt.compute_verdict(tt.parse_validator_output(body)), expected)

    def test_the_empty_output_control_still_holds(self) -> None:
        """sa.cold-boot-182 D0-1: empty stdout must never be GREEN. It was cured
        by the {0,1} guard; it is now ALSO cured one layer down, so removing
        either does not silently reopen it."""
        parsed = tt.parse_validator_output("")
        self.assertFalse(parsed["summary_present"])
        self.assertEqual(tt.compute_verdict(parsed)[0], "aborted")


# ── The gate ─────────────────────────────────────────────────────────────────

class TheGateReadsTheOutputNotOneInteger(unittest.TestCase):
    """Before this cure the gate's entire verdict was `returncode >= 2`."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.box = self.tmp / "box"
        (self.box / "vault" / "tools").mkdir(parents=True)

    def _plant(self, body: str) -> None:
        (self.box / "vault" / "tools" / "tropo-test.py").write_text(
            body, encoding="utf-8")

    def test_a_zero_exit_that_produced_no_verdict_is_refused(self) -> None:
        """THE MEASURED CASE. An exit 0 whose output says it examined nothing
        used to PASS, because only the integer was read."""
        self._plant('#!/usr/bin/env python3\n'
                    'print("NO HEALTH VERDICT HAS BEEN PRODUCED")\n')
        problems, _ = guards.box_self_test_problems(self.box)
        self.assertTrue(problems, "a pass having examined nothing must be refused")
        self.assertIn("NO health verdict", problems[0])

    def test_not_initialized_is_refused_by_its_status_line_not_its_exit_code(self) -> None:
        """Exit 0 deliberately: if Mike rules decision 4 the other way, this is
        exactly what the gate would see, and it must still refuse the shipped
        bytes rather than accept a non-verdict as health."""
        self._plant('#!/usr/bin/env python3\n'
                    f'print("{tt.NOT_INITIALIZED_STATUS}")\n')
        problems, _ = guards.box_self_test_problems(self.box)
        self.assertTrue(problems)
        self.assertIn("NOT INITIALIZED", problems[0])

    def test_a_healthy_box_still_passes(self) -> None:
        self._plant('#!/usr/bin/env python3\n'
                    'print("Validator: 111 passed, 0 failed, 92 warnings")\n'
                    'print("YELLOW")\n')
        problems, _ = guards.box_self_test_problems(self.box)
        self.assertEqual(problems, [])

    def test_red_still_refuses(self) -> None:
        self._plant('#!/usr/bin/env python3\nimport sys\n'
                    'print("Validator: 1 passed, 9 failed, 0 warnings")\n'
                    'sys.exit(2)\n')
        problems, _ = guards.box_self_test_problems(self.box)
        self.assertTrue(problems)
        self.assertIn("FAILED RED", problems[0])

    def test_a_missing_rebuilder_is_named_as_the_customers_problem(self) -> None:
        """The disposable-copy gate cannot initialize a box that cannot derive
        its own index — and neither can the customer, which is what it says."""
        problems, _ = guards.box_self_test_on_initialized_copy(self.box)
        self.assertTrue(problems)
        self.assertIn("tropo-rebuild-index.py not found", problems[0])

    def test_the_artifact_is_never_mutated(self) -> None:
        """'Keep the artifact pristine' — argus-a175. The copy is initialized;
        the box under test is not touched, not even by a failed run."""
        self._plant('#!/usr/bin/env python3\nprint("Validator: 1 passed, 0 failed, 0 warnings")\n')
        before = sorted(p.relative_to(self.box).as_posix()
                        for p in self.box.rglob("*") if p.is_file())
        guards.box_self_test_on_initialized_copy(self.box)
        after = sorted(p.relative_to(self.box).as_posix()
                       for p in self.box.rglob("*") if p.is_file())
        self.assertEqual(before, after)


class TheGateAndTheToolCannotDriftApart(unittest.TestCase):
    """One fact, two readers — the studio's costliest family. The gate greps for
    a string the tool prints; if either moves without the other, the gate goes
    blind and nothing else would say so."""

    def test_the_status_constant_is_identical_on_both_sides(self) -> None:
        self.assertEqual(guards._NOT_INITIALIZED_STATUS, tt.NOT_INITIALIZED_STATUS)

    def test_the_shipped_tool_actually_emits_the_constant(self) -> None:
        """Not 'the constants match' — that would pass with both wrong. This
        asserts the string appears in the tool's own not-initialized branch."""
        source = TROPO_TEST.read_text(encoding="utf-8")
        self.assertIn("print(NOT_INITIALIZED_STATUS)", source)

    def test_the_gate_does_not_test_the_not_initialized_exit_code(self) -> None:
        """DECISION 4 IS MIKE'S AND NO GATE MAY DEPEND ON IT. If a future edit
        reintroduces an exit-code test for this state, his ruling silently
        becomes a gate contract again."""
        source = (TOOLS / "lib" / "build_guards.py").read_text(encoding="utf-8")
        body = source[source.index("def box_self_test_problems"):
                      source.index("def box_self_test_on_initialized_copy")]
        self.assertNotIn("NOT_INITIALIZED_EXIT", body)
        self.assertIn("_NOT_INITIALIZED_STATUS in out", body)




# ── FACE 4: auto-initialisation (Mike-ruled 2026-09-08) ──────────────────────
#
# Decision 4 asked which exit code a stranger should get on a correct-but-unbuilt
# box. Mike dissolved the question: build the index and ask again. What follows
# tests the behaviour that replaced it, INCLUDING the two states that did not
# disappear but moved one layer down — a build that fails, and a build that
# reports success and changes nothing.

#: A validator that answers not-initialized until the index exists, then healthy.
#: The sentinel is the file a real rebuild would produce, so the two runs differ
#: for the same reason they differ in production rather than by a counter.
SWITCHING_VALIDATOR = '''#!/usr/bin/env python3
import sys, pathlib
if pathlib.Path("vault/00-index.jsonl").exists():
    print("Summary: 5 passed, 0 failed, 0 warnings")
    sys.exit(0)
print("=" * 70)
print("This Studio has no index yet - nothing is wrong.")
print("=" * 70)
sys.exit(2)
'''

#: Stands in for tropo-rebuild-index.py. Writes the index the validator looks for
#: and records that it ran, so a test can prove control REACHED the build rather
#: than inferring it from a downstream verdict.
REBUILDER_OK = '''#!/usr/bin/env python3
import pathlib
pathlib.Path("vault").mkdir(exist_ok=True)
pathlib.Path("vault/00-index.jsonl").write_text("{}\\n", encoding="utf-8")
pathlib.Path("REBUILDER-RAN").write_text("yes", encoding="utf-8")
'''

REBUILDER_FAILS = '''#!/usr/bin/env python3
import sys, pathlib
pathlib.Path("REBUILDER-RAN").write_text("yes", encoding="utf-8")
print("could not write the index: disk is a lie", file=sys.stderr)
sys.exit(1)
'''

#: Reports success and produces nothing. The build says it worked; the Studio is
#: still unbuilt. Retrying would loop forever, so this must be reported instead.
REBUILDER_LIES = '''#!/usr/bin/env python3
import pathlib
pathlib.Path("REBUILDER-RAN").write_text("yes", encoding="utf-8")
'''


class AutoInitialisation(_Fixture):
    VALIDATOR = SWITCHING_VALIDATOR
    REBUILDER = REBUILDER_OK

    def setUp(self) -> None:
        super().setUp()
        rb = self.studio / "vault" / "tools" / "tropo-rebuild-index.py"
        rb.write_text(self.REBUILDER, encoding="utf-8")

    def rebuilder_ran(self) -> bool:
        return (self.studio / "REBUILDER-RAN").exists()

    def test_the_build_actually_runs(self) -> None:
        """Control must REACH the branch. A verdict alone cannot prove that:
        a validator that returned healthy without the build ever firing would
        produce an identical exit code and an identical stdout."""
        self.run_self_test()
        self.assertTrue(self.rebuilder_ran(),
                        "auto-init reported a verdict without running the build")

    def test_the_stranger_gets_a_real_verdict_not_a_diagnostic(self) -> None:
        r = self.run_self_test()
        self.assertNotIn(tt.NOT_INITIALIZED_STATUS, r.stdout)
        self.assertIn("GREEN", r.stdout)
        self.assertEqual(r.returncode, 0)

    def test_no_auto_init_does_not_build(self) -> None:
        """The negative control. Without it the suite cannot tell 'auto-init
        works' from 'the fixture was initialised all along'."""
        r = self.run_self_test("--no-auto-init")
        self.assertFalse(self.rebuilder_ran())
        self.assertIn(tt.NOT_INITIALIZED_STATUS, r.stdout)
        self.assertEqual(r.returncode, tt.NOT_INITIALIZED_EXIT)

    def test_progress_goes_to_stderr_so_json_stays_parseable(self) -> None:
        """`npm test --json` feeds CI. Progress chatter on stdout would make the
        payload unparseable exactly when a machine is reading it."""
        r = self.run_self_test("--json")
        json.loads(r.stdout)
        self.assertIn("Building it now", r.stderr)


class AutoInitialisationThatFails(AutoInitialisation):
    REBUILDER = REBUILDER_FAILS

    def test_it_is_loud_and_non_zero(self) -> None:
        """Comparing the tool's exit against the tool's own constant is
        self-referential — set the constant to 0 and that assertion stays green
        while `npm test` reports success for a Studio whose index would not
        build. Measured in adversarial review. So: assert NON-ZERO independently,
        and assert the constant does not collide with a code that already means
        something else."""
        r = self.run_self_test()
        self.assertNotEqual(r.returncode, 0,
                            "an initialization failure must never exit 0")
        self.assertEqual(r.returncode, tt.AUTO_INIT_FAILED_EXIT)
        self.assertIn(tt.AUTO_INIT_FAILED_STATUS, r.stderr)

    def test_the_failure_code_does_not_collide_with_another_meaning(self) -> None:
        """6 is the argparse/CLI-usage code — which itself exists because
        argparse's default of 2 collided with substrate-RED. Shipping 6 here
        would have made `--bogus-flag` and "your index would not build" the same
        integer, rebuilding that collision one layer up."""
        usage = self.run_self_test("--definitely-not-a-flag")
        self.assertNotEqual(
            tt.AUTO_INIT_FAILED_EXIT, usage.returncode,
            "initialization-failed shares an exit code with CLI usage error")
        for taken in (0, 1, 2, 3, 4, 5):
            self.assertNotEqual(tt.AUTO_INIT_FAILED_EXIT, taken)

    def test_it_claims_no_health_verdict(self) -> None:
        r = self.run_self_test()
        self.assertIn("NO HEALTH VERDICT HAS BEEN PRODUCED", r.stderr)

    def test_it_shows_the_build_error_and_names_the_command(self) -> None:
        """The half that was missing from the original crash report: the human
        is told what broke AND what to type."""
        r = self.run_self_test()
        self.assertIn("disk is a lie", r.stderr)
        self.assertIn(tt.AUTO_INIT_COMMAND_DISPLAY, r.stderr)

    def test_the_command_offered_is_the_one_that_actually_ran(self) -> None:
        """"Run it by hand to see the full error" must name the command that
        FAILED. The executed argv and the printed cure differ by --no-genesis,
        so offering the cure here would hand the human a command that may not
        reproduce the failure and that mints the identity this tool just
        declined to mint — unwarned, and after the tool went to trouble to
        avoid it."""
        r = self.run_self_test()
        self.assertIn("--no-genesis", r.stderr,
                      "the failure message offers a command other than the one "
                      "that ran, and that command mints Studio identity")
        self.assertEqual(
            tt.AUTO_INIT_COMMAND_DISPLAY.split(),
            ["python3"] + tt.AUTO_INIT_ARGV[1:],
            "the displayed command has drifted from the executed argv")

    def test_json_consumers_see_the_failure_as_its_own_status(self) -> None:
        payload = json.loads(self.run_self_test("--json").stdout)
        self.assertEqual(payload["status"], "initialization-failed")
        self.assertFalse(payload["health_verdict_produced"])

    # inherited cases that describe the succeeding rebuilder
    test_the_stranger_gets_a_real_verdict_not_a_diagnostic = None
    test_progress_goes_to_stderr_so_json_stays_parseable = None


#: Writes SOME rows, then dies. The shape that made the next run report GREEN.
REBUILDER_PARTIAL = """#!/usr/bin/env python3
import sys, pathlib
pathlib.Path("vault").mkdir(exist_ok=True)
pathlib.Path("vault/00-index.jsonl").write_text('{"partial":true}\\n')
pathlib.Path("REBUILDER-RAN").write_text("yes", encoding="utf-8")
print("REFUSED: index shrink floor violated", file=sys.stderr)
sys.exit(1)
"""


class AFailedBuildLeavesNothingTheNextRunCanMisread(AutoInitialisation):
    """THE FALSE GREEN. Found in adversarial review and reproduced by hand.

    A build that writes rows and then dies leaves a partial index. The validator
    asks "is there an index", not "is it whole", so the NEXT run skipped
    auto-init entirely and printed GREEN — substrate healthy, having repaired
    nothing. Before auto-init existed this state could not arise unattended: a
    human ran the build and watched it fail.
    """

    REBUILDER = REBUILDER_PARTIAL

    def test_the_second_run_does_not_report_green(self) -> None:
        first = self.run_self_test()
        self.assertNotEqual(first.returncode, 0)
        second = self.run_self_test()
        self.assertNotIn("GREEN", second.stdout,
                         "a partial index from a failed build was read as a "
                         "healthy Studio on the next run")
        self.assertNotEqual(second.returncode, 0)

    def test_the_partial_output_is_removed_and_said_out_loud(self) -> None:
        r = self.run_self_test()
        self.assertFalse((self.studio / "vault" / "00-index.jsonl").exists(),
                         "partial index left on disk after a failed build")
        self.assertIn("Partial output removed", r.stderr)

    def test_an_index_that_was_already_there_is_never_deleted(self) -> None:
        """Only files THIS build created may be removed. A pre-existing artifact
        is the user's and is not ours to delete."""
        idx = self.studio / "vault" / "00-index.jsonl"
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text("PRE-EXISTING\n", encoding="utf-8")
        self.run_self_test()
        self.assertTrue(idx.exists(), "deleted an index we did not create")
        self.assertEqual(idx.read_text(encoding="utf-8"), "PRE-EXISTING\n")

    def test_the_build_failure_reason_reaches_the_human(self) -> None:
        r = self.run_self_test()
        self.assertIn("shrink floor", r.stderr)

    test_the_stranger_gets_a_real_verdict_not_a_diagnostic = None
    test_progress_goes_to_stderr_so_json_stays_parseable = None


#: Explains itself on STDOUT and says nothing on stderr. Every other failing
#: fixture in this file writes to stderr — including the partial-index one, which
#: adopted the finding's exact wording but kept it on the stream the code already
#: handled. So the branch that prints the build's stdout was exercised by nothing
#: and could be deleted with the whole suite staying green. Measured.
REBUILDER_FAILS_ON_STDOUT = """#!/usr/bin/env python3
import sys, pathlib
pathlib.Path("REBUILDER-RAN").write_text("yes", encoding="utf-8")
print("REFUSED: index shrink floor violated (this went to stdout)")
sys.exit(1)
"""


class AFailureExplainedOnStdoutStillReachesTheHuman(AutoInitialisation):
    """A rebuilder is free to explain itself on either stream. The human must be
    told WHAT broke either way — being told only that something failed is the
    half of the original crash report this whole record exists to fix."""

    REBUILDER = REBUILDER_FAILS_ON_STDOUT

    def test_the_reason_is_shown_even_when_it_arrives_on_stdout(self) -> None:
        r = self.run_self_test()
        self.assertEqual(r.returncode, tt.AUTO_INIT_FAILED_EXIT)
        self.assertIn("shrink floor", r.stderr,
                      "the build explained itself on stdout and the tool threw "
                      "the reason away")

    test_the_stranger_gets_a_real_verdict_not_a_diagnostic = None
    test_progress_goes_to_stderr_so_json_stays_parseable = None


class AutoInitialisationThatSilentlyDoesNothing(AutoInitialisation):
    """The build exits 0 and produces no index. Retrying is an infinite loop, so
    this is reported as a failure rather than retried — the state that MOVED
    rather than disappeared."""

    REBUILDER = REBUILDER_LIES

    def test_it_does_not_loop_and_reports_the_failure(self) -> None:
        r = self.run_self_test()
        self.assertEqual(r.returncode, tt.AUTO_INIT_FAILED_EXIT)
        self.assertIn(tt.AUTO_INIT_FAILED_STATUS, r.stderr)
        self.assertIn("still has no index", r.stderr)

    test_the_stranger_gets_a_real_verdict_not_a_diagnostic = None
    test_progress_goes_to_stderr_so_json_stays_parseable = None


class EveryGateOptsOutOfAutoInit(unittest.TestCase):
    """The coupling that would silently corrupt a release artifact.

    tropo-test.py now writes an index when the validator says there is none. A
    build gate that took that path would write it INTO the box it is sealing,
    and the same extracted_tree is read by build-no-studio-identity, which flips
    PASS -> REFUSED as soon as a genesis artifact appears. It would also destroy
    box_self_test_problems' own wrong-box detection, whose entire mechanism is
    seeing NOT INITIALIZED come back from shipped bytes.

    Argus A175 on the record (f0152b4c4ef4): "Do not silently initialize a
    customer's live Studio as a diagnostic side effect."

    ONE CHECK, NOT TWO. This class briefly had a companion asserting
    `"--no-auto-init" in source`. Mutation-proving killed it: removing the flag
    from the actual invocation left that assertion GREEN, because the comment
    block above the invocation contains the same string. It was a guard that
    could not change verdict, sitting next to one that could, which is worse
    than no guard — it makes the pair look doubly protected. Deleted rather than
    repaired: two checks for one defect means a mutation to either survives.
    """

    def _guards_source(self) -> str:
        here = Path(__file__).resolve()
        return (here.parents[1] / "lib" / "build_guards.py").read_text(encoding="utf-8")

    def test_no_gate_invocation_of_tropo_test_omits_the_opt_out(self) -> None:
        """AST, not a line-grep. The line version was measured failing BOTH ways
        in adversarial review: a genuine second call site through a differently
        named variable stayed green, and merely reformatting the correct call so
        the flag wrapped to line two went red. A check that misses the defect it
        names and fires on whitespace is worse than none.

        This walks every argv list literal in the module and asserts that any
        list launching the shipped self-test carries the opt-out — however the
        path is spelled, and across as many lines as it likes.
        """
        import ast as _ast

        tree = _ast.parse(self._guards_source())

        # ALIASES, to a fixpoint. Keying on the literal name `box_test` was
        # measured insufficient: `other = box_test` then launching `other`
        # sailed straight through, which is the precise case this guard's
        # docstring claims to prevent. Seed with anything bound to a path that
        # names the shipped self-test, then propagate through assignments until
        # nothing new appears.
        aliases = {"box_test"}
        for _ in range(10):
            grew = False
            for node in _ast.walk(tree):
                if not isinstance(node, _ast.Assign):
                    continue
                refs = {n.id for n in _ast.walk(node.value)
                        if isinstance(n, _ast.Name)}
                lits = [c.value for c in _ast.walk(node.value)
                        if isinstance(c, _ast.Constant)
                        and isinstance(c.value, str)]
                if refs & aliases or any("tropo-test.py" in l for l in lits):
                    for tgt in node.targets:
                        for n in _ast.walk(tgt):
                            if isinstance(n, _ast.Name) and n.id not in aliases:
                                aliases.add(n.id)
                                grew = True
            if not grew:
                break

        launches = []
        for node in _ast.walk(tree):
            # Only real subprocess launches. An earlier version walked EVERY
            # list literal and flagged an error MESSAGE containing the filename
            # — a false red, which is the same defect as a false green wearing
            # the other hat.
            if not isinstance(node, _ast.Call):
                continue
            fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if fname not in ("_run", "run", "check_output", "Popen"):
                continue
            if not node.args or not isinstance(node.args[0], (_ast.List, _ast.Tuple)):
                continue
            literals, names = [], []
            for el in node.args[0].elts:
                for sub in _ast.walk(el):
                    if isinstance(sub, _ast.Name):
                        names.append(sub.id)
                    elif isinstance(sub, _ast.Constant) and isinstance(sub.value, str):
                        literals.append(sub.value)
            if (any("tropo-test.py" in lit for lit in literals)
                    or aliases & set(names)):
                launches.append((literals, node.lineno))

        self.assertTrue(launches,
                        "no invocation of the shipped self-test found in "
                        "build_guards — has it moved? this guard is now blind")
        for literals, lineno in launches:
            self.assertIn(
                "--no-auto-init", literals,
                "build_guards.py:%d launches the shipped self-test without "
                "--no-auto-init; a gate run would write an index into the box "
                "it is sealing" % lineno)


class TheBuildRunsOnceAndInTheStudioRoot(_Fixture):
    """Two invariants the first version of this suite asserted nowhere: that
    auto-init does not retry, and that the build is anchored to the Studio root
    rather than to wherever the human happened to be standing."""

    VALIDATOR = SWITCHING_VALIDATOR
    REBUILDER = """#!/usr/bin/env python3\nimport pathlib\nc = pathlib.Path("BUILD-COUNT")\nc.write_text(str(int(c.read_text()) + 1) if c.exists() else "1")\npathlib.Path("vault").mkdir(exist_ok=True)\n"""

    def setUp(self) -> None:
        super().setUp()
        (self.studio / "vault" / "tools" / "tropo-rebuild-index.py").write_text(
            self.REBUILDER, encoding="utf-8")

    def test_the_build_is_attempted_exactly_once(self) -> None:
        """This rebuilder exits 0 and never creates the index, so the validator
        keeps answering not-initialized. A retry loop — even a bounded one —
        shows up here as a count above 1."""
        self.run_self_test()
        count = (self.studio / "BUILD-COUNT").read_text(encoding="utf-8").strip()
        self.assertEqual(count, "1",
                         "auto-init retried; it must ask once and report")

    def test_the_build_runs_in_the_studio_root_not_the_callers_cwd(self) -> None:
        """AUTO_INIT_ARGV carries a RELATIVE script path and `--vault-path .`,
        so cwd=studio_root in build_index is load-bearing. Deleting it kept the
        whole suite green, because every other fixture already stands in the
        Studio root."""
        sub = self.studio / "some" / "deep" / "subdir"
        sub.mkdir(parents=True)
        subprocess.run(
            [sys.executable,
             str(self.studio / "vault" / "tools" / "tropo-test.py")],
            cwd=str(sub), capture_output=True, text=True, timeout=120)
        self.assertTrue((self.studio / "BUILD-COUNT").exists(),
                        "the build did not run in the Studio root when invoked "
                        "from a subdirectory")
        self.assertFalse((sub / "BUILD-COUNT").exists(),
                         "the build ran in the caller's cwd instead of the "
                         "Studio root")


class OneSourceForTheCommand(unittest.TestCase):
    def test_the_auto_init_command_is_the_printed_cure(self) -> None:
        """The command we RUN and the command we would have TOLD the human to run
        are one string. Two copies is the studio's dominant defect family, and
        this is the assertion that keeps them from becoming two."""
        self.assertEqual(tt.AUTO_INIT_ARGV[0], sys.executable)
        # Derived from the cure, plus exactly one documented flag. Asserting the
        # delta by name is the point: a second flag appearing here silently would
        # mean the automated path and the printed command had drifted apart
        # again, which is the whole thing this constant exists to prevent.
        self.assertEqual(tt.AUTO_INIT_ARGV[1:-1], tt.NOT_INITIALIZED_CURE.split()[1:])
        self.assertEqual(tt.AUTO_INIT_ARGV[-1], "--no-genesis")

    def test_the_automated_path_does_not_mint_studio_identity(self) -> None:
        """The health check must not become the thing that gives a Studio its
        identity. Measured before this flag existed: a 1,184-byte
        .tropo/studio-identity.md appeared in a real box purely from running
        `npm test`. The boot contract routes an identity-less Studio to Po."""
        self.assertIn("--no-genesis", tt.AUTO_INIT_ARGV)


if __name__ == "__main__":
    unittest.main(verbosity=2)
