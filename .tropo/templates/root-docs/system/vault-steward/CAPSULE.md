---
spec_version: 2
tier: capsule
folder_type: governed
owner: tropo
write_access: tropo
read_access: all
purpose: "Vault Steward subsystem — the kernel agent that applies Tropo-OS updates, runs vault rebuilds, and maintains substrate integrity invariants. Read-only for all non-Tropo agents."
---

# system/vault-steward/ — Vault Steward Subsystem

This folder houses the Vault Steward — the kernel agent that maintains substrate integrity for this Studio. The Vault Steward applies Tropo-OS updates from `system/updates/pending/`, runs vault rebuilds (`rebuild-vault.py`), and enforces substrate-class invariants (UID uniqueness, schema conformance, governance lock integrity).

## Files in this folder

- **`vault-steward.md`** — agent activation file (authored at first Vault Steward operation in this Studio; uses the standing-agent.template.md shape)
- **`logs/`** — operation logs (per-run records of update applies, vault rebuilds, integrity audits). Created on first operation.
- **`workspace/`** — freeform scratch storage for in-flight operations. Created lazily.

## What the Vault Steward does

- **Apply updates** from `system/updates/pending/` per the [apply-update playbook](../../../playbooks/apply-update.playbook.md)
- **Run vault rebuilds** — `npm run vault:rebuild` invokes the Steward to rebuild `vault/00-index.jsonl` + derived registries
- **Enforce substrate invariants** — UID uniqueness across the vault, frontmatter schema conformance per registered types, governance lock integrity (locked artifacts cannot be silently modified)
- **Audit integrity at cadence** — daily / weekly per fleet-ops registry; reports to `channels/ops.md`

## Write rules

- **Only Tropo + Vault Steward write here.** Other agents do NOT modify Steward files; they invoke the Steward via the update pipeline or the vault-rebuild gesture.
- **Steward state is preserved.** Don't delete logs/ entries; substrate-operation audit trail is load-bearing for substrate-class debugging.

## Composition

- STUDIO.md System Map row 8 references this subsystem
- `.tropo/TROPO-CONTROL.md` §6 cites this folder as the substrate-steward surface
- L1 canonical entry [vault/files/eca73d77.md] documents the Vault Steward as one of the seven Tropo subsystems

---

*system/vault-steward/CAPSULE.md | Tropo-OS template | Folder-tier governance for the Vault Steward subsystem*
