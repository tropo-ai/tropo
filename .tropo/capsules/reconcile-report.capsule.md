---
uid: 013b7b6e
type: capsule-definition
name: "reconcile-report"
title: "reconcile-report — Capsule Definition v1.0"
description: "Structured persona-agnostic report schema for sa.reconciler output. The contract sa.reconciler honors when handing reconciliation findings to the executive."
extends: core
version: "1.0"
status: locked
state: active
locked_by: argus-a60
locked_at: 2026-05-13
schema_version: 2
extraction_scope: ship
author: argus
owner: argus
created: 2026-05-13
modified: 2026-05-13
created_by: argus-a60
modified_by: argus-a60
governed_by: 222873b9   # capsule-definition meta-capsule
aligned_with:
  - "2b49ba79"   # Import Primitive Architecture Specification v1.0 LOCKED
  - "ee814120"   # core.capsule v1.1
applies_to: reconcile-report
member_of:
  - "c512438b"   # v1.25.0 Stream A — Capsules
  - "8dd772a0"   # tropo-governance
tags: [capsule-definition, reconcile-report, sa-reconciler, import-primitive, v1.25.0-stream-a]
---

# reconcile-report — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](222873b9.md) |
| Aligned with | [Import Primitive — Architecture Specification (2b49ba79)](2b49ba79.md) |
| Member of | [v1.25.0 — Stream A: Capsules (c512438b)](c512438b.md) |
| Member of | [Tropo Governance (8dd772a0)](8dd772a0.md) |

*A `reconcile-report` entry is the structured output sa.reconciler hands its commissioning executive at the end of every reconciliation pass. It's persona-agnostic: any executive (Argus, Vela, Cowork concierge, future agents) can consume the same report shape and compose user-facing voice in its own persona. Reports are append-only artifacts; immutable once handed off; archivable on rotation.*

---

## Intent

The `reconcile-report` capsule is the contract between sa.reconciler and the executive. sa.reconciler does structural intelligence work (enumeration, pattern recognition, categorization, application of routine + pattern-matched events). The executive composes the user-facing surface in its own voice. The report is the data the executive triages.

Persona-agnostic structure matters. If sa.reconciler wrote narrative prose ("I noticed you moved Q3 Strategy..."), that narrative would either (a) flatten the executive's voice when surfaced to the user verbatim, or (b) be discarded when the executive rewrites for its persona. Pure-structured output keeps each agent focused on what it's actually good at — sa.reconciler does data; executive does voice.

**Before creating a reconcile-report instance:** authorship is exclusively sa.reconciler's. No other agent writes reconcile-report entries. The capsule defines the contract; sa.reconciler's playbook ([reconcile-imports.playbook](4a2f6dbd.md)) produces the instances.

**Failure mode prevented:** ambiguous reconciler output where executive can't mechanically triage routine-vs-judgment-vs-blocking findings, leading to either (a) every event surfaced to user (naggy) or (b) silent application of judgment-class events (substrate drift). Structured categorization with confidence levels + explicit "blocking requires user resolution" semantics prevents both failure modes.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `type` | string | Must be `reconcile-report` |
| `run_uid` | 8-hex | sa.reconciler run UID (each spawn gets one) |
| `executive` | string | Persona that commissioned the run (e.g., `argus-a60`, `vela-v45`); per the TROPO-CONTROL.md identity model, this is a `tropo-agent-id` or recognizable persona slug |
| `trigger_path` | enum | `anomaly` \| `scheduled` \| `user-invoked` — which of the three triggering paths fired this run |
| `scope` | string | `full-studio` \| `folder:<path>` \| `operation:<uid>` — what the pass covered |
| `started_at` | ISO 8601 timestamp | When sa.reconciler began the pass |
| `completed_at` | ISO 8601 timestamp | When the report was sealed |
| `total_deltas_detected` | integer | Raw delta count from Step 4 of the playbook |
| `total_events_after_pattern_match` | integer | Count after Step 5 pattern recognition compressed raw deltas |
| `events_by_category` | object | Counts: `{routine: int, pattern_matched: int, judgment: int, blocking: int}` |
| `events_applied` | integer | Count of events actually applied to substrate (routine + pattern-matched + any judgment auto-resolved by executive) |
| `events_deferred` | integer | Count of events surfaced to executive review (judgment) or user (blocking) |
| `schema_version` | integer | `1` |

**Core inherited (required):** `uid`, `status`, `title`, `owner`, `created`, `modified`. Per core.capsule v1.1.

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `description` | string | One-line summary (e.g., "Daily reconciliation pass; 47 events; all routine") |
| `pattern_catalog_version` | string | The reconcile-imports.playbook version sa.reconciler ran (for forensic replay) |
| `audit_log_range` | object | `{first_event_uid: <8-hex>, last_event_uid: <8-hex>}` — pointer into journal.jsonl for the rows this pass wrote |
| `tags` | string array | Free-form |

---

## Required Body Sections

Every `reconcile-report` body MUST contain these four categorized sections, in this order. Sections may be empty (zero events in that category) — empty sections still appear with an explicit "(none)" note.

### 1. `## Routine`

Auto-applied events; high confidence (≥ 0.95); not surfaced to user under normal posture.

Each entry: one-line description + target UID + action + brief evidence. Brevity is the point — the executive scans, confirms nothing requires attention, moves on. For empty: `(none)`.

### 2. `## Pattern-matched`

Auto-applied events compressed by pattern recognition; high confidence (≥ 0.80 and < 0.95); optionally surfaced to user as a one-line note if context warrants ("references updated after your folder reorg"); not pushy.

Each entry: pattern name + event description + count of underlying raw deltas + evidence summary. The pattern-name is critical — it lets the executive know what to say to the user without re-deriving the pattern.

### 3. `## Judgment`

Executive review needed; medium confidence (≥ 0.50 and < 0.80). The executive applies its own persona-appropriate judgment; may resolve internally; may surface to user if non-obvious.

Each entry: full event description + evidence + proposed action + confidence value + rationale (why-this-is-judgment-not-routine).

### 4. `## Blocking`

User resolution required; low confidence (< 0.50). Must be surfaced to user; the report's `proposed_user_question` field is a starting point but the executive frames in its own voice.

Each entry: full event description + evidence + 2+ candidate interpretations + proposed user question + confidence value.

---

## Optional Body Sections

- `## Run Telemetry` — diagnostic data (timing per playbook step; tool invocations; lock acquisitions; etc.); useful for forensics
- `## Substrate Touched` — list of UIDs whose state changed during this pass; convenience for graph-walker validation

---

## Governance Rules

1. **sa.reconciler is the only author.** No other agent writes reconcile-report instances. Manual authorship is a substrate defect.
2. **Reports are immutable post-handoff.** Once sa.reconciler writes `[SHUTDOWN]` to its activation record, the report is sealed. Executive consumption is read-only.
3. **Empty categories appear explicitly.** A pass with zero blocking events still has a `## Blocking` section with `(none)`. Validator + executive both expect all four sections present.
4. **`events_applied + events_deferred = total_events_after_pattern_match`** must hold; validator-enforced. Accounting integrity.
5. **`events_by_category` sums to `total_events_after_pattern_match`** must hold; validator-enforced.
6. **Pattern-matched events name their pattern.** Each entry includes a `pattern_name:` field referencing an entry in the reconcile-imports.playbook pattern catalog. Unknown patterns are validator warnings.
7. **Reports persist; rolling archival deferred.** Reports stay in vault until rolling-archival ships (post-v1.25.0; v1.X scope per arch-spec OTQ 11). No automatic deletion.

---

## Validation Checks (run at check-in)

Core checks inherited from core.capsule v1.1. In addition:

1. **[enforced]** `type: reconcile-report`
2. **[enforced]** All required frontmatter fields present
3. **[enforced]** `trigger_path` is one of: `anomaly`, `scheduled`, `user-invoked`
4. **[enforced]** `scope` matches the regex `^(full-studio|folder:.+|operation:[0-9a-f]{8})$`
5. **[enforced]** `events_applied + events_deferred == total_events_after_pattern_match`
6. **[enforced]** Sum of `events_by_category` values equals `total_events_after_pattern_match`
7. **[enforced]** Body contains all 4 required sections in declared order
8. **[enforced]** `started_at <= completed_at`
9. **[honor-system]** Pattern-matched entries reference patterns that exist in the reconcile-imports.playbook catalog
10. **[honor-system]** Each event entry includes the four required attributes (event description; evidence; proposed action; confidence value) where applicable to its category
11. **[enforced]** `schema_version: 1`

---

## State Machine

```
draft (during sa.reconciler run)
   ↓ (sa.reconciler [SHUTDOWN])
active (executive consumes; immutable after handoff)
   ↓ (rolling archival; post-v1.25.0 scope)
archived (state: archived; historical record preserved)
```

| Status | Meaning |
|---|---|
| `draft` | sa.reconciler is composing the report mid-run; not yet handed off |
| `active` | Report sealed; handed to executive; available for downstream consumption (queries, audit, recovery) |
| `archived` | Rolling archival has retired the report from active queries; substrate preserves it as historical record |

**Valid transitions:**

- `draft → active` — sa.reconciler writes [SHUTDOWN]; report sealed and handed to executive
- `active → archived` — rolling archival cycle (post-v1.25.0); never automatic from sa.reconciler

---

## Relationship to Other Capsules

- **[core.capsule v1.1 (ee814120)](ee814120.md)** — inherited floor.
- **[external-artifact.capsule v1.0 (eedd7034)](eedd7034.md)** — reports describe actions on external-artifact instances.
- **[agent.capsule]** — sa.reconciler (the agent that authors reconcile-report instances) is an agent.capsule instance.
- **[playbook.capsule]** — reconcile-imports.playbook (sa.reconciler's playbook; ships in v1.25.0 Stream C) governs what events appear in the report and how they're categorized.
- **[task.capsule]** — blocking events surfaced to the user MAY spawn task entries for user follow-up; convention TBD in v1.X.

---

## Inheritance

Extends `core`. Inherits UID/owner/title/status/created/modified invariants. Adds report-specific accounting integrity rules + categorized body shape.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before consuming or authoring a reconcile-report.*

**Tools available:**

- `import-walker.py` — sa.reconciler invokes this; the tool does the work; sa.reconciler writes the report
- `tropo-validate.py` (amended in v1.25.0 Stream E) — enforces the report-integrity checks

**Skills:**

- sa.reconciler agent (v1.25.0 Stream C) — the only canonical author of reconcile-report instances
- Executive personas (Argus, Vela, etc.) — read reports + compose user-facing response in their own voice

**Procedures:**

- **Author flow (sa.reconciler-only):** during a reconciliation pass, sa.reconciler accumulates events; at Step 9 of the playbook, composes this report; at Step 10, writes [SHUTDOWN] and hands off.
- **Consume flow (executive):** executive reads frontmatter (mechanical triage); reads §Routine briefly (confirms nothing surfaced); reads §Pattern-matched (optional one-line surfacing to user); reads §Judgment (applies persona judgment); reads §Blocking (must surface to user; frames in its own voice).
- **Audit flow:** report's `audit_log_range:` points into journal.jsonl; full event-by-event trail recoverable.

**Rules (at-a-glance):**

1. sa.reconciler-only authorship.
2. Reports are immutable post-handoff.
3. All four categorized sections always present (empty marked explicitly).
4. Accounting integrity: events_applied + events_deferred = total events after pattern match.
5. Pattern-matched entries name their pattern (catalog reference).
6. Reports persist until rolling archival ships.
7. Executive composes user-facing voice; report is data, not narrative.

**Pitfalls:**

- Executive surfacing §Routine events to user → naggy; violates the intended posture.
- Manually authoring a reconcile-report → Rule 1 violation; substrate defect.
- Editing a sealed report → Rule 2 violation; report integrity broken.
- Omitting an empty section → Rule 3 violation; validator Check 7 failure.
- Inconsistent counts (events_by_category sum ≠ total) → Rule 5 violation; validator Check 6 failure.

**Worked examples:** None ship in v1.25.0. First real reports are produced when sa.reconciler runs its first pass post-ship.

**Go next:**

- Need to understand the agent that authors these? → [sa.reconciler agent (e4af1001)](e4af1001.md)
- Need to understand the playbook that drives the categorization? → [reconcile-imports.playbook (4a2f6dbd)](4a2f6dbd.md)
- Need to understand the entries reports describe actions on? → [external-artifact.capsule v1.0 (eedd7034)](eedd7034.md)
- Need the architectural reasoning? → [Import Primitive Architecture Specification v1.0 (2b49ba79)](2b49ba79.md) §A.4 + §C.7

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-05-13 | **LOCKED.** Initial definition. Authored in v1.25.0 Stream A per locked arch-spec [2b49ba79](2b49ba79.md) §C.7 + §A.4. Required + optional frontmatter; four required body sections (Routine / Pattern-matched / Judgment / Blocking); 7 governance rules; 11 validation checks (8 enforced + 3 honor-system); state machine; Studio shop-signage. Three-instrument verification: Argus build (this pass) + Stream G gauntlet pending. | argus-a60 |

---

*reconcile-report capsule definition | LOCKED v1.0 | UID 013b7b6e | locked 2026-05-13 by argus-a60 | v1.25.0 Stream A | three-instrument verification: Argus build complete; sa.cold-boot + sa.skeptic via Stream G gauntlet.*
*"Pure structured. Persona-agnostic. The agent does data; the executive does voice."*
