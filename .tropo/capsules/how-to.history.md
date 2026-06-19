---
uid: d04d382b
name: "how-to-history"
type: capsule-history
governs: a7c3f489
governs_path: .tropo/capsules/how-to.capsule.md
extracted_at: 2026-05-11
extracted_by: argus-a56
extracted_in_cycle: "v1.19.0 — Convergence Phase 1"
extracted_in_release: pending-v1.19.0
schema_version: 2
governed_by: 5ec083a3
extraction_scope: argo-private
member_of:
  - "8dd772a0"
tags: [capsule-history, extracted-from-how-to-capsule, v1.19.0-stream-c]
---

# how-to — Capsule History

*History extracted from how-to.capsule v1.3 → v1.4 body refactor (v1.19.0 Stream C; 2026-05-11). Active capsule preserves: 8 required frontmatter slots (with legacy synonym acceptance for `skill`/`skill_id`/`title`/`published`), optional frontmatter, 3 Required Body Sections with synonym acceptance + implicit-source rules, State Machine, 6 Governance Rules, validation checks with implicit-source term definitions, 4-phase retrofit rollout, Inheritance-from-core reconciliation. This file preserves: v1.0/v1.1/v1.2/v1.3 amendment-block prose, two-dialect relationship narrative, sibling-vs-substitute relationship to session-agent, 4-phase retrofit rollout detail, examples (3 worked YAMLs), §Studio Shop Signage, Relationship-to-Other-Capsules, full changelog.*

---

## Amendment Blocks (extracted)

### v1.3 (2026-05-09, Argus A53; LOCKED — v1.15 Stream A amendment)

Source brief: [1df4610d](../../vault/files/1df4610d.md); release plan [c7e4f9a2](../../vault/files/c7e4f9a2.md). Additive non-breaking under `capsule_version: "1.3"` opt-in. Added optional `trigger_description:` field — hand-authored agent-facing prose answering "when does an agent reach for this skill?" The Tropo Skill Catalog (v1.15 ship at `.tropo/skill-catalog.md`) emits this verbatim alongside structural fields per Q2 hybrid catalog generation lock. Added optional `capsule_version:` opt-in marker. 1 new validation check (17) gated on opt-in. Pre-v1.3 how-to entries grandfathered.

### v1.2 (2026-04-27, Argus A37 — registry-reference scrub)

Registry-topology consolidation work. Frontmatter `version:` advanced from v1.1 → v1.2. Body changelog row backfilled at v1.3 lock 2026-05-09 by argus-a53. No semantic contract changes — reference-hygiene only.

### v1.1 (2026-04-25, Argus A34)

Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop). Added §Studio — Shop Signage section per v3 capsule shop-signage pattern. Added Relations Header. Frontmatter `aligned_with: b4e2a718` + `composes_with: d5e1b4a3` + `pattern_family: b4e2a718` declared. No semantic changes.

### v1.0 (2026-04-20, Argus A28; LOCKED)

Three-instrument verified: Argus build (v0.1→v0.2) + sa.research pattern inventory ([record 020](../../agents/sa/sa.research/activation-log/020-how-to-capsule-patterns.md)) + sa.cold-boot stranger test (records [031](../../agents/sa/sa.cold-boot/activation-log/031-argus-a28-record.md) PASS-WITH-GAPS, [033](../../agents/sa/sa.cold-boot/activation-log/033-argus-a28-record.md) PASS — zero new findings).

**Guiding principle:** *"Codification, not invention"* — same principle as session-agent.capsule v1.0. Every required field already exists in the majority of 14 skills across Dialect A (`skill` + `purpose` + `when` + optional `mode` + optional `params`) and Dialect B (`skill_id` + `title` + `version` + `status` + `reads` + `writes`). All 14 skills Day-1 compliant via synonym acceptance.

---

## Relationship to existing `.tropo/skills/` infrastructure — the two dialects (extracted)

- **Two dialects coexist today.**
  - **Dialect A** (7 files): `skill`, `purpose`, `when`, optional `mode`, optional `params`, `uid`
  - **Dialect B** (2 files): `skill_id`, `title`, `version`, `status`, `tier`, `author`, `created`, `reads`, `writes`
  - Plus the CURATOR and the index.
- **This capsule harmonizes them** with documented synonym acceptance — validator recognizes `skill`, `skill_id`, and (going forward) `name` as equivalent; `purpose` and body-preamble text as equivalent; `when` stays as the prose trigger surface.
- **All 14 skills compliant Day 1.** No forced migration. Phase 1 normalizes `name` and adds any missing provenance pair; Phases 2-3 opt skills into machine-readable triggers and typed I/O.

---

## Relationship to session-agent.capsule — siblings, not substitutes (extracted)

- **session-agent** = callable specialist. Loads domain, receives `[PENDING]`, returns `[DONE]` with verdict. JSON I/O.
- **how-to** = inline behavior bundle. Agent reads, executes steps in own context, confirms post-conditions. Filesystem I/O (`reads`/`writes`).

~70% of frontmatter overlaps (uid, name, status, owner, domain/purpose, triggers, provenance). Registry.jsonl treats them as homogeneous rows distinguished by `type:` discriminator. **Cross-capsule alignment note:** session-agent.capsule v1.0 uses `class: session-agent` as its discriminator; this capsule uses `type: how-to`. Alignment to `type:` across all Pillar 1 primitives planned as session-agent.capsule v1.1 amendment at Stream 1 Step 4 (registry.jsonl prep).

---

## Inheritance from core — explicit reconciliation (extracted)

Skill files live at `.tropo/skills/<name>.skill.md` and are **kernel infrastructure artifacts, not vault entries**. They declare `extends: core` for conceptual alignment and UID governance, but are not subject to core's ledger-check-in validation in the same way. Mirrors the session-agent.capsule treatment.

| Core field | Applied to skill files? | How |
|---|---|---|
| `uid` | Yes | 8-hex, unique, immutable. 13 of 14 already have; `check-sa-catalog` has `uid: null` (Phase 1 cleanup). |
| `type` | Yes | `type: how-to` — discriminator for registry filtering. |
| `status` | Yes | State machine. |
| `title` | Not required | `name` + `purpose` serve the catalog role. Skills don't carry a separate `title:`. |
| `owner` | Yes | Required going forward. Missing from all Dialect-A skills — Phase 1 backfill. |
| `created` | Yes (or legacy) | Provenance pair; legacy forms accepted. |
| `modified` | Mapped | Accept `updated` as synonym for `modified`; both optional at Phase 1. |

The validator for skills is THIS capsule's validation check list, not core's.

---

## Retrofit Rollout — Phased, Non-Breaking (extracted)

Adopted from sa.research inventory findings ([record 020](../../agents/sa/sa.research/activation-log/020-how-to-capsule-patterns.md)). The 14 existing skills are inventoried: 11 green-retrofit, 2 yellow (CURATOR, check-sa-catalog with uid:null), 0 red. All 12 are compliant Day 1 via synonym acceptance.

### Phase 1 — Immediate, zero-break (ships with v1.2 capsule lock)

- Publish capsule with 8-slot required set + 3-intent body convention.
- Synonym acceptance enabled: `skill` / `skill_id` / `name`, `published` / `active`, implicit-purpose rule, implicit-when rule.
- Normalize `name:` field opportunistically (all 12 valid skills already have a name-source via legacy synonym).
- Mark `check-sa-catalog.skill.md` (`uid: null`) as YELLOW-retrofit; validator flags but does not block.
- Backfill `owner:` on Dialect-A skills as opportunistic Phase-1 cleanup.
- **Outcome:** 12 of 14 skills compliant the day the capsule ships; 2 yellow flagged for cleanup.

### Phase 2 — 2-4 weeks later, opt-in

- Populate `registry.jsonl` from capsule + existing skill frontmatter.
- Begin `triggers:` machine-readable backfill. Priority order: skills with clear glob/event triggers (e.g., `register-file.skill.md` with file-creation trigger, `boot-* ` skills with event triggers).
- Begin typed I/O backfill (`reads:` / `writes:` already in Dialect B).

### Phase 3 — Address the 2 yellow skills

- **CURATOR.skill.md** — meta-skill (skill catalog index). Decision: either retrofit to standard skill shape OR formalize as a separate `type: index` artifact. Defer to Phase 3 walk.
- **check-sa-catalog.skill.md** — assign UID; restore validator-passing state.

### Phase 4 — Cut-over (v1.4+ target)

- Once all active skills are typed, promote `triggers:` from optional to **required** for `status: active`.
- Any skill created after this date is born typed.

**Principle:** *"Codification, not invention."* The capsule never forces a schema change existing skills can't accommodate.

---

## Examples (extracted — 3 worked YAML templates)

### Minimal — Phase 1 active skill (Dialect A shape)

Day-1 compliance shape. Legacy `skill:` field preserved as `name:` synonym. No typed I/O; just minimal required slots.

```yaml
---
uid: 1a3f5b7c
skill: register-file
type: how-to
status: active
owner: argus
purpose: "Register a new file in the vault with proper frontmatter and validate the entry"
when: "After creating any new vault entry that needs UID assignment and index registration"
mode: inline
created: 2026-04-15
created_by: argus-a25
---
```

Existing 7 Dialect-A skills pass validation with roughly this shape.

### Minimal — Phase 1 active skill (Dialect B shape)

Same Day-1 compliance, legacy `skill_id:` + `title:` synonyms; legacy `status: published` (accepted as `active` synonym).

```yaml
---
uid: 2b4d6f8a
skill_id: rebuild-pm-state
title: "Rebuild PM State"
type: how-to
status: published
tier: vault
owner: vela
purpose: "Rebuild project-management state from source files after schema changes or migration"
when: "After v2 schema migrations OR when PM state drift detected by validator"
reads:
  - vault/files/*.md
  - vault/00-index.jsonl
writes:
  - vault/pm-state/*.jsonl
version: "1.0"
author: vela-v31
created: 2026-04-21
---
```

### Full — Phase 2+ active skill with typed I/O + machine-readable triggers

Illustrative target post-retrofit.

```yaml
---
uid: 1a3f5b7c
name: register-file
type: how-to
status: active
owner: argus
purpose: "Register a new file in the vault with proper frontmatter and validate the entry"
when: "After creating any new vault entry that needs UID assignment and index registration"
mode: inline
category: lifecycle
triggers:
  - "new-file-created"
  - "**/*.md@author-time"
domain_tags: [registration, lifecycle, vault-hygiene, governance]
description: "Mints a UID, ensures required frontmatter, registers the entry in vault/00-index.jsonl, and validates against the relevant capsule's schema. Used as the first step after authoring any new vault entry."
reads:
  - .tropo/capsules/<type>.capsule.md
writes:
  - vault/files/<uid>.md
  - vault/00-index.jsonl
invocation_examples:
  - input: "register-file vault/files/new-task.md"
    expected_success: "UID minted, frontmatter validated, index entry written"
created: 2026-04-15
created_by: argus-a25
---
```

---

## Studio — Shop Signage (extracted)

*Preserved per Mike-A55 directive: capsules are agent-read, not human-read.*

### Tools available

- `ls .tropo/skills/*.skill.md` — survey existing 14 skills
- `cat .tropo/skills/index.skill.md` — the CURATOR (skill catalog index)
- `.tropo-studio/registries/registry.jsonl` — runtime callable catalog
- Reference skills: [register-file.skill.md](../skills/register-file.skill.md) (Dialect A canonical), [rebuild-pm-state.skill.md](../skills/rebuild-pm-state.skill.md) (Dialect B canonical)

### Skills

- `register-skill.skill.md` *(forthcoming v1.5)* — scaffold skill file with 8 REQUIRED slots + 3 REQUIRED body intents
- `audit-skills.skill.md` *(forthcoming v1.5)* — vault audit of skill registry vs activation files

### Procedures

- **Author a new skill — at `status: draft`** — create file at `.tropo/skills/<name>.skill.md`; author 8 REQUIRED frontmatter slots + Preamble (only required at draft); rebuilder projects UID into registry.jsonl
- **Advance to `active`** — fill remaining 2 body intents (Steps with synonym Process/Procedure, Success with synonym Post-conditions/Verification/Output Format); pass cold-boot stranger test; flip `status: draft → active`
- **Invoke a skill** — agent reads skill file inline; executes Steps in agent's own context; confirms Success post-conditions
- **Compose with `triggers:`** — machine-readable trigger declarations (glob patterns, event names, keyword matches) enable registry.jsonl discovery beyond prose `when:`
- **Activate vs publish** — `status: active` (preferred) OR legacy `status: published` (Dialect B synonym) — both registry-visible
- **Supersede a skill** — author successor at `active` with `supersedes: <predecessor-uid>`; predecessor flips `superseded` + `superseded_by:` (bidirectional pair)
- **Tag with v0.2 implicit-source rules** — if frontmatter `purpose:` absent, validator uses first non-heading prose paragraph after H1; if `when:` absent, validator uses body `## When to Use` (or `## When`) section content

### Pitfalls

- Filename stem ≠ `name:` field → Check 2 violation
- Authoring at `status: active` without 3 body intents (Preamble / Steps / Success) → Check 10 violation
- Declaring `writes:` paths outside target folder's AGENTS.md write-scope → Rule 4 violation
- Hand-editing registry.jsonl → Rule 6 violation; registry derived from skill frontmatter
- Mixing dialects within one skill (e.g., `skill_id` + `skill` both present) → validator picks first synonym per priority order; unambiguous but stylistically odd; normalize at next edit
- Treating `published` as different from `active` — they're synonyms; v0.2 accepts both indefinitely; new skills should prefer `active`

### Worked examples

- [register-file.skill.md](../skills/register-file.skill.md) — Dialect A canonical shape
- [rebuild-pm-state.skill.md](../skills/rebuild-pm-state.skill.md) — Dialect B canonical shape with `reads:` / `writes:`
- See §Examples block above for 3 illustrative YAMLs

### Go next

- Sibling Pillar 1 callable specialists → [session-agent.capsule (b4e2a718)](session-agent.capsule.md)
- Sibling Pillar 1 typed callables → [tool.capsule (d5e1b4a3)](tool.capsule.md) — skills can be wrapped as tools via `transport: action`
- Composed substrate → [action.capsule (9b7f5e34)](action.capsule.md) — compound operations
- The CURATOR (skill catalog) → [.tropo/skills/index.skill.md](../skills/index.skill.md)
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Relationship to Other Capsules — Narrative (extracted)

- **[session-agent.capsule (b4e2a718)](session-agent.capsule.md)** — sibling Pillar 1 primitive. Callable specialists vs inline behavior bundles. ~70% frontmatter overlap.
- **[tool.capsule (d5e1b4a3)](tool.capsule.md)** — companion typed primitive. Skills can be wrapped as tools via `transport: action`.
- **[action.capsule (9b7f5e34)](action.capsule.md)** — compound operations. Distinct from skills (markdown-native behavior bundles).
- **[core.capsule (ee814120)](core.capsule.md)** — extended (with explicit reconciliation; skills are kernel infrastructure artifacts, not vault entries).
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.

---

## Changelog (full lineage)

| Version | Date | Change | Author |
|---|---|---|---|
| 0.1 | 2026-04-20 | Initial DRAFT. Structure complete; awaiting sa.research inventory findings. | Argus A28 |
| 0.2 | 2026-04-20 | sa.research inventory integrated. 8-slot required set. Synonym acceptance for `skill`/`skill_id`/`name`, `published`/`active`. Implicit-source rules for `purpose:` (first paragraph after H1) and `when:` (body `## When to Use`). 4-phase non-breaking retrofit. | Argus A28 |
| 1.0 | 2026-04-20 | LOCKED. sa.cold-boot second pass PASS — all gaps closed, no regressions. Three-instrument verification complete. Second v1.2 Pillar 1 capsule shipped. | Argus A28 |
| 1.1 | 2026-04-25 | Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop). Added §Studio — Shop Signage section. Added Relations Header. Frontmatter `aligned_with: b4e2a718` + `composes_with: d5e1b4a3` + `pattern_family: b4e2a718`. No semantic changes. | argus-a34 |
| 1.2 | 2026-04-27 | Registry-reference scrub. Frontmatter `version:` advanced; body changelog row backfilled at v1.3 lock. No semantic changes. | argus-a37 (backfill-noted argus-a53) |
| 1.3 | 2026-05-09 | LOCKED — v1.15 Stream A amendment. Additive non-breaking under `capsule_version: "1.3"` opt-in. Added optional `trigger_description:` field. Added optional `capsule_version:` opt-in marker. 1 new validation check (17) gated on opt-in. | argus-a53 |
| 1.4 | 2026-05-11 | **v1.19.0 Stream C — Capsule Pedagogy Completion.** Body refactor to 5-section pedagogy pattern per Mike-A55 *"capsules are agent-read, not human-read"* directive. Active body reduced from 401 → ~240 lines (~40% reduction). Substrate-load-bearing content preserved in active: 8 required frontmatter slots (with legacy synonym acceptance), 3 Required Body Sections with synonyms + implicit-source rules, State Machine, 6 Governance Rules, validation checks with term definitions, 4-Phase Retrofit Rollout, Inheritance-from-core reconciliation. Extracted to history: v1.0-v1.3 amendment-block prose, two-dialect relationship narrative, sibling-vs-substitute relationship to session-agent, 3 worked YAML examples (Dialect A + Dialect B + full typed), §Studio quick-ref, Relationship-to-Other-Capsules narrative, full changelog. **No schema changes.** UID `a7c3f489` preserved. | argus-a56 |

---

## Provenance

- **Extracted at:** 2026-05-11
- **Extracted by:** argus-a56
- **Active capsule version at extraction:** v1.3 (401 lines)
- **Active capsule version after extraction:** v1.4 (~240 lines; ~40% reduction)

---

*how-to capsule history | UID d04d382b | v1.19.0 Stream C extraction 2026-05-11 by Argus A56 | Bidirectional pair: governs a7c3f489*
