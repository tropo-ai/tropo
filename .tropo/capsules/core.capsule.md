---
uid: ee814120
name: "core"
type: capsule-definition
extends: null
version: 1.6
tier: os
author: tropo
created: 2026-04-10
modified: 2026-06-09
modified_by: argus-a104
v1_6_lock_break: "v1.5 → v1.6 lock-break Mike-authorized 2026-06-09 (Option A + 'push'). Adds the canonical `state` field declaration to Optional Frontmatter — the universal 2-value visibility flag {active, archived}, the result of the state DISAMBIGUATE (99e52c18, move 3 of the lifecycle knot 9f6a1379). Purely additive (documents the migrated reality — 51 entries migrated to state∈{active,archived}, 0 violations; the universal validator check d2b9c8e6.py:3021 already enforces it at WARN). prior modified argus-a99 2026-06-05."
status: locked
locked_at: 2026-06-05
locked_by: argus-a99
v1_4_lock_break: "v1.3 -> v1.4 lock-break Mike-A99-signed 2026-06-05 (verbatim 'consider it signed'). Extends enforced_enums to accept the {canonical, aliases} dict form (SKOS canon+alias per doctrine 1573867b) alongside the list form (backward-compatible; list-form capsules unaffected). The validator (c4512bdc Piece 1, built + verified this cycle) three-way classifies each entry value (case-folded): canonical=PASS, alias=NORMALIZABLE (a groomer work-item; separate counter; does NOT touch warnings/fails/exit), unknown=WARN. state alias maps are REJECTED (state is a DISAMBIGUATE target, not a synonym-fold target). Unrecognized enum shapes ERROR. Purely additive. Implements c4512bdc (the alias-map + groomer machinery)."
v1_3_lock_break: "v1.2 -> v1.3 lock-break Mike-A98-signed 2026-06-04 (verbatim 'go'). Adds the OPTIONAL enforced_enums frontmatter field -- the slot for a type capsule to declare its own enforced field-vocabularies (status/state). Purely additive: no existing required field, rule, or check changed; descendants that omit enforced_enums are unaffected. Implements the ENFORCE step of the Field-Semantics Map (476fef2e) per design-spec addc4490 v0.5 (enforce-first, task pilot). Companion lock-break: task.capsule (3289712a) populates the block."
aligned_with:
  - "57a9c11f"   # HUMAN-NAVIGATION.md (P0 OS-tier primitive, draft pending Mike signature)
  - "db0fd9b1"   # SELF-HEALING.md (P0 OS-tier primitive, sibling)
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# core — Capsule Definition

**Relations**

| Relation | Target |
|---|---|
| Extends | `null` |

*The root capsule definition. Every other capsule type inherits from `core`. Its rules are universal invariants — no descendant can remove or override them.*

## Intent

Establish the universal frontmatter and ownership rules that every governed entry in the Vault must satisfy. This is the schema floor — the minimum any entry must meet to exist in the Vault.

## Required Frontmatter

Every entry MUST have:

| Field | Type | Constraint |
|-------|------|-----------|
| `uid` | string | exactly 8 lowercase hex characters; unique across the Vault |
| `type` | string | one of the registered capsule types |
| `status` | string | valid for the type's state machine |
| `title` | string | ≤ 100 characters; no newlines/tabs/control chars; **human-readable display-name** (see §Title Semantics below) |
| `owner` | string | known agent or human identifier; ≤ 30 characters |
| `created` | string | ISO 8601 date (YYYY-MM-DD); immutable |
| `modified` | string | ISO 8601 date (YYYY-MM-DD); ≥ created |

## Optional Frontmatter (v1.3 amendment 2026-06-04)

A type capsule MAY declare these; entries and descendants that omit them are unaffected (purely additive).

| Field | Type | Constraint |
|-------|------|-----------|
| `state` | enum | OPTIONAL **universal visibility flag** — exactly one of `active` (the live/current reference) or `archived` (filed away). **Nothing else.** This is the canonical 2-value result of the `state` DISAMBIGUATE (move 3 of the lifecycle knot [9f6a1379]; spec [99e52c18]; Mike decision Option A 2026-06-09). `state` is NOT lifecycle-position (that is `status`, per-type-rich) and NOT kind-over-time (that is `lifecycle`: standing/versioned/…). Provenance is the kept `archived_at`/`archived_by` annotation; genuine supersession is the separate `superseded_by:`. Enforced **universally** by the validator state-enum check (`d2b9c8e6.py` — WARN now, ERROR-ratchet next cycle once a clean cycle confirms no new drift). The pipeline runtime no longer writes `state:done` (completion is `status`, per the 99e52c18 engine fix). |
| `enforced_enums` | map | OPTIONAL, declared on a **type capsule's** frontmatter. Maps a field name (`status`, `state`) to the legal values for that type. When present it is the **single enforced source** for that field's vocabulary: the validator reads it straight from the capsule (no derived registry) and classifies any entry of that type's raw frontmatter value. Two forms (v1.4): **(a) list form** — `status: [new, accepted, active, closed]` (canonical only); a value outside the list WARNs. **(b) `{canonical, aliases}` dict form (v1.4, SKOS canon+alias)** — `status: {canonical: [new, active, done], aliases: {closed: done, open: new}}`; canonical values PASS, **alias values are NORMALIZABLE** (recognized, not a WARN — a groomer normalizes them to canon, non-breaking per the gradual-typing tighten-only guarantee), and only genuinely-unknown values WARN. `state` may use the list form ONLY (aliases rejected — `state` is a DISAMBIGUATE target, not a synonym-fold target). An unrecognized shape ERRORs (never silent-skips). The capsule's prose enum line and the block are kept in agreement by a coherence check. See §Governance Rule 8 + Validation Check 10. |
| `subsystem_hub` | list[string] | OPTIONAL core field **(v1.5; member_of DISAMBIGUATE)**. UIDs each resolving to an entry that carries `subsystem_name:` (a subsystem hub). Carries an entry's **subsystem membership** — the cross-cutting "what subsystem(s) does this belong to" tags. **Distinct from `member_of:`, which is the entry's true organizational PARENT (non-hub).** The two were historically conflated in `member_of`; the v2.5 project split + this core field finish the disambiguation fleet-wide. Rendered as a parent/nav edge alongside `member_of`. See §Governance Rule 9. |

## Title Semantics (v1.2 amendment 2026-05-15)

The `title:` field carries the entry's **human-readable display-name**. It is the surface text that appears wherever the entry is referenced in a rendered context — in another entry's `📥 Cited by` section, in a Navigation block breadcrumb, in a channel post citation, in a chat message link.

`title:` is distinct from `name:` (which is the structured machine-name; used by tooling, registries, agent slugs). Both fields may be present; `name:` is structured (e.g., `vela-v45`, `tropo-os-release`), `title:` is readable (e.g., `"Vela V45 — Activation Entry"`, `"Tropo-OS v1.27.0 — Dev-Pipeline Enforcement Hardening"`).

When an entry is referenced from another entry's rendered Navigation block, the display surface is `title:`. If `title:` is absent, the renderer falls back to `name:`, then to the bare UID — both of which fail the [HUMAN-NAVIGATION.md (57a9c11f)](../HUMAN-NAVIGATION.md) primitive's readable-name-first contract. Authors MUST populate `title:` for every governed entry.

## Navigation Block Render Obligation (v1.2 amendment 2026-05-15)

Every governed vault entry's rendered body MUST contain a sentinel-wrapped Navigation block at the top, immediately after the H1 title. The block is authored by [`.tropo/scripts/generate-relations-header.py`](../scripts/generate-relations-header.py) during the canonical render pass (Step 4/4 of `rebuild-vault.py`). Agents do not hand-author the block; the renderer produces it from frontmatter + graph state.

The block carries five sections per [HUMAN-NAVIGATION.md (57a9c11f)](../HUMAN-NAVIGATION.md): 📍 Path / 🔗 Self / ↓ Children / ↔ Siblings / 📥 Cited by. Sentinels (`<!-- nav-block:start --> ... <!-- nav-block:end -->`) make the block idempotently replaceable.

**Skip-class:** entries without an H1 title (pre-frontmatter legacy, README-class meta-files) skip Navigation block rendering by design. The validator (Check 9 below) honors this skip-class.

## Governance Rules

1. **UID uniqueness.** No two entries may share a UID. UIDs are never reused.
2. **UID immutability.** A UID, once assigned, never changes.
3. **Ownership.** Every entry has exactly one owner at any time. Ownership transfers require the prior owner's consent (or vault principal override).
4. **Type immutability.** An entry's type is set at creation and does not change. To "convert" an entry to a different type, archive the original and create a new entry.
5. **Created date immutability.** The `created` date is set once and never changes.
6. **Title required.** `title:` (display-name) is required per §Required Frontmatter above. Missing or empty `title:` is a substrate defect (Validation Check 5 + Check 9).
7. **Navigation block render obligation.** Every governed entry with frontmatter + H1 MUST carry a sentinel-wrapped Navigation block per §Navigation Block Render Obligation above.
8. **Enforced enums are the capsule's single source (v1.3; alias form v1.4).** A type capsule MAY declare `enforced_enums:` in frontmatter. When present, the validator reads the legal value-set directly from the capsule (no derived registry, no staleness) and enforces every entry of that type against it; the capsule body's canonical prose enum line and the `enforced_enums:` block MUST agree (coherence check). The capsule becomes the enforced single source of truth for its own field vocabularies. **(v1.4)** The block may declare per-field `aliases` (the `{canonical, aliases}` form): the validator recognizes alias values as NORMALIZABLE (non-breaking; a groomer normalizes them to canon) and WARNs only genuinely-unknown values — the gradual-typing tighten-only guarantee. `state` aliases are rejected; unrecognized shapes ERROR.
9. **`member_of` = parent; `subsystem_hub` = subsystem (v1.5; member_of DISAMBIGUATE).** `member_of:` is the entry's true organizational PARENT (the project/collection it lives under) and MUST NOT carry subsystem-hub UIDs (a hub = an entry with `subsystem_name:`). Subsystem membership lives in the separate `subsystem_hub:` core field. Type capsules that historically required/carried a hub in `member_of:` are reconciled to require it in `subsystem_hub:` (kb-article, governance-contract, registry, charter, capsule-history, docx-template, events; + the release/release-plan derivation walks `subsystem_hub`). Enforced by `check_no_hub_uids_in_member_of` (Check 11, un-gated). Per [member_of DISAMBIGUATE (6f5bb2cb)](../../vault/files/6f5bb2cb.md); Mike-A100-signed lock-break.

## Validation Checks (run at check-in)

1. UID matches `^[0-9a-f]{8}$`
2. UID is not already in use by a different file
3. Type is in the registered capsule types
4. Status is valid for the type's state machine (delegated to type-specific definition)
5. **Title present (non-empty), length ≤ 100 chars; no forbidden characters** *(v1.2 amendment — enforcement at WARN; ratchet to ERROR after migration substrate is clean)*
6. Owner is a known identifier; length ≤ 30 chars
7. Created and modified are valid ISO 8601 dates
8. modified ≥ created
9. **Navigation block render safety** *(v1.2 amendment, NEW)* — entries with frontmatter + H1 MUST have a sentinel-wrapped Navigation block in body. WARN at v1.X; ERROR ratchet planned. Implemented via `check_navigation_block_render_safety()` in `tropo-validate.py`.
10. **Enforced-enum compliance** *(v1.3; three-way v1.4)* — for any type whose capsule declares `enforced_enums`, each entry's raw frontmatter `status`/`state` is classified (case-folded): **canonical = PASS; alias (dict form) = NORMALIZABLE** (a separate counter — NOT a WARN; does not touch warnings/fails/exit; a groomer normalizes it to canon); **unknown = WARN** (ratchet to ERROR per-field when that field's true-drift reaches zero). An unrecognized `enforced_enums` shape ERRORs. Reads the block + the entry via `yaml.safe_load` in `d2b9c8e6.py` (c4512bdc Piece 1). Companion coherence check: the `enforced_enums` block's canonical values match the capsule's prose enum line (backtick-colon anchor `` `status:` ∈ `` / `` `state:` ∈ ``).

## Inheritance

`core` is the root. It has no parent. All other capsule definitions extend `core` and inherit its rules.

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.5 | 2026-06-05 | `subsystem_hub:` added as a core optional field + Governance Rule 9: `member_of` = true organizational parent, `subsystem_hub` = subsystem membership (the two were conflated in `member_of`). Finishes the v2.5 project split fleet-wide. Purely additive (subsystem_hub optional; member_of semantics clarified, not changed). Mike-A100-signed lock-break; implements member_of DISAMBIGUATE (6f5bb2cb). | argus-a100 |
| 1.4 | 2026-06-05 | `enforced_enums` extended to the `{canonical, aliases}` dict form (SKOS canon+alias). Validator three-way classifies: canonical=PASS / alias=NORMALIZABLE (separate counter, non-breaking) / unknown=WARN; `state` aliases rejected; unrecognized shapes ERROR. Backward-compatible (list form unaffected). Mike-A99-signed lock-break; implements c4512bdc (alias-map machinery; Piece 1 built + verified). | argus-a99 |
| 1.3 | 2026-06-04 | Optional `enforced_enums:` frontmatter slot added (the ENFORCE-step primitive: a type capsule declares its own enforced status/state vocabularies; validator reads them straight from the capsule, no registry). +1 governance rule (8), +1 validation check (10), +1 optional-frontmatter section. Purely additive. Mike-A98-signed lock-break; implements addc4490 v0.5 (enforce-first, task pilot). | argus-a98 |
| 1.2 | 2026-05-15 | Title semantics clarified (display-name; distinct from `name:`); Navigation block render obligation added (per HUMAN-NAVIGATION.md primitive); 2 new governance rules + 2 new/expanded validation checks (Check 5 enforcement WARN; Check 9 NEW). Aligned-with HUMAN-NAVIGATION (`57a9c11f`) + SELF-HEALING (`db0fd9b1`). | vela-v45 |
| 1.1 | 2026-04-14 | Field name: `modified` (was `last_modified` — errata April 13, 2026) | vela-v28 |
| 1.0 | 2026-04-10 | Initial locked definition | tropo |

---

*core capsule definition | LOCKED v1.5 | Tropo OS | v1.0 Apr 10 → v1.2 May 15 → v1.3/v1.4 Jun 4-5 → v1.5 Jun 5, 2026 (member_of=parent / subsystem_hub=subsystem split)*
*"The schema floor every governed entry stands on. Title is the human handle; Navigation block is the human surface; enforced_enums is the capsule enforcing its own vocabulary."*
