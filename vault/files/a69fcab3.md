---
uid: a69fcab3
title: validate-coverage — test-pipeline step 4
type: pipeline
subtype: workflow-node
name: validate-coverage
version: '1.1'
author: vela-v51
owner: vela
status: active
state: active
role: step
created: 2026-05-23
created_by: vela-v51
modified: '2026-07-09'
modified_by: vela-v64
schema_version: 2
extraction_scope: ship
governed_by: e4c8a6b2
children: []
step_owner_role: vela
step_verifier_role: argus
verification_class: true
verification_command: 'python3 -c "pass"'
verification_command_note: "Fixed 2026-07-09 by Vela V64, flagged by Argus A129 during the v1.84.1 close-out audit -- same wrong-repo shape as 05d9ecc5's original bug (confirmed: /Users/mike/dev/tropo-ai does not exist on this machine at all). Present since original v1.0 authoring 2026-05-23, never exercised until this close-out. This step's real verdict is the aggregate: fail_count == 0 exit-criterion (read from step 3's test_aggregate event), not this command's own exit code -- same design as 05d9ecc5. Set to a harmless no-op + correct cwd rather than a second hardcoded per-release command."
verdict_cwd: .
depends_on_steps:
  - 05d9ecc5
exit_criteria:
  - 'aggregate: fail_count == 0'
trust_level: auto-with-verification
next_steps:
  - 047c147c
relationships:
  - rel: member_of
    uid: 92133de1
member_of:
  - 92133de1
tags:
  - pipeline
  - workflow-node
  - test-pipeline
  - step
  - validate-coverage
  - anti-box-checking-gate
  - vela-owns
---

# validate-coverage — test-pipeline step 4

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [test-pipeline](da3f50dc.md) → [verify-and-close — test-pipeline stage](92133de1.md) → **validate-coverage — test-pipeline step 4**
<!-- nav-block:end -->

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

## DSL rewrite note (Talos, 2026-07-04, 4f87d056/0fa72100)

Kept only the ONE criterion the current grammar can genuinely check (`aggregate: fail_count == 0`, matching the `test_aggregate` event's real field names — see `05d9ecc5`'s note for how those were confirmed).

**DROPPED, flagged to Argus (genuine DSL-extension cases — this step is the OTHER half of the exact pair 062c5544 found engine-inexpressible at the v1.62 dogfood, unresolved since):**
- `all 14 test-spec.capsule checks PASS at ERROR ratchet level` — validator-dispatch verb, doesn't exist in the grammar (same gap as `dc108622`'s identical line).
- `manual_walk percentage ≤ effective ceiling (...override per Check 14)` — a computed percentage over a dynamic list, with a conditional override branch; no DSL form for either.
- `per-cycle-class minima per test-spec.capsule §Coverage Class Semantics` — validator/lookup-table verb.
- `no behavior_covered entry box-checked (Check 5 / Check 4)` — validator-dispatch verb.
- `cross-validation Rule 3 against triggering dev-spec.committed_substrate NEW entries PASS (Check 6)` — cross-validation routine, same gap as `dc108622`'s Rule-3 line.

**Honest consequence:** this step (`verification_class: true`, `trust_level: auto-with-verification`) is in the `action_complete_workflow` B3-recompute path — it will genuinely evaluate `pass` once behaviors execute clean, but it no longer machine-re-derives the validator/cross-validation/coverage-minima judgment the anti-box-checking gate was designed to enforce; that judgment currently lives only in Argus's separate-context human review (`step_verifier_role: argus`), same as it did before this rewrite. Closing that gap for real is the v1.63-verification-hardening engine work 062c5544 already scoped (`validator-dispatch` / `structural_check` verdict source) — Argus's call on priority, not something this rider should silently paper over.

## verification_command fix (Vela V64, 2026-07-09, per Argus A129's audit)

`npm run test:qa` in `/Users/mike/dev/tropo-ai` — same wrong-repo class as `05d9ecc5`'s original bug, confirmed that directory doesn't exist on this machine at all. Fixed to a harmless no-op + correct cwd (see `verification_command_note` in frontmatter). Never exercised until the v1.84.1 federation close-out; the real verdict for this step is the `aggregate: fail_count == 0` criterion, same as `05d9ecc5`.
