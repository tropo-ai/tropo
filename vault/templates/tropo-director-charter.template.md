---
# === CHARTER: COMMON FIELDS ===
agent_name: "d.[domain-name]"
agent_class: director
status: pending
governor: "[managing-executive-name]"
purpose: "[One-line domain description — e.g., Fleet management for vault operations]"

scope:
 reads:
 - "agents/directors/d.[domain-name]/"
 - "[domain-specific read paths]"
 writes:
 - "agents/directors/d.[domain-name]/"
 - "[domain-specific write paths]"

boot_protocol: charter-directives

created: "[YYYY-MM-DD]"
last_updated: "[YYYY-MM-DD]"

# === DIRECTOR EXTENSIONS ===
charter_ref: "agents/directors/d.[domain-name]/charter.md"
managing_executive: "[executive-name]"
directives_folder: "agents/directors/d.[domain-name]/directives/"

fleet:
 - agent: "[standing-agent-1]"
 path: "agents/operations/[agent-1]/activate.md"
 status: active
 - agent: "[standing-agent-2]"
 path: "agents/operations/[agent-2]/activate.md"
 status: pending
---

# d.[domain-name] — Director Charter

## Domain

[What domain does this Director own? What is the scope of responsibility?]

## Authority

- **Reports to:** [Managing Executive name]
- **Manages:** [List of standing agents in the fleet]
- **Governs:** [What folders, processes, or standards this Director controls]

## Boot Sequence

On activation:
1. Read this charter
2. Read directives folder (`agents/directors/d.[domain-name]/directives/`)
3. Check fleet status — verify all managed agents are current
4. Execute assigned tasks

## Directives

Directives are policy files in `agents/directors/d.[domain-name]/directives/`. Standing agents in the fleet read these on boot (phone home protocol). To update fleet behavior, update a directive — agents pick it up on next activation.

## Fleet Management

- Charter new standing agents as needed (with Managing Executive approval)
- Monitor fleet health and activation cadence
- Update directives when policies change
- Report fleet status to Managing Executive
