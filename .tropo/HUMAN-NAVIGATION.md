---
uid: 57a9c11f
type: os-primitive
title: "Human Navigation — Tropo-OS P0 Primitive"
description: "Every Tropo Studio's vault is governed substrate for agents. Its rendered markdown body is ALSO a deliverable surface for humans — specifically the principal who reviews work, walks the graph, and verifies outcomes. Substrate that is not human-navigable is incomplete: the agent half ships, the human half doesn't. This primitive declares the contract every governed vault entry must satisfy at the rendered-body level: filesystem-tree walkability on the composable graph. Up (path) / Self (identity) / Down (children) / Lateral (siblings) / Inbound (cited-by). Readable-name first; UIDs in code-fences for copy-paste."
version: "1.3"
v1_3_amendment_note: "v1.3 (Argus A95, 2026-06-03, captain-mode per Mike-A95 directive) — adds the 'Where surfaces live' clause to §Agent-Authored Visual Surfaces. v1.1 said author the surface; v1.2 said deliver it openable + keep it live; v1.3 says WHERE it lives so the human can FIND and PRUNE it: the canonical home is <studio>/boards/<agent>/ (the Dashboard home in STUDIO.md System Map), exposed at the studio root — never a hidden dotfolder. Private scratch + memory stay in .tropo-capsule/. Driven by finding 5afbbdd2 (Metis G65 / Mike-G65): agent-authored boards were landing in hidden .tropo-capsule/workspace/, so the human could neither find nor prune them. ADDITIVE; v1.0/v1.1/v1.2 content unchanged. SIGNED by Mike at OS-tier 2026-06-03 ('approved')."
tier: os
status: active
state: active
author: vela-v45
created: 2026-05-15
modified: 2026-06-03
created_by: vela-v45
modified_by: argus-a95
v1_2_amendment_note: "v1.2 (Metis G64, 2026-05-31, same day as v1.1) - adds two requirements to §Agent-Authored Visual Surfaces that the first Po pressure test proved were missing. v1.1 said the render 'ships in the bare zip on day one' - necessary but NOT sufficient. (1) DELIVERY / last-mile: a render the human cannot open is incomplete; ship it with the one-line command that opens it (macOS `open <path>`), never a folder-navigation instruction. (2) LIVENESS: a snapshot of chat input is not the deliverable; render from real tracked state where possible, and a snapshot is acceptable only when labeled AND paired with an in-session offer to make it real. Driven by finding a7d2e5c9 (Po bailed a cold skeptic partly because the board couldn't be opened and was a static cartoon). ADDITIVE; SIGNED by Mike at OS-tier 2026-06-02 ('approved', G65 closeout walk) alongside v1.1. Argus notified."
signed_by: mike-maziarz
signed_at: 2026-05-15
signed_v1_3_at: 2026-06-03
signed_v1_3_context: "Mike-A95 sign-off 2026-06-03 — 'approved.' Locks the v1.3 additive 'Where surfaces live' clause at OS-tier; prior signatures unchanged. Recorded by argus-a95 captain-mode (closes finding 5afbbdd2)."
signing_context: "Mike-V45 sign-off 2026-05-15 — 'I'm good.' Same OS-tier sign-off pattern as SELF-HEALING.md (db0fd9b1; Mike-signed 2026-05-09). Authored 2026-05-15 by vela-v45 in captain-mode per Mike-V45 directive arc (substrate-coherence cleanup session). v1.0 ships in every Studio via the release pipeline."
signed_v1_1_v1_2_at: 2026-06-02
signed_v1_1_v1_2_context: "Mike-G65 sign-off 2026-06-02 — 'approved.' Locks the v1.1 (L1-native visual surfaces) + v1.2 (render delivery + liveness) additive amendments at OS-tier; v1.0 signature (2026-05-15) unchanged. Recorded by metis-g65 in the small-stuff closeout walk."
v1_1_amendment_note: "v1.1 (Metis G64, 2026-05-31, captain-mode per Mike-G64 directive) — adds §Agent-Authored Visual Surfaces — and Why They Are L1-Native. Extends the primitive from the auto-rendered text nav-block (v1.0) to the broader truth Mike-G64 surfaced: humans navigate visually, agents author rich rendered surfaces (boards / diagrams / maps as SVG / PNG / self-contained HTML), and this is L1-native — a harnessed agent writes static rendered files with no npm and no server, so the visual surface ships in the bare L1 zip. Composes with the three-tier product model (L1 agent-authored static → L2 served-live-operable cockpit → hosted). ADDITIVE — does not alter the v1.0 Mike-signed content; SIGNED by Mike at OS-tier 2026-06-02 ('approved', G65 closeout walk; same sign-off gesture as v1.0). Authored under the Vela-V45 captain-mode precedent (executive authors the OS primitive on Mike's directive; Mike signs). Argus notified for architectural-stewardship review."
governed_by: 8dd772a0   # Tropo Governance hub
aligned_with:
  - "a4f9e2b1"   # operating-principles.md OP-12 (Studio-tier interpretation)
  - "ee814120"   # core.capsule (structural contract supporting this primitive)
  - "db0fd9b1"   # SELF-HEALING.md (sibling P0 primitive; precedent for this shape)
member_of:
  - "8dd772a0"   # Tropo Governance hub (OS-tier substrate)
extraction_scope: ship
schema_version: 2
tags: [os-primitive, human-navigation, p0, every-agent-every-studio, rendered-surface-as-deliverable, navigation-block, filesystem-tree-on-graph, agent-authored-visual-surfaces, l1-native-rendering, boards-svg-png-html, render-delivery-last-mile, render-liveness, v1-1-v1-2-mike-signed-2026-06-02]
---

# Human Navigation — Tropo-OS P0 Primitive

*Authoritative declaration. Ships in every Studio. Cannot be overridden by Studio-tier or agent-tier configuration. Signed by Mike Maziarz at OS-tier — v1.0 2026-05-15; v1.1 + v1.2 2026-06-02.*

---

## The Primitive

**The substrate is for agents. The rendered surface is also for humans.**

Every governed vault entry's rendered markdown body MUST provide filesystem-tree walkability on the composable graph. Five affordances, sentinel-wrapped at the top of every body, authored by the canonical render pipeline at rebuild time. Five sections, in order:

```
📍 Path:     root → parent → **this file**          ← filesystem `cd ..` chain
🔗 This file — UID `<uid>` · type · state · status  ← identity + copy-paste handle
↓ Children (N):                                     ← filesystem `ls .`
↔ Siblings (N):                                     ← filesystem `ls ../` minus self
📥 Cited by (N):                                    ← graph-only bonus (non-tree edges)
```

The block is sentinel-wrapped (`<!-- nav-block:start --> ... <!-- nav-block:end -->`) for idempotent find-and-replace. Authored automatically at rebuild time; the agent does not hand-write it. Every UID rendered in the block is preceded by its readable display-name (the `title:` field from the cited entry's frontmatter). The bare UID never appears as a surface text — only as a copy-paste handle in a code-fence and as the link target.

*Tagline: the substrate is for agents; the rendered body is for humans.*

The principle is one paragraph. The discipline is everything below.

---

## Why This Exists

Mike Maziarz, Founder of Tropo, named this directly during Vela V45's session 2026-05-14:

> "I'm building tropo for agents. However, you will often ask me to review a file for my feedback. I need to be able to navigate up and down the lineage more easily in the markdown section of the documents. The frontmatter does not help me when I look in 'source' mode because I cannot navigate. One thing all my crew do not appreciate, and it is very frustrating to me, is that I do not have your ability to translate a UID into a readable format. It is nearly impossible for me. The crew never remembers that and it is very hard for me. I'm just being honest. I'm the human, I need a surface also."

The crew had been authoring substrate for months without surfacing the principal's navigation needs. Every executive read past the same friction (an Operating Principle 5 drift miss — drift is the crew's responsibility, and the crew missed it). UIDs in YAML are machine wiring; they are not human navigation affordances. A vault file that hides its UID in frontmatter (invisible in markdown preview) and shows only outbound `member_of:` rows in a Relations table is half-built: the agent half ships, the human half doesn't.

Tropo's bigger claim is that human-AI collaboration is durable across generations because the substrate persists. If the substrate is illegible to the human at the moment they would verify it, the verification bottleneck collapses. The principal cannot scale verification across a substrate they cannot navigate. **Bounded verification depends on a navigable rendered surface.**

This primitive closes that gap structurally — the rule is no longer behavioral and forgettable, it's rendered by construction and codified at OS tier so it ships with every Studio.

---

## The Pattern — Filesystem-Tree Walkability on the Composable Graph

A filesystem gives a human four navigation affordances naturally: where am I (path), how do I go up (parent), how do I go down (children), who shares my parent (siblings). The composable graph offers all four — and one bonus the filesystem cannot offer: inbound references via typed non-tree edges (cited-by). The rendered Navigation block surfaces all five at the top of every governed body, capped for readability:

| Section | Filesystem analog | Source | Cap |
|---|---|---|---|
| 📍 Path | `pwd` and `cd ..` chain | walk `member_of:` edges up to root | 5 levels deep |
| 🔗 This file | `ls -la <self>` | own frontmatter (uid, type, state, status, title) | n/a — always one line |
| ↓ Children | `ls .` | inverse `member_of:` (entries that point AT this one) | 8 per type |
| ↔ Siblings | `ls ../` minus self | for each parent, list other children of that parent | 6 per parent |
| 📥 Cited by | (graph-only — no filesystem equivalent) | inverse references via non-member_of fields (refs, governed_by, supersedes, etc.) | 5 total |

Multi-parent files render multiple sibling groups (one per parent). Each section is optional — rendered only when non-empty (a root-level hub has no Path; a leaf entry may have no Children; etc.). The block produces no surface if the file has no resolvable UID or no H1 (pre-frontmatter legacy / README-class meta-files are skipped).

---

## The Readable-Name-First Discipline

**When any agent (executive, sa.*, child-agent) writes a file Mike will read, or references a file in a channel post, transfer, brief, or chat message: readable name first, UID in parentheses, UID as the link target — never the reverse.**

```
❌ Old pattern: see [2238250e](vault/files/2238250e.md) for the rebuilder bug
✅ New pattern: see [the integrity-json rebuilder bug note (2238250e)](vault/files/2238250e.md)
```

The link target stays the same (clicks work); the surface text the principal scans is the readable name. Compliance is contractual at vault-entry render time (the Navigation block renders readable names by construction) AND behavioral at agent-write time (every channel post + transfer + chat reference).

---

## Agent-Authored Visual Surfaces — and Why They Are L1-Native (v1.1)

*Amendment authored 2026-05-31 by Metis G64 in captain-mode per Mike-G64 directive. Additive to the v1.0 Mike-signed primitive; pending Mike's OS-tier signature to lock, the same "I'm good" gesture as v1.0.*

The Navigation block above is the **baseline** human surface — auto-rendered on every entry by the render pipeline. It answers "where am I and who points at me." But humans do not navigate a large system by reading text headers alone. **Humans are visual.** They navigate by maps, boards, trees, charts — rendered surfaces taken in at a glance.

So the human-navigation contract is broader than the nav-block: **agents author rich visual surfaces for the humans they serve** — boards, diagrams, maps, ordered tables, status charts — not only the auto-rendered text block.

**The load-bearing truth (Mike-G64, 2026-05-31): this is L1-native. It needs no server.**

A harnessed agent (Claude Code, Codex) can write a self-contained `.html` file with inline CSS and SVG, author an `.svg` diagram, or generate a `.png` — all as static files on the filesystem, all opened directly in a browser (`file://`) or rendered in the editor preview. No npm. No Node server. No build step. Just the L1 floor: a capable harness, a filesystem, and Python. **The agent is the renderer; the output is a governed static file.** The beautiful, human-navigable surface is therefore available in the bare L1 zip — the stranger's very first encounter — not gated behind a running server.

**Fidelity rises with commitment, but the surface exists at every tier:**

- **L1 (the zip):** the agent authors static rendered surfaces — SVG / PNG / self-contained HTML — as governed files. Clickable (relative links between rendered files; an inline index for search). The human navigates visually with zero server.
- **L2 (the local server):** the same surfaces, now served live and *operable* — they reflect current state and the human can act on them.
- **Hosted:** the same again, multi-user.

Same concept the whole way up. The static L1 render and the live L2 cockpit are one human-navigation surface at rising fidelity.

**Freshness discipline.** A static render is a point-in-time snapshot. The agent that authors a board owns keeping it current — regenerate it when the underlying work changes, so the human never navigates by a map that has drifted from the territory (composes with the regenerate-board pattern + sa.board-agent). The only thing the L1 static surface gives up versus the L2 server is *live* and *operable* — that is the L1/L2 line drawn correctly, and the reason to climb to L2.

**Two requirements the render must meet (v1.2 — proven necessary by the first Po pressure test, finding `a7d2e5c9`).** "Ships in the bare zip" is necessary but not sufficient. A rendered file that the human cannot open, or that reflects nothing real, has not done its job.

- **Delivery (the last mile).** A render the human cannot open is zero value — the same "invisible value is zero value" failure as a capability with no encounter path (OP-10). The agent does not stop at writing the file; it hands the human the one-line command that opens it. On the macOS L1 floor that is `open <path>`, which pops the render straight into the default browser — one line the human pastes. Never "navigate to the folder and double-click." The render is not delivered until the human can see it in one move.
- **Liveness.** A snapshot of what the human just said is a cartoon, not a surface — to anyone who thinks in systems it has near-zero value over a photo of a whiteboard. Render from real tracked state wherever possible. A snapshot is acceptable only when it is (a) labeled honestly as a snapshot and (b) paired with an immediate, in-session offer to make it real — capture the items as tracked work now, so the next render reflects something true. Liveness at L1 comes from rendering tracked substrate, not from re-drawing chat input.

**Where surfaces live (v1.3 — proven necessary by finding `5afbbdd2`).** A human-facing rendered surface must live in a findable, human-manageable home — never a hidden dotfolder. The canonical home is `<studio>/boards/<agent>/` (the Dashboard home in [STUDIO.md](../STUDIO.md)'s System Map), exposed at the studio root so the human can discover surfaces without an agent opening each one, and prune the ones that accumulate. Private agent scratch and memory stay in `.tropo-capsule/` (not human-facing). The split: if a human is meant to read it, it lives in `boards/`; if it's the agent's own working state, it stays in `.tropo-capsule/`. The delivery rule (`open <path>`) and liveness rule above still apply — the home makes the surface findable; delivery makes it openable; liveness keeps it true. *(Finding 5afbbdd2: Metis G65 / Mike-G65 — agent boards were landing in the hidden `.tropo-capsule/workspace/`, so the human could neither find nor prune them.)*

**The standard.** Every agent, in every Studio, renders for the human it serves — and the human can find it, open it, and it reflects something real. Visualization-for-the-human is core to what Tropo is, not an optional agent trait. When the human is staring at raw substrate they cannot read, or at a surface they cannot find, or at a file they cannot open, or at a cartoon of their own words, the surface has not shipped.

---

## Boundaries

**Human Navigation does not override write-scope discipline.** The Navigation block is rendered by `.tropo/scripts/generate-relations-header.py` during the canonical render pass (Step 4/4 of `rebuild-vault.py`). Agents do not hand-author the block; agents do not amend the block in-place. Drift in the block is a render-pipeline issue, not an authorship issue.

**Human Navigation does not require ceremony for rendering.** The block ships with every Studio, every rebuild, every entry. No agent has to remember to include it; the script does. No principal has to authorize it; it's the default.

**Human Navigation does not eliminate the need for written context.** The block is a navigation surface, not a substitute for body content. Authors continue to write substantive body content (the meat of the entry). The block answers "where am I and who points at me"; the body answers "what is this and what does it mean."

---

## Composition

This primitive is the OS-tier authoritative declaration. Studio-tier and agent-tier documents *interpret* and *apply* it; they don't restate it.

- **[`.tropo/capsules/core.capsule.md`](capsules/core.capsule.md)** (v1.2+) — the structural contract supporting this primitive. Declares `title:` as required core frontmatter (display-name field — distinct from `name:` which is structured); declares the Navigation block render obligation; ratchets validation from latent to enforced.
- **[`.tropo/scripts/generate-relations-header.py`](scripts/generate-relations-header.py)** (v1.X — vela-v45 amendment 2026-05-14) — the canonical render pipeline. Authors the five-section Navigation block on every governed vault entry at rebuild time.
- **[`.tropo/scripts/tropo-validate.py`](scripts/tropo-validate.py)** `check_navigation_block_render_safety()` — extends the validator to catch missing-title + missing-Navigation-block defects. WARN at v1.X; ERROR ratchet at v1.X+1 once migration substrate is clean.
- **[`.tropo-studio/operating-principles.md`](../.tropo-studio/operating-principles.md) OP-12** — Studio-tier interpretation; "Design for Human Navigation — the Rendered Surface Is a Deliverable." Operationalizes the primitive for Argo-OS specifically. Mirrors how OP-3 operationalizes SELF-HEALING.md for Argo-OS.
- **Agent boot extensions** at `vault/files/<boot-extension-uid>.md` — no per-agent restatement needed; the primitive inherits automatically.

---

## Boot Internalization

Every agent activation reads this document at Group 2 of [`agent-activation.playbook`](playbooks/agent-activation.playbook.md) (alongside SELF-HEALING.md). Every agent's startup signal confirms internalization. The principal sees the confirmation and redirects if the principle isn't operational.

Soft-gated, not strict-gated — by design. The structural enforcement (Navigation block render + validator extension) catches drift in audit; the boot internalization catches it at agent-genesis; the readable-name-first discipline catches it during work.

---

## The Standard

**The standard is the principal can navigate any governed vault entry without leaving the rendered preview.** No source-mode peek to find the UID. No clicking through to read titles. No mental translation from 8-hex to meaning. Where am I, what's above me, what's below me, what's beside me, what points at me — all visible in a glance at the top of the body.

When the principal cannot navigate, the primitive has failed. When the principal finds themselves clicking a link just to know what file it points at, the readable-name-first discipline has failed. When the principal asks "wait, what is this UID?", the crew has failed Operating Principle 5 (drift is the crew's responsibility) by letting Navigation block render-safety drift.

The miss-and-learn loop: when the principal does spot a navigation failure, the agent who missed it captures the miss + the fix propagates to the substrate (memory pin → validator check → capsule contract amendment, as appropriate).

---

## Why This Is OS-Tier (Not Studio-Tier)

Tropo is the OS; Studios are installs. The human-navigation requirement applies to every Studio, not just Argo. A future Studio that adopts Tropo-OS inherits SELF-HEALING.md, inherits the capsule kernel, inherits the render scripts — and must inherit this primitive too. Otherwise the human-navigation half is per-Studio behavioral discipline that decays unevenly across the ecosystem.

`.tropo-studio/operating-principles.md` OP-12 (Argo's interpretation) ships with Argo but does NOT propagate to other Studios. This primitive at `.tropo/HUMAN-NAVIGATION.md` DOES propagate to every Studio via the build-release pipeline. That's the mechanism by which the doctrine travels.

---

*Human Navigation — Tropo-OS P0 Primitive | UID `57a9c11f` | v1.3 | v1.0 authored 2026-05-15 by Vela V45 (Mike-signed 2026-05-15) | v1.1 + v1.2 by Metis G64 (Mike-signed 2026-06-02) | v1.3 §Where surfaces live by Argus A95 2026-06-03 per Mike-A95 directive (Mike-signed 2026-06-03) | Ships in every Studio*
*"The substrate is for agents; the rendered body is for humans. The agent draws it, ships it in the bare zip, hands the human the one line that opens it, and draws it from something real — or it hasn't shipped."*
