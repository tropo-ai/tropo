---
uid: eedd7034
type: capsule-definition
name: external-artifact
title: external-artifact — Capsule Definition v1.4
description: Sidecar truth for adopted files; availability gates mounted body and edge derivation from authoritative mount paths.
extends: core
version: '1.4'
template_enforced_from: '2026-07-13'
template_enforced_from_note: 'ADDED 2026-07-31 per core.capsule v1.9 §Governance Rule 11 (OPTIONAL `template_enforced_from`). Value is the date THIS capsule''s §Template leg was authored, derived from the first commit introducing the ## §Template heading in this file and cross-checked against this capsule''s own changelog/amendment note. Declares the mint-time contract''s start so instances predating the scaffold are not judged against it. One-line enforcement-scope metadata; no schema/enum/state-machine/template change, so no version bump (the extraction_scope sweep precedent).'
supersedes_version: '1.3'
v1_4_amendment_note: 'Additive mounted-content Phase 2, 2026-08-02, implementing corrected brief 811cf6d2: only availability: available text sources behind a verified derived external-artifact projection, adopted mount, and exactly one UID/path-consistent authoritative sidecar populate FTS; all other mounted bodies are empty. Mount-scoped Obsidian wikilinks, including UID-shaped targets, produce mentions edges only from provenance-verified, entries-backed same-mount candidates, with deterministic missing/ambiguous observations. Exact no-follow source bytes and the folder-mount registry are transaction-bound derivation inputs compared with the trusted pre-transaction manifest. Alias additions, changes, and removals atomically rederive all same-mount dependents. Template/body-shape exemption shares the index sidecar-binding decision for available projections or, while offline, requires the adopted registry''s owned UID/hash plus a verified derived tombstone.'
v1_3_amendment_note: 'Additive mounted-content Phase 1 foundation, 2026-08-02: derived projections carry availability {available, unavailable, ambiguous} plus projection_authority: derived-only. Temporary source loss retains the UID/link target but removes source-derived paths, outgoing edges, and body links. No self-describing Markdown, folder notes, wikilinks, source-body FTS, or mount/import semantic changes.'
v1_3_user_lock_provenance: 'Mike explicitly agreed to the mounted-content Phase 1 behavior in the canonical conversation event evt_4927862819e98650_00000003 on 2026-08-02. This records provenance for the v1.3 amendment only; it does not replace or reinterpret historical locked_by: argus-a62 or v1_0_locked_by: argus-a60.'
v1_2_amendment_note: 'v1.1 -> v1.2 amendment 2026-07-13 by talos-t29 per Mike-locked Governed Autonomy S2 dev-spec bba40cd7 (activation 0d9f89bc; committed substrate "Template legs for the top-10 types"). Additive + non-breaking: NEW §Template section (the mint-stamped scaffold) per the Template-Leg Contract v1.0 (b933eafb). Sidecars are normally authored by import-walker.py, not hand-minted -- the leg exists for the manual-override/edge-case path and says so explicitly. No schema, enum, or state-machine change.'
status: locked
state: active
enforced_enums:
  status:
    - active
    - archived
meta_status_rollup:
  in-progress:
    - active
  done:
    - archived
locked_by: argus-a62
locked_at: 2026-05-14
v1_0_locked_by: argus-a60
v1_0_locked_at: 2026-05-13
schema_version: 2
extraction_scope: ship
author: argus
owner: argus
created: 2026-05-13
modified: 2026-08-02
created_by: argus-a60
modified_by: argus-a144
governed_by: 222873b9
aligned_with:
  - 2b49ba79
  - 5a89297a
  - ee814120
applies_to: external-artifact
member_of:
  - c512438b
  - e3cde3f4
tags:
  - capsule-definition
  - external-artifact
  - sidecar
  - import-primitive
  - v1.25.0-stream-a
  - v1.28.0-stream-a
  - original-styles-at-import
subsystem_hub:
  - 8dd772a0
---

# external-artifact — Capsule Definition v1.4

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Vault Schema v2 — Architecture Specification (222873b9)](222873b9.md) |
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

### Derived projection metadata (not sidecar authority)

`vault/files/<uid>.md` and its reflected index row carry two additive fields:

| Field | Type | Constraint |
|---|---|---|
| `availability` | enum | `available` \| `unavailable` \| `ambiguous`. This is transient reachability, separate from lifecycle `status` and explicit `unmount`. |
| `projection_authority` | enum | Literal `derived-only`. A projection is a stable relative-link target, never a source of metadata truth. |

When availability is not `available`, the projection retains identity and human-readable metadata only. Source paths, membership/relations, source links, and source-derived body content are absent until the same sidecar UID is re-found. Existing sidecars remain authoritative and are never rewritten from a projection.

### Mounted body and edge derivation (v1.4)

For a mounted projection, the index resolves content from the folder-mount registry's current root plus the authoritative sidecar under that same mount. In this sidecar-authoritative phase, a source read requires `type: external-artifact`, `projection_authority: derived-only`, canonical projection path `vault/files/<uid>.md`, a registered adopted mount, one authoritative sidecar whose UID equals the record UID, and agreement among the sidecar location, sidecar `source_path`, and any projection `mount_relpath`. The sidecar supplies the relative source path when `mount_relpath` is absent. A projection's absolute `source_path` is advisory and is never an indexing authority. Authored/spoofed records and mismatched sidecar or mount claims produce an empty body, no outgoing edges, and a deterministic `mounted-source-provenance-invalid` observation.

Only a mounted text source with projection and mount availability both equal to `available`, a supported text extension, a source size at or below 4 MiB, and byte-exact valid UTF-8 may populate `entries_fts.body`. Every unavailable, ambiguous, orphaned, missing, unreadable, opaque, or over-bound mounted body is the empty string—never projection boilerplate and never a prior cached body. Reconnect or full freshen derives from the same sidecar UID and restores content without minting.

Mounted text is opened relative to a no-follow mount descriptor. Every path component and the leaf must remain a regular contained object with stable descriptor/directory-entry identity across the bounded read. The exact bytes read once are shared by FTS, wikilink harvesting, and a portable `@mounted-source/<mount_uid>/<uid>` derivation digest; absolute machine paths never enter index rows or provenance. The exact `.tropo-studio/folder-mounts.json` bytes, a path-free `@mounted-registry/<mount_uid>` digest for attribution, and any consumed sidecar metadata are also transaction inputs. Before/after snapshots refuse the whole index transaction when registry or source identity changes concurrently. Incremental freshen and removal additionally compare every current mounted virtual input with the trusted pre-transaction manifest; a change outside mounts rederived in that transaction refuses rather than advancing a seal over stale SQLite.

Alias identity additions, changes, and removals expand an incremental freshen or removal to every surviving mounted record in each affected mount, in the same sealed transaction. Removal captures affected mounts from the pre-removal index union, so ambiguous-to-unique and unique-to-missing transitions are immediate and equal a full rebuild. Only entries-backed projections that pass the same adopted-mount, derived-authority, canonical-path, and authoritative-sidecar provenance checks enter the alias catalog as a source or target. An invalid projection emits its provenance diagnostic but contributes no alias candidate, edge, or ambiguity. Bare aliases retain the union of same-mount UID, stem, and title candidates; explicit paths retain all same-mount path candidates. Exactly one candidate produces an edge, more than one is ambiguous, and zero is missing. No precedence rule may turn a retained collision into a unique match.

Obsidian wikilinks in an eligible mounted text body resolve only within that source's `mount_uid`. Explicit mount-relative paths take precedence; bare links resolve by filename stem, then by title only when unique. `[[target]]`, `[[target|label]]`, and `[[target#heading|label]]` share the same target resolution. A unique result emits a `mentions` edge. Missing and ambiguous results emit deterministic `wikilink-alias-missing` or `wikilink-alias-ambiguous` rows in SQLite `index_observations`; they emit no graph edge, never pick the first candidate, never mint, and never cross mounts. Losing source availability removes body-derived edges and observations on the next freshen.

Mounted/adopted derived projections are exempt only from the live template/body-shape validator leg because their body is a generated link stub or an external source, not a minted Studio template instance. An available projection must pass the same shared binding decision as index source reads: exactly one matching authoritative same-UID sidecar under an adopted registered mount. Duplicate same-UID sidecars are ambiguous and deny exemption. An unavailable or ambiguous tombstone may instead rely on the adopted registry's recorded projection UID and projection hash plus a verified source-free derived stub. Attached, unregistered, invalid/duplicate-sidecar, authored, and spoofed projections are not exempt and emit a mounted-projection provenance finding before normal template checks continue. UID, duplicate, provenance, capsule, index-union, and all other structural validation remain in force.

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
4. **Vault projection is derived; never authoritative.** `vault/files/<uid>.md` (Tier 1) or `vault/files/<uid>/metadata.md` (Tier 2) is regenerated in full from this sidecar through the canonical writer. Partial frontmatter repair is forbidden. A differing hand-edited projection is replaced and explicitly reported as repaired/tampered. Per OS Invariant #8, anything that exists only in the projection and not in the sidecar is data Tropo can lose.
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
13. **[enforced at mounted-folder reconcile; v1.3]** Projection and index availability agree. An unavailable/ambiguous projection retains its UID but contains no source path, source link, membership/relations, or source-derived body edge. Re-finding the sidecar restores `available` on the same UID.
14. **[enforced at index derivation; v1.4]** Mounted FTS and body-derived edges resolve through authoritative mount metadata and are availability-gated. Non-available or unreadable sources produce an empty FTS body and no source-derived outgoing edges.
15. **[enforced at index derivation; v1.4]** Wikilinks—including `[[8hex]]`—resolve from retained candidate sets of provenance-verified, entries-backed projections within one mount or produce a named deterministic observation with sorted candidates and no edge. Invalid projections are neither alias source nor target and cannot create ambiguity. Cross-mount, global-UID, and first-candidate fallback are forbidden. Alias-changing incrementals atomically rederive every mounted record in affected mounts.
16. **[enforced at live template validation; v1.4]** Template/body-shape exemption requires a canonical `type: external-artifact`, `projection_authority: derived-only` stub owned by a registered adopted mount. Available projections use the indexer's shared binding verifier and require exactly one matching same-UID authoritative sidecar plus a consistent mount-relative path; duplicate same-UID candidates are ambiguous. Unavailable/ambiguous tombstones require the UID and exact projection hash in registry ownership plus a verified source-free stub. Attached, unknown, invalid/duplicate-sidecar, authored, mounted-note, and spoofed projections emit a provenance finding and remain checked. No structural validator exemption follows from this rule.
17. **[enforced at index derivation; v1.4]** The folder-mount registry and exact no-follow regular-file bytes consumed for mounted FTS/edges are transaction-bound manifest inputs under portable names. Incremental and removal writes compare current mounted virtuals with the trusted pre-transaction manifest and refuse changes outside every mount rederived by that transaction. Concurrent registry/source changes, symlinks, special files, path swaps, and over-4-MiB bodies fail closed without a partial index write or stale certification.
18. **[enforced at index derivation; v1.4]** Mounted source reads and aliases require a canonical derived `external-artifact` projection bound to one same-UID authoritative sidecar in a registered adopted mount, with sidecar location/source path and projection mount-relative path consistent. Unverified rows contribute no body or outgoing edge and emit a named provenance observation. Removing a mounted projection captures its mount from the pre-removal union and atomically rederives every surviving same-mount row, FTS body, edge, and observation under the same index seal.

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
- **Temporary source loss (v1.3):** keep the projection and UID as an unavailable link target; remove source-derived outgoing edges. Re-find restores the same UID. Explicit user `unmount` keeps its separate recycle-and-forget behavior.
- **Mounted body search (v1.4):** available mounted UTF-8 text bodies are indexed from authoritative mount metadata. Offline and unreadable states replace the FTS body with empty text; restore repopulates it under the same UID.
- **Mounted wikilinks (v1.4):** unique same-mount aliases, including UID-shaped aliases, become `mentions`; complete sorted candidate collisions and missing aliases remain observations only. Alias changes rederive the affected mount atomically.
- **Still out of scope:** self-describing Markdown, folder notes, and mount/import transitions.

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

## §Template (v1.2 — the mint-stamped scaffold; contract at [b933eafb](../../vault/files/b933eafb.md))

*Stamped verbatim by `mint file --type external-artifact` (S2, bba40cd7); `<<MINT:*>>` tokens are the only substitution. **This type is normally authored by `import-walker.py`, not hand-minted** — this leg exists for the manual-override/edge-case path, not the primary creation mechanism (say so to anyone reaching for it). This capsule uses `status:` (not `state:`) as its active/archived lifecycle flag — a real divergence from the other nine legged types, confirmed against this capsule's own core-inherited-fields sentence and State Machine. `governance: tier-1-sidecar` is the sole legal birth value (the State Machine's only entry transition). The five source-* fields are normally computed by import-walker.py from a real file on disk; a manual mint has no file to compute them from, so they're REQUIRED placeholders here, not defaults.*

~~~markdown
---
uid: <<MINT:uid>>
type: external-artifact
title: "<!-- REQUIRED: title -->"
source_filename: "<!-- REQUIRED: original filename -->"
source_path: "<!-- REQUIRED: relative path to source, e.g. ../<filename> for Tier 1 -->"
original_path: "<!-- REQUIRED: path to source when first imported, relative to Studio root -->"
source_size_bytes: "<!-- REQUIRED: source file size in bytes at last reconciliation -->"
source_mtime: "<!-- REQUIRED: source file mtime, ISO 8601 -->"
source_hash: "<!-- REQUIRED: hash of the source per hash_function below -->"
hash_function: "<!-- REQUIRED: one of stable-id | content-aware | sha256 -->"
governance: tier-1-sidecar
owner: <<MINT:author>>
status: active
member_of:
  - "<!-- REQUIRED: the immediate parent folder-project UID -->"
schema_version: 1
created: '<<MINT:date>>'
modified: '<<MINT:date>>'
capsule_version: '<<MINT:capsule_version>>'
governed_by: 8dd772a0
---

# <!-- REQUIRED: title --> — Tropo Sidecar

Governs `<!-- REQUIRED: source_path (mirror frontmatter) -->` in folder-project `<!-- REQUIRED: member_of uid (mirror frontmatter) -->`.
Vault projection at `vault/files/<<MINT:uid>>.md` (Tier 1) or `vault/files/<<MINT:uid>>/metadata.md` (Tier 2).
~~~

**Leg rules:** `schema_version: 1` here is this type's own sidecar-schema version — NOT the generic vault-entry `schema_version: 2` convention every other legged type uses; don't "fix" it to 2. Prefer `import-walker.py` for real imports; use this scaffold only for a genuine manual/edge-case sidecar, and expect to hand-verify the source-* fields against the real file since nothing computed them.

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.4 | 2026-08-02 | **Mounted-content Phase 2.** Availability-gated source-body FTS from authoritative mount metadata; exact empty-body fail-closed behavior; same-mount wikilink aliases with unique-edge/missing-or-ambiguous-observation outcomes; template/body-shape-only projection exemption. Preserves the v1.3 derived-stub contract and user-lock provenance unchanged. | cursor-phase2 |
| 1.3 | 2026-08-02 | **Mounted-content Phase 1 additive foundation.** Adds derived projection metadata `availability` + `projection_authority`; temporary source loss retains stable UIDs while removing stale source-derived edges; full deterministic regeneration replaces partial repair; orphan sidecars are named nonzero residuals. Existing sidecars remain authoritative. Explicit unmount is unchanged. Documents the no-source-body-index precondition and defers self-describing Markdown, folder notes, wikilinks, body FTS, and mount/import semantics. | cursor-phase1 |
| 1.0 | 2026-05-13 | **LOCKED.** Initial definition. Authored in v1.25.0 Stream A per locked arch-spec [2b49ba79](2b49ba79.md) §C.1 + §3.6. Required + optional frontmatter; minimal body convention; 8 governance rules; 11 validation checks (10 enforced + 1 honor-system; three implemented in v1.25.0 Stream E); tier-aware state machine with UID stability across promotion/extraction; Studio shop-signage per agent-read-not-human-read pedagogy. Three-instrument verification: Argus build (this pass) + Stream G gauntlet pending. | argus-a60 |
| 1.1 | 2026-05-14 | **LOCKED amendment.** Additive: new optional `original_styles:` frontmatter field for `.docx` style-extraction-at-import. Schema mirrors arch-spec §3.4 `extracted_styles` structure. Authored in v1.28.0 Stream A per locked arch-spec [5a89297a v0.5](../../vault/files/5a89297a.md) §3.5.5 Amendment 2 + §3.11 item 3. Populated by `import-walker.py create-sidecar` (v1.28.0 amended) via shared library function `extract_office_styles()` at `.tropo/scripts/office_styles.py` (v1.28.0 NEW; also used by `tropo-register-template.py` + `tropo-backfill-styles.py`). Added Validation Check 12 (`check_original_styles_structure`, WARN severity; opportunistic field; implemented at v1.28.0 Stream D). Naming asymmetry with `docx-template.extracted_styles:` is intentional, semantics-driven (preservation context vs template context — closes pre-lock gauntlet RC-2 per arch-spec v0.5 walk Mike-A62 2026-05-14). No breaking changes; pre-v1.1 instances remain valid (field is optional). | argus-a62 |
| 1.2 | 2026-07-13 | **Governed Autonomy S2** ([bba40cd7](../../vault/files/bba40cd7.md)) — NEW §Template leg per the Template-Leg Contract v1.0 ([b933eafb](../../vault/files/b933eafb.md)). `mint file --type external-artifact` stamps a manual/edge-case scaffold at `governance: tier-1-sidecar`, `status: active` — the primary creation path remains `import-walker.py`. Additive; no schema/enum/state-machine change. | talos-t29 |

---

*external-artifact capsule definition | LOCKED v1.4 | UID eedd7034 | v1.0 locked 2026-05-13 by argus-a60 | v1.1 amended 2026-05-14 by argus-a62 | v1.2 template leg 2026-07-13 | v1.3 mounted-content availability foundation 2026-08-02 | v1.4 mounted-content body/edge derivation 2026-08-02.*
*"Sidecars are truth. Vault is projection. UIDs survive every transition."*
