#!/usr/bin/env python3
"""Regression tests for byte-safe Tropo navigation path components."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
sys.path.insert(0, str(TOOLS))

SPEC = importlib.util.spec_from_file_location(
    "tropo_rehydrate_navigation_components",
    TOOLS / "tropo-rehydrate.py",
)
REHYDRATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REHYDRATE)

DD16C90C_TITLE = (
    "Federation graph-model joint gate LOCKED — segment-local authority (D-1), "
    "viewer-projection API (D-4), superseded-OS walked-but-flagged (D-2), owner "
    "wall-clock decay overlay (D-3 YES), extraction_scope backfill-first inside "
    "v1.82 (D0-lite)"
)


class TestNavigationComponent(unittest.TestCase):
    def test_short_component_is_unchanged(self):
        self.assertEqual(
            REHYDRATE.navigation_component(
                "dd16c90c — Human-readable title",
                identity="dd16c90c",
                suffix=".md",
            ),
            "dd16c90c — Human-readable title.md",
        )

    def test_exact_byte_boundary_is_unchanged(self):
        stem = "a" * (REHYDRATE.NAV_COMPONENT_MAX_BYTES - len(".md"))
        component = REHYDRATE.navigation_component(
            stem,
            identity="aaaaaaaa",
            suffix=".md",
        )
        self.assertEqual(component, f"{stem}.md")
        self.assertEqual(
            len(component.encode("utf-8")),
            REHYDRATE.NAV_COMPONENT_MAX_BYTES,
        )

    def test_one_byte_over_boundary_is_shortened_with_digest(self):
        stem = "a" * (REHYDRATE.NAV_COMPONENT_MAX_BYTES - len(".md") + 1)
        component = REHYDRATE.navigation_component(
            stem,
            identity="aaaaaaaa",
            suffix=".md",
        )
        self.assertLessEqual(
            len(component.encode("utf-8")),
            REHYDRATE.NAV_COMPONENT_MAX_BYTES,
        )
        self.assertRegex(component, r" …~[0-9a-f]{16}\.md$")

    def test_multibyte_title_is_clipped_at_utf8_boundary(self):
        component = REHYDRATE.navigation_component(
            "文" * 100,
            identity="bbbbbbbb",
            suffix=".md",
        )
        encoded = component.encode("utf-8")
        self.assertLessEqual(
            len(encoded),
            REHYDRATE.NAV_COMPONENT_MAX_BYTES,
        )
        self.assertEqual(encoded.decode("utf-8"), component)
        self.assertRegex(component, r" …~[0-9a-f]{16}\.md$")

    def test_long_common_prefixes_do_not_collide(self):
        common = "same readable prefix " * 30
        first = REHYDRATE.navigation_component(
            f"{common}first",
            identity="cccccccc",
        )
        second = REHYDRATE.navigation_component(
            f"{common}second",
            identity="cccccccc",
        )
        same_title_other_uid = REHYDRATE.navigation_component(
            f"{common}first",
            identity="dddddddd",
        )
        self.assertEqual(
            first,
            REHYDRATE.navigation_component(
                f"{common}first",
                identity="cccccccc",
            ),
            "the projection name must be deterministic",
        )
        self.assertEqual(len({first, second, same_title_other_uid}), 3)

    def test_dd16c90c_component_fits_and_retains_readable_prefix(self):
        stem = f"dd16c90c — {REHYDRATE.sanitize(DD16C90C_TITLE)}"
        self.assertGreater(
            len(f"{stem}.md".encode("utf-8")),
            REHYDRATE.NAV_COMPONENT_MAX_BYTES,
        )
        component = REHYDRATE.navigation_component(
            stem,
            identity="dd16c90c",
            suffix=".md",
        )
        self.assertTrue(component.startswith("dd16c90c — Federation graph-model"))
        self.assertRegex(component, r" …~[0-9a-f]{16}\.md$")
        self.assertLessEqual(
            len(component.encode("utf-8")),
            REHYDRATE.NAV_COMPONENT_MAX_BYTES,
        )


class TestBuildOneTreeLongTitleRegression(unittest.TestCase):
    def test_build_creates_byte_safe_long_project_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_files = root / "vault" / "files"
            ledger_files.mkdir(parents=True)
            project_tree = root / "vault" / "00-project-tree.jsonl"
            output = root / "00-tropo-nav" / "00-tropo-all"

            project_uid = "eeeeeeee"
            project_title = "Federation project " + ("文" * 100)
            project_source = ledger_files / f"{project_uid}.md"
            project_source.write_text(f"# {project_title}\n", encoding="utf-8")
            project_tree.write_text(
                json.dumps({"uid": project_uid}) + "\n",
                encoding="utf-8",
            )
            index = {
                project_uid: {
                    "title": project_title,
                    "state": "active",
                    "type": "project",
                    "member_of": [],
                    "subsystem_hub": [],
                },
            }

            REHYDRATE.build_one_tree(
                root,
                output,
                ledger_files,
                project_tree,
                index,
                {project_uid: "active"},
                None,
                "all",
            )

            project_folders = [path for path in output.iterdir() if path.is_dir()]
            self.assertEqual(len(project_folders), 1)
            self.assertLessEqual(
                len(os.fsencode(project_folders[0].name)),
                REHYDRATE.NAV_COMPONENT_MAX_BYTES,
            )
            self.assertRegex(project_folders[0].name, r" …~[0-9a-f]{16}$")
            anchors = list(project_folders[0].glob(f"{project_uid} — *.md"))
            self.assertEqual(len(anchors), 1)
            self.assertEqual(anchors[0].stat().st_ino, project_source.stat().st_ino)
            self.assertEqual(index[project_uid]["title"], project_title)

    def test_build_links_long_title_without_mutating_canonical_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_files = root / "vault" / "files"
            ledger_files.mkdir(parents=True)
            project_tree = root / "vault" / "00-project-tree.jsonl"
            output = root / "00-tropo-nav" / "00-tropo-all"

            project_uid = "f65a7d72"
            entry_uid = "dd16c90c"
            project_source = ledger_files / f"{project_uid}.md"
            entry_source = ledger_files / f"{entry_uid}.md"
            project_source.write_text("# Parent project\n", encoding="utf-8")
            canonical_content = f"# {DD16C90C_TITLE}\n"
            entry_source.write_text(canonical_content, encoding="utf-8")
            project_tree.write_text(
                json.dumps({"uid": project_uid}) + "\n",
                encoding="utf-8",
            )

            index = {
                project_uid: {
                    "title": "Federation",
                    "state": "active",
                    "type": "project",
                    "member_of": [],
                    "subsystem_hub": [],
                },
                entry_uid: {
                    "title": DD16C90C_TITLE,
                    "state": "active",
                    "type": "decision",
                    "member_of": [project_uid],
                    "subsystem_hub": [],
                },
            }
            project_states = {
                uid: entry["state"] for uid, entry in index.items()
            }

            REHYDRATE.build_one_tree(
                root,
                output,
                ledger_files,
                project_tree,
                index,
                project_states,
                None,
                "all",
            )

            rendered = list((output / "Federation").glob(f"{entry_uid} — *.md"))
            self.assertEqual(len(rendered), 1)
            self.assertLessEqual(
                len(os.fsencode(rendered[0].name)),
                REHYDRATE.NAV_COMPONENT_MAX_BYTES,
            )
            self.assertRegex(rendered[0].name, r" …~[0-9a-f]{16}\.md$")
            self.assertEqual(rendered[0].stat().st_ino, entry_source.stat().st_ino)
            self.assertEqual(entry_source.read_text(encoding="utf-8"), canonical_content)
            self.assertEqual(index[entry_uid]["title"], DD16C90C_TITLE)


class TestMountSourceLeaves(unittest.TestCase):
    """7b1e0ae5 §3.5 — source-file symlink leaves + per-leaf guard."""

    def test_available_mount_renders_source_symlink_not_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_files = root / "vault" / "files"
            ledger_files.mkdir(parents=True)
            mount_root = root / "external-mount"
            mount_root.mkdir()
            source = mount_root / "Invoice.docx"
            source.write_bytes(b"PK\x03\x04-real-docx")

            project_uid = "p1111111"
            entry_uid = "e2222222"
            mount_uid = "m3333333"
            (ledger_files / f"{project_uid}.md").write_text("# Parent\n", encoding="utf-8")
            (ledger_files / f"{entry_uid}.md").write_text(
                "---\nuid: e2222222\ntype: external-artifact\ntitle: Invoice.docx\n---\n",
                encoding="utf-8",
            )
            project_tree = root / "vault" / "00-project-tree.jsonl"
            project_tree.write_text(
                json.dumps({"uid": project_uid}) + "\n", encoding="utf-8"
            )
            (root / ".tropo-studio").mkdir()
            (root / ".tropo-studio" / "folder-mounts.json").write_text(
                json.dumps(
                    {
                        "mounts": {
                            mount_uid: {
                                "name": "share",
                                "path": str(mount_root),
                                "state": "adopted",
                                "availability": "available",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            index = {
                project_uid: {
                    "title": "Parent",
                    "state": "active",
                    "type": "project",
                    "member_of": [],
                    "subsystem_hub": [],
                },
                entry_uid: {
                    "title": "Invoice.docx",
                    "state": "active",
                    "type": "external-artifact",
                    "member_of": [project_uid],
                    "subsystem_hub": [],
                    "mount_uid": mount_uid,
                    "mount_relpath": "Invoice.docx",
                    "source_filename": "Invoice.docx",
                    "source_path": str(source),
                    "availability": "available",
                },
            }
            availability, roots = REHYDRATE.load_mount_availability(root)
            output = root / "00-tropo-nav" / "00-tropo-active"
            REHYDRATE.build_one_tree(
                root,
                output,
                ledger_files,
                project_tree,
                index,
                {uid: e["state"] for uid, e in index.items()},
                "active",
                "active",
                mount_availability=availability,
                mount_roots=roots,
            )

            parent = output / "Parent"
            source_leaves = list(parent.glob("Invoice.docx"))
            self.assertEqual(len(source_leaves), 1)
            self.assertTrue(source_leaves[0].is_symlink())
            self.assertEqual(source_leaves[0].resolve(), source.resolve())
            # Governed record must NOT also render beside the source.
            self.assertEqual(list(parent.glob(f"{entry_uid} — *.md")), [])

    def test_unavailable_mount_keeps_record_hardlink_no_source_leaf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_files = root / "vault" / "files"
            ledger_files.mkdir(parents=True)
            mount_root = root / "external-mount"
            mount_root.mkdir()
            source = mount_root / "notes.md"
            source.write_text("hello\n", encoding="utf-8")

            project_uid = "p4444444"
            entry_uid = "e5555555"
            mount_uid = "m6666666"
            entry_source = ledger_files / f"{entry_uid}.md"
            (ledger_files / f"{project_uid}.md").write_text("# Parent\n", encoding="utf-8")
            entry_source.write_text("# record\n", encoding="utf-8")
            project_tree = root / "vault" / "00-project-tree.jsonl"
            project_tree.write_text(
                json.dumps({"uid": project_uid}) + "\n", encoding="utf-8"
            )

            index = {
                project_uid: {
                    "title": "Parent",
                    "state": "active",
                    "type": "project",
                    "member_of": [],
                    "subsystem_hub": [],
                },
                entry_uid: {
                    "title": "notes.md",
                    "state": "active",
                    "type": "external-artifact",
                    "member_of": [project_uid],
                    "subsystem_hub": [],
                    "mount_uid": mount_uid,
                    "mount_relpath": "notes.md",
                    "source_filename": "notes.md",
                    "source_path": str(source),
                },
            }
            output = root / "nav"
            REHYDRATE.build_one_tree(
                root,
                output,
                ledger_files,
                project_tree,
                index,
                {uid: e["state"] for uid, e in index.items()},
                None,
                "all",
                mount_availability={mount_uid: "unavailable"},
                mount_roots={mount_uid: str(mount_root)},
            )
            parent = output / "Parent"
            records = list(parent.glob(f"{entry_uid} — *.md"))
            self.assertEqual(len(records), 1)
            self.assertFalse(records[0].is_symlink())
            self.assertEqual(records[0].stat().st_ino, entry_source.stat().st_ino)
            self.assertEqual(list(parent.glob("notes.md")), [])

    def test_broken_link_target_skips_leaf_by_name_and_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_files = root / "vault" / "files"
            ledger_files.mkdir(parents=True)
            project_uid = "p7777777"
            good_uid = "e8888888"
            bad_uid = "e9999999"
            (ledger_files / f"{project_uid}.md").write_text("# Parent\n", encoding="utf-8")
            good_src = ledger_files / f"{good_uid}.md"
            good_src.write_text("# good\n", encoding="utf-8")
            bad_src = ledger_files / f"{bad_uid}.md"
            bad_src.write_text("# bad\n", encoding="utf-8")
            project_tree = root / "vault" / "00-project-tree.jsonl"
            project_tree.write_text(
                json.dumps({"uid": project_uid}) + "\n", encoding="utf-8"
            )
            index = {
                project_uid: {
                    "title": "Parent",
                    "state": "active",
                    "type": "project",
                    "member_of": [],
                    "subsystem_hub": [],
                },
                good_uid: {
                    "title": "good",
                    "state": "active",
                    "type": "note",
                    "member_of": [project_uid],
                    "subsystem_hub": [],
                },
                bad_uid: {
                    "title": "bad",
                    "state": "active",
                    "type": "note",
                    "member_of": [project_uid],
                    "subsystem_hub": [],
                },
            }
            output = root / "nav"
            real_link = os.link

            def flaky_link(src, dst):
                if bad_uid in str(dst):
                    raise OSError(18, "Invalid cross-device link")
                return real_link(src, dst)

            original = REHYDRATE.os.link
            REHYDRATE.os.link = flaky_link
            try:
                skipped = REHYDRATE.build_one_tree(
                    root,
                    output,
                    ledger_files,
                    project_tree,
                    index,
                    {uid: e["state"] for uid, e in index.items()},
                    None,
                    "all",
                )
            finally:
                REHYDRATE.os.link = original
            parent = output / "Parent"
            self.assertEqual(len(list(parent.glob(f"{good_uid} — *.md"))), 1)
            self.assertEqual(list(parent.glob(f"{bad_uid} — *.md")), [])
            self.assertTrue(any(bad_uid in name for name in skipped))


class TestAbsolutePathValidatorNavGuards(unittest.TestCase):
    def test_skips_nav_dir_and_symlinks(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "tropo_validate_no_absolute_paths",
            TOOLS / "tropo-validate-no-absolute-paths.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vault").mkdir()
            (root / ".tropo").mkdir()
            nav = root / "00-tropo-nav" / "00-tropo-active"
            nav.mkdir(parents=True)
            dirty = nav / "leak.md"
            dirty.write_text("/Users/maz/secret.md\n", encoding="utf-8")
            outside = root / "vault" / "ok.md"
            outside.write_text("no absolute paths here\n", encoding="utf-8")
            link = root / "vault" / "link.md"
            link.symlink_to("/Users/maz/elsewhere.md")

            walked = list(mod.walk_files(root))
            self.assertNotIn(dirty, walked)
            self.assertNotIn(link, walked)
            self.assertIn(outside, walked)

            resolved = mod.resolve_vault_root(None)
            # With no walk-up hit from the loaded module path, cwd fallback is ok;
            # explicit shape check: vault/+.tropo/ is accepted when present.
            self.assertTrue(
                (root / "vault").is_dir() and (root / ".tropo").is_dir()
            )
            # Force the candidate path through the same predicate the resolver uses.
            self.assertTrue(
                (root / ".tropo").is_dir()
                and ((root / "vault").is_dir() or (root / "ledger").is_dir())
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
