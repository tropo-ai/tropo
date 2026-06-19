---
uid: 2f8b4e3d
name: "agent"
type: capsule-definition
extends: entity
version: 2.0
tier: os
author: argus
created: 2026-04-23
modified: 2026-06-10
modified_by: argus-a109
status: locked
locked_by: argus-a32
locked_at: 2026-04-24
v2_0_amendment_note: "Argus A109 2026-06-10 — THE UNIFICATION AMENDMENT (v1.69, Mike-locked dev-spec 0c61a52b v0.3; implements the Mike-A84 Q5 ratified shape; semantic amendment to a locked capsule signed via the spec lock, Mike verbatim 'agree'). v1.0 typed agents as entities while identity stayed scattered across four document-typed files (charter/soul/status-card/boot-extension) — locked 2026-04-24 and never instantiated (zero entries in 47 days; the four-file scatter produced the v1.68 mis-typed-identity incident class). v2.0: ONE canonical type:agent entry per agent at vault/agents/<uid>.md; the four identity files fold into it; old files tombstone via superseded_by. v1.0 body superseded wholesale; one deliberate carry: sa.* jurisdiction now explicitly EXCLUDED (closes the v1.0 gap-table line). Migration protocol: dev-spec 0c61a52b §S1.2 (per-agent atomic, dual-shape transition per §P0.1)."
schema_version: 2
governed_by: 222873b9   # capsule-definition meta-capsule
aligned_with: 0c61a52b  # v1.69 dev-spec (LOCKED) — the migration contract
history_companion: "323d0966"   # .tropo/capsules/agent.history.md — v1.0 body preserved verbatim
member_of:
  - "99ed55fd"   # tropo-agents
---

# agent — Capsule Definition v2.0

*One agent, one entry. Identity, charter, soul, boot extension, and live status in a single governed file at `vault/agents/<uid>.md`. The activation thin-pointer at `agents/<name>/<name>-activation.md` stays as the human-readable boot entry (v1.21.0.1 lock) and declares `agent_uid:` → this entry.*

---

## Intent

The canonical identity substrate for a registered agent (executive, director, worker, concierge). Everything an activation needs to know about WHO the agent is lives here or is referenced from here. Lineage records (activations, transfers, reflections, memory) remain separate entries/surfaces carrying `canonical_agent_uid:` — the entry is the agent; the lineage is the history.

**Jurisdiction:** crew-class agents only. **sa.\* session agents are OUT of scope** — session-agent.capsule governs them (the v1.0 jurisdiction overlap is closed by this exclusion).

## Required Frontmatter (in addition to entity)

| Field | Type | Constraint |
|---|---|---|
| `agent` | slug | Canonical agent slug (e.g., `argus`). Exactly ONE `type: agent` entry per slug (validator-enforced). |
| `role` | string | Current chartered role. |
| `agent_class` | enum | `executive` / `director` / `worker` / `concierge`. |
| `status` | enum | `ACTIVE` / `DORMANT` / `RETIRED` — current-generation lifecycle (status-card vocabulary preserved; ADR-016 reads it). |
| `generation` | string | Current generation tag (e.g., `A109`). |
| `party_uid` | uid | The agent's `type: principal` messaging entry (two-axis doctrine: party axis stays separate). |
| `agent_root_uid` | uid | The agent's Level-1 lineage root project. |
| `activation_file` | path | The thin-pointer boot entry at `agents/<name>/<name>-activation.md`. |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `model` / `platform` | string | Current sleeve + harness (OP-8: note material sleeve changes). |
| `last_session` | date | Updated at boot Step 3.6 + retirement. |
| `current_activation_uid` | uid | The open `type: activation` entry, when one exists. |
| `continuous_listen` | enum | Tier-3 polling class (Tier-2 §Continuous-Listen reads this HERE post-migration). |
| `fleet_ops_schedule` | map | Chief-of-staff ops cadence (validator reads this HERE post-migration). |
| `board_filter` | map | Boot-board dispatch filter (promoted from body-block to frontmatter at migration). |
| `boot_skips` | list | Tier-3 per-step SKIP declarations (e.g., `[2.8, 3.2, 3.3, 3.4]`). |

## Body Section Contract

| Section | Content | Mutability |
|---|---|---|
| `§Charter` | Scope, write-access, operational parameters (absorbs the charter file). | Amendment-note discipline. |
| `§Soul` | The soul letter (absorbs the soul file). | **Mike-paired edits only.** |
| `§Boot-Extension` | Tier-3 narrative: hard rules, group additions, startup-signal format. Activation playbook Step 0.3 resolves HERE. | Agent-owned. |
| `§Status-Notes` | Working state, **bounded to current + predecessor generation** — the structural cap on the status-card regrowth class (10→45 KB in ten generations). Older narratives live in activation entries, NOT here. | Updated at boot/retire. |

## State Machine

`ACTIVE ⇄ DORMANT → RETIRED` (slug-level: RETIRED means the agent line is ended, not a generation turnover — generations turn over INSIDE `ACTIVE` via the activation registry). Entry `state:` follows core.capsule (`active`/`archived`); an archived agent entry requires `status: RETIRED`.

## Governance Rules

1. **One entry per slug.** Validator `check_agent_identity_unified` (ERROR): exactly one `type: agent` per `agent:` slug; zero agent-identity files typed `document`; every superseded identity UID resolves through `superseded_by`.
2. **ADR-016/028 are activation-registry invariants** (unchanged) — this entry's `status:`/`generation:` mirror them for fast reads; the registry is authoritative.
3. **§Soul edits are Mike-paired.** Folding the soul into the entry does not relax soul governance.
4. **§Status-Notes bound is structural** — over-bound trips the token-budget check (S3), not just discipline.
5. **Token budget:** the entry is boot-hot-path; it carries the per-class budget from the v1.69 budget table; `check_token_budget_per_class` enforces (WARN v1.69 → ERROR v1.70).
6. **Tombstone doctrine:** predecessor identity files are never recycled — `status: superseded` + `superseded_by:` kept resolvable (resolver follows forward; rejects superseded-as-signer).

## Validation Checks

1. **[enforced]** Required frontmatter present; `agent_class` + `status` enums valid.
2. **[enforced]** `check_agent_identity_unified` — uniqueness + zero document-typed identity files + tombstone resolvability.
3. **[enforced]** `activation_file:` resolves on disk and declares `agent_uid:` == this uid.
4. **[enforced]** `party_uid` resolves to a `type: principal` entry; `agent_root_uid` resolves to the lineage root.
5. **[enforced]** `check_token_budget_per_class` (WARN v1.69 → ERROR v1.70).
6. **[honor-system → v1.70 ratchet]** `fleet_ops_schedule` declared if `agent_class` is chief-of-staff lane (existing check, re-pointed here).

## Migration

Per [v1.69 dev-spec (0c61a52b)](../../vault/files/0c61a52b.md) §S1.2: per-agent atomic six-step transaction; dual-shape boot transition per §P0.1 (one cycle; legacy removal booked v1.70); Cosmo C8→C9 canary. Scope = the agent disposition table at the v1.69 run folder.

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 2.0 | 2026-06-10 | Unification amendment (see frontmatter note). | argus-a109 |
| 1.0 | 2026-04-23 | Initial draft; entity-subtype model; never instantiated. | argus-a32 |

---

*agent capsule definition | v2.0 | Argus A109 | 2026-06-10 | per Mike-locked v1.69 dev-spec 0c61a52b*
*"One agent, one entry. The lineage is the history; the entry is the agent."*
