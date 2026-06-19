---
uid: 3c9a7b1e
name: "team"
type: capsule-definition
extends: entity
version: 1.0
tier: os
author: argus
created: 2026-04-23
modified: 2026-04-24
modified_by: argus-a32
status: locked
locked_by: argus-a32
locked_at: 2026-04-24
schema_version: 2
governed_by: 222873b9   # capsule-definition meta-capsule
aligned_with: f2e8a7b1   # Tropo Work v2 Architecture Specification
supersedes: (v0.3 team primitive — informal)
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# team — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Tropo Work v2 — Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md) |
| Extends | `entity` |
| Supersedes | `(v0.3 team primitive — informal)` |

*A composite entity: a group of agents, people, or other entities operating together. Specializes entity by requiring non-empty `members:`, naming an executive principal, and optionally declaring shared channels.*

*Subtype of [entity.capsule (1e9c3f7a)](entity.capsule.md). Per [Tropo Work v2 Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md) §2.5. Supersedes v0.3's informal `team` primitive.*

---

## Intent

A team is a composite entity. The Argo crew is a team (members: Argus, Vela, Metis, Orpheus, Talos). A user's Tropo instance may have teams (`research-team` members: [researcher, analyst, drafter]). Teams are the composition primitive one level above atomic agents.

Teams have executive principals — the entity that signs on the team's behalf. For the Argo crew, the principal is Mike (vault-principal). For a user's research-team, it might be the user themselves, or a designated director-class agent.

**Before creating a team, ask:**
- Who are the members? (At least one; must be entities.)
- Who is the executive principal? (Cannot be the team itself; typically the founder, owner, or director.)
- Does the team have a shared channel? (Optional; declared via `shared_channel:`.)

---

## Required Frontmatter (in addition to entity)

| Field | Type | Constraint |
|---|---|---|
| `subtype` | literal | Must be `team`. |
| `members` | array of UIDs | Non-empty. Each UID resolves to another entity (typically agents, persons, or sub-teams). |
| `principal` | UID | Must differ from self. Typically the team's founder, owner, or executive agent. |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `shared_channel` | path | Path to the team's shared communication channel (e.g., `channels/crew-standup.md`, `channels/research-team.md`). |
| `charter` | UID or path | Link to the team's charter document (if one exists). For the Argo crew, points at the Operating Agreement. |
| `team_class` | enum | `crew` (chartered + persistent) / `project-team` (scoped to work) / `functional` (operational grouping). |

---

## Governance Rules (in addition to entity)

1. **Principal is external.** Per entity Rule 2, team principals must differ from the team's own UID. The team is composite; someone else signs on its behalf.
2. **`members:` non-empty.** An entity without members is not a team. If you find yourself authoring a team with `members: []`, reconsider — is this really an atomic entity (agent) instead?
3. **Membership does not imply hierarchy.** Listing B in A's `members:` means B operates as part of A. It does NOT mean A can command B. Request-lifecycle (spec §2.3) governs work delegation — membership is structural composition, not authority.
4. **Teams may contain sub-teams.** `members:` may include other team-subtype entities. Federation cleanly composes via this recursion (subject to cycle-detection per entity Rule 5).
5. **Shared channel is optional.** Not every team needs a channel (a one-off project-team may coordinate via existing executive channels). Required only when the team has persistent independent operations.

---

## Validation Checks (in addition to entity)

1. **[enforced]** `subtype: team`
2. **[enforced]** `members:` non-empty; each UID resolves to an entity
3. **[enforced]** `principal:` resolves to an entity that differs from self
4. **[enforced]** No self-membership cycles (inherited from entity Rule 7)
5. **[honor-system]** `shared_channel:` (if present) points at a file that exists

---

## Relationship to Other Capsules

- **[entity.capsule (1e9c3f7a)](entity.capsule.md)** — parent
- **[agent.capsule (2f8b4e3d)](agent.capsule.md)** — most members are typically agent-subtype entities

---

## Known Enforcement Gaps

Inherits entity.capsule's gaps. Subtype-specific:

| Gap | What closes it | Target | Owner |
|---|---|---|---|
| Shared-channel existence not mechanically verified when `shared_channel:` is declared | Validator walks the referenced path; warns if missing | v1.5 | argus |
| Hierarchy queries ("what entities does A govern transitively?") are honor-system | Graph-walker utility over `members:` edges | v1.5 | argus |

---

## Extension from core + entity

*Where this capsule specializes [entity.capsule (1e9c3f7a)](entity.capsule.md).* team.capsule tightens: `subtype` must be `team`; `members:` must be non-empty; `principal:` must differ from self. Adds optional fields: `shared_channel:`, `charter:`, `team_class:`. All entity.capsule base rules inherited unchanged.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you act.*

**Tools available:**
- `python3 .tropo/scripts/tropo-validate.py` — runs team.capsule's 5 checks including cycle detection on `members:`
- Channel convention — `channels/<team-slug>.md` for shared-channel pattern (see channels/CAPSULE.md)

**Skills:**
- `compose-team.skill.md` *(forthcoming v1.5)* — authors a new team entity from existing member entities

**Procedures:**
- Team-charter authoring pattern — charter lives at `agents/<team-slug>/charter.md` for chartered crews (Argo crew precedent via Operating Agreement)
- Shared-channel convention — team-wide coordination via `channels/<team>.md`

**Rules (at-a-glance):**
1. Principal is external (not self; per entity Rule 2)
2. `members:` non-empty — a team without members is not a team
3. Membership does NOT imply hierarchy or authority — use request-lifecycle for delegation
4. Teams may contain sub-teams (composite recursion, cycle-safe per entity Rule 5)
5. Shared channel optional — not every team needs persistent channel-level coordination

**Pitfalls:**
- Team authors itself as principal → Rule 1 + entity Rule 2 violation
- Empty `members:` → not a team; reconsider (likely an agent-subtype or standing project)
- Treating membership as authority → use request-lifecycle + `auto_accept_from:` for work-flow
- Cross-vault membership at v1.0 → forbidden until federation UID-namespacing ships (v1.5+)

**Worked examples:**
- Argo crew as a team entity *(to be authored at v1.4 migration)* — members: agent-subtype entities for Argus/Vela/Metis/Orpheus/Talos; principal: Mike (vault principal)

**Go next:**
- Atomic member type → [agent.capsule (2f8b4e3d)](agent.capsule.md) or `person` subtype *(v1.5)*
- Entity base → [entity.capsule (1e9c3f7a)](entity.capsule.md)
- Team's vault context → [vault.capsule (4d6e2f9a)](vault.capsule.md)
- Team delegating work → [task.capsule v3.0 (3289712a)](task.capsule.md) (request-lifecycle from team to member)

---

## Migration Notes

v0.3 had an informal `team` capsule. Migrate v0.3 team entries to `type: entity, subtype: team` with `principal:` populated + `members:` verified. The Argo crew vault entry, if one exists, gets this treatment; if not, author fresh at v1.4 migration.

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-04-23 | Initial DRAFT. Subtype of entity.capsule. Supersedes v0.3 informal team primitive. Pending three-instrument. | argus-a32 |

---

*team capsule definition | DRAFT v1.0 | Argus A32 | 2026-04-23*
*"Composition is not command. Structure is not authority."*
