---
title: "Generate a View"
action_id: act-generate-view
version: 1.0
status: published
tier: os
target_capsule: collection-ref
creates: "collections/<view-name>/ (folder hierarchy of collection files) + vault/files/<uid>.md entries for each collection-ref"
author: tropo
created: 2026-04-10
last_updated: 2026-04-10
governed_by: 9b7f5e34  # action.capsule v1.1
member_of:
  - "2d083137"   # tropo-work (v1.12 backfill 2026-05-08)
---

# Generate a View

*Atomic action: create a new view — a navigable folder hierarchy of collections — from a natural-language structure description.*
*The counterpart to `refresh-view`: generate-view creates a view from scratch; refresh-view updates an existing one.*

---

## 1. Intent

This action takes a natural-language description of how a human wants to organize a body of work, and generates a navigable folder hierarchy of collections under `collections/<view-name>/`. Each folder in the hierarchy contains one or more collection files; each collection file references vault entries by UID.

**A view is the user-facing term for a folder hierarchy of collections arranged for a specific human's purpose.** Mike can have a keystone-view. Vela can have a release-view. Each view contains many collections. Different users can create different views of the same underlying ledger.

**When to invoke this action:**

The user says something like:
- "Generate a view for project keystone with overview, discovery, sprints, and release sections"
- "Create a personal view of my current work organized by priority and project"
- "I want to see all the architecture work organized by component"
- "Set up a release-planning view with scope, timeline, and risks"

**When to use `refresh-view` instead:** when the view already exists and the user wants to update memberships based on new vault entries.

**Reference:** [`collection-ref.capsule.md`](../capsules/collection-ref.capsule.md) and the Phase 1 spec §7.

---

## 2. Prerequisites

1. **The Vault exists.**
2. **The `collections/` folder exists** at the vault root.
3. **The collection-ref capsule definition exists.**
4. **A natural-language description of the desired structure is available** from the user.
5. **The target view name is not already taken** (no existing folder at `collections/<view-name>/`). If taken, ask the user whether to refresh the existing view, replace it, or choose a different name.

---

## 3. Inputs

### Required inputs

| Input | Type | Notes |
|-------|------|-------|
| `view_name` | string | URL-friendly short identifier for the view. Becomes the root folder name. Example: `keystone-view`, `mike-view`, `release-planning`. Lowercase, hyphen-separated, no spaces. |
| `structure_description` | string | Natural-language description of the desired folder hierarchy. Example: "overview with charter and success criteria, discovery with research and design folders, sprints with sprint-01 containing plan/tasks/review/retro, release with scope and timeline." |
| `owner` | string | Who owns the view. Usually the requesting user. |

### Optional inputs

| Input | Type | Notes |
|-------|------|-------|
| `purpose` | string, ≤120 chars | One-line purpose statement for the view as a whole. If missing, derive from the structure description. |
| `source_scope` | natural language | Which vault entries should be candidate members. Example: "everything tagged keystone" or "all entries with parent_project=<uid>" or "all entries in the Tropo Vault project." If missing, the agent uses judgment based on the view name. |
| `max_depth` | integer | Maximum folder nesting depth. Default: 3. Prevents runaway hierarchies. |
| `empty_slot_behavior` | enum | `scaffold` (create empty collections as placeholders) or `skip` (only create collections with matching content). Default: `scaffold`. |

---

## 4. Process

### Step 1 — Interpret the structure description

The agent parses the natural-language structure description and produces an internal representation of the folder hierarchy. This is the interpretation step — the reasoning engine decides how to map the user's words to folders and collections.

Guidance for interpretation:
- Top-level phrases become top-level folders
- Sub-phrases become sub-folders
- Leaf phrases become collection files
- Explicit lists (plan, tasks, review, retro) become parallel collection files in a shared parent
- Ambiguous phrases should prompt the user for clarification, not be silently guessed

If the user's description is vague ("just the normal structure for a release project"), ask for more specificity rather than guessing the whole shape.

### Step 2 — Validate the structure

- Maximum depth respected
- No forbidden characters in folder or file names (use kebab-case, no spaces, no special chars)
- No name collisions between sibling collections
- The root `view_name` slot is not already taken

### Step 3 — Determine source scope

If `source_scope` was provided, parse it into candidate-matching criteria. If missing, derive candidates from the view name: a `keystone-view` would search for entries tagged `keystone` or with `parent_project` matching a keystone project UID. If neither tags nor parent_project match the view name, start with no candidates and rely on manual curation later.

### Step 4 — Generate UIDs

One UID per collection file that will be created. For a view with 18 collections, generate 18 UIDs. Verify none collide with existing entries in the vault index.

### Step 5 — Create the folder hierarchy

Walk the interpreted structure. For each folder node, create the directory under `collections/<view-name>/`. For each leaf collection, prepare the collection file path.

### Step 6 — Populate each collection

For each collection being created, walk the candidate entries from the source scope and decide which ones belong in THIS specific collection. The decision is based on:
- The collection's purpose (interpret the leaf name and its parent context)
- Matching entry fields (type, tags, status, owner)
- Reasonable judgment about where an entry best fits

Per the Pattern A + Pattern B layering from the design conversation:
- Store a `purpose` field in the collection's frontmatter (always — this is Pattern A)
- Store a `query` field in the frontmatter when the membership is query-expressible (Pattern B, optional acceleration)
- Store the resolved members as an explicit list in the body (what the last generation or refresh produced)

If the collection has no matching entries, create an empty scaffolding file (if `empty_slot_behavior: scaffold`) or skip the slot (if `empty_slot_behavior: skip`).

### Step 7 — Write the root view file

At `collections/<view-name>/<view-name>.collection.md`, create a root collection file that serves as the view's table of contents. Its `members` list contains the UIDs of the top-level child collections. Its body provides a human-readable overview of the view's structure.

### Step 8 — Register every collection in the Vault

For each collection file created, write a matching `collection-ref` entry in `vault/files/<uid>.md` and append a record to `vault/00-index.jsonl`. The collection-ref entry includes the collection's `collection_path` field pointing at the file's location under `collections/`.

### Step 9 — Confirm to the user

Report:
- The view's root folder path
- The total number of collections created
- How many are populated vs. empty scaffolding
- Any friction findings (entries that didn't cleanly map, structure mismatches with the source data)
- Suggested next action: "open `<view-name>/<view-name>.collection.md` in your editor to navigate"

---

## 5. Template

The view generation produces many files, each matching the standard collection template. See [`create-collection.action.md`](create-collection.action.md) §5 for the individual collection file templates (flat and hierarchical variants).

The root view file uses a slight extension of the standard collection template — its body contains an "About This View" section explaining that the view was generated from a structure description, when it was generated, and by whom.

---

## 6. Verification

1. Every collection file created has a matching `collection-ref` entry in the Vault
2. Every collection file's UID matches its vault entry's UID
3. Every member UID referenced in any collection exists in the Vault
4. The folder hierarchy matches the interpreted structure
5. The root view file exists and references all top-level child collections
6. No duplicate UIDs anywhere in the generated set

**Visual verification (user-facing):**

After generation, the user opens the vault in their editor. Confirm:
- The `collections/<view-name>/` folder appears in the file tree
- Navigating into sub-folders reveals the expected collection files
- Opening any collection file shows a readable markdown document
- Wikilinks `[[uid]]` in collection bodies resolve to vault entries

If visual verification fails (wikilinks don't resolve, folder structure doesn't render), document the limitation and report back.

---

## Failure Modes

| Failure | Action |
|---------|--------|
| View name collision | Stop and ask user: refresh existing, replace, or rename |
| UID collision | Regenerate and retry |
| Ambiguous structure description | Stop and ask user for clarification on specific ambiguous parts |
| Source scope returns zero candidates | Proceed with empty scaffolding; warn user |
| Partial write (some collections created, some failed) | Stop and report; do not leave the view in a half-built state — either complete or roll back |
| Maximum depth exceeded | Stop and ask user to simplify the structure |

---

## A Note on Sharing Views

A view is a pure, portable artifact under L1. To share a view:
- Copy the `collections/<view-name>/` folder to another vault
- The view's collection files reference vault entries by UID — if the target vault has matching UIDs, the view works immediately
- If the target vault has different UIDs, the view's wikilinks will not resolve until the target vault is synchronized

This makes views trivially shareable within a crew that shares a ledger. Cross-vault sharing requires UID reconciliation — a Phase 2+ concern handled by the hosted service tier.

---

## Pairs With

- [`refresh-view.action.md`](refresh-view.action.md) — refreshes an existing view's memberships without regenerating the structure
- [`create-collection.action.md`](create-collection.action.md) — creates a single collection (generate-view creates many at once)

---

*Generate View Action | v1.0 | Tropo OS | April 10, 2026*
*Reads: `.tropo/capsules/collection-ref.capsule.md`*
*Writes: `collections/<view-name>/**/*.collection.md`, `vault/files/<uid>.md` (many), `vault/00-index.jsonl` (many records)*
