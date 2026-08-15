"""Plant tests for ADR-047 Layer-1 current/archive index separation."""

from __future__ import annotations

import contextlib
import json
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib import index_surfaces  # noqa: E402

_rebuild_spec = importlib.util.spec_from_file_location(
    "tropo_rebuild_index_adr047", TOOLS_DIR / "tropo-rebuild-index.py"
)
assert _rebuild_spec and _rebuild_spec.loader
rebuild_index_module = importlib.util.module_from_spec(_rebuild_spec)
# Register before exec_module: code running at module scope may look itself up
# in sys.modules. @dataclass does exactly that, and an unregistered module
# makes it raise AttributeError on None before any test can run.
sys.modules[_rebuild_spec.name] = rebuild_index_module
_rebuild_spec.loader.exec_module(rebuild_index_module)

_orient_spec = importlib.util.spec_from_file_location(
    "tropo_orient_title_preservation", TOOLS_DIR / "tropo-orient.py"
)
assert _orient_spec and _orient_spec.loader
orient_module = importlib.util.module_from_spec(_orient_spec)
sys.modules[_orient_spec.name] = orient_module
_orient_spec.loader.exec_module(orient_module)

_kernel_spec = importlib.util.spec_from_file_location(
    "tropo_register_kernel_title_preservation",
    TOOLS_DIR / "tropo-register-kernel.py",
)
assert _kernel_spec and _kernel_spec.loader
kernel_module = importlib.util.module_from_spec(_kernel_spec)
sys.modules[_kernel_spec.name] = kernel_module
_kernel_spec.loader.exec_module(kernel_module)


def _uids(path: Path) -> set[str]:
    return {
        str(record["uid"])
        for record in index_surfaces.iter_jsonl(path)
        if record.get("uid")
    }


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )


#: Every index surface `tropo-orient` resolves over. Named in one place because
#: `_records()` reads the UNION of current and archive (ADR-047), and a test that
#: redirects only some of them silently measures the live vault through the rest.
_ORIENT_SURFACES = ("INDEX_JSONL", "ARCHIVE_INDEX_JSONL", "INDEX_SQLITE")


def _orient_isolated(root: Path):
    """Point every orient surface inside `root`, so a fixture is the whole world.

    This exists because of a real failure, not a hypothetical one. Both orient
    tests below patched `INDEX_JSONL` and left `ARCHIVE_INDEX_JSONL` aimed at the
    developer's own vault, so `_records()` returned the fixture UNION 1,805 live
    archive rows.

    What made it survive a full release is that the archive index is a DERIVED,
    gitignored file: absent on a fresh clone, so the union was the fixture and
    the suite was green; present the moment anyone runs a full rebuild, and red
    from then on. A test whose correctness depends on a build artifact being
    missing passes exactly where nobody is working.

    Patching by name from one list means a fourth surface cannot be forgotten in
    one test and remembered in the other.
    """
    patches = [
        mock.patch.object(orient_module, "ROOT", root),
    ]
    for name in _ORIENT_SURFACES:
        current = getattr(orient_module, name)
        patches.append(
            mock.patch.object(orient_module, name, root / "vault" / current.name)
        )
    return patches


class ArchiveIndexSplitTests(unittest.TestCase):
    def test_control_orient_isolation_actually_hides_the_live_vault(self) -> None:
        """The control for `_orient_isolated`, and the regression pin.

        Asserts the escape route is closed rather than trusting that it is: with
        the helper active over an empty fixture, `_records()` must be EMPTY. If a
        surface is ever added to orient and not to `_ORIENT_SURFACES`, this fails
        here — next to the reason — instead of somewhere downstream as a puzzling
        set mismatch.
        """
        self.assertTrue(
            orient_module.ARCHIVE_INDEX_JSONL.name.endswith(".jsonl"),
            "the archive surface must still be a real attribute to redirect",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vault").mkdir(parents=True)
            with contextlib.ExitStack() as stack:
                for patch in _orient_isolated(root):
                    stack.enter_context(patch)
                self.assertEqual(orient_module._records(), {})

    def test_yaml_single_quoted_live_title_shapes_share_one_canonical_projection(
        self,
    ) -> None:
        cases = (
            (
                "'Boot-Protocol + Memory-System Hardening — three coupled gaps: "
                "dead-path-rot, recommended-not-gated reads, learnings-don''t-feed-back "
                "(Talos T11 + Vela V55 diagnosis 2026-05-29)'",
                "Boot-Protocol + Memory-System Hardening — three coupled gaps: "
                "dead-path-rot, recommended-not-gated reads, learnings-don't-feed-back "
                "(Talos T11 + Vela V55 diagnosis 2026-05-29)",
            ),
            (
                "'Proposal for Argus + Talos — Make All Entries Openable: emit a "
                "UID→source_path map at vault-rebuild (the ''all walkable'' gap)'",
                "Proposal for Argus + Talos — Make All Entries Openable: emit a "
                "UID→source_path map at vault-rebuild (the 'all walkable' gap)",
            ),
            (
                "'The Toolbelt — mirror the Claude Code harness pattern: 10-15 core "
                "tools loaded at boot, one lookup verb for the rest, skills migrated + "
                "named ''skill'' everywhere (the un-built 4th Pillar-1 surface)'",
                "The Toolbelt — mirror the Claude Code harness pattern: 10-15 core "
                "tools loaded at boot, one lookup verb for the rest, skills migrated + "
                "named 'skill' everywhere (the un-built 4th Pillar-1 surface)",
            ),
            (
                "'Verification-Command Hardening (v1.64) — Test-Spec: vc:true gate "
                "steps bind to a machine verdict, not an agent''s word'",
                "Verification-Command Hardening (v1.64) — Test-Spec: vc:true gate "
                "steps bind to a machine verdict, not an agent's word",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = root / "vault" / "files"
            tools = root / "vault" / "tools"
            files.mkdir(parents=True)
            tools.mkdir()
            expected_by_uid: dict[str, str] = {}

            for index, (yaml_title, expected_title) in enumerate(cases, 1):
                markdown_uid = f"{index:08x}"
                tool_uid = f"{index + len(cases):08x}"
                markdown_source = files / f"{markdown_uid}.md"
                markdown_source.write_text(
                    "---\n"
                    f"uid: {markdown_uid}\n"
                    "type: note\n"
                    f"title: {yaml_title} # trailing YAML comment\n"
                    "state: active\n"
                    "status: active\n"
                    "---\n\n"
                    "# fixture\n",
                    encoding="utf-8",
                )
                tool_source = tools / f"tool-{index}.py"
                tool_source.write_text(
                    '"""---\n'
                    f"uid: {tool_uid}\n"
                    "type: tool\n"
                    f"title: {yaml_title} # trailing YAML comment\n"
                    "state: active\n"
                    "status: active\n"
                    "---\n"
                    '"""\n',
                    encoding="utf-8",
                )

                markdown_record = rebuild_index_module.process_file(markdown_source)
                tool_record = rebuild_index_module.process_tool_file(tool_source)
                self.assertIsNotNone(markdown_record)
                self.assertIsNotNone(tool_record)
                with self.subTest(index=index, source_kind="markdown-jsonl"):
                    self.assertEqual(markdown_record["title"], expected_title)
                with self.subTest(index=index, source_kind="tool-jsonl"):
                    self.assertEqual(tool_record["title"], expected_title)

                for source_kind, record in (
                    ("markdown", markdown_record),
                    ("tool", tool_record),
                ):
                    entry_row, _edge_rows, fts_row = (
                        rebuild_index_module._record_to_index_rows(record, files)
                    )
                    with self.subTest(index=index, source_kind=source_kind):
                        self.assertEqual(entry_row[2], expected_title)
                        self.assertEqual(fts_row[1], expected_title)
                expected_by_uid[markdown_uid] = expected_title
                expected_by_uid[tool_uid] = expected_title

            index_path = root / "vault" / "00-index.jsonl"
            records = [
                {"uid": uid, "title": title}
                for uid, title in expected_by_uid.items()
            ]
            _write(index_path, records)
            with contextlib.ExitStack() as stack:
                for patch in _orient_isolated(root):
                    stack.enter_context(patch)
                orient_records = orient_module._records()
            self.assertEqual(
                {uid: record["title"] for uid, record in orient_records.items()},
                expected_by_uid,
            )

    def test_title_is_lossless_across_source_kinds_jsonl_sqlite_fts_and_orient(
        self,
    ) -> None:
        long_title = "title-" + ("x" * 140)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = root / "vault" / "files"
            tools = root / "vault" / "tools"
            files.mkdir(parents=True)
            tools.mkdir()

            source = files / "00000001.md"
            source.write_text(
                "---\n"
                'uid: "00000001"\n'
                "type: note\n"
                f'title: "{long_title}"\n'
                "state: active\n"
                "status: active\n"
                "---\n\n"
                "# fixture\n",
                encoding="utf-8",
            )
            tool_source = tools / "tool.py"
            tool_source.write_text(
                '"""---\n'
                "uid: 00000002\n"
                "type: tool\n"
                f'title: "{long_title}"\n'
                "state: active\n"
                "status: active\n"
                "---\n"
                '"""\n',
                encoding="utf-8",
            )

            markdown_record = rebuild_index_module.process_file(source)
            tool_record = rebuild_index_module.process_tool_file(tool_source)
            self.assertIsNotNone(markdown_record)
            self.assertIsNotNone(tool_record)
            self.assertEqual(markdown_record["title"], long_title)
            self.assertEqual(tool_record["title"], long_title)

            entry_row, _edge_rows, fts_row = (
                rebuild_index_module._record_to_index_rows(
                    markdown_record,
                    files,
                )
            )
            self.assertEqual(entry_row[2], long_title)
            self.assertEqual(fts_row[1], long_title)

            _write(root / "vault" / "00-index.jsonl", [markdown_record])
            ranked_item = SimpleNamespace(
                uid="00000001",
                ranked_member=SimpleNamespace(score=1.0),
                circle_member=SimpleNamespace(relation="refs", distance=1),
            )
            result = SimpleNamespace(
                ok=True,
                value=SimpleNamespace(items=(ranked_item,)),
            )
            with (
                # Same isolation as the test above, from the same list — this
                # one patched two of the three surfaces and passed anyway,
                # because it asserts one UID's title rather than the whole set.
                # A latent hole in a green test is still a hole.
                contextlib.ExitStack() as stack,
                mock.patch.object(
                    orient_module.vp.ViewerProjection,
                    "from_repo_root",
                    return_value=object(),
                ),
                mock.patch.object(
                    orient_module,
                    "SqliteStructuralIndex",
                    return_value=object(),
                ),
                mock.patch.object(
                    orient_module,
                    "SqliteRankIndex",
                    return_value=object(),
                ),
                mock.patch.object(
                    orient_module.distiller,
                    "orient_deterministic",
                    return_value=result,
                ),
            ):
                for patch in _orient_isolated(root):
                    stack.enter_context(patch)
                answer = orient_module.orient("00000001", 1, "00000009")
            self.assertEqual(answer["task_title"], long_title)
            self.assertEqual(answer["items"][0]["title"], long_title)
            self.assertIn(long_title, orient_module.render_text(answer))

    def test_legacy_kernel_registration_preserves_source_title(self) -> None:
        long_title = "kernel-" + ("κ" * 130)
        self.assertEqual(
            Path(kernel_module.INDEX_PATH)
            .relative_to(Path(kernel_module.VAULT_ROOT))
            .as_posix(),
            "vault/00-index.jsonl",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tropo_dir = root / ".tropo"
            kernel_source = tropo_dir / "schema" / "kernel.md"
            kernel_source.parent.mkdir(parents=True)
            kernel_source.write_text(
                "---\n"
                "uid: 00000003\n"
                "type: os-primitive\n"
                f'title: "{long_title}"\n'
                "status: published\n"
                "---\n\n"
                "# fallback title\n",
                encoding="utf-8",
            )
            index_path = root / "vault" / "00-index.jsonl"
            index_path.parent.mkdir(parents=True)
            index_path.write_text("", encoding="utf-8")

            with (
                mock.patch.object(kernel_module, "VAULT_ROOT", str(root)),
                mock.patch.object(kernel_module, "TROPO_DIR", str(tropo_dir)),
                mock.patch.object(kernel_module, "INDEX_PATH", str(index_path)),
                mock.patch.object(kernel_module, "DRY_RUN", False),
            ):
                kernel_module.main()

            records = index_surfaces.read_jsonl_strict(
                index_path,
                verify_surface_metadata=False,
            )
            self.assertEqual(records[0]["title"], long_title)

    def test_exact_adr047_archive_predicate(self) -> None:
        self.assertTrue(index_surfaces.is_archive_record({"state": "archived", "status": "done"}))
        self.assertTrue(index_surfaces.is_archive_record({"state": "active", "status": "superseded"}))
        self.assertTrue(index_surfaces.is_archive_record({"state": "archived", "status": "superseded"}))

        # Retired is a lifecycle state, not an ADR-047 supersession.  This plant
        # prevents an attractive-but-wrong broader predicate from hiding identities.
        self.assertFalse(index_surfaces.is_archive_record({"state": "active", "status": "retired"}))
        self.assertFalse(index_surfaces.is_archive_record({"state": "active", "status": "done"}))

    def test_partition_is_lossless_and_disjoint(self) -> None:
        records = [
            {"uid": "00000001", "state": "active", "status": "active"},
            {"uid": "00000002", "state": "archived", "status": "done"},
            {"uid": "00000003", "state": "active", "status": "superseded"},
        ]
        current, archive = index_surfaces.partition_records(records)
        self.assertEqual({row["uid"] for row in current}, {"00000001"})
        self.assertEqual({row["uid"] for row in archive}, {"00000002", "00000003"})
        self.assertEqual(len(current) + len(archive), len(records))
        self.assertFalse({row["uid"] for row in current} & {row["uid"] for row in archive})

    def test_incremental_route_moves_uid_between_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vault_dir = tmp_path / "vault"
            vault_dir.mkdir()
            current_path = vault_dir / index_surfaces.CURRENT_INDEX_NAME
            archive_path = vault_dir / index_surfaces.ARCHIVE_INDEX_NAME
            _write(current_path, [{"uid": "deadbeef", "state": "active", "status": "active"}])
            _write(archive_path, [{"uid": "aaaaaaaa", "state": "archived", "status": "done"}])

            surface, action = index_surfaces.route_record(
                tmp_path, {"uid": "deadbeef", "state": "archived", "status": "done"}
            )
            self.assertEqual(surface, index_surfaces.ARCHIVE_INDEX_NAME)
            self.assertEqual(action, "inserted (new)")
            self.assertNotIn("deadbeef", _uids(current_path))
            self.assertEqual(_uids(archive_path), {"aaaaaaaa", "deadbeef"})

            surface, action = index_surfaces.route_record(
                tmp_path, {"uid": "deadbeef", "state": "active", "status": "active"}
            )
            self.assertEqual(surface, index_surfaces.CURRENT_INDEX_NAME)
            self.assertEqual(action, "inserted (new)")
            self.assertEqual(_uids(current_path), {"deadbeef"})
            self.assertEqual(_uids(archive_path), {"aaaaaaaa"})

    def test_union_is_opt_in_and_current_wins_impossible_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vault_dir = tmp_path / "vault"
            vault_dir.mkdir()
            current_path = vault_dir / index_surfaces.CURRENT_INDEX_NAME
            archive_path = vault_dir / index_surfaces.ARCHIVE_INDEX_NAME
            _write(current_path, [{"uid": "deadbeef", "surface": "current"}])
            _write(
                archive_path,
                [
                    {"uid": "deadbeef", "surface": "bad-overlap"},
                    {"uid": "aaaaaaaa", "surface": "archive"},
                ],
            )

            default = index_surfaces.load_index_records(tmp_path)
            union = index_surfaces.load_index_records(tmp_path, include_archive=True)
            self.assertEqual([row["uid"] for row in default], ["deadbeef"])
            self.assertEqual([row["uid"] for row in union], ["deadbeef", "aaaaaaaa"])
            self.assertEqual(union[0]["surface"], "current")

    def test_remove_uid_cleans_both_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vault_dir = tmp_path / "vault"
            vault_dir.mkdir()
            current_path = vault_dir / index_surfaces.CURRENT_INDEX_NAME
            archive_path = vault_dir / index_surfaces.ARCHIVE_INDEX_NAME
            _write(current_path, [{"uid": "deadbeef"}])
            _write(archive_path, [{"uid": "deadbeef"}, {"uid": "aaaaaaaa"}])

            removed = index_surfaces.remove_uid(tmp_path, "deadbeef")
            self.assertEqual(
                removed,
                [
                    index_surfaces.CURRENT_INDEX_NAME,
                    index_surfaces.ARCHIVE_INDEX_NAME,
                ],
            )
            self.assertFalse(_uids(current_path))
            self.assertEqual(_uids(archive_path), {"aaaaaaaa"})

    def test_full_rebuild_emits_two_surfaces_and_union_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = root / "vault" / "files"
            files.mkdir(parents=True)
            (root / ".tropo").mkdir()

            fixtures = {
                "00000001": ("active", "active"),
                "00000002": ("archived", "done"),
                "00000003": ("active", "superseded"),
            }
            for uid, (state, status) in fixtures.items():
                (files / f"{uid}.md").write_text(
                    "---\n"
                    f'uid: "{uid}"\n'
                    "type: note\n"
                    f'title: "fixture {uid}"\n'
                    f"state: {state}\n"
                    f"status: {status}\n"
                    "schema_version: 2\n"
                    "---\n\n"
                    f"# fixture {uid}\n",
                    encoding="utf-8",
                )

            self.assertEqual(rebuild_index_module.rebuild_index(root, True), 0)
            current_path = root / "vault" / index_surfaces.CURRENT_INDEX_NAME
            archive_path = root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME
            self.assertEqual(_uids(current_path), {"00000001"})
            self.assertEqual(_uids(archive_path), {"00000002", "00000003"})

            with sqlite3.connect(root / "vault" / "00-index.sqlite") as conn:
                sqlite_uids = {row[0] for row in conn.execute("SELECT uid FROM entries")}
            self.assertEqual(sqlite_uids, set(fixtures))

            # Plant the full-vs-incremental sibling-drift class: flip the
            # current source to archived, freshen just that UID, and require
            # the exact same routing predicate + union-preserving SQLite row.
            current_source = files / "00000001.md"
            current_source.write_text(
                current_source.read_text(encoding="utf-8").replace(
                    "state: active", "state: archived", 1
                ),
                encoding="utf-8",
            )
            self.assertEqual(rebuild_index_module.freshen_one("00000001", root), 0)
            self.assertNotIn("00000001", _uids(current_path))
            self.assertIn("00000001", _uids(archive_path))
            incremental_row = next(
                row
                for row in index_surfaces.iter_jsonl(archive_path)
                if row.get("uid") == "00000001"
            )
            with sqlite3.connect(root / "vault" / "00-index.sqlite") as conn:
                state = conn.execute(
                    "SELECT state FROM entries WHERE uid='00000001'"
                ).fetchone()[0]
            self.assertEqual(state, "archived")

            # Governed Autonomy S2 AC-10: the subsequent full pass must derive
            # the exact same touched row, including Gardener fields.
            self.assertEqual(rebuild_index_module.rebuild_index(root, True), 0)
            full_row = next(
                row
                for row in index_surfaces.iter_jsonl(archive_path)
                if row.get("uid") == "00000001"
            )
            self.assertEqual(incremental_row, full_row)


if __name__ == "__main__":
    unittest.main()
