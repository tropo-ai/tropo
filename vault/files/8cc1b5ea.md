---
uid: 8cc1b5ea
title: "validate-evidence - vault-ops-pipeline step 4"
type: pipeline
subtype: workflow-node
name: "validate-evidence"
version: "1.0"
author: vela-v54
owner: vela
status: draft
state: active
role: step
created: 2026-05-27
created_by: vela-v54
modified: 2026-05-27
modified_by: vela-v54
schema_version: 2
extraction_scope: ship
governed_by: e4c8a6b2
children: []
step_owner_role: vela
step_verifier_role: same-as-executor
verification_class: true
verification_command: "python3 vault/tools/d2b9c8e6.py"
depends_on_steps:
  - "7a683e3a"   # step 3
exit_criteria:
  - "Every dispatched sa.* (scheduled) OR every substrate_touch (on-demand) in step 2 plan has a completion event in run.jsonl"
  - "For scheduled: every sa.* activation-log record has [DONE] block written by the sa.* itself (not by the pipeline); any [DONE]-missing dispatch surfaces as gap"
  - "For on-demand: every substrate_touch's declared verification_method evidence resolves clean (e.g., machine_executable_script exited 0; deterministic_assertion passed; structural_check validator clean; agentic_review verdict captured; manual_walk note present)"
  - "vault-ops-spec.acceptance_criteria post-conditions verified against substrate state - reader can answer 'did this work happen?' by reading substrate, not by trusting the plan"
  - "Any gap (missing evidence / failed assertion / box-checking smell) HALTS close; activation cannot reach step 5 until gap resolved OR explicitly skipped with documented rationale"
trust_level: auto-with-verification
next_steps:
  - "98de904e"   # step 5 close-activation
relationships:
  - rel: member_of
    uid: 9dab87a0   # vault-ops-pipeline root
member_of:
  - "9dab87a0"
tags: [pipeline, workflow-node, vault-ops-pipeline, step, anti-box-checking-gate, evidence-validation]
---

# validate-evidence - vault-ops-pipeline step 4

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [vault-ops-pipeline](9dab87a0.md) → **validate-evidence - vault-ops-pipeline step 4**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/tropo-work/vault-ops-pipeline/8cc1b5ea — validate-evidence - vault-ops-pipeline step 4.md](../../00-tropo-nav/00-tropo-active/tropo-work/vault-ops-pipeline/8cc1b5ea%20%E2%80%94%20validate-evidence%20-%20vault-ops-pipeline%20step%204.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-active/tropo-work/vault-ops-pipeline/8cc1b5ea — validate-evidence - vault-ops-pipeline step 4.md](argo-os/00-tropo-nav/00-tropo-active/tropo-work/vault-ops-pipeline/8cc1b5ea%20%E2%80%94%20validate-evidence%20-%20vault-ops-pipeline%20step%204.md)

**🔗 This file** — UID `8cc1b5ea` · type `pipeline` · state `active` · status `draft`

**↔ Siblings (5):**
  - **under [vault-ops-pipeline](9dab87a0.md):** [accept-vault-ops-spec - vault-ops-pipeline step 1](dac91126.md) · [close-activation - vault-ops-pipeline step 5](98de904e.md) · [execute-vault-ops - vault-ops-pipeline step 3](7a683e3a.md) · [plan-vault-ops - vault-ops-pipeline step 2](bd298097.md) · [vault-ops-pipeline first dogfood — V54 session ...](5e824d80.md)
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [pipeline (e4c8a6b2)](e4c8a6b2.md) |
| Member of | [vault-ops-pipeline (9dab87a0)](9dab87a0.md) |

*The anti-box-checking gate. Mirrors test-pipeline step 4 validate-coverage. Without this, "I dispatched the fleet" becomes box-checking when one sa.* silently failed.*

**Why this step exists:** the V53 transfer claimed "v1.53 archived per rolling-window" but the rolling-window flip never executed - substrate state didn't match the claim. That class of failure is exactly what this step catches. Plan-claimed work is verified against substrate-actual evidence before close.

**What it does:**
1. Walks vault-ops-spec.plan.md (or run.state.json) item by item
2. For each scheduled dispatch: confirms sa.* activation-log record exists + has [DONE] block + summary aligns with what plan said it would do
3. For each on-demand substrate_touch: confirms verification_method evidence resolves per declared check:
   - `machine_executable_script`: exit code captured in run.jsonl + zero
   - `deterministic_assertion`: assertion passed (DSL evaluation logged)
   - `structural_check`: validator extension output clean
   - `agentic_review`: sa.* verdict captured (verdict text + dispatch_target named)
   - `manual_walk`: note present in run.jsonl (counts only if owner-walked, not pipeline-written)
4. Compares against vault-ops-spec.acceptance_criteria post-conditions: reads substrate state + confirms the claim holds
5. Any gap flagged with specific evidence (which item, what's missing, what was claimed vs what's verifiable)

**Anti-box-checking smells to flag:**
- sa.* activation-log record exists but no [DONE] block - sa.* didn't self-terminate cleanly
- run.jsonl `dispatch_completed` event written but no corresponding activation-log record on disk
- substrate_touch claims completion but target_substrate_refs file shows pre-touch state
- acceptance_criteria worded as "the fleet ran" instead of named post-conditions - flag for spec amendment

**Failure modes:**
- Any gap from above - step halts; activation cannot transition to step 5 until gap resolved
- Resolution paths: (a) re-execute the missing item; (b) re-author evidence from out-of-band action with explicit run.jsonl `evidence_added_manually` event + rationale; (c) explicit skip with owner-documented rationale (logged in plan.md amendment + run.jsonl `item_skipped` event)
- No silent passes; no "good enough" - if the gate doesn't fire honestly, the doctrine dies

**Hands off to:** [step 5 close-activation (98de904e)](98de904e.md) when all exit criteria PASS honestly.
