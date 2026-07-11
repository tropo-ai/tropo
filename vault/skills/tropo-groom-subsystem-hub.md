---
uid: a01e15ef
name: groom-subsystem-hub
type: how-to
status: active
owner: argus
created: 2026-05-05
created_by: argus-a45
modified: 2026-05-09
modified_by: argus-a53
version: 1.0.0
governed_by: a7c3f489
aligned_with:
  - 8a4e21c5
  - 18a3d11a
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
purpose: Apply the Hub Update Discipline from subsystem-hub.capsule §Hub Update Discipline to a subsystem hub entry
when: When sa.hub-groomer dispatches in worker mode (groom a hub) or judge mode (assess hub freshness)
trigger_description: Reach for this when grooming a subsystem hub entry — applies subsystem-hub.capsule §Hub Update Discipline (Current State refresh, release_history maintenance, capability roll-up). Used by sa.hub-groomer in both worker mode (perform the grooming) and judge mode (assess whether the hub needs grooming). Hub grooming is non-trivial — refreshing the Current State block requires understanding what shipped in the recent release cycle and what changed about the subsystem's surface.
relationships:
  - rel: implements
    to: 8a4e21c5
  - rel: bound-to
    to: 18a3d11a
subsystem_hub:
  - 76bab75f
---

# Skill: groom-subsystem-hub

*The per-hub grooming procedure invoked by [`sa.hub-groomer`](../../agents/sa/sa.hub-groomer/sa.hub-groomer.md) in both worker and judge modes. Produces a recommended draft of the four grooming surfaces (release_history row + Change Log entry + Current State section + optional sections) that satisfy [subsystem-hub.capsule v1.3 §Hub Update Discipline](../capsules/subsystem-hub.capsule.md).*

---

## When to use

Invoked by sa.hub-groomer instances at release ship gate. Not for general-purpose hub authoring.

**Worker mode** (one of N parallel workers): produce one independent grooming draft for one touched hub.
**Judge mode** (one judge per touched hub, runs after all workers complete): reconcile worker drafts into unified recommendation.

The invoking executor (dev-pipeline step `groom-subsystems`) writes the final groomed hub body + corresponding `subsystem-registry.jsonl` row per the recommendation.

---

## Inputs

Common to both modes:
- **Target hub:** UID + body of the subsystem hub being groomed (loaded by sa.hub-groomer at boot).
- **Release context:** UID + body of the release entry being authored, the release plan, build entry, release notes.
- **Channel file:** path to the shared IPC file for this hub's grooming session.

Worker-only:
- **Worker number:** 1 OR 2 (identifies which worker section to write under).

Judge-only:
- **Worker drafts:** content already written to channel file under `## Worker 1 Draft` and `## Worker 2 Draft` headers.

---

## Worker mode procedure

1. **Identify shipped artifacts that touched this subsystem.** Cross-reference the release notes + build manifest + release plan's `sub_systems:` array against the target hub's `subsystem_name:`. Produce a list of UIDs + one-line descriptions.

2. **Author the `release_history:` frontmatter row.** Single YAML record:
   ```yaml
   - release_uid: <release-entry-uid>
     release_version: <semver from release_version: field>
     summary: <one-line; ≤ 200 chars; describes what the release did to this subsystem>
     registry_uid: <pending>   # placeholder; executor backfills after writing registry row
     streams_touched: [<optional array of stream identifiers from release plan §2; OMIT if whole release touched the subsystem>]
   ```
   `streams_touched:` is OPTIONAL and ONLY populated when the release plan declares streams AND only some of them touched the subsystem. Whole-release touches OMIT the field.

3. **Author the `## Change Log` entry.** Per [§Change Log Entry Format](../capsules/subsystem-hub.capsule.md):
   ```markdown
   ### v<release_version> — <release_date> — Shipped

   - [<artifact-uid> <artifact-title>] — <one-line description>
   - ...

   **Impact:** <one- or two-sentence narrative answering "what should the subsystem reader know NOW that they didn't before?">

   **Next:** <optional — what's queued for next release; delete line if nothing>
   ```

4. **Update the `## Current State` section.** Rewrite (not append) the section in 3-6 sentences (~150-300 words) reflecting post-ship reality. Anchor to the new `last_release_reflected:` value. Truth-today shape — describe the subsystem's current state, not its history.

5. **Update optional sections IF present.** If the target hub has `## Open Questions`, prune resolved questions + add new ones surfaced by the release. If the target hub has `## Architectural Constraints`, update entries that the release changed (rare). If sections aren't present, do NOT add them as part of grooming.

6. **Write the worker draft to the channel file** under `## Worker N Draft` header (where N is the worker number). Use the output format in [sa.hub-groomer §Output Format](../../agents/sa/sa.hub-groomer/sa.hub-groomer.md).

7. **Author worker rationale** (2-4 sentences) naming the substantive grooming choices and any judgment calls.

---

## Judge mode procedure

1. **Read both worker drafts** from the channel file.

2. **Identify divergences across all 4 grooming surfaces:**
   - `release_history:` row content (release_uid + version usually identical; summary + streams_touched may diverge)
   - `## Change Log` entry (artifact list completeness + impact narrative)
   - `## Current State` section (substantive reality vs. surface differences)
   - Optional sections updates (if present)

3. **Categorize divergences:**
   - **Trivial wording** (workers said the same thing different ways) — pick the clearer phrasing.
   - **Substantive content** (one worker included an artifact the other missed; one worker characterized impact differently) — reconcile based on which worker's draft better matches the actual release deltas.
   - **Conflict** (workers disagree on whether something happened) — investigate via release deltas; if unresolvable, flag for executor review with both perspectives.

4. **Produce the unified draft** by reconciling per the categorization. Do NOT default to one worker; integrate the strongest version of each surface from each draft.

5. **Author the divergence table** with reconciliation rationale per surface (see [sa.hub-groomer §Output Format](../../agents/sa/sa.hub-groomer/sa.hub-groomer.md)).

6. **Author the convergence-by-disagreement verdict:**
   - **HEALTHY** — workers diverged on details (wording / framing / minor inclusions) but converged on substance. Most common; expected pattern. The pattern A44's swarm proved on the v1.7 audit.
   - **SUSPICIOUS** — workers diverged on substance (different facts about what shipped, contradictory impact assessments). Flag for human review; the unified draft includes both perspectives explicitly.
   - **TRIVIAL** — workers near-identical. Honest signal that one worker may have copied the other (rare in BATCH mode but possible) OR both workers missed the same context. Recommend executor re-run with different worker prompts before accepting.

7. **Write the unified recommendation to the channel file** under `## Judge Recommendation` header.

8. **Author judge rationale** (2-4 sentences) naming the substantive reconciliation choices.

---

## Outputs

Both modes write to the channel file. The invoking executor reads from the channel file, reviews, and writes the final groomed hub body + corresponding `subsystem-registry.jsonl` row.

---

## Constraints

- **No direct hub writes.** Skill produces drafts; executor writes finals.
- **Worker isolation.** Workers do NOT read each other's drafts — preserves independence for convergence-by-disagreement signal.
- **Judge isolation from worker work.** Judge does NOT produce worker drafts; just reconciles.
- **No content invention.** Drafts summarize shipped reality. Don't claim impact the release notes don't support.
- **Grooming, not authoring.** If the target hub lacks an optional section, don't add it. Authoring new sections is its own discipline (per [§Adding a New Subsystem in v1.3 capsule](../capsules/subsystem-hub.capsule.md)).

---

## Worked example

For v1.7 ship's own dogfood gate (Gate 6 of [release plan e29c0ec3](../../vault/files/e29c0ec3.md)):

- 6 touched subsystem hubs (all 6 active hubs, since v1.7 is documentation-as-release-deliverable's first instance).
- For each: executor (dev-pipeline step `groom-subsystems`) dispatches sa.hub-groomer × 2 workers (parallel) + sa.hub-groomer × 1 judge (sequential after workers).
- 6 channel files (one per hub) accumulate worker drafts + judge recommendations.
- Executor reviews 6 judge recommendations + writes 6 hub-side `release_history:` rows + 6 corresponding `subsystem-registry.jsonl` rows + 6 `## Current State` rewrites.

---

*groom-subsystem-hub.skill | v1.0.0 | argus-a45 | 2026-05-05 (v1.7 Stream A6)*
*"Workers diverge on details. Judge names divergences. Executor writes finals."*
