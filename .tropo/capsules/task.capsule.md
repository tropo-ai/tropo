---
subsystem_hub:
  - "2d083137"
uid: 3289712a
name: "task"
type: capsule-definition
extends: core
version: "4.3"
supersedes_version: "4.2"
tier: os
author: tropo
created: 2026-04-10
modified: 2026-06-09
modified_by: argus-a106
status: locked
locked_by: argus-a98
locked_at: 2026-06-04
enforced_enums:
  status: [new, accepted, active, closed]
  state: [active, archived]
meta_status_rollup:
  to-do: [new, accepted]
  in-progress: [active]
  done: [closed]
v4_3_lock_break: "v4.2 -> v4.3 lock-break Mike-A106-signed 2026-06-09 (approved via gate-package: 'Sign the lock-break'). Adds task-level VERIFIER-INDEPENDENCE for approvers: NEW Governance Rule 14 (approver independence enforced — resolved approver MUST differ from resolved executor [owner ∪ accepted_by uids] UNLESS principal_class:human) + NEW Validation Check 22 (check_task_approver_distinct_from_executor, WARN→ERROR ratchet, forward-looking — 0 current matching tasks). Implements Metis's proposal 9a8c9adc via dev-spec d996b941 (2 gauntlet rounds) under ADR-044 (no new ADR; enforce at L1). The check rides on the shared identity resolver .tropo/scripts/lib/_identity.py (L0c — Talos engine lane, extracted from 9e7003b1.py, hard-fail-on-import per AC-L0c-fail) + the principal_class human-discriminant backfilled crew-wide this session (L0a, Mike-A106-blessed). Verifier independence (Rule 1) stays recommended-not-enforced; this is the APPROVER-side counterpart only. Additive — no existing field/rule/check changed."
v4_2_lock_break: "v4.1 -> v4.2 lock-break Mike-A98-signed 2026-06-04 (verbatim 'go'). Populates the enforced_enums block (the slot core.capsule v1.3 added): status [new,accepted,active,closed] agrees with Validation Check 1 (:203) + state [active,archived] agrees with Check 2 (:204). Purely additive -- no existing field, rule, or check changed. Makes task the enforced single source for its own status/state vocabulary; the validator d2b9c8e6.py reads this block directly and WARNs the 35 live status-drift values (done 27/open 8); state is clean. ENFORCE step of the Field-Semantics Map (476fef2e) per addc4490 v0.5 -- task is the first type piloted."
last_body_refactor: 2026-05-11
history_file: e71e654b
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — 5-section pedagogy
aligned_with:
  - f2e8a7b1   # Tropo Work v2 Architecture Specification
  - 8b3f1d92   # Tropo Work v3 Architecture Specification
  - e1c47a9f   # dev-pipeline + vault inbox primitive
tags: [capsule-definition, task, work-item, 5-section-pedagogy, v1.19.0-stream-c-refactored]
---

# task — Capsule Definition v4.1

## 1. Intent

Track discrete units of work from request through verification. A task is a unit of work with intent, request-lifecycle, multi-acceptor processing, verification gate, optional approval gate, and composition edges. Tasks are the most common `WorkItem` subtype in the Vault.

Every task has:

- **Request lifecycle** — who asked whom (`requested_by:` → `requested_of:`), accept/reject/re-request semantics
- **Intrinsic status** — 4 states (`new` / `accepted` / `active` / `closed`) aligned with the universal work-item lifecycle, independent of any pipeline context
- **Acceptors and processors** — `accepted_by:` array carries the agreement audit trail (multi-acceptor / multi-pipeline-run); `processor:` is the derived view of currently-active acceptors
- **Owner** — the singular accountable entity ("whose name is on this if it drifts"). Distinct from `processor:` (current drivers, plural) and `requested_by:` (originator). Optional; set on `new → accepted`; defaults to first acceptor materialized at accept-time.
- **Verifier** — entity that certifies the work meets technical acceptance. Verification independence is recommended but not enforced (Rule 1).
- **Approver (optional)** — when `approval_required: true`, the entity that signs off before `status: closed (resolution: done)`. Distinct from verifier.
- **Composition edges** — graph relationships (`has-subtasks`, `depends-on`, `blocked-by`, etc.) via `relationships:`

**A task's status is NOT a pipeline position.** If a task is being processed as a member of a pipeline-run, the pipeline-run tracks its own `current_stage:` + `current_step:` — those do not appear on the task. Work-items are substrate; pipelines + pipeline-runs are flow over the substrate.

Tasks share universal work-item primitives (`status:`, `accepted_by:`, `processor:`) with sibling typed-artifact capsules (`note`, `design-brief`, `decision`); each carries its own type-specific richness.

Failure mode prevented: silent driver/accountable conflation in v3.0 (`owner:` doing two jobs); pipeline position bleeding into work-item state (v2.0 `stage:` overload); rigid 8-state vocabulary that doesn't match how work actually flows; verification independence rigidity preventing legitimate self-verification in small/mechanical workflows.

---

## 2. Schema

### Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `title` | string | ≤120 chars |
| `status` | enum | `new` / `accepted` / `active` / `closed` (v4.0 — 4 states) |
| `requested_by` | UID | Required from `new` onward; persists through entire lifecycle. Immutable after first-author. Resolves to an entity. |
| `member_of` | UID array | Projects this task belongs to. At least one required; at least one must resolve to a vault-entity-owned project (D7 invariant — enforced via vault-inbox fallback). |
| `state` | enum | `active` / `archived`. Lifecycle-visibility flag per core conventions. |
| `resolution` | enum | Required when `status: closed`. One of `done` / `rejected` / `cancelled`. Captures the terminal variant. Immutable once set (Rule 11). |

**Inherited core fields:** `uid`, `type` (= `"task"`), `created`, `modified`, `state`. Tasks additionally carry `created_by:`.

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `requested_of` | UID | Required from `new` through `accepted`; optional at `active`/`closed`. Resolves to an entity. Changes legally on re-request after rejection. |
| `owner` | UID | **v4.0 refined.** Singular accountable entity. Distinct from `processor:` and `requested_by:`. Set on `new → accepted`; defaults to first entry in `accepted_by:` **materialized at accept-time** (frozen — NOT continuously re-evaluated; Rule 12). Mutable by explicit reassignment. NOT a driver field — that's `processor:`. |
| `accepted_by` | record array | **v4.0.** Acceptance records — agents and/or pipeline-runs that have committed to processing. Each record: `{accepted_by_uid, date_accepted, date_completed, date_rejected, notes}`. Multi-acceptor / multi-pipeline-run is first-class. |
| `processor` | UID array | **v4.0.** Derived view over `accepted_by:` records that have `date_accepted:` set and no `date_completed:`/`date_rejected:` — the currently-active acceptors. Computed-on-read by default; materialization is query-cache implementation detail. |
| `verifier` | UID | Required when `status: closed` AND `resolution: done` (unless verification explicitly skipped per capsule policy). Verification independence recommended but not enforced (Rule 1). |
| `approver` | UID | **v4.0.** Required when `approval_required: true` AND `status: closed` AND `resolution: done`. Distinct from `verifier:` conceptually; same UID MAY appear in both fields when one entity serves both roles. |
| `approval_required` | boolean | **v4.0.** Default `false`. When `true`, state machine enforces approver gate before `status: closed (resolution: done)`. |
| `blocked` | boolean | **v4.0.** Only meaningful when `status: active`. Default `false`. Variant of `active`, not a separate state. |
| `blocked_reason` | string | **v4.0.** Required if `blocked: true`. Human-readable blocker description. |
| `blocked_by` | UID | **v4.0.** Optional when `blocked: true`. UID of blocking entry. |
| `informs` | UID array | **v4.0.** Notification list — no state-machine effect; tracked for visibility. |
| `priority` | enum | `p0` / `p1` / `p2` / `p3` |
| `due` | ISO date | Optional deadline |
| `verification_method` | enum | `cold-boot` (default) / `manual` / `peer-review`. Used when verifier is set. |
| `relationships` | typed-edge array | Standard verbs: `has-subtasks` / `subtask-of`, `depends-on` / `blocked-by`, `attached-to`, `derived-from` / `composes-into`, `supersedes` / `superseded-by`, `references`. |

### Body shape — Standard Task Body

Every task body MUST follow this structure:

```markdown
## Intent

Why this task exists. What problem it solves. What would happen if it were never done.

## What to Do

Concrete steps or specification. Enough detail that an agent with no prior context could execute.

## Verification

How to know the task is done. Acceptance criteria the verifier checks.

**Verification method:** cold-boot | manual | peer-review
*(If not cold-boot, state the reason here.)*
```

---

## 3. State Machine

**4 states (v4.0, collapsed from v3.0's 8). Substates that mattered in v3.0 are expressed as fields, not states.**

```
new → accepted → active ⇌ active+blocked → closed (resolution: done | rejected | cancelled)
       ↑___________↓ (re-request: status returns to new if all acceptances rejected)
```

| Status | Meaning |
|---|---|
| `new` | Request pending. No live acceptance record in `accepted_by:`. Task has been requested but no one has committed. |
| `accepted` | At least one acceptance record exists with `date_accepted:` set; processing not yet started. |
| `active` | At least one processor working the task. May be additionally `blocked: true` while waiting on external dependency. May be in verify or approve gate (tracked via `verifier:` / `approver:` field state, not separate status). |
| `closed` | Terminal. `resolution:` captures variant: `done` (completed, verified, approved if required), `rejected` (request died), `cancelled` (work abandoned). Body becomes read-only at close (Rule 8). |

### What used to be states are now fields (v4.0 collapse)

| v3.0 state | v4.0 captures it as |
|---|---|
| `requested` | `status: new` + `requested_of:` set + no live records in `accepted_by:` |
| `blocked` | `status: active` + `blocked: true` + `blocked_reason:` + optional `blocked_by:` |
| `verify` | `status: active` + `verifier:` unset (gate pending) → set (gate passed) |
| approve gate (NEW) | `status: active` + `approval_required: true` + `approver:` unset → set |
| `done` | `status: closed` + `resolution: done` |
| `rejected` | `status: closed` + `resolution: rejected` |
| `cancelled` | `status: closed` + `resolution: cancelled` |

### Done-state validation

A task flips `active → closed (resolution: done)` only when:

1. **Verifier set** (unless verification explicitly skipped per capsule policy). Independence is recommended but not enforced (Rule 1).
2. **If `approval_required: true`:** `approver:` is set.

Otherwise, `active → closed` requires `resolution: rejected` (request died) or `resolution: cancelled` (work abandoned).

### Aggregate Rule (status alignment with accepted_by)

- All records empty / all rejected → `status: new`
- ≥1 live record, no processing started → `status: accepted`
- ≥1 processor currently acting → `status: active`
- All processors completed AND verifier set (and approver if required) → `status: closed (resolution: done)`
- Closed by any other path → `status: closed (resolution: rejected | cancelled)`

The `status:` field is stored explicitly for query efficiency and to capture intent. Consistency between stored `status:` and `accepted_by:` is enforced at write-time by Check 21.

**`accepted → active` transition trigger.** Fires when a processor begins editing the task's body, populates an output artifact, or explicitly flips `status:` from `accepted` to `active`. By convention — the agent declares it active when they begin work.

### Valid transitions

- `new → accepted` — first acceptor writes record with `date_accepted:` set
- `new → closed (resolution: rejected)` — requester closes without finding acceptor
- `accepted → active` — processor begins work
- `accepted → new` — all acceptance records get `date_rejected:` set; returns to pending re-routing
- `accepted → closed (resolution: cancelled)` — request abandoned before work begins
- `active → closed (resolution: done)` — verifier set; approver set if `approval_required: true`
- `active → closed (resolution: cancelled)` — work abandoned mid-flight
- `closed (resolution: done) → active` — regression reopen (requires `resolution:` cleared + different verifier on re-close per Rule 7)
- Any terminal → `state: archived` — lifecycle visibility flip; `status:` and `resolution:` preserved

### Per-record rejection vs top-level `closed (resolution: rejected)`

Both coexist: per-record `date_rejected:` on an `accepted_by:` entry = "this acceptor said no." Top-level `status: closed` + `resolution: rejected` = "the task as a whole closed without finding any successful acceptor."

Verification may be skipped if capsule-rule or work-item class doesn't mandate it (e.g., simple internal tracking task); transition `active → closed (resolution: done)` is legal with `verifier:` absent.

---

## 4. Validation Rules

### Governance Rules (13, in addition to core)

1. **Verification independence (RECOMMENDED, NOT enforced — v4.0).** When `verifier:` is set, it SHOULD differ from entries in `accepted_by:` whenever practical — independent verification catches what self-review misses. **NOT a hard invariant.** Small/mechanical/solo workflows may legitimately self-verify. v4.0 explicitly drops v2.0/v3.0's `owner ≠ verifier` validation check.
2. **Every task belongs to at least one vault-entity-owned project.** `member_of:` required non-empty; at least one entry must resolve to a project whose `owner:` chains to the vault-entity (D7 invariant). Vault-inbox catches orphans automatically.
3. **Status transitions follow the v4.0 state machine.** Skipping states is not permitted. Substates (`blocked`, `verify`, `approve`) are not transitions — they are field changes within `status: active`.
4. **Request propagation at root-accept.** When a task with child tasks (via `has-subtasks` edges) is accepted, children's `requested_of:` propagates per spec §2.3 — children transition to `status: new, requested_of: <root-recipient>`. Recipient may reject/delegate children individually post-acceptance.
4a. **Child-subtask lifecycle independence after root-accept.** After Rule 4 propagation, children track their own lifecycle independently. Parent's subsequent state transitions do NOT force child transitions. A parent at `closed (resolution: done)` may have children still at `active` or `accepted` — legal and common. Per-task capsule-rule MAY declare parent-blocks-on-children via `depends-on:` edges, but default is independence. Composition is graph structure, NOT lifecycle lockstep.
5. **`requested_by:` is immutable after first-author.** Once set, does not change. Rejections do not clear it. Re-requests preserve `requested_by:` and update `requested_of:`.
6. **Per-record rejections logged on the acceptance record (v4.0).** Each acceptor's rejection lives on their `accepted_by:` record (`date_rejected:` set, `notes:` carries the reason). Top-level `closed (resolution: rejected)` is set by the requester after acceptances all reject and re-routing isn't pursued.
7. **Regression reopening requires audit trail.** When a `closed (resolution: done)` task moves back to `active`, prior `resolution:` is cleared (reason recorded), and a different entity must perform the second verification when the task re-closes.
8. **Closed tasks are read-only.** When `status: closed`, body content is immutable regardless of `resolution:` value. State-level archival permitted; body and resolution remain frozen.
9. **Auto-accept optimization.** If recipient's `auto_accept_from:` contains the requester's UID, the request skips `status: new` and lands directly at `accepted` with auto-written record.
10. **Approver semantics (v4.0).** When `approval_required: true`, `approver:` MUST be set before `closed (resolution: done)`. Conceptually distinct from `verifier:` (verifier asks "is the work technically correct?"; approver asks "is this acceptable to ship?"). Same UID MAY appear in both fields when one entity serves both roles.
11. **Resolution immutability (v4.0).** Once `status: closed` is set with `resolution:`, that resolution is immutable. Regression reopen (Rule 7) clears it.
12. **Owner default semantics on rejection-cycle (v4.0).** `owner:` default ("first entry in `accepted_by:`") is **materialized at accept-time** — frozen at that point, NOT continuously re-evaluated. If first acceptor's `date_rejected:` is later set, `owner:` does NOT automatically point at a different acceptor. Explicit reassignment required.
13. **Self-verification is invokable at any status (v4.0).** `verifier:` field MAY be set/updated/refreshed at any status — not only at closure. Mid-stream verifier updates create audit trail in long-running work without advancing the status machine. The terminal verifier (whose attestation gates `closed AND done`) is whichever entity is in `verifier:` at the moment of close.
14. **Approver independence — ENFORCED (v4.3, verifier-independence; Mike-A106-signed lock-break).** When `approval_required: true` and the task reaches `closed (resolution: done)`, the resolved `approver:` identity MUST differ from the resolved executor identity (`owner:` ∪ each `accepted_by[].accepted_by_uid`) — an entity cannot sign off its own work — **UNLESS** the approver's `principal_class` is `human` (a human principal retains final-approval latitude over their own work; agent-principals do not). This is the approver-side counterpart to verifier independence, which stays *recommended-not-enforced* (Rule 1). Implements [d996b941](../../vault/files/d996b941.md) under ADR-044; enforced by Check 22.

### Validation Checks (22, ERROR-severity at check-in unless noted)

1. `status:` ∈ {`new`, `accepted`, `active`, `closed`}
2. `state:` ∈ {`active`, `archived`}
3. Status transition (if any) is in valid transitions list
4. `requested_by:` present non-null at all states; resolves to entity; immutable after first-author (Rule 5)
5. `requested_of:` present non-null when `status ∈ {new, accepted}`; resolves to entity. May be absent at `active`/`closed`.
6. `member_of:` present non-empty; at least one entry resolves to a vault-entity-owned project (D7 invariant)
7. `title:` ≤120 chars; no forbidden chars
8. **(v4.0)** If `owner:` present, resolves to entity. (OPTIONAL in v4.0; absence is legal — validator no longer flags missing owner.)
9. **(v4.0)** If `status: closed`: `resolution:` present and ∈ {`done`, `rejected`, `cancelled`}
10. **(v4.0)** If `accepted_by:` present, every entry is a structured record with required `accepted_by_uid:` (resolves to entity or pipeline-run) and `date_accepted:` (ISO date), plus optional `date_completed:`, `date_rejected:`, `notes:`
11. **(v4.0)** If `processor:` materialized in frontmatter, every entry corresponds to a live acceptance record in `accepted_by:`
12. **(v4.0)** If `status: closed (resolution: done)`: `verifier:` present (resolves to entity). Unless task explicitly skips verification per capsule policy. **No independence enforcement** — Rule 1 v4.0 softening.
13. **(v4.0)** If `status: closed (resolution: done)` AND `approval_required: true`: `approver:` present (resolves to entity)
14. **(v4.0)** If `blocked: true`: `blocked_reason:` present (non-empty); only legal when `status: active`
15. **(v4.0)** If `blocked_by:` present, resolves to a live vault entry; only meaningful when `blocked: true`
16. **(v4.0)** If `informs:` present, every UID resolves to entity
17. **(v4.0)** If `approval_required: true`, `approver:` field timing follows Rule 10
18. If `verification_method:` is `manual` or `peer-review`, `## Verification` body section contains a stated reason
19. If `priority:` present, value ∈ {`p0`, `p1`, `p2`, `p3`}
20. *(honor-system)* `stage:` field absence (v3.0+ compliance — v2.0 field must not appear on v3.0+/v4.0-authored tasks)
21. **(v4.0)** Aggregate consistency: stored `status:` aligns with §Aggregate Rule's derivation from `accepted_by:` and lifecycle state. Drift caught at check-in.
22. **(v4.3, verifier-independence — WARN→ERROR)** `check_task_approver_distinct_from_executor`: on `type: task` + `approval_required: true` + `status: closed` + `resolution: done` — `approver:` set AND resolves (shared `_identity._resolve_principal_uid`) to a registered ACTIVE principal AND `resolved(approver)` ∉ {`resolved(owner)`} ∪ {`resolved(accepted_by[].accepted_by_uid)`}, **UNLESS** `_get_principal_class(resolved(approver)) == human`. **WARN this cycle → ERROR next ratchet** (not require-0 yet). Forward-looking — 0 current matching tasks (190 closed-done, none approval-required). Per Rule 14 + dev-spec [d996b941](../../vault/files/d996b941.md); rides on the shared resolver `.tropo/scripts/lib/_identity.py` (L0c, Talos engine lane).

Core checks inherited: UID uniqueness + immutability, type immutability, owner/created/modified invariants.

---

## 5. Composes-With

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor (UID immutability, type immutability, owner/created/modified invariants).
- **[entity.capsule (1e9c3f7a)](entity.capsule.md)** — `requested_by:`, `requested_of:`, `owner:`, `verifier:`, `approver:`, `informs:` all reference entity UIDs.
- **[project.capsule (34e4cb0b)](project.capsule.md)** — `member_of:` points at projects; D7 invariant requires at least one vault-entity-owned project.
- **[pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)** — pipeline-runs may have tasks as members; pipeline-runs carry pipeline-position, tasks do not.
- **[note.capsule (db3a8e51)](note.capsule.md)**, **[design-brief.capsule (de5181b0)](design-brief.capsule.md)**, **[decision.capsule](decision.capsule.md)** — sibling typed-artifact capsules sharing universal work-item primitives (`status:`, `accepted_by:`, `processor:`). The v1.4.4 sibling-cascade aligned note v3.2 + design-brief v3.1 + task v4.0 with textually identical work-item primitives.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.

### History

The v3.0/v4.0/v4.0.1 amendment-block opener prose, Migration Notes v3.0 → v4.0 (status enum mapping, owner field migration, new v4.0 fields default, migration script), Migration Notes v2.0 → v3.0 (historical lineage), Inheritance + sibling-cascade narrative, Relationship-to-Other-Capsules narrative, Extension from core, §Studio — Shop Signage authoring procedure (human-facing quick-ref with tools, skills, procedures, pitfalls, worked examples, argo-reference examples), and full changelog (v1.0 through v4.1) are preserved in the companion [task.history.md (e71e654b)](task.history.md) governed by `capsule-history.capsule` (5ec083a3).

---

*task capsule definition | LOCKED v4.1 | history at [task.history.md](task.history.md) | v4.1 body refactor 2026-05-11 by Argus A56 (v1.19.0 Stream C — 5-section pedagogy pattern; agent-read-not-human-read per Mike-A55). Prior v1.0–v4.0.1 locks preserved in history. UID `3289712a` preserved.*
*"Status is the work. Position is the run. Acceptors are the agreement. Processors are the drivers. Owner is accountable. Verifier checks the work. Approver signs off on the ship."*
