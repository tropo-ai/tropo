#!/usr/bin/env python3
"""Acceptance tests for Mount Identity migration (7b1e0ae5 §3.4 / AC4)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
sys.path.insert(0, str(TOOLS))

SPEC = importlib.util.spec_from_file_location(
    "tropo_migrate_mount_identity",
    TOOLS / "tropo-migrate-mount-identity.py",
)
MIG = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MIG
SPEC.loader.exec_module(MIG)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _stub_studio(tmp: Path) -> Path:
    (tmp / ".tropo").mkdir()
    (tmp / "vault" / "files").mkdir(parents=True)
    (tmp / ".tropo-studio").mkdir()
    # Minimal index surfaces so freshen can fall through carefully in unit tests
    # that only exercise plan builders (no apply).
    (tmp / "vault" / "00-index.jsonl").write_text("", encoding="utf-8")
    _write(
        tmp / "vault" / "files" / f"{MIG.EXTERNAL_CONTEXT_L0_UID}.md",
        f"---\nuid: {MIG.EXTERNAL_CONTEXT_L0_UID}\ntype: project\nstatus: evergreen\n"
        f"state: active\ntitle: external-context\nmember_of: []\n---\n\n# external-context\n",
    )
    return tmp


class TestMountIdentityMigrationPlan(unittest.TestCase):
    def test_backfill_retarget_reparent_and_dispose(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _stub_studio(Path(tmp))
            mounts = {
                "mounts": {
                    "aaaaaaaa": {
                        "name": "share",
                        "path": "/tmp/share",
                        "state": "adopted",
                        "availability": "available",
                    },
                    "bbbbbbbb": {
                        "name": "notes",
                        "path": "/tmp/notes",
                        "state": "adopted",
                        "availability": "available",
                    },
                },
                "schema_version": 1,
            }
            (root / ".tropo-studio" / "folder-mounts.json").write_text(
                json.dumps(mounts), encoding="utf-8"
            )

            # Missing identity for aaaaaaaa (unresolvable refs).
            _write(
                root / "vault" / "files" / "11111111.md",
                "---\nuid: '11111111'\ntype: project\nstatus: active\nstate: active\n"
                "title: sub\nmount_uid: 'aaaaaaaa'\nmember_of:\n  - '2d083137'\n---\n\n# sub\n",
            )

            # Wrong-shape identity for bbbbbbbb (document under handmade L0).
            _write(
                root / "vault" / "files" / "bbbbbbbb.md",
                "---\nuid: bbbbbbbb\ntype: document\ndocument_type: folder-mount\n"
                "status: active\nstate: active\ntitle: notes mount\n"
                "member_of:\n  - ae4168fc\nmount_kind: folder\n---\n\n# notes\n",
            )
            _write(
                root / "vault" / "files" / "22222222.md",
                "---\nuid: '22222222'\ntype: external-artifact\nstatus: active\nstate: active\n"
                "title: leaf\nmount_uid: 'bbbbbbbb'\nmember_of:\n  - 'ae4168fc'\n---\n\n# leaf\n",
            )

            # Stray: empty member_of, Tropo Work via subsystem_hub.
            _write(
                root / "vault" / "files" / "33333333.md",
                "---\nuid: '33333333'\ntype: project\nstatus: active\nstate: active\n"
                "title: projects\nmount_uid: 'bbbbbbbb'\nsubsystem_hub:\n  - '2d083137'\n---\n\n# projects\n",
            )

            # Handmade stand-in L0.
            _write(
                root / "vault" / "files" / "ae4168fc.md",
                "---\nuid: ae4168fc\ntype: project\nstatus: active\nstate: active\n"
                "title: maz-notes\nmount_uid: 'bbbbbbbb'\nmount_relpath: ''\n"
                "subsystem_hub:\n  - 2d083137\n---\n\n# maz-notes\n",
            )

            before = MIG.measure_metrics(root)
            self.assertGreater(before.unresolvable_mount_refs, 0)
            self.assertGreater(before.improper_mount_identity_refs, 0)

            plan = MIG.build_plan(root)
            actions = {c.uid: c.action for c in plan.changes}
            self.assertEqual(actions["aaaaaaaa"], "identity-create")
            self.assertEqual(actions["bbbbbbbb"], "identity-retarget")
            self.assertEqual(actions["11111111"], "reparent")
            self.assertEqual(actions["22222222"], "reparent")
            self.assertEqual(actions["33333333"], "reparent")
            self.assertEqual(actions["ae4168fc"], "dispose-standin")

            # Apply staged bytes without index freshen (unit-level semantic check).
            for path, raw in plan.staged.items():
                path.write_bytes(raw)

            after = MIG.measure_metrics(root)
            self.assertEqual(after.unresolvable_mount_refs, 0)
            self.assertEqual(after.improper_mount_identity_refs, 0)

            b_fm, _, _ = MIG._parse_frontmatter(
                (root / "vault" / "files" / "bbbbbbbb.md").read_text(encoding="utf-8")
            )
            self.assertEqual(b_fm["type"], "project")
            self.assertEqual(b_fm["member_of"], [MIG.EXTERNAL_CONTEXT_L0_UID])
            self.assertNotIn("document_type", b_fm)

            leaf_fm, _, _ = MIG._parse_frontmatter(
                (root / "vault" / "files" / "22222222.md").read_text(encoding="utf-8")
            )
            self.assertEqual(leaf_fm["member_of"], ["bbbbbbbb"])

            standin_fm, _, body = MIG._parse_frontmatter(
                (root / "vault" / "files" / "ae4168fc.md").read_text(encoding="utf-8")
            )
            self.assertEqual(standin_fm["state"], "archived")
            self.assertEqual(standin_fm["disposition"], "superseded-by-mount-identity")
            self.assertEqual(standin_fm["member_of"], ["bbbbbbbb"])
            self.assertIn("Disposition (7b1e0ae5 §3.4)", body)

            # Idempotent plan on the repaired tree.
            second = MIG.build_plan(root)
            self.assertEqual(second.changes, [])


class ProductionApplyWeldTests(unittest.TestCase):
    """AC4 through the real CLI — the weld, not the planner (7b1e0ae5 §3.4).

    The planner test above writes ``plan.staged`` bytes directly, which proves
    the semantics and nothing about the wiring: ``apply_plan``,
    ``_freshen_projection_index`` and the CLI could all disappear while it stayed
    green. This case drives ``--apply`` as a subprocess against a TempStudio
    built by the production index writer, and pins the locked UID-keyed
    unchanged assertion to a real non-mount sentinel.
    """

    MOUNT_MISSING = "aaaaaaaa"   # no governed identity at all
    MOUNT_WRONG = "bbbbbbbb"     # exists, wrong type, wrong parent
    SENTINEL = "5ce77777"        # unrelated, non-mount, must not move

    def build_studio(self, tmp: Path) -> Path:
        root = tmp / "studio"
        (root / "vault" / "files").mkdir(parents=True)
        (root / ".tropo-studio").mkdir(parents=True)
        (root / ".tropo").mkdir(parents=True)
        (root / "STUDIO.md").write_text("# TempStudio\n", encoding="utf-8")
        (root / ".tropo" / "boot-config.md").write_text("# boot\n", encoding="utf-8")

        files = root / "vault" / "files"
        _write(
            files / f"{MIG.EXTERNAL_CONTEXT_L0_UID}.md",
            f"---\nuid: {MIG.EXTERNAL_CONTEXT_L0_UID}\ntype: project\n"
            f"status: evergreen\nstate: active\ntitle: external-context\n"
            f"member_of: []\nlifecycle: standing\nextraction_scope: ship\n"
            f"---\n\n# external-context\n",
        )
        # The sentinel: an ordinary governed note with no mount involvement.
        _write(
            files / f"{self.SENTINEL}.md",
            f"---\nuid: '{self.SENTINEL}'\ntype: note\nstatus: active\nstate: active\n"
            f"title: unrelated sentinel\nmember_of:\n  - '2d083137'\n"
            f"created: '2026-08-12'\ncreated_by: talos-t41\n---\n\n"
            f"# unrelated sentinel\n\nA non-mount row. The migration must not touch it.\n",
        )
        # Tropo Work, so the sentinel's parent resolves.
        _write(
            files / "2d083137.md",
            "---\nuid: '2d083137'\ntype: project\nstatus: evergreen\nstate: active\n"
            "title: Tropo Work\nmember_of: []\nlifecycle: standing\n---\n\n# Tropo Work\n",
        )
        # Mount with no identity + a mirror wrongly under Tropo Work.
        _write(
            files / "11111111.md",
            "---\nuid: '11111111'\ntype: project\nstatus: active\nstate: active\n"
            "title: share-sub\nmount_uid: 'aaaaaaaa'\nmount_relpath: 'sub'\n"
            "member_of:\n  - '2d083137'\n---\n\n# share-sub\n",
        )
        # Mount whose identity exists in the wrong shape.
        _write(
            files / f"{self.MOUNT_WRONG}.md",
            "---\nuid: bbbbbbbb\ntype: document\ndocument_type: folder-mount\n"
            "status: active\nstate: active\ntitle: notes mount\n"
            "member_of:\n  - '2d083137'\nmount_kind: folder\n---\n\n# notes mount\n",
        )
        _write(
            files / "22222222.md",
            "---\nuid: '22222222'\ntype: external-artifact\nstatus: active\nstate: active\n"
            "title: leaf.md\nmount_uid: 'bbbbbbbb'\nmount_relpath: 'leaf.md'\n"
            "member_of:\n  - 'bbbbbbbb'\n---\n\n# leaf\n",
        )
        (root / ".tropo-studio" / "folder-mounts.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mounts": {
                        self.MOUNT_MISSING: {
                            "name": "share",
                            "path": str(tmp / "external" / "share"),
                            "state": "adopted",
                            "availability": "available",
                        },
                        self.MOUNT_WRONG: {
                            "name": "notes",
                            "path": str(tmp / "external" / "notes"),
                            "state": "adopted",
                            "availability": "available",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        return root

    def index_rows(self, root: Path) -> dict:
        rows = {}
        index = root / "vault" / "00-index.jsonl"
        if not index.is_file():
            return rows
        for line in index.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rows[row["uid"]] = row
        return rows

    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOLS / "tropo-migrate-mount-identity.py"),
             "--studio", str(root), *args],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )

    def test_cli_apply_repairs_indexes_and_leaves_non_mount_rows_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.build_studio(Path(tmp))

            rebuild = subprocess.run(
                [sys.executable, str(TOOLS / "tropo-rebuild-index.py"),
                 "--apply", "--vault-path", str(root)],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            self.assertEqual(rebuild.returncode, 0, rebuild.stdout + rebuild.stderr)

            sentinel_path = root / "vault" / "files" / f"{self.SENTINEL}.md"
            sentinel_bytes_before = sentinel_path.read_bytes()
            rows_before = self.index_rows(root)
            self.assertIn(
                self.SENTINEL, rows_before, "fixture must index the sentinel first"
            )
            non_mount_before = {
                uid: row for uid, row in rows_before.items()
                if not row.get("mount_uid")
                and uid not in {self.MOUNT_MISSING, self.MOUNT_WRONG}
            }
            self.assertTrue(
                non_mount_before,
                "fixture planted no non-mount rows, so the unchanged assertion "
                "would pass vacuously",
            )

            applied = self.run_cli(root, "--apply")

            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            self.assertIn("Result: CLEAN", applied.stdout)
            self.assertIn("unresolvable=0 improper_identity=0", applied.stdout)
            self.assertIn("Second-plan changes: 0", applied.stdout)

            # The weld: the created identity must be on the INDEX, not merely on
            # disk. Direct byte-writes would leave this assertion red.
            rows_after = self.index_rows(root)
            self.assertIn(
                self.MOUNT_MISSING,
                rows_after,
                "the created mount identity never reached the index — "
                "apply_plan/_freshen_projection_index is not welded to the CLI",
            )
            self.assertEqual(rows_after[self.MOUNT_MISSING].get("type"), "project")
            self.assertEqual(
                rows_after[self.MOUNT_WRONG].get("member_of"),
                [MIG.EXTERNAL_CONTEXT_L0_UID],
            )

            # The locked unchanged assertion, UID-keyed and byte-level on a real
            # non-mount row.
            self.assertEqual(
                sentinel_path.read_bytes(),
                sentinel_bytes_before,
                "the migration rewrote an unrelated non-mount file",
            )
            non_mount_after = {
                uid: rows_after[uid] for uid in non_mount_before if uid in rows_after
            }
            self.assertEqual(
                set(non_mount_after),
                set(non_mount_before),
                "a non-mount row disappeared from the index",
            )
            for uid, before_row in non_mount_before.items():
                # Gardener's `swept` field is a derived repository-clock stamp,
                # not authored row content. A fixture built before midnight and
                # migrated after midnight legitimately advances only that date;
                # comparing it byte-for-byte made the mount-only invariant fail
                # on elapsed time. The canonical source bytes above remain the
                # hard no-rewrite assertion. Compare index semantics here while
                # dropping only the volatile sweep clock.
                def stable_row(row):
                    if isinstance(row, dict):
                        return {
                            key: stable_row(value)
                            for key, value in row.items()
                            if key != "swept"
                        }
                    if isinstance(row, list):
                        return [stable_row(value) for value in row]
                    return row

                self.assertEqual(
                    stable_row(non_mount_after[uid]),
                    stable_row(before_row),
                    f"non-mount row {uid} changed during a mount-only migration",
                )

    def test_second_cli_apply_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.build_studio(Path(tmp))
            rebuild = subprocess.run(
                [sys.executable, str(TOOLS / "tropo-rebuild-index.py"),
                 "--apply", "--vault-path", str(root)],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            self.assertEqual(rebuild.returncode, 0, rebuild.stdout + rebuild.stderr)

            first = self.run_cli(root, "--apply")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            snapshot = {
                path.name: path.read_bytes()
                for path in sorted((root / "vault" / "files").glob("*.md"))
            }

            second = self.run_cli(root, "--apply")

            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("Planned changes: 0", second.stdout)
            self.assertIn("Result: CLEAN", second.stdout)
            after = {
                path.name: path.read_bytes()
                for path in sorted((root / "vault" / "files").glob("*.md"))
            }
            self.assertEqual(
                after, snapshot, "the second apply rewrote already-migrated files"
            )

    def test_dry_run_cli_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.build_studio(Path(tmp))
            rebuild = subprocess.run(
                [sys.executable, str(TOOLS / "tropo-rebuild-index.py"),
                 "--apply", "--vault-path", str(root)],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            self.assertEqual(rebuild.returncode, 0, rebuild.stdout + rebuild.stderr)
            before = {
                path.name: path.read_bytes()
                for path in sorted((root / "vault" / "files").glob("*.md"))
            }

            preview = self.run_cli(root)

            self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
            self.assertIn("DRY-RUN", preview.stdout)
            self.assertIn("Projected after: unresolvable=0", preview.stdout)
            after = {
                path.name: path.read_bytes()
                for path in sorted((root / "vault" / "files").glob("*.md"))
            }
            self.assertEqual(after, before, "the dry run wrote to the vault")
            self.assertNotIn(
                self.MOUNT_MISSING,
                self.index_rows(root),
                "the dry run indexed a mount identity it only previewed",
            )


if __name__ == "__main__":
    unittest.main()
