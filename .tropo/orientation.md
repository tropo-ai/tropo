---
uid: orientation
type: os-primitive
status: active
owner: tropo
tier: os
canonical_substrate: docs/tropo-studio-map.md
canonical_uid: '3e581123'
modified: '2026-08-27'
modified_by: metis-g113
migration_note: "2026-08-27 consolidation (Mike-directed, two-canonical-documents ruling): full harness-map content absorbed into the Studio Map at docs/tropo-studio-map.md (3e581123). This file is now the kernel thin pointer per the v1.69 two-file pattern; the digest's §Find Things carries the binding rules and re-fingerprints on this change."
---

# Tropo-OS — Orientation (kernel thin pointer)

**The canonical orientation surface is [the Studio Map](../docs/tropo-studio-map.md)** —
capabilities, rules, locations, and the moment index, one hop from everything. Read it at need;
the boot digest carries the binding find-things rules every boot.

**Degraded floor (canonical unreachable):** current truth is `vault/00-index.jsonl` (FTS +
relationships at `vault/00-index.sqlite`); capability catalogs sit beside this file
(`tool-catalog.md` · `skill-catalog.md` · `sa-agent-catalog.md` · `toolbelt.md`); if a capability
exists, use it; delete only via `vault/tools/tropo-recycle.py`; the L1 canonical entry is
`vault/files/eca73d77.md`.

---

*Kernel thin pointer | canonical: [docs/tropo-studio-map.md](../docs/tropo-studio-map.md) | cut over 2026-08-27 by Metis G113, Mike-directed | prior full content in git history (v1.15 rescope shape)*
