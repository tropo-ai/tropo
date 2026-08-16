#!/usr/bin/env python3
"""Contract for the package link-integrity checker (tool d7170a1d).

Five v1.87 packages were superseded in one evening, each on one instance of
shipped text citing a file the recipient never receives, each found by one cold
walk. This tool exists to turn that class into something a build can refuse.

The cases below are mostly about what the checker must NOT report. A link
checker that flags template placeholders and not-yet-created directories
produces a number people learn to ignore, and an ignored report is worse than no
report — it looks like coverage.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "vault" / "tools" / "tropo-validate-package-links.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("package_link_checker", str(TOOL))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LinkIntegrityTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tool = load_tool()
        self.box = Path(tempfile.mkdtemp(prefix="link-box-")).resolve()
        (self.box / "vault" / "files").mkdir(parents=True)
        (self.box / "vault" / "capsules").mkdir(parents=True)
        (self.box / ".tropo" / "concierge").mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.box, ignore_errors=True)

    def write(self, rel: str, text: str) -> None:
        path = self.box / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def classes(self, findings) -> dict:
        out: dict = {}
        for f in findings:
            out.setdefault(f["class"], []).append(f)
        return out

    # ------------------------------------------------------------- detection
    def test_a_link_to_a_producing_studio_record_is_reported(self) -> None:
        self.write("START-TROPO.md", "See [the brief](vault/files/31ec9fc9.md) first.\n")
        found = self.tool.scan(self.box)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["class"], "producing-studio-record")
        self.assertTrue(found[0]["first_hour"])

    def test_a_target_that_ships_elsewhere_is_a_wrong_path_not_missing_content(self) -> None:
        """The distinction decides who fixes it: an author or the packager."""
        self.write("vault/capsules/core.capsule.md", "# core\n")
        self.write(".tropo/00-index.md", "[core](capsules/core.capsule.md)\n")
        found = self.tool.scan(self.box)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["class"], "wrong-relative-path")

    def test_a_link_to_a_producing_studio_agent_is_reported(self) -> None:
        self.write("vault/skills/x.md", "[the groomer](../../agents/sa/sa.groom/sa.groom.md)\n")
        self.assertEqual(
            self.classes(self.tool.scan(self.box)).keys(), {"producing-studio-agent"})

    # ------------------------------------------------- what must NOT be flagged
    def test_placeholders_and_recipient_directories_are_not_defects(self) -> None:
        """These are instructions and future state, not addresses.

        Reporting them is how a link report becomes noise, and a report people
        skim is indistinguishable from no report at all.
        """
        self.write("vault/templates/t.md",
                   "[charter](../agents/[agent-name]/[agent-name]-charter.md)\n"
                   "[uid](../../vault/files/<uid>.md)\n"
                   "[boards](boards/)\n")
        self.assertEqual(self.tool.scan(self.box), [])

    def test_external_and_outside_links_are_someone_elses_business(self) -> None:
        self.write("README.md",
                   "[site](https://example.invalid/x)\n"
                   "[mail](mailto:a@example.invalid)\n"
                   "[escape](../../../etc/passwd)\n")
        self.assertEqual(self.tool.scan(self.box), [])

    def test_a_resolving_link_is_silent(self) -> None:
        self.write("vault/files/aaaaaaaa.md", "# real\n")
        self.write("START-TROPO.md", "[real](vault/files/aaaaaaaa.md)\n")
        self.assertEqual(self.tool.scan(self.box), [])

    # ------------------------------------------------------------- scoping
    def test_first_hour_scope_narrows_to_what_a_newcomer_meets(self) -> None:
        self.write("START-TROPO.md", "[x](vault/files/11111111.md)\n")
        self.write("vault/files/deep.md", "[y](vault/files/22222222.md)\n")
        self.assertEqual(len(self.tool.scan(self.box)), 2)
        narrowed = self.tool.scan(self.box, first_hour_only=True)
        self.assertEqual(len(narrowed), 1)
        self.assertEqual(narrowed[0]["source"], "START-TROPO.md")

    # ------------------------------------------------------------- gate mode
    def test_strict_exits_non_zero_and_default_does_not(self) -> None:
        """--strict is the build gate; plain mode is a report you can read."""
        self.write("START-TROPO.md", "[x](vault/files/33333333.md)\n")
        for strict, expected in ((False, 0), (True, 1)):
            with self.subTest(strict=strict):
                argv = [str(self.box)] + (["--strict"] if strict else [])
                proc = subprocess.run(
                    [sys.executable, str(TOOL), *argv],
                    capture_output=True, text=True, timeout=600)
                self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)

    def test_a_clean_box_passes_strict(self) -> None:
        self.write("START-TROPO.md", "no links here\n")
        proc = subprocess.run(
            [sys.executable, str(TOOL), str(self.box), "--strict"],
            capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("every relative link resolves", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
