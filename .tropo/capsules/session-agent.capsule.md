---
uid: b4e2a718
name: "session-agent"
type: capsule-definition
extends: core
version: "1.6"
supersedes_version: "1.5"
v1_6_amendment_note: "v1.5 → v1.6 amendment 2026-05-29 by Argus A87 captain-mode per v1.60 dev-spec e2a8b5d1 Lane S-migrate (session-agent.capsule version bump per v1.56 tool.capsule v1.6 single-file-truth pattern precedent). NEW §2.5 Canonical File Layout subsection — session-agent class definitions migrate from agents/sa/sa.<name>/sa.<name>.md sidecar pattern to vault/session-agents/<uid>.{md|json|py} single-file-truth at vault/session-agents/<uid>.{ext}; agent class-definition is the single canonical source; sidecar pattern retired. Activation-log substrate at agents/sa/sa.<name>/activation-log/ preserved as historical record (frozen post-v1.60); going-forward dispatch records live in events log per tropo.sub_agent.* family. Migration scope per V55 Lane S-prune lock at c6f2ff1e §3 keep_set: 16 sa.* class definitions (post A87 sa.pipeline-verify RETIRE confirm at event 198, final keep = 16). Talos engineers migration per the v1.56 tools precedent; tropo-validate.py + .tropo/scripts/lib/session_agent_validators.py extensions cover new schema. Composes with v1.60 Lane S-prune lock c6f2ff1e + Mike-A87 Pillar 1 closes-at-three-surfaces walk lock 2026-05-29 + cb7d713a v1.61+ fleet-ops trigger-wire brief (fleet-ops cluster KEPT empirically). Substantive architecture (gauntlet protocol + commission record substrate + standard sub-agent dispatch family events) unchanged from v1.5 — only path pattern + single-file-truth layout amended."
tier: os
author: argus
created: 2026-04-20
modified: 2026-05-29
modified_by: argus-a87
historical_modified: 2026-05-11
historical_modified_by: argus-a56
created_by: argus-a28
status: locked
locked_by: argus-a53
locked_at: 2026-05-09
last_body_refactor: 2026-05-11
enforced_enums:
  status: [draft, active, deprecated, superseded]
meta_status_rollup:
  to-do: [draft]
  in-progress: [active]
  done: [deprecated, superseded]
history_file: 709efecd
schema_version: 2
governed_by: 222873b9
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — 5-section pedagogy
aligned_with: 7d3f9a2c       # sa/CAPSULE.md — universal commissioning protocol
composes_with: a7c3f489      # how-to.capsule — sibling Pillar 1
pattern_family: a7c3f489     # how-to / tool / session-agent share registry shape
member_of:
  - "99ed55fd"   # tropo-agents
tags: [capsule-definition, session-agent, pillar-1, 5-section-pedagogy, v1.19.0-stream-c-refactored]
---

# session-agent — Capsule Definition v1.5

## 1. Intent

A session-agent (sa.\*) is a session-resident specialist — loads a domain once, serves queries or executes scoped work during a single spawning session.

Tropo sa.\* agents are Tropo's closest internal analog to "callable tools." They exist as markdown activation files with a prose-based commissioning protocol ([sa/CAPSULE.md, UID 7d3f9a2c](../../vault/files/e863a1e0.md)) and an append-only record channel (`activation-log/NNN-*.md`).

This capsule defines the **typed session-agent** — a sa.\* with an explicit name, domain, spawnable-by scope, and optional JSON Schema for inputs and outputs. Typed session-agents are registry-discoverable (their entry in `registry.jsonl` carries their schemas and dispatch name) and can be invoked with confidence by any agent or, at L2, by the Librarian as a routed service.

**This capsule does not replace [sa/CAPSULE.md](../../vault/files/e863a1e0.md).** The sibling CAPSULE governs the universal commissioning protocol (6 steps, record format, termination semantics) that applies to every sa.\*. This capsule defines the governed *shape* of every sa.\* activation file — required and optional frontmatter, required body sections, state machine, validation. The two capsules are complementary.

Failure mode prevented: sa.\* agents discoverable only by globbing `agents/sa/`; inputs and outputs as prose conventions, not typed contracts; activation files diverging in shape over time (some carry `class:`, others `type:`; some use `commissioned:`, others `created:`); inability to register sa.\* as routable services to the Librarian at L2.

---

## 2. Schema

### Required Frontmatter (8 slots, in addition to core)

All 8 are ALREADY present in the 8 existing sa.\* per the sa.research inventory. The capsule codifies them as required; no retrofit needed. The 8 slots: `uid`, `name`, `class` (OR `type` — v1.1), `status`, `owner`, `domain`, `spawnable_by`, provenance-pair.

| Field | Type | Constraint |
|---|---|---|
| `uid` | string (8-hex) | Registry key. Stable identifier. |
| `name` | string | Full dispatch name with `sa.` prefix. MUST equal parent folder name (e.g., `sa.cold-boot` for folder `agents/sa/sa.cold-boot/`). Registry lookup key. |
| `class` | string | Must be `"session-agent"`. Type discriminator. **v1.1:** `type: session-agent` accepted as equivalent. Either field satisfies. |
| `status` | enum | `active` / `draft` / `deprecated` / `superseded`. Drives registry visibility. |
| `owner` | string | Executive responsible for activation file. Routes change requests. |
| `domain` | string | One-sentence scope statement. ≤160 chars. Human-readable catalog entry. |
| `spawnable_by` | YAML array OR bare string (legacy) | Who can commission. Values: `["all-executives"]`, specific agents, role tags. **Array form preferred.** Bare-string form accepted as legacy indefinitely (4 of 8 existing agents use it). |
| provenance-pair | date + string | `created` + `created_by` OR legacy `commissioned` + `commissioned_by` (7 of 8 existing agents use the legacy pair). Validator accepts either. |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `input` | JSON Schema (inline or `$ref`) | Structured input the sa.\* accepts. Phase 4 target: required. |
| `output` | JSON Schema (inline or `$ref`) | Structured output. When present, MUST include `verdict` (or `status`) field with enum. Typical: `pass / pass-with-gaps / fail / inconclusive`. Phase 4 target: required. |
| `triggers` | string array | Glob/keyword/event triggers for discovery |
| `domain_tags` | string array | Machine-readable tags (e.g., `[testing, navigation, governance]`) |
| `archetype` | enum | `one-shot` / `persistent` / `daemon`. Informs termination semantics. |
| `version` | semver | For sa.\* with versioned activation files |
| `updated` + `updated_by` | date + string | Modification provenance |
| `supersedes` / `superseded_by` | UID | Bidirectional pair for supersession |
| `boot_context_budget_tokens` | integer | Declared context cost at boot. Enables Librarian capacity planning. |
| `co_dispatch_with` | UID array | sa.\* typically spawned alongside this one (fleet-ops composition pattern) |
| `description` | string | One-paragraph expansion of `domain` for registry display. ≤400 chars. |
| `memory_scope` | path array | What this sa.\* loads at boot. Librarian uses for boot-cost estimation. |
| `polling_cadence` | string | For long-running sa.\* (`"every 30s"` / `"on-demand"` / `"batch"`). Default `"on-demand"`. |
| `keep_alive_default` | boolean | Runs indefinitely (true) or batch-terminates (false). Spawner overrides via `[RESPONSE]`. Default false. |
| `invocation_examples` | object array | Sample `{input, expected_output}` pairs for cold-boot verification |
| `trigger_description` | string | **v1.4 — required under `capsule_version: "1.4"` opt-in.** Hand-authored agent-facing prose answering "when does an agent reach for this sa.\*?" Distinct from `domain:` (≤160 chars, what-it-does) and `description:` (≤400 chars, registry-display): `trigger_description:` answers the *when*. Min 50 chars; max 600 chars. The Tropo sa.\* Agent Catalog (v1.15 ship at `.tropo/sa-agent-catalog.md`) emits this verbatim. |
| `capsule_version` | string | **v1.4 opt-in marker.** Values: `"1.4"`. When absent, instance treated as MIGRATION-PENDING pre-v1.4 (Check 18 does NOT fire). |

### Required Body Sections (6, with synonyms)

Every `status: active` activation file MUST document these six intents, in this order. Validator matches on intent, not exact heading text.

1. **Purpose** (synonyms: `Intent`, `Overview`) — one paragraph. What the agent is for.
2. **Boot Sequence** (synonyms: `Boot`, `Activation Sequence`, `Startup`) — explicit ordered steps the agent follows at spawn. MUST include a line beginning with `[QUERY] Boot complete —` (the canonical prefix the validator matches on; suffix may vary).
3. **Invocation Protocol** (synonyms: `Research Protocol`, `Execution Protocol`, `How Tests Are Requested`, `Capabilities`, `Task 1-N`) — how `[PENDING]` items are shaped. The input surface.
4. **Output Format** (synonyms: `Response Format`, `Report Format`, `Deliverable`) — the fixed template the agent writes to the record on `[DONE]` or `[FAILED]`. MUST include any `verdict` / `status` enum the agent emits.
5. **Guardrails / Constraints** (synonyms: `Constraints`, `What This Agent Will NOT Do`, `Will NOT Do`, `Scope Limits`) — what the agent will NOT do + explicit write-scope boundaries. At minimum, the universal limits from sa/CAPSULE.md.
6. **Termination** (synonyms: `Shutdown`, `Communication` when embedded there, `Termination Semantics`) — explicit `[DONE]` / `[SHUTDOWN]` / poll-cycle behavior. May be inline in Boot Sequence, Constraints, or Communication section if termination is structurally part of those (e.g., vault-janitor self-terminates from Constraints).

For `status: draft` sa.\*: only Section 1 (Purpose) is required; others optional during drafting.

Optional body sections (used by some existing sa.\*): `Capabilities` (multi-mode agents); `Panel Pattern` (agents commonly spawned in parallel); footer tagline.

---

## 3. State Machine

```
draft → active → deprecated
              ↘ superseded (via supersedes/superseded_by on replacement)
```

Canonical status enum: `status:` ∈ {draft, active, deprecated, superseded}

| Status | Meaning |
|---|---|
| `draft` | Activation file under construction. Domain declared but not yet commissionable. |
| `active` | Ready to be commissioned. Registry-visible. Canonical live state. |
| `deprecated` | Retired from active use, no replacement. Activation file preserved for history. Should not be commissioned. |
| `superseded` | Replaced by newer sa.\*. Replacement carries `supersedes: <this-uid>`; this agent carries `superseded_by: <replacement-uid>`. |

**Transitions:**

- `draft → active` requires: all required frontmatter present, all required body sections (or synonyms), cold-boot stranger test PASS (Vela dispatches via sa.cold-boot)
- `active → deprecated` requires: explicit note in activation file body explaining retirement. Entry flagged in `registry.jsonl` as deprecated.
- `active → superseded` requires: new sa.\* at `active` with `supersedes:` pointing here. This agent gains `superseded_by:` + `status: superseded`.

**Activation files persist** for deprecated and superseded agents (audit trail). They are NOT deleted.

---

## 4. Validation Rules

### Inheritance from core — explicit reconciliation

sa.\* activation files at `agents/sa/<name>/<name>.md` are **agent-lifecycle artifacts, not vault entries**. They declare `extends: core` for conceptual alignment + UID governance, but are not subject to core's check-in validation in the same way vault entries are. The capsule validator for sa.\* is THIS capsule's validation check list, not core's. Specifically: `uid` enforced normally; `type`/`class` discriminator (v1.1: either satisfies core's `type:` requirement); `status` enforced normally; `title` NOT required (name + domain serve catalog role); `owner` required; `created` (or legacy `commissioned`) provenance pair; `modified` (or legacy `updated`) optional-but-encouraged.

### Governance Rules (7, in addition to core + sa/CAPSULE.md)

1. **One activation file per sa.\*.** Lives at `agents/sa/<name>/<name>.md` where `<name>` is the full sa.\*-prefixed dispatch name.
2. **Name field must match folder name.** If `name: "sa.cold-boot"`, folder is `agents/sa/sa.cold-boot/` and file is `sa.cold-boot.md`. Mismatch is validation failure.
3. **`spawnable_by` defaults to `["all-executives"]`** when omitted (per sa/CAPSULE.md). Omission allowed at `draft`; explicit declaration required at `active`.
4. **Output schemas are the contract (when declared).** A sa.\* that declares `output:` JSON Schema but returns non-conforming output is a capsule violation. Cold-boot stranger test verifies schema compliance. Sa.\* without declared schemas evaluated against prose Output Format section.
5. **Terminal — one level only.** sa.\* agents cannot spawn sub-agents (mirrors sa/CAPSULE.md). Capsule does not relax this.
6. **Ephemeral — single-session lifetime.** Persistent domain specialists are Service Directors (per ADR-022), not sa.\*. Activation files persist across sessions; agent instances do not.
7. **Registry writes are generated, not hand-edited.** `registry.jsonl` entries for any `active` sa.\* are produced by the registry builder. Activation files are hand-written; registry entries are derived.

### Validation Checks (18, ERROR-severity at check-in / registry rebuild)

1. All 8 required frontmatter slots present with correct types: `uid`, `name`, `class` (OR `type` — v1.1), `status`, `owner`, `domain`, `spawnable_by`, provenance-pair (either `created`+`created_by` OR `commissioned`+`commissioned_by`)
2. `name` matches parent folder name exactly (both with `sa.` prefix)
3. Type discriminator present. Either `class: session-agent` (legacy, v1.0) OR `type: session-agent` (v1.1, preferred for new agents). At least one MUST be present.
4. `status` ∈ {`draft`, `active`, `deprecated`, `superseded`}
5. `domain` is non-empty string, ≤160 chars
6. `spawnable_by` is YAML array OR bare string (legacy form accepted). Values resolve to registered executives or `"all-executives"`. Array form preferred.
7. `uid` registered in `registry.jsonl`; reverse lookup matches `name`
8. If `governed_by` present, referenced UID resolves to a valid spec/decision/capsule
9. Provenance pair present — either (`created`+`created_by`) OR (`commissioned`+`commissioned_by`). Legacy form accepted indefinitely on existing sa.\*; new sa.\* should prefer `created`+`created_by`.
10. For `active`: body documents all 6 intents (Purpose / Boot Sequence / Invocation Protocol / Output Format / Guardrails-Constraints / Termination) — detectable by canonical heading OR any declared synonym. For `draft`: Purpose intent required; others optional.
11. Boot Sequence (or synonym) section contains a line matching the prefix `[QUERY] Boot complete —` (suffix may vary)
12. If `input:` present: valid JSON Schema with top-level `type` or `$ref`
13. If `output:` present: valid JSON Schema AND includes a `verdict` or `status` field with enum values
14. If `archetype: one-shot`: activation file body contains a clear self-terminate step (in Termination, synonym, or inline in Boot Sequence / Guardrails where structurally appropriate)
15. Activation file lives at `agents/sa/<name>/<name>.md` — path matches `name`
16. For `active`: `activation-log/` folder exists alongside activation file. For `draft`: optional (first commission creates it).
17. If `supersedes` present, referenced UID resolves to a sa.\* activation file. If `superseded_by` present, same.
18. **(v1.4; gated on `capsule_version: "1.4"`)** `trigger_description:` present, ≥50 chars, ≤600 chars. Pre-v1.4 instances grandfathered.

---

## Retrofit Rollout — Phased, Non-Breaking

The 8 existing sa.\* are inventoried: 6 green-retrofit, 2 yellow (arch-specs, metis-nav — prose-by-design), 0 red. All 8 compliant Day 1.

### Phase 1 — Immediate, zero-break (ships with v1.2 capsule lock)

- Publish capsule with 8-field required set.
- Typed I/O (`input`/`output`) + `triggers` + `domain_tags` remain optional.
- Normalize `spawnable_by` to YAML array form across existing agents (trivial edit; sa.repair-agent T1 pass).
- **Outcome:** all 8 agents compliant the day the capsule ships. No forced migration.

### Phase 2 — 2–4 weeks later, opt-in

- Populate `registry.jsonl` from capsule + existing agent frontmatter.
- Begin typed-I/O backfill. Priority order: sa.cold-boot (canonical), sa.research, sa.project-tree, then sa.vault-janitor / sa.channel-health-monitor / sa.repair-agent.

### Phase 3 — Address the 2 yellow agents

- **sa.arch-specs** and **sa.metis-nav** have prose-by-design outputs. Recommendation: envelope schema only (`{question, answer, source, out_of_scope?}`) — preserves prose utility while still registry-visible.

### Phase 4 — Cut-over (v1.4+ target)

- Once all active sa.\* are typed, promote `input` and `output` from optional to **required** for `active` status.
- Any sa.\* created after this date is born typed.
- Deprecated agents keep legacy shape.

**Principle:** *"Codification, not invention."* The capsule never forces a schema change existing agents can't accommodate.

---

## 5. Composes-With

- **[sa/CAPSULE.md (7d3f9a2c)](../../vault/files/e863a1e0.md)** — sibling. Universal commissioning protocol (`aligned_with`). This capsule extends it with typing. The two capsules are complementary, not redundant.
- **[how-to.capsule (a7c3f489)](how-to.capsule.md)** — companion typed primitive (v1.2 Pillar 1; `composes_with` + `pattern_family`). Skills are markdown behaviors; session-agents are callable specialists. Both go in registry.jsonl.
- **[tool.capsule (d5e1b4a3)](tool.capsule.md)** — companion typed primitive (v1.2 Pillar 1). External MCP tools expose typed I/O via their own schema; sa.\* are internal typed specialists. sa.\* can be wrapped as tools via `transport: sa`.
- **[playbook-run.capsule (f2a8c3e1)](playbook-run.capsule.md)** — sa.\* invocations can produce playbook-run entries when the sa.\* executes a playbook-like sequence.
- **[action.capsule (9b7f5e34)](action.capsule.md)** — composed substrate. Compound operations distinct from sa.\* callable specialists.
- **[core.capsule (ee814120)](core.capsule.md)** — extended (with explicit reconciliation; sa.\* are agent-lifecycle artifacts, not vault entries).
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.
- **[`.tropo-studio/registries/registry.jsonl`](../../.tropo-studio/registries/registry.jsonl)** — runtime callable catalog (sa.\* project here per [e2f7d195](../../vault/files/e2f7d195.md)). Registry writes generated from activation file frontmatter (Rule 7).
- **[`agents/sa/commission-quickref.md`](../../agents/sa/commission-quickref.md)** — hot-path commissioning quickref. Read at commission time.
- **[`.tropo/sa-agent-catalog.md`](../sa-agent-catalog.md)** — v1.15 ship surface. Catalog generator emits `trigger_description:` (v1.4 field) verbatim alongside structural fields. The user-facing filename uses Mike's preferred language; underlying schema type is `session-agent`.

### History

The v0.1-v1.4 amendment-block opener prose, Phase 1-vs-Phase 4 framing, relationship-to-existing-sa.\*-infrastructure narrative, the full Inheritance-from-core reconciliation table, the 2 worked YAML examples (minimal Phase 1 + full Phase 2+ typed sa.cold-boot), the full §Studio — Shop Signage authoring procedure (human-facing quick-ref), the Relationship-to-Other-Capsules narrative, the Cross-References block, and the full changelog are preserved in the companion [session-agent.history.md (709efecd)](session-agent.history.md) governed by `capsule-history.capsule` (5ec083a3).

---

*session-agent capsule definition | LOCKED v1.5 | history at [session-agent.history.md](session-agent.history.md) | v1.5 body refactor 2026-05-11 by Argus A56 (v1.19.0 Stream C — 5-section pedagogy pattern). Prior v0.1–v1.4 locks preserved in history. UID `b4e2a718` preserved.*
*"The typed specialist. Loads a domain once. Serves queries with contracts."*
