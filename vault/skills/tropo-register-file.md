---
skill: register-file
name: register-file
type: how-to
purpose: 'Register a new file in the vault — UID, frontmatter, matched-primitive index projection, folder index, ops log. Plus: sync `projects/<slug>/` filesystem with vault entries across the create/move/rename/delete lifecycle (v1.4 D2.2).'
when: After creating any file with YAML frontmatter; OR when a file in `projects/<slug>/` is created, moved, renamed, or removed
uid: a1b2c3d4
status: active
owner: argus
created: 2026-04-15
created_by: argus
version: '1.1'
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: 'Reach for this whenever you create a new vault file with YAML frontmatter, OR when a file in projects/<slug>/ is created/moved/renamed/removed. Generates the UID, ensures required frontmatter fields, projects the entry into the right index per matched-primitives topology (vault/files/<uid>.md → vault/00-index.jsonl via rebuild-vault.py), updates folder 00-index.md, and posts to ops.md when material. Plus: keeps projects/<slug>/ filesystem in sync with vault entries across the file lifecycle (v1.4 D2.2 amendment).'
subsystem_hub:
  - 8dd772a0
---

# Register a File

Use this whenever you create a new file that has YAML frontmatter. Per matched-primitives topology ([adac1f10](../../vault/files/adac1f10.md)), the index that owns the UID depends on the file's domain.

## Steps

1. **Generate a UID.** Run `openssl rand -hex 4` or generate 8 random lowercase hex characters. Example: `a3f2b918`.

2. **Add the UID to frontmatter.** Insert `uid: a3f2b918` in the file's YAML frontmatter block (between the `---` delimiters). Include `type:`, `title:`, `status:` (per the file's capsule), `created:`, and `created_by:`.

3. **The rebuilder projects the file into the right index.** Per matched-primitives:
 - **Ledger entries** (governed work artifacts at `vault/files/<uid>.md`) → projected into `vault/00-index.jsonl` by `vault/tools/tropo-rebuild-vault.py` on `python3 vault/tools/tropo-rebuild-vault.py --apply`.
 - **Runtime callables** (sa.\*/skills/tools) → projected into `.tropo-studio/registries/registry.jsonl` by `scripts/rebuild-registry.ts`.
 - **Agent identity** (executive activations, charters) → manually update `.tropo-studio/registries/agent-registry.yaml` with the agent's UID, class, path, and identity.
 - **Kernel content** (capsules, kernel playbooks, kernel skills) → discoverable via folder listing — filename IS the address. No separate index step.

4. **Update the folder index.** Open `00-index.md` in the same folder and add a row:
 ```
 | <filename> | <type> | <status> | <one-line description> |
 ```

5. **Log to ops.** Append one line to `channels/ops.md`:
 ```
 [YYYY-MM-DD HH:MM] <your-agent-id> — Created <path-to-file>. UID: <uid>.
 ```

## Success

The file has a `uid:` in frontmatter, the appropriate matched-primitive index reflects it (after rebuild for ledger/runtime; after manual update for agent identity; immediate for folder-listed kernel content), it is listed in the folder's `00-index.md`, and the creation is logged in `channels/ops.md`.

---

## Project-File Sync Protocol (v1.4 D2.2)

*When a file inside `projects/<slug>/` is created, moved, renamed, or removed, both the filesystem AND the Vault must agree on the file's identity. The Vault holds the canonical record (UID, frontmatter, relationships); the filesystem holds the navigable surface. This section governs the four lifecycle events that keep them in sync.*

*Per [v1.4 Stream 2 §D2.2 (d9f3b8c1)](../../vault/files/d9f3b8c1.md) — "syncs files in projects/<slug>/ with ledger entries." Handles create / move / rename / delete lifecycle. Idempotent; safe to re-run.*

### Create — A new file lands in `projects/<slug>/`

Standard `## Steps` above apply. Plus:

- The vault entry MUST declare `member_of:` containing the project's UID — that's what makes it a "project file" rather than a vault-root orphan.
- If the file is created at `projects/<slug>/<filename>.md` BEFORE the ledger entry exists, treat as a vault-root file pending registration: assign UID, author the ledger entry at `vault/files/<uid>.md`, set `member_of: [<project-uid>]`, then log via §Steps step 5.
- Update the project's `projects/<slug>/00-index.md` (per [D2.3 00-index auto-maintenance](../../vault/files/d9f3b8c1.md)) — list the new file with type and one-line description.

### Move — File goes from `projects/<slug-A>/` to `projects/<slug-B>/`

A move means the file's organizational home changed; its identity (UID) did not.

1. **Read the file's frontmatter.** Capture `uid:` + current `member_of:`.
2. **Update `member_of:`.** Remove the old project's UID; add the new project's UID. Preserve all other `member_of:` entries. (Files can belong to multiple projects per Principle 2.4.)
3. **Move the file** on the filesystem from `projects/<slug-A>/<filename>.md` to `projects/<slug-B>/<filename>.md`. The file's `<uid>.md` ledger entry stays at `vault/files/<uid>.md` — the LEDGER path doesn't change.
4. **Run `python3 vault/tools/tropo-rebuild-vault.py --apply`** so `00-index.jsonl` reflects the updated `member_of:`.
5. **Update both projects' 00-index.md** — remove from old project, add to new.
6. **Log to ops.md:**
   ```
   [YYYY-MM-DD HH:MM] <your-agent-id> — Moved <filename> from <slug-A>/ to <slug-B>/. UID: <uid>.
   ```

**Idempotency:** if the file is already at the target location with correct `member_of:`, this is a noop. Reading frontmatter pre-write makes the protocol safe to re-run.

### Rename — File changes name within `projects/<slug>/`

The UID is the canonical identifier per [STUDIO.md §Cross-References](../../STUDIO.md): "Reference files by UID, not path. UIDs survive renames and moves." Renames update the filesystem; the vault entry's UID and content stay.

1. **Read the file's frontmatter** — capture UID and current title.
2. **Update `title:`** in frontmatter to match the new intent. Title-rename is the semantic change; filesystem-rename is the surface.
3. **Rename the file** on the filesystem: `projects/<slug>/<old-name>.md` → `projects/<slug>/<new-name>.md`. The `<uid>.md` vault entry stays.
4. **Run `python3 vault/tools/tropo-rebuild-vault.py --apply`** so the index reflects the new title.
5. **Update `projects/<slug>/00-index.md`** — replace the old filename row with the new.
6. **Log to ops.md:**
   ```
   [YYYY-MM-DD HH:MM] <your-agent-id> — Renamed <old-name> → <new-name> in <slug>/. UID: <uid>.
   ```

**The UID is immutable across renames.** Cross-references in other vault entries (via `refs:`, `member_of:`, `composes_into:`) continue to resolve unchanged. This is the architectural payoff of UID-addressing.

**Idempotency:** if the filename and title already match the target, noop.

### Delete — File is removed from `projects/<slug>/`

**Per [STUDIO.md §Vault Constraints](../../STUDIO.md): archive instead of delete.** Files are NOT removed from the Vault; they transition to `state: archived`.

1. **Read the file's frontmatter** — capture UID, current state, current member_of.
2. **Set `state: archived`** in frontmatter. If a single-clean-successor exists, also set `superseded_by: <successor-uid>` per the V35 supersession-on-archive discipline (see [STUDIO.md](../../STUDIO.md)).
3. **Move the file** on the filesystem from `projects/<slug>/<filename>.md` to `projects/<slug>/99-archive/<filename>.md` (per the numerical-prefix navigation convention — `99-` for archive). If `99-archive/` doesn't exist, create it.
4. **Run `python3 vault/tools/tropo-rebuild-vault.py --apply`** so the index reflects `state: archived`.
5. **Update `projects/<slug>/00-index.md`** — move the file's row to the §Archived section (or remove if the project's 00-index policy doesn't track archived).
6. **Log to ops.md:**
   ```
   [YYYY-MM-DD HH:MM] <your-agent-id> — Archived <filename> in <slug>/. UID: <uid>. [superseded_by: <uid> | reason: <one-line>]
   ```

**The ledger entry stays at `vault/files/<uid>.md`.** It is now `state: archived` — readable, refer-able, but not in active views. Hard-delete is a separate destructive operation requiring explicit human authorization per STUDIO.md §Constraints.

**Idempotency:** if `state: archived` is already set and the file is already in `99-archive/`, noop.

---

## Idempotency Summary

All four lifecycle protocols are **safe to re-run**. Each step's pre-condition is checked before action:

- **Create** — skip if UID already in frontmatter and vault entry exists
- **Move** — skip if already at target with correct `member_of:`
- **Rename** — skip if filename and title already match target
- **Delete** — skip if `state: archived` already set and file in `99-archive/`

This makes the skill safe to invoke during recovery passes, audit sweeps, or batch-organize sessions. The skill describes the protocol; executors (agent or human or future automation script) verify the pre-condition before mutating.

---

## Cross-References

- [STUDIO.md](../../STUDIO.md) — `archive-instead-of-delete`, `cross-references-by-UID`, `numerical-prefix-navigation` conventions
- [project.capsule v2.3 (34e4cb0b)](../capsules/project.capsule.md) — projects-as-static-organizational-containers; `member_of:` declared by member
- [v1.4 Stream 2 (d9f3b8c1)](../../vault/files/d9f3b8c1.md) §D2.2 — skill spec
- [view-by-owner.py](../scripts/view/view-by-owner.py) + [view-by-status.py](../scripts/view/view-by-status.py) — D2.4 view scripts that render projects/<slug>/ files projected by ownership and status

---

*register-file skill v1.1 | Vela V36 | 2026-04-28 — D2.2 project-file sync lifecycle added*
*"Filesystem and ledger agree. UID is the canonical identifier. Archive, don't delete."*
