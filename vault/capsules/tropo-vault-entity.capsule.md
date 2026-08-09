---
uid: 4d6e2f9a
name: vault-entity
type: capsule-definition
extends: entity
version: 1.1
tier: os
author: argus
created: 2026-04-23
modified: 2026-07-07
modified_by: talos-t25
status: retired
locked_by: argus-a127
locked_at: 2026-07-07
schema_version: 2
governed_by: 222873b9
aligned_with:
  - f2e8a7b1
  - 18059aef
subsystem_hub:
  - 8dd772a0
retired_at: '2026-07-12'
retired_by: argus-a130
retired_via: "Type Disposition walk 5dcbadbd (Mike-verdicted 2026-07-12, S2 activation 0d9f89bc) — zero instances ever authored; retired on the how-to precedent (v1.60, 'never earned itself empirically'). Verified no live convention references before retirement (grep 2026-07-12: historical mentions only). Tombstone-in-place per the how-to pattern; a future need re-enters via the closed registry (propose capsule → Mike locks)."
---

# vault-entity — Capsule Definition v1.1

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Tropo Work v2 — Architecture Specification (f2e8a7b1)](../../vault/files/f2e8a7b1.md) |
| Authorized by | ADR-051 — Vault-Node Primitive joint gate (18059aef), Fork 1 — the rename |
| Extends | `entity` |
| Sibling (new type, separate lifecycle) | `vault` manifest (a1f7c750) — the vault-node MANIFEST; renamed OUT of this capsule's name per ADR-051 Fork 1 |

*The vault-entity is the vault AS A PRINCIPAL: grounds every action in a founder/owner principal and anchors the D7 invariant. Exactly one vault-entity per vault-NODE (reframed per-vault-node, Mike's D7 ruling, ADR-051; generalizes the prior per-vault framing to the many-vaults-per-studio model — see Governance Rule 1). Makes federation recursive: vault-of-vaults composes via the same `entity` primitive. Renamed `vault` → `vault-entity` at v1.1 (ADR-051 Fork 1): the name `vault` was freed for a NEW, separate type — the vault-node MANIFEST (a1f7c750) — which governs membership + publish + audience + curation + contract, a different lifecycle from this capsule's principal-grounding + D7-anchor concern. UID `4d6e2f9a` is PRESERVED across the rename; only `name:` and display text changed.*

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
| `subtype` | literal | Must be `vault-entity` (renamed from `vault` per ADR-051 Fork 1; UID `4d6e2f9a` preserved). |
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

1. **Exactly one per vault-NODE** (reframed per-vault-node, ADR-051 Mike D7 ruling — generalizes the prior per-vault framing now that a studio holds MANY vaults). Authoring a second `subtype: vault-entity` in the same vault-node is a P0 violation. The capsule-validator rejects the second write.
2. **Principal grounds at a person (typically).** The vault's `principal:` must be a `subtype: person` entity (or, for fully-autonomous agent-owned vaults, an `agent` entity — rare; document at ratification if adopted). This ensures every vault-scoped action traces back to a human or accountable agent.
3. **Vault-entity is not archivable while the vault is live.** `state: archived` on a vault-entity means the vault itself is retired (the whole system). Rare; signals vault-dissolution or hand-off to federation.
4. **Membership is optional and additive.** A vault with `members: []` is legal at instantiation; the vault grows as crew agents, teams, and sub-vaults are added.
5. **D7 (from arch-spec §2.3) enforces through this primitive.** Every work-item in the Vault must `member_of` at least one project that traces ownership to the vault-entity. The vault-entity's inbox_project (authored at Gate 3) catches orphans.
6. **Activity log is append-only.** The vault-entity's activity log captures vault-scope events (entity creations, retirements, principal transfers, vault-inbox adds). Append-only; immutable.

---

## Validation Checks (in addition to entity)

1. **[enforced]** `subtype: vault-entity`
2. **[enforced]** Exactly one `subtype: vault-entity` entity per vault-NODE (validator rejects second write in the same node)
3. **[enforced]** `principal:` resolves to a `subtype: person` entity (or `subtype: agent` with documented rationale)
4. **[enforced]** `principal:` differs from self (inherited from entity Rule 2)
5. **[enforced]** If `inbox_project:` present, resolves to a `type: project` entry owned by self (i.e., the vault-entity)
6. **[honor-system]** Activity log file exists at declared path; append-only discipline (validator target: v2.1 per arch-spec §8.3)

---

## Relationship to Other Capsules

- **[entity.capsule (1e9c3f7a)](entity.capsule.md)** — parent
- **vault (a1f7c750) — the vault-node MANIFEST** — the SEPARATE type freed by this rename (ADR-051 Fork 1): membership + publish + audience + curation + contract. Not a parent/child relation — two types governing two lifecycles for the same vault-node.
- **[project.capsule v2.3](project.capsule.md)** — vault-entity-owned projects enforce D7
- **[agent.capsule (2f8b4e3d)](agent.capsule.md)** — crew agents are members of the vault-entity (typically)

---

## Known Enforcement Gaps

Inherits entity.capsule's gaps. Subtype-specific:

| Gap | What closes it | Target | Owner |
|---|---|---|---|
| Vault-entity singleton enforcement (exactly one `subtype: vault-entity` per vault-NODE) — CLOSED at v1.1: `check_vault_capsule_types` (tropo-validate.py, 943bb220) enforces it, scoped by `extraction_scope` as the vault-node grouping key until Fork 2's per-vault-root manifest lands and gives the validator a first-class node boundary to scope by instead (judgment call — see 943bb220 build report) | — | v1.1 | talos-t25 |
| Activity log append-only discipline is honor-system | Filesystem-level append-only enforcement OR file-hash check | v2.1 | argus |
| `inbox_project:` lifecycle not enforced — vault-entity with `inbox_project: null` breaks D7 | Validator rejects vault-entity without resolvable `inbox_project:` | v1.4.1 | argus |

---

## Extension from core + entity

*Where this capsule specializes [entity.capsule (1e9c3f7a)](entity.capsule.md).* vault-entity.capsule tightens: `subtype` must be `vault-entity`; `principal:` must resolve to a `subtype: person` entity (or rare `agent`); `name:` is the vault's public name. Adds optional fields: `members:`, `vault_class:`, `inbox_project:`, `activity_log:`, `founded_at:`, `federation_parent:`. All entity.capsule base rules inherited unchanged.

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
1. **Exactly one per vault-NODE** (singleton invariant, reframed per-vault-node)
2. Principal grounds at a person (typically; rare `agent` exception)
3. Vault-entity not archivable while vault is live
4. Membership optional + additive
5. **D7 enforces through this primitive** — every work-item `member_of` traces to the vault-entity's project tree
6. Activity log append-only

**Pitfalls:**
- Authoring a second vault-entity in the same vault-node → Rule 1 violation; reject
- Principal not grounded at a person → untraceable action chains
- Vault-inbox not authored before Gate 3 closes → D7 enforcement breaks
- `members:` used as authority claim → membership is compositional (per team.capsule precedent)
- `state: archived` on live vault-entity → signals whole-vault dissolution; rare + intentional only

**Worked examples:**
- [Argo vault entity (7f5b1d83)](../../vault/files/7f5b1d83.md) — `principal: 6c0e4a2b` (Mike); `inbox_project: 8a4c9e15`; authored at v1.4 Gate 3; `extraction_scope: argo-reference` (this studio's own live vault-node)
- [Starter "Your Tropo Vault" entity (7c3a8e91)](../../vault/files/7c3a8e91.md) — `extraction_scope: ship` (the template bundled for OTHER studios' vault-nodes at first-run, not a second instance in Argo's own node)
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
| 1.1 | 2026-07-07 | **RENAMED `vault` → `vault-entity`** (ADR-051 Fork 1, 18059aef; Mike-accepted 2026-07-06). File moved `tropo-vault.capsule.md` → `tropo-vault-entity.capsule.md`; `name: vault` → `name: vault-entity`; `subtype: vault` → `subtype: vault-entity` (governed rewrite of the 2 live instances, 7f5b1d83 + 7c3a8e91). UID `4d6e2f9a` PRESERVED — no dangling reference. Frees the `vault` name for the NEW vault-node manifest type (a1f7c750, tropo-vault.capsule.md). Singleton reframed per-vault-node (Mike's D7 ruling) generalizing the prior per-vault framing. Re-locked by Argus A127; executed by Talos T25 (dev-spec 943bb220). | talos-t25 |

---

*vault-entity capsule definition | LOCKED v1.1 | Argus A127 (rename authorization) + Talos T25 (execution) | 2026-07-07*
*"The vault-ENTITY is the vault as a principal. The vault (a1f7c750) is the vault as a mountable, contract-bearing node."*
