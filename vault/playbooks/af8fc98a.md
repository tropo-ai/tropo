---
uid: af8fc98a
type: playbook
title: "Run Release Test Plan — v1.4.2 Ship Gauntlet Orchestrator"
description: "Top-level orchestrator for the 3-stage release ship gauntlet codified in release-test-plan v2 (`f4a8c2d6`). Calls dispatch-walker.playbook + dispatch-cold-boot.playbook (Strict + Skeptic). Aggregates verdicts. Outputs structured report for ship-signal eligibility."
version: "0.3"
status: active
locked_by: vela-v37
locked_at: 2026-05-01
owner: vela
readers: [agent, human]
scope: multi-session
trigger: release-pre-ship-verification
domain: test-harness
estimated_duration: "2-6 hours wall-clock end-to-end (Stage 1 ~15 min, Stage 2 ~10 min, Stage 3 ~1-4 hours depending on agent runtime + paired-mode dispatch)"
target_artifact_type: release
verdict_format: "PASS / PASS-WITH-FINDINGS / HALT-SHIP"
tags: [test-harness, orchestrator, release-gate, kernel-tier, v1.4.2, doctrine-grounded, three-stage-gauntlet]
governed_by: e7b3c509   # playbook.capsule v2.4 (test-harness subtype)
calls:
  - .tropo/playbooks/dispatch-walker.playbook.md
  - .tropo/playbooks/dispatch-cold-boot.playbook.md
relationships:
  - kind: implements
    target: f4a8c2d6   # release-test-plan v2 (in-place v1→v2 amendment per Sprint 5; UID preserved)
  - kind: governed-by
    target: b19e8d43   # release.capsule v3.1 Rule 10
  - kind: composes
    target: 7579f894   # dispatch-walker.playbook v0.2 (Stage 3.1)
  - kind: composes
    target: a5fb24a6   # dispatch-cold-boot.playbook v0.2 (Stages 3.2-strict + 3.3-skeptic)
  - kind: grounded-in
    description: "The Patient Honing Doctrine — institutionalizes the v1.4.2 ship gauntlet as kernel primitive."
created: 2026-05-01
created_by: vela-v37
modified: 2026-05-01
modified_by: vela-v37
schema_version: 2
extraction_scope: ship
member_of: [8e4a2c1f]   # Stream 1 — Test-Harness Authoring
member_of:
  - "76bab75f"   # tropo-playbooks (v1.8 Stream B1 backfill)

---

# Run Release Test Plan — v1.4.2 Ship Gauntlet Orchestrator

*Sprint 4 first-instance test-harness orchestrator. Pulls dispatch-walker.playbook v0.2 + dispatch-cold-boot.playbook v0.2 together as the executable form of [release-test-plan v2 (f4a8c2d6)](../files/f4a8c2d6.md). Per [The Patient Honing Doctrine](../../.tropo-studio/memory/patient-honing-doctrine.md): the workshop IS the system; the system compensates for forgetting. The ship gauntlet is workshop primitive from v1.4.2 forward.*

---

## Intent

Orchestrate the 3-stage release ship gauntlet end-to-end against a target release version. Run Stage 1 (Pre-Build) → Stage 2 (Build + Extract) → Stage 3 (Post-Extraction: Walker + Cold-boot Strict + Cold-boot Skeptic + Validate). Aggregate verdicts. Output structured report establishing ship-signal eligibility for Mike's §G.5 sign.

**Why this is kernel primitive (not crew operational doc).** The v1.4.0 → v1.4.1 cycle proved the gauntlet works. It also proved the orchestration logic lives in V36's session memory rather than substrate. This playbook makes the protocol discoverable + executable. Per release.capsule v3.1 Rule 10, walker + cold-boot are required pre-ship gates; the orchestrator binds them into a single ship-eligibility verdict.

**Sibling sub-playbooks** (called by this orchestrator):
- [`dispatch-walker.playbook` v0.2 (`7579f894`)](dispatch-walker.playbook.md) — Stage 3.1
- [`dispatch-cold-boot.playbook` v0.2 (`a5fb24a6`)](dispatch-cold-boot.playbook.md) — Stages 3.2-strict + 3.3-skeptic

**Spec implemented:** [release-test-plan v2 (f4a8c2d6)](../files/f4a8c2d6.md). Sprint 5 amends v1 → v2 to formalize the Stage 3.2-strict / 3.3-skeptic split + cite this orchestrator as canonical executable form.

**Transitional invocation mode (until Sprint 4-orchestrator usage settles).** This is the first orchestrator-class playbook in the vault. Eat-own-dog-food test against v1.4.2 itself produces the first exemplar run; pre-eat-dog-food, expect operational refinement.

---

## Rules

1. **Orchestrator MUST run all stages in declared order.** Stage 1 → Stage 2 → Stage 3. Stage skipping is a Rule-1 violation; partial gauntlet is HALT-SHIP class. (Exception: Stage 3.3 Skeptic-mode DEFERRED-PENDING-CAPSULE — see Rule 11 for the bounded transitional behavior.)
2. **Each stage gates the next.** Stage 1 ALL PASS → Stage 2 unlocks; Stage 2 ALL PASS → Stage 3 unlocks. Any FAIL or HALT-SHIP at any stage HALTs the orchestrator; remediate at source; bump patch version per Mike's "every observable build state gets a unique version" rule (2026-04-29); restart from Stage 1.
3. **Stage 3 sub-stages have defined parallelism — with filesystem isolation.** 3.1 (Walker), 3.2 (Cold-boot Strict), 3.3 (Cold-boot Skeptic), and 3.4 (validate) MAY run in parallel ONLY IF each sub-agent operates against a separate copy of the extracted vault (re-extract per agent OR copy the extracted directory per agent before parallel dispatch). Sequential dispatch against single extracted vault is also valid + simpler; **recommended for v1.4.2 first-runs.** Parallel reduces wall-clock at extraction-overhead cost; without isolation, parallel dispatches contaminate Strict-mode "every read = gap" tracking. (Round 1 v0.2 amendment per cold-boot 106 + skeptic 027 F3 convergence.)
4. **Sub-playbook invocation MUST spawn a fresh subagent session per invocation.** Per Round 1 v0.2 amendment (cold-boot 106 F1 + skeptic 027 F4 convergence). When Step 3.1 / 3.2 / 3.3 says "invoke sub-playbook," the dispatcher uses the Claude Code Agent tool with `subagent_type: general-purpose` + spawn-prompt that instructs the subagent to read the sub-playbook + execute its declared Steps end-to-end + write output to the activation-log record (per the sub-playbook's own dispatch protocol). The orchestrator does NOT inline-execute sub-playbook Steps; it delegates to fresh subagent sessions. This matches the sibling test-harness pattern (`dispatch-walker.playbook` + `dispatch-cold-boot.playbook` themselves spawn agents — recursive spawn is fine because each sub-playbook bounds its own recursion).
5. **Verdict aggregation is non-overridable except via Rule 7's documented override path.** PASS / PASS-WITH-FINDINGS / HALT-SHIP / HALT-SHIP-REVIEW per §Verdict Aggregation. Dispatcher does NOT silently reclassify; ship under HALT-SHIP requires Mike's explicit override per Rule 7 with audit-trail discipline.
6. **HALT-SHIP at any stage = no ship by default.** Per Mike's 2026-04-29 directive "every observable build state gets a unique version" — remediate at source, bump patch version, run a NEW gauntlet against the new build. The HALT-SHIP record is permanent audit trail. **Mike's override path** (Rule 7) is the documented exception, not silent.
7. **§G.5 ship-signal authority is Mike's; HALT-SHIP override path is documented + audit-trailed.** Orchestrator PASS or PASS-WITH-FINDINGS verdict establishes ship-eligibility; Mike signs ship per release.capsule v3.1 §5.5.3 authorized-signal language ("ship it" / "go" / "send it"). **Override path for HALT-SHIP / HALT-SHIP-REVIEW:** Mike MAY override the orchestrator's HALT verdict, but the override MUST be (a) declared in console with explicit rationale, (b) recorded in the release entry's `verification_artifacts:` array as a structured override entry (`{type: ship-override, by: mike, rationale: <text>, overridden_verdict: <halt-class>, override_at: <iso8601>}`), (c) permanent audit trail. Multiple overrides per release version trigger §Escalation Heuristics architect-review. Override is the documented exception, not silent path. (Round 1 v0.2 amendment per skeptic 027 F6 — Rule 5/Rule 7 tension reconciled.)
8. **Activation-log evidence is required.** Each Stage 3 sub-stage produces an activation-log record. The release entry's `verification_artifacts:` array MUST include all run records' UIDs (or DEFERRED-PENDING-CAPSULE annotation per Rule 11 for Stage 3.3 in transitional state). For partial gauntlets that HALT before Stage 3 completes: the partial record set IS the audit trail; release entry is NOT authored (no ship-eligibility); activation-log records persist as historical evidence of the failed run.
9. **Dispatcher MAY be Vela** (orchestrator is Vela-owned per crew scope). Argus, Metis, or Mike MAY also dispatch with appropriate lane awareness (Stage 3.1 walker dispatcher must be Mike or Metis per walker allowlist; Stage 3.2/3.3 cold-boot dispatcher follows cold-boot allowlist).
10. **Dispatcher MUST author the orchestrator-run record themselves.** Same audit obligation as sibling playbooks. Copy-paste from another agent's draft is a Gate 5 independence violation.
11. **Stage 3.3 Skeptic-mode DEFERRED-PENDING-CAPSULE is bounded transitional — max 2 release cycles.** (Round 1 v0.2 amendment per skeptic 027 F1 + cold-boot 106 F2 convergence.) When `sa.user-error-walker` capsule does not yet exist (transitional state), Step 3.3 marks DEFERRED-PENDING-CAPSULE per dispatch-cold-boot.playbook's pre-spawn `ls` check. **Forcing function:** the deferral is valid for at most 2 release cycles (e.g., v1.4.2 + v1.4.3). On the 3rd consecutive release where the capsule still doesn't exist, DEFERRED escalates to HALT-SHIP — the architectural debt becomes ship-blocking. Phase-out target: post-Sprint-1b activation-log.capsule close (Argus-tracked at [argus-vela 2026-05-01](../../channels/argus-vela.md)). Track deferral count in §Known Enforcement Gaps row 1 — increment per release that defers; reset on capsule lock.
12. **Combinatoric escalation: ≥2 PARTIALs in Stage 3 → HALT-SHIP-REVIEW.** (Round 1 v0.2 amendment per skeptic 027 F2.) Single PARTIAL in Stage 3 → PASS-WITH-FINDINGS (standard). **Two or more PARTIALs across Stage 3 sub-stages** (e.g., Stage 3.1 PARTIAL AND Stage 3.2-strict PARTIAL) → orchestrator verdict escalates to HALT-SHIP-REVIEW: ship-blocked by default; ship requires Mike + Argus review of the combinatoric pattern (PARTIAL across distinct lenses signals coverage gap each lens missed in isolation). Three PARTIALs → HALT-SHIP (not just review).

---

## Groups

```
Group 1 (Stage 1) — Pre-Build → milestone: Pre-Build PASS
 ↓
Group 2 (Stage 2) — Build + Extract → milestone: Build PASS
 ↓
Group 3 (Stage 3) — Post-Extraction (parallel-with-isolation OR sequential) → milestone: Stage 3 verdict
 ↓
Group 4 — Verdict Aggregation + Report → milestone: Gauntlet Complete
```

---

### Group 0 — Orchestrator-run record initialization (precondition)

**Owner:** dispatcher
**Parallel:** no
**Depends on:** dispatcher decision to run gauntlet
**Milestone:** Run Initialized
**Milestone timeout:** 5 min

(Round 1 v0.2 amendment per cold-boot 106 P1 — orchestrator-run record path/filename was previously undeclared.)

#### Step 0.1 — Create orchestrator-run record
*Executor: dispatcher.* Create `playbook-runs/run-release-test-plan-<release-version>-<YYYY-MM-DD-HHMM>/run.jsonl`. This matches the existing `playbook-runs/agent-activation-...` pattern. Generate 8-hex run UID. Initialize with one event:

`{"event": "run_created", "run_uid": "<uid>", "playbook": "run-release-test-plan", "playbook_version": "<this-version>", "release_version": "<target-release>", "dispatcher": "<short-handle>", "build_uid": "<build-entry-uid>", "extracted_path": "<realpath>", "timestamp": "<iso8601>", "status": "active"}`

This is the state anchor for Group milestones. Multi-run canonical-of-record: latest run timestamp wins for the same release-version-under-test; older runs become audit history (cited in release entry only if explicitly canonical for that ship).

#### Step 0.2 — Write Run Initialized milestone
*Executor: dispatcher.* Append `{"event": "milestone_fired", "milestone": "Run Initialized", "group": "Group 0", "timestamp": "<iso8601>"}` to run.jsonl.

---

### Group 1 — Stage 1: Pre-Build (source vault)

**Owner:** dispatcher (typically Vela; release-engineer when Vela hands off)
**Parallel:** yes (all 5 sub-steps can run in parallel; no filesystem isolation needed since they're checks, not parallel agent dispatches)
**Depends on:** Run Initialized
**Milestone:** Pre-Build PASS
**Milestone timeout:** 30 min

Run before invoking `scripts/build-release.py`. Per release-test-plan v2 §Stage 1.

**Source-vs-extracted tree note:** Stage 1 runs against the SOURCE vault (live vault tree at vault root). Stage 3 runs against the EXTRACTED vault (separately-extracted ship-zip). Do not conflate.

#### Step 1.1 — Vault validate
*Executor: dispatcher.* Run `python3 .tropo/scripts/tropo-validate.py`. Pass criterion: exit 0; zero unresolved cross-references; AGENTS.md/CAPSULE.md coverage 100% on governed folders.

#### Step 1.2 — Ledger rebuild
*Executor: dispatcher.* Run `npx tsx `.tropo/scripts/rebuild-vault.py`. Pass criterion: all vault entries parse; zero unclosed-frontmatter; index regenerates cleanly.

#### Step 1.3 — KB freshness
*Executor: dispatcher.* Manual review + `npm run kb:index`. Pass criterion: no KB article contradicts current ledger / capsule conventions.

#### Step 1.4 — Capsule worked-examples resolution
*Executor: dispatcher.* grep + index lookup. Pass criterion: all UIDs cited in capsule "Worked examples" / "Aligned with" / "Relationship to other capsules" sections resolve in `vault/00-index.jsonl`.

#### Step 1.5 — Open ship-blockers query
*Executor: dispatcher.* Ledger query: `member_of:` includes the release's planning project AND `status: active|accepted` AND `priority: p0`. Pass criterion: zero results.

#### Step 1.6 — Stage 1 verdict + milestone
*Executor: dispatcher.* All 5 sub-steps PASS → write Pre-Build PASS milestone. Any FAIL → HALT; remediate at source; restart Stage 1.

---

### Group 2 — Stage 2: Build + Extract

**Owner:** dispatcher (release-engineer)
**Parallel:** no (sequential through build-release.py + extraction)
**Depends on:** Pre-Build PASS
**Milestone:** Build PASS
**Milestone timeout:** 30 min

Run during `scripts/build-release.py` execution. Per release-test-plan v2 §Stage 2.

#### Step 2.1 — Build script success
*Executor: dispatcher.* Run `python3 .tropo/scripts/build-release.py --version <ver>` (or `--bump patch`). Pass criterion: script exits 0; produces zip + extracted vault at `releases/v<ver>/testing/`.

#### Step 2.2 — Inventory check
*Executor: dispatcher.* Pass criterion: ship-tagged vault entries copied; ship-artifact-declared files copied; kernel files copied; version stamps applied.

#### Step 2.3 — Size sanity
*Executor: dispatcher.* `du -sh` comparison. Pass criterion: final zip within historical envelope (no >2x size jump without explanation).

#### Step 2.4 — Frontmatter validity (extracted)
*Executor: dispatcher.* Run rebuild-vault against extracted root. Pass criterion: every vault file has valid frontmatter.

#### Step 2.5 — Stage 2 verdict + milestone
*Executor: dispatcher.* All 4 sub-steps PASS → write Build PASS milestone. Any FAIL → HALT; investigate build script; restart from Stage 1 if root cause is in source vault, or Stage 2 if local.

---

### Group 3 — Stage 3: Post-Extraction (stranger-arriving experience)

**Owner:** mixed (3.1 Metis or Mike; 3.2 + 3.3 Vela; 3.4 dispatcher)
**Parallel:** yes WITH filesystem isolation per Rule 3 (recommended sequential for v1.4.2 first-runs); sequential is the simpler default
**Depends on:** Build PASS
**Milestone:** Stage 3 verdict (per §Verdict Aggregation)
**Milestone timeout:** 4 hours

Run against the extracted vault at `releases/v<ver>/testing/<vault-name>/` BEFORE atomic-triangle commit.

**Source-vs-extracted note:** Stage 3 operates against the EXTRACTED vault (output of Stage 2.1). Step 1.x ran against source; Step 3.x runs against extracted. Different fixture.

#### Step 3.1 — Walker dispatch (boot chain structural integrity)
*Executor: Mike or Metis (walker allowlist; Vela/Argus denylisted).*

Invoke [`dispatch-walker.playbook` v0.2](dispatch-walker.playbook.md) per Rule 4 — spawn fresh subagent session via Agent tool; subagent reads the sub-playbook + executes its 9 Steps + writes [DONE] to its activation-log record. Pass parameters: target = extracted ship-zip path; user story = release plan §0; dispatcher = `mike` or `metis-<gen>`.

Pass criterion: walker `[DONE]` verdict is PASS or PARTIAL within tolerance (per §Verdict Aggregation tolerance definition). HALT-SHIP class FAIL blocks the gauntlet.

#### Step 3.2 — Cold-boot Strict-mode dispatch
*Executor: Vela (or any cold-boot-allowlisted dispatcher).*

Invoke [`dispatch-cold-boot.playbook` v0.2](dispatch-cold-boot.playbook.md) per Rule 4 with `mode: strict`. Peer walker record UID = Step 3.1 output (paired-Stage-3 dispatch).

Pass criterion: cold-boot Strict `[DONE]` verdict is PASS or PARTIAL within tolerance.

#### Step 3.3 — Cold-boot Skeptic-mode dispatch (DEFERRED-PENDING-CAPSULE bounded per Rule 11)
*Executor: Vela (or any cold-boot-allowlisted dispatcher).*

Invoke [`dispatch-cold-boot.playbook` v0.2](dispatch-cold-boot.playbook.md) per Rule 4 with `mode: skeptic`.

**Pre-spawn capsule check** (per dispatch-cold-boot Step 6): `ls agents/sa/sa.user-error-walker/sa.user-error-walker.md`.

- **If agent capsule exists:** proceed with Skeptic-mode dispatch. Pass criterion: cold-boot Skeptic `[DONE]` verdict is PASS or PARTIAL within tolerance.
- **If agent capsule absent (DEFERRED-PENDING-CAPSULE):** orchestrator marks Stage 3.3 DEFERRED. Per Rule 11, this is bounded transitional state — track in §Known Enforcement Gaps deferral counter. Continue to Step 3.4. Final verdict reflects the deferral per §Verdict Aggregation; on the 3rd consecutive release with capsule still missing, the deferral escalates to HALT-SHIP automatically.

#### Step 3.4 — Extracted-vault validate
*Executor: dispatcher.*

Run `python3 .tropo/scripts/tropo-validate.py --vault-root <extracted-path>`. Pass criterion: exit 0. May run in parallel-with-isolation per Rule 3, but is cheap enough that sequential is preferred.

#### Step 3.5 — Stage 3 verdict + milestone
*Executor: dispatcher.*

Aggregate Stage 3 verdict per §Verdict Aggregation including Rule 12 combinatoric-escalation. Write milestone (Stage 3 PASS / PASS-WITH-FINDINGS / HALT-SHIP-REVIEW / HALT-SHIP). Proceed to Group 4.

---

### Group 4 — Verdict Aggregation + Structured Report

**Owner:** dispatcher
**Parallel:** no
**Depends on:** Stage 3 milestone
**Milestone:** Gauntlet Complete
**Milestone timeout:** 30 min

#### Step 4.1 — Aggregate stage verdicts
*Executor: dispatcher.* Walk Group 1 + Group 2 + Group 3 milestones; produce overall verdict per §Verdict Aggregation including Rule 11 (DEFERRED forcing function) + Rule 12 (combinatoric escalation). Cite all activation-log record UIDs.

#### Step 4.2 — Compose structured report
*Executor: dispatcher.* Per §Report Format. Include: overall verdict; per-stage verdicts + sub-step outcomes; activation-log record UIDs; findings catalog; ship-eligibility statement; Rule 11 deferral count if applicable; Rule 12 combinatoric flag if applicable.

#### Step 4.3 — Append to release entry's verification_artifacts (atomic-triangle eligible)
*Executor: dispatcher.*

Per release.capsule v3.1 Rule 10. **Append discipline:** ALL run records (walker + cold-boot Strict + cold-boot Skeptic if run, OR DEFERRED-PENDING-CAPSULE annotation) atomic with paired-mode discipline per dispatch-cold-boot.playbook v0.2 Rule 2 + Step 9. If verdict is HALT-SHIP / HALT-SHIP-REVIEW, do NOT append by default — Mike's Rule 7 override is the documented exception (override entry adds its own structured record per Rule 7).

**DEFERRED-PENDING-CAPSULE entry shape** (Round 1 v0.2 sweep-close per regression 107 F2). When Stage 3.3 is DEFERRED-PENDING-CAPSULE per Rule 11, append the following structured shape to `verification_artifacts:` instead of a normal cold-boot record entry:

```yaml
verification_artifacts:
  - type: cold-boot
    mode: skeptic
    record_uid: null   # no record exists; agent capsule pending
    deferred: true
    deferred_reason: "sa.user-error-walker capsule pending Argus authoring (Sprint 1b queue); per Rule 11 bounded transitional"
    deferral_count: <integer>   # tracks per-release per Rule 11; this run's increment
    dispatched_at: null   # n/a — not dispatched
```

This preserves the audit trail (the deferral IS evidence of the transitional state) without falsifying a record_uid. Per Rule 11, deferral counts are tracked in §Known Enforcement Gaps row 1; on count ≥3 the deferral escalates to HALT-SHIP (release entry not authored).

#### Step 4.4 — Surface to Mike for §G.5 ship-signal eligibility
*Executor: dispatcher.*

If overall verdict is PASS or PASS-WITH-FINDINGS within tolerance, surface to Mike with the structured report. Mike's §G.5 sign establishes ship.

If HALT-SHIP / HALT-SHIP-REVIEW, surface with failure mode + remediation path. Mike MAY invoke Rule 7 override; if not, cycle does NOT advance.

#### Step 4.5 — Gauntlet Complete milestone
*Executor: dispatcher.* Write Gauntlet Complete milestone. Orchestrator session ends.

---

## Verdict Aggregation

```
Stage 1 ALL PASS     ─┐
Stage 2 ALL PASS     ─┼─→ ship-eligible (atomic-triangle commit eligible per release.capsule v3.1)
Stage 3 verdict      ─┘   (per Stage 3 aggregation rules below)
                          (Mike's §G.5 sign required for ship; orchestrator does not ship)

Stage 3 aggregation rules:
  All sub-stages PASS              → Stage 3 PASS                    → Gauntlet PASS
  ≤1 PARTIAL within tolerance      → Stage 3 PASS-WITH-FINDINGS       → Gauntlet PASS-WITH-FINDINGS
  ≥2 PARTIALs (combinatoric)       → Stage 3 HALT-SHIP-REVIEW         → Gauntlet HALT-SHIP-REVIEW (Rule 12)
  ≥3 PARTIALs OR any HALT-SHIP     → Stage 3 HALT-SHIP                → Gauntlet HALT-SHIP

Stage 3.3 DEFERRED-PENDING-CAPSULE (Rule 11 bounded transitional):
  Deferral count 1 (e.g., v1.4.2)  → counted, continue                → Gauntlet PASS-WITH-FINDINGS (transitional)
  Deferral count 2 (e.g., v1.4.3)  → counted, continue with WARNING   → Gauntlet PASS-WITH-FINDINGS (with warning + escalation hint)
  Deferral count 3 (e.g., v1.4.4)  → forcing function fires           → Gauntlet HALT-SHIP (architectural debt becomes ship-blocking)

Any FAIL or HALT-SHIP at Stage 1 or Stage 2 → Gauntlet HALT-SHIP
                                            → block ship; remediate; bump version; restart from Stage 1
                                            → Mike's Rule 7 override is the documented exception with audit-trail
```

**Verdict line vocabulary** (declared inline per playbook.capsule v2.4 escape hatch — `PASS / PASS-WITH-FINDINGS / HALT-SHIP-REVIEW / HALT-SHIP` is not in the canonical-format enum but four-valued + middle buckets operationally meaningful):

- **PASS** — all stages cleared with no findings worth surfacing. Rare in practice.
- **PASS-WITH-FINDINGS** — gauntlet cleared with P1/P2 findings worth surfacing but no ship-blockers. Most common ship-eligible outcome. Rule 11 DEFERRED-PENDING-CAPSULE counts here in deferral counts 1-2; counts 3+ escalate.
- **HALT-SHIP-REVIEW** (Round 1 v0.2 addition) — combinatoric trigger only: ≥2 PARTIALs in Stage 3 per Rule 12. Ship-blocked by default; ship requires Mike + Argus review of the combinatoric pattern + explicit override per Rule 7. Distinct from outright HALT-SHIP because the constituent verdicts were soft-fails individually; the combinatorics make the aggregate harder. (Rule 11 DEFERRED count 2 stays in PASS-WITH-FINDINGS-with-warning per the deferral table above — distinct mechanism from combinatoric escalation; sweep-fix in v0.2 close per regression cold-boot 107 F1.)
- **HALT-SHIP** — outright ship-blocker (Stage 1 FAIL, Stage 2 FAIL, Stage 3.x HALT-SHIP, ≥3 PARTIALs in Stage 3, OR Rule 11 deferral count ≥3). Block ship; remediate; bump version; restart. Mike's Rule 7 override is the documented exception.

**"PARTIAL within tolerance" definition** (Round 1 v0.2 amendment per cold-boot 106 P1):

A PARTIAL verdict from a Stage 3 sub-stage is "within tolerance" when ALL of the following hold:
- Zero P0 findings in the sub-stage's findings table
- All P1 findings have remediation paths declared OR are dispatcher-discretion-borderline-cases with Argus or Mike sign
- Walker (3.1) does NOT report artifact-layer absence (per dispatch-walker.playbook §Recommendation triage)
- Cold-boot (3.2/3.3) does NOT report HALT-SHIP class drift (per dispatch-cold-boot.playbook §Verdict triggers)

PARTIAL outside tolerance is HALT-SHIP class — it's just a softer phrase for the same thing. Dispatcher classifies in Step 3.5 with reviewer sign for borderline calls.

---

## Escalation Heuristics

(Round 1 v0.2 amendment per skeptic 027 F9 — substrate-vs-session-memory boundary; orchestrator IS the meta-decision-maker; absence of escalation heuristics IS the doctrine-violation the doctrine names.)

When does the dispatcher escalate up vs cycle through? When does HALT-SHIP-REVIEW move to architect-level redesign vs another remediation pass? These are the meta-decisions the orchestrator MUST encode.

**Repeat-finding rule.** If the SAME finding (same root cause; not just same symptom) surfaces in two consecutive gauntlet runs against the same release version, the issue escalates from "remediation work" to "architect review required" — there's a structural pattern the surfacing-layer fix isn't addressing. Surface to Argus on argus-vela; do not auto-remediate a third time.

**Repeat-HALT-SHIP rule.** If the SAME stage HALTs SHIP three times in a row across consecutive gauntlet runs (e.g., Stage 3.2 cold-boot Strict HALTs in v1.4.2-rc1 + rc2 + rc3 with related findings), the cycle is a candidate for architect-level redesign — the artifact-under-test or the test instrument is mismatched. Surface to Argus + Mike for redesign discussion; do not commit to a 4th rebuild without that discussion.

**Multiple Mike override rule.** Mike's Rule 7 HALT-SHIP override is a deliberate exception. **Two or more Rule 7 overrides per release version** trigger architect-review escalation — the override pattern is becoming a workaround for unfixed structural issues. Surface to Argus; the architectural redesign discussion is a Stream 5 / v1.5+ candidate.

**HALT-on-unavailable-release-engineer.** If a Stage 1 or Stage 2 finding requires the release-engineer (typically Vela or build-script-owner) and they're unavailable, dispatcher continues with local-best-effort: document the finding in the orchestrator-run record + flag as DEFERRED-RELEASE-ENGINEER + continue to next eligible step. This is NOT a Rule 11 transitional deferral; it's an operational fallback. The orchestrator's verdict reflects the deferral.

**Ship-pressure binding.** Per Patient Honing Doctrine: rushed building is anti-doctrine. If ship pressure is forcing compression of the gauntlet (e.g., "let's skip Stage 3.3 because Skeptic is slow"), STOP. Surface to Mike with the doctrine reminder. The orchestrator's role is to make the gauntlet uniform across releases; ship-pressure-driven deviations corrupt the institutional learning the gauntlet provides.

**When in doubt, surface, don't cycle.** Three remediation passes without resolution is a signal — the ideal-flow restart-from-Stage-1 pattern (Rule 2) is O(n²) on remediation count under realistic operational pressure (per skeptic 027 F5). Operational reality: cherry-pick safe fixes, but log the cherry-picks as orchestrator-run record entries; the audit trail catches drift.

---

## Outcomes

The run-release-test-plan.playbook is COMPLETE when:

- [REQUIRED] All 5 Groups have fired their milestones (Run Initialized / Pre-Build PASS / Build PASS / Stage 3 verdict / Gauntlet Complete)
- [REQUIRED] Orchestrator-run record exists at `playbook-runs/run-release-test-plan-<release>-<YYYY-MM-DD-HHMM>/run.jsonl` with full event history
- [REQUIRED] Structured report exists in the orchestrator-run record per §Report Format
- [REQUIRED] All activation-log record UIDs are cited in the report (or DEFERRED-PENDING-CAPSULE annotation per Rule 11)
- [REQUIRED] Verdict (PASS / PASS-WITH-FINDINGS / HALT-SHIP-REVIEW / HALT-SHIP) is established
- [REQUIRED-IF-PASS] If PASS or PASS-WITH-FINDINGS within tolerance: report surfaced to Mike for §G.5 ship-signal; release entry's `verification_artifacts:` populated atomically per Rule 8
- [REQUIRED-IF-HALT] If HALT-SHIP-REVIEW or HALT-SHIP without Mike Rule 7 override: report surfaced with failure mode + remediation path; release entry NOT authored; the partial run record set IS the audit trail
- [REQUIRED-IF-OVERRIDE] If HALT with Mike Rule 7 override: override structured-record appended to release entry per Rule 7

The orchestrator does NOT halt mid-execution on stage HALTs — it continues to Group 4 to produce the structured report (the report IS the audit artifact regardless of verdict).

---

## Verification

**Self-attestation.** Same as sibling playbooks — dispatcher self-reports completion via the orchestrator-run record (which IS the audit trail). Group milestones + activation-log record UIDs + structured report constitute the evidence chain.

The TARGET-side verification is each Stage's job; the dispatcher's verification of the orchestrator protocol is the orchestrator-run record's existence + Group milestone completeness + structured report.

---

## Report Format

*Test-harness subtype Required Section per playbook.capsule v2.4. Verdict format declared inline per v2.4 escape hatch — `PASS / PASS-WITH-FINDINGS / HALT-SHIP-REVIEW / HALT-SHIP` is four-valued; middle buckets operationally meaningful with explicit triggers per §Verdict Aggregation.*

**Verdict line.** One of: `PASS` / `PASS-WITH-FINDINGS` / `HALT-SHIP-REVIEW` / `HALT-SHIP`. Trigger conditions per §Verdict Aggregation above.

**Evidence section.** Orchestrator-run record contains:
- Group 0 (Run Initialized) creation event with run_uid + release_version + build_uid + extracted_path
- Group 1 (Stage 1) milestone + 5 sub-step verdicts
- Group 2 (Stage 2) milestone + 4 sub-step verdicts
- Group 3 (Stage 3) milestone + 4 sub-step verdicts (with DEFERRED-PENDING-CAPSULE flag if applicable per Rule 11)
- All activation-log record UIDs
- Findings catalog: P0/P1/P2 by stage with proposed remediation
- Combinatoric flag per Rule 12 if applicable
- Deferral count per Rule 11 if applicable
- Ship-eligibility statement
- Mike Rule 7 override entry if invoked (`{type: ship-override, by: mike, rationale: ..., overridden_verdict: ..., override_at: ...}`)

**Findings table.** Aggregated from sub-playbook records:
- Stage 3.1 walker findings (per dispatch-walker.playbook §Report Format)
- Stage 3.2 cold-boot Strict findings (per dispatch-cold-boot.playbook §Report Format Strict triggers)
- Stage 3.3 cold-boot Skeptic findings (per dispatch-cold-boot.playbook §Report Format Skeptic triggers — when run; DEFERRED annotation when transitional)
- Stage 1/2 findings flat-listed by sub-step

**Convergence note.** This orchestrator IS the canonical convergence-by-disagreement instrument across the gauntlet. **All Stage 3 verdicts MUST be cited in the report** with cross-references between activation-log records (per dispatch-walker.playbook + dispatch-cold-boot.playbook convergence-note rules). Convergence-by-disagreement (e.g., walker PASS + Strict FAIL) signals real divergence; investigate before ship. Rule 12 combinatoric escalation IS the structural enforcement of "≥2 PARTIALs across distinct lenses = something both lenses miss in isolation."

---

## Resources

### Knowledge Base

- [release-test-plan v2 (f4a8c2d6)](../files/f4a8c2d6.md) — the spec this orchestrator implements as executable form. v2 amendment (Sprint 5 task `1f5b3a9d`) formalizes Stage 3.2-strict / 3.3-skeptic split.
- [dispatch-walker.playbook v0.2 (7579f894)](dispatch-walker.playbook.md) — Stage 3.1 sub-playbook.
- [dispatch-cold-boot.playbook v0.2 (a5fb24a6)](dispatch-cold-boot.playbook.md) — Stages 3.2-strict + 3.3-skeptic sub-playbook.
- [release.capsule v3.1 (b19e8d43)](../capsules/release.capsule.md) — Rule 10 declares walker + cold-boot required pre-ship.
- [build.capsule v1.1 (b3d7e5a1)](../capsules/build.capsule.md) — build entry schema for Stage 2.
- [agents/sa/commission-quickref.md (8c3b8017)](../../agents/sa/commission-quickref.md) — sa.* spawn protocol.
- [The Patient Honing Doctrine](../../.tropo-studio/memory/patient-honing-doctrine.md) — doctrinal grounding; Rule 11 + §Escalation Heuristics operationalize the doctrine for the orchestrator's meta-decision-maker role.
- [Strict-vs-Skeptic Test-Harness Modes brief (f7b3e2a1)](../files/f7b3e2a1.md) — informs Stage 3.2/3.3 split.

### Sub-Playbooks Called

- `dispatch-walker.playbook` — Stage 3.1 (spawned per Rule 4 invocation contract)
- `dispatch-cold-boot.playbook` — Stages 3.2 + 3.3 (one invocation per mode; spawned per Rule 4)

These declare `composes_into:` pointing back at this orchestrator's filename slug — bidirectional pair per playbook.capsule v2.4 §Subtypes §Test-Harness composition rule. Validation Check 21 bidirectional consistency loop closes cleanly with this orchestrator's `calls:` declaration.

### Templates

The orchestrator-run record (Group milestones + sub-step verdicts + structured report + Rule 7 override entries when applicable) is the dispatcher's canonical template. Lives at `playbook-runs/run-release-test-plan-<release>-<YYYY-MM-DD-HHMM>/run.jsonl` per Group 0 Step 0.1.

### Exemplar Records

No prior orchestrator-run records exist — this is the first-instance test-harness orchestrator ship in v1.4.2. Eat-own-dog-food test against v1.4.2 itself produces the first exemplar.

---

## Known Enforcement Gaps

| Gap | Severity | Tracking | Land at |
|---|---|---|---|
| `sa.user-error-walker` capsule not yet authored — Rule 11 DEFERRED-PENDING-CAPSULE counter starts at 0; increments per release that defers; resets on capsule lock; escalates to HALT-SHIP at count ≥3 | P1 — bounded transitional | [Argus A41 path-2 decision on argus-vela 2026-05-01](../../channels/argus-vela.md); deferral count tracked here in this row (current: 0 — first eat-own-dog-food run will increment if v1.4.2 runs gauntlet pre-capsule) | Argus authors capsule post-Sprint-1b; deferral counter resets |
| Stage-1-restart back-pressure — restart-from-Stage-1-after-any-Stage-3-fix is O(n²) under realistic remediation; §Escalation Heuristics §When-in-doubt-surface-don't-cycle softens but doesn't formalize | P1 from skeptic 027 F5 | Round 2 polish; possibly partial-restart semantics (re-run only affected stages) | v0.3 amendment OR Sprint 5 spec amendment |
| Sibling-drift hazard — orchestrator + dispatch-walker + dispatch-cold-boot share scaffolding by design; Sprints 2+3 deferrals (max-attempts ceiling, escalation heuristics) now have a HOME (this orchestrator's Rule 12 + §Escalation Heuristics); but no mechanical sync at vault:rebuild | P1 from skeptic 027 F10 + skeptic 026 F7 + skeptic 025 F7 | Round 2 polish; possibly vault-rebuild lint rule | v0.3 amendment OR vault-rebuild infrastructure work |
| §Outcomes lacks `[REQUIRED]` / `[OPTIONAL]` tags per playbook.capsule §3 §Outcomes worked example — affects ALL three siblings (orchestrator + dispatch-walker + dispatch-cold-boot) | P1 from arch-specs 027 F1 | Cross-sprint cleanup — covers walker v0.3 + cold-boot v0.3 + this orchestrator v0.3 | sweep amendment across all three siblings |
| `composes_into: run-release-test-plan` resolved by this orchestrator's `calls:` declaration — Validation Check 21 bidirectional loop is now closeable for v1.4.2 test-harness suite (per arch-specs 027 Probe 7 PASS) | P3 housekeeping — closes a gap noted in Sprints 2+3 §Known Enforcement Gaps | Sprints 2+3 sibling §Known Enforcement Gaps rows can be closed at sibling v0.3 amendment | sibling v0.3 amendments (sweep) |
| Capsule v2.5 amendment candidates inherited from Sprints 2+3 + Sprint 4: (a) `mode:` semantics for dual-mode playbooks (sub-playbook gap), (b) placeholder/forward-reference dispatch targets, (c) `dispatches:` typed-field-vs-relationships lean, (d) verdict_format canonical enum extension to include orchestrator's `PASS/PASS-WITH-FINDINGS/HALT-SHIP-REVIEW/HALT-SHIP` 4-valued shape (or codify inline-declaration as canonical for orchestrator-class) | P2 — Argus-lane capsule work | [argus-vela 2026-05-01 capsule v2.5 [QUERY]](../../channels/argus-vela.md) | playbook.capsule v2.5 |

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 0.1 | 2026-05-01 | Initial draft per Sprint 4 of v1.4.2 cycle. Top-level orchestrator pulling dispatch-walker.playbook v0.2 + dispatch-cold-boot.playbook v0.2 together as the executable form of release-test-plan v1. Authored against playbook.capsule v2.4 test-harness subtype. Uses Groups model. Stage 3.3 Skeptic-mode DEFERRED-PENDING-CAPSULE behavior declared as transitional. | vela-v37 |
| 0.3 | 2026-05-01 | **Stream 1 cross-sprint sweep close** — descriptor drift fixed ("release-test-plan v1" → "release-test-plan v2" across §Description, §Intent, frontmatter relationships comments, §Resources, §Stage 1+2 prose; UID resolution preserved); §Outcomes [REQUIRED] / [REQUIRED-IF-X] tags added per playbook.capsule v2.4 §3 §Outcomes worked example (closes arch-specs 027 F1 sibling-cut finding affecting all 3 playbooks); 107-F3 cognitive translation tax cosmetic from regression record 107 absorbed into v0.3 sweep. v2 spec descriptor canonicalized at Sprint 5 lock 2026-05-01. activation-log.capsule v1.0 (`5d3a7e4b`) locked 2026-05-01 by argus-a41 (Sprint 1b). | vela-v37 |
| 0.2 | 2026-05-01 | **Round 1 BATCH remediation + sweep close** — folds 4 P0 + 4 high-leverage P1 from three-instrument convergence (sa.cold-boot 106 + sa.arch-specs 027 + sa.skeptic 027); plus 2 sweep-close fixes from regression sa.cold-boot 107 (107-F1 internal contradiction in §Verdict Aggregation HALT-SHIP-REVIEW vs Rule 11 deferral count=2 — resolved by removing DEFERRED-clause from HALT-SHIP-REVIEW bucket; 107-F2 DEFERRED-PENDING-CAPSULE `verification_artifacts:` entry shape declared at Step 4.3). Locked status:active 2026-05-01 by vela-v37 post-regression-PASS-WITH-NEW-FINDINGS (107-F3 cosmetic deferred to v0.3). **P0-1 (cold-boot 106 F1 + skeptic 027 F4 convergence):** Rule 4 declares sub-playbook invocation MUST spawn fresh subagent session per invocation; canonical model named. **P0-2 (skeptic 027 F1 + cold-boot 106 F2 convergence):** Rule 11 declares DEFERRED-PENDING-CAPSULE bounded transitional with max-2-cycle forcing function; deferral counter tracked in §Known Enforcement Gaps row 1; count ≥3 escalates to HALT-SHIP. **P0-3 (skeptic 027 F2):** Rule 12 declares combinatoric-escalation rule — ≥2 PARTIALs in Stage 3 → HALT-SHIP-REVIEW; ≥3 PARTIALs → HALT-SHIP. **P0-4 (skeptic 027 F6):** Rule 5 + Rule 7 reconciled — HALT-SHIP override path documented with structured override-record + multiple-overrides-trigger-architect-review (per §Escalation Heuristics). **P1 fixes:** §Escalation Heuristics section added (skeptic 027 F9 — substrate-vs-session-memory doctrine compliance: repeat-finding rule, repeat-HALT-SHIP rule, multiple Mike override rule, HALT-on-unavailable, ship-pressure binding, when-in-doubt-surface); "PARTIAL within tolerance" definition added to §Verdict Aggregation (cold-boot 106 P1); Rule 3 + Step 3 group declaration distinguish parallel-with-isolation vs sequential default (cold-boot 106 + skeptic 027 F3 convergence); Group 0 added with orchestrator-run record path/filename declaration at `playbook-runs/run-release-test-plan-<release>-<YYYY-MM-DD-HHMM>/run.jsonl` + multi-run canonical-of-record semantic (cold-boot 106 + skeptic 027 F8 convergence). HALT-SHIP-REVIEW added as new verdict bucket (4-valued vocabulary; declared inline per v2.4 escape hatch). Round 2 deferred (tracked in §Known Enforcement Gaps): Stage-1-restart partial-restart semantics, §Outcomes [REQUIRED] tags (cross-sprint cleanup affecting all 3 siblings), sibling-drift mechanical sync, capsule v2.5 amendments (Argus-lane), 5 P2 + 1 P3 polish. | vela-v37 |

---

*run-release-test-plan.playbook | v0.3 active (cross-sprint sweep close 2026-05-01) | Vela V37 | 2026-05-01*
*"Stage 1 catches what didn't ship. Stage 2 catches what shouldn't ship. Stage 3 catches what shouldn't have shipped. The orchestrator catches what each catches alone."*
