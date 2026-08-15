#!/usr/bin/env python3
"""Behavior tests for corrected v1.87 velocity items 2 and 6."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load("v187_corrected_build", ROOT / "vault/tools/tropo-build-release.py")


class PostRebuildValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="v187-post-rebuild-")
        self.root = Path(self.temporary.name)
        (self.root / ".tropo").mkdir()
        tools = self.root / "vault/tools"
        tests = tools / "tests"
        tests.mkdir(parents=True)
        shutil.copy2(
            ROOT / "vault/tools/tropo-rebuild-vault.py",
            tools / "tropo-rebuild-vault.py",
        )
        (tools / "tropo-rebuild-index.py").write_text(
            "print('dummy rebuild')\n", encoding="utf-8"
        )
        (tools / "tropo-validate.py").write_text(
            "from pathlib import Path\n"
            "counter = Path(__file__).with_name('validator-count.txt')\n"
            "count = int(counter.read_text() or '0') if counter.exists() else 0\n"
            "counter.write_text(str(count + 1))\n"
            "print('Summary: 1 passed, 0 failed, 0 warnings, 0 normalizable')\n",
            encoding="utf-8",
        )
        (tests / "test_post_migration_release_clean.py").write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "counter = Path(__file__).parents[1] / 'post-validator-count.txt'\n"
            "count = int(counter.read_text() or '0') if counter.exists() else 0\n"
            "counter.write_text(str(count + 1))\n"
            "print('Result: 1 passed, 0 failed (recorded studio debt: 0, from test)')\n"
            "print('PASS — studio debt unchanged at 0.')\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        (self.root / "vault/00-index.jsonl").write_text("", encoding="utf-8")
        self.rebuild = tools / "tropo-rebuild-vault.py"

    def tearDown(self):
        self.temporary.cleanup()

    def test_build_path_skips_precheck_then_runs_one_post_rebuild_validator(self):
        run_id = "a" * 32
        rebuild = subprocess.run(
            [
                sys.executable,
                str(self.rebuild),
                "--vault-path",
                str(self.root),
                "--dry-run",
                "--skip-validator",
                "--validator-run-id",
                run_id,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(rebuild.returncode, 0, rebuild.stdout + rebuild.stderr)
        self.assertIn("no validator launched here", rebuild.stdout)
        self.assertFalse((self.root / "vault/tools/validator-count.txt").exists())

        with (
            patch.multiple(
                build.tropo_roots,
                STUDIO_ROOT=self.root,
                VAULT_DIR=self.root / "vault",
            ),
            patch.object(build, "STUDIO_DEBT_RATCHET_TIMEOUT_S", 10),
        ):
            receipt = build._run_post_rebuild_validation(run_id)

        self.assertTrue(receipt["clear"])
        self.assertEqual(receipt["phase"], "post-rebuild")
        self.assertEqual(receipt["attempt_id"], run_id)
        self.assertEqual(
            (self.root / "vault/tools/post-validator-count.txt").read_text(),
            "1",
        )
        self.assertTrue(receipt["tree_sha256"])
        self.assertTrue(
            (self.root / ".tropo-studio/locks/build-validation-receipt.json").is_file()
        )

    def test_standalone_rebuild_still_runs_its_validator(self):
        result = subprocess.run(
            [
                sys.executable,
                str(self.rebuild),
                "--vault-path",
                str(self.root),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.root / "vault/tools/validator-count.txt").read_text(),
            "1",
        )

    def test_skip_without_valid_attempt_id_refuses(self):
        result = subprocess.run(
            [
                sys.executable,
                str(self.rebuild),
                "--vault-path",
                str(self.root),
                "--dry-run",
                "--skip-validator",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires --validator-run-id", result.stderr)

    def test_malformed_post_rebuild_output_fails_closed(self):
        bad = self.root / "vault/tools/tests/test_post_migration_release_clean.py"
        bad.write_text("print('no result line')\n", encoding="utf-8")
        with (
            patch.multiple(
                build.tropo_roots,
                STUDIO_ROOT=self.root,
                VAULT_DIR=self.root / "vault",
            ),
            patch.object(build, "STUDIO_DEBT_RATCHET_TIMEOUT_S", 10),
        ):
            receipt = build._run_post_rebuild_validation("b" * 32)
        self.assertFalse(receipt["clear"])
        self.assertIsNone(receipt["summary"])


class HeadlessWalkAnswerTests(unittest.TestCase):
    class UnreadablePipe:
        @staticmethod
        def isatty():
            return False

        @staticmethod
        def readline():
            raise AssertionError("non-TTY stdin must never be read")

    def test_non_tty_defaults_immediately_without_reading(self):
        output = io.StringIO()
        with patch.dict(build.os.environ, {}, clear=True), redirect_stdout(output):
            answer, interactive = build._resolve_walk_answer(
                stdin=self.UnreadablePipe()
            )
        self.assertEqual(answer, "")
        self.assertFalse(interactive)
        self.assertIn("stdin not read", output.getvalue())

    def test_flag_precedes_environment_and_invalid_value_refuses(self):
        with patch.dict(
            build.os.environ, {build.WALK_ANSWER_ENV: "n"}, clear=True
        ):
            answer, interactive = build._resolve_walk_answer(
                explicit_answer="yes",
                stdin=self.UnreadablePipe(),
            )
        self.assertEqual(answer, "")
        self.assertFalse(interactive)
        with self.assertRaises(ValueError):
            build._resolve_walk_answer(
                explicit_answer="maybe",
                stdin=self.UnreadablePipe(),
            )

    def test_noninteractive_no_cannot_claim_skipped_by_mike(self):
        with tempfile.TemporaryDirectory(prefix="v187-walk-no-") as temporary:
            root = Path(temporary)
            verdict = root / "cold-walk-verdict.json"
            with (
                patch.dict(build.os.environ, {}, clear=True),
                self.assertRaises(SystemExit) as refusal,
            ):
                build.step_10_6_cold_walk_gate(
                    "1.87.0",
                    str(root),
                    str(verdict),
                    str(root / "last.json"),
                    walk_answer="n",
                    stdin=self.UnreadablePipe(),
                )
            self.assertFalse(verdict.exists())
        self.assertEqual(refusal.exception.code, 2)

    def test_real_tty_still_prompts_and_may_answer_no(self):
        class Tty:
            @staticmethod
            def isatty():
                return True

        with patch("builtins.input", return_value="n") as prompt:
            answer, interactive = build._resolve_walk_answer(stdin=Tty())
        self.assertEqual(answer, "n")
        self.assertTrue(interactive)
        prompt.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
