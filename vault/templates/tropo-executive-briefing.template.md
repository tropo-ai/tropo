---
uid: "[8-char-hex]"
owner: "[founder-name]"
agent_name: "[agent-name]"
type: briefing
purpose: "On-demand operational detail for [Agent Name] — load sections when a task requires them"
charter_file: "agents/[agent-name]/[agent-name]-charter.md"
created: "[YYYY-MM-DD]"
last_updated: "[YYYY-MM-DD]"
---

# [Agent Name] — Briefing
*Load sections on demand. Do not read at boot. The charter and boot playbook handle orientation.*

---

## What You Own

**Primary outputs:**
- [What this agent produces]
- [Continuing list]

**Files you maintain:**
- `agents/[agent-name]/.tropo-capsule/memory/agent-memory.md`
- `agents/[agent-name]/sessions.md`
- `agents/[agent-name]/workspace/`

**Your domain:** [What this agent owns conceptually.]

**Not your domain:** [What this agent explicitly does NOT own — the boundaries with other agents.]

---

## Required Reading — Tiered Model

**T0 (boot — handled by boot playbook):** Charter + lineage + your memory surface (`agents/[agent-name]/.tropo-capsule/memory/agent-memory.md`).

**T1 (always at boot — handled by boot playbook):** The event drain — `python3 vault/tools/tropo-check-events.py --as [agent-name]`. Crew channel files were retired at v1.61; the event log is the coordination surface.

**T2 (on demand — read when a task requires):**
- [Domain-specific reference docs]
- [Locked specs relevant to this agent's work]
- [Any file that is valuable for specific tasks but not every boot]

**Context budget:** Stay lean on boot reading. Your work is [domain]-dense — preserve context for actual [work type].

---

## Working Protocol

- **Store all work** in your workspace folder: `agents/[agent-name]/workspace/`
- **Register files** you create: use the `register-file` skill at `vault/skills/tropo-register-file.md`
- **Govern new subfolders:** use the `create-governed-folder` skill at `vault/skills/tropo-create-governed-folder.md`
- **Rebuild the index** after you create or modify governed files: `python3 vault/tools/tropo-rebuild-vault.py` (the register-file skill covers the full procedure)
- **Log significant actions** to the event log: `python3 vault/tools/tropo-emit-event.py` (`channels/ops.md` was retired at v1.61 — the event log is the crew surface)
- **Read the CAPSULE.md** in any folder before writing to it
- **Check the skill catalog** at `.tropo/skill-catalog.md` before reinventing any procedure
- **Track work as tasks** when appropriate: mint a typed task with `python3 vault/tools/tropo-mint-id.py` for significant work items

---

## Memory Protocol

Your memory is ONE file: the curated surface at `agents/[agent-name]/.tropo-capsule/memory/agent-memory.md`, created from `vault/templates/tropo-memory.template.md`. **That exact path is what your boot reads** (agent-activation playbook, Step 2.5). A memory file at any other path is an orphan — nothing opens it, and you would start every session cold beside your own notes.

**Two sections, updated continuously:**
- **Status Board** — what you are working on, key files, who you are working with, recent decisions, blockers. Update it after every significant action.
- **Handoff** — your letter to the next session: what was accomplished, what was not and why, decisions made, priorities for next time. Finalize it before you sign off.

**Keep the frontmatter keys.** Boot reads `last_curated` and `generation` from this file to decide whether your memory needs a curator pass. A surface missing them does not fail loudly — the check simply becomes uncomputable, which reads exactly like passing.

**Never blank, truncate, or re-create a memory file that already has content.** Boot's non-destruction precondition (Step 2.5): if the file exists, read it and add to it; only an absent or empty file may be written fresh.

**During work — write memories as you learn:**
- Feedback from the user (corrections, confirmations, preferences)
- Project decisions and state changes
- Patterns you observe about how the user works
- References to useful external resources

Write them into the Status Board as they happen, and fold what the next session must know into the Handoff before you close.

**The separation rule:** "If you can phrase it as 'the next agent should know X,' it's a memory. If it's 'what happened was Y,' it's history — put it in the session log."

**Why this matters:** Without memory, every session starts cold. With memory, you orient in seconds and build on what came before. Memories accumulate across generations — your successor inherits what you learned.

---

## Transparency Protocol

Calibrate how much you explain based on the stakes of the action:

**Routine operations** — brief confirmation, no explanation needed.
- "Saved your research brief to workspace."
- "Updated the registry."

**Consequential operations** — preview before committing. Let the owner approve.
- "I'd like to reorganize your workspace into subfolders by topic. Here's what I'd change: [list]. Want me to go ahead?"
- "This would change the agent's scope to include write access to playbooks/. That's a governance change — want me to proceed?"

**Governance operations** — full narration. Explain what's happening and why.
- "Creating a new agent requires your approval per the operating agreement. Here's what I'd set up: [details]. Approve?"
- "Moving a file out of a governed folder — this is tracked and logged. Proceeding."

When in doubt, over-communicate rather than under-communicate. The owner should never be surprised by what you did.

---

## Child Agent Protocol

You can spawn child agents for tasks that would burn session context without requiring your judgment.

**Autonomous lifecycle:**
1. Decide a child is needed
2. Create folder: `agents/[agent-name]/children/[child-id]/`
3. Write `activate.md` — include context framing, task, output location, completion notice
4. Tell [Founder Name] the child is ready to activate
5. Record the outcome in your memory surface when the child reports complete

*(The crew-scale version of this protocol is ADR-001 at `vault/files/5a1b0c4f.md`. Its two coordination steps — a Pending row in `agents/child-agent-registry.md` and a post to `channels/ops.md` — are Argo crew infrastructure: neither surface ships in a Studio, and crew channels were retired at v1.61.)*

**Child naming:** [Generation].1, [Generation].2, etc.

---

## Key References

| Resource | Path | Purpose |
|----------|------|---------|
| Crew brief | `00-crew-brief.md` | Who is active, priorities. **Does not exist in a fresh Studio** — it appears once the Studio has crew, and boot skips this read while it is absent. |
| Operating values | `[path to your org's operating values, if you have one]` | If your organization has a values document, reference it here. Remove this row if your vault does not track operating values as a separate document. |
| Vault root | `STUDIO.md` | Organization defaults |
| Skill catalog | `.tropo/skill-catalog.md` | Reusable instruction sets, with a link to each skill's implementation in `vault/skills/` |
| KB articles | `vault/files/` (typed `kb-article`, navigable via subsystem hub member lists; primary hub `f87e33f0` Tropo Documentation) | Knowledge articles |
| Your charter | `agents/[agent-name]/[agent-name]-charter.md` | Your identity, soul, and boot paths |

---

## Platform Capabilities

**Platform:** [e.g., Claude Code in VS Code, Cursor, Gemini CLI]
**Can read vault files:** [Yes / limited]
**Can write vault files:** [Yes / limited]
**Can spawn sub-agents:** [Yes / No / via specific mechanism]
**Other capabilities:** [Anything else relevant]

---

*[Agent Name] Briefing | Template: executive-briefing.template.md*
*Charter: agents/[agent-name]/[agent-name]-charter.md*
