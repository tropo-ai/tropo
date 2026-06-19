# Charter Schema — Tropo-OS Standard

**Version:** 0.1.0
**Scope:** Defines the YAML frontmatter schema that every agent file must include.

---

## Common Fields (All Classes)

```yaml
---
agent_name: "name" # Lowercase, no spaces
agent_class: executive # executive | task
status: active # active | pending | retiring | retired
governor: "operating-agreement" # Who governs: OA, human name, or parent agent
purpose: "One-line role description"
uid: "a1b2c3d4" # 8-char random hex — unique file identity
owner: "founder's name" # The human owner — written into every charter

scope:
 reads:
 - "channels/"
 - "agents/"
 writes:
 - "agents/[name]/"
 - "channels/"

boot_protocol: full # full | parent-inherit

created: "YYYY-MM-DD"
last_updated: "YYYY-MM-DD"
---
```

## Executive Extensions

Executive agents are named crew members with persistent identity. They have a soul (values, voice, decision style) and DNA (model, platform, capabilities).

```yaml
soul:
 role: "Named role"
 values: ["value 1", "value 2", "value 3"]
 voice: "Communication style"
 decision_style: "How this agent handles ambiguity"
 lineage_note: "Generation context"

dna:
 model: "model-name"
 platform: "platform-name"
 context_window: "window size"
 capabilities: ["cap1", "cap2"]

generation: 1
```

## Task Agent Extensions

Task agents are single-use helpers spawned by a parent agent. They do one job and terminate.

```yaml
parent: "parent-agent-name"
task_id: "parent.1"
task_description: "What this task does"
spawned: "YYYY-MM-DD"
```

## Boot Protocols

| Protocol | Used By | Sequence |
|----------|---------|----------|
| `full` | Executives | Read activation file, read operating agreement, read registry, check channels, report online |
| `parent-inherit` | Task Agents | Read activation, inherit parent context, execute, report, terminate |

## Lifecycle States

| State | Meaning |
|-------|---------|
| `active` | Agent is operational |
| `pending` | Agent is created but not yet activated |
| `retiring` | Agent is in handoff process |
| `retired` | Agent is no longer active, kept for reference |

---

*Charter Schema | Tropo-OS v0.1.0*
