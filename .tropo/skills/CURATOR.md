---
type: curator
owner: "d.curator (via Tropo framework)"
schedule: "on-demand (when skills are added or modified)"
last_run: "2026-04-10"
last_run_by: "vela-v25 (initial creation)"
hot_window: "n/a"
warm_window: "n/a"
cold_after: "n/a"
v1_61_channel_tail_note: "Argus A97 2026-06-04 — v1.61 channel-retirement tail fix; replaced dead channel-post instructions with the canonical tropo.broadcast.crew event-log pattern. No contract change."
member_of:
  - "8dd772a0"   # tropo-governance (v1.12 backfill 2026-05-08)
---

# CURATOR — Skills Folder

*Index maintenance for `.tropo/skills/`.*
*Owner: d.curator (the CURATOR Director). Created: April 10, 2026 by Vela V25.*
*Per ADR-020 (The Curator Protocol).*

---

## What This Folder Is

`.tropo/skills/` contains the skill primitives that ship with Tropo-OS. Each file (`<action-name>.skill.md`) is a small, focused instruction set that teaches any Tropo agent how to perform a specific action. Skills are the "how do I do this one thing?" layer between KB articles and playbooks.

Skills are loaded by agents at boot (via the skills index) and invoked during work when an agent needs to perform an action that has a published skill. The skills index is the catalog that makes skills discoverable and reflexive.

---

## What Matters

Every file in this folder matters permanently. Skills are not compressed, summarized, or archived. The curator's job is **index maintenance** — keeping `00-index.md` accurate, complete, and useful as skills are added, modified, or removed.

**What the curator must protect:**
- Every skill file has an accurate entry in `00-index.md`
- The index categorizes skills by purpose (lifecycle, governance, maintenance, debugging)
- Each index entry includes the skill name, purpose, when to use, and execution mode
- The "when to use" field is precise — agents should be able to read the index and know which skill fits their current task

**What drifts and needs tending:**
- New skill files added to the folder that aren't in the index yet
- Skill files whose frontmatter changes (purpose, when, mode) without index updates
- Removed or renamed skills that still appear in the index
- Skills that should be categorized differently as their purpose evolves

---

## How to Curate

This folder uses a **non-compressing, index-maintenance** CURATOR model — the same as `design/` and the Primary Source folder. Skills themselves are never modified by the curator. Only the index is rewritten.

Follow the d.curator efficiency protocol (see `agents/directors/d.curator/directives/efficiency-protocol.md` v1.1):

### Step 1: Read the current index

Read `.tropo/skills/00-index.md`. Build a list of every skill currently indexed: filename, purpose, when, mode, category.

### Step 2: Scan the folder

Use Glob to find all `*.skill.md` files in `.tropo/skills/`. Compare against the index.

### Step 3: Classify each skill file

- **Unchanged (use mod-date skip):** If the skill file's last-modified date is older than the index's `last_updated`, and the file is present in the index — no action needed.
- **Already indexed, possibly changed:** File modified since last index. Read frontmatter only (first 10 lines). Compare `skill`, `purpose`, `when`, `mode` against the index entry. If matched — current. If differs — update the entry.
- **New:** File exists but not in index. Read the full skill file. Write a complete index entry under the appropriate category (Lifecycle, Governance, Maintenance, Debugging, or a new category if justified).
- **Orphaned:** Index entry exists but file is gone. Remove the entry. Note the removal in the run report.

### Step 4: Categorize thoughtfully

Skills fall into one of these categories today. A new category should be added only when at least two skills justify it:

- **Lifecycle** — skills invoked by boot/retirement playbooks
- **Governance** — skills that create or register governed artifacts
- **Maintenance** — skills that keep the vault healthy over time
- **Debugging** — skills that diagnose and fix specific failure modes

### Step 5: Write the updated index

Rewrite `.tropo/skills/00-index.md` with:
- Updated `last_updated` in frontmatter
- Each category's table current
- The "How Skills Relate to Other Primitives" section unchanged unless the spec evolves
- The "Adding a New Skill" procedure unchanged

### Step 6: Report

Produce a run summary:
- Skills indexed: [total count]
- New entries added: [count + filenames]
- Entries updated: [count + what changed]
- Orphaned entries removed: [count + filenames]
- Uncategorized or ambiguous: [flag for Mike review if any]

---

## When This Curator Runs

**On demand** — when a Tropo agent adds, modifies, or removes a skill file.

**At vault maintenance playbook runs** — the CURATOR fleet dispatch (Sub-Agent 11) can invoke this curator as one of the on-demand curators in its pass.

**At update pipeline application** — when Tropo ships new skills via an update package, this curator runs as a post-apply step to refresh the index.

---

## Curator Agent Instructions

When you are dispatched as a curator agent for the skills folder:

1. **Phone home first** — read the d.curator directives at `agents/directors/d.curator/directives/`:
 - `quality-standard.md`
 - `efficiency-protocol.md` (v1.1 with mod-date skip)
 - `index-naming-standard.md` (the index is always `00-index.md`)

2. **Read this CURATOR.md** for folder-specific instructions.

3. **Follow the four-tier efficiency protocol** — skip (unmodified) → frontmatter-only → partial body → full read. Most runs should be cheap.

4. **Do not modify any skill file.** You read everything; you write only `00-index.md`.

5. **Emit a `tropo.broadcast.crew` event (`category: ops`)** with a run report (`channels/ops.md` retired per Rule 13):
 ```
 [YYYY-MM-DD] skills-curator | Indexed N skills. Added M. Updated K. Report at logs.
 ```

---

*CURATOR for Skills Folder v1.0 | Created by Vela V25 | April 10, 2026*
*Per ADR-020 (The Curator Protocol)*
*Governed by d.curator Director directives*
*"Skills are the reflex. The index is the map."*
