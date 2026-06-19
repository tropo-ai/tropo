---
uid: eedd7034
type: capsule-definition
name: "external-artifact"
title: "external-artifact — Capsule Definition v1.1"
description: "Sidecar schema for user files imported into a Tropo Studio. The substrate primitive that makes the import primitive's two-tier governance ladder work. v1.1 adds optional `original_styles:` frontmatter field for `.docx` style-extraction-at-import (v1.28.0 Stream A)."
extends: core
version: "1.1"
status: locked
state: active
enforced_enums:
  status: [active, archived]
meta_status_rollup:
  in-progress: [active]
  done: [archived]
locked_by: argus-a62
locked_at: 2026-05-14
v1_0_locked_by: argus-a60
v1_0_locked_at: 2026-05-13
schema_version: 2
extraction_scope: ship
author: argus
owner: argus
created: 2026-05-13
modified: 2026-05-14
created_by: argus-a60
modified_by: argus-a62
governed_by: 222873b9   # capsule-definition meta-capsule
aligned_with:
  - "2b49ba79"   # Import Primitive Architecture Specification v1.0 LOCKED
  - "5a89297a"   # Working-Copy + Template Registration + Format-Only Export Arch-Spec v0.5 LOCKED — §3.5.5 Amendment 2 + §3.11 item 3 mandate this v1.1 amendment
  - "ee814120"   # core.capsule v1.1
applies_to: external-artifact
member_of:
  - "c512438b"   # v1.25.0 Stream A — Capsules
  - "e3cde3f4"   # v1.28.0 Stream A — Capsule Substrate (v1.1 amendment lands here)
  - "8dd772a0"   # tropo-governance
tags: [capsule-definition, external-artifact, sidecar, import-primitive, v1.25.0-stream-a, v1.28.0-stream-a, original-styles-at-import]
---

# external-artifact — Capsule Definition v1.1

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](222873b9.md) |
| Aligned with | [Import Primitive — Architecture Specification (2b49ba79)](2b49ba79.md) |
| Member of | [v1.25.0 — Stream A: Capsules (c512438b)](c512438b.md) |
| Member of | [Tropo Governance (8dd772a0)](8dd772a0.md) |

*An `external-artifact` entry is a sidecar — a markdown+YAML file that carries Tropo's metadata for a user file imported into the Studio. Sidecars live at `<folder>/.tropo-studio/<filename>.tropo.md`. They are the canonical truth for imported user content per OS Invariant #8 (sidecar-as-truth); vault projections are derived from them.*

---

## Intent

The `external-artifact` capsule is the substrate primitive that makes user-content governance work. When a user imports a folder of strategy documents, research PDFs, financial models, and meeting notes into a Tropo Studio, every file in scope gets an `external-artifact` sidecar adjacent to it (in the folder's hidden `.tropo-studio/` directory). The sidecar carries the UID + metadata + governance state; the source file is untouched.

This capsule operationalizes the brief's locked structural rule (*"sidecar is canonical truth; vault is projection"*) at the typed-substrate level. Without `external-artifact`, the import primitive has no schema; with it, the entire reconciler subsystem, vault projection layer, validator-check apparatus, and extraction machinery have a contractual foundation to operate against.

**Before creating an external-artifact instance:** confirm the file is in a governed folder (one with `.tropo-folder.md` present) and is NOT in `.tropoignore`. Sidecars are authored by `import-walker.py` (Stream B); manual authorship is not the normal path.

**Failure mode prevented:** silent metadata loss when user files move, rename, or content-change outside agentic processes. With `external-artifact` as truth + UID stability + hash-based reconciliation, the historical sidecar-tooling failure modes (Lightroom catalog corruption; Apple Photos opacity; digiKam edge cases) do not reproduce in Tropo.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `type` | string | Must be `external-artifact` |
| `source_filename` | string | Original filename (e.g., `Q3-strategy-memo.docx`); immutable post-import |
| `source_path` | string | Relative path to the source file. **Tier 1:** `../<filename>` (relative to sidecar in `.tropo-studio/`). **Tier 2:** `source.<ext>` (sibling of metadata.md in per-UID directory). |
| `original_path` | string | Path to the source when first imported, relative to Studio root. Equals `source_path` in Tier 1; preserved as the original location in Tier 2 for symlink-tree regeneration. |
| `source_size_bytes` | integer | Source file size at last reconciliation |
| `source_mtime` | ISO 8601 timestamp | Source file mtime at last reconciliation |
| `source_hash` | hex string | Hash of source per the `hash_function` value below |
| `hash_function` | enum | `stable-id` \| `content-aware` \| `sha256` — which function produced the recorded `source_hash` (per fallback chain) |
| `member_of` | UID array | At minimum the immediate parent folder-project UID (single direct parent only; transitivity walks via graph) |
| `governance` | enum | `tier-1-sidecar` (v1.25.0) \| `tier-2-vault-native` (Phase 2) |
| `schema_version` | integer | `1` |

**Core inherited (required):** `uid`, `status`, `title`, `owner`, `created`, `modified`. Per core.capsule v1.1.

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `description` | string | One-line description; placeholder at import time; populated by sa.\* refined pass at promotion or on user request |
| `relations` | typed-edge array | Cross-references; empty at import; populated as any agent creates a cross-reference touching this entry |
| `tags` | string array | Free-form tags |
| `created_by`, `modified_by` | string | Tool or agent identifier. Convention: `<tool-name>-v<version>` for tool writes; `<agent-id>` for agent writes |
| `original_styles` | structured object | **v1.1 NEW (per arch-spec [5a89297a v0.5](../../vault/files/5a89297a.md) §3.5.5 Amendment 2).** Style metadata extracted from the source binary at import time. Schema mirrors `docx-template.extracted_styles:` structure declared in arch-spec §3.4 (keys: `page`, `default_font`, `theme`, `named_styles`, `headers_footers`, `sections_count`, `special_features`). Populated by `import-walker.py create-sidecar` via the shared library function `extract_office_styles()` at `.tropo/scripts/office_styles.py` (v1.28.0 NEW). `.docx` only for v1.28.0; other Office types (`.xlsx`, `.pptx`) defer to their own future cycles per arch-spec §5.6. Naming asymmetry with `docx-template.extracted_styles:` is intentional, semantics-driven: `original_styles:` records *"what the source binary had at import time"* (preservation context — feeds export §3.7 P2 fallback); `extracted_styles:` records *"what we extracted for template/format use"* (template context). Field is OPTIONAL — pre-v1.28.0 projections + non-Office binaries permanently lack it; `tropo-backfill-styles.py` (v1.28.0 NEW per arch-spec §3.13) backfills pre-existing `.docx` projections. |

---

## Required Body Sections

Minimal body convention. Sidecars are metadata-bearing; the body carries a single navigational paragraph:

```
# <Title> — Tropo Sidecar

Governs `<source_path>` in folder-project `<member_of-uid>`.
Vault projection at `vault/files/<uid>.md` (Tier 1) or `vault/files/<uid>/metadata.md` (Tier 2).
```

No required §-level sections beyond this paragraph. The sidecar is primarily a frontmatter contract; the body is a navigational hint.

---

## Governance Rules

1. **UID immutable across tier upgrades.** When a sidecar transitions from `governance: tier-1-sidecar` to `governance: tier-2-vault-native` (promotion) or back (extraction-to-tier-1), the UID does NOT change. Cross-references that pointed at the entry resolve before and after.
2. **Source-path semantics by tier.** `source_path` is always relative to the sidecar's own location. In Tier 1, this resolves to `../<filename>`. In Tier 2 (when the sidecar IS the metadata.md inside the per-UID directory), this resolves to `source.<ext>`. Validator enforces tier-appropriate format.
3. **Sidecars travel with their source.** OS-level move atomicity: when a user moves a folder, both the source file and the `.tropo-studio/<filename>.tropo.md` move together. Relative path `../<filename>` stays valid without rewriting.
4. **Vault projection is derived; never authoritative.** `vault/files/<uid>.md` (Tier 1) or `vault/files/<uid>/metadata.md` (Tier 2) is regenerable from this sidecar at any time. Per OS Invariant #8, anything that exists only in the projection and not in the sidecar is data Tropo can lose.
5. **Hash function fallback chain.** Per `hash_function:` enum: try stable-identifier first (Office docProps/core.xml dc:identifier; PDF /ID); fall back to content-aware hash (XML payload extraction + SHA-256); fall back to plain SHA-256. The function used is recorded; future reconciliations honor the recorded function unless explicitly upgraded.
6. **`member_of` is the immediate direct parent only.** Sub-folder transitivity walks via the graph. Sub-folder governance requires either a governed parent folder OR direct membership in a vault-entity-owned root project (per project.capsule v2.4 Rule 1 composability).
7. **`created_by` / `modified_by` for tools follows `<tool-name>-v<version>` convention.** Tools are not agents (no `tropo-agent-id`); the audit log's `executive:` field carries the persona that triggered the operation for accountability.
8. **Hash function upgrade is non-destructive.** If a stable-identifier becomes available for a file previously hashed with content-aware (or plain SHA-256), the reconciler MAY upgrade the `hash_function:` + recompute `source_hash:`. The audit log records the upgrade event.

---

## Validation Checks (run at check-in)

Core checks inherited from core.capsule v1.1. In addition:

1. **[enforced]** `type: external-artifact`
2. **[enforced]** All required fields present per §Required Frontmatter
3. **[enforced]** `governance` is one of: `tier-1-sidecar`, `tier-2-vault-native`
4. **[enforced]** `hash_function` is one of: `stable-id`, `content-aware`, `sha256`
5. **[enforced]** `schema_version: 1`
6. **[enforced; check_sidecar_source_pairing]** Sidecar's `source_path` resolves to an existing source file at the expected location. Reverse-check: every file in a governed folder (per parent's `.tropo-folder.md`) that is NOT in `.tropoignore` has a corresponding sidecar.
7. **[enforced; check_external_artifact_typing]** All required external-artifact fields present (this rule + core check 4 combined).
8. **[enforced; check_uid_stability_across_tier]** If a vault projection exists at `vault/files/<uid>.md` or `vault/files/<uid>/metadata.md`, its UID matches this sidecar's UID; projection path matches `governance:` value per arch-spec §C.3.
9. **[enforced]** `source_path` relative-format is correct for the tier (Tier 1: `../<filename>`; Tier 2: `source.<ext>`).
10. **[enforced]** `member_of` non-empty; immediate-parent UID resolves to a `type: project` with `lifecycle: standing` AND `governance: tier-1-sidecar` OR `tier-2-vault-native` matching this sidecar's governance value, OR to a vault-entity-owned root project (per project.capsule v2.4 Rule 1).
11. **[honor-system]** `created_by` / `modified_by` follows convention: `<tool-name>-v<version>` for tool writes; `<agent-id>` for agent writes.
12. **[enforced; check_original_styles_structure — v1.1 NEW per arch-spec §3.10 check 7]** If `original_styles:` is present on an external-artifact entry, its structure conforms to the `extracted_styles` schema declared in arch-spec §3.4 (page / default_font / theme / named_styles / headers_footers / sections_count / special_features). Severity: WARN — `original_styles:` is opportunistic (not load-bearing for governance); validator surfaces structural drift but does not refuse the build. Implemented at v1.28.0 Stream D.

**Validator functions implementing these checks** ship in v1.25.0 Stream E ([cd63ff4e](cd63ff4e.md)): `check_external_artifact_typing()`, `check_sidecar_source_pairing()`, `check_uid_stability_across_tier()`. **v1.28.0 Stream D adds** `check_original_styles_structure()` per check 12.

---

## State Machine

**Canonical status enum:** `status:` ∈ {active, archived}

```
[ungoverned source file at <folder>/<filename>]
   ↓ (auto-index via import-walker.py)
[external-artifact at <folder>/.tropo-studio/<filename>.tropo.md
  governance: tier-1-sidecar, status: active]
   ↓ (agent-mediated promotion)  ↑ (agent-mediated extraction → tier-1-sidecar)
[external-artifact at vault/files/<uid>/metadata.md + source.<ext>
  governance: tier-2-vault-native, status: active]
   ↓ (agent-mediated extraction → ungoverned)
[ungoverned source file at user-chosen destination
  external-artifact entry: status: archived, state: archived (historical record preserved)]
```

UID is stable across all transitions. `governance:` carries the tier; `status:` carries lifecycle workflow (active/archived). Both fields are orthogonal; both contribute to state-machine position.

**Valid transitions:**

- `[ungoverned] → [tier-1-sidecar, active]` — auto-index by import-walker.py
- `[tier-1-sidecar, active] → [tier-2-vault-native, active]` — agent-mediated promotion per arch-spec §A.8
- `[tier-2-vault-native, active] → [tier-1-sidecar, active]` — agent-mediated extraction (demotion) per arch-spec §A.8 mode `tier-1-sidecar`
- `[tier-2-vault-native, active] → [ungoverned]` — agent-mediated extraction per arch-spec §A.8 mode `ungoverned`; sidecar entry flips to `status: archived, state: archived`
- `[tier-1-sidecar, active] → [ungoverned]` — agent-mediated extraction; same archival pattern

**In-flight transitions** (promotion or extraction mid-flight): atomic at the `import-walker.py` lock level. Failure mid-flight triggers journal-replay rollback per arch-spec §S.1 + §A.6.

---

## Relationship to Other Capsules

- **[core.capsule v1.1 (ee814120)](ee814120.md)** — inherited floor. UID/owner/title/status/created/modified invariants.
- **[project.capsule v2.4 (34e4cb0b)](34e4cb0b.md)** — `member_of:` resolves to project instances (folder-projects per the import primitive's folder-as-project mapping).
- **[reconcile-report.capsule v1.0 (013b7b6e)](013b7b6e.md)** — sibling. sa.reconciler reports actions on external-artifact instances using this report schema.
- **[tool.capsule]** — `import-walker.py` (the tool that authors and modifies external-artifact instances) is a tool.capsule instance.
- **[agent.capsule]** — `sa.reconciler` (the agent that orchestrates reconciliation) is an agent.capsule instance.
- **[playbook.capsule]** — `reconcile-imports.playbook` (sa.reconciler's playbook) is a playbook.capsule instance.

---

## Inheritance

Extends `core`. Inherits UID immutability, type immutability, owner/created/modified invariants. Adds tier-aware state machine + cross-tier UID stability.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before authoring or modifying an external-artifact instance.*

**Tools available:**

- `import-walker.py` (v1.25.0 Stream B) — the canonical author + modifier of external-artifact instances
- `scan-import-state.py` (v1.25.0 Stream B) — boot-time shallow scanner; reports anomaly counts
- `tropo-validate.py` (amended in v1.25.0 Stream E) — enforces the three new validator checks
- `rebuild-vault.py` (amended in v1.25.0 Stream D) — walks sidecars to regenerate vault projections

**Skills:**

- sa.reconciler agent (v1.25.0 Stream C) — orchestrates reconciliation passes; never directly authors; delegates writes to import-walker.py
- sa.* refined pass (v1.X follow-on; agent name in-cycle scope) — enriches title/description/relations on promotion

**Procedures:**

- **Auto-index at install + ongoing:** import-walker.py creates sidecars for every file in governed folders not in `.tropoignore`. User never invokes directly.
- **Promotion (Tier 1 → Tier 2):** agent-mediated; user says "promote folder X to vault-native"; agent invokes import-walker.py promote-folder.
- **Extraction:** agent-mediated; three modes (ungoverned / tier-1-sidecar / stay).
- **Reconciliation:** daily via fleet-ops scheduling sa.reconciler; boot-time anomaly-driven via scan-import-state.py output.
- **Rebuild from sidecars:** if vault/ is corrupted or accidentally deleted, `rebuild-vault.py` walks `**/.tropo-studio/*.tropo.md` and regenerates all projections byte-equivalent.

**Rules (at-a-glance):**

1. UID immutable across tier upgrade.
2. Source-path is relative to sidecar; Tier 1 vs Tier 2 formats differ.
3. Sidecars travel with their source file.
4. Vault projection is derived; never authoritative.
5. Hash function fallback chain: stable-id → content-aware → sha256.
6. `member_of` is the immediate direct parent only.
7. Tool writes use `<tool-name>-v<version>` convention for `created_by`/`modified_by`.
8. Hash function upgrades are non-destructive + audit-logged.

**Pitfalls:**

- Authoring a sidecar with absolute `source_path` → violates Rule 2; reconciler can't track folder moves.
- Authoring a sidecar without `hash_function` → Check 4 failure; reconciler can't validate or upgrade.
- Setting `governance: tier-2-vault-native` while `source_path: ../<filename>` → Rule 2 violation; Tier 2 source lives at sibling `source.<ext>`.
- Adding multiple direct parents to `member_of:` → Rule 6 violation; sub-folder transitivity walks via graph traversal, not via duplicating membership.
- Hand-editing a sidecar in `.tropo-studio/` outside an agent → violates conversation-as-surface; the audit log won't capture the change; reconciler may detect drift on next pass.

**Worked examples:** None ship in v1.25.0 (no built-in sample data). First real instances are created at user install-time when import-walker.py runs its first pass against the user's existing folders.

**Go next:**

- Need to understand the reconciler that operates on these? → [sa.reconciler agent (e4af1001)](e4af1001.md) + [reconcile-imports.playbook (4a2f6dbd)](4a2f6dbd.md)
- Need to understand the report sa.reconciler produces? → [reconcile-report.capsule v1.0 (013b7b6e)](013b7b6e.md)
- Need the OS-tier invariant? → OS Invariant #8 in TROPO-CONTROL.md (added v1.25.0 Stream D)
- Need the architectural reasoning? → [Import Primitive Architecture Specification v1.0 (2b49ba79)](2b49ba79.md)

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-05-13 | **LOCKED.** Initial definition. Authored in v1.25.0 Stream A per locked arch-spec [2b49ba79](2b49ba79.md) §C.1 + §3.6. Required + optional frontmatter; minimal body convention; 8 governance rules; 11 validation checks (10 enforced + 1 honor-system; three implemented in v1.25.0 Stream E); tier-aware state machine with UID stability across promotion/extraction; Studio shop-signage per agent-read-not-human-read pedagogy. Three-instrument verification: Argus build (this pass) + Stream G gauntlet pending. | argus-a60 |
| 1.1 | 2026-05-14 | **LOCKED amendment.** Additive: new optional `original_styles:` frontmatter field for `.docx` style-extraction-at-import. Schema mirrors arch-spec §3.4 `extracted_styles` structure. Authored in v1.28.0 Stream A per locked arch-spec [5a89297a v0.5](../../vault/files/5a89297a.md) §3.5.5 Amendment 2 + §3.11 item 3. Populated by `import-walker.py create-sidecar` (v1.28.0 amended) via shared library function `extract_office_styles()` at `.tropo/scripts/office_styles.py` (v1.28.0 NEW; also used by `tropo-register-template.py` + `tropo-backfill-styles.py`). Added Validation Check 12 (`check_original_styles_structure`, WARN severity; opportunistic field; implemented at v1.28.0 Stream D). Naming asymmetry with `docx-template.extracted_styles:` is intentional, semantics-driven (preservation context vs template context — closes pre-lock gauntlet RC-2 per arch-spec v0.5 walk Mike-A62 2026-05-14). No breaking changes; pre-v1.1 instances remain valid (field is optional). | argus-a62 |

---

*external-artifact capsule definition | LOCKED v1.1 | UID eedd7034 | v1.0 locked 2026-05-13 by argus-a60 (v1.25.0 Stream A) | v1.1 amendment locked 2026-05-14 by argus-a62 (v1.28.0 Stream A) | three-instrument verification: v1.0 Argus build complete + Stream G gauntlet; v1.1 spec-level pre-lock gauntlet absorbed in arch-spec v0.5; capsule-level verification at v1.28.0 Stream F ship-time gauntlet.*
*"Sidecars are truth. Vault is projection. UIDs survive every transition. The styles that came in get to leave the way they came." (v1.1)*
