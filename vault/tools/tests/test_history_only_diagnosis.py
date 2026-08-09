#!/usr/bin/env python3
"""When a lineage record is only in Git history, does the check say WHY?

WHAT HAPPENED (metis-g101, 2026-08-04). The fleet-boot-health check reported
that argus could not produce a successor because its predecessor was
"available only in Git history after hard deletion". Nobody had deleted
anything. Argus A145 had been activated by a Cursor cloud agent on the branch
`cursor/activate-argus-a145-c85b`, and that branch was never merged to main.

The message named a destructive act that did not occur, named no branch, and
suggested no remedy -- so a reader's next move was to go looking for what had
gone wrong with the vault, rather than to type one `git checkout`.

That is this whole arc's recurring failure in miniature: AN INSTRUMENT
REPORTING CONFIDENTLY AND WRONGLY. The old message was not even reading the
provenance it already had -- the loader stamps the source commit into
`source_path` as `.git-history/<commit>/<path>`, so the true cause was one
subprocess call away the entire time.

WHAT THESE TESTS PIN. Both branches of the diagnosis, because a fix verified on
only the case that prompted it is how a rule silently narrows:

  1. commit NOT on main  -> say it was left on a branch, and name the branch
  2. commit IS on main   -> say it was deleted from the working tree

and, in both, that we never again emit the bare phrase "after hard deletion"
for a cause we did not establish.

These tests RUN the function against a real Git repository built in a temp
directory -- they do not grep the source for the strings. Per the instrument
Mike gave this lineage: count tests that RUN the thing against tests that
INSPECT it.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import authority_chain as ac  # noqa: E402


def _git(repo: pathlib.Path, *argv: str) -> str:
    done = subprocess.run(
        ["git", *argv], cwd=str(repo), capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


class _RepoFixture:
    """A real repo with one record on main and one left on an unmerged branch."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.email", "test@example.invalid")
        _git(self.root, "config", "user.name", "test")

        (self.root / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "seed")

        # A record that lands on main and is later removed from the tree.
        (self.root / "deleted.md").write_text("on main\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "add deleted.md")
        self.on_main_commit = _git(self.root, "rev-parse", "HEAD")
        (self.root / "deleted.md").unlink()
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "remove deleted.md")

        # A record written on a branch that is never merged.
        _git(self.root, "checkout", "-q", "-b", "cursor/activate-someone-abcd")
        (self.root / "stranded.md").write_text("on a branch\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "activate someone")
        self.branch_commit = _git(self.root, "rev-parse", "HEAD")
        _git(self.root, "checkout", "-q", "main")

    def close(self) -> None:
        self._tmp.cleanup()


class TestHistoryOnlyDiagnosis(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = _RepoFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.repo.close()

    def _cause(self, commit: str, relative: str) -> str:
        """Run the real function against a record stamped like the loader does."""
        record = ac.ActivationRecord(
            uid="deadbeef",
            agent="someone",
            generation="X2",
            status="active",
            activated_by="mike",
            activated_at="2026-08-04",
            agent_public_key=None,
            name="someone-x2",
            source_path=pathlib.Path(".git-history") / commit / relative,
            history_only=True,
        )
        original = ac._repo_root_for
        ac._repo_root_for = lambda _record, _root=self.repo.root: _root
        try:
            return ac._history_only_cause(record)
        finally:
            ac._repo_root_for = original

    def test_unmerged_branch_is_named_not_called_a_deletion(self):
        """The argus A145 case. Must name the branch and never say 'deletion'."""
        cause = self._cause(self.repo.branch_commit, "vault/files/deadbeef.md")
        self.assertIn("never merged into main", cause)
        self.assertIn("cursor/activate-someone-abcd", cause)
        self.assertIn(self.repo.branch_commit[:8], cause)
        self.assertNotIn("delet", cause.lower().replace("not deleted", ""))

    def test_deletion_from_main_is_reported_as_a_deletion(self):
        """The other half. A record that really was removed must say so."""
        cause = self._cause(self.repo.on_main_commit, "deleted.md")
        self.assertIn("deletion from the working tree", cause)
        self.assertIn(self.repo.on_main_commit[:8], cause)
        self.assertNotIn("never merged", cause)

    def test_both_causes_offer_a_runnable_remedy(self):
        """A diagnosis a reader cannot act on is half an instrument."""
        for commit, rel in (
            (self.repo.branch_commit, "vault/files/deadbeef.md"),
            (self.repo.on_main_commit, "deleted.md"),
        ):
            with self.subTest(commit=commit):
                self.assertIn("git checkout", self._cause(commit, rel))

    def test_unidentifiable_provenance_says_so_instead_of_guessing(self):
        """No commit in the path => admit it. Never fall back to a guess."""
        record = ac.ActivationRecord(
            uid="deadbeef",
            agent="someone",
            generation="X2",
            status="active",
            activated_by="mike",
            activated_at="2026-08-04",
            agent_public_key=None,
            name="someone-x2",
            source_path=pathlib.Path("vault/files/deadbeef.md"),
            history_only=True,
        )
        cause = ac._history_only_cause(record)
        self.assertIn("could not be identified", cause)
        self.assertNotIn("hard deletion", cause)


if __name__ == "__main__":
    unittest.main(verbosity=2)
