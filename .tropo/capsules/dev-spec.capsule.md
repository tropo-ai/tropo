---
uid: c3f68cb5
name: "dev-spec"
type: capsule-definition
extends: core
version: 1.2
v1_2_amendment_note: "v1.1 → v1.2 amendment 2026-06-07 by Talos T13 per Mike-A103 signed lock-break (verbatim 'do it right, let's build' 2026-06-07) + Argus A103 dev-spec e26935da S5. Additive + non-breaking. (1) NEW optional field cascade_disposition (object; two keys doc + test; each: {mode: triggered|attested; evidence_ref: uid|path [required for attested]; attested_by: principal-label [required for attested, resolved via _resolve_principal_uid to a registered type:principal != cycle executor]; reason: one-line}). mode:triggered means cascade proven via triggered_doc/test_activation_uids; mode:attested means proven by another path. (2) NEW Rule 8: a dev-spec reaching terminal status with EMPTY triggered_doc/test_activation_uids MUST carry cascade_disposition covering BOTH doc and test (each triggered+done, OR attested with independent attestor + evidence_ref) — UNLESS pre-S5 grandfathered (target_release < 1.66.0). Closes finding 15c085de (retroactive anchoring must not bypass the doc/test cascade). Independence reuses _resolve_principal_uid from S1 (ed04d931). Engine enforcement in check_triggered_pipeline_completion (~L1807); validator check in d2b9c8e6.py (WARN now, ERROR-ratchet next cycle per gradual discipline)."
v1_1_amendment_note: "v1.0 → v1.1 amendment 2026-05-28 by Argus A87 captain-mode per v1.59 dev-spec d8c3f1b7 V1 + Mike-A87 walk lock by-number 2026-05-28. Two changes. (1) acceptance_criteria field type formalized from `string` to `list of strings` (substrate-honest: existing 25-30 dev-specs already use list-of-strings shape; v1.0 schema said `string` but practice diverged; v1.1 ratifies the practice). Each entry is a Mike-walkable success condition; not box-checkable; ≤300 chars per entry recommended. (2) NEW cross-validation pairing rule (V1): every entry in dev-spec.acceptance_criteria MUST have at least one paired entry in the triggering test-spec's behaviors_covered with verifies_acceptance_criterion:<int> set to that entry's 1-based positional index. Paired with test-spec.capsule v1.0 → v1.1 amendment (Rule 3 extension covering acceptance_criteria coverage; existing target_substrate cross-validation rule unchanged). Pointer mechanism = 1-based positional index per Mike-A87 walk lean lowest-churn (vs by-name list-of-objects with stable IDs which would require migration of 25-30 dev-specs). Honest tradeoff: by-number is fragile under middle-insertion of acceptance_criteria entries (later indices shift); ratchet to by-name available as v1.60+ amendment if reorder-breakage becomes empirical pattern. Engine refusal: pipeline-runtime.py lock-step validator extension refuses dev-spec or test-spec lock when pairing rule fails (mismatch surface: acceptance_criteria entry with no behaviors_covered pairing; OR behaviors_covered.verifies_acceptance_criterion pointing at non-existent index). Vela V54 test-spec body at 6183301b for v1.59 already dogfooded this pattern by populating verifies_acceptance_criterion on every behavior in the very test-spec that verifies V1 — empirical proof point captured for H1 retrospective."
tier: os
author: argus-a80
created: 2026-05-23
modified: 2026-06-09
created_by: argus-a80
modified_by: argus-a105
status: locked
enforced_enums:
  status: [draft, active, done, locked, archived]
meta_status_rollup:
  in-progress: [draft, active]
  done: [done, locked, archived]
schema_version: 2
governed_by: 222873b9   # capsule-definition meta
aligned_with:
  - "de5160c0"   # design-spec.capsule v2.1 — retrospective architectural-record sibling (different concept; lexically distinct slot)
  - "a7f2e9c4"   # arch-spec.capsule v2.1 — heavier formal-contract sibling
  - "de5181b0"   # design-brief.capsule — exploratory upstream sibling
pattern_family: "spec-family"   # dev-spec / doc-spec / test-spec; symmetric activation-input shape across dev / doc / test pipelines
v1_0_authoring_context: "Authored by Argus A80 2026-05-23 as the third *-spec capsule per c3dc9f00 v0.2 §1 (renamed from 'design-spec' to 'dev-spec' per Mike-A80 walk 2026-05-23 to avoid collision with locked design-spec.capsule v2.1 at UID de5160c0). Locked at v1.0 per Mike-G57 velocity calibration 'v1.0 capsules will be easy ... done by end of work day' + the locked Captain's Briefing v3.0 §Three-Pipeline Substrate-Enforcement direction. Composes with doc-spec.capsule v1.0 + test-spec.capsule v1.0 (forthcoming this cycle); together they form the *-spec family — symmetric activation-input shape across dev / doc / test pipelines per the v1.46 pipeline-runtime engine. Mike-A80 framing: 'It's like an ignition key that fits.'"
member_of:
  - "8dd772a0"   # tropo-governance
---

# dev-spec — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [capsule-definition meta (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [design-spec.capsule v2.1 (de5160c0)](design-spec.capsule.md) — retrospective architectural-record sibling; lexically distinct |
| Aligned with | [arch-spec.capsule v2.1 (a7f2e9c4)](arch-spec.capsule.md) — heavier formal-contract sibling |
| Aligned with | [design-brief.capsule (de5181b0)](design-brief.capsule.md) — exploratory upstream sibling |
| Pattern family | `spec-family` — dev-spec + doc-spec + test-spec (symmetric activation-input shape across dev / doc / test pipelines) |
| Extends | `core` |

*A dev-pipeline activation-input commitment — declares what a dev-cycle (or per-stream sub-cycle) will author, amend, or refactor + the acceptance criteria for clean close. The "ignition key" for dev-pipeline activations (Mike-A80 framing).*

*First of the spec-family alongside `doc-spec` and `test-spec`. Each *-spec is the symmetric activation-input for its corresponding pipeline (dev / doc / test). Together they enforce upfront commitment to "what will be built / documented / tested" before any pipeline engine fires.*

---

## Intent

A `dev-spec` entry is a forward-looking, per-cycle (or per-stream) commitment. It answers four questions before a dev-pipeline activation fires:

1. **What does this cycle (or stream) commit to authoring / amending / refactoring?** Enumerated substrate targets — UIDs, paths, change classes, brief descriptions. No fuzzy framing; "we'll author capsules" is rejected by validator.
2. **What is the acceptance criterion for clean close?** Mike-walkable success conditions; the substrate that verifies the cycle did what it said it would.
3. **What doc-pipeline activations does this dev-cycle trigger?** Populated at activation-time by the engine; honest record of the cross-pipeline cascade.
4. **What test-pipeline activations does this dev-cycle trigger?** Same; engine writes; honest record.

The dev-pipeline engine refuses to activate without a compliant dev-spec entry. The dev-cycle cannot close-ship until corresponding doc-pipeline + test-pipeline activations close clean. The symmetric `*-spec` shape across all three pipelines is the substrate-level enforcement of the discipline that Captain's Briefing v3.0 names as the v2.0.0 substrate-readiness condition.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `type` | string | Literal `dev-spec` |
| `target_release` | string | Semver string the cycle ships against (e.g., `"1.51.0"`) |
| `target_stream` | string OR null | Literal stream identifier for multi-stream cycles (e.g., `"Stream-A"`, `"Phase-B"`); `null` for single-stream cycles |
| `committed_substrate` | list of objects | Each object has `target` (UID or path), `change_class` (one of: `NEW` / `AMENDED` / `REFACTORED` / `DEPRECATED`), `description` (≤ 200 chars) |
| `acceptance_criteria` | list of strings (v1.1+; was `string` at v1.0) | Non-empty list; each entry is a Mike-walkable success condition (not box-checkable); ≤300 chars per entry recommended. **v1.1 cross-validation pairing rule (V1):** every entry must have at least one paired test-spec behaviors_covered entry with `verifies_acceptance_criterion:<int>` set to this entry's 1-based positional index. Engine refuses dev-spec OR test-spec lock if any acceptance_criteria entry has no behaviors_covered pairing OR any verifies_acceptance_criterion points at non-existent index. Pointer = positional 1-based index per Mike-A87 walk lock 2026-05-28 (lowest-churn vs by-name list-of-objects; ratchet to by-name available as v1.60+ amendment if reorder-breakage becomes empirical pattern). |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `triggered_doc_spec_uids` | list of UIDs | Populated by engine at doc-pipeline trigger fire; honest record of which doc-spec entries the dev-pipeline activation triggered. Spec UIDs (the input contracts) — semantically distinct from `triggered_doc_activation_uids` below. |
| `triggered_doc_activation_uids` | list of UIDs | **v1.0.1 amendment** (Argus A80 2026-05-23 per Talos T9 engine impl note). Populated by engine at doc-pipeline trigger fire — the RUNTIME activation UIDs (paired companion to `triggered_doc_spec_uids` per the spec-vs-activation semantic split). Close enforcement check at engine-level reads these (not the spec UIDs) because activation UIDs carry `status:done` — the coupling gate per Pipeline-Runtime Engine Extension §Three-Pipeline Coupling State Machine. Each entry pairs 1:1 with the same-index entry in `triggered_doc_spec_uids` (spec[0] → activation[0]). |
| `triggered_test_spec_uids` | list of UIDs | Populated by engine at test-pipeline trigger fire; honest record of cascade. Spec UIDs. |
| `triggered_test_activation_uids` | list of UIDs | **v1.0.1 amendment** (Argus A80 2026-05-23). Runtime activation UIDs paired companion to `triggered_test_spec_uids` — same pattern as doc-side above. Close enforcement uses these for coupling gate. |
| `cascade_disposition` | object (optional) | **v1.2 (S5, e26935da).** Per-`doc` + per-`test` disposition of the three-pipeline cascade, REQUIRED at terminal status when `triggered_doc/test_activation_uids` are empty (Rule 8). Each leg: `mode: triggered` (proven via the activation UIDs) \| `mode: attested` (proven by another path, incl. a no-per-stream-deliverable). `attested` requires `evidence_ref` (uid\|path), `attested_by` (a principal-label resolving via `_resolve_principal_uid` to a registered `type:principal` ≠ the cycle executor — independence; exempt for pre-S5 `target_release < 1.66.0`), and `reason`. Enforced by `check_triggered_pipeline_completion` + the validator. Closes `15c085de`. |
| `references_cycle_brief` | UID | The exploratory cycle brief (design-brief class) that preceded this spec, if any. Briefs explore; specs commit; this field preserves the cycle-brief role |
| `risk_register` | list of objects | Inherited from upstream cycle-brief if one exists; each entry has `risk`, `mitigation` |
| `gauntlet_rounds_required` | integer | Default per Argus discipline pin (5+); explicit override for higher or lower rigor cycles |
| `pipeline_run_uid` | UID | Backreference to the pipeline-run.capsule instance this spec activated (engine writes) |
| `closed_at` | ISO 8601 | When the dev-cycle activation closed clean (engine writes at close) |
| `acceptance_evidence` | list of UIDs | UIDs of substrate that ratifies acceptance_criteria met (e.g., release entry, vela-test-plan, ship artifacts) |

---

## State Machine

```
draft → active → done → (superseded: done + state: archived)
```

**Strict status enum:** `status:` ∈ {draft, active, done, locked, archived}

| Stage | State | Meaning |
|-------|-------|---------|
| `draft` | `active` | Under authoring; not yet committed; engine refuses to activate against it |
| `active` | `active` | Locked at v1.0 by Mike-walk (or captain-mode for established cycles); dev-pipeline activation has fired; cycle work in flight |
| `done` | `active` | Cycle closed clean; `closed_at` set; corresponding doc + test pipeline activations also `done` |
| `done` | `archived` | Superseded by a newer spec (e.g., cycle-scope reshape mid-execution); requires `superseded_by:` field |

### Valid transitions

- `draft, active` → `active, active` (locking authority sets; engine fires activation)
- `active, active` → `done, active` (engine fires at close; all triggered_*_spec_uids must also be `done`)
- `done, active` → `done, archived` (when superseded; requires bidirectional `supersedes:` / `superseded_by:` pair)

### Invalid transitions

- `done` → `active` (cannot un-close a cycle; supersede if scope reshapes after close)
- `active` → `draft` (cannot un-lock; supersede if scope reshapes mid-cycle)
- `active, active` → `done, active` while any `triggered_doc_spec_uid` or `triggered_test_spec_uid` is not `done` (engine refuses; this is the three-pipeline coupling enforcement)

---

## Governance Rules (in addition to core)

1. **Locking authority locks the v1.0** of any cycle-or-stream-scope dev-spec. Mike walks the cycle brief + walks the dev-spec; locking is the act that lets the engine activate. Captain-mode authority (Argus) may lock without Mike-walk for established / non-strategic cycles where Mike has pre-authorized the scope.
2. **`committed_substrate` must list at least one substrate target per stream.** Anti-fuzzy-framing gate. "We'll author capsules" is not a target; `{target: "vault/files/abc12345.md", change_class: "NEW", description: "doc-spec.capsule v1.0"}` is.
3. **Cycle close requires all triggered_*_spec_uids `done`.** Engine-level enforcement at close-time; the three-pipeline coupling lives here. If a triggered doc-pipeline or test-pipeline activation enters `failed` or `blocked`, the dev-spec activation flips to `blocked_on_triggered_failure`.
4. **Multi-stream cycles author one dev-spec per stream.** Composes with the "many more, smaller releases" doctrine. Each stream's dev-spec carries its own `committed_substrate` + `acceptance_criteria`; all share the same `target_release`.
5. **`acceptance_criteria` must be Mike-walkable.** Concrete enough that a reader can answer "did the cycle do this?" by reading the cycle's substrate. Not "ship the work" but "registry primitive established + bypass-pattern broken + validator 0 ERRORs at STRICT mode + build-release.py Step 1 passes without TROPO_SKIP_ENFORCEMENT_GATE=1" (real example from v1.50).
6. **Supersession requires bidirectional pointer pair.** If dev-spec B supersedes dev-spec A, then A has `superseded_by: B-uid` AND B has `supersedes: A-uid`. The vault steward audits this. Composes with v2.1 design-spec.capsule Rule 3 + arch-spec sibling discipline.
7. **Legacy grandfather (v1.10–v1.50).** Cycles pre-v1.51 grandfathered as pre-dev-spec-discipline; their cycle briefs (design-brief class) suffice as historical activation record. No retroactive dev-spec authoring required. v1.51+ enforces strict.
8. **(NEW v1.2) Retroactive anchoring must not bypass the doc/test cascade.** A dev-spec reaching terminal status with EMPTY `triggered_doc_activation_uids` AND `triggered_test_activation_uids` MUST carry `cascade_disposition` covering BOTH doc and test — each either `mode: triggered` (proven via the activation UIDs) or `mode: attested` (proven by another path, with `evidence_ref` + independent `attested_by`). **Exception:** `target_release < 1.66.0` (pre-S5 grandfather) — executor-of-record attestation allowed. Independence uses `_resolve_principal_uid`; `attested_by` must resolve to a registered `type:principal` that is NOT the cycle executor. Closes finding `15c085de`. Engine enforcement in `check_triggered_pipeline_completion`; validator WARN at v1.66, ERROR-ratchet next cycle.

---

## Validation Checks (run at vault rebuild)

In addition to core checks:

1. `check_dev_spec_required_fields` — `type` / `target_release` / `target_stream` / `committed_substrate` / `acceptance_criteria` present (WARN at v1.0; ERROR ratchet at v1.1)
2. `check_dev_spec_committed_substrate_non_empty` — at least one entry per stream (anti-fuzzy-framing)
3. `check_dev_spec_committed_substrate_resolvable` — each `target` is either a resolvable UID in `vault/00-index.jsonl` OR a valid path; each `change_class` is one of the four enum values
4. `check_dev_spec_acceptance_criteria_present` — non-empty string (length > 0)
5. `check_dev_spec_target_stream_consistent` — multi-stream cycle = unique `target_stream` per dev-spec + same `target_release` across all the cycle's specs
6. `check_dev_spec_triggered_uids_resolvable` — `triggered_doc_spec_uids` + `triggered_test_spec_uids` each resolve to entries of correct type
7. `check_dev_spec_acceptance_evidence_resolvable` — when present, each UID resolves
8. `check_dev_spec_close_invariants` — `stage: done` + `state: active` requires `closed_at` + all `triggered_*_spec_uids` at `stage: done` (the three-pipeline coupling enforcement)
9. `check_dev_spec_supersession_bidirectional` — if `superseded_by:` set, the target also has `supersedes:` pointing back (Rule 6)

Authoring lane for the validators: Argus (in the v1.51 cycle that authors this capsule).

---

## Inheritance

Extends `core`. Inherits all core rules + frontmatter floor (uid / type / status / state).

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author a dev-spec.*

**Tools available:**
- `vault/00-index.jsonl` — grep `type: dev-spec` for live cycle activations; check parent cycle brief before authoring
- `vault/00-index.jsonl` — grep `type: design-brief` AND `member_of: <dev-pipeline-inbox-uid>` for upstream cycle briefs the dev-spec composes with
- `.tropo-studio/registries/registry.jsonl` — verify cross-references resolve (`refs:`, `composes_with:`, `references_cycle_brief:` UIDs)
- Companion capsules: [doc-spec.capsule v1.0](doc-spec.capsule.md) (forthcoming this cycle); [test-spec.capsule v1.0](test-spec.capsule.md) (forthcoming this cycle); together form the *-spec family
- Sibling for retrospective architectural records: [design-spec.capsule v2.1 (de5160c0)](design-spec.capsule.md) — lexically distinct; different concept (post-hoc record vs forward-looking commitment)
- Sibling for heavier formal contracts: [arch-spec.capsule v2.1 (a7f2e9c4)](arch-spec.capsule.md)

**Skills:**
- `author-dev-spec.skill.md` *(forthcoming v1.51)* — scaffold the spec from a cycle brief; pre-fill `references_cycle_brief:` + `target_release:` + `risk_register:` from the brief
- `lock-dev-spec.skill.md` *(forthcoming v1.51)* — Mike-walk gate; on lock, fire `pipeline-activate.py` against the dev-spec (engine-level trigger)
- `close-dev-spec.skill.md` *(forthcoming v1.51)* — at cycle close, verify all `triggered_*_spec_uids` at `done`; populate `closed_at` + `acceptance_evidence`; flip `stage: done`

**Procedures:**
- **Author** — capture the dev-pipeline activation commitment in spec form. Required fields: `target_release` / `target_stream` / `committed_substrate` (with at least one resolvable target per stream) / `acceptance_criteria`. Optional: `references_cycle_brief:` if one exists, `risk_register:` inherited from brief, `gauntlet_rounds_required:` if non-default
- **Walk + Lock** — Mike-walk gate (cycle-brief walk + dev-spec walk are typically the same Mike-session); locking authority flips `stage: draft → active` + sets `locked_by` + `locked_at`; engine activates dev-pipeline against the dev-spec
- **Cycle work in flight** — substrate authoring per `committed_substrate`; engine fires doc-pipeline + test-pipeline triggers per Three-Pipeline Substrate-Enforcement Architecture; cascade activations populate `triggered_doc_spec_uids` + `triggered_test_spec_uids` honestly
- **Close** — when cycle substrate complete + all triggered activations at `done` + acceptance criteria verifiable, `close-dev-spec.skill.md` fires; sets `closed_at` + `acceptance_evidence`; flips `stage: active → done`
- **Supersede mid-cycle** — if scope substantively reshapes (the v1.50 Phase 1 grooming → registry primitive pattern), author successor dev-spec at `stage: draft`; on lock, atomically set predecessor `state: archived` + `superseded_by:` + successor `supersedes:` (Rule 6 bidirectional pair). The reshape itself surfaces honestly in release notes per stm-a79-005 mid-cycle reframe pattern

**Rules (at-a-glance):**
1. **Locking authority locks v1.0** — Mike-walk for strategic cycles; captain-mode for established / pre-authorized cycles
2. **`committed_substrate` is anti-fuzzy** — at least one resolvable target per stream
3. **Cycle close requires all triggered_*_spec_uids done** — three-pipeline coupling enforcement at engine close-time
4. **Multi-stream = one dev-spec per stream** — composes with "many more, smaller releases" doctrine
5. **`acceptance_criteria` is Mike-walkable** — concrete success conditions; not box-checkable
6. **Supersession bidirectional** — `supersedes:` ↔ `superseded_by:` pair
7. **Legacy v1.10–v1.50 grandfathered** — pre-dev-spec-discipline; cycle briefs suffice as historical activation record; v1.51+ enforces

**Pitfalls:**
- **Fuzzy `committed_substrate`** — Validation Check 2 violation; "we'll author capsules" rejected; name the UIDs
- **Box-checkable `acceptance_criteria`** — Validation Check 4 violation (formally) + Rule 5 violation (semantically); concrete success conditions only
- **Close-attempt while triggered activation incomplete** — engine refuses; the three-pipeline coupling lives at engine close-time
- **Multi-stream cycle with one dev-spec** — Rule 4 violation; author one per stream
- **One-way supersession pointer** — Rule 6 violation; vault steward audit catches the asymmetry
- **Authoring a v1.10–v1.50 cycle's dev-spec retroactively** — Rule 7 violation; legacy grandfathered honestly

**Worked examples:**
- *(forthcoming)* — **v1.51 cycle dev-spec** at recursive-bootstrap pattern: v1.51's own dev-spec is the first instance; activates v1.51 against itself; dogfoods the discipline. Same shape as v1.46 pipeline-runtime engine v3.0 self-validating bootstrap
- *(forthcoming)* — multi-stream v1.51 example: Phase A (Argus self-walked schemas) + Phase B (cross-lane semantics walks) + Phase C (pipeline definitions) + Phase D (integration + recursive bootstrap activation) — each phase may be its own dev-spec entry

**Go next:**
- Companion capsules → [doc-spec.capsule v1.0](doc-spec.capsule.md) + [test-spec.capsule v1.0](test-spec.capsule.md) (forthcoming this cycle)
- Upstream brief → [design-brief.capsule (de5181b0)](design-brief.capsule.md) — briefs explore; specs commit; specs `references_cycle_brief:` upstream
- Retrospective sibling → [design-spec.capsule v2.1 (de5160c0)](design-spec.capsule.md) — when capturing architectural-record post-hoc rather than committing-to-build forward
- Heavier sibling → [arch-spec.capsule v2.1 (a7f2e9c4)](arch-spec.capsule.md) — when full formal-contract rigor needed
- Pipeline engine substrate → [pipeline.capsule v3.0](pipeline.capsule.md) + [pipeline-run.capsule v2.0](pipeline-run.capsule.md) (forthcoming v1.51 amendment)
- Strategic-frame parent → [Captain's Briefing v3.0 (a5f4b26b)](../../vault/files/a5f4b26b.md) §Three-Pipeline Substrate-Enforcement
- Architectural design-brief → [Three-Pipeline Substrate-Enforcement Architecture (c3dc9f00)](../../vault/files/c3dc9f00.md) §1 dev-spec.capsule

---

## Why `dev-spec` (not `design-spec`)

The activation-input concept needs a slot name that doesn't collide with the locked `design-spec.capsule v2.1` (UID `de5160c0`) which captures a different concept (retrospective architectural-record vs forward-looking activation-commitment). The lexically symmetric trio — `dev-spec` / `doc-spec` / `test-spec` — also reads as one architectural pattern (each *-spec is the activation-input for its corresponding pipeline), which sharpens the Three-Pipeline Substrate-Enforcement thesis. Mike-A80 framing 2026-05-23: *"It's like an ignition key that fits."*

Original c3dc9f00 v0.2 §1 named the slot `design-spec` (Mike-A79 walk 2026-05-22). Argus A80 caught the collision at boot per investigate-before-designing discipline (Tier 3 Rule 1) + surfaced as substrate-coherence finding; Mike-A80 walk 2026-05-23 ratified the rename. Cascade through c3dc9f00 v0.2 → v0.3 + Captain's Briefing v3.0 amend_history + roadmap v3 same-batch per stm-a79-004 multi-doc amendment cascade doctrine.

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-05-23 | Initial version locked. Forward-looking activation-input commitment capsule for dev-pipeline cycles. Anti-fuzzy-framing gate on `committed_substrate`. Three-pipeline coupling enforcement at engine close-time (Rule 3 + Validation Check 8). Multi-stream cycles = one dev-spec per stream (Rule 4). Legacy v1.10–v1.50 grandfathered (Rule 7). Authored by Argus A80 per c3dc9f00 v0.2 §1 spec + Mike-A80 rename walk 2026-05-23. First of the *-spec family alongside forthcoming doc-spec + test-spec. | argus-a80 |

---

*dev-spec capsule definition | LOCKED v1.0 | Argus A80 | 2026-05-23 | First of the *-spec family*
*"The ignition key for dev-pipeline activations. Commit to what gets built before the engine fires."*
