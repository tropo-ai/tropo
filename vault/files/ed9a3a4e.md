---
uid: ed9a3a4e
title: "Tropo Platform UI Foundation Refactor"
type: project
name: "tropo-ui-foundation-refactor"
status: done
state: archived
owner: talos
created: 2026-05-16
modified: 2026-05-30
created_by: talos-t5
modified_by: metis-g62
member_of:
  - "2918e3b4"   # app-pipeline
scoped_by:
  - "b31e8115"   # the project-plan
relationships:
  - rel: member_of
    uid: 2918e3b4
  - rel: refs
    uid: d05ed9ba   # design brief
schema_version: 2
extraction_scope: ship
file_ext: md
tags: [project, ui-foundation, refactor, app-pipeline, multi-deploy]
board_hygiene_note: "Board-hygiene close by Metis G62 2026-05-30 per Mike-G62 cleanup directive. Verified complete/stale via read-only audit (final_commit markers / shipped evidence / stale-activation closure). Operational substrate; no writing touched."
---

# Tropo Platform UI Foundation Refactor

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [app-pipeline](2918e3b4.md) → **Tropo Platform UI Foundation Refactor**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/Tropo Platform UI Foundation Refactor/ed9a3a4e — Tropo Platform UI Foundation Refactor.md](../../00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/Tropo%20Platform%20UI%20Foundation%20Refactor/ed9a3a4e%20%E2%80%94%20Tropo%20Platform%20UI%20Foundation%20Refactor.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/Tropo Platform UI Foundation Refactor/ed9a3a4e — Tropo Platform UI Foundation Refactor.md](argo-os/00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/Tropo%20Platform%20UI%20Foundation%20Refactor/ed9a3a4e%20%E2%80%94%20Tropo%20Platform%20UI%20Foundation%20Refactor.md)

**🔗 This file** — UID `ed9a3a4e` · type `project` · state `archived` · status `done`

**↓ Children (11):**
  - **project (10):** [app-deploy-1 — UI Foundation Step 1a + 1b](52dadffd.md) · [app-deploy-10 — Decompose app/projects/[id]/pag...](c8ab4772.md) · [app-deploy-2 — UI Foundation Step 1c-crew (swee...](f33dfb17.md) · [app-deploy-3 — Step 1c-rest + 1d retire aliases](dc0f800e.md) · [app-deploy-4 — UI primitives foundation (Panel/...](a53fc475.md) · [app-deploy-5 — UI primitives forms+layout + tag...](34afcebc.md) · [app-deploy-6 — Shared AppShell + Header collapse](f8c5b343.md) · [app-deploy-7 — Brand sweep Mo → Tropo + wordmar...](5772556c.md) · + 2 more
  - **project-plan:** [Tropo Platform UI Foundation Refactor — Project...](b31e8115.md)

**↔ Siblings (33):**
  - **under [app-pipeline](2918e3b4.md):** [01-inbox — app-pipeline](46dfbb0a.md) · [app-deploy-1 — UI Foundation Step 1a + 1b](52dadffd.md) · [app-deploy-10 — Decompose app/projects/[id]/pag...](c8ab4772.md) · [app-deploy-11 — Minimum-viable smoke-test layer...](7f3d8c91.md) · [app-deploy-12 — eslint --fix auto-cleanup (part...](6e1f4b73.md) · [app-deploy-13 — Next.js framework migrations + ...](9b4d2e58.md) · + 27 more
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [app-pipeline (2918e3b4)](2918e3b4.md) |

## Purpose

Top-level project for the Tropo platform UI foundation refactor work. Encompasses ~6-8 `app-deploy-N` runs spanning token consolidation, primitives layer, shared shell, brand sweep, and big-file decomposition.

This project is the **graph parent** for every activation-root project created by deploys under this initiative. Each `app-deploy-N` activation-root becomes a child of this project.

Scoped by [Project Plan (b31e8115)](b31e8115.md). See the plan for deliverables, dependencies, verification, and phasing.

## Members (deploy activation-roots)

- [app-deploy-1 (52dadffd)](52dadffd.md) — Step 1a + 1b token consolidation ✅ done
- [app-deploy-2 (f33dfb17)](f33dfb17.md) — Step 1c-crew sweep ✅ done
- Future: app-deploy-3, 4, 5, … per the project plan

---

*Tropo Platform UI Foundation Refactor | active | scoped by b31e8115*
