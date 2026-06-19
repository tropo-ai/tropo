---
uid: 7ea3def0
name: "team-def"
type: capsule-definition
extends: core
version: 1
tier: os
author: tropo
created: 2026-04-10
status: locked
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# team-def — Capsule Definition

**Relations**

| Relation | Target |
|---|---|
| Extends | `core` |

*A team definition — declares a composable grouping of agents and humans. Teams can contain other teams.*

## Intent

Track teams as first-class entities in the Vault. A team is a composable grouping of agents and/or humans (and/or other teams). Teams enable scoping for boards, collections, and verification — "show me what's owned by my team," "verify this against a member of the engineering team."

Per the federated levels architecture (UID 91664cd8), teams are the unit of governance between individual agents and the marketplace.

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `description` | string | ≤ 120 chars; the team's purpose |
| `members` | array | list of agent/human identifiers and/or team UIDs |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `parent_teams` | array of UIDs | teams this team belongs to |
| `charter_ref` | UID | reference to a document that charters this team |
| `visibility` | enum | `personal`, `team`, `marketplace` (per federated levels) |

## State Machine

```
active → archived
```

## Governance Rules (in addition to core)

1. **No cycles in parent_teams.** A team cannot be its own ancestor. The vault steward audits team graphs for cycles.
2. **Members can be agents, humans, or other teams.** Composition is recursive.
3. **Member changes are governed by the team's charter** if one exists. Otherwise, the team owner approves member changes.
4. **Archiving a team does not delete its membership history.** The archived team file is preserved.

## Validation Checks (run at check-in)

In addition to core checks:

1. Description length ≤ 120 chars
2. members field is present and is an array (may be empty for newly created teams)
3. If parent_teams is present, no cycles exist
4. Status is one of: `active`, `archived`
5. If visibility is present, value is one of `personal`, `team`, `marketplace`

## Inheritance

Extends `core`. Inherits all core rules.

---

*team-def capsule definition | LOCKED v1 | Tropo OS | April 10, 2026*
