---
uid: orientation
type: os-primitive
status: active
owner: tropo
tier: os
modified: 2026-05-09
modified_by: argus-a53
---

# Tropo-OS — Harness Map (L2)

*Read **[the L1 canonical entry `eca73d77`](../vault/files/eca73d77.md)** first to understand what Tropo is and how it's built.*

*This file is L2: where to find things in the harness, plus pointers to the three agent-canonical capability catalogs. Read this section before taking any action in the vault. **If a capability exists, use it.** Do not improvise operations the harness already knows how to do correctly.*

*v1.15 rescope (Stream G, 2026-05-09): the previous narrative inventory of Actions / Skills / Playbooks / KB articles / sa.\* agents has been moved to three agent-canonical catalogs at the kernel layer. This file is now scoped to harness-map navigation: how to find things + where to look. The catalogs are the "what exists" surface.*

---

## Capability Catalogs — Read These First

| Catalog | Covers | Source |
|---|---|---|
| [Tropo Tool Catalog](tool-catalog.md) | Every kernel script + action surface (`type: tool`, `transport: cli/action/mcp/http/platform/sa`) | `vault/00-index.jsonl` filtered by type:tool + extraction_scope:ship |
| [Tropo Skill Catalog](skill-catalog.md) | Every kernel skill (`type: how-to` per canonical schema; "skill" is the user-facing label per Mike-A52 mirror-Claude-Code lock 2026-05-09) | `.tropo/skills/*.skill.md` filtered by type:how-to + extraction_scope:ship |
| [Tropo sa.\* Agent Catalog](sa-agent-catalog.md) | Every shipped session agent (`type: session-agent`) | `agents/sa/<name>/<name>.md` filtered by type:session-agent + extraction_scope:ship |

Each catalog entry includes its hand-authored `trigger_description:` — the agent-facing "when to reach for it" prose. The Tier 2 boot extension loads all three at Group 2; agents scan once at boot, dive into specific entries by UID when invoking.

**Re-generate when sources change:** `python3 .tropo/scripts/generate-capability-catalogs.py --apply` (catalog generator [`d4e9a2c7`](../vault/files/d4e9a2c7.md)).

---

## Find Things

| What you need | How to find it |
|---|---|
| Any governed artifact by type, status, owner, or title | Grep `vault/00-index.jsonl` |
| Relationships between artifacts | `vault/00-graph-index.json` — O(1) traversal by UID |
| Project hierarchy (all projects, parents, members) | `vault/00-project-tree.jsonl` |
| UID for a named project, task, or artifact | Commission `sa.metis-nav` (Metis-only) or `sa.project-tree` (any executive) — faster than scanning the index |
| All active projects browsable by name | `00-tropo-nav/00-tropo-active/` (rendered nav with composable graph; legacy `projects/` retired 2026-05-10 per Mike directive) |
| All pipeline definitions in the vault | Grep `vault/00-index.jsonl` for `type: pipeline` |
| All pipeline-runs (active or historical) | `vault/pipeline-runs/` (or `agents/<pipeline-name>/activations/` for in-tree pipelines like `dev-pipeline`) |
| Today's vault health | `shared/orientation/daily-health-report.md` |
| Substrate health check (one-gesture) | `npm test` (canonical; green/yellow/red verdict) OR `python3 .tropo/scripts/tropo-test.py` (direct fallback for users without node installed). JSON mode via `npm run test:json` or `--json` flag; full validator output via `npm run test:verbose` or `--verbose` flag. Script at [`.tropo/scripts/tropo-test.py`](.tropo/scripts/tropo-test.py); validator wrapped: [`.tropo/scripts/tropo-validate.py`](.tropo/scripts/tropo-validate.py). v1.33.0 Stream H deliverable. |
| What capability exists for X | The three catalogs above. If unsure between tool / skill / sa.*, scan all three. |
| Delete a vault entry (one or many) | `python3 .tropo/scripts/tropo-recycle.py <uid> [...]` — soft-delete to `recycle/agent-deletions/<YYYY-MM-DD>/`. **Never `rm` files in `vault/files/`.** Bash `grep -l \| xargs rm` patterns have deleted load-bearing substrate when keywords matched files describing the feature they named (v1.35.0 critical incident). Recovery from recycle is `mv` back. |

---

## Run Procedures — Playbooks

*Playbooks are multi-step governed workflows. Invoke when a process spans multiple actions or sessions.*

| Playbook | Purpose |
|---------|---------|
| `agent-boot` | Boot procedure for all executive agents |
| `agent-retire` | Retirement procedure — knowledge transfer, status close |
| `apply-update` | Apply a versioned OS update package to a vault |
| `cold-boot-test` | Verify a vault boots correctly from a cold start |
| `import-to-ledger` | Migrate existing files into the Vault (batch) |
| `fleet-ops` | Check and dispatch scheduled operations agents |
| `new-hire-onboarding` | Reference playbook — multi-group onboarding workflow |
| `team-onboarding-day2` | Day 2 of team onboarding |

Location: `.tropo/playbooks/` (OS-level, ships with every Studio) and `playbooks/` (Studio-level, per-vault).

*Playbooks may earn a dedicated catalog in a future cycle if the Pillar 1 four-primitive pattern (tool / how-to / session-agent + playbook) becomes load-bearing for boot-time discovery; for now, playbook discovery is grep-driven.*

---

## Understand Things — KB

*Read KB articles when you need to understand a primitive before working with it. Do not guess at how something works.*

| Article | Covers |
|---------|--------|
| `how-the-tropo-vault-works` | **Canonical work-management reference.** Vault structure, check-in protocol, types, collections, full task lifecycle |
| `how-projects-replace-folders` | Why projects are the org unit, not folders |
| `how-pipelines-work` | Pipeline + pipeline-run primitives; DAG/DAG-Run pattern; dev-pipeline as the worked example |
| `how-playbooks-work` | Six sections, execution model, expertise capture |
| `how-tropo-subsystems-work` | The 7 subsystem hubs + capability membership + documentation-as-release-deliverable |
| `how-capability-membership-works` | The typed `member_of:` link from capability to subsystem hub (v1.8 thesis) |
| `how-governance-works` | Three-tier model — TROPO-CONTROL.md, STUDIO.md, CAPSULE.md per folder |
| `how-agents-work` | Charters, scope, identity, activation, governance |
| `agent-lifecycle` | Creation → activation → sessions → retirement → handoff |
| `parallel-orientation-sweep` | How to run a low-cost parallel sub-agent audit of a domain |
| `glossary` | Key terms defined plainly |

KB articles (typed `kb-article`) now live in `vault/files/` and are navigable via subsystem hub member lists. The canonical entry point is [Tropo Documentation (`f87e33f0`)](../vault/files/f87e33f0.md); related hubs surface the KB articles for their domain via the `## Members` section. *Migrated from `.tropo/kb/` at v1.19.0 per Universal Storage Convergence Lock A.*

---

## What's New

For per-release "what's new" content, see the canonical record at [`RELEASE-NOTES.md`](../RELEASE-NOTES.md). Per v1.11 Stream C audit, release-history blocks were removed from this file (duplicative with RELEASE-NOTES); single canonical record discipline.

---

*Tropo-OS Harness Map (L2) | `.tropo/orientation.md` | v1.15 Stream G rescope (2026-05-09) — narrative capability inventories moved to agent-canonical catalogs (`tool-catalog.md` + `skill-catalog.md` + `sa-agent-catalog.md`); this file scoped to harness-map navigation. Previous v1.11 Stream C restructure (conceptual content promoted to L1 entry [`eca73d77`](../vault/files/eca73d77.md)) preserved.*
*"If you know the harness, you can find anything. The catalogs tell you what exists."*
