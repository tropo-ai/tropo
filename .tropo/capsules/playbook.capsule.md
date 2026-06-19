---
uid: e7b3c509
name: "playbook"
type: capsule-definition
extends: core
version: 2.6
supersedes_version: "2.5"
v2_6_amendment_note: "v2.5 → v2.6 amendment 2026-06-11 by Argus A109 per the Mike-locked v1.69 dev-spec (0c61a52b §S2) — the 5th Pillar-1 single-file-truth instance (tool.capsule v1.6 exemplar). Adds §Canonical File Layout: playbook entries at vault/playbooks/<uid>.md (the entry IS the playbook; UID-as-filename; P0.6 walker indexes). TWO playbook-specific provisions: (1) BOOT-CONTRACT EXCEPTION — agent-activation + agent-retire keep kernel thin-pointers at .tropo/playbooks/ (canonical_substrate_uid: + inline degraded floor; the Tier-1/Tier-2 two-file pattern; copy-to-vault-FIRST ordering); (2) SUBDIRECTORY FLATTENING — concierge-paths/ → concierge_path: true frontmatter, pipelines/ → existing pipeline subtype, migrations/ → per-file archive disposition. No schema field changes; required slots + 21 checks unchanged; v1.69 S2 migrates 23 live candidates by relocation + frontmatter addition. Older history → companion 1b834ed6."
tier: os
author: argus
created: 2026-04-16
modified: 2026-06-11
created_by: tropo
modified_by: argus-a109
status: active
enforced_enums:
  status:
    canonical: [draft, active, superseded, archived]
    aliases:
      published: active
meta_status_rollup:
  to-do: [draft]
  in-progress: [active, published]
  done: [superseded, archived]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
history_file: 1b834ed6
last_body_refactor: 2026-05-11
aligned_with:
  - e6d373bc   # Tropo Playbook Specification v2.2
  - 90b57b3b   # D2.6+D4.9 design brief (concierge re-routing pair)
composes_with: e4c8a6b2 # pipeline.capsule v1.0 (subtype of this)
pattern_exemplar: d0c00001 # document.capsule
member_of:
  - "76bab75f"   # tropo-playbooks (v1.8 Stream B1 backfill)
---

# playbook — Capsule Definition v2.6

| Relation | Target |
|---|---|
| Governed by | [capsule-definition meta (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Playbook Spec v2.2 (e6d373bc)](../../vault/files/e6d373bc.md) |
| Extends | `core` |
| Pattern exemplar | [document.capsule (d0c00001)](document.capsule.md) |
| Composes with | [pipeline.capsule (e4c8a6b2)](pipeline.capsule.md) (subtype) |

---

## Canonical File Layout (v2.6 NEW — v1.69 S2, 5th Pillar-1 instance)

Playbook entries follow single-file truth at **`vault/playbooks/<uid>.md`** — the entry IS the playbook (YAML frontmatter + procedure body), UID-as-filename, indexed by the rebuild-index `vault/playbooks/` walker, discoverable by query. Cold-boot invocation: query the index for the playbook by name/trigger → UID + path → execute. Same pattern as tools (v1.6) / how-tos / session-agents / actions.

**Boot-contract exception (the two-file pattern):** `agent-activation` and `agent-retire` additionally keep **kernel thin-pointers at their legacy `.tropo/playbooks/` paths** — frontmatter declares `canonical_substrate_uid:` → the vault entry; body carries an inline degraded-mode floor (phase structure + both HARD GATES + milestone obligations) sufficient to boot if the vault canonical is unreachable. The proven Tier-1/Tier-2 kernel-pointer pattern: a booting agent can never 404 on a moved playbook. Migration ordering is copy-to-vault-FIRST (mint UID → write canonical → verify → overwrite kernel path with pointer → verify), per dev-spec [0c61a52b](../../vault/files/0c61a52b.md) §S2.

**Subdirectory flattening:** pre-v1.69 subdirectory semantics move to frontmatter — `concierge-paths/` members declare `concierge_path: true`; `pipelines/` members are the existing pipeline subtype. Directories are not governance; fields are (flat-vault doctrine). `migrations/` content (3 v030-era + 2 general) takes per-file **archive disposition** — historical record, not live fleet.

**Deprecation:** new playbooks authored at v2.6+ go straight to `vault/playbooks/<uid>.md`. After v1.69 S2, `.tropo/playbooks/` contains ONLY the two kernel thin-pointers.

---

## 1. Intent

A playbook is a governed orchestration document. It coordinates humans, agents, data, rules, and external systems across whatever duration the work requires — the pattern that makes process execution legible, repeatable, and verifiable.

This capsule is the minimum governance contract every playbook in the vault must satisfy. It declares the body-section floor (5 required), the state machine (`draft → active → superseded → archived`), the validation rules (21 checks across structural + behavioral + composition concerns), and the subtypes (pipeline, concierge-paths, test-harness). The full orchestration semantics — Four-tier binding, run folders, thread.md, verification receipts, portability — are specified in [Playbook Specification v2.2 (e6d373bc)](../../vault/files/e6d373bc.md). This capsule is the machine-checkable contract; the spec is the human-readable architecture.

**Before authoring a playbook:** check `.tropo/playbooks/` for live playbooks with matching `domain:` or `trigger:` — duplicate triggers create library drift. If an existing playbook is close but not right, supersede it rather than parallel-author.

---

## 2. Schema

### Required Frontmatter (beyond core)

| Field | Type | Constraint |
|---|---|---|
| `type` | literal | Must be `playbook`. |
| `title` | string | ≤ 100 chars. Verb-led or noun phrase. |
| `version` | string | Semver or decimal (e.g., `"1.0"`, `"2.2"`). For `status: active` or later, MUST be concrete (not placeholder). |
| `status` | enum | `draft` / `active` / `superseded` / `archived`. New files start at `draft`. |
| `author` OR `owner` | object or string | `owner:` is single agent/human identifier (core capsule requires). `author:` is `{name, role}` object — add only when attribution beyond ownership is meaningful. |
| `readers` | array | Non-empty. Values: `[agent]`, `[human]`, `[agent, human]`, `[system]`, or combinations. |
| `scope` | enum | `single-session` / `multi-session` / `standing`. |
| `tags` | array | At least one tag. Lowercase-hyphen. |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `trigger` | string | When this playbook runs (e.g., `activation`, `user-request-agent-creation`). RECOMMENDED — playbook without `trigger:` has ambiguous execution semantics + is orphaned from Rule 1 duplicate-check. |
| `domain` | string | Lowercase-hyphen domain tag (e.g., `agent-lifecycle`). Informs library organization. |
| `estimated_duration` | string | Best-effort duration estimate. |
| `estimated_sessions` | integer | For `multi-session` or `standing` scope. |
| `spec` | UID or path | Design spec this playbook implements. |
| `requires` | object | Declared needs: `roles`, `services`, `channels`, `playbooks`. See Playbook Spec v2.2 §4 Binding Layer. |
| `calls` | array | Sub-playbooks or skills this playbook invokes. **Composition direction:** orchestrator declares `calls:`; sub-playbooks declare `composes_into:` pointing back. Bidirectional consistency enforced by Validation Check 21. |
| `composes_into` | array | Sub-playbook declares this when it composes into one or more orchestrators. Array of `{playbook: <slug>, role: <role-in-orchestrator>}` entries. REQUIRED on test-harness sub-playbooks; RECOMMENDED on any composing playbook. |
| `supersedes` | UID or path | Prior playbook this one supersedes. |
| `superseded_by` | UID or path | Successor playbook (set when superseded). Bidirectional pair with `supersedes:`. |
| `governed_by` | UID | This capsule's UID (`e7b3c509`). RECOMMENDED for new playbooks. |
| `aligned_with` | UID | Adjacent spec or capsule. |
| `locked_by`, `locked_at` | string, date | Lock provenance for `status: active` or later. |
| `last_updated` OR `modified` | ISO 8601 date | Most recent amendment. |
| `created`, `created_by` | ISO 8601 date, string | Authorship provenance. |
| `changelog` | array | Per-version change log entries. |
| `relationships` | array | Schema v2 unified relationships for cross-cutting references. |

### Example — Minimum-Viable Playbook Frontmatter

```yaml
---
uid: <8-hex>
type: playbook                # required
title: "<verb-led or noun phrase>"  # ≤ 100 chars
version: "1.0"
status: draft                 # required starting state
author:
 name: "<author name>"
 role: "<role>"
readers: [agent]              # or [human] / [agent, human] / [system]
scope: single-session         # or multi-session / standing
tags: [<lowercase-hyphen-tag>]
# RECOMMENDED:
trigger: "<when this runs>"
domain: "<lowercase-hyphen>"
estimated_duration: "<string>"
governed_by: e7b3c509         # this capsule
---
```

### Required Body Sections (5 sections)

Every playbook body MUST contain these. Order recommended but not enforced; validator checks presence.

**1. `## Intent`** — Goal + why. North Star for execution decisions. 2-5 sentences. **Voice directive:** address declared `readers:`. For `[agent]`-only playbooks, second-person agent voice works; for `[human, agent]`, neutral third-person. Match the voice throughout.

**2. `## Rules`** — Hard constraints; non-negotiable. Bulleted list — each rule is single, unambiguous, testable. **Phrasing directive:** imperative form with `MUST` / `MUST NOT` / `SHOULD` / `SHOULD NOT`. Rules cascade per Playbook Spec v2.2 §3: Principles + Operating Agreement → Director policies → Agent charter → Parent playbook → this playbook (most specific). No layer removes constraints from above.

**3. Executable Content (one of)** — A playbook body MUST declare executable content via one of:
- **`## Groups`** — formal DAG-of-groups per Playbook Spec v2.2 §3. Each Group declares Owner, Parallel, Depends-on, Milestone, Milestone-timeout. Sub-steps declare Executor, Owner, Deadline, Produces, Boundary-call. Recommended for multi-phase, multi-owner, long-duration processes.
- **`## Steps`** OR **`## Execution Steps`** — linear numbered sequence. Two accepted shapes: (a) parent-section shape (single `## Steps` heading containing numbered sub-items); (b) top-level-numbered shape (`## Step N: <title>` headers — minimum two for shape recognition). Recommended for single-session, single-owner, sequential processes.

A playbook MUST use one model OR the other. Hybrid is a validation error.

**4. `## Outcomes`** — End states (not waypoints). Format: `[REQUIRED] <outcome>` / `[OPTIONAL] <outcome>`. At least one `[REQUIRED]` outcome mandatory.

**5. `## Verification`** — Proof of correct execution. MUST declare one method from:

| Method | Description |
|--------|-------------|
| `self-attestation` | Executor confirms completion |
| `peer-review` | Another agent or human reviews output |
| `human-sign-off` | Named human or role must approve |
| `automated-check` | Runtime validates against measurable criteria |
| `cold-boot-test` | 3 independent cold-boot agents execute and check outcomes |
| `external-audit` | Third-party validates |

**Selection heuristic:** lightest method that establishes proof appropriate to risk. Single-session low-stakes → `self-attestation`. Stakeholder-visible multi-session → `peer-review` / `human-sign-off`. Load-bearing OS / governance → `cold-boot-test`. Regulated → `external-audit` / `automated-check`. Verification receipts are structured YAML entries in `run.jsonl` per Spec v2.2 §5.

### Expected-If-Present Body Sections

Not required, but commonly appropriate. When present, conform to patterns:

- **`## Suggestions`** — Soft constraints. Bulleted; one clear guidance statement per item. Strongly recommended for playbooks with human readers.
- **`## Resources`** — Knowledge articles, data sources, reference documents, templates, external systems, sub-playbooks. Structure per Spec v2.2 §3 with subsections (Knowledge Base / External Systems / Templates / Sub-Playbooks).
- **`## Revision History`** OR **`## Changelog`** — Append-only per-version log. Required for `version > 1.0`.

### Optional Body Sections

- **`## Known Enforcement Gaps`** — for honor-system rules pending mechanization. Table form: gap / what closes it / target release / owner.
- **`## Conscious Trade-offs`** — architectural trade-offs documented explicitly.
- **`## Related Playbooks`** — for playbook libraries or cross-referenced sub-playbooks.
- **`## Post-Outcome Handoff`** — REQUIRED if concierge-paths subtype (§Composes-With §Subtypes).
- **`## Report Format`** — REQUIRED if test-harness subtype (§Composes-With §Subtypes).

### Scope — Which Files Are Playbooks?

A file is a **playbook** when all three hold (NEW playbooks at v1.3+):

1. **Filename:** ends in `.playbook.md`
2. **Frontmatter:** `type: playbook`
3. **Body:** all 5 REQUIRED sections present

Files not meeting all three are specs, guides, templates, or notes — not playbooks.

**Legacy grace** (pre-v2.0 lock 2026-04-21): files lacking `type: playbook` or using legacy `status: published` are treated as compliant; next amendment MUST update to v2.0+ values. Body-section requirements apply regardless of age.

**Pipeline subtype** substitutes pipeline.capsule's body-section set for this floor (per §Composes-With §Subtypes); pipeline files satisfy this capsule's governance INTENT at a different grain.

---

## 3. State Machine

```
draft → active → superseded → (state: archived)
 ↑______↓ (revision during draft only; active playbooks amend via version bump OR supersession)
```

**Required starting state:** every new playbook MUST be authored at `status: draft`. Direct creation at `active` or later is a validation error.

Canonical status enum: `status:` ∈ {draft, active, superseded, archived}

| Status | Meaning |
|--------|---------|
| `draft` | Being authored. Required starting state. |
| `active` | Live; governs executions. Runs reference this version via `playbook_version:`. |
| `superseded` | Successor exists (`superseded_by:` set). In-flight runs continue; new runs use successor. |
| `archived` | Retired. No new runs permitted. |

### Valid transitions

- `draft → active` — author finishes first-draft; requires all REQUIRED body sections present + compliant
- `draft → draft` — revisions before active are free
- `active → draft` — pre-amendment revision; rare; prefer version bumps
- `active → active` — in-place version bump for minor corrections; in-flight runs continue on the version they started
- `active → superseded` — successor published; bidirectional `supersedes:` / `superseded_by:` set atomically (Rule 5)
- `superseded → archived` — historical; no remaining runs reference this version
- `any → archived` (direct) — retired without successor; in-flight runs complete under archived content; no new runs

**Legacy aliasing (v1.3 grace):** `status: published` treated as `active`. Legacy files don't need rewriting at v1.3; next amendment MUST update. **NEW authoring:** start at `draft`. Aliasing is for legacy maintenance, NOT permission for new files to skip `draft`.

---

## 4. Validation Rules

### Governance Rules

1. **One active playbook per (`trigger:`, `scope:`) pair.** Duplicates at `status: active` are validation errors. Triggerless playbooks orphaned from this rule until their next amendment adds `trigger:` (RECOMMENDED to add for protection).
2. **Rules section is normative.** Rule violation HALTS execution (runtime obligation; not validator-enforced since content is natural language).
3. **Executable content in exactly one shape.** `## Groups` OR a `## Steps` / `## Execution Steps` section OR top-level-numbered `## Step N:` headers — but not multiple. Neither = spec or guide, not playbook.
4. **Verification method declared.** §Verification MUST name one of the 6 enumerated methods.
5. **Supersession is atomic-commit.** When active playbook is superseded: (a) successor published at `active`, (b) predecessor flipped to `superseded`, (c) bidirectional `supersedes:` / `superseded_by:` set — all in single commit. Non-atomic = Rule 1 violation (two active playbooks for same `trigger + scope`).
6. **Pipeline subtype composes at intent level.** Pipeline files satisfy pipeline.capsule's body-section set (§What This Pipeline Governs / §Stages / §Positions / §Forward-Only Motion Rule / §Stage Transition Rules / §Cold-Boot Walk-Through / §Known Enforcement Gaps) in place of this capsule's REQUIRED floor — equivalent governance intent at different grain. Both capsules' rules apply additively.
7. **Change Log append-only.** Earlier entries stay as historical truth; later entries may correct earlier in prose.
8. **Portability rule** (inherited from Spec v2.2 §4). Playbook logic NEVER references vault-specific UIDs/paths/names in executable content. Vault-specific resolution at the binding layer (`.tropo-studio/bindings/<slug>.binding.md`).
9. **Concierge-paths subtype declares `## Post-Outcome Handoff`.** Per [D2.6+D4.9 design brief (`90b57b3b`)](../../vault/files/90b57b3b.md) — structural fix for v1.3.1 post-outcome routing bypass. Validator enforces honor-system at v1.4; mechanical at v1.5.
10. **Test-harness subtype declares `## Report Format` + verification-output frontmatter.** Operationalizes the v1.4.1 cycle's test-harness pattern as kernel substrate.

### Validation Checks (run at check-in)

In addition to core checks. **[enforced]** = mechanically checkable; **[honor-system]** = v1.3 reader-verified.

1. **[enforced]** Filename ends in `.playbook.md`
2. **[honor-system during v1.3 grace; enforced for new playbooks post-2026-04-21]** `type: playbook` present
3. **[enforced]** All required frontmatter fields present (per §2 Schema Required Frontmatter)
4. **[enforced]** `status:` is one of `draft`, `active`, `superseded`, `archived` (or legacy `published` during grace)
5. **[enforced]** `readers:` is non-empty array of recognized values
6. **[enforced]** `scope:` is one of `single-session`, `multi-session`, `standing`
7. **[enforced]** Body contains all 5 REQUIRED sections (executable-content satisfied by Groups / Steps parent / Execution Steps / minimum-two top-level `## Step N:` headers). Pipelines substitute pipeline.capsule's set.
8. **[enforced]** Body declares executable content via exactly one shape — not multiple.
9. **[enforced]** §Outcomes contains at least one `[REQUIRED]` outcome
10. **[enforced]** §Verification declares one of the 6 methods
11. **[enforced]** New playbook files start at `status: draft`; direct `active` rejected. (Legacy `active` or `published` predating v2.0 lock exempt; see history file Known Enforcement Gaps.)
12. **[enforced]** `supersedes:` / `superseded_by:` (if present) form bidirectional pairs + both resolve to valid entries
13. **[enforced]** If `status: superseded`, `superseded_by:` is set + resolves
14. **[enforced]** If `status: active` or later, `version:` is concrete semver/decimal — not placeholder.
15. **[honor-system]** Cold-boot-verifiable: stranger reading playbook + declared Resources can execute to declared Outcomes.
16. **[honor-system]** §Rules items are unambiguous + testable — each rule mechanically evaluable as passed/violated.
17. **[honor-system]** No vault-specific UIDs/paths/names in executable content (portability per Spec v2.2 §4).
18. **[honor-system]** Pipeline subtype (if applicable): also satisfies pipeline.capsule's validation checks.
19. **[honor-system at v1.4; enforced at v1.5]** Concierge-paths subtype (if applicable): body contains `## Post-Outcome Handoff` section, non-empty.
20. **[honor-system at v1.4.2; enforced at v1.5+]** Test-harness subtype (if applicable): frontmatter contains `target_artifact_type:` + `verdict_format:` (and `mode:` if Strict/Skeptic variants); body contains `## Report Format` section, non-empty.
21. **[stub-warn at v1.4.2; hard-fail at v1.5+]** `composes_into:` ↔ `calls:` bidirectional consistency. Every `composes_into:` entry's named orchestrator MUST list this playbook in `calls:`; every `calls:` entry MUST resolve to a playbook with `composes_into:` pointing back.

Core checks inherited: UID uniqueness, UID immutability, type immutability, owner/created/modified invariants.

---

## 5. Composes-With

### Extends

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor (UID immutability, owner semantics, frontmatter invariants).

### Pattern Exemplar

- **[document.capsule (d0c00001)](document.capsule.md)** — playbook is patterned on document per v3 Decision 3; adds Groups-or-Steps body-shape + 5-required-floor + declared-verification + executable-content discipline.

### Composes With

- **[pipeline.capsule v1.0 (e4c8a6b2)](pipeline.capsule.md)** — subtype. Pipelines are playbooks satisfying pipeline.capsule's three-condition check. Both capsules govern; pipeline.capsule adds requirements; never removes this floor.
- **[Playbook Specification v2.2 (e6d373bc)](../../vault/files/e6d373bc.md)** — aligned-with. This capsule is the machine-checkable contract; the spec is the human-readable architecture covering binding layers, run folders, thread.md, verification receipts, portability rules.
- **[subsystem-hub.capsule v1.5 (8a4e21c5)](subsystem-hub.capsule.md)** — pattern precedent for capsule shape (v1.5 taxonomy: Required / Optional / Beyond-Contract body sections; v1.4 dropped the EXPECTED-IF-PRESENT category as part of contract simplification).
- **[project-plan.capsule v1.0 (f7b9c4a2)](project-plan.capsule.md)** — sibling. Project-plans scope projects; playbooks orchestrate processes. A project-plan may invoke a playbook (via `calls:`).
- **[release-plan.capsule v1.0 (a3f1e7b2)](release-plan.capsule.md)** — sibling at release scope. A release-plan coordinates streams; stream work executes through playbooks.
- **[release.capsule v2.0 (b19e8d43)](release.capsule.md)** — pattern precedent for UID-preserving supersession.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.

### Subtypes

Playbooks support a subtyping pattern. Subtype declares additional requirements atop this capsule's floor; compliant subtypes MUST also satisfy every rule of this capsule.

**Subtype declaration shape — graduation threshold:**

- **In-capsule subtype** — appropriate when additional requirements are minimal: **≤ 2 additional Required Body Sections AND ≤ 2 additional Validation Checks AND no frontmatter SHAPE requirement** (independent fields without cross-validation are FIELD requirements, not SHAPE). Stay in-capsule per earn-the-abstraction discipline.
- **Separate capsule file** — appropriate when substantial: **≥ 3 additional Required Body Sections OR ≥ 3 additional Validation Checks OR ≥ 1 frontmatter SHAPE requirement** (typed shape with cross-validating fields).

*Cardinality clarification:* "shape" requires ≥ 2 cross-validating fields (one field is always field; two-or-more cross-validating is shape).

#### Pipeline (governed by [pipeline.capsule (e4c8a6b2)](pipeline.capsule.md))

Three-condition identification per pipeline.capsule §Scope (canonical): (1) filename `.tropo/playbooks/pipelines/<name>.pipeline.md`, (2) `tags:` includes `pipeline`, (3) frontmatter (`stages`, `positions`, `artifact_types`, `forward_only: true`) declared. Pipeline body-section set substitutes for this floor; both capsules' frontmatter + rules apply additively.

#### Concierge-Paths (in-capsule subtype)

Two-condition identification: (1) filename `.tropo/playbooks/concierge-paths/<name>.playbook.md`, (2) `tags:` includes `concierge-paths`.

**Additional Required Body Section — `## Post-Outcome Handoff`.** Section MUST address: (a) **Bounce intents** — which user intents route back to concierge after completion; MUST cite [executive-activation.template §Routing](../templates/executive-activation.template.md) as **canonical source** for the bounce-intent set (re-stating inline without canonical reference creates parity drift). (b) **Inline intents** — which intents stay with the spawned agent. (c) **Enforcement mechanism** — typically [create-executive-agent.skill (c7ea9e01)](../skills/create-executive-agent.skill.md) baking canonical `## Routing` section into the spawned agent's activation file.

Worked example: [start-a-project.playbook v1.1 (`57a87001`)](../playbooks/concierge-paths/start-a-project.playbook.md).

#### Test-Harness (in-capsule subtype)

Two-condition identification: (1) filename pattern `.tropo/playbooks/<name>.playbook.md` (kernel-tier), (2) `tags:` includes `test-harness`.

**Additional Required Frontmatter:**

| Field | Type | Constraint |
|---|---|---|
| `target_artifact_type` | enum | `release` / `build` / `capsule-definition` / `playbook` / `ledger-entry` / `vault` / `kernel-artifact`. New values via capsule amendment; authors don't mint inline. |
| `verdict_format` | enum | Canonical: `PASS / PASS-WITH-FINDINGS / FAIL`, `PASS / PASS-WITH-GAPS / FAIL`, `PASS-CLEAN / PASS-WITH-NEW-FINDINGS / REGRESSION-FAILURE`, `RATIFY-CLEAN / RATIFY-WITH-REVISIONS / REJECT-REWORK-REQUIRED`, `STRUCTURAL-CONFORMS / STRUCTURAL-CONFORMS-WITH-FINDINGS / STRUCTURAL-VIOLATIONS-PRESENT`. MUST be tri-valued AND middle bucket operationally meaningful with explicit "use this bucket when X" trigger. Convergence note MUST name peer harnesses by record UID. |
| `mode` | enum (optional) | `strict` (read-only structural conformance against declared spec) or `skeptic` (adversarial pressure-test for failure modes spec doesn't enumerate). Omit if single-mode. |

**Additional Required Body Section — `## Report Format`** (positioned AFTER §Verification). Section MUST address: Verdict line (from `verdict_format:`); Evidence section (artifacts the verdict is grounded in); Findings table (P0/P1/P2 severity + named issue + proposed fix); Convergence note (cite peer harness records by UID when multi-instrument BATCH; bias-discount if any).

Note: the playbook's §Verification (Required floor §5) declares how the harness's OWN execution is verified (typically `self-attestation`) — distinct from the harness's verdict on its TARGET, which is declared in §Report Format. Don't conflate.

**Composition rule:** test-harness sub-playbooks declare `composes_into:` typed edges; orchestrator declares `calls:`. Bidirectional consistency enforced by Validation Check 21.

```yaml
# Sub-playbook frontmatter
composes_into:
  - playbook: run-release-test-plan
    role: stage-3-strict-mode

# Orchestrator frontmatter
calls:
  - .tropo/playbooks/dispatch-cold-boot.playbook.md
```

Worked examples: `run-release-test-plan.playbook` (orchestrator) + `dispatch-cold-boot.playbook` (Strict + Skeptic modes) + `dispatch-walker.playbook` ship v1.4.2.

### Future subtypes

Authored in future releases as patterns emerge. Any new subtype: declares `extends: core`, documents composition with this capsule in §Composes-With, names identification check, declares additional requirements atop this floor.

---

*playbook capsule definition | UID `e7b3c509` | v2.5 | history at [1b834ed6](playbook.history.md)*
