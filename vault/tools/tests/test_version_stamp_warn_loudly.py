#!/usr/bin/env python3
"""Governance-Linkage item 3 (f015450313f2 / f015f5391494): step_8b_stamp_versions
must WARN LOUDLY on a site it cannot reach, not skip silently.

Mike ruled warn-safe, not build-failure: an unmatched or missing site prints a
named WARN line and the step still returns/proceeds. Negative control per the
design brief — point a site at a path that does not exist and assert the WARN
line names it; remove the emit and the test must go red.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load(
    "version_stamp_warn_loudly_build", ROOT / "vault/tools/tropo-build-release.py"
)


class VersionStampWarnsLoudlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.build_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _run(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            total = build.step_8b_stamp_versions(str(self.build_dir), "1.94.0")
        return total, stdout.getvalue(), stderr.getvalue()

    def test_missing_site_warns_loudly_and_names_the_path(self) -> None:
        """Negative control: a site pointed at a path that does not exist
        must still WARN, naming that exact path, in stderr."""
        sites = [
            ("does/not/exist.md", r"Tropo-OS v\d+\.\d+\.\d+", "Tropo-OS v{version}"),
        ]
        with mock.patch.object(build, "VERSION_STAMP_SITES", sites):
            total, _stdout, stderr = self._run()
        self.assertEqual(total, 0)
        self.assertIn("WARN", stderr)
        self.assertIn("does/not/exist.md", stderr)

    def test_unmatched_site_warns_loudly_and_names_the_pattern(self) -> None:
        """A site that exists but whose pattern matches nothing must WARN,
        not silently report zero as if nothing were wrong."""
        target = self.build_dir / "README.md"
        target.write_text("no version claim in this file\n", encoding="utf-8")
        sites = [
            ("README.md", r"Tropo-OS v\d+\.\d+\.\d+", "Tropo-OS v{version}"),
        ]
        with mock.patch.object(build, "VERSION_STAMP_SITES", sites):
            total, _stdout, stderr = self._run()
        self.assertEqual(total, 0)
        self.assertIn("WARN", stderr)
        self.assertIn("README.md", stderr)

    def test_matched_site_stamps_and_emits_no_warn_for_that_site(self) -> None:
        """A site that exists and matches stamps normally, with no WARN
        naming it (WARN is reserved for sites the stamp could not reach)."""
        target = self.build_dir / "README.md"
        target.write_text("Tropo-OS v1.93.0 is live.\n", encoding="utf-8")
        sites = [
            ("README.md", r"Tropo-OS v\d+\.\d+\.\d+", "Tropo-OS v{version}"),
        ]
        with mock.patch.object(build, "VERSION_STAMP_SITES", sites), \
                mock.patch.object(build, "DRY_RUN", False):
            total, stdout, stderr = self._run()
        self.assertEqual(total, 1)
        self.assertIn("Tropo-OS v1.94.0 is live.", target.read_text(encoding="utf-8"))
        self.assertNotIn("WARN", stderr)
        self.assertIn("Version stamp: README.md", stdout)

    def test_summary_line_reports_total_against_configured_site_count(self) -> None:
        """The 'N total stamps' line must be legible against how many sites
        were configured, not a bare count compared to nothing."""
        matched = self.build_dir / "README.md"
        matched.write_text("Tropo-OS v1.93.0\n", encoding="utf-8")
        sites = [
            ("README.md", r"Tropo-OS v\d+\.\d+\.\d+", "Tropo-OS v{version}"),
            ("missing.md", r"Tropo-OS v\d+\.\d+\.\d+", "Tropo-OS v{version}"),
        ]
        with mock.patch.object(build, "VERSION_STAMP_SITES", sites), \
                mock.patch.object(build, "DRY_RUN", False):
            _total, stdout, _stderr = self._run()
        self.assertIn("1 total stamps", stdout)
        self.assertIn("of 2 configured sites", stdout)


class LiveSiteListReachesEverySiteTests(unittest.TestCase):
    """f015450313f2 item 2 / f015f5391494 item 4a: at the time of the fix,
    every configured VERSION_STAMP_SITES entry matched against the live
    Studio tree. A future edit to one of these files that breaks its
    pattern should fail this test loudly, not rot silently the way the
    original six-of-eight went unnoticed for three releases.

    Runs read-only: DRY_RUN forced True so no live file is ever written by
    this test.
    """

    def test_every_configured_site_matches_live_tree(self) -> None:
        with mock.patch.object(build, "DRY_RUN", True):
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                total = build.step_8b_stamp_versions(str(ROOT), "1.999.999-probe")
        self.assertEqual(
            stderr.getvalue(), "",
            f"a configured site no longer matches live content: {stderr.getvalue()}",
        )
        self.assertEqual(total, len(build.VERSION_STAMP_SITES))


if __name__ == "__main__":
    unittest.main()
