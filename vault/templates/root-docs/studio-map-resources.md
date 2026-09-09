---
uid: 'f0151af6fe88'
type: document
title: "Studio Map resources"
description: "The one declared list of resources the rendered Studio Map surfaces to a human — read by vault/tools/tropo-render-studio-map.py and rendered as the Resources section at the top of boards/po/studio-map.html. Add a resource here, not in the renderer."
status: published
state: active
owner: metis
author: metis-g120
created: '2026-09-05'
created_by: metis-g120
modified: '2026-09-05'
modified_by: metis-g120
schema_version: 2
extraction_scope: ship
tags:
  - studio-map
  - resources
  - rendered-surface
  - human-surface
---

# Studio Map resources

*The curated list the rendered Studio Map carries. One line per resource: a link and one sentence
saying why a human would open it. Paths are box-relative (they resolve inside any extracted
Studio); URLs are public. The renderer rewrites every relative path for the render's own location —
write them from the Studio root and nowhere else.*

- [The Architecture Review](docs/architecture-review-v5/tropo-l1-architecture-review.html) — What the system is, why it is shaped this way, and its honest failure record; the Map's sibling canonical document.
- [What is Tropo? — the L1 canonical entry](vault/files/eca73d77.md) — The single entry document: read this first when you are arriving cold and want the whole idea in one pass.
- [The Tropo Handbook](vault/files/c92ae197.md) — The standing reference a human reads end to end: the method, the vocabulary, and how the pieces fit.
- [START-TROPO.md](START-TROPO.md) — The first-run instructions for a freshly unzipped Studio: the one command to run before you open your AI tool.
- [CHANGELOG.md](CHANGELOG.md) — What changed in this release and every release before it, in the project's own words.
- [tropo-ai.com](https://tropo-ai.com) — The public home of Tropo: setup guidance, and the place to point someone who has never seen a Studio.
- [Public releases](https://github.com/tropo-ai/tropo/releases) — Every published box, so you can see what is current and what you are running.
