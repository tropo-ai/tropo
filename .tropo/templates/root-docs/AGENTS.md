---
spec_version: 2
tier: os
maintained_by: tropo
# tropo_version field removed v1.43.0 Stream G per V47 walk P1 finding:
# folder-tier AGENTS.md governance is not bound to a specific OS version
# (it inherits OS version from runtime context). Hardcoded version field
# was a recurring drift class. Removed for substrate-honesty.
---

# Tropo-OS Governed Folder

This folder is part of a Tropo-OS vault. Before operating, read these files in order:

1. **`.tropo/TROPO-CONTROL.md`** -- OS rules, identity checkpoint, invariants
2. **`STUDIO.md`** (vault root) -- Organization defaults and constraints
3. **`CAPSULE.md`** (this folder) -- Folder purpose and operating logic

CAPSULE.md may override STUDIO.md defaults. It may not override STUDIO.md
constraints or TROPO-CONTROL.md invariants.

**New to this vault?** If no specific agent file was provided to you, read `.tropo/concierge/activate.md` — it is your guide for the first session.

Do not modify this file. It is maintained by Tropo through the update pipeline.
