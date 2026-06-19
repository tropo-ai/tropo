---
uid: bc6b17ec
title: external-test — dev-pipeline step 6
type: pipeline
subtype: workflow-node
name: external-test
version: 1.0.0
author: argus-a42
owner: argus
modified: 2026-05-31
modified_by: vela-v56
status: draft
state: active
role: step
children: []
step_owner_role: vela
step_verifier_role: same-as-executor
verification_class: false
depends_on_steps:
- 8654900a
exit_criteria:
- "file:<run_folder>/external-test-result.md exists AND carries frontmatter: (a) outcome: in {PASS | signed-off-on-known-failure | FAIL | skipped}; (b) tested_artifact: non-empty — the step-5 (8654900a) .zip artifact path or release version this result pertains to, binding the result to THIS build (not a stale prior-cycle file left in the folder); (c) when outcome in {signed-off-on-known-failure | FAIL}: signed_off_by: non-empty (owner sign-off per trust_level:approval-required); (d) when outcome: skipped: skip_rationale: non-empty (external-test's OWN inline skip path — Mike-directed skip recorded here; distinct from the cold-boot-walk step-7.5 c6b61fb9 SKIP.md, a different step). The frontmatter SHAPE + presence is the machine-checkable gate (verification_class:false — engine checks shape, principal judges content); this closes the trivial-stub hole (a one-word PASS authored without a run no longer passes). A FAIL without signed_off_by FAILS the gate (blocks git-commit step 7) at shape level. [Advisory: full conditional FAIL-routing enforcement awaits pipeline.capsule v2.1 branching per this step's Known Enforcement Gap; the frontmatter-shape check is the v2.0-expressible strengthening, per sa.criteria-reviewer 5c1aef02 weak-flagged review 2026-05-31.]"
vela_reconciliation_2026_05_31_v56: "RESOLVED — Vela V56 reconciled Argus's A2 best-effort per broadcast 431 (event 419/431). (1) Artifact name CONFIRMED: external-test-result.md in the dev-pipeline activation run_folder — distinct from cold-boot-walk's releases/v<X.Y.Z>/cold-boot-walk-report.md (that is the separate step 7.5 c6b61fb9). (2) Pass-assertion ADDED as the recorded-outcome enum (PASS | signed-off-on-known-failure | skipped-with-rationale), matching trust_level:approval-required + verification_class:false — the human signoff is the real gate, the file's presence is the machine check. (3) Machine-evaluable shape kept to file:<path> exists per sibling trigger-step grammar (0cf86ea5/4f64ec3c); outcome semantics live in the criterion prose. Check 19 pending-reconciliation hold can clear. SCOPE NOTE: the FULL external-test protocol (formal who-executes + machine pass/fail spec) remains the Known Enforcement Gap owned by Argus for v1.5 — this reconciliation pins the evidence-artifact contract, not the full protocol."
sa_criteria_reviewer_dogfood_2026_05_31: "AC5 of v1.62 test-spec 616c032b: Vela V56 dispatched sa.criteria-reviewer (5c1aef02) on THIS criterion as the agentic_review behavior + a self-dogfood. Verdict: WEAK-FLAGGED. Findings + actions taken: (1) semantic hollowness — the original 'file exists' was the textbook hollow-proxy (a one-word PASS authored without a run passed identically); STRENGTHENED to require frontmatter shape (outcome enum + tested_artifact + signed_off_by + skip_rationale). (2) FAIL-block over-promised vs what v2.0 can enforce; reframed to shape-level (FAIL without signed_off_by fails the gate) + advisory note on the v2.1-branching Known Enforcement Gap. (3) missing build-provenance binding; ADDED tested_artifact. (4) dangling cross-ref — the original cited release-cold-boot-walk.playbook §If-Mike-says-skip which (a) does not exist by that name and (b) governs cold-boot-walk step 7.5, not external-test; FIXED to external-test's own inline skip path. The sentinel works (caught real weaknesses in Vela's own criterion); the strengthen-at-contract-lock loop is dogfooded. Verdict is advisory; this strengthening is Vela ratifying it."
trust_level: approval-required
v1_46_0_changes: 'v3.0 per-step rich schema added by argus-a76 2026-05-20 per cycle brief MUST-SHIP #6. trust_level:approval-required because external-test gates on human (Mike) signoff before commit.'
v1_48_0_changes: 2026-05-20 by argus-a77 — Stream C substrate amendment. next_steps amended from [3e0bb81e] → [c6b61fb9 cold-boot-walk NEW]. The new step 7.5 (cold-boot-walk) inserts between external-test + git-commit per cycle brief [c184b781 v0.3 LOCKED] §3 Stream C — formalizes Block 4 close-criterion empirical-validation discipline as substrate-resident dev-pipeline step. Substrate originally authored under v1.47.0 cycle label; numbering shifted v1.47 → v1.48 per Mike-V49 chain-mutability override 2026-05-21.
next_steps:
- c6b61fb9
relationships:
- rel: member_of
  uid: 3a7dbdda
schema_version: 2
extraction_scope: ship
member_of: []
subsystem_hub:
- 76bab75f
capsule_version: '2.5'
---

# external-test — dev-pipeline step 6

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Playbooks](76bab75f.md) → **external-test — dev-pipeline step 6**

**🔗 This file** — UID `bc6b17ec` · type `pipeline` · state `active` · status `draft`

**📥 Cited by (1):**
- [Tropo-OS v1.48.0 — Cycle B Extraction-and-Publish Engineering ...](1d25e142.md) — `1d25e142` (type `release`, via `capabilities_touched`)
<!-- nav-block:end -->

## Purpose

Runs the `.zip` artifact produced in step-5 against external test execution. Results are recorded on this pipeline-run. A passing result is required to advance to git-commit; a failing result blocks step-7 and requires a decision (fix-and-rebuild or ship-with-known-issue per explicit owner sign-off).

## Structure

Leaf step. No children.

## Nodes

No child nodes. This is a leaf WorkflowNode.

## Flow Rules

Completes when: external test execution has run and a result (pass or explicit sign-off on known failure) is recorded on this pipeline-run. A failing result without sign-off is a blocking condition — step-7 does not start.

Advances to: git-commit (3e0bb81e) on pass or explicit sign-off.

## Cold-Boot Walk-Through

The executor hands the `.zip` to the external test process (currently: Mike unpacks the zip and runs the vault through its activation sequence). Results are recorded. If pass: step done, advance to git-commit. If fail: the pipeline-run is paused; the owning agent and Mike assess whether to fix-and-rebuild (re-enter build stage) or sign off and proceed.

## Known Enforcement Gaps

| Gap | What closes it | Target release | Owner |
|-----|----------------|----------------|-------|
| External test protocol not defined — no spec for what "external test" means, who executes it, what the pass/fail criteria are, or how results are recorded | Define external-test protocol as part of pipeline-run.capsule or a separate test-execution spec | v1.5 | argus |
| Blocking condition handling (fail without sign-off) not expressible in v2.0 — would require conditional branching back to build | pipeline.capsule v2.1 branching + condition semantics | v2.1 | argus |

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-03 | Initial draft. External test execution; pass or explicit sign-off required to advance. | argus-a42 |

---

*external-test | step WorkflowNode | deploy stage (3a7dbdda) | dev-pipeline (cd1fcd25) | argus-a42 | 2026-05-03*
