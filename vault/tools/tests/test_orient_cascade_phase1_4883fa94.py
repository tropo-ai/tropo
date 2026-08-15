"""Causal AC1–AC9 contract for orient() Cascade Phase 1 (dev-spec 4883fa94).

Every test here is MUTATION-SENSITIVE by design: it asserts on the mechanism
itself, so removing the mechanism — the wide draw, the complete roster, the
keyword provenance, the age output, the gateway preflight, the tier labels,
the evidence-scope wording — turns the matching class red. That is the AC9
"causal classes" requirement of the amended lock (Mike-approved lock break,
2026-08-13): tests that pass with the mechanism deleted are decoration.

The live studio is the fixture for the ReproductionTests because the spec's
AC7 names the real 2026-08-12 miss (root ``b1e7a2c3``, series ``5d4e135c`` and
``c933e1fa``); pure-function classes use in-memory records so they stay true
when the studio's data moves on.

Run (the spec's own commands):
    python3 -m unittest vault.tools.tests.test_orient_cascade_phase1_4883fa94
"""

import hashlib
import importlib.util
import json
import socket
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"


def _load_tool():
    """Import the hyphenated CLI module, registered so dataclasses resolve."""

    spec = importlib.util.spec_from_file_location(
        "orient_cascade_under_test", TOOLS / "tropo-orient.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["orient_cascade_under_test"] = module
    spec.loader.exec_module(module)
    return module


tool = _load_tool()

#: One live orientation, computed once — the spec's own reproduction root.
#: Class-level reuse keeps the suite honest AND affordable.
_LIVE = {}


def _live_answer():
    if "answer" not in _LIVE:
        _LIVE["answer"] = tool.orient("b1e7a2c3", 12, "7c017d1f")
    return _LIVE["answer"]


def _cli(*argv):
    return subprocess.run(
        [sys.executable, str(TOOLS / "tropo-orient.py"), *argv],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )


class DrawAndOrderTests(unittest.TestCase):
    """AC1 — draw max(8*k, 256), rank the full draw, display governed order."""

    def test_draw_budget_decouples_from_display_k(self):
        answer = _live_answer()
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["draw_budget"], max(8 * 12, 256))
        self.assertEqual(len(answer["items"]), 12)
        # The causal claim: the contest was wider than the display. Restoring
        # draw=k makes ranked_total collapse to k and this line turns red.
        self.assertGreater(answer["ranked_total"], 12)

    def test_display_is_governed_ranker_order_not_a_post_sort(self):
        answer = _live_answer()
        distances = [it["distance"] for it in answer["items"]
                     if isinstance(it.get("distance"), int)]
        # Under the governed ranker, this root's top-12 interleaves 1-hop and
        # 2-hop members. A restored distance-primary post-sort makes the
        # sequence monotonically non-decreasing — and turns this red.
        self.assertNotEqual(distances, sorted(distances),
                            "display order is distance-monotonic: an "
                            "orchestration post-sort has been restored")

    def test_explicit_draw_budget_flag_widens_the_contest(self):
        answer = tool.orient("b1e7a2c3", 5, "7c017d1f", draw_budget=64)
        self.assertEqual(answer["draw_budget"], 64)
        self.assertEqual(len(answer["items"]), 5)


class OneHopRosterTests(unittest.TestCase):
    """AC2 — the complete one-hop roster, independently re-derived."""

    def test_roster_equals_independent_graph_enumeration(self):
        answer = _live_answer()
        emitted = {row["uid"] for row in answer["one_hop"]["nodes"]}
        # Independent enumeration: straight over both index projections,
        # no tool helpers. Dropping any node from the roster turns red.
        records = {}
        for name in ("00-index.jsonl", "00-archive-index.jsonl"):
            path = ROOT / "vault" / name
            if not path.is_file():
                continue
            for line in path.read_text().splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                uid = str(rec.get("uid") or "")
                if uid and uid not in records:
                    records[uid] = rec
        task = records.get("b1e7a2c3") or {}
        parents = [str(u) for u in (task.get("member_of") or ())]
        expected = set()
        for uid, rec in records.items():
            if uid == "b1e7a2c3":
                continue
            member_of = [str(u) for u in (rec.get("member_of") or ())]
            if uid in parents or "b1e7a2c3" in member_of or (
                parents and any(p in member_of for p in parents)
            ):
                expected.add(uid)
        self.assertEqual(emitted, expected)
        self.assertEqual(answer["one_hop"]["total"], len(expected))

    def test_roster_rows_carry_disclosed_rank_or_say_unranked(self):
        answer = _live_answer()
        for row in answer["one_hop"]["nodes"]:
            self.assertIn("governed_rank", row)


class KeywordRecallTests(unittest.TestCase):
    """AC3 — deterministic keyword recall: provenance, honest totals, loud caps."""

    def test_every_hit_names_its_matched_terms(self):
        answer = _live_answer()
        recall = answer["keyword_recall"]
        self.assertTrue(recall["hits"])
        for hit in recall["hits"]:
            self.assertTrue(hit["terms_matched"],
                            f"{hit['uid']} carries no match provenance")

    def test_totals_stay_honest_when_lists_are_capped(self):
        answer = _live_answer()
        recall = answer["keyword_recall"]
        self.assertLessEqual(len(recall["hits"]), 200)
        self.assertGreaterEqual(recall["total"], len(recall["hits"]))
        if recall["total"] > 40:
            rendered = tool.render_text(answer)
            self.assertIn("more not shown", rendered)

    def test_terms_derive_from_task_title_and_tags(self):
        terms = tool._query_terms(
            {"title": "agentic-builders", "tags": ["launch-pillar"]}, ()
        )
        self.assertIn("agentic", terms)
        self.assertIn("builders", terms)
        self.assertIn("launch-pillar", terms)


class AgeVisibilityTests(unittest.TestCase):
    """AC4 — modified dates, stale flags, exact rendered-catalog age."""

    def test_catalog_fixture_reports_exact_age_against_known_clock(self):
        rec = {"subtype": "catalog", "modified": "2026-05-30"}
        self.assertEqual(tool._catalog_age_days(rec, "2026-08-13"), 75)
        # Removing the age mechanism (returning None) turns this red.
        self.assertIsNone(tool._catalog_age_days(
            {"modified": "2026-05-30"}, "2026-08-13"))

    def test_clock_ignores_template_placeholder_dates(self):
        records = {
            "a": {"modified": "2026-08-01"},
            "b": {"modified": "[YYYY-MM-DD]"},
        }
        self.assertEqual(tool._index_clock(records), "2026-08-01")

    def test_live_catalog_states_its_age_in_the_rendering(self):
        answer = _live_answer()
        catalog_rows = [r for r in answer["one_hop"]["nodes"]
                        if r.get("catalog_age_days") is not None]
        self.assertTrue(catalog_rows, "no rendered catalog carries an age")
        rendered = tool.render_text(answer)
        self.assertIn("days behind the newest index row", rendered)

    def test_rows_carry_normalised_dates(self):
        answer = _live_answer()
        for row in answer["one_hop"]["nodes"]:
            self.assertLessEqual(len(row["modified"]), 10)


class GatewayPreflightTests(unittest.TestCase):
    """AC5 — a missing gateway is named truthfully, before any hold."""

    def _gateway_open(self):
        try:
            socket.create_connection(("127.0.0.1", 8080), timeout=0.5).close()
            return True
        except OSError:
            return False

    def test_closed_gateway_refuses_by_name_and_spends_nothing(self):
        if self._gateway_open():
            self.skipTest("live metering gateway on 127.0.0.1:8080 — this "
                          "test only exercises the refusal branch and must "
                          "not spend")
        spend_dir = ROOT / "vault" / "loop-runs" / ".model-spend"
        before = {p.name: p.read_bytes() for p in spend_dir.glob("*.json")} \
            if spend_dir.is_dir() else {}
        result = _cli("--task", "b1e7a2c3", "--k", "3", "--read")
        self.assertIn("metering gateway is not accepting on 127.0.0.1:8080",
                      result.stdout)
        self.assertIn("THE READ DID NOT HAPPEN", result.stdout)
        after = {p.name: p.read_bytes() for p in spend_dir.glob("*.json")} \
            if spend_dir.is_dir() else {}
        self.assertEqual(before, after,
                         "the spend ledger changed on a refused preflight")


class DeterminismTests(unittest.TestCase):
    """AC6 — identical commands, byte-identical output."""

    def test_two_production_runs_share_a_sha256(self):
        first = _cli("--task", "b1e7a2c3", "--k", "8")
        second = _cli("--task", "b1e7a2c3", "--k", "8")
        self.assertEqual(first.returncode, 0)
        self.assertEqual(
            hashlib.sha256(first.stdout.encode()).hexdigest(),
            hashlib.sha256(second.stdout.encode()).hexdigest(),
        )


class ReproductionTests(unittest.TestCase):
    """AC7 — the 2026-08-12 miss cannot recur: both live series visible in
    complete evidence with disclosed governed rank; archived below active."""

    def test_both_named_series_appear_in_one_hop_evidence_with_rank(self):
        answer = _live_answer()
        rows = {r["uid"]: r for r in answer["one_hop"]["nodes"]}
        for uid in ("5d4e135c", "c933e1fa"):
            self.assertIn(uid, rows, f"live series {uid} missing from roster")
            self.assertIsNotNone(rows[uid]["governed_rank"],
                                 f"{uid} has no disclosed governed rank")
            self.assertFalse(rows[uid]["archived"])

    def test_both_named_series_appear_in_keyword_evidence(self):
        answer = _live_answer()
        hit_uids = {h["uid"] for h in answer["keyword_recall"]["hits"]}
        self.assertIn("5d4e135c", hit_uids)
        self.assertIn("c933e1fa", hit_uids)

    def test_archived_one_hop_projects_rank_below_active(self):
        answer = _live_answer()
        projects = [r for r in answer["one_hop"]["nodes"]
                    if r["type"] == "project" and r["governed_rank"]]
        active = [r["governed_rank"] for r in projects if not r["archived"]]
        archived = [r["governed_rank"] for r in projects if r["archived"]]
        self.assertTrue(active and archived)
        self.assertLess(max(active), min(archived))


class TierLabelTests(unittest.TestCase):
    """AC8 — which tiers ran, and the claim's scope, stated with the answer."""

    def test_deterministic_packet_states_scope_and_model_call_count(self):
        answer = _live_answer()
        rendered = tool.render_text(answer)
        self.assertIn("deterministic tiers only — 0 model calls", rendered)
        self.assertIn("orientation evidence only", rendered)
        self.assertIn("does not answer", rendered)
        self.assertIn(f"drew up to {answer['draw_budget']}", rendered)

    def test_json_packet_carries_both_budgets(self):
        answer = _live_answer()
        for key in ("draw_budget", "ranked_total", "k"):
            self.assertIn(key, answer)

    def test_evidence_scope_wording_never_claims_the_task_answered(self):
        rendered = tool.render_text(_live_answer())
        self.assertNotIn("task is answered", rendered.lower())
        self.assertIn("selecting evidence does not answer", rendered)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
