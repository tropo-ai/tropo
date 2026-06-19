---
uid: 9b13fcab
type: ship-artifact
title: "Ship (web): Capsule-vs-Instance Naming"
description: "Web extraction for the Capsule-vs-Instance Naming KB article. Renders at /kb/9b3e8c47. Source: 9b3e8c47 — Tropo's kernel rule for distinguishing capsule definitions from their instances. Nearest Capsules reference pending 'How Capsules Work' canonical."
kind: file
target: [web]
source_mode: direct-copy
canonical_source: argo-os/vault/files/9b3e8c47.md
parent: 62823771
extraction_scope: ship
state: archived
status: locked
owner: talos
author: talos-t8
created: 2026-05-18
created_by: talos-t8
modified: 2026-05-30
modified_by: metis-g62
schema_version: 2
member_of:
  - "4a99638d"
  - "62823771"
cleanup_rules:
  strip_nav_blocks: true
  strip_relations_table: true
  rewrite_uid_refs: true
  uid_rewrite_template: "/kb/<uid>"
  broken_link_policy: strip
g60_bulk_amendment_note: "cleanup_rules block added 2026-05-24 by metis-g60 as part of class-wide audit per design-brief e4c8b2a1. Wrapper was authored pre-v1.49 (cleanup_rules schema landed v1.49 per KGAE wrapper 89a649b5 reference). Mirrors canonical KGAE pattern. Closes substrate-bleed defect class structurally for this wrapper; future publishes apply nav-block + relations-table + UID-ref cleanup at extract time."
tags: [ship-artifact, target-web, category-kb-articles, kb-article, tropo-capsules]
publication_state:
  web: live
board_hygiene_note: "Board-hygiene 2026-05-30 (Metis G62): content verified LIVE on tropo-ai.com via platform-repo + live-site audit; wrapper status draft->shipped to match reality. Publish gate is the kb-content snapshot + manifest, not this field."
---

# Ship (web): Capsule-vs-Instance Naming

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Governance](8dd772a0.md) → [Tropo Website Content Structure](4a99638d.md) → **Ship (web): Capsule-vs-Instance Naming**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-all/tropo-work/web-pipeline/Tropo Website Content Structure/9b13fcab — Ship (web)- Capsule-vs-Instance Naming.md](../../00-tropo-nav/00-tropo-all/tropo-work/web-pipeline/Tropo%20Website%20Content%20Structure/9b13fcab%20%E2%80%94%20Ship%20%28web%29-%20Capsule-vs-Instance%20Naming.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-all/tropo-work/web-pipeline/Tropo Website Content Structure/9b13fcab — Ship (web)- Capsule-vs-Instance Naming.md](argo-os/00-tropo-nav/00-tropo-all/tropo-work/web-pipeline/Tropo%20Website%20Content%20Structure/9b13fcab%20%E2%80%94%20Ship%20%28web%29-%20Capsule-vs-Instance%20Naming.md)

**🔗 This file** — UID `9b13fcab` · type `ship-artifact` · state `archived` · status `locked`

**↔ Siblings (29):**
  - **under [Tropo Website Content Structure](4a99638d.md):** [Ship (web): Hello Tropo #01 — 2026 Customer Eve...](4681f97f.md) · [Ship (web): How Agents Work](a7365c8d.md) · [Ship (web): How Playbooks Work](7165b151.md) · [Ship (web): How the Tropo Vault Works](5bbee0e2.md) · [Ship (web): How to Build with Tropo Agents — Ex...](a205f415.md) · [Ship (web): How to Build with Tropo Capsules — ...](4dd40f6f.md) · + 16 more
  - **under [Web Category: KB Articles](62823771.md):** [Ship (web): Hello Tropo #01 — 2026 Customer Eve...](4681f97f.md) · [Ship (web): How Agents Work](a7365c8d.md) · [Ship (web): How Playbooks Work](7165b151.md) · [Ship (web): How the Tropo Vault Works](5bbee0e2.md) · [Ship (web): How to Use Channels](4154e232.md) · [Ship (web): Substrate Gap — Capsules Canonical ...](11ec50b6.md) · + 1 more
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [Tropo Website Content Structure (4a99638d)](4a99638d.md) |
| Member of | [Web Category: KB Articles (62823771)](62823771.md) |

*Web-target ship-artifact entry per [Tropo Website Content Structure (4a99638d)](4a99638d.md). Renders at tropo-ai.com/kb/9b3e8c47.*

## Purpose

Ships the Capsule-vs-Instance Naming KB article ([9b3e8c47](9b3e8c47.md)) to the KB surface at `/kb/9b3e8c47`. Serves as the nearest available canonical reference for the Capsules primitive while the full "How Capsules Work" article (substrate gap filed at [c8a91f4e](c8a91f4e.md)) remains unwritten. Cited by the Capsules explainer page ([4dd40f6f](4dd40f6f.md)).

## Description

Source: [9b3e8c47](9b3e8c47.md) — "Capsule-vs-Instance Naming". Type: kb-article. Explains Tropo's kernel rule for distinguishing capsule definitions from their instances on the file system — a short, precise explainer on naming discipline.

Extraction applies KB Articles category default cleanup: strip nav-block sentinels and Relations table, strip substrate-only sections, rewrite UID-style links (KB siblings → `/kb/<uid>`; articles → `/agentic-builders/uid/<uid>`; substrate-only → plain text), preserve cited-by references routed to web URLs.

Rendered by `KBLayout` React component: title + description, body content, cross-references rendered cleanly, cited-by section. When the proper "How Capsules Work" canonical is authored and a new ship-artifact entry replaces this as the Capsules explainer sidebar link, this entry continues shipping as a standalone KB reference.
