---
uid: 52dadffd
title: "app-deploy-1 — UI Foundation Step 1a + 1b"
type: project
name: "app-deploy-1"
status: done
state: archived
completed_at: 2026-05-16
final_commit: "369716a"
owner: talos-t5
created: 2026-05-16
modified: 2026-05-30
created_by: talos-t5
modified_by: metis-g62
member_of:
  - "ed9a3a4e"   # Tropo Platform UI Foundation Refactor (top-level project; added 2026-05-16 by project plan b31e8115)
  - "2918e3b4"   # app-pipeline
relationships:
  - rel: member_of
    uid: 2918e3b4   # app-pipeline
  - rel: refs
    uid: d05ed9ba   # informing design brief
  - rel: refs
    uid: f5cf7de7   # pipeline-run
changes_in_scope:
  - "app/styles/tropo-tokens.css"
  - "app/globals.css"
theme: "ui-foundation-step-1a-1b-token-consolidation"
expected_visual_diff: "zero"
target_branch: "main"
target_remote: "tropo-ai/tropo-ai"
live_url: null   # platform app has no public deploy target at v1.0.0; smoke-test runs Local mode
schema_version: 2
extraction_scope: ship
file_ext: md
tags: [project, activation-root, app-deploy, app-pipeline, refactor, ui-foundation]
board_hygiene_note: "Board-hygiene close by Metis G62 2026-05-30 per Mike-G62 cleanup directive. Verified complete/stale via read-only audit (final_commit markers / shipped evidence / stale-activation closure). Operational substrate; no writing touched."
---

# app-deploy-1 — UI Foundation Step 1a + 1b

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [app-pipeline](2918e3b4.md) → [Tropo Platform UI Foundation Refactor](ed9a3a4e.md) → **app-deploy-1 — UI Foundation Step 1a + 1b**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/app-deploy-1 — UI Foundation Step 1a + 1b/52dadffd — app-deploy-1 — UI Foundation Step 1a + 1b.md](../../00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/app-deploy-1%20%E2%80%94%20UI%20Foundation%20Step%201a%20%2B%201b/52dadffd%20%E2%80%94%20app-deploy-1%20%E2%80%94%20UI%20Foundation%20Step%201a%20%2B%201b.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/app-deploy-1 — UI Foundation Step 1a + 1b/52dadffd — app-deploy-1 — UI Foundation Step 1a + 1b.md](argo-os/00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/app-deploy-1%20%E2%80%94%20UI%20Foundation%20Step%201a%20%2B%201b/52dadffd%20%E2%80%94%20app-deploy-1%20%E2%80%94%20UI%20Foundation%20Step%201a%20%2B%201b.md)

**🔗 This file** — UID `52dadffd` · type `project` · state `archived` · status `done`

**↔ Siblings (43):**
  - **under [Tropo Platform UI Foundation Refactor](ed9a3a4e.md):** [app-deploy-10 — Decompose app/projects/[id]/pag...](c8ab4772.md) · [app-deploy-2 — UI Foundation Step 1c-crew (swee...](f33dfb17.md) · [app-deploy-3 — Step 1c-rest + 1d retire aliases](dc0f800e.md) · [app-deploy-4 — UI primitives foundation (Panel/...](a53fc475.md) · [app-deploy-5 — UI primitives forms+layout + tag...](34afcebc.md) · [app-deploy-6 — Shared AppShell + Header collapse](f8c5b343.md) · + 4 more
  - **under [app-pipeline](2918e3b4.md):** [01-inbox — app-pipeline](46dfbb0a.md) · [app-deploy-10 — Decompose app/projects/[id]/pag...](c8ab4772.md) · [app-deploy-11 — Minimum-viable smoke-test layer...](7f3d8c91.md) · [app-deploy-12 — eslint --fix auto-cleanup (part...](6e1f4b73.md) · [app-deploy-13 — Next.js framework migrations + ...](9b4d2e58.md) · [app-deploy-14 — no-explicit-any sweep in script...](2c8d1f47.md) · + 27 more
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [Tropo Platform UI Foundation Refactor (ed9a3a4e)](ed9a3a4e.md) |
| Member of | [app-pipeline (2918e3b4)](2918e3b4.md) |

## Purpose

Activation-root project for `app-deploy-1`, the first run of `app-pipeline`. Ships **Step 1a + 1b** of the UI Foundation Refactor: extend `app/styles/tropo-tokens.css` to coverage parity with the legacy token set, then alias the legacy `--accent`/`--bg0`/`--panel`/etc. names in `app/globals.css` to the new `--tropo-*` system.

**Expected visual diff: zero.** Every existing legacy-token reference (e.g., `var(--accent)`) resolves through the new system after this run. No component, page, or CSS class is modified. The visible behavior of the platform app is identical before and after.

This project is the graph parent for all artifacts the deploy produces: per-deploy notes, alias-mapping documentation, baseline screenshots (if captured), the commit + push trail.

## Scope

- `app/styles/tropo-tokens.css` — add tokens for coverage parity with legacy: `--tropo-bg-deep`, `--tropo-bg-soft`, `--tropo-surface-glass`, `--tropo-surface-glass-soft`, `--tropo-hairline-translucent`, `--tropo-border-glow`, `--tropo-shadow`, `--tropo-panel-shadow`, `--tropo-panel-shadow-hover`, `--tropo-panel-shadow-accent`, `--tropo-ring`, `--tropo-radius-xl`, `--tropo-radius-lg-10`.
- `app/globals.css` — replace the legacy `:root` and `html.dark` token definition blocks (lines ~25-107) with alias definitions pointing at the new `--tropo-*` tokens.

## Out of scope

- Class-name renames (`.mb-*`, `.ma-*`, `.crew-*` stay as-is — Step 2 / Step 4)
- Component or page edits
- Visual changes of any kind
- Files outside `app/styles/tropo-tokens.css` and `app/globals.css`

## Verification commitment

- `npx tsc --noEmit` clean
- `npm run build` clean
- Production preview (`npm start`) renders all 5 routes without visual diff against pre-change baseline
- `grep -c 'var(--accent\|var(--bg0\|var(--panel\b\|var(--text\b\|var(--muted\|var(--border\b)' <app components lib>` returns same count before and after (the legacy names still exist; they now resolve via aliases)

## Lifecycle

- 2026-05-16 — Created at step-0 (post Mike-confirmation). State: `standing`.
- On smoke-test completion: state flips to `done`. Project becomes historical record.

---

*app-deploy-1 — activation-root project | first run of app-pipeline | pipeline-run.capsule v1.4*
