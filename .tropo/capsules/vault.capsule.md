---
uid: 4d6e2f9a
name: "vault"
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
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# vault — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Tropo Work v2 — Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md) |
| Extends | `entity` |

*The vault itself is an entity. Exactly one vault-entity per vault. Grounds every action in a founder/owner principal. Makes federation recursive: vault-of-vaults composes via the same `entity` primitive.*

*Subtype of [entity.capsule (1e9c3f7a)](entity.capsule.md). Per [Tropo Work v2 Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md) §2.5 + D7 (L0 hierarchy invariant).*

---

## Intent

A vault is not an empty container holding entities — it IS an entity, sitting at L0 of a recursive federation hierarchy. This insight is what makes v2's federation model fall out "for free" (subject to the UID namespacing follow-on work).

**Every Tropo vault has exactly one vault-entity.** Its `principal:` is the founder/owner — the human whose identity grounds every action that happens inside the vault. For the Argo vault, the principal is Mike. For a user's personal Tropo vault, the principal is that user. For a team's shared vault, the principal is the team's designated owner (a person-subtype entity, not the team itself — principals ground back to atomic entities at some depth).

**The vault-entity is created once, at vault instantiation, and does not move.** It exists at `.tropo-studio/entity.md` (or equivalent canonical path TBD during Stream 1 authoring). It is the anchor for D7 enforcement (every work-item `member_of` at least one vault-entity-owned project) and for activity-log root (`vault/activity.jsonl` is the vault-entity's activity log).

---

## Required Frontmatter (in addition to entity)

| Field | Type | Constraint |
|---|---|---|
| `subtype` | literal | Must be `vault`. |
| `principal` | UID | Must resolve to an entity with `subtype: person`. Principals ground at person-subtype (or agent for fully-agent-owned vaults — rare; see Governance Rule 3). |
| `name` | string | The vault's name (e.g., "Argo", "acme-research-vault"). ≤ 100 chars. |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `members` | array of UIDs | Sub-entities (crew agents, teams, other vaults in federated configurations). Empty for newly-instantiated vaults. Populates as the vault grows. |
| `vault_class` | enum | `personal` / `team` / `department` / `company` / `marketplace` — federation-depth hint; informational. |
| `inbox_project` | UID | Reference to the vault-entity's inbox project (catches orphan work per D7). Required effectively; set when vault-inbox is authored at v1.4 Gate 3. |
| `activity_log` | path | Path to vault-entity's activity log (default: `vault/activity.jsonl`). |
| `founded_at` | ISO 8601 date | When the vault was instantiated. |
| `federation_parent` | UID | If this vault is federated as a member of a larger entity (team-vault → company-vault), reference here. Empty for root vaults. |

---

## Governance Rules (in addition to entity)

1. **Exactly one per vault.** Authoring a second `subtype: vault` entity in the same vault is a P0 violation. The capsule-validator rejects the second write.
2. **Principal grounds at a person (typically).** The vault's `principal:` must be a `subtype: person` entity (or, for fully-autonomous agent-owned vaults, an `agent` entity — rare; document at ratification if adopted). This ensures every vault-scoped action traces back to a human or accountable agent.
3. **Vault-entity is not archivable while the vault is live.** `state: archived` on a vault-entity means the vault itself is retired (the whole system). Rare; signals vault-dissolution or hand-off to federation.
4. **Membership is optional and additive.** A vault with `members: []` is legal at instantiation; the vault grows as crew agents, teams, and sub-vaults are added.
5. **D7 (from arch-spec §2.3) enforces through this primitive.** Every work-item in the Vault must `member_of` at least one project that traces ownership to the vault-entity. The vault-entity's inbox_project (authored at Gate 3) catches orphans.
6. **Activity log is append-only.** The vault-entity's activity log captures vault-scope events (entity creations, retirements, principal transfers, vault-inbox adds). Append-only; immutable.

---

## Validation Checks (in addition to entity)

1. **[enforced]** `subtype: vault`
2. **[enforced]** Exactly one `subtype: vault` entity in the vault (validator rejects second write)
3. **[enforced]** `principal:` resolves to a `subtype: person` entity (or `subtype: agent` with documented rationale)
4. **[enforced]** `principal:` differs from self (inherited from entity Rule 2)
5. **[enforced]** If `inbox_project:` present, resolves to a `type: project` entry owned by self (i.e., the vault-entity)
6. **[honor-system]** Activity log file exists at declared path; append-only discipline (validator target: v2.1 per arch-spec §8.3)

---

## Relationship to Other Capsules

- **[entity.capsule (1e9c3f7a)](entity.capsule.md)** — parent
- **[project.capsule v2.3](project.capsule.md)** — vault-entity-owned projects enforce D7
- **[agent.capsule (2f8b4e3d)](agent.capsule.md)** — crew agents are members of the vault-entity (typically)

---

## Known Enforcement Gaps

Inherits entity.capsule's gaps. Subtype-specific:

| Gap | What closes it | Target | Owner |
|---|---|---|---|
| Vault-singleton enforcement (exactly one `subtype: vault` per vault) is honor-system at v1.0 | Rebuild validator counts vault-subtype entities; rejects on count > 1 | v1.5 | argus |
| Activity log append-only discipline is honor-system | Filesystem-level append-only enforcement OR file-hash check | v2.1 | argus |
| `inbox_project:` lifecycle not enforced — vault-entity with `inbox_project: null` breaks D7 | Validator rejects vault-entity without resolvable `inbox_project:` | v1.4.1 | argus |

---

## Extension from core + entity

*Where this capsule specializes [entity.capsule (1e9c3f7a)](entity.capsule.md).* vault.capsule tightens: `subtype` must be `vault`; `principal:` must resolve to a `subtype: person` entity (or rare `agent`); `name:` is the vault's public name. Adds optional fields: `members:`, `vault_class:`, `inbox_project:`, `activity_log:`, `founded_at:`, `federation_parent:`. All entity.capsule base rules inherited unchanged.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you act.*

**Tools available:**
- `vault/activity.jsonl` — vault-entity's activity log; append-only per Rule 6
- Principal-chain walker — `principal:` field chains from any entity up to vault-entity; enables audit traceability

**Skills:**
- `create-vault-entity.skill.md` *(forthcoming Gate 3 deliverable)* — authors vault-entity + vault-inbox at v1.4 vault instantiation
- Mike-signing protocol — principal grounding at vault-entity authoring

**Procedures:**
- Vault-instantiation protocol — at v1.4 Gate 3: author person-entity for founder → author vault-entity with `principal: <founder-uid>` → author vault-inbox project → Mike-sign via channel approval
- Federation-authoring protocol *(forthcoming v1.5+)* — linking vault-entities into team/company/marketplace hierarchies via `federation_parent:`

**Rules (at-a-glance):**
1. **Exactly one per vault** (singleton invariant)
2. Principal grounds at a person (typically; rare `agent` exception)
3. Vault-entity not archivable while vault is live
4. Membership optional + additive
5. **D7 enforces through this primitive** — every work-item `member_of` traces to the vault-entity's project tree
6. Activity log append-only

**Pitfalls:**
- Authoring a second vault-entity → Rule 1 violation; reject
- Principal not grounded at a person → untraceable action chains
- Vault-inbox not authored before Gate 3 closes → D7 enforcement breaks
- `members:` used as authority claim → membership is compositional (per team.capsule precedent)
- `state: archived` on live vault-entity → signals whole-vault dissolution; rare + intentional only

**Worked examples:**
- [Argo vault entity (7f5b1d83)](../../vault/files/7f5b1d83.md) — `principal: 6c0e4a2b` (Mike); `inbox_project: 8a4c9e15`; authored at v1.4 Gate 3
- Pattern for external Tropo vaults: user authors vault-entity at first-run; concierge prompts for founder person-entity + signing

**Go next:**
- Vault's principal → [entity.capsule subtype: person (1e9c3f7a)](entity.capsule.md) + forthcoming person.capsule
- Vault's crew agents → [agent.capsule (2f8b4e3d)](agent.capsule.md)
- Vault's crew as a team → [team.capsule (3c9a7b1e)](team.capsule.md)
- Vault-inbox catching orphan work → [project.capsule v2.3 (34e4cb0b)](project.capsule.md) + [vault-inbox instance (8a4c9e15)](../../vault/files/8a4c9e15.md)
- D7 enforcement path → [Tropo Work v2 Arch Spec (f2e8a7b1)](../../vault/files/f2e8a7b1.md) §2.3

---

## Migration Notes

v1.3 and prior did not have a vault-entity. Migration: at v1.4 Gate 3, author the Argo vault-entity at `.tropo-studio/entity.md` (or canonical path). Principal: Mike's person-subtype entity (authored in the same Gate 3 pass). Inbox-project: authored alongside. All three artifacts Mike-signed.

Migration for user vaults (external Tropo users): during v1.4 release-extraction, the release zip ships with a vault-entity template the user fills at first-run. Concierge at first-boot detects the missing vault-entity + prompts the user to ground (per §1.5 STUDIO.md Bootstrap extended to vault-entity creation).

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-04-23 | Initial DRAFT. Subtype of entity.capsule. Pending three-instrument. | argus-a32 |

---

*vault capsule definition | DRAFT v1.0 | Argus A32 | 2026-04-23*
*"The vault is not a box holding entities. It is an entity."*
