---
spec_version: 2
tier: capsule
folder_type: registry
owner: concierge
write_access: [concierge, human-owner]
read_access: all
purpose: "Agent files — one folder per agent"
naming: "[agent-name]/[agent-name]-agent.md"
lifecycle: permanent
uid: 208457f4
---

# agents/ — Agent Files

Every agent in the vault lives here. Each agent gets its own folder.

## Operating Logic

- One folder per agent, named for the agent: `agents/strategist/`
- The agent file lives at `agents/[name]/[name]-agent.md`
- All agent files must have charter frontmatter (see `.tropo/schema/charter-schema.md`)
- All agent files must have a `uid:` in frontmatter for registry tracking
- New agents require human owner approval
- Each agent folder includes a `workspace/` subfolder for that agent's working files
