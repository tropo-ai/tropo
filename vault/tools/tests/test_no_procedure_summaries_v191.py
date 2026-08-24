#!/usr/bin/env python3
"""S4 AC4(a) (29506520), argus-a154 2026-08-23 — no procedure summaries in identity files.

An identity file may POINT AT a canonical procedure; it may not enumerate its
steps. metis's own §Boot-Extension carried a six-item summary of an eight-step
procedure and one wrong field value; argus's carried six of eight, omitting
§7 and §8 — two lines, two files, written separately, the same shortfall.

The detector this test proves out is SHAPE-based, not label-based, and the
docstring on `check_no_procedure_summaries_in_identity` records why: a
label-matcher against the playbook's own step names missed both real cases
(paraphrased words score below threshold) and flagged files merely discussing
a reflection or a Captain's Log (prose about a procedure is not the defect).
So the cases below are chosen to prove the SAME two failure directions: a
real paraphrase (parenthetical series, and a markdown list) is caught next to
its playbook pointer, and a pointer-only reference or unrelated prose is not.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[3]
TOOLS = STUDIO / "vault" / "tools"

_spec = importlib.util.spec_from_file_location(
    "tropo_validate_for_ac4a", TOOLS / "tropo-validate.py")
tv = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tv
_spec.loader.exec_module(tv)

PLAYBOOK_UID = "e2c7d185"


class _VaultFixture:
    def __init__(self, tmp: Path):
        self.root = tmp
        self.agents = tmp / "vault" / "agents"
        self.playbooks = tmp / "vault" / "playbooks"
        self.agents.mkdir(parents=True, exist_ok=True)
        self.playbooks.mkdir(parents=True, exist_ok=True)
        # The canonical playbook this UID resolves to. Only its EXISTENCE (the
        # stem) matters to the detector -- content is irrelevant here.
        (self.playbooks / f"{PLAYBOOK_UID}.md").write_text(
            "# Agent Retirement\n", encoding="utf-8")

    def write_agent(self, slug: str, body: str) -> Path:
        path = self.agents / f"{slug}.md"
        path.write_text(
            f"---\nuid: aaaa{slug[:4]}\ntype: agent\nagent: {slug}\n---\n\n{body}\n",
            encoding="utf-8")
        return path


class NoProcedureSummariesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ac4a-")
        self.addCleanup(self._tmp.cleanup)
        self.fixture = _VaultFixture(Path(self._tmp.name))

    def test_a_parenthetical_series_next_to_the_pointer_is_flagged(self):
        """The real metis/argus shape: a comma-series paraphrasing the steps."""
        self.fixture.write_agent(
            "metis-like",
            f"Retire via [the playbook]({PLAYBOOK_UID}.md) "
            "(fold, letter, reflection, Captain's Log, memory capture, drain).",
        )
        findings, checked, _ = tv.check_no_procedure_summaries_in_identity(self.fixture.root)
        self.assertEqual(checked, 1)
        self.assertEqual(len(findings), 1)
        self.assertIn("metis-like", findings[0])

    def test_a_markdown_list_next_to_the_pointer_is_flagged(self):
        self.fixture.write_agent(
            "list-like",
            f"Retire per {PLAYBOOK_UID}:\n"
            "- write the letter\n"
            "- fold memory\n"
            "- log the Captain's Log entry\n",
        )
        findings, checked, _ = tv.check_no_procedure_summaries_in_identity(self.fixture.root)
        self.assertEqual(checked, 1)
        self.assertEqual(len(findings), 1)
        self.assertIn("list-like", findings[0])

    def test_a_bare_pointer_is_not_flagged(self):
        """Keep the pointer, delete the enumeration -- this is the cured shape."""
        self.fixture.write_agent(
            "clean",
            f"Retire via the canonical [Agent Retirement playbook]({PLAYBOOK_UID}.md).",
        )
        findings, checked, _ = tv.check_no_procedure_summaries_in_identity(self.fixture.root)
        self.assertEqual(checked, 1)
        self.assertEqual(findings, [])

    def test_prose_about_the_practice_without_a_uid_is_not_flagged(self):
        """The false-positive class a label-matcher fell into: discussion, not
        enumeration, and no playbook UID in the passage at all."""
        self.fixture.write_agent(
            "prose",
            "Write the reflection honestly. The Captain's Log entry should name "
            "what actually happened this generation, not what was supposed to.",
        )
        findings, checked, _ = tv.check_no_procedure_summaries_in_identity(self.fixture.root)
        self.assertEqual(checked, 1)
        self.assertEqual(findings, [])

    def test_a_non_agent_file_is_not_checked(self):
        path = self.fixture.agents / "not-an-agent.md"
        path.write_text(
            f"---\nuid: bbbbbbbb\ntype: note\n---\n\n"
            f"({PLAYBOOK_UID}) (a, b, c, d)\n", encoding="utf-8")
        findings, checked, _ = tv.check_no_procedure_summaries_in_identity(self.fixture.root)
        self.assertEqual(checked, 0)
        self.assertEqual(findings, [])

    def test_no_agents_directory_is_zero_checked_not_a_crash(self):
        empty = Path(tempfile.mkdtemp(prefix="ac4a-empty-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(empty, ignore_errors=True))
        findings, checked, _ = tv.check_no_procedure_summaries_in_identity(empty)
        self.assertEqual((findings, checked), ([], 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
