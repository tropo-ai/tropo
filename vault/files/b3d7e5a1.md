---
subsystem_hub:
  - "2d083137"
uid: b3d7e5a1
name: "build"
type: capsule-definition
extends: core
version: 2.2
supersedes_version: "2.1"
tier: os
author: argus
created: 2026-04-21
modified: 2026-06-09
modified_by: argus-a105
meta_status_rollup_added: "argus-a104 2026-06-08 — new meta_status_rollup per 4acf3f2d v0.4 DERIVE (Mike-signed 7-capsule lock-break batch); additive (type had no rollup); prior modified argus-a35 2026-04-25"
created_by: argus-a30
amended_by: argus-a32
status: locked
locked_by: argus-a30
locked_at: 2026-04-21
amended_at: 2026-04-22
enforced_enums:
  status: [draft, building, tested, done, locked, archived]
meta_status_rollup:
  to-do: [draft]
  in-progress: [building, tested]
  done: [done, locked, archived]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
aligned_with:
  - d2e7b1f4   # Typed Pipeline Architecture design brief (historical)
  - 8b3f1d92   # Tropo Work v3 Architecture Specification (v3 amendment source)
pattern_exemplar: d0c00001   # document.capsule — build is patterned on document per v3 Decision 3; adds versioned-package discipline + filesystem-artifact requirement + §Test Results requirement + Rule 2a release-engineering carve-out
amendment_ref: 959a8b3d # Gate 2 resolution — v1.3.1 release plan
---

# build — Capsule Definition v1.1

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Typed Pipeline Architecture + Pipelines as Playbook Subtype (d2e7b1f4)](../../vault/files/d2e7b1f4.md) |
| Aligned with | [Tropo Work v3 — Architecture Specification (8b3f1d92)](../../vault/files/8b3f1d92.md) |
| Pattern exemplar | [document.capsule (d0c00001)](document.capsule.md) |
| Extends | `core` |

*A build is a versioned, tested package ready for Deploy. It's the Build-stage output of the typed pipeline — the bridge between a locked arch-spec and a shipped release. Each build derives from one or more arch-specs and, when it ships, composes into exactly one release.*

---

## Intent

A `build` is what Build stage produces: a versioned artifact, tested and ready for Deploy. Each build has a version (semver), a filesystem path, and a verification record. Builds are the concrete output of the architectural thinking that flowed through brief → spec → build.

In Tropo-OS today, each release of the framework (v1.0, v1.1, v1.2, etc.) has a corresponding build folder at `releases/v1.x.x/builds/tropo-os-v1.x.x/`. This capsule codifies what a build vault entry for that folder must declare — the frontmatter contract, the verification record, the traceability back to its specs.

**Before creating a build vault entry:** has the build itself been produced (the folder at `releases/v<version>/builds/`)? The vault entry records the build; it does not produce it. Build production happens via the Tropo-OS release builder (`build-release.py` in the Argo source vault; **not shipped to user vaults** — this capsule's vocabulary applies to the Argo crew building Tropo-OS releases, not to users building their own work). The vault entry follows the production.

---

## Scope — What Is a Build

A vault entry is a **build** when:

1. **Type:** `type: build` in frontmatter.
2. **Body shape:** four REQUIRED body sections present (see §Required Body Sections).
3. **Filesystem artifact:** the `build_path:` frontmatter field resolves to an actual directory on disk.

*v3 amendment (2026-04-24): the `stage: build` frontmatter literal previously required by v1.1 is dropped in v2.0 per v3 Decision 4. Type is the sufficient discriminator.*

A build vault entry is NOT:
- The build folder itself (that lives in `releases/v<version>/builds/`). The entry records the build; it is not the build.
- A release record (`type: release`). Releases are post-ship historical records; builds are pre-ship packages. Every release derives from exactly one build; every build may (or may not) ship to a release.
- A test report (`type: test-report`). Test reports are subsidiary artifacts; a build may reference one via `test_report:` frontmatter, but a test report is not itself a build.

---

## Required Frontmatter (beyond core)

| Field | Type | Constraint |
|---|---|---|
| `title` | string | ≤ 120 chars. Format: `"<Product> v<version> — Build"` (e.g., `"Tropo-OS v1.3.0 — Build"`) |
| `description` | string | ≤ 200 chars. One-line summary of what this build packages. |
| `state` | enum | `active` or `archived`. |
| `status` | enum | `draft`, `building`, `tested`, `locked`, `archived`. See state machine below. Required starting state: `draft`. |
| `owner` | string | Agent who authored/owns the build vault entry. |
| `build_version` | string | Semver format `^\d+\.\d+\.\d+(-[a-z0-9.-]+)?$` (e.g., `1.3.0`, `1.3.0-rc1`, `1.3.0-beta.2`). Immutable once set. |
| `build_path` | string | Filesystem path from vault root to the build folder (e.g., `releases/v1.3.0/builds/tropo-os-v1.3.0`). Must resolve to a directory. |
| `derived_from` | array of UIDs | Upstream spec(s) this build implements. At least one UID. Every UID resolves to a locked spec: for general builds this MUST be an `arch-spec` at `status: locked`; for **release-engineering builds** (see Rule 2a carve-out), this MAY instead be a `design-spec` at `status: locked` when that spec is the `basis_spec:` of a release-plan whose `release_version:` matches this build's `build_version:` AND whose `streams:` array overlaps this build's `member_of:`. See Rule 2a + Check 8 for the full four-condition qualifier. Composability pair with the spec's `composes_into:`. |
| `member_of` | array of UIDs | At least one live project (typically the release-planning project that coordinated this build) + the pipeline stage bucket as a UID reference (typically `a5f7a762` = `work-pipeline/4-build/3-active` bucket during authoring; or the build-archive UID `d4f5b6a7` post-ship). All entries MUST be UIDs per the UID-addressing invariant — do NOT use folder-path literals (e.g., `4-build/3-active`) even though they resolve to the same bucket. |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `composes_into` | UID (single, not array) | The `release` this build shipped as. Populated when (and only when) this build ships. At most one — a build ships at most once. Bidirectional pair with the release's `derived_from:`. |
| `test_report` | UID | Reference to a test-report vault entry for verification provenance. |
| `zip_path` | string | If a distribution zip was produced, the path (e.g., `releases/v1.3.0/dist/tropo-os-v1.3.0.zip`). |
| `manifest_path` | string | If a build manifest was produced, the path (e.g., `releases/v1.3.0/builds/tropo-os-v1.3.0/MANIFEST.md`). |
| `supersedes` | UID | Prior build this one supersedes (rare — usually builds are version-unique; used only when a build is re-cut to fix a defect before ship). |
| `superseded_by` | UID | Successor build (bidirectional pair). |
| `locked_by` | string | Who locked. Required when `status: locked`. |
| `locked_at` | ISO 8601 date | When locked. Required when `status: locked`. |
| `build_date` | ISO 8601 date | When the build was produced on disk. Informational. |
| `relationships` | array of typed edges | Schema v2 cross-cutting references. |

---

## Required Body Sections

Every build vault entry MUST contain these four sections, in this order.

### 1. `## Build Summary`

One paragraph: what does this build package? What product, what version, what's in it at the highest level. Anchored to the build_version. Accessible to a reader who has never seen this product before.

### 2. `## Spec Traceability`

List of arch-spec UIDs this build derives from + one-line description of what each spec contributed. This section mirrors `derived_from:` in prose form, with enough context that a reader can trace the spec → build relationship without querying the frontmatter.

### 3. `## Test Results`

Summary of verification performed on this build. If a `test_report:` is set, link to it; this section is the summary. At minimum name: (a) what was tested, (b) what passed, (c) what failed, (d) what was not tested. Honest negative results are discipline; silent negative results are drift.

### 4. `## Known Issues`

Defects discovered during build or test that are shipping with this build. Each entry: issue + severity + planned resolution. Shipping with known issues is legitimate; hiding known issues is not. A build with zero known issues should say so explicitly ("No known issues at lock.").

---

## Optional Body Sections

- `## Build Provenance` — how the build was produced (script, pipeline, manual steps)
- `## Migration Notes` — for upgrade from prior version, what users need to know
- `## Performance Characteristics` — benchmarks, capacity, resource requirements
- `## Security Review` — if applicable, summary of security audit / threat model updates
- `## Change Log` — bulleted diff from prior version; mirrors release-notes pattern but at build level

---

## State Machine

```
draft → building → tested → locked → (state: archived on post-ship supersession or retirement)
 ↑_______↓ (revision during draft only)
 ↓_______↓ (revision during building if build fails)
```

**Required starting state:** every new build vault entry MUST be authored at `status: draft`.

**Strict status enum:** `status:` ∈ {draft, building, tested, done, locked, archived}

| Status | Meaning |
|--------|---------|
| `draft` | Vault entry being authored; the build on disk may not yet exist. |
| `building` | Build is being produced (disk artifact authoring in progress). Vault entry references the forthcoming path. |
| `tested` | Build is on disk AND verification has run. §Test Results section populated. |
| `locked` | Build is committed — its `build_version:` + `build_path:` + test results are final. Ready for Deploy. |
| `archived` | Historical. Either shipped (with `composes_into:` pointing at the release) or retired without ship. |

### Valid transitions

- `draft → draft` (revision during authoring)
- `draft → building` — build production begins
- `building → draft` — build failed; re-plan
- `building → tested` — build on disk, tests run
- `tested → building` — re-build required (test failures indicate build-level issues)
- `tested → locked` — verification passed; build committed
- `locked → archived` — either shipped (`composes_into:` populated; archived post-ship) or retired (never shipped; archived per Deploy-stage Close)
- `locked → archived (superseded)` — rare; only if a locked-but-unshipped build is re-cut. Supersession per standard pattern.

---

## Governance Rules

1. **Build version is immutable.** Once `build_version:` is set, it cannot change. Every build has a unique version; re-cuts produce new builds (via supersession), not version-mutations.
2. **Builds must derive from locked specs.** Rule applied via Validation Check 8 — every UID in `derived_from:` must resolve to a locked spec. The general case requires an `arch-spec` at `status: locked`. Builds that reference draft or reviewed specs are a governance violation.

   **2a. Release-engineering carve-out (v1.1).** A build is a *release-engineering build* when **all four** of the following hold, evaluated at build-lock time:
   (i) the build's `build_version:` matches semver-exactly the `release_version:` of some release-plan vault entry;
   (ii) that release-plan is at `type: release-plan, stage: specify|build|done, state: active|archived` (release-plan.capsule v1.0 uses `stage:` as its lifecycle enum; release-plans do not carry a `status:` field, so "locked" vocabulary is deliberately avoided here);
   (iii) that release-plan's `basis_spec:` field points to a ledger entry of `type: design-spec` that is **locked** — defined as either `status: locked` OR (`locked_by:` and `locked_at:` both present and non-empty) — AND this build's `derived_from:` includes that basis_spec UID. (v2.2 compound-lock-signal amendment per [7a2b4f91](../../vault/files/7a2b4f91.md): design-spec capsule's canonical lock signal is the `locked_by:` + `locked_at:` pair, not a `status:` field. Pre-v2.2 strict reading of "status: locked" caused well-formed locked design-specs like [f3c7a291](../../vault/files/f3c7a291.md) to fail Rule 2a unless they carried a tactical `status: locked` retrofit. v2.2 accepts either signal — preserves design-spec capsule convention while satisfying build's lock-state semantic.);
   (iv) **project-scope overlap:** this build's `member_of:` array contains at least one UID that also appears in the release-plan's `streams:` array — confirming the build was authored under a project that composes into the release-plan, not an unrelated project that happens to share a version string.
   When all four conditions hold, the build MAY derive from that basis_spec directly without a separate arch-spec, because the release-plan's basis_spec is the architectural commitment this build implements; re-specifying at arch-spec level between release-plan authoring and build production would be authoring theater with no architectural gain. The carve-out is **class-narrow** (applies to release-engineering builds only — builds authored outside a qualifying release-plan continue to require arch-spec derivation per Rule 2); it is **not volume-narrow** — by design, every Tropo-OS release-engineering build qualifies, because this is the pattern release-engineering builds have always followed. General (non-release-engineering) builds continue to require arch-spec derivation. **Qualification is evaluated once at build-lock time;** subsequent supersession or state changes of the release-plan do not retroactively invalidate a locked build that qualified at lock time (per Rule 6b locked-builds-are-body-immutable).
3. **`composes_into:` is populated at ship time, not at build lock.** A locked build may or may not ship. When it ships, the deploy-stage owner authors the `release` entry, sets `release.derived_from: [<this-build-uid>]`, and as the atomic pair also sets `this-build.composes_into: <release-uid>`.
4. **`build_path:` must resolve.** A build vault entry that points at a non-existent directory is a governance violation — either the build disappeared or was never produced. Validator enforces.
5. **Test Results are non-negotiable.** A build may not transition to `status: locked` without §Test Results populated. Honest negative results are required; omission is a lock-blocker.
6. **Known Issues are append-only post-lock.** After `status: locked`, new known issues may be appended (e.g., issues discovered post-lock but pre-ship) but existing entries are immutable. Integrity of the historical record.

6b. **Locked builds are body-immutable except three permitted post-lock frontmatter mutations** (added 2026-04-21 per Phase 5 swarm P0 #1). The three permitted mutations:
 - (a) `composes_into:` — set at ship time when a release derives from this build (see Rule 3)
 - (b) `member_of:` — append the stage-archive UID at Close-path transition (per the advance/attach/close hard rule in project.capsule v2.2 §Stage Transitions) — preserves the "every file has a live project home" invariant when the originating project archives
 - (c) §Known Issues body section append (see Rule 6) — the one body-mutation carve-out
All other changes require supersession via `supersedes:` / `superseded_by:`.
7. **One ship per build.** A build ships at most once (one `composes_into:` entry). If a build needs to ship twice (e.g., re-release after defect fix), the second ship is a new build via supersession.

8. **Build is for versioned software packages, not content publications** (v2.1 — Gate B P0 #2 remediation, symmetric to release.capsule v3.0 Decision 11 pitfall). Content-production work-pipelines (a document going from draft to published) **skip `build` and `release` entirely** and terminate at [document.capsule (d0c00001)](document.capsule.md) at `status: published` per v3 Decision 11. The `build` capsule is shaped for versioned software packages: semver `build_version:`, filesystem `build_path:`, §Test Results section, ship-engineering protocol. A content-pipeline that reaches for `build` will get crushing friction at §Test Results (no software tests apply to a published document), `build_path:` (no folder is produced), and `build_version:` (content versions don't follow semver). The right move is not to amend `build` to handle content — it's to match the capsule to the workload. **Tropo provides primitives; users pick which fit their work** (per Decision 11). When a finding surfaces the wrong capsule for the work, fix the pipeline-authoring, not the capsule.

---

## Validation Checks (run at check-in)

Labeled **[enforced]** or **[honor-system]** per the v1.3 discipline.

1. **[enforced]** `type: build`
2. **[enforced]** `status` is one of: `draft`, `building`, `tested`, `locked`, `archived`
4. **[enforced]** `build_version:` matches semver pattern `^\d+\.\d+\.\d+(-[a-z0-9.-]+)?$`
5. **[enforced]** `build_version:` is unique across all builds (excluding superseded)
6. **[enforced]** `build_path:` is a non-empty string
7. **[enforced]** `build_path:` resolves to an existing directory on disk (when `status: tested` or `status: locked`)
8. **[enforced]** `derived_from:` non-empty; every UID resolves to a locked spec. **General case:** UID resolves to `type: arch-spec` at `status: locked`. **Release-engineering carve-out case (per Rule 2a):** evaluated mechanically at build-lock time in four steps —
    (a) read the build's `build_version:`;
    (b) find a vault entry of `type: release-plan` whose `release_version:` matches semver-exactly AND whose `stage:` ∈ {`specify`, `build`, `done`} AND whose `state:` ∈ {`active`, `archived`};
    (c) confirm that release-plan's `basis_spec:` field equals a UID in this build's `derived_from:` AND that basis_spec is `type: design-spec` AND is **locked** — defined as either `status: locked` OR (`locked_by:` and `locked_at:` both present and non-empty); (v2.2 compound-lock-signal: see Rule 2a condition (iii) note for rationale);
    (d) **project-scope overlap:** confirm this build's `member_of:` array contains at least one UID that also appears in the release-plan's `streams:` array.
   If all four (a)(b)(c)(d) hold, the carve-out applies and the UID in `derived_from:` MAY resolve to a design-spec (not an arch-spec). If any of (a)(b)(c)(d) fails, fall through to general case — arch-spec requirement. Post-lock state changes of the release-plan do not affect a build locked under the carve-out (lock-time evaluation only; per Rule 6b).
9. **[enforced]** `member_of:` non-empty; every UID resolves
10. **[enforced]** If `composes_into:` present, resolves to a `release` entry whose `derived_from:` includes this build's UID (bidirectional pair consistency)
11. **[enforced]** New build entries start at `status: draft`
12. **[enforced]** If `status: locked`, `locked_by:` and `locked_at:` present
13. **[enforced]** Body contains all 4 required sections in required order
14. **[honor-system]** §Test Results section is populated with substantive content (not just a heading) before `status: tested` or later
15. **[enforced]** `supersedes:` / `superseded_by:` (if present) form bidirectional pairs; both resolve

---

## Known Enforcement Gaps

| Gap | What closes it | Target release | Owner |
|---|---|---|---|
| `build_path:` resolution check requires filesystem access; validator needs to handle vault-root-relative paths correctly when run from different working directories | Validator documented to always resolve paths from vault root + explicit working-directory convention | v1.4.0 | argus + vela |
| §Test Results population is honor-system (Check 14); mechanical check requires parsing section content for substantive claims | Tighter validator that verifies §Test Results matches a structural template | v1.5.0 | argus |
| Rule 7 "one ship per build" is enforced by Check 10 bidirectional pair — but enforcement happens at the release entry's authoring, not at the build's lock. A locked build sits with empty `composes_into:` until ship time; if two releases both try to derive from the same build, the second's bidirectional-pair check fails. Honest surface. | No change needed; documenting existing behavior | — | — |
| (v2.2 implementer note per sa.cold-boot 093 F2) Rule 2a (iii) + Check 8 (c) compound-lock-signal accepts the design-spec's `locked_by:` + `locked_at:` pair when "both present and non-empty." For validator implementations: "non-empty" excludes `null`, empty string `""`, and whitespace-only values. The condition treats these as absent (left disjunct fails) — fall through to general-case arch-spec requirement. Future validator authoring should use a "truthy non-whitespace string" check, not just key-presence. | Validator implementation in `vault:validate` or build-release.py (Phase E); no immediate spec change needed | v1.4.0 / Phase E | argus + talos |

---

## Relationship to Other Capsules

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.
- **[arch-spec.capsule v1.0 (a7f2e9c4)](arch-spec.capsule.md)** — upstream. Builds derive from specs via `derived_from:` ↔ spec's `composes_into:`.
- **[release.capsule (forthcoming D4)](release.capsule.md)** — downstream (ship). Releases derive from builds via `derived_from:` ↔ build's `composes_into:`.
- **[release-plan.capsule v1.0 (a3f1e7b2)](release-plan.capsule.md)** — coordination precedent. A release plan may name a build as a shipment target; when the build ships, the release entry satisfies the plan.
- **[pipeline.capsule v1.0 (e4c8a6b2)](pipeline.capsule.md)** — declares `build` as the Build-stage artifact type via `artifact_types: {build: build}`.
- **[build-archive evergreen project (d4f5b6a7)](../../vault/files/d4f5b6a7.md)** — terminal sink for closed builds that didn't ship (Close path at build-GATE).
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — this capsule's governance.

---

## Inheritance

Extends `core`. Inherits UID immutability, type immutability, owner/created/modified invariants.

---

## Extension from core

*Where this capsule specializes [core.capsule (ee814120)](core.capsule.md).* build.capsule extends core: **`title:` allowed up to 120 chars** (core: 100; build titles carry version strings); **`description:` up to 200 chars** (core: 120; build descriptions narrate packaging scope); **`status:` as workflow state** (`draft → building → tested → locked → archived`); **`state:` as archive-visibility** (`active/archived`). **v3 amendment (v2.0):** the `stage: build` pipeline-position literal previously required by v1.1 has been dropped per v3 Decision 4 — builds are identified by `type: build` alone; pipeline-position is a property of the pipeline-run, not the work. Rule 2a release-engineering carve-out (v1.1 amendment, retained under v3) permits `basis_spec:` from release-plan as substitute for `derived_from:` arch-spec under four mechanical conditions.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you act.*

**Tools available:**
- `scripts/build-release.py` — Argo's release builder; packages a Tropo-OS release; runs skeleton-manifest generation + kernel-stamp + integrity checks; authored at v1.3 foundation. **Not shipped to user vaults** (`extraction_scope: argo-reference` per v1.5). Listed here as part of the Argo release-pipeline contract; user vaults will not have this script in their `.tropo/scripts/` directory.
- `scripts/rehydrate.py` — regenerates ledger indexes post-build
- `python3 .tropo/scripts/tropo-validate.py` — runs build's 16 validation checks including the Rule 2a four-condition qualifier (Check 8)
- `.tropo-studio-skeleton/` template directory — canonical skeleton structure shipped in build; updated per v1.4 Stream 2

**Skills:**
- `author-build.skill.md` *(forthcoming v1.5)* — authors build entry with `derived_from:` + `composes_into:` + §Test Results atomically
- `skeleton-manifest.skill.md` *(forthcoming v1.5)* — generates build manifest from SKELETON_DIRS + skeleton_governance tuples in `build-release.py`
- Migration script (v1.4 Stream 1 D1.3) — carries v1.3 build-entry patterns forward to v2-schema

**Procedures:**
- Three-instrument verification before lock (sa.arch-specs + sa.skeptic + sa.cold-boot BATCH)
- Ship-sequence script §A→§I — Vela-established v1.3.1 pattern; includes §B.4 post-rebuild drift grep
- Pipeline-walker integration — pipeline-walker test harness validates build artifacts against typed-pipeline invariants (pre-ship gate)
- Release Test Harness (RTH) dispatch — Record 003 pattern per v1.3.1 precedent; T-01 PASS required

**Rules (at-a-glance):**
1. Builds MUST derive from specs at `status: locked`
2. **Rule 2a release-engineering carve-out** — if `build_version:` matches a release-plan's `release_version:`, `derived_from:` may be the release-plan's `basis_spec:` (a locked `design-spec`) in lieu of a separate arch-spec — four-condition mechanical qualifier per Check 8 (Gate 2 resolution, v1.3.1)
3. `composes_into:` is single-element (one release per build)
4. Build version is immutable once set
5. §Test Results populated before `status: locked`
6. Body immutable after lock except two permitted mutations
7. One release per build (Rule 7)
8. **Build is for versioned software packages, not content publications** (v2.1) — content pipelines skip `build` and `release`, terminate at [document (status: published)](document.capsule.md) per Decision 11

**Pitfalls:**
- Authoring a build without locked upstream spec → Rule 1 failure (unless Rule 2a carve-out applies)
- Two release entries both deriving from the same build → Rule 7 violation; bidirectional-pair check catches second attempt
- Editing body after lock → Rule 6 violation
- Rule 2a without passing all four conditions → governance bypass attempt; validator catches
- Build-spec drift (build deviates from spec's contracts) → Rule 3 violation; honor-system until v1.4+ validator
- Version mismatch between build and release → Check 10 failure at release authoring
- **Using `build` for content publications** → wrong capsule for content-vs-software work (Rule 8 / v2.1). Content pipelines skip `build` entirely and terminate at [document (status: published)](document.capsule.md). The capsule is shaped for versioned software packages (semver, build_path, §Test Results); content publications get crushing at §Test Results. Fix the pipeline, not the capsule (Decision 11 principle). Caught by sa.cold-boot 080 in stranger-authoring of "Documenting the vault-rebuild script — operator how-to" — Step 4 alone scored 5/5 ceremony-load.

**Worked examples:**
- [v1.3.1 Build (dc9826d9)](../../vault/files/dc9826d9.md) — current live build; v1.1-era with Rule 2a carve-out applied; `derived_from: [f3c7a291]` (Tropo-OS Stack design-spec)
- [v1.3.0 Build (3bc9319f)](../../vault/files/3bc9319f.md) — first Rule 2a carve-out applicant (surfaced the v1.1 amendment need)
- [v1.2.1 Build](#) — v1.0-era
- Release-engineering builds vs general builds: Rule 2a applies only to release-engineering builds; general builds must derive from arch-specs (Rule 1)

**Go next:**
- Downstream ship → [release.capsule v2.0 (b19e8d43)](release.capsule.md) — release records what shipped
- Upstream plan → [release-plan.capsule v1.0 (a3f1e7b2)](release-plan.capsule.md) — for release-engineering builds, the plan provides `basis_spec:`
- Upstream spec (general builds) → [arch-spec.capsule v1.0 (a7f2e9c4)](arch-spec.capsule.md)
- Pipeline position context → [pipeline.capsule v2.0 (e4c8a6b2)](pipeline.capsule.md) declares build as build-stage output
- Test scenarios + results → *(test-scenario.capsule / test-run.capsule Studio uplifts forthcoming later in Stream 3 D3.2)*

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 2.0 | 2026-04-24 | **v3 amendment.** `stage: build` frontmatter literal dropped per v3 Decision 4. §Scope condition 2 removed; Required Frontmatter `stage` row removed; Validation Check 2 removed. Extension-from-core paragraph rewritten — builds no longer use `stage:` as pipeline-position; `status:` is the workflow state, `state:` is archive-visibility. Rule 2a release-engineering carve-out (v1.1) retained under v3. `pattern_exemplar: d0c00001` declared per Decision 3 — build is patterned on document.capsule with versioned-package + filesystem-artifact + §Test Results discipline layer. UID preserved at b3d7e5a1. | argus-a33 |
| 1.0 | 2026-04-21 | Initial version LOCKED. D3 deliverable of v1.3 Typed Pipeline Capsule Ship v1.3 Typed Pipeline Capsule Ship project plan. Codifies existing convention for release-folder build artifacts. Four-section body shape. `composes_into:` intentionally single (not array) per Rule 7 — cold-boot 052 verified this elegantly falls out of one-build-one-ship. Three-instrument verification: Argus build + sa.cold-boot 052 BATCH (verdict PASS-WITH-GAPS, ship recommended). One P1 remediated in-session: `member_of:` example updated from path-literal (`4-build/3-active`) to UID reference (`a5f7a762`) to preserve the UID-addressing invariant. Set-level swarm deferred to Phase 5. | argus-a30 |
| 1.1 | 2026-04-22 | **Additive amendment — Rule 2a release-engineering carve-out.** UID preserved (`b3d7e5a1`); `status: locked` retained; no prior rule relaxed for general builds. Adds Rule 2a + amends Required Frontmatter `derived_from:` description + amends Validation Check 8 to declare the carve-out's mechanical qualifier. Surfaced by sa.arch-specs conformance check during v1.3.0 Session 7 testing pass: v1.3 release-engineering build [3bc9319f](../../vault/files/3bc9319f.md) derived from [f3c7a291](../../vault/files/f3c7a291.md) (Tropo-OS Stack Architecture v1.0, `type: design-spec`, not arch-spec) and failed Check 8 under v1.0. Options were: (a) author a v1.3 arch-spec solely to satisfy the rule (documentation-theater; no architectural re-specification between release-plan and build was warranted); (b) amend build.capsule to recognize that release-engineering builds' architectural commitment is the release-plan's `basis_spec:` (a locked design-spec). Path (b) chosen — Gate 2 resolution per [v1.3.1 release plan (2ac2a053)](../../vault/files/2ac2a053.md) task [959a8b3d](../../vault/files/959a8b3d.md). Mike approved 2026-04-22. **Three-instrument verification (executed at v1.3.1 Stream 3 close):** Instrument 1 = Argus build; Instrument 2 = sa.skeptic 008 adversarial + sa.arch-specs 011 cross-capsule conformance (two reviewers composing the independent-review instrument per the Session 4 convergence-by-disagreement pattern); Instrument 3 = sa.cold-boot 066 stranger test. **Reviewer findings and remediations:** sa.arch-specs 011 returned FAIL with 3 P0s on the initial v1.1 draft — (1) "locked release-plan" vocabulary collision (release-plan.capsule v1.0 uses `stage:` not `status:`), (2) "lists this build in its shipment path" references a non-existent release-plan field, (3) stateless-reader Principle 3.6 violation because the qualifier wasn't mechanically detectable as worded. sa.skeptic 008 converged on two of the three P0s ("shipment path" + "or its successor" ambiguity) plus flagged "narrow" as empirically-false scoping. All P0s remediated in a second v1.1 pass before close: Rule 2a and Check 8 rewritten as a four-condition / four-step mechanical qualifier; "or its successor" removed; "narrow" reframed as class-narrow not volume-narrow; time-variance clause added (qualification evaluated once at build-lock); arch-specs' recommended project-scope-overlap defense adopted as condition (iv) / Check 8 step (d) — build's `member_of:` must overlap release-plan's `streams:` — closes Q9 version-collision attack surface. sa.cold-boot 066 returned PASS on stranger-executability of the initial v1.1 and its polish recommendations were folded into the remediation pass. Unblocks v1.3.1 Stream 4 D4.5 build-entry authoring. | argus-a32 |
| 2.2 | 2026-04-25 | **Compound-lock-signal amendment (Rule 2a condition (iii) + Check 8 step (c)) — closes [7a2b4f91](../../vault/files/7a2b4f91.md).** Path A from the task spec: amend build.capsule to recognize design-spec's canonical lock signal (`locked_by:` + `locked_at:` pair) alongside the existing `status: locked` signal. Pre-v2.2 strict reading required tactical `status: locked` retrofit on design-specs (per A32's f3c7a291 emergency edit during v1.3.1 Stream 4 D4.5). v2.2 accepts either signal: `status: locked` OR (`locked_by:` + `locked_at:` both present and non-empty). Preserves design-spec capsule convention; eliminates retrofit pressure on future design-specs serving as basis_spec; build.capsule's lock-state semantic remains complete. UID `b3d7e5a1` preserved. **Single-instrument verification (sa.cold-boot 093) PASS-WITH-FINDINGS** — verdict LOCK-WITH-FOLLOW-UPS; 0 P0 / 0 P1 / 2 P2. **F2 folded into this lock pre-commit** (one-line implementer note in §Known Enforcement Gaps clarifying "non-empty" excludes null/empty-string/whitespace-only values for future validator implementations). **F1 acknowledged-as-polish-deferred** — sa.cold-boot's own framing notes Check 8 (c)'s clean restatement provides cross-reference redundancy that covers the risk; Rule 2a (iii) parenthetical lift can be future polish. All 4 branch-state walk cases (status:locked / pair / partial pair / both signals) evaluate per task spec. | argus-a35 |
| 2.1 | 2026-04-25 | **Gate B P0 #2 remediation (sa.cold-boot 080 lens).** Added Rule 8 — *Build is for versioned software packages, not content publications* — symmetric to release.capsule's Decision 11 pitfall. Content-production work-pipelines skip `build` and `release` entirely and terminate at `document (status: published)` per v3 Decision 11. The capsule was previously shaped only for versioned software (semver `build_version:`, filesystem `build_path:`, software-style §Test Results); a stranger authoring a content how-to via `build` got crushing friction at Step 4 (5/5 ceremony-load score in sa.cold-boot 080's walk on "Documenting the vault-rebuild script"). Polish closed the release-end of the content-vs-software asymmetry at v3.0; v2.1 closes the build-end. New Pitfalls + Studio §Rules-at-a-glance entry added. UID preserved at b3d7e5a1. | argus-a34 |

---

*build capsule definition | LOCKED v2.2 | amended 2026-04-25 by argus-a35 (compound-lock-signal — Rule 2a condition (iii) + Check 8 step (c) accept design-spec's `locked_by:`+`locked_at:` pair); amended 2026-04-25 by argus-a34 (v2.1 — Rule 8 content-vs-software); amended 2026-04-24 by argus-a33 (v2.0 — v3 amendment); v1.1 lock April 22 2026 by argus-a32 (Rule 2a carve-out); v1.0 lock April 21 2026 by argus-a30 preserved in git history | UID preserved at b3d7e5a1*
*"Briefs explore. Specs formalize. Builds package. Releases record. Content publishes." — v3 drops `stage: build` literal per Decision 4; v2.1 adds Rule 8 content-vs-software discrimination per Decision 11; v2.2 accepts compound lock signal on design-spec basis_specs per [7a2b4f91](../../vault/files/7a2b4f91.md); pattern_exemplar: d0c00001; Rule 2a release-engineering carve-out retained.*
