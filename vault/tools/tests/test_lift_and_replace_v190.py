#!/usr/bin/env python3
"""ea09fc6e lift-and-replace update engine — AC proofs (plan phase first).

Red baseline discipline per A153's explicit instruction: the PLAN classes
land red before tropo-apply-image.py exists; the apply/bootstrap/AC6 classes
join this file as their phases build (absent classes keep their verify
commands honestly red rather than vacuously green).
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load_applier():
    spec = importlib.util.spec_from_file_location(
        "tropo_apply_image", TOOLS / "tropo-apply-image.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["tropo_apply_image"] = module
    spec.loader.exec_module(module)
    return module


def _write_image(root: Path, files: dict) -> Path:
    """A scratch image tree plus its emitted manifest (builder's format)."""
    image = root / "image"
    for rel, content in files.items():
        target = image / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return image


def _prior_manifest(root: Path, files: dict, version: str = "1.89.0") -> Path:
    """A prior image manifest in the tropo.image-manifest/v1 shape."""
    import hashlib
    manifest = {
        "schema": "tropo.image-manifest/v1",
        "version": version,
        "file_count": len(files),
        "files": {
            rel: {"sha256": hashlib.sha256(content.encode()).hexdigest(),
                  "bytes": len(content.encode())}
            for rel, content in files.items()
        },
    }
    path = root / "tropo-image-manifest.json"
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True),
                    encoding="utf-8")
    return path


def _tree_state(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


class PlanPurityTests(unittest.TestCase):
    """AC1 — plan computes a countable operation list and writes nothing."""

    def test_plan_mutates_zero_bytes(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_plan_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            (studio / "old.txt").write_text("old", encoding="utf-8")
            image = _write_image(root, {"vault/tool.py": "new"})
            prior = _prior_manifest(root, {"old.txt": "old"})
            before = _tree_state(root)
            plan = applier.plan(image_dir=image, studio_dir=studio,
                                prior_manifest=prior)
            self.assertEqual(_tree_state(root), before,
                             "plan mutated the tree — plan is compute-only")
            self.assertIsNotNone(plan)


class SetDerivationTests(unittest.TestCase):
    """AC2 — the three sets derive from declared inputs, never a scan."""

    def test_replace_is_every_file_in_the_new_image(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_set_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            image = _write_image(root, {"a.py": "1", "b/c.py": "2"})
            prior = _prior_manifest(root, {"gone.py": "x"})
            plan = applier.plan(image_dir=image, studio_dir=studio,
                                prior_manifest=prior)
            self.assertEqual(
                sorted(plan["replace"]), ["a.py", "b/c.py"],
                "replace must be every file in the new image")

    def test_delete_comes_only_from_the_prior_manifest(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_del_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            # A user file on disk that is in NO manifest: structurally
            # unreachable by the delete-set — this is the spec's core
            # safety property. And an OS file the prior manifest names but
            # the new image drops: that one IS deletable.
            (studio / "user-notes.md").write_text("user", encoding="utf-8")
            (studio / "retired-tool.py").write_text("old", encoding="utf-8")
            image = _write_image(root, {"kept.py": "1"})
            prior = _prior_manifest(
                root, {"kept.py": "1", "retired-tool.py": "old"})
            plan = applier.plan(image_dir=image, studio_dir=studio,
                                prior_manifest=prior)
            self.assertEqual(plan["delete"], ["retired-tool.py"])
            self.assertNotIn(
                "user-notes.md", plan["delete"],
                "the delete-set scanned the studio — user content is "
                "structurally unreachable, not defended")

    def test_skip_is_the_enumerated_never_touch_list(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_skip_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            (studio / ".claude").mkdir()
            (studio / ".claude" / "settings.json").write_text(
                "{}", encoding="utf-8")
            image = _write_image(
                root, {".claude/settings.json": "machine version"})
            prior = _prior_manifest(root, {".claude/settings.json": "user"})
            plan = applier.plan(image_dir=image, studio_dir=studio,
                                prior_manifest=prior)
            self.assertIn(".claude/settings.json", plan["skip"])
            self.assertNotIn(".claude/settings.json", plan["replace"])


class DeterministicProgressTests(unittest.TestCase):
    """AC3 — the total is known before the first write and cannot move."""

    def test_count_is_fixed_and_complete_before_any_write(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_cnt_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            image = _write_image(
                root, {"a.py": "1", "b.py": "2", "c.py": "3"})
            prior = _prior_manifest(
                root, {"a.py": "1", "dropped.py": "x"})
            plan = applier.plan(image_dir=image, studio_dir=studio,
                                prior_manifest=prior)
            self.assertEqual(plan["total"], 4,
                             "3 replaces + 1 delete — known before the "
                             "first write, and the bar renders over this")
            self.assertEqual(
                plan["total"],
                len(plan["replace"]) + len(plan["delete"]),
                "the total is derived, not declared — a bar that can move "
                "is proof the reasoning did not happen first")



class BackupBeforeWriteTests(unittest.TestCase):
    """AC4 — backup replace ∪ delete precedes the first write; receipt
    carries the pointer; the test proves the RECOVERY path, not counts."""

    def test_backup_exists_before_first_write_and_recovers_originals(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_bak_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            (studio / "old.py").write_text("OLD CONTENT", encoding="utf-8")
            image = _write_image(root, {"new.py": "NEW"})
            prior = _prior_manifest(root, {"old.py": "OLD"})
            receipt = applier.apply(image_dir=image, studio_dir=studio,
                                    prior_manifest=prior)
            backup_dir = Path(receipt["backup_dir"])
            self.assertTrue(backup_dir.is_dir(), "no backup directory")
            self.assertEqual(
                (backup_dir / "old.py").read_text(encoding="utf-8"),
                "OLD CONTENT",
                "the backup does not recover the deleted original — the "
                "recovery path is the point, not the count")
            self.assertEqual(
                (studio / "new.py").read_text(encoding="utf-8"), "NEW")

    def test_backup_captures_replaced_files_too(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_bak2_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            (studio / "both.py").write_text("V1", encoding="utf-8")
            image = _write_image(root, {"both.py": "V2"})
            prior = _prior_manifest(root, {"both.py": "V1"})
            receipt = applier.apply(image_dir=image, studio_dir=studio,
                                    prior_manifest=prior)
            backup = Path(receipt["backup_dir"])
            self.assertEqual(
                (backup / "both.py").read_text(encoding="utf-8"), "V1",
                "a replaced file's prior bytes were not captured")

    def test_receipt_names_the_backup_pointer(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_rcpt_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            image = _write_image(root, {"new.py": "NEW"})
            receipt = applier.apply(image_dir=image, studio_dir=studio,
                                    prior_manifest=None)
            self.assertIn("backup_dir", receipt)
            self.assertTrue(Path(receipt["backup_dir"]).is_dir())


class NeverTouchTests(unittest.TestCase):
    """AC5 — the never-touch class survives a full apply unchanged."""

    def test_harness_configs_neither_replaced_nor_deleted(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_nt_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            (studio / ".claude").mkdir()
            (studio / ".cursorrules").write_text(
                "USER RULES", encoding="utf-8")
            (studio / ".claude" / "settings.json").write_text(
                '{"user": true}', encoding="utf-8")
            image = _write_image(root, {
                ".claude/settings.json": '{"machine": true}',
                ".cursorrules": "MACHINE RULES",
                "tool.py": "x",
            })
            prior = _prior_manifest(root, {
                ".claude/settings.json": '{"older": true}',
                ".cursorrules": "OLDER RULES",
            })
            applier.apply(image_dir=image, studio_dir=studio,
                          prior_manifest=prior)
            self.assertEqual(
                (studio / ".claude" / "settings.json").read_text(
                    encoding="utf-8"), '{"user": true}',
                "a harness config was silently reverted")
            self.assertEqual(
                (studio / ".cursorrules").read_text(encoding="utf-8"),
                "USER RULES")


class FailureHonestyTests(unittest.TestCase):
    """AC8 — a mid-apply failure halts, names the operation, leaves the
    backup intact, and performs NO rollback."""

    def test_failure_names_operation_and_leaves_evidence(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_fail_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            (studio / "gone.py").write_text("old", encoding="utf-8")
            image = _write_image(root, {"a.py": "1", "b.py": "2"})
            prior = _prior_manifest(root, {"gone.py": "old"})
            # Plant a failure at the second replace: make its target's
            # parent an unwritable FILE after the first op applied.
            plan_result = applier.plan(image_dir=image, studio_dir=studio,
                                       prior_manifest=prior)
            real_write = Path.write_bytes

            def failing_write(self, data):
                if self.name == "b.py":
                    raise OSError("planted mid-apply failure")
                return real_write(self, data)

            with mock.patch.object(Path, "write_bytes", failing_write):
                with self.assertRaises(applier.ApplyFailure) as caught:
                    applier.apply(image_dir=image, studio_dir=studio,
                                  prior_manifest=prior)
            message = str(caught.exception)
            self.assertIn("b.py", message, "the failing op was not named")
            self.assertIn("2", message,
                          "the failing operation INDEX was not named")
            # No rollback: the first op STAYS applied.
            self.assertEqual(
                (studio / "a.py").read_text(encoding="utf-8"), "1",
                "a rollback was performed — failure honesty means the "
                "applied prefix stays and the evidence tells the story")




class BootstrapTests(unittest.TestCase):
    """AC7 — the applier that executes is the one from the NEW image,
    staged to a temp path and run from there."""

    def test_new_image_applier_executes_not_the_installed_one(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_boot_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            # An INSTALLED applier that is the retired delta engine: if the
            # bootstrap runs THIS one, the sentinel never appears.
            (studio / "vault" / "tools").mkdir(parents=True)
            (studio / "vault" / "tools" / "tropo-apply-image.py").write_text(
                "raise SystemExit('retired delta engine must not run')\n",
                encoding="utf-8")
            image = _write_image(root, {"vault/tool.py": "new"})
            # The image carries the NEW applier AND its lib dependency —
            # the box is complete by design; a real image ships both.
            (image / "vault" / "tools" / "lib").mkdir(
                parents=True, exist_ok=True)
            shutil.copy2(
                Path(applier.__file__).parent / "lib"
                / "package_state_exclusions.py",
                image / "vault" / "tools" / "lib"
                / "package_state_exclusions.py")
            shutil.copy2(
                Path(applier.__file__),
                image / "vault" / "tools" / "tropo-apply-image.py")
            receipt = applier.bootstrap(image_dir=image, studio_dir=studio)
            self.assertEqual(receipt["mode"], "legacy-source")
            self.assertEqual(
                (studio / "vault" / "tool.py").read_text(encoding="utf-8"),
                "new",
                "the new image's applier did not execute")


class IdempotencyTests(unittest.TestCase):
    """AC9 — applying the same image twice changes nothing on the second
    run beyond a new receipt."""

    def test_second_apply_is_a_no_op_beyond_the_receipt(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_idem_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            (studio / "old.py").write_text("old", encoding="utf-8")
            image = _write_image(root, {"a.py": "A", "b/c.py": "B"})
            prior = _prior_manifest(root, {"old.py": "old"})
            first = applier.apply(image_dir=image, studio_dir=studio,
                                  prior_manifest=prior, version="run1")
            self.assertEqual(first["deleted"], 1)
            state_after_first = _tree_state(studio)
            second = applier.apply(image_dir=image, studio_dir=studio,
                                   version="run2")
            self.assertEqual(second["deleted"], 0,
                             "the second run deleted something")
            self.assertEqual(second["replaced"], 2)  # replace is idempotent
            state_after_second = _tree_state(studio)
            receipts = {p.name for p in (studio / "vault" / "updates").rglob("*")
                        if p.is_file() and "backups" not in p.parts}
            # Beyond receipts and backups, the studio state is unchanged.
            core_before = {
                k: v for k, v in state_after_first.items()
                if "vault/updates" not in k}
            core_after = {
                k: v for k, v in state_after_second.items()
                if "vault/updates" not in k}
            self.assertEqual(core_before, core_after,
                             "the second apply changed governed state")


class MigrationContractTests(unittest.TestCase):
    """AC10 — no unwired user-content rewriter ships in the image."""

    def test_an_undeclared_migration_in_the_box_refuses(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_mig_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            image = _write_image(root, {"vault/tool.py": "x"})
            migrations = image / ".tropo" / "playbooks" / "migrations"
            migrations.mkdir(parents=True)
            (migrations / "stowaway.playbook.md").write_text(
                "---\nuid: deadbee1\ntitle: rewrite user files\n---\n",
                encoding="utf-8")
            with self.assertRaises(applier.MigrationContractError):
                applier.assert_migration_contract(image)

    def test_a_declared_and_wired_migration_passes(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_mig2_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            image = _write_image(root, {"vault/tool.py": "x"})
            self.assertTrue(applier.assert_migration_contract(image))




class LegacySourceModeTests(unittest.TestCase):
    """AC6 — no prior image manifest: replace phase completes, deletions
    SKIP with one named WARN, no halt, no guess. Every studio installed
    before this ships is in this mode on its first lift-and-replace."""

    def test_legacy_source_completes_and_warns(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_leg_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            # A stale OS file the new image drops: in legacy-source it
            # SURVIVES (recoverable harm), named by the WARN.
            (studio / "stale-os.py").write_text("old", encoding="utf-8")
            image = _write_image(root, {"fresh.py": "new"})
            receipt = applier.apply(image_dir=image, studio_dir=studio,
                                    prior_manifest=None)
            self.assertEqual(receipt["mode"], "legacy-source")
            self.assertEqual(receipt["deleted"], 0,
                             "legacy-source deleted — it must skip, not guess")
            self.assertEqual(len(receipt["warnings"]), 1)
            self.assertIn("no prior image manifest", receipt["warnings"][0])
            self.assertTrue(
                (studio / "stale-os.py").is_file(),
                "a stale OS file was removed in legacy-source mode")
            self.assertEqual(
                (studio / "fresh.py").read_text(encoding="utf-8"), "new")

    def test_legacy_source_never_touches_user_content(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v190_leg2_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            (studio / "user" / "notes").mkdir(parents=True)
            (studio / "user" / "notes" / "mine.md").write_text(
                "USER CONTENT", encoding="utf-8")
            image = _write_image(root, {"os.py": "x"})
            before = _tree_state(studio / "user")
            applier.apply(image_dir=image, studio_dir=studio,
                          prior_manifest=None)
            self.assertEqual(_tree_state(studio / "user"), before,
                             "user content changed under legacy-source")


class UpdateHistoryWriterTests(unittest.TestCase):
    """4e9ce4cc row 3 / AC2 — the customer's update history survives and
    grows: across a bootstrap apply, planted rows survive as a byte-identical
    prefix plus exactly one appended truthful row (success or failure).
    Exclusion of the file from every image is T53's landed work; the WRITER
    is this spec's."""

    PLANTED = [
        {"version": "1.90.0", "outcome": "success", "mode": "full",
         "backup_dir": "/prior", "utc": "2026-08-01T00:00:00Z"},
        {"version": "1.93.0", "outcome": "success", "mode": "full",
         "backup_dir": "/prior2", "utc": "2026-08-20T00:00:00Z"},
    ]

    def _studio_with_planted_history(self, root: Path) -> Path:
        studio = root / "studio"
        (studio / "vault" / "updates").mkdir(parents=True)
        planted_bytes = "".join(
            json.dumps(r) + "\n" for r in self.PLANTED).encode("utf-8")
        (studio / "vault" / "updates" / "update-history.jsonl").write_bytes(
            planted_bytes)
        return studio

    def _image_with_manifest_version(self, root: Path, version: str) -> Path:
        image = _write_image(root, {"os.py": "new"})
        (image / "tropo-image-manifest.json").write_text(
            json.dumps({"schema": "tropo.image-manifest/v1",
                        "version": version, "file_count": 1,
                        "files": {"os.py": {"sha256": "0" * 64, "bytes": 3}}}),
            encoding="utf-8")
        return image

    def _history_bytes(self, studio: Path) -> bytes:
        return (studio / "vault" / "updates" / "update-history.jsonl").read_bytes()

    def test_success_appends_one_row_with_the_image_manifest_version(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v194_hist_") as tmp:
            root = Path(tmp).resolve()
            studio = self._studio_with_planted_history(root)
            (studio / "os.py").write_text("old", encoding="utf-8")
            image = self._image_with_manifest_version(root, "1.94.0")
            prior = _prior_manifest(root, {"os.py": "old"})

            receipt = applier.apply(image_dir=image, studio_dir=studio,
                                    prior_manifest=prior)

            planted_bytes = "".join(
                json.dumps(r) + "\n" for r in self.PLANTED).encode("utf-8")
            after = self._history_bytes(studio)
            self.assertTrue(
                after.startswith(planted_bytes),
                "planted rows are not a byte-identical prefix — the "
                "customer's prior history was damaged")
            appended = after[len(planted_bytes):]
            lines = appended.decode("utf-8").splitlines()
            self.assertEqual(len(lines), 1,
                             f"expected exactly one appended row, got {len(lines)}")
            row = json.loads(lines[0])
            self.assertEqual(row["version"], "1.94.0",
                             "version must come from the image manifest, "
                             "not the stamp")
            self.assertEqual(row["outcome"], "success")
            self.assertEqual(row["mode"], receipt["mode"])
            self.assertEqual(row["backup_dir"], receipt["backup_dir"])
            self.assertIn("utc", row)

    def test_failure_path_appends_a_failed_row(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v194_histf_") as tmp:
            root = Path(tmp).resolve()
            studio = self._studio_with_planted_history(root)
            (studio / "a.py").write_text("old", encoding="utf-8")
            image = self._image_with_manifest_version(root, "1.94.0")
            prior = _prior_manifest(root, {"a.py": "old"})
            real_write = Path.write_bytes

            def failing_write(self, data):
                if self.name == "os.py":
                    raise OSError("planted failure")
                return real_write(self, data)

            with mock.patch.object(Path, "write_bytes", failing_write):
                with self.assertRaises(applier.ApplyFailure):
                    applier.apply(image_dir=image, studio_dir=studio,
                                  prior_manifest=prior)

            rows = [json.loads(line) for line in
                    self._history_bytes(studio).decode("utf-8").splitlines()]
            self.assertEqual(len(rows), len(self.PLANTED) + 1)
            self.assertEqual(rows[-1]["outcome"], "failed",
                             "a failed apply must still record its row — "
                             "the history is the customer's, and a failed "
                             "attempt is part of it")
            self.assertEqual(rows[-1]["version"], "1.94.0")

    def test_no_manifest_version_falls_back_to_the_stamp(self) -> None:
        applier = _load_applier()
        with tempfile.TemporaryDirectory(prefix="v194_hist stamp".replace(" ", "_")) as tmp:
            root = Path(tmp).resolve()
            studio = self._studio_with_planted_history(root)
            (studio / "os.py").write_text("old", encoding="utf-8")
            image = _write_image(root, {"os.py": "new"})  # NO image manifest
            prior = _prior_manifest(root, {"os.py": "old"})

            receipt = applier.apply(image_dir=image, studio_dir=studio,
                                    prior_manifest=prior, version="20260830T230000")

            rows = [json.loads(line) for line in
                    self._history_bytes(studio).decode("utf-8").splitlines()]
            self.assertEqual(rows[-1]["version"], receipt["version"],
                             "without a manifest version the row must carry "
                             "the same stamp as the receipt — an honest "
                             "unknown, never a fabricated semver")

    def test_the_cli_stdout_stays_one_json_document(self) -> None:
        """bootstrap json.loads the child applier's WHOLE stdout; a stray
        print anywhere in the apply path breaks it silently far away."""
        import subprocess
        import sys as _sys
        with tempfile.TemporaryDirectory(prefix="v194_histcli_") as tmp:
            root = Path(tmp).resolve()
            studio = root / "studio"
            studio.mkdir()
            (studio / "os.py").write_text("old", encoding="utf-8")
            image = self._image_with_manifest_version(root, "1.94.0")
            prior = _prior_manifest(root, {"os.py": "old"})
            proc = subprocess.run(
                [_sys.executable, str(TOOLS / "tropo-apply-image.py"), "apply",
                 "--image", str(image), "--studio", str(studio),
                 "--prior-manifest", str(prior)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
            receipt = json.loads(proc.stdout)  # ONE document, whole stdout
            self.assertEqual(receipt["schema"], "tropo.apply-receipt/v1")
            rows = [json.loads(line) for line in
                    (studio / "vault" / "updates" / "update-history.jsonl")
                    .read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
