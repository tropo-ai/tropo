---
uid: 0b379424
type: capsule-definition
capsule_kind: meta
title: "os-config — Capsule Definition"
version: '1.0'
status: locked
locked_by: mike-maziarz
locked_at: '2026-07-13'
lock_note: "Mike verbatim 2026-07-13, live in session: 'lock both of those, then proceed with your work.' Locked with the capsule-of-capsules (38c63381) as the second and third capsules through the closed-registry gate."
owner: argus
author: argus-a130
created: '2026-07-13'
created_by: argus-a130
modified: '2026-07-13'
modified_by: argus-a130
schema_version: 2
extraction_scope: ship
governed_by: 8dd772a0
provenance_note: "Authored per the Mike-walked Type Disposition sheet (5dcbadbd Table A row 8, verdict GOVERN — 'these are the boot contract itself; tiny capsule, kernel-class'). Follows the capsule-of-capsules mold (38c63381, Mike-locked 2026-07-13). S2 activation 0d9f89bc."
tags: [capsule-definition, os-config, boot-contract, kernel-class, governed-autonomy-s2]
---

# os-config — Capsule Definition

## Intent

An **os-config** is a canonical boot-contract substrate: the Tier-1 (OS) and Tier-2 (Studio) configuration documents every agent activation resolves through. Exactly two live instances exist by design (`8f6ea459` Tier 1, `cf8c3be9` Tier 2), each paired with a kernel thin-pointer carrying a degraded-mode floor (the two-file pattern). This capsule is `meta`-kind: instances exist and are indexed, but **creating one is boot-contract surgery under a Mike-locked dev-spec — never a minting gesture.** The kind table's "not mintable" means exactly that; it does not mean "no records."

## Required Frontmatter

| Field | Constraint |
|---|---|
| `uid` | 8-hex (existing: `8f6ea459`, `cf8c3be9`) |
| `type` | `os-config` (literal) |
| `tier` | `1` (OS-kernel) or `2` (Studio/vault) — the boot-chain position |
| `status` | `published` (live boot contract) → `retired` (superseded by a locked migration) |
| `version` | quoted; bumps only under boot-contract amendment authority |

## Optional Frontmatter

| Field | Purpose |
|---|---|
| `layer` | `vault` on Tier 2 (observed) |
| `canonical_substrate_uid` / pointer pairing fields | the two-file pattern linkage (pointer ↔ canonical) |

## Governance Rules

1. **Two-file integrity**: every os-config canonical has exactly one kernel thin-pointer (`.tropo/boot-config.md` ↔ Tier 1; `.tropo-studio/agent-boot.extension.md` ↔ Tier 2). The pointer carries a *gates-only* degraded floor — shrink floors, never delete them (real safety mechanism; boot-audit 2026-07-11).
2. **Amendments are boot-contract surgery**: any content change requires a Mike-locked dev-spec naming the file as committed substrate, and re-derivation of every fingerprinted downstream (digest/fast-path) via the canonical writer — `check_boot_derivation_fresh` must return green in the same gesture.
3. **No third tier by accretion**: a new os-config instance means a new boot-contract tier — an architecture decision (ADR-class + Mike lock), never an authoring convenience.
4. **Single-source direction (S4)**: the Governed Autonomy S4 stream will shrink the pointer floors to gates-only stubs; this capsule inherits that outcome rather than pre-legislating it.

## Validation Checks

1. `capsule-yaml-parses` + tier ∈ {1, 2} (generic + enum)
2. Two-file pairing resolves both directions (pointer names canonical uid; canonical exists) — composes with the existing boot-chain checks
3. `check_boot_derivation_fresh` — not this capsule's own check, but the gate every amendment must leave green (named here so a stranger amending cold knows the full contract, per pin-13 discipline)

## Inheritance

Extends `core.capsule` (ee814120). Governed by the capsule-of-capsules (38c63381). `meta`-kind: no §Template and no state-machine section by declaration — instances are not minted and their lifecycle is the boot-contract migration process itself (§Intent states why, per the mold's omission-is-a-declaration rule).

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-07-13 | Initial authoring per walked GOVERN verdict (5dcbadbd row 8): schema from the two live instances; two-file integrity + amendment-authority + no-third-tier rules; meta-kind with declared omissions per the mold (38c63381). Status draft; awaits Mike lock. | argus-a130 |

---

*os-config capsule | v1.0 DRAFT | UID 0b379424 | mold: 38c63381 | S2 (bba40cd7)*
