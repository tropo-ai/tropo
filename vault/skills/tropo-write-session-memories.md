---
skill: write-session-memories
name: write-session-memories
type: how-to
purpose: Append session learnings to the episodic memory log
when: At retirement (Phase 2) or when capturing significant learnings mid-session
mode: inline
params:
  - memory_log_path
uid: 3f8c2d61
status: active
owner: argus
created: 2026-04-15
modified: 2026-06-14
modified_by: talos-t20
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: Reach for this at retirement (Phase 2) to capture session learnings before context closes — the mechanism by which knowledge survives generations. Appends JSONL entries to agents/<name>/.tropo-capsule/memory/agent-memories.jsonl (or override path). The curator later folds these into the agent's memory surface. Use mid-session when something material happens that the next generation MUST inherit.
subsystem_hub:
  - 99ed55fd
---

# Write Session Memories

Use this at retirement to capture what you learned before the context window closes. This is how knowledge survives generations.

## Steps

1. **Review your session.** Think about what you learned that a future agent should know. Categories:
 - **Feedback** — corrections or confirmations from the human ("Mike prefers X," "don't do Y")
 - **Semantic** — facts, definitions, or architectural truths discovered
 - **Procedural** — how-to knowledge, skills, or operational reflexes
 - **Reference** — pointers to canonical substrate or external resources

2. **Append to the memory log.** For each distinct learning, append a single JSON line to `{memory_log_path}` (default: `agents/<name>/.tropo-capsule/memory/agent-memories.jsonl`):

 ```json
 {"ts": "YYYY-MM-DD", "generation": "T<N>", "kind": "feedback|semantic|procedural|reference", "note": "Clear, concise statement of the learning. Lead with the rule/fact."}
 ```

3. **Apply the separation heuristic.** Before writing, ask: "Can I phrase this as 'the next agent should know X'?" If yes, it's a memory. If you can only phrase it as "what happened was Y," it's history — put it in the living transfer, not the memory log.

4. **Be direct.** Lead with the truth, then the rationale.
 - *Example:* `{"ts": "2026-06-14", "generation": "T20", "kind": "feedback", "note": "Don't propose retirement; Mike calls it directly. Why: context-load at the principal axis is a bottleneck."}`

## Success

- All material learnings from the session appended to `agent-memories.jsonl`.
- JSON lines are valid and use the correct `kind`.
- No routine history mixed into the memory log.
