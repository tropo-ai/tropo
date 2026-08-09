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


if __name__ == "__main__":
    unittest.main(verbosity=2)
