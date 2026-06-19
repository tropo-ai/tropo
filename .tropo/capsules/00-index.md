---
subsystem_hub:
  - "2d083137"
title: "Tropo Capsule Definitions — Index"
status: published
type: index
tier: os
owner: tropo
created: 2026-04-10
---

# Tropo Capsule Definitions

*Capsule definitions are versioned governance schemas. Each defines the rules an entry of a given type must follow when checked into the Vault.*

This folder is part of the Tropo OS kernel. It ships with the fresh vault. Capsule definitions are read by agents at check-in to validate entries against the declared rules.

## Release Lifecycle Capsule Types (release-plan added April 19, 2026 — Argus A28)

| Type | File | State Machine |
|------|------|---------------|
| `release` | [`release.capsule.md`](release.capsule.md) | build → verify → deploy → done → archived |
| `release-plan` | [`release-plan.capsule.md`](release-plan.capsule.md) | design → specify → build → done → archived |

The `release-plan` is the coordination artifact authored before and during a release build — it names the thesis, streams, gates, and ship criteria. The `release` is the post-ship historical record. They are complementary and 1:1 linked via `shipped_release:` on the plan. `release-plan` was drafted by [d.pm (Pam)](../../agents/directors/d.pm/d.pm.md) at Mike's direction and locked by Argus A28 on 2026-04-19 to unblock the v1.2 release plan.

*Note: `release` capsule was locked April 16 but not previously indexed here — added as part of this April 19 release-lifecycle section.*

## Agent Lifecycle Capsule Types (added April 17, 2026 — Argus A27)

| Type | File | State Machine |
|------|------|---------------|
| `agent-configurator` | [`agent-configurator.capsule.md`](agent-configurator.capsule.md) | draft → active → superseded |

Agent-configurators live at `agents/<name>/<name>-activation.md` — not in the Vault. The compiled per-agent activation artifact Mike attaches to boot an agent. Self-executing on first read.

*Note: V31's April 19 ADR-032 migration shipped thin loaders, not monoliths. Capsule v1.0 describes the abandoned pattern and is pending v2.0 amendment by Argus (queued, 2026-04-19).*

## Phase 1.B Capsule Types (added April 14, 2026 — Argus A23)

| Type | File | State Machine |
|------|------|---------------|
| `playbook-run` | [`playbook-run.capsule.md`](playbook-run.capsule.md) | active → paused → complete → archived; active → failed → archived |

## Phase 1 Capsule Types

| Type | File | State Machine |
|------|------|---------------|
| `core` | [`core.capsule.md`](core.capsule.md) | — (root type) |
| `task` | [`task.capsule.md`](task.capsule.md) | backlog → active → blocked → review → done → archived |
| `project` | [`project.capsule.md`](project.capsule.md) | proposed → active → paused → completed → archived |
| `design-spec` | [`design-spec.capsule.md`](design-spec.capsule.md) | draft → locked → superseded |
| `design-brief` | [`design-brief.capsule.md`](design-brief.capsule.md) | draft → reviewed → informing |
| `decision` | [`decision.capsule.md`](decision.capsule.md) | proposed → accepted → superseded |
| `document` | [`document.capsule.md`](document.capsule.md) | draft → published → archived |
| `collection-ref` | [`collection-ref.capsule.md`](collection-ref.capsule.md) | active → archived |
| `board-definition` | [`board-definition.capsule.md`](board-definition.capsule.md) | draft → active → archived |
| `board-snapshot` | [`board-snapshot.capsule.md`](board-snapshot.capsule.md) | draft → active → archived |
| `team-def` | [`team-def.capsule.md`](team-def.capsule.md) | active → archived |

## Inheritance

All capsule types inherit from `core`. A child type adds rules but cannot remove parent rules. The inheritance chain is resolved at check-in: the validator runs `core` checks, then the type's own checks, then any sub-type checks.

## Adding New Types

Creating a new capsule type is a governed act. It requires:

1. A proposed capsule definition file in `.tropo-studio/capsules/` (org-level) or as a new entry in this folder (OS-level)
2. The new type extends an existing parent type
3. Mike (or the vault principal) approves the new type before it can be referenced in the vault index
4. The schema reference (`.tropo/schema/vault-index-schema.md`) is updated to include the new type in the controlled vocabulary

## Refs

- [Tropo Ledger Phase 1 Specification](../../vault/files/5eb5fd1f.md) — UID 5eb5fd1f
- [Vault Index Schema](../schema/vault-index-schema.md)
- [Tropo Work Architecture Specification](../../design/tropo-work-architecture.md) — UID 2d016ecf

---

*Capsule definitions index | Metis G38 + Mike Maziarz | April 10, 2026*
