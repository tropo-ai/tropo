---
uid: 7f4a8d2e
name: generation-log
type: capsule-definition
extends: core
version: 1.0
tier: os
author: argus
created: 2026-05-09
modified: '2026-06-10'
modified_by: talos-t14
created_by: argus-a53
status: retired
locked_by: argus-a53
locked_at: 2026-05-09
archived_at: 2026-05-11
archived_by: argus-a58
archived_in_cycle: v1.21.0
archived_reason: 'Retired in v1.21.0 Stream 3 — gen-log substrate retires; activation registry substrate replaces. Canonical successor: activation.capsule (4e8b21f0) v1.0. Legacy gen-log files migrated
  to vault archives at v1.21.0 Stream 0b as type: document, status: archived. Their content lives at vault/files/ as honest historical record; going-forward lineage queries hit the activation registry,
  not the archives.'
superseded_by: 4e8b21f0
schema_version: 2
governed_by: 222873b9
aligned_with:
- c080a66d
- 9c4e7a2b
- 8dd772a0
state: archived
---

# generation-log — Capsule Definition v1.0

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [Vela's gen-log capsule-typing thesis (c080a66d)](../../vault/files/c080a66d.md) |
| Aligned with | [v1.15.3 design brief (9c4e7a2b)](../../vault/files/9c4e7a2b.md) |
| Extends | `core` |
| Composes with | [write-gen-log-row.skill (c9b3e6f1)](../skills/write-gen-log-row.skill.md) — the procedural skill that writes rows per this schema |

*The governance contract for agent generation-logs at `agents/<name>/generation-log.md`. Closes the 4×-recurrence row-order drift defect (V33 2026-04-21 / A38 2026-04-27 / A47 2026-05-06 / A49 2026-05-06) via three-layer pattern: capsule declares rules; skill mechanizes the write procedure; tropo-validate.py enforces invariants at vault-rebuild time (ERROR severity from day-one per Mike-A53 lock + v1.10 enforcement gate cleared).*

*v1.0 LOCKED 2026-05-09 by Argus A53 at v1.15.3 ship per Mike-A53 captain-mode walk-and-confirm. Composes Vela c080a66d Tier 2-3 substrate elevation thesis + three Argus augmentations (Tier-1 fold, current-substrate composition, ERROR-from-day-one).*

---

## Intent

A generation-log is the **authoritative identity record** for an agent across generations. Each row records: generation tag (e.g., `A53`, `V42`, `G50`), boot date, retire date (or `—` if active), and key contribution narrative. The log is append-only at the row level; existing rows are immutable except for retire-date population at retirement and post-hoc reconciliation when recovering from drift.

Per ADR-028 (boot-time generation logging): an agent's generation = last row + 1. This makes the gen-log a **load-bearing substrate primitive** — agents derive their identity from it at boot. Drift in the gen-log is identity drift; row-order drift specifically caused tail-read agents to misidentify their generation 4× in 3 weeks, which is why this capsule exists.

The capsule does NOT govern the gen-log file at `vault/files/<uid>.md` (gen-logs live at their canonical agent paths, not in vault/files/). It governs the **shape** any file at `agents/<name>/generation-log.md` must satisfy, enforced by the validator at vault-rebuild time.

---

## File Location (canonical)

`agents/<name>/generation-log.md`

Where `<name>` is the agent slug (e.g., `argus`, `vela`, `metis`, `orpheus`). Files at this path are auto-detected by the validator and verified against this capsule's invariants.

---

## Required Body Structure

A valid generation-log file MUST contain:

1. **H1 title** — `# <Name> — Generation Log` (e.g., `# Argus — Generation Log`)
2. **Header narrative** — short prose block (1-3 short paragraphs) describing the log's role
3. **Markdown separator** — `---`
4. **Generation table** — markdown table with the columns declared below, in this order

---

## Generation Table Schema

The table MUST have these four columns in this order:

| Column | Header | Type | Constraint |
|---|---|---|---|
| 1 | `Gen` | string | Generation tag matching regex `^[A-Z][a-z]?[0-9]+$` (e.g., `A53`, `V42`, `G50`, `Vd1`) — case-sensitive prefix + integer suffix |
| 2 | `Boot Date` | string | ISO 8601 date `YYYY-MM-DD` OR approximate `~YYYY-MM-DD` for early historical records (v1.15.3 in-cycle amendment) |
| 3 | `Retire Date` | string | ISO 8601 date `YYYY-MM-DD` OR approximate `~YYYY-MM-DD` OR literal `—` (em-dash) OR `[Session in progress]` for current generation OR empty (currently-active agent; common de facto pattern; v1.15.3 in-cycle amendment 2026-05-09) |
| 4 | `Key Contribution` | string | Free-form narrative; no constraint |

**Header row format:** the literal headers `\| Gen \| Boot Date \| Retire Date \| Key Contribution \|` followed by the separator row `\|-----\|-----------\|-------------\|------------------\|`. The validator parses by header text, not column position alone, for robustness against future column additions.

---

## Invariants (validation rules)

The validator MUST verify these invariants. Any violation is an ERROR (post-v1.10 enforcement; v1.15.3 lock).

1. **Generation tag uniqueness.** No two rows may share a Gen tag. (Catches duplicate generation entries from sloppy boot or merge conflicts.)
2. **Sort order: (prefix, int_suffix) ascending.** Rows MUST be sorted lexicographically by prefix then numerically by suffix. `A1, A2, A10, A48, A53` — not `A1, A10, A2, A48, A53`. (Catches the specific drift defect this capsule exists to close.)
3. **Tag format conformance.** Every Gen cell MUST match the regex `^[A-Z][a-z]?[0-9]+$`. (Catches typos, lowercase prefixes, missing suffix integers.)
4. **Boot date format.** Every Boot Date cell MUST match `^~?\d{4}-\d{2}-\d{2}$` (exact OR approximate-with-tilde for early historical records). (Catches date-format drift; v1.15.3 amendment allows the `~` approximate marker.)
5. **Retire date conformance.** Every Retire Date cell MUST match: exact date `^\d{4}-\d{2}-\d{2}$`; OR approximate `^~\d{4}-\d{2}-\d{2}$`; OR exactly `—` (em-dash); OR start with `[Session` (in-progress marker); OR empty (currently-active agent — common de facto pattern; v1.15.3 in-cycle amendment 2026-05-09). (Allows historical fuzziness + active-agent emptiness while catching obvious format drift.)
6. **Predecessor row closed.** When a new row is appended at boot, the immediately-preceding row's Retire Date MUST NOT be `[Session in progress]` or empty — i.e., the predecessor must be retired before the successor opens. **Post-hoc reconciliation is acceptable** when recovering from drift incidents; the validator surfaces the violation but the agent's recovery flow may close out the predecessor row from the new boot. (Vela's brief framing 2026-05-08.)

**Invariant 6 ENFORCEMENT NOTE.** v1.15.3 ships invariant 6 at WARN severity (not ERROR) because legitimate post-hoc reconciliation triggers it. v1.16+ may promote to ERROR if drift recurrence justifies, with reconciliation flow becoming an explicit `[reconciled-at-boot]` row marker.

Invariants 1-5 ship at ERROR severity from day-one.

---

## State Machine

```
draft → locked
```

Generation-log files don't have a state machine in the typed-primitive sense — they're append-only substrate. Once created (first boot of an agent), a gen-log lives indefinitely. The `state` field is not applicable; the capsule is structural-shape governance.

---

## Governance Rules

1. **Append-only at row scope.** Existing rows are immutable except (a) retire-date population at retirement; (b) post-hoc reconciliation when recovering from drift; (c) row-order resorting via `sort-gen-log.py` (preserves row content; only changes order).
2. **Canonical path.** Files MUST live at `agents/<name>/generation-log.md`. The validator auto-detects via path glob.
3. **Authoritative for identity.** Per ADR-028: agent generation = last row + 1. Boot agents derive identity from the gen-log; the capsule's invariants are identity-load-bearing.
4. **Skill is the write abstraction.** Playbooks call [`write-gen-log-row.skill`](../skills/write-gen-log-row.skill.md) (UID `c9b3e6f1`); skills don't inline write prose. Centralizes the logic that historically caused drift via per-agent prose variation.
5. **Script is the executor.** [`sort-gen-log.py`](../../.tropo-studio/scripts/sort-gen-log.py) at the Studio-admin tier (Vela's 2026-05-08 ship); `--check` mode is non-mutating (boot-drift detection); `--apply` mode is idempotent (clean files no-op). Skills + playbooks call the script; agents don't author rows by hand.
6. **Boot-drift check at Group 1.** Tier 3 boot extensions SHOULD invoke `sort-gen-log.py --check` before reading the gen-log tail (v1.15.3 Stream E.ii pattern; Argus Tier 3 ships this).

---

## Validation Checks (run by tropo-validate.py)

The validator MUST implement these checks for every file matching `agents/*/generation-log.md`:

1. File exists at canonical path (skip if absent — gen-log is created at first agent boot).
2. H1 title matches `^# .+ — Generation Log$`.
3. Markdown table is detectable (header row matches the canonical column headers).
4. **Invariant 1** (uniqueness): no duplicate Gen tags. ERROR.
5. **Invariant 2** (sort order): rows sorted by (prefix, int_suffix). ERROR.
6. **Invariant 3** (tag format): every Gen matches the regex. ERROR.
7. **Invariant 4** (boot date format): every Boot Date is YYYY-MM-DD. ERROR.
8. **Invariant 5** (retire date format): every Retire Date is date OR em-dash OR `[Session...]`. ERROR.
9. **Invariant 6** (predecessor closed): predecessor of any non-first row has retire-date populated. WARN (allows post-hoc reconciliation).

Implementation: `tropo-validate.py` v1.15.3+ extension — single function `validate_generation_log(filepath, fm) -> list[Finding]`. Walks the table; emits Findings with severity per invariant.

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author.*

**Tools available:**
- `python3 .tropo-studio/scripts/sort-gen-log.py <path>` — re-sort a gen-log; idempotent
- `python3 .tropo-studio/scripts/sort-gen-log.py <path> --check` — non-mutating drift detection (exit 0 = clean; non-zero = drift)
- `python3 .tropo/scripts/tropo-validate.py` — full structural validator including gen-log invariants (v1.15.3+)

**Skills:**
- [`write-gen-log-row.skill`](../skills/write-gen-log-row.skill.md) — the canonical write abstraction. Read predecessor → close if blank → append new row → call sort-gen-log.py at end. Returns invariant-pass signal or HALT.

**Procedures:**
- **Author a new row** — agents do not inline write prose. Boot/retirement playbooks call the skill; skill handles the row format and post-write sort. If you find yourself hand-editing a gen-log, stop and call the skill.
- **Recover from drift** — run `sort-gen-log.py --apply`. If invariants 1/3/4 (uniqueness/format) fail, investigate the row content; re-sorting only fixes order, not content drift.
- **Boot-drift detection** — Tier 3 boot extensions should invoke `sort-gen-log.py --check` before reading the gen-log tail. Catches drift surfaced from prior boots that didn't run the skill end-to-end.

**Rules (at-a-glance):**
1. Append-only at row scope (post-hoc reconciliation excepted)
2. Canonical path: `agents/<name>/generation-log.md`
3. Authoritative for identity (ADR-028: gen = last row + 1)
4. Skill is the write abstraction
5. Script is the executor
6. Boot-drift check at Group 1

**Pitfalls:**
- **Tail-read hides sort drift.** Reading only the last row to determine generation works for the current boot but masks structural drift. Run `--check` before tail-read. (Vela V42's 2026-05-08 forensic finding.)
- **Hand-editing the gen-log.** The skill exists to centralize write logic; per-agent prose variation is exactly how drift entered 4 times. Use the skill.
- **Post-hoc reconciliation without note.** Surfacing invariant-6 violations as expected (during recovery) is fine; doing it silently lets future generations confuse recovery for fresh drift. Note the reconciliation in the row's Key Contribution.

**Worked examples:**
- [Argus generation-log](../../vault/files/50dfd8a2.md) — reference shape; A1-A53 rows; v1.15.3 Stream E.i backfilled drift (A47/A48/A49 reordered).
- [Vela generation-log](../../vault/files/cb269071.md) — V1-V42; backfilled by Vela 2026-05-08 (V36/V37/V38/V39 inversions resolved).

**Go next:**
- Skill that mechanizes writes → [`write-gen-log-row.skill`](../skills/write-gen-log-row.skill.md)
- Script that the skill calls → `.tropo-studio/scripts/sort-gen-log.py`
- Validator that enforces → `tropo-validate.py` (v1.15.3+)
- Source thesis → [Vela c080a66d — Generation-log capsule-typing](../../vault/files/c080a66d.md)
- Brief that locked this capsule → [v1.15.3 design brief (9c4e7a2b)](../../vault/files/9c4e7a2b.md)

---

## Inheritance

Extends `core`. Inherits all core rules (UID uniqueness/immutability, type immutability, owner/created/modified invariants).

Note: `core` requires `uid:` in frontmatter, but the **gen-log files themselves don't carry frontmatter** (per current substrate). The capsule's `uid: 7f4a8d2e` is for the CAPSULE DEFINITION; gen-log file instances are governed by canonical-path detection rather than per-instance UID. v1.16+ may promote gen-logs to fully governed entries with frontmatter if integration with the typed-primitive substrate (rebuild-index, vault graph) earns its place.

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-05-09 | **LOCKED.** Initial version per v1.15.3 substrate-elevation cycle (composes Vela c080a66d Tier 2-3 thesis + Argus three augmentations). Schema (4-column table); 6 invariants (5 at ERROR + invariant 6 at WARN to allow post-hoc reconciliation); validator integration in tropo-validate.py at ERROR-from-day-one severity per Mike-A53 lock; skill abstraction at write-gen-log-row (UID c9b3e6f1); boot-drift check at Tier 3 Group 1 per Argus boot extension v1.15.3. Closes 4×-recurrence drift defect at substrate level. | argus-a53 + Mike Maziarz |

---

*generation-log capsule definition | LOCKED v1.0 (Argus A53, 2026-05-09; v1.15.3 substrate elevation; composes Vela c080a66d) | Tropo OS*
*"Three layers, one substrate. The drift becomes structurally impossible."*
