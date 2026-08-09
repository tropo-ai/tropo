---
uid: 92133de1
title: verify-and-close — test-pipeline stage
type: pipeline
subtype: workflow-node
name: verify-and-close
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
  - a69fcab3
  - 047c147c
next_steps: []
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
  - verify-and-close
---

# verify-and-close — test-pipeline stage

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [test-pipeline](da3f50dc.md) → **verify-and-close — test-pipeline stage**
<!-- nav-block:end -->

*Stage 3 of 3. Anti-box-checking gate + close-activation back-feed. Owner: Vela (anti-box-checking gate is mine per test-spec.capsule v1.0 walk lock).*

Two leaf steps:
- **4. validate-coverage** ([a69fcab3](a69fcab3.md)) — all 14 test-spec capsule validation checks pass at ERROR ratchet level; manual_walk ceiling honored; per-cycle-class minima met
- **5. close-activation** ([047c147c](047c147c.md)) — set test-spec closed_at + acceptance_evidence; pipeline-run status:done; back-feed dev-pipeline activation gate; Mike approval signal captured

Stage closes when both steps at status:done. This is the terminal stage of the pipeline; close back-feeds into triggering dev-pipeline's activation gate per Pipeline-Runtime Engine Extension v0.1 [51d171f3] §Three-Pipeline Coupling State Machine.
