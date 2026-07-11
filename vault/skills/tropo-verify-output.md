---
skill: verify-output
name: verify-output
type: how-to
purpose: How to verify the output of a Tropo agent — day-to-day verification toolkit consolidating philosophy, instruments, and protocols into one named landing surface
when: When you've received output from an agent (your personal agent, a sub-agent dispatch, a playbook run, a pipeline run) and need to confirm it's right before acting on it or shipping. When you need to know which verification instrument fits which class of output. When you want to teach yourself or another reader the verification doctrine that's distributed across the manifesto + sa.* fleet + grooming protocol.
mode: inline
uid: a9623c63
status: active
owner: argus
created: 2026-05-10
created_by: argus-a54
modified: 2026-05-10
modified_by: argus-a54
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: Reach for this when you need to verify an agent's output and want one document that pulls together the philosophy (manifesto Principles 5+6 — verify-before-claim + bounded-verification-as-moat), the instruments (sa.cold-boot for stranger reads, sa.skeptic for adversarial review, sa.first-use-walker for stranger-encounter walks, sa.pipeline-walker for pipeline runs), the demo (evaluate-tropo.playbook as the worked example), and the grooming protocol (work-pipeline verification, not just artifact verification). Replaces the v1.4-era split where verification doctrine lived across the manifesto + scattered playbook references + sa.* commissioning protocols with no single named landing surface. New v1.16.0 ship — backlog 9d0f7e3b closed.
related_capsule: a7c3f489
related_release: a0998f03
subsystem_hub:
  - 2d083137
  - 8dd772a0
---

# Verify Output

Use this when you've received output from an agent and need to know it's right before acting on it. The verification toolkit is layered — each layer catches a different class of defect. Pick the right instrument for what you're verifying.

The principle underneath: **verify before claim** ([The Studio Manifesto v1.0 §Verification](../../library/the-studio-manifesto.md), Principle 5+6). "Locked" doesn't mean "built." "Designed" doesn't mean "tested." The output is the plan. The verification is the proof. You are responsible for the proof.

## When to Use

- You received an artifact from an agent (a brief, a spec, a piece of code, a document) and need to confirm it holds before acting on it.
- You're about to ship a release and need to know the substrate is sound for stranger encounter.
- You're auditing a pipeline run and need to confirm each stage's output meets the next stage's input contract.
- You want to teach yourself the verification doctrine that's distributed across the manifesto + sa.* fleet.

## The Toolkit — Four Instruments

Each instrument verifies a different class of output. Reach for the one that matches what you're checking.

### sa.cold-boot — Stranger Read Verification

**What it does:** Spawns a sub-agent that reads a target document (a brief, a spec, a capsule definition, a playbook) **cold** — with no prior context about Tropo, your project, or the document's history. Reports what landed clean, what was ambiguous, what was missing.

**When to reach for it:** Before locking any artifact that strangers will read. Catches assumed-context bugs (you wrote it; the document makes sense to you because you have context the reader doesn't have).

**Cost:** ~5-10 minutes per dispatch.

**Pattern:** [`vault/files/e863a1e0.md`](../../vault/files/e863a1e0.md) declares the 6-step commissioning protocol. Hot-path quick-reference: [`agents/sa/commission-quickref.md`](../../agents/sa/commission-quickref.md).

### sa.skeptic — Adversarial Review

**What it does:** Spawns a sub-agent whose job is to **find weaknesses** in a target artifact. Looks for ambiguity, edge cases, missing escape hatches, conflicts with existing principles, performative-vs-load-bearing language, false-positive risks. Returns structured findings ordered by severity (P0 ship-blocking, P1 should-fix, P2 polish).

**When to reach for it:** When you have a draft of something load-bearing (a primitive declaration, a governance contract, a soul letter) and you need someone explicitly looking for what's wrong with it. Skeptic is the antidote to "smile-me-to-yes" reviews.

**Cost:** ~10-15 minutes per dispatch.

### sa.first-use-walker — Stranger Encounter Walk

**What it does:** Simulates a stranger working through a multi-step user-facing flow (a welcome playbook, an onboarding sequence, a tour). Walks every step the stranger would walk; reports friction, gaps, places where the stranger would lose orientation.

**When to reach for it:** Before locking any user-facing playbook or onboarding sequence. Tests the artifact's correctness in the dimension that matters: can a stranger actually do the thing the artifact tells them to do?

**Cost:** ~15-30 minutes per dispatch (longer for substantial flows).

### sa.pipeline-walker — Pipeline-Run Verification

**What it does:** Walks a pipeline run end-to-end, verifying each stage's output against the next stage's input contract. Reports any stage where the output doesn't satisfy what the next stage expects. Useful for dev-pipeline activations, publish-pipeline activations, or any DAG-style workflow.

**When to reach for it:** Mid-pipeline-run when you're not sure a stage shipped clean substrate to the next. Or post-run as part of release verification.

**Cost:** ~10-20 minutes per pipeline-run walked.

## The Demo — evaluate-tropo.playbook

[`evaluate-tropo.playbook.md`](../playbooks/concierge-paths/evaluate-tropo.playbook.md) is the worked example of verification at work. A skeptic-class user (someone evaluating Tropo before committing to it) walks the playbook; the playbook surfaces what Tropo actually does + what its limits are. Read this when you want to see verification doctrine applied to a real surface.

## The Grooming Protocol — Work-Pipeline Verification

Verifying an *artifact* is one thing. Verifying the *work-pipeline* that produced the artifact is another. The grooming protocol catches drift in the production substrate itself.

[`grooming.playbook.md`](../playbooks/grooming.playbook.md) walks the work-pipeline and surfaces:
- Tasks marked `done` but `state: active` (hygiene state-flips)
- Briefs marked `specify` but downstream spec already shipped (status drift)
- Pipeline-runs marked `active` but no recent activity (stale runs)
- Cross-references to UIDs that no longer exist (broken graph)

Run grooming when the substrate feels noisy or when validators surface drift findings you don't recognize.

## The Bounded-Verification Thesis

Tropo's strategic moat is **bounded verification** — the human's scarce capacity to validate outcomes scales when the verification surface is bounded by the constraints the human defined ([mission-brief.md](../../context/mission-brief.md)).

In practice: you don't verify *everything* an agent produces. You verify the dimensions that matter for the constraint you set. Three-instrument verification (Argus build + independent review + sa.cold-boot stranger test) is the canonical pattern for substrate-introducing work; lighter verification (single-instrument + dogfood gate) is right for substrate-amending work.

The instruments above are the toolkit. The bounded-verification thesis is the discipline that decides which to use.

## Composability

These instruments compose. A typical substrate-introducing cycle's three-instrument verification fold uses:

- **sa.cold-boot** validates a stranger reads the substrate cleanly
- **sa.skeptic** adversarially reviews the declaration
- **sa.first-use-walker** confirms the boot-time enforcement chain works (when applicable)

Bundled findings from all three feed into single remediation pass; regression cold-boot validates the bundle if remediations are substantive.

## Constraints / What This Skill Will NOT Do

- **Will not specify** which instrument to use for arbitrary output classes — judgment remains with the agent invoking. This skill is the inventory + the philosophy; the routing is contextual.
- **Will not replace** principal review. For canonical positioning documents (Studio Manifesto, Tropo Work narrative, etc.), Mike's principal review is the load-bearing verification step; sa.* instruments are augmentations, not substitutes.
- **Will not cover sub-cases beyond the four instruments listed.** New instruments (sa.spec-reviewer, sa.architecture-walker, etc.) added in future cycles will be folded in via amendment.

## Composes With

- **[The Studio Manifesto v1.0 (`fbb13cca`)](../../library/the-studio-manifesto.md)** — Principles 5+6 (verify-before-claim, bounded-verification-as-moat). The philosophy this skill operationalizes.
- **[evaluate-tropo.playbook (`64b8e1d3`)](../playbooks/concierge-paths/evaluate-tropo.playbook.md)** — the worked-example demo of verification applied.
- **[grooming.playbook](../playbooks/grooming.playbook.md)** — work-pipeline verification companion.
- **[`vault/files/e863a1e0.md`](../../vault/files/e863a1e0.md)** + **[`agents/sa/commission-quickref.md`](../../agents/sa/commission-quickref.md)** — sa.* commissioning protocol (6-step universal rule).
- **[`agents/sa/sa.cold-boot/`](../../agents/sa/sa.cold-boot/)**, **[`agents/sa/sa.skeptic/`](../../agents/sa/sa.skeptic/)**, **[`agents/sa/sa.first-use-walker/`](../../agents/sa/sa.first-use-walker/)**, **[`agents/sa/sa.pipeline-walker/`](../../agents/sa/sa.pipeline-walker/)** — the actual sa.* agents this skill references.

---

*verify-output skill | UID `a9623c63` | Argus A54 | 2026-05-10 | v1.16.0 Stream C*
*"Pick the right instrument for what you're checking. Verification is the proof."*
