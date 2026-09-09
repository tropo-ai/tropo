#!/usr/bin/env python3
"""The one producer of the four memory-surface filenames must resolve both eras.

Phase 2 of the memory rebuild (f0153a6df07f). Step 1 makes every reader tolerant
of the new name and the old; this proves the resolver those readers share.

The tests that matter here are the ones that would go red if the fallback arm
died, because that arm is the whole reason step 1 can land before step 2 without
breaking a boot. Each is mutation-checked rather than asserted about.

talos-t65, 2026-09-08.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]

_spec = importlib.util.spec_from_file_location(
    "memory_surfaces_under_test", TOOLS / "lib" / "memory_surfaces.py"
)
assert _spec and _spec.loader
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)


class _Studio(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="memory-surfaces-"))
        self.addCleanup(self._clean)

    def _clean(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _agent_dir(self, slug: str = "talos") -> Path:
        d = ms.agent_memory_dir(self.tmp, slug)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _studio_dir(self) -> Path:
        d = self.tmp / ".tropo-studio" / "memory"
        d.mkdir(parents=True, exist_ok=True)
        return d


class ResolutionPrefersTheNewNameAndFallsBack(_Studio):
    def test_the_new_name_wins_when_it_exists(self) -> None:
        d = self._agent_dir()
        (d / ms.AGENT_INDEX).write_text("new", encoding="utf-8")
        self.assertEqual(ms.agent_index(self.tmp, "talos").name, ms.AGENT_INDEX)

    def test_the_legacy_name_resolves_when_it_is_the_only_one(self) -> None:
        """The fallback arm. Kill it and this is the test that goes red — which
        is exactly the boot that breaks if step 1 lands wrong."""
        d = self._agent_dir()
        (d / ms.AGENT_INDEX_LEGACY).write_text("old", encoding="utf-8")
        resolved = ms.agent_index(self.tmp, "talos")
        self.assertEqual(resolved.name, ms.AGENT_INDEX_LEGACY)
        self.assertEqual(resolved.read_text(encoding="utf-8"), "old")

    def test_the_new_name_wins_when_BOTH_exist(self) -> None:
        """Mid-transition a folder can legitimately hold both. Preference must
        be the canonical name, or step 2 would silently keep reading the file
        it just moved away from."""
        d = self._agent_dir()
        (d / ms.AGENT_INDEX_LEGACY).write_text("old", encoding="utf-8")
        (d / ms.AGENT_INDEX).write_text("new", encoding="utf-8")
        self.assertEqual(
            ms.agent_index(self.tmp, "talos").read_text(encoding="utf-8"), "new")

    def test_neither_present_names_the_canonical_file(self) -> None:
        """An absence must be reported against the name the studio is moving
        TO. A caller that says 'agent-memory.md is missing' after step 2 sends
        its reader looking for a file that will never exist again."""
        self._agent_dir()
        resolved = ms.agent_index(self.tmp, "talos")
        self.assertEqual(resolved.name, ms.AGENT_INDEX)
        self.assertFalse(resolved.exists())

    def test_resolution_never_creates_anything(self) -> None:
        """Step 1 is readers only. A resolver that touched the filesystem would
        move a file before step 2 said to."""
        d = self._agent_dir()
        before = sorted(p.name for p in d.iterdir())
        ms.agent_index(self.tmp, "talos")
        ms.agent_log(self.tmp, "talos")
        self.assertEqual(sorted(p.name for p in d.iterdir()), before)
        self.assertEqual(before, [])

    def test_a_directory_of_the_right_name_is_not_a_surface(self) -> None:
        """`is_file()`, not `exists()`: a directory named memory.md must not
        satisfy the probe and shadow a real legacy file beside it."""
        d = self._agent_dir()
        (d / ms.AGENT_INDEX).mkdir()
        (d / ms.AGENT_INDEX_LEGACY).write_text("old", encoding="utf-8")
        self.assertEqual(ms.agent_index(self.tmp, "talos").name, ms.AGENT_INDEX_LEGACY)


class BothScopesLandOnTheSameTwoNames(_Studio):
    def test_the_canonical_names_are_identical_across_scopes(self) -> None:
        """The point of the rename, asserted rather than assumed: after this,
        one name means one thing in any memory folder."""
        self.assertEqual(ms.AGENT_INDEX, ms.STUDIO_INDEX)
        self.assertEqual(ms.AGENT_LOG, ms.STUDIO_LOG)

    def test_no_canonical_name_contains_the_word_current(self) -> None:
        """`memory-current.md` is the filename that caused the confusion; the
        spec's success test is that no live filename carries the word."""
        for name in (ms.AGENT_INDEX, ms.AGENT_LOG, ms.STUDIO_INDEX, ms.STUDIO_LOG):
            self.assertNotIn("current", name)

    def test_the_studio_legacy_index_resolves(self) -> None:
        d = self._studio_dir()
        (d / ms.STUDIO_INDEX_LEGACY).write_text("crew", encoding="utf-8")
        self.assertEqual(ms.studio_index(self.tmp).name, ms.STUDIO_INDEX_LEGACY)

    def test_the_studio_legacy_log_resolves(self) -> None:
        d = self._studio_dir()
        (d / ms.STUDIO_LOG_LEGACY).write_text("", encoding="utf-8")
        self.assertEqual(ms.studio_log(self.tmp).name, ms.STUDIO_LOG_LEGACY)


class ClassifyingANameHandedToYou(unittest.TestCase):
    def test_every_era_of_index_name_classifies(self) -> None:
        for name in (ms.AGENT_INDEX, ms.AGENT_INDEX_LEGACY, ms.STUDIO_INDEX_LEGACY):
            self.assertTrue(ms.is_index_name(name), name)

    def test_every_era_of_log_name_classifies(self) -> None:
        for name in (ms.AGENT_LOG, ms.AGENT_LOG_LEGACY, ms.STUDIO_LOG_LEGACY):
            self.assertTrue(ms.is_log_name(name), name)

    def test_the_classifier_is_live(self) -> None:
        """Negative control. A classifier that said yes to everything would
        make every assertion above pass while proving nothing."""
        for name in ("MEMORY.md", "short-term-memory.jsonl", "entries",
                     "history", "memory-current.jsonl", "notes.md"):
            self.assertFalse(ms.is_index_name(name), name)
            self.assertFalse(ms.is_log_name(name), name)

    def test_a_full_path_classifies_by_its_basename(self) -> None:
        self.assertTrue(
            ms.is_index_name("agents/talos/.tropo-capsule/memory/agent-memory.md"))
        self.assertTrue(ms.is_log_name(".tropo-studio/memory/memories.jsonl"))

    def test_index_and_log_never_overlap(self) -> None:
        self.assertEqual(set(ms.ALL_INDEX_NAMES) & set(ms.ALL_LOG_NAMES), set())


class TheStudiosOwnSurfacesResolveRightNow(unittest.TestCase):
    """Against the live tree, not a fixture. Whichever era this studio is in,
    the resolver must land on a file that is actually there — the check that
    keeps meaning something after step 2 moves them."""

    def test_the_studio_scope_index_resolves_to_a_real_file(self) -> None:
        self.assertTrue(ms.studio_index(ROOT).is_file(), ms.studio_index(ROOT))

    def test_the_studio_scope_log_resolves_to_a_real_file(self) -> None:
        self.assertTrue(ms.studio_log(ROOT).is_file(), ms.studio_log(ROOT))

    def test_every_executive_memory_index_resolves_to_a_real_file(self) -> None:
        agents = [
            p.name for p in (ROOT / "agents").iterdir()
            if p.is_dir() and (p / ".tropo-capsule" / "memory").is_dir()
            and not p.name.startswith("sa")
        ]
        self.assertTrue(agents, "no agent memory folders found — not vacuous")
        missing = [
            slug for slug in agents
            if not ms.agent_index(ROOT, slug).is_file()
            and not ms.agent_memory_dir(ROOT, slug).joinpath("history").is_dir()
        ]
        self.assertEqual(missing, [], "resolver found no memory index for: %s" % missing)


if __name__ == "__main__":
    unittest.main(verbosity=2)
