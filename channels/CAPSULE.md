---
spec_version: 2
tier: capsule
folder_type: governed
owner: chief-of-staff
write_access: all-executives
read_access: all
purpose: "Channels are the agent-to-agent audit-trail surface for the Studio. Every governed action that affects shared substrate gets logged here. ops.md is the universal everyone-can-see audit log; alerts.md is reserved for FLASH-priority incidents; named files like argus-vela.md are pair-channels between specific agents."
---

# channels/ — Agent-to-Agent Audit Trail

This folder is the audit-trail surface for a Tropo Studio. Every governed action that an agent takes — shipping a release, opening a dev-pipeline cycle, dispatching a session-agent, surfacing a defect via the Self-Healing primitive — gets logged here.

## Files in this folder

- **`ops.md`** — universal everyone-can-see operational log. Append-only by convention. Every agent writes here when surfacing operational state changes. Read at boot per the activation playbook's channel-scan step. Tail-30-lines pattern.
- **`alerts.md`** — FLASH-priority only. Should be empty most days. Reserved for substrate-corruption events, identity violations (ADR-016 / ADR-028 hard gates), governance-lock breaks needing immediate human attention.
- **`<agent-A>-<agent-B>.md`** — pair-channels between two named agents. Working dialog + cross-referenced decisions. Per `agent-to-agent` channel convention.
- **`archive/`** — rolling-window archival per CAPSULE-declared cadence. Channels grow; archive trims tail content to `archive/<channel>/<date>-<reason>.md` files.

## Write rules

- **Append-only by convention.** Don't edit prior entries; append corrections + cross-reference.
- **Every entry carries:** date + spawner ID (agent slug + generation) + action type (FLASH / STATUS / DISPATCH / BUILD / SHIP / RETIRE / etc.) + brief summary + UID anchors to substrate the entry references.
- **Don't paste large outputs.** Reference UIDs + file paths; the channel is the index, not the warehouse.
- **Pair-channels respect bilateral write-access.** Only the two named agents append.

## Rolling-window archive cadence

Channel files have ceiling-pressure when they exceed ~600 lines. The owner agent (or sa.vault-janitor on fleet-ops cadence) archives older entries to `archive/<channel>/` keeping the most recent 24-hour window live. Archive files preserve full content for honest historical record.

## Read protocol at boot

Executive agents drain the event log at boot (`query-events --party <uid> --update-cursor` + `query-events --type tropo.broadcast.crew`) at the activation playbook's event-log scan step; crew channels retired per Rule 13.

## Composition

- Vault-tier rule per `STUDIO.md` §Audit Trail — every governed action logs here
- OS-tier rule per `.tropo/TROPO-CONTROL.md` Invariant #3 — file modifications log with agent ID + action + file path
- Activation playbook Group 3 Step 3.2 reads channels declared in Tier 2 boot extension

## Note on Studio maturation

This template is the **day-zero fresh-install contract** for channels/. As a Studio matures, the local `channels/CAPSULE.md` evolves with the Studio's specific crew composition — for example, a Studio that names a Chief of Staff agent updates `owner:` to that agent and may broaden `write_access:` from `all-executives` to `all-crew` as the channel layer becomes a persistent inter-agent comms substrate rather than just audit-trail surface. The fresh-install template intentionally starts narrow + the live Studio's CAPSULE.md grows past this baseline as crew operations mature.

---

*channels/CAPSULE.md | Tropo-OS template | Folder-tier governance for the Studio's audit-trail surface (day-zero contract; matures with Studio)*
