---
uid: e1c8d3a5
type: pipeline
subtype: workflow-node
name: promotion-workstream
title: 'Promotion Workstream — 2026 Customer Event Plan (teach-by-example: auto-task-spawn)'
description: 'Workstream sub-pipeline for the Promotion lane: pre/during/post-event social cadence, landing page, lead capture, analyst outreach. Carries its own cascade_spec.spawns_tasks — demonstrates auto-task-generation as teach-by-example per v1.35.0 Q19 lock.'
version: '1.0'
status: active
state: active
role: workstream
domain: marketing-event-activation
owner: promotion-coordinator-agent
author: argus-a67
created: 2026-05-16
created_by: argus-a67
modified: 2026-05-16
modified_by: argus-a67
schema_version: 2
extraction_scope: ship
governed_by: e4c8a6b2
children: []
next_steps: []
cascade_spec:
  generates_project_plan: false
  spawns_workstreams: []
  spawns_tasks:
    - title: 'Pre-event tease post #1 — announce attendance'
      owner_agent_class: promotion-coordinator-agent
      relative_offset_days: -21
    - title: 'Pre-event tease post #2 — booth preview'
      owner_agent_class: promotion-coordinator-agent
      relative_offset_days: -14
    - title: Landing page launch (lead capture live)
      owner_agent_class: promotion-coordinator-agent
      relative_offset_days: -14
    - title: 'Pre-event tease post #3 — speaker session promo'
      owner_agent_class: promotion-coordinator-agent
      relative_offset_days: -7
    - title: Day-of arrival teaser
      owner_agent_class: promotion-coordinator-agent
      relative_offset_days: 0
    - title: Day-of booth photo + live update
      owner_agent_class: promotion-coordinator-agent
      relative_offset_days: 0
    - title: Day+1 thank-you + highlights
      owner_agent_class: promotion-coordinator-agent
      relative_offset_days: 1
    - title: Post-event recap blog/email + lead nurture sequence start
      owner_agent_class: promotion-coordinator-agent
      relative_offset_days: 3
member_of:
  - f3a2c819
  - e8d1a4f6
unit_of_work_purpose: Pre/during/post-event promotional cadence + lead-capture infrastructure. Highest task-density workstream — also the canonical teach-by-example for auto-task-spawn via cascade_spec.spawns_tasks.
tags:
  - pipeline
  - workstream
  - promotion
  - hello-tropo
  - auto-task-spawn-teach-by-example
  - v1-35-0
file_ext: md
subsystem_hub:
  - 2d083137
capsule_version: '2.5'
---

# Promotion Workstream — 2026 Customer Event Plan

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Work](2d083137.md) → **Promotion Workstream — 2026 Customer Event Plan (teach-by...**
<!-- nav-block:end -->

*Carries its own `cascade_spec.spawns_tasks:` — when the master pipeline cascades and this workstream activates, the activation-script ALSO auto-spawns 8 date-keyed tasks against the event date. Teach-by-example for users learning Tropo's cascade depth.*

## Purpose

Pre-event awareness; during-event live cadence; post-event recap + lead capture sequence. Owned by `promotion-coordinator-agent`. **First canonical use of `cascade_spec.spawns_tasks:` (Q19 teach-by-example pattern).**

## Structure

```
promotion-workstream
├── Pre-event social cadence (T-21 days → T-1 day)
├── Landing page + lead-capture (T-14 days launch)
├── Day-of live updates (T = 0)
├── Post-event recap (T+1 to T+7 days)
└── Lead nurture sequence start (T+3 days)
```

## Nodes

Leaf workstream. Tasks include both auto-spawned (from `spawns_tasks:` cascade — see frontmatter) AND agent-generated (additional tasks the agent adds beyond the auto-spawned cadence).

## Flow Rules

Auto-spawned tasks carry `relative_offset_days:` resolved at activation time against the event date provided to `pipeline-activate.py --event-date`. Without `--event-date`, auto-spawn is skipped (WARN logged).

## Cold-Boot Walk-Through

When master cascade fires + reaches this workstream, the activation-script reads this pipeline's `cascade_spec.spawns_tasks:`, resolves each task's `relative_offset_days:` against the event date, and authors a `type: task` capsule for each at terminal location `member_of:` this workstream's activation-root-project. The 8 tasks emerge with proper `due_date:` values; `promotion-coordinator-agent` picks them up + executes (or adapts).

## Known Enforcement Gaps

| Gap | What closes it | Target | Owner |
|---|---|---|---|
| `event-date` argument required for spawns_tasks; warn-skip if absent | Master pipeline could declare event-date in its cascade_spec context | v1.35.5 | Argus |
| Task dependencies via `depends_on:` honor-system at v1.35.0 | Validator enforces resolution | v1.36.0 | Argus |

## Changelog

- **v1.0** (2026-05-16, argus-a67) — Initial; first canonical use of `cascade_spec.spawns_tasks:` per v1.35.0 Q19 teach-by-example lock.

---

*Promotion workstream | Hello Tropo | First auto-task-spawn example | Argus A67 | 2026-05-16*
*"The cascade goes one level deeper here — by design, as a teach-by-example."*
