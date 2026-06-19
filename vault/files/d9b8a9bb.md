---
uid: d9b8a9bb
type: project
state: active
status: active
title: Packs
description: 'Container for all shipping reference packs and worked-example projects — the content a stranger encounters when they download Tropo. Four packs currently: Green City (v1.1 multi-agent pilot), Verification Starter (Helm content-brief walker exemplar), Agent Identity Starter (Canon brand-voice reviewer toy), Governed Work Starter (Lantern newsletter-planning toy). Each pack consists of a design brief + one or more toy projects + optional canonical artifacts. Evergreen content — ships in releases, does not cycle through the innovation pipeline.'
owner: argus
created: 2026-04-24
modified: 2026-04-24
created_by: vela-v35
member_of:
- b1e7a2c3
tags:
- subsystem-child
- packs
- shipping-reference
- evergreen
- workshop-uplift-target
lifecycle: standing
subsystem: tropo-library
extraction_scope: ship
slug: packs
file_ext: md
schema_version: 2
governed_by: 34e4cb0b
subsystem_hub:
- 1aba710c
capsule_version: '2.5'
---

# Packs

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Library](1aba710c.md) → **Packs**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/agentic-builders/Packs/d9b8a9bb — Packs.md](../../00-tropo-nav/00-tropo-active/agentic-builders/Packs/d9b8a9bb%20%E2%80%94%20Packs.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-active/agentic-builders/Packs/d9b8a9bb — Packs.md](argo-os/00-tropo-nav/00-tropo-active/agentic-builders/Packs/d9b8a9bb%20%E2%80%94%20Packs.md)

**🔗 This file** — UID `d9b8a9bb` · type `project` · state `active` · status `active`

**↓ Children (6):**
  - **design-brief (3):** [Agent Identity Starter — Design Brief](a11de571.md) · [Governed Work Starter — Design Brief](a11de572.md) · [Verification Starter — Design Brief](7e71f1ca.md)
  - **document:** [Canon — Brand Voice Reviewer Toy Agent Spec](ca102001.md)
  - **project (2):** [Green City Energy — The Ridgewood Pilot](9b74ffe5.md) · [Lantern — Monthly Newsletter Planning (Toy Proj...](1a17e001.md)

**↔ Siblings (43):**
  - **under [agentic-builders](b1e7a2c3.md):** [01-inbox](86338b71.md) · [About The Agentic Builders](608a82c1.md) · [addendums](5896edd8.md) · [agentic-builder.playbook — Curriculum Spine for...](750b0996.md) · [Becoming an Agentic Animal — the skills series](5d4e135c.md) · [building-with-maz](c933e1fa.md) · + 37 more

**📥 Cited by (2):**
- [Tropo-OS v1.9.0](1b4bb15a.md) — `1b4bb15a` (type `release`, via `capabilities_touched`)
- [v1.14 schema split is overdue — patch-as-we-go has piled up; M...](fb395501.md) — `fb395501` (type `note`, via `refs`)
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [project (34e4cb0b)](34e4cb0b.md) |
| Member of | [agentic-builders (b1e7a2c3)](b1e7a2c3.md) |

*Container for all shipping reference packs and worked-example projects under [Tropo Library (1aba710c)](1aba710c.md). Established 2026-04-24 by Vela V35 at Founder direction: "we let the workshop get messy. our tools and blueprints are just laying on the floor." This container is the drawer those tools go back into.*

---

## Purpose

Tropo-OS ships reference content a stranger encounters the moment they unzip the release. Before this container existed, those reference projects were scattered — Green City at L0 as an orphan, Lantern and Helm toys archived alongside their v1.3 cycle-shell as if they were cycle-completed work, three starter-pack design briefs parented only to archived v1.3 Stream B. The content was real and shipping; the organization made it unfindable.

This container is the single home for:
1. **Worked-example projects** — complete reference projects demonstrating a domain use-case (Green City — multi-agent solar pilot; Lantern — newsletter planning; Helm — content brief production; Canon — brand-voice review).
2. **Starter-pack design briefs** — authored specs describing what each v1.3+ pack teaches.
3. **Pipeline-walked reference artifacts** — the concept notes, arch specs, builds, releases that child toys produced during pipeline walks (these live as children of their parent toy, not directly here).

## What belongs here

A project belongs in Packs if:
- It ships in the Tropo-OS release zip (`extraction_scope: ship`), OR
- It is authored as a teaching example for strangers, OR
- It is the canonical design brief or toy for a named pack (Verification / Agent Identity / Governed Work / future)

Crew operational work, release-cycle work, and internal architecture work do NOT belong here — those live in `work-pipeline` or their respective subsystem hubs.

## Members (2026-04-24)

### Worked-example projects
- [Green City Energy — The Ridgewood Pilot (9b74ffe5)](9b74ffe5.md) — v1.1 era; multi-agent solar coordination example
- [Lantern — Monthly Newsletter Planning (1a17e001)](1a17e001.md) — v1.3 Governed Work Starter toy
- [Helm Toy — HR Analytics Content Brief (70ece701)](70ece701.md) — v1.3 Verification Starter toy
- [Canon — Brand Voice Reviewer Toy Agent Spec (ca102001)](ca102001.md) — v1.3 Agent Identity Starter toy (type: document)

### Starter-pack design briefs
- [Verification Starter — Design Brief (7e71f1ca)](7e71f1ca.md)
- [Agent Identity Starter — Design Brief (a11de571)](a11de571.md)
- [Governed Work Starter — Design Brief (a11de572)](a11de572.md)

### Not yet authored
- A top-level README or index document explaining what each pack teaches and which toy exemplifies it. Candidate for v1.4 Stream B (Craftsman's Workshop) uplift work.

## v1.4 relationship

This container IS the target surface for v1.4 Thesis B (Craftsman's Workshop) CAPSULE uplift on pack content. Each pack needs bench-signage CAPSULE work: which playbooks apply when working with it, which skills, which pitfalls, where to go next. That work is scoped in [v1.4 Stream 3 (b4e8f2a9)](b4e8f2a9.md).

Also the natural surface for the [v1.4 First-Use Walk gate (fb925dea)](fb925dea.md) — strangers creating their first agent must encounter ≥3 of these packs unprompted.

## Governance

- **Owner:** Argus (authored most v1.3 pack content; Tropo Library owner).
- **Contributors:** Metis (Green City authored by Metis G42); Mike (Green City ownership); Vela (this container, starter-pack structural hygiene).
- **Lifecycle:** `standing` — does not close. Content inside may version (e.g., Green City v1.1 → v1.4 uplift) but the container persists.
- **Write scope for children:** each pack's author retains authority over their pack's content; this container's metadata is Vela-maintained.

---

*Packs container | d9b8a9bb | Created 2026-04-24 by Vela V35 on Founder direction | Parent: [Tropo Library (1aba710c)](1aba710c.md)*
*"Tools back in the drawer. Blueprints on the wall. The workshop is a workshop again."*
