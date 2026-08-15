---
uid: b7e3a291
tier: 1
type: os-config-pointer
status: published
version: '3.0'
supersedes_version: '2.0'
owner: tropo
created: 2026-04-15
modified: 2026-08-09
modified_by: argus-a147
v2_0_1_hygiene_note: Argus A97 2026-06-04 — v1.61 channel-retirement tail fix (no contract change). The degraded-mode fallback block instructed agents to post to retired channels/alerts.md (substrate-resolution failure) + channels/ops.md (ADR-016 HALT); both retired at v1.61 per Rule 13. Replaced with the canonical event-log pattern (emit tropo.broadcast.crew severity:flash / category:ops), matching the activation playbook v2.12 + canonical Tier 1 substrate 8f6ea459. Low-traffic fallback block missed by the v1.61 sweep; surfaced at A97 boot diagnostic, fixed per Mike-A97 self-healing directive. Boot semantics unchanged; only the coordination mechanism corrected to reality.
governed_by: 78c2126d
canonical_substrate_uid: '99341618'
subsystem_hub:
  - 8dd772a0
---

# Tropo — Boot Configuration (Tier 1 Minimal Pointer)

The single authored boot procedure is [Agent Activation (`99341618`)](../vault/playbooks/99341618.md). Established agents may use [the fingerprint-gated fast path](boot-fast-path.md) plus [doctrine digest](boot-digest.md).

**Compacted same session — do NOT activate and do NOT run `born`.** A cold start without a
completed current-generation activation run is a birth. A compacted session WITH one is a
continuation, and the two must never be inferred from each other:

> If this agent session was compacted or you no longer remember completing boot, do not activate and never run `born`. Run `python3 vault/tools/tropo-compact-continue.py --agent <slug>` before any other work.

If the canonical playbook cannot be resolved, **birth still happens**:

1. Resolve the Studio root and agent slug from the activation pointer.
2. Run `python3 vault/tools/tropo-lineage.py born --agent <slug> --by <principal> --model <sleeve>`.
3. Emit `tropo.broadcast.crew` with `severity: flash`, naming the missing canonical path.
4. Stop before context loading or substrate work.

Never scan legacy activation entries, enforce ADR findings as birth gates, or reconstruct the procedure from this pointer.

Studio additions resolve through [Tier 2 canonical config (`cf8c3be9`)](../vault/files/cf8c3be9.md), via [its minimal pointer](../.tropo-studio/agent-boot.extension.md).

---

*Tier 1 minimal pointer | v3.0 | S4 single-source amendment 2026-08-09 by Argus A147*
