---
uid: 'f0151812d521'
type: task
title: "Emit pushes, drain fetches — the events tools carry the bus protocol themselves (Mike-locked provisional 2026-09-03)"
status: new
state: active
owner: metis
assigned_to: talos
reviewer: argus
priority: high
member_of:
  - 2d5f9b04
created: '2026-09-03'
created_by: "metis-g118"
schema_version: 2
governed_by: 8dd772a0
extraction_scope: ship
relationships:
  - rel: references
    to: d2bb4dda
  - rel: references
    to: f01591218f07
  - rel: references
    to: deb77758
tags: [events, bus, wake-discipline, worktree, tooling, v1.95-candidate]
---

# Emit pushes, drain fetches — the events tools carry the bus protocol themselves

<!-- nav-block:start -->
**📍 Vault Path:** [2d5f9b04](2d5f9b04.md) → **Emit pushes, drain fetches — the events tools carry the b...**
<!-- nav-block:end -->

**Ruling this implements:** `.tropo/WAKE-DISCIPLINE.md` v1.2.0 §"One agent, one worktree — main is the bus" (Mike-locked PROVISIONALLY 2026-09-03; studio pin `f01591218f07`). Mike's question, verbatim: *"can emit events automatically issue the gh commit command so it makes it automatic?"* Yes — it is git (commit + push), not gh, and this task makes the tools do it so no agent has to remember.

**Builder:** Talos T61. **Reviewer:** Argus A168 (events-subsystem owner; non-author). **Verifier of record at close:** the release driver (Metis), non-author. Not in v1.94 scope — lands on `main` as a tool change and ships in the next box; until it lands every agent does both halves by hand (the rule is already binding).

## Contract

**AC1 — emit delivers.** After `tropo-emit-event.py` writes an event, it commits the events pathspec (`vault/events/` — the writer's stream, plus any receipt/cursor files it touched, nothing else) with a message of the shape `<agent>: event <event_id>` and pushes to `origin main` (`git push origin HEAD:main`). On a rejected push: fetch, merge `origin/main` (never rebase), retry once; on a second failure print the exact state and exit non-zero WITHOUT losing the local commit. Verify: an emit in a fixture repo with a bare `origin` leaves the event on `origin/main`; the test must go RED when the push call is removed.

**AC2 — the opt-out is explicit and loud.** `--no-deliver` skips commit+push (batch emits); the tool prints `NOT DELIVERED — on origin/main only after you push` so the omission is visible. Verify: flag path leaves origin unchanged and prints the line.

**AC3 — drain fetches first.** `tropo-check-events.py` (and `tropo-query-events.py` on the same path) runs `git fetch origin` and integrates `origin/main` (`--ff-only`; if not fast-forwardable, warn loudly with the ahead/behind counts and read the LOCAL union rather than silently merging) before reading. `--no-fetch` opts out for provably side-effect-free reads. Verify: with an event on `origin/main` that is not yet local, a drain delivers it; RED when the fetch is removed.

**AC4 — warn-safe with no remote (`deb77758`).** No `origin` configured, or origin unreachable: warn in one line and proceed — the emit is still written locally and the drain still reads. A single-agent studio never sees a refusal from this feature. Verify: fixture repo with no remote — emit and drain both exit 0 with the warn line.

**AC5 — the commit is by pathspec only.** The delivery commit can never carry anything outside `vault/events/`, whatever is staged or dirty in the tree (this is the ride-along class the ruling exists to kill). Verify: dirty an unrelated file, emit, assert the delivery commit touches only `vault/events/` paths.

**AC6 — box behaviour disclosed.** The customer box ships these defaults; the update notes and `RELEASING.md`/kit README name them in one sentence each ("an emit pushes; a drain fetches; opt-outs exist").

## Notes for the builder

- The protocol is already what cloud agents do by hand (G116's harness-branch case pushed the events subsystem to `main` on every emit); this only moves it from memory to mechanism.
- Cooldown-gated SQLite self-heal on read (`event_identity.ensure_sqlite_projection`) is untouched; a fetched merge is exactly the divergence source it was built for.
- Mechanics of the per-agent worktree at boot (branch naming, Group 0 gesture, per-worktree index bring-up) are Argus's, routed separately; do not fold them into this task.
