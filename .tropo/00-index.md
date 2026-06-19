---
uid: 6eeaf1ca
type: document
status: published
title: "Tropo Kernel — System Index"
description: "One-stop navigation for the.tropo/ kernel. When you have a system question, start here."
owner: tropo
created: 2026-04-13
modified: 2026-04-13
tags: [kernel, index, navigation, system, orientation, scope-ship]
file_ext: md
schema_version: 1
created_by: argus-a22
---

# Tropo Kernel — System Index

*When you have a question about how Tropo works, start here.*
*This file is the navigation hub for the entire `.tropo/` kernel.*

---

## The Short Version

```
You have a question about how Tropo works.
→ Find the right section below.
→ Follow the pointer to the exact file.
Do not guess. The answer is in the kernel.
```

---

## 1. OS Rules and Identity

| Question | File |
|----------|------|
| What are the invariants that nothing can override? | [`TROPO-CONTROL.md`](TROPO-CONTROL.md) |
| How does an agent enter and orient to a vault? | [`kb/how-vault-entry-works.md`](kb/how-vault-entry-works.md) |
| How does governance work (the three layers)? | [`kb/how-governance-works.md`](kb/how-governance-works.md) |
| What version of Tropo-OS is this vault running? | [`version.md`](version.md) |
| What is the 800-word OS primer? | [`orientation.md`](orientation.md) |

---

## 2. The Type System (Capsules)

| Question | File |
|----------|------|
| What capsule types exist and what are their rules? | [`capsules/00-index.md`](capsules/00-index.md) |
| What are the universal rules every type inherits? | [`capsules/core.capsule.md`](capsules/core.capsule.md) |
| Task rules, state machine, verification | [`capsules/task.capsule.md`](capsules/task.capsule.md) |
| Project rules, required board + collections | [`capsules/project.capsule.md`](capsules/project.capsule.md) |
| Decision rules (ADR lifecycle) | [`capsules/decision.capsule.md`](capsules/decision.capsule.md) |
| Document rules | [`capsules/document.capsule.md`](capsules/document.capsule.md) |
| Board rules (generated snapshots) | [`capsules/board.capsule.md`](capsules/board.capsule.md) |
| Collection rules | [`capsules/collection-ref.capsule.md`](capsules/collection-ref.capsule.md) |
| Note rules (quick capture) | [`capsules/note.capsule.md`](capsules/note.capsule.md) |
| Kernel rules (OS infrastructure) | [`capsules/kernel.capsule.md`](capsules/kernel.capsule.md) |
| Playbook rules | [`capsules/playbook.capsule.md`](capsules/playbook.capsule.md) |

---

## 3. Creating Things (Actions)

| Question | File |
|----------|------|
| What actions exist? What is the action/capsule/playbook relationship? | [`actions/00-index.md`](actions/00-index.md) |
| How do I create a project (+ board + collections)? | [`actions/create-project.action.md`](actions/create-project.action.md) |
| How do I create a task? | [`actions/create-task.action.md`](actions/create-task.action.md) |
| How do I create a collection? | [`actions/create-collection.action.md`](actions/create-collection.action.md) |
| How do I create a decision (ADR)? | [`actions/create-decision.action.md`](actions/create-decision.action.md) |
| How do I generate a view (hierarchy of collections)? | [`actions/generate-view.action.md`](actions/generate-view.action.md) |
| How do I delete a vault entry cleanly? | [`actions/delete-entry.action.md`](actions/delete-entry.action.md) |

---

## 4. Governing Procedures (Playbooks)

| Question | File |
|----------|------|
| How does an agent boot? | [`playbooks/agent-boot.playbook.md`](playbooks/agent-boot.playbook.md) |
| How does an agent retire? | [`playbooks/agent-retire.playbook.md`](playbooks/agent-retire.playbook.md) |
| How are Tropo updates applied? | [`playbooks/apply-update.playbook.md`](playbooks/apply-update.playbook.md) |
| Migration playbooks | [`playbooks/migrations/`](playbooks/migrations/) |

---

## 5. Skills (Reusable Sub-Routines)

| Question | File |
|----------|------|
| What skills are available? | [`skills/`](skills/) |
| How do I scan channels for action items? | [`skills/scan-channels.skill.md`](skills/scan-channels.skill.md) |
| How do I regenerate a board? | [`skills/regenerate-board.skill.md`](skills/regenerate-board.skill.md) |
| How do I construct a briefing package? | [`skills/construct-briefing.skill.md`](skills/construct-briefing.skill.md) |
| How do I check vault health? | [`skills/check-vault-health.skill.md`](skills/check-vault-health.skill.md) |

---

## 6. Templates (Scaffolding)

| Question | File |
|----------|------|
| What templates exist? | [`templates/`](templates/) |
| Executive agent template | [`templates/executive-charter.template.md`](templates/executive-charter.template.md) |
| Task template | [`templates/task.template.md`](templates/task.template.md) |
| Project template | [`templates/project.template.md`](templates/project.template.md) |
| Board template (folder-style) | [`templates/board.template.md`](templates/board.template.md) |
| Executive dashboard template | [`templates/executive-dashboard.template.md`](templates/executive-dashboard.template.md) |
| Memory template | [`templates/memory.template.md`](templates/memory.template.md) |

---

## 7. Knowledge Base (How Things Work)

| Question | File |
|----------|------|
| KB index — all articles | [`kb/00-index.md`](kb/00-index.md) |
| What is Tropo? | [`kb/what-is-tropo.md`](kb/what-is-tropo.md) |
| How do agents work? | [`kb/how-agents-work.md`](kb/how-agents-work.md) |
| **How do projects replace folders? (core operating method)** | [`kb/how-projects-replace-folders.md`](kb/how-projects-replace-folders.md) |
| What is the Parallel Orientation Sweep (L2 boot pattern)? | [`kb/parallel-orientation-sweep.md`](kb/parallel-orientation-sweep.md) |
| How does vault entry and governance work? | [`kb/how-vault-entry-works.md`](kb/how-vault-entry-works.md) |
| How does governance work (three layers)? | [`kb/how-governance-works.md`](kb/how-governance-works.md) |
| How do playbooks work? | [`kb/how-playbooks-work.md`](kb/how-playbooks-work.md) |
| How does the Vault work? | [`kb/how-the-tropo-vault-works.md`](kb/how-the-tropo-vault-works.md) |
| How does Tropo Work (tasks/boards/projects) work? | [`kb/how-tropo-work-works.md`](kb/how-tropo-work-works.md) |
| How do tasks work? | [`kb/how-tasks-work.md`](kb/how-tasks-work.md) |
| How do teams work? | [`kb/how-teams-work.md`](kb/how-teams-work.md) |
| Glossary | [`kb/glossary.md`](kb/glossary.md) |

---

## 8. System Infrastructure

| Question | File |
|----------|------|
| Concierge activation (user-facing onboarding agent) | [`concierge/activate.md`](concierge/activate.md) |
| Vault steward (structural validation) | [`system/vault-steward.template.md`](system/vault-steward.template.md) |
| Schema reference | [`schema/`](schema/) |
| Capsule definitions index | [`capsules/00-index.md`](capsules/00-index.md) |

---

## How to Use This File

**At boot:** You do not need to read this file at every boot. Read it when you have a system question.

**When you have a question:** Grep the question column above. If your question matches, follow the pointer. Do not guess or rely on prior knowledge about how Tropo works — the kernel files are the authority.

**When something seems wrong:** The vault integrity auditor checks kernel coverage. If a file listed here is missing, that is a governance gap — flag it, do not silently work around it.

**When you want to update the kernel:** You do not. Kernel files are maintained by Tropo through the update pipeline. Flag the gap in `channels/ops.md` or raise it with the vault architect (Argus).

---

*Tropo Kernel System Index | `.tropo/00-index.md`*
*"When you have a system question, start here. The answer is in the kernel."*
