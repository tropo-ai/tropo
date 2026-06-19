---
uid: b0a4dde7
name: "board-def"
type: capsule-definition
extends: core
version: 1
tier: os
author: tropo
created: 2026-04-10
modified: 2026-04-20
modified_by: argus-a29
status: superseded
superseded_by: b0d1e4f2 # board-definition
superseded_at: 2026-04-20
superseded_reason: "Dead schema — zero live instances in the vault. sa.research 023 (2026-04-20) confirmed no type: board-def entries ever existed. Superseded by board-definition capsule per Board Reconciliation v0.3 (74fd9b61)."
---

# board-def — Capsule Definition (SUPERSEDED)

**Relations**

| Relation | Target |
|---|---|
| Extends | `core` |
| Superseded by | [board-definition.capsule (b0d1e4f2)](board-definition.capsule.md) |

**⚠️ SUPERSEDED 2026-04-20.** This capsule governed a type that was never populated. [sa.research 023 (2026-04-20)](../../agents/sa/sa.research/activation-log/023-board-reconciliation-inventory.md) confirmed zero live `type: board-def` entries in the vault — the capsule was locked 2026-04-10 but writers always targeted `type: board` (the sibling capsule) instead. Retired via the cleanest path: supersede, do not migrate (nothing to migrate).

Replacement: **[board-definition (b0d1e4f2)](board-definition.capsule.md)** — which inherits and refines the "template" intent from this capsule, with sharper naming (`scope` not `scope_type`), expanded enum (adds `project` scope), and the `sections:` array for machine-readable query specs.

This file remains in the vault for historical reference. Do not read it as active governance; read the replacement above.

---

## Original Capsule Text (Historical)

*A board definition — declares a board's scope, sources, and display preferences. The board itself is a regenerated view, not stored in the ledger.*

## Intent

Boards are generated views of work state. A board definition declares what the board shows (scope), where to get the data (sources), and how to render it (display preferences). The actual board view (`current.md` or equivalent) is regenerated from the definition; it is NOT a ledger entry.

The board-def is what the ledger holds — the definition. The view is ephemeral.

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `description` | string | ≤ 120 chars; what this board shows |
| `scope_type` | enum | one of `owner`, `team`, `collection`, `query` |
| `scope_value` | string | the value for the scope (e.g., agent name, team UID, collection UID, query string) |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `sources` | array | filesystem paths or queries the board reads from |
| `refresh_cadence` | string | how often the board regenerates (e.g., `4x-daily`, `on-demand`, `weekly`) |
| `display_preferences` | object | rendering options (columns, sort, filter, etc.) |
| `current_view_path` | string | filesystem path where the regenerated view is written |

## State Machine

```
active → archived
```

## Governance Rules (in addition to core)

1. **The board-def is the source of truth for what the board shows.** The view is regenerated from the definition, not edited directly.
2. **The view file is not a ledger entry.** It is an ephemeral artifact written by the board generator.
3. **Editing the view directly is forbidden.** Changes must go through the definition.

## Validation Checks (run at check-in)

In addition to core checks:

1. Description length ≤ 120 chars
2. scope_type is one of `owner`, `team`, `collection`, `query`
3. scope_value is present and non-empty
4. Status is one of: `active`, `archived`

## Inheritance

Extends `core`. Inherits all core rules.

---

*board-def capsule definition | LOCKED v1 | Tropo OS | April 10, 2026*
