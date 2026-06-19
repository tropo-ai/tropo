---
uid: 3i7v4bd1
name: "Three-instrument verification for governance artifacts [PINNED]"
description: "Argus build + independent review (swarm or peer) + sa.cold-boot stranger test. Each instrument catches defects the others cannot. Mandatory for load-bearing governance files before marking active. Pinned 2026-04-21 after v1.3 capsule ship validation."
type: feedback
pinned: true
pinned_at: 2026-04-21
pinned_by: argus-a30
pin_directive: mike-maziarz
created: 2026-04-18
created_by: argus-a27
modified: 2026-04-22
modified_by: argus-a32
applies_to: all-crew
extraction_scope: ship
extraction_scope_changed_at: 2026-04-22
extraction_scope_changed_by: argus-a32
extraction_scope_change_note: "v1.3.1 Stream 3 D3.4 resolution — the three-instrument discipline is universal (not Argo-specific); the evidence examples below are from Argo-OS deployment history and ship as authentic demonstration rather than scrubbed-generic prose. A stranger evaluating Tropo sees how the discipline was forged + validated at scale, with real receipts and real dates. evaluate-tropo.playbook.md Resources section references this file; it now ships in the release."
originSessionId: 4469e791-1679-43ee-b92a-a2fcd11f8af1
---
# Three-Instrument Verification

*Starter-extraction note (added 2026-04-22 for v1.3.1 ship): this file was authored for the Argo-OS internal deployment. The discipline it describes (three-instrument verification) is universal and applies to any Tropo vault. The specific examples below reference Argo-OS history — agent generations (Argus A27, Argus A30), session-agent records (sa.cold-boot 025/026/027, 049/050/051/052), session dates (April 2026) — which are real receipts from the Argo vault's history. They ship as evidence of the discipline's application at scale, not as prescriptive detail your own vault must mirror. When applying the discipline in your own vault: use your own agents, your own session records, your own projects; the three-role structure is the invariant.*

---


Before marking any load-bearing governance artifact (capsule definition, activation file, playbook, boot-protocol template) as `active` or `cold_boot_verified: true`, run it through three independent instruments. Each catches a different class of defect. None substitutes for the others.

**Why:** April 18, 2026 session. Argus A27 built three agent-configurator artifacts (Orpheus activation, Talos activation, template) in Haiku 4.5. A spot-check in Opus 4.7 found 6 findings — 2 blockers, 4 refinements. After fixes, sa.cold-boot (record 025) found 9 additional gaps in the template alone, including a critical first-generation HALT bug that had been fixed in Orpheus/Talos but not carried back into the template body. Three rounds of cold-boot tests (025, 026, 027) were needed before all three artifacts cleared. Each instrument genuinely saw things the others could not.

## How to apply

**1. Haiku 4.5 (or equivalent) — build.** Fast and accurate at structural work. Load-bearing architecture, section ordering, frontmatter schemas, internal consistency within a single file.

**2. Opus 4.7 (or equivalent with 1M context) — architect review.** Cross-file referent verification, adversarial edge-case reasoning on gate logic, consistency across sibling artifacts, naming alignment with upstream specs. Does NOT catch stranger-usability gaps — its context is too rich.

**3. sa.cold-boot — stranger-actionability test.** Intentionally naive sub-agent reads ONLY the target file and attempts the task from cold. Every additional file it needs to open is a finding. Catches what neither model can see: unstated conventions, placeholder gaps, procedural ambiguity that only fails for someone without session context. The naivety IS the instrument.

**Mandatory:** artifacts intended for `cold_boot_verified: true` must PASS a sa.cold-boot test, not just an architect review. Architect review does not count as cold-boot verification — the agent doing the review already has context.

## The failure mode this prevents

Documentation-vs-implementation drift. A fix applied to one file gets described in another file's instructions but never propagated to the file that instructs copying. The instructions claim the fix exists; the copied body still has the bug. Record 026 caught exactly this pattern.

Architect review does not surface this — the reviewer knows the fix was applied elsewhere and assumes consistency. Only a cold-boot reader, reading the one target file in isolation, notices.

## When to invoke which

- **Small edits to an existing active artifact:** Haiku alone is usually enough if the change is scoped.
- **New artifact or major restructuring:** all three instruments, in order.
- **Capsule definitions, activation files, OS-level playbooks, templates that ship to users:** all three, non-negotiable. These are the artifacts that compound — a bug here creates downstream bugs forever.
- **After any PARTIAL verdict from sa.cold-boot:** re-run sa.cold-boot after fixes, not just a self-check. The "I fixed it" assertion is not verification.

## Validation at scale — v1.3 capsule ship, 2026-04-21

The discipline proved itself at scale during the v1.3 Typed Pipeline Capsule Ship (project-plan [b5e9c7d3]). Argus A30 shipped 14 artifacts (4 new typed-artifact capsules, 2 amendments, 1 new pipeline capsule, 1 pipeline instance, 5 archive projects, 1 directive) using the three-instrument discipline. Data:

- **4 sa.cold-boot BATCH dispatches** (records 049 pipeline, 050 concept, 051 arch-spec, 052 build) ran in parallel / sequentially throughout the session.
- **2 P0 contradictions caught** on arch-spec.capsule (051): valid-transitions list vs §Governance Rule 6 fast-path contradiction; Rule 4 direct-commissioned allowance vs Check 5 non-empty requirement. Both remediated in-session before lock.
- **15+ P1 findings remediated** across the 4 cold-boots. Every cold-boot returned PASS-WITH-GAPS verdict; every gap closed before the corresponding capsule locked.
- **1 duplicate-catch fired:** release.capsule already existed at v1.0 (April 16); approach shifted to v1.0 → v2.0 supersession preserving UID `b19e8d43`. This was the filesystem itself acting as an instrument — the Write tool blocked an overwrite, forcing a Read, which surfaced the pre-existing capsule.

**The P0s mattered.** arch-spec v1.0 would have shipped with internal contradictions — the state machine's transition list would have disagreed with §Rule 6 about whether `draft → locked` is legal, and Check 5 would have rejected a spec class Rule 4 explicitly allowed. A future author using the capsule would have hit either contradiction immediately. Cold-boot caught both before lock. This is exactly the failure mode three-instrument exists for.

**Pattern observed under load:** the BATCH cold-boot in particular is disproportionately cheap compared to its value. 4 BATCH dispatches across the session consumed ~55K-200K tokens each (agent-side context, not parent) and 8-15 minutes each in wall clock. LIVE-CHANNEL swarm would have been costlier per artifact; BATCH cold-boot was the right tool for per-artifact stranger tests.

## Updated role mapping (2026-04-21)

The original April 18 memory named specific sleeves (Haiku 4.5 builds, Opus 4.7 reviews). That specific mapping is now one instance of a broader pattern:

- **Instrument 1 — Argus build** (or equivalent owner-of-the-work). Today typically Opus 4.7 1M authoring; the role is "the artifact's author."
- **Instrument 2 — Independent review** (swarm or peer executive). Today typically sa.arch-specs + sa.skeptic LIVE-CHANNEL swarm OR another executive peer-reviewing. The role is "review by someone who has context but did not author."
- **Instrument 3 — Stranger test** (sa.cold-boot). Today sa.cold-boot BATCH mode is most common. The role is "read by someone with no context at all."

The three roles are the invariant; the specific sleeves mapping to each role have evolved with model availability. Future sleeves may shift again; the three-role structure holds.

## Related

- Cold-boot records that informed this memory (v1): `agents/sa/sa.cold-boot/activation-log/025-argus-a27-record.md`, `026-argus-a27-record.md`, `027-argus-a27-record.md`.
- Cold-boot records that validated at scale (v2 — v1.3 ship): `048-argus-a30-record.md` (project-plan.capsule), `049-argus-a30-record.md` (pipeline.capsule), `050-argus-a30-record.md` (concept.capsule), `051-argus-a30-record.md` (arch-spec.capsule — 2 P0s caught), `052-argus-a30-record.md` (build.capsule).
- The v1.3 ship project plan that drove the scale validation: [b5e9c7d3](../../vault/files/b5e9c7d3.md).
- The agent-configurator trilogy that originally prompted this practice (v1 lineage).

---

*Three-instrument verification | PINNED 2026-04-21 by argus-a30 per mike-maziarz directive*
*Original: Argus A27 | April 18, 2026. Validated at scale: Argus A30 | April 21, 2026.*
*"Different lenses catch different defects. Use them all before shipping governance."*
