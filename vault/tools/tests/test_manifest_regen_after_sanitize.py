#!/usr/bin/env python3
"""MANIFEST.md must be regenerated AFTER the sanitize walk, on every build.

f015b6182652 (argus-a172, from the Spine A AC8 sanitize measurement).

THE HOLE. `step_9_generate_manifest` stamps a sha256 per shipped file. Later,
`step_10_sanitize_argo_identity` REWRITES every shipped text file carrying an
Argo-identity pattern. The regeneration that followed was gated on
`step_10_2_purge_run_local_artifacts` returning a non-zero removal count — so on
a QUIET build, where the purge legitimately removes nothing, every sanitized file
shipped with a hash stamped before its own rewrite.

WHY IT REACHES A CUSTOMER. `MANIFEST.md` is read on a customer's disk by
`lib/tropo_update_namespace.classify` to decide replace-vs-preserve at update
time. A shipped file whose bytes disagree with its manifest row classifies as
USER_MODIFIED_SHIPPED — so Po asks the customer to approve overwriting files
they never touched.

The regeneration was riding on another step's litter: Step 10b runs the box,
leaves bytecode, and the purge's non-zero count did the work. `step_9d` (the
image manifest) already carries the cure and states it: gating on a purge that
may legitimately be a no-op leaves exactly the same hole on the quiet path.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

BUILD_TOOL = TOOLS / "tropo-build-release.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_release_manifest_regen", BUILD_TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_release_manifest_regen"] = mod
    spec.loader.exec_module(mod)
    return mod


class ManifestMatchesTheBytesThatShip(unittest.TestCase):
    """The world test: run the real sequence on a fixture box whose purge is a
    no-op, and read the manifest back against the bytes on disk."""

    def setUp(self):
        self.mod = _load()
        self.mod.DRY_RUN = False
        self.box = Path(tempfile.mkdtemp(prefix="manifest-regen-")).resolve()
        self.addCleanup(shutil.rmtree, self.box, True)
        # The sanitiser regenerates the box's mint registry, which needs the
        # box to carry real capsules. 2.1 MB copied once per test is cheaper
        # than a fixture that does not resemble a box.
        shutil.copytree(TOOLS.parents[1] / "vault" / "capsules",
                        self.box / "vault" / "capsules")
        (self.box / "vault" / "files").mkdir(parents=True, exist_ok=True)
        # A shipped text file the sanitiser WILL rewrite, and one it will not.
        (self.box / "docs").mkdir(parents=True)
        (self.box / "docs" / "welcome.md").write_text(
            "# Welcome\n\nThis file mentions the Studio by name.\n", encoding="utf-8")
        (self.box / "docs" / "untouched.md").write_text(
            "# Untouched\n\nNothing here matches a pattern.\n", encoding="utf-8")

    def _purge_is_a_noop(self):
        removed = self.mod.step_10_2_purge_run_local_artifacts(str(self.box))
        self.assertEqual(removed, 0,
                         "the fixture is not quiet — this test only means "
                         "something when the purge removes nothing")

    def _manifest_rows(self):
        """(relative path, sha256) for every row MANIFEST.md lists."""
        text = (self.box / "MANIFEST.md").read_text(encoding="utf-8")
        # The writer's own shape: `| {rel} | {size:,} | `{checksum}` |`
        rows = {m.group(1).strip(): m.group(2)
                for m in re.finditer(r"^\|\s*(\S+)\s*\|[^|]*\|\s*`([0-9a-f]{64})`\s*\|",
                                     text, re.MULTILINE)}
        # A parser that silently returns nothing makes every comparison below
        # pass having compared NOTHING. My first regex expected the path and the
        # checksum to be adjacent columns; they are separated by size, so it
        # matched zero rows and the positive test went green over an empty set.
        # The mutation control is what exposed it.
        self.assertTrue(rows, "parsed no manifest rows — the comparison would be vacuous")
        return rows

    #: MANIFEST.md lists ITSELF, with the hash it carried before it was
    #: rewritten — structurally unavoidable for a file that hashes the tree it
    #: lives in, and the reason step_9d's image manifest "excludes itself by
    #: design". Named as the ONE exclusion so it cannot quietly grow into a
    #: list that hides a real staleness.
    SELF = "MANIFEST.md"

    def _mismatches(self):
        bad = []
        for rel, recorded in self._manifest_rows().items():
            if rel == self.SELF:
                continue
            path = self.box / rel
            if not path.is_file():
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != recorded:
                bad.append(rel)
        return bad

    def _run_sequence(self, *, regenerate: bool):
        self.mod.step_9_generate_manifest(str(self.box), "9.9.9")
        self.mod.step_10_sanitize_argo_identity(str(self.box))
        self._purge_is_a_noop()
        if regenerate:
            self.mod.step_9_generate_manifest(str(self.box), "9.9.9")

    def test_the_sanitiser_actually_rewrites_the_planted_file(self):
        """The fixture must plant something the sanitiser really changes, or
        both arms below pass for nothing."""
        before = (self.box / "docs" / "welcome.md").read_bytes()
        self.mod.step_10_sanitize_argo_identity(str(self.box))
        after = (self.box / "docs" / "welcome.md").read_bytes()
        self.assertNotEqual(before, after, "the sanitiser left the plant alone")

    def test_every_manifest_row_matches_the_bytes_on_disk(self):
        self._run_sequence(regenerate=True)
        self.assertEqual(self._mismatches(), [])
        # and the comparison was real: many rows, not an empty set
        self.assertGreater(len(self._manifest_rows()), 50)

    def test_without_the_regeneration_the_sanitised_file_is_stale(self):
        """Remove the fix and the hole is visible: the mutation control."""
        self._run_sequence(regenerate=False)
        self.assertIn("docs/welcome.md", self._mismatches(),
                      "the sanitised file's row matched anyway — this control "
                      "is not controlling")


class TheRegenerationIsNotGatedOnThePurge(unittest.TestCase):
    """The ordering itself, read from the source, so a future edit that re-gates
    it goes red here rather than at a customer's first update."""

    def test_the_final_freeze_regenerates_unconditionally(self):
        src = BUILD_TOOL.read_text(encoding="utf-8")
        tree = ast.parse(src)
        gated = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test_src = ast.dump(node.test)
            if "step_10_2_purge_run_local_artifacts" not in test_src:
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    fn = child.func
                    name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
                    if name == "step_9_generate_manifest":
                        gated.append(child.lineno)
        self.assertEqual(
            gated, [],
            "MANIFEST.md is regenerated inside a branch conditioned on the "
            "purge's return at line(s) %s. On a quiet build the purge removes "
            "nothing and every sanitised file ships with a pre-rewrite hash; "
            "step_9d already states why unconditional is the only honest shape."
            % gated)


if __name__ == "__main__":
    unittest.main()
