---
uid: e615bfd4
layer: vault
tier: 2
owner: vault-admin
delegate: "[name of vault-admin delegate agent, or leave blank]"
vault: "[vault name]"
created: "[date on first edit]"
modified: "[date on first edit]"
created_by: concierge
governed_by: e6c3f410 # ADR-032 — Three-Layer Boot Configuration Model
aligned_with: 99341618 # Agent Activation Playbook v2.2
applies_to: all-agents
---

# Vault Boot Extension (Tier 2) — `[your vault name]`

*Layer 2 of the three-tier boot config ([ADR-032](../vault/files/e6c3f410.md)). Applies to every agent on this vault.*
*Read at Group 0, Step 0.2 of [.tropo/playbooks/agent-activation.playbook.md](../.tropo/playbooks/agent-activation.playbook.md).*
*Composes with: Tier 1 at [.tropo/boot-config.md](../.tropo/boot-config.md) (OS floor) and Tier 3 at `agents/<name>/agent-boot.extension.md` (agent specifics).*
*Owner: the human who runs this vault. Delegate to an operations agent when you have one.*
*Can add vault-required steps. Cannot remove OS-required steps.*

---

## Group Alignment

This extension uses Group 0–5 nomenclature matching the Agent Activation Playbook v2.2. The OS playbook declares the skeleton; this file fills vault-specific additions.

---

## Group 1 — No Vault-Level Additions (default)

Identity verification (hard gates ADR-016 / ADR-028) is entirely OS-defined. This vault adds no additional identity requirements by default.

Add your own identity checks here if your vault has conventions beyond the OS floor.

---

## Group 2 Additions (Context Loading)

**Vault root resolution:** handled in Group 0 Step 0.0 per v2.2. This section does not re-declare vault root; Step 2.2 only confirms the resolution.

**Canonical Taxonomy — required read (Group 2, FIRST in this group; v1.8 universal directive):**
- [`.tropo-studio/CAPSULE.md`](CAPSULE.md) §Canonical Taxonomy — Tropo (the method) > Studio (the install) > Vault (the protected governed-content storage). Internalize before any other Group 2 read. Vocabulary fix-on-encounter directive applies — fix pre-v1.8 vocabulary in place per the canonical map; preserve historical changelog rows as honest record. Every executive + sa.\* agent internalizes the taxonomy at boot.

**Vault operating principles — required read (default):**
- [`.tropo-studio/operating-principles.md`](operating-principles.md) — baseline principles every agent reads. **(v1.8 update: Principle 3 now includes the vocabulary fix-on-encounter directive — see CAPSULE.md §Canonical Taxonomy for the canonical map.)**

**Vault-level memory — required read (default):**
- [`.tropo-studio/memory/MEMORY.md`](memory/MEMORY.md) — vault-wide cross-agent memories. Read the index; read pinned or CRITICAL entries in full.

**Vault directives — required read (default):**
- All files in [`.tropo-studio/directives/`](directives/) — standing instructions to all crew.

**Mission brief — required (default):**
- `context/mission-brief.md` (create this file when you know your vault's mission).

---

## Group 3 Additions (Operational Grounding)

**Crew brief — declared default (optional):**
- `00-crew-brief.md` at vault root (if your vault has a crew brief).

**Fleet-ops execution — optional:**
- If your vault runs a scheduled fleet, declare `playbooks/fleet-ops.playbook.md` here and require executives to run it at boot. Skip if no scheduled fleet.

**Vault-wide default channels** (every agent scans these unless suppressed by Tier 3):
- `channels/ops.md` — operational updates
- `channels/alerts.md` — FLASH-priority only, should be empty most days
- *(Add or remove channels as your vault's communication model evolves.)*

Agent-specific channels (agent-to-agent pairs) are declared in each agent's Tier 3 extension.

**Channel read bounding (recommended):**
- **Since-predecessor rule:** read only entries dated on or after the predecessor's `last_session`. Earlier entries were processed already.
- **Silent-skip on empty delta:** if a channel has no new entries since `last_session`, skip the read.

These rules cap channel-read cost at "last 1–3 days" in typical cases.

**Vault navigation — declare your indexes here:**
- `vault/00-project-tree.jsonl` — project hierarchy backbone (if your vault uses the Vault pattern)
- `vault/00-cascade-roots.jsonl` — cascade indexes for deep-domain loading

---

## Group 4 — No Vault-Level Additions (default)

Self-diagnostic is agent-owned (Tier 3). Add vault-wide diagnostic steps here if you want every agent to run them.

---

## Group 5 — No Vault-Level Additions (default)

Startup signal format is declared in each agent's Tier 3 extension.

---

## Vault Context

**Active crew:** *(populate as your crew forms)*

**Ledger:** *(path to your ledger, if you use one)*

**Agent registry:** [`registries/agent-registry.yaml`](registries/agent-registry.yaml)

**Vault administrator:** *(the human — you — and any delegates)*

---

## What this file is NOT

This file is a **generic Tier 2 scaffold** that shipped with Tropo-OS. It declares the minimal structural skeleton every vault needs. As your crew develops patterns, amend this file to capture them.

**Do not delete this file.** The boot playbook's Tier Reachability rule HALTs activation if this file is missing from an established vault. If you genuinely don't want vault-level additions, leave the file with the declared defaults.

---

*Tier 2 Vault Boot Extension | Skeleton template shipped with Tropo-OS*
*"The vault sets the room."*
