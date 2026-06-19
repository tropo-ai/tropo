---
uid: a2bc3e16
type: capsule-definition
name: "working-copy"
title: "working-copy — Capsule Definition v1.0"
description: "Markdown working-copy derived from an external-artifact projection. The agent's canonical editing medium for content inside imported binaries."
extends: core
version: "1.0"
status: locked
state: active
locked_by: argus-a61
locked_at: 2026-05-13
schema_version: 2
extraction_scope: ship
author: argus
owner: argus
created: 2026-05-13
modified: 2026-05-13
created_by: argus-a61
modified_by: argus-a61
governed_by: 222873b9   # capsule-definition meta-capsule
aligned_with:
  - "5a89297a"   # Working-Copy Primitive + Template Registration + Format-Only Export — Architecture Specification v0.3 LOCKED
  - "2b49ba79"   # Import Primitive Architecture Specification v1.0 LOCKED (Invariant #8 sidecar-equivalence)
  - "eedd7034"   # external-artifact.capsule v1.0 (the projection type working-copies derive from)
  - "ee814120"   # core.capsule v1.1
applies_to: working-copy
pattern_exemplar: eedd7034   # external-artifact.capsule — same shape (frontmatter-heavy + content body + lifecycle + validator + governance rules)
member_of:
  - "9b70a355"   # v1.26.0 Stream A — Working-Copy Capsule Definition
  - "8dd772a0"   # tropo-governance
tags: [capsule-definition, working-copy, agent-editing-medium, import-primitive-derivative, v1.26.0-stream-a]
---

# working-copy — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](222873b9.md) |
| Aligned with | [Working-Copy Primitive Architecture Spec (5a89297a)](5a89297a.md) |
| Aligned with | [Import Primitive Architecture Spec (2b49ba79)](2b49ba79.md) |
| Aligned with | [external-artifact.capsule v1.0 (eedd7034)](eedd7034.md) |
| Pattern exemplar | [external-artifact.capsule (eedd7034)](eedd7034.md) |
| Member of | [v1.26.0 — Stream A: Working-Copy Capsule Definition (9b70a355)](9b70a355.md) |
| Member of | [Tropo Governance (8dd772a0)](8dd772a0.md) |

*A `working-copy` entry is a vault-resident markdown file derived from an `external-artifact` projection by extracting the content of the source binary. It is the agent's canonical editing medium for the imported content. Sources stay where they are; the working-copy is what agents read + edit; the export gesture (v1.27.0) regenerates a deliverable binary from the working-copy + a chosen template.*

---

## Intent

The `working-copy` capsule is the substrate primitive that makes agent-native editing of imported binaries possible. When a user imports a `.docx` (or, in future cycles, other binary types) via the v1.25.0 import primitive, the binary lands as a governed `external-artifact` with a sidecar + projection — but the binary itself is opaque to agents. Agents reason over markdown, not Word XML.

The `working-copy` capsule closes that gap. `tropo-extract.py` (Stream B) reads the source binary via the docx skill, extracts text + structural markdown (headings, lists, tables, inline formatting), and authors a `working-copy` instance at `vault/files/<working-uid>.md`. The agent reads + edits the working-copy in markdown; vault queries index the content; the reconciler monitors source-binary drift; lineage chains via `derived_from:` back through the projection (which equals the sidecar per the sidecar-equivalence invariant from arch-spec §2.6) to the original binary.

**Before creating a working-copy instance:** confirm a corresponding `external-artifact` projection exists at `vault/files/<projection-uid>.md`. Working-copies are authored by `tropo-extract.py`; manual authorship is not the normal path.

**Failure mode prevented:** the "binary-as-black-box" problem. Without working-copies, agents either operate blind on `.docx` content (can't read it) or operate via skill-mediated XML-editing for every interaction (expensive + brittle + not Tropo-native). Working-copies make the imported content first-class governable: queryable, edit-trackable, lineage-chained, drift-detected.

---

## Required Frontmatter (in addition to core)

Inherited from [`core.capsule`](core.capsule.md): `uid`, `type` (= `"working-copy"`), `created`, `modified`, `state` (= `active` at authoring).

Working-copy-specific required fields:

| Field | Type | Constraint |
|-------|------|-----------|
| `title` | string | ≤ 120 chars. Default at extraction: filename of source binary stripped of extension (e.g., `CFO_Whitepaper_Revised.docx` → `CFO_Whitepaper_Revised`). Mutable — agent/user may rename. |
| `derived_from` | array of 1 UID | MUST resolve to a `type: external-artifact` projection. Exactly one parent in v1.0 (one working-copy per source binary; branching deferred to a future cycle). Composability pair with the projection's lineage. |
| `source_filename` | string | Filename of source binary at extraction time. Audit field; stays stable even if source file is later renamed. |
| `source_hash_at_extraction` | string | Hash of source binary at extraction time. Immutable; enables forensic replay of extraction state. Distinct from `last_source_hash_seen:` which mutates per reconciler reset. |
| `last_source_hash_seen` | string | Last hash the reconciler verified against the source binary. Updated on every reconcile pass where the binary hash is checked + on user-resolved drift events (`keep` resolution). |
| `hash_function` | string enum | One of: `stable-id`, `content-aware`, `sha256`. The hash function used to compute `source_hash_at_extraction:`. Drift detection uses the same function. |
| `extraction_tool_version` | string | E.g., `tropo-extract-v1.0.0`. Audit field. Enables future re-extraction with newer tooling to be detected as a versioned operation distinct from the same-tooling re-extraction (`--force` refresh path). |
| `owner` | string | Agent slug. Default at extraction: the activating executive's slug (e.g., `argus-a61`). |
| `extraction_scope` | string enum | One of: `argo-reference`, `argo-private`, `external`. Default for working-copies: `argo-private` (user content; not for ship build; not externally extracted in releases). Templates intended for marketplace publishing later may transition to `external`. |

---

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `last_exported_at` | ISO 8601 date | Timestamp of most recent export from this working-copy. Null if never exported. Convenience field; the reconciler journal carries the full export history. |
| `last_exported_path` | string | File path of most recent export (e.g., `exports/2026-05-13-gtm-strategy.docx`). Null if never exported. |
| `last_exported_template` | UID | Template UID used at most recent export. Null if never exported. |
| `member_of` | array of UIDs | Parent projects. Inherits the projection's `member_of:` by default (typically the folder-marker project). User-content projects (e.g., "MindBridge GTM Strategy" governing a body of work) MAY be added explicitly. |
| `description` | string | ≤ 500 chars. Optional human-readable description. May be auto-extracted from `.docx` core.xml at extraction time (see `tropo-extract.py` behavior). |
| `archived_at` | ISO 8601 date | Timestamp of archival. Set when `state: active → state: archived`. |
| `archived_by` | string | Agent slug at archival. |
| `relationships` | array of typed edges | Schema v2 cross-cutting references (e.g., to other working-copies, related projects). |

---

## Required Body Sections

**Working-copies are content-bearing markdown.** The body IS the extracted + agent-edited content. **No required structural sections** (no Relations table, no Intent section, no Governance Rules — those belong on capsule-definition files, not working-copy instances).

The validator does NOT enforce body section presence on working-copy instances; this is distinct from `document.capsule` or `design-brief.capsule`.

**Convention:** working-copy body begins with a level-1 heading `# <title>` matching the frontmatter `title:` field. The extraction tool authors this; agents may modify. Markdown body content follows per standard markdown conventions.

---

## Governance Rules (in addition to core)

1. **Authored only by `tropo-extract.py` (or its descendants).** Manual authorship of working-copy instances is not the normal path. If you need to hand-author a working-copy, you should be editing the extraction tool's behavior instead.

2. **One-working-copy-per-projection in v1.0.** A given `external-artifact` projection has at most one `state: active` working-copy derived from it at any time. Branching (multiple working-copies from one projection for exploring alternate drafts) is a future-cycle concern.

3. **Source binary is never mutated by working-copy operations.** The working-copy is the agent's edit medium; the source binary is the import-record. Agent edits to the working-copy do NOT propagate to the source. (The reverse propagation — source binary changes off-system → working-copy stale → drift detection → refresh/keep resolution — IS in scope; see arch-spec §3.8.)

4. **Working-copy `derived_from:` must point at a live external-artifact projection.** Dangling lineage is an ERROR per the validator (§Validation Checks below). If a projection is archived, the working-copy derived from it should also archive.

5. **State transitions are explicit.** `state: active → state: archived` requires an explicit gesture (user invocation, project-closure, or successor-working-copy authoring). No silent archival on source-binary changes (drift detection surfaces; doesn't archive).

6. **Modification stamps land on every edit.** Per `core.capsule` discipline: `modified:` + `modified_by:` update on every agent edit. The validator enforces; the convention serves cross-generational forensic clarity.

7. **Content is the agent's responsibility, NOT the tool's.** `tropo-extract.py` authors the initial extraction; from there, the agent owns the working-copy's content quality. The tool does not validate, normalize, or re-format the agent's edits.

---

## Validation Checks (run at check-in)

Per [arch-spec 5a89297a §3.10](5a89297a.md) — the Stream D validator extensions land these:

1. **Working-copy schema check** — for each `type: working-copy` entry: `derived_from:` non-empty AND single-element AND resolves to `type: external-artifact`; `source_hash_at_extraction:` non-empty; `last_source_hash_seen:` non-empty; `hash_function:` one of the valid values (`stable-id`, `content-aware`, `sha256`). Severity: **ERROR**.

2. **Working-copy lineage check** — for each `type: working-copy`, verify the `derived_from:` projection's vault entry exists. Severity: **ERROR** if dangling.

3. **Sidecar-equivalence check (Invariant #8 enforcement)** — for each `type: working-copy`, verify the projection it derives from has a sibling sidecar present at the projection's `source_sidecar:` path. Per arch-spec §2.6 invariant: projection-UID = sidecar-UID per v1.25.0 §A.4 baking-in rule 1. Severity: **ERROR** if dangling.

4. **Index-sync check** — for each new `vault/files/<uid>.md` entry of type `working-copy`, verify a row exists in `vault/00-index.jsonl`. Closes the v1.25.0 import-walker-doesn't-sync-index sibling defect at the substrate level: `tropo-extract.py` MUST append index rows inline, not defer to `rebuild-index.py`. Severity: **ERROR**.

5. **One-working-copy-per-projection check** — for each `type: external-artifact` projection: at most one `state: active` working-copy with `derived_from: [<projection-uid>]`. Severity: **ERROR** if multiple actives found.

---

## State Machine

```
state: active ─────────────────────► state: archived
       (extracted; being worked;        (superseded; no longer the canonical
        may have been exported           working version; preserved for history)
        any number of times)
```

**Only two states** (per v0.2 walk-lock Q2; dropped over-engineered 5-state machine).

**Valid transitions:**

- `state: active → state: archived` — explicit gesture. Triggers: (a) user/agent invokes archival; (b) project containing the working-copy is archived; (c) successor working-copy is extracted from same projection (which would violate Validation Check 5; resolution: archive the predecessor first).

**No `state: archived → state: active` reversal.** If an archived working-copy is needed again, derive a fresh working-copy via `tropo-extract.py --force` from the same projection (new extraction event + fresh UID + fresh lineage chain). The archived one stays archived for historical record.

**Cross-cutting `status:` reporting:** working-copy instances do NOT carry a `status:` field (unlike design-brief, task, note). The 2-state `state:` machine is sufficient; lifecycle progress is tracked via the journal + the tracking fields (`last_exported_at:`, `last_source_hash_seen:`) rather than via a status enum.

**Tracking fields update WITHOUT state change:**
- `last_source_hash_seen:` mutates on every reconciler pass; no state transition.
- `last_exported_at:` + `last_exported_path:` + `last_exported_template:` mutate on every export; no state transition.
- `modified:` + `modified_by:` mutate on every agent edit; no state transition.

Export is an event, not a state. Drift is a derived property, not a state. The 2-state `state:` enum is intentionally minimal.

---

## Relationship to Other Capsules

- **`external-artifact` (parent)** — every working-copy `derived_from:` exactly one external-artifact projection in v1.0. The projection is the canonical truth for the source binary; the working-copy is the canonical truth for the agent's view of the binary's content. Together they constitute the full governed identity of an imported binary.

- **`docx-template` (cycle-pair)** — v1.27.0 ships the `docx-template` capsule; the export gesture (v1.27.0 `tropo-export.py`) composes working-copy + template to produce a `.docx` deliverable in `exports/`. The working-copy carries `last_exported_template: <template-uid>` after each export; templates have no reverse pointer to working-copies (one template can be used by many working-copies; the reverse lookup goes via the journal).

- **`reconcile-report` (sa.reconciler output)** — reconciler runs surface `working-copy-source-drift` events in the report's §Judgment section; the executive surfaces to user with refresh/keep paths. The working-copy is the affected artifact; the report carries the diagnosis.

- **Folder-marker `project` (sibling)** — working-copies inherit the folder-marker project's `member_of:` chain by default. User-content projects (e.g., a "GTM Strategy 2026" project) may be added explicitly to surface a working-copy in a project board.

---

## Inheritance

`working-copy` extends `core` (per `extends: core` in this capsule's frontmatter). Inherited fields: `uid`, `type`, `created`, `modified`, `state`, `created_by`, `modified_by`, `schema_version`.

This capsule does NOT extend `external-artifact` despite the lineage relationship — working-copies are NOT a subtype of external-artifacts; they are derivative artifacts with their own schema. The `derived_from:` edge is the composability mechanism, not type inheritance.

---

## Studio — Shop Signage

In a typical Tropo Studio after v1.26.0 ships, an executive (or stranger user) encountering a working-copy in vault has a clear mental model: *"This is a markdown view of someone's imported `.docx`. The agent edited it. The original binary is unchanged at the source. Queries here surface the content. If I want to look at what the original `.docx` says, I follow `derived_from:` to the projection, then `source_path:` to the binary."*

The capsule is intentionally narrow: it formalizes the markdown working-copy as a governable artifact. It does NOT govern: extraction policy (that's `tropo-extract.py` behavior + arch-spec §3.5); drift detection (that's the reconcile-imports playbook + sa.reconciler); export generation (that's v1.27.0's `tropo-export.py` + `docx-template`). Each substrate-element does one thing; working-copy is one of them.

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-05-13 | **LOCKED.** Initial capsule authored in v1.26.0 Stream A per [arch-spec 5a89297a §3.1 + §3.11](5a89297a.md). Schema: 9 required frontmatter fields (beyond core) + 7 optional; 2-state lifecycle (active/archived); 5 validation checks (schema, lineage, sidecar-equivalence, index-sync, one-per-projection); 7 governance rules. Pattern-exemplar [external-artifact.capsule (eedd7034)](eedd7034.md). UID pre-minted at arch-spec v0.3 lock; file authored at cycle execution. | argus-a61 |

---

*working-copy.capsule v1.0 | UID `a2bc3e16` | LOCKED 2026-05-13 by argus-a61 | v1.26.0 Stream A deliverable.*
*"The working-copy is the canonical agent-editing medium. Source binary is the import-record. Lineage is everything."*
