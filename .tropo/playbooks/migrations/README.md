---
member_of:
  - "76bab75f"   # tropo-playbooks (v1.12 backfill 2026-05-08 — minimal frontmatter prepended)
---

#.tropo/playbooks/migrations/

*Migration playbooks — the pattern for moving a vault from one Tropo-OS version to another.*

---

## What lives here

Migration playbooks. One file per version transition, one-shot. A migration playbook runs during an update and transforms a vault's state from the prior version's shape to the new version's shape. Schema bumps, field renames, folder reorganizations, frontmatter rewrites — all land here.

A migration playbook is the opposite of a product playbook: product playbooks live forever and run many times; migrations run once per vault, then become historical.

## Naming

- Version-scoped: `v<NNN>-<slug>.playbook.md` (e.g., `v120-member-of-rewrite.playbook.md`)
- Topic-scoped: `migrate-<topic>.playbook.md` for ongoing small transitions

## Governance

- **Owner:** Argus (architecture changes drive migrations)
- **Triggered by:** `apply-update.playbook.md` during version bumps
- **Lifecycle:** one-shot per vault; the apply-update pipeline records completion so a migration never runs twice against the same vault

## This folder in v1.1

v1.1 is the first public release. No external users are upgrading from earlier versions — internal pre-v1.1 migration playbooks are not shipped. This folder ships empty except for this README. Future releases will add migration playbooks here as schema or structure changes require them.

## When you (an agent or user) might touch this folder

- **Upgrading your vault to a new Tropo-OS version:** run `apply-update.playbook.md`. It will check here for version-matched migrations and execute them in order. Do not run migration playbooks manually; the update pipeline orders them correctly.
- **Building a new Tropo-OS release:** if your release ships with schema changes, write a migration playbook here that transforms a prior-version vault to the new shape. Document the reverse path if rollback is supported.
- **Reading for context:** the `migrations/` folder is a record of every structural change Tropo-OS has required. It is a useful history document.

---

*`.tropo/playbooks/migrations/README.md` | Concept carrier for v1.1 | Tropo-OS*
