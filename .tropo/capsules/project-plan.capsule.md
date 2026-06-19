---
subsystem_hub:
  - "2d083137"
uid: f7b9c4a2
name: "project-plan"
type: capsule-definition
extends: core
version: "1.4"
supersedes_version: "1.3"
tier: os
author: argus
created: 2026-04-21
modified: 2026-06-09
modified_by: argus-a105
meta_status_rollup_added: "argus-a104 2026-06-08 — new meta_status_rollup per 4acf3f2d v0.4 DERIVE (Mike-signed 7-capsule lock-break batch); additive (type had no rollup); prior modified argus-a67 2026-05-16"
created_by: argus-a30
status: active
last_locked_at: 2026-05-03
last_locked_by: argus-a43
last_body_refactor: 2026-05-16
v1_4_anchor: "Argus A67 amendment per v1.35.0 design spec d2f8c194 (LOCKED Mike-A67 2026-05-16 Q25α). Extends `derived_from:` to accept pipeline-template UIDs alongside design-brief UIDs for cascade-generated project-plans. Backward-compatible: existing brief-derived plans unaffected; type-discrimination at resolution-time (target capsule type determines validation path). Required by v1.35.0 cascade capability where `pipeline-activate.py` generates a project-plan as part of pipeline activation per pipeline.capsule v2.6 `cascade_spec.generates_project_plan: true`. Status flipped locked→active for v1.4 amendment activation; re-locks at v1.36.0 if stable."
history_file: c4790782
enforced_enums:
  status: [draft, locked, done, archived]
meta_status_rollup:
  to-do: [draft]
  in-progress: [locked]
  done: [done, archived]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — pedagogy-pattern reference
aligned_with:
  - a3f1e7b2   # release-plan.capsule (sibling at release scope)
  - e1c47a9f   # dev-pipeline + vault inbox primitive
composes_with: 34e4cb0b   # project.capsule — every plan scopes exactly one project
tags: [capsule-definition, project-plan, 5-section-pedagogy, v1.19.0-stream-c-refactored]
---

# project-plan — Capsule Definition v1.3

## 1. Intent

Every non-trivial Tropo project SHOULD begin with a `project-plan`. The plan is the scoping artifact — what this project will deliver, the acceptance criteria per deliverable, the dependencies blocking them, the verification approach, and the rough phasing. The plan is the graph anchor between the design briefs that informed the project (upstream) and the typed artifacts the project will produce at each pipeline stage (downstream).

The `project-plan` sits one level below `release-plan` in scope: a release-plan coordinates a whole release; a project-plan coordinates a single project's contribution to that release. A release-plan typically composes many project-plans.

Before authoring, confirm the design brief(s) this project derives from are filed. A project-plan should not be authored for work with no preceding design thinking — it has nothing to scope against. Small one-deliverable projects (~4 hours) may proceed without a plan per Governance Rule 1.

Failure mode prevented: projects executing without scoped objectives, undeclared acceptance criteria, or hidden blocking dependencies — leading to mid-flight scope shifts, missed verification, or work that ships without anyone agreeing it was done.

---

## 2. Schema

### Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `title` | string | ≤100 chars; format `"<Project name> — Project Plan"` |
| `description` | string | ≤160 chars; what the project will deliver |
| `owner` | string | Agent coordinating the plan (typically project owner, a Director, or the Founder) |
| `status` | enum | `draft` / `locked` / `done` / `archived` |
| `plan_for` | UID | Single UID of the project this plan scopes. Bidirectional with project's `scoped_by:` |
| `derived_from` | UID array | **v1.4 extended:** Source(s) this plan specifies. Two valid target classes: (1) **design brief UIDs** — `type: design-brief` entries (existing pattern; bidirectional with brief's `composes_into:`); (2) **pipeline-template UIDs (v1.4 NEW)** — `type: pipeline` entries for cascade-generated plans (pipeline-activate.py authors the plan as part of pipeline.capsule v2.6 `cascade_spec:` cascade). Type-discrimination at resolution-time; mixed-class arrays honor-system at v1.4 (typically a project-plan derives from one source class). Empty array legal only with §Open Decisions `direct-commission` entry that closes before lock. |
| `member_of` | UID array | Buckets the plan belongs to. Includes the `plan_for:` UID + typically a pipeline-stage bucket. |

### Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `composes_into` | UID array | Upstream artifacts (typically a single release-plan) |
| `produced_artifacts` | UID array | Append-only record of artifacts shipped under this plan |
| `target_estimate_hours` | number | Best-effort sizing; not a commitment |
| `locked_by` | string | Required when `status: locked` or later |
| `locked_at` | ISO date | Required when `status: locked` or later |
| `supersedes` / `superseded_by` | UID | Bidirectional pair for mid-flight supersession |
| `verification_discipline` | enum | `three-instrument` (default) / `two-instrument` / `self-attested` |
| `risk_level` | enum | `low` / `medium` / `high` — informs whether §Risk Register is populated |
| `tags` | array | Domain markers (e.g., `sprint` for dev-pipeline-context plans — see §5 Tag Conventions) |
| `relationships` | typed-edge array | Schema-v2 unified relationships for cross-cutting references |

### Body shape — 7 required sections + 3 optional, in declared order

1. **`## Objectives`** — 3–6 outcome bullets answering "why this project, why now?" Outcome-focused not activity-focused.
2. **`## Scope`** — In-scope + Out-of-scope subsections; prevents creep.
3. **`## Deliverables`** — Named list with per-deliverable: what it is, acceptance criteria, effort estimate (hours), blocking dependencies.
4. **`## Dependencies`** — Blocking deps + reference artifacts (specs/briefs/capsules read) + external deps (cross-team or cross-vault inputs).
5. **`## Verification Plan`** — How each deliverable is verified. Typically the three-instrument pattern (owner build → independent review → stranger test). May name exceptions per deliverable.
6. **`## Timeline`** — Phases with per-phase deliverables, approximate hours, blocking order. **No hard calendar dates** — Tropo is too fluid for date-pegged commitments. Hours are sizing signals, not commitments.
7. **`## Open Decisions`** — Items blocked on a human decision; close before `status: locked`. Each entry names: decision, owner, what it blocks, recommendation (if any).
8. *(optional)* **`## Risk Register`** — Required when `risk_level: medium` or `high`. Table form: risk / likelihood / impact / mitigation / owner.
9. *(optional)* **`## Lessons / Reflections`** — Retrospective. Populated after `status: done`. The only body section appendable post-lock.
10. *(optional)* **`## Provenance`** — Trigger/context note when commissioned mid-session.

---

## 3. State Machine

```
draft → locked → done → archived (mirrors project lifecycle)
   ↑       ↓
   └ revisions allowed only while draft ─┘

locked → archived (mid-flight supersession; superseded_by set)
```

**Strict status enum:** `status:` ∈ {draft, locked, done, archived}

| State | Meaning |
|-------|---------|
| `draft` | Plan being authored. Objectives, deliverables, open decisions still evolving. |
| `locked` | Plan committed. Open decisions closed. Deliverables authorized to begin. |
| `done` | All deliverables shipped per acceptance criteria. §Lessons populated. `produced_artifacts:` non-empty. |
| `archived` | Historical. Either project closed naturally (reached `done` first) or plan was superseded mid-flight (`superseded_by:` set; predecessor never reached `done`). |

**Valid transitions:**

- `draft → locked` — All §Open Decisions closed; deliverables + acceptance criteria frozen
- `draft → draft` — Free revisions before lock
- `locked → draft` — **NOT ALLOWED.** Locked revisions go through supersession (Governance Rule 9)
- `locked → done` — All acceptance criteria met; §Lessons populated
- `locked → archived (superseded)` — Atomic-commit supersession per Governance Rule 9
- `done → archived` — Mirrors project lifecycle

---

## 4. Validation Rules

### Governance Rules (10)

1. **Plans SHOULD, not MUST.** Small one-deliverable work under ~4h may proceed without a plan; record skip rationale in project frontmatter or channel post.
2. **One active plan per project.** `plan_for:` is a single UID; ≤1 plan at `status: locked` or `done` per project at a time (versions allowed via supersedes/superseded_by).
3. **Locked plans are body-immutable except §Lessons / Reflections.** Post-lock revisions go through supersession; §Lessons is the only section appendable post-lock.
4. **Acceptance criteria are non-negotiable.** A deliverable is not done until its declared acceptance criteria are met. Changing acceptance criteria mid-flight requires plan supersession.
5. **Plan owner usually = project owner.** When a Director coordinates, `owner:` may differ from the project's owner field. Declare explicitly.
6. **`produced_artifacts:` is append-only.** Historical delivery record; never retroactively removed.
7. **§Open Decisions close before lock.** Each entry resolves or is explicitly deferred with rationale + recorded as a documented gap.
8. **Verification discipline declared, not assumed.** Default `three-instrument`. `two-instrument` is appropriate for pattern-matched work following a recently-locked sibling template. `self-attested` is appropriate only for mechanical work (renames, frontmatter backfills, bucket migrations) with no architectural surface.
9. **Supersession is atomic-commit.** When a locked plan is superseded mid-flight, ONE commit simultaneously: (a) promotes successor `draft → locked`, (b) sets predecessor `state: archived`, (c) sets predecessor `superseded_by:` pointing at successor, (d) sets successor `supersedes:` pointing at predecessor. Non-atomic supersession temporarily violates Rule 2 and must be avoided. Validator check 12 enforces bidirectional pair consistency.
10. **Post-lock decisions surface via channel, not body edit.** New information or blockers surfacing after lock route to the plan owner via the relevant pair channel. Minor clarifications append to §Lessons (the only post-lock-mutable section). Body-changing decisions force supersession per Rule 9.

### Validation Checks (ERROR-severity at check-in)

1. `plan_for:` resolves to a valid `project` entry
2. `member_of:` non-empty array of valid UIDs; includes the `plan_for:` UID
3. `derived_from:` (if non-empty) — every UID resolves to a `design-brief` entry (existing pattern, brief-derived plans) OR a `pipeline` entry (v1.4 NEW, cascade-generated plans authored by pipeline-activate.py per pipeline.capsule v2.6 `cascade_spec.generates_project_plan`). Mixed-class arrays accepted but unusual — a plan typically derives from one source class.
4. `composes_into:` (if present) — every UID resolves to a `release-plan` or `project` entry
5. `status:` is one of `draft` / `locked` / `done` / `archived`
6. If `status: locked` or later, `locked_by:` + `locked_at:` are present
7. If `status: done`, `produced_artifacts:` is non-empty AND §Lessons / Reflections section exists in body
8. Body contains all 7 required sections in declared order
9. If `verification_discipline:` present, value is one of `three-instrument` / `two-instrument` / `self-attested`
10. If `risk_level:` is `medium` or `high`, body contains §Risk Register
11. `supersedes:` (if present) resolves to a prior `project-plan` at `status: done` or `archived`
12. `superseded_by:` (if present) — successor at `status: draft` or `locked`; the successor's `supersedes:` field points back at this plan (bidirectional pair per Rule 9)
13. If `state: archived` AND `superseded_by:` set, successor must be at `status: locked` or `done` (supersession only legal once successor promoted past draft)

Core checks inherited: UID uniqueness, UID immutability, type immutability, owner/created/modified invariants.

---

## 5. Composes-With

- **[project.capsule (34e4cb0b)](project.capsule.md)** — project-plan scopes a project via `plan_for:`. Project's work happens under the plan's coordination.
- **[release-plan.capsule (a3f1e7b2)](release-plan.capsule.md)** — sibling at release scope. Release-plan's `streams:` are projects; each stream project may carry a project-plan. Release-plan composes N project-plans via `composes_into:` pointers on each plan.
- **[design-brief.capsule (de5181b0)](design-brief.capsule.md)** — upstream. Briefs inform plans via `derived_from:`; bidirectional pair with brief's `composes_into:`.
- **[pipeline.capsule (e4c8a6b2)](pipeline.capsule.md)** — project-plans describe what a project will do as it walks a pipeline; plan may declare anticipated pipeline path.
- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor for UID/owner/modified invariants.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — this capsule's own governance.

### Tag Conventions

When a project-plan operates in a release-engineering / dev-pipeline context as one slice of an arch-spec's deliverables, it MAY carry `tags: [sprint]`. The formal type stays `project-plan`; agents and humans refer to it as a "sprint" colloquially. The §Verification Plan body section carries the sprint's testing plan; no structural specialization is needed. Vault queries use `type: project-plan, tags: contains(sprint)`.

The pattern follows release-plan.capsule v1.0's tag conventions (`tags: [stream]` on projects; `tags: [decision]` on tasks): type stays generic, tags carry domain vocabulary, slang follows the tag. Anti-application: `tags: [sprint]` MUST NOT appear on project-plans outside dev / release-engineering / dev-pipeline contexts. The tag is domain-scoped; misapplication is a tagging defect to remove.

### History

Detailed v1.1 + v1.2 amendment-block prose, the extended Tag Conventions detail (slang convention, anti-application rule, why-a-tag, worked example YAML), the full §Studio — Shop Signage authoring procedure (human-facing quick-ref preserved per Mike-A55 *"capsules are agent-read, not human-read"* directive), the Relationship-to-release-plan comparison table, the Inheritance section, and the full changelog are preserved in the companion [project-plan.history.md (c4790782)](project-plan.history.md) governed by `capsule-history.capsule` (5ec083a3).

---

*project-plan capsule definition | LOCKED v1.3 | history at [project-plan.history.md](project-plan.history.md) | v1.3 body refactor 2026-05-11 by Argus A56 (v1.19.0 Stream C — 5-section pedagogy pattern; agent-read-not-human-read per Mike-A55 v1.18.0 walk Q3). Prior v1.0 / v1.1 / v1.2 locks preserved in history.*
*"The plan scopes the project. The project walks the pipeline. The release composes the work."*
