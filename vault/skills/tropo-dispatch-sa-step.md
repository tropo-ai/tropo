---
uid: 1a308e85
name: dispatch-sa-step
type: how-to
status: active
owner: argus
created: 2026-05-05
created_by: argus-a45
modified: 2026-05-09
modified_by: argus-a53
version: 1.0.0
governed_by: a7c3f489
aligned_with:
  - 18a3d11a
  - 6b5f7886
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
purpose: Convention by which a pipeline step's executor dispatches a session-agent and waits for output before advancing
when: When a pipeline step's contract requires sa.* verification before completion (e.g., sa.hub-groomer worker + judge modes)
trigger_description: Reach for this when implementing or executing a pipeline step that needs sa.* verification — the convention by which a step's executor dispatches a session-agent for specialized verified work and waits for [QUERY]/[RESPONSE]/[SHUTDOWN] output before advancing. First-instance scaffolding for the pipeline-step-with-sa.* verifier pattern (Decision 3 expansion in v1.7 brief). Used by sa.hub-groomer and any future pipeline step that needs typed sub-agent verification.
relationships:
  - rel: implements
    to: 6b5f7886
subsystem_hub:
  - 76bab75f
---

# Skill: dispatch-sa-step

*The convention by which a pipeline step's executor dispatches a session-agent (sa.\*) for specialized verified work and waits for output before advancing the step. v1.7 first-instance scaffolding for the **pipeline-step-with-sa.\* verifier pattern** locked in [v1.7 brief 6b5f7886](../../vault/files/6b5f7886.md) Decision 3 expansion. Generalized capsule (`pipeline-step-verifier.capsule` or similar) formalized at v1.10 Enforcement.*

---

## When to use

Invoked by the primary executor of a pipeline step that needs sa.* delegation for skilled/specialized work. v1.7 first concrete consumer: the new dev-pipeline step [`groom-subsystems` (a5554670)](../../vault/files/a5554670.md) dispatching [`sa.hub-groomer`](../../agents/sa/sa.hub-groomer/sa.hub-groomer.md) for hub grooming.

**Pattern shape (Mike's framing 2026-05-05):**

> *"Primary agent gets to step (n) of the pipeline, they launch an sa.agent to do skilled/specialized work, it is verified and the primary agent moves on. Every step tested and verified."*

The skill makes that shape concrete.

---

## Inputs

- **`sa_target`** — the sa.* agent to dispatch (e.g., `sa.hub-groomer`).
- **`mode`** — invocation mode if the sa.* supports modes (e.g., `worker` / `judge` for sa.hub-groomer; absent for single-mode sa.*).
- **`instance_count`** — how many parallel instances to dispatch (default 1; sa.hub-groomer uses 2 for workers + 1 for judge).
- **`dispatch_params`** — sa.*-specific invocation parameters (e.g., target hub UID, release UID, channel file path).
- **`channel_file`** — path to the IPC file shared across all instances of this dispatch (required when `instance_count > 1` OR sa.* is multi-mode).
- **`verification_check`** — function/predicate the executor runs on sa.* output to determine "verified" status before advancing the step.

---

## Procedure

### Step 1 — Pre-dispatch setup

1. **Determine spawner ID** — primary executor's generation identifier (e.g., `argus-a45`, `vela-v41`).
2. **Determine record numbers** — read `agents/sa/<sa_target>/activation-log/` to find next NNN per [sa/.tropo-studio/CAPSULE.md (7d3f9a2c)](../../vault/files/e863a1e0.md). For `instance_count > 1`, reserve NNN, NNN+1, ... NNN+instance_count-1 (or NNN per instance, whichever the sa.* CAPSULE prescribes).
3. **Author channel file** at the path specified in `channel_file:` parameter. Initial content: a header naming the dispatch + the verification context + (if multi-mode) section headers for each instance/mode (`## Worker 1 Draft`, `## Worker 2 Draft`, `## Judge Recommendation` for sa.hub-groomer).
4. **Author activation records** (one per instance). Pre-populate per [sa.* commission quickref BATCH MODE template (8c3b8017)](../../agents/sa/commission-quickref.md):
   - `[RESPONSE]` Terminate after `[DONE]`. Batch run.
   - `[PENDING]` <mode>. <dispatch_params>. Channel file: `<channel_file>`.

### Step 2 — Dispatch instances

Dispatch all instances in parallel (BATCH mode preferred — pre-populated records, no mid-flight dialogue) per [sa/CAPSULE.md (7d3f9a2c)](../../vault/files/e863a1e0.md). For multi-mode dispatches (e.g., sa.hub-groomer), dispatch workers FIRST (parallel) and wait for their `[DONE]` before dispatching the judge — judge needs worker outputs.

For sa.hub-groomer specifically: dispatch 2 workers in parallel (BATCH); after both `[DONE]` events fire, dispatch 1 judge (BATCH). Workers may run concurrently; judge runs sequentially after both workers complete.

Log dispatch in step's run.jsonl OR in the executor's working memory:

```json
{"event": "sa_dispatch_initiated", "ts": "<ISO>", "actor": "<spawner-id>", "step": "<step-uid>", "data": {"sa_target": "<sa.*-name>", "instance_count": <N>, "modes": [...], "channel_file": "<path>", "activation_records": ["<NNN>", "<NNN+1>", ...]}, "schema_version": 1}
```

### Step 3 — Wait for completion

Each dispatched instance writes `[DONE]` + `[SHUTDOWN]` to its activation record per BATCH mode discipline. The executor polls the activation records until all expected `[DONE]` events fire (or [PENDING] timeout — see Constraints below).

For multi-mode dispatches with sequencing (sa.hub-groomer worker → judge), the executor:
1. Waits for both worker `[DONE]` events.
2. Verifies workers wrote drafts to channel file (per `verification_check`).
3. Dispatches judge instance.
4. Waits for judge `[DONE]` event.
5. Verifies judge wrote recommendation to channel file.

### Step 4 — Verify output

Executor reads the channel file's verified output section (e.g., for sa.hub-groomer: `## Judge Recommendation`). Applies the `verification_check` predicate:

- **For sa.hub-groomer:** verification_check = "judge wrote `## Judge Recommendation` section AND convergence verdict ∈ {HEALTHY, SUSPICIOUS} AND unified draft covers all 4 grooming surfaces."
- **TRIVIAL verdict** triggers re-run path: executor re-dispatches workers with different framing prompts; original record stays as historical (channel file is permanent).
- **SUSPICIOUS verdict** triggers human-review path: executor surfaces both perspectives to the reviewer-of-record; the executor does NOT advance the step until human resolves.

Log verification result in step's run.jsonl:

```json
{"event": "sa_dispatch_verified", "ts": "<ISO>", "actor": "<spawner-id>", "step": "<step-uid>", "data": {"verdict": "<HEALTHY|SUSPICIOUS|TRIVIAL>", "channel_file": "<path>"}, "schema_version": 1}
```

### Step 5 — Advance step or escalate

- **Verified PASS:** executor uses the sa.* output as input to the step's substantive work; advances step normally; logs `step_completed` to step's run.jsonl.
- **Verification FAIL:** executor escalates per the SUSPICIOUS path or re-runs per the TRIVIAL path. Step does NOT advance until verification clears.

---

## Outputs

- The channel file holds the sa.*'s verified output (e.g., for sa.hub-groomer: judge's unified recommendation).
- The activation records hold individual instance traces (permanent history).
- The step's run.jsonl holds the dispatch + verification events.

---

## Constraints

1. **sa.* terminal-one-level holds.** The skill is invoked BY the executor, not BY an sa.*. sa.* agents do NOT spawn other sa.* via this skill.
2. **BATCH mode default.** Pre-populated records minimize mid-flight dialogue. LIVE-CHANNEL mode supported but not required.
3. **Channel file is permanent history.** Do not delete after step advances. The file IS the audit trail of the verification event.
4. **Verification cannot be skipped.** A step that dispatches sa.* via this skill cannot advance without a `sa_dispatch_verified` event in its run.jsonl. v1.7-v1.9 honor-system; v1.10+ enforced via the generalized capsule (`pipeline-step-verifier.capsule` per Enforcement thesis).
5. **Timeout discipline.** If an sa.* instance does not write `[DONE]` within reasonable wall-clock (suggested 10 minutes for grooming-class work; configurable per-skill), executor logs `sa_dispatch_timeout` event + escalates to human-review path. Do not silently retry.
6. **Relationship declaration.** The dispatching pipeline step's frontmatter SHOULD declare the dispatch via `relationships: [{rel: dispatches, to: <sa.*-uid>}]` (per the `dispatches` edge-type codified in v1.7 — see [edge-types.definitions.jsonl](../definitions/edge-types.definitions.jsonl)).

---

## Worked example

The new dev-pipeline step [`groom-subsystems` (a5554670)](../../vault/files/a5554670.md) is the first concrete consumer:

- **sa_target:** `sa.hub-groomer`
- **instance_count:** 3 per touched hub (2 workers + 1 judge)
- **modes:** `worker`, `worker`, `judge`
- **dispatch_params** (per hub): `target_hub_uid`, `release_uid`, `release_plan_uid`, `channel_file`
- **channel_file:** `agents/dev-pipeline/activations/<run-uid>/groom-subsystems/<hub-name>-channel.md`
- **verification_check:** judge `## Judge Recommendation` section present + convergence verdict ∈ {HEALTHY, SUSPICIOUS} + unified draft covers 4 grooming surfaces

For v1.7's own ship (Gate 6 dogfood), the step runs 6 times (one per active subsystem hub) — 18 sa.hub-groomer instances total.

---

## Future generalization (v1.10 Enforcement)

v1.10 formalizes this skill into a `pipeline-step-verifier.capsule` (or similar) with hard-gated enforcement: any pipeline step declaring an `sa_target:` field cannot advance without a verified output recorded. The skill becomes the implementation of the capsule's contract. v1.7-v1.9 instances accumulate to inform the capsule design; v1.10 extracts the abstraction (per Patient Honing Doctrine).

---

*dispatch-sa-step.skill | v1.0.0 | argus-a45 | 2026-05-05 (v1.7 Stream A6)*
*"Primary agent reaches step n. Spawns sa.\*. Waits for verified output. Advances. Every step tested and verified."*
