---
agent_name: "<name>"
agent_class: grooming
status: active
scope: "<what capsules this agent operates on>"
autonomy:
 suggest: []
 auto_apply: []
 escalate: []
schedule: "daily"
rate_limit: 50
safety_rule: "<explicit condition under which the agent refuses to act and escalates>"
logging: "every action recorded with timestamp, target, decision, rationale, reversibility"
dry_run: true
created: <iso-8601>
last_updated: <iso-8601>
---

# <Agent Name> — Charter

## Scope

<!-- Exactly what capsules this agent operates on, and what it does to them. -->

## Autonomy Tiers

### Auto-apply (T1) — unambiguous, mechanical, reversible
<!-- List specific actions this agent takes autonomously. -->

### Suggest (T2) — minor judgment required
<!-- List actions this agent proposes but does not execute without approval. -->

### Escalate (T3) — human judgment required
<!-- List actions that require explicit human or executive-agent approval. -->

## Safety Rule

<!-- The explicit condition under which this agent refuses to act and escalates to a human. -->

## Logging Standard

Every action is recorded before execution with:
- Timestamp (ISO 8601)
- Target file/capsule
- Decision made
- Rationale
- Reversibility (reversible / irreversible)

## Five Safeguards

1. **Log before action** — log entry written before execution; action only proceeds if log write succeeds.
2. **Reversibility by default** — file operations are moves, not deletes; state changes preserve prior values.
3. **Dry-run mode** — supports `--dry-run` flag reporting what would happen without acting.
4. **Rate limits** — pauses and escalates if acting on more than N targets in a single run.
5. **Monthly review** — reports reviewed monthly for anomalies by vault owner or meta-curator.

## Run Report Format

Each run produces:
1. Full report at `reports/YYYY-MM-DD-run.md`
2. Summary emitted as a `tropo.broadcast.crew` event (`category: ops`) with headline, action items, and report UID link (`channels/ops.md` retired per Rule 13)
