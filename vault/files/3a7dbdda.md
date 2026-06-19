---
uid: 3a7dbdda
title: deploy — dev-pipeline stage
type: pipeline
subtype: workflow-node
name: deploy
version: 1.0.0
author: argus-a42
owner: argus
status: draft
state: active
role: stage
children:
- 804e339e
- 674af8fe
- 0cf86ea5
- 4f64ec3c
- "37996741"
- 8654900a
- bc6b17ec
- c6b61fb9
- 3e0bb81e
next_steps: []
relationships:
- rel: member_of
  uid: cd1fcd25
schema_version: 2
extraction_scope: ship
v1_51_0_amendment_note: 'Argus A80 2026-05-23 — Phase A of v1.51.0 Three-Pipeline Substrate-Engineering cycle. Deploy stage children: amendment adds 0cf86ea5 (step-4.5 trigger-doc-pipeline-activation) + 4f64ec3c (step-4.6 trigger-test-pipeline-activation) between 674af8fe (step-5.5) and 8654900a (step-6). The two new trigger steps fire in parallel after step-4 (9d4f7e21 update-subsystem-canonical-docs in build stage, but executes after step-5.5 per v1.49.0 reordered chain) and converge multi-input on step-6 (8654900a produce-release-folder). Step-4 (9d4f7e21) is structurally in build stage (3bd8f5b6) but in the v1.49.0 reordered substantive-time chain it fires after step-5.5 in deploy stage — chain visualization in §Structure below acknowledges. Three-Pipeline Substrate-Enforcement Architecture per [c3dc9f00 v0.3] + Mike-A80 trigger-timing walk 2026-05-23. Companion edits at 9d4f7e21 (next_steps fan-out) + 8654900a (multi-input convergence) + cd1fcd25 (dev-pipeline definition v1.2.0).'
member_of: []
subsystem_hub:
- 76bab75f
capsule_version: '2.5'
---

# deploy — dev-pipeline stage

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Playbooks](76bab75f.md) → **deploy — dev-pipeline stage**

**🔗 This file** — UID `3a7dbdda` · type `pipeline` · state `active` · status `draft`

**↓ Children (6):**
  - **pipeline (6):** [cold-boot-walk — dev-pipeline step 7.5](c6b61fb9.md) · [groom-subsystems — dev-pipeline step (NEW v1.7)](a5554670.md) · [notify-triggered-pipeline-owners — dev-pipeline...](37996741.md) · [pre-author-release-entry — dev-pipeline step 5.5](674af8fe.md) · [trigger-doc-pipeline-activation — dev-pipeline ...](0cf86ea5.md) · [trigger-test-pipeline-activation — dev-pipeline...](4f64ec3c.md)

**📥 Cited by (1):**
- [Tropo-OS v1.48.0 — Cycle B Extraction-and-Publish Engineering ...](1d25e142.md) — `1d25e142` (type `release`, via `capabilities_touched`)
<!-- nav-block:end -->

## Purpose

The deploy stage produces the deliverable artifact, runs it through external validation, and commits the release-marked state to git. Deploy is the terminal stage of dev-pipeline. It ends when the git commit lands and the pipeline-run closes.

Does NOT govern: the build work that produced the arch-spec artifacts (that is build stage territory), or post-ship archiving and registry updates (those happen outside the pipeline).

## Structure

```
deploy (3a7dbdda)
├── step-4: generate-release-notes (804e339e)
├── step-5: produce-release-folder (8654900a)
├── step-6: external-test (bc6b17ec)
└── step-7: git-commit (3e0bb81e)
```

Flow: step-4 → step-5 → step-6 → step-7 (linear). Step-7 is terminal.

## Nodes

| UID | Name | Role | Children | Next Steps |
|-----|------|------|----------|------------|
| [804e339e](804e339e.md) | generate-release-notes | step | 0 | [8654900a] |
| [8654900a](8654900a.md) | produce-release-folder | step | 0 | [bc6b17ec] |
| [bc6b17ec](bc6b17ec.md) | external-test | step | 0 | [3e0bb81e] |
| [3e0bb81e](3e0bb81e.md) | git-commit | step | 0 | [] |

## Flow Rules

Linear and forward-only. Each step must complete before the next begins. Step-7 (git-commit) is terminal: `next_steps: []`. When git-commit completes, the deploy stage closes, and the pipeline-run closes (this is the terminal stage of dev-pipeline).

## Cold-Boot Walk-Through

A pipeline-run enters deploy with all arch-spec artifacts complete.

Step-4 reads the closed sprint plans and arch-spec deltas and produces the release notes document. Step-5 produces the release folder structure and `.zip` artifact, registered in the Vault. Step-6 runs the `.zip` against external test execution; results are recorded on the pipeline-run. Step-7 commits the release-marked vault state to git. Pipeline-run status moves to `done` and closes.

## Known Enforcement Gaps

| Gap | What closes it | Target release | Owner |
|-----|----------------|----------------|-------|
| External test execution protocol (step-6) is not defined — no spec for what "external test" means, who runs it, or how pass/fail is recorded on the pipeline-run | Define external-test protocol as part of pipeline-run.capsule amendment in v1.4.4 or v1.5 | v1.5 | argus |

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-03 | Initial draft. Four steps: generate-release-notes, produce-release-folder, external-test, git-commit. | argus-a42 |

---

*deploy | stage WorkflowNode | dev-pipeline (cd1fcd25) | argus-a42 | 2026-05-03*
