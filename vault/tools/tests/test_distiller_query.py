#!/usr/bin/env python3
"""Cut 4A viewer-safe query and hidden-hit byte-identity plants."""
from __future__ import annotations

import inspect
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from vault.tools.tests import test_distiller as legacy

import lib.distiller_query as dq
import lib.metered_model as mm


SNAPSHOT = "snapshot-query-1"


class QueryCase(unittest.TestCase):
    def setUp(self) -> None:
        self.roots = legacy._RootFactory()
        self.addCleanup(self.roots.cleanup)

    def fixture(self, visible=(), hidden=()):
        fx = legacy._OrientFixture(self.roots)
        fx.node("task0001", legacy.TEAM, type_="task", status="active")
        for uid in visible:
            fx.node(uid, legacy.TEAM, type_="note", status="active")
        for uid in hidden:
            fx.node(uid, legacy.PRIV_ALICE, type_="note", status="active")
        return fx

    def sqlite_query(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "index.sqlite"
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE VIRTUAL TABLE entries_fts USING fts5(uid UNINDEXED, title, body)"
        )
        conn.executemany("INSERT INTO entries_fts VALUES (?,?,?)", rows)
        conn.commit()
        conn.close()
        return dq.SqliteQueryIndex(path, index_as_of=SNAPSHOT), path


class ViewerSafeProposalTests(QueryCase):
    def test_hidden_unknown_and_absent_proposals_are_observationally_identical(self):
        fx = self.fixture(visible=("visible1",), hidden=("hidden01",))
        query = dq.InMemoryQueryIndex({}, index_as_of=SNAPSHOT)

        outputs = []
        for proposals in (
            ("visible1",),
            ("hidden01", "visible1"),
            ("unknown1", "visible1"),
            ("hidden01", "unknown1", "visible1"),
        ):
            result = dq.resolve_query(
                "intent",
                legacy.bob(),
                SNAPSHOT,
                projection=fx.projection(),
                query_index=query,
                parse_double=lambda **_kwargs: dq.QueryProposal(proposals),
            )
            self.assertTrue(result.ok, msg=result.error)
            outputs.append(result.value.canonical())
        self.assertEqual(len(set(outputs)), 1)
        self.assertNotIn("hidden01", outputs[0])
        self.assertNotIn("unknown1", outputs[0])

    def test_parse_double_is_constrained_and_invalid_paths_fall_back(self):
        fx = self.fixture(visible=("visible1",), hidden=("hidden01",))
        query = dq.InMemoryQueryIndex(
            {"visible1": "relevant intent"}, index_as_of=SNAPSHOT
        )

        def raises(**_kwargs):
            raise RuntimeError("local double failure")

        for parse_double in (
            None,
            raises,
            lambda **_kwargs: {"uids": ["visible1"]},
            lambda **_kwargs: ("hidden01",),
            lambda **_kwargs: ("visible1", 7),
        ):
            with self.subTest(parse_double=parse_double):
                result = dq.resolve_query(
                    "relevant intent",
                    legacy.bob(),
                    SNAPSHOT,
                    projection=fx.projection(),
                    query_index=query,
                    parse_double=parse_double,
                )
                self.assertTrue(result.ok, msg=result.error)
                self.assertEqual(result.value.uids, ("visible1",))
                self.assertTrue(result.value.fallback_used)


class ParseModelAdapterTests(QueryCase):
    @staticmethod
    def model_result(text):
        return mm.MeteredModelResult(
            text=text,
            model="claude-haiku-4-5-20251001",
            usage={"input_tokens": 1, "output_tokens": 1},
            receipt=mm.ModelReceipt(
                "a1b2c3d4",
                "2026-07-23",
                "0c938a95",
                "1.0.0",
                "abcd1234",
                "parse-query",
                "claude-haiku-4-5-20251001",
                ("team",),
                1,
                1,
            ),
        )

    def test_closed_model_uids_still_cross_total_viewer_filter(self):
        fx = self.fixture(visible=("a0000001",), hidden=("b0000001",))

        def call_model(*_args, **_kwargs):
            return self.model_result(
                json.dumps({"uids": ["b0000001", "a0000001"]})
            )

        adapter = dq.ParseQueryModelAdapter(
            run_binding=object(),
            segment_class="team",
            call_model=call_model,
        )
        result = dq.resolve_query(
            "needle",
            legacy.bob(),
            SNAPSHOT,
            projection=fx.projection(),
            query_index=dq.InMemoryQueryIndex({}, index_as_of=SNAPSHOT),
            parse_double=adapter,
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(result.value.uids, ("a0000001",))
        self.assertFalse(result.value.fallback_used)

    def test_denied_and_malformed_model_outputs_equal_fts_fallback(self):
        fx = self.fixture(visible=("a0000001",))
        query = dq.InMemoryQueryIndex(
            {"a0000001": "needle"},
            index_as_of=SNAPSHOT,
        )
        baseline = dq.resolve_query(
            "needle",
            legacy.bob(),
            SNAPSHOT,
            projection=fx.projection(),
            query_index=query,
        ).value.canonical()
        outputs = (
            mm.ModelRefusal("CONSENT_DENIED", "ask"),
            self.model_result("{"),
            self.model_result('{"uids":["not-a-uid"]}'),
            self.model_result('{"uids":[],"extra":true}'),
        )
        for output in outputs:
            with self.subTest(output=output):
                adapter = dq.ParseQueryModelAdapter(
                    call_model=lambda *_args, value=output, **_kwargs: value,
                )
                result = dq.resolve_query(
                    "needle",
                    legacy.bob(),
                    SNAPSHOT,
                    projection=fx.projection(),
                    query_index=query,
                    parse_double=adapter,
                )
                self.assertTrue(result.ok, msg=result.error)
                self.assertEqual(result.value.canonical(), baseline)


class FullThenFilteredFtsTests(QueryCase):
    def resolve_with_hidden(
        self,
        hidden_count: int,
        *,
        visible=("visible1", "visible2"),
        seed_limit=16,
    ):
        hidden = tuple(f"hidden{i:02d}" for i in range(hidden_count))
        fx = self.fixture(visible=visible, hidden=hidden)
        rows = [
            *[(uid, "needle", f"visible body {uid}") for uid in reversed(visible)],
            *[(uid, "needle", f"hidden body {uid}") for uid in hidden],
        ]
        query, path = self.sqlite_query(rows)
        raw_count = sqlite3.connect(path).execute(
            "SELECT count(*) FROM entries_fts WHERE entries_fts MATCH 'needle'"
        ).fetchone()[0]
        result = dq.resolve_query(
            "needle",
            legacy.bob(),
            SNAPSHOT,
            projection=fx.projection(),
            query_index=query,
            seed_limit=seed_limit,
        )
        self.assertTrue(result.ok, msg=result.error)
        return raw_count, result.value

    def test_zero_one_many_hidden_hits_leave_visible_seed_bytes_identical(self):
        outputs = []
        counts = []
        for hidden_count in (0, 1, 7):
            raw_count, seeds = self.resolve_with_hidden(
                hidden_count, visible=("visible1",)
            )
            counts.append(raw_count)
            outputs.append(seeds.canonical())
            self.assertEqual(seeds.uids, ("visible1",))
            self.assertTrue(seeds.fallback_used)
        self.assertEqual(counts, [1, 2, 8])
        self.assertEqual(len(set(outputs)), 1)

    def test_limit_is_applied_after_visibility_filter_and_stable_sort(self):
        for hidden_count in (0, 9):
            _count, seeds = self.resolve_with_hidden(hidden_count, seed_limit=1)
            self.assertEqual(seeds.uids, ("visible1",))

    def test_sql_source_has_no_prefilter_observable_operators(self):
        search_sql = inspect.getsource(dq.SqliteQueryIndex.search_uids)
        for forbidden in ("LIMIT", "OFFSET", "snippet(", "bm25(", "count("):
            self.assertNotIn(forbidden, search_sql)


class QueryNormalizationAndBindingTests(QueryCase):
    def test_terms_are_normalized_deduplicated_sorted_and_fts_safe(self):
        self.assertEqual(
            dq.normalize_query_terms('  Beta alpha ALPHA "or" café  '),
            ("alpha", "beta", "café", "or"),
        )

    def test_empty_intent_is_an_explicit_no_seed_nonfallback(self):
        fx = self.fixture()
        result = dq.resolve_query(
            "   ",
            legacy.bob(),
            SNAPSHOT,
            projection=fx.projection(),
            query_index=dq.InMemoryQueryIndex({}, index_as_of=SNAPSHOT),
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(result.value.uids, ())
        self.assertFalse(result.value.fallback_used)

    def test_query_index_snapshot_mismatch_refuses_before_double(self):
        fx = self.fixture(visible=("visible1",))
        calls = []

        def parse(**_kwargs):
            calls.append(True)
            return ("visible1",)

        result = dq.resolve_query(
            "intent",
            legacy.bob(),
            SNAPSHOT,
            projection=fx.projection(),
            query_index=dq.InMemoryQueryIndex({}, index_as_of="other"),
            parse_double=parse,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, dq.QueryErrorCode.BINDING_MISMATCH)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
