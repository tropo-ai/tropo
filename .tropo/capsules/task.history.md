---
uid: e71e654b
name: "task-history"
type: capsule-history
governs: 3289712a
governs_path: .tropo/capsules/task.capsule.md
extracted_at: 2026-05-11
extracted_by: argus-a56
extracted_in_cycle: "v1.19.0 — Convergence Phase 1"
extracted_in_release: pending-v1.19.0
schema_version: 2
governed_by: 5ec083a3
extraction_scope: argo-private
member_of:
  - "8dd772a0"
tags: [capsule-history, extracted-from-task-capsule, v1.19.0-stream-c]
---

# task — Capsule History

*History extracted from task.capsule v4.0.1 → v4.1 body refactor (v1.19.0 Stream C; 2026-05-11). Active capsule preserves: Required+Optional Frontmatter, State Machine (4-state with field-substates), 13 Governance Rules, 21 Validation Checks, Standard Task Body template, Extension from core. This file preserves: v3.0 + v4.0 + v4.0.1 amendment-block prose, Migration Notes v3.0 → v4.0, Migration Notes v2.0 → v3.0 (historical lineage), Inheritance/sibling-cascade narrative, Relationship-to-Other-Capsules narrative, §Studio — Shop Signage quick-ref, full changelog with v1.0-v4.0.1 lineage.*

---

## Amendment Blocks (extracted from v4.0.1 active body opener)

### v4.0 (2026-05-03, Argus A43; LOCKED)

Three-instrument verified across rounds 1+2 with round-3 single-instrument regression PASS-WITH-FINDINGS; 4 P2 doc-drift residuals folded pre-lock. v1.4.4 Stream A work-item primitives per [dev-pipeline + vault inbox primitive (e1c47a9f)](../../vault/files/e1c47a9f.md). **BREAKING.** Major changes:

- **Status enum collapsed from 8 states to 4** (`new` / `accepted` / `active` / `closed`). v3.0 substates (`requested`, `blocked`, `verify`, `rejected`, `cancelled`) are now expressed as fields, not states.
- **`owner:` field SEMANTICS REFINED** (NOT dropped). v3.0's `owner:` conflated "current driver" with "accountable entity." v4.0 splits the conflation: `owner:` is now purely the accountable entity, distinct from `processor:` (multi-valued, currently driving) and `requested_by:` (originator). Optional field; set on `new → accepted`; defaults to first entry in `accepted_by:` materialized at accept-time (NOT continuously re-evaluated). Singular UID. Mutable by explicit reassignment.
- **`accepted_by:` array of acceptance records** added (universal work-item primitive). Each record: `{accepted_by_uid, date_accepted, date_completed, date_rejected, notes}`. Multi-pipeline-run / multi-agent processing is first-class.
- **`processor:` derived array** added — the currently-active acceptors. Computed-on-read by default.
- **`approver:` field added** (single, optional). Distinct from `verifier:`. Verifier asks "is the work technically correct?"; approver asks "is this acceptable to ship?".
- **`approval_required:` boolean flag** added (default `false`) — when `true`, gates `closed (resolution: done)` on approver being set.
- **`blocked:` boolean + `blocked_reason:` text + `blocked_by:` UID** added — blocking is a flag on `status: active`, not a separate state.
- **`resolution:` enum** added (`done` / `rejected` / `cancelled`) — required when `status: closed`.
- **`informs:` array** added (optional) — notification list with no state-machine effect.
- **Verification independence is now a SOFT rule (recommended, not enforced).** v3.0's `owner ≠ verifier` invariant is dropped as a hard validation check.

### v3.0 (2026-04-23, Argus A32)

v2 substrate compliance per [Tropo Work v2 Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md). **Decouples intrinsic `status:` from pipeline-position.** v2.0's overloaded `stage:` field is replaced by two orthogonal fields: `status:` (work-item intrinsic lifecycle) + `pipeline_position:` (set on pipeline-runs, not on work-items). Adds request-lifecycle fields (`requested_by:`, `requested_of:`) + clarifies `owner:` timing. New 8-state status vocabulary. Preserves owner≠verifier invariant. Breaking for v2.0; migration via v1.4 Stream 1 script.

### v4.0.1 (2026-05-10, Argus A54)

v1.16.0 Stream A — §Worked examples (ship) citation cleanup. Removed 3 citations to non-shipping UIDs (b8c4e1f2, a1f5b8d2, c7d3a9e4) per backlog [5a4e9c2b](../../vault/files/5a4e9c2b.md) (Cold-Boot 098 P1 finding). Schema, validation rules, frontmatter shape — all unchanged. Inline abstract YAML examples preserved as canonical schema-documentation. Lock-break authorized by Mike-A54 at v1.16.0 walk Q1 2026-05-10.

---

## Migration Notes — v3.0 → v4.0 (preserved for migration script reference)

**v3.0 8-state `status:` collapses to v4.0 4-state + field flags. v3.0 `owner:` becomes the first record in `accepted_by:`.** Migration is mechanical and deterministic.

### Status enum mapping

| v3.0 `status:` | v4.0 `status:` | v4.0 fields set |
|---|---|---|
| `requested` | `new` | (none — same as `new` semantics) |
| `accepted` | `accepted` | `accepted_by:` populated with v3.0 `requested_of:` as first record |
| `active` | `active` | `accepted_by:` populated with v3.0 `owner:` as first record; `owner:` preserved with refined accountable semantics |
| `blocked` | `active` | + `blocked: true`, `blocked_reason:` preserved |
| `verify` | `active` | + `accepted_by:` populated with v3.0 `owner:`; `verifier:` field set if v3.0 had it. **MIGRATION-AMBIGUOUS branch:** if v3.0 instance was at `verify` but `verifier:` was not recorded, migration loses the gate-pending semantic. Migration script flags for manual review. |
| `done` | `closed` | + `resolution: done` |
| `rejected` | `closed` | + `resolution: rejected` |
| `cancelled` | `closed` | + `resolution: cancelled` |

### Owner field migration

v3.0 `owner:` (single UID, set on `accepted → active`) maps to BOTH:

1. **v4.0 `owner:` field preserved** — the same UID survives at v4.0 with refined semantics (purely accountable). No data loss.
2. **A new record in `accepted_by:`** — `accepted_by_uid:` = v3.0 owner UID; `date_accepted:` = task's transition-to-active date (or v3.0 `modified:` if not recoverable); `date_completed:` = v3.0 transition-to-done date if `status: done`; `notes:` = "Migrated from v3.0 owner field".

After migration, `processor:` is derived from `accepted_by:` per the §Aggregate Rule. Migration is **information-preserving, not lossy**.

### New v4.0 fields default

For migrated v3.0 entries: `owner:` preserved; `approver:` absent; `approval_required:` `false`; `blocked:` `true` if migrated from v3.0 `status: blocked` else `false`/absent; `blocked_reason:` preserved if v3.0 had it; `blocked_by:` absent; `informs:` absent; `resolution:` set per status mapping above.

### Migration script

Mechanical, deterministic, dry-run-able. Ships with v1.4.4. Validates by re-running v4.0 validation checks against migrated entries.

---

## Migration Notes — v2.0 → v3.0 (historical lineage)

v2.0's `stage:` field decouples as follows:

| v2.0 `stage:` | v3.0 `status:` | v3.0 `pipeline_position:` |
|---|---|---|
| `ideate` | `accepted` (default; flip to `active` at next-touch) | (not on task) |
| `build` | `active` | (not on task) |
| `verify` | `verify` | (not on task) |
| `done` | `done` | (not on task) |
| `cancelled` | `cancelled` | (not on task) |
| `rejected` | `rejected` | (not on task) |

**Request-lifecycle backfill:** v2.0 tasks have no `requested_by:` / `requested_of:` fields. Migration script adds them: `requested_by:` = `created_by:`; `requested_of:` = v2.0 `owner:` (or creating project's owner if no v2.0 owner). Orphan cases assigned to the vault-entity.

**Pipeline-position:** tasks tracked in pipeline context via v2.2 project.capsule's `active_pipeline:` field lose that context in v3.0. Migration script authors a companion pipeline-run entry per spec §6.2 with the task as a member. Orphan cases flagged for manual review.

Full migration script in Stream 1 D1.3 (Vela-lane deliverable; authored post-capsule-lock).

---

## Studio — Shop Signage (extracted)

*Preserved per Mike-A55 directive: capsules are agent-read, not human-read.*

### Tools available

- `python3 .tropo/scripts/tropo-validate.py` — runs capsule validation checks
- `python3 .tropo/scripts/rebuild-vault.py --apply` — regenerates `vault/00-index.jsonl`; catches missing `member_of:` + orphan tasks
- Migration script at `scripts/migration-v2/migration-script.py` (Stream 1 D1.3) — backfills v2.0 → v3.0 schema

### Skills

- `request-work.skill.md` *(forthcoming v1.5)* — authors a new task with request-lifecycle fields populated
- `verify-task.skill.md` *(forthcoming v1.5)* — captures verifier attestation at verify→done transition
- `sa.cold-boot` activation-log protocol — authors a `status: active` verification task on an artifact

### Procedures

- `agent-activation.playbook.md` — agents that boot may be handed tasks at `status: new`
- `sa.skeptic` dispatch protocol — authors an adversarial-review task on a governance artifact
- Three-instrument verification regime — triad of review/cold-boot/build against a locked artifact's task-tree

### Pitfalls

- **(v4.0)** Treating `owner:` as a driver field → owner is purely accountable in v4.0; current drivers are in `processor:` (multi-valued, derived from `accepted_by:`)
- **(v4.0)** Expecting v3.0's 8-state status (`requested`/`verify`/`blocked`/`done`/`rejected`/`cancelled`) to work → collapsed to 4-state in v4.0; substates expressed as fields (`blocked: true`, `verifier:` set, `resolution:`)
- Authoring a task without `member_of:` → violates D7; orphan routing via vault-inbox
- Expecting `stage:` to work → gone in v3.0; migration script handles v2.0 carryover
- Mutating `requested_by:` post-first-author → violates Rule 5; preserve provenance
- Forcing parent-done → children-done lockstep → violates Rule 4a; composition is graph, not lifecycle-sync
- **(v4.0)** Setting `blocked: true` outside `status: active` → only meaningful when active; validation check 14 catches
- **(v4.0)** Setting `approval_required: true` without naming an approver before close → state machine blocks `closed (resolution: done)` until `approver:` is set
- **(v4.0)** Setting `status: closed` without `resolution:` → validation check 9 catches
- **(v4.0)** Expecting verification independence to be enforced → it's a SOFT recommendation in v4.0 (Rule 1)

### Worked examples (schema documentation)

The abstract YAML instances below carry the canonical schema-documentation purpose. They are intentionally abstract (no real-world UID references) so the schema reads cleanly without coupling to development-internal artifacts.

**Minimal v4.0 task (`status: new`, optional owner unset):**

```yaml
---
uid: c4d5e6f7
type: task
title: "Migrate v3.0 task instances to v4.0 schema"
status: new
state: active
created: 2026-05-03
created_by: argus-a43
modified: 2026-05-03
requested_by: mike
requested_of: argus-a43
member_of: [c8047001]
priority: p1
---

## Intent
Convert all v3.0 task entries in the Vault to v4.0 schema using the migration script.

## What to Do
Run scripts/migrate-tasks-v3-to-v4.py in dry-run mode; review the output; run live; validate.

## Verification
All v3.0 tasks pass v4.0 validation post-migration. No information loss (owner preserved + accepted_by populated).
```

**v4.0 task at `status: closed (resolution: done)` with full role model:**

```yaml
---
uid: d7e8f9a0
type: task
title: "Lock note.capsule v3.2 amendment"
status: closed
resolution: done
state: archived
created: 2026-05-03
created_by: argus-a43
modified: 2026-05-04
requested_by: mike
owner: argus-a43
accepted_by:
  - accepted_by_uid: argus-a43
    date_accepted: 2026-05-03
    date_completed: 2026-05-04
    notes: "Authored amendment + folded BATCH findings."
verifier: sa.cold-boot
verification_method: cold-boot
member_of: [c8047001]
---
```

### Argo development examples (argo-reference)

- v1.4 Gate tasks: c1a3f8b4, f8d4a2c9, 9e4b7f3c, 2f7a9c4b, 6b3e8d1a
- Stream D deferred tasks: 17e70d10, 7a2b4f91, b688fc82, 3f9e2a71, 8d4c7f91

*Argo examples are deliberately argo-reference scope: they demonstrate the pattern in Tropo's own development vault, but fresh installs don't carry development-internal tasks.*

### Go next

- Need to name an actor (who requests/owns/verifies)? → [entity.capsule (1e9c3f7a)](entity.capsule.md)
- Task belongs in a project? → [project.capsule (34e4cb0b)](project.capsule.md)
- Task is member of a pipeline-run? → [pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)

---

## Inheritance + Sibling-Cascade Narrative (extracted)

Extends `core`. Inherits UID immutability, type immutability, owner/created/modified invariants.

v3.0 established the WorkItem request-lifecycle pattern. Sibling typed-artifact capsules (`design-brief`, `arch-spec`, `build`, `release`, `note`, `document`, `concept`, `decision`, `test-scenario`, etc.) align their required frontmatter tables to match the status/request-lifecycle model.

**Sibling-cascade at v1.4.4 (this bundle).** task v4.0 shipped in v1.4.4 Stream A alongside note v3.2 + design-brief v3.1 — the universal work-item primitives (`accepted_by:` array, `processor:` derived) are textually identical across all three capsules. Decision (the 4th work-item type) was queued as v1.4.5 candidate per [127d2fe2](../../vault/files/127d2fe2.md). The "per-sibling amendments" path was chosen over a shared `work-item.capsule` intermediate layer to keep type-specific richness in each capsule — earn-the-abstraction principle.

---

## Relationship to Other Capsules — Narrative (extracted)

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor
- **[entity.capsule (1e9c3f7a)](entity.capsule.md)** — `requested_by:`, `requested_of:`, `owner:`, `verifier:` all reference entity UIDs
- **[project.capsule (34e4cb0b)](project.capsule.md)** — `member_of:` points at projects
- **[pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)** — pipeline-runs may have tasks as members; pipeline-runs carry pipeline-position, tasks do not

---

## Extension from core (extracted)

*Where this capsule specializes the core.capsule (ee814120) floor.* task.capsule v4.0 extends core: **title** allowed up to 120 chars (core: 100; tasks need room for descriptive titles); **status** is the lifecycle enum (core's generic `status:` field; task specifies the 4-state v4.0 vocabulary); **owner** is OPTIONAL with refined accountable-only semantics (core treats `owner:` as a singular driver/accountable field; task v4.0 splits driver semantics into multi-valued `processor:` and keeps `owner:` purely accountable, optional, defaulting to first acceptor).

---

## Changelog (full lineage)

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | — | original | tropo |
| 1.1 | — | closure procedure added | tropo |
| 1.2 | 2026-04-13 | project required | tropo |
| 1.3 | 2026-04-13 | projects: [] array | A22 |
| 2.0 | 2026-04-16 | v2 schema: projects → member_of, status → stage + state, simplified state machine aligned with v2 vocabulary | A24 |
| 3.0 | 2026-04-23 | BREAKING: v2 substrate compliance. Decouple v2.0's `stage:` into `status:` (intrinsic) + pipeline_position (on pipeline-runs only). Add `requested_by:` / `requested_of:` required fields. Clarify `owner:` timing. New 8-state status vocabulary. Root-accept propagation rule per spec §2.3. Migration table maps v2.0 → v3.0 mechanically. | argus-a32 |
| 4.0 | 2026-05-03 | LOCKED — BREAKING: v1.4.4 Stream A work-item primitives. Status enum collapsed from 8 to 4. `owner:` PRESERVED with refined accountable-only semantics (post-BATCH remediation per skeptic Decision 1 #1) — distinct from `processor:` and `requested_by:`. Added `accepted_by:` array. Added `processor:` (derived). Added `approver:` + `approval_required:` (distinct from verifier). Added `blocked:` flag + `blocked_reason:` + `blocked_by:`. Added `resolution:` enum required at `status: closed`. Added `informs:` array. Rule 1 SOFTENED — verification independence is recommended, not enforced. `requested_of:` moved to Optional with conditional-required wording. Rules 10 + 11 added (approver semantics, resolution immutability). 11 new validation checks. §Aggregate Rule added to State Machine. `accepted → active` transition trigger documented. Migration v3.0 → v4.0 is mechanical and information-preserving (not lossy). | argus-a43 |
| 4.0.1 | 2026-05-10 | Patch — §Worked examples (ship) citation cleanup. Removed 3 citations to non-shipping UIDs per backlog 5a4e9c2b (Cold-Boot 098 P1 finding; 10-day pending closure). Schema, validation rules, frontmatter shape — all unchanged. Inline abstract YAML examples preserved as canonical schema-documentation. Lock-break authorized by Mike-A54 at v1.16.0 walk Q1 2026-05-10. | argus-a54 |
| 4.1 | 2026-05-11 | **v1.19.0 Stream C — Capsule Pedagogy Completion.** Body refactor to 5-section pedagogy pattern (Intent → Schema → State Machine → Validation Rules → Composes-With) per Mike-A55 *"capsules are agent-read, not human-read"* directive. Active body reduced from 509 → ~280 lines (~45% reduction). Substrate-load-bearing content preserved: Required+Optional Frontmatter, State Machine with field-substates, 13 Governance Rules, 21 Validation Checks, Standard Task Body template. Extracted to history: v3.0/v4.0/v4.0.1 amendment-block prose, Migration Notes v3.0→v4.0 + v2.0→v3.0, Inheritance+Sibling-Cascade narrative, Relationship-to-Other-Capsules narrative, §Studio quick-ref, full changelog. **No schema changes, no validation rule changes, no governance rule changes, no state machine changes.** UID `3289712a` preserved. | argus-a56 |

---

## Provenance

- **Extracted at:** 2026-05-11
- **Extracted by:** argus-a56
- **Active capsule version at extraction:** v4.0.1 (509 lines)
- **Active capsule version after extraction:** v4.1 (~280 lines; ~45% reduction)
- **Extraction-fidelity check:** All historical content preserved. Active capsule retains all schema + state machine + 13 governance rules + 21 validation checks.

---

*task capsule history | UID e71e654b | v1.19.0 Stream C extraction 2026-05-11 by Argus A56 | Bidirectional pair: governs 3289712a*
