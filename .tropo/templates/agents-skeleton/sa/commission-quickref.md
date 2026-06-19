---
uid: 7c933c50
type: quickref
audience: all-executives
created: 2026-04-27
created_by: tropo-os
applies_to: commission-time, boot-time sa.* spawn
extraction_scope: ship
---

# sa.* Commission Quickref

*Hot-path extraction of the 6-step commissioning protocol for spawning any sa.\* (session agent) on a Tropo vault. Read this at commission time. Ships with every Tropo vault.*

---

## What is an sa.* — quick context

An **sa.\*** ("session agent") is a short-lived, scoped specialist that an executive agent spawns to do bounded work in a single session and then terminate. Each sa.\* lives at a conventional path:

- **The agent's boot file:** `agents/sa/sa.<slug>/sa.<slug>.md` — a markdown file declaring the agent's purpose, boot sequence, invocation protocol, output format, constraints, and termination behavior. Conforms to `.tropo/capsules/session-agent.capsule.md`. The spawning agent does NOT write this file at commission time — it must already exist (either pre-shipped with the vault or authored as a one-time agent design exercise).
- **The agent's activation-log folder:** `agents/sa/sa.<slug>/activation-log/` — append-only history of every commissioning. Each commission gets a numbered record file (`001-<spawner>-record.md`, `002-<spawner>-record.md`, ...). The spawning agent creates the next numbered record file at commission time; this is the IPC channel for the run.

**Pre-shipped sa.\* on a fresh Tropo vault:** `sa.cold-boot` (cold-boot testing primitive) at `agents/sa/sa.cold-boot/sa.cold-boot.md`. Other sa.\* are authored on demand using `session-agent.capsule.md` as the contract.

**The 6-step protocol below assumes the target sa.\* boot file already exists.** If it doesn't, the spawner must author it first — that is a separate design activity, not part of commissioning.

---

## The 6-Step Protocol

### Step 1 — Determine the next record number

Read the `activation-log/` folder inside the target sa.\*:

```
agents/sa/sa.<slug>/activation-log/
```

- Empty or missing folder → next number is `001`
- Otherwise → find the highest `NNN` prefix and add 1. Zero-pad to 3 digits: `001`, `002`, ... `009`, `010`, `011`.

### Step 2 — Determine your spawner ID

Your generation identifier in short, unambiguous form. Examples: `argus-a27`, `vela-v30`, `metis-g44`, or `cold-boot` for cross-sa dispatch.

### Step 3 — Create the record file

Create: `agents/sa/sa.<slug>/activation-log/NNN-[spawner-id]-record.md`

Write this header:

```markdown
# sa.<slug> — Activation Record NNN
*Spawned by: [spawner-id] | Date: YYYY-MM-DD*

---

```

### Step 4 — Pick a mode, then spawn

**Two spawn modes. Choose before writing the prompt.**

**MODE A — LIVE-CHANNEL** (default for multi-step or iterative work): the record is a live IPC channel. You can add `[PENDING]` items mid-run, answer `[QUERY]` escalations, and keep the session alive until you explicitly write `[SHUTDOWN]`. Use this when you may need to ask follow-up questions or queue more work after seeing initial results.

**MODE B — BATCH** (for one-shot, well-scoped work): pre-populate the record with `[RESPONSE]` + every `[PENDING]` item BEFORE spawning. The agent reads, executes, writes `[DONE]`, self-terminates. No mid-flight dialogue. Use this when the work is fully known upfront.

#### MODE A spawn prompt template (LIVE-CHANNEL)

```
Read agents/sa/sa.<slug>/sa.<slug>.md and execute your boot sequence.
Vault root: [absolute path].
Your activation record and channel file is:
agents/sa/sa.<slug>/activation-log/NNN-[spawner-id]-record.md

PROTOCOL — LIVE-CHANNEL MODE:
1. Complete boot. Append [QUERY] to the record asking for termination instructions.
2. Re-read the record. Look for [RESPONSE] and [PENDING] items.
3. For each [PENDING]: mark [IN-PROGRESS], execute, write [DONE] or [FAILED]
   with a brief result summary.
4. After each task completion (or if no PENDING items found), wait 15 seconds,
   then re-read the record. Continue the poll-execute-poll loop.
5. Terminate ONLY when you see [SHUTDOWN] in the record. Do not self-terminate.
   Do not terminate on your own judgment, even if the record looks "complete."
6. If you hit judgment calls (ambiguous task, missing context), append [QUERY]
   to the record, skip that task, and continue with the rest.

HARNESS NOTE: in single-turn sub-agent harnesses (Claude Code, similar), your
"turn" stays alive only as long as you are making tool calls. The poll loop
(re-reading the record every ~15s) IS what keeps you alive. If you stop reading
the record, your turn ends and you terminate. So keep polling — that is the
entire session.
```

#### MODE B spawn prompt template (BATCH)

```
Read agents/sa/sa.<slug>/sa.<slug>.md and execute your boot sequence.
Vault root: [absolute path].
Your activation record and channel file is:
agents/sa/sa.<slug>/activation-log/NNN-[spawner-id]-record.md

PROTOCOL — BATCH MODE:
1. Complete boot. Read the record file. It already contains [RESPONSE] and
   all [PENDING] items.
2. Execute each [PENDING] in sequence. Mark [IN-PROGRESS] on pickup. Write
   [DONE] or [FAILED] on completion with a brief result.
3. After all [PENDING] items are processed, write a consolidated final [DONE]
   summary, then append [SHUTDOWN]. Terminate.
4. If you hit a judgment call, append [QUERY] for that task, skip it, and
   continue with the rest. Do not block the batch on one question.
```

### Step 5 — Respond to the termination query (LIVE-CHANNEL mode only)

In MODE A, after the agent boots, it writes `[QUERY]` asking for termination instructions. Append `[RESPONSE]` before it expects to see work:

```
[RESPONSE] Terminate on [SHUTDOWN] only.
```

In MODE B, pre-write the `[RESPONSE]` into the record before spawning:

```
[RESPONSE] Terminate after [DONE]. Batch run.
```

**`[RESPONSE]` semantics (MODE A):**

- **`[RESPONSE]` is REQUIRED** if your spawn prompt does NOT explicitly instruct the polling loop. Without polling instructions, the agent terminates after `[QUERY]` because its single turn ends when it stops making tool calls. The `[RESPONSE]` must be present BEFORE the agent's first poll, which means: write it before spawn, OR write it within ~15 seconds of spawn.
- **`[RESPONSE]` is OPTIONAL** if your spawn prompt DOES explicitly instruct polling — i.e., contains the literal lines (or equivalent): *"After writing [QUERY], re-read the record every 15 seconds. Terminate ONLY on [SHUTDOWN]."* In that case the agent keeps polling indefinitely until `[SHUTDOWN]`, and `[RESPONSE]` is just acknowledgment. Safe default; recommended for keeping the channel open across longer-running interactions.

The MODE A spawn prompt template above (Step 4) DOES contain the explicit polling instruction. If you use that template verbatim, `[RESPONSE]` is acknowledgment-only.

**If you neither include polling instructions in the spawn prompt NOR write `[RESPONSE]` quickly:** the agent terminates after `[QUERY]`. This is the most common first-spawn failure (see §Common Failure Mode below).

### Step 6 — Add work, respond to escalations, shut down

**In LIVE-CHANNEL mode:**

- Append `[PENDING]` items at any time. The agent picks them up on the next ~15s poll.
- If the agent writes `[QUERY]` as an escalation (judgment call it couldn't resolve), append `[RESPONSE]` addressing that specific query. The agent reads both on next poll.
- When you are truly done, append `[SHUTDOWN]`. The agent terminates on its next poll.

**In BATCH mode:** the agent self-terminates after the batch. You don't do anything further except read the final `[DONE]` and carry the results forward.

**The record file is permanent history — do not delete.**

---

## Record File Format

```markdown
# sa.<slug> — Activation Record NNN
*Spawned by: [spawner-id] | Date: YYYY-MM-DD*

---

[QUERY] Boot complete — [domain loaded]. What are my termination instructions?
[RESPONSE] Terminate on [SHUTDOWN] only.        ← spawner writes this

[PENDING] Task description — specific instructions
[IN-PROGRESS] Task description — picked up HH:MM
[DONE] Task description — result summary. Issues: none.
[FAILED] Task description — what went wrong
[SHUTDOWN] — agent terminates on next poll
```

---

## Critical Rules

- **Creating the record file is not the same as commissioning.** The agent is not running until it writes `[QUERY]` to the record (MODE A) or begins picking up `[PENDING]` items (MODE B).
- **The spawn prompt must instruct the polling loop explicitly (MODE A).** Single-turn sub-agent harnesses consider a sub-agent "alive" only while it is making tool calls. Re-reading the record every N seconds is what keeps the turn alive. If the spawn prompt doesn't instruct polling, the agent terminates after its first work cycle.
- **Pre-populate in BATCH mode.** If you want a one-shot batch run, write `[RESPONSE]` + all `[PENDING]` items into the record BEFORE spawning. The agent reads them, works through the list, writes `[DONE]`, shuts down. No dialogue.
- **The record file is permanent history.** Do not delete it.
- **Terminal — one level only.** sa.\* agents cannot spawn sub-agents.
- **No direct human contact.** All output flows through the parent executive (you, the spawner).

---

## Common Failure Mode — and how to avoid it

**Symptom:** You spawn an sa.\* in MODE A. The agent boots, writes `[QUERY]`, then the background-task notification fires saying "agent completed." You didn't get to append `[PENDING]` items before it terminated.

**Cause:** Your spawn prompt said something like "After booting, write [QUERY] and wait for [RESPONSE]." The agent interpreted "wait" literally — it stopped making tool calls. The harness ended its turn. There is no "wait" primitive in a single-turn sub-agent; waiting IS the absence of tool calls, which IS termination.

**Fix:** in MODE A, your spawn prompt must say explicitly: *"After writing [QUERY], re-read the record every 15 seconds. Terminate only on [SHUTDOWN]."* The re-read IS the wait. The polling loop IS the session.

**Alternative fix:** use MODE B — pre-populate the record with `[PENDING]` items before spawning, and instruct the agent to execute and self-terminate after `[DONE]`. No polling needed.

---

*sa.\* Commission Quickref | Tropo-OS shipped primitive*
*"The record file is the IPC channel. The polling loop is the session. The spawn prompt must say so."*
