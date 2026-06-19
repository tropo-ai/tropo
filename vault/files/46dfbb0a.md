---
uid: 46dfbb0a
title: "01-inbox — app-pipeline"
type: project
name: "01-inbox"
status: active
state: active
owner: talos
created: 2026-05-16
modified: 2026-05-16
created_by: talos-t5
modified_by: talos-t5
member_of:
  - "2918e3b4"   # app-pipeline
schema_version: 2
extraction_scope: ship
file_ext: md
tags: [project, inbox, app-pipeline, composable-inbox]
lifecycle: standing
---
# 01-inbox — app-pipeline

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [app-pipeline](2918e3b4.md) → **01-inbox — app-pipeline**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/tropo-work/app-pipeline/app-pipeline-01-inbox — app-pipeline/46dfbb0a — 01-inbox — app-pipeline.md](../../00-tropo-nav/00-tropo-active/tropo-work/app-pipeline/app-pipeline-01-inbox%20%E2%80%94%20app-pipeline/46dfbb0a%20%E2%80%94%2001-inbox%20%E2%80%94%20app-pipeline.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-active/tropo-work/app-pipeline/app-pipeline-01-inbox — app-pipeline/46dfbb0a — 01-inbox — app-pipeline.md](argo-os/00-tropo-nav/00-tropo-active/tropo-work/app-pipeline/app-pipeline-01-inbox%20%E2%80%94%20app-pipeline/46dfbb0a%20%E2%80%94%2001-inbox%20%E2%80%94%20app-pipeline.md)

**🔗 This file** — UID `46dfbb0a` · type `project` · state `active` · status `active`

**↓ Children (6):**
  - **design-brief (2):** [Machines as Substrate — Capsule Lifecycle Decla...](12ccd1a8.md) · [The Work-Item Detail Screen — Governed Edit, In...](d7b3f1a9.md)
  - **note (4):** [184 pre-existing eslint errors block npm test g...](5e3a82c1.md) · [KB source viewer doesn't resolve bundle-native ...](d4e20de3.md) · [Possible light-mode rescue needed for .tropo-bu...](41ce6dc2.md) · [Tropo agent sessions within L2 — load registere...](a7e2f4c1.md)

**↔ Siblings (33):**
  - **under [app-pipeline](2918e3b4.md):** [app-deploy-1 — UI Foundation Step 1a + 1b](52dadffd.md) · [app-deploy-10 — Decompose app/projects/[id]/pag...](c8ab4772.md) · [app-deploy-11 — Minimum-viable smoke-test layer...](7f3d8c91.md) · [app-deploy-12 — eslint --fix auto-cleanup (part...](6e1f4b73.md) · [app-deploy-13 — Next.js framework migrations + ...](9b4d2e58.md) · [app-deploy-14 — no-explicit-any sweep in script...](2c8d1f47.md) · + 27 more
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [app-pipeline (2918e3b4)](2918e3b4.md) |

## Purpose

The inbox for app-pipeline. Pre-cycle candidates for the Tropo platform app land here as notes, design briefs, or work-items before getting picked into a per-deploy pipeline-run. Composable-inbox pattern: items here roll up to the Studio-root `01-vault-inbox/` for cross-pipeline visibility.

## What Belongs Here

- **Refactor proposals** for the platform app — design briefs (e.g., the UI foundation refactor brief `d05ed9ba`).
- **Feature ideas** for the platform that aren't yet scoped into a deploy.
- **Architectural concerns** found while reading the codebase — substrate observations, dependency-graph oddities, accumulated debt.
- **Defects and follow-ups** found in the platform app that aren't blocking enough to fire an out-of-cycle deploy.
- **Notes about deploy targets, hosting, build tooling** — anything that informs platform deploys but doesn't belong inside an active run.

## What Does Not Belong Here

- In-flight deploy work (lives under the active deploy's activation-root project, not here).
- Website work (lives in web-pipeline 01-inbox at [b39e7d54](b39e7d54.md)).
- Studio governance work (lives in dev-pipeline's 01-inbox; will be `studio-pipeline` later).
- Marketing strategy or content authoring (those live in MOS and the website-pipeline surfaces; the platform app consumes them but doesn't author them).

## Lifecycle

Items arrive as `type: note`, `type: design-brief`, or `type: task` with `member_of: [46dfbb0a]`. When Mike or Talos picks an item into a deploy, it gets referenced from the activation-root project of that pipeline-run (`refs:` or `member_of:` extended). Once shipped, the inbox item can be archived (`state: archived`) or referenced as historical context.

Aggressive archive bias: ideas that sit unused for a cycle don't need defensive preservation — if the problem resurfaces, the idea will too.

## Current Inbox Items

- **[Tropo Platform UI Foundation Refactor — Design Brief (d05ed9ba)](d05ed9ba.md)** — Five-step refactor: token consolidation, primitives layer, shared shell, brand sweep, page decomposition. Status: `design`. Authored 2026-05-16 by Talos T5. First filed in web-pipeline 01-inbox before app-pipeline existed; should be re-parented here for canonical home. **Re-parent action: change brief's `member_of:` from `[b39e7d54, 7b2e94c1]` to `[46dfbb0a, 2918e3b4]` once app-pipeline ships.**

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-16 | Initial draft. Authored as part of app-pipeline v1.0.0 construction at Mike's direction; mirrors web-pipeline 01-inbox structure. | talos-t5 |

---

*01-inbox | app-pipeline | composable inbox | rolls up to 01-vault-inbox*
