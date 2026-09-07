#!/usr/bin/env python3
"""f01592dca86d AC5 — the validator warns on a locked dev-spec its release plan does not list.

The spec lock appends its uid to the live plan's `dev_spec_uids` (AC1). This
check is the SECOND reader: a plan edited by hand afterwards, or a spec locked
before the append existed, shows up as one WARN line. Warn-safe by contract
(deb77758) — it never counts toward the fail tally.

Plant the mismatch, assert the line. The remove-the-check control is by
construction: `check_dev_spec_plan_membership_drift` is looked up by name, so
deleting it makes every test here error.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_dev_spec_plan_membership_drift
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("tropo_validate_pmd", TOOLS / "tropo-validate.py")
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)


def _entry(uid: str, lines: list) -> str:
    return "---\nuid: '%s'\n%s\n---\n\n# %s\n" % (uid, "\n".join(lines), uid)


class PlanMembershipDrift(unittest.TestCase):

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="plan-drift-")).resolve()
        self.files = self.root / "vault" / "files"
        self.files.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def _write(self, uid: str, lines: list) -> None:
        (self.files / f"{uid}.md").write_text(_entry(uid, lines), encoding="utf-8")

    def _spec(self, uid: str = "5ec00001", status: str = "locked", target: str = "9.9.9") -> None:
        self._write(uid, ["type: dev-spec", "title: spec", f"status: {status}",
                          f"target_release: '{target}'"])

    def _plan(self, uid: str = "b1a00001", status: str = "specify", members=(), version: str = "9.9.9") -> None:
        body = ["type: release-plan", "title: plan", f"status: {status}",
                f"release_version: '{version}'"]
        if members is None:
            body.append("dev_spec_uids: []   # fills at spec-lock")
        else:
            body.append("dev_spec_uids:")
            body.extend(f"  - {m}" for m in members)
        self._write(uid, body)

    def _run(self):
        return validate.check_dev_spec_plan_membership_drift(self.root)

    # ------------------------------------------------------------ the plant

    def test_a_locked_spec_its_live_plan_does_not_list_is_one_warn_line(self) -> None:
        self._spec()
        self._plan(members=None)
        findings, checked, warns = self._run()
        self.assertEqual(checked, 1)
        self.assertEqual(warns, 1, findings)
        self.assertEqual(len(findings), 1)
        line = findings[0]
        self.assertTrue(line.startswith("[WARN]"), "drift must be WARN, never FAIL")
        self.assertIn("5ec00001", line)
        self.assertIn("b1a00001", line)
        self.assertIn("does not list it", line)

    def test_a_done_spec_dropped_by_a_hand_edit_is_also_caught(self) -> None:
        """The v1.94 case: specs went locked -> done while the list stayed empty."""
        self._spec(status="done")
        self._plan(members=["deadbeef"])
        findings, checked, warns = self._run()
        self.assertEqual((checked, warns), (1, 1), findings)

    # ------------------------------------------------------------ the silences

    def test_a_listed_member_is_silent(self) -> None:
        self._spec()
        self._plan(members=["5ec00001"])
        findings, checked, warns = self._run()
        self.assertEqual((checked, warns), (1, 0), findings)
        self.assertEqual(findings, [])

    def test_a_listed_member_with_a_trailing_comment_is_silent(self) -> None:
        self._spec()
        self._write("b1a00001", ["type: release-plan", "title: plan", "status: specify",
                                 "release_version: '9.9.9'", "dev_spec_uids:",
                                 "  - 5ec00001   # Spine A"])
        findings, checked, warns = self._run()
        self.assertEqual(warns, 0, findings)

    def test_a_spec_with_no_live_plan_is_silent(self) -> None:
        """Locked outside a release cycle, or the plan already shipped: nothing to drift from."""
        self._spec()
        self._plan(status="done", members=[])
        findings, checked, warns = self._run()
        self.assertEqual((checked, warns), (1, 0), findings)

    def test_a_spec_without_a_target_release_is_not_checked(self) -> None:
        self._write("5ec00001", ["type: dev-spec", "title: spec", "status: locked"])
        self._plan(members=None)
        findings, checked, warns = self._run()
        self.assertEqual((checked, warns), (0, 0), findings)

    def test_a_draft_spec_is_not_checked(self) -> None:
        self._spec(status="draft")
        self._plan(members=None)
        findings, checked, warns = self._run()
        self.assertEqual((checked, warns), (0, 0), findings)

    # ------------------------------------------------------------ ambiguity emits

    def test_two_live_plans_for_one_version_warn_rather_than_guess(self) -> None:
        self._spec()
        self._plan(uid="b1a00001", members=["5ec00001"])
        self._plan(uid="b1a00002", members=["5ec00001"])
        findings, checked, warns = self._run()
        self.assertEqual(warns, 1, findings)
        self.assertIn("refusing to guess", findings[0])

    # ------------------------------------------------------------ the register

    def test_the_check_is_registered_in_the_validator_main(self) -> None:
        """A check nothing calls reports green forever."""
        source = (TOOLS / "tropo-validate.py").read_text(encoding="utf-8")
        body = source.split("def main(")[1] if "def main(" in source else source
        self.assertIn("check_dev_spec_plan_membership_drift(vault)", body,
                      "the drift check is defined but never called from main")


if __name__ == "__main__":
    unittest.main()
