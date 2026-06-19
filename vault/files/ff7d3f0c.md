---
uid: ff7d3f0c
type: document
status: published
state: active
title: "Green City — Concept Note: The Ridgewood Solar Pilot"
description: "Initial idea capture: can governed AI agents coordinate a neighborhood solar pilot from permit to power-on?"
owner: mike
member_of: [9b74ffe5]
created: 2026-04-16
modified: 2026-04-16
tags: [ideate, concept-note, green-city, scope-ship]
file_ext: md
schema_version: 2
extraction_scope: ship
scope: ship
created_by: metis-g42
---

# Concept Note: The Ridgewood Solar Pilot

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Library](1aba710c.md) → [Packs](d9b8a9bb.md) → [Green City Energy — The Ridgewood Pilot](9b74ffe5.md) → **Green City — Concept Note: The Ridgewood Solar Pilot**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/agentic-builders/Packs/Green City Energy — The Ridgewood Pilot/ff7d3f0c — Green City — Concept Note- The Ridgewood Solar Pilot.md](../../00-tropo-nav/00-tropo-active/agentic-builders/Packs/Green%20City%20Energy%20%E2%80%94%20The%20Ridgewood%20Pilot/ff7d3f0c%20%E2%80%94%20Green%20City%20%E2%80%94%20Concept%20Note-%20The%20Ridgewood%20Solar%20Pilot.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-active/agentic-builders/Packs/Green City Energy — The Ridgewood Pilot/ff7d3f0c — Green City — Concept Note- The Ridgewood Solar Pilot.md](argo-os/00-tropo-nav/00-tropo-active/agentic-builders/Packs/Green%20City%20Energy%20%E2%80%94%20The%20Ridgewood%20Pilot/ff7d3f0c%20%E2%80%94%20Green%20City%20%E2%80%94%20Concept%20Note-%20The%20Ridgewood%20Solar%20Pilot.md)

**🔗 This file** — UID `ff7d3f0c` · type `document` · state `active` · status `published`

**↔ Siblings (9):**
  - **under [Green City Energy — The Ridgewood Pilot](9b74ffe5.md):** [Build vendor shortlist — three qualified instal...](e2ae8e49.md) · [Complete household consent documentation — all ...](b400ea7a.md) · [Green City Energy — Ridgewood Pilot Board](7e766fde.md) · [Green City — Agent Coordination Model for the R...](ac231d58.md) · [Green City — Ridgewood Pilot Agent Architecture...](8fbfe701.md) · [Permit Research Agent — Charter](3cebbcde.md) · + 3 more
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [Green City Energy — The Ridgewood Pilot (9b74ffe5)](9b74ffe5.md) |

*Stage: Ideate | Green City Energy | April 2026*

---

## The Idea

Ridgewood has a problem every neighborhood has: distributed solar is economically compelling for individual households, but the coordination overhead — permits, vendor selection, installation scheduling, utility interconnection — is enough to stop most people before they start. The process that should take six weeks takes six months. Families who want to participate give up.

Green City Energy's hypothesis: **if you govern the coordination with AI agents, you collapse the overhead without sacrificing quality or compliance.**

Not agents that make decisions for households. Agents that do the research, track the paperwork, coordinate the vendors, and flag the issues — so the humans can focus on the decisions that require them.

---

## The Opportunity

**The coordination tax is the bottleneck.** A qualified installer can do the technical work. A motivated homeowner can sign the paperwork. What neither can easily do is track the seventeen interdependencies between permit status, utility approval, vendor scheduling, and equipment delivery — simultaneously, for ten households, without things falling through the cracks.

That is the work AI agents are built for.

**The governance model matches the stakes.** Distributed energy is regulated. Permits matter. Contracts matter. A mistake in a permit application doesn't just delay one household — it can invalidate a batch. The coordination must be accurate, auditable, and recoverable when something goes wrong.

This is not a domain for ungoverned agents that "slog fish into barrels and some fall out." Every action must be traceable. Every agent must know exactly what it's authorized to do.

---

## The Proposed Approach

Three governed agents, each with a declared scope:

1. **Permit Research Agent** — owns the regulatory layer. Researches requirements, tracks applications, flags compliance issues. Touches nothing outside `ridgewood/permits/`.

2. **Vendor Coordination Agent** — owns the vendor layer. Manages the shortlist, tracks quotes and timelines, flags conflicts. Touches nothing outside `ridgewood/vendors/`.

3. **Customer Onboarding Agent** — owns the household layer. Manages consent, paperwork, and the customer-facing experience. Touches nothing outside `ridgewood/customers/`.

Each agent retires and hands off to a successor. The institutional memory — what was researched, what was agreed, what is pending — transfers in the living document, not in the agent's memory.

---

## Why Governance Is Not Optional Here

When the Permit Research Agent discovers that Ridgewood County requires a specific fire suppression addendum that most installers miss, that finding needs to reach the Vendor Coordination Agent so vendor selection accounts for it. But the permit agent should not be modifying the vendor shortlist. The finding needs to travel through a governed handoff — a channel post, a vault entry — not through an agent acting outside its scope.

This is the architecture. Not because the agent is incapable of touching the vendor files. Because the governance is the product.

---

## Next Step

Write the design brief. Define the agent coordination model precisely — what each agent owns, what the handoff protocols are, how the agents communicate without communicating directly.

*Concept note filed: April 2026 | Moves to Design stage with design brief `ac231d58`*
