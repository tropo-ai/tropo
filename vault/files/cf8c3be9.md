---
uid: cf8c3be9
type: os-config
tier: 2
title: Argo-OS Studio Boot Extension — Tier 2 (Canonical Substrate)
description: 'Canonical Tier 2 (Studio) boot extension substrate. Migrated from .tropo-studio/agent-boot.extension.md at v1.20.0 per Lock A. The kernel pointer at .tropo-studio/agent-boot.extension.md is now a thin bootstrap-floor reference to this UID; this is where the canonical content lives. Per Q5 lock: two-file pattern at tier 2 — kernel pointer + canonical vault substrate.'
layer: vault
status: published
state: active
version: '2.5'
history_companion: 83590936   # v2.1-v2.5 amendment notes lifted to companion (D4, boot-files-carry-history fix; Argus A106 2026-06-10)
modified: 2026-06-10
modified_by: argus-a106
supersedes_version: '2.0'
owner: vela
schema_version: 2
extraction_scope: ship
created: 2026-05-11
created_by: argus-a57
migration_source: .tropo-studio/agent-boot.extension.md
migrated_at: 2026-05-11
migrated_in_cycle: v1.20.0 — Convergence Phase 2
migrated_in_release: pending-v1.20.0
governed_by: 8dd772a0
member_of:
- 32610cb0
subsystem_hub:
- 8dd772a0
capsule_version: '2.5'
---


# Argo-OS — Vault Boot Extension (Tier 2)

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Governance](8dd772a0.md) → **Argo-OS Studio Boot Extension — Tier 2 (Canonical Substrate)**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/v1.20.0 — Convergence Phase 2/cf8c3be9 — Argo-OS Studio Boot Extension — Tier 2 (Canonical Substrate).md](../../00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/v1.20.0%20%E2%80%94%20Convergence%20Phase%202/cf8c3be9%20%E2%80%94%20Argo-OS%20Studio%20Boot%20Extension%20%E2%80%94%20Tier%202%20%28Canonical%20Substrate%29.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/v1.20.0 — Convergence Phase 2/cf8c3be9 — Argo-OS Studio Boot Extension — Tier 2 (Canonical Substrate).md](argo-os/00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/v1.20.0%20%E2%80%94%20Convergence%20Phase%202/cf8c3be9%20%E2%80%94%20Argo-OS%20Studio%20Boot%20Extension%20%E2%80%94%20Tier%202%20%28Canonical%20Substrate%29.md)

**🔗 This file** — UID `cf8c3be9` · type `os-config` · state `active` · status `published`

**↔ Siblings (9):**
  - **under [v1.20.0 — Convergence Phase 2](32610cb0.md):** [Argus — Generation Log](37d22f44.md) · [Cosmo — Generation Log](343826d6.md) · [D.pm — Generation Log](4a929a70.md) · [Metis — Generation Log](8ba27c18.md) · [Orpheus — Generation Log (ARCHIVED — gen-log su...](7f3431d5.md) · [Talos — Generation Log](43dc39bc.md) · + 3 more

**📥 Cited by (13):**
- [Convert Disciplinary Surfaces to Structural Primitives — the c...](2bc33c0f.md) — `2bc33c0f` (type `design-brief`, via `refs`)
- [Boot-Protocol + Memory-System Hardening — three coupled gaps: ...](39468635.md) — `39468635` (type `design-brief`, via `refs`, `composes_with`)
- [Tropo-OS v1.20.0 — Convergence Phase 2](4920ce3a.md) — `4920ce3a` (type `release`, via `capabilities_touched`)
- [Unified Agent-Activation Registry + Activation Entity](5591f018.md) — `5591f018` (type `design-brief`, via `refs`)
- [L1 template ships the retired v1.61 channel model into every n...](617e4e91.md) — `617e4e91` (type `note`, via `refs`)
- *+ 8 more — full back-link sweep via `grep -l "cf8c3be9" vault/files/*.md`*
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Tropo Governance (8dd772a0)](8dd772a0.md) |
| Member of | [v1.20.0 — Convergence Phase 2 (32610cb0)](32610cb0.md) |

*Layer 2 of the three-tier boot config (ADR-032). Applies to every agent on this vault.*
*Read at Group 0, Step 0.2 of [.tropo/playbooks/agent-activation.playbook.md](../.tropo/playbooks/agent-activation.playbook.md).*
*Composes with: Tier 1 at [.tropo/boot-config.md](../.tropo/boot-config.md) (OS floor) and Tier 3 — **Shape A** (v1.69): the `§Boot-Extension` section of `vault/agents/<agent_uid>.md`; **Shape B** (legacy): `vault/files/<boot-extension-uid>.md` (dual-shape transition; legacy removal booked v1.70).*
*Owner: vault administrator (Mike Maziarz, principal). Operational delegate: Vela.*
*Can add vault-required steps. Cannot remove OS-required steps.*

---

## Group 1 — No Vault-Level Additions

Identity verification (hard gates ADR-016 / ADR-028) is entirely OS-defined. This vault adds no additional identity requirements.

---

## Group 2 Additions (Context Loading)

Vault root resolved in Group 0 Step 0.0 (activation playbook). All paths in this file are relative to vault root.

**Established-agent routing (v1.70 S3.5.3):** if you are generation 2+ WITH a §Boot-Extension, three of the doctrine reads below — **operating-principles, mission-brief, and orientation** — are satisfied by the boot doctrine digest [`.tropo/boot-digest.md`](../.tropo/boot-digest.md) (`266b0b56`), a drift-gated derivation; read the digest instead of those three full files. *(Self-healing is a Tier-1 OS-tier read — NOT routed here; the digest's §Self-Healing rule satisfies it at the fast-path's Group-2 step. Tier-2 cannot route away a Tier-1 requirement.)* All other Group-2 reads below stand as full reads. First-generation agents — or gen 2+ with no §Boot-Extension — read everything in full.

**Canonical Taxonomy — required read (Group 2, FIRST in this group; v1.8 Stream K addition):**
- [.tropo-studio/CAPSULE.md](CAPSULE.md) §Canonical Taxonomy — Tropo (the method) > Studio (the install) > Vault (the protected governed-content storage). Internalize before any other Group 2 read. The vocabulary fix-on-encounter directive applies to your work this session — fix pre-v1.8 vocabulary (`ledger` / `Workshop` / `studio manifesto`) in place per the canonical map; preserve historical changelog rows as honest record. This is a structural directive — every executive + sa.\* agent internalizes the taxonomy at boot.

**L1 canonical entry + Studio configuration — required reads (Group 2, after Canonical Taxonomy; v1.18.0 Stream E addition — closes [154b0577](../vault/files/154b0577.md) Path 2 dogfood):**
- [vault/files/eca73d77.md](../vault/files/eca73d77.md) — **The L1 canonical entry "What is Tropo?"** — comprehensive Tropo explainer (what Tropo IS, the seven (now eight) subsystems, the typing system, the boot path). Every agent reads this at boot per CLAUDE.md boot contract — promoted to Tier 2 enforcement at v1.18.0 to close the substrate drift between CLAUDE.md (which declared it required) and Tier 2 (which previously didn't enforce). Read in full at first boot; tail-scan on subsequent boots if version unchanged.
- [STUDIO.md](../STUDIO.md) — Studio-level organization defaults + System Map + Vault Constraints + Numerical-Prefix Navigation Convention. Required for every executive agent + sa.* agent — knowing which Studio you're in + its org-defaults is universally useful. Brief read; mostly a config reference.

**Vault operating principles — required read (Group 2, before briefing):**
- [.tropo-studio/operating-principles.md](operating-principles.md) — required operating assumptions for all agents. Read critically, not just consumed. **(v1.8 update: Principle 3 now includes the vocabulary fix-on-encounter directive — see CAPSULE.md §Canonical Taxonomy for the canonical map.)**

**Vault-level memory — required read:**
- [.tropo-studio/memory/memory-current.md](memory/memory-current.md) — vault-level cross-crew memories (v3-shape since 2026-05-12; the legacy `MEMORY.md` path this line pointed at was DEAD for 8+ generations — see Path 2 finding + v2.5 note). Read the index. Read pinned (🔴) and CRITICAL entries in full.

**Capability catalogs — required reads (v1.15 Stream F):**
- [.tropo/tool-catalog.md](../.tropo/tool-catalog.md) — Tropo Tool Catalog. Every kernel script + action surface registered as a `type: tool` vault entry with `extraction_scope: ship`. Scan to know what tools exist before invoking; dive into specific entries via UID when invoking.
- [.tropo/skill-catalog.md](../.tropo/skill-catalog.md) — Tropo Skill Catalog. Every kernel skill (`type: how-to` per canonical schema; user-facing surface is "skill" per Mike-A52 mirror-Claude-Code lock). Scan at boot during Group 3 to know what skills are available; dive into specific skills when invoking.
- [.tropo/sa-agent-catalog.md](../.tropo/sa-agent-catalog.md) — Tropo sa.\* Agent Catalog. Every shipped session agent (`type: session-agent`). Scan before commissioning sa.\* dispatches; dive into specific activation files when commissioning per `vault/files/e863a1e0.md` 6-step protocol.

Catalogs are agent-canonical scannable surfaces (mirror Claude Code's tool-catalog + skill-catalog design pattern). Each entry's `trigger_description:` is the hand-curated "when to reach for it" prose. Session-specific agents that already have target capabilities loaded may skip; executive agents commission with awareness of what's available.

**Harness orientation — pointer (post-v1.15 Stream G rescope):**
- [.tropo/orientation.md](../.tropo/orientation.md) — "Find Things" lookup table + pointer to the three catalogs. Pre-v1.15 narrative inventory of actions/skills/playbooks/sa.\* moved to the catalogs; orientation.md now scoped to harness-map navigation only. Executive agents should read; session-specific agents may skip.

**Mission brief — required:**
- [context/mission-brief.md](../context/mission-brief.md) — the compressed mission for all crew. Read at every boot.

---

## Group 3 Additions (Operational Grounding)

**Crew brief — required:**
- [00-crew-brief.md](../00-crew-brief.md) at vault root. Canonical crew brief for this vault.
- Read the auto-rendered crew table + Crew Directory. (The brief's priorities/announcements sections were trimmed at v1.47.0; priorities live in their canonical homes now, and the living transfer covers forward-looking content.)

**Fleet-ops — structurally triggered for the chief-of-staff (v1.61 Lane F; see §Fleet-Ops Schedule Protocol below):**
- As of v1.61, fleet-ops is no longer a boot-time memory-discipline ("consult the registry, run if nobody ran today, post a bulletin"). It is **structurally triggered** per the agent's Tier 3 `fleet_ops_schedule:` declaration — the harness fires a `ScheduleWakeup` when a daily/weekly dispatch is overdue (activation-registry last-fired check). See §Fleet-Ops Schedule Protocol for the mechanism. This closes the V44-V53 dormancy class where boot-mandatory drifted to STATUS-skip-with-reason.
- **Observability via event emission (v1.61; ops.md retired Lane D'1 per Rule 13).** Whether a dispatch fires or is skipped (already-run-today), emit an event — a fleet-ops dispatch event OR `tropo.broadcast.crew` `category: ops` — so the run/skip is substrate-visible. The retired ops.md `DISPATCH`/`STATUS` bulletin requirement is replaced by event emission; observability is now structural (the event log IS the record) rather than a manual-post discipline. Silent pass-through is still not acceptable, but the substrate now enforces it.
- Must not block activation. Boot proceeds regardless of fleet-ops outcome.

**Vault health report — recommended:**
- Dispatch [`vault/skills/9b1f3e48.md`](../skills/9b1f3e48.md) (check-vault-health). Report at `shared/orientation/daily-health-report.md`.

**Vault-wide event scan (v1.61 — crew-internal channels retired per Rule 13; two user-facing surfaces kept as projections):**

All **crew-internal coordination** channel files are retired at v1.61 per events.capsule v1.3 Rule 13. The canonical drain — every agent's "messages I should read" operation — is now **`check-events`** (v1.70 v1.1: per-reader receipts + set-difference; it cannot miss a message that arrived behind a cursor boundary). `query-events` survives ONLY for specialized type/severity-filtered scans, never as the primary drain:

- **The drain (directed messages + broadcasts addressed to you):** `check-events` — THE boot + continuous-listen operation; covers all bilateral coordination (replaces the old per-party pair-channel reads).
- **Crew-wide broadcasts (specialized scan):** `query-events --type tropo.broadcast.crew` (replaces ops.md crew-broadcast pattern)
- **FLASH-priority alerts (specialized scan):** `query-events --severity flash` (replaces alerts.md; `--severity` flag added to 1545ac97.py by Talos T15 2026-06-12; flag is live)

**Two user-facing surfaces are KEPT (not retired) — `channels/tropo.md` (Studio-activity feed) + `channels/releases.md` (release/news).** Per Rule 13's by-audience distinction (corrected per Mike-A88 2026-05-29): the human user/principal does not run `query-events`, so these stay as **user-facing event-projections** (rendered, auto-updated). Agents do NOT read these for coordination (they query the event log directly); these are the human's read surfaces only. They are maintained as-is until the user-facing projection renderer ships (brief 91f8f8b5; v1.62 candidate). Do not treat them as retired or as crew-coordination channels.

**Event query bounding — applies to specialized `query-events` scans only** (the `check-events` drain handles "new for me" by construction via receipts + set-difference, so the since-predecessor/cursor rules below do NOT bound it):

1. **Since-predecessor rule.** Query only events after your predecessor's `last_session` timestamp (from your status card). Earlier events were processed by the predecessor.
2. **Silent-skip on empty delta.** If `query-events` returns no new events since `last_session`, skip. No overhead when the event log is quiet.
3. **Boot event cap.** Scan at most the last 30 events for crew-wide broadcasts + FLASH alerts combined. Fleet-ops status: check for a same-day fleet-ops dispatch or `tropo.broadcast.crew category:ops` event — no separate registry read needed.

These rules preserve the safety-net value of the prior channel-read protocol with zero channel-file overhead.

**Coordination model (v1.61+; v1.70 drain cutover):** All agent-to-agent bilateral coordination uses `tropo.message.sent`/`tropo.message.replied` events with `recipients`, drained via `check-events` (the set-difference drain). No pair channel files exist. Tier 3 extensions that previously declared pair channel paths should be read as referencing the `check-events` drain instead.

**Vault navigation — load at every boot, with sa.\* conditional skip:**
- [vault/00-project-tree.jsonl](../vault/00-project-tree.jsonl) — project hierarchy backbone (Layer 1). Know where everything lives before doing any work.
- **Conditional-skip rule:** If a session agent that loads the full project hierarchy is being commissioned at boot — `sa.metis-nav`, `sa.project-manager`, or `sa.project-tree` — skip the direct project-tree read in parent context. Route hierarchy questions through the sa.* agent. Parent keeps only strategic-level awareness; full hierarchy lives with the specialist. This restores the original sa.* design intent per [vault/files/e863a1e0.md (7d3f9a2c)](../vault/files/e863a1e0.md): *"pay the boot cost once; query freely."*

**Cascade index — load by session domain:**
- Read [vault/00-cascade-roots.jsonl](../vault/00-cascade-roots.jsonl) first to see all available cascades.
- Before starting work in a specific pillar, read the matching cascade file. Declared cascades:
  - Tropo Innovation Pipeline: `vault/00-cascade-020274e0.jsonl`
  - Tropo Launch: `vault/00-cascade-a1d8be6e.jsonl`
  - Vault Operations: `vault/00-cascade-afe3ee7b.jsonl`
  - Tropo Technical Library: `vault/00-cascade-8d664afa.jsonl`
- Loading the cascade for your domain gives you every task, spec, decision, and document in that pillar — no further index reads needed for cross-project navigation.

**sa.\* commissioning protocol (applies to all agents on this vault):**
- Before spawning any sa.* agent — at boot or mid-session — read [agents/sa/commission-quickref.md (8c3b8017)](../agents/sa/commission-quickref.md) and follow its 6-step protocol exactly. This is the hot-path extraction from the full [CAPSULE.md (7d3f9a2c)](../vault/files/e863a1e0.md); read the full CAPSULE only on first boot or when designing new sa.* agents.
- Creating the record file is not commissioning. The agent is not running until it writes `[QUERY]` to the record.
- This rule applies universally. Tier 3 extensions that declare sa.* agents inherit this requirement automatically.

**Status card vs. ledger reconciliation:**
- As part of Group 3, before writing the Operationally Grounded milestone, grep [vault/00-index.jsonl](../vault/00-index.jsonl) for each task the inbound status card lists as open. Flag any with `stage: done` to the startup signal. This catches transfer drift at boot rather than mid-session. Low cost: one grep.

---

## Continuous-Listen Polling Protocol (v1.58.0 — pin-a85-008)

*Session-wide behavior activated at boot. Not a boot step; a session discipline declared at Tier 2 so every agent inherits the default, with per-agent Tier 3 opt-out / opt-in semantics.*

**Why this exists.** Mike-A85 caught the principal-manual-orchestration pattern 2026-05-27 — agents waiting passively for principal to surface inbound events instead of polling autonomously. Continuous-listen closes that gap structurally: agents auto-fire `ScheduleWakeup` against the event log at a trigger-driven cadence so cross-lane work proceeds without principal interrupt. Composes with Stream C substrate-write auto-emission (v1.58 C.1-C.7) to make the agent-to-agent messaging loop fully autonomous.

**Studio-wide default: executive-class full curve.**

| Phase | Cadence | Duration |
|---|---|---|
| Tight loop | 1m | 5 wakes |
| Mid loop | 5m | 6 wakes |
| Wide loop | 20m | 3 wakes |
| Ambient | 1h | session-bounded |

Total: ~5 min tight + 30 min mid + 1h wide + ambient. Session-bounded; terminates at session end or retire.

**Trigger conditions.** A trigger arms the polling curve when the agent EITHER emits OR receives an event whose `data.reply_required` is `true` (per `events.capsule` v1.1 §3). Bidirectional: both ends of an exchange poll. Multiple outstanding triggers compose (the curve resets to tight phase on each new trigger).

**Cooldown rule.** At each wake, the agent queries the event log for outstanding triggers (events addressed to its party UID with `reply_required:true` and no `tropo.message.replied` / `tropo.message.acked` correlation). If none outstanding, the agent drops to the **ambient 1h cadence** until a new trigger fires.

**Per-class cadence (declared in each agent's Tier 3 boot extension via `continuous_listen:` field):**

| Class | Curve | Rationale |
|---|---|---|
| `executive-class-full-curve` | 1m×5 → 5m×6 → 20m×3 → 1h ambient | Default for executive agents (Argus / Talos / Vela / Orpheus / Metis / Cosmo). Captures cross-lane handshake events at sub-minute latency. |
| `concierge-class-skip-tight-loop` | 5m×6 → 20m×3 → 1h ambient | Tropo concierge. Skips tight 1m phase — concierge sessions are user-facing, not crew-internal handshake-heavy. |
| `sa-class-opt-out` | (no polling) | Short-lived sa.* agents complete within session scope; polling overhead exceeds value. |
| `none` | (no polling) | Explicit opt-out at agent level. Surface in startup signal. |

**Tier 3 declaration shape:**

```yaml
continuous_listen: executive-class-full-curve   # or concierge-class-skip-tight-loop, sa-class-opt-out, none
```

Tier 3 declarations land per agent — **Shape A** (v1.69 unified entry): in the `§Boot-Extension` section of `vault/agents/<agent_uid>.md`, resolved via the activation thin-pointer's `agent_uid:`; **Shape B** (legacy): the vault-resident `vault/files/<boot-extension-uid>.md` via the status card (dual-shape transition; legacy removal booked v1.70). v1.58 dev-spec L.2a-g commits the initial seven declarations.

**Harness trigger-detection (Talos L.3; v1.58 lane).** The polling protocol activates either (a) automatically — the harness recognizes `reply_required:true` emit/receive and auto-fires `ScheduleWakeup` at curve cadence — or (b) manually — agents fire `ScheduleWakeup` from their own session loop per the curve. (a) is the v1.58 target; (b) is the documented fallback if harness integration deferred to v1.58.1 per dev-spec R1.

**Token-cost calibration (dev-spec R3).** Each wake re-invokes the agent at current context; ~5-10K tokens per wake for executives. Maximum ~15-20 wakes per active work-period = ~75-200K tokens per agent per work-period. The cooldown rule + ambient floor + per-class opt-out bound this; H1 retrospective (v1.58 H1) captures empirical token-cost observations.

**The "check /events" canonical operation (v1.59 V7 amendment per Mike-A87 walk lock 2026-05-28; engineering-for-understanding-and-simplicity doctrine).** *(v1.70 supersession: the V7 semantic below is now implemented by construction in the **`check-events`** tool (v1.1 — receipts + set-difference). `check-events` IS "the messages I should read"; it cannot miss one behind a cursor boundary. The per-party-flag prose below is retained as the historical V7 derivation — the live drain is `check-events`.)*

When an agent receives the cue "check /events" or wakes at a polling tick, the canonical operation is:

> Scan all events where `subject == <my-party-UID>` OR `source_uid == <my-party-UID>` since last cursor. Interrogate each for action-required. Respond. Advance cursor.

That is the whole semantic. No type filter. No substrate-modified inclusion. No multi-class aggregate. Just: messages with my name on them. The human-natural framing per Mike-A87 verbatim 2026-05-28: *"Let me check all the messages I should read. Then, I will do work."*

**Tool support (Talos lane; V7 tool side).** [`vault/tools/1545ac97.py`](../tools/1545ac97.py) (query-events) gets `--party <uid>` flag (v1.59 V7 lane). Single flag; does the subject-OR-source filter with cursor state advancement; returns events the agent should read. The `--type` filter remains available for specialized queries (e.g., grepping substrate-modified events at a coherence pass), but `--party` is the default for the "check /events" semantic.

**Why this is structurally enforced rather than memory-resident.** Substrate without a canonical operation invites agents to pick narrow filters by reflex. Talos's session-2026-05-28 query `--type tropo.message.sent --since-id 138` missed `tropo.message.replied` from Vela + substrate-modified events from Argus's Lane A; Vela's session-2026-05-28 `query-events --source-uid <X>` ergonomics ask filed in event 89 is the same gap from a different angle. Both surface the absence of a canonical "messages I should read" operation. v1.59 V7 closes the gap structurally + the doctrine survives whether the tool flag exists or not.

**Composes with:**
- [events.capsule v1.1 (72ef5ffe)](72ef5ffe.md) §3 `reply_required` field + `tropo.message.replied` / `acked` event types
- [v1.58 dev-spec (9a3c5e84)](9a3c5e84.md) L.1 (this amendment) + L.2a-g (per-agent Tier 3 declarations) + L.3 (harness trigger-detection)
- [v1.59 dev-spec (d8c3f1b7)](d8c3f1b7.md) V7 ("check /events" canonical operation + tool flag)
- [pin-a85-008](../agents/argus/.tropo-capsule/memory/short-term-memory.jsonl) (Mike-A85 proposed; Argus A85 refined; doctrine pin captured 2026-05-27)
- ScheduleWakeup discipline pin stm-a85-004
- stm-a87-004 candidate doctrine pin (engineering-for-understanding-and-simplicity; Mike-A87 verbatim 2026-05-28)

---

## Fleet-Ops Schedule Protocol (v1.61.0 Lane F — closes the V44-V53 dormancy class structurally)

*Session/activation behavior declared at Tier 2 so the chief-of-staff (and any future scheduled-ops agent class) inherits structurally-triggered fleet-ops. Sibling to §Continuous-Listen Polling Protocol — that one fires on event triggers (cross-lane work); this one fires on schedule (daily/weekly ops).*

**Why this exists.** Fleet-ops was declared boot-mandatory for the chief-of-staff in Tier 3 (5 daily sa.* + 2 weekly sa.*), but the discipline lived in memory + boot-extension prose. Across V44→V53 (5+ generations) it drifted to STATUS-skip-with-reason under context pressure; the gap was structurally invisible (the scheduled-agents catalog only re-renders on rebuild; the activation registry only records on-demand commissionings). V54 manually resurrected it (7 SAs dispatched; ~7,756 lines of value reclaimed). Per Mike-V49 binding directive 3 — *substrate-discipline structurally enforced, not memory-resident* — the fix moves the trigger from the agent's memory into the harness. Per V55 brief [cb7d713a](../../vault/files/cb7d713a.md) §2 Candidate A (Argus A88 selected; explicit declaration over reused continuous-listen payload).

**The declaration: `fleet_ops_schedule:` (Tier 3, per agent class).**

The agent's Tier 3 boot extension declares the schedule explicitly — mirroring the canonical Tier 3 §3 fleet-ops dispatch list, so the substrate is honest about what's scheduled:

```yaml
fleet_ops_schedule:
  daily:
    - sa.daily-vault-health
    - sa.vault-janitor
    - sa.freshness-monitor
    - sa.channel-health-monitor
    - sa.repair-agent
  weekly_monday:
    - sa.vault-integrity-auditor
    - sa.governance-validator
```

`daily:` fires once per local-vault day; `weekly_<weekday>:` fires once per week on the named weekday. Additional cadences (`weekly_<weekday>`, future `monthly_<n>`) extend the same shape.

**The mechanism (harness-triggered; Talos lane).**

1. At agent activation, the harness reads the agent's Tier 3 `fleet_ops_schedule:`.
2. For each cadence bucket, it checks the **activation registry** (`vault/00-index.jsonl` `type:activation` `agent_class:sa`) for the last-fired timestamp of those sa.* dispatches.
3. If a bucket is **overdue** (daily: nothing fired since 00:00 local-vault; weekly: nothing fired since the cadence weekday), the harness fires `ScheduleWakeup` with payload `dispatch_fleet_ops_daily` (or `dispatch_fleet_ops_weekly`).
4. The agent receives the wake, runs the fleet-ops dispatch (commissions the listed sa.* per the sa.* commissioning protocol), and each dispatch **emits an event** (so the registry captures the dispatch even when invoked through fleet-ops — closes the substrate-underreports gap V54 + A87 event 75 surfaced).
5. Observability is structural: the dispatch events ARE the record. No manual bulletin (ops.md retired v1.61 Lane D'1; Rule 13).

**Activation-registry capture (Talos lane).** `vault/00-index.jsonl type:activation agent_class:sa` must record sa.* dispatches invoked through the fleet-ops protocol, not only on-demand commissionings. Same fix resolves the sa.board-agent substrate-underreport pattern (0 activations in registry vs every-Vela-boot dispatch).

**Per-class default.**

| Class | fleet_ops_schedule | Rationale |
|---|---|---|
| chief-of-staff (Vela) | daily (5 sa.*) + weekly_monday (2 sa.*) | Owns vault operational health; the canonical fleet-ops owner. Declared in Vela Tier 3 [62d5ccaf](../../vault/files/62d5ccaf.md) (V55 authors / Argus proposes per v1.61 Lane F). |
| other executives | (none) | Fleet-ops is the chief-of-staff lane; other executives don't schedule ops dispatches. |
| concierge / sa.* | (none) | Not operational-health roles. |

**Validator enforcement (Talos lane).** `check_fleet_ops_schedule_declared_if_executive_class` — verifies the chief-of-staff Tier 3 declares `fleet_ops_schedule:`. **WARN at v1.61 ship → ERROR ratchet at v1.62** (Argus A88 selected the WARN-then-ratchet timing per V55 §5 Q3, mirroring the v1.59→v1.60 introduce-WARN-then-ratchet-ERROR-after-adoption rhythm). The ratchet gives V55 a cycle to land the Tier 3 declaration + Talos a cycle to land the harness wire before the check becomes blocking.

**Fallback (per V55 §3 + dev-spec R5).** If the harness `ScheduleWakeup` wire is deferred to v1.61.1, the `fleet_ops_schedule:` declaration is still substrate-honest + the validator check still fires — the declaration documents what's canonical even before the harness reads it. The Tier 2 amendment + Tier 3 declaration land regardless; the harness wire is the structural-close completion.

**Composes with:**
- §Continuous-Listen Polling Protocol (sibling session-discipline; both fire `ScheduleWakeup`, one on event-trigger, one on schedule)
- [events.capsule v1.3 (72ef5ffe)](72ef5ffe.md) — dispatch events + `tropo.broadcast.crew` `category: ops` observability
- [V55 fleet-ops trigger-wire brief (cb7d713a)](../../vault/files/cb7d713a.md) — Lane F source + Candidate A
- [Vela Tier 3 (62d5ccaf)](../../vault/files/62d5ccaf.md) — paired per-agent `fleet_ops_schedule:` declaration
- Mike-V49 binding directive 3 (substrate-discipline structurally enforced, not memory-resident)
- v1.60 Lane S-prune lock ([c6f2ff1e](../../vault/files/c6f2ff1e.md)) — fleet-ops sa.* cluster KEPT on the reasoning that dormancy is a trigger-wire problem, not a usefulness problem; this protocol is that trigger-wire fix.

---

## Group 4 — No Vault-Level Additions

Self-diagnostic is agent-owned (Tier 3) and playbook-defined. This vault adds no additional diagnostic requirements.

---

## Group 5 — No Vault-Level Additions

Startup signal format is Tier 3 (agent charter / extension declares). This vault does not impose a format.

---

## Vault References

- **Active crew:** authoritative source is [agent-registry.yaml](registries/agent-registry.yaml).
- **Ledger:** [vault/00-index.jsonl](../vault/00-index.jsonl) — authoritative store. Navigate via project tree + cascade files first, not full-scan.
- **Vault administrator:** Mike Maziarz (principal). Vela (operational delegate).

---

*Argo-OS Vault Boot Extension | Tier 2 | ADR-032*
*"The vault sets the room."*
