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

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/2e097029 — execute — test-pipeline stage.md](../../00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/2e097029%20%E2%80%94%20execute%20%E2%80%94%20test-pipeline%20stage.md)

**🌳 Tropo-Nav Path** (chat): [tropo-os-v1.84.1/00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/2e097029 — execute — test-pipeline stage.md](tropo-os-v1.84.1/00-tropo-nav/00-tropo-active/tropo-work/test-pipeline/2e097029%20%E2%80%94%20execute%20%E2%80%94%20test-pipeline%20stage.md)

**🔗 This file** — UID `2e097029` · type `pipeline` · state `active` · status `active`

**↓ Children (2):**
  - **pipeline (2):** [author-test-substrate — test-pipeline step 2](d3511487.md) · [run-test-substrate — test-pipeline step 3](05d9ecc5.md)

**↔ Siblings (2):**
  - **under [test-pipeline](da3f50dc.md):** [prepare — test-pipeline stage](69c291b7.md) · [verify-and-close — test-pipeline stage](92133de1.md)

**📥 Cited by (1):**
- [Tropo-OS v1.51.0 — Three-Pipeline Substrate-Engineering (Six A...](b0435ff0.md) — `b0435ff0` (type `release`, via `capabilities_touched`)
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [pipeline (e4c8a6b2)](e4c8a6b2.md) |
| Member of | [test-pipeline (da3f50dc)](da3f50dc.md) |

*Stage 2 of 3. Test substrate authoring + execution. Owners: Vela (substrate authoring + manual_walk + agentic_review dispatch) + Talos (engineering implementation when machine_executable_script needs runtime).*

Two leaf steps:
- **2. author-test-substrate** ([d3511487](d3511487.md)) — author test substrate for each behaviors_covered entry; new files OR extensions to existing
- **3. run-test-substrate** ([05d9ecc5](05d9ecc5.md)) — execute each behavior; capture per-behavior pass/fail; aggregate to run.jsonl

Stage closes when both steps at status:done with pass/fail evidence captured. Hands off to verify-and-close stage.
