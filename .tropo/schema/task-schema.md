# Task Schema — Tropo-OS Standard

*Defines the YAML frontmatter for task, project, and board files.*
*Adapted from the Agentic Project Management spec for filesystem-native implementation.*

---

## Task File

**Location:** `tasks/[uid-short]-[slug].md`
**Example:** `tasks/a3f2-design-landing-page.md`

```yaml
---
uid: "[8-char hex]"
title: "[Task title]"
type: task
status: backlog | active | in_progress | blocked | complete
priority: P0 | P1 | P2 | P3
owner: "[agent name or human name — exactly one owner]"
project: "[project uid or name]"
created: "YYYY-MM-DD"
created_by: "[who created this task]"
due: "YYYY-MM-DD" # optional
depends_on: [] # optional — UIDs of blocking tasks
linked_files:
 - path: "[file path]"
 relationship: created | edited | referenced
---

[Task description — what needs to be done, acceptance criteria, context]
```

### Field Notes

- **`owner`** — exactly one. No shared ownership. If an agent needs help, it creates sub-tasks.
- **`priority`** — P0 (critical/blocking), P1 (high/this session), P2 (normal), P3 (low/backlog).
- **`depends_on`** — lightweight dependency tracking. List UIDs of tasks that must complete first. Not a critical path engine — just enough for agents to know what's blocked.
- **`linked_files`** — builds provenance. "Who created this file?" → check the task that produced it.
- **`status` transitions** — `backlog` → `active` → `in_progress` → `complete`. Any status can go to `blocked`. `blocked` returns to previous status when unblocked.

---

## Project File

**Location:** `projects/[slug].md` or `projects/[slug]/project.md`
**Example:** `projects/q3-rebrand.md`

```yaml
---
uid: "[8-char hex]"
title: "[Project name]"
type: project
status: planning | active | complete | paused
owner: "[agent or human]"
parent_project: "[uid]" # optional — for sub-projects (e.g., sprints within a release)
created: "YYYY-MM-DD"
target_date: "YYYY-MM-DD" # optional
tags: [] # optional — for filtering
---

[Project description — scope, goals, success criteria]

## Tasks

*Maintained by the project owner or any agent working on this project.*

| Task | Status | Owner | Priority |
|------|--------|-------|----------|
```

### Field Notes

- **`parent_project`** — enables hierarchy. A release contains sprints, a sprint contains workstreams.
- **`tags`** — free-form. Conventions: `#agent-name`, `#domain`, `#release`, `#priority`.
- The task table is a convenience view. The source of truth is the individual task files in `tasks/`.

---

## Board File

**Location:** `projects/[slug]-board.md` or root-level for vault-wide boards
**Example:** `projects/q3-rebrand-board.md`

```yaml
---
uid: "[8-char hex]"
title: "[Board name]"
type: board
scope: "[project uid]" # optional — scoped to a project. Omit for vault-wide.
filters:
 status: [active, in_progress, blocked]
 owner: "[agent name]" # optional
 priority: [P0, P1] # optional
sort: priority | due | created
---

[Board description — what this view is for, who uses it]
```

### Field Notes

- **Boards are views, not containers.** A board defines a query over `tasks/`. The agent reads the board, scans task files matching the filters, and assembles the view.
- **Boards are optional.** Small vaults with a few tasks don't need boards. They emerge when there's enough work to need filtered views.

---

## Spec Adaptation Note

This schema adapts the locked Agentic Project Management spec (Metis G18, April 3, 2026) for filesystem-native implementation:

| PM Spec (SQLite) | Task Schema (Files) | Rationale |
|-------------------|---------------------|-----------|
| Auto-increment `id` | 8-char hex `uid` | UIDs work across filesystems, no central counter |
| `assigned_agent` | `owner` | Consistent with agent charter `owner` field |
| `tags` as JSON array | `tags` as YAML list | Same concept, native format |
| No `priority` field | `priority: P0-P3` | Practical need for sorting and triage |
| No `depends_on` | `depends_on: [uid]` | Lightweight dependency — not full critical path |
| `project_channel_id` | Omitted | Channels are separate files, not DB references |
| Board `filters` as JSON | Board `filters` as YAML | Same concept, native format |

The PM spec remains authoritative for the platform (SQLite) implementation. This schema is the filesystem adaptation for the fresh vault.
