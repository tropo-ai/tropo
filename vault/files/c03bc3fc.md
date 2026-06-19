---
uid: c03bc3fc
title: "app-deploy-9 — Decompose app/crew/page.tsx via components/crew/*"
type: project
name: "app-deploy-9"
status: done
state: archived
completed_at: 2026-05-16
final_commit: "bad3947"
owner: talos-t5
created: 2026-05-16
modified: 2026-05-30
created_by: talos-t5
modified_by: metis-g62
member_of:
  - "ed9a3a4e"
  - "2918e3b4"
relationships:
  - rel: member_of
    uid: 2918e3b4
  - rel: refs
    uid: b31e8115
  - rel: refs
    uid: 7b6c8cb7
changes_in_scope:
  - "app/crew/page.tsx"
  - "components/crew/Badges.tsx"
  - "components/crew/ThreadsView.tsx"
  - "components/crew/ProjectsView.tsx"
  - "components/crew/BoardsView.tsx"
  - "components/crew/CommandCenterView.tsx"
theme: "decompose-crew-page-via-sub-components"
expected_visual_diff: "zero — pure code-org refactor; same components rendered, same DOM tree, same fetches"
target_branch: "main"
target_remote: "tropo-ai/tropo-ai"
live_url: null
schema_version: 2
extraction_scope: ship
file_ext: md
tags: [project, activation-root, app-deploy, app-pipeline, decomposition, plan-D9, final-plan-deliverable]
board_hygiene_note: "Board-hygiene close by Metis G62 2026-05-30 per Mike-G62 cleanup directive. Verified complete/stale via read-only audit (final_commit markers / shipped evidence / stale-activation closure). Operational substrate; no writing touched."
---

# app-deploy-9 — Decompose crew page

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [app-pipeline](2918e3b4.md) → [Tropo Platform UI Foundation Refactor](ed9a3a4e.md) → **app-deploy-9 — Decompose app/crew/page.tsx via components...**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/Tropo Platform UI Foundation Refactor/app-deploy-9 — Decompose app-crew-page.tsx via components-crew--/c03bc3fc — app-deploy-9 — Decompose app-crew-page.tsx via components-crew--.md](../../00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/Tropo%20Platform%20UI%20Foundation%20Refactor/app-deploy-9%20%E2%80%94%20Decompose%20app-crew-page.tsx%20via%20components-crew--/c03bc3fc%20%E2%80%94%20app-deploy-9%20%E2%80%94%20Decompose%20app-crew-page.tsx%20via%20components-crew--.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/Tropo Platform UI Foundation Refactor/app-deploy-9 — Decompose app-crew-page.tsx via components-crew--/c03bc3fc — app-deploy-9 — Decompose app-crew-page.tsx via components-crew--.md](argo-os/00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/Tropo%20Platform%20UI%20Foundation%20Refactor/app-deploy-9%20%E2%80%94%20Decompose%20app-crew-page.tsx%20via%20components-crew--/c03bc3fc%20%E2%80%94%20app-deploy-9%20%E2%80%94%20Decompose%20app-crew-page.tsx%20via%20components-crew--.md)

**🔗 This file** — UID `c03bc3fc` · type `project` · state `archived` · status `done`

**↔ Siblings (43):**
  - **under [Tropo Platform UI Foundation Refactor](ed9a3a4e.md):** [app-deploy-1 — UI Foundation Step 1a + 1b](52dadffd.md) · [app-deploy-10 — Decompose app/projects/[id]/pag...](c8ab4772.md) · [app-deploy-2 — UI Foundation Step 1c-crew (swee...](f33dfb17.md) · [app-deploy-3 — Step 1c-rest + 1d retire aliases](dc0f800e.md) · [app-deploy-4 — UI primitives foundation (Panel/...](a53fc475.md) · [app-deploy-5 — UI primitives forms+layout + tag...](34afcebc.md) · + 4 more
  - **under [app-pipeline](2918e3b4.md):** [01-inbox — app-pipeline](46dfbb0a.md) · [app-deploy-1 — UI Foundation Step 1a + 1b](52dadffd.md) · [app-deploy-10 — Decompose app/projects/[id]/pag...](c8ab4772.md) · [app-deploy-11 — Minimum-viable smoke-test layer...](7f3d8c91.md) · [app-deploy-12 — eslint --fix auto-cleanup (part...](6e1f4b73.md) · [app-deploy-13 — Next.js framework migrations + ...](9b4d2e58.md) · + 27 more
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [Tropo Platform UI Foundation Refactor (ed9a3a4e)](ed9a3a4e.md) |
| Member of | [app-pipeline (2918e3b4)](2918e3b4.md) |

**Plan deliverable:** [b31e8115#D9](b31e8115.md) — **final deploy in the plan.**

## What ships

`app/crew/page.tsx` shrinks from **999 → 172 lines** (83% reduction) by extracting 18 inline sub-components into 5 focused component files at `components/crew/`.

**New files:**
- `components/crew/Badges.tsx` (87 lines) — StatusBadge, TierBadge, TaskStatusBadge, ProjectStatusBadge, RelativeTime, TagList (atomic display widgets shared across views)
- `components/crew/ThreadsView.tsx` (248 lines) — ThreadCard, ThreadColumn, ThreadPanel, ThreadsView (Tier 1/2/3 three-column grid + detail panel)
- `components/crew/ProjectsView.tsx` (243 lines) — ProjectCard, ProjectDetailPanel, ProjectsView (top-level + nested project tree + detail panel with tasks-by-status)
- `components/crew/BoardsView.tsx` (216 lines) — BoardCard, BoardDetailPanel, BoardsView (published + internal sections + detail panel)
- `components/crew/CommandCenterView.tsx` (44 lines) — pinned-tasks view

**Modified:**
- `app/crew/page.tsx` — now a thin orchestrator (172 lines): owns dashboard fetch + tab navigation state + detail-panel slot management. TabButton stays inline (12 lines, tightly coupled to the page's TabId type + handleTabChange). Renders the four views + three detail panels with backdrops.

## Acceptance

- `app/crew/page.tsx` ≤ 400 lines: **172** ✓ (target 400; achieved 43%)
- typecheck clean (`npx tsc --noEmit` exit 0)
- `npm run build` ✓ Compiled successfully
- 4/4 routes HTTP 200
- Behaviorally identical — pure code-org refactor

## Notes

This is the smallest D-deploy in Phase 3 in code volume (no extracted hook; pure component extraction). The crew page wasn't tangled like `/` and `/projects/[id]` were — just had a lot of inline sub-components stacked in one file. Now each tab's components live in their own file; the page assembles them.

The `--arctic` references (in ProjectsView and BoardsView) survive untouched per the pre-existing-broken-token note ([53a7a624](53a7a624.md)) — not in this run's scope.
