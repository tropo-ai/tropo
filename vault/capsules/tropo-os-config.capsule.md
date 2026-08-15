---
uid: 0b379424
type: capsule-definition
capsule_kind: meta
title: "os-config — Capsule Definition"
version: '1.1'
status: locked
locked_by: mike-maziarz
locked_at: '2026-07-13'
lock_note: "Mike verbatim 2026-07-13, live in session: 'lock both of those, then proceed with your work.' Locked with the capsule-of-capsules (38c63381) as the second and third capsules through the closed-registry gate."
owner: argus
author: argus-a130
created: '2026-07-13'
created_by: argus-a130
modified: '2026-08-09'
modified_by: argus-a147
v1_1_s4_lock_break: "Mike authorized Argus to proceed 2026-08-09 after S4 review. Aligns the capsule with the locked S4 single-source cut: Tier-1 canonical os-config 8f6ea459 retires; .tropo/boot-config.md points to canonical playbook 99341618; Tier-2 cf8c3be9 remains the sole live os-config instance. Adds the removal direction to governance and updates pairing validation. No new tier or mint path."
schema_version: 2
extraction_scope: ship
governed_by: 8dd772a0
provenance_note: "Authored per the Mike-walked Type Disposition sheet (5dcbadbd Table A row 8, verdict GOVERN — 'these are the boot contract itself; tiny capsule, kernel-class'). Follows the capsule-of-capsules mold (38c63381, Mike-locked 2026-07-13). S2 activation 0d9f89bc."
tags: [capsule-definition, os-config, boot-contract, kernel-class, governed-autonomy-s2]
---

# os-config — Capsule Definition

## Intent

An **os-config** is a canonical Studio-specific boot-contract substrate. After
the S4 single-source cut, exactly one live instance exists by design:
`cf8c3be9` Tier 2. The former Tier-1 instance `8f6ea459` is retired; the Tier-1
kernel pointer resolves directly to canonical activation playbook `99341618`.
Creating or retiring an instance is boot-contract surgery under a Mike-locked
dev-spec, never a minting gesture.

## Required Frontmatter

| Field | Constraint |
|---|---|
| `uid` | 8-hex (existing: `8f6ea459`, `cf8c3be9`) |
| `type` | `os-config` (literal) |
| `tier` | `1` (retired historical Tier-1 instances only) or `2` (live Studio config) |
| `status` | `published` (live boot contract) → `retired` (superseded by a locked migration) |
| `version` | quoted; bumps only under boot-contract amendment authority |

## Optional Frontmatter

| Field | Purpose |
|---|---|
| `layer` | `vault` on Tier 2 (observed) |
| `canonical_substrate_uid` / pointer pairing fields | the two-file pattern linkage (pointer ↔ canonical) |

## Governance Rules

1. **Pointer integrity**: `.tropo/boot-config.md` resolves to canonical playbook
   `99341618`; `.tropo-studio/agent-boot.extension.md` resolves to the sole live
   os-config `cf8c3be9`. Both pointers stay minimal; shrink floors, never delete
   them.
2. **Amendments are boot-contract surgery**: any content change requires a Mike-locked dev-spec naming the file as committed substrate, and re-derivation of every fingerprinted downstream (digest/fast-path) via the canonical writer — `check_boot_derivation_fresh` must return green in the same gesture.
3. **No tier by accretion**: a new os-config instance means a new boot-contract
   tier — an architecture decision (ADR-class + Mike lock), never convenience.
4. **Removal is governed too**: retiring an os-config requires the same locked
   boot-contract authority, a zero-content-loss audit, and an atomic pointer
   repoint to a retained canonical.

## Validation Checks

1. `capsule-yaml-parses` + tier ∈ {1, 2} (generic + enum)
2. Tier-1 pointer resolves `99341618`; Tier-2 pointer resolves live os-config
   `cf8c3be9`; every retired os-config names a retained `superseded_by`
3. `check_boot_derivation_fresh` — not this capsule's own check, but the gate every amendment must leave green (named here so a stranger amending cold knows the full contract, per pin-13 discipline)

## Inheritance

Extends `core.capsule` (ee814120). Governed by the capsule-of-capsules (38c63381). `meta`-kind: no §Template and no state-machine section by declaration — instances are not minted and their lifecycle is the boot-contract migration process itself (§Intent states why, per the mold's omission-is-a-declaration rule).

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.1 | 2026-08-09 | S4 alignment: one live Tier-2 os-config; Tier-1 points directly to canonical activation playbook; governed removal + pairing rules. | argus-a147 |
| 1.0 | 2026-07-13 | Initial authoring per walked GOVERN verdict (5dcbadbd row 8): schema from the two live instances; two-file integrity + amendment-authority + no-third-tier rules; meta-kind with declared omissions per the mold (38c63381). Status draft; awaits Mike lock. | argus-a130 |

---

*os-config capsule | v1.1 LOCKED | UID 0b379424 | S4 alignment by Argus A147*
