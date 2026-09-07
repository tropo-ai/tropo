---
uid: ee814120
name: core
type: capsule-definition
extends: null
version: 2.2
v2_2_lock_break: "v2.1 -> v2.2 lock-break under Mike-locked v1.94 dev-spec 91d951f4 (B-1, The Ship Manifest; locked 2026-09-02, all seven AC6 rows ratified at Mike's walk), whose committed_substrate explicitly assigns this capsule amendment to the Stream 5 package. Adds the OPTIONAL shadow-edition fields (ships_as, shadow_of, edition_of_body_hash, edition_date, edition_kind), Governance Rule 13, and Validation Check 14 -- the designation and freshness half of the SHADOW verdict, whose other half (ship_verdict) lives on the ship-artifact capsule. Purely additive: absence means not-designated, no existing field, rule, check, or instance changes, and no source is required to carry anything. A source with no frontmatter CANNOT carry ships_as, which is why the root manifest carries path-designated pairs instead -- see Rule 13."
v2_1_lock_break: "v2.0 -> v2.1 lock-break under Mike-locked v1.89 dev-spec 271d28d7 (locked 2026-08-16; activation 7a47c089), whose committed_substrate explicitly assigns this capsule amendment to the pairing package. Adds the OPTIONAL lifecycle_pairing block (\u00a7Lifecycle Pairing Contract), Governance Rule 12, and Validation Check 13 \u2014 the status/state RELATION that independent enum enforcement structurally cannot see. Purely additive: absence means not-declared/not-checked, no existing field, rule, check, or instance changes, and no global terminal default is introduced anywhere."
tier: os
author: tropo
created: 2026-04-10
modified: '2026-09-05'
modified_by: argus-a171
v2_0_amendment_note: "Mike-approved typed-mint pilot, 2026-08-03. Defines one narrow, explicit subtype-specialization mechanism so a descendant capsule may override only named core fields in `core_field_specializations`. This records existing note/task contracts rather than forcing invented title/status/owner values into legal births. Undeclared omissions remain defects; no instance migration is implied."
v1_9_lock_break: "v1.8 → v1.9. Adds the OPTIONAL `template_enforced_from:` field (§Optional Frontmatter) + §Governance Rule 11: a capsule carrying a `## §Template` leg declares the date that leg was authored, and the generic instance verifier grandfathers entries created on or before it for section presence. Purely additive: absent is legal; no existing required field, rule, enum, or check changes; no instance is modified. Follows the `enforced_enums` idiom exactly — the capsule declares, the validator reads it straight from the capsule, no derived registry and no runtime git dependency. Written because the Live Template + Body Shape check applied a MINT-TIME contract retroactively: every §Template leg in this vault was authored 2026-07-12..07-18 against a corpus months older, producing 1,089 MISSING-SECTION findings across 363 entries that could not have been minted from the scaffold they were judged against. The pre-existing corpus is on the protect list of the Mike-walked program brief b600698e §6 ('they gain template/verifier legs, nothing migrates') and historical migration is explicitly OUT of scope in S2 (bba40cd7)."
current_amendment_authority: a286c210
current_amendment_locked_by: mike-maziarz
current_amendment_locked_at: 2026-07-12
v1_7_lock_break: "v1.6 → v1.7 lock-break under Mike-locked Gardener Pruning dev-spec a286c210 (locked 2026-07-12; committed_substrate explicitly AMENDS vault/capsules/ and assigns the pruning block contract to Argus). Adds the OPTIONAL universal pruning block: an evidence-carrying, body-version-keyed, human-overridable valid-time verdict for governed Markdown bodies. Purely additive: absent is legal; no existing instance changes; mint templates remain untouched. Defines locator/hash/override/staleness semantics before the canonical writer + validator land."
v1_6_lock_break: v1.5 → v1.6 lock-break Mike-authorized 2026-06-09 (Option A + 'push'). Adds the canonical `state` field declaration to Optional Frontmatter — the universal 2-value visibility flag {active, archived}, the result of the state DISAMBIGUATE (99e52c18, move 3 of the lifecycle knot 9f6a1379). Purely additive (documents the migrated reality — 51 entries migrated to state∈{active,archived}, 0 violations; the universal validator check d2b9c8e6.py:3021 already enforces it at WARN). prior modified argus-a99 2026-06-05.
status: locked
s5_uid_rule_sweep_2026_09_05: "Validation check 1 reads 'the uid as minted' (12-hex composite since 3d430852; 8-hex legacy; UID_RE in tropo-validate.py the one authority) instead of a hard-coded ^[0-9a-f]{8}$. Mike-ruled 2026-09-05 at the v1.95 walk, S5 on plan f015ba71c711: 'We tried to catch all the 8hex hard coded rules, you must update that.' Prose-only, one check line; no enum, state, template or version change (the extraction_scope sweep precedent). By argus-a171."
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
| `lifecycle_pairing` | map | OPTIONAL, declared on a **type capsule's** frontmatter. Declares which intrinsic statuses are terminal for the type, and which statuses may legally coexist with `state: archived`. `status` and `state` are already enforced independently by `enforced_enums`; this block declares the missing *relation* between them, so a type can refuse a combination its own law forbids without flattening per-type vocabulary. When present it MUST conform to §Lifecycle Pairing Contract. **Absence means “not declared / not checked” — never “apply a global default”**: one shared hardcoded terminal set is exactly the folklore this block replaces. |
| `ships_as` | UID or path | OPTIONAL **shadow designation, source side (v2.2)**. Names the PUBLIC TWIN that ships in this entry's place: the box carries the twin and not the source. Legal on any governed entry that has frontmatter to carry it. **A source with no frontmatter cannot carry this field** — that is the same fact as "it has no uid", seen from the other side — so path-designated pairs live as rows in the release root manifest instead, and adding frontmatter to a principal-owned document purely to feed a manifest inverts which one serves the other (§Governance Rule 13). Absence means not-designated; the entry ships or is denied on its own verdict. |
| `shadow_of` | UID or path | OPTIONAL **shadow designation, twin side (v2.2)**. The inverse of `ships_as`: names the SOURCE this entry is the public edition of. A UID when the source is a governed entry; a **vault-root-relative path** when the source has no uid (e.g. `operating-agreement/OPERATING-AGREEMENT.md`). Required on any ship-artifact whose `ship_verdict` is `SHADOW` (see the ship-artifact capsule). A twin body **keeps its source's uid refs** — ref-rewriting is ruled OUT for v1.94 and carried as a standing limitation, so a reader following a ref from a twin lands on the source's uid. |
| `edition_of_body_hash` | string | OPTIONAL, **written by the election walk at election-apply, never hand-authored (v2.2)**. 64 lowercase hex: the source body's `body_sha256` at the moment this twin was last elected as its current edition. The election walk lists a pair when the source's body hash no longer matches this value. Absent means never elected — the walk lists the pair on its first run, which is correct rather than an error. |
| `edition_date` | string | OPTIONAL, **written by the election walk at election-apply (v2.2)**. ISO 8601 date of that election. Informational beside `edition_of_body_hash`, which is the field the mechanism actually turns on; a date alone cannot say whether the source moved. |
| `edition_kind` | string | OPTIONAL free-form label for what kind of edition a twin is (`public` is today's only value in use). Descriptive, not enforced: the mechanism keys on `shadow_of` and `edition_of_body_hash`, never on this. |

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

## Lifecycle Pairing Contract (v2.1 amendment 2026-08-16)

The Mike-locked [v1.89 lifecycle pairing dev-spec](../files/271d28d7.md) adds the relation the schema floor was missing. `enforced_enums` validates `status` and `state` as independent vocabularies, so a project at `status: evergreen, state: archived` passes both field checks while the project capsule says evergreen never terminates. The opposite shortcut is equally wrong: a terminal status with `state: active` is a done-and-current record, not a contradiction.

A type capsule declares the closed block:

```yaml
lifecycle_pairing:
  terminal_statuses: [done]                 # fallback ONLY; forbidden when lifecycle_machine exists
  archived_state_allowed_statuses: any      # or a non-empty canonical list
```

### Field semantics

1. **Closed shape.** Only the two keys above are legal. An unknown key, a non-mapping value, a non-string member, or an empty list is an error, never a silent skip.
2. **One terminal authority.** When the capsule declares `lifecycle_machine`, terminal statuses come only from `states[].terminal`, and a simultaneous `terminal_statuses` fallback is an error — two sources that can disagree are worse than one that can be wrong. A capsule with no machine MUST declare a non-empty `terminal_statuses` fallback; a declaration that can name no terminal status cannot answer the question it exists to answer.
3. **Values resolve through the same capsule's enum.** Every member of `terminal_statuses` and of a list-form `archived_state_allowed_statuses` must resolve through that capsule's canonical `enforced_enums.status` values or its declared aliases. The loader keeps the raw value for findings and compares on the canonical one, so an alias and its canon are the same status, and declaring both is a duplicate rather than two entries.
4. **`any` is a scalar wildcard only.** `archived_state_allowed_statuses: any` means archival is a pure visibility move at every intrinsic status. `any` inside a list is an error, and there is no terminal wildcard at all: a type that terminates at every status is not expressing lifecycle.
5. **Orthogonality is preserved.** `state: active` is never contradictory merely because `status` is terminal. The block constrains the archived direction only.
6. **Absence is not a default.** An undeclared type is explicitly unchecked. Inheriting a guessed global rule would falsely reject done-and-current law and miss per-type archive rules.

## Shadow Edition Contract (v2.2 amendment 2026-09-02)

The Mike-locked [Ship Manifest dev-spec](../files/91d951f4.md) establishes SHADOW as one of three
ship verdicts: a source that does not ship is replaced in the box by a **public twin** — a
deliberately authored edition, not a redaction. Mike's frame at the lock walk governs how these are
written: *"The twin is meant to help future tropo-studio owners... PII, privacy are not my concern.
It is super hard to get people to adopt what we are doing, we are enablers not preventers."* A twin
is a gift to a stranger. Names in a twin are fine.

The pairing is **two fields pointing at each other**, and either side alone is enough to designate:

```yaml
# On the source (only if it has frontmatter to carry it):
ships_as: f0155ddd04f7

# On the twin:
shadow_of: "operating-agreement/OPERATING-AGREEMENT.md"   # uid, or path when the source has none
edition_kind: public
edition_of_body_hash: "<64 lowercase hex>"   # written by the walk, never by hand
edition_date: '2026-09-02'                   # written by the walk
```

**Designation by path is first-class, not a fallback.** The seed pair proves why: the source
`operating-agreement/OPERATING-AGREEMENT.md` opens at `# Operating Agreement v3.0` with no
frontmatter at all, so it has nowhere to put `ships_as` and no uid to be named by. Its pairing is a
row in the release root manifest. Four review passes over this spec read *"the source carries
`ships_as`"* without noticing it cannot; authoring the artefact is what surfaced it.

**Freshness informs; it never blocks.** `edition_of_body_hash` records the source body as it stood
when the twin was last elected. When the source moves, the election walk lists the pair. It does not
fail a build, and **zero elections is a legal, stated outcome** — Mike at the walk: *"it's okay if
they drift for a while, but there should always be a 'beacon home' between the two files and the
opportunity to update... I do not want blockers, I want awareness of drift."*

**Twin bodies keep their source's uid refs.** Rewriting refs uid-to-uid is ruled OUT for v1.94 and
recorded as a standing limitation rather than deleted quietly, because a reader following a ref out
of a twin will land on the source's uid and should find that documented rather than surprising.

## Title Semantics (v1.2 amendment 2026-05-15)

The `title:` field carries the entry's **human-readable display-name**. It is the surface text that appears wherever the entry is referenced in a rendered context — in another entry's `📥 Cited by` section, in a Navigation block breadcrumb, in a channel post citation, in a chat message link.

`title:` is distinct from `name:` (which is the structured machine-name; used by tooling, registries, agent slugs). Both fields may be present; `name:` is structured (e.g., `vela-v45`, `tropo-os-release`), `title:` is readable (e.g., `"Vela V45 — Activation Entry"`, `"Tropo-OS v1.27.0 — Dev-Pipeline Enforcement Hardening"`).

When an entry is referenced from another entry's rendered Navigation block, the display surface is `title:`. If `title:` is absent, the renderer falls back to `name:`, then to the bare UID — both of which fail the [HUMAN-NAVIGATION.md (57a9c11f)](../../.tropo/HUMAN-NAVIGATION.md) primitive's readable-name-first contract. Authors MUST populate `title:` for every governed entry.

## Navigation Block Render Obligation (v1.2 amendment 2026-05-15)

Every governed vault entry's rendered body MUST contain a sentinel-wrapped Navigation block at the top, immediately after the H1 title. The block is authored by [`.tropo-studio/scripts/generate-relations-header.py`](../../.tropo-studio/scripts/generate-relations-header.py) during the canonical render pass (Step 4/4 of `rebuild-vault.py`). Agents do not hand-author the block; the renderer produces it from frontmatter + graph state.

The block carries five sections per [HUMAN-NAVIGATION.md (57a9c11f)](../../.tropo/HUMAN-NAVIGATION.md): 📍 Path / 🔗 Self / ↓ Children / ↔ Siblings / 📥 Cited by. Sentinels (`<!-- nav-block:start --> ... <!-- nav-block:end -->`) make the block idempotently replaceable.

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
12. **Lifecycle pairing is declared per type, and silence is not consent (v2.1).** A type capsule MAY declare `lifecycle_pairing:` to state which statuses are terminal and which may coexist with `state: archived`. Where a `lifecycle_machine` exists it is the only terminal authority and a fallback list alongside it is an error; where none exists the fallback is required. Declared values resolve through that capsule's own `enforced_enums.status` canon and aliases — no consumer may invent a second status list. An undeclared type is unchecked rather than defaulted. The block says which pairs the type's own law permits; it never grants authority to close, archive, or mutate an entry.

13. **A shadow pair is designated, never inferred (v2.2).** A source ships in its twin's place only when the pair is DECLARED — `ships_as` on the source, `shadow_of` on the twin, or a path-designated row in the release root manifest. No tool may infer a pairing from naming, adjacency, or content similarity. Where a source has no frontmatter it **cannot** carry `ships_as`, and the manifest row is the designation; do not add frontmatter to a principal-owned document to satisfy a field, because that inverts which one serves the other. `edition_of_body_hash` and `edition_date` are WRITTEN BY THE ELECTION WALK at election-apply and are never hand-authored — a hand-set edition hash is a claim that a human compared two bodies, which is exactly what the walk exists to do.

## Validation Checks (run at check-in)

1. UID is the uid as minted through the ADR-050 chokepoint: `^[0-9a-f]{12}$` (composite, since 3d430852 Stage B 2026-08-31) or `^[0-9a-f]{8}$` (legacy records); `UID_RE` in `tropo-validate.py` is the one authority and accepts both. *(S5, Mike-ruled 2026-09-05: "the uid as minted" replaces every hard-coded 8-hex rule; field rows in type capsules that still say "8-hex" defer to this line.)*
2. UID is not already in use by a different file
3. Type is in the registered capsule types
4. Status is valid for the type's state machine (delegated to type-specific definition)
5. **Title present (non-empty), length ≤ 100 chars; no forbidden characters** *(v1.2 amendment — enforcement at WARN; ratchet to ERROR after migration substrate is clean)*
6. Owner is a known identifier; length ≤ 30 chars
7. Created and modified are valid ISO 8601 dates
8. modified ≥ created
9. **Navigation block render safety** *(v1.2 amendment, NEW)* — entries with frontmatter + H1 MUST have a sentinel-wrapped Navigation block in body. WARN at v1.X; ERROR ratchet planned. Implemented via `check_navigation_block_render_safety()` in `tropo-validate.py`.
10. **Enforced-enum compliance** *(v1.3; three-way v1.4)* — for any type whose capsule declares `enforced_enums`, each entry's raw frontmatter `status`/`state` is classified (case-folded): **canonical = PASS; alias (dict form) = NORMALIZABLE** (a separate counter — NOT a WARN; does not touch warnings/fails/exit; a groomer normalizes it to canon); **unknown = WARN** (ratchet to ERROR per-field when that field's true-drift reaches zero). An unrecognized `enforced_enums` shape ERRORs. Reads the block + the entry via `yaml.safe_load` in `d2b9c8e6.py` (c4512bdc Piece 1). Companion coherence check: the `enforced_enums` block's canonical values match the capsule's prose enum line (backtick-colon anchor `` `status:` ∈ `` / `` `state:` ∈ ``).

13. **Lifecycle-pairing compliance** *(v2.1; implemented by the v1.89 pairing package)* — for any type whose capsule declares `lifecycle_pairing`, one shared implementation (`vault/tools/lib/lifecycle_pairing.py`) MUST validate the declaration's closed shape and enum resolution, then classify each entry of that type: `state: archived` with a status outside the declared allowed set is a violation; `state: active` is never a violation on terminal status alone. Malformed declarations ERROR rather than silently skipping the type. Undeclared types are not checked.

12. **Pruning-contract compliance** *(v1.7; required implementation in the active Gardener cycle)* — one shared `check_pruning_contract` implementation MUST validate every present block's closed shape, enums, bounded confidence, provenance, current/stale T2 + judge-version disposition, T1 locator, strict evidence resolution, override authority/effect, and no-evidence refusal through both full-validator and targeted `check-one` paths. Evidence-less or unresolvable current blocks FAIL; stale blocks WARN and re-queue; absent blocks PASS silently. Until that implementation lands and its plants pass, this v1.7 amendment is schema-only and the Gardener cycle cannot close.

14. **Shadow-designation coherence** *(v2.2; implemented by the v1.94 Ship Manifest package)* — one shared implementation (`vault/tools/lib/ship_verdict.py`) MUST resolve every designated pair and refuse an INCOHERENT one: a `ships_as` whose target does not exist; a `shadow_of` naming a uid that resolves to nothing (a PATH target is checked for existence on disk, not in the index); a source designated to two different twins; and a twin claiming two different sources. A pair designated on one side only is LEGAL, not a defect — either field alone designates. `edition_of_body_hash` present without `shadow_of` is a defect, because an edition hash with no source to compare against can never change verdict.

## Inheritance

`core` is the root. It has no parent. All other capsule definitions extend `core` and inherit its rules.

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 2.2 | 2026-09-02 | OPTIONAL shadow-edition fields (`ships_as`, `shadow_of`, `edition_of_body_hash`, `edition_date`, `edition_kind`) + §Shadow Edition Contract, Governance Rule 13, Validation Check 14. The designation half of the SHADOW ship verdict; the verdict itself lives on the ship-artifact capsule. Designation by PATH is first-class rather than a fallback, because the seed pair's source carries no frontmatter and therefore cannot carry `ships_as` — a fact four review passes over the spec read past. Edition fields are walk-written, never hand-authored. Purely additive: absence means not-designated; no instance changes. Lock-break authorized by Mike-locked dev-spec 91d951f4, which assigns this capsule amendment to the Stream 5 package. | talos-t60 |
| 2.1 | 2026-08-16 | OPTIONAL `lifecycle_pairing:` block + §Lifecycle Pairing Contract, Governance Rule 12, Validation Check 13. Declares the relation between `status` and `state` that independent enum enforcement cannot see: which statuses are terminal, and which may legally coexist with `state: archived`. Terminality comes from `lifecycle_machine` where one exists (a simultaneous fallback is an error) and from a required fallback list where none does; declared values resolve through the capsule's own `enforced_enums.status` canon and aliases. Purely additive — absence means unchecked, never a global default. Lock-break authorized by Mike-locked dev-spec 271d28d7 (activation 7a47c089), which assigns this capsule amendment to the pairing package. | talos-t44 |
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

*core capsule definition | LOCKED v2.1 | Tropo OS | lifecycle_pairing contract added 2026-08-16 by Talos T44 under Mike-locked dev-spec 271d28d7*
*"The schema floor every governed entry stands on. Title is the human handle; Navigation block is the human surface; enforced_enums is the capsule enforcing its own vocabulary."*
