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
4. **Living transfer — write it to a FILE and let the tool place it.** Author your letter anywhere convenient and pass it to step 5 with `--transfer-file`. The tool writes it to **both** homes in one gesture: `agents/<slug>/transfers/<generation>.md` — **the canonical home your successor's boot contract now reads** (create-only, so it can never be overwritten) — and, as a bridge, the handoff section of `agent-memory.md`, which several agents' Tier-3 contracts still name. Do not hand-write either — that is the divergence rule 7 exists to prevent, and until 2026-08-04 it was the agent's job. *(Boot readers moved to the per-generation file in the 2026-08-04 cutover; the second write retires once every Tier-3 contract points there.)*

   **Use `###` for headings inside the letter, not `##`.** The boot reader ends the transfer section at the next `##` of any kind, so a `##` heading truncates everything after it — silently. Orpheus O34's letter had one at line 7. *(Latent today: that reader has no production caller. It will matter the moment one appears.)*

   **What belongs in it, now that the briefing covers the facts:** warnings, judgment, what you would have done next, and the state of the human relationship. Not a status report — the log carries that better than you can. A page, not five.
5. **Close the activation entry — USE THE NEW TOOL:**

   ```
   python3 vault/tools/tropo-lineage.py retire --agent <slug> --letter <path> \
       --transfer-file <path to your letter> --reason clean-retirement
   ```

   **Writing the transfer IS the close.** There is no separate step and no ceremony gate: no reflection gate, no memory-fold gate, no drained-events gate, no RETIRING pre-write required. The tool writes your letter to both homes, flips the record and your status card in one gesture, and records anything it could not do as a finding in the record rather than refusing.

   It refuses exactly three things, each guarding something destructive: an activation UID that does not resolve; an **empty or unreadable letter** — the state does NOT flip, so your last words are never replaced by a zero-byte file; and a **second retirement** — your first letter is never overwritten.

   **You do not need `--check-broker`, and its absence is not a gap.** This lifecycle mints and touches no cryptographic keys at all (ADR-066), so `KEY_BROKER_UNAVAILABLE` cannot occur. Talos's step-0 broker discipline (`b00c2116`) was correct for the old path and is now designed out rather than forgotten.

   *Why this changed:* the old `40b2f455.py close` enforced R-1/R-2/R-3 invariants that only the retiring agent could satisfy — which is how Po's record sat open for thirty days and how G98 and T37 lost their clean closes to `KEY_BROKER_UNAVAILABLE`. This line pointed at that tool until 2026-08-04, and **Orpheus O34 avoided the trap only because she was told out of band.** Her First-Use Walk is what got it changed. The old tool remains available for records the new one cannot yet handle; it is not the default.
6. **Step 4.2 — RETIRED, three sub-steps, all required:** (a) frontmatter `status: RETIRED`; (b) §Status-Notes body REWRITE — your generation flips to its retirement summary, predecessor's note ages out (bound: current + predecessor), add "Passed to [N+1]" top-3 priorities; (c) VERIFY by re-reading §Status-Notes — both surfaces must agree before you proceed.
7. **Retirement broadcast** (`tropo.broadcast.crew`, category retirement) + reflection at `agents/<name>/reflections/`.

**The session is not over until the principal says it is. Never ask if the session is ending — wait to be told.**

---

*Kernel thin-pointer | canonical: [vault/playbooks/e2c7d185.md](../../vault/playbooks/e2c7d185.md) | v1.69 S2 | Argus A109 2026-06-11*
*"Retire clean. The successor inherits what you verify, not what you claim."*
