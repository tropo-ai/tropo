---
uid: 38c63381
type: capsule-definition
capsule_kind: meta
title: "capsule-definition — Capsule Definition (the capsule of capsules)"
version: '1.1'
template_enforced_from: '2026-07-13'
template_enforced_from_note: 'ADDED 2026-07-31 per core.capsule v1.9 §Governance Rule 11 (OPTIONAL `template_enforced_from`). Value is the date THIS capsule''s §Template leg was authored, derived from the first commit introducing the ## §Template heading in this file and cross-checked against this capsule''s own changelog/amendment note. Declares the mint-time contract''s start so instances predating the scaffold are not judged against it. One-line enforcement-scope metadata; no schema/enum/state-machine/template change, so no version bump (the extraction_scope sweep precedent).'
v1_1_amendment_note: "v1.0 → v1.1. Adds the OPTIONAL `instance_verifier_severity:` block — the declared grade for each check in the generic instance-verifier tier this capsule already defines (§The Three Legs, leg 3). Purely additive: no schema, enum, state machine, required section, or existing check changed. Written because the tier's grades were previously hardcoded in tool code with nothing governing them: the live Template + Body Shape check landed section-presence at FAIL, skipping the WARN→ERROR-ratchet the studio uses for every other new check, and there was no capsule declaration to contradict it. Grades now live here once and are read straight from this capsule, per the `enforced_enums` idiom (core.capsule §Governance Rule 8)."
status: locked
locked_by: mike-maziarz
locked_at: '2026-07-13'
lock_note: "Mike verbatim 2026-07-13, live in session: 'Lock it and proceed with the plan.' First capsule locked under the closed-registry law it itself defines (b600698e §9 Q1) — the fixed point set."
owner: argus
author: argus-a130
created: '2026-07-13'
created_by: argus-a130
modified: '2026-07-31'
modified_by: cursor-agent
schema_version: 2
extraction_scope: ship
governed_by: 8dd772a0
instance_verifier_severity:
  sections-present: WARN
  placeholder-survival: FAIL
  stray-mint-token: ERROR
  body-unreadable: FAIL
provenance_note: "Authored per the Mike-walked Type Disposition sheet (5dcbadbd, Table A row 1, verdict GOVERN — 'the registry's own backbone must be first through the gate') inside the S2 activation (0d9f89bc, dev-spec bba40cd7). The type capsule-definition had 65 instances and no governing capsule — the highest-irony row on the sheet. Awaits Mike's lock per the walked closed-registry law (b600698e §9 Q1)."
tags:
  - capsule-definition
  - meta-capsule
  - closed-registry
  - governed-autonomy-s2
---

# capsule-definition — Capsule Definition

*The capsule of capsules: the governance contract every capsule document in `vault/capsules/` must satisfy — including this one (see §Self-Hosting). Sixty-five capsule documents followed this shape by convention; from this capsule's lock forward, the convention is a contract.*

## Intent

Define what a **capsule document** is and must contain, so that: (1) every governed type's contract is itself governed — the closed registry (Governed Autonomy S2, `bba40cd7`) can resolve `type → capsule → legs` deterministically; (2) proposing a **new type** is a governed, mintable gesture with a scaffold, not a blank page; (3) capsule amendments follow one auditable pattern instead of sixty-five drifting habits.

A capsule is a **self-contained unit of work definition**: an agent holding a capsule has everything needed to create, work, and verify instances of its type correctly (Mike's founding intent, restated as the binding requirement).

## Capsule Kinds (the field that scopes every rule below)

Every capsule declares `capsule_kind:` in frontmatter — the rules bind by kind:

| Kind | What it governs | Mintable instances? | Three-legs rule |
|---|---|---|---|
| `instance-type` | A type agents create records of (`document`, `note`, `task`, `dev-spec`, …) | **Yes** — via `mint file --type <type>` | **BINDS**: schema + template + verifier required for mint to accept the type |
| `meta` | OS structure, not instances (`core`, `kernel`, `events`, `vault`, `node`, this capsule) | No | Schema leg only; template/verifier not applicable |
| `convention` | A substrate convention outside `vault/files/` (`playbook-run` → `playbook-runs/`, `activation-log` → sa.* records, `loop-run`) | No (instances live outside the index by design) | Schema leg + the convention's own verification path; no mint template |

*(Un-kinded capsules default to `instance-type` if their type has index records, else `meta` — the migration sweep stamps explicit kinds; the default exists so the rule is total, not so it is relied on.)*

## Required Frontmatter (every capsule document)

| Field | Constraint |
|---|---|
| `uid` | 8-hex, minted via the ADR-050 chokepoint |
| `type` | `capsule-definition` (literal) |
| `capsule_kind` | enum per §Capsule Kinds |
| `title` | `"<type-name> — Capsule Definition"` pattern |
| `version` | quoted semver-ish string; bumps on every amendment |
| `status` | enum: `draft` → `locked` (Mike) → `retired` (tombstone-in-place per the how-to precedent; never deleted) |
| `owner` | the accountable agent slug |
| `created` / `created_by` / `modified` / `modified_by` | standard provenance |
| `v<N>_amendment_note` | one per version bump — what changed, under what authority (see §Governance Rules) |

## Required Body Sections (in canonical order)

1. `## Intent` — what the type is FOR, one or two paragraphs
2. `## Required Frontmatter` — the instance schema (table), including every **enforced enum** with its full value set
3. `## Optional Frontmatter` — table, each field with purpose
4. `## State Machine` — instance lifecycle: states, legal transitions, the legal **birth value** (instance-type kinds)
5. `## Governance Rules` — numbered, binding
6. `## Validation Checks` — what the verifier reads; each check named
7. `## §Template` — **instance-type kinds only**: the mint-stamped scaffold per the Template-Leg Contract (`b933eafb`)
8. `## Inheritance` — what it extends (`core.capsule` ee814120 is the instance-floor root) and what patterns on it
9. `## Changelog` — one row per version, newest first, never edited retroactively

*(`meta` and `convention` kinds may omit 3/4/7 where genuinely inapplicable — omission is a declaration, not an oversight, and the §Intent must say why.)*

## The Three Legs (the closed-registry criterion — S2, walked law b600698e §9 Q1)

An `instance-type` is **governed** — and therefore mintable — when its capsule carries:

1. **Schema** — §Required Frontmatter + §State Machine + enforced enums (what a valid instance IS)
2. **Template** — §Template per the Template-Leg Contract (what mint STAMPS; placeholders consumed by the work)
3. **Verifier** — §Validation Checks readable by the generic instance verifier (`check-one`): placeholder survival, section presence, enum validity, `capsule_version` stamp — plus any type-specific checks, which live HERE, with their type, not bolted onto the global monolith

`mint file --type <T>` resolves T's capsule and **refuses** when the capsule is absent, `status: draft`/`retired`, or missing a required leg — naming the missing piece and the cure: *propose the capsule (mint one from §Template below) → Mike locks.* The refusal is the registry's closure; there is no separate edict.

## Governance Rules

1. **New types enter by proposal, permanently** (Mike-locked, b600698e §9 Q1): a new type = a new capsule document, minted from this capsule's §Template, reviewed, **locked by Mike**. No agent — any class, any generation — creates a type by writing `type:` frontmatter alone.
2. **Locked capsules amend only under authority**: an amendment to a `status: locked` capsule requires a Mike-locked dev-spec naming it as committed substrate (precedent: dev-spec capsule v1.2–v1.4; design-brief v3.3). Every amendment = version bump + `v<N>_amendment_note` + changelog row, additive and non-breaking unless the authorizing spec says otherwise.
3. **Retirement is tombstone-in-place** (the how-to precedent, v1.60): `status: retired` + `retired_at/by/via` naming the authority and evidence. The file stays readable; the registry stops resolving it; history is never rewritten.
4. **One capsule per type; one type per capsule.** The capsule's filename (`tropo-<type>.capsule.md`) must match the type string it governs exactly — the publish-pipeline dot/dash mismatch (5dcbadbd Table A row 5) is the defect class this rule ends.
5. **Self-containment is the bar**: a stranger holding only the capsule (plus core.capsule it extends) can create, work, and verify a correct instance cold. If the capsule needs a companion explainer, the capsule is incomplete.

## Validation Checks

1. `capsule-yaml-parses` — frontmatter is valid YAML with all §Required Frontmatter fields (ERROR)
2. `capsule-kind-declared` — `capsule_kind` present and in-enum (WARN until the kind-stamping sweep completes; ERROR-ratchet after)
3. `capsule-sections-present` — required body sections per kind (WARN → ERROR-ratchet, same schedule)
4. `capsule-filename-type-match` — filename type-string == governed type (ERROR; the rule-4 net)
5. `instance-type-has-legs` — `instance-type` + `status: locked` ⇒ all three legs present (**this is the check S2's mint refusal reads**; lands with the S2 build)
6. `capsule-changelog-current` — a changelog row exists for the frontmatter `version` (WARN — the v3.2 missing-row class)

## Generic Instance-Verifier Checks (v1.1 amendment 2026-07-31)

The checks above grade **capsule documents**. This section grades the *other* tier this capsule defines: the **generic instance verifier** (§The Three Legs, leg 3) that runs over every *instance* of any type carrying a §Template leg — `check-one` per-entry, and the validator's Live Template + Body Shape pass in bulk. Type-specific instance checks still live on their own type's capsule; only the four generic-tier checks are graded here, because there is exactly one of each across all types and duplicating the grade per type is how grades drift.

| Check | What it reads | Grade |
|---|---|---|
| `sections-present` | Every fixed-title §Template heading carrying a REQUIRED placeholder survives, by exact title, in an instance **minted from that leg** | `WARN` → ERROR-ratchet once the substrate is cured |
| `placeholder-survival` | No `&lt;!-- REQUIRED: … --&gt;` placeholder survives to verification (escaped here so this capsule does not trip its own check) | `FAIL` (deterministic INCOMPLETE per the Template-Leg Contract `b933eafb`) |
| `stray-mint-token` | No `<<MINT:*>>` token survives in a minted file | `ERROR` (tool defect, not an authoring gap — `b933eafb`) |
| `body-unreadable` | The instance's canonical file reads as UTF-8 | `FAIL` |

The machine-readable `instance_verifier_severity:` block in this capsule's frontmatter carries the same four grades; **the block and this table MUST agree** — the block is what tools read, the table is what a reader is owed. Same contract as `enforced_enums` (core.capsule §Governance Rule 8): the capsule declares, the verifier reads it straight from the capsule, and no tool keeps a private second copy. A check this capsule does not grade is **not** silently defaulted: the verifier withholds its findings and reports the undeclared grade as an ERROR, so the gap is loud and self-curing.

**Why `sections-present` is WARN.** It rides the studio's standing WARN-then-ratchet discipline for any newly-landed check — land advisory, cure the substrate, then ratchet — the same schedule check 2 and check 3 above carry. It also fails softer by nature than its neighbours: a surviving placeholder or a stray mint token is unambiguous evidence of an incomplete or malformed mint, whereas an absent heading may equally mean the instance was never minted from the leg at all. Enforcement scope is bounded by each capsule's `template_enforced_from` (core.capsule §Optional Frontmatter); the ratchet to ERROR is a deliberate, separate amendment once the in-scope population is clean.

## §Template (the scaffold for PROPOSING a new type — the registry's front door)

*Stamped by `mint file --type capsule-definition`; `<<MINT:*>>` tokens only. Completing this scaffold IS drafting a type proposal; Mike's lock makes it law.*

~~~markdown
---
uid: <<MINT:uid>>
type: capsule-definition
capsule_kind: instance-type   # one of: instance-type | meta | convention — see the capsule-of-capsules §Capsule Kinds
title: "<!-- REQUIRED: <type-name> — Capsule Definition -->"
version: '0.1'
status: draft                  # Mike's lock flips this; mint refuses draft types
owner: <<MINT:author>>
author: <<MINT:author>>
created: '<<MINT:date>>'
created_by: <<MINT:author>>
modified: '<<MINT:date>>'
modified_by: <<MINT:author>>
schema_version: 2
capsule_version: '<<MINT:capsule_version>>'
governed_by: 8dd772a0
---

# <!-- REQUIRED: type-name --> — Capsule Definition

## Intent
<!-- REQUIRED: what this type is FOR and why it earns being a type rather than a field on an existing one (the earn-the-abstraction bar) -->

## Required Frontmatter
<!-- REQUIRED: the instance schema table, every enforced enum with its full value set -->

## Optional Frontmatter
<!-- OPTIONAL: table of optional fields (delete if none) -->

## State Machine
<!-- REQUIRED for instance-type: states, legal transitions, and the single legal BIRTH value -->

## Governance Rules
<!-- REQUIRED: numbered, binding -->

## Validation Checks
<!-- REQUIRED: what the verifier reads for this type — named checks -->

## §Template
<!-- REQUIRED for instance-type: the mint-stamped instance scaffold per the Template-Leg Contract (b933eafb) — frontmatter defaults valid-by-construction + body skeleton with consumable placeholders. Plant-test before lock: mint once into scratch → check-one passes with zero edits beyond placeholder consumption -->

## Inheritance
<!-- REQUIRED: extends core.capsule (ee814120); name any pattern_exemplar -->

## Changelog
| Version | Date | Change | Author |
|---------|------|--------|--------|
| 0.1 | <<MINT:date>> | Initial proposal. | <<MINT:author>> |
~~~

**Leg rules:** `status: draft` is the only legal birth value — a proposed type is refusable-by-construction until Mike locks it; the §Intent placeholder demands the earn-the-abstraction justification up front (the counterforce to type sprawl, structural).

## Inheritance

Extends nothing — this is the root of the capsule layer. `core.capsule` (ee814120) remains the root of the **instance** layer (the frontmatter floor every instance inherits); the two roots are complementary, not nested: core governs records, this governs the documents that govern records.

## Self-Hosting

This capsule is `type: capsule-definition` — it governs its own type and must satisfy its own contract. Verified at authoring: all required fields present, all required-for-`meta` sections present, filename matches governed type, changelog current. Every future amendment to this capsule re-runs that self-check; the capsule of capsules passing its own gate is the registry's fixed point.

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.1 | 2026-07-31 | **Generic instance-verifier grades declared.** Adds the optional `instance_verifier_severity:` frontmatter block + the §Generic Instance-Verifier Checks section that mirrors it in prose. Grades the four generic-tier checks this capsule already defines in §The Three Legs leg 3 (`sections-present` WARN→ratchet, `placeholder-survival` FAIL, `stray-mint-token` ERROR, `body-unreadable` FAIL). Purely additive — no schema, enum, state machine, required section, or capsule-document check changed. Closes the gap that let the Live Template + Body Shape check land `sections-present` at FAIL against no governing declaration. | cursor-agent |
| 1.0 | 2026-07-13 | Initial authoring per the Mike-walked GOVERN verdict (5dcbadbd row 1) inside the S2 activation (0d9f89bc). Defines capsule kinds (instance-type / meta / convention), the required capsule shape, the three-legs closed-registry criterion, the amendment/retirement law, six validation checks, and the new-type proposal §Template — the registry's front door. Status draft; awaits Mike's lock per the walked closed-registry law. | argus-a130 |

---

*capsule-definition capsule | v1.0 DRAFT — awaiting Mike's lock | UID 38c63381 | Governed Autonomy S2 (bba40cd7)*
*"The registry's backbone goes through the gate first. The capsule of capsules passing its own gate is the fixed point."*
