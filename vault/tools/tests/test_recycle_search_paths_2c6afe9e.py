"""Contract for tropo-recycle.py's bare-UID resolution (finding 2c6afe9e).

The reported bug: a governed agent entry at vault/agents/<uid>.md SKIPped as
"source not found" because the lookup consulted a hardcoded two-directory list.
Deletion discipline says never `rm` and always use the gesture, so a class of
governed substrate the gesture cannot reach forces every caller to either violate
the discipline or improvise.

These tests pin the resolution PROPERTY (every immediate vault/ subdirectory is a
lookup root), not the specific directory the finding happened to name. Each one
carries a mutation control: `test_*_would_have_failed_under_the_old_list` proves
the suite can actually go red, because a regression test that passes against the
bug it describes is measuring something else.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tropo-recycle.py"

_spec = importlib.util.spec_from_file_location("tropo_recycle", TOOL)
recycle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recycle)

# The directories the pre-fix tool consulted. Kept only as the mutation control.
OLD_HARDCODED_LIST = ("files", "session-agents")

UID_DIRS = ("files", "agents", "capsules", "entities", "playbooks", "session-agents")


def build_studio(root: Path, dirs=UID_DIRS) -> None:
    """A studio shaped like the real one: several vault/ subdirs holding <uid>.md."""
    for name in dirs:
        (root / "vault" / name).mkdir(parents=True, exist_ok=True)
    # a non-entry subdirectory, to prove probing it is harmless
    (root / "vault" / "events" / "streams").mkdir(parents=True, exist_ok=True)


class SearchPathDiscoveryTests(unittest.TestCase):
    def test_every_vault_subdirectory_is_a_lookup_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_studio(root)
            found = {p.name for p in recycle.uid_search_paths(root)}
            for name in UID_DIRS:
                self.assertIn(
                    name, found,
                    f"vault/{name}/ holds UID-named entries but is not a lookup root",
                )

    def test_files_is_probed_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_studio(root)
            self.assertEqual(recycle.uid_search_paths(root)[0].name, "files")

    def test_a_directory_added_later_is_covered_without_a_code_change(self):
        """The property's whole point: no edit needed for the next new directory."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_studio(root)
            self.assertNotIn("ledgers", {p.name for p in recycle.uid_search_paths(root)})
            (root / "vault" / "ledgers").mkdir()
            self.assertIn("ledgers", {p.name for p in recycle.uid_search_paths(root)})

    def test_missing_vault_directory_degrades_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = recycle.uid_search_paths(Path(tmp))
            self.assertEqual([p.name for p in paths], ["files"])

    def test_discovery_would_have_failed_under_the_old_list(self):
        """Mutation control — the plant has teeth.

        If this passes while the others do too, the suite is measuring the fix
        rather than restating it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_studio(root)
            old = [root / "vault" / n for n in OLD_HARDCODED_LIST]
            missed = {"agents", "capsules", "entities", "playbooks"}
            self.assertTrue(
                missed.isdisjoint({p.name for p in old}),
                "the old hardcoded list already covered these; the finding would not exist",
            )


class BareUidResolutionTests(unittest.TestCase):
    """recycle_uid() end-to-end against a scratch studio."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        build_studio(self.root)
        self._saved = (recycle.VAULT_ROOT, recycle.VAULT_FILES, recycle.INDEX,
                       recycle.ARCHIVE_INDEX)
        recycle.VAULT_ROOT = self.root
        recycle.VAULT_FILES = self.root / "vault" / "files"
        recycle.INDEX = self.root / "vault" / "00-index.jsonl"
        recycle.ARCHIVE_INDEX = self.root / "vault" / "00-archive-index.jsonl"
        self.dest = self.root / "recycle" / "agent-deletions" / "test"
        self.dest.mkdir(parents=True)

    def tearDown(self):
        (recycle.VAULT_ROOT, recycle.VAULT_FILES, recycle.INDEX,
         recycle.ARCHIVE_INDEX) = self._saved
        self._tmp.cleanup()

    def _entry(self, subdir: str, uid: str) -> Path:
        p = self.root / "vault" / subdir / f"{uid}.md"
        p.write_text(f"---\nuid: {uid}\n---\n", encoding="utf-8")
        return p

    def test_agent_entry_recycles_the_reported_regression(self):
        src = self._entry("agents", "5a662be2")
        ok, msg = recycle.recycle_uid("5a662be2", "test", self.dest)
        self.assertTrue(ok, msg)
        self.assertFalse(src.exists(), "source should have moved")
        self.assertTrue((self.dest / "5a662be2.md").exists(), "should land in recycle bin")

    def test_every_uid_bearing_directory_resolves(self):
        for i, subdir in enumerate(UID_DIRS):
            uid = f"aaaaaa{i:02d}"
            self._entry(subdir, uid)
            ok, msg = recycle.recycle_uid(uid, "test", self.dest)
            self.assertTrue(ok, f"vault/{subdir}/ unreachable: {msg}")

    def test_duplicate_uid_across_directories_refuses_rather_than_guessing(self):
        a = self._entry("agents", "dddddddd")
        b = self._entry("capsules", "dddddddd")
        ok, msg = recycle.recycle_uid("dddddddd", "test", self.dest)
        self.assertFalse(ok)
        self.assertIn("REFUSED", msg)
        self.assertTrue(a.exists() and b.exists(), "a refusal must not move anything")

    def test_absent_uid_still_skips_and_names_what_it_searched(self):
        ok, msg = recycle.recycle_uid("ffffffff", "test", self.dest)
        self.assertFalse(ok)
        self.assertIn("SKIP", msg)
        self.assertIn("vault/agents", msg,
                      "the SKIP message must list the directories actually searched")

    def test_agent_entry_is_unreachable_when_the_old_list_is_restored(self):
        """Mutation control for the end-to-end path.

        Restore the pre-fix behaviour and the reported bug must come back. If it
        does not, this test never proved the fix did anything.
        """
        self._entry("agents", "5a662be2")
        original = recycle.uid_search_paths
        recycle.uid_search_paths = lambda vault_root=None: [
            self.root / "vault" / n for n in OLD_HARDCODED_LIST
        ]
        try:
            ok, msg = recycle.recycle_uid("5a662be2", "test", self.dest)
        finally:
            recycle.uid_search_paths = original
        self.assertFalse(ok, "the old list should not reach vault/agents/")
        self.assertIn("source not found", msg)


if __name__ == "__main__":
    unittest.main()
