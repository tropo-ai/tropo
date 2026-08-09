---
uid: 2e097029
title: execute — test-pipeline stage
type: pipeline
subtype: workflow-node
name: execute
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
  - d3511487
  - 05d9ecc5
next_steps:
  - 92133de1
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
  - execute
---

# execute — test-pipeline stage

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [test-pipeline](da3f50dc.md) → **execute — test-pipeline stage**
<!-- nav-block:end -->

*Stage 2 of 3. Test substrate authoring + execution. Owners: Vela (substrate authoring + manual_walk + agentic_review dispatch) + Talos (engineering implementation when machine_executable_script needs runtime).*

Two leaf steps:
- **2. author-test-substrate** ([d3511487](d3511487.md)) — author test substrate for each behaviors_covered entry; new files OR extensions to existing
- **3. run-test-substrate** ([05d9ecc5](05d9ecc5.md)) — execute each behavior; capture per-behavior pass/fail; aggregate to run.jsonl

Stage closes when both steps at status:done with pass/fail evidence captured. Hands off to verify-and-close stage.
