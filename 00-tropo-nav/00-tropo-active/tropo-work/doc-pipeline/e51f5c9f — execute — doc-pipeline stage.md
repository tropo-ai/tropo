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

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/tropo-work/doc-pipeline/e51f5c9f — execute — doc-pipeline stage.md](../../00-tropo-nav/00-tropo-active/tropo-work/doc-pipeline/e51f5c9f%20%E2%80%94%20execute%20%E2%80%94%20doc-pipeline%20stage.md)

**🌳 Tropo-Nav Path** (chat): [tropo-os-v1.84.1/00-tropo-nav/00-tropo-active/tropo-work/doc-pipeline/e51f5c9f — execute — doc-pipeline stage.md](tropo-os-v1.84.1/00-tropo-nav/00-tropo-active/tropo-work/doc-pipeline/e51f5c9f%20%E2%80%94%20execute%20%E2%80%94%20doc-pipeline%20stage.md)

**🔗 This file** — UID `e51f5c9f` · type `pipeline` · state `active` · status `active`

**↓ Children (2):**
  - **pipeline (2):** [author-doc-substrate — doc-pipeline step 2](408eda13.md) · [voice-review-substrate — doc-pipeline step 3](79c6479c.md)

**↔ Siblings (2):**
  - **under [doc-pipeline](5a4337ff.md):** [prepare — doc-pipeline stage](be7e3792.md) · [verify-and-close — doc-pipeline stage](5f8be017.md)
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [pipeline (e4c8a6b2)](e4c8a6b2.md) |
| Member of | [doc-pipeline (5a4337ff)](5a4337ff.md) |

*Stage 2 of 3. Substrate authoring + voice review. Owner: Orpheus (substrate) + Talos (engineering when machine-author needed).*

Two leaf steps:
- **2. author-doc-substrate** ([408eda13](408eda13.md)) — Orpheus authors or amends doc files per plan; new files OR extensions to existing; nav-block rendered post-touch via generate-relations-header.py; Talos engineering when machine-authored generation needed
- **3. voice-review-substrate** ([79c6479c](79c6479c.md)) — Orpheus dispatches voice review (per voice-review.skill.md three layers: tone consistency + lore alignment + stranger-encounter test) on tiers where voice_review_required:true (default summary + subsystem); spec-tier self-spot-check on prose-heavy sections per doc-spec.capsule §Tier 3 procedural note

Stage closes when both steps at status:done. Hands off to verify-and-close stage.
