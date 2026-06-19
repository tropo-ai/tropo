---
subsystem_hub:
  - "2d083137"
uid: 7c47429a
name: "note"
type: capsule-definition
extends: core
version: 3.2
supersedes_version: "3.1"
tier: os
author: tropo
created: 2026-04-11
modified: 2026-06-09
modified_by: argus-a105
meta_status_rollup_added: "argus-a104 2026-06-08 — +done→done in meta_status_rollup per 4acf3f2d v0.4 DERIVE (Mike-signed 7-capsule lock-break batch); additive; prior modified argus-a43 2026-05-03"
status: locked
locked_by: argus-a43
locked_at: 2026-05-03
enforced_enums:
  status:
    canonical: [new, accepted, active, closed]
    aliases:
      done: closed
meta_status_rollup:
  to-do: [new, accepted]
  in-progress: [active]
  done: [closed, done]
schema_version: 2
governed_by: 222873b9
aligned_with:
  - 8b3f1d92   # Tropo Work v3 Architecture Specification (Decisions 1, 2, 4)
  - e1c47a9f   # dev-pipeline + vault inbox primitive (v1.4.4 source brief)
---

> **v3.2 amendment (2026-05-03, v3.1 → v3.2; LOCKED — three-instrument verified across rounds 1+2 with round-3 single-instrument regression PASS-WITH-FINDINGS; 4 P2 doc-drift residuals folded pre-lock):**
> - **v1.4.4 Stream A — work-item primitives.** Note joins task and design-brief under the inbox primitive (per [dev-pipeline + vault inbox primitive (e1c47a9f)](../../vault/files/e1c47a9f.md)) — but at the lightest discipline level: the universal primitives are added as OPTIONAL on note, reflecting that notes are captures-at-rest by default, not request-driven workflow.
> - **Added optional:** `status:` enum (`new` / `accepted` / `active` / `closed`) — populated only when the note's lifecycle is meaningful (e.g., routed via `intended_for:` and acted on). Default: absent. When set, note's status enum IS the abstract 4-state directly — no type-specific richness layered on top.
> - **Added optional:** `accepted_by:` array of acceptance records; `processor:` derived array from open `accepted_by:` entries.
> - **No request-lifecycle on note** (`requested_by:` / `requested_of:` / `verifier:` / `approver:` not added). Notes remain captures, not requests; the existing `intended_for:` field handles routing intent. If a captured note matures into requested work, promote to a task via `composes_into:`.
> - **No `verifier:` / `approver:` / `resolution:` / `blocked:`** — notes don't have processing-quality gates or terminal sub-resolutions.
> - **Migration v3.1 → v3.2:** zero-touch. Existing notes pass v3.2 validation unchanged — `status:` is optional, so absence is legal. No body changes; no field additions; no migration script needed for the note class.
>
> **v3 amendments (2026-04-24, v2.0 → v3.0):**
> - **Decision 1:** note is now the universal lightweight WorkItem — subsumes `concept` (deprecated, see [concept.capsule (c9e1a5b7)](concept.capsule.md)) and covers all capture-class work (ideas, notes, observations, questions). Tagging distinguishes (e.g., `tags: [idea]`, `tags: [observation]`).
> - **Decision 2:** Rule 2 flipped — notes are **rewriteable**. Git history carries the temporal record.
> - **Decision 4:** `stage:` field dropped. State machine is now `state: active | archived` only.
> - **Decision 7:** tagging stays frictionless — freeform, unlimited, lowercase-hyphenated.
> - **Added optional:** `intended_for:` (entity UID) — "who this note is going to" when a capture is routed to someone specific.

# note — Capsule Definition

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Tropo Work v3 — Architecture Specification (8b3f1d92)](../../vault/files/8b3f1d92.md) |
| Extends | `core` |

*The lightest governed primitive. A quick capture — an insight, an observation, a question, an idea — with just enough structure to find it later.*

## Intent

Capture thoughts fast and find them later. Notes are the "Apple Notes" of Tropo-OS: governed by the OS (every note has a UID, lives in the Vault, has a type), permissive at the app layer (body is free-form, categories are optional, tags are unlimited, no required sections, no workflow).

The OS says: "this thing exists and is governed." The app says: "do whatever you want inside it."

**Use a note when:**
- A design insight surfaces mid-session and you want to capture it before it disappears
- An observation or question is worth preserving but isn't a task (no work to do) or a decision (no binding commitment)
- You want to log something for future reference without the overhead of a full document
- A notebook entry has matured enough to stand on its own as a discrete, findable artifact

**Do NOT use a note for:**
- Work to do — use `task`
- A binding decision — use `decision`
- A formal specification — use a document with appropriate tags
- Stream-of-consciousness capture — use the notebook (append-only, single-file)

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `captured_by` | string | Agent-id or human name of who wrote the note. ≤ 30 chars. |

**Required core fields (inherited from `core.capsule`):** `uid`, `type` (= `"note"`), `created`, `modified`, `state` (= `active` at capture). See [core.capsule (ee814120)](core.capsule.md) for full core inheritance. *(v3.2 cross-capsule alignment: same five fields enumerated identically across note v3.2 / design-brief v3.1 / task v4.0.)*

**Timestamp convention:** `created` SHOULD use `YYYY-MM-DDTHH:MM` (date + time) rather than date-only. Notes are quick captures where temporal ordering within a day matters. The core capsule's ISO 8601 format permits both; notes prefer the higher resolution.

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `category` | string | From the Common Categories list below, or any freeform string. Not an enum — the list is a starting point, not a constraint. |
| `tags` | array of strings | Unlimited freeform tags. The discovery and composition axis. Use lowercase-hyphenated. |
| `surfaced_by` | string | Who had the thought (often different from who captured it) |
| `context` | string | One-line "what we were doing when this surfaced." ≤ 120 chars. |
| `refs` | array of UIDs | Related vault entries |
| `member_of` | array of UIDs | Projects this note belongs to. Replaces v1 `parent_project:`. Default when not set: vault-inbox (L0 fallback per v3 spec §2.5). |
| `intended_for` | UID | **v3 addition.** When the note is a capture routed to a specific entity (e.g., an agent captures an idea for the founder), declares who it's going to. Optional; routing semantics are v1.5+ — v3 carries the field for capture-time tagging without automating delivery. |
| `composes_into` | array of UIDs | Downstream artifacts derived from this note (e.g., a design-brief that was born from this capture). Populated when the note is promoted/derived-from; preserves provenance. |
| `status` | enum | **v3.2 addition.** One of: `new`, `accepted`, `active`, `closed`. Populated only when the note's lifecycle is meaningful (typically routed via `intended_for:` and acted on). Default: absent. When set, see §State Machine + §Aggregate Rule. |
| `accepted_by` | array of records | **v3.2 addition.** Acceptance records — who has agreed to act on this note (typically empty for self-captured notes; populated when `intended_for:` recipient or another agent accepts the note for processing). Each record: `{accepted_by_uid, date_accepted, date_completed, date_rejected, notes}`. See §Aggregate Rule below. |
| `processor` | array of UIDs | **v3.2 addition.** Derived view over `accepted_by:` records that have `date_accepted:` set and no `date_completed:`/`date_rejected:` — the currently-active acceptors. Computed on read by default; materialization is a query-cache implementation detail (writers MUST keep materialized values consistent with the source-of-truth `accepted_by:` array). Empty when no active acceptors. |

Any additional fields are legal as frontmatter extras per core rules. The note capsule does not police extras.

## Common Categories

These exist so new users aren't staring at a blank field. They are suggestions, not an enum. The system accepts any string. If you invent `category: shower-thought`, it works.

| Category | When to use |
|---|---|
| `design-insight` | How the system should work. An architectural learning from practice. |
| `product-idea` | A feature, capability, or experience idea worth preserving. |
| `observation` | Something noticed. No action implied. |
| `question` | An open question worth preserving for later. |
| `friction` | Something that didn't work well. A pain point. |
| `pattern` | A recurring shape worth naming. |
| `principle` | A rule or guideline that emerged from practice. |

## State Machine

**Two orthogonal dimensions** (v3.2):

### `status:` — work-item lifecycle (v3.2 addition; OPTIONAL)

```
[absent] OR  new → accepted → active → closed
                    ↑___________↓ (re-routing: status returns to new if all acceptances rejected)
```

`status:` is optional on notes. When present, the canonical status enum is: `status:` ∈ {new, accepted, active, closed}. Most notes (self-captured observations, ideas, design insights) never need lifecycle tracking and leave the field absent. Routed notes (typically via `intended_for:`) populate `status:` when the recipient's processing arc matters.

| Status | Meaning |
|-------|---------|
| (absent) | Note has no lifecycle tracked. Default for self-captured notes that don't require processing. |
| `new` | Captured; routed via `intended_for:` or otherwise pending acceptance; no acceptor has agreed to act on it yet. |
| `accepted` | At least one acceptance record exists in `accepted_by:` with `date_accepted:` set, no `date_completed:` or `date_rejected:`; processor has agreed but has not begun acting. |
| `active` | At least one processor is currently acting on the note. **Trigger:** processor edits the note's body, populates `composes_into:` with a derived artifact, or explicitly flips status from `accepted` → `active`. The transition is by convention — the agent processing the note declares it active when they begin work. |
| `closed` | Terminal — note's processing arc is complete. The note's body and `composes_into:` are the durable record. |

**Notes have no `verify` / `approve` / `blocked` / `resolution:` semantics** — captures don't have processing-quality gates, and the terminal state is uniformly `closed` (no done/rejected/cancelled distinction; a note that "fails" is simply archived via `state: archived`).

### Aggregate Rule (status derived from acceptance — applies when status IS set)

When `status:` is populated on a note, it reflects the aggregate of its `accepted_by:` records:

- All records empty / all rejected (`date_rejected:` set on every entry) → `status: new`
- ≥1 live record (`date_accepted:` set, no `date_completed:`/`date_rejected:`), no processing started → `status: accepted`
- ≥1 processor currently acting (per the `active` trigger above) → `status: active`
- All processors completed (`date_completed:` set on all live records) OR explicitly closed by requester → `status: closed`

The `status:` field is stored explicitly (not computed on read) for query efficiency. Consistency between stored `status:` and `accepted_by:` is enforced at write-time by **Validation Check 10** (the validator catches drift).

When `status:` is absent, the Aggregate Rule does not apply — the note has no lifecycle being tracked.

### `state:` — lifecycle visibility (preserved from v3.1)

```
state: active → state: archived
```

| State | Meaning |
|-------|---------|
| `active` | Note exists and is current |
| `archived` | Note is historical (archive is permanent; preserved for temporal record) |

`status:` and `state:` are independent dimensions. A note at `status: closed` may still be at `state: active` (closed processing, but still a current artifact). A note flips to `state: archived` when it's no longer the current reference.

**v3 amendment (preserved from v3.0):** `stage:` field dropped per Decision 4 — notes have no pipeline-position.

## Governance Rules (in addition to core)

1. **No required body structure.** The body is free-form markdown. One sentence, one paragraph, ten paragraphs, or nothing at all — if the title and frontmatter say enough, an empty body is valid.
2. **Notes are rewriteable** (v3 Decision 2; flipped from v2.0 Rule 2 which was append-only). If a note's insight evolves, edit the note in place — git history is the temporal record. Append-only note-chains added friction that didn't earn its keep under the frictionless-capture principle. Notes that significantly pivot may optionally be superseded via a new note with `supersedes:`, but this is uncommon and reserved for cases where preserving the prior text as-written matters.
3. **Notes are not tasks.** A note that implies work to do should generate a task as a follow-on, not become one. Notes observe; tasks act. If you catch yourself writing acceptance criteria in a note, you're writing a task.
4. **Tags + projects are the grouping mechanism** (v3 amendment; was Collections in v2.0). Notes are standalone vault entries organized via (a) tags (freeform, unlimited, lowercase-hyphenated — the primary discovery axis), and (b) `member_of:` project memberships (including the L0 vault-inbox default). Collections/collection-refs remain available for lightweight reference manifests (see [collection-ref.capsule (c01ec700)](collection-ref.capsule.md)) but are not the primary organization mechanism under v3. Don't build folder-like structures — build playlists via tags, roll up via projects.

## Validation Checks (run at check-in)

In addition to core checks:

1. `captured_by` is present and ≤ 30 chars
2. `state:` is one of: `active`, `archived` (v3 amendment: `stage: build` check dropped per Decision 4)
3. If `category` is present, it is a non-empty string
4. If `tags` is present, each tag is ≤ 30 chars, lowercase-hyphenated
5. If `refs` is present, each UID exists in the vault index
6. If `intended_for` is present, resolves to an entity UID (v3 addition)
7. If `composes_into` is present, each UID resolves to a live vault entry (v3 addition)
8. **[v3.2]** If `status:` is present, value is one of: `new`, `accepted`, `active`, `closed`. (Field is OPTIONAL — absence is legal and is the default for self-captured notes.)
9. **[v3.2]** If `accepted_by:` is present, every entry is a structured record with required `accepted_by_uid:` (resolves to an entity or pipeline-run) and `date_accepted:` (ISO date), plus optional `date_completed:`, `date_rejected:`, `notes:`.
10. **[v3.2]** Aggregate consistency (when `status:` is set): stored `status:` value matches what the Aggregate Rule (§State Machine) would derive from `accepted_by:`. Drift caught at check-in. **(Cross-link: §State Machine §Aggregate Rule defines the derivation; this check is its enforcement mechanism.)**
11. **[v3.2]** If `processor:` is materialized in frontmatter, every entry corresponds to a live acceptance record in `accepted_by:` (`date_accepted:` set, no `date_completed:`/`date_rejected:`). Materialization is a query-cache choice; the source of truth is `accepted_by:`.

## Concurrency Policy

Optimistic on everything. Notes are lightweight and owned by one person. Merge conflicts are unlikely; if they occur, both versions are valid — create a second note.

## Relationship to Other Types

- **vs. Task:** a note observes; a task acts. A note can *generate* a task ("this insight implies we should do X") but should not *become* one.
- **vs. Document:** a document is a substantial, structured artifact (spec, guide, report). A note is a quick capture. If a note grows past a few paragraphs and gains structure, it has probably become a document.
- **vs. Decision:** a decision is a binding commitment with a state machine (proposed → accepted → superseded). A note has no binding force.
- **vs. Notebook (5ab66d92):** the notebook is a single append-only file for stream-of-consciousness capture. Notes are discrete, individually-governed vault entries. The notebook is the inbox; notes are the filed artifacts. Notebook entries that mature can be promoted to notes.
- **vs. Memory:** a memory is an active directive applied at boot. A note is a historical record. A note can inform a memory ("we learned X" → memory says "apply X going forward"), but the note itself is not applied as a rule.

## How to Capture a Note

See `.tropo/actions/create-note.action.md` for the step-by-step action (filename retained for action-registry compatibility; verb in v3 narrative discipline is **capture** per Decision 13). The capsule definition (this file) is WHAT a note is. The action file is HOW to capture one.

## Inheritance

Extends `core`. Inherits all core rules. Not currently extended by subtypes, though domain-specific note types (`research-note`, `meeting-note`) are possible future extensions via the standard capsule inheritance mechanism.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you capture a note.*

**Tools available:**
- `vault/00-index.jsonl` — grep by tag or title before capturing (avoid silent duplication of an existing capture)
- `vault/files/<uid>.md` writer — notes live as flat ledger entries; filename is the UID
- [vault-inbox (2d5f9b04)](../../vault/files/2d5f9b04.md) — L0 fallback project (ship-scoped); default `member_of:` when no project is named at capture time
- Tag-cascade queries — once tagged, notes are findable across the project graph via tag joins
- `.tropo/actions/create-note.action.md` — action-registry entry for capture (verb mapping per Decision 13)

**Skills:**
- `capture-note.skill.md` *(forthcoming v1.5)* — scaffolds frontmatter (`captured_by:` + `created:` with HH:MM precision + tags + member_of) and accepts free-form body
- Tag-find skill *(forthcoming v1.5)* — list all notes carrying a given tag across the Vault

**Procedures:**
- **Capture** workflow — verb: **capture** per Decision 13. Set `captured_by:` (your agent-id), use `created:` with `YYYY-MM-DDTHH:MM` precision (per Timestamp convention), tag freely (lowercase-hyphenated), assign `member_of:` (default vault-inbox if unsure). Body free-form; empty body is valid if title + frontmatter say enough.
- **Tag** workflow — verb: **tag** per Decision 13. Add to `tags:` array; use Common Categories baseline palette OR invent freeform; lowercase-hyphenated.
- **Archive** workflow — verb: **archive** per Decision 13. Flip `state: active → archived`. **`state:` and `status:` are orthogonal** (v3.2): archiving does not force `status: closed`; a note may be at `state: archived` while still carrying `status:` from its routed lifecycle, OR may have no `status:` at all (the v3.2 default for self-captured notes). See §State Machine for the two-dimensional lifecycle.
- **Edit-in-place** — notes are rewriteable per Rule 2 (v3 Decision 2). If a note's insight evolves, edit the note; git history carries the temporal record. **Do not** chain hand-forked notes for revisions — that was v2.0 append-only behavior, flipped in v3.
- **Promotion to a heavier type** — if a note grows past a few paragraphs and gains structure, it has probably become a `document` (or a `design-brief`, or a `decision`). Author the heavier type with `derived_from: [<note-uid>]`; optionally set the note's `composes_into:` to the new entry.

**Rules (at-a-glance):**
1. **No required body structure** — body is free-form; empty is valid (Rule 1)
2. **Notes are rewriteable** (v3 Decision 2; flipped from v2.0 append-only) — git history is the temporal record
3. **Notes are not tasks** — a note observes; a task acts. If you catch yourself writing acceptance criteria in a note, you're writing a task (Rule 3)
4. **Tags + projects are the grouping mechanism** — not folders, not collections-as-containers (Rule 4)
5. **`status:` is OPTIONAL on notes (v3.2)** — when present, value is one of `new` / `accepted` / `active` / `closed`; absence is the default for self-captured notes that don't track a lifecycle. `state: active | archived` is the orthogonal lifecycle-visibility dimension. `stage:` field is dropped per v3 Decision 4 (status is the lifecycle field).

**Pitfalls:**
- **Writing a task as a note** — if it has acceptance criteria, owner, or implies work, it's a task. Rule 3 violation; convert before saving.
- **Treating notes as append-only** — pre-v3 (v2.0) Rule 2 said append-only; v3 Decision 2 flipped it. Old habits persist; if you catch yourself authoring a successor note for a small revision, just edit the original instead.
- **Setting `status:` without aligning `accepted_by:` records** — when `status:` IS tracked on a note (v3.2), the §Aggregate Rule requires `accepted_by:` to align with the stored status. Validation Check 10 catches drift. Self-captured notes that don't need lifecycle tracking should leave both fields absent — that's the default and the most frictionless path.
- **Forgetting tags** — untagged notes are hard to find later. Tags are the primary discovery axis (Rule 4).
- **Using `note` for substantial structured content** — once it has §sections, an audience, and a publish lifecycle, it's a `document`. Promote via `derived_from:` rather than letting the note grow.
- **Setting `member_of: []`** — the note is then orphaned (no project home). Default to [vault-inbox (2d5f9b04)](../../vault/files/2d5f9b04.md) at capture if no specific project applies.

**Worked example — minimal v3.2 note (status absent, self-captured):**

```yaml
---
uid: a1b2c3d4
type: note
created: 2026-05-03T14:30
captured_by: argus-a44
state: active
tags: [design-insight, work-items]
member_of: [2d5f9b04]   # vault-inbox (ship-scoped)
---
The aggregate rule pattern is a useful primitive across work-item types.
```

**Worked example — routed v3.2 note (status populated, intended_for + accepted_by tracking):**

```yaml
---
uid: e5f6g7h8
type: note
created: 2026-05-03T15:00
captured_by: mike
state: active
status: active
intended_for: argus-a44
accepted_by:
  - accepted_by_uid: argus-a44
    date_accepted: 2026-05-03
    notes: "Composing into design-brief 127d2fe2."
processor: [argus-a44]
tags: [design-insight, v1.4.4]
member_of: [2d5f9b04]
---
Reframe decision as a 4th work-item type.
```

**Worked examples (ship):**
- See [00-index.jsonl](../../vault/00-index.jsonl) `type: note` for the live catalog of notes in your vault. v3 notes accumulate as work proceeds; fresh installs begin with the catalog empty.

**Argo development examples (argo-reference — Argo development vault only):**
- 4e5c9f18 — Capsule naming convention idea captured as a v1.5-candidate note by Argus A33; tagged `capsule-naming`, `v1.5-candidate`

**Go next:**
- More structured alternative → [document.capsule v3.1 (d0c00001)](document.capsule.md) — for substantial written content with publish lifecycle
- Procedural step-by-step content → [how-to.capsule (a7c3f489)](how-to.capsule.md)
- If the capture is actually work to do → [task.capsule (3289712a)](task.capsule.md) (request-lifecycle: `requested → accepted → active → verify → done`)
- If the capture is a binding commitment → [decision.capsule v3.1 (179d74e9)](decision.capsule.md)
- Related quick-capture pattern (argo-reference example): "Mike's Notebook" 5ab66d92 — single append-only stream-of-consciousness file in the Argo development vault
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 2.0 | 2026-04-16 | (v2.0 locked; body signature at the time read "DRAFT v1" — a drift documented at v3 reconciliation.) | tropo |
| 3.0 | 2026-04-24 | **v3 amendment — note becomes the universal lightweight WorkItem.** Subsumes `concept` (deprecated, see [concept.capsule (c9e1a5b7)](concept.capsule.md)) per v3 Decision 1; any capture (idea / concept / observation / question) is now a note with appropriate tags. Rule 2 FLIPPED from append-only to rewriteable per Decision 2 — git history carries the temporal record. `stage:` field dropped; state machine is `state: active → archived` only per Decision 4. Added optional frontmatter fields: `intended_for:` (UID of entity the capture is routed to) + `composes_into:` (downstream artifacts derived from this note). Rule 4 reworded: tags + projects are the grouping mechanism (collections remain available as lower-weight reference manifests per collection-ref.capsule). Signature-line drift (body said "DRAFT v1" while frontmatter said v2.0) resolved at v3.0. UID preserved at 7c47429a. | argus-a33 |
| 3.1 | 2026-04-25 | **Gate B P0 #4 remediation (sa.skeptic 014 lens).** Added §Workshop — Shop Signage section (the surface Decision 13's verb-audit explicitly governs). v3.0 had shipped without §Studio on the most-used primitive — sa.skeptic 014 P0-3 flagged this as a cold-boot self-containment cliff. Studio section pattern matches the 8 other v3 capsules (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next); content uses canonical Decision 13 verbs throughout (`capture`, `tag`, `archive`). Renamed §"How to Create a Note" heading → §"How to Capture a Note" (deprecated verb `create` → canonical `capture`). UID preserved at 7c47429a. | argus-a34 |
| 3.2 | 2026-05-03 | **LOCKED — v1.4.4 Stream A work-item primitives** ([source brief: e1c47a9f](../../vault/files/e1c47a9f.md)). Note joins task and design-brief under the universal work-item primitives — at the lightest discipline level, all OPTIONAL. Added optional `status:` enum (`new` / `accepted` / `active` / `closed`; absence is the default for self-captured notes). Added optional `accepted_by:` array of acceptance records + `processor:` derived array (computed-on-read by default; materialization is implementation choice). Aggregate Rule documented (when `status:` is set, it's derived from `accepted_by:`; stored explicitly for query efficiency; consistency enforced by Validation Check 10). State machine §updated to two orthogonal dimensions (optional `status:` work-item lifecycle + preserved `state:` lifecycle visibility). Validation checks 8–11 added; check 10 cross-linked to Aggregate Rule. `accepted → active` transition trigger documented (processor edits body, populates composes_into, or explicit flip). Required core fields enumerated (uid, type, created, modified, state). Two minimal worked-example instances added (self-captured + routed). No request-lifecycle (`requested_by:` / `requested_of:` / `verifier:` / `approver:`) — notes are captures, not requests; promotion to task handles request-shaped work. **Migration v3.1 → v3.2 zero-touch:** existing notes pass v3.2 validation unchanged (status optional, absence legal). UID preserved at 7c47429a. Pending three-instrument verification regression (post-remediation) bundled with task v4.0 + design-brief v3.1. | argus-a43 |

---

*note capsule definition | LOCKED v3.2 | Tropo-OS | amended + locked 2026-05-03 by argus-a43 (v1.4.4 Stream A — optional work-item primitives + three-instrument verification across 3 rounds + single-instrument regression PASS); v3.1 lock April 25, 2026 by argus-a34 preserved in git history; v3.0 amendment April 24, 2026 by argus-a33; v2.0 lock April 11, 2026 preserved | UID preserved at 7c47429a*
*"The lightest governed primitive. Capture it. Tag it. Find it later. Edit it freely; git remembers. Track its lifecycle only when it matters."*
