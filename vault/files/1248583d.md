---
uid: 1248583d
name: "loop"
type: capsule-definition
extends: core
version: "1.2"
tier: os
author: argus
created: 2026-06-14
created_by: argus-a112
modified: 2026-06-14
modified_by: argus-a114
v1_2_amendment_note: "v1.1→v1.2 (Argus A114 2026-06-14, Mike-A114 'human launch gate' direction): (1) adds the ACTIVATION GATE (§3.1) — before a loop-run starts, a human sets/confirms the brake ceilings via a launch prompt with easy defaults; (2) reintroduces max_iterations as a COOPERATIVE human-set HARD STOP (default 5: run at most N, then STOP and return to the human), distinct from the un-forgeable auto-kill that stays deferred — the human-set stop + the $/time hard floor cover the practical case (un-forgeable OTEL iteration needed only for fully-autonomous-no-human); (3) fixes §7 check #3, which still required the deferred max_iterations-as-auto-kill, leaving the validator demanding a field v1.1 had removed — now requires (max_iterations OR human_checkpoint_every) AND (max_budget_usd OR max_wall_clock_min). Realizes the Mike-A114 walk; locks with dev-spec v0.6. Build (Talos): the launch prompt + terminal hard-stop-at-N runtime; brake fields + fail-closed contract exist today."
v1_1_amendment_note: "v1.0→v1.1 (Argus A113 2026-06-14, Mike-directed 'practical not industrial'): the iteration brake is reframed from an un-forgeable hard auto-kill (the OTEL ground-truth machinery — overkill for L1) to a HUMAN-IN-THE-LOOP checkpoint: after human_checkpoint_every iterations (configurable, default 5) the loop HALTS for explicit human confirmation. The HARD auto-kill brakes remain spend (gateway 429) + wall-clock (run-folder ctime) — they bound any runaway by money + time, so cooperative iteration counting is SAFE (a mis-count costs a few iterations before $/time catch it). max_iterations hard-auto-kill + the OTEL un-forgeable iteration source + the no_progress auto-trip are DEFERRED (only needed for fully-autonomous-no-human; revisit if that becomes a requirement). no-progress is reviewed by the human at the checkpoint."
status: locked
locked_by: mike-maziarz
locked_at: 2026-06-14
enforced_enums:
  status: [draft, active, locked, archived, retired]
meta_status_rollup:
  to-do: [draft]
  in-progress: [active]
  done: [locked, archived, retired]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
realizes_dev_spec: 9da979b2
composes_with:
  - ee814120   # core.capsule — inherited floor
  - e4c8a6b2   # pipeline.capsule — sibling; loop REUSES its Exit-Criteria DSL (§6) + Verifier Pattern (§4)
  - ee42c7c8   # loop-run.capsule — the runtime/instance layer
  - 222873b9   # Tropo Work governance
tags: [capsule-definition, loop, bounded-verification, brakes, agentic-tools, agent-decided-next-step, v1.71-s1]
---

# loop — Capsule Definition v1.2

## 1. Intent

A loop is a declarative contract for **agent-decided iteration toward a verifiable goal, bounded by brakes**. Where a [pipeline (e4c8a6b2)](pipeline.capsule.md) is a *fixed* DAG (the path is known before the run; the acyclic + forward-only invariants forbid loopback), a loop is the **agent-decided-next-step + verifier-loopback superset**: look at state → the agent DECIDES the next action toward the goal → act → an independent verifier CHECKS → stop-or-repeat. The loop is the template; the [loop-run (ee42c7c8)](loop-run.capsule.md) is the instance.

**The loop is not the product — the exit condition is.** The whole value of declaring a loop is its `goal`: a verifiable, externally-defined done-condition, written *before* the run and checked by something *other than* the agent. That is bounded verification, Tropo's moat. A loop without a frozen, independently-checked goal is a "confident token furnace," not a governed loop.

This capsule is **reuse-heavy by design** (per dev-spec [9da979b2](../../vault/files/9da979b2.md)): every loop ingredient but one already exists. Triggers are ScheduleWakeup/launchd + Continuous-Listen + the event log; the decision policy is an executive or an agentic tool; tools are the Toolbelt; the verifier is the gauntlet/validator/cold-boot; state is the vault + run.jsonl + memory; the done-condition is the acceptance-criteria/Exit-Criteria DSL. The genuinely-new value is **governance**: one declared place for a loop's contract, a platform-enforced circuit-breaker (`brakes`) the agent can't bypass, and an independent verifier — **not autonomy.**

Before creating a loop: is this work actually a loop? See §6 (When-to-loop). If you can draw the whole DAG before running, it is a **pipeline**, not a loop. If it runs once, it is a **one-shot prompt**. Only loop when the next step is data-dependent AND the done-condition is externally verifiable.

---

## 2. Schema

### Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `uid` | 8-hex | Per core. |
| `type` | literal | `loop`. |
| `name` | string | ≤120 chars. Human-readable. |
| `version` | semver | Increments on any structural edit; loop-runs pin the version at start. |
| `author` | UID | Authoring entity. |
| `state` | enum | `active` / `archived`. |
| `status` | enum | `draft` / `active` / `locked` / `archived`. See §State Machine. |
| `goal` | object | **The frozen done-condition (a precondition).** `{ exit_criteria: [<DSL string>], authored_by: <principal-uid> }`. `exit_criteria` REUSES the pipeline Exit-Criteria DSL ([pipeline.capsule §6](pipeline.capsule.md)). `authored_by` MUST be a principal distinct from the loop's executor (§4); for `consequence: high\|critical` it MUST be a human principal. The executor may NOT edit `goal` after a loop-run starts. |
| `trigger` | object | `{ kind: schedule\|event\|manual, spec: <string> }`. `schedule` → ScheduleWakeup/launchd; `event` → an event-log correlation; declares WHAT starts a loop-run. |
| `policy` | object | The decision-maker. `{ kind: executive\|agentic-tool, ref: <agent-class\|tool-uid> }`. Route by consequence: mechanical/interpretive → agentic-tool (Haiku-class via `lib/llm.py`); judgment/irreversible → executive. |
| `tools` | UID array | The allowed tool set (Toolbelt UIDs) the loop's policy may call. The loop declares its tool scope; absent = read-only. |
| `verifier` | object | The independent checker. `{ kind: gauntlet\|validator\|cold-boot\|sa.<slug>, independent: true, lenses: <int>, attestation: aspirational\|signed }`. Extends [pipeline §4](pipeline.capsule.md) with the loop's independence requirement (§5). Rigor scales with `consequence` (§5). |
| `brakes` | object | **The circuit-breaker (the one new safety primitive).** Required, non-empty — a loop-run with no `brakes` does not start (§State Machine + Rule 2). Schema in §3. |
| `consequence` | enum | `low` / `medium` / `high` / `critical`. Drives required verifier rigor (§5) + brake ceilings. A loop whose `tools` include vault writes, external API calls, or multi-agent dispatch MUST NOT be `low` without a human-signed classification (Rule 4). |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `realizes_dev_spec` | UID | The dev-spec this loop instance was built from. |
| `supersedes` / `superseded_by` | UID | Supersession pair. |
| `locked_by` / `locked_at` | string / date | Lock provenance when `status: locked`. |
| `owner` | UID | Responsible entity; may transfer (author immutable). |

### Required Body Sections (5, in order)

1. **`## Purpose`** — what this loop does + what it does NOT (disambiguate from adjacent loops/pipelines).
2. **`## Goal & Verifier`** — the frozen done-condition (DSL), who authored it (non-executor), and how the verifier independently checks it.
3. **`## Brakes`** — the declared ceilings + their ground-truth enforcers (§3).
4. **`## Cold-Boot Walk-Through`** — a stranger-readable narrative of one loop-run from trigger to a brake/goal stop.
5. **`## Known Enforcement Gaps`** — gap / what closes it / target / owner (ADR-031 pattern).

Appended: **`## Changelog`**.

---

## 3. The `brakes` schema + enforcement (realizes dev-spec §Q1)

Brakes are **set by a human at the activation gate (§3.1)** with easy defaults. Three layers: a **human-set iteration stop** (`max_iterations`, default 5 — the front-door brake the operator reasons about), two **HARD auto-kill floors** (`max_budget_usd` + `max_wall_clock_min`, platform-enforced, ground-truth, fail-closed) that bound any runaway by **money + time** when the operator has walked away, and an optional **check-in cadence** (`human_checkpoint_every`) for longer loops:

```yaml
brakes:
  # Set by the HUMAN at the activation gate (§3.1) — easy defaults; the human confirms or tweaks.
  max_iterations: <int>          # v1.2: COOPERATIVE human-set HARD STOP — run at most N, then STOP and return to the human (default 5). Counted from run.jsonl; SAFE because the $/time floor below is the hard backstop. NOT the un-forgeable auto-kill (deferred).
  max_budget_usd: <number>       # per-run spend ceiling — HARD auto-kill floor (gateway 429; fail-closed)
  max_wall_clock_min: <int>      # process-age ceiling — HARD auto-kill floor (run-folder ctime watchdog; fail-closed)
  human_checkpoint_every: <int>  # OPTIONAL pause-and-resume cadence for longer loops: PAUSE for human confirmation every N (resumable). Distinct from max_iterations (terminal stop).
  tool_timeout_sec: <int>        # per-tool-call timeout (harness)
  # DEFERRED (post-v1.71): un-forgeable OTEL iteration auto-kill + no_progress_iters auto-trip — need an un-forgeable OTEL iteration source; needed only for fully-autonomous-no-human. The human-set max_iterations + the $/time floor cover the practical case; no-progress is reviewed by the human at the stop/checkpoint.
```

**The HARD auto-kill floors (spend + wall-clock) read GROUND-TRUTH the agent cannot forge; the iteration brakes are human-set and cooperatively counted** (the human-set `max_iterations` stop + the optional `human_checkpoint_every` cadence need not be un-forgeable, because spend + wall-clock are the hard backstops — a mis-count at worst costs a few iterations before $/time catch it):

- **Iteration stop (`max_iterations`) — the human-set hard stop (v1.2, the front-door brake).** Set by the operator at the activation gate (§3.1; default **5**). The loop runs at most N iterations, then STOPS terminally and returns to the human (relaunch is a new loop-run). Cooperatively counted from run.jsonl — SAFE because the $/time floor catches a gamed count. This is the un-forgeable auto-kill's practical replacement, not the auto-kill itself (deferred). **⚠ Runtime build item (v1.71/Talos):** the terminal stop-at-N + the launch prompt are NOT yet enforced by the watchdog; **enforced today** are spend, wall-clock, the `human_checkpoint_every` pause-at-N, and the loop-start fail-close. The field + fail-closed contract exist now; the terminal-stop runtime is the build delta.
- **Spend (`max_budget_usd`) — a local metering gateway.** The loop's model calls route through a local reverse-proxy (`ANTHROPIC_BASE_URL` → mitmproxy/Routerly) that reads Anthropic's own per-response `usage` and returns **HTTP 429 at budget**. Un-bypassable: the proxy holds the real API key; the loop's policy agent holds only a virtual key. This is the L1-deployable model-gateway; at L2/L3 it is a managed AI gateway — **one mechanism, every tier.** Fail-closed: a missing/unreadable spend file trips.
- **Wall-clock (`max_wall_clock_min`) — a launchd watchdog.** Reads the run-**folder** `ctime` (process age — the agent's run.jsonl appends don't reset it) and terminates the session / writes a poison sentinel honored at tool-call boundaries. HARD auto-kill, fail-closed.
- **Check-in cadence (`human_checkpoint_every`) — the OPTIONAL pause-and-resume mode (v1.1).** For longer loops where a terminal stop-at-N is too blunt: every N iterations the loop PAUSES — appends `human_checkpoint_required` to run.jsonl and STOPS until an explicit human `continue` — so the human reviews progress (incl. no-progress) and resumes or kills. Distinct from `max_iterations` (terminal). The cooperative count triggers the pause; the hard floor catches a gamed count. (Un-forgeable OTEL iteration enforcement deferred — see the v1.1/v1.2 notes.)
- The **in-agent check** (policy reads its counters + self-stops) is **cooperative-but-audited**: the fast path; if skipped/forged, the validator catches the over-run after the fact. It is NOT the circuit-breaker.

Runtime: the brakes circuit-breaker tool ([1edbee15](../../vault/files/1edbee15.md), Talos-built) + the `loop-run` engine. **Fail-closed:** the engine refuses to start a loop-run with empty `brakes`, no `goal`, no `verifier`, or no gateway route.

### 3.1 The activation gate — the human sets the ceilings at launch (Mike-A114)

A loop's brakes are **set by a human at activation**, not pre-baked by an author. When a loop-run is launched, the runtime prompts the operator with a few plain questions and easy defaults, and writes the answers into the `loop_contract_locked` event the runtime enforces:

- *"Stop after how many iterations?"* → `max_iterations` (default **5**, hard stop — runs at most N, then STOPS and returns to you). *(runtime build item — see the closing note; today the equivalent is `human_checkpoint_every` pause-at-N.)*
- *"Dollar ceiling for this run?"* → `max_budget_usd` (hard auto-kill floor).
- *"Maximum minutes?"* → `max_wall_clock_min` (hard auto-kill floor).
- *(optional)* *"Check in every N instead of stopping?"* → `human_checkpoint_every` (pause-and-resume cadence).

The human-set iteration stop is the brake the operator reasons about ("it'll run 5 times and come back to me" — zero training required); the $/time floor is the seatbelt for when the operator isn't watching. A loop-run launched with no human-set ceilings fail-closes (Rule 2). *Build (v1.71, Talos): the launch prompt + the terminal hard-stop-at-N runtime behavior; the brake fields + the fail-closed contract exist today.*

---

## 4. The `goal` — frozen, external, non-executor-authored (realizes §Q2 property 2)

The exit condition is written *before* the loop runs (a precondition), uses the [pipeline Exit-Criteria DSL (§6)](pipeline.capsule.md), and is **authored or countersigned by a principal distinct from the loop's executor** — verifier-independence applied to the precondition, not just the verdict. A bar the executor set for itself is trivially passable. `consequence: high|critical` loops require a human principal (Mike) to sign the `goal` before the first run. The executor cannot redefine "done" mid-run (the `goal` is immutable once a loop-run pins it).

---

## 5. The `verifier` — consequence-scaled defense-in-depth (realizes §Q2)

Reward-hacking is real (agents overwrite tests, fool judges). No single property suffices; the verifier stacks five, **each closing a vector the others don't**, and its rigor is a **dial set by `consequence`**:

1. **Independent** — a separate agent; no shared context/incentive/write-scope with the policy agent (extends pipeline §4's explicit-override case: `verifier.kind != policy`).
2. **Frozen precondition** — the `goal`, authored by a non-executor (§4).
3. **Multi-lens adversarial** — `lenses ≥ 2` divergent refuters; majority to pass. Required count scales with `consequence`.
4. **Machine-attested — ASPIRATIONAL at v1.71** (`attestation: aspirational`). The verifier signing its own un-forgeable verdict depends on the deferred run.jsonl signing frontier (event 2500, unbuilt) — NOT the verifier-independence line. Carried by (3) + the cooperative-audited validator until signing lands; `attestation: signed` is reserved for when it does.
5. **Outcome-not-proxy** — verify the real done-condition (cold-boot/stranger-test), never a self-reported flag the agent controls.

**Honest framing:** no verifier is perfectly ungameable; the goal is to make gaming cost more than doing the work. Robustness is a dial set by stakes, not a universal guarantee.

---

## 6. When-to-loop (realizes §Q3/Q4) — the gate before declaring a loop

A governed loop earns its cost over a one-shot prompt or a fixed pipeline only when **all three** hold:

1. **Recurs / runs long** — multiple look-decide-act-check passes (single-pass → one-shot prompt).
2. **Next step is data-dependent** — the loop-vs-pipeline line: *if you can draw the whole DAG before running, it's a pipeline; if the next node depends on the last node's output in a way you can't predetermine, it's a loop.* The loop's cost is legibility — pay it only when the decision-in-the-middle is genuine.
3. **Done is externally verifiable** — the exit condition is writable as a precondition; if not, do not build a loop.

Fail any → one-shot or pipeline instead.

---

## 7. Validation Rules

### Governance Rules (in addition to core)

1. **New loop files start at `status: draft`.** Direct creation at active/locked is a validation error.
2. **`brakes`, `goal`, `verifier` are required and non-empty.** A loop with any of them empty cannot start a loop-run (fail-closed, engine-enforced). Anti-token-furnace gate.
3. **`goal.authored_by` ≠ executor.** The done-condition's author must be a principal distinct from the loop's policy executor; `consequence: high|critical` requires a human author.
4. **`consequence` is not freely self-declared.** A loop whose `tools` include vault writes, external API calls, or multi-agent dispatch may not declare `consequence: low` without a human-signed classification.
5. **`version` increments on any structural edit.** Loop-runs pin at start; the pinned version does not drift.
6. **Amendments via supersession once `status: locked`.**

### Validation Checks (WARN at v1.0; ERROR-ratchet after the v1.71 build lands the runtime)

1. `type: loop`; `name` present ≤120; `version` valid semver; `author` resolves.
2. `status:` ∈ {draft, active, locked, archived, retired}; `state` ∈ {active, archived}; new files start `draft`.
3. **`check_loop_has_brakes`** — `brakes` present + non-empty with at least **one human-set iteration brake (`max_iterations` OR `human_checkpoint_every`)** AND **one hard floor (`max_budget_usd` OR `max_wall_clock_min`)**. Empty / floor-absent → ERROR (fail-closed). *(v1.2 fix: v1.1 deferred `max_iterations` out of the schema but this check still required it, leaving the validator demanding a removed field; v1.2 reintroduces `max_iterations` as the cooperative human-set stop and accepts the check-in cadence as the alternative iteration brake.)*
4. **`check_loop_goal_independent`** — `goal.authored_by` present + ≠ the `policy.ref` executor; `consequence: high|critical` → `goal.authored_by` resolves to a human principal.
5. **`check_loop_verifier_independent`** — `verifier.independent: true` + `verifier.kind != policy.kind/ref`; `lenses` present.
6. **`check_loop_consequence_scope`** — write-scope/dispatch tools + `consequence: low` → ERROR unless a human-signed classification is referenced.
7. Body contains §Purpose, §Goal & Verifier, §Brakes, §Cold-Boot Walk-Through, §Known Enforcement Gaps in order.

---

## 8. Composes-With

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.
- **[pipeline.capsule (e4c8a6b2)](pipeline.capsule.md)** — sibling. The loop REUSES its Exit-Criteria DSL (§6) for `goal` + its Verifier Pattern (§4) for `verifier`; it does not reinvent them. The loop is the agent-decided-next-step + verifier-loopback *superset* of the pipeline's fixed, acyclic DAG.
- **[loop-run.capsule (ee42c7c8)](loop-run.capsule.md)** — the runtime/instance layer. A loop is the template; a loop-run is the instance, recording iterations as run.jsonl events + the (cooperative) brake counters + verifier receipts.
- **brakes circuit-breaker ([1edbee15](../../vault/files/1edbee15.md))** — the platform enforcer (metering gateway + launchd watchdog + loop-run engine). Talos-built per the dev-spec.
- **[dev-spec 9da979b2](../../vault/files/9da979b2.md)** — the design this capsule realizes (Q1 brakes locus, Q2 verifier stack, Q3/Q4 when-to-loop, all Mike-A112-walk-locked).

The dispatcher (66f7b892), continuous-listen (91c4e2a7), and fleet-ops (cb7d713a) v1.71 mechanisms are the loop's first three consumers — each a declared loop instance.

---

## Changelog

| Version | Date | Change | By |
|---|---|---|---|
| 1.0 | 2026-06-14 | Initial draft. Declares the `loop` type realizing dev-spec 9da979b2 (Mike-A112 walk: Q1 out-of-band metering-gateway brakes, Q2 consequence-scaled defense-in-depth verifier, Q3/Q4 when-to-loop). Reuses pipeline.capsule §4/§6. Authored at the v1.71 S1 build; locks with its dev-spec + the brakes runtime. | argus-a112 |
| 1.1 | 2026-06-14 | "Practical not industrial" (Mike-directed): iteration brake reframed from an un-forgeable auto-kill to a human checkpoint; `max_iterations` auto-kill + OTEL iteration source + no-progress auto-trip deferred. Hard $/time auto-kills stand. | argus-a113 |
| 1.2 | 2026-06-14 | Activation gate (§3.1): the human sets brake ceilings at launch with easy defaults. `max_iterations` reintroduced as a cooperative human-set HARD STOP (default 5), backed by the $/time floor — distinct from the deferred un-forgeable auto-kill. §7 check #3 fixed (no longer requires the deferred field). Mike-A114 walk; locks with dev-spec v0.6. | argus-a114 |

---

*loop capsule definition | v1.2 LOCKED (Mike-A114 2026-06-14, design lock) | sibling to pipeline.capsule | realizes dev-spec 9da979b2 | UID `1248583d`*
*"The loop is not the product. The exit condition is — and that's bounded verification."*
