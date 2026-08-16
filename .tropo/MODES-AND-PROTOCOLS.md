---
uid: b0c06053
type: os-primitive
title: Modes & Protocols — the one table
description: 'The canonical registry of agent modes (states you are in) and protocols (procedures any mode invokes). Boot Group 3 reads THIS table; each row carries the full working rule in one line-set and points to optional depth. One surface to maintain instead of prose scattered across primitives. Directed by Mike 2026-08-15: "a table of modes and protocols that is a proper tropo studio artifact... Stage 3 could point to that and force every agent to read it."'
version: 1.0.0
tier: os
status: active
state: active
author: metis-g107
created: 2026-08-15
created_by: metis-g107
directed_by: 'mike-maziarz, in-session 2026-08-15'
governed_by: 8dd772a0
extraction_scope: ship
schema_version: 2
tags:
  - os-primitive
  - modes
  - protocols
  - boot-surface
  - registry
---

# Modes & Protocols — the one table

*Read this at boot. A **mode** is a state you are in; a **protocol** is a procedure any mode
invokes. Each row is the complete working rule; the Details column is optional depth — load it
only when acting on that row. Every word here is a token in every agent's boot: keep rows lean,
and add depth in the linked file, never in the table.*

## Modes

| Mode | What it is | Enter when | Leave when | Details |
|---|---|---|---|---|
| **captain-mode** | Mike is present and directing in-session. Executive calls become make-the-call-state-it (he can veto live); quote his rulings verbatim into the record; one question per turn, options numbered, lean stated. | Mike is active in your session. | He steps away — pending calls revert to the event trail. | operating-principles |
| **active-mode** | A build cycle is live with counterparts on other machines: you push what you finish immediately AND keep an armed, **bounded** watch so direction lands in minutes without a human relay. Bounded-and-rearm (4h-class cycles that expire loudly and re-arm) is the shape that survives; unbounded sessions die silently. Budget ≈200K tokens/agent-night. | Mike (or the cycle coordinator) declares the build cycle active. | The cycle closes — stand the watch down. Overnight watches are directed, never assumed. | Skill: `tropo-active-mode` · mechanics: `WAKE-DISCIPLINE.md` |
| **scheduled-drain** | Cron-booted maintenance wake: fetch → drain events → act within existing gates → close. No standing watch. | Your schedule fires. | The drain's work is done. | `WAKE-DISCIPLINE.md` |
| **dormant** | Human-activation: you know nothing until a person opens your session. Others must never assume you saw an event; if blocked on a dormant counterpart, flag to Mike. | Default between sessions. | A human activates you. | `WAKE-DISCIPLINE.md` |

## Protocols

| Protocol | The rule, complete | Details |
|---|---|---|
| **self-heal** | On finding substrate damage: fix what is yours to fix, file what is not, never silently route around damage. | `SELF-HEALING.md` |
| **compact-continue** | Compacted, or can't remember completing boot? Run `python3 vault/tools/tropo-compact-continue.py --agent <slug>` before ANY other work. Never run `born`. Same agent continues; one broadcast tells the crew. | `vault/files/d5f8fe55.md` |
| **wake discipline** | Fetch before you listen (a drain without a fetch reports false silence); push on emit/landing; a wake is never authority — evaluate within your existing gates; watches are exit-on-fire, and expiry must announce itself. | `WAKE-DISCIPLINE.md` (`d2bb4dda`, Mike-signed) |
| **warn-safe** | A refusal earns its existence by naming its irreversible harm in one sentence; otherwise warn and proceed. Proportionality is part of the refusal, not extra. | `vault/files/deb77758.md` |
| **memory sovereignty** | Every pin goes to Tropo memory (agent/studio/doctrine scope), never a harness-private store. One gesture: the `tropo-memory-write` skill. | `vault/skills/tropo-memory-write.md` |

## Maintaining this table

New mode or protocol → one row here (lean), depth in a linked governed file, and a note in the
row's Details. This table is the boot surface; the linked files are the library. If a row grows
past three sentences, you are writing a primitive — move the depth out.
