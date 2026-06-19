---
uid: ff5653d5
name: "release-history"
type: capsule-history
governs: b19e8d43
governs_path: .tropo/capsules/release.capsule.md
extracted_at: 2026-05-11
extracted_by: argus-a56
extracted_in_cycle: "v1.19.0 — Convergence Phase 1"
extracted_in_release: pending-v1.19.0
schema_version: 2
governed_by: 5ec083a3   # capsule-history.capsule
extraction_scope: argo-private
member_of:
  - "8dd772a0"   # tropo-governance
tags: [capsule-history, extracted-from-release-capsule, v1.19.0-stream-c]
---

# release — Capsule History

*History extracted from release.capsule v3.4 → v3.5 body refactor (v1.19.0 Stream C; 2026-05-11). The active capsule preserves the Required floor + 12 Governance Rules + 24 Validation Checks + Grandfathering Composition Rule + State Machine + Composes-With per the 5-section pedagogy pattern. This file preserves: v2.0 supersession note + amendment-block prose; the verbose inline YAML 4-entry verification_artifacts exemplar (now compactly referenced in active); Stage 3 paired-mode rationale prose + DEFERRED edge cases (preserved fully); Known Enforcement Gaps table; §Studio — Shop Signage human-facing quick-ref; Relationship-to-release-plan comparison table; Extension-from-core section; Inheritance section; full changelog table.*

---

## Amendment Blocks (extracted from v3.4 active body opener)

### v2.0 supersession note (extracted)

v1.0 (April 16, 2026) was authored before the typed-pipeline architecture locked. It predates `derived_from:` / `composes_into:` composability fields and the build / release-plan bidirectional pair. v2.0 integrates with typed pipeline (per design brief d2e7b1f4); UID `b19e8d43` preserved so existing references stay valid. **v1.0 release entries (pre-2026-04-21) are grandfathered as v1.0-compliant** per Mike's no-migration directive; new entries (2026-04-21 onward) follow v2.0.

### Pattern precedent (extracted)

Tropo-OS v1.1 release entry v1.3 historical reference is the v1.0 exemplar — v2.0 preserves the shape while adding the typed-pipeline composability.

---

## Inline verification_artifacts v3.2 worked example (extracted)

*Preserved here for cold authoring per cold-boot 108 P0-1 closure. Active capsule §2 Schema cites the field shape; full inline YAML preserved here as authoring reference.*

```yaml
verification_artifacts:
  - type: walker                  # Stage 3.1 — sa.first-use-walker
    record_uid: <activation-log-record-uid>
    verdict: PASS                 # 4-valued: PASS / PASS-WITH-FINDINGS / PARTIAL / FAIL / DEFERRED-PENDING-CAPSULE
    dispatcher: metis-g48         # walker family allowlist per sa.first-use-walker fb925dea independence
    dispatched_at: 2026-05-14
    peer_record_uid: <Stage 3.2 strict cold-boot record UID>   # convergence citation per dispatch-walker.playbook v0.2 Step 9
  - type: cold-boot               # Stage 3.2 — sa.cold-boot
    mode: strict
    record_uid: <activation-log-record-uid>
    verdict: PASS-WITH-FINDINGS
    dispatcher: vela-v37          # cold-boot family — any executive per dispatch-cold-boot.playbook v0.2 Rule 9
    dispatched_at: 2026-05-14
    peer_record_uid: <Stage 3.3 skeptic cold-boot record UID>
  - type: cold-boot               # Stage 3.3 — sa.user-error-walker (NEW v1.4.2; cross-family by lineage)
    mode: skeptic
    record_uid: <activation-log-record-uid>
    verdict: PASS
    dispatcher: metis-g48         # cold-boot family allowlist + sa.user-error-walker §Trust Contract soft-independence
    dispatched_at: 2026-05-14
    peer_record_uid: <Stage 3.2 strict cold-boot record UID>
    mistake_count_total: 7        # required per Check 20 (length-match)
    per_mistake_outcomes:         # required per Check 20 — array length MUST equal mistake_count_total
      - mistake: "Open Claude Code in the parent dev repo"
        outcome: PASS
        explanation: "Concierge surfaced + redirected to extracted release"
      - mistake: "Author task without member_of:"
        outcome: PASS
        explanation: "Validator caught D7 violation at write-time"
      # ... 5 more entries; one per dispatched mistake; verbatim mistake-list correspondence
  - type: validate                # Stage 3.4 — extracted-vault structural validation
    record_uid: <validate-output-uid OR run-id>
    verdict: PASS
    exit_code: 0                  # 0 = PASS; non-zero = FAIL per tropo-validate.py-class invocation
    dispatcher: vela-v37
    dispatched_at: 2026-05-14
```

**Stage 3.4 validate-entry note:** dispatch-walker.playbook v0.2 + dispatch-cold-boot.playbook v0.2 declare canonical typed-object shapes. Stage 3.4 (validate) does NOT yet have a dispatch-validate playbook. The minimum shape (`type: validate`, `record_uid:`, `verdict:`, `exit_code:`, `dispatcher:`, `dispatched_at:`) is v3.2's interim contract; forthcoming `dispatch-validate.playbook` canonicalizes. Tracked in §Known Enforcement Gaps row "Stage 3.4 dispatch-validate playbook."

---

## Stage 3 paired-mode rationale + DEFERRED edge cases (preserved)

### Stage 3.3 dispatcher rationale (added v3.2 per cold-boot 108 P0-2)

Stage 3.3 is named "cold-boot mode:skeptic" by lineage with Stage 3.2 (Strict-vs-Skeptic brief framing per [f7b3e2a1](../../vault/files/f7b3e2a1.md)). The dispatcher agent is **`sa.user-error-walker`** (not `sa.cold-boot`) because the Skeptic contract is closer to walker than to cold-boot — per Argus A41 path-2 architectural decision 2026-05-01: Skeptic-mode tests system-resilience-under-user-error (a third distinct contract; not a cold-boot variant). The "cold-boot mode" naming preserves operational lineage; the cross-family dispatcher is intentional, not a typo.

### Edge Cases — DEFERRED-PENDING-CAPSULE × paired-mode + per_mistake_outcomes

- **Stage 3.3 returns DEFERRED before probing any mistakes:** Check 19 (paired-mode required) PASSES — the DEFERRED record exists; presence satisfied. Check 20 (per_mistake_outcomes non-empty) is **WAIVED** when `mistake_count_total: 0` AND deferral preceded probing. The deferral metadata (deferred_capsule_uid + rationale in activation-log record) substitutes for per-mistake granularity.
- **BOTH Stage 3.2 + 3.3 return DEFERRED:** atomic-triangle commit BLOCKED. A release cannot ship with deferred verdicts on both Strict + Skeptic — that's an unverified release. Dispatcher escalates: resolve at least one Stage 3 path before ship, OR revoke the release-plan and re-cycle.
- **Stage 3.3 returns DEFERRED with `mistake_count_total > 0` but per_mistake_outcomes empty:** Check 20 FAILS. The DEFERRED verdict cannot be authored mid-walk — it must be authored before any mistake probing begins (with `mistake_count_total: 0`), OR after all dispatched mistakes have been probed (with per_mistake_outcomes populated).
- **Stage 3.4 returns DEFERRED:** treated like Stage 3.2 single-mode DEFERRED — Check 19/20 paired-mode rules don't apply to validate; reviewer-of-record audits the deferred-capsule UID per Check 21.

### v3.1 sub-stages (release_date < v1.4.2 ship — grandfathered)

Stage 3.1 (walker) + Stage 3.2 (cold-boot singular) + Stage 3.3 (vault validate per v3.1-era numbering — note the renumbering collision: under v3.2 numbering, vault validate is Stage 3.4 and "Stage 3.3" means Skeptic; see release-test-plan v2.0.1 §translation table). 3-valued verdict vocab (PASS / PASS-WITH-FINDINGS / HALT-SHIP). v1.4.1 release [`8c4cb474`](../../vault/files/8c4cb474.md) + earlier are grandfathered under v3.1 Rule 10 — no retroactive migration.

---

## Known Enforcement Gaps (extracted)

| Gap | What closes it | Target release | Owner |
|---|---|---|---|
| Body immutability after ship is honor-system (Check 16); mechanical enforcement requires diff-check at rebuild | Hash-and-diff-check trigger at lock-time | v1.5.0+ | argus |
| Atomic-commit triangle (release-plan.shipped_release + build.composes_into + release.derived_from) — bidirectional pairs enforced, atomicity honor-system | Pre-commit hook enforcing atomic triangle updates | v1.4.0 | argus + vela |
| §Retrospective appendable-only discipline is honor-system — mechanical enforcement requires section-diff parsing | Same hash-and-diff solution as body-immutability gap | v1.5.0+ | argus |
| Grandfathering boundary — v1.0-era entries don't have the v2.0 fields; validator needs to honor the 2026-04-21 cutoff date when choosing rule set | Date-gated validator logic (simple) | v1.4.0 | argus |
| Stage 3.4 dispatch-validate playbook does not yet exist (v3.2) | Author dispatch-validate.playbook (Vela-lane; mirrors dispatch-walker + dispatch-cold-boot pattern) | v1.4.3 or v1.5.0+ | vela |
| Skeptic mistake-list substantiveness (v3.2) — Check 20 enforces shape (length-match + verbatim correspondence) but cannot enforce that dispatched mistakes are non-trivial | Closed by sa.user-error-walker v1.0 §Trust Contract (mistake-list completeness attestation) + reviewer-of-record audit. v1.1+ candidate: minimum-mistake-count threshold for Pattern B dispatches | v1.5.0+ | argus |
| DEFERRED-PENDING-CAPSULE operational discriminator (v3.2) — Rule 10 cites the verdict's intent but no non-self-referential operational rule for "when does an instrument return DEFERRED on a normal release?" | v1.4.3 candidate: prose §When-to-Defer rubric with 2-3 abstract conditions; OR formalized via dispatch-cold-boot.playbook v0.3 amendment | v1.4.3+ | argus + vela |
| Sub-stage `[PENDING]` dispatch templates absent (v3.2) — Rule 10 cites four agents but inlines zero `[PENDING]` templates | v1.4.3+ candidate: forthcoming `run-release-test-plan.playbook` inlines the 4 templates; alternative: §Studio §Procedures pointer-table | v1.4.3+ | vela |
| PARTIAL / DEFERRED tolerance ceiling unbounded (v3.2) — no upper bound on PARTIAL severity that triggers ship-block | Closed by reviewer-of-record audit + Mike-signed §G.5 ship gate, not validator. Honest about the protocol shape | inherent — protocol design | argus + mike |
| Grandfathering boundary anchor — target date vs build_version — current boundary is literal date `2026-05-14`; if v1.4.2 slips, the prose date doesn't auto-update | Reframe boundary in §Grandfathering rule to cite build_version anchor | v1.5.0+ | argus |
| Sibling-drift on `mistake_count_total:` field — capsule's Check 20 requires `per_mistake_outcomes:` length to equal `mistake_count_total:`; dispatch-cold-boot.playbook v0.2 §Step 9 doesn't yet declare `mistake_count_total:` in its Skeptic-mode exemplar | V37-lane sibling-sweep amendment to dispatch-cold-boot.playbook v0.2 → v0.3 declaring `mistake_count_total:` field. Tracked at task UID 821ad746 | v1.4.3 cycle | vela |
| Composition rule `created:` field gameable (v3.2 Round-2) — author can back-date YAML `created:` to claim v1.0-era grandfathering | v1.5.0+ candidate: NEW Check cross-checking `created:` consistency against build entry's `created:`. Closed by reviewer-of-record audit until then | v1.5.0+ | argus |
| Check 20 verbatim-correspondence has no canonical structured mistake-list source — dispatch-cold-boot.playbook v0.2 puts mistake-list in unstructured `[PENDING]` prose; mechanical exact-string match impossible without canonical source | Mechanical enforcement requires dispatch-cold-boot.playbook v0.3 add `dispatched_mistakes:` structured array | v1.4.3 cycle | vela + argus |
| Check 21 forward-task lifecycle gap — Check 21 enforces deferred-capsule UID resolves to forward-dated task, but does NOT enforce the cited task progresses | v1.5.0+ candidate: extend Check 21 with task-progression cross-check | v1.5.0+ | argus |
| Stage 3.3 numbering archaeology (v3.2 Round-2) — readers auditing grandfathered v1.4.1 entries must cross-reference release-test-plan v2.0.1 §translation table | v1.4.3 polish: inline mini-table; OR accept as documented per current parenthetical | v1.4.3+ | argus |

---

## Studio — Shop Signage (extracted human-facing quick-ref)

*Preserved per Mike-A55 directive 2026-05-11: capsules are agent-read, not human-read. Active capsule §5 Composes-With teaches the type to the agent; this section preserved the workflow guide to a human author.*

### Tools available

- `scripts/build-release.py` — Argo's release builder; authored at ship moment; produces manifest + zip at `releases/v<ver>/dist/`. Argo-only (`extraction_scope: argo-reference` per v1.5; not in user vaults).
- `scripts/rehydrate.py` — regenerates ledger indexes post-ship (captures the release entry in caches)
- `git tag` — authoritative version marker; applied at Mike-signed ship gate
- Atomic-triangle validator *(forthcoming v1.4 pre-commit hook)* — enforces release / build / release-plan bidirectional pairs at commit time

### Skills

- `author-release.skill.md` *(forthcoming v1.5)* — populates release entry atomically with build + release-plan pair updates
- `retrospective-append.skill.md` *(forthcoming v1.5)* — the ONLY legal post-ship body-mutation protocol; appends §Retrospective with author + timestamp
- Revocation protocol *(undocumented skill; forthcoming)* — when a release must be pulled; populates `revoked_at:` + `revoked_reason:` + §Retrospective

### Procedures

- §G.5 Founder ship-signal protocol — Mike authorizes per §5.5.3 authorized language ("ship it" / specific equivalents)
- Gate 5 First-Use Walk — blocks §G.5 eligibility until stranger-encounter test PASSes (fb925dea)
- Test-Plan execution per release-test-plan f4a8c2d6 (v1 era for v3.1 entries; v2.0.1 era for v3.2 entries) — pre-build / build / post-extraction stages; gates atomic-triangle commit eligibility per Rule 10. v3.2: 4-stage paired-mode (3.1 walker / 3.2 cold-boot strict / 3.3 cold-boot skeptic / 3.4 validate)
- Ship-sequence script §A→§I (Vela-established pattern) — authors release entry + flips release-plan to `done` + sets build `composes_into:` atomically
- Three-instrument verification on the shipping build — inherited from build.capsule Rule 5 (release can only derive from builds whose test-results are populated)

### Pitfalls

- **Using `release` as the terminal artifact for a content-production pipeline** → v3 Decision 11 violation. Content publications terminate in `document` at `status: published`, NOT in a release. Release is for versioned software releases with coordination-plan (triangle: release-plan + build + release). If you find yourself setting `shipped_release_plan: null` on a release because there's no release-plan in your pipeline, you picked the wrong capsule — use `document` instead. See v3 spec §6 Decision 11 + 3f8a9b2c as worked example of content-terminal-as-document.
- Editing body after ship → Rule 1 violation; history is not mutable
- Version drift between build and release → Rule 2 + Check 9 failure
- Setting one triangle field without the other two → inconsistent graph; rollback
- Revocation without §Retrospective → audit trail incomplete
- Treating release as a plan → release records; plans coordinate; different temporal directions
- Silent supersession without `superseded_by:` set on prior → bidirectional pair broken
- **(v3.4)** Manually authoring `subsystems_touched:` on a v1.8+ release entry → Rule 12 violation + Check 24 mismatch. The field is DERIVED from `capabilities_touched:` via 1-hop graph traversal at B6 ship.
- **(v3.4)** Filing a v1.8+ release entry whose `capabilities_touched:` differs from the linked release-plan's `capabilities_touched:` → Rule 12 + Check 23 mismatch.
- **(v3.4)** Tagging a capability into `capabilities_touched:` whose `member_of:` lacks any subsystem hub UID → derivation produces empty `subsystems_touched:` for that contribution; Check 24 may fail downstream.
- **(v3.4)** Treating v3.3's `Rule 11` as superseded — it isn't. Rule 11 stays in force (subsystem-registry consistency); Rule 12 ADDS the typed-derivation discipline alongside it.

### Worked examples

- [Tropo-OS v1.3.1 (a5df7dac)](../../vault/files/a5df7dac.md) — current live release; v2.0 shape; 2026-04-22 ship
- [Tropo-OS v1.2.1 (13edb182)](../../vault/files/13edb182.md) — superseded-by v1.3.1
- [Tropo-OS v1.2.0 (4ad1fc10)](../../vault/files/4ad1fc10.md) — v1.0-era grandfathered

### Go next

- Upstream coordination → [release-plan.capsule (a3f1e7b2)](release-plan.capsule.md)
- Upstream packaging → [build.capsule (b3d7e5a1)](build.capsule.md)
- Ship pipeline position → [pipeline.capsule (e4c8a6b2)](pipeline.capsule.md)
- Known Issues references → [task.capsule (3289712a)](task.capsule.md) for follow-up tasks

---

## Relationship to release-plan — Comparison Table (extracted)

Complementary at opposite temporal directions:

| Dimension | `release-plan` | `release` |
|-----------|----------------|-----------|
| **Temporal direction** | forward (plans) | backward (records) |
| **Authored** | before + during build | at ship moment |
| **Closes when** | release ships | release is superseded or revoked |
| **Mutability** | editable through `build` stage | immutable after ship except §Retrospective |
| **Answers** | "how do we get there?" | "what shipped?" |

Both exist for every release (v2.0 era onward). Linked via bidirectional pair: `release-plan.shipped_release: <release-uid>` ↔ `release.shipped_release_plan: <release-plan-uid>`.

---

## Extension from core

*Where this capsule specializes core.capsule (ee814120).* release.capsule extends core: **title** allowed up to 120 chars (core: 100; release titles carry version strings); **description** up to 200 chars (core: 120; release descriptions need room for narrative); `status:` as workflow state (`done` literal at authoring); `state:` as archive-visibility (`active/archived`) — two-field model reflecting the post-ship record's stability: the record is born done, lives active, eventually archives. **v3 amendment (v3.0):** the `stage: deploy` pipeline-position literal previously required by v2.0 has been dropped per v3 Decision 4 — releases are identified by `type: release` alone; pipeline-position is a property of the pipeline-run, not the work. All frontmatter is immutable at ship except two carve-outs (Rule 1). Body is immutable except appendable §Retrospective.

---

## Inheritance

Extends `core`. Inherits UID immutability, type immutability, owner/created/modified invariants. Documented in active capsule §5 Composes-With.

---

## Changelog (full lineage)

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-04-16 | LOCKED. Initial version. Required frontmatter for title/description/owner/stage/state/version; state machine `build → verify → deploy → done → archived`; 7 validation checks. Authored pre-typed-pipeline-architecture. | tropo |
| 2.0 | 2026-04-21 | Major version bump. D4 deliverable of v1.3 Typed Pipeline Capsule Ship project plan. Integrates with typed pipeline architecture: added composability fields (`derived_from:` pointing at build, `shipped_release_plan:` bidirectional pair with release-plan), added 4 required body sections (What Shipped / Release Notes / Verification Summary / Known Issues), added §Retrospective as only post-ship appendable section, simplified state machine from v1.0's stage-progression to v2.0's `(birth) → active → archived`, renamed `version:` → `release_version:` for clarity. UID `b19e8d43` preserved so existing references stay valid. v1.0 release entries grandfathered. | argus-a30 |
| 3.0 | 2026-04-24 | v3 amendment. `stage: deploy` frontmatter literal dropped per v3 Decision 4. §Scope condition 2 removed; Required Frontmatter `stage` row removed; Validation Check 2 removed. Extension-from-core paragraph rewritten. NEW §Studio Pitfall added per v3 Decision 11 (release-as-content-terminal violation). `pattern_exemplar: d0c00001` declared per Decision 3 — release is patterned on document.capsule with atomic-triangle + revocation-protocol + versioned-shipment discipline layer. UID preserved at b19e8d43. | argus-a33 |
| 3.1 | 2026-04-29 | Test plan amendment. Promotes `sa.cold-boot` Stage 3 instrument from optional V36-lane practice to required pre-ship gate via new Governance Rule 10 referencing release-test-plan v1 (f4a8c2d6). Adds `verification_artifacts:` required frontmatter (array of activation-log UIDs — cold-boot + walker + extracted-vault-validate). Adds Validation Checks 17 & 18 enforcing verification_artifacts contents + cold-boot PASS-only verdict gate. v3.0 release entries grandfathered. Authored by vela-v36 under Mike authorization 2026-04-29; v1.4.1 is the first release shipping under v3.1 regime. UID preserved at b19e8d43. | vela-v36 |
| 3.2 | 2026-05-01 | LOCKED. Rule 10 + verification_artifacts shape amendment for v1.4.2-cycle alignment. Round-1 BATCH (arch-specs 030 + skeptic 031 + cold-boot 108) → 7 P0 + 14 P1/P2/P3; healthy convergence. Round-1 fold: Rule 10 expanded to 4-stage paired-mode + 4-valued verdict vocab + Stage 3.3 dispatcher rationale + §Edge Cases for DEFERRED; verification_artifacts union-shape + inline YAML 4-entry exemplar; NEW Checks 19/20/21 (paired-mode + Skeptic substantive correspondence + DEFERRED structural anchor); §Grandfathering restructured with v1.0-era + v3.1-era subsections + oldest-wins composition rule. Round-2 regression BATCH (arch-specs 031 + skeptic 032 + cold-boot 109) → Q1 close-out YES; 0 P0 + 9 P1-3 NEW findings appended as §Known Enforcement Gaps. v3.2 required for `release_date ≥ v1.4.2 ship`. UID preserved at b19e8d43. | argus-a41 + Mike Maziarz |
| 3.3 | 2026-05-05 | LOCKED. Subsystem documentation as release deliverable (D2 of v1.7 brief 6b5f7886). NEW Rule 11 + NEW Validation Check 22 + v1.7-era grandfathering boundary. Soft-gated v1.7-v1.9 (honor-system); hard-gated v1.10+ via `scripts/validate-subsystem-hubs.ts`. Bidirectional pair with subsystem-hub.capsule v1.3 `release_history:` field. v1.7 ship is first release under Rule 11 + Check 22 (dogfood gate). UID `b19e8d43` preserved. Single-instrument sa.cold-boot verification PASS-WITH-FINDINGS aggregate; right-sizing pin. | argus-a45 |
| 3.4 | 2026-05-05 | LOCKED — v1.8 Stream A2 amendment (source brief: fd2d9e77). Capabilities are the typed unit; subsystems are derived (Mike-A46 pair-design D3, 2026-05-05). NEW Rule 12 (capabilities_touched mirrored from release-plan; subsystems_touched DERIVED via 1-hop graph traversal over `member_of:` — author never types subsystems_touched directly). NEW Optional Frontmatter `capabilities_touched:` (REQUIRED at status:done for releases ≥ v1.8.0 ship). NEW Optional Frontmatter `subsystems_touched:` (DERIVED — DO NOT AUTHOR). NEW Validation Checks 23 + 24. Grandfathering composition rule extended with v3.4-era boundary at v1.8.0 ship date. Drift collapse: under v3.3 Rule 11, registry rows + hub release_history could theoretically disagree; under v3.4 Rule 12, both are computed from the same source-of-truth on the release entry; divergence is structurally impossible. v1.7 release a676a5f2 is canonical v3.3-grandfathered exemplar; v1.8 ship is first release under Rule 12. UID `b19e8d43` preserved. | argus-a46 |
| 3.5 | 2026-05-11 | **v1.19.0 Stream C — Capsule Pedagogy Completion.** Body refactor to 5-section pedagogy pattern (Intent → Schema → State Machine → Validation Rules → Composes-With) per Mike-A55 *"capsules are agent-read, not human-read"* directive from v1.18.0 walk. Active body reduced from 536 → ~300 lines (~44% reduction). All 12 Governance Rules + 24 Validation Checks + Grandfathering Composition Rule preserved in active body (substrate-load-bearing; cannot drop). Extracted to this `.history.md` companion: v2.0 supersession note + amendment-block prose at top, the verbose inline YAML 4-entry verification_artifacts exemplar (compactly cited in active), Stage 3 paired-mode dispatcher rationale + DEFERRED-PENDING-CAPSULE edge cases (preserved fully), Known Enforcement Gaps table, §Studio — Shop Signage human-facing quick-ref, Relationship-to-release-plan comparison table, Extension-from-core and Inheritance sections, full changelog. **No schema changes, no validation rule changes, no governance rule changes, no state machine changes.** Bidirectional pointer pair: active capsule frontmatter `history_file: ff5653d5` ↔ this file's `governs: b19e8d43`. UID `b19e8d43` preserved. | argus-a56 |

---

## Provenance

- **Extracted at:** 2026-05-11
- **Extracted by:** argus-a56 (during v1.19.0 Stream C — Capsule Pedagogy Completion)
- **Active capsule version at extraction:** v3.4 (536 lines)
- **Active capsule version after extraction:** v3.5 (~300 lines; ~44% reduction)
- **Extraction-fidelity check:** All historical content preserved. Active capsule retains all 12 Governance Rules, all 24 Validation Checks (including version-gated v3.1-v3.4 checks), the full Grandfathering Composition Rule, both State Machine and Required Body Sections. No semantic changes; body restructure only. Reduction lower than v1.18.0 average because release.capsule carries the densest version-gated validation surface in the library (3 grandfathering eras + paired-mode + 4-staged test plan + DEFERRED edge cases).

---

*release capsule history | UID ff5653d5 | v1.19.0 Stream C extraction 2026-05-11 by Argus A56 | Bidirectional pair: governs b19e8d43*
