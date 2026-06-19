---
uid: dir-capsule-01
spec_version: 2
extraction_scope: ship
tier: capsule
folder_type: directors
name: "directors"
owner: vela
write_access: [mike, vela, metis, argus]
read_access: all
purpose: "Director agents — standing specialist agents that serve the vault and its users directly"
capability_level: L1
permitted_types: [director-agent]
created: 2026-04-16
last_modified: 2026-04-16
created_by: metis-g42
---

# agents/directors/ — Director Agents Capsule

*Read this file before creating or modifying any director agent in this folder.*

---

## What This Folder Is

Director agents are standing specialist agents that serve specific purposes within the vault. They are distinct from executive agents (Metis, Argus, Vela) who govern the vault itself. Directors serve users and specific domains directly.

**Directors are first-class agents.** They have the same infrastructure requirements as executive agents — soul, memory, channels, session history. They are not lesser. They have a different purpose.

---

## What Belongs Here

Each subfolder is one director agent. The naming convention is `d.<name>/`.

Every director agent subfolder MUST contain:

| File | Purpose | Required |
|------|---------|---------|
| `activate.md` | Identity and boot pointer — who this director is, which playbook governs activation | YES |
| `soul.md` | The director's character — editable by the vault owner | YES |
| `CAPSULE.md` | Governance for this director's folder | YES |
| `AGENTS.md` | Operating rules for any agent entering this folder | YES |
| `channels/inbox.md` | Persistent conversation log | YES |
| `sessions/session-history.md` | Running log of all sessions | YES |
| `.tropo-capsule/memory/MEMORY.md` | What the director has learned — editable | YES |

A director agent that ships without all of the above is non-compliant.

---

## How Director Agents Activate

**Director agents activate via Tropo playbooks.** Not via custom markdown files.

The `activate.md` file is a LIGHT identity file — it names the director, declares its soul and memory files, and points to the governing playbook. The playbook contains the actual activation logic.

The governing playbook lives at `.tropo/playbooks/` (OS-level) or `playbooks/` (vault-level).

**An activate.md that contains activation logic instead of pointing to a playbook is non-compliant.** This is the most common error when creating a new director. Read the playbook spec at `.tropo/playbooks/agent-boot.playbook.md` before creating any director.

---

## The Director Infrastructure Model

Directors use the same infrastructure patterns as executive agents:

| Component | Executive agents | Director agents |
|-----------|-----------------|-----------------|
| Soul | `agents/<name>/<name>-soul.md` | `agents/directors/d.<name>/soul.md` |
| Memory | `.tropo-capsule/memory/MEMORY.md` | `.tropo-capsule/memory/MEMORY.md` |
| Channels | `channels/<name>-<other>.md` | `channels/inbox.md` (user-facing) |
| Session history | `transfers/living-transfer.md` | `sessions/session-history.md` |
| Activation | Playbook-driven | Playbook-driven |

Directors are simpler because they serve a narrower purpose — but the infrastructure is equivalent.

---

## What Does NOT Belong Here

- Executive agent files (Metis, Argus, Vela, Orpheus) — those live in `agents/<name>/`
- Session agents (sa.*) — those live in `agents/sa/`
- Grooming agents — those live in `agents/grooming/`
- Visitor registrations — those live in `agents/visitors/`

---

## The Soul and Memory Are User-Editable

This is a design choice, not an oversight. Director agents serve the vault owner and users. They should be customizable. The `soul.md` and `.tropo-capsule/memory/MEMORY.md` files in each director subfolder are explicitly intended to be edited by the human who owns the vault.

Every director's `soul.md` should contain the note: *"This is your director's starting character. Edit this file to make it yours."*

---

*agents/directors/ Capsule | Owner: Vela | Created: 2026-04-16 by Metis G42*
*"Directors are first-class agents. Different purpose. Equal dignity."*
