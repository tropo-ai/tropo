---
uid: "e02c52b1"
name: "test-scenario"
type: capsule-definition
extends: core
version: 1.1
supersedes_version: "1.0"
tier: os
author: vela
created: 2026-04-20
modified: 2026-06-09
created_by: vela-v32
modified_by: argus-a105
status: locked
locked_by: vela-v32
locked_at: 2026-04-20
meta_status_rollup:
  to-do: [draft]
  in-progress: [active]
  done: [archived]
meta_status_rollup_note: "argus-a104 2026-06-08 — rollup completion per the unified lifecycle knot (move 2, 9f6a1379); additive lock-break."
schema_version: 2
governed_by: "222873b9"
locked_under: "42373659"
aligned_with: "ae0b2ee5"   # test-run.capsule (sibling — scenario specifies; run records)
composes_with: "ae0b2ee5"  # test-run.capsule (every active scenario should produce a run per release)
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# test-scenario — Capsule Definition v1.1 (LOCKED)

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Extends | `core` |

*A vault-agnostic stranger-journey specification for the Release Test Harness. Defines one reproducible end-to-end exercise a new user would perform against a freshly-unzipped Tropo-OS build. Ships with Tropo-OS as part of the reference test kit.*

## Intent

Every Tropo-OS release must be verifiable by exercise, not just by inspection. A `test-scenario` specifies one concrete user journey — "create an agent," "file a task," "retire an agent," "upgrade the vault" — with enough detail that any operator (sub-agent, human tester, or CI runner) can execute it against a build and record a pass/fail verdict.

Scenarios are **vault-agnostic by design**. They reference primitives (agents, playbooks, vault entries) by type and role, not by Argo-specific UIDs. A scenario authored for v1.2 should still run against v1.3, v2.0, or a stranger's own derived vault — the harness is a product artifact, not an Argo-specific exercise.

**A `test-scenario` is a spec. A `test-run` records one execution of the spec against a specific build.**

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `type` | literal | `test-scenario` |
| `title` | string | ≤ 120 chars. Format: `"T-{id} — {imperative-journey}"`. Example: `"T-02 — Create first user agent"`. |
| `description` | string | ≤ 200 chars. What this scenario exercises and why it matters. |
| `scenario_id` | string | Unique slug (e.g., `T-02`). Stable across scenario revisions. Never reused. |
| `owner` | string | Agent responsible for the scenario's authoring + maintenance (typically `vela` or `d.pm`). |
| `stage` | enum | See state machine below. |
| `state` | enum | `active` or `archived`. |
| `applies_to` | enum | `vault-agnostic` (ships as reference test kit — **default**) or `vault-specific` (tied to a named vault). |
| `harness_mode` | enum | `sa-batch`, `human-driven`, or `hybrid`. Declares how this scenario is meant to be executed. (v1.0 note: `ci` enum value deferred until an actual CI/pipeline runner ships; will be reintroduced as `pipeline` with concrete semantics at that time.) |
| `pass_criteria` | array of strings | Bulleted assertions that must ALL hold for the scenario to pass. Each string is one concrete check (e.g., "A new file exists at `agents/<name>/activate.md`"). |

**Note on UID-type fields (applies to frontmatter AND relationships):** all fields whose values are UIDs — `uid`, `relationships.to`, `depends_on` entries pointing at other scenario UIDs, etc. — **MUST be quoted strings** (`uid: "e02c52b1"`, never bare `uid: e02c52b1`). YAML parsers may coerce unquoted 8-hex tokens that happen to match scientific-notation patterns (e.g., `Release Test Harness project`) to `Infinity`. Quoting is the only safe form. This rule was validated against real index corruption caught by sa.release-test-harness record 001 (2026-04-20).

**Note on default `extraction_scope`:** vault-agnostic scenarios default to `extraction_scope: ship` and ship with Tropo-OS as part of the reference test kit. A scenario that ships only in Argo (vault-specific) must explicitly set `extraction_scope: argo-reference`. The default is the safe choice — scenarios are the product surface.

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `depends_on` | array of scenario_ids | Scenarios that must PASS before this one runs (e.g., `T-02` depends on `T-01`). |
| `coverage_domains` | array of strings | Product surfaces this scenario exercises (e.g., `[activation, agent-lifecycle, ledger-write]`). |
| `estimated_duration` | string | Rough time budget (e.g., `"5 min"`). |
| `blast_radius` | array of path glob strings | For `harness_mode: hybrid` (write-flow) scenarios: the filesystem paths this scenario writes to under the build root. Lets the runner decide whether to copy the build to a throwaway directory. Example: `["agents/<created-name>/**", "channels/ops.md", "tasks/<uid>-*.md"]`. Omit for read-only scenarios. |
| `tags` | array | Free-form tags (e.g., `[first-boot, stranger-journey, read-only]`). |
| `relationships` | array of typed edges | Schema v2 unified relationships. |

---

## Required Body Sections

A `test-scenario` body MUST contain these sections, in this order:

1. **Purpose** — one-paragraph statement of what user experience this scenario validates and what failure would mean.
2. **Preconditions** — state the scenario assumes before execution (e.g., "a fresh-unzipped build at `releases/<version>/testing/<build-name>/`"). Include `depends_on` scenarios that must have passed first.
3. **Setup** — ordered steps the operator (or runner) takes to prepare. Keep atomic and verifiable.
4. **Execution Steps** — ordered steps the operator performs. Each step references an action that a real user would take (e.g., "Read `CLAUDE.md`", "Invoke the `create-task` action with inputs X, Y"). **Vault-agnostic — no hardcoded Argo UIDs.** Use placeholders like `<agent-name>`, `<project-uid>`, `<build-root>` where values vary.
5. **Assertions** — the concrete checks mapping to `pass_criteria`. One bullet per assertion. Each must be objectively verifiable (file exists, frontmatter valid, output matches, etc.).
6. **Expected Output** — what the operator should observe/produce if the scenario passes (a screenshot, transcript excerpt, filesystem state description, etc.).
7. **Failure Diagnostic** — what each likely failure looks like and where to look (e.g., "If assertion 3 fails, inspect `<build-root>/playbook-runs/<run-uid>/run.jsonl` for the missing milestone").

Optional:

8. **Regression History** — populated at lock; records when the scenario was added, amended, and by whom.

---

## State Machine

```
draft → active → archived
 ↑______↓ (revision during active)
```

| Stage | Meaning |
|-------|---------|
| `draft` | Scenario being authored. Not yet in the harness. |
| `active` | Scenario is live in the harness; runs produce `test-run` entries. |
| `archived` | Scenario no longer exercised (superseded, obsolete, or replaced by a broader scenario). |

### Valid transitions

- `draft` → `active` — owner + one reviewer approve. Scenario enters the harness.
- `active` → `draft` — revision needed (scenario is being reshaped; pause runs).
- `active` → `archived` — scenario superseded or no longer relevant. Body must carry a reason + link to successor (if any).

---

## Governance Rules

1. **Vault-agnostic by default.** `applies_to: vault-agnostic` is the expected value. `vault-specific` is permitted but must carry a rationale in the Purpose section explaining why a general scenario couldn't capture it.
2. **No Argo UIDs in Execution Steps.** References to primitives use role-based placeholders (`<agent-name>`, `<project-uid>`, `<release-version>`). UIDs may appear in Preconditions to name specific release builds being tested, but never as hardcoded identities.
3. **Assertions must be objectively verifiable.** "The vault feels coherent" is not a valid assertion. "File `<build-root>/.tropo/version.md` contains `version: "<expected>"`" is.
4. **scenario_id is immutable.** Once assigned, never reused or reassigned. Archived scenarios keep their IDs to preserve cross-reference.
5. **Extraction scope.** Ship scenarios carry `extraction_scope: ship` so they propagate to every vault as part of the reference test kit.
6. **Ownership.** Scenarios authored by `vela` or `d.pm` by default. Other agents may author with owner acknowledgement.
7. **One active version per scenario_id.** If a scenario is revised materially, either edit in place (minor) or create a successor with a new scenario_id and archive the old with `superseded_by:`.

---

## Validation Checks (run at check-in)

In addition to core checks:

1. `scenario_id:` matches pattern `^T-\d{2,3}$` (e.g., `T-01`, `T-110`).
2. `stage:` is one of `draft`, `active`, `archived`.
3. `state:` is one of `active`, `archived`.
4. `applies_to:` is one of `vault-agnostic`, `vault-specific`. Default: `vault-agnostic`.
5. `harness_mode:` is one of `sa-batch`, `human-driven`, `hybrid`. (`ci` deferred to future spec when a real pipeline runner ships.)
6. `pass_criteria:` is non-empty array of strings.
7. If `depends_on:` present, every entry is a valid `scenario_id`.
8. Body contains all 7 required sections.
9. If `applies_to: vault-agnostic`, the Execution Steps section SHOULD NOT contain hardcoded UIDs outside the designated placeholder patterns (heuristic — surfaces warnings, not errors).
10. If `stage: archived`, body must carry a "Reason for Archival" note and (if applicable) a link to a successor scenario.
11. All UID-type frontmatter values are quoted strings. Warn (not fail) on bare 8-hex tokens in `uid:`, `relationships.to:`, and any other UID field. This is the rule that prevents scientific-notation coercion (e.g., `9e780757 → Infinity`).
12. If `harness_mode: hybrid` and `blast_radius:` is absent, warn. Hybrid write-flow scenarios should declare their write paths so the runner can isolate.
13. If `applies_to: vault-agnostic` and `extraction_scope` is not `ship`, warn. The default is `ship`; explicit non-ship must carry rationale in body.

---

## Studio — Shop Signage

*Tools and rules-at-a-glance for authoring + maintaining a `test-scenario`. Read this section first when you sit down at the test-scenario bench.*

### Tools

| Tool | Verb (v3 Decision 13) | When |
|---|---|---|
| Manual authoring at `vault/files/<uid>.md` | **author** | Drafting a new scenario; revising an active one |
| Lock-flip on the file | **lock** | Scenario is reviewed and ready for the harness |
| Archive an old scenario when superseded | **archive** | Scenario obsoleted by a successor or no longer relevant |

### Skills

| Skill | When |
|---|---|
| [sa.release-test-harness](../../agents/sa/sa.release-test-harness/sa.release-test-harness.md) | The runner. Executes `harness_mode: sa-batch` and `hybrid` scenarios; produces a [test-run](test-run.capsule.md) per execution |
| [create-design-spec.action.md](../actions/create-design-spec.action.md) (analogue) | Pattern for authoring a governed spec entry; scenarios follow the same drafting discipline |

### Procedures

- **Authoring a new scenario.** (1) Pick the next `scenario_id` (`T-NN` format; never reuse). (2) **Generate a UID** via `openssl rand -hex 4` (or any random-hex source). (3) Author at `vault/files/<uid>.md` with `type: test-scenario`, `stage: draft`. (4) Fill all 7 required body sections. (5) Set `applies_to: vault-agnostic` (default) — use role-based placeholders, not Argo UIDs, in Execution Steps. (6) Get owner-plus-one-reviewer approval (record by file edit by the reviewer + a one-line ack post on [channels/ops.md](../../channels/ops.md), or by review entry in the file's Regression History section). (7) Flip `stage: draft → active`. The scenario is now in the harness.
- **Revising an active scenario.** Flip `stage: active → draft` to pause runs while reshaping. Edit. Flip back to `active`. The `scenario_id` stays put — it's immutable.
- **Archiving a scenario.** Flip `stage: active → archived`. Body must add a "Reason for Archival" note + link to a successor scenario if one exists.
- **Quoting all UIDs.** All UID-type frontmatter values (`uid:`, `relationships.to:`, `depends_on:` entries) MUST be quoted strings. Bare 8-hex tokens are coerced to `Infinity` by some YAML parsers (validated against real index corruption — sa.release-test-harness record 001, 2026-04-20).

### Rules at a glance

1. **Vault-agnostic by default.** No Argo UIDs in Execution Steps; use placeholders. `vault-specific` is permitted but must carry a rationale in Purpose.
2. **Assertions must be objectively verifiable.** "Feels coherent" is not an assertion. "File X exists" is.
3. **`scenario_id` is immutable.** Never reused or reassigned. Archived scenarios keep their IDs.
4. **One active version per scenario_id.** Material revisions either edit in place (minor) or supersede with a new ID + archive the old (major).
5. **Quote UID-type fields.** Always.

### Pitfalls

- **Hardcoded Argo UIDs in Execution Steps** → scenarios won't run against a stranger's vault. Use `<agent-name>`, `<project-uid>`, `<release-version>` placeholders.
- **Subjective `pass_criteria`** ("the agent feels responsive") → scenarios that can't be objectively scored. Rewrite as concrete file-state / output-shape / frontmatter checks.
- **Reusing a `scenario_id` after archival** → breaks cross-references. New journey gets a new ID.
- **Bare 8-hex UID values** → YAML scientific-notation coercion. Quote everything.
- **Missing `blast_radius:` on a `harness_mode: hybrid` scenario** → runner can't decide whether to copy the build to a throwaway directory before executing.
- **Validation Check 9 ("hardcoded UIDs in Execution Steps") is a WARNING, not a FAIL.** A vault-agnostic scenario with leaked Argo UIDs will pass validation silently. Manual review before lock is the second line of defense — don't take warning-silence as success.

### Worked examples

- **[sa.release-test-harness records 001 + 002](../../agents/sa/sa.release-test-harness/activation-log/)** — the only live evidence of a test-scenario being executed in this vault. Read these to see what a scenario produces in execution + what a re-run looks like (record 002 archived record 001's run after the v1.2.1 hotfix).
- **Stranger-encounter is also exercised via the lighter [sa.cold-boot](../templates/agents-skeleton/sa/sa.cold-boot/sa.cold-boot.md) path** dispatched by [evaluate-tropo.playbook](../playbooks/concierge-paths/evaluate-tropo.playbook.md) Step 4. That path doesn't author a formal `test-scenario` entry — it's the inline-prompt fallback. Full `test-scenario` discipline applies when the scenario is meant to be re-run across releases (the harness path, not the cold-boot inline path).
- **Future:** kernel-seed scenarios at `.tropo/seed/test-scenarios/<id>.md` are a candidate convention for v1.4.1; the directory is not yet populated. Until then, sa.release-test-harness records 001/002 are the canonical reference set.

### Go next

- **Pair capsule:** [test-run.capsule (ae0b2ee5)](test-run.capsule.md) — records one execution of this scenario against a specific release.
- **Runner:** [sa.release-test-harness](../../agents/sa/sa.release-test-harness/sa.release-test-harness.md) (Argo's harness runner; the matching ship-class primitive is [sa.cold-boot](../templates/agents-skeleton/sa/sa.cold-boot/sa.cold-boot.md)).
- **Stream context:** [v1.3 Stream: Release Test Harness v1.0 maturation (42373659)](../../vault/files/42373659.md) — where this capsule was locked.

---

## Relationship to `test-run`

A `test-scenario` is the **specification**. A `test-run` is a **record of one execution** of that specification against a specific release build.

| Dimension | `test-scenario` | `test-run` |
|-----------|-----------------|------------|
| **Verb** | specifies | records |
| **Mutability** | editable through `active` | immutable after created |
| **When authored** | once per journey | once per (scenario, release) pair |
| **Scope** | vault-agnostic user journey | concrete execution: date, verdict, evidence |
| **Lifecycle** | `draft → active → archived` | `pending → running → pass/fail/skip/partial` |

One scenario generates many runs over time. Each `test-run` references its scenario by UID.

---

## Ship Scope

Scenarios with `extraction_scope: ship` ship in the release bundle at `vault/files/<uid>.md` and are indexed in the release's 00-index. A stranger unzipping Tropo-OS gets the reference test kit automatically — they can run scenarios against their own vault without re-authoring anything.

---

## Inheritance

Extends `core`. Inherits UID uniqueness/immutability, type immutability, owner/created/modified invariants.

---

## Resolutions (v0.1 → v1.0 lock, 2026-04-20)

Resolved at lock by Vela V32 under Mike's direction. Context: v0.1 prototype was authored same-day during the v1.2 ship cycle; the first live run (sa.release-test-harness record 001) validated the shape and surfaced 2 additional lessons beyond the original 4 open questions. Lock proceeds as the first deliverable of the [v1.3 Stream: Release Test Harness v1.0 maturation (42373659)](../../vault/files/42373659.md) under the v1.3 release container.

### Original v0.1 open questions

- **Q1 — structured `pass_criteria` objects vs strings.** **DEFERRED to v1.1+.** The current LLM-driven runner (sa.release-test-harness) executes string-based pass criteria plus the Assertions body section without friction. Structured `{assertion, method, expected}` objects would be required for a non-LLM CI/pipeline runner. No such runner exists in v1.0; revisit when one is in flight.

- **Q2 — optional `blast_radius` field.** **APPLIED.** New optional frontmatter field declares filesystem write paths for hybrid scenarios. Warns on hybrid scenarios that omit it. Lets the runner decide when to copy the build to a throwaway directory.

- **Q3 — `evidence_template` capsule for `human-driven` scenarios.** **DEFERRED.** No human-driven scenarios authored yet. Add the sibling capsule when the first one ships (candidate: T-07 multi-harness parity).

- **Q4 — `extraction_scope: ship` as default.** **APPLIED.** Vault-agnostic scenarios default to `ship`; argo-reference is an explicit override with rationale. New validation check warns on the mismatch.

### Harness-validated additions (discovered during first live run)

- **A1 — UID-type fields must be quoted strings.** **APPLIED** as a validation check + a note in the frontmatter section. The first `vault:rebuild` on test-run `v1.3 historical reference` parsed bare `Release Test Harness project` as `Infinity`. Quoting is the only safe form.

- **A2 — Drop `harness_mode: ci` enum value.** **APPLIED.** The v0.1 enum carried `ci` as future tense with no concrete runner. v1.0 trims to `sa-batch`, `human-driven`, `hybrid`. A `pipeline` enum value will be added when a real pipeline runner ships with specified semantics.

### Items carried forward as v1.1+ backlog

- Structured `pass_criteria` (Q1) — add when non-LLM runner appears.
- `evidence_template` capsule (Q3) — add when first human-driven scenario is authored.
- `pipeline` harness_mode enum — add when real CI/pipeline runner ships.

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 0.1 | 2026-04-20 | Initial DRAFT. Vault-agnostic by default per Mike direction. Ships with Tropo-OS as reference test kit. First live run (sa.release-test-harness record 001) validated the shape and surfaced 2 additional lessons. | vela-v32 |
| **1.0** | **2026-04-20** | **LOCKED.** v0.1 open questions resolved: Q2 (blast_radius) and Q4 (ship default) applied; Q1 and Q3 deferred to v1.1+. Harness lessons A1 (quoted UIDs) and A2 (drop `ci` enum) applied. Lock under [v1.3 Stream 42373659](../../vault/files/42373659.md). | vela-v32 |
| **1.1** | **2026-04-28** | **Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop).** Added §Studio — Shop Signage section (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next) per the v3 capsule shop-signage pattern proven at 17-capsule scale. Added `aligned_with: ae0b2ee5` + `composes_with: ae0b2ee5` (sibling test-run.capsule). No semantic changes to §Required Frontmatter / §Required Body Sections / §Validation Checks / §Governance Rules / §State Machine. UID preserved at e02c52b1. | argus-a38 |

---

*test-scenario capsule definition | LOCKED v1.1 | argus-a38 | 2026-04-28 (Stream 3 D3.2 — §Studio + sibling relations); v1.0 lock 2026-04-20 by Vela V32 preserved in git history*
*"The journey is the spec. The record is the run."*
*Spec governance: [222873b9](../../vault/files/222873b9.md) (Ledger Schema v2) | Locked under [v1.3 Stream: Release Test Harness v1.0 maturation (42373659)](../../vault/files/42373659.md).*
