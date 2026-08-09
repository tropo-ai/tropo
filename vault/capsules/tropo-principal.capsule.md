---
uid: 8c19ed59
type: capsule-definition
capsule_kind: instance-type
title: "principal — Capsule Definition"
version: '1.0'
template_enforced_from: '2026-07-13'
template_enforced_from_note: 'ADDED 2026-07-31 per core.capsule v1.9 §Governance Rule 11 (OPTIONAL `template_enforced_from`). Value is the date THIS capsule''s §Template leg was authored, derived from the first commit introducing the ## §Template heading in this file and cross-checked against this capsule''s own changelog/amendment note. Declares the mint-time contract''s start so instances predating the scaffold are not judged against it. One-line enforcement-scope metadata; no schema/enum/state-machine/template change, so no version bump (the extraction_scope sweep precedent).'
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
provenance_note: "Authored per the Mike-walked Type Disposition sheet (5dcbadbd Table A row 3, verdict GOVERN — corrected from the recon's fold→entity lean because the dev-spec capsule's attestation machinery REQUIRES type:principal resolution). Follows the capsule-of-capsules mold (38c63381, Mike-locked 2026-07-13). S2 activation 0d9f89bc."
tags: [capsule-definition, principal, attestation, governed-autonomy-s2]
---

# principal — Capsule Definition

## Intent

A **principal** is a registered actor the governance machinery can resolve and hold accountable: the identity anchor behind `attested_by:`, `locked_by:`, `human_signoff`, and separation-of-duties checks. When a gate needs "an independent registered principal who is NOT the executor," `_resolve_principal_uid` resolves against this type — which is why principal is a first-class type and not a fold into `entity`: folding would break a locked contract (dev-spec capsule Rule 8). Nine live records: crew executives, the concierge classes, and humans.

## Required Frontmatter

| Field | Constraint |
|---|---|
| `uid` | 8-hex, minted via the ADR-050 chokepoint |
| `type` | `principal` (literal) |
| `title` | `"<Name> — <Role>"` |
| `principal_class` | `human` or the `agent-*` family (observed: `agent-executive`, `agent-concierge`) — the validator's L0a contract (`check_principal_class_present`, WARN→ERROR ratchet) |
| `slug` | unique across all principals (`check_principal_slug_unique`) — the resolution key |
| `status` | `active` → `retired` (a retired principal stays resolvable for historical attestations; never deleted) |
| `created` / `created_by` | provenance |

## Optional Frontmatter

| Field | Purpose |
|---|---|
| `party_uid` | messaging-axis UID, for principals that are also messaging parties |
| `agent_root_uid` | lineage-axis UID, for agent-class principals |
| `refs` | related identity substrate (unified entry, status card) |

## State Machine

`active` → `retired`. Birth value: `active`. No other states — a principal either can or can no longer *newly* attest; past attestations remain valid against retired principals (history is never orphaned).

## Governance Rules

1. **Registration is deliberate**: principals are created when an actor genuinely enters the accountability graph (crew commissioning, human registration) — never as a side effect.
2. **Slug immutability**: the slug is the resolution key for recorded attestations; it never changes post-creation. Retire and re-register rather than rename.
3. **Independence is checked against this type**: any gate requiring attestor ≠ executor resolves both sides here; a gate that accepts a non-principal attestor is defective.
4. **Retired ≠ recycled**: `status: retired`, file stays. Recycling a principal breaks every historical attestation that names it.

## Validation Checks

1. `check_principal_class_present` — every active principal carries an in-family `principal_class` (exists today; becomes this capsule's leg)
2. `check_principal_slug_unique` — slug uniqueness (exists today; becomes this capsule's leg)
3. Generic instance verifier: placeholders consumed, sections present, `capsule_version` stamped (lands with S2)

## §Template

*Stamped by `mint file --type principal`; `<<MINT:*>>` tokens only. A surviving `<!-- REQUIRED: -->` = deterministic INCOMPLETE.*

~~~markdown
---
uid: <<MINT:uid>>
type: principal
title: "<!-- REQUIRED: <Name> — <Role> -->"
principal_class: agent-executive   # one of: human | agent-executive | agent-concierge | agent-<role>
slug: "<!-- REQUIRED: unique resolution key, kebab-case, immutable -->"
status: active
created: '<<MINT:date>>'
created_by: <<MINT:author>>
schema_version: 2
capsule_version: '<<MINT:capsule_version>>'
governed_by: 8dd772a0
---

# <!-- REQUIRED: Name — Role -->

## Who
<!-- REQUIRED: one paragraph — who this actor is and why they enter the accountability graph -->

## Accountability scope
<!-- REQUIRED: what this principal can attest/lock/sign (e.g. human signoff, independent attestation, cycle verification) -->
~~~

**Leg rules:** `status: active` is the only birth value; `slug` is immutable post-mint; the class comment carries the live family so an author never guesses.

## Inheritance

Extends `core.capsule` (ee814120). Governed by the capsule-of-capsules (38c63381).

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-07-13 | Initial authoring per walked GOVERN verdict (5dcbadbd row 3): schema from the 9 live records + the two existing validator checks adopted as verifier legs; template + state machine per the mold (38c63381). Status draft; awaits Mike lock. | argus-a130 |

---

*principal capsule | v1.0 DRAFT | UID 8c19ed59 | mold: 38c63381 | S2 (bba40cd7)*
