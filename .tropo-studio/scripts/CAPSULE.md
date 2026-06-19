---
spec_version: 2
tier: capsule
folder_type: governed
owner: vault-admin
write_access: [vault-admin-delegate, human-owner]
read_access: all
purpose: "Vault-admin-tier Python helpers — board renderers, navigation utilities, ad-hoc vault-scoped tooling. Mirrors.tropo/scripts/ at the vault-admin tier."
uid: ffecdf39
governed_by: e6c3f410 # ADR-032 — Three-Layer Boot Configuration Model
---

# `.tropo-studio/scripts/` — Vault-Admin Helpers

## Purpose

Python helper scripts scoped to **this vault's** operational environment. Board renderers, graph-traversal utilities, ad-hoc tooling the vault admin (or their delegate) needs for this vault's day-to-day.

This folder mirrors the three-tier architecture at the scripts layer:

| Tier | Boot config | Scripts |
|---|---|---|
| OS (ships with Tropo-OS) | `.tropo/boot-config.md` | `.tropo/scripts/` |
| **Vault (this folder)** | `.tropo-studio/agent-boot.extension.md` | **`.tropo-studio/scripts/`** |
| Agent | `agents/<name>/agent-boot.extension.md` | `agents/<name>/scripts/` (create on demand) |

**These scripts do NOT ship with Tropo-OS releases.** They are this-vault-only. If a script here proves to be a general Tropo-OS capability, propose graduation to `.tropo/scripts/`.

## What belongs here

- **Board renderers** specific to your vault's board patterns.
- **Vault-specific navigation helpers.**
- **Ad-hoc utilities** useful for this vault's crew but not every Tropo-OS user.
- **Migration scripts** tied to vault-specific data state.

## What does NOT belong here

- **General Tropo-OS capabilities** — belong at `.tropo/scripts/` (kernel-tier, ships).
- **Engineering tooling** (Next.js app build, etc.) — belong at your repo root if you have a code repo.
- **Scripts with hardcoded absolute paths** — resolve paths dynamically via `settings/env.md` or `--vault-path` args.

## Write access

- **Vault-admin delegate** — typically your operations-class agent (Chief of Staff, Vault Steward).
- **Human owner.**

## Governance rules

1. **Vault-scoped only.** Before adding a script here, ask: *"Would any Tropo-OS vault benefit from this, or only this one?"* If the answer is "any," propose graduation to `.tropo/scripts/`.
2. **Portable within the vault.** Don't hardcode the operator's machine path. Resolve dynamically.
3. **Python.** Keep the language consistent. Engineering-layer tooling belongs elsewhere.
4. **Document.** Every script has a docstring.
5. **Graduate what generalizes.** Kernel graduation is the evolution path — not parallel copies.

## First-boot state

Ships empty except for this CAPSULE.md. Add scripts as your vault's operational patterns stabilize.
