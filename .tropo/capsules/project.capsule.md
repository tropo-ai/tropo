---
uid: 34e4cb0b
name: "project"
type: capsule-definition
extends: core
version: 2.5
tier: os
author: tropo
created: 2026-04-10
modified: 2026-06-09
modified_by: argus-a105
meta_status_rollup_added: "argus-a104 2026-06-08 — +active→in-progress in meta_status_rollup per 4acf3f2d v0.4 DERIVE (Mike-signed 7-capsule lock-break batch); additive; prior modified argus-a80 2026-05-23"
status: locked
locked_by: argus-a32
locked_at: 2026-04-24
v2_5_amendment_lock_by: argus-a80
v2_5_amendment_lock_at: 2026-05-23
v2_5_amendment_mike_authorization: "Mike-A80 2026-05-23 verbatim 'B. let's do it right.' — explicit lock-break approval on v2.4 to land v1.14 schema split per Vela V51 Path 2 finding [fb395501] + Mike-V51 directive 'fix it now'. Resolves the v1.13.1 render-time hub-skip workaround pattern that has accumulated three documented strand cases (Packs / Registries / + 17 tracked entries; ~1056 hub-edge entries in member_of arrays vault-wide) + closes the suppression-list-growth band-aid pattern."
enforced_enums:
  status:
    canonical: [active, evergreen, done, cancelled]
    aliases: {ideate: active, build: active, specify: active, dormant: evergreen}
meta_status_rollup:
  to-do: [ideate, specify, parked]
  in-progress: [active, build, locked]
  done: [done, cancelled, superseded]
  standing: [evergreen, dormant, standing]
meta_status_rollup_note: "argus-a116 2026-06-17 (v1.72 Move 1, dev-spec 8082aad0): status is the canonical project lifecycle field {active,evergreen,done,cancelled}; ideate/build/specify alias→active (pre-pipeline residue per Mike-A116), dormant→evergreen; evergreen→standing bucket (permanent studio-structure holders). Prior (argus-a104 2026-06-08): rollup completion per the unified lifecycle knot (move 2, 9f6a1379)."
schema_version: 2
governed_by: 222873b9
aligned_with:
 - 74fd9b61 # Board Reconciliation v0.3 §5.4 (v2.1 alignment preserved)
 - f2e8a7b1 # Tropo Work v2 Architecture Specification (v2.3 alignment)
supersedes_version: "2.4"
member_of:
   # tropo-work (v1.8 Stream B1 backfill)

---

# project — Capsule Definition v2.4

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Board System Reconciliation — Unified Capsule Design (74fd9b61)](../../vault/files/74fd9b61.md) |
| Aligned with | [Tropo Work v2 — Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md) |
| Extends | `core` |

*A container node in the project graph. Projects organize work, provide navigation, and compose hierarchically through `member_of:` relationships. **Projects are static organizational containers — they do not walk pipelines, they do not carry pipeline-position.** Flow is expressed via pipeline-runs (per [pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)), which may have projects as members.*

**v2.3 (2026-04-23, Argus A32)** — v2 substrate compliance per [Tropo Work v2 Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md). **Breaking change vs v2.2:** removes the three pipeline-walk frontmatter fields (`active_pipeline:`, `position:`, `attached_to:`), the three body sections (§Scope of Activity, §Stage Transitions, §Pipeline Mobility), and six validation checks (10-15) that governed project-walks-pipeline semantics. In v2, projects are static; pipeline-runs walk. Per Mike's 2026-04-23 Edison directive: *"if we blow up something we did two days ago, why should we care if it is better? We are building an operating system."* The v2.2 pipeline-walk work shipped 2026-04-21 is explicitly deprecated. UID `34e4cb0b` preserved.

**v2.2 retained content:** board references (`status_board:`, `grooming_board:`, `sprint_board:`, `portfolio_board:`) remain — they predate the pipeline-walk work and are orthogonal. `slug:` demotion from v2.1 retained. Inheritance from core unchanged.

---

## Intent

Every unit of work belongs to a project. Projects are graph nodes — they have identity, state, lifecycle, and membership edges. A project can belong to other projects through `member_of:`, forming the composable hierarchy. The project graph is the organizational spine of the vault.

**Projects do not flow.** A project that needs to move through stages is the target of a pipeline-run, not a pipeline-walker itself. This separation (Airflow's DAG vs. DAG-Run pattern) is the load-bearing v2 insight.

**Before creating a project, ask:**
- Which projects should this belong to? A project without `member_of:` declared is a root project — intentional for top-level masters (vault-entity-owned roots), an oversight for everything else.
- Is this truly organizational, or is flow involved? If flow, author a pipeline-run that has this project as a member.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `title` | string | ≤ 120 chars. Required. |
| `description` | string | ≤ 120 chars. |
| `owner` | UID or string | The entity (preferably an entity UID post-v2) responsible for the project. String owners permitted for pre-migration entries. |
| `status` | enum | Project lifecycle. `{active, evergreen, done, cancelled}` (v1.72; see state machine below). The legacy `stage:` field is retired (pre-pipeline). |
| `state` | enum | `active` / `archived`. |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `slug` | string | URL-safe identifier. Lowercase, hyphens. Used for `projects/<slug>/` navigation folder when present. Optional since v2.1. |
| `member_of` | array of UIDs | Parent projects. **Empty legal only when `owner:` is a vault-entity** (top-level master projects); every other project must have at least one parent (D7 invariant per v2 spec). **v2.5: subsystem hub UIDs do NOT belong here** — use `subsystem_hub:` instead. Hub UIDs in `member_of:` were the source of the v1.12 backfill collapse + the v1.13.1 render workaround. Post-v2.5 migration, `member_of:` contains only true parent (non-hub) project UIDs; Validation Check 11 ERRORs on hub UIDs in this field. |
| `subsystem_hub` | array of UIDs | **NEW v2.5.** Subsystem hub UIDs this project nests under for navigation rendering. Semantically distinct from `member_of:`: `member_of:` declares organizational parentage (the project tree); `subsystem_hub:` declares subsystem-membership (which subsystem hub(s) catalog this project as a member). Both render as parent edges in the project tree; the field split eliminates the v1.12-backfill-vs-intentional-hub-parentage ambiguity that produced the v1.13.1 render workaround. Empty array (or field omission) means "no subsystem hub membership." Multiple hubs permitted when a project belongs to multiple subsystems (e.g., cross-cutting infrastructure). |
| `lifecycle` | enum | `standing` / `versioned` / `session`. See meanings below. |
| `version` | semver string | Required when `lifecycle: versioned`. Optional otherwise. |
| `capsule_version` | literal string | Optional but **load-bearing for Validation Check 9**. Value `"2.3"` signals the project was authored (or migrated) under v2.3 rules. Check 9 (v2.2 deprecated-field rejection) only fires on projects with `capsule_version: 2.3`. Pre-v2.3 projects without this field grandfather through until migration script (Stream 1 D1.3) sets it. Resolves sa.skeptic 011 P0-2 (validator self-DoS). |
| `status_board` | UID | Reference to a `type: board-definition` entry. Project's status board. Kernel `project-board` default applies when omitted. |
| `grooming_board` | UID | Reference to a `type: board-definition` entry. Grooming board. No kernel default. |
| `sprint_board` | UID | Reference to a `type: board-definition` entry. Sprint view. No kernel default. |
| `portfolio_board` | UID | Reference to a `type: board-definition` entry. Rollup/portfolio view. No kernel default. |
| `primary_collection` | UID | collection-ref for all members. |
| `tasks_collection` | UID | collection-ref for tasks only. |
| `relationships` | array of typed edges | Graph edges — `references`, `supersedes`, etc. per schema v2. |

**Lifecycle enum meanings:**

| Value | Meaning |
|---|---|
| `standing` | Evergreen. No defined end. Used for operational hubs, subsystem containers, pipeline stage buckets, standing teams. Stays at `stage: build` indefinitely; never reaches `done`. |
| `versioned` | Tracked with a `version:` field. Lifecycle tied to a release, iteration, or numbered cycle. Examples: "v1.4 Release Scope", "Q3 Campaign v1", "Sprint 42". Archives when the version ships or retires. |
| `session` | Short-lived. Scoped to one session, workshop, or ephemeral effort. Archives quickly (typically within a week). Lightweight; minimal ceremony. |

---

## Removed in v2.3 (v2.2 deprecations)

| Field / Section | v2.2 Role | v2.3 Replacement |
|---|---|---|
| `active_pipeline:` | Pointed at pipeline this project walks | **Removed.** Use pipeline-run with project as member. |
| `position:` | Current pipeline position | **Removed.** Pipeline-run carries `current_stage:` + `current_step:`. |
| `attached_to:` | Attach-path archival target | **Removed.** Pipeline-run terminates via `status: cancelled` or `status: complete` + archive; project-level attach semantics unused. |
| §Scope of Activity (body) | Monotonic-widening stage scope | **Removed.** Projects don't carry pipeline scope. |
| §Stage Transitions (body) | Advance/Attach/Close at GATE | **Removed.** Pipeline-run transitions replace this; see `pipeline-run.capsule` §State Machine. |
| §Pipeline Mobility (body) | Pipeline-switching mid-walk | **Removed.** New pipeline-run on the project = new pipeline context. |
| Validation checks 10-15 | Pipeline-walk discipline | **Removed.** |

**Migration impact:** ~3-5 projects in the current vault have `active_pipeline:` / `position:` / `attached_to:` set. Migration script (Stream 1 D1.3) strips these fields + authors companion pipeline-runs where flow was active.

---

## State Machine

```
active → done
  ↓
  cancelled (from active)
  ↓
 archived (state: archived after done or cancelled)

evergreen — permanent studio-structure holder; never reaches done (standing bucket)
```

| `status` | Meaning |
|---|---|
| `active` | Work in progress — the canonical in-progress state. Legacy `ideate` / `build` / `specify` normalize here (pre-pipeline residue). |
| `evergreen` | A permanent holder of studio structure (operational hubs, subsystem containers). Never-terminal, always current → the `standing` meta_status bucket. |
| `done` | Work complete, project closed. |
| `cancelled` | Abandoned before completion. |

**Standing projects (`lifecycle: standing`)** carry `status: evergreen` and never reach `done`. Examples: Tropo Innovation Pipeline, Vault Operations. *(v1.72: the legacy `stage: build` convention for standing projects is retired — `status: evergreen` is the canonical signal.)*

**`state: archived`** — applied after `done` or `cancelled` when the project is no longer navigable in active views.

---

## Governance Rules

1. **Top-level projects must be vault-entity-owned.** A project with `member_of: []` MUST have `owner:` chain to the vault-entity. Non-vault-entity-owned projects must declare at least one parent via `member_of:`. This enforces D7 (every work-item has a vault-entity-project home).

2. **Projects do not own their members.** Membership is declared by the member (via `member_of:`), not by the project. Never maintain a manual members list.

3. **Slug is optional and immutable when declared.** Once a project folder exists at `projects/<slug>/`, the slug cannot change without updating all navigation files. Removing the slug is permitted only if no folder exists.

4. **Archived projects are read-only.** No new tasks or members may be added to an archived project.

5. **Board references MUST resolve when declared** (per [ADR-035 (a7c4e5b2)](../../vault/files/a7c4e5b2.md) Surface 2). Absent fields fall back to the kernel default; present-but-unresolvable is a validation error.

6. **`version:` required when `lifecycle: versioned`.** Versioned projects without version strings are incomplete.

7. **Projects are static organizational containers.** They do not carry pipeline-walk metadata. Flow is expressed via pipeline-runs (per [pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)) that may have this project as a member. Authoring a project with `active_pipeline:` or similar v2.2-era fields is a validation failure in v2.3; migration script strips.

8. **(NEW v2.5)** **Subsystem hub membership uses `subsystem_hub:`, not `member_of:`.** Subsystem hubs are identified by their `subsystem_name:` frontmatter field; entries currently include `tropo-governance (8dd772a0)`, `tropo-work (2d083137)`, `tropo-agents (99ed55fd)`, `tropo-playbooks (76bab75f)`, `tropo-rendering (dbc1cbbf)`, `tropo-documentation (f87e33f0)`, `tropo-library (1aba710c)`, `tropo-link (3a207ed3)`, `tropo-test-harness (952f3aa3)`, `import-primitive (58722bdf)`, plus archived hubs. When a project nests under a subsystem hub for navigation rendering, declare via `subsystem_hub: [<hub-uid>]`. When a project has a true non-hub parent project, declare via `member_of: [<parent-uid>]`. Both fields may be populated when a project has both a true parent + subsystem hub membership. The two fields are NOT interchangeable; the v1.12 backfill collapsed them and the v1.13.1 render workaround masked the conflation for 18 months. v2.5 closes the schema ambiguity at the root + retires the workaround.

---

## Validation Checks (run at check-in)

In addition to core checks:

1. **[enforced]** If `slug:` present: lowercase, hyphens only, ≤ 50 chars.
2. **[enforced]** `status:` ∈ {active, evergreen, done, cancelled}. *(v1.72 Move 1, Mike-A116: `status` is the canonical project lifecycle field. `ideate`/`build`/`specify` normalize → `active` (pre-pipeline residue — pipelines now own the build lifecycle); `dormant` → `evergreen`. `evergreen` = a permanent studio-structure holder, never-terminal → the `standing` meta_status bucket. The legacy `stage:` field is retired — its ~71 residual carriers drop in the v1.72 backfill, e4396825 / dev-spec 8082aad0.)*
3. **[enforced]** `state:` ∈ `{active, archived}`.
4. **[enforced]** `title:` ≤ 120 chars; `description:` ≤ 120 chars; `owner:` ≤ 50 chars (UID or short string).
5. **[enforced]** If `lifecycle:` present, value ∈ `{standing, versioned, session}`.
6. **[enforced]** If `lifecycle: versioned`, `version:` is present and is valid semver.
7. **[enforced]** If `status_board:` / `grooming_board:` / `sprint_board:` / `portfolio_board:` present: UID resolves to `type: board-definition`.
8. **[enforced]** If `member_of: []`, `owner:` must resolve to a `subtype: vault` entity (top-level enforcement per Rule 1).
9. **[enforced]** None of the deprecated v2.2 fields (`active_pipeline:`, `position:`, `attached_to:`) appear in a project with `capsule_version: 2.3`. **This check fires ONLY when the `capsule_version:` field is explicitly set to `"2.3"`** — not on every project at rebuild. Rationale: existing v2.2 projects in the vault carry the deprecated fields; Check 9 firing on all of them at rebuild would DoS the validator until migration runs. With `capsule_version:` gating, pre-v2.3 projects grandfather through; Check 9 catches only newly-authored v2.3 projects that accidentally include deprecated fields. Migration script (Stream 1 D1.3) sets `capsule_version: 2.3` as it strips the deprecated fields — after migration, all projects fall under Check 9's enforcement. **sa.skeptic 011 P0-2 resolution.**

10. **(NEW v2.5) [enforced]** If `subsystem_hub:` present: each UID resolves to a vault entry with `subsystem_name:` field set (i.e., is a subsystem hub). `check_subsystem_hub_resolves`. WARN at v1.51 ship; ERROR ratchet at v1.52+ once migration is complete + new pattern is established.

11. **(NEW v2.5) [enforced]** Hub UIDs (entries with `subsystem_name:` field) MUST NOT appear in `member_of:`. Use `subsystem_hub:` instead. `check_no_hub_uids_in_member_of`. This check is the structural-enforcement gate that prevents the v1.12-style ambiguity from recurring: once v2.5 migration completes + this check ratchets to ERROR, future authoring CANNOT introduce hub UIDs into `member_of:` (the engine rejects the entry at validation). Severity: WARN during v1.51 migration window; ERROR post-migration (v1.52+). Pre-v2.5 entries that pre-date the migration grandfather via `capsule_version:` gating same as Check 9.

**Six v2.2 validation checks (10-15) removed.** Pipeline-walk discipline migrated to pipeline-run.capsule. **v2.5 reintroduces Checks 10-11** at the new semantic level (subsystem-hub schema split discipline).

---

## Relationship to Other Capsules

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.
- **[entity.capsule (1e9c3f7a)](entity.capsule.md)** — `owner:` references entity UIDs (post-v2 migration).
- **[vault.capsule (4d6e2f9a)](vault.capsule.md)** — top-level projects are vault-entity-owned.
- **[task.capsule v3.0 (3289712a)](task.capsule.md)** — tasks' `member_of:` points at projects.
- **[pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)** — pipeline-runs may have projects as members. Projects themselves do not carry pipeline-position; pipeline-runs do.
- **[board-definition.capsule (b0d1e4f2)](board-definition.capsule.md)** — `*_board:` references.

---

## Extension from core

*Where this capsule specializes the [core.capsule (ee814120)](core.capsule.md) floor.* project.capsule v2.3 extends core per capsule-inheritance convention: **`title:` allowed up to 120 chars** (core: 100; project titles often describe scope + version); **uses `status:` as the lifecycle enum** (core's generic `status:` field; project specifies the `{active, evergreen, done, cancelled}` vocabulary — v1.72 Move 1, Mike-A116). **The legacy `stage:` field is retired** (the pre-pipeline `ideate → build → done` vocabulary; pipelines now own the build lifecycle); `ideate`/`build`/`specify` alias → `active`, and the ~71 residual `stage:` carriers drop in the v1.72 backfill. These extensions are honest documentation; the typed-capsule specialization pattern is load-bearing across the capsule set.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you act.*

**Tools available:**
- `python3 .tropo/scripts/tropo-validate.py` — runs capsule checks including project.capsule v2.3's 9 checks
- `python3 .tropo/scripts/rebuild-vault.py --apply` — regenerates indexes; confirms `member_of:` graph integrity
- Migration script `scripts/migration-v2/migration-script.py` (Stream 1 D1.3) — strips v2.2 pipeline-walk fields + sets `capsule_version: 2.3`

**Skills:**
- `create-project.skill.md` *(forthcoming v1.4 Stream 2)* — authors a new project with vault-entity-ownership enforcement
- `register-file.skill.md` *(forthcoming v1.4 Stream 2)* — syncs `projects/<slug>/` filesystem with vault entries

**Procedures:**
- `start-a-project.playbook.md` — canonical onboarding path for project-creation (v1.4 Stream 2 amendment routes through ledger-native creation)
- Concierge re-routing protocol (v1.4 Stream 2 D2.6) — post-outcome-playbook-complete, concierge re-enters intent-detection

**Rules (at-a-glance):**
1. Top-level projects must be vault-entity-owned (D7 invariant via Rule 1)
2. Projects do NOT own their members — members declare via `member_of:`
3. Slug is optional; immutable when declared
4. Archived projects are read-only
5. Board references must resolve (ADR-035 Surface 2)
6. `version:` required when `lifecycle: versioned`
7. **Projects are static organizational containers** — they do NOT carry pipeline-walk metadata (v2.3 breaking change from v2.2)

**Pitfalls:**
- Authoring a project with v2.2 pipeline-walk fields (`active_pipeline:`, `position:`, `attached_to:`) → Check 9 failure IF `capsule_version: 2.3` set (grandfathers otherwise)
- Top-level project without vault-entity ownership → violates Rule 1 + D7; routes to [vault-inbox (2d5f9b04)](../../vault/files/2d5f9b04.md) instead
- Manual members list maintained on the project → violates Rule 2; membership is member-declared
- `lifecycle: versioned` without `version:` → Check 6 failure
- Expecting projects to "walk a pipeline" → that's v2.2 semantics; v2 uses pipeline-runs with projects as members

**Worked examples (ship — every fresh install has these):**
- [vault-inbox project (2d5f9b04)](../../vault/files/2d5f9b04.md) — top-level vault-entity-owned project (the D7 anchor); ships in every fresh install

**Argo development examples (argo-reference — visible in the Argo development vault, not in fresh installs):**
- v1.4 Release Scope (5d26bdba) — `lifecycle: versioned` example
- v1.4 Release Plan (4b8e2f71) — coordinating project with 5 streams as sub-projects
- Stream 1 (e7c4a9b2), Stream 2 (d9f3b8c1), Stream 3 (b4e8f2a9), Stream 4 (a5c2e9d7) — stream-class project pattern

> *The above Argo examples are deliberately argo-reference scope: they demonstrate the pattern in Tropo's own development vault, but fresh installs don't carry development-internal projects. The shipped vault-inbox example is the canonical first-install example.*

**Sub-patterns:**

- **L0 root project** *(introduced v2.4, ships from v1.6)* — a project at the L0 root of the work-substrate graph (no parent; `member_of: []`). Pure-hierarchy use case: organizes children but does no work, holds no decisions, hosts no board. Properties: `status: active` permanent (no transitions through `proposed → active → completed → archived`); no required board; no required collection; `member_of: []` (true L0); children attach via their own `member_of:` arrays. Examples that ship in every vault: [`tropo-work (b8e5f3a2)`](../../vault/files/b8e5f3a2.md) — the work-substrate L0 root introduced in v1.6. Per Mike directive 2026-05-04 (during v1.6 pair-design walk): *"I have always used the concept of a 'project' as an enhanced 'folder.'"* The L0 root project is the limit case of that mental model — projects as enhanced organizational anchors, with no work attached at the root level. Earned-the-abstraction: the existing `project` capsule type carries this sub-pattern without requiring a new lighter type.

**Go next:**
- Need to identify the project's owner? → [entity.capsule (1e9c3f7a)](entity.capsule.md) + subtypes (agent/team/vault)
- Tasks live in this project? → [task.capsule v3.0 (3289712a)](task.capsule.md)
- Need to orchestrate flow over this project? → [pipeline.capsule v2.0 (e4c8a6b2)](pipeline.capsule.md) + [pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)
- Need a status/grooming board? → [board-definition.capsule (b0d1e4f2)](board-definition.capsule.md)

---

## Migration Notes (v2.4 → v2.5 — v1.14 schema split)

**Scope:** ~1056 entries in `vault/files/` currently have subsystem hub UIDs in `member_of:` arrays (Argus A80 query 2026-05-23). Of those, **188 are hub-only-parented** (no non-hub parent; rely on v1.13.1 render workaround to render correctly at L0 OR mistakenly render at L0 when they should nest under their declared hub). The other **868 are mixed** (have non-hub parent + hub edge; work fine via the workaround but the schema ambiguity persists in their substrate).

**Migration approach (one-shot scripted; v1.51 cycle Phase B):**

1. Script: `.tropo/scripts/migrate-v14-subsystem-hub-split.py` (dry-run first; Mike-walks the diff output; then apply).
2. For each `vault/files/<uid>.md` entry with hub UIDs in `member_of:`:
   - Move hub UIDs from `member_of:` array → `subsystem_hub:` array (preserve order; preserve YAML comments)
   - If `member_of:` becomes empty AND `owner:` is not a vault-entity, log as DEFECT (Rule 1 violation; needs Mike review per entry — these are the 188 hub-only-parented strand cases)
   - Set `capsule_version: 2.5` on the migrated entry (gates Validation Checks 10-11 enforcement)
3. Renderers updated atomically: `rebuild-vault.py` + `rehydrate.py` + `generate-relations-header.py` treat `subsystem_hub:` as parent-edge for tree-rendering; v1.13.1 hub-skip workaround REMOVED (member_of: hub UIDs would now FAIL Check 11, so they shouldn't exist post-migration).
4. Suppression list at `canonical-l0-projects.yaml` `non_l0_with_hub_only_risk:` section retires entirely; canonical_l0_projects entry for `Registries (7e93ed75)` removed (Registries reorganizes back under tropo-governance via `subsystem_hub:`).
5. Vault rebuild + rendered tree-diff verification (before vs after).

**Authoring guidance going forward (v1.51+):**

- New project nesting under tropo-governance hub: `subsystem_hub: ["8dd772a0"]` (NOT `member_of: ["8dd772a0"]`)
- New project with true parent project + subsystem hub: `member_of: ["<parent-uid>"]` + `subsystem_hub: ["<hub-uid>"]`
- True L0 projects (vault-entity-owned, no parent): `member_of: []` + `subsystem_hub: []` (or omitted)
- Validation Check 11 ERRORs on hub UIDs in `member_of:` — engine rejects the entry at validation; no recurrence path

**Composes with:**
- Vela V51 Path 2 finding at [fb395501](../../vault/files/fb395501.md) (the surface that triggered the cycle)
- Mike-A80 directive 2026-05-23 verbatim "B. let's do it right" (lock-break authorization on v2.4)
- v1.51 cycle brief at [1feefe68](../../vault/files/1feefe68.md) (cycle scope)

---

## Migration Notes (v2.2 → v2.3)

Automated by migration script (Stream 1 D1.3):

1. **Strip v2.2 pipeline-walk fields** from every project entry: `active_pipeline:`, `position:`, `attached_to:`
2. **For projects where `active_pipeline:` was set**: author a companion pipeline-run entry with `pipeline:` = ex-active-pipeline UID, `members:` = [project-uid], `current_stage:` = ex-position. The pipeline-run becomes the flow-vehicle; the project becomes static.
3. **Verify `owner:` chains to vault-entity** for root projects. Non-chainable orphans route to vault-inbox (authored at Gate 3).
4. **Lifecycle enrichment**: audit every project for correct `lifecycle:` value per v2.3 meanings. Most will be `standing` (operational hubs) or `versioned` (release scopes).

Honor-system migration window: v1.4 ships the capsule amendment + script + proof-on-high-traffic-projects. v1.5 closes long tail.

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 2.5 | 2026-05-23 | **v1.14 schema split — separates `subsystem_hub:` field from `member_of:`.** Closes the v1.12-backfill-vs-intentional-hub-parentage ambiguity that produced the v1.13.1 render workaround + the suppression-list-growth band-aid pattern. Adds `subsystem_hub:` optional frontmatter field (Optional Frontmatter row 2). Adds Governance Rule 8 (subsystem hub membership uses `subsystem_hub:`, not `member_of:`). Adds Validation Checks 10-11 (`check_subsystem_hub_resolves` + `check_no_hub_uids_in_member_of`); WARN at v1.51 migration window, ERROR ratchet at v1.52+. Adds §Migration Notes (v2.4 → v2.5) section enumerating the migration approach. Lock-break authorized by Mike-A80 verbatim 'B. let's do it right' 2026-05-23 after Argus A80 + Vela V51 surfaced that surgical Option A (V51's 3-5h scope) would leave the structural failure mode intact. Composes with v1.51 cycle brief [1feefe68] + Vela V51 Path 2 finding [fb395501]. UID preserved. | argus-a80 |
| 2.4 | 2026-05-04 | **§Workshop signage addition: L0 root project sub-pattern.** Documents the limit-case use of `type: project` as a pure-hierarchy L0 organizational anchor: `status: active` permanent (no transitions); no required board / collection; `member_of: []` (true L0); children attach via their own `member_of:` arrays. Authored as Stream A.2 of v1.6 cycle (b6f1e9c4 Decision 2). Earned-the-abstraction: existing project type carries the sub-pattern without requiring a new lighter capsule. First instance: tropo-work L0 root (b8e5f3a2). **Signage-only — no schema change, no validation-check additions, no breaking behavior. UID preserved.** | argus-a44 |
| 2.3 | 2026-04-23 | **BREAKING: v2 substrate compliance.** Removes `active_pipeline:` / `position:` / `attached_to:` frontmatter + §Scope of Activity / §Stage Transitions / §Pipeline Mobility body sections + validation checks 10-15 (pipeline-walk discipline). Projects are static organizational containers; flow belongs to pipeline-runs. Clarifies `lifecycle` enum meanings. Requires `version:` when `lifecycle: versioned`. Per Mike's 2026-04-23 Edison directive reverting the v2.2 pipeline-walk work. UID preserved. Pending three-instrument verification. | argus-a32 |
| 2.2 | 2026-04-21 | Pipeline-aware project semantics per Typed Pipeline Architecture brief: `active_pipeline:` + `position:` + `attached_to:` optional frontmatter fields; §Scope of Activity + §Stage Transitions + §Pipeline Mobility body sections; 6 new validation checks. All new fields optional per no-migration directive. Three-instrument: Argus build + sa.cold-boot. UID preserved. **SUPERSEDED by v2.3.** | argus-a30 |
| 2.1 | 2026-04-20 | Board field migration per Board Reconciliation v0.3: `board:` removed; four named-field board references added; `slug:` demoted to optional. | argus-a29 |
| 2.0 | 2026-04-16 | v2 schema: projects → member_of, status → stage + state. | A24 |

---

*project capsule definition | DRAFT v2.3 | Argus A32 | 2026-04-23*
*"Projects are static. Pipelines walk. Never conflate them again."*
