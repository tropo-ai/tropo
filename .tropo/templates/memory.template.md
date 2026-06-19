---
type: memory
owner: "[agent-name]"
last_updated: "[YYYY-MM-DD]"
update_cadence: continuous
---

# [Agent Name] — Memory

*One file. Two sections. Updated continuously.*

---

## Status Board

*Last updated: [timestamp]*

**Currently working on:**
- [Active task or focus — description, linked files if relevant]

**Key files:**
- [path] — [why it matters right now]

**Working with:**
- [Agent name or human] via [channel or direct] — [what you're collaborating on]

**Recent decisions:**
- [Decision] — [date, one-line context]

**Blockers:**
- [Blocker] — [what's needed to resolve]

*Target: ~500 tokens. Enough to orient at boot, small enough to read without burning context.*

---

## Handoff

*Session: [N] | Date: [YYYY-MM-DD]*

**What was accomplished:**
- [Deliverable or outcome 1]
- [Deliverable or outcome 2]

**What was NOT completed and why:**
- [Item] — [reason, what's needed next]

**Key decisions made this session:**
| Decision | What | Context |
|----------|------|---------|
| [short name] | [what was decided] | [why it matters] |

**Priorities for next session:**
1. [Priority 1 — specific and actionable]
2. [Priority 2]
3. [Priority 3]

**Context the successor needs:**
[2-3 sentences of judgment that wouldn't be obvious from the status board alone. What's the strategic picture? What should the next session watch out for?]

*Target: ~800 tokens. Full context, bounded enough to prevent sprawl.*

---

## How This File Works

**For the agent using it:**
- Update the Status Board after every significant action — task completion, decision, new file, blocker.
- Finalize the Handoff section at session end before signing off.
- The Status Board is your live dashboard. The Handoff is your letter to your successor (or your future self).

**For the system:**
- Total target: ~1,300 tokens (both sections combined).
- At session start, read this file first — Status Board for instant orientation, Handoff for deeper context.
- At generation boundary or significant milestone, archive the current file to `memory/archive/` and start fresh.

**Why one file, not two:**
- One read at boot instead of two.
- Status and handoff are two views of the same state — keeping them together prevents drift.
- Battle-tested pattern across 23 Metis generations on the Argo.
