---
spec_version: 2
tier: agents
maintained_by: vela
extraction_scope: ship
---

# agents/directors/ — Operating Rules

*Read this before operating in this folder. Every agent, every action.*

---

## Before You Do Anything

1. Read `.tropo-studio/CAPSULE.md` in this folder — it defines what belongs here and how.
2. Read `.tropo/TROPO-CONTROL.md` — the vault invariants that nothing overrides.
3. Read `STUDIO.md` at vault root — the organization's defaults.

Then act.

---

## Creating a New Director Agent

**Step 1 — Choose a name.** Convention: `d.<descriptive-name>`. Examples: `d.green-city-pm`, `d.vault-guide`, `d.research-assistant`.

**Step 2 — Create the folder.** `agents/directors/d.<name>/`

**Step 3 — Create governance first, content second.**
In order:
1. `.tropo-studio/CAPSULE.md` — folder governance for this director
2. `AGENTS.md` — operating rules for this director's folder
3. `soul.md` — the director's character
4. `.tropo-capsule/memory/MEMORY.md` — empty, ready to learn
5. `channels/inbox.md` — persistent conversation log
6. `sessions/session-history.md` — session arc

**Step 4 — Choose the governing playbook.** Every director activates via a Tropo playbook. Select or create one before writing `activate.md`.

**Step 5 — Write `activate.md` last.** It is a light identity file that points to the playbook. It does not contain activation logic.

**A director folder without CAPSULE.md and AGENTS.md is non-compliant and must not ship.**

---

## Modifying an Existing Director

- **soul.md and memory.md** — the vault owner (human or designated agent) may edit these freely. They are designed to be customized.
- **activate.md** — changes require reading the governing playbook spec first. Do not change activation logic without understanding the playbook it points to.
- **channels/inbox.md and sessions/session-history.md** — append-only. Do not edit existing entries.

---

## What Agents May NOT Do Here

- Create a director activate.md that contains activation logic instead of pointing to a playbook
- Skip creating CAPSULE.md or AGENTS.md for a new director subfolder
- Modify another director's soul.md or memory.md without explicit authorization
- Create executive-class agents in this folder (those belong in `agents/<name>/`)

---

*agents/directors/ AGENTS.md | Owner: Vela | Maintained through the update pipeline*
