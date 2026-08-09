"""lib/d5_proof_repo.py — the D5 disposable-protected-repo proof harness helper.

Dev-spec 396d88a4 (D5 Atomic Promotion, GitHub.com transport) acceptance:
    "The GitHub enforcement gate is proven against a DISPOSABLE PROTECTED GitHub
     repository (not only a local bare remote): the named least-privilege App
     credential + exact-SHA required check + branch rules + non-force CAS; a
     broken governed file is blocked at the required Action; the local pre-commit
     hook catches it best-effort and its absence is detected + refused."
Test-spec 0f06a8b5 assertions P2 (protected-ref CAS) + P6 (GitHub gate).

WHAT THIS IS
  The provisioning + teardown + credential plumbing for the SERVER-SIDE half of
  the D5 proof — the part a local `file://` bare remote can NOT prove: that the
  GitHub host itself REFUSES a force push / a non-fast-forward / an unchecked
  direct push to the protected canonical ref, and that the REQUIRED Action blocks
  a broken governed file at the PR gate. The client mechanics (CAS non-ff,
  exact-sha/changed-tree refusal, validator logic, hook install/absence) are
  already proven against a bare remote in test_d5_atomic_promotion_0f06a8b5.py;
  this module wires the live-repo prerequisites so the paired server-side tests
  (test_d5_server_side_proof.py) run the moment a credential is provisioned.

HONESTY BOUNDARY — the ambient `gh` / git credential in this environment is the
  AGENT's (read-only) auth, NOT the least-privilege D5 App credential. Every
  WRITE this harness performs (git push, branch-protection PUT, PR create) uses
  an EXPLICIT `D5_*` token passed here — never the ambient auth — so the proof
  exercises the App credential the spec names, not whatever the box happens to be
  logged in as. `gh` may be used read-only for manual inspection.

ENV CONTRACT (Cloud secrets Mike provisions; see README-d5-server-side-proof.md)
  Required to RUN the server-side proof at all:
    D5_PROOF_REPO            owner/repo of the disposable protected repo,
                             e.g. "tropo-ai/tropo-d5-proof".
    D5_GITHUB_APP_TOKEN      the least-privilege installation access token
                             (contents:write on the proof repo ONLY) — the
                             principal permitted to advance the protected ref.
                             This is the credential UNDER TEST.
      ── OR, to mint that token at runtime from a durable App identity ──
    D5_GITHUB_APP_ID              the GitHub App id (numeric).
    D5_GITHUB_APP_INSTALLATION_ID the installation id on the proof repo's owner.
    D5_GITHUB_APP_PRIVATE_KEY     the App private key PEM (raw PEM, or "@/path"
                             to a PEM file). RS256-signed via the `openssl` CLI
                             (no python crypto dependency).
  Required only for PROVISION / TEARDOWN (kept SEPARATE from the push token so
  the proof can show the App can push but cannot administer):
    D5_GITHUB_ADMIN_TOKEN    a token with administration:write AND workflow-write
                             on the proof repo (fine-grained PAT: "Administration"
                             + "Workflows" Read/write; classic PAT: admin + the
                             "workflow" scope). Administration sets branch
                             protection / required checks / push restrictions;
                             workflow-write is REQUIRED because provision seeds
                             .github/workflows/governance-validate.yml, which
                             GitHub refuses to any credential lacking workflow
                             scope. Omit only if Mike provisions the workflow +
                             protection by hand in the GitHub UI.
  Optional:
    D5_CANONICAL_REF         default "refs/heads/main".
    D5_REQUIRED_CHECK        default "governance-validate" (the Action job name).
    D5_PROOF_KEEP            "1" → skip teardown of test branches (debugging).

  The tests SKIP (never fail/error) whenever the required env is absent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------- #
# Locations of the two artifacts the proof repo must carry for its required
# Action to run: the workflow and the (standalone) hardened validator.
# --------------------------------------------------------------------------- #
_TOOLS = Path(__file__).resolve().parents[1]                     # vault/tools

# sys.path bootstrap — importable as `lib.d5_proof_repo` AND runnable standalone
# (`python3 vault/tools/lib/d5_proof_repo.py`). Must precede the `lib.*` import.
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from lib.github_transport import run_git  # noqa: E402

WORKFLOW_SRC = _TOOLS / "federation" / "github-gate" / "governance-validate.yml"
VALIDATOR_SRC = _TOOLS / "federation" / "tropo_validate_governed.py"
WORKFLOW_DEST_REL = ".github/workflows/governance-validate.yml"
VALIDATOR_DEST_REL = "vault/tools/federation/tropo_validate_governed.py"

DEFAULT_CANONICAL_REF = "refs/heads/main"
DEFAULT_REQUIRED_CHECK = "governance-validate"

API_ROOT = "https://api.github.com"
GH_API_VERSION = "2022-11-28"

# A clean + a broken governed file, byte-for-byte fixed, for the P6 gate proof.
CLEAN_GOVERNED_FILE = (
    "---\n"
    "uid: d5c1ea11\n"
    "type: note\n"
    'title: "D5 proof — clean governed file"\n'
    "owner: mike\n"
    "---\n"
    "This file is well-formed; the required Action must let it pass.\n"
)
# Duplicate YAML key `uid:` — tropo_validate_governed.py rules this BROKEN (exit 1).
BROKEN_GOVERNED_FILE = (
    "---\n"
    "uid: d5b0056e\n"
    "type: note\n"
    'title: "D5 proof — broken governed file"\n'
    "owner: mike\n"
    "uid: d5b0056e\n"
    "---\n"
    "This file has a duplicate uid key; the required Action must BLOCK it.\n"
)

SKIP_REASON = (
    "D5 server-side proof requires a live disposable protected repo + the "
    "least-privilege App credential — set D5_PROOF_REPO and D5_GITHUB_APP_TOKEN "
    "(or the D5_GITHUB_APP_ID/INSTALLATION_ID/PRIVATE_KEY triple). See "
    "vault/tools/tests/README-d5-server-side-proof.md."
)


class ProofRepoError(Exception):
    """A provisioning / teardown / credential failure in the D5 proof harness."""


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass
class ProofConfig:
    repo: str                         # "owner/repo"
    push_token: Optional[str]         # least-privilege App token (under test)
    admin_token: Optional[str]        # administration:write (provision/teardown)
    canonical_ref: str = DEFAULT_CANONICAL_REF
    required_check: str = DEFAULT_REQUIRED_CHECK
    keep: bool = False

    @property
    def owner(self) -> str:
        return self.repo.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.repo.split("/", 1)[1]

    @property
    def branch(self) -> str:
        return self.canonical_ref.rsplit("/", 1)[-1]

    def authed_url(self, token: str) -> str:
        return f"https://x-access-token:{token}@github.com/{self.repo}.git"

    @classmethod
    def from_env(cls) -> Optional["ProofConfig"]:
        """Build a config from the D5_* env contract, or None if the minimum
        (a repo + a push credential) is absent. Never raises — a missing env is a
        SKIP signal, not an error."""
        repo = os.environ.get("D5_PROOF_REPO", "").strip()
        if not repo or "/" not in repo:
            return None
        push_token = _resolve_push_token_quiet()
        if not push_token:
            return None
        return cls(
            repo=repo,
            push_token=push_token,
            admin_token=os.environ.get("D5_GITHUB_ADMIN_TOKEN", "").strip() or None,
            canonical_ref=os.environ.get("D5_CANONICAL_REF", DEFAULT_CANONICAL_REF).strip(),
            required_check=os.environ.get("D5_REQUIRED_CHECK", DEFAULT_REQUIRED_CHECK).strip(),
            keep=os.environ.get("D5_PROOF_KEEP", "").strip() == "1",
        )


def server_creds_present() -> bool:
    """True when the minimum to RUN the server-side proof is set (repo + a push
    credential). Used by the tests' @skipUnless — evaluated at import, so it must
    never touch the network."""
    return ProofConfig.from_env() is not None


def admin_creds_present() -> bool:
    return bool(os.environ.get("D5_GITHUB_ADMIN_TOKEN", "").strip())


# --------------------------------------------------------------------------- #
# Credential minting (App-triple → installation token, via openssl; no py crypto)
# --------------------------------------------------------------------------- #
def _b64url(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _read_private_key() -> Optional[str]:
    raw = os.environ.get("D5_GITHUB_APP_PRIVATE_KEY", "").strip()
    if not raw:
        return None
    if raw.startswith("@"):
        p = Path(raw[1:]).expanduser()
        return p.read_text(encoding="utf-8") if p.is_file() else None
    return raw


def mint_installation_token(app_id: str, installation_id: str, private_key_pem: str) -> str:
    """Mint a short-lived installation access token from the App identity. Signs
    the App JWT with RS256 via the `openssl` CLI (stdlib base64 for the rest), so
    there is no PyJWT/cryptography dependency. Raises ProofRepoError on failure."""
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {"iat": now - 60, "exp": now + 540, "iss": str(app_id)}
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as kf:
        kf.write(private_key_pem)
        key_path = kf.name
    try:
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=signing_input.encode("ascii"), capture_output=True,
        )
        if proc.returncode != 0:
            raise ProofRepoError(f"openssl JWT signing failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
        jwt = f"{signing_input}.{_b64url(proc.stdout)}"
    finally:
        try:
            os.unlink(key_path)
        except OSError:
            pass
    status, body = api_request(
        "POST", f"/app/installations/{installation_id}/access_tokens", token=jwt, jwt=True,
    )
    if status != 201 or not isinstance(body, dict) or "token" not in body:
        raise ProofRepoError(f"installation-token exchange failed (HTTP {status}): {body}")
    return body["token"]


def _resolve_push_token_quiet() -> Optional[str]:
    """Return the least-privilege push token, minting from the App triple if
    needed. Returns None (never raises) so it is safe in the import-time
    skip check; minting only fires when the triple is actually present."""
    direct = os.environ.get("D5_GITHUB_APP_TOKEN", "").strip()
    if direct:
        return direct
    app_id = os.environ.get("D5_GITHUB_APP_ID", "").strip()
    installation_id = os.environ.get("D5_GITHUB_APP_INSTALLATION_ID", "").strip()
    pem = _read_private_key()
    if app_id and installation_id and pem:
        try:
            return mint_installation_token(app_id, installation_id, pem)
        except Exception:
            return None
    return None


# --------------------------------------------------------------------------- #
# Minimal GitHub REST client (explicit token — never ambient auth)
# --------------------------------------------------------------------------- #
def api_request(
    method: str,
    path: str,
    *,
    token: str,
    data: Optional[dict] = None,
    jwt: bool = False,
    accept: str = "application/vnd.github+json",
    timeout: int = 30,
):
    """One REST call with an EXPLICIT bearer token. Returns (status, parsed_body).
    HTTP errors are returned (not raised) so callers can assert on status codes."""
    url = API_ROOT + path
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", GH_API_VERSION)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        raw = err.read()
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = {"raw": raw.decode("utf-8", "replace")}
        return err.code, parsed


# --------------------------------------------------------------------------- #
# Provisioning
# --------------------------------------------------------------------------- #
def clone(cfg: ProofConfig, token: str, dest: Path) -> Path:
    """Clone the proof repo into `dest` using the given explicit token."""
    run_git(["clone", "--quiet", cfg.authed_url(token), str(dest)])
    return dest


def seed_repo_content(cfg: ProofConfig, work: Path) -> None:
    """Write the workflow, the standalone validator, and a clean seed governed
    file into `work` and commit them (does not push)."""
    (work / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (work / "vault" / "tools" / "federation").mkdir(parents=True, exist_ok=True)
    (work / "files").mkdir(parents=True, exist_ok=True)
    (work / WORKFLOW_DEST_REL).write_text(WORKFLOW_SRC.read_text(encoding="utf-8"), encoding="utf-8")
    (work / VALIDATOR_DEST_REL).write_text(VALIDATOR_SRC.read_text(encoding="utf-8"), encoding="utf-8")
    (work / "files" / "d5c1ea11.md").write_text(CLEAN_GOVERNED_FILE, encoding="utf-8")
    (work / "README.md").write_text(
        "# D5 disposable proof repo\n\n"
        "Provisioned by vault/tools/lib/d5_proof_repo.py for the D5 server-side\n"
        "enforcement proof (dev-spec 396d88a4 / test-spec 0f06a8b5). Disposable —\n"
        "safe to delete/reset between runs.\n",
        encoding="utf-8",
    )
    run_git(["add", "-A"], cwd=work)
    run_git(["commit", "-qm", "d5-proof: seed workflow + validator + clean governed file"], cwd=work)


def set_branch_protection(cfg: ProofConfig, *, restrict_to_app_slug: Optional[str] = None) -> dict:
    """PUT branch protection on the canonical ref via the ADMIN token: required
    'governance-validate' status check (strict = up-to-date = the exact-tip pin),
    enforce for admins, no force pushes, no deletions, linear history. Optionally
    restrict who may push to the least-privilege App only (org repos only).

    Returns the resulting protection body. Raises ProofRepoError without an admin
    token — provisioning protection is an administration:write act by design."""
    if not cfg.admin_token:
        raise ProofRepoError(
            "branch protection requires D5_GITHUB_ADMIN_TOKEN (administration:write). "
            "The least-privilege push token intentionally cannot set it."
        )
    payload = {
        "required_status_checks": {
            "strict": True,                       # branch must be up to date → exact-tip pin
            "checks": [{"context": cfg.required_check}],
        },
        "enforce_admins": True,                   # unbypassable, even for admins
        "required_pull_request_reviews": None,
        "restrictions": (
            {"users": [], "teams": [], "apps": [restrict_to_app_slug]}
            if restrict_to_app_slug else None
        ),
        "allow_force_pushes": False,              # server refuses force push
        "allow_deletions": False,                 # server refuses ref deletion
        "required_linear_history": True,          # non-ff / merge-tree rewrite refused
    }
    status, body = api_request(
        "PUT",
        f"/repos/{cfg.repo}/branches/{cfg.branch}/protection",
        token=cfg.admin_token,
        data=payload,
        accept="application/vnd.github+json",
    )
    if status not in (200, 201):
        raise ProofRepoError(f"set branch protection failed (HTTP {status}): {body}")
    return body if isinstance(body, dict) else {}


def provision(cfg: ProofConfig, *, restrict_to_app_slug: Optional[str] = None) -> dict:
    """End-to-end provision: verify the repo exists, seed the workflow/validator/
    clean file onto the canonical ref (admin push, before protection), then set
    branch protection. Returns a summary dict. Requires the admin token."""
    if not cfg.admin_token:
        raise ProofRepoError("provision requires D5_GITHUB_ADMIN_TOKEN (administration:write).")
    status, repo = api_request("GET", f"/repos/{cfg.repo}", token=cfg.admin_token)
    if status != 200:
        raise ProofRepoError(
            f"proof repo {cfg.repo} not reachable (HTTP {status}): {repo}. "
            "Create the disposable repo first (Mike/ops), then re-run provision."
        )
    with tempfile.TemporaryDirectory() as td:
        work = clone(cfg, cfg.admin_token, Path(td) / "work")
        seed_repo_content(cfg, work)
        push = run_git(["push", "--quiet", cfg.authed_url(cfg.admin_token),
                        f"HEAD:{cfg.canonical_ref}"], cwd=work, check=False)
        if push.returncode != 0:
            stderr = (push.stderr or "").strip()
            # The seed commit adds .github/workflows/governance-validate.yml, so the
            # provisioning credential MUST be allowed to write workflow files. A
            # fine-grained PAT needs "Workflows: Read and write"; a classic PAT
            # needs the "workflow" scope. Fail fast with an actionable message
            # instead of surfacing a raw git traceback. (D5 provisioning gotcha,
            # argus 2026-07-22.)
            if "workflow" in stderr.lower():
                raise ProofRepoError(
                    "provision could not seed the governance-validate workflow onto "
                    f"{cfg.canonical_ref}: D5_GITHUB_ADMIN_TOKEN cannot create/update "
                    "files under .github/workflows/. Grant the provisioning credential "
                    "workflow-write — a fine-grained PAT needs 'Workflows: Read and "
                    "write'; a classic PAT needs the 'workflow' scope — then re-run "
                    f"provision. (git rejected the push: {stderr})"
                )
            raise ProofRepoError(f"provision push to {cfg.canonical_ref} failed: {stderr}")
    protection = set_branch_protection(cfg, restrict_to_app_slug=restrict_to_app_slug)
    return {
        "repo": cfg.repo,
        "canonical_ref": cfg.canonical_ref,
        "required_check": cfg.required_check,
        "protection_url": protection.get("url"),
        "private": bool(repo.get("private")) if isinstance(repo, dict) else None,
    }


def teardown(cfg: ProofConfig) -> dict:
    """Remove branch protection and delete every `d5-proof/*` test branch. Never
    deletes the repo or the canonical ref. No-op teardown of protection needs the
    admin token; test-branch cleanup uses the push token."""
    result: dict = {"deleted_branches": [], "protection_removed": False}
    if cfg.keep:
        result["kept"] = True
        return result
    if cfg.admin_token:
        status, _ = api_request(
            "DELETE", f"/repos/{cfg.repo}/branches/{cfg.branch}/protection",
            token=cfg.admin_token,
        )
        result["protection_removed"] = status in (200, 204)
    token = cfg.push_token or cfg.admin_token
    if token:
        status, refs = api_request("GET", f"/repos/{cfg.repo}/branches?per_page=100", token=token)
        if status == 200 and isinstance(refs, list):
            for b in refs:
                nm = b.get("name", "")
                if nm.startswith("d5-proof/"):
                    st, _ = api_request(
                        "DELETE", f"/repos/{cfg.repo}/git/refs/heads/{nm}", token=token)
                    if st in (200, 204):
                        result["deleted_branches"].append(nm)
    return result


# --------------------------------------------------------------------------- #
# CLI — provision / teardown / doctor
# --------------------------------------------------------------------------- #
def _doctor() -> int:
    """Report what the env contract resolves to, without touching the network for
    anything but an optional whoami. Exit 0 = ready to run the proof."""
    cfg = ProofConfig.from_env()
    if cfg is None:
        print("D5 proof: NOT READY — missing D5_PROOF_REPO and/or a push credential.")
        print(SKIP_REASON)
        return 1
    print(f"D5 proof: repo           = {cfg.repo}")
    print(f"D5 proof: canonical_ref  = {cfg.canonical_ref}")
    print(f"D5 proof: required_check = {cfg.required_check}")
    print(f"D5 proof: push token     = present ({'minted' if not os.environ.get('D5_GITHUB_APP_TOKEN') else 'direct'})")
    print(f"D5 proof: admin token    = {'present' if cfg.admin_token else 'ABSENT (provision/teardown disabled)'}")
    status, body = api_request("GET", f"/repos/{cfg.repo}", token=cfg.push_token)
    if status == 200 and isinstance(body, dict):
        perms = body.get("permissions", {})
        print(f"D5 proof: repo reachable — permissions={perms}")
        print("D5 proof: NOTE — for a fine-grained PAT this 'admin' value mirrors the "
              "token OWNER's role, not the token's scopes; least-privilege is asserted "
              "functionally (an admin write must be refused) by test_push_token_is_least_privilege.")
        return 0
    print(f"D5 proof: repo GET returned HTTP {status}: {body}")
    return 2


def main(argv: Optional[list] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="d5_proof_repo",
        description="D5 disposable-protected-repo proof harness (provision/teardown/doctor).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_prov = sub.add_parser("provision", help="seed workflow+validator+clean file, set branch protection")
    p_prov.add_argument("--restrict-to-app-slug", default=None,
                        help="restrict pushes to this App slug (org repos only)")
    sub.add_parser("teardown", help="remove protection + delete d5-proof/* branches")
    sub.add_parser("doctor", help="report resolved env contract + repo reachability")
    args = parser.parse_args(argv)

    if args.cmd == "doctor":
        return _doctor()
    cfg = ProofConfig.from_env()
    if cfg is None:
        print(SKIP_REASON)
        return 1
    try:
        if args.cmd == "provision":
            print(json.dumps(provision(cfg, restrict_to_app_slug=args.restrict_to_app_slug), indent=2))
        elif args.cmd == "teardown":
            print(json.dumps(teardown(cfg), indent=2))
    except ProofRepoError as e:
        print(f"d5_proof_repo: {args.cmd} failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover — standalone CLI path
    raise SystemExit(main())


__all__ = [
    "ProofConfig", "ProofRepoError", "server_creds_present", "admin_creds_present",
    "mint_installation_token", "api_request", "clone", "seed_repo_content",
    "set_branch_protection", "provision", "teardown",
    "CLEAN_GOVERNED_FILE", "BROKEN_GOVERNED_FILE", "SKIP_REASON",
    "DEFAULT_CANONICAL_REF", "DEFAULT_REQUIRED_CHECK",
]
