---
subsystem_hub:
  - "2d083137"
uid: 8a4e21c5
name: "subsystem-hub"
type: capsule-definition
extends: core
version: 1.6
supersedes_version: "1.5"
v1_6_amendment_note: "v1.5 → v1.6 amendment 2026-05-24 by Argus A81 captain-mode per v1.52 A-lane A10 closure (cycle brief 404ac636 §3 A-lane substrate-hygiene; Path 2 ticket 8096ccdb absorbed) + stm-a81-003 strong-lean calibration. Strengthens §1 body-section requirement: 'What This Subsystem Covers' must explicitly enumerate **In scope** + **Not in scope** (was: free-form prose mentioning what does NOT belong). Defect-class fix: Tropo Documentation hub (f87e33f0) drifted 11 entries in 2026-05-10 (8 Substack articles + Reading-Notes guide + Substack Launch Style + Studio Manifesto) because the hub's scope statement didn't formally name what doesn't belong. Free-form prose accumulates everything ambiguous; structured enumeration prevents drift by construction. Composes with Captain's Briefing v3.0 §Structural-Enforcement Requirement 1 (pristine subsystem documentation across three tiers); v1.53 Orpheus doc-pipeline cycle implements the structured enumeration across all 9 active hubs. Validator Check 2 amended (still v1.10 deferred per existing pattern) to require both subsections present in §1. Companion v1.6 §1 body-template at history file."
tier: os
author: tropo
created: 2026-04-20
modified: 2026-05-25
created_by: argus-a29
modified_by: orpheus-o11
v1_6_implementation_note: "v1.6 schema strengthening (Argus A81 2026-05-24) implemented across 6 active hubs by Orpheus O11 on 2026-05-25 during v1.53 Lane D D1: Tropo Work (2d083137); Tropo Governance (8dd772a0; 25-cycle catch-up); Tropo Playbooks (76bab75f; 25-cycle); Tropo Library (1aba710c; 43-cycle); Tropo Documentation (f87e33f0; defect-class fix exemplar — 5 legacy scope blocks consolidated to single v1.6 §1); Tropo Rendering (dbc1cbbf; 40-cycle). All 6 hubs now carry In scope + Not in scope + Edge cases enumeration; Current State currency through v1.52. §6 worked-example narrative added documenting the implementation pattern."
status: locked
locked_by: argus-a46
locked_at: 2026-05-05
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
history_file: 17867222
last_body_refactor: 2026-05-11
aligned_with: 74fd9b61   # Board Reconciliation v0.3 (cross-capsule consistency)
aligned_with_v1_4: fd2d9e77   # v1.8 design brief — Capability Subsystem Membership (v1.4 amendment source)
composes_with: 34e4cb0b   # project.capsule — hubs ARE typed projects
pattern_family: 34e4cb0b   # subsystem-hub is a typed project shape
verifier_deferred_to: "1.10.0"
member_of:
  - "8dd772a0"   # tropo-governance
tags: [capsule-definition, subsystem-hub, governance, concentrator-not-archive]
---

# subsystem-hub — Capsule Definition v1.6

| Relation | Target |
|---|---|
| Governed by | [capsule-definition meta (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Board Reconciliation v0.3 (74fd9b61)](../../vault/files/74fd9b61.md) (cross-capsule consistency) |
| Pattern family | [project.capsule (34e4cb0b)](project.capsule.md) |
| Extends | `core` |
| Composes with | [project.capsule (34e4cb0b)](project.capsule.md); [release.capsule (b19e8d43)](release.capsule.md); [release-plan.capsule (a3f1e7b2)](release-plan.capsule.md) |

---

## 1. Intent

A `subsystem-hub` is the governance-backed concentrator for one Tropo subsystem. It exists for **one reader question**: *"what is the truth-today state of subsystem X?"* The hub body answers. The cascade (the project-tree-rendered transitive inventory of all artifacts member_of the subsystem; lives at `vault/00-cascade-<hub-uid>.jsonl`) gives the full work inventory; the ADR set holds historical decisions; the graph index holds relationships; the daily-health-report holds health snapshots. **The hub points at all of them; it does not duplicate them.**

A hub is a typed project — `type: project` with specific body-shape rules layered on top. This capsule documents the additional contract that applies to projects serving as subsystem hubs, identified by graph position (direct children of [tropo-subsystems root (aae9a37b)](../../vault/files/aae9a37b.md)).

Failure mode prevented: hubs drifting into archive shape that duplicates ADRs / daily-health-report / graph-index content; reader confusion about which surface is canonical for which question.

---

## 2. Schema

### Scope — Which Projects Are Hubs?

A project is a subsystem hub when all three hold:

1. **Graph position:** `member_of: [aae9a37b]` — direct child of [tropo-subsystems root](../../vault/files/aae9a37b.md).
2. **Lifecycle:** `lifecycle: standing` — evergreen; never reaches `stage: done`.
3. **Role declaration:** frontmatter `tags:` includes `subsystem-hub`.

Projects not meeting all three are ordinary projects. The three conditions are checkable via registry query; the tag is the explicit role signal.

**Transitional tolerance:** mechanical validator (deferred to v1.10) will accept legacy `subsystem` tag in place of `subsystem-hub` and emit WARNING (not ERROR) prompting migration. v1.7-v1.9 honor this on agent-discipline.

**Live roster:** [`collections/subsystem-hubs.collection.md`](../../collections/subsystem-hubs.collection.md). The capsule does not enumerate instances inline (a v1.0 anti-pattern).

### Required Frontmatter (beyond `project.capsule`)

| Field | Type | Constraint |
|---|---|---|
| `lifecycle` | literal | Must be `standing` |
| `tags` | array | MUST include `subsystem-hub` |
| `subsystem_name` | string | Canonical short name (e.g., `tropo-work`, `tropo-agents`, `tropo-library`, `tropo-link`). Lowercase, hyphens. |
| `subsystem_scope` | string | ≤ 200 chars. One-sentence description of what this subsystem covers vs what it does not. |
| `member_of` | array | MUST include `aae9a37b` (tropo-subsystems root); may include additional parents. |
| `last_release_reflected` | semver string OR `null` | Most recent release whose ship work is reflected in `release_history` + Change Log (e.g., `"1.7.0"`). MAY be `null` for newly-created hubs that have not yet ridden a release ship; MUST be set by close of first release after creation. |
| `release_history` | array | Append-only event log of release impacts. Each entry: `{release_uid, release_version, summary, registry_uid, streams_touched?, derived_from?}`. Bidirectional pair with [`subsystem-registry.jsonl`](../../subsystem-registry.jsonl) — registry is cross-cut; this field is per-hub record. `derived_from` (v1.4 OPTIONAL): `"manual_authoring"` for v1.7-and-earlier rows; `"capabilities_touched"` for v1.8+ rows derived via 1-hop `member_of:` graph traversal per release.capsule v3.4 Rule 12. **Append-order = chronological; never edit prior entries.** May be empty `[]` for newly-created hubs. v1.8+ rows DERIVED at B6 atomic-triangle commit; manual authoring of v1.8+ rows = Rule 12 violation. |
| `aligned_with` | UID | On a **hub instance**, MUST equal `8a4e21c5` (this capsule's UID) — cross-capsule consistency back-reference; pattern: every governed-by-this-capsule instance carries the back-reference. Distinct from THIS capsule's own `aligned_with: 74fd9b61` (capsule-level pointer to Board Reconciliation, not instance-level pointer). |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `subsystem_acronym` | string | Historical TWS/TPS/TVS/TAS/TBS/TLGS acronyms; retained for legacy lookup; deprecated forward. |
| `supersedes` | array of UIDs | Hubs merged into this one. Bidirectional pair with `superseded_by:`. |
| `superseded_by` | UID | Successor hub if archived during merger. |

**Unknown frontmatter tolerance.** Hubs MAY carry frontmatter fields beyond declared §Required + §Optional (e.g., `current_subsystem_version`, instance-specific tracking). Validator (when it lands at v1.10) treats unknown fields as informal data + does NOT error on presence. Hubs accumulating informal fields SHOULD consider promotion to declared-optional in future capsule amendment.

### Required Body Sections (4 sections)

Every subsystem-hub body MUST contain these four sections:

**1. `## What This Subsystem Covers`** — Two REQUIRED subsections (v1.6 strengthening per A10 closure 2026-05-24):

- **`### In scope`** — explicit bullet list of artifact classes the hub holds canonically (system-of-record material). Each bullet names a class + one-line rationale.
- **`### Not in scope`** — explicit bullet list of artifact classes that do NOT belong here, with pointers to where they DO belong. Disambiguates against adjacent subsystems. Each bullet names the class + canonical home (UID or path).
- **`### Edge cases`** (optional) — explicit acknowledgment of multi-parent borderline entries (e.g., Studio Manifesto's documentation+governance dual nature).

The two-subsection structure replaces v1.5's free-form prose pattern. **Why structured:** v1.5 surfaced the drift class — Tropo Documentation hub accumulated 11 audience-facing entries because the scope statement was implied not enumerated. Structured enumeration prevents the same drift by construction.

**Legacy alias accepted:** `## What This Covers`. Existing hubs continue rendering with v1.5 free-form prose until v1.53 Orpheus doc-pipeline production cycle (Captain's Briefing v3.0 §Structural-Enforcement Requirement 1) refactors all 9 hubs to v1.6 structured enumeration. Validator Check 2 (deferred v1.10) accepts both shapes during transition; ratchets to v1.6-only at v1.10 ship.

**2. `## How Tasks Flow`** — One paragraph describing task flow within this subsystem. How tasks created here reach release ships (`projects:` array pointer pattern; appearance on both subsystem board + Drop board).

**3. `## Current State`** — Narrative summary of what's shipped, in-progress, planned **as of `last_release_reflected:`**. The answer to "where is this subsystem TODAY" — 3-6 sentences (~150-300 words). Updated at every ship per §4 Hub Update Discipline.

**4. `## Change Log`** — Append-only log of release impacts. Each entry per the canonical format (full example in [history file](subsystem-hub.history.md)). MUST exist even for brand-new hubs (acceptable initial body: `*(no changes yet — first entry on next release)*`). Complementary to `release_history:` frontmatter (prose record vs structured record).

**Change Log Entry Format** (per entry):

```markdown
### v<release> — <ISO date> — Shipped

<list of shipped artifacts with UIDs + short descriptions>

**Impact:** <one- or two-sentence narrative of what the subsystem reader should know NOW.>

**Next:** <optional — what's queued for next release.>
```

Worked example in [history file](subsystem-hub.history.md).

### Optional Body Sections

A hub MAY contain these two sections; absence does NOT violate the contract:

- **`## Open Questions`** — explicit open questions / decisions-not-yet-made as of `last_release_reflected:`. Each with context + blocker. When resolved, deleted in the same ship; resolution recorded in §Change Log + (if it produced an ADR) the ADR set.
- **`## Architectural Constraints`** — what MUST NOT change in this subsystem and why, as of `last_release_reflected:`. Invariants future generations should not revisit without explicit governance action (ADR supersession).

### Optional Body Sections — Beyond Contract

A hub may add any sections beyond REQUIRED + OPTIONAL without validation impact. Common candidates: `## Roadmap`, `## Glossary`, `## Recent Surprises`. Validator (v1.10) is silent on unknown headers.

**Sections dropped from contract in v1.3** (informal-only thereafter): `## Key Decisions / ADRs` (ADR set is the canonical historical record); `## Health Read` (`shared/orientation/daily-health-report.md` is canonical); `## Related Work` (`vault/00-graph-index.json` is canonical). Existing hubs containing these may keep them as informal documentation; validator does not enforce shape.

### Adding a New Subsystem (protocol summary)

Propose via pair channel → crew decision → author hub stub at `vault/files/<uid>.md` meeting Scope + REQUIRED frontmatter + 4 REQUIRED body sections → register in [`collections/subsystem-hubs.collection.md`](../../collections/subsystem-hubs.collection.md) + `vault/00-index.jsonl` + cascade index → first Change Log + `release_history` + registry row on next release ship.

Full protocol detail in [history file §Adding a New Subsystem](subsystem-hub.history.md).

### Bootstrapping (Fresh Vaults)

Starter vaults ship with **zero subsystem hubs**. Hub creation is a downstream user action. When a fresh-vault user creates their first hub: include 4 REQUIRED body sections + REQUIRED frontmatter; OPTIONAL sections at user discretion; validator does not yet exist (v1.10 deferred).

---

## 3. State Machine

```
active → archived (only on explicit subsystem retirement via ADR)
```

Hubs do not have `draft` or `superseded` states for the hub artifact itself. A hub is live from creation (REQUIRED-section-compliant). Content evolves continuously via Change Log entries + `release_history:` appends + optional section growth; the hub itself stays `active` indefinitely.

Archival applies only when a subsystem is explicitly retired or merged. Migration Window protocol (subsystem_name uniqueness during merger): see [history file §Migration Window](subsystem-hub.history.md). Validator's uniqueness check (v1.10) ignores hubs with `state: archived` or `superseded_by:` set.

---

## 4. Validation Rules

### Governance Rules

1. **One hub per subsystem.** Duplicate hubs for same subsystem are validation error. `subsystem_name` globally unique across active hubs (Migration Window exception).
2. **Hubs are concentrators, not archives.** Body answers truth-today. Historical questions route to ADR set / daily-health-report / graph index. Recapitulation creates drift.
3. **Change Log + `release_history:` are append-only.** Never edit prior entries. Later entries may correct prior in prose; earlier stay as historical truth. Both bidirectional with [`subsystem-registry.jsonl`](../../subsystem-registry.jsonl).
4. **Updates ride release ships.** Per release.capsule v3.3 (soft-gated v1.7-v1.9) + v3.4 derivation discipline (v1.8+) — release blocked from `state: shipped` until each touched subsystem has `release_history:` entry + corresponding registry row. v1.10 hard-gates.
5. **`## Current State` is honest.** Pretending a subsystem is further along than reality violates [Operating Principles §3](../../.tropo-studio/operating-principles.md).

### Hub Update Discipline

Subsystem hubs update as part of release ship process:

1. During release scoping, release plan's `sub_systems:` field declares affected hubs (or `[]` empty per Correction 1 retrospective-not-predictive; populated at ship). **Equivalence rule:** release-plan.capsule v1.1's `sub_systems:` (informal string identifiers) MUST match this capsule's `subsystem_name:` by string equality at ship time. 1:1 coverage check deferred to v1.10.
2. During release build, streams tag affected subsystems; list grows incrementally.
3. At release close — **before release entry filed (Ship Gate)** — each affected hub gets:
   - New `release_history:` frontmatter entry: `{release_uid, release_version, summary, registry_uid, streams_touched?, derived_from?}`
   - New Change Log entry per format
   - `## Current State` updated to reflect new shipped state
   - `## Open Questions` + `## Architectural Constraints` revised if present
4. `last_release_reflected:` frontmatter field bumped to release version.
5. Row appended to [`subsystem-registry.jsonl`](../../subsystem-registry.jsonl) per touched subsystem.

**Ship Gate ordering** (atomicity-by-ordering pattern):
(a) author hub-side `release_history:` entry first with placeholder `registry_uid: pending`;
(b) write registry row capturing hub-side UID;
(c) backfill `release_history:` entry's `registry_uid` to registry row's UID.

The `sa.hub-groomer` swarm (v1.7 Stream A6) handles this automatically; manual authoring follows same sequence.

**v1.8+ derivation discipline** (release.capsule v3.4 Rule 12): `release_history:` rows are DERIVED at B6 from release entry's `subsystems_touched:` (which derives from `capabilities_touched:` via 1-hop `member_of:` graph traversal). Hub authors no longer write `release_history:` rows independently for v1.8+; manual authoring of v1.8+ rows = Rule 12 violation. **Drift collapse:** both registry rows + hub `release_history` computed from same source-of-truth (`capabilities_touched:` on release entry); divergence structurally impossible. v1.10 hard-gates: release-entry blocked from `state: shipped` if derived rows fail consistency check.

**Honest limit:** v1.8 derivation enforces structural consistency, not capability completeness. Author omissions in `capabilities_touched:` still produce self-consistent graphs. Reviewer-of-record + sa.* gauntlet substrate-vs-extract delta check catch omissions until v1.10 Enforcement adds capability-completeness validation.

**Ownership resolution.** When a hub's owner is unclear (predecessor retired; transfer incomplete), ship-gate hub-update reverts to lead architect (Argus) until ownership reassigned via crew decision.

### Validation Checks (deferred to v1.10)

Mechanical validation (`scripts/validate-subsystem-hubs.ts`) deferred to v1.10 per Decision 1 of v1.7 brief. v1.7-v1.9 operate on agent-discipline. When the validator lands:

1. **REQUIRED frontmatter present.** `lifecycle: standing`; `tags` includes `subsystem-hub`; `subsystem_name` non-empty lowercase-hyphen; `subsystem_scope` non-empty ≤ 200 chars; `member_of` includes `aae9a37b`; `last_release_reflected` is `null` or valid semver string; `release_history` is array (may be empty for new hubs). **ERROR.**
2. **Four REQUIRED body sections present.** `## What This Subsystem Covers` (or legacy alias `## What This Covers`); `## How Tasks Flow`; `## Current State`; `## Change Log` (header present even if body is no-changes-yet placeholder). **ERROR.**
3. **`subsystem_name` unique across active hubs** (excluding `state: archived` or `superseded_by:` set). **ERROR.**
4. **`aae9a37b` resolves.** The `tropo-subsystems` root UID exists as active project. **ERROR (ADR-035 Surface 2 enforcement).**
5. **`last_release_reflected:` lag check.** If hub's `last_release_reflected:` more than one minor version behind current vault version, emit **WARNING**.
6. **`release_history` consistency.** Each entry's `registry_uid` resolves to a row in `subsystem-registry.jsonl`. **ERROR.**
7. **Migration-window invariants.** If `state: archived` and `superseded_by:` set, successor hub must exist + must be `state: active`. If two active hubs share `subsystem_name:`, at least one must have `superseded_by:` set OR `state: archived`. **ERROR.**
8. **`superseded_by:` requires `state: archived`.** A hub with `superseded_by:` set MUST also have `state: archived`. **ERROR.**

Validator exits 0 on clean; 1 on any ERROR. WARNINGs do not affect exit code.

### Pending Sub-Requirements (active deferred work)

Per [playbook.capsule v2.5 §Pending Sub-Requirements pattern](playbook.capsule.md), v1.4+ declares active sub-requirements:

| Sub-requirement | Triggering | Land-at version |
|---|---|---|
| Mechanical validator (`scripts/validate-subsystem-hubs.ts`) | v1.7 brief Decision 1 | v1.10.0 Enforcement |
| Section-content-freshness enforcement (`## Current State` staleness check) | sa.skeptic 035 Q3-P0 | v1.10.0 or v1.11.0 |
| 1:1 `sub_systems:` ↔ `subsystem_name:` coverage check | sa.arch-specs 035 P2-2 | v1.10.0 (effectively superseded by v1.8 typed `capabilities_touched`; formal close at v1.10) |
| Capability completeness check (release.capsule v3.4 Rule 12 enforces structural derivation, not completeness) | v1.8 brief fd2d9e77 §9 Risks | v1.10.0 Enforcement |
| Hub-side `## Current State` body validation (folded from v1.3 Required Frontmatter rigorization scope) | v1.4 close of v1.3 row 2 | v1.10.0 Enforcement |

**Atomicity-of-deletion rule:** when a deferral lands, the row is removed in the same atomic commit that authors the closing artifact. Self-pruning is non-optional; rows naming closed sub-requirements are drift; v1.10 validator surfaces as ERROR.

---

## 5. Composes-With

### Extends

- **`project.capsule`** (implicitly via shared `type: project`). Hub governance adds to project governance; does not replace it.
- **`core.capsule` floor** — UID immutability, single-owner, type immutability.

### Composes With

- **[release-plan.capsule (a3f1e7b2)](release-plan.capsule.md)** — `sub_systems:` field declaring touched subsystems; capabilities_touched is the typed authoring surface; subsystem hub membership is the rollup.
- **[release.capsule (b19e8d43)](release.capsule.md)** — v3.3 soft-gated enforcement rule (release blocks ship without registry entry per touched subsystem); v3.4 Rule 12 derivation discipline (release_history rows derived from capabilities_touched via 1-hop graph traversal). `release_history:` on this capsule is the per-hub record bidirectional with the registry's vault-wide cross-cut.
- **[collection.capsule (c04e7a91)](collection.capsule.md)** — [`collections/subsystem-hubs.collection.md`](../../collections/subsystem-hubs.collection.md) is the live roster.
- **[playbook.capsule v2.5 (e7b3c509)](playbook.capsule.md)** — pattern precedent for §Pending Sub-Requirements + capsule-history extraction (this capsule follows the same pattern).
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.

### Anticipates

- **[ADR-035 (a7c4e5b2)](../../vault/files/a7c4e5b2.md)** Declared-Presence — Surface 2 enforcement of `aae9a37b` resolution lands at v1.10 Validation Check 4.
- **[ADR-037 (e8d2a19f)](../../vault/files/e8d2a19f.md)** triggers — `on_release_ship` trigger closes soft-gate-to-hard-gate transition at v1.10.

### v1.17.0 addition

- **[Tropo Link hub (3a207ed3)](../../vault/files/3a207ed3.md)** — eighth subsystem hub introduced at v1.17.0; brings active hub count to 8 (was 6 at v1.4 lock; tropo-documentation added at v1.8 = 7; tropo-link added at v1.17.0 = 8).

---

## 6. Structured Enumeration as Navigation Contract (v1.6 worked-example narrative)

*Added 2026-05-25 by Orpheus O11 reflecting the v1.53 Lane D D1 implementation of the v1.6 schema strengthening (Argus A81 v1.6 amendment 2026-05-24).*

### 6.1 The §1 IS the navigation contract

A hub's `## What This Subsystem Covers` section is not orientation. It is the navigation contract between Mike (and any stranger-engineer reading the substrate) and the subsystem. **In scope** enumerates what someone can expect to find here as system-of-record. **Not in scope** routes someone elsewhere when they have a question that does NOT belong here. **Edge cases** acknowledges cross-subsystem composition explicitly so multi-parent artifacts (e.g., Studio Manifesto's documentation + governance dual nature) are documented, not implicit.

Free-form prose answered "what's here" softly. Structured enumeration answers "what's here, what's not, and where to look instead" mechanically. The same reader navigating six hubs gets the same structural shape at every stop; muscle memory compounds.

### 6.2 What worked across the D1 implementation (6 hubs)

Lane D D1 refreshed six subsystem hubs to v1.6 §1 structured shape on 2026-05-25. Patterns that proved load-bearing:

- **In scope bullets name canonical-artifact CLASSES, not specific instances.** "ADRs (41+ numbered)" not "ADR-035 + ADR-036 + ...". The bullet is a class-level enumeration; instances appear in the cascade. This keeps §1 stable across release ships.
- **Not in scope bullets carry a `→ Tropo X` canonical-home pointer.** Every "not in scope" item names where it DOES belong. The reader who lands here by mistake gets a one-hop route to the right hub, no dead-end.
- **Edge cases bullets name the composition explicitly.** "score-formula-doctrine (5f2c1b94) — authored by Governance, implements memory ranking for Tropo Agents (cross-subsystem doctrine)" is honest substrate; treating it as single-parent would have been a lie.
- **Cross-subsystem composition is the rule, not the exception.** Every hub in the v1.53 D1 refresh surfaced 4-6 Edge cases. Tropo is composed of subsystems that compose with each other; the §1 contract makes that explicit instead of hiding it.

### 6.3 The Documentation hub defect-class fix (worked example)

[Tropo Documentation hub (f87e33f0)](../../vault/files/f87e33f0.md) carried **five separate scope blocks** at v1.5: `## What lives here` + `## What does NOT live here` + `## Edge case: multi-parent composability` + `## Discipline going forward` + `## What This Subsystem Covers` (a duplicate at a later position). The drift accumulated over five months because no structural pressure consolidated them.

The v1.6 §1 enumeration prevents this by construction: there is ONE §1, with ONE In scope + ONE Not in scope + (optional) ONE Edge cases. Drift authoring a sixth scope block fails the structural shape check.

The D1 implementation collapsed the five blocks into one v1.6 §1 (11 In scope bullets + 7 Not in scope bullets + 5 Edge cases). The hub now reads coherent; the drift class is structurally closed.

### 6.4 What this composes with

- **Captain's Briefing v3.0 §Structural-Enforcement Requirement 1** — pristine documentation across three tiers. The v1.6 schema operationalizes pristineness at the subsystem-hub tier (tier:subsystem per doc-spec.capsule).
- **doc-pipeline (5a4337ff)** — Lane D D1 ran through doc-pipeline's second production cycle (activation c7a26c5a; doc-spec c660ec29). The pipeline + the schema compose: the schema declares what pristine looks like; the pipeline enforces with every release ship.
- **Workbench Surface Visibility doctrine (3c02f3b7)** — structured enumeration surfaces in nav-tree + Cited By + cross-subsystem composition links. The hub IS the workbench Mike navigates; structured §1 makes it readable.
- **Substrate-Verify-Twice discipline (83af4ac1)** — the D2.b narrative I'm authoring now (this section) caught a stale v1.5 footer signature in the capsule itself (fix-on-see). The discipline applies to every authoring pass, including documenting the discipline.

### 6.5 What v1.6 does NOT do

- The schema does not prescribe HOW many In scope bullets. Six hubs at D1 ranged from 6 to 11 bullets; appropriate to the subsystem's surface area.
- The schema does not enforce Edge cases as REQUIRED. Some hubs have zero genuine multi-parent artifacts; absence is honest.
- The schema does not validate prose quality (voice-review.skill handles that downstream at doc-pipeline Step 3).

The v1.6 strengthening is structural shape. Prose quality + cross-tier coherence are downstream concerns operationalized by doc-pipeline.

---

*subsystem-hub capsule definition | UID `8a4e21c5` | v1.6 (schema strengthening Argus A81 2026-05-24; D1 implementation + §6 worked-example narrative Orpheus O11 2026-05-25) | history at [17867222](subsystem-hub.history.md)*
