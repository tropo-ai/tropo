---
skill: create-snapshot
name: create-snapshot
type: how-to
purpose: Create an explicit board-snapshot — a frozen vault entry capturing a rendered board at a specific point in time
when: Release ship, stage close, pre-change checkpoint, or any moment whose state deserves preservation. NOT on every board render — regeneration is ephemeral.
mode: both
params:
  - scope_ref_uid
  - board_definition_uid
  - reason
uid: d847e2b3
status: active
owner: argus
created: 2026-04-20
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
how_to_capsule_governed_by: a7c3f489
board_snapshot_governed_by: b5a7c391
aligned_with: 74fd9b61
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: 'Reach for this when a moment deserves a permanent record — release ship, stage close, pre-change baseline, or any state worth preserving. Renders the board against live ledger sources at the moment of call and writes a frozen vault entry (type: board-snapshot) with the rendered markdown + provenance + reason. Distinct from regenerate-board.skill.md which is ephemeral. Examples: snapshot at release ship (''the world at v1.X.Y ship''), at stage close (''the spec at lock''), or before a major restructure (''pre-change baseline'').'
subsystem_hub:
  - 76bab75f
---

# Create a Board Snapshot

Use this skill when a moment deserves a permanent record — the state of a project the day a release shipped, the shape of a board when a stage closed, the pre-change baseline before a major rework. Do NOT use this for routine board regeneration — that's ephemeral, returned in the agent's response, not written to the Vault.

## When to Call This Skill

**Call create-snapshot when:**
- A release just shipped and the board state is the "this was the world at ship" record.
- A pipeline stage just closed and the board is the historical truth of that stage.
- Before a significant change (restructure, migration, spec revision), capturing the pre-change baseline.
- A human or agent explicitly asks for a snapshot (e.g., "give me a historical checkpoint of project X").

**Do NOT call create-snapshot for:**
- Routine status checks ("what does project X look like right now?") — regenerate ephemerally.
- Board refreshes triggered by stale timestamps — not a moment-that-matters.
- Every render (would flood the Vault with low-signal entries).

## Inputs

| Param | Type | Required | Semantics |
|-------|------|----------|-----------|
| `scope_ref_uid` | UID | required | The project / team / collection being snapshotted. Must resolve in the Vault. |
| `board_definition_uid` | UID | required | The `board-definition` that produces the render. Must resolve in the Vault with `type: board-definition`. |
| `reason` | string | required | Free prose — why this moment matters. Non-empty. |

## Steps

1. **Verify inputs per [ADR-035 Surface 2](../../vault/files/a7c4e5b2.md).**
 - Grep [vault/00-index.jsonl](../../vault/00-index.jsonl) for `scope_ref_uid`. If it does not resolve: HALT fail-loud, emit error naming the unresolved UID.
 - Grep for `board_definition_uid`. Confirm it resolves AND has `type: board-definition` AND `status: active`. Fail-loud on any miss.
 - Confirm `reason` is non-empty. If empty: HALT.

2. **Resolve the scope of the definition.** Read the board-definition's `scope:` field. Confirm it matches the scope-type of `scope_ref_uid` (e.g., if definition has `scope: project`, `scope_ref_uid` must be a `type: project` entry). Mismatch is a fail-loud halt.

3. **Render the board against live sources.** Execute each section query in the definition's `sections:` array against the current ledger state. Use the render formats locked in [v0.3 §7.2.1](../../vault/files/74fd9b61.md) — table, list, list-with-links, tree, or null-result — per each section's `render:` field. Assemble the rendered markdown in section order.

4. **Generate the snapshot UID.** Call the core UID primitive (8-hex random). Verify the UID is not already in [00-index.jsonl](../../vault/00-index.jsonl); if collision, regenerate. In the Argo vault, the primitive is `scripts/generate-uid` or equivalent; for cold-run environments, any 8-hex random that passes uniqueness check works.

5. **Write the snapshot ledger entry** at `vault/files/<uid>.md` with this frontmatter:

```yaml
---
uid: <generated-uid>
type: board-snapshot
snapshot_of: <scope_ref_uid>
board_definition: <board_definition_uid>
taken_at: <ISO 8601 minute-precision, vault-local>
taken_by: <agent-id or human-name>
reason: <reason string from input>
scope: <mirror from definition>
scope_ref: <scope_ref_uid>
state: active
created: <YYYY-MM-DD>
created_by: <agent-id>
schema_version: 2
---
```

 Followed by the rendered markdown from step 3 as the body.

6. **Run `python3 vault/tools/tropo-rebuild-vault.py --apply`** to propagate the new snapshot into the vault index. The snapshot is queryable via `type: board-snapshot` and `snapshot_of: <scope_ref_uid>` after rebuild.

7. **Return the snapshot UID** to the caller. Do NOT automatically post to channels or emit notifications unless explicitly asked — snapshots are permanent records, not announcements.

## Failure Handling

- **ADR-035 Surface 2 violation** (unresolved input UID): HALT fail-loud. Do not write a defective snapshot. Surface the error to the caller.
- **Scope mismatch** (definition scope does not fit scope_ref_uid's type): HALT. The rendering would produce meaningless output.
- **Query-vocabulary violation** (definition uses a section query outside [v0.3 §7.2 vocabulary](../../vault/files/74fd9b61.md)): HALT. A defective definition cannot produce a valid snapshot.
- **UID collision after 3 regeneration attempts**: HALT — this would indicate a broken UID primitive, not a collision; investigate the primitive.

## Cold-Boot Notes

A stranger agent calling this skill must have: (a) the three input params, (b) read access to the Vault, (c) ability to execute the render engine (which uses v0.3 §7.2 vocabulary). Nothing else in context is required. The skill is self-contained given the inputs.

---

*create-snapshot | Skill v1.0 | Argus A29 | 2026-04-20*
*"Snapshots are moments that deserve preservation. Make them deliberately."*
