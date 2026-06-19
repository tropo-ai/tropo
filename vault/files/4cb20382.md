---
uid: 4cb20382
name: "kb-article"
type: capsule-definition
extends: document
version: "1.1"
tier: os
author: argus-a55
created: 2026-05-11
created_by: argus-a55
modified: 2026-06-06
modified_by: argus-a101
v1_1_completion_note: "v1.1 member_of DISAMBIGUATE completed 2026-06-06 by Argus A101 per spec 6f5bb2cb (Mike-A100-approved 9 lock-breaks) + core.capsule v1.5 Rule 9. The v1.1 §2 table swap (subsystem_hub carries hub membership; member_of = true parent only) was applied but the body §4 ERROR validation rule + §5 Composes-With prose were left keyed on member_of-as-hub. A101 finished the reconciliation so the body matches the table. Data already conforms (all 26 kb-articles use subsystem_hub). No version re-bump: same v1.1 logical change, applied across two passes (table prior gen; body+check A101)."
status: active
enforced_enums:
  status:
    canonical: [draft, published, archived, superseded]
    aliases: {done: published}
meta_status_rollup:
  in-progress: [draft]
  done: [published, archived, superseded, done]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9   # entity.capsule (meta-capsule for capsule-definitions)
pattern_exemplar: d0c00001   # document.capsule — kb-article is patterned on document
last_body_refactor: 2026-05-11
member_of:
  - "f87e33f0"   # tropo-documentation (kb-articles are documentation-class)
  - "8dd772a0"   # tropo-governance (governance-class capsule definitions)
  - "be5bc951"   # v1.18.0 activation root
related_brief: d95d75e5   # v1.18.0 design brief — declares this capsule's purpose
tags: [capsule-definition, kb-article, documentation-class, v1.18.0-cycle-stream-a, lock-c-foundation, first-capsule-under-pedagogy-first-5-section-pattern]
---

# kb-article — Capsule Definition v1.0

## 1. Intent

KB articles are how the Tropo substrate teaches itself to agents. When a fresh agent needs to understand a primitive — how playbooks work, how projects replace folders, how the vault is structured — they read the relevant kb-article. The article supplements the capsule definition with operational reasoning + worked examples + common usage patterns. **A capsule declares the type's schema; a kb-article teaches the type's use.** Capsules are the type-definition layer; kb-articles are the explanation-of-use layer.

This capsule declares the canonical shape for typed KB articles. Type ensures agents discover articles via index queries. Required frontmatter ensures each article carries identity + lifecycle + governance + audience. Required body structure (Intent opener + body content + composes-with) ensures each article actually teaches.

This capsule `extends: document` — it inherits document.capsule's lifecycle floor and identity field semantics + adds kb-article-specific frontmatter (audience, category, member_of multi-parent) + the §2 body shape conventions below. Articles authored under this capsule satisfy document.capsule's floor AND this capsule's additions.

Failure mode prevented: KB articles drifting into untyped or under-structured prose; agents reading articles and improvising operational behavior because the article doesn't anchor in the substrate.

## 2. Schema

Required frontmatter fields:

| Field | Type | Notes |
|---|---|---|
| `uid` | string (8-hex) | UID-addressed; unique across vault |
| `type` | `"kb-article"` | exact value |
| `title` | string | ≤80 chars |
| `description` | string | one-line summary; ≤120 chars |
| `status` | enum | `draft` / `published` / `archived` — the article's lifecycle state |
| `state` | enum | `active` / `inactive` — orthogonal to status; tracks whether the article is currently in-circulation (`active`) or deprecated-but-preserved (`inactive`). Most published articles are `state: active`; articles superseded by newer ones flip to `state: inactive` + `status: archived` together |
| `author` | string | agent UID or human name |
| `created` | date | ISO `YYYY-MM-DD` |
| `created_by` | string | agent UID |
| `modified` | date | ISO `YYYY-MM-DD` |
| `modified_by` | string | agent UID |
| `schema_version` | integer | `2` (current) |
| `governed_by` | string (8-hex UID) | this capsule's UID (`4cb20382`) |
| `subsystem_hub` | list[string] | at least one subsystem hub UID — the subsystem(s) this article documents **(v1.1 member_of DISAMBIGUATE: moved here from `member_of`; all 26 kb-articles already conform)** |
| `member_of` | list[string] | optional; true organizational parent (non-hub) |
| `extraction_scope` | enum | `ship` / `argo-reference` / `argo-private`. **`ship`** = article ships in every Tropo Studio (canonical how-it-works explainers; most KB articles); **`argo-reference`** = article is reference-only for the Argo dev Studio (internal documentation); **`argo-private`** = article is Argo-private historical record (rarely used for kb articles; common for capsule-history files). Default `ship` unless the article is dev-Studio-internal. |

Recommended (not required) frontmatter:

| Field | Type | Notes |
|---|---|---|
| `audience` | string | comma-separated audience tags (agentic-builders, agents, strangers, etc.) |
| `category` | enum | `how-to` / `reference` / `concept` / `glossary` / `decision-support` |
| `tags` | list[string] | searchable tags |
| `supersedes` | string (8-hex UID) | if this article replaces a prior one |

Body structure (3 sections; agent-read performant):

```markdown
## Intent
What does this article teach? Who is it for? What context is the reader in
when they reach for it? What will they know after reading?

## <Author-chosen heading; varies by category>

(Replace the angle-bracket placeholder with your actual section heading.
The middle section's name + structure varies by `category:`:)

- category: how-to → "## Steps" or "## How to <do the thing>" + numbered steps + examples + common pitfalls
- category: reference → "## Reference" or topic-specific heading + tables + field definitions + cross-references
- category: concept → "## The Concept" or topic-specific heading + explanation + analogues + composes-with
- category: glossary → "## Terms" + entries (term: definition + cross-references)
- category: decision-support → "## Decision Framing" + question framing + options + trade-offs

## Composes-With
Related articles + capsule definitions + concepts (UID-linked).
```

Provenance lives in frontmatter (`author`, `created`, `created_by`, `modified`, `modified_by`); no body Provenance section needed (Lock C agent-read performant; per Mike-A55 directive *"focused on agent use, not human"*).

## 3. State Machine

**Canonical status enum:** `status:` ∈ {draft, published, archived, superseded}

```
draft → published → archived
```

Transitions:

- **draft → published** — author signals article is ready for substrate use; `status:` updates; `modified:` + `modified_by:` updated
- **published → archived** — superseded by newer article OR scope retired; `status:` updates; the successor article (if any) declares `supersedes: <archived-uid>` linking back

No back-transitions. Archived articles stay archived (historical record). Revisions to published articles update in place (frontmatter `modified:` advances; body content edited); the article doesn't return to `draft` for revisions.

## 4. Validation Rules

**ERROR-severity** (must pass; cycle build halts if any fails):

- All required frontmatter fields present (per §2 Schema table)
- `type: kb-article` exact match
- `governed_by:` resolves to `4cb20382` (this capsule's UID)
- `subsystem_hub:` non-empty list with at least one resolvable subsystem hub UID (v1.1 member_of DISAMBIGUATE — was `member_of:` pre-v1.1; `member_of:` is now the optional true organizational parent per core.capsule v1.5 Rule 9)

**WARN-severity** (logged; cycle build continues; surface in next validator pass):

- Body has at least an `## Intent` h2 section OR an equivalent intent-teaching opener (italic-gloss subtitle line followed by opening paragraph that names what the article teaches; common pre-v1.18.0 convention preserved during grace window). v1.18.0+ articles SHOULD use canonical `## Intent`; legacy articles using equivalent openers (e.g., italic subtitle + leading paragraph) satisfy the WARN rule.
- `audience:` field declared (recommended for performant agent retrieval)
- `category:` field declared (recommended for body-shape consistency per §2)

**INFO-severity** (logged; informational only):

- `tags:` field declared (searchability)
- `supersedes:` consistent if declared (predecessor article exists + has `status: archived`)

## 5. Composes-With

- **Subsystem hubs** — every kb-article declares `subsystem_hub:` pointing at the subsystem(s) it documents. Required. The kb-article is a child of its subsystem in the rendered project graph. **The subsystem hubs are the canonical organizational anchor** for KB content (Mike-A55 framing 2026-05-11); the hubs index + reference; the articles carry the substance.
- **Canonical location — `vault/files/<uid>.md` under Universal Storage Convergence Lock A.** KB articles live at `vault/files/<uid>.md` with full `subsystem_hub:` edges into subsystem hubs (primary: `f87e33f0` Tropo Documentation; cross-cuts as appropriate). Discovery flows through the hub `## Members` lists, not through a hand-maintained catalog. *Migrated from `.tropo/kb/*.md` (provisional v1.18.x location) at v1.19.0 per Convergence Phase 1.* Type, governance, and location are all stable at v1.19.0+.
- **Capsule definitions** — when an article documents a typed primitive, link to that capsule's UID in body via inline reference (e.g., `[playbook.capsule](../capsules/playbook.capsule.md)` with `governed_by:` field also pointing at the capsule).
- **Other kb-articles** — cross-references via UID; `supersedes:` chains for evolved articles
- **`type: capsule-history` artifacts** (the `.history.md` sibling pattern per v1.18.0 Stream B) — capsule-history files are governed by their OWN typed primitive [`capsule-history.capsule` (5ec083a3)](capsule-history.capsule.md), authored v1.18.0 Stream C bundled remediation. Previously (Stream A initial authoring), capsule-history files declared `governed_by: 4cb20382` (this capsule) as a kb-article-class placeholder; Stream C remediation corrected the typing. v1.18.0 ship updates the 3 existing history files (playbook.history + activation-log.history + subsystem-hub.history) to declare `governed_by: 5ec083a3`.

---

*kb-article | UID `4cb20382` | v1.0 | history at <none — new capsule; first body authored under the v1.18.0 Q3-locked 5-section pattern>*
