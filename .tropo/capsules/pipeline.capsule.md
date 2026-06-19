---
subsystem_hub:
  - "2d083137"
uid: e4c8a6b2
name: "pipeline"
type: capsule-definition
extends: core
version: "3.2"
supersedes_version: "3.1"
tier: os
author: argus
created: 2026-04-21
modified: 2026-06-09
modified_by: argus-a105
status: active
last_locked_at: 2026-05-07
last_locked_by: argus-a49
last_body_refactor: 2026-05-20
v3_2_amendment_note: "v3.1 -> v3.2 amendment 2026-06-02 by Argus A94 (v1.64 Verification-Command Hardening; dev-spec d6e50d38; opened in PARALLEL with the v1.63 close per Mike-A94 'two pipelines in parallel' — concurrency_model: independent is the documented default, pipeline.capsule is status:active not locked, so no lock-break: the amendment is the cycle's sanctioned committed_substrate). Adds the verification_command step field (the machine that produces a vc:true step's natural verdict) + tightens verification_class to require machine-produced output for GATE steps. Closes the vc:true self-attestation hole (the parallel to v1.62 B4 which removed the vc:false stdin hatch). NON-BREAKING by design: verification_command is OPTIONAL/additive; the REQUIRED-for-gate invariant ratchets via Check 20 (WARN now -> ERROR later, exactly as Check 19 did) so it cannot red-light a concurrent cycle's validate. Companion (same cycle): Rule 11 extension + Check 20 (WARN) + Talos engine evaluate_criterion runner. The per-criterion verification_method exit_criteria schema change (6ec09070, the mixed-class completion) lands after its own gauntlet round."
v3_0_anchor: "Argus A76 amendment per v1.46.0 Replacement-Body Specs (8e5b3c47 v0.5 LOCKED). Adds per-step rich schema for step WorkflowNode entries (step_owner_role / step_verifier_role / verification_class / depends_on_steps / exit_criteria / trust_level / compensation_step_id / instructions_ref / retry_policy / timeout_hours) + pipeline-level defaults (default_trust_gradient / default_retry_policy / default_timeout_hours). Adds same-as-executor verifier pattern + verification-class step pattern + minimum-viable exit-criteria DSL + 2 new validator checks. All v2.6 schema preserved as OPTIONAL — pre-v3.0 step entries continue to validate. Pairs with pipeline-run.capsule v2.0 which provides the runtime enforcement layer (structured verification_receipt + activation contract + trust gradient gates + new event types). Companion design-spec at vault/files/2b809e0f.md v0.2 LOCKED. Body authored current-tense per Mike-A75 'no history in capsules' lock 2026-05-20; v2.6 and prior amendment narratives + diffs extracted to pipeline.history.md (fa811352)."
v3_1_amendment_note: "v3.0 -> v3.1 amendment 2026-05-31 by Argus A89 (v1.62 Substrate-Enforces-Discipline cycle; dev-spec c1a62d3f; spine cdc1615e; Mike-A89 con). Adds Governance Rule 11 (completion-gate invariant) + Validation Check 19 (check_gate_steps_have_exit_criteria) + scopes the Part-8 backward-compat fallback. CODIFIES the engine behavior Talos shipped in Lane B (pipeline-runtime.py 9e7003b1): for ship/close steps + trust_level:approval-required steps, empty/absent exit_criteria resolves to FAIL (NOT the permissive v2.6 fallback); refuse-bootstrap if a gate step declares no criteria; assert_all_steps_verified before workflow_complete; self-attestation (--verification-data-stdin) removed. Root cause closed: Part-8's v2.6 empty-exit_criteria fallback was the escape hatch ('fail-closed engine shipped failing open', cdc1615e) — the permissive fallback now applies ONLY to ordinary non-gate steps. Pairs with release.capsule v3.10 Rule 17 (Vela ship-block) + pipeline-run.capsule runtime. Body current-tense per Mike-A75 no-history lock; this narrative is the frontmatter amendment record."
history_file: fa811352
enforced_enums:
  status: [draft, active, locked, archived, retired]
meta_status_rollup:
  to-do: [draft]
  in-progress: [active]
  done: [locked, archived, retired]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — 5-section pedagogy
aligned_with:
  - f2e8a7b1   # Tropo Work v2 Architecture Specification
  - e1c47a9f   # dev-pipeline + vault inbox primitive
  - e7a3b591   # v1.9.2 design brief — Self-Doc Discipline
  - 2b809e0f   # v1.46.0 pipeline-runtime.py design-spec
composes_with:
  - a3f1e7b2   # release-plan.capsule
  - 5a8f3b2c   # pipeline-run.capsule (runtime layer)
tags: [capsule-definition, pipeline, workflow-node, per-step-rich-schema, same-as-executor-verifier, exit-criteria-dsl]
---

# pipeline — Capsule Definition v3.0

## 1. Intent

A pipeline is a declarative workflow template. Pipelines are composed of WorkflowNodes recursively — a pipeline is a root WorkflowNode, stages are composite WorkflowNodes, steps are leaf WorkflowNodes. One capsule, fractal composition. Pipelines are executed by pipeline-runs (per [pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)); the pipeline is the template, the pipeline-run is the instance.

Declare a workflow. Name the shape of the work: stages, steps, and the transitions between them. Pipelines are the protocol layer; pipeline-runs are the execution layer. This split (DAG/DAG-Run in Airflow; Process/Instance in BPMN) is the load-bearing architectural move of v2.

Before creating a pipeline: is there an existing pipeline that covers this workflow? Amending an existing pipeline via version bump is cheaper than authoring a new one. Pipelines are versioned artifacts; pipeline-runs pin the version at start.

**The WorkflowNode model.** Pipeline, Stage, and Step are the same structural type — a WorkflowNode. A Pipeline is the root. Stages have children. Steps are leaves. Naming is presentation for humans; the schema has one capsule. This lets a workflow compose to any depth (subject to soft-cap at depth 3 per industry learning — see Rule 5).

**v3.0 adds per-step rich schema.** Step WorkflowNodes (leaf nodes) gain optional structured fields naming their executor class, their verifier class, their machine-checkable exit criteria, their DAG dependencies, and their trust gradient. The runtime layer (pipeline-run.capsule v2.0) enforces these contracts via structured `verification_receipt` events. Steps stop being prose paragraphs an executor reads; they become structured contracts an executor's `verification_receipt` resolves against substrate.

Failure mode prevented at v3.0: memory-resident step discipline (an agent reading a step's prose and self-asserting completion without machine-checkable evidence). Closes the failure mode named in [d.skeptic-arch's audit (9f6b01e6)](../../vault/files/9f6b01e6.md) at step-scale.

---

## 2. Schema

### Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `uid` | 8-hex | Per core. Every WorkflowNode has its own UID and vault entry. |
| `type` | literal | `pipeline` (pipeline is its own top-level type in v2, not a playbook subtype) |
| `subtype` | literal | `workflow-node` — every entry in this capsule hierarchy is a WorkflowNode; subtype is fixed |
| `name` | string | ≤120 chars. Human-readable (e.g., "Release Pipeline", "Research Stage", "Draft Step"). |
| `version` | semver string | Increments on any structural edit. Pipeline-runs pin this version at start. |
| `author` | UID | Entity that authored the pipeline. Resolves to entity. |
| `children` | UID array | Each child is a separate vault entry. Empty for leaf steps; non-empty for stages and root pipelines. Composition via UID-references, not inline objects. |
| `state` | enum | `active` / `archived`. Lifecycle-visibility per core. |
| `status` | enum | `draft` / `active` / `locked` / `archived`. See §State Machine. |

### Optional Frontmatter (preserved from v2.6 unless noted)

| Field | Type | Purpose |
|---|---|---|
| `next_steps` | UID array | Successor WorkflowNodes. Empty `[]` for terminal. Length 1 for linear default. Length >1 for branching (v2.0 schema-supported; behavior deferred to v2.2). Field may be omitted on terminal leaves; readers treat omission as equivalent to `[]`. |
| `condition` | string | Expression governing when this node activates given parent's completion. Used for branching and conditional stages. Optional at v2.0; richer semantics deferred to v2.2. |
| `role` | string | Informational label (`"stage"` / `"gate-check"` / `"verify-step"` / `"workstream"`). Human-readable; does not drive behavior. `"workstream"` signals a sub-pipeline spawned by a parent pipeline's `cascade_spec:` (per v2.6 cascade pattern). |
| `domain` | string | Workflow domain this pipeline serves. Lowercase-hyphen. Typically set only on root pipelines. |
| `supersedes` / `superseded_by` | UID | Bidirectional pair for supersession |
| `locked_by`, `locked_at` | string, date | Standard capsule lock provenance when `status: locked` |
| `owner` | UID | Entity responsible for this pipeline (or sub-node). Typically same as `author:` at creation; may transfer. |
| `relationships` | typed-edge array | Schema v2 unified relationships |
| `requires_confirmation` | boolean | Default `false`. When `true` on a leaf step, pipeline-run executor transitions to `status: paused` on step entry (BEFORE step work begins) and waits for explicit human confirmation. Use for steps that need human approval of inputs/decisions before processing. Distinct from `restart_strategy: manual` on pipeline-run, which pauses on step FAILURE — `requires_confirmation:` pauses on step ENTRY. Honored by pipeline-run.capsule v1.1+. |
| `cascade_spec` | object | Declarative substrate-generation specification. When present (typically on a root or composite WorkflowNode), the pipeline-activation runtime ([`.tropo/scripts/pipeline-activate.py`](../scripts/pipeline-activate.py)) reads this field at activation-time and generates the declared substrate (project-plan + spawned workstream activations) as part of activation step-0. Composes with §Rule 10 activation-root-project authoring (cascade-generated substrate `member_of:` the activation-root-project). Pipelines without `cascade_spec:` activate without cascade behavior. Schema + validation rules at §Key Sub-patterns below. |

### Per-Step Rich Schema (NEW v3.0; OPTIONAL — preserves all v2.6)

For step WorkflowNode entries (entries with `subtype: workflow-node` whose body indicates step role — typically leaf nodes with `children: []`) — new OPTIONAL frontmatter fields. Pre-v3.0 step entries without these fields continue to validate; v3.0-shaped step entries gain machine-checkable structure.

| Field | Type | Constraint |
|---|---|---|
| `step_owner_role` | string | Which agent class executes this step. Values: `argus` / `talos` / `vela` / `metis` / `sa.<slug>` / `director` / `human-only`. Schema-resolvable to entity registry. |
| `step_verifier_role` | string | OPTIONAL. Which agent class verifies this step's completion. Default if absent: `"same-as-executor"`. Other values: any agent-class string. For explicit override on high-stakes steps (lock-breaks, schema migrations, security-sensitive ops), declare a different class than `step_owner_role` to trigger separate-context sub-agent verification dispatch. |
| `verification_class` | boolean | OPTIONAL. Default `false`. When `true`, marks the step as inherently-verifying (build step where `npm run build` exit code IS the verdict; HTTP-fetch step where response code IS the verdict; validator-script step where script output IS the verdict). Bypasses the structured `verification_receipt` event; the step's natural output is the verification. **(v3.2 / v1.64)** For a `verification_class: true` GATE step (ship/close OR `trust_level: approval-required`), that natural output MUST be machine-produced via `verification_command` — never an agent-supplied `--natural-verdict`. A vc:true gate step with no `verification_command` is a specification error (Rule 11 extension → FAIL: it cannot be machine-verified). |
| `verification_command` | string OR null | **(NEW v3.2 / v1.64)** OPTIONAL in general; **REQUIRED for `verification_class: true` GATE steps** (ship/close OR `trust_level: approval-required`); WARN for ordinary vc:true steps (a build step's `npm run build` exit code genuinely IS self-verifying). The shell command the engine runs at `step_completed` to produce the step's natural verdict — exit 0 = pass, nonzero = fail; stdout/stderr tail captured into the `step_completed` event. Supports named-handle substitution: `{activation}`, `{activation_root}`, `{dev_spec}`, `{triggered_test_activation}` are replaced with the run's live UIDs before execution. Closes the vc:true self-attestation hole. Enforced by Check 20 (WARN-ratchet → ERROR). |
| `verdict_cwd` | path OR null | **(NEW v3.3 / v1.66)** OPTIONAL. Working directory in which the engine runs `verification_command`. Default: vault root (VAULT_ROOT). Use for steps whose verification must run outside the vault — e.g. platform-repo build/test steps (`/Users/mike/dev/tropo-ai`). Named-handle substitution applied to `verification_command` before execution in this directory. |
| `depends_on_steps` | UID array | DAG edges. UIDs of other step WorkflowNodes that must complete before this step is eligible. Empty array (or omitted field) = root step. Used by pipeline-run executor to compute eligible-next-steps set. |
| `exit_criteria` | string array | List of machine-checkable assertions. Each entry uses the exit-criteria DSL (defined below). Verifier (or executor, per same-as-executor default) walks them deterministically at `step_completed` time and writes a structured `verification_receipt` event with per-criterion verdict. |
| `trust_level` | enum | OPTIONAL. One of: `approval-required` / `auto-with-verification` / `auto-after-track-record` / `human-only`. Default if absent: pipeline's `default_trust_gradient:` (see below). |
| `compensation_step_id` | UID OR null | OPTIONAL. What step runs if THIS step needs to be undone (saga pattern). `null` (or omitted) = no compensation; failure modes don't include rollback. v3.0 ships single-step compensation only (compensation step's own failure halts pipeline); saga-array compensation (multi-step ordered reverse-undo) defers to v3.1+. |
| `instructions_ref` | path OR UID | OPTIONAL. Pointer to capsule/playbook/document explaining HOW the step's work is done. Centralizes prose; doesn't duplicate. |
| `retry_policy` | object | OPTIONAL. `{ max_retries: <int>, backoff: linear \| exponential }`. Default: `{ max_retries: 0, backoff: linear }`. |
| `timeout_hours` | int | OPTIONAL. Default 24. Verifier flags step as stale if `step_started` event > timeout_hours old without `step_completed`. |

### Pipeline-Level Defaults (NEW v3.0)

On root pipeline WorkflowNode (in addition to v2.6's `cascade_spec:`):

| Field | Type | Purpose |
|---|---|---|
| `default_trust_gradient` | enum | Default `trust_level:` for steps without explicit override. Per-pipeline default. |
| `default_retry_policy` | object | Default retry_policy for steps without explicit override. |
| `default_timeout_hours` | int | Default timeout. |

### WorkflowNode Architecture

Every entry in this capsule hierarchy is a **WorkflowNode**. A pipeline is a root WorkflowNode; its children are WorkflowNodes (typically called "stages"); their children are WorkflowNodes (typically called "steps"). Naming is presentation for humans; the schema has one type.

**Composition:**

```
Pipeline (root WorkflowNode)
├── Stage (composite WorkflowNode with children)
│   ├── Step (leaf WorkflowNode, no children)
│   └── Step
└── Stage
    ├── Step
    └── Step
```

Each box is a separate vault entry (`type: pipeline, subtype: workflow-node`) referenced by UID via `children:`. This mirrors Tropo's composition pattern elsewhere: `members:` on pipeline-runs, `member_of:` on work-items, `children:` here — all UID-reference compositions to independently-governed vault entries.

**Composition depth is bounded.** Structural composition supports arbitrary tree depth in principle, but governance rule §5 (soft-cap at 3 levels) keeps practical pipelines at 3 nested WorkflowNodes maximum without explicit rationale. Honest statement: **fractal structural composition is schema-supported; practical composition depth is bounded to 3 by capsule rule.**

**Flow.** Flow is expressed via `next_steps:` AND (NEW v3.0) `depends_on_steps:` on step WorkflowNodes:

- **Linear (default):** each node's `next_steps:` has one UID. Execution flows: step A completes → next_steps: [B] → step B starts.
- **Branching (schema-supported, behavior v2.2):** `next_steps:` has multiple UIDs. At v2.0, behavior is "pick the first one whose `condition:` evaluates true." Richer semantics deferred.
- **DAG (NEW v3.0):** step's `depends_on_steps:` names UIDs of step WorkflowNodes that must complete before this step is eligible. Executor computes eligible-next-steps set from the DAG; permits multi-input convergence beyond linear `next_steps:`. Acyclic invariant enforced by validator check below.
- **Terminal:** `next_steps: []` or field omitted — no successor; execution completes here.

### Required Body Sections (6, in declared order)

1. **`## Purpose`** — One paragraph naming what workflow this pipeline governs + what it does NOT govern. Disambiguates against adjacent pipelines in the same domain.
2. **`## Structure`** — Diagram (ASCII or prose) of the pipeline's WorkflowNode tree. Names each node, its role, and the flow relationships.
3. **`## Nodes`** — Table enumerating every child WorkflowNode. Columns: UID, name, role, children-count, next_steps-count. Each UID links to the child's vault entry.
4. **`## Flow Rules`** — Prose description of how execution advances. Linear-default, branching, or DAG via `depends_on_steps:`. Any condition expressions. Terminal nodes.
5. **`## Cold-Boot Walk-Through`** — Narrative walking a hypothetical pipeline-run from start to completion. Minimum one complete walk; multiple if common branches warrant examples. Stranger-readable without external context.
6. **`## Known Enforcement Gaps`** — Per ADR-031 pattern. Table of gap / what closes it / target release / owner.

Appended: **`## Changelog`** — Append-only log of amendments.

**Optional body sections:**

- `## Design Rationale` — REQUIRED when nesting depth > 3
- `## Related Pipelines` — for vaults with multiple pipelines
- `## Migration Protocol` — REQUIRED when superseding a prior pipeline

---

## 3. State Machine

```
draft → active → locked → archived (supersession or retirement)
   ↑________↓ (revision during draft; locked pipelines amend via supersedes)
```

**Required starting state:** every new pipeline file MUST be authored at `status: draft`. Direct creation at `active` or `locked` is a validation error.

| Status | Meaning |
|---|---|
| `draft` | Pipeline being authored. Structure still evolving. Pipeline-runs may NOT pin draft versions. |
| `active` | Pipeline is live. Pipeline-runs may pin this version. Minor revisions permitted but trigger version bump. |
| `locked` | Pipeline committed. Amendments require successor via `supersedes:`. |
| `archived` | Historical. Pipeline no longer used; superseded or retired. |

**Valid transitions:**

- `draft → active` — author finishes first-draft; pipeline goes live
- `active → draft` — revision before formal lock (permissible but rare)
- `active → locked` — formal lock; amendments require supersession
- `locked → archived (superseded)` — successor authored; bidirectional `supersedes:` / `superseded_by:` pair set atomically
- `any → archived (retired)` — pipeline no longer needed; any pipeline-runs still active must complete or cancel on the pinned version

---

## 4. Same-As-Executor Verifier Pattern (NEW v3.0)

Default for `step_verifier_role:` is `same-as-executor`. The executor agent writes the structured `verification_receipt` event at step boundary — per-criterion assertions checked against substrate, explicit verdict per criterion + overall verdict, rationale. The forcing function is the structured receipt format, not role-separation.

**Why this works:** *agents don't tend to lie when they have to sign off on something in a record.* The structured receipt makes hallucinated completion visible — the agent has to enumerate each `exit_criteria:` entry + assert verdict against substrate that's mechanically checkable. False claims contradict substrate the next reader can verify.

**The cardboard-muffin defense at step-scale** comes from:

- Mandatory `verification_receipt` event before any dependent step becomes eligible (validator enforced; see pipeline-run.capsule v2.0 §Validation Checks)
- Structured per-criterion assertions in the receipt (agent enumerates each `exit_criteria:` entry + verdict)
- Substrate-checkable nature of the `exit_criteria:` (verifier reasoning is constrained to what substrate actually shows, not what the agent's reasoning produced)

**Explicit override for high-stakes steps:** declare `step_verifier_role: <other-class>` (different from `step_owner_role:`). Triggers a separate sub-agent dispatch with isolated context (step_declared event + step_completed.artifact_links only; no executor reasoning chain passed). Mechanical validator enforcement of the isolation defers to v1.47.0+ if evidence justifies; v3.0 ships honor-system enforced via capsule-body declaration.

---

## 5. Verification-Class Step Pattern (NEW v3.0)

Steps whose work IS verification — `npm run build` exit code IS the verdict; HTTP-fetch response status code IS the verdict; validator-script output IS the verdict — declare `verification_class: true` and bypass the structured `verification_receipt` overhead. The step's natural output is the verification. A `verification_class: true` step still writes `step_completed` event with the verdict captured in event data (build exit code; HTTP response; validator pass/fail); next-step eligibility computes from the natural verdict rather than from a separate receipt event.

---

## 6. Exit-Criteria DSL (NEW v3.0; minimum-viable)

Each entry in a step's `exit_criteria:` array is a single machine-checkable assertion string. Supported assertion shapes at v3.0:

| Shape | Example | Semantic |
|---|---|---|
| `<uid-ref>.exists` | `spec.uid exists` | The referenced vault entry exists on disk |
| `<uid-ref>.<field> == <value>` | `spec.status == locked` | Frontmatter field equals value |
| `<uid-ref>.<field> contains <value>` | `spec.member_of contains <cycle-root-uid>` | Array field contains element |
| `<uid-ref>.body matches <pattern>` | `release_entry.body matches "§Chain Progress Snapshot"` | Markdown body contains pattern (regex or literal) |
| `file:<path>.exists` | `file:argo-os/external-work/web/articles/<uid>/index.md exists` | File exists at path |

UID references in `exit_criteria:` resolve via the pipeline-run's context (members + cycle_root + activation_uid + step-local artifact_links). Spec resolution rules locked in pipeline-run.capsule v2.0 §Exit Criteria Resolution.

### 6a. Per-criterion `verification_method` (v3.2 / v1.64) — prefix-dispatched, NOT a schema change

Gate `exit_criteria:` are **mixed-class** — a real close step legitimately mixes a field-check, a validator-run, a human signoff, and an aggregate read ([per 6ec09070](../../vault/files/6ec09070.md)). The verification *method* for each criterion is encoded **by prefix on the criterion string**, so `exit_criteria:` stays a plain string array (fully back-compat — a bare string is DSL; zero schema migration). The engine's `evaluate_criterion` ([pipeline-runtime.py](../../vault/tools/9e7003b1.py)) dispatches:

| Criterion shape | Method | Resolver |
|---|---|---|
| (no prefix) | `dsl` | parse + substrate-read (§6 above) |
| `human: <subject>` | `human_signoff` | a `human_signoff` event with verdict accepted/approved |
| `aggregate: <key> <op> <value>` | `aggregate` | a `test_aggregate` event carrying that key/value |
| *(step-level)* `verification_command` | `command` | the engine runs the command at `step_completed`; exit code = verdict (§2) |

**Why prefixes, not a structured field.** Encoding the method in the string keeps `exit_criteria:` a string array — every existing criterion still validates (bare = DSL). This documents the engine's actual model; it is not a new schema.

**A vc:true gate's verdict source** is therefore whichever method fits: `verification_command` (command), a `human:` criterion / `trust_level: approval-required` (human_signoff), or an `aggregate:` criterion. A human-approval gate (e.g. close-cycle) is human_signoff-verified and needs **no** `verification_command`. Check 20 WARNs only a vc:true step with **no verdict source of any kind**.

**Deferred to v3.1+:**

- Multi-assertion-per-string composition (AND/OR within one criterion) — v3.0 is single assertion per array entry
- Quantifier expressions (`all member_of entries have status: done`) — defers to v3.1
- Custom DSL extensions per earn-the-abstraction-strict

---

## 7. Validation Rules

### Governance Rules (11, in addition to core)

1. **One root-pipeline per domain, per active version.** Duplicate root pipelines with the same `domain:` at `status: active` or `locked` are a validation error. Distinct workflows warrant distinct domains.
2. **Children reference separate vault entries.** Authoring a pipeline with inline children (children-as-objects instead of children-as-UID-references) is a v2.0 violation. Every WorkflowNode is its own vault entry.
3. **`version:` increments on any structural edit.** Adding/removing children, changing `next_steps:`, adding `condition:`, adding/changing per-step rich schema fields — all trigger a version bump. Pipeline-runs pin at start; the pinned version does not drift.
4. **Forward-only default.** Linear pipelines (every node's `next_steps:` length 1 or 0) flow forward only. Enforced at pipeline-run execution time by the executor; spec-§2.4 inheritance.
5. **Nesting depth soft-cap at 3.** Deeper nesting requires `## Design Rationale` body section documenting rationale. Validator warning at depth 4+; mechanical rejection v2.2.
6. **Author is the entity; owner may transfer.** `author:` immutable after creation (provenance). `owner:` may transfer via explicit entity transition (prior owner's consent required per core Rule 3).
7. **Archived pipelines are read-only.** No frontmatter edits. Active pipeline-runs continue on the pinned version; new runs cannot start.
8. **Pipeline amendments via supersession.** Once `status: locked`, structural changes require authoring a successor pipeline with new UID, setting bidirectional `supersedes:` / `superseded_by:` pairs atomically.
9. **(v2.1)** `requires_confirmation: true` field is meaningful only on **leaf step** WorkflowNodes. Presence on composite stages is honor-system ignored by the executor; declare confirmation gates on the actual gating step.
10. **(v2.2) Activation-root-project authoring at step-0** — every pipeline activation MUST author a `type: project` vault entry as part of its step-0 (accept-work-item) sub-actions; that project becomes the graph parent for all downstream artifacts the activation produces. Substrate invariant: *"Everything a pipeline activation produces is a child of the activation root project."* Runtime enforcement via [`.tropo/scripts/pipeline-activate.py`](../scripts/pipeline-activate.py) at v1.35.0; per-pipeline migration earned at future cycles.
11. **(v3.1 / v1.62) Completion-gate invariant — empty `exit_criteria` is FAIL for gate steps, not pass.** For any **`verification_class: false`** step that is a ship/close step OR carries `trust_level: approval-required`, an absent or empty `exit_criteria:` resolves to **FAIL**, never the permissive v2.6 empty-criteria fallback (§8). *(Carve-out: `verification_class: true` steps self-verify via their natural output per §5 — the build exit code / HTTP status / validator verdict IS the verification — so they are exempt from the non-empty requirement. This matches the engine: pipeline-runtime.py B1 applies empty→FAIL to `verification_class: false` steps and auto-receipts `verification_class: true` steps from natural output.)* Three coupled requirements: (a) a pipeline-run MUST refuse to bootstrap if any such gate step declares no `exit_criteria:` — you cannot start a run that cannot be verified at the end; (b) `workflow_complete` MUST NOT fire until `assert_all_steps_verified` confirms every step carries a real PASS `verification_receipt`; (c) criteria are **engine-computed against substrate**, never agent self-attestation (the `--verification-data-stdin` path is removed). Runtime enforcement: [`pipeline-runtime.py`](../../vault/tools/9e7003b1.py) (v1.62 Lane B — B1 empty→FAIL, B2 refuse-bootstrap, B3 assert_all_steps_verified, B4 self-attestation removed). This closes the "fail-closed engine shipped failing open" class ([cascade-completion retrospective cdc1615e](../../vault/files/cdc1615e.md)): the §8 empty-`exit_criteria` fallback was the escape hatch. Composes with release.capsule v3.10 Rule 17 (the ship-block). **(v3.2 / v1.64) The vc:true branch — completing both gate-step branches.** The §5 carve-out (vc:true steps self-verify via natural output) holds ONLY when that natural output is *machine-produced*: a `verification_class: true` GATE step MUST have a **verdict source** — a `verification_command` (command method; engine runs it at `step_completed`, exit code = verdict), a `human:`/`trust_level: approval-required` human_signoff, or an `aggregate:` criterion (the per-criterion methods, §6a). A vc:true gate step with **no verdict source of any kind** is the **vc:true self-attestation hole** (an agent typing `--natural-verdict pass` with no mechanism that produced the verdict — the parallel to the vc:false `--verification-data-stdin` hatch v1.62 B4 removed). It resolves to FAIL once Check 20 ratchets to ERROR (**WARN at v1.64** so it cannot red-light a concurrent cycle's validate while existing steps are remediated). Both gate-step branches are now closed: **vc:false needs `exit_criteria` (Check 19); vc:true needs a verdict source (Check 20).** Engine: `evaluate_criterion` dispatches the per-criterion methods + runs `verification_command` (pipeline-runtime.py 9e7003b1); the validator catches a sourceless vc:true step at rebuild (Check 20).

### Validation Checks (20; Checks 1-19 ERROR-severity at check-in, Check 20 WARN-ratchet at v1.64)

1. `type: pipeline`
2. `subtype: workflow-node`
3. `name:` present, ≤120 chars
4. `version:` is valid semver
5. `author:` resolves to an entity
6. `children:` (if non-empty) — each UID resolves to another `type: pipeline, subtype: workflow-node` entry
7. `next_steps:` (if present) — each UID resolves to another WorkflowNode in this tree or sibling scope
8. `status:` ∈ {draft, active, locked, archived, retired}
9. `state:` ∈ {active, archived}
10. New pipeline files start at `status: draft`
11. Body contains §Purpose, §Structure, §Nodes, §Flow Rules, §Cold-Boot Walk-Through, §Known Enforcement Gaps in that order
12. `supersedes:` / `superseded_by:` (if present) form bidirectional pairs
13. `domain:` (if present) is unique across active/locked root pipelines
14. *(honor-system)* Nesting depth ≤3 (warning at depth 4+; mechanical bound v2.2)
15. *(honor-system)* Cold-boot verifiable: stranger reading the pipeline can trace a walk via §Cold-Boot Walk-Through without external context
16. **(v2.1)** If `requires_confirmation:` is present, value is boolean. Field is meaningful only on leaf step WorkflowNodes (`children: []`); presence on composite nodes is honor-system ignored by executor.
17. **(NEW v3.0) `check_step_verifier_distinct_from_owner_when_overridden`** — for step WorkflowNodes where both `step_owner_role` and `step_verifier_role` are declared AND `step_verifier_role != "same-as-executor"`, they must be different agent classes. Enforces the explicit-override discipline (an explicit `step_verifier_role:` value MUST mean separate-context verification).
18. **(NEW v3.0) `check_step_depends_on_acyclic`** — for any pipeline definition graph, walk all step's `depends_on_steps:` and confirm no cycles. DAG invariant enforced structurally.
19. **(NEW v3.1 / v1.62) `check_gate_steps_have_exit_criteria`** — for any **`verification_class: false`** step that is a ship/close step OR carries `trust_level: approval-required`, `exit_criteria:` MUST be non-empty. Empty/absent → ERROR (the engine refuses bootstrap + refuses `workflow_complete`). `verification_class: true` steps are exempt (they self-verify via natural output per §5 + Rule 11 carve-out). Closes the empty-criteria escape hatch (Governance Rule 11; cdc1615e). Runtime-enforced in pipeline-runtime.py (v1.62 Lane B).
20. **(NEW v3.2 / v1.64) `check_vc_true_has_verification_command`** — the vc:true completeness check (vc:true parallel to Check 19). For any **`verification_class: true`** step, a **verdict source** MUST exist — one of: `verification_command` (command); `trust_level: approval-required` or a `human:` criterion (human_signoff); or an `aggregate:` criterion (§6a per-criterion methods). None present → **WARN** (ratchets to ERROR later, the Check 19 WARN→ERROR lifecycle — shipped WARN at v1.64 so it cannot red-light a concurrent cycle's validate). A vc:true step's verdict is supposed to BE its natural output; with no source the engine has no mechanism and falls back to agent attestation (the self-attestation hole). **Recognizes all four verdict sources, not command-only** — approval-required gates are human_signoff-verified and correctly need no `verification_command` (the A94 re-scope; the original command-only framing falsely warned human gates). Closes the vc:true self-attestation hole (Rule 11 vc:true branch). Engine: `evaluate_criterion` + `verification_command` (9e7003b1); validator catches a sourceless vc:true step at rebuild (d2b9c8e6.py).

Core checks inherited. (Two additional essential checks ship in pipeline-run.capsule v2.0; see Part 2 of the spec.)

---

## 8. Backward-Compatibility

- v2.6 step WorkflowNodes without `step_owner_role` / `step_verifier_role` / `exit_criteria:` / `depends_on_steps:` continue to validate as v3.0 — those fields are OPTIONAL. Existing pipeline definitions remain valid against v3.0 schema until each retrofits through the setup-new-pipeline.playbook.
- v2.6 `cascade_spec:` field semantics preserved entirely. v3.0 step schema composes alongside; cascade spawn-behavior still fires per v2.6 contract.
- Pipeline-runs activated against v3.0-shaped step entries pin the pipeline version at run-start per Rule 3; runs against v2.6-shaped entries continue to work via fallback semantics in pipeline-run.capsule v2.0 §Backward-Compatibility (auto-defaulted `step_verifier_role: same-as-executor` + empty `exit_criteria:` + `trust_level: auto-with-verification`). **(v3.1 / v1.62) EXCEPTION — gate steps:** the permissive empty-`exit_criteria` fallback applies ONLY to ordinary non-gate steps. For ship/close steps and `trust_level: approval-required` steps, empty/absent `exit_criteria:` resolves to **FAIL** per Governance Rule 11 + Validation Check 19 — there is no permissive fallback at the gate. This is the deliberate closure of the escape hatch identified in cdc1615e (the v2.6 empty-criteria default is exactly what let v1.60/v1.61 ship hollow).

---

## 9. Composes-With

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.
- **[pipeline-run.capsule v2.0 (5a8f3b2c)](pipeline-run.capsule.md)** — the runtime layer. Pipeline-runs execute pipelines; pipeline-runs pin `pipeline_version:` at start. v2.0 provides structured `verification_receipt` enforcement + activation contract + trust gradient gates that operationalize v3.0's per-step rich schema.
- **[entity.capsule (1e9c3f7a)](entity.capsule.md)** — `author:` and `owner:` reference entity UIDs. `step_owner_role` and `step_verifier_role` resolve to entity registry agent-class strings.
- **[project.capsule (34e4cb0b)](project.capsule.md)** — projects may be pipeline-run members; projects no longer reference pipelines directly (v2.2's `active_pipeline:` field removed). **(Rule 10)** activation-root-project authored at step-0 of every pipeline activation.
- **[playbook.capsule (e7b3c509)](playbook.capsule.md)** — related primitive. Pipelines conceptually inherit from playbook; `extends: core` documents non-formal composition.
- **[release-plan.capsule (a3f1e7b2)](release-plan.capsule.md)** — `composes_with`. v1.9.2 step `update-subsystem-canonical-docs` consumes release-plan's `hub_summaries:` field.
- **[release.capsule (b19e8d43)](release.capsule.md)** — v1.9.2 step `update-subsystem-canonical-docs` consumes release entry's derived `subsystems_touched:`.
- **[subsystem-hub.capsule (8a4e21c5)](subsystem-hub.capsule.md)** — v1.9.2 step writes derived `release_history:` rows to each touched hub.
- **[Tropo Work v2 Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md)** — parent spec.
- **[v1.46.0 pipeline-runtime.py design-spec (2b809e0f)](../../vault/files/2b809e0f.md)** — companion design-spec for the v3.0 runtime engine.

### Key Sub-patterns

- **`update-subsystem-canonical-docs` step (v2.4 ACTIVATED).** Dev-pipeline step at WorkflowNode UID [9d4f7e21](../../vault/files/9d4f7e21.md). At step invocation, executor reads release-plan's `capabilities_touched:` + `hub_summaries:`, derives `subsystems_touched:` via 1-hop graph traversal, validates `hub_summaries:` covers each derived hub, writes `release_history:` rows + `subsystem-registry.jsonl` rows + back-writes `subsystems_touched:` to release entry. Frontmatter only — body section auto-writes OUT of scope. Executor module at `.tropo/scripts/dev-pipeline/update-subsystem-canonical-docs.py`.

- **Activation-root-project (v2.2; runtime-enforced at v1.35.0).** Every pipeline activation's step-0 authors a `type: project` vault entry that becomes the graph parent for all downstream artifacts the activation produces. Substrate invariant: *"Everything is a child of the project. Step 0."* Runtime enforcement via [`.tropo/scripts/pipeline-activate.py`](../scripts/pipeline-activate.py).

- **`cascade_spec:` field (v2.6 ACTIVATED) — declarative substrate-generation specification.** When a pipeline carries `cascade_spec:` in its frontmatter, the pipeline-activation runtime reads it at activation-time and generates the declared substrate atomically alongside the activation-root-project.

  **Schema:**

  ```yaml
  cascade_spec:
    generates_project_plan: true        # boolean (required); if true, activation authors a type: project-plan capsule member_of activation-root-project (project-plan.capsule v1.4 governs)
    spawns_workstreams:                 # array (required if cascade_spec present); 0..n entries
      - pipeline_uid: <8-hex>           # required; resolves to type:pipeline AND role:"workstream" AND status:active OR status:locked
        name: "<workstream name>"       # required; human-readable; ≤120 chars
        owner_agent_class: <string>     # required; functional-class agent identifier (no proper-name characters)
        member_of_project_plan: true    # boolean (required if generates_project_plan: true)
    spawns_tasks:                       # optional array (deeper-cascade teach-by-example pattern); honored on workstream-class pipelines
      - title: "<task title>"           # required; ≤160 chars
        owner_agent_class: <string>     # required; functional-class agent
        relative_offset_days: <int>     # required; integer offset from event_date (negative = before; 0 = event day; positive = after)
        depends_on: [<task-title>]      # optional array of prior task titles in same workstream
  ```

  **Validation rules:**
  - *Spec-time* (validator extension; honor-system at v1.35.0; mechanical at v1.36.0+): valid YAML; every `pipeline_uid` resolves to `type:pipeline + role:"workstream" + status:active|locked`; cycle detection (a pipeline's cascade cannot transitively spawn itself); `owner_agent_class` matches functional-class pattern.
  - *Runtime* (pipeline-activate.py; hard-fail): schema-validate before any authoring; resolve targets; cycle-check; abort with non-zero exit on any failure.

  **Atomicity:** all-or-nothing cascade. Roll-back manifest at `<run-folder>/cascade-rollback.jsonl`; on mid-cascade failure, walk manifest in reverse and clean up; no partial-cascade substrate persists.

  **Backward-compatibility:** pipelines without `cascade_spec:` activate without cascade behavior. Existing pipeline-runs unaffected.

  **First instance:** Hello Tropo's event-campaign master pipeline + 6 workstream pipeline templates (v1.35.0 ship).

### History

The v1.0/v2.0/v2.1/v2.2/v2.3/v2.4/v2.5/v2.6 amendment-block prose, the §Conscious Trade-offs section, the §Known Enforcement Gaps table, the §Migration Notes v1.0 → v2.0, the full §Studio — Shop Signage authoring procedure, the Relationship-to-Other-Capsules narrative, the Extension-from-core section, and the full changelog are preserved in the companion [pipeline.history.md (fa811352)](pipeline.history.md) governed by `capsule-history.capsule` (5ec083a3). v3.0 amendment narrative + diff appended to history at v1.46.0 ship.

---

*pipeline capsule definition | v3.0 ACTIVE | history at [pipeline.history.md](pipeline.history.md) | v3.0 body authored 2026-05-20 by Argus A76 per v1.46.0 Replacement-Body Specs (8e5b3c47 v0.5 LOCKED). Prior v1.0–v2.6 locks preserved in history. UID `e4c8a6b2` preserved.*
*"Pipeline is the template. Pipeline-run is the instance. The step is the contract. The receipt is the proof."*
