---
uid: 7c0e314a
name: "kernel"
type: capsule-definition
extends: core
version: 2.0
tier: os
author: tropo
created: 2026-04-12
modified: 2026-04-16
status: locked
schema_version: 2
governed_by: 222873b9
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# kernel — Capsule Definition

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Extends | `core` |

*The self-governing type. Kernel files ARE the operating system — capsule definitions, actions, playbooks, skills, templates, schema, KB articles, orientation. They govern everything else. This capsule governs them.*

## Intent

Track and govern the files that compose Tropo-OS itself. Every other capsule type defines how work artifacts behave. This capsule defines how the OS artifacts behave — the files that ship in `.tropo/` and that every other file depends on.

The bootstrap: `kernel.capsule.md` is governed by `kernel`. The type governs itself. This is the one self-referential type in the system, and it exists because OS-level files need governance rules that are different from work artifacts.

**Use kernel when:**
- The file IS part of the operating system (lives in `.tropo/` or is an OS-level governance file)
- The file ships in every Tropo vault identically
- The file is maintained by Tropo (the project), not by the vault owner
- Modifying the file is a versioned amendment, not a casual edit

**Do NOT use kernel for:**
- Work artifacts created by users or agents — use `task`, `document`, `decision`, etc.
- Vault-level configuration (`.tropo-studio/`) — that's instance state, not OS
- Agent-specific files (`agents/`) — that's identity, not OS

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `kernel_type` | string | What kind of kernel file: `capsule`, `action`, `playbook`, `skill`, `template`, `schema`, `kb`, `orientation`, `script`, `system` |
| `tier` | string | Always `os` for kernel files |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `version` | string or number | The version of this specific file (e.g., `1`, `1.1`, `2.0`) |
| `spec` | UID | If this file implements a spec, the spec's UID |
| `author` | string | Who wrote it (agent-id or `tropo` for OS-shipped files) |
| `extends` | string | For capsule definitions: what parent type this extends |
| `domain` | string | For playbooks: what domain this operates in |

## State Machine

```
build → deploy → done → (superseded: done + state: archived)
```

| Stage | State | Meaning |
|-------|-------|---------|
| `build` | `active` | Under development, not yet reliable |
| `deploy` | `active` | Stable, shipped, in use — still mutable between versions |
| `done` | `active` | Locked — immutable; amendments require a new version |
| `done` | `archived` | Superseded by a newer version |

### Valid transitions

- `build` → `deploy` (author with reviewer approval)
- `deploy` → `done` (vault principal only — locks the file)
- `done` → `done, state: archived` (when superseded; requires `superseded_by:` field)
- `build` → `done, state: archived` (abandoned draft)

### Invalid transitions

- `done` → `build` or `deploy` (never un-lock — version forward)
- `done, state: archived` → any active state

## Governance Rules (in addition to core)

1. **Kernel files are owned by Tropo.** `owner: tropo` — not by an individual agent. No agent can modify a kernel file without a versioned amendment approved by the vault principal.

2. **Kernel files ship by convention.** Every entry with `type: kernel` goes in the build. No `scope: ship` tag needed — kernel IS ship. The build script copies all kernel entries unconditionally. This is the one type where shipping is automatic, not tag-driven.

3. **Amendments, not edits.** A locked kernel file is never edited in place. To change it: create a new version (bump the `version` field), publish it, lock it when stable, supersede the old version. The capsule versioning rules (spec §3.6) apply. Existing references to the old version remain valid under the old rules until explicitly migrated.

4. **The bootstrap.** `kernel.capsule.md` is `governed_by: kernel`. This is the intended self-reference. The kernel type governs the kernel type. No infinite regress — the validation chain stops at `kernel` because `kernel` extends `core`, and `core` is the root with no parent. The check-in validates: `core` rules first, then `kernel` rules. Both pass. Done.

5. **Kernel files carry the OS.** If every `kernel`-type entry were extracted from the Vault and assembled into a folder structure, the result would be a complete `.tropo/` kernel directory. The Vault is the source of truth; the filesystem is the deployment target.

## Validation Checks (run at check-in)

In addition to core checks:

1. `kernel_type` is present and is one of the valid values
2. `tier` is present and equals `os`
3. `owner` is `tropo` (or the vault principal for amendments in progress)
4. `stage:` is one of: `build`, `deploy`, `done`
5. `state:` is one of: `active`, `archived`
6. If `stage: done` and `state: active`: no body content has changed since the prior check-in (enforces immutability)
6. If `version` is present, it follows semver or simple integer versioning

## Concurrency Policy

Pessimistic. Kernel files are never edited concurrently. One author at a time, one amendment at a time. If two agents need to amend the same kernel file, they coordinate through the channel — the second waits for the first to publish.

## Relationship to Other Types

- **vs. every other type:** kernel files GOVERN other types. A `task.capsule.md` of type `kernel` defines what a `task` of type `task` must be. The kernel is one layer above the work.
- **vs. `document`:** KB articles use the canonical `kb-article` type (governed by `4cb20382`) rather than `kernel`. They live at `vault/files/<uid>.md` (migrated from `.tropo/kb/` at v1.19.0) and ship as Tropo-maintained content. The `kernel` type applies to OS files under `.tropo/` (capsules, playbooks, skills, scripts) — files maintained by Tropo, not by the vault owner, that ship identically in every vault.
- **vs. `playbook`:** a playbook could be `type: playbook` in the Vault. But if it ships in `.tropo/playbooks/` as part of the OS, it's `type: kernel` with `kernel_type: playbook`. The `playbook` capsule type is for user-created playbooks; `kernel` with `kernel_type: playbook` is for OS-shipped playbooks.

## How to Create a Kernel Entry

Kernel entries are not created through an action file. They are created by Metis (or the vault principal) during OS development and registered in the Vault manually or via the kernel registration script at `.tropo/scripts/`. This is deliberate — kernel files are not user-facing primitives. Users don't create kernel files. The OS ships them.

## Inheritance

Extends `core`. Inherits all core rules. Not currently extended by subtypes — all kernel files share the same governance. If domain-specific kernel governance emerges (e.g., playbook-specific rules vs. capsule-specific rules), subtypes can be added via the standard capsule inheritance mechanism.

---

*kernel capsule definition | DRAFT v1 | Tropo OS | April 12, 2026*
*"The type that governs the types. The bootstrap."*
