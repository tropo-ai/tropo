---
uid: 78c51bdf
name: "publish-pipeline-history"
type: capsule-history
governs: 7e3a91c8
governs_path: .tropo/capsules/publish.pipeline.capsule.md
extracted_at: 2026-06-11
extracted_by: argus-a110
extracted_in_cycle: "v1.69 — Agent + Playbook Unification (S3 token-performance SPLIT)"
extracted_in_release: pending-v1.69.0
schema_version: 2
governed_by: 5ec083a3
extraction_scope: argo-private
member_of:
  - "76bab75f"   # tropo-playbooks (mirrors the capsule's member_of)
tags: [capsule-history, extracted-from-publish-pipeline-capsule, v1.69-s3-split]
---

# publish.pipeline — Capsule History

*History extracted from publish.pipeline.capsule v1.3 at the v1.69 S3 token-performance split (2026-06-11, Argus A110; capsule was 59,797 bytes vs the 51,200 write-time budget). Active capsule preserves: §1–§11 live contract, §14–§18 live step/activation specifications, v1.3 + v1.2 frontmatter amendment notes. This file preserves: the v1.1 frontmatter amendment note, §12 Provenance, §13 Implementation Status (a frozen v1.49.0.2-era snapshot), the stranded mid-file v1.2 footer (a defect — §17/§18 were appended after it, leaving a duplicate stale footer mid-document; removed at this split), §17.5 design rationale, and the pre-split v1.3 footer.*

---

## Frontmatter Amendment Note (extracted; v1.3 + v1.2 notes remain in the active capsule)

**v1_1_amendment_note:** "v1.0 → v1.1 amendment 2026-05-22 by Argus A78 captain-mode end-of-session under Mike-A78 'proceed' directive. Codifies operational state after v1.49.0 ship + v1.49.0.1 Talos surgical patch + v1.49.0.2 Argus surgical patch. Five substantive amendments: (1) §6 sentinel convention — two-commit flow MARKED OPERATIONAL (was specified at v1.0; Talos v1.49.0.1 patch implements it; web target now writes publication_state.web:live commit to vault alongside sentinel commit to website-content); (2) §7 validator checks — MARKED SHIPPED — check_publish_pipeline_md_schema + check_target_module_present + check_article_source_required_fields + check_ship_artifact_required_fields all live in tropo-validate.py at WARN level (4 checks, not 2); (3) §8 exit codes amended to include publish-check.py exit codes (0/1/2/3); (4) NEW §11.1 Pre-publish readiness check — surfaces publish-check.py as the canonical user-facing preflight gesture (composes the 4 validators + manifest-walker logic into one command; outputs ready-to-paste wrapper scaffold when missing; resolves pipeline UID on READY; supports --slug lookup); (5) NEW §13 v1.1 Implementation Status — mirrors c5a7e391 §3.7 pattern at capsule scope; documents what's operational vs specified-but-deferred. Composes with c5a7e391 v0.5 §13.3 P1+P2+P6 ship records. Per Mike-A78 'we'll continue building the spec' — capsule is living substrate; future cycles continue to amend it."

---

## §12. Provenance (extracted verbatim)

### v1.0 (2026-05-22)

- **v1.0 authored 2026-05-22** by Argus A78 captain-mode during v1.49.0 cycle step-3 (author-arch-spec-artifacts) under Mike-A78 "more than you said. We have runway here" directive 2026-05-22.
- **Engineering substrate** (publish.py + publish_types.py + publish_targets/web.py + publish_targets/docx.py + two example pipeline definitions f1b4c8d2 + e0a3d9c7) authored by Talos T9 2026-05-22; capsule documents Talos's operational shape, not invented schema.
- **Sentinel convention (§6)** resolved by Argus + Talos pair-call 2026-05-22 on argus-talos.md; Talos engineering perspective on commit-author-email-as-detection-surface; Argus locked into capsule per S0.1.
- **Class-core/workflow distinction (§2)** per c5a7e391 v0.4 §3.6 lock-break amendment authorized by Mike-A78 2026-05-22.
- **Six friction minimizers (§1)** per Mike-A78 v1.49.0 walk Q5 (corrected — "once the pipeline is in production, and used daily, it should seek to minimize friction").
- **Validator extension specs (§7)** per v1.49.0 brief §S0.2; WARN at v1.49 → ERROR ratchet at v1.50.0+.

### v1.1 (2026-05-22)

- **v1.1 amendment authored 2026-05-22** by Argus A78 captain-mode end-of-session under Mike-A78 "proceed" directive (after v1.49.0 ship + v1.49.0.1 Talos surgical patch + v1.49.0.2 Argus surgical patch). Codifies operational state of the publish.pipeline class as of v1.49.0.2.
- **§6 two-commit flow MARKED OPERATIONAL** — Talos's v1.49.0.1 `_platform_commit()` patch implements the publish-act semantics specified at v1.0. Concrete 6-step sequence documented inline (rsync → sentinel commit website-content → push → _platform_commit kb-content + publication_state.web → Vercel hook → done). Sequencing is load-bearing per Fire 2 KGAE retrospective.
- **§7 validator checks ratcheted from 2 → 4** — added check_article_source_required_fields + check_ship_artifact_required_fields (Argus A78 v1.49.0.2 ship per c5a7e391 §13.3 P1+P2). Both close substrate-coherence defects from c5a7e391 §13.2 KGAE retrospective (Fire 1 wrapper missing kind:file; Fire 3 source missing slug + published_at). All 4 SHIPPED at WARN level → ERROR ratchet at v1.50.0+.
- **§8 exit codes amended** — added publish-check.py exit codes (0/1/2/3 — READY / NOT READY / not-found / no-wrapper).
- **§11.1 Pre-publish readiness check NEW** — surfaces publish-check.py as the canonical user-facing preflight gesture; closes the discoverability P0 from R1 paired-walk (d.fresh-reader) on publish-check.py 2026-05-22.
- **§13 Implementation Status NEW** — per-component shipped vs deferred table; mirrors c5a7e391 §3.7 pattern at capsule scope.
- **R1 paired-walk absorbed** for publish-check.py 2026-05-22 (d.skeptic-arch substrate-coherence + d.fresh-reader stranger-engineer); both returned HOLD-WITH-P0s; 4 P0s + 4 P1s absorbed inline before ship. Substrate-resident discipline working — same pattern as v1.49.0 brief v0.2 → v0.3 absorption.

---

## §13. Implementation Status (extracted verbatim — frozen v1.49.0.2-era snapshot; ~20 versions stale at extraction)

**Honest end-of-cycle snapshot. Mirrors c5a7e391 §3.7 pattern at capsule scope.** v1.1 codifies the operational state of the publish.pipeline class as of v1.49.0.2.

### Shipped substrate (v1.49.0 + v1.49.0.1 + v1.49.0.2)

| Component | Path / UID | Ship | Status |
|---|---|---|---|
| publish.pipeline.capsule | `.tropo/capsules/publish.pipeline.capsule.md` (UID 7e3a91c8) | v1.49.0 → v1.1 amendment | Operational |
| publish.py thin runner | `.tropo/scripts/publish.py` | v1.49.0 (Talos T9) | Operational |
| publish_types.py dataclasses | `.tropo/scripts/publish_types.py` | v1.49.0 (Talos T9) | Operational |
| publish_targets/web.py | `.tropo/scripts/publish_targets/web.py` | v1.49.0 + v1.49.0.1 patch | Operational; 6-step sequence per §6 |
| publish_targets/docx.py | `.tropo/scripts/publish_targets/docx.py` | v1.49.0 (Talos T9) | Operational; stops at stage |
| publish-check.py preflight | `.tropo/scripts/publish-check.py` | v1.49.0.2 (Argus A78) | Operational; --slug mode + pipeline UID resolution + scaffold output |
| check_publish_pipeline_md_schema | tropo-validate.py | v1.49.0 (Argus A78) | WARN-level operational |
| check_target_module_present | tropo-validate.py | v1.49.0 (Argus A78) | WARN-level operational |
| check_article_source_required_fields | tropo-validate.py | v1.49.0.2 (Argus A78) | WARN-level operational |
| check_ship_artifact_required_fields | tropo-validate.py | v1.49.0.2 (Argus A78) | WARN-level operational |
| lib/article_readiness.py shared module | `.tropo/scripts/lib/article_readiness.py` | v1.49.0.2 (Argus A78; R1 paired-walk P1 absorption) | Operational; consumed by validator + publish-check.py |
| Sentinel convention (pipeline-bot@argo-os identity) | publish_targets/web.py | v1.49.0 (Talos T9) + S0.1 pair-call resolution | Operational + git-blame validatable |
| publish-to-web example pipeline | vault/files/f1b4c8d2.md | v1.49.0 (Talos T9) | Operational; ships 12 articles |
| publish-to-docx example pipeline | vault/files/e0a3d9c7.md | v1.49.0 (Talos T9) | Example shape |
| KGAE article LIVE on tropo-ai.com | vault/files/7d4c3e8a.md → /agentic-builders/knowledge-graphs-arent-enough | v1.49.0 (live after 3 fix-on-see fires) | Live (Captain's Read v2.0 Gate 1 ratified) |

### Specified but deferred (see c5a7e391 §13.4 + §13.6 multi-cycle arc)

| Component | Spec § | Suggested cycle |
|---|---|---|
| Asset architecture (`!asset:` sentinel resolution; per-entry asset directory) | c5a7e391 §4.5 | v2.3+ dedicated cycle (P7 + C4) |
| Per-category cleanup_rules defaults table (Articles/KB/Explainers/Legal) | c5a7e391 §3.5 | v1.50 grooming OR v2.1+ (C3) |
| Multi-template per target + staging-area-with-routing-gate + Mike-eyeball editorial gate | c5a7e391 §3 Step 3 LOAD-BEARING | v2.4+ dedicated cycles (C1) |
| Three-sub-gate verification harness (smoke/build/integration) for web target | c5a7e391 §3 Step 5 | v2.2+ Vela-lane cycle (C2) |
| Other-target publish gestures (MindBridge / LinkedIn / PDF / pptx) | c5a7e391 §3 Step 4 + §8 | v2.x+ per-target cycles (C5; MindBridge first per Mike-A74 Block 4 Fold Plan Gate 3) |
| Auto-generate wrapper from source article (removes manual step) | c5a7e391 §13.3 P4 | v1.50 grooming OR v2.1+ |
| `tropo publish <article-uid>` ergonomic user command | c5a7e391 §13.3 P5 | v2.1+ |
| Extract validator-rule logic into shared `lib/article_readiness.py` module (DRY between tropo-validate.py + publish-check.py) | NEW v1.50 candidate (R1 paired-walk finding) | v1.50 grooming |

### How to read this section

**This capsule (v1.2) declares the operational shape of the publish.pipeline class.** v1.0 + v1.1 codified MVP + first-round polish; v1.2 absorbs three Metis G58+G59 LOCKED design briefs as substrate-class amendments (Package Step §14 + Design Step §15 + Section-Scope Composition §16). The deferred-row items are real future work; future cycles continue to amend this capsule + c5a7e391.

---

## Stranded mid-file v1.2 footer (extracted verbatim — defect: §17/§18 were appended AFTER this footer at the v1.3 amendment, leaving a stale duplicate footer mid-document; removed at the v1.69 split)

*publish.pipeline.capsule v1.2 | UID `7e3a91c8` | v1.0 authored Argus A78 2026-05-22 during v1.49.0 cycle | v1.1 amendment Argus A78 2026-05-22 (operational state codification) | v1.2 amendment Argus A81 2026-05-24 (P-lane P1+P2+P5 absorption per Metis G58+G59 design briefs; Mike-A81 strong-lean execute calibration stm-a81-003) | Operational substrate by Talos T9 + Argus A78+A81 | Companion to c5a7e391 v0.5 (universal workflow + maturity arc) + ship-artifact.capsule v1.4 + numeric-folder-prefix.capsule v1.0 + doc-spec.capsule v1.0*
*"The class codifies what the workflow describes. Three stages observable. Targets extend. Humans verify. v1.49 shipped MVP; v1.49.0.2 absorbed first-round polish; v1.52 absorbs package + design + section-scope discipline; the spec at c5a7e391 is the destination."*

---

## §17.5 What This Resolves (extracted verbatim — design rationale for the activation-modes amendment)

The lightweight-vs-heavy verification tension that surfaced during v1.49 cycle 4 closure (G60 session 2026-05-24): both paths were right in different situations. Strict mode IS the heavy path; express mode IS the lightweight path; standard mode IS the hybrid. The activation-modes reframe lets all three coexist as substrate-declared options rather than fixed engine properties.

The "agent skipped Step 3a" failure mode (G58 case-study original publish): if the activation called for strict mode, the engine would have halted at the design-walk gate. If express mode, the skip was explicitly authorized. Standard mode would have logged a soft-warning for the skip. The discipline becomes structurally enforced at the mode the calling agent chose — not implicit in agent training.

---

## Pre-split v1.3 footer (extracted verbatim)

*publish.pipeline.capsule v1.3 | UID `7e3a91c8` | v1.0 authored Argus A78 2026-05-22 during v1.49.0 cycle | v1.1 amendment Argus A78 2026-05-22 (operational state codification) | v1.2 amendment Argus A81 2026-05-24 (P-lane P1+P2+P5 absorption per Metis G58+G59 design briefs) | v1.3 amendment Metis G60 2026-05-24 (cross-lane substrate-class work per Mike-G60 directive; absorbs activation-modes c8a47e91 + Phase 3a integration e7d4b58f into NEW §17 + §18) | Operational substrate by Talos T9 + Argus A78+A81 + Metis G60 (cross-lane absorption) | Companion to c5a7e391 v0.5 + ship-artifact.capsule v1.4 + numeric-folder-prefix.capsule v1.0 + doc-spec.capsule v1.0 + 5a89297a v0.5 working-copy spec*
*"The class codifies what the workflow describes. Three stages observable. Targets extend. Activation modes parameterize rigor. Outputs live where content lives. Humans verify. v1.49 shipped MVP; v1.49.0.2 absorbed first-round polish; v1.52 absorbed package + design + section-scope discipline; v1.53 absorbs activation parameterization + multi-target convention; the spec at c5a7e391 is the destination."*

---

*publish.pipeline — Capsule History | UID `78c51bdf` | extracted 2026-06-11 by Argus A110 at the v1.69 S3 token-performance split | governs: publish.pipeline.capsule (7e3a91c8)*
*"The capsule carries the contract; the companion carries the becoming."*
