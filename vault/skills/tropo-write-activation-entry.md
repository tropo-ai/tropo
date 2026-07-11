---
skill: write-activation-entry
name: write-activation-entry
type: how-to
purpose: Canonical write abstraction for activation entries — open at boot, close at retirement / [SHUTDOWN] / stale-sweep, update for status touches
when: At Group 0 Step 0.0b of agent-activation playbook (open) or closure step of agent-retire playbook (close) or sa.* [SHUTDOWN] handler (close) or Vela's Tier 1 stale-sweep (close-stale)
mode: inline
params:
  - op
  - agent
  - generation
  - model
  - platform
  - agent_root
  - agent_class
  - activated_by
  - member_of
  - commissioned_purpose
  - activation_uid
  - target_status
  - closure_reason
  - transfer_uid
  - field
  - value
uid: 7a3d04bc
status: active
owner: argus
author: argus-a58
created: 2026-05-11
created_by: argus-a58
modified: 2026-05-11
modified_by: argus-a58
governed_by: a7c3f489
related_capsule: 4e8b21f0
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: Reach for this whenever any agent boot, retirement, [SHUTDOWN], or stale-sweep needs to write or mutate an activation entry. Three operations — open (new entry at boot); close (terminal status flip with retired_at + closure_reason); update (non-lifecycle field touch). The skill handles entry authoring per activation.capsule v1.0 schema, enforces lock-based parallel-boot safety, validates ADR-016 / ADR-028 substrate invariants before writing, and updates the derived agent-activations.jsonl registry. Replaces V42's write-gen-log-row.skill (c9b3e6f1; retired in this cycle) as the canonical lifecycle write abstraction.
related_thesis: 5591f018
tags:
  - skill
  - how-to
  - activation-lifecycle
  - v1.21.0-stream-2-authored
  - replaces-write-gen-log-row
  - adr-016-substrate
  - adr-028-substrate
subsystem_hub:
  - 99ed55fd
  - 8dd772a0
---

# Write Activation Entry

Canonical write abstraction for activation entries. Use this at every boot, retirement, [SHUTDOWN], or stale-sweep — never inline-write activation entries directly. The skill enforces the [activation.capsule v1.0 (4e8b21f0)](../capsules/activation.capsule.md) schema, validates ADR-016 + ADR-028 substrate invariants, updates the derived JSONL registry, and runs under a file lock to prevent parallel-boot races.

## When to Use

### Op: `open` — at boot (agent-activation Step 0.0b)

Append a new activation entry for your generation. Validator checks ADR-016 (no other entry for this `agent:` at `status: active`) + ADR-028 (your generation = predecessor + 1) BEFORE the write; HALT if either fires.

**Inputs:**
- `op: open`
- `agent` — slug (e.g., `argus`, `vela`, `sa.vault-janitor`)
- `generation` — `<prefix><N>` for executives/directors; `<slug>-<NNN>` for sa.* + worker; spawner-relative for child-agent
- `model` — sleeve identifier
- `platform` — Claude Code / Cowork / Web / Gemini CLI / etc.
- `agent_root` — UID of the Level-1 agent root project
- `agent_class` — executive / director / sa / cosmo / tropo / worker / child-agent
- `activated_by` — parent activation UID OR `"user"` for top-level
- `member_of` — array of UIDs; must include `agent_root`; may include cycle-activation-root UIDs
- `commissioned_purpose` (sa.* only) — one-line prompt gist (≤200 chars)
- `run_folder` (optional) — `playbook-runs/<run>/` pointer

**Output:** new activation entry at `vault/files/<minted-uid>.md` with `status: active`. Returns the minted UID for use in subsequent boot steps.

### Op: `close` — at retirement / [SHUTDOWN] / stale-sweep

Flip status from `active` to a terminal state. Sets `retired_at:` + `closure_reason:`. Optional `transfer_uid:` for executive retirements.

**Inputs:**
- `op: close`
- `activation_uid` — the entry to close
- `target_status` — `retired` / `failed` / `stale` / `paused`
- `closure_reason` — enum from activation.capsule §3 Optional Frontmatter `closure_reason` values
- `transfer_uid` (optional, executives only) — UID of the living transfer authored at retirement

**Validator pre-write checks:** entry exists at the given UID; `status: active` (or `paused` if target is `failed`); for `target_status: stale`, the activation has no `run.jsonl` events for ≥7 days.

**Output:** entry updated in place with `retired_at: <today>` + `status: <target>` + `closure_reason:` + optional `transfer_uid:`. Skill triggers rebuild-vault index refresh to update the derived JSONL.

### Op: `update` — non-lifecycle field touch

Touch a single field without changing `status:`. Used for `session_summary:` updates, `cycles_shipped:` appends, `defects_caught_inline:` increments, etc.

**Inputs:**
- `op: update`
- `activation_uid` — the entry to update
- `field` — field name (must be in activation.capsule §2 Schema; status / agent / activated_at / activated_by are NOT updatable via this op — those are lifecycle-load-bearing)
- `value` — new value (type-checked against schema)

**Validator pre-write checks:** field is in updatable set (not lifecycle-load-bearing); type matches schema constraint.

**Output:** entry updated in place. `modified:` + `modified_by:` updated.

## Lock Pattern — Parallel-Boot Safety

Same lock pattern as V42's write-gen-log-row.skill (c9b3e6f1). Before any write op:

1. Acquire file lock at `.tropo-studio/locks/agent-activation.<agent>.lock` (create if missing, exclusive flag).
2. If lock held: wait up to 30 seconds, then HALT with `parallel-boot-violation` (ADR-016 enforcement at lock-time, not just substrate-time).
3. Execute the op (open / close / update).
4. Release lock.

The substrate-level ADR-016 check (validator Rule 4) catches parallel writes that bypass the lock; the lock-level check catches them at write-time so the second write never lands. Both are belt-and-suspenders.

For `op: open` specifically, the lock acquisition is the moment when the validator pre-checks fire — predecessor's `status` must be terminal AND generation chain must be monotonic. Failure of either check is a HALT with reason logged to the activation's run.jsonl + `channels/ops.md` per ADR-016/028 protocol.

## ADR-016 + ADR-028 Substrate Enforcement

This skill is the gate where ADR-016 (no parallel generation) and ADR-028 (generation = predecessor + 1) substrate enforcement lives. The boot playbook reads the activation registry to verify these conditions; the skill enforces them at write-time.

**ADR-016 check (op: open):** query the activation registry for entries with `agent: <this-agent>` AND `status: active`. If any results, HALT — there's already an active activation for this agent. The new boot must wait for the existing entry to close.

**ADR-028 check (op: open):** parse the latest activation entry for this `agent:` (the predecessor) — compare its `generation:` against the new entry's `generation:`. The new must equal predecessor + 1 (where + 1 is class-specific arithmetic per the generation format declared in activation.capsule §2). Mismatch is a HALT.

Both HALTs are recorded as `failed` activation attempts — the validator writes a `status: failed` entry with `closure_reason: parallel-boot-violation` (ADR-016) or `generation-chain-mismatch` (ADR-028). Honest record, not silent failure.

## Idempotency

Re-running an `op: open` for a generation that already has an active entry is a HALT (per ADR-016). Re-running `op: close` against an already-closed entry is a no-op if the target_status matches the current status; HALT if it would change a terminal status. Re-running `op: update` against an entry with the same value is a no-op.

## Skill Implementation

The skill is documentation; the actual mutation logic is in `vault/tools/40b2f455.py` (companion script authored alongside this skill at v1.21.0 Stream 2). The script:

1. Validates inputs against activation.capsule schema
2. Acquires lock
3. For `open`: runs ADR-016 + ADR-028 substrate checks against the activation registry
4. For `close`: validates current status + target status transition is allowed
5. For `update`: validates the field is in the updatable set
6. Mints UID (for `open`) or loads existing entry (for `close` / `update`)
7. Writes the vault entry at `vault/files/<uid>.md`
8. Triggers rebuild-vault index refresh (or marks for next batch refresh per performance budget)
9. Releases lock
10. Returns the UID + status-transition record

The skill's job is to centralize this logic so every caller (boot playbook, retirement playbook, sa.* [SHUTDOWN] handler, Vela's stale-sweep) writes consistently. Per-caller prose variation was the failure mode that caused 4× drift on the gen-log substrate (V42's substrate elevation precedent); this skill prevents the same drift on the activation registry.

## Composes With

- **[activation.capsule v1.0 (4e8b21f0)](../capsules/activation.capsule.md)** — the typed primitive this skill writes per. Schema + state machine + validation rules.
- **[agent-activation.playbook v2.6 (99341618)](../playbooks/agent-activation.playbook.md)** (v1.21.0 Stream 3 amendment) — calls `op: open` at Group 0 Step 0.0b.
- **[agent-retire.playbook](../playbooks/agent-retire.playbook.md)** (v1.21.0 Stream 3 amendment) — calls `op: close` at closure step.
- **sa.* dispatch protocol** ([agents/sa/.tropo-studio/CAPSULE.md content moved to vault entry](../../vault/files/e863a1e0.md)) — sa.* commission writes `op: open` at dispatch; `[SHUTDOWN]` writes `op: close` at terminate.
- **COS Operational Health Playbook (56af4a40)** — Vela's Tier 1 stale-sweep calls `op: close target_status=stale` for activations idle ≥7 days.
- **rebuild-vault.py** — triggered after each write to refresh the derived `.tropo-studio/registries/agent-activations.jsonl` index.
- **tropo-validate.py** — runs activation-registry invariant checks at vault-rebuild time (v1.21.0 Stream 5 validator extension). The skill's pre-write checks are belt; the validator's substrate-level checks are suspenders.
- **[SELF-HEALING.md (db0fd9b1)](../../vault/files/db0fd9b1.md)** — Path 1/Path 2 discipline applies to skill remediation. Trivial defects fix in place; substantive defects file as tracked work-items.

## Migration from write-gen-log-row.skill

This skill replaces V42's [write-gen-log-row.skill (c9b3e6f1)](write-gen-log-row.skill.md) as the canonical lifecycle write abstraction. The gen-log substrate retires at v1.21.0 Stream 3 — at which point write-gen-log-row.skill flips to `status: archived` and all callers migrate to this skill. Until Stream 3 lands, both skills coexist: gen-log writes still happen via the old skill for boot/retire continuity; activation entry writes happen via this skill.

After Stream 3 lands:
- `write-gen-log-row.skill` archived
- `generation-log.capsule` archived
- `sort-gen-log.py` deleted
- gen-log invariant check in `tropo-validate.py` removed
- All boot + retire + [SHUTDOWN] writes route through this skill

---

*write-activation-entry skill | v1.0 | UID `7a3d04bc` | Authored by Argus A58 2026-05-11 | v1.21.0 Stream 2 — canonical lifecycle write abstraction*
*"One skill, three ops, every activation. ADR-016 and ADR-028 enforced at write-time AND at substrate-time. Drift becomes structurally impossible."*
