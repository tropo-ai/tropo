---
uid: 00ac0959
name: "board"
type: capsule-definition
extends: core
version: 2.0
tier: os
author: tropo
created: 2026-04-12
modified: 2026-04-20
modified_by: argus-a29
status: superseded
superseded_by: [b0d1e4f2, b5a7c391] # board-definition + board-snapshot
superseded_at: 2026-04-20
superseded_reason: "Board Reconciliation v0.3 (74fd9b61) split the template/render mix-up into two distinct types."
schema_version: 2
governed_by: 222873b9
---

# board — Capsule Definition (SUPERSEDED)

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../ledger/files/222873b9.md) |
| Extends | `core` |
| Superseded by | [board-definition.capsule (b0d1e4f2)](board-definition.capsule.md) |
| Superseded by | [board-snapshot.capsule (b5a7c391)](board-snapshot.capsule.md) |

**⚠️ SUPERSEDED 2026-04-20.** This capsule mixed the template and rendered-view concerns into a single type, which drove four locked-but-contradictory capsule interactions documented in [Board Reconciliation v0.3 (74fd9b61)](../../ledger/files/74fd9b61.md). It has been split into two replacement capsules:

- **Template half → [board-definition (b0d1e4f2)](board-definition.capsule.md)** — the long-lived template declaring scope + sections + render format.
- **Rendered-view half → [board-snapshot (b5a7c391)](board-snapshot.capsule.md)** — the point-in-time rendered ledger entry.

The 60 live `type: board` entries migrate to `type: board-snapshot` per v0.3 §9.1. No new `type: board` entries should be written; writers MUST target the replacement types.

This file remains in the vault for historical reference. Do not read it as active governance; read the replacements above.

---

## Original Capsule Text (Historical)

*A generated snapshot of status and activity. Boards are never edited — they are regenerated from source data. If a board and a file disagree, the file wins.*

## Intent

Provide a point-in-time view of work state — what's active, what's done, what's blocked, who owns what. Boards are the orientation surface for both humans (scanning a project's status) and agents (booting into a project context). Every project has a board. The board is the first thing you read; the files behind it are the source of truth.

**Use a board when:**
- A project needs a current-state snapshot for orientation
- A team needs a dashboard of activity across members
- A collection needs a rendered view of its members' statuses
- Any scope needs a generated summary that stays current without manual maintenance

**Do NOT use a board for:**
- Source-of-truth data — boards are derived, not canonical
- Manual status tracking — if you're editing a board by hand, you want a document, not a board
- Historical records — use a collection or a note for that

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `scope` | string | One of: `project`, `owner`, `team`, `collection`, `query` |
| `scope_ref` | UID or string | The UID of the project/team/collection this board scopes, or the owner name for owner-scoped boards |
| `generated_by` | string | Agent-id that generated this board |
| `generated_at` | string | ISO 8601 datetime (`YYYY-MM-DDTHH:MM`) — when this snapshot was produced |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `source_query` | string | The query or filter the generator used to produce this board |
| `template` | string | Which board template was used for rendering (e.g., `project-board.template.md`) |
| `supersedes` | UID | The previous board this one replaces |

## State Machine

```
build (current) → done (superseded) → state: archived
```

| Stage | Meaning | Who transitions |
|-------|---------|-----------------|
| `build` | This is the live snapshot for its scope | Board generator |
| `done` | Replaced by a newer snapshot | Board generator (automatic on regeneration) |

**`state: archived`** — applied when a superseded board is no longer needed for audit trail.

Only ONE board per `scope` + `scope_ref` combination can be at `stage: build` at any time. When a new board is generated, the prior board moves to `stage: done`.

## Governance Rules (in addition to core)

1. **Boards are generated, never edited.** An agent or script produces the board by reading source data (project tasks, collection members, team activity). No human or agent edits a board directly. If the board is wrong, fix the source data and regenerate.

2. **Boards are disposable.** Regeneration creates a new entry and supersedes the old one. Superseded boards are historical snapshots — keep them for audit trail, archive them when they're no longer useful.

3. **The source data wins.** A board shows task X as `active` but the task file says `done`? The task file is right. The board is stale. Regenerate.

4. **Board body is free-form.** The capsule governs the metadata (scope, generator, timestamp). The body content — what sections, what tables, what format — is determined by the template. Different scopes can use different templates. The capsule doesn't police the body.

5. **Boards serve two users.** A human scans the board for orientation ("what's the status of this project?"). An agent reads the board at boot for context ("what should I work on?"). The template should serve both — scannable for humans, parseable for agents.

## Validation Checks (run at check-in)

In addition to core checks:

1. `scope` is present and is one of: `project`, `owner`, `team`, `collection`, `query`
2. `scope_ref` is present and non-empty
3. If `scope` is `project`, `team`, or `collection`, `scope_ref` is a valid UID in the ledger
4. `generated_by` is present and is a known agent identifier
5. `generated_at` is present and is a valid ISO 8601 datetime
6. `stage:` is one of: `build`, `done`
7. `state:` is one of: `active`, `archived`
8. If `stage: build`, no other board with the same `scope` + `scope_ref` is also at `stage: build`

## Concurrency Policy

Not applicable. Boards are write-once artifacts. A generator writes a new board; it doesn't modify an existing one. Concurrency conflicts cannot arise.

## Relationship to Projects

Per the architecture spec §6.5, every project MUST have a board (required `board` field in the project capsule). The project's board is the universal orientation primitive — the first thing a human or agent reads when entering a project context.

The board's `scope_ref` points at the project's UID. The project's `board` field points at the board's UID. Bidirectional reference.

## Inheritance

Extends `core`. Inherits all core rules. Not currently extended by subtypes. Domain-specific board types (`sprint-board`, `team-dashboard`) are possible future extensions.

---

*board capsule definition | DRAFT v1 | Tropo OS | April 12, 2026*
*"Generated, not authored. If the board and the file disagree, the file wins."*
