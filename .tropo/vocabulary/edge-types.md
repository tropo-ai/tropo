---
uid: ae4c277c
title: "Tropo Graph — Edge Type Vocabulary"
type: vocabulary
tier: os
status: published
owner: argus
created: 2026-04-14
created_by: argus-a23
path:.tropo/vocabulary/edge-types.md
---

# Tropo Graph — Edge Type Vocabulary

*The canonical list of directed edge types in the Tropo knowledge graph. Every frontmatter field that references another UID is a directed edge. This vocabulary defines those edges formally.*

*Source of truth for: `vault/00-graph.jsonl` (edge log), `vault/00-graph-index.json` (traversal index).*

---

## Canonical Edge Types

| Edge Type | Frontmatter Field | Direction | Meaning |
|-----------|------------------|-----------|---------|
| `belongs-to` | `project` / `projects` | file → project | This artifact is a member of this project |
| `has-board` | `board` | project → board | This project's generated board |
| `has-collection` | `primary_collection`, `tasks_collection` | project → collection | This project's membership roster or work queue |
| `scopes-to` | `scope_ref` | board → project | This board scopes to this project |
| `supersedes` | `supersedes` | file → file | This version replaces that version |
| `implements` | `implements` | file → file | This artifact implements that spec |
| `references` | `refs` | file → file | Formal dependency or reference (structural) |
| `blocked-by` | `blocked_by` | task → task | This task cannot proceed until that task is done |
| `blocks` | `blocks` | task → task | This task blocks that task |
| `required-by` | `required_by` | file → file | That artifact requires this one |
| `extends` | `extends` | capsule → capsule | This capsule inherits from that capsule |
| `governed-by` | `governed_by` | file → governance-doc | This file is governed by that document |
| `member-of` | `project` (on projects) | project → project | This project is a member of that project |

---

## Structural vs Non-Structural References

**Structural (goes in frontmatter, appears in the graph):**
A relationship that another agent must traverse to understand the artifact's governance, dependency, or provenance.

*Test:* "Would a vault steward agent need to follow this relationship to understand the artifact?"

**Non-structural (stays in body text):**
Illustrative mentions, historical context, "see also" cross-references, narrative citations.

*These do not appear in the graph. They are for human readers, not for traversal.*

---

## Validation Rule

At check-in, any UID reference in a frontmatter field must use one of the edge types above. Unknown edge types are flagged as warnings by the governance validator. New edge types require Argus review before being added to this vocabulary.

---

## Edge Log Format (`vault/00-graph.jsonl`)

One JSON object per edge, one line per object:

```jsonl
{"from":"<uid>","rel":"<edge-type>","to":"<uid>"}
```

Example:
```jsonl
{"from":"63642415","rel":"belongs-to","to":"35abbdae"}
{"from":"35abbdae","rel":"member-of","to":"32c75ba0"}
{"from":"5dfa62dd","rel":"supersedes","to":"77d14e53"}
```

---

*Tropo Graph Edge Type Vocabulary | v1.0 | OS tier | Argus A23 | April 14, 2026*
*Formalized per Metis G41 design brief (d66f4ba5) Q2 recommendation.*
*"Every UID reference is a directed edge. Name the edges you intend to traverse."*
