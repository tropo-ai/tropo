---
uid: 53a7a624
title: Undefined-token references in globals.css — pre-existing broken state
type: note
description: Six legacy CSS variables (--fg, --fg-muted, --bg, --glass, --radius, --arctic) are referenced but never defined in app/globals.css; pre-existing condition surfaced during app-deploy-1 token-consolidation pass.
author: talos-t5
status: closed
state: archived
created: 2026-05-16
modified: 2026-05-17
created_by: talos-t5
modified_by: talos-t6
done_at: 2026-05-17
done_by: talos-t6
closed_by: 3f9c2e84
member_of:
  - cd1fcd25
relationships:
  - rel: refs
    uid: d05ed9ba
  - rel: refs
    uid: 52dadffd
schema_version: 2
extraction_scope: ship
file_ext: md
tags:
  - note
  - self-healing-finding
  - path-2
  - app-pipeline
  - globals-css
  - undefined-tokens
  - scope-deferral
---

# Undefined-token references in globals.css

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [dev-pipeline](cd1fcd25.md) → **Undefined-token references in globals.css — pre-existing ...**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/53a7a624 — Undefined-token references in globals.css — pre-existing broken state.md](../../00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/53a7a624%20%E2%80%94%20Undefined-token%20references%20in%20globals.css%20%E2%80%94%20pre-existing%20broken%20state.md)

**🌳 Tropo-Nav Path** (chat): [tropo-os-v1.84.1/00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/53a7a624 — Undefined-token references in globals.css — pre-existing broken state.md](tropo-os-v1.84.1/00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/53a7a624%20%E2%80%94%20Undefined-token%20references%20in%20globals.css%20%E2%80%94%20pre-existing%20broken%20state.md)

**🔗 This file** — UID `53a7a624` · type `note` · state `archived` · status `closed`

**↔ Siblings (21):**
  - **under [dev-pipeline](cd1fcd25.md):** [groom-subsystems — dev-pipeline step (NEW v1.7)](a5554670.md) · [License decision reversal — AGPL-3 → Apache 2.0...](c5d8e421.md) · [Setup New Pipeline](45d21cd8.md) · [tropo-mount — vault mount-gate + compose-lockfi...](8a4c1f6e.md) · [Tropo-OS v1.15.4 — Self-Healing Primitive](3e50b7b6.md) · [Tropo-OS v1.16.0 — First-User Readiness Pass](9149b649.md) · + 15 more
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [dev-pipeline (cd1fcd25)](cd1fcd25.md) |

## Finding

While executing `app-deploy-1` (token consolidation, Step 1a + 1b of the UI Foundation Refactor), I audited `app/globals.css` for all `var(--…)` references that aren't `--tropo-*`. The audit surfaced **six legacy CSS variables that are referenced but never defined** anywhere in the codebase:

| Variable | Usage count | Example location |
|---|---|---|
| `--fg` | 2 in globals.css | line 846, line 1668 |
| `--fg-muted` | 2 in globals.css (one with `#888` fallback) | line 4103, line 4463 |
| `--bg` | 1 in globals.css | line 4331 |
| `--glass` | 1 in globals.css | line 1677 |
| `--radius` | 1 in globals.css | line 2709 |
| `--arctic` | 1 in globals.css, 2 in `app/crew/page.tsx` | line 5155 + crew page lines 525, 706 |
| `--font-mono` | 4 in globals.css | with fallbacks to "SF Mono"/monospace |
| `--surface` | 1 in globals.css | with fallback to var(--tropo-graphite-soft) |
| `--glass-bg` | 1 in globals.css | with fallback to #1a1f2e |

**Updated 2026-05-16 (app-deploy-3 close):** Added `--font-mono`, `--surface`, `--glass-bg` discovered during the comprehensive sweep. Same treatment: all use explicit fallbacks; references currently render the fallback values; sweeping would change visual output. Same scope-deferral rationale.

`grep -rn` confirms: no `:root` or `html.dark` block defines any of these. They were referenced but never declared.

## Impact

Pre-existing broken state. References resolve via CSS cascade:
- With explicit fallback (e.g., `var(--fg-muted, #888)`): renders the fallback.
- Without fallback (e.g., `var(--fg)` for `color:`): inherits from the parent element. Effectively a no-op when the parent already has the desired color.

The user-visible effect today is mostly invisible (the styles look approximately right because of fallbacks or inheritance). But the references are noise — they document a design intent that isn't honored.

## Scope deferral

These references are NOT in `app-deploy-1`'s scope. The deploy commits to **zero visual diff** against the pre-change baseline. Adding aliases now would:
- Render fallbacks that weren't rendering before (`--fg-muted, #888` → resolved to `--tropo-fg-muted`, a different color)
- Render references that were inheriting before (`color: var(--fg)` → resolved to `--tropo-fg`, which may differ from the inherited color the parent provides)

Either case = visual diff. That breaks the run's commitment.

## Proposed fix (future cycle)

Add these aliases to the alias block in `globals.css` (post-Step 1d, or as part of Step 4 brand sweep):

```css
:root {
  --fg:        var(--tropo-fg);
  --fg-muted:  var(--tropo-fg-muted);
  --bg:        var(--tropo-bg);
  --glass:     var(--tropo-surface-glass);
  --radius:    var(--tropo-radius-md);
  --arctic:    var(--tropo-accent2);   /* best guess — needs verification against original design intent */
}
```

**Or:** sweep the references out (replace each `var(--fg)` with `var(--tropo-fg)` etc. at the call site) as part of Step 1c. Either approach resolves the broken state. The sweep is more thorough; the aliasing is faster.

**`--arctic` is the one uncertain mapping.** Search MindBridge-era history for the original color value before assuming. Likely a pale blue or amber tone given the name; `--tropo-accent2` (#E0B33C amber) is my best guess but should be verified.

## Recommendation

Pick up at Step 1c or Step 4 — whichever cycle next touches `globals.css` legacy tokens. Not blocking; not urgent. Closing this note happens when the references are either aliased or swept out.

## Provenance

Surfaced 2026-05-16 by Talos T5 during `app-deploy-1` verify-build sanity check. Per Self-Healing P0 primitive, filed as Path-2 work-item rather than expanded in current run's scope (would violate zero-visual-diff commitment).

---

*Inbox note · 53a7a624 · pre-existing broken state · scope-deferral · path-2*
