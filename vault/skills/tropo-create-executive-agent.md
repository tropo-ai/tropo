---
skill: create-executive-agent
name: create-executive-agent
type: how-to
purpose: Create an end-user executive agent using the three-file pattern (charter + briefing + activation). Codifies the 13 Rules from first-vault-setup.playbook.md v4.0.
when: Called by any concierge-paths playbook that creates an end-user agent (start-a-project, create-an-agent, set-up-my-team). Not for Argo crew agents (those use the thin-loader pattern at agent-configurator.capsule v2.1).
uid: c7ea9e01
owner: argus
created: 2026-04-21
created_by: argus-a31
modified: 2026-07-19
modified_by: argus-a135
aligned_with: e7b3c509
status: active
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: Reach for this when a concierge-paths playbook (start-a-project, create-an-agent, set-up-my-team) needs to create an end-user executive agent — uses the three-file pattern (charter + briefing + activation) and applies the 13 Rules codified from first-vault-setup.playbook.md v4.0. NOT for Argo crew agents — those use the thin-loader pattern at agent-configurator.capsule v2.1. The skill is called BY playbooks; it is not a playbook itself.
subsystem_hub:
  - 99ed55fd
---

# Create an Executive Agent (End-User)

*The end-user agent creation protocol. Extracted from [first-vault-setup.playbook.md v4.0](../playbooks/first-vault-setup.playbook.md) Path 1 Step 2. Every outcome-playbook in `.tropo/playbooks/concierge-paths/` that creates an agent calls this skill. Codify once; prevent drift across the library.*

---

## When To Use

Call this skill when:
- A concierge-paths outcome-playbook needs to create an end-user executive agent (the founder's agent, a project agent, a team member agent).

Do NOT use this skill for:
- **Argo crew agents** (Argus, Vela, Metis, Orpheus, etc.) — those use the thin-loader pattern governed by [agent-configurator.capsule v2.1 (3210818a)](../capsules/agent-configurator.capsule.md). The two patterns coexist intentionally (see §End-User vs Crew Standard below).
- Task agents, grooming agents, directors, sa.* session agents — those have their own capsules.

---

## Inputs (from the calling playbook)

Before calling this skill, the playbook must have gathered from the user:

| Input | Format | Example |
|---|---|---|
| `founder_name` | string | `"Sarah Chen"` |
| `agent_name` | string, lowercase-hyphen | `"researcher"`, `"coordinator"`, `"editor"` |
| `agent_role` | string, human-readable | `"Research and brief synthesis for client proposals"` |
| `agent_mission` | string, 1–2 sentences | What the agent will actually do |
| `agent_values` | string or bullets, in founder's voice | What matters most in how this agent works |
| `project_context` (optional) | string | Scope, project name, company name — for scoped agents |

If any required input is missing, append `[QUERY]` to the calling record and ask the founder. Do not invent.

---

## The Three-File Pattern (End-User Standard)

Every executive agent is three files inside `agents/<name>/`:

1. **`<name>-activation.md`** — the **ignition key**. ~15 lines. The file the founder attaches to start a session. Points at the charter and the boot playbook. Short by design — minimizes boot-context overhead.
2. **`<name>-charter.md`** — **identity**. Soul, role, lineage, crew relationships, boot paths, retirement acts. Loaded at boot. This is who the agent IS.
3. **`<name>-briefing.md`** — **on-demand reference**. What the agent owns, tiered reading, working protocol, memory protocol, platform capabilities. NOT loaded at boot; read only when a task requires it.

**Why three files.** The founder can see the agent's identity (charter) in one file — visible, legible, non-engineer-friendly. Operational detail (briefing) stays out of boot context until needed. The activation file is the thin pointer that survives across sessions.

### Templates

Use the templates in `vault/templates/`:
- `vault/templates/tropo-executive-charter.template.md` → fills `<name>-charter.md`
- `vault/templates/tropo-executive-briefing.template.md` → fills `<name>-briefing.md`
- `vault/templates/tropo-executive-activation.template.md` → fills `<name>-activation.md`

Populate EVERY `[placeholder]` in each template from the conversation inputs. Do not ship with `[agent-name]` or `[FILL:...]` in the file.

---

## The 13 Rules (verbatim from first-vault-setup v4.0)

These rules are the covenant. Every agent creation satisfies them.

**Conversation discipline** (owned by calling playbook, not this skill — preserved here for completeness per the plan's "no silent drops" criterion):

1. Do NOT explain the system before the founder has asked. Lead with questions, not lectures.
2. Do NOT use jargon: no "UIDs", "frontmatter", "YAML", "charter schema", "registry" in conversation with the founder.
13. The session summary and launch handoff (final step of every path) MUST NOT be skipped.

**Agent-creation rules** (owned by this skill — enforce at every call):

3. Every agent file MUST have valid charter frontmatter per [`.tropo/schema/charter-schema.md`](../schema/charter-schema.md).
4. Every agent file MUST have a `uid:` in frontmatter (8-char hex, generated with `openssl rand -hex 4` or equivalent).
5. Every agent file MUST have the `owner:` field set to the founder's name.
6. Every agent MUST have a `workspace/` folder created inside its agent folder at `agents/<name>/workspace/`.
7. Every agent MUST have a `memory.md` file created from `vault/templates/tropo-memory.template.md`.
8. Every agent MUST have a `sessions.md` file created from `vault/templates/tropo-sessions.template.md`.
9. Every agent MUST be registered in `.tropo-studio/registries/agent-registry.yaml`.
10. Every agent creation MUST be logged to the crew event log via `tropo-emit-event.py --type tropo.broadcast.crew` (`channels/ops.md` was retired v1.61 — the event log is the crew-communication surface).
11. Every agent creation MUST be reflected in the vault index (`vault/00-index.jsonl`) via `tropo-rebuild-vault.py` (`agents/00-index.md` was retired v1.74 — the JSONL index is the discovery surface).
12. Agent creation requires the founder's confirmation BEFORE writing files. Show the slate: "Here's what I'll create — [agent name], [role], three files + workspace + memory + session log. OK to proceed?" Wait for yes.

---

## Steps

Run these in order. Every step maps to one or more Rules.

### 1. Read required schemas and governance (Rule 3)

Before authoring:
- `.tropo/schema/charter-schema.md` — the required charter frontmatter fields
- `vault/files/3572cded.md` (or `agents/AGENTS.md` if pre-v0.3.0) — folder-level governance for where new agents may be created

### 2. Get founder confirmation (Rule 12)

Show the slate in user voice (no jargon per Rule 2):

> "Here's what I'll create: an agent called **[name]** to handle **[role]** for you. Three files, a workspace, a memory, a session log. About 30 seconds. OK to go?"

Wait for yes. If the founder wants to rename or adjust scope, re-show the slate before proceeding.

### 3. Mint three distinct UIDs (Rule 4)

Mint one UID **per governed file** — charter, briefing, and activation each carry their own:

```bash
python3 vault/tools/tropo-mint-id.py --count 3 --kind file --reason "new executive agent <name>"
```

Record which UID belongs to which file. They are three governed entries that point at each other,
not one entry written three times.

*Until 2026-08-13 this step told the author to generate ONE UID and put it in all three files, and
step 7 restated that instruction in the activation file's frontmatter line. Following it
literally made a newcomer's first `tropo-rebuild-index.py --apply` abort on a duplicate-UID
collision — the index treats one UID in three files as exactly the corruption it is. The agent is
one entity; its identity is carried by the charter's UID and the pointers between the files, not by
reusing an address. The shipped example agent already used distinct UIDs, so the instruction was the
stale side (v1.86 cold-walk finding 3, `ae5e743c`; fixed under locked dev-spec `e52826c5`).*

### 4. Create the agent folder and workspace (Rule 6)

- `mkdir -p agents/<name>/workspace/`

### 5. Create the charter (Rules 3, 4, 5)

Path: `agents/<name>/<name>-charter.md`. Copy from `vault/templates/tropo-executive-charter.template.md`. Fill in:

- Frontmatter: `uid:` (the charter's **own** UID from step 3), `owner:` (founder's name), `agent_name:`, `role:`, `created:` (today), plus every other required field from `charter-schema.md`
- Body: identity, soul paragraph (use founder's words from `agent_values`), lineage (this is generation 1 — the founding row), captain context (who the founder is and how they work), crew relationships (empty for solo agent, populated for team agents), boot paths, retirement acts

Populate EVERY placeholder. Zero `[FILL:...]` and zero `[agent-name]` survive to the written file.

### 6. Create the briefing

Path: `agents/<name>/<name>-briefing.md`. Copy from `vault/templates/tropo-executive-briefing.template.md`. Fill in:

- Frontmatter: `uid:` (the briefing's **own** UID from step 3 — distinct from charter and activation)
- What the agent owns (scope, deliverables)
- Tiered reading (what to read at boot vs on-demand)
- Working protocol (how the agent approaches work)
- Memory protocol (how the agent maintains `memory.md`)
- Transparency protocol (how the agent reports progress)
- Child protocol (whether the agent may spawn sub-agents; default no for end-user agents)
- Platform capabilities (Claude Code, Cursor, Codex — whatever the founder uses)

### 7. Create the activation file

Path: `agents/<name>/<name>-activation.md`. Copy from `vault/templates/tropo-executive-activation.template.md`. Fill in:

- Frontmatter: `uid:` (this file's **own** UID from step 3 — never the charter's; three governed files carry three distinct UIDs or the first index rebuild aborts on collision), pointer to charter, pointer to boot playbook
- Body: §Who You Are + §How to Boot + **§Routing** (concierge-bounce rules — present in the template by default per [playbook.capsule v2.3 §Subtypes §Concierge-Paths (`e7b3c509`)](../capsules/playbook.capsule.md)). The §Routing section is verbatim from the template; replace `[Founder Name]` placeholders, do not edit the bounce rules themselves. The bounce rules are the structural enforcement of D4.9 — they keep system primitives (projects / agents / teams / updates) under canonical playbook governance instead of drifting into agent-inline handling.

### 8. Create memory.md (Rule 7)

Path: `agents/<name>/memory.md`. Copy from `vault/templates/tropo-memory.template.md`. Populate:
- `owner:` — founder's name
- Status Board → "First session pending"

### 9. Create sessions.md (Rule 8)

Path: `agents/<name>/sessions.md`. Copy from `vault/templates/tropo-sessions.template.md`. Populate:
- Agent name in the header

### 10. Create the agent folder's AGENTS.md + CAPSULE.md

- Copy `vault/templates/AGENTS.md` to `agents/<name>/AGENTS.md` (identical in every folder — do not modify)
- Generate a `CAPSULE.md` for `agents/<name>/` with `folder_type: workspace`, `owner: <agent-name>`, `write_access: [<agent-name>, <founder>]`

(If the [tropo-create-governed-folder](tropo-create-governed-folder.md) skill is available, call it instead of doing this by hand — same result, less duplication.)

### 11. Register in the vault registry (Rule 9)

Add an entry under the `user_agents:` map in `.tropo-studio/registries/agent-registry.yaml`. The registry is a **map keyed by messaging UID** (use the charter UID from step 3; do not reuse it in another file) — the value is an indented block:
```yaml
user_agents:
  <uid-from-step-3>:
    class: personal            # end-user founder agent (crew/personal/worker/service)
    name: "<Agent Name>"
    type: executive
    purpose: "<role (human-readable)>"
    status: active
    path: agents/<name>/<name>-activation.md
    owner: <founder-name>
    commissioned: <today>
```

One entry per agent (the agent is one entity across its three files — do not add separate rows for the briefing/activation). Check existing `user_agents:` entries for the exact field set your Studio uses.

### 12. Refresh the vault index (Rule 11)

Rebuild the JSONL discovery index so the new agent resolves (`agents/00-index.md` was retired v1.74):
```bash
python3 vault/tools/tropo-rebuild-vault.py --only <uid>   # or a full rebuild
```
Confirm the agent is present in `vault/00-index.jsonl`.

### 13. Log the creation to the crew event log (Rule 10)

Emit a crew broadcast (`channels/ops.md` was retired v1.61 — the event log is the crew surface):
```bash
python3 vault/tools/tropo-emit-event.py --type tropo.broadcast.crew \
  --source /skills/create-executive-agent --source-uid c7ea9e01 --lifecycle ephemeral \
  --data '{"headline": "Created executive agent <name>", "body": "agents/<name>/ · UID <uid> · owner <founder-name> · role <role>"}'
```

---

## Validation Checks

After creating the agent, before reporting success, verify:

1. `agents/<name>/` exists as a folder
2. `agents/<name>/workspace/` exists as a folder
3. `agents/<name>/<name>-charter.md`, `<name>-briefing.md`, `<name>-activation.md` all exist
4. Charter, briefing, and activation carry three distinct `uid:` values, and their pointer fields resolve to one another
5. Every file has `owner: <founder-name>` in frontmatter
6. `agents/<name>/memory.md` exists with `owner:` populated
7. `agents/<name>/sessions.md` exists with agent name
8. `agents/<name>/AGENTS.md` and `agents/<name>/CAPSULE.md` exist
9. `.tropo-studio/registries/agent-registry.yaml` has at least one entry for this agent
10. `vault/00-index.jsonl` contains the new agent's entry (after `tropo-rebuild-vault.py`) — the current discovery surface (`agents/00-index.md` retired v1.74)
11. A `tropo.broadcast.crew` creation event was emitted (verify with `tropo-query-events.py`) carrying the correct UID (`channels/ops.md` retired v1.61)
12. Zero `[FILL:...]` or `[agent-name]` placeholders survive in any authored file
13. **`agents/<name>/<name>-activation.md` contains a non-empty `## Routing` section** (D4.9 / [playbook.capsule v2.3 §Subtypes §Concierge-Paths](../capsules/playbook.capsule.md)). The section MUST list at minimum the four bounce intents (project creation / team setup / new standalone agent / system updates) and one inline-handling clause. Validation: grep the activation file for `^## Routing$` heading + ≥ 4 bounce-bullets in the section body. If missing or partial, the template was not copied correctly or was edited away — halt and re-copy from `vault/templates/tropo-executive-activation.template.md`.

If any check fails, halt and report the specific check number to the calling playbook. The calling playbook decides whether to retry or escalate to the founder.

---

## Success

- Three-file agent exists at `agents/<name>/` with valid charter, briefing, activation
- Workspace, memory.md, sessions.md, AGENTS.md, CAPSULE.md all present
- Registered in agent-registry.yaml; present in vault/00-index.jsonl; creation event emitted to the crew log
- All 13 validation checks pass (see §Validation Checks above)
- Every one of the 10 agent-creation Rules (3–12) is satisfied

The calling playbook then resumes with post-creation work (memory-moment narration, launch handoff, etc.) — that's playbook scope, not skill scope.

---

## Template Adaptation Notes

The templates referenced above (`executive-charter.template.md`, `executive-briefing.template.md`, `executive-activation.template.md`, `memory.template.md`, `sessions.template.md`) were originally designed to cover both crew agents (Argus, Vela, Metis, etc.) and end-user agents. They carry some crew-oriented content by default. When creating an END-USER agent via this skill, the concierge-paths caller SHOULD:

1. **Charter template — "Boot Sequence" body section.** The charter template body includes a "Boot Sequence" numbered list (steps 1–7). This is a simplified boot sequence a human can read; it coexists with the separate `[agent]-activation.md` file (which is the ignition key the founder attaches). Leave the charter's Boot Sequence in place but note to the founder (at Step 5 narration) that they don't need to understand it — the activation file + boot playbook handle activation automatically.

2. **Charter vocabulary mapping.** The charter template body uses headings "Identity / Mission / Boot Sequence / Operating Principles / Retirement Protocol." Step 5 of this skill uses conceptual vocabulary ("soul paragraph, lineage, captain context, crew relationships, boot paths, retirement acts"). These map as follows when filling in the template:
 - **soul paragraph** → fills in under "# [Agent Name] — Activation File" H1 (the 2-3 sentence identity paragraph) + the Identity section
 - **lineage** → fills in the `lineage_note:` frontmatter field + any narrative in Identity section
 - **captain context** → fills in Mission section (who the founder is and what success looks like)
 - **crew relationships** → for solo end-user agents, typically empty or single-line ("Solo agent — reports to [founder-name] directly")
 - **boot paths** → already handled by the `boot_protocol: full` frontmatter field — no body content needed
 - **retirement acts** → fills in the Retirement Protocol body section

3. **Charter frontmatter paths — `generation_log`, `briefing_package`, `living_transfer`.** These point to crew-infrastructure paths (generation-log.md, briefing-package/ folder, transfers/living-transfer.md). End-user agents typically don't need generation tracking or briefing packages. For end-user agents, these fields MAY be left at template defaults (paths that would be valid if ever created) or set to `null` — the agent does not use them at boot and the paths resolve on-demand if the founder ever creates them. A v1.4 template amendment will split end-user vs crew templates; v1.3 uses this adaptation note.

4. **Briefing template — "Files you maintain."** The briefing template lists crew-oriented files (`[agent]-status.md`, `generation-log.md`, `transfers/living-transfer.md`, `boards/board-*/current.md`). For end-user agents, adapt to the founder's actual files — typically just `agents/[name]/memory.md` + `agents/[name]/sessions.md` + `agents/[name]/workspace/`.

**Why these adaptations exist.** The three-file pattern (charter + briefing + activation) is correct for end-user agents. The template CONTENT at v1.3 is crew-oriented because the templates predate end-user-specific needs. v1.3 ships the skill + adaptation notes; v1.4 or later splits the templates into end-user-specific variants. This gap is tracked in §Known Gaps below.

---

## Known Gaps (v1.3 — resolved in v1.4)

- **End-user-specific template variants not yet shipped.** Templates are crew-oriented by default; concierge-paths consumers adapt per §Template Adaptation Notes above. v1.4 Pillar 2 or Stream B Phase 2 delivers `executive-charter-enduser.template.md`, `executive-briefing-enduser.template.md`, `executive-activation-enduser.template.md` with end-user-appropriate content.
- **Mechanical validation of the 13 Validation Checks not shipped.** Validation is honor-system for v1.3; a later cycle ships a validator running the 13 checks mechanically at check-in.
- **Registry convention — all-three-files vs charter-only.** This skill's Step 11 leaves the choice to the vault's registry CAPSULE. v1.4 standardizes on registering all three files (charter, briefing, activation) per agent.

---

## End-User vs Crew Standard

This skill governs **end-user agent creation** via the three-file pattern. Argo crew agents use the **thin-loader pattern** per [agent-configurator.capsule v2.1 (3210818a)](../capsules/agent-configurator.capsule.md). The two patterns are deliberately distinct:

| Dimension | End-user (this skill) | Argo crew (thin-loader) |
|---|---|---|
| **Files** | Three: charter + briefing + activation | One activation file + Tier 3 boot extension |
| **Audience** | Non-engineer founders who need the agent's identity visible in one file | Sophisticated crew who boot through a three-tier chain |
| **Boot chain** | Charter + briefing loaded directly | Three-tier chain (OS → vault → agent), soul-first pattern |
| **When to use** | Created via concierge-paths outcome playbooks | Created via agent-configurator capsule |

The patterns are NOT competing. End-user agents are legible; crew agents are compositional. Keep them apart.

If a caller asks which pattern to use for their agent, default to this skill (end-user). Only crew-scope architectural work uses thin-loader, and that's gated on the agent-configurator capsule, not this skill.

---

## Related

- [playbook.capsule v2.0 (e7b3c509)](../capsules/playbook.capsule.md) — governs the playbooks that call this skill
- [first-vault-setup.playbook.md v4.0](../playbooks/first-vault-setup.playbook.md) — the source this skill was extracted from (currently active; superseded by concierge-paths library at v1.3 ship close)
- [agent-configurator.capsule v2.1 (3210818a)](../capsules/agent-configurator.capsule.md) — the crew-side counterpart (do not mix)
- [charter-schema.md](../schema/charter-schema.md) — the required charter frontmatter
- [tropo-create-governed-folder.md](tropo-create-governed-folder.md) — reusable sub-skill for folder+CAPSULE+AGENTS.md creation
- [tropo-register-file.md](tropo-register-file.md) — reusable sub-skill for agent-registry.yaml updates

---

*create-executive-agent skill | v1.0 | Argus A31 | 2026-04-21*
*D2 deliverable of v1.3 Stream B Foundation project plan. Extracts the 13 Rules from first-vault-setup.playbook.md v4.0 into reusable form for the concierge-paths outcome-playbook library.*
*"The covenant stays in one place. Every playbook that creates an agent references the covenant. Drift cannot begin."*
