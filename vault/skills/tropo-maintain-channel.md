---
skill: maintain-channel
name: maintain-channel
type: how-to
purpose: Archive old channel entries to keep channels under their line ceiling
when: When a channel approaches 75% of its line ceiling, or at session retirement
uid: 7f3a9b1c
status: active
owner: vela
created: 2026-04-15
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: Reach for this when a channel file is approaching its line ceiling (75% of 150 working / 200 topic ceiling) or at session retirement as standard hygiene. Identifies the rolling window (24h working / 7d topic) per channel-header type, finds archivable entries (older than window, no unresolved action items, no <24h-old entries), and moves them to archive/channels/<channel>-YYYY-MM.md. Preserves blockers in place; moves resolved/archivable content out. Vela owns this discipline at the vault level via vault-maintenance.playbook.md.
subsystem_hub:
  - 2d083137
---

# Maintain a Channel

Use this when a channel file is growing long. Channels have a line ceiling (default: 150 for working channels, 200 for topic channels). Archive old entries before they breach the ceiling.

## Steps

1. **Count lines.** Check the channel file's line count. If it's under 75% of the ceiling, stop — no maintenance needed.

2. **Identify the rolling window.** Working channels (ephemeral, between two agents) keep a 24-hour rolling window. Topic channels (`ops.md`, `alerts.md`, `releases.md`) keep a 7-day rolling window. Check the channel header for its type.

3. **Identify archivable entries.** Entries older than the rolling window are candidates for archival. Each entry starts with a date in brackets: `[YYYY-MM-DD]`. Entries within the rolling window stay.

4. **Check for blockers.** Do NOT archive an entry if it contains unresolved action items directed at an active agent — look for phrases like "action required," "blocked on," "waiting for," or "your review task." If found, skip that entry and note it in the archival record. Entries less than 24 hours old are never archived regardless of the rolling window.

5. **Create or append to the archive.** The archive file lives at `archive/channels/<channel-name>-YYYY-MM.md`. If it doesn't exist, create it with a header:

 ```markdown
 # Archive: <Channel Name> — <Month Year>

 *Archived from channels/<channel-name>.md per ADR-013. Archived <date> by <agent>.*

 ---
 ```

 Append the archivable entries to the archive file. For long entries, you may condense them — keep the date, author, subject line, and a 1-2 sentence summary. Mark condensed entries with `(condensed)`.

6. **Remove archived entries from the live channel.** Delete the archived entries from the channel file. Add an archival note to the channel header area (below the existing archival notes):

 ```
 *[YYYY-MM-DD] entries (N items) archived YYYY-MM-DD per ADR-013 (CEILING BREACH: N lines, ceiling: N). Archive at archive/channels/<channel-name>-YYYY-MM.md. Archived by <agent>.*
 ```

7. **Verify.** Count lines after archival. The channel should be under the ceiling. If still over, repeat Steps 3-6 for the next oldest entries.

## Safety Rules

- Never archive entries less than 24 hours old.
- Never archive entries with unresolved action items directed at active agents. Flag these and skip.
- Never delete a channel file — only remove individual entries.
- Always write to the archive before removing from the live channel. If the archive write fails, abort.
- Create `archive/channels/` if it doesn't exist.

## When This Skill Is Invoked

- By any agent who notices a channel is long
- By the concierge when it detects a channel over 75% ceiling during boot
- By the channel maintenance grooming agent (when activated)
- At session retirement as part of the vault-janitor sweep

---

*Channel Maintenance Skill v1 | Created by Vela V23, April 7, 2026*
*Protocol source: ADR-013, channels/CURATOR.md, vault-janitor operational knowledge*
