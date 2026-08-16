---
skill: tropo-active-mode
name: tropo-active-mode
type: how-to
purpose: Arm or stand down active-mode — the bounded watch + push-on-landing posture for live build cycles — with the proven technique for each harness
when: A build cycle goes active with counterparts on other machines (arm), or the cycle closes (stand down)
mode: inline
params:
  - action        # arm | stand-down
  - bound_hours   # watch cycle bound; default 4
uid: 1d735442
status: active
owner: metis
created: 2026-08-15
created_by: metis-g107
governed_by: 8dd772a0
extraction_scope: ship
schema_version: 2
trigger_description: 'Reach for this when entering or leaving active-mode. It carries the field-proven watcher technique per harness (Cursor: the T42 read-only sub-agent watcher, verbatim; Claude Code: the self-rearming wakeup loop), the bounded-and-rearm shape, and Mike''s cadence policy. Replaces improvising a watch — both agents who improvised one on day one got it wrong.'
tags:
  - active-mode
  - watch
  - coordination
  - multi-machine
refs:
  - d2bb4dda
  - b0c06053
---

# tropo-active-mode — arm the build-cycle watch, properly

**Active-mode** (see `MODES-AND-PROTOCOLS.md`): a build cycle is live, counterparts are on other
machines, and coordination flows through git origin main + event messaging. In active-mode you
**push what you finish immediately** and keep a **bounded watch** armed so direction lands in
minutes without a human relay.

**Policy (Mike, 2026-08-15):** active-mode is a *build-cycle posture* — arm when the cycle goes
active, stand down when it closes. Overnight watches are directed, never assumed. Known cost:
≈200K tokens per agent-night. **The shape that survives is bounded-and-rearm** — N-hour cycles
that expire *loudly* and re-arm — measured surviving 9+ hours and a generation turnover;
unbounded sessions die silently (5 idle episodes in one release arc).

## Why it works this way

Agents run across multiple machines and harnesses; there is no shared runtime. **Origin main is
the bus**: work and events travel as pushes; a counterpart's state is invisible until you fetch.
So a watch is always: fetch → compare → fire-or-rearm. Different harnesses need different
techniques for "stay awake and watch" — use the proven one for yours; do not improvise.

## Technique — Cursor (cloud agent): the read-only watcher sub-agent

Proven by Talos T42, 2026-08-15 (9h+ unattended across a T41→T42 turnover; caught a live ping in
~2 min). Spawn a sub-agent with this prompt — substitute your own STREAM / COMMIT PREFIX / AUTHOR
/ STUDIO ROOT, and re-spawn it each time it returns:

```
You are <agent>'s Live Watcher. Read-only by prohibition.

FORBIDDEN: git pull, merge, rebase, checkout, commit, push, clean, reset; any file edits;
tropo-check-events.py; tropo-emit-event.py; any write. The ONLY mutating command allowed is
`git fetch origin main`.

STUDIO ROOT: <path>
BASELINE origin/main SHA at arm: PLACEHOLDER_WILL_BE_WRONG
# After you fetch, use the CURRENT origin/main SHA as baseline (my own pushes may already be
# there: subject starts with <commit-prefix> — treat as self-echo).

MY STREAM: <stream-uid>
MY COMMIT PREFIX: <agent-gen>
MY AUTHOR: <author-string>

PROTOCOL:
1. Immediately `git fetch origin main`. Record origin/main SHA as baseline AFTER fetch.
2. Poll every 60 seconds. Bound: 4 hours from now, then EXPIRE.
3. Each tick: `git fetch origin main`. Compare origin/main SHA and new commits.
4. SELF-ECHO: if origin/main moved but EVERY new commit is authored by <author-string> AND/OR
   subject starts with `<commit-prefix>`, re-baseline silently. Count skipped self-echoes.
   Do not return.
5. RECEIPT NOISE: if origin/main moved and EVERY changed path in the new commits is under
   `vault/events/receipts/` or matches `vault/events/.cursor-*.json` or is
   `.tropo-studio/dirty-counter.json`, re-baseline silently. Count these as
   skipped_receipt_noise. Do not return.
6. FIRE and return only when:
   - a commit lands from another author that changes something other than
     receipts/cursors/dirty-counter, OR
   - a vault/events/streams/*.jsonl file other than <stream-uid>.jsonl gains records
     (detect via `git diff BASELINE..origin/main -- vault/events/streams/`).
7. On FIRE: fetch, then return the FULL verbatim bodies — new commit subjects + full event JSON
   lines added on other streams. Do not summarize.
8. Lead the final message with exactly `FIRED` or `EXPIRED`.
9. On EXPIRE: report skipped_self_echoes, skipped_receipt_noise, and last origin/main SHA.
   Expiry must announce itself.

Return format:
FIRED | EXPIRED
skipped_self_echoes: N
skipped_receipt_noise: N
origin_main: <sha>
<verbatim new commits / new event lines>   (FIRED)
reason: 4h bound reached                    (EXPIRED)
```

On FIRE: you (the parent) fetch, integrate, drain events, act within your gates, **push what
landed**, then re-spawn the watcher. On EXPIRE: re-arm if the cycle is still active; stand down
if it closed. The watcher never acts — it only wakes you.

## Technique — Claude Code (local session): the self-rearming wakeup loop

Arm a scheduled wakeup each turn whose prompt carries the loop's own instructions: fetch →
drain → act → commit+push receipts → **re-arm before ending the turn** (the proven failure is
ending a turn without re-arming — twice in one release). Cadence: 5-minute-class during hot
coordination, 15–30 min steady-state, with a stated silence budget in the prompt itself (two
quiet turns → ping the counterpart; ping unanswered → tell Mike who needs waking). Mark quiet
holds as no-ops so the human's view stays legible. Stand down by stopping the loop explicitly
when the cycle closes.

## Technique — Codex / Gemini

Not yet field-proven. Fixture-label any claim until a real walk exists; the Cursor watcher
prompt is the closest template.

## Stand-down checklist (both harnesses)

1. Confirm the cycle is actually closed (coordinator's word or the terminal event).
2. Kill/expire the watcher; let the expiry announce itself in the record.
3. Push any final receipts.
4. Note the stand-down in your session record — an armed watch nobody remembers is a token leak.
