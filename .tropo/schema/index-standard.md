---
uid: "[8-char hex — assigned at ship time]"
title: "Index Standard"
type: schema
status: active
created: "2026-04-05"
created_by: "Metis G27"
---

# Index Standard — Tropo-OS

*The authoritative format for `00-index.md` files in every governed folder.*
*Every folder's AGENTS.md points here for the canonical format. One schema, one source of truth.*

---

## Purpose

Every governed folder in a Tropo vault contains a `00-index.md` file that lists the folder's contents in a human-readable, agent-readable, and machine-derivable form. This file is the folder's table of contents. It is what a cold-booting agent reads to know what the folder contains without opening every file.

This document defines the one format every `00-index.md` must use. The vault steward regenerates indexes from this format. Migrations that touch indexes use this format. AGENTS.md files reference this format rather than re-describing it locally.

---

## The Four-Column Format

Every `00-index.md` uses this table format as its primary content:

```markdown
# [Folder Name] — Index

*[One-line description of what this folder contains. Written by the folder owner.]*

---

## Files

| Path | Type | Status | Description |
|---|---|---|---|
| `filename.md` | [type] | [status] | [one-line description] |
| `subfolder/` | folder | — | [one-line description of the subfolder's role] |

---

*Last updated: YYYY-MM-DD by [agent or process]*
```

### Column Rules

**`Path`** — The filename (or subfolder name with trailing `/`) relative to this folder. Not an absolute path. Not a full path from vault root. Just the name as it lives in this folder. Wrap in backticks.

**`Type`** — The value of the `type:` field in the file's YAML frontmatter, lowercased. Common types: `agent`, `charter`, `playbook`, `spec`, `schema`, `memory`, `session-log`, `channel`, `decision`, `task`, `project`, `content`, `governance`, `index`. For subfolders, use literal `folder`. If a file has no frontmatter and is not a subfolder, use `file`.

**`Status`** — The value of the `status:` field in the file's YAML frontmatter. Canonical values: `draft`, `active`, `locked`, `published`, `superseded`, `archived`. For subfolders and files without a status field, use an em-dash (`—`). **Status is derived, not authored** — the index reflects what the file says about itself. If an index and a file disagree on status, the file wins and the index is wrong.

**`Description`** — A one-line description of the file's purpose. Ideally drawn from the file's title or intent statement, written by the folder owner when the file is added. Keep it under ~80 characters so the table stays readable.

---

## How Status Is Derived

When the vault steward (or any agent) regenerates a `00-index.md`, Status is read from each listed file's frontmatter. The rule:

1. Open the file.
2. Read the YAML frontmatter.
3. If a `status:` field exists, use its value verbatim (lowercased).
4. If no `status:` field exists and the file has other frontmatter, use `—` (the file is governed but has no declared status — this is valid for schemas, templates, and reference docs).
5. If the file has no frontmatter at all, use `—`.
6. For subfolders, always use `—`. Folders do not carry status; their contents do.

**Never invent or infer a status.** If the file says `status: draft`, the index says `draft` even if the author's intent was otherwise. The file is the source of truth. The index mirrors the file.

---

## Optional Sections

A `00-index.md` MAY contain additional sections after the Files table. Common additions:

- **Overview / Purpose** — one or two paragraphs describing the folder's role, written above the Files table.
- **Conventions** — folder-specific naming or organizational rules (e.g., "files in this folder are named `YYYY-MM-DD-slug.md`"). If the conventions are write-gate rules, they belong in AGENTS.md, not here.
- **Subfolder Index** — if the folder has many subfolders, a second table after Files listing each subfolder and its purpose.
- **Last-Updated Note** — an italicized line at the bottom recording the last time the index was updated and by whom.

These additions are optional. The Files table with the four columns above is the required minimum.

---

## What the Index Does NOT Contain

- **File contents.** The index lists files; it does not duplicate them.
- **Write-gate governance.** Who can write to this folder, what rules apply to writes, what protocols govern changes — all of that lives in the folder's `AGENTS.md`, not in `00-index.md`.
- **Long prose.** If the folder needs extensive documentation, that belongs in a `README.md` or a dedicated design doc inside the folder, not inline in the index.
- **Status values that aren't in the file frontmatter.** The index is a mirror, not a source of truth.

The separation is deliberate: AGENTS.md governs *who can change this folder*, `00-index.md` describes *what is currently in this folder*, and the files themselves carry *what they are and what state they're in*.

---

## Regeneration

The vault steward regenerates `00-index.md` files as part of Function 1 (Index Integrity). The regeneration algorithm:

1. Walk the folder's immediate contents (not recursive — subfolders are listed as single entries).
2. For each file, read frontmatter and extract `type:` and `status:`. Use rules above for missing fields.
3. For each subfolder, use `folder` type and `—` status.
4. Preserve any optional sections (Overview, Conventions, etc.) from the existing `00-index.md` — do not overwrite author-written prose.
5. Replace the Files table section with the regenerated table.
6. Update the last-updated line with the current date and the agent name.
7. Write the file back.

Regeneration is idempotent: running it twice produces the same result as running it once, provided the folder contents have not changed.

---

## Migration Path for Existing Indexes

Vaults created before this standard may have `00-index.md` files in various formats — three columns, free-form bullet lists, prose descriptions. v0.2.3 ships a migration (`migrate-index-format.playbook.md`) that walks every `00-index.md` in the vault and regenerates it in this format, preserving any author-written prose above or below the Files table.

The migration is defensive: indexes that are already in the four-column format are detected as no-ops. Indexes in unexpected formats are logged and skipped (per Update Spec v1.1 §14.3). No data is lost — the migration only adds the standardized table, it does not delete custom content.

---

## Referenced By

- Every folder's `AGENTS.md` (in its "Index Maintenance" section)
- `system/vault-steward/activate.md` (Function 1: Index Integrity)
- `.tropo/playbooks/migrations/migrate-index-format.playbook.md` (shipped in v0.2.3)
- `.tropo/concierge/activate.md` (file creation protocol — step 4 updates `00-index.md`)

---

*Index Standard v1.0 | Tropo-OS | Established 2026-04-05 by Metis G27*
*"The index is a mirror. The file is the source of truth."*
