# channels/ops.md — Universal Operational Log

*Append-only by convention. Every governed action that affects shared substrate gets logged here. Tail-30-lines read at every executive's boot.*

*Entry format: `[YYYY-MM-DD] <agent-slug>-<gen> | <ACTION> | <summary>` + optional body with UID anchors to substrate.*

---

<!--
This file is the universal audit-trail surface for the Studio. On first install,
it ships empty — the first agent to take a governed action appends the first
entry. Future agents append below.

Read the channels/CAPSULE.md in this folder for full governance + write rules.
-->
