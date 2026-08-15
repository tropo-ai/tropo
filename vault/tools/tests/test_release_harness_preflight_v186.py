#!/usr/bin/env python3
"""v1.86 preflight for measured cold-walk packaging and import-closure risks."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load("v186_preflight_build", ROOT / "vault/tools/tropo-build-release.py")
event_identity = _load(
    "v186_preflight_event_identity", ROOT / "vault/tools/lib/event_identity.py"
)
harness = _load("v186_preflight_harness", ROOT / ".tropo/scripts/test-harness-check.py")
l0_validator = _load(
    "v186_preflight_l0",
    ROOT / "vault/tools/tropo-validate-canonical-l0.py",
)


class ReleaseHarnessPreflightV186(unittest.TestCase):
    def _ship_artifact(self, uid: str) -> dict:
        for line in (ROOT / "vault/00-index.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("uid") == uid:
                return row
        self.fail(f"ship artifact {uid} not found")

    @staticmethod
    def _copy(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def _source_shaped_release(self, release_root: Path) -> None:
        root_docs = ROOT / "vault/templates/root-docs"
        for name in ("AGENTS.md", "README.md", "START-TROPO.md", "CLAUDE.md"):
            self._copy(root_docs / name, release_root / name)

        capsule_artifact = self._ship_artifact("7f746921")
        with patch.object(build, "DRY_RUN", False):
            emitted = build.build_from_manifest(str(release_root), [capsule_artifact])
        self.assertEqual(emitted, 1)
        self.assertEqual(
            (release_root / "CAPSULE.md").read_bytes(),
            (root_docs / "CAPSULE.md").read_bytes(),
        )

        for relative in (
            ".tropo/version.md",
            ".tropo/orientation.md",
            ".tropo/concierge/activate.md",
            ".tropo/playbooks/test-harness.playbook.md",
            "vault/00-index.jsonl",
            "vault/tools/tropo-generate-relations-header.py",
            "vault/tools/tropo-rebuild-index.py",
            "vault/tools/tropo-validate.py",
        ):
            self._copy(ROOT / relative, release_root / relative)
        shutil.copytree(
            ROOT / "vault/tools/lib",
            release_root / "vault/tools/lib",
        )
        shutil.copytree(
            ROOT / ".tropo/scripts/lib",
            release_root / ".tropo/scripts/lib",
        )
        self._copy(
            ROOT / "vault/capsules/tropo-release.capsule.md",
            release_root / "vault/files/b19e8d43.md",
        )

        with patch.object(build, "DRY_RUN", False):
            build.step_9_generate_manifest(str(release_root), "1.86.0")

    @staticmethod
    def _by_name(results: list[dict]) -> dict[str, bool]:
        return {result["check"]: result["ok"] for result in results}

    def test_source_shaped_surface_passes_and_mutations_go_red(self):
        with tempfile.TemporaryDirectory(prefix="v186-release-preflight-") as temporary:
            release_root = Path(temporary)
            self._source_shaped_release(release_root)

            results, _ = harness.run_checks(release_root)
            self.assertTrue(all(result["ok"] for result in results), results)

            (release_root / "CAPSULE.md").unlink()
            checks = self._by_name(harness.run_checks(release_root)[0])
            self.assertFalse(checks["required files/dirs present"])
            self._copy(
                ROOT / "vault/templates/root-docs/CAPSULE.md",
                release_root / "CAPSULE.md",
            )

            (release_root / "MANIFEST.md").unlink()
            checks = self._by_name(harness.run_checks(release_root)[0])
            self.assertFalse(checks["MANIFEST present"])
            with patch.object(build, "DRY_RUN", False):
                build.step_9_generate_manifest(str(release_root), "1.86.0")

            missing_lib = release_root / "vault/tools/lib/decay_gate.py"
            missing_lib.unlink()
            results, _ = harness.run_checks(release_root)
            import_closure = next(
                result for result in results
                if result["check"] == "shipped Python lib import closure"
            )
            self.assertFalse(import_closure["ok"])
            self.assertIn("lib.decay_gate", import_closure["detail"])
            self._copy(ROOT / "vault/tools/lib/decay_gate.py", missing_lib)

            leak = release_root / "vault/files/private-canary.md"
            leak.write_text(
                "---\nuid: deadbeef\ntype: note\nextraction_scope: argo-private\n---\n",
                encoding="utf-8",
            )
            checks = self._by_name(harness.run_checks(release_root)[0])
            self.assertFalse(checks["no private/reference-only content leaked"])

    def test_real_ship_filter_contains_no_private_scope(self):
        entries = build.load_ship_entries(str(ROOT / "vault/00-index.jsonl"))
        self.assertGreater(len(entries), 0)
        self.assertTrue(
            all(entry.get("extraction_scope") == "ship" for entry in entries),
            "release extraction must remain a positive ship-scope filter",
        )

    def test_build_validation_receipt_is_post_rebuild_and_parse_bound(self):
        passing = SimpleNamespace(
            returncode=0,
            stdout=(
                "Result: 85 passed, 280 failed "
                "(recorded studio debt: 283, from 2026-08-09)\nPASS\n"
            ),
            stderr="",
        )
        with (
            patch.object(build.subprocess, "run", return_value=passing),
            patch.object(
                build, "_validator_tree_snapshot",
                return_value=("a" * 64, 123),
            ),
            patch.object(
                build, "_write_validation_receipt",
                return_value=Path("/tmp/receipt.json"),
            ),
        ):
            receipt = build._run_post_rebuild_validation("b" * 32)
        self.assertTrue(receipt["clear"])
        self.assertEqual(receipt["phase"], "post-rebuild")
        self.assertEqual(receipt["tree_sha256"], "a" * 64)
        self.assertEqual(receipt["summary"], {"passed": 85, "failed": 280})

    def test_release_l0_gate_excludes_explicit_non_ship_cockpit_projects(self):
        with tempfile.TemporaryDirectory(prefix="v186-l0-scope-") as temporary:
            root = Path(temporary)
            vault = root / "vault"
            vault.mkdir()
            (vault / "00-index.jsonl").write_text(
                "\n".join((
                    json.dumps({"uid": "shiproot", "extraction_scope": "ship"}),
                    json.dumps({"uid": "802b9c5c", "extraction_scope": "argo-reference"}),
                )) + "\n",
                encoding="utf-8",
            )
            (vault / "00-project-tree.jsonl").write_text(
                "\n".join((
                    json.dumps({"uid": "shiproot", "title": "Ship Root",
                                "state": "active", "parent": None}),
                    json.dumps({"uid": "802b9c5c", "title": "Competitive Briefs",
                                "state": "active", "parent": None}),
                    json.dumps({"uid": "unknown", "title": "Unknown Scope",
                                "state": "active", "parent": None}),
                )) + "\n",
                encoding="utf-8",
            )

            all_roots = l0_validator.load_rendered_l0_set(root)
            ship_roots = l0_validator.load_rendered_l0_set(
                root, extraction_scope_filter="ship"
            )

        self.assertEqual(
            {row["uid"] for row in all_roots},
            {"shiproot", "802b9c5c", "unknown"},
        )
        self.assertEqual(
            {row["uid"] for row in ship_roots},
            {"shiproot", "unknown"},
            "explicit non-ship roots are excluded; unknown scope remains fail-safe visible",
        )
        self.assertIn(
            "'--extraction-scope', 'ship'",
            (ROOT / "vault/tools/tropo-build-release.py").read_text(encoding="utf-8"),
        )

    def test_release_version_file_is_canonical_bare_line(self):
        with tempfile.TemporaryDirectory(prefix="v186-version-") as temporary:
            release_root = Path(temporary)
            (release_root / ".tropo").mkdir()
            with patch.object(build, "DRY_RUN", False):
                build.step_8_write_version(str(release_root), "1.86.0")
            self.assertEqual(
                (release_root / ".tropo/version.md").read_bytes(),
                b"v1.86.0\n",
            )

    def test_vendor_ref_walk_includes_python_and_numeric_uids(self):
        with tempfile.TemporaryDirectory(prefix="v186-vendor-refs-") as temporary:
            root = Path(temporary)
            (root / "vault/tools").mkdir(parents=True)
            (root / "vault/files").mkdir(parents=True)
            (root / "vault/tools/numeric-tool.py").write_text(
                '#!/usr/bin/env python3\n"""\n---\nuid: 99341618\n'
                'type: tool\nrefs: [deadbeef]\n---\n"""\n',
                encoding="utf-8",
            )
            (root / "vault/files/deadbeef.md").write_text(
                "---\nuid: deadbeef\ntype: note\nrefs: [99341618]\n---\n",
                encoding="utf-8",
            )

            all_uids = build._vendor_manifest_collect_all_uids(root)
            referenced = build._vendor_manifest_collect_referenced_uids(root)

        self.assertEqual(all_uids, {"99341618", "deadbeef"})
        self.assertEqual(referenced, {"99341618", "deadbeef"})

    def test_per_studio_boot_derivations_are_removed_after_copy(self):
        with tempfile.TemporaryDirectory(prefix="v186-boot-derivations-") as temporary:
            root = Path(temporary)
            (root / ".tropo").mkdir()
            (root / "vault").mkdir()
            for relative in build.PER_STUDIO_BOOT_DERIVATIONS:
                target = root / relative
                target.write_text("source-studio fingerprint\n", encoding="utf-8")
            (root / "vault/00-index.jsonl").write_text(
                "\n".join((
                    json.dumps({
                        "uid": "266b0b56",
                        "path": ".tropo/boot-digest.md",
                    }),
                    json.dumps({
                        "uid": "a993f079",
                        "path": ".tropo/boot-fast-path.md",
                    }),
                    json.dumps({
                        "uid": "deadbeef",
                        "path": "vault/files/deadbeef.md",
                    }),
                )) + "\n",
                encoding="utf-8",
            )

            with patch.object(build, "DRY_RUN", False):
                removed = build.step_3f_remove_per_studio_boot_derivations(
                    str(root)
                )

            self.assertEqual(removed, 2)
            self.assertTrue(
                all(not (root / relative).exists()
                    for relative in build.PER_STUDIO_BOOT_DERIVATIONS)
            )
            remaining_rows = [
                json.loads(line)
                for line in (root / "vault/00-index.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]
            self.assertEqual(
                [row["uid"] for row in remaining_rows],
                ["deadbeef"],
                "the package index must not retain rows for excluded derivations",
            )

    def test_legitimately_empty_archive_surface_is_strictly_readable(self):
        with tempfile.TemporaryDirectory(prefix="v186-index-pair-") as temporary:
            root = Path(temporary)
            (root / ".tropo").mkdir()
            shutil.copytree(
                ROOT / "vault/tools/lib",
                root / "vault/tools/lib",
            )
            self._copy(
                ROOT / "vault/tools/tropo-rebuild-index.py",
                root / "vault/tools/tropo-rebuild-index.py",
            )
            self._copy(
                ROOT / "vault/tools/tropo-generate-relations-header.py",
                root / "vault/tools/tropo-generate-relations-header.py",
            )
            source = root / "vault/files/deadbeef.md"
            source.parent.mkdir(parents=True)
            source.write_text(
                "---\nuid: deadbeef\ntype: note\nstate: active\n---\n",
                encoding="utf-8",
            )
            (root / "vault/00-index.jsonl").write_text(
                json.dumps({
                    "uid": "deadbeef",
                    "type": "note",
                    "state": "active",
                    "path": "vault/files/deadbeef.md",
                }) + "\n",
                encoding="utf-8",
            )

            with patch.object(build, "DRY_RUN", False):
                build.step_10_1_seal_release_index_pair(str(root), "ff6f762e")

            archive = root / "vault/00-archive-index.jsonl"
            index_surfaces = build._load_release_index_surfaces(str(root))
            self.assertEqual(archive.read_bytes(), b"")
            self.assertEqual(index_surfaces.read_jsonl_strict(archive), [])
            self.assertEqual(
                len(index_surfaces.read_jsonl_strict(root / "vault/00-index.jsonl")),
                1,
            )
            self.assertTrue(
                (root / ".tropo-studio/locks/index-surfaces.meta.json").is_file()
            )
            sqlite_path = root / "vault/00-index.sqlite"
            self.assertTrue(sqlite_path.is_file())
            with sqlite3.connect(sqlite_path) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM index_ratchet_metadata"
                    ).fetchone()[0],
                    1,
                )

    def test_index_seal_refusal_is_reported_without_traceback(self):
        class PlantedRefusal(RuntimeError):
            pass

        with tempfile.TemporaryDirectory(prefix="v186-index-refusal-") as temporary:
            root = Path(temporary)
            source = root / "vault/files/deadbeef.md"
            source.parent.mkdir(parents=True)
            source.write_text("---\nuid: deadbeef\ntype: note\n---\n", encoding="utf-8")
            (root / "vault/00-index.jsonl").write_text(
                json.dumps({
                    "uid": "deadbeef",
                    "type": "note",
                    "path": "vault/files/deadbeef.md",
                }) + "\n",
                encoding="utf-8",
            )
            fake_surfaces = SimpleNamespace(
                CURRENT_INDEX_NAME="00-index.jsonl",
                ARCHIVE_INDEX_NAME="00-archive-index.jsonl",
                IndexSurfaceRefusal=PlantedRefusal,
                GovernedFloorRecovery=lambda **kwargs: kwargs,
                prove_full_source_derivation=lambda *args, **kwargs: object(),
                write_jsonl_pair_atomic=lambda *args, **kwargs: (
                    _ for _ in ()
                ).throw(PlantedRefusal("planted floor refusal")),
                read_jsonl_strict=lambda path: [],
            )
            output = io.StringIO()
            with (
                patch.object(build, "DRY_RUN", False),
                patch.object(
                    build, "_load_release_index_surfaces",
                    return_value=fake_surfaces,
                ),
                patch.object(
                    build, "_build_release_genesis_sqlite_image",
                    return_value=b"planted sqlite image",
                ),
                redirect_stdout(output),
                self.assertRaises(SystemExit) as refusal,
            ):
                build.step_10_1_seal_release_index_pair(
                    str(root), "ff6f762e"
                )

        self.assertEqual(refusal.exception.code, 1)
        self.assertIn("Build REFUSED", output.getvalue())
        self.assertIn("planted floor refusal", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())


class V2CutoverMarkerIsNotShipped(unittest.TestCase):
    """The box must not carry Argo's v2 event-cutover marker.

    Punch-list item 6 (51dc85ef), talos-t40 2026-08-08. Shipping it does not
    merely leak Argo's baseline commit and its 6,678-row ledger counts — it
    BLOCKS the customer studio from emitting v2 events at all, because the
    marker's presence is an authenticated local contract whose evidence UIDs are
    hardcoded to Argo entries that do not ship.

    Absence is the designed state, so the cure is to ship nothing.
    """

    MARKER_REL = ".tropo/event-streams-v2.enabled"

    def test_the_marker_is_excluded_from_the_kernel_copy(self):
        self.assertTrue(
            build.should_exclude_kernel(str(ROOT / self.MARKER_REL)),
            "the v2 cutover marker must never reach a customer box",
        )

    def test_the_exclusion_does_not_over_match_the_rest_of_the_kernel(self):
        """Control. Without it, a pattern of '' would pass the test above."""
        for still_ships in (".tropo/boot-config.md", ".tropo/TROPO-CONTROL.md"):
            with self.subTest(path=still_ships):
                self.assertFalse(build.should_exclude_kernel(str(ROOT / still_ships)))

    def test_removing_the_pattern_puts_the_marker_back_in_the_box(self):
        """The teeth: prove the pattern is what does the work."""
        without = [
            p
            for p in build.KERNEL_EXCLUDE_PATTERNS
            if "event-streams-v2.enabled" not in p
        ]
        self.assertEqual(len(without), len(build.KERNEL_EXCLUDE_PATTERNS) - 1)
        from lib.ship_extract import should_exclude_kernel as engine

        self.assertFalse(engine(str(ROOT / self.MARKER_REL), without))

    def test_a_marker_less_box_can_still_emit(self):
        """Why shipping nothing is the fix and not a gap.

        Absence returns None, which the loader documents as legacy mode and the
        validator reports as 'pre-cutover studio'. Emission is unblocked.
        """
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "box"
            (box / ".tropo").mkdir(parents=True)
            (box / "vault" / "events").mkdir(parents=True)
            self.assertIsNone(event_identity.load_cutover_marker(box))

    def test_a_disabled_marker_would_block_emission_so_it_is_not_an_option(self):
        """Rules out the alternative shape, in code rather than in a comment.

        'Ship it disabled' reads like the conservative choice and is the one
        thing that cannot work: the loader requires `enabled` to be exactly
        True and raises otherwise, which is the same blocked box by a different
        route.
        """
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "box"
            (box / ".tropo").mkdir(parents=True)
            (box / "vault" / "events").mkdir(parents=True)
            marker = json.loads(
                (ROOT / ".tropo/event-streams-v2.enabled").read_text(encoding="utf-8")
            )
            marker["enabled"] = False
            (box / self.MARKER_REL).write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaises(Exception) as caught:
                event_identity.load_cutover_marker(box)
            self.assertIn("enabled", str(caught.exception))

    def test_a_populated_stream_in_the_box_would_defeat_the_absence(self):
        """The condition this fix depends on, asserted rather than assumed.

        Absence only means legacy mode while the box carries no event history.
        A populated stream with no marker refuses — cutover is forward-only. No
        ship path puts one in the box today (there are zero ship-scoped index
        rows under vault/events/), and this test is here so that if one ever
        appears, it fails next to the reason instead of in a customer's studio.
        """
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "box"
            (box / ".tropo").mkdir(parents=True)
            streams = box / "vault" / "events" / "streams"
            streams.mkdir(parents=True)
            (streams / "a.jsonl").write_text('{"id":"x"}\n', encoding="utf-8")
            with self.assertRaises(Exception):
                event_identity.load_cutover_marker(box)

            # An EMPTY stream file is harmless — the guard reads content, not
            # the presence of the directory a skeleton might create.
            (streams / "a.jsonl").write_text("", encoding="utf-8")
            self.assertIsNone(event_identity.load_cutover_marker(box))


if __name__ == "__main__":
    unittest.main(verbosity=2)
