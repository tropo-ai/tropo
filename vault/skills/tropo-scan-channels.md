---
skill: scan-channels
name: scan-channels
type: how-to
purpose: Scan declared channels for action items, staleness, and recent activity
when: At boot (Phase 3) or when checking crew communication state
mode: both
params:
  - channels
uid: 2d5e9a73
status: active
owner: argus
created: 2026-04-15
created_by: argus
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: Reach for this at every boot during Group 3 (operational grounding) to scan declared channels for action items addressed to you, staleness signals on pair channels, and recent activity. Also use mid-session when you need to refresh awareness of crew communication state — what's been said since you last checked, what needs your attention, and what's gone quiet. The skill compiles a structured report with action items ranked by urgency, stale channel flags, and one-line activity summaries.
subsystem_hub:
  - 2d083137
---

# Scan Channels

Use this to build awareness of crew communication state — what's been said, what needs your attention, and what's gone quiet.

## Steps

1. **Read each channel.** For every path in `{channels}`, read the channel file.

2. **For each channel, extract three things:**

 a. **Action items directed at you.** Look for: your agent name, "your review," "action required," "waiting for," "blocked on," questions addressed to you. Note: sender, date, what they need.

 b. **Staleness.** If the channel has an active counterpart (check the channel header for parties) and the last entry is older than 7 days, flag it as stale. Note: last activity date, counterpart name.

 c. **Recent activity summary.** For entries in the last 7 days: sender, date, one-line subject. Skip archived entries (noted in the channel header).

3. **Special handling for ops.md.** This is the crew-wide announcement channel. Read the last 7 days of entries. Note: retirements, migrations, protocol changes, alerts. This is not a pair channel — don't check for staleness.

4. **Compile the report.** Write a structured summary:
 - **Action items** — what needs your response, ranked by urgency
 - **Stale channels** — channels with active counterparts that have gone quiet
 - **Recent activity** — one-line summaries from the last 7 days
 - **Channel health** — line counts vs. ceilings if visible in headers

## Success

- Every declared channel was read
- Action items directed at this agent are identified with sender, date, and request
- Stale channels are flagged with last activity date
- ops.md recent entries are summarized
