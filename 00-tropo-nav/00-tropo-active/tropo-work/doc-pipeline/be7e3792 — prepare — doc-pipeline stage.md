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

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/tropo-work/doc-pipeline/be7e3792 — prepare — doc-pipeline stage.md](../../00-tropo-nav/00-tropo-active/tropo-work/doc-pipeline/be7e3792%20%E2%80%94%20prepare%20%E2%80%94%20doc-pipeline%20stage.md)

**🌳 Tropo-Nav Path** (chat): [tropo-os-v1.84.1/00-tropo-nav/00-tropo-active/tropo-work/doc-pipeline/be7e3792 — prepare — doc-pipeline stage.md](tropo-os-v1.84.1/00-tropo-nav/00-tropo-active/tropo-work/doc-pipeline/be7e3792%20%E2%80%94%20prepare%20%E2%80%94%20doc-pipeline%20stage.md)

**🔗 This file** — UID `be7e3792` · type `pipeline` · state `active` · status `active`

**↓ Children (2):**
  - **pipeline (2):** [accept-doc-spec — doc-pipeline step 0](5f8a9072.md) · [plan-doc-substrate — doc-pipeline step 1](0526fa53.md)

**↔ Siblings (2):**
  - **under [doc-pipeline](5a4337ff.md):** [execute — doc-pipeline stage](e51f5c9f.md) · [verify-and-close — doc-pipeline stage](5f8be017.md)
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [pipeline (e4c8a6b2)](e4c8a6b2.md) |
| Member of | [doc-pipeline (5a4337ff)](5a4337ff.md) |

*Stage 1 of 3. Activation-input validation + planning. Owner: Orpheus.*

Two leaf steps:
- **0. accept-doc-spec** ([5f8a9072](5f8a9072.md)) — engine validates doc-spec input against capsule v1.0 (12 checks); confirms triggering dev-cycle reference + target_subsystem resolves
- **1. plan-doc-substrate** ([0526fa53](0526fa53.md)) — Orpheus authors plan substrate enumerating per-tier doc_changes_required path + change_summary; cross-validates against triggering dev-spec NEW substrate (Check 10)

Stage closes when both steps at status:done. Hands off to execute stage.
