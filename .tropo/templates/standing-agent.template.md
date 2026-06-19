---
# === CHARTER: COMMON FIELDS ===
agent_name: "[agent-name]"
agent_class: standing
status: pending
governor: "d.[director-name]"
purpose: "[One-line description of what this agent does]"

scope:
 reads:
 - "[paths this agent reads]"
 writes:
 - "[paths this agent writes]"

boot_protocol: activate-directives

created: "[YYYY-MM-DD]"
last_updated: "[YYYY-MM-DD]"

# === STANDING AGENT EXTENSIONS ===
director: "d.[director-name]"
schedule: "on-demand"
activation_trigger: "manual"
last_activated: null
---

# [Agent Name] — Activation File

## Purpose

[What does this agent do? Be specific. This is the complete instruction set — the agent reads this and knows its job.]

## Phone Home

On activation:
1. Read this file
2. Read Director's directives (`agents/directors/d.[director-name]/directives/`)
3. If directives changed since last activation, reconcile before executing
4. Execute task below
5. Log completion to event log

## Task

[Detailed instructions for what this agent does on each activation. Include:]

### Inputs
- [What files/data does this agent read?]

### Process
1. [Step 1]
2. [Step 2]
3. [Step 3]

### Outputs
- [What does this agent produce? Where does it write?]

### Completion
- Post to event log: `[COMPLETE] [agent-name] [output-path] | [description]`
