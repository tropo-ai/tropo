---
skill: render-chain-progress-board
name: render-chain-progress-board
type: how-to
purpose: Render a ship-time visual snapshot of where the just-shipped release lands in the active strategic chain
when: At every release ship, after the SHIP actions complete (version bump + predecessor archive + channels bulletin), before posting the SHIP confirmation to the human
mode: both
params:
  - strategic_chain_ref
  - current_release_version
  - pristine_streak_at_ship
uid: 135be96d
status: active
owner: argus
created: 2026-05-16
created_by: argus-a68
modified: 2026-05-16
modified_by: argus-a68
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: 'Reach for this at every release ship to render a visual ship-time snapshot of where the just-shipped cycle lands in the broader strategic chain (current binding: Captain''s Read v2.0.0 chain at a5f4b26b). The board surfaces block structure, cycle-by-cycle status, ASCII progress bar with ''you are here'' marker, streak counter, and risk catalog state — visual guideposts for the principal at ship-time. Render twice per ship: once embedded in the release entry body as a §Chain Progress Snapshot section (frozen ship-time historical record); once in chat as part of the SHIP confirmation (immediate visibility for the principal). Strategic chain reference is parameterized — Captain''s Read provides it today; whatever frames the chain post-v2.0.0 provides it next. Origin: A68 rendered the first such board at v1.35.0 ship 2026-05-16 in response to Mike-A68 ''Give me a board view of the drive we have towards v2.0. I''d like to see where we are at.'' Mike-A68 named the pattern
  a model of excellence + directed it be baked into Studio discipline.'
subsystem_hub:
  - 76bab75f
  - 8dd772a0
---

# Render Chain Progress Snapshot Board

Use this at every release ship to give the principal a visual snapshot of where the just-shipped cycle lands in the active strategic chain. The board renders **twice** — embedded in the release entry body (frozen historical record) AND in the chat SHIP confirmation (visible to the principal at ship-time).

This skill exists because the principal needs visual guideposts at ship-time, not paragraphs of prose. Releases compound across a long chain; at any single ship the human reasonably wants to see the whole arc + where they are + what's ahead without re-deriving it from text.

## Steps

1. **Resolve the active strategic-chain reference.** Read the active strategic-chain document. Current binding (v1.29 → v2.0.0): [Captain's Read (a5f4b26b)](../../vault/files/a5f4b26b.md) — provides three-block frame (Substrate hardening v1.29-v1.33 / The Funnel v1.34-v1.36 / Pre-ship polish v1.37-v1.40+) + v2.0.0 federation foundation as destination + risk catalog + pristine-streak target. Post-v2.0.0 a new strategic-chain document takes its place; the format pattern stays the same.

2. **Identify the just-shipped cycle's position in the chain.** Note: which block, which cycle within that block, what status (closed / in-flight / pending), what this cycle just shipped, what the immediate next cycle is.

3. **Render the board in this canonical format** (monospace ASCII; designed for chat-rendering + markdown viewers; ~30-50 lines):

   ```
   ═══════════════════════════════════════════════════════════════════════
     <Project name>  ·  <chain start>.x.x → <chain destination>  ·  Where we are
   ═══════════════════════════════════════════════════════════════════════

     Pristine-no-Rule-7 streak: <N>  →  target <N+1> at <next-cycle> ship  →  ~<target> at <destination>


   ┌──────────────────────────────────────────────────────────────────────┐
   │  BLOCK 1 — <block name>                       ✅ CLOSED              │
   │  <one-line block thesis>                                             │
   ├──────────────────────────────────────────────────────────────────────┤
   │  <vX.Y.Z>  <codename>            SHIPPED   <agent>                  │
   │  ... one row per cycle in the block ...                              │
   └──────────────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────────────┐
   │  BLOCK 2 — <block name>                      🔆 IN PROGRESS / ✅ CLOSED │
   │  <one-line block thesis>                                             │
   ├──────────────────────────────────────────────────────────────────────┤
   │  <vX.Y.Z>  <codename>            SHIPPED   <agent>                  │
   │                                                                      │
   │  <vX.Y.Z>  <codename>            ██████░░░  ~N%  <agent>            │
   │           ├─ <sub-state row 1>                            ✓          │
   │           ├─ <sub-state row 2>                            ✓          │
   │           └─ <sub-state row N>                            ◌ next     │
   └──────────────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────────────┐
   │  BLOCK 3 — <block name>                            ◌ AHEAD           │
   │  <one-line block thesis>                                             │
   ├──────────────────────────────────────────────────────────────────────┤
   │  <vX.Y.Z>  <codename>                              PENDING            │
   │  ... one row per pending cycle ...                                   │
   └──────────────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────────────┐
   │  <destination version>  <CODENAME>                🏁 DESTINATION     │
   │  <one-line destination thesis + audience>                            │
   └──────────────────────────────────────────────────────────────────────┘


     Progress bar — cycles to <destination>:

     <chain start> ═══════════════════════════════════════════════ <destination>
      ▓▓▓▓▓▓▓▓▓▓▓▓▓ ▓▓▓▓ ▓▓▓▓ ░░░░ ░░░░ ░░░░ ░░░░ ░░░░ 
      └─ Block 1 ─┘ B2.1 B2.2 │B2.3 │ B3.1│ B3.2│ B3.3│ B3.4+│ <destination>

      ▓ shipped   ▒ in-flight (you are here)   ░ ahead


     Risks tracked (<strategic-chain document> §<risks-section>):
       1. <risk name>      — <current state at this ship>
       2. <risk name>      — <current state>
       3. <risk name>      — <current state>


     This cycle's last legs:  <step 1>  →  <step 2>  →  <step 3>  →  ship
     (omit if just-shipped cycle is the chain's final step before destination)
   ```

   The exact glyphs (`▓` shipped / `▒` in-flight / `░` ahead / `═` borders / `│` cell separators / `✅` closed / `🔆` in-progress / `◌` ahead / `🏁` destination) are part of the canonical format — preserve them so future renders compose visually with past renders.

4. **Embed in the release entry body.** Add a `## Chain Progress Snapshot` section to the release entry, positioned after `## Verification Summary` and before `## Known Issues` per release.capsule v3.6 §Body Shape. Frame the embedded version as a ship-time snapshot: prepend the board with one italic line — *"Snapshot at v<X.Y.Z> ship <YYYY-MM-DD>. Future ships render new snapshots; this one is frozen at the moment v<X.Y.Z> went live."* The embedded board does not get updated after ship; the next release's snapshot supersedes it implicitly.

5. **Render in chat as part of SHIP confirmation.** Place the board in the chat reply that posts the SHIP confirmation, between the ship-action summary (version bumped / predecessor archived / channels bulletin posted) and the "what waits for the next cycle" lines. The chat render is identical to the embedded board minus the snapshot-framing italic line.

6. **Refresh the strategic-chain reference if this cycle changed it.** If the just-shipped cycle closes a block, opens a block, updates the risk catalog, or shifts the destination version, update the chain document inline at ship-time as part of release work. The skill execution is the trigger; the chain document is the substrate that grows from it.

## Success

- Release entry body contains `## Chain Progress Snapshot` section with the ship-time board frozen in it + the snapshot-framing italic
- Chat SHIP confirmation includes the board rendered in monospace ASCII (immediate visibility for the principal)
- Principal can see, at one glance: where the cycle landed, what's ahead, how many cycles to the chain's terminal release, what the streak state is, what risks are active
- Streak count in the board matches the release entry frontmatter `pristine_streak:` field
- Block + cycle labels match the active strategic-chain document (NOT hardcoded for a single chain — substitutable as the chain evolves)
- The canonical glyph set is preserved across renders so the visual history composes

## Format reference

The canonical worked-example board format is the v1.35.0 ship render at [v1.35.0 release entry (9743fa03)](../../vault/files/9743fa03.md) `## Chain Progress Snapshot` — first ship under this skill. Future renders may evolve the format as the chain matures or the destination ships; the structural principle stays:

- Block framing (closed / in-progress / ahead / destination)
- Cycle-by-cycle status table within each block
- For the in-flight cycle: sub-bullets showing micro-state
- ASCII progress bar with you-are-here marker
- Streak counter line
- Risk catalog state
- "This cycle's last legs" pointer if more remains in-cycle (omitted at clean ship)

## Composes with

- **[Captain's Read (a5f4b26b)](../../vault/files/a5f4b26b.md)** — the strategic-chain document the skill consumes today. Provides block structure, cycle list, destination, risk catalog. Successor chain documents post-v2.0.0 will provide the same shape.
- **[release.capsule v3.6 (b19e8d43)](../capsules/release.capsule.md)** — `## Chain Progress Snapshot` is now a required body section per v3.6 amendment; this skill is the canonical authoring procedure.
- **`.tropo/HUMAN-NAVIGATION.md`** — OS-tier primitive that names "humans need visual guideposts; design substrate with explicit visibility cues." This skill is one operationalization of that primitive at ship-time.

## Why this exists

Mike-A68 verbatim at v1.35.0 ship 2026-05-16 after seeing the first render: *"What you just did right there should be baked into our studio. Honestly, I am impressed. Why wouldn't we do that after every release? It's a model of excellence for how a tropo studio should work."* The discipline is now Studio property, not executive discretion.
