#!/usr/bin/env python3
"""AC11 — boot derivations stay fingerprint-fresh across Compact-Continue edits.

The fast path and the digest are compressed copies of canonical boot sources.
An agent that reads them instead of the sources is trusting a fingerprint, so
the gate that says "these are current" has to fail the moment a source moves.

This suite proves the gate reacts to the Compact-Continue surgery specifically:
the canonical activation playbook and the kernel pointers are declared sources
of the fast path, so the branch this stream added to them is inside the hashed
set. It runs against copied trees; the live studio is never mutated.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"

VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "tropo_validate_for_boot_derivation", TOOLS / "tropo-validate.py"
)
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
assert VALIDATOR_SPEC.loader is not None
sys.modules[VALIDATOR_SPEC.name] = VALIDATOR
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)

CC_SPEC = importlib.util.spec_from_file_location(
    "tropo_compact_continue_for_boot", TOOLS / "tropo-compact-continue.py"
)
CC = importlib.util.module_from_spec(CC_SPEC)
assert CC_SPEC.loader is not None
sys.modules[CC_SPEC.name] = CC
CC_SPEC.loader.exec_module(CC)

FAST_PATH = Path(".tropo/boot-fast-path.md")
DIGEST = Path(".tropo/boot-digest.md")
CANONICAL = Path("vault/playbooks/99341618.md")
BOOT_CONFIG = Path(".tropo/boot-config.md")


class BootDerivationFreshnessTests(unittest.TestCase):
    def copied_tree(self) -> Path:
        """A copy carrying only what the derivation gate reads."""
        tmp = Path(tempfile.mkdtemp(prefix="cc-boot-derivation-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        for rel in (
            ".tropo",
            ".tropo-studio",
            "vault/playbooks",
            "vault/files",
            "vault/tools",
        ):
            source = ROOT / rel
            if source.is_dir():
                shutil.copytree(
                    source, tmp / rel, dirs_exist_ok=True, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.sqlite"),
                )
        return tmp

    def test_live_derivations_are_fresh_after_the_compact_continue_surgery(self):
        findings, checked, defects = VALIDATOR.check_boot_derivation_fresh(ROOT)
        self.assertGreater(checked, 0, "no boot-derivation artifacts were checked")
        self.assertEqual(defects, 0, f"boot derivations drifted: {findings}")

    def test_editing_a_declared_source_turns_the_gate_red(self):
        """Mutation: the canonical playbook is a hashed source of the fast path."""
        tree = self.copied_tree()
        _, _, before = VALIDATOR.check_boot_derivation_fresh(tree)
        self.assertEqual(before, 0, "the copied tree did not start fresh")

        target = tree / CANONICAL
        target.write_text(
            target.read_text(encoding="utf-8") + "\n\nDrifted after curation.\n",
            encoding="utf-8",
        )

        findings, _, after = VALIDATOR.check_boot_derivation_fresh(tree)
        self.assertGreater(
            after,
            0,
            "editing a declared boot source did not fail the freshness gate",
        )
        self.assertTrue(
            any("boot-fast-path" in f for f in findings),
            f"the fast path did not report the drift: {findings}",
        )

    def test_hand_editing_a_derivation_turns_the_gate_red(self):
        """Self-fingerprint half: the compressed copy cannot be edited in place."""
        tree = self.copied_tree()
        target = tree / DIGEST
        target.write_text(
            target.read_text(encoding="utf-8") + "\n\nHand-edited, not re-rendered.\n",
            encoding="utf-8",
        )

        findings, _, defects = VALIDATOR.check_boot_derivation_fresh(tree)
        self.assertGreater(defects, 0)
        self.assertTrue(
            any("self_fingerprint" in f for f in findings),
            f"a hand-edited derivation passed: {findings}",
        )

    def test_the_compact_continue_branch_is_present_in_the_hashed_sources(self):
        """The surgery has to be inside the gated set, not beside it."""
        wanted = VALIDATOR._normalize_trigger_text(CC.TRIGGER_LINE)
        for rel in (CANONICAL, BOOT_CONFIG, Path(".tropo/playbooks/agent-activation.playbook.md")):
            with self.subTest(source=str(rel)):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn(
                    wanted,
                    VALIDATOR._normalize_trigger_text(text),
                    f"{rel} does not carry the Compact-Continue branch",
                )

        fast_path = (ROOT / FAST_PATH).read_text(encoding="utf-8")
        self.assertIn(
            wanted,
            VALIDATOR._normalize_trigger_text(fast_path),
            "the established-agent fast path does not carry the trigger — the "
            "agents most likely to be compacted are the ones that read it",
        )
        digest = (ROOT / DIGEST).read_text(encoding="utf-8")
        self.assertIn("Compact-Continue", digest)
        self.assertIn(
            wanted,
            VALIDATOR._normalize_trigger_text(digest),
            "the doctrine digest states the rule without the exact command",
        )

    def test_fast_path_declares_the_canonical_sources_it_compresses(self):
        """A derivation whose source list drops a file it summarizes is blind."""
        import re

        text = (ROOT / FAST_PATH).read_text(encoding="utf-8")
        front = text.split("---", 2)[1]
        declared = set(re.findall(r"^\s*path:\s*(\S+)\s*$", front, re.M))
        for required in (
            str(CANONICAL),
            str(BOOT_CONFIG),
            str(DIGEST),
            ".tropo/playbooks/agent-activation.playbook.md",
        ):
            self.assertIn(
                required,
                declared,
                f"{required} carries the Continue branch but is not a hashed "
                f"source of the fast path",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
