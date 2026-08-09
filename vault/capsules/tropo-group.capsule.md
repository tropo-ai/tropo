---
uid: e27250db
name: group
type: capsule-definition
capsule_kind: instance-type
extends: core
version: 1.0
template_enforced_from: '2026-07-18'
template_enforced_from_note: 'ADDED 2026-07-31 per core.capsule v1.9 §Governance Rule 11 (OPTIONAL `template_enforced_from`). Value is the date THIS capsule''s §Template leg was authored, derived from the first commit introducing the ## §Template heading in this file and cross-checked against this capsule''s own changelog/amendment note. Declares the mint-time contract''s start so instances predating the scaffold are not judged against it. One-line enforcement-scope metadata; no schema/enum/state-machine/template change, so no version bump (the extraction_scope sweep precedent).'
tier: os
author: argus-a134
created: 2026-07-18
modified: 2026-07-18
modified_by: argus-a134
status: locked           # locked 2026-07-19 (Mike-walked GO) — authorizing contract dev-spec 0bfa771d; 3 legs present (group-authority-v1 schema + §Template b933eafb + §Validation Checks)
locked_by: mike-maziarz
locked_at: '2026-07-19'
locked_walk_by: argus-a135
schema_version: 2
governed_by: 222873b9
aligned_with:
  - "0bfa771d"          # B4a dev-spec — the authorizing contract
  - "252534fe"          # B4a cycle brief — the Personal-audience bootstrap group
subsystem_hub:
  - 8dd772a0
---

# group — Capsule Definition v1.0 (the governed audience group)

**Relations**

| Relation | Target |
|---|---|
| Governed by | capsule-definition meta (222873b9) |
| Authorized by | B4a dev-spec (0bfa771d) |
| Extends | `core` |

*A group is a governed, named set of principals with declared containment. A vault
manifest's `audience` resolves to exactly one live group UID — never an inline member
list, never a slug, never a `team`/`team-def`. This capsule governs the group source
lifecycle: birth as an indexed draft, one-shot finalization, and signed publication into
the deterministic registry projection.*

## Intent

B4a makes one product sentence mechanically true (dev-spec 0bfa771d §Outcome): *a Tropo
audience is a governed, named group whose membership and declared containment are resolved
locally and deterministically; a vault manifest may name only a live, resolvable group
UID.* The type earns its abstraction because an audience is a distinct concern from a
principal, a role, or a team operation: `extends: core` (never `team`, `team-def`, or
`entity`) is locked (dev-spec §Group contract) so a group carries no signing, command,
activation, role, or team-operation semantics. It is an audience — a set with declared
containment — and nothing more.

## Required Frontmatter

| Field | Type | Constraint |
|---|---|---|
| `type` | literal | Must be `group`. |
| `slug` | string | Lowercase kebab-case; **globally unique and immutable**. |
| `title` | string | Human-readable; one line. |
| `description` | string | The group's purpose. |
| `owner` | UID | An active principal UID resolved through the pinned portable principal directory. |
| `members` | array of UIDs | **Non-empty**, duplicate-free, canonicalization-sorted; each resolves to an active principal. |
| `includes_groups` | array of UIDs | Duplicate-free; rejects unknown, inactive, self, and cyclic edges. May be empty (`[]`). |
| `status` | enum | `draft` \| `active`. |
| `version` | integer | `1` at birth (no increment in B4a). |
| `semantic_hash` | string \| null | `null` while `draft`; lowercase SHA-256 over the canonical semantic bytes once `active`. |

**Semantic canonicalization v1:** canonical UTF-8 JSON plus LF, with the **fixed** key
order `uid, type, slug, title, description, owner, members, includes_groups, status,
version` (this order is not sorted). UID lists (`members`, `includes_groups`) sort
lexicographically. YAML formatting and provenance fields are non-semantic. `semantic_hash`
is lowercase SHA-256 over exactly those canonical bytes.

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| *(none in B4a)* | — | A B4a group carries no optional semantic fields. Successor / migration / role fields are explicitly deferred to B4b (dev-spec §Explicit B4b exclusions). |

## State Machine

```
draft → active        (one-shot; the single legal birth value is `draft`)
```

**Status enum:** `status:` ∈ {draft, active}. The transition happens exactly once, at
signed finalization. Active semantic fields are immutable. B4a has NO mutate, deprecate,
successor, grant, revoke, or migration transition.

| Status | Meaning |
|---|---|
| `draft` | Authored but not finalized; absent from every registry and resolver. |
| `active` | Signed generation committed; visible in the registry projection; semantics frozen. |

## Governance Rules

1. **`slug` is globally unique and immutable.** A collision refuses `GROUP_SLUG_DUPLICATE`.
2. **`owner` and every `member` resolve through the pinned active principal directory.** Unresolved/inactive → `PRINCIPAL_UNRESOLVED`.
3. **`members` is non-empty, duplicate-free, and canonicalization-sorted.**
4. **`includes_groups` rejects unknown, inactive, self, and cyclic edges** (`GROUP_CYCLE` for a cycle/self-edge).
5. **Drafts and unsigned candidates are absent from every registry and resolver.** Membership is visible only after signed finalization.
6. **`status` transitions exactly once, `draft → active`; active semantic fields are immutable** (`GROUP_IMMUTABLE` on an attempted active semantic mutation).
7. **`extends: core` only** — any `team`/`team-def`/`entity` lineage or signing/role/command/activation semantics is a violation.
8. **Containment defines order, not member equality.** `can_reference(A, B)` is true exactly when B equals A or is declared wider than A; equal member snapshots without a declared `includes_groups` edge remain incomparable.
9. **No B4b operations in a B4a group** — no grant/revoke, no version increment beyond birth, no successor, no audience migration, no role group.

## Validation Checks

1. **[enforced]** `type: group` recognized; lineage is `core` (reject `team`/`team-def`/`entity`).
2. **[enforced]** Required frontmatter present (slug, title, description, owner, members, includes_groups, status, version, semantic_hash).
3. **[enforced]** `slug` lowercase-kebab + globally unique across active groups (`GROUP_SLUG_DUPLICATE`).
4. **[enforced]** `members` non-empty, duplicate-free, sorted; each resolves to an active principal (`PRINCIPAL_UNRESOLVED`).
5. **[enforced]** `includes_groups` duplicate-free; no unknown/inactive/self/cyclic edge (`GROUP_CYCLE`).
6. **[enforced]** `draft` ⇒ `semantic_hash: null`; `active` ⇒ `semantic_hash` matches the canonical semantic bytes.
7. **[enforced]** Active semantic fields immutable across `draft → active` (current-state shape at v1.0; cross-commit diff deferred, same precedent as `vault.capsule` check 3).
8. **[enforced at resolve]** Drafts/unsigned candidates never appear in the registry projection or resolver (Rule 5).
9. **[target vNext]** B4b guarded transitions (grant/revoke/migration) — honor-system until B4b lands the ceremony.

## §Template

*Mint-stamped scaffold per the Template-Leg Contract (b933eafb). `mint file --type group`
stamps a `draft` group; the one-shot finalizer ([`tropo-finalize-group.py`](../tools/tropo-finalize-group.py))
seals it and the signed installer ([`tropo-group-authority.py`](../tools/tropo-group-authority.py) `install`)
publishes it into the registry projection. Drafts are never resolver-visible.*

```yaml
---
uid: <MINTED>
type: group
slug: <REPLACE-lowercase-kebab-globally-unique>
title: <REPLACE-human-title>
description: <REPLACE-purpose>
owner: <REPLACE-active-principal-uid>
members:
  - <REPLACE-active-principal-uid>
includes_groups: []
status: draft
version: 1
semantic_hash: null
created: <YYYY-MM-DD>
created_by: <author-slug>
modified: <YYYY-MM-DD>
modified_by: <author-slug>
schema_version: 2
---

# <REPLACE-title> — Group

<!-- REPLACE: one line on who this audience is and why it exists -->
```

## Inheritance

Extends `core` (ee814120), the instance-frontmatter floor. It deliberately does NOT
extend `team`, `team-def`, or `entity` — a group is an audience, not a role, a team
operation, or a principal-grounding entity. Consumers: `vault.capsule` (a1f7c750)
`audience` resolves to a group UID governed here; `group_authority` signs the group
corpus; `group_registry.py` projects the deterministic JSONL + resolver over active
groups; `audience_context.py` is the single adapter every caller consumes.

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-07-18 | Initial DRAFT — the governed audience-group type. Authored per B4a dev-spec 0bfa771d §Group contract. | argus-a134 |

*group capsule definition | DRAFT v1.0 | Argus A134 | 2026-07-18*
*"A group is an audience: a named set of principals with declared containment. Not a role. Not a team. Not a principal."*
