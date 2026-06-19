---
title: "Tropo Actions — Index"
status: published
type: index
tier: os
owner: tropo
created: 2026-04-10
member_of:
  - "2d083137"   # tropo-work (v1.12 backfill 2026-05-08)
---

# Tropo Actions

*Atomic operations for creating and modifying typed files in a Tropo vault.*
*Each action is a self-contained instruction an agent reads and executes to bring one capsule into existence (or to operate on one).*

---

## What Actions Are

Actions are the **constructor layer** of Tropo Work. They sit between capsule definitions (the type system — what a thing IS) and playbooks (the orchestration layer — how multiple things compose into workflows).

The three layers:

| Layer | Primitive | Purpose | Example |
|-------|-----------|---------|---------|
| **Type** | Capsule definition | What a typed file IS — structure, governance, validation | `task.capsule.md` |
| **Constructor** | Action | How to CREATE or modify one instance of a type | `create-task.action.md` |
| **Orchestration** | Playbook | How to sequence multiple actions and other operations | `release-version.playbook.md` |

When a user says "I want to create a task," the system invokes the `create-task.action.md` action. The action reads the task capsule definition, gathers inputs from the user, generates a UID, applies the template, validates, writes the file, updates the index, and confirms.

A simple user intent invokes one action. A compound user intent invokes a playbook that invokes multiple actions in sequence.

---

## L1 / L2 / L3 Progression

Actions are designed to work at all three capability levels:

- **L1 (Phase 1):** An agent reads the action file and executes it step by step. Markdown files, no code, governance through language. Ships in the Tropo-OS zip.
- **L2 (Phase 2):** A standing always-on service (the local reasoning kernel — "the brain") reads the action file and executes it as a service call. Same file, faster substrate. When a user says "create a task for me," the brain reads the action, applies inputs, produces a valid task, checks it into the Vault — in milliseconds.
- **L3 (Phase 3):** The action is exposed as an MCP tool or A2A endpoint. External agents can invoke `create-task` against a Tropo vault and get back a valid task. Cross-vault interop.

The action file does not change between layers. Only the executor changes. This is the same architectural pattern as capsule definitions and the boot/retire playbooks.

---

## Phase 1 Actions

### Single-capsule creation

| Action | Creates | Capsule |
|--------|---------|---------|
| [`create-task.action.md`](create-task.action.md) | A new task entry | [`task`](../capsules/task.capsule.md) |
| [`create-project.action.md`](create-project.action.md) | A new project + board stub + two collections (compound) | [`project`](../capsules/project.capsule.md) |
| [`create-design-brief.action.md`](create-design-brief.action.md) | A new design brief | [`design-brief`](../capsules/design-brief.capsule.md) |
| [`create-design-spec.action.md`](create-design-spec.action.md) | A new design spec (draft) | [`design-spec`](../capsules/design-spec.capsule.md) |
| [`create-collection.action.md`](create-collection.action.md) | A new collection (two-file write) | [`collection-ref`](../capsules/collection-ref.capsule.md) |
| [`create-decision.action.md`](create-decision.action.md) | A new ADR (proposed) | [`decision`](../capsules/decision.capsule.md) |

### View operations (multi-collection)

| Action | Purpose | Operates on |
|--------|---------|-------------|
| [`generate-view.action.md`](generate-view.action.md) | Generate a new view (folder hierarchy of collections) from a natural-language structure description | Creates many collections at once |
| [`refresh-view.action.md`](refresh-view.action.md) | Update an existing view's memberships to reflect the current state of the Vault; preserves structure, refreshes contents | Updates many collections at once |

### Lifecycle operations

| Action | Purpose | Operates on |
|--------|---------|-------------|
| [`delete-entry.action.md`](delete-entry.action.md) | Retire or destroy a registered vault entry cleanly — soft (archive) or hard (destructive), with incoming-reference handling (refuse/break/redirect) and steward notification | Any registered entry of any type |

Nine actions total. Six atomic single-capsule creations, two view-level operations, and one lifecycle operation. The delete-entry action closes the Phase 1 create/delete asymmetry — added by G39 on April 10, 2026 after the gap surfaced during a fictional test artifact cleanup.

**A view** is a folder hierarchy of collections arranged for a specific human's purpose. Mike can have a keystone-view. Vela can have a release-view. Each view contains many collections. Views are generated from a natural-language structure description (via `generate-view`) and refreshed as the Vault changes (via `refresh-view`). Different users can create different views of the same underlying ledger; views coexist and are shareable as pure markdown artifacts.

---

## What's NOT Yet Covered

The Phase 1 action set is intentionally small. The following operations are NOT yet covered as dedicated actions and require manual editing or future action files:

- **Editing an existing entry** — most edits are straightforward state transitions or content updates that can be done by direct file modification. A future `edit-<type>.action.md` family may formalize this.
- **State transitions** — locking a design spec, accepting a decision, completing a task. Each is currently done by direct frontmatter edit. Candidates for future action files: `lock-design-spec`, `accept-decision`, `complete-task`.
- **Archiving** — *covered by `delete-entry.action.md` in soft mode (sets `status: archived`, preserves files).* A dedicated `archive-entry` action may be added later if soft-delete semantics diverge from archiving.
- **Document creation** — `create-document.action.md` is not yet written. Documents are general-purpose and the action would mirror the others closely.
- **Team creation** — `create-team.action.md` is not yet written. Pending clarification of how teams are formed (charter? member list only? both?).
- **Board creation** — boards are created as stubs by `create-project.action.md` and regenerated by the board synthesizer. A standalone `create-board.action.md` may be added for non-project boards.

These are flagged for future Phase 1 work or for later generations to extend.

---

## Action File Structure

Every action file uses a six-section structure:

1. **Intent** — what the action does, when to invoke it, what user intent triggers it
2. **Prerequisites** — what must be true before the action can run
3. **Inputs** — what the agent gathers from the user or context
4. **Process** — step-by-step instructions
5. **Template** — the starting frontmatter and body skeleton with placeholders
6. **Verification** — what the agent confirms before declaring done

Plus a "Failure Modes" appendix for known error conditions and their handling.

This structure parallels the capsule definition structure (Intent / Structure / Requirements / Process / Governance / Validation) and the playbook structure (Intent / Suggestions / Rules / Resources / Outcomes / Verification). All three primitives have six-section bodies because they are all instructions an agent reads and follows.

---

## Adding a New Action

Creating a new action is itself a governed act. It requires:

1. The corresponding capsule definition must exist (you cannot have an action that targets a non-existent type)
2. The action file follows the six-section structure
3. The action file ships in `.tropo/actions/` (kernel) or in a vault-level extension folder
4. The action is registered in this index

For Phase 1, action files do not need vault entries — they are kernel infrastructure, same as capsule definitions and playbooks. They live in `.tropo/actions/` and ship with the OS.

---

## Refs

- [Tropo Ledger Phase 1 Specification](../../vault/files/5eb5fd1f.md) — UID `5eb5fd1f`
- [Capsule definitions index](../capsules/00-index.md)
- [Schema reference](../schema/vault-index-schema.md)

---

*Tropo Actions Index | v1.0 | Metis G38 + Mike Maziarz | April 10, 2026*
*"Capsule is the noun. Action is the verb. Playbook is the sentence."*
