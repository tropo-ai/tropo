---
uid: 48f8c52c
type: project
status: evergreen
state: active
title: external-context
description: "Standing L0 root for governed mount projects — customer and Studio external folders that Tropo mounts and adopts. Identity lives here before any nav rendering. Shipped skeleton (extraction_scope: ship) per Mount Identity 7b1e0ae5; Mike lock of that spec is the canonical-L0 registry approval."
owner: mike
created: 2026-08-12
modified: 2026-08-12
modified_by: talos-t41
created_by: talos-t41
tags:
  - external-context
  - mount-identity
  - standing
  - evergreen
  - l0
file_ext: md
schema_version: 2
extraction_scope: ship
slug: external-context
lifecycle: standing
member_of: []
governed_by: 34e4cb0b
refs:
  - 7b1e0ae5
  - 50dd756e
---

# external-context

*Standing L0 container for governed mount projects. Identity before rendering.*

---

## Purpose

Every folder Tropo mounts gets a first-class `type: project` identity under this root.
The nav then renders those mounts as a real tree; without this root, mounted content
is either unresolvable or wrongly parented under Tropo Work.

## What belongs here

- One governed mount project per live or historical mount (`vault/files/<mount_uid>.md`)
- Nested folder mirrors parent into those mount projects (not into Tropo Work)

## What does not

- Federated team-vault mounts (`tropo-mount.py` / 409ef1cc) — different subsystem
- Internal Tropo Work trees

---

*Shipped 2026-08-12 by Talos T41 for locked Mount Identity 7b1e0ae5. Capsule note:
project.capsule §Template birth uses `status: evergreen` for standing structural
containers; §Sub-patterns says `active` — followed §Template; flag for Argus.*
