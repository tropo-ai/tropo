---
uid: sa-agent-catalog
name: sa-agent-catalog
type: catalog
kind: sa-agent
generated_at: 2026-08-14
generated_by: generate-capability-catalogs.py (v1.15)
source: agents/sa/*/<name>.md filtered by type:session-agent + extraction_scope:ship
governed_by: b4e2a718   # session-agent.capsule v1.4
extraction_scope: ship
---

# Tropo sa.* Agent Catalog

*Auto-generated 2026-08-14 from `agents/sa/<name>/<name>.md` activation files with `type: session-agent` + `extraction_scope: ship`. Sa.\* agents are SEMI-AUTONOMOUS (own context + judgment + [QUERY] mid-execution capacity) — a category boundary, not a flavor variation. Plus dual-purpose: real fleet-ops work AND living-example pattern library for users authoring their own. The user-facing 'sa-agent' filename mirrors Claude Code's tool-catalog pattern; underlying schema type is `session-agent`. Hand-authored content lives in each activation file's `trigger_description:` field.*

## How to commission

Sa.\* agents are dispatched, not invoked directly. To commission one: read [`agents/sa/.tropo-studio/CAPSULE.md`](../agents/sa/.tropo-studio/CAPSULE.md) for the canonical 6-step protocol — or the hot-path extraction at [`agents/sa/commission-quickref.md`](../agents/sa/commission-quickref.md) for repeat commissionings within a session. The protocol summary: (1) determine next record number under `agents/sa/<name>/activation-log/`; (2) determine your spawner ID; (3) create the record file with header + `[PENDING]` items; (4) spawn the agent via Task; (5) respond to its `[QUERY]` with `[RESPONSE]`; (6) add work and terminate with `[SHUTDOWN]`.

## Archetypes

- **`one-shot`** — spawn once per task; the agent self-terminates after writing `[DONE]` (or after `[SHUTDOWN]` in live-channel mode).
- **`persistent`** — boot once at the start of a session and stay alive; the spawning agent queries it repeatedly throughout the session before sending `[SHUTDOWN]` at retirement.
- **`on-demand`** — spawn when triggered, may run multiple times in a session; lighter-weight than persistent but reusable.

## Spawnable-by values

- **`all-executives`** — any executive agent (Argus, Vela, Metis, Orpheus, etc.) may dispatch.
- **`[<agent>, fleet-ops]`** — restricted to the named agents plus the fleet-ops dispatcher (a scheduled-dispatch surface that runs sa.\* agents on cadence per the fleet-ops registry).
- **`[<agent>]`** — restricted to the named agent only (typically because the sa.\* serves that agent's workflow specifically, e.g. `sa.metis-nav` is Metis-only).

**3 session agents** registered in this Studio.

---

## sa.channel-health-monitor

**Domain.** Channel health auditing — stale entries, unresolved FLASH alerts, format compliance

**Archetype.** `one-shot`

**Spawnable by.** vela, fleet-ops

**When to reach for it.** 'Reach for this as part of fleet-ops or vault-maintenance hygiene — audits channels (ops.md, alerts.md, pair channels) for stale entries (older than rolling window with no activity), unresolved FLASH alerts that should be acknowledged or archived, and format compliance against the channel header conventions. Vela-fleet-ops scoped: spawnable_by limited to vela + fleet-ops dispatch. Use when channel health visibly degrades or as scheduled audit.'

**Activation file.** [agents/sa/sa.channel-health-monitor/sa.channel-health-monitor.md](../agents/sa/sa.channel-health-monitor/sa.channel-health-monitor.md)

**UID.** `5993a668` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.reconciler

**Domain.** Sidecar/source/projection reconciliation — keeps the import primitive's substrate self-consistent under user edits, moves, renames, copies, deletions, and new imports

**Archetype.** `one-shot`

**Spawnable by.** all-executives

**When to reach for it.** 'Reach for this when the import primitive''s substrate needs reconciliation — sidecars and source files have drifted, a folder has moved, new files have arrived, hashes have shifted. Two triggering paths converge here: (1) anomaly-driven — every executive boot runs scan-import-state.py; if it spots orphans or unindexed content, executive commissions this agent for the session; (2) time-driven — fleet-ops registers sa.reconciler as a daily job; first executive of day triggers fleet-ops; if >24h since last run, fleet-ops invokes. Plus on-demand for user-invoked operations ("import folder X", "extract folder Y"). Per-spawn ephemeral; runs the reconcile-imports playbook; produces a structured reconcile-report; terminates with [SHUTDOWN]. Narrow scope: sidecar/source/projection sync only (adjacent reconciliation domains — broken [[uid]] references, member_of inconsistencies, locked-spec drift — live with tropo-validate.py, not here).'

**Activation file.** [agents/sa/sa.reconciler/sa.reconciler.md](../agents/sa/sa.reconciler/sa.reconciler.md)

**UID.** `3bedf4b2` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.vault-janitor

**Domain.** Channel ceiling enforcement, working channel cleanup, recycle bin report

**Archetype.** `one-shot`

**Spawnable by.** vela, fleet-ops

**When to reach for it.** 'Reach for this on routine cadence (typically daily or when channels visibly grow long) for hygiene work — enforces channel line ceilings (archives older entries when channels approach 75% of ceiling), cleans up stale working channels (24h rolling window), reports recycle bin contents for audit. Vela-fleet-ops scoped: spawnable_by limited to vela + fleet-ops. Emits a tropo.broadcast.crew event (category: ops) when ceilings breach. Composes-with maintain-channel.skill for the per-channel archival logic.'

**Activation file.** [agents/sa/sa.vault-janitor/sa.vault-janitor.md](../agents/sa/sa.vault-janitor/sa.vault-janitor.md)

**UID.** `5d588cb7` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

*Tropo sa.\* Agent Catalog | Generated 2026-08-14 | v1.15 substrate*
