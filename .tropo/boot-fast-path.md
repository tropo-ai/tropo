---
uid: a993f079
type: boot-fast-path
title: "Established-Agent Boot Fast-Path \u2014 the compact activation sequence (gates, not tutorial)"
status: active
boot_derivation: true
owner: argus
created: 2026-06-13
created_by: argus-a111
spec_version: '0.3'
canonical: '99341618'
sources_fingerprint:
- uid: cf8c3be9
  path: .tropo-studio/agent-boot.extension.md
  body_sha256: 4c765298e3f0a47d64b2a012ce16021a5684140d939cbc0f29819152ae824911
- uid: 8f6ea459
  path: .tropo/boot-config.md
  body_sha256: 645359b9af3c5711b5e7c54e4294b91a8aecf08141fdae4f5052cf2829057e81
- uid: 266b0b56
  path: .tropo/boot-digest.md
  body_sha256: 6bae0dc60032cbb93b187dad93a7ec65a81b9bcea75aa258524ba9426e977e9a
- uid: c2caddf4
  path: .tropo/playbooks/agent-activation.playbook.md
  body_sha256: 756d1872bf3912680d6ca382543e81006915585e73e8c30f5c2dc9ffdce59e63
- uid: '99341618'
  path: vault/playbooks/99341618.md
  body_sha256: 39d9d86701c92b33db8c0338648911713fb146ac9351d8ed35d1da791f670876
note: "PROTOTYPE (A111, boot-cost work, S3.5). The established-agent boot procedure: a faithful compaction of the canonical playbook's 6 groups + hard gates + Tier-3 hooks. An established agent (gen 2+ with a \xA7Boot-Extension) reads THIS (~3-4K) instead of re-reading the ~15K canonical every boot. The canonical (99341618) stays the first-gen full read + the on-need reference for any unclear step. Grounded in: the v1.69 kernel degraded floor (c2caddf4, promoted from emergency-only) + the canonical groups + the doctrine digest (266b0b56). WIRING (kernel-pointer \xA7Rules cut-over) + a completeness gauntlet complete (cut-over wired + cold-boot-proven 2026-06-14 by argus-a113) \u2014 it changes the established-agent boot PATH."
sources:
- 99341618 (canonical playbook)
- c2caddf4 (kernel degraded floor)
- 266b0b56 (doctrine digest)
- 8f6ea459 (Tier 1)
- cf8c3be9 (Tier 2)
self_fingerprint:
  body_sha256: 5c2d4db4ab6364eafa15b21705abda3ef150baed79067eda5d739c2c06df486d
gauntlet_verified_at: '2026-06-14'
---

# Established-Agent Boot Fast-Path

*You have booted before. The sequence is internalized; this is the checklist + the gates, not the tutorial. Execute from the three-tier chain. Open the full canonical playbook ([99341618](../vault/playbooks/99341618.md)) only when a specific step is unclear. **First-generation agents: read the full canonical instead — you need the detail.***

***Milestone gate (structural, not advisory):** each group ends by appending its milestone to `run.jsonl`. Before starting any group, READ `run.jsonl` and confirm the prior group's `milestone_fired` event exists — if absent, the gate has not cleared; stop and state the violation. Do not advance on assumption.*

***`run.jsonl` event schema — write these EXACT shapes (tooling + the validator parse them; do not improvise a format):***
- *Group 0 open: `{"event": "run_created", "run_uid": "<8hex>", "agent": "<name>", "generation": "<gen>", "vault_root": "<path>", "timestamp": "<date>", "status": "active"}` then `{"event": "activation_entry_opened", "activation_uid": "<uid>", "timestamp": "<date>"}`*
- *Each milestone: `{"event": "milestone_fired", "milestone": "<name>", "group": "Group N", "timestamp": "<date>"}`*
- *Final (Group 5): the Agent Active milestone adds `"run_status": "complete"`.*

---

## Group 0 — Boot Configuration → `Boot Config Chain Complete`
- Resolve **vault root** from your activation file's location (`<root>/agents/<name>/<name>-activation.md` → `<root>/`).
- Create `playbook-runs/agent-activation-<name>-<gen>-<date>/run.jsonl`; write the `run_created` event.
- Read **Tier 1** (`.tropo/boot-config.md` → canonical `8f6ea459`) + **Tier 2** (`.tropo-studio/agent-boot.extension.md` → canonical `cf8c3be9`). *(Established: tail-scan if version unchanged.)*
- **Identity resolution:** activation thin-pointer declares `agent_uid:` → ALL identity reads/writes go to `vault/agents/<agent_uid>.md` (unified entry; §Charter/§Soul/§Boot-Extension/§Status-Notes).
- Write the activation entry: `python3 vault/tools/40b2f455.py open ...` — it validates the hard gates before writing. Record `activation_entry_opened`.

## Group 1 — Identity Verification (HARD GATES) → `Identity Gates Clear`
- **ADR-016:** predecessor must be RETIRING/RETIRED, not ACTIVE → else HALT, emit `tropo.broadcast.crew category:ops`, await human.
- **ADR-028:** your `generation` = predecessor + 1 → else HALT, flag to human.
- *(Both are enforced at the Group-0 `40b2f455 open` write; this is the belt-and-suspenders read.)*

## Group 2 — Context Loading (soul FIRST) → `Context Loaded`
1. **§Soul** (unified entry §Soul) — read first; it frames everything.
2. **`.tropo/SELF-HEALING.md`** — internalize; confirm in startup signal.
3. **Doctrine → the digest:** read [`.tropo/boot-digest.md` (266b0b56)](boot-digest.md) for the binding rules of all 13 OPs + taxonomy + mission + find-things. Open a full doctrine file only when a rule is in active play. *(This replaces re-reading operating-principles + self-healing-full + mission + orientation verbatim.)*
4. In parallel: **agent memory** `agents/<name>/.tropo-capsule/memory/agent-memory.md` (v3 single surface; run the F5 staleness gate; §Living-Transfer is the handoff; **NEVER read `agent-memories.jsonl` at boot**) · **vault memory** `.tropo-studio/memory/memory-current.md`.
5. [Tier 3] harness orientation + any declared architecture reads.

## Group 3 — Operational Grounding → `Operationally Grounded`
- Read `00-crew-brief.md` (who's on deck, incoming/retiring).
- **Drain events both axes:** `python3 vault/tools/2471edc0.py --as <name>` (check-events; party + agent-root; answered-state, not watermark).
- [Tier 3 / chief-of-staff] vault-health + fleet-ops if declared (opt-in, v2.18).
- Run the import-state scanner if present (`vault/tools/0a316ca6.py`); commission `sa.reconciler` only on `anomaly_detected`.
- Update your **status surface** (unified-entry frontmatter + §Status-Notes) → ACTIVE.
- Status-card vs index reconcile: grep `vault/00-index.jsonl` for inbound open tasks; flag any `done` to the signal.

## Group 4 — Self-Diagnostic → `Diagnostic Complete`
- Document self-diagnostic: is anything read this boot stale/counterproductive/missing? Surface in the signal (don't buffer).
- **Inbound transfer-freshness check (4.1.5; executives):** before treating a predecessor carry-forward as truth, verify each against current substrate — a cited gap may already be closed (bundled remediation, mid-cycle fix). Carry forward only what's still open; flag the delta. *(This is the verify-transfer-against-raw safety net.)*
- **Filesystem-map verification (4.1.6; defensive default):** before declaring any identity-class file missing, query `vault/00-index.jsonl` / resolve via the activation thin-pointer's UIDs. Do NOT reconstruct from memory — reconstruction corrupts lineage. Resumed-across-migration false-positives die here.
- Boot retrospective: one line each — what worked, what didn't (this boot IS the fast-path's test).
- [Tier 3] dispatch `sa.board-agent` if a `board_filter:` is declared → fold the backlog headline into the signal.

## Group 5 — Startup Signal → `Agent Active`
- [Tier 3] **Tropo-invitation check (5.1.5):** if not Tropo + the daily flag is unset, fold a one-line invite into the signal (skip if uninstalled/already-fired-today).
- [Tier 3] **sandwich anchor:** re-read the last paragraph of your §Soul.
- Compose + deliver the **startup signal BEFORE any substantive work:** identity · situational read · honest priority · diagnostic findings (+ board headline, self-healing confirmation) · ≤3 clarifying questions.
- Write the final milestone with `"run_status": "complete"`.

---

*Established-Agent Boot Fast-Path | prototype v0.3 (gauntlet + live-test folded) | Argus A111 | the gates + sequence, compacted; canonical [99341618](../vault/playbooks/99341618.md) is the on-need reference + first-gen read. Pairs with the doctrine digest (266b0b56). Wiring + completeness gauntlet pending Mike's walk.*
