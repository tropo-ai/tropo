---
uid: 9a7d314a
name: "doc-spec"
type: capsule-definition
extends: core
version: "1.0.2"
supersedes_version: "1.0.1"
tier: os
author: argus-a80
created: 2026-05-23
modified: 2026-06-09
created_by: argus-a80
modified_by: argus-a105
v1_0_2_amendment_note: "v1.0.1 -> v1.0.2 amendment 2026-05-25 by Argus A84 captain-mode per v1.54 cycle Lane V V3. Adds optional frontmatter field `substrate_verify_twice_findings:` mirroring the same-named field in release.capsule v3.7 (V2 paired amendment). Doc-spec instances capture substrate-verify-twice defect-class findings at authoring time (e.g., 'authored doc_changes_required entry citing capsule schema field X assumed-to-be-named foo; canonical field is bar; caught at Step 0 gate; remediated in-cycle'). Findings aggregate up to enclosing release-entry via Lane V Layer 3 cross-cycle observability ledger per O11's [83af4ac1](../../vault/files/83af4ac1.md) brief. Honor-system at v1.54.0; future cycles may add validator enforcement if drift patterns surface. Composes with Lane V Layer 2 (check_canonical_reference_shape validator in tropo-validate.py; Talos T10 lane per [137ac7e1 V1](../../vault/files/137ac7e1.md)) which catches the defect class at agent-author time + Layer 1 (voice-review.skill v1.1 Step 4.5 substrate-verify-twice discipline shipped v1.53)."
v1_0_1_amendment_note: "v1.0 → v1.0.1 amendment 2026-05-25 by orpheus-o11 during v1.53 E7 (doc-pipeline activation c7a26c5a; doc-spec c660ec29; pair with Talos T10 for engine wiring per Argus A83 directive). Adds explicit Orpheus disposition signoff gate at close: NEW Required-at-close frontmatter field orpheus_disposition_signoff (structured object with attested_by + attested_at + attestation_text + substantive_completeness enum + optional findings). NEW Validation Check 14 check_doc_spec_orpheus_disposition_signoff (WARN at v1.53; ERROR ratchet at v1.54+). NEW §Disposition Signoff body section codifying the doctrine: signoff is substantive judgment that acceptance_criteria met materially, not procedural box-check. Composes with Workbench Surface Visibility doctrine (3c02f3b7) — signoff IS the visible attestation that doc-work landed substantively. Defect class closed: v1.52 doc-pipeline first production run lacked structural enforcement that 'no minimum-viable-doc-work being skipped' per Mike-O11 directive 2026-05-24."
status: active
walk_completed_at: 2026-05-23
walk_walked_by: ["mike-maziarz", "orpheus-o11"]
walk_locked_by: mike-maziarz
enforced_enums:
  status: [draft, active, done]
meta_status_rollup:
  in-progress: [draft, active]
  done: [done]
v1_0_lock_context: "LOCKED v1.0 by Mike-A80 2026-05-23 after Walk Format Doctrine semantics walk with Orpheus O11 + Argus A80 (substrate). All 4 substantive walk-questions resolved per Q1-Q4 lock decisions in argus-orpheus channel head 2026-05-23. Refinements folded from DRAFT into v1.0: Q1 (Tier 3 cold-boot-derivability promoted to position 1 + cross-tier 'rendered human-navigation surface clean' criterion added); Q2 (new §Voice Review Definition section with 3 layers + spec-tier procedural note); Q3 (Tier 2 cross-reference wording sharpened + Check 9 scope extended to nav-block render verification); Q4 (Rule 6 prose rewritten — multi-tier shape now DEFAULT-recommended + new Check 13 soft WARN for per-tier with NEW substrate). Schema fields unchanged from DRAFT; body-prose refinements + 1 new check + 1 extended check. Phase C (doc-pipeline definition v1.0) opens now per c3dc9f00 architecture; Orpheus O11 primary; Argus engine integration."
schema_version: 2
governed_by: 222873b9   # capsule-definition meta
aligned_with:
  - "c3f68cb5"   # dev-spec.capsule v1.0 — sibling activation-input *-spec capsule (precedent)
  - "621824df"   # test-spec.capsule v1.0 — sibling *-spec capsule (parallel Phase B walk)
pattern_family: "spec-family"   # dev-spec / doc-spec / test-spec; symmetric activation-input shape across dev / doc / test pipelines
v1_0_draft_authoring_context: "Authored DRAFT by Argus A80 2026-05-23 as Phase B pre-walk Argus deliverable per v1.51 cycle brief [1feefe68 v0.2 LOCKED] + Three-Pipeline Substrate-Enforcement Architecture [c3dc9f00 v0.3] §2 sketch. Schema body authored against the precedent of dev-spec.capsule v1.0 [c3f68cb5]. Semantics walk pending with Orpheus O11 — Orpheus walks 'what makes documentation pristine across three tiers (summary / subsystem / spec)' substance + voice review semantics + cross-tier coherence semantics. Mike locks at v1.0 LOCK after walk."
member_of:
  - "8dd772a0"   # tropo-governance
---

# doc-spec — Capsule Definition v1.0 (LOCKED)

**Relations**

| Relation | Target |
|---|---|
| Governed by | [capsule-definition meta (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [dev-spec.capsule v1.0 (c3f68cb5)](dev-spec.capsule.md) — sibling activation-input *-spec capsule (precedent) |
| Aligned with | [test-spec.capsule v1.0 (621824df)](test-spec.capsule.md) — sibling *-spec capsule (parallel Phase B walk) |
| Pattern family | `spec-family` — dev-spec + doc-spec + test-spec (symmetric activation-input shape across dev / doc / test pipelines) |
| Extends | `core` |

*A doc-pipeline activation-input commitment — declares what documentation must update across three tiers (summary / subsystem / spec) to reflect a triggering dev-cycle's substrate changes. The "ignition key" for doc-pipeline activations.*

*Second of the *-spec family alongside `dev-spec` and `test-spec`. Each *-spec is the symmetric activation-input for its corresponding pipeline.*

*v1.0 DRAFT — Argus authors schema; Orpheus O11 walks "pristine three tiers" semantics; Mike locks at v1.0 LOCK after walk.*

---

## Intent

A `doc-spec` entry is a forward-looking, per-dev-cycle (or per-stream) commitment that the cycle's documentation impact is real, not implicit. It answers four questions before a doc-pipeline activation fires:

1. **Which subsystems does the triggering dev-cycle's substrate document?** Enumerated subsystem UIDs (or null for cross-subsystem); the cycle's docs must surface in at least one subsystem's hub.
2. **At which tiers must documentation update?** summary / subsystem / spec / multi — anchored to Captain's Briefing v3.0 §Structural-Enforcement Requirement 1 (pristine three tiers).
3. **What specific doc files need update?** Per-tier path list with change_summary; cross-validation against triggering dev-spec's NEW substrate.
4. **What is the acceptance criterion for clean close?** Mike-walkable verification that the documentation update is pristine, not box-checking.

The doc-pipeline engine refuses to activate without a compliant doc-spec entry. The doc-pipeline cycle cannot close until acceptance_criteria verified + voice review complete (for tiers requiring it).

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `type` | string | Literal `doc-spec` |
| `target_subsystem` | UID OR null | The subsystem being documented (subsystem hub UID), OR null for cross-subsystem changes. If null, doc-pipeline requires at least one entry in `doc_changes_required:` per tier. |
| `target_tier` | enum | `summary` / `subsystem` / `spec` / `multi`. Anchored to Captain's Briefing v3.0 §Structural-Enforcement Requirement 1. |
| `triggered_by_dev_cycle` | UID | UID of dev-pipeline activation that triggered this doc-spec (per dev-pipeline retrofit step 4.5 fire). Engine writes; honest cross-pipeline back-reference. Race-lock disambiguator per Engine Extension v0.1 §Race condition handling. |
| `doc_changes_required` | list of objects | Each object has `tier` (one of: summary / subsystem / spec), `path` (string; vault-relative path to the doc file needing update OR explicit "new-file" marker), `change_summary` (≤200 chars). |
| `acceptance_criteria` | string | Non-empty; Mike-walkable verification per Captain's Briefing v3.0 Requirement 1 framing; not box-checkable. |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `voice_review_required` | boolean | Default `true` for tiers `summary` + `subsystem`; default `false` for tier `spec`. Set explicitly to override default per cycle. Voice review = Orpheus O11 reads each updated doc + confirms voice consistency + lore-tone alignment. |
| `cross_reference_check` | boolean | Default `true` for tier `spec`; default `false` for other tiers. When true, validator extension `check_doc_spec_cross_references_resolve` runs against the doc-spec's `doc_changes_required:` paths after authoring. |
| `references_cycle_brief` | UID | Cycle brief that informs the doc-spec (composes_with; preserves cycle-brief role as exploratory cross-cycle planning). |
| `pipeline_run_uid` | UID | Backreference to the doc-pipeline-run.capsule instance this spec activated (engine writes). |
| `closed_at` | ISO 8601 | When the doc-pipeline activation closed clean (engine writes). |
| `acceptance_evidence` | list of UIDs | UIDs of substrate that ratifies acceptance_criteria met (e.g., updated doc files; voice-review notes; cross-reference audit). |
| `orpheus_disposition_signoff` | object | **REQUIRED at close (v1.0.1 NEW).** Structured Orpheus attestation that doc-pipeline work landed substantively. Schema: `attested_by:` (orpheus generation slug, e.g., `orpheus-o11`); `attested_at:` (ISO 8601); `attestation_text:` (1-3 sentence judgment); `substantive_completeness:` (enum: `PASS` / `PASS-with-findings` / `FAIL-incomplete`); optional `findings:` (list of specific items). See §Disposition Signoff body section below for the doctrine. |
| `substrate_verify_twice_findings` | list of objects | **v1.0.2+ (NEW); OPTIONAL.** Captures substrate-verify-twice defect-class instances surfaced during doc-spec authoring or doc-pipeline execution per [O11 brief 83af4ac1](../../vault/files/83af4ac1.md) Layer 3 cross-cycle observability. Each finding object: `instance_description:` (string ≤200 chars) + `canonical_uid:` (UID of referenced canonical primitive) + `canonical_field:` (field/enum/version cited that drifted) + `assumed_shape:` (what authoring agent assumed) + `actual_shape:` (canonical's actual current shape) + `catch_location:` (validator / pipeline-gate / sibling-walk / fix-on-see / sa-review) + `remediation_cycle:` (cycle UID that absorbed the fix; usually same as enclosing). Findings aggregate up to release-entry via mirror field in release.capsule v3.7. Honor-system at v1.54.0; future cycles may add validator enforcement once drift patterns surface. |

---

## State Machine

```
draft → active → done → (superseded: done + state: archived)
```

**Canonical status enum:** `status:` ∈ {draft, active, done}

| Stage | State | Meaning |
|-------|-------|---------|
| `draft` | `active` | Under authoring; engine refuses doc-pipeline activation against it |
| `active` | `active` | LOCKED at v1.0 by locking authority (Argus + Orpheus paired walk → Mike locks; or captain-mode for established cycles where Mike pre-authorized); doc-pipeline activation has fired |
| `done` | `active` | Doc-pipeline cycle closed clean; `closed_at` set; acceptance_criteria verified + voice review complete (if required); `acceptance_evidence` populated |
| `done` | `archived` | Superseded (e.g., cycle scope reshape mid-execution); requires `superseded_by:` field |

### Valid transitions
- `draft, active` → `active, active` (locking authority sets; doc-pipeline engine activates)
- `active, active` → `done, active` (engine fires at close after acceptance_criteria + voice_review verified)
- `done, active` → `done, archived` (when superseded; requires bidirectional `supersedes:` / `superseded_by:` pair)

### Invalid transitions
- `done` → `active` (cannot un-close; supersede if scope reshapes after close)
- `active` → `draft` (cannot un-lock; supersede if scope reshapes mid-cycle)

---

## Governance Rules (in addition to core)

1. **Locking authority locks v1.0** — Mike walks the cycle brief + Orpheus O11 walks the doc-spec semantics + Mike locks; captain-mode for established cycles per same pattern as dev-spec.capsule.
2. **`doc_changes_required` must list at least one entry per tier the doc-spec touches.** Anti-fuzzy-framing gate. "We'll update docs" is not a change_summary; `{tier: "summary", path: "vault/files/eca73d77.md", change_summary: "L1 canonical entry — add Three-Pipeline Substrate-Enforcement to subsystem table"}` is.
3. **Voice review gate.** For tiers `summary` + `subsystem` (where `voice_review_required: true` by default), close requires Orpheus O11 voice-review-notes entry referenced in `acceptance_evidence:`. For tier `spec`, voice review optional; technical-accuracy + cross-reference-integrity gate per `cross_reference_check:` apply instead.
4. **Cross-validation gate against triggering dev-spec.** For each dev-spec `committed_substrate` entry with `change_class: NEW`, the triggered doc-spec MUST have at least one `doc_changes_required:` entry that either (a) references the substrate's subsystem hub OR (b) explicitly justifies "no doc impact" in `change_summary` with rationale. Pristine three tiers requires that NEW substrate becomes findable for stranger-engineers + cross-referenced from hub.
5. **`acceptance_criteria` must be Mike-walkable per Captain's Briefing v3.0 Requirement 1.** Concrete enough that a reader can answer "does this read as pristine?" by reading the updated docs. Not "docs updated" but "stranger engineer reading the L1 entry cold understands Three-Pipeline Substrate-Enforcement as one of the seven subsystems; subsystem hub for dev-pipeline lists all 13 current steps; design-spec body for engine extension reads present-tense canon with no stale references."
6. **Multi-tier shape is the DEFAULT for cycles authoring NEW substrate or substantively amending substrate that has cross-tier surface** (summary mention + subsystem membership + spec body). Per-tier shape is acceptable when work is tier-isolated AND the author justifies isolation in `change_summary:` of the relevant `doc_changes_required:` entry (e.g., 'README polish; subsystem hubs unchanged; specs unchanged'). When in doubt, multi-tier — the cost of one extra `doc_changes_required:` entry is bounded; the cost of cross-tier drift is unbounded. (Rewritten v1.0 per Q4 walk lock — cross-tier coherence IS the structural value-add of having a doc-spec capsule; if the schema is shape-neutral, it doesn't enforce coherence; multi-tier default makes the preference observable + new soft WARN at Check 13 surfaces the question at authoring time without blocking legitimate per-tier cases.)
7. **Supersession requires bidirectional pointer pair.** Same as dev-spec.capsule v1.0 Rule 6 + sibling supersession discipline.
8. **Legacy grandfather (v1.10–v1.50).** Cycles pre-v1.51 grandfathered as pre-doc-spec-discipline; their cycle briefs + ship artifacts suffice as historical record. v1.51+ enforces.

---

## Validation Checks (run at vault rebuild)

In addition to core checks:

1. `check_doc_spec_required_fields` — `type` / `target_subsystem` / `target_tier` / `triggered_by_dev_cycle` / `doc_changes_required` / `acceptance_criteria` present (WARN at v1.0; ERROR ratchet at v1.1)
2. `check_doc_spec_target_subsystem_resolvable` — `target_subsystem:` UID resolves in vault index (or is explicitly `null` for cross-subsystem)
3. `check_doc_spec_target_tier_valid` — one of: summary / subsystem / spec / multi
4. `check_doc_spec_doc_changes_required_non_empty` — at least one entry per tier the spec touches (anti-fuzzy-framing)
5. `check_doc_spec_doc_changes_paths_resolvable` — each `path:` either exists at vault root OR is explicitly marked "new-file" in `change_summary:`
6. `check_doc_spec_triggered_by_dev_cycle_resolvable` — UID resolves to a dev-pipeline activation entry
7. `check_doc_spec_acceptance_criteria_present` — non-empty string
8. `check_doc_spec_voice_review_evidence_present` — if `voice_review_required: true` (or default for tier summary + subsystem), `acceptance_evidence:` must include Orpheus O11 voice-review entry UID
9. `check_doc_spec_cross_reference_check_evidence` — if `cross_reference_check: true` (or default for tier spec), `acceptance_evidence:` must include cross-reference audit entry UID. **EXTENDED v1.0 per Q3 walk lock:** check now verifies (a) all UIDs cited in body prose resolve, (b) all `member_of:` edges in frontmatter resolve, (c) **nav-block renders cleanly post-touch** (the auto-generated 📍 Path / 🔗 Self / ↓ Children / ↔ Siblings / 📥 Cited by sections via [.tropo/scripts/generate-relations-header.py](../scripts/generate-relations-header.py)). The render check catches a defect class invisible to body-prose-only audits — if a frontmatter `member_of:` edge points at an archived parent, body prose looks clean but nav-block renders broken.
10. `check_doc_spec_cross_validation_against_dev_spec` — for each `triggered_by_dev_cycle`'s dev-spec.committed_substrate entry with `change_class: NEW`, this doc-spec MUST have either (a) doc_changes_required entry referencing the substrate's subsystem hub OR (b) doc_changes_required entry with change_summary including "no doc impact: <rationale>". WARN at v1.0; ERROR ratchet at v1.2 (Rule 4 enforcement)
11. `check_doc_spec_close_invariants` — `status: done` + `state: active` requires `closed_at` + voice-review evidence (if required) + cross-reference audit (if required)
12. `check_doc_spec_supersession_bidirectional` — if `superseded_by:` set, target also has `supersedes:` pointing back (Rule 7)
13. **(NEW v1.0 per Q4 walk lock)** `check_doc_spec_per_tier_with_new_substrate` — if `target_tier:` is one of `summary`/`subsystem`/`spec` (per-tier shape) AND the triggering dev-spec's `committed_substrate` contains entries with `change_class: NEW`, fire WARN: *"per-tier doc-spec with NEW substrate from triggering dev-spec — is this really tier-isolated? Consider `target_tier: multi` or document rationale in `change_summary:`."* Soft WARN (not gating). Surfaces the multi-tier-default question at authoring time without blocking legitimate per-tier cases; authors with genuinely tier-isolated work write the rationale + the WARN clears.
14. **(NEW v1.0.1 per E7)** `check_doc_spec_orpheus_disposition_signoff` — if `status: done`, frontmatter MUST include `orpheus_disposition_signoff:` object with required subfields (`attested_by` + `attested_at` + `attestation_text` non-empty + `substantive_completeness` in enum). FAIL severity. Fires at vault rebuild + at doc-pipeline Step 5 close-gate per E7 engine wiring. **WARN at v1.53 (grace cycle); ERROR ratchet at v1.54+.** Talos T10 engineering lane: wire the check into tropo-validate.py + add Step 5 close-gate enforcement to pipeline-runtime.py (when v1.53 E6 lands doc-pipeline runtime parity).
15. **(NEW v1.0.2 per v1.54 Lane V V3)** `check_doc_spec_substrate_verify_twice_findings_shape` — if `substrate_verify_twice_findings:` field populated, each finding object MUST include `instance_description:` (non-empty string ≤200 chars) + `canonical_uid:` (resolvable UID OR explicit `"null"` marker) + `canonical_field:` (non-empty string) + `assumed_shape:` (non-empty) + `actual_shape:` (non-empty) + `catch_location:` (in enum: `validator` / `pipeline-gate` / `sibling-walk` / `fix-on-see` / `sa-review`) + `remediation_cycle:` (resolvable UID). WARN severity at v1.54.0+ (honor-system field; shape-discipline gate ensures aggregation up to release-entry remains parseable). No ERROR ratchet planned — field stays honor-system pending drift-pattern signal from future cycles.

Authoring lane for the validators: Argus (most checks; v1.51 Phase C cycle); Talos T10 for Check 14 (v1.53 E7 engine wiring); Argus captain-mode for Check 15 (v1.54 Lane V V3 schema amendment + shape-validator; Python implementation paired with Lane V V1 in same Talos engineering pass).

---

## Pristine Three Tiers — LOCKED v1.0

*LOCKED v1.0 by Mike-A80 + Orpheus O11 walk 2026-05-23. Refinements per Q1 + Q3 walk locks folded into Tier 3 (cold-boot-derivability promoted to position 1; spec-tier procedural note added) + Tier 2 (cross-reference wording sharpened — strict on members, medium on adjacency) + cross-tier criterion (rendered human-navigation surface clean) added.*

### Tier 1 — Summary

- **Audience:** stranger encountering Tropo for the first time
- **Surface:** L1 canonical entry [eca73d77](../../vault/files/eca73d77.md); README; tropo-ai.com homepage content
- **Pristine criteria:**
  - Cold-readable by stranger without external context
  - All operational subsystems mentioned (currently: agent lifecycle / vault / tropo-work / import / publish-pipeline + v1.51-adds: doc-pipeline + test-pipeline)
  - No stale references to retired primitives (e.g., no pre-v1.8 vocabulary; no references to deleted/superseded UIDs)
  - Subsystem table current
- **Voice review:** required; Orpheus O11 voice-tone consistency check (per §Voice Review Definition below)
- **Cross-reference check:** light; references resolve but exhaustive integrity not required at this tier
- **Rendered human-navigation surface clean** (cross-tier criterion per Q1 walk lock) — see Cross-tier criterion below

### Tier 2 — Subsystem

- **Audience:** Tropo user navigating subsystems; engineer implementing against a subsystem
- **Surface:** Subsystem hubs (e.g., [tropo-governance (8dd772a0)](../../vault/files/8dd772a0.md); [tropo-agents (99ed55fd)](../../vault/files/99ed55fd.md); etc.)
- **Pristine criteria:**
  - Each subsystem's hub entry current (members; capability references; latest cycle's deltas surfaced)
  - Tools / skills / scripts inventoried (capability catalogs current)
  - Cross-subsystem composition explicit (when subsystem X composes with subsystem Y, both hubs reference)
  - No stale members list (deleted/archived entries pruned from members:)
- **Voice review:** required; Orpheus O11 tone + lore-consistency check (per §Voice Review Definition below)
- **Cross-reference check (per Q3 walk lock):** strict on members + capability references (navigation surface; broken member = broken navigation); medium on adjacency (composes_with edges, related-subsystems pointers). Tier 2 hubs are the navigation backbone; member integrity is load-bearing for navigation (broken member UIDs land users on 404); adjacency is softer because it's orientation, not navigation
- **Rendered human-navigation surface clean** (cross-tier criterion per Q1 walk lock) — see Cross-tier criterion below

### Tier 3 — Spec

- **Audience:** engineer or governance authority needing canonical architectural reference
- **Surface:** Capsule definitions (.tropo/capsules/*.capsule.md); architectural specs (vault/files/<uid>.md type:arch-spec OR type:design-spec); ADRs; locked governance docs
- **Pristine criteria (cold-boot-derivability is the load-bearing sufficiency condition; promoted to position 1 per Q1 walk lock):**
  - **Stranger-engineer can derive correct behavior from spec alone (cold-boot proof)** — load-bearing sufficiency condition; the criteria below are necessary but not sufficient. If a stranger engineer cannot enact the spec's contract from the body alone, the spec is not pristine regardless of how current the cross-references are
  - Latest canonical architectural specifications + capsule definitions current
  - **NOT DATED** — body reads present-tense canon; history accessible via amend_history but body doesn't say "as of 2026-05-23"
  - Cross-reference integrity (every UID cited resolves; every aligned_with target exists)
  - State machine + governance rules align with current substrate (e.g., dev-spec.capsule v1.0 state machine matches what engine extension v0.2 enforces)
- **Voice review:** optional; technical-accuracy + cross-reference-integrity gate substitute
- **Spec-tier procedural note (per Q2 walk lock):** *For spec-tier docs, authors should self-request voice spot-check on prose-heavy sections (§Intent, §Why, §Studio Shop Signage, §How to Validate body prose) when substantively changed. Spot-check is not gating; it is discipline. The voice-review default remains `false` for spec tier.*
- **Cross-reference check:** required + strict

### Cross-tier criterion (applies to ALL three tiers per Q1 walk lock)

- **Rendered human-navigation surface clean.** nav-block (📍 Path / 🔗 Self / ↓ Children / ↔ Siblings / 📥 Cited by) renders correctly; body prose uses readable-name-first citations not bare UIDs per OP-12; specific style rules (em-dash discipline per Mike binding pin; voice-tone per §Voice Review Definition) operationalize through the voice-review skill definition rather than capsule body enumeration. Capsule body commits the criterion; the voice-review skill enforces the specifics.

---

## Inheritance

Extends `core`. Inherits all core rules + frontmatter floor.

---

## Disposition Signoff (LOCKED v1.0.1 per E7; 2026-05-25 orpheus-o11 + Talos T10 pair)

*The signoff gate is the structural enforcement that doc-pipeline work landed substantively, not procedurally. Per Mike-O11 directive 2026-05-24 post-v1.52 first production run: "the purpose of this pipeline is to ensure we update our canonical documentation with every single release." The signoff makes that purpose machine-checkable.*

At doc-pipeline Step 5 close-activation, Orpheus MUST populate `orpheus_disposition_signoff:` with substantive attestation BEFORE the doc-spec can flip `stage: active → done`. The attestation is judgment, not checklist:

### Schema

```yaml
orpheus_disposition_signoff:
  attested_by: orpheus-o11            # current Orpheus generation slug
  attested_at: 2026-05-25T15:30:00Z   # ISO 8601 timestamp at close
  attestation_text: |                  # 1-3 sentence judgment in plain English
    Doc-pipeline activation met acceptance_criteria substantively. D1 hub
    refreshes through v1.52 currency landed across 6 hubs; D2 capsule body
    restructurings extended substrate-preservation + composability narratives;
    D3 L1 polish + Three-Pipeline currency added. No minimum-viable shortcuts.
  substantive_completeness: PASS       # enum: PASS / PASS-with-findings / FAIL-incomplete
  findings: []                         # optional list of specific items if PASS-with-findings or FAIL
```

### Enum semantics

- **PASS** — doc-pipeline work met the acceptance criteria substantively. Reader of the updated docs would say "this is pristine, not aspirational." Activation closes clean.
- **PASS-with-findings** — acceptance criteria met BUT specific items deserve surfacing for next cycle (e.g., adjacent substrate that could not be touched in scope; carry-forward observations). Activation closes; findings file to doc-pipeline/01-inbox (b48ba471).
- **FAIL-incomplete** — acceptance criteria NOT met materially. Specific items in findings name the gaps. Activation does NOT close; remediation per finding; re-attempt close after gaps addressed.

### What the signoff is NOT

- **Not a checklist gate.** Each item in `doc_changes_required:` being touched is not sufficient; Orpheus reads the work + judges whether the touch was substantive.
- **Not a delegation surface.** Orpheus attests personally per generation (attested_by names the generation slug). Another agent cannot sign off on Orpheus's behalf.
- **Not a verification of every line.** The signoff IS judgment that the acceptance_criteria (Mike-walkable per Captain's Briefing v3.0 Requirement 1) hold materially. Spot-checks + voice review + cross-reference audit produce the evidence; the signoff is the reading of that evidence.

### Composition

- **[Workbench Surface Visibility doctrine (3c02f3b7)](../../vault/files/3c02f3b7.md)** — signoff IS visible attestation that doc-work landed substantively. Without the signoff, completed doc-work without surface = dropped work per the doctrine.
- **[voice-review.skill v1.1 (811856a5)](../skills/voice-review.skill.md)** — Step 3 voice-review notes feed the signoff's evidence base; substrate-verify-twice discipline (v1.1 Step 4.5) self-applies to the signoff text itself (Orpheus verifies the attestation text claims hold against the actual substrate touched).
- **[substrate-verify-twice brief (83af4ac1)](../../vault/files/83af4ac1.md)** — the signoff is the structural enforcement layer that the brief's Layer 1 (skill discipline) + Layer 2 (validator) + Layer 3 (cross-cycle ledger) compose against.
- **doc-pipeline Step 5 close-activation (343dd5d8)** — the operational gate; engine refuses close without the signoff object well-formed (Talos T10 engine wiring).

### v1.52 first-run gap (defect class this closes)

The v1.52 doc-pipeline first production run (activation 461b3896) closed without explicit substantive-completeness attestation. Mike-O11 caught the gap post-close: *"did you sign off on your pipeline and report back?"* The retrospective ops.md bulletin landed AFTER close, not BEFORE. v1.0.1 makes the attestation a structural requirement at close, not an afterthought.

---

## Voice Review Definition (LOCKED v1.0 per Q2 walk lock)

*When an author sets `voice_review_required: true` (default for summary + subsystem tiers), three layers operationalize the term. Orpheus O11 walks each layer at voice-review-evidence-fire time:*

1. **Tone consistency** — sounds like Tropo (plain English, precise, functional); not academic, not marketing-fluff, not aspirational; no em-dashes (per Mike binding pin)
2. **Lore alignment** — framing matches canonical taxonomy (Tropo / Studio / Vault), operating values, soul-level voice discipline
3. **Stranger-encounter test** — first-time reader can follow; not written for the crew

The specific style rules (em-dash discipline, voice-tone catalog, etc.) live in the voice-review skill definition (forthcoming Phase C as the doc-pipeline Step 2 author-doc-updates substrate); not enumerated in capsule body to avoid drift between capsule + skill.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author a doc-spec.*

**Tools available:**
- `vault/00-index.jsonl` — grep `type: doc-spec` for live doc-pipeline activations
- `vault/00-index.jsonl` — find triggering dev-spec by `triggered_by_dev_cycle:` UID
- `.tropo-studio/registries/subsystem-registry.jsonl` — subsystem hub UIDs + current scope
- Companion capsules: [dev-spec.capsule v1.0 (c3f68cb5)](dev-spec.capsule.md); [test-spec.capsule v1.0 (621824df)](test-spec.capsule.md) — sibling *-spec capsules
- doc-pipeline definition (forthcoming Phase C; Orpheus O11 primary owner)

**Skills (forthcoming v1.51):**
- `author-doc-spec.skill.md` — scaffold the spec from a triggering dev-spec; pre-fill `triggered_by_dev_cycle:` + propose `target_subsystem:` + `target_tier:` based on dev-spec.committed_substrate
- `lock-doc-spec.skill.md` — Argus + Orpheus paired walk → Mike-walk gate → lock; on lock, doc-pipeline engine activates
- `close-doc-spec.skill.md` — at cycle close, verify acceptance_criteria + voice-review + cross-reference audit; populate `closed_at` + `acceptance_evidence`

**Rules (at-a-glance):**
1. Locking authority locks v1.0
2. `doc_changes_required` is anti-fuzzy — at least one entry per tier with concrete change_summary
3. Voice review gate for summary + subsystem tiers
4. Cross-validation against triggering dev-spec (NEW substrate must surface in docs)
5. Acceptance criteria Mike-walkable per Captain's Briefing v3.0 Requirement 1
6. Multi-tier shape OR per-tier shape
7. Supersession bidirectional
8. Legacy v1.10–v1.50 grandfathered

**Pitfalls:**
- **Fuzzy `doc_changes_required`** — Validation Check 4 violation; concrete path + change_summary required
- **Missing voice review evidence for summary/subsystem tiers** — Validation Check 8 violation; Orpheus voice-review-notes UID required in acceptance_evidence
- **NEW substrate without doc impact entry** — Validation Check 10 violation; if dev-spec lists NEW substrate target, doc-spec must surface it OR explicitly justify "no doc impact"
- **Spec tier docs that drift toward "as of <date>"** — pristine criteria violation; body reads present-tense canon
- **Locking without `## How to Validate` section** — same pattern as design-spec.capsule v2.1; body section required pre-lock

**Worked examples (forthcoming Phase D):**
- v1.51 cycle's own doc-spec — Argus authors at trigger fire (step 4.5); Orpheus O11 walks doc-pipeline activation; closes at Phase D. Will become the first instance.
- Composition example: dev-spec.committed_substrate NEW entry for [dev-spec.capsule v1.0](dev-spec.capsule.md) → doc-spec doc_changes_required entry for tier:summary updating L1 entry + tier:subsystem updating tropo-governance hub.

**Go next:**
- Sibling activation-input capsule → [dev-spec.capsule v1.0 (c3f68cb5)](dev-spec.capsule.md) — precedent shape
- Sibling activation-input capsule → [test-spec.capsule v1.0 (621824df)](test-spec.capsule.md) — parallel Phase B walk
- Pipeline class → doc-pipeline definition (forthcoming Phase C; Orpheus O11 primary)
- Architectural parent → [Three-Pipeline Substrate-Enforcement Architecture v0.3 (c3dc9f00)](../../vault/files/c3dc9f00.md) §2
- Strategic-frame parent → [Captain's Briefing v3.0 (a5f4b26b)](../../vault/files/a5f4b26b.md) §Structural-Enforcement Requirement 1 (pristine three tiers)

---

## How to Validate

*Required per design-spec.capsule v2.1 Rule 4 lock prerequisite shape.*

Phase B acceptance test (the capsule is shipped when these pass):
1. Mike + Orpheus O11 + Argus walk the schema + pristine-three-tiers semantics; lock at v1.0
2. Author first instance (Phase D triggered by v1.51 dev-pipeline step 4.5) — schema passes all 12 validation checks at WARN level
3. doc-pipeline definition (Phase C; Orpheus primary) activates against the first doc-spec instance; cycle closes clean
4. Cross-validation gate (Check 10) fires correctly against v1.51 dev-spec committed_substrate

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.2 | 2026-05-25 | **v1.0.2 amendment** by Argus A84 captain-mode per v1.54 cycle Lane V V3 (composes with [cycle brief 5d0c831f v0.2 LOCKED](../../vault/files/5d0c831f.md) + [dev-spec 137ac7e1 v1.0 LOCKED](../../vault/files/137ac7e1.md)). Adds optional frontmatter field `substrate_verify_twice_findings:` mirroring release.capsule v3.7 same-named field; doc-spec instances capture defect-class findings at authoring/execution time, aggregate up to enclosing release entry. NEW Validation Check 15 `check_doc_spec_substrate_verify_twice_findings_shape` (WARN at v1.54.0+; honor-system field; no ERROR ratchet planned). Composes with Lane V Layer 1 (voice-review.skill v1.1 Step 4.5 substrate-verify-twice discipline; shipped v1.53) + Layer 2 (check_canonical_reference_shape validator in tropo-validate.py; Talos T10 lane). | argus-a84 |
| 1.0.1 | 2026-05-25 | **v1.0.1 amendment** by Orpheus O11 during v1.53 E7. Added `orpheus_disposition_signoff:` Required-at-close field + Validation Check 14 + §Disposition Signoff body section. Composes with Workbench Surface Visibility doctrine; closes v1.52 first-production-run "no minimum-viable shortcuts" enforcement gap per Mike-O11 directive 2026-05-24. | orpheus-o11 |
| 1.0 | 2026-05-23 | **LOCKED v1.0** by Mike-A80 + Orpheus O11 walk. Four Q1-Q4 walk locks folded from DRAFT: Q1 (Tier 3 cold-boot-derivability promoted to position 1; cross-tier "rendered human-navigation surface clean" criterion added applying to all three tiers); Q2 (new §Voice Review Definition section with 3 layers — tone consistency + lore alignment + stranger-encounter test; spec-tier procedural note added to Tier 3 sub-section); Q3 (Tier 2 cross-reference wording sharpened — strict on members + medium on adjacency; Check 9 scope EXTENDED to verify (a) body-prose UID resolution + (b) member_of: frontmatter edge resolution + (c) nav-block render verification post-touch); Q4 (Rule 6 prose REWRITTEN — multi-tier shape now DEFAULT-recommended for cycles with cross-tier surface; new Check 13 soft WARN `check_doc_spec_per_tier_with_new_substrate` surfaces multi-tier-default question at authoring time without blocking legitimate per-tier cases). Schema fields unchanged from DRAFT (booleans + enums stable; UID c3f68cb5 sibling preserved as v1.0 architectural precedent). Body-prose refinements + 1 new check + 1 extended check. Authoring lane: Argus authors validator extensions; Orpheus O11 owns Voice Review Definition semantics + Phase C doc-pipeline definition v1.0 (post-lock). | argus-a80 + orpheus-o11 + mike-a80 |
| 1.0-DRAFT | 2026-05-23 | Initial DRAFT authored. Schema modeled on dev-spec.capsule v1.0 precedent. Pristine-three-tiers first-draft semantics captured for Orpheus O11 walk. Cross-validation gate against triggering dev-spec (Rule 4 + Check 10). Voice review gate for summary + subsystem tiers (Rule 3 + Check 8). Multi-tier OR per-tier shape (Rule 6). Authored by Argus A80 as Phase B pre-walk Argus deliverable per v1.51 cycle. **Pending Orpheus O11 + Mike walk; lock at v1.0 LOCK after.** | argus-a80 |

---

*doc-spec capsule definition | UID `9a7d314a` | v1.0.2 LOCKED | v1.0.2 amendment 2026-05-25 by Argus A84 captain-mode (v1.54 Lane V V3 substrate_verify_twice_findings field). v1.0.1 amendment 2026-05-25 by Orpheus O11 (v1.53 E7 orpheus_disposition_signoff). v1.0 LOCKED 2026-05-23 by Mike-A80 + Orpheus O11 walk.*
*"The ignition key for doc-pipeline activations. Pristine three tiers: summary cold-readable; subsystem hub current; spec body present-tense canon."*
