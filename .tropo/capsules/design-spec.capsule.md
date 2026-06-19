---
uid: de5160c0
name: "design-spec"
type: capsule-definition
extends: core
version: 2.1
supersedes_version: "2.0"
tier: os
author: tropo
created: 2026-04-10
modified: 2026-06-09
modified_by: argus-a105
status: locked
enforced_enums:
  status:
    canonical: [design, draft, specify, done, locked, archived]
    aliases: {ideate: design}
meta_status_rollup:
  to-do: [design, draft, ideate]
  in-progress: [specify]
  done: [done, locked, archived]
meta_status_rollup_note: "argus-a104 2026-06-08 — rollup completion per the unified lifecycle knot (move 2, 9f6a1379); additive lock-break."
schema_version: 2
governed_by: 222873b9
aligned_with: a7f2e9c4   # arch-spec.capsule v2.1 — heavier formal-contract sibling
pattern_family: a7f2e9c4 # arch-spec.capsule (formal contract sibling); design-spec is the lighter narrative form
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# design-spec — Capsule Definition v2.1

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [arch-spec.capsule (a7f2e9c4)](arch-spec.capsule.md) |
| Pattern family | [arch-spec.capsule (a7f2e9c4)](arch-spec.capsule.md) |
| Extends | `core` |

*A design specification — an architectural document that defines how something works. Goes through draft, gets locked, may eventually be superseded.*

*v2.1 (2026-04-25, Argus A34) adds §Studio — Shop Signage + Relations Header per Stream 3 D3.2 of v1.4. v2.0 lock preserved. UID `de5160c0` preserved across the amendment.*

## Intent

Capture architectural decisions and design intent in a versioned, reviewable form. Design specs are the primary way the crew records "this is how X is built and why." Once locked, a design spec becomes a contract — changes require either an amendment or supersession.

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `description` | string | ≤ 120 chars; one-line summary |
| `version` | string | semantic version (e.g., `0.1`, `1.0`) |
| `author` | string | who drafted the spec |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `reviewer` | string | Who reviewed the spec before lock |
| `locked_by` | string | Who locked the spec (required when status = locked) |
| `locked_at` | ISO 8601 date | When the spec was locked |
| `supersedes` | UID | If this spec replaces a prior spec |
| `superseded_by` | UID | If this spec has been replaced |
| `refs` | array of UIDs | Related entries |
| `consistent_with` | array | External principles or specs this spec aligns with |

## State Machine

```
specify → done → (superseded: done + state: archived)
```

**Canonical status enum:** `status:` ∈ {design, draft, specify, done, locked, archived}

| Stage | State | Meaning |
|-------|-------|---------|
| `specify` | `active` | Under active design; not yet committed |
| `done` | `active` | Locked — approved and committed; treated as a contract |
| `done` | `archived` | Superseded by a newer spec |

### Valid transitions

- `specify` → `done` (locking authority only)
- `done` → `done, state: archived` (when superseded; requires `superseded_by:` field)

### Invalid transitions

- `done` → `specify` (cannot un-lock; create a new draft)
- Editing the body of a locked spec (frontmatter `superseded_by` may be updated; body is frozen)

## Governance Rules (in addition to core)

1. **Only the locking authority locks.** Locking is a governance act, typically performed by Mike (in Argo) or the equivalent vault principal. The author cannot lock their own draft.
2. **Locked specs are immutable in their content.** Once locked, the spec body cannot be edited. Amendments are made by drafting a new version (incrementing the version field) or superseding.
3. **Supersession requires both directions.** If spec B supersedes spec A, then spec A must have `superseded_by: B-uid` and spec B must have `supersedes: A-uid`. The vault steward audits this.
4. **A spec must have a `How to Validate` section** in its body before it can be locked (per Rule 10 in `design/AGENTS.md`).
5. **Version must increment between drafts.** Two drafts with the same version is a versioning violation.

## Validation Checks (run at check-in)

In addition to core checks:

1. Description length ≤ 120 chars
2. Version field is present and follows semantic versioning convention
3. Author field is present
4. `status:` is one of: `specify`, `done`
5. `state:` is one of: `active`, `archived`
6. If `status: done` and `state: active`: `locked_by` and `locked_at` fields are present
7. If `status: done` and `state: active`: entry body contains a `## How to Validate` section
8. If `state: archived`: `superseded_by` field is present and references a valid UID
8. If `supersedes` is present, the referenced UID exists and has `superseded_by` pointing back to this entry

## Inheritance

Extends `core`. Inherits all core rules.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author a design-spec.*

**Tools available:**
- `vault/00-index.jsonl` — grep `type: design-spec` for live specs; check for prior specs covering the same surface before authoring (drift prevention)
- `vault/00-index.jsonl` — grep `type: design-brief` for briefs upstream of this spec
- `.tropo-studio/registries/registry.jsonl` — verify cross-references resolve (`refs:`, `consistent_with:`, `supersedes:` UIDs)
- Reference instances: [Playbook Executor State Machines (12d8918c)](../../vault/files/12d8918c.md) (`stage: done`, locked); [Tropo Work Architecture v0.3 (2d016ecf)](../../vault/files/2d016ecf.md); [Playbook → Task Integration Spec (468783eb)](../../vault/files/468783eb.md)
- Sibling capsule for heavier specs: [arch-spec.capsule v2.1 (a7f2e9c4)](arch-spec.capsule.md) — when the spec needs 5 REQUIRED body sections + non-empty `derived_from:`, prefer arch-spec

**Skills:**
- `author-design-spec.skill.md` *(forthcoming v1.5)* — scaffold the spec body with §How to Validate as the lock prerequisite (Rule 4)
- `lock-design-spec.skill.md` *(forthcoming v1.5)* — verify §How to Validate present, set `locked_by` + `locked_at`, flip `stage: specify → done`

**Procedures:**
- **Author** — capture the architectural decision in spec form; declare `description` (≤120 chars), `version` (semver), `author`; start at `stage: specify`, `state: active`
- **Verify before lock** — confirm body contains `## How to Validate` section per Rule 4; ensure version increments cleanly across drafts (Rule 5)
- **Lock** — locking authority (Rule 1: NOT the author) sets `locked_by` + `locked_at`, flips `stage: specify → done`; spec body becomes immutable (Rule 2)
- **Supersede** — author successor at `stage: specify`; on successor lock, atomically set predecessor `state: archived` + `superseded_by: <successor-uid>` AND successor `supersedes: <predecessor-uid>` (Rule 3 bidirectional pair)
- **Amend** — Rule 2 disallows body edits on locked specs; minor corrections require a new version (decimal bump) drafted as a new file; major changes go through supersession
- **Choose between design-spec and arch-spec** — design-specs are lighter, narrative, single-section freedom; arch-specs add 5 REQUIRED body sections (Thesis / Architecture / Required Contracts / etc.) + non-empty `derived_from:` invariant + locked-contract rigor. For governance-load-bearing artifacts, prefer arch-spec; for design notes that document a decision, design-spec suffices

**Rules (at-a-glance):**
1. **Only the locking authority locks** — author cannot self-lock; locking is a governance act
2. **Locked specs are immutable in content** — body frozen at `stage: done`
3. **Supersession requires both directions** — bidirectional `supersedes:` ↔ `superseded_by:` pair; vault steward audits
4. **Locked specs MUST contain `## How to Validate`** — body section is a lock prerequisite per `design/AGENTS.md` Rule 10
5. **Version must increment between drafts** — two drafts at the same version is a versioning violation

**Pitfalls:**
- **Author self-locking** — Rule 1 violation; route lock through the locking authority (typically Mike for Argo, vault principal for downstream vaults)
- **Editing the body of a locked spec** — Rule 2 violation; the only legal post-lock body change is `superseded_by:` frontmatter; for content changes, draft a new version or supersede
- **Locking without `## How to Validate`** — Rule 4 / Validation Check 7 violation; the spec lacks the verification surface the lock is supposed to ratify
- **Supersession with one-way pointer** — Rule 3 violation; vault steward audit catches the asymmetry
- **Two drafts at same version** — Rule 5 violation; bump version on every draft revision
- **Description over 120 chars** — Validation Check 1 violation; tighten to one-line summary
- **Missing `superseded_by:` after archival** — Validation Check 8 violation; archived state requires the pointer

**Worked examples:**
- [Playbook Executor — Run and Step State Machines (12d8918c)](../../vault/files/12d8918c.md) — `stage: done`, `state: active`, locked design-spec referenced by playbook-run.capsule v2.1
- [Tropo Work — Architecture Specification (2d016ecf)](../../vault/files/2d016ecf.md) — v0.3 five-object model + note + board capsules; widely-referenced
- [Playbook → Task Integration Spec (468783eb)](../../vault/files/468783eb.md) — playbook-step-to-task-creation specification; cross-cuts playbook + task capsules

**Go next:**
- Heavier sibling → [arch-spec.capsule v2.1 (a7f2e9c4)](arch-spec.capsule.md) — when 5 REQUIRED body sections + locked-contract discipline are needed
- Lighter sibling upstream → [design-brief.capsule (de5181b0)](design-brief.capsule.md) — briefs precede specs; specs formalize what briefs explore
- Plan integration → [project-plan.capsule v1.1 (f7b9c4a2)](project-plan.capsule.md) — plans `derived_from:` design-briefs (and may reference specs in dependencies)
- Folder governance → `design/AGENTS.md` — governs the `design/` folder where specs may also live (Rule 10 cited above)
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-04-10 | Initial version locked. Thin governance for design specifications — frontmatter floor, state machine, supersession rules, How-to-Validate body section as lock prerequisite. | tropo |
| 2.0 | 2026-04-16 | Schema v2 alignment. Frontmatter / validation-check polish; numbering of governance rules + checks formalized. | tropo |
| 2.1 | 2026-04-25 | **Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop).** Added §Workshop — Shop Signage section (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next) per the v3 capsule shop-signage pattern. Added Relations Header right after H1 — clickable navigation surface mirroring frontmatter (governed_by, aligned_with sibling arch-spec, lighter-sibling-upstream design-brief, pattern_family). Frontmatter `aligned_with: a7f2e9c4` + `pattern_family: a7f2e9c4` declared. No semantic changes to §Required Frontmatter / §Validation Checks / §Governance Rules / §State Machine. UID preserved at de5160c0. | argus-a34 |

---

*design-spec capsule definition | LOCKED v2.1 | Argus A34 | 2026-04-25 (Stream 3 D3.2 — §Studio + Relations Header); v2.0 lock preserved in git history; v1 by Tropo OS (April 10, 2026)*
*"The brief explores. The design-spec structures. The arch-spec locks the contract."*
