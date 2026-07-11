---
skill: construct-briefing
name: construct-briefing
type: how-to
purpose: Build a successor's briefing package from source material per the CURATOR
when: At retirement (Phase 3) for executive agents with successors
mode: delegated
params:
  - agent_name
  - generation
  - curator_path
  - briefing_path
uid: 5d3f1a87
status: active
owner: argus
created: 2026-04-15
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: Reach for this at retirement (Phase 3) when constructing the briefing package for your successor — the most valuable artifact of retirement. Reads the agent's CURATOR.md (defines structure, tone, editorial guidance), archives the predecessor briefing if present, gathers source material (living transfer, completed work, status card, recent channels), and assembles the curated orientation. Delegated mode — runs as a sub-agent in its own context to keep parent context for retirement reflection.
subsystem_hub:
  - 99ed55fd
---

# Construct a Briefing Package

Use this at retirement to build a curated orientation for your successor. The briefing package is the most valuable artifact of retirement — it is your gift to the next generation.

## Steps

1. **Read the CURATOR.** Open `{curator_path}` (default: `agents/{agent_name}/briefing-package/CURATOR.md`). It defines the structure, tone, and editorial guidance for this agent's briefing packages. Follow its instructions.

2. **Archive the current briefing.** If `{briefing_path}/00-index.md` exists, move it to `{briefing_path}/archive/00-index-g<previous-gen>.md`.

3. **Read source material.** Gather context from:
 - Your living transfer (just written in Phase 3 of retirement)
 - Your session's completed work (from the board or status card)
 - Channel activity relevant to your successor
 - Any specs locked, tasks created, or decisions made this session
 - BOARD.md for strategic context

4. **Write the new 00-index.md.** Structure per the CURATOR, but at minimum include:

 ```markdown
 ---
 agent: "{agent_name}"
 generation: "G<current>"
 briefing_date: "<today>"
 status: "FINAL"
 predecessor: "G<current>"
 for_successor: "G<next>"
 ---

 # {Agent Name} Briefing Package — G<next> Orientation

 *Constructed by: G<current> at retirement | For: G<next>*
 *Tone note: <one sentence — what kind of session is the successor walking into?>*

 ## The one-line strategic summary
 <What happened and what's next>

 ## Read in this order
 <Numbered list of files with why each matters>

 ## Priority actions
 <What the successor should do, ranked>

 ## What NOT to do
 <Guardrails — common mistakes, things to avoid>

 ## Key Mike insights from this session
 <Direct quotes or paraphrases that carry judgment>

 ## One thing to remember
 <The single most important piece of context>
 ```

5. **Verify the reading list.** For each file referenced in "Read in this order," confirm the file exists and the path is correct. Broken references in a briefing produce a disoriented successor.

## Success

- Prior briefing archived with generation label
- New `00-index.md` is complete with all required sections
- Every file referenced in the reading list exists at the declared path
- The briefing is self-contained — a cold-boot successor can orient from this file alone
