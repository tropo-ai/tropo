"""Librarian L1 causal contract (dev-spec d317f532).

Mutation-sensitive by design: removing the mechanism turns the matching test
red. FeedArtifactTests covers AC1 (roster parity, budget honesty, determinism);
SkillContractTests covers AC2 (the contract phrases, verbatim).

Run (the spec's own commands):
    python3 -m unittest vault.tools.tests.test_librarian_l1_d317f532
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
SKILL = ROOT / "vault" / "skills" / "tropo-librarian.md"

#: The live task the spec's measurement window runs on — the same root every
#: orient() causal suite already uses, so index churn cannot strand this file.
TASK = "b1e7a2c3"


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "librarian_tool_under_test", TOOLS / "tropo-orient.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["librarian_tool_under_test"] = module
    spec.loader.exec_module(module)
    return module


tool = _load_tool()

_CACHE = {}


def _answer():
    if "a" not in _CACHE:
        _CACHE["a"] = tool.orient(TASK, 8, "7c017d1f")
    return _CACHE["a"]


class FeedArtifactTests(unittest.TestCase):
    """AC1 — one artifact: evidence + budgeted bodies, honestly accounted."""

    def test_task_own_body_leads_the_feed(self):
        # A task is not its own graph neighbour; ranking alone omits the one
        # document every question is about. The librarian's first live
        # exchange found this — the fix is permanent and this test is causal.
        answer = _answer()
        feed = tool.render_librarian_feed(answer, 400_000)
        self.assertIn(f"### {TASK} · vault/files/{TASK}.md · THE TASK ITSELF",
                      feed)
        first_body = feed.index("### ")
        self.assertEqual(feed[first_body:first_body + 12], f"### {TASK}"[:12])

    def test_feed_carries_the_complete_roster(self):
        answer = _answer()
        feed = tool.render_librarian_feed(answer, 400_000)
        for row in answer["one_hop"]["nodes"]:
            self.assertIn(row["uid"], feed,
                          f"roster node {row['uid']} missing from the feed")
        self.assertIn("one-hop roster is COMPLETE", feed)

    def test_bodies_included_in_ranked_order_and_labeled(self):
        answer = _answer()
        feed = tool.render_librarian_feed(answer, 400_000)
        governed = [it["uid"] for it in answer["items"]
                    if (tool.FILES / f"{it['uid']}.md").is_file()]
        self.assertTrue(governed, "fixture task has no governed ranked bodies")
        positions = [feed.index(f"### {uid} · vault/files/{uid}.md")
                     for uid in governed if f"### {uid}" in feed]
        self.assertEqual(positions, sorted(positions),
                         "bodies are not in ranked order")

    def test_budget_cap_names_what_it_excluded(self):
        answer = _answer()
        feed = tool.render_librarian_feed(answer, 10)  # starvation budget
        self.assertIn("FEED LEDGER", feed)
        self.assertIn("body budget (10 chars) reached", feed)
        self.assertNotIn("excluded: none", feed)

    def test_ledger_counts_are_honest(self):
        answer = _answer()
        feed = tool.render_librarian_feed(answer, 400_000)
        self.assertIn("bodies included:", feed)
        self.assertIn("of budget 400000", feed)

    def test_determinism_two_renders_byte_identical(self):
        answer = _answer()
        self.assertEqual(tool.render_librarian_feed(answer, 400_000),
                         tool.render_librarian_feed(answer, 400_000))

    def test_cli_flag_writes_the_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "feed.md"
            proc = subprocess.run(
                [sys.executable, str(TOOLS / "tropo-orient.py"),
                 "--task", TASK, "--k", "5", "--for-librarian", str(out)],
                cwd=ROOT, capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
            self.assertTrue(out.is_file())
            text = out.read_text()
            self.assertIn("LIBRARIAN FEED", text)
            self.assertIn("FEED LEDGER", text)

    def test_contract_header_travels_with_every_feed(self):
        feed = tool.render_librarian_feed(_answer(), 400_000)
        for phrase in ("You never write", "citations by UID",
                       "not in my context"):
            self.assertIn(phrase, feed)


class SkillContractTests(unittest.TestCase):
    """AC2 — the skill exists, names the real flag, carries the contract."""

    def test_skill_exists_and_names_the_flag(self):
        self.assertTrue(SKILL.is_file())
        text = SKILL.read_text()
        self.assertIn("--for-librarian", text)
        self.assertIn("tropo-orient.py", text)

    def test_contract_phrases_verbatim(self):
        text = SKILL.read_text()
        for phrase in ("write-never", "citations-always", "not-in-my-context"):
            self.assertIn(phrase, text)

    def test_cache_never_memory_and_measurement_log(self):
        text = SKILL.read_text()
        self.assertIn("cache, never memory", text)
        self.assertIn("librarian-log.jsonl", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
