---
uid: 76cf302e
title: specify — app-pipeline stage
type: pipeline
subtype: workflow-node
name: specify
version: 1.0.0
author: talos-t5
owner: talos
status: draft
state: active
role: stage
created: 2026-05-16
modified: 2026-05-16
created_by: talos-t5
modified_by: talos-t5
children:
  - ea9e9f61
next_steps:
  - 5e865a88
member_of:
  - 2918e3b4
relationships:
  - rel: member_of
    uid: 2918e3b4
  - rel: governed_by
    uid: e4c8a6b2
schema_version: 2
extraction_scope: ship
file_ext: md
tags:
  - pipeline
  - app-pipeline
  - stage
  - specify
---

# specify — app-pipeline stage

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [app-pipeline](2918e3b4.md) → **specify — app-pipeline stage**
<!-- nav-block:end -->

## Purpose

The specify stage of app-pipeline. Accepts the human-issued deploy request for the Tropo platform app, authors the activation-root project per pipeline.capsule Rule 10, and pauses for Mike to confirm the deploy number + theme + files/features-in-scope before any build work begins.

**Does NOT govern:** the implementation itself (build stage); the commit and push (deploy stage); design or research that happens pre-pipeline (those produce the scope, they don't run inside it).

## Structure

```
specify (76cf302e)
└── step-0: accept-deploy-request (ea9e9f61) — requires_confirmation: true
```

One leaf step. Linear, forward-only. Specify completes when the activation-root project is committed and Mike has confirmed the deploy number, theme, and scope; next_steps points to the build stage.

## Nodes

| UID | Name | Role | Children | Next Steps |
|-----|------|------|----------|------------|
| [ea9e9f61](ea9e9f61.md) | accept-deploy-request | step | 0 | [] (terminal in stage; flow advances to build) |

## Flow Rules

Linear. step-0 is the only step in this stage. On completion, stage advances to build. step-0 declares `requires_confirmation: true` — pipeline-run pauses on entry until Mike confirms the proposed deploy number, theme, and scope.

## Cold-Boot Walk-Through

Mike says "run app-pipeline as app-deploy-1, theme: 'ui-foundation-step-1a-1b', scope: app/styles/tropo-tokens.css + app/globals.css." Pipeline-run starts. Specify stage opens. Executor enters step-0 (accept-deploy-request). Per `requires_confirmation: true`, the run pauses on entry with a `pause_started` event in run.jsonl naming the proposed deploy number, theme, and files in scope. Mike confirms (or redirects); run resumes. Step-0 work executes: activation-root project (`app-deploy-1`) authored as `type: project, status: active, state: standing` per pipeline.capsule Rule 10. Project becomes the graph parent for all downstream artifacts the run produces. Step-0 closes; specify stage's next_steps fires; flow advances to build.

## Known Enforcement Gaps

| Gap | What closes it | Target release | Owner |
|-----|----------------|----------------|-------|
| Confirmation-pause UX — currently `requires_confirmation: true` is honored by pipeline-run.capsule v1.1+; app-pipeline-specific message-on-pause format unspecified | Step body documents the message format for v1.0; executor module formalizes v1.1+ | v1.0.0 | talos |

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-16 | Initial draft. Authored as part of app-pipeline v1.0.0 construction at Mike's direction; mirrors web-pipeline specify stage v1.0.0. | talos-t5 |

---

*specify | app-pipeline stage | pipeline.capsule v2.5 | Authored 2026-05-16 by Talos T5*
