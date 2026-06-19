---
uid: f2a8c3e1
name: "playbook-run"
type: capsule-definition
extends: core
version: 2.1
supersedes_version: "2.0"
tier: vault
author: argus
created: 2026-04-14
modified: 2026-04-25
modified_by: argus-a34
status: locked
schema_version: 2
governed_by: 222873b9
aligned_with: e7b3c509   # playbook.capsule v2.1 — the definition this run instantiates
composes_with: e7b3c509  # every playbook-run pins exactly one playbook (definition ↔ instance)
pattern_exemplar: 5a8f3b2c # pipeline-run.capsule v1.0 — sibling instance-vs-definition pattern
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# playbook-run — Capsule Definition v2.1

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [playbook.capsule (e7b3c509)](playbook.capsule.md) |
| Pattern exemplar | [pipeline-run.capsule (5a8f3b2c)](pipeline-run.capsule.md) |
| Extends | `core` |
| Composes with | [playbook.capsule (e7b3c509)](playbook.capsule.md) |

*A playbook run is a single execution instance of a playbook. It is the state persistence unit for all execution that happens under a governed process.*

*v2.1 (2026-04-25, Argus A34) adds §Studio — Shop Signage + Relations Header per Stream 3 D3.2 of v1.4. v2.0 lock 2026-04-16 by Argus A23 preserved. UID `f2a8c3e1` preserved across the amendment.*

## Intent

Track one execution of one playbook, from authorization to completion. A playbook run is not the playbook itself (that lives in `.tropo/playbooks/`) — it is the instance. Each run has its own identity, its own context, its own event log, and its own working memory.

**Ask:** *"Which project does this run belong to?"* Every run has a parent project. No orphaned runs.

**Use a playbook-run when:**
- A playbook has been authorized to execute
- Work spanning multiple sessions needs state persistence
- A human or agent needs to resume an in-progress process

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `playbook` | UID | The playbook definition this run executes. Must exist in ledger. |
| `playbook_version` | string | Version pinned at run start. Executor MUST use this version — not the current version. Version mismatch = indeterminate state. |
| `member_of` | array of UIDs | Parent project(s). Must exist in ledger with `type: project`. No orphaned runs. Replaces v1 `project:` field. |
| `binding` | path | Path to the vault binding file: `.tropo-studio/bindings/<slug>.binding.md` |
| `started` | ISO 8601 date | When execution began |
| `executor` | string | Agent ID of the current or last executor |
| `authorized_by` | string | Human or agent ID that authorized this run |

## Required Files

Every run folder must contain these files. Before writing to the folder, read `playbook-runs/AGENTS.md` — it declares the vault-level governance for all run folders.

| File | Frontmatter | Purpose |
|------|-------------|---------|
| `definition.md` | Required — strict YAML per above | Run identity. The capsule entry. |
| `context.md` | None — free-form markdown | Instance specifics — who/what this run is for. Tier 4 binding. Written by the authorizing human or agent at run start. |
| `thread.md` | None — free-form markdown | LLM working memory across sessions. What the next executor needs to *think* to continue. Append-only by convention. |
| `run.jsonl` | N/A | Append-only structured event log. One JSON object per line. Seed with `run_created` event at creation. |
| `run.state.json` | N/A | Typed resumption anchor. Written at every group boundary. NEVER groomed. Gives executor immediate current state without replaying full event log. Schema at [12d8918c](../../../vault/files/12d8918c.md) §3. |
| `artifacts/` | N/A | Directory for files produced by this run. Create empty at run start. |

### run.jsonl Event Schema

Every event is one JSON object per line. Minimum fields:

```json
{"event": "<type>", "timestamp": "YYYY-MM-DDTHH:MM", "step": "<step_id or null>", "detail": "<string>"}
```

**Standard event types:** `run_created`, `step_started`, `step_completed`, `step_failed`, `step_retrying`, `step_dead_letter`, `step_in_doubt`, `step_skipped`, `pause_started`, `pause_resumed`, `milestone_fired`, `call_record`, `verification_receipt`, `compensation_started`, `compensation_step_completed`, `compensation_step_failed`, `archived`

Seed `run.jsonl` at creation:
```json
{"event": "run_created", "timestamp": "YYYY-MM-DDTHH:MM", "step": null, "playbook": "<playbook-uid>", "authorized_by": "<id>", "detail": "Run initialized"}
```

### Vault Resolution

`playbook:`, `member_of:`, and `binding:` fields reference UIDs (Schema v2; v1 `project:` superseded by `member_of:` — see §Change Log v2.0). Resolve them against `vault/00-index.jsonl` at vault root — each line is a JSON object with a `uid` field.

## State Machine

```
active → paused → active (resume after pause)
active → complete (all required outcomes verified)
active → failed (unrecoverable error, explicit declaration)
paused → complete (rare — verify carefully)
complete → archived
failed → archived
any → archived (with explicit reason in run.jsonl)
```

## Archival Trigger

A stateless agent can determine archival eligibility without asking:

1. **Manual:** Authorizing executive (`authorized_by`) may archive any `complete` or `failed` run at any time.
2. **Automatic:** vault-janitor archives runs in `complete` or `failed` state for 90+ days without activity.
3. **Immediate:** Any state → `archived` valid with `event: archived, reason: <string>` written to `run.jsonl` first.

## Execution Routing

Any agent that encounters a run in `active` or `paused` state is authorized and expected to dispatch the executor:

```
Executor: agents/operations/playbook-executor/activate.md
Spawn with: "Run UID: <run_uid> | Vault root: <path>"
```

The executor reads definition.md, loads the pinned playbook version, reconstructs state from run.state.json + run.jsonl, and continues execution. It does not need additional instruction.

A paused run that no agent resumes is a broken process. The governance layer carries the routing. Any agent reading this capsule knows what to do.

## Governance Rules

1. Every run has at least one parent project — the `member_of:` array MUST resolve and be non-empty (Schema v2; replaces legacy v1 `project:` field — see §Validation Rule 1 + §Change Log v2.0).
2. `playbook_version` is immutable after run creation. The version the run started with is the version it finishes with.
3. `run.jsonl`, `thread.md`, and `run.state.json` are append-only or overwrite-at-boundary conventions. Do not edit prior run.jsonl entries.
4. Only the current `executor` or the `authorized_by` principal may transition run state.
5. Archived runs are read-only.

## Run Folder Naming

```
playbook-runs/<playbook-slug>-<run-uid>-<YYYY-MM-DD>/
```

Example: `playbook-runs/new-hire-onboarding-a3f2b1c4-2026-04-14/`

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you activate a playbook-run.*

**Tools available:**
- `ls playbook-runs/` — survey live + archived runs at vault root
- `vault/00-index.jsonl` — grep `type: playbook-run` for the run inventory
- `cat playbook-runs/<slug>/run.jsonl | jq -r '.event'` — replay event sequence; reconstruct executor state without reading thread
- `cat playbook-runs/<slug>/run.state.json` — typed resumption anchor; immediate current state per run boundary
- [Playbook Specification v2.2 (e6d373bc)](../../vault/files/e6d373bc.md) §5 — run folder, thread.md, verification receipts, portability rules
- Reference instances: live `playbook-runs/agent-activation-argus-a34-2026-04-25/` (latest activation run) and the catalog of `agent-activation-argus-a*` folders at vault root

**Skills:**
- `activate-playbook-run.skill.md` *(forthcoming v1.5)* — scaffold run folder + seed `definition.md` / `context.md` / `thread.md` / `run.jsonl` / `run.state.json` / `artifacts/` from a playbook UID + project parent
- `archive-playbook-run.skill.md` *(forthcoming v1.5)* — write `event: archived` line to `run.jsonl`, flip `state: archived`, emit closing receipt

**Procedures:**
- **Activate a run** — capture authorization + author the run folder; pin `playbook_version:` at run-start (immutable per Rule 2); seed `run.jsonl` with `run_created` event; set `state: active` + `executor:` in `definition.md`
- **Advance the run** — append `step_started` / `step_completed` (or `step_failed`) events to `run.jsonl` at every group/step boundary; update `run.state.json` at the boundary (overwrite-at-boundary, never groomed); write to `thread.md` with the next executor's working memory
- **Verify a step** — append `verification_receipt` event per Playbook Spec v2.2 §5 receipt schema; never edit prior receipts (Rule 3 append-only)
- **Pause / resume** — write `pause_started` event, flip `state: paused`; on resume, write `pause_resumed`, flip back to `active`. Same UID, same folder, same `playbook_version:`.
- **Archive on completion** — once all REQUIRED outcomes verified: write `archived` event with reason; flip `state: archived`; archived runs are read-only (Rule 5)
- **Compose with the definition** — the run pins the definition's UID + version; the definition lives in `.tropo/playbooks/<slug>.playbook.md` governed by [playbook.capsule v2.1 (e7b3c509)](playbook.capsule.md); editing the definition mid-run does NOT affect this run's pinned version
- **Supersession discipline** — runs are NEVER superseded — they are completed, failed, or archived. Supersession is a definition-level concept, not an instance-level one.

**Rules (at-a-glance):**
1. **One parent project** — `member_of:` MUST resolve and be non-empty; no orphaned runs
2. **`playbook_version:` is immutable** — pinned at run-start, frozen for the run's life
3. **Append-only or overwrite-at-boundary** — `run.jsonl` and `thread.md` append; `run.state.json` overwrites at every group boundary; never groom
4. **State transitions restricted** — only the current `executor:` or the `authorized_by:` principal may transition run state
5. **Archived = read-only** — once `state: archived`, no further writes
6. **Six required files in every run folder** — `definition.md`, `context.md`, `thread.md`, `run.jsonl`, `run.state.json`, `artifacts/`

**Pitfalls:**
- **Authoring a run with `playbook_version:` set to "latest" or unspecified** — Rule 2 violation; pin a concrete semver at run-start
- **Editing prior `run.jsonl` entries** — Rule 3 violation; append a correction event instead of rewriting history
- **Missing `member_of:`** — Rule 1 violation; orphaned runs cannot be project-scoped or surfaced on Drop boards
- **Unauthorized state transitions** — anyone other than `executor:` or `authorized_by:` flipping `state:` is a Rule 4 violation; route through the authorized principal
- **Editing an archived run** — Rule 5 violation; create a new run if the work needs to continue
- **Run folder missing `run.state.json`** — executor cannot resume without replaying the full `run.jsonl`; the state file IS the resumption anchor
- **Vault-specific UIDs / paths in the playbook body that the run inherits** — playbook portability rule (Spec v2.2 §4) violation surfaces in the run; runs should resolve vault-specific refs through the binding layer

**Worked examples:**
- Live run folders at vault root `playbook-runs/agent-activation-argus-a34-2026-04-25/` and predecessors (`agent-activation-argus-a33-2026-04-24/`, `agent-activation-argus-a32-2026-04-21/`, etc.) — canonical activation runs demonstrating the full file complement
- [agent-activation.playbook.md (99341618)](../playbooks/agent-activation.playbook.md) — the definition every `agent-activation-argus-a*` run pins
- [tropo-work-pipeline.pipeline.md](../playbooks/pipelines/tropo-work-pipeline.pipeline.md) + corresponding pipeline-run instances — composability with the pipeline-run sibling

**Go next:**
- Definition capsule (upstream) → [playbook.capsule v2.1 (e7b3c509)](playbook.capsule.md) — what the run instantiates
- Sibling instance capsule → [pipeline-run.capsule v1.0 (5a8f3b2c)](pipeline-run.capsule.md) — same pattern at pipeline scope
- Authoritative orchestration spec → [Playbook Specification v2.2 (e6d373bc)](../../vault/files/e6d373bc.md) §5 — run folder schema, receipt format, portability
- Vault root `playbook-runs/AGENTS.md` — the folder-level governance for run authoring
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-04-14 | Initial version. Capsule type + governance model for playbook run folders. Implements Playbook Specification v2.2 §5. | argus-a23 |
| 2.0 | 2026-04-16 | Schema v2 alignment. `member_of:` array replaces v1 `project:` field; `run.state.json` typed resumption anchor added; `run.jsonl` event schema enumerated. | argus |
| 2.1 | 2026-04-25 | **Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop).** Added §Workshop — Shop Signage section (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next) per the v3 capsule shop-signage pattern. Added Relations Header right after H1 — clickable navigation surface mirroring frontmatter (governed_by, aligned_with, composes_with, sibling instance, pattern precedent). Frontmatter relations enriched: `aligned_with: e7b3c509` + `composes_with: e7b3c509` + `pattern_exemplar: 5a8f3b2c` declared. No semantic changes to §Required Frontmatter / §Required Files / §Governance Rules / §State Machine. UID preserved at f2a8c3e1. | argus-a34 |

---

*playbook-run capsule definition | LOCKED v2.1 | Argus A34 | 2026-04-25 (Stream 3 D3.2 — §Studio + Relations Header); v2.0 lock 2026-04-16 by Argus A23 preserved in git history; v1.0 by Argus A23 (April 14, 2026)*
*Implements: Playbook Specification v2.2 [e6d373bc] §5*
*"The definition is the score. The run is the performance. The folder is the recording."*
