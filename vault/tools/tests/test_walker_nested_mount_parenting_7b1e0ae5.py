#!/usr/bin/env python3
"""AC3 — hierarchy-preserving mirror parenting under a mount (7b1e0ae5 §3.3).

The defect this pins: the import walker hardcoded every new folder mirror to the
Tropo Work hub (``2d083137``), so an entire mounted OneDrive tree filed itself
under Tropo's own internal work substrate. §3.3 replaces that default with
``resolve_mirror_parent_member``.

Two assertions carry the weight, and they fail to different mutations:

* **top mirror → mount** dies if the argument fix is reverted (the flat defect);
* **nested mirror → its parent folder's mirror** dies if the parent-chain lookup
  is flattened — the assertion the first draft of this spec could not detect,
  because a flattening resolver still keeps every mirror off Tropo Work.

The in-tree negative control is what stops the fix from becoming "never use
Tropo Work again": an ordinary in-tree root import must still parent there.
"""

from __future__ import annotations

import ast
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"

SPEC = importlib.util.spec_from_file_location(
    "tropo_import_walker_nested_contract",
    TOOLS / "tropo-import-walker.py",
)
WALKER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = WALKER
SPEC.loader.exec_module(WALKER)

TROPO_WORK = "2d083137"
MOUNT_UID = "aa11bb22"


class NestedMountParentingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="walker-nested-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.studio = self.tmp / "studio"
        (self.studio / "vault" / "files").mkdir(parents=True)
        self.mount_root = self.tmp / "external" / "share"
        (self.mount_root / "projects" / "q3").mkdir(parents=True)

    def marker_uid_for(self, folder: Path, uid: str, parent_member: str) -> None:
        """Write the on-disk folder marker the walker reads for the chain."""
        WALKER.write_folder_marker(
            folder,
            uid,
            folder.name,
            str(folder / ".tropo-studio" / ".tropo-folder.md"),
            parent_member=parent_member,
        )

    # -- the two positive assertions ------------------------------------- #

    def test_top_level_mirror_parents_to_the_mount(self):
        """`share/projects` is a child of the mount root: parent is the mount."""
        parent = WALKER.resolve_mirror_parent_member(
            self.mount_root / "projects", self.studio, MOUNT_UID
        )
        self.assertEqual(parent, MOUNT_UID)
        self.assertNotEqual(
            parent, TROPO_WORK, "a mounted mirror must never file under Tropo Work"
        )

    def test_nested_mirror_parents_to_its_parent_folders_mirror(self):
        """`share/projects/q3` parents to `projects`'s mirror, not flat to the mount."""
        projects = self.mount_root / "projects"
        self.marker_uid_for(projects, "cc33dd44", MOUNT_UID)

        parent = WALKER.resolve_mirror_parent_member(
            projects / "q3", self.studio, MOUNT_UID
        )

        self.assertEqual(
            parent,
            "cc33dd44",
            "the nested mirror flattened onto the mount instead of chaining to "
            "its parent folder's mirror",
        )

    def test_marker_mirror_and_resolver_agree_on_the_chain(self):
        """The marker the walker wrote is the same uid the resolver returns."""
        projects = self.mount_root / "projects"
        self.marker_uid_for(projects, "cc33dd44", MOUNT_UID)
        marker = projects / ".tropo-studio" / ".tropo-folder.md"
        self.assertTrue(marker.is_file())

        front = WALKER.parse_frontmatter(marker)
        self.assertEqual(front.get("uid"), "cc33dd44")
        self.assertRegex(str(front.get("uid")), r"^[0-9a-f]{8}$")
        member_of = front.get("member_of") or []
        if isinstance(member_of, str):
            member_of = [member_of]
        self.assertIn(
            MOUNT_UID,
            [str(m) for m in member_of],
            "the top mirror's own marker must record the mount as its parent",
        )
        self.assertNotIn(TROPO_WORK, [str(m) for m in member_of])

        self.assertEqual(
            WALKER.resolve_mirror_parent_member(projects / "q3", self.studio, MOUNT_UID),
            front.get("uid"),
            "resolver and on-disk marker disagree about the chain",
        )

    def test_no_mounted_mirror_resolves_to_tropo_work(self):
        """Sweep: nothing under a mount, at any depth, files under Tropo Work."""
        projects = self.mount_root / "projects"
        self.marker_uid_for(projects, "cc33dd44", MOUNT_UID)
        deep = projects / "q3" / "drafts"
        deep.mkdir(parents=True)
        self.marker_uid_for(projects / "q3", "ee55ff66", "cc33dd44")

        resolved = [
            WALKER.resolve_mirror_parent_member(folder, self.studio, MOUNT_UID)
            for folder in (projects, projects / "q3", deep)
        ]

        self.assertEqual(resolved, [MOUNT_UID, "cc33dd44", "ee55ff66"])
        self.assertNotIn(TROPO_WORK, resolved)

    # -- the negative control -------------------------------------------- #

    def test_in_tree_root_level_import_still_parents_to_tropo_work(self):
        """Unmounted, directly under the studio root: Tropo Work is correct."""
        in_tree = self.studio / "04-external-work"
        in_tree.mkdir(parents=True)

        self.assertEqual(
            WALKER.resolve_mirror_parent_member(in_tree, self.studio, None),
            TROPO_WORK,
            "the fix must not remove Tropo Work as the in-tree default",
        )

    def test_unmounted_nested_folder_without_a_marker_falls_back_to_tropo_work(self):
        """No mount, no parent marker: the fallback is the hub, not a guess."""
        nested = self.studio / "04-external-work" / "loose"
        nested.mkdir(parents=True)

        self.assertEqual(
            WALKER.resolve_mirror_parent_member(nested, self.studio, None),
            TROPO_WORK,
        )

    # -- mutation control ------------------------------------------------- #

    def test_flattening_the_resolver_goes_red_on_the_nested_assertion(self):
        """Mutation: a resolver that always returns the mount must fail AC3.

        This is the control Argus required. A flat resolver keeps every mirror
        off Tropo Work — so the Tropo Work sweep above stays green under it —
        and only the parent-chain assertion detects the flattening.
        """
        projects = self.mount_root / "projects"
        self.marker_uid_for(projects, "cc33dd44", MOUNT_UID)

        def flat_resolver(parent_folder, studio_root, mount_uid):
            return mount_uid or TROPO_WORK

        mutant = flat_resolver(projects / "q3", self.studio, MOUNT_UID)
        real = WALKER.resolve_mirror_parent_member(
            projects / "q3", self.studio, MOUNT_UID
        )

        self.assertEqual(mutant, MOUNT_UID)
        self.assertNotEqual(
            mutant,
            real,
            "the flattening mutant produced the same answer as the real "
            "resolver — the nested assertion cannot detect the defect it exists "
            "to catch",
        )
        self.assertEqual(real, "cc33dd44")

    def test_no_mirror_writing_call_site_hardcodes_the_hub(self):
        """Guard the wiring, structurally: reads the shipped source with AST.

        A correct resolver is worth nothing if a call site still passes
        ``TROPO_WORK_L0_UID``, or silently takes the signature default. The
        distinction matters: a *signature* default is fine (in-tree callers rely
        on it); a *mirror-creating call* that leans on it is the original defect.
        """
        source = (TOOLS / "tropo-import-walker.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertIn("def resolve_mirror_parent_member(", source)

        # Writers that put a parent edge into a mirror's frontmatter or index row.
        parenting_writers = {
            "write_folder_marker",
            "write_folder_mirror",
            "append_folder_mirror_index_row",
        }
        offenders = []
        seen = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in parenting_writers:
                continue
            seen.add(name)
            passed = None
            for keyword in node.keywords:
                if keyword.arg == "parent_member":
                    passed = ast.unparse(keyword.value)
            if passed is None:
                offenders.append(f"{name}@{node.lineno}: relies on the hub default")
            elif "TROPO_WORK_L0_UID" in passed:
                offenders.append(f"{name}@{node.lineno}: hardcodes {passed}")

        self.assertEqual(
            seen,
            parenting_writers,
            "a parenting writer disappeared; the guard is watching a stale set",
        )
        self.assertEqual(
            offenders,
            [],
            "mirror-creating call site(s) do not pass a resolved parent: "
            + "; ".join(offenders),
        )

    def test_members_rebuild_preserves_the_mount_parent_in_frontmatter(self):
        """`rebuild_folder_mirror` keeps its hub default out of an existing mirror.

        It is the one mirror writer that takes ``parent_member`` and is called
        without one. That is only safe because it regenerates the ## Members
        body and never rewrites the parent edge — so assert the behaviour rather
        than trusting the comment that says so.
        """
        files = self.studio / "vault" / "files"
        mirror = files / "cc33dd44.md"
        mirror.write_text(
            "---\n"
            "uid: cc33dd44\n"
            "type: project\n"
            "title: projects\n"
            f"mount_uid: {MOUNT_UID}\n"
            "member_of:\n"
            f"  - {MOUNT_UID}\n"
            "modified: 2026-01-01\n"
            "modified_by: seed\n"
            "---\n"
            "\n# projects\n\n## Members\n\n(none)\n\n*Mirror authored by seed.*\n",
            encoding="utf-8",
        )
        (self.studio / "vault" / "00-index.jsonl").write_text("", encoding="utf-8")

        rebuilt = WALKER.rebuild_folder_mirror(
            studio_root=self.studio,
            folder_uid="cc33dd44",
            folder_name="projects",
            original_path="external/share/projects",
            folder_marker_path_rel="external/share/projects/.tropo-studio/.tropo-folder.md",
        )

        self.assertTrue(rebuilt)
        text = mirror.read_text(encoding="utf-8")
        front = text.split("---", 2)[1]
        self.assertIn(MOUNT_UID, front, "the members rebuild dropped the mount parent")
        self.assertNotIn(
            TROPO_WORK,
            front,
            "the members rebuild leaked its Tropo Work signature default into an "
            "existing mounted mirror",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
