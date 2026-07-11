---
uid: 69c291b7
title: prepare — test-pipeline stage
type: pipeline
subtype: workflow-node
name: prepare
version: '1.0'
author: vela-v51
owner: vela
status: active
state: active
role: stage
created: 2026-05-23
created_by: vela-v51
modified: 2026-05-23
modified_by: vela-v51
schema_version: 2
extraction_scope: ship
governed_by: e4c8a6b2
children:
  - dc108622
  - 846a0909
next_steps:
  - 2e097029
relationships:
  - rel: member_of
    uid: da3f50dc
member_of:
  - da3f50dc
tags:
  - pipeline
  - workflow-node
  - test-pipeline
  - stage
  - prepare
---

# prepare — test-pipeline stage

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [test-pipeline](da3f50dc.md) → **prepare — test-pipeline stage**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/69c291b7 — prepare — test-pipeline stage.md](../../00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/69c291b7%20%E2%80%94%20prepare%20%E2%80%94%20test-pipeline%20stage.md)

**🌳 Tropo-Nav Path** (chat): [tropo-os-v1.84.1/00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/69c291b7 — prepare — test-pipeline stage.md](tropo-os-v1.84.1/00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/69c291b7%20%E2%80%94%20prepare%20%E2%80%94%20test-pipeline%20stage.md)

**🔗 This file** — UID `69c291b7` · type `pipeline` · state `active` · status `active`

**↓ Children (2):**
  - **pipeline (2):** [accept-test-spec — test-pipeline step 0](dc108622.md) · [plan-test-substrate — test-pipeline step 1](846a0909.md)

**↔ Siblings (2):**
  - **under [test-pipeline](da3f50dc.md):** [execute — test-pipeline stage](2e097029.md) · [verify-and-close — test-pipeline stage](92133de1.md)

**📥 Cited by (1):**
- [Tropo-OS v1.51.0 — Three-Pipeline Substrate-Engineering (Six A...](b0435ff0.md) — `b0435ff0` (type `release`, via `capabilities_touched`)
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [pipeline (e4c8a6b2)](e4c8a6b2.md) |
| Member of | [test-pipeline (da3f50dc)](da3f50dc.md) |

*Stage 1 of 3. Activation-input validation + planning. Owner: Vela.*

Two leaf steps:
- **0. accept-test-spec** ([dc108622](dc108622.md)) — engine validates test-spec input against capsule v1.0; confirms triggering dev-cycle reference
- **1. plan-test-substrate** ([846a0909](846a0909.md)) — Vela authors plan substrate enumerating per-behavior test substrate path + verification_method dispatch

Stage closes when both steps at status:done. Hands off to execute stage.
