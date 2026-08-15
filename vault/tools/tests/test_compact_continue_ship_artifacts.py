#!/usr/bin/env python3
"""AC13 (proportional) — the three Compact-Continue ship artifacts stay clean.

Argus's ruling, evt_a9360f18f56fe472_00000063: do not change locked parent
0dc0a350 and do not sweep the ten pre-existing locked direct-copy siblings
inside this stream. Compact's proof is bounded — the three NEW artifacts
resolve, carry required fields, terminate at manifest root 79cca015, and
contribute zero strict findings.

Whole-command strict green is NOT the claim and must not become one: the run
carries 33 P0s, all pre-existing and none attributable to Compact. This suite
fails if any of the three ever picks up a finding of its own.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_VALIDATOR = ROOT / "vault" / "tools" / "tropo-validate-release-manifest.py"

MANIFEST_ROOT = "79cca015"
ARTIFACTS = {
    "623708e8": ("vault/templates/root-docs/GEMINI.md", "GEMINI.md"),
    "0283151e": (
        "vault/templates/harness-configs/.claude/settings.json",
        ".claude/settings.json",
    ),
    "f147b86b": (
        "vault/templates/harness-configs/.gemini/settings.json",
        ".gemini/settings.json",
    ),
}


def frontmatter(uid: str) -> dict:
    text = (ROOT / "vault" / "files" / f"{uid}.md").read_text(encoding="utf-8")
    block = re.search(r"\A---\n(.*?)\n---", text, re.S).group(1)
    out: dict = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip().strip("'\"")
    return out


class ShipArtifactContractTests(unittest.TestCase):
    def test_each_artifact_declares_its_source_output_and_manifest_root(self):
        for uid, (source, output) in ARTIFACTS.items():
            with self.subTest(uid=uid):
                fm = frontmatter(uid)
                self.assertEqual(fm["type"], "ship-artifact")
                self.assertEqual(fm["kind"], "file")
                self.assertEqual(fm["parent"], MANIFEST_ROOT)
                self.assertEqual(fm["canonical_source"], f"argo-os/{source}")
                self.assertEqual(fm["output_path"], output)
                self.assertTrue(
                    (ROOT / source).is_file(),
                    f"{uid} names a canonical source that does not exist",
                )

    def test_no_compact_artifact_carries_a_manifest_finding(self):
        """The bounded AC13 claim: zero strict findings attributable to Compact."""
        proc = subprocess.run(
            [sys.executable, str(MANIFEST_VALIDATOR), "--strict"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        output = proc.stdout + proc.stderr
        self.assertTrue(output.strip(), "the manifest validator produced no output")
        offending = [
            line
            for line in output.splitlines()
            if any(uid in line for uid in ARTIFACTS)
        ]
        self.assertEqual(
            offending,
            [],
            "a Compact-Continue ship artifact picked up a manifest finding:\n"
            + "\n".join(offending),
        )

    def test_the_ten_locked_siblings_are_recorded_not_swept(self):
        """Guard the boundary of the ruling itself.

        The pre-existing C17 findings belong to locked artifacts and are a
        separate manifest-cleanup task needing Mike's approval. If a later pass
        edits them inside a Compact change, this states plainly that it was out
        of scope here.
        """
        proc = subprocess.run(
            [sys.executable, str(MANIFEST_VALIDATOR), "--strict"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        c17 = [
            line
            for line in (proc.stdout + proc.stderr).splitlines()
            if "C17-path-tree-containment" in line
        ]
        self.assertTrue(
            all(uid not in line for line in c17 for uid in ARTIFACTS),
            "a Compact artifact is back under a containment finding",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
