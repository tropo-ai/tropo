---
subsystem_hub:
  - "2d083137"
uid: 5a8f3b2c
name: "pipeline-run"
type: capsule-definition
extends: core
version: "2.1"
supersedes_version: "2.0"
tier: vault
author: argus
created: 2026-04-23
modified: 2026-06-09
modified_by: argus-a105
status: active
last_locked_at: 2026-05-05
last_locked_by: argus-a46
last_body_refactor: 2026-05-20
v2_1_amendment_note: "v2.0 -> v2.1 amendment 2026-05-31 by Argus A89 (v1.62 Substrate-Enforces-Discipline; dev-spec c1a62d3f; spine cdc1615e; Mike-A89 con). Adds Governance Rule 8 (workflow_complete requires all-steps-verified) + promotes/strengthens the deferred check_pipeline_runtime_terminal_state into active Validation Check 15 (check_workflow_complete_all_steps_verified) + state-machine active->complete condition. Runtime half of pipeline.capsule v3.1 Rule 11; codifies pipeline-runtime.py B3 (assert_all_steps_verified before workflow_complete, Talos Lane B). Makes a hollow cascade un-closable: v1.60/v1.61 runs sat active because cascade steps never verified — under Rule 8 workflow_complete refuses to fire + the completion report (completion-report.capsule) renders BLOCKED. Body current-tense per Mike-A75 no-history lock."
v2_0_anchor: "Argus A76 amendment per v1.46.0 Replacement-Body Specs (8e5b3c47 v0.5 LOCKED). Lock-break authorized by Mike-A75 2026-05-20 verbatim 'I actually don't like the amendments inside the capsule. it bloats them... if none, just do it.' Body replacement in place with status: locked → active flip; UID 5a8f3b2c preserved; v1.4 body content + amendment narratives extract to pipeline-run.history.md. Substantial additive amendment — adds runtime enforcement layer for pipeline.capsule v3.0 per-step rich schema. v2.0 adds: activation contract event-prebuild at run-start; structured verification_receipt format (per-criterion machine-checkable assertions; default same-as-executor verifier per Mike-A75 lock); 12 new event types (activation_contract_locked / step_declared / anticipatory_reflection / skip_request / skip_authorization / verifier_findings / human_signoff / workflow_complete / create_agent / tool_call / activation_superseded + extended verification_receipt structure); OTel GenAI v1.37 attribute extension (Argus A75 WebFetch-verified 2026-05-20); SHIELDA-typed dispositions on step_failed (arXiv:2508.07935v1 verified); trust gradient gates (4 levels: approval-required / auto-with-verification / auto-after-track-record / human-only); exit_criteria resolution chain (4-step UID resolution); new frontmatter (depends_on_activation OPTIONAL / supersedes_activation OPTIONAL dual-semantics / concurrency_model OPTIONAL / run_folder REQUIRED elevated from v1.4 optional / substrate_authored_by REQUIRED NEW); actor_label_resolved rendering hint on events (no rename of v1.4 actor: UID); Rule 7 clarification (verification_receipt is event append; truly-done state derived from event sequence; no frontmatter mutation); 2 new MUST-SHIP validator checks + 4 DEFERRED to v1.47.0+. Opportunistic fixes (R2 P1.4 + P2.1 absorption): governed_by corrected 222813b9 → 222873b9 (broken ref in v1.4 frontmatter); modeled_on updated f2a8c3e1 v2.0 → v2.1 comment. Companion pipeline.capsule v3.0 ships in same cycle. Companion design-spec pipeline-runtime.py at vault/files/2b809e0f.md v0.2 LOCKED."
history_file: b90c9495
enforced_enums:
  status: [active, paused, complete, cancelled]
meta_status_rollup:
  in-progress: [active, paused]
  done: [complete, cancelled]
schema_version: 2
governed_by: 222873b9
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — 5-section pedagogy
aligned_with:
  - f2e8a7b1   # Tropo Work v2 Architecture Specification
  - e1c47a9f   # dev-pipeline + vault inbox primitive
  - 2b809e0f   # v1.46.0 pipeline-runtime.py design-spec
modeled_on: f2a8c3e1   # playbook-run.capsule v2.1 — structural template
tags: [capsule-definition, pipeline-run, instance-tracking, activation-contract, structured-verification-receipt, otel-genai, shielda-dispositions, trust-gradient]
---

# pipeline-run — Capsule Definition v2.0

## 1. Intent

A pipeline-run is a single execution instance of a pipeline on a bundle of members. Ephemeral. Pins pipeline version at run-start. Records activity-log. Archives on completion.

A pipeline-run is NOT the pipeline itself (that lives in `vault/files/<pipeline-uid>.md` or as a `pipeline` subsystem file) — it is the instance. Each run has its own identity, its own pinned pipeline version, its own context, its own event log, and its own working memory. This is the Airflow DAG/DAG-Run separation rendered in markdown.

**Use a pipeline-run when:**
- An entity invokes a pipeline on a bundle of work-items and/or projects
- Work spanning multiple sessions needs state persistence + audit trail
- Operational intelligence about the process itself is wanted (how long did v1.4 spend in Build vs. Verify?)

**Ask:** *"Which entity invoked this run? Which pipeline does it execute? What members does it process?"* Every run has these three non-null.

**v2.0 adds the runtime enforcement layer** for pipeline.capsule v3.0's per-step rich schema. At run-start, the pipeline-run executor ([`.tropo/scripts/pipeline-runtime.py`](../scripts/pipeline-runtime.py)) writes an immutable activation contract (one `activation_contract_locked` event + one `step_declared` event per locked step). At each step boundary, the executor (or override verifier) writes a structured `verification_receipt` event with per-criterion machine-checkable assertions. Truly-done state is derived from the event log — no frontmatter mutation (Rule 7 preserved). The structured receipt format is the forcing function against memory-resident step discipline.

Failure mode prevented: pipeline definitions and pipeline executions conflated in one entity (Airflow's classic UX trap); pipeline edits during a long-running execution mutating the executing instance's behavior mid-flight; member status transitions performed by the run directly (instead of by processor-agents acting through the member's own request-lifecycle) producing graphs that don't replay correctly. **New at v2.0:** memory-resident step discipline (an agent reading a step's prose and self-asserting completion without machine-checkable evidence) — closed by structured verification_receipt + exit_criteria DSL.

---

## 2. Schema

### Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `uid` | 8-hex | Per core |
| `type` | literal | `pipeline-run` |
| `name` | string | ≤120 chars; human-readable (e.g., "Release v1.4") |
| `pipeline` | UID | Pipeline definition this run executes. Must resolve to `type: pipeline` entry. |
| `pipeline_version` | string | Semver, **pinned at run-start**. Executor MUST use this version — not the current pipeline version. Editing the pipeline after run-start does NOT affect this run. |
| `status` | enum | `active` / `paused` / `complete` / `cancelled`. Workflow lifecycle. |
| `state` | enum | `active` / `archived`. Lifecycle-visibility flag. Independent of `status`. |
| `current_stage` | UID | Current stage WorkflowNode. Resolves to node in pinned pipeline version. |
| `current_step` | UID | Current step WorkflowNode. For simple pipelines where stage IS leaf step, `current_step` = `current_stage`. |
| `members` | UID array | Polymorphic — each UID resolves to either a work-item (task/design-brief/arch-spec/build/release/note/etc.) OR a project. Cannot be empty. |
| `owner` | UID | The entity that invoked the run. Resolves to entity. |
| `principal` | UID | The entity signing (usually same as `owner`; may differ when an agent invokes on behalf of a human). |
| `authorized_by` | string or UID | Legacy field inherited from playbook-run; for v2 compliance prefer `owner:` + `principal:` UIDs. |
| `started_at` | ISO date | When the run began |
| `current_step_entered_at` | ISO date | Updated on each step transition |
| `binding` | path | Optional path to vault binding file (inherited from playbook-run; may be unused for pure pipeline-runs) |
| **`run_folder`** | path | **(REQUIRED at v2.0)** Canonical path `argo-os/vault/pipeline-runs/<pipeline-name>-<activation-uid>-<date>/`. v1.4-shape entries continue to validate against v1.4 default; v2.0-shape entries (those with any v2.0 field) MUST declare `run_folder:` explicitly. Pipeline-runtime.py writes the field at activation_contract_locked time; the value is part of the immutable activation contract. |
| **`substrate_authored_by`** | UID | **(REQUIRED NEW at v2.0)** 8-hex UID of the v1.4-shape activation entry (type:activation, activation_class:pipeline) that pipeline-activate.py wrote for the substrate-authoring lineage of this pipeline-run. Two-entry vault substrate model: pipeline-activate.py preserves v1.4-shape behavior (writes type:activation entries for substrate-authoring); pipeline-runtime.py writes type:pipeline-run entries (v2.0-shape; this field links back to the substrate-authoring entry). v1.4-shape entries don't carry this field. |

### Optional Frontmatter (preserved from v1.4 unless noted)

| Field | Type | Purpose |
|---|---|---|
| `member_snapshot_mode` | enum | `live` (default; effective membership evolves with vault graph) / `snapshot-at-start` (frozen at run-start) |
| `completed_at` | ISO date | Set when `status: complete` |
| `target_date` | ISO date | Optional ship-target |
| `restart_strategy` | enum | `manual` (default; transitions to `paused` on step failure) / `retry-current-step` (retries up to 3 times) / `retry-from-last-checkpoint`. Governs WITHIN-RUN failure recovery; compose with `supersedes_activation:` for ACROSS-RUN supersession at different scale. |
| `member_of` | UID array | Parent project(s). For v2, a pipeline-run may optionally belong to a project. REQUIRED `member_of: [<activation-root-project-uid>]` for dev-pipeline activation pipeline-runs per v1.6 substrate invariant. |
| **`depends_on_activation`** | UID OR array | **(NEW v2.0)** Pipeline-run-uid(s) of activation(s) this run depends on. Cross-activation dependency edge — this run's terminal verification gates on the depended-on activation(s) reaching terminal. Composes with cascade composition: cascade-spawned workstreams produce independent activations with `depends_on_activation:` edges back to the spawning activation. |
| **`supersedes_activation`** | UID | **(NEW v2.0)** Pipeline-run-uid of a prior activation this one replaces. **Dual semantics — same field used for two operational cases, both producing a supersession chain in the pipeline-run graph:** (1) **Self-bootstrap supersession** (engine change mid-cycle): the current activation is running under an older engine; mid-cycle a new engine prototype becomes usable; the older activation closes cleanly with `closure_reason: self-validating-bootstrap-supersession`; a new activation spawns under the new engine with `supersedes_activation:` pointing at the prior — preserves cycle continuity across an engine transition. (2) **Mid-flight contract-modification supersession**: the activation contract was locked at activation-time and is immutable; if steps need to be added mid-flight, the current activation closes and a new activation spawns with an amended contract + `supersedes_activation:` pointing at the prior — preserves the contract's authority while allowing legitimate amendment. **Disambiguation:** rationale for any given supersession lives in the new activation's `activation_contract_locked` event's `supersession_reason:` data field (one-of: `self-bootstrap` / `contract-modification` / `restart-from-scratch` / `other`). Compose with `restart_strategy:` enum: `restart_strategy:` governs WITHIN-RUN failure recovery; `supersedes_activation:` governs ACROSS-RUN supersession when continuation-within-current-run isn't appropriate. Different scales. |
| **`concurrency_model`** | enum | **(NEW v2.0)** `independent` (default) / `single-active-per-pipeline-lock`. Default `independent` — multiple pipeline-runs against the same pipeline definition may coexist. `single-active-per-pipeline-lock` reserves the pipeline for one active run at a time (subsequent runs queue or fail). |

### Required Files

Every run folder MUST contain these files. Before writing to the folder, read the governing AGENTS.md if one exists at the pipeline-runs parent folder.

| File | Purpose |
|---|---|
| `definition.md` | Run identity. The capsule entry. Required frontmatter per above. |
| `context.md` | Free-form markdown. Instance specifics — who/what this run is for. Written by invoking entity at run-start. |
| `thread.md` | LLM working memory across sessions. Append-only by convention. |
| `run.jsonl` | Append-only structured event log. See §run.jsonl Event Schema. Seed with `run_created` event at creation; **(NEW v2.0)** immediately followed by `activation_contract_locked` event + one `step_declared` event per locked step. |
| `run.state.json` | Typed resumption anchor. Written at every stage boundary. NEVER groomed. Gives executor current state without replaying full event log. |
| `artifacts/` | Directory for files produced by this run. Create empty at run start. |

### run.jsonl Event Schema

Every event is one JSON object per line. Append-only; events are never mutated or deleted.

```json
{
  "event": "<type>",
  "ts": "YYYY-MM-DDTHH:MM:SSZ",
  "actor": "<entity-uid>",
  "actor_label_resolved": "<readable>",
  "step": "<workflow-node-uid or null>",
  "stage": "<workflow-node-uid or null>",
  "data": {...event-specific payload...},
  "schema_version": 2
}
```

**`actor_label_resolved:` rendering hint (NEW v2.0; OPTIONAL):** alongside the canonical `actor:` UID field, v2.0 events MAY carry an `actor_label_resolved:` field for human-readable display of the log (e.g., "Argus A75", "Mike Maziarz"). NOT canonical; just for rendering. Aligns with OTel GenAI pattern where `gen_ai.agent.id` = UID + `gen_ai.agent.name` = readable. v1.4's `actor:` field continues to work as canonical UID; no rename.

**Standard event types (v1.4 preserved):** `run_created`, `step_started` / `step_completed` / `step_failed` / `step_skipped`, `stage_entered` / `stage_exited`, `status_changed`, `member_added` / `member_removed` (relevant for `member_snapshot_mode: live`), `rejection_recorded`, `restart_triggered`, `verification_receipt`, `milestone_fired`, `pause_started` / `pause_resumed`, `completed`, `archived`.

**New event types (NEW v2.0):**

| Event type | Purpose | Required data fields |
|---|---|---|
| `activation_contract_locked` | Immutable contract written at activation | pipeline_uid, pipeline_version, cycle_context, steps_locked, skips_authorized_upfront, additional_steps_added, trust_overrides, human_instructions, supersession_reason (if applicable), supersedes_activation (if applicable) |
| `step_declared` | One per locked step; pre-built at activation | step_id, step_owner_role, step_verifier_role, depends_on_steps, exit_criteria, trust_level, instructions_ref |
| `anticipatory_reflection` | Pre-step "what could go wrong" | step_id, reflection (text) |
| `skip_request` | Agent requests mid-flow skip | step_id, requested_by (UID), reason |
| `skip_authorization` | Human authorizes a skip_request | step_id, authorized_by (must resolve to type:principal or future type:human), conditions |
| `verifier_findings` | Terminal-state verifier's gap report (written by sa.pipeline-verify) | verdict (complete \| incomplete_with_authorized_skips \| incomplete_gaps), gaps (array), rubric_scores |
| `human_signoff` | Final human attestation | signed_by (UID), verdict (accepted \| accepted_with_exceptions \| rejected), notes |
| `workflow_complete` | Pipeline-run closure | terminal_state (complete \| cancelled), final_verifier_findings_ref |
| `create_agent` | Emitted when a separate-context sub-agent is dispatched for verifier-isolation override; composes with OTel `create_agent` span | agent_class (sub-agent's class), agent_id, dispatch_context_uids (UIDs of substrate sub-agent received: activation_contract_locked + step_declared + step_completed.artifact_links only — no executor reasoning chain), gen_ai.agent.name + gen_ai.agent.id + gen_ai.agent.version |
| `tool_call` | Emitted within agent step execution when a tool is invoked; composes with OTel `execute_tool` span | tool_name, tool_args, tool_response_summary (optional), gen_ai.operation.name (`execute_tool`), tool-specific OTel attributes per v1.37 spec |
| `activation_superseded` | Emitted on the PRIOR activation entry when a close-and-respawn supersession happens; creates an audit record on the superseded activation pointing forward at the superseding activation | superseded_by (new activation UID), supersession_reason (self-bootstrap / contract-modification / restart-from-scratch / other), prior_status_at_supersession |

### Structured verification_receipt event (NEW v2.0; extends v1.4's existing type)

v1.4 has `verification_receipt` in the standard event vocabulary. v2.0 specifies the structured format:

```json
{
  "event": "verification_receipt",
  "ts": "<ISO-8601>",
  "actor": "<executor-uid-or-verifier-uid>",
  "actor_label_resolved": "<readable>",
  "step": "<step-uid>",
  "data": {
    "verifier_role_resolved": "same-as-executor | <agent-class>",
    "verdict": "pass | fail | error",
    "per_criterion": [
      {"criterion": "<exit_criteria-entry-text>", "verdict": "pass | fail | error", "rationale": "<text>", "substrate_state_at_check": "<optional-detail>"}
    ],
    "rubric_scores": {"completeness": 0.0-1.0, "substrate_fidelity": 0.0-1.0, "exit_criteria_coverage": 0.0-1.0, "...": "step-specific dimensions"},
    "overall_rationale": "<text>"
  },
  "schema_version": 2
}
```

The structured `per_criterion` array is the cardboard-muffin defense at step-scale. Agent enumerates each `exit_criteria:` entry from the step's pipeline definition + asserts verdict against substrate that's mechanically checkable.

### Activation Contract — Required at run-start (NEW v2.0)

At pipeline-run creation, `pipeline-runtime.py` writes an `activation_contract_locked` event to run.jsonl as the FIRST substantive event (after `run_created`). The activation contract contains:

```json
{
  "event": "activation_contract_locked",
  "ts": "<ISO-8601>",
  "actor": "<human-or-agent-uid>",
  "actor_label_resolved": "<readable>",
  "data": {
    "pipeline_uid": "<pipeline-uid>",
    "pipeline_version": "<semver>",
    "cycle_context": "<free-text>",
    "steps_locked": [<array of step-spec objects from pipeline definition>],
    "skips_authorized_upfront": [{"step_id": "<id>", "authorized_by": "<human-uid>", "reason": "<text>"}],
    "additional_steps_added": [<array of step-spec objects added beyond definition>],
    "trust_overrides": [{"step_id": "<id>", "override_to": "<trust-level>"}],
    "human_instructions": "<free-text>",
    "supersession_reason": "<self-bootstrap | contract-modification | restart-from-scratch | other | null>",
    "supersedes_activation": "<prior-run-uid | null>"
  },
  "schema_version": 2
}
```

**`supersession_reason:` + `supersedes_activation:` data fields** are present in this event whenever the activation supersedes a prior run (per the dual-semantics use cases documented in `supersedes_activation:` frontmatter field above — self-bootstrap supersession or mid-flight contract-modification supersession). `null` (or field absent) when this is a fresh activation not superseding anything. Frontmatter `supersedes_activation:` field on the pipeline-run entry mirrors the event-payload field; both must agree.

After the `activation_contract_locked` event, one `step_declared` event is appended per step in `steps_locked:` array. These pre-built events make the runtime knowable from JSONL alone — no need to query the pipeline definition at execution time.

`additional_steps_added:` is captured at activation-contract-lock time and is part of the immutable contract; mid-flight additions require activation supersession via `supersedes_activation:`.

### OTel GenAI attribute extension (NEW v2.0; verified against v1.37 spec 2026-05-20)

Events MAY carry OpenTelemetry GenAI attributes per [the v1.37 spec agent-spans page](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/). Authoritative attribute requirement levels per span type:

**Span types relevant to pipeline-runtime:**

- **`invoke_workflow`** — emitted once per pipeline-run activation (outer span); span name `invoke_workflow {gen_ai.workflow.name}`. Required: `gen_ai.operation.name`. Conditionally Required: `gen_ai.workflow.name`, `error.type` (when error condition).
- **`invoke_agent`** (INTERNAL by default for in-process agents; CLIENT for remote agent invocations) — per-step agent invocation spans; span name `invoke_agent {gen_ai.agent.name}` or `invoke_agent`. Required: `gen_ai.operation.name`, `gen_ai.provider.name`. Conditionally Required: `error.type`, `gen_ai.agent.description`, `gen_ai.agent.id`, `gen_ai.agent.name`, `gen_ai.agent.version`, `gen_ai.conversation.id`, `gen_ai.data_source.id`, `gen_ai.output.type`, `gen_ai.request.model`, `server.port` (CLIENT only). Recommended: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`, `server.address` (CLIENT only).
- **`create_agent`** — sub-agent creation events (e.g., separate-context verifier dispatch when `step_verifier_role:` overrides to a different class); span name `create_agent {gen_ai.agent.name}`. Required: `gen_ai.operation.name`, `gen_ai.provider.name`. Conditionally Required: `error.type`, `gen_ai.agent.description`, `gen_ai.agent.id`, `gen_ai.agent.name`, `gen_ai.agent.version`, `gen_ai.request.model`, `server.port`.
- **`execute_tool`** — tool calls within an agent invocation (per OTel tool-call conventions).

**Notable:** `invoke_workflow` has a significantly narrower core attribute set than `invoke_agent` — only operation + workflow name. This is the relevant span type for pipeline-runtime's outer activation span; per-step agent spans use `invoke_agent` with the broader set.

Plus span identifiers used by Tropo (not OTel-spec but standard distributed-tracing): `trace_id` (one trace per pipeline-run = activation_uid), `span_id` (per-event unique id), `parent_span_id` (parent event's span_id; span-tree reconstruction).

Free interop with OpenTelemetry exporters when/if Tropo Studio ever ships observability tooling.

### SHIELDA-typed dispositions on step_failed (NEW v2.0; verified against arXiv:2508.07935v1 2026-05-20)

v1.4's `step_failed` events get extended with three optional data fields. Verified terminology per the SHIELDA paper:

```json
{
  "event": "step_failed",
  "ts": "<ISO>",
  "actor": "<agent-uid>",
  "actor_label_resolved": "<readable>",
  "step": "<step-uid>",
  "data": {
    "failure_phase": "RP | E | RP/E",
    "failure_class": "Goal | Context | Reasoning | Planning | Memory | Knowledge Base | Model | Tool | Interface | Task Flow | Other Agent | External System",
    "disposition": "retry | skip_with_authorization | complete_with_exception | compensate | abort",
    "retry_count": <int>,
    "error_detail": "<text>"
  },
  "schema_version": 2
}
```

**`failure_phase` values** (paper-verbatim):

- `RP` (Reasoning/Planning) — stage where the agent analyzes input, formulates goals, interprets context, generates a task plan. Paper combines Reasoning + Planning into ONE phase.
- `E` (Execution) — stage where the agent operationalizes its plan via tool invocations, API calls, output generation, UI interaction.
- `RP/E` — many exceptions span both phases per the paper's Table 1; use this value when the exception originated in reasoning/planning AND surfaced in execution.

**`failure_class` 12 values** (paper-verbatim verified spellings): Goal | Context | Reasoning | Planning | Memory | Knowledge Base (two words) | Model | Tool | Interface | Task Flow (two words) | Other Agent (not "MultiAgent") | External System (not "Environmental"). The paper enumerates 36 specific exception types distributed across these 12 artifacts + 48 reusable handler patterns.

**`disposition` Tropo-specific 5-value set** (deliberate simplification of SHIELDA's broader handler-pattern enumeration for v1.46.0 minimum-viable): retry / skip_with_authorization / complete_with_exception / compensate / abort. The paper's full disposition vocabulary includes additional values (Retry with Backoff, Escalate to Human, Escalate to Peer Agent, No-op, rollback) that Tropo may adopt in v2.1+ if operational evidence justifies.

`disposition: skip_with_authorization` REQUIRES a corresponding `skip_authorization` event later in the log referencing this step_failed's step. Validator check `check_skip_authorization_explicit` enforces this discipline — DEFERRED to v1.47.0+.

### pause_started.data.reason vocabulary (preserved from v1.1)

| Reason | Trigger | Resume requirement |
|---|---|---|
| `"step-failure"` | Default for `restart_strategy: manual` failure path | Operator intervention; resumed via fix + explicit `pause_resumed` |
| `"human-confirmation-required"` | `requires_confirmation: true` step-ENTRY gate | Authorized confirmer appends `pause_resumed` with `data.confirmation_granted_by:` |
| `"explicit-pause"` | Operator-initiated pause | Operator-initiated `pause_resumed` |
| `"trust-gradient-gate"` | **(NEW v2.0)** Step's `trust_level: approval-required` fires on step_started | Authorized confirmer appends `pause_resumed` with `confirmation_granted_by:` |

**`pause_resumed.data.confirmation_granted_by:`** — entity-UID that authorized the resume when prior pause reason was `"human-confirmation-required"` or `"trust-gradient-gate"`. Required for confirmation-pause cycles. `actor:` (event author) and `confirmation_granted_by:` (the entity authorizing) may differ legitimately.

**Seed events at creation (NEW v2.0 — three events):**

```json
{"event": "run_created", "ts": "<ISO>", "actor": "<owner-uid>", "data": {...}, "schema_version": 2}
{"event": "activation_contract_locked", "ts": "<ISO>", "actor": "<owner-uid>", "data": {<full contract>}, "schema_version": 2}
{"event": "step_declared", "ts": "<ISO>", "actor": "<owner-uid>", "data": {<step-spec>}, "schema_version": 2}
```

(One `step_declared` event per step in `steps_locked:`.)

### Size Limit + Rollover

- **Soft limit:** 10,240 events per `run.jsonl`
- **Beyond limit:** rollover to `run-002.jsonl`, `run-003.jsonl`, etc. with index file `run-index.json` listing segments
- **Replay:** full replay requires reading index + segments in order

---

## 3. State Machine

```
active ⇌ paused → complete → (grace period) → archived
      ↘ cancelled (terminal)
```

| Status | Meaning |
|---|---|
| `active` | Run executing. Executor can advance steps. |
| `paused` | Human intervention point. Executor cannot advance until explicit resume. Triggered by `restart_strategy: manual` on step failure, by explicit pause, by `requires_confirmation: true` step-entry gate, or **(NEW v2.0)** by `trust_level: approval-required` step gate. |
| `complete` | Terminal step reached + any required Gate signals received. Run archives after grace period. |
| `cancelled` | Operator-cancelled mid-flight. Terminal. Side-effect compensation out-of-v2.0-scope. |

**Valid transitions:**

- `active → paused` (step failure with `restart_strategy: manual`; explicit pause; step entry where `requires_confirmation: true`; **(NEW v2.0)** step entry where `trust_level: approval-required`)
- `paused → active` (explicit resume after intervention or confirmation)
- `active → complete` (terminal step reached + **(v2.1/v1.62) ALL declared steps verified per Rule 8 / assert_all_steps_verified** + workflow_complete event written)
- `active → cancelled` (operator cancels)
- `paused → cancelled` (operator cancels while paused)
- `complete → archived` (grace period elapses; state-level transition)
- `cancelled → archived` (grace period elapses)
- `any → archived` (explicit with `event: archived, reason: <string>` logged to run.jsonl first)

**No `failed` state.** Unlike playbook-run.capsule v2.1, pipeline-runs route failure through `paused` with restart-strategy. Matches Airflow's "retry-or-fail-for-manual-intervention" default.

**Archival eligibility:** Manual (owner/principal at any time post-complete-or-cancelled); Automatic (vault-janitor archives runs in `complete` or `cancelled` state for 30+ days without activity); Immediate (any status → `archived` with `event: archived, reason: <string>` logged first). Grace period defaults to 30 days from `status: complete`; configurable per-pipeline.

---

## 4. Validation Rules

### Governance Rules (8, in addition to core)

1. **Pipeline-version pin is immutable.** `pipeline_version:` is set at run-start and does NOT change. Editing the pipeline after run-start does NOT affect this run.
2. **Members list is authoritative at run-start.** `members:` at run-start defines the bundle. Per `member_snapshot_mode:`, the effective set may evolve (`live`) or freeze (`snapshot-at-start`), but declared `members:` is source of truth for what the run was invoked on.
3. **`run.jsonl`, `thread.md`, `run.state.json` are append-only or overwrite-at-boundary.** Do not edit prior run.jsonl entries. thread.md is conventionally append-only. run.state.json overwrites at each stage boundary (coarser than step boundary).
4. **Only the current executor OR owner OR principal may transition status.** Status transitions are logged to run.jsonl with `event: status_changed`.
5. **Archived runs are read-only.** Post-archival, all files in the run folder are immutable.
6. **Multiple concurrent pipeline-runs on same members are permitted.** Each run holds its own current_stage/current_step; members' intrinsic status is shared state. **(NEW v2.0)** `concurrency_model: single-active-per-pipeline-lock` overrides this default at the pipeline level.
7. **Pipeline-runs do NOT force member status transitions.** Member status transitions happen via the member's own request-lifecycle. Processor-agents operating within a pipeline-run may trigger a member's status transition AS PART OF executing their step — the transition runs through the member's request-lifecycle machinery, not via a mutation the run itself performs. When multiple concurrent runs have shared members, the first processor-agent to complete a status-transitioning action wins; subsequent processors observe the transition. **The run is a coordination + audit-trail container; it observes, it doesn't mutate.**

   **(NEW v2.0 — Rule 7 clarification.)** The new `verification_receipt` event mechanism (and all other new v2.0 event types) preserves Rule 7. **`verification_receipt` is an append-only event in run.jsonl; truly-done state is DERIVED from the event sequence** (a step is truly-done when the pattern `step_completed` → `verification_receipt: verdict: pass` exists in the log for that step_uid). **No frontmatter mutation on the pipeline-run entry happens via verification_receipt.** Readers compute step state by walking the event log. Rule 7 holds: the run observes (records the verdict in the log); it doesn't mutate.
8. **(NEW v2.1 / v1.62) `workflow_complete` requires all-steps-verified — the close gate.** The `workflow_complete` event MUST NOT be written until `assert_all_steps_verified` holds: every declared step (per the `step_declared` events at run-start) has, in `run.jsonl`, either a `verification_receipt: verdict: pass` OR — for `verification_class: true` steps — a natural-output pass verdict in its `step_completed` event. A run cannot reach `status: complete` with any step unverified. This is the runtime half of pipeline.capsule v3.1 Rule 11 (the engine gate); enforced by pipeline-runtime.py `action_complete_workflow` (v1.62 Lane B3). It is what makes a hollow cascade un-closable: v1.60/v1.61's runs sat `active` because their cascade steps never verified — under this rule `workflow_complete` refuses to fire and the completion report ([completion-report.capsule](completion-report.capsule.md)) renders the BLOCKED verdict instead of a silent green board.

### Validation Checks (15, ERROR-severity at check-in)

1. `type: pipeline-run`
2. `status:` ∈ {active, paused, complete, cancelled}
3. `state` ∈ {active, archived}
4. `pipeline:` resolves to a `type: pipeline` entry
5. `pipeline_version:` is valid semver
6. `members:` non-empty; each UID resolves to a work-item or project
7. `owner:` and `principal:` resolve to entities
8. `current_stage:` and `current_step:` resolve to WorkflowNodes in the pinned pipeline version
9. `started_at` is valid ISO 8601; `completed_at` valid or null
10. If `status: complete`, `completed_at` is set
11. *(honor-system)* `run.jsonl` exists in run folder; append-only discipline
12. *(honor-system)* `run.state.json` matches latest stage-boundary events in `run.jsonl`
13. **(NEW v2.0) `check_pipeline_runtime_has_jsonl`** — every `type: pipeline-run` entry (and `type: activation, activation_class: pipeline` v1.4-backward-compat entries) must have a corresponding `run.jsonl` file at its `run_folder:` path. ERROR. (`run_folder:` field is REQUIRED for v2.0-shape entries so the check is structurally enforceable.)
14. **(NEW v2.0) `check_step_completion_has_verification`** — for every `step_completed` event followed by a dependent step's `step_started`, a `verification_receipt: verdict: pass` for the prior step must exist between them. ERROR. (Verification-class steps bypass per `verification_class: true` declaration on the step's pipeline definition.)
15. **(NEW v2.1 / v1.62) `check_workflow_complete_all_steps_verified`** — promoted from DEFERRED + strengthened (subsumes the old `check_pipeline_runtime_terminal_state`). A `status: complete` run / `workflow_complete` event is INVALID unless EVERY declared step (per `step_declared` events at run-start) has a passing verdict in the log: a `verification_receipt: verdict: pass`, OR a `verification_class: true` natural-output pass. ERROR. workflow_complete-event-exists is necessary but NOT sufficient — all steps must also be verified (Governance Rule 8 / assert_all_steps_verified). Closes the cdc1615e hollow-cascade class at the runtime check layer.

**DEFERRED to v1.47.0+** (verifier-isolation enforcement):
- `check_skip_authorization_explicit` — every `step_skipped` event with `disposition: skip_with_authorization` references a `skip_authorization` event from a human-class actor (resolves to type:principal or type:human)
- `check_pipeline_runtime_age_bounded` — `status: active` runs older than N days without recent events surface as warning
- `check_verification_receipt_actor_class` — mechanically enforce separate-context verification by requiring verification_receipt's actor to resolve to a session-agent class distinct from the executor (only fires for steps with `step_verifier_role:` declared as non-`same-as-executor`). Defers per Mike-A75 same-as-executor lock; honor-system enforcement via capsule-body declaration carries the discipline in v1.46.0.
- `check_pipeline_run_substrate_authored_by_resolves` — verify the cited `substrate_authored_by:` UID resolves to a type:activation activation_class:pipeline entry

Core checks inherited.

---

## 5. Trust Gradient Gates (NEW v2.0)

Per pipeline.capsule v3.0's `trust_level:` field on step WorkflowNodes:

| trust_level | Gate behavior |
|---|---|
| `approval-required` | At `step_started`, run transitions `status: active → paused` with `pause_started.data.reason: "trust-gradient-gate"`. Resumes on `pause_resumed` with `confirmation_granted_by:`. |
| `auto-with-verification` | No gate; structured verification_receipt sufficient. |
| `auto-after-track-record` | Verifier checks track-record: if this `step_id` (PIPELINE-scoped, NOT global) has ≥ 3 prior `verification_receipt: pass` events across past activations of THIS pipeline AND the step's `exit_criteria:` hasn't changed between those past-pass versions and current, auto-with-verification. Otherwise gates as approval-required. Track-record threshold value (currently 3) may be calibrated based on operational experience. Exit-criteria changes invalidate track-record; the step earns trust under its current contract, not prior contracts. |
| `human-only` | Step cannot be marked complete by any agent; requires `human_signoff` event with valid `signed_by:`. |

Trust level resolution at step boundary: step's own `trust_level:` if declared, else pipeline's `default_trust_gradient:`, else `auto-with-verification`.

---

## 6. Exit Criteria Resolution (NEW v2.0)

When `verification_receipt` walks a step's `exit_criteria:` (per pipeline.capsule v3.0 DSL), UID references in the criteria resolve via:

1. Step's own context (e.g., `spec.uid` resolves to the artifact_link in step_completed)
2. Pipeline-run's `members:` array
3. Pipeline-run's frontmatter `cycle_context` if it names UIDs
4. Pipeline-run's `activation_contract_locked.cycle_root_uid` if declared

Resolution failure during verification = `verification_receipt.verdict: error` with `error_detail: "exit_criterion <text> failed to resolve UID reference"`.

---

## 7. Workflow Visibility Surface (NEW v2.0; deferred render)

Rendered file at `00-tropo-nav/pipelines/active-pipelines.md` auto-lists every `status: active` pipeline-run with:

- pipeline name + activation_uid
- current_stage + current_step
- last event timestamp
- owner + principal UIDs
- count of step_declared / step_completed / step_failed / step_skipped events
- terminal_verification_state (pending / passed / failed)

Auto-rendered by `render-active-pipelines.py`. **Deferred to v1.47.0** — engine substrate ships at v1.46.0; render script lands when operational evidence justifies.

---

## 8. Backward-Compatibility

- All v1.4 schema preserved entirely. v1.4-shaped pipeline-runs remain valid against v2.0 schema; new optional fields default to v1.4-equivalent semantics.
- v1.4 events without OTel GenAI attributes continue to validate; v2.0 events SHOULD carry them but it's not required for backward-compat.
- v1.4 `actor:` field continues to work as canonical UID; v2.0 events MAY add `actor_label_resolved:` rendering hint. No rename.
- Runs activated against v2.6-shaped pipelines (no per-step rich schema) get auto-defaulted: `step_owner_role` inferred from pipeline definition's prose or set to a fallback; `step_verifier_role` defaults to `same-as-executor`; `exit_criteria` empty array (verification_receipt records "no criteria to check; verdict: pass"); `trust_level` defaults to `auto-with-verification`. Activation contract event captures the defaults explicitly so the runtime is self-describing.
- v1.4-shape activation entries (`type: activation, activation_class: pipeline`) continue to exist for backward-compat alongside new v2.0-shape `type: pipeline-run` entries. The two-entry vault substrate model links them via `substrate_authored_by:` on the v2.0 entry.

---

## 9. Composes-With

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor
- **[playbook-run.capsule v2.1 (f2a8c3e1)](playbook-run.capsule.md)** — structural template (`modeled_on`); pipeline-run forks + specializes. v2.0 amendment may inform a future playbook-run amendment for symmetric structural enforcement; out of v1.46.0 scope.
- **[pipeline.capsule v3.0 (e4c8a6b2)](pipeline.capsule.md)** — the template type pipeline-runs execute. Pinned via `pipeline_version:` at run-start. v2.0 pipeline-run READS v3.0 pipeline's per-step rich schema fields (step_owner_role / step_verifier_role / verification_class / depends_on_steps / exit_criteria / trust_level). cascade_spec semantics preserved; cascade-spawned workstreams produce independent activations with `depends_on_activation:` edges back to the spawning activation.
- **[activation.capsule (per registry)](activation.capsule.md)** — agent activations are distinct from pipeline-runs; v2.0 clarifies the type discrimination. The legacy `type:activation activation_class:pipeline` shape from v1.35.0 era continues to exist for substrate-authoring entries (pipeline-activate.py output); new v2.0 runtime entries use canonical `type: pipeline-run` shape. Two-entry vault substrate model: pipeline-activate.py writes v1.4-shape activation entries (substrate authoring); pipeline-runtime.py writes v2.0-shape pipeline-run entries (runtime execution); the two link via `substrate_authored_by:` on the v2.0 entry.
- **[project.capsule (34e4cb0b)](project.capsule.md)** — projects may be pipeline-run members. Activation-root-project at step-0 of dev-pipeline; pipeline-run children declare `member_of: [<root>]`.
- **[task.capsule (3289712a)](task.capsule.md)** — work-items may be pipeline-run members. Member status transitions happen via task's request-lifecycle, not via run mutation (Rule 7).
- **[entity.capsule (1e9c3f7a)](entity.capsule.md)** — `owner:`, `principal:`, `authorized_by:` reference entities. `actor:` (UID) + `authorized_by:` (UID) on events resolve via entity registry; `actor_label_resolved:` is rendering hint only (NOT canonical).
- **[release.capsule (b19e8d43)](release.capsule.md)** — release-pipeline-runs reaching ship gate write `subsystem-registry.jsonl` rows per release.capsule Rule 11.
- **[subsystem-hub.capsule (8a4e21c5)](subsystem-hub.capsule.md)** — bidirectional pair with release_history rows at ship gate.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.
- **[v1.46.0 pipeline-runtime.py design-spec (2b809e0f)](../../vault/files/2b809e0f.md)** — canonical executor design-spec; pipeline-runtime.py implements this v2.0 contract.

**sa.\* dispatch sub-pattern:** pipeline-runs whose pinned pipeline includes steps that dispatch session-agents (sa.\*) declare dispatch via `relationships:` array entry of `kind: dispatches`. Dispatched sa.\* writes verified output back to run; executor advances after verification per `dispatch-sa-step.skill` convention.

---

## Member Processing — How Runs Execute Over Members

The core model: a pipeline-run is a coordination container + audit trail. It holds `members:`, pinned `pipeline_version:`, and a `current_stage:` + `current_step:` pointer. Execution happens via **processor-agents** operating within the run.

### Step 1 — Processor discovers the run

An agent reads the pipeline-run's `definition.md`. Sees: which pipeline is pinned (and at which version); what members are in scope; which stage/step is current.

**Confirmation gate check.** Before proceeding to Step 2, executor reads the current step's WorkflowNode. If `requires_confirmation: true` is set AND no `pause_resumed` event has fired for this step entry yet (OR step's `trust_level: approval-required` AND not yet authorized this entry), executor:

1. Transitions run `status: active → paused`
2. Appends `pause_started` event to `run.jsonl` with `data: {"reason": "human-confirmation-required" | "trust-gradient-gate", "step": "<current-step-uid>"}`
3. Also appends `status_changed` event (per Rule 4 — all status transitions log `status_changed`)
4. Halts. Does NOT proceed to processor filtering.

Run remains paused until authorized confirmer (owner / principal / `authorized_by` entity) appends `pause_resumed` event with `data.confirmation_granted_by: <entity-uid>` and transitions `status: paused → active`.

**Re-entry semantics.** Confirmation pause fires once per step ENTRY — re-entry of the same step (e.g., after regression-reopen) re-fires the gate. Each re-entry requires NEW `confirmation_granted_by:`.

### Step 2 — Processor filters members by `requested_of`

Agent filters `members:` by `requested_of = <own entity-uid>`:

- **Direct members:** work-item with `requested_of: <agent-entity>` is in processor's slice
- **Project members:** processor recurses into project's `member_of:` graph (bounded depth 3) to find work-items, filters each by `requested_of`
- **Multiple-project membership:** work-item reachable via multiple project members is included once (dedup)
- **Member `requested_of: <other-agent>`:** skipped; another processor owns that slice

### Step 3 — Processor executes the step

The step's work happens via the **member's own request-lifecycle** (not via a run mutation). E.g., if step is "review the design-brief members," processor transitions each reviewed member through `active → verify → done` via the request-lifecycle protocol. The run observes; it doesn't cause directly.

### Step 4 — Processor logs step completion + writes verification_receipt

Processor appends `step_completed` event to run's `run.jsonl` with member-UIDs processed + artifact_links. **(NEW v2.0)** Processor (or override verifier per `step_verifier_role:`) writes a structured `verification_receipt` event walking each `exit_criteria:` entry from the step's pipeline definition + asserting verdict against substrate. The pair `step_completed` + `verification_receipt: verdict: pass` is what makes the step truly-done. Run's `current_step:` advances per pipeline's `next_steps:` or `depends_on_steps:` schema.

For `verification_class: true` steps, the structured receipt is bypassed; the step's natural output (build exit code / HTTP response / validator pass-fail) IS the verification, captured in `step_completed.data`.

### Step 5 — Repeat or complete

Next step's processor (same agent or different) picks up new `current_step:`, filters `members:` by their own `requested_of`, executes. Continues until terminal step reached. **(NEW v2.0)** Terminal step writes `workflow_complete` event; sa.pipeline-verify dispatched for terminal verification produces `verifier_findings` event; human signs off via `human_signoff` event; `status: active → complete`.

### Special cases

- **Empty processor slice:** agent filters and gets zero members → skip; logged but no-op
- **Stage-exit conditions:** WorkflowNode may declare `condition:` string gating advancement based on member statuses; condition reads member state but doesn't cause it
- **Multiple runs on shared member:** per Rule 7, first processor to transition wins; other runs observe (concurrency_model: independent default)
- **Project-member contents change mid-run:** per `member_snapshot_mode:` (`live` or `snapshot-at-start`)
- **(NEW v2.0) Mid-flight contract amendment:** activation contract is immutable; legitimate amendments require close-and-respawn via `supersedes_activation:` per the dual-semantics field definition above
- **(NEW v2.0) Skip authorization:** agent emits `skip_request` event; human emits `skip_authorization` event referencing the step + reason; subsequent `step_skipped` event references both. Validator enforcement deferred to v1.47.0+.

**What this DOES NOT say:** pipeline-runs do not "run" members; they orchestrate processors. Runs don't have CPU, state mutation authority, or execution threads. Every action belongs to a processor-agent acting within the run's context. The run is a governance + audit shell.

### History

The v1.0/v1.1/v1.2/v1.3/v1.4 amendment-block prose, the Archival Trigger procedure, the Known Enforcement Gaps table, the Execution Routing block, the Run Folder Naming convention, the run.state.json schema example, the v1.2 sub-patterns block (activation-root-project + sa.* pipeline-step verifier + subsystem-registry write), the full §Studio — Shop Signage authoring procedure, the Migration Notes (v1.3 project-walker → v2 pipeline-run), the Extension-from-core narrative, and the full changelog are preserved in the companion [pipeline-run.history.md (b90c9495)](pipeline-run.history.md) governed by `capsule-history.capsule` (5ec083a3). v2.0 amendment narrative + diff appended to history at v1.46.0 ship.

---

*pipeline-run capsule definition | v2.0 ACTIVE | history at [pipeline-run.history.md](pipeline-run.history.md) | v2.0 body authored 2026-05-20 by Argus A76 per v1.46.0 Replacement-Body Specs (8e5b3c47 v0.5 LOCKED). Lock-break authorized by Mike-A75 2026-05-20. Prior v1.0–v1.4 locks preserved in history. UID `5a8f3b2c` preserved.*
*"The pipeline is the template. The run is the instance. The contract is locked at activation. The receipt is the proof."*
