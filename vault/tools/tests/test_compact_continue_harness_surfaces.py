#!/usr/bin/env python3
"""Compact-Continue harness surfaces — AC7/AC8 (d5f8fe55 / 408c158c).

One trigger, copied exactly, on every surface a compacted session can land on.
Wording drift is the failure mode: a harness whose copy says something slightly
different sends that agent down a different path, and the difference between
"Continue" and "activate" is a phantom generation.

AC12 (live per-harness compaction encounters) is a manual walk and is not
claimed here. What this file proves about unavailable harnesses is exactly what
fixtures can prove: the adapter file exists, parses, targets the documented hook
contract, and carries the canonical line.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
TOOL = TOOLS / "tropo-compact-continue.py"

SPEC = importlib.util.spec_from_file_location("tropo_compact_continue_surfaces", TOOL)
CC = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = CC
SPEC.loader.exec_module(CC)

VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "tropo_validate_for_triggers", TOOLS / "tropo-validate.py"
)
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
assert VALIDATOR_SPEC.loader is not None
sys.modules[VALIDATOR_SPEC.name] = VALIDATOR
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)

RETIREMENT_CANONICAL = ROOT / "vault" / "playbooks" / "e2c7d185.md"
RETIREMENT_POINTER = ROOT / ".tropo" / "playbooks" / "agent-retire.playbook.md"


def normalize(text: str) -> str:
    return VALIDATOR._normalize_trigger_text(text)


class TriggerMatrixTests(unittest.TestCase):
    """AC7 — Claude, Cursor, Codex, Gemini, and manual entry all carry it."""

    def test_every_declared_surface_exists_and_carries_the_exact_trigger(self):
        wanted = normalize(CC.TRIGGER_LINE)
        missing, drifted = [], []
        for rel in sorted(CC.TRIGGER_SURFACES):
            path = ROOT / rel
            if not path.is_file():
                missing.append(rel)
                continue
            if wanted not in normalize(path.read_text(encoding="utf-8", errors="replace")):
                drifted.append(rel)
        self.assertEqual(missing, [], f"declared surfaces absent: {missing}")
        self.assertEqual(drifted, [], f"surfaces without the exact trigger: {drifted}")

    def test_the_matrix_covers_every_harness_the_spec_names(self):
        """A harness missing from the manifest is invisible to the gate."""
        surfaces = set(CC.TRIGGER_SURFACES)
        for expected in (
            "CLAUDE.md",                                    # Claude + Cursor root
            "AGENTS.md",                                    # Codex + Cursor root
            "START-TROPO.md",                               # universal manual entry
            "GEMINI.md",                                    # Gemini native
            ".claude/settings.json",                        # Claude hook adapter
            ".gemini/settings.json",                        # Gemini hook adapter
            "vault/templates/root-docs/CLAUDE.md",
            "vault/templates/root-docs/AGENTS.md",
            "vault/templates/root-docs/START-TROPO.md",
            "vault/templates/root-docs/GEMINI.md",
            "vault/templates/ide-configs/.cursorrules",
            "vault/templates/harness-configs/.claude/settings.json",
            "vault/templates/harness-configs/.gemini/settings.json",
        ):
            self.assertIn(expected, surfaces)

    def test_hook_adapters_parse_and_target_a_compaction_event(self):
        """Fixture-honest: JSON adapters are checked as config, not as live runs."""
        for rel, matcher in (
            (".claude/settings.json", "compact"),
            ("vault/templates/harness-configs/.claude/settings.json", "compact"),
            (".gemini/settings.json", "compress"),
            ("vault/templates/harness-configs/.gemini/settings.json", "compress"),
        ):
            with self.subTest(surface=rel):
                payload = json.loads((ROOT / rel).read_text(encoding="utf-8"))
                entries = payload.get("hooks", {}).get("SessionStart", [])
                self.assertTrue(entries, f"{rel} declares no SessionStart hook")
                matchers = [str(entry.get("matcher", "")) for entry in entries]
                self.assertIn(
                    matcher,
                    matchers,
                    f"{rel} has no {matcher!r} matcher; it would not fire after "
                    f"a compaction",
                )

    def test_no_adapter_infers_a_slug_or_runs_born(self):
        """Adapters inject a line. They never act on the agent's behalf."""
        for rel, kind in CC.TRIGGER_SURFACES.items():
            if kind != "json":
                continue
            with self.subTest(surface=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertNotIn("lineage.py born", text)
                self.assertNotIn("--agent talos", text, "an adapter hardcoded a slug")
                self.assertIn("<slug>", text, "the injected line lost its placeholder")

    def test_wording_drift_on_any_surface_turns_the_gate_red(self):
        """Mutation: the check must fail when a copy is reworded."""
        findings, checked, defects = VALIDATOR.check_compact_continue_trigger_copy(ROOT)
        self.assertEqual(defects, 0, f"live tree is not clean: {findings}")
        self.assertGreaterEqual(checked, len(CC.TRIGGER_SURFACES))

        target = ROOT / "vault" / "templates" / "root-docs" / "GEMINI.md"
        original = target.read_bytes()
        try:
            target.write_text(
                target.read_text(encoding="utf-8").replace(
                    "never run `born`", "you may run `born`"
                ),
                encoding="utf-8",
            )
            _, _, mutated_defects = VALIDATOR.check_compact_continue_trigger_copy(ROOT)
        finally:
            target.write_bytes(original)
        self.assertGreater(
            mutated_defects,
            0,
            "rewording a shipped trigger copy did not fail the gate",
        )

        _, _, restored = VALIDATOR.check_compact_continue_trigger_copy(ROOT)
        self.assertEqual(restored, 0, "the mutation was not restored")

    def test_a_surface_that_disappears_turns_the_gate_red(self):
        """Mutation: deleting a declared surface is a defect, not a silent pass."""
        target = ROOT / "vault" / "templates" / "root-docs" / "GEMINI.md"
        original = target.read_bytes()
        try:
            target.unlink()
            _, _, defects = VALIDATOR.check_compact_continue_trigger_copy(ROOT)
        finally:
            target.write_bytes(original)
        self.assertGreater(defects, 0, "a missing declared surface passed the gate")


class RetirementBoundaryTests(unittest.TestCase):
    """AC8 — context pressure routes to Continue; only a human retires."""

    def test_canonical_trigger_two_no_longer_authorizes_retirement(self):
        text = RETIREMENT_CANONICAL.read_text(encoding="utf-8")
        section = text.split("## When to Start Retirement", 1)[1].split("---", 1)[0]
        self.assertIn("NOT a retirement trigger", section)
        self.assertIn("tropo-compact-continue.py", section)
        self.assertNotIn(
            "If the harness provides a resource signal, trust it",
            section,
            "the old auto-compact retirement authority is still present",
        )

    def test_escalation_row_prefers_continue_over_racing_the_compactor(self):
        text = RETIREMENT_CANONICAL.read_text(encoding="utf-8")
        row = next(
            line
            for line in text.splitlines()
            if line.startswith("| Context approaching auto-compact")
        )
        self.assertIn("tropo-compact-continue.py", row)
        self.assertIn("human has already signalled", row)

    def test_degraded_retirement_floor_names_continue_and_human_authority(self):
        text = RETIREMENT_POINTER.read_text(encoding="utf-8")
        self.assertIn(normalize(CC.TRIGGER_LINE), normalize(text))
        self.assertIn("Not a retirement trigger", text)
        self.assertIn("retirement authority", text)

    def test_no_retirement_surface_routes_compaction_to_born(self):
        patterns = [re.compile(p, re.I) for p in CC.COMPACT_TO_BORN_PATTERNS[:2]]
        wanted = normalize(CC.TRIGGER_LINE)
        for path in (RETIREMENT_CANONICAL, RETIREMENT_POINTER):
            with self.subTest(surface=path.name):
                scan = normalize(path.read_text(encoding="utf-8")).replace(wanted, " ")
                for pattern in patterns:
                    for match in pattern.finditer(scan):
                        window = scan[max(0, match.start() - 60):match.start()].lower()
                        if "never" in window or "not " in window:
                            continue
                        self.fail(
                            f"{path.name} routes compaction toward birth: "
                            f"{match.group(0)[:80]!r}"
                        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
