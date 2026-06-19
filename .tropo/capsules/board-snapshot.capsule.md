---
uid: "b5a7c391"
name: "board-snapshot"
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
composes_with: "b0d1e4f2" # board-definition.capsule (sibling pair — definition templates the render; snapshot freezes one render in time)
supersedes: "00ac0959" # retires pre-v0.3 board capsule (the rendered-view half)
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# board-snapshot — Capsule Definition v1.1

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Board System Reconciliation — Unified Capsule Design (74fd9b61)](../../vault/files/74fd9b61.md) |
| Aligned with | [ADR-035 — Declared-Presence Validation Rule (a7c4e5b2)](../../vault/files/a7c4e5b2.md) |
| Extends | `core` |
| Supersedes | [board.capsule (00ac0959)](board.capsule.md) |

*A governed vault entry containing a rendered view of a board-definition at a specific point in time. UID-addressable, preserved in the graph for historical reference. Created deliberately, not on every regeneration.*

---

## Intent

A `board-snapshot` is a frozen render — what a board looked like at `taken_at`. It is a historical record, not a live view. Regenerating a board does NOT create a snapshot; snapshots are created explicitly by [`create-snapshot.skill.md` (d847e2b3)](../skills/create-snapshot.skill.md) or by direct action when a moment matters (release ship, stage close, pre-change checkpoint).

Snapshots are the "what did it look like on date X?" side of the board system. Regenerations are the "what does it look like right now?" side. Both are valid; they serve different questions.

This capsule supersedes the rendered-view half of [board.capsule (00ac0959)](board.capsule.md). The ~60 existing `type: board` ledger entries migrate to `type: board-snapshot` per [v0.3 §9.1 (74fd9b61)](../../vault/files/74fd9b61.md) migration table (current ledger count: ~65 — figure has drifted slightly post-migration as new snapshots have been taken).

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `type` | literal | Must be `board-snapshot` |
| `snapshot_of` | UID | The project / team / collection / other scope target this snapshot captures. Required per [ADR-035 Surface 2](../../vault/files/a7c4e5b2.md) — must resolve in the ledger. |
| `board_definition` | UID | The `board-definition` that produced this snapshot. Required per [ADR-035 Surface 2](../../vault/files/a7c4e5b2.md) — must resolve. |
| `taken_at` | ISO 8601 | Minute-precision (`YYYY-MM-DDTHH:MM`). Vault-local time. No timezone suffix on writes; readers parse leniently. |
| `taken_by` | string | Agent or human who triggered the snapshot. |
| `reason` | string | Free prose naming why this moment mattered. Required (not optional) — helps future readers orient. |
| `scope` | enum | One of: `project | owner | team | collection | query`. Mirrors the originating definition's `scope`. |
| `scope_ref` | UID or string | Mirrors the scope target. Redundant with `snapshot_of` when `scope: project`; retained for index-lookup performance. |
| `state` | enum | `active` or `archived`. Inherited from core. Creation default: `active`. |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `trigger` | string | What prompted creation — e.g., `"pre-v1.2-ship"`, `"stage-close"`, `"manual"`. |
| `superseded_by` | UID | Rare. Present only when a snapshot was replaced (e.g., corrected after a render defect). Supersedes are the exception; normally snapshots are immutable. |

---

## Body

The snapshot's body IS its payload — the rendered markdown. Sections, tables, links, null-results — rendered per the source `board-definition`'s `sections:` array, in the render formats locked by [v0.3 §7.2.1 (74fd9b61)](../../vault/files/74fd9b61.md).

Body format is free in the sense that the capsule does not prescribe it beyond "the output of the definition's sections." Definition-governed; not snapshot-governed.

---

## State Machine

```
active → archived
```

| State | Meaning |
|-------|---------|
| `active` | Current record. Readers trust its `taken_at` as the anchor for historical queries. |
| `archived` | No longer indexed by default (e.g., very old snapshots archived to reduce index noise). Still readable; just not in default queries. |

**No `build → done → superseded` lifecycle.** A snapshot is not a live view that gets replaced by a newer live view. It is a historical record. Archival is a grooming operation (after ~180 days per [v0.3 §11 Open Question 1](../../vault/files/74fd9b61.md)); it is not a supersession.

**Immutability.** Once a snapshot is written with `state: active`, its body and its `taken_at` MUST NOT be modified. Typos in `reason:` or `taken_by:` may be corrected; the payload and timestamp are sealed. If a defect is discovered, write a new snapshot with an updated `reason:` noting the prior was defective, then archive the defective one.

---

## UID Generation

Snapshots are created by [`create-snapshot.skill.md` (d847e2b3)](../skills/create-snapshot.skill.md) which calls the core UID primitive (8-hex random, verified unique against the vault index before write). Agents writing snapshots directly without the skill MUST call the same primitive — see v0.3 §5.2.

---

## Governance Rules

1. **Snapshots are generated, never authored.** A human or agent triggers creation; the rendering engine produces the body. Manual body edits are prohibited.
2. **Snapshots are historical truths, not current state.** See [v0.3 §8 cold-boot reader rule (74fd9b61)](../../vault/files/74fd9b61.md). A current-status query regenerates from the definition against live sources; a historical-date query reads the closest-before snapshot.
3. **Snapshots are never deleted.** Deletion semantics are deferred to [eda09d06 Schemaless Document Store](../../vault/files/eda09d06.md). Until that lock, snapshots move to `state: archived` at most, never removed from the ledger.
4. **`snapshot_of` and `board_definition` MUST resolve.** Per ADR-035 Surface 2. Write-time validation; the snapshot cannot be written if either target is unreachable.

---

## Validation Checks (run at check-in)

1. `type: board-snapshot` present.
2. All nine required frontmatter fields present.
3. `snapshot_of` resolves in the vault index.
4. `board_definition` resolves in the vault index AND has `type: board-definition`.
5. `taken_at` is valid ISO 8601 minute-precision.
6. `scope` value is in the allowed enum.
7. If `scope: project`, `scope_ref == snapshot_of` (the redundancy invariant).
8. `state` is `active` or `archived`.
9. `reason` non-empty.

---

## Studio — Shop Signage

*Tools and rules-at-a-glance for creating + curating a `board-snapshot`. Read this section first when a moment in vault state matters enough to capture it.*

### Tools

| Tool | Verb (v3 Decision 13) | When |
|---|---|---|
| Create snapshot via skill | **author** (via the skill) | A specific moment matters: pre-ship, stage-close, pre-change checkpoint |
| State flip active → archived | **archive** | Old snapshot superseded by re-take (rare) or retired after ~180 days per design-spec convention |
| Supersede on rare defect-correction | **supersede** | A defective snapshot must be replaced; original moves to `state: archived` with a `superseded_by:` pointer |

### Skills

| Skill | When |
|---|---|
| [create-snapshot.skill (d847e2b3)](../skills/create-snapshot.skill.md) | Canonical creation path — calls the UID primitive, materializes the body from the source [board-definition](board-definition.capsule.md), validates ADR-035 Surface 2 |
| [regenerate-board.skill](../skills/regenerate-board.skill.md) | Companion (NOT for snapshots) — produces a current view; renders are ephemeral; this skill does NOT create snapshots |

### Procedures

- **Taking a snapshot.** Invoke [create-snapshot.skill](../skills/create-snapshot.skill.md) with `snapshot_of: <project|team|collection uid>`, `board_definition: <uid>`, `taken_by:`, `reason:`. The skill calls the UID primitive, renders the body from the definition's `sections:` array against live sources, and writes the entry at `vault/files/<uid>.md` with `state: active`.
- **Reading "what was the world on date X?"** Read the closest-before-X snapshot. The snapshot's `taken_at` anchors it; its body is the rendered template at that moment. Do NOT regenerate from the definition — regenerations show current state, not historical truth.
- **Reading "what is the world right now?"** Regenerate from the source [board-definition](board-definition.capsule.md). Snapshots are not for current-status queries; regenerations are.
- **Archiving an old snapshot.** Flip `state: active → archived`. The snapshot remains in the ledger (never deleted) and remains queryable; it just falls out of default-active queries. Convention: archive after ~180 days per [design-spec §11 Open Question 1 (74fd9b61)](../../vault/files/74fd9b61.md).
- **Correcting a defective snapshot (rare).** Author a new snapshot with corrected `reason:` noting the prior was defective. Set the old one's `state: archived` and `superseded_by: <new-uid>`. Never edit the defective snapshot's body — immutability holds.

### Rules at a glance

1. **Snapshots are generated, never authored by hand.** A human or agent triggers; the rendering engine produces the body. Manual body edits are prohibited.
2. **Snapshots are historical truths, not current state.** A current-status query regenerates from the definition. A historical-date query reads the closest-before snapshot.
3. **Snapshots are never deleted.** Archived only. Deletion semantics deferred to [Schemaless Document Store (eda09d06)](../../vault/files/eda09d06.md).
4. **`snapshot_of:` and `board_definition:` MUST resolve.** Per ADR-035 Surface 2; write-time validation halts the create if either target is unreachable.
5. **Body and `taken_at` are immutable after `state: active`.** Typos in `reason:` / `taken_by:` may be corrected; payload and timestamp are sealed.
6. **Reason is required, not optional.** Helps future readers orient: pre-v1.4-ship / stage-3-close / pre-migration-checkpoint.

### Pitfalls

- **Treating snapshots as current state** → readers consult a stale snapshot for "what's true today." Use regenerations for current; snapshots for historical.
- **Manual body edits after creation** → governance violation; immutability is the entire value proposition. Re-take if the data is wrong.
- **Missing `reason:`** → snapshot is illegible to future readers. Always populate.
- **Authoring the body directly without the skill** → bypasses UID primitive + ADR-035 validation. Always go through [create-snapshot.skill](../skills/create-snapshot.skill.md).
- **Deleting an old snapshot** → no. Archive instead. The historical trail is the value.
- **Snapshotting on every regeneration** → snapshots accumulate without value. Take them at moments that matter, not on every render.
- **`scope: query` snapshots have no resolvable `snapshot_of:` target** → the enum lists `query` as a legal scope, but the validation rule (Check 3) requires `snapshot_of:` to resolve to a UID in the Vault; a query is a string, not a UID. Until a query-target UID convention exists (v1.5+ candidate), use `scope: collection` and snapshot the materialized collection's UID instead. Trying to set `scope: query` with a query-string in `snapshot_of:` will fail at write-time.

### Worked examples

- **The ~60 v0.3-migration snapshots.** When [Board System Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md) locked, the existing `type: board` ledger entries migrated to `type: board-snapshot` per §9.1 of the design spec. They are the canonical historical examples — query the index for `type: board-snapshot` and read any one to see the produced shape (current ledger count: ~65 entries; the original "60" figure was the migration-time snapshot of the cohort).

### Go next

- **Pair capsule:** [board-definition.capsule (b0d1e4f2)](board-definition.capsule.md) — the template every snapshot points back at via `board_definition:`.
- **Creation skill:** [create-snapshot.skill (d847e2b3)](../skills/create-snapshot.skill.md).
- **Companion (current view, not historical):** [regenerate-board.skill](../skills/regenerate-board.skill.md).
- **Design spec:** [Board System Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md) §8 for the cold-boot reader rule (current vs historical query routing).
- **ADR alignment:** [ADR-035 Surface 2 (a7c4e5b2)](../../vault/files/a7c4e5b2.md) — the declared-presence rule that requires `snapshot_of:` and `board_definition:` to resolve at write-time.

---

## Relationship to `board-definition`

Every snapshot points at exactly one definition (`board_definition:`). The definition is the template that shaped the render. Definitions do not track their snapshots; the inverse edge emerges from the index (query: "all snapshots with `board_definition: <uid>`").

When a definition is superseded, existing snapshots retain their pointer to the superseded version. A superseded definition is not deleted; it is a historical template.

---

## Relationship to `project`

When `scope: project`, the snapshot's `snapshot_of` is the project UID. The project does NOT declare `snapshots:` as an array on its frontmatter — that would require re-writing the project every time a snapshot is created. The inverse edge emerges from the index.

---

## Inheritance

Extends `core`. Inherits all core rules. Adds the frontmatter constraints and validation checks declared above. Not currently extended by subtypes.

---

*board-snapshot Capsule Definition | v1.1 | argus-a38 | 2026-04-28 (Stream 3 D3.2 — §Studio + composes_with sibling); v1.0 lock 2026-04-20 by Argus A29 preserved in git history*
*Supersedes rendered-view half of [board (00ac0959)](board.capsule.md). Pairs with [board-definition (b0d1e4f2)](board-definition.capsule.md).*
*"The snapshot is what the world was. The regeneration is what the world is."*

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-04-20 | Initial lock. Supersedes the rendered-view half of board.capsule (00ac0959). Companion to board-definition.capsule (b0d1e4f2). Defines record-side of the board system per [Board System Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md). Migration: 60 existing `type: board` entries flip to `type: board-snapshot` per §9.1. | argus-a29 |
| 1.1 | 2026-04-28 | **Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop).** Added §Workshop — Shop Signage section (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next) per the v3 capsule shop-signage pattern proven at 20-capsule scale. Added `composes_with: b0d1e4f2` (sibling board-definition.capsule — definition templates the render; snapshot freezes one render in time). No semantic changes to §Required Frontmatter / §Body / §Validation Checks / §Governance Rules / §State Machine / §UID Generation. UID preserved at b5a7c391. | argus-a38 |
