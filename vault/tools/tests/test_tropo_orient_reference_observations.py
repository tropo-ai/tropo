#!/usr/bin/env python3
"""Regression plants for Orient's indexed-member/reference partition."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import distiller as deterministic  # noqa: E402
from lib import task_circle as tc  # noqa: E402
from vault.tools.tests import test_distiller as legacy  # noqa: E402


def _load_cli():
    path = TOOLS / "tropo-orient.py"
    spec = importlib.util.spec_from_file_location("tropo_orient_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


class ArchivedUnionMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.current = self.root / "00-index.jsonl"
        self.archive = self.root / "00-archive-index.jsonl"
        self.current.write_text(
            json.dumps(
                {
                    "uid": "aaaa0001",
                    "title": "Current task",
                    "type": "task",
                    "status": "active",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.archive.write_text(
            json.dumps(
                {
                    "uid": "bbbb0002",
                    "title": "Archived architectural record",
                    "type": "decision",
                    "status": "done",
                    "state": "archived",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_archived_member_renders_with_real_union_metadata(self):
        member = tc.CircleMember("bbbb0002", 1, tc.REL_REF, "aaaa0001")
        ranked = SimpleNamespace(score=0.75)
        orientation = SimpleNamespace(
            items=(
                SimpleNamespace(
                    uid="bbbb0002", circle_member=member, ranked_member=ranked
                ),
            ),
            reference_observations=(),
        )
        result = SimpleNamespace(ok=True, value=orientation)

        with mock.patch.object(cli, "INDEX_JSONL", self.current), mock.patch.object(
            cli, "ARCHIVE_INDEX_JSONL", self.archive
        ), mock.patch.object(
            cli.vp.ViewerProjection, "from_repo_root", return_value=object()
        ), mock.patch.object(
            cli, "SqliteStructuralIndex", return_value=object()
        ), mock.patch.object(
            cli, "SqliteRankIndex", return_value=object()
        ), mock.patch.object(
            cli.distiller, "orient_deterministic", return_value=result
        ):
            answer = cli.orient("aaaa0001", 8, "7b921d17")

        self.assertTrue(answer["ok"])
        self.assertEqual(answer["task_title"], "Current task")
        self.assertEqual(
            answer["items"][0]["title"], "Archived architectural record"
        )
        self.assertEqual(answer["items"][0]["type"], "decision")
        self.assertEqual(answer["items"][0]["status"], "done")
        self.assertTrue(answer["items"][0]["indexed"])
        self.assertNotIn("not in the index", cli.render_text(answer))

    def test_sqlite_entries_row_is_admission_even_when_archived(self):
        database = self.root / "index.sqlite"
        connection = sqlite3.connect(database)
        connection.execute(
            "CREATE TABLE entries ("
            "uid TEXT PRIMARY KEY, type TEXT, status TEXT, state TEXT, fm_json TEXT)"
        )
        connection.execute(
            "CREATE TABLE edges (src_uid TEXT, rel TEXT, dst_uid TEXT)"
        )
        connection.execute(
            "INSERT INTO entries VALUES (?, ?, ?, ?, ?)",
            ("aaaa0001", "task", "active", "active", "{}"),
        )
        connection.execute(
            "INSERT INTO entries VALUES (?, ?, ?, ?, ?)",
            ("bbbb0002", "decision", "done", "archived", "{}"),
        )
        connection.execute(
            "INSERT INTO edges VALUES (?, ?, ?)",
            ("aaaa0001", "refs", "bbbb0002"),
        )
        connection.execute(
            "INSERT INTO edges VALUES (?, ?, ?)",
            ("aaaa0001", "refs", "deadbeef"),
        )
        connection.commit()
        connection.close()

        index = tc.SqliteStructuralIndex(database)
        self.assertEqual(index.structure("bbbb0002")["type"], "decision")
        self.assertIsNone(index.structure("deadbeef"))


class DeterministicObservationIsolationTests(unittest.TestCase):
    def setUp(self):
        self.roots = legacy._RootFactory()
        self.addCleanup(self.roots.cleanup)

    def fixture(self, unresolved_count):
        fx = legacy._OrientFixture(self.roots)
        fx.node("task0001", legacy.TEAM, type_="task", status="active")
        fx.node("real0001", legacy.TEAM, type_="capsule", status="locked")
        fx.node("real0002", legacy.TEAM, type_="note", status="active")
        fx.rel("task0001", "real0001", "refs")
        fx.rel("task0001", "real0002", "refs")
        for index in range(unresolved_count):
            target = f"e{index:07x}"
            fx._node_root[target] = self.roots.manifest_root(legacy.TEAM)
            fx.rel("task0001", target, "refs")
        return fx

    def orient(self, fx):
        return deterministic.orient_deterministic(
            "task0001",
            legacy.bob(),
            2,
            projection=fx.projection(),
            circle_index=fx.circle_index(),
            rank_index=fx.rank_index(),
        )

    def test_one_hundred_unresolved_refs_leave_ranked_output_and_scores_unchanged(self):
        baseline = self.orient(self.fixture(0))
        observed = self.orient(self.fixture(100))
        self.assertTrue(baseline.ok and observed.ok)

        baseline_scores = {
            item.uid: (item.score, item.breakdown, item.contributions)
            for item in baseline.value.items
        }
        observed_scores = {
            item.uid: (item.score, item.breakdown, item.contributions)
            for item in observed.value.items
        }
        self.assertEqual(observed.value.uids(), baseline.value.uids())
        self.assertEqual(
            observed.value.ranked.canonical(), baseline.value.ranked.canonical()
        )
        self.assertEqual(observed_scores, baseline_scores)
        self.assertEqual(len(observed.value.reference_observations), 100)
        self.assertTrue(
            all(
                item.classification == tc.REFERENCE_MISSING_INDEX_ENTRY
                for item in observed.value.reference_observations
            )
        )


class RendererSeparationAndEscapingTests(unittest.TestCase):
    HOSTILE = '"><script>alert("orient")</script>'

    def answer(self):
        return {
            "ok": True,
            "task": "aaaa0001",
            "task_title": "Current task",
            "items": [
                {
                    "uid": "bbbb0002",
                    "title": "Real indexed document",
                    "type": "decision",
                    "status": "done",
                    "why": "this work references it · 1 hop away",
                    "score": 0.75,
                    "stale": False,
                    "indexed": True,
                }
            ],
            "reference_observations": [
                {
                    "raw_target": self.HOSTILE,
                    "via": "aaaa0001",
                    "relation": tc.REL_REF,
                    "provenance": f"{tc.REL_REF}:aaaa0001",
                    "distance": 1,
                    "classification": tc.REFERENCE_NON_UID_OR_INVALID,
                }
            ],
        }

    def test_text_has_separate_observations_without_a_fake_vault_link(self):
        rendered = cli.render_text(self.answer())
        self.assertIn("REFERENCE OBSERVATIONS", rendered)
        self.assertIn(self.HOSTILE, rendered)
        self.assertIn("vault/files/bbbb0002.md", rendered)
        self.assertNotIn(f"vault/files/{self.HOSTILE}.md", rendered)

    def test_html_escapes_hostile_raw_text_and_never_links_observations(self):
        rendered = cli.render_board(self.answer())
        self.assertIn("<section class=\"observations\">", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn('href="../../vault/files/bbbb0002.md"', rendered)
        observation_section = rendered.split(
            '<section class="observations">', 1
        )[1].split("</section>", 1)[0]
        self.assertNotIn("<a ", observation_section)
        self.assertNotIn("vault/files/", observation_section)

    def test_cli_json_keeps_observations_out_of_ranked_items(self):
        output = io.StringIO()
        with mock.patch.object(
            sys, "argv", ["tropo-orient.py", "--task", "aaaa0001", "--json"]
        ), mock.patch.object(cli, "orient", return_value=self.answer()), contextlib.redirect_stdout(
            output
        ):
            self.assertEqual(cli.main(), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual([item["uid"] for item in payload["items"]], ["bbbb0002"])
        self.assertEqual(
            payload["reference_observations"][0]["raw_target"], self.HOSTILE
        )
        self.assertNotIn("raw_target", payload["items"][0])


if __name__ == "__main__":
    unittest.main()
