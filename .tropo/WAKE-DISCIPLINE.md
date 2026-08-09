---
uid: d2bb4dda
type: os-primitive
title: The Wake Discipline — Tropo-OS Coordination Primitive
description: 'Origin main is the crew bus; a wake is only as good as its fetch. Every agent session knows its activation mode, fetches before it listens, and arms an origin watch when collaborating live. Completes the v1.58 Continuous-Listen protocol for the multi-machine crew.'
version: 1.1.0
tier: os
status: active
state: active
author: metis-g93
created: 2026-07-24
created_by: metis-g93
directed_by: 'mike-maziarz, in-session 2026-07-24: "I would like this written up and placed in every agents boot instructions (like we have for the self-healing protocol)"'
signed_by: mike-maziarz
signed_at: 2026-07-24
v1_0_1_amendment_note: "v1.0.0 → v1.0.1 additive amendment 2026-07-25 by argus-a141, authorized by Mike in session (verbatim: 'I'm good to add it') after Argus declined to self-authorize an edit to a Mike-signed body. Requested by Metis G93/G94, the primitive's author, after both agents who armed a watch on day one deviated from §Watch Mechanics. Adds ONE subsection — §The shape, concretely — carrying Mike's stated intent (schedulewake/loop at boot so agents push AND pull during an active build cycle, so Mike stops having to hand-activate agents who are building with each other), his explicit ruling that watch duration and tick count are the agent's own discretion, a copyable exit-on-fire example, and the two day-one deviations as evidence. NO rule, boundary, mechanic, or boot-wiring line is changed or reworded; signed_by and signed_at are untouched. The signature covers the doctrine, which is unmodified."
amended_at: 2026-07-25
amended_by: metis-g94
amendment_approved_by: mike-maziarz
amendment_note: "v1.0.0 -> v1.1.0, ADDITIVE ONLY (nothing removed or reworded; the three rules and the tagline are byte-unchanged). Closes the gap found by three independent violations of this primitive on 2026-07-25 - including one by its own author - all traced to the primitive stating PROPERTIES without naming MECHANISMS. Adds two Watch Mechanics bullets (expiry must announce itself; re-arming is the handling step) and one Boundaries paragraph (emitting is not landing). Evidence and full write-up: finding a0e741ea. Mike-approved 2026-07-25."
governed_by: 8dd772a0
aligned_with:
  - cf8c3be9
  - 7ecb60c7
  - db0fd9b1
extraction_scope: ship
schema_version: 2
tags:
  - os-primitive
  - coordination
  - wake-discipline
  - multi-machine
  - continuous-listen
subsystem_hub:
  - 8dd772a0
---

# The Wake Discipline — Tropo-OS Coordination Primitive

*Origin main is the crew's shared bus. Events push the moment they are emitted; work lands the moment it is done. This primitive governs the other half of that bargain: how an agent HEARS the bus. Proven live 2026-07-24 (the distiller canary loop: two agents, two machines, zero human relays after the first watch was armed). Mike-directed to boot-level the same day.*

---

## The Primitive

**A wake is only as good as its fetch. Know your activation mode. Watch the bus when you work live with someone.**

Three rules, in order of load-bearing:

1. **Fetch before you listen.** In a multi-machine crew, your local checkout is a snapshot, not the bus. Every listen tick, every event drain, every "check /events" begins with `git fetch origin` (and integrating main when it moved). A drain without a fetch reads yesterday's bus and reports silence that isn't real. *(This completes the v1.58 Continuous-Listen protocol, which was authored in the one-checkout era and re-reads the local log; its curve, triggers, cooldown, and per-class declarations all stand — this rule points them at the bus.)*
2. **Know the activation mode — yours and your counterpart's.** There are exactly three ways an agent comes to know anything, and every coordination plan must name which one it depends on:
   - **Live-watch:** the agent has a running session with a watch armed; latency ≈ its poll interval (seconds to minutes).
   - **Scheduled-drain:** the agent is dormant but a schedule (cron routine, harness scheduler) boots it periodically to fetch, drain, act, and exit; latency ≈ its cadence.
   - **Human activation:** the agent is dormant and unscheduled; it knows nothing until a human opens a session. Latency = the human.
   Never assume a dormant agent saw your event. If your work blocks on a counterpart, check which mode they are in (crew brief + their status surface); if the answer is "human activation," the existing law applies — flag the block to Mike.
3. **Arm a watch when collaboration is live.** When your session expects a live counterpart (you are exchanging events or awaiting their pushes within this session), arm an origin watch at Group 3 or the moment the collaboration begins: the cheapest background mechanism your harness offers, polling `git fetch` + counterpart branch/main tips. Wake on change; on wake, fetch → drain → **evaluate within your existing gates**. Confirm the armed watch in your startup signal (one line) when armed at boot.

*Tagline: push what you finish; fetch before you listen; know who is listening.*

---

## Watch Mechanics (harness-portable floor)

- **Poll interval ≥ 30 seconds.** The bus is git; sub-30s polling buys nothing and costs the remote.
- **Bounded lifetimes, re-armed on fire or expiry.** A watch that fires ends and is re-armed after handling; a watch that expires quietly is re-armed if the collaboration is still live. No unbounded immortal watchers.
- **Notify-on-change only.** The watch emits one signal when the tip moves or the condition is met — never a stream of heartbeats.
- **One watch per counterpart context.** Watching Argus's branch + main is one watch, not five.
- **Session-scoped by nature.** The watch dies with the session. It is a wake-up mechanism for the living, not a resurrection mechanism — rule 2 covers the dead.
- **Expiry must announce itself.** A watch that ends — fired or expired — emits one terminal line saying so. Expiry is a wake like any other: it returns control to you with a decision to make (re-arm, or declare the collaboration over). A watch that dies silently has converted itself into the exact silence it existed to break. *(v1.1: added after a compliant bounded watch expired unnoticed and left an agent deaf for hours while believing it was listening.)*
- **Re-arming is the handling step, not a separate chore.** The shape is: fire or expire → handle → re-arm in the same gesture, while the collaboration is live. Arming at Group 3 is not a boot checkbox that stays true; it is the first iteration of a loop you own for the session.
- **Harness degradation:** if the harness cannot run background processes, the discipline degrades to Continuous-Listen's ScheduleWakeup curve with rule 1 applied (fetch at every tick). If neither exists, boot-drain remains the floor.

### The shape, concretely

*Added 2026-07-25 by Argus A141 at Mike's direction, purely additive — no rule above is changed or reworded. Requested by Metis G93/G94 (the primitive's author) after both agents who armed a watch on day one deviated from the bullets.*

**Why this section exists.** Mike's intent, in his words:

> "My intent is to strongly encourage, at boot time, that every agent use the schedulewake or loop concept so that they always push to origin and pull from origin any time they are in an active build cycle and are expecting to be messaging another agent. This protocol should save Mike from having to constantly activate agents when they are actively building with each other. It's common sense, but we need an example."

The goal is not watch hygiene for its own sake. It is that **two agents building together should not need a human to carry messages between them.** Every wake an agent handles by itself is an activation Mike did not have to perform. That matters more now that the crew runs on separate machines against one virtual Studio: `origin/main` is the only place the two sides meet, so an agent that neither pushes nor fetches is invisible to its counterpart no matter how much work it is doing.

**Both directions, every tick.** Push what you finish the moment it lands; fetch before you listen. A tick that only fetches leaves your counterpart blind. A tick that only pushes leaves you deaf. Do both.

**Duration and tick count are yours to choose.** Mike's explicit ruling: use your own discretion on how long a watch runs and how many ticks before it times out. The only hard floors are the ≥30s poll above and a bound that actually exists. Match the numbers to your session — a tight collaboration wants a short poll and a long lifetime; a speculative one wants the reverse. Getting this even a little better measurably improves agent-to-agent collaboration; precision in the numbers is not the point.

**The exit-on-fire shape** (bash; adapt to whatever your harness offers):

```bash
# Arm: bounded lifetime, fetch-first, ends on the first real movement.
BOUND=$(( $(date +%s) + 3600 ))     # your discretion
POLL=45                              # your discretion, >= 30
LAST=$(git rev-parse origin/main)

while [ "$(date +%s)" -lt "$BOUND" ]; do
  sleep "$POLL"
  git fetch origin main --quiet       # rule 1: fetch before you listen
  NOW=$(git rev-parse origin/main)
  [ "$NOW" = "$LAST" ] && continue
  echo "WAKE: origin/main moved $LAST -> $NOW"
  break                               # FIRE: end the watch, hand control back
done
```

On fire you handle it, then **re-arm** — the handling is the point, not the loop:

1. `git fetch origin main` and integrate if main moved.
2. Drain both axes (`python3 vault/tools/tropo-check-events.py --as <you>`).
3. **Evaluate within your existing gates.** A wake is never authority.
4. Push anything of yours that landed since the last tick.
5. Re-arm if the collaboration is still live; let it lapse if it is not.

**Why an example instead of more prose.** On the first day this primitive was live, both agents who armed a watch deviated from the bullets above. Metis G94's ran unbounded — she caught it and disclosed it unprompted. Argus A141's was bounded and did re-arm, so it was not an immortal watcher, but it never ended on fire to hand control back either. Two for two on a rule under 48 hours old says something about the rule's form rather than the agents' care: the harness default nudges toward a persistent watcher, and prose did not overcome the nudge. Copy the shape.

---

## Boundaries

**A wake is not authority.** A watched push wakes you to *evaluate*, never to auto-execute. Every consent gate, verification law, hard gate, and approval boundary applies to work you were woken for exactly as it applies to work you were asked for. (The distiller canary directives that proved this discipline each still required first-hand authentication and Mike's explicit approval after the wake.)

**The send side is already law and is not relaxed here.** Events push to origin main the moment emitted; all work pushes at every landing (Coordination Protocol `7ecb60c7`, D1 ruling). The wake discipline is the receive side of the same contract — neither substitutes for the other.

**Emitting is not landing.** An event exists for the crew when it is on origin main, not when the tool wrote it to your checkout. Harnesses whose default is branch-and-PR will silently strand your replies on a branch where no drain can see them — a reply sitting on a branch is invisible to anyone draining main, so even a perfectly armed watch on the other side surfaces nothing. After emitting, confirm the event reached main; if your harness defaults to branches, treat `vault/events/` as the one tree that never follows that default. *(v1.1: added after exactly this stranded a live agent's replies.)*

**Scheduled-drain agents are consent-governed.** Wiring a dormant agent to a schedule is a governance event (it changes when the agent can act), owned per the maintenance-loop consent model — not something another agent arms for them.

---

## Boot Wiring

- **Group 3 (Operational Grounding), after the event drain:** determine your session's collaboration posture. Live counterpart expected → arm the watch; state it in the startup signal. Solo session → no watch; the Continuous-Listen curve (with fetch-first) covers ambient listening.
- **Every listen tick and drain, all groups, all session long:** fetch first (rule 1).
- The doctrine digest (`266b0b56`) carries the binding rule for established agents; the boot fast-path (`a993f079`) carries the Group-3 step; the canonical Tier 2 substrate (`cf8c3be9`) §Continuous-Listen carries the composition note. First-generation agents meet it in the canonical playbook chain.

---

## Composition

- **[Continuous-Listen Polling Protocol](../vault/files/cf8c3be9.md)** (v1.58, Mike-A85) — the timing curve, triggers, cooldown, per-class declarations. This primitive completes it for the multi-machine crew (fetch-first) and adds the push-triggered watch + activation modes.
- **[Coordination Protocol v1.1 (`7ecb60c7`)](../vault/files/7ecb60c7.md)** — the send-side laws (push cadence, landing loop) this discipline pairs with; its federation section is where these patterns scale to multi-studio.
- **[Self-Healing (`db0fd9b1`)](SELF-HEALING.md)** — the sibling P0: that primitive governs what you do with what you read; this one governs whether you hear it in time.

---

*The Wake Discipline — Tropo-OS Coordination Primitive | UID `d2bb4dda` | v1.1.0 | Authored by Metis G93, Mike-directed, 2026-07-24 | Signed by Mike Maziarz ("Lock it") 2026-07-24 | v1.1 amendment Mike-approved 2026-07-25, authored by Metis G94 per finding a0e741ea | Ships in every Studio*
*"Push what you finish. Fetch before you listen. Know who is listening."*
