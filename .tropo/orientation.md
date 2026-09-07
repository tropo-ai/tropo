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
capabilities, rules, locations, and the moment index, one hop from everything. **Read it in full
at boot** (boot-fast-path Step 3a, Mike-ruled 2026-08-30 — a whole read, not a §2-only skim);
reach for it again at need afterward for any specific lookup. The boot digest carries the binding
find-things rules every boot.

**Degraded floor (canonical unreachable):** current truth is `vault/00-index.jsonl` (FTS +
relationships at `vault/00-index.sqlite`); capability catalogs sit beside this file
(`tool-catalog.md` · `skill-catalog.md` · `sa-agent-catalog.md` · `toolbelt.md`); if a capability
exists, use it; delete only via `vault/tools/tropo-recycle.py`; the L1 canonical entry is
`vault/files/eca73d77.md`.

**Indexes missing (clean clone):** both index files are per-machine, `.gitignore`d products —
a fresh clone or first boot on a new machine legitimately has neither. Build them with
`python3 vault/tools/tropo-rebuild-index.py --apply` (dry-run without `--apply`; add
`--reconcile` only to force full re-derivation past the verified-archive cache, not needed for a
first build). That regenerates `vault/00-index.jsonl` + `vault/00-project-tree.jsonl`; the SQLite
edge/FTS index derives from the same rebuild.

---

*Kernel thin pointer | canonical: [docs/tropo-studio-map.md](../docs/tropo-studio-map.md) | cut over 2026-08-27 by Metis G113, Mike-directed | prior full content in git history (v1.15 rescope shape)*
