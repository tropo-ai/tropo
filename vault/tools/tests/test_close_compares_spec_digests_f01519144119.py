#!/usr/bin/env python3
"""f01519144119 — the close READS the digests the lock pins.

The lock writes `acceptance_criteria_sha256` and `committed_substrate_sha256`
into `<run>/declaration-snapshot.json`; until 2026-09-06 nothing compared them
at close, so a run could close against acceptance criteria rewritten after its
lock in silence (measured on T62's Spine B run by argus-a172). Now the close
recomputes both from the spec on disk, prints ONE WARN per moved component
naming both digests, and records `spec_amended_after_lock: true` with the
component names on the canonical receipt. Never refuses (deb77758).

Arms: lock -> amend a criterion -> close: WARN + receipt field, exit 0.
      lock -> close untouched: no WARN, no field, exit 0.
      the whole-file pin `dev_spec_sha256` is no longer written by the lock.
Remove the comparison in tropo-close-dev.py and the first arm goes red.

Isolation per temp_studio; each gesture runs in a fresh interpreter rooted in
the temp Studio; tearDown asserts production is byte-identical.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_close_compares_spec_digests_f01519144119
"""
from __future__ import annotations

import json
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

SPEC_UID = "10c53001"


class TheCloseReadsTheSnapshot(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="close-digests-")).resolve()
        self.studio = temp_studio.TempStudio(self.tmp / "studio").build()
        self.before = temp_studio.production_fingerprint()
        # the temp studio copies the lock and mint tools; the close is this suite's subject
        shutil.copy2(TOOLS / "tropo-close-dev.py", self.studio.tools / "tropo-close-dev.py")
        self.studio.write_entry("cd1fcd25", [
            "type: pipeline", "title: dev-pipeline", "status: active",
            "version: 2.0.0", "children:", "  - 0c6518ef", "  - fa3a49c8"])
        for uid, title in (("0c6518ef", "specify"), ("fa3a49c8", "build")):
            self.studio.write_entry(uid, ["type: pipeline", "subtype: workflow-node",
                                          f"title: {title}", "status: active"])
        self.spec = self.studio.write_entry(SPEC_UID, [
            "type: dev-spec", "title: the spec", "status: draft",
            "acceptance_criteria:",
            "  - id: AC1",
            "    behavior: the close compares the digests the lock pinned",
            "    verify:",
            "      method: automated",
            "      command: python3 -m unittest vault.tools.tests.test_close_compares_spec_digests_f01519144119",
            "committed_substrate:",
            "  - path: vault/tools/tropo-close-dev.py",
            "    change_class: AMENDED"])
        # a repo, so the close's git() reads a real HEAD and a clean tree
        subprocess.run(["git", "init", "-q"], cwd=self.studio.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=self.studio.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "seed"], cwd=self.studio.root, check=True)

    def tearDown(self) -> None:
        after = temp_studio.production_fingerprint()
        changes = temp_studio.diff_fingerprints(self.before, after)
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertEqual(changes, {}, f"the production Studio changed while an ISOLATED test ran: {changes}")

    def _run(self, body: str) -> subprocess.CompletedProcess:
        script = self.studio.root / "run_gesture.py"
        script.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(self.studio.tools)!r})\n"
            "import importlib.util\nfrom pathlib import Path\n"
            f"STUDIO = Path({str(self.studio.root)!r})\n"
            "import importlib.util as _ilu\n"
            "_mspec = _ilu.spec_from_file_location('mint_seed', STUDIO / 'vault' / 'tools' / 'tropo-mint-id.py')\n"
            "_mint = _ilu.module_from_spec(_mspec); _mspec.loader.exec_module(_mint)\n"
            "_mint.mint_studio_identity(root=STUDIO, minted_by='fixture-genesis')\n"
            + body, encoding="utf-8")
        return subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=180)

    def _lock(self) -> None:
        r = self._run(
            f"spec = importlib.util.spec_from_file_location('lockdev', {str(self.studio.tools / 'tropo-lock-dev-spec.py')!r})\n"
            "lockdev = importlib.util.module_from_spec(spec); spec.loader.exec_module(lockdev)\n"
            "assert Path(lockdev.VAULT_ROOT).resolve() == STUDIO\n"
            f"code, message = lockdev.lock_dev_spec({SPEC_UID!r}, 'talos-t63')\n"
            "print(f'EXIT={code}'); print(message)\n")
        self.assertIn("EXIT=0", r.stdout, r.stderr[-2000:])
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=self.studio.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "lock"], cwd=self.studio.root, check=True)

    def _close(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.studio.tools / "tropo-close-dev.py"),
                               "--dev-spec-uid", SPEC_UID, "--actor", "talos-t63"],
                              capture_output=True, text=True, timeout=180, cwd=self.studio.root)

    def _receipt(self) -> dict:
        folders = [d for d in self.studio.runs.iterdir() if d.is_dir()]
        self.assertEqual(len(folders), 1, folders)
        for line in (folders[0] / "run.jsonl").read_text().splitlines():
            ev = json.loads(line)
            if ev.get("event") == "dev_closed" and ev["data"].get("receipt_kind") == "canonical-dev-close":
                return ev["data"]
        self.fail("no canonical receipt")

    def _snapshot(self) -> dict:
        folder = next(d for d in self.studio.runs.iterdir() if d.is_dir())
        return json.loads((folder / "declaration-snapshot.json").read_text())

    # ------------------------------------------------------------ the pin is gone

    def test_the_lock_writes_component_digests_and_no_whole_file_pin(self) -> None:
        self._lock()
        snap = self._snapshot()
        self.assertNotIn("dev_spec_sha256", snap, "the stale-from-birth whole-file pin is back")
        self.assertRegex(snap["acceptance_criteria_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(snap["committed_substrate_sha256"], r"^[0-9a-f]{64}$")
        run_entry = next(p for p in self.studio.files.glob("*.md") if "type: pipeline-run" in p.read_text())
        text = run_entry.read_text()
        self.assertNotIn("dev_spec_sha256:", text)
        self.assertIn("acceptance_criteria_sha256:", text)

    # ------------------------------------------------------------ arm 1: amended

    def test_a_criterion_amended_after_lock_is_warned_and_recorded(self) -> None:
        self._lock()
        text = self.spec.read_text()
        self.spec.write_text(text.replace("the close compares the digests the lock pinned",
                                          "the close compares the digests the lock pinned, AND MORE"))
        r = self._close()
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertIn("[WARN] spec amended after lock: acceptance_criteria_sha256", r.stderr)
        self.assertNotIn("committed_substrate_sha256 pinned", r.stderr, "the untouched component was reported")
        receipt = self._receipt()
        self.assertIs(receipt.get("spec_amended_after_lock"), True)
        self.assertEqual(receipt.get("spec_amended_components"), ["acceptance_criteria_sha256"])
        digests = receipt["spec_digests"]["acceptance_criteria_sha256"]
        self.assertNotEqual(digests["pinned_at_lock"], digests["at_close"])

    def test_a_committed_substrate_change_is_named_as_such(self) -> None:
        self._lock()
        text = self.spec.read_text()
        self.spec.write_text(text.replace("change_class: AMENDED", "change_class: NEW"))
        r = self._close()
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertIn("committed_substrate_sha256", r.stderr)
        self.assertEqual(self._receipt().get("spec_amended_components"), ["committed_substrate_sha256"])

    # ------------------------------------------------------------ arm 2: silent

    def test_an_unamended_close_is_silent_and_carries_no_field(self) -> None:
        self._lock()
        r = self._close()
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertNotIn("spec amended after lock", r.stderr)
        receipt = self._receipt()
        self.assertNotIn("spec_amended_after_lock", receipt)
        self.assertNotIn("spec_amended_components", receipt)

    def test_a_prose_edit_that_leaves_the_criteria_alone_is_silent(self) -> None:
        """The whole reason the digests are per component: a typo fix is not an amendment."""
        self._lock()
        self.spec.write_text(self.spec.read_text() + "\nA prose paragraph added after the lock.\n")
        r = self._close()
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertNotIn("spec amended after lock", r.stderr)


if __name__ == "__main__":
    unittest.main()
