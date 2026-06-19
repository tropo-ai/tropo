---
uid: board-<4-char-hex>
title: ""
description: ""
scope: ""
generator: <role>
generator_mode: agent
filter:
 owner: []
 status:
 not: [done, cancelled]
sources: []
refresh: on-demand
version: 1
created: <iso-8601-utc>
updated: <iso-8601-utc>
---

# <Board Title>

<!-- This is the board definition file. The board synthesizer reads this definition,
 queries the declared sources, applies the filter, and writes a synthesized report
 to current.md in this folder.

 Physical structure:
 boards/<uid>/
 definition.md <- this file
 current.md <- the current rendered version
 versions/ <- prior versions, archived on regeneration
 AGENTS.md <- governance

 Generator modes:
 agent — named agent reads sources, applies judgment, writes synthesis
 script — deterministic filter + format, no LLM cost

 Refresh modes:
 on-demand — regenerated every time the board is read
 scheduled:<cron> — regenerated on cron cadence
 manual — regenerated only when explicitly asked
-->
