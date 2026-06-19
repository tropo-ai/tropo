---
uid: a7c3f489
name: "how-to"
type: capsule-definition
extends: core
version: "1.5"
supersedes_version: "1.4"
tier: os
author: argus
created: 2026-04-20
modified: 2026-05-29
modified_by: argus-a87
created_by: argus-a28
status: retired
retired_at: 2026-05-29
retired_by: argus-a87
retired_via: "v1.60 Lane H-retire per Mike-A87 walk lock 2026-05-29 verbatim 'Yes, let's drop them. ... how-tos are instructions; we have capsules, playbooks, and pipelines that provide instructions; how-tos are also like documentation; they are not needed and have potential for drift.' Substrate-honest retire — the primitive never earned itself empirically (zero entries authored across 18 months since v1.0 lock 2026-04-20); existing primitives (capsules + playbooks + pipelines) cover the use case; how-tos add redundancy + drift risk. Earn-the-abstraction-strict applied at substrate level. Composes with v1.56 taxonomy walk amendment same cycle (4 callable surfaces → 3 callable surfaces; how-tos removed). how-to.history (UID d04d382b) preserved per honest historical record discipline. Pattern-exemplar reference to playbook.capsule + aligned_with session-agent.capsule preserved as historical pedagogy reference; future cycles do not author how-to entries. References sweep: vault grep for stale how-to citations executed at v1.60 Lane H-retire; fix-in-place trivial; Path 2 substantive."
historical_locked_by: argus-a53
historical_locked_at: 2026-05-09
last_body_refactor: 2026-05-11
history_file: d04d382b
schema_version: 2
governed_by: 222873b9
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — 5-section pedagogy
aligned_with: b4e2a718       # session-agent.capsule — sibling Pillar 1
composes_with: d5e1b4a3      # tool.capsule — skills wrap as tools via transport: action
pattern_family: b4e2a718     # Pillar 1 callable surfaces
member_of:
  - "76bab75f"   # tropo-playbooks
tags: [capsule-definition, how-to, pillar-1, 5-section-pedagogy, v1.19.0-stream-c-refactored]
---

# how-to — Capsule Definition v1.4

## 1. Intent

A how-to is an inline behavior bundle — markdown-native skill that an agent reads and executes in its own context. Loads, follows steps, confirms post-conditions.

Tropo skills are the markdown-native behavior bundles agents read and execute inline (as distinct from session-agents, which are callable specialists). Today they exist as 14 files at `.tropo/skills/` with two naming dialects and a shared body convention (preamble + Steps + Success post-conditions).

This capsule defines the **typed how-to** — a skill with an explicit name, purpose, when-to-invoke, and (optionally) machine-readable triggers, I/O shape (via `reads`/`writes`), and structured invocation examples. Typed how-tos become registry-discoverable entries that the Librarian (v1.3+) can serve via queries like *"what skill handles markdown cleanup?"* or *"list skills that write to `vault/files/`."*

**Sibling distinction from session-agent.capsule:**
- **session-agent** = callable specialist. Loads domain, receives `[PENDING]`, returns `[DONE]` with verdict. JSON I/O.
- **how-to** = inline behavior bundle. Agent reads, executes steps in own context, confirms post-conditions. Filesystem I/O.

Failure mode prevented: skills discoverable only by globbing + reading an index; no typed triggers for registry-driven discovery; no explicit `description` field for progressive disclosure; two naming dialects (Dialect A and Dialect B) diverging over time without harmonization layer.

---

## 2. Schema

### Required Frontmatter (8 slots, in addition to core)

Parallels session-agent.capsule's 8-slot convention. Legacy synonym acceptance preserves Day-1 compliance for the existing 14 skills.

| Field | Type | Constraint |
|---|---|---|
| `uid` | string (8-hex) | Registry key. Tropo moat. |
| `name` | string | Dispatch name. MUST equal filename stem (e.g., `register-file` for `register-file.skill.md`). **Accept `skill` and `skill_id` as legacy synonyms indefinitely** — existing 14 skills use them; no forced rename. |
| `type` | string | Must be `"how-to"`. Type discriminator. |
| `status` | enum | `draft` / `active` / `deprecated` / `superseded`. **Accept `published` as legacy synonym for `active`** (Dialect B). No forced rename at Phase 1. |
| `owner` | string | Executive/role responsible. Missing from most Dialect-A skills — Phase 1 backfill. Required on new skills. |
| `purpose` | string | One-sentence "what this skill does." ≤160 chars. Maps to Dialect-A `purpose:`. **Implicit-source rule:** when frontmatter `purpose:` absent, "implicit purpose" is the **first non-heading prose paragraph after the H1 title, before the first H2**. Italicized descriptors count as prose paragraphs. |
| `when` | string | Prose trigger — "when to invoke." Maps to Dialect-A `when:` and CURATOR index's "When to use" column. **Implicit-source rule:** when frontmatter `when:` absent, accept body `## When to Use` (or `## When`) heading content as implicit source. |
| provenance-pair | date + string | `created` + `created_by`. Accept legacy absence on existing Dialect-A skills; required on new skills. |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `mode` | enum | `inline` / `delegated` / `both`. Invocation mode — whether skill runs in parent context or as spawned sub-agent. Already used by 3 Dialect-A skills. |
| `category` | enum | `lifecycle` / `governance` / `maintenance` / `debugging` / `discovery` / `content` (or extension). Machine-readable replacement for CURATOR categorization. |
| `triggers` | string array | Machine-readable triggers — glob patterns (`"**/*.capsule.md"`), event names (`"on-boot"`, `"on-retire"`), keyword matches. Aligns with Cursor `globs:` / Copilot `applyTo:`. Enables registry.jsonl discovery beyond prose `when:`. |
| `params` | string array | Named substitution parameters (`[memory_path, health_report_path]`). Already used by 3 Dialect-A skills. |
| `reads` | path array | Files the skill reads. Already used by Dialect B. Enables file-to-skill reverse index. |
| `writes` | path array | Files the skill writes. Governance-relevant: validator may cross-check against AGENTS.md write-scope. |
| `description` | string | One-paragraph expansion for registry display. ≤400 chars. |
| `domain_tags` | string array | Machine-readable tags. Complements `purpose` prose. |
| `version` | semver | For versioned skills (Dialect B). |
| `tier` | enum | `os` / `vault` / `agent`. Already used by Dialect B. Governance scope. |
| `author` | string | Human/agent who wrote the skill. Dialect-B convention. |
| `supersedes` / `superseded_by` | UID | Same semantics as session-agent.capsule. |
| `invocation_examples` | object array | Sample `{input, expected_success}` pairs for cold-boot verification and Librarian routing. |
| `trigger_description` | string | **v1.3 — required under `capsule_version: "1.3"` opt-in.** Hand-authored agent-facing prose answering "when does an agent reach for this skill?" Distinct from `purpose:` (≤160 chars, what-it-does) and `description:` (≤400 chars, registry-display): `trigger_description:` answers the *when*. Min 50 chars; max 600 chars. The Tropo Skill Catalog (v1.15 ship at `.tropo/skill-catalog.md`) emits this verbatim. |
| `capsule_version` | string | **v1.3 opt-in marker.** Values: `"1.3"`. When absent, instance treated as MIGRATION-PENDING pre-v1.3 (Check 17 does NOT fire). |

### Required Body Sections (3 intents with synonyms)

Every `status: active` skill file MUST document these three intents. Validator matches on intent, not exact heading.

1. **Preamble** — opening paragraph under the H1. "Use this when..." framing. Functions as implicit `description` when frontmatter `description:` is absent.
2. **Steps** (synonyms: `Process`, `Procedure`) — numbered, imperative, copy-paste-ready procedure.
3. **Success** (synonyms: `Post-conditions`, `Verification`, `Output Format`, `Deliverable`, `Confirm`, `Return`) — post-conditions. How the caller confirms the skill succeeded.
   - **Pattern also accepted:** success embedded in the final Step (common in Dialect-B skills — e.g., "Step 5 — Confirm" with inline `Return:...`). When the final step's heading contains `Confirm`/`Return`/`Verify` and the step body documents post-conditions, that satisfies the Success intent.

**Optional body sections:** Safety Rules / Constraints / What This Skill Will NOT Do (guardrails); Failure Handling (error recovery semantics); Examples (concrete invocation samples); Footer tagline.

For `status: draft` skills: only Preamble required. Others optional during drafting.

### Inheritance from core — explicit reconciliation

Skill files live at `.tropo/skills/<name>.skill.md` and are **kernel infrastructure artifacts, not vault entries**. They declare `extends: core` for conceptual alignment + UID governance, but are not subject to core's ledger-check-in validation in the same way. Mirrors session-agent.capsule treatment. The validator for skills is THIS capsule's validation check list, not core's. Specifically: `uid` enforced (8-hex, unique, immutable); `type: how-to` discriminator; `status` state machine; `title` NOT required (`name` + `purpose` serve catalog role); `owner` required going forward; `created` (or legacy) provenance pair; `modified` (or legacy `updated`) optional at Phase 1.

---

## 3. State Machine

```
draft → active → deprecated
              ↘ superseded (via supersedes/superseded_by on replacement)
```

Mirrors session-agent.capsule. `status: published` accepted as legacy synonym for `active` (Dialect B).

| Status | Meaning |
|---|---|
| `draft` | Skill under construction. Not yet registry-visible. |
| `active` | Ready to invoke. Registry-visible. Canonical live state. |
| `deprecated` | Retired, no replacement. File preserved for history. |
| `superseded` | Replaced by newer skill. Replacement carries `supersedes: <this-uid>`; this skill gains `superseded_by:` + `status: superseded`. |

**Transitions:** `draft → active` requires all 8 required frontmatter slots + 3 body intents + cold-boot stranger test PASS. `active → deprecated` requires explicit retirement note. `active → superseded` requires successor at `active` with `supersedes:`. Skill files persist for deprecated/superseded skills (audit trail).

---

## 4. Validation Rules

**Term definitions:**

- **"Filename stem"** — filename with `.skill.md` compound extension removed (e.g., `register-file` for `register-file.skill.md`)
- **"Legacy name source"** — when frontmatter `name:` absent, name resolves from legacy synonyms in priority order: `name` → `skill` → `skill_id` → `title` (Dialect B used `title`)
- **"Implicit purpose"** — first non-heading prose paragraph after H1 title, before first H2
- **"Implicit when"** — body `## When to Use` (or `## When`) section content

### Governance Rules (6, in addition to core)

1. **One skill file per skill.** Lives at `.tropo/skills/<name>.skill.md` where `<name>` equals the `name:` frontmatter field (or legacy synonym).
2. **Name field matches filename stem.** Validation failure if mismatch.
3. **Accept legacy name fields.** `skill:` and `skill_id:` remain valid as synonyms for `name:` indefinitely. Phase 1 migrates opportunistically; no forced rewrite.
4. **`reads` / `writes` are governance-relevant.** When declared, validator may cross-check against target folders' AGENTS.md write-scope. A skill that writes to a folder it's not authorized for is a capsule violation.
5. **Skills are read-at-runtime.** They do not produce vault entries; they produce effects in the filesystem. Their invocation may be recorded in `playbook-run` or agent records if called as part of a larger workflow.
6. **Registry writes are generated, not hand-edited.** `registry.jsonl` entries produced by the registry builder.

### Validation Checks (17, ERROR-severity at check-in / registry rebuild)

1. All 8 required frontmatter slots present: `uid`, `name` (or legacy `skill`/`skill_id`/`title`), `type`, `status`, `owner`, `purpose` (frontmatter OR implicit purpose rule), `when` (frontmatter OR implicit when rule), provenance pair. **Known Phase-1 exception:** `.tropo/skills/check-sa-catalog.skill.md` has `uid: null` and is marked YELLOW-retrofit. Validator flags but does not block.
2. Name source (from legacy-source rule) matches filename stem.
3. `type` equals `"how-to"`.
4. `status` ∈ {`draft`, `active`, `deprecated`, `superseded`}. **Accept `published` as legacy synonym for `active`** (Dialect B).
5. `purpose` is non-empty string, ≤160 chars (frontmatter field OR implicit-purpose paragraph).
6. `when` is non-empty string (frontmatter field OR implicit-when section content).
7. **Soft at Phase 1; hard at Phase 2+.** If `uid` is registered in `registry.jsonl` (the runtime callable catalog — skills project here per [e2f7d195](../../vault/files/e2f7d195.md)), reverse lookup matches name-source. If not registered, Phase-1 compliant. Phase 2+ hardens to "MUST be registered."
8. Provenance pair present — either (`created` + `created_by`) OR legacy absence accepted on pre-capsule Dialect-A skills.
9. For `status: active`: body documents all 3 intents (Preamble, Steps with synonyms, Success with synonyms) — including the embedded-in-final-Step pattern. For `draft`: only Preamble required.
10. *(honor-system)* `purpose` is substantive; `when` is substantive (validator catches empty/placeholder; quality reader-verified)
11. If `mode` present: ∈ {`inline`, `delegated`, `both`}
12. If `category` present: matches enum or documented extension
13. If `triggers` present: each entry is a glob pattern, event name, or keyword
14. If `reads` / `writes` present: paths well-formed; if `writes` declared, cross-check against target folders' AGENTS.md write-scope
15. If `supersedes` / `superseded_by` present: referenced UIDs resolve to skill files; bidirectional pair consistent
16. Skill file lives at `.tropo/skills/<name>.skill.md` (or accepted legacy location); path matches name-source
17. **(v1.3; gated on `capsule_version: "1.3"`)** `trigger_description:` present, ≥50 chars, ≤600 chars. Pre-v1.3 instances grandfathered.

Core checks inherited.

---

## Retrofit Rollout — Phased, Non-Breaking

14 existing skills inventoried: 12 green-retrofit, 2 yellow (CURATOR, check-sa-catalog with uid:null), 0 red. All 12 Day-1 compliant via synonym acceptance.

### Phase 1 — Immediate, zero-break

- Publish capsule with 8-slot required set + 3-intent body convention
- Synonym acceptance enabled: `skill`/`skill_id`/`name`, `published`/`active`, implicit-purpose rule, implicit-when rule
- Mark `check-sa-catalog.skill.md` (`uid: null`) as YELLOW-retrofit
- Backfill `owner:` on Dialect-A skills opportunistically

### Phase 2 — 2-4 weeks later, opt-in

- Populate `registry.jsonl` from capsule + existing skill frontmatter
- Begin `triggers:` machine-readable backfill
- Begin typed I/O backfill (`reads:`/`writes:` already in Dialect B)

### Phase 3 — Address 2 yellow skills

- **CURATOR.skill.md** — meta-skill (skill catalog index). Decision: either retrofit to standard shape OR formalize as separate `type: index` artifact
- **check-sa-catalog.skill.md** — assign UID; restore validator-passing state

### Phase 4 — Cut-over (v1.4+ target)

- Once all active skills typed, promote `triggers:` from optional to **required** for `active` status
- Any skill created after this date born typed

**Principle:** *"Codification, not invention."* The capsule never forces a schema change existing skills can't accommodate.

---

## 5. Composes-With

- **[session-agent.capsule (b4e2a718)](session-agent.capsule.md)** — sibling Pillar 1 primitive (`aligned_with` + `pattern_family`). Callable specialists vs inline behavior bundles. ~70% frontmatter overlap. Cross-capsule alignment note: session-agent.capsule uses `class: session-agent` discriminator; this capsule uses `type: how-to`. Alignment to `type:` across all Pillar 1 primitives planned at Stream 1 Step 4.
- **[tool.capsule (d5e1b4a3)](tool.capsule.md)** — companion typed primitive (`composes_with`). Skills can be wrapped as tools via `transport: action`. Skills CAN invoke tools; tools do not invoke skills.
- **[action.capsule (9b7f5e34)](action.capsule.md)** — compound operations. Distinct from skills (markdown-native behavior bundles read inline by agents).
- **[playbook.capsule (e7b3c509)](playbook.capsule.md)** — playbooks may invoke skills as part of multi-step workflows.
- **[playbook-run.capsule (f2a8c3e1)](playbook-run.capsule.md)** — skill invocations may be recorded in playbook-run event logs.
- **[core.capsule (ee814120)](core.capsule.md)** — extended (with explicit reconciliation; skills are kernel infrastructure, not vault entries).
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.
- **[`.tropo-studio/registries/registry.jsonl`](../../.tropo-studio/registries/registry.jsonl)** — runtime callable catalog. Skills project here. Registry writes generated from skill frontmatter (Rule 6).
- **[`.tropo/skill-catalog.md`](../skill-catalog.md)** — v1.15 ship surface. Catalog generator emits `trigger_description:` (v1.3 field) verbatim alongside structural fields.
- **The CURATOR** at [`.tropo/skills/index.skill.md`](../skills/index.skill.md) — meta-skill (skill catalog index). Phase 3 decides whether to retrofit to standard shape or formalize as separate `type: index` artifact.

### History

The v1.0-v1.3 amendment-block opener prose, the two-dialect relationship narrative (Dialect A vs Dialect B), the sibling-vs-substitute relationship to session-agent, the full 4-phase Retrofit Rollout detail (with priority order for typed-I/O backfill), the 3 worked YAML examples (Dialect A minimal + Dialect B minimal + full typed), the full §Studio — Shop Signage authoring procedure (human-facing quick-ref), the Relationship-to-Other-Capsules narrative, and the full changelog are preserved in the companion [how-to.history.md (d04d382b)](how-to.history.md) governed by `capsule-history.capsule` (5ec083a3).

---

*how-to capsule definition | LOCKED v1.4 | history at [how-to.history.md](how-to.history.md) | v1.4 body refactor 2026-05-11 by Argus A56 (v1.19.0 Stream C — 5-section pedagogy pattern). Prior v1.0–v1.3 locks preserved in history. UID `a7c3f489` preserved.*
*"The inline skill. Markdown-native. Read, follow, confirm."*
