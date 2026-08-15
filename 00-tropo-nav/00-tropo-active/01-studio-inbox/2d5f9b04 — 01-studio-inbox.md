---
uid: 2d5f9b04
type: project
title: 01-studio-inbox
description: 'Catch-all project for captured-but-unfiled work in this vault. D7 enforcement target: every work-item without explicit project membership routes here. Refile to specific projects as context emerges. Naming follows numerical-prefix convention (per Vela V35''s how-naming-conventions-work.md). v1.6 cycle merged the prior dual-entry split (8a4c9e15 archived as superseded; 2d5f9b04 is now the single canonical vault-inbox primitive that ships AND Argo uses for itself).'
owner: 7c3a8e91
state: active
status: active
lifecycle: standing
member_of: []
slug: 01-vault-inbox
created: 2026-04-29
modified: 2026-05-05
modified_by: argus-a44
v1_6_changes:
  - '2026-05-05: title vault-inbox → 01-vault-inbox (numerical-prefix convention)'
  - '2026-05-05: slug updated vault-inbox → 01-vault-inbox to match'
  - '2026-05-05: now the single canonical vault-inbox primitive — ships in user vaults AND used by Argo dev-vault for itself; 16 children reparented from archived 8a4c9e15 via merge-vault-inbox-2026-05-05.py sweep'
created_by: vela-v36
schema_version: 2
capsule_version: '2.3'
extraction_scope: ship
governed_by: 34e4cb0b
tags:
  - project
  - vault-inbox
  - standing
  - fresh-install
  - d7-enforcement
  - orphan-catcher
  - v1.4.1
refs:
  - 7c3a8e91
  - 4b6e2c8a
  - 4d6e2f9a
---

# vault-inbox

*Top-level vault-entity-owned project. Catch-all for captured-but-unfiled work in this vault. Authored 2026-04-29 as part of v1.4.1 ship.*

---

## Purpose

The vault-inbox catches work-items that are captured but not yet filed into specific projects. Per the [Tropo Work substrate](../../vault/files/d61ce0a7.md) **D7 invariant:** every work-item must `member_of` at least one vault-entity-owned project. This is that project. Orphans land here.

**Typical landing scenarios:**

- You jot a note without specifying a project — `member_of:` defaults to `[2d5f9b04]`
- An agent captures an insight during a session — lands here unless explicitly routed
- A work-item gets created programmatically with no project context — vault-inbox is the fallback

## Lifecycle

- **`lifecycle: standing`** — evergreen; never archives while the vault is live
- **`stage: build`** — always active; the inbox is by nature a perpetual work-in-progress bucket
- **`state: active`** — visible in default views as the orphan-catcher

## What to do with inbox items

Work-items in vault-inbox are not meant to STAY here. The invariant is "has a vault-entity-project home"; the inbox satisfies it, but items should be re-filed to more specific projects as context emerges.

**Grooming pattern:** periodically review vault-inbox contents. For each item:
- Belongs to an existing project? → update `member_of:` to that project; remove vault-inbox membership
- Worth doing as standalone work? → either complete it inline OR move it to a new project that owns it
- No longer relevant? → `state: archived` with `resolution:`

## Governance

Governed by [project.capsule v2.3 (34e4cb0b)](vault/capsules/tropo-project.capsule.md). Key rules:

- **Rule 1 (top-level enforcement):** `member_of: []` is legal because `owner:` chains to the vault-entity ([7c3a8e91](7c3a8e91.md)) whose principal grounds at a person.
- **Lifecycle: standing** — no `done` terminal; stays active indefinitely.

## Relationship to the vault-entity

This project is referenced by the vault-entity's `inbox_project:` field ([7c3a8e91](7c3a8e91.md)). The vault-entity and vault-inbox are paired artifacts — both ship in every fresh install to satisfy D7 on day one.

---

*Starter vault-inbox | Authored 2026-04-29 by vela-v36 as part of v1.4.1 P0-3 remediation ([task a1f5b8d2](a1f5b8d2.md)) | Replaces the dangling 8a4c9e15 reference cold-boot 097 surfaced.*
*"Orphans catch here. Grooming routes them onward."*
