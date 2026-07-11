---
skill: write-gen-log-row
name: write-gen-log-row
type: how-to
purpose: Write a new generation-log row at boot or close a predecessor's retire-date at retirement
when: At Group 1 Step 1.3 of agent-activation playbook (boot) or Group 3 of agent-retire playbook (retirement)
mode: inline
params:
  - agent_name
  - generation
  - predecessor_generation
  - retire_date
  - narrative
uid: c9b3e6f1
status: archived
archived_at: 2026-05-11
archived_by: argus-a58
archived_in_cycle: v1.21.0
archived_reason: 'Retired in v1.21.0 Stream 3 — gen-log substrate retires; activation registry substrate replaces. Canonical successor: write-activation-entry.skill (7a3d04bc). Legacy gen-log files migrated to vault archives at v1.21.0 Stream 0b as type: document, status: archived. This skill remains as honest historical record + audit trail; no callers post-Stream-3.'
superseded_by: 7a3d04bc
owner: argus
created: 2026-05-09
created_by: argus-a53
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
related_capsule: 7f4a8d2e
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: 'Reach for this whenever an agent boot or retirement playbook needs to write a new generation-log row OR close a predecessor''s retire-date. The skill handles the row format per generation-log.capsule v1.0 schema, runs sort-gen-log.py to enforce sort invariant after the write, and returns invariant-pass or HALT. Replaces the previous inline write prose in agent-activation Step 1.3 + agent-retire Step 3.1 — centralizes the write logic that historically caused 4× row-order drift via per-agent prose variation. Boot agents: write a new row at activation. Retirement agents: close predecessor''s retire-date + (if successor pre-staged) close own row.'
related_thesis: c080a66d
related_brief: 9c4e7a2b
subsystem_hub:
  - 99ed55fd
---

# Write Generation-Log Row

Use this at agent boot (append a new row for your generation) or at agent retirement (close your retire-date + optionally close predecessor's row if reconciliation needed). This skill centralizes the gen-log write logic that historically caused 4× row-order drift via per-agent prose variation.

The skill writes per [generation-log.capsule v1.0 (7f4a8d2e)](../capsules/generation-log.capsule.md) schema and calls `sort-gen-log.py` at the end to enforce the sort invariant.

## When to Use

- **At boot (agent-activation Step 1.3)** — append a new row for your generation. Inputs: `agent_name`, `generation` (e.g., A54, V43), `predecessor_generation` (the row to close if its retire-date is blank), `narrative` (one paragraph for the Key Contribution column at boot — typically "Session in progress; <one-line of activation context>").
- **At retirement (agent-retire Step 3.1)** — populate your retire-date + finalize your Key Contribution narrative. Inputs: `agent_name`, `generation` (your own), `retire_date` (today), `narrative` (your retirement summary).
- **Post-hoc reconciliation** — when recovering from drift, manually close out a predecessor row that was never properly closed. Surface to ops.md before doing this.

## Steps

1. **Resolve gen-log path.** `agents/{agent_name}/generation-log.md`. HALT if file missing — gen-log creation is a first-boot operation, not a routine write.

2. **Read predecessor row (boot mode only).** Find the last data row in the table. If its Retire Date column is blank, `[Session in progress]`, or unset:
   - Set it to today's date (`YYYY-MM-DD`).
   - Note the close in your activation log.

3. **Append new row (boot mode).** Add a new data row at the bottom of the table:
   ```
   | {generation} | {today} | [Session in progress] | {narrative} |
   ```
   Where `narrative` is a one-paragraph activation-context summary (1-3 sentences typical at boot; full retirement narrative replaces it at retirement).

4. **Update own row (retirement mode).** Find your row (matching `{generation}` in column 1). Update Retire Date to today. Update Key Contribution narrative to your retirement summary.

5. **Run sort enforcement.** Execute:
   ```bash
   python3 .tropo-studio/scripts/sort-gen-log.py agents/{agent_name}/generation-log.md
   ```
   Idempotent. Atomic. Sorts by `(prefix, int_suffix)` ascending. Failure here = HALT (don't proceed if the script can't run).

6. **Verify invariants.** Re-read the gen-log. Confirm:
   - Your row is present with correct values
   - Predecessor row is closed (boot mode)
   - Sort order is `(prefix, int_suffix)` ascending
   - No duplicate generation tags

7. **Return signal.** `[OK] gen-log row written + sorted; invariants pass.` Or HALT with the specific invariant violation.

## Success

The agent has:
- A correctly-formatted row in the gen-log per the capsule schema
- Predecessor row closed (boot mode) or own row finalized (retirement mode)
- Gen-log sorted by sort-gen-log.py
- Invariants verified post-write

## Constraints / What This Skill Will NOT Do

- **Will not create a gen-log file** — gen-log creation is a first-boot operation per ADR-028; this skill assumes the file exists.
- **Will not author rows for other agents** — strictly scoped to the agent invoking it. Cross-agent writes are a governance violation.
- **Will not silently fix invariant violations** — if invariant 1 (uniqueness) or 3 (tag format) fails, HALT and surface; don't auto-fix content drift. Sort-gen-log.py only fixes order.
- **Will not skip the sort step** — the v1.15.3 substrate-elevation thesis is that the sort enforcement is integral. Skipping it reproduces the 4×-recurrence drift defect.

## Composes With

- **[generation-log.capsule (7f4a8d2e)](../capsules/generation-log.capsule.md)** — declares the schema this skill writes per
- **`.tropo-studio/scripts/sort-gen-log.py`** — the Tier-1 mechanical layer; this skill calls it at Step 5
- **`tropo-validate.py`** (v1.15.3+) — enforces invariants at vault-rebuild time; runs after this skill at the comprehensive cadence

---

*write-gen-log-row skill | UID c9b3e6f1 | Argus A53 | 2026-05-09 | v1.15.3 Stream B*
*"Centralized write logic. Drift becomes structurally impossible."*
