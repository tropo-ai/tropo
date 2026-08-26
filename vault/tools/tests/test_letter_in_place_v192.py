"""AC4 (b1e78abb, v1.92): tropo-lineage.py retire --letter accepts a letter
already placed at its own create-only destination, identity-conditioned.

A154, A155 and T49 each hand-worked around this: an agent authors its own
retirement letter directly at `transfers/<GEN>.md` (its create-only, correct
home) and then passes `--letter transfers/<GEN>.md` to the same command that
wrote it — and the old code refused, unconditionally, on `os.link()`'s
FileExistsError, because ANY pre-existing destination looked like a
collision, even the exact file the source names.

Four branches, matching the spec's own §Acceptance evidence verbatim:
  (a) in-place letter accepted, close succeeds, lineage line carries the path
  (b) different source against occupied destination refuses, occupant bytes
      unchanged
  (c) an EMPTY in-place letter still refuses
  (d) same content at a different path is accepted (this build's identity
      rule includes content-hash, not samefile-only)

Reuses test_lineage.py's bare-tmpdir + subprocess pattern (light fixture,
per the spec's own §Handoff).

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_letter_in_place_v192
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOL = pathlib.Path(__file__).resolve().parents[1] / "tropo-lineage.py"


class LetterInPlace(unittest.TestCase):

    def setUp(self) -> None:
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="letter-in-place-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def run_tool(self, *args):
        p = subprocess.run(
            [sys.executable, str(TOOL), "--root", str(self.root), *args],
            capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout, p.stderr

    def born(self, agent="metis", by="mike"):
        c, out, err = self.run_tool("born", "--agent", agent, "--by", by)
        self.assertEqual(c, 0, err)
        return json.loads(out)

    def transfers_path(self, agent, gen) -> pathlib.Path:
        return self.root / "agents" / agent / "transfers" / f"{gen}.md"

    def lineage_path(self, agent="metis") -> pathlib.Path:
        return self.root / "agents" / agent / "lineage.jsonl"

    def _last_lineage_record(self, agent="metis") -> dict:
        lines = self.lineage_path(agent).read_text(encoding="utf-8").splitlines()
        return json.loads(lines[-1])

    # (a) in-place letter accepted, close succeeds, lineage line carries the path.
    def test_a_letter_already_at_its_create_only_home_is_accepted(self) -> None:
        gen = self.born()["generation"]
        dest = self.transfers_path("metis", gen)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("Dear successor,\n\nBuild the ship. Then sail it.\n", encoding="utf-8")
        before = dest.read_bytes()

        code, out, err = self.run_tool(
            "retire", "--agent", "metis", "--letter", str(dest)
        )
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["letter"], f"agents/metis/transfers/{gen}.md")
        self.assertEqual(dest.read_bytes(), before, "in-place accept must not rewrite the letter")

        record = self._last_lineage_record()
        self.assertEqual(record["t"], "retired")
        self.assertEqual(record.get("letter"), f"agents/metis/transfers/{gen}.md")

    # (b) different source against occupied destination refuses, occupant unchanged.
    def test_a_different_source_against_an_occupied_destination_refuses(self) -> None:
        gen = self.born()["generation"]
        dest = self.transfers_path("metis", gen)
        dest.parent.mkdir(parents=True, exist_ok=True)
        occupant = "The real letter, already here.\n"
        dest.write_text(occupant, encoding="utf-8")

        other = self.root / "a-different-letter.md"
        other.write_text("A completely different letter someone else wrote.\n", encoding="utf-8")

        code, out, err = self.run_tool(
            "retire", "--agent", "metis", "--letter", str(other)
        )
        self.assertNotEqual(code, 0, "a different source must refuse, not silently accept")
        self.assertIn("already exists", err)
        self.assertEqual(dest.read_text(encoding="utf-8"), occupant, "occupant bytes must be unchanged")

    # (c) an EMPTY in-place letter still refuses.
    def test_an_empty_in_place_letter_still_refuses(self) -> None:
        gen = self.born()["generation"]
        dest = self.transfers_path("metis", gen)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("", encoding="utf-8")

        code, out, err = self.run_tool(
            "retire", "--agent", "metis", "--letter", str(dest)
        )
        self.assertNotEqual(code, 0, "an empty letter must never satisfy AC4's relaxation")
        self.assertIn("empty", err.lower())
        self.assertEqual(dest.read_text(encoding="utf-8"), "", "the empty file must be left exactly as found")

    # (d) same content at a different path is accepted (content-hash identity).
    def test_the_same_content_at_a_different_path_is_accepted(self) -> None:
        gen = self.born()["generation"]
        dest = self.transfers_path("metis", gen)
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = "Identical bytes, two different files.\n"
        dest.write_text(text, encoding="utf-8")

        elsewhere = self.root / "a-copy-of-the-same-letter.md"
        elsewhere.write_text(text, encoding="utf-8")

        code, out, err = self.run_tool(
            "retire", "--agent", "metis", "--letter", str(elsewhere)
        )
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["letter"], f"agents/metis/transfers/{gen}.md")
        self.assertEqual(dest.read_text(encoding="utf-8"), text, "identical content must not be rewritten")

    # Control: the un-relaxed refusal (normal path, source != dest, dest occupied
    # with real content) is still the whole point of create-only. Without this,
    # branch (b) could pass for the wrong reason (e.g. every retire refusing).
    def test_control_the_normal_no_letter_case_still_writes_via_the_ordinary_path(self) -> None:
        gen = self.born()["generation"]
        letter = self.root / "letter.md"
        letter.write_text("An ordinary letter, never placed in advance.\n", encoding="utf-8")
        dest = self.transfers_path("metis", gen)
        self.assertFalse(dest.exists())

        code, out, err = self.run_tool(
            "retire", "--agent", "metis", "--letter", str(letter)
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.read_text(encoding="utf-8"), letter.read_text(encoding="utf-8"))

    # Mutation, run rather than asserted: prove the identity check is doing
    # real work by confirming a near-miss (one byte different) still refuses.
    def test_mutation_a_near_identical_but_not_equal_letter_still_refuses(self) -> None:
        gen = self.born()["generation"]
        dest = self.transfers_path("metis", gen)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("The letter, version one.\n", encoding="utf-8")

        near_miss = self.root / "near-miss.md"
        near_miss.write_text("The letter, version two.\n", encoding="utf-8")

        code, out, err = self.run_tool(
            "retire", "--agent", "metis", "--letter", str(near_miss)
        )
        self.assertNotEqual(code, 0, "a one-character difference must not satisfy identity")
        self.assertEqual(dest.read_text(encoding="utf-8"), "The letter, version one.\n")


if __name__ == "__main__":
    unittest.main()
