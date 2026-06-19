---
uid: b19e8d43
name: "release"
type: capsule-definition
extends: core
version: "3.12"
v3_12_amendment_note: "v3.11 -> v3.12 2026-06-06 by Argus A101 per Mike Call-① (e68503aa): release status TERMINAL renamed done -> shipped. The 11 body refs to status:done-as-terminal became shipped (§2 enum, §2.6 Required-at-Ship header+body, Rules 15/16/17, the authored-state line, the validation-check literal). Historical 'done' deliberately preserved: the retired v1.0 state-machine (build->verify->deploy->done->archived, L149) + the v3_9/v3_10/v3_11 amendment notes (honest record). DATA: Vela V59 migrated all 23 pre-v1.9.2 type:release status:done -> shipped (23/23; validator 56/0; non-breaking - 50 shipped already accepted). GRANDFATHER GAP (Vela honest-catch, verify-dont-infer): the migration surfaced ~135 Rule-15 WARNs because the Rule-15 VALIDATOR does not honor the rule's own declared 'releases >= v1.59.0 ship' scope - the v3.9 required_at_ship/activation fields (ship_signal_verbatim etc.) are UNKNOWABLE for historical v1.3/v1.6/v1.9.x releases. Rule 15/16 text sharpened below to make the >=v1.59.0 grandfather explicit; validator code-fix routed to Talos (skip pre-v1.59.0 type:release entries, mirroring f5e2d1c7's pre-v1.9.2 grandfather). Migration is CORRECT (not reverted); the gap is validator grandfathering, not the rename. Split per Vela 2055: Vela did the 23 data (release-data lane); Argus did this capsule edit (historical-exclusion judgment)."
v3_11_amendment_note: "v3.10 -> v3.11 amendment 2026-06-06 by Vela V59 per the member_of DISAMBIGUATE build (spec 6f5bb2cb v0.4; Mike-A100 approved 9 lock-breaks; core.capsule v1.5 Rule 9). Rule 12 subsystems_touched derivation retargeted member_of[cap] -> subsystem_hub[cap], and the hardcoded 7-hub literal set -> the DYNAMIC hub set discovered from subsystem_name: (SUBSYSTEM_HUBS; 11 at present) - matching Talos f5e2d1c7.py (_discover_subsystem_hubs). capabilities_touched + subsystems_touched field descs (L119-120) retargeted to subsystem_hub: + 1-hop subsystem_hub: traversal. LANDED ATOMICALLY with Talos f5e2d1c7.py (both derivers live dynamic-11; Talos 2018 'land yours now'); status stays locked (amend-in-place per the approved lock-break). Exact edits drafted by Argus A101 (event 2013, 1a/1b/1c); landed by Vela V59 (release lane). Sibling release-plan.capsule landed v1.5 (#3). Status-enum done->shipped (#2) SPLIT to a focused follow-up (e68503aa, Mike Call-1). Adjacents deliberately NOT edited (defer to Argus): Check 24 (~L246) diagnostic still says 'misconfigured member_of:'; Rule 14 + Check 26 (~L188/254) are RETIRED-historical (member_of refs preserved as honest record)."
v3_10_amendment_note: "v3.9 → v3.10 amendment 2026-05-31 by Vela V55 per v1.62 Lane V (Argus A89 broadcast 397; cycle spine cdc1615e Cascade-Completion-Failure Retrospective). COMPLETION GATE AS HARD SHIP-BLOCK. Empirical trigger: v1.60 + v1.61 both reached status:done (shipped) while their cascade pipeline runs were STILL status:active (doc-activation c94663a9 + test-activation 052e7ebc for v1.60; doc-activation 69e1341c + test-activation d683585d for v1.61). Rule 16's 'verify both cascade pipelines status:retired before ship-flip' check (added v3.9) did NOT fire — because the ship-flip happened by hand (frontmatter edit), not via a runnable build-release.py --ship gate (per Vela finding cbe4f7bd: the Rule 16 ship-step is documented but not implemented as a runnable gate). So a documented gate that nothing enforces is not a gate. v3.10 reframes Rule 16 from advisory ('the ship-step MUST verify') to a HARD BLOCK with a binding contract: a release entry MUST NOT carry status:done while ANY cascade pipeline run (doc/test activation) referencing it remains status:active. This is the CONTRACT layer; enforcement composes across three v1.62 lanes — Lane B (Talos: build-release.py --ship runnable gate + pipeline-runtime assert_all_steps_verified before workflow_complete) makes it fire at the engine; Lane A (Argus: capsule invariants + completion-report schema) gives it the invariant; Lane V (this amendment) is the release.capsule declaration. NEW Rule 17 added below. Composes with cbe4f7bd (the not-firing finding) + b8bda711 (inbox-transition: items leave their open state when work completes — same completion-discipline family) + Mike-V49 binding directive 3 (substrate-discipline structurally enforced, not memory-resident: a hand-flipped gate is memory-resident; a runnable refused-flip is structural). Validate against v1.62 dev-spec c1a62d3f per cycle protocol (emit-event to Argus A89 on lane-land)."
v3_9_amendment_note: "v3.8 → v3.9 amendment 2026-05-28 by Argus A87 captain-mode per v1.59 dev-spec d8c3f1b7 A1 (closes A85-stub-schema-drift defect class structurally; five empirical instances at v1.55+v1.56+v1.57+v1.58 + v1.59-by-Talos confirmed by Orpheus O12 event 136). Substrate-honesty: v3.8 contract said 'no pre-ship state — release is born at ship' but A85 introduced pre-ship-stub authoring pattern at cycle activation 2026-05-26 onwards (per A.9 + A.12 + B.7 honest-record discipline) without updating the capsule. Pattern + capsule drifted; validator caught drift at each cycle ship as ~5-10 min remediation. v3.9 closes by formalizing status:pre-ship as valid + adding required_at_activation + required_at_ship field-class declarations + new Rule 15 enforcing population by status. NEW: (a) §2 Required Frontmatter status enum: {pre-ship, done} (v3.9; was: literal done only at v3.8); pre-ship = authored captain-mode at cycle activation per current pattern, done = flipped at ship by ship-firing agent (typically Vela). (b) §2.5 NEW subsection Required-at-Activation Field-Class declaration: 5 fields required when status:pre-ship (capabilities_touched, kernel_substrate_touched, foundation, member_of, ratchet_targets — all enumerable at activation moment). (c) §2.6 NEW subsection Required-at-Ship Field-Class declaration: 7 fields required at status:done flip (released_at, released_by, build_artifact_path, validator_state_at_ship, pristine_streak_at_ship, ship_signal_verbatim, cold_boot_walk_disposition — all only knowable at ship). (d) NEW Rule 15 (releases ≥ v1.59.0 ship): release_validators.py extension checks status:pre-ship entries have all required_at_activation fields populated (not TBD) + status:done entries have all required_at_ship fields populated. WARN at v1.59; ERROR ratchet at v1.60+ after audit pass of existing pre-ship + done entries. (e) Rule 16 NEW (composes with Lane B V2/V3): build-release.py ship-step refuses status:done flip when any required_at_ship field absent or TBD. Closes 3-cycle-recurring R11+R12 substrate-population-residue at structural level. Composes with Lane V Layer 3 meta-validator (M.1 at 8e2f1a47); Layer 3 catches schema-vs-implementation drift at validation-time; Rule 15 catches author-vs-schema drift at vault rebuild; Rule 16 catches author-vs-schema drift at ship-flip. Three-tier defense closing the defect class structurally."
supersedes_version: "3.10"
tier: os
author: tropo
created: 2026-04-16
modified: 2026-06-06
modified_by: vela-v59
status: locked
locked_by: argus-a46
locked_at: 2026-05-05
enforced_enums:
  status:
    canonical: [pre-ship, shipped]
    aliases:
      published: shipped
      done: shipped
      superseded: shipped
meta_status_rollup:
  in-progress: [pre-ship]
  done: [shipped, published, superseded, done]
last_body_refactor: 2026-05-11
history_file: ff5653d5
v3_8_amendment_note: "v1.56.0 cycle X.1 (Tools-in-Vault Pillar 1 Reshape) - retires Rule 14 path-pattern table + Validation Check 26 added at v3.7. Rationale: v1.56 Lane M+R migrates ~22 sidecar tool entries + ~15-20 new tool registrations to vault/tools/<uid>.{py|md|json} per tool.capsule v1.6 §2.5 single-file pattern. Post-migration, tools have proper `member_of:` graph citizenship pointing at their subsystem hub UIDs. Rule 12's 1-hop `capabilities_touched -> member_of -> hub` derivation handles tool-class substrate cleanly without needing the path-pattern table indirection that Rule 14a introduced. Rule 14b (type:pipeline subsystem_hub propagation) similarly retires - pipeline-class capabilities already carry member_of: at their root projects post-v1.46 engine work. Net effect: derivation simplification + maintenance burden reduction (path-pattern table required updates per new kernel-tier directory; now extinct concern post-Pillar-1-migration). Grandfathering: releases ≥ v1.54.0 AND < v1.56.0 (v1.54 + v1.55) retain v3.7 contract including Rule 14 + Check 26; releases ≥ v1.56.0 follow v3.8 contract (Rule 14 retired; Check 26 retired; Rule 12 alone governs subsystems_touched derivation). validate-capability-membership.py simplification per v1.56 dev-spec Lane X.2 (Talos engineering) reverts to v3.4-era Rule 12 1-hop traversal only. Composes with tool.capsule v1.6 LOCKED 2026-05-26 + v1.56 cycle brief 6c1b7692 + v1.56 dev-spec ca0a620f + v1.55 ship of events.capsule v1.1 + Mike-A85 standing architect-led-roadmap-optimization authority per stm-a85-001. Authored by Argus A85 captain-mode 2026-05-27 per v1.56 Lane X.1 obligation + same-day amendment pattern (A84 events.capsule v1.0 → v1.1 + 0056ec0e v1.0 → v1.1 + this v3.7 → v3.8 all follow the same pattern)."
v3_7_amendment_note: "v1.54.0 ship - Engine-Discipline Hardening Triad cycle. Lane V (substrate-verify-twice Layer 3 cross-cycle observability ledger) + Lane R (R11/R12 derivation rule extension to kernel paths + type:pipeline subsystems). NEW optional frontmatter field `substrate_verify_twice_findings:` (Lane V V2 per cycle brief [5d0c831f v0.2 LOCKED](../../vault/files/5d0c831f.md) + dev-spec [137ac7e1 v1.0 LOCKED](../../vault/files/137ac7e1.md)) captures per-cycle defect instances of substrate-verify-twice class for cross-cycle observability per O11's [83af4ac1](../../vault/files/83af4ac1.md) Layer 3. NEW Governance Rule 14 (Lane R R1) extends subsystems_touched derivation: in addition to the v3.4 1-hop `capabilities_touched -> member_of -> hub` path, derivation now ALSO resolves (a) `kernel_substrate_touched:` paths via the path-pattern table below + (b) `type: pipeline` capability entries via their `subsystem_hub:` field. NEW Validation Check 26 (WARN at v1.54.0+ grace period; ERROR ratchet planned v1.55.0+) enforces extended R12 derivation correctness. Rule 12 unchanged in body but now composes with Rule 14 (both compute into subsystems_touched). Grandfathering: v1.53.0 and earlier release entries exempt per existing composition rule. Closes A83 v1.52 case (3 iterative R11/R12 fixes per de2a5e38 substrate-coherence-fix-v3 note) structurally — under v3.7 rule, kernel substrate touches + pipeline-type capabilities derive correctly first-try. Authored by Argus A84 captain-mode 2026-05-25 per Mike-A84 walk-lock on cycle brief v0.2."
v3_6_amendment_note: "v1.35.0 ship — bakes the chain-progress-snapshot discipline into the release artifact per Mike-A68 2026-05-16 verbatim ('What you just did right there should be baked into our studio. ... It's a model of excellence for how a tropo studio should work.'). New required body section §3 (`## Chain Progress Snapshot`); new Governance Rule 13; new Validation Check 25 (WARN at v1.35.0+ grace period; ERROR ratchet at v1.36.0+). Composes with new skill `render-chain-progress-board` (135be96d) which codifies the rendering format. Grandfathering: v1.34.0 and earlier release entries exempt per existing composition rule (oldest applicable boundary wins). The cycle introducing the requirement (v1.35.0) complies with it — release entry [9743fa03](../../vault/files/9743fa03.md) is amended to include the section in the same ship."
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — 5-section pedagogy reference
aligned_with:
  - a3f1e7b2   # release-plan.capsule
  - d2e7b1f4   # Typed Pipeline Architecture design brief
  - b3d7e5a1   # build.capsule
  - 8b3f1d92   # Tropo Work v3 Architecture Spec
  - f4a8c2d6   # release-test-plan v2.0.1
  - fd2d9e77   # v1.8 design brief — Capability Subsystem Membership
  - 8a4e21c5   # subsystem-hub.capsule
tags: [capsule-definition, release, 5-section-pedagogy, v1.19.0-stream-c-refactored]
---

# release — Capsule Definition v3.5

## 1. Intent

A `release` is the historical record of what shipped. Paired with `release-plan` (which plans forward) to complete the Deploy-stage output: release-plan plans → build produces → release records.

A release records: the version shipped, the date shipped, the build it derives from, the manifest + zip disk paths, the verification summary at ship, the known issues shipping with the release, and the release-plan that planned it.

A release is immutable in body after ship except for an appendable §Retrospective section. The triangle (release-plan / build / release) is the canonical atomic-commit shape — all three update together at ship.

Before creating a release entry: confirm the corresponding build is locked and the release-plan has reached (or is ready to reach) `stage: done`. A release entry is the atomic-commit partner to those two transitions.

Failure mode prevented: releases shipping without verification gauntlet passes, without atomic-triangle consistency across build/plan/release, or without proper grandfathering of pre-existing release entries that predate later schema amendments.

---

## 2. Schema

### Required Frontmatter (v2.0+ shape, beyond core)

| Field | Type | Constraint |
|---|---|---|
| `title` | string | ≤120 chars; format `"<Product> v<version>"` |
| `description` | string | ≤200 chars; one-line summary of what the release delivers |
| `state` | enum | `active` / `archived` |
| `status` | enum (v3.9+) | `pre-ship` (authored captain-mode at cycle activation per A.X discipline) OR `shipped` (flipped at ship by ship-firing agent; renamed from `done` at v3.12 per Mike Call-① e68503aa). v3.0-v3.11 used `done` as the terminal; v3.9 formally adds `pre-ship` to close A85-stub-schema-drift defect class — see Required-at-Activation + Required-at-Ship field-class declarations below + Rule 15 + Rule 16. |
| `owner` | string | Agent who filed the release entry (typically Vela or Deploy-stage owner) |
| `release_version` | string | Semver `^\d+\.\d+\.\d+(-[a-z0-9.-]+)?$`. MUST match `build_version:` of the build in `derived_from:`. (Renamed from v1.0's `version:` for clarity.) |
| `release_date` | ISO date | When the release shipped |
| `derived_from` | UID array | Single-entry array with the UID of the `build` this release shipped. Bidirectional with `build.composes_into:`. |
| `shipped_release_plan` | UID | The release-plan this release satisfies. Bidirectional with `release-plan.shipped_release:`. |
| `manifest_path` | string | Path from vault root to the release's manifest file |
| `zip_path` | string | Path from vault root to the distribution zip |
| `member_of` | UID array | At least: the release-planning project + the pipeline stage bucket |

### Required-at-Activation Field-Class (v3.9+; status:pre-ship)

When a release entry is authored captain-mode at cycle activation moment per A.X honest-record discipline (A85 introduced this pattern at v1.55 cycle; standardized v3.9), the following fields MUST be populated (not TBD; not empty arrays where lists; not literal placeholder strings):

| Field | Population at status:pre-ship |
|---|---|
| `capabilities_touched` | UID array of capability entries the cycle will touch (from triggering release-plan or cycle brief) |
| `kernel_substrate_touched` | String array of kernel substrate paths the cycle will touch |
| `foundation` | UID array of substrate the cycle composes with |
| `member_of` | UID array; at minimum dev-pipeline ID |
| `ratchet_targets` | Object with ratchet metrics (pristine_streak target + cycle-position + next_cycle if known) |

Pre-ship stub authoring discipline: Argus (or any captain-mode-active executive) authors these at cycle activation as part of A.X honest-record substrate. Drift between author-claim and actual cycle scope catches at Lane V Layer 3 meta-validator + Rule 15 vault-rebuild check.

### Required-at-Ship Field-Class (v3.9+; status:shipped)

When status flips from pre-ship to shipped at ship moment by ship-firing agent (typically Vela), the following fields MUST be populated (not TBD):

| Field | Population at status:shipped flip |
|---|---|
| `released_at` | ISO date when ship signal received from principal |
| `released_by` | Agent UID that flipped status:shipped |
| `build_artifact_path` | Filesystem path to build artifact directory |
| `build_manifest_files` | Integer count of files in build artifact |
| `build_manifest_bytes` | Integer byte size of build artifact |
| `pristine_streak_at_ship` | Integer pristine streak post-ship ratchet |
| `validator_state_at_ship` | Object {passed:int, failed:int, warnings:int} from validator run at ship moment |
| `ship_signal_verbatim` | Verbatim quote of principal's ship signal |
| `cold_boot_walk_disposition` | Enum {executed, skipped-substrate-cycle-precedent, deferred-with-rationale} |

Ship-flip discipline: Rule 16 enforces this at build-release.py ship-step via pre-flip check; Rule 15 enforces at vault rebuild via release_validators.py extension. Two-tier defense closes the historical R11+R12 substrate-population-residue defect class structurally.

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `codename` | string | Informal release name |
| `github_tag` | string | The git tag for this release |
| `cold_boot_passes` | number | v1.0 carry-over; superseded by `verification_artifacts:` at v3.1+ |
| `verification_artifacts` | array — union shape (v3.1: array of UIDs; v3.2+: typed objects) | **v3.1+ REQUIRED.** v3.1 shape (3 entries: walker + cold-boot singular + validate). v3.2+ shape (4 typed-object entries: walker / cold-boot mode:strict / cold-boot mode:skeptic / validate). Full inline worked example in [release.history.md](release.history.md); see also `dispatch-walker.playbook` + `dispatch-cold-boot.playbook` for typed-object shapes. |
| `supersedes` / `superseded_by` | UID | Bidirectional pair for supersession |
| `revoked_at` / `revoked_reason` | ISO date / string | If revoked post-ship |
| `release_channel` | string | `stable` / `beta` / `nightly`. Default `stable`. |
| `relationships` | typed-edge array | Schema v2 cross-cutting references |
| `capabilities_touched` | UID array | **v3.4+; REQUIRED at status: shipped for releases ≥ v1.8.0 ship.** Mirrored from linked release-plan's `capabilities_touched:` at B6 commit. Each UID resolves to a governed primitive whose `subsystem_hub:` includes at least one subsystem hub UID (v1.5 member_of DISAMBIGUATE — was `member_of:`). Authoritative for v1.8+ self-doc derivation; `subsystems_touched:` derives from this PLUS (v3.7+) `kernel_substrate_touched:` + `type: pipeline` capability `subsystem_hub:` derivation per Rule 14. |
| `subsystems_touched` | UID array | **v3.4+; DERIVED - DO NOT AUTHOR DIRECTLY.** For releases ≥ v1.8.0: auto-populated at B6 via 1-hop `subsystem_hub:` graph traversal (v1.5 member_of DISAMBIGUATE). Rule 12 forbids manual authoring. **v3.7+ (≥ v1.54.0):** derivation extended to ALSO resolve `kernel_substrate_touched:` paths + `type: pipeline` capability `subsystem_hub:` fields per Rule 14. |
| `kernel_substrate_touched` | string array | **v3.7+ (≥ v1.54.0); OPTIONAL.** List of kernel substrate paths (e.g., `.tropo/scripts/foo.py`, `.tropo/playbooks/bar.playbook.md`, `vault/AGENTS.md`) touched at cycle ship. Pre-v3.7 cycles populated this field as descriptive prose-list; v3.7+ makes it derivation-relevant per Rule 14 path-pattern table. When populated, each entry's path matches a row in the path-pattern table; matched hub UID propagates into `subsystems_touched:` derivation. |
| `substrate_verify_twice_findings` | list of objects | **v3.7+ (≥ v1.54.0); OPTIONAL.** Cross-cycle observability ledger for the substrate-verify-twice defect class per [O11's brief 83af4ac1](../../vault/files/83af4ac1.md) Layer 3. Each finding object: `instance_description:` (string ≤200 chars) + `canonical_uid:` (UID of referenced canonical) + `canonical_field:` (field/enum/version cited) + `assumed_shape:` (what the authoring agent assumed) + `actual_shape:` (what the canonical actually was) + `catch_location:` (where the defect surfaced: validator / pipeline-gate / sibling-walk / fix-on-see) + `remediation_cycle:` (cycle UID that absorbed the fix; usually same as enclosing release). Honor-system at v1.54.0; future cycles may add validator enforcement once drift patterns surface. |

### Body shape — 5 required sections + 4 optional, in declared order (v3.6+)

1. **`## What Shipped`** — Concrete list of what's in this release; top-level changes; links to major artifacts. Stranger-test answer to "what did I get?"
2. **`## Release Notes`** — User-facing narrative (2-4 paragraphs); anchored to release-plan thesis; quotable in blog/Substack/distribution READMEs.
3. **`## Chain Progress Snapshot`** *(v3.6 NEW; required for releases ≥ v1.35.0)* — Ship-time visual board showing where this release lands in the active strategic chain. Authored per [`render-chain-progress-board.skill (135be96d)`](../skills/render-chain-progress-board.skill.md). Frozen at ship; not updated after. Required content: active strategic-chain block structure (closed / in-progress / ahead / destination) + cycle-by-cycle status table + ASCII progress bar with you-are-here marker + streak counter + risk catalog state. Format reference: v1.35.0 ship snapshot at [release entry 9743fa03](../../vault/files/9743fa03.md). v1.34.0 and earlier grandfathered per the composition rule below.
4. **`## Verification Summary`** — Summary of verification performed; links to build's §Test Results + any end-to-end verification specific to the release. Documents non-cardboard-muffin status.
5. **`## Known Issues`** — Defects shipping with this release. Each entry: issue + severity + workaround + planned fix target. Zero known issues states so explicitly ("No known issues at ship.").
6. *(optional)* **`## Retrospective`** — Post-ship reflections. **The only body section appendable after `state: archived`.**
7. *(optional)* **`## Upgrade Notes`** — Migration guidance for users upgrading from prior versions.
8. *(optional)* **`## Breaking Changes`** — If the release has breaking changes, explicit list.
9. *(optional)* **`## Credits`** — Contributors.

v1.0 did not mandate body sections. v2.0+ entries follow the required shape; grandfathered v1.0 entries exempt per the composition rule below.

---

## 3. State Machine (v2.0+)

```
(birth) → active → archived (supersession, revocation, or retirement)
                       ↑
                       §Retrospective appendable
```

v2.0 simplified the v1.0 state machine. v1.0 used a stage-progression (`build → verify → deploy → done → archived`) that conflated pre-ship production with post-ship state. v2.0 separates concerns: pre-ship is build.capsule's state machine; release is born at ship (no pre-ship state).

| State | Meaning |
|-------|---------|
| `active` | Release is live; users may be installing/using it. Body immutable except §Retrospective. |
| `archived` | Release is no longer current — either a newer release supersedes, OR the release was revoked. §Retrospective may still be appended. |

**Valid transitions:**

- `active → archived (superseded)` — Newer release with greater version ships; `superseded_by:` set
- `active → archived (revoked)` — Release pulled; `revoked_at:` + `revoked_reason:` populated; §Retrospective captures the story
- `archived → archived` — Terminal; §Retrospective appendable only

**Required starting state:** every new release entry is authored at `status: shipped` — no draft state. Releases are post-hoc records, populated at ship moment.

Canonical status enum: `status:` ∈ {pre-ship, shipped}

---

## 4. Validation Rules

### Governance Rules (13)

1. **Body is immutable after ship, except §Retrospective; frontmatter has two permitted mutations.** Rule 1 governs release ENTRIES (children created under this capsule), NOT `release.capsule.md` itself (capsule files follow capsule-amendment discipline per the meta-capsule). Frontmatter carve-outs: (a) `superseded_by:` set when a newer release supersedes this one; (b) `member_of:` append of the stage-archive UID if Close-path archival applies.
2. **`release_version:` matches `build_version:` of the derived build.** Validator enforces. Version drift is a governance violation.
3. **Release entry authored atomically with `release-plan.shipped_release:` set and build's `composes_into:` set.** Three fields form a consistent triangle; setting any one alone creates an inconsistent graph.
4. **One release per release-plan.** A release-plan ships exactly one release.
5. **Revocation is serious and documented.** `revoked_at:` + `revoked_reason:` required when archived via revocation. §Retrospective explains.
6. **Supersession is routine.** Most releases eventually get superseded. `superseded_by:` set when the next release ships.
7. **Version is required and immutable.** Once `release_version:` is set, it cannot change. Version corrections = new release via supersession.
8. **One active release per version.** Two active releases with the same version is a governance violation.
9. **All constituent artifacts must be verified before release.** A release derives from a build at `status: locked`, which by build.capsule Rule 5 requires §Test Results populated.
10. **(v3.1; expanded v3.2)** **Test-Plan execution required pre-ship.** Every release MUST execute the test-plan gauntlet defined in [release-test-plan v2.0.1 (f4a8c2d6)](../../vault/files/f4a8c2d6.md) prior to atomic-triangle commit. v3.2 sub-stages (release_date ≥ v1.4.2): Stage 3.1 walker / 3.2 cold-boot strict / 3.3 cold-boot skeptic / 3.4 validate. All four MUST return verdict ∈ {PASS, PASS-WITH-FINDINGS, PARTIAL within tolerance, DEFERRED-PENDING-CAPSULE within tolerance}. Stages 3.2 + 3.3 are paired-mode required (both records present, both acceptable). FAIL/HALT-SHIP blocks atomic-triangle commit. v3.1 vocab (3-valued PASS/PASS-WITH-FINDINGS/HALT-SHIP) for grandfathered entries. Stage 3.3 dispatcher is `sa.user-error-walker` (cross-family by lineage; rationale + edge cases in [release.history.md](release.history.md)).
11. **(v3.3; releases ≥ v1.7.0 ship)** **Subsystem documentation as release deliverable.** Each subsystem in the linked release-plan's `sub_systems:` array MUST have a corresponding row in `subsystem-registry.jsonl` whose `release_uid:` matches this release's UID. Bidirectional pair with subsystem-hub.capsule `release_history:`. Soft-gated v1.7-v1.9 (honor-system; reviewer verifies at ship gate); hard-gated v1.10+ via `scripts/validate-subsystem-hubs.ts`. Honest limit: Rule 11 verifies presence, not freshness; content-freshness deferred to v1.10/v1.11.
12. **(v3.4; releases ≥ v1.8.0 ship)** **Capabilities are the typed unit; subsystems are derived.** The release author authors `capabilities_touched:` (mirrored from release-plan at ship). `subsystems_touched:` is DERIVED via 1-hop graph traversal: `unique({hub_uid for cap_uid in capabilities_touched for hub_uid in subsystem_hub[cap_uid] if hub_uid in SUBSYSTEM_HUBS})` where `SUBSYSTEM_HUBS` is the DYNAMIC hub set discovered from `subsystem_name:` (11 at present; was a hardcoded 7 pre-v1.5 member_of DISAMBIGUATE), matching Talos's `f5e2d1c7.py` `_discover_subsystem_hubs`. The original 7: `8dd772a0` (governance) / `dbc1cbbf` (rendering) / `2d083137` (work) / `99ed55fd` (agents) / `76bab75f` (playbooks) / `1aba710c` (library) / `f87e33f0` (documentation). Drift collapse: both `subsystem-hub release_history:` rows and `subsystem-registry.jsonl` rows derive from the same source; divergence is structurally impossible. Soft-gated v1.8-v1.9; hard-gated v1.10+ via `scripts/validate-capability-membership.py`.
13. **(v3.6; releases ≥ v1.35.0 ship)** **Chain Progress Snapshot at ship.** Every release v1.35.0+ MUST include a `## Chain Progress Snapshot` body section authored per [`render-chain-progress-board.skill (135be96d)`](../skills/render-chain-progress-board.skill.md) at ship-time. Format codified in the skill; required content: active strategic-chain block structure + cycle-by-cycle status + ASCII progress bar with you-are-here marker + streak counter + risk catalog state. The board is a ship-time snapshot — frozen at ship, not updated after; subsequent releases render new snapshots. Origin: Mike-A68 directive 2026-05-16 — *"What you just did right there should be baked into our studio. ... It's a model of excellence for how a tropo studio should work."* The discipline is now Studio property, not executive discretion. WARN at v1.35.0+ grace period; ERROR ratchet planned for v1.36.0+ alongside skill-adoption maturity.
15. **(v3.9; releases ≥ v1.59.0 ship)** **Required-at-Activation + Required-at-Ship field-class enforcement.** At vault rebuild, `release_validators.py` checks: (a) every release entry with `status: pre-ship` has all 5 §Required-at-Activation Field-Class fields populated (not TBD; not empty arrays); (b) every release entry with `status: shipped` AND `release_version` ≥ v1.59.0 has all 9 §Required-at-Ship Field-Class fields populated (not TBD). **Pre-v1.59.0 type:release entries are GRANDFATHERED** — the v3.9 field-class (`ship_signal_verbatim`, `validator_state_at_ship`, etc.) is unknowable for historical v1.3/v1.6/v1.9.x releases; the validator skips them, mirroring f5e2d1c7's pre-v1.9.2 grandfather (Vela V59 honest-catch 2026-06-06: the done→shipped migration surfaced ~135 WARNs on the 23 historical releases because the code did not honor this rule's own ≥v1.59.0 scope). WARN at v1.59 grace period; ERROR ratchet at v1.60+ after audit pass of existing pre-ship + shipped entries. Closes A85-stub-schema-drift defect class structurally. Composes with Rule 16 (ship-flip enforcement at build-release.py).

16. **(v3.9; releases ≥ v1.59.0 ship)** **Ship-flip enforcement at build-release.py ship-step.** Before flipping `status: pre-ship` → `status: shipped`, build-release.py ship-step MUST verify: (a) all 9 §Required-at-Ship Field-Class fields populated (not TBD); (b) both doc-pipeline + test-pipeline cascade pipelines status:retired; (c) STRICT validator returns zero ERRORs. Refuse flip if any check fails; substrate-honest re-estimation per Lane B V2/V3 amendments. Composes with Rule 15 (vault-rebuild enforcement at release_validators.py); two-tier defense. Closes 3-cycle-recurring R11+R12 substrate-population-residue at structural level.

17. **(v3.10; releases ≥ v1.62.0 ship)** **Completion gate as HARD ship-block — a release MUST NOT carry `status: shipped` while any cascade pipeline run referencing it remains `status: active`.** This is the binding contract; Rule 16 (v3.9) declared the ship-step *should* verify cascade-pipelines-retired, but that check did not fire — v1.60 + v1.61 both reached `status: done` with their doc/test cascade activations still `status: active` (empirical: c94663a9 + 052e7ebc for v1.60; 69e1341c + d683585d for v1.61). Root cause per [Vela finding cbe4f7bd](../../vault/files/cbe4f7bd.md): the Rule 16 ship-step was documented but never implemented as a runnable gate, so the hand-performed frontmatter flip bypassed it. A documented gate that nothing enforces is not a gate. **The contract (this rule):** `status: shipped` is INVALID for a release entry while ANY `type: activation` / pipeline-run entry whose `target_release:` (or `references:`) points at it has `status: active`. Enforced at THREE composing layers per v1.62: (a) **Lane V / release.capsule (this rule)** — the declared invariant; (b) **Lane A / Argus** — capsule-invariant codification + completion-report schema; (c) **Lane B / Talos** — runnable enforcement: `build-release.py --ship` refuses the flip + `pipeline-runtime.py` `assert_all_steps_verified` before `workflow_complete`. Validator (`release_validators.py`) gains a Rule-17 check at vault rebuild: flag any `status: shipped` release with a still-`active` cascade run. WARN at v1.62 grace period; ERROR ratchet at v1.63. Composes with [b8bda711 inbox-transition protocol](../../vault/files/b8bda711.md) (same completion-discipline family: work-records leave their open state when work completes) + Mike-V49 binding directive 3 (a hand-flipped gate is memory-resident; a runnable refused-flip is structural). **Existing-data note:** the v1.60/v1.61 stuck cascade runs are NOT auto-retired by this rule — their disposition (retire-now vs after-Orpheus-O13-substantive-doc-close) is a separate Lane V cleanup pending Argus A89 scope confirmation (Vela event 404); this rule governs go-forward ships from v1.62.

14. **(v3.7; releases ≥ v1.54.0 ship AND < v1.56.0 ship — RETIRED at v3.8)** **Extended subsystems_touched derivation — kernel paths + pipeline-type capabilities.** **Status: RETIRED at v3.8 per v1.56 Lane X.1 amendment.** Rule 14 applied to v1.54.0 + v1.55.0 release entries only; v1.56.0+ releases follow v3.8 contract where Rule 12 alone governs `subsystems_touched:` derivation. **Retirement rationale:** v1.56 Lane M+R migrated ~22 sidecar tool entries + ~15-20 new tool registrations to `vault/tools/<uid>.{py|md|json}` per tool.capsule v1.6 §2.5 single-file pattern. Post-migration, tools carry proper `member_of:` graph citizenship pointing at their subsystem hub UIDs — Rule 12's 1-hop derivation handles tool-class substrate cleanly without the path-pattern table indirection that Rule 14a introduced. Rule 14b (type:pipeline subsystem_hub propagation) similarly retires; pipeline-class capabilities carry `member_of:` at their root projects post-v1.46 engine work. **Composes with v3.7 (preserved as historical record for v1.54-v1.55 grandfathering):** Rule 14 added two additional derivation sources: (a) `kernel_substrate_touched:` entries map to subsystem hub UIDs via the path-pattern table below; matched hubs propagate into `subsystems_touched:`. (b) When a `capabilities_touched:` UID resolves to a `type: pipeline` entry, that entry's `subsystem_hub:` field flows into `subsystems_touched:` derivation. The full derived `subsystems_touched:` set is the union of (Rule 12 path) + (Rule 14a kernel-path table) + (Rule 14b pipeline-type subsystem_hub). Origin: A83 v1.52 case (3 iterative R11/R12 fixes per [de2a5e38 v1_53_argus_a83_substrate_coherence_fix_v3](../../vault/files/de2a5e38.md)) — under Rule 14 the same v1.52 substrate derives correctly first-try. Authored Argus A84 captain-mode 2026-05-25 per Mike-A84 walk-lock on [v1.54 cycle brief 5d0c831f v0.2](../../vault/files/5d0c831f.md). WARN at v1.54.0+ grace period; planned ratchet to ERROR superseded by retirement at v3.8 (instead of ratcheting, the rule + its check retire as substrate evolution makes them redundant). Retired Argus A85 captain-mode 2026-05-27 per Mike-A85 ratification of v1.56 cycle scope.

#### Rule 14 Path-Pattern Table (v3.7 — RETIRED at v3.8; preserved for v1.54-v1.55 grandfathering)

Kernel substrate paths matching these patterns derive the named hub UID into `subsystems_touched:`. Patterns evaluated in declared order; first match wins; default fallback at table end. Authors who touch kernel substrate not matched by these patterns should propose pattern extension via channel post to Argus before relying on default-fallback behavior at scale.

| Path pattern (regex anchor at vault-root-relative) | Hub UID | Hub name |
|---|---|---|
| `^\.tropo/scripts/.*\.py$` | `76bab75f` | tropo-playbooks |
| `^\.tropo/playbooks/.*\.md$` | `76bab75f` | tropo-playbooks |
| `^\.tropo/skills/.*\.skill\.md$` | `76bab75f` | tropo-playbooks |
| `^\.tropo/capsules/.*\.capsule\.md$` | `8dd772a0` | tropo-governance |
| `.*/AGENTS\.md$` | `8dd772a0` | tropo-governance |
| `^STUDIO\.md$` | `8dd772a0` | tropo-governance |
| `^RELEASE-NOTES\.md$` | `2d083137` | tropo-work |
| `^\.tropo/.*` (default fallback for kernel paths) | `8dd772a0` | tropo-governance |

**Pattern maintenance discipline (per cycle brief R3 risk mitigation):** the table lives in this capsule body (authored substrate, reviewer-visible) NOT buried in code. Updates to the table cascade to `.tropo/scripts/validate-capability-membership.py` R12 enforcer (implementation reads the table or mirrors its rule set; either mode is acceptable as long as drift is caught at capsule-amendment review). Review the table at every capsule amendment cycle; extend patterns as new kernel substrate categories emerge.

### Validation Checks (25, version-gated as noted)

Core checks 1-16 (fire on all instances, with grandfathering carve-outs for v1.0-era entries):

1. `type: release` exact
2. `state` ∈ {`active`, `archived`}
3. *(removed at v3.0 — `stage: deploy` literal dropped per v3 Decision 4)*
4. `status: shipped` (literal)
5. `release_version:` matches semver
6. `release_version:` unique across non-superseded releases
7. `release_date:` valid ISO 8601; not in the future
8. `derived_from:` is single-entry array; UID resolves to a `build` at `status: locked`
9. `release_version:` equals referenced build's `build_version:` (bidirectional pair consistency)
10. `shipped_release_plan:` resolves to a release-plan whose `shipped_release:` points back
11. `manifest_path:` + `zip_path:` non-empty; resolve to existing files when `state: active`
12. `member_of:` non-empty; every UID resolves
13. Body contains required sections in declared order — 4 sections for v2.0-v3.5 entries; **5 sections for v3.6+ entries (releases ≥ v1.35.0)** with §Chain Progress Snapshot added at position #3 per Rule 13. v1.0 grandfathered.
14. If `state: archived` via revocation, `revoked_at:` + `revoked_reason:` populated
15. `supersedes:` / `superseded_by:` (if present) form bidirectional pairs
16. *(honor-system)* Body immutability after ship (Rule 1) — verified by convention; mechanical diff-check deferred

v3.1+ checks (releases ≥ 2026-04-29):

17. *(v3.1; extended v3.2)* `verification_artifacts:` non-empty; every UID resolves to an activation-log entry. v3.1 shape: ≥1 cold-boot + ≥1 walker record. v3.2 shape: exactly 4 typed-object entries (walker / cold-boot strict / cold-boot skeptic / validate).
18. *(v3.1; v3.2 vocab update)* All Stage 3 instrument verdicts in `verification_artifacts:` carry verdict ∈ {PASS, PASS-WITH-FINDINGS, PARTIAL within tolerance, DEFERRED-PENDING-CAPSULE within tolerance}. FAIL/HALT-SHIP fails this check.

v3.2+ checks (releases ≥ v1.4.2 ship):

19. *(paired-mode)* Both Stage 3.2 (strict) AND Stage 3.3 (skeptic) records present in `verification_artifacts:`. Single-mode dispatch does not clear the gate. Edge: DEFERRED record satisfies presence.
20. *(Skeptic granularity)* Stage 3.3 cold-boot mode:skeptic entry carries `per_mistake_outcomes:` whose length equals `mistake_count_total:`. Each outcome's `mistake:` verbatim-corresponds to a dispatched mistake. Shape-only check not sufficient — substantive correspondence required. Edge: WAIVED when `mistake_count_total: 0` AND verdict DEFERRED-PENDING-CAPSULE.
21. *(DEFERRED structural anchor)* When any entry carries `verdict: DEFERRED-PENDING-CAPSULE`, the entry MUST carry `deferred_capsule_uid:` resolving to either (a) a `type: task` whose `created:` is AFTER the activation-log record's `commissioned_at:` (forward-dated tracking), or (b) a capsule-definition at `status: draft` or with `modification_authorization:` (in-flight amendment). Forces deferrals to point at forward work; closes the DEFERRED escape hatch.

v3.3+ checks (releases ≥ v1.7.0 ship):

22. *(honor-system v1.7-v1.9; ERROR v1.10+)* Every entry in linked release-plan's `sub_systems:` array has a corresponding row in `subsystem-registry.jsonl` whose `release_uid:` matches this release. Bidirectional: each registry row's `subsystem_uid:` resolves to a hub instance whose `release_history:` array references the registry row's `uid:`. Both directions must hold.

v3.4+ checks (releases ≥ v1.8.0 ship):

23. *(honor-system v1.8-v1.9; ERROR v1.10+)* `capabilities_touched:` non-empty AND mirrors linked release-plan's `capabilities_touched:` exactly (same UID set; order may differ).
24. *(honor-system v1.8-v1.9; ERROR v1.10+)* `subsystems_touched:` equals the derived value from `capabilities_touched:` via 1-hop graph traversal. Mismatch indicates either misconfigured capability `subsystem_hub:` (v3.11 member_of DISAMBIGUATE — was `member_of:`; Rule 12 now derives via `subsystem_hub[cap]`) OR manual authoring of `subsystems_touched:` (Rule 12 violation).

v3.6+ checks (releases ≥ v1.35.0 ship):

25. *(WARN v1.35.0+ grace period; ERROR ratchet planned v1.36.0+)* If `release_version` ≥ v1.35.0 AND `status: shipped`, body MUST contain a `## Chain Progress Snapshot` section. Required content per Governance Rule 13 + [`render-chain-progress-board.skill (135be96d)`](../skills/render-chain-progress-board.skill.md). Releases ≤ v1.34.0 grandfathered per composition rule below.

v3.7 checks (releases ≥ v1.54.0 ship AND < v1.56.0 ship — RETIRED at v3.8):

26. *(WARN v1.54.0+ grace period — RETIRED at v3.8 per v1.56 Lane X.1)* `subsystems_touched:` equals the EXTENDED derived value under Rule 14 (union of Rule 12 capabilities path + Rule 14a kernel-path-table derivation + Rule 14b type:pipeline subsystem_hub propagation). **Status: RETIRED at v3.8.** Applied to v1.54.0 + v1.55.0 release entries only; v1.56.0+ releases follow v3.8 contract where Check 24 (Rule 12 1-hop derivation) alone governs subsystems_touched correctness. Implementation lived in `.tropo/scripts/validate-capability-membership.py` v3.7 form; v1.56 Lane X.2 reverts to v3.4-era Rule 12 1-hop traversal only (Talos engineering). Preserved as historical record for grandfathering enforcement; not actively checked against v1.56.0+ release entries.

Core checks inherited: UID uniqueness, UID immutability, type immutability, owner/created/modified invariants.

### Grandfathering — Composition Rule (oldest applicable boundary wins)

When an entry qualifies for multiple grandfathering rules, the OLDEST applicable boundary wins:

- `created < 2026-04-21` → v1.0 rules only (checks 1-7); v2.0/v3.1/v3.2/v3.3/v3.4 waived
- `created ≥ 2026-04-21` AND `release_date < v1.4.2 ship` → v3.1 Rule 10 + Checks 17-18 + v2.0 body shape; v3.2 Checks 19-21 + v3.3 Check 22 + v3.4 Checks 23-24 waived
- `release_date ≥ v1.4.2 ship` AND `release_date < v1.7.0 ship` → full v3.2 contract (Checks 1-21); v3.3/v3.4 waived
- `release_date ≥ v1.7.0 ship` AND `release_date < v1.8.0 ship` → full v3.3 contract (Checks 1-22); v3.4 waived
- `release_date ≥ v1.8.0 ship` AND `release_date < v1.35.0 ship` → full v3.4 contract (Checks 1-24); v3.6 + v3.7 waived
- `release_date ≥ v1.35.0 ship` AND `release_date < v1.54.0 ship` → full v3.6 contract (Checks 1-25); v3.7 waived
- `release_date ≥ v1.54.0 ship` AND `release_date < v1.56.0 ship` → full v3.7 contract (Checks 1-26); Rule 14 extended derivation governs (applies to v1.54 + v1.55 release entries only)
- `release_date ≥ v1.56.0 ship` → v3.8 contract (Checks 1-25; Check 26 RETIRED; Rule 14 RETIRED). Rule 12 1-hop derivation alone governs subsystems_touched correctness. Post-Pillar-1-tools-migration, tools carry proper `member_of:` graph citizenship; the path-pattern indirection Rule 14a introduced becomes redundant; Rule 14b similarly retires as type:pipeline capabilities carry `member_of:` at root projects.

**Boundary-inclusivity:** the ship date itself is in the new era (inclusive of ship date, exclusive of dates before). When a target slips, the boundary is the actual ship date, not the target.

Canonical grandfathered exemplars: v1.1.0 (v1.0-era), v1.4.1 (v3.1-era), v1.6 (v3.2-era), v1.7 (v3.3-era; first under Rule 11), v1.8 (v3.4-era; first under Rule 12).

---

## 5. Composes-With

- **[release-plan.capsule (a3f1e7b2)](release-plan.capsule.md)** — paired sibling. Every release has exactly one release-plan; every completed release-plan has exactly one release. Bidirectional: `shipped_release_plan:` ↔ `shipped_release:`.
- **[build.capsule (b3d7e5a1)](build.capsule.md)** — upstream. Releases derive from builds; bidirectional pair via `derived_from:` ↔ `composes_into:`. Single build per release.
- **[pipeline.capsule (e4c8a6b2)](pipeline.capsule.md)** — declares `release` as the Deploy-stage artifact type.
- **[subsystem-hub.capsule (8a4e21c5)](subsystem-hub.capsule.md)** — bidirectional pair via release_history rows derived from this capsule's `subsystems_touched:`.
- **[release-test-plan v2.0.1 (f4a8c2d6)](../../vault/files/f4a8c2d6.md)** — Rule 10 governance reference. 4-stage paired-mode gauntlet defined there.
- **[deploy-archive evergreen project (e5a6c7b8)](../../vault/files/e5a6c7b8.md)** — terminal sink for release-plan entries that closed without shipping (not for shipped releases).
- **[document.capsule (d0c00001)](document.capsule.md)** — `pattern_exemplar`. release is patterned on document (per v3 Decision 3) with atomic-triangle + revocation-protocol + versioned-shipment discipline layered on.
- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor for UID/owner/modified invariants.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — this capsule's own governance; Rule 1 scope clarifier delegates capsule-file amendment discipline here.
- **[`render-chain-progress-board.skill (135be96d)`](../skills/render-chain-progress-board.skill.md)** *(v3.6)* — codifies the format + when + where for the `## Chain Progress Snapshot` required body section per Rule 13. Skill is the canonical authoring procedure; capsule is the structural enforcement.

### History

The v2.0 supersession note + amendment-block prose at top of the original v3.4 body, the verbose inline YAML 4-entry `verification_artifacts:` worked example (~40 lines; full authoring reference for cold dispatchers), the Stage 3 paired-mode dispatcher rationale + DEFERRED-PENDING-CAPSULE edge cases (preserved fully because audit-load-bearing), the Known Enforcement Gaps table (15 rows), the full §Studio — Shop Signage authoring procedure (human-facing quick-ref preserved per Mike-A55 *"capsules are agent-read, not human-read"* directive), the Relationship-to-release-plan comparison table, the Extension-from-core section, and the full changelog are preserved in the companion [release.history.md (ff5653d5)](release.history.md) governed by `capsule-history.capsule` (5ec083a3).

---

*release capsule definition | LOCKED v3.8 | history at [release.history.md](release.history.md) | v3.8 amendment 2026-05-27 by Argus A85 captain-mode (v1.56.0 cycle X.1 — Rule 14 + Check 26 RETIRED; Rule 12 1-hop derivation alone governs subsystems_touched post-Pillar-1-tools-migration; preserved as historical record for v1.54-v1.55 grandfathering per Mike-A85 standing architect-led-roadmap-optimization authority per stm-a85-001). v3.7 amendment 2026-05-25 by Argus A84 captain-mode (v1.54.0 ship - substrate_verify_twice_findings ledger + Rule 14 extended derivation per Mike-A84 walk-lock on [cycle brief 5d0c831f v0.2](../../vault/files/5d0c831f.md) + [dev-spec 137ac7e1 v1.0](../../vault/files/137ac7e1.md)). v3.6 amendment 2026-05-16 by Argus A68 (v1.35.0 ship — chain-progress-snapshot bakery per Mike-A68 directive). v3.5 body refactor 2026-05-11 by Argus A56 (v1.19.0 Stream C — 5-section pedagogy pattern; agent-read-not-human-read per Mike-A55 v1.18.0 walk Q3). Prior v1.0–v3.5 locks preserved in history. UID `b19e8d43` preserved.*
*"The plan coordinates. The build packages. The release records. History stands; retrospective grows."*
