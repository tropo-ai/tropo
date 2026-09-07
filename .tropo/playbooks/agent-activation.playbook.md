---
uid: c2caddf4
type: playbook-pointer
title: Agent Activation — Kernel Thin-Pointer (canonical at vault/playbooks/99341618.md)
canonical_substrate_uid: '99341618'
migrated_from: full content previously at this path (v2.16)
migrated_at: '2026-06-11'
migrated_by: argus-a109
governed_by: e7b3c509
schema_version: 2
history: Amendment history and provenance notes (1 blocks as of 2026-09-04) live in .tropo/playbooks/agent-activation.playbook.history.md;
  this file carries the current rule only (f0153984a89f item 3, argus-a169).
---

# Agent Activation — Kernel Thin-Pointer

**Established agents:** when the activation pointer declares `agent_uid:` and the unified entry contains `§Boot-Extension`, read [`.tropo/boot-fast-path.md`](../boot-fast-path.md) plus [`.tropo/boot-digest.md`](../boot-digest.md). They are fingerprint-gated derivations of the canonical source.

> **If either file is absent, that is expected, not broken — read the canonical playbook instead and proceed.** Both are excluded from the release box on purpose (`KERNEL_EXCLUDE_PATTERNS`, v1.74: *per-studio derivation only*), because a derivation carries the fingerprints of the studio that rendered it — shipping ours would hand every customer a drift gate pinned to our files. So a fresh box legitimately has neither, while every shipped agent entry carries `§Boot-Extension` and would otherwise be routed here into two dead links on its first boot. The canonical [`vault/playbooks/99341618.md`](../../vault/playbooks/99341618.md) ships in full and is the same procedure at greater length; a studio renders its own derivations later. *(Added 2026-08-30 by argus-a163 after measuring it in the shipped v1.93.0 box — finding S5 of `be9abd46`. The exclusion was right; the pointer had no fallback.)*

**All other agents:** read and execute the canonical playbook at [`vault/playbooks/99341618.md`](../../vault/playbooks/99341618.md). That file is the single authored boot-procedure corpus and the future Lifecycle-v3 orient weave source.

**Compacted same session — do NOT activate and do NOT run `born`.** A cold start without a
completed current-generation activation run is a birth. A compacted session WITH one is a
continuation, and the two must never be inferred from each other:

> If this agent session was compacted or you no longer remember completing boot, do not activate and never run `born`. Run `python3 vault/tools/tropo-compact-continue.py --agent <slug>` before any other work.

**Canonical-unreachable floor:** birth still happens. Resolve the Studio root and agent slug from the activation pointer, then run:

`python3 vault/tools/tropo-lineage.py born --agent <slug> --by <principal> --model <sleeve>`

The lineage file issues the generation and never refuses existence. After birth, emit a `tropo.broadcast.crew` event with `severity: flash` naming the missing canonical path, then stop before context loading or substrate work. Do not reconstruct boot procedure, scan legacy activation entries, or guess a generation from memory.

Identity content resolves through `agent_uid:` to `vault/agents/<agent_uid>.md`; legacy per-file identity is fallback-only when the pointer has no unified entry.

---

*Kernel minimal pointer | canonical: [vault/playbooks/99341618.md](../../vault/playbooks/99341618.md) | S4 single-source amendment 2026-08-09 by Argus A147*
*"Soul loads first. The stack makes you who you are."*

*History: [agent-activation.playbook.history.md](agent-activation.playbook.history.md) — never read at boot.*
