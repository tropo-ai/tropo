---
status: deprecated
superseded_by: "executive-activation.template.md + executive-charter.template.md + executive-briefing.template.md"
deprecated_date: "2026-04-10"
deprecated_by: "vela-v25"
---

# executive.template.md — DEPRECATED

*This single-file executive template has been superseded. Executive agents now use a three-file structure.*

## Why the split

The old single-file template combined identity, boot procedure, operational reference, and retirement protocol into one 170+ line document. Every boot read the whole file whether the agent needed the reference sections or not. Proven ungovernable at scale: Metis's activation file grew to ~8,000 tokens with 7,700 tokens of reference material loaded at boot that was never used during work.

The three-file structure solves this:

- **`[agent]-activation.md`** (~15 lines) — The ignition key. Points to the charter and the boot playbook. This is what a human attaches to start a session.
- **`[agent]-charter.md`** (~180 lines) — The persistent identity. Soul, lineage, captain context, crew relationships, startup signal. Its frontmatter declares every path the boot playbook needs.
- **`[agent]-briefing.md`** (~130 lines) — On-demand operational reference. What the agent owns, working protocol, memory protocol, transparency protocol, child protocol, platform capabilities. Not loaded at boot — read when a task requires it.

## The new templates

- `executive-activation.template.md` — the ignition key
- `executive-charter.template.md` — the persistent identity
- `executive-briefing.template.md` — the operational reference

## When to use which

- **New executive agents:** start with all three templates. Fill in `executive-charter.template.md` first (the soul), then `executive-briefing.template.md` (the operations), then `executive-activation.template.md` (the pointer).
- **Migrating existing agents:** take the old monolithic activation file and split it along the charter/briefing lines. Identity, soul, lineage, crew, startup signal → charter. Working protocol, memory, transparency, child protocol, platform capabilities → briefing. The activation file becomes ~15 lines.
- **Non-executive agents (workers, grooming agents):** do not use the three-file structure. They don't have identity or lineage. A single activation file is correct for them.

## Why the activation file persists as a concept

The activation file is the human-facing entry point. It is the file a human attaches to a terminal session or names in a chat to begin work with an agent. It exists because the workflow needs a consistent name — you don't want to remember whether to attach `agent-charter.md` or `agent-soul.md`. The activation file stays, but shrinks to its essential role: a pointer that triggers the playbook-driven boot.

## The lineage of this decision

- April 5, 2026 — Boot Playbook Spec LOCKED. The boot procedure became a separate artifact from individual activation files.
- April 7, 2026 — Agent Lifecycle Architecture LOCKED (Identity / Mind / Craft). Three concerns named.
- April 9, 2026 — Metis G37 measured her boot: 17 reads, ~22,000 tokens, ~70% waste. Task 008bb233 opened.
- April 9, 2026 — Metis G38 became the first agent to boot from the new activation/charter/briefing structure. Mike confirmed "boot seemed excellent."
- April 10, 2026 — All five Argo executives migrated (Metis, Vela, Orpheus, Argus, Silas). The pattern validated across a full crew.
- April 10, 2026 — Starter template updated. The pattern ships.

---

*Deprecated template retained for reference. Do not use for new agents.*
*Vela V25, April 10, 2026.*
