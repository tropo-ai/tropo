"""Compatibility coverage for the user-facing Tropo health wrapper."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
TROPO_TEST_PATH = ROOT / "vault" / "tools" / "tropo-test.py"
SPEC = importlib.util.spec_from_file_location("tropo_test_health", TROPO_TEST_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError("could not load tropo-test.py")
TROPO_TEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TROPO_TEST)


class StudioVersionTests(unittest.TestCase):
    def _parse(self, content: str) -> str:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            version_dir = root / ".tropo"
            version_dir.mkdir()
            (version_dir / "version.md").write_text(content, encoding="utf-8")
            return TROPO_TEST.read_studio_version(root)

    def test_canonical_bare_version(self) -> None:
        self.assertEqual(self._parse("v1.84.1\n"), "1.84.1")
        self.assertEqual(self._parse("\n \tv1.84.1  \n\n"), "1.84.1")

    def test_legacy_decorated_version(self) -> None:
        self.assertEqual(self._parse("**Current:** v1.84.1\n"), "1.84.1")
        self.assertEqual(
            self._parse(
                "# Tropo version\n\n"
                "**Current:** v1.84.1\n\n"
                "This file records the installed release.\n"
            ),
            "1.84.1",
        )

    def test_actual_studio_version_is_accepted(self) -> None:
        self.assertEqual(TROPO_TEST.read_studio_version(ROOT), "1.84.1")

    def test_malformed_versions_are_unknown(self) -> None:
        malformed = (
            "",
            " \t\n",
            "1.84.1\n",
            "v1.84\n",
            "v1..1\n",
            "v01.84.1\n",
            "v1.84.1 trailing\n",
            "prefix v1.84.1\n",
            "v1.84.1-rc1\n",
            "v1.84.1+build.7\n",
            "v1.84.1.0\n",
            "**Current:** v1..1\n",
            "**Current:** v1.84\n",
            "**Current:** v1.84.1 trailing\n",
            "prefix **Current:** v1.84.1\n",
        )
        for content in malformed:
            with self.subTest(content=content):
                self.assertEqual(self._parse(content), "unknown")

    def test_unicode_digit_mutations_are_unknown(self) -> None:
        mutations = (
            "v١.84.1\n",
            "v1.٨٤.1\n",
            "v1.84.١\n",
            "v1.8٤.1\n",
            "v1.84.1١\n",
            "**Current:** v1.8٤.1\n",
        )
        for content in mutations:
            with self.subTest(content=content):
                self.assertEqual(self._parse(content), "unknown")

    def test_multiline_and_duplicate_decorated_mutations_are_unknown(self) -> None:
        mutations = (
            "**Current:**\nv1.84.1\n",
            "**Current:** v1.\n84.1\n",
            "**Current:** v1.84.1\n**Current:** v1.84.1\n",
            "**Current:** v1.84.1\n**Current:** v1.84.2\n",
            "**Current:** v1.84.1\n\n**Current:** v1.84\n",
            "**Current:** v1.84.1\nv1.84.1\n",
            "v1.84.2\n**Current:** v1.84.1\n",
            "**Current:** v1.84.1\nInstalled after v1.84.0.\n",
        )
        for content in mutations:
            with self.subTest(content=content):
                self.assertEqual(self._parse(content), "unknown")

    def test_extra_canonical_content_lines_are_unknown(self) -> None:
        mutations = (
            "v1.84.1\nnotes\n",
            "notes\nv1.84.1\n",
            "v1.84.1\nv1.84.1\n",
            "v1.84.1\nv1.84.2\n",
        )
        for content in mutations:
            with self.subTest(content=content):
                self.assertEqual(self._parse(content), "unknown")


class PythonPreflightTests(unittest.TestCase):
    def test_below_floor_main_fails_loud_with_actual_interpreter(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(
            TROPO_TEST.sys, "version_info", (3, 8, 19)
        ), mock.patch.object(
            TROPO_TEST.sys, "executable", "/fixture/bin/python3"
        ), contextlib.redirect_stderr(stderr):
            exit_code = TROPO_TEST.main()

        message = stderr.getvalue()
        self.assertEqual(exit_code, 3)
        self.assertIn("requires Python >= 3.9", message)
        self.assertIn("actual interpreter: /fixture/bin/python3", message)
        self.assertIn("actual version: Python 3.8.19", message)

    def test_supported_floor_passes_without_output(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            supported = TROPO_TEST.python_version_preflight(
                (3, 9, 0), "/fixture/bin/python3.9"
            )
        self.assertTrue(supported)
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
