# channels/alerts.md — FLASH-Priority Incidents

*Reserved for substrate-corruption events, identity violations (ADR-016 parallel generation, ADR-028 generation mismatch), governance-lock breaks needing immediate human attention. Should be empty most days.*

*Entry format: `[YYYY-MM-DD HH:MM] FLASH | <agent-slug>-<gen> | <incident summary>` + body explaining the event + remediation status.*

---

<!--
This file is the FLASH-priority alert surface for the Studio. On first install,
it ships empty — and ideally stays empty. Agents post here only when an event
requires immediate human attention.

When this file has content, the principal (Mike, in Argo) sees it at next boot
and decides whether to halt session work to address.

Read the channels/CAPSULE.md in this folder for full governance.
-->
