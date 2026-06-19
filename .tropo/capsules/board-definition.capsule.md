---
subsystem_hub:
  - "2d083137"
uid: "b0d1e4f2"
name: "board-definition"
type: capsule-definition
extends: core
version: 1.1
supersedes_version: "1.0"
tier: os
author: tropo
created: 2026-04-20
modified: 2026-04-28
created_by: argus-a29
modified_by: argus-a38
status: locked
schema_version: 2
extraction_scope: ship
governed_by: "74fd9b61" # Board System Reconciliation Design Spec v0.3
aligned_with: "a7c4e5b2" # ADR-035 — Declared-Presence Validation Rule
composes_with: "b5a7c391" # board-snapshot.capsule (sibling pair — definition templates the render; snapshot freezes one render in time)
supersedes: "b0a4dde7" # retires board-def capsule (dead schema — zero live instances)
---

# board-definition — Capsule Definition v1.1

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Board System Reconciliation — Unified Capsule Design (74fd9b61)](../../vault/files/74fd9b61.md) |
| Aligned with | [ADR-035 — Declared-Presence Validation Rule (a7c4e5b2)](../../vault/files/a7c4e5b2.md) |
| Extends | `core` |
| Supersedes | [board-def.capsule (b0a4dde7)](board-def.capsule.md) |

*A template declaring what a board shows — scope, recursion, sections with prose queries, render format. Stable, long-lived artifact in the Vault. Regenerations read the definition but do not create new definition entries.*

---

## Intent

A `board-definition` is a governed template for rendering boards. It names the target scope (project, team, collection, query), the recursion semantics, and an ordered list of sections — each a prose query against the Vault rendered in a declared format.

The kernel ships one default board-definition: **`project-board`** (UID [c72f1a85](../seed/ledger/project-board.board-definition.md)). Projects inherit it as their status board when they declare no `status_board:`. Agents and humans can author additional board-definitions (custom status boards, grooming boards, sprint boards, portfolio boards) and projects declare which they use via named fields on the project frontmatter.

This capsule supersedes [board-def.capsule (b0a4dde7)](board-def.capsule.md) (dead schema — zero live instances) and takes over the "template" half of the pre-v0.3 [board.capsule (00ac0959)](board.capsule.md) (whose rendered-view half is now governed by [board-snapshot.capsule (b5a7c391)](board-snapshot.capsule.md)).

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `type` | literal | Must be `board-definition` |
| `name` | string | Canonical short name. Lowercase, hyphens (e.g., `project-board`, `team-portfolio`, `sprint-board-q2`). Used for [§6.2 default-lookup (74fd9b61)](../../vault/files/74fd9b61.md) when `default_for:` is set. |
| `intent` | enum | One of: `status | grooming | sprint | portfolio | custom`. Governs binding to project named fields (`status_board:`, `grooming_board:`, etc.). |
| `scope` | enum | One of: `project | owner | team | collection | query`. |
| `sections` | array | Ordered list of section specs. See §Section Spec below. |
| `author` | string | Agent or human who authored this definition. Required per [ADR-035 Surface 2](../../vault/files/a7c4e5b2.md). |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `default_for` | enum | If this definition is a kernel default, the type it defaults for (e.g., `project`). Only present on kernel seeds under `.tropo/seed/vault/`. |
| `recursion` | enum | One of: `subtree | direct | deep=<N>`. Default when omitted: `subtree`. |
| `description` | string | ≤ 200 chars. Human-readable purpose. |
| `supersedes` | UID | Prior version of this definition. |

## Section Spec (values in the `sections:` array)

Each section is an object with the following fields:

| Field | Type | Required? | Semantics |
|-------|------|-----------|-----------|
| `title` | string | required | Rendered as `## <title>` in the output. |
| `query` | prose string | required | Executable query per [v0.3 §7.2 vocabulary](../../vault/files/74fd9b61.md). |
| `render` | enum | required | One of: `table | list | list-with-links | tree`. See [v0.3 §7.2.1 exemplars](../../vault/files/74fd9b61.md). |
| `columns` | array | required when `render: table` | Frontmatter field names. Unknown fields → blank cell. |
| `sort` | string | optional | Sort spec. Default when omitted: `modified DESC`. |
| `group_by` | string | optional | `<field>`, or `<field> then <field>`, or `tag=<literal> first, then others`. |
| `limit` | integer | optional | Max rows. Default: unbounded. |
| `null_result` | string | optional | Displayed when zero rows match. Default: `"— No results. —"`. |

---

## State Machine

```
draft → active → superseded
```

| State | Meaning |
|-------|---------|
| `draft` | Being written or not yet verified. Do not reference from a project's named-board field. |
| `active` | Verified and approved. May be referenced by projects and kernel seeds. |
| `superseded` | Replaced by a newer version with `supersedes:` pointer. Retained for history. |

**Transition rules:**
- `draft` → `active` requires: (a) verification by the author (cold-boot test optional for custom definitions, required for kernel seeds), (b) unique `(type: board-definition, name, default_for)` triple in the ledger when `default_for:` is set (see [v0.3 §6.2](../../vault/files/74fd9b61.md)).
- Only one kernel seed per `(name, default_for)` may be `active` at any time.

---

## Governance Rules

1. **Definitions are read-only at rendering time.** An agent rendering a board reads the definition; it does not modify the definition.
2. **Definitions do not contain rendered data.** The body is free-form documentation about the template's purpose — not the rendered board itself.
3. **Name uniqueness for defaults** is enforced at [v0.3 §6.2 lookup time](../../vault/files/74fd9b61.md) — two active definitions with the same `(name, default_for)` triple cause a fail-loud halt.
4. **Custom definitions can reuse names.** Two projects may each have a custom `sprint-board` definition with distinct UIDs; the name is for human referenceability, uniqueness is UID-based.
5. **Body format is free.** The capsule governs the `sections:` array (machine-readable); the body is human prose.

---

## Validation Checks (run at check-in)

1. `type: board-definition` present.
2. `name` non-empty, lowercase-hyphens only.
3. `intent` in allowed enum.
4. `scope` in allowed enum.
5. `sections` present with at least one entry; each entry has required fields (title, query, render).
6. Each section's `render` value is in the allowed enum.
7. If `render: table`, `columns` is non-empty.
8. Each section's `query` string uses only vocabulary declared in [v0.3 §7.2](../../vault/files/74fd9b61.md).
9. If `default_for:` is set, `author: tropo` (kernel seed convention; non-tropo authors cannot ship defaults).
10. ADR-035 Surface 2: any UID referenced in a section query (e.g., `referenced by cascade of <uid>`) must resolve in the Vault.

---

## Studio — Shop Signage

*Tools and rules-at-a-glance for authoring + maintaining a `board-definition`. Read this section first when you sit down at the board-definition bench.*

### Tools

| Tool | Verb (v3 Decision 13) | When |
|---|---|---|
| Manual authoring at `vault/files/<uid>.md` | **author** | Drafting a new definition (custom or kernel seed) |
| Stage flip draft → active | **lock** | Definition reviewed and ready to be bound by projects / referenced by snapshots |
| Supersede with a new definition | **supersede** | Material change to template structure; old becomes `state: superseded` |

### Skills

| Skill | When |
|---|---|
| [regenerate-board.skill](../skills/regenerate-board.skill.md) | The renderer. Reads a definition + queries the Vault; produces a current rendered view |
| [create-snapshot.skill (d847e2b3)](../skills/create-snapshot.skill.md) | Creates a [board-snapshot](board-snapshot.capsule.md) from this definition at a specific moment |

### Procedures

- **Authoring a custom definition.** (1) Generate a UID via `openssl rand -hex 4` (or any random-hex source). (2) Author at `vault/files/<uid>.md` with `type: board-definition`, `state: draft` (the lifecycle field is `state:` per §State Machine — not `stage:`). (3) Set `name:` (lowercase-hyphens), `intent:` (status / grooming / sprint / portfolio / custom — match the project's named-field binding: `status_board:` ↔ `intent: status`, `grooming_board:` ↔ `intent: grooming`, etc.; `custom` is for definitions not bound by a named field), `scope:` (project / owner / team / collection / query). (4) Author the `sections:` array — each section is `{title, query, render, columns?, sort?, group_by?, limit?, null_result?}`. Use only the prose-query vocabulary declared in [§7.2 of the design spec (74fd9b61)](../../vault/files/74fd9b61.md). The kernel seed at [project-board (c72f1a85)](../seed/ledger/project-board.board-definition.md) is the canonical reference shape — copy from it. (5) Verify (cold-boot test optional for custom; required for kernel seeds). (6) Flip `state: draft → active`.
- **Authoring a kernel seed.** Same as custom + set `default_for: <type>` and `author: tropo`. Kernel seeds live under `.tropo/seed/vault/`. Only one seed per `(name, default_for)` may be active at a time.
- **Binding to a project.** Edit the project's frontmatter to declare a named-field reference: `status_board: <board-definition uid>`, `grooming_board:`, `sprint_board:`, `portfolio_board:`. See [project.capsule §Optional Frontmatter](project.capsule.md) for the full list of named fields. Without a named field, projects fall back to the kernel `project-board` default.
- **Decide whether to snapshot.** A regeneration produces a current view; a snapshot freezes one render in time. Take a snapshot when the moment matters (pre-ship, stage-close, pre-change checkpoint) — invoke [create-snapshot.skill (d847e2b3)](../skills/create-snapshot.skill.md). Otherwise let regenerations stay ephemeral. See sibling [board-snapshot.capsule (b5a7c391)](board-snapshot.capsule.md) for the snapshot-side discipline.
- **Superseding a definition.** Author the successor with `supersedes: <prior-uid>`. Flip the prior's `state: active → superseded`. Existing snapshots retain pointers to the superseded version — they're historical truths.

### Rules at a glance

1. **Definitions are read-only at rendering time.** The renderer reads; never modifies.
2. **Body is human prose, not rendered data.** The body documents the template's purpose. The render lives in [board-snapshot](board-snapshot.capsule.md) bodies, not here.
3. **Name uniqueness for kernel defaults.** Two active definitions with the same `(name, default_for)` triple cause a fail-loud halt at lookup time.
4. **Custom names can repeat across definitions.** Two projects may each have a `sprint-board` definition; uniqueness is UID-based, not name-based.
5. **Section queries must use only declared vocabulary.** Per [§7.2 of the design spec (74fd9b61)](../../vault/files/74fd9b61.md). Unknown query terms are a validation error, not a render error.
6. **ADR-035 Surface 2:** any UID referenced in a section query (e.g., `referenced by cascade of <uid>`) must resolve in the Vault.

### Pitfalls

- **Rendered data in the body** → conflates the template with the render. The body is documentation; the render is in the snapshot.
- **Two active kernel seeds with the same `(name, default_for)`** → fail-loud halt at the first project that tries to resolve the default. Always supersede the prior, never parallel-author.
- **Section query referencing a UID that doesn't resolve** → ADR-035 Surface 2 violation; render fails. Fix the reference or remove the section.
- **Author non-tropo with `default_for:` set** → only kernel seeds may declare defaults. Custom definitions omit `default_for:`.
- **Editing a `superseded` definition's body** → snapshots that reference it are now misaligned with the documented template. Don't edit superseded definitions; author successors instead.

### Worked examples

- **[project-board kernel seed (c72f1a85)](../seed/ledger/project-board.board-definition.md)** — the canonical kernel default that ships with Tropo-OS. Every project without a `status_board:` named-field reference inherits this. Read it as the reference shape for any new board-definition.

### Go next

- **Pair capsule:** [board-snapshot.capsule (b5a7c391)](board-snapshot.capsule.md) — the frozen render produced from this template at a moment in time.
- **Renderer:** [regenerate-board.skill](../skills/regenerate-board.skill.md).
- **Project binding:** [project.capsule v2.3+ (34e4cb0b)](project.capsule.md) §Optional Frontmatter for the named-field references.
- **Design spec:** [Board System Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md) §7.2 for the section-query vocabulary; §6.2 for default-lookup semantics.

---

## Relationship to `board-snapshot`

A `board-definition` is a template. A `board-snapshot` is a frozen render of that template against live sources at a specific `taken_at`. The relationship is one-to-many: one definition can produce many snapshots over time.

Snapshots reference their source definition via `board_definition: <uid>`. Definitions do not track their snapshots; the inverse edge emerges from the index.

When a board-definition is `superseded`, existing snapshots retain their `board_definition:` pointer to the superseded version — they are historical truths of what the template WAS at their `taken_at`.

---

## Relationship to `project`

Projects declare named-field references to board-definitions:

```yaml
status_board: <board-definition uid> # optional — falls back to project-board default
grooming_board: <board-definition uid> # optional
sprint_board: <board-definition uid> # optional
portfolio_board: <board-definition uid> # optional
```

See [project.capsule v2.1 (34e4cb0b)](project.capsule.md) §Optional Frontmatter for the full named-field list. Additional named fields require a capsule update (capsule is the schema, governance through convention).

---

## Example — Kernel Default

See [`project-board` kernel seed (c72f1a85)](../seed/ledger/project-board.board-definition.md) for the shipped default. That file is the canonical example of a valid board-definition.

---

## Inheritance

Extends `core`. Inherits all core rules (uid, type, state, schema_version, provenance). Adds the frontmatter constraints and validation checks declared above. Not currently extended by subtypes.

---

*board-definition Capsule Definition | v1.1 | argus-a38 | 2026-04-28 (Stream 3 D3.2 — §Studio + composes_with sibling); v1.0 lock 2026-04-20 by Argus A29 preserved in git history*
*Supersedes [board-def (b0a4dde7)](board-def.capsule.md). Pairs with [board-snapshot (b5a7c391)](board-snapshot.capsule.md).*
*"The template lives. The render is ephemeral. The snapshot is the record."*

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-04-20 | Initial lock. Supersedes board-def.capsule (b0a4dde7). Companion to board-snapshot.capsule (b5a7c391). Defines template-side of the board system per [Board System Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md). | argus-a29 |
| 1.1 | 2026-04-28 | **Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop).** Added §Workshop — Shop Signage section (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next) per the v3 capsule shop-signage pattern proven at 19-capsule scale. Added `composes_with: b5a7c391` (sibling board-snapshot.capsule). No semantic changes to §Required Frontmatter / §Section Spec / §Validation Checks / §Governance Rules / §State Machine. UID preserved at b0d1e4f2. | argus-a38 |
