#!/usr/bin/env python3
"""AC1-AC4 of 05de711d — the release runner actually executes, resumes,
gates the outward act, and hands the operator a runnable command at every
halt.

Rewritten from the spec and the implementation's own behaviour, not from
the suite this replaces. That suite passed 70/70 while five independent
verification passes found 18+ real defects underneath it — the point named
explicitly in the handoff: a green suite you wrote yourself is evidence
about the suite, not about the runner, until something that was not trying
to agree with you has tried to break it. The specific vacuity patterns
those passes found (a fixture too small to reach the boundary it was meant
to prove; an adapter test that only exercises its own injected lambda; an
assertion on a channel the code doesn't read back; a status check that
does not say *which* halt) are the shapes this file is built to not repeat.

Two kinds of test live here, deliberately kept apart:

  * LOGIC gets fixtures — small, hand-built profiles and run states, one
    dimension changed at a time, because the claim under test is about the
    runner's own control flow and a fixture can isolate exactly that.
  * GATES get real artifacts — the orchestrator precondition, and the
    plan/run walkability checks, are tested against actual copies of the
    real release runs and release plans on disk (the abandoned run
    `d9025a97`, the shipped run `cd68bea8`, the superseded run `42261546`,
    and the two real cancelled plans `9873ff78`/`088e21aa` whose `status:`
    line sits past the historical 60-line scan window). A gate is a claim
    about the world; the world we actually have is the only fixture that
    can't be built too small to reach its own boundary.

Every real adapted step is checked for signature compatibility against the
actual shipped callable via `inspect.signature` — not a docstring grep, not
membership in a dict — and where a real tool is safe to invoke read-only
(the harness receipt on a bogus activation, the freeze tool against a run
with no recorded candidate) the adapter is exercised against that real
tool, not a stand-in of the adapter's own devising.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location(
    "release_run_under_test", TOOLS / "tropo-release-run.py")
runner = importlib.util.module_from_spec(_spec)
sys.modules["release_run_under_test"] = runner
_spec.loader.exec_module(runner)

#: Captured BEFORE any substitution, so the guard below cannot be fooled by the
#: substitution itself.
_REAL_RUNTIME_DRIVER = runner.RUNTIME_DRIVER

# Fixture runs have no pipeline runtime to drive: their activations are not real
# and the runtime would refuse. Production always drives; the two tests in
# TheWalkRecordsItselfWithTheRuntime keep that substitution honest.
runner.RUNTIME_DRIVER = lambda *a, **k: None


class AdaptersMatchTheRealCallablesTheyAdapt(unittest.TestCase):
    def test_capture_baseline_adapter_call_binds_the_real_signature(self):
        import importlib.util as ilu
        spec = ilu.spec_from_file_location(
            "cap_base_probe", TOOLS / "tropo-release-validation-gate.py")
        module = ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        sig = inspect.signature(module.capture_baseline)
        # _adapt_capture_baseline calls fn(ctx.activation_uid) — one bare
        # positional argument, no keywords.
        sig.bind("deadbeef")

    def test_compare_current_adapter_call_binds_the_real_signature(self):
        import importlib.util as ilu
        spec = ilu.spec_from_file_location(
            "compare_current_probe", TOOLS / "tropo-release-validation-gate.py")
        module = ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        sig = inspect.signature(module.compare_current)
        sig.bind("deadbeef")

    def test_harness_receipt_adapter_call_binds_the_real_signature(self):
        import importlib.util as ilu
        spec = ilu.spec_from_file_location(
            "harness_receipt_probe", TOOLS / "tropo-check-harness-receipt.py")
        module = ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        sig = inspect.signature(module.main)
        # _adapt_harness_receipt calls fn(["--activation-uid", ctx.activation_uid])
        sig.bind(["--activation-uid", "deadbeef"])

    def test_freeze_candidate_main_accepts_the_adapters_argv_shape(self):
        import importlib.util as ilu
        spec = ilu.spec_from_file_location(
            "freeze_probe", TOOLS / "tropo-freeze-release-candidate.py")
        module = ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        sig = inspect.signature(module.main)
        sig.bind(["--run-dir", "x", "--candidate", "y", "--emit"])

    def test_build_release_main_takes_no_argv_parameter(self):
        """The build step's main() parses sys.argv itself — the ONLY reason
        _adapt_build_release mutates sys.argv globally rather than calling
        fn(argv). If main() ever grows an argv parameter, the adapter is
        silently wrong in the other direction (an argument nobody reads)."""
        import importlib.util as ilu
        spec = ilu.spec_from_file_location(
            "build_release_probe", TOOLS / "tropo-build-release.py")
        module = ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        sig = inspect.signature(module.main)
        self.assertEqual(list(sig.parameters), [])


# ===========================================================================
# Adapters exercised against real, safe-to-call tools where possible — never
# a stand-in of the adapter's own invention.
# ===========================================================================

class AdaptersCallRealTools(unittest.TestCase):
    def test_the_build_is_given_the_activation_it_cannot_proceed_without(self):
        """The live defect talos-t52 disclosed rather than shipping red.

        `stage6_package_authority` refuses a package it cannot attribute, in its
        own words: "Deliberately no fallback. There is no 'if we cannot resolve
        a run, carry on' branch ... a gate a caller can decline is not a gate."
        The adapter sent only --target, so the activation was None and a
        runner-driven walk could not get through the build step at all.

        This asserts the argv the adapter BUILDS, because that is the real
        interface: the flag is parsed by hand from sys.argv and does not appear
        in the tool's --help, which nearly caused the report to be dismissed.
        """
        import sys as _sys
        seen = {}

        def recorder(*a, **k):
            seen["argv"] = list(_sys.argv)
            return 0
        ctx = _ctx(STUDIO_ROOT, STUDIO_ROOT, activation_uid="713a1b4e")
        ctx = ctx.__class__(**{**ctx.__dict__, "version": "9.9.9"}) \
            if hasattr(ctx, "__dict__") else ctx
        saved = _sys.argv
        try:
            runner._adapt_build_release(recorder, ctx)
        finally:
            _sys.argv = saved
        self.assertIn("--activation-uid", seen["argv"])
        self.assertIn("713a1b4e", seen["argv"],
                      "the build cannot attribute the package it is asked to make")

    def test_harness_receipt_adapter_reports_the_real_tools_refusal(self):
        """No fixture at all: the real tropo-check-harness-receipt.py, given
        an activation uid that resolves to nothing, refuses read-only. The
        adapter must turn that refusal into a failure the walk can see."""
        import importlib.util as ilu
        spec = ilu.spec_from_file_location(
            "harness_receipt_real", TOOLS / "tropo-check-harness-receipt.py")
        module = ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        ctx = _ctx(STUDIO_ROOT, STUDIO_ROOT, activation_uid="ffffffff")
        failure = runner._adapt_harness_receipt(module.main, ctx)
        self.assertIsNotNone(failure)
        self.assertIn("exit code", failure)

    def test_freeze_adapter_refusal_never_writes_to_the_journal(self):
        """D-3's regression, against the REAL tool: a run with no recorded
        candidate cannot pass, and the journal it started with must come
        back byte-identical — no forged package_frozen, no partial write."""
        import importlib.util as ilu
        spec = ilu.spec_from_file_location(
            "freeze_real_1", TOOLS / "tropo-freeze-release-candidate.py")
        module = ilu.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            _write_journal(run_dir, {"event": "run_created", "data": {"pipeline_run_uid": "aaaaaaaa"}})
            before = (run_dir / "run.jsonl").read_text(encoding="utf-8")
            candidate = Path(tmp) / "candidate.zip"
            candidate.write_bytes(b"not a real package")
            ctx = _ctx(tmp, run_dir, candidate=candidate)

            failure = runner._adapt_freeze_candidate(module.main, ctx)

            self.assertIsNotNone(failure)
            after = (run_dir / "run.jsonl").read_text(encoding="utf-8")
            self.assertEqual(before, after)
            self.assertNotIn("package_frozen", after)

    def test_freeze_adapter_calls_the_emitting_half_not_the_pure_half(self):
        """D-3, direct: with a genuinely earned freeze (a matching candidate
        hash and the four required instrument receipts, in the exact
        `release-verification-receipt` shape `resolve_receipt_set` actually
        requires — verified empirically against the real tool, not guessed),
        --emit must actually land tropo.release.package_frozen in the
        journal. Calling `decide` instead of `main(..., --emit)` — the exact
        original defect — would leave this green with a payload but no
        journal write; this asserts the write, not the payload, so binding
        the pure half again cannot pass silently."""
        import hashlib
        import importlib.util as ilu
        spec = ilu.spec_from_file_location(
            "freeze_real_2", TOOLS / "tropo-freeze-release-candidate.py")
        module = ilu.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            candidate = Path(tmp) / "candidate.zip"
            candidate.write_bytes(b"the built package bytes")
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            run_uid = "aaaaaaaa"

            rows = [
                {"event": "run_created", "data": {"saga_id": "release:aaaaaaaa",
                                                    "pipeline_run_uid": run_uid}},
                {"event": "tropo.release.candidate_built",
                 "data": {"candidate_sha256": digest, "release_run_uid": run_uid}},
            ]
            for instrument in ("full-validator", "release-harness", "external-test", "cold-walk"):
                rows.append({
                    "event": "release-verification-receipt",
                    "data": {
                        "receipt_kind": "release-verification-receipt",
                        "instrument": instrument,
                        "release_run_uid": run_uid,
                        "candidate_sha256": digest,
                        "verdict": "pass",
                        "executor_or_attester": "test",
                        "execution_mode": "machine",
                        "evidence_ref": "x",
                        "started_at": "2026-01-01T00:00:00Z",
                        "completed_at": "2026-01-01T00:00:01Z",
                    },
                })
            _write_journal(run_dir, *rows)
            ctx = _ctx(tmp, run_dir, candidate=candidate)

            failure = runner._adapt_freeze_candidate(module.main, ctx)

            after = (run_dir / "run.jsonl").read_text(encoding="utf-8")
            self.assertIsNone(failure)
            self.assertIn("tropo.release.package_frozen", after,
                          "the earned freeze was not recorded — got failure=%r, "
                          "journal=%r" % (failure, after))


# ===========================================================================
# AC1's D-2 finding: a return value must be interpreted, never discarded.
# ===========================================================================

class ReturnValueGovernsSuccess(unittest.TestCase):
    def test_a_verdict_fail_dict_from_a_shaped_stand_in_fails_the_walk(self):
        """The stand-in matches the real capture_baseline/compare_current
        shape (one positional activation_uid arg) rather than an arbitrary
        lambda, so this exercises the same call shape the real adapter uses
        without touching the live Studio's ROOT."""
        with tempfile.TemporaryDirectory() as tmp:
            _write_tool_module(Path(tmp), "stand_in.py", (
                "def capture_baseline(activation_uid):\n"
                "    return {'verdict': 'fail', 'regressions': ['x']}\n"
            ))
            prof = _profile(_slot("build-the-artifact",
                                   _tool("f9365ede", "stand_in.py:capture_baseline")))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=True,
                                    context=_ctx(tmp, tmp))
            self.assertEqual(outcome.status, "failed")
            self.assertEqual(outcome.failed_at.step_uid, "f9365ede")
            self.assertIn("fail", outcome.failed_at.error)

    def test_the_real_harness_receipt_nonzero_exit_fails_the_walk(self):
        prof = _profile(_slot("verify-the-artifact",
                               _tool("a0f2bea8", "tropo-check-harness-receipt.py:main")))
        outcome = runner.walk(prof, base_dir=TOOLS, execute=True,
                                context=_ctx(STUDIO_ROOT, STUDIO_ROOT, activation_uid="ffffffff"))
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.failed_at.step_uid, "a0f2bea8")

    def test_a_two_tuple_with_an_empty_refusal_does_not_fail(self):
        """decide()-shaped (payload, refusal): an empty-string refusal is
        the pass shape, and must not be mistaken for a truthy failure."""
        with tempfile.TemporaryDirectory() as tmp:
            _write_tool_module(Path(tmp), "decide_ok.py", (
                "def decide(run_dir, candidate):\n"
                "    return ({'verdict': 'pass'}, None)\n"
            ))
            prof = _profile(_slot("verify-the-artifact",
                                   _tool("7de2c49f", "decide_ok.py:decide")))
            with self.assertRaises(ValueError):
                # The real adapter requires ctx.candidate; this proves the
                # two-tuple path is reached via the adapter, not bypassed.
                runner._adapt_freeze_candidate(
                    lambda argv: ({"verdict": "pass"}, None), _ctx(tmp, tmp))

    def test_a_bool_result_never_fails(self):
        """bool is an int subclass in Python; _exit_code_failure must check
        bool BEFORE int, or False (== 0) would read as a failing exit code."""
        self.assertIsNone(runner._exit_code_failure(False))
        self.assertIsNone(runner._exit_code_failure(True))

    def test_a_dict_with_no_verdict_key_falls_through_to_exit_code_check(self):
        self.assertIsNone(runner._verdict_failure({"other": "field"}, "x"))


# ===========================================================================
# AC1: unadapted steps and bare commands.
# ===========================================================================

class UnadaptedStepsFallBackToABareCall(unittest.TestCase):
    def test_a_step_with_no_adapter_is_called_with_no_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "called.json"
            _write_tool_module(Path(tmp), "plain.py", (
                "from pathlib import Path\n"
                "def go():\n"
                f"    Path({str(marker)!r}).write_text('yes')\n"
                "    return 0\n"
            ))
            prof = _profile(_slot("build-the-artifact", _tool("zzzzzzzz", "plain.py:go")))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=True)
            self.assertTrue(marker.is_file())
            self.assertTrue(outcome.actions[0].invoked)

    def test_a_bare_command_string_runs_as_a_subprocess_from_the_vault_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "ran.txt"
            prof = _profile(_slot(
                "build-the-artifact",
                _tool("zzzzzzzz", "echo hi > %s" % marker.name)))
            outcome = runner.walk(prof, execute=True, context=_ctx(tmp, tmp))
            self.assertTrue(outcome.actions[0].invoked)
            self.assertTrue(marker.is_file())

    def test_a_bare_command_entry_is_never_run_without_a_context(self):
        """D-6's second half: a bare-command entry is only ever shelled out
        when a context is present. execute=True with context=None must not
        invoke it — this is the cold-execute contract, not an oversight."""
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "should_not_exist.txt"
            prof = _profile(_slot("build-the-artifact", _tool("zzzzzzzz", "touch %s" % marker)))
            outcome = runner.walk(prof, execute=True, context=None)
            self.assertFalse(outcome.actions[0].invoked)
            self.assertFalse(marker.exists())

    def test_a_bare_command_step_also_records_start_and_completion_with_the_runtime(self):
        """Argus A160's disclosed gap (flagged as my call whether it belongs
        in the contract tests): the callable path records step-start/
        step-complete via `drive`; the bare-command path historically did
        not, so a step could run, report success, and leave the runtime
        never marking it complete — invisible to a green suite because
        nothing downstream depends on it within one walk. Both paths now
        call the same `_record_step` helper (single source, so they cannot
        drift apart again); this pins that the bare-command path is one of
        the two callers, not just the callable one already covered by
        TheWalkRecordsItselfWithTheRuntime."""
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "ran.txt"
            calls = []
            prof = _profile(_slot(
                "build-the-artifact",
                _tool("zzzzzzzz", "echo hi > %s" % marker.name)))
            outcome = runner.walk(
                prof, execute=True, context=_ctx(tmp, tmp),
                drive=lambda c, sub, uid, extra=None: calls.append((sub, uid)))
            self.assertTrue(outcome.actions[0].invoked)
            self.assertIn(("step-start", "zzzzzzzz"), calls)
            self.assertIn(("step-complete", "zzzzzzzz"), calls)

    def test_a_bare_command_step_that_cannot_be_recorded_is_not_reported_as_invoked(self):
        """The bare-command mirror of TheWalkRecordsItselfWithTheRuntime's
        callable-path test: a step that ran but could not be recorded with
        the runtime is not success — the next step would never become
        eligible and resume would re-run it forever."""
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "ran.txt"
            prof = _profile(_slot(
                "build-the-artifact",
                _tool("zzzzzzzz", "echo hi > %s" % marker.name)))
            outcome = runner.walk(
                prof, execute=True, context=_ctx(tmp, tmp),
                drive=lambda c, sub, uid, extra=None:
                ("runtime refused" if sub == "step-complete" else None))
            self.assertTrue(marker.is_file(), "the command still ran")
            self.assertFalse(outcome.actions[0].invoked)
            self.assertIn("could not be recorded", outcome.actions[0].error)

    def test_the_release_history_step_is_given_the_arguments_its_real_script_requires(self):
        """COMMAND_ARGS is the bare-command sibling of ADAPTERS, added when
        argus-a160 drove the first walk that ever reached step 2e9b1db7 (it
        had been unreachable behind a profile step-order defect). Same
        real-signature-compatibility bar as every ADAPTERS entry: every flag
        _args_release_history constructs must be one the real script's own
        --help recognizes."""
        real_script = (STUDIO_ROOT / ".tropo" / "scripts" / "dev-pipeline"
                        / "update-subsystem-canonical-docs.py")
        help_text = _help_text(real_script)
        recognized = _recognized_flags(help_text)
        ctx = _ctx(STUDIO_ROOT, STUDIO_ROOT, release_plan_uid="planuid01")
        ctx = runner.RunContext(**{**ctx.__dict__, "release_entry_uid": "entryuid1"})
        args = runner._args_release_history(ctx)
        flags = [a for a in args if a.startswith("--")]
        for flag in flags:
            self.assertIn(flag, recognized,
                          "%s is not recognized by the real script's --help" % flag)
        self.assertIn("entryuid1", args)

    def test_the_release_history_step_raises_without_a_release_entry_uid(self):
        ctx = _ctx(STUDIO_ROOT, STUDIO_ROOT, release_plan_uid="planuid01")
        with self.assertRaises(ValueError):
            runner._args_release_history(ctx)


# ===========================================================================
# AC1: raising steps stop the walk as failed, never reported invoked.
# ===========================================================================

class ARaisingStepStopsTheWalk(unittest.TestCase):
    def test_a_raising_step_is_never_reported_invoked(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_tool_module(Path(tmp), "boom.py", (
                "def go():\n"
                "    raise RuntimeError('kaboom')\n"
            ))
            prof = _profile(_slot("build-the-artifact", _tool("zzzzzzzz", "boom.py:go")))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=True)
            self.assertEqual(outcome.status, "failed")
            self.assertFalse(outcome.failed_at.invoked)
            self.assertIn("RuntimeError", outcome.failed_at.error)

    def test_missing_version_raises_and_is_reported_failed_not_silently_skipped(self):
        prof = _profile(_slot("build-the-artifact",
                               _tool("8654900a", "tropo-build-release.py:main")))
        outcome = runner.walk(prof, base_dir=TOOLS, execute=True,
                                context=_ctx(STUDIO_ROOT, STUDIO_ROOT, version=None))
        self.assertEqual(outcome.status, "failed")
        self.assertIn("ValueError", outcome.failed_at.error)

    def test_missing_candidate_raises_and_is_reported_failed(self):
        prof = _profile(_slot("verify-the-artifact",
                               _tool("7de2c49f", "tropo-freeze-release-candidate.py:main")))
        outcome = runner.walk(prof, base_dir=TOOLS, execute=True,
                                context=_ctx(STUDIO_ROOT, STUDIO_ROOT, candidate=None))
        self.assertEqual(outcome.status, "failed")
        self.assertIn("ValueError", outcome.failed_at.error)

    def test_a_system_exit_zero_from_an_adapted_step_counts_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_tool_module(Path(tmp), "clean_exit.py", (
                "def go():\n"
                "    raise SystemExit(0)\n"
            ))
            prof = _profile(_slot("build-the-artifact", _tool("zzzzzzzz", "clean_exit.py:go")))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=True)
            self.assertTrue(outcome.actions[0].invoked)
            self.assertIsNone(outcome.actions[0].error)

    def test_a_system_exit_nonzero_from_an_adapted_step_fails_the_step(self):
        """D-5: except Exception does not catch SystemExit — a refusing
        CLI main() (tropo-build-release.py has ~20 sys.exit() refusal
        paths) must not tear the whole walk down uncaught."""
        with tempfile.TemporaryDirectory() as tmp:
            _write_tool_module(Path(tmp), "dirty_exit.py", (
                "def go():\n"
                "    raise SystemExit(3)\n"
            ))
            prof = _profile(_slot("build-the-artifact", _tool("zzzzzzzz", "dirty_exit.py:go")))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=True)
            self.assertEqual(outcome.status, "failed")
            self.assertIn("3", outcome.failed_at.error)

    def test_later_steps_are_never_visited_after_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_tool_module(Path(tmp), "boom2.py", "def go():\n    raise RuntimeError('x')\n")
            prof = _profile(_slot(
                "build-the-artifact",
                _tool("aaaaaaaa", "boom2.py:go"),
                _tool("bbbbbbbb", "boom2.py:go"),
            ))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=True)
            self.assertEqual([a.step_uid for a in outcome.actions], ["aaaaaaaa"])


# ===========================================================================
# The safety boundary: the outward act is never invoked, by uid OR by slot.
# ===========================================================================

class NeverFiresThePublishStep(unittest.TestCase):
    """Every test here must first satisfy the orchestrator PRECONDITION for
    3dd817cb (a valid identity plus an orchestrator_invoked row) — otherwise
    the precondition gate refuses first, for an unrelated reason, and the
    walk never reaches the invocation attempt this class exists to guard.
    Verified by mutation: with an unsatisfied gate, emptying NEVER_INVOKED
    and PUBLISH_SLOTS entirely left two of these three tests green, because
    the gate's own unrelated refusal provided false cover."""

    def test_the_named_publish_step_is_never_invoked_even_with_a_working_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "FIRED"
            _write_tool_module(Path(tmp), "would_fire.py", (
                "from pathlib import Path\n"
                f"def cmd_fire():\n    Path({str(marker)!r}).write_text('bang')\n    return 0\n"
            ))
            _write_journal(Path(tmp),
                            {"event": "run_created",
                             "data": {"saga_id": "release:aaaaaaaa",
                                       "pipeline_run_uid": "aaaaaaaa"}},
                            {"event": "tropo.release.orchestrator_invoked",
                             "ts": "2026-01-01T00:00:00Z", "actor": "mike"})
            prof = _profile(_slot("publish-the-artifact",
                                   _tool("3dd817cb", "would_fire.py:cmd_fire")))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=True, context=_ctx(tmp, tmp))
            self.assertIsNone(runner._requires_orchestrator_invoked(_ctx(tmp, tmp)),
                              "the precondition gate must be OPEN for this test to isolate "
                              "the outward-act boundary rather than the gate")
            self.assertFalse(marker.exists())
            self.assertFalse(outcome.actions[0].invoked)

    def test_a_renamed_step_in_the_publish_slot_is_also_never_invoked(self):
        """D-6: the boundary must survive a step being renamed — it is
        keyed to the SLOT as well as to the literal uid `3dd817cb`."""
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "FIRED"
            _write_tool_module(Path(tmp), "would_fire2.py", (
                "from pathlib import Path\n"
                f"def go():\n    Path({str(marker)!r}).write_text('bang')\n    return 0\n"
            ))
            _write_journal(Path(tmp), {"event": "tropo.release.orchestrator_invoked", "ts": "2026-01-01T00:00:00Z"})
            prof = _profile(_slot("publish-the-artifact",
                                   _tool("cafefeed", "would_fire2.py:go")))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=True, context=_ctx(tmp, tmp))
            self.assertFalse(marker.exists())
            self.assertFalse(outcome.actions[0].invoked)

    def test_a_bare_command_publish_step_is_also_never_shelled_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "FIRED"
            _write_journal(Path(tmp),
                            {"event": "run_created",
                             "data": {"saga_id": "release:aaaaaaaa",
                                       "pipeline_run_uid": "aaaaaaaa"}},
                            {"event": "tropo.release.orchestrator_invoked",
                             "ts": "2026-01-01T00:00:00Z", "actor": "mike"})
            prof = _profile(_slot("publish-the-artifact",
                                   _tool("3dd817cb", "touch %s" % marker)))
            self.assertIsNone(runner._requires_orchestrator_invoked(_ctx(tmp, tmp)))
            runner.walk(prof, execute=True, context=_ctx(tmp, tmp))
            self.assertFalse(marker.exists())


# ===========================================================================
# AC1's own named command target.
# ===========================================================================

class ExecutionIsReal(unittest.TestCase):
    def test_execute_actually_invokes_a_resolvable_deterministic_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "ran.json"
            _write_tool_module(Path(tmp), "real_step.py", (
                "from pathlib import Path\n"
                f"def go(activation_uid):\n    Path({str(marker)!r}).write_text(activation_uid)\n    return 0\n"
            ))
            prof = _profile(_slot("build-the-artifact", _tool("f9365ede", "real_step.py:go")))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=True,
                                    context=_ctx(tmp, tmp, activation_uid="cafebabe"))
            self.assertTrue(outcome.actions[0].invoked)
            self.assertEqual(marker.read_text(), "cafebabe")

    def test_without_execute_nothing_is_invoked(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "should_not_run.json"
            _write_tool_module(Path(tmp), "no_run.py", (
                "from pathlib import Path\n"
                f"def go(activation_uid):\n    Path({str(marker)!r}).write_text('x')\n"
            ))
            prof = _profile(_slot("build-the-artifact", _tool("f9365ede", "no_run.py:go")))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=False,
                                    context=_ctx(tmp, tmp))
            self.assertFalse(outcome.actions[0].invoked)
            self.assertFalse(marker.exists())

    def test_a_dry_run_report_is_the_default_regardless_of_context(self):
        prof = _profile(_slot("build-the-artifact", _tool("aaaaaaaa", "unresolvable.py:go")))
        cold = runner.walk(prof)
        self.assertFalse(cold.actions[0].invoked)


# ===========================================================================
# AC2's own named command target.
# ===========================================================================

class ResumeFromRunState(unittest.TestCase):
    def test_a_terminal_step_is_skipped_and_not_invoked_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "should_not_rerun.json"
            _write_tool_module(Path(tmp), "again.py", (
                "from pathlib import Path\n"
                f"def go(activation_uid):\n    Path({str(marker)!r}).write_text('x')\n"
            ))
            _write_state(Path(tmp), d0000001="verified")
            prof = _profile(_slot("build-the-artifact", _tool("d0000001", "again.py:go")))
            outcome = runner.walk(prof, base_dir=Path(tmp), execute=True, context=_ctx(tmp, tmp))
            self.assertTrue(outcome.actions[0].already_done)
            self.assertFalse(outcome.actions[0].invoked)
            self.assertFalse(marker.exists())

    def test_a_verified_judgment_step_no_longer_halts_the_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_state(Path(tmp), j0000001="verified", a0000001="pending")
            prof = _profile(_slot(
                "verify-the-artifact",
                _playbook("j0000001", "j0000001", "mike"),
                _tool("a0000001", "no-such-tool.py:nope"),
            ))
            outcome = runner.walk(prof, context=_ctx(tmp, tmp))
            self.assertEqual([a.step_uid for a in outcome.actions], ["j0000001", "a0000001"])
            self.assertIsNone(outcome.halted_at)
            self.assertEqual(outcome.status, "incomplete")

    def test_an_unsatisfied_judgment_step_still_halts(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_state(Path(tmp), j0000001="pending", a0000001="pending")
            prof = _profile(_slot(
                "verify-the-artifact",
                _playbook("j0000001", "j0000001", "mike"),
                _tool("a0000001", "no-such-tool.py:nope"),
            ))
            outcome = runner.walk(prof, context=_ctx(tmp, tmp))
            self.assertEqual(outcome.status, "halted")
            self.assertEqual(outcome.halted_at.step_uid, "j0000001")

    def test_missing_run_state_means_nothing_is_assumed_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof = _profile(_slot("verify-the-artifact", _playbook("j0000001", "j0000001", "mike")))
            outcome = runner.walk(prof, context=_ctx(tmp, tmp))
            self.assertEqual(outcome.status, "halted")
            self.assertFalse(outcome.actions[0].already_done)

    def test_an_unreadable_run_state_file_raises_rather_than_assumes_nothing_done(self):
        """D-7: the exact inversion — a damaged state file (an interrupted
        write leaves this shape) must not read as a cold start, or --execute
        re-runs a release from the beginning against already-completed
        steps."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "run.state.json").write_text('{"step_status": {"d": "veri', encoding="utf-8")
            with self.assertRaises(runner.RunStateUnreadable):
                runner.step_status(Path(tmp))

    def test_each_terminal_state_variant_is_recognized(self):
        for state in ("verified", "completed", "skipped"):
            with tempfile.TemporaryDirectory() as tmp:
                _write_state(Path(tmp), d0000001=state)
                prof = _profile(_slot("build-the-artifact", _tool("d0000001", "no-such.py:nope")))
                outcome = runner.walk(prof, context=_ctx(tmp, tmp))
                self.assertTrue(outcome.actions[0].already_done, "state %r should be terminal" % state)

    def test_a_non_terminal_state_variant_still_halts(self):
        """Real corpus vocabulary (42261546's own run.state.json carries
        `declared` for steps not yet started) — this is not a synthetic
        string, it is what an in-flight run actually writes."""
        with tempfile.TemporaryDirectory() as tmp:
            _write_state(Path(tmp), j0000001="declared")
            prof = _profile(_slot("verify-the-artifact", _playbook("j0000001", "j0000001", "mike")))
            outcome = runner.walk(prof, context=_ctx(tmp, tmp))
            self.assertEqual(outcome.status, "halted")
            self.assertFalse(outcome.actions[0].already_done)


# ===========================================================================
# AC3's own named command target — the orchestrator precondition. Gates get
# real artifacts: this is the mechanism five real defects (D-9, D-12, F1's
# sibling class) were found in, and every fixture-based test of it in the
# suite this replaces missed at least one of them.
# ===========================================================================

class OrchestratorGate(unittest.TestCase):
    def test_the_gate_is_registered_for_the_publish_step(self):
        self.assertIn("3dd817cb", runner.PRECONDITIONS)

    def test_a_run_with_no_orchestrator_event_halts(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_journal(Path(tmp), {"event": "run_created",
                                         "data": {"saga_id": "release:aaaaaaaa",
                                                   "pipeline_run_uid": "aaaaaaaa"}})
            prof = _profile(_slot("publish-the-artifact", _tool("3dd817cb", "x.py:cmd_fire")))
            outcome = runner.walk(prof, context=_ctx(tmp, tmp))
            self.assertEqual(outcome.status, "halted")
            self.assertIn("orchestrator has not been run", outcome.halted_at.command)

    def test_the_gate_lifts_once_the_journal_carries_the_moment(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_journal(Path(tmp),
                            {"event": "run_created",
                             "data": {"saga_id": "release:aaaaaaaa",
                                       "pipeline_run_uid": "aaaaaaaa"}},
                            {"event": "tropo.release.orchestrator_invoked",
                             "ts": "2026-08-26T20:05:00Z", "actor": "mike"})
            prof = _profile(_slot("publish-the-artifact", _tool("3dd817cb", "x.py:cmd_fire")))
            outcome = runner.walk(prof, execute=True, context=_ctx(tmp, tmp))
            # Never invoked regardless (NEVER_INVOKED); the gate lifting means
            # the walk reaches the not-invoked halt, not the precondition halt.
            self.assertIsNotNone(outcome.halted_at)
            self.assertNotIn("orchestrator has not been run", outcome.halted_at.command)

    def test_against_the_real_shipped_run_the_gate_still_refuses(self):
        """D-12, live: cd68bea8 is the run that actually published, and its
        journal carries no orchestrator_invoked row. If this ever starts
        passing, either the defect was fixed upstream (good — update this
        test with the fix) or the gate quietly stopped reading the real
        journal (bad — this is the test that would catch it)."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _copy_real_run(Path(tmp), "release-pipeline-cd68bea8-2026-08-26")
            ctx = _ctx(tmp, run_dir, release_plan_uid="46079e11")
            result = runner._requires_orchestrator_invoked(ctx)
            self.assertIsNotNone(result)
            self.assertIn("orchestrator has not been run", result)

    def test_journal_is_byte_identical_after_a_full_walk_through_a_gated_profile(self):
        """The spec's own words: 'AC3 carries a test asserting the journal
        is unmodified after a walk; that test is the contract, not a
        nicety.' A one-step profile containing only the gated step never
        exercises the walk BODY that precedes the gate — this profile has a
        real earlier step too, so the walk actually runs before it halts."""
        with tempfile.TemporaryDirectory() as tmp:
            _write_tool_module(Path(tmp), "first.py", "def go():\n    return 0\n")
            _write_journal(Path(tmp), {"event": "run_created",
                                         "data": {"saga_id": "release:aaaaaaaa",
                                                   "pipeline_run_uid": "aaaaaaaa"}})
            before = (Path(tmp) / "run.jsonl").read_text(encoding="utf-8")
            prof = _profile(_slot(
                "build-the-artifact", _tool("11111111", "first.py:go")),
                _slot("publish-the-artifact", _tool("3dd817cb", "x.py:cmd_fire")))
            runner.walk(prof, base_dir=Path(tmp), execute=True, context=_ctx(tmp, tmp))
            after = (Path(tmp) / "run.jsonl").read_text(encoding="utf-8")
            self.assertEqual(before, after)
            self.assertNotIn("orchestrator_invoked", after)

    def test_a_missing_journal_refuses_with_a_reason_naming_the_read_failure(self):
        """Not merely `status == 'halted'` — Close's own finding on this
        exact shape: a status-only assertion survives deleting the
        precondition gate entirely, because the not-invoked halt also
        produces `status == 'halted'`. Assert the DISTINGUISHING reason. A
        run with NO journal at all fails closed one step earlier than 'no
        orchestrator event' — the run's own identity can't be read, and the
        gate says so rather than guessing an identity or silently opening."""
        with tempfile.TemporaryDirectory() as tmp:
            prof = _profile(_slot("publish-the-artifact", _tool("3dd817cb", "x.py:cmd_fire")))
            outcome = runner.walk(prof, context=_ctx(tmp, tmp))
            self.assertEqual(outcome.status, "halted")
            self.assertIn("could not read this run's moments", outcome.halted_at.command)
            self.assertIn("refusing rather than assuming the orchestrator ran",
                          outcome.halted_at.command)

    def test_the_never_invoked_boundary_holds_even_on_the_abandoned_run(self):
        """The abandoned run d9025a97's own journal carries a stale
        orchestrator_invoked row from before it was abandoned, so the gate
        opens on it (a documented, still-live gap — see the walkability
        tests below for the defence that actually stops it). This test
        confirms the SEPARATE, unconditional boundary — NEVER_INVOKED / the
        publish slot check — still holds even when the gate opens: the
        publish tool must still never be called."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _copy_real_run(Path(tmp), "release-pipeline-d9025a97-2026-08-23")
            self.assertIsNone(runner._requires_orchestrator_invoked(
                _ctx(tmp, run_dir)), "expected this real gap to still be open")
            marker = Path(tmp) / "FIRED"
            _write_tool_module(Path(tmp), "would_fire3.py", (
                "from pathlib import Path\n"
                f"def cmd_fire():\n    Path({str(marker)!r}).write_text('bang')\n    return 0\n"
            ))
            prof = _profile(_slot("publish-the-artifact",
                                   _tool("3dd817cb", "would_fire3.py:cmd_fire")))
            runner.walk(prof, base_dir=Path(tmp), execute=True, context=_ctx(tmp, run_dir))
            self.assertFalse(marker.exists())


# ===========================================================================
# AC4's own named command target.
# ===========================================================================

class HaltNamesARunnableCommand(unittest.TestCase):
    def test_a_judgment_halt_names_a_runnable_signoff_command(self):
        prof = _profile(_slot("verify-the-artifact", _playbook("j0000001", "6f3d2a18", "vela")))
        outcome = runner.walk(prof, context=_ctx(STUDIO_ROOT, STUDIO_ROOT, activation_uid="97fdda71"))
        _assert_runnable(self, outcome.halted_at.command)
        self.assertIn("97fdda71", outcome.halted_at.command)

    def test_a_judgment_halt_with_no_activation_still_shows_a_findable_path(self):
        """D-8: no runnable command can be built with an empty activation,
        but the operator must not be left with a bare description and no
        instruction for what to do about it."""
        prof = _profile(_slot("verify-the-artifact", _playbook("j0000001", "6f3d2a18", "vela")))
        outcome = runner.walk(prof, context=_ctx(STUDIO_ROOT, STUDIO_ROOT, activation_uid=""))
        self.assertIn("release-authorization.json", outcome.halted_at.command)
        self.assertIn("run.state.json", outcome.halted_at.command)

    def test_a_cold_walk_with_no_context_returns_a_bare_description(self):
        prof = _profile(_slot("verify-the-artifact", _playbook("j0000001", "6f3d2a18", "vela")))
        outcome = runner.walk(prof)
        self.assertEqual(outcome.halted_at.command, "perform 6f3d2a18 as executor class 'vela'")

    def test_a_precondition_halt_names_the_real_orchestrator_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_journal(Path(tmp), {"event": "run_created",
                                         "data": {"saga_id": "release:aaaaaaaa",
                                                   "pipeline_run_uid": "aaaaaaaa"}})
            prof = _profile(_slot("publish-the-artifact", _tool("3dd817cb", "x.py:cmd_fire")))
            outcome = runner.walk(prof, context=_ctx(tmp, tmp, release_plan_uid="46079e11"))
            _assert_runnable(self, outcome.halted_at.command)
            self.assertIn("46079e11", outcome.halted_at.command)

    def test_the_not_invoked_halt_for_publish_names_a_runnable_fire_command(self):
        """Fourth's F3: this exact halt kind is the one AC4's own instrument
        was never applied to in the suite this replaces. Same rigor here."""
        with tempfile.TemporaryDirectory() as tmp:
            _write_journal(Path(tmp),
                            {"event": "run_created",
                             "data": {"saga_id": "release:aaaaaaaa",
                                       "pipeline_run_uid": "aaaaaaaa"}},
                            {"event": "tropo.release.orchestrator_invoked",
                             "ts": "2026-08-26T20:05:00Z", "actor": "mike"})
            prof = _profile(_slot("publish-the-artifact", _tool("3dd817cb", "x.py:cmd_fire")))
            outcome = runner.walk(prof, execute=True, context=_ctx(tmp, tmp))
            self.assertEqual(outcome.status, "halted")
            _assert_runnable(self, outcome.halted_at.command)

    def test_every_shipped_judgment_step_produces_a_runnable_halt(self):
        """Sweep of every real judgment step in the shipped profile
        (6bf18510), not just one hand-picked example."""
        from lib.release_profile import load_profile
        from lib import release_bindings
        profile = load_profile(STUDIO_ROOT, "6bf18510",
                                 declared_leaves=release_bindings.declared_leaves(STUDIO_ROOT))
        for slot_spec in profile.slots:
            for binding in slot_spec.steps:
                if binding.kind != "playbook":
                    continue
                one_step = _profile(_slot(slot_spec.slot, binding))
                outcome = runner.walk(one_step, context=_ctx(
                    STUDIO_ROOT, STUDIO_ROOT, activation_uid="97fdda71"))
                self.assertEqual(outcome.status, "halted", binding.step_uid)
                _assert_runnable(self, outcome.halted_at.command)


# ===========================================================================
# Real-artifact coverage for the walkability gates main() consults before
# ever calling walk() — the CLI-level defence for the exact D-9/D-12 shapes.
# ===========================================================================

class RunWalkabilityAgainstRealRuns(unittest.TestCase):
    def test_the_abandoned_run_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _copy_real_run(Path(tmp), "release-pipeline-d9025a97-2026-08-23")
            reason = runner.run_is_walkable(run_dir)
            self.assertIsNotNone(reason)
            self.assertIn("never bootstrapped", reason)

    def test_the_superseded_run_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp)
            _copy_real_run(studio, "release-pipeline-cd68bea8-2026-08-26")
            superseded = _copy_real_run(studio, "release-pipeline-42261546-2026-08-25")
            reason = runner.run_is_walkable(superseded)
            self.assertIsNotNone(reason)
            self.assertIn("superseded by", reason)

    def test_the_shipped_run_is_permitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp)
            shipped = _copy_real_run(studio, "release-pipeline-cd68bea8-2026-08-26")
            _copy_real_run(studio, "release-pipeline-42261546-2026-08-25")
            self.assertIsNone(runner.run_is_walkable(shipped))

    def test_a_run_with_no_state_file_at_all_is_permitted_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(runner.run_is_walkable(Path(tmp)))


class ReleasePlanWalkabilityAgainstRealPlans(unittest.TestCase):
    def test_the_first_real_cancelled_plan_past_the_historical_scan_window_is_refused(self):
        """F1: `status: cancelled` sits at line 64 of 9873ff78.md, past the
        60-line cap the original implementation used. This is the exact
        plan that bug's own docstring named."""
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp)
            _copy_real_plan(studio, "9873ff78")
            reason = runner.plan_is_walkable(studio, "9873ff78")
            self.assertIsNotNone(reason)
            self.assertIn("cancelled", reason)

    def test_the_second_real_cancelled_plan_past_the_window_is_refused(self):
        """F1's other named plan: status at line 127 of 088e21aa.md."""
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp)
            _copy_real_plan(studio, "088e21aa")
            reason = runner.plan_is_walkable(studio, "088e21aa")
            self.assertIsNotNone(reason)
            self.assertIn("cancelled", reason)

    def test_the_live_plan_that_actually_shipped_is_permitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp)
            _copy_real_plan(studio, "46079e11")
            self.assertIsNone(runner.plan_is_walkable(studio, "46079e11"))

    def test_a_plan_missing_entirely_is_permitted_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(runner.plan_is_walkable(Path(tmp), "00000000"))

    def test_the_scan_reads_the_whole_frontmatter_block_not_a_fixed_line_count(self):
        """The regression proof, independent of any specific real file: a
        fixture whose status line sits deliberately past ANY once-used fixed
        window (60 lines) must still be caught — this is what the real
        plans above happen to exercise, pinned here without depending on
        their exact byte offsets ever staying the same."""
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp)
            files_dir = studio / "vault" / "files"
            files_dir.mkdir(parents=True)
            padding = "".join("field_%02d: some realistic value here\n" % n for n in range(90))
            (files_dir / "deadbeef.md").write_text(
                "---\nuid: deadbeef\n%sstatus: cancelled\nabandon_reason: x\n---\n" % padding,
                encoding="utf-8")
            reason = runner.plan_is_walkable(studio, "deadbeef")
            self.assertIsNotNone(reason)
            self.assertIn("cancelled", reason)


# ===========================================================================
# runner.main() itself — nothing in the suite this replaces ever drove it,
# which the fourth verification pass named as the reason its own dead
# walkability-refusal mutation stayed invisible.
# ===========================================================================

class MainCliGating(unittest.TestCase):
    """`declared_leaves` walks the REAL pipeline tree rooted at 634913c2,
    which a hermetic fixture vault does not carry — every real profile load
    needs it, so it is patched to an empty tuple here. That is honest for
    these fixture profiles: they declare zero steps, so "no uid is a live
    leaf" excludes nothing they use. Patching `declared_leaves` isolates the
    concern this class is testing (main()'s own CLI plumbing and gating)
    from an unrelated one (leaf-membership enforcement, already covered
    elsewhere against the real tree)."""

    def setUp(self):
        self._saved = runner.release_bindings.declared_leaves
        runner.release_bindings.declared_leaves = lambda *a, **k: ()
        self.addCleanup(setattr, runner.release_bindings, "declared_leaves", self._saved)

    def _run_main(self, argv):
        import io
        import contextlib
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runner.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_main_refuses_to_walk_a_cancelled_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp)
            _copy_real_plan(studio, "9873ff78")
            _copy_real_run(studio, "release-pipeline-d9025a97-2026-08-23")
            profile_dir = studio / "vault" / "files"
            (profile_dir / "profuid01.md").write_text(
                "---\nuid: profuid01\ntype: release-profile\nproduct: test\n"
                "pipeline_uid: \"00000000\"\nslots:\n"
                "- slot: build-the-artifact\n  gate_contract: candidate\n  steps: []\n"
                "- slot: verify-the-artifact\n  gate_contract: pre-freeze\n  steps: []\n"
                "- slot: publish-the-artifact\n  gate_contract: pre-outward-fire\n  steps: []\n"
                "---\n", encoding="utf-8")
            code, out, err = self._run_main([
                "profuid01", "--vault-path", str(studio),
                "--release-plan-uid", "9873ff78",
            ])
            self.assertEqual(code, 2)
            self.assertIn("refusing to walk", err)
            self.assertIn("cancelled", err)

    def test_main_dry_run_reports_and_exits_zero_on_a_simple_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp)
            profile_dir = studio / "vault" / "files"
            profile_dir.mkdir(parents=True)
            (profile_dir / "profuid02.md").write_text(
                "---\nuid: profuid02\ntype: release-profile\nproduct: test2\n"
                "pipeline_uid: \"00000000\"\nslots:\n"
                "- slot: build-the-artifact\n  gate_contract: candidate\n  steps: []\n"
                "- slot: verify-the-artifact\n  gate_contract: pre-freeze\n  steps: []\n"
                "- slot: publish-the-artifact\n  gate_contract: pre-outward-fire\n  steps: []\n"
                "---\n", encoding="utf-8")
            code, out, err = self._run_main(["profuid02", "--vault-path", str(studio)])
            self.assertEqual(code, 0)
            self.assertIn("complete", out)

    def test_main_errors_when_zero_profiles_are_discoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = self._run_main(["--vault-path", tmp])
            self.assertEqual(code, 2)
            self.assertIn("ERROR", err)


# ===========================================================================
# Documented-vs-actual discrepancy: walk() follows frontmatter slot order,
# not ReleaseProfile.ordered_steps()'s canonical (build, verify, publish)
# order.
# ===========================================================================

class ProfileSlotOrderIsFrontmatterOrder(unittest.TestCase):
    def test_walk_visits_slots_in_the_order_they_were_declared(self):
        # Publish declared FIRST, deliberately out of canonical order.
        prof = _profile(
            _slot("publish-the-artifact", _tool("f1111111", "no.py:x")),
            _slot("build-the-artifact", _tool("s2222222", "no.py:x")),
        )
        outcome = runner.walk(prof)
        self.assertEqual(outcome.actions[0].step_uid, "f1111111")


class TheWalkRecordsItselfWithTheRuntime(unittest.TestCase):
    """Found by the first real release this runner ever drove.

    The runner executed a step and never told the pipeline runtime. The step
    stayed `declared`, only the first step was ever eligible, and the doc leg
    refused with "not eligible in this run" — the walk could not pass step one
    on a real release. Worse, the resume this runner is built around reads step
    state that NOTHING WROTE; every resume test passed because its fixture
    wrote that state by hand.

    A walker that does not advance the run is not a driver.
    """

    def test_the_production_default_is_the_real_runtime_driver(self):
        self.assertIs(_REAL_RUNTIME_DRIVER, runner._drive_runtime)

    def test_the_walk_records_start_and_completion_of_every_executed_step(self):
        import tempfile as _tf, json as _json
        with _tf.TemporaryDirectory() as d:
            root = Path(d)
            (root / "run.state.json").write_text('{"step_status":{}}', encoding="utf-8")
            (root / "run.jsonl").write_text(_json.dumps(
                {"event": "tropo.release.orchestrator_invoked",
                 "data": {"saga_id": "release:abcd1234",
                          "pipeline_run_uid": "abcd1234"}}) + "\n", encoding="utf-8")
            (root / "t.py").write_text("def go(*a, **k):\n    return 0\n", encoding="utf-8")
            calls = []
            ctx = runner.RunContext(
                vault_root=root, release_plan_uid="p", run_dir=root,
                activation_uid="abc12345")
            prof = _profile(_slot("build-the-artifact", _tool("f9365ede", "t.py:go")))
            outcome = runner.walk(prof, base_dir=root, execute=True, context=ctx,
                                  drive=lambda c, sub, uid, extra=None:
                                  calls.append((sub, uid)))
            self.assertTrue(outcome.actions[0].invoked, outcome.actions[0].error)
            self.assertIn(("step-start", "f9365ede"), calls)
            self.assertIn(("step-complete", "f9365ede"), calls)

    def test_a_step_that_cannot_be_recorded_is_not_reported_as_invoked(self):
        """Running and failing to record is not success: the next step would
        never become eligible and resume would re-run it forever."""
        import tempfile as _tf, json as _json
        with _tf.TemporaryDirectory() as d:
            root = Path(d)
            (root / "run.state.json").write_text('{"step_status":{}}', encoding="utf-8")
            (root / "run.jsonl").write_text(_json.dumps(
                {"event": "tropo.release.orchestrator_invoked",
                 "data": {"saga_id": "release:abcd1234",
                          "pipeline_run_uid": "abcd1234"}}) + "\n", encoding="utf-8")
            (root / "t.py").write_text("def go(*a, **k):\n    return 0\n", encoding="utf-8")
            ctx = runner.RunContext(
                vault_root=root, release_plan_uid="p", run_dir=root,
                activation_uid="abc12345")
            prof = _profile(_slot("build-the-artifact", _tool("f9365ede", "t.py:go")))
            outcome = runner.walk(
                prof, base_dir=root, execute=True, context=ctx,
                drive=lambda c, sub, uid, extra=None:
                "runtime refused" if sub == "step-complete" else None)
            self.assertEqual(outcome.status, "failed")
            self.assertFalse(outcome.actions[0].invoked)


from lib.release_profile import ReleaseProfile, SlotSpec  # noqa: E402
from lib.release_bindings import ExecutorBinding  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders. Real dataclasses, not a duck-typed stand-in: an
# ExecutorBinding built here runs the SAME __post_init__ validation a real
# vault entry's binding runs (playbook needs an executor, tool must not name
# one) — a fixture built this way cannot silently represent a combination
# load_profile_from_frontmatter could never produce.
# ---------------------------------------------------------------------------

def _binding(step_uid, kind, entry, executor=None, description="a step"):
    return ExecutorBinding(
        step_uid=step_uid, kind=kind, entry=entry,
        executor=executor, description=description,
    )


def _tool(step_uid, entry, description="a tool step"):
    return _binding(step_uid, "tool", entry, description=description)


def _playbook(step_uid, entry, executor, description="a playbook step"):
    return _binding(step_uid, "playbook", entry, executor=executor, description=description)


def _slot(name, *bindings, gate_contract="candidate"):
    return SlotSpec(slot=name, gate_contract=gate_contract, steps=tuple(bindings))


def _profile(*slots, uid="test-profile", product="test", pipeline_uid="00000000"):
    return ReleaseProfile(uid=uid, product=product, pipeline_uid=pipeline_uid, slots=tuple(slots))


def _write_tool_module(directory: Path, filename: str, source: str) -> Path:
    """A fixture tool script the runner will dynamically import, exactly the
    way it imports the real ones (`_resolve_callable`) — no mock objects,
    a real file on disk with real source."""
    path = directory / filename
    path.write_text(source, encoding="utf-8")
    return path


def _copy_real_run(dest_studio: Path, folder_name: str) -> Path:
    """Copy a real vault/pipeline-runs/<folder_name> into an isolated studio
    root. Never operates on the checkout in place — the gates under test
    read from disk, and a test must not be able to leave a mark on the real
    corpus it is verifying against."""
    src = STUDIO_ROOT / "vault" / "pipeline-runs" / folder_name
    dest = dest_studio / "vault" / "pipeline-runs" / folder_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)
    return dest


def _copy_real_plan(dest_studio: Path, uid: str) -> Path:
    src = STUDIO_ROOT / "vault" / "files" / f"{uid}.md"
    dest = dest_studio / "vault" / "files" / f"{uid}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)
    return dest


def _ctx(vault_root, run_dir, release_plan_uid="p", activation_uid="a1a1a1a1",
          version=None, candidate=None):
    return runner.RunContext(
        vault_root=Path(vault_root), release_plan_uid=release_plan_uid,
        run_dir=Path(run_dir), activation_uid=activation_uid,
        version=version, candidate=candidate,
    )


def _write_state(run_dir: Path, **statuses):
    (run_dir / "run.state.json").write_text(
        json.dumps({"step_status": statuses}), encoding="utf-8")


def _write_journal(run_dir: Path, *rows):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# AC4 helper: a command is "runnable" only if every flag it names is
# recognized by the TARGET TOOL'S OWN --help, checked at the right
# subcommand level. Argus's own checker (per the mechanical verification
# pass) matched flags anywhere in --help text with no subcommand scoping,
# missing an unknown flag placed under the wrong subcommand and an unknown
# subcommand entirely. This checks both.
# ---------------------------------------------------------------------------

_FLAG_RE = re.compile(r"(--[A-Za-z][A-Za-z0-9_-]*)")
_CHOICES_RE = re.compile(r"\{([a-zA-Z0-9_,-]+)\}")


def _help_text(tool_path: Path, *args) -> str:
    result = subprocess.run(
        [sys.executable, str(tool_path), *args, "--help"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout + result.stderr


def _recognized_flags(help_text: str):
    return set(_FLAG_RE.findall(help_text))


def _subcommand_choices(help_text: str):
    match = _CHOICES_RE.search(help_text)
    if not match:
        return set()
    return set(match.group(1).split(","))


def _assert_runnable(testcase: unittest.TestCase, command_text: str) -> None:
    """Every `python3 ...` line in `command_text` must name a real tool
    under vault/tools/, every flag on it must be recognized by that tool's
    (or its subcommand's) own --help, and any bare subcommand token must be
    one of the tool's own declared choices."""
    lines = [ln.strip() for ln in command_text.splitlines() if ln.strip().startswith("python3 ")]
    testcase.assertTrue(lines, "no runnable command line found in: %r" % (command_text,))
    for line in lines:
        tokens = shlex.split(line)
        testcase.assertEqual(tokens[0], "python3", line)
        raw_path = tokens[1]
        # Placeholders like <activation-uid> never appear here — the path is
        # always a real relative tool path in every halt this runner builds.
        tool_path = STUDIO_ROOT / raw_path if not Path(raw_path).is_absolute() else Path(raw_path)
        testcase.assertTrue(tool_path.is_file(), "%s does not exist on disk" % (tool_path,))

        top_help = _help_text(tool_path)
        choices = _subcommand_choices(top_help)
        top_flags = _recognized_flags(top_help)

        tail = [("DUMMY_VALUE" if t.startswith("<") and t.endswith(">") else t) for t in tokens[2:]]
        # Split at the first bare (non-flag, non-value-of-a-flag) token that
        # is a declared subcommand choice, if any.
        subcommand_index = None
        i = 0
        while i < len(tail):
            token = tail[i]
            if token.startswith("--"):
                i += 2  # flag and its value
                continue
            if choices and token in choices:
                subcommand_index = i
            i += 1

        if subcommand_index is None:
            for flag in tail:
                if flag.startswith("--"):
                    testcase.assertIn(
                        flag, top_flags,
                        "%s: %r is not a recognized flag (--help: %s)"
                        % (tool_path.name, flag, sorted(top_flags)))
            continue

        subcommand = tail[subcommand_index]
        testcase.assertIn(
            subcommand, choices,
            "%s: %r is not one of its declared subcommands %s"
            % (tool_path.name, subcommand, sorted(choices)))
        sub_help = _help_text(tool_path, subcommand)
        sub_flags = _recognized_flags(sub_help)
        for flag in tail[subcommand_index + 1:]:
            if flag.startswith("--"):
                testcase.assertIn(
                    flag, sub_flags,
                    "%s %s: %r is not a recognized flag (--help: %s)"
                    % (tool_path.name, subcommand, flag, sorted(sub_flags)))


# ===========================================================================
# AC1 signature compatibility — the actually-missing test class. Every prior
# suite checked adapter dispatch via a fixture profile and a fixture tool of
# its own devising; none checked that the ARGUMENTS an adapter passes bind
# against the REAL shipped callable's REAL signature.
# ===========================================================================


if __name__ == "__main__":
    unittest.main()
