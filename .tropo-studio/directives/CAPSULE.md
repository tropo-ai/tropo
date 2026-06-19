---
spec_version: 2
tier: capsule
folder_type: governed
owner: vault-admin
write_access: [human-owner, vault-admin-delegate]
read_access: all
purpose: "Vault-level standing directives — instructions every agent in this vault reads at boot. One directive per file."
uid: 7724238f
---

# `.tropo-studio/directives/` — Standing Directives

## Purpose

Standing instructions to all agents in this vault. A directive is **crew-wide and persistent** — not a one-off task, not a channel message. If a behavior should apply to every agent at every boot, it belongs here.

Read by every executive agent at Group 2 Step 2.6 of the activation playbook (or per your vault's Tier 2 extension).

## What belongs here

- **Crew-wide operational patterns** — e.g., meta-feedback loop, clickable links invariant, pair-channel archival.
- **Standing guidance** that doesn't fit in operating-principles (too specific) or a playbook (no flow / action sequence).

Each directive is a standalone markdown file with minimal frontmatter (`uid`, `title`, `type: directive`, `status: active`, `owner`) and a body that declares: when it triggers, what to do, why it exists.

## What does NOT belong here

- **One-time tasks** — those go in your work management system (tasks, issues).
- **Agent-specific rules** — those go in the agent's charter or Tier 3 extension.
- **Action sequences with multiple steps** — those are playbooks (`playbooks/`).
- **Architectural decisions** — those are ADRs / decision records.

## Example

One shipped as reference: [`example.directive.md`](example.directive.md) — the Meta-Feedback Loop pattern (crew-tested on Argo). Read it as a template for authoring your own.

## Naming convention

`<slug>.directive.md` — slug is descriptive, lowercase, hyphen-separated.
