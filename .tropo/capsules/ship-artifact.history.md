---
uid: 437e8944
name: "ship-artifact-history"
type: capsule-history
governs: eeb59ddf
governs_path: .tropo/capsules/ship-artifact.capsule.md
extracted_at: 2026-05-11
extracted_by: argus-a56
extracted_in_cycle: "v1.19.0 — Convergence Phase 1"
extracted_in_release: pending-v1.19.0
schema_version: 2
governed_by: 5ec083a3
extraction_scope: argo-private
member_of:
  - "8dd772a0"   # tropo-governance
tags: [capsule-history, extracted-from-ship-artifact-capsule, v1.19.0-stream-c]
---

# ship-artifact — Capsule History

*History extracted from ship-artifact.capsule v1.1.4 → v1.2 body refactor (v1.19.0 Stream C; 2026-05-11). Active capsule preserves: Required+Optional Frontmatter, §Source Modes (6 modes + override-child shapes + skip applicability — substrate-load-bearing), §Cleanup Rules + cross-reference forms table, §State Machine, 12 Governance Rules, 23 Validation Checks, §5 Composes-With. This file preserves: v1.0 / v1.1 / v1.1.1-v1.1.4 amendment-block opener prose, §Conscious Trade-offs section (5 entries), §Known Enforcement Gaps table, §Studio — Shop Signage human-facing quick-ref, full Relationship-to-Other-Capsules narrative, Inheritance section, full changelog.*

---

## Amendment Blocks (extracted from v1.1.4 active body opener)

### v1.1 (2026-04-25, Argus A34)

Gate D2.1.A three-instrument remediation pass. 3 P0s closed (Rule 5 composition asymmetry; `skip` semantics; manifest root UID resolution path). 9 high-leverage P1s folded in same-session (extraction_scope namespace tri-lens convergence; output_path collision effective-vs-declared; code-fence parser model; wikilink/bare-UID handling; fast-path state-machine transition; member_of in Required Frontmatter; purpose/description duplication resolved; folder-mode mkdir; atomic-commit for cross-referenced authoring). 5 P1 polish + 10 P2s carved as documented gaps. v1.0 is now-history; v1.1 is the lock-candidate. Status: draft pending sa.cold-boot 085 regression.

### v1.0 (2026-04-25, Argus A34)

Initial version. Implemented V33's [Release Structure as Graph design brief (7b42d916)](../../vault/files/7b42d916.md) per the 7 locked decisions in §6 of [Stream 2 D2.1 project-plan (4e5a2011)](../../vault/files/4e5a2011.md). Three-instrument verification surfaced the v1.1 amendment set; sa.arch-specs 017 / sa.skeptic 015 / sa.cold-boot 084 records on file.

### v1.1.1-v1.1.4 patch series (2026-04-25, Argus A35)

Phase D.A-D.E close-out patches per arch-spec [747c33c9 §3.4](../../vault/files/747c33c9.md) capsule version drift policy (mechanical, non-breaking).

- **v1.1.1 (D.A bootstrap):** `manifest_root_uid: TBD` → `manifest_root_uid: b2e7d4a9` (the newly-authored "Tropo Release Structure" evergreen project). Atomic commit per Rule 12 (capsule patch + project authoring landed together).
- **v1.1.2 (D.D dry-run finding):** Check 4 exception extended to `source_mode: structure-only`. Surfaced when D.D dry-run reader caught 2 P0s on `decisions/` and `system/` folder ship-artifacts whose canonical_source paths don't exist in argo by design.
- **v1.1.3 (D.E sa.cold-boot 088 polish):** illustrative example `parent:` clarification — required so override-child mechanism fires correctly for root-doc relocations.
- **v1.1.4 (D.E close-out polish):** trailing slash convention, two new pitfall rows (wrong parent for override-child relocation + canonical-remap subtree without output_path), §Worked examples added canonical-remap subtree pattern.

---

## Conscious Trade-offs (extracted)

### Single capsule type with `kind:` discriminator vs separate folder/file capsules

V33's brief proposed a single `ship-artifact` capsule with `kind: folder | file` discriminator. This v1.0 honors that — one capsule, one validator, one body shape. Folder-only fields (`children:`) and file-only fields (`output_path:`, `cleanup_rules:`) are ignored on the wrong kind without error.

**Rationale.** Two separate capsules would double the governance surface for marginal benefit. A single capsule with kind-discrimination matches the brief, the validator, and the build script — three cleaner surfaces.

**Reversal cost:** split into two capsules; migrate existing entries (~150-200 at v1.4 ship); ~4-6 hours mechanical work. Not blocking; reversible.

### `recursive-ship-all` + per-file overrides composition

The kernel ships via one folder-manifest entry with `recursive-ship-all`; per-file entries with `output_path:` overrides relocate specific files (Decision 4). This composes cleanly but introduces composition-validation complexity — the validator must check that a per-file override's `canonical_source:` actually falls under its parent's recursive tree.

**Rationale.** ~98% manifest-entry reduction over per-file enumeration; cost is a single composition-validation rule. Worth it.

**Reversal cost:** ~500 manifest entries instead of ~10 + the recursive parent. ~6-8 hours mechanical authoring. Reversible.

### `release-only` markers ship to the recipient as visible source

`release-only` blocks remain in the release output WITH their HTML comment markers (per Decision 1's strip rules). Recipients see the markers in source view; rendered output hides them.

**Rationale.** Self-documenting — recipients learn the convention by encountering it. Stripping the markers (showing only the content) would hide the convention from learners.

**Reversal cost:** amend `cleanup_rules:` to add `strip_release_only_markers: true`; update build-release.py. ~15 min mechanical.

### Validator is L2 (Python) not L1 (markdown)

Per Decision 7 + Mike's L1/L2 framing: the validator script is acceleration tooling, not L1 contract material. The capsule (this file) is L1; the validator that enforces the capsule is L2.

**Rationale.** Validation work is mechanical (UID resolution, path checks, enum validation, link traversal); deterministic Python is the right tool. The L1 thesis is preserved — manifest entries + capsules are markdown; the validator is L2.

**Reversal cost:** very expensive (would require LLM-based interpretation of every check). Not worth considering.

### No mechanical enforcement in v1.4 of every honor-system check

Several validation checks (17, 18) are honor-system at v1.4 — substance of `purpose:` / `description:` / cleanup notes. v1.4 ships the capsule + validator with mechanical enforcement of the [enforced] subset; the [honor-system] subset is documented at v1.4 + relies on cold-boot review during Phase D sprint.

**Rationale.** Mechanical enforcement of "is this prose substantive?" is itself an LLM judgment call (Decision 7's L2 framing) and over-rotates to LLM-in-build-pipeline. Honor-system at v1.4 + cold-boot during Phase D is sufficient.

**Reversal cost:** add LLM-judgment validation step to the validator. Already on the v1.5 path.

---

## Known Enforcement Gaps (extracted)

| Gap | What closes it | Target release | Owner |
|---|---|---|---|
| Validator script `.tropo/scripts/validate-release-manifest.py` not authored at capsule lock | Phase E build-release.py rewrite; separate session arc, likely Talos-lane | 1.4.0 | argus + talos |
| Orphan/zombie scanner not authored | Same — Phase E deliverable | 1.4.0 | argus + talos |
| `cleanup_rules:` parser not authored | Same — Phase E (build-release.py) | 1.4.0 | argus + talos |
| Sub-file marker code-fence boundary handling not implemented | Phase E (arch-spec specifies CommonMark + GFM model; implementation follows) | 1.4.0 | argus + talos |
| Sa.* wrapper for interactive triage not authored | Deferred to v1.5+ per Decision 7 | 1.5.0 | argus or vela |
| `--check-external` URL HEAD check flag not implemented | Optional v1.5+ enhancement | 1.5.0 | engineering lane |
| Initial manifest (~150-200 ship-artifact entries) not yet authored | Phase D sprint per [4e5a2011] §2 Phase D + Decision 5 | 1.4.0 | argus + mike |
| `manifest_root_uid: TBD` in capsule frontmatter — Check 14 honor-system until Phase D creates the Tropo Release Structure project | ✅ **RESOLVED 2026-04-25 by v1.1.1 patch** — Phase D.A bootstrap atomic commit landed b2e7d4a9 + capsule patch in one commit per Rule 12. Frontmatter `manifest_root_uid:` now resolves to `b2e7d4a9`. Mechanical enforcement of Check 14 still awaits Phase E validator. | 1.4.0 | argus + mike |
| `pattern_exemplar: d0c00001` declaration accuracy — ship-artifact's lifecycle (`draft → reviewed → locked → archived`) is closer to build.capsule + arch-spec.capsule than to document.capsule's `draft → published → archived`. The pattern_exemplar declaration is convention-conformance per v3 Decision 3, not strict pattern-following. | v1.5 amendment (or earlier if cross-capsule pattern_family taxonomy lands) | 1.5.0 | argus |
| `release-only` marker stripping behavior at v1.1 keeps markers in release output (self-documenting); v1.5+ may add `cleanup_rules.strip_release_only_markers: true` option | Optional v1.5+ amendment if recipient experience surfaces friction | 1.5.0 | argus |

---

## Studio — Shop Signage (extracted)

*Preserved per Mike-A55 directive: capsules are agent-read, not human-read. Active capsule §5 Composes-With teaches the type to the agent; this section preserved the workflow guide to a human author.*

### Tools available

- `vault/00-index.jsonl` — grep `type: ship-artifact` to inventory existing entries before authoring; check for `canonical_source:` collisions
- `.tropo/scripts/validate-release-manifest.py` *(forthcoming Phase E)* — orphan/zombie scanner + manifest health check
- `.tropo-studio/scripts/draft-ship-manifest.py` *(forthcoming Phase D Sprint)* — one-time helper that walks v1.3.1's release tree + emits draft ship-artifact entries
- [Release Structure as Graph design brief (7b42d916)](../../vault/files/7b42d916.md) — V33's authoritative source for the design intent
- [Stream 2 D2.1 project-plan (4e5a2011)](../../vault/files/4e5a2011.md) §6 — the 7 locked decisions backing this capsule
- `releases/v1.3.1/builds/tropo-os-v1.3.1/` — the v1.3.1 release tree; reverse-engineer manifest entries from this baseline

### Skills

- `author-ship-artifact.skill.md` *(forthcoming v1.5)* — scaffold frontmatter + `## Purpose` + `## Description` from a target argo path
- `validate-ship-artifact.skill.md` *(forthcoming v1.4 Phase E)* — wraps the CLI validator for in-session use during manifest authoring

### Procedures

- **Author a ship-artifact** — verb: author per v3 Decision 13. Determine `kind:` (folder vs file); set `canonical_source:` to the argo path; pick `source_mode:` based on §Source Modes table; set `extraction_scope:`; set `parent:` to the containing folder ship-artifact's UID; write `## Purpose` + `## Description` body sections; commit at `status: draft`.
- **Lock a ship-artifact** — verb: lock per v3 Decision 13. Run the validator (Phase E forthcoming); confirm orphan/zombie scanner PASS; transition `draft → reviewed → locked` (or `draft → locked` fast-path for trivial mirror entries — document fast-path rationale in `## Notes`); set `locked_by:` + `locked_at:`.
- **Supersede** — verb: supersede per v3 Decision 13. Author successor at `status: locked` with `supersedes: <old-uid>`; flip predecessor to `state: archived` + set `superseded_by: <new-uid>`. Atomic commit per Rule 9.
- **Migrate from v1.3.1 baseline** — verb: migrate per v3 Decision 13. Run `draft-ship-manifest.py` (Phase D Sprint); review surfaced edge cases; finalize entries.
- **Validate** — verb: verify per v3 Decision 13. Run `validate-release-manifest.py` against the live manifest; fail-loud on any violation per Decision 2.

### Pitfalls

- Authoring a ship-artifact without `member_of: <Tropo Release Structure UID>` → Rule 1 / Check 14 violation
- `canonical_source:` references a non-existent argo path → Rule 2 / Check 4 violation
- Two entries with the same `output_path:` → Check 9 collision
- Folder-only `source_mode:` (e.g., `recursive-ship-all`) on `kind: file` entry → Check 5 violation
- Adding to `argo-os/.tropo/` without expecting it to ship — kernel uses `recursive-ship-all`; new files auto-ship
- HTML comment markers inside code-fences treated as strip directives → Decision 1 implementation; build-release.py respects code-fence boundaries
- Setting `output_path:` for a file under a `recursive-ship-all` parent without realizing the override
- Cycle in `parent:` chain → Rule 10 / Check 16 violation
- Locking a ship-artifact that references a draft canonical-source-bearing arch-spec — ship-artifacts can reference any argo path; argo's contents lock independently. The pitfall is reverse: locking ship-artifact then later moving the canonical_source path = stranded entry; use supersession (Rule 9).
- **(v1.1.4)** Parenting a `direct-copy` override at root sentinel instead of the `recursive-ship-all` kernel parent — relocation overrides whose `parent:` is the root sentinel don't trigger the override-child mechanism per §Source Modes "Override-child shapes" table. Result: recursive parent still mirrors the file at its canonical-source path AND the override emits at output_path → file ships at TWO recipient paths. Different effective paths so Check 9 doesn't flag the duplication, but structurally wrong.
- **(v1.1.4)** Authoring a canonical-remap subtree without setting `output_path:` on the folder entry — the entry's `description:` may CLAIM the remap, but without an explicit `output_path:` the entry defaults to mirror its `canonical_source` minus `argo-os/` prefix, emitting at the kernel-mirror path NOT at the intended recipient folder.

### Worked examples

- **Folder ship-artifact (illustrative — kernel):** `kind: folder, source_mode: recursive-ship-all, canonical_source: argo-os/.tropo/, output_path: .tropo/, extraction_scope: ship`. One entry covers the entire kernel tree.
- **File ship-artifact (illustrative — relocation):** `kind: file, source_mode: direct-copy, canonical_source: argo-os/.tropo/templates/root-docs/README.md, output_path: README.md, extraction_scope: ship, parent: <UID-of-.tropo-folder-ship-artifact>`. **`parent:` MUST be the `.tropo/` folder ship-artifact (a `recursive-ship-all` parent), NOT the root sentinel** — required so the override-child mechanism per §Source Modes "Override-child shapes" table fires correctly.
- **File ship-artifact (illustrative — with cleanup):** a `channels/CAPSULE.md` entry might carry `cleanup_rules: {strip_markers: true, broken_link_policy: fail-loud}` if the file contains `argo-only` blocks.
- **Skip override (illustrative):** `kind: file, source_mode: skip` under a `recursive-ship-all` parent, used to exclude one specific file from a homogeneous tree. `## Purpose` MUST document the reason.
- **(v1.1.4) Canonical-remap subtree (illustrative — Mike's call A pattern):** when a folder needs to ship to recipient at one location BUT its canonical content lives elsewhere in argo (typically under `.tropo/templates/<skeleton>/`), use `recursive-ship-all` with explicit `output_path:` override. Example for shipping `.tropo-studio/` skeleton: `kind: folder, source_mode: recursive-ship-all, canonical_source: argo-os/.tropo/templates/.tropo-studio-skeleton/, output_path: .tropo-studio/, extraction_scope: ship, parent: <root-sentinel-UID>`. Note `parent:` is the root sentinel (NOT the `.tropo/` recursive-ship-all kernel) — intentional. Result: intentional dual-ship — content emits at recipient `.tropo/templates/.tropo-studio-skeleton/<file>` (via kernel recursive-ship-all mirror) AND at recipient `.tropo-studio/<file>` (via this entry's output_path remap). Different effective paths; Check 9 PASSES.

### Go next

- Upstream design intent → [Release Structure as Graph (7b42d916)](../../vault/files/7b42d916.md)
- Decision rationale → [Stream 2 D2.1 project-plan §6 (4e5a2011)](../../vault/files/4e5a2011.md)
- Validator + build implementation → [Build-Release Pipeline arch-spec v1.0 (747c33c9)](../../vault/files/747c33c9.md)
- Hardening pattern precedent → [ADR-035 Declared-Presence (a7c4e5b2)](../../vault/files/a7c4e5b2.md)
- Pattern exemplar → [document.capsule v3.1 (d0c00001)](document.capsule.md)
- Pillar 1 build/release siblings → [build.capsule (b3d7e5a1)](build.capsule.md), [release.capsule (b19e8d43)](release.capsule.md)
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Relationship to Other Capsules — Narrative (extracted)

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor (UID immutability, type immutability, owner / created / modified invariants).
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.
- **[document.capsule v3.1 (d0c00001)](document.capsule.md)** — pattern exemplar per v3 Decision 3. ship-artifact patterns on document.capsule with the additional discipline layer of: (a) graph-shape enforcement (parent + children + acyclicity), (b) path resolution at lock time, (c) source_mode enum + behavior contracts, (d) cleanup_rules + marker handling, (e) build-time integration with the validator.
- **[build.capsule v2.1 (b3d7e5a1)](build.capsule.md)** — sibling at the build/release infrastructure layer. Builds package versioned software; ship-artifacts declare what goes IN to a build's output.
- **[release.capsule v3.0 (b19e8d43)](release.capsule.md)** — sibling at the build/release infrastructure layer. Releases record what shipped; ship-artifacts declare what's shippable.
- **[release-plan.capsule v1.0 (a3f1e7b2)](release-plan.capsule.md)** — coordination precedent. A release plan coordinates a release; ship-artifacts coordinate the manifest within that release's build.
- **[playbook.capsule v2.1 (e7b3c509)](playbook.capsule.md)** — pattern precedent for the §Studio + Relations Header convention.
- **[project-plan.capsule v1.1 (f7b9c4a2)](project-plan.capsule.md)** — governs [Stream 2 D2.1 project-plan (4e5a2011)](../../vault/files/4e5a2011.md), which is the project-plan that delivers this capsule.

---

## Inheritance

Extends `core`. Inherits UID immutability, type immutability, owner / created / modified invariants.

Not currently extended by subtypes. Future subtypes are possible (e.g., `ship-artifact-with-templating` for files that need templating-engine processing beyond simple marker stripping); none exist at v1.0.

---

## Changelog (full lineage)

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-04-25 | Initial version. DRAFT pending three-instrument verification (Gate D2.1.A). Implements V33's Release Structure as Graph design brief per the 7 locked decisions: single capsule with `kind: folder | file` discriminator; `.tropo/templates/root-docs/` + `.tropo/templates/ide-configs/` for relocations; `recursive-ship-all` for `.tropo/` + per-file `output_path:` overrides; HTML comment markers `argo-only` + `release-only`; fail-loud broken-link policy; CLI validator + build-release.py step ownership; v1.3.1-as-template manifest authoring mechanism; script-drafted + human-reviewed migration ordering. 18 validation checks (16 [enforced] + 2 [honor-system]). 6 source modes. UID `eeb59ddf` (preserved across all future amendments). | argus-a34 |
| 1.1 | 2026-04-25 | Gate D2.1.A three-instrument remediation pass. Sa.arch-specs 017 + sa.skeptic 015 + sa.cold-boot 084 returned 3 P0 + ~14 P1 + ~10 P2. All 3 P0s closed: P0-1 Rule 5 composition asymmetry (Override-child shapes table + Check 20); P0-2 `skip` semantics (When `skip` applies subsection + Check 21); P0-3 manifest root UID resolution (`manifest_root_uid:` capsule frontmatter field + Rule 1 + Check 14). 9 high-leverage P1s folded. 5 P1 polish + 10 P2s carved as documented gaps. Validation Checks expanded to 23. State Machine valid transitions expanded. Governance Rules expanded to 12. UID `eeb59ddf` preserved. | argus-a34 |
| 1.1.1 | 2026-04-25 | Phase D.A bootstrap patch — `manifest_root_uid: TBD` → `manifest_root_uid: b2e7d4a9` (Tropo Release Structure evergreen project). Atomic commit per Rule 12 (capsule patch + project authoring landed together). UID `eeb59ddf` preserved. | argus-a35 |
| 1.1.2 | 2026-04-25 | Phase D.D dry-run finding — structure-only Check 4 exception. Extends Check 4's skip exception to also cover `source_mode: structure-only`. Both Rule 2 governance prose AND Validation Check 4 enforcement annotation updated. UID `eeb59ddf` preserved. | argus-a35 |
| 1.1.3 | 2026-04-25 | Phase D.E sa.cold-boot 088 polish — illustrative example `parent:` clarification. §Studio "File ship-artifact (illustrative — relocation)" example now explicitly shows `parent:` MUST be the `.tropo/` folder ship-artifact (recursive-ship-all parent), NOT the root sentinel. UID `eeb59ddf` preserved. | argus-a35 |
| 1.1.4 | 2026-04-25 | Phase D.E close-out polish — three Studio additions: (1) `canonical_source` row clarification — trailing slash on folder paths is convention, not enforced; (2) §Pitfalls — added two new pitfall rows ("wrong parent for override-child relocation" + "canonical-remap subtree without output_path"); (3) §Worked examples — added "Canonical-remap subtree (illustrative — Mike's call A pattern)" worked example. UID `eeb59ddf` preserved. | argus-a35 |
| 1.2 | 2026-05-11 | **v1.19.0 Stream C — Capsule Pedagogy Completion.** Body refactor to 5-section pedagogy pattern (Intent → Schema → State Machine → Validation Rules → Composes-With) per Mike-A55 *"capsules are agent-read, not human-read"* directive. Active body reduced from 519 → ~290 lines (~44% reduction). Substrate-load-bearing content preserved in active: Required+Optional Frontmatter, §Source Modes (6 modes + override-child shapes + skip applicability), §Cleanup Rules + cross-reference forms table, §State Machine, 12 Governance Rules, 23 Validation Checks. Extracted to history: v1.0/v1.1/v1.1.1-v1.1.4 amendment-block opener prose, §Conscious Trade-offs (5 entries), §Known Enforcement Gaps table, §Studio quick-ref, Relationship-to-Other-Capsules narrative, Inheritance section, full changelog. **No schema changes, no validation rule changes, no governance rule changes.** Bidirectional pointer pair: active capsule `history_file: 437e8944` ↔ this file's `governs: eeb59ddf`. UID `eeb59ddf` preserved. | argus-a56 |
| 1.3 | 2026-05-18 | **v1.42.0 — Multi-Target Extraction.** Adds always-array `target:` field (default implicit `[release]`; new value `web`); converts `manifest_root_uid:` from scalar to per-target map; introduces per-target `cleanup_rules` defaults; new `cleanup_rules.uid_rewrite_template:` field; Rule 1 + Rule 10 target-aware restatement (dual-root graph governance per-target subgraph); new Validation Check 24 (target enum validity; ERROR at v1.3 directly). Entry-level backward-compat 100% (existing entries continue valid; absent `target:` field implies `[release]`). Capsule-reader migration atomic-commit: all readers of `manifest_root_uid:` (build-release.py + validate-release-manifest.py + .tropo-studio/scripts/dry-run-manifest.py) updated in same git commit as this amendment. Migration narrative preserved as Migration 1 in §Schema Migrations above. Unblocks Talos web-deploy-3 (hosted-blog at /agentic-builders/) which held pending substrate-class extraction discipline for web target. UID `eeb59ddf` preserved. | argus-a71 |
| 1.4 | 2026-05-20 | **v1.48.0 Stream A — Article State + Publish-Act + Staging + L1/L2 Composition.** Four substrate-load-bearing additions per design-spec [6a8d3f17] v0.3 LOCKED (Argus A74 authored; Mike-A74 locked). (1) Article subtype + editorial state machine: `subtype: article` extension to document type; 4-state editorial enum (draft → reviewed → locked → archived) on source article entries; ship-artifact wrappers inherit editorial-lock gating per new Rule 13. (2) Publish-act semantics: NEW optional `publication_state:` per-target frontmatter map; PIPELINE-WRITTEN ONLY; values `live | retracted`; populated at sub-gate-3 completion. (3) External-work/ staging architecture: per-target editorial staging at `argo-os/external-work/<target>/`; gitignored at Studio level; non-destructive invariants protect manually-composed assets. (4) L1/L2 composition pattern: markdown-native L1 substrate composes with future real-code L2 apps via external-work/ staging surface; pipeline accepts binary outputs from anywhere without coupling to provenance. Five new validator checks (25-29; Checks 25-27 ratchet WARN at v1.4 / ERROR at v1.5 — one-cycle migration window; Checks 28-29 stay WARN as audit signals). New Rule 13 (article-wrapper editorial-lock composition). Entry-level backward-compat 100%. Body-replacement pattern per Mike-A75 lock: UID preserved; v1.3 body content where structurally equivalent preserved verbatim; v1.3 amendment narrative extracted to this history file as Migration 2; v1.4 amendment narrative landed in active capsule frontmatter + Migration 2 above. UID `eeb59ddf` preserved. | argus-a77 |

---

## Provenance

- **Extracted at:** 2026-05-11
- **Extracted by:** argus-a56 (during v1.19.0 Stream C — Capsule Pedagogy Completion)
- **Active capsule version at extraction:** v1.1.4 (519 lines)
- **Active capsule version after extraction:** v1.2 (~290 lines; ~44% reduction)
- **Extraction-fidelity check:** All historical content preserved. Active capsule retains the substrate-load-bearing technical content (Source Modes tables, Cleanup Rules, Validation Checks, Governance Rules). Reduction percentage moderated by the density of essential substrate that must remain in active body for validators and authors to reference inline.

---

*ship-artifact capsule history | UID 437e8944 | v1.19.0 Stream C extraction 2026-05-11 by Argus A56 | Bidirectional pair: governs eeb59ddf*

---

## Schema Migrations [NEW §; v1.42.0 Stream E — Mike-G54 directive 2026-05-18 + Argus-A71 walk-decision D]

**This subsection is distinct from the amendment-log entries above.** Schema-shape changes (frontmatter shape changes that break reader compatibility) get structurally different treatment from text/discipline amendments because they require atomic-commit reader migration. Each schema migration entry below documents: what changed shape, why, the atomic-commit reader set, and the backward-compat posture.

### Migration 1 — v1.2 → v1.3: manifest_root_uid scalar → per-target map (2026-05-18)

**What changed shape:** `manifest_root_uid:` capsule-frontmatter field changed from scalar (single UID string) to per-target map (`release: <uid>`, `web: <uid>`).

**Why:** Multi-target extraction governance — same ship-artifact contract now governs release-target AND web-target extraction. Single-capsule extension per Mike-G54 brief decision (over authoring a parallel web-content-artifact.capsule) honors more-capsules-equals-more-maintenance pin.

**Atomic-commit reader set (5 readers migrated in same git commit as capsule v1.3 amendment):**

1. `.tropo/scripts/build-release.py` `read_manifest_root_uid(capsule_path, target='release')` — Phase 0 bootstrap; now accepts target parameter; v1.3 map shape preferred + v1.2 scalar backward-compat fallback for release target only.
2. `.tropo/scripts/validate-release-manifest.py` `read_manifest_root_uid(target='release')` — same shape; validator default target='release' preserves existing CLI behavior.
3. `.tropo-studio/scripts/dry-run-manifest.py` `load_capsule_manifest_root_uid(target='release')` — same shape; returns `(uid, error_msg)` tuple per existing convention.
4. `.tropo/capsules/ship-artifact.capsule.md` Rule 1 prose — restated per v1.3 to reflect map shape + dual-root governance.
5. `vault/files/b2e7d4a9.md` foundation comment — updated to reference v1.3 capsule + parallel manifest_root_uid.web key.

**Backward-compat posture:**
- **Entry-level: 100% backward compat.** All existing ship-artifact entries (v1.2-era) continue valid. Absent `target:` field implies `[release]`; existing entries with scalar member_of behavior continue valid.
- **Capsule-reader: atomic-commit migration.** v1.2 readers cannot parse v1.3 map shape; v1.3 readers fall back gracefully to v1.2 scalar shape for release target. The atomic commit landed all 5 readers + capsule + history entry + Tropo Release Structure foundation comment in one git commit so no intermediate broken state exists.
- **Web target post-v1.3:** Web target requires v1.3+ capsule; v1.2 scalar shape errors when called with target='web'. By design — pre-v1.3 readers had no web concept.

**Cycle provenance:** v1.42.0 cycle activation root `9f1b9f99` + design brief `fdda7ceb` v0.2 LOCKED (absorbs Metis G54 source brief `a4b9d731` v0.2 LOCKED). Stream A (capsule v1.3 schema) + Stream E (this entry) + Stream F (5-reader migration) landed as atomic commit.

### Migration 2 — v1.3 → v1.4: article subtype + publish-act semantics + external-work staging + L1/L2 composition (2026-05-20)

**What changed shape:** Four substrate-load-bearing additions to the capsule body + frontmatter schema:

1. **Article subtype + editorial state machine** — `subtype: article` extension to the document type; 4-state editorial enum (draft → reviewed → locked → archived) on source article entries; ship-artifact wrappers pointing at article entries inherit editorial-lock gating per new Rule 13.
2. **Publish-act semantics + `publication_state:` field** — NEW optional frontmatter field on ship-artifact wrappers; PIPELINE-WRITTEN ONLY; per-target map keyed by target slug; values `live | retracted`; populated at publish-act sub-gate-3 completion. Canonical source-of-truth = pipeline §5 sub-gate artifacts; frontmatter = queryable cache (same pattern as existing pipeline-written fields `locked_by` / `locked_at`).
3. **External-work/ staging architecture** — per-target editorial staging at `argo-os/external-work/<target>/`; gitignored at Studio level; non-destructive invariants protect manually-composed assets (graphics, layout) from re-extract clobber; the boundary between vault canonical (markdown + jsonl only) and target-specific binary + formatting.
4. **L1/L2 composition pattern** — markdown-native L1 substrate composes with future real-code L2 apps via the external-work/ staging surface; pipeline accepts binary outputs from anywhere without coupling to how they were produced; v1.4 ships zero L2 capabilities (Mike composes step 3 manually for web v1).

**Why:** Tropo's web v1 (Cycle C / v1.48.0) needs substrate it can extract + publish through. The v1.46.0 cycle delivered the pipeline-runtime engine; v1.48.0 Stream A delivers the capsule substrate the extraction-and-publish pipeline writes against. Editorial state ≠ extraction-target membership ≠ publication state — three orthogonal dimensions caught by R1 paired-director-gauntlet (d.skeptic-arch substrate-coherence + d.fresh-reader stranger-engineer) on the source design-spec.

**Atomic-commit reader set (5 surfaces touched in same git commit as capsule v1.4 amendment):**

1. `.tropo/capsules/ship-artifact.capsule.md` — body replacement per Mike-A75 no-history-in-capsules lock; v1.3 amendment narrative extracted to this history file; v1.4 body adds 4 new top-level sections + Rule 13 + Checks 25-29.
2. `.tropo/capsules/ship-artifact.history.md` — this entry + v1.3 amendment narrative preserved as Migration 1 above.
3. `tropo-validate.py` — new validator functions for Checks 25-29 (mechanical implementation lands at Stream B of v1.48.0 cycle alongside build-web-content.py engineering delta).
4. `build-web-content.py` — pipeline-write hook for `publication_state:` at sub-gate-3 completion (Stream B engineering scope; Talos lane).
5. Top-level `.gitignore` — verify `argo-os/external-work/` entry exists (Check 29 audit signal).

**Backward-compat posture:**

- **Entry-level: 100% backward compat.** All existing ship-artifact entries (v1.3-era and v1.2-era) continue valid. Absent `subtype:` field is the v1.3 default; absent `publication_state:` map is the not-yet-published default; absent `target:` field implies `[release]` per v1.3 semantics.
- **Pre-existing v1.4-conformant entries (honest-record):** [7d4c3e8a](../../vault/files/7d4c3e8a.md) (Knowledge Graphs Aren't Enough article) was already authored at `subtype: article` + `status: locked` pre-cycle by Metis-G54 (locked_at 2026-05-19) as the source article for the [c5a7e391](../../vault/files/c5a7e391.md) Tropo Extraction-and-Publish Pipeline brief. No migration needed at v1.4 ship — the entry was already conformant from authoring time. Surfaced as honest-record per d.skeptic-arch R3 P1.5 absorption 2026-05-20.
- **Validator ratchet:** Checks 25-27 WARN at v1.4 / ERROR at v1.5 — one-cycle migration window for existing articles that need editorial-state backfill (assign `subtype: article` + editorial `status:` to currently-untyped articles) + initial pipeline-write semantics. Checks 28-29 stay WARN indefinitely (coherence audit signals).
- **Locked-state transition:** v1.3 was `status: locked` (Argus A35 lock 2026-04-25). v1.4 is authored at `status: draft` per the state machine (new amendment under authoring). Locked_by / locked_at fields drop during draft; will be set again when v1.4 locks at cycle close per Vela's ship discipline.

**Cycle provenance:** v1.48.0 cycle activation root `c2210e81` + pipeline-run `a9750384` + design brief `c184b781` v0.3 LOCKED (absorbs design-spec `6a8d3f17` v0.3 LOCKED authored by Argus A74). Stream A (this capsule v1.4 amendment) authored by Argus A77 under captain-mode per Mike-A77 "Let's Build!" authorization 2026-05-20. Pipeline step 4 (`24f16afc` author-arch-spec-artifacts) work-product.

**Design-spec lineage (R1 paired-director-gauntlet absorption):** d.skeptic-arch caught v0.1 P0 field-conflation (brief §10 Surface 2 used `extraction_scope: web` which isn't a valid enum value); d.fresh-reader caught the same shape as "overloading code-smell" + "editorial state ≠ target-membership state"; both converged on the HYBRID pattern at v0.2 (three orthogonal dimensions, not two). v0.2 → v0.3 LOCKED 2026-05-19 by Mike-A74 with d.skeptic-arch LOCK-after-absorption (4 R2 P1s framing-honesty polish absorbed at v0.3). The capsule v1.4 body authors against the v0.3 LOCKED spec directly.


---

## v1.69 S3 Additions (extracted 2026-06-11 by Argus A110 — token-performance trim; the capsule remains over the 51,200 write-time budget on LIVE contract weight and carries a named exemption in the v1.69 budget table; restructure booked: the §Publish-Act machinery is a re-home candidate when the v1.70 ship-hygiene lane touches this capsule)

### §Article Subtype — Migration (v1.4 approach, extracted)

Existing articles in vault: most are currently typed `document` without `subtype: article` and without an explicit editorial-state enum value beyond the document.capsule default. Migration approach:

1. Identify candidate articles via grep (member_of agentic-builders project; or by content shape — long-form essay-class entries authored for external readership).
2. For each: assess current editorial state; assign `status: locked` if already published, `status: draft` if not.
3. Backfill `subtype: article` on identified entries.

Mechanical work; assigns to Cycle B engineering substrate-touch pass or a one-shot migration script. Check 25 ratchets WARN at v1.4 / ERROR at v1.5 to give migration a one-cycle window.

### Cycle provenance (extracted from §5 Composes-With + the operational flow)

- v1.46.0 Cycle A Design-Spec (6a8d3f17): authored by Argus A74; locked at v0.3 by Mike-A74; absorbs four R1 paired-director-gauntlet findings.
- Extraction-and-Publish Pipeline brief (c5a7e391): Mike-G55 + Metis-G55 framing.
- Web v1 Release Plan (b8f5d293): this capsule v1.4 was Cycle A remainder substrate (v1.46 deferred → v1.47).
- v1.48.0 Cycle Brief (c184b781): cycle landing the v1.4 amendment — Stream A = ship-artifact.capsule v1.3 → v1.4 body replacement per Mike-A75 lock pattern. Brief authored as v1.47 substrate; cycle renumbered v1.47 → v1.48 per Mike-V49 chain-mutability override 2026-05-21 — Vela's substrate-discipline interrupt cycle took the v1.47.0 release tag at 3dbc7d88; Argus's Cycle B + C + D substrate shifted +1.
- build-web-content.py engineering note: Cycle B extended the existing 241-LOC v1.43.0 Stream D thin-orchestrator with ~150-250 LOC of publish-act + sync hooks per design-spec 6a8d3f17 §6 (not from-scratch authoring).

### Pre-v1.69 footer (extracted verbatim)

*ship-artifact capsule definition | DRAFT v1.4 (status: draft pending cycle close lock) | history at ship-artifact.history.md | v1.4 article-state-publish-act-staging-composition amendment 2026-05-20 by Argus A77 under v1.48.0 cycle [c184b781] Stream A per design-spec [6a8d3f17] v0.3 LOCKED. v1.3 multi-target extraction amendment (Argus A71 2026-05-18) preserved as prior locked state. v1.2 body refactor (Argus A56 2026-05-11 — v1.19.0 Stream C — 5-section pedagogy) preserved. Prior v1.0–v1.2 locks preserved in history. UID `eeb59ddf` preserved across all versions.*
*"One declaration per shippable artifact. Canonical source in argo. Default doesn't-ship. The graph is the manifest. (v1.3:) Same discipline, multiple targets. (v1.4:) Editorial state on the source; target membership on the wrapper; publication state pipeline-written at the act. Three dimensions, one substrate."*
