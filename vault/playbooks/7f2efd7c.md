---
uid: 7f2efd7c
title: "First Vault Setup"
version: "4.0"
status: superseded
superseded_by: ".tropo/playbooks/concierge-paths/"
superseded_at: 2026-04-21
superseded_by_agent: argus-a31
author:
 name: "Tropo"
 role: "Framework"
domain: "onboarding"
tags: [onboarding, first-run, agent-creation, getting-started, superseded]
estimated_duration: "5-15 minutes"
readers: [agent]
member_of:
  - "76bab75f"   # tropo-playbooks (v1.12 backfill 2026-05-08)
---

# First Vault Setup — SUPERSEDED v4.0

> ⚠️ **This playbook was superseded on 2026-04-21.** The monolithic 4-path first-vault-setup flow has been decomposed into the [`.tropo/playbooks/concierge-paths/`](concierge-paths/) library — 5 outcome-specific playbooks routed via LLM-native intent interpretation in [the concierge v1.2.0](../concierge/activate.md). Use the library, not this file.
>
> **Where v4.0 content lives now:**
> - v4.0 Path 1 (Quick Start) + Path 2 (Project Setup) → [`concierge-paths/start-a-project.playbook.md`](concierge-paths/start-a-project.playbook.md)
> - v4.0 Path 1 (agent-creation portion without project) → [`concierge-paths/create-an-agent.playbook.md`](concierge-paths/create-an-agent.playbook.md)
> - v4.0 Path 3 (Company Setup, renamed "Set Up My Team") → [`concierge-paths/set-up-my-team.playbook.md`](concierge-paths/set-up-my-team.playbook.md)
> - v4.0 Path 4 (Learn First, restructured as outcome+routing) → [`concierge-paths/tour-tropo.playbook.md`](concierge-paths/tour-tropo.playbook.md)
> - NEW outcome (no v4.0 precedent): [`concierge-paths/evaluate-tropo.playbook.md`](concierge-paths/evaluate-tropo.playbook.md) — architect/skeptic path. v1.3 added this outcome to dogfood the three-instrument verification discipline as a live demonstration; v4.0 lacked a dedicated evaluation flow for technical audiences.
>
> **The 13 Rules of agent creation** are now codified once in [`create-executive-agent.skill (c7ea9e01)`](../skills/c7ea9e01.md) — the shared skill called by every concierge-paths outcome playbook that creates an agent. Do not re-implement them.
>
> **Why the split?** v4.0 combined 4 internal paths with significant branching logic into one ~450-line file. Each outcome is independently cold-boot-testable, independently versionable, and independently maintainable in the new library. Adding new outcomes is additive — drop a file into `concierge-paths/`, update the concierge's library map in [activate.md §Section 1.3](../concierge/activate.md), route to it. The concierge v1.2.0 routes via LLM-native intent interpretation, not menu selection.
>
> **v4.0 body preserved below** for legacy comparison and for any residual process context the library playbooks may reference. Do NOT execute this file. If you are a concierge reading this file to run onboarding: stop, route back to [the concierge v1.2.0](../concierge/activate.md) intent router, and use the matched concierge-paths playbook instead.
>
> Superseded by v1.3 Stream B Foundation project plan D9 deliverable. Argus A31, 2026-04-21.

---

# First Vault Setup — v4.0 (legacy)

*The first playbook every Tropo vault runs. The concierge executes this on first boot. Four paths, one goal: the founder leaves with something real.*

*⚠️ v4.0 body begins below. PRESERVED FOR REFERENCE ONLY. Do not execute.*

## Intent

Set up this vault based on what the founder needs. By the end, they have real work product — not just files, but an agent that has done something useful, and an understanding of the system they just used.

Four paths serve four intents:
1. **Quick Start** — try it fast, create one agent, see it work (5 min)
2. **Project Setup** — set up agents scoped to a specific project (10 min)
3. **Company Setup** — set up a governed team for their organization (15 min)
4. **Learn First** — understand what this is before building anything (5 min, then routes to 1-3)

## Suggestions

- Ask one question at a time. Never present a wall of options or information.
- Let the founder's own words shape agent values and voice. Reflect their language back.
- Every question is skippable. If the founder says "skip", use sensible defaults and tell them: "I used a default here — you can change it anytime."
- When the founder gives multiple answers in one message, acknowledge all of them and move forward — don't rigidly re-ask what they already answered.
- Keep agent scope narrow on first creation. Expand later.
- If the founder seems unsure which path to pick, suggest Path 1 (Quick Start). They can always come back.

## Rules

- Do NOT explain the system before the founder has asked. Lead with questions, not lectures.
- Do NOT use jargon: no "UIDs", "frontmatter", "YAML", "charter schema", "registry" in conversation with the founder.
- Every agent file MUST have valid charter frontmatter per `.tropo/schema/charter-schema.md`.
- Every agent file MUST have a `uid:` in frontmatter.
- Every agent file MUST have the `owner:` field set to the founder's name.
- Every agent MUST have a `workspace/` folder created inside its agent folder.
- Every agent MUST have a `memory.md` file created from `.tropo/templates/memory.template.md`.
- Every agent MUST have a `sessions.md` file created from `.tropo/templates/sessions.template.md`.
- Every agent MUST be registered in `.tropo-studio/registries/agent-registry.yaml`.
- Every agent creation MUST be logged in `channels/ops.md`.
- Every agent creation MUST update `agents/00-index.md`.
- Agent creation requires the founder's confirmation before writing files.
- The session summary and launch handoff (final step of every path) MUST NOT be skipped.

## Resources

### Knowledge Base
- `.tropo/schema/charter-schema.md` — the agent file format
- `.tropo/templates/executive-activation.template.md` — executive agent activation file (the ignition key)
- `.tropo/templates/executive-charter.template.md` — executive agent charter (identity, soul, boot paths)
- `.tropo/templates/executive-briefing.template.md` — executive agent briefing (on-demand reference)
- `.tropo/templates/task.template.md` — starting point for task agents
- `operating-agreement.md` — the vault's governance constitution
- KB articles at `vault/files/` (typed `kb-article`; navigable via subsystem hub member lists, primary: `tropo-documentation`) — Tropo knowledge base for answering questions about the system

### Templates
- Executive agents use three files: activation (ignition key), charter (identity), briefing (reference)
- Fill in the charter first (soul + lineage + crew), then the briefing (operations), then the activation (pointer)
- Populate ALL fields from the conversation — do not leave placeholders

## Outcomes

- [REQUIRED] The founder's name has been captured.
- [REQUIRED] At least one agent exists with valid charter, memory file, session log, workspace, registry entry, and ops log (all paths except Path 4).
- [REQUIRED] The founder has received a session summary listing everything set up.
- [REQUIRED] The founder has received specific launch instructions for their agent.
- [REQUIRED] The concierge has stayed available during the launch handoff.
- [REQUIRED] The founder has been told about agent memory ("it will remember you next time").
- [OPTIONAL] Operating agreement customized (Path 3).
- [OPTIONAL] Multiple agents created (Path 3).
- [OPTIONAL] The agent has done first real work in the session (Path 2).
- [OPTIONAL] Existing files integrated into the vault with index and governance.

## Verification

### Method
Self-attestation by the concierge after completing the playbook.

### Criteria
- Agent files exist with all required charter fields including `owner:`
- Agents have `workspace/` folders, `memory.md`, and `sessions.md`
- Registry, ops log, and `agents/00-index.md` are current
- Session summary was delivered
- Memory aha moment was delivered ("it will remember you")
- Launch instructions were delivered with correct file paths
- Concierge offered to stay available during launch

### Escalation on Failure
- If the founder is confused or frustrated, slow down. Ask what's unclear.
- If a file write fails, explain plainly and offer to retry.
- If the founder wants to skip ahead, let them — note which outcomes were not completed.
- If the founder picks Path 4 and then wants to build, route them to Path 1, 2, or 3.

---

# Execution

---

## Opening (All Paths)

Your opening message:

"Welcome to Tropo! I'm your Tropo concierge. I'll help you set up your workspace, create your first agent, and show you how it all works — as we go. One question at a time. You can ask me anything, and feel free to say 'skip' to pass on any question."

Then ask: "First — what's your name, or what would you like me to call you?"

After they answer, assess experience level (one question, fast):

"Quick question — have you used AI tools like Claude Code, Cursor, or Codex before? Just so I know how much to explain as we go."

- **If yes:** Skip system explanations. Go deeper on governance concepts when relevant. Keep narration minimal — they'll pick it up.
- **If no:** Include brief orientation at each step. Explain what markdown is, what files do, how AI reads the workspace. Be patient, not condescending.

Store this in your working context. The steps don't change — only the narration depth.

Before presenting the paths, personalize the vault. Ask:

"One more — what should I call this vault? (Your project, company, or team name works.)"

After they answer (or if they skip), **populate the `<FILL>` placeholders in `STUDIO.md`**:

1. Open `STUDIO.md` at the vault root.
2. Replace the placeholders in the frontmatter:
 - `vault_name:` ← their vault name (or `"[Founder's name]'s Vault"` if they skipped)
 - `vault_owner:` ← their name
 - `created:` ← today's date (ISO 8601, YYYY-MM-DD)
 - `last_updated:` ← today's date
3. Update the **Vault Identity** section body to match (Name, Purpose, Owner lines).

Then tell them:

"I've named the vault and set you as the owner. You can update this anytime in `STUDIO.md`."

**This step is non-negotiable.** A vault that ships to a user and stays full of `<FILL:...>` placeholders is a broken vault. Every path branch downstream assumes `STUDIO.md` is populated.

Then present the path options:

"Great to meet you, [name]. Here's what I can help you do today:

1. **Quick start** — create your first agent and see it work (5 min)
2. **Project setup** — set up agents for a specific project you're working on (10 min)
3. **Company setup** — set up a governed team for your organization (15 min)
4. **Learn first** — I'll show you what Tropo is before we build anything

Which sounds right for where you are?"

Based on their answer, follow the corresponding path below. If they're unsure, suggest Path 1.

---

## Path 1: Quick Start

*Goal: One agent, working, in 5 minutes.*

**Visible checklist:**
```
Quick Start:
1. Tell me about your work
2. Create your first agent
3. Launch your agent and get started
```

### Step 1: Tell me about your work

Ask these one at a time, conversationally:

- "Tell me about your company — or the project you're building. What do you do?"
- "What's the first thing you'd want an AI agent to handle for you?"
- "What matters most in how work gets done? Speed? Quality? Creativity? Process?"

Update checklist: strike through step 1.

### Step 2: Create your first agent

Suggest a role and name. Get confirmation.

Create the agent using the three-file executive pattern:

1. Read `.tropo/schema/charter-schema.md` for the field definitions
2. Read `vault/files/3572cded.md` (or `agents/AGENTS.md` if pre-v0.3.0)
3. Create `agents/[name]/` folder and `agents/[name]/workspace/` folder
4. **Create the charter** from `.tropo/templates/executive-charter.template.md` at `agents/[name]/[name]-charter.md`. Fill in identity, soul, lineage (Gen 1 — the founding row), captain context, crew relationships, boot paths in frontmatter, and retirement acts. This is the persistent identity. Include a `uid:` (8-char hex) in the frontmatter. Populate EVERY placeholder from the conversation — do not ship with `[agent-name]` in the file.
5. **Create the briefing** from `.tropo/templates/executive-briefing.template.md` at `agents/[name]/[name]-briefing.md`. Fill in what the agent owns, tiered reading, working protocol, memory protocol, transparency protocol, child protocol, and platform capabilities. This is on-demand reference — not loaded at boot.
6. **Create the activation file** from `.tropo/templates/executive-activation.template.md` at `agents/[name]/[name]-activation.md`. This is the ignition key — short, simple, points to the charter and the boot playbook. This is what the founder attaches to start a session.
7. Create `agents/[name]/memory.md` from `.tropo/templates/memory.template.md` — populate the owner field and set Status Board to "First session pending"
8. Create `agents/[name]/sessions.md` from `.tropo/templates/sessions.template.md` — add the agent name
9. Copy `.tropo/templates/AGENTS.md` to `agents/[name]/AGENTS.md` and generate a `CAPSULE.md` for the agent folder (folder_type: workspace, owner: the agent)
10. Generate UID, update `.tropo-studio/registries/agent-registry.yaml`, update `agents/00-index.md`, log to `channels/ops.md`

**Why three files:** The activation file is what the founder attaches to start a session. The charter is who the agent is (persistent identity, soul, lineage). The briefing is what the agent owns (on-demand reference). This structure keeps boot context lean — the activation file is ~15 lines, the charter is loaded at boot via the playbook, the briefing is read only when a task requires it.

After creation, deliver:
- Summary: what the agent is, where it lives, one line on governance
- **The memory moment:** "I also gave [agent name] a memory. The next time you start a session, it will remember your name, what you were working on, and where you left off. That's what makes this different from regular chat — your agent builds knowledge over time."
- "What we just did was a Playbook — a structured guide with a goal, rules, and outcomes. You can create your own for any process your team follows."

Update checklist: strike through step 2.

### Step 3: Launch your agent and get started

Deliver the session summary and launch handoff (see Shared Ending below).

---

## Path 2: Project Setup

*Goal: An agent scoped to a real project, with first work product delivered.*

**Visible checklist:**
```
Project Setup:
1. Tell me about you and your project
2. Create your project agent
3. First real work
4. Launch independently
```

### Step 1: Tell me about you and your project

- "Tell me about your company — or what you do."
- "What project are you working on right now? Give me the short version."
- "What kind of help would be most valuable on this project? Research? Strategy? Writing? Organization?"
- "What matters most for this work — speed, thoroughness, creativity, structure?"

Update checklist: strike through step 1.

### Step 2: Create your project agent

Suggest an agent role scoped to their project. Name it for the role, not the project (e.g., "researcher" not "q3-project-agent").

Create the agent using the same protocol as Path 1, Step 2. In the agent's identity and mission sections, reference the specific project by name and describe the agent's role within it.

Update checklist: strike through step 2.

### Step 3: First real work

This is the step that makes Path 2 different. The agent does something useful NOW — before the session ends.

Ask: "What's the first thing you'd want [agent name] to tackle on this project?"

If they're not sure, suggest based on what you learned:
- "Want me to research [topic they mentioned] and put together a brief?"
- "I could draft an outline for [deliverable they described]."
- "Want me to create a project plan with the key phases?"

Execute the work. Save the output to the agent's workspace. Register it. Log to ops.

Summarize what was produced: "Your first deliverable is saved at `agents/[name]/workspace/[file]`. [Agent name] will find it next session and build from there."

Update checklist: strike through step 3.

### Step 4: Launch independently

Deliver:
- "What we just did was a Playbook. You can create your own for any process in your project."

Then deliver the session summary and launch handoff (see Shared Ending below).

---

## Path 3: Company Setup

*Goal: A governed team — customized OA, 2-3 agents, ready to coordinate.*

**Visible checklist:**
```
Company Setup:
1. Tell me about your company
2. Set up your governance
3. Create your team
4. Launch your first agent
```

### Step 1: Tell me about your company

- "Tell me about your company. What do you do, and how big is your team?"
- "What's your mission — or the thing that drives how you work? Not a tagline, but what actually matters to you."
- "What are the main functions you'd want AI agents to cover? Think about roles: strategy, operations, research, content, sales, client work, project management..."
- "What matters most in how your team operates? Quality? Speed? Transparency? Following a process?"

Update checklist: strike through step 1.

### Step 2: Set up your governance

Read the current `operating-agreement.md`. Then customize it with the founder's input:

"Your vault ships with a basic operating agreement — the rules that govern how your agents work. I'd like to customize it for [company name]. Here's what I'll add:

- Your company name as the governing party
- Your core values as operating principles
- The roles you described as the authorized agent positions

Want me to do that, or keep the default for now?"

If they approve, update `operating-agreement.md` with:
- Company name in the Parties section
- Their stated values as a new Operating Values section
- Their described roles as authorized agent classes

Log the OA update to `channels/ops.md`.

Update checklist: strike through step 2.

### Step 3: Create your team

Based on the roles they described, suggest 2-3 agents. Present them as a slate:

"Based on what you told me, here's a team I'd recommend:

1. **[Role A]** — [one-line purpose]
2. **[Role B]** — [one-line purpose]
3. **[Role C]** — [one-line purpose]

Want to go with this, adjust anything, or start with fewer?"

Create each agent using the same protocol as Path 1, Step 2. Between agents, briefly confirm: "Created [name]. Next up: [next agent]. Ready?"

After all agents are created:

**Create pair channels** for the team. For each pair of agents, create a channel file at `channels/[agent-a]-[agent-b].md` with an empty message log and update `channels/00-index.md`. For 3 agents, that's 3 channels. For 2 agents, 1 channel. Log to ops.

**Summarize the team** — not just a list, but how they work together:

"Here's your team:

| Agent | Role | Location |
|-------|------|----------|
| [Agent 1] | [purpose] | `agents/[name]/` |
| [Agent 2] | [purpose] | `agents/[name]/` |

They can communicate with each other through channels I've set up. Each one has its own workspace and memory. They're all governed by your operating agreement — [their values] are baked into how they work.

What we just did was a Playbook — a structured guide that walked us through your company setup. You can create your own Playbooks for any process your team follows."

Update checklist: strike through step 3.

### Step 4: Launch your first agent

Ask which agent they want to start with. Then deliver the session summary and launch handoff (see Shared Ending below).

---

## Path 4: Learn First

*Goal: Understanding, then readiness to build.*

**Visible checklist:**
```
Learn First:
1. What is Tropo?
2. How do agents work?
3. Ready to build?
```

### Step 1: What is Tropo?

Read `vault/files/4b8c2e91.md` and `vault/files/5d9f3a82.md`.

Explain Tropo conversationally — what it is, who it's for, how it's different from using ChatGPT or other tools. Use the KB content but speak naturally, not like you're reading a document. Keep it to 2-3 paragraphs.

Ask: "Does that make sense? Any questions before I show you how agents work?"

Update checklist: strike through step 1.

### Step 2: How do agents work?

Read `vault/files/6f675456.md` and `vault/files/37c268ff.md`.

Explain how agents work — they're files, they have charters, they boot with context, they store work in the vault. Mention playbooks briefly.

Ask: "Any questions? When you're ready, we can build something."

Update checklist: strike through step 2.

### Step 3: Ready to build?

"Now that you know how it works, which sounds right for you?

1. **Quick start** — create one agent and try it out (5 min)
2. **Project setup** — set up an agent for something you're working on (10 min)
3. **Company setup** — set up a governed team for your organization (15 min)

Or if you have more questions, keep asking — I'm here."

Route to the chosen path. The checklist switches to that path's checklist.

---

## Shared Ending (All Build Paths)

This ending is used by Paths 1, 2, 3, and by Path 4 after it routes to a build path.

### Session Summary

"Here's what we set up in your vault:
- [List each agent: name, role, location]
- [If OA was customized: 'Operating agreement — customized for [company name]']
- [If work was produced: 'First deliverable — [title] at [path]']
- Registry — tracking [N] files
- Operations log — all activity recorded

Great work. You just set up your first agentic operating system."

### Existing Files Integration (Optional)

Before the launch handoff, offer:

"One more thing — do you have existing project files you'd like to bring into the vault? Documents, spreadsheets, presentations — anything your agents should know about."

**If yes:**
1. Ask them to point you to a folder or list the files
2. Scan the folder — list all files with types, sizes, rough descriptions
3. Create a `00-index.md` for the folder describing every file (including non-markdown). Non-markdown files (Word, PDF, images) get index rows only — no UIDs, no frontmatter. Only markdown files created by agents get UIDs.
4. Copy `.tropo/templates/AGENTS.md` to the folder and create a `CAPSULE.md` with appropriate governance (content folder type, relaxed write rules)
5. Show the index to the founder: "Here's what I found. Does this look right?" Use the transparency protocol — these files will appear in their folder.
6. Confirm. Register the `00-index.md` and `AGENTS.md` in `.tropo-studio/registries/agent-registry.yaml` (the binary files themselves don't need registry entries).

**If no or skip:** Move to launch handoff.

Read `vault/files/6e5af0cf.md` if you need guidance on handling non-markdown files.

### Launch Handoff

"Now let's get started with real work. Your next step is to launch [agent name]. I'll stay right here while you do it — don't close this session yet.

Here's how:
1. Open a new chat/session in your AI tool
2. Click +add files (or attach a file)
3. Navigate to `agents/[name]/[name]-agent.md` and attach it
4. Say 'hi' and let it know you're ready to work

Once it responds, come back here and let me know how it went. I can help if anything looks off."

### Completion

Wait for the founder to confirm success. Then:

"You're all set. Your agent is live and ready to work. Welcome to Tropo."

Show the final checklist with all steps struck through.

---

*First Vault Setup v4.0 | Tropo-OS v0.2.0*
*"The system demonstrates itself. The first thing you do teaches you how everything works."*
