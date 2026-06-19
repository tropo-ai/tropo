---
uid: c01ec700
name: "collection-ref"
type: capsule-definition
extends: core
version: 3.0
supersedes_version: "2.0"
tier: os
author: tropo
created: 2026-04-10
modified: 2026-04-24
modified_by: argus-a33
status: locked
enforced_enums:
  status:
    canonical: [build, done]
    aliases: {active: build}
meta_status_rollup:
  in-progress: [build, active]
  done: [done]
schema_version: 2
governed_by: 222873b9
aligned_with: 8b3f1d92   # Tropo Work v3 Architecture Specification (Decision 6)
pattern_exemplar: d0c00001   # document.capsule — collection-ref is patterned on document per v3 Decisions 3 + 6; adds pointer-vs-container discipline + UID-match-to-collection-file invariant + type-enum simplified from 3 to 2 in v3
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# collection-ref — Capsule Definition

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Tropo Work v3 — Architecture Specification (8b3f1d92)](../../vault/files/8b3f1d92.md) |
| Pattern exemplar | [document.capsule (d0c00001)](document.capsule.md) |
| Extends | `core` |

*A pointer entry that registers a collection in the Vault. The actual collection file lives in `collections/`; this entry tells the Vault that the collection exists.*

## Intent

Collections live outside the Vault, in `collections/` with arbitrary sub-hierarchy. But the Vault needs to know that a collection exists so it can be discovered, queried, and referenced. The `collection-ref` type is a thin pointer entry: it registers the collection's UID, name, and path in the vault index without storing the collection's contents.

This keeps the collection-as-human-organization principle intact (collections live where humans put them) while making collections discoverable by query (the Vault knows what collections exist).

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `description` | string | ≤ 120 chars; the collection's purpose |
| `collection_path` | string | path from vault root to the collection file |
| `collection_type` | enum | one of `manual`, `dynamic` (simplified from 3-value enum per v3 Decision 6; `ai-suggested` was a variant of dynamic — LLM query source is declarable in the collection file itself, doesn't need its own top-level enum value) |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `member_count` | integer | cached count of members in the collection |
| `last_synced` | ISO 8601 date | when this ref was last verified against the actual collection file |

## State Machine

**Canonical status enum:** `status:` ∈ {build, done}

*v3 amendment (2026-04-24, v2.0 → v3.0): field renamed `stage:` → `status:` per v3 Decision 4 + 6. Values (`build`, `done`) preserved — this is a rename, not a semantics change.*

```
build → done → state: archived
```

| Status | State | Meaning |
|-------|-------|---------|
| `build` | `active` | Collection exists and is current |
| `done` | `active` | Collection closed but still navigable |
| any | `archived` | Collection no longer maintained |

## Governance Rules (in addition to core)

1. **The collection_path must point to an actual file.** If the collection file is moved or deleted, the collection-ref must be updated or archived. The vault steward audits this.
2. **The UID of the collection-ref must match the UID inside the collection file's frontmatter.** A collection has one UID; the ref and the file share it.
3. **Modifying the collection's contents** is done by editing the actual collection file in `collections/`, NOT by editing this entry. This entry is a pointer.

## Validation Checks (run at check-in)

In addition to core checks:

1. Description length ≤ 120 chars
2. collection_path is a valid filesystem path (relative to vault root)
3. collection_type is one of `manual`, `dynamic` (v3 Decision 6 simplification; was 3 values in v2.0)
4. `status:` is one of: `build`, `done` (renamed from `stage:` per v3 Decision 4)
5. `state:` is one of: `active`, `archived`

## Inheritance

Extends `core`. Inherits all core rules.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you register a collection.*

**Tools available:**
- `vault/00-index.jsonl` — find existing collection-refs before creating a duplicate
- `collections/` directory — the actual collection files live here (manual YAML manifests or dynamic query specs; LLM-generated query sources declared in the collection file itself, not a separate enum value per v3 Decision 6)
- `vault/files/<uid>.md` writer — the ref lives as a flat ledger entry; its UID MUST match the UID inside the collection file's frontmatter (Rule 2)

**Skills:**
- `register-collection.skill.md` *(forthcoming v1.5)* — creates ref + collection file atomically with UIDs matched
- `audit-collection-refs.skill.md` *(forthcoming v1.5)* — vault steward periodically verifies `collection_path:` still resolves to a file

**Procedures:**
- Registration workflow — author the collection file in `collections/<path>` FIRST, then author the `collection-ref` with the same UID; set `collection_path:` to vault-relative path; set `collection_type:` (manual / dynamic — v3 Decision 6 simplified from 3-value to 2-value enum)
- Content editing — **edit the collection file, never this ref entry** (Rule 3; the ref is a pointer, not a container)
- Orphan repair — if the collection file is moved or deleted, update `collection_path:` or archive the ref (Rule 1; vault steward audits)

**Rules (at-a-glance):**
1. `collection_path:` must point to an actual file — orphan refs get repaired or archived
2. The ref's UID matches the UID inside the collection file's frontmatter — one UID per collection, two homes
3. Content edits happen in the collection file; this ref is pointer-only
4. `collection_type:` is one of: `manual`, `dynamic` (v3 Decision 6 — dropped `ai-suggested`)
5. `status:` = `build` (live) or `done` (closed but navigable); `state:` = `active` or `archived`. Renamed from `stage:` in v3.0 per Decision 4.

**Pitfalls:**
- Editing this ref's body to change collection content → Rule 3 violation; edit the collection file instead
- Creating a ref with a UID different from the collection file's frontmatter UID → Rule 2 violation; two UIDs for one collection, downstream drift
- Leaving `collection_path:` stale after the collection file is moved → Rule 1 orphan; queryers hit a dead path
- Using `collection-ref` as a collection itself → confuses pointer-vs-content; the ref doesn't hold members
- Choosing `collection_type: dynamic` when the collection is actually a hand-maintained manual list → misleads queryers about maintenance cadence

**Worked examples:**
- [417898d0](../../vault/files/417898d0.md) — "All Decisions" collection-ref; every ADR in number order with supersession chains visible (Vela-owned, primary governance index)
- [ffc87c04](../../vault/files/ffc87c04.md) — v0.3 Compliance project primary-members collection-ref; scoped to one project's member roster (Metis-owned)

**Go next:**
- Actual collections live under → `collections/` (outside the Vault, human-organized hierarchy)
- Collections commonly enumerate projects → [project.capsule v2.3 (34e4cb0b)](project.capsule.md)
- Collections may enumerate decisions → [decision.capsule (179d74e9)](decision.capsule.md)
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1 | 2026-04-10 | Initial version locked. Thin pointer entry registering a collection file in the Vault; pointer-vs-container discipline. | tropo |
| 2.0 | 2026-04-16 | (v2.0 implicit in prior frontmatter; reconciled at v3.0 amendment.) | tropo |
| 3.0 | 2026-04-24 | v3 amendment: `stage:` field renamed → `status:` per v3 Decisions 4 + 6. `collection_type:` enum simplified from 3 values (`manual`, `dynamic`, `ai-suggested`) to 2 (`manual`, `dynamic`) — LLM query source declarable in collection file itself; no separate top-level enum value needed. `pattern_exemplar: d0c00001` declared per Decision 3 — collection-ref is patterned on document.capsule with pointer-vs-container discipline layer. UID preserved at c01ec700. | argus-a33 |

---

*collection-ref capsule definition | LOCKED v3.0 | amended 2026-04-24 by argus-a33; v1/v2.0 lock April 10, 2026 by Tropo preserved in git history | UID preserved at c01ec700*
*"A pointer. Not a container. UID matches the collection file's frontmatter; content lives there."*
