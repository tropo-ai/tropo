---
uid: b90c9495
name: "pipeline-run-history"
type: capsule-history
governs: 5a8f3b2c
governs_path: .tropo/capsules/pipeline-run.capsule.md
extracted_at: 2026-05-11
extracted_by: argus-a56
extracted_in_cycle: "v1.19.0 — Convergence Phase 1"
extracted_in_release: pending-v1.19.0
schema_version: 2
governed_by: 5ec083a3
extraction_scope: argo-private
member_of:
  - "8dd772a0"
tags: [capsule-history, extracted-from-pipeline-run-capsule, v1.19.0-stream-c]
---

# pipeline-run — Capsule History

*History extracted from pipeline-run.capsule v1.3 → v1.4 body refactor (v1.19.0 Stream C; 2026-05-11). Active capsule preserves: Required+Optional Frontmatter, Required Files (definition.md / context.md / thread.md / run.jsonl / run.state.json / artifacts/), run.jsonl Event Schema, State Machine (status: active/paused/complete/cancelled; state: active/archived), 7 Governance Rules, 12 Validation Checks, Member Processing protocol (5 steps), Composes-With. This file preserves: v1.0/v1.1/v1.2/v1.3 amendment-block prose, Archival Trigger procedure, Known Enforcement Gaps table, Execution Routing block, Run Folder Naming, Studio Shop Signage quick-ref, v1.2 sub-patterns, Migration Notes, full changelog.*

---

## Amendment Blocks (extracted)

### v2.0 (2026-05-20, Argus A76; ACTIVE — v1.46.0 Replacement-Body Spec; lock-break from v1.4)

v1.46.0 amendment per [Replacement-Body Specs (8e5b3c47)](../../vault/files/8e5b3c47.md) v0.5 LOCKED + [pipeline-runtime.py design-spec (2b809e0f)](../../vault/files/2b809e0f.md) v0.2 LOCKED. Substantial additive amendment introducing the runtime enforcement layer for pipeline.capsule v3.0's per-step rich schema. Lock-break: `status: locked → active` per Mike-A75 principal authorization 2026-05-20 verbatim *"I actually don't like the amendments inside the capsule. it bloats them... if none, just do it, if there is material downside then we will create a new capsule and superscede. I do not want history inside capsules. it is a waste."*

**Lock-break authorization context (captured per v1.46.0 cycle precedent):** pipeline-run.capsule was `status: locked` (locked by argus-a46 at 2026-05-05). No formal OS Invariant for capsule-lock-break exists in current substrate (capsule-definition meta-capsule at UID `222873b9` doesn't currently enumerate a capsule-lock-break rule). v1.46.0 establishes precedent via explicit Mike-A75 principal authorization captured here. A75 architect-lane confirmation that informed the authorization: no material downside to updating in place. Pipeline-runs pin `pipeline_version:` (the pipeline definition's version), not the capsule's version. v2.0 is additive (all v1.4 schema preserved). Validators read current capsule; vault entries cite by UID (`5a8f3b2c` preserved). Historical content extracts to this file per capsule-history.capsule pattern. **v1.47.0+ candidate:** formalize capsule-lock-break rule at the capsule-definition meta-capsule level (222873b9). When formalized, prior precedent cycles (including this v1.46.0 one) read clean against the formal rule.

**Authoring context:** v1.46.0 is the cycle Mike-A74 named as the structural fix for the cardboard-muffin pattern (7 cycles v1.39 → v1.45 shipping memory-resident discipline; v1.46.0 builds substrate-enforced state machine). pipeline.capsule v3.0 + pipeline-run.capsule v2.0 are the paired schema additions; companion pipeline-runtime.py engine is the canonical executor. Mike-A75 walked + locked the spec across 1M-token session 2026-05-20; A76 authored the canonical body 2026-05-20 against the locked spec.

**Twelve amendment areas:**

1. **Activation contract construction** — at run-start, pipeline-runtime.py writes `activation_contract_locked` event as first substantive event (after `run_created`) containing immutable contract (pipeline_uid + pipeline_version + cycle_context + steps_locked + skips_authorized_upfront + additional_steps_added + trust_overrides + human_instructions + supersession_reason + supersedes_activation). Then one `step_declared` event per step in `steps_locked:`. Pre-built events make the runtime knowable from JSONL alone — no need to query the pipeline definition at execution time.

2. **Structured `verification_receipt` enforcement** — same-as-executor default per Mike-A75 lock; verifier writes structured per-criterion checks (per_criterion array with criterion text + verdict + rationale + substrate_state_at_check + rubric_scores + overall_rationale). Truly-done state derived from event sequence (`step_completed` → `verification_receipt: verdict: pass`). Rule 7 preserved: event append, not frontmatter mutation.

3. **Trust gradient gates** — per pipeline.capsule v3.0's `trust_level:` field. Four levels: `approval-required` (pauses on step_started with reason `trust-gradient-gate`); `auto-with-verification` (no gate; structured receipt sufficient); `auto-after-track-record` (≥ 3 prior pass events PIPELINE-scoped + unchanged exit_criteria → auto; otherwise gates); `human-only` (requires `human_signoff` event).

4. **Exit_criteria resolution chain** — 4-step UID resolution at verification_receipt time: step's own context (artifact_link in step_completed) → pipeline-run's `members:` array → pipeline-run's `cycle_context` if it names UIDs → pipeline-run's `activation_contract_locked.cycle_root_uid` if declared. Resolution failure produces `verification_receipt.verdict: error`.

5. **OTel GenAI v1.37 attribute extension** — Argus A75 WebFetch-verified 2026-05-20 against opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/. Authoritative attribute requirement levels per span type (invoke_workflow / invoke_agent / create_agent / execute_tool). Notable: invoke_workflow has narrower core attribute set than invoke_agent (only operation.name + workflow.name as core); relevant for pipeline-runtime's outer activation span.

6. **SHIELDA-typed dispositions on step_failed** — verified at arXiv:2508.07935v1 2026-05-20. failure_phase (RP | E | RP/E; paper combines Reasoning + Planning into ONE phase RP); failure_class (12 paper-verbatim values: Goal | Context | Reasoning | Planning | Memory | Knowledge Base | Model | Tool | Interface | Task Flow | Other Agent | External System); disposition (Tropo-specific 5-value minimum-viable: retry | skip_with_authorization | complete_with_exception | compensate | abort; broader handler-pattern vocabulary deferred to v2.1+ if operational evidence justifies).

7. **`actor_label_resolved:` rendering hint on events** — alongside canonical `actor:` UID field. OPTIONAL; for human-readable display of the log. NOT canonical; aligns with OTel pattern (`gen_ai.agent.id` = UID + `gen_ai.agent.name` = readable). v1.4's `actor:` field continues to work; no rename.

8. **12 new event types** (preserves all v1.4 event types): activation_contract_locked; step_declared; anticipatory_reflection; skip_request; skip_authorization; verifier_findings; human_signoff; workflow_complete; create_agent (sub-agent dispatch for verifier-isolation override); tool_call (tool invocations within agent steps); activation_superseded (audit record on superseded prior activation); + structured `verification_receipt` extension. Schema_version bump 1 → 2 on event records.

9. **3 new optional frontmatter fields**: `depends_on_activation:` (cross-activation dependency edge); `supersedes_activation:` (dual-semantics field for self-bootstrap supersession + mid-flight contract-modification supersession); `concurrency_model:` (independent default / single-active-per-pipeline-lock).

10. **2 required frontmatter fields**: `run_folder:` ELEVATED from optional-with-default in v1.4 to REQUIRED at v2.0 (canonical path `argo-os/vault/pipeline-runs/<pipeline-name>-<activation-uid>-<date>/`); `substrate_authored_by:` NEW REQUIRED (links v2.0 pipeline-run entry to the v1.4-shape activation entry pipeline-activate.py wrote for substrate-authoring lineage; two-entry vault substrate model per design-spec 2b809e0f §2 + §16).

11. **Workflow visibility surface** — rendered file at `00-tropo-nav/pipelines/active-pipelines.md` auto-listing every `status: active` pipeline-run. DEFERRED to v1.47.0 (engine substrate ships at v1.46.0; render script lands when operational evidence justifies).

12. **Rule 7 clarification** — explicit statement that `verification_receipt` is append-only event in run.jsonl; truly-done state DERIVED from event sequence; no frontmatter mutation on pipeline-run entry via verification_receipt; readers compute step state by walking event log. Closes potential confusion that structured verification might imply frontmatter writes.

**Validation Checks count: 12 → 14** — two new MUST-SHIP ERROR-severity checks added:

- `check_pipeline_runtime_has_jsonl` — every `type: pipeline-run` entry (and v1.4-backward-compat `type: activation, activation_class: pipeline` entries) must have a corresponding `run.jsonl` file at its `run_folder:` path. `run_folder:` REQUIRED at v2.0 makes the check structurally enforceable.
- `check_step_completion_has_verification` — for every `step_completed` event followed by a dependent step's `step_started`, a `verification_receipt: verdict: pass` for the prior step must exist between them. Verification-class steps bypass per `verification_class: true` declaration.

**Deferred to v1.47.0+:** check_pipeline_runtime_terminal_state; check_skip_authorization_explicit; check_pipeline_runtime_age_bounded; check_verification_receipt_actor_class (verifier-isolation enforcement; defers per Mike-A75 same-as-executor lock); check_pipeline_run_substrate_authored_by_resolves.

**Opportunistic fixes in same body-replacement edit (per R2 P1.4 + P2.1 absorption at spec v0.3):**

- `governed_by:` field corrected `222813b9 → 222873b9` (broken ref in v1.4 frontmatter; UID `222813b9` doesn't resolve to any vault file; pre-existing broken reference inherited from v1.4 substrate; verified `222873b9` resolves to capsule-definition meta-capsule per pipeline.capsule + entity.capsule citations).
- `modeled_on:` comment updated `f2a8c3e1   # playbook-run.capsule v2.0` → `f2a8c3e1   # playbook-run.capsule v2.1` (verified on-disk version is v2.1).
- `pause_started.data.reason:` vocabulary extended with `"trust-gradient-gate"` (NEW v2.0; fires when step's `trust_level: approval-required` gates on step_started).
- `pause_resumed.data.confirmation_granted_by:` semantics extended to cover both v1.1 confirmation pauses and v2.0 trust-gradient gates.

**Composes-with additions:** [pipeline.capsule v3.0 (e4c8a6b2)](pipeline.capsule.md) cite version-bumped; [pipeline-runtime.py design-spec (2b809e0f)](../../vault/files/2b809e0f.md) added to aligned_with (companion executor design-spec). [activation.capsule (per registry)](activation.capsule.md) cite added with discriminator clarification for two-entry vault substrate model.

**Backward-compatibility:** all v1.4 schema preserved entirely; v1.4-shaped pipeline-runs remain valid against v2.0 schema; new optional fields default to v1.4-equivalent semantics; v1.4 events without OTel GenAI attributes continue to validate; runs activated against v2.6-shaped pipelines (no per-step rich schema) get auto-defaulted with explicit defaults captured in activation_contract_locked event for self-describing runtime; v1.4-shape activation entries (`type: activation, activation_class: pipeline`) continue to exist alongside new v2.0-shape `type: pipeline-run` entries.

### v1.4 (2026-05-11, Argus A56; ACTIVE — v1.19.0 Stream C body refactor)

v1.19.0 Stream C body refactor applying the 5-section pedagogy pattern (Intent / Schema / State Machine / Validation Rules / Composes-With + Member Processing protocol). Amendment-block prose for v1.0 → v1.3, Archival Trigger procedure, Known Enforcement Gaps table, Execution Routing block, Run Folder Naming convention, run.state.json schema example, v1.2 sub-patterns block, Studio Shop Signage authoring procedure, Migration Notes (v1.3 project-walker → v2 pipeline-run), Extension-from-core narrative, and full changelog all extracted from capsule body to this history file. Capsule body shrinks; pedagogy structure standardizes. UID `5a8f3b2c` preserved. `status: locked` preserved (locked at v1.0; never unlocked through v1.4 cycles — formally unlocked at v2.0 per Mike-A75 principal authorization). Sister refactor at pipeline.capsule v2.5 same cycle.

### v1.3 (2026-05-05, Argus A46; LOCKED — v1.8 Stream C pre-doc)

v1.8 Stream C pre-doc per [v1.8 brief fd2d9e77](../../vault/files/fd2d9e77.md). Additive non-breaking signage-only amendment, paired with [pipeline.capsule v2.3](pipeline.capsule.md). §Workshop signage gains pre-doc for v1.9's forthcoming dev-pipeline step-7 `update-subsystem-canonical-docs`: pipeline-runs whose pinned pipeline includes step-7 will, at B6 atomic-triangle commit, read the release entry's derived `subsystems_touched:` (computed via 1-hop `member_of:` traversal over `capabilities_touched:` per [release.capsule v3.4 Rule 12](release.capsule.md)) and write derived `release_history:` rows + `subsystem-registry.jsonl` rows + optionally invoke sa.hub-groomer for body updates. v1.8 cycle ships substrate; v1.9 cycle adds the executor step. Cross-cycle pre-doc ensures v1.9 step-7 author has consumption pattern pre-locked.

### v1.2 (2026-05-05, Argus A45; LOCKED — v1.7 Stream A3 sister-amendment)

Closing v1.6 sister-amendment debt paired with [pipeline.capsule v2.2](pipeline.capsule.md) (which introduced the activation-root-project pattern at step-0 of dev-pipeline). Additive, non-breaking. Acknowledges three new sub-patterns in §Workshop signage: (1) activation-root-project compliance — pipeline-runs invoked by dev-pipeline activations are `member_of: [<activation-root-project-uid>]` per the substrate invariant locked in v1.6; (2) sa.* dispatch sub-pattern via `dispatches` edge type; (3) subsystem-registry write at ship gate per [release.capsule v3.3](release.capsule.md) Rule 11.

### v1.1 (2026-05-03, Argus A43; LOCKED — v1.4.4 Stream B minimum amendment)

Paired with [pipeline.capsule v2.1](pipeline.capsule.md). Additive, non-breaking. Honors the new `requires_confirmation: boolean` field on leaf-step WorkflowNodes — step-ENTRY pause for human approval, distinct from `restart_strategy: manual` step-FAILURE pause. Adds executor protocol for `requires_confirmation: true`, log `pause_started` event with `data.reason: "human-confirmation-required"`, await explicit resume from owner/principal/authorized confirmer.

### v1.0 (2026-04-23, Argus A32)

Initial DRAFT. New capsule modeled on playbook-run.capsule v2.0. Per Tropo Work v2 Arch Spec §2.4 + §3.1. Pending three-instrument verification.

---

## Archival Trigger (extracted)

A stateless agent can determine archival eligibility without asking:

1. **Manual:** `owner` (invoking entity) OR `principal` may archive any `complete` or `cancelled` run at any time.
2. **Automatic:** vault-janitor archives runs in `complete` or `cancelled` state for 30+ days without activity.
3. **Immediate:** Any status → `archived` valid with `event: archived, reason: <string>` written to `run.jsonl` first.

Grace period defaults to 30 days from `status: complete`; configurable per-pipeline via the pipeline's capsule or per-run override.

---

## Known Enforcement Gaps (extracted)

| Gap | What closes it | Target release | Owner |
|---|---|---|---|
| Concurrency correctness (two runs advancing same member) is honor-system | Optimistic-concurrency check-and-set on member status transitions | v2.1 | argus |
| Activity log append-only discipline not mechanically enforced | File-hash check OR filesystem-level append-only enforcement | v2.1 | argus |
| Processor-filter recursion depth enforcement is honor-system | Validator with bounded-walk primitive | v2.1 | argus |
| Compensation/saga semantics for cancelled runs | Separate follow-on spec (v2.1+) | v2.1+ | argus |
| Back-pressure when one entity is flooded with `requested_of` | Rate-limiter primitive | v2.1+ | argus |
| Circuit-breakers for repeatedly-failing runs | Separate follow-on spec | v2.1+ | argus |

All gaps documented honestly per arch-spec.capsule Rule 8.

---

## Execution Routing (extracted)

Any agent that encounters a run in `active` or `paused` status is authorized and expected to dispatch the executor, following the same pattern as playbook-run:

```
Executor: agents/operations/pipeline-executor/activate.md (forthcoming v1.4)
Spawn with: "Run UID: <run_uid> | Vault root: <path>"
```

The executor reads `definition.md`, loads the pinned pipeline version, reconstructs state from `run.state.json` + `run.jsonl`, and continues execution. It does not need additional instruction.

A `paused` run that no agent resumes is a broken process. Per governance: Vela (or ship-lane owner) watches for stalled runs during ship-gate pre-flight.

---

## Run Folder Naming (extracted)

```
vault/pipeline-runs/<pipeline-slug>-<run-uid>-<YYYY-MM-DD>/
```

Example: `vault/pipeline-runs/release-pipeline-a3f2b1c4-2026-04-23/`

May alternatively live under a project-scoped folder if the run is `member_of:` a project; convention TBD during migration.

---

## run.state.json schema (illustrative, extracted)

Appended by executor at every stage boundary (not every step). Overwrite-at-boundary; previous boundary is not preserved (use `run.jsonl` for history).

```json
{
  "schema_version": 1,
  "pipeline_run_uid": "<run-uid>",
  "pipeline_version": "<semver-pinned>",
  "current_stage": "<stage-workflow-node-uid>",
  "current_step": "<step-workflow-node-uid>",
  "status": "active",
  "stage_entered_at": "2026-04-24T14:00:00Z",
  "active_members_by_processor": {
    "<entity-uid-1>": ["<member-uid-a>", "<member-uid-b>"],
    "<entity-uid-2>": ["<member-uid-c>"]
  },
  "members_in_terminal_state": ["<member-uid-d>"],
  "events_since_last_boundary": <int>
}
```

Minimal v1.0; v1.5+ may enrich (per-processor progress deltas, performance metadata).

---

## v1.2 Sub-patterns (extracted)

- **Activation-root-project sub-pattern.** Every dev-pipeline activation produces an activation root project at step-0 ([first instance: 3a9d6c5e v1.6](../../vault/files/3a9d6c5e.md); [second instance: 51ee36a6 v1.7](../../vault/files/51ee36a6.md)). All pipeline-run children of that activation belong to the root project's graph. The activation run itself is recorded in the run's `run.jsonl` event log; the activation root project is the *graph home* for outputs (briefs, release plans, sub-agent records, build entries, release entries, etc.).

- **sa.\* pipeline-step verifier sub-pattern (v1.7 instance; v1.10 generalization).** A pipeline step may dispatch a session-agent (sa.\*) for specialized verified work. The primary executor reaches step (n), spawns the sa.\* via `dispatch-sa-step.skill`, the sa.\* performs work + verification, returns verified output to the step's record, and the executor advances. v1.7 first instance: `sa.hub-groomer` (multi-agent swarm: 2 workers + 1 judge with convergence-by-disagreement) at dev-pipeline step "groom-subsystems." v1.10 Enforcement formalizes the generalized capsule.

- **Subsystem-registry write sub-pattern (v1.7 ship gate).** Release-pipeline-runs whose pinned pipeline includes a Ship Gate write rows to `subsystem-registry.jsonl` for each subsystem the release touched, per [release.capsule v3.3 Rule 11](release.capsule.md) (soft-gated v1.7-v1.9; hard-gated v1.10+). Ordering: hub-side `release_history:` row first (with placeholder `registry_uid: pending`), then registry row, then backfill `registry_uid:` on the hub-side row.

---

## Studio — Shop Signage (extracted)

*Preserved per Mike-A55 directive: capsules are agent-read, not human-read.*

### Tools available

- `run.jsonl` append-only log — append events per §run.jsonl Event Schema; never mutate priors
- `run.state.json` — stage-boundary anchor
- vault rebuild — validates pipeline-run frontmatter + references at every rebuild
- Executor dispatch pattern (per `playbook-run.capsule` precedent)

### Skills

- `invoke-pipeline.skill.md` *(forthcoming v1.5)* — starts a new pipeline-run on a bundle of members
- `advance-pipeline-run.skill.md` *(forthcoming v1.5)* — processor-agent's per-step execution protocol
- Migration script (Stream 1 D1.3) — backfills v1.3 project-walker data into companion pipeline-run entries

### Procedures

- Any playbook that dispatches a processor-agent against a pipeline-run (e.g., release-pipeline execution)
- `agent-activation.playbook.md` — agents may boot into a pipeline-run as their assigned context

### Pitfalls

- Editing `pipeline_version:` post-start → data-integrity break
- Mutating prior `run.jsonl` entries → breaks replay + audit
- Authoring `members: []` → nonsensical; no work for the run to coordinate
- Treating runs as pipelines (DAG/DAG-Run confusion — Airflow's classic UX trap) → runs are instances; pipelines are templates
- Assuming step failure auto-retries → default `restart_strategy: manual`; failures PAUSE
- Expecting the run to transition member status automatically → runs observe, processors mutate (via member's request-lifecycle)
- **(v1.1)** Confusing `requires_confirmation:` with `restart_strategy: manual` → former is step-ENTRY gate (pauses BEFORE work begins); latter is step-FAILURE gate (pauses AFTER work). Both can fire on same step.
- **(v1.1)** Resuming a confirmation-pause without recording `confirmation_granted_by:` → audit trail loses who authorized the resume
- **(v1.2)** dev-pipeline activation pipeline-runs without `member_of: [<activation-root-project-uid>]` → violates v1.6 substrate invariant
- **(v1.2)** Pipeline step dispatching sa.\* without declaring `relationships: [{kind: dispatches, to: <sa-uid>}]` → graph-index does not surface the dispatch edge
- **(v1.2)** Release-pipeline-run reaching ship gate without writing subsystem-registry rows → violates release.capsule v3.3 Rule 11

### Worked examples

- `pipeline-run-template.md` *(forthcoming v1.4 deliverable)* — canonical skeleton with event-log seed + required-files checklist
- `playbook-run` instances in `playbook-runs/` — structural precedent; pipeline-runs are near-1:1 forks

### Go next

- Need to execute steps? → processor-agents boot from `agent-activation.playbook.md`
- Need to define what the pipeline does? → [pipeline.capsule (e4c8a6b2)](pipeline.capsule.md)
- Members are tasks? → [task.capsule (3289712a)](task.capsule.md)
- Members are projects? → [project.capsule (34e4cb0b)](project.capsule.md)
- Need the entity model? → [entity.capsule (1e9c3f7a)](entity.capsule.md)

---

## Migration Notes (extracted)

v1.3 used project-walks-pipeline semantics (project.capsule v2.2's `active_pipeline:` + `position:`). v2 supersedes this: pipeline-walks are now pipeline-runs. Migration:

1. **Any v1.3 project with `active_pipeline:` set** — author a companion pipeline-run entry with `owner: <project-owner-entity>`, `pipeline: <active_pipeline>`, `members: [<project-uid>]`, `current_stage: <position>`. The pipeline-run becomes the flow; the project becomes organizational-only.
2. **Strip v2.2 pipeline-walk fields** from project frontmatter (per project.capsule v2.3 amendment).
3. **v1.4 ships the capsule + migration script + proof-on-high-traffic-projects.** v1.5 closes the long tail.

---

## Extension from core (extracted)

pipeline-run.capsule extends core: **uses `status:` for workflow-lifecycle** (active/paused/complete/cancelled per core's status-machine convention); **adds `state:` for visibility** (active/archived) separate from status — dual-field asymmetry intentional per Tropo Work v2 Arch Spec §3.1; **`name:` field** ≤120 chars specialized for run identification (core: `title:` ≤100); modeled structurally on [playbook-run.capsule v2.0 (f2a8c3e1)](playbook-run.capsule.md).

---

## Changelog (full lineage)

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-04-23 | Initial DRAFT. New capsule modeled on playbook-run.capsule v2.0. Per Tropo Work v2 Arch Spec §2.4 + §3.1. Pending three-instrument verification. | argus-a32 |
| 1.1 | 2026-05-03 | LOCKED — v1.4.4 Stream B minimum amendment paired with [pipeline.capsule v2.1]. Additive non-breaking. Adds executor protocol for `requires_confirmation: true` on leaf-step WorkflowNodes — pause on step ENTRY. Confirmation gate check before Step 1. New pause_started.data.reason vocab. Two new pitfalls. | argus-a43 |
| 1.2 | 2026-05-05 | LOCKED — v1.7 Stream A3 sister-amendment closing v1.6 sister-amendment debt paired with [pipeline.capsule v2.2]. Additive non-breaking. §Workshop signage: 2 new Rules-at-a-glance, 3 new sub-patterns, 3 new pitfalls. Forward-references release.capsule v3.3 Rule 11 + subsystem-hub.capsule v1.3 + dispatch-sa-step.skill + edge-types.definitions.jsonl `dispatches` row. Mechanical additive; no separate verification. | argus-a45 |
| 1.3 | 2026-05-05 | LOCKED — v1.8 Stream C pre-doc per [v1.8 brief fd2d9e77]. Additive non-breaking signage-only amendment, paired with [pipeline.capsule v2.3]. §Workshop signage gains pre-doc for v1.9's forthcoming dev-pipeline step-7 `update-subsystem-canonical-docs`. Pipeline-runs whose pinned pipeline includes step-7 will, at B6 atomic-triangle commit, read the release entry's derived `subsystems_touched:` and write derived `release_history:` rows + `subsystem-registry.jsonl` rows. v1.8 ships substrate; v1.9 adds executor step. | argus-a46 |
| 1.4 | 2026-05-11 | **v1.19.0 Stream C — Capsule Pedagogy Completion.** Body refactor to 5-section pedagogy pattern per Mike-A55 *"capsules are agent-read, not human-read"* directive. Active body reduced from 472 → ~290 lines (~39% reduction; lower than average because pipeline-run carries substantial Required Files spec + run.jsonl Event Schema + Member Processing protocol that must remain in active body for executor reference). Extracted to history: v1.0-v1.3 amendment-block prose, Archival Trigger, Known Enforcement Gaps, Execution Routing, Run Folder Naming, run.state.json schema, v1.2 sub-patterns, §Studio quick-ref, Migration Notes, Extension from core, full changelog. **No schema changes.** UID `5a8f3b2c` preserved. | argus-a56 |

---

## Provenance

- **Extracted at:** 2026-05-11
- **Extracted by:** argus-a56
- **Active capsule version at extraction:** v1.3 (472 lines)
- **Active capsule version after extraction:** v1.4 (~290 lines; ~39% reduction)

---

*pipeline-run capsule history | UID b90c9495 | v1.19.0 Stream C extraction 2026-05-11 by Argus A56 | Bidirectional pair: governs 5a8f3b2c*
