---
uid: a1f7c750
name: vault
type: capsule-definition
extends: core
version: 1.0
tier: os
author: argus-a127
created: 2026-07-07
modified: 2026-07-07
modified_by: argus-a127
status: draft            # → locked by Argus at forge-write after Mike-walk; ADR-051 is the authorizing decision
schema_version: 2
governed_by: 222873b9
aligned_with:
  - 18059aef            # ADR-051 — the authorizing decision (Fork 1)
  - "32067bea"          # Studio-Identity Primitive — the sibling that prefix_policy REFERENCES
subsystem_hub:
  - 8dd772a0
---

# vault — Capsule Definition v1.0 (the vault-node MANIFEST)

**Relations**

| Relation | Target |
|---|---|
| Governed by | capsule-definition meta (222873b9) |
| Authorized by | ADR-051 (18059aef) — Fork 1 |
| Sibling (referenced, never contained) | Studio-Identity Primitive (32067bea) |
| Extends | `core` |

*A vault is a governed NODE: a folder with a manifest declaring membership, audience,
remote, publish/curation policy, and a product contract. This type governs the manifest
LIFECYCLE. Principal-grounding + the D7 anchor is the SEPARATE `vault-entity` type
(4d6e2f9a) — one per vault-node. New type, not a fold, per ADR-051 Fork 1 (the
don't-overload-a-governed-name discipline of ADR-050).*

## Intent

Every vault is a first-class typed node (Mike lock #1, 5d3ab142 §0). Its manifest is the
mount-time contract a consumer relies on and the source the composed index reads to assign
the segment (= vault-node UID, signed I1, dd16c90c). A studio holds MANY vaults; each has
exactly one manifest. `extends: core` (not `entity`) is deliberate: the manifest is a
composition/product node, not a principal-grounding entity — that lifecycle stays in
`vault-entity`, keeping the two concerns un-overloaded (ADR-051 Fork 1).

## Where instances live

At the **per-vault-root manifest path** (ADR-051 Fork 2), NOT `vault/files/<uid>.md`.
Instances carry `path:` in their index record (mirrors how 32067bea chose
`.tropo/studio-identity.md`). Extending the governed-write gate to cover that path is the
mount-gate / compose-lockfile spec's job (Fork 2, downstream) — this capsule declares the
location; the gate-path extension is a named dependency, not owned here.

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `type` | literal | Must be `vault`. |
| `kind` | enum | `os` \| `personal` \| `team` \| `knowledgebase`. **Immutable after `active`** (Fork 3). |
| `owner` | UID / label | The accountable owner (agent or human). |
| `audience` | UID | A named GROUP-entity reference (5d3ab142 §3). NEVER an inline member list. |
| `remote` | string | The vault's git remote. |
| `prefix_policy` | object | **REFERENCES the studio identity (32067bea) by reference** (ADR-051 §2 sibling boundary); carries the genesis-grandfather rule; NEVER contains a studio prefix. Names `mint_policy` for post-genesis reminting. |
| `publish_policy` | object | Who may publish + attestation requirements. |
| `curation_policy` | object | Gardener / distiller mode + cadence. |
| `curator` | UID / label | A NAMED curator (human or agent). Unowned curation is a confirmed failure mode → rejected. |
| `version` | semver | The manifest/contract version; bumps on contract or curation change. |
| `contract` | object | What a consumer may rely on: registered types present, capsule versions, curation quality signal. |
| `regulated_acceptance` | object | **A1 (ADR-051).** The forward-only-revocation ceiling's owner-acceptance-at-creation, as a NAMED field: `{accepted: bool, accepted_by: <owner-principal-UID>, accepted_at: <date>, ceiling: "forward-only-revocation", note}`. Present always; REQUIRED-populated for regulated deployments (e.g. audit-industry / MindBridge). |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `member_of` | array of UIDs | Parent vault(s) — vaults compose via `member_of` (Mike lock #1). |
| `successor` | UID | REQUIRED when `status: deprecated`; the vault that replaces this one. |
| `founded_at` | ISO 8601 date | When the vault node was created. |
| `federation_parent` | UID | Enclosing federation node, if any. |

## State Machine

```
draft → active → deprecated (successor: required) → (state: archived when no studio mounts it)
```

**Status enum:** `status:` ∈ {draft, active, deprecated, archived}; **`state:`** ∈ {active, archived}.
`status` IS the manifest lifecycle (subsumes Metis's §2 `lifecycle` field).

| Status | State | Meaning |
|---|---|---|
| `draft` | active | Vault exists locally; not yet published-from or mounted-into. |
| `active` | active | First publish/mount has happened; the manifest is a live contract. |
| `deprecated` | active | Superseded; `successor:` REQUIRED (the lockfile/mount world must never see a vault silently vanish). |
| `archived` | archived | No studio mounts it. |

### Guarded transitions — governed ceremonies, not free edits

- **`audience` WIDENING** → publish-gate ceremony + owner sign + re-lint (retroactive disclosure of everything already published — the most dangerous write in the system).
- **`audience` NARROWING** → forward-only revocation event: logged, triggers re-lint; cannot un-clone (the accepted ceiling; recorded via `regulated_acceptance` for regulated owners).
- **`contract` NARROWING** (drop a type / downgrade a capsule version) → BREAKING: MUST bump `version` and is a **mount-gate re-consent trigger**. Contract WIDENING is non-breaking.
- **`curator` / `curation_policy` change** → bumps `version`; surfaces in the mount delta (the quality signal changed).
- **`kind` change** → REJECTED after `active` (Fork 3): a conversion is a NEW vault + a migration changeset, not an in-place flip.

## Governance Rules (in addition to core)

1. **Manifest edits are governed writes.** Each guarded transition above is a governed ceremony, not a free edit.
2. **Sibling boundary (ADR-051 §2).** `prefix_policy` REFERENCES the studio identity (32067bea); a manifest that INLINES a studio prefix is a violation.
3. **`kind` is immutable after `active`** (Fork 3).
4. **`audience` is a group-UID reference**, never an inline member list (5d3ab142 §3).
5. **A named `curator` is required** — unowned curation is rejected.
6. **`status: deprecated` requires a resolvable `successor:`.**
7. **Exactly one manifest per vault-node** (segment = nearest-enclosing manifest; one-clone-per-vault-UID). A studio has MANY vaults — this is NOT a per-studio singleton.
8. **Contract narrowing bumps `version` and triggers mount re-consent.**
9. **`regulated_acceptance` populated at creation for regulated deployments** (A1).

## Validation Checks (the validator must enforce)

1. **[enforced]** `type: vault` recognized as the manifest type, DISTINCT from `vault-entity`.
2. **[enforced]** Required frontmatter present (kind, owner, audience, remote, prefix_policy, publish_policy, curation_policy, curator, version, status, contract, regulated_acceptance).
3. **[enforced — current-state shape at v1.0; cross-version diff deferred]** `kind` ∈ enum; a `kind` change on a manifest whose `status` has ever been `active` (Fork 3) requires git-log inspection across commits and is deferred to a later ratchet, same precedent as `check_article_state_machine_invariants`'s sequential-transition-history note in tropo-validate.py — v1.0 validates current-state shape only.
4. **[enforced]** `prefix_policy` references studio identity (32067bea); REJECT an inlined studio prefix (sibling-boundary, Rule 2).
5. **[enforced]** `audience` resolves to a group entity; REJECT an inline member list (Rule 4).
6. **[enforced]** `curator` present and resolves (Rule 5).
7. **[enforced]** `status: deprecated` ⇒ resolvable `successor:` (Rule 6).
8. **[enforced]** For regulated deployments, `regulated_acceptance.accepted == true` + `accepted_by` resolves to the owner principal (A1).
9. **[target vNext]** Contract narrowing across versions requires a `version` bump + a mount re-consent flag (needs contract-diffing; honor-system until the differ lands).
10. **[enforced at compose]** Exactly one manifest per vault-node (nearest-enclosing; one-clone-per-vault-UID) — no UID under two segment tags.

## Relationship to Other Capsules

- **core** — parent.
- **vault-entity (4d6e2f9a)** — the SEPARATE principal-grounding + D7-anchor type (renamed per ADR-051 Fork 1). One vault-entity per vault-node.
- **team / group** — `audience` resolves to a group entity.
- The **mount-gate / compose-lockfile** spec extends the governed-write gate to the per-vault-root manifest path (Fork 2) and consumes `contract` + `publish_policy` at mount.

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-07-07 | Initial DRAFT — the vault-node manifest type. Authored per ADR-051 Fork 1 (18059aef) from dev-spec 943bb220 §2. | argus-a127 |

*vault (manifest) capsule definition | DRAFT v1.0 | Argus A127 | 2026-07-07*
*"The vault-ENTITY is the vault as a principal. This is the vault as a mountable, contract-bearing node."*
