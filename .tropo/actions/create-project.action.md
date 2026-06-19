---
title: "Create a Project"
action_id: act-create-project
version: 3.1
status: published
tier: os
target_capsule: project
creates: "vault/files/<uid>.md (type: project) + primary_collection + tasks_collection + projects/<slug>/ navigation folder. v0.3+: no per-project board stub — projects inherit the kernel project-board default via §6.2 lookup."
author: tropo
created: 2026-04-10
last_updated: 2026-04-20
updated_by: argus-a29
aligned_with: 74fd9b61 # Board Reconciliation v0.3
collection_note: "Each collection requires TWO writes: (1) a physical manifest file at collections/projects/<slug>/ with type: collection, and (2) a ledger pointer entry at vault/files/<uid>.md with type: collection-ref. These are different types with different homes. The manifest holds the members. The ledger entry makes the collection discoverable. Both are required."
reads:
 -.tropo/capsules/project.capsule.md
 -.tropo/capsules/board-definition.capsule.md
 - vault/AGENTS.md
 - vault/00-index.jsonl # for project-board default triple lookup
writes:
 - vault/files/<project_uid>.md
 - vault/files/<primary_collection_uid>.md
 - vault/files/<tasks_collection_uid>.md
 - collections/projects/<slug>/all.collection.md
 - collections/projects/<slug>/tasks.collection.md
 - vault/00-index.jsonl
 - projects/<slug>/AGENTS.md
 - projects/<slug>/CAPSULE.md
 - projects/<slug>/default.collection.md
governed_by: 9b7f5e34  # action.capsule v1.1
member_of:
  - "2d083137"   # tropo-work (v1.12 backfill 2026-05-08)
---

# Create a Project

*Compound action (v3.1): creates a project entry plus two collections in a single atomic operation.*
*A project is not valid until both companion collections exist and their UIDs are wired into the project's frontmatter. The project's status board is inherited from the kernel `project-board` default via §6.2 lookup; no per-project board artifact is created at project-creation time.*

---

## 1. Intent

This action creates one new project entry in the ledger, together with the two companion artifacts the project capsule requires: a primary collection (full membership roster) and a tasks collection (work queue). All three are created in sequence before any is considered complete. The project's status board is NOT a separate artifact — under [Board Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md), every project inherits the kernel `project-board` definition ([c72f1a85](../seed/ledger/project-board.board-definition.md)) by default, and custom status boards are authored as separate `board-definition` entries referenced via a `status_board:` UID on the project frontmatter (optional).

**When to invoke this action:**

The user says something like:
- "Start a project to do X"
- "Create a project for the Vault build"
- "I want to track X as a project — it's going to take multiple sessions"
- "Set up a sub-project under the Tropo Work initiative"

**Do NOT invoke this action for:**
- A single discrete piece of work — use `create-task.action.md` instead.
- An ad-hoc grouping of existing files — use `create-collection.action.md` instead.

**Reference:** The project capsule definition at `.tropo/capsules/project.capsule.md` defines what a valid project IS. This action defines how to CREATE one.

---

## 2. Prerequisites

Before running this action, verify:

1. **The Vault exists.** `vault/` must be present at the vault root.
2. **The `collections/` folder exists** at the vault root (create it if missing).
3. **The project capsule definition exists** at `.tropo/capsules/project.capsule.md`.
4. **The vault index is writable.**
5. **If `project` (parent) is specified,** the referenced UID must exist in the Vault AND have `type: project`.
6. **If `team` is specified,** the referenced UID must exist in the Vault AND have `type: team-def`.

If any prerequisite fails, stop and report.

---

## 3. Inputs

### Required inputs

| Input | Type | Notes |
|-------|------|-------|
| `title` | string, ≤100 chars | Human-readable project name |
| `description` | string, ≤120 chars | One-line goal of the project. **If the caller does not provide this, derive it from the title:** `"<title> project"` is an acceptable default — do not stall waiting for it. |
| `slug` | string | URL-friendly short identifier (lowercase, hyphen-separated, no spaces). Example: `board-governance-test`. |
| `owner` | string | Agent or human responsible. Defaults to the requesting agent if not specified. |

### Optional inputs

| Input | Type | Notes |
|-------|------|-------|
| `project` | UID | If this is a sub-project of a larger project |
| `target_date` | ISO 8601 date | Best-effort completion date |
| `start_date` | ISO 8601 date | When active work begins (defaults to today) |
| `team` | UID | Team responsible for the work |
| `tags` | array of strings | Up to 10 tags |
| `initial_status` | enum | `proposed` (default) or `active` if work begins immediately |
| `initial_members` | array of UIDs | Entries to add to the primary collection at creation. Optional — collections can start empty. |
| `initial_tasks` | array of UIDs | Task UIDs to add to the tasks collection at creation. Optional. |

---

## 4. Process

This action creates three artifacts in sequence (v0.3+: no board stub — projects inherit the kernel `project-board` default). Do not declare success until all three exist and are cross-wired.

**This action is self-contained.** All templates are in §5 — you do not need to open `create-collection.action.md`.

**CRITICAL — each collection requires TWO writes:**
- A **manifest file** at `collections/projects/<slug>/` — type `collection` — holds the member list
- A **ledger pointer entry** at `vault/files/<uid>.md` — type `collection-ref` — makes it discoverable

These are different capsule types stored in different locations. Both are required. A vault entry with no manifest is a broken pointer. A manifest with no vault entry is invisible to queries. Do not skip either write.

### Step 1 — Generate UIDs

Generate three 8-character lowercase hex UIDs. Verify no collisions in `vault/00-index.jsonl`. Regenerate any that collide.

- `project_uid` — for the project entry
- `primary_collection_uid` — for the primary collection
- `tasks_collection_uid` — for the tasks collection

(v0.3+: no `board_uid` — projects inherit the kernel `project-board` definition; per-project board UIDs are created only when a caller explicitly authors a custom `board-definition` for the project, as a separate operation.)

### Step 2 — Validate slug

Lowercase, letters/numbers/hyphens only, no spaces. Grep `vault/00-index.jsonl` for existing `type: project` entries with the same slug. If collision, ask the user for a different slug.

### Step 3 — Validate parent and team references

If `project` (parent) is provided: verify the UID exists in the Vault with `type: project`. Walk the parent chain for cycles.

If `team` is provided: verify the UID exists with `type: team-def`.

### Step 4 — Create the primary collection (TWO writes)

**Write 1 — the manifest** (type: `collection`, lives in `collections/`):
- Create directory `collections/projects/<slug>/` if it doesn't exist
- Write `collections/projects/<slug>/all.collection.md` using the primary collection manifest template in §5
- This file holds the actual member list. It is what agents read to see what's in the collection.

**Write 2 — the ledger pointer** (type: `collection-ref`, lives in `vault/files/`):
- Write `vault/files/<primary_collection_uid>.md` using the primary collection ledger entry template in §5
- The `collection_path:` field in this entry must point at the manifest: `collections/projects/<slug>/all.collection.md`
- This entry makes the collection discoverable from `vault/00-index.jsonl`

**Write 3 — the index record:**
- Append the `collection-ref` index record to `vault/00-index.jsonl`

### Step 5 — Create the tasks collection (TWO writes)

**Write 1 — the manifest** (type: `collection`, lives in `collections/`):
- Write `collections/projects/<slug>/tasks.collection.md` using the tasks collection manifest template in §5

**Write 2 — the ledger pointer** (type: `collection-ref`, lives in `vault/files/`):
- Write `vault/files/<tasks_collection_uid>.md` using the tasks collection ledger entry template in §5
- The `collection_path:` field must point at: `collections/projects/<slug>/tasks.collection.md`

**Write 3 — the index record:**
- Append the `collection-ref` index record to `vault/00-index.jsonl`

### Step 6 — [RETIRED in v0.3] Create the project board stub

**RETIRED 2026-04-20 per [Board Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md).** Under v0.3, projects inherit the kernel `project-board` default ([c72f1a85](../seed/ledger/project-board.board-definition.md)) as their status board via the §6.2 `(type: board-definition, name: project-board, default_for: project)` lookup. No per-project stub is needed. The first time an agent renders the project's status board, it regenerates ephemerally against live sources from the default definition.

Projects that need a custom status board declare `status_board: <uid>` in their frontmatter pointing at a custom `board-definition` entry. That authorship is separate from create-project — author the custom definition first, then reference it at project creation.

Skip this step. Proceed to Step 7.

### Step 7 — Write the project file

Write `vault/files/<project_uid>.md` using the project template in §5. Three UIDs are known at this point (project, primary_collection, tasks_collection) — wire them in at write time. Do NOT write a `board:` field (retired in project.capsule v2.1). If the caller declared a custom `status_board:` UID as input, include it; otherwise omit (default fallback applies).

### Step 8 — Append the project index record

Append to `vault/00-index.jsonl`. Use this exact record shape (fill in values):

```json
{"uid":"<project_uid>","type":"project","status":"<status>","title":"<title>","description":"<description>","owner":"<owner>","created":"<today>","modified":"<today>","tags":[<tags>],"file_ext":"md","schema_version":1,"slug":"<slug>","primary_collection":"<primary_collection_uid>","tasks_collection":"<tasks_collection_uid>","created_by":"<your-agent-id>"}
```

Note: the `"board"` key is removed in v0.3. The `status_board:`, `grooming_board:`, `sprint_board:`, `portfolio_board:` keys are added only when the caller explicitly provided a custom definition UID.

Note (orthogonal, out of v0.3 scope): the `status:` and `schema_version: 1` fields in this record disagree with [project.capsule v2.1 (34e4cb0b)](../capsules/project.capsule.md) which requires `stage: + state: + schema_version: 2`. That defect is flagged for Vela's pillar-integrity follow-up; v0.3 did not fix it to keep scope tight. Do not confuse: this bug is about the project record, not the board record.

### Step 9 — Verify all four artifacts

Run the verification checklist from §6 before declaring success. (Three artifacts now — board stub retired.)

### Step 10 — [OPTIONAL] Create a creation-time board-snapshot

Under v0.3, creation-time snapshots are **optional**. A brand-new project has no content, so a creation-time snapshot captures four null-result sections — low signal for most callers. Skip this step unless the caller explicitly requested a snapshot (e.g., `snapshot_at_creation: true` input, or a release-ship context).

When the caller does request a snapshot, dispatch [`create-snapshot.skill.md` (d847e2b3)](../skills/create-snapshot.skill.md) with:
- `scope_ref_uid: <project_uid>`
- `board_definition_uid: <status_board UID if declared, else the project-board kernel default UID c72f1a85>`
- `reason: "Project creation snapshot"`

The skill writes the snapshot per [board-snapshot.capsule (b5a7c391)](../capsules/board-snapshot.capsule.md) and returns its UID.

If the caller did not request a snapshot, skip to Step 11. The project is complete without a creation-time snapshot; the board-definition + on-demand regeneration covers the orientation use case.

**Legacy board-synthesizer dispatch (pre-v0.3 path — retired).** The pre-v0.3 pattern dispatched [board-synthesizer Protocol C](../../agents/operations/board-synthesizer/board-synthesizer-activate.md) to replace a stub board. That path produced `type: board` entries with non-compliant `status: current / schema_version: 1` frontmatter (the bug [sa.research 023 surfaced](../../agents/sa/sa.research/activation-log/023-board-reconciliation-inventory.md)). The v3 synthesizer now uses board-snapshot semantics and is a thin wrapper around [create-snapshot.skill.md](../skills/create-snapshot.skill.md); the pre-v0.3 instructions that used to follow here (write `type: board` / `status: current`, supersede a stub, wire a `board:` field on the project) are **retired and explicitly forbidden**. Use `create-snapshot.skill.md` directly when an explicit snapshot is needed per the block above.

### Step 11 — Create the projects/ navigation folder

Create `projects/<slug>/` with three files (v0.3+: `project.board.md` retired — status boards are rendered on demand from the kernel `project-board` default or a declared `status_board:` definition). This is the human navigation layer (ADR-033). The file tree IS the UI.

**File 1 — `projects/<slug>/AGENTS.md`**

```markdown
---
spec_version: 2
tier: os
maintained_by: vela
tropo_version: "0.3.0"
---

# Tropo-OS Governed Folder

Read CAPSULE.md before operating.

**Write gate:** Owner only.
```

**File 2 — `projects/<slug>/CAPSULE.md`**

```markdown
---
spec_version: 2
tier: capsule
folder_type: governed
owner: <owner>
write_access: [<owner>]
project_uid: <project_uid>
created: <today>
created_by: <your-agent-id>
---

# projects/<slug>/ — <title>

Navigation folder for the [<title>](../../vault/files/<project_uid>.md) project.

The files in this folder are generated — do not hand-edit `default.collection.md`. Status boards for this project are rendered on demand by [regenerate-board.skill.md](../../.tropo/skills/regenerate-board.skill.md) from the project's declared `status_board:` definition, falling back to the kernel `project-board` default — no static board file is stored in this folder.

**Ledger entry:** `vault/files/<project_uid>.md`
**Status board:** inherits kernel `project-board` default ([c72f1a85](../../vault/files/c72f1a85.md)) unless the project declares a `status_board:` UID.
```

**File 3 — `projects/<slug>/default.collection.md`**

```markdown
# <title> — Default Collection

*Generated view of everything in this project, grouped by type.*
*Regenerate via a grooming pass when project membership changes (v0.3+: this collection is a manual curation, not a generated view — no synthesizer dispatch required).*

---

## Decisions
- [To be populated]

## Specs
- [To be populated]

## Tasks
- [To be populated]

## Notes
- [To be populated]

---

*<title> | default.collection.md | Generated <today> by <your-agent-id>*
*Source: vault/files/<project_uid>.md → primary_collection: <primary_collection_uid>*
```

### Step 12 — Confirm to the user

Report:
- Project UID and ledger location
- Status board: inherits kernel `project-board` default ([c72f1a85](../../vault/files/c72f1a85.md)) unless the caller explicitly declared a custom `status_board:`
- Snapshot UID (ONLY if Step 10 created a creation-time snapshot; otherwise omit this line)
- Primary collection UID and path
- Tasks collection UID and path
- Navigation folder: `projects/<slug>/`

---

## 5. Templates

### Project file (`vault/files/<project_uid>.md`)

```markdown
---
uid: <project_uid>
type: project
status: <initial_status>
title: "<title>"
description: "<description>"
owner: <owner>
created: <today>
modified: <today>
tags: [<tags>]
file_ext: md
schema_version: 1
slug: <slug>
primary_collection: <primary_collection_uid>
tasks_collection: <tasks_collection_uid>
project: <parent_uid, if present>
target_date: <if present>
start_date: <start_date or today>
team: <if present>
created_by: <your-agent-id>
---

# <title>

*<One-sentence subtitle stating the project's purpose.>*

---

## What This Is

<One paragraph: what the project will accomplish, what "done" looks like, why it matters now.>

## Scope

**In scope:**
- <Item>

**Out of scope:**
- <Item>

## Critical Path

<Narrative or visual of dependencies. What must happen first, what gates completion.>

## Decisions Needed

- [To be populated as decisions arise]

## Status

**Status:** <initial_status>
**Next priority:** <what comes next>
**Blockers:** None

---

*<title> | <slug> | Owner: <owner> | Created <today>*
*Status board: inherits kernel `project-board` default. Override by adding `status_board: <board-definition uid>` to the frontmatter.*
*All: [[<primary_collection_uid>]] | Tasks: [[<tasks_collection_uid>]]*
```

**v0.3 note.** The `board:` field is removed from the project template ([project.capsule v2.1](../capsules/project.capsule.md)). Projects inherit the kernel `project-board` definition by default; custom overrides use named-field references (`status_board:`, `grooming_board:`, `sprint_board:`, `portfolio_board:`). Orthogonal defects (`status:` field where v2.1 wants `stage:/state:`; `schema_version: 1` where v2.1 wants 2) are NOT fixed in v0.3 — out of scope per v0.3 §10. Routed to Vela's pillar-integrity backlog.

### Board stub — RETIRED in v0.3

The board stub template is retired. Projects inherit the kernel [`project-board` definition (c72f1a85)](../seed/ledger/project-board.board-definition.md); no per-project board stub is created at project creation time.

For explicit creation-time snapshots (optional), the caller dispatches [`create-snapshot.skill.md` (d847e2b3)](../skills/create-snapshot.skill.md) with the project UID and the kernel default's UID (or a custom `board-definition` UID). See Step 10.

### Primary collection manifest (`collections/projects/<slug>/all.collection.md`)

```markdown
---
uid: <primary_collection_uid>
type: collection
collection_type: manual
name: "<title> — All"
owner: <owner>
purpose: "Full membership roster for the <title> project"
render_as: flat
created: <today>
modified: <today>
file_ext: md
schema_version: 1
---

# <title> — All

*Full membership roster for the <title> project.*

## Members

- [To be populated as work is created]

---

*<title> — All | Collection | Owner: <owner> | Created <today>*
```

### Primary collection ledger entry (`vault/files/<primary_collection_uid>.md`)

```markdown
---
uid: <primary_collection_uid>
type: collection-ref
status: active
title: "<title> — All"
description: "Full membership roster for the <title> project"
owner: <owner>
created: <today>
modified: <today>
tags: [collection, project]
file_ext: md
schema_version: 1
collection_path: "collections/projects/<slug>/all.collection.md"
collection_type: manual
member_count: 0
created_by: <your-agent-id>
---

# <title> — All — Collection Reference

Ledger registration for [`collections/projects/<slug>/all.collection.md`](../../collections/projects/<slug>/all.collection.md).

**Purpose:** Full membership roster for the <title> project.
**Owner:** <owner>
**Member count:** 0 (empty at creation)
```

### Tasks collection manifest (`collections/projects/<slug>/tasks.collection.md`)

```markdown
---
uid: <tasks_collection_uid>
type: collection
collection_type: manual
name: "<title> — Tasks"
owner: <owner>
purpose: "Work queue for the <title> project — tasks only"
render_as: flat
created: <today>
modified: <today>
file_ext: md
schema_version: 1
---

# <title> — Tasks

*Work queue for the <title> project — tasks only.*

## Members

- [To be populated as tasks are created]

---

*<title> — Tasks | Collection | Owner: <owner> | Created <today>*
```

### Tasks collection ledger entry (`vault/files/<tasks_collection_uid>.md`)

```markdown
---
uid: <tasks_collection_uid>
type: collection-ref
status: active
title: "<title> — Tasks"
description: "Work queue for the <title> project — tasks only"
owner: <owner>
created: <today>
modified: <today>
tags: [collection, tasks, project]
file_ext: md
schema_version: 1
collection_path: "collections/projects/<slug>/tasks.collection.md"
collection_type: manual
member_count: 0
created_by: <your-agent-id>
---

# <title> — Tasks — Collection Reference

Ledger registration for [`collections/projects/<slug>/tasks.collection.md`](../../collections/projects/<slug>/tasks.collection.md).

**Purpose:** Work queue for the <title> project — tasks only.
**Owner:** <owner>
**Member count:** 0 (empty at creation)
```

---

## 6. Verification

Before declaring the action complete, verify each item using these concrete checks:

1. **Project file exists:** `ls vault/files/<project_uid>.md` → file present
2. **Primary collection manifest exists:** `ls collections/projects/<slug>/all.collection.md` → file present
3. **Primary collection-ref exists:** `ls vault/files/<primary_collection_uid>.md` → file present
4. **Tasks collection manifest exists:** `ls collections/projects/<slug>/tasks.collection.md` → file present
5. **Tasks collection-ref exists:** `ls vault/files/<tasks_collection_uid>.md` → file present
6. **Three index records exist:** `grep '<project_uid>\|<primary_collection_uid>\|<tasks_collection_uid>' vault/00-index.jsonl` → 3 lines returned
7. **Project frontmatter wired — primary_collection:** `grep '^primary_collection: <primary_collection_uid>' vault/files/<project_uid>.md` → match found
8. **Project frontmatter wired — tasks_collection:** `grep '^tasks_collection: <tasks_collection_uid>' vault/files/<project_uid>.md` → match found
9. **Project file has NO `board:` field:** `grep '^board:' vault/files/<project_uid>.md` → no match (retired in project.capsule v2.1).
10. **Default board-definition reachable:** `grep '"name":"project-board"' vault/00-index.jsonl | grep '"type":"board-definition"'` → exactly 1 match (the kernel seed). If zero: vault has not been through apply-update since v0.3 seed shipped — ask the concierge to run the [apply-update playbook (`.tropo/playbooks/apply-update.playbook.md`)](../playbooks/apply-update.playbook.md) before create-project can succeed.
11. **Navigation folder complete:** `ls projects/<slug>/AGENTS.md projects/<slug>/CAPSULE.md projects/<slug>/default.collection.md` → all 3 present. (Removed `project.board.md` — v0.3 renders status boards on demand; no per-project static board file.)
12. **Slug unique (if declared):** `grep '"slug": "<slug>"' vault/00-index.jsonl` → exactly 1 result. If `slug` was omitted (v2.1 allows this): skip this check.

If any check fails, repair before reporting success.

---

## 7. Failure Modes

| Failure | Action |
|---------|--------|
| UID collision | Regenerate and retry |
| Slug collision | Ask user for different slug |
| Parent project UID not found or wrong type | Stop and ask user to correct |
| Parent cycle detected | Stop and report — refuse to create |
| Team UID not found or wrong type | Stop and ask user to correct |
| Collection creation fails | Stop — do not create a partial project. Report which step failed. |
| Default board-definition unreachable | Halt — the kernel `project-board` seed (c72f1a85) is missing. Ask the concierge to run the [apply-update playbook (`.tropo/playbooks/apply-update.playbook.md`)](../playbooks/apply-update.playbook.md) to land the seed, then retry. Per [ADR-035 Surface 2 (a7c4e5b2)](../../vault/files/a7c4e5b2.md) — no silent fallback. |
| Ledger not present | Escalate — vault not Phase 1 compliant |
| Partial write | Roll back in reverse order: project index → project file → tasks collection-ref index → tasks collection-ref file → tasks collection manifest → primary collection-ref index → primary collection-ref file → primary collection manifest. |

---

*Create Project Action | v3.1 | Tropo OS | 2026-04-20*
*v3.1 (2026-04-20, Argus A29) — [Board Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md) compliance: board stub retired (projects inherit kernel `project-board` default), three-artifact flow replaces four-artifact, `board:` removed from project template, creation-time snapshot is now optional via [create-snapshot.skill.md](../skills/create-snapshot.skill.md). Orthogonal project-capsule `status:`/`schema_version:` drift NOT fixed in v3.1 — routed to Vela's pillar-integrity backlog per v0.3 §10 scope boundary.*
*v3.0 (April 14, 2026) — collection-ref pattern, four-artifact flow.*
*v1.0 (April 10) — bare project only. v2.0 (April 13) — compound action. v2.1 (April 13) — Vela V28 friction fixes. v2.2 (April 13) — Metis G40 collection two-write fix. v2.3 (April 13) — board synthesizer dispatched at Step 10; humans never see a stub. v3.0 (April 14) — Step 11 adds projects/<slug>/ navigation folder (ADR-033 Phase 2). Every project now fully wired at creation: vault entries + collections + navigation layer.*
*Reads (v3.1): `.tropo/capsules/project.capsule.md` (v2.1), `.tropo/capsules/board-definition.capsule.md`, `vault/AGENTS.md`, `vault/00-index.jsonl` (for project-board default triple lookup).*
*Writes (v3.1): `vault/files/<uid>.md` (×3 — 1 project + 2 collection-refs), `collections/projects/<slug>/` (×2 manifests), `vault/00-index.jsonl` (×3 records), `projects/<slug>/` (×3 files — AGENTS, CAPSULE, default.collection).*
*Scripts associated with v0.3 migration (one-time): `scripts/migrate-boards-v03.ts` (60 boards + 5 dangling + 59 renames + 1 scope fix), `scripts/groom-status-boards-v03.ts` (59 snapshot-pointing `status_board:` fields cleared). Both are historical — do not re-run against a vault already migrated.*
