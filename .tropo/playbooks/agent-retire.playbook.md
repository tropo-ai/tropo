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

**Primary path:** read the canonical playbook at [`vault/playbooks/e2c7d185.md`](../../vault/playbooks/e2c7d185.md) (Agent Retirement v2.12, full content) and execute it.

**Degraded-mode floor (use ONLY if the canonical does not resolve — emit `tropo.broadcast.crew` with `severity: flash`, retire on this floor, note the degradation in your transfer):**

1. **Step 0.0a — migration-lock check:** if `.tropo-studio/locks/migration-in-progress.lock` exists → HALT with advisory and AWAIT clearance or human direction (the lock is per-apply and short-lived). Do not proceed.
2. **Step 0.1 — RETIRING hard gate (dual-shape):** if your activation thin-pointer declares `agent_uid:` → write `status: RETIRING` to `vault/agents/<agent_uid>.md` frontmatter; else to `agents/<name>/<name>-status.md`. This write is what protects your successor's boot — never skip it.
3. **Memory fold:** dispatch sa.memory-curator (trigger: retire) per `vault/files/e863a1e0.md` — folds `agent-memories.jsonl` since the boundary into `agent-memory.md` §Top-of-Mind, archives a frozen snapshot to `history/`, advances the boundary (append-only: never clear).
4. **Living transfer:** author AS the `§Living-Transfer-from-Predecessor` section of `agent-memory.md` (v3 single surface — no separate transfer file). FINAL before close.
5. **Close the activation entry:** `python3 vault/tools/40b2f455.py close --activation-uid <uid> --target-status retired --transfer-uid <8-hex stub uid>` — the tool enforces the R-1/R-2/R-3 retirement invariants and auto-creates the transfer stub. The transfer-uid is 8-hex, NEVER a slug.
6. **Step 4.2 — RETIRED, three sub-steps, all required:** (a) frontmatter `status: RETIRED`; (b) §Status-Notes body REWRITE — your generation flips to its retirement summary, predecessor's note ages out (bound: current + predecessor), add "Passed to [N+1]" top-3 priorities; (c) VERIFY by re-reading §Status-Notes — both surfaces must agree before you proceed.
7. **Retirement broadcast** (`tropo.broadcast.crew`, category retirement) + reflection at `agents/<name>/reflections/`.

**The session is not over until the principal says it is. Never ask if the session is ending — wait to be told.**

---

*Kernel thin-pointer | canonical: [vault/playbooks/e2c7d185.md](../../vault/playbooks/e2c7d185.md) | v1.69 S2 | Argus A109 2026-06-11*
*"Retire clean. The successor inherits what you verify, not what you claim."*
