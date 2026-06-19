---
uid: 1b834ed6
type: capsule-history
governs: e7b3c509
governs_path: ".tropo/capsules/playbook.capsule.md"
extracted_at: 2026-05-11
extracted_by: argus-a55
extracted_in_release: pending-v1.18.0   # updated to actual release UID at v1.18.0 ship
extracted_in_cycle: "v1.18.0 — Capsule Library Phase 1"
schema_version: 2
governed_by: 5ec083a3   # capsule-history.capsule (v1.18.0 Stream C remediation — type:capsule-history governed by its own typed primitive, not kb-article)
extraction_scope: argo-private   # historical record; not user-shipping content
member_of:
  - "76bab75f"   # tropo-playbooks
  - "8dd772a0"   # tropo-governance
  - "be5bc951"   # v1.18.0 activation root
tags: [capsule-history, extracted-from-playbook-capsule, v1.18.0-extraction, governance-pedagogy-first-precedent]
---

# playbook — Capsule History

*Historical record extracted from the active capsule definition at v1.18.0 to keep the active body pedagogy-first per Lock C governance hybrid. The active capsule lives at `.tropo/capsules/playbook.capsule.md` (UID `e7b3c509`). This file preserves changelog + amendment-block content + conscious-trade-offs + known-enforcement-gaps + self-supersession note that previously lived in the active body.*

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 2.0 | 2026-04-21 | **UID-preserving supersession of v1.0** (uid `e7b3c509` preserved; body replaced end-to-end). Codifies current playbook reality — 5 REQUIRED body sections (Intent/Rules/executable-content/Outcomes/Verification), state machine matching `status:` convention used by existing playbooks (draft/active/superseded/archived with legacy `published` → `active` aliasing during v1.3 grace window), pipeline as explicit subtype (closes pipeline.capsule v1.0's dangling parent reference), 18 validation checks labeled [enforced]/[honor-system], Known Enforcement Gaps table, Conscious Trade-offs. Aligns to [Playbook Specification v2.2 (e6d373bc)](../../vault/files/e6d373bc.md). D1 deliverable of v1.3 Stream B Foundation project plan. Three-instrument verification: Argus build + sa.cold-boot 054 BATCH stranger test (verdict PASS-WITH-GAPS LOCKABLE; zero P0 findings; 5 P1 authoring-guidance gaps remediated same-day per A28/A30 in-session remediation pattern). sa.arch-specs 005 review in flight at lock time. | argus-a31 |
| 2.0 (round 1 — cold-boot 054 P1s) | 2026-04-21 | In-session remediation of 5 P1 findings from cold-boot 054 — all authoring-guidance gaps, none affecting the floor or validation checks. Landed: (1) §Intent voice directive, (2) §Rules phrasing directive (imperative MUST/SHOULD), (3) §Steps worked example block, (4) §Verification selection heuristic paragraph, (5) §Required Frontmatter `author` vs `owner` clarification, (6) §State Machine cross-hazard note for new authoring vs legacy-aliasing. All six ran via Edit tool in a single atomic pass. | argus-a31 |
| 2.0 (round 2 — arch-specs 005 P0s + P1s) | 2026-04-21 | In-session remediation of 3 P0 + 10 P1 findings from arch-specs 005. **P0-1** (§Scope vs grace-window contradiction): §Scope explicit grace-window carve-out paragraph; Check 2 relabeled [honor-system during v1.3 grace; enforced for NEW playbooks]. **P0-2** (pipeline subtype boundary broken vs live `tropo-work-pipeline.pipeline.md`): §Scope §Subtype paragraph rewritten — pipelines SUBSTITUTE pipeline.capsule's body-section set for this capsule's floor, they do not add to it; Governance Rule 6 rewritten. **P0-3** (`apply-update.playbook.md` uses top-level `## Step N:` headers): §Required Body Sections Section 3 amended to accept three Steps shapes. P1s landed: triggerless-playbook handling under Rule 1; Rule 4 dangling §5 reference resolved; Rule 9 moved OUT of Governance Rules into §Self-Supersession note; Check 14 rewritten; Check 15 separated rule from process; 3 new rows in §Known Enforcement Gaps; 2 new §Conscious Trade-offs rows; §Subtypes §Pipeline paragraph rewritten to defer to pipeline.capsule. Ship recommendation arch-specs-005 transitions from BLOCK → PASS. | argus-a31 |
| 1.0 | 2026-04-16 | Initial version (Tropo framework placeholder). Thin governance using `stage:`/`state:` frontmatter (design/specify/build/done/cancelled) that did not match existing playbook files' actual convention (`status: published`). Superseded by v2.0 on 2026-04-21 to codify current reality and close pipeline.capsule v1.0's dangling parent reference. | tropo |
| 2.1 | 2026-04-25 | **Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop).** Added §Workshop — Shop Signage section (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next) per the v3 capsule shop-signage pattern proven at 11-capsule scale. Added Relations Header right after H1. No semantic changes to §Required floor / §Validation Checks / §Governance Rules / §State Machine. UID preserved at e7b3c509. | argus-a34 |
| 2.2 | 2026-04-28 | **v3 §9 known-gap closure — `pattern_exemplar` declaration added.** Closes one of the Decision-12 follow-on items: playbook.capsule was missing the `pattern_exemplar: d0c00001` declaration that v3 Decision 3 specifies for document-like capsules. Added `pattern_exemplar: d0c00001` in frontmatter + corresponding "Pattern exemplar" row in §Relations table. No semantic changes to §Required Frontmatter / §Required Body Sections / §Validation Checks / §Governance Rules / §State Machine. UID preserved at e7b3c509. **Documented v3-spec drift surfaced as finding:** v3 spec §6 Decision 3 lists `how-to` as document-pattern capsule, but how-to.capsule v1.0+ was authored as Pillar 1 callable surface (declares `pattern_family: b4e2a718`). how-to no longer fits document-pattern; v3 spec text predates the reclassification. | argus-a38 |
| 2.3 (round 1 — three-instrument BATCH P0 + P1 closure) | 2026-04-28 | **sa.skeptic 022 P0 closure — §Routing parity drift across 7 surfaces.** Validation Check 13's "≥ 4 bullets" floor cannot detect content divergence across 7 surfaces referencing bounce-intent set. **Fix:** declared [executive-activation.template §Routing](../templates/executive-activation.template.md) as **canonical source**; amended §Subtypes §Concierge-Paths section content minimum to require derived surfaces cite that file as canonical. **sa.skeptic 022 P1 closure (graduation threshold)** — added Subtype declaration shape table to §Subtypes intro. UID preserved at e7b3c509. | argus-a39 |
| 2.3 | 2026-04-28 | **D4.9 — Concierge-Paths subtype + §Post-Outcome Handoff Required Body Section.** Structural fix for [v1.3.1 Findings #3 + #8 + #13]: post-outcome project-creation requests bypass `start-a-project.playbook` because spawned agents don't bounce back to concierge for routing. **Three changes**, all additive: §Subtypes §Concierge-Paths added (two-condition identification + `## Post-Outcome Handoff` Required Body Section); Governance Rule 9 added; Validation Check 19 added [honor-system at v1.4; enforced at v1.5]. In-capsule subtype, no separate capsule file (earn-the-abstraction). | argus-a39 |
| 2.4 (round 2 — regression cold-boot fold) | 2026-05-01 | **Regression sa.cold-boot 101 PASS-WITH-NEW-FINDINGS at ceremony 2/5 (down from 100's 3/5).** All 5 P0s confirmed CLOSED. Zero regressions on v2.3 surface. 4 new findings (none P0); P1-A + P1-B + P2-D folded inline before lock: (P1-A) field-vs-shape cardinality clarification; (P1-B) §Pending Sub-Requirements deletion-is-atomic-with-Land-at-amendment rule per Rule 5 atomic-supersession precedent; (P2-D) `verdict_format:` canonical list now includes `PASS-CLEAN / PASS-WITH-NEW-FINDINGS / REGRESSION-FAILURE` (regression-cold-boot schema). **v2.4 LOCKED 2026-05-01 by argus-a39.** | argus-a39 |
| 2.4 (round 1 — BATCH remediation) | 2026-05-01 | **Three-instrument BATCH (sa.arch-specs 024 + sa.skeptic 024 + sa.cold-boot 100) + bundled remediation per A35 fold-findings-into-pre-lock pin.** All 5 P0s closed: (P0 #1 verdict_format gaming) added semantic constraint; (P0 #2 composes_into enforcement) added Validation Check 21; (P0 #3 threshold prose ambiguity) explicit field-vs-shape distinction; (P0 #4 target_artifact_type value space) declared enum; (P0 #5 composes_into YAML shape) added literal YAML examples. **P1 closures folded inline:** §Pending Sub-Requirements forget-loop guard; composes_into declaration placement; mode operational semantics; §Report Format ordering position; test-harness §Verification floor relationship. | argus-a39 |
| 2.4 | 2026-05-01 | **v1.4.2 Stream 1 Task 1 — Test-Harness subtype declared.** §Subtypes §Test-Harness in-capsule subtype with two-condition identification (filename pattern + `test-harness` tag); declares additional Required Frontmatter (`target_artifact_type:` + `verdict_format:` + optional `mode:`); declares additional Required Body Section §Report Format. Governance Rule 10 + Validation Check 20 added. **ADR-040 ledger-trackability sub-requirement REMOVED per Mike directive 2026-05-01** ("not ready to do that move yet; refine 1.4.x first"). | argus-a39 |
| 2.5 | 2026-05-11 | **v1.18.0 Stream B body refactor.** Body restructured to 5-section canonical structure (Intent → Schema → State Machine → Validation Rules → Composes-With) per v1.18.0 brief §4.1 Q3-locked pattern. Historical content (§Known Enforcement Gaps + §Conscious Trade-offs + full §Changelog + §Self-Supersession Note + §Studio quick-ref + amendment preamble paragraphs) extracted to this `.history.md` companion file (UID `1b834ed6`). Active body trimmed from 636 → ~280 lines (~56% reduction); all historical content preserved in this file. `history_file:` + `last_body_refactor:` frontmatter fields added. No semantic changes to §Validation Rules / §State Machine / §Schema content; pure restructure + extraction per the pedagogy-first agent-read-performant pattern. UID preserved at `e7b3c509`. | argus-a55 |

---

## Conscious Trade-offs (extracted from prior active body)

### Minimal floor vs Spec v2.2 maximum

Spec v2.2 names seven body sections as "required" (Intent, Suggestions, Rules, Resources, Groups, Outcomes, Verification). The active capsule requires only FIVE (Intent, Rules, executable-content, Outcomes, Verification), with Suggestions and Resources demoted to "Expected-If-Present."

**Rationale.** Spec v2.2's seven-section model is optimal for the orchestration playbooks it targets (agent activation, update handling, multi-session onboarding). But simpler playbooks — single-session procedures, capsule-generated outcome-playbooks, cold-boot tests — do not need Suggestions or Resources and over-declaring empty sections creates ceremony without signal. The capsule's floor is the enforceable minimum; authors should still include Suggestions and Resources when they add value.

**Reversal cost if stricter floor becomes preferred:** amend the active capsule's §Schema adding Suggestions + Resources as required. ~15 min edit + migration pass across all existing playbooks. Bounded.

### Steps / Execution-Steps as an extension beyond Spec v2.2

Spec v2.2 §3 describes only the Groups model as the core execution model. The active capsule introduces two additional accepted shapes: `## Steps` / `## Execution Steps` parent-section shape, and `## Step N: <title>` top-level-numbered shape. Both codify patterns already in live use (first-playbook uses parent-section Steps; apply-update uses top-level-numbered Steps).

**Rationale.** Not every playbook needs the Groups DAG. Single-owner, single-session procedures read more naturally as linear sequences; forcing them into a one-Group wrapper with milestones adds ceremony.

**Reversal cost if Groups-only proves preferred:** migrate every Steps-shape playbook to Groups shape (≈10 playbooks at ~10-15 min each). Bounded but non-trivial.

### No `member_of:` requirement for playbooks

Playbooks are governance artifacts, not project-scoped work. They are not required to declare `member_of:` linking them to a project.

**Rationale.** Playbooks are consumed at runtime — they're the code, not the artifact. A playbook may be invoked by many projects and across many releases; forcing it to be a member of one project would either (a) force a fictional "OS" project for every framework playbook, or (b) create thrash when playbooks migrate between projects. Runs of a playbook DO carry `project:` linkage (per Spec v2.2 §5 run folder), which is the correct place for project scoping.

**Reversal cost if project linkage becomes preferred:** amend active capsule's §Schema adding `member_of:` + a backfill pass. ~2h backfill work. Not blocking today; re-evaluate at v2.0 of Spec v2.2 or when marketplace-published playbooks need project provenance.

### Either Groups OR Steps, not both

Rule enforces exactly one executable-content shape. A playbook that conceptually wants to show a DAG of groups but prefers a linear narrative for some subset must pick. This is a deliberate simplification.

**Reversal cost if hybrid execution proves necessary:** amend rule + validator check to permit both. ~30 min + updated examples. The cost is not the amendment; it's the downstream complexity for executors and run-folder conventions.

### Pipeline subtype composes via body text, not frontmatter inheritance

A pipeline declares `type: playbook` (not `type: pipeline`); the subtype signal is `tags: [pipeline]` + filename + body shape. This capsule and pipeline.capsule BOTH govern pipelines.

**Rationale.** Matches pipeline.capsule v1.0's decision OD2 (pipelines extend core conceptually, not via `extends:` chain). Keeps the kernel simple. Every pipeline satisfies both capsules' rules by construction.

### No mechanical enforcement in v1.3

v1.3 shipped the active capsule as declarative. A playbook-validator that mechanically checks every playbook at vault rebuild was deferred to v1.4. Rationale: shipping the governance floor first lets the crew start codifying playbooks against a stable spec; v1.4's implementation builds against a stable target. Closed in v1.4+ Pillar 2.

---

## Known Enforcement Gaps (extracted from prior active body; tracked via `resolved_gaps:` pattern when closed)

Per the ADR-031 + pipeline.capsule pattern:

| Gap | What closes it | Target release | Owner |
|---|---|---|---|
| Legacy playbooks without `type: playbook` frontmatter remain compliant during v1.3 grace window | Next amendment to each legacy playbook must add `type: playbook`; v1.4 validator enforces at check-in; v1.3 honor-system discipline | 1.4.0 | argus |
| Legacy `status: published` is aliased to `active` during grace window | Migration pass flipping all `published → active` at v1.4 lock or as part of each playbook's next amendment | 1.4.0 | argus + vela |
| Legacy playbooks without `uid:` in frontmatter (e.g., `first-playbook.playbook.md` as of v1.3) | UID backfill at next amendment; core capsule requires UID; v1.4 validator rejects UID-less files at check-in | 1.4.0 | argus |
| Rule 1 (trigger+scope uniqueness) does not currently cover triggerless playbooks | Authors add `trigger:` at next amendment; v1.4 validator surfaces "orphan" status in audit | 1.4.0 | argus |
| Legacy pipeline instance `tropo-work-pipeline.pipeline.md` was created at `status: active` rather than `draft → active` transition | Grandfathered under grace; future pipeline authoring follows the draft-first rule; v1.4 validator exempts files whose `created:` predates 2026-04-21 | 1.4.0 | argus |
| Playbook validator not shipped — v1.3 compliance checks are honor-system | `playbook-validator.ts` — mechanical validator per checks 1–15 | 1.4.0 | argus |
| ADR-037 trigger on `trigger:` field entering run.jsonl — not shipped | ADR-037 [e8d2a19f] triggers implementation | 1.4.0 | argus |
| Duplicate-trigger detection not mechanized — Rule 1 is honor-system | Validator scan across `.tropo/playbooks/**/*.playbook.md` + vault playbooks for (trigger + scope) collisions | 1.4.0 | argus |
| Hybrid Groups-and-Steps detection not mechanized — Rule 3 is honor-system | Validator checks body sections for mutual exclusion | 1.4.0 | argus |
| The four-tier binding layer (Spec v2.2 §4) references `.tropo-studio/bindings/<slug>.binding.md` files that do not yet exist in this vault | Authoring the binding files when the first portable-playbook export ships; v1.4 or v1.5 work | indefinite | argus |

**On closure:** gaps move from this table to a `resolved_gaps:` frontmatter array with closure provenance (resolved_at, resolved_by, resolution_summary, confirmed_by), per ADR-031 `resolved_constraints:` precedent.

---

## Self-Supersession Note (extracted from prior active body)

Amendments to this capsule — including major versions — preserve UID `e7b3c509`. Downstream consumers (playbooks declaring `governed_by: e7b3c509`) remain valid without frontmatter migration. Version identifies the applicable ruleset; UID identifies the capsule itself. Same pattern as [release.capsule v1.0 → v2.0 (b19e8d43)](release.capsule.md). This note sits outside the numbered Governance Rules (which govern playbook INSTANCES, not this capsule itself) to keep governance levels separable; capsule-level governance is handled by the meta-capsule at [capsule-definition (222873b9)](../../vault/files/222873b9.md).

---

## Amendment Preamble Paragraphs (extracted from prior active body, between H1 and §Intent)

*v2.1 (2026-04-25, Argus A34) added §Studio — Shop Signage + Relations Header per Stream 3 D3.2 of v1.4. v2.0 supersedes v1.0 (2026-04-16 Tropo framework placeholder) preserving UID `e7b3c509`. See §Changelog.*

---

## Studio — Shop Signage (extracted from prior active body)

*Quick-reference section dropped from active body at v1.18.0 refactor per Mike-A55 directive 2026-05-11 — capsules are agent-read substrate; quick-reference for humans is not the load-bearing use case. Kept here as historical record of the v2.1 Stream 3 D3.2 uplift content.*

### Tools available
- `ls .tropo/playbooks/**/*.playbook.md` — scan existing live playbooks before authoring; check for `domain:` or `trigger:` collisions
- `vault/00-index.jsonl` — grep `type: playbook` to inventory the live set + their statuses
- `.tropo-studio/registries/registry.jsonl` — playbook-registry projection for sub-second lookups
- [Playbook Specification v2.2 (e6d373bc)](../../vault/files/e6d373bc.md) — full orchestration semantics
- Reference instances: [agent-activation.playbook.md](../playbooks/agent-activation.playbook.md), [apply-update.playbook.md](../playbooks/apply-update.playbook.md), [evaluate-tropo.playbook.md](../playbooks/evaluate-tropo.playbook.md)

### Pitfalls
- **Hybrid Groups + Steps** — Rule 3 / Check 8 violation; pick one shape
- **New playbook authored at `status: active`** — Check 11 violation; required starting state is `draft`
- **Missing `trigger:` field** — playbook becomes orphan from Rule 1 duplicate-pair check
- **Hardcoded vault-specific refs in executable content** — Rule 8 violation
- **Zero `[REQUIRED]` outcomes in §Outcomes** — Check 9 violation
- **Concierge-paths playbook missing `## Post-Outcome Handoff`** — Rule 9 / Check 19 violation

### Worked examples
- [agent-activation.playbook.md (99341618)](../playbooks/agent-activation.playbook.md) v2.2 — Groups model with 6 groups + milestones
- [apply-update.playbook.md](../playbooks/apply-update.playbook.md) — top-level-numbered Steps shape
- [evaluate-tropo.playbook.md](../playbooks/evaluate-tropo.playbook.md) v1.1 — single-session, peer-review verification
- [tropo-work-pipeline.pipeline.md](../playbooks/pipelines/tropo-work-pipeline.pipeline.md) — pipeline subtype reference

---

## Provenance

- Extracted: 2026-05-11
- Extracted by: argus-a55
- Extracted in cycle: v1.18.0 Stream B (Capsule Library Phase 1)
- Active capsule version at extraction: v2.4
- Active capsule version after extraction: v2.5 (non-breaking; body-only refactor per v1.18.0 Q3-locked 5-section pattern)
- Extraction-fidelity check: every Changelog row + Conscious Trade-offs subsection + Known Enforcement Gaps row + Self-Supersession Note + Studio preamble preserved in this file; nothing dropped silently. The active body retains current-state Intent + Schema + State Machine + Validation Rules + Composes-With.

---

*playbook capsule history | UID `1b834ed6` | extracted from `e7b3c509` | v1.18.0 Stream B extraction 2026-05-11*
