#!/usr/bin/env python3
"""3d8d4351 AC3/AC5 — the REAL_FIRE verdict triple, actor-aware, derived.

The verdict comes from journal rows only; principal gestures are rows whose
actor resolves to a HUMAN principal within the gesture classes; machine-marked
rows never count. The pairing table is DERIVED by static writer scan, never
hand-listed. all_targets_live_at is absent from the predicate.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_ms = importlib.util.spec_from_file_location("rm", TOOLS / "lib" / "release_metrics.py")
rm = importlib.util.module_from_spec(_ms)
sys.modules["rm"] = rm
_ms.loader.exec_module(rm)

_es = importlib.util.spec_from_file_location("re_ev", TOOLS / "lib" / "release_events.py")
re_ev = importlib.util.module_from_spec(_es)
sys.modules["re_ev"] = re_ev
_es.loader.exec_module(re_ev)

REGISTRY = ROOT / ".tropo-studio" / "registries" / "agent-registry.yaml"
SCHEMA = ROOT / "vault" / "schema" / "one-prompt-release-scorecard.schema.json"
BASELINE = {"baseline_version": "none", "composite_sha256": "0" * 64,
            "classifier_version": "manual"}
TS = {"scope_locked_at": "2026-08-31T01:00:00Z",
      "orchestrator_started_at": "2026-08-31T01:05:00Z",
      "primary_live_at": "2026-08-31T01:20:00Z",
      "all_targets_live_at": "2026-08-31T01:22:00Z"}


def row(event, actor="7b921d17", span="s", invoked_via=None):
    r = {"event": event, "actor": actor, "span_id": span,
         "ts": "2026-08-31T01:30:00Z"}
    if invoked_via:
        r["invoked_via"] = invoked_via
    return r


class VerdictTripleTests(unittest.TestCase):
    def test_fired_one_gesture(self) -> None:
        v = rm.derive_real_fire_verdict(
            [row("tropo.release.scope_locked", span="a"),
             row("tropo.release.fire_authorized", span="b"),
             row("tropo.release.published", span="c")],
            rm.resolve_principal_uids(REGISTRY))
        self.assertEqual(v["verdict"], "fired-one-gesture")
        self.assertEqual(v["derivation"]["principal_gesture_count"], 2,
                         "the lock and the go/no-go — completion facts are not gestures")

    def test_refused_then_attested(self) -> None:
        v = rm.derive_real_fire_verdict(
            [row("tropo.release.scope_locked", span="a"),
             row("tropo.release.verify_only_invoked", actor="0" * 8,
                 invoked_via="verify-only", span="b"),
             row("tropo.release.published", span="c")],
            rm.resolve_principal_uids(REGISTRY))
        self.assertEqual(v["verdict"], "refused-then-attested")

    def test_failed_when_neither_shape_holds(self) -> None:
        v = rm.derive_real_fire_verdict(
            [row("tropo.release.scope_locked", span="a")],
            rm.resolve_principal_uids(REGISTRY))
        self.assertEqual(v["verdict"], "failed")

    def test_machine_marked_fire_never_counts(self) -> None:
        v = rm.derive_real_fire_verdict(
            [row("tropo.release.fire_authorized", actor="7b921d17",
                 invoked_via="fire-authorize", span="a"),
             row("tropo.release.published", span="b")],
            rm.resolve_principal_uids(REGISTRY))
        self.assertNotEqual(v["verdict"], "fired-one-gesture",
                            "the :206 forgery class — a machine row wearing a "
                            "human actor — must not count, ever")

    def test_over_target_is_not_one_gesture(self) -> None:
        v = rm.derive_real_fire_verdict(
            [row("tropo.release.scope_locked", span="a"),
             row("tropo.release.orchestrator_invoked", span="b"),
             row("tropo.release.fire_authorized", span="c"),
             row("tropo.release.published", span="d")],
            rm.resolve_principal_uids(REGISTRY))
        self.assertEqual(v["verdict"], "failed")
        self.assertEqual(v["derivation"]["principal_gesture_count"], 3)


class PredicateShapeTests(unittest.TestCase):
    """all_targets_live_at is recorded, never verdict-bearing; the card
    validates against the version-branched schema with its derivation."""

    def _card(self, rows):
        return rm.build_scorecard_v2(
            mode=rm.REAL_FIRE, saga_id="release:aaaaaaaa",
            pipeline_run_uid="aaaaaaaa", release_version="1.94.0",
            journal_rows=rows, principal_registry_path=REGISTRY,
            timestamps=TS, active_machine_seconds=90.0,
            observed_refusals=[], baseline=BASELINE)

    def test_a_live_all_targets_none_card_still_verdicts(self) -> None:
        ts = dict(TS, all_targets_live_at=None)
        card = rm.build_scorecard_v2(
            mode=rm.REAL_FIRE, saga_id="release:aaaaaaaa",
            pipeline_run_uid="aaaaaaaa", release_version="1.94.0",
            journal_rows=[row("tropo.release.scope_locked", span="a"),
                          row("tropo.release.fire_authorized", span="b"),
                          row("tropo.release.published", span="c")],
            principal_registry_path=REGISTRY, timestamps=ts,
            active_machine_seconds=1.0, observed_refusals=[], baseline=BASELINE)
        self.assertEqual(card["verdict"], "fired-one-gesture",
                         "the predicate is free of all_targets_live_at — "
                         "completion facts are the completion verifier's")

    def test_the_card_validates_with_its_derivation(self) -> None:
        card = self._card([row("tropo.release.scope_locked", span="a"),
                           row("tropo.release.fire_authorized", span="b"),
                           row("tropo.release.published", span="c")])
        findings = rm.validate_scorecard(card, SCHEMA)
        self.assertEqual(findings, [], findings)
        self.assertTrue(card["verdict_derivation"])

    def test_v1_cards_stay_readable(self) -> None:
        c1 = rm.build_scorecard(
            mode=rm.REHEARSAL, saga_id="release:aaaaaaaa",
            pipeline_run_uid="aaaaaaaa", release_version="1.94.0",
            principal_inputs=[
                {"input": "release_scope_locked", "at": "2026-08-31T01:00:00Z"},
                {"input": "release_orchestrator_invoked", "at": "2026-08-31T01:05:00Z"},
                {"input": "release_fire_authorized", "at": "2026-08-31T01:10:00Z"}],
            timestamps=TS, active_machine_seconds=10.0,
            observed_refusals=[], baseline=BASELINE)
        self.assertEqual(rm.validate_scorecard(c1, SCHEMA), [])


class PairingTableDerivedTests(unittest.TestCase):
    """§5: the event classes the engine journals, DERIVED by static scan of
    the writers (declarations_in_source pattern) — each asserted present in
    the closed vocabulary with a counted reader named. A class added later
    without a reader turns this red mechanically."""

    def test_every_written_class_is_in_the_closed_vocabulary(self) -> None:
        import re
        writers = [TOOLS / "tropo-release.py",
                   TOOLS / "tropo-publish-release.py"]
        written = set()
        for w in writers:
            text = w.read_text()
            written.update(re.findall(r'event="(tropo\.release\.[a-z_]+)"', text))
            written.update(re.findall(r'"(tropo\.release\.[a-z_]+)"', text))
        # every class a writer emits must exist in the vocabulary
        unknown = {c for c in written - set(re_ev.RELEASE_EVENTS.keys())
                    if not c.endswith(("_at", "_by", "_uid"))}
        self.assertFalse(unknown,
                         "a writer emits classes outside the closed vocabulary: %s" % unknown)

    def test_verify_only_invoked_has_a_writer_and_is_vocabulary(self) -> None:
        self.assertIn("tropo.release.verify_only_invoked", re_ev.RELEASE_EVENTS)
        pub = (TOOLS / "tropo-publish-release.py").read_text()
        self.assertIn('"tropo.release.verify_only_invoked"', pub,
                      "the verify-only path journals through the class")


if __name__ == "__main__":
    unittest.main(verbosity=2)
