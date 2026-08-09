---
uid: e51f5c9f
title: execute — doc-pipeline stage
type: pipeline
subtype: workflow-node
name: execute
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
  - 408eda13
  - 79c6479c
next_steps:
  - 5f8be017
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
  - execute
---

# execute — doc-pipeline stage

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [doc-pipeline](5a4337ff.md) → **execute — doc-pipeline stage**
<!-- nav-block:end -->

*Stage 2 of 3. Substrate authoring + voice review. Owner: Orpheus (substrate) + Talos (engineering when machine-author needed).*

Two leaf steps:
- **2. author-doc-substrate** ([408eda13](408eda13.md)) — Orpheus authors or amends doc files per plan; new files OR extensions to existing; nav-block rendered post-touch via generate-relations-header.py; Talos engineering when machine-authored generation needed
- **3. voice-review-substrate** ([79c6479c](79c6479c.md)) — Orpheus dispatches voice review (per voice-review.skill.md three layers: tone consistency + lore alignment + stranger-encounter test) on tiers where voice_review_required:true (default summary + subsystem); spec-tier self-spot-check on prose-heavy sections per doc-spec.capsule §Tier 3 procedural note

Stage closes when both steps at status:done. Hands off to verify-and-close stage.
