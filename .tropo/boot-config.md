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
governed_by: 78c2126d
canonical_substrate_uid: '99341618'
subsystem_hub:
- 8dd772a0
history: Amendment history and provenance notes (1 blocks as of 2026-09-04) live in .tropo/boot-config.history.md; this file
  carries the current rule only (f0153984a89f item 3, argus-a169).
---

# Tropo — Boot Configuration (Tier 1 Minimal Pointer)

The single authored boot procedure is [Agent Activation (`99341618`)](../vault/playbooks/99341618.md). Established agents may use [the fingerprint-gated fast path](boot-fast-path.md) plus [doctrine digest](boot-digest.md) **when present — both are deliberately excluded from the release box (per-studio derivations carry their rendering studio's fingerprints), so on a fresh box read the canonical and proceed. Their absence is not a partial extraction.**

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

*History: [boot-config.history.md](boot-config.history.md) — never read at boot.*
