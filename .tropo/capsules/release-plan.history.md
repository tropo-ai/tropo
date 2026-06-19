---
uid: 3ef45183
name: "release-plan-history"
type: capsule-history
governs: a3f1e7b2
governs_path: .tropo/capsules/release-plan.capsule.md
extracted_at: 2026-05-11
extracted_by: argus-a56
extracted_in_cycle: "v1.19.0 — Convergence Phase 1"
extracted_in_release: pending-v1.19.0
schema_version: 2
governed_by: 5ec083a3   # capsule-history.capsule
extraction_scope: argo-private
member_of:
  - "8dd772a0"   # tropo-governance
tags: [capsule-history, extracted-from-release-plan-capsule, v1.19.0-stream-c]
---

# release-plan — Capsule History

*History extracted from release-plan.capsule v1.3 → v1.4 body refactor (v1.19.0 Stream C; 2026-05-11). The active capsule preserves the §Required floor + Schema + State Machine + Validation Rules + Composes-With per the 5-section pedagogy pattern. This file preserves: v1.1 + v1.2 + v1.3 amendment-block prose at the top of the original v1.3 body; migration policy paragraphs per version; Known Enforcement Gaps section; the original Resolutions section (Argus A28 v1.0 review); the Argus Review Amendments section (v1.0 lock); the full §Studio — Shop Signage human-facing quick-ref; the Relationship-to-release comparison table; the Extension-from-core and Inheritance sections; the full changelog table.*

---

## Amendment Blocks (extracted from v1.3 active body opener)

### v1.3 (2026-05-07, Argus A49; LOCKED post-Stream B4)

Lock path: single-instrument sa.cold-boot 142 PASS-WITH-FINDINGS + Round 2 fold + regression sa.cold-boot 143 REGRESSION-PASS-WITH-FINDINGS lock-eligible + Round 3 surgical sweep. v1.9.2 Stream A2 amendment per [v1.9.2 brief e7a3b591](../../vault/files/e7a3b591.md). Additive, non-breaking under `capsule_version: "1.3"` opt-in. Two changes:

- **Added required `hub_summaries: {hub_uid: text}` field** (gated on `capsule_version: "1.3"` opt-in marker) — map of subsystem hub UID → 3-5 sentence summary describing what the cycle does to that subsystem. Empty `{}` legal at `stage: design`; non-empty REQUIRED at `stage: locked` for cycles touching ≥ 1 subsystem (ZERO-touch cycles may keep `{}`). The substantive prose v1.8 + v1.9.0 + v1.9.1 manual scripts hand-wrote — now lives here for the executor to read at ship. Authoring discipline: write summaries at lock time when cycle thesis is clearest; do NOT pre-empt mid-cycle.
- **Added soft principle prose for `capabilities_touched:` semantics** — capsule body codifies "list only substantively-amended capabilities" rule with a rule-of-thumb (lifecycle marker change OR non-trivial body content change; metadata-only edits don't warrant listing). NO mechanical rule, NO validator at v1.9.2; author judgment + v1.10's structural-consistency check (carry-forward 3d7c387f §3.4) is sufficient. Per Mike-A49 walk Q5 over-engineering catch 2026-05-06: anticipating a problem we haven't had is over-engineering. v1.10+ may mechanize from real evidence if author judgment empirically fails.

**Why v1.3 over a major bump.** Both new pieces are additive and gated on `capsule_version: "1.3"` opt-in; no in-flight v1.2 plan is broken. The `hub_summaries:` field is REQUIRED at v1.3 lock specifically to give the v1.9.2 dev-pipeline step `update-subsystem-canonical-docs` (NEW per pipeline.capsule v2.4) an authored input. v1.10 Enforcement promotes the validator (Check 21 from honor-system to ERROR) per v1.10 carry-forward 3d7c387f. v1.3 stays surgical.

**Migration policy for pre-v1.3 release-plan instances** (v1.4.4–v1.7 on v1.1; v1.8/v1.9.0/v1.9.1 on v1.2). The v1.3 amendment **grandfathers pre-v1.3 instances** through the `capsule_version:` opt-in pattern v1.1 introduced. v1.0/v1.1/v1.2 instances continue on their authored schema; v1.3+ instances opt in by declaring `capsule_version: "1.3"` and enforce the full check set including new Checks 21 + 22 + 23. v1.9.2 release-plan ships at v1.3 schema (the FIRST instance — its `hub_summaries:` correctness is the schema's first verification at Stream B4 lock); prior plans complete on the schema they were authored against.

### v1.2 (2026-05-05, Argus A46; LOCKED)

v1.8 Stream A1 amendment per [v1.8 brief fd2d9e77](../../vault/files/fd2d9e77.md). Additive, non-breaking under capsule_version opt-in. Two changes:

- **Added required `capabilities_touched: [UIDs]` field** (gated on `capsule_version: "1.2"` opt-in marker) — array of UIDs referencing every governed primitive (capsule definition, action, skill, playbook, sa.* agent, KB article, library doc) this release touches. Empty `[]` at `stage: design`; non-empty at `stage: specify` onward. The TYPED counterpart to v1.1's informal `sub_systems:` strings.
- **Soft-deprecated `sub_systems:` (string array)** under v1.2 opt-in. v1.2 release-plans SHOULD declare `capabilities_touched:` instead; `subsystems_touched:` is then derived from `{cap.subsystem_hub for cap in capabilities_touched}` via 1-hop graph traversal at ship time (consumed by release.capsule v3.4). v1.1 instances continue to use `sub_systems:` strings unchanged — grandfathered through v1.2's `capsule_version` gate.

**Why v1.2 over a major bump.** The new field is additive at v1.2 and only fires under opt-in; no in-flight v1.1 plan is broken. v1.10 Enforcement promotes the validator from WARNING to ERROR (per v1.8 brief §3 + e61b49cc §13 chain) — that may warrant a v2.0 bump if the migration is breaking at that point. v1.2 stays surgical.

**Migration policy for pre-v1.2 release-plan instances** (v1.4.4 / v1.5 / v1.6 / v1.7 all on v1.1; older v1.4.0–v1.4.3 on v1.0). The v1.2 amendment grandfathers pre-v1.2 instances through the same `capsule_version:` opt-in marker pattern v1.1 introduced. v1.0 instances stay on v1.0 schema (Checks 13/16/17/18 do NOT fire). v1.1 instances stay on v1.1 schema (Checks 19/20 do NOT fire — the new v1.2 checks). v1.2+ instances opt in by declaring `capsule_version: "1.2"` and enforce the full check set. v1.8 release-plan ships at v1.2 schema; prior plans complete on the schema they were authored against.

### v1.1 (2026-05-03, Argus A43; LOCKED — single-instrument cold-boot verified 4 PASS / 1 PARTIAL)

v1.4.4 Stream C minimum amendment per [dev-pipeline + vault inbox primitive (e1c47a9f)](../../vault/files/e1c47a9f.md). Additive, non-breaking. Three changes:

- **Added optional `sub_systems:` field** — array of informal STRING names (e.g., `["library", "work", "agents"]`) declaring which subsystems this release touches. No UID-resolution validation; no formal registry (deferred to future amendment when subsystem registry lands).
- **Added optional `arch_specs:` field** — array of arch-spec UIDs authored under this release-plan. Tracking pointer only; no 1:1 sub_systems↔arch_specs validation (deferred per Mike directive 2026-05-03 until subsystem registry lands).
- **Tightened §Required Body Sections** — added §Sub-Systems section (between §Streams and §Blocking Decisions); §Thesis must include explicit intent statement; §Ship Gates must include explicit "Definition of Done" sub-paragraph.

**Out of scope (deferred):** subsystem UID registry; 1:1 validation; capsule-fire-time auto-spawn enforcement at the capsule level. The dev-pipeline executor still does best-effort auto-spawn from the strings list (documented in §Studio / Procedures), but no validator enforces correctness — author's discipline carries the integrity until registry exists.

**Migration policy for pre-v1.1 release-plan instances** (v1.4.0 / v1.4.1 / v1.4.2 / v1.4.3 + the v1.4 release-plan itself). v1.0 instances do NOT carry `sub_systems:` / `arch_specs:` frontmatter or §Sub-Systems body section. To prevent v1.1's stricter Checks 13 + 16 + 17 + 18 from breaking those in-flight plans, the v1.1 amendment grandfathers pre-v1.1 instances: v1.0-authored release-plans (those without `capsule_version: "1.1"` in frontmatter) are treated as MIGRATION-PENDING and the four new/tightened checks do NOT fire on them. v1.1+ authored release-plans (declared via `capsule_version: "1.1"` opt-in marker) enforce the full check set. v1.4.4 release-plan ships at v1.1 schema; prior in-flight plans complete on v1.0 schema. See §Known Enforcement Gaps for the path-forward when those plans reach `stage: done`.

---

## Resolutions (Argus A28 Review, 2026-04-19)

*d.pm's four open questions at v1.0, resolved at initial lock:*

### Q1 — `status` vs `stage`+`state` fragmentation

This capsule uses Schema v2 shape (`stage` + `state`), matching the already-locked release capsule (b19e8d43) and design-brief v2. core.capsule v1.1 (ee814120) still declares `status:` as the universal state field. **Resolution:** lock release-plan as drafted — the `stage + state` pattern is already in production via release. The broader core schema migration is a separate, bigger concern affecting every capsule type and belongs in its own ADR (proposed: "ADR — Core Capsule Schema v1.2 — stage/state migration"). That ADR will be filed by Argus as v0.5 or v0.6 scope work. Locking this capsule does not block on that migration; both the pattern and the convergence are already in flight.

### Q2 — Schema path

`.tropo/schema/vault-index-schema.md` is live (confirmed present). **Resolution:** update it to add release-plan to the type enum and status table. Broader finding: several existing capsule types (release, playbook-run, agent-configurator, board) are also absent from the schema's type enum — documentation drift predates this capsule. Flagging to Vela V31 as maintenance item; fixing for release-plan as part of this lock.

### Q3 — Decision-task gates marker

**Resolution:** use `tags: [decision]` (unchanged from draft). No first-class `type_tag:` field exists today. If a future refactor introduces one, amend this capsule at that time. Do not anticipate. Convention documented in §Tag Conventions of active capsule.

### Q4 — Structured `required_sections:` field

**Resolution:** defer. Required body sections remain prose conventions in §Required Body Sections of active capsule. Premature to structure this without a board renderer use case driving it. Revisit when the plan-as-graph test (rendering 4-build/2-active as the v1.2 plan structure) is built — if that renderer needs programmatic section mapping, amend at that time.

---

## Argus Review Amendments (2026-04-19, v1.0 lock)

Three changes applied during v1.0 lock review:

- **A1.** `basis_spec` constraint tightened from "design-spec, design-brief, or project" to "design-spec at status: locked". Rationale: a release plan must be grounded in locked architecture; multi-spec cases are handled by the `foundation:` array. Reflected in active capsule §2 Schema + Validation Check 5.
- **A2.** §Tag Conventions section added, explicitly declaring the `stream` (on projects) and `decision` (on tasks) tags as markers established by this capsule. Previously these tags appeared in validation rules without a definition section. Preserved in active capsule §5 Composes-With.
- **A3.** Status changed from `draft` to `locked`; `locked_by: argus-a28`, `locked_at: 2026-04-19` added to frontmatter.

---

## Known Enforcement Gaps (extracted)

| Gap | Impact | Path forward |
|-----|--------|--------------|
| **Pre-v1.1 release-plan instances** (v1.4.0 / v1.4.1 / v1.4.2 / v1.4.3 + the v1.4 release-plan) lack `sub_systems:` / `arch_specs:` / `capsule_version:` frontmatter and §Sub-Systems body section | Without grandfathering, v1.1's stricter Checks 13 + 16 + 17 + 18 would break those in-flight plans at next check-in. | Validator gates Checks 13 + 16 + 17 + 18 on `capsule_version: "1.1"` opt-in marker. Pre-v1.1 instances (no marker) treated as MIGRATION-PENDING and grandfathered through. v1.4.4 release-plan ships at v1.1 schema (declares the marker). When the long-tail v1.0 plans reach `stage: done` and archive, the grandfathering need expires naturally. No mechanical migration; plans complete on the schema they were authored against. |
| **Subsystem UID registry not yet authored** | `sub_systems:` is array of strings; no UID resolution; no formal subsystem-hub validation | Future amendment (post-v1.4.4) introduces subsystem registry; `sub_systems:` migrates from strings to UIDs; 1:1 validation added; capsule version bumps to v1.2 or v2.0. Mike-deferred 2026-05-03 to keep v1.4.4 ship tight. Status: resolved at v1.8 via the typed `capabilities_touched:` substrate. |
| **1:1 sub_systems↔arch_specs validation deferred** | A release-plan can declare 3 sub_systems but populate arch_specs with 5 UIDs (or 0); validator does not flag | Authors apply discipline — declare what you touch; populate arch_specs as work surfaces. When subsystem registry lands, 1:1 validation activates. Mike-deferred 2026-05-03. Status: superseded at v1.8 by typed capabilities_touched substrate (no longer needed). |
| **§Thesis intent statement and §Ship Gates Definition-of-Done are honor-system** | Validator cannot prose-parse; Checks 17 + 18 fire as honor-system markers | Reviewer-of-record (typically Argus) verifies at `design → specify` transition. When prose-parsing tooling exists (NLP-validator pattern), upgrade Checks 17 + 18 from honor-system to enforced. |
| **Step-2 executor idempotency on re-run** | dev-pipeline executor may re-execute step-2 against a release-plan that already has populated `arch_specs:`. Behavior: re-run should be no-op (skip already-spawned subsystems). Not currently specified in pipeline-run.capsule. | Future pipeline-run amendment can add idempotency rule (re-execution of completed step is no-op). For v1.4.4: author's discipline — don't re-run step-2 unless intentional. |

---

## Studio — Shop Signage (extracted v1.1 + v1.2 + v1.3 human-facing quick-ref)

*Preserved per Mike-A55 directive 2026-05-11: capsules are agent-read, not human-read. Active capsule §5 Composes-With teaches the type to the agent; this section preserved the workflow guide to a human author.*

### Tools available

- `python3 .tropo/scripts/tropo-validate.py` — runs release-plan's validation checks including basis_spec / streams / gates resolution
- `scripts/build-release.py` — Argo's release builder; packages the release at `stage: build → done` transition; produces manifest + zip. **Argo-only (`extraction_scope: argo-reference` per v1.5; not in user vaults).**
- `scripts/rehydrate.py` — regenerates ledger indexes after stream/gate additions
- Atomic-triangle check (forthcoming pre-commit hook v1.4) — enforces `release-plan.shipped_release` ↔ `build.composes_into` ↔ `release.derived_from` consistency at ship moment

### Skills

- `create-release-plan.skill.md` *(forthcoming v1.5)* — authors a new release plan with basis_spec grounding + streams/gates scaffolding
- `amend-release-plan.skill.md` *(forthcoming v1.5)* — scoped edits during `design` / `specify` / `build` with founder-sign enforcement at `build` boundary
- `ship-sequence.skill.md` *(extracted from V34's §A→§I pattern in v1.3.1; forthcoming v1.5)* — reproducible ship-time orchestration

### Procedures

- **Ship-sequence §A→§I script pattern** (established v1.3.1 by Vela V34) — pre-flight through surface-to-founder
- **§G.5 Founder ship-signal protocol** — Mike authorizes ship with explicit language per §5.5.3 of each release plan
- **Gate-resolution protocol** — every `gates` task reaches `stage: done` before release-plan can reach `stage: done`
- **Three-instrument verification regime** — at stream close + at ship gate
- **(v1.1) dev-pipeline integration — auto-spawn arch-specs from `sub_systems:`** (best-effort, not enforced): When dev-pipeline step-2 (spawn-arch-specs, UID e1b819c4) executes against a release-plan at `stage: specify` or later, the executor reads the release-plan's `sub_systems:` array and authors one arch-spec vault entry per declared subsystem. Each authored arch-spec's UID is appended to `arch_specs:`. The capsule does NOT validate that every sub-system has a corresponding arch-spec (1:1 enforcement deferred); the pipeline does best-effort and the author's discipline carries integrity.
- **(v1.2) Capability-tagging-at-stream-start sub-pattern.** When opening a stream, the executor identifies each governed primitive the stream will touch (capsule, action, skill, playbook, sa.* agent, KB article) and appends its UID to `capabilities_touched:`. This produces an honest, granular tally of what the release modifies — the foundation that v1.9.2's update-subsystem-canonical-docs step consumes. Stream owners SHOULD update the field as work progresses, not retrospectively at ship; the field is queryable mid-cycle for stream-status views.
- **(v1.2) Derived `subsystems_touched:` discipline.** The release-plan author NEVER types `subsystems_touched:` directly on the corresponding release.capsule v3.4 entry. At ship (B6 atomic-triangle), the substrate computes `subsystems_touched = unique({hub_uid for cap_uid in capabilities_touched for hub_uid in member_of[cap_uid] if hub_uid in {7 subsystem hubs}})` and populates the release entry. Subsystem-hub `release_history:` rows + `subsystem-registry.jsonl` rows are generated from the same query. Drift between capability membership and subsystem rollup is structurally impossible because the rollup IS the query result.
- **(v1.3) Author per-hub summaries at release-plan lock time.** When the release-plan flips to `status: locked` (Stream B4 in dev-pipeline cycles), the author writes 3-5 sentences per touched subsystem hub describing what the cycle does to that subsystem. The text becomes the `release_history:` row `summary:` field for that hub at ship time, written by update-subsystem-canonical-docs step. Discipline: write at lock when cycle thesis is clearest; do NOT pre-empt mid-cycle (summaries change as work surfaces); do NOT defer to ship (reproduces the manual-substitute pattern v1.9.2 closes).
- **(v1.3) `capabilities_touched:` substantive-amendment discipline.** When tagging a capability into the array, ask: "did this capability's lifecycle marker change (`version:` bump, `status:` flip), OR did its body content non-trivially change?" If yes, list. If only metadata changed (modified_by, formatting, prose typo), do NOT list. The discriminator is author judgment per the soft principle prose; honor-system at v1.9.2-v1.9.x; ERROR-promoted at v1.10. The discipline operates as a side-channel during normal authoring — not a session-goal sweep, not a retrospective audit. Example: a release that bumps capsule X v1.0→v1.1 and ALSO updates capsule X's modified_by because of an unrelated metadata sweep — list capsule X. A release that ONLY updates capsule Y's modified_by — do NOT list.

### Pitfalls

- Two active plans for same version → Rule 6 violation
- `basis_spec:` pointing at a draft or reviewed spec → Check 5 failure
- Editing streams during `stage: build` without founder sign-off → Rule 7 violation; ship-gate integrity at risk
- Silently dropping a gate → Rule 3 violation; gates must resolve OR be explicitly removed with rationale
- Treating release-plan as the historical artifact → release-plan plans; release records; don't conflate
- **(v1.1)** Authoring `sub_systems:` as UIDs instead of strings → at v1.1 the field is strings only; UIDs may parse but won't resolve and will need migration
- **(v1.1)** Expecting 1:1 sub_systems↔arch_specs validation at v1.1 → deferred per Mike directive 2026-05-03
- **(v1.1)** Authoring at `stage: specify` with empty `sub_systems:` → Check 16 violation
- **(v1.1)** Skipping the §Sub-Systems body section → Check 13 violation
- **(v1.2)** Declaring `capsule_version: "1.2"` but leaving `capabilities_touched: []` at `stage: specify` → Check 19 violation
- **(v1.2)** Tagging a capability whose `member_of:` lacks any subsystem hub UID → Check 20 WARNING (ERROR at v1.10)
- **(v1.2)** Tagging a capability whose `member_of:` includes MULTIPLE subsystem hub UIDs → Check 20 WARNING; PRIMARY function determines the hub
- **(v1.2)** Manually authoring `subsystems_touched:` on the release.capsule v3.4 entry → release.capsule v3.4 Rule 12 violation (derived-not-authored discipline)
- **(v1.3)** Declaring `capsule_version: "1.3"` but leaving `hub_summaries: {}` at lock when ≥ 1 subsystem hub derived → Check 21 violation
- **(v1.3)** Authoring `hub_summaries[hub_uid]` text shorter than 50 chars (placeholder shape) → Check 22 violation
- **(v1.3)** Authoring `hub_summaries[hub_uid]` text longer than 1500 chars → Check 22 violation (hub frontmatter readability)
- **(v1.3)** Listing metadata-only-touched capabilities in `capabilities_touched:` → Check 23 violation
- **(v1.3)** Pre-empting `hub_summaries:` mid-cycle (writing summaries during Stream B before lock) → low-risk pitfall; cycle thesis still surfacing
- **(v1.3)** Retrospectively patching `hub_summaries:` after ship → reproduces the manual-substitute pattern v1.9.2 closes; re-fire cycle if defect surfaces

### Worked examples

- [Tropo-OS v1.4 Release Plan (4b8e2f71)](../../vault/files/4b8e2f71.md) — 5 streams + 6 gates
- [Tropo-OS v1.3.1 Release Plan (2ac2a053)](../../vault/files/2ac2a053.md) — hotfix-class planning
- [Tropo-OS v1.3.0 Release Plan (137a7e13)](../../vault/files/137a7e13.md) — major-cycle planning
- [Tropo-OS v1.2.0 Release Plan (8c3e2d5f)](../../vault/files/8c3e2d5f.md)

### Go next

- Ship-time record → [release.capsule v2.0 (b19e8d43)](release.capsule.md) — atomic triangle partner
- Packaging output → [build.capsule v1.1 (b3d7e5a1)](build.capsule.md) — upstream of the release
- Underlying spec grounding → [arch-spec.capsule v1.0 (a7f2e9c4)](arch-spec.capsule.md) or a locked design-spec
- Stream project shape → [project.capsule v2.3 (34e4cb0b)](project.capsule.md) — streams are projects with `tags: [stream]`
- Decision gates → [task.capsule v3.0 (3289712a)](task.capsule.md) — gates are tasks with `tags: [decision]`
- Boards for tracking → [board-definition.capsule (b0d1e4f2)](board-definition.capsule.md)

---

## Relationship to `release` — Comparison Table (extracted)

The release-plan and release capsules are complementary, not redundant:

| Dimension | `release-plan` | `release` |
|-----------|----------------|-----------|
| **Verb** | coordinates | records |
| **When authored** | before and during build | at deploy |
| **Scope** | streams, gates, decisions | drops, version, date |
| **Lifecycle** | `design → specify → build → done` | `build → verify → deploy → done` |
| **Mutability** | editable through `build` | immutable after `done` |
| **Question answered** | "how do we get there?" | "what shipped?" |

A release-plan is the PM-facing artifact. A release is the public/historical artifact. Linked via `shipped_release:` on the plan and `relationships: [member-of: <release-plan-uid>]` on the release.

---

## Extension from core

*Where this capsule specializes core.capsule (ee814120).* release-plan.capsule extends core: **title allowed up to 100 chars** (no relaxation); **uses `stage:` as lifecycle enum** (design/specify/build/done/cancelled — stage-progression pattern matching typed-pipeline artifacts, distinct from core's generic `status:` naming); **adds specialized fields** (`release_version`, `basis_spec`, `streams`, `gates`, `foundation`, `ship_criteria`, `shipped_release`, `target_date`) governing release-cycle coordination. Core's `status:` field is realized here as `stage:` per typed-pipeline convention.

---

## Inheritance

Extends `core`. Inherits all core rules (UID uniqueness/immutability, type immutability, owner/created/modified invariants). Documented in active capsule §5 Composes-With.

---

## Changelog (full lineage)

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-04-19 | LOCKED. Initial version — drafted by d.pm, locked by Argus A28 with three amendments (basis_spec tightened, tag conventions section added, locked frontmatter fields added). Four open questions resolved inline. | d.pm (Pam P3) draft + argus-a28 lock |
| 1.1 | 2026-05-03 | LOCKED — v1.4.4 Stream C minimum amendment (source brief: e1c47a9f). Additive, non-breaking. Added optional `sub_systems:` field (array of informal strings; no registry validation). Added optional `arch_specs:` field (array of arch-spec UIDs; no 1:1 validation against sub_systems). Added §Sub-Systems required body section. Tightened §Thesis to require explicit intent; §Ship Gates to require explicit Definition of Done. 4 new validation checks (13 expanded + 14/15/16). New §Studio Procedures entry documenting dev-pipeline auto-spawn integration as best-effort. UID preserved at a3f1e7b2. | argus-a43 |
| 1.2 | 2026-05-05 | LOCKED — v1.8 Stream A1 amendment (source brief: fd2d9e77). Additive, non-breaking under `capsule_version: "1.2"` opt-in. Added required `capabilities_touched: [UIDs]` field — TYPED list of governed primitives this release touches; each UID MUST resolve to a ledger entry whose `member_of:` includes exactly one of the 7 subsystem hub UIDs. Soft-deprecated `sub_systems:` (string array) under v1.2 opt-in in favor of derived `subsystems_touched:` (computed by release.capsule v3.4 from this plan's `capabilities_touched:` via 1-hop graph traversal at ship). 2 new validation checks (19 + 20). New §Studio Procedures entries: capability-tagging-at-stream-start + derived-subsystems_touched discipline. UID preserved at a3f1e7b2. | argus-a46 |
| 1.3 | 2026-05-07 | LOCKED — v1.9.2 Stream A2 amendment (source brief: e7a3b591). Lock path: sa.cold-boot 142 PASS-WITH-FINDINGS (1 P0 + 7 P1 + 9 P2 + 3 P3); Round 2 fold addressed top 3 + Mike-surfaced #4; sa.cold-boot 143 regression REGRESSION-PASS-WITH-FINDINGS lock-eligible; Round 3 surgical sweep closed 5 incomplete-closure residuals. Additive, non-breaking under `capsule_version: "1.3"` opt-in. Added required `hub_summaries: {hub_uid: text}` map field — per-hub release-impact summary (3-5 sentence prose); consumed by NEW dev-pipeline step `update-subsystem-canonical-docs` at ship to write hub `release_history:` rows + subsystem-registry rows. Added soft principle prose for `capabilities_touched:` semantics — "list only substantively-amended capabilities"; NO mechanical rule, author judgment + v1.10's structural-consistency check is sufficient (per Mike-A49 walk Q5 over-engineering catch). 3 new validation checks (21 honor-system; 22 length bounds; 23 honor-system substantive-amendment). UID preserved at a3f1e7b2. | argus-a49 |
| 1.4 | 2026-05-11 | **v1.19.0 Stream C — Capsule Pedagogy Completion.** Body refactor to 5-section pedagogy pattern (Intent → Schema → State Machine → Validation Rules → Composes-With) per Mike-A55 *"capsules are agent-read, not human-read"* directive from v1.18.0 walk. Active body reduced from 377 → ~260 lines (~31% reduction; lower than v1.18.0 average because release-plan carries 23 version-gated validation checks that must remain enumerated). Extracted to this `.history.md` companion: v1.1 + v1.2 + v1.3 amendment-block prose (~50 lines of opener prose), migration policy paragraphs per version, Resolutions section (Argus A28 v1.0 review), Argus Review Amendments section (v1.0 lock), Known Enforcement Gaps table, §Studio — Shop Signage human-facing quick-ref, Relationship-to-release comparison table, Extension-from-core section, Inheritance section, full changelog. **No schema changes, no validation rule changes, no governance rule changes, no state machine changes.** Bidirectional pointer pair: active capsule frontmatter `history_file: 3ef45183` ↔ this file's `governs: a3f1e7b2`. UID `a3f1e7b2` preserved. | argus-a56 |

---

## Provenance

- **Extracted at:** 2026-05-11
- **Extracted by:** argus-a56 (during v1.19.0 Stream C — Capsule Pedagogy Completion)
- **Active capsule version at extraction:** v1.3 (377 lines)
- **Active capsule version after extraction:** v1.4 (~260 lines; ~31% reduction)
- **Extraction-fidelity check:** All historical content preserved in this companion. Active capsule retains v1.0-locked §Required floor + State Machine + 9 Governance Rules + 23 Validation Checks (the version-gating prose is preserved compactly per-check). No semantic changes; body restructure only. Note: reduction percentage is lower than v1.18.0 precedent average (52%) because release-plan carries far more enumerated validation checks that must remain in the active body for the validator to honor; the verbose prose extracted is concentrated in the amendment-block opener + the Studio quick-ref.

---

*release-plan capsule history | UID 3ef45183 | v1.19.0 Stream C extraction 2026-05-11 by Argus A56 | Bidirectional pair: governs a3f1e7b2*
