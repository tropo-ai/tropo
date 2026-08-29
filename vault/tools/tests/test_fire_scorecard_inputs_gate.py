#!/usr/bin/env python3
"""The `fire-scorecard-inputs` gate — the release must be ABLE to measure
what it cost the principal, checked before the outward act, not after.

D-12 (adversarial review): the scorecard needs
`tropo.release.orchestrator_invoked` in the run journal; without it the
card cannot be valid, `completion_verification` is never observed, and the
saga ends "the release is public; the journal is not" — v1.92.0's exact
resting state. Nothing on the fire path noticed until the card was already
refused, AFTER the outward act, when the only remedy left is re-firing a
live release. This gate moves the same fact to the earliest boundary where
it is knowable and refusing is free.

Rewritten from the implementation and the gate registry's own contract,
not from the suite this replaces. Two things that suite never exercised,
added here: the REFUSED/ERROR distinction `_gate_verifier` draws (a
PublishError is a refusal; anything else is an operational error, a
materially different signal to the operator) — and the roster's own
loud-failure guarantee, that this gate cannot be silently dropped from the
pre-outward-fire phase without `register_pre_outward_fire_gates` raising.
The refusal path is also checked against the run that actually shipped
without measuring itself, not only a synthetic fixture.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_gates  # noqa: E402

_pub_spec = importlib.util.spec_from_file_location(
    "publisher_under_test", TOOLS / "tropo-publish-release.py")
publisher = importlib.util.module_from_spec(_pub_spec)
sys.modules["publisher_under_test"] = publisher
_pub_spec.loader.exec_module(publisher)

_preflight_spec = importlib.util.spec_from_file_location(
    "preflight_under_test", TOOLS / "tropo-release-preflight.py")
preflight = importlib.util.module_from_spec(_preflight_spec)
sys.modules["preflight_under_test"] = preflight
_preflight_spec.loader.exec_module(preflight)

GATE = "fire-scorecard-inputs"
ORCHESTRATOR_EVENT = {"event": "tropo.release.orchestrator_invoked",
                        "ts": "2026-08-26T20:05:00Z", "actor": "mike"}


class ScorecardInputsGateFixture(unittest.TestCase):
    """Base: patches the seam the gate actually reads (tropo_roots.STUDIO_ROOT
    at call time, per the gate's own module-level lookup) and builds one
    verifier table shared by every test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self._saved_root = publisher.tropo_roots.STUDIO_ROOT
        publisher.tropo_roots.STUDIO_ROOT = self.root
        self.addCleanup(setattr, publisher.tropo_roots, "STUDIO_ROOT", self._saved_root)
        self.table = publisher._pre_outward_fire_verifiers(release_gates)

    def _run(self, activation="97fdda71"):
        run_dir = self.root / "vault" / "pipeline-runs" / "release-pipeline-abcd1234-2026-08-26"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.state.json").write_text(
            json.dumps({"activation_uid": activation}), encoding="utf-8")
        return run_dir

    def _journal(self, run_dir, *rows):
        (run_dir / "run.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")

    def _gate_outcome(self, activation="97fdda71"):
        ctx = {"publish_state": {"activation_uid": activation}}
        return self.table[GATE](ctx)


class TheGateIsRegisteredAndCannotBeSilentlyDropped(unittest.TestCase):
    """Not `GATE in table` alone — that a name maps to SOMETHING is a weaker
    claim than that the roster refuses to build without it, which is the
    actual mechanism protecting against a quiet removal."""

    def test_the_gate_is_one_of_the_pre_outward_fire_verifiers(self):
        table = publisher._pre_outward_fire_verifiers(release_gates)
        self.assertIn(GATE, table)

    def test_the_gate_is_a_row_on_the_declared_roster(self):
        roster_ids = {row[0] for row in preflight.PRE_OUTWARD_FIRE_ROSTER}
        self.assertIn(GATE, roster_ids)

    def test_building_the_registry_without_this_verifier_raises_loudly(self):
        """The regression this class exists to prevent: a future refactor
        that drops the gate from the verifiers dict must not silently
        exclude it from the fire phase — it must refuse to build a registry
        at all."""
        table = dict(publisher._pre_outward_fire_verifiers(release_gates))
        del table[GATE]
        with self.assertRaises(preflight.ReleaseGateError):
            preflight.register_pre_outward_fire_gates(preflight.GateRegistry(), table)

    def test_a_stray_verifier_not_on_the_roster_also_raises(self):
        table = dict(publisher._pre_outward_fire_verifiers(release_gates))
        table["not-a-real-gate-id"] = table[GATE]
        with self.assertRaises(preflight.ReleaseGateError):
            preflight.register_pre_outward_fire_gates(preflight.GateRegistry(), table)

    def test_the_full_registry_registers_all_eleven_gates_including_this_one(self):
        table = publisher._pre_outward_fire_verifiers(release_gates)
        registry = preflight.register_pre_outward_fire_gates(preflight.GateRegistry(), table)
        self.assertIn(GATE, registry)
        self.assertEqual(len(registry), len(preflight.PRE_OUTWARD_FIRE_ROSTER))


class TheGateRefusesWithoutTheOrchestratorMoment(ScorecardInputsGateFixture):
    def test_a_run_with_only_earlier_moments_refuses(self):
        run_dir = self._run()
        self._journal(run_dir, {"event": "run_created"}, {"event": "tropo.release.candidate_built"})
        outcome = self._gate_outcome()
        self.assertEqual(outcome.verdict, release_gates.VERDICT_REFUSED)
        self.assertIn("orchestrator has not been run", outcome.detail)

    def test_the_refusal_names_the_exact_cure_command(self):
        run_dir = self._run()
        self._journal(run_dir, {"event": "run_created"})
        outcome = self._gate_outcome()
        self.assertIn("python3 vault/tools/tropo-release.py", outcome.detail)

    def test_a_missing_journal_file_refuses_rather_than_passes(self):
        """No run.jsonl at all — fail closed, never treat absence-of-evidence
        as evidence of the moment having happened."""
        self._run()  # run.state.json only, no _journal() call
        outcome = self._gate_outcome()
        self.assertEqual(outcome.verdict, release_gates.VERDICT_REFUSED)

    def test_an_empty_journal_file_refuses(self):
        run_dir = self._run()
        (run_dir / "run.jsonl").write_text("", encoding="utf-8")
        outcome = self._gate_outcome()
        self.assertEqual(outcome.verdict, release_gates.VERDICT_REFUSED)

    def test_a_journal_with_unparseable_lines_around_the_real_ones_still_reads_correctly(self):
        run_dir = self._run()
        run_dir.joinpath("run.jsonl").write_text(
            '{not valid json\n{"event": "run_created"}\n\n', encoding="utf-8")
        outcome = self._gate_outcome()
        self.assertEqual(outcome.verdict, release_gates.VERDICT_REFUSED)
        self.assertIn("orchestrator has not been run", outcome.detail)

    def test_no_activation_uid_at_all_in_publish_state_refuses(self):
        run_dir = self._run()
        self._journal(run_dir, {"event": "run_created"})
        ctx = {"publish_state": {}}
        outcome = self.table[GATE](ctx)
        self.assertEqual(outcome.verdict, release_gates.VERDICT_REFUSED)
        self.assertIn("cannot be located", outcome.detail)

    def test_an_activation_that_matches_no_run_folder_refuses(self):
        run_dir = self._run()
        self._journal(run_dir, *[ORCHESTRATOR_EVENT])
        outcome = self._gate_outcome(activation="ffffffff")
        self.assertEqual(outcome.verdict, release_gates.VERDICT_REFUSED)
        self.assertIn("no release run folder", outcome.detail)

    def test_a_run_folder_with_an_unreadable_state_file_is_skipped_not_crashed_on(self):
        """The scan globs release-pipeline-* and reads each candidate's
        run.state.json — a sibling folder with a damaged state file must
        not raise; it must simply not match."""
        damaged = self.root / "vault" / "pipeline-runs" / "release-pipeline-damaged0-2026-08-01"
        damaged.mkdir(parents=True)
        (damaged / "run.state.json").write_text("{not json", encoding="utf-8")
        run_dir = self._run()
        self._journal(run_dir, *[ORCHESTRATOR_EVENT])
        outcome = self._gate_outcome()
        self.assertEqual(outcome.verdict, release_gates.VERDICT_PASS)


class TheGatePassesOnceTheMomentIsRecorded(ScorecardInputsGateFixture):
    def test_it_passes_once_the_orchestrator_event_is_in_the_journal(self):
        run_dir = self._run()
        self._journal(run_dir, {"event": "run_created"}, ORCHESTRATOR_EVENT)
        outcome = self._gate_outcome()
        self.assertEqual(outcome.verdict, release_gates.VERDICT_PASS)
        self.assertIn(ORCHESTRATOR_EVENT["ts"], outcome.detail)

    def test_it_finds_the_moment_regardless_of_position_in_the_journal(self):
        run_dir = self._run()
        self._journal(run_dir, ORCHESTRATOR_EVENT,
                       {"event": "run_created"}, {"event": "step_started"})
        outcome = self._gate_outcome()
        self.assertEqual(outcome.verdict, release_gates.VERDICT_PASS)

    def test_it_uses_the_first_orchestrator_event_when_more_than_one_exists(self):
        second = dict(ORCHESTRATOR_EVENT, ts="2026-08-27T00:00:00Z")
        run_dir = self._run()
        self._journal(run_dir, ORCHESTRATOR_EVENT, second)
        outcome = self._gate_outcome()
        self.assertIn(ORCHESTRATOR_EVENT["ts"], outcome.detail)
        self.assertNotIn(second["ts"], outcome.detail)


class TheGateDistinguishesRefusalFromOperationalError(unittest.TestCase):
    """`_gate_verifier` maps PublishError -> VERDICT_REFUSED and any other
    exception -> VERDICT_ERROR. These are different signals to an operator
    (a refusal names a cure; an error means the check itself broke) and no
    test in the suite this replaces ever drove the ERROR branch for this
    gate."""

    def test_a_publish_error_is_reported_as_refused(self):
        def raises_publish_error(ctx):
            raise publisher.PublishError("deliberately refused for this test")

        verifier = publisher._gate_verifier(release_gates, "probe-gate", raises_publish_error)
        outcome = verifier({})
        self.assertEqual(outcome.verdict, release_gates.VERDICT_REFUSED)
        self.assertIn("deliberately refused", outcome.detail)

    def test_an_unexpected_exception_is_reported_as_an_operational_error_not_a_refusal(self):
        def raises_type_error(ctx):
            raise TypeError("a bug, not a business refusal")

        verifier = publisher._gate_verifier(release_gates, "probe-gate", raises_type_error)
        outcome = verifier({})
        self.assertEqual(outcome.verdict, release_gates.VERDICT_ERROR)
        self.assertNotEqual(outcome.verdict, release_gates.VERDICT_REFUSED)

    def test_a_subprocess_timeout_is_also_reported_as_an_operational_error(self):
        import subprocess

        def raises_timeout(ctx):
            raise subprocess.TimeoutExpired(cmd=["x"], timeout=5)

        verifier = publisher._gate_verifier(release_gates, "probe-gate", raises_timeout)
        outcome = verifier({})
        self.assertEqual(outcome.verdict, release_gates.VERDICT_ERROR)
        self.assertIn("timed out", outcome.detail)

    def test_a_clean_return_is_reported_as_pass_with_the_detail_preserved(self):
        def passes(ctx):
            return "all clear"

        verifier = publisher._gate_verifier(release_gates, "probe-gate", passes)
        outcome = verifier({})
        self.assertEqual(outcome.verdict, release_gates.VERDICT_PASS)
        self.assertEqual(outcome.detail, "all clear")

    def test_scorecard_inputs_itself_only_ever_raises_publish_error_never_a_bare_exception(self):
        """A structural guarantee about THIS gate specifically: every one of
        its documented failure branches raises PublishError (refusal-class),
        never lets an unrelated exception (e.g. a KeyError from a malformed
        ctx) escape as an undifferentiated operational error. Probed by
        feeding it every malformed publish_state shape its own code
        branches on."""
        with tempfile.TemporaryDirectory() as tmp:
            saved = publisher.tropo_roots.STUDIO_ROOT
            publisher.tropo_roots.STUDIO_ROOT = Path(tmp)
            try:
                table = publisher._pre_outward_fire_verifiers(release_gates)
                for ctx in (
                    {"publish_state": {}},
                    {"publish_state": {"activation_uid": ""}},
                    {"publish_state": {"activation_uid": "deadbeef"}},
                ):
                    outcome = table[GATE](ctx)
                    self.assertEqual(outcome.verdict, release_gates.VERDICT_REFUSED,
                                      "ctx=%r produced %r instead of a clean refusal"
                                      % (ctx, outcome.verdict))
            finally:
                publisher.tropo_roots.STUDIO_ROOT = saved


class TheGateAgainstTheRealRunThatActuallyShipped(unittest.TestCase):
    """Gates get real artifacts. cd68bea8 is not a constructed scenario — it
    is the run that produced v1.92.0, and its journal genuinely carries no
    tropo.release.orchestrator_invoked row. If this gate had existed and
    been wired into the fire path before that release, this is the exact
    refusal an operator would have seen, before the outward act rather than
    after it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        shutil.copytree(
            STUDIO_ROOT / "vault" / "pipeline-runs" / "release-pipeline-cd68bea8-2026-08-26",
            self.root / "vault" / "pipeline-runs" / "release-pipeline-cd68bea8-2026-08-26")
        self._saved_root = publisher.tropo_roots.STUDIO_ROOT
        publisher.tropo_roots.STUDIO_ROOT = self.root
        self.addCleanup(setattr, publisher.tropo_roots, "STUDIO_ROOT", self._saved_root)

    def test_the_gate_refuses_against_the_real_shipped_run(self):
        table = publisher._pre_outward_fire_verifiers(release_gates)
        ctx = {"publish_state": {"activation_uid": "97fdda71"}}
        outcome = table[GATE](ctx)
        self.assertEqual(outcome.verdict, release_gates.VERDICT_REFUSED)
        self.assertIn("orchestrator has not been run", outcome.detail)
        self.assertIn("v1.92.0", outcome.detail)


if __name__ == "__main__":
    unittest.main()
