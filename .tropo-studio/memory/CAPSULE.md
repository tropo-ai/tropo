---
spec_version: 2
tier: capsule
folder_type: governed
owner: vault-admin
write_access: all-agents
read_access: all
purpose: "Studio-level memory — cross-agent patterns and organizational knowledge. Every agent reads memory-current.md at boot."
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

**There is exactly one index, and it is `memory-current.md`.** Each memory's full text is a
standalone file in `entries/`; the index carries one line per memory, linking to it.

An entry looks like this:

```yaml
---
uid: <8-hex, minted with `python3 vault/tools/tropo-mint-id.py --kind file`>
type: memory
subtype: feedback | procedural | semantic | architectural | relationship | reference
scope: studio
created: YYYY-MM-DD
created_by: your-agent-id
---
```

Its index line looks like this:

```
- [<uid>](entries/<uid>.md) — one-line summary a reader uses to decide whether to open it
```

## Boot contract

Every agent, at every boot, reads **`memory-current.md`** — the index, and only the index. Open a
full entry from `entries/` when its one-line summary is not enough. Keep the index readable at boot:
if it grows past a few hundred lines, compress the lines, never drop an entry.

## Adding a memory

Write the entry into `entries/`, then append its one line to `memory-current.md`. Both steps, always.

> **Why both steps, and why only one index.** An entry with no index line is invisible at boot even
> though its file is perfectly intact, and an index line in a file nothing boots from is the same
> failure wearing a different hat. In the studio that builds Tropo, a binding ruling from the founder
> was appended to a second index that agents did not read; the whole crew booted without it for eight
> days and nothing could show it was missing. That is why this folder ships one index and not two.

## Do not create a second index

If you find yourself adding a file that lists memories — `MEMORY.md`, `index.md`, anything of that
shape — stop. `memory-current.md` is the index. A second one is a place for memories to go missing.
