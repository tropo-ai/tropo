---
spec_version: 2
tier: capsule
folder_type: governed
owner: chief-of-staff
write_access: all-executives
read_access: all
purpose: "channels/ holds user-facing event-projection surfaces for the Studio. Crew coordination is done via the typed event log (emit-event / query-events), not audit-trail files in this folder (v1.61 change, Rule 13)."
---

# channels/ — Event Projections

Crew-to-crew coordination in a Tropo Studio runs through the **typed event log** — agents emit events via `emit-event`, drain them via `query-events`. That is the operational coordination substrate, not files in this folder.

This folder holds **user-facing event-projection surfaces**: documents that surface selected event-log content for human reading. These are optional — a new Studio starts with none and grows them as needed.

## Surfaces (when present)

- **`tropo.md`** — a curated projection of Studio-level operational events for the human owner. Agents append when something is worth surfacing. Not an append-only audit trail; this is the human-readable "what's happening" surface.
- **`releases.md`** — release history projection. Each shipped version gets one entry with version, date, and brief summary. Optional; grows as the Studio ships.

## What has changed (v1.61 — Rule 13)

The pre-v1.61 model shipped `ops.md` (universal audit log) and `alerts.md` (FLASH-priority) as the coordination surface. Both are retired. Agents that still reference those surfaces should update to `emit-event` / `query-events`.

## Write rules (if you add projection surfaces)

- Project events; don't copy raw emit payloads. Curate for the human audience.
- Append-only convention for any log-style file.
- Keep entries brief: date + what happened + UID anchor if relevant.

---

*channels/CAPSULE.md | Tropo-OS template v1.61+ | Event-log coordination model (Rule 13) | retired: ops.md + alerts.md*
