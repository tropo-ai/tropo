---
uid: d8f3e2c1
name: check-sa-catalog
type: how-to
title: Check SA Catalog
skill_id: check-sa-catalog
version: 1.0
status: active
owner: vela
tier: os
author: vela
created: 2026-04-14
created_by: vela
modified: 2026-06-04
modified_by: argus-a97
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
purpose: Returns the current session-agent catalog — available sa.* agents, their domains, and commissioning info
when: When you want to know what session agents are available to spawn
trigger_description: 'Reach for this when you need to know which session agents (sa.*) are available to spawn — current catalog of fleet members, their domains, and commissioning info. Useful before a sa.* commissioning step, when planning verification posture, or when checking what specialist work can be delegated. Note: v1.15 ships a dedicated sa-agent-catalog at .tropo/sa-agent-catalog.md generated from vault entries — for shipped Studios that catalog supersedes this skill''s role; this skill remains useful for Argo-internal sa.* discovery during development.'
reads:
  - agents/sa/README.md
  - agents/sa/00-index.md
writes: null
subsystem_hub:
  - 76bab75f
---

# check-sa-catalog — Skill

*Returns the current session agent catalog — available sa.* agents, their domains, and commissioning info.*
*Use when you want to know what session agents are available to spawn.*

---

## When to Use

Call this skill when:
- You want to know what sa.* agents exist before spawning one
- You need a specific domain capability and want to check if an agent covers it
- Another executive asks "is there an sa.* agent that does X?"

Do NOT read `agents/sa/` directly at every boot — use this skill on demand.

---

## Process

1. Read `agents/sa/README.md` — the human-readable catalog summary
2. Read `agents/sa/00-index.md` — the structured index table
3. Return: list of available agents with name, domain, status, and spawnable_by

---

## Output Format

```
SA CATALOG — [date]

Available session agents:
| Agent | Domain | Status | Spawnable by |
|-------|--------|--------|-------------|
| sa.vela-test | General vault operations | active | vela |
| sa.backlog-analyst | Backlog analysis + task cleanup | active | all-executives |
| sa.arch-specs | Architectural docs on demand | active | all-executives |
| sa.v04-scope | Architecture Spec v0.4 task tracker | active | all-executives |
| sa.skeptic | Devil's advocate design review | active | all-executives |
| sa.cold-boot | Cold-boot testing of files | active | all-executives |

To spawn: Agent(prompt: "Read agents/sa/sa.<slug>/sa.<slug>.md and execute your boot sequence. Vault root: [path]. Activation record: agents/sa/sa.<slug>/activation-log/NNN-[spawner-id]-record.md.")
```

---

## Notes

- The catalog is maintained by Vela — if an agent is missing or stale, emit a `tropo.broadcast.crew` event (`category: ops`) (`channels/ops.md` retired per Rule 13)
- New agents can be commissioned by any executive — read `vault/files/e863a1e0.md` for the protocol
- Activation-log records are the history of every session run — browse `agents/sa/sa.<slug>/activation-log/` to see prior runs

---

*check-sa-catalog skill | v1.0 | Vela V28 | April 14, 2026*
