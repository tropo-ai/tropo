---
title: "Create a Design Brief"
action_id: act-create-design-brief
version: 1.0
status: published
tier: os
target_capsule: design-brief
creates: "vault/files/<uid>.md (type: design-brief)"
author: tropo
created: 2026-04-10
last_updated: 2026-04-10
governed_by: 9b7f5e34  # action.capsule v1.1
member_of:
  - "2d083137"   # tropo-work (v1.12 backfill 2026-05-08)
---

# Create a Design Brief

*Atomic action: create a single design brief entry in the Vault.*
*Reads the `design-brief` capsule definition. Produces a valid design-brief file and an index record.*

---

## 1. Intent

This action creates one new design-brief entry in the Vault. A design brief is an exploratory document that articulates a problem, proposes a framework, and informs a future design spec. Briefs are NOT locked — they inform.

**When to invoke this action:**

The user says something like:
- "Draft a brief for the capabilities matrix framework"
- "Write a design brief on the release pipeline concept"
- "I need to articulate the problem before I commit to a spec"

**Use a brief when:**
- You are exploring a problem space and need to articulate the question before proposing an answer
- You want to open a conversation rather than declare a position
- The thinking is rich but not yet ready for a lockable spec
- Multiple specs may eventually emerge from the same framing

**Do NOT use a brief when:**
- The thinking is locked-in enough to be a spec — use `create-design-spec.action.md`
- A decision needs to be recorded — use `create-decision.action.md`
- General reference material — use `create-document.action.md` (coming)

**Reference:** [`.tropo/capsules/design-brief.capsule.md`](../capsules/design-brief.capsule.md)

---

## 2. Prerequisites

1. **The Vault exists.**
2. **The design-brief capsule definition exists** at `.tropo/capsules/design-brief.capsule.md`.
3. **The vault index is writable.**

---

## 3. Inputs

### Required inputs

| Input | Type | Notes |
|-------|------|-------|
| `title` | string, ≤100 chars | Brief name — should reflect the problem being articulated |
| `description` | string, ≤120 chars | One-line summary of the brief's question or framework |
| `author` | string | Who drafted the brief (agent or human) |
| `owner` | string | Who owns the brief (usually the author; may differ for commissioned briefs) |

### Optional inputs

| Input | Type | Notes |
|-------|------|-------|
| `version` | string | Semantic version if iterating (`0.1`, `0.2`). Defaults to `0.1`. |
| `tags` | array | Topic classification |
| `informs` | array of UIDs | Specs this brief informs (usually empty at creation) |
| `refs` | array of UIDs | Related entries |

---

## 4. Process

### Step 1 — Generate UID

8-char hex. Verify no collision.

### Step 2 — Validate inputs

- Title length ≤ 100 chars
- Description length ≤ 120 chars
- Author and owner are present
- Version follows semantic versioning convention if present

### Step 3 — Apply the template

### Step 4 — Write the file

`vault/files/<uid>.md`

### Step 5 — Append the index record

Type `design-brief`, initial status `draft`.

### Step 6 — Confirm to the user

Report UID, location, version, and initial status.

---

## 5. Template

```markdown
---
uid: <generated>
type: design-brief
status: draft
title: "<title>"
description: "<description>"
owner: <owner>
created: <today>
modified: <today>
tags: [<tags>]
file_ext: md
schema_version: 1
version: <version, default 0.1>
author: <author>
informs: []
---

# <title>

*A design brief — not a spec. This document articulates the problem, proposes a framework, and raises open questions. It informs a future design spec but does not itself lock.*

---

## The Problem

<Articulate the problem the brief is addressing. What is broken, missing, or unresolved? What's the forcing function?>

## The Proposed Framework

<The core conceptual move. Not a full design — a frame for thinking about the problem.>

## Why This Frame

<Why this framing is the right one. What alternative framings were considered and rejected.>

## Open Questions

- <Question>
- <Question>
- <Question>

## What This Brief Does NOT Cover

<Scope boundaries — what's explicitly out of scope, deferred, or depends on other work.>

## What's Next

<What happens after this brief — does it become a spec? Does another brief need to come first? Who takes the next step?>

---

*<Brief title> | Draft v<version> | <author> | <date>*
```

---

## 6. Verification

1. File exists at `vault/files/<uid>.md`
2. Index record exists and matches file
3. All v1 schema fields present
4. Status is `draft` (initial state per the design-brief state machine)
5. Author field is populated

---

## Failure Modes

| Failure | Action |
|---------|--------|
| UID collision | Regenerate |
| Missing author | Stop and ask |
| Ledger not present | Escalate |
| Partial write | Clean up orphan, report |

---

*Create Design Brief Action | v1.0 | Tropo OS | April 10, 2026*
*Reads: `.tropo/capsules/design-brief.capsule.md`*
*Writes: `vault/files/<uid>.md`, `vault/00-index.jsonl`*
