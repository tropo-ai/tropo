---
uid: f2a8b471
name: "research"
type: capsule-definition
extends: core
version: 1.0
tier: os
author: tropo
created: 2026-04-16
modified: 2026-06-09
modified_by: argus-a105
status: locked
meta_status_rollup:
  to-do: [design]
  done: [done]
meta_status_rollup_note: "argus-a104 2026-06-08 — rollup completion per the unified lifecycle knot (move 2, 9f6a1379); additive lock-break."
schema_version: 2
governed_by: 222873b9
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# research — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Extends | `core` |

*A governed research artifact — findings from a research panel, competitive analysis, technical survey, or domain investigation that informs design decisions.*

## Intent

Research reports are first-class pipeline artifacts. They inform design briefs, are cited in specifications, and produce the evidentiary record for architectural decisions. A research artifact without governance loses its chain of provenance — the link from "we researched this" to "therefore we designed it this way" becomes invisible.

**Before creating a research entry:** what decision or design brief will this inform? Declare it in `relationships:` with `rel: informs`.

---

## Required Frontmatter

| Field | Type | Constraint |
|-------|------|-----------|
| `title` | string | ≤ 100 chars |
| `description` | string | ≤ 120 chars. What was researched and what was found. |
| `owner` | string | Agent who conducted or commissioned the research |
| `stage` | enum | See state machine below |
| `state` | enum | `active` or `archived` |
| `member_of` | array of UIDs | Project(s) this research belongs to |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `relationships` | array | `informs:` — design briefs or specs this research feeds into |
| `sources` | array | External sources consulted (URLs or citation strings) |
| `commissioned_by` | string | Agent who requested this research |

---

## State Machine

```
design → done → state: archived
```

| Stage | Meaning |
|-------|---------|
| `design` | Research in progress |
| `done` | Research complete and published |

Research does not go through `verify` — the research itself is the finding. The downstream design brief or spec validates the research by acting on it.

---

## Governance Rules

1. **Research informs something.** A research artifact with no `informs:` relationship is an orphan finding — declare what it feeds into before publishing.

2. **Published research is immutable.** Once at `stage: done`, research findings are not edited. If findings change, create a new research entry and use `supersedes:` to link it.

3. **Sources must be traceable.** If research draws on external sources, list them in `sources:` or in the body.

---

## Validation Checks

1. `member_of:` present, non-empty array
2. `stage:` is one of: `design`, `done`
3. `state:` is one of: `active`, `archived`
4. `title:` ≤ 100 chars
5. `description:` ≤ 120 chars
6. If `stage: done`: at least one `relationships:` entry with `rel: informs` is present (research must declare what it informs before being marked complete)

---

*research capsule definition | LOCKED v1.0 | Tropo OS | April 16, 2026*
