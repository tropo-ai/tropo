---
uid: "ae0b2ee5"
name: "test-run"
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
  to-do: [pending]
  in-progress: [running]
  done: [done]
meta_status_rollup_note: "argus-a104 2026-06-08 — rollup completion per the unified lifecycle knot (move 2, 9f6a1379); additive lock-break."
schema_version: 2
governed_by: "222873b9"
locked_under: "42373659"
aligned_with: "e02c52b1"   # test-scenario.capsule (sibling — scenario specifies; run records)
composes_with: "e02c52b1"  # test-run records one execution of one test-scenario against one release
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# test-run — Capsule Definition v1.1 (LOCKED)

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Extends | `core` |

*An immutable execution record of a single `test-scenario` run against a specific Tropo-OS release build. The permanent trail of what was tested, when, by whom, and with what verdict. Together, all `test-run` entries for a release form the evidentiary basis for the ship decision.*

## Intent

A `test-scenario` specifies a user journey. A `test-run` records one execution of that journey. The pair mirrors `release-plan` / `release` — the scenario plans, the run records what happened.

Every ship should produce a **full run-set** — one `test-run` for each active scenario in the harness at ship time. Missing runs are honest gaps, not silent passes. A scenario tagged `active` with no run for the current release is a signal the harness didn't cover that ground.

Runs are immutable after creation. Failed runs become regression records; their presence alongside subsequent passes preserves the history of "this used to fail and got fixed."

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `type` | literal | `test-run` |
| `title` | string | ≤ 120 chars. Format: `"Run: {scenario_id} against {release_version} — {verdict}"`. Example: `"Run: T-01 against v1.2.0 — PASS"`. |
| `description` | string | ≤ 200 chars. One-line outcome summary. |
| `scenario` | UID | The `test-scenario` this run exercises. Must resolve to a `test-scenario` at `stage: active` (or `archived` for historical runs). |
| `release` | UID | The `release` entry this run validates. Must resolve to a `release` entry. |
| `owner` | string | Agent or human who conducted the run. |
| `stage` | enum | See state machine below. |
| `state` | enum | `active` (current verdict for this scenario+release pair) or `archived` (superseded by a re-run). |
| `verdict` | enum | `pass`, `fail`, `partial`, `skip`, `blocked`. Required when `stage: done`. |
| `run_date` | ISO 8601 datetime | When the run executed. |

**Note on UID-type fields (applies to frontmatter AND relationships):** all fields whose values are UIDs — `uid`, `scenario`, `release`, `previous_run`, `regression_from`, `relationships.to`, etc. — **MUST be quoted strings** (e.g., `scenario: "e02c52b1"`, never bare `scenario: e02c52b1`). YAML parsers may coerce unquoted 8-hex tokens that match scientific-notation patterns (e.g., `Release Test Harness project`) to `Infinity`. Quoting is the only safe form. Validated by sa.release-test-harness record 001 (2026-04-20) which produced the corruption before this rule was applied.

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `operator` | string | The runner identity — `sa.release-test-harness`, human name, CI job ID. Distinct from `owner` (who owns the run record) vs. who executed. |
| `harness_mode` | enum | Which mode actually ran (`sa-batch`, `human-driven`, `hybrid`). Should match the scenario's declared mode; divergence is worth noting. (`ci` was dropped in test-scenario.capsule v1.0 lesson A2 and is dropped here at v1.1 for symmetry; will be reintroduced as `pipeline` when a real CI runner ships with concrete semantics.) |
| `duration_ms` | integer | Execution wall-clock time in milliseconds. |
| `evidence` | array of paths | Paths to transcripts, screenshots, record files, log excerpts the run produced. |
| `regression_from` | UID | If this is a `fail` that was a `pass` in a prior release, the UID of the prior passing run. Makes regressions legible in the graph. |
| `previous_run` | UID | The most recent prior run of this same scenario (any verdict). Forms a chain per scenario. |
| `gaps` | array of integers | If `verdict: partial`, the specific assertion indices (1-based, from the scenario's `pass_criteria` array) that weren't exercised. Example: `gaps: [3, 8]`. Free-form reason may appear in body §3 Assertion Results; the indices make the partial verdict legible at a glance. |
| `blockers` | array of strings | If `verdict: blocked`, what prevented execution (e.g., "prerequisite T-01 failed"). |
| `relationships` | array of typed edges | Schema v2 unified relationships. |

---

## Required Body Sections

A `test-run` body MUST contain these sections, in this order:

1. **Run Context** — what scenario, which release build, who ran it, when.
2. **Execution Summary** — one paragraph describing what the runner actually did. Include mode (sa-batch / human-driven / hybrid), operator identity, and any deviation from the scenario spec.
3. **Assertion Results** — one row per `pass_criteria` from the scenario, with result (pass/fail/skip) and evidence reference.
4. **Verdict** — the overall disposition with 1–2 sentences of rationale. Matches the `verdict:` frontmatter.
5. **Findings** — any observations beyond pass/fail — gaps, surprises, regressions, recommendations for scenario revision.

Optional:

6. **Evidence Appendix** — quoted transcripts, log excerpts, paths to screenshots.
7. **Follow-ups** — tasks filed as a consequence of this run (fixes, new scenarios, scenario revisions).

---

## State Machine

```
pending → running → done → (state: archived when superseded)
 ↓
 (terminal: no transitions out of done)
```

| Stage | Meaning |
|-------|---------|
| `pending` | Run scheduled or queued, not yet started. |
| `running` | Execution in progress. Intermediate evidence may be appended. |
| `done` | Execution complete. `verdict:` is set. Body is immutable from this point. |

### Valid transitions

- `pending` → `running` — operator picks up the run.
- `running` → `done` — verdict determined, body closed.
- There is no transition OUT of `done`. Re-running a scenario produces a new `test-run` entry; the old one is marked `state: archived` and the new one takes `state: active`.

---

## Verdict Semantics

| Verdict | Meaning | When appropriate |
|---------|---------|------------------|
| `pass` | All assertions passed. | Scenario fully exercised and green. |
| `fail` | One or more assertions failed. | Scenario exercised, broke. File follow-up. |
| `partial` | Some assertions passed, others were skipped (not failed). | Scenario exercised partially — e.g., a known gap, or an intermediate stop. Populate `gaps:`. |
| `skip` | Run not executed deliberately. | Scenario archived for this release, or prerequisite not met by design. |
| `blocked` | Run could not execute because of an external prerequisite. | Prerequisite scenario failed; environment not available. Populate `blockers:`. |

**`fail` and `partial` are both useful verdicts.** They record honest gaps. `skip` and `blocked` are not substitute for `fail` when something actually broke.

---

## Governance Rules

1. **Immutability after `done` — with a single carve-out for supersession.** Once `stage: done`, the run record is immutable **except for the `state:` field**, which may flip `active ↔ archived` to support supersession by re-runs (see Rule #2). No other field may be edited after `done`. Corrections to content are made by filing a new run, not by editing the closed one. The carve-out was validated end-to-end by sa.release-test-harness record 002 archiving record 001's test-run when the v1.2.1 re-run superseded the v1.2.0 fail (2026-04-20).
2. **One active run per (scenario, release) pair.** Re-runs supersede earlier runs via `state: active` ↔ `state: archived`. The most-recent run for a scenario+release is the canonical verdict.
3. **scenario + release are both required.** A test-run with no scenario or no release is not a valid run; it's an orphan.
4. **Verdict must match the body.** If body Assertion Results show all green, `verdict:` must be `pass`. If any assertion is red, `verdict:` must be `fail` (or `partial` if some weren't run).
5. **Regressions must be linked.** If a run is `fail` and a prior run of the same scenario was `pass`, populate `regression_from:` so the graph shows the regression.
6. **Evidence is referenced, not embedded.** Large transcripts live at their own paths (record files, log files, screenshot paths). `evidence:` is an array of pointers, not blobs.
7. **Extraction scope.** `test-run` entries are `extraction_scope: argo-reference` by default — they are Argo's test history, not part of the shipped reference kit. (Scenarios ship; runs don't.)

---

## Validation Checks (run at check-in)

In addition to core checks:

1. `scenario:` resolves to a `test-scenario`.
2. `release:` resolves to a `release` entry.
3. `stage:` is one of `pending`, `running`, `done`.
4. `state:` is one of `active`, `archived`.
5. If `stage: done`, `verdict:` is set and is one of `pass`, `fail`, `partial`, `skip`, `blocked`.
6. If `verdict: partial`, `gaps:` is non-empty and every entry is a positive integer (1-based assertion index).
7. If `verdict: blocked`, `blockers:` is non-empty.
8. If `verdict: fail` and a prior run of the same scenario exists at `pass`, warn if `regression_from:` is not set.
9. Body contains all 5 required sections.
10. Only one active run per (scenario, release) pair (enforced by a cross-run check).
11. All UID-type frontmatter values are quoted strings. Warn (not fail) on bare 8-hex tokens in `uid:`, `scenario:`, `release:`, `previous_run:`, `regression_from:`, and `relationships.to:`. Prevents scientific-notation coercion (`9e780757 → Infinity`).
12. Post-`done` edits to any field OTHER than `state:` are a governance violation. Only `state: active ↔ archived` is permitted post-`done`.

---

## Studio — Shop Signage

*Tools and rules-at-a-glance for opening, executing, and closing a `test-run`. Read this section first when you sit down at the test-run bench.*

### Tools

| Tool | Verb (v3 Decision 13) | When |
|---|---|---|
| Manual record authoring at `vault/files/<uid>.md` | **author** | Creating a new run record (stage: pending) |
| Stage flip pending → running → done | **close** | Run executes and verdict is determined; body becomes immutable from this point |
| State flip active → archived on supersession | **archive** | A re-run of the same scenario+release pair is recorded; predecessor flips to archived |
| Re-run a scenario against a release | **author** + **archive** | Re-run = author a new test-run record (new UID, `state: active`) + archive the predecessor's `state: active → archived`. NOTE: re-runs do NOT use the `supersede` verb — that verb is reserved for the `supersedes:` / `superseded_by:` field pair (which test-run does not declare); test-runs use state-flip archival instead per Governance Rule #2 |

### Skills

| Skill | When |
|---|---|
| [sa.release-test-harness](../../agents/sa/sa.release-test-harness/sa.release-test-harness.md) | The Argo runner. Auto-generates runs for `harness_mode: sa-batch` and `hybrid` scenarios |
| Manual operator authoring | For `harness_mode: human-driven` scenarios — a human conducts the run and authors the record |

### Procedures

- **Opening a run.** Generate a UID via `openssl rand -hex 4` (or any random-hex source). Author a record at `vault/files/<uid>.md` with `type: test-run`, `stage: pending`, `scenario: "<test-scenario uid>"` (quoted), `release: "<release uid>"` (quoted). Both `scenario:` and `release:` are required and must resolve.
- **Executing.** Flip `stage: pending → running` when the operator begins. Append intermediate evidence as needed (assertions partially complete, mid-run findings).
- **Closing.** When verdict is determined, set `verdict:` (`pass | fail | partial | skip | blocked`) and flip `stage: running → done`. From this point the body is immutable; only `state:` may flip later (for supersession).
- **Superseding via re-run.** A re-run of the same (scenario, release) pair lands as a new `test-run` at `state: active`. Flip the prior run's `state: active → archived`. The most-recent active run is the canonical verdict.
- **Linking regressions.** If `verdict: fail` and a prior run of the same scenario was `pass` in an earlier release, populate `regression_from: <prior-run-uid>`. The regression is now legible in the graph.
- **Quoting all UIDs.** All UID-type frontmatter values (`uid:`, `scenario:`, `release:`, `previous_run:`, `regression_from:`, `relationships.to:`) MUST be quoted strings. Validated against real index corruption (sa.release-test-harness record 001, 2026-04-20).

### Rules at a glance

1. **Immutable after `done`** — body and all fields except `state:` are sealed. Corrections by filing a new run, not editing.
2. **One active run per (scenario, release) pair** — re-runs supersede via `state` flip.
3. **`scenario:` + `release:` are both required** — a run with either missing is an orphan.
4. **Verdict matches the body** — if assertions are green, `verdict: pass`. If any are red, `fail` or `partial`.
5. **Regressions linked** — `verdict: fail` + prior `pass` on same scenario → set `regression_from:`.
6. **Evidence referenced, not embedded** — `evidence:` is an array of pointers to record files / log paths / screenshots.
7. **Quote UID-type fields** — always.

### Pitfalls

- **Editing any field after `done` other than `state:`** → governance violation. Re-run is the protocol for corrections.
- **Multiple active runs per (scenario, release) pair** → ambiguous canonical verdict. Always flip the predecessor to `archived` when superseding.
- **`verdict: fail` without `regression_from:` on a regression** → the graph misses the pattern. Populate it.
- **Embedding large transcripts in `evidence:`** → frontmatter bloat. Reference via path; let the record file hold the bulk.
- **Bare 8-hex UIDs** → `Infinity` coercion. Quote everything.
- **Skipping `gaps:` on a `verdict: partial`** → the partial is illegible. Populate the assertion-index array.

### Worked examples

- **sa.release-test-harness record 001** (2026-04-20) — first live run of T-01 against v1.2.0; surfaced the unquoted-UID corruption that drove this capsule's v1.0 A1/A2 amendments.
- **sa.release-test-harness record 002** (2026-04-20) — re-run after v1.2.1 hotfix; archived record 001's run via `state` flip; validated the supersession carve-out (Governance Rule #1) end-to-end.

### Go next

- **Pair capsule:** [test-scenario.capsule (e02c52b1)](test-scenario.capsule.md) — the journey this run records.
- **Release context:** [release.capsule (b19e8d43)](release.capsule.md) — the release this run validates.
- **Stream context:** [v1.3 Stream: Release Test Harness v1.0 maturation (42373659)](../../vault/files/42373659.md) — where this capsule was locked.

---

## Relationship to `test-scenario` and `release`

```
test-scenario (spec) ─────────────────┐
 │
 exercised_by │
 ▼
test-run (execution record) ─── validates ─── release
```

A scenario accumulates runs over time (one per release, sometimes multiple if a release is re-verified). A release accumulates runs across all its scenarios. The pair defines the test coverage matrix — visible at a glance via `member_of` + graph queries.

---

## Ship Scope

`test-run` entries are `extraction_scope: argo-reference` — they remain in Argo as the test-history record and do not ship in the release. A stranger unzipping Tropo-OS gets scenarios (the test kit) but not Argo's run history (Argo's private verification ledger).

---

## Inheritance

Extends `core`. Inherits UID uniqueness/immutability, type immutability, owner/created/modified invariants.

---

## Resolutions (v0.1 → v1.0 lock, 2026-04-20)

Resolved at lock by Vela V32 under Mike's direction. Context: v0.1 prototype was authored same-day during the v1.2 ship cycle; first live run (sa.release-test-harness record 001) and supersession (record 002) validated the pair pattern and surfaced additional lessons. Lock proceeds as a deliverable of the [v1.3 Stream: Release Test Harness v1.0 maturation (42373659)](../../vault/files/42373659.md).

### Original v0.1 open questions

- **Q1 — auto-generated vs manual runs.** **RESOLVED AS: BOTH PERMITTED, DOCUMENTED.** The capsule allows either. The Phase 1 runner (`sa.release-test-harness`) auto-generates runs for `harness_mode: sa-batch` and `hybrid` scenarios. Human operators author runs for `harness_mode: human-driven` scenarios. No capsule edit needed; clarified in body.

- **Q2 — auto-file follow-up tasks on fail.** **DEFERRED.** Keeps the "parent executive decides" contract declared in the runner's activation file. Auto-filing on fail risks noise (e.g., flaky tests producing N tasks per retry) and removes human judgment from the loop. Revisit if/when scenarios stabilize to the point that failure = real bug.

- **Q3 — `release-run-summary` capsule for per-release aggregation.** **DEFERRED.** A graph query (`member_of: <release-uid>` plus `type: test-run`) gives the same aggregate without adding a wrapper artifact. Don't add entities for queries that already work.

- **Q4 — `gaps:` as assertion indices.** **APPLIED.** Changed `gaps:` type from array-of-strings to array-of-integers (1-based assertion indices from the scenario's `pass_criteria` array). Free-form reason may appear in body §3 Assertion Results, but the structured indices make a partial verdict scannable at a glance.

### Harness-validated additions (discovered during live runs 001 + 002)

- **A1 — `state:` carve-out to immutability rule.** **APPLIED.** Governance Rule #1 now explicitly permits `state: active ↔ archived` post-`done` to support supersession by re-runs. All other fields remain immutable after `done`. Validated end-to-end by record 002 archiving record 001's test-run cleanly.

- **A2 — UID-type fields must be quoted strings.** **APPLIED** as validation check #11 + a frontmatter note. The first `vault:rebuild` on the test-run graph coerced bare `Release Test Harness project` to `Infinity`. Quoting is canonical.

### Items carried forward as v1.1+ backlog

- Auto-file-task-on-fail (Q2) — revisit when scenario stability warrants.
- `release-run-summary` capsule (Q3) — add if a human UI pulls summary over graph query.

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 0.1 | 2026-04-20 | Initial DRAFT. Complements `test-scenario` capsule (e02c52b1). Pair-relationship mirrors release-plan / release. | vela-v32 |
| **1.0** | **2026-04-20** | **LOCKED.** Q4 (gaps as indices) applied; Q1 documented; Q2 + Q3 deferred. Harness lessons A1 (state carve-out to immutability) and A2 (quoted UIDs) applied. Lock under [v1.3 Stream 42373659](../../vault/files/42373659.md). | vela-v32 |
| **1.1** | **2026-04-28** | **Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop).** Added §Studio — Shop Signage section (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next) per the v3 capsule shop-signage pattern proven at 18-capsule scale. Added `aligned_with: e02c52b1` + `composes_with: e02c52b1` (sibling test-scenario.capsule — pair where scenario specifies and run records). No semantic changes to §Required Frontmatter / §Required Body Sections / §Validation Checks / §Governance Rules / §State Machine. UID preserved at ae0b2ee5. | argus-a38 |

---

*test-run capsule definition | LOCKED v1.1 | argus-a38 | 2026-04-28 (Stream 3 D3.2 — §Studio + sibling relations); v1.0 lock 2026-04-20 by Vela V32 preserved in git history*
*"The record is the evidence. The evidence is the ship signal."*
*Spec governance: [222873b9](../../vault/files/222873b9.md) (Ledger Schema v2) | Locked under [v1.3 Stream: Release Test Harness v1.0 maturation (42373659)](../../vault/files/42373659.md).*
