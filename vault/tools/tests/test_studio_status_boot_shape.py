"""tropo-studio-status v0.3 — the boot shape (metis-g119, Mike-directed 2026-09-04).

Three behaviours, each with a control that changes verdict when the mechanism is
removed:
  1. the board section prints counts by default and the item list only with
     board='full'; its first line names the population and the count;
  2. the broadcast fires only when a NEW identity enters the attention set — an
     item leaving (a loop turning green) does not emit;
  3. legacy status_check records (attention_key only, no attention_ids) fall
     back to the v0.2 key comparison for that one transition.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_SPEC = importlib.util.spec_from_file_location("tropo_studio_status", TOOLS / "tropo-studio-status.py")
SS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(SS)


class DecideEmit(unittest.TestCase):
    A = [("sa.daily-vault-health", "overdue"), ("sa.vault-janitor", "overdue")]

    def test_first_run_with_attention_emits(self):
        emit, why, new = SS.decide_emit(self.A, None, None)
        self.assertTrue(emit)
        self.assertEqual(new, SS.attention_ids(self.A))

    def test_empty_attention_never_emits(self):
        emit, _, new = SS.decide_emit([], ["x:overdue"], "deadbeef")
        self.assertFalse(emit)
        self.assertEqual(new, [])

    def test_item_leaving_does_not_emit(self):
        # previous run: both overdue; now: janitor ran and turned green
        prev = SS.attention_ids(self.A)
        now = [("sa.daily-vault-health", "overdue")]
        emit, why, new = SS.decide_emit(now, prev, SS.attention_key(self.A))
        self.assertFalse(emit, why)
        self.assertEqual(new, [])

    def test_new_entrant_emits_and_names_only_the_entrant(self):
        prev = SS.attention_ids(self.A)
        now = self.A + [("git-commit-backstop", "never-run")]
        emit, why, new = SS.decide_emit(now, prev, SS.attention_key(self.A))
        self.assertTrue(emit)
        self.assertEqual(new, ["git-commit-backstop:never-run"])

    def test_bucket_worsening_is_a_new_identity(self):
        prev = SS.attention_ids(self.A)
        now = [("sa.daily-vault-health", "failing"), ("sa.vault-janitor", "overdue")]
        emit, _, new = SS.decide_emit(now, prev, SS.attention_key(self.A))
        self.assertTrue(emit)
        self.assertEqual(new, ["sa.daily-vault-health:failing"])

    def test_unchanged_set_is_deduped(self):
        prev = SS.attention_ids(self.A)
        emit, why, _ = SS.decide_emit(self.A, prev, SS.attention_key(self.A))
        self.assertFalse(emit)
        self.assertIn("deduped", why)

    def test_legacy_record_falls_back_to_key_compare(self):
        # a v0.2 status_check line carries attention_key only (prev_ids None)
        same_key = SS.attention_key(self.A)
        emit, why, _ = SS.decide_emit(self.A, None, same_key)
        self.assertFalse(emit, why)
        emit2, _, _ = SS.decide_emit(self.A, None, "0000000000000000")
        self.assertTrue(emit2)


class BoardShape(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ss-board-")
        idx_dir = Path(self.tmp) / "vault"
        idx_dir.mkdir(parents=True)
        rows = [
            {"uid": "aaaa0001", "type": "task", "status": "new", "owner": "vela", "title": "Open task one"},
            {"uid": "aaaa0002", "type": "dev-spec", "status": "draft", "assigned_to": "vela-v77", "title": "Open spec two"},
            {"uid": "aaaa0003", "type": "task", "status": "done", "owner": "vela", "title": "Closed task"},
            {"uid": "aaaa0004", "type": "document", "status": "published", "owner": "vela", "title": "A document is not work"},
            {"uid": "aaaa0005", "type": "task", "status": "new", "owner": "argus", "title": "Someone else's"},
        ]
        with open(idx_dir / "00-index.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        self._root = SS.ROOT
        SS.ROOT = self.tmp

    def tearDown(self):
        SS.ROOT = self._root

    def test_default_is_counts_with_population_named_and_no_list(self):
        title, lines = SS.section_work("vela")
        self.assertEqual(title, "your work board (vela)")
        self.assertTrue(lines[0].startswith("  2 open work item(s) — the boot number"), lines[0])
        self.assertIn("documents, notes and pipeline definitions are not work items", lines[0])
        self.assertNotIn("  --- open items ---", lines)
        self.assertFalse(any("Open task one" in ln for ln in lines))
        self.assertTrue(any("--board full" in ln for ln in lines))
        self.assertIn("  dev-spec/draft: 1", lines)
        self.assertIn("  task/new: 1", lines)

    def test_full_prints_the_list(self):
        _, lines = SS.section_work("vela", board="full")
        self.assertIn("  --- open items ---", lines)
        self.assertTrue(any("aaaa0001 — Open task one" in ln for ln in lines))
        self.assertTrue(any("aaaa0002 — Open spec two" in ln for ln in lines))
        self.assertFalse(any("Closed task" in ln or "A document is not work" in ln or "Someone else" in ln for ln in lines))

    def test_nothing_open_is_zero_not_absent(self):
        _, lines = SS.section_work("orpheus")
        self.assertTrue(lines[0].startswith("  0 open work item(s)"), lines[0])
        self.assertTrue(any("nothing open" in ln for ln in lines))


if __name__ == "__main__":
    unittest.main()
