---
uid: <8-char-hex>
type: document
status: published
title: "<Vault Name> — Executive Dashboard"
description: "Hand-written executive dashboard with generated sections. Current state of all work, projects, vault health, standing rules."
owner: <primary-strategist-role>
created: <YYYY-MM-DD>
modified: <YYYY-MM-DD>
tags: [dashboard, executive, status]
file_ext: md
schema_version: 1
path: DASHBOARD.md
---

<!-- EXECUTIVE DASHBOARD TEMPLATE
 Tropo-OS | Ships in every vault at DASHBOARD.md

 This is a hybrid document: some sections are generated from source data,
 others are curated by a crew member (the owner). The source annotation
 on each section tells the generator which sections to rebuild and which
 to leave untouched.

 Hybrid model:
 generated — rebuilt from ledger queries, status cards, vault metrics.
 A generator (board-synthesizer, sub-agent, or the owner)
 can refresh these sections without reading the rest.
 curated — written by the owner. Requires judgment. A generator
 MUST NOT overwrite these sections. They persist across
 regenerations.

 Reading order for humans:
 1. Health line (is anything broken?)
 2. Decisions waiting (what do I need to act on?)
 3. What shipped (what happened?)
 4. What's blocked (what can't move?)
 5. Everything else (orientation, not urgency)

 The template ships in the product. Every vault gets a DASHBOARD.md.
 Small vaults: the human curates all sections manually.
 Scaled vaults: a generator refreshes the generated sections; the
 strategist curates the rest.
-->

# <Vault Name> — Executive Dashboard

*What's happening right now. Updated by <owner> at natural breakpoints.*

---

<!-- source: generated | from: vault/00-index.jsonl, vault health metrics -->
## System Health

<!-- One-line health indicator. Green = no blockers, no orphans, no stale boards.
 Yellow = maintenance items exist but nothing is broken.
 Red = structural problem requiring immediate attention.

 Below the indicator: key vault metrics in a compact line. -->

**<STATUS>** | <entry-count> entries | <orphan-count> orphans | <project-count> active projects | <capsule-status>

---

<!-- source: curated | owner writes and maintains -->
## Decisions Waiting on <Human>

<!-- FIRST SECTION after health. The human's action items.
 This section surfaces decisions that block crew work.
 Empty table is the goal state. -->

| Decision | Context | Blocking | Since |
|----------|---------|----------|-------|

---

<!-- source: curated | owner writes at session breakpoints -->
## Last 7 Days — What Shipped

<!-- Rolling 7-day window. Most recent first. Dated entries.
 Not just task completions — significant milestones, locked decisions,
 shipped artifacts, anything Mike should know about.
 Older entries age off when the window rolls. -->

---

<!-- source: curated | owner writes and maintains -->
## Blocked

<!-- What can't move and why. Requires judgment — not every backlog item
 is blocked. Only surface genuine blockers: dependency chains,
 waiting on external input, structural problems.
 Empty section = healthy. -->

| Item | Blocker | Owner | Since |
|------|---------|-------|-------|

---

<!-- source: generated | from: agent status cards, crew brief -->
## Active Work

<!-- One row per active crew member. What they're working on RIGHT NOW.
 Not their full task list — their current focus.
 Source: agent status cards + crew brief. -->

| Who | Role | Current Focus | Status |
|-----|------|---------------|--------|

---

<!-- source: curated | owner assesses -->
## Critical Path

<!-- One-line visual progression toward the next major milestone.
 The owner assesses where the project is and what's next.
 Format: milestone name, then a visual progress indicator. -->

---

<!-- source: generated | from: ledger query type=project, status=active -->
## Active Projects

<!-- All active projects with health indicators.
 Health = ratio of done tasks to total tasks, plus blocker presence.
 This is the drill-down surface — each project links to its board. -->

| Project | Owner | Tasks | Done | Health | Board |
|---------|-------|-------|------|--------|-------|

---

<!-- source: generated | from: vault/00-index.jsonl metrics -->
## Vault Health

<!-- Expanded metrics for the technical reader. Not needed for
 the 30-second executive scan — that's the health line at top.
 Useful for crew members assessing vault state at boot. -->

| Metric | Value |
|--------|-------|

---

<!-- source: curated | owner writes, rarely changes -->
## Standing Rules

<!-- Stable operational rules that apply across sessions.
 These change when Mike locks a new directive or when the
 crew discovers a pattern worth codifying.
 Not a dumping ground — each rule earns its place. -->

---

*<Vault Name> — Executive Dashboard | Owner: <owner> | Template: executive-dashboard.template.md*
