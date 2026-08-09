---
uid: 47c26a60
type: dev-spec
title: "Memory reinforcement scoring — a recurrence counter for the curator"
description: "Adds reinforcement_count (a recurrence signal distinct from read-usage), incremented on ratified MERGE, into memory scoring — so lessons reality re-teaches auto-float."
status: locked
locked_by: argus
locked_at: '2026-07-22'
dev_spec_activation_uid: 'b233b7ac'
priority: p2
owner: argus
assigned_to: talos
author: argus-a136
created: 2026-07-22
modified: '2026-07-22'
created_by: argus-a136
modified_by: tropo-lock-dev-spec.py
schema_version: 2
capsule_version: '1.5'
extraction_scope: ship
governed_by: 8dd772a0
member_of:
  - cd1fcd25
target_release: "1.90.0"
target_stream: memory-v3-1-reinforcement
gauntlet_rounds_required: 5
references_cycle_brief: 6dd954b9
refs:
  - 6dd954b9
  - a5b3c891
  - 5f2c1b94
  - 50c0bdce
committed_substrate:
  - target: vault/capsules/tropo-memory.capsule.md
    change_class: AMENDED
    description: "v1.5 -> v1.6 (Mike-approved lock-break): add reinforcement_count + reinforced_by as curator-mutable optional frontmatter; add validation checks + governance-contract split."
  - target: .tropo-studio/score-formula-doctrine.md
    change_class: AMENDED
    description: "v1.0 -> v1.1: add the reinforcement signal (log-compressed, distinct from usage) to the composite; rebalance weights to sum 1.0; declare the reinforce half-life/cap."
  - target: vault/session-agents/50c0bdce.md
    change_class: AMENDED
    description: "sa.memory-curator: on a ratified MERGE, increment survivor reinforcement_count (+= merged+1), append generations to reinforced_by, and compute the reinforce signal in the scoring pass."
  - target: vault/tools/tropo-validate.py
    change_class: AMENDED
    description: "Add checks: reinforcement_count is a non-negative integer; curator-mutable-field discipline covers it; reinforced_by entries are well-formed generation labels."
  - target: "planned identifier: vault/tools/tests/test_memory_reinforcement.py"
    change_class: NEW
    description: "Plants: MERGE increments + lineage, score monotonicity in reinforcement_count, log-compression cap, non-curator write refusal, weight-sum invariant, seeding backfill."
acceptance_criteria:
  - "REINFORCE FIELD: a memory entry may carry reinforcement_count (non-negative integer, default 0, curator-mutable) + reinforced_by (list of generation labels); a non-curator write to reinforcement_count surfaces the same discipline finding as the other curator-mutable fields; the capsule documents both."
  - "MERGE INCREMENTS + LINEAGE: when sa.memory-curator's MERGE recommendation is human-ratified, the survivor's reinforcement_count increases by (merged entry's reinforcement_count + 1) and the merged entry's contributing generation(s) are appended to the survivor's reinforced_by; an unratified/rejected merge changes neither field."
  - "SCORE INTEGRATION: the composite score gains a reinforcement term (log-compressed like usage: log10(max(reinforcement_count,1)) normalized by a declared cap), the four prior weights + the new one sum to exactly 1.0, and an entry with higher reinforcement_count (all else equal) scores >= one with lower — monotonic, never negative."
  - "DISTINCT SIGNAL: reinforcement_count is never conflated with reference_count in code or doctrine (reads vs re-learns stay separate signals); the doctrine states the distinction explicitly."
  - "SEEDING (optional, curator-assisted): a documented one-time backfill path lets the curator set reinforcement_count for existing hand-merged pins (e.g. an entry whose body records N generations independently re-deriving it) from evidence, without fabricating counts — evidence-backed only, flagged for ratification."
  - "NO RUNAWAY BY CONSTRUCTION: every increment is gated by a human-ratified merge (no auto-merge, no write-time similarity auto-increment); the log-compression bounds any single entry's reinforce contribution; the curator remains off the critical path."
  - "NON-DESTRUCTIVE: the merged-away entry follows existing MERGE lifecycle (archived, not destroyed); reinforced_by preserves its contributing lineage so the recurrence is auditable."
risk_register:
  - risk: "Over-merge inflates a false recurrence signal (two distinct lessons merged as one)."
    mitigation: "Every +1 is human-ratified (the existing MERGE ratification flow); no auto-increment. Log-compression caps any single entry's dominance. The merged entry is archived (recoverable), not destroyed."
  - risk: "Weight rebalance destabilizes existing tiers (entries oscillate current<->topic after the new signal lands)."
    mitigation: "Calibrate the new weight against the live corpus at first curator pass (same procedure the doctrine already uses for initial weights); ship with the reinforce weight small; hysteresis in tier thresholds already prevents oscillation."
  - risk: "Amending a Mike-locked capsule (memory.capsule v1.5) without approval."
    mitigation: "The capsule amendment is a Mike-approved lock-break (this dev-spec is the vehicle); build does not proceed on the capsule until Mike signs, exactly as every prior memory amendment (v1.1 A106, v1.5 A132)."
tags: [dev-spec, memory, v3-1, reinforcement, recurrence, score-formula, curator, mike-idea]
---

# Memory reinforcement scoring — a recurrence counter for the curator

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [dev-pipeline](cd1fcd25.md) → **Memory reinforcement scoring — a recurrence counter for t...**
<!-- nav-block:end -->

## Outcome

Make one product sentence mechanically true:

> A memory that reality independently re-taught the agent N times outranks one merely looked up often — because recurrence is a distinct, first-class scoring signal, not invisible prose.

Mike-originated idea (2026-07-20). The design-brief `6dd954b9` holds the framing + the gap analysis; this dev-spec commits the build.

## The gap (from the brief)

The score formula ([`5f2c1b94`](5f2c1b94.md)) scores three signals: **recency**, **usage** (`reference_count` = reads/citations, log-compressed), **explicit pins** (Wilson). The curator ([`50c0bdce`](50c0bdce.md)) already has a `MERGE` action that consolidates a detected duplicate into the higher-`reference_count` survivor, human-ratified — but it **discards the recurrence**: it keeps the higher-read entry and drops the other without recording that the lesson *re-emerged*. So the system counts how often a memory is *looked up*, never how often reality *re-taught* it. Recurrence is arguably the strongest importance signal (an agent independently re-deriving the same lesson from fresh experience N times), and today it exists only as hand-maintained prose (e.g. Argus's #1 pin = ten generations A115–A135 hand-merged into one entry), invisible to the score.

## Design

### 1. Fields (memory.capsule v1.5 → v1.6, curator-mutable optional)
- `reinforcement_count` — integer, default 0, **curator-mutable**. Count of ratified consolidations into this entry. **Kept strictly separate from `reference_count`** (reads ≠ re-learns).
- `reinforced_by` — list of generation labels (e.g. `[A115, A124, A129, A135]`), **curator-mutable**. The contributing-generation lineage — feeds the permanent-record principle and makes the recurrence auditable.

The capsule already permits unpoliced extras (§Optional line), but a first-class feature documents the fields in the Optional Frontmatter table + Governance Contract (curator-mutable) + Validation Checks. That documentation is the v1.6 amendment — a Mike-approved lock-break, this dev-spec being the vehicle.

### 2. Curator MERGE does the +1 (sa.memory-curator, 50c0bdce)
On a **human-ratified** MERGE (existing Phase 6/7 flow): the survivor's `reinforcement_count += (merged.reinforcement_count + 1)`, and the merged entry's contributing generation(s) append to the survivor's `reinforced_by` (dedup). Rejected/deferred merges touch neither. Detection stays where it is (curator-time, off the critical path, "similar context + body") — **no write-time matching**, so an agent jotting a note never pays a search + similarity judgment.

### 3. Score formula (score-formula-doctrine v1.0 → v1.1)
Add a reinforcement term, log-compressed like usage:
```
reinforce_signal(M) = min( log10(max(reinforcement_count(M),1)) / log10(reinforce_cap), 1.0 )
score(M) = w_recency·age_decay + w_usage·usage + w_pin·wilson + w_reinforce·reinforce_signal + w_subtype·subtype_weight
```
Proposed rebalance (sum = 1.0; calibrate at first pass per the doctrine's existing procedure): `w_recency 0.20, w_usage 0.30, w_pin 0.25, w_reinforce 0.15, w_subtype 0.10`. `reinforce_cap` initial 100 (a lesson re-taught 100× saturates). Monotonic in `reinforcement_count`, never negative. Ship the reinforce weight small; the doctrine's tier-threshold hysteresis prevents oscillation.

### 4. Validator (tropo-validate.py)
`reinforcement_count` ∈ non-negative integers; it joins the curator-mutable-field discipline check (non-curator write → same finding class as score/tier); `reinforced_by` entries are well-formed generation labels. Weight-sum invariant (the five weights sum to 1.0) asserted in the paired test.

### 5. Seeding existing hand-merged pins (optional, evidence-backed)
A documented one-time curator-assisted backfill: for an existing entry whose body/history records N generations independently re-deriving it, the curator may set `reinforcement_count` from that evidence (ratified, never fabricated). Argus #1 (~10 recurrences) is the worked example. Optional; not required for the feature to ship.

## Design decisions (open questions from the brief, resolved by the architect)
- **Similarity aggressiveness:** keep human-ratified MERGE as the sole increment gate — do NOT add an auto-similarity heuristic that auto-merges. Mike (2026-07-20) is unworried about runaways; ratification + log-compression are sufficient guards, and auto-merge would introduce the exact false-signal risk. (Curator may *propose* more candidates; the human still ratifies.)
- **Score integration:** a dedicated weighted term (legible) over routing through the reserved Wilson/anti-pin path — recurrence is a positive vote, cleaner as its own term.
- **Seeding:** curator-assisted, evidence-backed, optional — not an automated historical sweep.

## Build lanes
1. Argus locks this contract + the paired test-spec (V1 pairing) — **after Mike approves the memory.capsule v1.6 lock-break** (core-subsystem scoring change).
2. Talos builds: capsule amendment + doctrine amendment + curator MERGE logic + validator check + tests.
3. Vela (or independent) runs the property/fault suite (weight-sum, monotonicity, non-curator refusal, seeding).
4. Mike signs the scoring change (it alters every agent's memory tiering).

## Explicit exclusions
No anti-pin/downvote (reserved v3.1+ per the doctrine). No auto-merge / write-time similarity. No change to reference_count semantics. No cross-Studio reinforcement aggregation (federation territory).

---

*Dev-spec | UID `47c26a60` | Argus A136 | 2026-07-22 | status: design (lock + build await Mike's memory.capsule v1.6 lock-break approval — core scoring change). Cycle brief `6dd954b9`.*
