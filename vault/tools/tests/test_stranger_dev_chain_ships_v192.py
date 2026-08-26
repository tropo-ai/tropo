"""AC1 (v1.92 Stream 2, 1a478c48): the dev-pipeline ignition ships, sanitized.

Before this build the dev-pipeline's substrate (definition, stages, steps)
shipped, but its only ignition -- `tropo-lock-dev-spec.py` (aeb2df3d) -- was
`extraction_scope: argo-reference`. A stranger studio received a pipeline it
could not start. Its own lib dependency closure (`b281edeb`, `vault/tools/
lib/`) was `status: draft` / `argo-reference` too -- designed correctly at
authoring (Metis's AC8 cold walk found the box shipped 70 tool scripts and
zero lib modules) but never actually wired live.

WHAT THIS FILE PROVES, from `vault/00-index.jsonl` -- the live index, not a
fixture, so a later hand-edit that quietly reverts any of this is caught at
the next validator/test run rather than at the next stranger's cold boot:

  - `aeb2df3d` (tropo-lock-dev-spec.py, the lock), `41b7c9e2` (tropo-close-
    dev.py, the close) and `5187be30` (tropo-mint-id.py, the mint) all carry
    `extraction_scope: ship` -- the complete minimal loop a stranger needs
    (mint -> lock -> evidence -> close) is in the box.
  - `b281edeb` (the lib/ closure) is present, `status: active`, and
    `extraction_scope: ship` -- "live", per AC1's own wording.
  - The three shipped TOOL files (not the ship-artifact, which is a folder
    reference, not source) carry no absolute `/Users` (or `/private`) paths
    and no reference to a UID whose OWN extraction_scope is `argo-private` --
    found live authoring this file: two such references in
    `tropo-mint-id.py` citing `7cac6473` (Federation Foundation, argo-
    private), one of them baked into the tool's OWN generated output (the
    `studio-identity.md` manifest body every user's `--kind studio` mint
    writes), not just a source comment. Fixed in the same build.

Run with pytest per the spec's own naming (`--skill` is AC4's extension,
added separately once the skill exists):
    python3 -m pytest -q vault/tools/tests/test_stranger_dev_chain_ships_v192.py

Also runnable via unittest, no pytest dependency:
    python3 -m unittest vault.tools.tests.test_stranger_dev_chain_ships_v192
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REAL_ROOT = Path(__file__).resolve().parents[3]
VAULT_FILES = REAL_ROOT / "vault" / "files"
INDEX_PATH = REAL_ROOT / "vault" / "00-index.jsonl"

#: The complete minimal dev loop a stranger needs, by UID -> its source file.
DEV_CHAIN_TOOLS = {
    "aeb2df3d": REAL_ROOT / "vault" / "tools" / "tropo-lock-dev-spec.py",
    "41b7c9e2": REAL_ROOT / "vault" / "tools" / "tropo-close-dev.py",
    "5187be30": REAL_ROOT / "vault" / "tools" / "tropo-mint-id.py",
}

LIB_CLOSURE_UID = "b281edeb"

ABSOLUTE_PATH_RE = re.compile(r"/Users/[\w./-]+|/private/[\w./-]+")
HEX_UID_RE = re.compile(r"\b[0-9a-f]{8}\b")


def _require_index() -> dict:
    """uid -> record, from the LIVE index file (not a fixture).

    Hard-fails, never skips, when the index is absent. Metis G112's finding
    on AC1's first non-author verification (2026-08-24, run 8098be20): a
    fresh worktree has no vault/00-index.jsonl (it is gitignored, derived,
    D4) -- the original SkipTest-on-missing version reported "0 tests run,
    skipped 2, exit 0" there, a green ship gate that could not see its own
    subject, in exactly the scenario the First-Use Walk actually runs in
    (a customer-shaped box where the index exists only after rebuild). A
    ship gate that greens when it cannot see what it is gating is the class
    this whole cycle hunts. Rebuild first (`python3 vault/tools/
    tropo-rebuild-vault.py`), then re-run.
    """
    if not INDEX_PATH.is_file():
        raise RuntimeError(
            f"{INDEX_PATH} does not exist. This test cannot verify anything "
            "about extraction_scope without it -- refusing rather than "
            "reporting a hollow green. Run `python3 vault/tools/"
            "tropo-rebuild-vault.py` first, then re-run this test."
        )
    index = {}
    with INDEX_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "uid" in d:
                index[d["uid"]] = d
    return index


class TheCompleteMinimalDevLoopShips(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.index = _require_index()

    def test_every_chain_tool_is_extraction_scope_ship(self) -> None:
        for uid in DEV_CHAIN_TOOLS:
            entry = self.index.get(uid)
            self.assertIsNotNone(entry, f"{uid} does not resolve in the live index")
            self.assertEqual(
                entry.get("extraction_scope"), "ship",
                f"{uid} ({entry.get('title', '')[:60]!r}) is "
                f"{entry.get('extraction_scope')!r}, not 'ship'",
            )

    def test_the_lib_closure_ship_artifact_is_present_and_live(self) -> None:
        entry = self.index.get(LIB_CLOSURE_UID)
        self.assertIsNotNone(
            entry, f"{LIB_CLOSURE_UID} (the lib/ closure) does not resolve"
        )
        self.assertEqual(entry.get("type"), "ship-artifact")
        self.assertEqual(
            entry.get("extraction_scope"), "ship",
            f"{LIB_CLOSURE_UID} is not extraction_scope: ship",
        )
        self.assertIn(
            entry.get("status"), ("active",),
            f"{LIB_CLOSURE_UID} is status {entry.get('status')!r}, not live",
        )


class ShippedToolsAreSanitized(unittest.TestCase):
    """No absolute argo paths, no argo-private UID references, in any of the
    three shipped tool files."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.index = _require_index()

    def test_no_absolute_paths_in_any_chain_tool(self) -> None:
        for uid, path in DEV_CHAIN_TOOLS.items():
            self.assertTrue(path.is_file(), f"{path} not found for {uid}")
            text = path.read_text(encoding="utf-8", errors="replace")
            hits = ABSOLUTE_PATH_RE.findall(text)
            self.assertEqual(
                hits, [],
                f"{path.name} contains absolute path(s): {hits[:5]}",
            )

    def test_no_argo_private_uid_references_in_any_chain_tool(self) -> None:
        """A referenced UID is fine (design-rationale citations are normal
        and expected throughout this codebase -- argo-reference citations
        are everywhere); a referenced UID whose OWN entry is extraction_
        scope: argo-private is the actual sanitization concern this
        criterion names. Checked against the live index so a citation added
        after this test was written is still caught."""
        for uid, path in DEV_CHAIN_TOOLS.items():
            text = path.read_text(encoding="utf-8", errors="replace")
            candidates = set(HEX_UID_RE.findall(text))
            private_hits = []
            for candidate in sorted(candidates):
                entry = self.index.get(candidate)
                if entry is not None and entry.get("extraction_scope") == "argo-private":
                    private_hits.append((candidate, entry.get("title", "")[:60]))
            self.assertEqual(
                private_hits, [],
                f"{path.name} references argo-private UID(s): {private_hits}",
            )

    def test_mutation_a_planted_absolute_path_turns_this_red(self) -> None:
        """Teeth, run rather than asserted."""
        real_text = DEV_CHAIN_TOOLS["aeb2df3d"].read_text(encoding="utf-8")
        mutated = real_text + '\n# debug: /Users/someone/scratch\n'  # portability:exempt — planted fixture string, proves the regex fires; never shipped as a real path
        self.assertEqual(ABSOLUTE_PATH_RE.findall(real_text), [])
        self.assertNotEqual(ABSOLUTE_PATH_RE.findall(mutated), [])

    def test_mutation_a_planted_argo_private_reference_turns_this_red(self) -> None:
        """Teeth for the second axis: plant a citation of a REAL argo-private
        UID (from the live index, so the plant is genuine) and confirm the
        production check's own logic flags it."""
        private_uid = next(
            (u for u, e in self.index.items()
             if e.get("extraction_scope") == "argo-private"),
            None,
        )
        if private_uid is None:
            self.skipTest("no argo-private entry exists in this index to plant")
        real_text = DEV_CHAIN_TOOLS["aeb2df3d"].read_text(encoding="utf-8")
        mutated = real_text + f"\n# see {private_uid} for context\n"
        candidates_before = {
            c for c in HEX_UID_RE.findall(real_text)
            if self.index.get(c, {}).get("extraction_scope") == "argo-private"
        }
        candidates_after = {
            c for c in HEX_UID_RE.findall(mutated)
            if self.index.get(c, {}).get("extraction_scope") == "argo-private"
        }
        self.assertEqual(candidates_before, set())
        self.assertEqual(candidates_after, {private_uid})


SKILL_UID = "ea724d2c"
SKILL_PATH = REAL_ROOT / "vault" / "skills" / "tropo-first-dev-spec.md"

FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)^```[^\n]*$", re.MULTILINE | re.DOTALL)
#: A command LINE naming a script to run: `python3 <path> ...` or `python <path> ...`,
#: capturing the path operand (argv[1], not argv[0]/the interpreter).
SCRIPT_INVOCATION_RE = re.compile(r"^\s*python3?\s+(\S+\.py)\b")
#: Heredoc / inline-script forms that name no script PATH at all -- the spec's own
#: named exception ("An inline heredoc/py -c evidence gesture counts as executable").
INLINE_GESTURE_RE = re.compile(r"^\s*python3?\s+(-c\b|-\s*<<)")


def _path_is_in_ship_set(operand: str, index: dict) -> bool:
    """Ship set = any type:tool entry whose own path is extraction_scope:
    ship, OR anything under vault/tools/lib/ (ships whole, via the b281edeb
    folder closure -- individual lib modules carry no UID of their own)."""
    normalized = operand.lstrip("./")
    if normalized.startswith("vault/tools/lib/"):
        return True
    for entry in index.values():
        if entry.get("type") == "tool" and entry.get("path") == normalized:
            return entry.get("extraction_scope") == "ship"
    return False


class TheSkillShipsAndItsCommandsResolve(unittest.TestCase):
    """AC4, `--skill` mode: the stranger's cold entry point exists in the
    box, and every fenced command in it is actually runnable from one."""

    @classmethod
    def setUpClass(cls) -> None:
        # Hard-fail, never skip (see _require_index's docstring): a missing
        # skill file here is not "cannot check" -- it is AC4 itself being
        # false, and a skip would report that as a pass-shaped gray, not red.
        if not SKILL_PATH.is_file():
            raise RuntimeError(
                f"{SKILL_PATH} does not exist -- AC4 (the stranger's cold "
                "entry point) is false. Refusing rather than skipping."
            )
        cls.text = SKILL_PATH.read_text(encoding="utf-8")
        cls.index = _require_index()

    def test_the_skill_exists_at_ship_scope(self) -> None:
        entry = self.index.get(SKILL_UID)
        self.assertIsNotNone(entry, f"{SKILL_UID} (the skill) does not resolve")
        self.assertEqual(entry.get("type"), "how-to")
        self.assertEqual(
            entry.get("extraction_scope"), "ship",
            f"{SKILL_UID} is {entry.get('extraction_scope')!r}, not 'ship'",
        )

    def test_every_fenced_command_resolves_within_the_ship_set(self) -> None:
        fences = FENCE_RE.findall(self.text)
        self.assertTrue(fences, "no fenced code blocks found in the skill")

        checked = 0
        for fence in fences:
            for line in fence.splitlines():
                if INLINE_GESTURE_RE.match(line):
                    checked += 1  # named exception: no script path to check
                    continue
                m = SCRIPT_INVOCATION_RE.match(line)
                if not m:
                    continue
                operand = m.group(1)
                checked += 1
                self.assertTrue(
                    _path_is_in_ship_set(operand, self.index),
                    f"fenced command names {operand!r}, which is not in the "
                    "ship set (not extraction_scope: ship, not under "
                    "vault/tools/lib/)",
                )
        self.assertGreater(
            checked, 0, "no script invocations or inline gestures found to check"
        )

    def test_mutation_a_fenced_command_naming_an_argo_reference_tool_turns_this_red(
        self,
    ) -> None:
        """Teeth, run rather than asserted. Plants a real argo-reference tool
        path (not fabricated) and confirms the check refuses it."""
        argo_ref_tool = next(
            (e["path"] for e in self.index.values()
             if e.get("type") == "tool" and e.get("extraction_scope") == "argo-reference"),
            None,
        )
        if argo_ref_tool is None:
            self.skipTest("no argo-reference tool exists in this index to plant")
        mutated = self.text + f"\n```\npython3 {argo_ref_tool} --help\n```\n"
        fences = FENCE_RE.findall(mutated)
        planted = fences[-1]
        line = planted.splitlines()[0]
        m = SCRIPT_INVOCATION_RE.match(line)
        self.assertIsNotNone(m)
        self.assertFalse(_path_is_in_ship_set(m.group(1), self.index))


if __name__ == "__main__":
    if "--skill" in sys.argv:
        sys.argv.remove("--skill")
        suite = unittest.TestLoader().loadTestsFromTestCase(
            TheSkillShipsAndItsCommandsResolve
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    unittest.main()
