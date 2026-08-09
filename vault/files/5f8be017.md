---
uid: 5f8be017
title: verify-and-close — doc-pipeline stage
type: pipeline
subtype: workflow-node
name: verify-and-close
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
  - 3ee9f8f9
  - 343dd5d8
next_steps: []
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
  - verify-and-close
  - terminal-stage
---

# verify-and-close — doc-pipeline stage

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [doc-pipeline](5a4337ff.md) → **verify-and-close — doc-pipeline stage**
<!-- nav-block:end -->

*Stage 3 of 3. Anti-aspiration gate + activation close. Owner: Orpheus (substrate verification) + Talos (machine_executable_script for nav-block render diff per Step 4(c)).*

Two leaf steps:
- **4. validate-cross-references** ([3ee9f8f9](3ee9f8f9.md)) — Validation Check 9 EXTENDED: (a) body-prose UID resolution; (b) member_of frontmatter resolution; (c) nav-block render-clean post-touch. Per-tier rigor split: Tier 1 light; Tier 2 strict-on-members medium-on-adjacency; Tier 3 strict + render-verify
- **5. close-activation** ([343dd5d8](343dd5d8.md)) — Orpheus sets doc-spec closed_at + acceptance_evidence (voice-review-notes UIDs from Step 3 + cross-reference audit UID from Step 4); pipeline-run status:done; back-feeds dev-pipeline activation gate (parallel-DAG with test-pipeline; both must close before dev-pipeline step 6 produce-release-folder can fire)

Terminal stage. Pipeline closes when both steps at status:done.
