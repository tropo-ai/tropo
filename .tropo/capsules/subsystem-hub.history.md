---
subsystem_hub:
  - "2d083137"
uid: 17867222
type: capsule-history
governs: 8a4e21c5
governs_path: ".tropo/capsules/subsystem-hub.capsule.md"
extracted_at: 2026-05-11
extracted_by: argus-a55
extracted_in_release: pending-v1.18.0
extracted_in_cycle: "v1.18.0 — Capsule Library Phase 1"
schema_version: 2
governed_by: 5ec083a3   # capsule-history.capsule (v1.18.0 Stream C remediation)
extraction_scope: argo-private
member_of:
  - "8dd772a0"
  - "be5bc951"
tags: [capsule-history, extracted-from-subsystem-hub-capsule, v1.18.0-extraction]
---

# subsystem-hub — Capsule History

*Historical record extracted from the active capsule at v1.18.0 to keep the active body pedagogy-first per Lock C. Active capsule at `.tropo/capsules/subsystem-hub.capsule.md` (UID `8a4e21c5`). Preserves Change Log Entry Format examples + Adding-a-New-Subsystem protocol + Worked Example + Migration Note + Migration Window + Studio Shop Signage + v1.0→v1.1 + v1.1→v1.2 + v1.2→v1.3 Change Notes + lineage footer.*

---

## Change Log Entry Format (examples; canonical shape in active body §2)

Every hub Change Log entry:

```markdown
### v<release> — <ISO date> — Shipped

<list of shipped artifacts with UIDs + short descriptions>

**Impact:** <one- or two-sentence narrative of what the subsystem reader should know NOW that they didn't before.>

**Next:** <optional — what's queued for next release that readers should anticipate. Delete line if nothing queued.>
```

**Example** (v1.7 entry, hypothetical, for Tropo Governance):

```markdown
### v1.7 — 2026-05-XX — Shipped

- [subsystem-hub.capsule v1.2 → v1.3 (8a4e21c5)] — contract simplification + release_history + §Studio.
- [release.capsule v3.2 → v3.3 (b19e8d43)] — soft-gated enforcement rule (release blocks ship without registry entry per touched subsystem).
- [subsystem-registry.jsonl] — NEW append-only event log; primitive for documentation-as-release-deliverable enforcement.

**Impact:** Documentation-as-release-deliverable doctrine is now structural enforcement (soft-gated v1.7-v1.9; hard-gated v1.10). Subsystem hubs are concentrators, not archives.

**Next:** v1.8 picks Tropo Library canonical name (Documentation thesis); v1.10 ships the validator + hard-gates the registry rule.
```

---

## Adding a New Subsystem (protocol detail)

Six subsystems exist today (as of v1.4 lock; v1.17.0 added tropo-link = eighth). Adding a new subsystem follows this protocol:

1. **Propose** via the relevant pair channel. Name the proposed subsystem, the boundary tests against existing subsystems, the rationale.
2. **Crew decision** — lock the addition in writing.
3. **Create the hub stub** as a project-typed vault entry meeting the three Scope conditions + REQUIRED frontmatter and body sections. New hubs may start with `last_release_reflected: null` + `release_history: []`.
4. **Register in three places** (all three required for the hub to be discoverable + governed):
   - [`collections/subsystem-hubs.collection.md`](../../collections/subsystem-hubs.collection.md) — add to active-roster.
   - [`vault/00-index.jsonl`](../../vault/00-index.jsonl) — subsystem hubs are vault entries; rebuilder projects them automatically.
   - Cascade index — new file `00-cascade-<hub-uid>.jsonl` rooted at new hub OR include in existing cascade.
5. **First Change Log entry + `release_history` row + registry row** land on the next release that touches the new subsystem. At that point, set `last_release_reflected:` from `null` to the release semver.

---

## Worked Example — Minimum-Viable Hub (full)

Copy-paste starting point for a new subsystem hub:

```markdown
---
uid: <8-hex>
name: "<Display Name (ACRONYM)>"
type: project
state: active
lifecycle: standing
owner: <agent-name>
created: YYYY-MM-DD
created_by: <agent-generation>
modified: YYYY-MM-DD
modified_by: <agent-generation>
tags: [<short-acronym>, subsystem-hub]
member_of: [aae9a37b]
subsystem_name: "<lowercase-hyphen>"
subsystem_scope: "<≤200 char description: what this covers vs what it does NOT cover>"
last_release_reflected: null
release_history: []
aligned_with: 8a4e21c5
---

# <Display Name (ACRONYM)>

*<One-line italic strapline: who this is for and what reader question it answers.>*

## What This Subsystem Covers

<One paragraph naming scope + boundaries. What belongs here and — explicitly — what does NOT belong here. The boundary test against adjacent subsystems goes in the last sentence: "if the question is X, that is here; if the question is Y, it lives elsewhere.">

## How Tasks Flow

<One paragraph describing how tasks created in this subsystem reach release ships. Tasks carry `projects: [<this-uid>]` in frontmatter, surface on both this hub's board and the active release Drop board, ride a release for closure.>

## Current State

<3-6 sentences answering "where is this subsystem RIGHT NOW?" Anchored to `last_release_reflected:`. For a brand-new hub: name what's planned for the first release that touches the subsystem.>

## Change Log

*(no changes yet — first entry on next release)*
```

This minimum-viable form passes the contract: 4 REQUIRED body sections + REQUIRED frontmatter (including `release_history: []`).

---

## Migration Note — Pre-v1.3 Hub Shapes

Some pre-v1.3 hubs may exhibit shapes the v1.3+ contract doesn't directly anticipate:

- **Dual or nested Change Log surfaces.** A hub may have a `## Change Log` section AND additional release-impact prose under separate headers. v1.3 treats canonical `## Change Log` as authoritative; older nested surfaces stay as informal documentation.
- **Legacy header aliases.** `## What This Covers` is accepted alias for `## What This Subsystem Covers`. Some hubs use `## What's Current` — tolerated as informal; catch-up work normalizes to canonical `## Current State`.
- **Numbered or stylized headers.** Some hubs use `## 1. Section Name` style. Validator (v1.10) accepts canonical names with optional numeric prefixes.
- **Pre-v1.3 sections that v1.3 dropped from contract** (`## Key Decisions / ADRs` / `## Health Read` / `## Related Work`). These remain in instance bodies as informal documentation; the validator does not enforce shape on them.

The v1.3+ contract is forward-shape: new hubs follow it cleanly; existing hubs stay compliant via strip-and-tolerate without forced rewrite.

---

## Migration Window (subsystem_name uniqueness during merger)

When a subsystem is merged into another (e.g., TBS into TAS, or TLGS into Library), the `subsystem_name` global uniqueness rule (Governance Rule 1) admits a temporal exception:

- The successor hub may share `subsystem_name:` with the superseded hub for **up to one release cycle** during the migration.
- During the migration window:
  - The **superseded hub freezes** — `last_release_reflected:` does not update; no new Change Log entries; no new `release_history` rows; `state: archived` AND `superseded_by: <successor-uid>` set on the same commit that creates the successor.
  - The **successor hub is the sole owner of forward updates** — `last_release_reflected:` advances on it; new Change Log entries + `release_history` rows + registry rows land on it.
- At the close of the migration window (no later than the next release boundary), the superseded hub MUST have `state: archived` and the successor MUST be the sole `subsystem_name:` holder.

The validator's uniqueness check (v1.10) ignores hubs with `state: archived` or `superseded_by:` set.

---

## Studio — Shop Signage (extracted from prior active body)

*Quick-reference section dropped from active body at v1.18.0 refactor per Mike-A55 directive 2026-05-11 — capsules are agent-read substrate; quick-reference for humans is not the load-bearing use case.*

**Tools:** [`subsystem-registry.jsonl`](../../subsystem-registry.jsonl) (vault-wide append-only cross-cut); [`collections/subsystem-hubs.collection.md`](../../collections/subsystem-hubs.collection.md) (live roster); `vault/00-index.jsonl` (query `type: project AND tags includes subsystem-hub AND state != archived`); cascade indexes (`00-cascade-<hub-uid>.jsonl`); `shared/orientation/daily-health-report.md` (health record — replaces dropped `## Health Read`); `vault/00-graph-index.json` (relationship record — replaces dropped `## Related Work`); ADR set (replaces dropped `## Key Decisions / ADRs`); `scripts/validate-subsystem-hubs.ts` DEFERRED to v1.10.

**Skills:** [`groom-subsystem-hub.skill.md`](../skills/groom-subsystem-hub.skill.md) (NEW v1.7 — sa.hub-groomer swarm); `author-subsystem-hub.skill.md` (forthcoming v1.5); `update-hub-changelog.skill.md` (forthcoming v1.5).

**Procedures:**
- **Add a new subsystem** — propose via pair channel → crew decision → author hub stub → run `rebuild-vault.py --apply` → add to collection roster → first §Change Log + `release_history` + registry row on next release ship
- **Update on every release ship** — at release close, BEFORE release entry filed (Ship Gate): append §Change Log entry; append `release_history` row; append `subsystem-registry.jsonl` row; update §Current State; update §Open Questions / §Architectural Constraints if present; bump `last_release_reflected:`
- **Verify hub health** — until v1.10, run `rebuild-vault.py --apply` for index consistency; cross-check `last_release_reflected:` vs `.tropo/version.md` manually
- **Merge / supersede a subsystem** — atomic commit: successor gains `supersedes: [<predecessor-uid>]`; predecessor flips `state: archived` + `superseded_by: <successor-uid>`

**Pitfalls** (full list preserved here; active body §4 has summary):
- Hub missing `lifecycle: standing` — validator ERROR
- `tags:` missing `subsystem-hub` — validator ERROR
- `member_of:` missing `aae9a37b` — validator ERROR + ADR-035 Surface 2 violation
- `release_history:` field missing from frontmatter — contract violation
- Two active hubs sharing `subsystem_name:` — validator ERROR (outside Migration Window)
- `superseded_by:` set but `state: active` — stuck migration
- `last_release_reflected:` more than one minor version behind current vault — validator WARNING
- `release_history:` row pointing at unresolvable `registry_uid` — validator ERROR
- Editing prior §Change Log or `release_history:` entries — Rule 3 violation
- §Current State claiming further-along state than reality — Rule 5 + Operating Principle 3 violation
- Re-introducing `## Key Decisions / ADRs` / `## Health Read` / `## Related Work` as required — these were dropped intentionally; underlying primitives are canonical

**Worked examples:**
- [Tropo Work hub (2d083137)](../../vault/files/2d083137.md) — canonical hub shape
- [Tropo Playbooks hub (76bab75f)](../../vault/files/76bab75f.md) — canonical Change Log demonstration
- [Tropo Library hub (1aba710c)](../../vault/files/1aba710c.md) — v1.7 Stream D scope reframe target
- [Tropo Link hub (3a207ed3)](../../vault/files/3a207ed3.md) — NEW v1.17.0; eighth subsystem
- Live roster: [`collections/subsystem-hubs.collection.md`](../../collections/subsystem-hubs.collection.md)

---

## v1.0 → v1.1 Change Notes

Authored by Argus A29 at v1.0 (2026-04-20); revised by Argus A30 at v1.1 (2026-04-20) following swarm review by sa.skeptic + sa.arch-specs. UID preserved at `8a4e21c5`.

**Substantive deltas:**
1. REQUIRED body sections reduced from 7 to 3 to match current practice.
2. EXPECTED-IF-PRESENT category introduced for 6 sections that v1.0 had as REQUIRED-but-aspirational.
3. `last_release_reflected:` promoted to REQUIRED (was optional; internal contradiction with §Hub Update Discipline).
4. §Current Instances enumeration removed (replaced with pointer to collection roster).
5. §Hub Update Discipline rewritten with explicit enforcement honesty.
6. §Adding a New Subsystem protocol added.
7. §Bootstrapping (Fresh Vaults) added.
8. §Migration Window added.
9. §Known Enforcement Gaps added.
10. §Conscious Trade-offs added.
11. §Validation Checks rewritten for new model.
12. `migration_target:` is semver, not calendar.

---

## v1.1 → v1.2 Change Notes

**v1.2 (2026-04-25, Argus A34) — Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop).** Added §Studio — Shop Signage section per the v3 capsule shop-signage pattern. Added Relations Header right after H1. Frontmatter `composes_with: 34e4cb0b` + `pattern_family: 34e4cb0b` declared. No semantic changes. UID preserved at `8a4e21c5`.

---

## v1.2 → v1.3 Change Notes

**v1.3 (2026-05-05, Argus A45) — Substantive simplification + integration with release.capsule v3.3 enforcement.** Authored as Stream A1 of v1.7 release plan. Implements four decisions from v1.7 brief: D1 (validator deferral), D2 (release_history bidirectional with registry), D4 (contract strip), D8 (capsule amendment scope = core + §Studio).

**Substantive deltas (v1.2 → v1.3):**

1. **Contract stripped** — three EXPECTED-IF-PRESENT sections removed entirely: `## Key Decisions / ADRs` (ADR set IS the historical record), `## Health Read` (`shared/orientation/daily-health-report.md` IS the health record), `## Related Work` (`vault/00-graph-index.json` IS the relationship record). Removing these eliminates 18 ERROR-class violations across 6 active hubs.

2. **`## Current State` promoted from EXPECTED-IF-PRESENT to REQUIRED.** Load-bearing answer to truth-today reader question.

3. **`## Open Questions` + `## Architectural Constraints` demoted to OPTIONAL.** No `migration_target:` enforcement.

4. **`release_history:` REQUIRED frontmatter array added.** Append-only event log; bidirectional pair with [`subsystem-registry.jsonl`](../../subsystem-registry.jsonl).

5. **§Pending Sub-Requirements added** (per playbook.capsule v2.4 pattern). Three deferrals declared: validator (→ v1.10), Required Frontmatter rigorization (→ v1.8), Tropo Library canonical naming (→ v1.8).

6. **§Validation Checks rewritten + deferred to v1.10.** Old checks 5+6 (EXPECTED-IF-PRESENT shape + migration_target enforcement) removed. New check 6 added: `release_history` consistency.

7. **§Workshop signage updated** for v1.3 contract. Pitfalls section adds "Re-introducing dropped sections as required" warning.

8. **§Hub Update Discipline updated** to reference `release_history:` row authoring + registry row + soft-gate-to-hard-gate transition.

9. **§Conscious Trade-offs removed** (folded into §Pending Sub-Requirements).

10. **§Known Enforcement Gaps removed** (folded into §Pending Sub-Requirements per cleaner playbook.capsule v2.4 pattern).

**UID preserved at `8a4e21c5`.** Every hub's `aligned_with: 8a4e21c5` back-reference remains valid.

**Three-instrument verification (v1.3) — Round 1 BATCH 2026-05-05:**
- **sa.arch-specs** [record 035](../../agents/sa/sa.arch-specs/activation-log/035-argus-a45-record.md) — PASS-WITH-FINDINGS (1 P0 + 4 P1 + 3 P2 + 1 drift)
- **sa.skeptic** [record 035](../../agents/sa/sa.skeptic/activation-log/035-argus-a45-record.md) — PASS-WITH-FINDINGS (1 P0 + 7 P1 + 6 P2). Cross-cutting calibration finding: rhetorical confidence outran structural enforcement.
- **sa.cold-boot** [record 127](../../agents/sa/sa.cold-boot/activation-log/127-argus-a45-v1.7-subsystem-hub-v1.3.md) — PASS-WITH-FINDINGS (5 P1, ceremony 2/3/1)

**Bundled remediation (Round 1 fold, 2026-05-05).** Both P0s + most P1s folded inline per A35 fold-findings-into-pre-lock pattern.

**Round 2 regression — single-instrument sa.cold-boot 2026-05-05** [record 128](../../agents/sa/sa.cold-boot/activation-log/128-argus-a45-v1.7-subsystem-hub-v1.3-regression.md): **REGRESSION-PASS-WITH-FINDINGS** (lock recommended). status:draft → status:locked at 2026-05-05.

---

## v1.3 → v1.4 Change Notes (extracted from prior active preamble)

**v1.4 (2026-05-05, Argus A46) — derivation amendment per v1.8 brief fd2d9e77.** Additive non-breaking. **`release_history:` row population is now DERIVED from query at release ship** — for releases dated ≥ v1.8.0 ship, each touched-subsystem hub gets a `release_history:` row generated from the release entry's `subsystems_touched:` derived field (which itself derives from `capabilities_touched:` via 1-hop `member_of:` graph traversal per release.capsule v3.4 Rule 12). Per-hub `release_history:` no longer authored independently — it's one face of the same query result that produces `subsystem-registry.jsonl` rows. Drift between hub-side and registry-side becomes structurally impossible.

Hub authors STILL write `## Current State` body sections + Change Log entries (content; not derivable from frontmatter).

**§Pending Sub-Requirements row 2 (Required Frontmatter rigorization deferred to v1.8) CLOSED** — capability-side rigor in v1.8 satisfies the rigorization scope; remaining hub-side rigor folds into v1.10 Enforcement validator.

**§Pending Sub-Requirements row 3 (Tropo Library canonical naming deferred to v1.8) PUNTED to v1.9** — Documentation 7th-subsystem question requires empirical input from v1.8 Stream E1 placeholder audit; v1.8 ships with documentation-class capabilities at `member_of: [1aba710c]` placeholder.

Two new rows added: section-content-freshness explicitly tied to v1.10 + capability-completeness as v1.10 Enforcement target. UID `8a4e21c5` preserved.

---

## v1.4 → v1.5 Change Notes

**v1.5 (2026-05-11, Argus A55) — v1.18.0 Stream B body refactor.** Body restructured to 5-section canonical structure (Intent → Schema → State Machine → Validation Rules → Composes-With) per v1.18.0 brief §4.1 Q3-locked pattern. Historical content (Change Log Entry Format full examples + Adding-a-New-Subsystem protocol full detail + Worked Example + Migration Note pre-v1.3 + Migration Window + Studio Shop Signage + v1.0→v1.1, v1.1→v1.2, v1.2→v1.3, v1.3→v1.4 Change Notes + v1.4 preamble paragraph + lineage footer) extracted to this `.history.md` companion file (UID `17867222`).

Active body trimmed from 537 → ~285 lines (~47% reduction); all historical content preserved in this file. `history_file:` + `last_body_refactor:` frontmatter fields added. No semantic changes to §Governance Rules / §State Machine / §Schema content; pure restructure + extraction. UID preserved at `8a4e21c5`.

---

## Lineage footer (extracted from prior active body)

*subsystem-hub Capsule Definition | v1.4 LOCKED 2026-05-05 by Argus A46 | v1.8 Stream A3 — release_history derivation per release.capsule v3.4 Rule 12 + 3 §Pending Sub-Requirements rows closed (Required Frontmatter rigorization + Tropo Library canonical naming + registry_uid Stream A5 dependency) + 2 new rows added (Capability completeness + Hub-side current_state body validation) + §Hub Update Discipline §Enforcement language updated for derivation discipline; UID 8a4e21c5 preserved; pending Stream F gauntlet | v1.3 LOCKED 2026-05-05 by Argus A45 — contract simplification + release_history + §Pending Sub-Requirements + 3-instrument BATCH-folded + Round 2 regression PASS*

*v1.2 lock 2026-04-25 by Argus A34 preserved in git history. v1.1 lock 2026-04-20 by Argus A30 preserved. v1.0 by Argus A29 (2026-04-20). UID `8a4e21c5` preserved across v1.0 → v1.1 → v1.2 → v1.3 → v1.4 → v1.5.*

*"The hub is where a reader answers 'what is this subsystem TODAY?' — not by reading every file, but by reading this. Concentrator, not archive."*

---

## Provenance

- Extracted: 2026-05-11
- Extracted by: argus-a55
- Extracted in cycle: v1.18.0 Stream B (Capsule Library Phase 1)
- Active capsule version at extraction: v1.4
- Active capsule version after extraction: v1.5 (non-breaking; body-only refactor)
- Extraction-fidelity check: every Change Log Entry Format example + Adding-a-New-Subsystem protocol + Worked Example + Migration Note + Migration Window + Studio Shop Signage + v1.0→v1.1 + v1.1→v1.2 + v1.2→v1.3 + v1.3→v1.4 amendment notes preserved in this file.

---

*subsystem-hub capsule history | UID `17867222` | extracted from `8a4e21c5` | v1.18.0 Stream B extraction 2026-05-11*
