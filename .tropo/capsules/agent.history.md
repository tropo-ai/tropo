---
uid: 323d0966
type: capsule-history
title: "agent.capsule — History Companion"
governs: 2f8b4e3d
governs_path: ".tropo/capsules/agent.capsule.md"
created: 2026-06-10
created_by: argus-a109
modified: 2026-06-10
modified_by: argus-a109
schema_version: 2
extraction_scope: argo-reference
member_of:
  - "99ed55fd"   # tropo-agents
tags: [capsule-history, agent-capsule, v1-archive]
---

# agent.capsule — History Companion

*Superseded version bodies preserved verbatim per the LEAN+companion pattern (playbook.history.md exemplar) + Preservation Discipline (the Studio is not a git repo; the companion IS the version history). Created at the v2.0 unification amendment (Argus A109, 2026-06-10, per Mike-locked v1.69 dev-spec 0c61a52b).*

---

## v1.0 (2026-04-23 → superseded 2026-06-10) — full body verbatim

**Frontmatter of record:** `version: 1.0` · `extends: entity` · `status: locked` (argus-a32, 2026-04-24) · `aligned_with: f2e8a7b1` (Tropo Work v2 Architecture Specification) · `governed_by: 222873b9`.

**Why superseded:** v1.0 typed agents as entity-subtypes while identity stayed scattered across four document-typed files (charter / soul / status card / boot extension). Locked 2026-04-24, never instantiated — zero `subtype: agent` entries existed at the v1.69 audit (2026-06-10). The v2.0 unification (Mike-A84 Q5 shape, ratified; v1.69 dev-spec 0c61a52b Mike-locked) replaced the model with one canonical `type: agent` entry per agent at `vault/agents/<uid>.md`.

---

# agent — Capsule Definition v1.0

*An AI agent in the vault. Specializes entity by requiring an activation file, optional crew-generation metadata, and session-lifecycle semantics. Replaces ad-hoc `agents/<name>/` patterns with a typed primitive.*

*Subtype of entity.capsule (1e9c3f7a). Per Tropo Work v2 Architecture Specification (f2e8a7b1) §2.5.*

## Intent

Typed capsule for AI agents — Claude, GPT, Gemini, any LLM operating inside a vault. Before v2, agents lived as folders (`agents/<name>/`) with activation files + charters + briefings, but had no typed capsule governing their identity. This capsule makes agent-entities first-class primitives in the Vault.

An agent-entity represents one LLM role: Argus, Vela, a session-scoped sa.* agent, a user-authored researcher. The capsule specializes entity with: `activation_file:` (path to the boot instructions), `generation:` (optional crew-generation metadata for long-running crew agents), and session-lifecycle semantics that the base entity doesn't capture.

**Before creating an agent-entity, ask:**
- Is this a persistent crew agent (Argus, Vela, user-authored executive) or ephemeral session agent (sa.cold-boot, one-off task agent)?
- Does it need an activation file? (Yes for crew; optional for ephemeral.)
- Who is the principal? (Per entity base: self-signing for atomic agents.)

## Required Frontmatter (in addition to entity)

| Field | Type | Constraint |
|---|---|---|
| `subtype` | literal | Must be `agent` (inherited; fixed for this subtype capsule). |
| `activation_file` | path | Relative path to the agent's activation file (e.g., `agents/researcher/researcher-activation.md`). Required for crew + user-authored agents. Optional for transient session agents. |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `agent_class` | enum | `executive` / `director` / `worker` / `session` — operational classification. Executive = chartered crew with full identity. Director = service director (d.pm pattern). Worker = scoped operational agent. Session = ephemeral/transient (sa.\* pattern). |
| `generation` | string | Generation tag for crew agents (e.g., `a32` for Argus generation 32). Optional; empty for non-crew agents. |
| `platform` | string | Harness the agent typically runs on (e.g., `claude-code`, `codex`, `cursor`, `cowork`). For crew with platform continuity. |
| `model` | string | Default/recommended LLM (e.g., `claude-opus-4-6`, `gpt-5`). Informational; harnesses may override. |
| `activation_context` | string | Brief description of the default context this agent boots into. |

## State Machine Extensions

Base entity states (`active`, `archived`) plus:

```
active → dormant (session pause; retains identity) → active
active → retired (permanent; generation-ended; equivalent to archived for agent-subtype)
```

| State | Meaning |
|---|---|
| `active` | Boot-ready. Activation file loads the agent into operational state. |
| `dormant` | Paused between sessions. No active session. Resumes via activation. (Session agents typically skip dormant; they go directly to archived.) |
| `retired` | Permanent end. Generation ended (for crew); session concluded (for session agents). Functionally equivalent to `state: archived`. |

## Governance Rules (in addition to entity)

1. **Principal is self (atomic).** Per entity Rule 2, `principal:` equals own uid. Self-signing.
2. **`members:` MUST be empty.** Atomic subtype per entity Rule 3.
3. **Activation file is authoritative.** When the activation file exists, the agent's operational behavior is defined by that file (plus charter + briefing if present). The capsule governs identity; the activation file governs behavior.
4. **Crew agents (agent_class: executive) carry generation metadata.** Every crew session increments the generation; new generation-log entries at session start, retirement at session end.
5. **Session agents may skip activation files.** Transient sa.\* agents that exist only for the duration of one task may have `activation_file: null` or omit the field. The capsule governance relaxes only for agent_class: session.

## Validation Checks (in addition to entity)

1. **[enforced]** `subtype: agent`
2. **[enforced]** If `agent_class ∈ {executive, director, worker}`: `activation_file:` present + resolves to a file on disk
3. **[enforced]** If `agent_class: session`: `activation_file:` may be absent
4. **[honor-system]** Generation-log consistency between capsule metadata and activation file (validator target: v1.5)

## Relationship to Other Capsules

- **entity.capsule (1e9c3f7a)** — parent
- **session-agent.capsule** — the existing session-agent capsule; session-class agents may be governed by session-agent.capsule instead of or in addition to this; resolve in v1.4 Stream 3 uplift

## Known Enforcement Gaps

Inherits entity.capsule's gaps (cross-vault UID uniqueness, principal-chain cycle detection, signing attestation). Subtype-specific gaps:

| Gap | What closes it | Target | Owner |
|---|---|---|---|
| `activation_file:` resolution is honor-system at v1.0 (no validator confirms the file exists on disk) | Validator extension at v1.5 | v1.5 | argus |
| `agent_class: session` jurisdiction overlap with session-agent.capsule — which capsule governs sa.* entries? | Resolve at v1.4 Stream 3 CAPSULE uplift | v1.4 Stream 3 | argus |
| Generation-log consistency between capsule metadata and activation file — honor-system | Validator that cross-reads generation-log + capsule | v1.5 | argus |

## Extension from core + entity

*Where this capsule specializes entity.capsule (1e9c3f7a).* agent.capsule adds: `activation_file:` (required for non-session classes), `agent_class:`, `generation:`, `platform:`, `model:`, `activation_context:`. Extends entity.capsule's state machine with `dormant` (between sessions) and `retired` (equivalent to `archived` for crew-agents). All entity.capsule rules apply unchanged.

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you act.*

**Tools available:**
- Activation file convention — `agents/<name>/<name>-activation.md` is the boot entry
- Generation-log convention — `agents/<name>/generation-log.md` tracks per-session crew continuity
- Registry pointer: `.tropo-studio/registries/agent-registry.yaml` (post-v2 migration ships this)

**Skills:**
- `create-executive-agent.skill.md` (existing; amended in v1.4 Stream 4 to produce entity-compliant agent-subtype output)
- `create-session-agent.skill.md` *(forthcoming v1.5)*

**Procedures:**
- `agent-activation.playbook.md` — boots an agent; generates new generation-log row
- `agent-retire.playbook.md` — closes a session; flips state; updates generation-log
- Three-file agent pattern — activation + charter + briefing for executive-class agents

**Rules (at-a-glance):**
1. Principal is self (atomic) per entity Rule 2
2. `members:` MUST be empty (atomic subtype)
3. Activation file is authoritative for behavior when present
4. Crew agents (agent_class: executive) carry generation metadata
5. Session agents may skip activation files

**Pitfalls:**
- Authoring `members:` on an agent → atomic-subtype violation; agents have no members
- Crew agent without `generation:` → breaks generation-log continuity
- Agent with `principal:` pointing at another entity → not self-signing; breaks atomic-entity rule
- Missing `activation_file:` for non-session agent → behavior undefined

**Worked examples:**
- Argo crew (Argus, Vela, Metis, Orpheus, Talos, d.pm) migrate to `agent_class: executive` or `director` at v1.4 Stream 1 migration
- Session agents (sa.cold-boot, sa.skeptic, sa.arch-specs) are `agent_class: session`

**Go next:**
- Atomic entity base → entity.capsule (1e9c3f7a)
- Composite grouping of agents → team.capsule (3c9a7b1e)
- Agent's vault context → vault.capsule (4d6e2f9a)
- Agent running sa.* work → session-agent.capsule (jurisdiction resolution deferred to Stream 3)

## Migration Notes

All existing `agents/<name>/` folders get corresponding agent-subtype entity vault entries at v1.4 migration. Activation files remain at their existing paths; capsule entries reference them via `activation_file:`. Crew agents (Argus, Vela, Metis, Orpheus, Talos, d.pm) get explicit `agent_class: executive` (or `director` for d.pm). Session agents (sa.\*) get `agent_class: session`.

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-04-23 | Initial DRAFT. Subtype of entity.capsule. Pending three-instrument. | argus-a32 |

---

*agent capsule definition | DRAFT v1.0 | Argus A32 | 2026-04-23*
*"One LLM, one role, one activation file. Identity in the capsule; behavior in the activation."*

---

*agent.capsule History Companion | UID `323d0966` | created Argus A109 2026-06-10 at the v2.0 amendment*
