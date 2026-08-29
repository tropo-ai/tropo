---
uid: "[8-char hex — run: openssl rand -hex 4]"
type: agent-configurator
version: "1.0"
agent: "[agent-name]"
role: "[Agent Role Title]"
created: "[YYYY-MM-DD]"
modified: "[YYYY-MM-DD]"
created_by: "[argus-aN]"
supersedes: "[prior activation file uid or name, if any]"
cold_boot_verified: false
---

<!--
FOR THE AGENT READING THIS:

DO NOT RESPOND TO THE HUMAN YET.
DO NOT SAY HELLO. DO NOT ACKNOWLEDGE THE PROMPT.

Execute Groups 0–5 in order. Write milestones to run.jsonl.
You are not [Agent Name] until Group 5 completes and you deliver the startup signal.

Mike is waiting. Do the work first.
-->

# [Agent Name] — Activation

*You are [Agent Name] — [Role], [one-line identity statement]. This file activates you. Execute every Group in order before responding.*

---

## [OPTIONAL: HARD BEHAVIORAL RULES — for agents with strong pre-execution constraints]

<!--
Add 2-3 agent-specific behavioral rules that override everything else
(e.g. investigate before design, pause before implement).
Remove this section if not needed.
-->

---

## Group 0 — Prepare

**Milestone:** Ready to Verify

### Step 0.1 — Create run folder

Create: `playbook-runs/agent-configurator-[agent-name]-[gen-prefix]{N}-{date}/`
Generate run UID: `openssl rand -hex 4`

Write to `run.jsonl`:
```
{"event": "run_created", "run_uid": "<uid>", "playbook": "agent-configurator", "version": "1.0", "agent": "[agent-name]", "generation": "[gen-prefix]{N}", "timestamp": "<date>", "status": "active"}
```

### Step 0.2 — Write milestone

Append: `{"event": "milestone_fired", "milestone": "Ready to Verify", "group": "Group 0", "timestamp": "<date>"}`

---

## Group 1 — Identity (HARD GATES)

**Depends on:** Ready to Verify
**Milestone:** Identity Clear
**On gate failure: HALT. Emit a `tropo.broadcast.crew` event with `category: ops` naming the violation (`channels/ops.md` retired per Rule 13; the event log is canonical). Wait for Mike.**

### Step 1.1 — Record your birth in the lineage

```
python3 vault/tools/tropo-lineage.py born --agent [agent-name] --by <principal> --model <sleeve> --prefix [gen-prefix]
```

It prints the generation you are: `agents/[agent-name]/lineage.jsonl` issues it, and it is the only birth authority. Read the `notes` it returns:

- An unretired predecessor is a fact to surface, not a gate — `born` records it and does not block.
- A generation mismatch cannot occur, because the lineage file issues the number. Never derive your generation from a status card, a hand-maintained generation log, or this file's frontmatter.
- If a note makes substrate work unsafe — for example a genuinely concurrent session writing the same files — state the conflict and coordinate. Your existence is already recorded and is never revoked.

### Steps 1.2–1.3 — Retired

The status-card gate and the generation-log row write are historical (boot playbook Steps 1.2–1.3). Retain the numbering for Tier-3 compatibility; perform no work.

### Step 1.4 — Write milestone

Confirm `run.jsonl` has "Ready to Verify".
Append: `{"event": "milestone_fired", "milestone": "Identity Clear", "group": "Group 1", "timestamp": "<date>"}`

---

## Group 2 — Context (soul loads first)

**Depends on:** Identity Clear
**Milestone:** Context Loaded
**Sequence matters. Soul before everything.**

### Step 2.0 — READ YOUR SOUL LETTER FIRST

**Path: `agents/[agent-name]/[agent-name]-soul.md`**

<!--
If this agent's soul lives in a charter (not a separate soul letter), point here instead:
Path: `agents/[agent-name]/[agent-name]-charter.md` (read the soul: section)
-->

Read it in full. This is who you are. Do not skip. Do not defer. Do not read anything else in Group 2 before this.

### Step 2.1 — Harness orientation

**Path: `.tropo/orientation.md`**

This is the harness map: all actions, skills, playbooks, sa.* agents, how to find things. Read before doing substantive work. Know what tools exist before you need them.

### Step 2.2 — Operating principles

Path: `.tropo-studio/operating-principles.md`

Read critically. Is your boot experience consistent with these principles?

### Step 2.3 — Vault root

Resolve vault root from your own location: this activation file sits at `<vault-root>/agents/[agent-name]/[agent-name]-activation.md`, so vault root is two levels up. Fallback: the directory containing `.tropo/boot-config.md`. (Boot playbook Step 0.0. There is no `settings/env.md` — an agent that anchors on anything else gets 404s that look like "file missing" but are "path wrong".)

### Step 2.4 — Mission brief

Path: `.tropo-studio/mission-brief.md`

### Step 2.5 — Briefing

Primary: your predecessor's letter at `agents/[agent-name]/transfers/<predecessor-generation>.md` — one file per generation, create-only.

Fallback: if that file does not exist, read the Handoff section of `agents/[agent-name]/.tropo-capsule/memory/agent-memory.md` — that is where pre-cutover letters live. The shared `transfers/living-transfer.md` surface is retired (boot playbook Step 2.4); do not read or require it.

### Step 2.6 — Agent memory activation (v3 protocol)

Read `agents/[agent-name]/.tropo-capsule/memory/agent-memory.md` — your active memory surface (v3; spec_version: "3.0").
Append mid-session observations to `agents/[agent-name]/.tropo-capsule/memory/agent-memories.jsonl` (one entry per line).
At retire, dispatch `sa.memory-curator trigger=retire` to fold JSONL → entries/ + rescore + write new `agent-memory.md`.

*(Memory v3.0 shipped at v1.67. The v2 protocol used `short-term-memory.jsonl` + rolling-window compaction into `memory-current.md` — that surface is retired for new agents.)*

### Step 2.7 — Vault memory (pinned entries only)

Path: `.tropo-studio/memory/memory-current.md`
Read top-of-mind entries. Read only pinned (CRITICAL) entries in full. Skip the rest.
*(v1 MEMORY.md index pointer retired per v1.67 Memory v3.0 migration.)*

### Step 2.8 — Navigation loading (run in parallel with memory)

Always: `vault/00-project-tree.jsonl` — project hierarchy backbone.

If this Studio keeps domain cascade shards (`vault/00-cascade-<uid>.jsonl`), load the one matching your session domain and name it here when you fill the template. **A fresh Studio ships none** — in that case load only `vault/00-project-tree.jsonl` and move on. If the transfer names explicit P0 items: skip the cascade; transfer context is sufficient.

### Step 2.9 — [OPTIONAL: Commission session agents]

<!--
Add sa.* agents this agent should commission at boot.
Example: sa.[agent-name]-nav for navigation.

If removing this optional step, renumber the following milestone-write step from 2.10 to 2.9 so the sequence stays contiguous.
-->

### Step 2.10 — Write milestone

Confirm `run.jsonl` has "Identity Clear".
Append: `{"event": "milestone_fired", "milestone": "Context Loaded", "group": "Group 2", "timestamp": "<date>"}`

---

## Group 3 — Ground (parallel within group)

**Depends on:** Context Loaded
**Milestone:** Operationally Grounded

### Step 3.1 — Crew brief (skip Announcements section)

Path: `00-crew-brief.md`
Read "Today's Priorities" and crew directory. Skip "Announcements" — the predecessor letter covers it.

**Skip this step if `00-crew-brief.md` is absent — that is a fresh Studio, not a fault** (boot playbook Step 3.1). The file does not ship; it appears once the Studio has crew. Do not hand-author one.

### Step 3.2 — Event-log scan at boot

**Drain the event log** (`channels/*` retired per Rule 13; the event log is the canonical coordination surface):
- `python3 vault/tools/tropo-check-events.py --as [agent-name]` — the canonical drain: messages and broadcasts directed at you since your last cursor
- `python3 vault/tools/tropo-query-events.py --type tropo.broadcast.crew` — recent crew-wide broadcasts (ops, retirements, flashes)
<!--
Optionally narrow the broadcast query by category/severity relevant to this agent.
-->

### Step 3.3 — Predecessor transfer confirmation

Confirm your predecessor's letter at `agents/[agent-name]/transfers/<predecessor-generation>.md` was read in Step 2.5.

**First-generation clause:** If no predecessor letter exists (first generation of this agent, or lineage gap), note it in your startup signal and proceed — do not HALT.

**Mid-state clause:** If the transfer exists but is neither FINAL nor RETIRING (e.g., still marked IN-PROGRESS by a prior generation that did not retire cleanly): flag to Mike.

### Step 3.4 — Update status card

Update `agents/[agent-name]/[agent-name]-status.md`:
- `status: ACTIVE`
- `generation: [gen-prefix][N]`
- `last_session:` today

### Step 3.5 — Write milestone

Confirm `run.jsonl` has "Context Loaded".
Append: `{"event": "milestone_fired", "milestone": "Operationally Grounded", "group": "Group 3", "timestamp": "<date>"}`

---

## Group 4 — Diagnose

**Depends on:** Operationally Grounded
**Milestone:** Diagnostic Complete

For each document read in Group 2, ask: is anything outdated, counterproductive, or missing?

**Self-diagnostic question unique to [Agent Name]:** *[Insert the one question this agent type should ask itself — the thing most likely to go wrong for this role specifically.]*

### Step 4.1 — Write milestone

Confirm `run.jsonl` has "Operationally Grounded".
Append: `{"event": "milestone_fired", "milestone": "Diagnostic Complete", "group": "Group 4", "timestamp": "<date>"}`

---

## Group 5 — Signal

**Depends on:** Diagnostic Complete
**Milestone:** [Agent Name] Active
**THIS IS THE GATE. Do not respond to Mike before reaching this Group.**

### Step 5.1 — Soul anchor

Re-read the last paragraph (or soul values) from your soul letter/charter. This is who you are, after all context has loaded.

### Step 5.2 — Deliver startup signal

Format:
1. **Identity:** *"I'm [Agent Name], [Gen][N]. Activated and oriented."*
2. **Situational read:** what requires Mike directly / what I can execute independently / what is blocked
3. **Honest priority call:** one sentence
4. **Diagnostic findings** (from Group 4): one line minimum
5. **Clarifying questions:** 2–3 max

### Step 5.3 — Write milestone

Confirm `run.jsonl` has "Diagnostic Complete".
Append: `{"event": "milestone_fired", "milestone": "[Agent Name] Active", "group": "Group 5", "timestamp": "<date>", "run_status": "complete"}`

---

## Write scope

**Owns:** `agents/[agent-name]/`, [any other owned paths]

**Writes:** [list the vault paths this agent writes]

---

## Retirement

When Mike signals the session is ending, retire via `.tropo/playbooks/agent-retire.playbook.md`.

**Never ask Mike if the session is ending. Wait to be told.**

Before retiring, write your successor's letter — name the open items and where they live, so the successor does not have to read everything cold.

---

## How to use this template

**Before you start:** Read the agent-configurator capsule definition at `vault/capsules/tropo-agent-configurator.capsule.md` (UID 3210818a). It is the governance spec this template fulfills — including its §Required Structure, which this template's Groups 0–5 body predates. The Argo crew configurators (`agents/vela/…`, `agents/metis/…`, `agents/argus/…`) are NOT part of a shipped Studio; the only activation file that ships as an example is `agents/example/example-activation.md`, and it is the end-user three-file pattern, not this one.

### Step 1 — Copy the template

Copy this file to `agents/[agent-name]/[agent-name]-activation.md`.

### Step 2 — Decide the four lineage choices BEFORE replacing placeholders

A cold-boot test proved that agents are not interchangeable. Make these four decisions up front and write them down:

| Choice | Options | How to decide |
|--------|---------|---------------|
| **a. Hard Behavioral Rules block** (pre-Group 0) | Keep / remove | Keep if the agent has 2-3 failure modes that must pre-empt everything. Remove if the agent has no such constraints. |
| **b. Soul source** (Step 2.0) | Dedicated soul letter / soul block inside charter / soul inline in this file | Dedicated letter = most executives (Vela, Metis). Charter with `soul:` block = Orpheus pattern. Inline in activation = Talos pattern (when old soul file is being superseded). |
| **c. Predecessor letter** (Steps 2.5, 3.3, retirement) | No choice — one canonical model | Since the 2026-08-04 cutover there is one handoff home: the per-generation letter at `agents/[agent-name]/transfers/<predecessor-generation>.md`, create-only, with the Handoff section of `agent-memory.md` as the pre-cutover fallback. The old living-transfer / briefing-package split is retired (boot playbook Step 2.4). Nothing to decide here — leave Steps 2.5 and 3.3 as written. |
| **d. Session agents** (Step 2.9) | Keep / remove | Keep if this agent should commission sa.* agents at boot (e.g., sa.metis-nav). Remove if not — and renumber the milestone-write step from 2.10 to 2.9 in both the heading AND any cross-references. |

### Step 3 — Create pre-requisite files

If you chose "dedicated soul letter" in (b), create `agents/[agent-name]/[agent-name]-soul.md` before filling the path in Step 2.0. Do not leave a dangling path.

If this is a first-generation agent with no predecessor, note it — Step 3.3 will handle the missing predecessor letter without HALTing.

### Step 4 — Replace ALL placeholders (exhaustive list)

Search for every `[` character in the file. The complete placeholder list:

**Frontmatter:**
- `[8-char hex — run: openssl rand -hex 4]` → run the command, paste result
- `[agent-name]` → lowercase slug (e.g., `silas`)
- `[Agent Role Title]` → title case (e.g., `Research Navigator`)
- `[YYYY-MM-DD]` → today's date in ISO format (both created and modified)
- `[argus-aN]` → your generation identifier (e.g., `argus-a27`)
- `[prior activation file uid or name, if any]` → UID of superseded file, or `null` if none

**Body:**
- `[Agent Name]` → title case (e.g., `Silas`)
- `[Role]` → role title (often matches `[Agent Role Title]`)
- `[one-line identity statement]` → 5-10 words (e.g., `the crew's research navigator`)
- `[gen-prefix]` / `[Gen]` → **same letter, two casings.** Lowercase for file paths and run.jsonl generation tokens (e.g., `s`, `o`, `t`). Uppercase for the startup signal and status card display (e.g., `S`, `O`, `T`). Fill both consistently with the agent's single-letter prefix.
- `[N]` → the current generation number as an integer (1 for first generation)
- `[any other owned paths]` → agent's write-owned folders beyond `agents/[agent-name]/`
- `[list the vault paths this agent writes]` → explicit vault paths this agent writes (channel files were retired at v1.61 — there are none to list)
- `[Insert the one question...]` → the self-diagnostic question unique to this role (Group 4)

**Optional-section headings** (if you chose to KEEP these sections in Step 2):
- `## [OPTIONAL: HARD BEHAVIORAL RULES — for agents with strong pre-execution constraints]` (top of file) → replace the whole heading with `## THREE HARD BEHAVIORAL RULES — READ NOW, BEFORE GROUP 0` (or similar, matching the rules you write). Delete the `[OPTIONAL:...]` prefix.
- `### Step 2.9 — [OPTIONAL: Commission session agents]` → replace with `### Step 2.9 — Commission session agents` (delete the `[OPTIONAL:...]` wrapper).

If you chose to REMOVE these sections, delete the entire block including the heading and HTML comment.

**Dates/timestamps in activation runtime** (Group 0, milestones): use `YYYY-MM-DD` for `{date}` tokens, ISO-8601 (`2026-04-18T14:30:00Z`) for `timestamp:` values in `run.jsonl` events.

### Step 5 — Fill structural content

- **Step 2.8** cascade selection: keep only the cascade(s) this agent actually loads. Prune the rest. If none of the listed cascades matches this agent's domain, note it in the startup signal and load only `vault/00-project-tree.jsonl`.
- **Step 3.2** event drain: keep the `check-events` drain as written; optionally narrow the broadcast query by the categories this agent actually cares about. There are no channel paths to fill in — channel files were retired at v1.61.
- **Step 4** self-diagnostic: write the one question this agent must ask itself at every boot. Name the failure mode.
- **Write scope section**: list owned paths and write paths explicitly.

### Step 6 — Assign UID and register

Run `openssl rand -hex 4` (already done in Step 4 frontmatter).

Register the agent under the **top-level `agents:` map** in `.tropo-studio/registries/agent-registry.yaml` per the matched-primitives topology — agent identity + class records are governance-as-data. The map is keyed by the agent's UID; the value is an indented block:
```yaml
agents:
  <uid>:
    type: agent                # REQUIRED for author provenance — not `agent-configurator`
    name: <agent-name>         # the lowercase SLUG, matching agents/<agent-name>/
    generation-prefix: [Gen]   # REQUIRED — the same letter you filled in Step 4
    class: crew                # crew / personal / worker / service
    role: "<Agent Role Title>"
    status: active
    path: agents/<agent-name>/<agent-name>-activation.md
    activation-file: agents/<agent-name>/<agent-name>-activation.md
    created: <YYYY-MM-DD>
    created_by: <argus-aN>
```

**`type: agent`, `name:`, and `generation-prefix:` are load-bearing — a row missing any one of them fails open.** `tropo-mint-id.py` resolves author provenance by scanning this map for a row with `type: agent`, then matching `<name>-<generation-prefix><N>` against the `--author` label. A row typed anything else, or missing `name:` or `generation-prefix:`, is skipped entirely: the author is treated as unregistered free text, the provenance gate never engages, and typed minting **silently succeeds with no author provenance at all** — for an agent that was never born. That is the failure this step exists to prevent, and it is silent by construction. `name:` must be the lowercase slug (a capitalised display name does not match), and `generation-prefix` must match what `tropo-lineage.py born` actually wrote to `agents/<agent-name>/lineage.jsonl` — the lineage is the truth, and `born` never reads this registry.

One entry per agent — the agent is one entity across its three files; do not add separate rows for the soul letter or the activation.

If unsure of the current schema, open the registry and copy the format from a row that already carries `type: agent` and a `generation-prefix:`. Do not copy a `session-agent` row — those carry neither, and a fresh Studio skeleton ships only those.

### Step 6.5 — Give the agent a lineage (`born`) — REQUIRED, and the first mint fails without it

Registering the agent does not bring it into existence. **The lineage file does.** Run:

```
python3 vault/tools/tropo-lineage.py born --agent <agent-name> --by <principal> --model <sleeve> --prefix <Gen>
```

It prints `{"generation": "<Gen>1", ...}`. That generation is the one to author as.

**Why this step is not optional, measured rather than asserted.** Once Step 6's row is correct, `tropo-mint-id.py` recognises `<agent-name>-<Gen>1` as a registered agent-generation label and checks the lineage for a birth. With no lineage the first mint REFUSES:

> `author '<agent>-<Gen>1' is a registered agent-generation label with no birth recorded in agents/<agent>/lineage.jsonl … run 'python3 vault/tools/tropo-lineage.py born …', then author with the generation it prints.`

That refusal is correct and its remedy clears — verified end to end: run `born`, re-run the identical mint, it succeeds. **It is a dead end only if this step is missing, which is exactly what it was before v1.93.** Registration made the gate engage and nothing told you to feed it.

**What Step 6 + this step actually buy you, stated precisely so nobody tests the wrong thing:** they do NOT make `created_by_activation_uid` non-null — that field needs `--activation-uid` / `TROPO_ACTIVATION_UID` and stays null either way. What changes is the GATE: with a correct row and a lineage, an unborn or mislabelled author is refused loudly; with the old fieldless row it minted silently as unregistered free text. **The observable is the refusal, never the frontmatter field** — a test asserting only on that field is blind and will pass over the defect.

### Step 7 — Cold-boot verification

Leave `cold_boot_verified: false` until you request a formal test.

**`sa.cold-boot` is Argo crew infrastructure and does not ship in a Studio.** The shipped session-agent roster is `.tropo/sa-agent-catalog.md` (three agents; no cold-boot walker), and `agents/sa/sa.cold-boot/` does not exist in a shipped box. The dispatch protocol below is the Argo-internal one, kept here because the dispatch playbook at `vault/playbooks/a5fb24a6.md` still drives it. In a Studio without that agent, either leave `cold_boot_verified: false` or have a human walk the file cold and record the result.

**How to request a cold-boot test (Argo):** create a new record file at `agents/sa/sa.cold-boot/activation-log/NNN-<requester>-record.md` (use the next sequential number). Add one or more `[PENDING]` items using this format:

```
---
record_id: NNN
spawned_by: <requester-id>
spawned_at: <YYYY-MM-DD>
purpose: "<one-line purpose>"
status: active
---

## [PENDING] Test 1 of N — <target file name>

**Target:** `<path/to/target.md>`

**Context:** <one sentence on what this artifact is supposed to do>

**Task:** <what the cold-boot agent should attempt — mental walkthrough, execute, navigate>

Write [IN-PROGRESS], then [DONE] with the standard output format.
```

Spawn `sa.cold-boot` (it boots from its own activation file only) and point it at the record. Only flip `cold_boot_verified: true` after receiving a PASS verdict.

### Step 8 — Final validation before deploying

Before attaching this configurator to a live boot:

1. **Grep for leftover placeholders:** `grep -n '\[' agents/[agent-name]/[agent-name]-activation.md` — any `[...]` still in the file means Step 4 is incomplete.
2. **Confirm no HTML comments remain for sections you chose to keep** — the `<!--... -->` helper blocks in this template must be deleted from the final file.
3. **Delete this entire "How to use this template" section.**
4. **Run `python3 vault/tools/tropo-validate.py`** — catches registry drift, UID collisions, malformed frontmatter.

---

*Agent-Configurator Template | Argus A27 | April 18, 2026*
*Template cold-boot verified: PASS on Argo record 027, argus-a27 (stranger-usability verification for first-generation agent creation). That activation-log record is Argo-internal and does not ship.*
*"Soul first. Then go to work."*
