---
uid: null
title: "Tropo Compose-Lockfile — Schema Reference"
status: locked
type: schema-reference
tier: os
schema_version: 1
owner: talos
created: '2026-07-08'
modified: '2026-07-08'
refs:
 - path: "vault/files/409ef1cc.md"
   title: "Mount-gate + compose-lockfile + per-vault-root manifest governed-write gate (ADR-051 Fork 2)"
 - path: "vault/files/18059aef.md"
   title: "ADR-051"
 - path: "vault/files/a1f7c750.md"
   title: "vault.capsule — vault-node manifest type"
---

# Tropo Compose-Lockfile — Schema Reference v1

*The authoritative schema for the compose-lockfile (`.tropo-studio/compose.lock`) and the per-vault-root manifest path convention it governs.*
*Locked v1 on 2026-07-08 by Talos T26, per dev-spec [409ef1cc](../../vault/files/409ef1cc.md) implementing [ADR-051](../../vault/files/18059aef.md) Fork 2 (Argus A127 rulings).*
*Style mirrors [`vault-index-schema.md`](vault-index-schema.md) in this folder.*

---

## Overview

The compose-lockfile is a **studio-level** JSON artifact recording every vault this studio has mounted. One JSON object per mounted vault-UID. Mounting is a `member_of` edge + clone, **pinned by the lockfile** ([5d3ab142](../../vault/files/5d3ab142.md) §6) — the studio records each mounted vault's resolved commit state so composition is reproducible: same lockfile ⇒ same composed brain. Mounted vaults do NOT float at HEAD.

**Location:** `<studio-root>/.tropo-studio/compose.lock` (RULED, per 409ef1cc — studio-level, not per-vault, because composition is a studio-wide act).

**Format:** JSON (not JSONL). Chosen for human legibility over the `.jsonl`-registry alternative (OP-12) — a `.lock` name signals "lockfile" to a cold reader at a glance, matching the `package-lock.json` / `Cargo.lock` convention a stranger already knows.

**Written/updated exclusively by:** `vault/tools/tropo-mount.py` (the mount-gate). A hand-edit of `compose.lock` is a governed-write bypass of the same class `vault/AGENTS.md` names for `vault/files/` direct-writes — do not hand-edit; run the gate.

**Companion path convention (this schema also documents it, per 409ef1cc §2):** each mounted vault's manifest lives at `<vault-root>/.tropo/vault-manifest.md` — a kernel-tier sibling to `.tropo/studio-identity.md` ([32067bea](../../vault/files/32067bea.md)), outside `vault/files/`. This is the file `tropo-mount.py` reads and validates before writing a compose.lock record.

---

## Top-level shape

```json
{
  "schema_version": 1,
  "vaults": {
    "<vault_uid>": { ... one record, shape below ... },
    "<vault_uid>": { ... }
  }
}
```

`vaults` is keyed by the mounted vault's 8-hex UID (the vault-node UID from its manifest's `uid:` field) — this is also the segment key the composed index assigns records to (signed **I1**, [dd16c90c](../../vault/files/dd16c90c.md): segment = vault-node UID; one-clone-per-vault-UID guarantees no UID appears under two segment tags).

---

## Record Schema v1

Every record under `vaults.<vault_uid>` is a JSON object with the following fields:

```json
{
  "vault_uid": "<8-char-hex>",
  "resolved_commit": "<full git commit hash>",
  "manifest_version": "<semver string, from the mounted manifest's version: field>",
  "contract_hash": "<sha256 hex digest of the canonical JSON dump of the contract block>",
  "contract": { "...": "the full contract block, verbatim, as of this pin" },
  "consent": { "...": "governed executable-consent record, shape below" },
  "name_prefix": "<the <vault>: qualification prefix for this mount>",
  "mounted_at": "<ISO 8601 UTC timestamp>",
  "mounted_by": "<principal who ran the mount>",
  "mount_path": "<absolute local filesystem path used at mount time>",
  "manifest_kind": "<the mounted manifest's kind: field, verbatim>"
}
```

### Field Reference

#### `vault_uid` — required
- **Type:** string, 8-char lowercase hex (`^[0-9a-f]{8}$`)
- **Source:** the mounted vault's own manifest `uid:` field
- **Purpose:** primary key (duplicated as the dict key + inside the record for self-description when a record is extracted/logged standalone)

#### `resolved_commit` — required
- **Type:** string, full git commit hash (40 hex chars)
- **Source:** `git -C <mount-path> rev-parse HEAD` at mount time
- **Constraints:** never a branch name, tag, or `HEAD` — always a resolved, immutable commit. A mount-path that cannot resolve to a commit (not a git repo, no commits) is refused, never recorded with a placeholder.
- **Purpose:** the reproducibility anchor — composing from this lockfile always resolves this vault to exactly this commit, never floats to a branch's current tip.

#### `manifest_version` — required
- **Type:** string (semver)
- **Source:** the mounted manifest's `version:` field at pin time
- **Purpose:** the "before" state a future re-mount's narrowing-diff compares its "after" manifest_version against (a1f7c750 Guarded Transitions: contract narrowing MUST bump this).

#### `contract_hash` — required
- **Type:** string, sha256 hex digest (64 hex chars)
- **Computation:** `sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")))`
- **Purpose:** a quick equality fingerprint. The AUTHORITATIVE narrowing-diff does not trust the hash alone — it walks the full `contract` object stored alongside it (below), because a hash mismatch alone cannot say WHAT narrowed.

#### `contract` — required
- **Type:** object (verbatim copy of the mounted manifest's `contract:` block)
- **Shape (per a1f7c750):** `registered_types` (array of strings), `capsule_versions` (object, capsule-name → semver string), `capabilities` (array of strings — the `<vault>:skill`-qualified or unqualified capability names this mount exposes), and any other fields the mounted manifest's contract declares.
- **Purpose:** stored in full (not just hashed) so a re-mount's narrowing check is a real structural diff — dropped `registered_types` entries, downgraded `capsule_versions` entries, or dropped `capabilities` entries are each individually named in a refusal message, not just "the hash changed."

#### `consent` — required
- **Type:** object
- **Shape:**
  ```json
  {
    "consented": true,
    "consented_by": "<principal>",
    "consented_at": "<ISO 8601 UTC timestamp>",
    "capability_set": ["<name>", "<name>", "..."]
  }
  ```
  or, when no capabilities were ever declared / consented:
  ```json
  { "consented": false, "capability_set": [] }
  ```
- **Purpose:** the governed-write record of executable-consent (bc25583d §6 / 5d3ab142 §5) — recorded on disk, not a runtime toggle, so it survives process restart and travels with the composition. `capability_set` is the exact set consented to at the time of `consented_at`; a contract widening that adds new capabilities re-triggers consent for the delta (the RULED per-vault-at-first-mount granularity, 409ef1cc "RULED conventions").
- **Constraint:** a mount whose `contract.capabilities` is non-empty MUST have `consent.consented == true` with a non-empty `capability_set` covering every declared capability, or the mount-gate refuses to write the record at all (AC-3).

#### `name_prefix` — required
- **Type:** string
- **Source:** the mounted manifest's `prefix_policy.mint_prefix`, if present; else defaults to the `vault_uid` itself.
- **Purpose:** the qualification prefix a mounted capability's name resolves under — `<name_prefix>:<capability>` — so capability names never collide with this studio's own reserved OS/private capability namespace (dependency-confusion defense, Birsan 2021, per 5d3ab142 §6 / bc25583d §6).

#### `mounted_at` — required
- **Type:** string, ISO 8601 UTC timestamp
- **Constraints:** set at first mount; preserved (not overwritten) on a re-mount that does not include a fresh `--consent` (only a genuinely re-consented write refreshes it)
- **Purpose:** audit trail — when this vault entered the composition

#### `mounted_by` — required
- **Type:** string
- **Purpose:** advisory provenance — who ran the mount gesture

#### `mount_path` — required (v1 amendment, 2026-07-08, security-review fix)
- **Type:** string, absolute local filesystem path
- **Source:** the `--mount-path` argument the mount was run with, resolved to an absolute path
- **Purpose:** lets `check_vault_manifest_governed_write_gate` (`vault/tools/tropo-validate.py`) re-read the LIVE `<mount_path>/.tropo/vault-manifest.md` on disk and diff it against the pinned `contract`/`contract_hash` — closing the gap where the governed-write gate could previously only re-hash compose.lock's own embedded contract against its own hash (catching a hand-edit of compose.lock, but never a direct hand-edit of the actual governed artifact, the manifest file itself).
- **Constraint / honesty note:** this is advisory, LOCAL-MACHINE state, not a durable cross-machine pin (a real federated clone's local path is not guaranteed to be the same path, or to exist at all, on a different machine or after the local clone is removed). The validator's cross-check treats a missing/unreachable `mount_path` as "cannot verify against the live manifest" — it does NOT silently pass, and it does NOT itself become a new refusal surface for `tropo-mount.py` (a missing mount_path never blocks a mount). The reproducibility guarantee that matters (AC-4) remains `resolved_commit`; `mount_path` is a live-detection convenience layered on top, same spirit as `git remote` tracking a path that can go stale.

#### `manifest_kind` — required (v1 amendment, 2026-07-08, security-review fix)
- **Type:** string, the mounted manifest's `kind:` field verbatim
- **Purpose:** lets `check_vault_manifest_governed_write_gate`'s Fork-3 kind-immutability cross-check compare against a live `vault/files/` belt-and-suspenders manifest sharing the same UID (previously dead code — the record shape had no `kind` for it to compare against at all).

---

## Guarded transitions enforced at mount (a1f7c750, executed by `tropo-mount.py`)

| Transition | Enforcement at the gate |
|---|---|
| Second mount of an already-present `vault_uid` | REFUSED unless `--force-remount` (AC-5, one-clone-per-vault-UID) |
| `contract` narrowing (dropped `registered_types` / downgraded `capsule_versions` entry / dropped `capabilities`) without a `manifest_version` bump | REFUSED |
| `contract` narrowing WITH a `manifest_version` bump but no `--consent` on the re-mount | REFUSED (re-consent for the delta) |
| `contract` widening (new `capabilities` added) without `--consent` on the re-mount | REFUSED (consent must cover the new capability_set) |
| Unqualified capability name colliding with a reserved OS/private capability name | REFUSED (dependency-confusion defense, AC-2) |
| Mount-path not a resolvable git commit | REFUSED (AC-4, no floating/unpinned mounts) |
| Executable capabilities declared with no `--consent` | REFUSED, nothing written (AC-3) |

`kind` change after `active`, and `audience` widening/narrowing, are manifest-authoring-side guarded transitions (a1f7c750 §Guarded transitions) enforced by the governed-write gate on the manifest itself (see `check_vault_manifest_governed_write_gate` in `vault/tools/tropo-validate.py`) — not by `tropo-mount.py`, which only sees the manifest at mount time, not across its authoring history.

---

## Example Record

```json
{
  "schema_version": 1,
  "vaults": {
    "7c3a8e91": {
      "vault_uid": "7c3a8e91",
      "resolved_commit": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      "manifest_version": "1.2.0",
      "contract_hash": "9f8e7d6c5b4a3928170615243342516071829384756afedcba0918273645fe",
      "contract": {
        "registered_types": ["task", "decision", "document"],
        "capsule_versions": {"core": "1.4", "task": "1.1"},
        "capabilities": ["7c3a8e91:daily-digest"]
      },
      "consent": {
        "consented": true,
        "consented_by": "mike",
        "consented_at": "2026-07-08T14:02:11Z",
        "capability_set": ["7c3a8e91:daily-digest"]
      },
      "name_prefix": "7c3a8e91",
      "mounted_at": "2026-07-08T14:02:11Z",
      "mounted_by": "mike",
      "mount_path": "/Users/mike/git/tropo-studios/other-studio",
      "manifest_kind": "knowledgebase"
    }
  }
}
```

---

## Rationale Summary

**Why JSON, not JSONL:** the compose-lockfile is read/written as one coherent studio-wide state (all mounts composed together), not appended-to line-by-line like the vault index — a single JSON document with a keyed `vaults` map matches the access pattern (look up / update one vault-UID's record) and matches the `package-lock.json` / `Cargo.lock` prior art a stranger already recognizes as "a lockfile."

**Why store the full `contract` block, not just its hash:** a hash alone can prove "something changed" but not "what narrowed" — the mount-gate's re-consent enforcement (AC-6) needs a real structural diff to name the dropped type / downgraded capsule version in its refusal message, per this studio's discipline of specific, never-bare refusals.

**Why `consented_at`/`mounted_at` are recorded on disk, not held in-process:** the whole point of "executable-consent as a governed write, not a runtime toggle" (bc25583d §6) is that the trust decision is auditable and survives a reboot — an in-memory flag would not.

---

## Refs

- **Dev-spec:** `vault/files/409ef1cc.md` — Mount-gate + compose-lockfile + per-vault-root manifest governed-write gate (ADR-051 Fork 2)
- **ADR-051:** `vault/files/18059aef.md`
- **vault.capsule (manifest type):** `vault/capsules/tropo-vault.capsule.md`
- **Vault Index Schema (style precedent):** `.tropo/schema/vault-index-schema.md`
- **Mount-gate tool:** `vault/tools/tropo-mount.py`

---

*Compose-Lockfile Schema v1 | Locked | Talos T26 | 2026-07-08*
*"One record per mounted vault. One pin per record. The lockfile is the composition."*
