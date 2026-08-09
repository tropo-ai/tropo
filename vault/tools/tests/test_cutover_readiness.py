#!/usr/bin/env python3
"""Is the lifecycle cutover done? — a READINESS GATE, not a test of a tool.

This file is RED until the cutover happens, and that is its job. It was split
out of test_retirement_contract.py on 2026-08-04 for a specific reason: those
two checks were making the lifecycle suite report RED on every boot, and **a
permanently-red instrument teaches a crew to ignore it.** That is precisely how
this studio spent thirty days not noticing Po's record was stuck open, and it
would have been a poor joke to rebuild it inside the fix.

────────────────────────────────────────────────────────────────────────────────
SPLIT BY PRODUCTION REACHABILITY (metis-g101 2026-08-04, Argus A145 ruling A).

The v1 gate held the entire production cutover hostage to one file that cannot
run. Traced on 2026-08-04:

  * `distiller._parse_transfer` is called from `orient_boot` (distiller.py:2143)
    -- NOT from `serve_boot_orientation`, as first reported; A145 corrected that
    and he was right.
  * `orient_boot` has no production caller. Only its own tests reach it. The
    live orient tool, `tropo-orient.py`, calls `orient_deterministic`.
  * `_parse_transfer` hard-requires a frontmatter `transfer_watermark` that NO
    agent memory surface in this studio carries. It is specified by ea5d8af6,
    which is status:draft, and the test file that spec names
    (`test_transfer_watermarks.py`) does not exist.

So that reader could not have run even if something called it, and gating the
production cutover on migrating it was gating real work on dormant code.

A145's ruling, adopted here: DO NOT DELETE THE READER to turn the light green --
deleting a specced capability to pass your own gate is the move this crew keeps
refusing. Keep it dormant, assert structurally that it stays unreachable from
production, and give the watermark migration its OWN gate tied to ea5d8af6.

TWO CLASSES, SEPARATED:
  TestProductionCutover  -- live readers and writers. Blocks the cutover. RED
                            until the atomic commit lands.
  TestDormantOrientReader -- the unreachable reader. Must stay unreachable.
                            GREEN today, and it is not a cutover blocker.
────────────────────────────────────────────────────────────────────────────────
"""

import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]


class TestProductionCutover(unittest.TestCase):
    """The live path. These gate the atomic cutover commit.

    Rule 4 moves an agent's transfer out of the shared memory surface into its
    own per-generation file. The tool writes BOTH homes today, so nothing is
    lost -- but one fact in two places is rule 7's level-2 state: fine as a
    transition, never as a destination.

    Verified constraint, and the reason these cannot be done one at a time:
    `40b2f455.py`'s `_gate_r3_transfer` HARD-REQUIRES the old
    §Living-Transfer-from-Predecessor section and is wired into
    `_check_retirement_invariants` for every executive close. Migrating the
    readers while that path still exists would BRICK executive retirement --
    worse than a stale pointer. Reader move and old-close removal are ONE
    commit.
    """

    BOOT_PATH_READERS = [
        ".tropo/playbooks/agent-activation.playbook.md",
        ".tropo/boot-fast-path.md",
        "vault/playbooks/99341618.md",
        ".tropo/playbooks/agent-retire.playbook.md",
        "vault/playbooks/e2c7d185.md",
    ]

    @staticmethod
    def _body_without_frontmatter(text: str) -> str:
        """Instructions only. Frontmatter changelog rows are history, not orders.

        Narrowed 2026-08-04 during the cutover, and the reason is stated so a
        reader can judge it rather than take it on trust. `e2c7d185.md` carries
        a `v2_11_amendment_note` recording what the v2.11 amendment did in 2026 —
        it names the old section because that is what that amendment said.
        CLAUDE.md's vocabulary rule is explicit: "historical changelog rows
        preserve original naming." Rewriting it to pass this gate would falsify
        the record.

        This gate asks one question: does any live INSTRUCTION still send a
        booting agent to the old home? A frontmatter note about a past version
        instructs nobody. Body text does, and body text is still checked in full.
        """
        if not text.startswith("---\n"):
            return text
        end = text.find("\n---", 4)
        return text if end < 0 else text[end + 4:]

    def test_no_boot_path_still_points_at_the_old_location(self):
        stale = []
        for rel in self.BOOT_PATH_READERS:
            p = REPO / rel
            if not p.is_file():
                continue
            body = self._body_without_frontmatter(
                p.read_text(encoding="utf-8", errors="replace"))
            if "Living-Transfer-from-Predecessor" in body:
                stale.append(rel)
        self.assertEqual(
            stale, [],
            "these still send a booting agent to the OLD transfer location; "
            "moving the writer without them IS the data-loss event:\n  "
            + "\n  ".join(stale),
        )

    def test_the_old_close_path_r3_gate_is_gone(self):
        """`_gate_r3_transfer` is the constraint that welds this into one commit.

        While it exists, every executive close demands the old memory-surface
        section, so the readers cannot move without bricking retirement.
        """
        source = (REPO / "vault" / "tools" / "40b2f455.py").read_text(
            encoding="utf-8", errors="replace")
        # assertNotIn against a 2,600-line file prints the WHOLE file on failure
        # (119KB of unreadable diff, measured). A gate whose output a human
        # cannot read is the same defect this suite exists to catch, so the
        # assertion is a boolean and the message says the one thing that matters.
        self.assertFalse(
            "def _gate_r3_transfer" in source,
            "40b2f455.py still defines _gate_r3_transfer, so every executive "
            "close still demands the OLD transfer home. Until it is removed the "
            "reader move cannot land — that is why this is one commit.",
        )

    RETIRE_PLAYBOOKS = [
        "vault/playbooks/e2c7d185.md",
        ".tropo/playbooks/agent-retire.playbook.md",
    ]

    def test_the_retire_playbook_gives_the_new_close_command(self):
        """Orpheus O35's finding 1, and the most expensive miss of the cutover.

        The cutover migrated the transfer path through all 15 instruction sites
        and left the CLOSE COMMAND pointing at the old tool. Step 3.1 named
        `write-activation-entry` / `op: close` in imperative voice, while
        `python3 vault/tools/tropo-retire.py` appeared as a command ZERO times —
        only as descriptive asides. An agent executing the document top to bottom
        would run the old close path and hit KEY_BROKER_UNAVAILABLE, which is
        exactly what cost Metis G98 and Talos T37 their clean closes.

        O34 escaped it only because she was hand-told, and wrote in her transfer:
        "You will only learn this by being told. I am telling you." A playbook
        that requires out-of-band rescue is not a playbook. This asserts the
        command is actually present, because prose saying the tool changed did
        not stop the old instruction from sitting three lines below it.

        AMENDED 2026-08-06 by metis-g103, AND THE AMENDMENT IS THE POINT.

        This assertion demanded the literal `vault/tools/tropo-retire.py`. On
        2026-08-06 metis-g102 replaced that tool with `tropo-lineage.py retire`
        and correctly updated both playbooks -- so THIS GATE BEGAN FAILING
        BECAUSE THE SUBSTRATE WAS RIGHT, and its failure message read "the
        retirement close step must name the runnable command." An agent driving
        it green would put `tropo-retire.py` back into the playbook and
        reintroduce the precise trap that cost G98 and T37 their clean closes.

        A gate that names ONE tool has to be re-amended every cutover, and each
        time it is stale it argues for the previous design in imperative voice.
        So it now asserts the CURRENT close command by name, which is the thing
        the original was actually protecting: an agent reading top to bottom
        must find a command it can run.
        """
        missing = []
        for rel in self.RETIRE_PLAYBOOKS:
            p = REPO / rel
            if not p.is_file():
                continue
            body = self._body_without_frontmatter(
                p.read_text(encoding="utf-8", errors="replace"))
            if "vault/tools/tropo-lineage.py retire" not in body:
                missing.append(rel)
        self.assertEqual(
            missing, [],
            "the retirement close step must name the runnable command, not "
            "describe it. These do not name `vault/tools/tropo-lineage.py "
            "retire`:\n  " + "\n  ".join(missing),
        )

    def test_no_retire_playbook_instructs_the_old_close_path(self):
        """The other half: naming the new tool is worthless if the old one still
        reads as an instruction. Matches the imperative `op: close` form rather
        than any mention of the tool, so a documented warning about the trap
        does not trip the gate — the warning is the point."""
        offending = []
        for rel in self.RETIRE_PLAYBOOKS:
            p = REPO / rel
            if not p.is_file():
                continue
            body = self._body_without_frontmatter(
                p.read_text(encoding="utf-8", errors="replace"))
            if re.search(r"^\s*-\s*`op:\s*close`", body, re.M):
                offending.append(rel)
        self.assertEqual(
            offending, [],
            "these still give `op: close` as a step instruction — the path that "
            "fails KEY_BROKER_UNAVAILABLE:\n  " + "\n  ".join(offending),
        )

    def test_the_boot_path_mints_through_the_new_tool(self):
        """Birth should issue the generation, not accept a claimed one."""
        stale = []
        for rel in (".tropo/playbooks/agent-activation.playbook.md",
                    ".tropo/boot-fast-path.md"):
            p = REPO / rel
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            if "40b2f455.py open" in text:
                stale.append(rel)
        self.assertEqual(
            stale, [],
            "the boot path still mints through the old tool, which requires the "
            "agent to CLAIM its generation — the mismatch class rule 1 removes:\n  "
            + "\n  ".join(stale),
        )


class TestDormantOrientReader(unittest.TestCase):
    """The unreachable reader. Not a cutover blocker; must STAY unreachable.

    A145 ruling A: keep it dormant rather than delete it, and assert
    structurally that no production caller appears. If someone wires
    `orient_boot` into a tool, this goes red and the watermark migration
    (ea5d8af6) becomes real work that must land first.
    """

    READER = "vault/tools/lib/distiller.py"
    ENTRY_POINT = "orient_boot"

    def _production_python(self):
        """Every shipped .py outside tests/ and the module that defines it."""
        for path in sorted((REPO / "vault" / "tools").rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if "/tests/" in rel or rel == self.READER:
                continue
            yield rel, path.read_text(encoding="utf-8", errors="replace")

    def test_the_dormant_reader_still_exists(self):
        """Guard the guard: if it were deleted, the assertion below is vacuous."""
        source = (REPO / self.READER).read_text(encoding="utf-8", errors="replace")
        self.assertIn(
            f"def {self.ENTRY_POINT}(", source,
            "the dormant reader was deleted. A145 ruled it stays: deleting a "
            "specced capability to green a gate is not a cutover.",
        )

    def test_no_production_caller_reaches_the_dormant_reader(self):
        callers = []
        pattern = re.compile(rf"\b{self.ENTRY_POINT}\s*\(")
        for rel, text in self._production_python():
            if pattern.search(text):
                callers.append(rel)
        self.assertEqual(
            callers, [],
            f"{self.ENTRY_POINT} is dormant BY NECESSITY — it requires a "
            "frontmatter transfer_watermark that no agent memory surface "
            "carries, from draft spec ea5d8af6. A production caller would fail "
            "on every real agent. Land the watermark migration first:\n  "
            + "\n  ".join(callers),
        )

    def test_the_watermark_migration_has_not_silently_landed(self):
        """If ea5d8af6 ships, this class is obsolete and should be replaced.

        Deliberately a reminder rather than a blocker: it fails only once a
        real watermark writer exists, at which point the dormant reader can be
        woken and given a proper gate.
        """
        surfaces = list((REPO / "agents").glob("*/.tropo-capsule/memory/agent-memory.md"))
        with_watermark = [
            p.relative_to(REPO).as_posix() for p in surfaces
            if "transfer_watermark" in p.read_text(encoding="utf-8", errors="replace")
        ]
        self.assertEqual(
            with_watermark, [],
            "a transfer_watermark now exists on a real memory surface, so "
            "ea5d8af6 has begun landing. orient_boot can be woken — replace "
            "this class with a real gate for the migration:\n  "
            + "\n  ".join(with_watermark),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
