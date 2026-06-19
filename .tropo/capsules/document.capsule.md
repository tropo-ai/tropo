---
uid: d0c00001
name: "document"
type: capsule-definition
extends: core
version: 3.1
supersedes_version: "3.0"
tier: os
author: tropo
created: 2026-04-10
modified: 2026-06-09
modified_by: argus-a105
status: locked
enforced_enums:
  status:
    canonical: [draft, published, archived, retired, superseded]
    aliases:
      done: published
meta_status_rollup:
  in-progress: [draft]
  done: [published, archived, retired, superseded, done, locked, reviewed]
schema_version: 2
governed_by: 222873b9
aligned_with: 8b3f1d92   # Tropo Work v3 Architecture Specification (document-as-exemplar per Decision 3)
pattern_family: document   # self-declaration; document-like capsules reference this via `pattern_exemplar: d0c00001` per v3 Decision 3
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# document — Capsule Definition

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Tropo Work v3 — Architecture Specification (8b3f1d92)](../../vault/files/8b3f1d92.md) |
| Pattern family | `document` |
| Extends | `core` |

*A general document — KB articles, guides, notes, reference material. The catch-all type for written content that doesn't fit a more specific type.*

## Intent

Hold written content that has lifecycle (draft → published → archived) but doesn't fit the more constrained types (task, design-spec, decision). Documents include knowledge base articles, how-to guides, reference material, notes, summaries, and reports.

If a document is doing the work of a more specific type (e.g., it's actually a design spec), use the more specific type instead.

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `description` | string | ≤ 120 chars; one-line summary |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `audience` | string | Who this document is for (e.g., "agents", "users", "operators") |
| `category` | string | Free-form classification (e.g., "kb", "guide", "reference") |
| `published_by` | string | Who marked the document published |
| `published_at` | ISO 8601 date | When the document was published |
| `refs` | array of UIDs | related entries |
| `pattern_family` | literal | **v3.0 addition.** Set to `document` on document.capsule itself (self-declaration). Downstream document-like capsules reference this exemplar via their own `pattern_exemplar: d0c00001` field. Enables tooling queries: *"show me every capsule patterned on document"* = grep `pattern_exemplar: d0c00001`. Enforcement vector for v3 Decision 3's "convention over machinery" discipline. |

## State Machine

*v3 amendment (2026-04-24, v2.0 → v3.0): field renamed `stage:` → `status:`.*
*v3.1 amendment (2026-04-25, Gate B P0 #1 remediation): status enum corrected to `draft → published → archived` per [v3 spec (8b3f1d92)](../../vault/files/8b3f1d92.md) §4 + Decision 11. v3.0 had retained the v2.0 values `design / done`, contradicting Decision 11's mandate that content-production pipelines terminate in `document (status: published)`. Caught by sa.arch-specs 016 P0-1 + sa.skeptic 014 P0-1 (dual-instrument convergence). The §Intent paragraph above (line 26) had always read `draft → published → archived` — the State Machine + enums were the drift. Now reconciled.*

```
draft → published → archived
 ↑   ↓
 └───┘ (re-opening for revision)
```

Canonical status enum: `status:` ∈ {draft, published, archived, retired, superseded}

| Status | State | Meaning |
|-------|-------|---------|
| `draft` | `active` | Document is being written |
| `published` | `active` | Document is finalized, available, and publicly readable; `published_by:` + `published_at:` set |
| `archived` | `archived` | Document is no longer current; preserved for history. Status and state both flip to archived as an atomic pair |

### Valid transitions

- `status: draft` → `status: published` (publishing — verb: **publish** per v3 Decision 13)
- `status: published` → `status: draft` (re-opening for revision; `published_at:` updates when re-published)
- `status: published` → `status: archived` + `state: archived` (archival — verb: **archive**; status and state flip together)
- `status: archived` → `status: published` (un-archive; archival is reversible per Rule 3)

## Governance Rules (in addition to core)

1. **Published documents may be edited.** Unlike design specs and decisions, published documents are living artifacts and can be revised in place. Significant revisions should bump a `version` field if the document has one.
2. **Re-publishing from draft** is allowed; the `published_at` date is updated.
3. **Archiving is reversible.** An archived document can be re-published if it becomes relevant again.

## Validation Checks (run at check-in)

In addition to core checks:

1. `description:` ≤ 120 chars
2. `status:` is one of: `draft`, `published`, `archived` (per v3 spec §4 + Decision 11; v3.1 P0 #1 remediation 2026-04-25)
3. `state:` is one of: `active`, `archived`. When `status: archived`, `state:` MUST be `archived` (atomic pair)
4. If `status: published`: `published_by` and `published_at` fields are present

## Inheritance

Extends `core`. Inherits all core rules. May be extended by domain-specific subtypes (e.g., `kb-article`, `legal-document`) that add further required fields.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author a document.*

**Tools available:**
- `vault/00-index.jsonl` — grep for existing docs on the topic before authoring (avoid silent duplication)
- Cascade indexes at `vault/00-cascade-*.jsonl` — find related docs in the same domain
- `vault/files/<uid>.md` writer — documents live as flat ledger entries; filename is UID
- Type-discrimination check (before creating): is this really a decision, design-brief, arch-spec, task, playbook, or capsule-definition? If yes, use that type instead (Rule 6)

**Skills:**
- `author-document.skill.md` *(forthcoming v1.5)* — scaffold frontmatter + body
- `publish-document.skill.md` *(forthcoming v1.5)* — flip `status: draft → published`, stamp `published_by:` + `published_at:`

**Procedures:**
- Publishing workflow (v3.1) — `status: draft` while writing; flip to `status: published` + set `published_by:` + `published_at:` at publish (Check 4). Verb: **publish** per v3 Decision 13.
- Revision workflow — unlike decisions, published documents edit in place; bump `version:` for significant revisions
- Re-opening for revision — `published → draft` is legal; `published_at:` updates when re-published
- Archival workflow — `status: published → archived` paired atomically with `state: active → archived`. Verb: **archive** per v3 Decision 13.
- Archival reversibility — archived docs may be re-published if they become relevant again (Rule 3); `status: archived → published` legal

**Rules (at-a-glance):**
1. Documents are living artifacts — editable in place, unlike decisions and locked specs
2. Significant revisions bump `version:` if the document has one
3. Archiving is reversible
4. At `status: published`, `published_by:` + `published_at:` required (Check 4)
5. If a document fits a more specific type, use the more specific type (Rule 6)

**Pitfalls:**
- Using `document` type for content that belongs as a decision, arch-spec, or design-brief → Rule 6 violation; degrades queryability
- Editing a published document without bumping `version:` after significant changes → invisible drift; readers can't tell what changed
- Flipping to `status: published` without setting `published_by:` + `published_at:` → Check 4 failure
- Authoring step-by-step procedural content as a `document` when [how-to.capsule (a7c3f489)](how-to.capsule.md) fits better
- Forgetting `audience:` when the doc targets a non-default reader (agents vs users vs operators)
- Using deprecated v3.0 enum values (`design` / `done`) instead of v3.1 (`draft` / `published` / `archived`) — pre-migration documents may carry the old values; the v2→v3 migration script remaps `design → draft` and `done → published`

**Worked examples:**
- [a4f9e2b1](../../vault/files/a4f9e2b1.md) — Agent Operating Principles; the vault's governing operating document (boot-required reading for every agent)
- [5a766c42](../../vault/files/5a766c42.md) — Architectural Principles v2; the architectural keel of the vault
- [8ce11580](../../vault/files/8ce11580.md) — Tropo Operating Values; six values locked 2026-04-02, read at every boot
- [5ab66d92](../../vault/files/5ab66d92.md) — Mike's Notebook; running capture of Mike's observations with universal append protocol (any crew member may append)

**Go next:**
- More structured alternative → [how-to.capsule (a7c3f489)](how-to.capsule.md) — for procedural step-by-step content
- If the document records a decision → [decision.capsule (179d74e9)](decision.capsule.md)
- If the document is exploratory design thinking → [design-brief.capsule v2.1 (de5181b0)](design-brief.capsule.md)
- If the document specifies structure formally → [arch-spec.capsule v1.0 (a7f2e9c4)](arch-spec.capsule.md)
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1 | 2026-04-10 | Initial version locked. Catch-all type for written content with lifecycle (design → done). | tropo |
| 2.0 | 2026-04-16 | (v2.0 implicit in prior frontmatter; reconciled at v3.0 amendment.) | tropo |
| 3.0 | 2026-04-24 | **v3 amendment — document becomes standalone exemplar for document-pattern capsules per Decision 3.** `stage:` field renamed → `status:` per Decision 4. v3.0 incorrectly preserved v2.0 values (`design`, `done`) — see v3.1. Added `pattern_family: document` self-declaration in frontmatter. Added `pattern_family:` optional frontmatter row. Content publications terminate here per Decision 11. UID preserved at d0c00001. | argus-a33 |
| 3.1 | 2026-04-25 | **Gate B P0 #1 remediation (dual-instrument convergence: sa.arch-specs 016 + sa.skeptic 014).** Status enum corrected to `draft → published → archived` per [v3 spec (8b3f1d92)](../../vault/files/8b3f1d92.md) §4 + Decision 11. v3.0 had retained v2.0 values `design / done` against spec mandate; the §Intent paragraph (line 26) had always said `draft → published → archived` while the State Machine + Validation Check 2 + Studio Procedures said `design / done` — the file contradicted itself. Now reconciled. Affects 203-entry migration scope: v2→v3 migration script (Phase 7 of [9d3f7a61]) remaps `done → published` + `design → draft` for documents (not just key-rename as v3.0 had specified). State Machine, Status table, Valid transitions, Validation Check 2 + 3, Studio Procedures + Rules + Pitfalls all updated. UID preserved at d0c00001. | argus-a34 |

---

*document capsule definition | LOCKED v3.1 | amended 2026-04-25 by argus-a34 (Gate B P0 #1 — status enum corrected to draft→published→archived per spec §4 + D11); v3.0 amended 2026-04-24 by argus-a33; v1/v2.0 lock April 10, 2026 by Tropo preserved in git history | UID preserved at d0c00001*
*"Living artifacts. Editable. The pattern exemplar for document-like capsules across Tropo Work v3."*
