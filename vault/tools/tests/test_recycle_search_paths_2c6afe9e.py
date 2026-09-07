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

class SlugNamedUidResolutionTests(unittest.TestCase):
    """f0150ba5074d — a READABLE-named governed file must recycle BY UID.

    THE DEFECT, filed by argus-a167 after recycling a probe one minute after minting it:
    the uid branch searched for `<uid>.md` and nothing else, so every file
    `tropo-mint-id.py --title` produces was invisible to it. SKIP, `Recycled 0/1`,
    exit 0 — quiet enough that a script would not stop.

    WHY IT IS WORSE THAN A MISSING FEATURE. Deletion Discipline (0aefe71d, Mike-pinned)
    says never `rm`, always recycle. The canonical AUTHORING path was producing files the
    canonical DELETION path could not address, so an agent obeying both rules correctly
    ends up unable to delete what it just made — and the honest end of that road is
    somebody reaching for `rm`, the one thing the discipline exists to prevent.

    EVERY TEST HERE CARRIES ITS MUTATION CONTROL, matching this module's standing
    discipline: the pre-fix behaviour is reproduced exactly and must NOT resolve the
    file. Argus's filing named this as the part that matters most, and said why — the
    current behaviour would pass a naive test written against bare-named fixtures, which
    is exactly how the defect survived readable minting shipping.
    """

    SLUG_NAME = "a-readable-slug-name"
    SLUG_UID = "f0157102b973"

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

    def _slug_entry(self, subdir="files", slug=None, uid=None) -> Path:
        slug = slug or self.SLUG_NAME
        uid = uid or self.SLUG_UID
        p = self.root / "vault" / subdir / f"{slug}-{uid}.md"
        p.write_text(f"---\nuid: '{uid}'\ntype: note\n---\n# probe\n", encoding="utf-8")
        return p

    @staticmethod
    def _pre_fix_lookup(uid, search_paths):
        """The tool's behaviour before this cure: bare stem only.

        Reproduced here rather than described, so every control below measures the real
        old lookup instead of a paraphrase of it.
        """
        return [d / f"{uid}.md" for d in search_paths if (d / f"{uid}.md").exists()]

    def test_a_slug_named_file_recycles_by_uid(self):
        src = self._slug_entry()
        ok, msg = recycle.recycle_uid(self.SLUG_UID, "test", self.dest)
        self.assertTrue(ok, f"the canonical deletion path cannot address a canonically "
                            f"minted file: {msg}")
        self.assertFalse(src.exists(), "the source should have moved")

    def test_it_would_have_failed_under_the_old_bare_stem_lookup(self):
        """THE CONTROL. Without it this suite passes against the bug it describes."""
        self._slug_entry()
        old = self._pre_fix_lookup(self.SLUG_UID, recycle.uid_search_paths())
        self.assertEqual(
            old, [],
            "the pre-fix bare-stem lookup already found the slug-named file, so the fix "
            "changed nothing and every assertion in this class proves nothing")

    def test_the_readable_name_is_preserved_in_the_bin(self):
        """Recycling the same file BY UID and BY PATH must land it under one name.

        The explicit-path branch sets `uid = src.stem`, so a path-recycled file keeps its
        readable name. If the uid branch forced `<uid>.md`, the same file would land under
        two different names depending on which argument the caller used — one fact, two
        behaviours, in the tool whose entire job is that nothing is lost.
        """
        self._slug_entry()
        ok, _ = recycle.recycle_uid(self.SLUG_UID, "test", self.dest)
        self.assertTrue(ok)
        landed = sorted(p.name for p in self.dest.glob("*.md"))
        self.assertEqual(
            landed, [f"{self.SLUG_NAME}-{self.SLUG_UID}.md"],
            "the readable name was not preserved in the recycle bin")

    def test_bare_named_files_still_resolve(self):
        """The regression arm: the fast path must not have been traded away."""
        p = self.root / "vault" / "files" / "bbbbbbbb.md"
        p.write_text("---\nuid: bbbbbbbb\n---\n", encoding="utf-8")
        ok, msg = recycle.recycle_uid("bbbbbbbb", "test", self.dest)
        self.assertTrue(ok, msg)
        self.assertTrue((self.dest / "bbbbbbbb.md").exists())

    def test_slug_resolution_reaches_every_uid_bearing_directory(self):
        """Not just vault/files/ — the 2c6afe9e property applies to both shapes."""
        for i, subdir in enumerate(UID_DIRS):
            uid = f"cccccc{i:02d}0000"[:12]
            self._slug_entry(subdir=subdir, slug=f"probe-{i}", uid=uid)
            ok, msg = recycle.recycle_uid(uid, "test", self.dest)
            self.assertTrue(ok, f"slug-named file in vault/{subdir}/ unreachable: {msg}")

    def test_one_uid_in_two_shapes_refuses_rather_than_guessing(self):
        """The ambiguity the fix could have introduced, closed deliberately.

        A bare `<uid>.md` and a `<slug>-<uid>.md` are two homes for one uid. Picking
        either silently would soft-delete a file the caller did not name — the same
        reasoning the existing cross-directory refusal already carries.
        """
        bare = self.root / "vault" / "files" / f"{self.SLUG_UID}.md"
        bare.write_text(f"---\nuid: '{self.SLUG_UID}'\n---\n", encoding="utf-8")
        slugged = self._slug_entry()

        ok, msg = recycle.recycle_uid(self.SLUG_UID, "test", self.dest)
        self.assertFalse(ok, "two files claim this uid; picking one is not a resolution")
        self.assertIn("REFUSED", msg)
        self.assertTrue(bare.exists() and slugged.exists(),
                        "a refusal must not move anything")

    def test_a_uid_that_is_merely_a_substring_is_not_matched(self):
        """Anchoring, not searching. `*-<uid>.md` must not match `<uid>extra.md` or a
        file whose stem merely CONTAINS the uid — that would soft-delete a stranger."""
        decoy = self.root / "vault" / "files" / f"prefix-{self.SLUG_UID}extra.md"
        decoy.write_text("---\nuid: 'other'\n---\n", encoding="utf-8")
        ok, msg = recycle.recycle_uid(self.SLUG_UID, "test", self.dest)
        self.assertFalse(ok, f"a non-matching file was resolved: {msg}")
        self.assertTrue(decoy.exists(), "a decoy must never be moved")

