---
uid: orientation
type: os-primitive
status: active
owner: tropo
tier: os
modified: '2026-06-27'
modified_by: argus-a120
---

# Tropo-OS — Harness Map (L2)

*Read **[the L1 canonical entry `eca73d77`](../vault/files/eca73d77.md)** first to understand what Tropo is and how it's built.*

*This file is L2: where to find things in the harness, plus pointers to the three agent-canonical capability catalogs. Read this section before taking any action in the vault. **If a capability exists, use it.** Do not improvise operations the harness already knows how to do correctly.*

*v1.15 rescope (Stream G, 2026-05-09): the previous narrative inventory of Actions / Skills / Playbooks / KB articles / sa.\* agents has been moved to three agent-canonical catalogs at the kernel layer. This file is now scoped to harness-map navigation: how to find things + where to look. The catalogs are the "what exists" surface.*

---

## How Discovery Works (One Home — v1.76)

Since One Home (ADR-045) + the truth-state split (ADR-047), **every governed thing lives in one indexed home and one lossless two-surface projection** — discovery is simple and truth-state is structural:

- **The current index (`vault/00-index.jsonl`) is the default spine.** Search it for current tools, skills, capsules, actions, playbooks, ADRs, and work items by `type`, `owner`, `status`, or `title`. `vault/00-archive-index.jsonl` is preserved history, reached deliberately with `tropo-vault-search.py "<query>" --include-archive`. Together they are complete; the default no longer carries the measured 37.9% archived/superseded noise floor.
- **Names are readable; the UID is the address.** Shipped OS components carry a clean `tropo-<name>` filename (e.g. `vault/tools/tropo-validate.py`); your own content is `<slug>-<uid>.md`. The presence/absence of the `tropo-` prefix tells you OS-owned vs. your content at a glance. Cross-references resolve by **UID**, so a rename never breaks a link.
- **The capability catalogs are the curated "what exists + when to reach for it" layer** (below), generated from the index. The **Toolbelt** ([`toolbelt.md`](toolbelt.md)) is the compact boot-known quick-reference over the same set.
- **Lenses on the same data:** relationships + structured frontmatter queries → `vault/00-index.sqlite` (edges, FTS, JSON fields); project hierarchy → `vault/00-project-tree.jsonl`. The old `00-graph-index.json` family is retired.

*If you can name what is currently true, search the current index. If you need history, opt in to the archive. If you want "what can I do here," read the catalogs. One home, one lossless partition, readable names.*

---

## Capability Catalogs — Read These First

| Catalog | Covers | Source |
|---|---|---|
| [Tropo Tool Catalog](tool-catalog.md) | Every kernel script + action surface (`type: tool`, `transport: cli/action/mcp/http/platform/sa`) | `vault/00-index.jsonl` filtered by type:tool + extraction_scope:ship |
| [Tropo Skill Catalog](skill-catalog.md) | Every kernel skill (`type: how-to` per canonical schema; "skill" is the user-facing label per Mike-A52 mirror-Claude-Code lock 2026-05-09) | `vault/00-index.jsonl` filtered by type:how-to + extraction_scope:ship (canonical files now at `vault/skills/tropo-<name>.md` per One Home) |
| [Tropo sa.\* Agent Catalog](sa-agent-catalog.md) | Every shipped session agent (`type: session-agent`) | `vault/00-index.jsonl` filtered by type:session-agent + extraction_scope:ship (files at `agents/sa/<name>/`) |

Each catalog entry includes its hand-authored `trigger_description:` — the agent-facing "when to reach for it" prose. The Tier 2 boot extension loads all three at Group 2; agents scan once at boot, dive into specific entries by UID when invoking.

**Re-generate when sources change:** `python3 vault/tools/tropo-generate-capability-catalogs.py --apply` (catalog generator [`d4e9a2c7`](../vault/files/d4e9a2c7.md)).

---

## Find Things

| What you need | How to find it |
|---|---|
| Any current governed artifact by type, status, owner, or title | Search `vault/00-index.jsonl` or run `python3 vault/tools/tropo-vault-search.py "<query>"` |
| Archived/superseded history | `python3 vault/tools/tropo-vault-search.py "<query>" --include-archive` (unions `vault/00-archive-index.jsonl`) |
| Relationships between artifacts | `vault/00-index.sqlite` — query `edges` by UID (the old graph-JSON family is retired) |
| Project hierarchy (all projects, parents, members) | `vault/00-project-tree.jsonl` |
| UID for a named project, task, or artifact | Commission `sa.metis-nav` (Metis-only) or `sa.project-tree` (any executive) — faster than scanning the index |
| All active projects browsable by name | `00-tropo-nav/00-tropo-active/` (rendered nav with composable graph; legacy `projects/` retired 2026-05-10 per Mike directive) |
| All pipeline definitions in the vault | Grep `vault/00-index.jsonl` for `type: pipeline` |
| All pipeline-runs (active or historical) | `vault/pipeline-runs/` (or `agents/<pipeline-name>/activations/` for in-tree pipelines like `dev-pipeline`) |
| Today's vault health | `shared/orientation/daily-health-report.md` |
| Substrate health check (one-gesture) | `npm test` (canonical; green/yellow/red verdict) OR `python3 vault/tools/tropo-test.py` (direct fallback for users without node installed). JSON mode via `npm run test:json` or `--json` flag; full validator output via `npm run test:verbose` or `--verbose` flag. Script at [`vault/tools/tropo-test.py`](../vault/tools/tropo-test.py); validator wrapped: [`vault/tools/tropo-validate.py`](../vault/tools/tropo-validate.py). v1.33.0 Stream H deliverable. |
| What capabilities the studio actually has + whether the tool chain runs | The capability regression test `vault/tools/tests/test_capability_chain_smoke.py` (rebuild + index-coverage + emit + build-release/archive + no-two-homes adversarial) — the One Home cold-boot proof |
| What capability exists for X | The three catalogs above. If unsure between tool / skill / sa.*, scan all three. |
| Delete a vault entry (one or many) | `python3 vault/tools/tropo-recycle.py <uid> [...]` — soft-delete to `recycle/agent-deletions/<YYYY-MM-DD>/`. **Never `rm` files in `vault/files/`.** Bash `grep -l \| xargs rm` patterns have deleted load-bearing substrate when keywords matched files describing the feature they named (v1.35.0 critical incident). Recovery from recycle is `mv` back. |

---

## Run Procedures — Playbooks

*Playbooks are multi-step governed workflows. Invoke when a process spans multiple actions or sessions.*

| Playbook | Purpose |
|---------|---------|
| `agent-boot` | Boot procedure for all executive agents |
| `agent-retire` | Retirement procedure — knowledge transfer, status close |
| `apply-update` | Apply a versioned OS update package to a vault |
| `cold-boot-test` | Verify a vault boots correctly from a cold start |
| `import-to-vault` | Migrate existing files into the Vault (batch) |
| `fleet-ops` | Check and dispatch scheduled operations agents |
| `new-hire-onboarding` | Reference playbook — multi-group onboarding workflow |
| `team-onboarding-day2` | Day 2 of team onboarding |

Location: canonical at `vault/playbooks/<uid>.md` (One Home); thin pointers remain at `.tropo/playbooks/` for the bootstrap-floor set (e.g. the agent-activation playbook the boot chain reads before the index is loaded). Studio-level playbooks: `playbooks/` (per-vault).

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

*Tropo-OS Harness Map (L2) | `.tropo/orientation.md` | v1.76 One Home refresh (2026-06-27, Argus A120): added §How Discovery Works (the index is the complete spine; tropo- names; the OS-vs-user boundary); repointed catalog sources to the index + the renamed generator/test tools (the deleted `.tropo/scripts/` shims); playbook canonical home → `vault/playbooks/`; `import-to-ledger`→`import-to-vault` vocab. | v1.15 Stream G rescope (2026-05-09) — narrative capability inventories moved to agent-canonical catalogs (`tool-catalog.md` + `skill-catalog.md` + `sa-agent-catalog.md`); this file scoped to harness-map navigation. Previous v1.11 Stream C restructure (conceptual content promoted to L1 entry [`eca73d77`](../vault/files/eca73d77.md)) preserved.*
*"If you know the harness, you can find anything. The catalogs tell you what exists."*
