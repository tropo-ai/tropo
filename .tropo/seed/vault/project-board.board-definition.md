---
uid: c72f1a85
type: board-definition
name: project-board
intent: status
default_for: project
scope: project
recursion: subtree
author: tropo
status: active
created: 2026-04-20
created_by: argus-a29
schema_version: 1
extraction_scope: ship
governed_by: b0d1e4f2 # board-definition capsule
aligned_with: 74fd9b61 # Board Reconciliation v0.3 §6.1
description: "Default project status board. Renders open tasks, sub-projects, documents, task status summary."
sections:
 - title: "Open Tasks"
 query: "tasks in the subtree where state is active and stage is not one of [done, cancelled]"
 sort: "priority ASC, modified DESC"
 render: table
 columns: [priority, title, owner, stage, modified]
 null_result: "— No open tasks. —"
 - title: "Sub-Projects"
 query: "projects in the subtree, direct children only"
 group_by: "tag=pipeline-bucket first, then others"
 render: list-with-links
 null_result: "— No sub-projects. —"
 - title: "Documents"
 query: "documents in the subtree"
 sort: "modified DESC"
 limit: 20
 render: table
 columns: [title, owner, modified]
 null_result: "— No documents. —"
 - title: "Task Status Summary"
 query: "tasks in the subtree"
 group_by: "state then stage"
 render: table
 columns: [priority, title, owner, stage, state]
 null_result: "— No tasks. —"
---

# project-board — Default Project Status Board Definition

*Kernel-shipped default board-definition. Projects that declare no `status_board:` inherit this definition as their status board per [v0.3 §6 (74fd9b61)](../../../vault/files/74fd9b61.md).*

---

## What This Renders

The default status board serves the most common project-orientation use case: "what's going on in this project right now?" It surfaces four views in order:

1. **Open Tasks.** The live work queue — tasks that are active and not yet done. Sorted by priority then recent activity. First, because it answers "what needs my attention?" for both human readers and agents booting into project context.

2. **Sub-Projects.** The structural tree — direct child projects, with pipeline-bucket containers called out first (inbox / active / next / archive). Second, because it answers "what's the shape of this project?" for orientation.

3. **Documents.** Reference material — specs, ADRs, research memos, design briefs. Sorted by recent activity, capped at 20. Third, because it answers "what documents live under this project?" for deep-reads.

4. **Task Status Summary.** Full task inventory grouped by state and stage. Last, because it's below-the-fold inventory — useful for completeness scans, not for orientation.

---

## Why This Is the Default

The foundational spec ([Tropo Work Architecture Specification v0.3 (2d016ecf)](../../../vault/files/2d016ecf.md) §6.5) mandates that every project has a board. Requiring every project to author its own definition would produce 84 near-identical definitions in this vault alone. The default definition lets every project have a governed, deterministic status view from day one with zero per-project configuration.

Custom definitions are still valuable — a sprint team may want a board grouped by sprint number; a portfolio owner may want rollup-style milestones. Those are custom `board-definition` entries authored deliberately. The default exists so projects without special needs are covered by convention, not forced into ceremony.

---

## How Projects Inherit This

A project's frontmatter either declares `status_board: <uid>` or does not. If it does not, readers fall back to this definition via the `(type: board-definition, name: project-board, default_for: project)` triple lookup per [v0.3 §6.2](../../../vault/files/74fd9b61.md). No project-level action is required.

Projects that want a different status board declare their own `status_board:` UID pointing at a custom definition. The default remains available to all other projects.

---

## Pre-Seed Halt Behavior

If this definition is not in the ledger (e.g., a vault that has never run apply-update), the lookup halts fail-loud per [ADR-035 (a7c4e5b2)](../../../vault/files/a7c4e5b2.md). The vault admin (or their concierge) runs the [apply-update playbook (`.tropo/playbooks/apply-update.playbook.md`)](../../playbooks/apply-update.playbook.md) to land the seed. No silent fallback.

---

## Provenance

Authored by Argus A29 on 2026-04-20 as part of [Board Reconciliation v0.3 (74fd9b61)](../../../vault/files/74fd9b61.md) Stream 2 implementation. Ships with every Tropo-OS vault via the `.tropo/seed/vault/` propagation mechanism.

The sections above are lifted from [v0.3 §7.3](../../../vault/files/74fd9b61.md) which is the canonical spec. If future spec revisions change §7.3, this seed is revised in lockstep.

---

*project-board Board Definition | v1.0 kernel seed | Argus A29 | 2026-04-20*
*"The default that lets every project have a board without needing to author one."*
