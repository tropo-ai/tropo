---
uid: fa811352
name: "pipeline-history"
type: capsule-history
governs: e4c8a6b2
governs_path: .tropo/capsules/pipeline.capsule.md
extracted_at: 2026-05-11
extracted_by: argus-a56
extracted_in_cycle: "v1.19.0 — Convergence Phase 1"
extracted_in_release: pending-v1.19.0
schema_version: 2
governed_by: 5ec083a3
extraction_scope: argo-private
member_of:
  - "8dd772a0"
tags: [capsule-history, extracted-from-pipeline-capsule, v1.19.0-stream-c]
---

# pipeline — Capsule History

*History extracted from pipeline.capsule v2.4 → v2.5 body refactor (v1.19.0 Stream C; 2026-05-11). Active capsule preserves: WorkflowNode model (Pipeline/Stage/Step as fractal composition), Required+Optional Frontmatter (including `requires_confirmation:` v2.1 + `update-subsystem-canonical-docs` v2.4), 6 Required Body Sections (Purpose/Structure/Nodes/Flow Rules/Cold-Boot Walk-Through/Known Enforcement Gaps), State Machine, 8 Governance Rules + Rule 9 (requires_confirmation) + Rule 10 (activation-root-project), 16 Validation Checks. This file preserves: v1.0/v2.0/v2.1/v2.2/v2.3/v2.4 amendment-block prose, Conscious Trade-offs (3 entries), Known Enforcement Gaps table, Migration Notes v1.0→v2.0, §Studio Shop Signage with v2.4 sub-pattern detail + activation-root-project sub-pattern + worked diff, Relationship-to-Other-Capsules, Extension from core, full changelog.*

---

## Amendment Blocks (extracted)

### v3.0 (2026-05-20, Argus A76; ACTIVE — v1.46.0 Replacement-Body Spec)

v1.46.0 amendment per [Replacement-Body Specs (8e5b3c47)](../../vault/files/8e5b3c47.md) v0.5 LOCKED + [pipeline-runtime.py design-spec (2b809e0f)](../../vault/files/2b809e0f.md) v0.2 LOCKED. Substantial additive amendment introducing per-step rich schema + verifier pattern + exit-criteria DSL. All v2.6 schema preserved as OPTIONAL — pre-v3.0 step entries continue to validate.

**Authoring context:** v1.46.0 is the cycle Mike-A74 named as the structural fix for the cardboard-muffin pattern (7 cycles v1.39 → v1.45 shipping memory-resident discipline; v1.46.0 builds substrate-enforced state machine). pipeline.capsule v3.0 + pipeline-run.capsule v2.0 are the paired schema additions; companion pipeline-runtime.py engine is the canonical executor. Mike-A75 walked + locked the spec across 1M-token session 2026-05-20; A76 authored the canonical body 2026-05-20 against the locked spec.

**Five amendment areas:**

1. **Per-step rich schema** added (OPTIONAL frontmatter on step WorkflowNode entries): `step_owner_role` (which agent class executes), `step_verifier_role` (default `same-as-executor`), `verification_class` (boolean; bypasses structured receipt for inherently-verifying work), `depends_on_steps` (DAG edges; UID array), `exit_criteria` (machine-checkable assertion strings; DSL), `trust_level` (4-value enum), `compensation_step_id` (saga single-step), `instructions_ref` (path or UID), `retry_policy` (object), `timeout_hours` (int).
2. **Pipeline-level defaults** added (root pipeline WorkflowNode): `default_trust_gradient`, `default_retry_policy`, `default_timeout_hours`.
3. **Same-as-executor verifier pattern** documented (Mike-A75 lock: agents don't tend to lie when they have to sign off in a record). Default verifier is the executor; structured `verification_receipt` event format is the forcing function. Explicit override available via `step_verifier_role: <other-class>` for high-stakes steps.
4. **Verification-class step pattern** documented. Steps whose work IS verification (build / fetch / validator) declare `verification_class: true` and bypass structured-receipt overhead; step's natural output is the verification.
5. **Exit-criteria DSL** minimum-viable shipped. 5 assertion shapes: `<uid-ref>.exists`, `<uid-ref>.<field> == <value>`, `<uid-ref>.<field> contains <value>`, `<uid-ref>.body matches <pattern>`, `file:<path>.exists`. UID references resolve via pipeline-run context. Quantifiers + composition deferred to v3.1+.

**Validation Checks count: 16 → 18** — two new ERROR-severity checks added:
- `check_step_verifier_distinct_from_owner_when_overridden` — explicit `step_verifier_role:` must name a different class than `step_owner_role:` (enforces override discipline)
- `check_step_depends_on_acyclic` — DAG invariant; `depends_on_steps:` cycles are validation errors

**Frontmatter cleanup:** `v2_6_anchor:` field dropped from capsule frontmatter per Mike-A75 "no history in capsules" lock 2026-05-20. v2.6 anchor description moved to this history file as the v2.6 amendment block (below). v3.0's amendment context lives in frontmatter `v3_0_anchor:` as a single-line pointer (provenance, not changelog).

**Composes-with addition:** [pipeline-runtime.py design-spec (2b809e0f)](../../vault/files/2b809e0f.md) added to `aligned_with:`. Companion design-spec for the v3.0 runtime engine that operationalizes the per-step rich schema at runtime via pipeline-run.capsule v2.0.

**Backward-compatibility:** v2.6 step WorkflowNodes without per-step rich schema fields continue to validate as v3.0. Pipeline-runs against v2.6-shaped step entries auto-default: `step_verifier_role: same-as-executor`, empty `exit_criteria:` array, `trust_level: auto-with-verification`. Activation contract event captures the defaults explicitly so the runtime is self-describing.

**Migration impact on existing pipelines:** dev-pipeline retrofits first under setup-new-pipeline.playbook (MUST-SHIP #6 in v1.46.0 cycle brief); web-pipeline + app-pipeline at v1.47.0; kb-pipeline + publish-pipeline at v1.48.0.

### v2.6 (2026-05-16, Argus A67; ACTIVE — v1.35.0 cascade pattern)

v1.35.0 amendment per [design spec d2f8c194](../../vault/files/d2f8c194.md) (LOCKED Mike-A67 2026-05-16 stance-i + Q24α + Q25α + Q26α). Two amendments: (1) docs add `"workstream"` to documented `role:` value examples; (2) schema add optional `cascade_spec:` frontmatter field declaring substrate-generation behavior at pipeline activation. Cascade behavior implemented by new `.tropo/scripts/pipeline-activate.py` (NEW substrate at v1.35.0; §Rule 10 v2.2 runtime enforcement pulled in-scope per stance-i). Backward-compatible: pipelines without `cascade_spec:` behave exactly as v2.5; existing pipeline-runs unaffected. Status flipped locked → active to permit minor refinements through v1.35.5; never re-locked (continued active state at v3.0 ship 2026-05-20).

### v2.5 (2026-05-11, Argus A56; ACTIVE — v1.19.0 Stream C body refactor)

v1.19.0 Stream C body refactor applying the 5-section pedagogy pattern (Purpose / Schema / State Machine / Validation Rules / Composes-With + History pointer). Amendment-block prose, Conscious Trade-offs section, Known Enforcement Gaps table, Migration Notes, Studio Shop Signage, Relationship-to-Other-Capsules, Extension-from-core, and full changelog extracted from capsule body to this history file. Capsule body shrinks; pedagogy structure standardizes. UID `e4c8a6b2` preserved. Sister refactor at pipeline-run.capsule v1.4 same cycle.

### v2.4 (2026-05-07, Argus A49; LOCKED post-Stream B4)

v1.9.2 Stream A3 amendment per [v1.9.2 brief e7a3b591](../../vault/files/e7a3b591.md). Additive non-breaking — signage + sub-pattern activation. Activates v2.3 pre-doc §Sub-pattern entry for `update-subsystem-canonical-docs` (formerly forthcoming-v1.9; now ACTIVATED v1.9.2). Two scope adjustments per Q7 walk reframe (Mike-A49 2026-05-06 agent-canonical-vs-human-canonical curve ball):

- **Frontmatter only.** v2.3 pre-doc said: "(c) optionally invokes `sa.hub-groomer` swarm to author recommended `## Current State` body updates." v1.9.2 DROPS sub-clause (c) — body sections are human documentation; not the executor's scope. Carry-forward note [4b7a9d3f](../../vault/files/4b7a9d3f.md) files broader audience-split thesis for v1.10+.
- **Per-hub summary text comes from release-plan, not from sa.hub-groomer.** v2.3 pre-doc was ambiguous on prose source. v1.9.2 locks: prose comes from release-plan's NEW `hub_summaries:` field (per release-plan.capsule v1.3 Stream A2). Author writes per-hub summaries at release-plan lock time; executor reads at ship.

v2.4 also documents the NEW step's vault entry at [9d4f7e21](../../vault/files/9d4f7e21.md) (Stream A4). The dev-pipeline INSTANCE (cd1fcd25) is amended at Stream A4 to insert the new step between `author-arch-spec-artifacts` and `generate-release-notes`.

### v2.3 (2026-05-05, Argus A46; LOCKED — v1.8 Stream C pre-doc)

Additive non-breaking signage-only amendment per [v1.8 brief fd2d9e77](../../vault/files/fd2d9e77.md). §Studio §Sub-patterns gained entry pre-documenting v1.9's forthcoming `update-subsystem-canonical-docs` step. v1.9.2 activates the pre-doc with adjusted scope per Q7.

### v2.2 (2026-05-04, Argus A44; LOCKED)

v1.6 Stream A.3 amendment per [v1.6 design brief b6f1e9c4](../../vault/files/b6f1e9c4.md) Decision 3. Additive non-breaking — signage + rule documentation. Documents the **activation-root-project pattern** as mandatory step-0 sub-action of every pipeline activation: when a pipeline activates, step-0 (accept-work-item) must author a `type: project` ledger entry that becomes the graph parent for all downstream artifacts produced by that activation. Per Mike directive 2026-05-04: *"Everything is a child of the project. Step 0."* Substrate invariant locked. Sister amendment owed at pipeline-run.capsule v1.2 (deferred to v1.7+). v1.6 dev-pipeline activation #2 honors via documented protocol.

### v2.1 (2026-05-03, Argus A43; LOCKED)

v1.4.4 Stream B minimum amendment per [dev-pipeline + vault inbox primitive e1c47a9f](../../vault/files/e1c47a9f.md). Additive non-breaking. Single change: adds `requires_confirmation: boolean` optional field on WorkflowNode (default `false`) — when `true`, pipeline-run executor pauses on step entry awaiting human confirmation. Honored by [pipeline-run.capsule v1.1](pipeline-run.capsule.md). v2.0 existing KEGs (branching, condition language, nesting-depth mechanical, migration protocol) deferred to v2.2.

### v2.0 (2026-04-23, Argus A32)

**BREAKING rewrite** per [Tropo Work v2 Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md) §2.4. Replaces v1.0's flat `stages:` + `positions:` model with recursive WorkflowNode model. Pipeline becomes its own top-level type, not a playbook subtype. GATE positions, flat position arrays, `forward_only: true` literal, `artifact_types:` per-stage map, `owner_per_position:` map, and `gate_rules:` per-stage all removed — functions absorbed into WorkflowNode recursive structure and pipeline-run mechanics. Industry precedent: Airflow DAGs, BPMN 2.0 subprocess nesting, Camunda WorkflowNodes. UID `e4c8a6b2` preserved per governance Rule 2.

**Why the rewrite:** v1.0 was the v1.3 Typed Pipeline Architecture's declarative half. Post-v1.3.1 review + Mike's Edison directive (2026-04-23) locked that the "project walks pipeline" abstraction was the wrong seam. The v2 insight: pipelines are playbooks with workflow shape; pipeline-runs are playbook-runs on a bundle of members.

### v1.0 (2026-04-21, Argus A30; LOCKED — superseded by v2.0)

Initial LOCKED. D7 of v1.3 Typed Pipeline Capsule Ship. Flat stages/positions model. Three-instrument: Argus build + sa.cold-boot 049. SUPERSEDED by v2.0 (2026-04-23) per Mike's Edison directive.

---

## Conscious Trade-offs (extracted)

### Linear-default schema with array-supporting `next_steps:`

Rather than strict linear `next_step: <uid>` or fully-rich DAG schema with parallel/conditional semantics, v2.0 ships `next_steps: [...]` with length-1 default. Schema supports branching now; behavior ships incrementally. Per sa.skeptic P1-3 resolution: *"the cost of the richer field now is trivial; the cost of breaking linear-only assumptions later is a schema migration."*

### No separate GATE type

v1.0 had GATE positions as a distinct role. v2.0 absorbs GATE into regular WorkflowNodes — a GATE is just a step whose pipeline-run behavior pauses for human intervention (via `restart_strategy: manual` on the run, or explicit pause on the step). Simpler schema; GATE semantics live in the run's behavior, not the template's role vocabulary.

### `extends: core` instead of `extends: playbook`

Inherited from v1.0's OD2 decision (Mike 2026-04-21). Pipelines compose with the playbook primitive conceptually but don't formalize the capsule-inheritance chain beyond core. Keeps the kernel simple. If cross-capsule inheritance patterns emerge in v1.5+, revisit.

---

## Known Enforcement Gaps (extracted)

| Gap | What closes it | Target release | Owner |
|---|---|---|---|
| `next_steps:` length >1 branching behavior not fully specified (v2.0 supports "first condition true") | Richer branching semantics: parallel fan-out, condition-gated fan-in | v2.2 (deferred from v2.1 per v1.4.4 minimum-scope decision) | argus |
| Nesting depth bound is honor-system | Validator enforces soft-cap at 3 with warning-at-4 | v2.2 (deferred from v2.1) | argus |
| `condition:` expression language not specified | Condition DSL (likely simple expression language over pipeline-run state) | v2.2 (deferred from v2.1) | argus |
| Migration Protocol section not required at v2.0 but often needed on supersession | Require §Migration Protocol when `supersedes:` is set | v2.2 (deferred from v2.1) | argus |
| Loop / iteration semantics not specified | Loop-step WorkflowNode subtype OR loop modifier on existing step | v2.2+ | argus |

---

## Migration Notes — v1.0 → v2.0 (extracted)

v1.0 pipelines use flat `stages:` + `positions:` + `artifact_types:` + `gate_rules:`. v2.0 reorganizes into nested WorkflowNodes. Migration script (Stream 1 D1.3) handles:

1. **For each v1.0 pipeline:** author a v2.0 root WorkflowNode with `name:` = v1.0 pipeline's name, `domain:` = v1.0 pipeline's domain, `version: 2.0.0`.
2. **For each v1.0 stage:** author a v2.0 composite WorkflowNode with `name:` = stage name, `role: "stage"`, `children:` = UIDs of position WorkflowNodes.
3. **For each v1.0 position in a stage:** author a v2.0 leaf WorkflowNode with `name:` = position name, `role:` = v1.0 position role (inbox/accepted/active/GATE/archived), `next_steps:` per v1.0 stages array order.
4. **v1.0 `artifact_types` map** deprecated — artifact types live on work-item capsules; pipeline no longer declares them per-stage.
5. **v1.0 `gate_rules`** deprecated — GATE behavior lives in pipeline-run `restart_strategy:` + step-level pause semantics.

The `tropo-work-pipeline` v1.0 instance (if it exists as a vault entry) will be the primary migration target.

---

## Studio — Shop Signage (extracted; includes v2.4 sub-pattern detail)

*Preserved per Mike-A55 directive: capsules are agent-read, not human-read.*

### Tools available

- `python3 .tropo/scripts/tropo-validate.py` — runs pipeline.capsule's 16 validation checks
- `python3 .tropo/scripts/rebuild-vault.py --apply` — catches broken `children:` / `next_steps:` references
- Migration script (Stream 1 D1.3) — carries v1.0 flat model to v2.0 recursive structure

### Skills

- `create-pipeline.skill.md` *(forthcoming v1.5)* — authoring 1 root + N child vault entries per pipeline is heavy without skill; sa.skeptic 011 flagged as v1.5 priority
- Pipeline-migration script (v1.4 Stream 1 D1.3) for v1.0 → v2.0 carryover

### Procedures

- Pipeline-run execution protocol — defined in [pipeline-run.capsule §Member Processing](pipeline-run.capsule.md)
- Pipeline-supersession protocol — via `supersedes:` / `superseded_by:` bidirectional pairs per Rule 8
- Three-instrument verification at pipeline lock — sa.arch-specs + sa.skeptic + sa.cold-boot

### Sub-patterns

#### v2.4 ACTIVATED — `update-subsystem-canonical-docs` step

ACTIVATED 2026-05-07 by [v1.9.2 design brief e7a3b591](../../vault/files/e7a3b591.md). NEW dev-pipeline step at WorkflowNode UID [`9d4f7e21`](../../vault/files/9d4f7e21.md). Inserted between `author-arch-spec-artifacts` ([24f16afc](../../vault/files/24f16afc.md)) and `generate-release-notes` ([804e339e](../../vault/files/804e339e.md)) in the dev-pipeline instance ([cd1fcd25](../../vault/files/cd1fcd25.md)). Closes the manual-substitute pattern that ran across v1.8 + v1.9.0 + v1.9.1.

**Behavior:** at step invocation, executor:
- Reads release-plan's `capabilities_touched:` and `hub_summaries:` (NEW v1.3 field per release-plan.capsule v1.3 Stream A2)
- Derives `subsystems_touched:` via 1-hop `member_of:` graph traversal over `capabilities_touched:` (per release.capsule v3.4 Rule 12)
- Validates `hub_summaries:` covers each derived subsystem hub
- For each touched-subsystem hub:
  - (a) appends `release_history:` row with `derived_from: capabilities_touched` + `summary:` from `hub_summaries[hub_uid]`
  - (b) bumps `last_release_reflected:`
  - (c) writes a corresponding `subsystem-registry.jsonl` row
  - (d) writes derived `subsystems_touched:` back to the release entry

**Frontmatter only — body sections OUT of scope** per v1.9.2 Q7 walk reframe (carry-forward note [4b7a9d3f](../../vault/files/4b7a9d3f.md) for v1.10+).

**Executor module:** `.tropo/scripts/dev-pipeline/update-subsystem-canonical-docs.py` (permanent location; NOT per-cycle scaffold).

**Failure modes:** missing `hub_summaries:` for derived hub (FAIL); hub UID resolves to non-hub (FAIL); registry write conflict (FAIL); vault index inconsistency (FAIL). On any FAIL, pipeline halts; no atomic-triangle commit; agent reviews + re-fires.

**Honor-system at v1.9.2-v1.9.x; v1.10 promotes structural-consistency check to ERROR.**

#### v2.2 — Activation-root-project

Pattern for structural artifact authored at every pipeline activation's step-0. When a pipeline activates against a work-item (e.g., a design brief), step-0 (accept-work-item) authors a new `type: project` ledger entry that becomes the **graph parent** for everything that activation produces: the input work-item gets `member_of:` updated to include the activation root; all downstream artifacts (release plan, sub-agent records, build entry, release entry) are authored with `member_of: [<activation-root-uid>]` directly. Per Mike directive 2026-05-04: *"Everything is a child of the project. Step 0."*

The activation root project itself is `member_of: [<pipeline-uid>]` so the graph composes upward — activation root's parent is the pipeline; the pipeline's parent (post-v1.6) is `tropo-work` (b8e5f3a2). Result: a stranger walking the graph from `tropo-work` down can reconstruct EVERYTHING produced by every activation.

**First instance in production:** activation root project [3a9d6c5e](../../vault/files/3a9d6c5e.md) for v1.6 dev-pipeline run [c4f7e2a1](../../agents/dev-pipeline/activations/c4f7e2a1/run.jsonl).

**v1.5 historical gap:** v1.5 (run [7c0402b8](../../agents/dev-pipeline/activations/7c0402b8/run.jsonl)) was the FIRST dev-pipeline activation in Tropo history — preceded the activation-root-project pattern. v1.5's outputs are direct children of dev-pipeline (cd1fcd25), not under an activation-root-project node. Per lineage-in-graph principle (v1.6 brief b6f1e9c4 Decision 5), v1.5 entries stay as-is — backfilling would pretend the pattern existed before it did. The asymmetry IS the historical record.

### Pitfalls

- Authoring inline children (children-as-objects) instead of separate vault entries → Rule 2 violation
- Nesting past depth 3 without `## Design Rationale` → warning at v2.0/v2.1, validator-reject at v2.2 (deferred from v2.1)
- Forgetting `version:` bump on structural edits → breaks pipeline-run version-pin invariant
- Using v1.0 `stages:` + `positions:` frontmatter → deprecated; v2.0+ validator rejects
- Authoring GATE as a separate type → v2.0 absorbs GATE into regular WorkflowNodes
- Over-claiming "any depth" composition → depth bounded to 3 by Rule 5
- **(v2.1)** Setting `requires_confirmation: true` on composite stage (not leaf step) → field meaningful only on leaf steps; presence on stages is honor-system ignored by executor
- **(v2.1)** Confusing `requires_confirmation:` with `restart_strategy: manual` → former pauses on step ENTRY (before work, awaiting human approval); latter pauses on step FAILURE (after work, awaiting human intervention)

### Worked example — v2.0 → v2.1 amendment diff (confirmation-gated leaf step)

```diff
 ---
 uid: 180e9108
 type: pipeline
 subtype: workflow-node
 name: "Generate Release Plan"
-version: "2.0.0"
+version: "2.1.0"             # bump on structural edit per Rule 3
 author: <argus-uid>
 children: []                  # leaf step
 next_steps: [<next-step-uid>]
 state: active
 status: active
+requires_confirmation: true   # v2.1 — pause on step ENTRY for human approval
 ---
```

**Resulting executor behavior** (per [pipeline-run.capsule v1.1 §Member Processing Step 1 Confirmation gate check](pipeline-run.capsule.md)): on entering this step, executor transitions run `status: active → paused`, appends `pause_started` event with `data.reason: "human-confirmation-required"`, halts. Authorized confirmer reviews, appends `pause_resumed` event with `data.confirmation_granted_by: <confirmer-uid>`, transitions back to active. Executor proceeds to step work.

### Worked examples

- *(forthcoming v1.5+ — `create-pipeline.skill.md` will generate template pipeline trees)*
- Historical: v1.0 `tropo-work-pipeline` pre-migration; post-migration is v2.0 root + children → renamed to `legacy-work-pipeline` at v1.6 + reparented under `tropo-work` for lineage-in-graph
- **Activation-root-project: v1.6 run c4f7e2a1** — first instance of v2.2's pattern. Project [3a9d6c5e](../../vault/files/3a9d6c5e.md) authored at step-0; `member_of: [cd1fcd25]`; v1.6 brief [b6f1e9c4](../../vault/files/b6f1e9c4.md) updated `member_of: [cd1fcd25, 3a9d6c5e]` per substrate invariant.

### Go next

- Instance executing a pipeline → [pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)
- Members processed → [task.capsule (3289712a)](task.capsule.md) or [project.capsule (34e4cb0b)](project.capsule.md)
- Pipeline authoring context → this capsule's §Architecture + `create-pipeline.skill.md` (forthcoming)
- Author + owner context → [entity.capsule (1e9c3f7a)](entity.capsule.md)

---

## Relationship to Other Capsules — Narrative (extracted)

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.
- **[pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)** — runtime layer. Pipeline-runs execute pipelines; pipeline-runs pin `pipeline_version:` at start.
- **[entity.capsule (1e9c3f7a)](entity.capsule.md)** — `author:` and `owner:` reference entity UIDs.
- **[project.capsule (34e4cb0b)](project.capsule.md)** — projects may be pipeline-run members; projects no longer reference pipelines directly (v2.2's `active_pipeline:` field removed).
- **[playbook.capsule (e7b3c509)](playbook.capsule.md)** — related primitive. Pipelines conceptually inherit from playbook; `extends: core` documents non-formal composition.
- **[Tropo Work v2 Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md)** — parent spec.

---

## Extension from core (extracted)

pipeline.capsule v2.0 extends core: **uses `status:` for workflow-lifecycle** (draft/active/locked/archived per core's status-machine convention); **adds `state:` for visibility** (active/archived) separate from status; **`name:` field** ≤120 chars specialized for pipeline naming (core: `title:` ≤100). These extensions are honest typed-capsule specializations.

---

## Changelog (full lineage)

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-04-21 | Initial LOCKED. D7 of v1.3 Typed Pipeline Capsule Ship. Flat stages/positions model. Three-instrument: Argus build + sa.cold-boot 049. **SUPERSEDED by v2.0** per Mike's Edison directive. | argus-a30 |
| 2.0 | 2026-04-23 | BREAKING: v2 substrate compliance. Replaces flat model with recursive WorkflowNode model. Pipeline becomes its own top-level type. Children are separate ledger entries referenced by UID. `next_steps:` array (length-1 default, array-supported for v2.1 branching). GATE/forward_only/artifact_types/gate_rules removed. Soft-cap nesting at depth 3. UID preserved. | argus-a32 |
| 2.1 | 2026-05-03 | LOCKED — v1.4.4 Stream B minimum amendment. Additive non-breaking. Adds `requires_confirmation: boolean` on WorkflowNode (default false) — pause on step ENTRY for human approval. Distinct from `restart_strategy: manual` (step FAILURE pause). Validation Check 16 added. v2.0 KEGs (branching, condition language, nesting-bound, migration protocol) deferred to v2.2. | argus-a43 |
| 2.2 | 2026-05-04 | Activation-root-project pattern documented as substrate invariant. Additive non-breaking — signage + rule documentation. §Studio Sub-patterns block documents activation-root-project sub-pattern: every pipeline activation's step-0 must author a `type: project` ledger entry as graph parent for all downstream artifacts. §Rules-at-a-glance gains Rule 10. v1.5 historical-gap documented (lineage-in-graph honored). Per Mike directive 2026-05-04. Sister amendment at pipeline-run.capsule v1.2 (deferred to v1.7+). | argus-a44 |
| 2.3 | 2026-05-05 | v1.8 Stream C pre-doc for v1.9 step-7 contract. Additive non-breaking signage-only. §Studio §Sub-patterns gains entry pre-documenting v1.9's forthcoming `update-subsystem-canonical-docs` step. v1.9.2 activates with adjusted scope per Q7. | argus-a46 |
| 2.4 | 2026-05-07 | LOCKED — v1.9.2 Stream A3 amendment. Additive non-breaking — signage + sub-pattern activation. Activates v2.3 pre-doc §Sub-pattern entry for `update-subsystem-canonical-docs` (now ACTIVATED with WorkflowNode UID 9d4f7e21). Two scope adjustments per Q7 walk reframe: (1) frontmatter only — body section auto-writes DROPPED; (2) per-hub summary text comes from release-plan's NEW `hub_summaries:` field, not from sa.hub-groomer. dev-pipeline INSTANCE (cd1fcd25) amended at Stream A4 to insert new step. | argus-a49 |
| 2.5 | 2026-05-11 | **v1.19.0 Stream C — Capsule Pedagogy Completion.** Body refactor to 5-section pedagogy pattern per Mike-A55 *"capsules are agent-read, not human-read"* directive. Active body reduced from 411 → ~270 lines (~34% reduction; moderated by substantial WorkflowNode model architecture + Sub-patterns activation detail that must remain in active body). Extracted to history: v1.0-v2.4 amendment-block prose, Conscious Trade-offs (3 entries), Known Enforcement Gaps table, Migration Notes v1.0→v2.0, §Studio quick-ref with full sub-pattern detail (v2.4 update-subsystem-canonical-docs + v2.2 activation-root-project), Relationship-to-Other-Capsules narrative, Extension from core, full changelog. **No schema changes.** UID `e4c8a6b2` preserved. | argus-a56 |

---

## Provenance

- **Extracted at:** 2026-05-11
- **Extracted by:** argus-a56
- **Active capsule version at extraction:** v2.4 (411 lines)
- **Active capsule version after extraction:** v2.5 (~270 lines; ~34% reduction)

---

*pipeline capsule history | UID fa811352 | v1.19.0 Stream C extraction 2026-05-11 by Argus A56 | Bidirectional pair: governs e4c8a6b2*
