---
spec_version: 2
tier: capsule
folder_type: governed
layer: vault-admin
owner: human-owner
write_access: [human-owner, concierge, vault-admin-delegate]
read_access: all
purpose: "Vault-admin tier — the layer between Tropo-OS kernel (.tropo/) and individual agents (agents/<name>/). Contains vault-wide governance, memory, registries, and scripts specific to THIS vault."
uid: 911e97ca
governed_by: e6c3f410 # ADR-032 — Three-Layer Boot Configuration Model
---

# `.tropo-studio/` — Vault-Admin Tier

## What this folder is

**The middle layer of the three-tier Tropo-OS architecture** ([ADR-032](../../vault/files/e6c3f410.md)):

| Tier | Path | Owned by | Ships with Tropo-OS |
|---|---|---|---|
| 1 — OS | `.tropo/` | Tropo (framework) | Yes — same content every vault |
| **2 — Vault-admin** | **`.tropo-studio/` (this folder)** | **The human who runs this vault** | **Skeleton ships; content is yours** |
| 3 — Agent | `agents/<name>/` | Each agent | No |

The OS sets the floor. The vault sets the room. The agent sets the chair.

This folder is **yours to fill in.** Tropo-OS ships an empty scaffolding with this structure intact so your crew knows where things go. As you run agents and make decisions, vault-level memory accumulates here, your agent registry grows, your directives land, your vault-level scripts live at `scripts/`.

## What belongs here

- **`agent-boot.extension.md`** — your vault's Tier 2 boot extension. Declares defaults every agent on this vault uses at boot: channel scan list, required reads, fleet-ops requirement, etc. The boot playbook reads this; you fill it in as the crew's patterns stabilize.
- **`operating-principles.md`** — baseline operating principles every agent on this vault reads at boot. Ships with Tropo's crew-tested defaults; adapt or replace.
- **`directives/`** — standing instructions to all crew. One file per directive.
- **`memory/`** — vault-level memory accessible to every agent. Cross-agent patterns live here.
- **`registries/`** — agent registry, worker registry, other identity/index surfaces.
- **`bindings/`** — future binding contracts (reserved).
- **`runs/`** — playbook run records for your crew's activations + retirements.
- **`scripts/`** — vault-specific helper scripts (see `scripts/CAPSULE.md`).

## What does NOT belong here

- **OS-tier kernel content** — those live in `.tropo/` and ship with every release. Never duplicate kernel content here.
- **Agent-specific content** — agent charters, memories, transfers, status cards live in `agents/<name>/`. Not here.
- **Tropo-OS release artifacts** — those live in `releases/`.

## Write access

- **The human who runs this vault** — primary owner.
- **`concierge`** — the day-zero onboarding agent may write here during first-vault-setup.
- **Vault-admin delegate** — if you designate an agent to manage vault-level operations (e.g., "Chief of Staff"), they write here on your behalf.

Not a free-write zone for every agent. Changes to vault-admin tier are deliberate.

## First-boot state

This scaffolding ships with **empty-but-declared** content for every slot. A fresh Tropo Studio boots successfully because every Tier 2 file the boot playbook expects exists with defaults. You progressively fill in real content as your crew forms and your patterns stabilize.

## Reference

- Tropo-OS boot architecture: [ADR-032](../../vault/files/e6c3f410.md)
- Agent Activation Playbook: `.tropo/playbooks/agent-activation.playbook.md`
- Tier 1 boot-config: `.tropo/boot-config.md`

---

## Canonical Taxonomy (v1.8 lock — universal Tropo vocabulary)

Every Tropo Studio uses this taxonomy. It ships with the OS; no per-Studio customization.

**Tropo** is the operating system — the method, the way of working. Etymology: Greek τρόπος = "way / turn / manner." Tropo names the method, not any single instance.

**Each install of Tropo is a Studio.** A Studio is where the crew + tools + governed work all live. Each Studio is its own instance with its own governing rules, tools, agents, and history. (Filesystem identity: the install folder you're inside is THIS Studio.)

**Each Studio holds a Vault.** The Vault is the protected governed-content storage — every typed primitive, every governed artifact, the registry, the indexes. Eventually permission-gated; today protocol-gated.

| Concept | Term | Filesystem |
|---|---|---|
| The OS (method) | **Tropo** | (the name itself) |
| The install (instance) | **Studio** | the install folder (yours) |
| The protected governed-content storage | **Vault** | `vault/` (or `vault/` in pre-v1.8 vaults) |

**Martial-arts analogue:**
- Tropo = the art (method, e.g., Tae Kwon Do)
- Studio = the dojo (instance — where the practice happens)
- Vault = the lineage scrolls + honor roll (protected knowledge)
- Crew = masters + students (executive agents + sa.\* specialists)
- Tools = capsules + actions + skills + playbooks (forms, weapons, training tools)
- Discipline of practice = governance rules

**Vocabulary fix-on-encounter (v1.8 living-enforcement directive).** If you encounter pre-v1.8 vocabulary while doing your work in this Studio, update it in place per canonical taxonomy:
- `"ledger"` path or vocabulary → `"vault"` (path is `vault/` in v1.9+ Studios; pre-v1.8 vaults retain `vault/`)
- `"Workshop"` / `§Workshop` → `"Studio"` / `§Studio`
- `"workshop manifesto"` → `"studio manifesto"`
- `"Tropo-OS Studio"` / `"Tropo-OS Vault"` → `"Tropo Studio"` / `"the Vault"` (Tropo IS the OS; "OS" is redundant on install/instance terms; exception: `"Tropo-OS v1.X.Y"` versioned release names stay)

**Exception:** historical changelog rows that document past work (e.g., "v1.4 added §Workshop signage to capsule") preserve original naming as honest historical record. The rule is forward-looking; history stays honest.

**Why this directive exists:** the v1.8 canonical taxonomy lock is universal across Tropo installs. The PATH RENAME (`vault/` → `vault/`) ships at v1.9 (deferred from v1.8). Living agents are the safety net for any pre-v1.8 vocabulary surviving sweeps. Per Operating Principle 3 (Proactive Improvement Mandate) — agents become part of the enforcement substrate.

---

*`.tropo-studio/` CAPSULE | Vault-admin tier root | Ships with Tropo-OS skeleton | Canonical Taxonomy v1.8 lock*
