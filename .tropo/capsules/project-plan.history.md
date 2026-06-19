---
uid: c4790782
name: "project-plan-history"
type: capsule-history
governs: f7b9c4a2
governs_path: .tropo/capsules/project-plan.capsule.md
extracted_at: 2026-05-11
extracted_by: argus-a56
extracted_in_cycle: "v1.19.0 — Convergence Phase 1"
extracted_in_release: pending-v1.19.0
schema_version: 2
governed_by: 5ec083a3   # capsule-history.capsule
extraction_scope: argo-private
member_of:
  - "8dd772a0"   # tropo-governance
tags: [capsule-history, extracted-from-project-plan-capsule, v1.19.0-stream-c]
---

# project-plan — Capsule History

*History extracted from project-plan.capsule v1.2 → v1.3 body refactor (v1.19.0 Stream C; 2026-05-11). The active capsule preserves the §Required floor + State Machine + Validation Rules + Composes-With per the 5-section pedagogy pattern. This file preserves: amendment-block prose at the top of the original v1.2 body; the extended Tag Conventions detail; the full §Studio — Shop Signage authoring procedure (human-facing quick-ref); the Relationship-to-release-plan comparison table; the Inheritance section; the full changelog table.*

---

## Amendment Blocks (extracted from v1.2 active body)

### v1.1 (2026-04-25, Argus A34)

Stream 3 D3.2 uplift of v1.4 (Craftsman's Workshop). Added §Workshop — Shop Signage + Relations Header per the v3 capsule shop-signage pattern. v1.0 lock 2026-04-21 by Argus A30 preserved. UID `f7b9c4a2` preserved across the amendment.

### v1.2 (2026-05-03, Argus A43; LOCKED — single-instrument cold-boot verified PASS-WITH-MINOR-GAP)

v1.4.4 Stream D minimum amendment. Additive, non-breaking. Adds §Tag Conventions section establishing `tags: [sprint]` as the marker convention for project-plan instances functioning as sprints under dev-pipeline (or any release-engineering context). When a project-plan carries `tags: [sprint]`, agents refer to it as a "sprint" colloquially in conversation, channels, and prose — the formal type remains `project-plan`; the slang follows the tag. Same pattern release-plan.capsule v1.0 established for `tags: [stream]` on projects and `tags: [decision]` on tasks: type stays generic, tags carry domain vocabulary, slang follows the tag.

Per [dev-pipeline + vault inbox primitive (e1c47a9f)](../../vault/files/e1c47a9f.md) Q3 (sprint plan granularity) — Mike-directed 2026-05-03 to use project-plan as the sprint substrate rather than authoring a separate sprint-plan.capsule. Earn-the-abstraction: project-plan v1.1 already has every body section a sprint needs (Objectives / Scope / Deliverables with acceptance criteria / Dependencies / Verification Plan / Timeline / Open Decisions). Sprint plans inherit all of it; "testing plan" maps to §Verification Plan. UID `f7b9c4a2` preserved.

---

## Tag Conventions — Extended Detail (extracted from v1.2)

The active capsule §5 Composes-With carries the tag-convention rule in compact form. The extended detail follows.

### The slang convention

When a project-plan carries `tags: [sprint]`, agents refer to it as a "sprint" colloquially — in conversation, channel posts, prose, and informal references. The formal type remains `project-plan`; the vault query is `type: project-plan, tags: contains(sprint)`. The slang is for human ergonomics and domain vocabulary fit; the schema is generic.

### Anti-application rule

`tags: [sprint]` MUST NOT appear on project-plans outside dev / release-engineering / dev-pipeline contexts. A marketing project-plan, a research project-plan, or any plan whose work isn't release-cycle engineering should NOT carry the sprint tag — they may carry their own domain tags (e.g., `tags: [campaign]`, `tags: [study]`) but not `[sprint]`. The tag is domain-scoped; misapplication is a tagging defect to remove, not a semantic ambiguity to interpret.

This pattern follows release-plan.capsule v1.0's precedent — type stays generic; tags carry domain vocabulary; slang follows the tag. Other domains may add their own marker tags as work patterns surface (e.g., `tags: [campaign]` for marketing project-plans, `tags: [study]` for research project-plans); the convention is established and extensible.

### Why a tag rather than a subtype

Earn-the-abstraction. The schema is the same; only the domain context differs. A `subtype:` field would imply structural specialization (different required fields, different validation); a tag implies domain context only. Sprints don't have unique structural needs — they have all the project-plan body sections any project plan has. Tag is the right granularity.

### Example: a sprint within a v1.4.4 arch-spec

```yaml
---
uid: <8-hex>
type: project-plan
title: "Sprint 1 — Work-Item Primitives — Project Plan"
description: "Authors note v3.2 + design-brief v3.1 + task v4.0 as bundled three-instrument cycle."
status: locked
state: active
plan_for: <project-uid>           # sub-project of the arch-spec
derived_from: [<design-brief-uid>]
member_of: [<arch-spec-uid>, ...]
tags: [sprint, v1.4.4-stream-a]   # the slang marker
verification_discipline: three-instrument
---
```

Body uses standard project-plan §Required Body Sections (Objectives, Scope, Deliverables, Dependencies, Verification Plan ← carries the sprint's testing plan, Timeline, Open Decisions). No structural difference from a generic project-plan; the tag is the only signal that "in dev context, call this a sprint."

---

## Studio — Shop Signage (extracted v1.1 + v1.2 human-facing quick-ref)

*Preserved per Mike-A55 directive 2026-05-11: capsules are agent-read, not human-read. The Studio quick-ref is a human-facing convenience; extracted from active body to history. Active capsule §5 Composes-With teaches the type to the agent; this section teaches the workflow to a human author.*

### Tools available

- `ls collections/projects/` — survey existing project rosters before authoring a plan for a duplicate scope
- `vault/00-index.jsonl` — grep `type: project-plan` for the live plan inventory; cross-check `plan_for:` to detect Rule 2 collisions
- `vault/00-index.jsonl` — grep `type: design-brief` to find the briefs this plan should derive from (composability pair)
- `.tropo-studio/registries/registry.jsonl` — verify `plan_for:`, `derived_from:`, `member_of:` UIDs resolve before lock
- Reference instances: [v1.3 Stream B Foundation plan (c0ce1b3a)](../../vault/files/c0ce1b3a.md) (3-instrument verified, locked); [v1.3 Session 7 plan (198339b0)](../../vault/files/198339b0.md) (`status: done`, Lessons populated)

### Skills

- `author-project-plan.skill.md` *(forthcoming v1.5)* — scaffold the 7 REQUIRED body sections + minimum frontmatter; pre-fills `governed_by: f7b9c4a2` and asserts `derived_from:` non-empty (or registers a direct-commission entry under §Open Decisions)
- `lock-project-plan.skill.md` *(forthcoming v1.5)* — validates §Open Decisions empty, `verification_discipline:` declared, all REQUIRED sections present; flips `status: draft → locked` atomically with `locked_by` / `locked_at`

### Procedures

- **(v1.2) Authoring a sprint** — within a release-engineering / dev-pipeline context, when the work being scoped is one slice of an arch-spec's deliverables: author a project-plan as usual with `tags: [sprint]` declared in frontmatter. The §Verification Plan body section carries the sprint's testing plan. The plan's `member_of:` references the arch-spec (or the sub-project under the arch-spec). Agents and humans may refer to this plan as a "sprint" colloquially; ledger queries use `type: project-plan, tags: contains(sprint)`.
- **Pre-authoring discipline** — author the design brief first per Rule 1 + §Intent; if no brief exists and the work is small enough to bypass, record the skip rationale in the project frontmatter or channel post; a plan with empty `derived_from:` MUST carry a §Open Decisions `direct-commission` entry that closes before lock
- **Compose with the brief** — set `derived_from: [<brief-uid>...]`; on each referenced brief, append this plan's UID to `composes_into:` (atomic bidirectional pair per design-brief.capsule v1.1)
- **Author the plan body** — fill the 7 REQUIRED sections in declared order: Objectives → Scope → Deliverables → Dependencies → Verification Plan → Timeline → Open Decisions; populate Risk Register if `risk_level: medium`/`high`
- **Lock** — close every §Open Decisions entry per Rule 7; declare `verification_discipline:` (default three-instrument); set `locked_by` + `locked_at`; flip `status: draft → locked`
- **Advance through Done** — as deliverables ship, append their UIDs to `produced_artifacts:` (Rule 6 append-only); when all acceptance criteria met, populate §Lessons / Reflections (Rule 3 append-only post-lock surface); flip `status: locked → done`
- **Supersession discipline** — Rule 9 atomic-commit: when a locked plan needs revision mid-flight, in ONE commit (a) author successor at `draft` for same `plan_for:`, (b) lock the successor (promoting from draft → locked), (c) flip predecessor `state: archived` + `superseded_by: <successor-uid>`, (d) set successor `supersedes: <predecessor-uid>`; non-atomic supersession violates Rule 2
- **Post-lock decision-surfacing** — new blockers surfaced after lock route via the relevant pair channel (Rule 10); minor clarifications append to §Lessons (the only post-lock-mutable section); body-changing decisions force supersession per Rule 9
- **Archive** — when project closes (`done`) the plan flips to `archived`; `done → archived` mirrors project lifecycle

### Rules at-a-glance (mirrors §4 Validation Rules in active capsule)

1. Plans SHOULD, not MUST exist — small (one-deliverable, ~4h) work may proceed without a plan; record the skip rationale
2. One plan per project — `plan_for:` is single UID; ≤ 1 active plan per project at a time
3. Locked plans are body-immutable except §Lessons — frozen at lock; revisions go through supersession
4. Acceptance criteria are non-negotiable — changing them mid-flight requires supersession
5. Plan owner is usually the project owner — declare differences explicitly when a Director coordinates
6. `produced_artifacts:` append-only — historical delivery record; never retroactively removed
7. §Open Decisions close before lock — each entry resolves or moves to a documented gap
8. Verification discipline declared, not assumed — default `three-instrument`; `two-instrument` for pattern-matched work; `self-attested` only for mechanical work
9. Supersession is atomic-commit — successor lock + predecessor archive + bidirectional pair, all in one commit
10. Post-lock decisions surface via channel, not body edit — channel preserves audit trail; §Lessons carries the insight forward

### Pitfalls

- **Authoring at `status: locked` directly** — plans MUST start at `draft`; no validator check today, but an authoring discipline gap
- **Empty `derived_from:` without §Open Decisions `direct-commission` entry** — Validation Check 3 violation pattern
- **Two locked plans for the same `plan_for:` project** — Rule 2 + Validation Check 12 violation
- **Editing locked plan body (other than §Lessons)** — Rule 3 violation
- **`status: done` without §Lessons / Reflections** — Validation Check 7 violation
- **Risk-level medium/high without §Risk Register** — Validation Check 10 violation
- **`verification_discipline: self-attested` on a load-bearing governance artifact** — Rule 8 spirit-violation
- **Mid-flight scope expansion absorbed into the locked plan** — Rule 4 violation; supersede instead

### Worked examples

- [v1.3 Stream B Foundation plan (c0ce1b3a)](../../vault/files/c0ce1b3a.md) — 9-deliverable plan, 3-instrument verification, brief-derived
- [v1.3 Session 7 plan (198339b0)](../../vault/files/198339b0.md) — `status: done` with Lessons populated
- [v1.3 Session 3 plan (5e53a3a1)](../../vault/files/5e53a3a1.md) — superseded mid-flight (Rule 9 worked example)

### Go next

- Sibling at smaller scope → [playbook.capsule v2.5 (e7b3c509)](playbook.capsule.md)
- Sibling at release scope → [release-plan.capsule v1.0 (a3f1e7b2)](release-plan.capsule.md)
- Upstream → [design-brief.capsule (de5181b0)](design-brief.capsule.md)
- Composed entity → [project.capsule v2.1 (34e4cb0b)](project.capsule.md)
- Pipeline integration → [pipeline.capsule (e4c8a6b2)](pipeline.capsule.md)
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Relationship to `release-plan` — Comparison Table (extracted)

The project-plan and release-plan capsules are complementary at different scopes:

| Dimension | `project-plan` | `release-plan` |
|-----------|----------------|----------------|
| **Verb** | scopes one project | coordinates a release |
| **Scope** | K deliverables | N streams (N projects) |
| **Authored when** | after design brief, before significant authoring | before release build starts |
| **Closes when** | project done | release shipped |
| **Answers** | "what will this project produce and how do we verify?" | "how do we ship this release?" |
| **Composes** | from K deliverables | from N project-plans |

A project-plan can exist without a release-plan (small standalone project). A release-plan composes from many project-plans. The `composes_into:` field on a project-plan points at the release-plan (if one exists) for traversal.

---

## Inheritance

Extends `core`. Inherits all core rules (UID uniqueness/immutability, type immutability, owner/created/modified invariants). Documented in active capsule §5 Composes-With.

---

## Changelog (full lineage)

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-04-21 | Initial version LOCKED. Authored by Argus A30 as the first deliverable of the v1.3 capsule ship project. Two-instrument verification (per the capsule's own `verification_discipline:` taxonomy this amendment introduced): Argus build + sa.cold-boot 048 BATCH stranger test. Swarm review deferred to set-level review across all v1.3 capsules. Cold-boot verdict: PASS-WITH-GAPS, ship recommended. 5 P1 remediation edits landed in-session (supersession state transition; atomic-commit supersession rule; brief-side reverse pointer documentation; post-lock decision-surfacing governance; operational definitions of verification_discipline enum values). P2 polish deferred to v1.1. | argus-a30 |
| 1.1 | 2026-04-25 | Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop). Added §Workshop — Shop Signage section (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next) per the v3 capsule shop-signage pattern. Added Relations Header right after H1 — clickable navigation surface mirroring frontmatter. Frontmatter `composes_with: 34e4cb0b` declared. No semantic changes to §Required floor / §Validation Checks / §Governance Rules / §State Machine. UID preserved at f7b9c4a2. | argus-a34 |
| 1.2 | 2026-05-03 | LOCKED — v1.4.4 Stream D minimum amendment. Additive, non-breaking. New §Tag Conventions section establishes `tags: [sprint]` as the marker for project-plan instances functioning as sprints under dev-pipeline / release-engineering contexts. Slang convention documented: when a project-plan carries `tags: [sprint]`, agents and humans refer to it as a "sprint" colloquially; formal type remains `project-plan`. Same pattern as release-plan.capsule v1.0's `tags: [stream]` + `tags: [decision]`: type stays generic, tags carry domain vocabulary, slang follows the tag. New Studio procedure for authoring sprints. No new fields, no new validation checks, no body section additions, no schema changes. Earn-the-abstraction per Mike directive 2026-05-03. UID `f7b9c4a2` preserved. Pending single-instrument cold-boot verification per A41 right-sizing pin. | argus-a43 |
| 1.3 | 2026-05-11 | **v1.19.0 Stream C — Capsule Pedagogy Completion.** Body refactor to 5-section pedagogy pattern (Intent → Schema → State Machine → Validation Rules → Composes-With) per Mike-A55 *"capsules are agent-read, not human-read"* directive from v1.18.0 walk. Active body reduced from 375 → ~190 lines (~49% reduction; matches v1.18.0 precedent average of 52%). Extracted to this `.history.md` companion: v1.1 + v1.2 amendment-block prose, extended Tag Conventions detail (slang convention, anti-application rule, why-a-tag, example), §Studio — Shop Signage authoring procedure in full (human-facing quick-ref), Relationship-to-release-plan comparison table, Inheritance section, full changelog. **No schema changes, no validation rule changes, no governance rule changes, no state machine changes.** Bidirectional pointer pair: active capsule frontmatter `history_file: c4790782` ↔ this file's `governs: f7b9c4a2`. UID `f7b9c4a2` preserved. | argus-a56 |

---

## Provenance

- **Extracted at:** 2026-05-11
- **Extracted by:** argus-a56 (during v1.19.0 Stream C — Capsule Pedagogy Completion)
- **Active capsule version at extraction:** v1.2 (375 lines)
- **Active capsule version after extraction:** v1.3 (~190 lines; ~49% reduction)
- **Extraction-fidelity check:** All historical content preserved in this companion file. Active capsule retains v1.0-locked §Required floor + State Machine + Validation Rules + Governance Rules. No semantic changes; body restructure only. Tag Conventions rule preserved in compact form in active §5 Composes-With; extended detail in this file.

---

*project-plan capsule history | UID c4790782 | v1.19.0 Stream C extraction 2026-05-11 by Argus A56 | Bidirectional pair: governs f7b9c4a2*
