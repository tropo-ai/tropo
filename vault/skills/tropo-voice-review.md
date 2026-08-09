---
skill: voice-review
name: voice-review
type: how-to
purpose: Review a touched documentation file for voice consistency, lore alignment, and stranger-encounter readability
when: At doc-pipeline Step 3 (voice-review-substrate) on any touched tier:summary or tier:subsystem doc; optionally on tier:spec docs when prose-heavy sections substantively changed (per doc-spec.capsule §Tier 3 procedural note)
mode: both
params:
  - doc_path
  - tier
uid: 811856a5
status: active
owner: orpheus
created: 2026-05-23
created_by: orpheus-o11
modified: 2026-07-21
modified_by: orpheus-o33
version: 1.3
supersedes_version: 1.2
v1_3_amendment_note: 'v1.2 → v1.3 amendment 2026-07-21 by orpheus-o33 adding a concrete banned-jargon-word checklist to Layer 3 (stranger-encounter test), seeded with "substrate." Trigger: Mike direction 2026-07-21 during the-readiness-trap (18cd6f16) retitle/refile — the word had shipped unnoticed across the homepage, How Tropo Works, Market Map, and Who We Follow copy, past this exact review layer, because Layer 3''s prior wording was a judgment call ("flag if a reference assumes jargon") rather than a concrete list to check against — it even used "substrate-jargon" as its own generic example term. The fix is at the review-gate source, not a one-off word swap on the single article Mike caught: a living, growing list future reviews check mechanically. A fully automated version of this class of check (started for the no-em-dash discipline) already exists as an unbuilt design-brief ([70f29fea](../files/70f29fea.md)) — Orpheus O33 flagged it back to Mike as worth reviving now that a second concrete rule motivates it; not yet actioned.'
v1_2_amendment_note: 'v1.1 → v1.2 amendment 2026-05-28 by orpheus-o12 adding Step 4.5b (coordination-channel state check; Layer 1.5) per finding [f90791ad](../../vault/files/f90791ad.md) Option A. Empirically demonstrated by v1.53 doc-pipeline c7a26c5a where Argus A83 posted scope-narrowing directive between E7 ship and Step 5 close; Orpheus O11 read the post AFTER executing the scope-variance work. Step 4.5 v1.1 caught canonical drift; coordination drift was the adjacent gap. v1.2 extends the same substrate-verify-twice discipline to the coordination layer: before declaring step PASS on long-running activations, tail inter-agent channels (argus-<self> + metis-<self> + ops.md) for posts since activation start that may refine, narrow, supersede, or redirect scope. Light addition; same composition shape; closes finding f90791ad.'
v1_1_amendment_note: v1.0 → v1.1 amendment 2026-05-25 by orpheus-o11 adding Step 4.5 (substrate-verify-twice check) per defect-class brief 83af4ac1 Layer 1. Discipline runs alongside the three layers without renaming the canon. Reviews now verify canonical-primitive references in the artifact under review (capsule schemas, enums, cited file versions, agent states) before declaring PASS — closes the defect class captured at v1.52 first production run (5 instances; all fix-on-see absorbed but each cost a remediation cycle).
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: Reach for this at doc-pipeline Step 3 to review any touched tier:summary or tier:subsystem doc against the Tropo voice canon. The skill walks three layers (tone consistency + lore alignment + stranger-encounter test) and produces a voice-review-notes entry capturing per-layer PASS/FAIL + specific findings. Also use on tier:spec docs as a self-spot-check when prose-heavy sections (§Intent, §Why, §Studio Shop Signage, §How to Validate body prose) are substantively changed — spot-check is not gating but the discipline is the same. The skill's output entry becomes acceptance_evidence for the doc-spec close gate at Step 5.
composes_with:
  - 9a7d314a
  - 5a4337ff
  - 79c6479c
subsystem_hub:
  - f87e33f0
---

# Voice Review

Use this to review a touched documentation file against the Tropo voice canon before it ships.

The skill carries an **intent** (voice consistency) and a **goal** (pristine documentation per the voice metric). The three layers below name how Tropo currently approaches that intent — they are guidelines, not hard-coded rules. The human walking the review (you, Orpheus, or whichever generation is operating) exercises judgment within the frame: weight the layers per piece, skip a layer when it's not load-bearing for this doc, add a fourth lens when the piece needs one. The substrate names the discipline; the human owns the judgment.

The skill operationalizes the three-layer Voice Review Definition from [doc-spec.capsule v1.0 §Voice Review Definition (9a7d314a)](../../vault/files/9a7d314a.md), which defines the canonical concept of "voice review" as a term. This skill carries the operational pattern; the capsule carries the definitional contract. Authoring a doc that names a voice-review_required tier without running this skill leaves an unsigned commitment in the substrate; the doc-pipeline Step 3 gate enforces the discipline (the run-the-skill check), not a specific PASS/FAIL pattern on the three layers.

## Steps

1. **Read the doc at `{doc_path}` in full.** Include frontmatter (for tier context) + body prose + closing block (call-to-action, bio, etc. as applicable).

2. **Layer 1 — Tone consistency.** Read the body prose against the Shop-Floor Notes canon ([72abbb86](../../vault/files/72abbb86.md)) for tropo-ai.com agentic-builders content, or the appropriate canon for the surface:

 - Sounds like Tropo: plain English, precise, functional. Not academic. Not vendor-marketing. Not aspirational.
 - No em-dashes (per Mike binding pin 2026-05-21). Hyphens or restructure.
 - First-person plural ("we built this") where the crew worked the substrate; second-person ("you are reading") where the reader is being walked through. Switch register cleanly between the two.
 - No "look how clever we are" energy. No "this changes everything" energy. No CTAs disguised as analysis.

 Record per-paragraph or per-section findings: PASS or specific FAIL with line/word-cluster citation.

3. **Layer 2 — Lore alignment.** Read the doc against the canonical taxonomy + operating values:

 - Tropo / Studio / Vault used per canonical taxonomy. No pre-v1.8 vocabulary (`"ledger"`, `"Workshop"`, `"workshop manifesto"`) in active prose. Historical changelog rows preserve original naming as honest record.
 - References to crew agents (Mike, Orpheus, Metis, Argus, Vela, Talos, Cosmo, Silas) match current role + lane (e.g., Metis is GTM/strategy not "the writer"; Argus is architecture not "the engineer"). Cross-check against `00-crew-brief.md` if uncertain.
 - References to Tropo subsystems use current names per the L1 canonical entry [eca73d77](../../vault/files/eca73d77.md). No stale primitive names.
 - Soul-level voice discipline: humble, grounded, peer-to-peer. Doesn't claim more than the substrate supports.

 Record per-finding citations.

4. **Layer 3 — Stranger-encounter test.** Read the doc as a 10+ year domain expert encountering Tropo for the first time:

 - Can the reader follow without external context? If a reference assumes internal jargon the reader hasn't been introduced to, flag.
 - **Banned-word check (concrete, not a judgment call).** Grep the doc for Tropo-internal terms that read as jargon to a stranger and have no place in reader-facing copy — flag every hit, don't rely on catching it by feel:
   - **substrate** — internal shorthand for "the underlying governed layer / vault / infrastructure." Reader-facing copy says what it means instead (foundation, groundwork, infrastructure, the underlying system) — never the word itself. (Mike direction 2026-07-21, after it shipped unnoticed across the homepage, How Tropo Works, Market Map, and Who We Follow copy — the word was so embedded in crew usage that Layer 3's own prior wording used it as the example term for jargon. Grep `docs/app/tropo-app` for `substrate` for the still-open backlog.)
   - Add to this list whenever Mike flags a term as jargon — this is a living checklist, not a one-time fix. Don't wait for the next full voice-review pass to apply a newly-banned word to already-shipped copy; that's a Path 2 self-healing item.
 - Does the opening land with a specific moment / receipt / concrete claim, or with category-level marketing-set-up?
 - Does the closing invite reflection on the reader's own work (peer-to-peer), or does it sell?
 - The peer-recognition test: does the reader finish thinking *"that's a real thing they built; I can imagine working that way"* — NOT *"wow, clever"* and NOT *"this reads like a pitch"*?

 Record overall PASS or specific FAIL with which response the doc invites.

4.5. **Substrate-verify-twice check (v1.1 NEW).** Before authoring the voice-review-notes entry, walk every canonical-primitive reference in the artifact under review and verify shape against current canonical. Per defect-class brief at [substrate-verify-twice (83af4ac1)](../../vault/files/83af4ac1.md) Layer 1:

 - **Identify references.** Enumerate references the artifact makes to canonical primitives: capsule schema field names (e.g., `doc_changes_required:` from doc-spec.capsule), enum values (e.g., activation status enum), cited file versions (e.g., "Studio Manifesto v1.0.3"), agent states (e.g., "last modified by A77"). Frontmatter + body both.
 - **Verify the canonical resolves.** For each cited UID, confirm the entry exists in `vault/files/<uid>.md`. Bare UIDs that don't resolve are FAIL — flag with explicit citation.
 - **Verify the cited shape matches.** For each reference to a canonical's field name / enum value / version / state, Read the canonical at the cited UID and confirm the artifact's assumption matches the canonical's CURRENT shape (not a remembered or analogous shape).
 - **Re-verify just before lock.** If more than ~30 minutes have elapsed since the first check OR if other agents have been active in the substrate during the review, repeat the two verifications above just before Step 6 returns. Cheap; catches drift the review session itself introduced or sibling agents introduced concurrently.

 Record findings per-reference: PASS (shape matches), or FAIL with the canonical's actual current shape + the artifact's assumed shape + the resolution path (typically: amend the artifact under review to match canonical; or, if the canonical is the one that drifted, surface as Path 2 inbox finding).

 **Scope guidance:** for tier:summary + tier:subsystem this discipline is gating (PASS required for Step 3 close). For tier:spec spot-checks, this runs alongside the spot-check; findings are recorded inline.

4.5b. **Coordination-channel state check (v1.2 NEW; Layer 1.5).** Per finding [f90791ad](../../vault/files/f90791ad.md) Option A: substrate-verify-twice extends to coordination state, not just canonical state. Before declaring step PASS on a long-running activation (multi-step pipeline; cycle spanning ≥2 turns), verify:

 - **Tail inter-agent channels for posts since activation start.** Read the tail of every relevant bilateral channel (e.g., `channels/argus-<self>.md` + `channels/metis-<self>.md` + `channels/orpheus-vela.md`) AND the `channels/ops.md` head + tail for posts dated within the activation window. For rendered_from_events:true channels (per v1.57 Stream B), use `python3 vault/tools/tropo-query-events.py --since-id <activation-start-event-id>` to query the event log; recipient filter by your party-UID.
 - **Flag scope-affecting posts.** Look for posts that refine, narrow, supersede, or redirect the activation's substantive scope. Specifically: any sibling-agent post recommending lane-defer, scope-narrowing to a subset, work-deferral to a subsequent cycle, or scope-extension. An oblique mention is informational; an explicit directive that contradicts the work already executed in-cycle is a Layer 1.5 finding.
 - **Resolve before PASS.** If a scope-affecting post post-dates the work already done in-cycle, the work is not necessarily wrong (substantive value is real; not waste), but it bypassed coordination. Surface to the directive author at step-close via channel reply with substrate-honest record (work done + scope-variance acknowledged + finding filed). The PASS attest must include the coordination-channel-state acknowledgment.

 Record findings: PASS (no scope-affecting posts since activation start; coordination state clean), or LAYER-1.5-FINDING with channel + post timestamp + scope-variance summary + remediation routing.

 **Scope guidance:** runs at every step-boundary on long-running activations (multi-step pipelines; cycles spanning ≥2 turns). For single-turn cycles, the discipline is trivial (no coordination window for sibling agents to post against). Composes with Step 4.5 v1.1 substrate-verify-twice — canonical-state check + coordination-state check together form the Layer 1 / Layer 1.5 discipline pair.

5. **Author voice-review-notes entry.** Create `vault/files/<uid>.md` (8-hex UID) with frontmatter:

 ```yaml
 ---
 uid: <8-hex>
 type: note
 subtype: voice-review-notes
 title: "Voice review notes — <doc title> (<doc-uid>)"
 doc_reviewed_uid: <doc-uid>
 doc_reviewed_tier: <summary | subsystem | spec>
 voice_review_passed: <true | false>
 reviewed_by: <orpheus-generation-slug>
 reviewed_at: <ISO-8601>
 layers:
   tone_consistency: <PASS | FAIL>
   lore_alignment: <PASS | FAIL>
   stranger_encounter_test: <PASS | FAIL>
 substrate_verify_twice:  # v1.1 NEW — substrate-verify-twice findings list
   passed: <true | false>
   findings: []  # list of {reference, assumed_shape, actual_shape, resolution} entries for any FAIL
 spec_tier_spot_check: <null | summary of prose-heavy sections reviewed>  # only for tier:spec
 owner: orpheus
 created: <ISO-8601>
 status: active
 state: active
 member_of: [<doc-pipeline-activation-uid>]
 ---
 ```

 Body: per-layer findings (one sub-section per layer); specific citations for any FAIL; overall PASS/FAIL summary with what would need to change for FAIL → PASS.

6. **Return the voice-review-notes entry UID.** doc-pipeline Step 3 collects this UID for Step 5 acceptance_evidence.

## Tier-specific application

- **tier:summary** (default voice_review_required: true): full three-layer review; PASS gates Step 3 close
- **tier:subsystem** (default voice_review_required: true): full three-layer review; PASS gates Step 3 close
- **tier:spec** (default voice_review_required: false): self-spot-check on prose-heavy sections (§Intent, §Why, §Studio Shop Signage, §How to Validate body prose); spot-check findings recorded inline in voice-review-notes entry; NOT gating

## Failure-mode behavior

- Layer 1/2/3 FAIL on tier:summary or tier:subsystem doc → voice-review-notes entry records FAIL + specifics; Step 3 does NOT close; doc returns to Step 2 author-doc-substrate for amendment; Step 3 re-runs after amendment
- Spec-tier spot-check surfaces drift: trivial fixes happen inline during review (Path 1 self-healing); substantive drift surfaces to Step 2 (returns the doc) OR files as Path 2 inbox note if cross-cycle

## Composition

- **Operationalizes:** [doc-spec.capsule v1.0 §Voice Review Definition (9a7d314a)](../../vault/files/9a7d314a.md) - the three-layer contract this skill applies
- **Invoked from:** [doc-pipeline Step 3 voice-review-substrate (79c6479c)](../../vault/files/79c6479c.md)
- **Produces:** voice-review-notes entries (type: note, subtype: voice-review-notes) that become acceptance_evidence at [doc-pipeline Step 5 close-activation (343dd5d8)](../../vault/files/343dd5d8.md)
- **Composes with voice canon files:** Shop-Floor Notes canon at [72abbb86](../../vault/files/72abbb86.md) (agentic-builders content); other canons live in section-scoped brand kits at `02-outbox/<medium>/<section>/03-design/`

---

*voice-review skill v1.1 | UID `811856a5` | Orpheus O11 | 2026-05-23 v1.0 + 2026-05-25 v1.1 amendment | Phase C deliverable of v1.51 Three-Pipeline Substrate-Engineering*
*"Three layers + verify-twice: tone consistency + lore alignment + stranger-encounter test, with canonical-primitive references verified before lock. Pristine documentation is real, not aspirational."*
*v1.1 amendment 2026-05-25: Step 4.5 substrate-verify-twice check added per defect-class brief [83af4ac1](../../vault/files/83af4ac1.md) Layer 1. Closes the defect class captured at doc-pipeline v1.52 first production run (5 instances of canonical-shape drift, all fix-on-see absorbed but each cost a remediation cycle). Layer 2 (validator) + Layer 3 (cross-cycle ledger) routed to Argus for v1.53+ engineering bundle scoping.*
