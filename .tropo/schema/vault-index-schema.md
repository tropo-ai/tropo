---
uid: null
title: "Tropo Vault Index — Schema Reference"
status: locked
type: schema-reference
tier: os
schema_version: 1
owner: metis
created: 2026-04-10
modified: 2026-04-12
refs:
 - path: "vault/files/5eb5fd1f.md"
 title: "Tropo Vault Phase 1 Specification"
---

# Tropo Vault Index — Schema Reference v1.1

*The authoritative schema for the vault index (`vault/00-index.jsonl`).*
*Locked v1 on April 10, 2026 by Metis G38 + Mike Maziarz.*
*v1.1 additive amendment on April 12, 2026 by Metis G40 + Mike Maziarz — five optional fields added: `scope`, `project`, `parent`, `created_by`, `path`. No breaking changes. `schema_version` stays at 1.*

---

## Overview

The vault index is a JSONL (JSON Lines) file. One JSON object per line. Each object is one entry record.

**Location:** `<vault-root>/vault/00-index.jsonl`

**Format:** JSONL — append-friendly, line-diffable, parser-ubiquitous.

**Scale commitment:** must remain performant at 2,000 entries and not degrade before 10,000 entries.

**Query strategy (Phase 1):** streaming scan. Read the index a line at a time, stop when the query is answered. Phase 2 may add auxiliary indexes (materialized views) maintained by a standing agent.

---

## Record Schema v1

Every record is a JSON object with the following fields, in this order:

```json
{
 "uid": "<8-char-hex>",
 "type": "<capsule-type>",
 "status": "<state>",
 "title": "<title-string>",
 "description": "<description-string>",
 "owner": "<owner-id>",
 "created": "<iso-date>",
 "modified": "<iso-date>",
 "tags": ["<tag>", "<tag>"],
 "file_ext": "<extension>",
 "schema_version": 1,
 "scope": "<ship or absent>",
 "project": "<uid or absent>",
 "parent": "<uid or absent>",
 "created_by": "<agent-id or absent>",
 "path": "<vault-relative path or absent>"
}
```

---

## Field Reference

### `uid` — required

- **Type:** string
- **Format:** exactly 8 characters, lowercase hexadecimal (`[0-9a-f]{8}`)
- **Constraints:** unique across the Vault, never reused, never changes
- **Purpose:** primary key; identifies the entry file at `vault/files/<uid>.md`
- **Example:** `"a7e3d1f9"`

### `type` — required

- **Type:** string, enum
- **Valid values (Phase 1):** `task`, `project`, `design-spec`, `design-brief`, `decision`, `document`, `collection-ref`, `board-def`, `team-def`
- **Valid values (post-Phase-1 additions):** `playbook-run` (Argus A23, April 14), `agent-configurator` (Argus A27, April 17), `release` (April 16), `release-plan` (locked Argus A28, April 19), `board` (April 12). The capsule definition files in [`.tropo/capsules/`](../capsules/00-index.md) are the authoritative list — this schema enum was not kept in lockstep during April 10–18 and was partially updated by Argus A28 on 2026-04-19 as part of the `release-plan` lock. Full reconciliation pass owed.
- **Constraints:** must match a registered capsule type
- **Purpose:** identifies the entry's capsule definition and state machine
- **Adding new types:** requires a capsule definition and Mike's approval, plus update of this schema
- **Example:** `"task"`

### `status` — required

- **Type:** string, enum (scoped by type)
- **Valid values per type:**

| Type | Valid statuses |
|------|----------------|
| `task` | `backlog`, `active`, `blocked`, `review`, `done`, `archived` |
| `project` | `proposed`, `active`, `paused`, `completed`, `archived` |
| `design-spec` | `draft`, `locked`, `superseded` |
| `design-brief` | `draft`, `reviewed`, `informing` |
| `decision` | `proposed`, `accepted`, `superseded` |
| `document` | `draft`, `published`, `archived` |
| `collection-ref` | `active`, `archived` |
| `board-def` | `active`, `archived` |
| `team-def` | `active`, `archived` |
| `release-plan` | **status field uses `stage` + `state` (Schema v2 shape)** — `stage:` ∈ {`design`, `specify`, `build`, `done`, `cancelled`}, `state:` ∈ {`active`, `archived`}. See [`release-plan.capsule.md`](../capsules/release-plan.capsule.md). |

**Schema fragmentation note (Argus A28, 2026-04-19):** The `release-plan` capsule (and the already-locked `release` and `design-brief` v2 capsules) use `stage` + `state` as the lifecycle fields, not the `status` field this table enforces. This is genuine schema drift — the Schema v2 shape is in production via multiple locked capsules, but this schema reference document still canonicalizes `status`. A separate ADR is owed to migrate the `core` capsule from `status:` to `stage:` + `state:` across all capsule types. Until that migration lands, readers should consult each capsule's own definition for the authoritative state field.

- **Constraints:** must be valid for the entry's `type`; state transitions must follow the type's state machine (defined in the capsule definition)
- **Purpose:** current lifecycle state of the entry
- **Example:** `"active"`

### `title` — required

- **Type:** string
- **Max length:** 100 characters
- **Constraints:** no newlines, no tab characters, no control characters
- **Purpose:** human-readable name for display in queries, boards, collection renderings
- **Rationale for limit:** titles longer than 100 chars are doing description work and should be rewritten
- **Example:** `"Lock Tropo Work Architecture Spec"`

### `description` — required

- **Type:** string
- **Max length:** 120 characters (hard limit)
- **Constraints:** no newlines, no tab characters, no control characters
- **Purpose:** one-line description of what the entry is about — scannable at a glance
- **Rationale for limit:** matches standard terminal width; forces brevity; longer explanations belong in the entry body
- **Enforcement:** check-in MUST reject entries with descriptions over 120 characters
- **Example:** `"Walk Mike through the spec section by section before Phase 2 design work begins"`

### `owner` — required

- **Type:** string
- **Max length:** 30 characters
- **Constraints:** must be a known agent or human identifier
- **Purpose:** who owns this entry and is responsible for its state transitions
- **Phase 1 values:** agent names (`metis`, `vela`, `argus`, `orpheus`, `silas`, `talos`) or human identifiers (`mike`)
- **Phase 2:** may become a tokenized identity (Ed25519 key fingerprint or similar)
- **Example:** `"metis"`

### `created` — required

- **Type:** string
- **Format:** ISO 8601 date (`YYYY-MM-DD`)
- **Constraints:** immutable after creation; never updated
- **Purpose:** when the entry first entered the Vault
- **Example:** `"2026-04-09"`

### `modified` — required

- **Type:** string
- **Format:** ISO 8601 date (`YYYY-MM-DD`)
- **Constraints:** updated at every check-in; must be >= `created`
- **Purpose:** when the entry was last updated
- **Queryability:** enables "what changed recently?" and "what hasn't been touched in 30 days?"
- **Example:** `"2026-04-10"`

### `tags` — required (may be empty array)

- **Type:** array of strings
- **Max length:** 10 tags per entry
- **Per-tag max length:** 30 characters
- **Constraints:** each tag is lowercase, hyphen-separated by convention (not enforced at schema level)
- **Purpose:** cross-cutting classification for queries
- **Empty is valid:** `"tags": []`
- **Priority convention:** use tags `p0`, `p1`, `p2`, `p3` for priority rather than a dedicated field
- **Example:** `["architecture", "phase-1", "p0"]`

### `file_ext` — required

- **Type:** string
- **Constraints:** file extension without leading dot; lowercase
- **Purpose:** identifies the file type of the entry in `vault/files/<uid>.<ext>`
- **Phase 1 default:** almost always `"md"` (markdown)
- **Future values:** may include `svg`, `csv`, `json`, etc. for non-markdown capsule types
- **Rationale:** future-proofs the index for non-markdown entries without requiring a schema change
- **Example:** `"md"`

### `schema_version` — required

- **Type:** integer
- **Current value:** `1`
- **Purpose:** records the schema version this entry was written under; enables future migrations
- **Increment policy:** increments only on breaking schema changes
- **Example:** `1`

### `scope` — optional (v1.1 additive, April 12, 2026)

- **Type:** string
- **Valid values:** `ship` (or absent)
- **Constraints:** if present, must be `ship`. Absent means the entry does not ship in the product release.
- **Purpose:** the release pipeline reads this field to determine what goes in the build. `grep '"scope":"ship"' 00-index.jsonl` returns every entry that ships.
- **fm alignment:** matches `scope:` in the entry's frontmatter. Same name, same value.
- **Example:** `"ship"` or absent

### `project` — optional (v1.1 additive, April 12, 2026)

- **Type:** string (UID)
- **Format:** 8-char hex UID of a `project`-type entry
- **Constraints:** if present, must reference a valid `project` entry in the Vault
- **Purpose:** "all tasks in project X" without opening every file. Board generation, project boot pattern, orphan-work detection.
- **fm alignment:** matches `project:` in the entry's frontmatter. Renamed from `parent_project:` (legacy name, to be swept).
- **Example:** `"6211b7b8"` or absent
- **Note:** reverses the v1 decision to exclude project from the index. The migration proved that project queryability outweighs index leanness.

### `parent` — optional (v1.1 additive, April 12, 2026)

- **Type:** string (UID)
- **Format:** 8-char hex UID of another vault entry
- **Constraints:** if present, must reference a valid entry in the Vault. No cycles (an entry cannot be its own ancestor).
- **Purpose:** task decomposition — "all subtasks of task X." Sub-project hierarchy. Parent-child relationships queryable without file reads.
- **fm alignment:** matches `parent:` in the entry's frontmatter.
- **Example:** `"dd98e990"` or absent

### `created_by` — optional (v1.1 additive, April 12, 2026)

- **Type:** string
- **Max length:** 30 characters
- **Constraints:** agent-id or human identifier of the original creator
- **Purpose:** generation lineage — "what did G39 produce?" Cross-generation queries. Audit trail for who created what.
- **fm alignment:** matches `created_by:` in the entry's frontmatter.
- **Example:** `"metis-g39"` or absent

### `path` — optional (v1.1 additive, April 12, 2026)

- **Type:** string
- **Format:** vault-relative path to the file (e.g., `.tropo/capsules/core.capsule.md`)
- **Constraints:** if present, the file MUST exist at this path. If absent, the file lives at the default location `vault/files/<uid>.md`.
- **Purpose:** allows vault registration of files that live outside `vault/files/` — kernel files in `.tropo/`, agent charters in `agents/`, governance files at root. The Vault becomes a universal registry without requiring files to move.
- **Build pipeline usage:** the build script resolves each entry's location as `path` if present, else `vault/files/<uid>.md`. One mechanism for all entries regardless of where they live on disk.
- **fm alignment:** matches `path:` in the entry's frontmatter (optional — only present on entries that don't live in `vault/files/`).
- **Example:** `".tropo/capsules/core.capsule.md"` or absent

---

## Fields Explicitly NOT in the Index

These fields exist in entry files but are NOT in the index, to keep records lean:

| Field | Lives in | Why not in index |
|-------|----------|------------------|
| `refs` | entry fm | Traversal happens by reading the referenced file |
| `priority` | `tags` as `p0`/`p1`/`p2`/`p3` | Using tags avoids a per-type-conditional field |
| `verifier` | entry fm | Only meaningful for tasks; stored in the entry |
| `blocks`, `blocked_by` | entry fm | Too structured for the index; derive from entry body |
| `assigned` | entry fm | Convention not yet locked; add when stabilized |
| `due` | entry fm | Time-based queries not yet in use; add when needed |
| Change history | entry body | Never in the index |
| Body content | entry body | Never in the index |

---

## Record Ordering

Records in the index are **append-ordered by check-in time**. Newly checked-in entries go at the end of the file. This makes append operations O(1) and preserves a chronological audit trail of when entries entered the Vault.

When an entry is updated, the corresponding record is updated **in place** — the line is replaced, the record stays in its original position. This preserves append-order for new entries while allowing updates to existing records.

**Exception:** when the index is rebuilt from scratch (e.g., by the vault steward after detecting corruption), records should be sorted by `created` ascending. This is idempotent and recoverable.

---

## Character Encoding

The index is UTF-8. Non-ASCII characters are permitted in `title`, `description`, and `tags`. The 100 / 120 / 30 character limits apply to Unicode code points, not bytes.

---

## Validation at Check-In

The check-in protocol (see `vault/AGENTS.md`) must validate the following against this schema before writing the record:

1. `uid` matches `^[0-9a-f]{8}$`
2. `type` is in the enum of registered capsule types
3. `status` is valid for the entry's `type`
4. `title` length ≤ 100 characters, no newlines/tabs/control chars
5. `description` length ≤ 120 characters, no newlines/tabs/control chars
6. `owner` is a known identifier, length ≤ 30 characters
7. `created` and `modified` are valid ISO 8601 dates
8. `modified` >= `created`
9. `tags` is an array, length ≤ 10, each tag ≤ 30 characters
10. `file_ext` is a lowercase string, no leading dot
11. `schema_version` equals the current schema version (1)
12. The JSON object is valid JSON (parseable by any standard parser)
13. The entire record fits on a single line (no embedded newlines)

If any validation fails, the check-in is refused and no change is made to `files/` or the index.

---

## Query Patterns

Common queries and how to execute them against a JSONL index:

### Lookup by UID

Scan until you find the matching UID, then stop.

```
grep '"uid":"a7e3d1f9"' 00-index.jsonl
```

Or programmatically: read line by line, parse each as JSON, check `uid` field.

### Filter by type

```
grep '"type":"task"' 00-index.jsonl
```

### Filter by status

```
grep '"status":"active"' 00-index.jsonl
```

### Filter by owner

```
grep '"owner":"metis"' 00-index.jsonl
```

### Filter by tag

```
grep '"architecture"' 00-index.jsonl | grep '"tags":'
```

(The double filter is because tag values could theoretically appear in other fields like title or description. For strict queries, parse the JSON and check the `tags` array.)

### Complex filters (multiple criteria)

Use `jq` or read and parse programmatically:

```
jq -c 'select(.type == "task" and.status == "active" and.owner == "metis")' 00-index.jsonl
```

### Full index scan

Read every line, parse every record. Phase 1 supports this at 2,000-entry scale. Beyond 10,000 entries, use auxiliary indexes (see Phase 2 roadmap).

---

## Schema Evolution

### Additive changes (no version bump)

Adding optional fields that older agents can ignore does NOT require a schema version bump. Example: adding a `verifier` field to task records is additive — older agents reading the record simply ignore the new field.

### Breaking changes (version bump required)

The following require incrementing `schema_version`:

- Removing a field
- Renaming a field
- Changing a field's type (e.g., string to integer)
- Changing a field's semantics
- Changing an enum's allowed values (removal) or requiring new values
- Changing a validation constraint in a stricter direction

When `schema_version` is bumped to 2:

1. A migration playbook is written that reads v1 records and produces v2 records
2. The Vault is migrated once via the update pipeline
3. The schema reference document is updated to describe both v1 and v2
4. Agents check the `schema_version` field before parsing and use the appropriate logic

### Deprecation policy

Fields are deprecated for at least one minor version before removal. A deprecated field is marked in this reference document but still written by check-ins until removal.

---

## Example Records

```jsonl
{"uid":"a7e3d1f9","type":"task","status":"active","title":"Lock Tropo Work Architecture Spec","description":"Walk Mike through the spec section by section before Phase 2 design work begins","owner":"metis","created":"2026-04-09","modified":"2026-04-10","tags":["architecture","phase-1","p0"],"file_ext":"md","schema_version":1}
{"uid":"2d016ecf","type":"design-spec","status":"draft","title":"Tropo Work Architecture Specification","description":"Five-object model, librarian, check-out/check-in lifecycle, capsule inheritance","owner":"metis","created":"2026-04-09","modified":"2026-04-09","tags":["architecture","spec"],"file_ext":"md","schema_version":1}
{"uid":"ee225d4f","type":"design-brief","status":"draft","title":"Tropo Capabilities Matrix Design Brief","description":"L1/L2/L3 framework for classifying Tropo capabilities by enforcement mechanism","owner":"metis","created":"2026-04-10","modified":"2026-04-10","tags":["capabilities","framework"],"file_ext":"md","schema_version":1}
{"uid":"1693e7f2","type":"task","status":"active","title":"Design and build the Tropo release pipeline","description":"CI/CD analog for shipping Tropo versions — spec, playbook, role, first real test","owner":"vela","created":"2026-04-10","modified":"2026-04-10","tags":["release","operations","p1"],"file_ext":"md","schema_version":1}
{"uid":"10fd68f5","type":"task","status":"active","title":"Build the Tropo Capabilities Matrix from locked brief","description":"Inventory Tropo capabilities, classify L1/L2/L3, produce the matrix and v1.0 scope","owner":"metis-g39","created":"2026-04-10","modified":"2026-04-10","tags":["capabilities","matrix","p1"],"file_ext":"md","schema_version":1}
```

Five records. About 1.6 KB. Readable, parseable, diff-friendly.

---

## Rationale Summary

**Why JSONL:** line-oriented (append and diff friendly), self-describing (every record carries field names), parser-ubiquitous (every language and every LLM handles JSON natively), schema-evolution friendly (additive changes don't break old readers).

**Why fixed field order:** token efficiency for agents scanning the index; predictable parsing; easier visual diffing.

**Why hard character limits:** predictable record sizes, forced brevity, scale safety.

**Why tags instead of a priority field:** priority is only meaningful for tasks; tags generalize across types; avoids optional fields.

**Why `file_ext` in the schema:** future-proofs the index for non-markdown entry types without requiring a schema version bump when the first non-markdown type ships.

**Why `schema_version` in every record:** future migrations need to know what they're migrating from. Per-record versioning lets the Vault contain records from multiple schema versions during a rolling migration.

---

## Refs

- **Phase 1 Specification:** `vault/files/5eb5fd1f.md` — see §5 for the locked format decision
- **Vault AGENTS.md:** `vault/AGENTS.md` — the check-in protocol that enforces this schema
- **Vault CAPSULE.md:** `vault/CAPSULE.md` — folder governance metadata

---

*Vault Index Schema v1.1 | Locked | Metis G38 + G40 + Mike Maziarz | April 10 + 12, 2026*
*"One record per line. One truth per record. The index is the interface."*
