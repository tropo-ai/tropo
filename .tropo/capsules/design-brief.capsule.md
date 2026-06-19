---
subsystem_hub:
  - "2d083137"
uid: de5181b0
name: "design-brief"
type: capsule-definition
extends: core
version: 3.2
supersedes_version: "3.1"
tier: os
author: tropo
created: 2026-04-10
modified: 2026-06-09
modified_by: argus-a105
meta_status_rollup_added: "argus-a104 2026-06-08 — +locked→done in meta_status_rollup per 4acf3f2d v0.4 DERIVE (Mike-signed 7-capsule lock-break batch); additive, bucket-only (status enforced_enums unchanged — locked still WARNs per v3_2 note); prior modified argus-a99 2026-06-05"
status: locked
locked_by: argus-a99
locked_at: 2026-06-05
v3_2_lock_break: "v3.1 -> v3.2 lock-break Mike-A99-signed 2026-06-05 (verbatim 'consider it signed'). Adds the enforced_enums block (the c4512bdc Piece-3 pilot): status canonical [design, specify, done] (enum UNCHANGED) + done-family aliases. Per-type scoping: for a design-brief, shipped/published mean done (a brief whose informed release shipped is complete) so they are aliases here - they are canonical for release/document (hence those types deferred). locked is NOT aliased (genuinely overloaded: done on a shipped brief vs committed-current on a live roadmap) so it WARNs + the groomer flags it. Also normalizes the canonical prose anchor to the ∈ form for the coherence check. Purely additive (enum unchanged); turns on enforcement + the alias machinery for this type. Implements c4512bdc Piece 3."
enforced_enums:
  status:
    canonical: [design, specify, done]
    aliases: {closed: done, complete: done, completed: done, finished: done, final: done, shipped: done, published: done}
meta_status_rollup:
  to-do: [design, accepted]
  in-progress: [specify, active]
  done: [done, locked, superseded, closed, complete, completed, finished, final, shipped, published]
meta_status_rollup_note: "argus-a104 2026-06-08 — rollup completion per the unified lifecycle knot (move 2, 9f6a1379); additive lock-break."
schema_version: 2
governed_by: 222873b9
aligned_with:
  - d2e7b1f4   # Typed Pipeline Architecture design brief (historical)
  - 8b3f1d92   # Tropo Work v3 Architecture Specification (v3 amendment source)
  - e1c47a9f   # dev-pipeline + vault inbox primitive (v1.4.4 source brief)
pattern_exemplar: d0c00001   # document.capsule — design-brief is patterned on document per v3 Decision 3; adds exploratory-permissiveness + composability pair + lifecycle-without-lock
---

> **v3.1 amendment (2026-05-03, v3.0 → v3.1; LOCKED — three-instrument verified across rounds 1+2 with round-3 single-instrument regression PASS-WITH-FINDINGS; 4 P2 doc-drift residuals folded pre-lock):**
> - **v1.4.4 Stream A — work-item primitives.** Design-brief joins note + task as a first-class work-item under the inbox primitive (per [dev-pipeline + vault inbox primitive (e1c47a9f)](../../vault/files/e1c47a9f.md)).
> - **Existing 3-state status enum preserved** (`design → specify → done`). It is intrinsic to design-brief lifecycle and richer than the abstract 4-state needs.
> - **Added optional:** `accepted_by:` array of acceptance records — who is using this brief to inform their work (typically the agent who picked it up to author the spec it informs); `processor:` derived array from open `accepted_by:` entries.
> - **Added optional:** `requested_by:` (single UID) — who requested the brief, formalizing today's `mike-directed` tag + body-provenance convention; `requested_of:` (single UID) — who was asked to author. Most briefs are self-initiated and leave both empty; briefs authored at someone else's direction populate them.
> - **No `verifier:` / `approver:` / `resolution:` fields** — briefs aren't verified the way specs are (the downstream spec is what gets verified); briefs aren't approved (acceptance via `accepted_by:` covers it); briefs don't have multiple terminal resolutions (a brief that "fails" simply moves to `state: archived`).
> - **Mapping to abstract 4-state** (cross-WorkItem queries): `design` → abstract `active`; `specify` → abstract `active`; `done` → abstract `closed`. Briefs do not map to abstract `new` or `accepted`; those abstract states are unused for this type. See §State Machine.
> - **Migration v3.0 → v3.1:** purely additive. Existing briefs get `accepted_by: []` on migration; status enum unchanged; `requested_by:` / `requested_of:` left empty (manual backfill optional for known mike-directed briefs).
>
> **⚠️ v3 amendment (2026-04-24, v2.1 → v3.0):** The `stage:` field on design-brief has been renamed to `status:` per v3 Decision 4. Values preserved: `design → specify → done` is now a `status:` lifecycle enum, not a `stage:` field. The known terminology collision that v2.1 documented at length (§State Machine) is **resolved** by this rename — `stage:` is now exclusively a pipeline-run property; design-brief's lifecycle is `status:`.
>
> Read "stage:" in the body below as "status:" throughout. The v3.0 amendment is a rename, not a semantics change; all existing guidance applies with the renamed field.

# design-brief — Capsule Definition

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Typed Pipeline Architecture + Pipelines as Playbook Subtype (d2e7b1f4)](../../vault/files/d2e7b1f4.md) |
| Aligned with | [Tropo Work v3 — Architecture Specification (8b3f1d92)](../../vault/files/8b3f1d92.md) |
| Pattern exemplar | [document.capsule (d0c00001)](document.capsule.md) |
| Extends | `core` |

*A design brief — a shorter, exploratory document that articulates a problem, proposes a framework, and informs a future spec. Briefs are not locked; they inform.*

## Intent

Capture early-stage design thinking before a full spec exists. A brief articulates a problem, proposes a framework, raises open questions, and points at the spec or specs that will eventually be written from it. Briefs are deliberately less formal than specs — they exist to start a conversation, not to end one.

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `description` | string | ≤ 120 chars; one-line summary |
| `author` | string | who drafted the brief |
| `status` | enum | One of: `design`, `specify`, `done`. Briefs always begin at `design` (active authoring); no pre-authoring `new` state. (v3.1 — surfaced explicitly; was implicit in v3.0 §State Machine + Validation Check 3) |

**Required core fields (inherited from `core.capsule`):** `uid`, `type` (= `"design-brief"`), `created`, `modified`, `state` (= `active` at authoring). See [core.capsule (ee814120)](core.capsule.md) for full core inheritance. *(v3.1 cross-capsule alignment: same five fields enumerated identically across note v3.2 / design-brief v3.1 / task v4.0.)*

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `version` | string | semantic version if iterating on the brief |
| `informs` | array of UIDs | specs this brief informs (when they exist) |
| `refs` | array of UIDs | related entries |
| `derived_from` | array of UIDs | Upstream artifacts this brief composes from — typically `concept` UIDs when a concept preceded the brief. Empty/unset is legal (many briefs are commissioned directly). Composability pair with `composes_into:` on each referenced concept, per Typed Pipeline Architecture brief. v2.1 amendment. |
| `composes_into` | array of UIDs | Downstream artifacts this brief feeds — typically `project-plan` or `arch-spec` UIDs authored from this brief. Populated as downstream artifacts are authored. Bidirectional pair with `derived_from:` on the downstream. v2.1 amendment. |
| `accepted_by` | array of records | **v3.1 addition.** Acceptance records — who is using this brief to inform their work (typically the agent that accepted the brief to author the spec it informs). Each record: `{accepted_by_uid, date_accepted, date_completed, date_rejected, notes}`. See §Aggregate Note in State Machine. |
| `processor` | array of UIDs | **v3.1 addition.** Derived view over `accepted_by:` records that have `date_accepted:` set and no `date_completed:`/`date_rejected:` — currently-active acceptors. Computed-on-read by default; materialization is a query-cache implementation detail (writers MUST keep materialized values consistent with the source-of-truth `accepted_by:` array). |
| `requested_by` | UID | **v3.1 addition.** Who requested the brief (e.g., the founder when a brief is captured at their direction). Optional — most briefs are self-initiated by the author. Formalizes today's `mike-directed` tag + body-provenance convention. Single UID. |
| `requested_of` | UID | **v3.1 addition.** Who was asked to author the brief. Optional. Single UID. Mutable on re-request (rare for briefs). |

## State Machine

The design-brief carries **two orthogonal dimensions** (v3.1):

### `status:` — design-brief intrinsic lifecycle (3-state, preserved from v3.0)

```
status: design → status: specify (informing) → status: done (after spec is locked)
 ↑___________↓ (revision)
```

**Canonical enum (enforce-first anchor):** `status:` ∈ {design, specify, done}. *(v3.2 — off-canon done-family synonyms `closed`/`complete`/`completed`/`finished`/`final`/`shipped`/`published` are aliases→`done` per the `enforced_enums` block; `locked` is overloaded → WARNs for groomer adjudication.)*

| Status | Meaning |
|-------|---------|
| `design` | Brief is being written or revised |
| `specify` | Brief is reviewed and actively informing one or more specs |
| `done` | Brief's work is complete (spec it informed has locked) |

*Historical note: in v2.1 and earlier this field was named `stage:`, which created a terminology collision with the typed-pipeline architecture where `stage:` was also used as a pipeline-position field on other capsules. v3 Decision 4 resolved the collision by dropping `stage:` from every WorkItem-class capsule and renaming design-brief's lifecycle enum to `status:`. The collision is now gone — queries against `stage:` only return pipeline-run `current_stage:` references, and design-brief lifecycle queries use `status:` cleanly. Pre-v3 brief instances may still carry `stage:` in frontmatter; the v3 migration pass (Stream C of [6e8d3f9a](../../vault/files/6e8d3f9a.md)) handles the rename.*

### Valid transitions

- `status: design` → `status: specify` (reviewer accepts the brief)
- `status: specify` → `status: design` (revision needed)
- `status: specify` → `status: done` (the spec this brief informed has locked)

### Mapping to abstract 4-state (cross-WorkItem queries; v3.1 addition)

Per Option B (layered abstraction) — design-brief's intrinsic 3-state maps to the universal abstract layer:

| Intrinsic `status:` | Abstract status | Reasoning |
|---|---|---|
| `design` | `active` | Brief is being written — work in progress |
| `specify` | `active` | Brief is informing a spec — still active as input |
| `done` | `closed` | Spec the brief informed has locked — terminal |

**Design-brief never maps to abstract `new` or `accepted`** — those abstract states are unused for this type. Briefs come into being already at `design` (active authoring); there's no pre-authoring placeholder state. If a brief is "requested but not yet authored," that case is tracked via a task with `composes_into:` pointing at the eventual brief — not via an empty brief at status `new`.

**`state: archived` orthogonality.** The `state:` dimension (active / archived) is independent of the `status:` mapping. A brief at `status: done` may still be `state: active` (the brief remains the current authoritative reference for the spec it informed). `state: archived` flips when the brief is no longer the current reference (typically when superseded by a newer brief on the same topic). Cross-WorkItem queries should filter on `state: active` first, then on the abstract status, to surface only currently-relevant briefs.

### Aggregate note for `accepted_by:` (v3.1)

Unlike note (where `status:` IS the abstract status, derived from `accepted_by:`), design-brief's intrinsic `status:` is independent of `accepted_by:`. Both are stored explicitly; both are queryable.

- `accepted_by:` tracks **who is using the brief to inform their work** (typically agents who picked it up to author the spec it informs).
- `status:` tracks **the brief's own authoring lifecycle** (being-written / informing / spec-has-locked).

A brief at `status: specify` may have multiple acceptors in `accepted_by:` (multiple agents using it to inform multiple downstream specs). When a brief reaches `status: done`, all live acceptance records should be closed (`date_completed:` set) — this is convention, not enforced.

## Governance Rules (in addition to core)

1. **Briefs are not locked.** Unlike design specs, briefs do not have a `locked` state. They exist to inform, not to constrain.
2. **A brief that informs a spec stays in `informing` even after the spec is locked.** The brief is the historical record of the thinking that produced the spec.
3. **A brief can be updated even after the spec it informs is locked.** This is allowed because the brief is exploratory; the spec is the contract.

## Validation Checks (run at check-in)

In addition to core checks:

1. **[enforced]** Description length ≤ 120 chars
2. **[enforced]** Author field is present
3. **[enforced]** `status:` is one of: `design`, `specify`, `done` (renamed from `stage:` per v3 Decision 4)
4. **[enforced]** `state:` is one of: `active`, `archived`
5. **[enforced]** `derived_from:` (if present) — every UID resolves to a live vault entry, typically a `concept`. (v2.1 amendment)
6. **[enforced]** `composes_into:` (if present) — every UID resolves to a live vault entry, typically a `project-plan` or `arch-spec`. (v2.1 amendment)
7. **[v3.1]** If `accepted_by:` is present, every entry is a structured record with required `accepted_by_uid:` (resolves to an entity or pipeline-run) and `date_accepted:` (ISO date), plus optional `date_completed:`, `date_rejected:`, `notes:`.
8. **[v3.1]** If `processor:` is materialized in frontmatter, every entry corresponds to a live acceptance record in `accepted_by:` (`date_accepted:` set, no `date_completed:`/`date_rejected:`). Materialization is a query-cache choice; the source of truth is `accepted_by:`.
9. **[v3.1]** If `requested_by:` is present, resolves to an entity UID.
10. **[v3.1]** If `requested_of:` is present, resolves to an entity UID.

---

## Known Enforcement Gaps

| Gap | Impact | Path forward |
|-----|--------|--------------|
| **Pre-v3 brief instances carrying `stage:` instead of `status:`** | Validation Check 3 will hard-fail any pre-v3 instance still using the legacy `stage:` field at next check-in. v3.0 explicitly grandfathered these through the migration window; v3.1's stricter required-field surfacing leaves them exposed. | The v2.x → v3.0 status-rename migration (Stream C of [`6e8d3f9a`](../../vault/files/6e8d3f9a.md)) must complete before v3.1 enforcement is universal. Pre-v3 instances NEED to migrate; they shouldn't grandfather forever. Until that completes, treat pre-v3 instances as MIGRATION-PENDING — flag at check-in, route to manual reconciliation, do not block other vault operations. |

## Inheritance

Extends `core`. Inherits all core rules.

---

## Relationship to Other Capsules

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor (UID immutability, owner semantics, frontmatter invariants).
- **[concept.capsule (forthcoming, v1.3 ship)](concept.capsule.md)** — upstream typed artifact. Concepts may precede briefs; when they do, the brief declares `derived_from: [<concept-uid>]` and the concept's `composes_into:` gets this brief's UID. Composability bidirectional pair per Typed Pipeline Architecture brief.
- **[project-plan.capsule v1.0 (f7b9c4a2)](project-plan.capsule.md)** — downstream. Project-plans frequently derive from briefs via `derived_from:`; this brief's `composes_into:` gets the project-plan's UID.
- **[arch-spec.capsule (forthcoming, v1.3 ship)](arch-spec.capsule.md)** — downstream. Arch-specs may derive from briefs when a spec formalizes a brief's thinking. Same bidirectional pair pattern.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — this capsule's governance.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author a brief.*

**Tools available:**
- `vault/00-index.jsonl` — grep for existing briefs on the topic before authoring
- Cascade indexes at `vault/00-cascade-*.jsonl` — find adjacent briefs in the same domain
- `vault/files/<uid>.md` writer — briefs live as flat ledger entries; UID is the filename
- Upstream concept lookup — `grep -l "type: concept" vault/files/` to find concepts ready to derive from

**Skills:**
- `author-design-brief.skill.md` *(forthcoming v1.5)* — scaffold frontmatter + populate optional `derived_from:` from upstream concept
- `register-file.skill.md` *(forthcoming, Stream 2 V-S2.1)* — register brief in 00-index.jsonl with correct frontmatter

**Procedures:**
- `derived_from:` composability — populate from upstream concept UIDs; atomically append brief's UID to the concept's `composes_into:`
- Brief → spec handoff — when a brief is ready, author an arch-spec with `derived_from: [<this-brief>]`; brief's `composes_into:` gets the spec's UID
- Status-vs-stage discipline — briefs use `status:` for lifecycle (design/specify/done), NOT `stage:` (v3 Decision 4). The pre-v3 "stage collision" is resolved by the rename; queries use `status:` cleanly.
- Three-instrument verification — applies to amendments of design-brief.capsule itself, not to brief instances

**Rules (at-a-glance):**
1. **Briefs are NOT locked** — they exist to inform, not to constrain
2. A brief stays in `specify` even after its downstream spec locks — the brief is the historical thinking
3. Briefs remain editable post-spec-lock — exploratory, not contractual
4. `derived_from:` (optional) — every UID resolves to a concept
5. `composes_into:` (optional) — every UID resolves to a project-plan or arch-spec
6. `status: design → specify → done` is the lifecycle field (renamed from `stage:` in v3.0 per Decision 4)

**Pitfalls:**
- Treating a brief as a contract → specs are contracts; briefs inform
- Using `stage:` on a design-brief instance (v2.1 and earlier convention) → v3 violation; use `status:` instead per Decision 4. Pre-v3 instances migrate per Stream C of [6e8d3f9a](../../vault/files/6e8d3f9a.md)
- Authoring a brief when an upstream concept exists and not setting `derived_from:` → missed composability pair
- Spec authored from brief without appending brief's `composes_into:` → breaks bidirectional pair
- Treating `done` as body-immutable — briefs remain editable; it's the spec derived from them that's contractual

**Worked examples:**
- [e5661ec7](../../vault/files/e5661ec7.md) — Tropo Work v2 brief (d.pm P3, 2026-04-23; the v1.4 primitive source)
- [804c2f3d](../../vault/files/804c2f3d.md) — v1.4 Kickoff Design Brief (Vela V34)
- [7e71f1ca](../../vault/files/7e71f1ca.md) — verification pack design brief (Argus A31)
- [afe7503c](../../vault/files/afe7503c.md) — v1.1 release brief
- [7d4a9c2e](../../vault/files/7d4a9c2e.md) — additional real instance
- [127d2fe2](../../vault/files/127d2fe2.md) — v3.1 instance demonstrating the new `accepted_by:` + `requested_by:` fields (decision-as-work-item brief, Argus A43, 2026-05-03)

**Worked example — minimal v3.1 design-brief instance (self-initiated):**

```yaml
---
uid: 9b8a7c6d
type: design-brief
created: 2026-05-03
status: design
state: active
title: "Universal acceptance primitive across WorkItems"
description: "Adds accepted_by + processor to all work-item types as universal primitive."
author: argus-a43
owner: argus
version: "0.1"
member_of: [2d5f9b04]   # vault-inbox (ship-scoped)
tags: [design-brief, work-item, v1.4.4]
---
```

**Worked example — Mike-directed v3.1 design-brief (request-lifecycle populated):**

See [`127d2fe2`](../../vault/files/127d2fe2.md) — frontmatter shows `author: argus-a43`, the v3.1 `accepted_by:` array populated at handoff time, and request-lifecycle context in §Provenance (the brief was authored at Mike's direction; `requested_by:` would be populated at v3.1 if the field had existed when this brief was authored).

**Go next:**
- Upstream capture → [concept.capsule v1.0 (c9e1a5b7)](concept.capsule.md) — many briefs derive from a concept
- Downstream formalization → [arch-spec.capsule v1.0 (a7f2e9c4)](arch-spec.capsule.md) — specs formalize briefs
- Alternative downstream → [project-plan.capsule v1.0 (f7b9c4a2)](project-plan.capsule.md) — for briefs that spawn plans directly
- Pipeline position → [pipeline.capsule v2.0 (e4c8a6b2)](pipeline.capsule.md) — briefs at Design stage
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 3.0 | 2026-04-24 | **v3 amendment.** `stage:` field renamed → `status:` per v3 Decision 4; values (`design → specify → done`) preserved. Pre-v3 `⚠️ Known terminology collision` §State Machine block removed as resolved-by-rename; historical note retained. Studio prose updated (Procedures + Rules-at-a-glance + Pitfalls) to use `status:` consistently. `pattern_exemplar: d0c00001` declared in frontmatter per Decision 3 — design-brief is patterned on document.capsule with exploratory-permissiveness + composability-pair + lifecycle-without-lock discipline layer. Signature-line drift resolved at v3.0. UID preserved at de5181b0. | argus-a33 |
| 3.1 | 2026-05-03 | **LOCKED — v1.4.4 Stream A work-item primitives** ([source brief: e1c47a9f](../../vault/files/e1c47a9f.md)). Design-brief joins note + task as a first-class work-item. Intrinsic 3-state status enum preserved unchanged. Added optional `accepted_by:` array of acceptance records + `processor:` derived array (universal work-item pattern; `processor:` is computed-on-read by default, materialization is implementation choice). Added optional `requested_by:` / `requested_of:` (formalizes today's mike-directed tag + body-provenance convention). State Machine §updated with abstract 4-state mapping (`design` → active, `specify` → active, `done` → closed), `state: archived` orthogonality clarification, and aggregate note clarifying the relationship between intrinsic `status:` and `accepted_by:`. Added `status:` to Required Frontmatter table (drift fix from v3.0 — was implicit). Required core fields enumerated. 4 new validation checks (7-10). §Known Enforcement Gaps section added — pre-v3 instances carrying `stage:` instead of `status:` flagged as MIGRATION-PENDING (per arch-specs P1-3). Two minimal worked-example instances added (self-initiated + reference to Mike-directed `127d2fe2`). No `verifier:` / `approver:` / `resolution:` (briefs aren't verified/approved/resolved that way). Migration v3.0 → v3.1 purely additive: existing briefs get `accepted_by: []`. UID preserved at de5181b0. Pending three-instrument verification regression (post-remediation) bundled with note v3.2 + task v4.0. | argus-a43 |
| 2.1 | 2026-04-21 | v1.3 capsule ship deliverable D5. Additive non-breaking amendment: added `derived_from:` and `composes_into:` optional frontmatter fields to enable composability pair with typed pipeline artifacts. Added validation checks 5 + 6. Added §Relationship to Other Capsules section. Self-attested mechanical amendment per project-plan v1.3 Typed Pipeline Capsule Ship project plan D5 acceptance criteria. Existing v2.0 instances remain Day-1 compliant (fields are optional). | argus-a30 |
| 2.0 | 2026-04-16 | Unknown (prior version; no changelog entry preserved). Lockstate reached. | tropo |

---

*design-brief capsule definition | LOCKED v3.1 | Tropo-OS | amended + locked 2026-05-03 by argus-a43 (v1.4.4 Stream A — work-item primitives + request-lifecycle + three-instrument verification across 3 rounds + single-instrument regression PASS); v3.0 lock April 24, 2026 by argus-a33 preserved in git history; v2.1 lock April 21, 2026 preserved | UID preserved at de5181b0*
*v3.1 adds work-item primitives (`accepted_by:` + `processor:`) and optional request-lifecycle (`requested_by:` / `requested_of:`) without changing the intrinsic 3-state lifecycle.*
