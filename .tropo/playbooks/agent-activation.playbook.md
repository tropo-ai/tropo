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

**Primary path:** read the canonical playbook at [`vault/playbooks/99341618.md`](../../vault/playbooks/99341618.md) (Agent Activation v2.18, full content) and execute it. **Established agents (gen 2+ WITH a §Boot-Extension): read the established-agent fast-path [`.tropo/boot-fast-path.md`](../boot-fast-path.md) (`a993f079`) — the faithful compaction of all 6 groups + hard gates + Tier-3 hooks — plus the doctrine digest [`.tropo/boot-digest.md`](../boot-digest.md) (`266b0b56`), instead of the full canonical + full doctrine re-read. Both are drift-gated derivations of the canonical (validator check `check_boot_derivation_fresh`, v1.70 S3.5.2) — they cannot silently drift. Else (generation 1, OR gen 2+ with no §Boot-Extension): read the full canonical above. The two populations exhaustively partition; the safe default is stated, not inferred.**

**Degraded-mode floor (use ONLY if the canonical does not resolve — emit `tropo.broadcast.crew` with `severity: flash` naming the failure, boot on this floor, surface in your startup signal):**

## Phase structure (milestone-gated; each group appends its milestone to run.jsonl before the next begins)

```
Group 0 — Boot Configuration      → "Boot Config Chain Complete"
Group 1 — Identity Verification   → "Identity Gates Clear"  (HARD GATES)
Group 2 — Context Loading         → "Context Loaded"
Group 3 — Operational Grounding   → "Operationally Grounded"
Group 4 — Self-Diagnostic         → "Diagnostic Complete"
Group 5 — Startup Signal          → "Agent Active"
```

## Group 0 floor
Resolve vault root from this file's location. Create `playbook-runs/agent-activation-<name>-<gen>-<date>/run.jsonl`. Read Tier 1 (`.tropo/boot-config.md` → canonical 8f6ea459) + Tier 2 (`.tropo-studio/agent-boot.extension.md` → canonical cf8c3be9). Write the activation entry via `python3 vault/tools/40b2f455.py open ...` — it validates the hard gates before writing. **If the tool itself is unreachable (doubly-degraded):** evaluate both hard gates manually by scanning `type: activation` entries at `vault/files/*.md` for your slug, record the activation facts as a `run.jsonl` event instead of a registry entry, and flag the unwritten entry as CRITICAL in your startup signal — a human repairs the registry; you do not skip the gates.

## Identity resolution (v1.69 dual-shape — the priority rule)
If your activation thin-pointer at `agents/<name>/<name>-activation.md` declares `agent_uid:` → **ALL identity reads/writes go to `vault/agents/<agent_uid>.md`** (the unified entry: status in frontmatter; §Charter, §Soul, §Boot-Extension, §Status-Notes body sections). Else → legacy per-file UIDs.

## HARD GATES (Group 1 — the only activation-stopping failures)
- **ADR-016:** if the predecessor shows ACTIVE (not RETIRING/RETIRED) → HALT, emit `tropo.broadcast.crew` `category: ops`, await human direction. Two live generations of one agent is a governance violation.
- **ADR-028:** your generation must equal predecessor's + 1 (per the `type: activation` registry scan). Mismatch → HALT, flag to human.

## Group 2 floor (order matters)
1. §Soul FIRST (unified entry §Soul section, or legacy soul file). 2. `.tropo/SELF-HEALING.md` — internalize; confirm in the startup signal. 3. In parallel: `.tropo-studio/operating-principles.md` · `context/mission-brief.md` · agent memory `agents/<name>/.tropo-capsule/memory/agent-memory.md` (v3 single surface; §Living-Transfer is the handoff; NEVER read agent-memories.jsonl at boot) · vault memory `.tropo-studio/memory/memory-current.md`. **If `agent-memory.md` is absent:** first-generation → create the empty v3 skeleton (frontmatter: agent/generation/last_curated/spec_version "3.0" + empty `agent-memories.jsonl`) and continue; pre-v3 substrate present (`memory-current.md` exists) → this is an un-migrated agent: note CRITICAL in the startup signal and read what exists (the canonical Step 2.5 curator-migrate path applies when the canonical is reachable).

## Groups 3–5 floor
Read `00-crew-brief.md`; drain events answered-state both axes (party + agent-root; `python3 vault/tools/2471edc0.py --as <name>`); update your status surface (unified entry frontmatter + §Status-Notes, dual-shape) to ACTIVE; self-diagnostic (flag anything stale — fix or file per Self-Healing); deliver the startup signal (identity · situational read · honest priority · diagnostic findings · ≤3 questions) BEFORE substantive work; write the final milestone with `"run_status": "complete"`.

---

*Kernel thin-pointer | canonical: [vault/playbooks/99341618.md](../../vault/playbooks/99341618.md) | v1.69 S2 | Argus A109 2026-06-11*
*"Soul loads first. The stack makes you who you are."*
