#!/usr/bin/env python3
"""v1.91 S3 AC3 (176a8995) — the CHANGELOG promotion is a BUILD-time gate.

Today the only `## [version]` check on the release path is
tropo-publish-release.py cmd_stage -> _changelog_equality_assert, which runs
AFTER the build has frozen the package, so promoting [Unreleased] late forces a
rebuild that voids every instrument receipt. v1.90 lost a full rebuild cycle to
this ordering and the box shipped a CHANGELOG with no 1.90.0 section (Argus
F-06; 62deeec1). tropo-build-release.py only COPIES CHANGELOG.md into the box
(Phase 3, "ship gate will block until it exists") and never reads its sections.

CONTRACT THIS TEST DRIVES (red at birth, 2026-08-23):
  A build whose studio CHANGELOG.md has no `## [<target>]` section REFUSES AT
  BUILD, naming CHANGELOG and the version, BEFORE Step 0 (the vault rebuild —
  measured at 4-25 minutes). It is a static file check: S3's principle is that
  everything that can refuse refuses before the cost, and a gate that waits for
  the rebuild is a gate that still burns the cycle. --dry-run rehearses the
  same refusal (a rehearsal that hides a refusal is not a rehearsal).

HOW IT RUNS: the build tool is copied into a Studio-shaped temp tree
(temp_studio.py) so its roots resolve there, and is invoked with
`--target 9.9.9 --dry-run`. In that tree Step 0 fails fast on a missing
rebuild-vault.py, which is the marker this test uses for "the build got past
where the gate belongs": today the output reaches Step 0 and never says
CHANGELOG. With the section present the build must NOT refuse on CHANGELOG
(the positive arm). Mutation clause: move the check back to stage -> RED.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import temp_studio  # noqa: E402

TOOL = "tropo-build-release.py"
TARGET = "9.9.9"
UNPROMOTED = ("# Changelog\n\n## [Unreleased]\n\n- the v9.9.9 work, never promoted\n\n"
              "## [9.9.8] - 2026-08-01\n\n- prior release\n")
PROMOTED = ("# Changelog\n\n## [Unreleased]\n\n## [9.9.9] - 2026-08-23\n\n- the v9.9.9 "
            "work\n\n## [9.9.8] - 2026-08-01\n\n- prior release\n")
STEP0 = "Step 0 — Vault rebuild"
_CHANGELOG_REFUSAL = re.compile(r"CHANGELOG", re.I)


class ChangelogAtBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="s3-changelog-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.studio = temp_studio.TempStudio(tmp / "studios" / "argo-os").build()
        shutil.copy2(temp_studio.REAL_TOOLS / TOOL, self.studio.tools / TOOL)
        (self.studio.root / ".tropo" / "version.md").write_text("9.9.8\n")

    def _build(self, changelog: str) -> str:
        (self.studio.root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(self.studio.tools / TOOL), "--target", TARGET, "--dry-run"],
            cwd=str(self.studio.root), capture_output=True, text=True, timeout=300,
            stdin=subprocess.DEVNULL)
        self.rc = proc.returncode
        return proc.stdout + proc.stderr

    def test_a_build_with_no_version_section_refuses_at_build(self) -> None:
        out = self._build(UNPROMOTED)
        self.assertNotEqual(self.rc, 0, f"build proceeded with no [{TARGET}] section:\n{out}")
        self.assertTrue(
            _CHANGELOG_REFUSAL.search(out) and TARGET in out,
            f"build refused, but not on CHANGELOG [{TARGET}] — the [version] gate "
            f"lives only at stage (tropo-publish-release.py _changelog_equality_assert), "
            f"after the freeze. Output:\n{out.strip()[-600:]}")
        self.assertNotIn(
            STEP0, out,
            f"the CHANGELOG refusal arrived after Step 0 (vault rebuild) began — a "
            f"static file check must refuse before the cycle is spent:\n{out[-600:]}")

    def test_a_promoted_changelog_is_not_refused(self) -> None:
        out = self._build(PROMOTED)
        before_step0 = out.split(STEP0)[0] if STEP0 in out else out
        self.assertFalse(
            _CHANGELOG_REFUSAL.search(before_step0) and "REFUS" in before_step0.upper(),
            f"a CHANGELOG with a [{TARGET}] section was refused:\n{out[-600:]}")
        self.assertIn(STEP0, out,
                      f"build never reached Step 0 with a promoted CHANGELOG — the gate "
                      f"refused something else first:\n{out[-600:]}")


if __name__ == "__main__":
    unittest.main()
