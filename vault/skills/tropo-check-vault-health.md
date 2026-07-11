---
skill: check-vault-health
name: check-vault-health
type: how-to
purpose: Read the daily vault health report and summarize blocking issues, staleness, and alerts
when: At boot (Phase 3) or when assessing vault operational state
mode: both
params:
  - health_report_path
uid: 9b1f3e48
status: active
owner: argus
created: 2026-04-15
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: Reach for this at boot during Group 3 (operational grounding) for a fast read of vault health — top-level OK/WARNING/CRITICAL status, blocking issues, agent status-card staleness flags (>48h on active agents), and active alerts. Also use mid-session when assessing operational state without reading every status card and channel individually. Reads shared/orientation/daily-health-report.md (or override path); reports gaps if the report itself is missing or stale.
subsystem_hub:
  - 76bab75f
---

# Check Vault Health

Use this to quickly assess the operational state of the vault without reading every status card and channel individually.

## Steps

1. **Read the health report.** Open `{health_report_path}` (default: `shared/orientation/daily-health-report.md`). If the file doesn't exist or is older than 48 hours, note the gap and skip to Step 4.

2. **Extract key findings:**

 a. **Vault status.** The top-level status: OK, WARNING, or CRITICAL. Note any blocking issues.

 b. **Staleness.** List any agent status cards flagged as stale (typically >48 hours for active agents). Note: agent name, last modified, age.

 c. **Channel health.** List any channels breaching their line ceiling. Note: channel name, current lines, ceiling.

 d. **Unresolved alerts.** List any unacknowledged ACTION items from `channels/alerts.md` referenced in the report. Note: date, source, description, owner.

3. **Assess impact.** For each finding, note whether it affects this agent's work:
 - A stale status card for a counterpart means their state is unknown
 - A channel ceiling breach means archival is overdue
 - An unresolved alert may indicate a systemic issue

4. **Compile the report.** Write a structured summary:
 - **Status** — one line: vault OK/WARNING/CRITICAL + reason
 - **Blocking** — anything that prevents normal operation (usually none)
 - **Staleness** — agents with stale status cards
 - **Alerts** — unresolved items, with owners
 - **Health report age** — when the report was generated (flag if >48h)

## Success

- Health report was read (or gap noted if missing/stale)
- Blocking issues identified (or confirmed none)
- Stale agents and unresolved alerts listed with owners
- Agent knows the vault's operational state before starting work
