---
uid: 34afcebc
title: "app-deploy-5 — UI primitives forms+layout + tagline removal"
type: project
name: "app-deploy-5"
status: done
state: archived
completed_at: 2026-05-16
final_commit: "69e0ac1"
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
    uid: 7273be51
changes_in_scope:
  - "components/ui/Wordmark.tsx"
  - "components/ui/Select.tsx"
  - "components/ui/IconButton.tsx"
  - "components/ui/Divider.tsx"
  - "components/ui/index.ts"
  - "components/Header.tsx"
  - "components/ProjectHeader.tsx"
  - "app/projects/page.tsx"
  - "lib/app-config.ts"
theme: "ui-primitives-forms-layout-plus-tagline-removal"
expected_visual_diff: "scoped — tagline removal removes 'v2.0 Research. Analyze. Publish.' from /projects and /projects/[id]; primitive callsites otherwise zero-diff"
target_branch: "main"
target_remote: "tropo-ai/tropo-ai"
live_url: null
schema_version: 2
extraction_scope: ship
file_ext: md
tags: [project, activation-root, app-deploy, app-pipeline, primitives, ui-foundation, plan-D5, tagline-removal]
board_hygiene_note: "Board-hygiene close by Metis G62 2026-05-30 per Mike-G62 cleanup directive. Verified complete/stale via read-only audit (final_commit markers / shipped evidence / stale-activation closure). Operational substrate; no writing touched."
---

# app-deploy-5 — UI primitives forms+layout + tagline removal

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [app-pipeline](2918e3b4.md) → [Tropo Platform UI Foundation Refactor](ed9a3a4e.md) → **app-deploy-5 — UI primitives forms+layout + tagline removal**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/app-deploy-5 — UI primitives forms+layout + tagline removal/34afcebc — app-deploy-5 — UI primitives forms+layout + tagline removal.md](../../00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/app-deploy-5%20%E2%80%94%20UI%20primitives%20forms%2Blayout%20%2B%20tagline%20removal/34afcebc%20%E2%80%94%20app-deploy-5%20%E2%80%94%20UI%20primitives%20forms%2Blayout%20%2B%20tagline%20removal.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/app-deploy-5 — UI primitives forms+layout + tagline removal/34afcebc — app-deploy-5 — UI primitives forms+layout + tagline removal.md](argo-os/00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/app-deploy-5%20%E2%80%94%20UI%20primitives%20forms%2Blayout%20%2B%20tagline%20removal/34afcebc%20%E2%80%94%20app-deploy-5%20%E2%80%94%20UI%20primitives%20forms%2Blayout%20%2B%20tagline%20removal.md)

**🔗 This file** — UID `34afcebc` · type `project` · state `archived` · status `done`

**↔ Siblings (43):**
  - **under [Tropo Platform UI Foundation Refactor](ed9a3a4e.md):** [app-deploy-1 — UI Foundation Step 1a + 1b](52dadffd.md) · [app-deploy-10 — Decompose app/projects/[id]/pag...](c8ab4772.md) · [app-deploy-2 — UI Foundation Step 1c-crew (swee...](f33dfb17.md) · [app-deploy-3 — Step 1c-rest + 1d retire aliases](dc0f800e.md) · [app-deploy-4 — UI primitives foundation (Panel/...](a53fc475.md) · [app-deploy-6 — Shared AppShell + Header collapse](f8c5b343.md) · + 4 more
  - **under [app-pipeline](2918e3b4.md):** [01-inbox — app-pipeline](46dfbb0a.md) · [app-deploy-1 — UI Foundation Step 1a + 1b](52dadffd.md) · [app-deploy-10 — Decompose app/projects/[id]/pag...](c8ab4772.md) · [app-deploy-11 — Minimum-viable smoke-test layer...](7f3d8c91.md) · [app-deploy-12 — eslint --fix auto-cleanup (part...](6e1f4b73.md) · [app-deploy-13 — Next.js framework migrations + ...](9b4d2e58.md) · + 27 more
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [Tropo Platform UI Foundation Refactor (ed9a3a4e)](ed9a3a4e.md) |
| Member of | [app-pipeline (2918e3b4)](2918e3b4.md) |

**Plan deliverable:** [b31e8115#D5](b31e8115.md) + bundled tagline-removal hygiene per Mike-T5 directive 2026-05-16 ("bundle a little more work")

## What ships

**Primitives authored** (`components/ui/`):
- `<Wordmark>` — the Tropo brand mark (inline SVG glyph + "tropo" lockup with accent dot)
- `<Select>` — native select wrapped in Tropo chrome (variants: `mode`, `kb`, `default`)
- `<IconButton>` — square icon-only button (authored for future use; first widespread wiring at D6/D7)
- `<Divider>` — visual separator (orientations: `vertical` for inline nav, `horizontal` for hairlines)

**Callsites wired** (`components/Header.tsx`):
- `<Wordmark>` replaces the inline SVG + text block (~15 lines compressed to 1 callsite)
- `<Select variant="kb">` replaces `<select className="mb-kbSelect">`
- `<Select variant="mode">` replaces `<select className="mb-modeSelect">`
- `<Divider />` replaces `<span className="mb-navDivider" />`

**Tagline removal**:
- `lib/app-config.ts` — `APP_LABEL` constant deleted (the legacy "Research. Analyze. Publish." tagline)
- `app/projects/page.tsx` — `APP_LABEL` import removed; `<span className="mb-brandSub">` deleted
- `components/ProjectHeader.tsx` — same removal pattern
- `components/Header.tsx` — unused `APP_LABEL` import cleaned up

## Verification

- `npx tsc --noEmit` clean
- `npm run build` ✓ Compiled successfully
- 4/4 routes HTTP 200 (dev server, hot-reloaded)
- `/projects` curl shows zero matches for "Research" / "ANALYZE" / "PUBLISH" — tagline confirmed gone
