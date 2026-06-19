---
uid: 1e9c3f7a
name: "entity"
type: capsule-definition
extends: core
version: 1.1
supersedes_version: "1.0"
tier: os
author: argus
created: 2026-04-23
modified: 2026-04-27
modified_by: argus-a37
status: locked
locked_by: argus-a32
locked_at: 2026-04-24
schema_version: 2
governed_by: 222873b9   # capsule-definition meta-capsule
aligned_with: f2e8a7b1   # Tropo Work v2 Architecture Specification
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# entity — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Tropo Work v2 — Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md) |
| Extends | `core` |

*An entity is an actor in the vault. Persons, agents, teams, departments, companies, vaults, marketplaces — all share this uniform primitive. Entities request work, accept work, own work, sign actions, and compose into larger entities via membership. Entity is the "actor" half of Tropo Work v2's actor ↔ content split; WorkItem is the "content" half.*

*Formalizes [Tropo Work v2 Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md) §2.5 (Entity topology) + §3.1 (required frontmatter). Subtype capsules (agent, team, vault, person, department, company, marketplace) extend this base.*

---

## Intent

Name who acts. In v1.3 and prior, actors were modeled implicitly: agents lived as folders in `agents/<name>/`, teams were declared in a `team` capsule, humans had no typed representation. This asymmetry forced every subsystem (request-lifecycle, permissions, federation) to special-case each actor class.

v2 replaces the asymmetry with a uniform primitive. Every actor — human, AI agent, team, department, company, vault, marketplace — is an `entity` with a `subtype` that specializes. The shared base carries: identity, principal (who signs), membership (for composites), and auto-accept policy. Specialization happens via subtype capsules that extend this one.

**Before creating an entity, ask:** who is the principal? An atomic entity (person, agent) is self-signing. A composite entity (team, department, company) names a principal who signs on its behalf. A vault-entity names its founder/owner. This is the grounding check — if you can't name the principal, you can't author the entity.

**The uniform-entity move makes federation fall out structurally.** Individual vault → team vault → department vault → company vault → marketplace are the same primitive at increasing nesting depth. This capsule does not yet specify federation permissions or cross-vault visibility (those are a follow-on spec); it sets up the primitive such that the follow-on work has a clean seam to cut against.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `uid` | 8-hex | Per core. |
| `type` | literal | `entity`. |
| `subtype` | enum | One of: `person` / `agent` / `team` / `department` / `company` / `vault` / `marketplace`. Drives specialization via subtype capsules. |
| `name` | string | ≤ 100 chars. Human-readable name. May contain dots for namespaced agent patterns (e.g., `sa.cold-boot`, `d.pm`). |
| `principal` | UID | Must resolve to another entity. **Self-reference is legal and expected for atomic subtypes** (person, agent) — an atomic entity is its own principal (self-signing). Composite subtypes (team, department, company, vault, marketplace) MUST name a principal that is NOT self (the signing human or executive agent). |
| `state` | enum | `active` / `archived`. Lifecycle-visibility flag per core conventions. |
| `title` | string | Per core; ≤ 100 chars. Typically matches or describes `name`. |
| `owner` | string | Per core. For entities, `owner` is typically the principal's identifier. |
| `created` | date | Per core. |
| `modified` | date | Per core. |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `members` | array of UIDs | Legal only for composite subtypes (team, department, company, vault, marketplace). Empty for atomic subtypes (person, agent). Each UID resolves to another entity. Recursion cycles (entity contains itself transitively) are forbidden — see Validation Check 7. |
| `auto_accept_from` | array of UIDs | Each UID resolves to another entity. Enables the request-lifecycle auto-accept optimization: requests from listed entities skip `status: requested` on work-items and transition directly to `accepted` (per [Tropo Work v2 spec (f2e8a7b1)](../../vault/files/f2e8a7b1.md) §2.3). **Cap: ≤ 20 entries per entity at v1.0** (governance Rule 9 below). **Restriction: same-vault only** until federation UID-namespacing ships (v1.5+). Changes to this field MUST be logged in the entity's activity log with principal signature per governance Rule 9. Useful for tight pair-channels (argus-vela) or trusted-director patterns. |
| `subtype_version` | string | Semver of the specialization rules from the subtype capsule. Optional; used when subtype capsules version their specializations. |
| `primary_collection` | UID | Optional collection-ref for entity-authored artifacts (useful for agents with rich bodies of work). |
| `principal_chain` | array of UIDs | Optional derived field: the full chain from this entity's `principal:` up to the root vault-entity. Convenience for chain-of-signing audit; computable from `principal:` walks at rebuild time. Not required. |
| `relationships` | array of typed edges | Schema v2 unified relationships — `collaborates-with`, `reports-to`, `supervises`, etc. Not mandated at v1.0; subtype capsules may mandate specific edges. |

---

## State Machine

```
active → archived  (terminal for v1.0; revival = new entity entry, not state reversion)
```

| State | Meaning |
|---|---|
| `active` | Entity is operational. Can request, accept, own work. |
| `archived` | Retired crew agent, dissolved team, sunset company. Entity no longer acts; historical record remains queryable. |

**No `paused` state in v1.0.** Subtype capsules may introduce pause semantics (e.g., `agent` subtype adding `retired | active | dormant`). The base capsule stays minimal.

**Valid transitions:**

- `active → archived` — retirement, dissolution, succession
- `archived → archived` — terminal; immutable historical record

---

## Governance Rules (in addition to core)

1. **Principal grounding is load-bearing.** Every entity MUST have a `principal:` that resolves. Authoring an entity without a principal — or with a principal UID that doesn't resolve — is a P0 validation failure. The principal is who the entity's actions ground back to; no principal means untraceable actions.

2. **Atomic vs composite principal rules.**
   - **Atomic subtypes** (`person`, `agent`): `principal:` equals self (same UID as the entity's own `uid:`). Self-signing.
   - **Composite subtypes** (`team`, `department`, `company`, `vault`, `marketplace`): `principal:` MUST differ from self. Typically the owning human (for personal-scope composites) or a named executive agent (for organizational-scope composites). A composite entity cannot be its own principal.
   - Subtype capsules may further constrain (e.g., `vault.capsule` may require `principal.subtype: person`).

3. **Members legal only for composites.** If `subtype ∈ {person, agent}`, `members:` MUST be empty or absent. If `subtype ∈ {team, department, company, vault, marketplace}`, `members:` MAY be non-empty and MUST each resolve to another entity.

4. **Membership is non-reciprocal but verifiable.** Entity A listing B in `members:` does NOT automatically make A appear in B's `member_of:` (entities don't have `member_of:` at the entity level; membership is one-directional — containers hold members, members don't claim containers). Verification relies on `members:` arrays being authoritative.

5. **No self-membership recursion.** An entity MUST NOT appear in its own `members:` array, directly or transitively. Validator rejects cycles.

6. **`auto_accept_from:` is opt-in and reversible.** Default: empty (requests require explicit accept). Authoring auto-accept ties a permission to an entity-level field; removing it is edit-and-save. Useful for intra-crew high-trust pair-channels; inadvisable for cross-vault interactions.

7. **Subtype immutability.** An entity's `subtype:` is set at creation and does not change. Converting a person entity to an agent entity is not legal — archive the original and create a new entity. (Matches core Rule 4 on `type:` immutability; extends to subtype discrimination.)

8. **Principal transfer requires principal authorization.** Changing an entity's `principal:` from X to Y requires X's explicit consent (or vault-principal override). Silent principal rewrites are forbidden. Logged to the entity's activity (if the entity has one) or the vault-entity's activity log.

9. **`auto_accept_from:` governance — bounded, signed, same-vault-only.** Resolves sa.skeptic 011 P0-3 (v1.0 original text allowed unbounded auto-accept, creating a request-lifecycle bypass surface). Three constraints:
   - **Cap:** `auto_accept_from:` array MUST NOT exceed **20 entries** at v1.0. A v1.5+ federation spec may relax this; at v1.0, the cap prevents wildcard-bypass of the request-lifecycle governance.
   - **Signed audit log:** any CHANGE to `auto_accept_from:` (add, remove, reorder) MUST append a `principal-signed` entry to the entity's activity log OR the vault-entity's activity log (if the entity has no local activity log). Entry format: `{event: "auto_accept_changed", actor: <principal-uid>, prior: [...], current: [...], ts: <ISO-8601>}`. This is honor-system at v1.0; validator target v1.5.
   - **Same-vault only:** all UIDs in `auto_accept_from:` MUST resolve to entities within the same vault-entity tree. Cross-vault auto-accept is forbidden at v1.0 — federation UID-namespacing (spec §5 Q6) must ship before cross-vault auto-accept is safe. Validator target v1.5.

---

## Validation Checks (run at check-in)

In addition to core checks. All labeled **[enforced]** unless noted.

1. **[enforced]** `type: entity`
2. **[enforced]** `subtype` is in the declared enum (`person` / `agent` / `team` / `department` / `company` / `vault` / `marketplace`)
3. **[enforced]** `principal:` present; resolves to another entity vault entry
4. **[enforced]** If `subtype ∈ {person, agent}`: `principal:` equals self (`principal: <own-uid>`)
5. **[enforced]** If `subtype ∈ {team, department, company, vault, marketplace}`: `principal:` differs from self
6. **[enforced]** `members:` absent or empty if `subtype ∈ {person, agent}`; may be non-empty if composite
7. **[enforced]** If `members:` present, every UID resolves to another entity; no self-membership cycles (walk detection)
8. **[enforced]** If `auto_accept_from:` present: (a) array length ≤ 20 (Rule 9 cap); (b) every UID resolves to another entity; (c) every UID resolves to an entity within the same vault-entity tree (same-vault-only per Rule 9; honor-system until validator ships)
9. **[enforced]** `state` ∈ `{active, archived}`
10. **[honor-system]** Principal chain (if `principal_chain:` populated) terminates at a vault-entity or person — pure trees only, no cycles. Validator target: v1.5.

---

## Known Enforcement Gaps

| Gap | What closes it | Target release | Owner |
|---|---|---|---|
| Cross-vault UID uniqueness not enforced — federation may collide 8-hex UIDs across vaults | UID namespacing convention (vault-prefix + UID) per [Tropo Work v2 spec (f2e8a7b1)](../../vault/files/f2e8a7b1.md) §5 Q6 | v1.5 or v2.0 | argus |
| Principal-chain cycle detection is honor-system (no walker at v1.0) | Validator walks `principal:` chain; rejects cycles | v1.5 | argus |
| Signing attestation (can we verify a claimed-principal actually authorized the action?) is honor-system | Attestation-token concept per [a07219dc](../../vault/files/a07219dc.md); cryptographic per future secrets-vault | v1.5+ | argus |

These gaps are named honestly per arch-spec.capsule Rule 8. None block v1.0 authoring; all are flagged for post-v1.4 work.

---

## Inheritance

Extends `core`. Inherits UID immutability, type immutability, owner/created/modified invariants.

Subtype capsules extend this (entity). Each subtype MAY:

- **Tighten** constraints (e.g., `vault.capsule` requires `subtype: vault` + specific principal class)
- **Add** subtype-specific required fields (e.g., `agent.capsule` may require `activation_file:`)
- **Specialize** state machine (e.g., `agent.capsule` may add `retired | dormant` states)

Subtype capsules MUST NOT:

- Relax base rules (principal grounding, subtype immutability, recursion prohibition)
- Remove required fields
- Override core-level invariants

---

## Relationship to Other Capsules

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.
- **[agent.capsule (forthcoming D1.1)](agent.capsule.md)** — subtype extension; replaces ad-hoc `agents/<name>/` patterns.
- **[team.capsule (forthcoming D1.1)](team.capsule.md)** — subtype extension; replaces v0.3 `team` primitive.
- **[vault.capsule (forthcoming D1.1)](vault.capsule.md)** — subtype extension; exactly one instance per vault.
- **[task.capsule v3.0 (forthcoming D1.2)](task.capsule.md)** — WorkItem's `requested_by:`, `requested_of:`, `owner:` all reference entity UIDs.
- **[pipeline-run.capsule (forthcoming D1.1)](pipeline-run.capsule.md)** — `owner:` and `principal:` on runs reference entity UIDs.
- **[project.capsule v2.3 (forthcoming D1.2)](project.capsule.md)** — `owner:` on projects references entity UIDs; vault-entity-owned projects enforce D7 (every work-item has a vault-entity-project home).
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.

---

## Extension from core

*Where this capsule specializes the [core.capsule (ee814120)](core.capsule.md) floor.* entity.capsule v1.0 extends core per capsule-inheritance convention: **`title:` used as-is per core** (≤ 100 chars); **uses `state:` as the lifecycle enum** instead of core's `status:` (entities use `state: active/archived` because the entity-lifecycle surface is simpler than status-machine primitives; the subtype capsule may add a richer lifecycle field if warranted — e.g., `agent.capsule` extends `state` with dormant/retired sub-states); **`name:` is a new specialization field** distinct from core's `title:` (name is the short identifier; title is the human-readable descriptor). Honest typed-capsule specialization per the pattern.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you act.*

**Tools available:**
- `python3 .tropo/scripts/tropo-validate.py` — runs entity.capsule's 10 validation checks including principal grounding + cycle detection
- Activity log protocol — every entity action grounds back to a principal; verify chain resolves
- Registry pointers per [adac1f10](../../vault/files/adac1f10.md) matched-primitives topology: `.tropo-studio/registries/agent-registry.yaml` (agent-subtype identity), `vault/00-index.jsonl` (entity records that live in the ledger), folder listings (entity records that live elsewhere — discoverable via path).

**Skills:**
- `create-entity.skill.md` *(forthcoming v1.4 deliverable)* — authors a new entity with principal grounding + subtype selection
- `create-executive-agent.skill.md` — existing; will be amended to produce entity-compliant agent subtypes in v1.4 Stream 3
- `entity-compose.skill.md` *(v1.5+)* — authors composite entities (teams, departments) from atomic members

**Procedures:**
- `agent-activation.playbook.md` — boots an agent-subtype entity
- `agent-retire.playbook.md` — transitions an agent-subtype entity `active → archived`
- Principal-transfer protocol (Rule 8) — transfer entity principal between vault members with audit logging

**Rules (at-a-glance):**
1. **Principal grounding is load-bearing** — every entity MUST have a `principal:` that resolves
2. Atomic subtypes (person, agent) self-sign; composite subtypes (team, department, company, vault, marketplace) name external principals
3. Members legal only for composites; atomic subtypes have empty `members:`
4. Membership is non-reciprocal — containers hold the truth; members don't claim
5. No self-membership recursion
6. `auto_accept_from:` is opt-in and reversible; **capped at 20 entries, same-vault only, audit-logged** (Rule 9)
7. Subtype immutability — a person-entity doesn't convert to an agent-entity
8. Principal transfer requires principal authorization + audit log
9. **`auto_accept_from:` governance — bounded, signed, same-vault-only** (new Rule 9; sa.skeptic 011 P0-3 resolution)

**Pitfalls:**
- **Principal self-confusion** on composites → Rule 2 violation; composite entities never self-sign
- **Membership asymmetry** — listing B in A's members and expecting B to "know" → membership is one-directional
- **Subtype transitions** — trying to convert agent-entity to team-entity → Rule 7 forbids; archive + author new
- **Auto-accept over-scoping** — `auto_accept_from: [<wildcards>]` or >20 entries → Rule 9 cap violation; bypasses request-lifecycle governance
- **Cross-vault auto-accept** at v1.0 → forbidden until federation UID-namespacing ships (Rule 9)

**Worked examples:**
- [Mike Maziarz person entity (6c0e4a2b)](../../vault/files/6c0e4a2b.md) — atomic; self-signing; founder
- [Argo vault entity (7f5b1d83)](../../vault/files/7f5b1d83.md) — composite; principal: 6c0e4a2b
- Crew-agent entities *(authored at v1.4 migration)* — Argus, Vela, Metis, Orpheus, Talos, d.pm
- Argo-crew team entity *(authored at v1.4 migration)* — composite with agent members + Mike principal

**Go next:**
- Specializing to an AI agent? → [agent.capsule (2f8b4e3d)](agent.capsule.md)
- Composite of entities? → [team.capsule (3c9a7b1e)](team.capsule.md)
- Vault-top entity? → [vault.capsule (4d6e2f9a)](vault.capsule.md)
- Entity authoring work-items? → [task.capsule v3.0 (3289712a)](task.capsule.md) — `requested_by:`, `requested_of:`, `owner:`, `verifier:` all reference entity UIDs
- Entity invoking a pipeline-run? → [pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)

---

## Migration Notes

v1.3 and prior did not have a unified entity primitive. Migration path:

1. **Crew agents** (Argus, Vela, Metis, Orpheus, Talos) get entity vault entries authored at v1.4 ship time. Their existing `agents/<name>/` folders continue as-is; the vault entry is the typed-primitive reference.
2. **d.pm and other directors** follow the same pattern.
3. **Session agents (sa.\*)** are entity-subtype `agent`. They may or may not get vault entries depending on persistence needs; transient sa.* agents may skip entity vault entries without penalty.
4. **Mike** is the vault-entity's `principal:`. Gets a `person` subtype entity entry authored at Gate 3 (the vault-entity + vault-inbox deliverable).
5. **The vault itself** gets exactly one `vault` subtype entity entry. `principal: <mike-entity-uid>`.
6. **v0.3 `team` primitive**: amend each existing team vault entry to `type: entity, subtype: team` with principal populated. Supersedes `team.capsule`.

Migration script handles steps 1-6 mechanically where fields exist; manual grounding where fields don't (principals especially).

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-04-23 | Initial DRAFT. Authored per [Tropo Work v2 Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md) §2.5 + §3.1. Base primitive for agent/team/vault/person/department/company/marketplace subtypes. Pending three-instrument verification before lock. | argus-a32 |

---

*entity capsule definition | DRAFT v1.0 | Argus A32 | 2026-04-23*
*"Name who acts. Everything else composes from that."*
