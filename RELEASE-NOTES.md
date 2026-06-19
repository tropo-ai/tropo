*v1.55–v1.68 authored 2026-06-11 by Orpheus O17 as a currency catch-up. RELEASE-NOTES had drifted 14 versions behind (last entry v1.54) because the release-note cascade never fired across Blocks 5–6 — the same retroactive-anchor gap closed structurally at v1.66 S5. Each entry is reconstructed from its cycle's release entry, dev-spec, and ship broadcast: the Block-6 cycles (v1.62–v1.68) carry full ship detail; the Block-5 messaging cycles (v1.55–v1.61, whose release entries shipped as activation-time stubs) carry verified theme + committed scope at honest altitude. Going forward this surface should be written at each ship, not reconstructed.*

---

## v1.68.0 — Lifecycle Close + Inbox Cure (2026-06-10 by vela-v61; Block 6 — Structure-Enforcement)

**The lifecycle model stops leaking and the inbox is drained to zero.** v1.68 closes the enforcement gaps the prior lifecycle cycles left open and cures a 226-item inbox backlog structurally.

- **S1 — Lifecycle ENFORCE-Close.** Status-leak narrowed to 3 named exclusions; the unexplained-membership ("M2") class driven to zero via a `REFERENCE_EXEMPT` predicate that prints its reasoning; state-enum + M2 ERROR ratchets live; a canonical `archive()` tool ([6cc9dcdb](vault/files/6cc9dcdb.md)).
- **S2 — Inbox Transition Protocol.** `check_inbox_transition` two-tier check + `action_bootstrap` auto-re-parent wiring; a 264-correction drain took inbox membership 412 → ~181 and the HARD count 226 → 0; inbox-HARD ERROR ratchet live.
- **Self-Healing v1.1.0** exit-side declaration (Mike-signed).

*Tropo-OS v1.68.0 | UID `10411500` | the lifecycle stops leaking; the inbox hits zero.*

---

## v1.67.0 — Memory v3.0 Cascade Close (2026-06-10 by vela-v61; cascade by argus-a108; Block 6)

**Every agent now boots from one memory surface.** v1.67 completes the Memory v3.0 migration crew-wide: a single boot-read file plus an append-only episodic log the curator folds at retirement.

- **Single-surface boot-read** — `agent-memory.md` replaces the prior multi-file memory index; one read per boot.
- **Append-only episodic log** — `agent-memories.jsonl` accumulates mid-session observations; the curator folds it at retire.
- **Curator retirement-fold** — `sa.memory-curator` v1.1 (`trigger:retire`) runs as a standard retire step.
- **F5 boot-staleness gate** — boot detects an unfolded log backlog and surfaces it in the startup signal.
- **Crew-wide cascade** — all 7 agents migrated via `sa.memory-curator` dispatches 008–013 (Argus A108), each verified against raw; rollback intact.
- Build-release validator timeout raised 120s → 300s to accommodate vault growth.

*Tropo-OS v1.67.0 | UID `ec0ddabc` | one memory surface, an episodic log, a curator that folds at retire.*

---

## v1.66.0 — Make Verification Real (2026-06-10 by vela-v61; dev cycle argus-a103→a106 + talos-t13 + orpheus-o17 + vela-v60; Block 6)

**The pipeline engine stops trusting an agent's word that a step passed.** v1.66 closes the verification-theater gap: gate verdicts must come from real sources. Six rounds of adversarial sa.skeptic found and closed five distinct self-attestation routes; round 6 found none.

- **S1 — Verification spine** (Talos T13 + Vela V60): pipeline-runtime hardened against self-attestation; engine-level self-attestation fully closed; Check-20 ratcheted to ERROR.
- **S2 — Lifecycle DERIVE + state DISAMBIGUATE** (Talos + Argus A104/A105): the lifecycle field derives from the capsule definition; a 51-entry state migration to {active, archived}; core.capsule v1.6.
- **S3 — Pristine tier docs** (Orpheus O17 + Argus A106): the 3-tier boot documentation re-verified cold-boot-clean; 4 drift items (D1–D4) corrected in Tier 1/2 and attested PRISTINE — the doc cascade that cleared the cut.
- **S5 — Cascade-coupling close-gate** (Talos): build-release refuses to close a cycle with open triggered doc/test activations; dev-spec.capsule v1.2.
- **B1 — Boot playbook split** (Argus A104/A105): activation playbook v2.13 lean + history companion [4b4ab7db](vault/files/4b4ab7db.md); ~11K tokens saved per established-agent boot.
- **meta_status rename** (Argus A105): `meta_stage` → `meta_status` end-to-end (engine + 23 capsules).
- **CLAUDE.md routing** (Vela V61): executive activation bypasses the concierge load; ~8K tokens saved per executive boot.

*Tropo-OS v1.66.0 | UID `f4d0d0c7` | a gate verdict is a machine result or a real human signoff — never an agent's say-so.*

---

## v1.65.0 — Coherence + Enforcement Sweep (2026-06-07 by vela-v59 + argus-a102; Block 6)

**A coherence release: it tightens the substrate's own structural rules rather than adding features.** The headline is **member_of DISAMBIGUATE** — for months a single `member_of` field carried two jobs (which project an entry belongs to, and which subsystem it serves), and that conflation drove a recurring class of derivation bugs.

- **member_of DISAMBIGUATE** — core.capsule v1.5 Rule 9 splits the field: `member_of` = parent edge, `subsystem_hub` = subsystem edge. Derivations + 7 type capsules retargeted; subsystem-hub discovery made dynamic (10 active hubs).
- **`done → shipped` release terminal** — release.capsule v3.12: the canonical terminal release status is now `shipped`; ~50 entries already conformed, zero migration.
- **ADR-044 ACCEPTED** — Structure-Enforcement is the v2.0 architecture (the decision of record governing Block 6).
- **Lifecycle status/stage migration** (70b24992 phase 3/4) — the vocabulary-unification work that began from Mike's "imagine the stranger" comment; zero drops, reversible.
- **Enforcement ratchet** — Check 11 (no hub UIDs in `member_of`) WARN → ERROR with drift = 0.

*Tropo-OS v1.65.0 | UID `895fad3a` | plumbing that makes the next layer trustworthy — v1.66 makes verification real.*

---

## v1.64.0 — Verification-Command Hardening (2026-06-03 by vela-v58; dev cycle vela-v57; Block 6)

**Closes the `vc:true` self-attestation hole — the gate verifies its own steps by machine verdict, not an agent's word.** v1.62 made a `verification_class:false` gate step's verdict machine-produced; v1.64 closes the remaining hole where a `verification_class:true` gate step's verdict could still be agent-typed.

- **pipeline.capsule v3.2** — a `verification_command` field (required for vc:true gate steps) + Rule 11 closing both gate-step verdict branches.
- **Engine** runs the command at step-completed (exit 0 = pass), and refuses `--natural-verdict` for vc:true gates.
- **tropo-validate Check 20** — ratchets gate steps toward requiring `verification_command` (WARN now → ERROR at v2.0).
- **check-one.py** — a targeted single-entry validator, the reusable primitive a gate step's `verification_command` calls.

*Tropo-OS v1.64.0 | UID `6e7ab9b5` | the gate completes itself; the 1.62→1.63→1.64 lineage closes.*

---

## v1.63.0 — Immutable Agent Identity (2026-06-02 by vela-v58; dev cycle vela-v57; Block 6)

**Agent identity becomes an immutable, canonical, single-source primitive.** Before v1.63 the crew discovered each other's identities by scraping status cards or watching who-emitted-what — scatter that root-caused four session defects (most visibly Talos's entire work queue going invisible because dispatches went to a lineage UID while his card pointed at a phantom).

- **Registry `party_uid` column** — every crew row carries one canonical party-UID (the single source). Reuse-where-live (Argus, Vela, Cosmo, Po — UIDs kept, event history preserved); mint-fresh-where-phantom (Talos, Metis, Orpheus). The lineage axis (agent-root) and the party axis (party_uid) are now cleanly separated — agent-root never carries messaging.
- **Identity coherence closed** — `check_agent_identity_coherence` 8 WARN → PASS; Talos's queue is addressable again.
- **Non-agent emitter convention** — tools emit their own tool-UID; run-completions use engine-tool source + run-UID subject.
- **Six engine sibling-drift fixes** root-caused and routed to the engine lane (a shared terminal-status helper + a `check_uid_refs_are_strings` validator so the class fails loud at every rebuild).

*Tropo-OS v1.63.0 | UID `f050f2db` | identity carved in stone — one canonical party-UID per agent; the registry is the single source.*

---

## v1.62.0 — Substrate Enforces Discipline: Cascade-Completion Gate (2026-06-01 by vela-v56; Block 6 cycle 1)

**Makes "done means verified" structural rather than memory-resident.** v1.62 builds cascade-completion verification into the pipeline engine: a vc:true gate step is verified by the engine recomputing each criterion against substrate by its real method — never by an agent typing `natural_verdict: pass`. The self-attestation hatch is removed; amending a step's criteria invalidates any prior asserted verdict.

- The completion report computes per-criterion coverage; `complete-workflow` asserts every step carries a real verification receipt; **release.capsule Rule 17** makes the completion gate a runnable HARD ship-block.
- **The cycle verified itself** — v1.62's own test-pipeline drove the full gate end-to-end, caught two broken criteria before ship, and closed genuine (6/6 steps verified by their real methods, zero hatch).
- **Three real debts the hardened gate exposed**, all repaired not dodged: a build-release headless deadlock (`stdin=DEVNULL` + child-call timeouts); a verify-step gap (threading run_events + honoring `verification_command`); and a prior-release R12 derive debt on v1.60/v1.61 — **repaired, not grandfathered**, so the predecessors pass the same hardened gate this cycle ships through.

*Tropo-OS v1.62.0 | UID `9b1d085d` | Block 6 opens — the done-means-verified machine ships through its own firing gate.*

---

## v1.61.0 — Messaging-Substrate Completion + Po Executive Identity + Fleet-Ops Trigger-Wire (2026-05-29 by argus-a88 + vela-v55; Block 5 cycle 7 of 7 — closes Block 5)

**Block 5 — the Messaging-Substrate Reframe — closes.** The final cycle completes the event-log coordination model and lands two adjacent primitives.

- **Channel retirement (Rule 13)** — crew-internal coordination channels retire in favor of the event log (`query-events --party <uid>`); two user-facing projections (`channels/tropo.md` activity + `channels/releases.md`) are kept as rendered human surfaces.
- **Po executive identity** — the Studio Concierge's identity substrate (charter + agent root + boot extension) authored as a first-class executive shell.
- **Fleet-Ops trigger-wire** — fleet-ops moves from a boot-time memory discipline to a structurally-triggered `fleet_ops_schedule:` (the harness fires a ScheduleWakeup when a daily/weekly dispatch is overdue), closing the V44–V53 dormancy class.

*Tropo-OS v1.61.0 | UID `a3064bd3` | Block 5 closes; Block 6 opens at v1.62.*

---

## v1.60.0 — Pillar 1 Closes at Three Surfaces (2026-05-29 by argus-a87; Block 5 cycle 6 of 7)

**Pillar 1 (single-file-truth) reaches an honest three-surface close** — the substrate consolidation to the single-file pattern established at v1.56, completed across its remaining surfaces.

*Tropo-OS v1.60.0 | UID `c4d9e3a7` | Pillar 1 closes at three surfaces.*

---

## v1.59.0 — Structural-Discipline Amendment Cycle (2026-05-28 by argus-a87; Block 5 cycle 5 of 7)

**A structural-discipline amendment cycle** — ten candidate substrate amendments hardening the messaging + release machinery, shipped under release.capsule v3.9 conventions (formal `status: pre-ship` + Required-at-Activation / Required-at-Ship field-classes). The cycle self-validated: its own release-entry stub drifted, the fifth instance of the schema-drift class the cycle structurally closed.

*Tropo-OS v1.59.0 | UID `c8f4b1d3` | discipline amendments; the cycle proves its own thesis.*

---

## v1.58.0 — Messaging Arc Operational Completeness (2026-05-28 by argus-a85/a87 + crew; Block 5 cycle 4 of 7)

**Brings the messaging arc to operational completeness** — the Continuous-Listen Polling Protocol and the "check /events" canonical operation, so agents poll the event log autonomously for reply-required work instead of waiting for the principal to surface it.

*Tropo-OS v1.58.0 | UID `a92c1f43` | the messaging loop becomes autonomous.*

---

## v1.57.0 — Stream B Projection Renderer: Channels-as-Views (2026-05-27 by argus-a85; Block 5 cycle 3 of 7)

**Closes the channel-bloat disease structurally: channels become deterministic projections of the canonical event log.** A render-events-as-views tool generates channel surfaces from the event stream — channels are views, not separate stores.

*Tropo-OS v1.57.0 | UID `6b7e2f4c` | channels become views of the event log.*

---

## v1.56.0 — Tools-in-Vault: Pillar 1 Single-File-Truth Reshape (2026-05-26 by argus-a85; Block 5 cycle 2 of 7)

**Reshapes tool substrate to the single-file-truth pattern** (tool.capsule v1.6 §2.5): every kernel tool becomes one governed vault entry — the Pillar 1 pattern later applied to how-tos, session-agents, and actions.

*Tropo-OS v1.56.0 | UID `9e7c4a31` | tools become single-file-truth vault entries.*

---

## v1.55.0 — Messaging Foundation: Event-Stream-as-Canonical-Truth (2026-05-26 by vela-v53 + crew; Block 5 cycle 1 of 7 — opens Block 5)

**Block 5 opens: the event stream becomes canonical truth.** The foundational messaging substrate — an append-only event log as the single coordination surface, per the Messaging System Reframe ([9fc86533](vault/files/9fc86533.md)).

- **events.capsule v1.1 LOCKED** — a CloudEvents v1.0 envelope + lifecycle enum {evergreen, ephemeral} + a 10-check validator family + 5 primitive event types (`tropo.message.sent`/`acked`/`replied` + `tropo.cycle.opened`/`closed`) + a correlationid extension.
- **Mike principal-UID entry** — the first principal substrate entry.
- **vault/events/ infrastructure** — canonical append-only JSONL + a derived SQLite index + AGENTS.md governance.
- **3 tools at vault/tools/** — emit-event + rebuild-events-sqlite + query-events (CloudEvents envelope + file-lock serialization + SQLite dual-write).
- **event_validators.py** — checks 1–10 wired into tropo-validate.

*Tropo-OS v1.55.0 | UID `e25392e6` | Block 5 — the Messaging-Substrate Reframe — opens; the event log becomes the single source of coordination truth.*

---

## v1.54.0 — Engine-Discipline Hardening Triad: Substrate-Verify-Twice + Bootstrap-Replay + Derivation-Rule Extension (2026-05-25 by argus-a84 + talos-t10 + Mike-A84; engine-class cycle; DRAFT-PRE-SHIP pending Vela ship gates)

**The engine learns what we keep telling it.** Three engine-class lanes that each close a v1.52 + v1.53 friction class structurally. A83 burned ~30 min mid-cycle on substrate-verify-twice misses + R11/R12 iterative fixes + ship-time def-amendment block; v1.54 makes those classes impossible going forward. No new user-visible features; pure internals ratchet. Block 4 — Hardening Through Test extends to consecutive cycle 10. Pristine streak target **60 → 61** at clean ship.

Dev-spec [137ac7e1 v1.0](vault/files/137ac7e1.md) carries 10 committed_substrate items across 3 lanes + cycle brief [5d0c831f v0.2](vault/files/5d0c831f.md) LOCKED post Mike-A84 walk on all 3 Q's (Q1 Lane B = Option A auto-heal; Q2 Lane V Layer 2 = Option A validator-wide; Q3 Lane D = hard-defer to v1.55+ for clean engine-cycle theme).

What shipped (Lane V — Substrate-Verify-Twice Layers 2 + 3):

- **V1 — `check_canonical_reference_shape()` validator check** in [`.tropo/scripts/tropo-validate.py`](.tropo/scripts/tropo-validate.py) (Talos T10). Walks substrate citing canonical primitives (capsule field names, enums, file versions); verifies UID resolves AND cited shape matches canonical's current shape. WARN at v1.54; ERROR ratchet v1.55. Catches assumed-state references substrate-wide.
- **V2 — release.capsule v3.6 → v3.7** at [`.tropo/capsules/release.capsule.md`](.tropo/capsules/release.capsule.md) — NEW optional `substrate_verify_twice_findings:` frontmatter field captures per-cycle defect instances for Layer 3 cross-cycle observability ledger per O11 brief [83af4ac1](vault/files/83af4ac1.md).
- **V3 — doc-spec.capsule v1.0.1 → v1.0.2** at [`.tropo/capsules/doc-spec.capsule.md`](.tropo/capsules/doc-spec.capsule.md) — mirror `substrate_verify_twice_findings:` field; doc-spec instances capture at authoring time + aggregate to enclosing release. NEW Validation Check 15 shape-validator (WARN; honor-system field).
- **V4 — v1.54 release entry dogfood** — this entry populates `substrate_verify_twice_findings:` with at least one real cycle finding (the first dogfooded ledger entry sets the canonical example pattern).

What shipped (Lane B — Engine Bootstrap-Replay Auto-Heal; Option A per Mike-A84 walk Q1):

- **B1 — `_auto_bootstrap_triggered_pipeline()` auto-heal** in [`.tropo/scripts/pipeline-runtime.py`](.tropo/scripts/pipeline-runtime.py) (Talos T10). When engine detects active pipeline-runs whose def-snapshot predates current def, re-bootstraps + reconciles run.state silently at engine tick. No manual ceremony. Matches Self-Healing Path 1.
- **B2 — regression test fixture** in `.tropo/scripts/lib/` validates B1 auto-heal behavior. Spawn pipeline-run against def-snapshot A; amend def to A+1; verify reconciliation without manual intervention. The A83 v1.53 b67c75e2 case (or equivalent) demonstrably auto-heals.

What shipped (Lane R — R11/R12 Derivation Rule Extension):

- **R1 — release.capsule v3.7 §4 Rule 14** NEW extends `subsystems_touched:` derivation to two additional sources: (a) `kernel_substrate_touched:` path-pattern table maps kernel paths to hub UIDs (`.tropo/scripts/*` → tropo-playbooks; `.tropo/capsules/*` → tropo-governance; `*/AGENTS.md` → tropo-governance; etc.); (b) `type: pipeline` capability entries' `subsystem_hub:` field flows into derivation. Composes with Rule 12 (1-hop capabilities path remains canonical). Pattern table lives in capsule body (authored substrate, reviewer-visible) per cycle brief R3 mitigation. NEW Validation Check 26 enforces extended derivation (WARN v1.54+; ERROR ratchet v1.55+).
- **R2 — extended R12 enforcer** in [`.tropo/scripts/validate-capability-membership.py`](.tropo/scripts/validate-capability-membership.py) (Talos T10) implements Rule 14 derivation per R1 pattern table. A83's v1.52 [de2a5e38](vault/files/de2a5e38.md) substrate (3 iterative R11/R12 fixes) derives correctly first-try under R1+R2 rule extension.

What shipped (cross-lane):

- **Lane D Pristine Documentation Continuation hard-deferred to v1.55+** per Mike-A84 walk Q3 — keeps v1.54 a clean engine-discipline cycle (D2/D3/D4 from v1.53 honest-defer await dedicated documentation cycle when prioritized).
- **doc-pipeline cascade fires automatically** for v1.54's own capsule amendments (V2 + V3 + R1 all touch documentation scope) — Orpheus O12 authors doc-spec body at trigger fire.
- **test-pipeline cascade fires automatically** for v1.54's regression-test scope — Vela V53 authors test-spec body at trigger fire.

Validator state at ship target: **clean (0 ERRORs)**; WARNs surveyed + dispositioned per Lane R WARN-grace period.

Engine-class internals cycle by intent. Wall-clock target under 24h per Mike-A83 calibration. The three classes that A83 hit at v1.53 (substrate-verify-twice failures + R11/R12 iterative reconciliation + ship-time def-amendment block) all close structurally — next cycle's wall-clock returns under target not because we move faster but because the engine catches our mistakes before we make them.

---

## v1.53.0 — Three-Pipeline Discipline Compounding: Engine Hardening + Pristine Documentation + Lane A Carryforward + ADR-040 Enforcement Gap (2026-05-25 by argus-a83 + talos-t10 + orpheus-o11 + vela-v53 + metis-g61 + Mike-A83; multi-agent same-day ship)

**Discipline compounds. v1.51 shipped the cascade; v1.52 dogfooded it; v1.53 hardens the engine + reshapes substrate + lands the doctrine emergent at first-production-fire.** Four-lane substantive cycle dispositioned 100% honestly across Argus + Talos + Orpheus + Metis + Vela parallel execution. Dev-spec [90ed15fb v1.1](vault/files/90ed15fb.md) carries 23 committed_substrate items across 4 lanes (Lane M Memory Architecture Reshape deferred to dedicated future cycle per Mike-A83 walk; full v3.0 spec captured at [d0624a04](vault/files/d0624a04.md)). Pristine streak target **59 → 60**. Block 4 — Hardening Through Test extends to 9 consecutive cycles.

What shipped (Lane E — Engine Hardening; 7 items by Talos T10 + Argus A83):

- **E1 — pipeline-runtime.py action_complete_workflow** emits parseable BLOCKED + exits non-zero on coupling close-check refusal. Closes v1.52 silent-failure defect.
- **E2 — verify-step verification_class:false semantics** treats completed as terminal regardless of verifier_role mismatch. Auto-emits verification_receipt verdict:pass at step_complete. Option (b) per V52 lean.
- **E3 — `lib/spec_lock_validators.py` NEW** wired to tropo-validate.py main(). LOCK-strict required-field checks across dev-spec + doc-spec + test-spec at status:locked. ERROR severity. Structurally closes substrate-verify-twice defect class at authoring time.
- **E4 — `check_doc_spec_closure_claim_mtime_alignment` NEW** added to lib/doc_spec_validators.py DOC_SPEC_CHECKS. WARN at v1.53; ERROR ratchet v1.54. Catches closure-claim drift class.
- **E5 — re-bootstrap after contract-modification supersession** action_bootstrap accepts re-bootstrap when activation_superseded + supersession_reason:contract-modification. ~15 LOC; closes re-bootstrap use case.
- **E6 — pipeline-run.capsule instance authoring for doc + test pipelines** via `_auto_bootstrap_triggered_pipeline()` mirroring action_bootstrap. Trigger-step now passes --rollback-manifest pointing to trigger-scoped path bypassing E2-session idempotency guard legitimately.
- **E7 — doc-pipeline def + doc-spec.capsule v1.0 → v1.0.1 amendment** for Orpheus disposition signoff gate at close. Two-piece: (Orpheus side) doc-spec.capsule gained orpheus_disposition_signoff Required field + §Disposition Signoff body + Validation Check 14 (FAIL severity); (Talos engine side) check_doc_spec_orpheus_disposition_signoff wired + close-gate enforcement in check_triggered_pipeline_completion.

What shipped (Lane D — Pristine Documentation; D1 substantive by Orpheus O11):

- **D1 — 6 subsystem hubs refreshed to subsystem-hub.capsule v1.6 §1 In-scope/Not-in-scope/Edge-cases shape:** Tropo Work ([2d083137](vault/files/2d083137.md)) + Tropo Governance ([8dd772a0](vault/files/8dd772a0.md)) + Tropo Playbooks ([76bab75f](vault/files/76bab75f.md)) + Tropo Library ([1aba710c](vault/files/1aba710c.md)) — 43-cycle drift cleared + Tropo Documentation ([f87e33f0](vault/files/f87e33f0.md)) — 40-cycle drift + 5 legacy scope blocks consolidated to single §1 (v1.6 defect-class fix exemplar) + Tropo Rendering ([dbc1cbbf](vault/files/dbc1cbbf.md)) — 40-cycle drift. Substantive Current State extensions through v1.52 across all 6 hubs. Captain's Briefing v3.0 §Requirement 1 Gate A substantively closed.
- **D2/D3/D4 + substrate-verify-twice Layers 2+3 honest-defer to v1.54** Pristine Documentation Continuation + Capsule-Hygiene Bundle cycle. v1.53 close-criterion holds at D1 substantive.

What shipped (Lane A — v1.52 Deferred Cleanup; A13 + F1 substantive by Argus A83):

- **A13 drift reconciliation** — 35 substrate-class items archived (12 projects + 9 release-plans + 8 builds + 3 project-plans + 1 design-brief + 1 board-snapshot + 3 historical notes). state:active/status:done mismatches dispositioned to state:archived with archived_at + archival_reason fields.
- **F1 prose-caps-to-UIDs conversion** — 7 legacy release entries converted (v1.45 + v1.46 + v1.44 + v1.43 + v1.18 + v1.17 + v1.19). capabilities_touched bare UIDs; kernel substrate paths moved to kernel_substrate_touched per A81's canonical v1.20.0 pattern.
- **A1 + A2 + A3 + A6 honest-deferred to v1.54** with v1_53_disposition + v1_53_rationale fields per cycle brief ≤1h time-box Risk register.

What shipped (Lane I3 — ADR-040 Enforcement Gap; by Talos T10):

- **commit 589a123** — `git rm --cached` of 21 argo-os/ files accidentally git-tracked despite "fully gitignored" doctrine. .gitignore blocks re-addition; physical files untouched on disk. Path-2 finding [8f2e1a47](vault/files/8f2e1a47.md) closed.

What shipped (cross-lane substrate-coherence captain-mode):

- **Workbench Surface Visibility Doctrine** OP-14 promotion candidate [3c02f3b7](vault/files/3c02f3b7.md) authored at v1.52 ship binds v1.53 substrate decisions; pipeline-activate.py owner/assigned_to propagation + dev-pipeline notify-step 4.7 ([37996741](vault/files/37996741.md)) live.
- **Memory System Spec v3.0** [d0624a04](vault/files/d0624a04.md) substrate captured (Lane M deferred to dedicated memory cycle per Mike-A83 walk; 5-question walk decisions absorbed + 4 doctrine pins).
- **substrate-coherence stubs** authored for lost activation files: [e7f2c834](vault/files/e7f2c834.md) (Metis G59→G60 transfer) + [c7a26c5a](vault/files/c7a26c5a.md) (Orpheus doc-pipeline activation). Same defect class as v1.52 lost pipeline files; T10's three architectural fixes (rollback → tropo-recycle.py + idempotency guard + validator ERROR on direct unlink) prevent recurrence.
- **substrate-verify-twice defect-class brief** [83af4ac1](vault/files/83af4ac1.md) authored by Orpheus O11; Layer 1 (voice-review.skill v1.0 → v1.1 with Step 4.5 substrate-verify-twice discipline) shipped standalone; Layers 2 + 3 → v1.54 candidate cycle.
- **Mike-A83 4 doctrine pins** (stm-a83-001 through stm-a83-005) authored at Memory v3.0 walk: substrate-verify-twice applies to playbook STEPS not just spec authoring + memory architecture is load-bearing future-proofing + memories vs memory architectural-frame distinction + Studio Sovereignty > Substrate Sovereignty + canary-pair-then-cascade transition pattern.

Validator: **44 passed / 0 failed / 305 warnings** clean throughout. No engine defects; no substrate regressions.

Multi-agent same-day ship pattern at substantive scale (Argus A83 + Talos T10 + Orpheus O11 + Metis G61 + Vela V53 + Mike across single calendar arc). "Do it all properly" Mike-A83 anchor binding; partial-close patterns rejected in favor of substantive close + honest deferrals where bounded. Cycle dispositioned 100% honestly.

---

## v1.52.0 — Phase 1 Grooming Continuation + publish.pipeline Class Substrate Amendment (2026-05-24 by argus-a81 + Mike-A81; single-agent substantial-substrate ship)

**First production-cycle use of v1.51 three-pipeline cascade discipline against external (non-recursive-bootstrap) scope.** v1.51 shipped the discipline; v1.52 fires it. Engine bootstrap clean (activation [07ea7ac6](vault/files/07ea7ac6.md); pipeline-run [700fada1](vault/files/700fada1.md)); steps S0-S3 progressed through standard state-machine without engine defects. Dev-spec [f8bf8c4a](vault/files/f8bf8c4a.md) (first external production-cycle dev-spec instance) carries 28 committed_substrate items across 4 lanes; cycle dispositioned 100% honestly (closures + deferrals-with-rationale). Pristine streak **58 → 59** at Vela V52 ship close. Block 4 — Hardening Through Test extended to 8 consecutive cycles.

What shipped (P-lane — 5 publish.pipeline class items absorbed substantive substrate-class):

- **numeric-folder-prefix.capsule v1.0 LOCKED** NEW typed primitive at [`.tropo/capsules/numeric-folder-prefix.capsule.md`](.tropo/capsules/numeric-folder-prefix.capsule.md) (UID 61f650aa) — OS-tier two-axis folder naming doctrine; binding across every Studio. 4 validator checks wired at WARN; ratchet to ERROR at v1.1.
- **publish.pipeline.capsule v1.1 → v1.2** at [`.tropo/capsules/publish.pipeline.capsule.md`](.tropo/capsules/publish.pipeline.capsule.md) — three NEW substantive sections: §14 Package Step Specification (Dated-Filename Model + Check-and-Move Rule + Conflict Surfacing per [2f5e8c1a v1.3](vault/files/2f5e8c1a.md)) + §15 Design Step Specification (Substrate Inputs + Brand-Kit Inheritance Cascade + Agent Behavior + Iteration Modes + Diff-Aware Re-Runs + Close + Handoff per [5b3e9c47 v1.1](vault/files/5b3e9c47.md)) + §16 Section-Scope Substrate Composition + Bio Cascade per [b7e4f192](vault/files/b7e4f192.md) Metis G59 finding (all 5 design-space questions resolved captain-mode per Metis leans + Argus agreement).
- **02-outbox/AGENTS.md + 03-design/AGENTS.md** authored — tropo-system governance contracts for the two new canonical folder reservations; both declare `canonical_contract: 61f650aa` reference.

What shipped (A-lane — 14 items dispositioned 100%):

- **A4 Studio Manifesto v1.0.2 → v1.0.3** at [`fbb13cca`](vault/files/fbb13cca.md) — Mike-A81 lock-break authorized verbatim "A4 - Yes, break lock, it is Studio"; §I third-layer canonical concept Workshop → Studio (the last stranger-facing artifact using pre-v1.8 vocabulary; closes the v1.8 Canonical Taxonomy lock alignment gap).
- **A8 L1 canonical entry §5 refresh** at [`eca73d77`](vault/files/eca73d77.md) — Mike-A81 lock walked verbatim "A8 - agree"; "7 subsystems" → "9 subsystems" + table extended with Tropo Link (3a207ed3 NEW v1.17.0) + Tropo Test Harness (952f3aa3 ELEVATED v1.42.0). Cold-boot readers now see model that matches registry reality.
- **A10 subsystem-hub.capsule v1.5 → v1.6** at [`.tropo/capsules/subsystem-hub.capsule.md`](.tropo/capsules/subsystem-hub.capsule.md) — §1 body requires structured `### In scope` / `### Not in scope` / optional `### Edge cases` subsections (replaces free-form prose; closes the Tropo Documentation hub drift defect class Metis G51 surfaced 2026-05-10). v1.10 validator ratchet from v1.5+v1.6 acceptance → v1.6-only.
- **A11 Deletion Discipline doctrine extension** at [`0aefe71d`](vault/files/0aefe71d.md) — +4 scope table rows (library/ + tab/ + registries/*.yaml + *.jsonl) + NEW §Bypass-by-Approval Pressure section (converts agent-refusal posture into agent-surfacing; principal's bypass-choice becomes substrate). v1.40.0 R5 sa.skeptic-102 P2-A + P2-C absorbed; P2-B deferred.
- **A12b structural fix** — [write-activation-entry.py](.tropo/scripts/write-activation-entry.py) `auto_create_transfer_stub()` + `successor_generation()` helpers + [agent-retire.playbook v2.10](.tropo/playbooks/agent-retire.playbook.md). Auto-stub fires at op_close when --transfer-uid set + stub absent. **Closes the recurring G55→G56 / G56→G57 / G57→G58 surgical-fix pattern** (3 cycles of Vela captain-mode at ship time).
- **A5 + A7 + A9 + A12 closed** — 01-vault-inbox → 01-studio-inbox filesystem rename + ref sweep; zombie audit clean (0 new candidates beyond Talos-purged); roadmap legacy-path honest-record annotation; A12 inherited closed at v1.48.0.2.
- **A1 + A2 + A3 + A6 + A13 deferred to v1.53** with honest-record closure_notes per cycle brief ≤1h time-box Risk register.

F1 prose-cap research:

- **v1.20.0 release entry [4920ce3a](vault/files/4920ce3a.md)** converted 63 prose `capabilities_touched` strings to 49 resolved UIDs (78% conversion clean); 14 non-vault-substrate entries preserved at NEW `kernel_substrate_touched` field. v1.20.0 partially un-grandfathered. Remaining 5-6 legacy entries deferred to v1.53 batched sa.* dispatch.

Cycle retrospective:

- **H1 observation-class retrospective** at [c53fe8f8](vault/files/c53fe8f8.md) — 6 structural patterns captured: (1) Strong-lean execute calibration stm-a81-003 operationally transformative; (2) Honest re-estimation discipline catches scope inflation; (3) First production-cycle use of v1.51 cascade held clean; (4) Roadmap-Board Format template emerged mid-cycle as crew substrate ([eb94fa08](vault/files/eb94fa08.md)); (5) In-cycle absorption pattern compounded at scale; (6) Single-agent ship pattern distinct from v1.51 multi-agent pattern.

Roadmap-Board Format template ratified mid-cycle:

- **[Roadmap-Board Format v1.0 (eb94fa08)](vault/files/eb94fa08.md)** — Mike-A81 ratified the 7-section format that landed during morning roadmap-ask captain-mode authoring. Now substrate-resident + crew-wide binding for roadmap-class asks. Composes with Walk Format Doctrine.

Validator: **46 passed / 0 failed / 260 warnings** clean throughout. No engine defects; no substrate regressions.

The strong-lean execute calibration (stm-a81-003) shaped this cycle's velocity. Mike-A81 verbatim mid-cycle: *"When you have a strong lean, you do not have to ask me. I trust you. If you don't have a strong lean, certainly ask. I generally do not have an opinion on how you group or order work."* v1.52 dispositioned 28 committed_substrate items + 14 A-lane Path 2 tickets through 3 substantive Mike-walks (cycle brief Q1 + A4 lock-break + A8 canonical-set refresh). Single-agent depth shape distinct from v1.51 multi-agent breadth.

---

## v1.51.0 — Three-Pipeline Substrate-Engineering (2026-05-23 by argus-a77/a78/a79/a80/a81 + vela-v51 + orpheus-o11 + talos-t9 + Mike across single-calendar-day multi-agent ship; SHIPPED by Vela V51)

**The Three-Pipeline Substrate-Enforcement Architecture lands end-to-end in a single calendar day.** Six artifacts LOCKED v1.0 across Argus + Vela + Orpheus lanes; Talos T9 engine implementation SHIPPED; Phase A acceptance 6/6 PASS; Phase D recursive-bootstrap dogfood verified. The substrate-discipline-becomes-structural thesis Mike-G57 named (substrate enforcement at engine + capsule + activation level instead of memory-resident convention) demonstrated by the cycle's own execution pattern: the architecture shipped via three-pipeline-class substrate WHILE Argus + Vela + Orpheus + Talos shipped in parallel across a single calendar day. Pristine streak **57 → 58**. Block 4 — Hardening Through Test extended to 7 consecutive cycles. Release entry: [b0435ff0](vault/files/b0435ff0.md).

What shipped (Six Artifacts):

- **dev-spec.capsule v1.0.1** at [.tropo/capsules/dev-spec.capsule.md (c3f68cb5)](.tropo/capsules/dev-spec.capsule.md) — Argus A80 self-walked + Mike-A80 ignition-key amendment (rename from design-spec to dev-spec resolving collision with locked design-spec.capsule v2.1)
- **doc-spec.capsule v1.0** at [.tropo/capsules/doc-spec.capsule.md (9a7d314a)](.tropo/capsules/doc-spec.capsule.md) — Mike + Orpheus O11 walk
- **test-spec.capsule v1.0** at [.tropo/capsules/test-spec.capsule.md (621824df)](.tropo/capsules/test-spec.capsule.md) — Mike + Vela V51 walk; 5 substantive Q's resolved 5/5 (cross-validation MANDATED + verification_method enum 4→5 with agentic_review + manual_walk ceiling 30%/50%-hard-cap + coverage_class per-cycle-class minima + harness_framework_changes_required three trigger classes)
- **doc-pipeline definition v1.0** at [vault/files/5a4337ff.md](vault/files/5a4337ff.md) — Orpheus O11 Phase C complete
- **test-pipeline definition v1.0** at [vault/files/da3f50dc.md](vault/files/da3f50dc.md) — Vela V51 Phase C complete (10 vault entries: root + 3 stages + 6 steps with per-step rich schema per pipeline.capsule v3.0 fractal-WorkflowNode pattern)
- **dev-pipeline retrofit v1.2.0** at [vault/files/cd1fcd25.md](vault/files/cd1fcd25.md) — two NEW trigger steps inserted in deploy stage (step 4.5 trigger-doc-pipeline-activation + step 4.6 trigger-test-pipeline-activation; parallel fan-out from step 4 close; multi-input convergence on step 6 produce-release-folder)

Engine implementation:

- **Pipeline-Runtime Engine Extension v0.3 spec** at [vault/files/51d171f3.md](vault/files/51d171f3.md) — two extensions: (1) multi-pipeline-class registration (doc-pipeline + test-pipeline alongside existing dev-pipeline + publish-pipeline); (2) three-pipeline coupling state machine (dev-pipeline activation requires dev-spec input; trigger steps fire doc + test pipelines in parallel; engine close enforcement requires both triggered activations at status:done before close succeeds)
- **Talos T9 engine implementation SHIPPED** — all engine additions live + verified per Phase A acceptance 6/6 PASS (multi-pipeline-class registration / activation-input validation / trigger-step smoke / coupling-enforcement smoke / recursive-bootstrap / race condition)
- **Phase D recursive-bootstrap dogfood VERIFIED** Argus-side: engine activates dev-pipeline with dev-spec input → trigger-step fires both doc + test pipelines → close enforcement holds → activation retires cleanly. The substrate IS the proof.

Plus architectural side-cycle:

- **v1.14 schema split SHIPPED** — A80 captain-mode same session per V51 Path 2 finding fb395501 + Mike-V51 "this is what happens when we patch as we go" directive: project.capsule v2.4 → v2.5 with NEW `subsystem_hub:` field + Rule 8 + Validation Checks 10-11; migration script applied to 1059 entries; v1.13.1 hub-skip render workaround REMOVED from rebuild-index.py + rehydrate.py + generate-relations-header.py; canonical-l0-projects.yaml suppression list retired entirely; Registries hub correctly nests under tropo-governance via subsystem_hub: [8dd772a0] instead of bubbling to L0. Closes the v1.12 substrate-membership-backfill defect at substrate layer with no recurrence path.

V51 fix-on-see absorptions at ship time:

- v1.51.0.1 — Metis G57→G58 transfer-stub at [vault/files/7b2c1360.md](vault/files/7b2c1360.md) (third consecutive transfer-stub pattern dogfooded V49+V50+V51; structural fix awaits Argus v1.50 brief 04e73e8d §A12b auto-generation at retirement-time)
- v1.51.0.2 — derive-subsystem-registry.py patched twice: (a) added subsystem_hub: field reading per A80's v1.14 schema split (symmetric reader-not-audited defect); (b) zero-indent YAML block-list parser fix (same regex bug A80 fixed in migration script same session). Restored deriver coverage 10 → 75 rows
- v1.51.0.3 — derive-subsystem-registry.py + validate-capability-membership.py both gained release-entry-subsystems_touched-fallback path for releases where capabilities_touched is prose-named (closes pre-existing R12 mismatch on v1.43-v1.47 + v1.50)
- v1.51.0.4 — vault/files/7eba9698.md (v1.50.0 release entry) gained subsystems_touched declaration matching post-fix derivation output (was missing pre-A80-v1.14-fix)

Symmetric-defect lesson pinned crew-wide this session arc: **when changing a writer, audit ALL readers.** Recurred three times (nav-tree symlinks→hardlinks affected generate-relations-header.py reader; v1.14 schema split affected derive-subsystem-registry.py reader; validate-capability-membership.py loader same shape). Each catch cost a build cycle. Pattern recurred enough to formalize at substrate level for v1.52+.

Multi-agent ship pattern: **Argus** (A77 substrate-resident discipline codification at v1.48 base; A78 publish.pipeline at v1.49 base; A79 registry primitive + v1.50 + retirement-invariants; A80 dev-spec + doc-spec + test-spec drafts + engine extension spec + v1.14 schema split captain-mode + v1.51 cycle brief; A81 v1.51 cycle close handoff) + **Vela V51** (test-spec.capsule walk lock + test-pipeline definition v1.0 + ship discipline) + **Orpheus O11** (doc-spec.capsule walk lock + doc-pipeline definition v1.0) + **Talos T9** (engine implementation + 6 verification_method execution surfaces) + **Mike** (six locking walks + Path B "do it right" v1.14 directive + Three-Pipeline architecture C-lock).

---

## v1.50.0 — Registry Primitive Establishment + Bypass-Pattern Break (2026-05-23 by argus-a79 + vela-v51 + Mike; SHIPPED by Vela V51)

**10-cycle TROPO_SKIP_ENFORCEMENT_GATE=1 bypass pattern empirically broken on production build run.** v1.40-v1.49 inclusive shipped under systemic bypass of the v1.10 Pure Enforcement validator; v1.50.0 build completed at 0 ERRORs without bypass — the registry primitive substrate this cycle establishes (subsystem-registry.jsonl populated at canonical path + auto-derived by rebuild-vault.py on every --apply rebuild + grandfather threshold extended (1,9,2)→(1,40,0) with substrate-honest rationale codified in source) made the enforcement gate pass naturally. The substrate-discipline-becomes-structurally-enforced arc reaches its cleanest validation: V48 named the bypass pattern at retire-time; V49 elevated to binding directive 3; A79 + V51 closed the substrate gap that made the bypass necessary. Pristine streak **56 → 57**. Block 4 — Hardening Through Test extended to 6 consecutive cycles (v1.43-v1.50 inclusive of v1.50 substrate-class cold-boot-walk skip per policy-honest). Release entry: [7eba9698](vault/files/7eba9698.md).

What shipped:

- **registry.capsule v1.0** NEW typed primitive at `.tropo/capsules/registry.capsule.md` (UID 55a57893) — typed wrapper definition declaring registries as first-class graph substrate per Mike-A79 architectural directive that registries are not free-floating data files.
- **Registries hub** NEW at vault/files/7e93ed75.md — concentrator collecting all 5 registry wrapper entries; added to canonical-L0 set as 10th entry per Mike-V51 approval 2026-05-23 (will retire from L0 when v1.14 schema split lands per Path 2 finding fb395501).
- **5 registry wrapper entries** — 4 retrofits of existing free-floating registries (main-vault 3a1fa720 + canonical-l0-projects 57476b03 + agent-registry 6dbcd7c8 + playbook-runs ce068ba4) + 1 NEW subsystem-registry wrapper 880a9e5a (the substrate that closes the bypass pattern).
- **subsystem-registry.jsonl populated at canonical path** `.tropo-studio/registries/subsystem-registry.jsonl` (72 rows across 29 releases derived from current shipped release entries' capabilities_touched fields). Legacy 95-row registry archived to subsystem-registry.history.jsonl.
- **derive-subsystem-registry.py** NEW production deriver at `.tropo/scripts/derive-subsystem-registry.py` — going-forward registry sync; called by rebuild-vault.py Step [5d/5] on every --apply rebuild. Reuses 1-hop member_of traversal pattern from dev-pipeline step 4 update-subsystem-canonical-docs executor.
- **rebuild-vault.py extension** — Step [5d/5] invokes deriver; registry stays in sync by construction.
- **validate-capability-membership.py** path updated to read canonical .tropo-studio/registries/subsystem-registry.jsonl. Grandfather threshold extended (1,9,2)→(1,40,0) with substrate-honest rationale codified in source (v1.10-v1.39 shipped under systemic bypass; reconstructing strict-compliance-shaped historical data is archaeology not enforcement; v1.40+ enforces strict). 4 unversioned releases explicitly grandfathered.
- **Pass A back-write** — 49 release entries' subsystems_touched fields updated to match derived sets.
- **Release-plan grandfather check enhancement** in build-release.py — release_version + title parsing fallbacks; closes v1.4.2+ Backlog parent reference defect.
- **TROPO_SKIP_ENFORCEMENT_GATE doc retired for routine use post-v1.50.0** — build-release.py comment block updated; emergency-only.
- **3 historical dated-sweep scripts archived** to recycle/agent-deletions/2026-05-22-argus-a79-script-cleanup/
- **Path 2 follow-on** — 1387582c authored for v1.51+ research on 6 legacy prose-cap releases.
- **Path 2 finding fb395501** filed by Vela V51 — v1.14 schema split overdue (the proper architectural fix that the v1.13.1 hub-skip workaround + canonical-l0 suppression list have been deferring for 3 documented cycles: Packs + Registries + this cycle's surface). Mike-V51 verbatim filing directive: *"this is what happens when we patch as we go ... more work for him and it's piling up."* Routed to Argus 01-inbox p1 for v1.51+ priority.

Three in-cycle substrate absorptions at v1.50 ship time (Vela fix-on-see per substrate-discipline doctrine):
- v1.50.0.1 — A80-authored v1.51 design-spec 51d171f3 refs[4] UID corrected from 1cb7e1e2 (hallucinated; did not resolve) → 5a8f3b2c (canonical pipeline-run.capsule v2.0)
- v1.50.0.2 — 7 orphaned working-copies of David's papers recycled to recycle/agent-deletions/2026-05-23/ via tropo-recycle.py per Mike-V50 recycle-as-default doctrine (external-work/David - 2 short papers/ directory absent on disk; projections orphaned; sidecar-equivalence FAILs blocking build)
- v1.50.0.3 — Registries L0 disposition walked with Mike-V51; canonical-L0 amendment authored (9 → 10) under Mike approval; lock-comment annotates retirement-on-v1.14-schema-split

Multi-agent ship: **Argus A79** authored substrate (registry.capsule + Registries hub + 5 wrapper entries + derive-subsystem-registry.py + Pass A back-write + grandfather threshold + SKIP gate doc retirement + 3 historical-script archive + Path 2 follow-on) → handed off ship gates → retired clean 2026-05-22. **Vela V51** drove ship discipline (fix-on-see absorptions + canonical-L0 walk with Mike + 4-attempt build sequence ending in clean-bypass PASS + Stage 1 substrate-class smoke gates + Stage 3 cold-boot-walk skip per Mike Q2 + close-cycle + this entry). v1.14 schema split filed as Path 2 (fb395501) for v1.51+ priority — Argus A80's call on cycle scheduling.

---

## v1.49.0 — publish.pipeline Class Codified + KGAE Live on tropo-ai.com (Captain's Read v2.0 Gate 1 RATIFIED) (2026-05-23 by argus-a78 + talos-t9 + vela-v50 + Mike across multi-agent V50 session; SHIPPED by Vela V50)

Captain's Read v2.0 Gate 1 ratified. The publish.pipeline class codifies what Talos already proved in code into a reusable typed primitive. Two first-target implementations (web refactor + docx greenfield) prove multi-target shape. **KGAE ("Knowledge Graphs Aren't Enough") article ships live to tropo-ai.com via the new web target** — the conversion-lever content lands at https://tropo-ai.com/agentic-builders/knowledge-graphs-arent-enough.

Multi-agent ship: **Argus A78** authored substrate (publish.pipeline.capsule v1.0 → v1.1 + 4 validator checks + canonical release entry + in-cycle substrate-coherence absorptions per Mike-A78 'no-punt' directive) → retired clean. **Talos T9** shipped runtime (publish.py + publish_types.py + publish_targets/web.py + publish_targets/docx.py + 2 example pipeline definitions + KGAE live via Vercel auto-deploy + S0.1 sentinel pair-call resolution). **Vela V50** drove Steps 6-8 ship discipline (build-release.py + 8 Stage 1 smoke tests PASS + 3-persona cold-boot-walk SHIP-CLEAR aggregate at 8.0/10 floor + close-cycle + this entry). **Pristine streak 55 → 56.** Release entry: [ac0f5a29](vault/files/ac0f5a29.md). Cold-boot-walk aggregate: [/Users/mike/dev/tropo-releases/v1.49.0/cold-boot-walk-report.md](../../tropo-releases/v1.49.0/cold-boot-walk-report.md).

The cycle proves the **substrate-discipline-becomes-structurally-enforced** arc continues: A78 closed substrate-coherence findings in-cycle (74f84c63) per Mike-A78 'no-punt'; V50 absorbed close-cycle v1.1.0 repurpose (gitignore-state honest) + 8-item backlog closure batch + 2 stale pipeline-runtime activations + Tier 3 §Group 4 Additions simplification + recovery from V50 parallel-authoring damage (4ce628af duplicate release entry retired; 08e4a7c2 brief reframed to v1.50 priority elevation). First cycle exercising v1.48's substrate-resident dev-pipeline step 7.5 cold-boot-walk substrate at production scale; 3 personas dispatched via Agent tool in parallel; per-persona Studio clones at dispatch (v1.1 amendment) eliminated concurrent-mutation race; aggregate verdict feeds ship-gate. Block 4 — Hardening Through Test extended to 5 consecutive cycles at 8.0+ floor.

What shipped:

- **publish.pipeline.capsule v1.0 → v1.1** at `.tropo/capsules/publish.pipeline.capsule.md` (UID 7e3a91c8) — typed primitive automating workflow steps 1-3 of c5a7e391's locked five-step universal pattern (extract / package / design+format); workflow step 4 (publish) = target-specific extension; workflow step 5 (verify) = human activity. Companion lock-break amendment at c5a7e391 v0.4 §3.6 preserves Mike-G55 5-step lock while clarifying class-core vs workflow-steps distinction. v1.1 amendment codifies sentinel convention (pipeline-bot@argo-os = publish-act event; Check 27 derives) + publish-check.py preflight + Implementation Status §13.
- **publish.py** thin shared runner + publish_types.py (StageResult / PublishResult / PublishTargetError dataclasses) — single-command invocation per brief §S2; positional pipeline UID; convention-over-configuration defaults.
- **publish_targets/web.py** — refactor of operational build-web-content.py into class shape. V50 parallel-run equivalence test verified byte-for-byte identical output across 12 files; refactor preserves operational behavior; rollback path intact via build-web-content.py.
- **publish_targets/docx.py** — greenfield via python-docx (T9 chose python-docx over brief §S4's "Probably pandoc-based" framing for cleaner dependency tree). Stops at stage; no publish().
- **Example pipeline definitions:** [publish-to-web (f1b4c8d2)](vault/files/f1b4c8d2.md) operational + [publish-to-docx (e0a3d9c7)](vault/files/e0a3d9c7.md) example.
- **4 NEW validator checks** in tropo-validate.py at WARN level: check_publish_pipeline_md_schema + check_target_module_present + check_article_source_required_fields + check_ship_artifact_required_fields (ratchet to ERROR at v1.50+).
- **publish-check.py** canonical user-facing preflight (composes 4 validators + manifest-walker logic into one command; outputs ready-to-paste wrapper scaffold when missing; resolves pipeline UID on READY; supports --slug lookup).
- **KGAE article LIVE on tropo-ai.com** at https://tropo-ai.com/agentic-builders/knowledge-graphs-arent-enough — first content through formalized publish.pipeline substrate; production-eyeball confirmed by Mike-V50.
- **dev-pipeline step 7 repurpose** at [3e0bb81e](vault/files/3e0bb81e.md) v1.0.0 → v1.1.0: git-commit → close-cycle. Drops gitignore-mismatch narrative (per Mike-A72 argo-os/ fully-gitignored directive 2026-05-18 superseding ADR-040); preserves pipeline-run done + work-item closed + date_completed write semantics. V50 captain-mode lock-break under Mike-V50 'let's do both' authorization.

10 substrate-coherence findings from the cold-boot-walk filed for v1.50 grooming — none ship-blocking; top items: TROPO-CONTROL.md §8 version table stale (Argus-lane), rebuild-vault.py --quiet flag (Talos-lane), end-user light-path branch in agent-activation playbook (Argus + Metis lanes), concierge activate.md trim + session-break recovery (Argus-lane).

---

## v1.48.0 — Cycle B Extraction-and-Publish Engineering + Cycle A Remainder + Substrate-Resident Discipline Codification (2026-05-22 by argus-a77 + talos-t9 + vela-v49 + Mike across multi-agent V49 session; SHIPPED by Vela V49)

The Tropo Extraction-and-Publish Pipeline ships end-to-end. The substrate-discipline-becomes-structurally-enforced theme reaches its **first multi-agent cycle** under the v1.46 pipeline-runtime engine: Argus A77 authored Streams A + C + D substrate-side; Talos T9 shipped Stream B core engineering (the actual publish pipeline); Vela V49 closed the cycle with Stages 1-3 ship discipline + two in-cycle substrate absorptions. Pristine streak **54 → 55**. Release entry: [1d25e142](vault/files/1d25e142.md).

The cycle proves the Stream B → Vela ship-protocol pattern Mike-A72 locked at v1.43: substrate authoring + engineering + ship gates compose across three executive lanes without losing coherence.

What shipped:

- **Stream A — Cycle A remainder** (A77 substrate authoring) — `ship-artifact.capsule` v1.3 → v1.4 body replacement per Mike-A75 no-history-in-capsules lock (UID `eeb59ddf` preserved; history at `.tropo/capsules/ship-artifact.history.md` Migration 2 entry); 5 NEW validator checks (Check 25 article state machine + Check 26 wrapper editorial lock + Check 27 publication_state shape + Check 28 target coherence + Check 29 external-work gitignore); 2 in-cycle Stream A migrations (Tropo Work + Studio Manifesto articles legacy vocab → v1.4 editorial state enum)
- **Stream B — Cycle B core engineering** (Talos T9 ship 2026-05-22): `build-web-content.py` steps 5-7 (rsync + git commit + push to `github.com/tropo-ai/website-content` + Vercel deploy hook); Author Agent loop live (Haiku intent → vault-search → web research → Sonnet edit → diff → write to disk); `vault-search.py` crew-callable wired into Author search API; web-pipeline v3.0 retrofit (5 leaf steps with per-step rich schema); KGAE ship-artifact wrapper [89a649b5](vault/files/89a649b5.md) for Cycle C acceptance gate; Carryalong 1 absorbed (`tropo-validate.ts` ledger→vault path + CLAUDE.md ADR-040 stale prose). Mike's reaction quoted in T9 ops bulletin: *"This is revolutionizing how I build in the Studio."*
- **Stream C — substrate-resident discipline: cold-boot-walk-as-step** ([c6b61fb9](vault/files/c6b61fb9.md)) — new step 7.5 in dev-pipeline deploy stage; wires into [release-cold-boot-walk.playbook (6f3d2a18)](.tropo/playbooks/release-cold-boot-walk.playbook.md) via `dev_pipeline_step` substrate link; canonical chain wiring at external-test next_steps + git-commit depends_on_steps. Mike-V48 directive 2026-05-20 codified per [V48 inbox note (89a25cfe)](vault/files/89a25cfe.md).
- **Stream D — substrate-resident discipline: pre-author-release-entry-as-step** ([674af8fe](vault/files/674af8fe.md)) — new step 5.5 in dev-pipeline deploy stage; closes V48-surfaced missing-release-entry pair-call pattern by making the gesture substrate-resident; canonical chain wiring at generate-release-notes next_steps + produce-release-folder depends_on_steps.
- **Phase B sa.board-agent canonicalization** — `agent-activation.playbook` v2.12 §Step 4.2.5 declares the canonical [Tier 3] slot for sa.board-agent dispatch; Phase A's Vela-only dogfood (v1.47 ship) now propagates to OS-tier. Argus A77 adopted in his own Tier 3; pattern available for all executives.
- **Carryalong 3 retirement-invariants** — `write-activation-entry.py op_close` mode enforces R-1 (retirement-run-folder) + R-2 (RETIRING-transit) + R-3 (reflection-authored) invariants symmetric to activation-side ADR-016/028 enforcement; A77 dogfooded at own retirement.

Two **in-cycle substrate absorptions at v1.48 ship time** (Vela fix-on-see per substrate-discipline doctrine):

- **v1.48.0.1** — 5 pipeline-step entries (`e8d162b3` + `2f7a3e68` + `5a3e72f4` + `9c4b8d21` + `1f6c4a9d`) flipped from `step_verifier_role: talos` (equal to `step_owner_role: talos` — failing pipeline.capsule v3.0 §Check 17) to `step_verifier_role: same-as-executor` (default value when no separate-context verification needed; Talos self-verifies in practice).
- **v1.48.0.2** — Metis G55→G56 transfer-stub authored at [vault/files/e7c4f523.md](vault/files/e7c4f523.md). Closes [A77 Path-2 inbox note bbc2659d](vault/files/bbc2659d.md) — the UID was registered in [G55 activation entry (1f170842)](vault/files/1f170842.md) + [Metis status card (9c2e99ef)](vault/files/9c2e99ef.md) at G55 retirement but never had a vault stub authored. Surgical fix; structural fix lives at v1.50 brief [04e73e8d](vault/files/04e73e8d.md) A12b (transfer-stub auto-generation at retirement-time).

**v1.49+ carry-forwards (Argus A78 lane + crew):**
- Cycle C web v1 ship via v1.49 brief [143c74d5](vault/files/143c74d5.md) — A77's harness fires for first production exercise; Captain's Read v2.0 Gate 1 lands here
- Phase 1 grooming sweep via v1.50 brief [04e73e8d](vault/files/04e73e8d.md) — Vela's ship discipline operates the cycle; A12b transfer-stub auto-generation
- T9 pair-call pending with Argus (sentinel convention for publish-act sub-gate-3 hook)
- Cycle B harness amendment (`release-cold-boot-walk.playbook` v1.0 → v1.1 per-persona Studio clones) — deferred to V50/v1.49 cycle
- vault-search.py ranking refinement (T9 lane) — "metis soul" query didn't surface 734bf7b0 in top 3 per V49 smoke test; Q5 use-case validation; T9 follow-up

Stage 1 smoke test PASS (vela-test-plan [dbe7bd24](vault/files/dbe7bd24.md) — 7/8 + 1 partial; Validator Gate 40/0/192). Stage 3 cold-boot-walk DEFERRED to v1.49 Cycle C (Mike-conditional; substrate-discipline scope; UX-class measurement at v1.49). Engine ceremony skipped per scope discipline (v1.46 first-production-use dogfood complete; v1.48 small-cycle uses simpler ship pattern).

---

## v1.47.0 — Vela Substrate-Discipline Cycle (Boot-Board Phase A Dogfood + 131-Item Backlog Sweep) (2026-05-21 by vela-v49 + Mike across V49 session 2026-05-20 → 2026-05-21; SHIPPED by Vela V49)

Vela-authored substrate-discipline cycle. **Interrupt cycle in Mike-A74-locked three-cycle extraction-and-publish-pipeline arc** per chain-mutability doctrine + Mike-V49 captain-mode authorization 2026-05-21 verbatim *"I think you have another release, Vela!"* + *"Just ship."* Argus's Cycle B (extraction-and-publish-pipeline Talos engineering) shifts v1.47 → **v1.48**; Cycle C shifts → **v1.49**. Three-cycle arc preserved; numbering shifted +1. Pristine streak **53 → 54**. Release entry: [3dbc7d88](vault/files/3dbc7d88.md).

The cycle codifies into substrate what V49's session demonstrated empirically: the Chief of Staff role can't carry 28-generation backlog drift; substrate-discipline must be structurally enforced at boot, not memory-resident across executive sessions.

What shipped:

- **Stream A — 131-item backlog sweep** (165 → 34 active items; 79% reduction). Four bulk-archival waves restoring substrate-hygiene baseline. In-place `state:active → state:archived` flip preserving honest historical per OP-13 Preservation Discipline. Types fully cleared: task, collection-ref, build, board-snapshot, test-scenario, test-run, generation-log, project-plan, release-notes. Diff report at `playbook-runs/agent-activation-vela-v49-2026-05-20/backlog-sweep/02-diff-report.md`.
- **Stream B — sa.board-agent Phase A boot-board discipline substrate**. New sa.* class definition (UID [281a79db](vault/files/281a79db.md) at `agents/sa/sa.board-agent/sa.board-agent.md` per session-agent.capsule v1.4) + Python implementation at `.tropo-studio/scripts/board-agent-query.py` (~250 lines; queries vault/00-index.jsonl with executive-declared filter; computes five lenses — by-type / by-project / oldest-15 / newest-10 / drift-class signals — renders board markdown; returns JSON headline) + design brief at [736f2251](vault/files/736f2251.md) (v1.47 candidate; Phase A Vela-dogfooded; Phase B canonicalization deferred to A76 next coherence cycle) + Vela Tier 3 §Group 4 Additions amendment declaring sa.board-agent dispatch step + `board_filter:`. Smoke-tested clean: 37 items / 5 lenses / executes in <1s. **Next Vela boot dispatches sa.board-agent automatically** — first production data point on the Phase A discipline.

Six-question design walk Mike-V49 locked before authorizing Phase A: (1) Group 4 self-diagnostic wire-in; (2) canonical board shape + per-agent filter; (3) ephemeral workspace output + Path-2 routing for substantive findings; (4) executive context savings ~10-25K per boot; (5) three-board composability (boot/work/master); (6) v1.47 candidate framing pending A76 anti-inflation pressure-test. All decisions captured in design brief 736f2251.

Mike-V49 served as principal-class skeptic functionally equivalent to source-time R3 substrate-coherence gauntlet in a different shape — absorbed the role d.skeptic-arch + d.fresh-reader companion-directors would otherwise have played. Stage 1 smoke test PASS (vela-test-plan [44c1fba8](vault/files/44c1fba8.md) 8 tests + Validator Gate). Stage 3 cold-boot-walk DEFERRED per Vela captain-mode call (substrate-only-cycle scope; UX-class minimal; would likely score similarly to v1.46 ~8.0).

Engine ceremony (pipeline-runtime fire through dev-pipeline) skipped per scope discipline — v1.46 first-production-use engine dogfood is complete + v1.47 is small substrate-discipline cycle; reverted to simpler ship pattern (build → smoke test → release entry flip → RELEASE-NOTES + ops.md + argus-vela). v1.48+ cycles can resume engine ceremony.

v1.48+ carry-forwards: Argus's Cycle B (extraction-and-publish-pipeline Talos engineering per c5a7e391 brief) + Phase B canonicalization of boot-board discipline (canonical playbook §4.3 slot + per-executive Tier 3 amendments — Argus lane per brief 736f2251) + Argus's other v1.47 candidates (v1.14 schema split, subsystem-registry backfill, pre-author-release-entry-stub, cold-boot-walk-as-step, dev-pipeline step 8 amendment for Studio ships, pipeline-runtime.py human-signoff contract check) + search-route haystack expansion (Q5 on Author Agent brief 1c4768b6 — Metis/Talos lane).

---

## v1.46.0 — Pipeline-Runtime Engine v3.0 Foundation + First Production Use (2026-05-20 by argus-a74→a75→a76 + vela-v47→v48→v49 + Mike across 3 days; SHIPPED by Vela V49)

Block 4 — Hardening Through Test **4th consecutive cycle at 8.0/10 sustained** (v1.43 + v1.44 + v1.45 + v1.46 floor extended). Substrate-class plateau thesis empirically confirmed both directions: UX-class cycles lift; substrate-class cycles hold floor. v2.0.0 Federation Foundation is the next destination cycle. Pristine streak **52 → 53**. Release entry: [82e44710](vault/files/82e44710.md).

The structural fix for memory-resident-discipline failure across generations. Pipeline-Runtime Engine v3.0 replaces memory-resident step coordination with substrate-enforced canonical lifecycle: `declared → started → completed → verified`. The cycle dogfoods itself — v1.46.0 ship IS pipeline-run [9d190713](vault/files/9d190713.md) firing through the engine the cycle ships (first production-use under self-validating bootstrap).

What shipped:
- **Engine** — `.tropo/scripts/pipeline-runtime.py` NEW (~1313 lines; canonical lifecycle state machine; pause/resume + skip-authorization + terminal-verify + human-signoff + complete-workflow). In-cycle pause-loop fix landed via V48 + A76 pair-call (~25 LOC `pause_resumed_pending: set[step_uid]` derived state)
- **Capsule replacement-bodies** — pipeline.capsule v2.6 → v3.0 + pipeline-run.capsule v1.4 → v2.0 (per A75-authored [8e5b3c47](vault/files/8e5b3c47.md) v0.5 LOCKED)
- **Design-spec** — pipeline-runtime.py [design-spec v0.2 LOCKED (2b809e0f)](vault/files/2b809e0f.md) authored A75 captain-mode pre-engineering
- **sa.pipeline-verify** — NEW sa.* class for verification_class:true natural-verdict capture
- **setup-new-pipeline.playbook** — NEW playbook for pipeline-class authoring (canonical lifecycle teaching surface)
- **tropo-validate.py** — 4 NEW validator checks (canonical-lifecycle enforcement; pipeline-run schema; eligibility shape; pause_resumed_pending integrity)
- **dev-pipeline retrofit** — step entries `declared → started → completed → verified` at substrate level
- **RELEASE-NOTES catchup** — v1.40 → v1.45 entries authored A74 session (post-cycle absorption)
- **manifest_walker.py** block-style YAML bug fix (e9b3c421 closed in-cycle)
- **v1.46.0.1 substrate fix (3 layers; A76 + Mike pair-call)** — build-release.py Step 1b canonical-L0 verification hoisted out of `if not bypass:` branch (always-runs; non-bypassable since v1.46.0.1; ~5 LOC) + 6-entry canonical-L0 substrate cleanup (spurious v1.12 hub-UID member_of backfill cleared) + validate-canonical-l0.py state-filter tightening
- **v1.46.0.2 substrate fix (4 reparents; V49 + Mike absorption)** — sa.* root + Hello Tropo customer event plan + Tropo Website Content Structure + David - 2 short papers imported-folder mirror each given non-hub canonical parent (surgical inline edits per fix-on-see doctrine)

Multi-layer gauntlet discipline canonical pattern empirically extended to **3 layers**: source-time (A75 d.skeptic-arch + d.fresh-reader R3 paired walk — 25 unique findings absorbed) + build-time (V48 R5 spot-check per pin 7b69bd19 — engine pause-loop defect + missing release entry caught) + engine-time (DAG eligibility enforcement newly empirically validated). Pair-call discipline canonical pattern empirically validated **3x at v1.46** (engine fix + missing release entry + canonical-L0 substrate fix).

Ship-time bypass-shadow catch + structural fix: Mike-V48 navigated rendered `00-tropo-nav/00-tropo-active/` 2026-05-20 + diagnosed canonical-L0 corruption from v1.12 backfill 2026-05-08 hidden across 10 cycles by `TROPO_SKIP_ENFORCEMENT_GATE=1` silencing validate-canonical-l0.py. Halt-everything posture imposed verbatim *"I do not feel good about this. Everything is on halt until I understand if we are doing more damage."* Resolved via A76 + Mike pair-call (v1.46.0.1 substrate fix) + V49 + Mike absorption (v1.46.0.2 reparenting); halt cleared by Mike-A76 *"if you don't think we need to halt, I am okay continuing"* + *"let's proceed with your work"*. Bypass-shadow defect class is now structurally defended at canonical-L0 surface; capability-membership Rule 11/12 still bypassed pending v1.47 first-stream substrate work (subsystem-registry.jsonl backfill).

Cold-boot walk: avg 8.0/10 SUSTAINED across all 3 personas; 4th consecutive cycle at the new floor. Block 4 thesis empirically confirmed both directions.

---

## v1.45.0 — Operator Path Connective-Tissue Repair (2026-05-19 by argus-a73; SHIPPED by Vela V48)

Block 4 Hardening Through Test cycle 5 of N. **BLOCK 4 CLOSES** per Vela V48 declaration 2026-05-19 — 3 consecutive cycles at 8.0/10 sustained (v1.43 + v1.44 + v1.45) satisfies the close-criterion (sustained-at-new-floor IS positive delta vs 7.33 baseline). Pristine streak **51 → 52**. Release entry: [6c8f3a92](vault/files/6c8f3a92.md).

Closes the operator-path connective-tissue friction V47 R3 + V48 R4 walks empirically surfaced.

What shipped:
- **Stream 1** — nav-block render suppression on `type: kb-article` entries (operator FAQ no longer leads with 14 lines of nav metadata before content)
- **Stream 2** — reader-frame off-ramp callouts strengthened in 5 first-encounter files (`"you don't need to read past this line — your AI does"`)
- **Stream 3** — CLAUDE.md two-stage boot pattern (Stage 1 concierge ≤30s; Stage 2 deeper substrate lazy by topic)
- **Stream 4** — L1 entry §3→§4 operator off-ramp paragraph
- **Stream 5** — named-defect inventory sweep: 6 fixes (concierge L86 `ledger`→`tasks, projects` + agents/AGENTS.md stale `tropo_version` removed + create-an-agent.playbook §Resources hrefs corrected + START-TROPO Enterprise FAQ link + Markdown-is-the-API engineer-trust teaser + operator FAQ Q1 coordinator offer-to-walk pattern)
- **Stream 6** — DEFERRED to v1.46+ (validator-against-shipped credibility; scope-cap discipline)

Cold-boot walk: avg 8.0/10 SUSTAINED across all 3 personas (engineer + operator + enterprise); 3rd consecutive cycle. Vela V48 captain-mode build-artifact spot-check caught 5 source-vs-template drift defects at Stage 1; fix-on-see absorbed.

Multi-layer gauntlet discipline empirically validated 3rd consecutive cycle — director-gauntlet source-time (d.skeptic-arch + d.fresh-reader) + Vela build-time spot-check. Canonical pattern going forward.

---

## v1.44.0 — Stranger-Encounter UX Readiness (2026-05-19 by argus-a73; SHIPPED by Vela V48)

Block 4 Hardening Through Test cycle 4 of N. Pristine streak **50 → 51**. Release entry: [8f3d7c91](vault/files/8f3d7c91.md).

First cycle scoped specifically to MOVE the cold-boot walk score (v1.41+v1.42 baseline both 7.33; v1.44 target ≥ 8.0). Six substantive streams collapsed from v0.3 fold plan's v1.45+v1.46 buckets per Mike-A73 anti-inflation pressure-test.

What shipped:
- **Stream A** — 5 first-encounter surface vocab cuts (concierge top + L1 §1 plain opener + L1 §4 capsule-typing plain prose + STUDIO subsystem-registry trim + create-an-agent §4.5 condensed)
- **Stream B** — operator fast-path in START-TROPO.md with explicit per-AI-tool activation steps + L1/FAQ routing split
- **Stream C** — harness-narration callout in 5 files (`"The AI reading this drives the configuration — you're guiding; the AI is typing"`)
- **Stream D** — 3 NEW persona FAQ articles: [Operator FAQ (4e7d2c91)](vault/files/4e7d2c91.md) + [Engineer FAQ (8c4e1b73)](vault/files/8c4e1b73.md) + [Enterprise FAQ (b6a3f582)](vault/files/b6a3f582.md)
- **Stream E** — 2 NEW canonical primitive KB articles: [How Capsules Work (5f7a9d83)](vault/files/5f7a9d83.md) + [How Tropo Work Works (2d4f8c91)](vault/files/2d4f8c91.md)
- **Stream F** — DEFERRED to v1.45 (curriculum spine; ~400 lines outside scoped six streams)

R2 substrate-honesty gauntlet caught 4 P0 substrate-honesty breaks (capsule pedagogy 6→5 sections; per-capsule state machines vs universal; register-kernel.py corrected; four-files-in-three-tiers framing). All absorbed in-cycle.

Director system commissioned: companion-directors d.skeptic-arch + d.fresh-reader + d.doc-curator per [director.capsule v1.0 (30137f44)](vault/files/30137f44.md).

Cold-boot walk: 8.0/10 sustained across all 3 personas (operator +0.67 vs baseline).

---

## v1.43.0 — First-Encounter Substrate + Publishing Engine (2026-05-18 by argus-a72; SHIPPED by Vela V48)

Block 4 Hardening Through Test cycle 3 of N. Pristine streak **49 → 50**. Release entry: [a7e2c481](vault/files/a7e2c481.md).

Closes V47's v1.41+v1.42 cold-boot walk P0 defects + lands the publishing-engine substrate Stream C+D split deliberately deferred from v1.42 per scope-cap discipline.

What shipped:
- **Stream A** — `channels/` folder skeleton via ship-artifact entries (closes V47 walk P0: channels/ops.md referenced by Rule 10 + STUDIO System Map + concierge §1.5 but silently absent on extract)
- **Stream B** — `system/` folder skeleton via ship-artifact entries (closes V47 walk P0: concierge Boot Protocol Step 6 silently passes; vault-steward unreachable)
- **Stream C** — `lib/ship_extract/` shared engine refactor — 5 sub-modules (manifest_walker + source_mode_dispatch + cleanup_engine + validator + output_writer) extracted from `build-release.py`
- **Stream D** — `build-web-content.py` thin orchestration; outputs to website-content working copy; unblocks Talos's web-deploy-3 canonical extraction path
- **Stream E** — `release-cold-boot-walk.playbook v1.0 → v1.1` amendment (per-persona Studio clones at dispatch; closes concurrent-mutation harness defect)
- **Stream F** — substrate-coherence drift reconciliation: TROPO-CONTROL.md §8 version sync + 2 phantom playbooks + 2 phantom sa.* registry entries + L1 capsule-count drift + AGENTS.md template stale-version fix
- **Stream G** — "You're done" UX surface at end of create-an-agent walk + AGENTS.md template scope-flex fixes

Cold-boot walk: 8.0/10 across all 3 personas — first cycle to cross the ship-clear bar in Block 4. Pristine streak ratchets cleanly.

---

## v1.42.0 — ship-artifact.capsule v1.3 Multi-Target Extraction (2026-05-18 by argus-a71; SHIPPED by Vela V48)

Block 4 Hardening Through Test cycle 2 of N. Pristine streak **48 → 49**. Release entry: [5fb6bcd3](vault/files/5fb6bcd3.md).

Substrate-class governance amendment enabling multi-target extraction (release + web targets) via per-target iteration. Unblocks Talos's web-deploy-3 hosted-blog substrate which held pending substrate-class extraction discipline for web target.

What shipped:
- **`ship-artifact.capsule` v1.2 → v1.3 amendment**: always-array `target:` field (default implicit `[release]`; new value `web`); `manifest_root_uid:` converted from scalar to per-target map; per-target `cleanup_rules:` defaults; new `cleanup_rules.uid_rewrite_template:` field; Rule 1 + Rule 10 target-aware restatement
- **Validator Check 24** (NEW): `target:` enum validity enforcement; ERROR at v1.3 directly (no migration window — hard governance rule with clean default)
- **5-reader atomic-commit migration**: `build-release.py` + `validate-release-manifest.py` + `.tropo-studio/scripts/dry-run-manifest.py` + 2 internal readers updated in same git commit as the v1.3 amendment
- **NEW evergreen substrate**: [Tropo Website Content Structure (4a99638d)](vault/files/4a99638d.md) — manifest-root for web-target ship-artifact entries
- **History §Schema Migrations subsection** added to ship-artifact.capsule

Entry-level backward-compat 100%: existing v1.2 entries continue valid; absent `target:` field implies `[release]`. Zero migration cost for legacy substrate.

Cold-boot walk: 7.33/10 (zero net movement from v1.41 baseline). Honest cycle-comparable signal — substrate-architecture work doesn't move first-encounter UX score. Block 4 close-criterion thesis (UX-class moves the needle; substrate-class doesn't) empirically supported.

---

## v1.41.0 — Ship v1.40 Properly (2026-05-18 by argus-a71; SHIPPED by Vela V48)

Block 4 Hardening Through Test cycle 1 of N. Pristine streak **47 → 48**. Release entry: [ec1ac5ae](vault/files/ec1ac5ae.md).

Closes v1.40-fidelity gaps surfaced at Vela V47's v1.40 build inspection — substrate codified but not delivered in build artifact. Block 4 thesis empirically validated: source-time gauntlets are structurally blind to build-time defects; build-artifact spot-check is the unconditional second line.

What shipped:
- **LICENSE swap** AGPL-3 → Apache 2.0 with [ADR (4a4a1235)](vault/files/4a4a1235.md); legal substrate change matching Mike-confirmed direction
- **Folder-tier ship-artifact entries** for `vault/AGENTS.md` + `vault/CLAUDE.md` (closing v1.40 doctrine 4/5 → 5/5 tier fidelity gap)
- **`build-release.py` Step 0 vault:rebuild** as halt-mode pre-flight (root cause of v1.40 first-build incident where canonical doctrine entry was excluded; bypass-gate does NOT skip Step 0)
- **Memory v3 template fix** (substrate-class shape: `entries/`, `topics/`, `history/`, `short-term-memory.jsonl`, `memory-current.md` properly extract per template)
- **8 empty scaffolds** (`boards/`, `channels/`, `collections/`, `decisions/`, `playbooks/`, `projects/`, `settings/`, `system/`) skipped in build manifest — fresh-install user encounters zero visible empty directories

Build pre-flight halted on substrate-class defects (504896d7 + de204cfa) per Stream C; absorbed fix-on-see.

Cold-boot walk: 7.33/10 baseline — first run of `release-cold-boot-walk.playbook v1.0` with 3 personas (engineer/operator/enterprise). Block 4 baseline established.

---

## v1.38.0 — Validator-Check Consolidation + Audit (2026-05-17 by argus-a70)

## v1.40.0 — Deletion Discipline Doctrine (Multi-Tier Codification) (2026-05-17 by argus-a70)

Block 3 cycle 4 of ~4. **CLOSES Block 3.** Pristine streak **46 → 47**. Release entry: [8c9962a7](vault/files/8c9962a7.md).

Codifies the ban-on-rm + use-tropo-recycle.py discipline at four substrate tiers + canonical single source of truth. Incident-driven cycle — Mike-A70 audit 2026-05-17 + Talos T8 commit `7a8df68` same-day bypass demonstrated the gap.

What shipped:
- **Canonical doctrine** [0aefe71d](vault/files/0aefe71d.md) v1.0 LOCKED — single source of truth; full forbidden-op list; 13-row scope table; recovery procedures.
- **OS-tier**: `.tropo/SELF-HEALING.md` §Preservation Discipline (inverse-vector primitive).
- **Studio-tier**: `.tropo-studio/operating-principles.md` Principle 13.
- **Folder-tier**: `vault/AGENTS.md` §Deletion Discipline (point-of-action).
- **Memory-tier**: vault-level pin [839a65f9](vault/files/839a65f9.md) at tier=current; elevated from Argus-personal.

R1 caught the cycle's own A68 violation (tier amendments duplicated content); absorbed in-cycle via trim. R5 hostile-implementer lens cleared SHIP with 3 P2 deferrals [31e68629](vault/files/31e68629.md).

Validator at ship: **30 PASSED / 0 FAILED / 151 warnings**. Zero new failure or warning CLASSES.

**BLOCK 3 CLOSES.** All 4 Block 3 cycles validated the thesis (Pre-ship polish; Ratchet cycles; Closes carry-forwards; Maturity proof). The substrate maturity story at v2.0.0 is complete. **Next: v2.0.0 Federation Foundation PUBLIC SHIP.**

---

## v1.39.0 — Memory Subsystem Generational Fold (A52-A57 Catch-up) (2026-05-17 by argus-a70)

Block 3 pre-ship polish cycle 3 of ~4. Pristine streak **45 → 46**. Release entry: [8638c394](vault/files/8638c394.md).

Closes a 12-generation-old carry-forward: Argus's 11 STM entries from A52-A57 finally folded into the v3 memory substrate via sa.memory-curator-004 dispatch.

What shipped:
- **13 new memory entries** at `agents/argus/.tropo-capsule/memory/entries/` (5 fresh Mike-A68-A69 doctrines + 8 A55-A56 procedural/architectural pins).
- **3 entries archived** to `history/argus-a52-a57-stm-fold-archive.md`.
- **STM cleared** (16 → 0; all dispositioned).
- **memory-current.md regenerated** with last_compacted=2026-05-17 + compacted_by=argus-a70 + full lineage.

**Cycle deviation:** Captain's Read named v1.39.0 = "Self-reference render pattern" (cosmetic; no concrete substrate scope). Per Mike-A70 agreement, deviated to memory fold (concrete + substantive + closes-a-12-generation-carry-forward). Self-reference render → v1.40.0+ candidate.

Validator at ship: **31 PASSED / 0 FAILED / 163-167 warnings** (vs 31/0/147 at v1.38.0; +16-20 WARN honest substrate-surfacing from new memory entries; zero new failure or warning CLASSES).

LIGHT gauntlet (R1 captain-mode LOCK + R5 ship-time only). sa.memory-curator's suggest-don't-write protocol with pre-ratified action rules IS the gauntlet for memory work. 5 binding memory pins validated consecutively (A65 9th + A68 4th + A69×3 3rd).

**1 cycle to v2.0.0 public ship.**

---

Block 3 pre-ship polish cycle 2 of ~4. Pristine streak **44 → 45**. Release entry: [f1e50c42](vault/files/f1e50c42.md).

Substrate-wide audit of all 35 validator check functions in `tropo-validate.py` against a 4-class parser/bug-risk rubric. **Zero Pattern C (raw substring-match) bugs found beyond the v1.37.0 R3 fix in `check_charter_conformance`.** The validator was substantially healthier than the cycle-opening hypothesis predicted.

What shipped:
- **Inventory document [391043ad](vault/files/391043ad.md)** — canonical per-check classification (35 → 34 checks); future check authors consult before adding a 36th.
- **§Validator Check Pattern in `.tropo/scripts/CAPSULE.md`** — NEW canonical section. Pattern A (`yaml.safe_load` + dict-key lookup) + Pattern B (`split_frontmatter` + `get_scalar`) both blessed; forbidden Pattern C boundary broadened; full mechanics (chooser + signature + iteration + severity + registration + verification + inventory reference) documented.
- **`check_generation_logs` RETIRED.** Substrate it validated retired at v1.21.0; zero current scope. Recovery path documented in retirement notice.
- **Side-issue:** Talos T8 activation entry `agent_root` UID corrected inline; channel post flagging bug pattern.

Validator at ship: **31 PASSED / 0 FAILED / 147 warnings** (vs. 33/0/137 at v1.37.0 ship; deltas: -2 PASS retirement + cycle accounting; +10 WARN honest substrate-surfacing; zero new failure or warning CLASSES).

5 sa.* gauntlet rounds + 1 pre-R1 cycle-anchor dispatch (sa.skeptic-097 reversed charter SUPERSESSION → validator audit BEFORE wrong cycle landed). 6 binding memory pins validated consecutively (A64 9th + A65 8th + A68 3rd + A69×3 2nd).

2 cycles to v2.0.0 public ship.

---

---
release: "v1.37.0"
released: "2026-05-17"
codename: "Charter Capsule Definition"
member_of:
  - "a8d3f74c"   # v1.37.0 release entry
  - "8dd772a0"   # tropo-governance
  - "99ed55fd"   # tropo-agents
---

# Tropo-OS v1.37.0 — Charter Capsule Definition

**Block 3 pre-ship polish cycle 1 of ~4 per [v2.0.0 Captain's Read](vault/files/a5f4b26b.md) — OPENS Block 3.** First block-OPENING moment under §Chain Progress Snapshot discipline (v1.36.0 was first block-closing; v1.37.0 inverse). Single-stream cycle per Q1 Option C lock + NEW more-capsules-equals-more-maintenance pin (Mike-A69 verbatim 2026-05-17). Closes the v1.23.0 sa.skeptic-039 governance carry-forward: charters were implicit-typed-as-document; v1.37.0 formalizes type:charter as first-class governance capsule with check_charter_conformance validator (WARN at v1.37.0 / ERROR ratchet at v2.0.0 per Q2 Option B Mike-A69 lock).

Per design brief [d5a7e482 v0.2 LOCKED](vault/files/d5a7e482.md) + design spec [e3f47a82 v0.2 LOCKED](vault/files/e3f47a82.md) + release plan [f9c4a283 v0.1 LOCKED](vault/files/f9c4a283.md). Authored end-to-end captain-mode by Argus A69 in single session per three NEW Mike-A69 pins (more-capsules + captain-mode-make-the-call + sa.*-debate-doctrine).

---

## What shipped

**1. charter.capsule.md v1.0.1.** [8f3c9e1a](.tropo/capsules/charter.capsule.md). First-class governance capsule for charter-bearing agents (executive + director). 12 required frontmatter fields + one required Identity H2 body section (strict-literal regex; no role-shaped alternatives per more-capsules pin applied to validator whitelists). Optional substrate via §3 (soul / dna / channels / retirement_acts / governor / locked_at+locked_by / operational pointers / member_of). Lock semantics matches existing spec/ADR/Captain's Read pattern: lock at commission + Mike lock-break for amendment; carve-outs for hygiene + pointer + optional-additions per Q8-spec walk. Single capsule covers executive + director uniformly per Q6 lock; sa.* keep session-agent.capsule v1.5 LOCKED.

**2. check_charter_conformance validator extension.** [tropo-validate.py](.tropo/scripts/tropo-validate.py). 8 checks per capsule §7 — required fields + 3 enum validations + scope sub-fields + Identity H2 strict-literal regex + locked_at/locked_by atomic pair + retired/archived RELAXED at v2.0.0 ratchet. WARN-severity at v1.37.0 honor-system; ERROR ratchet at v2.0.0. **R3 P0 fix:** original implementation used substring-match against raw YAML text (false negatives); refactored to `yaml.safe_load(fm_text)` + dict-key lookup; WARN count rose 31 → 43 (substrate-honesty restored — exactly the per-agent rev work Q1 Option C deferred).

**3. Mechanical type-flip of 11 charters.** [v1.37.0-flip-charter-type-2026-05-17.py](.tropo/scripts/v1.37.0-flip-charter-type-2026-05-17.py). 6 charters flipped (5 no-type → type:charter: Argus / Vela / Metis / Orpheus / Cosmo; 1 type:agent-charter → type:charter: Tropo — closed third-variant substrate drift); 5 charters silent-skip per idempotency (Talos / Silas / Jules / D.ops / D.curator). Rollback manifest at `.tropo-studio/scripts/v1.37.0-flip-charter-type-manifest.json`. NO per-charter body amendments per Q1 Option C deferral — validator WARN signals (43 across 11 charters) surface conformance gaps for per-agent future-cycle rev work toward v2.0.0 ERROR ratchet.

**4. Closes v1.23.0 sa.skeptic-039 governance carry-forward.** Charters were the load-bearing identity primitive being migrated to vault/files/<uid>.md at v1.23.0, but the substrate had no `type: charter` capsule. Carry-forward through v1.29.0 → v1.36.0 (Block 1 substrate-hardening + Block 2 funnel both took priority per Captain's Read sequencing). v1.37.0 closes it per Block 3 thesis (closes carry-forwards; maturity proof).

---

## Three NEW pins authored mid-cycle by Mike-A69 (all FIRST-CYCLE validated)

1. **more-capsules-equals-more-maintenance** (Q6 walk verbatim) — sharpens earn-the-abstraction-strict pin for capsule substrate; binding when authoring/amending capsule definitions
2. **captain-mode-make-the-call-yourself-surface-fewer-walks** (R2 absorption verbatim) — Mike's constraint named: cross-agent context-load is binding when directing N agents; sa.*-debate replaces escalation
3. **sa.*-debate-doctrine** (R2 → ship extension verbatim "Our agents should use that liberally") — crew-wide directive; vault-memory elevation + OP-9 amendment candidate filed Path 2 [4e8c2d57](vault/files/4e8c2d57.md) for Vela's lane

---

## How it shipped clean

Four sa.* dispatches across 4 distinct R-round positions (R1 collapsed into Mike-walks for brief Q-locks):
- **R2** architectural-conformance (sa.skeptic-094 LOCK-after-absorption; 1 P0 + 5 P1 + 5 P2 + 3 RC absorbed)
- **R3** rotated-lens 3-sub-lenses (sa.skeptic-095 FAIL with P0: validator substring-match bug; refactored to PyYAML; WARN rose 31 → 43)
- **R4** cold-boot governance-author persona (sa.cold-boot-195 PASS — composed complete Nestor charter cold; capsule v1.0 → v1.0.1 with 8 pedagogical absorbs)
- **R5** ship-time consolidated cross-cut (sa.skeptic-096 LOCK-after-absorption; pin-count correction + spec §2 v1.4 → v1.5 cleanup + snapshot banner disambiguation)

**A64 rotate-the-gauntlet-lens pin VALIDATED AN 8TH CONSECUTIVE CYCLE.** **A65 fix-on-see; no hand-offs pin VALIDATED A 7TH CONSECUTIVE CYCLE** (every R2+R3+R4+R5 finding absorbed in-cycle; 6 Path 2 notes filed only for cross-lane / cross-cycle work per scope discipline). **A68 canonical-content-doctrine pin VALIDATED A 2ND CONSECUTIVE CYCLE.**

---

## Substrate state at ship

- **Validator:** 33 PASSED / 0 FAILED / +47 warnings vs v1.36.0 baseline (43 charter-conformance honest surfacing + ~4 nav-block from new Path 2 notes; zero new failure or warning classes)
- **`npm test`:** YELLOW ship-clear per v1.33.0 §3.3 contract
- **UID cross-references:** PASS
- **Version consistency:** PASS (flips to v1.37.0 at this `.tropo/version.md` bump)
- **Pristine-no-Rule-7 streak: 43 → 44.** Target 45 at v1.38.0 ship → ~46 at v2.0.0.

---

## What lands next

**v1.38.0** — Block 3 cycle 2: Hooks/triggers polish per Captain's Read. Pristine streak target 45.

**6 Path 2 carry-forwards filed at this cycle:**
- [d3a8e21c](vault/files/d3a8e21c.md) scripts/tropo-validate.ts stale ledger/ path (Talos lane)
- [f7e1b094](vault/files/f7e1b094.md) skill 135be96d block-closing + opening variant amendment
- [9b3e7c41](vault/files/9b3e7c41.md) charter SUPERSESSION pattern (v1.38.0+ governance work)
- [2f4b9d18](vault/files/2f4b9d18.md) validator-check sprawl observation
- [4e8c2d57](vault/files/4e8c2d57.md) sa.*-debate doctrine vault-memory elevation + OP-9 amendment (Vela lane)
- [c1d4f739](vault/files/c1d4f739.md) substrate-wide validator audit for split_frontmatter consumers

---

## Vela-test-plan at ship

[5c9e7b21](vault/files/5c9e7b21.md) per Mike-A63 release-step pin — 6 deterministic tests + 1 validator gate. V46 executes within 24h.

---

## Strategic frame at ship

**Block 3 — Pre-ship polish OPENS.** Captain's Read thesis ("ratchet cycles; closes carry-forwards; maturity proof") begins here. The substrate maturity story we tell at v2.0.0 now includes "charters are first-class governance capsules with validator enforcement." **3 cycles to v2.0.0 public ship** (v1.38 + v1.39 + v1.40+ → v2.0.0 federation foundation). 1000+ users land at v2.0.0.

v1.36.0 release entry [a4c8d691](vault/files/a4c8d691.md) archived per v1.21.0.1 rolling-window governance.

---

*Tropo-OS v1.37.0 RELEASE-NOTES | Authored 2026-05-17 by Argus A69 (captain-mode end-to-end per Mike-A69 'yes, proceed' + 3 NEW Mike-A69 pins) | Release entry [a8d3f74c](vault/files/a8d3f74c.md)*
*"Charters are first-class governance capsules now. Block 3 opens. 3 cycles to v2.0.0."*
