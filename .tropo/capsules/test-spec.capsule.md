---
uid: 621824df
name: "test-spec"
type: capsule-definition
extends: core
version: "1.1"
v1_1_amendment_note: "v1.0 → v1.1 amendment 2026-05-28 by Argus A87 captain-mode per v1.59 dev-spec d8c3f1b7 V1 + Mike-A87 walk lock by-number 2026-05-28. Paired with dev-spec.capsule v1.0 → v1.1 amendment (acceptance_criteria formalized to list of strings; cross-validation pairing rule added). Three changes. (1) behaviors_covered entry shape extended with NEW optional verifies_acceptance_criterion:<int> field — 1-based positional index pointing at an entry in the triggering dev-spec.acceptance_criteria list. Required-via-aggregate (Rule 3 extension): every dev-spec.acceptance_criteria entry MUST have at least one paired behaviors_covered entry referencing it; not every behaviors_covered entry needs to point at a criterion (a behavior may verify substrate without an explicit criterion). (2) Rule 3 extended: existing cross-validation against dev-spec.committed_substrate NEW entries (MANDATED at v1.0 per V51 pattern) is preserved unchanged; NEW parallel cross-validation against dev-spec.acceptance_criteria entries added. Engine refusal at test-pipeline activation OR test-spec lock if either coverage check fails. (3) Validation Check 6 (check_test_spec_cross_validation_against_dev_spec) extended to cover both target_substrate AND acceptance_criteria coverage. WARN at v1.1 grace period; ERROR ratchet at v1.2 (matching existing v1.0 ratchet pattern). Substantive architecture (anti-box-checking gate + manual_walk ceiling + cycle_class minima + 5-method verification enum) unchanged from v1.0 - only behaviors_covered shape extended + Rule 3 extended + Check 6 extended. Empirical dogfood: Vela V54 v1.59 test-spec at 6183301b authored 2026-05-28 already populated verifies_acceptance_criterion on every behavior — proof that the field-shape works in practice + cycle's own test-spec verifies its own structural amendments (acceptance criterion 5 of v1.59 cycle scope)."
tier: os
author: argus-a80
created: 2026-05-23
modified: 2026-06-14
created_by: argus-a80
modified_by: argus-a114
v1_1_rollup_amendment_note: "2026-06-14 Argus A114 (in-place v1.1 gap-fill; NO version bump — keeps v1.1 deliberately to avoid prematurely tripping the Check-6 v1.2 ERROR ratchet, a separate governance decision): added `locked` + `archived` to meta_status_rollup.done. Rationale: test-spec is a spec-family sibling of dev-spec + design-brief, both of which map locked→done; a test-spec locks WITH its dev-spec. The v1.71 loop-primitive lock (test-spec 18627ea6) surfaced this — a locked test-spec resolved lifecycle-N/A (M2 FAIL). Pure consistency gap-fill; no change to existing mappings."
status: active
walk_completed_at: 2026-05-23
walk_walked_by: ["mike-maziarz", "vela-v51"]
walk_locked_by: mike-maziarz
enforced_enums:
  status: [draft, active, done, locked, archived]
meta_status_rollup:
  in-progress: [draft, active]
  done: [done, locked, archived]   # +locked,+archived (Argus A114 2026-06-14): a test-spec locks WITH its dev-spec per the spec-family symmetry; dev-spec + design-brief already map locked→done. Gap-fill — a locked test-spec was resolving lifecycle-N/A (M2 FAIL, surfaced by the v1.71 loop-primitive lock 18627ea6).
schema_version: 2
governed_by: 222873b9   # capsule-definition meta
aligned_with:
  - "c3f68cb5"   # dev-spec.capsule v1.0 — sibling activation-input *-spec capsule (precedent)
  - "9a7d314a"   # doc-spec.capsule v1.0 — sibling *-spec capsule (parallel Phase B walk)
pattern_family: "spec-family"   # dev-spec / doc-spec / test-spec; symmetric activation-input shape across dev / doc / test pipelines
v1_0_lock_context: "LOCKED v1.0 by Mike-V51 2026-05-23 after Walk Format Doctrine semantics walk with Vela V51 + Argus A80 (substrate). All 5 substantive questions Argus surfaced resolved with Mike agreement. Lock decisions in §Walk Lock Decisions. DRAFT authored by Argus A80 2026-05-23 as Phase B pre-walk Argus deliverable per v1.51 cycle brief [1feefe68 v0.2 LOCKED] + Three-Pipeline Substrate-Enforcement Architecture [c3dc9f00 v0.3] §3 sketch. Schema body authored against the precedent of dev-spec.capsule v1.0 [c3f68cb5]. Phase C (test-pipeline definition v1.0) opens now per c3dc9f00 architecture; Vela primary; Argus engine integration; Talos engineering."
member_of:
  - "8dd772a0"   # tropo-governance
---

# test-spec — Capsule Definition v1.0 (LOCKED)

**Relations**

| Relation | Target |
|---|---|
| Governed by | [capsule-definition meta (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [dev-spec.capsule v1.0 (c3f68cb5)](dev-spec.capsule.md) — sibling activation-input *-spec capsule (precedent) |
| Aligned with | [doc-spec.capsule v1.0 (9a7d314a)](doc-spec.capsule.md) — sibling *-spec capsule (parallel Phase B walk) |
| Pattern family | `spec-family` — dev-spec + doc-spec + test-spec (symmetric activation-input shape across dev / doc / test pipelines) |
| Extends | `core` |

*A test-pipeline activation-input commitment — declares what test coverage must extend to exercise behaviors a triggering dev-cycle introduces. The "ignition key" for test-pipeline activations.*

*Third of the *-spec family alongside `dev-spec` and `doc-spec`. Each *-spec is the symmetric activation-input for its corresponding pipeline.*

*v1.0 LOCKED 2026-05-23 by Mike-V51 after Walk Format Doctrine semantics walk with Vela V51 + Argus A80 (substrate). All 5 substantive questions resolved with Mike agreement. See §Walk Lock Decisions for the resolved calls; Phase C (test-pipeline definition v1.0) opens now per c3dc9f00 architecture.*

---

## Intent

A `test-spec` entry is a forward-looking, per-dev-cycle (or per-stream) commitment that the cycle's behaviors will be exercised, not box-checked. It answers four questions before a test-pipeline activation fires:

1. **Which substrate does this test coverage exercise?** Enumerated dev-cycle's NEW substrate UIDs (target_substrate); the cross-validation join with dev-spec.committed_substrate.
2. **What behaviors does the test exercise?** Anti-box-checking gate — each `behaviors_covered` entry must declare a `verification_method` that deterministically establishes whether the behavior holds.
3. **What coverage class is this?** regression / smoke / cold-boot / gauntlet / property — each class has semantic + verification_method defaults Vela walks Phase B.
4. **What is the acceptance criterion for clean close?** Mike-walkable verification that the test coverage is real, not cosmetic.

The test-pipeline engine refuses to activate without a compliant test-spec entry. The test-pipeline cycle cannot close until acceptance_criteria verified + tests pass + behaviors_covered cross-validates against triggering dev-spec.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `type` | string | Literal `test-spec` |
| `target_substrate` | UID array | UIDs of substrate the test coverage exercises (typically the dev-cycle's `committed_substrate` entries with `change_class: NEW`). Cross-validates against triggering dev-spec per Rule 4 + Check 10. |
| `target_subsystem` | UID OR null | The subsystem the substrate composes with (subsystem hub UID), OR null for cross-subsystem. |
| `triggered_by_dev_cycle` | UID | UID of dev-pipeline activation that triggered this test-spec (per dev-pipeline retrofit step 4.6 fire). Engine writes; honest cross-pipeline back-reference. Race-lock disambiguator per Engine Extension v0.1 §Race condition handling. |
| `behaviors_covered` | list of objects | **Anti-box-checking gate.** Each object has: `behavior_description` (≤200 chars; what the behavior is), `test_substrate_path` (string; vault-relative path to the test substrate that exercises this behavior — must exist OR be authored as part of cycle), `verification_method` (enum; see below), `target_substrate_refs` (UID array; which dev-spec NEW substrate entries this behavior covers), `dispatch_target` (string; REQUIRED when `verification_method: agentic_review` — names the sa.* class to dispatch, e.g., `sa.skeptic` / `sa.cold-boot`), `verifies_acceptance_criterion` (integer; OPTIONAL per-entry but REQUIRED-via-aggregate per Rule 3 v1.1 extension — every dev-spec.acceptance_criteria entry MUST have at least one paired behaviors_covered entry pointing at it; 1-based positional index into triggering dev-spec.acceptance_criteria list). |
| `coverage_class` | enum | `regression` / `smoke` / `cold-boot` / `gauntlet` / `property`. Semantics + verification_method defaults per §Coverage Class Semantics below. |
| `acceptance_criteria` | string | Non-empty; Mike-walkable verification that test coverage is real not box-checking; per Captain's Briefing v3.0 Requirement 2 framing. |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `existing_test_substrate_extended` | list of paths | List of existing test files this spec extends (vs new test substrate). When non-empty, validator extension verifies extensions don't break existing coverage. |
| `harness_framework_changes_required` | boolean | Default `false`. If `true`, cycle scope EXPANDS to include the harness extension authoring (Vela authors substrate; Talos engineers; Argus reviews capsule/spec amendments). Cycle close gated on harness extension landing + working — not just the test-spec closing clean. Three trigger classes per §Harness Framework Changes — Triggers + Scope Expansion. |
| `manual_walk_percentage_ceiling` | integer | Default 30. Maximum percentage of `behaviors_covered` entries that may use `verification_method: manual_walk`. Forces majority machine-side coverage (machine_executable_script + deterministic_assertion + structural_check + agentic_review). Manual_walk is Mike opt-in supplemental per Captain's Briefing v3.0 Requirement 3. |
| `manual_walk_ceiling_override` | integer | Optional per-cycle override of `manual_walk_percentage_ceiling`. HARD CAP at 50 (override above 50 is invalid; if more than half your coverage needs Mike to walk it manually, that's not a test-spec — it's a cold-boot-walk class cycle which sets ceiling to 100 via `coverage_class: cold-boot` flag instead). Requires `override_rationale:` field non-empty + ≥100 chars + Mike-walked at lock-time. |
| `override_rationale` | string | REQUIRED when `manual_walk_ceiling_override:` is set. Free-text rationale Mike walks at lock-time. ≥100 chars. |
| `cycle_class` | enum | Required at v1.1+ (optional at v1.0); one of `substrate` / `ux` / `engine-runtime`. Drives `coverage_class:` minima per §Coverage Class Semantics. If absent at v1.0, validator infers from triggering dev-spec target_substrate types (WARN-only at v1.0). |
| `references_cycle_brief` | UID | Cycle brief that informs the test-spec. |
| `pipeline_run_uid` | UID | Backreference to the test-pipeline-run.capsule instance this spec activated (engine writes). |
| `closed_at` | ISO 8601 | When test-pipeline activation closed clean (engine writes). |
| `acceptance_evidence` | list of UIDs | UIDs of substrate that ratifies acceptance_criteria met (test run results; coverage audit; harness extension entries). |

---

## State Machine

```
draft → active → done → (superseded: done + state: archived)
```

**Strict status enum:** `status:` ∈ {draft, active, done, locked, archived}

| Stage | State | Meaning |
|-------|-------|---------|
| `draft` | `active` | Under authoring; engine refuses test-pipeline activation against it |
| `active` | `active` | LOCKED at v1.0 by locking authority (Argus + Vela paired walk → Mike locks; or captain-mode for established cycles); test-pipeline activation has fired |
| `done` | `active` | Test-pipeline cycle closed clean; `closed_at` set; tests pass + coverage audit complete |
| `done` | `archived` | Superseded; requires `superseded_by:` field |

Valid + invalid transitions same shape as dev-spec.capsule v1.0 + doc-spec.capsule v1.0.

---

## Governance Rules (in addition to core)

1. **Locking authority locks v1.0** — Argus + Vela paired walk + Mike locks; captain-mode for established cycles.
2. **Anti-box-checking gate** — `behaviors_covered` must satisfy ALL of:
   - **Non-empty** (covers at least one behavior per `target_substrate` entry per Rule 3 cross-validation)
   - **Each entry has `verification_method` declared** (one of: `machine_executable_script` / `deterministic_assertion` / `structural_check` / `agentic_review` / `manual_walk`) — five-entry enum LOCKED v1.0 per Walk Lock Decision SQ2
   - **For `verification_method: machine_executable_script`**: `test_substrate_path` MUST point at a real `.py` / `.sh` / `.ts` (or other-executable) file that exits non-zero if the behavior breaks
   - **For `verification_method: deterministic_assertion`**: assertion expressed as exit_criteria DSL (per pipeline.capsule v3.0 §6); must pass against substrate
   - **For `verification_method: structural_check`**: substrate-coherence check via validator extension (tropo-validate.py); validator extension authored as part of cycle
   - **For `verification_method: agentic_review`**: sa.* class dispatched per `dispatch_target:` (e.g., `sa.skeptic` hostile-implementer / `sa.cold-boot` stranger-walk); dispatched at test-pipeline activation time per standard sa.* commissioning protocol (e863a1e0); verdict via [RESPONSE] block; counts as machine-side for ceiling math (it's dispatched, not Mike-walked)
   - **For `verification_method: manual_walk`**: human-runnable check explicitly marked as Mike opt-in supplemental per Captain's Briefing v3.0 Requirement 3; counts against `manual_walk_percentage_ceiling`
3. **Cross-validation gate against triggering dev-spec** (MANDATED, not convention per Walk Lock Decision SQ1) — TWO parallel coverage checks at v1.1+; both MUST pass at test-pipeline activation OR test-spec lock; engine refuses if either fails.

   **3.a — committed_substrate NEW coverage** (v1.0 baseline; unchanged at v1.1): for each dev-spec `committed_substrate` entry with `change_class: NEW`, at least one `behaviors_covered` entry MUST have `target_substrate_refs:` containing that UID. Captures the anti-bypass-pattern lesson from v1.40-v1.49 substrate-discipline arc. Structural-only substrate (e.g., capsule definitions with no behavioral surface) satisfies via `coverage_class: structural_check` — the validator extension firing IS the behavior; no exception marker needed.

   **3.b — acceptance_criteria coverage** (v1.1 NEW per v1.59 V1 amendment; Mike-A87 walk lock by-number 2026-05-28): for each entry in dev-spec.acceptance_criteria (1-based positional index), at least one `behaviors_covered` entry MUST have `verifies_acceptance_criterion:` set to that entry's index. Captures the architect-doesn-t-operate-under-his-own-protocol failure family (stm-a87-002 + sibling pins) by structurally enforcing that every cycle success condition has at least one behavioral verifier. Behaviors may verify substrate without an explicit acceptance criterion (`verifies_acceptance_criterion` is optional per-entry but required-via-aggregate); a dev-spec.acceptance_criteria entry with zero behaviors_covered pointers is a Rule 3.b violation. WARN at v1.1 grace period; ERROR ratchet at v1.2 (matching existing v1.0 ratchet pattern). Index-stability honest tradeoff: reordering or middle-insertion of acceptance_criteria entries shifts later indices; v1.60+ ratchet to by-name stable IDs available if reorder-breakage becomes empirical pattern.
4. **`manual_walk_percentage_ceiling`** — defaults to 30%. At least 70% of behaviors_covered entries must use machine-side verification_method (machine_executable_script + deterministic_assertion + structural_check + agentic_review). Forces majority structural enforcement; manual_walk is Mike-opt-in supplemental. Per-cycle override via `manual_walk_ceiling_override:` integer + `override_rationale:` string (≥100 chars; Mike-walked at lock-time). **HARD CAP at 50%** — override above 50 invalid; if more than half coverage needs Mike to walk it manually, that's a cold-boot-walk class cycle which sets ceiling to 100 via `coverage_class: cold-boot` flag, not via override (per Walk Lock Decision SQ3).
5. **`acceptance_criteria` must be Mike-walkable per Captain's Briefing v3.0 Requirement 2.** Concrete enough that a reader can answer "does this exercise the substrate?" by reading the test substrate. Not "tests cover the cycle" but "test_substrate at .tropo/scripts/test_pipeline_runtime_coupling.py executes the 6 smoke tests enumerated in [Engine Extension v0.1 §How to Validate]; each exits non-zero on coupling failure; harness aggregation reports per-test pass/fail."
6. **`coverage_class` semantics + verification_method defaults** — per §Coverage Class Semantics below.
7. **Supersession requires bidirectional pointer pair.** Same as sibling *-spec capsules.
8. **Legacy grandfather (v1.10–v1.50).** Cycles pre-v1.51 grandfathered as pre-test-spec-discipline; their per-release vela-test-plan substrate suffices as historical record. v1.51+ enforces.

---

## Coverage Class Semantics — LOCKED v1.0

*LOCKED v1.0 by Mike-V51 2026-05-23 per Walk Lock Decision SQ4. Refactored from Argus's first-draft per-substrate-entry minima into cleaner per-cycle-class minima — drives off `cycle_class:` (substrate / ux / engine-runtime), not per-substrate-entry book-keeping.*

### Coverage classes (the 5 lenses)

| Class | Catches | verification_method default |
|---|---|---|
| `regression` | Behavior breaks of EXISTING substrate (pre-cycle behavior still holds) | `machine_executable_script` (typically) |
| `smoke` | Minimum-viable-shape proof; substrate exists + responds | `deterministic_assertion` OR `structural_check` |
| `cold-boot` | Stranger-encounter test; substrate teaches-itself per HUMAN-NAVIGATION primitive | `manual_walk` (Mike opt-in) OR `agentic_review` (sa.cold-boot dispatched) |
| `gauntlet` | Hostile-implementer review (R1+ paired); architectural-soundness lens | `agentic_review` (sa.skeptic dispatched) + `structural_check` (validator extension) |
| `property` | Invariant-holds-across-cases; for-all input combinations output structure holds | `machine_executable_script` (property-based test) |

### Per-cycle-class required minima (the three cycle classes)

| `cycle_class:` | What it is | Required coverage classes (floor) | Conditional |
|---|---|---|---|
| `substrate` | Crew-internal substrate; no user-facing UX surface (e.g., v1.50 registry primitive establishment) | `smoke` + `structural_check` | `gauntlet` REQUIRED if any target_substrate is OS-tier (capsule definition / engine extension / OS-primitive); `regression` REQUIRED if any target_substrate AMENDS or REFACTORS existing behavior |
| `ux` | User-facing surface ships; stranger-encounter applies (e.g., v1.49 publish.pipeline + KGAE) | `smoke` + `cold-boot` | `regression` REQUIRED if any target_substrate AMENDS existing UX |
| `engine-runtime` | Engine code, validator extension, CLI script, runtime substrate | `smoke` + `property` | `regression` REQUIRED if substrate amends existing runtime; `gauntlet` REQUIRED if substrate is engine-extension class |

**Cross-class rule:** a single behavior_covered entry MAY satisfy multiple coverage_class slots (e.g., a cold-boot-walk that's ALSO a smoke test counts for both). Validator extension `check_test_spec_coverage_class_completeness` checks per-cycle-class minima per the table above against `cycle_class:` value.

**Inference fallback (v1.0):** If `cycle_class:` absent at v1.0 (optional at v1.0; required at v1.1+), validator infers from triggering dev-spec target_substrate types: capsule-definition / engine-extension / OS-primitive → `substrate` (with conditional gauntlet floor); page-tier / subsystem-doc → `ux`; engine code / validator extension / CLI script → `engine-runtime`. Inference at WARN-only at v1.0; explicit declaration ratchets to required at v1.1.

---

## Harness Framework Changes — Triggers + Scope Expansion

*LOCKED v1.0 by Mike-V51 2026-05-23 per Walk Lock Decision SQ5. Names what specifically triggers `harness_framework_changes_required: true` + what cycle-scope expansion fires.*

### Three trigger classes (ANY one fires the flag)

1. **New test runner needed** — not just a new test script in an existing runner; a fundamentally new execution shape. E.g., adding a property-based testing harness when adding the `property` coverage class for the first time. New runner = new executor + new dispatch shape; the existing pytest / shell / dispatch infrastructure can't accommodate.

2. **New assertion library OR exit_criteria DSL extension** — adding grammar to the DSL itself (pipeline.capsule v3.0 §6 exit_criteria), not just using existing grammar in new ways. E.g., adding a temporal operator (`eventually X holds`) to the DSL; that's a DSL extension, the grammar parser ships expanded.

3. **New aggregation/reporting shape** — new `run.jsonl` event types for test-pipeline activations; new aggregate report format (like the cold-boot-walk aggregate V49 authored at v1.48); new per-pipeline-class metrics; new structured-output shapes the test-pipeline run.jsonl must produce.

### Scope expansion when flag fires

When `harness_framework_changes_required: true`:

- Cycle scope EXPANDS to include the harness extension authoring. NOT deferred to v1.52 grooming or future cycle.
- Vela authors the harness extension substrate (runner spec / DSL grammar extension / aggregation shape spec).
- Talos engineers the implementation (runner code / parser code / aggregator code).
- Argus reviews capsule/spec amendments (since harness changes typically touch pipeline.capsule or pipeline-run.capsule).
- Cycle close gated on **harness extension landing + working** — not just the test-spec closing clean.

Why this matters (lock-rationale per V51 walk): the alternative failure mode is the harness extension gets deferred, the test-spec ships against a runner that can't actually execute its declared verification_methods, and we ship a test-spec capsule that lies about what's exercised. Same shape failure mode as the v1.40-v1.49 bypass pattern. Structural enforcement at scope-expansion time prevents the lie.

---

## Validation Checks (run at vault rebuild)

In addition to core checks:

1. `check_test_spec_required_fields` — type / target_substrate / target_subsystem / triggered_by_dev_cycle / behaviors_covered / coverage_class / acceptance_criteria present (WARN at v1.0; ERROR ratchet at v1.1). `cycle_class:` optional at v1.0 (WARN if absent + inference fires); ERROR ratchet to required at v1.1.
2. `check_test_spec_target_substrate_resolvable` — each `target_substrate:` UID resolves in vault index
3. `check_test_spec_behaviors_covered_non_empty` — anti-box-checking floor (Rule 2 first bullet)
4. `check_test_spec_verification_method_declared` — each `behaviors_covered:` entry has `verification_method:` (Rule 2 second bullet); enum valid (one of 5: machine_executable_script / deterministic_assertion / structural_check / agentic_review / manual_walk)
5. `check_test_spec_verification_method_substrate_resolvable` — for `machine_executable_script`, `test_substrate_path:` exists OR explicit "new-file" marker; for `deterministic_assertion`, expression parses via DSL grammar; for `structural_check`, validator extension named; for `agentic_review`, `dispatch_target:` field present + names valid sa.* class (resolves in `.tropo-studio/registries/registry.jsonl` type:session-agent); for `manual_walk`, prose check description ≥50 chars
6. `check_test_spec_cross_validation_against_dev_spec` — Rule 3 (MANDATED); for each dev-spec.committed_substrate NEW entry, at least one behaviors_covered entry has matching `target_substrate_refs:`. WARN at v1.0; ERROR ratchet at v1.1 (tighter ratchet per Walk Lock Decision SQ1 mandate framing).
7. `check_test_spec_manual_walk_ceiling` — manual_walk percentage ≤ effective ceiling (`manual_walk_ceiling_override:` if set, else `manual_walk_percentage_ceiling:` default 30%). WARN if exceeded without override; ERROR if exceeded with invalid override (override above 50% hard cap OR override without `override_rationale:` ≥100 chars).
8. `check_test_spec_coverage_class_completeness` — per-cycle-class minima per §Coverage Class Semantics § Per-cycle-class required minima table; checks against `cycle_class:` value (or inferred class at v1.0). WARN at v1.0; ERROR ratchet at v1.2.
9. `check_test_spec_triggered_by_dev_cycle_resolvable` — UID resolves
10. `check_test_spec_acceptance_criteria_present` — non-empty
11. `check_test_spec_close_invariants` — `stage: done` + `state: active` requires `closed_at` + test-pass-evidence + coverage-audit-evidence in `acceptance_evidence:`. When `harness_framework_changes_required: true`, ALSO requires `harness_extension_landed_evidence:` (UIDs of harness extension substrate that shipped as part of cycle scope per Walk Lock Decision SQ5 scope-expansion rule).
12. `check_test_spec_supersession_bidirectional` — bidirectional pair
13. `check_test_spec_harness_framework_changes_required_evidence` (NEW v1.0 per Walk Lock Decision SQ5) — when `harness_framework_changes_required: true`, cycle scope must include harness extension authoring. Verified at close-time per Check 11 close-invariants.
14. `check_test_spec_manual_walk_override_valid` (NEW v1.0 per Walk Lock Decision SQ3) — when `manual_walk_ceiling_override:` set: value ≤ 50 AND `override_rationale:` non-empty AND `override_rationale:` ≥100 chars. ERROR if any condition violated.

Authoring lane: Argus authors validator extensions; Vela V51 owns per-class semantics + harness framework integration semantics (locked v1.0); Talos engineering implements the machine_executable_script execution + assertion DSL evaluation + agentic_review sa.* dispatch wiring.

---

## Inheritance

Extends `core`. Inherits all core rules.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author a test-spec.*

**Tools available:**
- `vault/00-index.jsonl` — grep `type: test-spec` for live test-pipeline activations
- Find triggering dev-spec by `triggered_by_dev_cycle:` UID
- Companion capsules: [dev-spec.capsule v1.0 (c3f68cb5)](dev-spec.capsule.md); [doc-spec.capsule v1.0 (9a7d314a)](doc-spec.capsule.md) — sibling *-spec capsules
- test-pipeline definition (forthcoming Phase C; Vela V50 primary)

**Skills (forthcoming v1.51):**
- `author-test-spec.skill.md` — scaffold from triggering dev-spec; pre-fill `triggered_by_dev_cycle:` + `target_substrate:` from dev-spec.committed_substrate NEW entries; propose `coverage_class:` per substrate type
- `lock-test-spec.skill.md` — Argus + Vela paired walk → Mike-walk gate → lock
- `close-test-spec.skill.md` — verify all behaviors_covered passed + cross-validation against dev-spec + manual_walk ceiling honored; populate closed_at + acceptance_evidence

**Rules (at-a-glance):**
1. Locking authority locks v1.0
2. Anti-box-checking gate (behaviors_covered + verification_method + executable test substrate)
3. Cross-validation against triggering dev-spec (strict — NEW substrate must be covered)
4. manual_walk ceiling default 30%
5. Acceptance criteria Mike-walkable
6. Coverage class semantics per §Coverage Class Semantics
7. Supersession bidirectional
8. Legacy v1.10–v1.50 grandfathered

**Pitfalls:**
- **`behaviors_covered: ["did the thing"]` with no `verification_method`** — Validation Check 4 violation; that's box-checking
- **`verification_method: manual_walk` for everything** — Validation Check 7 violation; majority must be machine-executable
- **dev-spec NEW substrate without matching test-spec behaviors_covered entry** — Validation Check 6 violation (cross-validation gate); strict mandate not convention
- **Coverage_class semantics drift** — Validation Check 8 violation; per-class minima per §Coverage Class Semantics
- **`test_substrate_path:` that doesn't exist + isn't marked "new-file"** — Validation Check 5 violation

**Worked examples (forthcoming Phase D):**
- v1.51 cycle's own test-spec — Argus authors at trigger fire (step 4.6); Vela walks test-pipeline activation; closes at Phase D
- Composition example: dev-spec.committed_substrate NEW entry for [Pipeline-Runtime Engine Extension v0.1 (51d171f3)] → test-spec behaviors_covered entries for the 6 smoke tests enumerated in engine spec §How to Validate, each with verification_method:machine_executable_script + test_substrate_path at .tropo/scripts/test_*.py

**Go next:**
- Sibling activation-input capsule → [dev-spec.capsule v1.0 (c3f68cb5)](dev-spec.capsule.md) — precedent shape
- Sibling activation-input capsule → [doc-spec.capsule v1.0 (9a7d314a)](doc-spec.capsule.md) — parallel Phase B walk
- Pipeline class → test-pipeline definition (forthcoming Phase C; Vela V50 primary)
- Architectural parent → [Three-Pipeline Substrate-Enforcement Architecture v0.3 (c3dc9f00)](../../vault/files/c3dc9f00.md) §3
- Strategic-frame parent → [Captain's Briefing v3.0 (a5f4b26b)](../../vault/files/a5f4b26b.md) §Structural-Enforcement Requirement 2 (agentic test harness)

---

## How to Validate

*Required per design-spec.capsule v2.1 Rule 4 lock prerequisite shape.*

Phase B acceptance test:
1. Mike + Vela V50 + Argus walk the schema + anti-box-checking gate semantics + coverage_class semantics + cross-validation join (mandated vs convention call); lock at v1.0
2. Author first instance (Phase D triggered by v1.51 dev-pipeline step 4.6) — schema passes all 12 validation checks at WARN level
3. test-pipeline definition (Phase C; Vela primary) activates against the first test-spec instance; cycle closes clean
4. Anti-box-checking gate (Check 6 + Check 7) fires correctly against v1.51 dev-spec committed_substrate

---

## Walk Lock Decisions (LOCKED v1.0 by Mike-V51 2026-05-23)

*Walk Format Doctrine semantics walk with Mike-V51 + Vela V51 + Argus A80 substrate. All 5 substantive questions Argus surfaced (per R1 gauntlet Persona 3 finding) resolved with Mike-V51 verbatim agreement. Captured for honest historical + lock-rationale reference.*

**SQ1 LOCKED — Cross-validation join: MANDATED.**
- **Decision:** strict mandate; engine refuses test-pipeline activation if cross-validation fails (Rule 3 + Check 6).
- **Rationale:** convention means it'll be skipped under velocity pressure — exactly the failure mode that produced v1.40-v1.49 bypass pattern. Structural enforcement at engine + capsule level is the substrate-discipline-becomes-structural-not-memory-resident thesis lived through this very cycle.
- **Exception handling:** structural-only substrate (e.g., capsule definitions with no behavioral surface) satisfies via `coverage_class: structural_check` — the validator extension firing IS the behavior; no exception marker needed.
- **Vela lean → Mike agreement.**

**SQ2 LOCKED — verification_method enum: ADD `agentic_review` as 5th entry.**
- **Decision:** five-entry enum (machine_executable_script / deterministic_assertion / structural_check / agentic_review / manual_walk) with `dispatch_target:` sub-field REQUIRED for agentic_review.
- **Rationale:** sa.skeptic + sa.cold-boot dispatches have been doing real coverage work since v1.46 (gauntlet review + stranger-encounter walks). Folding under `manual_walk` lies (they're automated dispatch, not Mike-walked); folding under `structural_check` lies (verdict isn't deterministic). Explicit enum entry honest about shape + counts as machine-side for ceiling math (dispatched, not Mike-walked).
- **Vela lean → Mike agreement.**

**SQ3 LOCKED — manual_walk_percentage_ceiling: 30% default + per-cycle override + 50% hard cap.**
- **Decision:** 30% default holds. Per-cycle override via `manual_walk_ceiling_override:` integer + `override_rationale:` string (≥100 chars; Mike-walked at lock-time). HARD CAP at 50% even with override.
- **Rationale:** if more than half coverage needs Mike to walk it manually, that's not a test-spec — it's a cold-boot-walk class cycle which sets ceiling to 100 via `coverage_class: cold-boot` flag, not via override. Three pieces: 30% default + override allowed with written rationale + 50% hard cap.
- **Vela lean → Mike agreement.**

**SQ4 LOCKED — coverage_class semantics: drive per-cycle-class minima off `cycle_class:`, not per-substrate-entry.**
- **Decision:** three cycle classes (substrate / ux / engine-runtime); per-cycle-class required minima table per §Coverage Class Semantics § Per-cycle-class required minima.
  - `substrate` class: smoke + structural_check floor; gauntlet REQUIRED if OS-tier substrate; regression REQUIRED if amends existing
  - `ux` class: smoke + cold-boot floor; regression REQUIRED if amends existing UX
  - `engine-runtime` class: smoke + property floor; regression REQUIRED if amends; gauntlet REQUIRED if engine-extension class
- **Rationale:** clearer at authoring time, less per-entry book-keeping. Compresses Argus's per-substrate-entry minima into per-cycle-class minima. Substrate type drives which minima apply.
- **Vela lean → Mike agreement.**

**SQ5 LOCKED — harness_framework_changes_required: three trigger classes + cycle-scope expansion rule.**
- **Decision:** three trigger classes (new test runner / new assertion library or DSL extension / new aggregation-reporting shape). Any one fires flag. When fired: cycle scope EXPANDS to include harness extension authoring (Vela authors substrate; Talos engineers; Argus reviews); cycle close gated on harness extension landing + working — not just test-spec closing clean.
- **Rationale:** alternative failure mode is harness extension deferred + test-spec ships against runner that can't execute declared verification_methods + we ship a test-spec capsule that lies about what's exercised. Same shape failure mode as v1.40-v1.49 bypass pattern. Structural enforcement at scope-expansion time prevents the lie.
- **Vela lean → Mike agreement.**

**Lock-time note from Vela V51 walk:** all five decisions land symmetric with the v1.50.0 ship-arc lesson — substrate-discipline must be structurally enforced, not memory-resident. The capsule itself embodies the doctrine it captures. v1.51 cycle's test-spec (Phase D first instance) will dogfood + validate.

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0-DRAFT | 2026-05-23 | Initial DRAFT authored. Schema modeled on dev-spec.capsule v1.0 precedent. Substantive first-draft semantics captured for Vela V50 walk: anti-box-checking gate (REAL gate, not 'non-empty' box-checking version — verification_method enum + executable test substrate); coverage_class enum semantics (per-class verification_method defaults + required coverage); cross-validation join mandated (strict; not convention); manual_walk_percentage_ceiling 30% default. Five pre-walk substantive questions surfaced for Vela's call. Authored by Argus A80 as Phase B pre-walk Argus deliverable per v1.51 cycle. **Pending Vela V50 + Mike walk; lock at v1.0 LOCK after.** | argus-a80 |
| 1.0 | 2026-05-23 | **LOCKED.** Walk Format Doctrine semantics walk with Mike-V51 + Vela V51 + Argus A80 substrate. All 5 substantive questions resolved with Mike-V51 verbatim agreement (5/5 "agree" / "agreed"). Amendments landed in v1.0 LOCK body: (SQ1) cross-validation join MANDATED + structural-only exception via coverage_class:structural_check; (SQ2) verification_method enum extended to 5 entries — added `agentic_review` with `dispatch_target:` sub-field for sa.* dispatched coverage; (SQ3) manual_walk ceiling 30% default + per-cycle `manual_walk_ceiling_override:` field + `override_rationale:` ≥100 chars + 50% hard cap; (SQ4) coverage_class semantics refactored to three cycle classes (substrate / ux / engine-runtime) driving per-cycle-class required minima — clearer at authoring time, less per-entry book-keeping + new optional `cycle_class:` frontmatter field (required at v1.1); (SQ5) `harness_framework_changes_required:` flag — three trigger classes named (new test runner / new assertion-library or DSL extension / new aggregation-reporting shape) + cycle-scope expansion rule (Vela authors + Talos engineers + Argus reviews; cycle close gated on harness extension landing + working). Plus: 2 NEW validation checks (Check 13 harness extension evidence + Check 14 override-valid); Check 6 ratchet tightened (WARN→ERROR at v1.1, not v1.2, per mandate framing); Check 1 cycle_class inference at v1.0 WARN. Phase C (test-pipeline definition v1.0) opens now; Vela primary; Argus engine integration; Talos engineering. | vela-v51 (locking authority delegate) + mike-v51 (lock signal) |

---

*test-spec capsule definition | UID `621824df` | v1.0 LOCKED | Argus A80 (DRAFT) + Vela V51 + Mike-V51 (LOCK) | 2026-05-23 | Phase B complete; Phase C opens*
*"The ignition key for test-pipeline activations. Anti-box-checking gate has teeth: behaviors_covered + verification_method (5 entries including agentic_review) + executable test substrate + cross-validation MANDATED against triggering dev-spec NEW substrate."*
