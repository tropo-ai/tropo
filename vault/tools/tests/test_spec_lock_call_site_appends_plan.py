#!/usr/bin/env python3
"""f01592dca86d AC1, the CALL SITE — the lock gesture itself appends to the plan.

AC1 was accepted on `append_uid_to_plan_list` and a world probe while nothing
in `lock_dev_spec` called it (A172's own correction, 2026-09-06). This suite
runs the real gesture in an isolated temp Studio and reads the plan back, in
the three arms A172 ruled:

  one live plan   -> appended, exactly one key, the plan still parses, the
                     lock's own message names the plan;
  no live plan    -> ONE WARN quoting the resolver's reason, exit 0, plan
                     files untouched;
  two live plans  -> the WARN names both, exit 0, neither plan touched;
  a locked plan   -> the WARN, not a write.

Remove the call from lock_dev_spec and the first arm goes red; the other arms
cannot tell (they assert nothing was written), which is why the first arm is
the load-bearing one. Mutation-proven by hand at landing: see the task record.

Isolation per temp_studio: a fresh interpreter rooted in a temp Studio with its
own copy of the tools; tearDown asserts production is byte-identical.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_spec_lock_call_site_appends_plan
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import temp_studio  # noqa: E402

SPEC_UID = "10c52001"
PLAN_UID = "b1a52001"
RIVAL_UID = "b1a52002"
VERSION = "9.9.9"


class TheLockAppendsToItsPlan(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="lock-appends-plan-")).resolve()
        self.studio = temp_studio.TempStudio(self.tmp / "studio").build()
        self.before = temp_studio.production_fingerprint()
        self.studio.write_entry("cd1fcd25", [
            "type: pipeline", "title: dev-pipeline", "status: active",
            "version: 2.0.0", "children:", "  - 0c6518ef", "  - fa3a49c8"])
        for uid, title in (("0c6518ef", "specify"), ("fa3a49c8", "build")):
            self.studio.write_entry(uid, ["type: pipeline", "subtype: workflow-node",
                                          f"title: {title}", "status: active"])
        self.studio.write_entry(SPEC_UID, [
            "type: dev-spec", "title: the spec", "status: draft",
            f"target_release: '{VERSION}'",
            "acceptance_criteria:",
            "  - id: AC1",
            "    behavior: the lock appends its uid to the plan",
            "    verify:",
            "      method: automated",
            "      command: python3 -m unittest vault.tools.tests.test_spec_lock_call_site_appends_plan"])

    def tearDown(self) -> None:
        after = temp_studio.production_fingerprint()
        changes = temp_studio.diff_fingerprints(self.before, after)
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertEqual(changes, {},
                         f"the production Studio changed while an ISOLATED test ran: {changes}")

    def _plan(self, uid: str = PLAN_UID, status: str = "specify",
              members_line: str = "dev_spec_uids: []   # fills at spec-lock, per stream") -> Path:
        return self.studio.write_entry(uid, [
            "type: release-plan", f"title: plan {uid}", f"status: {status}",
            f"release_version: '{VERSION}'", members_line])

    def _lock(self) -> subprocess.CompletedProcess:
        script = self.studio.root / "run_gesture.py"
        script.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(self.studio.tools)!r})\n"
            "import importlib.util\n"
            "from pathlib import Path\n"
            f"spec = importlib.util.spec_from_file_location('lockdev', {str(self.studio.tools / 'tropo-lock-dev-spec.py')!r})\n"
            "lockdev = importlib.util.module_from_spec(spec); spec.loader.exec_module(lockdev)\n"
            f"STUDIO = Path({str(self.studio.root)!r})\n"
            "assert Path(lockdev.VAULT_ROOT).resolve() == STUDIO\n"
            "import importlib.util as _ilu\n"
            "_mspec = _ilu.spec_from_file_location('mint_seed', STUDIO / 'vault' / 'tools' / 'tropo-mint-id.py')\n"
            "_mint = _ilu.module_from_spec(_mspec); _mspec.loader.exec_module(_mint)\n"
            "_mint.mint_studio_identity(root=STUDIO, minted_by='fixture-genesis')\n"
            f"code, message = lockdev.lock_dev_spec({SPEC_UID!r}, 'talos-t63')\n"
            "print(f'EXIT={code}')\n"
            "print(message)\n",
            encoding="utf-8")
        return subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120)

    @staticmethod
    def _members(text: str) -> list:
        head = text.split("\n---\n", 1)[0]
        return [l.strip().lstrip("- ").split()[0]
                for l in head.splitlines() if l.strip().startswith("- ")]

    # ---------------------------------------------------------- arm 1: appended

    def test_one_live_plan_is_appended_in_the_same_gesture(self) -> None:
        plan = self._plan()
        before = plan.read_text()
        result = self._lock()
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("EXIT=0", result.stdout, result.stderr[-2000:])
        self.assertIn(f"plan={PLAN_UID}", result.stdout,
                      "the lock's own message does not name the plan it appended to")
        self.assertNotIn("[WARN] release-plan", result.stderr)

        text = plan.read_text()
        self.assertNotEqual(text, before, "the plan was not written — the call site is missing")
        head = text.split("\n---\n", 1)[0]
        self.assertEqual(head.count("dev_spec_uids:"), 1, "a second key was written")
        self.assertEqual(self._members(text), [SPEC_UID])
        self.assertIn("fills at spec-lock", head, "the owner's note was dropped")
        # the spec locked too — same gesture, not a plan write on its own
        self.assertIn("status: locked", (self.studio.files / f"{SPEC_UID}.md").read_text())
        # and YAML reads the member (the AC4 defect: an entry outside the frontmatter)
        lockdev = self.studio.load("tropo-lock-dev-spec.py", "lockdev_for_parse")
        self.assertEqual(lockdev.parse_frontmatter(text).get("dev_spec_uids"), [SPEC_UID])

    def test_a_re_lock_attempt_does_not_double_the_member(self) -> None:
        """A second gesture refuses (already locked) and the plan is unchanged."""
        plan = self._plan()
        self.assertIn("EXIT=0", self._lock().stdout)
        once = plan.read_text()
        result = self._lock()
        self.assertIn("EXIT=1", result.stdout)
        self.assertEqual(plan.read_text(), once)

    # ---------------------------------------------------------- arm 2: no plan

    def test_no_live_plan_warns_once_and_the_lock_proceeds(self) -> None:
        shipped = self._plan(status="done", members_line="dev_spec_uids: []")
        before = shipped.read_text()
        result = self._lock()
        self.assertIn("EXIT=0", result.stdout, result.stderr[-2000:])
        self.assertEqual(result.stderr.count("[WARN] release-plan append skipped"), 1, result.stderr)
        self.assertIn("no live release-plan declares release_version", result.stderr)
        self.assertIn("plan=none", result.stdout)
        self.assertEqual(shipped.read_text(), before, "a terminal plan was written")
        self.assertIn("status: locked", (self.studio.files / f"{SPEC_UID}.md").read_text())

    # ---------------------------------------------------------- arm 3: two plans

    def test_two_live_plans_warn_naming_both_and_touch_neither(self) -> None:
        a = self._plan(PLAN_UID)
        b = self._plan(RIVAL_UID)
        before = (a.read_text(), b.read_text())
        result = self._lock()
        self.assertIn("EXIT=0", result.stdout, result.stderr[-2000:])
        self.assertEqual(result.stderr.count("[WARN] release-plan append skipped"), 1, result.stderr)
        self.assertIn("refusing to guess", result.stderr)
        self.assertIn(f"{PLAN_UID}.md", result.stderr)
        self.assertIn(f"{RIVAL_UID}.md", result.stderr)
        self.assertEqual((a.read_text(), b.read_text()), before)

    # ---------------------------------------------------------- condition 3: sealed plan

    def test_a_locked_plan_gets_the_warn_not_a_write(self) -> None:
        sealed = self._plan(status="locked", members_line="dev_spec_uids:\n  - deadbeef")
        before = sealed.read_text()
        result = self._lock()
        self.assertIn("EXIT=0", result.stdout, result.stderr[-2000:])
        self.assertIn("not a pre-lock state", result.stderr)
        self.assertEqual(sealed.read_text(), before, "a locked plan's member list was written")


if __name__ == "__main__":
    unittest.main()
