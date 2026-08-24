#!/usr/bin/env python3
"""v1.91 S3 AC1 + AC5 (176a8995) — the preflight subcommand exists; site_endpoint.

AC1's verify command is `python3 vault/tools/tropo-publish-release.py preflight
--version <v>`. Today tropo-publish-release.py's argparse knows stage, fire,
defer, handback, receive and verify-only — `preflight` is an "invalid choice"
(exit 2). That is the red. The per-precondition behaviour (transport, badge
target, marker, entry uid) lives in the sibling *_v191.py suites; this file
pins the entrypoint AC1 names and the shape of its refusals.

The tool is run as a COPY inside a Studio-shaped temp tree (temp_studio.py):
tropo-publish-release.py resolves its roots from its own location, so running
the real file would read the operator's real releases root and could let a
refusal recorder write into the real studio.

AC5 is network-bound (tropo-ai.com) and is documented as a skip with reason —
see SiteEndpointAC5.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import temp_studio  # noqa: E402

TOOL = "tropo-publish-release.py"


def _run(studio: temp_studio.TempStudio, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(studio.tools / TOOL), *args],
        cwd=str(studio.root), capture_output=True, text=True, timeout=120,
        stdin=subprocess.DEVNULL)


class PreflightSubcommandTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="s3-preflight-cli-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.studio = temp_studio.TempStudio(tmp / "studios" / "argo-os").build()
        shutil.copy2(temp_studio.REAL_TOOLS / TOOL, self.studio.tools / TOOL)

    def test_preflight_help_exits_zero(self) -> None:
        proc = _run(self.studio, "preflight", "--help")
        self.assertEqual(
            proc.returncode, 0,
            "publish-release has no preflight subcommand (S3 AC1: `preflight "
            f"--version <v>` must exist and run BEFORE the TTY confirm):\n"
            f"{(proc.stdout + proc.stderr).strip()[-400:]}")
        self.assertIn("--version", proc.stdout,
                      "preflight must take --version, the identity AC1's command passes")

    def test_preflight_on_an_unstaged_version_is_a_preflight_refusal(self) -> None:
        """A missing stage is a precondition like any other: the preflight names
        it (not-staged / no publish-state) and exits nonzero — it is not an
        argparse error, and it asks nothing (stdin is /dev/null)."""
        proc = _run(self.studio, "preflight", "--version", "9.9.9")
        out = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0, "an unstaged version preflighted green")
        self.assertNotIn("invalid choice", out,
                         f"`preflight` is not a subcommand yet:\n{out.strip()[-300:]}")
        self.assertRegex(out, r"(?i)not staged|publish-state|stage first",
                         f"refusal does not name the missing stage:\n{out.strip()[-300:]}")
        self.assertNotIn("[y/N]", out, "preflight prompted a human")


class SiteEndpointAC5(unittest.TestCase):
    @unittest.skip(
        "S3 AC5 needs the world: tropo-verify-release-live.py must OBSERVE "
        "site_endpoint — download and hash the public badge asset — or the "
        "observation must be retired out loud. Today lib/release_completion.py "
        "REQUIRED_FACTS binds publication_receipt, bus_published_event, "
        "run_published_event, closed_records, scorecard and nothing about the "
        "site; the only site_endpoint observation is the fire's "
        "_adapter_site_endpoint in tropo-publish-release.py, which tolerates "
        "absence; and https://tropo-ai.com/os-release.json and /api/os-release "
        "both 404 (62deeec1). Verify by hand once the endpoint ships: "
        "python3 vault/tools/tropo-verify-release-live.py --release-plan-uid <uid> "
        "must report a SEEN site_endpoint fact with its sha256, or the spec must "
        "record the retirement. No offline fixture can stand in for a public URL.")
    def test_site_endpoint_is_observed_or_retired(self) -> None:
        raise AssertionError("unreachable — skipped with reason above")


if __name__ == "__main__":
    unittest.main()
