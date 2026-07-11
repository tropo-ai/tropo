---
skill: regenerate-board
name: regenerate-board
type: how-to
purpose: Regenerate a board ephemerally from a board-definition — render live sources, return markdown, write nothing
when: Any time an agent or human needs the current state of a project's status board. NOT for historical preservation (use create-snapshot.skill.md).
mode: both
params:
  - scope_ref_uid
  - board_definition_uid
uid: 6c4a8f12
status: active
owner: argus
created: 2026-04-20
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
board_definition_governed_by: b0d1e4f2
aligned_with: 74fd9b61
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
supersedes_version: pre-v0.3 (legacy-folder-based)
trigger_description: Reach for this when an agent or human needs the CURRENT state of a project's status board. Renders the requested board-definition's sections against live ledger sources and returns the markdown. Writes nothing to disk — fully ephemeral. For historical preservation (snapshot a moment that matters), use create-snapshot.skill.md (UID d847e2b3) instead. The pre-v0.3 version operated on legacy boards/<slug>/ folders and wrote current.md files; that folder is retired and this skill now operates entirely at the ledger layer.
subsystem_hub:
  - dbc1cbbf
---

# Regenerate a Board

Use this when an agent or human needs the **current** state of a project's status board. Renders the requested `board-definition`'s sections against live ledger sources and returns the rendered markdown. **Writes nothing to disk.**

For historical preservation (snapshot a moment that matters), use [create-snapshot.skill.md (d847e2b3)](create-snapshot.skill.md) instead.

## v0.3 alignment note

This skill was rewritten for [Board Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md). The pre-v0.3 version operated on the legacy `boards/<slug>/` folder layout, archived prior versions, and wrote `current.md` files. That folder is retired; this skill now operates entirely at the ledger layer and produces ephemeral output.

## Inputs

| Param | Type | Required | Semantics |
|-------|------|----------|-----------|
| `scope_ref_uid` | UID | required | The project / team / collection to render. Must resolve in the Vault. |
| `board_definition_uid` | UID | optional | The `board-definition` to use. If omitted, the skill resolves the kernel `project-board` default via the §6.2 triple lookup. |

## Steps

1. **Validate inputs per [ADR-035 Surface 2](../../vault/files/a7c4e5b2.md).** Grep [vault/00-index.jsonl](../../vault/00-index.jsonl) for `scope_ref_uid` — must resolve with a valid type. If unresolvable: HALT fail-loud.

2. **Resolve the board-definition.**
 - If `board_definition_uid` was provided: verify it resolves with `type: board-definition` and `status: active`. Fail-loud on any miss.
 - If omitted AND `scope_ref_uid` is a project: check the project's frontmatter for `status_board:`. If declared and resolves, use it. If declared but does NOT resolve: HALT fail-loud (do not fall back to the default — that would mask a broken declaration).
 - If still unresolved: look up the kernel default via `grep '"name":"project-board"' vault/00-index.jsonl | grep '"type":"board-definition"' | grep '"default_for":"project"'`. Expect exactly one result. Zero → HALT fail-loud (vault needs the [apply-update playbook (`.tropo/playbooks/apply-update.playbook.md`)](../playbooks/apply-update.playbook.md) to run). More than one → HALT (conflicting defaults; vault admin reconciles).

3. **Read the resolved board-definition** from `vault/files/<def-uid>.md` (or `.tropo/seed/vault/` for the kernel default). Extract the `sections:` array from frontmatter.

4. **Execute each section query.** For each section in order:
 - Parse the prose query per [v0.3 §7.2 vocabulary (74fd9b61)](../../vault/files/74fd9b61.md). Supported target types: `tasks | projects | documents | decisions | board-definitions | board-snapshots | all`. Supported operators: `in the subtree | direct children only | up to N levels down | in the direct parent`, field predicates, boolean combinators, cascade operators.
 - Query against live ledger state — [00-index.jsonl](../../vault/00-index.jsonl) + cascade indexes as needed.
 - Apply `sort:` (default `modified DESC` when omitted) and `limit:` (default unbounded).
 - If `group_by:` declared: group per the rule (`<field>`, `<field> then <field>`, or `tag=<literal> first, then others`).
 - If zero results: render the section's `null_result:` string (default `"— No results. —"`).

5. **Render each section in its declared format** per [v0.3 §7.2.1 render exemplars (74fd9b61)](../../vault/files/74fd9b61.md):
 - `render: table` → markdown table with the `columns:` fields.
 - `render: list` → bulleted list with inline metadata.
 - `render: list-with-links` → `- [title](../../vault/files/<uid>.md) — <metadata>` bullet shape.
 - `render: tree` → indented nested markdown list following `member_of` edges (two-space indent per depth).

6. **Assemble** the rendered sections in section order with `## <title>` headings. Prepend an `# <Project Title> — Status Board (regenerated <timestamp>)` H1. The timestamp marks the render as ephemeral — readers know this is NOT a stored snapshot.

7. **Return the rendered markdown to the caller.** Do NOT write to disk. The caller decides what to do with the output (display inline, include in a channel post, feed to another tool, etc.).

## Success Criteria

- Every section executed without error OR null-result rendered when query returned zero.
- Output is valid markdown parseable by the rendering conventions.
- No files written, no vault entries created, no index updated.
- Rendering is reproducible: two invocations with the same inputs against the same ledger state produce byte-identical output (modulo the render timestamp in the H1).

## Failure Modes

- **ADR-035 Surface 2 violation** (unresolved input UID or unreachable declared `status_board:`): HALT fail-loud, surface error.
- **Query vocabulary violation** (section query uses undeclared vocabulary): HALT. Defective board-definition.
- **Render-format violation** (section declares an unknown `render:` value): HALT. Defective board-definition.
- **Kernel default missing** (pre-seed vault): HALT. Surface the [apply-update playbook (`.tropo/playbooks/apply-update.playbook.md`)](../playbooks/apply-update.playbook.md) remediation per [v0.3 §6.2 pre-seed halt (74fd9b61)](../../vault/files/74fd9b61.md).

## Comparison: regenerate-board vs create-snapshot

| Concern | regenerate-board | create-snapshot |
|---------|------------------|-----------------|
| **Writes to ledger?** | No — ephemeral output | Yes — creates `type: board-snapshot` entry |
| **Use case** | "What does project X look like right now?" | "Preserve the state of project X at this moment." |
| **Inputs** | scope_ref_uid, optional def UID | scope_ref_uid, def UID, reason (required) |
| **Output** | rendered markdown to caller | snapshot UID |
| **Cost** | low — reads ledger, returns string | higher — ledger write + index update + rebuild |
| **When to use** | Routine status queries, boot orientation, ad-hoc views | Release ship, stage close, pre-change baseline |

Both skills read the same board-definitions and use the same render engine. The difference is persistence: regenerate returns; create-snapshot records.

---

*regenerate-board | Skill v2.0 | Argus A29 | 2026-04-20*
*v2.0 rewritten for [Board Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md) — ledger-based, UID-addressed, ephemeral output. v1.0 (legacy folder layout) retired.*
*"Regenerate is live. Snapshot is historical. Both have their moment."*
