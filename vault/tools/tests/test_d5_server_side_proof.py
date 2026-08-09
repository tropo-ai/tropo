"""D5 SERVER-SIDE enforcement proof — dev-spec 396d88a4 / test-spec 0f06a8b5.

This is the half of the D5 proof a local `file://` bare remote CANNOT prove: that
the GitHub HOST ITSELF refuses a force push / a non-fast-forward / an unchecked
direct push to the protected canonical ref, and that the REQUIRED Action blocks a
broken governed file at the PR gate. The client mechanics (CAS non-ff,
exact-sha/changed-tree refusal, validator logic, hook install/absence) are already
proven against a bare remote in test_d5_atomic_promotion_0f06a8b5.py; the assertions
here need a LIVE disposable protected repo + the least-privilege App credential.

  Test-spec 0f06a8b5 assertions covered SERVER-SIDE here:
    P2  protected-ref CAS — the HOST refuses force-push, non-ff, and unchecked
                            direct-push to main (unbypassability BY the server,
                            not merely client detection); least-privilege token
                            cannot administer.
    P6  GitHub gate       — the REQUIRED Action running the hardened validator
                            BLOCKS a broken governed file at the PR (a clean file
                            passes); the local pre-commit hook's absence is
                            detected + refused, and the server Action is the
                            unbypassable backstop.

SKIP-BY-DEFAULT — the entire suite is gated on the D5_* env contract (see
d5_proof_repo.py + README-d5-server-side-proof.md). With no credential it SKIPS
cleanly (never fails/errors), so it collects safely in every environment. Provision
the repo first:  python3 vault/tools/lib/d5_proof_repo.py provision

Run once provisioned (from vault/tools/):
    D5_PROOF_REPO=owner/repo D5_GITHUB_APP_TOKEN=... \\
        python3 -m unittest tests.test_d5_server_side_proof
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import d5_proof_repo as proof  # noqa: E402
from lib import github_transport as ght  # noqa: E402
from lib import governance_gate as gg  # noqa: E402

# The required Action is asynchronous; give it room but never hang forever.
CHECK_TIMEOUT_S = int(os.environ.get("D5_CHECK_TIMEOUT_S", "240"))
CHECK_POLL_S = 5


@unittest.skipUnless(proof.server_creds_present(), proof.SKIP_REASON)
class _LiveProofBase(unittest.TestCase):
    """Clones the live disposable protected repo with the least-privilege PUSH
    token (the credential under test — never the ambient `gh`/git auth)."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = proof.ProofConfig.from_env()
        cls.token = cls.cfg.push_token
        cls._tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls._tmp.name)
        cls.clone = cls.base / "clone"
        proof.clone(cls.cfg, cls.token, cls.clone)
        cls.protected_tip = ght.run_git(
            ["rev-parse", "HEAD"], cwd=cls.clone).stdout.strip()
        cls._branches_to_clean = []

    @classmethod
    def tearDownClass(cls):
        # best-effort delete of every PR branch this suite pushed
        if not getattr(cls, "cfg", None):
            return
        if not cls.cfg.keep:
            for br in getattr(cls, "_branches_to_clean", []):
                proof.api_request(
                    "DELETE", f"/repos/{cls.cfg.repo}/git/refs/heads/{br}",
                    token=cls.token)
        cls._tmp.cleanup()

    # -- helpers -------------------------------------------------------------
    def _commit_file(self, work: Path, rel: str, content: str, msg: str) -> str:
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        ght.run_git(["add", "-A"], cwd=work)
        ght.run_git(["commit", "-qm", msg], cwd=work)
        return ght.run_git(["rev-parse", "HEAD"], cwd=work).stdout.strip()

    def _push_branch(self, work: Path, branch: str) -> "tuple[int, str]":
        proc = ght.run_git(
            ["push", "--quiet", self.cfg.authed_url(self.token),
             f"HEAD:refs/heads/{branch}"],
            cwd=work, check=False)
        if proc.returncode == 0:
            type(self)._branches_to_clean.append(branch)
        return proc.returncode, proc.stderr

    def _open_pr(self, branch: str, title: str) -> dict:
        status, body = proof.api_request(
            "POST", f"/repos/{self.cfg.repo}/pulls", token=self.token,
            data={"title": title, "head": branch, "base": self.cfg.branch,
                  "body": "D5 server-side proof (automated)."})
        self.assertIn(status, (200, 201), f"PR create failed: {body}")
        return body

    def _wait_for_check(self, sha: str) -> "tuple[str, str]":
        """Poll the Actions workflow runs for the head SHA until the required check
        (the governance-validate Action) concludes. Returns (status, conclusion).

        Uses the Actions API (`/actions/runs`, needs Actions:read) rather than the
        Checks API (`/commits/{sha}/check-runs`, needs Checks:read): GitHub does not
        expose a grantable 'Checks' permission for fine-grained PATs in all account
        types, so the least-privilege push credential carries Actions:read instead —
        it reads the identical governance-validate workflow conclusion. (D5
        provisioning, argus-a136 2026-07-22.)"""
        deadline = time.time() + CHECK_TIMEOUT_S
        last = ("unknown", "")
        while time.time() < deadline:
            code, body = proof.api_request(
                "GET", f"/repos/{self.cfg.repo}/actions/runs?head_sha={sha}",
                token=self.token)
            runs = (body or {}).get("workflow_runs", []) if isinstance(body, dict) else []
            match = [r for r in runs if self.cfg.required_check in (r.get("name") or "")]
            if match:
                r = match[0]
                last = (r.get("status", "unknown"), r.get("conclusion") or "")
                if r.get("status") == "completed":
                    return last
            time.sleep(CHECK_POLL_S)
        return last


class TestP2ServerSideUnbypassability(_LiveProofBase):
    def test_push_token_is_least_privilege(self):
        status, body = proof.api_request(
            "GET", f"/repos/{self.cfg.repo}", token=self.token)
        self.assertEqual(status, 200, f"repo not reachable with push token: {body}")
        # NOTE: the repo `permissions` field is NOT a reliable least-privilege
        # signal for a fine-grained PAT — GitHub populates it from the token
        # OWNER's role on the repo, not from the token's granted scopes, so a
        # fine-grained PAT owned by a repo admin reports permissions.admin==True
        # even when the token itself carries no Administration grant. (D5
        # provisioning, argus 2026-07-22.) Assert the FUNCTIONAL truth instead:
        # the credential under test must be REFUSED when it attempts an
        # administration write. The probe is idempotent — it PATCHes the repo's
        # own current `has_issues` value, so it mutates nothing whether the token
        # is refused (the least-privilege pass path) or unexpectedly allowed.
        current = bool(body.get("has_issues", True)) if isinstance(body, dict) else True
        st, pb = proof.api_request(
            "PATCH", f"/repos/{self.cfg.repo}", token=self.token,
            data={"has_issues": current})
        self.assertIn(
            st, (403, 404),
            "push credential could perform an administration write "
            f"(HTTP {st}) — it has administration:write, NOT least-privilege: {pb}")

    def test_server_refuses_force_push_to_protected_ref(self):
        # Rewrite history off the protected tip and force-push it. A LOCAL bare
        # remote accepts this (the client detects it after); the protected repo
        # must have the SERVER reject the force push outright.
        work = self.base / "force"
        ght.run_git(["clone", "--quiet", self.cfg.authed_url(self.token), str(work)])
        # AMEND the tip → a rewritten commit that is a SIBLING (same parent), not
        # a descendant, of the protected tip. Pushing it is a non-ff history
        # rewrite that requires --force — robust regardless of history depth.
        (work / "files" / "d5f0f0f0.md").write_text(
            proof.CLEAN_GOVERNED_FILE.replace("d5c1ea11", "d5f0f0f0"), encoding="utf-8")
        ght.run_git(["add", "-A"], cwd=work)
        ght.run_git(["commit", "--amend", "--no-edit", "-q"], cwd=work)
        rewritten = ght.run_git(["rev-parse", "HEAD"], cwd=work).stdout.strip()
        self.assertNotEqual(rewritten, self.protected_tip)
        proc = ght.run_git(
            ["push", "--force", self.cfg.authed_url(self.token),
             f"{rewritten}:{self.cfg.canonical_ref}"], cwd=work, check=False)
        self.assertNotEqual(proc.returncode, 0,
                            "server ACCEPTED a force push to the protected ref")
        self.assertRegex(
            proc.stderr.lower(),
            r"protected|force|denied|not permitted|cannot force-update|rejected")
        # the canonical tip is unchanged (unbypassable)
        self.assertEqual(ght.GitHubTransport(self.cfg.authed_url(self.token),
                                             canonical_ref=self.cfg.canonical_ref
                                             ).remote_tip(), self.protected_tip)

    def test_server_refuses_unchecked_direct_push_to_main(self):
        # A clean ff-descendant of the tip, pushed DIRECTLY to main without a PR /
        # required-check pass. "Unbypassable onto main": the protected ref must
        # reject it because the required status check has not passed for this SHA.
        work = self.base / "direct"
        ght.run_git(["clone", "--quiet", self.cfg.authed_url(self.token), str(work)])
        self._commit_file(work, "files/d5d1d1d1.md",
                          proof.CLEAN_GOVERNED_FILE.replace("d5c1ea11", "d5d1d1d1"),
                          "direct-to-main bypass attempt")
        cand = ght.run_git(["rev-parse", "HEAD"], cwd=work).stdout.strip()
        proc = ght.run_git(
            ["push", "--quiet", self.cfg.authed_url(self.token),
             f"{cand}:{self.cfg.canonical_ref}"], cwd=work, check=False)
        self.assertNotEqual(proc.returncode, 0,
                            "server ACCEPTED an unchecked direct push to main")
        self.assertRegex(
            proc.stderr.lower(),
            r"protected|required status check|review|not permitted|rejected|expected")


class TestP6RequiredActionGate(_LiveProofBase):
    def test_required_action_blocks_broken_governed_file(self):
        work = self.base / "broken"
        ght.run_git(["clone", "--quiet", self.cfg.authed_url(self.token), str(work)])
        branch = f"d5-proof/broken-{int(time.time())}"
        ght.run_git(["checkout", "-q", "-b", branch], cwd=work)
        sha = self._commit_file(work, "files/d5b0056e.md",
                                proof.BROKEN_GOVERNED_FILE, "broken governed file")
        rc, err = self._push_branch(work, branch)
        self.assertEqual(rc, 0, f"branch push failed: {err}")
        self._open_pr(branch, "D5 proof: broken governed file must be BLOCKED")
        status, conclusion = self._wait_for_check(sha)
        self.assertEqual(status, "completed",
                         "required Action never concluded within the timeout")
        self.assertEqual(conclusion, "failure",
                         "required Action did NOT block a broken governed file")

    def test_required_action_passes_clean_governed_file(self):
        work = self.base / "clean"
        ght.run_git(["clone", "--quiet", self.cfg.authed_url(self.token), str(work)])
        branch = f"d5-proof/clean-{int(time.time())}"
        ght.run_git(["checkout", "-q", "-b", branch], cwd=work)
        sha = self._commit_file(work, "files/d5c1ea22.md",
                                proof.CLEAN_GOVERNED_FILE.replace("d5c1ea11", "d5c1ea22"),
                                "clean governed file")
        rc, err = self._push_branch(work, branch)
        self.assertEqual(rc, 0, f"branch push failed: {err}")
        self._open_pr(branch, "D5 proof: clean governed file must PASS")
        status, conclusion = self._wait_for_check(sha)
        self.assertEqual(status, "completed",
                         "required Action never concluded within the timeout")
        self.assertEqual(conclusion, "success",
                         "required Action failed a clean governed file")

    def test_pre_commit_hook_absence_detected_and_server_is_backstop(self):
        # Client half: a fresh clone with NO hook installed must be REFUSED, not
        # silently skipped (P6 "absence is detected + refused").
        work = self.base / "nohook"
        ght.run_git(["clone", "--quiet", self.cfg.authed_url(self.token), str(work)])
        with self.assertRaises(gg.GateNotInstalled):
            gg.assert_hook_installed(work)
        # Server half: with the hook absent, a broken file pushed DIRECTLY to the
        # protected main is still blocked by the server (the required Action is
        # the unbypassable backstop — the missing local hook changes nothing).
        self._commit_file(work, "files/d5b0056e.md",
                          proof.BROKEN_GOVERNED_FILE, "broken file, no local hook")
        cand = ght.run_git(["rev-parse", "HEAD"], cwd=work).stdout.strip()
        proc = ght.run_git(
            ["push", "--quiet", self.cfg.authed_url(self.token),
             f"{cand}:{self.cfg.canonical_ref}"], cwd=work, check=False)
        self.assertNotEqual(proc.returncode, 0,
                            "server let a broken file reach main with no local hook")


if __name__ == "__main__":
    unittest.main()
