---
skill: tropo-memory-write
name: tropo-memory-write
type: how-to
purpose: Write a Tropo memory entry (agent/studio/doctrine scope) with correct frontmatter and index registration — friction-equal to a single harness write
when: Any time you want to pin a learning, discipline, observation, or substrate reference that should survive this session and port across harnesses
mode: inline
params:
  - scope
  - content
  - subtype
  - agent_slug
uid: 0b35633f
status: active
owner: talos
created: 2026-07-03
created_by: talos-t24
governed_by: a5b3c891
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: 'Reach for this whenever you want to pin a memory. One call with (scope, content) routes to the correct Tropo tier, authors valid memory.capsule frontmatter, appends the episodic log entry, and registers the file. Replaces the impulse to write to .claude/ or any harness-private store. Closes the authoring-friction gap that makes .claude/ the path of least resistance.'
subsystem_hub:
  - 99ed55fd
tags:
  - memory-sovereignty
  - memory-write
  - tropo-memory
  - extreme-portability
  - 8c015275
refs:
  - a5b3c891
  - 0b35633f
---

# tropo-memory-write — Write to Tropo Memory

Use this whenever you want to pin a memory. One call routes to the right Tropo tier with correct frontmatter. This is the structural alternative to writing to `.claude/` or any harness-private store.

**Why this exists:** Tropo's core promise is extreme work portability across agentic harnesses. Harness-private stores (`~/.claude/`, etc.) don't port, don't propagate to the next generation, and break that promise. This skill makes Tropo memory friction-equal to a harness write — so the right path is also the easy path. (OP-14; CLAUDE.md §Memory Writes; dev-spec 8c015275.)

---

## Parameters

| Param | Required | Values | Default |
|-------|----------|--------|---------|
| `scope` | yes | `agent` / `studio` / `doctrine` | — |
| `content` | yes | The memory body (markdown, plain prose) | — |
| `subtype` | no | `semantic` / `episodic` / `procedural` / `reference` / `feedback` | `semantic` |
| `agent_slug` | if scope=agent | e.g. `argus`, `talos`, `vela` | current agent |

---

## Scope → Path Mapping

| Scope | Path | Who reads it |
|-------|------|-------------|
| `agent` | `agents/<agent_slug>/.tropo-capsule/memory/entries/<uid>.md` | That agent at every boot |
| `studio` | `.tropo-studio/memory/entries/<uid>.md` | Every executive at every boot |
| `doctrine` | `vault/files/<uid>.md` (type: `memory`) | Vault-level; any agent via grep |

---

## Steps

1. **Choose scope.** Ask: "Should only I (this agent) know this? → `agent`. Should the whole crew know? → `studio`. Is this a binding OS-level rule? → `doctrine`."

2. **Generate a UID.** Run `python3 vault/tools/tropo-mint-id.py` to get a collision-checked 8-character hex UID (e.g. `3f8c2d61`).

3. **Determine the target path.**
   - `agent`: `agents/<agent_slug>/.tropo-capsule/memory/entries/<uid>.md`
   - `studio`: `.tropo-studio/memory/entries/<uid>.md`
   - `doctrine`: `vault/files/<uid>.md`

4. **Write the entry file** with this frontmatter template:

   ```yaml
   ---
   uid: <uid>
   type: memory
   subtype: <semantic|episodic|procedural|reference|feedback>
   scope: <agent|studio|doctrine>
   context: "<one-line situating context — what we were doing when this surfaced; ≤120 chars>"
   created: <YYYY-MM-DD>
   state: active
   tags: []
   ---

   <content body — clear, direct, lead with the rule/fact>
   ```

5. **Append to the episodic log** (`agents/<agent_slug>/.tropo-capsule/memory/agent-memories.jsonl` for agent scope; `.tropo-studio/memory/agent-memories.jsonl` for studio scope). Append one JSONL line:

   ```json
   {"ts": "YYYY-MM-DD", "generation": "<T-or-G-or-V-N>", "kind": "<subtype>", "uid": "<uid>", "note": "<brief statement of the learning; lead with the rule>"}
   ```

6. **Register in the vault index.** Run `python3 vault/tools/tropo-rebuild-index.py --apply` (or the full `python3 vault/tools/tropo-rebuild-vault.py --apply` for a comprehensive refresh). The rebuild automatically scans `.tropo-studio/memory/entries/` (studio scope) and `agents/*/.tropo-capsule/memory/entries/` (agent scope) since v1.79 — no manual index entry required.

7. **Do NOT write to `.claude/` or any harness-private path.** If the harness prompts you to save a memory, decline and route here instead.

---

## Quick Example — Agent-scope Feedback Pin

```yaml
---
uid: a3f2b918
type: memory
subtype: feedback
scope: agent
context: "Mike-T24 directed: don't propose retirement; Mike calls it directly"
pinned_by: [mike-maziarz]
created: 2026-07-03
state: active
tags: [mike-feedback, retirement-discipline]
---

Don't propose retirement. Mike calls the end of a session directly. Proposing retirement consumes context at the principal axis — the bottleneck. Work until Mike ends the session.
```

Write to: `agents/talos/.tropo-capsule/memory/entries/a3f2b918.md`

---

## Quick Example — Studio-scope Crew Knowledge

```yaml
---
uid: b7c1d293
type: memory
subtype: semantic
scope: studio
context: "Memory Sovereignty build (8c015275): canonical memory paths established"
created: 2026-07-03
state: active
tags: [memory-sovereignty, tropo-memory, routing]
---

Tropo memory routing rule (OP-14, v1.78.0): all substrate-class pins go to Tropo memory (agent/studio/doctrine scopes), never to .claude/ or harness-private stores. Abstraction: vault/skills/tropo-memory-write.md (0b35633f).
```

Write to: `.tropo-studio/memory/entries/b7c1d293.md`

---

## Success Criteria

- Entry file exists at the correct path for the chosen scope
- Frontmatter has all required fields (`uid`, `type: memory`, `subtype`, `scope`, `context`, `created`, `state`)
- Episodic log has a new JSONL entry timestamped today
- Vault index has a registration for the new UID
- ZERO new files written to `~/.claude/` or any harness-private location
