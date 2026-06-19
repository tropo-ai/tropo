---
uid: a3f1e7b2
name: "release-plan"
type: capsule-definition
extends: core
version: "1.5"
supersedes_version: "1.4"
v1_5_amendment_note: "v1.4 -> v1.5 amendment 2026-06-06 by Vela V59 per the member_of DISAMBIGUATE build (spec 6f5bb2cb v0.4; Mike-A100 approved 9 lock-breaks; core.capsule v1.5 Rule 9: member_of=parent, subsystem_hub=subsystem). Check 20 + the capabilities_touched field desc + the Composes-With derivation note retargeted from member_of: to subsystem_hub: for capabilities_touched -> hub resolution; the hardcoded 7-hub set softened to the dynamic hub set (from subsystem_name:; 11 at present). Status stays locked (amend-in-place per the approved lock-break). Exact edits drafted by Argus A101 (event 2013); landed by Vela V59 (release lane) as the independent member_of edit (Argus verified zero capability/release-plan stragglers; validator 55/0 before+after). Sibling release.capsule Rule 12 lands atomically with Talos f5e2d1c7.py; status-enum done->shipped split to a focused follow-up (e68503aa, Mike Call-1)."
tier: os
author: d.pm
created: 2026-04-19
modified: 2026-06-09
modified_by: argus-a105
meta_status_rollup_added: "argus-a104 2026-06-08 — new meta_status_rollup per 4acf3f2d v0.4 DERIVE (Mike-signed 7-capsule lock-break batch); additive (type had no rollup); prior modified vela-v59 2026-06-06"
status: locked
locked_by: argus-a49
locked_at: 2026-05-07
last_body_refactor: 2026-05-11
history_file: 3ef45183
enforced_enums:
  status:
    canonical: [design, specify, active, build, done, cancelled]
    aliases:
      shipped: done
meta_status_rollup:
  to-do: [design, specify]
  in-progress: [active, build]
  done: [done, cancelled, shipped]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — pedagogy-pattern reference
aligned_with:
  - e1c47a9f   # dev-pipeline + vault inbox primitive
  - fd2d9e77   # v1.8 design brief — Capability Subsystem Membership
  - e7a3b591   # v1.9.2 design brief — Self-Doc Discipline
composes_with:
  - b19e8d43   # release.capsule (atomic-triangle partner)
  - 8a4e21c5   # subsystem-hub.capsule (release_history rows derived)
  - 5a8f3b2c   # pipeline.capsule (update-subsystem-canonical-docs step)
tags: [capsule-definition, release-plan, 5-section-pedagogy, v1.19.0-stream-c-refactored]
---

# release-plan — Capsule Definition v1.4

## 1. Intent

Every Tropo-OS release is preceded by a `release-plan`. The plan is the coordination document — what's the thesis, what streams of work compose this release, what decisions block them, what specs they implement, what gates they must pass. It is the graph anchor that binds streams, tasks, decisions, and foundational specs into a single legible release narrative.

The `release-plan` is the PM layer of a release; the `release` capsule (b19e8d43) is the post-ship artifact layer. A release-plan plans; a release records what shipped. The two are 1:1 — every release-plan has exactly one corresponding release entry when shipping completes.

Before creating a release-plan: confirm the architectural basis (the spec this plan implements) is locked. A release-plan should not be authored for work with no locked architectural foundation — it has nothing to coordinate against.

Failure mode prevented: releases shipping without scoped streams, undeclared blocking decisions, or ungated ship criteria — leading to mid-cycle scope drift, missed gates, or content-substrate releases that don't propagate to subsystem hubs (the v1.9.2 self-doc discipline gap).

---

## 2. Schema

### Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `title` | string | ≤100 chars; format `"Tropo-OS v{version} — Release Plan"` |
| `description` | string | ≤120 chars; what this release delivers |
| `owner` | string | Agent coordinating the plan (typically `d.pm` or the Founder) |
| `status` | enum | `design` / `specify` / `active` / `build` / `done` / `cancelled` |
| `state` | enum | `active` / `archived` |
| `release_version` | string | Semver `^\d+\.\d+\.\d+$`; must match the corresponding release entry when one exists |
| `member_of` | UID array | Projects this plan belongs to (typically the release coordination project + pipeline stage folder) |
| `basis_spec` | UID | Primary locked architectural spec this plan implements. Must resolve to a `design-spec` at `status: locked` (multi-spec cases use the `foundation:` array). |
| `streams` | UID array | Ordered list of stream projects. Each must resolve to a `project` entry with `tags: [stream]` |

### Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `gates` | UID array | Blocking decisions — `task` entries with `tags: [decision]` that gate the release |
| `foundation` | UID array | Locked `design-spec` entries this release references (context, not scope) |
| `ship_criteria` | UID array | Tasks whose `stage: done` collectively signal "ready to ship" |
| `supersedes` / `superseded_by` | UID | Bidirectional pair for major re-planning |
| `shipped_release` | UID | The corresponding `release` entry. Required when `stage: done` |
| `target_date` | ISO date | Planned release date (best-effort, not enforced) |
| `locked_by` / `locked_at` | string / ISO datetime | Required when `stage: locked` or `stage: build` onward |
| `sub_systems` | string array | **v1.1 addition; SOFT-DEPRECATED at v1.2.** Informal subsystem names. v1.2+ release-plans use `capabilities_touched:` instead; `subsystems_touched:` is derived. v1.1 instances still REQUIRE this at `stage: specify`. |
| `arch_specs` | UID array | **v1.1 addition.** Tracking pointer for arch-spec entries authored under this release-plan. No 1:1 validation against `sub_systems:` (deferred). |
| `capabilities_touched` | UID array | **v1.2+; required under v1.2 opt-in.** TYPED list of governed primitives this release touches. Each UID must resolve to an entry whose `subsystem_hub:` includes at least one subsystem hub UID (v1.5 member_of DISAMBIGUATE — was `member_of:`). Empty `[]` legal at `stage: design`; non-empty at `stage: specify` onward. Mirrored to release.capsule at ship; derived `subsystems_touched:` computed via 1-hop graph traversal. *(v1.3 soft principle: list only substantively-amended capabilities; lifecycle marker change OR non-trivial body content change; metadata-only edits not listed.)* |
| `hub_summaries` | `{hub_uid: text}` map | **v1.3+; required under v1.3 opt-in.** Per-touched-subsystem-hub 3-5 sentence summary describing what the cycle does to that subsystem. Empty `{}` legal at `stage: design`; populated for every derived hub at `stage: locked` for cycles touching ≥ 1 subsystem (ZERO-touch may keep `{}`). Consumed by dev-pipeline step `update-subsystem-canonical-docs` at ship to write hub `release_history:` rows. Length: 50-1500 chars per entry. |
| `capsule_version` | string | **v1.1+ opt-in marker.** Values: `"1.1"` / `"1.2"` / `"1.3"`. Gates which validation checks fire. When absent, instance treated as MIGRATION-PENDING v1.0 (only Checks 1-12 fire). v1.4.4-v1.7 on v1.1; v1.8/v1.9.0/v1.9.1 on v1.2; v1.9.2+ on v1.3. |
| `relationships` | typed-edge array | Schema-v2 unified relationships for cross-cutting references |

### Body shape — 7 required sections + 2 optional, in order

1. **`## Thesis`** — One-paragraph statement of what this release delivers and why. **(v1.1+)** MUST include an explicit intent statement in the opening sentence.
2. **`## Foundation`** — Bulleted list of `foundation` specs as clickable links; the locked architectural context.
3. **`## Streams`** — One subsection per stream with owner, scope, and link to the stream project.
4. **`## Sub-Systems`** — **(v1.1+)** Subsystems this release touches; per subsystem one line + bulleted list of arch-spec UIDs (or "(arch-spec pending)"). Mirrors `sub_systems:` / `capabilities_touched:` frontmatter for human-readable display.
5. **`## Blocking Decisions`** — Enumerated gates with rationale; one subsection per `gates` entry.
6. **`## Ship Gates`** — Verification + deploy criteria mapping to `ship_criteria` tasks. **(v1.1+)** MUST include an explicit "Definition of Done" sub-paragraph stated as a discrete claim.
7. **`## Out of Scope`** — What this release explicitly does NOT include; prevents scope creep.
8. *(optional)* **`## Triage Notes`** — Record of project moves / rehoming done when the plan was drafted.
9. *(optional)* **`## Lessons / Reflections`** — Populated after `stage: done` for retrospective value.

---

## 3. State Machine

```
design → specify → build → done → archived
   ↑       ↓
   └ revision during active ─┘
            ↓
        cancelled (any stage)
```

| Stage | Meaning |
|-------|---------|
| `design` | Plan being drafted; streams being identified; not yet committed |
| `specify` | Plan committed; streams acknowledged; gates declared; work may begin |
| `build` | Release in flight; streams executing; plan is live reference |
| `done` | Release shipped; corresponding release entry exists at `stage: done` |
| `cancelled` | Release abandoned before shipping (any-stage terminal) |

**Valid transitions:**

- `design → specify` — Founder approves; streams committed
- `specify → design` — Revision needed (gate rejected, stream reshaped)
- `specify → build` — First stream enters active work
- `build → done` — Corresponding release entry reaches `stage: done`
- `any → cancelled` — Release abandoned (Founder approval required)

---

## 4. Validation Rules

### Governance Rules (9)

1. **Distinct from `release`.** A release-plan plans; a release records. They are 1:1 and linked via `shipped_release:` on the plan.
2. **Founder-gated transitions.** `design → specify` requires Founder approval. `specify → build` may be self-triggering (first work item starts). `build → done` requires the corresponding release entry at `stage: done`.
3. **Gates must be resolved before lock.** No `stage: done` until every `gates` decision-task has `stage: done` (or has been explicitly removed from the list with rationale in body).
4. **Streams must be projects.** Every UID in `streams:` resolves to a `project` entry. Tasks and specs cannot be streams.
5. **Version is immutable.** Once `release_version:` is set, it cannot change. If the target version changes, cancel the plan and create a new one.
6. **One active plan per version.** Two release-plan entries with the same `release_version:` in `state: active` is a governance violation.
7. **Stream / gate / ship_criteria edits free during `design` and `specify`.** Once `stage: build`, edits require Founder sign-off.
8. **Body immutability after `done`.** Once `stage: done`, body is read-only except §Lessons / Reflections which may be appended retrospectively.
9. **Default ownership is `d.pm`.** If `owner: d.pm`, the PM Director may update streams / gates / ship_criteria during `design` / `specify` / `build`. If `owner: <founder>`, Founder owns all edits.

### Validation Checks (ERROR-severity at check-in; version-gated as noted)

Core checks (1-12; fire on all instances):

1. `release_version:` matches semver `^\d+\.\d+\.\d+$`
2. `status:` ∈ {design, specify, active, build, done, cancelled}
3. `state:` is one of `active` / `archived`
4. `member_of:` non-empty array of valid UIDs
5. `basis_spec:` resolves to a `design-spec` at `status: locked`
6. `streams:` non-empty; every UID resolves to a `project` with `tags: [stream]`
7. `gates:` (if present) — every UID resolves to a `task` with `tags: [decision]`
8. `foundation:` (if present) — every UID resolves to a `design-spec`
9. `ship_criteria:` (if present) — every UID resolves to a `task`
10. If `stage: locked` (or later), `locked_by:` + `locked_at:` present
11. If `stage: done`, `shipped_release:` present and resolves to a release entry at `stage: done`
12. If `shipped_release:` present, its `release_version:` equals this plan's `release_version:`

v1.1 checks (gated on `capsule_version: "1.1"`; pre-v1.1 instances grandfathered):

13. Body contains all 7 required sections in declared order
14. If `sub_systems:` present, every entry is a non-empty string ≤60 chars
15. If `arch_specs:` present, every UID resolves to a `design-spec` or `arch-spec`
16. At `stage: specify` onward, `sub_systems:` is non-empty (legal-empty only at `stage: design`; skipped at `stage: cancelled`)
17. *(honor-system)* §Thesis opens with explicit intent statement as a discrete claim
18. *(honor-system)* §Ship Gates contains explicit "Definition of Done" sub-paragraph

v1.2 checks (gated on `capsule_version: "1.2"`):

19. `capabilities_touched:` non-empty at `stage: specify` onward
20. *(WARN at v1.8-v1.9; ERROR at v1.10)* Every UID in `capabilities_touched:` resolves to a ledger entry whose `subsystem_hub:` includes at least one subsystem hub UID (the dynamic hub set derived from `subsystem_name:`) [v1.5 member_of DISAMBIGUATE: was `member_of:`]

v1.3 checks (gated on `capsule_version: "1.3"`):

21. *(honor-system at v1.9.2-v1.9.x; ERROR at v1.10)* `hub_summaries:` populated for every subsystem hub UID present in the derived `subsystems_touched:` set (ZERO-touch cycles may keep `{}`)
22. Each `hub_summaries[hub_uid]` text VALUE is 50-1500 chars
23. *(honor-system)* `capabilities_touched:` follows the soft principle (lists only substantively-amended capabilities; lifecycle marker change OR non-trivial body content change; metadata-only edits not listed)

Core checks inherited: UID uniqueness, UID immutability, type immutability, owner/created/modified invariants.

The valid subsystem hub set referenced in Check 20 is the dynamic hub set derived from `subsystem_name:` (11 at present; was a hardcoded 7 pre-v1.5 member_of DISAMBIGUATE). The original 7: `8dd772a0` (tropo-governance) / `dbc1cbbf` (tropo-rendering) / `2d083137` (tropo-work) / `99ed55fd` (tropo-agents) / `76bab75f` (tropo-playbooks) / `1aba710c` (tropo-library) / `f87e33f0` (tropo-documentation).

---

## 5. Composes-With

- **[release.capsule (b19e8d43)](release.capsule.md)** — atomic-triangle partner. release-plan plans; release records. 1:1 link via `shipped_release:`. At ship, release derives `subsystems_touched:` from this plan's `capabilities_touched:` via 1-hop `subsystem_hub:` graph traversal (v1.5 member_of DISAMBIGUATE).
- **[build.capsule (b3d7e5a1)](build.capsule.md)** — upstream of the release. Atomic-triangle: `release-plan.shipped_release` ↔ `build.composes_into` ↔ `release.derived_from`.
- **[project.capsule (34e4cb0b)](project.capsule.md)** — streams are projects with `tags: [stream]`; each stream project may carry a `project-plan` coordinating its deliverables.
- **[task.capsule (3289712a)](task.capsule.md)** — gates are tasks with `tags: [decision]`; ship_criteria are tasks whose `stage: done` collectively signal ship.
- **[subsystem-hub.capsule (8a4e21c5)](subsystem-hub.capsule.md)** — release_history rows on each touched hub are derived from this plan's `capabilities_touched:` (computed `subsystems_touched:`) + `hub_summaries:` at ship via dev-pipeline step `update-subsystem-canonical-docs`.
- **[pipeline.capsule (5a8f3b2c)](pipeline.capsule.md)** — the dev-pipeline cycle executes against this capsule; step `update-subsystem-canonical-docs` consumes `hub_summaries:` at ship.
- **[design-spec.capsule](design-spec.capsule.md)** / **[arch-spec.capsule (a7f2e9c4)](arch-spec.capsule.md)** — the locked architectural foundation `basis_spec:` resolves to.
- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor for UID/owner/modified invariants; core's `status:` carries the lifecycle enum directly (the prior `stage:`-as-lifecycle convention is reconciled to `status:`).
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — this capsule's own governance.

### Tag Conventions

This capsule establishes two tag conventions on pre-existing types. Both tags are additive — they do not change the underlying type's semantics; they mark the entity for release-plan's validation surface.

| Tag | Applied to type | Purpose |
|-----|-----------------|---------|
| `stream` | `project` | Marks a project as a stream of work inside a release plan |
| `decision` | `task` | Marks a task as a blocking decision gate for a release plan |

A `project` tagged `stream` is still a project; a `task` tagged `decision` is still a task. Vault queries use `type: project, tags: contains(stream)` and `type: task, tags: contains(decision)`.

### History

Detailed v1.1 + v1.2 + v1.3 amendment-block prose at the top of the original v1.3 body, the migration policy paragraphs per version, the Known Enforcement Gaps table, the original Resolutions section (Argus A28 v1.0 review), the Argus Review Amendments section (v1.0 lock), the full §Studio — Shop Signage authoring procedure (human-facing quick-ref preserved per Mike-A55 *"capsules are agent-read, not human-read"* directive), the Relationship-to-release comparison table, the Extension-from-core and Inheritance sections, and the full changelog are preserved in the companion [release-plan.history.md (3ef45183)](release-plan.history.md) governed by `capsule-history.capsule` (5ec083a3).

---

*release-plan capsule definition | LOCKED v1.4 | history at [release-plan.history.md](release-plan.history.md) | v1.4 body refactor 2026-05-11 by Argus A56 (v1.19.0 Stream C — 5-section pedagogy pattern; agent-read-not-human-read per Mike-A55 v1.18.0 walk Q3). Prior v1.0–v1.3 locks preserved in history.*
*"The plan coordinates; the release records. Capabilities are the typed unit. Subsystems derive. Per-hub summaries authored at lock; the executor reads them at ship."*
