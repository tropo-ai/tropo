#!/usr/bin/env python3
"""Isolated plants for the strict generic test-spec v1.3 mint gate."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
SCRIPTS = ROOT / ".tropo" / "scripts"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mint = _load("test_spec_v13_mint_id", TOOLS / "tropo-mint-id.py")
check_one = _load("test_spec_v13_check_one", TOOLS / "tropo-check-one.py")
from lib import index_surfaces, template_leg  # noqa: E402
from lib import test_spec_validators  # noqa: E402


DEV_UID = "dddd0001"
ACTIVATION_UID = "aaaa0001"
TARGET_PATH = "vault/tools/tests/mint-v13-fixture.py"


def _write_entry(root: Path, uid: str, frontmatter: dict) -> Path:
    path = root / "vault" / "files" / f"{uid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n\n# Scratch fixture\n",
        encoding="utf-8",
    )
    return path


def _read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    end = text.find("\n---", 4)
    assert end != -1
    value = yaml.safe_load(text[4:end])
    assert isinstance(value, dict)
    return value


class ScratchMintRoot:
    def __init__(self, *, rebuild: bool = True) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="test_spec_v13_mint_")
        # .resolve(): macOS tempfile returns /var/folders/..., a symlink to
        # /private/var/folders/.... mint_file() resolves the root internally,
        # so an unresolved fixture root fails every containment check. Same
        # one-line defect as test_typed_mint_phase1.py (metis-g103 2026-08-06).
        self.root = Path(self._temp.name).resolve()
        (self.root / ".tropo").mkdir()
        (self.root / "vault" / "files").mkdir(parents=True)
        self.workspace = (
            self.root
            / "agents"
            / "test-agent"
            / ".tropo-capsule"
            / "workspace"
        )
        self.workspace.mkdir(parents=True)
        capsules = self.root / "vault" / "capsules"
        capsules.mkdir()
        tools = self.root / "vault" / "tools"
        tools.mkdir()
        shutil.copy2(
            ROOT / "vault" / "capsules" / "tropo-test-spec.capsule.md",
            capsules / "tropo-test-spec.capsule.md",
        )
        # Production Phase 1 intentionally accepts only note/task/dev-spec.
        # This isolated legacy-suite fixture gives test-spec its own visible
        # companion binding so the generic mint/check-one contract remains
        # covered without adding a fourth production template or fallback.
        embedded_leg = template_leg.load_template_leg(self.root, "test-spec")
        templates = capsules / "templates"
        templates.mkdir()
        companion = templates / "test-spec.template.md"
        companion.write_text(
            embedded_leg.scaffold.replace(
                "uid: <<MINT:uid>>\n",
                "uid: '<<MINT:uid>>'\n",
                1,
            ).replace(
                "created_by: <<MINT:author>>\n",
                "created_by: <<MINT:author>>\n"
                "created_by_activation_uid: <<MINT:activation_uid>>\n",
                1,
            ),
            encoding="utf-8",
        )
        companion_hash = hashlib.sha256(companion.read_bytes()).hexdigest()
        capsule_path = capsules / "tropo-test-spec.capsule.md"
        capsule_text = capsule_path.read_text(encoding="utf-8")
        capsule_text = capsule_text.replace(
            "version: '1.3'\n",
            "version: '1.3'\n"
            "mint_mode: human\n"
            "mint_template: vault/capsules/templates/test-spec.template.md\n"
            "mint_template_version: 'test-only-1.0'\n"
            f"mint_template_sha256: {companion_hash}\n"
            "mint_output_home: vault/files\n",
            1,
        )
        capsule_path.write_text(capsule_text, encoding="utf-8")
        (capsules / "mint-registry.json").write_bytes(
            template_leg.build_mint_registry_bytes(self.root)
        )
        shutil.copy2(
            TOOLS / "tropo-mint-id.py",
            tools / "tropo-mint-id.py",
        )
        shutil.copytree(TOOLS / "lib", tools / "lib")
        if rebuild:
            for name in (
                "tropo-rebuild-index.py",
                "tropo-generate-relations-header.py",
                "tropo-navblock-strip.py",
            ):
                shutil.copy2(TOOLS / name, tools / name)

    @property
    def mint_script(self) -> Path:
        return self.root / "vault" / "tools" / "tropo-mint-id.py"

    @property
    def rebuild_script(self) -> Path:
        return self.root / "vault" / "tools" / "tropo-rebuild-index.py"

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.mint_script), *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )

    def initialize_index(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(self.rebuild_script),
                "--apply",
                "--skip-rehydrate",
                "--vault-path",
                str(self.root),
            ],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)

    def close(self) -> None:
        self._temp.cleanup()


class TestSpecV13MintTests(unittest.TestCase):
    def test_template_loads_and_consumes_the_five_exact_tokens(self) -> None:
        scratch = ScratchMintRoot()
        self.addCleanup(scratch.close)

        leg = template_leg.load_mint_template(scratch.root, "test-spec")
        self.assertEqual(leg.capsule_version, "1.3")
        self.assertEqual(
            set(template_leg.MINT_TOKEN_RE.findall(leg.scaffold)),
            {"uid", "date", "author", "capsule_version", "activation_uid"},
        )

        uid, path = mint.mint_file(
            "test-spec",
            author="talos-t33",
            studio_root=scratch.root,
            output_dir=scratch.workspace / "template-output",
            freshen=False,
        )
        self.assertEqual(
            path,
            scratch.workspace / "template-output" / f"{uid}.md",
        )
        text = path.read_text(encoding="utf-8")
        self.assertEqual(template_leg.find_stray_mint_tokens(text), [])
        frontmatter = _read_frontmatter(path)
        self.assertEqual(frontmatter["uid"], uid)
        self.assertEqual(frontmatter["type"], "test-spec")
        self.assertEqual(frontmatter["status"], "draft")
        self.assertEqual(frontmatter["state"], "active")
        self.assertEqual(frontmatter["capsule_version"], "1.3")
        self.assertTrue(
            {
                "target_substrate",
                "target_subsystem",
                "triggered_by_dev_cycle",
                "behaviors_covered",
                "coverage_class",
                "acceptance_criteria",
            }
            <= frontmatter.keys()
        )
        self.assertGreater(
            len(template_leg.find_required_placeholders(text)),
            0,
        )

    def test_mint_consume_freshen_and_check_one_converge_in_scratch(self) -> None:
        scratch = ScratchMintRoot()
        self.addCleanup(scratch.close)
        target = scratch.root / TARGET_PATH
        target.parent.mkdir(parents=True)
        target.write_text("# deterministic scratch substrate\n", encoding="utf-8")
        _write_entry(
            scratch.root,
            DEV_UID,
            {
                "uid": DEV_UID,
                "type": "dev-spec",
                "title": "Scratch dev-spec",
                "status": "active",
                "target_release": "1.86.0",
                "target_stream": "mint-v13",
                "committed_substrate": [
                    {
                        "target": TARGET_PATH,
                        "change_class": "NEW",
                        "description": "Scratch target",
                    }
                ],
                "acceptance_criteria": ["The scratch mint converges."],
            },
        )
        _write_entry(
            scratch.root,
            ACTIVATION_UID,
            {
                "uid": ACTIVATION_UID,
                "type": "activation",
                "title": "Scratch activation",
                "status": "active",
                "dev_spec_uid": DEV_UID,
            },
        )
        scratch.initialize_index()

        result = scratch.run(
            "--type",
            "test-spec",
            "--author",
            "talos-t33",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        uid = result.stdout.strip()
        self.assertRegex(uid, r"^[0-9a-f]{8}$")
        path = scratch.root / "vault" / "files" / f"{uid}.md"
        self.assertTrue(path.is_file())

        current_rows = [
            row
            for row in index_surfaces.iter_jsonl(
                scratch.root / "vault" / "00-index.jsonl"
            )
            if row.get("uid") == uid
        ]
        self.assertEqual(len(current_rows), 1)
        self.assertEqual(current_rows[0]["path"], f"vault/files/{uid}.md")
        with sqlite3.connect(scratch.root / "vault" / "00-index.sqlite") as conn:
            sqlite_row = conn.execute(
                "SELECT fm_json FROM entries WHERE uid=?",
                (uid,),
            ).fetchone()
        self.assertIsNotNone(sqlite_row)
        self.assertEqual(json.loads(sqlite_row[0])["path"], f"vault/files/{uid}.md")

        frontmatter = _read_frontmatter(path)
        frontmatter.update(
            {
                "title": "Scratch Test-Spec",
                "description": "Scratch proof of strict generic mint convergence.",
                "member_of": [DEV_UID],
                "triggered_by_dev_cycle": ACTIVATION_UID,
                "target_release": "1.86.0",
                "target_substrate": [TARGET_PATH],
                "acceptance_criteria": (
                    "The scratch template is consumed, freshened, and passes "
                    "the targeted validator with no findings."
                ),
                "behaviors_covered": [
                    {
                        "behavior_description": (
                            "The targeted validator proves the scratch substrate "
                            "is paired by exact canonical path."
                        ),
                        "test_substrate_path": TARGET_PATH,
                        "verification_method": "structural_check",
                        "target_substrate_refs": [TARGET_PATH],
                        "verifies_acceptance_criterion": 1,
                    }
                ],
            }
        )
        path.write_text(
            "---\n"
            + yaml.safe_dump(frontmatter, sort_keys=False)
            + "---\n\n# Scratch Test-Spec\n",
            encoding="utf-8",
        )
        self.assertEqual(
            template_leg.find_required_placeholders(
                path.read_text(encoding="utf-8")
            ),
            [],
        )

        freshen = subprocess.run(
            [sys.executable, str(scratch.rebuild_script), "--only", uid],
            cwd=scratch.root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(freshen.returncode, 0, freshen.stdout + freshen.stderr)
        targeted = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "tropo-check-one.py"),
                uid,
                "--capsule",
                "test-spec",
                "--vault-path",
                str(scratch.root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            targeted.returncode,
            0,
            targeted.stdout + targeted.stderr,
        )
        self.assertIn("0 finding(s), 0 defect(s)", targeted.stdout)

    def test_missing_and_nonzero_freshen_roll_back_canonical_birth(self) -> None:
        for mode in ("missing", "nonzero"):
            with self.subTest(mode=mode):
                scratch = ScratchMintRoot(rebuild=False)
                self.addCleanup(scratch.close)
                if mode == "nonzero":
                    scratch.rebuild_script.write_text(
                        "def freshen_many(*args, **kwargs):\n"
                        "    return 7\n",
                        encoding="utf-8",
                    )

                result = scratch.run(
                    "--type",
                    "test-spec",
                    "--author",
                    "talos-t33",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("path:", result.stderr)
                self.assertEqual(
                    list((scratch.root / "vault" / "files").glob("*.md")),
                    [],
                )
                if mode == "missing":
                    self.assertIn("freshener is missing", result.stderr)
                else:
                    self.assertIn("transaction refused", result.stderr)

    def test_callable_no_freshen_requires_explicit_scratch_output(self) -> None:
        scratch = ScratchMintRoot(rebuild=False)
        self.addCleanup(scratch.close)

        with self.assertRaisesRegex(
            ValueError,
            "freshen=False is legal only with an explicit scratch output_dir",
        ):
            mint.mint_file(
                "test-spec",
                author="talos-t33",
                studio_root=scratch.root,
                freshen=False,
            )
        self.assertEqual(
            list((scratch.root / "vault" / "files").glob("*.md")),
            [],
        )

        with self.assertRaisesRegex(
            ValueError, "scratch|canonical home"
        ):
            mint.mint_file(
                "test-spec",
                author="talos-t33",
                studio_root=scratch.root,
                output_dir=scratch.root / "vault" / "files",
                freshen=False,
            )
        self.assertEqual(
            list((scratch.root / "vault" / "files").glob("*.md")),
            [],
        )

        output_dir = scratch.workspace / "explicit"
        uid, path = mint.mint_file(
            "test-spec",
            author="talos-t33",
            studio_root=scratch.root,
            output_dir=output_dir,
            freshen=False,
        )
        self.assertEqual(path, output_dir / f"{uid}.md")
        self.assertTrue(path.is_file())

    def test_cli_no_freshen_rejects_canonical_birth_before_write(self) -> None:
        scratch = ScratchMintRoot(rebuild=False)
        self.addCleanup(scratch.close)

        refused = scratch.run(
            "--type",
            "test-spec",
            "--author",
            "talos-t33",
            "--no-freshen",
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(refused.stdout, "")
        self.assertIn(
            "canonical --type birth cannot use --no-freshen",
            refused.stderr,
        )
        self.assertIn("explicit scratch --output-dir", refused.stderr)
        self.assertEqual(
            list((scratch.root / "vault" / "files").glob("*.md")),
            [],
        )

        output_dir = scratch.workspace / "cli"
        allowed = scratch.run(
            "--type",
            "test-spec",
            "--author",
            "talos-t33",
            "--no-freshen",
            "--output-dir",
            str(output_dir),
        )
        self.assertEqual(
            allowed.returncode,
            0,
            allowed.stdout + allowed.stderr,
        )
        uid = allowed.stdout.strip()
        self.assertTrue((output_dir / f"{uid}.md").is_file())

    def test_transaction_refusal_and_false_zero_raise_before_success(self) -> None:
        for code, expected in (
            (1, "transaction refused"),
            (0, "exact-row verification failed"),
        ):
            with self.subTest(code=code):
                scratch = ScratchMintRoot()
                self.addCleanup(scratch.close)
                freshener = mock.Mock()
                freshener.freshen_many.return_value = code
                with mock.patch.object(
                    mint, "_load_rebuild_index", return_value=freshener
                ):
                    with self.assertRaisesRegex(RuntimeError, expected):
                        mint.mint_file(
                            "test-spec",
                            author="talos-t33",
                            studio_root=scratch.root,
                        )
                self.assertEqual(
                    list((scratch.root / "vault" / "files").glob("*.md")),
                    [],
                )

    def test_post_commit_verification_failure_rolls_back_source_and_rows(self) -> None:
        scratch = ScratchMintRoot()
        self.addCleanup(scratch.close)
        scratch.initialize_index()
        uid = "cafebabe"

        with mock.patch.object(
            mint, "mint", return_value=[uid]
        ), mock.patch.object(
            mint,
            "_verify_minted_index_row",
            side_effect=RuntimeError("planted verification failure"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "governed birth was rolled back"
            ):
                mint.mint_file(
                    "test-spec",
                    author="talos-t33",
                    studio_root=scratch.root,
                )

        self.assertFalse(
            (scratch.root / "vault/files" / f"{uid}.md").exists()
        )
        self.assertFalse(mint._derived_uid_present(scratch.root, uid))

    def test_frozen_legacy_cohort_gains_no_generic_fail_or_error(self) -> None:
        frozen = test_spec_validators.FROZEN_LEGACY_TEST_SPEC_UIDS
        self.assertEqual(len(frozen), 46)
        self.assertTrue(
            all((ROOT / "vault" / "files" / f"{uid}.md").is_file() for uid in frozen)
        )
        for uid in sorted(frozen):
            with self.subTest(uid=uid):
                findings = check_one.run_generic_mint_checks(
                    uid,
                    "test-spec",
                    ROOT,
                )
                defects = [
                    finding
                    for finding in findings
                    if "[FAIL]" in finding or "[ERROR]" in finding
                ]
                self.assertEqual(defects, [], findings)


if __name__ == "__main__":
    unittest.main()
