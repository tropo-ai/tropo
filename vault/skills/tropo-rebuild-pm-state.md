---
uid: f0e7c6fc
name: rebuild-pm-state
type: how-to
title: Rebuild PM State
skill_id: rebuild-pm-state
version: 1.0
status: active
owner: vela
tier: os
author: vela
created: 2026-04-15
created_by: vela
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
purpose: Rebuilds vault/00-pm-state.json from the vault index and project tree
when: When the PM state is stale (filesystem mtime older than significant ledger activity) before booting sa.project-manager
trigger_description: 'Reach for this when PM state at vault/00-pm-state.json is stale — typically before booting sa.project-manager (which loads PM state at boot for fast project navigation queries) or after substantial work-management changes (new tasks, projects, board updates). Reads vault/00-index.jsonl + vault/00-project-tree.jsonl, writes the consolidated PM-state JSON. Companion to rebuild-vault.py: rebuild the vault first, then rebuild PM state from the rebuilt index.'
reads:
  - vault/00-index.jsonl
  - vault/00-project-tree.jsonl
writes:
  - vault/00-pm-state.json
subsystem_hub:
  - 76bab75f
---

# rebuild-pm-state — Skill

*Rebuilds `vault/00-pm-state.json` from the vault index and project tree.*
*Run when the PM state is stale (filesystem mtime older than significant ledger activity) before booting sa.project-manager.*

---

## When to Use

- sa.project-manager checks `00-pm-state.json` mtime at boot and finds it older than the most recent vault entry's modified date
- After significant ledger changes (bulk task updates, project restructuring)

---

## Process

### Step 1 — Begin rebuild

The build is a single-writer operation; no separate lock primitive is required. If a concurrent rebuild is suspected, last-write-wins on `00-pm-state.json` and the most recent rebuild is canonical.

### Step 2 — Load source data

Vault root: read `settings/env.md` to resolve paths. All paths relative to vault root.

Read:
- `vault/00-index.jsonl` — all entries
- `vault/00-project-tree.jsonl` — project hierarchy (parent-child relationships)

**Field mapping reference** (use when building the PM state):

| Concept | Source field | Definition |
|---------|-------------|------------|
| Task stage buckets | `stage` in index entry (v2) | `build` = in progress; `ideate` = queued not started; `verify` = waiting for verification; `done` = complete; `cancelled` = abandoned |
| Task state | `state` in index entry (v2) | `active` = live; `archived` = historical |
| Verifier | `verifier` field in index entry | The agent or human who confirmed a `done` task is actually complete. A done task with no `verifier` field cannot formally close. |
| Orphan task | `member_of` absent or empty array | A task with no project assignment — invisible to project boards and health reports |
| Stale blocker | `relationships:` entry with `rel: depends-on` or `rel: blocked-by` pointing to a UID with `stage: done` or `state: archived` | The blocking task is resolved but the dependency relationship wasn't cleared |
| Pillar | Top-level project in `00-project-tree.jsonl` (entries with `parent: null`) | The root-level organizing contexts: Tropo Innovation Pipeline, Tropo Launch, Vault Operations, etc. |
| Cross-pillar task | Task whose `member_of` array contains UIDs from two or more different root-level projects | Work that serves multiple strategic contexts simultaneously |

**v2 schema note:** The index (`00-index.jsonl`) now uses `stage:` + `state:` instead of `status:`, `member_of:` instead of `projects:`/`project:`, and `relationships:` array instead of scattered fields. Read the v2 schema spec (`222873b9`) for full field definitions.

### Step 3 — Build PM state

Compute and write `vault/00-pm-state.json`:

```json
{
 "generated_at": "ISO 8601 datetime",
 "generated_by": "agent-id",
 "source_entry_count": N,
 "project_count": N,
 "projects": {
 "<uid>": {
 "title": "...",
 "status": "active|completed|archived",
 "parent": "<uid> or null",
 "children": ["<uid>",...],
 "tasks": {
 "active": [{"uid": "...", "title": "...", "owner": "...", "priority": "..."}],
 "backlog": [...],
 "done": [...],
 "blocked": [{"uid": "...", "title": "...", "blocked_by": ["..."]}]
 },
 "integrity_flags": {
 "done_no_verifier": ["<uid>",...],
 "orphan_tasks": ["<uid>",...]
 }
 }
 },
 "cross_pillar_tasks": [
 {"uid": "...", "title": "...", "projects": ["<uid1>", "<uid2>"], "pillars": ["...", "..."]}
 ],
 "by_owner": {
 "<owner>": {
 "active": ["<uid>",...],
 "backlog": ["<uid>",...],
 "done_no_verifier": ["<uid>",...]
 }
 },
 "integrity_summary": {
 "done_no_verifier": N,
 "orphan_tasks": N,
 "blocked_tasks": N,
 "stale_blockers": N
 }
}
```

### Step 4 — Stamp generation metadata

The `00-pm-state.json` body itself carries `generated_at`, `generated_by`, and `source_entry_count` fields (see Step 3 schema). These are the canonical staleness signals — no separate registry tracking required. sa.project-manager checks the file's mtime + the `generated_at` field at boot.

### Step 5 — Confirm

Return: `PM state rebuilt — [N] projects, [N] entries, [N] integrity flags. Status: current.`

---

## Failure Handling

If Step 3 fails: set registry status back to `"unknown"` (not `"building"`). Do not leave it locked.

---

*rebuild-pm-state skill | v1.0 | Vela V28 | April 15, 2026*
