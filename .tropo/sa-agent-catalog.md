---
uid: sa-agent-catalog
name: sa-agent-catalog
type: catalog
kind: sa-agent
generated_at: 2026-06-19
generated_by: generate-capability-catalogs.py (v1.15)
source: agents/sa/*/<name>.md filtered by type:session-agent + extraction_scope:ship
governed_by: b4e2a718   # session-agent.capsule v1.4
extraction_scope: ship
---

# Tropo sa.* Agent Catalog

*Auto-generated 2026-06-19 from `agents/sa/<name>/<name>.md` activation files with `type: session-agent` + `extraction_scope: ship`. Sa.\* agents are SEMI-AUTONOMOUS (own context + judgment + [QUERY] mid-execution capacity) — a category boundary, not a flavor variation. Plus dual-purpose: real fleet-ops work AND living-example pattern library for users authoring their own. The user-facing 'sa-agent' filename mirrors Claude Code's tool-catalog pattern; underlying schema type is `session-agent`. Hand-authored content lives in each activation file's `trigger_description:` field.*

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

**15 session agents** registered in this Studio.

---

## sa.board-agent

**Domain.** Per-agent backlog board rendering at boot — queries vault/00-index.jsonl with executive-declared filter, computes five lenses (by-type, by-project, oldest-15, newest-10, drift-signals), returns compact headline + writes ephemeral workspace file. Substrate-discipline-becomes-structurally-enforced at activation.

**Archetype.** `dialogue-capable`

**Spawnable by.** all-executives

**When to reach for it.** Per-agent backlog board rendering at activation Group 4.

**Activation file.** [agents/sa/sa.board-agent/sa.board-agent.md](../agents/sa/sa.board-agent/sa.board-agent.md)

**UID.** `281a79db` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.channel-health-monitor

**Domain.** Channel health auditing — stale entries, unresolved FLASH alerts, format compliance

**Archetype.** `one-shot`

**Spawnable by.** [vela, fleet-ops]

**When to reach for it.** Reach for this as part of fleet-ops or vault-maintenance hygiene — audits channels (ops.md, alerts.md, pair channels) for stale entries (older than rolling window with no activity), unresolved FLASH alerts that should be acknowledged or archived, and format compliance against the channel header conventions. Vela-fleet-ops scoped: spawnable_by limited to vela + fleet-ops dispatch. Use when channel health visibly degrades or as scheduled audit.

**Activation file.** [agents/sa/sa.channel-health-monitor/sa.channel-health-monitor.md](../agents/sa/sa.channel-health-monitor/sa.channel-health-monitor.md)

**UID.** `5993a668` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.cold-boot

**Domain.** Cold-boot testing — validates that vault artifacts are self-sufficient from cold context

**Archetype.** `one-shot`

**Spawnable by.** all-executives

**When to reach for it.** Reach for this when you need to verify a vault artifact (capsule, action, AGENTS.md, playbook, activation file, capability registration) is self-sufficient from cold context — i.e., a stranger with no prior knowledge could read it and do the right thing. The agent reads ONLY the specified target files and attempts to execute or evaluate from that naive context; every off-target read is a finding, every ambiguity is a gap. Substrate-introducing cycles (v1.5/v1.8/v1.9.2/v1.15-class) want sa.cold-boot dispatch as Round 1 of three-instrument verification before lock.

**Activation file.** [agents/sa/sa.cold-boot/sa.cold-boot.md](../agents/sa/sa.cold-boot/sa.cold-boot.md)

**UID.** `3d9f1a7c` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.daily-vault-health

**Domain.** Daily vault health report — crew orientation briefing written to shared/orientation/

**Archetype.** `one-shot`

**Spawnable by.** [vela, fleet-ops]

**When to reach for it.** Reach for this once per local-vault day to produce the daily vault health report at shared/orientation/daily-health-report.md — the crew orientation briefing every executive reads at boot via check-vault-health.skill. Writes top-level OK/WARNING/CRITICAL status, blocking issues, agent staleness flags, channel health, fleet-ops dispatch state. Vela-fleet-ops scoped: spawnable_by limited to vela + fleet-ops; typically dispatched by the fleet-ops registry as a scheduled run.

**Activation file.** [agents/sa/sa.daily-vault-health/sa.daily-vault-health.md](../agents/sa/sa.daily-vault-health/sa.daily-vault-health.md)

**UID.** `eaf9302a` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.first-use-walker

**Domain.** First-use walk testing — measures stranger-encounter of shipped capabilities, not artifact-correctness

**Archetype.** `one-shot`

**Spawnable by.** metis

**When to reach for it.** Reach for this at v1.4+ ship gates to verify a shipped release passes the First-Use Walk — does a stranger downloading the zip encounter the new capabilities in their first 10 minutes via the product surface (foreman concierge → playbooks → first-agent flow), not via grep/ls/exploration. Distinct from artifact-correctness verification (cold-boot tests prove that); this proves stranger-encounter. Per Mike pin 2026-04-23: 'invisible value is zero value.' Spawnable only by metis (independence requirement per fb925dea).

**Activation file.** [agents/sa/sa.first-use-walker/sa.first-use-walker.md](../agents/sa/sa.first-use-walker/sa.first-use-walker.md)

**UID.** `6742f183` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.freshness-monitor

**Domain.** Status card staleness, crew brief consistency checks

**Archetype.** `one-shot`

**Spawnable by.** [vela, fleet-ops]

**When to reach for it.** Reach for this as part of fleet-ops or vault-maintenance hygiene — flags stale agent status cards (>48h on active agents) and crew brief inconsistencies (references to versions/cycles that don't match shipped state). Useful when the Studio has been quiet for a stretch and you want to know what aged. Vela-fleet-ops scoped: spawnable_by limited to vela + fleet-ops; typically dispatched by the fleet-ops registry. Pairs with sa.daily-vault-health to produce the morning-briefing.

**Activation file.** [agents/sa/sa.freshness-monitor/sa.freshness-monitor.md](../agents/sa/sa.freshness-monitor/sa.freshness-monitor.md)

**UID.** `7f4d520d` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.governance-validator

**Domain.** ADR consistency, OA vs. practice alignment, schema v2 compliance spot-check

**Archetype.** `one-shot`

**Spawnable by.** [vela, fleet-ops]

**When to reach for it.** Reach for this on weekly cadence (or when something feels off in governance) for a spot-check audit — ADRs internally consistent + still aligned with practice, Operating Agreement vs actual crew behavior, schema v2 compliance across vault entries. Surfaces drift that hasn't risen to the level of a validator-error but is worth attention. Vela-fleet-ops scoped: spawnable_by limited to vela + fleet-ops; scheduled weekly-monday.

**Activation file.** [agents/sa/sa.governance-validator/sa.governance-validator.md](../agents/sa/sa.governance-validator/sa.governance-validator.md)

**UID.** `06104842` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.memory-curator

**Domain.** Memory curation — async index-time ranker for v3 memory substrate. Scores entries, surfaces bounded recommendations, never silently mutates.

**Archetype.** `dialogue-capable`

**Spawnable by.** all-executives

**When to reach for it.** Reach for this when an executive agent needs memory curation — at retirement (compact STM + score updates + recommendations), at boot (additive fold + verification-before-use sweep), or via explicit invocation (mid-session big-fold, multi-generation historical compaction). The agent reads its own domain (memory.capsule + score formula doctrine + the target memory substrate) and produces scored frontmatter + bounded recommendations via live-channel ratification. Per v1.26.0 walk locks: per-spawn ephemeral; one definition per Studio; dispatched parametrically per agent per trigger; suggest-don't-write contract; bounded action set {merge, archive, demote, flag-stale}.

**Activation file.** [agents/sa/sa.memory-curator/sa.memory-curator.md](../agents/sa/sa.memory-curator/sa.memory-curator.md)

**UID.** `50c0bdce` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.reconciler

**Domain.** Sidecar/source/projection reconciliation — keeps the import primitive's substrate self-consistent under user edits, moves, renames, copies, deletions, and new imports

**Archetype.** `one-shot`

**Spawnable by.** all-executives

**When to reach for it.** Reach for this when the import primitive's substrate needs reconciliation — sidecars and source files have drifted, a folder has moved, new files have arrived, hashes have shifted. Two triggering paths converge here: (1) anomaly-driven — every executive boot runs scan-import-state.py; if it spots orphans or unindexed content, executive commissions this agent for the session; (2) time-driven — fleet-ops registers sa.reconciler as a daily job; first executive of day triggers fleet-ops; if >24h since last run, fleet-ops invokes. Plus on-demand for user-invoked operations (\"import folder X\", \"extract folder Y\"). Per-spawn ephemeral; runs the reconcile-imports playbook; produces a structured reconcile-report; terminates with [SHUTDOWN]. Narrow scope: sidecar/source/projection sync only (adjacent reconciliation domains — broken [[uid]] references, member_of inconsistencies, locked-spec drift — live with tropo-validate.py, not here).

**Activation file.** [agents/sa/sa.reconciler/sa.reconciler.md](../agents/sa/sa.reconciler/sa.reconciler.md)

**UID.** `e4af1001` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.release-test-harness

**Domain.** Release verification — executes vault-agnostic test scenarios against a Tropo-OS release build and files test-run records

**Archetype.** `one-shot`

**Spawnable by.** all-executives

**When to reach for it.** Reach for this at release-ship gates to execute vault-agnostic test scenarios against a freshly-built release — concrete user journeys (concierge invocation, agent activation, capability discovery) verified against the extracted release artifact, not the live vault. Files test-run records as governed evidence. Per harness regime locked 2026-04-20: no release ships without passing Release Test Harness run. Pairs with sa.cold-boot (artifact correctness) and sa.first-use-walker (stranger encounter); harness is the exercise-level ceiling.

**Activation file.** [agents/sa/sa.release-test-harness/sa.release-test-harness.md](../agents/sa/sa.release-test-harness/sa.release-test-harness.md)

**UID.** `24b57c2a` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.repair-agent

**Domain.** Apply T1/T2 repairs from auditor findings; escalate T3 to human

**Archetype.** `one-shot`

**Spawnable by.** [vela, fleet-ops]

**When to reach for it.** Reach for this in fleet-ops repair flow — applies low-risk T1 (mechanical) and T2 (judgment-bounded) repairs from auditor findings (sa.vault-integrity-auditor, sa.governance-validator, etc.), escalates T3 (architectural) to human. Vela-fleet-ops scoped: spawnable_by limited to vela + fleet-ops; typically dispatched by the fleet-ops registry following an auditor that surfaced findings. Self-healing vault doctrine in action — auditor finds, repair-agent fixes the bounded class, human handles the unbounded class.

**Activation file.** [agents/sa/sa.repair-agent/sa.repair-agent.md](../agents/sa/sa.repair-agent/sa.repair-agent.md)

**UID.** `cec903e9` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.skeptic

**Domain.** Adversarial design review — devil's advocate, flaw surfacing, edge case interrogation

**Archetype.** `on-demand`

**Spawnable by.** all-executives

**When to reach for it.** Reach for this when you need adversarial pressure-test on a design or spec — devil's advocate, flaw surfacing, edge case interrogation. Useful before locking architectural decisions to surface what enthusiasm is missing, after Argus drafts to find load-bearing-but-fragile assumptions, and as part of three-instrument verification. The skeptic is intentionally adversarial — its job is finding what's wrong, not validating what's right. Pair with sa.research (independent review by reasoning) and sa.cold-boot (stranger-test by naive read).

**Activation file.** [agents/sa/sa.skeptic/sa.skeptic.md](../agents/sa/sa.skeptic/sa.skeptic.md)

**UID.** `24891f65` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.user-error-walker

**Domain.** User-error-resilience testing — measures whether the system gracefully surfaces common new-user mistakes vs silently producing wrong-context behavior

**Archetype.** `one-shot`

**Spawnable by.** [all-executives]

**When to reach for it.** Reach for this at ship gates to verify the system gracefully surfaces common new-user mistakes (typos, wrong-folder writes, missing fields, malformed frontmatter) instead of silently producing wrong-context behavior. Walks a list of mistakes against the vault, reports per-mistake gracefulness verdicts (graceful = error message + recovery hint; ungraceful = silent corruption or unhelpful failure). Walker-family pattern parallel to sa.first-use-walker; dispatched by dispatch-cold-boot.playbook in Skeptic mode. Implements the Strict-vs-Skeptic brief.

**Activation file.** [agents/sa/sa.user-error-walker/sa.user-error-walker.md](../agents/sa/sa.user-error-walker/sa.user-error-walker.md)

**UID.** `3c844ee6` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.vault-integrity-auditor

**Domain.** Vault structural integrity — non-vault structure, index freshness, agent folder compliance

**Archetype.** `one-shot`

**Spawnable by.** [vela, fleet-ops]

**When to reach for it.** Reach for this on weekly cadence (or when something feels structurally off) for vault-wide integrity audit — non-vault structure compliance, index freshness vs. on-disk reality, agent-folder compliance with the agent template. Surfaces structural drift that hasn't yet broken the build but is degrading. Vela-fleet-ops scoped: spawnable_by limited to vela + fleet-ops; scheduled weekly-monday. Findings feed sa.repair-agent for T1/T2 remediation.

**Activation file.** [agents/sa/sa.vault-integrity-auditor/sa.vault-integrity-auditor.md](../agents/sa/sa.vault-integrity-auditor/sa.vault-integrity-auditor.md)

**UID.** `d6e11740` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

## sa.vault-janitor

**Domain.** Channel ceiling enforcement, working channel cleanup, recycle bin report

**Archetype.** `one-shot`

**Spawnable by.** [vela, fleet-ops]

**When to reach for it.** Reach for this on routine cadence (typically daily or when channels visibly grow long) for hygiene work — enforces channel line ceilings (archives older entries when channels approach 75% of ceiling), cleans up stale working channels (24h rolling window), reports recycle bin contents for audit. Vela-fleet-ops scoped: spawnable_by limited to vela + fleet-ops. Posts FLASH/ALERT to channels/alerts.md when ceilings breach. Composes-with maintain-channel.skill for the per-channel archival logic.

**Activation file.** [agents/sa/sa.vault-janitor/sa.vault-janitor.md](../agents/sa/sa.vault-janitor/sa.vault-janitor.md)

**UID.** `5d588cb7` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)

---

*Tropo sa.\* Agent Catalog | Generated 2026-06-19 | v1.15 substrate*
