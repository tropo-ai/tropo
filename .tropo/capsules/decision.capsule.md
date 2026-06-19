---
uid: 179d74e9
name: "decision"
type: capsule-definition
extends: core
version: 3.1
supersedes_version: "3.0"
tier: os
author: tropo
created: 2026-04-10
modified: 2026-06-09
modified_by: argus-a105
status: locked
enforced_enums:
  status: [design, done]
meta_status_rollup:
  to-do: [design]
  done: [done]
schema_version: 2
governed_by: 222873b9
aligned_with: 8b3f1d92   # Tropo Work v3 Architecture Specification
pattern_exemplar: d0c00001   # document.capsule — decision is patterned on document per v3 Decision 3 + 5; adds principal-accepts + immutability-after-acceptance + Alternatives-Considered body requirement + ADR-N decision numbering
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# decision — Capsule Definition

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Tropo Work v3 — Architecture Specification (8b3f1d92)](../../vault/files/8b3f1d92.md) |
| Pattern exemplar | [document.capsule (d0c00001)](document.capsule.md) |
| Extends | `core` |

*An architectural or strategic decision. Once accepted, decisions are immutable. They may be superseded by a newer decision but never edited in place.*

## Intent

Record decisions with their rationale, alternatives considered, and consequences. Decisions are the constitutional law of the vault — they record what was chosen and why, so that future agents can understand the reasoning even if the original participants are gone. This is the ADR (Architectural Decision Record) pattern.

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `description` | string | ≤ 120 chars; one-line summary of what was decided |
| `decision_number` | string | sequential identifier (e.g., `ADR-031`) |
| `proposer` | string | who proposed the decision |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `endorsed_by` | string | who endorsed/accepted the decision — the principal acknowledgement (a scalar UID/name). **Renamed from `accepted_by` in v1.72 Move 4 (field-disambiguation):** `accepted_by` is now the *task* assignment-record-array ONLY; a decision's principal-acknowledgement is the distinct concept `endorsed_by`. |
| `accepted_at` | ISO 8601 date | when the decision was accepted/endorsed |
| `supersedes` | UID | prior decision this one replaces |
| `superseded_by` | UID | newer decision that replaces this one |
| `refs` | array of UIDs | related entries |

## State Machine

*v3 amendment (2026-04-24, v2.0 → v3.0): field renamed `stage:` → `status:` per v3 Decision 4 + 5. Values (`design`, `done`) preserved — this is a rename, not a semantics change.*

```
design → done → (superseded: done + state: archived)
```

**Canonical status enum:** `status:` ∈ {design, done}

| Status | State | Meaning |
|-------|-------|---------|
| `design` | `active` | Decision is under consideration |
| `done` | `active` | Decision accepted; immutable |
| `done` | `archived` | Decision superseded by a newer one |

### Valid transitions

- `status: design` → `status: done` (vault principal only)
- `status: done` → `state: archived` (when superseded by a replacement)

### Invalid transitions

- `done` → `design` (cannot un-accept; author a new decision with `supersedes:` set per v3 Decision 13 canonical verb)
- Re-editing the body of an accepted decision (frontmatter `superseded_by` may be updated; body is frozen)

## Governance Rules (in addition to core)

1. **Decisions are immutable once accepted.** The body of an accepted decision cannot be edited. Errors are corrected by creating a new decision that supersedes.
2. **Only the vault principal accepts.** In Argo, that is Mike. Other agents propose; only the principal accepts.
3. **Supersession requires both directions** (same as design-spec): the new decision references the old via `supersedes`, and the old decision is updated to reference the new via `superseded_by`. The body of the old decision is NOT edited — only the frontmatter `superseded_by` field is updated.
4. **Decision numbers are sequential.** The next decision number is one greater than the highest existing decision number in the Vault.
5. **An accepted decision must record alternatives considered** in its body. Pure-prescription decisions without rationale are rejected.

## Validation Checks (run at check-in)

In addition to core checks:

1. Description length ≤ 120 chars
2. Decision number is present and matches the pattern `ADR-\d+` (or equivalent)
3. Proposer field is present
4. `status:` is one of: `design`, `done` (renamed from `stage:` per v3 Decision 4)
5. `state:` is one of: `active`, `archived`
6. If `status: done` and `state: active`: `endorsed_by` and `accepted_at` fields are present
7. If `status: done` and `state: active`: entry body contains an "Alternatives Considered" section
8. If `state: archived`: `superseded_by` field is present
9. If `supersedes` is present, the referenced UID exists and has `superseded_by` pointing back to this entry

## Inheritance

Extends `core`. Inherits all core rules.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you propose a decision.*

**Tools available:**
- `vault/00-index.jsonl` — grep existing ADRs before proposing (Rule 4: decision numbers are sequential)
- [All Decisions collection (417898d0)](../../vault/files/417898d0.md) — every ADR in number order with supersession chains visible; walk this to assign the next decision number
- `vault/files/<uid>.md` writer — decisions live as flat ledger entries

**Skills:**
- `propose-decision.skill.md` *(forthcoming v1.5)* — scaffold frontmatter + body sections (Context / Options / Decision / Alternatives Considered / Consequences)
- Supersession pattern — new ADR sets `supersedes:`, old ADR's frontmatter gets `superseded_by:` appended; old body stays frozen (Rule 3)

**Procedures:**
- Decision-number assignment — walk the All Decisions collection; next ADR number = highest + 1; write the number into `decision_number:` frontmatter before proposing
- Acceptance path — **only the vault principal (Mike) accepts**; other agents propose at `status: design`; Mike flips `status: done` + sets `endorsed_by:` + `accepted_at:` (Rule 2)
- Supersession protocol — bidirectional `supersedes:` / `superseded_by:` pair set atomically at new-ADR acceptance; body of superseded ADR is NOT edited, only its frontmatter
- Alternatives-considered discipline — pure-prescription decisions without rationale are rejected (Check 7)

**Rules (at-a-glance):**
1. Decisions are immutable once accepted — corrections happen via supersession, never via in-place edit
2. **Only the vault principal (Mike) accepts** — agents propose, principal accepts
3. Supersession requires bidirectional `supersedes:` / `superseded_by:` pair
4. Decision numbers are sequential — next = highest + 1
5. Accepted decisions must record "Alternatives Considered" in body (Check 7)
6. `status:` = `design` (proposed) or `done` (accepted); `state:` = `active` or `archived` (superseded). Renamed from `stage:` in v3.0 per Decision 4.

**Pitfalls:**
- Editing the body of an accepted decision → Rule 1 violation; author a superseding ADR instead
- Any agent except Mike accepting a proposal → Rule 2 violation; proposals ≠ acceptances
- Setting `supersedes:` without updating the old ADR's `superseded_by:` → Check 8 failure; broken bidirectional pair
- Skipping "Alternatives Considered" section → Check 7 rejection; pure-prescription decisions flagged
- Assigning a decision number without walking the index → collision with concurrent proposal; renumber retroactively

**Worked examples:**
- [e6c3f410](../../vault/files/e6c3f410.md) — ADR-032 Three-Layer Boot Configuration Model; the governance backbone for agent activation (Argus-proposed 2026-04-13, amended 2026-04-19)
- [c7b4e2f9](../../vault/files/c7b4e2f9.md) — ADR-031 Three-Layer Vault Hygiene; named the L1/L2/L3 self-governance stack; Mike-authored Mike-accepted
- [cfe79756](../../vault/files/cfe79756.md) — ADR-038 "CAPSULE.md lives in `<folder>/.tropo-studio/`"; structural decision about per-folder governance hiding

**Go next:**
- Index → [All Decisions collection (417898d0)](../../vault/files/417898d0.md) — ADR-number ordered catalog; authoritative
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)
- Acceptor → Mike; proposers typically Argus (architecture), Vela (operations), Metis (strategy)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1 | 2026-04-10 | Initial version locked. ADR pattern with sequential `decision_number:`, principal-accepts governance, immutability-after-acceptance, alternatives-considered body requirement. | tropo |
| 2.0 | 2026-04-16 | (v2.0 implicit in prior frontmatter though body signature read "v1"; reconciled at v3.0 amendment.) | tropo |
| 3.0 | 2026-04-24 | v3 amendment: `stage:` field renamed → `status:` per v3 Decisions 4 + 5; values (`design`, `done`) preserved. `pattern_exemplar: d0c00001` declared per Decision 3 — decision.capsule is patterned on document.capsule with heavy governance discipline layer (principal-accepts, immutability, alternatives-considered, ADR-numbering, bidirectional supersedes). UID preserved at 179d74e9. | argus-a33 |
| 3.1 | 2026-04-25 | **Gate B P0 #3 remediation.** Duplicate Validation Check #8 (lines 89-90 of v3.0) fixed — the second check (supersedes/superseded_by bidirectional pair) renumbered to Check 9. Mechanical bug; no semantic change. Caught by sa.arch-specs 016. UID preserved at 179d74e9. | argus-a34 |

---

*decision capsule definition | LOCKED v3.1 | amended 2026-04-25 by argus-a34 (Gate B P0 #3 — duplicate Check 8 renumbered); v3.0 amended 2026-04-24 by argus-a33; v1/v2.0 lock April 10, 2026 by Tropo preserved in git history | UID preserved at 179d74e9*
*"Decisions are the constitutional law of the vault — they record what was chosen and why. Immutable once accepted."*
