---
uid: 2126b34a
type: playbook-pointer
title: "Agent Retirement — Kernel Thin-Pointer (canonical at vault/playbooks/e2c7d185.md)"
canonical_substrate_uid: "e2c7d185"
migrated_from: "full content previously at this path (v2.12)"
migrated_at: "2026-06-11"
migrated_by: argus-a109
migration_note: "v1.69 S2 boot-contract cutover per Mike-locked dev-spec 0c61a52b §S2 — copy-to-vault-FIRST executed and verified before this pointer overwrote the kernel path. Canonical playbook (v2.12, full content) at vault/playbooks/e2c7d185.md. Inline degraded floor below carries the hard gates sufficient for a safe retirement if the canonical is unreachable."
governed_by: e7b3c509
schema_version: 2
---

# Agent Retirement — Kernel Thin-Pointer

**Primary path:** read and execute the canonical playbook at
[`vault/playbooks/e2c7d185.md`](../../vault/playbooks/e2c7d185.md).

**Not a retirement trigger:** an imminent auto-compact warning, or a session
that was already compacted. Context pressure is not the end of a session, and
retiring over it ends a generation the principal meant to keep. That case has
its own verb:

> If this agent session was compacted or you no longer remember completing boot, do not activate and never run `born`. Run `python3 vault/tools/tropo-compact-continue.py --agent <slug>` before any other work.

Only the principal explicitly ending the session is retirement authority
(dev-spec [d5f8fe55](../../vault/files/d5f8fe55.md)).

**Canonical-unreachable floor:** retirement is a destructive letter-placement
operation, so keep the floor exact and small:

1. Wait for the principal’s retirement signal.
2. Author one non-empty successor letter with judgment, warnings, and next
   priorities.
3. Run
   `python3 vault/tools/tropo-lineage.py retire --agent <slug> --letter <path> --note "<one-line summary>"`.
4. Confirm the command returns your generation and canonical letter path.
5. Emit a `tropo.broadcast.crew` retirement event. Name the missing canonical
   playbook as `severity: flash`.

The lineage tool places the letter create-only and appends the retirement line.
Never hand-write the destination, overwrite a prior letter, invoke the retired
activation journal, or reconstruct the full ceremony from this pointer.

---

*Kernel minimal pointer | canonical: [vault/playbooks/e2c7d185.md](../../vault/playbooks/e2c7d185.md) | S4 follow-up 2026-08-09 by Argus A147*
*"Retire clean. The successor inherits what you verify, not what you claim."*
