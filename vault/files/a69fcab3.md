---
uid: a69fcab3
title: "validate-coverage — test-pipeline step 4"
type: pipeline
subtype: workflow-node
name: "validate-coverage"
version: "1.0"
author: vela-v51
owner: vela
status: active
state: active
role: step
created: 2026-05-23
created_by: vela-v51
modified: 2026-05-23
modified_by: vela-v51
schema_version: 2
extraction_scope: ship
governed_by: e4c8a6b2
children: []
step_owner_role: vela   # anti-box-checking gate is mine per test-spec.capsule v1.0 walk lock SQ1
step_verifier_role: argus   # substrate-coherence verifier separate context
verification_class: true
verification_command: "npm run test:qa"
verdict_cwd: "/Users/mike/dev/tropo-ai"
depends_on_steps:
  - "05d9ecc5"   # step 3 run-test-substrate
exit_criteria:
  - "all 14 test-spec.capsule v1.0 [621824df] validation checks PASS at ERROR ratchet level"
  - "test_aggregate event from step 3: zero behaviors with fail verdict OR explicit Mike-walked override per Check 14 manual_walk_ceiling_override semantics"
  - "manual_walk percentage in behaviors_covered ≤ effective ceiling (default 30% OR override per Check 14)"
  - "per-cycle-class minima per test-spec.capsule §Coverage Class Semantics § Per-cycle-class required minima — verified against test-spec.cycle_class (or inferred class at v1.0)"
  - "no behavior_covered entry box-checked (Check 5 verification_method substrate-resolvable + Check 4 enum valid both PASS)"
  - "cross-validation Rule 3 against triggering dev-spec.committed_substrate NEW entries PASS (Check 6)"
trust_level: auto-with-verification
next_steps:
  - "047c147c"   # step 5 close-activation
relationships:
  - rel: member_of
    uid: 92133de1   # verify-and-close stage
member_of:
  - "92133de1"
tags: [pipeline, workflow-node, test-pipeline, step, validate-coverage, anti-box-checking-gate, vela-owns]
---

# validate-coverage — test-pipeline step 4

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [test-pipeline](da3f50dc.md) → [verify-and-close — test-pipeline stage](92133de1.md) → **validate-coverage — test-pipeline step 4**

**🔗 This file** — UID `a69fcab3` · type `pipeline` · state `active` · status `active`

**↔ Siblings (1):**
  - **under [verify-and-close — test-pipeline stage](92133de1.md):** [close-activation — test-pipeline step 5](047c147c.md)

**📥 Cited by (3):**
- [v1.62 dogfood: 2 test-pipeline steps have PROSE exit_criteria ...](062c5544.md) — `062c5544` (type `note`, via `refs`)
- [Tropo-OS v1.51.0 — Three-Pipeline Substrate-Engineering (Six A...](b0435ff0.md) — `b0435ff0` (type `release`, via `capabilities_touched`)
- [test-pipeline step-3 executor unwired — no test_aggregate rece...](d3a9c1f7.md) — `d3a9c1f7` (type `note`, via `refs`)
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [pipeline (e4c8a6b2)](e4c8a6b2.md) |
| Member of | [verify-and-close — test-pipeline stage (92133de1)](92133de1.md) |

*The anti-box-checking gate. Vela owns per test-spec.capsule v1.0 walk lock SQ1 (Mike-V51 2026-05-23). This is where "test coverage is real, not box-checking" becomes structurally enforced — not memory-resident.*

**Why this step is the substantive gate:** the test-spec.capsule v1.0 anti-box-checking machinery (14 validation checks + 5 verification_methods + cross-validation MANDATED + manual_walk ceiling + per-cycle-class minima) is only as strong as the step that enforces it. Step 4 is that step. If step 4 lets cosmetic coverage through, the whole architecture lies.

**What it does:**
1. Re-runs all 14 test-spec.capsule v1.0 validation checks at ERROR ratchet level (Check 1 required-fields through Check 14 override-valid)
2. Reads test_aggregate event from step 3 run.jsonl; verifies pass/fail distribution against acceptance_criteria
3. Computes manual_walk percentage: count of behaviors_covered with verification_method:manual_walk / total behaviors_covered count. Verifies ≤ effective ceiling (default 30% OR manual_walk_ceiling_override if set + valid per Check 14)
4. Checks per-cycle-class minima per test-spec.capsule §Coverage Class Semantics § Per-cycle-class required minima:
   - cycle_class:substrate → smoke + structural_check floor; gauntlet if OS-tier; regression if amends
   - cycle_class:ux → smoke + cold-boot floor; regression if amends UX
   - cycle_class:engine-runtime → smoke + property floor; regression if amends; gauntlet if engine-extension
5. Verifies cross-validation Rule 3 MANDATED: each dev-spec NEW substrate entry has matching test-spec behaviors_covered.target_substrate_refs (Check 6)
6. Surfaces violations to argus-vela channel for separate-context substrate-coherence review per pipeline.capsule v3.0 verification-class pattern

**Failure modes (Vela-walkable):**
- Any test-spec capsule check FAIL → step refuses to close; surface specific failing checks for Vela remediation
- Aggregate has fail verdicts without explicit override → step refuses to close; surface failing behaviors for cycle remediation
- manual_walk percentage exceeds ceiling → step refuses to close; demand override + ≥100 char rationale OR refactor verification_methods
- Per-cycle-class minima not met → step refuses to close; surface missing classes per cycle_class

**Why argus is step_verifier_role:** anti-box-checking misses are hard to catch in the executing context (Vela authored the test-spec + walked the plan + ran the execution; pattern-matching against own work has blind spots). Argus's separate context catches what Vela can't see.

**Hands off to:** step 5 close-activation, when all exit criteria PASS + Argus substrate-coherence verifier signs off.
