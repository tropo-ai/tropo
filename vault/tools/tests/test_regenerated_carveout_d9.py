#!/usr/bin/env python3
"""D9 — a derived index is REGENERATED: neither prompted for nor written.

vault/00-index.jsonl and its three siblings are MANIFEST-LISTED and never hash
equal to what shipped, because a rebuild regenerates them on the way past. So
category (d) read them as USER_MODIFIED_SHIPPED and Po asked the customer to
approve overwriting a file they had never touched — a prompt with no honest
answer, since "keep mine" and "take theirs" are both wrong for an artifact the
next rebuild settles anyway.

Ruled by Metis G105 with Argus A146 concurring (2026-08-08): a distinct class,
EXACT paths, consulted before every other branch including the apply engine's
add-target-missing fast path, leaving the Step 4.4 rebuild as sole writer.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import tropo_update_namespace as ns  # noqa: E402

FLOOR = TOOLS / "tests" / "test_clean_update_floor.py"


def _floor():
    spec = importlib.util.spec_from_file_location("floor_under_test", FLOOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules["floor_under_test"] = module
    spec.loader.exec_module(module)
    return module


class RegeneratedClassification(unittest.TestCase):
    def test_the_four_derived_surfaces_classify_regenerated(self) -> None:
        manifest = {p: "deadbeef" for p in ns.REGENERATED_PATHS}
        for path in sorted(ns.REGENERATED_PATHS):
            with self.subTest(path=path):
                self.assertEqual(
                    ns.classify(path, manifest_index=manifest, current_hash="cafebabe"),
                    ns.REGENERATED,
                    "a manifest-listed derived index must never reach "
                    "USER_MODIFIED_SHIPPED — that prompt has no honest answer")

    def test_the_carve_out_is_exact_path_not_a_prefix(self) -> None:
        """A146's sharpening. `vault/00-` is a namespace a governed file could
        join tomorrow; a carve-out that widens by accident repeals
        PRESERVE-by-default for a whole directory."""
        near_misses = [
            "vault/00-index.jsonl.bak",
            "vault/00-index.jsonl.tmp",
            "vault/00-indexes.jsonl",
            "vault/00-notes.md",
            "vault/files/00-index.jsonl",
        ]
        manifest = {p: "deadbeef" for p in near_misses}
        for path in near_misses:
            with self.subTest(path=path):
                self.assertNotEqual(
                    ns.classify(path, manifest_index=manifest, current_hash="cafebabe"),
                    ns.REGENERATED,
                    f"{path} was swept into the carve-out by a prefix match")

    def test_classification_holds_with_no_manifest_and_no_hash(self) -> None:
        """The class is a property of the path, not of the manifest. A studio
        with no MANIFEST.md must still not have its index written by an op."""
        for path in sorted(ns.REGENERATED_PATHS):
            with self.subTest(path=path):
                self.assertEqual(ns.classify(path), ns.REGENERATED)


class ApplyPathNeverWritesADerivedIndex(unittest.TestCase):
    """The ordering half. The guard existed; one branch reached past it."""

    def _apply(self, kind: str, create_target: bool):
        floor = _floor()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = "vault/00-index.jsonl"
            (root / "vault").mkdir(parents=True)
            if create_target:
                (root / rel).write_text('{"pre":"existing"}\n', encoding="utf-8")
            plan = [(kind, rel, '{"from":"the update package"}\n')]
            written, refused, needs_confirm, regenerated = floor.apply_plan(
                root, plan, ns, manifest_index={rel: "deadbeef"})
            on_disk = (root / rel).read_text(encoding="utf-8") if (root / rel).exists() else None
            return written, needs_confirm, regenerated, on_disk

    def test_add_when_the_target_is_MISSING_does_not_write_it(self) -> None:
        """The fast path A146 named.

        It wrote unconditionally when the target did not exist — true for every
        class except this one. On a fresh install the derived index is absent,
        so this branch is the likely one, not the exotic one.
        """
        written, needs_confirm, regenerated, on_disk = self._apply("add", create_target=False)
        self.assertEqual(written, [], "an add wrote a derived index directly")
        self.assertEqual(needs_confirm, [], "a derived index must not be prompted for either")
        self.assertEqual(regenerated, ["vault/00-index.jsonl"])
        self.assertIsNone(on_disk, "the rebuild is the sole writer; nothing else creates it")

    def test_replace_when_the_target_EXISTS_does_not_touch_it(self) -> None:
        written, needs_confirm, regenerated, on_disk = self._apply("replace", create_target=True)
        self.assertEqual(written, [])
        self.assertEqual(needs_confirm, [], "this is the prompt with no honest answer")
        self.assertEqual(regenerated, ["vault/00-index.jsonl"])
        self.assertEqual(on_disk, '{"pre":"existing"}\n', "the existing index was modified")

    def test_mutation_strip_the_carve_out_and_the_defect_returns(self) -> None:
        """The governing proof, as A146 specified it.

        Remove the class and a manifest-listed index goes straight back to
        USER_MODIFIED_SHIPPED — the customer prompt this whole item exists to
        delete.
        """
        rel = "vault/00-index.jsonl"
        manifest = {rel: "deadbeef"}
        self.assertEqual(
            ns.classify(rel, manifest_index=manifest, current_hash="cafebabe"),
            ns.REGENERATED, "control: the carve-out is in place")

        original = ns.REGENERATED_PATHS
        try:
            ns.REGENERATED_PATHS = frozenset()
            self.assertEqual(
                ns.classify(rel, manifest_index=manifest, current_hash="cafebabe"),
                ns.USER_MODIFIED_SHIPPED,
                "stripping the carve-out no longer reproduces the defect — "
                "this test has stopped discriminating the fix")
        finally:
            ns.REGENERATED_PATHS = original

        self.assertEqual(
            ns.classify(rel, manifest_index=manifest, current_hash="cafebabe"),
            ns.REGENERATED, "the carve-out must be restored after the mutation")


if __name__ == "__main__":
    unittest.main(verbosity=1)
