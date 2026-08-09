# D5 server-side enforcement proof — how to run it

*Pairs dev-spec [`396d88a4`](../../files/396d88a4.md) (D5 Atomic Promotion, GitHub.com transport) + test-spec [`0f06a8b5`](../../files/0f06a8b5.md). Built by Talos T35, 2026-07-19. This harness is **ready to run the moment the least-privilege GitHub App credential is provisioned as a Cloud secret** — until then every test SKIPS cleanly.*

---

## What this proves (and why a local bare remote can't)

The existing suite `test_d5_atomic_promotion_0f06a8b5.py` proves the **client-side** D5 mechanics against a local `file://` bare remote: CAS non-ff, exact-SHA / changed-tree refusal, the receipt-ref gauntlet, the closed error enum, `landed`=local-only, and the validator + hook logic. A `file://` remote **accepts** a `git push --force` and relies on the *client* to detect the rewrite afterward.

A **live disposable protected GitHub repo** proves the half a bare remote cannot — that the **host itself refuses**, so enforcement is unbypassable rather than merely detectable:

| Test | Assertion | Server-side property proven |
|---|---|---|
| `test_push_token_is_least_privilege` | P2 | the credential under test can push but **cannot administer** |
| `test_server_refuses_force_push_to_protected_ref` | P2 | GitHub **rejects** a force push to the canonical ref (not client-detected) |
| `test_server_refuses_unchecked_direct_push_to_main` | P2 | a clean ff commit pushed **directly to main** is rejected — required check unbypassable onto main |
| `test_required_action_blocks_broken_governed_file` | P6 | the **required Action** running the hardened validator concludes `failure` on a broken governed file |
| `test_required_action_passes_clean_governed_file` | P6 | a clean governed file concludes `success` |
| `test_pre_commit_hook_absence_detected_and_server_is_backstop` | P6 | missing local hook is **detected + refused**, and the server Action still blocks a broken file reaching main |

---

## Env contract (Cloud secrets)

| Var | Required? | Meaning |
|---|---|---|
| `D5_PROOF_REPO` | yes | `owner/repo` of the disposable protected repo, e.g. `tropo-ai/tropo-d5-proof` |
| `D5_GITHUB_APP_TOKEN` | yes* | the least-privilege installation access token (**the credential under test**) |
| `D5_GITHUB_APP_ID` | alt* | App id — with the two below, the harness mints the token at runtime (RS256 via `openssl`) |
| `D5_GITHUB_APP_INSTALLATION_ID` | alt* | installation id on the proof repo's owner |
| `D5_GITHUB_APP_PRIVATE_KEY` | alt* | App private key PEM (raw PEM, or `@/path/to/key.pem`) |
| `D5_GITHUB_ADMIN_TOKEN` | provision only | `administration:write` — sets branch protection. Omit if Mike configures protection in the UI. Kept **separate** from the push token by design. |
| `D5_CANONICAL_REF` | no | default `refs/heads/main` |
| `D5_REQUIRED_CHECK` | no | default `governance-validate` (the Action job name) |
| `D5_PROOF_KEEP` | no | `1` → skip teardown of `d5-proof/*` branches |
| `D5_CHECK_TIMEOUT_S` | no | default `240` — max wait for the required Action to conclude |

\* Provide **either** `D5_GITHUB_APP_TOKEN` **or** the `D5_GITHUB_APP_ID` + `D5_GITHUB_APP_INSTALLATION_ID` + `D5_GITHUB_APP_PRIVATE_KEY` triple. When both push-credential paths are absent, the suite skips.

The harness performs **every write with the explicit `D5_*` token** — never the ambient `gh`/git credential — so the proof exercises the App the spec names, not whatever the box is logged in as.

---

## Run it

```bash
# 0. from the Studio root — check the env contract resolves (no network writes)
python3 vault/tools/lib/d5_proof_repo.py doctor

# 1. provision the disposable repo (needs D5_GITHUB_ADMIN_TOKEN, or do it by UI)
python3 vault/tools/lib/d5_proof_repo.py provision
#    (org repos only: --restrict-to-app-slug <app-slug> restricts pushes to the App)

# 2. run the server-side proof (from vault/tools/)
cd vault/tools
python3 -m unittest -v tests.test_d5_server_side_proof

# 3. tear down the test branches (protection stays unless admin token present)
python3 vault/tools/lib/d5_proof_repo.py teardown
```

With no credential, step 2 prints `OK (skipped=N)` — safe in every environment.

---

## Provisioning checklist for Mike — least-privilege GitHub App

Copy-paste actionable. Two principals by design: a **least-privilege App** that can push but not administer (the credential under test), and an **admin token** used only to set protection.

### A. Create the disposable repo
- [ ] Create a throwaway repo, e.g. `tropo-ai/tropo-d5-proof`. **It must be PUBLIC unless the owning account is on GitHub Pro/Team** — GitHub's **free tier cannot enable branch protection on a private repo** (PUT `…/branches/main/protection` returns `403 "Upgrade to GitHub Pro or make this repository public"`), and branch protection is the exact enforcement D5 proves. The repo holds only test fixtures (the governance-validate workflow + validator + clean/broken files) and never any secret or real vault data, so public is safe for a disposable proof repo. (D5 provisioning gotcha, argus-a136 2026-07-22.)
- [ ] Settings → Actions → **enable Actions** for the repo (the required check must be allowed to run).

### B. Create the least-privilege GitHub App (the credential UNDER TEST)
- [ ] New GitHub App (org or personal). Repository permissions ONLY:
  - [ ] **Contents: Read and write** — advance the canonical ref / push branches.
  - [ ] **Pull requests: Read and write** — the harness opens the proof PRs.
  - [ ] **Actions: Read-only** — read the required governance-validate workflow conclusion (via the Actions API). *(GitHub does not expose a grantable "Checks" permission for fine-grained PATs in all account types; the harness reads the workflow conclusion via `/actions/runs`, so Actions:read is the correct grant — D5 provisioning, argus-a136 2026-07-22.)*
  - [ ] **Metadata: Read-only** (mandatory baseline).
  - [ ] **Administration: _NOT granted_** — the App must be unable to change branch protection. This is the point of `test_push_token_is_least_privilege`.
  - [ ] No Actions, Workflows, or Admin scopes.
- [ ] Install the App on the disposable repo ONLY (not org-wide).
- [ ] Provide as Cloud secrets **either**:
  - `D5_GITHUB_APP_TOKEN` = a fresh installation access token, **or**
  - `D5_GITHUB_APP_ID`, `D5_GITHUB_APP_INSTALLATION_ID`, `D5_GITHUB_APP_PRIVATE_KEY` (the harness mints the token — durable across the token's 1-hour expiry).

### C. Branch protection on the canonical ref (`main`) — via `D5_GITHUB_ADMIN_TOKEN` or the UI
Set (the `provision` command sets all of these via the REST API when given an admin token):
- [ ] **Require status checks to pass** → select **`governance-validate`**.
- [ ] **Require branches to be up to date before merging** (strict) — this is the exact-tip pin.
- [ ] **Require linear history** — refuses non-ff / merge-tree rewrites.
- [ ] **Do not allow force pushes.**
- [ ] **Do not allow deletions.**
- [ ] **Do not allow bypassing the above / Include administrators** (`enforce_admins`) — unbypassable onto main.
- [ ] (org repos only) **Restrict who can push** → the least-privilege App only.

If you use an admin token as a Cloud secret it needs **two** repository permissions on the disposable repo only — **Administration: Read and write** (branch protection) **and Workflows: Read and write** (classic PAT: the `workflow` scope). The second is mandatory because `provision` seeds `.github/workflows/governance-validate.yml`, and GitHub refuses any credential without workflow-write from creating or updating files under `.github/workflows/` — via `git push`, the Contents API, *and* the low-level Git Data trees API alike. Without it `provision` fails fast with `refusing to allow a Personal Access Token to create or update workflow … without workflow scope`. Keep this admin credential distinct from the App's push token. (D5 provisioning gotcha, argus 2026-07-22.)

> **Least-privilege verification uses a functional probe, not the repo `permissions` field.** `test_push_token_is_least_privilege` does **not** trust the `permissions.admin` value on the repo response: for a **fine-grained PAT** GitHub populates that field from the token *owner's* role on the repo, not from the token's granted scopes, so a fine-grained PAT owned by a repo admin reports `admin: true` even with no Administration grant. The test instead asserts that the credential under test is **refused** (`403/404`) when it attempts an idempotent administration write. Provisioning `doctor` still prints the `permissions` field, so expect `admin: true` there for an owner-held fine-grained PAT — it is not a failure signal; the functional probe in the test is authoritative.

### D. Required-Action wiring (handled by `provision`, listed for a manual path)
- [ ] `.github/workflows/governance-validate.yml` on the repo → copy of [`vault/tools/federation/github-gate/governance-validate.yml`](../federation/github-gate/governance-validate.yml).
- [ ] `vault/tools/federation/tropo_validate_governed.py` on the repo (the standalone hardened validator the workflow invokes).
- [ ] A clean seed governed file under `files/` so `main` starts valid.

### E. Exact Cloud-secret env var names the harness expects
```
D5_PROOF_REPO
D5_GITHUB_APP_TOKEN            # or the triple below
D5_GITHUB_APP_ID
D5_GITHUB_APP_INSTALLATION_ID
D5_GITHUB_APP_PRIVATE_KEY
D5_GITHUB_ADMIN_TOKEN          # provision/teardown only
```

Real production promotion stays a Mike-gated act (dev-spec `396d88a4` §Open) — this harness proves the mechanism against a disposable repo; it never publishes real data.
