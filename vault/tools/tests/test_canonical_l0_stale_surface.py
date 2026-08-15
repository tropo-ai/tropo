#!/usr/bin/env python3
"""Canonical-L0 preflight: stale derived surfaces name themselves (7b1e0ae5 §3.1).

The index and project-tree are gitignored, derived surfaces. A clone that pulls
a new canonical L0 without rebuilding reports it MISSING, which reads as "L0
status was lost" when the truth is "this machine has not rebuilt". That is
exactly how ``48f8c52c`` (external-context) read red on a reviewer's clone while
the governed source file and the registry row were both correct.

The gate must still FAIL — a red derived surface is a real release blocker — but
it must say which failure it is and print the cure.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"

SPEC = importlib.util.spec_from_file_location(
    "tropo_validate_canonical_l0",
    TOOLS / "tropo-validate-canonical-l0.py",
)
L0 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = L0
SPEC.loader.exec_module(L0)

EXTERNAL_CONTEXT = "48f8c52c"


class StaleDerivedSurfaceTests(unittest.TestCase):
    def scratch(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="canonical-l0-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        (tmp / "vault" / "files").mkdir(parents=True)
        (tmp / "vault" / "00-index.jsonl").write_text("", encoding="utf-8")
        (tmp / "vault" / "00-project-tree.jsonl").write_text("", encoding="utf-8")
        return tmp

    def test_source_present_but_unindexed_is_classified_stale_with_a_cure(self):
        root = self.scratch()
        (root / "vault" / "files" / f"{EXTERNAL_CONTEXT}.md").write_text(
            f"---\nuid: {EXTERNAL_CONTEXT}\ntype: project\ntitle: external-context\n---\n",
            encoding="utf-8",
        )

        classified = L0.classify_missing(
            root, [{"uid": EXTERNAL_CONTEXT, "title": "external-context"}]
        )

        self.assertEqual(len(classified["stale_derived_surface"]), 1)
        self.assertEqual(classified["source_absent"], [])
        entry = classified["stale_derived_surface"][0]
        self.assertEqual(entry["source_path"], f"vault/files/{EXTERNAL_CONTEXT}.md")
        self.assertFalse(entry["indexed"], "fixture must leave the entry unindexed")

        findings = {
            "canonical_count": 4,
            "rendered_count": 3,
            "non_l0_risk_count": 0,
            "missing_from_rendered": [
                {"uid": EXTERNAL_CONTEXT, "title": "external-context"}
            ],
            "non_l0_risk_at_l0": [],
            "extra_unknown": [],
            "title_mismatches": [],
            "pass": False,
        }
        findings.update(classified)
        out = StringIO()
        with redirect_stdout(out):
            L0.report_human(findings)
        rendered = out.getvalue()

        self.assertIn("STALE DERIVED SURFACE", rendered)
        self.assertIn(
            L0.STALE_SURFACE_CURE,
            rendered,
            "the report must print the exact cure command",
        )
        self.assertNotIn(
            f"--only {EXTERNAL_CONTEXT}",
            rendered,
            "`--only` never writes the project tree; prescribing it strands the "
            "operator on a gate that fails again with the same instruction",
        )
        self.assertIn("✗ FAIL", rendered, "a stale surface is still a release blocker")

    def test_source_absent_stays_the_plain_lost_l0_report(self):
        root = self.scratch()

        classified = L0.classify_missing(
            root, [{"uid": "deadbeef", "title": "gone"}]
        )

        self.assertEqual(classified["stale_derived_surface"], [])
        self.assertEqual(len(classified["source_absent"]), 1)

        findings = {
            "canonical_count": 4,
            "rendered_count": 3,
            "non_l0_risk_count": 0,
            "missing_from_rendered": [{"uid": "deadbeef", "title": "gone"}],
            "non_l0_risk_at_l0": [],
            "extra_unknown": [],
            "title_mismatches": [],
            "pass": False,
        }
        findings.update(classified)
        out = StringIO()
        with redirect_stdout(out):
            L0.report_human(findings)
        rendered = out.getvalue()

        self.assertNotIn("STALE DERIVED SURFACE", rendered)
        self.assertIn("has no governed source file", rendered)
        self.assertIn("✗ FAIL", rendered)

    def test_indexed_but_untreed_entry_is_cured_by_a_full_rebuild_not_only(self):
        """The cure has to be one that works.

        Running `--only <uid>` on a stale clone moves the entry from unindexed to
        indexed-but-untreed and the gate stays red, because `--only` freshens the
        index row and never writes ``00-project-tree.jsonl`` — the surface this
        validator reads. Printing it was a blind recovery path: the operator runs
        the command, the gate fails again, and the same instruction is reprinted.
        Caught by argus-a148 executing the printed cure, 2026-08-12.
        """
        root = self.scratch()
        (root / "vault" / "files" / f"{EXTERNAL_CONTEXT}.md").write_text(
            f"---\nuid: {EXTERNAL_CONTEXT}\ntype: project\n---\n", encoding="utf-8"
        )
        (root / "vault" / "00-index.jsonl").write_text(
            json.dumps({"uid": EXTERNAL_CONTEXT, "type": "project"}) + "\n",
            encoding="utf-8",
        )
        # Project tree deliberately left without the entry: the exact state a
        # completed `--only` leaves behind.

        classified = L0.classify_missing(
            root, [{"uid": EXTERNAL_CONTEXT, "title": "external-context"}]
        )

        entry = classified["stale_derived_surface"][0]
        self.assertTrue(
            entry["indexed"],
            "an indexed-but-untreed entry must not be reported as unindexed",
        )
        self.assertFalse(
            entry["in_project_tree"],
            "fixture must leave the project tree stale, or this proves nothing",
        )

        findings = {
            "canonical_count": 4,
            "rendered_count": 3,
            "non_l0_risk_count": 0,
            "missing_from_rendered": [
                {"uid": EXTERNAL_CONTEXT, "title": "external-context"}
            ],
            "non_l0_risk_at_l0": [],
            "extra_unknown": [],
            "title_mismatches": [],
            "pass": False,
        }
        findings.update(classified)
        out = StringIO()
        with redirect_stdout(out):
            L0.report_human(findings)
        rendered = out.getvalue()

        self.assertIn("--apply", rendered)
        self.assertIn(L0.STALE_SURFACE_CURE, rendered)
        self.assertNotIn(
            f"--only {EXTERNAL_CONTEXT}",
            rendered,
            "the report still prescribes `--only`, which cannot clear this gate",
        )
        self.assertIn("00-project-tree.jsonl", rendered)
        self.assertIn("in 00-index.jsonl", rendered)
        self.assertIn("✗ FAIL", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
