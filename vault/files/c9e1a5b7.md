---
uid: c9e1a5b7
name: "concept"
type: capsule-definition
extends: core
version: 1.0
tier: os
author: argus
created: 2026-04-21
modified: 2026-04-24
modified_by: argus-a33
created_by: argus-a30
status: deprecated
locked_by: argus-a30
locked_at: 2026-04-21
superseded_by: 7c47429a   # note.capsule — v3 Decision 1: ideas/concepts/notes collapse into one primitive
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
aligned_with: d2e7b1f4 # Typed Pipeline Architecture design brief
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

> **⚠️ DEPRECATED as of 2026-04-24 (v3 Decision 1).** The `concept` type is subsumed by [note.capsule (7c47429a)](note.capsule.md). Ideas, notes, and concepts are all one primitive in v3 — the simplest WorkItem, tagged per context (e.g., `tags: [idea]`, `tags: [product-idea]`). Historical concept instances remain readable and valid; new captures use note. See [Tropo Work v3 Architecture Specification (8b3f1d92)](../../vault/files/8b3f1d92.md) §6 Decision 1.
>
> Body below preserved as historical reference.

# concept — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Typed Pipeline Architecture + Pipelines as Playbook Subtype (d2e7b1f4)](../../vault/files/d2e7b1f4.md) |
| Extends | `core` |
| Superseded by | [note.capsule (7c47429a)](note.capsule.md) |

*A concept is a shaped idea — the bottom of the typed pipeline. It has enough form to be triaged at Design, enough substance to inform a design-brief, and enough honesty about its own incompleteness to invite the work that makes it real. Concepts compose upward through briefs, specs, and builds toward releases. Concepts come from anywhere.*

---

## Intent

Every Ideate-stage output is a `concept`. A concept articulates an idea with just enough structure for a reader to know what it is, why it matters, where its scope lies, and what remains unknown. Concepts are deliberately small artifacts — the first typed capture in the pipeline.

**A concept is upstream-terminal.** Nothing precedes a concept in the typed pipeline. A concept's `derived_from:` is always empty (and the field is not included in the frontmatter at all — see Governance Rule 2). Concepts compose forward into design-briefs via the brief's `derived_from:` field; the concept's own `composes_into:` tracks which briefs it fed.

**Before creating a concept:** does a live concept (or design-brief already) cover this idea? Check the ideate-stage inbox [work-pipeline/1-ideate/1-inbox/](../../work-pipeline/1-ideate/) and briefs in [design/1-inbox/](../../work-pipeline/2-design/1-inbox/) before authoring. Near-duplicate concepts create drift; prefer iterating a live concept to spawning a parallel one.

---

## Scope — What Is and Isn't a Concept

A vault entry is a **concept** when:

1. **Type:** `type: concept` in frontmatter.
2. **Stage:** `stage: ideate` (concepts live at the Ideate pipeline stage).
3. **Body shape:** four REQUIRED body sections present (see §Required Body Sections).

**Filename + location convention:** concepts live as ledger entries at `vault/files/<uid>.md` — same location as every other typed artifact. The filename is the UID + `.md`, not a slug. Discovery is via `type: concept` query against the ledger index, not by filename navigation. Concepts are NOT filed into `work-pipeline/1-ideate/` subfolders; they live in the flat ledger, with their `member_of:` array carrying the pipeline-bucket pointer.

Ideas in looser forms — raw notes, channel posts, half-sentences in other documents — are **not concepts**. They are pre-concept captures. When a pre-concept capture is shaped into a structural artifact (the four required sections filled), it becomes a concept.

A concept is NOT:
- A task (has no acceptance criteria; that's what briefs, specs, and plans add)
- A design-brief (no structured framework proposal yet)
- An ADR (no decision locked; concepts surface questions, they don't resolve them)

Concepts are the honest bottom of the pipeline. They're small on purpose.

---

## Required Frontmatter (beyond core)

| Field | Type | Constraint |
|---|---|---|
| `title` | string | ≤ 100 chars. Names the concept. |
| `description` | string | ≤ 160 chars. One-line summary — what this concept is about. |
| `stage` | literal | Must be `ideate`. |
| `state` | enum | `active` or `archived`. |
| `status` | enum | `draft`, `shaped`, `done`. See state machine below. |
| `owner` | string | Agent or human who captured the concept. |
| `member_of` | array of UIDs | At least one live project (typically the originating project; may additionally include [ideate-archive (a1c2e3d4)](../../vault/files/a1c2e3d4.md) if closed via Close path). **For strangers without a clear originating project:** use [ideate-archive (a1c2e3d4)](../../vault/files/a1c2e3d4.md) as the default `member_of:` entry. Every concept has a project home; the ideate-archive is the universal fallback until the concept gets adopted into a specific project. |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `composes_into` | array of UIDs | Downstream artifacts this concept composes into — typically `design-brief` UIDs authored from this concept. Empty at draft; populated when the concept advances to a brief OR attaches to an in-flight brief. Bidirectional pair with `derived_from:` on the downstream brief. |
| `supersedes` | UID | Prior concept this one supersedes (for concept iteration). |
| `superseded_by` | UID | Successor concept (bidirectional pair with `supersedes:` on the successor). |
| `tags` | array | Domain tags helping discovery (e.g., `[ai, governance, user-experience]`). |
| `captured_from` | string | Free-text origin note — where the idea came from (a conversation, a channel post, a moment). Helps preserve context when concepts persist across sessions. |
| `relationships` | array | Schema v2 unified relationships for cross-cutting refs. |

**Not present on concepts (by design):**

- **No `derived_from:` field.** Concepts are upstream-terminal. Declaring the field (even empty) implies something might precede — and nothing does. Omit entirely. See Governance Rule 2.

---

## Required Body Sections

Every concept body MUST contain these four sections, in this order. Each 1-3 paragraphs — substantial enough to shape the idea, short enough to stay honest about its early state.

### 1. `## The Idea`

What is this? State the idea directly in plain language. One paragraph, occasionally two. Avoid jargon. Write so a reader who has never heard of the idea can picture it. Lead with the verb — what the idea would do, what it would change, what it would enable.

### 2. `## Why It Matters`

Why should this exist? What problem does it address? Whose life gets better, or whose work gets easier, or which risk gets mitigated? The test: if a stranger reads only §The Idea and §Why It Matters, do they understand whether this concept is worth pursuing? If no, this section is too thin.

### 3. `## Initial Scope`

What would the first version look like? Draw the narrow line between "the minimum idea that would work" and "the expansive vision it could grow into." Concepts at the minimum-viable line advance more readily than maximally-scoped ones. If the minimum version is unclear, name that as an §Open Question rather than hand-waving.

### 4. `## Open Questions`

What do you not know? What decisions would a brief need to resolve before the idea becomes spec-able? List questions plainly. A concept with fewer than 2-3 open questions is either (a) genuinely simple (fine — keep it short) or (b) pretending to have answers it doesn't (not fine — surface what's unknown).

---

## Optional Body Sections

- `## Inspiration` — where the idea came from, non-obvious influences, prior art
- `## Near-Cousins` — concepts or briefs the author is aware of that this relates to but isn't duplicating
- `## Next Step` — the single next action that would advance this concept (e.g., "draft a design-brief proposing architecture X")

---

## State Machine

```
draft → shaped → done → (state: archived)
 ↑________↓ (revision during draft only)
```

| Status | Meaning |
|--------|---------|
| `draft` | Concept being authored. Sections being filled. Not yet ready for triage. |
| `shaped` | All four required body sections filled with real content (not placeholders). Concept is triageable: a reviewer can decide whether to advance, attach, or close. |
| `done` | Concept has transitioned via advance/attach/close from the ideate-GATE. Historical artifact; no further edits. |
| `archived` | Secondary home is [ideate-archive (a1c2e3d4)](../../vault/files/a1c2e3d4.md) if closed; or the originating project has itself archived. |

### Valid transitions

- `draft → draft` — revision during authoring.
- `draft → shaped` — all 4 required body sections filled with non-placeholder content; concept is triageable.
- `shaped → done (advance)` — a design-brief has been authored with `derived_from:` including this concept's UID; concept's `composes_into:` gets the brief's UID.
- `shaped → done (attach)` — this concept's content has been folded into an in-flight design-brief; concept's `composes_into:` gets that brief's UID; concept's `member_of:` array gets [ideate-archive (a1c2e3d4)](../../vault/files/a1c2e3d4.md) appended.
- `shaped → done (close)` — concept stands as historical with no downstream composition; `composes_into:` remains empty; `member_of:` gets [ideate-archive (a1c2e3d4)](../../vault/files/a1c2e3d4.md) appended.
- `done → archived` — when the originating project archives, or when the vault archives the concept as cleanup.

---

## Governance Rules

1. **Concepts are small on purpose.** Four required sections, 1-3 paragraphs each, is the target. A concept that requires 10 sections to explain is probably already a design-brief waiting to be written. Advance it.
2. **No `derived_from:` field.** Concepts are upstream-terminal in the typed pipeline. The field is not declared in frontmatter. Validator enforces absence.
3. **Shaped means ready for triage.** The `shaped` status is the triage gate — it signals to the **Ideate-stage owner** (a Director or executive agent assigned to triage Ideate-stage work; for Tropo's `tropo-work-pipeline`, this is declared in the pipeline instance) that the concept is reviewable. Concepts in `draft` are not yet triaged. "Director" in this capsule means a governance-role agent (per [ADR-022 Director pattern]); the concept's `owner:` field is the concept's *capturer* (whoever shaped it), which may or may not be the Ideate-stage owner who later triages it.
4. **One concept per idea.** Near-duplicate concepts create triage drift. If a live concept is close to what you'd write, iterate it via `supersedes:` rather than parallel-authoring.
5. **Advance/attach/close at the ideate-GATE.** The **ideate-GATE** is the position within the Ideate stage where the triage decision happens — specifically the `ideate-GATE` position declared in the pipeline the concept's project walks (see [pipeline.capsule v1.0 (e4c8a6b2)](pipeline.capsule.md) and Typed Pipeline Architecture brief §4). When a concept reaches `shaped` and the ideate-stage owner triages it, one of three transitions declares per the pipeline rule: advance to a brief, attach to an in-flight brief, or close. **Honor-system** means the discipline is documented and followed by convention but not mechanically enforced in v1.3; ADR-037 triggers automate enforcement in v1.4.
6. **`composes_into:` is append-only post-done** (amended 2026-04-21 per Phase 5 swarm P0 #3). Once a concept transitions to `done`, the body is immutable BUT the `composes_into:` frontmatter array remains append-only — parallel to arch-spec Rule 2's carve-out. This preserves the bidirectional pair invariant: when a second design-brief is later authored with `derived_from: [<this-concept-uid>]`, the concept's `composes_into:` MUST be appended with the new brief's UID to keep the graph symmetric. The prior framing (v1.0 initial draft) asserted full immutability which broke the invariant; cold-boot + Phase 5 swarm caught this.

---

## Validation Checks (run at check-in)

In addition to core checks:

1. **[enforced]** `type: concept`
2. **[enforced]** `stage: ideate`
3. **[enforced]** `status` is one of: `draft`, `shaped`, `done`
4. **[enforced]** `state` is one of: `active`, `archived`
5. **[enforced]** `member_of:` non-empty; every UID resolves
6. **[enforced]** `derived_from:` field NOT present (Governance Rule 2)
7. **[enforced]** If `composes_into:` present, every UID resolves to a live vault entry (typically `design-brief`)
8. **[enforced]** Body contains all 4 required sections in required order: §The Idea, §Why It Matters, §Initial Scope, §Open Questions
9. **[enforced, gated]** When `status: shaped` or later, each required body section is non-empty (>50 chars of content after the heading line). At `status: draft`, this check is silent — draft concepts have sections being filled. (Clarifies cold-boot 050 ambiguity: Check 9 is gated on shaped-or-later, not unconditional.)
10. **[enforced]** Transition to `status: shaped` requires all four required sections to pass check 9's content threshold
11. **[enforced]** If `status: done`, `composes_into:` is either populated (advance/attach paths) OR `member_of:` includes [a1c2e3d4] (close path)
12. **[enforced]** If `supersedes:` present, resolves to a prior concept; bidirectional pair with `superseded_by:` on successor. A superseded concept transitions to `status: done` (archived per §State Machine done → archived transition); the supersession is treated as a "close with superseded" variant of the Close path.

---

## Known Enforcement Gaps

Per the ADR-031 pattern:

| Gap | What closes it | Target release | Owner |
|---|---|---|---|
| Triage gate (shaped → done) is honor-system; no automated trigger surfaces to ideate-stage owner when a concept reaches `shaped` | ADR-037 trigger on `status:` transition to `shaped`; surfaces concept to owner for advance/attach/close declaration | v1.4.0 | argus |
| No validator today enforces the "no `derived_from:` field" rule | Pipeline validator at vault rebuild, per v1.4 Pillar 2 | v1.4.0 | argus |

---

## Relationship to Other Capsules

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.
- **[design-brief.capsule v2.1 (de5181b0)](design-brief.capsule.md)** — downstream. Concepts compose into briefs via bidirectional pair (`concept.composes_into:` ↔ `brief.derived_from:`). Briefs are the immediate next step for concepts that advance.
- **[project-plan.capsule v1.0 (f7b9c4a2)](project-plan.capsule.md)** — a concept may also compose into a project-plan directly if the concept spawns an immediate build without needing a formal brief (rare). The concept's `composes_into:` may include a project-plan UID in this case.
- **[pipeline.capsule v1.0 (e4c8a6b2)](pipeline.capsule.md)** — the pipeline schema declares `concept` as the Ideate-stage artifact type via `artifact_types: {ideate: concept}`.
- **[ideate-archive evergreen project (a1c2e3d4)](../../vault/files/a1c2e3d4.md)** — terminal sink for closed concepts.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — this capsule's own governance.

---

## Inheritance

Extends `core`. Inherits UID immutability, type immutability, owner/created/modified invariants.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author a concept.*

**Tools available:**
- `vault/00-index.jsonl` — grep before authoring to surface near-duplicates (honors Rule 4, "one concept per idea")
- Cascade indexes at `vault/00-cascade-*.jsonl` — locate adjacent concepts in the same domain
- UID generator — 8-hex; inherit the vault convention (`python -c "import secrets; print(secrets.token_hex(4))"`)
- `vault/files/<uid>.md` writer — the authored concept lives as a flat ledger entry; UID is the filename, not a slug
- [ideate-archive (a1c2e3d4)](../../vault/files/a1c2e3d4.md) — universal `member_of:` fallback when no originating project exists

**Skills:**
- `author-concept.skill.md` *(forthcoming v1.5)* — scaffold 4 required sections + frontmatter; omit `derived_from:` field entirely (Rule 2)
- `triage-concept.skill.md` *(forthcoming v1.4)* — ideate-stage owner walks the advance/attach/close decision at `shaped`

**Procedures:**
- Advance/attach/close at ideate-GATE — the concept's project-pipeline declares the ideate-GATE owner; triage happens when `status: shaped` (honor-system v1.3, ADR-037 trigger v1.4)
- Supersession for iteration — near-duplicate found? Author `supersedes: <prior-uid>` rather than parallel-authoring (Rule 4)
- Three-instrument verification — applies to amendments of concept.capsule itself (Argus build + sa.cold-boot + sa.skeptic), not to concept instances

**Rules (at-a-glance):**
1. Concepts are small on purpose — 4 required sections, 1-3 paragraphs each
2. **No `derived_from:` field** — concepts are upstream-terminal in the pipeline
3. `shaped` = triageable (all 4 sections filled with non-placeholder content; ≥50 chars each)
4. One concept per idea — supersede rather than parallel-author
5. Advance/attach/close at ideate-GATE (honor-system v1.3)
6. `composes_into:` is append-only post-done (preserves bidirectional pair with downstream briefs)

**Pitfalls:**
- Declaring `derived_from:` (even empty) → Rule 2 + Check 6 violation; concepts have no upstream
- Filling sections with placeholders and flipping to `shaped` → Check 10 failure
- Parallel-authoring a near-duplicate concept → Rule 4 drift; the triager can't tell which is canonical
- Concept with 10 sections or 5 paragraphs per section → this is already a design-brief waiting to be written; advance it
- Forgetting to append `composes_into:` when a downstream brief derives from this concept → bidirectional pair breaks

**Worked examples:**
- [25ddb006](../../vault/files/25ddb006.md) — "Meetly — User Research Synthesis" — toy-content concept authored by sa.pipeline-walker (Record 003) for the B2B meeting-assistant walker toy project
- [8d2db0cd](../../vault/files/8d2db0cd.md) — Helm walker toy-project Ideate-stage artifact; the first concept that passed walker 10/10 end-to-end
- [74d23972](../../vault/files/74d23972.md) — "Solace — Day-1 Onboarding Email" — toy-content concept for a learn-mode smart-thermostat brand (pipeline-walker Record 002)

**Go next:**
- Downstream composition → [design-brief.capsule v2.1 (de5181b0)](design-brief.capsule.md) — concepts compose into briefs
- Rare direct-to-plan path → [project-plan.capsule v1.0 (f7b9c4a2)](project-plan.capsule.md)
- Terminal sink → [ideate-archive (a1c2e3d4)](../../vault/files/a1c2e3d4.md) — evergreen archive project; the universal `member_of:` fallback when no originating project exists
- Pipeline position → [pipeline.capsule v2.0 (e4c8a6b2)](pipeline.capsule.md) declares concept as Ideate-stage output
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| deprecated | 2026-04-24 | **DEPRECATED per v3 Decision 1.** Subsumed by [note.capsule (7c47429a)](note.capsule.md). Ideas/concepts/notes collapse into one universal lightweight primitive; tagging distinguishes. Historical concept instances remain readable under the deprecation banner at top of body; new captures use note. `superseded_by: 7c47429a` frontmatter set. UID preserved. | argus-a33 |
| 1.0 | 2026-04-21 | Initial version LOCKED. D1 deliverable of v1.3 Typed Pipeline Capsule Ship v1.3 Typed Pipeline Capsule Ship project plan. Substantive body shape per Mike's OD1 (4 required sections). Upstream-terminal: no `derived_from:` field. Three-instrument verification: Argus build + sa.cold-boot 050 BATCH (verdict PASS-WITH-GAPS, ship recommended, 4 P1s remediated in-session): filename/location convention added to §Scope; `member_of:` stranger-fallback clarified (use ideate-archive as default); terminology defined inline (Director, ideate-GATE, honor-system, pipeline reference); Check 9 explicitly gated on status: shaped-or-later; Check 12 supersession-to-done transition clarified; validation checks labeled [enforced/gated]. Set-level swarm deferred to Phase 5. | argus-a30 |

---

*concept capsule definition | **DEPRECATED** 2026-04-24 per v3 Decision 1 (subsumed by [note.capsule (7c47429a)](note.capsule.md)) | originally LOCKED v1.0 by Argus A30 on 2026-04-21*
*"A concept is the honest bottom of the pipeline. Small on purpose. Shaped enough to triage. Upstream of everything that follows." — preserved as historical; new captures use note.*
