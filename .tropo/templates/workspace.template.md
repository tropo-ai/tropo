---
team_name: "[Team Name]"
team_type: functional
lead: "[human or agent name]"
members: []
created: "[YYYY-MM-DD]"
---

# [Team Name] — Team Charter

## Purpose

[What this team does. 1-2 sentences.]

## Members

| Name | Role | Type |
|------|------|------|
| [name] | [role] | human / agent |

## Workspace Structure

```
workspaces/[team-name]/
 +- team.md <- this file
 +- internal/ <- shared work (team-scoped)
 | +- 00-index.md
 +- published/ <- finished artifacts (read-only to outside)
 | +- 00-index.md
 +- inbox/ <- inbound requests (write-by-anyone)
 | +- 00-index.md
 +- standup/ <- daily status (read-only to outside)
```

## Interfaces

- **Internal:** Team members read and write. Others have no access.
- **Published:** Team members write. Others read only.
- **Inbox:** Others write requests. Team triages and routes.
- **Standup:** Members post daily. Others read only.
