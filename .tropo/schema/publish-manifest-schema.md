---
uid: null
title: "Tropo Publish Receipt — Schema Reference"
status: locked
type: schema-reference
tier: os
schema_version: 1
owner: talos
created: '2026-07-08'
modified: '2026-07-08'
refs:
 - path: "vault/files/44badb55.md"
   title: "Two-machine sovereignty proof + Git Beat 2 federation transport (ADR-051, v1.84 DoD)"
 - path: "vault/files/18059aef.md"
   title: "ADR-051"
 - path: "vault/files/409ef1cc.md"
   title: "Mount-gate + compose-lockfile (the pin the pull side re-checks against)"
 - path: "vault/files/98b9610a.md"
   title: "Git Beat 1 — local history-of-record (the private-side foundation this transport builds on)"
---

# Tropo Publish Receipt — Schema Reference v1

*The authoritative schema for the publish receipt `tropo-publish.py` emits on every run, and the ancestry/environment assertions it and its readers (`check_publish_boundary`, `tropo-mount.py`'s pull-side enforcement) all rely on.*
*Locked v1 on 2026-07-08 by Talos T27, per dev-spec [44badb55](../../vault/files/44badb55.md) implementing [ADR-051](../../vault/files/18059aef.md) (Argus A128 rulings, red-team-hardened).*
*Style mirrors [`shard-index-schema.md`](shard-index-schema.md) and [`compose-lockfile-schema.md`](compose-lockfile-schema.md) in this folder.*

---

## Overview

`tropo-publish.py` is the orphan-commit publisher: it enumerates a mounted **team vault**'s own `vault/files/*.md`, applies a two-gate allowlist (public `extraction_scope` AND a derived `segment` matching that team vault's own manifest UID), builds a fresh commit from exactly the files that clear both gates, and pushes only that single branch ref. **The receipt this schema documents is the honest, auditable record of what happened** — what crossed, what stayed home (without leaking what it *was*), and the git-plumbing proof that no private-origin history rode along.

**The privacy boundary is the filter + the orphan/accumulating-only construction — never `.gitignore`, never a server-side hook.** The receipt exists so that boundary is *checkable*, not merely *asserted*: `check_publish_boundary` (`tropo-validate.py`) and the pull-side mount-gate re-check (`tropo-mount.py`) never trust this receipt — they independently re-derive the same facts from the actual committed git object graph (Ruling 10, "B independently verifies"). The receipt is for **human/audit legibility**, not a trust boundary in itself.

**Emitted by:** `vault/tools/tropo-publish.py`, one receipt per invocation (dry-run or `--apply`).

**Format:** JSON, deterministic serialization (`json.dumps(..., sort_keys=True, separators=(',', ':'))` in the canonical form; the CLI's own `--receipt-out` prints an indented variant for human reading — the *content*, not the whitespace, is what determinism (AC11) is about).

**Consumed by:** a human reviewing a publish before/after the fact. **Not** consumed programmatically as a trust input by any validator or gate — see "Independent re-verification" below.

---

## Top-level shape

```json
{
  "team_vault_uid": "<8-hex>",
  "team_vault_root": "<path>",
  "remote": "<url-or-path>",
  "branch": "team-main",
  "crossed": [ /* see §Crossed set */ ],
  "held_back_count": 1,
  "held_back": [ /* see §Held-back */ ],
  "path_refusals": [ "<human-readable reason>", ... ],
  "environment_assertions": {
    "no_submodules": true,
    "single_worktree": true,
    "reflog": "<human-readable detail — see §Environment assertions>"
  },
  "applied": false,
  "new_commit": null,
  "parent": null,
  "ancestry_proof": null,
  "push_output": null,
  "note": "<present on a no-op or dry-run run>"
}
```

`applied`, `new_commit`, `parent`, `ancestry_proof`, and `push_output` are only populated when `--apply` actually wrote and pushed a commit; a dry-run (the default) or a run with nothing crossing leaves them `false`/`null`.

---

## Crossed set

```json
{
  "uid": "11111111",
  "path": "vault/files/11111111.md",
  "normalized_extraction_scope": "ship",
  "derived_segment": "aaaabbbb",
  "content_sha256": "<64-hex sha256 of the file's raw bytes>"
}
```

- **`normalized_extraction_scope`** — the value AFTER `lib.segment.normalize_extraction_scope` (NFKC → strip Cf/Cc → strip() → casefold()), never the raw frontmatter string. Proves what the allowlist comparison actually saw, not what a human might assume a raw value meant.
- **`derived_segment`** — `lib.segment.derive_segment`'s output, never a hand-editable per-record `segment:` frontmatter field (which this module never reads at all — see the un-forgeability contract in `lib/segment.py`).
- **`content_sha256`** — the crossed file's raw-byte hash at publish time. Lets a reader independently confirm exactly what content a given `uid` carried when it crossed, without re-deriving anything from git plumbing.

---

## Held-back — no metadata leak (AC "HONEST EXCLUSION RECEIPT")

```json
{
  "uid": "22222222",
  "extraction_scope": "argo-reference",
  "segment": "aaaabbbb"
}
```

**Deliberately minimal: `uid`, `extraction_scope`, `segment` — nothing else.** No `title`, no `type`, no `description`, no body content. The receipt proves a file was correctly excluded and gives its raw (non-normalized) scope and derived segment as the "why," without itself becoming a second leak surface for whatever the excluded file's content or title actually was. `held_back_count` duplicates `len(held_back)` as a cheap sanity total a reader can check without counting.

---

## Path refusals

A flat list of human-readable strings — one per file refused at the path-safety stage (symlink, hardlink, or realpath-escape) **before any frontmatter was ever read**. These files contribute **zero** rows to either `crossed` or `held_back`: a path-safety refusal is not a normal exclusion (the tool never read far enough to safely report even a `uid`), so there is nothing to include beyond the refusal reason itself.

---

## Environment assertions

```json
{
  "no_submodules": true,
  "single_worktree": true,
  "reflog": "remote /path/to/bare-remote.git reflog disabled (core.logallrefupdates=false/unset)"
}
```

- **`no_submodules`** / **`single_worktree`** — booleans; `tropo-publish.py` refuses outright (raises, publishes nothing) rather than proceeding with either false, so a receipt only ever shows `true` for these two.
- **`reflog`** — a human-readable detail string, not a boolean, because this check has **three** outcomes, not two: (1) verifiably disabled on a local-path remote (the normal green case), (2) verifiably **enabled** on a local-path remote — this REFUSES the publish outright, so it never appears in a receipt for a completed run, (3) **unverifiable** — the remote is a non-local URL (a real GitHub/GitLab-class host), a **named platform limit** (Ruling 11), disclosed in this string rather than silently assumed clean. A receipt whose `reflog` string contains "cannot be verified client-side" is reporting case 3 honestly, not case 1.

---

## Ancestry proof

```json
{
  "holds": true,
  "detail": "3 commit(s) reachable, linear, single orphan root; 9 object(s) reachable"
}
```

Populated only on a real `--apply` run. `holds: false` never appears in a receipt for a completed publish — `tropo-publish.py` raises `PublishRefused` and pushes nothing if the ancestry check fails on the commit it just built, per Ruling 5 ("EVERY commit reachable from the team branch was built from only-public files; no commit ever held private content"). The proof itself is **walked, not asserted**: `git log --format=%H %P` across the whole reachable history, confirming (a) no commit has more than one parent (a merge is exactly how unrelated/private history could enter) and (b) exactly one reachable commit has zero parents (the true orphan root — see Ruling 5's "public-only ACCUMULATING history": the FIRST publish is an orphan root, every SUBSEQUENT publish's parent is the prior team-branch tip, never a merge/rebase/cherry-pick from the private repo).

---

## Independent re-verification — this receipt is never a trust input (Ruling 10)

**No validator or gate in this studio ever reads a `tropo-publish.py` receipt as a fact to trust.** `check_publish_boundary` (`tropo-validate.py`) and the pull-side check in `tropo-mount.py::pull_side_team_branch_check` both re-derive every fact this schema documents **directly from the committed git object graph** — re-walking `git log`/`git rev-list --objects`, re-reading each file via `git show <tip>:<path>` (never the working tree, which closes the TOCTOU between what a filter saw and what is actually in the object store), and re-computing both gates via the exact same `lib/segment.py` functions `tropo-publish.py` itself calls. A compromised or merely buggy publish tool cannot assert its way past either re-check by writing a receipt that says the right thing — the receipt documents intent and provides an audit trail; the object graph is the only fact either re-check ever trusts.

---

## Example — a complete receipt (dry-run)

```json
{
  "applied": false,
  "branch": "team-main",
  "crossed": [
    {"uid": "11111111", "path": "vault/files/11111111.md", "normalized_extraction_scope": "ship", "derived_segment": "aaaabbbb", "content_sha256": "270f174e..."}
  ],
  "environment_assertions": {"no_submodules": true, "single_worktree": true, "reflog": "remote /path/to/bare-remote.git reflog disabled (core.logallrefupdates=false/unset)"},
  "held_back": [
    {"uid": "22222222", "extraction_scope": "argo-reference", "segment": "aaaabbbb"}
  ],
  "held_back_count": 1,
  "note": "dry-run — no objects written, nothing pushed (pass --apply to execute)",
  "path_refusals": [],
  "remote": "/path/to/bare-remote.git",
  "team_vault_root": "/path/to/team-vault",
  "team_vault_uid": "aaaabbbb"
}
```

---

## Rationale Summary

**Why the receipt is not a trust input:** a covenant this strict ("private provably never crosses") cannot depend on the honesty or correctness of the one tool doing the crossing — Ruling 10 exists precisely so a bug in `tropo-publish.py` is caught by an independent re-derivation, not laundered through a receipt that merely echoes what the (possibly buggy) tool believed it did.

**Why held-back carries uid/scope/segment and nothing else:** the receipt's own job is to prove the boundary held; giving it enough rope to also leak a private file's title or body would make the audit trail itself a violation of the thing it audits.

**Why environment assertions distinguish "verified disabled" from "cannot verify" rather than collapsing both to a boolean:** collapsing them would either (a) silently treat an unverifiable platform remote as verified-safe (dishonest), or (b) refuse every real GitHub/GitLab-class remote outright (unworkable) — Ruling 11 names the platform-visibility ceiling explicitly rather than hiding it behind a boolean that can't represent "don't know."

---

## Refs

- **Dev-spec:** `vault/files/44badb55.md` — Two-machine sovereignty proof + Git Beat 2 federation transport
- **ADR-051:** `vault/files/18059aef.md`
- **Shared module:** `vault/tools/lib/segment.py`
- **Publisher:** `vault/tools/tropo-publish.py`
- **Validator (independent re-check):** `vault/tools/tropo-validate.py::check_publish_boundary`
- **Pull-side enforcement:** `vault/tools/tropo-mount.py::pull_side_team_branch_check`
- **Compose-Lockfile Schema (mount_path / remote provenance):** `.tropo/schema/compose-lockfile-schema.md`
- **Shard-Index Schema (composed-index exclusion on pull):** `.tropo/schema/shard-index-schema.md`

---

*Publish Receipt Schema v1 | Locked | Talos T27 | 2026-07-08*
*"The receipt documents intent. The object graph is the only thing either re-check trusts."*
