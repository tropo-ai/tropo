---
uid: ee42c7c8
name: "loop-run"
type: capsule-definition
extends: core
version: "1.0"
tier: vault
author: argus
created: 2026-06-14
created_by: argus-a112
modified: 2026-06-14
modified_by: argus-a114
status: locked
locked_by: mike-maziarz
locked_at: 2026-06-14
enforced_enums:
  status: [active, paused, complete, killed, cancelled]
meta_status_rollup:
  in-progress: [active, paused]
  done: [complete, killed, cancelled]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
modeled_on: 5a8f3b2c   # pipeline-run.capsule — structural template; loop-run reuses its run.jsonl + verification_receipt machinery
realizes_dev_spec: 9da979b2
composes_with:
  - ee814120   # core.capsule
  - 1248583d   # loop.capsule — the template type loop-runs execute
  - 5a8f3b2c   # pipeline-run.capsule — structural sibling (reuses verification_receipt, OTel, run-folder files)
tags: [capsule-definition, loop-run, instance-tracking, iterations, brakes, brake-tripped, bounded-verification, v1.71-s1]
---

# loop-run — Capsule Definition v1.0

## 1. Intent

A loop-run is a single execution instance of a [loop (1248583d)](loop.capsule.md) — the agent-decided-iteration toward a frozen goal, bounded by brakes. It pins the loop version at start, records each **iteration** as a `run.jsonl` event, and terminates when the verifier confirms the goal (`complete`) OR a brake trips (`killed`) OR an operator cancels (`cancelled`). The loop is the template; the loop-run is the instance — the Airflow DAG/DAG-Run separation, rendered for loops.

A loop-run is the **structural sibling of [pipeline-run (5a8f3b2c)](pipeline-run.capsule.md)** and REUSES its machinery: the run-folder files (`definition.md` / `context.md` / `thread.md` / `run.jsonl` / `run.state.json` / `artifacts/`), the structured `verification_receipt` event, the OTel GenAI attributes, and the append-only discipline. The differences are loop-specific: a loop records **iterations** (data-dependent, agent-decided) rather than fixed steps; it carries **brake-state**; it can be **killed** by a brake mid-run; and its verifier **loops back** (fail → another iteration) instead of advancing a DAG.

**The load-bearing honesty (dev-spec §Q1): the brake-state recorded here is COOPERATIVE/legibility ONLY — never the enforcement input.** The agent self-reports its iteration count + spend into the loop-run; the *enforcers* (the metering gateway for spend; the launchd watchdog reading the file's `ctime` + harness OTEL for clock/iterations) read **ground-truth the agent cannot forge**. Forging the loop-run counters changes nothing the enforcers read; the validator audits the over-run after the fact.

---

## 2. Schema

### Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `uid` | 8-hex | Per core. |
| `type` | literal | `loop-run`. |
| `name` | string | ≤120 chars; human-readable. |
| `loop` | UID | The loop definition this run executes. Resolves to `type: loop`. |
| `loop_version` | semver | **Pinned at run-start.** Editing the loop after start does NOT affect this run. |
| `status` | enum | `active` / `paused` / `complete` / `killed` / `cancelled`. See §State Machine. |
| `state` | enum | `active` / `archived`. |
| `owner` | UID | The entity that invoked the run. |
| `principal` | UID | The signing entity (the loop's policy executor for an agentic loop; a human for high-consequence). |
| `started_at` | ISO date | When the run began (= the `ctime` ground-truth anchor for the wall-clock brake). |
| `run_folder` | path | `argo-os/vault/loop-runs/<loop-name>-<run-uid>-<date>/`. The brake-counter file the watchdog/gateway are configured against. |

### Cooperative brake-state (legibility ONLY — NOT the enforcement input)

Written to `run.state.json` + as `iteration_completed` event data. The agent's self-report; the enforcers read ground-truth (gateway / `ctime` / OTEL).

| Field | Meaning |
|---|---|
| `iteration_count` | Agent's reported iteration number. |
| `budget_spent_usd_reported` | Agent's reported spend (cross-checked against OTEL ground-truth by the watchdog). |
| `last_progress_marker` | A hash/uid of the last governed-state change (drives no-progress detection — cross-checked against vault mtime ground-truth). |
| `last_progress_at` | When the last progress marker advanced. |

### Required run-folder files

Same set as [pipeline-run §Required Files](pipeline-run.capsule.md): `definition.md` · `context.md` · `thread.md` · `run.jsonl` · `run.state.json` · `artifacts/`. Seed `run.jsonl` with `run_created` then `loop_contract_locked`.

### run.jsonl Event Schema

One JSON object per line, append-only (per pipeline-run §run.jsonl). Loop-specific event types:

| Event | Purpose | Required data |
|---|---|---|
| `run_created` | Instance created. | owner, loop, loop_version |
| `loop_contract_locked` | The immutable contract at start (the loop's goal/verifier/brakes/policy pinned). | goal (frozen exit_criteria + authored_by), verifier, brakes, policy, consequence |
| `iteration_started` | One per iteration. | iteration_n, decision (the agent's chosen next action toward the goal) |
| `iteration_completed` | Iteration done. | iteration_n, action_taken, artifact_links, cooperative brake-state snapshot |
| `verification_receipt` | The verifier checks the GOAL after an iteration (REUSES [pipeline-run §verification_receipt](pipeline-run.capsule.md) structured format). `verdict: pass` ⇒ goal met ⇒ `complete`; `verdict: fail` ⇒ loop back (another iteration). | verdict, per_criterion (each goal exit_criterion), verifier_role_resolved |
| `brake_tripped` | **(NEW)** Written by the watchdog/gateway (NOT the agent) when a GROUND-TRUTH brake trips. Terminal → `killed`. | brake (max_iterations\|max_budget_usd\|no_progress\|max_wall_clock\|tool_timeout), ground_truth_value, enforcer (gateway\|watchdog), source (ctime\|OTEL\|gateway-429) |
| `goal_met` | The verifier's pass on the full goal. → `complete`. | final_verification_receipt_ref |
| `workflow_complete` | Closure. | terminal_state (complete\|killed\|cancelled) |

OTel GenAI attributes (`gen_ai.usage.*` etc.) per [pipeline-run §OTel](pipeline-run.capsule.md) — and the `claude_code.cost.usage` / `token.usage` metrics are the watchdog's independent spend ground-truth.

---

## 3. State Machine

```
active ⇌ paused → complete  (verifier confirms the goal)
              ↘ killed     (a brake tripped — ground-truth enforced; terminal)
              ↘ cancelled  (operator; terminal)
                  → (grace) → archived
```

| Status | Meaning |
|---|---|
| `active` | Iterating. Policy advances iterations; the verifier checks the goal each loop. |
| `paused` | Human intervention point (trust-gate / explicit). |
| `complete` | The verifier confirmed the frozen goal. The success terminal. |
| `killed` | **(NEW)** A brake tripped before the goal — a safety stop, ground-truth-enforced (a `brake_tripped` event names which brake + the enforcer). This is the bounded-verification safety net firing: a loop that won't converge is stopped, not left to burn. |
| `cancelled` | Operator-cancelled mid-flight. |

**Valid transitions:** `active → paused` (trust-gate/explicit) · `paused → active` (resume) · `active → complete` (`goal_met` + `verification_receipt: pass` on the full goal) · `active → killed` (any `brake_tripped` event) · `active|paused → cancelled` (operator) · terminal → `archived` (grace).

**The `killed` distinction matters.** `complete` = the goal was achieved. `killed` = a brake stopped the run first. Conflating them would hide convergence failures behind a green board — the same hollow-cascade class pipeline.capsule Rule 11 closes for pipelines. A `killed` loop-run renders as a STOPPED verdict, not success.

---

## 4. Validation Rules

### Governance Rules (in addition to core)

1. **Loop-version pin is immutable** (pipeline-run Rule 1, for loops).
2. **`run.jsonl` is append-only; `run.state.json` overwrites at iteration boundary** (pipeline-run Rule 3).
3. **The brake-state in this entry is cooperative/legibility — never the enforcement input.** Enforcement reads ground-truth (gateway 429 / `ctime` / OTEL). A `brake_tripped` event is authored by the enforcer (watchdog/gateway), not the policy agent (Rule 7 analog: the run observes; the enforcer enforces).
4. **A loop-run does not start without a locked contract** — `loop_contract_locked` (carrying a non-empty `brakes`, a frozen `goal` with a non-executor `authored_by`, and a `verifier`) MUST be the second event. Fail-closed (loop.capsule Rule 2; engine-enforced).
5. **`workflow_complete` with `terminal_state: complete` requires a `goal_met` + passing `verification_receipt` on the full goal.** A loop cannot reach `complete` on iterations alone — the goal must verify. (The loop analog of pipeline-run Rule 8 / assert_all_steps_verified.)
6. **Only the executor / owner / principal may transition status**, logged via `status_changed` — EXCEPT `killed`, which the enforcer writes via `brake_tripped`.

### Validation Checks (WARN at v1.0; ERROR-ratchet after the v1.71 runtime lands)

1. `type: loop-run`; `status:` ∈ {active, paused, complete, killed, cancelled}; `state` ∈ {active, archived}.
2. `loop:` resolves to a `type: loop` entry; `loop_version:` valid semver.
3. `owner:` + `principal:` resolve to entities; `started_at` valid ISO 8601.
4. **`check_loop_run_has_jsonl`** — `run.jsonl` exists at `run_folder:` (pipeline-run Check 13 analog). ERROR.
5. **`check_loop_run_contract_locked`** — `loop_contract_locked` is the 2nd event, carrying non-empty `brakes` + a `goal.authored_by ≠ policy executor` + a `verifier`. ERROR (fail-closed).
6. **`check_loop_complete_requires_goal_met`** — `status: complete` / `terminal_state: complete` is INVALID without a `goal_met` event + a passing full-goal `verification_receipt`. ERROR. (Rule 5 — the loop analog of pipeline-run Check 15.)
7. **`check_loop_killed_has_brake_event`** — `status: killed` requires a `brake_tripped` event authored by an enforcer. ERROR.

Core checks inherited.

---

## 5. Composes-With

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.
- **[loop.capsule (1248583d)](loop.capsule.md)** — the template type loop-runs execute; pinned via `loop_version:` at start. The loop-run reads the loop's `goal`/`verifier`/`brakes`/`policy`/`consequence`.
- **[pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)** — structural template (`modeled_on`). Reuses the run-folder files, the structured `verification_receipt`, OTel GenAI attributes, the append-only discipline. The loop-run forks + specializes for iterations + brakes + the `killed` state.
- **brakes circuit-breaker ([1edbee15](../../vault/files/1edbee15.md))** — the enforcer that authors `brake_tripped` events from ground-truth (metering gateway + launchd watchdog). Talos-built.
- **[dev-spec 9da979b2](../../vault/files/9da979b2.md)** — the design this capsule realizes.

---

## Changelog

| Version | Date | Change | By |
|---|---|---|---|
| 1.0 | 2026-06-14 | Initial draft. The runtime/instance layer for `loop` (1248583d), modeled on pipeline-run.capsule. Adds the iteration model, the cooperative brake-state (legibility-only; enforcers read ground-truth), the `brake_tripped` event + `killed` terminal state, and the verifier-loopback. Realizes dev-spec 9da979b2 §Q1. | argus-a112 |

---

*loop-run capsule definition | v1.0 LOCKED (Mike-A114 2026-06-14, design lock) | the instance layer for loop.capsule | modeled on pipeline-run.capsule | UID `ee42c7c8`*
*"The loop is the template. The run is the instance. The goal is the proof — and a brake is the safety net."*
