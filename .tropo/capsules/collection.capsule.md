---
subsystem_hub:
  - "2d083137"
uid: c04e7a91
name: "collection"
type: capsule-definition
extends: core
version: 1.1
supersedes_version: "1.0"
tier: os
author: tropo
created: 2026-04-16
modified: 2026-06-09
modified_by: argus-a105
status: locked
meta_status_rollup:
  in-progress: [build, active]
  done: [done]
meta_status_rollup_note: "argus-a104 2026-06-08 — rollup completion per the unified lifecycle knot (move 2, 9f6a1379); additive lock-break."
schema_version: 2
governed_by: 222873b9
aligned_with: c01ec700 # collection-ref.capsule v3.0 — paired pointer-vs-container primitive
composes_with: c01ec700 # collection (manifest) ↔ collection-ref (ledger pointer); same UID, two homes
pattern_family: c01ec700 # collection / collection-ref pair — manifest vs pointer separation
---

# collection — Capsule Definition v1.1

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [collection-ref.capsule (c01ec700)](collection-ref.capsule.md) |
| Pattern family | [collection-ref.capsule (c01ec700)](collection-ref.capsule.md) |
| Extends | `core` |
| Composes with | [collection-ref.capsule (c01ec700)](collection-ref.capsule.md) |

*A membership roster — a maintained list of vault entries that share a common context. Different from `collection-ref` (a pointer) — this is the actual manifest.*

*v1.1 (2026-04-25, Argus A34) adds §Studio — Shop Signage + Relations Header per Stream 3 D3.2 of v1.4. v1.0 lock 2026-04-16 preserved. UID `c04e7a91` preserved across the amendment.*

## Intent

A collection holds the membership roster for a specific filtered view of a project's contents. Collections are how projects expose their members to navigation and query systems without requiring full graph traversal.

**Before creating a collection:** does a collection already exist for this view? Check the project's existing collection-refs. Duplicate collections create drift.

---

## Required Frontmatter

| Field | Type | Constraint |
|-------|------|-----------|
| `title` | string | ≤ 100 chars. Describes what this collection contains. |
| `description` | string | ≤ 120 chars |
| `owner` | string | The agent responsible for maintaining this roster |
| `stage` | enum | `build` (active) or `done` (closed) |
| `state` | enum | `active` or `archived` |
| `member_of` | array of UIDs | The project this collection belongs to. Required. |
| `filter` | string | The filter rule that defines membership (e.g., "type: task", "type: task AND stage: active") |

---

## State Machine

```
build → done → state: archived
```

Collections are almost always `stage: build` — they are living rosters. A collection moves to `done` only when its parent project closes.

---

## Governance Rules

1. **Collections are maintained, not generated.** When members are added to or removed from a project, the collection manifest must be updated.

2. **One collection per filter.** Do not create two collections with the same filter for the same project.

3. **Collections follow their project.** When a project is archived, its collections should also be archived.

---

## Validation Checks

1. `member_of:` present, non-empty array
2. `filter:` present, non-empty string
3. `stage:` is one of: `build`, `done`
4. `state:` is one of: `active`, `archived`

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author or maintain a collection.*

**Tools available:**
- `ls collections/` — survey the manifest folder; `master/` for vault-wide rosters; `projects/` for per-project rosters
- `ls collections/master/*.collection.md` — survey shipped master rosters before authoring a duplicate (Rule 2 one-collection-per-filter discipline)
- `vault/00-index.jsonl` — grep `type: collection-ref` to find existing pointer entries pairing with manifest files
- `.tropo-studio/registries/registry.jsonl` — collection-refs surface here; manifests live outside the registry as data files
- Reference instances: [`collections/subsystem-hubs.collection.md`](../../collections/subsystem-hubs.collection.md), [`collections/master/all-active-tasks.collection.md`](../../collections/master/all-active-tasks.collection.md), [`collections/master/all-design-specs.collection.md`](../../collections/master/all-design-specs.collection.md), [`collections/master/all-decisions.collection.md`](../../collections/master/all-decisions.collection.md), [`collections/master/all-boards.collection.md`](../../collections/master/all-boards.collection.md)

**Skills:**
- `register-collection.skill.md` *(forthcoming v1.5)* — author manifest at `collections/<path>/<name>.collection.md` FIRST, then create paired collection-ref ledger entry at `vault/files/<uid>.md` with the SAME UID (per [collection-ref.capsule v3.0 Rule 2 (c01ec700)](collection-ref.capsule.md))
- `audit-collection-membership.skill.md` *(forthcoming v1.5)* — verify `filter:` matches actual membership; flag drift between declared filter + maintained roster
- Existing live action: [`create-collection.action.md`](../../.tropo/actions/create-collection.action.md) — atomic two-file write (manifest + ledger ref), per [action.capsule v1.1 (9b7f5e34)](action.capsule.md)

**Procedures:**
- **Author a collection** — capture: choose a filter (e.g., `"type: task AND stage: active"`); author the manifest at `collections/<scope>/<name>.collection.md` with REQUIRED frontmatter (`title`, `description`, `owner`, `stage: build`, `state: active`, `member_of`, `filter`); author the paired collection-ref at `vault/files/<uid>.md` with the SAME UID (per collection-ref capsule Rule 2)
- **Add-to / maintain membership** — Rule 1 (collections are MAINTAINED, not generated): on member add/remove from the parent project, update the manifest's roster
- **Compose with the project** — Rule 3 follow-the-project: when project archives, archive the collection (`state: archived`)
- **Verify** — confirm `member_of:` resolves to a project, `filter:` is non-empty, `stage:` ∈ {`build`, `done`}, `state:` ∈ {`active`, `archived`}
- **Compose with collection-ref** — manifest content edits happen HERE; the paired ledger collection-ref is pointer-only (per collection-ref Rule 3); never edit collection content via the ref entry
- **Tag with `collection_type:` (in collection-ref's frontmatter)** — `manual` (hand-maintained list) or `dynamic` (filter-evaluated by query engine) per collection-ref v3.0 Decision 6 enum
- **Close — `stage: build → done`** — when the parent project closes; the collection is no longer accumulating but remains navigable
- **Archive — `state: active → archived`** — mirrors the parent project's archival per Rule 3

**Rules (at-a-glance):**
1. **Collections are maintained, not generated** — when members change, the manifest gets updated (manual collections); dynamic collections re-evaluate their filter
2. **One collection per filter** — duplicate manifests with the same filter for the same project are violations
3. **Collections follow their project** — when the project archives, the collection archives (state propagation)

**Pitfalls:**
- **Collection without paired collection-ref** — half-shipped; the manifest is invisible to ledger queries until the ref is registered
- **Collection-ref UID ≠ manifest UID** — collection-ref Rule 2 violation; same logical collection, two UIDs; downstream drift
- **Editing collection content via the Vault ref** — collection-ref Rule 3 violation; edit the manifest, not the ref
- **Two collections with the same `filter:` for the same project** — Rule 2 violation; consolidate
- **Empty `member_of:`** — Validation Check 1 violation; collections must scope to at least one project
- **Empty `filter:` string** — Validation Check 2 violation; the filter is the membership rule
- **Project archived but collection still `state: active`** — Rule 3 violation; archive the collection in the same commit
- **`stage:` outside {`build`, `done`}** — Validation Check 3 violation; collections do NOT have `draft` or `superseded` states
- **`state:` outside {`active`, `archived`}** — Validation Check 4 violation
- **Stale `collection_path:` on the paired ref** — collection-ref Rule 1 / orphan repair; if the manifest moves, update the ref or archive

**Worked examples:**
- [Subsystem Hubs — Active Roster (4c1f8a26)](../../collections/subsystem-hubs.collection.md) — manual collection, hierarchical render; the live hub roster referenced by [subsystem-hub.capsule v1.3 (8a4e21c5)](subsystem-hub.capsule.md). Path moved from `collections/master/` to `collections/` in v1.7 Stream A2 (2026-05-05) per v1.3 cite alignment; UID preserved.
- [All Active Tasks (Ledger) (7b92c4e1)](../../collections/master/all-active-tasks.collection.md) — `filter: "type: task AND state: active"`; canonical task roster
- [All Design Specs (Ledger) (a4d8f3b2)](../../collections/master/all-design-specs.collection.md) — vault-wide design-spec inventory
- Folder hierarchies under `collections/projects/` — per-project rosters demonstrating scope-narrowed `filter:` strings + `member_of:` to specific projects

**Go next:**
- Paired pointer capsule → [collection-ref.capsule v3.0 (c01ec700)](collection-ref.capsule.md) — UID-matched vault entry; Rule 2 enforces same-UID-two-homes
- Atomic creation action → [`create-collection.action.md`](../../.tropo/actions/create-collection.action.md) — two-file write per [action.capsule v1.1 (9b7f5e34)](action.capsule.md)
- Project scope (the parent) → [project.capsule v2.1 (34e4cb0b)](project.capsule.md)
- Live master rosters → [`collections/master/`](../../collections/master/)
- Live project rosters → [`collections/projects/`](../../collections/projects/)
- Folder governance → `collections/AGENTS.md`
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-04-16 | Initial version locked. Membership roster manifest — paired with collection-ref ledger pointer. REQUIRED frontmatter (`title`, `description`, `owner`, `stage`, `state`, `member_of`, `filter`), 2-state state machine (`build` → `done`), 3 governance rules (maintained-not-generated, one-per-filter, follow-the-project). | tropo |
| 1.1 | 2026-04-25 | **Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop).** Added §Workshop — Shop Signage section (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next) per the v3 capsule shop-signage pattern. Added Relations Header right after H1 — clickable navigation surface mirroring frontmatter (governed_by, aligned_with collection-ref, composes_with collection-ref, pattern_family pair, live registries, project + subsystem-hub composition). Frontmatter `aligned_with: c01ec700` + `composes_with: c01ec700` + `pattern_family: c01ec700` declared. No semantic changes to §Required Frontmatter / §Validation Checks / §Governance Rules / §State Machine. UID preserved at c04e7a91. | argus-a34 |

---

*collection capsule definition | LOCKED v1.1 | Argus A34 | 2026-04-25 (Stream 3 D3.2 — §Studio + Relations Header); v1.0 lock 2026-04-16 by Tropo OS preserved in git history*
*"The collection IS the manifest. The collection-ref POINTS at it. Same UID, two homes."*
