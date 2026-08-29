#!/usr/bin/env python3
"""AC5 of 05de711d — the release can report what it cost the principal.

v1.92 shipped without a scorecard: the fire skipped the orchestrator step,
so `orchestrator_started_at` stayed null, so the card was schema-invalid,
so the publisher's validity gate recorded it absent, so completion was
never observed and the saga never closed. Every link in that chain was
correct behaviour. AC5 is the fix: when the run's journal (and the
canonical event bus, for the one moment — `scope_locked` — that has never
once appeared in a run journal) carries both required stamps, a real card
is written and it validates against the schema; when it does not, no card
is written and the absence is named rather than papered over with a
placeholder.

Rewritten from the spec, the implementation, and the schema itself — not
from the suite this replaces. The one positive (card genuinely written)
case is built and verified against the REAL schema file and the REAL
refusal baseline shipped at `.tropo/release-refusal-baseline.json`, empir-
ically confirmed to validate clean before being pinned here; the negative
case is checked against the run that actually shipped (`cd68bea8`), whose
journal really does carry no orchestrator moment.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
SCHEMA_PATH = STUDIO_ROOT / "vault" / "schema" / "one-prompt-release-scorecard.schema.json"
BASELINE_PATH = STUDIO_ROOT / ".tropo" / "release-refusal-baseline.json"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_metrics as metrics  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "release_orchestrator_under_test", TOOLS / "tropo-release.py")
release = importlib.util.module_from_spec(_spec)
sys.modules["release_orchestrator_under_test"] = release
_spec.loader.exec_module(release)


def _copy_real_baseline(vault: Path) -> None:
    (vault / ".tropo").mkdir(parents=True, exist_ok=True)
    shutil.copy(BASELINE_PATH, vault / ".tropo" / "release-refusal-baseline.json")


def _write_bus_scope_locked(vault: Path, run_uid: str, ts: str) -> None:
    streams = vault / "vault" / "events" / "streams"
    streams.mkdir(parents=True, exist_ok=True)
    row = {
        "specversion": "1.0", "type": "tropo.release.scope_locked", "time": ts,
        "data": {"pipeline_run_uid": run_uid, "release_plan_uid": "cccccccc",
                  "activation_uid": "bbbbbbbb", "saga_id": "release:%s" % run_uid},
    }
    (streams / "bus1.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")


def _write_run_journal(run_dir: Path, *rows) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")


def _valid_baseline_dict(**overrides):
    baseline = {
        "baseline_version": "1.0.0",
        "classifier_version": "1.0.0",
        "classes": [{"id": "R188-01-example"}],
    }
    baseline.update(overrides)
    payload = json.dumps({k: v for k, v in baseline.items() if k != "composite_sha256"},
                          sort_keys=True, separators=(",", ":"))
    baseline["composite_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return baseline


def _minimal_stamps(**overrides):
    stamps = {
        "scope_locked_at": "2026-01-01T00:00:00Z",
        "orchestrator_started_at": "2026-01-01T00:05:00Z",
        "primary_live_at": "2026-01-01T00:10:00Z",
        "all_targets_live_at": "2026-01-01T00:15:00Z",
    }
    stamps.update(overrides)
    return stamps


def _three_gestures():
    return [
        {"input": "release_scope_locked", "at": "2026-01-01T00:00:00Z"},
        {"input": "release_orchestrator_invoked", "at": "2026-01-01T00:05:00Z"},
        {"input": "release_fire_authorized", "at": "2026-01-01T00:08:00Z"},
    ]


# ===========================================================================
# release_metrics.build_scorecard — the verdict derivation. Every documented
# fail branch is exercised, each changing exactly one input from an
# otherwise-passing baseline, so the failing dimension is unambiguous.
# ===========================================================================

class VerdictDerivation(unittest.TestCase):
    def _passing_card(self, **overrides):
        kwargs = dict(
            mode=metrics.REAL_FIRE, saga_id="release:aaaaaaaa",
            pipeline_run_uid="aaaaaaaa", release_version="1.0.0",
            principal_inputs=_three_gestures(), timestamps=_minimal_stamps(),
            active_machine_seconds=12.0, observed_refusals=[],
            baseline=_valid_baseline_dict(),
        )
        kwargs.update(overrides)
        return metrics.build_scorecard(**kwargs)

    def test_three_gestures_all_stamps_present_no_unknown_refusals_passes(self):
        card = self._passing_card()
        self.assertEqual(card["verdict"], "pass")

    def test_a_manual_bridge_gesture_fails_the_verdict(self):
        gestures = _three_gestures() + [{"input": "manual_resume", "at": "2026-01-01T00:06:00Z"}]
        card = self._passing_card(principal_inputs=gestures)
        self.assertEqual(card["verdict"], "fail")
        self.assertFalse(card["gestures"]["met"])

    def test_a_missing_principal_gesture_fails_the_verdict(self):
        gestures = _three_gestures()[:2]
        card = self._passing_card(principal_inputs=gestures)
        self.assertEqual(card["verdict"], "fail")
        self.assertIn("release_fire_authorized", card["gestures"]["detail"])

    def test_a_null_required_timestamp_fails_the_verdict_even_though_the_schema_allows_it_as_a_type(self):
        """primary_live_at/all_targets_live_at are schema-nullable, but the
        verdict predicate checks all four for None regardless — a null
        stamp is a legitimate schema value and a failing verdict at once."""
        card = self._passing_card(timestamps=_minimal_stamps(primary_live_at=None))
        self.assertEqual(card["verdict"], "fail")

    def test_elapsed_unobtainable_because_scope_locked_or_all_targets_live_is_missing_fails(self):
        card = self._passing_card(timestamps=_minimal_stamps(all_targets_live_at=None))
        self.assertIsNone(card["elapsed"]["lock_to_all_targets_live_seconds"])
        self.assertEqual(card["verdict"], "fail")

    def test_refusals_not_recorded_fails_the_verdict(self):
        card = self._passing_card(observed_refusals=None)
        self.assertFalse(card["refusals"]["recorded"])
        self.assertEqual(card["verdict"], "fail")

    def test_an_unknown_refusal_class_fails_the_verdict(self):
        card = self._passing_card(observed_refusals=["R188-99-never-seen-before"])
        self.assertIn("R188-99-never-seen-before", card["refusals"]["unknown"])
        self.assertEqual(card["verdict"], "fail")

    def test_a_known_refusal_class_does_not_fail_the_verdict_on_its_own(self):
        card = self._passing_card(observed_refusals=["R188-01-example"])
        self.assertEqual(card["refusals"]["known"], ["R188-01-example"])
        self.assertEqual(card["verdict"], "pass")

    def test_an_unknown_mode_raises(self):
        with self.assertRaises(metrics.ReleaseMetricsError):
            self._passing_card(mode="dress-rehearsal")

    def test_a_timestamps_mapping_missing_a_required_key_entirely_raises(self):
        """Key ABSENCE is stricter than key-present-but-null: build_scorecard
        refuses to guess a shape the caller never declared."""
        stamps = _minimal_stamps()
        del stamps["all_targets_live_at"]
        with self.assertRaises(metrics.ReleaseMetricsError):
            self._passing_card(timestamps=stamps)

    def test_an_unrecognized_gesture_input_raises(self):
        with self.assertRaises(metrics.ReleaseMetricsError):
            self._passing_card(principal_inputs=[{"input": "made_up_gesture", "at": "x"}])

    def test_a_gesture_with_no_timestamp_raises(self):
        with self.assertRaises(metrics.ReleaseMetricsError):
            self._passing_card(principal_inputs=[{"input": "release_scope_locked", "at": ""}])

    def test_output_timestamps_are_exactly_the_four_required_keys_even_if_more_were_supplied(self):
        card = self._passing_card(timestamps=dict(_minimal_stamps(), extra_key="ignored"))
        self.assertEqual(set(card["timestamps"]), {
            "scope_locked_at", "orchestrator_started_at",
            "primary_live_at", "all_targets_live_at"})


# ===========================================================================
# release_metrics.validate_scorecard — against the REAL shipped schema, on
# BOTH code paths (jsonschema when installed, the hand-rolled structural
# fallback when it is not — production runs the fallback today, per the
# close-verification pass's own measurement, and both must catch the same
# defect classes).
# ===========================================================================

class ValidateAgainstTheRealSchema(unittest.TestCase):
    def _valid_card(self):
        return metrics.build_scorecard(
            mode=metrics.REAL_FIRE, saga_id="release:aaaaaaaa",
            pipeline_run_uid="aaaaaaaa", release_version="1.0.0",
            principal_inputs=_three_gestures(), timestamps=_minimal_stamps(),
            active_machine_seconds=1.0, observed_refusals=[],
            baseline=_valid_baseline_dict(),
        )

    def _findings_both_paths(self, card):
        real = metrics.validate_scorecard(card, SCHEMA_PATH)
        structural = metrics._structural_check(
            card, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
        return real, structural

    def test_a_genuinely_valid_card_passes_both_validators(self):
        real, structural = self._findings_both_paths(self._valid_card())
        self.assertEqual(real, [])
        self.assertEqual(structural, [])

    def test_a_missing_required_top_level_key_is_caught_by_both(self):
        card = self._valid_card()
        del card["verdict"]
        real, structural = self._findings_both_paths(card)
        self.assertTrue(real)
        self.assertTrue(structural)

    def test_a_null_non_nullable_timestamp_is_caught_by_both(self):
        """The exact v1.92 defect shape: orchestrator_started_at null."""
        card = self._valid_card()
        card["timestamps"]["orchestrator_started_at"] = None
        real, structural = self._findings_both_paths(card)
        self.assertTrue(real)
        self.assertTrue(structural)

    def test_an_empty_release_version_below_minlength_is_caught_by_both(self):
        card = self._valid_card()
        card["release_version"] = ""
        real, structural = self._findings_both_paths(card)
        self.assertTrue(real)
        self.assertTrue(structural)

    def test_an_undeclared_key_is_caught_by_both_closed_schema_check(self):
        card = self._valid_card()
        card["an_extra_field_nobody_declared"] = True
        real, structural = self._findings_both_paths(card)
        self.assertTrue(real)
        self.assertTrue(structural)

    def test_a_verdict_outside_the_enum_is_caught_by_both(self):
        card = self._valid_card()
        card["verdict"] = "maybe"
        real, structural = self._findings_both_paths(card)
        self.assertTrue(real)
        self.assertTrue(structural)

    def test_the_fallback_runs_when_jsonschema_is_unavailable(self):
        """Forces the exact branch production takes today (close-pass
        measurement: jsonschema is not installed in this environment)."""
        saved = sys.modules.pop("jsonschema", None)
        import builtins
        real_import = builtins.__import__

        def _blocking_import(name, *args, **kwargs):
            if name == "jsonschema":
                raise ImportError("blocked for this test")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = _blocking_import
        try:
            findings = metrics.validate_scorecard(self._valid_card(), SCHEMA_PATH)
        finally:
            builtins.__import__ = real_import
            if saved is not None:
                sys.modules["jsonschema"] = saved
        self.assertEqual(findings, [])


# ===========================================================================
# classify_refusals / count_gestures — the metric primitives build_scorecard
# composes.
# ===========================================================================

class ClassifyRefusalsTests(unittest.TestCase):
    def test_none_means_not_recorded_and_is_distinct_from_zero_observed(self):
        result = metrics.classify_refusals(None, _valid_baseline_dict())
        self.assertFalse(result["recorded"])
        self.assertIsNone(result["occurrences"])
        self.assertIsNone(result["distinct_classes"])

    def test_an_empty_list_means_zero_observed_and_is_recorded(self):
        result = metrics.classify_refusals([], _valid_baseline_dict())
        self.assertTrue(result["recorded"])
        self.assertEqual(result["occurrences"], 0)

    def test_repeated_occurrences_of_one_class_count_distinctly_from_distinct_classes(self):
        baseline = _valid_baseline_dict()
        result = metrics.classify_refusals(
            ["R188-01-example", "R188-01-example", "R188-01-example"], baseline)
        self.assertEqual(result["occurrences"], 3)
        self.assertEqual(result["distinct_classes"], 1)
        self.assertEqual(result["known"], ["R188-01-example"])

    def test_an_id_absent_from_the_baseline_is_unknown_by_definition(self):
        result = metrics.classify_refusals(["never-seen-before"], _valid_baseline_dict())
        self.assertEqual(result["unknown"], ["never-seen-before"])
        self.assertEqual(result["known"], [])


class CountGesturesTests(unittest.TestCase):
    def test_three_distinct_principal_gestures_are_met(self):
        result = metrics.count_gestures(_three_gestures())
        self.assertTrue(result["met"])

    def test_a_manual_resume_present_alongside_all_three_is_not_met(self):
        gestures = _three_gestures() + [{"input": "manual_resume", "at": "x"}]
        result = metrics.count_gestures(gestures)
        self.assertFalse(result["met"])
        self.assertIn("manual_resume", result["detail"])

    def test_machine_continuation_is_not_a_valid_input_name(self):
        with self.assertRaises(metrics.ReleaseMetricsError):
            metrics.count_gestures([{"input": "machine_continued", "at": "x"}])


# ===========================================================================
# load_refusal_baseline — the digest-integrity gate over the REAL shipped
# baseline file.
# ===========================================================================

class LoadRefusalBaselineTests(unittest.TestCase):
    def test_the_real_shipped_baseline_loads_clean(self):
        baseline = metrics.load_refusal_baseline(STUDIO_ROOT)
        self.assertIn("composite_sha256", baseline)

    def test_a_missing_baseline_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(metrics.ReleaseMetricsError):
                metrics.load_refusal_baseline(Path(tmp))

    def test_a_tampered_baseline_with_a_stale_digest_raises(self):
        """An in-place edit that does not recompute composite_sha256 must be
        refused — the digest is the whole point of the gate."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            _copy_real_baseline(vault)
            path = vault / ".tropo" / "release-refusal-baseline.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["classes"].append({"id": "R188-99-snuck-in", "retrospective_row": "x"})
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(metrics.ReleaseMetricsError):
                metrics.load_refusal_baseline(vault)

    def test_a_baseline_with_a_freshly_recomputed_digest_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / ".tropo").mkdir(parents=True)
            (vault / ".tropo" / "release-refusal-baseline.json").write_text(
                json.dumps(_valid_baseline_dict()), encoding="utf-8")
            baseline = metrics.load_refusal_baseline(vault)
            self.assertEqual(baseline["baseline_version"], "1.0.0")


# ===========================================================================
# The AC5 contract itself: `_write_real_fire_scorecard`, exercised through
# the real orchestrator module, in both directions, against real-shaped
# journals and the real shipped baseline.
# ===========================================================================

class RealFireScorecardProduction(unittest.TestCase):
    def test_with_both_required_stamps_a_schema_valid_card_is_written(self):
        """The positive direction. scope_locked_at comes from the bus
        (never the run journal — measured fact, see the module docstring
        this reads); orchestrator_started_at from the run's own journal.
        Verdict is allowed to be 'fail' here (only two of three gestures are
        recorded) — AC5 asks for a VALID card, not a passing one."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            _copy_real_baseline(vault)
            run_uid = "aaaaaaaa"
            _write_bus_scope_locked(vault, run_uid, "2026-08-26T15:18:01Z")
            run_dir = vault / "run"
            _write_run_journal(
                run_dir,
                {"event": "run_created", "data": {"saga_id": "release:aaaaaaaa",
                                                     "pipeline_run_uid": run_uid}},
                {"event": "tropo.release.orchestrator_invoked",
                 "ts": "2026-08-26T20:05:00Z", "actor": "mike",
                 "data": {"pipeline_run_uid": run_uid}},
            )
            identity = release._identity(run_dir)

            release._write_real_fire_scorecard(identity, run_dir, vault, "9.9.9")

            card_path = metrics.scorecard_path(run_dir, metrics.REAL_FIRE)
            self.assertTrue(card_path.is_file())
            card = json.loads(card_path.read_text(encoding="utf-8"))
            self.assertIsNotNone(card["timestamps"]["orchestrator_started_at"])
            self.assertIsNotNone(card["timestamps"]["scope_locked_at"])
            findings = metrics.validate_scorecard(card, SCHEMA_PATH)
            self.assertEqual(findings, [], "card is not schema-valid: %s" % findings)

    def test_without_the_orchestrator_moment_no_card_is_written_and_the_absence_is_named(self):
        """The negative direction, against the run that ACTUALLY published:
        cd68bea8's own journal carries no tropo.release.orchestrator_invoked
        row (this is the live D-12 finding — v1.92 shipped without ever
        stamping this moment). No fixture invention needed."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            _copy_real_baseline(vault)
            run_dir = vault / "vault" / "pipeline-runs" / "release-pipeline-cd68bea8-2026-08-26"
            shutil.copytree(
                STUDIO_ROOT / "vault" / "pipeline-runs" / "release-pipeline-cd68bea8-2026-08-26",
                run_dir)
            identity = release._identity(run_dir)

            buf = io.StringIO()
            with redirect_stderr(buf):
                release._write_real_fire_scorecard(identity, run_dir, vault, "1.92.0")

            card_path = metrics.scorecard_path(run_dir, metrics.REAL_FIRE)
            self.assertFalse(card_path.is_file())
            self.assertIn("orchestrator_started_at", buf.getvalue())
            self.assertIn("NOT written", buf.getvalue())

    def test_without_scope_locked_no_card_is_written_either(self):
        """The OTHER required stamp: a run whose journal has the
        orchestrator moment but no bus-side scope_locked event still
        produces no card — both stamps are required, not just one."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            _copy_real_baseline(vault)
            run_uid = "aaaaaaaa"
            run_dir = vault / "run"
            _write_run_journal(
                run_dir,
                {"event": "run_created", "data": {"saga_id": "release:aaaaaaaa",
                                                     "pipeline_run_uid": run_uid}},
                {"event": "tropo.release.orchestrator_invoked",
                 "ts": "2026-08-26T20:05:00Z", "actor": "mike",
                 "data": {"pipeline_run_uid": run_uid}},
            )
            identity = release._identity(run_dir)
            buf = io.StringIO()
            with redirect_stderr(buf):
                release._write_real_fire_scorecard(identity, run_dir, vault, "9.9.9")
            self.assertFalse(metrics.scorecard_path(run_dir, metrics.REAL_FIRE).is_file())
            self.assertIn("scope_locked_at", buf.getvalue())

    def test_a_missing_refusal_baseline_never_raises_out_of_the_writer(self):
        """'Never raises: the release already happened.' A missing baseline
        is a real, plausible misconfiguration — it must not take the fire
        down with it, even though it also means no card gets written."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)  # deliberately no .tropo/release-refusal-baseline.json
            run_uid = "aaaaaaaa"
            _write_bus_scope_locked(vault, run_uid, "2026-08-26T15:18:01Z")
            run_dir = vault / "run"
            _write_run_journal(
                run_dir,
                {"event": "run_created", "data": {"saga_id": "release:aaaaaaaa",
                                                     "pipeline_run_uid": run_uid}},
                {"event": "tropo.release.orchestrator_invoked",
                 "ts": "2026-08-26T20:05:00Z", "actor": "mike",
                 "data": {"pipeline_run_uid": run_uid}},
            )
            identity = release._identity(run_dir)
            try:
                release._write_real_fire_scorecard(identity, run_dir, vault, "9.9.9")
            except Exception as exc:  # pragma: no cover - the assertion IS "this must not happen"
                self.fail("the writer raised instead of swallowing: %r" % (exc,))
            self.assertFalse(metrics.scorecard_path(run_dir, metrics.REAL_FIRE).is_file())

    def test_a_corrupt_run_journal_never_raises_out_of_the_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            _copy_real_baseline(vault)
            run_dir = vault / "run"
            run_dir.mkdir(parents=True)
            (run_dir / "run.jsonl").write_text("{not json\n", encoding="utf-8")
            identity = {"saga_id": "release:aaaaaaaa", "pipeline_run_uid": "aaaaaaaa"}
            try:
                release._write_real_fire_scorecard(identity, run_dir, vault, "9.9.9")
            except Exception as exc:
                self.fail("the writer raised instead of swallowing: %r" % (exc,))


if __name__ == "__main__":
    unittest.main()
