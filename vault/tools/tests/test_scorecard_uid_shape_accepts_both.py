"""The scorecard schema's two uid patterns must agree with the shape authority.

v1.95 close (talos-t64, 2026-09-07, metis-g123's blocker _00000223). The
scorecard schema hard-coded `^release:[0-9a-f]{8}$` and `^[0-9a-f]{8}$`, so it
could not validate a release opened after the composite mint flip of
2026-08-31. Run f015af4a6a0a is 12 hex: `tropo-release.py rehearse` exited 3
with exactly those two mismatches and nothing else, and the fire preflight
refuses on an invalid scorecard because the saga cannot close after the fire.

JSON Schema cannot import Python, so the schema carries a literal. This file is
what keeps that literal honest: it DERIVES the expected alternation from
`governed_path.UID_SHAPES` and asserts the schema matches. A future shape flip
that forgets this file's subject fails here, loudly, instead of surfacing as an
unvalidatable scorecard on some later release night.

The value tests are the negative control metis-g123 specified: 12-hex must
validate (it did not before), 8-hex must still validate (legacy is first-class
forever, never migrated), and 11-hex and 13-hex must fail both ways.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = STUDIO_ROOT / "vault" / "schema" / "one-prompt-release-scorecard.schema.json"
LIB = STUDIO_ROOT / "vault" / "tools" / "lib"


def _governed_path():
    if str(LIB) not in sys.path:
        sys.path.insert(0, str(LIB))
    import governed_path  # noqa: PLC0415
    return governed_path


def _release_metrics():
    spec = importlib.util.spec_from_file_location(
        "release_metrics_scorecard_uid", LIB / "release_metrics.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SchemaAgreesWithTheShapeAuthority(unittest.TestCase):
    """The literal in the JSON is derived from UID_SHAPES, not typed by hand."""

    def setUp(self) -> None:
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.props = self.schema["properties"]
        shapes = _governed_path().UID_SHAPES
        self.alternation = "|".join(
            "[0-9a-f]{%d}" % n for n in sorted(shapes, reverse=True))

    def test_pipeline_run_uid_pattern_is_the_derived_alternation(self) -> None:
        self.assertEqual(
            self.props["pipeline_run_uid"]["pattern"],
            "^(?:%s)$" % self.alternation,
            "the schema's uid pattern and governed_path.UID_SHAPES disagree; "
            "the shape fact has one home and this literal is derived from it",
        )

    def test_saga_id_pattern_is_the_derived_alternation(self) -> None:
        self.assertEqual(
            self.props["saga_id"]["pattern"],
            "^release:(?:%s)$" % self.alternation,
        )

    def test_both_patterns_name_the_one_home(self) -> None:
        """A literal without a pointer home is how the next flip gets missed."""
        for field in ("saga_id", "pipeline_run_uid"):
            self.assertIn("governed_path", self.props[field]["description"])


class TheValuesThatMustAndMustNotMatch(unittest.TestCase):
    """metis-g123's negative control, run against the schema's own patterns."""

    def setUp(self) -> None:
        props = json.loads(SCHEMA.read_text(encoding="utf-8"))["properties"]
        self.run_re = re.compile(props["pipeline_run_uid"]["pattern"])
        self.saga_re = re.compile(props["saga_id"]["pattern"])

    def test_the_composite_uid_of_this_very_run_validates(self) -> None:
        self.assertIsNotNone(self.run_re.fullmatch("f015af4a6a0a"))
        self.assertIsNotNone(self.saga_re.fullmatch("release:f015af4a6a0a"))

    def test_legacy_eight_hex_still_validates(self) -> None:
        """8-hex is first-class forever; accepts-both means BOTH."""
        self.assertIsNotNone(self.run_re.fullmatch("a190f1e7"))
        self.assertIsNotNone(self.saga_re.fullmatch("release:a190f1e7"))

    def test_eleven_and_thirteen_hex_still_fail(self) -> None:
        """The cure widens to two declared shapes, not to any hex length."""
        for bad in ("f015af4a6a0", "f015af4a6a0ab"):
            self.assertIsNone(self.run_re.fullmatch(bad), bad)
            self.assertIsNone(self.saga_re.fullmatch("release:" + bad), bad)

    def test_uppercase_is_refused_because_this_is_admission(self) -> None:
        """governed_path: admission is lowercase-exact. A case-insensitive
        match here would let two spellings of one identity both validate."""
        self.assertIsNone(self.run_re.fullmatch("F015AF4A6A0A"))

    def test_a_non_uid_string_still_fails(self) -> None:
        self.assertIsNone(self.run_re.fullmatch("run-v190-fireint"))


class TheValidatorActuallyEvaluatesThesePatterns(unittest.TestCase):
    """A pattern nothing evaluates is a rule that cannot refuse anything.

    jsonschema is not installed in this studio, so validate_scorecard takes the
    structural fallback -- which enforces `pattern` only because argus-a158
    added it (2026-08-25) after an invalid real-fire card validated clean. This
    asserts the seam still holds, through the production entry point.
    """

    def test_a_bad_uid_is_reported_through_validate_scorecard(self) -> None:
        metrics = _release_metrics()
        card = {"schema_version": 2, "pipeline_run_uid": "not-a-uid"}
        findings = metrics.validate_scorecard(card, SCHEMA)
        self.assertTrue(
            any("pipeline_run_uid" in f for f in findings),
            "the validator did not evaluate the uid pattern at all: %r" % (findings,),
        )

    def test_this_runs_composite_uid_is_not_reported(self) -> None:
        metrics = _release_metrics()
        card = {"schema_version": 2, "pipeline_run_uid": "f015af4a6a0a"}
        findings = metrics.validate_scorecard(card, SCHEMA)
        self.assertFalse(
            [f for f in findings if "pipeline_run_uid" in f],
            "the composite uid this release runs on is still refused: %r" % (findings,),
        )


if __name__ == "__main__":
    unittest.main()
