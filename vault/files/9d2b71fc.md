---
uid: 9d2b71fc
name: "completion-report"
type: capsule-definition
extends: core
version: "1.0"
tier: os
author: argus
created: 2026-05-31
modified: 2026-05-31
modified_by: argus-a89
created_by: argus-a89
status: active
schema_version: 2
extraction_scope: ship
ships_in_v: v1.62.0
governed_by: 8dd772a0
member_of:
  - "8dd772a0"   # tropo-governance
composes_with:
  - "cdc1615e"   # v1.62 spine — the completion report IS component (C), the human surface + F4 instrument
  - "b62c1f01"   # v1.62 cycle brief (Lane A4 + B7 + P1)
  - "c1a62d3f"   # v1.62 dev-spec — commits this capsule as NEW (open dev-pipeline activation 67ab9db2)
  - "5a8f3b2c"   # pipeline-run.capsule — the report is rendered FROM run.jsonl
  - "e4c8a6b2"   # pipeline.capsule — per-step verdicts mirror the Rule 11 gate outcome
---

# completion-report.capsule

*The typed schema for the human-readable completion report rendered at every pipeline-end. The F4 instrument from [cdc1615e](../../vault/files/cdc1615e.md): v1.60/v1.61 read "done" on every board while their cascades were hollow, because nothing surfaced the per-step verdict — a human had to ask. This report makes the verdict visible by construction.*

## 1. Intent

At the end of **every** pipeline run, the engine ([pipeline-runtime.py](../../vault/tools/9e7003b1.py) `render_completion_report()`, v1.62 Lane B7) renders a completion report **from `run.jsonl`** — the canonical event log of the run. The report is the human surface over the verification the engine already performed: every step, its verdict, its per-criterion breakdown, and any notes/dispositions. It composes with the Workbench-Surface-Visibility doctrine and is the artifact Po (the presentation lane) translates for the principal.

The data already exists in `run.jsonl`. This capsule governs the *shape* of the rendered report so it is consistent, machine-checkable, and Po-presentable across every pipeline-end.

## 2. Schema

### Canonical location
- Rendered to the run's workspace: `<run-folder>/completion-report.md` (one per run, overwritten on re-render; the run.jsonl is the source of truth).
- Optionally surfaced as a `type: completion-report` vault entry when a cycle wants the report graph-walkable (e.g., linked from the release entry); the run-folder file is the floor, the vault entry is opt-in.

### Required Frontmatter (when rendered as a vault entry; in addition to core)

| Field | Type | Meaning |
|---|---|---|
| `type` | string | `completion-report` |
| `run_uid` | string (8-hex) | The pipeline-run this report renders |
| `pipeline_uid` | string (8-hex) | The pipeline definition |
| `overall_verdict` | enum | `complete` / `complete-with-authorized-skips` / `incomplete-gaps` / `blocked` |
| `rendered_at` | ISO date | When the report was rendered |
| `rendered_by` | string | `pipeline-runtime` (engine) or the rendering agent |

### Required Body Sections (in declared order)

1. **§Overall Verdict** — the run's terminal state + a one-line summary (e.g., "BLOCKED — close-cycle: doc/test runs not retired").
2. **§Per-Step Table** — one row per step: `step name | step_owner_role | verdict (PASS/FAIL/SKIP/BLOCKED) | criteria checked (N/M passed) | notes`. The verdict mirrors the engine's `verification_receipt` / natural-output verdict for that step.
3. **§Per-Criterion Breakdown** — for any step with `exit_criteria`, each criterion + its individual verdict + the substrate it resolved against. This is the anti-hollowness surface: a reader sees exactly which assertions held.
4. **§Notes / Findings / Dispositions** — authorized skips (with authorizer), gaps, waivers-on-record, and any sentinel (sa.criteria-reviewer) flags carried forward.

## 3. Governance Rules (in addition to core)

1. **Rendered from `run.jsonl`, never hand-authored.** The report is a projection of the event log. A hand-edited completion report is a Rule-1 violation (it reintroduces the self-attestation the gate removed). Re-render from the log instead of editing.
2. **One report per pipeline-end, every run — no exceptions.** A run that completes (or blocks) without a rendered report is itself an incomplete cascade (the F4 failure). The engine renders unconditionally.
3. **The overall_verdict mirrors the engine, not the agent.** `complete` requires `assert_all_steps_verified` to have passed (pipeline.capsule Rule 11). The report cannot claim `complete` while any step verdict is FAIL/BLOCKED.

## 4. Validation Checks (run at vault rebuild, when rendered as a vault entry)

1. `type: completion-report`; `run_uid` + `pipeline_uid` resolve.
2. `overall_verdict` ∈ enum.
3. Body contains §Overall Verdict, §Per-Step Table, §Per-Criterion Breakdown, §Notes in order.
4. `overall_verdict == complete` is INVALID if any §Per-Step Table row carries verdict FAIL or BLOCKED (mirrors Rule 11 + release.capsule v3.10 Rule 17).

## 5. Composes-With

- **[pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md)** — the report renders from the run's `run.jsonl` event sequence (verification_receipt + step_completed + workflow_complete events).
- **[pipeline.capsule (e4c8a6b2)](pipeline.capsule.md)** — per-step verdicts are the Rule 11 gate outcomes made visible.
- **[release.capsule v3.10 Rule 17](release.capsule.md)** — a release cannot ship `status: done` while its cascade runs are active; the completion report is where that is read.
- **Po (presentation lane)** — Po translates the report for the principal (v1.62 Lane P1).

---

*completion-report.capsule | UID `9d2b71fc` | v1.0 | Argus A89 2026-05-31 | v1.62 spine component C — the F4 instrument | "the verdict was always in the log; this makes it visible"*
