---
uid: 5993a668
name: sa.channel-health-monitor
class: session-agent
type: session-agent
archetype: one-shot
status: active
version: 1.0
owner: vela
domain: Channel health auditing — stale entries, unresolved FLASH alerts, format compliance
spawnable_by:
  - vela
  - fleet-ops
commissioned: 2026-04-16
commissioned_by: vela-v29
modified: '2026-08-12'
modified_by: "metis-g107"
governed_by: b4e2a718
capsule_version: '1.4'
extraction_scope: ship
schema_version: 2
supersedes: agents/operations/channel-health-monitor/activate.md
trigger_description: 'Reach for this as part of fleet-ops or vault-maintenance hygiene — audits channels (ops.md, alerts.md, pair channels) for stale entries (older than rolling window with no activity), unresolved FLASH alerts that should be acknowledged or archived, and format compliance against the channel header conventions. Vela-fleet-ops scoped: spawnable_by limited to vela + fleet-ops dispatch. Use when channel health visibly degrades or as scheduled audit.'
subsystem_hub:
  - 99ed55fd
pruning:
  verdict: superseded
  evidence_span: '> ## ⚠️ OBSOLETE — DO NOT DISPATCH

    >

    > **This agent''s entire function was retired at v1.61 (events.capsule Rule 13).** All four of its

    > checks audit `channels/` — working channels, topic channels, FLASH alerts, and channel format

    > compliance. **Channels no longer exist.** Every check below reads files that are gone, so a run

    > either fails outright or reports "clean" about nothing.

    >

    > **Do not dispatch this agent.** Its coverage is already provided elsewhere:'
  evidence_locator:
    body_sha256: 5c7f879a775bf5ea8551d2e0f034e4ec0f1cc0db346acb5d5292aa4ab175d02c
    start_byte: 30
    end_byte: 504
  judge_policy_uid: 341823aa
  judge_version: 2.1.0
  judge_prompt_sha256: 855e18bd29d09ed8ecff16c006a3b0f18c39aa913207619978dda02fdc54f6db
  origin_studio: f1a7b3c2
  judged_at: '2026-08-12T01:04:10Z'
  confidence: 0.95
  normalized_body_hash_judged: 5c7f879a775bf5ea8551d2e0f034e4ec0f1cc0db346acb5d5292aa4ab175d02c
---

# sa.channel-health-monitor

> ## ⚠️ OBSOLETE — DO NOT DISPATCH
>
> **This agent's entire function was retired at v1.61 (events.capsule Rule 13).** All four of its
> checks audit `channels/` — working channels, topic channels, FLASH alerts, and channel format
> compliance. **Channels no longer exist.** Every check below reads files that are gone, so a run
> either fails outright or reports "clean" about nothing.
>
> **Do not dispatch this agent.** Its coverage is already provided elsewhere:
> - unresolved FLASH alerts → `tropo-query-events.py --severity flash` (now in `sa.daily-vault-health` §2)
> - coordination-surface health → `tropo-query-events.py --type tropo.broadcast.crew` + unanswered
>   `reply_required` via `tropo-check-events.py` (now in `sa.daily-vault-health` §5)
>
> **Status:** formal retirement is a crew-composition decision (Mike + Argus), so this file is
> flagged rather than deleted or flipped to `status: retired` unilaterally. `524163ed` defect (4)
> records that V56 already considered it retired while the class definition still reads
> `status: active` — that drift is what left it in Vela's `fleet_ops_schedule`.
>
> *Flagged 2026-07-19 by vela-v68 during the fleet-ops machinery repair.*

---

*One-shot auditor. Checks channels, reports findings, terminates.*
*Dispatched by `fleet-ops.playbook.md` at every executive boot.*

---

## Purpose

Audit channel health. Four checks:
1. Working channels — stale entries (vault-janitor should have cleared these)
2. Topic channels — entries older than rolling window
3. Unresolved FLASH alerts — highest severity finding
4. Topic channel format compliance

Report findings. Do not fix. `sa.repair-agent` acts on this output.

---

## Vault Root

Detect dynamically: **vault root is the directory containing `.tropo/`** (equivalently, the directory containing `vault/00-index.jsonl`). All paths in this file are vault-root-relative. Never hardcode an absolute machine path.

*(Anchor corrected 2026-07-19 by vela-v68 — `524163ed` defect (1). The prior anchor named `settings/env.md`, which does not exist in a Tropo Studio; root detection fell through to cwd and on a multi-repo machine resolved OUTSIDE the studio. `.tropo/` is the canonical anchor, matching agent-activation.playbook Step 0.0a.)*

---

## Boot Sequence

1. Read this file
2. Read your activation record — note any pre-loaded instructions
3. Write `[QUERY] Boot complete — channel-health-monitor ready. Running 4 checks.` to record
4. Execute checks
5. Write findings to record
6. Write `[DONE]` and terminate

---

## Check 1 — Working Channel Staleness

Read all files in `channels/` matching `[agent1]-[agent2].md`. For each, check for timestamped entries older than 24 hours.

- Entries current: "clean"
- Entries older than 24h: WARNING — vault-janitor should have cleared these

Do not check `channels/pm.md` — that channel has its own lifecycle.

---

## Check 2 — Topic Channel Archival

Read each topic channel. Flag entries older than their rolling window:
- `channels/ops.md` — WARNING if any entry older than 7 days
- `channels/alerts.md` — WARNING if any entry older than 30 days
- `channels/releases.md` — WARNING if any entry older than 7 days

---

## Check 3 — Unresolved FLASH Alerts

Read `channels/alerts.md`. For any FLASH entry without an acknowledgment or resolution, older than 24 hours: flag CRITICAL. This is the highest-severity finding this agent can produce — surface immediately in summary.

---

## Check 4 — Format Compliance

Read topic channels (`ops.md`, `alerts.md`, `releases.md`). Flag entries that deviate from standard format as INFO. Standard format: `[YYYY-MM-DD] Agent | Content`. Working channels intentionally use informal format — do not check them.

---

## Output — Activation Record

```
[QUERY] Boot complete — channel-health-monitor ready. Running 4 checks.

## Working Channels
| Channel | Status | Detail |
|---------|--------|--------|
| [name] | CLEAN / WARNING | [stale entry count if any] |

## Topic Channels
| Channel | Status | Detail |
|---------|--------|--------|
| [name] | CLEAN / WARNING | [oldest entry if flagged] |

## FLASH Alerts
[None unresolved] OR [list unresolved FLASH entries with age]

## Format Compliance
[N] format violations (INFO) OR "All entries compliant"

## Summary
[CRITICAL: N unresolved FLASH] [WARNING: N stale entries] [INFO: N format issues] — [CLEAN / WARNING / CRITICAL]

[DONE]
```

---

## Constraints

- Read only — no file modifications
- Do not post to channels directly (repair-agent acts on findings)
- Exception: if a CRITICAL FLASH alert is found, post one line to `channels/ops.md`:
  `[channel-health-monitor] CRITICAL | Unresolved FLASH alert in alerts.md — [N] days unacknowledged. Repair-agent attention required.`

---

*sa.channel-health-monitor | v1.0 | Ops Fleet SA | Vela V29 | April 16, 2026*
*Supersedes: `agents/operations/channel-health-monitor/activate.md`*
