---
spec_version: 2
tier: os
maintained_by: tropo
# tropo_version field removed v1.43.0 Stream G per V47 walk P1 finding:
# folder-tier AGENTS.md governance is not bound to a specific OS version
# (it inherits OS version from runtime context). Hardcoded "0.3.0" was
# extremely stale; removed for substrate-honesty.
---

# Tropo-OS Governed Folder

This folder is part of a Tropo-OS vault. Before operating, read these files in order:

1. **`.tropo/TROPO-CONTROL.md`** -- OS rules, identity checkpoint, invariants
2. **`STUDIO.md`** (vault root) -- Organization defaults and constraints
3. **`CAPSULE.md`** (this folder) -- Folder purpose and operating logic

CAPSULE.md may override STUDIO.md defaults. It may not override STUDIO.md
constraints or TROPO-CONTROL.md invariants.

Do not modify this file. It is maintained by Tropo through the update pipeline.
