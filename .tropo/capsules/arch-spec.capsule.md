---
uid: a7f2e9c4
name: "arch-spec"
type: capsule-definition
extends: core
version: 2.1
supersedes_version: "2.0"
tier: os
author: argus
created: 2026-04-21
modified: 2026-06-09
modified_by: argus-a105
created_by: argus-a30
status: locked
locked_by: argus-a30
locked_at: 2026-04-21
enforced_enums:
  status: [draft, reviewed, locked, archived, done]
meta_status_rollup:
  in-progress: [draft, reviewed]
  done: [locked, archived, done]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
aligned_with:
  - d2e7b1f4   # Typed Pipeline Architecture design brief (historical)
  - 8b3f1d92   # Tropo Work v3 Architecture Specification (v3 amendment source)
pattern_exemplar: d0c00001   # document.capsule — arch-spec is patterned on document per v3 Decision 3; adds 5 required body sections + locked-contract discipline + `derived_from:` non-empty invariant
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# arch-spec — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Typed Pipeline Architecture + Pipelines as Playbook Subtype (d2e7b1f4)](../../vault/files/d2e7b1f4.md) |
| Aligned with | [Tropo Work v3 — Architecture Specification (8b3f1d92)](../../vault/files/8b3f1d92.md) |
| Pattern exemplar | [document.capsule (d0c00001)](document.capsule.md) |
| Extends | `core` |

*An arch-spec is a structurally-sound specification ready for Build. It formalizes thinking from one or more design-briefs into named contracts (frontmatter, body shape, validation rules, state machine) and declares what must be true for an artifact conforming to this spec. Arch-specs are the Specify-stage output of the typed pipeline — the moment work crosses from "what are we proposing" into "what are we building."*

---

## Intent

An `arch-spec` is the Specify-stage output. It's the artifact that answers "given the thinking surfaced by the briefs, what exactly does the thing look like when we build it?" The arch-spec is less narrative than a design-brief and more formal — it declares contracts, names required fields, specifies validation rules, and states the state machine for the thing being built.

A locked arch-spec is a commitment: the build following it MUST match the spec. This is where the disciplined half of the pipeline begins — upstream of Build, downstream of Design.

**Before creating an arch-spec:** has a design-brief been locked (or at least shaped enough to spec against)? Specifying without a preceding brief is legal but should be rare and documented — briefs provide the thinking that specs formalize.

---

## Scope — What Is and Isn't an Arch-Spec

A vault entry is an **arch-spec** when:

1. **Type:** `type: arch-spec` in frontmatter.
2. **Body shape:** five REQUIRED body sections present (see §Required Body Sections).

*v3 amendment (2026-04-24): the `stage: specify` frontmatter literal previously required by v1.0 is dropped in v2.0 per v3 Decision 4 (WorkItems don't carry `stage:`; pipeline-position is a property of the pipeline-run, not the work). Type is the sufficient discriminator.*

Arch-specs are NOT:
- **Design-briefs.** Briefs explore; specs formalize. A brief is allowed to be speculative; a spec is expected to be precise.
- **Capsules.** Capsule definitions (`type: capsule-definition`) live at the Specify stage too, BUT they're governed by [capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md), not this arch-spec.capsule. Capsules are self-specifying via the meta-capsule; arch-specs are the broader class of specification artifacts that DON'T have their own dedicated capsule type.
- **Project-plans.** Plans scope; specs specify. Plans say what will be shipped; specs say what the thing IS.
- **ADRs.** Decisions lock a governance choice; specs lock a structural design. Different primitives.

Arch-specs are the Specify-stage fallback: when a piece of work needs specification but doesn't fit a more specialized type (capsule, playbook, pipeline), it gets an arch-spec.

---

## Required Frontmatter (beyond core)

| Field | Type | Constraint |
|---|---|---|
| `title` | string | ≤ 120 chars. Format: `"<Thing Being Specified> — Architecture Specification"` |
| `description` | string | ≤ 200 chars. One-line summary of what this spec covers. |
| `state` | enum | `active` or `archived`. |
| `status` | enum | `draft`, `reviewed`, `locked`, `archived`. See state machine below. Required starting state: `draft`. |
| `owner` | string | Agent who authored or owns the spec. |
| `derived_from` | array of UIDs | Upstream design-briefs this spec formalizes. **MUST be non-empty — every spec derives from at least one brief.** If the spec truly has no prior brief (rare), author a minimal brief first (the "direct-commission rationale brief") and derive this spec from it. This preserves the typed-pipeline composability invariant without the edge case. Each UID must resolve to a `design-brief`. Composability pair with the brief's `composes_into:`. |
| `member_of` | array of UIDs | At least one live project (typically the project authoring this spec). Pipeline-context addition (optional): the pipeline-stage-bucket (typically `63b69c61` for `3-specify/3-active`) OR a pipeline-run-scoped stage-stub project (see v3 Exercise Run 1 pattern — [9d4c1b87](../../vault/files/9d4c1b87.md) as exemplar). v3 amendment (2026-04-24): both conventions are legal — capsule-instance lifetime vs run-scoped ephemerality determines which fits. Use pipeline-stage-bucket for specs that persist across many runs; use stage-stub for specs authored as part of a single pipeline-run. |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `composes_into` | array of UIDs | Downstream artifacts this spec composes into — typically `build` UIDs authored from this spec. Empty at creation; populated when the spec advances to build, or when an existing build attaches additional scope to this spec. Bidirectional pair with `derived_from:` on the build. |
| `supersedes` | UID | Prior arch-spec this one supersedes. |
| `superseded_by` | UID | Successor spec (bidirectional pair with `supersedes:` on successor). |
| `locked_by` | string | Who locked. Required when `status: locked`. |
| `locked_at` | ISO 8601 date | When locked. Required when `status: locked`. |
| `spec_version` | string | Semver if the spec itself iterates (e.g., v0.1 → v0.2). Distinct from the `version` field which tracks capsule versions. |
| `informs_capsules` | array of UIDs | Capsule UIDs this spec informs or constrains (e.g., a spec for a new feature may inform multiple capsule amendments). |
| `relationships` | array of typed edges | Schema v2 cross-cutting references. |

---

## Required Body Sections

Every arch-spec body MUST contain these five sections, in this order.

### 1. `## Thesis`

One paragraph stating what this spec is for. What is being specified? Why does it need a spec rather than ad-hoc construction? What's the load-bearing claim this spec makes?

### 2. `## Architecture`

The structural design. Can be diagrams, prose, or both. Names the parts, how they relate, what flows between them. Multiple subsections allowed — use them if the architecture has distinct concerns (data model, protocol, control flow, etc.).

### 3. `## Required Contracts`

The formal commitments this spec makes. Three candidate subsections — **AT LEAST ONE must be populated; multiple may be populated if the spec governs multiple surfaces**:

- **Required Frontmatter** (if the spec governs a class of artifact): table of required fields + types + constraints
- **Required Body Sections** (if the spec governs a class of artifact): ordered list of required sections
- **Required Behavior** (if the spec governs a process, interaction, or infrastructure): numbered list of behavioral rules

Not every spec governs artifact shape — some specs govern protocols, some govern infrastructure, some govern APIs. Tailor this section to the spec's subject, but name contracts explicitly in at least one subsection. Prose-only specs drift; contract-named specs survive.

### 4. `## State Machine`

If the thing being specified has states, declare them. If it doesn't (e.g., the spec describes infrastructure), state that explicitly ("this spec does not govern state — N/A"). The section header is required; the content depends on the subject.

### 5. `## Open Technical Questions`

Questions that remain unanswered within this spec. A locked spec may still have open questions — they become the scope of future specs or amendments. Transparency is the discipline; pretending all questions are resolved is not.

---

## Optional Body Sections

- `## Related Specs` — cross-references to adjacent arch-specs, capsules, or ADRs
- `## Migration Protocol` — if the spec supersedes prior patterns, documents the migration (content, dates, who does what)
- `## Examples` — worked examples demonstrating contract application
- `## Validation Mechanism` — if the spec's contracts are mechanically checkable, names the validator script or rebuild-time check
- `## Known Gaps` — honest documentation of gaps pending future work (mirrors §Known Enforcement Gaps in capsules)

---

## State Machine

```
draft → reviewed → locked → (state: archived on supersession or retirement)
 ↑________↓ (revision during draft or reviewed)
```

**Required starting state:** every new arch-spec file MUST be authored at `status: draft`.

Canonical status enum: `status:` ∈ {draft, reviewed, locked, archived, done}

| Status | Meaning |
|--------|---------|
| `draft` | Spec being authored. Sections being filled. Not yet review-ready. |
| `reviewed` | Spec has been reviewed (typically by the Specify-stage owner, independent review, or swarm). Ready for lock but not yet committed. |
| `locked` | Spec committed. Builds following it are bound to its contracts. Amendments require supersession. |
| `archived` | Historical. Spec is no longer active — either superseded or retired. |

### Valid transitions

- `draft → draft` (revision during authoring)
- `draft → reviewed` — owner or reviewer accepts the spec
- `draft → locked` — **fast-path, discouraged but legal.** Skips the `reviewed` gate. Appropriate only for trivial pattern-matched specs where independent review would be ceremony (e.g., an arch-spec mirroring a recently-locked sibling spec closely). Use sparingly; document the reason in §Open Technical Questions.
- `reviewed → draft` — revision requested
- `reviewed → locked` — spec committed; `locked_by:` and `locked_at:` set (standard path)
- `locked → archived (superseded)` — successor spec locks; bidirectional `supersedes:` pair set atomically per project-plan Rule 9 pattern
- `archived → archived` — terminal; immutable historical record

**Resolving Rule 6 with this transition list:** cold-boot 051 caught a P0 contradiction between a prior draft's Rule 6 wording and the enumerated transitions. Fast-path `draft → locked` is now explicit in both the rule (§Governance Rule 6) and this transition list — the two no longer disagree.

---

## Governance Rules

1. **Specs formalize; they don't invent.** A spec should document what the design-brief(s) it derives from proposed. Inventing structure not suggested by the briefs is a drift signal — surface it in §Open Technical Questions or back-propagate to a brief amendment.
2. **Locked specs are body-immutable except two permitted post-lock frontmatter mutations** (amended 2026-04-21 per Phase 5 swarm P0 #1). Body content, required contracts, state machine, validation checks — all frozen at lock. The **two** permitted post-lock mutations are:
 - (a) appending to the `composes_into:` frontmatter array as downstream builds derive from this spec (see Rule 5) — preserves bidirectional composability pair invariant
 - (b) appending the stage-archive UID to `member_of:` at Close-path transition (per the advance/attach/close hard rule in project.capsule v2.2 §Stage Transitions) — preserves the "every file has a live project home" invariant when the originating project archives
All other changes require supersession via `supersedes:` / `superseded_by:`.
3. **Builds MUST derive from arch-specs at `status: locked`.** A build's `derived_from:` may only reference locked specs. Draft or reviewed specs cannot be used as a build basis — the contracts haven't stabilized. If a build needs to derive from a not-yet-locked spec, the spec must be locked first (or fast-path-locked per §State Machine transitions). Silent deviation from a locked spec's contracts is likewise not permitted.
4. **`derived_from:` is required non-empty.** Every spec must derive from at least one design-brief. Direct-commissioned specs (no prior brief) are not permitted at v1.0 — if work genuinely has no brief, author a minimal rationale-brief first, then derive the spec from it. This preserves the typed-pipeline composability invariant. (Resolves cold-boot 051 P0 #2: prior draft's Rule 4 + Check 5 contradiction.)
5. **`composes_into:` bidirectional pair is set at build-authoring time, not spec-lock time.** A spec locks with empty `composes_into:` — downstream builds haven't been authored yet. When a build is authored with `derived_from: [this-spec-uid]`, this spec's `composes_into:` gets the build's UID appended. Per Rule 2, this append is the one permitted post-lock mutation.
6. **Review before lock is the default; fast-path is the exception.** A spec typically passes through `reviewed` before `locked` so an independent reviewer verifies the formalization. Direct `draft → locked` is legal (see §State Machine) but should be reserved for trivial pattern-matched specs (e.g., a sibling of a recently-reviewed sibling). Document the fast-path reason in §Open Technical Questions.
7. **`state` and `status` operate at different layers.** `status` is the workflow enum: `draft → reviewed → locked → archived`. `state` is the lifecycle-visibility flag: `active` (shown in default views) or `archived` (hidden from default views but still queryable). A spec at `status: locked` typically has `state: active`. A spec at `status: archived` (superseded or retired) has `state: archived`. They're distinct fields with distinct semantics.
8. **Change Log for amendments.** Not currently required in body (open question whether to require), but recommended. Pattern follows subsystem-hub.capsule v1.1 Change Log shape.

---

## Validation Checks (run at check-in)

In addition to core checks. Labeled **[enforced]** (checkable at vault rebuild once v1.4 validator ships) or **[honor-system]** (reader-verified in v1.3).

1. **[enforced]** `type: arch-spec`
2. **[enforced]** `status` is one of: `draft`, `reviewed`, `locked`, `archived`
4. **[enforced]** `state` is one of: `active`, `archived`
5. **[enforced]** `derived_from:` present and non-empty; every UID resolves to a `design-brief`
6. **[enforced]** `member_of:` non-empty; every UID resolves
7. **[enforced]** If `composes_into:` present, every UID resolves to a `build` (software path) OR a `document` (content path per v3 Decision 11) OR (rare) another arch-spec. Type discrimination per the work-pipeline class — software-pipeline specs compose into builds; content-pipeline specs compose into published documents
8. **[enforced]** Body contains all 5 required sections in required order
9. **[enforced]** New arch-spec files start at `status: draft` (Rule 2 from project-plan precedent — required starting state)
10. **[enforced]** If `status: locked`, `locked_by:` and `locked_at:` are present
11. **[enforced]** `supersedes:` / `superseded_by:` (if present) form bidirectional pairs; both resolve
12. **[honor-system]** §Required Contracts is concrete (not prose-only); contains at least one of: required-frontmatter table, required-body-sections list, or required-behavior numbered list. Verified at spec review; mechanical enforcement not feasible for prose-shape.

---

## Known Enforcement Gaps

| Gap | What closes it | Target release | Owner |
|---|---|---|---|
| `draft → reviewed` transition is honor-system; no mechanical gate verifies review happened | ADR-037 trigger on `status:` transitions; requires a reviewed-by attestation | v1.4.0 | argus |
| Build-to-spec conformance check (Rule 3) is honor-system; builds may deviate from their spec without automated detection | Validator that walks a build's `derived_from:` spec and checks the build's artifacts against the spec's contracts | v1.4.0 or v1.5.0 | argus |
| §Required Contracts body-shape validation is qualitative; no mechanical check that the section contains the claimed contract types | Validator that parses §Required Contracts for named subsections and structured content | v1.5.0 | argus |

---

## Relationship to Other Capsules

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.
- **[design-brief.capsule v2.1 (de5181b0)](design-brief.capsule.md)** — upstream. Specs derive from briefs via `derived_from:` ↔ brief's `composes_into:` bidirectional pair.
- **[build.capsule (forthcoming D3)](build.capsule.md)** — downstream. Builds derive from specs via `derived_from:` ↔ spec's `composes_into:`.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — specialized sibling. Capsule definitions are a specialized form of arch-spec that have their own meta-capsule. An arch-spec is the fallback type for specifications that don't fit a more specialized meta-capsule.
- **[pipeline.capsule v1.0 (e4c8a6b2)](pipeline.capsule.md)** — declares `arch-spec` as the Specify-stage artifact type via `artifact_types: {specify: arch-spec}`.
- **[project.capsule (v2.1 currently, v2.2 in v1.3 ship) (34e4cb0b)](project.capsule.md)** — specs are `member_of:` a project. The project coordinates; the spec specifies.
- **[specify-archive evergreen project (c3e4a5f6)](../../vault/files/c3e4a5f6.md)** — terminal sink for closed specs (Close path from specify-GATE).

---

## Inheritance

Extends `core`. Inherits UID immutability, type immutability, owner/created/modified invariants.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author a spec.*

**Tools available:**
- `vault/00-index.jsonl` — grep upstream briefs (required non-empty `derived_from:` per Rule 4)
- Cascade indexes at `vault/00-cascade-*.jsonl` — locate adjacent specs + ADRs in the same domain
- `vault/files/<uid>.md` writer — specs live as flat ledger entries
- Atomic-triangle validator *(forthcoming v1.4 pre-commit hook)* — enforces spec ↔ build ↔ release bidirectional pairs
- Fast-path audit — search §Open Technical Questions across locked specs for documented fast-path rationale

**Skills:**
- `author-arch-spec.skill.md` *(forthcoming v1.5)* — scaffold 5 required sections + required frontmatter; enforce non-empty `derived_from:`
- `review-arch-spec.skill.md` *(forthcoming v1.5)* — independent-review attestation; closes the `draft → reviewed` honor-system gap (ADR-037 trigger in v1.4)
- Three-instrument BATCH dispatch — sa.arch-specs (structural) + sa.cold-boot (stranger) + sa.skeptic (adversarial) on spec drafts before lock

**Procedures:**
- `member_of:` composition — every spec's `member_of:` includes (a) the originating project AND (b) the specify-stage bucket UID (typically `63b69c61` for `3-specify/3-active`). **Default for stranger usage:** project + bucket. Pipeline-run-scoped specs (specs authored as members of a single pipeline-run rather than persisting across runs) may substitute a stage-stub project for the bucket — see §Required Frontmatter for the dual-convention legitimacy. When in doubt, use the bucket; it's the broader case.
- Lock workflow — `draft → reviewed → locked` standard path; `draft → locked` fast-path is LEGAL but **reserved for specs mirroring a recently-locked sibling spec** (e.g., a second spec in a series where the pattern has already been reviewed). Document the fast-path rationale in §Open Technical Questions at lock. Don't fast-path fresh designs.
- Rationale-brief pattern — no upstream concept or brief? Author minimal rationale-brief FIRST, then derive spec (preserves Rule 4 non-empty `derived_from:` invariant)
- Supersession protocol — set bidirectional `supersedes:` / `superseded_by:` atomically at lock moment
- Body-immutability discipline — once `locked`, body frozen; only `composes_into:` append and `member_of:` (Close path) mutable
- Three-instrument verification before flipping `status: locked` — per PIN memory, never lock before Instrument 3 PASS

**Rules (at-a-glance):**
1. Specs formalize, don't invent — content traces back to the brief(s)
2. Locked specs are body-immutable except two permitted frontmatter mutations (`composes_into:` append, `member_of:` stage-archive append)
3. Builds MUST derive from specs at `status: locked` — draft/reviewed specs cannot be build bases
4. `derived_from:` required non-empty — every spec derives from at least one brief
5. `composes_into:` is set at build-authoring time, not spec-lock time (spec locks with empty `composes_into:`)
6. Review before lock is the default; fast-path is the exception and must be documented
7. `state` (active/archived) and `status` (draft/reviewed/locked/archived) are distinct layers
8. Five required body sections in strict order: Thesis → Architecture → Required Contracts → State Machine → Open Technical Questions

**Pitfalls:**
- Direct-commissioned spec without a preceding brief → Rule 4 + Check 5 violation; author rationale-brief first
- Editing body post-lock → Rule 2 violation; requires supersession
- Build deriving from a `draft` or `reviewed` spec → Rule 3 violation; contracts haven't stabilized
- Prose-only §Required Contracts without named tables or numbered lists → Check 12 honor-system failure
- Inventing structure not surfaced by the brief → drift signal; surface in §Open Technical Questions or back-propagate to brief amendment
- Skipping `reviewed` without documenting fast-path rationale in §Open Technical Questions → Rule 6 violation
- Flipping `status: locked` before three-instrument PASS → violates pinned vault memory discipline (A31 Session 2 §11 Lesson)
- Using `stage: specify` on an arch-spec instance → v3 violation (Decision 4 dropped the literal). Arch-specs are identified by `type: arch-spec` alone. Pre-v3 instances migrate per Stream C of [6e8d3f9a](../../vault/files/6e8d3f9a.md)

**Worked examples:**
- [f2e8a7b1](../../vault/files/f2e8a7b1.md) — Tropo Work v2 Arch Spec (A32, 2026-04-23; v1.4 central thesis, 635 lines, three-instrument verified)
- [e01d7867](../../vault/files/e01d7867.md) — Helm walker toy-project Specify-stage artifact; first arch-spec to pass walker 10/10 end-to-end
- [77d612ae](../../vault/files/77d612ae.md) — "Solace Day-1 Onboarding Email — Structural Specification" — locked by sa.pipeline-walker (Record 002); reference for content-authoring specs
- [fb96c1cc](../../vault/files/fb96c1cc.md) — "Meetly User Research Synthesis — Structural Specification" — locked by sa.pipeline-walker (Record 003); companion to 77d612ae for walker-class specs

**Go next:**
- Upstream → [design-brief.capsule v2.1 (de5181b0)](design-brief.capsule.md) — every spec derives from at least one brief
- Downstream → [build.capsule v1.1 (b3d7e5a1)](build.capsule.md) — builds derive from locked specs
- Specialized sibling → [capsule-definition (222873b9)](../../vault/files/222873b9.md) — capsule definitions are a specialized form of arch-spec
- Terminal sink (post-supersession) → [specify-archive (c3e4a5f6)](../../vault/files/c3e4a5f6.md)
- Pipeline position → [pipeline.capsule v2.0 (e4c8a6b2)](pipeline.capsule.md) — arch-specs at Specify stage
- Decision gates grounded in specs → [release-plan.capsule v1.0 (a3f1e7b2)](release-plan.capsule.md) — `basis_spec:` requires arch-spec at `status: locked`

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 2.0 | 2026-04-24 | **v3 amendment.** `stage: specify` frontmatter literal dropped per v3 Decision 4 (WorkItems don't carry `stage:`; pipeline-position is a property of the pipeline-run). §Scope condition 2 removed; Required Frontmatter `stage` row removed; Validation Check 2 removed. §Studio Pitfall about `stage: specify` query collision reframed as v3-violation warning. `member_of:` convention clarified: pipeline-stage-bucket OR pipeline-run-scoped stage-stub — both legal under v3 per Finding 5 resolution. `pattern_exemplar: d0c00001` declared per Decision 3 — arch-spec is patterned on document.capsule with 5-required-body-sections + locked-contract + non-empty-derived_from discipline layer. UID preserved at a7f2e9c4. | argus-a33 |
| 2.1 | 2026-04-25 | **Gate D P2 alignment fix (sa.cold-boot 082).** Validation Check 7 amended to include `document` as a valid `composes_into:` target — the content-pipeline path per [v3 Decision 11 (8b3f1d92)](../../vault/files/8b3f1d92.md) terminates at `document (status: published)`, which means content-pipeline arch-specs compose into documents (not builds). v2.0's Check 7 enumerated only `build` or arch-spec; this caused a capsule-vs-architecture-decision lag that 082 caught at the doc layer. §Studio §Procedures retains the 4-condition Rule 2a release-engineering carve-out for builds; Check 7 now mirrors the content-vs-software discrimination locked into build.capsule v2.1 Rule 8. Also: §Studio Procedures `member_of:` row clarified with explicit "default for stranger usage" (P2 polish from 081). UID preserved at a7f2e9c4. | argus-a34 |
| 1.0 | 2026-04-21 | Initial version LOCKED. D2 deliverable of v1.3 Typed Pipeline Capsule Ship v1.3 Typed Pipeline Capsule Ship project plan. Five-section body shape. Three-instrument verification: Argus build + sa.cold-boot 051 BATCH (verdict PASS-WITH-GAPS, 2 P0 + 4 P1 remediated in-session): P0 #1 `draft → locked` fast-path added to enumerated transitions (resolves Rule 6 vs transitions-list contradiction); P0 #2 `derived_from:` Rule 4 tightened to require non-empty (resolves Rule 4 vs Check 5 contradiction — direct-commissioned specs now require a prior rationale-brief); P1 Rule 2 carved out `composes_into:` appends as the permitted post-lock mutation (resolves Rule 2 vs Rule 5 locked-spec mutation paradox); P1 Rule 3 tightened to require builds derive from `status: locked` specs; P1 §Required Contracts clarified as "at least one of three subsections must be populated"; P1 Rule 7 added clarifying `state` vs `status` dual-enum semantics. Set-level swarm deferred to Phase 5. Remaining P2s (worked example, filename convention, UID-assignment guidance, supersession Migration Protocol) deferred to v1.1. | argus-a30 |

---

*arch-spec capsule definition | LOCKED v2.1 | amended 2026-04-25 by argus-a34 (Gate D P2 — Check 7 includes `document` per Decision 11; member_of stranger-default clarified); v2.0 amended 2026-04-24 by argus-a33; v1.0 lock April 21, 2026 by argus-a30 preserved in git history | UID preserved at a7f2e9c4*
*"Briefs explore. Specs formalize. Locked specs bind what builds may become — or what documents may publish." — v2.1 aligns Check 7 with v3 Decision 11; pattern_exemplar: d0c00001.*
