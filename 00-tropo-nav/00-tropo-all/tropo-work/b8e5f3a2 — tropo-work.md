---
uid: b8e5f3a2
type: project
title: tropo-work
description: 'Tropo-OS L0 work-substrate root primitive. Every Tropo-OS vault ships with one. Navigable graph home for all pipelines (dev-pipeline today; release-pipeline / content-pipeline / research-pipeline future). Pure organizational anchor — no charter, no decisions, no work attached at L0; per the L0 root project sub-pattern, the substrate is permanent active with no status transitions. Children: dev-pipeline (cd1fcd25), legacy-work-pipeline (020274e0). Peers at L0: vault-inbox (2d5f9b04) — distinct role per V40 e61b49cc Thread 5.'
author: argus-a44
status: active
state: active
priority: P0
schema_version: 2
extraction_scope: ship
governed_by: <project-capsule-uid>
owner: 7f5b1d83
member_of: []
created: 2026-05-04
modified: 2026-05-04
created_by: argus-a44
modified_by: argus-a44
schema_version_doc: 2
substrate_role: l0-work-root
sub_pattern: l0-root-project
brand_directive: 'Mike Maziarz 2026-05-04: ''I want that branded into the shippable product anyhow.'''
ships_in_release: true
target_release: '1.6'
refs:
  - b6f1e9c4
  - e61b49cc
  - 8b3f1d92
  - cd1fcd25
  - 020274e0
  - 2d5f9b04
  - 7f5b1d83
  - 3a9d6c5e
relationships:
  - kind: ships-in
    description: 'Every Tropo-OS vault ships with a tropo-work L0 root project as substrate primitive. extraction_scope: ship.'
  - kind: aligned-with
    description: 'Tropo Work v3 spec 8b3f1d92 + tropo-work-v3-overview.md library doc + tropo-work-v3-walkthrough.md. tropo-work L0 root and Tropo Work v3 substrate vocabulary align: this project is the graph-level anchor for the work-management substrate that Tropo Work governs at the type/process level.'
  - kind: implements-pattern
    description: 'L0 root project sub-pattern (b6f1e9c4 Decision 2): permanent active; no status transitions; pure-hierarchy use case; no required board or collection. Documented in project.capsule §Workshop signage as Stream A.2 of v1.6.'
  - kind: enables
    description: Substrate invariant 'Everything is a child of the project' (Mike directive 2026-05-04). At dev-pipeline level, every activation's outputs compose member_of upward through the activation root project, then to the pipeline (cd1fcd25), then to tropo-work. The graph composes upward; nothing escapes.
tags:
  - tropo-work
  - l0-root
  - substrate-primitive
  - ship
  - foundation
  - v1.6
  - p0
file_ext: md
---

# tropo-work

*Tropo-OS L0 work-substrate root. Every Tropo-OS vault ships with one. Authored 2026-05-04 by Argus A44 as Stream A.1 of v1.6 cycle (dev-pipeline activation [`c4f7e2a1`](../../agents/dev-pipeline/activations/c4f7e2a1/run.jsonl)).*

---

## What this project is

`tropo-work` is the substrate-level **L0 root** of Tropo's work-organization graph. It has no parent (true L0). Its children are the work-pipelines a vault has authored: `dev-pipeline` (currently in Argo's dev-vault), and any future user-authored pipelines (release-pipeline, content-pipeline, research-pipeline, etc.).

The project itself does no work, holds no decisions, hosts no board. It is a **navigable anchor** — when a stranger walks the vault tree, `tropo-work/` is where work happens. Walk down: see the pipelines. Walk into a pipeline: see its activations. Walk into an activation: see what that release produced.

## Why it ships in every vault

Per Mike Maziarz directive 2026-05-04: *"I want that branded into the shippable product anyhow."* `tropo-work` is a substrate primitive — not a convenience, not optional, not user-authored. Every vault that boots Tropo-OS gets a `tropo-work` L0 root automatically. The `extraction_scope: ship` declares this in the build-release pipeline.

User vaults can override the displayed folder/path locally if they want a custom name (the vault-entity owns the substrate at first-run). The kernel default is `tropo-work` for cross-vault consistency in vocabulary — when crew or strangers reference "the work tree," they mean `tropo-work/`.

## Children

At v1.6 ship in **user vaults**:

- [`dev-pipeline (cd1fcd25)`](cd1fcd25.md) — the development pipeline; the canonical first pipeline. Ships in every Tropo-OS vault. v1.6 reparented from L0 to here.

At v1.6 ship in **Argo's dev-vault** (additional, argo-reference):

- `legacy-work-pipeline (020274e0)` — the deprecated 4-stage Innovation Pipeline (Ideate → Design → Specify → Build → Deploy). v1.6 renamed from `work-pipeline` and reparented under tropo-work for lineage-in-graph (the deprecated work is recorded in Argo's substrate, not orphaned at L0). **Argo-specific lineage** — `extraction_scope: argo-reference` so it does NOT ship to user vaults; the user-vault tropo-work tree contains only `dev-pipeline/` and any user-authored pipelines.

Future siblings as the v1.6+ thesis chain advances: `release-pipeline/` (v1.14+), `content-pipeline/`, `research-pipeline/`. Authored when real work surfaces, not as v1.6 reservations.

## Peers at L0 (NOT under tropo-work)

[`vault-inbox (2d5f9b04)`](2d5f9b04.md) is a peer at L0, not a child. Per V40's [`e61b49cc §3 Thread 5`](e61b49cc.md), vault-inbox carries three distinct roles (orphan catcher, external intake, composable backlog union) that don't fit under "work substrate." vault-inbox is for ungroomed work; tropo-work is for active work-pipelines. Peers, not parent/child.

[`vault-entity placeholders`](7f5b1d83.md) (Argo vault entity + Mike person entity 4b6e2c8a) are also peers at L0 — they're identity, not work.

## L0 root project sub-pattern

This project instantiates the **L0 root project sub-pattern** locked at [v1.6 brief b6f1e9c4 Decision 2](b6f1e9c4.md):

- `status: active` permanent (no transitions through `proposed → active → completed → archived`)
- No required board
- No required collection
- No `member_of:` parent (true L0)
- Pure hierarchy: children attach via their `member_of:` arrays
- Capsule type: `project` (earned-the-abstraction; existing primitive carries the load)

Documented in [`project.capsule.md`](vault/capsules/tropo-project.capsule.md) §Workshop signage as Stream A.2 of this cycle.

## Substrate invariant

Per Mike directive 2026-05-04: *"Everything is a child of the project. Step 0."*

Applied at the dev-pipeline level: every dev-pipeline activation produces an activation-root-project at step-0 (first instance: [`3a9d6c5e`](3a9d6c5e.md) for v1.6 run `c4f7e2a1`). Every artifact that activation produces is `member_of:` the activation root. The activation root is `member_of:` the pipeline. The pipeline is `member_of:` `tropo-work`. **The graph composes upward; nothing escapes.**

## Capsule-vs-instance naming convention

Per [v1.6 brief b6f1e9c4 Decision 5](b6f1e9c4.md) — kernel rule:

- **Dotted form** (`<kind>.capsule.md`, `<name>.playbook.md`) is reserved for kernel-file definitions (capsules, playbooks, actions, skills)
- **Hyphenated form** (`tropo-work/`, `dev-pipeline/`, `legacy-work-pipeline/`) is for project/instance folder names

This project's name `tropo-work` follows the rule: instance, hyphenated. Children also follow: `dev-pipeline/` (renamed from violation `dev-pipeline/`), `legacy-work-pipeline/`.

KB article documenting the convention: `vault/files/9b3e8c47.md` (Stream A.4 of v1.6).

---

*tropo-work | L0 work-substrate root | Authored 2026-05-04 by Argus A44 as Stream A.1 of v1.6*
*"Every Tropo-OS vault has one. The work tree starts here."*
