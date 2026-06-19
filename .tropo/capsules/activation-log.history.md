---
uid: 2207c655
type: capsule-history
governs: 8406c4f8
governs_path: ".tropo/capsules/activation-log.capsule.md"
extracted_at: 2026-05-11
extracted_by: argus-a55
extracted_in_release: pending-v1.18.0
extracted_in_cycle: "v1.18.0 — Capsule Library Phase 1"
schema_version: 2
governed_by: 5ec083a3   # capsule-history.capsule (v1.18.0 Stream C remediation)
extraction_scope: argo-private
member_of:
  - "99ed55fd"   # tropo-agents
  - "8dd772a0"   # tropo-governance
  - "be5bc951"   # v1.18.0 activation root
tags: [capsule-history, extracted-from-activation-log-capsule, v1.18.0-extraction]
---

# activation-log — Capsule History

*Historical record extracted from the active capsule at v1.18.0 to keep the active body pedagogy-first per Lock C. Active capsule at `.tropo/capsules/activation-log.capsule.md` (UID `8406c4f8`). This file preserves Limitations + Bootstrapping Case + Examples + Backfill Plan + Studio Shop Signage + Change Log + lineage footer.*

---

## Limitations (acknowledged — v1.1+ scope)

**Honest authorship contract.** v1.0 enforces nominal consistency for honest authors via Checks 1-24 + Rules 1-12. Records validated against these checks carry the v1.0 trust contract: filenames match record numbers, frontmatter matches body, verdict transcription is verbatim, cross-class linkage is explicit, uncertain-flagged records are not cite-eligible. The limitations below describe known scope-deferred attack surfaces against bad actors with consistent-forgery capability — tracked for v1.1+.

v1.0 detects only **consistent forgery** — cross-field self-consistency (Checks 5, 6, 13). **Substantive provenance** — proof that `commissioned_by:` reflects the actual harness identity that dispatched the spawn — requires an out-of-band anchor (e.g., a dispatch-time provenance crumb in `dispatches.jsonl`, or harness-identity attestation). v1.1+ concern, scoped to v1.5+ thesis arc at [v1.4.2+ Backlog (`c3e9f12a`)](../../vault/files/c3e9f12a.md).

Until then: **independence-violation laundering** by an actor with consistent forgery (writing `commissioned_by: <allowed-handle>` in both frontmatter AND body when actually dispatched by a denylisted role) is undetectable by this capsule alone. The per-agent activation file's `spawn_blocklist:` enforcement happens at dispatch time; bypass leaves no trace in the record.

**Companion limitations:**
- `target:` field is unconstrained free-text (Check 7 only requires non-empty). Target laundering — passing a clean walk of build A as a walk of build B — is not detected by v1.0. v1.1+ candidate: when `target:` is a UID, require it to resolve in registry; encourage hash-pinning (`target_sha:`) for build-directory targets.
- `extraction_scope` mismatch with per-agent declared default is documented but not enforced. v1.1+ candidate: enforce match; overrides require `extraction_scope_override_reason:` field.
- **Closure-path-(a) self-attestation is forgeable** (per [sa.skeptic 028](../../agents/sa/sa.skeptic/activation-log/028-argus-a41-record.md) NEW P1-1, 2026-05-01). Rule 12 closure protocol path (a) requires writing `verdict_resolved_by:` + `verdict_resolved_at:` markers, but these are honor-system with no review-record-UID anchor — same consistent-forgery class as headline limitation. v1.1+ candidate: optional segregation-of-duties rule (`verdict_resolved_by != backfilled_by`) for cheap proxy-attack cost-raise; or stronger, `verdict_resolved_review_record:` UID pointing at manual-review artifact.
- **No time-bound closure SLO** for `verdict_inference_uncertain:` records (per [sa.skeptic 028](../../agents/sa/sa.skeptic/activation-log/028-argus-a41-record.md) NEW P2-1, 2026-05-01). Records flagged uncertain may remain uncited indefinitely. Cite-eligibility gate structurally honored (Check 24); operational follow-through not enforced. v1.1+ candidate: SLO + escalation if closure not reached within N days.

These are documented limitations, not v1.0 ship-blockers.

---

## Bootstrapping Case (full detail)

When commissioning record 001 of a brand-new sa.* class whose activation file does not yet exist (the bootstrap window), the dispatcher follows fallback rules until the activation file lands:

- **`[PENDING]` shape:** use the inline generic template below (subset of [sa/CAPSULE.md (7d3f9a2c)](../../agents/sa/.tropo-studio/CAPSULE.md) §Record File Format). Per-agent specialized template lands when the activation file does.

  ```
  [PENDING] <task description in one sentence>

  Context: <one sentence on what this sa.* is supposed to do — temporary placeholder until activation file lands>
  Task: <what the sa.* should attempt — the per-agent contract is bootstrap-shaped here>
  Output: <expected output shape — minimum: a verdict and findings; specifics defer to activation file when authored>
  ```

- **`verdict` vocabulary:** dispatcher does not pre-populate `verdict:` at dispatch time (verdict is `complete*`-only — `dispatched` records OMIT verdict per §Conditional Frontmatter). Once the activation file lands and the agent completes its first run, the agent's §Output Format declares verdict values.

- **Per-agent extensions:** OPTIONAL during bootstrap. Records authored before the activation file lands MAY omit walker-family or cold-boot-family extensions. **Sticky per-record:** a record authored during the bootstrap window stays bootstrap-shaped even after the activation file lands; subsequent records (002+) carry the full per-agent contract. To upgrade record 001 retroactively, follow §Backfill Plan with `backfilled: true` markers.

- **Filename pattern:** Pattern A (default) unless the agent's name suffix signals walker-family membership (`*-walker` → Pattern B).

- **`agent:` membership inference:** until §Agent Class Membership table lands (v1.1+ candidate), use name suffix conventions: `*-walker` → walker family; everything else → verification-record family.

**Bootstrap window closure trigger:** the window closes when the per-agent activation file is authored at `status: active`. Detection: validator checks for `agents/sa/<name>/<name>.md` with frontmatter `status: active`. From that point:
- New records (002+) MUST conform fully to the activation file's declared `record_extensions:` (when [v1.3 amendment (168fb3f8)](../../vault/files/168fb3f8.md) lands) or its prose §Output Format declarations.
- The bootstrap-shape record 001 stays sticky as audit trail. Backfill is OPTIONAL for record 001 (orphan acceptable per §Backfill Plan tier-2 spot-check); REQUIRED only if record 001 is later cited from `release.capsule.verification_artifacts:` (tier-1 100%-cold-boot rule).

**Concrete near-term case:** the forthcoming `sa.user-error-walker` (Argus-lane post-Sprint-1b, per [Strict-vs-Skeptic brief f7b3e2a1](../../vault/files/f7b3e2a1.md)) — its first commission at record 001 will exercise this bootstrap window. Pattern B by walker-family precedent; `[PENDING]` template via the inline generic above; verdict OMITTED until activation file lands and first complete fires.

---

## Examples (full)

### Minimal — `status: complete`, cold-boot record (Pattern A)

```yaml
---
uid: <8-hex>
record: 100
agent: sa.cold-boot
mode: B-BATCH
commissioned_by: argus-a41
commissioned_at: "2026-05-01"
target: ".tropo/capsules/activation-log.capsule.md"
status: complete
verdict: "PASS-WITH-GAPS"
schema_version: 2
---

# sa.cold-boot — Activation Record 100
*Spawned by: argus-a41 | Date: 2026-05-01 | Target: activation-log.capsule v0.1*

---

[RESPONSE] Terminate after [DONE]. Batch run.

[PENDING] Cold-boot test: .tropo/capsules/activation-log.capsule.md
...

[IN-PROGRESS] ...

[DONE] Cold-boot test: activation-log.capsule v0.1 — PASS-WITH-GAPS
... [body must include verdict text "PASS-WITH-GAPS" verbatim per Check 21] ...

[SHUTDOWN]
```

Filename: `100-argus-a41-record.md`.

### Walker — `status: complete` with per-agent extensions (Pattern B)

```yaml
---
uid: a003f1c0
record: 003
agent: sa.first-use-walker
mode: B-BATCH
commissioned_by: metis-g48
commissioned_at: "2026-04-29"
target: "releases/v1.4.1/testing/tropo-os-v1.4.1/"
status: complete
verdict: "PASS"
schema_version: 2
build_under_test: "Tropo-OS v1.4.1"
prior_record: <walker-002-uid>
encounters_unprompted: 14
encounters_strong: 9
ceremony_load: 2
governed_by: 6742f183
extraction_scope: argo-private
---
```

Filename: `003-metis-g48-v1.4.1-rc1.md`.

### Salvage — `status: complete-via-salvage` (V36's 099 precedent)

```yaml
---
uid: a099c0b9
record: 099
agent: sa.cold-boot
mode: B-BATCH
commissioned_by: vela-v36
commissioned_at: "2026-04-30"
target: "/tmp/tropo-os-v1.4.1-fresh/tropo-os-v1.4.1/"
status: complete-via-salvage
verdict: "PASS-WITH-FINDINGS (5 findings inferred from artifact inspection)"
findings_source: artifact_inspection_only
agent_stall_caveat: "Stream watchdog fired at 600s no-progress mid-report-write. Diary insights LOST."
schema_version: 2
basis_artifact: "releases/v1.4.1/dist/tropo-os-v1.4.1.zip"
completed_at: "2026-04-30T14:46:00"
---
```

Body contains spawner-authored `[DONE]` block (per Row 6) + spawner-synthetic `[SHUTDOWN]` (per Row 7). Verdict text in frontmatter appears verbatim in body per Check 21.

### Blocked — refused dispatch

```yaml
---
uid: <8-hex>
record: 004
agent: sa.first-use-walker
mode: B-BATCH
commissioned_by: vela-v37
commissioned_at: "2026-05-02"
target: "releases/v1.4.2/testing/tropo-os-v1.4.2/"
status: blocked
blocked_reason: dispatcher-not-allowed
schema_version: 2
---
```

Body contains `[BLOCKED]` block citing `spawn_blocklist: [vela, argus]` per walker capsule. Re-dispatch by Mike or Metis at NNN+1.

---

## Backfill Plan

Activation-log records authored before this capsule locks may lack the required frontmatter. The validator's checks 1-9 will fail on legacy records until they're backfilled. The capsule does NOT accept records-without-frontmatter as valid; permissiveness would defeat the purpose.

**Backfill scope** (v1.4.1-era and prior records lacking frontmatter):
- [sa.cold-boot 100](../../agents/sa/sa.cold-boot/activation-log/100-argus-a39-record.md), [101](../../agents/sa/sa.cold-boot/activation-log/101-argus-a39-record.md) (A39)
- [sa.first-use-walker 002](../../agents/sa/sa.first-use-walker/activation-log/002-argus-a39-v1.4.0-rc1.md) (A39)
- Likely 097/098 + earlier records — full sweep needed at backfill time

**Backfill procedure** (post-lock cleanup task):

1. **Provenance markers — required.** Every backfilled record MUST carry in frontmatter: `backfilled: true` + `backfilled_by: <agent-handle>` + `backfilled_at: <date>`. Distinguishes inference-products from origin-authored records.

2. **Verdict-detection — structural rule, not judgment call.** Grep body for `PASS`, `FAIL`, `PARTIAL`, `PASS-WITH-GAPS`, `PASS-WITH-FINDINGS`, etc. on lines containing the literal string `Verdict:` or `[DONE]` or "verdict". If multiple matches that disagree, OR zero matches, flag with `verdict_inference_uncertain: true` and surface for manual review. The verbatim-match rule (Check 21) applies.

3. **`verdict_inference_uncertain:` closure protocol** (per Rule 12 + Check 24): Records flagged `verdict_inference_uncertain: true` are NOT cite-eligible from `release.capsule.verification_artifacts:` arrays or active `prior_record:` chains until the flag is closed. Closure paths: **(a) Verdict resolved** (manual review recovers; remove flag; add `verdict_resolved_by: <agent-handle>` + `verdict_resolved_at: <date>` markers; Check 21 verbatim-match must hold against the recovered verdict). **(b) Verdict unrecoverable** (reclassify to `status: blocked` + `blocked_reason: verdict_unrecoverable`). Records with the flag still set are queryable as a backlog (`grep '"verdict_inference_uncertain":true' vault/00-index.jsonl`).

4. **Coverage tiering:** Tier 1 — 100% cold-boot validation required for any backfilled record cited from `release.capsule.verification_artifacts:` or referenced by an active `prior_record:` chain. Tier 2 — Spot-check (~3 records or ~5%) acceptable for orphaned records nobody cites.

5. **Mechanical edit, not behavioral change.** Backfill writes frontmatter at top of file based on body inference. Body content is never modified.

This procedure is captured for the v1.4.2 cleanup task post-lock — the Sprint 1b task spec [`5d3a7e4b`](../../vault/files/5d3a7e4b.md) verification criterion *"All v1.4.1-era activation-log records validate against the capsule"* is met by executing the backfill procedure above on all legacy records.

---

## Studio — Shop Signage (extracted from prior active body)

*Quick-reference section dropped from active body at v1.18.0 refactor per Mike-A55 directive 2026-05-11 — capsules are agent-read substrate; quick-reference for humans is not the load-bearing use case.*

**Tools:** `ls agents/sa/<name>/activation-log/` · [sa/CAPSULE.md (7d3f9a2c)](../../agents/sa/.tropo-studio/CAPSULE.md) · [commission-quickref.md](../../agents/sa/commission-quickref.md) · reference records (sa.first-use-walker 003 a003f1c0, sa.cold-boot 099 a099c0b9 salvage) · [registry.jsonl](../../.tropo-studio/registries/registry.jsonl)

**Procedures:**
- **Author a new record (BATCH mode)** — spawner creates `<NNN>-<spawner>-record.md` with required frontmatter (status: `dispatched`), header + commission block, then spawns the agent
- **Author a new record (LIVE-CHANNEL mode)** — spawner creates file with header only; agent writes `[QUERY]`; spawner appends `[RESPONSE]` and `[PENDING]` items; agent processes
- **Advance to complete** — agent writes `[IN-PROGRESS]`, `[DONE]` with verdict per per-agent §Output Format (Check 21: verdict appears verbatim in `[DONE]` body), `[SHUTDOWN]`. Spawner updates frontmatter `status: complete` + `verdict:` + `completed_at:` after spawn closes
- **Salvage from a stall** — spawner inspects artifacts, authors `[DONE]` block from evidence (Row 6 spawner-during-salvage), writes synthetic `[SHUTDOWN]` (Row 7), sets frontmatter `status: complete-via-salvage` + `verdict:` + `findings_source` + `agent_stall_caveat`
- **Block a refused dispatch** — agent writes `[BLOCKED]` with reason. Spawner sets `status: blocked` + `blocked_reason:`. Re-dispatch at NNN+1
- **Cite a record cross-document** — by UID, not NNN
- **Backfill a legacy record** — see §Backfill Plan above
- **Close a `verdict_inference_uncertain:` flag** — see §Backfill Plan §3

**Pitfalls** (full list preserved here; summary in active body §4 Validation Checks):
- Authoring records without frontmatter — Check 1-9 violations
- Mismatched filename `<NNN>` vs frontmatter `record:` — Check 2 violation
- Re-dispatching at the same NNN after BLOCKED — Rule 1 violation
- Setting `status: complete` without `verdict` — Check 10 violation
- Setting `status: complete` with empty `[DONE]` block — Check 21 violation
- Setting `status: complete-via-salvage` without `findings_source` + `agent_stall_caveat` — Check 11 violation
- Setting `status: blocked` without `blocked_reason` — Check 12 violation
- Citing records by NNN instead of UID — Rule 7 violation
- Using `prior_record:` to cite a record of a different `agent:` class — Rule 10 + Check 20 violation
- Citing a `verdict_inference_uncertain: true` record from `release.capsule.verification_artifacts:` — Rule 12 + Check 24 violation
- Pattern C record with non-routine status whose filename doesn't surface that status — Pattern C status-disclosure rule violation
- Backfilling without `backfilled:` provenance markers — §Backfill Plan violation

**Worked examples:**
- [sa.cold-boot 099 (a099c0b9)](../../agents/sa/sa.cold-boot/activation-log/099-vela-v36-record.md) — V36's salvage example
- [sa.first-use-walker 003 (a003f1c0)](../../agents/sa/sa.first-use-walker/activation-log/003-metis-g48-v1.4.1-rc1.md) — walker Pattern B
- [Sprint 1b BATCH triple — sa.arch-specs 026 + sa.skeptic 026 + sa.cold-boot 104](../../agents/sa/sa.arch-specs/activation-log/026-argus-a41-record.md) — Round 1 verification
- [Round 2 regression — sa.arch-specs 027 + sa.skeptic 027 + sa.cold-boot 105](../../agents/sa/sa.arch-specs/activation-log/027-argus-a41-record.md) — Round 2

---

## Change Log

| Version | Date | Change | Author |
|---|---|---|---|
| 0.1 | 2026-05-01 | Initial DRAFT. Schema-from-real-records: codifies V36's records (099, walker 003) frontmatter conventions; surfaces heterogeneity gap (A39's records lack frontmatter — backfill scoped post-lock). Universal floor (9 required fields) + 4 conditional fields + 5 universal optional + named per-agent extensions for walker / cold-boot families. State machine: `dispatched → complete | complete-via-salvage | blocked` (one-way). 20 validation checks. Three filename conventions (Pattern A/B/C). | Argus A41 |
| 0.2 | 2026-05-01 | **Bundled remediation pass folding 25 findings from Round 1 three-instrument BATCH** ([arch-specs 026](../../agents/sa/sa.arch-specs/activation-log/026-argus-a41-record.md) + [skeptic 026](../../agents/sa/sa.skeptic/activation-log/026-argus-a41-record.md) + [cold-boot 104](../../agents/sa/sa.cold-boot/activation-log/104-argus-a41-record.md)). NEW sections: §Inheritance from core (closes arch-specs P0-1), §Archival Trigger (closes arch-specs P0-2), §Limitations (acknowledges skeptic P0-1), §Bootstrapping Case (closes cold-boot P0). NEW Governance Rules: Rule 9 (verdict transcription universal), Rule 10 (cross-class linkage uses `relationships:`), Rule 11 (frontmatter authoritative). NEW Validation Checks: Check 21, Check 22, Check 23. Sibling amendments filed: [aa39ff6a](../../vault/files/aa39ff6a.md), [168fb3f8](../../vault/files/168fb3f8.md). | Argus A41 |
| 0.3 | 2026-05-01 | **Round 2 close-out fold**: 8 NEW findings from Round 2 BATCH ([arch-specs 027](../../agents/sa/sa.arch-specs/activation-log/027-argus-a41-record.md) + [skeptic 027](../../agents/sa/sa.skeptic/activation-log/027-argus-a41-record.md) + [cold-boot 105](../../agents/sa/sa.cold-boot/activation-log/105-argus-a41-record.md)). Q1 close-out across all three lenses: YES. Zero NEW P0s. NEW Rule 12 + Check 24 (skeptic NEW P1-1 LOAD-BEARING — `verdict_inference_uncertain:` cite-eligibility closure protocol). Rule 11 expanded. §Bootstrapping Case rewritten. §Inheritance + §Limitations + §Backfill Plan polished. | Argus A41 |
| 1.0 | 2026-05-01 | **LOCKED.** Single-instrument [sa.skeptic 028 regression](../../agents/sa/sa.skeptic/activation-log/028-argus-a41-record.md) returned PASS-WITH-NEW-FINDINGS with Q1 close-out: YES on cite-eligibility fix (Rule 12 + Check 24 + §Backfill Plan §3). Skeptic recommended Option A: atomic v0.3 → v1.0 LOCK with 2 NEW documented-limitation findings folded into §Limitations. Sprint 1b CLOSED. | Argus A41 + Mike Maziarz |
| 1.1 | 2026-05-11 | **v1.18.0 Stream B body refactor.** Body restructured to 5-section canonical structure (Intent → Schema → State Machine → Validation Rules → Composes-With) per v1.18.0 brief §4.1 Q3-locked pattern. Historical content (§Limitations full detail + §Bootstrapping Case full detail + §Examples + §Backfill Plan + §Studio Shop Signage + §Change Log + lineage footer) extracted to this `.history.md` companion file (UID `2207c655`). Active body trimmed from 583 → ~290 lines (~50% reduction); all historical content preserved in this file. `history_file:` + `last_body_refactor:` frontmatter fields added. No semantic changes to §Validation Rules / §State Machine / §Schema content; pure restructure + extraction. UID preserved at `8406c4f8`. | argus-a55 |

---

## Lineage footer (extracted from prior active body)

*activation-log Capsule Definition | **LOCKED v1.0** | Argus A41 | 2026-05-01*
*"The record is the audit trail. The capsule makes it auditable."*
*Spec governance: [`222873b9`](../../vault/files/222873b9.md) (Ledger Schema v2). Sibling: [session-agent.capsule (b4e2a718)](session-agent.capsule.md). Aligned with: [sa/CAPSULE.md (7d3f9a2c)](../../agents/sa/.tropo-studio/CAPSULE.md). Authored under [The Patient Honing Doctrine](../../.tropo-studio/memory/patient-honing-doctrine.md).*

---

## Provenance

- Extracted: 2026-05-11
- Extracted by: argus-a55
- Extracted in cycle: v1.18.0 Stream B (Capsule Library Phase 1)
- Active capsule version at extraction: v1.0
- Active capsule version after extraction: v1.1 (non-breaking; body-only refactor)
- Extraction-fidelity check: every Limitations subsection + Bootstrapping Case content + Examples + Backfill Plan + Studio Shop Signage + Change Log row + lineage footer preserved in this file.

---

*activation-log capsule history | UID `2207c655` | extracted from `8406c4f8` | v1.18.0 Stream B extraction 2026-05-11*
