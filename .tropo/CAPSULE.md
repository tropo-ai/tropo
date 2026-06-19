---
spec_version: 2
tier: capsule
folder_type: system
owner: tropo
write_access: [tropo-update-pipeline]
read_access: all
purpose: "Tropo-OS kernel — templates, schemas, skills, playbooks, concierge, steward"
uid: 71b3ca43
---

#.tropo/ — Kernel

The Tropo-OS kernel directory. Contains the OS runtime: TROPO-CONTROL.md, templates, schemas, skills, playbooks, concierge activation, steward configuration, and knowledge base.

## Operating Logic

- **Agents do not write here** except during an approved update apply (via the update pipeline).
- TROPO-CONTROL.md is the OS singleton — invariants, identity checkpoint, health protocol.
- `templates/` contains canonical file templates (AGENTS.md, CAPSULE.md, task, project, board, grooming-agent).
- `skills/` contains instruction sets that teach agents specific actions.
- `playbooks/` contains kernel-level playbooks (apply-update, migrations).
- `kb/` contains the knowledge base articles.
- `concierge/` contains the concierge activation file.
- `version.md` declares the current Tropo-OS version.

## Index Maintenance Rule

**`00-index.md` must reflect the actual contents of the kernel.** Any agent that adds, removes, or renames a file inside `.tropo/` — including any subdirectory — MUST update `00-index.md` before completing the action. This is not optional. A stale index is worse than no index.

**Two enforcement points:**

1. **Here (CAPSULE.md):** This rule applies to any agent touching the kernel. If you wrote a file in `.tropo/` and did not update `00-index.md`, your action is incomplete.

2. **Build playbook (Phase 2):** The build script regenerates `00-index.md` from the actual kernel directory contents immediately before packaging. The shipped index is always accurate at release time regardless of any in-development drift.

The CAPSULE.md rule governs development-time accuracy. The build playbook governs release-time accuracy. Both are required because neither alone covers all paths.
