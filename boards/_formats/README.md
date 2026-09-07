# Board Formats: the shapes Tropo ships

A **board** is the agent-authored "beautiful board" surface. It has three parts:

- **shape**: which sections, in what structure (the formats in this folder)
- **style**: how it looks ([`../_shared/board.css`](../_shared/board.css), the shared stylesheet)
- **the work**: the agent reads the roadmap / release / design + live vault and fills the shape with judgment

You do not build a rendering engine. **The agent is the engine.** You give it a shape and a style; it supplies the content and the judgment about what to surface.

**Two classes share this stylesheet.** An *authored board* is what the rest of this document
describes: an agent fills a shape with judgment and regenerates it when the work moves. A
*derived render* is generated straight from the vault on a fixed template, with no judgment
step, and its generator regenerates it rather than a person. Both link the same
[`../_shared/board.css`](../_shared/board.css), so a style change reaches both at once. The
rule above governs the authored class: it means you do not build an engine to stand in for the
agent's judgment. It does not forbid a generator for the derived class, which this cycle ships.

## The named formats

| Format | Use it for |
|---|---|
| [`roadmap-board.html`](roadmap-board.html) | A forward-looking, multi-cycle roadmap. "Where do we stand on the road to v2.0", post-ship "yesterday + what's next." Mike's locked 7-section shape. |
| [`design-status-board.html`](design-status-board.html) | The status of one design / feature / initiative: its tier, lifecycle stage, artifacts, the decisions binding it, and what it waits on. |
| [`release-board.html`](release-board.html) | What ships in one cycle: the streams, the VEHICLE TABLE (every dev-spec linked, with its activation and last-touched time), the ship gates, what is owed, what waits on the principal, THE ENDGAME IN DEPENDENCY ORDER WITH SEATS, and the honest ledger. Upgraded 2026-08-31 from the v1.94 board Mike named the model. |

## How to author a board

1. **Copy** the format that fits to `boards/<you>/<slug>-<date>.html`.
2. The stylesheet `<link>` is already correct for `boards/<you>/`, so leave it.
3. **Fill** every `{{FILL: ...}}` with real content read from the source + live vault. Delete a section only if the ask precludes it.
4. **Status is the arbiter.** Every status badge reflects the item's authoritative `status` / `state` field in the vault, never a guess and never a stale tag. "Awaiting / needs X" reads the ownership fields (`requested_of` / `approver` / `verifier`) plus non-terminal status.
5. Hand-link files as `[readable name](path)`; no bare UIDs in human-facing text; no em-dashes.
6. Stamp the footer with author + **date AND TIME IN UTC** and "A snapshot; regenerate when work moves." A board read hours after writing must show its own staleness — date alone cannot (Mike-directed 2026-08-31).
7. **On a release board, link every vehicle and name every seat.** The reader who wants detail is one click away, never a search; and a remaining step no available seat can execute is the most decision-relevant fact the board carries.

A board is a **snapshot**: the authoring agent regenerates it when the underlying work moves.

## Where this goes next

- **L1 (today):** the agent fills a format and renders static HTML. Works in the bare zip, no server.
- **L2 (the cockpit):** a "define a board" surface (pick the format, pick the source) and the cockpit serves it live, regenerating from the vault.

Full vision + section structure of each format: see the **Board-Format Family** catalog at `vault/files/89f2d5d4.md`, and the brief [Productizing the Rich Board (`5a5b9d82`)](../../vault/files/5a5b9d82.md).
