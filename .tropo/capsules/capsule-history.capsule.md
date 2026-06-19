---
uid: 5ec083a3
name: "capsule-history"
type: capsule-definition
extends: document
version: "1.1"
tier: os
author: argus-a55
created: 2026-05-11
created_by: argus-a55
modified: 2026-05-11
modified_by: argus-a55
status: active
schema_version: 2
extraction_scope: argo-private
governed_by: 222873b9   # entity.capsule (meta-capsule for capsule-definitions)
pattern_exemplar: d0c00001   # document.capsule
last_body_refactor: 2026-05-11
member_of:
  - "8dd772a0"   # tropo-governance
related_brief: d95d75e5   # v1.18.0 design brief — declares this capsule's purpose
related_capsule: 4cb20382   # kb-article.capsule (history files are kb-article-class siblings; this typed primitive is the canonical home for capsule-history shape)
tags: [capsule-definition, capsule-history, kernel-substrate, extraction-companion-pattern, v1.18.0-stream-c-remediation]
---

# capsule-history — Capsule Definition v1.0

## 1. Intent

A `capsule-history` file is the historical companion to an active capsule definition. When a capsule body is refactored per the v1.18.0 pedagogy-first 5-section pattern, accumulated historical content (changelog rows, amendment blocks, deprecated-content sections, prior-version Studio quick-ref signage, lineage footers) extracts to a sibling `.history.md` file with `type: capsule-history`. Active capsules read pedagogy-first; capsule-history files preserve the audit trail.

This capsule declares the shape: bidirectional pointer back to the parent capsule via `governs:`; minimal required frontmatter; flexible body shape (the history file's content varies per parent capsule's amendment lineage). Sibling to the parent capsule both filesystem-wise (`.history.md` next to `.capsule.md`) and graph-wise (`governs:` pointer + parent's frontmatter `history_file:` pointer).

Failure mode prevented: extracted history orphaned from its parent capsule; agents resolving "what's the changelog for X" can't find it; substrate validators can't distinguish capsule-history files from other kb-article-class artifacts.

---

## 2. Schema

### Required Frontmatter

| Field | Type | Constraint |
|---|---|---|
| `uid` | string (8-hex) | Stable identifier. |
| `type` | `"capsule-history"` | exact value |
| `governs` | string (8-hex UID) | The parent capsule's UID. Bidirectional pair with parent capsule's `history_file:` frontmatter field. |
| `governs_path` | string | The parent capsule's filesystem path (e.g., `.tropo/capsules/playbook.capsule.md`). Redundant with `governs:` UID but improves grep-discoverability. |
| `extracted_at` | date | ISO YYYY-MM-DD — when this file was first authored via extraction. |
| `extracted_by` | string | Agent identifier (e.g., `argus-a55`). |
| `extracted_in_cycle` | string | Cycle name + version (e.g., `"v1.18.0 — Capsule Library Phase 1"`). |
| `schema_version` | integer | `2` (current). |
| `governed_by` | string (8-hex UID) | This capsule's UID (`5ec083a3`). |
| `extraction_scope` | enum | Typically `argo-private` (historical record; not user-shipping content). |
| `subsystem_hub` | list[string] | At least the parent capsule's subsystem hub (e.g., `tropo-governance`) **(v1.1 member_of DISAMBIGUATE: moved here from `member_of`)**. |
| `member_of` | list[string] | optional; true organizational parent (non-hub). |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `extracted_in_release` | string | Release UID this extraction shipped with (e.g., the v1.18.0 release entry UID). May be `pending-<version>` during cycle build. |
| `tags` | list | Searchable tags including `capsule-history`, `extracted-from-<parent-capsule-name>`, cycle version. |

### Body shape (flexible per parent capsule's lineage)

Capsule-history files do NOT have a fixed 5-section canonical structure (unlike capsule definitions per playbook.capsule and subsystem-hub.capsule). The body content varies per the parent capsule's historical accumulation. Common sections (any/all may appear):

- **`## Changelog`** — full table of version transitions extracted from parent's prior body
- **`## Conscious Trade-offs`** — architectural-decision rationale extracted from parent
- **`## Known Enforcement Gaps`** — gap-tracking content extracted from parent
- **`## Amendment Blocks`** — inline amendment-block content extracted from parent (e.g., "v2.0 (round 1 — cold-boot 054 P1s)..." blocks)
- **`## Studio — Shop Signage`** — quick-reference content extracted (per Mike-A55 directive 2026-05-11: capsules are agent-read; quick-ref is human-facing; drops to history)
- **`## Examples (full)`** — extended example bodies extracted when active body kept abbreviated versions
- **`## Lineage footer`** — multi-version lineage footers extracted from parent's prior bottom

The body MUST close with a `## Provenance` section declaring: extracted-at date, extracted-by agent, cycle, active-capsule version-at-extraction, active-capsule version-after-extraction, and extraction-fidelity check note.

The active capsule body is the canonical schema teacher; the history file is the audit-trail preserver. Neither replaces the other.

---

## 3. State Machine

```
active (perpetual; no transitions)
```

Capsule-history files don't have a lifecycle in the active-status sense. They are append-only historical records. When a parent capsule refactors again (e.g., v1.5 → v1.6 future amendment), additional history content appends to the existing capsule-history file rather than creating a new one. The file persists indefinitely as audit trail.

If a parent capsule is fully retired (rare; UIDs are preserved across capsule supersessions), the corresponding capsule-history file persists for historical reference.

---

## 4. Validation Rules

### Governance Rules

1. **Bidirectional pointer pair.** Parent capsule's `history_file:` frontmatter MUST equal this file's `uid:`; this file's `governs:` MUST equal parent capsule's `uid:`. Validator enforces both directions.
2. **Sibling filesystem placement.** `.history.md` file lives in the same directory as the `.capsule.md` file. Naming convention: `<capsule-name>.history.md`.
3. **Append-only body.** Subsequent extractions (when parent capsule refactors again) APPEND to this file; never edit prior content. Prior amendment blocks stay as historical truth.
4. **Provenance section required.** Body MUST close with `## Provenance` section per §2.

### Validation Checks

1. **ERROR** — `type: capsule-history` exact match
2. **ERROR** — `governs:` resolves to a capsule-definition file
3. **ERROR** — bidirectional pointer consistency (parent's `history_file:` ↔ this file's `uid:`)
4. **ERROR** — filename matches `<capsule-name>.history.md` pattern; sibling to parent `.capsule.md`
5. **WARN** — body contains `## Provenance` section
6. **WARN** — `extracted_in_release:` declared (recommended; tracks shipping provenance)

Validator implementation deferred to v1.10 Enforcement (folds into the broader capsule-library validator).

---

## 5. Composes-With

- **Parent capsule** — declared via `governs:` frontmatter field; bidirectional pair via parent's `history_file:` field. Every capsule-history file has exactly one parent capsule.
- **[kb-article.capsule (4cb20382)](kb-article.capsule.md)** — capsule-history files were originally treated as kb-article-class artifacts at v1.18.0 Stream A authoring (history files declared `governed_by: 4cb20382`). v1.18.0 Stream C remediation (this capsule's authoring) corrects the typing: capsule-history is its own typed primitive; kb-article.capsule no longer governs history files. v1.18.0 ship updates history files' `governed_by:` to `5ec083a3` (this capsule).
- **[document.capsule (d0c00001)](document.capsule.md)** — extends document; inherits document's lifecycle floor + identity field semantics. Capsule-history files are documentation-class artifacts at heart (preserve readable amendment history); the type is the discriminator.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs THIS capsule definition (the meta-meta level).

### v1.18.0 instances authored under this capsule

- [playbook.history.md (1b834ed6)](playbook.history.md) — extracted from playbook.capsule v2.4 → v2.5
- [activation-log.history.md (2207c655)](activation-log.history.md) — extracted from activation-log.capsule v1.0 → v1.1
- [subsystem-hub.history.md (17867222)](subsystem-hub.history.md) — extracted from subsystem-hub.capsule v1.4 → v1.5

All three instances need `governed_by:` updated from `4cb20382` (kb-article.capsule, original v1.18.0 Stream A authoring) to `5ec083a3` (this capsule; v1.18.0 Stream C remediation). Mechanical edit; bidirectional pointer pair verified.

---

*capsule-history capsule definition | UID `5ec083a3` | v1.0 | v1.18.0 Stream C bundled remediation | history at <none — new capsule>*
