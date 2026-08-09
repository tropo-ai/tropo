#!/usr/bin/env python3
"""boot-reconcile may commit additions. It may never commit a removal.

WHAT HAPPENED (metis-g101, 2026-08-04). boot_reconcile_if_dirty exists to
rescue work from a session that died before committing: the next boot stages
whatever it finds and commits it attributed to the prior activation. For
additive drift that is exactly right, and it has saved real work.

It never asked whether the drift was an addition. A worktree sharing the branch
ref lagged HEAD, so three just-committed files looked missing, and the next
boot committed their DELETION as "orphaned drift" -- 248 lines, authored as the
principal (8e52c270). A recovery mechanism destroyed what it exists to recover,
reported success, and signed a human's name to it.

OP-13: we never destroy governed substrate; removal goes through
tropo-recycle.py. An automatic `git add -A` cannot distinguish a deliberate
deletion from a stale checkout, so it must not be the thing that decides.

THE BOUNDARY (Argus A145 ruling B, 2026-08-04, acknowledged before building):
  * inspect tracked drift against HEAD WITH rename detection, BEFORE staging
  * any deletion or rename: refuse, emit the existing failure signal, leave the
    tree untouched and dirty, mark the birth provisional -- never commit
  * add/modify/untracked-only: keep the existing crash-recovery path
  * no path-scoped staging, no ownership guessing (that is the 8976b728 cut)

Every test here RUNS the real function against a real git repository. Renames
are covered because a rename is a delete plus an add and `git add -A` will
commit half of one. The stale-worktree case reproduces the original incident
shape rather than trusting that the deletion case covers it.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import tropo_git_history as gh  # noqa: E402


def _git(repo: pathlib.Path, *argv: str) -> str:
    done = subprocess.run(
        ["git", *argv], cwd=str(repo), capture_output=True, text=True, check=True
    )
    return done.stdout


def _head(repo: pathlib.Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


class ReconcileFixture(unittest.TestCase):
    """A real repo with one commit, pointed at by the module's repo root."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self._tmp.name).resolve()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "test@example.invalid")
        _git(self.repo, "config", "user.name", "test")
        (self.repo / "kept.md").write_text("governed substrate\n", encoding="utf-8")
        (self.repo / "also-kept.md").write_text("more substrate\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "seed")
        self.seed = _head(self.repo)

        self._prev_root = gh.repo_root()
        gh.set_repo_root(self.repo)

    def tearDown(self):
        gh.set_repo_root(self._prev_root)
        self._tmp.cleanup()

    def reconcile(self):
        """Run the real entry point with a prior activation available."""
        return gh.boot_reconcile_if_dirty(
            "someagent", "S2",
            lambda: [("aaaa1111", {
                "uid": "aaaa1111", "agent": "someagent", "generation": "S1",
                "status": "retired", "activated_at": "2026-08-01",
            })],
        )


class TestAdditiveDriftStillCommits(ReconcileFixture):
    """The rescue path must keep working. A guard that blocks everything is not a fix."""

    def test_a_new_untracked_file_is_still_rescued(self):
        (self.repo / "rescued.md").write_text("left behind\n", encoding="utf-8")
        ok, detail = self.reconcile()
        self.assertTrue(ok, detail)
        self.assertTrue(gh.is_clean(self.repo), "the rescue should leave a clean tree")
        self.assertNotEqual(_head(self.repo), self.seed, "a commit should exist")

    def test_a_modification_is_still_rescued(self):
        (self.repo / "kept.md").write_text("governed substrate, edited\n", encoding="utf-8")
        ok, detail = self.reconcile()
        self.assertTrue(ok, detail)
        self.assertTrue(gh.is_clean(self.repo), detail)

    def test_a_clean_tree_is_a_noop(self):
        ok, detail = self.reconcile()
        self.assertTrue(ok)
        self.assertEqual(_head(self.repo), self.seed)


class TestRemovalsAreRefused(ReconcileFixture):
    """The regression. Each of these committed a deletion before this guard."""

    def assert_refused_and_untouched(self, detail, *, expect_dirty=True):
        self.assertEqual(
            _head(self.repo), self.seed,
            "REFUSING means no commit — HEAD must not move",
        )
        if expect_dirty:
            self.assertFalse(
                gh.is_clean(self.repo),
                "the tree must be left exactly as found, still dirty, for a human",
            )
        self.assertIn("REFUSED", detail)

    def test_a_deleted_tracked_file_refuses(self):
        (self.repo / "kept.md").unlink()
        ok, detail = self.reconcile()
        self.assertFalse(ok, "a deletion must never be auto-committed")
        self.assert_refused_and_untouched(detail)
        self.assertFalse(
            (self.repo / "kept.md").exists(),
            "refusing must not resurrect the file either — the tree is UNTOUCHED",
        )

    def test_a_staged_deletion_refuses(self):
        _git(self.repo, "rm", "-q", "kept.md")
        ok, detail = self.reconcile()
        self.assertFalse(ok)
        self.assert_refused_and_untouched(detail)

    def test_a_rename_refuses(self):
        """A rename is a delete plus an add; `git add -A` commits half of one."""
        _git(self.repo, "mv", "kept.md", "renamed.md")
        ok, detail = self.reconcile()
        self.assertFalse(ok, "a rename removes a path and must not be auto-committed")
        self.assert_refused_and_untouched(detail)

    def test_deletion_mixed_with_additions_still_refuses(self):
        """The mixed case. Partial rescue is how half a rename gets committed."""
        (self.repo / "kept.md").unlink()
        (self.repo / "brand-new.md").write_text("also here\n", encoding="utf-8")
        ok, detail = self.reconcile()
        self.assertFalse(ok)
        self.assert_refused_and_untouched(detail)

    def test_the_stale_worktree_shape_that_caused_8e52c270(self):
        """Reproduce the original incident, not a proxy for it.

        A second worktree shared the branch ref. Work was committed from the
        primary, so the branch advanced while this tree's files stayed behind —
        which git reports as deletions of paths that are, in truth, safely
        committed. That is what got committed as 'orphaned drift'.
        """
        (self.repo / "landed-elsewhere.md").write_text("just committed\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "work landed from the other worktree")
        advanced = _head(self.repo)
        # This tree lags: the file is gone from disk but present in HEAD.
        (self.repo / "landed-elsewhere.md").unlink()

        ok, detail = self.reconcile()

        self.assertFalse(ok, "this is the exact shape that destroyed 248 lines")
        self.assertEqual(_head(self.repo), advanced, "no commit may be created")
        self.assertIn("REFUSED", detail)


class TestTheRefusalIsVisible(ReconcileFixture):
    """A silent refusal is its own defect — the caller must be able to act."""

    def test_refusal_raises_the_existing_failure_signal(self):
        (self.repo / "kept.md").unlink()
        ok, _ = self.reconcile()
        self.assertFalse(ok)
        flags = list((self.repo / ".tropo" / "flags").glob("uncommitted-*.flag"))
        self.assertTrue(flags, "the existing flag-file signal must still fire")
        self.assertIn("REFUSED", flags[0].read_text(encoding="utf-8"))

    def test_the_detail_names_the_offending_paths(self):
        """A human has to know WHAT to commit or discard."""
        (self.repo / "kept.md").unlink()
        _, detail = self.reconcile()
        self.assertIn("kept.md", detail)

    def test_uninspectable_drift_is_treated_as_destructive(self):
        """If we cannot prove the drift is additive, we do not commit it."""
        offending = gh.destructive_tracked_drift(pathlib.Path("/nonexistent-repo-xyz"))
        self.assertEqual(offending, [], "a non-repo is skipped, not guessed at")


class TestTheDetectorItself(ReconcileFixture):
    def test_additive_drift_reports_nothing(self):
        (self.repo / "new.md").write_text("x\n", encoding="utf-8")
        (self.repo / "kept.md").write_text("edited\n", encoding="utf-8")
        self.assertEqual(gh.destructive_tracked_drift(self.repo), [])

    def test_deletion_is_reported(self):
        (self.repo / "kept.md").unlink()
        found = gh.destructive_tracked_drift(self.repo)
        self.assertTrue(any(line.startswith("D") for line in found), found)

    def test_rename_is_reported_as_a_rename_not_two_entries(self):
        _git(self.repo, "mv", "kept.md", "renamed.md")
        found = gh.destructive_tracked_drift(self.repo)
        self.assertTrue(
            any(line.upper().startswith("R") for line in found),
            f"rename detection must be on: {found}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
