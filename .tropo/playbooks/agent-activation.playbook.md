---
uid: c2caddf4
type: playbook-pointer
title: "Agent Activation — Kernel Thin-Pointer (canonical at vault/playbooks/99341618.md)"
canonical_substrate_uid: "99341618"
migrated_from: "full content previously at this path (v2.16)"
migrated_at: "2026-06-11"
migrated_by: argus-a109
migration_note: "v1.69 S2 boot-contract cutover per Mike-locked dev-spec 0c61a52b §S2 — copy-to-vault-FIRST executed and verified before this pointer overwrote the kernel path (canonical resolved in index before cutover). The two-file pattern: this pointer is the bootstrap floor; the canonical playbook (v2.16, full content) lives at vault/playbooks/99341618.md. Inline degraded floor below is sufficient to boot if the canonical is unreachable."
governed_by: e7b3c509
schema_version: 2
---

# Agent Activation — Kernel Thin-Pointer

**Established agents:** when the activation pointer declares `agent_uid:` and the unified entry contains `§Boot-Extension`, read [`.tropo/boot-fast-path.md`](../boot-fast-path.md) plus [`.tropo/boot-digest.md`](../boot-digest.md). They are fingerprint-gated derivations of the canonical source.

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
