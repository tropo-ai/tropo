---
title: "Delete a Ledger Entry"
action_id: act-delete-entry
version: 1.0
status: draft
tier: os
target_capsule: core
operates_on: "any registered vault entry (task, project, design-spec, design-brief, decision, collection-ref, document, board, team)"
author: tropo
created: 2026-04-10
last_updated: 2026-04-10
governed_by: 9b7f5e34  # action.capsule v1.1
member_of:
  - "2d083137"   # tropo-work (v1.12 backfill 2026-05-08)
---

# Delete a Ledger Entry

*Atomic action: retire or destroy a registered vault entry cleanly.*
*The missing twin to the six `create-*` actions. Closes the Phase 1 create/delete asymmetry.*

---

## 1. Intent

This action removes or archives a registered entry from the Tropo Vault. It exists because the Phase 1 action set shipped with six creators and zero destructors, which is architecturally incomplete — agents could create governed entries atomically but had no protocol for retiring them cleanly. Without this action, deletion happens by direct filesystem operation, which is error-prone because a registered entry has multiple touch points (ledger file, index row, collection memberships, incoming wikilinks, steward convention checks). The delete-entry action turns that multi-touchpoint cleanup into a single governed operation.

**When to invoke this action:**

The user says something like:

- "Delete entry `<uid>`"
- "Archive this task — it's been superseded"
- "Retire that collection, it was a test"
- "This entry is obsolete, remove it"
- "Undo the create-task from earlier, it was a mistake"
- "Mark this spec as archived and update the index"

**Two modes:** This action supports both soft delete (reversible, preserves files, updates status to `archived`) and hard delete (destructive, removes files, removes the index row). Soft is the default because most "delete this" requests from users are actually "stop showing me this" requests that archive semantics handle correctly. Hard delete exists for test artifacts, mistakes, and entries that should genuinely not exist in the record.

**Reference:** Task [`8f3e2d1a`](../../vault/files/8f3e2d1a.md) (Phase 1.H), the six `create-*` actions in this folder as the structural template, and the create-collection action in particular as the closest parallel (two-file write → two-file cleanup).

---

## 2. Prerequisites

1. **The target UID exists in the vault index.** If it does not, the action fails with a "UID not found" error and reports what was searched.

2. **The caller has permission to delete the entry.** Permission is derived from the entry's owner field in frontmatter and the vault's governance rules (AGENTS.md + CAPSULE.md of the folders involved). For Phase 1, if the caller is the entry's declared owner or a Citizen-class agent with write access to `vault/files/`, the action proceeds. For other cases, the action refuses and reports who the owner is.

3. **The vault steward (if Phase 1.B is active) has been given a notification path.** For Phase 1.A (current), the steward notification is a best-effort write to a known location; the action does not block on it. Once Phase 1.B ships with Function 7 (convention coverage), the steward will consume the notification stream as an audit input and the action's notification step becomes load-bearing.

4. **No active check-out of the entry exists.** If the entry is currently checked out by another agent (per the library/librarian model), the action refuses and reports the check-out state. In Phase 1 without the full librarian service, this check is a best-effort read of the entry's frontmatter for any `checkout_status` field.

---

## 3. Inputs

### Required inputs

| Input | Type | Notes |
|-------|------|-------|
| `uid` | string (8-char hex) | The UID of the entry to delete. Must exist in `vault/00-index.jsonl`. |
| `reason` | string, ≤200 chars | Why the deletion is happening. Required for audit trail. Examples: "test artifact, no production use", "superseded by `<other-uid>`", "created in error, never referenced" |

### Optional inputs with defaults

| Input | Type | Default | Notes |
|-------|------|---------|-------|
| `mode` | `soft` \| `hard` | `soft` | Soft updates status to `archived`, preserves files. Hard removes files and the index row. |
| `reference_handling` | `refuse` \| `break` \| `redirect` | `refuse` | Only applies if incoming references exist. `refuse` aborts the action; `break` replaces `[[uid]]` occurrences with `[[deleted:uid]]`; `redirect` replaces `[[uid]]` with a new target (requires `redirect_to`). |
| `redirect_to` | string (8-char hex) | — | Required if `reference_handling: redirect`. The UID to redirect incoming references to. Must exist in the index. |
| `force` | boolean | `false` | Bypasses the incoming-references safety check for hard delete. Must be explicit. Soft delete does not use `force` because soft delete does not break references. |

### Inputs the action does NOT accept

- **Bulk UIDs.** This action deletes one entry at a time. Bulk deletion is a separate operation and should be composed in a playbook that invokes this action multiple times.
- **Silent deletion.** There is no mode that removes incoming references without replacing them with a marker. History must be preserved either as a visible `[[deleted:uid]]` stub or as a redirect to a new UID. Silent removal is not supported because it erases the audit trail.
- **Cascade deletion.** If the entry has children (e.g., a project with subtasks, a collection with nested collections), the action does NOT automatically delete them. It refuses and reports the children. The caller must delete children explicitly or choose to leave them as orphans.

---

## 4. Process

### Step 1 — Resolve the entry

Look up the `uid` in `vault/00-index.jsonl`. If not found, fail with a clear message: "UID `<uid>` is not in the vault index. Nothing to delete." Do not attempt a filesystem-level search; the index is the source of truth.

If found, read the index record and note:

- `type` (task, project, design-spec, design-brief, decision, collection-ref, document, board, team)
- `status` (active, archived, proposed, accepted, etc. — capsule-specific)
- `owner`
- Any `collection_path` field (present on collection-ref entries pointing at an external collection file)

Then load the entry's file from `vault/files/<uid>.md` and determine the cleanup footprint:

| Footprint | Entry types | Files to handle |
|-----------|-------------|-----------------|
| **Single-file** | task, project, design-spec, design-brief, decision, document, board, team | `vault/files/<uid>.md` + one index row |
| **Two-file** | collection-ref | `vault/files/<uid>.md` + `<collection_path>` + one index row |
| **Dual-indexed (pre-migration)** | any | Entry's current path may not be in `vault/files/` yet. The index row's metadata should indicate the actual location. Handle accordingly. |

If the file cannot be loaded (exists in index but not on disk), report the inconsistency to the steward and refuse — this is a repair case, not a delete case.

### Step 2 — Scan for incoming references

Run three scans, in order:

1. **Wikilink scan.** Grep the vault for `[[<uid>]]` occurrences. Collect every file path and line where the UID is referenced as a wikilink.
2. **Collection membership scan.** Grep all `.collection.md` files under `collections/` for the UID in any member list. Collect every collection that references the entry.
3. **Frontmatter reference scan.** Grep for the UID in frontmatter fields of other entries (`refs:`, `depends_on:`, `parent_project:`, `redirect_to:`, etc.). Collect every entry that declares a structured relationship to this one.

Combine the three scans into a single reference list. If the list is empty, proceed to Step 3 with `has_references: false`. If the list is non-empty, record `has_references: true` and carry the list forward.

### Step 3 — Determine mode and validate reference handling

**Soft mode (default):**

Soft delete does not break references. `[[uid]]` wikilinks continue to resolve because the file still exists. Collection memberships still resolve. Frontmatter references still resolve. The only change is that queries filtering on `status: active` will skip this entry. Proceed to Step 4 regardless of `has_references`.

**Hard mode:**

Hard delete removes the file and the index row. Incoming references will break unless handled. Apply the `reference_handling` policy:

- **`refuse` (default):** If `has_references: true`, abort the action. Report the reference list to the caller with a clear message: "Cannot hard-delete `<uid>` — it is referenced by N files. Update or remove the references first, then retry. Or pass `force: true` with `reference_handling: break` or `redirect`."
- **`break`:** Requires `force: true`. Proceed. Each incoming `[[uid]]` will be replaced in Step 4 with `[[deleted:<uid>]]`. Each collection membership will be replaced with a `# deleted:<uid>` stub line. Each frontmatter reference will be replaced with `deleted:<uid>`. The reader can see that a reference used to exist.
- **`redirect`:** Requires `redirect_to: <new-uid>`. Verify the new UID exists in the index. If not, refuse. If yes, proceed. Each incoming `[[uid]]` will be replaced with `[[<new-uid>]]`. Each collection membership updated. Each frontmatter reference updated. The history is overwritten with the redirect.

If any reference-handling validation fails (missing `force`, missing `redirect_to`, target UID not found), abort with a specific message. Do not proceed with a partial deletion.

### Step 4 — Apply the file changes

**Soft mode:**

- Read the entry's file from `vault/files/<uid>.md` (or the dual-indexed location).
- Update the frontmatter: set `status: archived`. Add an `archived_at: <today>` field. Add an `archived_reason: <reason from input>` field. Preserve all other frontmatter.
- Write the file back.
- For collection-ref entries, also update the companion collection file at `<collection_path>` with the same frontmatter changes.

**Hard mode (with reference handling applied):**

- If `reference_handling: break`, walk the reference list and perform the text replacements in each referring file. Record each change in a changelog structure.
- If `reference_handling: redirect`, walk the reference list and perform the text replacements to point at `redirect_to`. Record each change.
- Delete the file at `vault/files/<uid>.md`.
- If this is a collection-ref entry, delete the companion collection file at `<collection_path>` as well.
- If the folder containing the companion file becomes empty as a result (e.g., `collections/projects/tropo-ledger/` with only one `.collection.md` file), leave the folder in place. Folder cleanup is a separate concern and requires its own explicit choice.

### Step 5 — Update the index

**Soft mode:**

- Edit `vault/00-index.jsonl` to update the row for `uid`. Set `status: archived` and `modified: <today>` in the JSONL record. Write the updated line back in place.

**Hard mode:**

- Edit `vault/00-index.jsonl` to remove the row for `uid` entirely. Preserve the rest of the file byte-identical.
- The row removal is the commit point for a hard delete. Until this step completes, the delete can still be rolled back. After this step, the entry is gone from the index and requires restoration from version control to recover.

### Step 6 — Post steward notification

Write a notification record to the vault steward's inbox. The inbox location is defined by the steward's convention; for Phase 1, write to `system/vault-steward/inbox/delete-<uid>-<timestamp>.md` (create the directory if it does not exist).

The notification record includes:

```markdown
---
type: delete-notification
action_id: act-delete-entry
target_uid: <uid>
mode: soft | hard
reason: <from input>
reference_handling: <from input>
references_affected: <count>
timestamp: <ISO 8601>
actor: <agent or human identifier>
---

# Delete notification: <uid>

The entry `<uid>` (<type>, "<title>") was <archived | hard-deleted> on <date>.

**Reason:** <from input>

**Reference handling:** <describe what happened to the N incoming references>

**Files affected:**
- `vault/files/<uid>.md` — <updated to archived | removed>
- `<collection_path>` — <updated to archived | removed> (if applicable)
- `vault/00-index.jsonl` — <row updated | row removed>
- <list each file with a reference that was broken or redirected>

The vault steward should not flag this entry as an orphan or a broken reference during its next sweep. This notification is the record.
```

If the notification write fails, log the failure to the caller but do not fail the action — the file changes have already committed. A failed notification is a minor issue; a failed rollback is a major one.

### Step 7 — Confirm to the caller

Report, in structured form:

- The UID and title of the deleted entry
- The mode applied (`soft` or `hard`)
- The reason
- How many references were found
- How those references were handled
- The files affected (with paths)
- The index row status (updated / removed)
- The steward notification location
- A one-line summary suitable for a channel post or an ops.md entry

**Example success report:**

> Deleted entry `8c2a4f1b` — "Migrate existing vault content into the ledger (Phase 1.A)" — mode: soft. Reason: "superseded by Phase 1.A v2 (`<new-uid>`), original kept for audit." Incoming references: 3 (all preserved, status-aware queries will skip). Files: `vault/files/8c2a4f1b.md` → archived; `vault/00-index.jsonl` row → status: archived. Steward notified at `system/vault-steward/inbox/delete-8c2a4f1b-2026-04-10T17-45Z.md`.

---

## 5. Templates

### Soft-delete frontmatter update (applied to the entry's file)

```yaml
---
uid: <unchanged>
type: <unchanged>
status: archived # ← changed from previous state
title: <unchanged>
description: <unchanged>
owner: <unchanged>
created: <unchanged>
modified: <today> # ← updated
archived_at: <today> # ← new field
archived_reason: "<reason>" # ← new field
tags: <unchanged>
file_ext: md
schema_version: 1
---
```

### Soft-delete index row update (applied to the JSONL line)

```
Before: {"uid":"<uid>","type":"<type>","status":"active",...,"modified":"<old date>"}
After: {"uid":"<uid>","type":"<type>","status":"archived",...,"modified":"<today>"}
```

All other fields preserved byte-for-byte.

### Hard-delete confirmation message (returned to caller)

```
Hard-deleted entry <uid> ("<title>")
Reason: <reason>
Files removed: <list>
Index row: removed
Incoming references: N (handling: <refuse | break | redirect>)
 - <file>:<line> → <before> → <after>
 -...
Steward notification: <path>

This action cannot be rolled back without restoring from version control.
```

### Steward notification template

*(See Step 6 above for the full notification format.)*

---

## 6. Verification

After the action completes, the agent (or the caller) confirms:

1. **For soft delete:**
 - The entry's file at `vault/files/<uid>.md` has `status: archived` in frontmatter.
 - The index row for `<uid>` has `"status":"archived"`.
 - No other entries in the index were modified.
 - The steward notification file exists and is readable.
 - If the entry is a collection-ref, the companion collection file also has `status: archived`.

2. **For hard delete:**
 - The file at `vault/files/<uid>.md` no longer exists.
 - The index row for `<uid>` is not present in `vault/00-index.jsonl`.
 - The index is still valid JSONL (one record per line, no blank lines between records).
 - For every reference the action claimed to handle, that reference has actually been replaced in the target file (`[[uid]]` → `[[deleted:uid]]` or `[[<new-uid>]]` depending on mode).
 - No additional files were modified beyond the ones reported.
 - The steward notification file exists and is readable.
 - If the entry was a collection-ref, the companion collection file has been removed.

3. **For both modes:**
 - A spot-check grep for the UID in the vault returns only the expected locations (archived entry for soft, broken/redirected references for hard break/redirect, nothing for hard delete with no prior references).

**Visual verification (for collection-ref deletions):**

Open the vault in Obsidian or VS Code. Confirm:

- The collection no longer appears in the file tree (hard delete) or appears with a visible archived marker (soft delete, if the editor supports frontmatter-based filtering).
- Any wikilinks to the deleted UID either still resolve (soft), show as broken/deleted (hard break), or point to the new target (hard redirect).

---

## Failure Modes

| Failure | Action |
|---------|--------|
| UID not found in index | Abort. Report "UID `<uid>` is not in the vault index. Nothing to delete." |
| Permission denied (caller is not owner and not authorized) | Abort. Report who the owner is and suggest delegating to the owner. |
| Entry is currently checked out | Abort. Report the check-out state and the agent holding it. Suggest waiting or resolving the check-out first. |
| Entry has children (subtasks, nested collections) | Abort. Report the children list. The caller must delete children explicitly or acknowledge them as orphans. |
| `mode: hard` with `has_references: true` and `reference_handling: refuse` (default) | Abort. Report the reference list. Suggest soft delete, `force: true` with `break`, or `redirect_to` with a valid target. |
| `reference_handling: redirect` with `redirect_to` missing or UID not found | Abort. Report the specific validation failure. |
| File at `vault/files/<uid>.md` missing but index row present | Refuse and report the inconsistency to the steward. This is a repair case, not a delete case. |
| Partial commit: file removed but index update failed | Rollback: restore the file from the in-memory copy taken in Step 1. Report the rollback. Do NOT leave the vault in a half-deleted state. |
| Concurrent modification detected (the file was modified between Step 1 read and Step 4 write) | Abort. Report the conflict. Suggest re-running the action. |
| Steward notification write fails | Log the failure to the caller but do NOT abort. The file changes have committed; a failed notification is recoverable through a manual note. |

---

## A Note on Dogfooding

The first use of this action should be a low-stakes exercise on a test artifact that is known to be safe to delete. The natural first candidate is a deliberately-created throwaway entry — for example, a `test` task created with `create-task`, immediately hard-deleted with `delete-entry`, verified end-to-end, and reported. This exercises the full seven-step process without risk.

The second use should be the first real soft delete — an entry that has been superseded but whose history should be preserved. A likely candidate is a design-brief that has been replaced by a locked design-spec, or a task that was split into multiple sub-tasks and whose parent should be archived.

The third use — hard delete with reference handling — should wait until the first two have passed, because it is the most consequential mode and the one most likely to produce subtle failures.

Each of the three uses should be documented in `ops.md` and referenced from this action file's changelog as validation that the action works against real vault state.

---

## A Note on the Create/Delete Asymmetry

This action exists because the Phase 1 action set was built without a deletion primitive. The six `create-*` actions shipped on April 10, 2026 as part of G38's Tropo Vault Phase 1 build. The absence was not noticed during spec review; it was surfaced during G39's session on the same day, when a fictional test artifact (a generated view at `collections/keystone-view/`) needed to be cleaned up and the cleanup revealed the gap.

The deletion itself was trivial because the test artifact was never registered in the vault index. But the conversation that followed named the broader architectural incompleteness: *a governance-first storage system with six constructors and zero destructors is not architecturally complete.* The action was drafted within hours of the gap being named.

This is the pattern: Phase 1 gaps will continue to be surfaced through operational experience, not through spec review. Each surfaced gap should be closed with the smallest primitive that makes the gap disappear. The delete-entry action is that primitive for the create/delete axis.

---

## A Note on Verification Primitives

This action is designed around the bounded verification model described in Part 32 of *The Agentic Builders* (Metis G8, March 2026). The caller does not need to evaluate whether the agent's reasoning about the deletion was correct. The caller needs to verify that the action followed the protocol and achieved the specified outcomes:

- Did the file get removed (or archived)?
- Did the index get updated (or cleaned)?
- Were incoming references handled as specified?
- Was the steward notified?

These are bounded verification questions. Each has a mechanical answer. A domain expert (or a steward audit sweep) can verify all four without needing to understand the agent's reasoning about *whether* the delete was appropriate. That judgment belongs to the caller who invoked the action with a reason.

This is the L1/L2/L3 progression in action: at L1, an agent reads this file and executes the steps. At L2, the reasoning kernel executes the same file as a service call. At L3, the action is exposed as an MCP tool or A2A endpoint. The verification contract does not change across the layers.

---

*Delete Entry Action | v1.0 (draft) | Tropo OS | April 10, 2026*
*Author: Metis G39, directed by Mike Maziarz*
*Closes the Phase 1 create/delete asymmetry. Ships the missing destructor.*
*Reads: `.tropo/capsules/core.capsule.md`, `vault/00-index.jsonl`, target entry's file*
*Writes: target entry's file (soft), `vault/files/<uid>.md` removal (hard), `vault/00-index.jsonl`, `system/vault-steward/inbox/delete-*.md`*
*Refs: task [`8f3e2d1a`](../../vault/files/8f3e2d1a.md), [create-collection action](create-collection.action.md) as structural template, Part 32 of The Agentic Builders for the bounded verification framing*
