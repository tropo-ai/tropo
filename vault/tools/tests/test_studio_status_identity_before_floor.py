"""v1.95 Spine A AC2b: on a fresh box (no studio-ops substrate, no identity
manifest) tropo-studio-status.py prints the studio-identity WARN BEFORE its
F7 fatal floor, and on a box with NO identity the floor yields (return 0). Found by argus-a172 running the arrival-walk harness on a
HEAD candidate, 2026-09-06: the floor fired first, the WARN never printed.
Remove the pre-floor identity call and the first test goes red."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


class IdentityWarnPrecedesTheFloor(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="status-fresh-box-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "vault" / "tools").mkdir(parents=True)
        for name in ("tropo-studio-status.py", "tropo-mint-id.py"):
            shutil.copy(TOOLS / name, self.root / "vault" / "tools" / name)
        # the manifest reader imports vault/tools/lib, as it does in a real box
        shutil.copytree(TOOLS / "lib", self.root / "vault" / "tools" / "lib",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (self.root / ".tropo").mkdir()

    def _run(self):
        return subprocess.run([sys.executable, str(self.root / "vault" / "tools" / "tropo-studio-status.py"),
                               "--as", "po", "--no-emit"], capture_output=True, text=True,
                              cwd=str(self.root), timeout=120)

    def test_fresh_box_prints_the_identity_warn_and_completes(self):
        """v1.95 AC5 cold walk (Vela V78 on the sealed candidate #2, 2026-09-06): the
        identity WARN printed and the floor still returned 1, so Po's Step 0d never
        completed on any fresh box. No substrate folder is the not-initialised state:
        WARN twice, return 0."""
        r = self._run()
        out = r.stdout + r.stderr
        self.assertIn("[WARN] studio identity", out, out[-800:])
        self.assertIn("[WARN] studio-ops substrate not initialised", out, out[-800:])
        self.assertNotIn("FATAL", out, out[-800:])
        self.assertEqual(r.returncode, 0, out[-800:])

    def test_after_genesis_the_box_still_has_no_substrate_and_still_completes(self):
        """Step 0d runs AFTER Step 0b genesis, so the manifest exists and the substrate
        still does not (nothing at genesis creates it). Vela measured the crash
        'regardless of identity state'; this is that state."""
        self._write_manifest()
        r = self._run()
        out = r.stdout + r.stderr
        self.assertNotIn("[WARN] studio identity", out, out[-800:])
        self.assertIn("[WARN] studio-ops substrate not initialised", out, out[-800:])
        self.assertEqual(r.returncode, 0, out[-800:])

    def test_an_initialised_substrate_that_was_emptied_still_hits_the_floor(self):
        """Negative control: the FATAL floor is for a substrate that EXISTS and was
        emptied or truncated -- silence is never all-clear there."""
        self._write_manifest()
        ops = self.root / "vault" / "studio-ops"
        ops.mkdir(parents=True)
        (ops / "roster.json").write_text('{"items": []}')
        (ops / "log.jsonl").write_text("")
        r = self._run()
        out = r.stdout + r.stderr
        self.assertIn("FATAL", out, out[-800:])
        self.assertEqual(r.returncode, 1)

    def _write_manifest(self):
        (self.root / ".tropo" / "studio-identity.md").write_text(
            "---\nstudio_id: f015aaaabbbb\nmint_prefix: f015\ncreated: '2026-09-06'\n"
            "minted_by: test\nhq_registered: false\nschema_version: 1\nentity_name: fixture\n---\n\n# Studio Identity\n")


if __name__ == "__main__":
    unittest.main()
