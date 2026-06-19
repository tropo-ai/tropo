---
uid: "<FILL: assign a UID when you register this file (see vault/AGENTS.md)>"
tier: capsule
folder_type: vault-root
owner: human-owner
write_access: [human-owner, concierge, designated-agents]
read_access: all
purpose: "Vault-root governance — what belongs at this level, who writes here, and how your vault as a whole is organized."
spec_version: 2
---

# Vault Root — Governance Capsule

Welcome. This file governs the root of your vault — the top level, where your folders live.

If you are a **new user** exploring a freshly-unzipped vault, you do not need to read this top to bottom. Open [README.md](README.md), then say *"read START-TROPO.md"* to your AI tool. The concierge will take it from there.

If you are an **agent booting into this vault for the first time**, read this file in full before writing anything at vault root.

---

## What a vault-root CAPSULE is for

Every governed folder in a Tropo-OS vault has a `CAPSULE.md` that declares three things: what belongs in the folder, who can write to it, and how changes happen. This file does the same job — but for the **vault as a whole**, not just one folder.

In plain terms: this file is the charter for your vault's top level. It keeps the root tidy, keeps governance honest, and gives every agent a single place to check before creating a file at this level.

---

## Write access at vault root

The vault root is **not a free-write zone.** Most work belongs inside a specific folder (see the map below) — not at the top level.

The following may write at vault root:

- **The human owner** — you. This is your vault.
- **The concierge** — the onboarding agent at [.tropo/concierge/activate.md](.tropo/concierge/activate.md). It may write root-level files during first-time setup (for example, filling in [STUDIO.md](STUDIO.md) with your organization's details).
- **Designated agents** — any agent you explicitly authorize to edit root-level files. Authorization is a deliberate act, not a default.

Any other agent should write inside a folder, not at the root. If an agent believes a file genuinely belongs at the root, it should propose the addition (via a decision entry in `vault/`, or by asking you directly) rather than creating the file unilaterally.

---

## What belongs at vault root

Only a small, stable set of files:

- **The three governance companions** (this section explains them below).
- **[STUDIO.md](STUDIO.md)** — your organization-level defaults and constraints.
- **[README.md](README.md)** — the first thing a stranger sees.
- **[START-TROPO.md](START-TROPO.md)** — the user's entry point.
- **[LICENSE](LICENSE)** — licensing terms.

Everything else lives inside a folder. Not at the root.

**What does not belong at root:**
- Working files, drafts, notes, or scratch content.
- Agent memories, session state, or operational logs.
- Project artifacts, tasks, or decisions — those live in `vault/` (see the typed-pipeline model in [vault/files/60228176.md](vault/files/60228176.md)).

If you are not sure where a file goes, ask the concierge.

---

## The three governance companions

Three files sit side-by-side at vault root. Each does a different job. Agents read them in order at boot:

| File | Role |
|------|------|
| [AGENTS.md](AGENTS.md) | **Write rules.** Tells any agent what it must read before operating in this folder, and that it must not modify AGENTS.md itself. Maintained by Tropo. |
| [CAPSULE.md](CAPSULE.md) | **Vault-root governance** (this file). What belongs here, who writes, how changes happen. |
| [CLAUDE.md](CLAUDE.md) | **Claude Code boot pointer.** A short instruction file that points Claude Code at the concierge and the activation sequence. |

These three are deliberately kept small and readable. Together they form the vault's front door.

---

## Organization-level defaults

Vault-wide rules — file naming, required frontmatter, default lifecycle, default write access, audit trail, agent registration — live in [STUDIO.md](STUDIO.md), not here.

This file governs the root as a folder. [STUDIO.md](STUDIO.md) governs the vault as a whole. A folder's own `CAPSULE.md` may override the defaults in [STUDIO.md](STUDIO.md), but may not override its hard constraints (see [STUDIO.md](STUDIO.md) for the specific rules).

Edit [STUDIO.md](STUDIO.md) to match how your organization works. Tropo will not modify it for you.

---

## Your first contact: the concierge

You do not have to read the vault to use the vault.

The **concierge** is the first agent the vault hands you. It lives at [.tropo/concierge/activate.md](.tropo/concierge/activate.md). Point your AI tool at this folder and say *"read START-TROPO.md"* — the concierge will greet you, orient you, and walk you through creating your first agent or running your first playbook.

Any time you are unsure where something goes, what an agent is for, or how to get started — ask the concierge.

---

## How the vault is organized

A fresh vault ships with seven top-level folders of user content, plus a `vault/` folder for your governed work store. Each folder carries its own `AGENTS.md` + `CAPSULE.md` pair that explains what it is for in more detail.

| Folder | What lives here |
|--------|-----------------|
| [agents/](agents/) | Your agents. Each agent is a markdown file with structured metadata — create the file and the agent exists. Visiting agents register in `agents/visitors/`. |
| [boards/](boards/) | Views across your work — status dashboards, team boards, cross-cutting rollups. Boards render state; they do not own it. |
| [channels/](channels/) | Persistent inter-agent communication — reverse-chronological message logs so you (and your agents) can see who said what to whom. Not for work tracking. |
| [decisions/](decisions/) | Locked decisions and their reasoning. The durable record of what was decided and why. |
| [playbooks/](playbooks/) | Repeatable procedures. A playbook describes how a kind of work gets done, so it can run again without you. |
| [projects/](projects/) | Your projects — each a graph node that connects agents, decisions, playbooks, and work in the Vault. |
| [system/](system/) | Vault operations — the vault steward, update staging, and other infrastructure that keeps the vault healthy. |

**Work management lives in [vault/](vault/)** — tasks, project plans, design briefs, and other work artifacts. The Vault is the typed pipeline that Tropo Work runs on. See [vault/files/60228176.md](vault/files/60228176.md) for the full picture.

Governed infrastructure (playbook definitions, skills, schemas, templates, knowledge base) lives under `.tropo/`. You can read it. You generally do not need to edit it.

---

## How changes at root happen

Changing a root-level file is a deliberate act, not a background edit.

1. **Governance files** ([AGENTS.md](AGENTS.md), [CAPSULE.md](CAPSULE.md), [CLAUDE.md](CLAUDE.md)) are maintained by Tropo's update pipeline or by the human owner. Agents do not modify them.
2. **[STUDIO.md](STUDIO.md)** is yours. Edit it directly, or ask the concierge to help.
3. **Adding a new file at root** requires a decision entry in `vault/` explaining why the file cannot live inside an existing folder. The default answer is: it can. Put it in a folder.
4. **Adding a new top-level folder** is a vault-structure change. Propose it via a decision entry and, where appropriate, add it to [STUDIO.md](STUDIO.md)'s System Map.

The goal is to keep the root small enough that a stranger can understand the whole vault at a glance.

---

## Welcome

This is your vault. The file is the agent. The folder is the workspace. The vault is the OS — and you are its owner.

---

*Vault-root CAPSULE.md | Governs the top level of your Tropo-OS vault.*
