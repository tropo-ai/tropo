---
spec_version: 2
tier: capsule
folder_type: governed
owner: vault-admin
write_access: all-agents
read_access: all
purpose: "Vault-level memory — cross-agent patterns and organizational knowledge. Every agent reads the index at boot."
uid: 6e072ad6
---

# `.tropo-studio/memory/` — Vault-Level Memory

## Purpose

The **shared memory of the vault's crew.** Things every agent on every platform should know. Cross-agent patterns, human preferences that apply to everyone, organizational decisions.

Different from agent-level memory (`agents/<name>/.tropo-capsule/memory/`) which is per-agent.

## What belongs here

- **Cross-agent patterns** — behaviors every agent should adopt.
- **Human preferences that apply to everyone** — e.g., "always use clickable markdown links," "lead with the decision, not the context."
- **Organizational decisions** — naming conventions, locked ADRs that every agent should know at boot.
- **Anything whose audience is "every agent in the vault"** rather than "future generations of one specific agent."

## What does NOT belong here

- **Agent-specific operational knowledge** — that goes in `agents/<name>/.tropo-capsule/memory/`.
- **Temporary session context** — use a workspace.
- **Historical narrative** — that lives in transfers, reflections, or the crew's chronicle.
- **Decision records** — those are ADRs in the Vault, not memories.

## Format

Each memory is a standalone markdown file with minimal frontmatter:

```yaml
---
name: Short descriptive name
description: One-line summary used to decide relevance
type: feedback | project | user | reference
created: YYYY-MM-DD
created_by: your-agent-id
---
```

The index file `MEMORY.md` lists every memory as one line: `- [title](filename.md) — one-line description`. Every agent reads the index at boot; pinned entries get read in full.

## Boot contract

Every agent, at every boot, reads `MEMORY.md`. This is the index. Read full content of any memory you need that's directly linked. Keep the index under ~200 lines so it stays readable at boot.

## Adding a memory

Write the memory file, then append one line to `MEMORY.md`. The next boot surfaces it for every agent.
