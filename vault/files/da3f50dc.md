---
uid: da3f50dc
title: "test-pipeline"
type: pipeline
subtype: workflow-node
name: "test-pipeline"
version: "1.0"
author: vela-v51
owner: vela
domain: tropo-testing
status: active
state: active
role: root
created: 2026-05-23
created_by: vela-v51
modified: 2026-05-23
modified_by: vela-v51
test_spec_input_required: true   # v1.0: test-pipeline activations require test-spec.capsule v1.0 entry as activation input; engine refuses activation without compliant test-spec per Pipeline-Runtime Engine Extension v0.1 [51d171f3] §Activation-Input Validation + test-spec.capsule v1.0 [621824df] §Required Frontmatter
v1_0_authoring_context: "v1.0 authored by Vela V51 2026-05-23 as Phase C of v1.51 Three-Pipeline Substrate-Engineering cycle per Mike-V51 directive 'proceed with a' (drive Phase C now). Composes with: test-spec.capsule v1.0 LOCKED same session at [621824df] (the activation-input contract); pipeline.capsule v3.0 [e4c8a6b2] (governing capsule; per-step rich schema); Pipeline-Runtime Engine Extension v0.1 [51d171f3] (Argus A80; engine coupling enforcement at activation close); Three-Pipeline Substrate-Enforcement Architecture v0.3 [c3dc9f00] §3 §4 (Vela primary + Argus engine integration + Talos engineering implementation lane assignments). Triggered by dev-pipeline step 4.6 [4f64ec3c trigger-test-pipeline-activation] per dev-pipeline v1.51.0 retrofit; back-feeds into dev-pipeline activation close gate. Six steps organized into three stages (prepare / execute / verify-and-close). Vela primary per Mike-G57 one-primary-per-pipeline lock; Argus engine integration; Talos engineering implementation of machine_executable_script execution + assertion DSL evaluation + agentic_review sa.* dispatch wiring."
schema_version: 2
extraction_scope: ship
governed_by: e4c8a6b2   # pipeline.capsule v3.0
composes_with:
  - "621824df"   # test-spec.capsule v1.0 (activation-input contract)
  - "51d171f3"   # Pipeline-Runtime Engine Extension v0.1 (engine coupling enforcement)
  - "c3dc9f00"   # Three-Pipeline Substrate-Enforcement Architecture v0.3
  - "a5f4b26b"   # Captain's Briefing v3.0 (Structural-Enforcement Requirement 2)
  - "cd1fcd25"   # dev-pipeline (parent pipeline; coupling target)
member_of:
  - "b8e5f3a2"   # tropo-work L0 root (parallel to dev-pipeline placement)
children:
  - "69c291b7"   # prepare stage
  - "2e097029"   # execute stage
  - "92133de1"   # verify-and-close stage
next_steps: []
default_trust_gradient: auto-with-verification
default_retry_policy:
  max_retries: 0
  backoff: linear
default_timeout_hours: 12
tags: [pipeline, test-pipeline, vela-primary, three-pipeline-architecture, v1-51-phase-c, structural-enforcement, anti-box-checking-gate]
---

# test-pipeline

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → **test-pipeline**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/da3f50dc — test-pipeline.md](../../00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/da3f50dc%20%E2%80%94%20test-pipeline.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/da3f50dc — test-pipeline.md](argo-os/00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/da3f50dc%20%E2%80%94%20test-pipeline.md)

**🔗 This file** — UID `da3f50dc` · type `pipeline` · state `active` · status `active`

**↓ Children (27):**
  - **activation:** [test-pipeline Activation 11e4f590 — v1.53 Cycle...](11e4f590.md)
  - **pipeline (3):** [execute — test-pipeline stage](2e097029.md) · [prepare — test-pipeline stage](69c291b7.md) · [verify-and-close — test-pipeline stage](92133de1.md)
  - **project (23):** [test-pipeline Activation Root 208dbba3 — v1.53 ...](208dbba3.md) · [test-pipeline — Activation Root (2026-05-24)](2a416ad5.md) · [test-pipeline — Activation Root (2026-05-24)](b9c873de.md) · [test-pipeline — Activation Root (2026-05-25)](01c2bcc1.md) · [test-pipeline — Activation Root (2026-05-25)](19fa5b7d.md) · [test-pipeline — Activation Root (2026-05-26)](3fe8d221.md) · [test-pipeline — Activation Root (2026-05-26)](a6fe0bad.md) · [test-pipeline — Activation Root (2026-05-26)](bb8dab97.md) · + 15 more

**↔ Siblings (14):**
  - **under [tropo-work](b8e5f3a2.md):** [01-inbox](c5d8f1e3.md) · [app-pipeline](2918e3b4.md) · [dev-pipeline](cd1fcd25.md) · [doc-pipeline](5a4337ff.md) · [Hello Tropo — 2026 Customer Event Plan](e8d1a4f6.md) · [kb-pipeline](19a5f12c.md) · + 8 more

**📥 Cited by (27):**
- [v1.53.0 — Three-Pipeline Discipline Compounding — Test-Spec (E...](04881aa8.md) — `04881aa8` (type `test-spec`, via `composes_with`)
- [test-pipeline Activation — 2026-05-29](052e7ebc.md) — `052e7ebc` (type `activation`, via `agent_root`)
- [test-pipeline Activation 11e4f590 — v1.53 Cycle (substrate-coh...](11e4f590.md) — `11e4f590` (type `activation`, via `member_of`, `agent_root`)
- [test-pipeline Activation — 2026-05-24](227aa9cf.md) — `227aa9cf` (type `activation`, via `agent_root`)
- [test-pipeline Activation — 2026-05-27](34ed949d.md) — `34ed949d` (type `activation`, via `agent_root`)
- *+ 22 more — full back-link sweep via `grep -l "da3f50dc" vault/files/*.md`*
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [pipeline (e4c8a6b2)](e4c8a6b2.md) |
| Composes with | [test-spec (621824df)](621824df.md) |
| Composes with | [Pipeline-Runtime Engine Extension — Three-Pipeline Coupling + Multi... (51d171f3)](51d171f3.md) |
| Composes with | [Three-Pipeline Substrate-Enforcement Architecture v0.3 - dev-spec +... (c3dc9f00)](c3dc9f00.md) |
| Composes with | [Captain (a5f4b26b)](a5f4b26b.md) |
| Composes with | [dev-pipeline (cd1fcd25)](cd1fcd25.md) |
| Member of | [tropo-work (b8e5f3a2)](b8e5f3a2.md) |

*v1.0 LOCKED 2026-05-23 by Vela V51 as Phase C of v1.51 Three-Pipeline Substrate-Engineering. Activation-input: test-spec.capsule v1.0 [621824df] entry. Coupling: triggered by dev-pipeline step 4.6; back-feeds dev-pipeline activation close gate.*

---

## Intent

A test-pipeline activation exercises the behaviors a triggering dev-cycle introduces. The pipeline accepts a test-spec entry (the activation-input contract per test-spec.capsule v1.0), authors test substrate where needed, runs the tests, validates coverage against the test-spec's `behaviors_covered` declaration, and closes back into the triggering dev-pipeline's activation gate.

The substantive call this pipeline embodies: **test coverage is real, not box-checking.** Every closed test-pipeline activation has machine-checkable evidence that the dev-cycle's NEW substrate is exercised — not "tests cover the cycle" but "test_substrate at X executes Y behaviors with verification_method Z, each producing pass/fail evidence."

## Coupling shape

```
dev-pipeline activation (with dev-spec input)
  → step 4 update-subsystem-canonical-docs
    → step 4.5 trigger-doc-pipeline-activation     ┐
    → step 4.6 trigger-test-pipeline-activation    │ parallel fire
                ↓                                  │
              test-pipeline activation             │ (this pipeline)
                (with test-spec input)             │
                  → prepare → execute → verify     │
                  → close → status:done            │
                                                   │
  → step 6 produce-release-folder                  ┘ blocks until BOTH
    (eligible only when triggered_test_spec_uid +    triggered activations
     triggered_doc_spec_uid both status:done)        at status:done
```

Engine-level enforcement at the dev-pipeline activation close per Pipeline-Runtime Engine Extension v0.1 [51d171f3] §Three-Pipeline Coupling State Machine. test-pipeline activation status:done is a precondition for dev-pipeline activation close.

## Stages + steps (6 steps in 3 stages)

| Stage | Step | Owner | What |
|---|---|---|---|
| **prepare** ([69c291b7](69c291b7.md)) | 0. accept-test-spec ([dc108622](dc108622.md)) | vela | Validate test-spec input against capsule v1.0 (14 checks); confirm triggering dev-cycle reference resolves |
| | 1. plan-test-substrate ([846a0909](846a0909.md)) | vela | Author plan substrate naming each behavior's test substrate path + verification_method dispatch |
| **execute** ([2e097029](2e097029.md)) | 2. author-test-substrate ([d3511487](d3511487.md)) | vela (substrate) + talos (engineering when needed) | Author test substrate for behaviors_covered entries; new files OR extensions to existing |
| | 3. run-test-substrate ([05d9ecc5](05d9ecc5.md)) | talos (engine-orchestrated) + vela (manual_walk + agentic_review dispatch) | Execute each behavior; capture per-behavior pass/fail; aggregate |
| **verify-and-close** ([92133de1](92133de1.md)) | 4. validate-coverage ([a69fcab3](a69fcab3.md)) | vela | Anti-box-checking gate: all test-spec capsule checks pass; manual_walk ceiling honored; per-cycle-class minima met |
| | 5. close-activation ([047c147c](047c147c.md)) | vela | Set test-spec closed_at + acceptance_evidence; pipeline-run status:done; back-feed dev-pipeline activation gate |

## State machine

Per pipeline.capsule v3.0:
- `draft → active`: locked at v1.0 by Vela V51 + Mike-V51 lock signal 2026-05-23
- `active → archived`: only via supersession with bidirectional pointer pair

Pipeline-run instances (pipeline-run.capsule v2.0) carry the runtime state machine for individual activations.

## Activation-input contract

Per test-spec.capsule v1.0 [621824df] §Required Frontmatter. Engine refuses test-pipeline activation if any of:
- No test-spec entry referenced at activation time
- test-spec entry fails capsule v1.0 validation checks 1-12 at ERROR ratchet level
- test-spec.triggered_by_dev_cycle does not resolve to an in-flight dev-pipeline activation
- test-spec.target_substrate cross-validation against triggering dev-spec.committed_substrate NEW entries fails (Rule 3 MANDATED)

## Close-time contract

Per test-spec.capsule v1.0 Check 11 close invariants + Check 13 harness extension evidence + Check 14 manual_walk_ceiling_override valid. test-pipeline activation cannot transition status:done until:
- All behaviors_covered entries executed with pass/fail evidence in run.jsonl
- test-spec.closed_at populated
- test-spec.acceptance_evidence populated with run-jsonl UIDs + coverage-audit UIDs
- If test-spec.harness_framework_changes_required: harness_extension_landed_evidence populated
- Mike approval signal captured (per Step 5 trust_level: approval-required)

## Implementation status

| Layer | Owner | Status |
|---|---|---|
| **Pipeline substrate (this entry + 3 stages + 6 steps)** | Vela V51 | ✅ LOCKED v1.0 2026-05-23 |
| **Activation-input capsule (test-spec.capsule v1.0)** | Argus A80 + Vela V51 | ✅ LOCKED v1.0 2026-05-23 |
| **Engine coupling (pipeline-runtime extension)** | Argus A80 spec + Talos T9 implementation | Spec at [51d171f3] LOCKED; implementation at Talos T9 runway per argus-talos pair-call |
| **Engineering implementation of verification_method execution** | Talos T9 | NOT STARTED. Required surfaces: (a) machine_executable_script execution + result capture; (b) deterministic_assertion DSL evaluation per pipeline.capsule v3.0 §6 grammar; (c) structural_check validator extension dispatch; (d) agentic_review sa.* dispatch wiring (sa.skeptic / sa.cold-boot via standard commissioning protocol [e863a1e0]); (e) run.jsonl event types for test_executed + test_aggregate events; (f) close-time evidence collection writeback to test-spec. Argus engine extension [51d171f3] §How to Validate enumerates the 6 smoke tests. |
| **Phase D first instance** | v1.51 dev-pipeline activation triggers; Vela authors first test-spec; this pipeline activates against it | Pending Talos implementation; sequencing Argus's call per v1.51 cycle scope |

## What blocks Phase D ship

1. Talos T9 engineering implementation of verification_method execution surfaces (above)
2. Engine coupling implementation per [51d171f3] (pipeline-runtime extension)
3. First test-spec authored by v1.51 dev-pipeline trigger (Phase D natural test)

When Phase D fires, this pipeline gets its first activation; the activation closes clean; the v1.51 cycle dogfood-validates the three-pipeline architecture end-to-end.

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-05-23 | Initial v1.0 LOCKED authoring as Phase C of v1.51 Three-Pipeline Substrate-Engineering cycle. Root pipeline + 3 stages + 6 steps + per-step rich schema per pipeline.capsule v3.0. Composes with test-spec.capsule v1.0 [621824df] (activation-input contract; locked same session) + Pipeline-Runtime Engine Extension v0.1 [51d171f3] (engine coupling enforcement). Authored by Vela V51 per Mike-V51 'proceed with a' directive after test-spec.capsule walk + lock completed. Implementation surfaces enumerated; Talos T9 engineering implementation queued per argus-talos pair-call. | vela-v51 |

---

*test-pipeline v1.0 LOCKED | UID `da3f50dc` | 2026-05-23 | Vela V51 | Phase C of v1.51 Three-Pipeline Substrate-Engineering*
*"Anti-box-checking gate from substrate to runtime. Coverage is real because the engine refuses to close otherwise."*
