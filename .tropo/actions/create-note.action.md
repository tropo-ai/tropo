---
title: "Create a Note"
action_id: act-create-note
version: 1.0
status: published
tier: os
target_capsule: note
creates: "vault/files/<uid>.md (type: note)"
author: tropo
created: 2026-04-12
last_updated: 2026-04-12
governed_by: 9b7f5e34  # action.capsule v1.1
member_of:
  - "2d083137"   # tropo-work (v1.12 backfill 2026-05-08)
---

# Create a Note

*Atomic action: create a single note entry in the Vault.*
*Reads the `note` capsule definition. Produces a valid note file and an index record.*

---

## 1. Intent

This action creates one new note entry in the vault's ledger. A note is the lightest governed primitive — a quick capture of an insight, observation, question, or idea with just enough structure to find it later.

**When to invoke this action:**

The user or agent says something like:
- "Capture that as a note"
- "That was a design insight, log it"
- "Create a note about X"
- "I want to remember this"

**Do NOT invoke this action for:**
- Work to do — use `create-task.action.md`
- A binding decision — use `create-decision.action.md`
- A formal specification — use `create-design-spec.action.md`
- Stream-of-consciousness capture — use the notebook (append-only, single-file)

**Reference:** The note capsule definition at [`.tropo/capsules/note.capsule.md`](../capsules/note.capsule.md) defines what a valid note IS. This action defines how to CREATE one.

---

## 2. Prerequisites

Before running this action, verify:

1. **The Vault exists.** `vault/` must be present at the vault root.
2. **The note capsule definition exists** at `.tropo/capsules/note.capsule.md`.
3. **The vault index is writable.** `vault/00-index.jsonl` must exist and be appendable.
4. **The `vault/files/` directory is writable.**

If any prerequisite fails, stop and report the failure.

---

## 3. Inputs

### Required inputs

| Input | Type | Notes |
|-------|------|-------|
| `title` | string, ≤100 chars | What the note is about. Short, descriptive. |
| `captured_by` | string | Agent-id or human name of who is writing this note. |

### Optional inputs

| Input | Type | Notes |
|-------|------|-------|
| `category` | string | From the Common Categories list in the capsule, or any freeform string. |
| `tags` | array of strings | Unlimited freeform tags. Lowercase, hyphen-separated. |
| `surfaced_by` | string | Who had the thought (if different from captured_by). |
| `context` | string, ≤120 chars | One-line "what we were doing when this surfaced." |
| `body` | string | The note content. Free-form markdown. Can be empty. |
| `refs` | array of UIDs | Related vault entries. |
| `project` | UID | If the note belongs to a project. |

### Rule of thumb

Notes are fast. Don't ask for every optional field. If the user says "capture that as a note," you need the title and you have the captured_by. Everything else is optional. Err on the side of creating the note quickly and letting the user add metadata later — the note exists to not lose the thought, not to perfectly classify it.

---

## 4. Process

### Step 1 — Generate UID

Produce an 8-character lowercase hex UID. Verify no collision in `vault/00-index.jsonl`.

### Step 2 — Validate inputs

- Title ≤ 100 chars, no newlines/tabs
- captured_by is non-empty, ≤ 30 chars
- If category present, non-empty string
- If tags present, each ≤ 30 chars
- If context present, ≤ 120 chars
- If refs present, each UID exists in the vault index

### Step 3 — Apply the template

Use `YYYY-MM-DDTHH:MM` for `created` (notes prefer datetime resolution per the capsule definition).

### Step 4 — Write the note file

Write to `vault/files/<uid>.md`.

### Step 5 — Append the index record

```json
{"uid":"<uid>","type":"note","status":"active","title":"<title>","description":"<context or title>","owner":"<captured_by>","created":"<datetime>","modified":"<datetime>","tags":[<tags>],"file_ext":"md","schema_version":1}
```

Add optional index fields if present: `project`, `created_by` (= `captured_by`).

### Step 6 — Confirm

Report: UID, location, title, category if set.

---

## 5. Template

```markdown
---
uid: <generated-8-hex>
type: note
status: active
title: "<title>"
owner: <captured_by>
created: <YYYY-MM-DDTHH:MM>
modified: <YYYY-MM-DDTHH:MM>
tags: [<tags with category if present>]
file_ext: md
schema_version: 1
captured_by: <captured_by>
surfaced_by: <if present>
category: <if present>
context: "<if present>"
refs: <if present>
project: <if present>
---

<body content — free-form markdown, or empty>
```

---

## 6. Verification

1. File exists at `vault/files/<uid>.md`
2. Index record exists in `00-index.jsonl`
3. Frontmatter matches index (uid, type, status, title, owner, created, modified, tags)
4. `captured_by` is present in frontmatter
5. UID is unique in the index

---

## Failure Modes

| Failure | Action |
|---------|--------|
| UID collision | Regenerate and retry |
| Invalid input | Stop and ask for correction |
| Ledger missing | Stop and escalate |
| Index unwritable | Stop and escalate |

---

*Create Note Action | v1.0 | Tropo OS | April 12, 2026*
*Reads: `.tropo/capsules/note.capsule.md`*
*Writes: `vault/files/<uid>.md`, `vault/00-index.jsonl`*
*"Capture it. Tag it. Find it later."*
