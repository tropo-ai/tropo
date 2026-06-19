# Scheduled Agents — Fleet Catalog

*Auto-generated from the activation registry filtered by `agent_class: sa`. Last rendered: 2026-05-11 by argus-a58.*

This catalog answers *"which scheduled session-agents have run recently, and which are stale?"* Per v1.21.0 brief 5591f018 §Substrate Win 2 — the 33-day fleet-dormancy invisibility that founder caught (and no agent caught) closes by construction here: staleness becomes visible the moment a row's last-run drifts.

## In-flight (status: active sa.* dispatches)

*No sa.\* dispatches currently in-flight.*

Per v1.22.0 Stream 3 + activation.capsule v1.0.1: in-flight sa.\* dispatches should complete within 5 minutes. Entries lingering longer than 2 hours are subject to Vela's stale-sweep — flipped to `status: failed` with `closure_reason: harness-watchdog-stall` if confirmed stalled. Per-class stale threshold for sa.\* = 2 hours (vs 7 days for executives).

## Fleet

| Agent | Role | Last Activation | Latest Status | Activation Entry |
|---|---|---|---|---|
| [sa.arch-specs](../00-tropo-nav/agents/sa.arch-specs.md) | Session-agent (arch-specs) | — | no dispatches yet | — |
| [sa.backlog-analyst](../00-tropo-nav/agents/sa.backlog-analyst.md) | Session-agent (backlog-analyst) | — | no dispatches yet | — |
| [sa.channel-health-monitor](../00-tropo-nav/agents/sa.channel-health-monitor.md) | Session-agent (channel-health-monitor) | — | no dispatches yet | — |
| [sa.cold-boot](../00-tropo-nav/agents/sa.cold-boot.md) | Session-agent (cold-boot) | 2026-05-11 | retired | [`7205abb9`](../vault/files/7205abb9.md) |
| [sa.daily-vault-health](../00-tropo-nav/agents/sa.daily-vault-health.md) | Session-agent (daily-vault-health) | — | no dispatches yet | — |
| [sa.first-use-walker](../00-tropo-nav/agents/sa.first-use-walker.md) | Session-agent (first-use-walker) | — | no dispatches yet | — |
| [sa.freshness-monitor](../00-tropo-nav/agents/sa.freshness-monitor.md) | Session-agent (freshness-monitor) | — | no dispatches yet | — |
| [sa.governance-validator](../00-tropo-nav/agents/sa.governance-validator.md) | Session-agent (governance-validator) | — | no dispatches yet | — |
| [sa.hub-groomer](../00-tropo-nav/agents/sa.hub-groomer.md) | Session-agent (hub-groomer) | — | no dispatches yet | — |
| [sa.metis-nav](../00-tropo-nav/agents/sa.metis-nav.md) | Session-agent (metis-nav) | — | no dispatches yet | — |
| [sa.pipeline-walker](../00-tropo-nav/agents/sa.pipeline-walker.md) | Session-agent (pipeline-walker) | — | no dispatches yet | — |
| [sa.project-manager](../00-tropo-nav/agents/sa.project-manager.md) | Session-agent (project-manager) | — | no dispatches yet | — |
| [sa.project-tree](../00-tropo-nav/agents/sa.project-tree.md) | Session-agent (project-tree) | — | no dispatches yet | — |
| [sa.release-test-harness](../00-tropo-nav/agents/sa.release-test-harness.md) | Session-agent (release-test-harness) | — | no dispatches yet | — |
| [sa.repair-agent](../00-tropo-nav/agents/sa.repair-agent.md) | Session-agent (repair-agent) | — | no dispatches yet | — |
| [sa.research](../00-tropo-nav/agents/sa.research.md) | Session-agent (research) | — | no dispatches yet | — |
| [sa.research-and-writing](../00-tropo-nav/agents/sa.research-and-writing.md) | Session-agent (research-and-writing) | — | no dispatches yet | — |
| [sa.skeptic](../00-tropo-nav/agents/sa.skeptic.md) | Session-agent (skeptic) | — | no dispatches yet | — |
| [sa.user-error-walker](../00-tropo-nav/agents/sa.user-error-walker.md) | Session-agent (user-error-walker) | — | no dispatches yet | — |
| [sa.v04-scope](../00-tropo-nav/agents/sa.v04-scope.md) | Session-agent (v04-scope) | — | no dispatches yet | — |
| [sa.vault-index-monitor](../00-tropo-nav/agents/sa.vault-index-monitor.md) | Session-agent (vault-index-monitor) | — | no dispatches yet | — |
| [sa.vault-integrity-auditor](../00-tropo-nav/agents/sa.vault-integrity-auditor.md) | Session-agent (vault-integrity-auditor) | — | no dispatches yet | — |
| [sa.vault-janitor](../00-tropo-nav/agents/sa.vault-janitor.md) | Session-agent (vault-janitor) | — | no dispatches yet | — |
| [sa.vela-test](../00-tropo-nav/agents/sa.vela-test.md) | Session-agent (vela-test) | — | no dispatches yet | — |

## Stale-sweep threshold

Per v1.21.0 walk-lock (follow-up c) — Vela owns Tier 1 stale-sweep at **7-day threshold**: activations with `status: active` AND no `run.jsonl` events for ≥7 days flip to `status: stale` on her next boot. Sweep result surfaces in `channels/ops.md`.

## Substrate references

- **Activation entries:** `vault/files/<uid>.md` per dispatch (canonical source)
- **Registry:** `.tropo-studio/registries/agent-activations.jsonl` (derived; filtered by `agent_class: sa`)
- **Per-agent nav:** `00-tropo-nav/agents/sa.<slug>.md`
- **Stale-sweep ownership:** [COS Operational Health Playbook (56af4a40)](../vault/files/56af4a40.md) Tier 1 cadence

*Fleet catalog | sa.* agents indexed: 24 | Rendering pattern: v1.21.0 Stream 4*
