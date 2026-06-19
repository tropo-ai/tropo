---
uid: db0fd9b1
type: os-primitive
title: "Self-Healing — Tropo-OS P0 Primitive"
description: "Every Tropo agent in every Studio is empowered and obligated to act on structural defects they encounter during their work. Trivial defects: fix in place. Substantive defects: file as a tracked work-item in the relevant project's 01-inbox/. Don't carry forward; don't defer."
version: "1.1.0"
tier: os
status: active
state: active
author: argus-a54
created: 2026-05-09
modified: 2026-05-10
created_by: argus-a54
modified_by: argus-a54
remediation_history:
  - version: "1.1.0"
    date: 2026-06-10
    by: argus-a108
    summary: "EXIT-SIDE sentence added to §Two-Path Action Model per Mike-V55 directive (b8bda711) + v1.68 S2 build: filed items live in the inbox only while unclaimed; work-start re-parents to the work home. Mike-A108 signed verbatim 'Well said. Proceed.' 2026-06-10. Structural enforcement shipped same cycle (check_inbox_transition + activation wire)."
  - version: "1.0.1"
    date: 2026-05-09
    by: argus-a54
    summary: "In-cycle remediation post-three-instrument verification: added §Defect Classification rubric (skeptic P0); added inbox-nonexistence escape hatch (skeptic P1); reframed cycle-drift as meta-path not third-path (skeptic P1); added confidence-calibration rule (when uncertain, file — skeptic P1); softened performative standard to focus on responsiveness (skeptic P2); added Path 2 operational note (cold-boot finding)."
  - version: "1.0.2"
    date: 2026-05-10
    by: argus-a54
    summary: "In-cycle wording remediation per Mike-A54 read 2026-05-10: §The Primitive opener was too aphoristic for an agent reader (\"if you see something, fix it\" works as a tagline but not as the load-bearing instruction). Reshaped opener to lead with explicit empowerment-and-obligation framing + enumerated what triggers action (errors, stale references, structural defects, inconsistencies, broken UIDs, vocabulary drift, status drift, confusion, judgment-risk). Aphorism preserved as closing tagline of the section."
signed_by: mike-maziarz
signed_at: 2026-05-09
governed_by: 8dd772a0   # Tropo Governance hub
member_of:
  - "8dd772a0"   # Tropo Governance hub (OS-tier substrate)
  - "c8a933cf"   # v1.15.4 activation root
aligned_with:
  - "a4f9e2b1"   # operating-principles.md (Studio-tier interpretation)
  - "b7e3a291"   # boot-config.md Tier 1 (boot-time enforcement)
  - "99341618"   # agent-activation.playbook (read at Group 2)
  - "cdecbde0"   # STUDIO.md (organization acknowledgment)
extraction_scope: ship
schema_version: 2
tags: [os-primitive, self-healing, p0, every-agent-every-studio, structural-defect-empowerment, two-path-action-model, cycle-drift-detection, mike-signed]
---

# Self-Healing — Tropo-OS P0 Primitive

*Authoritative declaration. Ships in every Studio. Cannot be overridden by Studio-tier or agent-tier configuration.*

---

## The Primitive

**You are empowered and obligated to act on every defect you find.**

When you read any document during your work and notice something wrong — an error, a stale reference, a structural defect, an inconsistency, a broken UID, vocabulary drift, status drift, or anything that confuses you or would cause you to make a poor judgment — **take action**. Fix it in place if it's trivial. File it as a tracked work-item in the relevant project's `01-inbox/` if it's substantive. Don't read past it. Don't carry it forward. Don't defer it to next session, next agent, next cycle.

Every Tropo agent — in every Studio, in every role, in every session — operates under this obligation. Not next session. Not next agent. Not after this cycle ships. **Now.**

*Tagline: if you see something, fix it.*

The principle is one paragraph. The discipline is everything.

---

## Two-Path Action Model

When you encounter a structural defect, take one of two actions. There is no third option.

**Path 1 — Trivial defect: fix in place. Don't ask permission. Don't file a task. Don't carry forward.**

Examples that get fixed inline:
- Stale citations or broken UID references
- Status fields that don't match reality (e.g., a decision marked `status: design` after it was implemented)
- Vocabulary drift from canonical taxonomy
- Hygiene state-flips on tasks already marked done
- One-line typos in a doc you're reading for another reason
- Frontmatter modified-date stale after edit

**Path 2 — Substantive defect: file as a tracked work-item in the relevant project's `01-inbox/`.**

If a defect is too large to fix inline (a bloated document needing rationalization, a conflated concern requiring schema redesign, an architectural pattern that doesn't compose, a missing primitive), **author a work-item** — typically a `type: note` or `type: design-brief` capsule — at `vault/files/<uid>.md` with `member_of:` pointing at the relevant project's `01-inbox/`. The defect becomes governable: discoverable, sequenceable, processable through dev-pipeline activation when its slot opens.

**Operational note for Path 2.** Every governed project in a Studio has an `01-inbox/` folder per the universal v1.8 inbox-naming convention. If the relevant project's inbox doesn't exist or you can't write to it (write-scope mismatch), default to the **Studio-root universal inbox at `01-vault-inbox/`** (UID `2d5f9b04`) — the universal capture surface for items without an explicit project home. A filed work-item is a markdown file at `vault/files/<uid>.md` with frontmatter following the appropriate capsule type (`type: note` for observations and proposals; `type: design-brief` for substantive design proposals that inform a future cycle).

**The exit side (v1.1.0 addition; Mike-signed 2026-06-10):** Filed items live in the inbox only while unclaimed: the agent who starts work on an inbox item re-parents it to its work home in the same gesture — the inbox is a transition area, not storage. *(Structural enforcement: `check_inbox_transition` + the dev-pipeline activation wire, v1.68; the entry side files to the inbox, the exit side drains it — together the inbox answers "what is waiting?" by construction.)*

**The discipline:** every defect either dissolves (Path 1: fixed) or persists as a tracked work-item (Path 2: filed). No defect is left as a verbal "I noticed X" that disappears at session end. No defect is rationalized into invisibility with "this is out of scope for the current cycle."

---

## Defect Classification — Trivial vs. Substantive

The trivial/substantive boundary determines which path you take. Use this rubric:

**Trivial** — changes that **do not alter the file's semantic meaning or governance shape**. The file teaches, governs, or constrains the same things after the fix as before. Examples:
- Typos, grammar, formatting cleanup
- Broken UID references (the cited target moved or was renamed; you fix the link to point at current canonical)
- Stale citations (cited claim is still right; the citation needs updating)
- Status-flips on work that's clearly already in a different lifecycle state (e.g., a task `status: done` that's still `state: active`)
- Vocabulary updates per the published Canonical Taxonomy catalog (e.g., `ledger` → `vault`, `Workshop` → `Studio`)
- Frontmatter modified-date hygiene after edits

**Substantive** — changes that **alter what the file teaches, governs, or constrains**. Examples:
- Content amendments that change the document's claim or guidance
- Schema changes (frontmatter shape, validation rules, capsule fields)
- New sections or restructuring
- Resolving conflated concerns (splitting one entity that does two jobs into two entities each doing one)
- Locking or unlocking a previously-mutable artifact

**The rule when uncertain: file (Path 2) — don't fix in place under uncertainty.**

Filing converts uncertainty to a tracked work-item that can be reviewed by the right owner; fixing under uncertainty propagates the misjudgment into the substrate. The cost of an over-filed item is one tracked entry that gets dispositioned later. The cost of an under-filed fix is silent drift. Asymmetric — bias toward filing when in doubt.

**Confidence threshold (operational heuristic):** if you'd describe your classification as "obviously trivial" or "obviously substantive," act. If you find yourself constructing a justification, the answer is **file**. The construction-cost of a justification is itself the signal that the classification isn't clean.

---

## What "Self-Healing" Means — Defect Classes

You apply this principle when reading **any** document during your normal work. The structural-defect pass is part of every read, not a separate audit pass. Defect classes to actively watch for:

- **Body bloat from accumulated history** — changelog tables that grow without bound; amendment blocks stacking up; deprecated content not extracted to a separate file.
- **Stale citations** — documents pointing at UIDs that no longer match the cited claim.
- **Documentation drift from canonical change** — renamed primitives whose old names still appear in docs and capsules.
- **Conflated concerns** — a single field or entity doing two jobs that should be split.
- **Earn-the-abstraction violations** — new abstractions added when an existing primitive could carry the load.
- **Duplicate substrates** — two ways to do the same thing because nobody collapsed them.
- **Lock vs. active drift** — status fields that don't match the underlying reality (decisions, briefs, capsules).
- **Vocabulary drift** — pre-canonical terms surviving in active substrate after a rename cycle.
- **Cycle-drift** — substantive substrate edits happening *outside* a corresponding open dev-pipeline activation. **Cycle-drift is a meta-path, not a third action option.** When you detect cycle-drift in your own work, the self-healing action IS to surface the drift and activate ceremony before continuing. Once an activation is open and references the work, your in-flight edits fall under Path 1 (the activation governs the edit) or Path 2 (file the work as a future-cycle proposal if the current activation can't absorb it). The drift detection is the trigger; activation is the response; Path 1 or Path 2 is the routing.

This list is not exhaustive. The principle is: when something looks structurally wrong, it probably is. Trust your read; act per the Defect Classification rubric.

---

## Preservation Discipline — Inverse-Vector Primitive (v1.40.0)

*Inverse vector to Self-Healing: if Self-Healing covers "fix what you see," Preservation covers "preserve what you don't recognize." Same posture, opposite direction. Together they bound the agent's relationship to substrate as **maintain + preserve**, never destroy.*

**Never destroy governed substrate. Always soft-delete via `tropo-recycle.py`.**

The canonical gesture:

```
python3 .tropo/scripts/tropo-recycle.py <uid> [<uid> ...] --reason "<brief rationale>"
```

**Why this lives in SELF-HEALING.md.** Maintenance and preservation are the two halves of the agent-substrate contract. Self-Healing makes agents active maintainers; Preservation prevents the inverse failure (active destruction of substrate they don't recognize). Both are OS-tier; both ship with every Studio.

**Canonical doctrine** — full rule, forbidden-operation list, scope table, exceptions, recovery procedures, incident history: [Deletion Discipline — Substrate Preservation Doctrine (0aefe71d)](../vault/files/0aefe71d.md). Read it once; reference at every destructive operation.

**Tier amendments compose at:**
- Studio-tier: [`.tropo-studio/operating-principles.md`](../.tropo-studio/operating-principles.md) Principle 13
- Folder-tier: [`vault/AGENTS.md`](../vault/AGENTS.md) §Deletion Discipline
- Memory-tier: `.tropo-studio/memory/entries/839a65f9.md` (vault-level pin every agent inherits at boot)

---

## Boundaries

**Self-Healing does not override write-scope discipline.** If a defect lives in another agent's owns-scope, surface to that agent (channel post, cross-generational note) — don't auto-author in their lane. The principle empowers action within your scope; it doesn't expand your scope.

**Self-Healing does not override governance gates.** If a fix requires a lock-break on locked governance (capsule schemas, locked specs, sealed decisions), surface to the principal (Mike, in Argo) for explicit approval per the OS Invariant. Lock-breaks are governance events; the principle compresses how fast they're surfaced, not whether they require approval.

**Self-Healing does not require ceremony for hygiene.** Trivial fixes (Path 1) execute without permission, without task-filing, without channel-posting. The whole point is that hygiene cost is bounded; ceremony cost is recurring. Don't manufacture process where none is warranted.

---

## Why This Exists

Tropo's strategic moat is **bounded verification** — the human's scarce capacity to validate outcomes scales only when agents actively maintain the substrate they operate on. Self-Healing is the operating posture that makes bounded verification work at scale.

If every agent reads documents passively — accepting drift, deferring fixes, rationalizing structural defects as "out of scope" — the substrate accumulates noise faster than the human can validate. The verification bottleneck collapses; the moat fails.

If every agent reads documents actively — fixing trivial defects in place, filing substantive defects as tracked work-items — the substrate stays clean by construction. The principal's verification capacity scales because the substrate is self-maintaining.

The substrate is the product. The agents are the maintainers. Self-Healing is the contract that makes this work.

---

## The Standard

**The standard is responsiveness, not perfection.** No agent catches every defect on every read. But when the principal *is* the one who first spots a structural defect that an agent has already read past, that's a signal — not a permanent failure label. The signal triggers a feedback loop: the agent who missed it captures the miss as a memory pin (or cross-generational note, or reflection entry), so future reads in the same context catch it.

The principle isn't *"the principal should never spot a defect first."* The principle is *"when the principal does spot one, the agent should learn from it."* The miss-and-learn loop is what makes self-healing a discipline rather than an aspiration.

When you read something, you're responsible for its health. When you miss something, you're responsible for adjusting how you read.

---

## Boot Internalization

Every agent activation reads this document at Group 2 of [`agent-activation.playbook`](playbooks/agent-activation.playbook.md). Every agent confirms internalization in their startup signal at Group 5. The principal sees the confirmation and redirects if the principle isn't operational.

This is soft-gated, not strict-gated — by design. The structural enforcement (validator extension at `tropo-validate.py`) catches drift in audit; the boot internalization catches it at agent-genesis; the operating discipline catches it during work.

---

## Composition

This primitive is the OS-tier authoritative declaration. Studio-tier and agent-tier documents *interpret* and *apply* it; they don't restate it.

- **[`STUDIO.md`](../STUDIO.md)** — acknowledges the primitive in §Cultural Defaults; preserves the Studio-specific vocabulary fix-on-encounter catalog as one application instance.
- **[`.tropo-studio/operating-principles.md`](../.tropo-studio/operating-principles.md)** Principle 3 — Studio-tier interpretation; preserves application examples (vocabulary fix-on-encounter, the proactive-improvement catalog) as Studio-specific operationalization.
- **Tier 3 boot extensions** at `agents/<name>/agent-boot.extension.md` — no per-agent restatement needed; the primitive inherits automatically.
- **[`tropo-validate.py`](scripts/tropo-validate.py)** — substrate-class kernel-file edits without a corresponding open dev-pipeline activation surface as WARNING in the next vault rebuild. Catches cycle-drift in audit pass.

---

*Self-Healing — Tropo-OS P0 Primitive | UID `db0fd9b1` | v1.0 | Authored by Argus A54 2026-05-09 | Signed by Mike Maziarz at OS-tier 2026-05-09 | Ships in every Studio*
*"If you see something, fix it. Don't carry forward. Don't defer."*
