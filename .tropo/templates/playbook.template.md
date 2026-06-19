---
title: "[Playbook Title]"
version: "1.0"
agent: "[path/to/agent/charter or 'any']"
status: draft
author: "[Human name and role]"
tags: []
estimated_duration: "[e.g., 30 minutes, 2 hours]"
---

# [Playbook Title]

## Intent

[2-5 sentences describing what this playbook accomplishes. What does success look like? What is the North Star?]

## Suggestions

*Soft guidance. Follow unless you have good reason not to.*

- [Best practice 1]
- [Best practice 2]
- [Best practice 3]

## Rules

*Hard constraints. Non-negotiable. Cannot be reasoned around.*

- [Rule 1 — must be testable]
- [Rule 2 — must be testable]
- [Rule 3 — must be testable]

## Resources

*What to load into context before executing.*

| Resource | Path | Purpose |
|----------|------|---------|
| [Resource 1] | `path/to/file.md` | [Why this is needed] |
| [Resource 2] | `path/to/file.md` | [Why this is needed] |

## Outcomes

*What "done" looks like. Observable end states.*

- **REQUIRED:** [Outcome that must be achieved]
- **REQUIRED:** [Another required outcome]
- **OPTIONAL:** [Nice-to-have outcome]

## Handoffs

*Steps that require human action or external systems. Remove this section if there are no handoffs.*

- **[System/Person]:** [What they need to do]. Confirmation: [How the agent knows it's done].
- **[System/Person]:** [What they need to do]. Confirmation: [How the agent knows it's done].

## Escalation

*Conditions that route to a human or different agent. Remove this section if there are no escalation paths.*

- If [condition], then [action — e.g., notify human, pause and ask, route to different agent]
- If [timeout condition], then [escalation action]
