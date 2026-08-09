"""lib/github_transport.py — the D5 GitHub.com transport adapter.

Dev-spec 396d88a4 (D5 Atomic Promotion, GitHub.com transport; Phase T decided
2026-07-19); cycle brief 304badf7 §5 (remote-integration profile) + D3a
(GitHub path). Test-spec 0f06a8b5 assertion P2 (protected-ref CAS).

WHAT THIS IS
  The remote-integration primitive `publish_changeset` drives: advance a
  PROTECTED canonical ref by NON-FORCE FAST-FORWARD to an EXACT candidate SHA,
  against a pinned expected tip. It is a compare-and-swap:
    - non-force        — a plain `git push` (no --force); git itself REFUSES a
                         non-fast-forward, so a loser in a two-Studio race whose
                         candidate is a sibling (not a descendant) of the winner
                         is rejected → REMOTE_CAS_FAILED (exactly one winner).
    - pinned tip       — the candidate must be a fast-forward DESCENDANT of the
                         expected tip the plan was built on; otherwise the plan
                         is stale → STALE_PLAN (re-plan on the new tip).
    - exact candidate  — after the push, the remote ref MUST equal the candidate
                         SHA exactly. A host rebase/squash/merge-changed-tree
                         produces a DIFFERENT sha → REMOTE_CHECK_FAILED. The
                         host is never allowed to rewrite the integrated tree.

  GITHUB.COM TRANSPORT (Phase T): on real github.com the protected canonical ref
  additionally carries branch-protection + a required Action (see
  .github/workflows/, D3b/P6) and is advanced by a LEAST-PRIVILEGE GitHub App /
  installation credential. This adapter is credential-agnostic — it uses the
  ambient git credential (App token via the credential helper / an injected
  askpass), so the SAME code path proves the CAS/ff/exact-sha mechanics against a
  local bare remote (`file://…`) and runs unchanged against github.com once the
  least-privilege App credential is provisioned. The SERVER-SIDE branch-rule
  unbypassability (a host squash blocked BY github, a required Action blocking a
  broken file) is a github.com-only proof — flagged as a credential/repo
  prerequisite; the client verifies exact-sha + tree here regardless.

FAIL-CLOSED: any ambiguity (rejected push, moved tip, sha/tree mismatch) raises
a TYPED error carrying the closed D5 error code — never a silent success.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, Sequence

_PATH = os.environ.get("PATH", "/usr/bin:/bin")
_HOME = os.environ.get("HOME", "/tmp")

# The closed D5 remote-integration error codes this adapter can raise
# (publish_journal.CLOSED_ERROR_ENUM members — never a free-form string).
ERR_REMOTE_CAS_FAILED = "REMOTE_CAS_FAILED"
ERR_REMOTE_CHECK_FAILED = "REMOTE_CHECK_FAILED"
ERR_STALE_PLAN = "STALE_PLAN"


class GitError(Exception):
    """A git subprocess failed unexpectedly (not a modelled refusal)."""


class RemoteIntegrationError(Exception):
    """A modelled remote-integration refusal carrying a closed D5 error code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")


def run_git(
    args: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    git_dir: Optional[Path] = None,
    check: bool = True,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Run one git command. Deterministic env (no pager, no interactive prompt),
    so a missing credential FAILS CLOSED instead of hanging on a prompt."""
    cmd = ["git"]
    if git_dir is not None:
        cmd += ["--git-dir", str(git_dir)]
    cmd += list(args)
    env = {
        "GIT_TERMINAL_PROMPT": "0",       # never block on a credential prompt
        "GIT_PAGER": "cat",
        "PAGER": "cat",
        "PATH": _PATH,
        "HOME": _HOME,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "tropo-federation",
        "GIT_AUTHOR_EMAIL": "federation@tropo.local",
        "GIT_COMMITTER_NAME": "tropo-federation",
        "GIT_COMMITTER_EMAIL": "federation@tropo.local",
    }
    proc = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, env=env,
        input=input_text, capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc


def _rev_parse(repo: Path, rev: str) -> Optional[str]:
    proc = run_git(["rev-parse", "--verify", "--quiet", rev], cwd=repo, check=False)
    out = proc.stdout.strip()
    return out or None


def _tree_of(repo: Path, commit: str) -> Optional[str]:
    return _rev_parse(repo, f"{commit}^{{tree}}")


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    proc = run_git(
        ["merge-base", "--is-ancestor", ancestor, descendant], cwd=repo, check=False
    )
    return proc.returncode == 0


class GitHubTransport:
    """Protected-ref CAS integration against a remote (github.com or a local
    bare `file://` remote for the proof). `work_repo` is the local clone that
    holds the candidate commit; `remote_url` is the canonical remote.
    """

    def __init__(self, remote_url: str, *, canonical_ref: str = "refs/heads/main"):
        self.remote_url = remote_url
        self.canonical_ref = canonical_ref

    # -- reads ---------------------------------------------------------------
    def remote_tip(self) -> Optional[str]:
        """The current SHA of the canonical ref on the remote, or None if the
        ref does not exist yet (first integration)."""
        proc = run_git(["ls-remote", self.remote_url, self.canonical_ref], check=False)
        if proc.returncode != 0:
            raise GitError(f"ls-remote {self.remote_url} failed: {proc.stderr.strip()}")
        line = proc.stdout.strip()
        return line.split("\t")[0] if line else None

    # -- the CAS integration -------------------------------------------------
    def cas_advance(
        self, work_repo: Path, *, expected_tip: Optional[str], candidate_sha: str,
    ) -> dict:
        """Advance the protected ref to `candidate_sha` by non-force fast-forward
        CAS against `expected_tip`. Returns {"integrated_sha", "expected_tip"} on
        success; raises RemoteIntegrationError with a closed code otherwise.

        Steps (all fail-closed):
          1. the candidate must be a strict ff-descendant of expected_tip (or a
             root when expected_tip is None) — else our own plan is STALE.
          2. plain (non-force) push candidate → canonical_ref. Git rejects a
             non-fast-forward, so a racing loser is refused → REMOTE_CAS_FAILED.
          3. re-read the remote tip: it MUST equal candidate exactly (no host
             rebase/squash/changed-tree) — else REMOTE_CHECK_FAILED.
        """
        # 1. candidate must build on the pinned tip (ff only).
        if expected_tip is not None:
            if _rev_parse(work_repo, candidate_sha) is None:
                raise GitError(f"candidate {candidate_sha} not present in {work_repo}")
            if not _is_ancestor(work_repo, expected_tip, candidate_sha):
                raise RemoteIntegrationError(
                    ERR_STALE_PLAN,
                    f"candidate {candidate_sha[:12]} is not a fast-forward child of "
                    f"the pinned tip {expected_tip[:12]} — the ref moved; re-plan",
                )

        # 2. plain non-force push — git's own non-ff rejection IS the CAS arbiter.
        push = run_git(
            ["push", self.remote_url, f"{candidate_sha}:{self.canonical_ref}"],
            cwd=work_repo, check=False,
        )
        if push.returncode != 0:
            stderr = push.stderr.lower()
            if any(s in stderr for s in ("non-fast-forward", "fetch first", "rejected", "stale info")):
                raise RemoteIntegrationError(
                    ERR_REMOTE_CAS_FAILED,
                    f"protected-ref CAS lost the race for {self.canonical_ref}: "
                    f"another Studio integrated first (re-plan on the new tip)",
                )
            raise GitError(f"push to {self.remote_url} failed: {push.stderr.strip()}")

        # 3. exact-candidate check — the host may not rewrite the integrated tree.
        landed = self.remote_tip()
        if landed != candidate_sha:
            raise RemoteIntegrationError(
                ERR_REMOTE_CHECK_FAILED,
                f"remote {self.canonical_ref} is {str(landed)[:12]} after push, "
                f"not the exact candidate {candidate_sha[:12]} — host rewrite "
                f"(rebase/squash/changed-tree) refused",
            )
        return {"integrated_sha": candidate_sha, "expected_tip": expected_tip}

    def verify_integrated(self, work_repo: Path, candidate_sha: str) -> dict:
        """Re-assert that the canonical ref still equals the exact candidate AND
        its tree is byte-identical (defence against a post-integration host
        rewrite). Raises REMOTE_CHECK_FAILED on any drift."""
        tip = self.remote_tip()
        if tip != candidate_sha:
            raise RemoteIntegrationError(
                ERR_REMOTE_CHECK_FAILED,
                f"canonical ref drifted from {candidate_sha[:12]} to {str(tip)[:12]} "
                f"(host rewrite) — refused",
            )
        run_git(["fetch", "--quiet", self.remote_url, self.canonical_ref], cwd=work_repo, check=False)
        remote_tree = _tree_of(work_repo, "FETCH_HEAD")
        cand_tree = _tree_of(work_repo, candidate_sha)
        if remote_tree is not None and cand_tree is not None and remote_tree != cand_tree:
            raise RemoteIntegrationError(
                ERR_REMOTE_CHECK_FAILED,
                f"integrated tree {str(remote_tree)[:12]} != candidate tree "
                f"{str(cand_tree)[:12]} — host changed the tree; refused",
            )
        return {"integrated_sha": candidate_sha, "tree": cand_tree}


def init_bare_remote(path: Path, *, default_branch: str = "main") -> str:
    """Create a bare git repo to stand in for the canonical remote in the proof
    fixture (a `file://` remote exercises the SAME non-ff CAS + custom-ref
    plumbing as github.com; the branch-rule/required-Action layer is the
    github.com-only prerequisite, flagged separately)."""
    path.mkdir(parents=True, exist_ok=True)
    run_git(["init", "--bare", "--initial-branch", default_branch, str(path)])
    return str(path)


__all__ = [
    "ERR_REMOTE_CAS_FAILED", "ERR_REMOTE_CHECK_FAILED", "ERR_STALE_PLAN",
    "GitError", "RemoteIntegrationError", "GitHubTransport",
    "run_git", "init_bare_remote",
]
