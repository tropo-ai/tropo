---
uid: 8f3c9e1a
name: "charter"
type: capsule-definition
extends: core
version: "1.0.3"
supersedes_version: "1.0.2"
v1_0_3_amendment_note: "v1.0.2 → v1.0.3 amendment 2026-06-07 by Argus A103 per Mike-A103 signed lock-break ('approved'). ADDITIVE + NON-BREAKING: adds the OPTIONAL §3 frontmatter field `user_facing` (boolean; opt-in; absent/false = internal-only default, so every existing charter stays valid). Semantics: `user_facing: true` marks an agent surfaced/summonable in the L2 user-facing harness (the Tropo Work agent picker). Introduced by Metis-G73 (A2; first use on Po 194c4935, flagged for ratification); ratified here. ZERO change to required fields, body schema, lock semantics, or validator required-field checks — purely an optional-field addition."
v1_0_1_anchor: "R4 cold-boot synthetic-persona absorption (sa.cold-boot-195 by argus-a69 2026-05-17 captain-mode; verdict PASS; 0 P0 + 5 P1 + 3 P2 + 1 RC). Pedagogical-gap absorbs per persona's Nestor charter authoring walk: P1-1 boot_protocol on-demand vs playbook disambiguation (executive default = playbook); P1-2 scope path-shape examples (folder paths / file globs / capsule UIDs); P1-3 uid assignment convention (author-assigned 8-hex; verify via grep vault/00-index.jsonl); P1-4 §3/§6 locked_at/locked_by tension (optional pre-LOCK; required post-LOCK); P1-5 channels path convention (channels/<agent>-<peer>.md); P2-1 created_by/modified_by string format (agent-slug-generation); P2-2 on-disk path convention (vault/files/<uid>.md in §1); P2-3 member_of in §3 optional list. RC-1 (meta-capsule layering boundary — capsule's own frontmatter vs charter-instance frontmatter) deferred to future-cycle Path 2 candidate. All 8 absorption edits are pedagogical clarifications; ZERO change to architectural contracts (frontmatter schema + body schema + validator checks + lock semantics + scope all unchanged). Capsule remains spec-conformant + validator-compatible."
tier: os
author: argus
created: 2026-05-17
modified: 2026-06-07
created_by: argus-a69
modified_by: argus-a103
status: locked
locked_by: argus-a69
locked_at: 2026-05-17
enforced_enums:
  status: [active, locked, retired, archived, suspended, superseded]
meta_status_rollup:
  in-progress: [active]
  done: [locked, retired, archived, suspended, superseded]
locked_signoff: "Mike-A69 verbatim 'yes, proceed' 2026-05-17 — atomic LOCK with spec [e3f47a82] v0.2 + release-plan [f9c4a283] v0.1 + Stream A [7d28b6a1] v0.1; capsule shipped at v1.37.0 closing v1.23.0 sa.skeptic-039 governance carry-forward. R4 absorption v1.0 → v1.0.1 by argus-a69 captain-mode 2026-05-17 — pedagogical clarifications only; no architectural-contract changes; LOCK signoff carries forward."
ships_in_v: "1.37.0"
schema_version: 2
governed_by: 222873b9   # capsule-definition meta-capsule
basis_spec: e3f47a82     # v1.37.0 design spec (architectural contracts §3.1-§3.7)
pattern_exemplar: b4e2a718   # session-agent.capsule v1.5 — parallel typed primitive for ephemeral agents
aligned_with:
  - "e6c3f410"   # ADR-032 — Three-Layer Boot Configuration Model
  - "4e8b21f0"   # activation.capsule v1.0.3 — uses agent_class field
composes_with:
  - "b4e2a718"   # session-agent.capsule v1.5 — sa.* type contract (charter does NOT cover sa.*)
  - "e863a1e0"   # sa/CAPSULE.md — commissioning protocol (composes via boot_protocol: commissioned for directors)
member_of:
  - "99ed55fd"   # tropo-agents (charter is identity substrate for charter-bearing agents)
  - "8dd772a0"   # tropo-governance (charter is governance substrate per v1.37.0 cycle frame)
tags: [capsule-definition, charter, pillar-1, governance-substrate, executive-and-director, v1.37.0-ships, more-capsules-equals-more-maintenance-pin]
extraction_scope: ship
---

# charter — Capsule Definition v1.0

*The capsule definition for charter-bearing agents (executive + director). Closes the v1.23.0 sa.skeptic-039 governance carry-forward: charters were implicit-typed-as-document; v1.37.0 formalizes `type: charter` as a first-class governance capsule. Sa.* agents continue using session-agent.capsule v1.5 per spec §3.6 single-capsule scope (more-capsules-equals-more-maintenance pin Mike-A69 2026-05-17).*

---

## 1. Purpose

A **charter** is the load-bearing identity substrate for a charter-bearing agent. Every executive agent (Argus, Vela, Metis, Talos, Cosmo, Orpheus, Silas, Tropo) and every director-class agent (d.pm, d.ops, d.curator, etc.) boots into a charter that declares WHO they are, WHAT they govern, and HOW they boot.

**On-disk path convention.** Charter files live at `vault/files/<uid>.md` (8-hex UID assigned at commission per §2 uid row). The activation file at `agents/<agent-name>/<agent-name>-activation.md` is a thin pointer that resolves the charter UID via its frontmatter (`charter_uid:`). R4 P2-2 absorption: path convention previously implicit.

The charter is distinct from:
- **Activation entries** (per activation.capsule v1.0.3) — the per-generation boot records
- **Status cards** — the mutable per-session state surface
- **Soul letters** (per ADR-027) — the identity-narrative literature read at boot
- **Generation logs** (pre-v1.21.0) / activation registry records — the lineage substrate

The charter is the load-bearing identity contract. Each agent has ONE active charter at any time. Charters LOCK at commission and amend only via Mike lock-break per spec §3.3 lock semantics.

---

## 2. Required Frontmatter

A file is a valid charter if + only if its frontmatter declares all of these fields:

| Field | Type | Semantics |
|---|---|---|
| `uid` | 8-hex string | Stable identifier; unique across vault. Author-assigned at commission (any 8-hex value); verify uniqueness via `grep <uid> vault/00-index.jsonl` before commit. R4 P1-3 absorption: convention previously implicit. |
| `type` | literal `"charter"` | Distinguishes charters from other governed substrate |
| `agent_name` | string | The agent's name (lowercase; e.g., "argus", "vela", "d.pm") |
| `agent_class` | enum | One of: `executive`, `director`. Sa.* agents use session-agent.capsule (`type: session-agent`), not this capsule. |
| `role` | string | The agent's role (e.g., "Chief Architect", "Chief of Staff") |
| `capability_scope` | object | Sub-fields `reads:` (list of paths) + `writes:` (list of paths); the agent's governance contract (what it may read/write). Paths may be folder paths (e.g., `agents/<name>/`), file globs (e.g., `channels/<name>-*.md`), or capsule UIDs. **Renamed from `scope` in v1.72 Move 4 (field-disambiguation):** the bare `scope` name was overloaded with the scalar extraction/session taxonomy; a charter's read/write authorization object is the distinct concept `capability_scope`. |
| `status` | enum | One of: `active`, `locked`, `retired`, `archived`, `suspended` |
| `boot_protocol` | enum | One of: `playbook`, `commissioned`, `on-demand`. **Executive default: `playbook`** unless the agent is invoked-only-when-needed (rare sub-pattern; see enum semantics below). R4 P1-1 absorption. |
| `created` + `created_by` | date + string | Provenance. Convention: `created_by` uses `<agent-slug>-<generation>` format (e.g., `mike-a01`, `argus-a69`, `vela-v46`) — matches activation registry pattern. R4 P2-1 absorption. |
| `modified` + `modified_by` | date + string | Hygiene. Same `<agent-slug>-<generation>` format as `created_by`. |

### Enum value semantics

**`agent_class`:**
- `executive` — persistent identity-bearing agent that commissions per-generation (Argus A1→A69 boot into the same charter; each generation is a new activation entry against the same charter)
- `director` — persistent specialist agent commissioned once per ADR-022 (d.pm, etc.); no per-generation lineage

**`status`:** — `status:` ∈ {active, locked, retired, archived, suspended, superseded}
- `active` — charter is the current identity declaration; agent boots into this charter
- `locked` — charter is frontmatter-locked at commission (concurrent with `active`; not mutually exclusive); see §4 lock semantics
- `retired` — agent class has been retired (e.g., Silas after publishing role wound down); charter preserved for historical record; not boot-loaded
- `archived` — charter superseded by newer version; preserved for honest historical record; not boot-loaded
- `suspended` — agent class temporarily paused; not boot-loaded; resumable

**`boot_protocol`:**
- `playbook` — **EXECUTIVE DEFAULT.** Reads `agents/<name>/<name>-activation.md` + executes activation playbook per ADR-032. If uncertain, pick `playbook` for executive-class agents.
- `commissioned` — director boot pattern (commissioned-once-by-principal; per ADR-022)
- `on-demand` — narrow sub-pattern: executive that activates ONLY when principal invokes (Argus uses this; most executives use `playbook` even if they are not always-on). Rare; pick `playbook` unless the agent's role explicitly demands on-demand-only commissioning.

## 3. Optional Frontmatter

A charter MAY declare any of these fields; absence is not a defect:

- `soul` (object: role, values, voice, decision_style) — agents with explicit soul declaration
- `dna` (object: model, platform, context_window, capabilities) — agents whose sleeve/runtime declaration is load-bearing
- `channels` (list of paths) — agents with declared inter-agent channels. Convention: `channels/<agent>-<peer>.md` (e.g., `channels/argus-vela.md`); agent-pair-named, agent-side-of-pair in filename matches agent_name field. R4 P1-5 absorption.
- `retirement_acts` (list of strings) — agents with per-class retirement protocols
- `governor` — governance pointer (e.g., "operating-agreement")
- `locked_at` + `locked_by` — atomic pair, **REQUIRED once charter is LOCKED at commission** per §6 lock semantics (these fields transition from optional to required at the moment of LOCK signoff). R4 P1-4 absorption: §3/§6 tension clarified — optional pre-LOCK; required post-LOCK.
- `subsystem_hub` (list of UIDs) — subsystem hubs the charter belongs to for graph-walk discoverability (e.g., `99ed55fd` tropo-agents). Conventional; enables nav-block render + cross-reference resolution **(v1.0.2 member_of DISAMBIGUATE: moved here from `member_of`)**. R4 P2-3 absorption.
- `member_of` (list of UIDs) — the agent-root / true organizational parent (non-hub).
- `user_facing` (boolean) — **(v1.0.3, Mike-A103 signed 2026-06-07)** opt-in marker: when `true`, the agent is surfaced/summonable in the L2 user-facing harness (e.g., the Tropo Work agent picker). Absent or `false` = internal-only (the default — every existing charter without it stays valid). Introduced Metis-G73 (A2; first use on Po `194c4935`); ratified into the capsule here.
- Operational pointers: `status_card`, `generation_log`, `living_transfer`, `briefing_file`, `board`

## 4. Required Body Section

A charter body MUST contain exactly one H2 section matching the strict-literal Identity regex (case-insensitive):

```
^##\s+(?:\d+\.\s+)?Identity$
```

This accepts:
- `## Identity`
- `## IDENTITY`
- `## 1. Identity`
- `## 1. IDENTITY`
- (and any numbered-prefix `## N. Identity` variant)

This does NOT accept role-shaped H2 alternatives (e.g., `## Purpose`, `## Charter`, `## Role`). Per spec §3.2 Q7-spec captain-mode argus call 2026-05-17: strict literal wins; whitelist of role-shaped alternatives rejected as cousin to more-capsules-equals-more-maintenance pin.

The matching Identity section MUST contain at minimum:
- The agent's name in narrative form (e.g., "You are Argus, the Chief Architect of the Crew of the Argo.")
- The agent's role (one-sentence description)
- A pointer or summary of lineage (e.g., "See `<lineage substrate path>` for prior generations.")

## 5. Optional Body Sections

A charter MAY declare additional H2 sections. Common patterns:

- `## Soul` (or equivalent identity statement) — values + voice + decision style narrative
- `## Scope` — prose elaboration of the frontmatter scope contract
- `## Lineage` — prior generations + their defining contributions
- `## Crew` — working relationships with other agents
- `## Who Mike Is` (or equivalent principal description)
- `## Startup Signal` — boot signal format declaration
- `## Operating Notes` — agent-specific operating discipline

## 6. Lifecycle + Lock Semantics

Charter LOCKS at commission (initial authoring + Mike signoff). Once locked, mutability is governed by field class:

**Lock-break required (Mike signoff per OS Invariant):**
- Body content
- Identity fields: `agent_name`, `agent_class`, `role`, `scope`, `boot_protocol`
- Optional substrate field MUTATIONS to existing values (changing soul values, dna model, role-shaping fields)

**Standard editing (no lock-break):**
- Hygiene fields: `last_updated`, `modified`, `modified_by`
- Pointer fields: `status_card`, `generation_log`, `living_transfer`, `briefing_file`, `board`, `channels` (the pointer field is mutable as substrate moves; pointer targets follow their own capsule rules)
- Optional substrate field ADDITIONS (adding `soul`, `dna`, `channels`, `retirement_acts` where the field was previously absent — the per-agent charter-conformance-rev path toward v2.0.0 ERROR ratchet)

**The carve-out is narrow:** lock-break is required for anything that changes WHO the agent is or WHAT they govern (identity fields + mutations to authored optional substrate). Operational hygiene (dates, pointer updates, additive optional-substrate authoring) is routine editing.

**Enforcement note:** validator cannot mechanically distinguish a soul-addition from a soul-mutation without prior-state comparison (no git-diff hook in v1.37.0 scope). Honor-system at v1.37.0 ship; lock-break protocol relies on agent self-discipline + Mike review. Future-cycle Path 2: validator extension that compares against prior-version charter substrate.

## 7. Validation Checks (enforced by check_charter_conformance in tropo-validate.py)

Per v1.37.0 spec §3.4 — WARN at v1.37.0 honor-system; ERROR ratchet at v2.0.0 public ship.

For every file with `type: charter`:

1. All required frontmatter fields (§2) are present + correctly typed
2. `agent_class:` value is one of `executive` | `director`
3. `boot_protocol:` value is one of `playbook` | `commissioned` | `on-demand`
4. `status:` value is one of `active` | `locked` | `retired` | `archived` | `suspended`
5. `capability_scope:` object has both `reads:` + `writes:` sub-fields (each a list; may be empty)
6. Body contains exactly one H2 section matching `^##\s+(?:\d+\.\s+)?Identity$` (case-insensitive)
7. If `locked_at:` present, `locked_by:` must also be present (atomic LOCK metadata)
8. If `status: retired` or `status: archived`, checks 1-7 are RELAXED at WARN-only at v2.0.0 ratchet (retired/archived charters preserve original substrate as honest historical record; per-charter conformance enforcement applies only to live `active` + `locked` status)

## 8. Forbidden Patterns

- `type: document` on any file containing charter-shaped frontmatter (use `type: charter`)
- `type: agent-charter` on any file (deprecated third-variant typing; v1.37.0 mechanical type-flip script normalizes to `type: charter`)
- `type: charter` on a file that does NOT declare the required fields above (validator WARN at v1.37.0 / ERROR at v2.0.0+)
- `agent_class:` values other than `executive` or `director` (sa.* must use session-agent.capsule + `type: session-agent`)
- Charter body with NO H2 matching the strict-literal Identity regex
- Charter body that consists entirely of pointers without identity narrative

## 9. Why This Capsule Exists

Closes the v1.23.0 sa.skeptic-039 governance carry-forward: charters were the load-bearing identity primitive being migrated to vault/files/<uid>.md, but the substrate had no `type: charter` capsule — only ad-hoc `type: document` typing (and one `type: agent-charter` outlier for Tropo). Migration succeeded structurally; the typing imprecision propagated forward.

Per Captain's Read [a5f4b26b] Block 3 thesis: pre-ship polish; ratchet cycles; closes carry-forwards; maturity proof. v1.37.0 ships this capsule + mechanical type-flip + validator check; per-agent conformance amendments are each agent's future-cycle work; v2.0.0 public ship has clean typed-charter substrate end-to-end.

Per more-capsules-equals-more-maintenance pin (Mike-A69 2026-05-17): ONE capsule covers executive + director uniformly. Director-class variance handled as frontmatter optionality, not as a separate capsule.

## 10. Composability

- `session-agent.capsule v1.5 LOCKED` ([b4e2a718](../../vault/files/b4e2a718.md)) — parallel typed primitive for ephemeral agents; charter capsule does NOT override or replace; the two capsules govern disjoint file types via different discriminator fields (`type: charter` vs `type: session-agent`)
- `activation.capsule v1.0.3` ([4e8b21f0](../../vault/files/4e8b21f0.md)) — uses `agent_class:` field with extended enum (charter values + `pipeline`); cross-capsule consistency: executive/director values in charters are also valid `agent_class:` values in activation entries
- `sa/CAPSULE.md` ([e863a1e0](../../vault/files/e863a1e0.md)) — commissioning protocol; composes with charter via `boot_protocol: commissioned` for director-class agents
- `capsule-definition meta-capsule` ([222873b9](../../vault/files/222873b9.md)) — governs this capsule's shape

---

*charter capsule v1.0 | UID `8f3c9e1a` | Authored by argus-a69 2026-05-17 | LOCKED Mike-A69 'yes, proceed' 2026-05-17 | Ships at v1.37.0 closing v1.23.0 sa.skeptic-039 carry-forward | One capsule for executive + director (more-capsules-equals-more-maintenance pin)*
