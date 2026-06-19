---
title: "Create a Design Spec"
action_id: act-create-design-spec
version: 1.0
status: published
tier: os
target_capsule: design-spec
creates: "vault/files/<uid>.md (type: design-spec)"
author: tropo
created: 2026-04-10
last_updated: 2026-04-10
governed_by: 9b7f5e34  # action.capsule v1.1
member_of:
  - "2d083137"   # tropo-work (v1.12 backfill 2026-05-08)
---

# Create a Design Spec

*Atomic action: create a single design spec entry in the Vault.*
*Reads the `design-spec` capsule definition. Produces a valid design-spec file and an index record.*

---

## 1. Intent

This action creates one new design-spec entry in the Vault as a DRAFT. A design spec is an architectural document that defines how something works. Design specs go through draft, get locked by a locking authority, and may eventually be superseded.

**When to invoke this action:**

The user says something like:
- "Write a design spec for the Vault Phase 1"
- "Draft a spec for the release pipeline"
- "I want to formalize this as a lockable design spec"

**Design specs are contracts.** Once locked, they become authoritative. Drafts may be freely edited; locked specs may not be edited in place — amendments require a new version or supersession.

**Do NOT use this action for:**
- Exploratory thinking or framework articulation — use `create-design-brief.action.md`
- Architectural decisions (choices between alternatives) — use `create-decision.action.md`
- Reference documentation — use `create-document.action.md` (coming)

**Reference:** [`.tropo/capsules/design-spec.capsule.md`](../capsules/design-spec.capsule.md)

---

## 2. Prerequisites

1. **The Vault exists.**
2. **The design-spec capsule definition exists.**
3. **The vault index is writable.**
4. **If `supersedes` is provided,** the referenced UID must exist in the Vault and have type `design-spec` with status `locked`.

---

## 3. Inputs

### Required inputs

| Input | Type | Notes |
|-------|------|-------|
| `title` | string, ≤100 chars | Spec name |
| `description` | string, ≤120 chars | One-line summary of what the spec defines |
| `author` | string | Who drafted the spec |
| `owner` | string | Usually the author; may differ for commissioned specs |
| `version` | string | Semantic version. Defaults to `0.1`. |

### Optional inputs

| Input | Type | Notes |
|-------|------|-------|
| `reviewer` | string | Who will review before lock |
| `supersedes` | UID | If this spec replaces a prior spec |
| `refs` | array of UIDs | Related entries |
| `consistent_with` | array | External principles or specs this aligns with |
| `tags` | array | Topic classification |

---

## 4. Process

### Step 1 — Generate UID

8-char hex. Verify no collision.

### Step 2 — Validate inputs

- Title ≤ 100 chars
- Description ≤ 120 chars
- Version follows semantic versioning
- If `supersedes` is present, verify the referenced spec exists and is locked

### Step 3 — Apply the template

The template MUST include a `## How to Validate` section (required by the design-spec capsule definition before lock). The template in §5 includes this section pre-populated with a placeholder.

### Step 4 — Write the file

`vault/files/<uid>.md`

### Step 5 — Append the index record

Type `design-spec`, initial status `draft`.

### Step 6 — If supersession, update the old spec

If the new spec supersedes a prior locked spec, update the old spec's `superseded_by` field to point to the new spec's UID. This is a frontmatter-only edit (the old spec's body is immutable).

### Step 7 — Confirm to the user

Report UID, location, version, initial status.

---

## 5. Template

```markdown
---
uid: <generated>
type: design-spec
status: draft
title: "<title>"
description: "<description>"
owner: <owner>
created: <today>
modified: <today>
tags: [<tags>]
file_ext: md
schema_version: 1
version: <version>
author: <author>
reviewer: <if present>
supersedes: <if present>
refs: [<refs>]
consistent_with: [<consistent_with>]
---

# <title>

*<One-sentence subtitle stating what this spec defines.>*

---

## 1. Intent

<What this spec defines, why it exists, and what problem it solves.>

## 2. The Problem

<The current state or gap the spec addresses. Why the current approach doesn't work or doesn't exist.>

## 3. Design

<The proposed design. Structure, components, relationships, protocols. The heart of the spec.>

## 4. How It Works

<Operational description: how the design functions at runtime, under load, across agent interactions.>

## 5. What This Spec Does NOT Cover

<Explicit scope boundaries. What is deferred, what is out of scope, what depends on other specs.>

## 6. Migration / Rollout

<If this spec changes existing state, how the migration happens. Phased? All at once? Backward compatible?>

## 7. How to Validate

<REQUIRED per Rule 10 in design/AGENTS.md. How would this spec be tested if built? What does "this works" mean in practice? What tests prove it? What do the tests NOT prove?>

## 8. Open Questions

- <Question>
- <Question>

## 9. Design History

| Date | Who | What |
|------|-----|------|
| <today> | <author> | Initial draft |

---

*<Spec title> | Draft v<version> | <author> | <date>*
```

---

## 6. Verification

1. File exists at `vault/files/<uid>.md`
2. Index record exists and matches
3. All v1 schema fields present
4. Status is `draft`
5. Version field is present and follows semver convention
6. Author field is populated
7. The `## How to Validate` section is present in the body (required before lock per the design-spec capsule definition)
8. If supersedes, the prior spec has been updated with `superseded_by`

---

## A Note on Locking

This action creates a spec in DRAFT status. Locking a spec is a SEPARATE operation that requires:
- The locking authority (typically the vault principal)
- A `## How to Validate` section present in the body
- A reviewer sign-off (if specified)

Locking is not yet covered by its own action file (it is a state transition, not a creation). For now, locking is done by editing the file's frontmatter and body — future work may produce `lock-design-spec.action.md` for this transition.

---

## Failure Modes

| Failure | Action |
|---------|--------|
| UID collision | Regenerate |
| Missing How to Validate section | Add placeholder; warn user it must be filled before lock |
| Supersedes target not locked | Stop — cannot supersede a draft |
| Ledger not present | Escalate |
| Partial write | Clean up, report |

---

*Create Design Spec Action | v1.0 | Tropo OS | April 10, 2026*
*Reads: `.tropo/capsules/design-spec.capsule.md`*
*Writes: `vault/files/<uid>.md`, `vault/00-index.jsonl`*
