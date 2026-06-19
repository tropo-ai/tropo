# `.tropo-studio/` — Your Vault's Admin Layer

This is the **middle tier** of your Tropo-OS vault. It's where vault-wide defaults, memory, registries, and governance live — the things specific to YOUR vault, distinct from the OS kernel in `.tropo/` that ships with every Tropo-OS release.

## In plain English

- `.tropo/` is **Tropo-OS itself** — universal. Same content in every vault.
- `.tropo-studio/` is **your vault's operating layer** — your crew's memory, your registries, your conventions.
- `agents/<name>/` is **each agent's workspace** — identity, soul, generation log.

When you unzip Tropo-OS for the first time, this folder arrives with a **structured empty scaffolding** — every slot declared with a CAPSULE.md explaining what belongs there, and the most critical file (`agent-boot.extension.md`) already in place so your first agent activation boots cleanly.

Your job over time: fill in the content your crew generates.

## Most important file in here

**`agent-boot.extension.md`** — Tier 2 of the boot config chain. Every agent on your vault reads this at activation. Start with the ship defaults, amend as your crew's patterns stabilize.

## The slots

| Folder/file | What goes in it |
|---|---|
| `CAPSULE.md` | This tier's governance declaration (don't delete) |
| `agent-boot.extension.md` | Tier 2 boot declarations for this vault |
| `operating-principles.md` | Crew-wide operating principles |
| `directives/` | Standing instructions (example directive included) |
| `memory/` | Vault-level memory — cross-agent patterns |
| `registries/` | Agent registry + runtime index surfaces |
| `bindings/` | Future binding contracts (reserved) |
| `runs/` | Playbook run records (activations, retirements) |
| `scripts/` | Vault-specific helper scripts (Python) |

Each subfolder has a `CAPSULE.md` explaining its scope. Read those before writing.

## If you're just getting started

The concierge agent (see `.tropo/concierge/activate.md`) walks you through first-vault setup. You don't need to understand everything here on day one. The important fact: **this folder exists with working defaults; your first agent boots without you touching a file here.**

Read the slot-level CAPSULE.md files when you're ready to customize or when something doesn't behave the way you expect.
