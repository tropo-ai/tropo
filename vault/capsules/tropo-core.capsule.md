---
uid: ee814120
name: core
type: capsule-definition
extends: null
version: 2.0
tier: os
author: tropo
created: 2026-04-10
modified: 2026-08-03
modified_by: argus-a144
v2_0_amendment_note: "Mike-approved typed-mint pilot, 2026-08-03. Defines one narrow, explicit subtype-specialization mechanism so a descendant capsule may override only named core fields in `core_field_specializations`. This records existing note/task contracts rather than forcing invented title/status/owner values into legal births. Undeclared omissions remain defects; no instance migration is implied."
v1_9_lock_break: "v1.8 → v1.9. Adds the OPTIONAL `template_enforced_from:` field (§Optional Frontmatter) + §Governance Rule 11: a capsule carrying a `## §Template` leg declares the date that leg was authored, and the generic instance verifier grandfathers entries created on or before it for section presence. Purely additive: absent is legal; no existing required field, rule, enum, or check changes; no instance is modified. Follows the `enforced_enums` idiom exactly — the capsule declares, the validator reads it straight from the capsule, no derived registry and no runtime git dependency. Written because the Live Template + Body Shape check applied a MINT-TIME contract retroactively: every §Template leg in this vault was authored 2026-07-12..07-18 against a corpus months older, producing 1,089 MISSING-SECTION findings across 363 entries that could not have been minted from the scaffold they were judged against. The pre-existing corpus is on the protect list of the Mike-walked program brief b600698e §6 ('they gain template/verifier legs, nothing migrates') and historical migration is explicitly OUT of scope in S2 (bba40cd7)."
current_amendment_authority: a286c210
current_amendment_locked_by: mike-maziarz
current_amendment_locked_at: 2026-07-12
v1_7_lock_break: "v1.6 → v1.7 lock-break under Mike-locked Gardener Pruning dev-spec a286c210 (locked 2026-07-12; committed_substrate explicitly AMENDS vault/capsules/ and assigns the pruning block contract to Argus). Adds the OPTIONAL universal pruning block: an evidence-carrying, body-version-keyed, human-overridable valid-time verdict for governed Markdown bodies. Purely additive: absent is legal; no existing instance changes; mint templates remain untouched. Defines locator/hash/override/staleness semantics before the canonical writer + validator land."
v1_6_lock_break: v1.5 → v1.6 lock-break Mike-authorized 2026-06-09 (Option A + 'push'). Adds the canonical `state` field declaration to Optional Frontmatter — the universal 2-value visibility flag {active, archived}, the result of the state DISAMBIGUATE (99e52c18, move 3 of the lifecycle knot 9f6a1379). Purely additive (documents the migrated reality — 51 entries migrated to state∈{active,archived}, 0 violations; the universal validator check d2b9c8e6.py:3021 already enforces it at WARN). prior modified argus-a99 2026-06-05.
status: locked
locked_at: 2026-06-05
locked_by: argus-a99
v1_4_lock_break: 'v1.3 -> v1.4 lock-break Mike-A99-signed 2026-06-05 (verbatim ''consider it signed''). Extends enforced_enums to accept the {canonical, aliases} dict form (SKOS canon+alias per doctrine 1573867b) alongside the list form (backward-compatible; list-form capsules unaffected). The validator (c4512bdc Piece 1, built + verified this cycle) three-way classifies each entry value (case-folded): canonical=PASS, alias=NORMALIZABLE (a groomer work-item; separate counter; does NOT touch warnings/fails/exit), unknown=WARN. state alias maps are REJECTED (state is a DISAMBIGUATE target, not a synonym-fold target). Unrecognized enum shapes ERROR. Purely additive. Implements c4512bdc (the alias-map + groomer machinery).'
v1_3_lock_break: 'v1.2 -> v1.3 lock-break Mike-A98-signed 2026-06-04 (verbatim ''go''). Adds the OPTIONAL enforced_enums frontmatter field -- the slot for a type capsule to declare its own enforced field-vocabularies (status/state). Purely additive: no existing required field, rule, or check changed; descendants that omit enforced_enums are unaffected. Implements the ENFORCE step of the Field-Semantics Map (476fef2e) per design-spec addc4490 v0.5 (enforce-first, task pilot). Companion lock-break: task.capsule (3289712a) populates the block.'
aligned_with:
  - 57a9c11f
  - db0fd9b1
subsystem_hub:
  - 8dd772a0
---

# core — Capsule Definition

**Relations**

| Relation | Target |
|---|---|
| Extends | `null` |

*The root capsule definition. Every other capsule type inherits from `core`.
Its fields are the default floor; a descendant may specialize only the exact
fields it declares under the narrow subtype-specialization contract below.*

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

### Explicit Subtype Specializations

A subtype may narrow or relax a core field only when its capsule declares the
exception in `core_field_specializations` and explains the same exception in
its schema. An undeclared omission remains a core defect. This is a bounded
inheritance escape hatch, not permission for validators to infer exceptions.

The currently declared exceptions are exhaustive:

- `note`: `title`, `status`, and `owner` are optional. A minimal capture may use
  its body and `captured_by` without inventing work-lifecycle/accountability
  fields.
- `task`: `owner` is optional until acceptance, and `title` specializes the
  maximum length from 100 to 120 characters.

No existing instance migration follows from these declarations.

## Optional Frontmatter (v1.3 amendment 2026-06-04)

A type capsule MAY declare these; entries and descendants that omit them are unaffected (purely additive).

| Field | Type | Constraint |
|-------|------|-----------|
| `state` | enum | OPTIONAL **universal visibility flag** — exactly one of `active` (the live/current reference) or `archived` (filed away). **Nothing else.** This is the canonical 2-value result of the `state` DISAMBIGUATE (move 3 of the lifecycle knot [9f6a1379]; spec [99e52c18]; Mike decision Option A 2026-06-09). `state` is NOT lifecycle-position (that is `status`, per-type-rich) and NOT kind-over-time (that is `lifecycle`: standing/versioned/…). Provenance is the kept `archived_at`/`archived_by` annotation; genuine supersession is the separate `superseded_by:`. Enforced **universally** by the validator state-enum check (`d2b9c8e6.py` — WARN now, ERROR-ratchet next cycle once a clean cycle confirms no new drift). The pipeline runtime no longer writes `state:done` (completion is `status`, per the 99e52c18 engine fix). |
| `enforced_enums` | map | OPTIONAL, declared on a **type capsule's** frontmatter. Maps a field name (`status`, `state`) to the legal values for that type. When present it is the **single enforced source** for that field's vocabulary: the validator reads it straight from the capsule (no derived registry) and classifies any entry of that type's raw frontmatter value. Two forms (v1.4): **(a) list form** — `status: [new, accepted, active, closed]` (canonical only); a value outside the list WARNs. **(b) `{canonical, aliases}` dict form (v1.4, SKOS canon+alias)** — `status: {canonical: [new, active, done], aliases: {closed: done, open: new}}`; canonical values PASS, **alias values are NORMALIZABLE** (recognized, not a WARN — a groomer normalizes them to canon, non-breaking per the gradual-typing tighten-only guarantee), and only genuinely-unknown values WARN. `state` may use the list form ONLY (aliases rejected — `state` is a DISAMBIGUATE target, not a synonym-fold target). An unrecognized shape ERRORs (never silent-skips). The capsule's prose enum line and the block are kept in agreement by a coherence check. See §Governance Rule 8 + Validation Check 10. |
| `subsystem_hub` | list[string] | OPTIONAL core field **(v1.5; member_of DISAMBIGUATE)**. UIDs each resolving to an entry that carries `subsystem_name:` (a subsystem hub). Carries an entry's **subsystem membership** — the cross-cutting "what subsystem(s) does this belong to" tags. **Distinct from `member_of:`, which is the entry's true organizational PARENT (non-hub).** The two were historically conflated in `member_of`; the v2.5 project split + this core field finish the disambiguation fleet-wide. Rendered as a parent/nav edge alongside `member_of`. See §Governance Rule 9. |
| `template_enforced_from` | string | OPTIONAL, declared on a **type capsule's** frontmatter; legal only on a capsule that carries a `## §Template` leg. ISO 8601 date (YYYY-MM-DD) recording **when that capsule's §Template leg was authored** — the day the scaffold first existed to be minted from. The §Template leg is a MINT-TIME contract (it describes what `mint file` stamps), so its section-presence obligation can only bind instances that could have been minted from it. An entry whose `created` date is **on or before** this date is **grandfathered**: the generic instance verifier does not report MISSING-SECTION against it. (On-or-before, not strictly-before: the declaration has one-day granularity, so a same-day entry cannot be shown to have had the scaffold available — enforcement begins the day after.) Grandfathering is narrow by construction — it suppresses section presence only; a grandfathered entry remains subject to every other check, including placeholder survival, stray mint tokens, enum compliance, and the whole core floor. Read straight from the capsule like `enforced_enums`: **no derived registry, no runtime `git` dependency** (a shipped customer studio has no git history to re-derive from). A capsule carrying a leg but no `template_enforced_from` cannot date its own scaffold, so section-presence enforcement is inert for that type and the verifier says so at WARN rather than guessing. Per the protect list in the Governed Autonomy program brief ([b600698e](../files/b600698e.md) §6, "they gain template/verifier legs, nothing migrates") and S2's scope boundary ([bba40cd7](../files/bba40cd7.md), historical migration explicitly OUT). |
| `pruning` | map | OPTIONAL universal valid-time verdict for a governed Markdown body's current normalized content version. Absent is legal and means “no body-grain verdict.” When present it MUST conform to §Pruning Block Contract. Every machine stamp and human override uses the same canonical locked writer; it is never scaffolded by a type's mint template. Distinct from derived-only `decay.*` and from intrinsic lifecycle `status`/visibility `state`. |

## Pruning Block Contract (v1.7 amendment 2026-07-17)

The Mike-locked [Gardener Pruning dev-spec](../files/a286c210.md) establishes a body-grain valid-time channel: a model may propose that a governed Markdown body is `finished`, `superseded`, or `abandoned` even while its intrinsic lifecycle fields remain active. The verdict is source frontmatter because it must travel with the file; evidence and body-version keys make it contestable and mechanically staleable.

```yaml
pruning:
  verdict: finished | superseded | abandoned
  evidence_span: "<verbatim UTF-8 source text>"
  evidence_locator:
    body_sha256: "<64 lowercase hex — T1 raw post-fence body hash>"
    start_byte: 0
    end_byte: 0
  judge_policy_uid: "<8-hex UID of the active Gardener Pruning body-judge loop>"
  judge_version: "<non-empty judge/model package identifier>"
  judge_prompt_sha256: "<64 lowercase hex, or null when the judge has no prompt>"
  origin_studio: "<8-hex UID of the studio that produced this verdict>"
  judged_at: "<ISO 8601 datetime>"
  confidence: 0.0
  normalized_body_hash_judged: "<64 lowercase hex — T2 normalized-content hash>"
  override:                         # optional; human-authored only
    action: keep
    by: "<8-hex principal UID resolving to principal_class: human>"
    at: "<timezone-aware ISO 8601 datetime>"
    reason: "<non-empty rationale>"
```

### Field semantics

1. **Closed shape.** `pruning` and its nested mappings accept only the keys declared above. Required strings are trimmed and non-empty. Both hash fields are exactly 64 lowercase hexadecimal characters.
2. **Applicability.** The block applies only to governed Markdown files with an unambiguous YAML frontmatter fence and post-fence body. Python, JSON/JSONL, binary payloads, and files without that boundary are not pruning-eligible.
3. **Canonical transforms.** T1 and T2 mean exactly the transforms in [The Three Text Transforms](../files/132fb547.md). T1 hashes post-fence bytes after collapsing trailing newlines to exactly one. T2 strips nav blocks, decodes UTF-8 with replacement, NFC-normalizes, folds line endings/trailing whitespace, and emits exactly one trailing newline before hashing.
4. **Evidence is mandatory.** `evidence_span` is non-empty, strict UTF-8 text copied verbatim from the judged body's raw post-fence bytes. Generated nav-block regions are never eligible evidence. Invalid UTF-8 remains legal T2 input but cannot be cited as evidence.
5. **Locator is byte-exact.** `start_byte` and `end_byte` are integers but not booleans, with `0 <= start_byte < end_byte <= raw_body_length`. They are zero-based, half-open offsets into raw on-disk post-fence body bytes from the single judgment read. The addressed bytes MUST strict-decode to exactly `evidence_span`; `body_sha256` is T1 from that read.
6. **Provenance is typed.** `judge_policy_uid` is 8-hex and resolves in the current index to the one active `type: loop` entry implementing the `gardener-body-judge` committed substrate. That loop is the long-lived policy surface used by both first sweep and steady state; it carries the authoritative `judge_version`. `judge_version` is non-whitespace and MUST equal the loop's current value. `judged_at` and override `at` are timezone-aware ISO 8601 datetimes. `confidence` is a finite, non-boolean number in the inclusive range `0.0..1.0`; it never substitutes for evidence.
6b. **Provenance travels ON the stamp, and is derived, never supplied.** `origin_studio` is 8-hex and names the studio that produced the verdict; `judge_prompt_sha256` is 64 lowercase hex, or `null` only when the active judge genuinely has no prompt to hash (a model-only judge — absent is honest, a fabricated hash is not). Both exist because a verdict crossing a federation mount boundary must be evaluable WITHOUT resolving back into the origin studio, whose policy file the receiving side may not be able to read: an origin-resolved hop is not available at a boundary, so judge identity and producing studio must arrive with the verdict itself. **Neither field is caller-supplied.** The writer derives `origin_studio` from the studio it is running in (`STUDIO.md`) and `judge_prompt_sha256` from the active policy's own declaration; a provenance field a caller can hand in is a gate defended with a caller-controlled value, and would let a writer mint a stamp that lies about who judged the body. Unresolvable studio identity fails closed rather than falling back to a placeholder — a verdict with a guessed origin is worse at a boundary than a verdict that refused to be written.

7. **Judgment currency has two keys.** A verdict is current only when its T2 hash matches the body and the block's (`judge_policy_uid`, `judge_version`) pair matches that active loop. No “latest model” inference and no caller-only version claim is legal. A T2 mismatch, archived/missing policy, or policy-version change re-queues the body and excludes the verdict from current pruning gates; none is file corruption. Until the policy loop exists, production stamping fails closed while writer implementation and isolated tests may proceed.
8. **Locator currency is separate.** When T2 still matches but T1 changed through a pruning-neutral edit, the verdict remains current only if `evidence_span` resolves uniquely in the current eligible body outside nav blocks. The validator WARNs that the locator is stale and names re-stamping as the cure. If evidence no longer resolves uniquely, validation FAILs.
9. **Override effect is explicit.** The only legal override action is `keep`: while its T2 hash is current, derived pruning gates MUST treat the body as not pruned regardless of top-level verdict. `by` MUST resolve to a `type: principal` entry with `principal_class: human`. Overrides use the canonical writer's human-only override operation and the same per-UID lock/CAS path; the machine-stamp operation never creates, removes, or bypasses one.
10. **Override is version-scoped.** A judge upgrade on the same T2 body does not bypass `keep`. A real T2 body edit creates a new content version and does not inherit the old override; a later fresh verdict may replace the stale block while the original verdict + override remain in git history.
11. **Replacement policy.** Exact-retry equality covers `verdict`, `evidence_span`, every locator member, `judge_policy_uid`, `judge_version`, `confidence`, and `normalized_body_hash_judged`; the tool preserves the original `judged_at`. When those members match, source mutation is a no-op but index freshen/verification still runs. ANY non-identical payload on the same T2 + policy UID + judge version refuses, even when the verdict value matches. A version change on the same active policy UID may replace a same-T2 block after the new judge freshly revalidates evidence and no current override exists; the revalidated quote/locator MAY be byte-identical to the prior evidence. A different policy UID never silently supersedes an existing block; it requires a governed policy migration outside this writer slice. A new T2 version may replace a stale block with fresh evidence. Malformed existing blocks always refuse.
12. **Index projection is derived.** The complete nested `pruning` mapping is reflected into current/archive JSONL and SQLite `fm_json` by a targeted pruning projection. No parallel body-version registry is permitted.
13. **Concurrent-write safety.** The canonical writer is the sole sanctioned mutation channel for both machine stamps and human overrides. Live writes take a stable per-UID machine-local lock and perform compare-and-swap against the complete source snapshot immediately before replacement; any changed frontmatter or body byte refuses/retries. The candidate is same-directory temp-written, fsynced, atomically replaced, directory-fsynced, then re-read to prove body bytes/T1/T2 unchanged.
14. **Convergence boundary.** After any successful source write—or an idempotent source no-op—the writer freshens and verifies the exact derived index row. Persistent freshen failure returns non-zero and names the incremental repair command; it never reports success against stale projection. Source-first plus loud retry is the declared convergence model, not cross-file ACID.

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
10. **Pruning is evidence-carrying and version-bound (v1.7).** A `pruning:` block without complete evidence, locator, judge provenance, confidence, T1 hash, and T2 hash is invalid. Absence is always legal. A machine writer may stamp or replace only under §Pruning Block Contract; it never authors an override. `pruning` never changes `status`, `state`, or derived-only `decay.*`.
11. **A mint-time contract binds from its own start date (v1.9).** A capsule carrying a `## §Template` leg SHOULD declare `template_enforced_from:` — the date that leg was authored. The generic instance verifier reads it directly from the capsule and grandfathers every entry `created` on or before it for section presence, because an entry written before the scaffold existed was never minted from it and cannot have "dropped" its sections. The declaration is the capsule's, not the tool's: no derived registry, no runtime `git` lookup, so a shipped studio with no git history enforces identically. Grandfathering is scoped to MISSING-SECTION alone — a grandfathered entry stays subject to every other check. Retroactive application of this contract produced 1,089 findings across 363 entries, burying the 21 genuine ones; that is the standing reason the declaration exists.

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

12. **Pruning-contract compliance** *(v1.7; required implementation in the active Gardener cycle)* — one shared `check_pruning_contract` implementation MUST validate every present block's closed shape, enums, bounded confidence, provenance, current/stale T2 + judge-version disposition, T1 locator, strict evidence resolution, override authority/effect, and no-evidence refusal through both full-validator and targeted `check-one` paths. Evidence-less or unresolvable current blocks FAIL; stale blocks WARN and re-queue; absent blocks PASS silently. Until that implementation lands and its plants pass, this v1.7 amendment is schema-only and the Gardener cycle cannot close.

## Inheritance

`core` is the root. It has no parent. All other capsule definitions extend `core` and inherit its rules.

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 2.0 | 2026-08-03 | Added the explicit `core_field_specializations` contract used by typed-mint pilots. Descendants may override only named core defaults; undeclared omissions remain defects. Records the existing note/task schema without migrating instances. | argus-a144 |
| 1.9 | 2026-07-31 | OPTIONAL `template_enforced_from:` added to §Optional Frontmatter + §Governance Rule 11. A capsule carrying a `## §Template` leg declares the date that leg was authored; the generic instance verifier grandfathers entries `created` on or before it for section presence, because the leg is a mint-time contract and an entry that predates the scaffold was never minted from it. Purely additive (absent is legal; no instance touched; no existing rule changed). Follows the `enforced_enums` idiom: declared on the capsule, read straight from the capsule, no derived registry and no runtime git dependency. Cures 1,089 retroactive MISSING-SECTION findings across 363 entries that were burying 21 genuine ones. Protect-list authority: b600698e §6 + bba40cd7 scope boundary. | cursor-agent |
| 1.8 | 2026-07-25 | Pruning provenance for federation: `pruning.origin_studio` (8-hex, required) and `pruning.judge_prompt_sha256` (64-hex or null) added as required members, plus Rule 6b. A verdict crossing a federation mount boundary must be evaluable without resolving back into the origin studio, whose policy the receiving side may not be able to read — so judge identity and producing studio travel ON the stamp. Both are DERIVED by the writer (studio identity from `STUDIO.md`, prompt hash from the active policy), never caller-supplied; unresolvable studio identity fails closed. Cut before the Gardener first sweep's 250 proposals became stamps, i.e. at zero migration cost. Flagged by Metis G93 2026-07-25; authorized by Mike same session. | argus-a140 |
| 1.7 | 2026-07-17 | OPTIONAL universal `pruning:` valid-time block + evidence/T1/T2/override/staleness contract; no mint-template change. Lock-break authorized by Mike-locked Gardener Pruning dev-spec a286c210, which explicitly assigns the capsule schema amendment to Argus. | argus-a133 |
| 1.6 | 2026-06-09 | Canonical optional `state` field declaration added after the lifecycle-knot disambiguation; pure additive lock-break under Mike's Option-A + “push” authorization. | argus-a104 |
| 1.5 | 2026-06-05 | `subsystem_hub:` added as a core optional field + Governance Rule 9: `member_of` = true organizational parent, `subsystem_hub` = subsystem membership (the two were conflated in `member_of`). Finishes the v2.5 project split fleet-wide. Purely additive (subsystem_hub optional; member_of semantics clarified, not changed). Mike-A100-signed lock-break; implements member_of DISAMBIGUATE (6f5bb2cb). | argus-a100 |
| 1.4 | 2026-06-05 | `enforced_enums` extended to the `{canonical, aliases}` dict form (SKOS canon+alias). Validator three-way classifies: canonical=PASS / alias=NORMALIZABLE (separate counter, non-breaking) / unknown=WARN; `state` aliases rejected; unrecognized shapes ERROR. Backward-compatible (list form unaffected). Mike-A99-signed lock-break; implements c4512bdc (alias-map machinery; Piece 1 built + verified). | argus-a99 |
| 1.3 | 2026-06-04 | Optional `enforced_enums:` frontmatter slot added (the ENFORCE-step primitive: a type capsule declares its own enforced status/state vocabularies; validator reads them straight from the capsule, no registry). +1 governance rule (8), +1 validation check (10), +1 optional-frontmatter section. Purely additive. Mike-A98-signed lock-break; implements addc4490 v0.5 (enforce-first, task pilot). | argus-a98 |
| 1.2 | 2026-05-15 | Title semantics clarified (display-name; distinct from `name:`); Navigation block render obligation added (per HUMAN-NAVIGATION.md primitive); 2 new governance rules + 2 new/expanded validation checks (Check 5 enforcement WARN; Check 9 NEW). Aligned-with HUMAN-NAVIGATION (`57a9c11f`) + SELF-HEALING (`db0fd9b1`). | vela-v45 |
| 1.1 | 2026-04-14 | Field name: `modified` (was `last_modified` — errata April 13, 2026) | vela-v28 |
| 1.0 | 2026-04-10 | Initial locked definition | tropo |

---

*core capsule definition | LOCKED v2.0 | Tropo OS | explicit subtype-specialization contract added 2026-08-03 by Argus A144 under Mike's typed-mint approval*
*"The schema floor every governed entry stands on. Title is the human handle; Navigation block is the human surface; enforced_enums is the capsule enforcing its own vocabulary."*
