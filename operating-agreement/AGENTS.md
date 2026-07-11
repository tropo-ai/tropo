---
spec_version: 2
tier: os
maintained_by: tropo
tropo_version: "1.20.0"
governance_contract_uid: "9b78ca9e"
governed_path: "operating-agreement/"
---

# Tropo-OS Governed Folder

This folder is part of a Tropo-OS vault. Before operating, read these files in order:

1. **`.tropo/TROPO-CONTROL.md`** — OS rules, identity checkpoint, invariants
2. **`STUDIO.md`** (vault root) — Organization defaults and constraints
3. **`vault/files/9b78ca9e.md`** — Folder governance contract (the canonical source-of-truth for `operating-agreement/` rules)

The governance contract at `vault/files/9b78ca9e.md` is the canonical authority. The legacy `.tropo-studio/CAPSULE.md` in this folder (if present) remains in place as a thin pointer during the v1.20.0 cycle; it will retire at source-file cleanup. Read the canonical UID for current rules.

`vault/files/9b78ca9e.md` may override `STUDIO.md` defaults. It may not override `STUDIO.md` constraints or `TROPO-CONTROL.md` invariants.

Do not modify this file. It is maintained by Tropo through the update pipeline.
