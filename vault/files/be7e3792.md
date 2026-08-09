---
uid: be7e3792
title: prepare — doc-pipeline stage
type: pipeline
subtype: workflow-node
name: prepare
version: '1.0'
author: orpheus-o11
owner: orpheus
status: active
state: active
role: stage
created: 2026-05-23
created_by: orpheus-o11
modified: 2026-05-23
modified_by: orpheus-o11
schema_version: 2
extraction_scope: ship
governed_by: e4c8a6b2
children:
  - 5f8a9072
  - 0526fa53
next_steps:
  - e51f5c9f
relationships:
  - rel: member_of
    uid: 5a4337ff
member_of:
  - 5a4337ff
tags:
  - pipeline
  - workflow-node
  - doc-pipeline
  - stage
  - prepare
---

# prepare — doc-pipeline stage

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [doc-pipeline](5a4337ff.md) → **prepare — doc-pipeline stage**
<!-- nav-block:end -->

*Stage 1 of 3. Activation-input validation + planning. Owner: Orpheus.*

Two leaf steps:
- **0. accept-doc-spec** ([5f8a9072](5f8a9072.md)) — engine validates doc-spec input against capsule v1.0 (12 checks); confirms triggering dev-cycle reference + target_subsystem resolves
- **1. plan-doc-substrate** ([0526fa53](0526fa53.md)) — Orpheus authors plan substrate enumerating per-tier doc_changes_required path + change_summary; cross-validates against triggering dev-spec NEW substrate (Check 10)

Stage closes when both steps at status:done. Hands off to execute stage.
