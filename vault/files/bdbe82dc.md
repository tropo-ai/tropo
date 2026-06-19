---
uid: bdbe82dc
type: document
status: published
state: archived
title: Tropo-OS Release Folder Structure Schema
description: The definitive folder structure the build process creates. The contract between the build script and the cold-boot test.
owner: metis
created: 2026-04-12
modified: '2026-06-11'
tags:
- release
- schema
- folder-structure
- build-contract
- canonical
file_ext: md
schema_version: 2
extraction_scope: argo-reference
scope: ship
member_of:
- 809ca265
created_by: metis-g40
archived_at: '2026-06-11'
archived_by: metis-g77
modified_by: metis-g77
---

# Tropo-OS Release Folder Structure Schema

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [legacy-work-pipeline (deprecated 2026...](020274e0.md) → [4-build](a93faa83.md) → [3-active](a5f7a762.md) → [Tropo Work — The First App on Tropo-OS](809ca265.md) → **Tropo-OS Release Folder Structure Schema**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-all/tropo-work/legacy-work-pipeline (deprecated 2026-05-04)/4-build/3-active/Tropo Work — The First App on Tropo-OS/bdbe82dc — Tropo-OS Release Folder Structure Schema.md](../../00-tropo-nav/00-tropo-all/tropo-work/legacy-work-pipeline%20%28deprecated%202026-05-04%29/4-build/3-active/Tropo%20Work%20%E2%80%94%20The%20First%20App%20on%20Tropo-OS/bdbe82dc%20%E2%80%94%20Tropo-OS%20Release%20Folder%20Structure%20Schema.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-all/tropo-work/legacy-work-pipeline (deprecated 2026-05-04)/4-build/3-active/Tropo Work — The First App on Tropo-OS/bdbe82dc — Tropo-OS Release Folder Structure Schema.md](argo-os/00-tropo-nav/00-tropo-all/tropo-work/legacy-work-pipeline%20%28deprecated%202026-05-04%29/4-build/3-active/Tropo%20Work%20%E2%80%94%20The%20First%20App%20on%20Tropo-OS/bdbe82dc%20%E2%80%94%20Tropo-OS%20Release%20Folder%20Structure%20Schema.md)

**🔗 This file** — UID `bdbe82dc` · type `document` · state `archived` · status `published`

**↔ Siblings (35):**
  - **under [Tropo Work — The First App on Tropo-OS](809ca265.md):** [Add Outcome section to task capsule spec](1cffea32.md) · [Agent identity integration design](77d03e3d.md) · [Agent Identity Patterns — Research Report](f06be862.md) · [All tasks belong to one or more projects — 'no ...](d7da9885.md) · [Architecture spec v0.2 — incorporate research +...](c7a73c66.md) · [Capsule definition format v1](25b67be6.md) · + 29 more
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [Tropo Work — The First App on Tropo-OS (809ca265)](809ca265.md) |

*What does a stranger get when they unzip tropo-os? This document defines it.*
*This is the contract between the build script and the cold-boot test. If it's not in this schema, it doesn't ship. If it IS in this schema, the build must produce it and the cold-boot must find it.*

---

## The Structure

```
tropo-os-<version>/
│
├── .tropo/                              ← THE KERNEL (OS layer)
│   ├── orientation.md                   ← Read-this-first for any agent or human
│   ├── version.md                       ← Current version + changelog
│   ├── TROPO-CONTROL.md                 ← OS-level governance
│   │
│   ├── capsules/                        ← Type system (all capsule definitions)
│   │   ├── core.capsule.md
│   │   ├── task.capsule.md
│   │   ├── decision.capsule.md
│   │   ├── document.capsule.md
│   │   ├── project.capsule.md
│   │   ├── collection.capsule.md
│   │   ├── playbook.capsule.md
│   │   ├── note.capsule.md
│   │   └── board.capsule.md
│   │
│   ├── actions/                         ← How to create instances of each type
│   │   ├── create-task.action.md
│   │   ├── create-project.action.md
│   │   ├── create-decision.action.md
│   │   ├── create-document.action.md
│   │   ├── create-collection.action.md
│   │   ├── create-design-brief.action.md
│   │   ├── create-design-spec.action.md
│   │   ├── create-note.action.md
│   │   ├── generate-view.action.md
│   │   ├── refresh-view.action.md
│   │   └── delete-entry.action.md
│   │
│   ├── playbooks/                       ← Governed procedures
│   │   ├── agent-boot.playbook.md
│   │   ├── agent-retire.playbook.md
│   │   ├── agent-onboarding.playbook.md
│   │   ├── import-to-ledger.playbook.md
│   │   ├── build-release.playbook.md
│   │   ├── apply-update.playbook.md
│   │   ├── cold-boot-test.playbook.md
│   │   ├── first-playbook.playbook.md
│   │   ├── first-vault-setup.playbook.md
│   │   └── migrations/                  ← Update migration playbooks
│   │
│   ├── skills/                          ← Lightweight agent capabilities
│   │   ├── scan-channels.skill.md
│   │   ├── check-vault-health.skill.md
│   │   ├── regenerate-board.skill.md
│   │   ├── construct-briefing.skill.md
│   │   ├── register-file.skill.md
│   │   ├── create-governed-folder.skill.md
│   │   ├── maintain-channel.skill.md
│   │   ├── archive-board.skill.md
│   │   ├── write-session-memories.skill.md
│   │   └── debug-manifest.skill.md
│   │
│   ├── templates/                       ← File creation templates
│   │   ├── AGENTS.md
│   │   ├── CAPSULE.md
│   │   ├── executive-activation.template.md
│   │   ├── executive-charter.template.md
│   │   ├── executive-briefing.template.md
│   │   ├── executive.template.md
│   │   ├── task.template.md
│   │   ├── memory.template.md
│   │   └── sessions.template.md
│   │
│   ├── schema/                          ← Schema references
│   │   ├── vault-index-schema.md
│   │   ├── index-standard.md
│   │   ├── charter-schema.md
│   │   ├── task-schema.md
│   │   ├── agents-md-compatibility.md
│   │   └── template-instance-pattern.md
│   │
│   ├── kb/                              ← Knowledge base articles
│   │   ├── 00-index.md
│   │   ├── what-is-tropo.md
│   │   ├── how-tasks-work.md
│   │   ├── how-agents-work.md
│   │   ├── how-governance-works.md
│   │   ├── how-playbooks-work.md
│   │   ├── how-teams-work.md
│   │   ├── how-the-tropo-vault-works.md
│   │   ├── how-tropo-is-different.md
│   │   ├── how-tropo-work-works.md
│   │   ├── working-with-existing-files.md
│   │   ├── agent-lifecycle.md
│   │   └── glossary.md
│   │
│   ├── scripts/                         ← Execution-layer tooling
│   │   ├── build-release.py
│   │   └── populate-index-v1.1.py
│   │
│   ├── system/                          ← System-level agents and config
│   │   ├── README.md
│   │   └── vault-steward.template.md
│   │
│   └── platform-setup/                  ← Per-platform harness configuration
│       └── claude-code.md               ← (future: cursor.md, gemini-cli.md)
│
├── .tropo-studio/                        ← INSTANCE STATE (Organization layer — empty skeleton)
│   ├── memory/
│   │   └── MEMORY.md                    ← Vault-level memory index (empty, ready for use)
│   └── registries/                      ← (empty, ready for steward)
│
├── ledger/                              ← THE DATA LAYER
│   ├── 00-index.jsonl                   ← JSONL index (seed entries only)
│   ├── AGENTS.md                        ← Ledger write-gate governance
│   ├── CAPSULE.md                       ← Ledger folder governance
│   └── files/                           ← Seed vault entries (scope: ship)
│       ├── <uid>.md                     ← Getting Started project
│       ├── <uid>.md                     ← Seed tasks (3-5)
│       ├── <uid>.md                     ← Getting Started board
│       ├── <uid>.md                     ← Getting Started primary collection
│       ├── <uid>.md                     ← Getting Started tasks collection
│       └── ...                          ← Other scope:ship entries
│
├── agents/                              ← AGENT HOME (empty skeleton)
│   ├── 00-index.md
│   ├── AGENTS.md
│   ├── CAPSULE.md
│   └── .tropo-capsule/
│       └── memory/
│           └── MEMORY.md                ← Agent-level memory index (empty)
│
├── channels/                            ← COMMUNICATION (minimal seed)
│   ├── 00-index.md
│   ├── AGENTS.md
│   ├── CAPSULE.md
│   └── ops.md                           ← Operations channel (empty, ready for use)
│
├── boards/                              ← BOARDS (seed board for getting-started)
│   └── <getting-started>/
│       └── current.md
│
├── collections/                         ← COLLECTIONS (seed collections)
│   ├── AGENTS.md
│   └── CAPSULE.md
│
├── system/                              ← SYSTEM INFRASTRUCTURE
│   ├── 00-index.md
│   ├── AGENTS.md
│   ├── CAPSULE.md
│   ├── vault-steward/
│   │   └── activate.md
│   └── updates/                         ← Update pipeline infrastructure
│       ├── 00-index.md
│       ├── AGENTS.md
│       ├── CAPSULE.md
│       ├── applied/
│       ├── failed/
│       └── pending/
│
├── AGENTS.md                            ← Root governance (OS layer)
├── STUDIO.md                             ← Root governance (Organization layer)
├── CAPSULE.md                           ← Root governance (Folder layer)
├── CLAUDE.md                            ← Claude Code harness instructions
├── README.md                            ← Human-facing introduction
├── START-TROPO.md                       ← "Start here" for first-time users
├── operating-agreement.md               ← Governance contract (seed template)
└── MANIFEST.md                          ← Build manifest (generated by build script)
```

---

## Design Principles

1. **The kernel (`.tropo/`) is the OS.** It ships identical in every vault. Users don't modify it. Updates propagate through the pipeline. Everything inside `.tropo/` is maintained by Tropo.

2. **The skeleton (`.tropo-studio/`, `agents/`, `channels/`, `boards/`, `collections/`, `system/`) is the structure.** Empty directories with governance files, ready for the user to populate. The structure says: "this is where your agents live, this is where your channels go, this is where your boards are generated."

3. **The Vault is pre-seeded, not empty.** A fresh vault has a Getting Started project with a board, two collections, and 3-5 seed tasks. The user sees work they can interact with immediately, not an empty store.

4. **Root governance files are the front door.** `AGENTS.md`, `STUDIO.md`, `CAPSULE.md`, `README.md`, `START-TROPO.md` — these are the first things a human or agent reads. They orient to the vault before anything inside it.

5. **No content, only structure + seeds.** The release doesn't carry Argo's decisions, tasks, research, channels, or agent histories. It carries the OS, the structure, and enough seed content to demonstrate how the system works. The user's work fills the rest.

---

## What the Build Script Does

The build script reads this schema as its contract:

1. **Copy the kernel** — everything under `.tropo/` from the source vault (excluding `argo-private` tagged files)
2. **Copy the skeleton** — create the empty directory structure with governance files
3. **Copy seed vault entries** — query `"scope":"ship"` from the source index, copy matching files + build the seed index
4. **Copy root files** — AGENTS.md, STUDIO.md, CAPSULE.md, README.md, START-TROPO.md, CLAUDE.md, operating-agreement.md
5. **Generate MANIFEST.md** — list every file with path, size, checksum
6. **Write version.md** — stamp the version number

The schema IS the build spec. If a file isn't in this schema, the script doesn't copy it. If a directory isn't in this schema, the script doesn't create it.

---

## How the Cold-Boot Test Uses This

The cold-boot test playbook validates against this schema:

- Every directory in the schema exists in the build output
- Every required file exists
- The ledger index is consistent with the files in `vault/files/`
- The kernel is complete (all capsules, all actions, all playbooks present)
- The seed content is navigable (the Getting Started project has a board and collections)

If any check fails, the build doesn't ship.

---

## Change Management

This schema is a **canonical** artifact. Derived artifacts (the build script, the cold-boot test, the MANIFEST template) conform to it. When the schema changes, the derived artifacts update.

Adding a new top-level directory or a new kernel file requires amending this schema first. The build script doesn't improvise structure — it reads this document.

---

*Tropo-OS Release Folder Structure Schema | Draft v1 | Metis G40 + Mike Maziarz | April 12, 2026*
*"If it's not in the schema, it doesn't ship. If it IS in the schema, the build must produce it."*
