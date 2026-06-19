---
uid: d05ed9ba
title: "Tropo Platform UI Foundation Refactor — Design Brief"
type: design-brief
description: "Five-step refactor consolidating Tropo platform UI: tokens, primitives, shared shell, brand sweep, page decomposition."
author: talos-t5
status: done
state: archived
created: 2026-05-16
modified: 2026-05-30
created_by: talos-t5
modified_by: metis-g62
requested_by: mike
member_of:
  - "2918e3b4"   # app-pipeline
relationships:
  - rel: refs
    uid: 2c8e93f1   # tropo-ai.com Launch Foundations (the project this codebase shipped under)
  - rel: refs
    uid: 2918e3b4   # app-pipeline (governing pipeline)
  - rel: refs
    uid: 7b2e94c1   # web-pipeline (original filing location before app-pipeline existed)
schema_version: 2
extraction_scope: ship
file_ext: md
composes_into:
  - "b31e8115"   # Project plan derived from this brief
tags: [design-brief, web-pipeline, tropo-platform, ui, refactor, design-system, foundation, captain-mode]
board_hygiene_note: "Board-hygiene close by Metis G62 2026-05-30 per Mike-G62 cleanup directive. Verified complete/stale via read-only audit (final_commit markers / shipped evidence / stale-activation closure). Operational substrate; no writing touched."
---

# Tropo Platform UI Foundation Refactor — Design Brief

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [app-pipeline](2918e3b4.md) → **Tropo Platform UI Foundation Refactor — Design Brief**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/d05ed9ba — Tropo Platform UI Foundation Refactor — Design Brief.md](../../00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/d05ed9ba%20%E2%80%94%20Tropo%20Platform%20UI%20Foundation%20Refactor%20%E2%80%94%20Design%20Brief.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/d05ed9ba — Tropo Platform UI Foundation Refactor — Design Brief.md](argo-os/00-tropo-nav/00-tropo-all/tropo-work/app-pipeline/d05ed9ba%20%E2%80%94%20Tropo%20Platform%20UI%20Foundation%20Refactor%20%E2%80%94%20Design%20Brief.md)

**🔗 This file** — UID `d05ed9ba` · type `design-brief` · state `archived` · status `done`

**↔ Siblings (33):**
  - **under [app-pipeline](2918e3b4.md):** [01-inbox — app-pipeline](46dfbb0a.md) · [app-deploy-1 — UI Foundation Step 1a + 1b](52dadffd.md) · [app-deploy-10 — Decompose app/projects/[id]/pag...](c8ab4772.md) · [app-deploy-11 — Minimum-viable smoke-test layer...](7f3d8c91.md) · [app-deploy-12 — eslint --fix auto-cleanup (part...](6e1f4b73.md) · [app-deploy-13 — Next.js framework migrations + ...](9b4d2e58.md) · + 27 more

**📥 Cited by (1):**
- [Tropo Platform UI Foundation Refactor — Project Plan](b31e8115.md) — `b31e8115` (type `project-plan`, via `derived_from`)
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [app-pipeline (2918e3b4)](2918e3b4.md) |
| Composes into | [Tropo Platform UI Foundation Refactor — Project Plan (b31e8115)](b31e8115.md) |

*Re-parented from web-pipeline 01-inbox → app-pipeline 01-inbox 2026-05-16 (T5) after the three-pipeline routing decision (Mike directive). Original filing was in web-pipeline 01-inbox because app-pipeline didn't exist yet.*

## Intent

The Tropo platform codebase (`tropo-ai/` repo: the Next.js app at tropo-ai.com plus the in-app surfaces) has accumulated architectural debt across UI layers, design tokens, and screen-level composition. The debt is invisible at small scale but compounds with each new feature: changing a panel border requires three edits, adding a screen requires inventing a new chrome, the Mo→Tropo rename is materially incomplete. The platform now has five screens and is poised to grow significantly (agent-builder wizard, downloads page, Substack-hosted blog routes, marketing surfaces).

**This brief commits to a foundation pass before that growth.** The goal is one design-system, one component primitives layer, one shared shell, one brand. The result is a codebase where the next ten features are cheaper to build than the last one was.

The work is mechanical, incremental, and reversible. No rewrites. Each step ships independently and leaves the app working.

## Out of scope

- Visual redesign — every change in this brief preserves current visual output (light + dark mode, all five screens). Visual diff is zero pixels at every step.
- Backend / API changes — `app/api/*` and `lib/*` outside UI concerns are untouched.
- The query pipeline, KB resolver, Anthropic client, intent extraction — those subsystems get their own sa.* but no refactor in this brief.
- Author sub-app (`/author`) — included in the brand sweep but its `.ma-*` ecosystem may stay structurally separate if a deeper refactor reveals it as a sibling app rather than a feature.
- Tropo Studio (argo-os/) substrate — this brief is platform-tier, not Studio-tier. Studio governance work is out of scope.
- New screens or features.

## Decisions made

The following are committed by this brief and not open at implementation time:

1. **One token system.** `app/styles/tropo-tokens.css` is canonical. Legacy tokens (`--accent`, `--bg0`, `--panel`, `--text`, `--muted`, `--border`, `--ring`, `--r-md`, `--gap`, `--panel-shadow*`, etc.) get aliased to `--tropo-*` then retired.
2. **Component primitives live at `components/ui/`.** Existing pane-level components (Header, ChatPane, ArtifactPane, ConfigPane, etc.) consume primitives; they don't reinline panel chrome, button styling, or input styling.
3. **One shared shell.** A single `<AppShell>` (placement to be determined: `app/layout.tsx` or wrapper component) holds the header, nav, theme toggle, and user-greeting. All five screens render content inside it. `Header.tsx` and `ProjectHeader.tsx` collapse into a single header that adapts to context.
4. **One brand: Tropo.** `mb-`/`ma-`/`mo-` CSS prefixes, "Mo" / "Mo Power" / "Mo Author" literal strings, `mo-selected-kb` localStorage keys, and `recentMessages` sender labels all migrate to Tropo equivalents.
5. **Big files get decomposed.** `app/page.tsx` (822 lines), `app/crew/page.tsx` (999 lines), `app/projects/[id]/page.tsx` (989 lines) each split into focused sub-components co-located beside the page file. No file over ~400 lines as a soft target.
6. **Each step ships independently** behind its own commit + visual-diff verification. No single PR ships more than one step. Total scope is ~6 small commits.

## Current state — findings from codebase audit

Audit conducted by Talos T5 on 2026-05-16. Numbers are factual, not estimates.

### Two design systems coexist in one 5,183-line `globals.css`

Three legacy class-prefix families plus one new family:

| Prefix | Selector count | Scope |
|---|---|---|
| `.mb-*` | **357** | main `/`, `/projects`, Header, ChatPane, ConfigPane, ArtifactPane, ChatHistory, ProjectHeader, ProjectSettings |
| `.ma-*` | **255** | `/author`, `components/author/*` |
| `.crew-*` | **18** | `/crew` only |
| `.tropo-*` | **1** | the wordmark |

Two token systems:
- **New (`app/styles/tropo-tokens.css`, 126 lines):** semantic, clean. `--tropo-bg`, `--tropo-fg`, `--tropo-accent`, `--tropo-space-*`, `--tropo-radius-*`, etc.
- **Legacy (in `globals.css`):** `--accent`, `--circuit`, `--amber`, `--bg0`, `--bg1`, `--panel`, `--panel2`, `--text`, `--muted`, `--border`, `--ring`, `--r-xl`, `--r-lg`, `--r-md`, `--gap`, `--panel-shadow*`. Overlapping but not synonymous.

Token usage in code:
- `--tropo-*` references: **2 total** (1 in Header, 1 in ArtifactPane indirectly)
- Legacy token references: **88 total** (86 in `app/crew/page.tsx` alone)

### No shared shell — every screen rebuilds its own

`app/layout.tsx` body content: `{children}`. No wrapper.

- `Header.tsx` (244 lines) and `ProjectHeader.tsx` (244 lines): near-identical. Same KB-list fetch effect, same settings dropdown, same click-outside handler, same MODE_OPTIONS constant, same JSX skeleton. They diverge only on brand block (one shows wordmark, one shows "Mo" literal) and on the power-mode toggle widget.
- `app/page.tsx`, `app/author/page.tsx`, `app/projects/page.tsx`, `app/projects/[id]/page.tsx`, `app/crew/page.tsx` each own their wrapper structure.

### Crew page is a fourth paradigm

`app/crew/page.tsx` (999 lines):
- 98 inline `style={{}}` attributes with raw hex codes
- 86 direct `var(--legacy-token)` references
- 166 className uses
- 3 inline sub-components (StatusBadge, TierBadge, TaskStatusBadge) defined inside the file
- Mixes Tailwind utility classes (`text-xs font-medium`) with CSS classes (`crew-badge crew-badge--blue`)
- No shared Header — likely no chrome at all

### Mo → Tropo rename is incomplete

391 `mo-` / `mb-` prefixed strings remain across `app/`, `lib/`, `components/`.

User-visible brand strings still saying "Mo":
- `ProjectHeader.tsx:102` — `<span className="mb-brandTitle">Mo</span>`
- `app/projects/page.tsx:104, 109` — `Mo` brand + `Mo` nav link
- `app/author/page.tsx:429, 434` — `Mo` brand + `Mo` nav link
- `components/ChatPane.tsx:250, 313` — assistant message label `"Mo"`
- `components/author/ConversationPanel.tsx:1857, 1867` — assistant sender label `"Mo"`
- `app/api/author/classify/route.ts:52` — Mo in transcript formatting

Storage keys: `mo-selected-kb` (Header, ProjectHeader).

The Tropo rename hit the main `<Header>` wordmark and the `<html><title>`. Everything downstream is still mid-migration.

### Line counts on UI surface

| File | Lines |
|---|---|
| `app/page.tsx` | 822 |
| `app/author/page.tsx` | 557 |
| `app/crew/page.tsx` | 999 |
| `app/projects/page.tsx` | 259 |
| `app/projects/[id]/page.tsx` | 989 |
| `app/globals.css` | **5,183** |
| `app/styles/tropo-tokens.css` | 126 |
| Components (7 files) | 2,084 |
| **Total UI surface** | **~10,019 lines** |

For five screens with no overlap-by-design. Most of the volume is duplication and ad-hoc styling.

### Tagline "Research, Analyze, Publish"

Not found anywhere in current `app/`, `lib/`, `components/`. Already removed or never landed. **Resolved.** Folds into no work item.

## Proposed approach — five steps

Each step is a separate commit (or small commit group). Visual diff verified at each step.

### Step 1 — Token consolidation

**1a. Extend `tropo-tokens.css` to coverage parity** with the legacy system. Additions:
- `--tropo-bg-deep` — page backdrop tier (darker than surface)
- `--tropo-surface-glass`, `--tropo-surface-glass-soft` — translucent dark panels
- `--tropo-shadow-sm`, `--tropo-shadow-md` — primitive shadows
- `--tropo-panel-shadow`, `--tropo-panel-shadow-hover` — compound shadow tokens
- `--tropo-ring` — focus ring
- `--tropo-radius-xl` (12px) — fills the legacy gap

~20 added lines. One-time edit.

**1b. Alias legacy names to `--tropo-*` inside `globals.css`.** Replace the legacy `:root` block (lines ~30-65) and the `html.dark` override block with alias definitions:
```css
:root {
  --accent: var(--tropo-accent);
  --bg0:    var(--tropo-bg-deep);
  --panel:  var(--tropo-surface-bg);
  --text:   var(--tropo-fg);
  --muted:  var(--tropo-fg-muted);
  --border: var(--tropo-hairline);
  /* … */
}
```
**Behavioral diff: zero.** Every existing `var(--accent)` still resolves to `#FF5E1A`. Shippable as its own commit.

**1c. Sweep references to use `--tropo-*` directly.** One PR per class family:
- `crew-*` first (smallest, 18 selectors + the big page file)
- `ma-*` second (255 selectors + the author screen)
- `mb-*` third (357 selectors + the main app + 6 components)

Mechanical regex replace. Visual diff after each.

**1d. Retire the legacy aliases.** Grep confirms zero references. Delete the alias block. `globals.css` shrinks; `tropo-tokens.css` is the single source of truth.

### Step 2 — Primitives layer at `components/ui/`

Build a small primitives set composed from `--tropo-*` tokens:

| Primitive | Replaces |
|---|---|
| `<Panel>` | `mb-panel*` / `ma-panel*` chrome (border, shadow, radius, background) |
| `<Pane>` | full-pane wrappers (`mb-pane*`, `ma-pane*`) |
| `<Chip>` | `mb-chip*`, `crew-badge*`, `crew-tag` |
| `<Button>` | `mb-btn*`, `crew-btn`, `ma-button*` |
| `<IconButton>` | settings dropdown trigger, chip toggles |
| `<Select>` | `mb-modeSelect`, `mb-kbSelect`, `ma-*` selects |
| `<Divider>` | `mb-navDivider`, `crew-divider`, rule lines |
| `<Wordmark>` | the inline SVG + text wordmark currently re-implemented in 3 places |

~8 primitives, each ~30-60 lines. Existing pane components (`ChatPane`, `ArtifactPane`, `ConfigPane`, etc.) refactor one-at-a-time to consume primitives. As they migrate, the legacy `.mb-panel*` / `.mb-btn*` / etc. selectors in `globals.css` get deleted. `globals.css` shrinks by ~60-70%.

Pattern: variants via `clsx` or `class-variance-authority` — to be decided in implementation. Token usage is non-negotiable; variant library is an engineering choice.

### Step 3 — Shared `<AppShell>`

Either at `app/layout.tsx` (Next.js layout convention) or as a wrapper component. Decision deferred to spec time; both work.

`<AppShell>` provides:
- Shared header (the unified `<Header>` after `ProjectHeader.tsx` is merged)
- Nav (Projects / Author / Crew links with active-state)
- Theme toggle (light/dark)
- Settings dropdown
- KB selector (when applicable)
- User greeting

Each screen renders its content inside `<AppShell>`. Headers in `/author` and `/projects` collapse into one. `/crew` and `/projects/[id]` gain consistent chrome. The 244-line `ProjectHeader.tsx` deletes.

### Step 4 — Brand sweep: Mo → Tropo

After primitives exist, most `.mb-*` and `.ma-*` class names disappear naturally (they're absorbed into primitives). The remaining sweep is:

- CSS class renames: any `.mb-*` / `.ma-*` / `.crew-*` selectors not yet retired → `.tropo-*` equivalents.
- User-visible brand strings: `"Mo"` → `"Tropo"`, `"Mo Power"` → `"Tropo Power"`, `"Mo Author"` → `"Tropo Author"`.
- Storage keys: `"mo-selected-kb"` → `"tropo-selected-kb"` (with migration on first read).
- Assistant message labels: `"Mo"` → `"Tropo"`.
- API route internal strings: `recentMessages` formatting in `app/api/author/classify/route.ts`.

One sweep PR, mechanical, comprehensive. After this lands, `grep -r "Mo\b\|mb-\|ma-\|mo-" app/ lib/ components/` returns zero matches.

### Step 5 — Decompose big files

Each of the three monster files splits into focused sub-components co-located beside the page:

| Page | Sub-components |
|---|---|
| `app/page.tsx` (822) | `<QueryComposer>`, `<SSEController>`, `<ChatColumn>`, `<ArtifactColumn>`, `<ConfigColumn>` |
| `app/crew/page.tsx` (999) | Already has inline `StatusBadge`/`TierBadge`/`TaskStatusBadge`; extract them. Plus `<ThreadList>`, `<DashboardSummary>`, `<ProjectTree>`, etc. |
| `app/projects/[id]/page.tsx` (989) | `<ProjectOverview>`, `<TaskList>`, `<BoardView>`, `<ProjectChat>`, etc. |

Each split is conservative: extract a self-contained UI region, give it a clear prop type, leave behavior unchanged. No file over ~400 lines after Step 5.

## Verification plan

The acceptance discipline: **zero visual diff at every step.** This is a refactor, not a redesign; the user-facing surface must be byte-equivalent (modulo expected sources of variance: timestamps, randomness, dynamic data) across the migration.

### Per-step verification

| Step | Verification |
|---|---|
| 1a + 1b | `npm run build` clean. `npx tsc --noEmit` clean. Visual diff (manual or screenshot-tool) on all 5 screens × 2 modes = 10 surfaces. Zero pixel drift. |
| 1c (each PR) | Same as above. Plus: `grep -c 'var(--legacy-name)' <affected files>` returns 0 for the swept family. |
| 1d | Same. Plus: codebase-wide grep for legacy token names returns 0. |
| 2 (each primitive PR) | Visual diff on screens that use the migrated primitive. Plus: `app/globals.css` line count delta documented per PR (we expect shrinkage). |
| 3 | Visual diff on all 5 screens. Header parity across `/`, `/projects`, `/author`, `/crew`, `/projects/[id]`. |
| 4 | Visual diff. Grep for `Mo\b\|mb-\|ma-\|mo-` in `app/lib/components` returns 0. |
| 5 | Visual diff on the decomposed screens. `npx tsc --noEmit` clean. Each new sub-component under 400 lines as soft target. |

### Verification instruments

- `npx tsc --noEmit` — type safety preserved.
- `npm run build` — Next.js build succeeds.
- Manual visual diff against `main` baseline — Mike or Talos clicks through 5 screens × 2 modes after each step.
- `grep` audit on legacy token names + brand strings — quantitative checkpoint.
- Smoke test of one query end-to-end after Steps 3 and 5 — confirms shared shell + decomposed `app/page.tsx` still threads SSE correctly.

### Failure modes and rollback

| Failure | Detection | Rollback |
|---|---|---|
| Alias maps to wrong color/alpha | Visual diff at Step 1b | One revert. No data migration. |
| Primitive prop API doesn't fit a use site | TypeScript error at Step 2 | Fix prop API or leave that callsite legacy; primitive layer is incremental. |
| Shared shell breaks SSE / page state | Smoke test after Step 3 | One revert. Layout changes are isolated. |
| localStorage key migration loses user state | Manual test before sweep at Step 4 | Include read-fallback (`localStorage.getItem("tropo-selected-kb") ?? localStorage.getItem("mo-selected-kb")`) for one release, then drop. |
| Decomposed sub-component drops a prop | TypeScript error at Step 5 | Caught at compile, not at runtime. |

All risks are caught at the verification gate. No risk is irreversible.

## Risk

**Medium risk overall.** Mechanical work with bounded blast radius. The main risks:

1. **Visual drift from alias mismatch.** Some legacy tokens differ subtly from the closest `--tropo-*` equivalent (e.g., `--border: rgba(20,24,29,0.10)` light is ~10% alpha; `--tropo-hairline` resolves to `--tropo-ink-20: #C9CCD2` which is opaque). Visual diff catches it; alias mapping gets fixed before the sweep continues.
2. **Crew page is a tar-pit.** 999 lines, 98 inline styles with hex literals, mixed Tailwind/CSS-class/CSS-in-JS. Step 1c-crew is mechanical-only (variables); Step 5-crew is the real decomposition. They're separated for a reason.
3. **`/author` may resist primitive adoption.** `.ma-*` ecosystem (255 selectors) suggests author was designed as a sibling app. If primitives don't fit cleanly, the call is whether to (a) duplicate `<AuthorPanel>` etc. in `components/ui/` or (b) acknowledge `/author` as a sibling and skip primitivization there. Decision deferred to Step 2 implementation.
4. **Brand sweep timing.** Step 4 lands user-visible name changes. If marketing or product wants to coordinate (e.g., release-notes message), defer Step 4 until after that coordination. Engineering-only call: ship it whenever.

## Talos session-agent set (`sa.*`)

Foundation refactor surfaces the natural subsystem boundaries. Proposed sa.* set, authored after this brief locks:

| sa.* | Lane | Read-list (at boot) |
|---|---|---|
| **`sa.ui`** | Components, primitives, design tokens, CSS, layouts | `components/`, `app/layout.tsx`, `app/styles/`, `app/globals.css`, screen page files |
| **`sa.query`** | Query pipeline: intent extraction, research agent, execution agent, prompts | `lib/intent-extraction.ts`, `lib/research-agent.ts`, `lib/execution-agent.ts`, `lib/prompts/*`, `app/api/query/*` |
| **`sa.kb`** | KB system: vault resolver, 2-hop traversal, intent index, governance | `lib/kb.ts`, `lib/intent-extraction.ts` (vault project queries), `app/api/kb/*` |
| **`sa.author`** | Author sub-app (own ecosystem) | `app/author/`, `app/api/author/*`, `components/author/*` |
| **`sa.api`** | API routing, SSE contract, request validation | `app/api/*` route handlers (excluding query + author which have their own sa.*) |
| **`sa.anthropic`** | Anthropic client, model selection, streaming, retries | `lib/anthropic.ts`, `lib/app-config.ts` |
| **`sa.test`** | Test suite, sprint QA, smoke tests | `tests/`, `package.json` test scripts, `lib/debug.ts` |

Boundaries are anchored to the post-refactor subsystem shape, not today's accidental shape. Each sa.* gets a charter, write scope, trigger description, and read-list. Dispatched via the standard sa.* commissioning protocol ([e863a1e0](e863a1e0.md)).

## Open decisions

To be resolved at spec time (or at Mike's call):

1. **`<AppShell>` placement.** `app/layout.tsx` (Next.js convention; layout works for App Router) vs. wrapper component called from each page. Trade-off: layout.tsx makes it implicit and inheritable; wrapper makes it explicit and opt-in. Recommendation: `app/layout.tsx` — it's the Next.js idiom and removes the requirement to remember.
2. **Variant library.** `clsx` (lightweight, no abstractions) vs. `class-variance-authority` (cva — typed variant API, lightweight). Recommendation: `clsx` + `tailwind-merge` until we have 3+ primitives needing variants, then upgrade to cva if useful.
3. **Brand sweep timing.** Land immediately after Step 3 (engineering-only call), or defer to coordinate with product/marketing message? Recommendation: engineering ships when ready; if a coordinated announcement matters, that's a separate decision.
4. **`/author` primitive adoption.** Primitivize OR acknowledge as sibling app and leave alone. Resolve during Step 2 after we see how 2-3 primitives land in the main app.
5. **Pipeline routing.** Mike floated renaming `dev-pipeline` → `studio-pipeline` (Studio governance work) and creating a new `dev-pipeline` for platform/app work. This brief lands in web-pipeline 01-inbox for now. If pipeline routing changes, the brief moves with it. **Not blocking.** Mike's call when he's ready.

## Provenance

Authored by Talos T5 on 2026-05-16 at Mike's direction following a codebase audit. Mike's framing: *"Quality starts at the foundation. Let's lay a solid architectural foundation to all we do."* T5 captured this as the doctrinal anchor — refactor before the next ten features so the next ten features are cheaper than the last one.

The brief operates captain-mode (Talos + Mike pair) per Operating Principle 9. The work crosses Talos's engineering/architectural boundary; per Mike-T5 2026-05-16, executive-level Opus agents can make architectural calls without routing every decision through Argus. Big decisions and explicit brainstorm areas surface to Argus when they appear; this brief and its execution proceed under Talos's authority.

## Go next

- **Brief locks** → project plan authored from this brief (Talos lane).
- **Project plan locks** → execution begins with Step 1a + 1b (small commit, low risk, immediate verification).
- **sa.* set authored** → after this brief locks, before execution starts; each sa.* commission file lands in `agents/talos/sa/sa.<name>/` or equivalent location per Talos write scope.

---

*Tropo Platform UI Foundation Refactor — Design Brief | Talos T5 | 2026-05-16*
*"Quality starts at the foundation."*
