---
title: "Create a Decision"
action_id: act-create-decision
version: 1.0
status: published
tier: os
target_capsule: decision
creates: "vault/files/<uid>.md (type: decision)"
author: tropo
created: 2026-04-10
last_updated: 2026-04-10
governed_by: 9b7f5e34  # action.capsule v1.1
member_of:
  - "2d083137"   # tropo-work (v1.12 backfill 2026-05-08)
---

# Create a Decision

*Atomic action: create a single architectural decision record (ADR) in the Vault.*
*Reads the `decision` capsule definition. Produces a valid decision file and an index record.*

---

## 1. Intent

This action creates one new decision entry in the Vault. A decision is an architectural or strategic choice recorded with its rationale, alternatives considered, and consequences. Decisions are the constitutional law of the vault — they record what was chosen and why, so that future agents can understand the reasoning.

**When to invoke this action:**

The user says something like:
- "Record the decision that we're going with JSONL for the index"
- "Write an ADR for the capabilities matrix framework"
- "Let's formally decide between option A and option B"

**Decisions are immutable once accepted.** A proposed decision can be edited freely. An accepted decision CANNOT be edited in place — corrections require creating a new decision that supersedes the old one. This is by design: the vault should preserve not just what was decided but what was originally proposed.

**Use a decision when:**
- There are multiple alternatives and a choice needs to be recorded
- The choice has lasting architectural or strategic implications
- Future agents will need to understand why the choice was made
- The decision warrants being un-editable after acceptance

**Do NOT use a decision for:**
- Open-ended design work — use `create-design-spec.action.md`
- Exploratory thinking — use `create-design-brief.action.md`
- Temporary preferences or session notes — use memory or workspace files

**Reference:** [`.tropo/capsules/decision.capsule.md`](../capsules/decision.capsule.md)

---

## 2. Prerequisites

1. **The Vault exists.**
2. **The decision capsule definition exists.**
3. **The vault index is writable.**
4. **If `supersedes` is provided,** the referenced UID must exist and have type `decision` with status `accepted`.

---

## 3. Inputs

### Required inputs

| Input | Type | Notes |
|-------|------|-------|
| `title` | string, ≤100 chars | The decision's headline. Use declarative form ("We will use JSONL for the vault index"). |
| `description` | string, ≤120 chars | One-line summary of the decision |
| `decision_number` | string | Sequential identifier (e.g., `ADR-032`). Compute by finding the highest existing ADR number in the Vault and incrementing. If no ADRs exist yet, start at `ADR-001`. |
| `proposer` | string | Agent or human who proposed the decision |
| `owner` | string | Usually the proposer; may differ |

### Optional inputs

| Input | Type | Notes |
|-------|------|-------|
| `supersedes` | UID | If this decision replaces a prior accepted decision |
| `refs` | array of UIDs | Related entries (specs, briefs, tasks that informed the decision) |
| `tags` | array | Topic classification |

---

## 4. Process

### Step 1 — Generate UID

8-char hex. Verify no collision.

### Step 2 — Compute decision number

Scan the vault index for all entries with type `decision`. Find the highest `decision_number` by parsing the `ADR-<n>` format in their titles or frontmatter. Increment. Assign the new number to this decision.

If no decisions exist yet, start at `ADR-001`.

### Step 3 — Validate inputs

- Title length ≤ 100 chars
- Description length ≤ 120 chars
- Proposer field is present
- Decision number follows the `ADR-<number>` pattern
- If `supersedes` is present, verify the referenced decision exists and is accepted

### Step 4 — Apply the template

The template MUST include an "Alternatives Considered" section. The decision capsule definition requires this — a decision without alternatives is not a decision, it's an instruction.

### Step 5 — Write the file

`vault/files/<uid>.md`

### Step 6 — Append the index record

Type `decision`, initial status `proposed`.

### Step 7 — If supersession, update the old decision

If `supersedes` is provided, update the old decision's `superseded_by` field to point at the new decision's UID. This is a frontmatter-only edit — the old decision's body is immutable.

### Step 8 — Confirm to the user

Report UID, decision number, location, initial status. Note clearly that the decision is PROPOSED, not accepted — acceptance is a separate state transition that requires the vault principal.

---

## 5. Template

```markdown
---
uid: <generated>
type: decision
status: proposed
title: "<ADR-number>: <title>"
description: "<description>"
owner: <owner>
created: <today>
modified: <today>
tags: [<tags>]
file_ext: md
schema_version: 1
decision_number: "<ADR-number>"
proposer: <proposer>
supersedes: <if present>
refs: [<refs>]
---

# <ADR-number>: <title>

*Status: PROPOSED*
*Proposed by: <proposer> on <date>*

---

## Context

<What situation led to this decision? What problem needed solving? What constraints shaped the choice?>

## The Decision

<The choice being proposed. State it clearly and declaratively. "We will use JSONL for the vault index" — not "We're considering JSONL." A decision is a commitment to a direction.>

## Alternatives Considered

### Alternative A: <name>

<Description of the alternative.>

**Pros:**
- <Pro>
- <Pro>

**Cons:**
- <Con>
- <Con>

### Alternative B: <name>

<Description.>

**Pros:**
- <Pro>

**Cons:**
- <Con>

### Alternative C: <name> (if applicable)

<Description.>

## Why This Choice

<The rationale. Why this alternative won. What criteria were applied. What trade-offs were accepted.>

## Consequences

**Positive:**
- <Consequence>
- <Consequence>

**Negative:**
- <Consequence or trade-off>
- <Consequence or trade-off>

**Neutral / to monitor:**
- <Thing to watch for>

## Implementation Notes

<If this decision requires specific follow-on work — what that work is, who owns it, what the timeline looks like.>

## References

- <Related spec, brief, task, or prior decision>

---

*<ADR-number> | Status: PROPOSED | Proposed by <proposer> | <date>*
```

---

## 6. Verification

1. File exists at `vault/files/<uid>.md`
2. Index record exists and matches
3. All v1 schema fields present
4. Status is `proposed`
5. Decision number follows the `ADR-<n>` pattern and is unique across decisions in the Vault
6. The body contains an "Alternatives Considered" section (required by the decision capsule definition)
7. If `supersedes` is present, the prior decision has been updated with `superseded_by`

---

## A Note on Acceptance

This action creates a decision in PROPOSED status. Accepting a decision is a SEPARATE operation that requires:

- The vault principal (or designated approver) explicitly accepting
- Setting `accepted_by` and `accepted_at` fields in the frontmatter
- Transitioning status from `proposed` to `accepted`

Once accepted, the decision is immutable. The body cannot be edited. Corrections must go through supersession — creating a new decision that points at the old one.

Acceptance is not yet covered by its own action file. For now, acceptance is done by editing the frontmatter directly. Future work may produce `accept-decision.action.md`.

---

## Failure Modes

| Failure | Action |
|---------|--------|
| UID collision | Regenerate |
| Decision number collision (unlikely but possible) | Recompute from current state |
| Missing alternatives section in provided content | Add placeholder; warn user alternatives are required |
| Supersedes target not accepted | Stop — cannot supersede a proposed decision |
| Ledger not present | Escalate |
| Partial write | Clean up, report |

---

*Create Decision Action | v1.0 | Tropo OS | April 10, 2026*
*Reads: `.tropo/capsules/decision.capsule.md`*
*Writes: `vault/files/<uid>.md`, `vault/00-index.jsonl`*
