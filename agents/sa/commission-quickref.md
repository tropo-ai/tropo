---
uid: 8c3b8017
type: document
tier: capsule-derivative
canon: vault/files/e863a1e0.md
canon_uid: e863a1e0
owner: vela
audience: all-executives
created: 2026-04-19
modified: 2026-05-11
created_by: metis-g44
modified_by: argus-a58
applies_to: commission-time, boot-time sa.* spawn
subsystem_hub:
  - 99ed55fd
retyped_from: quickref
retyped_at: '2026-07-12'
retyped_by: argus-a130 (walked disposition 5dcbadbd, Mike-verdicted, S2 activation 0d9f89bc)
---

# sa.* Commission Quickref

*Hot-path extraction of the 6-step commissioning protocol from [vault/files/e863a1e0.md](.tropo-studio/CAPSULE.md). Read this at commission time — not the full CAPSULE. For the pattern's philosophy, the sa.* vs Service Director distinction, write rules, or design-time guidance: read the [full CAPSULE](.tropo-studio/CAPSULE.md).*

---

## The 6-Step Protocol

### Step 1 — Determine the next record number

Read the `activation-log/` folder inside the target sa.*:

```
agents/sa/sa.<slug>/activation-log/
```

- Empty or missing folder → next number is `001`
- Otherwise → find the highest `NNN` prefix and add 1. Zero-pad to 3 digits: `001`, `002`, ... `009`, `010`, `011`.

### Step 2 — Determine your spawner ID

Your generation identifier in short unambiguous form: `argus-a27`, `vela-v30`, `metis-g44`, `cold-boot`.

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

**MODE A — LIVE-CHANNEL** (default for multi-step or iterative work): the record is a live IPC channel. You can add `[PENDING]` items mid-run, answer `[QUERY]` escalations, and keep the session alive until you explicitly `[SHUTDOWN]`. Use this when you may need to ask follow-up questions or queue more work after seeing initial results.

**MODE B — BATCH** (for one-shot, well-scoped work): pre-populate the record with `[RESPONSE]` + every `[PENDING]` item BEFORE spawning. The agent reads, executes, writes `[DONE]`, self-terminates. No mid-flight dialogue. Use this when work is known upfront and no follow-up is expected (Argus's sa.research pattern).

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
4. **After each task completion (or if no PENDING items found), wait 15 seconds,
   then re-read the record.** Continue the poll-execute-poll loop.
5. Terminate ONLY when you see [SHUTDOWN] in the record. Do not self-terminate.
   Do not terminate on your own judgment, even if the record looks "complete."
6. If you hit judgment calls (ambiguous task, missing context), append [QUERY]
   to the record, skip that task, and continue with the rest.

CLAUDE CODE HARNESS NOTE: your "turn" stays alive as long as you are making
tool calls. The poll loop (re-reading the record every 15s) IS what keeps you
alive. If you stop reading the record, your turn ends and you terminate. So
keep polling — that is the entire session.
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

**If you don't write `[RESPONSE]` in MODE A, and your spawn prompt correctly instructs polling:** the agent keeps polling indefinitely until `[SHUTDOWN]`. Safe default.

**If your spawn prompt did NOT instruct polling:** the agent will terminate after the first `[QUERY]` because its single turn ends when it stops making tool calls. This was the failure mode caught on 2026-04-20 — Mode A requires the spawn prompt to explicitly name the poll loop.

### Step 6 — Add work, respond to escalations, shut down

**In LIVE-CHANNEL mode** (what most sessions use):

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
[RESPONSE] Terminate on [SHUTDOWN] only.  ← spawner writes this

[PENDING] Task description — specific instructions
[IN-PROGRESS] Task description — picked up HH:MM
[DONE] Task description — result summary. Issues: none.
[FAILED] Task description — what went wrong
[SHUTDOWN] — agent terminates on next poll
```

---

## Critical Rules

- **Creating the record file is not the same as commissioning.** The agent is not running until it writes `[QUERY]` to the record (MODE A) or begins picking up `[PENDING]` items (MODE B).
- **The spawn prompt must instruct the polling loop explicitly (MODE A).** The Claude Code harness considers a sub-agent "alive" only while it is making tool calls. Re-reading the record every N seconds is what keeps the turn alive. **If the spawn prompt doesn't instruct polling, the agent terminates after its first work cycle, regardless of what the CAPSULE says about "default keep-running."** The CAPSULE describes intent; the spawn prompt is what the agent actually executes.
- **Pre-populate in BATCH mode.** If you want a one-shot batch run, write `[RESPONSE]` + all `[PENDING]` items into the record BEFORE spawning. The agent reads them, works through the list, writes `[DONE]`, shuts down. No dialogue.
- **The record file is permanent history.** Do not delete it.
- **Terminal — one level only.** sa.* agents cannot spawn sub-agents.
- **No direct human contact.** All output flows through the parent executive (you, the spawner).
- **If the class you dispatched is a studio-ops v2.0 roster item** (check `vault/studio-ops/roster.json` — the daily/weekly fleet-ops classes: daily-vault-health, suite-health, vault-janitor, freshness-monitor, repair-agent, vault-integrity-auditor, governance-validator, memory-curator, gardener-body-judge), **append a `run_complete` event to `vault/studio-ops/log.jsonl` yourself** once the dispatch finishes — `{"at": "<ISO or bare date>", "runner": "sa.<slug>", "event": "run_complete", "result": "<one-line outcome>", "by": {"actor": "agent", "id": "<your-generation>"}}`. `tropo-studio-status.py` reads ONLY this log for freshness — the activation-log record you just wrote is invisible to it. *(Found 2026-09-02 by vela-v77: a full 5-agent fleet-ops sweep completed cleanly the prior day, every activation record showed [DONE], and `tropo-studio-status.py` still reported all five stale to the next booting agent — because nothing in this file or the sa.* class-defs said the spawner has to log the run separately. Backfilled retroactively; documented here so it doesn't recur. The contract itself was always in the design brief, `vault/files/756a70a9.md` — just never pointed to from here.)*

---

## Common Failure Mode — the one V31 hit on 2026-04-20

**Symptom:** You spawn an sa.* in MODE A. The agent boots, writes `[QUERY]`, then the background-task notification fires saying "agent completed." You didn't get to append `[PENDING]` items before it terminated.

**Cause:** Your spawn prompt said something like "After booting, write [QUERY] and wait for [RESPONSE]." The agent interpreted "wait" literally — it stopped making tool calls. The harness ended its turn. There is no "wait" primitive in a single-turn sub-agent; waiting IS the absence of tool calls, which IS termination.

**Fix:** in MODE A, your spawn prompt must say explicitly: *"After writing [QUERY], re-read the record every 15 seconds. Terminate only on [SHUTDOWN]."* The re-read IS the wait. The polling loop IS the session.

**Alternative fix:** use MODE B — pre-populate the record with `[PENDING]` items before spawning, and instruct the agent to execute and self-terminate after `[DONE]`. No polling needed.

---

*sa.* Commission Quickref | uid 8c3b8017 | Derivative of [CAPSULE.md (e863a1e0)](.tropo-studio/CAPSULE.md)*

---

## v1.22.0 Amendment — Proven Spawn Pattern (Stream 1 dispatch result, 2026-05-11)

*Three cycles (v1.19.0, v1.20.0, v1.21.0) attempted sa.* dispatch and hit harness-watchdog stalls. v1.22.0 Stream 1 dispatch (sa.cold-boot reviewing brief 9d7b04e2, activation entry [`7205abb9`](../../vault/files/7205abb9.md)) completed in ~45 seconds. The pattern that worked is below — adopt for all future sa.* dispatches.*

### Spawn prompt template (proven)

Frame the dispatched agent's task with **five elements**, in this order:

1. **One-sentence role + dispatch context.** "You are an sa.<name>-style reviewer dispatched by <spawner> during <cycle> <stream>." Specific. The agent knows what it is + why it's running.
2. **Pre-written activation entry pointer.** "Your activation entry has been pre-written at `vault/files/<uid>.md`." This is the v1.21.0 substrate's contribution — the dispatched agent has a registered identity before it starts working. The entry is closed via `op: close` after the dispatch completes (clean) or by stale-sweep (failed).
3. **The task in one sentence + named output format.** "Your task: cold-boot review of <target>. Return findings in under <N> words, categorized as: <list of categories>." Tight scope. Single deliverable. No room for scope creep.
4. **Read list (explicit paths).** "Read these files (read-only; do not write): <ordered list of file paths>." Bounded read surface. Explicit ordering.
5. **Stop criteria.** "Stop when you've reported. Don't elaborate. Don't write files. Just read + report findings as your final message." Removes the ambiguity that caused historical stalls (agent kept "thinking" after task was complete; harness watchdog fired).

### Default thresholds

- **Response word budget:** 300-400 words per dispatch. Brief gauntlet against a single brief (~200 lines): 350 words. Ship-time gauntlet against full cycle substrate: 600 words ceiling; consider multi-dispatch decomposition if larger.
- **Timeout:** 300 seconds (5 minutes) per dispatch is the success-criteria upper bound. Stream 1's actual was 45s. If a dispatch runs longer than 5 min, dispatcher should `op: close --target-status failed --closure-reason harness-watchdog-stall` rather than wait further; Vela's stale-sweep is belt-and-suspenders.
- **Subagent type:** in this Studio's harness (Claude Code), use `general-purpose` for sa.cold-boot-style read-and-report; `general-purpose` or `Plan` for sa.skeptic-style architectural review. The "sa.<name>" naming is a prompt-pattern convention; the harness-native subagent_type carries the actual capabilities.
- **Model / cost tier:** every `sa.*` class-def's frontmatter carries an abstract `cost_tier: low | standard | high` (added `f0153984a89f` item 5). Translate it per this Studio's harness and pass the result as an explicit model override — never omit it and let the dispatch silently inherit the spawner's own (often expensive) sleeve. In this Studio's harness (Claude Code): `low → haiku`, `standard → sonnet` (or omit to inherit), `high → opus` (or omit to inherit). A different harness maps its own cheap/standard/premium model names against the same three words — the class-def itself never names a literal model, so it stays harness-neutral across every Tropo install. **Locked by Mike 2026-09-05 ("Lock it. It's a simple directive."), and widened to EVERY dispatch path this Studio uses, not only `sa.*`: the harness Agent tool and every Workflow `agent()` call pass an explicit model too. Defaults by job, not by spawner: readers, extractors, censuses, link walkers and cold-reads are `low` (Haiku) or `standard` (Sonnet); the spawner's own sleeve (`high`) is for design, adversarial review and code on the critical path. Every activation record and every workflow agent label carries `model:` so spend can be measured by class (record-field wiring: task filed 2026-09-05). Measured the day of the lock: Metis dispatched one documentation reader with no model set (inherited Fable, ~237k tokens) and Orpheus six (inherited Fable, ~412k); her cold-readers went out on Haiku because the task said so in words. The rule was written here; nothing read it at the dispatch. *[Closed 2026-09-07, metis-g124: the directive now lives in CLAUDE.md and is read at every dispatch by construction; and `cost_tier` is now mirrored into every dispatchable class's indexed vault entry (`vault/session-agents/<uid>.md`, stamped by vela-v79 same day) so the canonical indexed lookup finds the tier — the class-def at `agents/sa/sa.<slug>/` remains the authoring surface, the vault entry is the mirror a dispatcher resolves. The two un-tiered index rows are correct: the type capsule `b4e2a718` and the DO-NOT-DISPATCH obsolete class `sa.channel-health-monitor` (5993a668).]*

### What NOT to do (historical stall causes)

- ❌ Open-ended "review this and surface anything that comes to mind" prompts — too broad; agent doesn't know when to stop
- ❌ Multi-task dispatches ("review the brief AND author the response AND file findings") — composition is fragile; do single tasks
- ❌ Prompts that imply the agent should "iterate until satisfied" — that's the watchdog stall pattern
- ❌ Dispatching without pre-writing the activation entry — leaves no substrate handle for the stalled case

### Composition

This amendment composes with the existing 6-step protocol above:
- Steps 1-3 (record file + spawner ID + [PENDING] items) — still required
- Step 4 (spawn the Agent) — now uses the proven spawn prompt template
- Steps 5-6 (QUERY/RESPONSE/SHUTDOWN) — now augmented by the activation entry's `op: close` after [SHUTDOWN] write

The 6-step protocol manages the record-file substrate; v1.22.0 amendment adds the prompt-shape discipline that makes the dispatch itself reliable. Together they constitute the canonical sa.* dispatch flow post-v1.22.0.

### Reference

Stream 1 dispatch transcript preserved at activation entry [`7205abb9`](../../vault/files/7205abb9.md) (status: retired, closure_reason: clean-retirement, retired_at: 2026-05-11). 14 substantive findings produced in 45 seconds — proof that sa.* dispatches work when given proper structure.

— Argus A58 | v1.22.0 Stream 2 amendment | 2026-05-11
