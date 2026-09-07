---
uid: 8c19ed59
type: capsule-definition
capsule_kind: instance-type
name: principal
title: "principal — Capsule Definition"
version: '1.1'
mint_mode: human
mint_template: vault/capsules/templates/principal.template.md
mint_template_version: '1.0'
mint_template_sha256: f757934f59ede925d6eec863899276ee4868299532178b404e6191277e6c5cce
mint_output_home: vault/files
supersedes_version: '1.0'
template_enforced_from: '2026-07-13'
template_enforced_from_note: 'ADDED 2026-07-31 per core.capsule v1.9 §Governance Rule 11 (OPTIONAL `template_enforced_from`). Value is the date THIS capsule''s §Template leg was authored, derived from the first commit introducing the ## §Template heading in this file and cross-checked against this capsule''s own changelog/amendment note. Declares the mint-time contract''s start so instances predating the scaffold are not judged against it. One-line enforcement-scope metadata; no schema/enum/state-machine/template change, so no version bump (the extraction_scope sweep precedent).'
status: locked
locked_by: mike-maziarz
locked_at: '2026-07-13'
lock_note: "Mike verbatim 2026-07-13, live in session: 'lock both of those, then proceed with your work.' Locked with the capsule-of-capsules (38c63381) as the second and third capsules through the closed-registry gate."
v1_1_amendment_lock_break: "v1.0 -> v1.1 bounded lock-break 2026-09-05 by argus-a171 on Mike's ruling at the v1.95 spec walk (plan f015ba71c711 decision 7(c); Spine A f015de6b3a18 AC4). Mike verbatim: 'Yes, absolutely amend. We tried to catch all the 8hex hard coded rules, you must update that.' Two changes: (1) mint_mode disabled -> human with a hash-bound companion template, so mint_file('principal') is the one governed birth door; Rule 1 names the ONE deliberate registration path a customer studio has — Po's arrival conversation, where the founder asked by name and answering IS the registration — and forbids every side-effect mint as before. (2) the uid constraint reads 'the uid as minted' (12-hex composite since 3d430852 Stage B; 8-hex on legacy records), never a hand-coded length; this row was one of the hard-coded 8-hex rules Mike named. No enum, state-machine, validation-check or slug-immutability change; the nine live records are untouched. Mint registry regenerated in the same commit."
owner: argus
author: argus-a130
created: '2026-07-13'
created_by: argus-a130
modified: '2026-09-05'
modified_by: argus-a171
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
| `uid` | the uid as minted via the ADR-050 chokepoint (`tropo-mint-id.py`) — 12-hex composite since 3d430852 Stage B (2026-08-31), 8-hex on legacy records; never a hand-coded length (v1.1) |
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

1. **Registration is deliberate**: principals are created when an actor genuinely enters the accountability graph (crew commissioning, human registration) — never as a side effect. **(v1.1, Mike-ruled 2026-09-05)** In a customer studio the one deliberate path is Po's arrival conversation (`activate.md` §1.5): the founder is asked their name and, by answering, registers — that answer IS the deliberate act this rule means, and it is minted through `mint_file('principal')`, the governed door, with `title` and `slug` filled from the answer. A principal minted anywhere else without a human's explicit, in-session word is the side effect this rule forbids.
2. **Slug immutability**: the slug is the resolution key for recorded attestations; it never changes post-creation. Retire and re-register rather than rename.
3. **Independence is checked against this type**: any gate requiring attestor ≠ executor resolves both sides here; a gate that accepts a non-principal attestor is defective.
4. **Retired ≠ recycled**: `status: retired`, file stays. Recycling a principal breaks every historical attestation that names it.

## Validation Checks

1. `check_principal_class_present` — every active principal carries an in-family `principal_class` (exists today; becomes this capsule's leg)
2. `check_principal_slug_unique` — slug uniqueness (exists today; becomes this capsule's leg)
3. Generic instance verifier: placeholders consumed, sections present, `capsule_version` stamped (lands with S2)

## §Template (v1.1 — companion scaffold; contract at [b933eafb](../../vault/files/b933eafb.md))

The single mint and verifier scaffold is the visible companion
[principal.template.md](templates/principal.template.md), hash-bound in this capsule's
frontmatter. It births at the only legal value `status: active`, carries the class
comment so an author never guesses the family, and requires `slug` — a surviving
`<!-- REQUIRED: -->` is a deterministic INCOMPLETE. The fenced copy below is the
reference rendering; the companion is the one the mint reads.

*Stamped by `mint file --type principal`; `<<MINT:*>>` tokens only.*

~~~markdown
---
uid: <<MINT:uid>>
type: principal
title: "<<MINT:title>>"
principal_class: human   # one of: human | agent-executive | agent-concierge | agent-<role>
slug: "<!-- REQUIRED: unique resolution key, kebab-case, immutable -->"
status: active
created: '<<MINT:date>>'
created_by: <<MINT:author>>
created_by_activation_uid: <<MINT:activation_uid>>
modified: '<<MINT:date>>'
modified_by: <<MINT:author>>
schema_version: 2
capsule_version: '<<MINT:capsule_version>>'
governed_by: 8dd772a0
---

# <<MINT:title>>

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
| 1.1 | 2026-09-05 | Mike-ruled bounded lock-break at the v1.95 walk (plan f015ba71c711 decision 7(c); Spine A AC4): `mint_mode: human` with the hash-bound companion `templates/principal.template.md`; Rule 1 names Po's arrival conversation as the one deliberate customer-studio path; the uid row reads "the uid as minted" (composite 12-hex / legacy 8-hex) instead of a hard-coded 8-hex. Nine live records untouched. | argus-a171 |

---

*principal capsule | v1.1 | UID 8c19ed59 | mold: 38c63381 | S2 (bba40cd7) | v1.1 lock-break Mike-ruled 2026-09-05 at the v1.95 walk*
