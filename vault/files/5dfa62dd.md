---
uid: 5dfa62dd
type: decision
status: done
state: active
title: ADR-034 — collection-ref is the canonical collection pattern
description: Resolves the collection-ref vs direct collection ambiguity. collection-ref is canonical. Direct collections are deprecated.
owner: argus
created: 2026-04-14
modified: 2026-04-16
member_of: []
tags:
- adr-034
- collection
- ledger
- schema
- v0.4
file_ext: md
schema_version: 2
extraction_scope: ship
decision_number: ADR-034
proposer: Argus A23
created_by: argus-a23
locked_by: argus-a23
locked_at: 2026-04-14
subsystem_hub:
- 8dd772a0
capsule_version: '2.5'
---

# ADR-034 — collection-ref is the canonical collection pattern

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Governance](8dd772a0.md) → **ADR-034 — collection-ref is the canonical collection pattern**

**🔗 This file** — UID `5dfa62dd` · type `decision` · state `active` · status `done`

**📥 Cited by (1):**
- [Duplicate ADR-034 entries in ledger](b4d1c283.md) — `b4d1c283` (type `task`, via `refs`)
<!-- nav-block:end -->

## Status

**LOCKED.** Argus A23, April 14, 2026.

---

## Context

Two patterns exist in the vault for collections:

**Pattern A — `collection-ref` (used by create-project v2.3+):**
- Vault entry: `type: collection-ref`, contains `collection_path:` pointing to manifest
- Manifest: `collections/projects/<slug>/all.collection.md` — holds the actual member list
- Two files, two purposes: vault entry = governed registration, manifest = member roster

**Pattern B — Direct collection (used by some pre-v2.3 collections):**
- Vault entry: `type: collection`, members listed inline in the file body
- One file, two purposes: vault entry IS the collection

Both patterns existed. Agents querying collections got inconsistent results. The `create-project` action (v2.3+) already used collection-ref. Older collections used direct.

---

## Decision

**`collection-ref` is the canonical collection pattern. Direct collections are deprecated.**

### Why collection-ref

**Separation of concerns.** The vault entry is the governed registration — it has a UID, a state machine, validation checks. The manifest is the content — a member list that can be freely reorganized, re-ordered, annotated. These are different concerns and should not live in the same file.

**Free content evolution.** Reorganizing a collection's members should not require touching ledger governance. With collection-ref, you edit the manifest. The vault entry is untouched. With direct, any member change is a ledger check-in.

**Consistency with the projects-as-nodes model.** The vault entry is the node. The manifest is the edge list. These are structurally distinct. The `collection_path:` field is the pointer from node to edge list — same pattern as `path:` for kernel entries.

**Already canonical in practice.** Every collection created by create-project v2.3+ uses collection-ref. The direct pattern only exists in pre-v2.3 collections.

### What changes

1. **New collections:** always use `collection-ref` + manifest. Never `type: collection` in the Vault.
2. **Capsule definitions:** `collection-ref.capsule.md` is the governed type. A `collection.capsule.md` for direct collections will be deprecated.
3. **Queries:** agents querying for collections filter `"type": "collection-ref"` in the index, then follow `collection_path:` to read members.
4. **Migration:** existing direct collections (`type: collection` in ledger) should be migrated to collection-ref pattern. Migration is a separate task — this ADR does not require immediate migration of existing entries.

### Standard collection-ref structure

```
vault/files/<uid>.md ← type: collection-ref, collection_path: <path>
collections/<context>/<slug>/ ← manifest files live here
 all.collection.md ← primary collection manifest
 tasks.collection.md ← tasks-only collection manifest
```

---

## Consequences

**What becomes easier:**
- Consistent collection queries — always `type: collection-ref`, always follow `collection_path:`
- Members can be reorganized without ledger governance overhead
- The `create-project` action is already correct — no changes needed

**What requires follow-up:**
- Migration of direct `type: collection` entries to collection-ref pattern (separate task)
- Deprecation notice in `collection.capsule.md`
- Update ledger query documentation to reference `type: collection-ref`

---

*ADR-034 | LOCKED | Argus A23 | April 14, 2026*
*Resolves: task 32b7692d — collection-ref vs direct collection type in ledger*
