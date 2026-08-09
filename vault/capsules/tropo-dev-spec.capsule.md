---
uid: c3f68cb5
extraction_scope: ship
ship_scope_lock_break: 'extraction_scope: ship ADDED 2026-07-02 per Mike verbatim directive "ship the capsules" (A122 session; board item e687375a): the shipped extract carried entries of this type with NO type capsule in the box — a stranger studio could not govern its own contents; every prior release concealed this (capsules shipped uid-flattened, M2 tally was mute). One-line distribution-metadata addition; no schema/enum/content change.'
name: dev-spec
type: capsule-definition
extends: core
version: 1.8
mint_mode: human
mint_template: vault/capsules/templates/dev-spec.template.md
mint_template_version: '1.1'
mint_template_sha256: 1514c4624a1a4a1d6acd2c2fa2a48e33cee88c13709641e034f84f4babaa7b0d
mint_output_home: vault/files
template_enforced_from: '2026-07-17'
template_enforced_from_note: 'ADDED 2026-07-31 per core.capsule v1.9 §Governance Rule 11 (OPTIONAL `template_enforced_from`). Value is the date THIS capsule''s §Template leg was authored, derived from the first commit introducing the ## §Template heading in this file and cross-checked against this capsule''s own changelog/amendment note. Declares the mint-time contract''s start so instances predating the scaffold are not judged against it. One-line enforcement-scope metadata; no schema/enum/state-machine/template change, so no version bump (the extraction_scope sweep precedent).'
template_enforced_from_version: '1.8'
template_enforced_from_version_note: 'ADDED at v1.8 because the revised companion replaces the v1.7 free-form body with seven required headings. The generic companion verifier grandfathers stamped pre-v1.8 instances by capsule_version, avoiding false body-shape and capsule-version failures without migrating legacy content; v1.8+ instances are checked against every required heading even on the amendment date.'
v1_8_amendment_note: "v1.7 → v1.8 amendment 2026-08-03 by Argus A144 under the governed parent-authored dev-spec companion decision. target_release and target_stream move from required fields to optional routing metadata. New v1.8+ acceptance_criteria are non-empty stable-ID objects with standalone verification instructions and evidence; pre-v1.8 list-of-strings remain valid without migration, and paired test-specs continue to cover them by 1-based integer while v1.8 criteria pair by AC ID. The body contract now requires seven named sections and permits four named optional sections to be omitted. Lifecycle remains status draft → locked → done and state active → archived."
v1_7_companion_template_amendment: "Mike-approved typed-mint pilot, 2026-08-03. Moves the single scaffold to a hash-bound visible companion and resolves the capsule's contradictory lifecycle to status draft → locked → done with state active → archived. Existing off-canon values require separate evidence-based migration; no bulk relabel is authorized here."
v1_6_amendment_note: "v1.5 → v1.6 amendment 2026-07-17 by Argus A133 under Mike/Metis ROUTE authorization for B4a and Contract C0 plus Template-Leg Contract b933eafb. Adds only the generic dev-spec §Template mint scaffold; no substrate-ref schema, lifecycle, pairing, severity, or validator change."
v1_5_amendment_note: "v1.4 → v1.5 amendment 2026-07-17 by Argus A133 under Mike's explicit 'proceed with the build plan' authorization for the active Gardener Pruning cycle. Defines the spec-family substrate-ref union already used by committed_substrate in live practice: ordered classification as 8-hex UID, canonical safe Studio-relative path, or exact opaque planned identifier. Adds strict no-fuzzy identity rules and current/archive UID↔path equivalence so dev/test pairing can share one parser. Schema-only, additive alignment; no lifecycle or severity change."
v1_4_amendment_note: 'v1.3 → v1.4 amendment 2026-07-07 by Talos T25 per ADR-052 (ee0e35ad, Mike-accepted: "I decide on lightweight lock-time coupling") + Argus A127''s work-order (event 00005883, Item 2). Additive + non-breaking; refines Rule 9''s enforcement surface without touching Validation Check 10 (check_dev_spec_activation_coupling stays the BACKSTOP, unmodified). (1) NEW optional field dev_spec_activation_uid — the correlated type:activation UID, written atomically by the new runnable lock gesture (see below) alongside status:locked. Purely additive symmetry: check_dev_spec_activation_coupling still correlates from the ACTIVATION side (dev_spec_uid match, any status) per its own existing, unmodified logic; this field just makes the pairing discoverable from the dev-spec side too. (2) The forthcoming lock-dev-spec.skill.md named in this capsule''s own Studio-Shop-Signage is now a REAL, runnable tool: vault/tools/tropo-lock-dev-spec.py. Per ADR-052''s decision, locking a dev-spec through this tool ATOMICALLY opens (or reuses, if one is already correlated) the dev-spec''s dev-pipeline activation in the SAME indivisible act — refusing the lock entirely (dev-spec file byte-for-byte unchanged) if the activation cannot be opened. This makes Rule 9''s discipline correct-by-construction for locks performed through the tool; hand-edited status:locked writes remain possible (this is a lightweight coupling, not a filesystem-level write-lock) and are exactly what Validation Check 10 continues to backstop, per ADR-052''s explicit "primary + backstop, not primary replaces backstop" framing. Gauntlet-proven in test_systemic_feed_pipeline_v184.py.'
v1_3_amendment_note: 'v1.2 → v1.3 amendment 2026-07-07 by Talos T25 per Argus A127''s dev-spec 8f15f08d (Pipeline-Activation Coupling Gate; assigned_to: talos in 8f15f08d''s own frontmatter — Argus specs the governance, Talos builds the enforcement + this capsule amendment as committed_substrate of that build, Argus verifies two-sided per the session''s build/verify lane). Additive + non-breaking. (1) NEW optional field build_status (enum: built_pending_verify | mike-signed-accepted [terminal]) — formalizes a studio convention already observed in-substrate on 92093c81 + 8e551957 before this field existed in the capsule. (2) NEW Rule 9 (Activation-Coupling): a dev-spec at status:locked and/or terminal build_status MUST have a correlated type:activation entry (dev_spec_uid match, any status) somewhere in vault/files/ — closes the off-pipeline gap named in 8e8a0962 (v1.81/v1.82 reached locked + mike-signed-accepted with ZERO activations). Cured retroactively for those two by Talos T25 the same session (activations 413db7f5/019c765a). (3) NEW Validation Check 10 (check_dev_spec_activation_coupling in tropo-validate.py): WARN at v1.3 against the named {92093c81, 8e551957} grandfather allowlist; ERROR-ratchet once the vault is genuinely clean of the violation class — NOT merely once the 2-uid allowlist empties, per a verify-before-designing finding: 9 OTHER pre-existing dev-specs (5e12ab9c, 81e52840, dabe7c64, 98b9610a, 0c61a52b, 55c33476, c036dd4b, 2fe61817, bc730fe4) were found off-pipeline on the same live scan, contradicting 8f15f08d''s own AC-6 premise that only the two named UIDs would be flagged. Flagged to Argus for judgment on those 9 (separate cleanup item vs allowlist expansion) rather than silently absorbed into this fix or silently allowed to ERROR-break the validator. Gauntlet-proven in test_dev_spec_activation_coupling.py + test_capability_chain_smoke.py.'
v1_2_amendment_note: 'v1.1 → v1.2 amendment 2026-06-07 by Talos T13 per Mike-A103 signed lock-break (verbatim ''do it right, let''s build'' 2026-06-07) + Argus A103 dev-spec e26935da S5. Additive + non-breaking. (1) NEW optional field cascade_disposition (object; two keys doc + test; each: {mode: triggered|attested; evidence_ref: uid|path [required for attested]; attested_by: principal-label [required for attested, resolved via _resolve_principal_uid to a registered type:principal != cycle executor]; reason: one-line}). mode:triggered means cascade proven via triggered_doc/test_activation_uids; mode:attested means proven by another path. (2) NEW Rule 8: a dev-spec reaching terminal status with EMPTY triggered_doc/test_activation_uids MUST carry cascade_disposition covering BOTH doc and test (each triggered+done, OR attested with independent attestor + evidence_ref) — UNLESS pre-S5 grandfathered (target_release < 1.66.0). Closes finding 15c085de (retroactive anchoring must not bypass the
  doc/test cascade). Independence reuses _resolve_principal_uid from S1 (ed04d931). Engine enforcement in check_triggered_pipeline_completion (~L1807); validator check in d2b9c8e6.py (WARN now, ERROR-ratchet next cycle per gradual discipline).'
v1_1_amendment_note: 'v1.0 → v1.1 amendment 2026-05-28 by Argus A87 captain-mode per v1.59 dev-spec d8c3f1b7 V1 + Mike-A87 walk lock by-number 2026-05-28. Two changes. (1) acceptance_criteria field type formalized from `string` to `list of strings` (substrate-honest: existing 25-30 dev-specs already use list-of-strings shape; v1.0 schema said `string` but practice diverged; v1.1 ratifies the practice). Each entry is a Mike-walkable success condition; not box-checkable; ≤300 chars per entry recommended. (2) NEW cross-validation pairing rule (V1): every entry in dev-spec.acceptance_criteria MUST have at least one paired entry in the triggering test-spec''s behaviors_covered with verifies_acceptance_criterion:<int> set to that entry''s 1-based positional index. Paired with test-spec.capsule v1.0 → v1.1 amendment (Rule 3 extension covering acceptance_criteria coverage; existing target_substrate cross-validation rule unchanged). Pointer mechanism = 1-based positional index per Mike-A87 walk lean
  lowest-churn (vs by-name list-of-objects with stable IDs which would require migration of 25-30 dev-specs). Honest tradeoff: by-number is fragile under middle-insertion of acceptance_criteria entries (later indices shift); ratchet to by-name available as v1.60+ amendment if reorder-breakage becomes empirical pattern. Engine refusal: pipeline-runtime.py lock-step validator extension refuses dev-spec or test-spec lock when pairing rule fails (mismatch surface: acceptance_criteria entry with no behaviors_covered pairing; OR behaviors_covered.verifies_acceptance_criterion pointing at non-existent index). Vela V54 test-spec body at 6183301b for v1.59 already dogfooded this pattern by populating verifies_acceptance_criterion on every behavior in the very test-spec that verifies V1 — empirical proof point captured for H1 retrospective.'
tier: os
author: argus-a80
created: 2026-05-23
modified: 2026-08-03
created_by: argus-a80
modified_by: argus-a144
status: locked
enforced_enums:
  status:
    - draft
    - locked
    - done
  state:
    - active
    - archived
meta_status_rollup:
  to-do:
    - draft
  in-progress:
    - locked
  done:
    - done
schema_version: 2
governed_by: 222873b9
aligned_with:
  - de5160c0
  - a7f2e9c4
  - de5181b0
pattern_family: spec-family
v1_0_authoring_context: 'Authored by Argus A80 2026-05-23 as the third *-spec capsule per c3dc9f00 v0.2 §1 (renamed from ''design-spec'' to ''dev-spec'' per Mike-A80 walk 2026-05-23 to avoid collision with locked design-spec.capsule v2.1 at UID de5160c0). Locked at v1.0 per Mike-G57 velocity calibration ''v1.0 capsules will be easy ... done by end of work day'' + the locked Captain''s Briefing v3.0 §Three-Pipeline Substrate-Enforcement direction. Composes with doc-spec.capsule v1.0 + test-spec.capsule v1.0 (forthcoming this cycle); together they form the *-spec family — symmetric activation-input shape across dev / doc / test pipelines per the v1.46 pipeline-runtime engine. Mike-A80 framing: ''It''s like an ignition key that fits.'''
subsystem_hub:
  - 8dd772a0
---

# dev-spec — Capsule Definition v1.8

**Relations**

| Relation | Target |
|---|---|
| Governed by | [capsule-definition meta (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [design-spec capsule (de5160c0)](tropo-design-spec.capsule.md) — retrospective architectural-record sibling; lexically distinct |
| Aligned with | [arch-spec capsule (a7f2e9c4)](tropo-arch-spec.capsule.md) — heavier formal-contract sibling |
| Aligned with | [design-brief capsule (de5181b0)](tropo-design-brief.capsule.md) — exploratory upstream sibling |
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
| `description` | string | Required one-line committed build summary. The mint companion scaffolds this field; authors must consume its placeholder before lock. |
| `committed_substrate` | list of objects | Each object has `target` (spec-family substrate-ref per §Substrate Reference Syntax), `change_class` (one of: `NEW` / `AMENDED` / `REFACTORED` / `DEPRECATED`), `description` (≤ 200 chars) |
| `acceptance_criteria` | list of objects (v1.8+) | Non-empty list. Each object is `{id: AC<number>, behavior: <non-empty>, verify: {method: automated\|manual\|peer-review, command: <non-empty command/procedure, or N/A with a reason>, evidence: <non-empty expected proof>}}`. IDs are unique and stable: edits and reordering do not renumber an existing criterion. The verify block makes the dev-spec independently executable at handoff; a paired test-spec still supplies independent and/or deeper verification. Every criterion must have test-spec behavior coverage through `verifies_acceptance_criterion: AC<number>`. **Legacy compatibility:** pre-v1.8 list-of-strings remain valid without bulk migration and retain 1-based integer test-spec pointers. |

## Substrate Reference Syntax (v1.5; shared by the spec family)

Every substrate-ref is a non-empty string classified in this strict order:

1. **UID** — exactly eight lowercase hexadecimal characters.
2. **Path** — either contains `/` OR is a root filename matching `^[A-Za-z0-9._-]+\.[A-Za-z0-9]+$` (for example `CLAUDE.md`); it is canonical POSIX Studio-relative syntax with no leading `/` or `./`, no `.`/`..` segments, no backslash/NUL/repeated separator, and no symlink/root escape when it exists. A directory target may retain one trailing `/` only when the dev-spec declares that directory as the substrate boundary.
3. **Opaque planned identifier** — contains no `/`, is not UID-shaped, is not root-file-shaped, and matches `^[a-z][a-z0-9.-]*$` (for example `gardener-body-judge`). It is legal only as an exact `committed_substrate.target` declaration; no slug inference is permitted.

Identity matching is exact. UID equals the same UID. Path/opaque equals the exact same canonical literal. UID may equal a path only when the current/archive index maps that UID to that exact canonical path. Prefix, containment, basename, case-fold, fuzzy, and “looks related” matches are forbidden. A missing path is only an expected mid-cycle condition for `change_class: NEW`; unsafe path syntax is always invalid.

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `target_release` | string | Optional routing metadata: semver release the cycle ships against. It does not determine the v1.8 schema contract. |
| `target_stream` | string OR null | Optional routing metadata: stream identifier for multi-stream cycles; `null` may denote a whole-cycle route. |
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
| `build_status` | enum (optional) | **v1.3 (8f15f08d, Talos T25 2026-07-07).** Formalizes a studio convention observed in-substrate since before this field existed (`92093c81`, `8e551957`) into the capsule contract. Enum: `built_pending_verify` (in-flight; build produced, verification not yet converged) \| `mike-signed-accepted` (**terminal** — Mike has signed the build). The terminal set is `{mike-signed-accepted}`; `check_dev_spec_activation_coupling` reads the terminal set from this capsule contract rather than hard-coding the literal, per Rule 9. |
| `dev_spec_activation_uid` | UID (optional) | **v1.4 (ADR-052 ee0e35ad, Talos T25 2026-07-07).** Written atomically by `vault/tools/tropo-lock-dev-spec.py` alongside `status: locked` — the correlated `type: activation` UID the lock gesture opened (or reused, if one was already correlated) in the same indivisible act. Purely additive discoverability from the dev-spec side; `check_dev_spec_activation_coupling` continues to correlate from the ACTIVATION side (`dev_spec_uid` match, any status) per its own unmodified logic — this field is not read by that check. |

## Body Contract (v1.8)

The companion's required headings are exact verifier keys. A v1.8 instance MUST retain and complete all seven: **Intent; Current State and Gap; Desired Capability; Scope Boundaries; Implementation Contract; Acceptance and Verification; Handoff.** The generic companion verifier reports every missing required heading and every surviving `REQUIRED` marker. `template_enforced_from_version: '1.8'` keeps pre-v1.8 instances on their historical free-form body contract; no legacy body migration is required.

Four named sections are optional and may be omitted entirely when they do not apply: **Dependencies and Sequencing; Risks and Failure Modes; Migration, Compatibility, and Rollback; Reference Scenarios and Examples.** Omitting one is not a defect. Adding other useful headings is allowed when they do not weaken or replace the seven required sections.

---

## State Machine

```
status: draft → status: locked → status: done
state:  active → state: archived
```

**Strict status enum:** `status:` ∈ {draft, locked, done}

**Strict visibility enum:** `state:` ∈ {active, archived}

| Status | State | Meaning |
|--------|-------|---------|
| `draft` | `active` | Under authoring; not yet committed; engine refuses to activate against it |
| `locked` | `active` | Lock tool completed and the dev-pipeline activation is open; cycle work is in flight |
| `done` | `active` | Cycle closed clean; `closed_at` set; corresponding doc + test pipeline activations are also `done` |
| any status | `archived` | Historical visibility. Status is preserved; supersession additionally requires `superseded_by:`. |

### Valid transitions

- `draft, active` → `locked, active` (only through `vault/tools/tropo-lock-dev-spec.py`; the tool opens or reuses the correlated activation atomically)
- `locked, active` → `done, active` (engine fires at close; all triggered activation UIDs must also be `done`)
- `*, active` → `*, archived` (visibility-only archive; supersession requires the bidirectional `supersedes:` / `superseded_by:` pair)

### Invalid transitions

- `done` → `locked` (cannot un-close a cycle; supersede if scope reshapes after close)
- `locked` → `draft` (cannot un-lock; supersede if scope reshapes mid-cycle)
- `locked, active` → `done, active` while any triggered doc/test activation is not `done` (engine refuses; this is the three-pipeline coupling enforcement)

---

## Governance Rules (in addition to core)

1. **Locking authority locks the v1.0** of any cycle-or-stream-scope dev-spec. Mike walks the cycle brief + walks the dev-spec; locking is the act that lets the engine activate. Captain-mode authority (Argus) may lock without Mike-walk for established / non-strategic cycles where Mike has pre-authorized the scope.
2. **`committed_substrate` must list at least one substrate target per stream.** Anti-fuzzy-framing gate. "We'll author capsules" is not a target; `{target: "vault/files/abc12345.md", change_class: "NEW", description: "doc-spec.capsule v1.0"}` is.
3. **Cycle close requires all triggered_*_spec_uids `done`.** Engine-level enforcement at close-time; the three-pipeline coupling lives here. If a triggered doc-pipeline or test-pipeline activation enters `failed` or `blocked`, the dev-spec activation flips to `blocked_on_triggered_failure`.
4. **Multi-stream cycles author one dev-spec per stream.** Composes with the "many more, smaller releases" doctrine. Each stream's dev-spec carries its own `committed_substrate` + `acceptance_criteria`. When optional routing metadata is used, sibling stream specs share `target_release` and use distinct `target_stream` values.
5. **`acceptance_criteria` must be stable, observable, standalone, and independently covered.** For v1.8+, every criterion has a unique stable `AC<number>` ID, a non-empty behavior, and a complete verify block (`method`, `command`, `evidence`). A bare `N/A` command is invalid; it must include the reason. The dev-spec verify block lets a receiving builder execute the handoff without first locating a test-spec. The paired test-spec remains required and supplies independent and/or deeper behavioral verification, with every v1.8 criterion covered by its stable AC ID. Pre-v1.8 list-of-strings and their 1-based test pointers remain valid without migration.
6. **Supersession requires bidirectional pointer pair.** If dev-spec B supersedes dev-spec A, then A has `superseded_by: B-uid` AND B has `supersedes: A-uid`. The vault steward audits this. Composes with v2.1 design-spec.capsule Rule 3 + arch-spec sibling discipline.
7. **Legacy grandfather (v1.10–v1.50).** Cycles pre-v1.51 grandfathered as pre-dev-spec-discipline; their cycle briefs (design-brief class) suffice as historical activation record. No retroactive dev-spec authoring required. v1.51+ enforces strict.
8. **(NEW v1.2) Retroactive anchoring must not bypass the doc/test cascade.** A dev-spec reaching terminal status with EMPTY `triggered_doc_activation_uids` AND `triggered_test_activation_uids` MUST carry `cascade_disposition` covering BOTH doc and test — each either `mode: triggered` (proven via the activation UIDs) or `mode: attested` (proven by another path, with `evidence_ref` + independent `attested_by`). **Exception:** `target_release < 1.66.0` (pre-S5 grandfather) — executor-of-record attestation allowed. Independence uses `_resolve_principal_uid`; `attested_by` must resolve to a registered `type:principal` that is NOT the cycle executor. Closes finding `15c085de`. Engine enforcement in `check_triggered_pipeline_completion`; validator WARN at v1.66, ERROR-ratchet next cycle.
9. **(NEW v1.3, 8f15f08d; REFINED v1.4 per ADR-052) Activation-Coupling — a dev-spec that has turned its ignition key must have a correlated pipeline activation.** A dev-spec at `status: locked`, and/or carrying a terminal `build_status` (per the enum above), MUST have at least one `type: activation` entry anywhere in `vault/files/` whose `dev_spec_uid` equals this dev-spec's `uid` — of ANY activation `status` (a `retired` activation still proves the pipeline was opened; existence is the gate, not activeness — see `2ffdd9d6`/`35c12763` precedent). Locking a dev-spec (the ignition moment) or reaching a terminal `build_status` (the escalation — work has reached shippable state) **without** ever opening the correlated dev-pipeline activation is the off-pipeline gap this rule closes ([8e8a0962](../../vault/files/8e8a0962.md)). **v1.4 PRIMARY mechanism (ADR-052, `ee0e35ad`, Mike-accepted "I decide on lightweight lock-time coupling"):** lock THROUGH `vault/tools/tropo-lock-dev-spec.py`, which flips `status: locked` and opens (or reuses) the correlated activation as ONE indivisible act, refusing the lock entirely if the activation cannot be opened. This is the correct-by-construction on-ramp — the compliant path and the easy path are the same act. **BACKSTOP (unchanged):** `check_dev_spec_activation_coupling` in [`tropo-validate.py`](../tools/tropo-validate.py) remains the always-on net that catches any escape around the tool (hand-edited `status: locked`, legacy/imported drift). Cure for anything the backstop still catches: open a correlated activation retroactively (feed-the-pipeline, per Mike's ruling on `8e8a0962` — NOT attested-cut) or prospectively (`tropo-lock-dev-spec.py`, or the lower-level `pipeline-activate.py --dev-spec-uid` on-ramp it wraps). WARN at v1.3 (grandfather allowlist `{92093c81, 8e551957}` per `8f15f08d`'s named cure targets), ERROR-ratchet once the vault reaches a genuinely clean pass for this violation class (Talos T25 2026-07-07 verify-before-designing finding: 9 OTHER pre-existing dev-specs were found off-pipeline at the moment the two named UIDs were cured, so the ratchet is keyed on whole-vault cleanliness, not merely the 2-uid allowlist emptying — see the check's own docstring for the full disclosure; flagged to Argus for a broader-cleanup judgment call, still in progress and explicitly out of THIS amendment's scope).

---

## Validation Checks (run at vault rebuild)

In addition to core checks:

1. `check_dev_spec_required_fields` — v1.8+ requires `type` / `description` / `status` / `state` / `committed_substrate` / `acceptance_criteria`; `target_release` and `target_stream` are optional routing metadata. Pre-v1.8 instances retain their historical required-field contract. (WARN at v1.0; ERROR ratchet at v1.1)
2. `check_dev_spec_committed_substrate_non_empty` — at least one entry per stream (anti-fuzzy-framing)
3. `check_dev_spec_committed_substrate_resolvable` — each `target` parses through the shared §Substrate Reference Syntax; UIDs resolve current/archive, paths are canonical/safe (missing allowed only for NEW), opaque identifiers are exact declarations; each `change_class` is one of the four enum values
4. `check_dev_spec_acceptance_criteria_present` — v1.8+ enforces a non-empty object list, unique stable `AC<number>` IDs, non-empty behaviors, and complete valid verify blocks; legacy pre-v1.8 list-of-strings remains accepted
5. `check_dev_spec_target_stream_consistent` — when optional routing metadata is present, multi-stream cycle = unique `target_stream` per dev-spec + same `target_release` across all the cycle's specs
6. `check_dev_spec_triggered_uids_resolvable` — `triggered_doc_spec_uids` + `triggered_test_spec_uids` each resolve to entries of correct type
7. `check_dev_spec_acceptance_evidence_resolvable` — when present, each UID resolves
8. `check_dev_spec_close_invariants` — `status: done` + `state: active` requires `closed_at` + every `triggered_*_spec_uid` at `status: done`; runtime activation completion is checked through the paired `triggered_*_activation_uid` fields (the three-pipeline coupling enforcement)
9. `check_dev_spec_supersession_bidirectional` — if `superseded_by:` set, the target also has `supersedes:` pointing back (Rule 6)
10. **(NEW v1.3, 8f15f08d; BACKSTOP, unmodified by v1.4)** `check_dev_spec_activation_coupling` — a dev-spec at `status: locked` and/or terminal `build_status` has at least one correlated `type: activation` entry (`dev_spec_uid` match, any activation status) somewhere in `vault/files/` (Rule 9). WARN at v1.3 against the named `{92093c81, 8e551957}` grandfather allowlist; ERROR-ratchet once the vault is genuinely clean of this violation class. Implemented in [`tropo-validate.py`](../tools/tropo-validate.py); gauntlet-proven in `vault/tools/tests/test_dev_spec_activation_coupling.py` + `test_capability_chain_smoke.py`. Per ADR-052 (v1.4), this check remains the always-on backstop beneath the new PRIMARY lock-time coupling tool (`tropo-lock-dev-spec.py`) — not removed, not weakened.

Authoring lane for the validators: Argus (in the v1.51 cycle that authors this capsule); Check 10 built by Talos T25 2026-07-07 per Argus's dev-spec `8f15f08d`. The v1.4 lock-time coupling tool is Talos's build per ADR-052 (`ee0e35ad`) + event `00005883` Item 2.

---

## Inheritance

Extends `core`. Inherits all core rules + frontmatter floor (uid / type / status / state).

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author a dev-spec.*

**Tools available:**
- `vault/tools/tropo-lock-dev-spec.py` — **next action after authoring**; validates the draft, flips `status: draft → locked`, and atomically opens or reuses the correlated dev-pipeline activation
- `vault/00-index.jsonl` — grep `type: dev-spec` for live cycle activations; check parent cycle brief before authoring
- `vault/00-index.jsonl` — grep `type: design-brief` AND `member_of: <dev-pipeline-inbox-uid>` for upstream cycle briefs the dev-spec composes with
- `.tropo-studio/registries/registry.jsonl` — verify cross-references resolve (`refs:`, `composes_with:`, `references_cycle_brief:` UIDs)
- Companion capsules: [doc-spec capsule](tropo-doc-spec.capsule.md) and [test-spec capsule](tropo-test-spec.capsule.md); together they form the *-spec family
- Sibling for retrospective architectural records: [design-spec capsule (de5160c0)](tropo-design-spec.capsule.md) — lexically distinct; different concept (post-hoc record vs forward-looking commitment)
- Sibling for heavier formal contracts: [arch-spec capsule (a7f2e9c4)](tropo-arch-spec.capsule.md)

**Skills:**
- `author-dev-spec.skill.md` *(forthcoming v1.51)* — scaffold the spec from a cycle brief; pre-fill `references_cycle_brief:` + `target_release:` + `risk_register:` from the brief
- `vault/tools/tropo-lock-dev-spec.py` — the shipped Mike-walk/captain-mode gate; locking and correlated activation opening are one indivisible gesture
- `close-dev-spec.skill.md` *(forthcoming v1.51)* — at cycle close, verify all `triggered_*_spec_uids` at `status: done`; populate `closed_at` + `acceptance_evidence`; flip the dev-spec to `status: done`

**Procedures:**
- **Author** — capture the dev-pipeline activation commitment in spec form. Required v1.8 fields: `committed_substrate` (with at least one resolvable target per stream) + object-form `acceptance_criteria`; `target_release` / `target_stream` are optional routing metadata. Complete the seven required body sections; delete any of the four optional sections that genuinely do not apply. Optional frontmatter also includes `references_cycle_brief:` if one exists, `risk_register:` inherited from brief, and `gauntlet_rounds_required:` if non-default
- **Walk + Lock** — Mike-walk gate (cycle-brief walk + dev-spec walk are typically the same Mike-session); run `python3 vault/tools/tropo-lock-dev-spec.py --dev-spec-uid <uid> --locked-by <principal>`. The tool flips `status: draft → locked`, sets lock provenance, and opens/reuses the correlated dev-pipeline activation atomically
- **Cycle work in flight** — substrate authoring per `committed_substrate`; engine fires doc-pipeline + test-pipeline triggers per Three-Pipeline Substrate-Enforcement Architecture; cascade activations populate `triggered_doc_spec_uids` + `triggered_test_spec_uids` honestly
- **Close** — when cycle substrate is complete + all triggered activations are done + acceptance criteria are verifiable, `close-dev-spec.skill.md` sets `closed_at` + `acceptance_evidence` and flips `status: locked → done`
- **Supersede mid-cycle** — if scope substantively reshapes (the v1.50 Phase 1 grooming → registry primitive pattern), author a successor at `status: draft`; on lock, atomically set predecessor `state: archived` + `superseded_by:` + successor `supersedes:` (Rule 6 bidirectional pair). The reshape itself surfaces honestly in release notes per stm-a79-005 mid-cycle reframe pattern

**Rules (at-a-glance):**
1. **Locking authority locks v1.0** — Mike-walk for strategic cycles; captain-mode for established / pre-authorized cycles
2. **`committed_substrate` is anti-fuzzy** — at least one resolvable target per stream
3. **Cycle close requires all triggered_*_spec_uids done** — three-pipeline coupling enforcement at engine close-time
4. **Multi-stream = one dev-spec per stream** — composes with "many more, smaller releases" doctrine
5. **`acceptance_criteria` is stable-ID + standalone** — v1.8 uses unique `AC<number>` objects with behavior + verify method/command/evidence; paired test-spec coverage points at the ID, while legacy criteria keep integer pointers
6. **Supersession bidirectional** — `supersedes:` ↔ `superseded_by:` pair
7. **Legacy v1.10–v1.50 grandfathered** — pre-dev-spec-discipline; cycle briefs suffice as historical activation record; v1.51+ enforces

**Pitfalls:**
- **Fuzzy `committed_substrate`** — Validation Check 2/3 violation; “we'll author capsules” is rejected; name the exact UID, canonical path, or planned identifier
- **Malformed or box-checkable `acceptance_criteria`** — Validation Check 4 + Rule 5 violation; v1.8 requires unique stable IDs, observable behavior, executable verification, and explicit evidence
- **Close-attempt while triggered activation incomplete** — engine refuses; the three-pipeline coupling lives at engine close-time
- **Multi-stream cycle with one dev-spec** — Rule 4 violation; author one per stream
- **One-way supersession pointer** — Rule 6 violation; vault steward audit catches the asymmetry
- **Authoring a v1.10–v1.50 cycle's dev-spec retroactively** — Rule 7 violation; legacy grandfathered honestly

**Worked examples:**
- *(forthcoming)* — **v1.51 cycle dev-spec** at recursive-bootstrap pattern: v1.51's own dev-spec is the first instance; activates v1.51 against itself; dogfoods the discipline. Same shape as v1.46 pipeline-runtime engine v3.0 self-validating bootstrap
- *(forthcoming)* — multi-stream v1.51 example: Phase A (Argus self-walked schemas) + Phase B (cross-lane semantics walks) + Phase C (pipeline definitions) + Phase D (integration + recursive bootstrap activation) — each phase may be its own dev-spec entry

**Go next:**
- Companion capsules → [doc-spec capsule](tropo-doc-spec.capsule.md) + [test-spec capsule](tropo-test-spec.capsule.md)
- Upstream brief → [design-brief capsule (de5181b0)](tropo-design-brief.capsule.md) — briefs explore; specs commit; specs `references_cycle_brief:` upstream
- Retrospective sibling → [design-spec capsule (de5160c0)](tropo-design-spec.capsule.md) — when capturing architectural-record post-hoc rather than committing-to-build forward
- Heavier sibling → [arch-spec capsule (a7f2e9c4)](tropo-arch-spec.capsule.md) — when full formal-contract rigor needed
- Pipeline engine substrate → [pipeline capsule](tropo-pipeline.capsule.md) + [pipeline-run capsule](tropo-pipeline-run.capsule.md)
- Strategic-frame parent → [Captain's Briefing v3.0 (a5f4b26b)](../../vault/files/a5f4b26b.md) §Three-Pipeline Substrate-Enforcement
- Architectural design-brief → [Three-Pipeline Substrate-Enforcement Architecture (c3dc9f00)](../../vault/files/c3dc9f00.md) §1 dev-spec.capsule

---

## Why `dev-spec` (not `design-spec`)

The activation-input concept needs a slot name that doesn't collide with the locked `design-spec.capsule v2.1` (UID `de5160c0`) which captures a different concept (retrospective architectural-record vs forward-looking activation-commitment). The lexically symmetric trio — `dev-spec` / `doc-spec` / `test-spec` — also reads as one architectural pattern (each *-spec is the activation-input for its corresponding pipeline), which sharpens the Three-Pipeline Substrate-Enforcement thesis. Mike-A80 framing 2026-05-23: *"It's like an ignition key that fits."*

Original c3dc9f00 v0.2 §1 named the slot `design-spec` (Mike-A79 walk 2026-05-22). Argus A80 caught the collision at boot per investigate-before-designing discipline (Tier 3 Rule 1) + surfaced as substrate-coherence finding; Mike-A80 walk 2026-05-23 ratified the rename. Cascade through c3dc9f00 v0.2 → v0.3 + Captain's Briefing v3.0 amend_history + roadmap v3 same-batch per stm-a79-004 multi-doc amendment cascade doctrine.

---

## §Template (v1.8 — companion scaffold)

The single mint and verifier scaffold is the visible companion
[dev-spec.template.md](templates/dev-spec.template.md), hash-bound in this
capsule's frontmatter. It births at `status: draft`, explains the dev-pipeline
root, requires an explicit `change_class` choice, and authors v1.8 acceptance
criteria as stable-ID objects with standalone verify blocks. Its seven required
headings and four deletable optional headings are the body contract described
above. Test-spec pairing uses the stable AC ID for v1.8 criteria and the
historical 1-based integer only for legacy pre-v1.8 criteria.

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.8 | 2026-08-03 | Aligned schema and verifier prose to the parent-authored companion: routing metadata optional; stable-ID acceptance objects with standalone verification; dual legacy/new test pairing; seven required and four optional body sections; lifecycle unchanged. No bulk migration of legacy criteria. | argus-a144 |
| 1.7 | 2026-08-03 | Mike-approved typed-mint pilot: moved the single scaffold to a visible hash-bound companion and resolved lifecycle vocabulary to `status: draft → locked → done` plus `state: active → archived`. No bulk instance migration. | argus-a144 |
| 1.6 | 2026-07-17 | Added the generic dev-spec §Template mint scaffold under [Template-Leg Contract](../files/b933eafb.md); no schema/lifecycle/pairing/validator change. | argus-a133 |
| 1.0 | 2026-05-23 | Initial version locked. Forward-looking activation-input commitment capsule for dev-pipeline cycles. Anti-fuzzy-framing gate on `committed_substrate`. Three-pipeline coupling enforcement at engine close-time (Rule 3 + Validation Check 8). Multi-stream cycles = one dev-spec per stream (Rule 4). Legacy v1.10–v1.50 grandfathered (Rule 7). Authored by Argus A80 per c3dc9f00 v0.2 §1 spec + Mike-A80 rename walk 2026-05-23. First of the *-spec family alongside forthcoming doc-spec + test-spec. | argus-a80 |
| 1.1 | 2026-05-28 | Formalized `acceptance_criteria` as a list and paired every criterion by 1-based index to test-spec behavior coverage. | argus-a87 |
| 1.2 | 2026-06-07 | Added independent doc/test cascade-disposition attestations for terminal cycles that legitimately do not fire a pipeline leg. | talos-t13 |
| 1.3 | 2026-07-07 | **Pipeline-Activation Coupling Gate (8f15f08d).** NEW optional `build_status` field (enum, terminal set `{mike-signed-accepted}`). NEW Rule 9 + Validation Check 10: a locked/terminal-build-status dev-spec must have a correlated `type:activation` entry (any status). WARN at v1.3 against a named `{92093c81, 8e551957}` grandfather allowlist; ERROR-ratchet keyed on whole-vault cleanliness for this violation class (see `v1_3_amendment_note` for the verify-before-designing finding that widened the ratchet bar beyond 8f15f08d's own AC-6 premise). Committed substrate of dev-spec 8f15f08d (`assigned_to: talos`); Argus specs, Talos builds (this amendment + the validator check), Argus verifies two-sided per session lane. | talos-t25 |
| 1.4 | 2026-07-07 | **Coupling runnable-lock (ADR-052 `ee0e35ad`, event 00005883 Item 2).** NEW optional `dev_spec_activation_uid` field (purely additive discoverability; not read by the validator check). Rule 9 REFINED (not replaced) to name the lock-time coupling tool (`vault/tools/tropo-lock-dev-spec.py`) as the PRIMARY correct-by-construction mechanism — locking a dev-spec through it atomically opens (or reuses) its correlated activation as one indivisible act; `check_dev_spec_activation_coupling` stays the always-on BACKSTOP, unmodified. Validation Check 10 unchanged. Gauntlet-proven in `test_systemic_feed_pipeline_v184.py`. | talos-t25 |
| 1.5 | 2026-07-17 | Defined the shared spec-family substrate-ref union and exact identity matching used by dev/test pairing: UID, canonical safe path, or exact opaque planned identifier. | argus-a133 |

---

*dev-spec capsule definition | LOCKED v1.8 | schema + acceptance + body-contract amendment 2026-08-03 by Argus A144 under the governed parent companion decision | prior locks preserved | First of the *-spec family*
*"The ignition key for dev-pipeline activations. Commit to what gets built before the engine fires."*
