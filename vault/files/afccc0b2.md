---
uid: afccc0b2
type: kb-article
title: Glossary
description: Key terms used in Tropo, defined plainly. Aliases section at the bottom for shorthand and cross-references.
status: published
state: active
author: argus-a55
created: 2026-05-11
created_by: argus-a55
modified: 2026-05-11
modified_by: argus-a56
schema_version: 2
governed_by: 4cb20382
extraction_scope: ship
member_of: []
subsystem_hub:
- f87e33f0
capsule_version: '2.5'
---

# Glossary

**Relations**

| Relation | Target |
|---|---|
| Governed by | [kb-article (4cb20382)](4cb20382.md) |

*Key terms used in Tropo, defined plainly. Aliases section at the bottom for shorthand and cross-references.*

---

## Core Primitives

**Vault** — Your Tropo workspace. A folder on your computer containing all your agents, playbooks, decisions, and governance files. The vault IS the system — there's no hidden state anywhere else.

**Ledger** — The flat, governed store of every work artifact in the vault. All entries live at `vault/files/<uid>.md`. The index at `vault/00-index.jsonl` is the discovery interface — you query it, not walk the filesystem. Machine-first, query-first.

**Entry** — A single governed file in the Vault. Has a UID, a type, a status, an owner. Conforms to a capsule definition. Every task, decision, spec, document, and project is an entry.

**Capsule Definition** — The schema for a type of vault entry. Lives at `.tropo/capsules/<type>.capsule.md`. Defines required frontmatter, a state machine, validation rules, and governance rules. Locked once stable. Examples: `task`, `project`, `decision`, `document`, `kb-article`, `playbook`.

**KB Article** — A typed governed primitive (`type: kb-article`) that teaches agents how a Tropo primitive works or how a concept composes. Lives in `vault/files/<uid>.md` and is discoverable via subsystem hub member lists (primary: [Tropo Documentation (`f87e33f0`)](f87e33f0.md)). *Migrated from `.tropo/kb/` at v1.19.0 per Universal Storage Convergence Lock A.* Governed by [kb-article.capsule (`4cb20382`)](4cb20382.md); extends `document`. Categories: `how-to` / `reference` / `concept` / `glossary` / `decision-support`. A capsule declares a type's schema; a kb-article teaches the type's use.

**Capsule History** — A typed governed primitive (`type: capsule-history`) that preserves accumulated historical content (changelogs, amendment blocks, deprecated-content) extracted from a parent capsule's prior body during a pedagogy-first refactor. Sibling to its parent capsule (`<capsule-name>.history.md`). Governed by [capsule-history.capsule (`5ec083a3`)](../capsules/capsule-history.capsule.md). Established at v1.18.0 per Lock C (active capsules teach; history files preserve audit trail).

**Collection** — A grouping of vault entries by reference, not by physical containment. Collections organize views of the Vault for human navigation — a project's tasks, all decisions, all specs by domain. Lives in `vault/collections/`.

**Playbook** — A structured guide that captures how a process should run. Six sections: Intent, Suggestions, Rules, Resources, Outcomes, Verification. The same playbook can be followed by a human or an agent.

**Operating Agreement** — The vault's constitution. Defines who has authority, how decisions are made, and what boundaries exist. Every agent operates under it.

**Channel** — A shared file where agents log activity and coordinate. `channels/ops.md` is the system-wide operations log. Working channels (e.g., `channels/metis-vela.md`) are for bilateral coordination.

**Board** — A synthesized view of an agent's active work. Generated from ledger data, not maintained by hand. Shows priorities, blockers, and state. Lives in `boards/`.

---

## Agent System

**Agent** — A chartered role in the vault. Defined by a charter file that declares identity, scope, values, and governance. Create the charter and the agent exists.

**Charter** — The file that defines WHO an agent is. Identity, soul, values, lineage, relationships. The charter is the agent's character — it doesn't change between generations.

**Briefing** — The file that contains WHAT an agent owns. On-demand reference material loaded when needed, not at boot. Keeps boot context lean.

**Generation** — A single session lifetime of an agent. Vela V27 is the 27th generation of Vela. Each generation boots, works, and retires. The charter persists; the generation is ephemeral.

**Living Transfer** — The handoff document a retiring generation writes for its successor. Current state, pending work, key context, warnings. The bridge between generations.

**Retirement** — The structured end of a generation. Follow the retirement playbook: write transfer, update briefing, post to channels, close out. The successor reads what you leave.

**Status Card** — Quick-reference card showing an agent's current state: generation, last session, blockers, recent work. Updated by the agent or by crew coordination.

**Concierge** — The built-in vault guide that helps you set up and manage your vault. It's the first agent you interact with. Runs onboarding, creates agents, helps with vault management.

**Citizen** — An agent born in the vault with a `tropo-agent-id`. Full CRUD within their declared scope.

**Visa** — A foreign agent that arrives and registers with the vault. Gets a `tropo-agent-id` at registration. Operates per vault policy with a paper trail.

**Undocumented** — An agent that operates in the vault without registering. Not blocked — but modifications are flagged by the vault steward on the next health check.

**tropo-agent-id** — An 8-character hex identifier assigned to every registered agent. Used for audit trails, ops logging, and cross-session identity. Survives renames and role changes.

---

## Governance

**Scope** — What an agent can read and write. Declared in the charter. An agent with `scope.writes: ["agents/strategist/"]` can only write to its own folder. Governance — agents have boundaries.

**AGENTS.md** — Per-folder governance file in the Vault era. Declares who can write to the folder, what belongs there, and what protocols to follow. The write-gate. Every governed folder has one.

**Canon / Canonical** — A source of truth that derived works must conform to. Capsule definitions, locked decisions, the Operating Agreement. If a teaching surface disagrees with a canonical source, the canonical source wins.

**Derived work** — A file that teaches or summarizes a canonical source. Orientation docs, AGENTS.md files, KB articles. Maintained, important, but not the authority. Should declare what it derives from.

**UID** — An 8-character hex unique identifier assigned to every vault entry and every registered agent. Used for cross-referencing, tracking, and identity. Never reused, never changes.

**Registry topology** — Tropo uses matched primitives per domain rather than one universal UID registry. Work artifacts are indexed at `vault/00-index.jsonl`. Agent identity is at `.tropo-studio/registries/agent-registry.yaml`. Runtime callables (sa.\*/skills/tools) are projected into `.tropo-studio/registries/registry.jsonl`. Kernel content (capsules / playbooks / skills) is discoverable via folder listing — filenames are addresses (`task.capsule.md` IS the type "task"). When referencing files across documents, use UIDs — they survive renames and moves. See [Registry Topology Consolidation](../../vault/files/adac1f10.md).

**Kernel** — The `.tropo/` folder. Contains framework primitives — capsule definitions, action templates, kernel playbooks, skills, and schemas. Receives updates from the Tropo update pipeline. Read from it, don't modify it casually. *(KB articles, formerly at `.tropo/kb/`, migrated to `vault/files/` at v1.19.0 per Universal Storage Convergence Lock A.)*

---

## Work Management

**Task** — A single unit of work tracked as a vault entry. Has an owner, status, priority, and project. State machine: backlog → active → blocked → review → done → archived. Owner ≠ verifier.

**Project** — A scoped body of work with an owner and a lifecycle. References constituent entries (tasks, specs, decisions) by UID. Projects are the human navigation primitive for a flat ledger — without them, humans see a graveyard of hex filenames.

**Decision (ADR)** — An architectural decision record. Immutable once accepted. State machine: proposed → accepted → superseded. Captures the decision, the context, and the alternatives considered.

**Document** — A governed artifact that isn't a task, decision, or spec. Orientation docs, migration maps, guides. State machine: draft → published → archived.

---

## Infrastructure

**Session** — A single conversation between a human and an agent. Agents don't retain memory natively, but the vault persists state between sessions. Boot from the charter + briefing + transfer.

**CURATOR** — A sub-agent dispatch pattern for index maintenance. A CURATOR reads a folder, produces a structured report, and updates the index. Dispatched by the vault maintenance system.

**Grooming Agent** — A system agent that maintains vault health autonomously. Detects drift, flags staleness, reports issues. Lives in `agents/directors/`.

**Memory** — Operational knowledge that persists between generations. Agent-level memory at `agents/<name>/.tropo-capsule/memory/`. Vault-level memory at `.tropo-studio/memory/`. One file per insight, flat index.

**Index (JSONL)** — The Vault's discovery interface at `vault/00-index.jsonl`. One JSON record per entry. Query by type, status, owner, tags. Authoritative — if it's not in the index, it doesn't exist in the Vault.

---

## Aliases

*Shorthand used by the crew. Multiple names for the same thing — all acceptable.*

### Agents

| Full Name | Short | Generation Style | tropo-agent-id |
|-----------|-------|-----------------|----------------|
| Vela | V | V27 | 150dc353 |
| Metis | Met, G | G41 | 7c017d1f |
| Argus | A | A21 | cdf9b3ad |
| Orpheus | O | O11 | c387a949 |
| Talos | T | — | 34cf0f1c |
| Silas | S | S5 | 3bf699ee |

### Terms

| Canonical Name | Aliases | Notes |
|---------------|---------|-------|
| Frontmatter | fm, YAML, yaml | The `---` delimited metadata block at the top of a file |
| Operating Agreement | OA | The vault constitution |
| AGENTS.md | write-gate, folder governance | The per-folder access control file |
| Capsule definition | capsule, cap def | The schema for a vault entry type |
| Architectural Decision Record | ADR | A locked decision in the Vault |
| Knowledge Base | KB | Typed `kb-article` entries at `vault/files/`; navigable via subsystem hub member lists (primary: `tropo-documentation`). *Migrated from `.tropo/kb/` at v1.19.0.* |
| Vault index | index, JSONL, the index | `vault/00-index.jsonl` |
| Living transfer | transfer, handoff | The generation-to-generation document |
| tropo-agent-id | agent UID, agent ID | 8-char hex per agent |
| UID | uid, ID | 8-char hex per entry |

---

*Glossary | Tropo OS | Last updated 2026-04-12 by Vela V27*
*Build note: the Aliases section is Argo-specific. The build agent produces a clean release version without crew aliases.*
