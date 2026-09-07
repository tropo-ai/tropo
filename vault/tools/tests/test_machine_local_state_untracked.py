#!/usr/bin/env python3
"""S2 (f0155dd8ab09, v1.95) — machine-local state is not tracked in git, and the
publish-pending marker (studio state) is written only on a state change.

The dirty counter, the per-reader event cursors and the per-reader receipts
describe THIS machine's runs; tracking them blocked the founder's fast-forward
pulls twice on 2026-09-05 and made two clones on one machine conflict on files
that describe the machine, not the studio. Every writer creates its file if
absent (rebuild-index `if path.is_file()`, check-events `load_cursor` try/except,
receipts append), so a fresh clone needs none of them.

Mutation clauses: remove any pattern from .gitignore and the first test names
it; re-track a file and the second names it; revert the marker's write-on-change
branch and the marker tests go red.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

#: ONE declared list. package_state_exclusions.py declares the dirty counter as
#: customer state for the box; .gitignore declares it machine-local for git;
#: this list is what both must agree with. Add a machine-local writer here.
MACHINE_LOCAL = (
    ".tropo-studio/dirty-counter.json",
    "vault/events/.cursor-cdf9b3ad.json",       # one representative per pattern
    "vault/events/receipts/cdf9b3ad.jsonl",
)
#: Studio state that stays tracked on purpose: boot reads it (5.1.8).
STUDIO_STATE = (
    ".tropo/publish-pending.json",
)


def _git(*args):
    return subprocess.run(["git", "-C", str(STUDIO_ROOT), *args],
                          capture_output=True, text=True, timeout=60)


class MachineLocalStateIsUntracked(unittest.TestCase):
    def test_every_machine_local_path_is_gitignored(self):
        for rel in MACHINE_LOCAL:
            with self.subTest(path=rel):
                r = _git("check-ignore", "-q", rel)
                self.assertEqual(r.returncode, 0, "%s is not ignored by git" % rel)

    def test_no_machine_local_path_is_tracked(self):
        r = _git("ls-files", "--", ".tropo-studio/dirty-counter.json",
                 "vault/events/.cursor-*.json", "vault/events/receipts/*.jsonl")
        tracked = [l for l in r.stdout.splitlines() if l.strip()]
        self.assertEqual(tracked, [], "machine-local files still tracked: %s" % tracked)

    def test_studio_state_stays_tracked_and_not_ignored(self):
        for rel in STUDIO_STATE:
            with self.subTest(path=rel):
                self.assertEqual(_git("ls-files", "--error-unmatch", rel).returncode, 0,
                                 "%s must stay tracked" % rel)
                self.assertNotEqual(_git("check-ignore", "-q", rel).returncode, 0,
                                    "%s must not be ignored" % rel)

    def test_the_box_exclusion_list_agrees_with_gitignore_on_the_counter(self):
        from lib import package_state_exclusions as pse
        self.assertTrue(pse.is_studio_state(".tropo-studio/dirty-counter.json"))


def _load_build():
    spec = importlib.util.spec_from_file_location("build_release_s2_marker", TOOLS / "tropo-build-release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MarkerIsWrittenOnlyOnStateChange(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="s2-marker-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / ".tropo").mkdir()
        (self.tmp / "vault").mkdir()
        self.build = _load_build()

    def _write(self, version):
        with patch.object(self.build.tropo_roots, "STUDIO_ROOT", self.tmp):
            return self.build._write_publish_pending_marker(version)

    def test_same_version_still_not_staged_leaves_the_bytes_alone(self):
        path = self._write("9.9.9")
        before = path.read_bytes()
        self._write("9.9.9")
        self.assertEqual(path.read_bytes(), before)

    def test_a_new_version_rewrites_it(self):
        path = self._write("9.9.9")
        self._write("9.9.10")
        self.assertEqual(json.loads(path.read_text())["version"], "9.9.10")

    def test_a_deferred_marker_for_the_same_version_is_replaced_by_a_fresh_build(self):
        """A rebuilt candidate after a defer is a new publish state: not-staged again."""
        path = self._write("9.9.9")
        body = json.loads(path.read_text()); body["publish_state"] = "deferred-by-mike"
        path.write_text(json.dumps(body))
        self._write("9.9.9")
        self.assertEqual(json.loads(path.read_text())["publish_state"], "not-staged")


if __name__ == "__main__":
    unittest.main()
