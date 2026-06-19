---
title: "Create a Collection"
action_id: act-create-collection
version: 1.0
status: published
tier: os
target_capsule: collection-ref
creates: "collections/<path>/<name>.collection.md AND vault/files/<uid>.md (type: collection-ref)"
author: tropo
created: 2026-04-10
last_updated: 2026-04-10
governed_by: 9b7f5e34  # action.capsule v1.1
member_of:
  - "2d083137"   # tropo-work (v1.12 backfill 2026-05-08)
---

# Create a Collection

*Atomic action: create a new collection.*
*Two-file write: the collection file itself (in `collections/`) AND a collection-ref entry in the Vault that registers its existence.*

---

## 1. Intent

This action creates a new collection — a human-organized manifest of references to vault entries. Collections live OUTSIDE the Vault, in `collections/` at the vault root, with arbitrary sub-hierarchy. They are the human's organizational layer.

**When to invoke this action:**

The user says something like:
- "Create a collection for the current sprint"
- "Make a playlist of the architecture specs I need to lock"
- "I want to group these five tasks under a project view"
- "Create a release scope collection for v1.0"

**Collections are curation.** They do NOT own the files they reference — the files live in the Vault. Adding or removing a member from a collection only updates the collection's manifest; the underlying entry is untouched.

**Reference:** [`.tropo/capsules/collection-ref.capsule.md`](../capsules/collection-ref.capsule.md) and Phase 1 spec §7.

---

## 2. Prerequisites

1. **The Vault exists.**
2. **The `collections/` folder exists** at the vault root (create it if missing — collections live outside the Vault but still inside the vault).
3. **All member UIDs provided must exist in the Vault.** Validate each before writing. A collection with dangling references is invalid.
4. **The collection-ref capsule definition exists.**

---

## 3. Inputs

### Required inputs

| Input | Type | Notes |
|-------|------|-------|
| `name` | string | Human-readable collection name |
| `path` | string | Where in `collections/` the file should live. Example: `collections/projects/tropo-ledger/` or `collections/master/`. The action creates sub-folders as needed. |
| `filename` | string | The collection file's name (without extension). Example: `phase-1-tasks`. Final file: `<path>/<filename>.collection.md`. |
| `purpose` | string, ≤120 chars | One-line purpose statement |
| `owner` | string | Who owns the collection |
| `members` | array of UIDs | At least one member UID. Each must exist in the Vault. |

### Optional inputs

| Input | Type | Notes |
|-------|------|-------|
| `collection_type` | enum | `manual` (default), `dynamic`, `ai-suggested` |
| `render_as` | enum | `flat` (default) or `hierarchical` |
| `groupings` | structured | If `render_as: hierarchical`, a map of section headers to member UIDs |
| `refs` | array | Related entries (other collections, parent project, etc.) |

### Inputs for hierarchical collections

If the user wants a hierarchical collection (nested headers inside the collection file), they provide:

```yaml
groupings:
 "Architecture":
 - <uid>
 - <uid>
 "Tasks":
 - <uid>
 - <uid>
```

The headers become `##` sections in the collection body. Members are listed under each header.

---

## 4. Process

### Step 1 — Generate two UIDs

- One for the collection-ref entry in the Vault (8-char hex)
- The collection file itself carries the SAME UID in its frontmatter (collections and their refs share UIDs — one UID, two physical files, one logical concept)

### Step 2 — Validate all member UIDs

For every UID in the `members` list, grep the vault index. Verify the UID exists. If ANY member UID is missing, stop and report which one. Do not create a collection with dangling references.

### Step 3 — Create the collection folder if needed

If the `path` directory doesn't exist in `collections/`, create it (and any parent directories). Collections can live at arbitrary depth.

### Step 4 — Write the collection file

Write to `<path>/<filename>.collection.md` using the template in §5. Fill in members list. If `render_as: hierarchical`, use the header-grouped template variant.

### Step 5 — Write the collection-ref entry in the Vault

Write to `vault/files/<uid>.md`. This is the pointer entry that registers the collection's existence in the ledger. It references the collection file's path.

### Step 6 — Append the index record

Add a JSONL record with type `collection-ref`. The record includes the collection's name, purpose, and path (the path goes in the body of the collection-ref entry, not the index record directly).

### Step 7 — Confirm to the user

Report:
- The collection's UID
- Where it lives (`<path>/<filename>.collection.md`)
- The collection-ref entry location (`vault/files/<uid>.md`)
- The number of members
- Render mode (flat or hierarchical)

---

## 5. Templates

### Collection file template (flat)

```markdown
---
uid: <generated>
type: collection
collection_type: <manual | dynamic | ai-suggested>
name: "<name>"
owner: <owner>
purpose: "<purpose>"
render_as: flat
created: <today>
modified: <today>
file_ext: md
schema_version: 1
---

# <name>

*<purpose>*

## Members

- [[<uid>]] <optional readable label>
- [[<uid>]] <optional readable label>
- [[<uid>]] <optional readable label>

---

*<name> | Collection | Owner: <owner> | Created <date>*
```

### Collection file template (hierarchical)

```markdown
---
uid: <generated>
type: collection
collection_type: <manual | dynamic | ai-suggested>
name: "<name>"
owner: <owner>
purpose: "<purpose>"
render_as: hierarchical
created: <today>
modified: <today>
file_ext: md
schema_version: 1
---

# <name>

*<purpose>*

## <Grouping 1>

- [[<uid>]] <label>
- [[<uid>]] <label>

## <Grouping 2>

### <Nested Subgroup>

- [[<uid>]] <label>
- [[<uid>]] <label>

---

*<name> | Collection | Owner: <owner> | Created <date>*
```

### Collection-ref entry template (goes in vault/files/<uid>.md)

```markdown
---
uid: <same uid as collection>
type: collection-ref
status: active
title: "<name>"
description: "<purpose, ≤120 chars>"
owner: <owner>
created: <today>
modified: <today>
tags: [<tags>]
file_ext: md
schema_version: 1
collection_path: "<path>/<filename>.collection.md"
collection_type: <manual | dynamic | ai-suggested>
member_count: <count>
---

# <name> — Collection Reference

This is the Vault-side registration for the collection at [`<path>/<filename>.collection.md`](<relative path>).

**Purpose:** <purpose>

**Owner:** <owner>

**Member count:** <count>

**Collection type:** <type>

**Last synced:** <today>

---

*The collection's actual manifest (member list) lives in the collection file, not here. This entry is a pointer that makes the collection discoverable from the vault index.*
```

---

## 6. Verification

1. Both files exist: the collection file and the collection-ref entry
2. Both share the same UID
3. The collection-ref's `collection_path` field points to a real file
4. Every member UID in the collection file exists in the Vault
5. Index record exists with type `collection-ref`
6. Wikilinks in the collection file are valid `[[uid]]` format

**Visual verification (user-facing):**

After creating the collection, open the vault in Obsidian or VS Code. Confirm:
- The collection file is visible in the file tree at its expected path
- Clicking a `[[uid]]` wikilink in the collection file jumps to the referenced vault entry
- If `render_as: hierarchical`, the outline view shows the header structure

If visual verification fails in Obsidian (wikilinks don't resolve), document the limitation — this may indicate the need for an Obsidian plugin (Phase 1.C follow-on work).

---

## Failure Modes

| Failure | Action |
|---------|--------|
| UID collision | Regenerate |
| Member UID not found in ledger | Stop and report which one; ask user to fix or remove |
| Path contains invalid characters | Stop and ask for valid path |
| Write to collection file succeeded but vault entry failed | Remove the orphaned collection file, report |
| Write to ledger succeeded but collection file failed | Remove the orphaned vault entry, report |
| Collections folder doesn't exist | Create it (permitted for this action since collections/ is where the primitive lives) |

---

## A Note on Dogfooding

This action creates collections. The first real collection you should create is probably `collections/projects/tropo-ledger/phase-1-tasks.collection.md` — grouping the seven Phase 1 tasks plus the project plan plus the spec. That collection IS the human-facing view of the Tropo Vault project. It is exactly the use case that justifies building this action in the first place.

---

*Create Collection Action | v1.0 | Tropo OS | April 10, 2026*
*Reads: `.tropo/capsules/collection-ref.capsule.md`*
*Writes: `collections/<path>/<name>.collection.md`, `vault/files/<uid>.md`, `vault/00-index.jsonl`*
