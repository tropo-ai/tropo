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
<!-- nav-block:end -->

*Stage 1 of 3. Activation-input validation + planning. Owner: Vela.*

Two leaf steps:
- **0. accept-test-spec** ([dc108622](dc108622.md)) — engine validates test-spec input against capsule v1.0; confirms triggering dev-cycle reference
- **1. plan-test-substrate** ([846a0909](846a0909.md)) — Vela authors plan substrate enumerating per-behavior test substrate path + verification_method dispatch

Stage closes when both steps at status:done. Hands off to execute stage.
