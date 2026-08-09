---
uid: a5b3c891
name: memory
type: capsule-definition
extends: core
version: 1.7
v1_7_lock_break: "MIKE-AUTHORIZED 2026-08-04, verbatim 'I authorize'. Records the handoff's canonical home as agents/<slug>/transfers/<GEN>.md per the lifecycle cutover Mike approved the same day, and restates §Living-Transfer-from-Predecessor as a deliberate MIRROR rather than the home. Adds A6b; scopes A6 aging to the mirror only. No field added or removed, no required-section change, no validation rule change — every existing surface stays valid, and the mirror is still written by tropo-retire.py in the same gesture. WHY IT MATTERED: this capsule defined the letter as 'authored as a section (no separate file)', which is what the cutover changed, and a capsule is where an agent goes for design intent. The do-not-clean-up-the-mirror warning is IN the capsule deliberately: a tidy-minded successor deleting the double-write causes exactly the data loss the move prevents. Found by Metis G101's changed-mechanism sweep; surfaced and NOT edited until authorized, because status: locked (locked_by mike-maziarz 2026-07-22)."
template_enforced_from: '2026-07-13'
template_enforced_from_note: 'ADDED 2026-07-31 per core.capsule v1.9 §Governance Rule 11 (OPTIONAL `template_enforced_from`). Value is the date THIS capsule''s §Template leg was authored, derived from the first commit introducing the ## §Template heading in this file and cross-checked against this capsule''s own changelog/amendment note. Declares the mint-time contract''s start so instances predating the scaffold are not judged against it. One-line enforcement-scope metadata; no schema/enum/state-machine/template change, so no version bump (the extraction_scope sweep precedent).'
supersedes_version: '1.5'
v1_6_amendment_note: 'v1.5 -> v1.6 amendment 2026-07-22 by talos-t35 under LOCKED memory-reinforcement dev-spec 47c26a60 (activation b233b7ac), explicitly authorized by Mike as a lock-break 2026-07-22 ("smart upgrade to memory"). Surgical + additive (one concern: a first-class recurrence signal on the memory surface). Adds two curator-mutable OPTIONAL frontmatter fields: reinforcement_count (non-negative integer, default 0 — count of human-ratified MERGE consolidations into this entry, KEPT STRICTLY SEPARATE from reference_count: reads != re-learns) + reinforced_by (list of contributing generation labels, e.g. [A115, A124, A129] — the recurrence lineage, auditable per the permanent-record principle). Both join the §Governance Contract curator-mutable set + the curator-mutable-field discipline (non-curator write -> WARN, same finding class as score/tier). NEW §Validation Check: reinforcement_count is a non-negative integer; reinforced_by entries are well-formed generation labels. The §Score Formula contract-mirror gains the reinforce term + rebalanced five-weight allocation per score-formula-doctrine v1.1 (5f2c1b94). The v1.0 entry-governance core — subtypes, scope, author/curator write-split, verification-before-use, state machine — is UNCHANGED. Mirrors the v1.1 (A106) + v1.5 (A132) Mike-authorized lock-break framing: build did not proceed on the capsule until Mike signed the lock-break, exactly as every prior memory amendment.'
v1_6_lock_status: "LOCKED — Mike authorized lock-break 2026-07-22; talos-t35 executed under dev-spec 47c26a60"
v1_6_lock_note: "Mike endorsed the memory-reinforcement upgrade + explicitly authorized the memory.capsule v1.5 -> v1.6 lock-break 2026-07-22 (dev-spec 47c26a60, activation b233b7ac). Additive: 2 curator-mutable optional fields (reinforcement_count + reinforced_by), 1 new validation check, discipline coverage, and the score-formula contract-mirror update. No schema/enum/state-machine change; v1.0 entry-governance core unchanged."
v1_5_amendment_note: 'Engine Phase-1 reconciliation authored 2026-07-15 by Argus A132 under locked dev-spec dd9d4fe6 (activation 0e826eb9), from Talos T31 finding c9421231 + A131 architectural adjudication. Makes the capsule honest to the converged v3 substrate: discrete entry content is a markdown body (never body: frontmatter); canonical scope enum is {agent, studio, doctrine}; legacy {vault, project} values are migration aliases, not authorable values; compact historical uid/subtype/score/date entries are legal history but migrate forward when they carry a live defect; episodic-log new writes use ts/generation/kind/uid/note while legacy date/type/content/expires and fold-boundary lines remain append-only history. This substantive lock-break was authored + scratch-proven by A132, then explicitly authorized by Mike on 2026-07-15 after his plain-English review; A132 applied the proven live migration and executed Mike''s re-lock gesture without self-authorizing it.'
v1_5_lock_status: "LOCKED — Mike authorized 2026-07-15; A132 executed"
v1_5_lock_note: "Mike: 'Yes, authorized.' after reviewing the simple summary: apply the proven frontmatter-only migration to 88 live memory files and re-lock memory capsule v1.5. Live proof: 224 entries preserved, 0 body changes, check_memory_typing 0 defects."
v1_4_amendment_note: 'v1.3 -> v1.4 amendment 2026-07-13 by talos-t29 per Mike-locked Governed Autonomy S2 dev-spec bba40cd7 (activation 0d9f89bc; committed substrate "Template legs for the top-10 types"). Additive + non-breaking: NEW §Template section (the mint-stamped scaffold) per the Template-Leg Contract v1.0 (b933eafb). Follows the three worked Lifecycle Examples'' demonstrated shape (body: as a frontmatter string field) since the Required Frontmatter table and Validation Check 1''s body requirement do not otherwise agree on where body content lives -- flagged, not silently resolved, in the leg''s own rules paragraph. No schema, enum, or state-machine change.'
tier: os
author: argus-a59
created: 2026-05-12
modified: 2026-07-22
modified_by: talos-t35
status: locked
locked_by: mike-maziarz
locked_at: 2026-07-22
v1_1_amendment_note: 'v1.0 -> v1.1 amendment 2026-06-09 by Argus A106 — Memory v3.0 cycle (dev-spec c8f1e3b4, Mike-A106 ''Let''''s go''). The lock-break gate was opened by Argus A96 2026-06-03 (Mike-A96-authorized, below); this applies the 7 staged amendments (A1-A7 at agents/argus/.tropo-capsule/workspace/v163-memory-capsule-v1.1-design.md). Surgical + cohesive (one concern: the memory surface + its governance). The v1.0 entry-governance core — subtypes, scope, author/curator write-split, score formula, verification-before-use — is UNCHANGED. Adds: A1 NEW §Surface Schema (the unified agent-memory.md 4-section boot-read); A2 §State Machine reconciliation (the current-tier index surface memory-current.md -> agent-memory.md §Top-of-Mind; entry tiers unchanged); A3 §Memories append-only-forever rule (short-term-memory.jsonl -> agent-memories.jsonl, folds advance a boundary, never clear — the property whose absence caused the A70->A89 18-gen lapse); A4 §Curator F5 boot-staleness gate hook (catch-up
  fold when ≥3 gens OR ≥50 unfolded since last_curated; Mike-A90-walked thresholds); A5 Top-of-Mind priority-ordering rule (prototype finding P-1); A6 Living-Transfer aging rule (prototype finding P-2 — every from-predecessor section needs an aging rule); A7 surface-body curator-write exception (entry-body stays author-only; surface §Top-of-Mind is curator-authored by design). Design authority: spec d0624a04 v3.1. Prototype-validated against Argus''s 91-gen memory. status stays active during the cycle; re-lock at cycle close. ships_in_v += v1.67.0.'
lock_break_note: Lock-break by Argus A96 2026-06-03, explicitly authorized by Mike-A96 this session — the one Mike-approval gate the v1.67 Memory v3.0 dev-spec (c8f1e3b4) names. status:locked->active reopens the capsule for the v1.0->v1.1 amendment that the v1.67 cycle builds (7 surgical amendments A1-A7, staged at agents/argus/.tropo-capsule/workspace/v163-memory-capsule-v1.1-design.md; 5 gauntlet rounds required). Capsule CONTENT remains v1.0 until the cycle amends it; this gesture only opens the gate. Supersedes A95's premature lock-break (which A95 reverted for lacking principal approval); this one carries it. Memory v3.0 slot reconciled to v1.67.
schema_version: 2
governed_by: 222873b9
aligned_with:
  - 802ee860
  - 5c0d3e1a
  - 6d1e4f2b
  - d0624a04
pattern_exemplar: 7c47429a
ships_in_v:
  - v1.26.0
  - v1.67.0
  - v1.90.0
tags:
  - capsule-definition
  - memory
  - v3
  - v3.0-single-surface
  - append-only-memories
  - f5-boot-gate
  - sa-memory-curator
  - curator-mutable-lifecycle
  - mike-A59-walked
  - mike-a106-memory-v3
subsystem_hub:
  - 99ed55fd
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

Each memory is a small atomic file at `agents/<name>/.tropo-capsule/memory/entries/<uid>.md` (per-agent), `.tropo-studio/memory/entries/<uid>.md` (studio-level), or `vault/files/<uid>.md` (doctrine). The boot-read **surface** over these entries is `agent-memory.md` (v1.1; see §Surface Schema below) — a curated index pointing at the high-score entries, not the entries themselves. *(v1.0 named this surface `memory-current.md`; v3.0 unifies it into the single-file `agent-memory.md` with a fixed four-section schema.)*

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
  §Living-Transfer-from-Predecessor  — MIRROR of the predecessor handoff, aged per A6 (v1.7: the
                                       CANONICAL home is agents/<slug>/transfers/<GEN>.md — see below)
  §History                           — pointer to history/ (frozen per-gen snapshots; NEVER read at boot)
  §Memories                          — pointer to agent-memories.jsonl (append-only; NEVER read at boot)
```

**A6b — The handoff's canonical home is a per-generation file (v1.7, 2026-08-04 lifecycle cutover).** The letter lives at `agents/<slug>/transfers/<GEN>.md` — **one file per generation, create-only, never overwritten by a later generation, kept forever.** `tropo-retire.py` writes it, and **writing the letter IS the retirement state flip.**

`§Living-Transfer-from-Predecessor` is now a **mirror**, written by the same tool in the same gesture. It is a deliberate bridge, not duplication: several agents' Tier-3 boot contracts still name the section, and the mirror retires only when the last of them moves. **Do not "clean up" the double-write** — deleting it early boots those lineages into a stale letter, which is the exact data loss the move exists to prevent.

**A6 aging applies to the MIRROR only.** The per-generation files are never aged, folded or dropped; aging exists because one section held one slot, and a per-generation file has no slot to contend for.

**Reading it:** `agents/<slug>/transfers/<predecessor-generation>.md` (G102 reads `G101.md`). **If absent, the predecessor retired pre-cutover** — read the mirror instead, and note that *finding no per-generation file is not evidence that no letter was written*.

**Boot contract:** the successor reads this surface **and the predecessor's letter** (two files since v1.7). §History and §Memories are *pointers*, not inline content — they exist for explicit on-need retrieval, never loaded at boot. (Validated against Argus's real 91-generation memory: ~24KB across 3 files → ~6KB curated surface + 2 pointers.)

**A5 — Top-of-Mind priority-ordering (REQUIRED).** §Top-of-Mind entries are **priority-ordered: binding doctrine / P0 feedback first**, then by descending curator score. The curator orders it at fold; ordering is not left to the reader's judgment (without this rule, ordering drifts across curators and Studios).

**A6 — Living-Transfer aging (REQUIRED).** §Living-Transfer-from-Predecessor is a snapshot that goes stale within a generation. At each retirement the curator **folds the prior Living-Transfer into §Top-of-Mind (or drops it)** — so generation N+2 never reads generation N's transfer as current. *(General pattern: every "from-predecessor" section needs an explicit aging rule, or it accretes and poisons future boots — the same drift class as status-card accretion. Candidate for `core.capsule` elevation.)*

**Surface authorship (A7 — curator-write exception).** The §Top-of-Mind and §Living-Transfer **bodies are curator-authored at fold** — the curator's legitimate lane, and the one place the curator writes a *body*. This is distinct from *entry* bodies, which stay author-only (§Governance Contract). `last_curated` / `curated_by` are curator-mutable frontmatter. The validation enforcement (entry-body curator-write → ERROR) must NOT fire on the curator's surface writes.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `subtype` | enum | One of: `semantic` / `episodic` / `procedural` / `reference` / `feedback`. See §Subtypes below. |
| `scope` | enum | One of: `agent` / `studio` / `doctrine`. See §Scope below. Legacy `vault`/`project` are migration aliases only. |
| `context` | string | One-line situating context. ≤ 120 chars. The "what we were doing when this surfaced" — per Anthropic Sept 2024 contextual retrieval pattern (49% retrieval-quality improvement; pure prompting pattern, no infra). |

**Required core fields (inherited from `core.capsule`):** `uid`, `type` (= `"memory"`), `created`, `modified`, `state` (= `active` at capture). See [core.capsule (ee814120)](core.capsule.md) for full core inheritance.

**Body:** markdown content after the closing frontmatter fence. Author-mutable. Curator never mutates an entry body (see §Governance Contract). `body:` is **not** a frontmatter field — v1.4's template followed stale Lifecycle Examples and is superseded by this rule.

---

## Optional Frontmatter

| Field | Type | Set by | Purpose |
|-------|------|--------|---------|
| `pinned_by` | array of UIDs | author | **v1.26.0.1 amendment (per Stream 8 sa.skeptic P1-2):** array-form. Resolvable UIDs required if set; empty array `[]` or absent means no explicit pin. Wilson lower bound boost applied per pin. Multi-source pin signal (e.g., `[mike-maziarz, argus-a59]`) handled by Wilson math at n=multi naturally; v3.1 anti-pin extension composes cleanly. Initial v1.26.0 spec declared single UID; corrected at v1.26.0.1 bundled remediation. |
| `last_referenced` | date | curator | Last time this entry was referenced (grep hit acted on, cross-referenced in another memory, cited in vault entry or channel). Curator updates per scoring pass. |
| `reference_count` | integer | curator | Implicit-vote tally. Curator increments per scoring pass based on usage since prior pass. Default 0. |
| `reinforcement_count` | integer | curator | **v1.6 amendment (dev-spec 47c26a60; Mike-authorized lock-break).** Recurrence tally — the count of human-ratified MERGE consolidations into this entry (how often reality *re-taught* the lesson). Non-negative integer, default 0. **Kept strictly separate from `reference_count`** — reads (looked-up) and re-learns (independently re-derived) are distinct signals; never conflated. Incremented on ratified MERGE only (curator-time, off the critical path). Feeds the reinforce term of the §Score Formula. |
| `reinforced_by` | array of generation labels | curator | **v1.6 amendment (dev-spec 47c26a60).** Contributing-generation lineage — e.g. `[A115, A124, A129, A135]` — appended (deduplicated) on each ratified MERGE. Makes the recurrence auditable and feeds the permanent-record principle (which generations independently re-derived this lesson). |
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
- **`studio`** — crew-class memory. Lives at `.tropo-studio/memory/entries/<uid>.md`. Read by every executive at boot per Tier 2 boot protocol.
- **`doctrine`** — OS-level, cross-Studio commitments. Lives at `vault/files/<uid>.md` and follows the governed Vault write contract.

Scope is set at author time + immutable. A memory authored at `agent` scope stays agent-scoped; if it later proves crew-class, the curator can recommend a copy-up to studio scope (via the `composes_into:` field provenance). Historical `scope: vault` maps to `studio`; historical `scope: project` maps by canonical path during the v1.5 forward migration. The aliases remain documented as data but are not valid for new writes.

### Historical compact entries (v1.5 reconciliation)

The live v3 corpus includes compact historical entries shaped as `uid` / `subtype` / `score` / `date` plus a markdown body. They are legal historical substrate, not evidence that `body:` belongs in frontmatter. When a compact entry has a live validation defect (missing scope/context, stale scope alias, non-enum subtype), `tropo-migrate-memory-schema.py` adds the canonical fields forward and records migration provenance; it never rewrites the body and never destroys the entry.

### Episodic log envelope (new writes)

`agent-memories.jsonl` is append-only forever. New memory-entry appends use:

```json
{"ts":"YYYY-MM-DD","generation":"A132","kind":"procedural","uid":"<entry-uid>","note":"<brief statement>"}
```

`kind` uses the same five subtype values. Historical `date`/`generation`/`type`/`content`/`expires` lines and `event: fold-boundary` lines remain legal and unchanged; readers normalize those aliases at read time. Migration never edits this log.

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
- `reinforcement_count` — incremented on a human-ratified MERGE only (`+= merged.reinforcement_count + 1`); the recurrence signal (v1.6 amendment, dev-spec 47c26a60)
- `reinforced_by` — contributing-generation lineage appended (deduplicated) on a ratified MERGE (v1.6 amendment)
- `score` — recomputed each pass
- `tier` — transitioned per state machine

**Why the split:** content lives with the author; lifecycle lives with the curator. An agent writing a memory entry sets what it MEANS; the curator decides where it goes and how it ranks. No agent should ever silently mutate scoring/tier (that's the curator's job + ratification flow). No curator should ever silently mutate an **entry** body (that's the author's content). **A7 exception:** the `agent-memory.md` **surface** bodies (§Top-of-Mind, §Living-Transfer) ARE curator-authored at fold — the curator's defined lane, distinct from entry bodies; this is not a violation (see §Surface Schema).

**Validation enforcement:** at substrate validation time, any change to curator-mutable fields by a non-curator agent should surface as a WARN (v1.26.0 ships at WARN; ERROR ratchet may follow in a later cycle once discipline is proven). **The v1.6 fields `reinforcement_count` + `reinforced_by` join this discipline: a non-curator write to either surfaces the same WARN finding class as `score`/`tier`** (dev-spec 47c26a60 §Design.4). The reverse — curator changing an author-mutable **entry** body — should ERROR immediately. **The `agent-memory.md` surface bodies are exempt (A7):** curator authorship of §Top-of-Mind / §Living-Transfer at fold is legitimate, never flagged.

**A4 — Curator fold cadence: retirement-canonical + the F5 boot-staleness gate (v1.1).** The curator's **retirement fold is canonical** (reads `agent-memories.jsonl` since the last boundary → §Top-of-Mind, archives a frozen `history/` snapshot, advances the boundary). The **F5 boot-staleness gate** is the safety net: at boot (agent-activation.playbook Step 2.5) the agent checks unfolded state since `last_curated` and fires a **catch-up fold when EITHER ≥3 generations OR ≥50 unfolded memories** (Mike-A90-walked thresholds; OR-logic so slow-drift and fast-volume each trip independently). The gate reads the append-only log's entry-count-since-boundary (A3 gives it a clean signal). This makes the silent-lapse failure *mechanically impossible* — the same posture as v1.62's completion gate (don't trust the discipline; let the substrate catch the lapse). The capsule declares the contract; `sa.memory-curator` (fold logic), `agent-activation.playbook` Step 2.5 (the gate), and `agent-retire.playbook` (the canonical fold) implement it.

---

## Verification-Before-Use

Per v1.26.0 Q7 lock, the curator runs an explicit citation-resolution walk at boot:

For each memory entry with `refs:` populated:
- Resolve each cited UID via the current/archive index union (`vault/00-index.jsonl` + `vault/00-archive-index.jsonl`)
- Verify file existence at expected path
- Check status/state fields if the cited entry has them (e.g., a cited release entry now state:archived may be fine if the memory is about that release historically; but a cited capsule that's been superseded is stale)

Findings flow into the curator's recommendation pass per Q6 lock — bounded actions are `flag-stale` (surface to executive for ratification) or `archive` (move to tier=archival if all refs broken).

**TTL emerges implicitly from the score formula** — entries with `last_referenced` distant from now + `reference_count` low + no `pinned_by` collapse to low score. Below the demote threshold, curator recommends `demote` action. Not a separate TTL mechanism.

---

## Score Formula (Stream 3 doctrine; declared here as contract)

Composite of **five** signals per the Reddit Hot + HN + Wilson research synthesis, extended v1.6 with the recurrence (reinforcement) signal:

```
score(M) = w_recency   · age_decay(last_referenced)
        + w_usage     · usage_signal(reference_count)
        + w_pin       · wilson_lower_bound(pinned_by, anti_pins=0)
        + w_reinforce · reinforce_signal(reinforcement_count)
        + w_subtype   · subtype_weight(subtype)
```

Where:
- `age_decay(t) = 1 / (1 + (now - t) / half_life(subtype))` — recency normalized by subtype-specific half-life
- `usage_signal = log10(max(reference_count, 1)) / log10(reference_count_cap)` — Reddit Hot pattern; compresses scale so vote inflation doesn't dominate (**reads / citations**)
- `wilson_lower_bound` — Reddit Best pattern; small-sample-pessimistic confidence interval on explicit pin signal
- `reinforce_signal = min( log10(max(reinforcement_count, 1)) / log10(reinforce_cap), 1.0 )` — **v1.6 (dev-spec 47c26a60).** Recurrence, log-compressed exactly like usage but a **DISTINCT signal** — `reinforcement_count` (re-learns) is never conflated with `reference_count` (reads). `reinforce_cap = 100` (a lesson re-taught 100× saturates). Monotonic in `reinforcement_count`, never negative.
- `subtype_weight` — semantic baseline; episodic faster decay; procedural slower decay; reference high-importance if not stale; feedback high-importance until superseded

Weights `w_*` calibrated against existing memory corpus (calibrate-at-first-pass per the doctrine's existing procedure). v1.6 five-weight allocation (per score-formula-doctrine v1.1, [5f2c1b94](../../.tropo-studio/score-formula-doctrine.md)): `w_recency = 0.20`, `w_usage = 0.30`, `w_pin = 0.25`, `w_reinforce = 0.15`, `w_subtype = 0.10`. **Sum = 1.0**; score normalized to [0, 1] range. The reinforce weight ships small; the doctrine's tier-threshold hysteresis prevents oscillation.

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
created: 2026-05-12T15:42
state: active
tags: [v1.26.0-walk, voting-mechanism, wilson-lower-bound]
---

Mike-A59 ratified Wilson lower bound for explicit pins after walking the small-sample inflation case. Pattern: explicit pin needs the Wilson math so newly-pinned entries don't dominate before implicit usage accumulates.
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
created: 2026-05-12T15:38
state: active
---

Keep migrations streamlined. Atomic per-agent. Don't pre-curate during migration — that's the curator's first run. Mike directive 2026-05-12.
```

`pinned_by: mike-maziarz` triggers Wilson lower bound boost at scoring. High score → tier: current.

**Example 3 — Reference memory citing canonical substrate:**

```yaml
---
uid: <8-hex>
type: memory
subtype: reference
scope: doctrine
context: "v1.26.0 Stream 0 substrate-repair sweep; flagging canonical-l0 set as architectural anchor"
refs:
  - "a1a003bf"   # mindbridge (canonical L0; Mike-A59 added 2026-05-12)
  - "5e9c1a82"   # agents L0
created: 2026-05-12T16:00
state: active
---

Canonical L0 set lives in .tropo-studio/registries/canonical-l0-projects.yaml. Validator gates build via validate-canonical-l0.py. Changes require Mike approval per OP 11.
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

1. **Required-field presence** — every newly-authored entry MUST have `uid`, `type: memory`, `subtype`, `scope`, `context`, `created`, and a non-empty markdown body. Historical compact entries are grandfathered until touched; the v1.5 migration forwards every currently defective entry.
2. **Enum compliance** — `subtype` must be in {semantic, episodic, procedural, reference, feedback}; `scope` must be in {agent, studio, doctrine}; `tier` must be in {current, topic, archival, demoted}. `vault`/`project` are read-time migration aliases only.

3. **UID resolution** — if `pinned_by` is set, MUST resolve to an entity UID in `vault/00-index.jsonl`. If `refs:` is set, EACH ref MUST resolve OR be flagged stale by curator.
4. **Score range** — if `score` is set, MUST be in [0.0, 1.0] inclusive.
5. **Context length** — `context` field ≤ 120 chars.
6. **Tier-state consistency (v1.26.0.1 amendment)** — `tier: current` + `tier: topic` MUST live at `entries/<uid>.md` per scope; `tier: archival` lives at `history/<uid>.md` per scope (per §State Machine); `tier: demoted` is terminal at `history/<uid>.md` until principal-ratified deletion. v1.26.0 initial spec had a bug claiming all non-stm tiers live at `entries/`; corrected at v1.26.0.1 bundled remediation per Stream 8 sa.skeptic P0-4.
7. **Curator-mutable field discipline** — `last_referenced`, `reference_count`, `score`, `tier`, and (v1.6) `reinforcement_count` + `reinforced_by` should only be modified by a writer with `modified_by:` containing "sa.memory-curator" or "argus" (overrides during substrate-repair). WARN on violation at v1.26.0 (unchanged grace posture at v1.6).

8. **Reinforcement field well-formedness (v1.6 amendment — dev-spec 47c26a60).** If `reinforcement_count` is set it MUST be a non-negative integer (a recurrence tally is never negative; log-compression in the §Score Formula bounds its contribution). If `reinforced_by` is set it MUST be a list of well-formed generation labels — non-empty strings, no empty/blank entries (e.g. `[A115, A124, A129]`); a scalar or a list containing non-string/blank entries is a violation. WARN at v1.6 (grace posture, matching the curator-mutable-field discipline). These fields are curator-written on a human-ratified MERGE only; see §Composition-with-v3 (`sa.memory-curator` Phase 6/7).

---

## Write Contract — Position 1 (Memory Sovereignty)

**Position 1 (Tropo-only):** Agents do NOT write substrate-class memory pins to harness-private stores (`~/.claude/`, `~/.codex/`, or any harness-equivalent). ALL substrate-class pins go to Tropo memory. This is a capsule-tier invariant, not a preference. (Rationale: harness-private stores do not port across harnesses, do not propagate to successive agent generations, and are invisible to the Tropo substrate. Empirical failure: Metis G59 wrote 6 substrate-class pins to `.claude/` in one session while authoring "extreme portability" into Mike's public bio. The failure is structural; Position 1 closes it at capsule tier. Dev-spec: 8c015275, locked 2026-07-01 by Mike.)

**Scope → Tier mapping (the write contract):**

| Scope | What it covers | Canonical path |
|-------|---------------|----------------|
| `agent` | Per-agent knowledge — feedback, learning, procedural reflexes, semantic facts specific to this agent | `agents/<slug>/.tropo-capsule/memory/entries/<uid>.md` |
| `studio` | Crew-class knowledge — shared doctrine, studio-level crew memory, crew-wide operating facts | `.tropo-studio/memory/entries/<uid>.md` |
| `doctrine` | OS-level, cross-Studio commitments — binding rules that apply to any Tropo Studio | `vault/files/<uid>.md` (type: `memory`, governed by vault) |

**The friction-parity abstraction:** Use `tropo-memory-write` (skill UID `0b35633f`, at `vault/skills/tropo-memory-write.md`). One call with `(scope, content)` — the skill maps scope → path, authors frontmatter with the correct capsule fields, appends to the episodic log, and registers the entry. This is friction-equal to a single harness write and always routes to the correct Tropo tier.

**What is NOT a substrate-class pin (and may stay harness-private):** Harness-instance-only UI state, session-scaffolding, ephemeral LLM configuration that has no portability value. The capsule's subtypes define substrate-class: `semantic`, `episodic`, `procedural`, `reference`, `feedback`. If the content fits one of these subtypes, it is substrate-class and belongs in Tropo memory.

**Enforcement posture at this capsule version:** the Position 1 rule is declared here and in OP-14 (`operating-principles.md` §14) + CLAUDE.md §Memory Writes. Automated enforcement (cross-harness audit, validator scan of `.claude/` growth) is explicitly v3. The floor guarantee is: boot-routing (every agent reads the rule at boot) + friction-parity (the abstraction exists) + proof test (floor test `a5c4993d`).

---

## Migration Notes

Stream 0 of v1.26.0 migrates existing memory substrate to this schema:

- **v1 agents (Vela, Metis):** each `feedback_*.md` file → one memory entry with `subtype: feedback` (the bulk are feedback-class pins). `MEMORY.md` index → curator-written `memory-current.md` (now a curated index, not the content store). Existing pin commentary becomes the body; YAML frontmatter added.
- **v2 agents (Argus, Cosmo, Tropo):** sections of `memory-current.md` (pointer-based at retirement) → individual entries with curator-assigned tier. Per A52→A58 deferred fold (Stream 6), the curator dispatches once to do the historical compaction across Argus's `history/` snapshots.
- **Studio-level memory** at `.tropo-studio/memory/`: each existing `*.md` pin → memory entry with `scope: studio`.

Migration is 1:1 mapping; pre-curation deferred to curator's first run.

---

## §Template (v1.5 — the mint-stamped scaffold; contract at [b933eafb](../../vault/files/b933eafb.md))

*Stamped verbatim by `mint file --type memory` (S2, bba40cd7); `<<MINT:*>>` tokens are the only substitution. `subtype:` and `scope:` have no single legal birth default — both are content-driven author choices, so both stay REQUIRED placeholders naming their legal values, never a literal. Memory content is a markdown body after frontmatter; this supersedes v1.4's stale `body:` string field.*

~~~markdown
---
uid: <<MINT:uid>>
type: memory
subtype: "<!-- REQUIRED: one of semantic | episodic | procedural | reference | feedback -->"
scope: "<!-- REQUIRED: one of agent | studio | doctrine -->"
context: "<!-- REQUIRED: one-line situating context, ≤120 chars -->"
created: '<<MINT:date>>'
state: active
schema_version: 2
capsule_version: '<<MINT:capsule_version>>'
governed_by: 8dd772a0
---

<!-- REQUIRED: memory content as markdown body; lead with the durable rule/fact -->
~~~

**Leg rules:** `subtype:`/`scope:` are author decisions with real consequences (they route curator scoring + write-contract tier) — never default them to a guessed common case. `pinned_by:` (array of UIDs, v1.26.0.1 shape) is optional and not scaffolded — add it only for a genuinely principal-pinned entry.

---

*memory.capsule v1.6 | UID a5b3c891 | Authored 2026-05-12 | v1.6 authored by talos-t35 under LOCKED memory-reinforcement dev-spec 47c26a60 (activation b233b7ac); **Mike-authorized lock-break + re-locked 2026-07-22** — adds curator-mutable `reinforcement_count` + `reinforced_by` (recurrence signal, distinct from reads) | v1.5 authored + scratch-proven by Argus A132 under Engine Phase-1 dev-spec dd9d4fe6; Mike-authorized + re-locked 2026-07-15 | Prior amendments preserved above | Ships in v1.26.0 · v1.67.0 · v1.90.0 · target Engine Phase 1*
*"Append memories to the log. The curator filters the signal. Author writes meaning; curator writes lifecycle. Memory lives in Tropo — not in the harness."*
