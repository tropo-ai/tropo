---
uid: b39e7d54
title: 01-inbox
type: project
name: 01-inbox
status: active
state: active
owner: talos
created: 2026-05-15
modified: 2026-05-15
created_by: talos-t4
modified_by: talos-t4
member_of:
  - 7b2e94c1
schema_version: 2
extraction_scope: ship
file_ext: md
tags:
  - project
  - inbox
  - web-pipeline
  - composable-inbox
lifecycle: standing
---
# 01-inbox — web-pipeline

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [web-pipeline](7b2e94c1.md) → **01-inbox**
<!-- nav-block:end -->

## Purpose

The inbox for web-pipeline. Pre-cycle candidates for the tropo-ai.com website land here as notes or work-items before getting picked into a per-deploy pipeline-run. Composable-inbox pattern: items here roll up to the Studio-root `01-vault-inbox/` for cross-pipeline visibility.

## What Belongs Here

- **Page or feature ideas** for the website that aren't yet scoped into a deploy.
- **Hosting / DNS / CI-CD setup work** (the first item to land — hosting research and host selection produces the substrate the pipeline operates on).
- **Design notes, content drafts, copy** that aren't tied to a specific deploy yet.
- **Defects and follow-ups** found on the live site that aren't blocking enough to fire an out-of-cycle deploy.

## What Does Not Belong Here

- In-flight deploy work (lives under the active deploy's activation-root project, not here).
- Marketing strategy itself (lives in MOS substrate, not here — the website surfaces MOS positioning; it doesn't author it).
- Tropo platform engineering work (lives at the tropo-ai/ repo root and dev-pipeline; the website is a separate product surface).

## Lifecycle

Items arrive as `type: note` or `type: task` with `member_of: [b39e7d54]`. When Mike or Talos picks an item into a deploy, it gets referenced from the activation-root project of that pipeline-run (`refs:` or `member_of:` extended). Once shipped, the inbox item can be archived (`state: archived`) or referenced as historical context.

Aggressive archive bias: ideas that sit unused for a cycle don't need defensive preservation — if the problem resurfaces, the idea will too.

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-15 | Initial draft. Authored as part of web-pipeline v1.0.0 construction at Mike's direction. | talos-t4 |

---

*01-inbox | web-pipeline | composable inbox | rolls up to 01-vault-inbox*
