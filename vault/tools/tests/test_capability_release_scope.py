"""Regression tests for release-family scoping in the capability gate."""

import importlib.util
import unittest
from pathlib import Path


TOOL_PATH = Path(__file__).resolve().parents[1] / "tropo-validate-capability-membership.py"
SPEC = importlib.util.spec_from_file_location("capability_validator", TOOL_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VALIDATOR)


def _codes(frontmatter):
    findings = VALIDATOR.validate_release_entry(
        "deadbeef", frontmatter, {}, {}, strict=True
    )
    return [(finding.severity, finding.check) for finding in findings]


class ReleaseScopeTests(unittest.TestCase):
    def test_non_os_release_family_skips_os_subsystem_rules(self):
        self.assertEqual(_codes({
            "type": "release",
            "status": "shipped",
            "release_version": "kb-marketing-v14.1",
        }), [("INFO", "NON-OS-release-family")])

    def test_superseded_archived_release_skips_canonical_ship_rules(self):
        self.assertEqual(_codes({
            "type": "release",
            "status": "shipped",
            "state": "archived",
            "superseded_by": "feedface",
            "release_version": "1.49.0",
        }), [("INFO", "SUPERSEDED-release-record")])

    def test_canonical_semver_release_remains_hard_gated(self):
        codes = _codes({
            "type": "release",
            "status": "shipped",
            "state": "active",
            "release_version": "1.72.0",
        })
        self.assertIn(("ERROR", "R11-missing-registry-rows"), codes)
        self.assertIn(("ERROR", "R12-brief-based-release-missing-fields"), codes)

    def test_governed_python_tools_participate_in_subsystem_derivation(self):
        member_map = VALIDATOR.load_member_of_map()
        for uid in ("d2b9c8e6", "f5e2d1c7", "a1b8c2d4"):
            self.assertIn("8dd772a0", member_map[uid])

    def test_shipped_skills_and_tools_use_canonical_subsystem_hub_edges(self):
        member_map = VALIDATOR.load_member_of_map()
        for uid in ("e392a8e6", "cdadf603"):
            self.assertIn("99ed55fd", member_map[uid])


if __name__ == "__main__":
    unittest.main()
