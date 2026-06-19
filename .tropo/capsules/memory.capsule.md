---
uid: a5b3c891
name: "memory"
type: capsule-definition
extends: core
version: 1.1
tier: os
author: argus-a59
created: 2026-05-12
modified: 2026-06-09
modified_by: argus-a106
status: active
locked_by: argus-a59
locked_at: 2026-05-12
v1_1_amendment_note: "v1.0 -> v1.1 amendment 2026-06-09 by Argus A106 — Memory v3.0 cycle (dev-spec c8f1e3b4, Mike-A106 'Let''s go'). The lock-break gate was opened by Argus A96 2026-06-03 (Mike-A96-authorized, below); this applies the 7 staged amendments (A1-A7 at agents/argus/.tropo-capsule/workspace/v163-memory-capsule-v1.1-design.md). Surgical + cohesive (one concern: the memory surface + its governance). The v1.0 entry-governance core — subtypes, scope, author/curator write-split, score formula, verification-before-use — is UNCHANGED. Adds: A1 NEW §Surface Schema (the unified agent-memory.md 4-section boot-read); A2 §State Machine reconciliation (the current-tier index surface memory-current.md -> agent-memory.md §Top-of-Mind; entry tiers unchanged); A3 §Memories append-only-forever rule (short-term-memory.jsonl -> agent-memories.jsonl, folds advance a boundary, never clear — the property whose absence caused the A70->A89 18-gen lapse); A4 §Curator F5 boot-staleness gate hook (catch-up fold when ≥3 gens OR ≥50 unfolded since last_curated; Mike-A90-walked thresholds); A5 Top-of-Mind priority-ordering rule (prototype finding P-1); A6 Living-Transfer aging rule (prototype finding P-2 — every from-predecessor section needs an aging rule); A7 surface-body curator-write exception (entry-body stays author-only; surface §Top-of-Mind is curator-authored by design). Design authority: spec d0624a04 v3.1. Prototype-validated against Argus's 91-gen memory. status stays active during the cycle; re-lock at cycle close. ships_in_v += v1.67.0."
lock_break_note: 'Lock-break by Argus A96 2026-06-03, explicitly authorized by Mike-A96 this session — the one Mike-approval gate the v1.67 Memory v3.0 dev-spec (c8f1e3b4) names. status:locked->active reopens the capsule for the v1.0->v1.1 amendment that the v1.67 cycle builds (7 surgical amendments A1-A7, staged at agents/argus/.tropo-capsule/workspace/v163-memory-capsule-v1.1-design.md; 5 gauntlet rounds required). Capsule CONTENT remains v1.0 until the cycle amends it; this gesture only opens the gate. Supersedes A95''s premature lock-break (which A95 reverted for lacking principal approval); this one carries it. Memory v3.0 slot reconciled to v1.67.'
schema_version: 2
governed_by: 222873b9
aligned_with:
  - "802ee860"   # v1.26.0 design brief (memory subsystem v3)
  - "5c0d3e1a"   # ADR-020 — Curator Protocol
  - "6d1e4f2b"   # ADR-021 — Historian Protocol
  - "d0624a04"   # Vault Memory System Spec v2 (predecessor)
pattern_exemplar: 7c47429a   # note.capsule — memory is patterned on note (light governance, frequent capture) plus curator-mutable lifecycle fields
member_of:
  - "99ed55fd"   # tropo-agents (Memory is part of agent lifecycle)
ships_in_v: [v1.26.0, v1.67.0]
tags: [capsule-definition, memory, v3, v3.0-single-surface, append-only-memories, f5-boot-gate, sa-memory-curator, curator-mutable-lifecycle, mike-A59-walked, mike-a106-memory-v3]
---

# memory — Capsule Definition

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [v1.26.0 design brief (802ee860)](../../vault/files/802ee860.md) |
| Aligned with | [ADR-020 — Curator Protocol (5c0d3e1a)](../../vault/files/5c0d3e1a.md) |
| Aligned with | [ADR-021 — Historian Protocol (6d1e4f2b)](../../vault/files/6d1e4f2b.md) |
| Pattern exemplar | [note.capsule (7c47429a)](note.capsule.md) |
| Extends | `core` |

*A memory entry — a discrete unit of preserved context (insight, learning, observation, pin, reference) carried across sessions. Memory entries compose the v3 memory substrate: written by agents during work, scored and groomed by sa.memory-curator, retrieved at runtime via grep + frontmatter sort.*

---

## Intent

Capture preserved context as governed substrate. Memory entries replace the v2 pattern (compacted memory-current.md as one large file with mixed-tier content) with discrete UID-addressable entries that:

- Carry their own provenance, classification, and lifecycle metadata
- Get scored by sa.memory-curator at index time so retrieval is sorted automatically
- Move through structural tiers (current → topic → archival) under curator discipline
- Stay grep-able + markdown-native (Tropo's L1 thesis preserved)

Each memory is a small atomic file at `agents/<name>/.tropo-capsule/memory/entries/<uid>.md` (per-agent) or `.tropo-studio/memory/entries/<uid>.md` (vault-level). The boot-read **surface** over these entries is `agent-memory.md` (v1.1; see §Surface Schema below) — a curated index pointing at the high-score entries, not the entries themselves. *(v1.0 named this surface `memory-current.md`; v3.0 unifies it into the single-file `agent-memory.md` with a fixed four-section schema.)*

**Use a memory entry when:**
- Capturing a corrective discipline pin from principal feedback ("Mike said don't propose retirement")
- Recording a learning that should outlive this session ("Wilson lower bound prevents small-sample inflation")
- Pinning a reference to canonical substrate ("L1 canonical entry is eca73d77")
- Logging an episodic moment with significance ("A58 retired 2026-05-12 after triple-ship + Mike-pin on federation correction")
- Procedural knowledge that future generations need ("When walking a Q, lead with lean + plain prose + ask once")

**Do NOT use a memory entry for:**
- Quick session-only scratch — that's `agents/<name>/.tropo-capsule/memory/agent-memories.jsonl` (the episodic log), not a memory entry
- Substantive standalone artifacts — use `document` or `note` (memory entries are pin-class, not document-class)
- Work to do — use `task`
- Binding architectural commitments — use `decision`

---

## Surface Schema — `agent-memory.md` (v1.1; the single boot-read)

**v3.0 introduces one boot-read surface.** A successor reads ONE file — `agents/<name>/.tropo-capsule/memory/agent-memory.md` — not three (the v2 `memory-current.md` + a separate `transfers/living-transfer.md` + a boot-time jsonl read). This surface is distinct from the *entry* schema below: entries are the atomic memory units; the surface is the curated boot index over them.

**Fixed four-section schema** (per spec [d0624a04](../../vault/files/d0624a04.md) v3.1 §3):

```
agent-memory.md
  frontmatter: agent / generation / last_curated / curated_by / spec_version: 3.0
  §Top-of-Mind                       — curated binding doctrine, 5–15 entries, priority-ordered (A5)
  §Living-Transfer-from-Predecessor  — predecessor handoff, authored as a section (no separate file), aged per A6
  §History                           — pointer to history/ (frozen per-gen snapshots; NEVER read at boot)
  §Memories                          — pointer to agent-memories.jsonl (append-only; NEVER read at boot)
```

**Boot contract:** the successor reads this one surface. §History and §Memories are *pointers*, not inline content — they exist for explicit on-need retrieval, never loaded at boot. (Validated against Argus's real 91-generation memory: ~24KB across 3 files → ~6KB curated surface + 2 pointers.)

**A5 — Top-of-Mind priority-ordering (REQUIRED).** §Top-of-Mind entries are **priority-ordered: binding doctrine / P0 feedback first**, then by descending curator score. The curator orders it at fold; ordering is not left to the reader's judgment (without this rule, ordering drifts across curators and Studios).

**A6 — Living-Transfer aging (REQUIRED).** §Living-Transfer-from-Predecessor is a snapshot that goes stale within a generation. At each retirement the curator **folds the prior Living-Transfer into §Top-of-Mind (or drops it)** — so generation N+2 never reads generation N's transfer as current. *(General pattern: every "from-predecessor" section needs an explicit aging rule, or it accretes and poisons future boots — the same drift class as status-card accretion. Candidate for `core.capsule` elevation.)*

**Surface authorship (A7 — curator-write exception).** The §Top-of-Mind and §Living-Transfer **bodies are curator-authored at fold** — the curator's legitimate lane, and the one place the curator writes a *body*. This is distinct from *entry* bodies, which stay author-only (§Governance Contract). `last_curated` / `curated_by` are curator-mutable frontmatter. The validation enforcement (entry-body curator-write → ERROR) must NOT fire on the curator's surface writes.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `subtype` | enum | One of: `semantic` / `episodic` / `procedural` / `reference` / `feedback`. See §Subtypes below. |
| `scope` | enum | One of: `agent` / `vault` / `project`. See §Scope below. |
| `context` | string | One-line situating context. ≤ 120 chars. The "what we were doing when this surfaced" — per Anthropic Sept 2024 contextual retrieval pattern (49% retrieval-quality improvement; pure prompting pattern, no infra). |

**Required core fields (inherited from `core.capsule`):** `uid`, `type` (= `"memory"`), `created`, `modified`, `state` (= `active` at capture). See [core.capsule (ee814120)](core.capsule.md) for full core inheritance.

**Body:** markdown content. Author-mutable. Curator never mutates body (see §Governance Contract).

---

## Optional Frontmatter

| Field | Type | Set by | Purpose |
|-------|------|--------|---------|
| `pinned_by` | array of UIDs | author | **v1.26.0.1 amendment (per Stream 8 sa.skeptic P1-2):** array-form. Resolvable UIDs required if set; empty array `[]` or absent means no explicit pin. Wilson lower bound boost applied per pin. Multi-source pin signal (e.g., `[mike-maziarz, argus-a59]`) handled by Wilson math at n=multi naturally; v3.1 anti-pin extension composes cleanly. Initial v1.26.0 spec declared single UID; corrected at v1.26.0.1 bundled remediation. |
| `last_referenced` | date | curator | Last time this entry was referenced (grep hit acted on, cross-referenced in another memory, cited in vault entry or channel). Curator updates per scoring pass. |
| `reference_count` | integer | curator | Implicit-vote tally. Curator increments per scoring pass based on usage since prior pass. Default 0. |
| `score` | float | curator | Composite score in [0, 1] range. Curator-written; agents read for sort order during retrieval. See §Score Formula in Stream 3 doctrine. |
| `tier` | enum | curator | One of: `current` / `topic` / `archival`. Curator-managed; transitions follow §State Machine below. |
| `tags` | array of strings | author | Freeform lowercase-hyphenated tags. Discovery axis; not policed. |
| `refs` | array of UIDs | author | Related vault entries cited in this memory's body. Used by curator for stale-detection (each ref resolved at boot per §Verification-Before-Use). |
| `composes_into` | array of UIDs | author | Downstream artifacts derived from this memory (e.g., a doctrine document that was born from this pin). Provenance. |
| `superseded_by` | UID | author or curator | If a later memory updates or replaces this one, the newer UID. Curator can mark via recommendations. |

Any additional fields are legal as frontmatter extras per core rules. The memory capsule does not police extras.

---

## Subtypes

Five subtypes carry the CoALA taxonomy (Sumers et al., 2023, arXiv 2309.02427) plus Tropo-specific extensions:

- **`semantic`** — facts, knowledge, definitions. *"Mike uses Opus 4.7 on Claude Code"* / *"Wilson lower bound prevents small-sample inflation in voting"* / *"Tropo's L1 thesis is filesystem + LLM + markdown."* Scoring discipline: longer half-life; semantic memory decays slowly because facts persist.
- **`episodic`** — events with temporal binding. *"A58 retired 2026-05-12 after triple-ship + Mike-pin on federation correction"* / *"Cosmo M1 boot 2026-04-26 established the lane-union rule."* Scoring discipline: faster decay; episodic memory matters most fresh, then becomes lineage record.
- **`procedural`** — skills, how-to, reflexes. *"When walking a Q, lead with lean + plain prose + ask once"* / *"Pin in argus-vela channel as TAG with one-line summary."* Scoring discipline: very slow decay if referenced; procedural memory drives behavior across generations.
- **`reference`** — pointer to canonical substrate. *"L1 canonical entry is at vault/files/eca73d77.md"* / *"agent-activation.playbook v2.9 is the current canonical."* Scoring discipline: stale-detection critical (citation must resolve); demoted aggressively if reference becomes broken.
- **`feedback`** — corrective discipline pins from principal feedback. *"Don't propose retirement — Mike calls it directly"* / *"Lead with lean on questions."* Scoring discipline: slow decay; feedback memory is high-importance until explicitly superseded.

The subtype shapes curator behavior: scoring weight, decay rate, stale-detection sensitivity all differ by subtype.

---

## Scope

Three scopes determine where the memory lives + who reads it:

- **`agent`** — per-agent memory. Lives at `agents/<owner-slug>/.tropo-capsule/memory/entries/<uid>.md`. Read by that agent at boot; not read by others by default (cross-agent grep works but is discretionary).
- **`vault`** — vault-level crew-class memory. Lives at `.tropo-studio/memory/entries/<uid>.md`. Read by every executive at boot per Tier 2 boot protocol.
- **`project`** — project-scoped memory. Lives at `<project-root>/memory/entries/<uid>.md` if the project has a memory folder. Used for memories that belong to a specific project rather than an agent or the crew.

Scope is set at author time + immutable. A memory authored at `agent` scope stays agent-scoped; if it later proves crew-class, the curator can recommend a copy-up to vault scope (via the `composes_into:` field provenance).

---

## State Machine

Memory entries move through structural tiers via curator-mediated transitions:

```
(append-to-jsonl) ──curator-fold──> current ──curator-demote──> topic ──curator-demote──> archival ──curator-demote──> demoted (terminal)
                                       ↑                          │
                                       └──curator-promote────────┘
```

- **`current`** — promoted; lives in `agents/<name>/.tropo-capsule/memory/entries/<uid>.md`; indexed in `agent-memory.md` §Top-of-Mind (the always-loaded boot surface; v1.0 named this index `memory-current.md`). High-score entries stay here.
- **`topic`** — demoted from current but still active substrate. Lives in entries/ same as current; indexed via `topics/<topic-name>.md` (lazy-loaded by agents on grep/glob). Score below current threshold but above archival threshold.
- **`archival`** — long-term storage. Moved to `history/` subdirectory. Not loaded at boot; agents read at need via explicit grep.
- **`demoted`** — terminal. Score collapsed to ~0. Substrate-eligible for cleanup. Curator can recommend deletion; deletion requires principal ratification.

Transitions:
- `jsonl → current` — curator's normal fold pass (reads `agent-memories.jsonl` since the last boundary). Most entries land here unless flagged as noise during fold.
- `current ↔ topic` — score-driven; curator may promote topic entries back to current if reference count spikes.
- `topic → archival` — score crosses lower threshold; reference_count plateaus without growth.
- `archival → demoted` — only via explicit curator recommendation + principal ratification.
- `demoted` — terminal; entry stays at rest until cleanup cycle.

---

## Governance Contract

The capsule enforces a clear **author vs curator write boundary** that mirrors the Slack/Notion convergent "suggest, don't write" pattern:

**Author-mutable fields** (any agent, including the memory's original author):
- `uid` (set at creation; never mutated)
- `type` (always `memory`)
- `subtype`, `scope`, `context`, `body` — content fields
- `created` (set at creation; never mutated)
- `modified` (updated whenever body changes)
- `pinned_by` — explicit pin (any agent can pin; principal pin gets Wilson boost)
- `tags`, `refs`, `composes_into`, `superseded_by` — provenance fields

**Curator-mutable fields** (sa.memory-curator only):
- `last_referenced` — updated per scoring pass
- `reference_count` — incremented per usage since prior pass
- `score` — recomputed each pass
- `tier` — transitioned per state machine

**Why the split:** content lives with the author; lifecycle lives with the curator. An agent writing a memory entry sets what it MEANS; the curator decides where it goes and how it ranks. No agent should ever silently mutate scoring/tier (that's the curator's job + ratification flow). No curator should ever silently mutate an **entry** body (that's the author's content). **A7 exception:** the `agent-memory.md` **surface** bodies (§Top-of-Mind, §Living-Transfer) ARE curator-authored at fold — the curator's defined lane, distinct from entry bodies; this is not a violation (see §Surface Schema).

**Validation enforcement:** at substrate validation time, any change to curator-mutable fields by a non-curator agent should surface as a WARN (v1.26.0 ships at WARN; ERROR ratchet may follow in a later cycle once discipline is proven). The reverse — curator changing an author-mutable **entry** body — should ERROR immediately. **The `agent-memory.md` surface bodies are exempt (A7):** curator authorship of §Top-of-Mind / §Living-Transfer at fold is legitimate, never flagged.

**A4 — Curator fold cadence: retirement-canonical + the F5 boot-staleness gate (v1.1).** The curator's **retirement fold is canonical** (reads `agent-memories.jsonl` since the last boundary → §Top-of-Mind, archives a frozen `history/` snapshot, advances the boundary). The **F5 boot-staleness gate** is the safety net: at boot (agent-activation.playbook Step 2.5) the agent checks unfolded state since `last_curated` and fires a **catch-up fold when EITHER ≥3 generations OR ≥50 unfolded memories** (Mike-A90-walked thresholds; OR-logic so slow-drift and fast-volume each trip independently). The gate reads the append-only log's entry-count-since-boundary (A3 gives it a clean signal). This makes the silent-lapse failure *mechanically impossible* — the same posture as v1.62's completion gate (don't trust the discipline; let the substrate catch the lapse). The capsule declares the contract; `sa.memory-curator` (fold logic), `agent-activation.playbook` Step 2.5 (the gate), and `agent-retire.playbook` (the canonical fold) implement it.

---

## Verification-Before-Use

Per v1.26.0 Q7 lock, the curator runs an explicit citation-resolution walk at boot:

For each memory entry with `refs:` populated:
- Resolve each cited UID via `vault/00-index.jsonl`
- Verify file existence at expected path
- Check status/state fields if the cited entry has them (e.g., a cited release entry now state:archived may be fine if the memory is about that release historically; but a cited capsule that's been superseded is stale)

Findings flow into the curator's recommendation pass per Q6 lock — bounded actions are `flag-stale` (surface to executive for ratification) or `archive` (move to tier=archival if all refs broken).

**TTL emerges implicitly from the score formula** — entries with `last_referenced` distant from now + `reference_count` low + no `pinned_by` collapse to low score. Below the demote threshold, curator recommends `demote` action. Not a separate TTL mechanism.

---

## Score Formula (Stream 3 doctrine; declared here as contract)

Composite of three signals per the Reddit Hot + HN + Wilson research synthesis:

```
score(M) = w_recency · age_decay(last_referenced)
        + w_usage   · log10(max(reference_count, 1))
        + w_pin     · wilson_lower_bound(pinned_by, anti_pins=0)
        + w_subtype · subtype_weight(subtype)
```

Where:
- `age_decay(t) = 1 / (1 + (now - t) / half_life(subtype))` — recency normalized by subtype-specific half-life
- `log10(reference_count)` — Reddit Hot pattern; compresses scale so vote inflation doesn't dominate
- `wilson_lower_bound` — Reddit Best pattern; small-sample-pessimistic confidence interval on explicit pin signal
- `subtype_weight` — semantic baseline; episodic faster decay; procedural slower decay; reference high-importance if not stale; feedback high-importance until superseded

Weights `w_*` calibrated against existing memory corpus at Stream 3 execution. Initial proposal: `w_recency = 0.25`, `w_usage = 0.35`, `w_pin = 0.30`, `w_subtype = 0.10`. Sum to 1.0; score normalized to [0, 1] range.

Tier thresholds (initial proposal; calibration in Stream 3):
- `score ≥ 0.65` → tier: current
- `0.35 ≤ score < 0.65` → tier: topic
- `0.15 ≤ score < 0.35` → tier: archival
- `score < 0.15` → tier: demoted (curator recommends deletion)

---

## Lifecycle Examples

**Example 1 — Episodic memory captured during work:**

```yaml
---
uid: <8-hex>
type: memory
subtype: episodic
scope: agent
context: "Mid-walk of v1.26.0 Q3 with Mike; just locked implicit + explicit voting"
body: "Mike-A59 ratified Wilson lower bound for explicit pins after walking the small-sample inflation case. Pattern: explicit pin needs the Wilson math so newly-pinned entries don't dominate before implicit usage accumulates."
created: 2026-05-12T15:42
state: active
tags: [v1.26.0-walk, voting-mechanism, wilson-lower-bound]
---
```

Curator processes at next pass; assigns score based on freshness + future reference count + (subtype=episodic decay weight).

**Example 2 — Feedback pin from principal:**

```yaml
---
uid: <8-hex>
type: memory
subtype: feedback
scope: agent
context: "Mike-A59 walking Q5 of v1.26.0 brief; reaffirming streamlined-cycle posture"
pinned_by: mike-maziarz
body: "Keep migrations streamlined. Atomic per-agent. Don't pre-curate during migration — that's the curator's first run. Mike directive 2026-05-12."
created: 2026-05-12T15:38
state: active
---
```

`pinned_by: mike-maziarz` triggers Wilson lower bound boost at scoring. High score → tier: current.

**Example 3 — Reference memory citing canonical substrate:**

```yaml
---
uid: <8-hex>
type: memory
subtype: reference
scope: vault
context: "v1.26.0 Stream 0 substrate-repair sweep; flagging canonical-l0 set as architectural anchor"
refs:
  - "a1a003bf"   # mindbridge (canonical L0; Mike-A59 added 2026-05-12)
  - "5e9c1a82"   # agents L0
body: "Canonical L0 set lives in .tropo-studio/registries/canonical-l0-projects.yaml. Validator gates build via validate-canonical-l0.py. Changes require Mike approval per OP 11."
created: 2026-05-12T16:00
state: active
---
```

At each curator boot pass, both `refs:` UIDs verified to resolve. If `a1a003bf` ever gets removed (unlikely; it's canonical L0), curator flags via `flag-stale` recommendation.

---

## Composition with v3 Architecture

This capsule is one piece of the v1.26.0 substrate. Composes with:

- **`sa.memory-curator`** (Stream 2) — operates on memory entries per this schema
- **Score formula doctrine** (Stream 3) — declares the composite math the curator implements
- **Verification-before-use validator extension** (Stream 4) — extends `tropo-validate.py` to catch curator-mutable-field violations + citation-resolution failures
- **Playbook amendments** (Stream 5) — agent-activation/retire playbooks dispatch curator + expect this schema
- **Migration** (Stream 0) — converts v1 `feedback_*.md` files + v2 `memory-current.md` content into discrete entries matching this schema

---

## Validation Checks

The capsule defines validation rules for `tropo-validate.py` (extended in Stream 4):

1. **Required-field presence** — every `type: memory` entry MUST have `subtype`, `scope`, `context`, `body`, `created`. WARN if missing at v1.26.0; ERROR ratchet in later cycle.
2. **Enum compliance** — `subtype` must be in {semantic, episodic, procedural, reference, feedback}; `scope` must be in {agent, vault, project}; `tier` must be in {current, topic, archival, demoted}.

3. **UID resolution** — if `pinned_by` is set, MUST resolve to an entity UID in `vault/00-index.jsonl`. If `refs:` is set, EACH ref MUST resolve OR be flagged stale by curator.
4. **Score range** — if `score` is set, MUST be in [0.0, 1.0] inclusive.
5. **Context length** — `context` field ≤ 120 chars.
6. **Tier-state consistency (v1.26.0.1 amendment)** — `tier: current` + `tier: topic` MUST live at `entries/<uid>.md` per scope; `tier: archival` lives at `history/<uid>.md` per scope (per §State Machine); `tier: demoted` is terminal at `history/<uid>.md` until principal-ratified deletion. v1.26.0 initial spec had a bug claiming all non-stm tiers live at `entries/`; corrected at v1.26.0.1 bundled remediation per Stream 8 sa.skeptic P0-4.
7. **Curator-mutable field discipline** — `last_referenced`, `reference_count`, `score`, `tier` should only be modified by a writer with `modified_by:` containing "sa.memory-curator" or "argus" (overrides during substrate-repair). WARN on violation at v1.26.0.

---

## Migration Notes

Stream 0 of v1.26.0 migrates existing memory substrate to this schema:

- **v1 agents (Vela, Metis):** each `feedback_*.md` file → one memory entry with `subtype: feedback` (the bulk are feedback-class pins). `MEMORY.md` index → curator-written `memory-current.md` (now a curated index, not the content store). Existing pin commentary becomes the body; YAML frontmatter added.
- **v2 agents (Argus, Cosmo, Tropo):** sections of `memory-current.md` (pointer-based at retirement) → individual entries with curator-assigned tier. Per A52→A58 deferred fold (Stream 6), the curator dispatches once to do the historical compaction across Argus's `history/` snapshots.
- **Vault-level memory** at `.tropo-studio/memory/`: each existing `*.md` pin → memory entry with `scope: vault`.

Migration is 1:1 mapping; pre-curation deferred to curator's first run.

---

*memory.capsule v1.2 | UID a5b3c891 | Authored 2026-05-12 | Amended 2026-06-14 by Talos T20 per Metis-G80 (00003705) | Ships in v1.26.0*
*"Append memories to the log. The curator filters the signal. Author writes meaning; curator writes lifecycle."*
