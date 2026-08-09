#!/usr/bin/env python3
"""Nine tests for the whole agent lifecycle.

Each one exists because a real generation was blocked, or because something
irreplaceable could be destroyed. Nothing here tests a hypothetical.

The predecessor design had twenty tests including a seven-point crash matrix,
for a failure whose entire cost was a duplicate line in an append-only file.
These nine cover the three things that do real damage and the four births that
were actually refused this week.
"""

import json
import pathlib
import subprocess
import sys
import tempfile
import shutil
import unittest

TOOL = pathlib.Path(__file__).resolve().parents[1] / "tropo-lineage.py"


class Lineage(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="lineage-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_tool(self, *args):
        p = subprocess.run(
            [sys.executable, str(TOOL), "--root", str(self.root), *args],
            capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout, p.stderr

    def born(self, agent="metis", by="mike"):
        c, out, err = self.run_tool("born", "--agent", agent, "--by", by)
        self.assertEqual(c, 0, err)
        return json.loads(out)

    def file(self, agent="metis"):
        return self.root / "agents" / agent / "lineage.jsonl"

    # 1. Genesis. The case that was never once tested before this week.
    def test_first_birth_is_generation_one(self):
        self.assertEqual(self.born()["generation"], "G1")

    # 2. The number comes from the file and nowhere else.
    def test_each_birth_takes_the_next_number(self):
        self.assertEqual(self.born()["generation"], "G1")
        self.assertEqual(self.born()["generation"], "G2")
        self.assertEqual(self.born()["generation"], "G3")

    # 3. G97, G99, G100, Po and G102 were each refused because a PREDECESSOR
    #    was in some state a gate disliked. This is that whole family.
    def test_an_unretired_predecessor_never_blocks_a_birth(self):
        self.born()
        out = self.born()
        self.assertEqual(out["generation"], "G2")
        self.assertTrue(out["notes"], "it is recorded, out loud")

    # 4. Retire, then be born. The everyday path.
    def test_retire_then_birth(self):
        self.born()
        c, out, err = self.run_tool("retire", "--agent", "metis")
        self.assertEqual(c, 0, err)
        self.assertEqual(json.loads(out)["generation"], "G1")
        self.assertEqual(self.born()["generation"], "G2")

    # 5. REAL DAMAGE 1. A letter cannot be reconstructed. rename() would have
    #    silently replaced it; link() refuses. This is the one file in the
    #    system whose loss is permanent.
    def test_a_letter_is_never_overwritten(self):
        letter = self.root / "first.md"
        letter.write_text("the real letter", encoding="utf-8")
        self.born()
        self.run_tool("retire", "--agent", "metis", "--letter", str(letter))

        placed = self.root / "agents" / "metis" / "transfers" / "G1.md"
        self.assertEqual(placed.read_text(encoding="utf-8"), "the real letter")

        second = self.root / "second.md"
        second.write_text("DESTROYS IT", encoding="utf-8")
        c, _, err = self.run_tool("retire", "--agent", "metis", "--letter", str(second))
        self.assertNotEqual(c, 0)
        self.assertIn("already exists", err)
        self.assertEqual(placed.read_text(encoding="utf-8"), "the real letter",
                         "the original letter must survive, byte for byte")

    # 6. REAL DAMAGE 2. Never invent a generation from a file we cannot read.
    def test_an_unreadable_file_stops_the_birth_and_changes_nothing(self):
        self.born()
        before = self.file().read_bytes()
        with open(self.file(), "a", encoding="utf-8") as f:
            f.write("{this is not json\n")
        after_corrupt = self.file().read_bytes()

        c, _, err = self.run_tool("born", "--agent", "metis", "--by", "mike")
        self.assertNotEqual(c, 0)
        self.assertIn("cannot read", err)
        self.assertEqual(self.file().read_bytes(), after_corrupt,
                         "nothing is rewritten, quarantined or truncated")
        self.assertIn(before, after_corrupt)

    # 7. REAL DAMAGE 3. Every birth failure this studio has ever had came from
    #    the index being reachable. Nothing on the path to the append may touch
    #    the index, the mint, a card or a registry.
    def test_the_birth_path_reaches_nothing(self):
        src = TOOL.read_text(encoding="utf-8")
        for forbidden in ("rebuild-index", "tropo-mint-id", "spec_from_file_location",
                          "00-index", "vault/agents", "folder-mounts"):
            self.assertNotIn(forbidden, src,
                             f"{forbidden} must not be reachable from the lifecycle")
        # The one outward call is the crew broadcast, and it is deliberately
        # imported INSIDE announce() so it cannot be reached before the append.
        self.assertNotIn("\nimport subprocess", src,
                         "subprocess must not be importable at module level")
        self.assertIn("import subprocess  # deliberately local", src)
        # ORDERING, not just placement. The guard above is satisfied by a single
        # occurrence of that comment, so a SECOND outward call could be added
        # and moved ahead of the append without any test noticing -- proven by
        # mutation on 2026-08-06, when exactly that mutation stayed green.
        # Both outward calls must sit after their append() in source order.
        for command in ("cmd_born", "cmd_retire"):
            body = src.split(f"def {command}(")[1].split("\ndef ")[0]
            append_at = body.index("append(path, record)")
            for outward in ("announce(", "unmerged_note("):
                self.assertGreater(
                    body.index(outward), append_at,
                    f"{outward} runs before the append in {command}; nothing "
                    f"outward may be reachable before the line is on disk")

    # 7a. A correct record nobody can see. Vela V72's birth sat on a Cursor
    #     Cloud branch for two hours while the whole crew read V71 RETIRED.
    #     (metis-g103, 2026-08-06)
    def _init_repo_on_branch(self, branch):
        import subprocess as sp
        for cmd in (["init", "-q", "."], ["config", "user.email", "t@t"],
                    ["config", "user.name", "t"]):
            sp.run(["git", *cmd], cwd=self.root, capture_output=True)
        (self.root / "seed.txt").write_text("seed\n", encoding="utf-8")
        sp.run(["git", "add", "seed.txt"], cwd=self.root, capture_output=True)
        sp.run(["git", "commit", "-qm", "seed"], cwd=self.root, capture_output=True)
        sp.run(["git", "checkout", "-q", "-B", branch], cwd=self.root,
               capture_output=True)

    def test_a_birth_on_a_side_branch_says_so(self):
        self._init_repo_on_branch("cursor/vela-v72-birth-018a")
        out = self.born()
        self.assertEqual(out["generation"], "G1", "the birth still happened")
        self.assertTrue(
            any("not main" in n for n in out["notes"]),
            f"a birth the crew cannot see must say so; got {out['notes']}")

    def test_a_birth_on_main_is_quiet(self):
        self._init_repo_on_branch("main")
        out = self.born()
        self.assertEqual(out["generation"], "G1")
        self.assertFalse(
            any("not main" in n for n in out["notes"]),
            f"main is the normal case and must not nag; got {out['notes']}")

    def test_no_repo_at_all_cannot_cost_a_birth(self):
        # No git init: the check must be swallowed like announce().
        out = self.born()
        self.assertEqual(out["generation"], "G1")
        self.assertFalse(any("not main" in n for n in out["notes"]))

    # 7b. One gesture writes both homes, and the second home can never cost the
    #     first. Mike's requirement, 2026-08-05.
    def test_a_broken_broadcast_cannot_cost_an_agent_its_birth(self):
        tools = self.root / "vault" / "tools"
        tools.mkdir(parents=True)
        (tools / "tropo-emit-event.py").write_text(
            "import sys\nsys.stderr.write('emitter is broken\\n')\nraise SystemExit(9)\n",
            encoding="utf-8")

        out = self.born()
        self.assertEqual(out["generation"], "G1", "the birth still happened")
        self.assertTrue(any("broadcast" in n for n in out["notes"]),
                        "and the crew not hearing is said out loud, not hidden")
        self.assertIn("G1", (self.file()).read_text(encoding="utf-8"),
                      "the line is on disk regardless")

    # 8. Two machines, offline, both append. Git's union merge concatenates;
    #    the reader must not choke and the history must survive.
    def test_two_machines_appending_offline_both_survive(self):
        self.born()
        machine_b = {"t": "born", "gen": "G2", "at": "2026-08-06T00:00:00Z", "by": "mike"}
        with open(self.file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(machine_b) + "\n")

        c, out, err = self.run_tool("log", "--agent", "metis")
        self.assertEqual(c, 0, err)
        self.assertIn("G1", out)
        self.assertIn("G2", out)
        self.assertEqual(self.born()["generation"], "G3",
                         "the next number follows the highest line present")


if __name__ == "__main__":
    unittest.main(verbosity=2)
