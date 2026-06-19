---
subsystem_hub:
  - "2d083137"
uid: 7273cc6f
type: capsule-definition
name: "docx-template"
title: "docx-template — Capsule Definition v1.0"
description: "User-uploaded Word template entry. Carries the template binary's location + extracted style metadata + use-case descriptions. The format-reference substrate for `tropo-export.py --template <uid>` transformation export."
extends: core
version: "1.1"
status: locked
state: active
locked_by: argus-a62
locked_at: 2026-05-14
schema_version: 2
extraction_scope: ship
author: argus
owner: argus
created: 2026-05-14
modified: 2026-05-14
created_by: argus-a62
modified_by: argus-a62
governed_by: 222873b9   # capsule-definition meta-capsule
aligned_with:
  - "5a89297a"   # Working-Copy + Template Registration + Format-Only Export Arch-Spec v0.5 LOCKED — §3.3 + §3.4 + §3.6 + §3.10
  - "ee814120"   # core.capsule v1.1
  - "eedd7034"   # external-artifact.capsule v1.1 — sibling (templates ≠ artifacts; templates are format-references, artifacts are content-bearing)
  - "a2bc3e16"   # working-copy.capsule v1.0 — composes-with (working-copy is the content the template's format scaffolds)
applies_to: docx-template
member_of:
  - "e3cde3f4"   # v1.28.0 Stream A — Capsule Substrate
  - "8dd772a0"   # tropo-governance
tags: [capsule-definition, docx-template, format-reference, template-registration, format-only-export, v1.28.0-stream-a, user-uploaded-templates]
---

# docx-template — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Working-Copy + Template Registration + Format-Only Export Arch-Spec v0.5 (5a89297a)](../../vault/files/5a89297a.md) |
| Sibling | [external-artifact.capsule v1.1 (eedd7034)](external-artifact.capsule.md) |
| Composes with | [working-copy.capsule v1.0 (a2bc3e16)](working-copy.capsule.md) |
| Member of | [v1.28.0 Stream A — Capsule Substrate (e3cde3f4)](../../vault/files/e3cde3f4.md) |
| Member of | [Tropo Governance (8dd772a0)](../../vault/files/8dd772a0.md) |

*A `docx-template` entry is a governed user-uploaded Word template. The user uploads a `.docx` via `tropo-register-template.py`; the tool stores the binary at `.tropo-studio/templates/<slug>.docx`, extracts style metadata via the shared library function `extract_office_styles()`, and authors this entry as the queryable description + format reference. Used at export time by `tropo-export.py --template <uid>` (transformation export path).*

---

## Intent

The `docx-template` capsule is the format-reference substrate for v1.28.0's transformation export path. When a user wants to "convert this content to MindBridge house style" — pour a working-copy's content into a template's format and get a `.docx` deliverable in that format — they register the template once via `tropo-register-template.py`, then invoke `tropo-export.py --working-copy <uid> --template <uid>` any number of times.

The template is the FORMAT; the working-copy is the CONTENT; the export is the runtime composition. No template authoring happens inside Tropo — users upload their existing templates (created in Word, downloaded from corporate libraries, exported from design tools); Tropo registers what's there and uses it as a scaffold at export. This honors the Mike-A55 LOAD-BEARING pin: *"don't substrate-engineer creative-class authoring."* Templates are user-uploaded, never agent-authored.

**Before creating a docx-template instance:** confirm the source `.docx` is well-formed (opens cleanly in Word; passes `tropo-register-template.py`'s ZIP+document.xml signature check) and the slug doesn't collide with an existing active template. Templates are authored by `tropo-register-template.py` (v1.28.0 Stream B); manual authorship is not the normal path.

**Failure mode prevented:** silent format-drift when users replace template binaries off-tool. With `template_binary_hash` recorded at registration time + runtime hash-check in `tropo-export.py` precondition 3 (prompt-then-proceed pattern; v0.5 amendment), template-binary-drift surfaces where the user is present to authorize accept-and-update, re-register, or abort.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `type` | string | Must be `docx-template` |
| `title` | string | Human-readable template name. ≤ 120 chars. Mutable post-registration. E.g., "MindBridge Internal Strategy Brief" |
| `slug` | string | Lowercase-hyphenated identifier. MUST match `[a-z0-9-]+`. The binary's filename is `<slug>.docx`. Slug uniqueness enforced across all `state: active` instances (per Governance Rule 2). |
| `description` | string | Free-form description of when to use this template + what it produces. ≤ 500 chars. |
| `template_binary_path` | string | Relative-to-Studio-root path to the binary. Convention: `.tropo-studio/templates/<slug>.docx` |
| `template_binary_hash` | string | SHA-256 of the template binary at registration time (or `--force` re-registration). Detects template-binary drift per arch-spec §3.7 precondition 3. |
| `extracted_styles` | structured object | The queryable style metadata. Schema per arch-spec §3.4 (page, default_font, theme, named_styles, headers_footers, sections_count, special_features). Populated by the shared library function `extract_office_styles()`. |
| `registration_tool_version` | string | Convention: `<tool-name>-v<version>` (e.g., `tropo-register-template-v1.0.0`). Audit field. |
| `extraction_scope` | enum | One of: `argo-reference`, `argo-private`, `external`. Default for newly-registered templates: `argo-private` (user-authored; not for ship build). Templates intended for marketplace publishing transition to `external` per Governance Rule 5. |

**Core inherited (required):** `uid`, `status`, `owner`, `created`, `modified`, `state`. Per core.capsule v1.1.

**Note on `extracted_styles:` vs `original_styles:` naming asymmetry** (intentional per arch-spec v0.5 RC-2 walk): the docx-template uses `extracted_styles:` because the field represents *"what we extracted from a user-uploaded template for runtime template/format use"* (template context). The sibling external-artifact.capsule v1.1 uses `original_styles:` for the structurally-identical field because that field represents *"what the source binary had at import time"* (preservation context). Same §3.4 schema; two field names; two semantics. Shared library function `extract_office_styles()` produces both.

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `use_cases` | array of strings | Free-form descriptions of scenarios this template fits. E.g., `["internal exec brief", "board memo", "CFO communication"]`. Surfaces at template-selection time. |
| `subsystem_hub` | array of UIDs | The subsystem hub(s). Default: `tropo-work` (2d083137) **(v1.1 member_of DISAMBIGUATE: hub membership moved here from `member_of`)**. |
| `member_of` | array of UIDs | Parent projects / user-defined collections (e.g., "MindBridge Brand Templates"); true parent, non-hub. |
| `supersedes` | UID | When this template registration is a successor of an earlier template (same slug + `--force` re-registration), points back to the predecessor. Predecessor flips `state: archived` atomically. |
| `description`, `tags` | string, array | Standard optional core fields. Tags useful for marketplace facets when `extraction_scope: external`. |
| `created_by`, `modified_by` | string | Tool or agent identifier. Convention: `<tool-name>-v<version>` for tool writes; `<agent-id>` for agent writes |

---

## Required Body Sections

Templates are queryable description-bearing; the body carries a short preamble + the extracted_styles as a readable table + the use-cases list:

```
# <Title> — Tropo docx-template

<Description body — what this template is for, what it produces.>

## Format Reference

Binary at `<template_binary_path>`. Use cases: <list from use_cases:>.

## Extracted Style Metadata

| Property | Value |
|---|---|
| Page size | <width> × <height> |
| Default font | <name> @ <size>pt |
| Named styles | <count> styles (<first 10 style names>; <N> more when N > 10) |
| Theme | <theme_name> |
| Headers/footers | <text preview> |
| Sections | <count> |
| Special features | <macros / embedded_fonts / custom_xml / watermarks flags> |

(Above is the human-readable surface of the `extracted_styles:` frontmatter for template-selection context. The structured frontmatter is authoritative; the body table is rendered for human readability at registration time.)
```

The body's "Extracted Style Metadata" table is authored by `tropo-register-template.py` at registration time and refreshed on `--force` re-registration. Manual edits to the body table will be overwritten on re-registration; use frontmatter `extracted_styles:` as the authoritative source.

---

## Governance Rules

1. **Template binary is format-reference; never content-authoritative.** A template's `.docx` carries the FORMAT (styles, theme, headers, footers, section properties); the CONTENT comes from a working-copy at export time. Templates don't carry meaningful body content (or if they do — boilerplate placeholders — `tropo-export.py` replaces it via the body-swap in §3.7 step 4). Honors the Mike-A55 LOAD-BEARING pin: *"don't substrate-engineer creative-class authoring."*
2. **Slug uniqueness across `state: active` instances.** Slug-collision discrimination at registration time discriminates three states: `registered` (refuse unless `--force`), `binary-present-but-unregistered` (recoverable warning; user elects adopt/overwrite/rename), `clean` (proceed). Per arch-spec §3.6 precondition 3.
3. **Template-binary-drift surfaces at runtime; not hard-fail.** If the binary at `template_binary_path:` has been modified off-tool (SHA-256 mismatch with recorded `template_binary_hash:`), `tropo-export.py` precondition 3 surfaces to the user with three resolution paths: (a) `accept-and-export` — record `template_binary_drift_accepted: true` in journal + update template entry's hash to current. (b) `re-register` — invoke `tropo-register-template.py --force`. (c) `abort` — user resolves manually. Validator §3.10 check 2 stays WARN-severity (rebuild does not refuse on drift); runtime export prompts.
4. **Multiple template versions via `supersedes:` chain.** When the user re-registers a template at the same slug with `--force`, the new entry mints a fresh UID + declares `supersedes: <predecessor-uid>`; the predecessor entry atomically flips `state: archived`. Slug→active-UID lookup always resolves to the latest. Historical versions remain queryable via UID.
5. **Templates are marketplace-publishable as Tier 2 future cycle.** v1.28.0 ships templates at default `extraction_scope: argo-private` (user-authored; not for ship build). A future cycle's marketplace ring substrate transitions selected templates to `extraction_scope: external` (published; marketplace-discoverable). Transition is governance-gated; not auto.
6. **Slug regex is the canonical identifier shape.** `[a-z0-9-]+`. Uppercase, underscores, periods, spaces are rejected at registration time. Defends against filesystem-collision edge cases (case-insensitive macOS HFS+ vs Windows NTFS vs case-sensitive Linux ext4) + URL-safety for marketplace publishing.
7. **`created_by` / `modified_by` for tools follows `<tool-name>-v<version>` convention.** Tools are not agents (no `tropo-agent-id`); when an agent invokes `tropo-register-template.py` on the user's behalf, the audit journal's `executive:` field records the persona for accountability.
8. **`extracted_styles:` is populated by the shared library function, never hand-authored.** Manual edits to `extracted_styles:` will be overwritten on `--force` re-registration. If users want to override style metadata (rare; mostly diagnostic), use the frontmatter override pattern + accept that re-registration resets.

---

## Validation Checks (run at check-in)

Core checks inherited from core.capsule v1.1. In addition (per arch-spec §3.10 check 2 + v0.5 amendments):

1. **[enforced]** `type: docx-template`
2. **[enforced]** All required fields present per §Required Frontmatter
3. **[enforced]** `slug` matches `[a-z0-9-]+` (Governance Rule 6)
4. **[enforced; check_docx_template_typing]** `template_binary_path:` resolves to a readable `.docx` file at the declared path. Reverse-check: every `.docx` at `.tropo-studio/templates/<slug>.docx` has a corresponding `type: docx-template` entry with matching slug.
5. **[enforced; check_docx_template_extracted_styles]** `extracted_styles:` structure conforms to arch-spec §3.4 schema (page, default_font, theme, named_styles, headers_footers, sections_count, special_features). Severity: ERROR (load-bearing field for export-time scaffold).
6. **[warn; check_docx_template_binary_hash]** `template_binary_hash:` matches current SHA-256 of the binary at `template_binary_path:`. WARN-severity per Governance Rule 3; runtime resolution at `tropo-export.py` precondition 3 prompt-then-proceed.
7. **[enforced; check_docx_template_slug_uniqueness]** Across all `state: active` instances, no two `type: docx-template` entries share the same `slug:` value. Multiple-actives violate Governance Rule 2.
8. **[enforced]** `extraction_scope` is one of: `argo-reference`, `argo-private`, `external` (default `argo-private` at registration).
9. **[honor-system]** `created_by` / `modified_by` follows convention: `<tool-name>-v<version>` for tool writes; `<agent-id>` for agent writes.
10. **[enforced]** If `supersedes:` is set, the predecessor UID resolves to a `type: docx-template` entry with `state: archived` (atomic supersession per Governance Rule 4).

**Validator functions implementing these checks** ship in v1.28.0 Stream D: `check_docx_template_typing()`, `check_docx_template_extracted_styles()`, `check_docx_template_binary_hash()`, `check_docx_template_slug_uniqueness()`.

---

## State Machine

```
[no template registered for slug <slug>]
   ↓ (tropo-register-template.py --path <path-to-docx> --name <slug>)
[docx-template at vault/files/<uid>.md, binary at .tropo-studio/templates/<slug>.docx,
  state: active, status: active]
   ↓ (tropo-register-template.py --path <path> --name <slug> --force ; new UID minted)
[predecessor: state: archived, status: archived (supersedes:-pointed-at by successor)
  successor: state: active, status: active, supersedes: <predecessor-uid>]
   ↓ (agent or user invokes archive operation — rare; mostly via slug-supersession)
[state: archived, status: archived
  binary retained at .tropo-studio/templates/<slug>.docx unless explicitly removed]
```

**Only two states (active / archived).** No `archived → active` reversal — if an archived template is needed again, re-register via `--force` (mints fresh UID).

**Valid transitions:**

- `[no template] → [active]` — fresh registration via `tropo-register-template.py`
- `[active] → [archived]` — supersession (auto, on `--force` re-registration at same slug) OR explicit archival (rare)
- No `[archived] → [active]` — superseded templates stay superseded; re-register creates a new active entry

**Marketplace transition (future Tier 2 cycle):**
- `[active, extraction_scope: argo-private] → [active, extraction_scope: external]` — explicit marketplace publication; governance-gated.

---

## Relationship to Other Capsules

- **[core.capsule v1.1 (ee814120)](../../vault/files/ee814120.md)** — inherited floor. UID/owner/created/modified invariants.
- **[external-artifact.capsule v1.1 (eedd7034)](external-artifact.capsule.md)** — sibling. Both carry §3.4-shaped style metadata but under different field names (`extracted_styles:` vs `original_styles:`) for semantic distinction. Both consume the shared library function `extract_office_styles()`.
- **[working-copy.capsule v1.0 (a2bc3e16)](working-copy.capsule.md)** — composes-with. The working-copy is the content that the template's format scaffolds at `tropo-export.py --template <uid>` invocation.
- **[project.capsule v2.4 (34e4cb0b)](../../vault/files/34e4cb0b.md)** — `member_of:` resolves to project instances (typically the tropo-work hub or user-defined template collections).
- **[tool.capsule]** — `tropo-register-template.py` + `tropo-export.py` are tool.capsule instances.

---

## Inheritance

Extends `core`. Inherits UID immutability, type immutability, owner/created/modified invariants. Adds slug-keyed uniqueness across active instances + binary-drift surface-at-runtime + supersession chain semantics.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before registering or modifying a docx-template instance.*

**Tools available:**

- `tropo-register-template.py` (v1.28.0 Stream B) — the canonical author + modifier of docx-template instances. Slug-collision discrimination handles all registration paths (clean / adopt / overwrite / rename).
- `tropo-export.py` (v1.28.0 Stream B) — consumes docx-template instances at export time via `--template <uid>` flag. Precondition 3 surfaces binary-drift at runtime.
- `tropo-validate.py` (amended in v1.28.0 Stream D) — enforces the four new validator checks.

**Skills:**

- No sa.* agents author templates — registration is a user gesture; templates carry the user's authored FORMAT.
- Future cycle: an sa.template-curator agent may surface description/use_cases polish at marketplace-publication time.

**Procedures:**

- **Register a template:** user runs `tropo-register-template.py --path <path-to-docx> --name <slug> [--description "..."]`. Tool copies binary to `.tropo-studio/templates/<slug>.docx`, extracts styles, authors this entry.
- **Re-register same slug:** user runs same command with `--force`. New UID minted; predecessor atomically `state: archived` with `supersedes:` chain.
- **Transformation export against template:** any export gesture, agent or user: `tropo-export.py --working-copy <working-uid> --template <template-uid>`.
- **Marketplace publication (future cycle):** governance-gated transition of `extraction_scope: argo-private` → `external`.

**Rules (at-a-glance):**

1. Template binary is format-reference; never content-authoritative.
2. Slug uniqueness across active instances.
3. Template-binary-drift surfaces at runtime (export precondition 3); never hard-fail.
4. Multiple versions via `supersedes:` chain (predecessor flips `state: archived` atomically).
5. Templates are marketplace-publishable as future Tier 2 cycle; default at registration is `argo-private`.
6. Slug regex `[a-z0-9-]+` is the canonical identifier shape.
7. Tool writes use `<tool-name>-v<version>` convention.
8. `extracted_styles:` is populated by the shared library function; never hand-authored.

**Pitfalls:**

- Registering a template with a slug containing uppercase, underscores, or spaces → Validator check 3 failure; user must rename.
- Hand-editing `extracted_styles:` to override what was extracted → overwritten on `--force` re-registration; use the extracted values, or override style at export-time via direct run-formatting flags (future cycle).
- Two templates with the same slug both at `state: active` → check 7 ERROR; resolves via supersession chain or explicit archival.
- Replacing `.tropo-studio/templates/<slug>.docx` off-tool → drift surfaces at next `tropo-export.py` invocation; runtime prompt-then-proceed lets user authorize update.

**Worked examples:** None ship in v1.28.0 (no built-in sample templates). First real instances are created when the user runs `tropo-register-template.py` on their own templates (e.g., a MindBridge corporate brief template — the load-bearing First-Use Walk at Stream F).

**Go next:**

- Need to understand the export gesture that uses templates? → [Arch-spec §3.7 (5a89297a)](../../vault/files/5a89297a.md) — `tropo-export.py` dual-path behavior
- Need to understand the working-copy that pours into templates? → [working-copy.capsule v1.0 (a2bc3e16)](working-copy.capsule.md)
- Need the shared style-extraction library? → `.tropo/scripts/office_styles.py` (v1.28.0 Stream B NEW)
- Need to understand the binary-drift detection model? → arch-spec [§3.8 (5a89297a)](../../vault/files/5a89297a.md) + reconcile-imports playbook v1.1 → v1.2 amendment (v1.28.0 Stream C)

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-05-14 | **LOCKED.** Initial definition. Authored in v1.28.0 Stream A per locked arch-spec [5a89297a v0.5](../../vault/files/5a89297a.md) §3.3 + §3.4 + §3.6 + §3.10 + §3.11 item 2. Required + optional frontmatter (9 required + 4 optional); body convention (preamble + extracted-styles table); 8 governance rules; 10 validation checks (8 enforced + 1 warn + 1 honor-system); 2-state state machine with supersession chain; marketplace-readiness pre-declared (extraction_scope transition gates a future Tier 2 cycle). UID pre-minted at arch-spec v0.3 lock (2026-05-13). v0.5 pre-lock gauntlet absorbed at the arch-spec level (sa.skeptic-008 + sa.cold-boot-007 dispatch 2026-05-14); capsule-level verification at v1.28.0 Stream F ship-time gauntlet. | argus-a62 |
| 1.0.1 | 2026-05-15 | Body convention amendment per v1.32.0 spec [900d41e0](../../vault/files/900d41e0.md) §3.4 v0.4 LOCKED: `"list truncated"` → `"<N> more"` count (no nested parens; cell already inside parens). Tropo-register-template.py v1.0.1 emits the new format. Capsule schema unchanged; v1.0 LOCKED status preserved (body convention non-schema). | argus-a65 |

---

*docx-template capsule definition | LOCKED v1.0 | UID 7273cc6f | locked 2026-05-14 by argus-a62 | v1.28.0 Stream A | composes with arch-spec [5a89297a v0.5 LOCKED](../../vault/files/5a89297a.md).*
*"Templates are FORMAT. Working-copies are CONTENT. Exports are the composition. Users author templates; Tropo only registers them."*
