---
spec_version: 2
tier: vault
folder_type: vault
maintained_by: vault-owner
owner: mike
write_access: [mike, metis, vela, argus, orpheus, silas, talos]
read_access: all
purpose: "The Tropo Vault — authoritative store of every governed work artifact in this vault"
governs: "vault/ and everything within it"
extraction_scope: ship
refs:
  - uid: null
    title: "Tropo Vault Phase 1 Specification"
    path: "vault/files/5eb5fd1f.md"
  - uid: 2d016ecf
    title: "Tropo Work Architecture Specification"
  - uid: ee225d4f
    title: "Capabilities Matrix Design Brief"
member_of:
  - "2d083137"   # tropo-work (v1.12 backfill 2026-05-08)
---

# vault/ — The Tropo Vault

*The flat, governed, authoritative store of every work artifact produced by this crew.*
*Read this file before writing anything to `vault/`.*

---

## What This Folder Is

The Vault is the single source of truth for governed work artifacts. Tasks, design specs, decisions, documents, board definitions, team definitions — everything the crew produces as governed work lives here.

The Vault is:

- **Flat.** All entries are stored in `files/` with no subfolder hierarchy. The filename is the entry's UID. Organization is through collections in `collections/`, not through folders.
- **Governed.** Every entry conforms to a capsule definition that specifies required frontmatter, a state machine, and validation rules. Entries that do not conform are not checked in.
- **Authoritative.** If an entry is not in the Vault's index, it does not exist in the Vault. The index is the truth.
- **Query-first.** The discovery interface is `00-index.jsonl`. Do not walk `files/` directly to find entries. Read the index.
- **Machine-first.** The Vault is optimized for reasoning agents to read and write. It is not optimized for human browsing. Humans use collections (`collections/`) to organize their view of the Vault.

The Vault is NOT:

- A traditional library of passive documents (that is `library/` — Orpheus's domain)
- A hierarchical file store
- A place for agent identity files, channels, governance infrastructure, or workspace scratch
- A publication channel (the book lives in `tab - the agentic builders/`)

---

## Before You Write

**Read the Phase 1 specification at [`vault/files/5eb5fd1f.md`](files/5eb5fd1f.md).** This file is the operational summary. The spec is the full design.

Confirm you understand:
- The four librarian functions (store, validate, retrieve, maintain)
- The check-in protocol below
- The locked vocabulary: vault, entries, index, collections

If any of this is unclear, read the spec before touching this folder.

---

## How to Find Entries (Retrieve)

1. **Read `00-index.jsonl`.** It contains one record per entry with UID, title, type, status, owner, and description.
2. **Scan the index for the field you care about** — UID, type, status, owner, or keywords in the description.
3. **Once you have a UID, open `files/<uid>.md`** to read the entry.
4. **If the index does not contain what you need, the entry does not exist in the Vault.** The index is authoritative.

**Do not navigate `files/` directly.** The filenames are UIDs, not names. Human-readable names live in the index, not in the filesystem. Walking `files/` will give you unintelligible UUIDs and wastes context.

---

## How to Store an Entry (Store + Validate)

The check-in protocol has five steps. Do not skip steps.

> **⚠ Direct-write bypass is a governance violation.** Editing `files/<uid>.md` directly without running the 5-step check-in protocol — even for "small" edits, even for "trivial" frontmatter changes, even for index hand-edits — is a governance violation. The protocol is the integrity boundary; bypassing it leaves the Vault in inconsistent states (file ≠ index, capsule rules unchecked, validation skipped, ownership unverified). If a change appears small enough to skip the protocol, it appears that way because the protocol's catches are silent on a clean diff — that is the protocol working, not overhead. **Run the 5 steps every time, or do not write to `files/`.** Drift caused by direct-write bypass is reported by the vault steward and traced back to the bypassing agent.

### Step 1 — Required frontmatter

Every entry MUST have:

| Field | Format | Notes |
|-------|--------|-------|
| `uid:` | 8-character hex | Generate a new one for new entries. Never reuse. |
| `title:` | Human-readable string | One line. ≤ 100 chars. |
| `type:` | Registered capsule type | See "Registered Types" below. |
| `status:` | Valid state for the type | See the type's state machine. |
| `owner:` | Agent or human identifier | Who owns this entry. ≤ 30 chars. |
| `created:` | ISO 8601 date | Date created. |
| `modified:` | ISO 8601 date | Date last modified. (Note: core capsule uses `last_modified` — errata task `03247039` will align. Use `modified` for now.) |
| `description:` | String | ≤ 120 chars. One-line summary. Required for index record. |
| `tags:` | Array of strings | Up to 10 tags. Required for index record. |
| `file_ext:` | String | Usually `md`. Required for index record. |
| `schema_version:` | Integer | Currently `1`. Required for index record. |

The capsule definition for the type may require additional fields (e.g., `priority:` for tasks, `version:` for design specs). Check the capsule definition for your type before writing.

### Step 2 — Validate against the capsule definition

Before writing anything to disk, verify:

- The UID is exactly 8 characters of hexadecimal.
- The type is a registered capsule type (see below).
- The status is valid for the type's state machine.
- The owner is a known agent or human.
- If updating an existing entry: your UID matches the existing file's UID.
- All required fields from the capsule definition are present.
- The state transition (if any) is valid per the state machine.

**If any validation fails, stop.** Do not place the file. Do not update the index. Return the validation error to whoever requested the check-in.

### Step 3 — Place the file

Write the entry to `files/<uid>.md`. The filename is the UID. No other naming scheme is permitted.

Example: an entry with `uid: a7e3d1f9` goes to `vault/files/a7e3d1f9.md`.

This is deliberate: the filesystem is a lookup table, not a navigation tree. Human-readable names are in the index, not in the filenames.

### Step 4 — Update the index atomically

Add or update the entry's record in `00-index.jsonl`. The index record must match the file's frontmatter.

**The index update is not optional.** An entry that exists in `files/` but is not in the index is invisible to the Vault. An index record that has no corresponding file is drift that the vault steward will flag.

Update index and place file in the same operation wherever possible. If the operations must be sequential, place the file first, then update the index — that way a failure leaves an orphaned file (recoverable) rather than an index pointer to nothing (harder to detect).

### Step 5 — Do not modify entries you do not own

If you need to change an entry owned by a different agent or human, do NOT modify it directly. Post the request to `channels/ops.md` and wait for the owner's approval. Ownership is declared in the entry's `owner:` field.

Renaming the `owner:` field IS an ownership transfer. Transfers require the prior owner's approval. Document the transfer in the entry's change history (a simple appended line in the body is sufficient for Phase 1).

---

## Registered Types (Tropo Work v3 — locked 2026-04-24, refreshed in this AGENTS.md 2026-04-28 by vela-v35 per Cosmo M1 drift finding)

The Vault ships with the following capsule types under [Tropo Work v3 (8b3f1d92)](files/8b3f1d92.md). Each has its own capsule definition in `.tropo/capsules/`. WorkItems carry `status:` (intrinsic lifecycle) and `state:` (archive visibility); `stage:` is dropped from the WorkItem class per v3 Decision 4.

| Type | Class | Capsule | Notes |
|------|-------|---------|-------|
| `note` | WorkItem | [`note.capsule`](../.tropo/capsules/note.capsule.md) | v3.1 — subsumes the deprecated `concept` primitive (D1). Lightweight capture; rewriteable. |
| `task` | WorkItem | [`task.capsule`](../.tropo/capsules/task.capsule.md) | v3.0 — request-lifecycle: `requested → accepted → active → verify → done` (+ `blocked`, `rejected`, `cancelled`). Owner ≠ verifier. |
| `design-brief` | WorkItem | [`design-brief.capsule`](../.tropo/capsules/design-brief.capsule.md) | v3.0 — informs a spec; not itself locked. |
| `arch-spec` | WorkItem | [`arch-spec.capsule`](../.tropo/capsules/arch-spec.capsule.md) | v2.0 — architectural lock; only the locking authority locks. |
| `design-spec` | WorkItem | [`design-spec.capsule`](../.tropo/capsules/design-spec.capsule.md) | v2.1 — design-side lock (e.g., release plans before they ship). v3.1-consistency-pass candidate. |
| `build` | WorkItem | [`build.capsule`](../.tropo/capsules/build.capsule.md) | v2.2 — versioned-package discipline; produces a release. |
| `release` | WorkItem | [`release.capsule`](../.tropo/capsules/release.capsule.md) | v3.0 — post-ship artifact; immutable. |
| `decision` | WorkItem | [`decision.capsule`](../.tropo/capsules/decision.capsule.md) | v3.1 — `status:` enum aligned with v3 (was `stage:` pre-v3; existing index entries may carry residual `stage:` until v1.4 Phase 7 migration). |
| `document` | WorkItem | [`document.capsule`](../.tropo/capsules/document.capsule.md) | v3.1 — pattern exemplar; `status: draft → published → archived`. Content-production pipelines terminate here per D11. |
| `collection-ref` | WorkItem | [`collection-ref.capsule`](../.tropo/capsules/collection-ref.capsule.md) | v3.0 — pointer to a collection file in `collections/`. |
| `project` | non-WorkItem | [`project.capsule`](../.tropo/capsules/project.capsule.md) | v2.3 — container; retains `stage:` lifecycle enum during v3.1 capsule-consistency carve-out. |
| `pipeline` | non-WorkItem | [`pipeline.capsule`](../.tropo/capsules/pipeline.capsule.md) | v2.0 — entity-authored protocol declaration; recursive WorkflowNode model. |
| `pipeline-run` | non-WorkItem | [`pipeline-run.capsule`](../.tropo/capsules/pipeline-run.capsule.md) | v2.1 — ephemeral execution instance with pinned `playbook_version`. |
| `entity` | foundation | [`entity.capsule`](../.tropo/capsules/entity.capsule.md) | v1.0 — Tropo Work v3 §2.3 D7 invariant: every WorkItem `member_of` an entity-owned project. |
| `agent` | foundation | [`agent.capsule`](../.tropo/capsules/agent.capsule.md) | v1.0 — registered crew/personal/worker/service identity. |
| `team` | foundation | [`team.capsule`](../.tropo/capsules/team.capsule.md) | v1.0 — multi-agent groupings; no cycles in `parent_teams`. |
| `vault` | foundation | [`vault.capsule`](../.tropo/capsules/vault.capsule.md) | v1.0 — vault-entity principal; owns top-level projects. |
| `concept` | DEPRECATED | [`concept.capsule`](../.tropo/capsules/concept.capsule.md) | Subsumed into `note` per v3 D1. Existing `type: concept` entries migrate at v1.4 Phase 7. Do not author new. |
| `board-def` | rendering | [`board-definition.capsule`](../.tropo/capsules/board-definition.capsule.md) | Board declarations; boards themselves are regenerated snapshots. |
| `board-snapshot` | rendering | [`board-snapshot.capsule`](../.tropo/capsules/board-snapshot.capsule.md) | Immutable point-in-time board capture. |
| `playbook` | governance | [`playbook.capsule`](../.tropo/capsules/playbook.capsule.md) | v2.1 — Group/milestone procedural declaration. |
| `playbook-run` | governance | [`playbook-run.capsule`](../.tropo/capsules/playbook-run.capsule.md) | v2.1 — execution instance of a playbook. |
| `project-plan` | governance | [`project-plan.capsule`](../.tropo/capsules/project-plan.capsule.md) | v1.1 — multi-stream coordinator. |
| `release-plan` | governance | [`release-plan.capsule`](../.tropo/capsules/release-plan.capsule.md) | v1.0 — release coordinator; v3.1-consistency-pass candidate. |
| `ship-artifact` | release | [`ship-artifact.capsule`](../.tropo/capsules/ship-artifact.capsule.md) | v1.1.4 — manifest entry per shippable folder/file (kind discriminator). |
| `subsystem-hub` | infrastructure | [`subsystem-hub.capsule`](../.tropo/capsules/subsystem-hub.capsule.md) | v1.2 — evergreen subsystem root (Library / Work / Agents / Playbooks / Rendering / Governance). |
| `action` | governance | [`action.capsule`](../.tropo/capsules/action.capsule.md) | v1.1 — atomic create-* operations governed by capsule. |
| `tool` | governance | [`tool.capsule`](../.tropo/capsules/tool.capsule.md) | v1.0 — registered scripts / harness extensions. |
| `how-to` | governance | [`how-to.capsule`](../.tropo/capsules/how-to.capsule.md) | v1.0 — procedural knowledge for humans + agents. |
| `session-agent` | governance | [`session-agent.capsule`](../.tropo/capsules/session-agent.capsule.md) | v1.2 — sa.* one-shot or live-channel. |
| `agent-configurator` | governance | [`agent-configurator.capsule`](../.tropo/capsules/agent-configurator.capsule.md) | v2.1 — thin-loader activation file. |
| `collection` | rendering | [`collection.capsule`](../.tropo/capsules/collection.capsule.md) | v1.0 — collection manifest body. v3.1-consistency-pass candidate. |
| `kb-article` | content | [`document.capsule`](../.tropo/capsules/document.capsule.md) | Knowledge base article (uses document.capsule with `pattern_family: document`). |

For the full schema of each type, see the corresponding capsule definition in `.tropo/capsules/`. The meta-spec (capsule-of-capsules) is [Vault Schema v2 — Architecture Specification (222873b9)](files/222873b9.md).

**Creating a new type** requires proposing a new capsule definition. This is a governed act — not every agent can create types. Propose the type to Mike or post to `channels/ops.md`. Do not silently invent a new type by writing an entry with an unrecognized `type:` value.

---

## How to Maintain the Vault

### Self-maintenance (every check-in)

Every check-in is responsible for maintaining consistency between the file placed in `files/` and the index record. The check-in agent:

1. Validates the entry before writing
2. Places the file atomically
3. Updates the index atomically
4. Refuses to leave the Vault in an inconsistent state

If a check-in fails mid-operation (e.g., file placed but index update failed), the check-in agent must either retry the index update immediately or remove the orphaned file. Do not leave the Vault in a half-committed state.

### Periodic maintenance (vault steward)

The vault steward runs periodic health checks against the Vault:

- **Index drift detection.** Files in `files/` without index records, or index records without files. Either is a fault.
- **UID uniqueness.** No two entries may share a UID. Collision is an emergency.
- **Capsule definition compliance.** Re-validate every entry against its current capsule definition. Flag drift caused by capsule definition version upgrades.
- **Orphan detection.** Entries referenced by collections or other entries that no longer exist in the Vault.
- **State machine compliance.** Flag entries in states not permitted by their type's state machine.
- **Size and scale.** Monitor the index size, file count, and query latency. Alert if the Vault approaches scale limits.

**The vault steward does NOT auto-repair vault issues.** It reports them to the vault owner and the affected entry owners. Auto-repair on governed work is out of scope for Phase 1 — every fix is a deliberate act.

---

## Deletion Discipline — Never Destroy; Always Soft-Delete (v1.40.0)

**You are reading this file because you are about to write or modify content in `vault/files/`.** The doctrine lives here at the point of action — impossible to miss.

**The rule:** every removal of an entry from `vault/files/<uid>.md` (or other governed substrate; see canonical scope table) goes through the canonical soft-delete gesture:

```
python3 .tropo/scripts/tropo-recycle.py <uid> [<uid> ...] --reason "<brief rationale>"
```

Never `rm`. Never `find ... -delete`. Never `git rm`. Never bypass for "obvious" cases (those are the cases that train future agents to bypass — which is how the v1.35.0 critical incident + the Talos T8 commit `7a8df68` 2026-05-17 incident both happened).

The discipline is the **process**, not the **outcome**. Process discipline holds regardless of approval, regardless of whether the file is archived / superseded / zombie / redirect-stub, regardless of whether content is recoverable from git history.

**Quick recovery** (if you need to undo a soft-delete):
```
mv recycle/agent-deletions/<YYYY-MM-DD>/<uid>.md vault/files/<uid>.md
npm run vault:rebuild
```

**Canonical doctrine** (full forbidden-operation list, scope table for all governed folders, full recovery procedures, three-incident history): [Deletion Discipline — Substrate Preservation Doctrine (0aefe71d)](files/0aefe71d.md). Read once; reference at every destructive operation. Doctrine also appears at OS-tier [`.tropo/SELF-HEALING.md`](../.tropo/SELF-HEALING.md) §Preservation Discipline + Studio-tier [`.tropo-studio/operating-principles.md`](../.tropo-studio/operating-principles.md) Principle 13 + memory-tier `.tropo-studio/memory/entries/839a65f9.md`.

---

## The Index Format

The index lives at `00-index.jsonl` in this folder. **The format is locked v1: JSONL (JSON Lines) — one JSON object per line, each object a complete self-describing record.**

Full schema reference: [`.tropo/schema/vault-index-schema.md`](../.tropo/schema/vault-index-schema.md)

**Quick reference:**

```json
{"uid":"<8-hex>","type":"<capsule-type>","status":"<state>","title":"<≤100 chars>","description":"<≤120 chars>","owner":"<≤30 chars>","created":"<YYYY-MM-DD>","modified":"<YYYY-MM-DD>","tags":["<tag>"],"file_ext":"<ext>","schema_version":1}
```

Each record fits on one line. Append new entries at the end of the file. Update existing entries by replacing the line in place. Schema validation is enforced at check-in (see Step 2 above).

**Common queries:**

- Lookup by UID: `grep '"uid": "a7e3d1f9"' 00-index.jsonl`
- All active tasks: `grep '"type": "task"' 00-index.jsonl | grep '"status": "active"'`
- Owned by Metis: `grep '"owner": "metis"' 00-index.jsonl`
- By tag: `grep '"architecture"' 00-index.jsonl | grep '"tags":'`

For complex queries, use `jq` or parse line-by-line in your language of choice.

---

## Scale Expectations

Phase 1 target: the Vault must remain performant at **2,000 entries** and should not degrade until at least **10,000 entries**. Index reads should return in under one second at this scale.

If you find yourself writing code or protocols that scale poorly (e.g., "rewrite the entire index on every check-in" at 10,000 entries is probably too expensive), flag it. Scale is a first-class concern for the Vault — we are not building this to replace it when it hits the first wall.

---

## What Does NOT Belong Here

The following are explicitly out of scope for the Vault:

| Not in the Vault | Lives in | Why |
|-------------------|----------|-----|
| Agent activation files, charters, status cards, transfers, briefings, reflections | `agents/` | Identity and lifecycle infrastructure — different owner and cadence |
| Channels and operational communication | `channels/` | Append-only conversation logs, not governed artifacts |
| Governance infrastructure — `STUDIO.md`, `TROPO-CONTROL.md`, `AGENTS.md`, `.tropo-studio/CAPSULE.md` | Various | The rules the Vault follows, not things the Vault contains |
| Workspace scratch, in-progress work, sub-agent output | `.tropo-capsule/workspace/` | Work that has not yet been checked in |
| Reference documentation and historical archives | `library/` | Passive, read-only material — Orpheus's domain |
| Business layer — founding charter, pitch materials | `tropo-business/` | May be migrated later; out of scope for Phase 1 |
| The book — chapters, drafts, primary source | `tab - the agentic builders/` | Separate publication channel |
| OS infrastructure — playbooks, skills, schemas, templates | `.tropo/`, `.tropo-studio/`, `.tropo-capsule/` | Shipped with the OS; not produced as governed work |
| Settings and environment | `settings/` | Configuration, not content |

**Test:** If it has a UID, a type, an owner, a state machine, and it is produced by the crew as governed work, it belongs in the Vault. If it is infrastructure, identity, or ephemera, it does not.

---

## Collections Are Elsewhere

Collections — the human-organized views of vault contents — live in `collections/` at the vault root, NOT inside the Vault. See the Phase 1 spec §7 for the collections format and protocol.

From the Vault's perspective, collections are consumers. They reference vault entries by UID. The Vault does not know or care how many collections reference a given entry, or how those collections organize their members. The Vault's job is to be the authoritative store; the collections folder's job is to be the human's organizational layer.

---

## Current State

This folder was created on April 10, 2026 by Metis G38 as part of the Phase 1 Vault build. It is currently empty of entries and the index is a placeholder.

The next generation (or G38 in bonus-round work) will:

1. Lock the index format (§5 of the Phase 1 spec)
2. Populate the Vault with initial entries from the existing `design/`, `tasks/`, and `decisions/` folders (migration Phase 1b)
3. Build the vault steward's vault audit functions
4. Ship the Vault into the starter vault as a Phase 1 primitive

Until then, treat this folder as the designated landing zone for governed work and follow the check-in protocol above.

---

## Refs

- **Phase 1 Specification:** [`vault/files/5eb5fd1f.md`](files/5eb5fd1f.md)
- **Tropo Work Architecture Spec:** [`design/tropo-work-architecture.md`](../design/tropo-work-architecture.md) (UID 2d016ecf)
- **Capabilities Matrix Brief:** [`design/tropo-capabilities-matrix-brief.md`](../design/tropo-capabilities-matrix-brief.md) (UID ee225d4f)
- **Folder CAPSULE.md:** [`.tropo-studio/CAPSULE.md`](.tropo-studio/CAPSULE.md) (UID b2296257)

---

*vault/AGENTS.md | The Librarian's Rules | Metis G38 + Mike Maziarz | April 10, 2026*
*"The Vault is the authoritative record. The index is the query interface. Files are files."*
