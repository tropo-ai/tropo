---
uid: 5f2c1b94
type: document
subtype: doctrine
title: Memory Score Formula — Doctrine for sa.memory-curator
description: The composite score formula for v3 memory entries. Read by sa.memory-curator at boot; declares the math the curator implements. Five signals (recency + usage + pin + reinforcement + subtype). v1.1 adds the reinforcement (recurrence) signal — log-compressed, DISTINCT from usage (reads != re-learns) — and rebalances the weights to sum 1.0. Calibrated against existing memory corpus at first execution. Earn-the-abstraction strict — initial weights chosen for legibility, refined via dogfood evidence.
status: published
state: active
version: '1.1'
author: argus-a59
created: 2026-05-12
modified: 2026-07-22
created_by: argus-a59
modified_by: talos-t35
schema_version: 2
extraction_scope: ship
governed_by: 8dd772a0
aligned_with:
  - a5b3c891
  - 50c0bdce
  - 802ee860
ships_in_v:
  - v1.26.0
  - v1.90.0
tags:
  - doctrine
  - memory-score-formula
  - sa-memory-curator
  - reddit-hot
  - hn-decay
  - wilson-lower-bound
  - calibrated-against-corpus
  - v1.26.0
subsystem_hub:
  - 99ed55fd
---

# Memory Score Formula — Doctrine

*The composite score that sa.memory-curator writes into each memory entry's `score` frontmatter field. Read by curator at boot; calibrated by curator at first execution against existing corpus.*

---

## The Composite

For each memory entry M, the score is a weighted sum of **five signals** (v1.1 adds the reinforcement/recurrence signal):

```
score(M) = w_recency   · age_decay(M)
        + w_usage     · usage_normalized(reference_count(M))
        + w_pin       · wilson_lower_bound(pinned_by(M))
        + w_reinforce · reinforce_signal(reinforcement_count(M))
        + w_subtype   · subtype_weight(subtype(M))
```

Normalized to `[0.0, 1.0]` after summation. **v1.1 weight allocation** (rebalanced to seat the new signal; sum EXACTLY 1.0):

| Weight | Value | Rationale |
|---|---|---|
| `w_recency` | 0.20 | Recency matters but doesn't dominate; old-and-still-used pins should hold their score (trimmed from 0.25 to seat reinforce) |
| `w_usage` | 0.30 | Implicit voting (reads/citations) is a bulk signal; reference-count compressed via log so inflation doesn't dominate (trimmed from 0.35) |
| `w_pin` | 0.25 | Explicit principal/agent pins carry strong signal; Wilson lower bound prevents small-sample inflation (trimmed from 0.30) |
| `w_reinforce` | 0.15 | **NEW v1.1 (dev-spec 47c26a60).** Recurrence — how often reality independently re-taught the lesson (ratified MERGE count). Ships small (arguably the strongest importance signal, but calibrated conservatively at first pass); log-compressed so no single entry dominates |
| `w_subtype` | 0.10 | Subtype-specific weighting fine-tunes (e.g., feedback pins should persist longer than episodic logs) |

**Weight-sum invariant:** `0.20 + 0.30 + 0.25 + 0.15 + 0.10 = 1.00` exactly. This invariant is asserted in the paired test (`test_memory_reinforcement.py`); the curator implements the same five weights.

Weights calibrated against corpus at first curator dispatch (calibrate-at-first-pass; same procedure §Calibration Procedure already prescribes). The reinforce weight ships small and the tier-threshold hysteresis (§Tier Thresholds) prevents oscillation when the new signal lands, per the dev-spec's weight-rebalance risk mitigation.

---

## Signal 1 — Recency (HN-adapted age decay)

Reference: Hacker News uses `score = (P-1) / (T+2)^G` where G ≈ 1.8 — time decays super-linearly, votes sub-linearly. We adapt to a normalized [0, 1] form:

```
age_decay(M) = 1 / (1 + (now - last_referenced(M)) / half_life(subtype(M)))
```

Result is 1.0 if just-referenced; 0.5 at one half-life; approaches 0 as time grows. Half-life varies by subtype:

| subtype | half_life (days) | Rationale |
|---|---|---|
| `semantic` | 90 | Facts persist; slow decay |
| `episodic` | 30 | Events matter most fresh, then become lineage |
| `procedural` | 120 | Skills/how-to persist longer than facts when referenced |
| `reference` | 60 | Citations stay relevant as long as cited target is canonical |
| `feedback` | 180 | Corrective discipline pins are slow-decay — they carry across generations |

**Use `last_referenced` not `created`.** A 6-month-old feedback pin that was referenced last week is still fresh. A new pin nobody references is already decaying. The half-life is the heuristic the curator uses to interpret decay — but the substrate carries the raw timestamp, not the decayed value.

---

## Signal 2 — Usage (Reddit Hot-style log compression)

Reference: Reddit's hot algorithm uses `log10(max(|U-D|, 1))` for vote weight — first 10 votes count as much as the next 100. We apply the same compression to memory reference counts:

```
usage_signal(M) = log10(max(reference_count(M), 1))
```

Then normalize to [0, 1] via:

```
usage_normalized(M) = min(usage_signal(M) / log10(reference_count_cap), 1.0)
```

Where `reference_count_cap` is the corpus-wide max (e.g., 1000) — entries with reference_count ≥ cap saturate at 1.0. Initial proposal: cap at 1000 (a memory referenced 1000 times is at saturation; this is far above any realistic count for the current corpus).

**Why log compression matters:** without it, a memory referenced 100 times would outrank one referenced 50 times by 2x in scoring. With log compression, the gap is `log(100)/log(50) ≈ 1.18`. The ranking respects relative volume without letting heavy-hitters dominate.

---

## Signal 3 — Explicit pin (Wilson lower bound)

Reference: Reddit's "Best" comment ranking uses the Wilson lower bound of a binomial confidence interval on upvote ratio. Adapted for pin signal:

For each entry M:
- `pin_count(M)` = 1 if `pinned_by` is set, else 0
- `anti_pin_count(M)` = 0 (we don't currently support anti-pins; reserved for v3.1+)
- `total_pins(M)` = `pin_count + anti_pin_count`

Wilson lower bound formula (95% confidence; z = 1.96):

```
def wilson_lower_bound(pin_count, anti_pin_count, z=1.96):
    n = pin_count + anti_pin_count
    if n == 0:
        return 0.0
    p = pin_count / n
    z_sq = z * z
    return ((p + z_sq / (2 * n)) - z * sqrt(p * (1 - p) / n + z_sq / (4 * n * n))) / (1 + z_sq / n)
```

**Why Wilson and not just "set boost to 1.0 when pinned":** Wilson penalizes small-sample-but-confident judgments. A memory with `pin_count=1, anti_pin_count=0` doesn't immediately dominate — its Wilson lower bound is ~0.21 (95% confidence the true ratio is at least 0.21 given 1 vote). A heavily-pinned memory (`pin_count=10, anti_pin_count=0`) has Wilson ~0.72. A unanimous-but-larger sample wins legitimately.

This handles Mike's framing from Q3: explicit pins matter but newly-pinned memories shouldn't immediately dominate before implicit usage accumulates.

**v3.1+ extension:** introduce `anti_pin_count` semantics (e.g., agent explicitly flags "this memory is misleading"). Wilson then becomes a real upvote/downvote ratio. v1.26.0 ships with anti_pin=0 always.

---

## Signal 4 — Reinforcement (recurrence; DISTINCT from usage) — NEW v1.1

Reference: dev-spec 47c26a60 (Mike-originated, 2026-07-20). **Recurrence is a distinct, first-class importance signal**: how many times reality *independently re-taught* the agent the same lesson — captured as `reinforcement_count`, incremented on each human-ratified `MERGE` consolidation into the entry (see `sa.memory-curator` Phase 6/7). Log-compressed exactly like usage, normalized by a declared cap:

```
reinforce_signal(M) = min( log10(max(reinforcement_count(M), 1)) / log10(reinforce_cap), 1.0 )
```

Where `reinforce_cap = 100` (initial; a lesson re-taught 100× saturates the signal at 1.0). The signal is **monotonic** in `reinforcement_count` (more recurrences never lowers the score) and **never negative** (`reinforcement_count = 0` → `log10(1)/log10(100) = 0`, zero contribution).

**Reinforcement is DISTINCT from usage — reads are not re-learns.** This is the load-bearing rule of v1.1 and it is stated explicitly so it is never conflated in code or doctrine:

- **`reference_count` (usage, Signal 2)** = how often an entry is *looked up / cited*. "We refer to this a lot." May just be a handy reference fact.
- **`reinforcement_count` (reinforcement, Signal 4)** = how often the agent *independently re-derived the same lesson from fresh experience* and a curator ratified the consolidation. "Reality taught us this N separate times." Arguably the loudest "this is load-bearing" signal.

They are **separate fields, separate signals, separate weighted terms** — never summed into one counter, never used as a proxy for each other. A memory looked up 200 times but never re-derived has high usage / zero reinforcement; Argus's #1 pin (ten generations A115–A135 each independently re-learning the same lesson, hand-merged into one entry) is the inverse — the recurrence that was invisible to the v1.0 score is exactly what Signal 4 makes first-class.

**Why cap at 100 and log-compress:** the same Reddit-Hot rationale as usage — the first handful of recurrences count for most of the signal; a runaway consolidation cannot let one entry dominate the corpus. Combined with the human-ratified-MERGE gate (every `+1` is a confirmed thumbs-up, no auto-increment), the signal cannot inflate by construction (dev-spec §Design "NO RUNAWAY BY CONSTRUCTION").

**Calibrate at first pass:** `w_reinforce = 0.15` and `reinforce_cap = 100` are initial values, calibrated against the live corpus at the first curator dispatch per §Calibration Procedure — shipped small so the weight rebalance does not destabilize existing tiers (the tier-threshold hysteresis in §Tier Thresholds absorbs the shift).

---

## Signal 5 — Subtype weight

A small constant per subtype that fine-tunes the score for class-specific behavior:

| subtype | subtype_weight | Rationale |
|---|---|---|
| `semantic` | 0.70 | Baseline; facts matter but compete with other classes |
| `episodic` | 0.50 | Lower weight; episodic memory has shorter useful life by nature |
| `procedural` | 0.85 | Higher weight; procedural memory drives ongoing behavior |
| `reference` | 0.80 | High weight; references resolve to canonical substrate |
| `feedback` | 0.90 | Highest weight; corrective discipline pins carry forward |

These are starting values; calibrated against existing corpus at first dispatch.

---

## Tier Thresholds (v1.26.0.1 calibration)

The curator uses score thresholds to recommend tier transitions:

| Tier | Score range | Curator action |
|---|---|---|
| `current` | score ≥ 0.55 | Stay in or promote-to current; indexed in memory-current.md |
| `topic` | 0.30 ≤ score < 0.55 | Stay in or demote-to topic; indexed via topics/ files (lazy-loaded) |
| `archival` | 0.10 ≤ score < 0.30 | Demote-to archival; moved to history/; read on need only |
| `demoted` | score < 0.10 | Recommend deletion (principal-ratification required) |

**v1.26.0.1 amendment (per Stream 8 sa.skeptic P1-5):** initial thresholds were 0.65/0.35/0.15/below-0.15 — but the worked example (a heavily-referenced feedback memory with Mike-pin and recent reference) scored 0.594, which fell into `tier: topic` instead of `tier: current` as the design intended. The signal sum range is approximately [0, 0.85] in practice (no entry achieves all four signals at max simultaneously), so thresholds calibrated against a theoretical [0, 1] range mis-place high-quality memories. v1.26.0.1 thresholds shift the current/topic boundary to 0.55 (matches worked example), topic/archival to 0.30, archival/demoted to 0.10. The worked example below recomputes correctly to `tier: current` under the new thresholds.

**Promotion has stricter discipline than demotion.** A topic entry needs score ≥ 0.55 to promote. A current entry needs score < 0.55 to demote. This hysteresis prevents oscillation — entries don't bounce between tiers when their score fluctuates around a threshold.

**Future calibration:** curator's first dispatch dry-runs scoring against existing corpus; if distribution clusters near 0.55 threshold (entries oscillating in/out of current), recalibration is a v3.x amendment opportunity.

---

## Calibration Procedure

At first curator dispatch (Stream 6 fold for Argus A52-A58), the curator:

1. Computes initial scores for all corpus entries using the weights above
2. Reports score distribution (histogram + tier proposed counts)
3. If distribution looks healthy (most entries land in current+topic; clear separation; no ties at threshold), proceed
4. If distribution is bunched (everything scores 0.5-0.7; no clear tier boundaries) → tune `w_*` and re-compute
5. Surface calibration findings + final weights to principal for ratification

**Calibration is one-time.** Subsequent dispatches use the locked weights. Re-calibration only at major substrate changes (e.g., subtype semantics shift; new subtype added).

---

## Worked Example

Consider a memory entry written 2026-04-15:
- `subtype: feedback` (corrective pin from Mike)
- `created: 2026-04-15`
- `last_referenced: 2026-05-10` (referenced ~recently)
- `reference_count: 47` (heavily implicit-voted across sessions)
- `pinned_by: mike-maziarz` (explicit principal pin)
- `reinforcement_count: 0` (never yet re-derived / consolidated)

Today is 2026-05-12. Score computation under the **v1.1 five-weight** formula:

```
Signal 1 — Recency:
  half_life(feedback) = 180 days
  days_since_last_ref = (2026-05-12 - 2026-05-10) = 2 days
  age_decay = 1 / (1 + 2/180) = 0.989

Signal 2 — Usage:
  reference_count = 47
  usage_signal = log10(47) = 1.672
  usage_normalized = min(1.672 / log10(1000), 1.0) = min(1.672 / 3.0, 1.0) = 0.557

Signal 3 — Wilson:
  pin_count = 1, anti_pin_count = 0
  wilson_lower_bound = 0.207 (95% CI lower bound with n=1)

Signal 4 — Reinforcement:
  reinforcement_count = 0
  reinforce_signal = min(log10(max(0,1)) / log10(100), 1.0) = min(0/2, 1.0) = 0.000

Signal 5 — Subtype weight:
  subtype_weight(feedback) = 0.90

Composite (v1.1 weights 0.20/0.30/0.25/0.15/0.10):
  score = 0.20·0.989 + 0.30·0.557 + 0.25·0.207 + 0.15·0.000 + 0.10·0.90
        = 0.198 + 0.167 + 0.052 + 0.000 + 0.090
        = 0.507

Tier (v1.26.0.1 thresholds): 0.30 ≤ 0.507 < 0.55 → topic
```

**Now reinforce it.** Suppose the curator ratifies MERGEs consolidating ten later generations that each independently re-derived this same lesson, so `reinforcement_count = 10` (all other signals unchanged):

```
Signal 4 — Reinforcement:
  reinforcement_count = 10
  reinforce_signal = min(log10(10) / log10(100), 1.0) = min(1.0/2.0, 1.0) = 0.500

Composite:
  score = 0.20·0.989 + 0.30·0.557 + 0.25·0.207 + 0.15·0.500 + 0.10·0.90
        = 0.198 + 0.167 + 0.052 + 0.075 + 0.090
        = 0.582

Tier: 0.582 ≥ 0.55 → current
```

**Recurrence floats the entry from `topic` to `current`** — the exact product sentence v1.1 makes mechanically true: *a memory reality independently re-taught N times outranks one merely looked up often.* The signal is monotonic (`reinforcement_count` 0 → 10 raised the score, never lowered it) and saturates gracefully (`reinforcement_count = 100` → `reinforce_signal = 1.0`, score ≈ 0.657).

Note: the base example's drop from v1.0's `current` (0.594) to v1.1's `topic` (0.507) is the weight-rebalance effect the dev-spec flags — the reinforce weight is drawn from the four prior terms, so an entry with zero recurrence sits slightly lower until reality re-teaches it. This is calibrated-at-first-pass and the tier-threshold hysteresis prevents oscillation; the reinforce weight ships small (0.15) precisely to bound this shift.

Note also: the Wilson contribution is modest because n=1 (single explicit pin). v1.26.0 ships with principal-pin-only Wilson; v3.1+ may extend to multi-agent pin aggregation.

---

## Edge Cases

**Zero-reference entries:**
- An entry never referenced (reference_count=0) gets `log10(max(0, 1)) = log10(1) = 0` for usage signal — zero contribution.
- New STM entries fold to tier=current at default score (around 0.5 from subtype + recency contributions); curator's first pass after folding will adjust.

**Pinned-but-never-referenced entries:**
- A new principal-pin gets Wilson ~0.21 (small-sample-pessimistic). Combined with recent `last_referenced` (recency = ~1.0) + zero usage + subtype, score lands around 0.4-0.5 — `topic` initially.
- As implicit usage accumulates over sessions, the entry climbs to current. The Wilson math prevents premature dominance; the usage signal catches up over time.

**Saturated entries (reference_count ≫ corpus-wide max):**
- Cap at 1.0 via the saturation logic.
- These entries always score near top regardless of decay; eventual demote requires substrate change (subtype reclassification or supersedure).

**Reinforcement edge cases (v1.1):**
- `reinforcement_count = 0` (default; never re-derived) → `reinforce_signal = log10(max(0,1))/log10(100) = log10(1)/2 = 0` — zero contribution, exactly like a zero-usage entry.
- `reinforcement_count = 1` (first consolidation) → `reinforce_signal = log10(1)/log10(100) = 0` still zero (a single occurrence is not yet a recurrence); the signal begins to register at `reinforcement_count ≥ 2` (`log10(2)/2 ≈ 0.150`). This is the intended log-compression floor: one datapoint is not a pattern.
- `reinforcement_count ≥ reinforce_cap` (≥ 100) → `reinforce_signal` saturates at `1.0` (log-compression cap; a runaway consolidation cannot let one entry dominate the corpus).
- Monotonic non-negativity holds across the whole domain — increasing `reinforcement_count` never decreases `reinforce_signal`, and it is never negative. Asserted in `test_memory_reinforcement.py`.

**Mismatched generation references:**
- A memory entry's `refs:` may cite UIDs that no longer exist (e.g., old release entries archived to retired state, deleted projects).
- Stale-detection (curator Phase 4) catches these. The memory itself stays — the curator just flags for `FLAG-STALE` recommendation. Principal/executive decides whether the entry is now wrong (archive) or just outdated-but-still-useful (keep).

---

## v3.1+ Future Considerations

Items the doctrine notes but defers to later cycles:

- **Anti-pin support** — currently `anti_pin_count = 0` always. Could surface a `disagree-with-this-pin` mechanism for cross-agent corrections.
- **Multi-agent pin aggregation** — `pinned_by` as array vs single UID; tracks all agents that pinned the memory.
- **Cross-Studio reference counting** — federation foundation territory (deferred to v2.x+).
- **Score audit trail** — frontmatter could carry `score_history:` (list of past scores); for now reduce-substrate by writing only current.
- **Adaptive thresholds** — instead of fixed 0.65/0.35/0.15, learn thresholds from corpus distribution. v3.1 candidate; v1.26.0 ships fixed.

---

## Composition

This doctrine is read by `sa.memory-curator` at boot (Boot Sequence step 2). The curator implements the formula in its scoring pass (Phase 2) — including (v1.1) the `reinforce_signal` term, computed from the entry's `reinforcement_count`. The validator (`tropo-validate.py`) checks: `score` field is in [0.0, 1.0] range; `tier` matches the score's threshold range; and (v1.6 capsule / v1.1 doctrine) `reinforcement_count` is a non-negative integer + `reinforced_by` is well-formed + both honor the curator-mutable-field discipline. Memory.capsule §Score Formula contract-mirror (v1.6) declares this doctrine as the authoritative math and carries the same five-weight allocation.

Weights `w_*` ratified by principal at calibration step before locking. Re-calibration amends this doctrine (v1.0 → v1.1 landed the reinforcement signal; future cycles continue the pattern).

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.1 | 2026-07-22 | **Reinforcement (recurrence) signal — dev-spec 47c26a60 (activation b233b7ac), Mike-endorsed.** Added Signal 4 `reinforce_signal = min(log10(max(reinforcement_count,1))/log10(reinforce_cap), 1.0)` with `reinforce_cap = 100`; log-compressed and DISTINCT from usage (reads != re-learns — stated explicitly). Added `w_reinforce = 0.15` and rebalanced the five weights to sum EXACTLY 1.0 (recency 0.20 / usage 0.30 / pin 0.25 / reinforce 0.15 / subtype 0.10). Worked example recomputed (base topic → reinforced current). Calibrate-at-first-pass; reinforce weight ships small; tier hysteresis absorbs the rebalance. | talos-t35 |
| 1.0 | 2026-05-12 | Initial four-signal composite (recency + usage + pin + subtype); Reddit-Hot / HN-decay / Wilson synthesis; calibrated-at-first-pass. | argus-a59 |

---

*Score Formula Doctrine v1.1 | UID 5f2c1b94 | Argus A59 (v1.0) · talos-t35 (v1.1, dev-spec 47c26a60) | 2026-07-22 | Ships in v1.26.0 · v1.90.0*
*"Recency decays. Usage compresses logarithmically. Pins survive Wilson. Recurrence re-teaches. Subtype tunes."*
