#!/usr/bin/env python3
"""The scorecard seam: the reader must read where the writer actually writes.

WHY THIS FILE EXISTS. The real-fire scorecard could not be valid in this Studio's
entire history, and the cause was not a bug in the scorecard — it was two seams
where a reader and a writer were never introduced:

  1. `_observed_refusals` looked for `read_refusals_for()`, a function defined
     nowhere, on a module whose queue is IN-MEMORY and process-local. The refusal
     records live on the durable telemetry lane the drainer writes.
  2. `_journal_timestamps` read only `run.jsonl`. `tropo.release.scope_locked` is
     emitted to the canonical event bus and has appeared in a release run journal
     ZERO times across every run this Studio has ever produced. The schema types
     `scope_locked_at` as non-nullable, so the card was invalid before it was
     written.

Both were invisible because nothing exercised the seam end to end: each side had
tests, built in its own shape, and the join between them had none. That is the
sixteenth instance of this defect class in the Argus lineage's records, and this
file exists so the seventeenth is not this one again.

Every test here pairs a positive with a negative. A join that "recovers" a stamp
for any run id is not a join, and a reader that returns [] for an unreadable store
is asserting a measurement it never took.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
STUDIO = TOOLS.parents[1]

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load_release_module():
    spec = importlib.util.spec_from_file_location(
        "trel_seam", TOOLS / "tropo-release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _studio(tmp: Path) -> Path:
    (tmp / "vault" / "events" / "streams").mkdir(parents=True)
    (tmp / ".tropo-studio" / "telemetry" / "shards").mkdir(parents=True)
    return tmp


def _write_stream(tmp: Path, rows) -> None:
    path = tmp / "vault" / "events" / "streams" / "stream-a.jsonl"
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_run_journal(run_dir: Path, rows) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


RUN_UID = "42261546"


class TheTimestampJoinReadsBothStores(unittest.TestCase):
    """scope_locked lives on the bus; the other moments live in the journal."""

    def setUp(self) -> None:
        self.m = _load_release_module()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = _studio(Path(self._tmp.name))
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = self.tmp / "run"
        # The journal carries orchestrator_invoked and completion_verified, and
        # deliberately NOT scope_locked — which is the real-world shape: zero
        # release run journals in this Studio have ever contained it.
        _write_run_journal(self.run_dir, [
            {"event": "tropo.release.orchestrator_invoked",
             "ts": "2026-08-25T18:00:00Z",
             "data": {"pipeline_run_uid": RUN_UID}},
            {"event": "tropo.release.published",
             "ts": "2026-08-25T18:10:00Z",
             "data": {"pipeline_run_uid": RUN_UID}},
            {"event": "tropo.release.completion_verified",
             "ts": "2026-08-25T18:12:00Z",
             "data": {"pipeline_run_uid": RUN_UID}},
        ])
        _write_stream(self.tmp, [
            {"type": "tropo.release.scope_locked",
             "time": "2026-08-25T17:41:05Z",
             "data": {"pipeline_run_uid": RUN_UID,
                      "release_plan_uid": "088e21aa"}},
        ])

    def test_the_journal_alone_cannot_see_scope_locked(self) -> None:
        """The 'before' state, pinned. If this ever passes, the premise moved."""
        stamps = self.m._journal_timestamps(self.run_dir)
        self.assertIsNone(
            stamps["scope_locked_at"],
            "scope_locked is a bus event; a journal-only read must not find it")

    def test_the_join_recovers_scope_locked_from_the_bus(self) -> None:
        stamps = self.m._journal_timestamps(
            self.run_dir, {"pipeline_run_uid": RUN_UID}, self.tmp)
        self.assertEqual(stamps["scope_locked_at"], "2026-08-25T17:41:05Z")

    def test_all_four_moments_are_present_after_the_join(self) -> None:
        """The card cannot validate without all four; this is that precondition."""
        stamps = self.m._journal_timestamps(
            self.run_dir, {"pipeline_run_uid": RUN_UID}, self.tmp)
        for key in ("scope_locked_at", "orchestrator_started_at",
                    "primary_live_at", "all_targets_live_at"):
            with self.subTest(stamp=key):
                self.assertIsNotNone(stamps[key])

    def test_the_join_is_a_join_and_not_a_time_window(self) -> None:
        """The negative half. A bus scan without the correlation would happily
        stamp another release's lock onto this card."""
        stamps = self.m._journal_timestamps(
            self.run_dir, {"pipeline_run_uid": "deadbeef"}, self.tmp)
        self.assertIsNone(
            stamps["scope_locked_at"],
            "a different run's lock must never land on this run's card")

    def test_completion_verified_supplies_all_targets_live(self) -> None:
        """It had NO source event before; the stamp was structurally None."""
        _write_run_journal(self.run_dir, [
            {"event": "tropo.release.completion_verified",
             "ts": "2026-08-25T18:12:00Z",
             "data": {"pipeline_run_uid": RUN_UID}},
        ])
        stamps = self.m._journal_timestamps(self.run_dir)
        self.assertEqual(stamps["all_targets_live_at"], "2026-08-25T18:12:00Z")


class TheRefusalReaderReadsTheDurableLane(unittest.TestCase):
    """Not the producer's in-memory queue, which is empty in this process."""

    def setUp(self) -> None:
        self.m = _load_release_module()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = _studio(Path(self._tmp.name))
        self.addCleanup(self._tmp.cleanup)
        shard = self.tmp / ".tropo-studio" / "telemetry" / "shards" / "s.jsonl"
        shard.write_text("\n".join(json.dumps(r) for r in [
            {"id": "build:20260825T170000:refused:1",
             "time": "2026-08-25T17:00:00Z",
             "data": {"outcome": "refused", "event_time_utc": "2026-08-25T17:00:00Z"}},
            {"id": "build:20260825T180000:refused:1",
             "time": "2026-08-25T18:00:00Z",
             "data": {"outcome": "refused", "event_time_utc": "2026-08-25T18:00:00Z"}},
            {"id": "build:20260825T190000:ok:1",
             "time": "2026-08-25T19:00:00Z",
             "data": {"outcome": "succeeded", "event_time_utc": "2026-08-25T19:00:00Z"}},
        ]) + "\n", encoding="utf-8")

    def test_it_finds_refusals_inside_the_window(self) -> None:
        found = self.m._observed_refusals(
            {}, self.tmp,
            window_start="2026-08-25T16:00:00Z",
            window_end="2026-08-25T20:00:00Z")
        self.assertEqual(len(found), 2, found)

    def test_it_counts_only_refusals_not_every_record(self) -> None:
        found = self.m._observed_refusals(
            {}, self.tmp,
            window_start="2026-08-25T16:00:00Z",
            window_end="2026-08-25T20:00:00Z")
        self.assertTrue(all("refused" in f for f in found), found)

    def test_the_window_actually_bounds(self) -> None:
        """The negative half: without this, 'it found some' proves nothing."""
        found = self.m._observed_refusals(
            {}, self.tmp,
            window_start="2020-01-01T00:00:00Z",
            window_end="2020-01-02T00:00:00Z")
        self.assertEqual(found, [])

    def test_an_unreadable_lane_is_None_and_never_empty_list(self) -> None:
        """None means NOT RECORDED. [] asserts none occurred. Conflating them is
        how a scorecard reports a clean night nobody measured."""
        found = self.m._observed_refusals({}, self.tmp / "no-such-studio")
        self.assertIsNone(found)


class TheStructuralFallbackEnforcesScalars(unittest.TestCase):
    """jsonschema is absent on every machine here, so the fallback IS the
    validator. It used to skip type/minLength/pattern entirely."""

    def setUp(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "rel_metrics_seam", TOOLS / "lib" / "release_metrics.py")
        self.metrics = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.metrics)

    def _check(self, value, schema):
        return self.metrics._structural_check(value, schema)

    def test_empty_string_fails_minlength(self) -> None:
        """`release_version: ""` — the exact value a real fire produced."""
        self.assertTrue(self._check("", {"type": "string", "minLength": 1}))

    def test_a_valid_string_passes_minlength(self) -> None:
        self.assertEqual(self._check("1.92.0", {"type": "string", "minLength": 1}), [])

    def test_null_fails_a_non_nullable_string(self) -> None:
        """`scope_locked_at: null` — the other value a real fire produced."""
        self.assertTrue(self._check(None, {"type": "string"}))

    def test_null_passes_where_the_schema_allows_it(self) -> None:
        self.assertEqual(self._check(None, {"type": ["string", "null"]}), [])

    def test_pattern_is_enforced(self) -> None:
        schema = {"type": "string", "pattern": r"^[0-9a-f]{8}$"}
        self.assertTrue(self._check("run-v190-fireint", schema))
        self.assertEqual(self._check("a190f1e7", schema), [])

    def test_a_bool_is_not_an_integer(self) -> None:
        """bool subclasses int in Python; a naive isinstance check passes True
        as a count."""
        self.assertTrue(self._check(True, {"type": "integer"}))


if __name__ == "__main__":
    unittest.main()
