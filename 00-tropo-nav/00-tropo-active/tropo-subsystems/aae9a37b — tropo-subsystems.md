---
uid: aae9a37b
type: project
status: evergreen
state: active
title: tropo-subsystems
description: Root container for Tropo's standing subsystems — evergreen infrastructure surfaces that host ongoing work across all releases.
owner: argus
created: 2026-04-19
modified: 2026-04-19
created_by: argus-a27
tags:
  - subsystems
  - root
  - standing
  - evergreen
  - infrastructure
file_ext: md
schema_version: 2
extraction_scope: ship
slug: tropo-subsystems
lifecycle: standing
member_of: []
---

# tropo-subsystems — Root

<!-- nav-block:start -->
**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/tropo-subsystems/aae9a37b — tropo-subsystems.md](../../00-tropo-nav/00-tropo-active/tropo-subsystems/aae9a37b%20%E2%80%94%20tropo-subsystems.md)

**🌳 Tropo-Nav Path** (chat): [tropo-os-v1.84.1/00-tropo-nav/00-tropo-active/tropo-subsystems/aae9a37b — tropo-subsystems.md](tropo-os-v1.84.1/00-tropo-nav/00-tropo-active/tropo-subsystems/aae9a37b%20%E2%80%94%20tropo-subsystems.md)

**🔗 This file** — UID `aae9a37b` · type `project` · state `active` · status `evergreen`

**↓ Children (10):**
  - **document:** [Tropo Capabilities](7a1ca900.md)
  - **project (9):** [Tropo Agents](99ed55fd.md) · [Tropo Documentation](f87e33f0.md) · [Tropo Governance](8dd772a0.md) · [Tropo Library](1aba710c.md) · [Tropo Link](3a207ed3.md) · [Tropo Playbooks](76bab75f.md) · [Tropo Rendering](dbc1cbbf.md) · [Tropo Test Harness](952f3aa3.md) · + 1 more

**📥 Cited by (1):**
- [Tropo Capabilities](7a1ca900.md) — `7a1ca900` (type `document`, via `member_of`, `refs`)
<!-- nav-block:end -->

*Standing infrastructure surfaces for Tropo-OS. Each subsystem below is an evergreen project hub — it holds the living history of work on that subsystem, across releases.*

*This is NOT in the work-pipeline. Pipeline stages are for versioned work that flows through ideate → design → specify → build → deploy. Subsystems are long-lived containers that span all of that — discrete work units flow through the pipeline, referencing the subsystem they belong to; subsystems themselves never move.*

*Created 2026-04-19 by Argus A27 + Mike Maziarz, extracting standing subsystems from the work-pipeline's 4-build/2-active bucket to preserve pipeline semantics (bucket = current sprint work, not evergreen infrastructure).*

---

## Members

Each subsystem is a standing project with its own board, collections, and task flow. Work in each subsystem is discovered via the cascade index and the rehydrated tree.

| Subsystem | UID | Description |
|-----------|-----|-------------|
| Tropo Library | [1aba710c](1aba710c.md) | Governed graph document store — ledger + registry + cascade + UID addressing + schemaless substrate + federation (NEW v1.3) |
| Tropo Work (formerly TWS) | [2d083137](2d083137.md) | Typed work primitives — tasks, projects, decisions, specs, collections, concept→release chain |
| Tropo Agents (formerly TAS; absorbs TBS) | [99ed55fd](99ed55fd.md) | Executive lifecycle + boot + session agents (sa.*) + v2 three-tier memory + retirement |
| Tropo Playbooks (formerly TPS) | [76bab75f](76bab75f.md) | Playbook spec v2.2 + playbook.capsule v2.0 + pipeline subtype + skills + actions |
| Tropo Rendering (formerly TLGS) | [dbc1cbbf](dbc1cbbf.md) | Board-definitions + board-snapshots + prose query vocabulary + render engine + synthesizer |
| Tropo Governance (formerly TVS) | [8dd772a0](8dd772a0.md) | ADRs + operating principles + verification instruments + three-instrument discipline |
| ~~TBS — Tropo Boot System~~ | [b8daa232](b8daa232.md) | ARCHIVED 2026-04-21 — absorbed into Tropo Agents per sa.research 028 (boot is a phase, not a sibling subsystem) |

**v1.3 rename notes.** All subsystem hubs renamed to canonical names per [capability matrix v1.0 OD2-F](../../TROPO-CAPABILITIES.md). UIDs preserved across all renames. Library is a new subsystem created in v1.3 (content extracted from former TWS + TLGS). TBS archived; its boot content merged into Tropo Agents. Naming decision: drop "System" suffix per v1.3 convention — "Tropo Work" reads cleaner than "Tropo Work System."

---

## Relationship to other roots

- **[work-pipeline](020274e0.md)** — versioned work flows through the pipeline and references subsystems via `projects:` dual-membership. The pipeline is temporal; subsystems are durable.
- **[Tropo Technical Library](8d664afa.md)** — narrative articles *about* these subsystems (essays, research, thought pieces). Reference material.
- **[Architecture Specifications](7c69071b.md)** — formal specs that govern subsystem design.

---

## Documentation Note

Each subsystem hub currently has a thin body (what it covers + how tasks flow). **Expansion is a real need** — each subsystem deserves richer documentation covering current state, open decisions, architectural constraints, external references, and health read. Filed as a documentation task on 2026-04-19. Subsystem hubs are where an agent or human lands when they ask "what's the current state of playbook work?" — the answer should be legible at a glance.

---

*tropo-subsystems | root project | Argus A27 + Mike Maziarz | 2026-04-19*
*"Subsystems are durable. Pipeline work is temporal. Different objects, different homes."*
