#!/usr/bin/env python3
"""The scorecard has to be able to say the release went badly.

Dev-spec 2fae6312 step 8. The headline claim of this package is three
gestures, and the cheapest way to satisfy it is to not count the fourth. So
most of this file is about whether the metrics can report failure at all:
manual bridges counted, unknown refusal classes surfaced rather than absorbed,
missing timestamps failing instead of defaulting.
"""

from __future__ import annotations

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

from lib.release_metrics import (  # noqa: E402
    EXTRA_INPUTS,
    GESTURE_TARGET,
    PRINCIPAL_GESTURES,
    REAL_FIRE,
    REHEARSAL,
    ReleaseMetricsError,
    build_scorecard,
    classify_refusals,
    count_gestures,
    load_refusal_baseline,
    scorecard_path,
    validate_scorecard,
)

SCHEMA = STUDIO_ROOT / "vault" / "schema" / "one-prompt-release-scorecard.schema.json"
SAGA = "release:934436ca"
RUN = "934436ca"

CLEAN_INPUTS = [
    {"input": "release_scope_locked", "at": "2026-08-16T20:00:00Z"},
    {"input": "release_orchestrator_invoked", "at": "2026-08-16T20:05:00Z"},
    {"input": "release_fire_authorized", "at": "2026-08-16T20:20:00Z"},
]

CLEAN_STAMPS = {
    "scope_locked_at": "2026-08-16T20:00:00Z",
    "orchestrator_started_at": "2026-08-16T20:05:00Z",
    "primary_live_at": "2026-08-16T20:25:00Z",
    "all_targets_live_at": "2026-08-16T20:28:00Z",
}


class BaselineTests(unittest.TestCase):
    def test_the_live_baseline_loads_and_its_digest_verifies(self):
        baseline = load_refusal_baseline(STUDIO_ROOT)
        self.assertEqual(len(baseline["classes"]), 15)
        self.assertEqual(baseline["source_retrospective_uid"], "5c26a093")

    def test_the_fifteen_ids_are_the_spec_table(self):
        ids = [row["id"] for row in load_refusal_baseline(STUDIO_ROOT)["classes"]]
        self.assertEqual(ids[0], "R188-01-latent-index-debt")
        self.assertEqual(ids[-1], "R188-15-release-entry-absent")
        self.assertEqual(len(set(ids)), 15)

    def test_an_edited_baseline_refuses_rather_than_reclassifying(self):
        """A digest nobody checks is a list of strings."""
        tmp = Path(tempfile.mkdtemp(prefix="refusal-baseline-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".tropo").mkdir()
        baseline = json.loads(
            (STUDIO_ROOT / ".tropo" / "release-refusal-baseline.json").read_text()
        )
        baseline["classes"].append({"id": "R188-16-snuck-in", "retrospective_row": "x"})
        (tmp / ".tropo" / "release-refusal-baseline.json").write_text(
            json.dumps(baseline), encoding="utf-8"
        )

        with self.assertRaises(ReleaseMetricsError) as caught:
            load_refusal_baseline(tmp)
        self.assertIn("digest does not match", str(caught.exception))


class GestureCountingTests(unittest.TestCase):
    def test_three_canonical_inputs_meet_the_target(self):
        counted = count_gestures(CLEAN_INPUTS)
        self.assertTrue(counted["met"])
        self.assertEqual(counted["target"], GESTURE_TARGET)

    def test_a_manual_resume_is_a_fourth_gesture_and_fails(self):
        """The cheapest way to claim three is to not count the fourth."""
        counted = count_gestures(
            CLEAN_INPUTS + [{"input": "manual_resume", "at": "2026-08-16T20:22:00Z"}]
        )
        self.assertFalse(counted["met"])
        self.assertIn("manual_resume", counted["detail"])
        self.assertIn("did not continue on its own", counted["detail"])

    def test_a_manual_reinvocation_also_fails(self):
        counted = count_gestures(
            CLEAN_INPUTS + [{"input": "manual_reinvocation", "at": "2026-08-16T20:30:00Z"}]
        )
        self.assertFalse(counted["met"])

    def test_a_missing_canonical_gesture_fails(self):
        for omit in PRINCIPAL_GESTURES:
            with self.subTest(omitted=omit):
                counted = count_gestures(
                    [i for i in CLEAN_INPUTS if i["input"] != omit]
                )
                self.assertFalse(counted["met"])
                self.assertIn(omit, counted["detail"])

    def test_machine_continuation_cannot_be_recorded_as_a_gesture(self):
        with self.assertRaises(ReleaseMetricsError) as caught:
            count_gestures(
                CLEAN_INPUTS + [{"input": "machine_continuation", "at": "x"}]
            )
        self.assertIn("not a principal input", str(caught.exception))

    def test_an_input_without_a_timestamp_is_refused(self):
        with self.assertRaises(ReleaseMetricsError):
            count_gestures([{"input": "release_scope_locked"}])

    def test_the_extra_inputs_are_named_not_excused(self):
        self.assertEqual(set(EXTRA_INPUTS), {"manual_resume", "manual_reinvocation"})


class RefusalClassificationTests(unittest.TestCase):
    def setUp(self):
        self.baseline = load_refusal_baseline(STUDIO_ROOT)

    def test_known_classes_are_recognised(self):
        result = classify_refusals(
            ["R188-01-latent-index-debt", "R188-05-missing-leg-evidence"], self.baseline
        )
        self.assertEqual(result["unknown"], [])
        self.assertEqual(result["distinct_classes"], 2)

    def test_an_unknown_class_is_new_and_stays_new(self):
        result = classify_refusals(["R188-99-brand-new"], self.baseline)
        self.assertEqual(result["unknown"], ["R188-99-brand-new"])

    def test_occurrences_and_distinct_classes_are_counted_separately(self):
        """Five of one class and five of five are different releases."""
        result = classify_refusals(["R188-01-latent-index-debt"] * 5, self.baseline)
        self.assertEqual(result["occurrences"], 5)
        self.assertEqual(result["distinct_classes"], 1)

    def test_the_classification_records_which_baseline_judged_it(self):
        result = classify_refusals([], self.baseline)
        self.assertEqual(
            result["baseline_composite_sha256"], self.baseline["composite_sha256"]
        )


class ScorecardTests(unittest.TestCase):
    def setUp(self):
        self.baseline = load_refusal_baseline(STUDIO_ROOT)

    def card(self, **overrides):
        kwargs = dict(
            mode=REAL_FIRE,
            saga_id=SAGA,
            pipeline_run_uid=RUN,
            release_version="v1.89.0",
            principal_inputs=CLEAN_INPUTS,
            timestamps=dict(CLEAN_STAMPS),
            active_machine_seconds=412.5,
            observed_refusals=[],
            baseline=self.baseline,
        )
        kwargs.update(overrides)
        return build_scorecard(**kwargs)

    def test_a_clean_run_passes_and_validates(self):
        card = self.card()
        self.assertEqual(card["verdict"], "pass")
        self.assertEqual(validate_scorecard(card, SCHEMA), [])

    def test_elapsed_includes_the_human_waits(self):
        card = self.card()
        self.assertEqual(card["elapsed"]["lock_to_all_targets_live_seconds"], 1680.0)
        self.assertEqual(card["elapsed"]["active_machine_seconds"], 412.5)

    def test_a_manual_bridge_fails_the_verdict(self):
        card = self.card(
            principal_inputs=CLEAN_INPUTS
            + [{"input": "manual_resume", "at": "2026-08-16T20:22:00Z"}]
        )
        self.assertEqual(card["verdict"], "fail")
        self.assertEqual(validate_scorecard(card, SCHEMA), [])

    def test_an_unknown_refusal_fails_the_verdict(self):
        card = self.card(observed_refusals=["R188-99-brand-new"])
        self.assertEqual(card["verdict"], "fail")

    def test_a_known_refusal_does_not_by_itself_fail(self):
        card = self.card(observed_refusals=["R188-01-latent-index-debt"])
        self.assertEqual(card["verdict"], "pass")
        self.assertEqual(card["refusals"]["occurrences"], 1)

    def test_a_site_that_never_went_live_fails(self):
        stamps = dict(CLEAN_STAMPS, all_targets_live_at=None)
        card = self.card(timestamps=stamps)
        self.assertEqual(card["verdict"], "fail")
        self.assertIsNone(card["elapsed"]["lock_to_all_targets_live_seconds"])
        self.assertEqual(validate_scorecard(card, SCHEMA), [])

    def test_a_missing_timestamp_key_is_refused_not_defaulted(self):
        stamps = dict(CLEAN_STAMPS)
        del stamps["primary_live_at"]
        with self.assertRaises(ReleaseMetricsError) as caught:
            self.card(timestamps=stamps)
        self.assertIn("not a partial measurement", str(caught.exception))

    def test_the_verdict_cannot_be_supplied_by_the_caller(self):
        with self.assertRaises(TypeError):
            self.card(verdict="pass")

    def test_rehearsal_and_real_fire_have_separate_fixed_paths(self):
        run = Path("/tmp/run")
        self.assertEqual(
            scorecard_path(run, REHEARSAL).name, "one-prompt-rehearsal-scorecard.json"
        )
        self.assertEqual(
            scorecard_path(run, REAL_FIRE).name, "one-prompt-real-fire-scorecard.json"
        )
        self.assertNotEqual(
            scorecard_path(run, REHEARSAL), scorecard_path(run, REAL_FIRE)
        )

    def test_an_unknown_mode_refuses(self):
        with self.assertRaises(ReleaseMetricsError):
            scorecard_path(Path("/tmp/run"), "sort-of-real")


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.baseline = load_refusal_baseline(STUDIO_ROOT)
        self.card = build_scorecard(
            mode=REHEARSAL, saga_id=SAGA, pipeline_run_uid=RUN,
            release_version="v1.89.0", principal_inputs=CLEAN_INPUTS,
            timestamps=dict(CLEAN_STAMPS), active_machine_seconds=1.0,
            observed_refusals=[], baseline=self.baseline,
        )

    def test_the_schema_is_closed(self):
        card = dict(self.card)
        card["looks_fine"] = True
        findings = validate_scorecard(card, SCHEMA)
        self.assertTrue(findings, "an unexpected key validated; the schema is open")

    def test_a_missing_metric_block_is_invalid(self):
        for block in ("gestures", "timestamps", "elapsed", "refusals", "verdict"):
            with self.subTest(missing=block):
                card = {k: v for k, v in self.card.items() if k != block}
                self.assertTrue(
                    validate_scorecard(card, SCHEMA),
                    f"a scorecard missing {block} validated",
                )

    def test_a_bad_mode_is_invalid(self):
        card = dict(self.card, mode="dry-run-ish")
        self.assertTrue(validate_scorecard(card, SCHEMA))

    def test_the_schema_file_is_where_the_spec_maps_it(self):
        self.assertTrue(SCHEMA.is_file(), str(SCHEMA))

    def test_both_validation_paths_catch_the_same_core_defects(self):
        """The fallback runs on any machine without jsonschema, including Mike's.

        Two code paths mean one of them can rot unobserved. These cases run the
        structural fallback explicitly rather than relying on which library the
        test machine happens to have.
        """
        from lib import release_metrics as rm

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual(rm._structural_check(self.card, schema), [])

        with_extra = dict(self.card, looks_fine=True)
        self.assertTrue(
            rm._structural_check(with_extra, schema),
            "the fallback let an unexpected top-level key through",
        )

        for block in ("gestures", "timestamps", "elapsed", "refusals", "verdict"):
            with self.subTest(missing=block):
                trimmed = {k: v for k, v in self.card.items() if k != block}
                self.assertTrue(
                    rm._structural_check(trimmed, schema),
                    f"the fallback accepted a scorecard missing {block}",
                )

        bad_mode = dict(self.card, mode="dry-run-ish")
        self.assertTrue(rm._structural_check(bad_mode, schema))

        nested_extra = json.loads(json.dumps(self.card))
        nested_extra["refusals"]["fudge"] = 1
        self.assertTrue(
            rm._structural_check(nested_extra, schema),
            "the fallback did not close nested objects",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
