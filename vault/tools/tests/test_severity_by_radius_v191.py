#!/usr/bin/env python3
"""S1 AC6 (dev-spec 0a0e94d1, metis-g111 assignment 2026-08-23).

Severity by BLAST RADIUS, not record age. G111's written review
(evidence/ac6-severity-review-2026-08-23.md) names the rule; this test reds
today because the code still assigns severity by grandfather/age rules.

The radius question: is this record the plan/release UNDER BUILD, or in the
image being built? Age decides nothing. A cancelled plan's missing hub edge
cannot ship — INFO. The plan under build with the same gap WILL ship — ERROR.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

spec = importlib.util.spec_from_file_location(
    "vcm_ac6", TOOLS / "tropo-validate-capability-membership.py")
vcm = importlib.util.module_from_spec(spec)
sys.modules["vcm_ac6"] = vcm
spec.loader.exec_module(vcm)

CAP = "aaaa1111"  # capability with no hub edge in the map
NO_HUB_MAP = {}   # empty member_of map: every capability is non-hub


def _plan(uid: str, status: str) -> tuple[str, dict]:
    return uid, {
        "capsule_version": "1.3",
        "status": status,
        "capabilities_touched": [CAP],
        "target_release": "9.9.9",   # post every grandfather threshold
        "subsystems_touched": [],
        "hub_summaries": {},
    }


class SeverityByRadiusTests(unittest.TestCase):
    """Red today: C20 fires ERROR (or WARNING) regardless of plan status."""

    def test_c20_plan_under_build_is_error(self) -> None:
        for status in ("active", "build", "specify"):
            findings = vcm.validate_release_plan(
                *_plan("bbbb0001", status), NO_HUB_MAP, strict=True)
            c20 = [f for f in findings if f.check == "C20-non-hub-capabilities"]
            self.assertEqual(
                len(c20), 1, f"C20 must fire once for status={status}")
            self.assertEqual(
                c20[0].severity, "ERROR",
                f"plan under build (status={status}) with a missing hub edge "
                f"WILL ship — ERROR by blast radius")

    def test_c20_cancelled_or_done_plan_is_info(self) -> None:
        for status in ("cancelled", "done", "closed"):
            findings = vcm.validate_release_plan(
                *_plan("bbbb0002", status), NO_HUB_MAP, strict=True)
            c20 = [f for f in findings if f.check == "C20-non-hub-capabilities"]
            self.assertEqual(
                len(c20), 1, f"C20 still reports the gap for status={status}")
            self.assertEqual(
                c20[0].severity, "INFO",
                f"a {status} plan's missing hub edge cannot ship — INFO by "
                f"blast radius (age/radius reds today)")

    def test_no_version_grandfather_escape(self) -> None:
        """Age decides nothing: an OLD-version plan under build still ERRORs."""
        uid, fm = _plan("bbbb0003", "active")
        fm["target_release"] = "1.0.0"  # ancient — under every threshold
        fm["title"] = "Tropo-OS v1.0.0 — ancient"
        findings = vcm.validate_release_plan(uid, fm, NO_HUB_MAP, strict=True)
        c20 = [f for f in findings if f.check == "C20-non-hub-capabilities"]
        self.assertEqual(
            len(c20), 1,
            "the plan under build is checked even at an ancient version — "
            "the version-grandfather escape must not silence the radius")
        if c20:
            self.assertEqual(c20[0].severity, "ERROR")


if __name__ == "__main__":
    unittest.main()
