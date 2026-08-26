---
uid: cd1fcd25
title: dev-pipeline
type: pipeline
subtype: workflow-node
name: dev-pipeline
version: 2.0.0
author: argus-a42
owner: argus
domain: tropo-development
status: active
state: active
role: root
created: 2026-05-03
modified: 2026-05-23
modified_by: argus-a80
dev_spec_input_required: true
v1_51_0_changes:
  - '2026-05-23 by argus-a80: Three-Pipeline Substrate-Engineering Phase A retrofit. (1) dev-pipeline now requires dev-spec.capsule v1.0 entry as activation input — engine validates per Pipeline-Runtime Engine Extension v0.1 [51d171f3]. (2) Two NEW step entries inserted in deploy stage [3a7dbdda] between step-5.5 [674af8fe pre-author-release-entry] and step-6 [8654900a produce-release-folder]: step-4.5 trigger-doc-pipeline-activation [0cf86ea5] + step-4.6 trigger-test-pipeline-activation [4f64ec3c]. Both fire in parallel after step-4 [9d4f7e21 update-subsystem-canonical-docs] close; both must complete before step-6 produce-release-folder becomes eligible (multi-input convergence per pipeline.capsule v3.0 DAG primitive). (3) Engine-level enforcement at activation close: dev-pipeline activation cannot close (status → done) until BOTH triggered_doc_spec_uid + triggered_test_spec_uid activations at status:done per [51d171f3 §Three-Pipeline Coupling State Machine]. (4) New chain: 0 → 1 → 2 →
    3 → 5 → 5.5 → 4 → [4.5, 4.6 parallel] → 6 → 7 → 7.5 → 8. Dev-pipeline grows from 11 steps + 1 hanging → 13 steps + 1 hanging. Per cycle brief [1feefe68 v0.2 LOCKED] Phase A scope. Mike-A80 trigger-timing walk 2026-05-23 ratified slot placement; Mike-A80 ignition-key amendment walked rename of activation-input capsule from `design-spec` → `dev-spec` (collision-fix with locked design-spec.capsule v2.1 at UID de5160c0). Companion edits at 9d4f7e21 (next_steps fan-out) + 8654900a (multi-input convergence) + 3a7dbdda (deploy stage children) + dev-spec.capsule v1.0 [c3f68cb5] + engine extension spec [51d171f3]. Talos T9 implements engine extension at runway per argus-talos pair-call channel.'
v2_0_0_two_pipeline_split: 'Amended 2026-08-09 by talos-t40 under Mike-locked dev-spec 0a0a6777; owner: argus preserved per his ruling evt_a2267930c7a21c90_00000020, which is standing write authorization for this build. Root children are now exactly Specify, Build, Test. The Deploy stage 3a7dbdda is deprecated and its release-class nodes move to release-pipeline 634913c2. Dev work ends at Test: no release-plan generation, packaging, doc/test trigger, deploy, publish or release-close node remains in this graph (AC1).'
member_of:
  - b8e5f3a2
children:
  - 03624b7a
  - 3bd8f5b6
  - 74945d48
next_steps: []
default_trust_gradient: auto-with-verification
default_retry_policy:
  max_retries: 0
  backoff: linear
default_timeout_hours: 24
v1_46_0_changes:
  - '2026-05-20 by argus-a76: pipeline.capsule v2.6 → v3.0 retrofit. 9 leaf step entries gained per-step rich schema (step_owner_role + step_verifier_role + verification_class + depends_on_steps + exit_criteria). Root pipeline gained default_trust_gradient + default_retry_policy + default_timeout_hours. Reference example for the v3.0 schema; first pipeline to retrofit through setup-new-pipeline.playbook (45d21cd8). exit_criteria arrays ship empty; future cycles populate detailed DSL assertions as each step''s verification contract crisps.'
v1_52_0_changes:
  - '2026-05-24 by argus-a82: NEW dev-pipeline step entry added — notify-triggered-pipeline-owners [37996741] at step-4.7 position between trigger-step pair (0cf86ea5 + 4f64ec3c) and produce-release-folder [8654900a]. Authored captain-mode per Mike-A82 directive to close owner-awareness gap surfaced when v1.52 first production cycle showed doc-pipeline + test-pipeline activations spawning silently. Step body: agent posts direct surface to each triggered pipeline''s owner''s bilateral channel naming the activation UID + spec UID + cycle context + ''awaiting your processing''. Deploy stage [3a7dbdda] children: array extended from 8 → 9 entries (notify slotted between 4.6 and 5). 0cf86ea5.next_steps amended [8654900a] → [37996741]. 4f64ec3c.next_steps amended [8654900a] → [37996741]. 8654900a.depends_on_steps amended [0cf86ea5, 4f64ec3c] → [37996741]. New chain: 3 → 5 → 5.5 → 4 → [4.5, 4.6 parallel] → 4.7 → 6 → 7 → 7.5 → 8. Companion pipeline-activate.py amendment same session writes owner
    + assigned_to fields on activation entries from pipeline def owner field (board-surfacing enabler — sa.board-agent filter on assigned_to_prefix catches activation as owner''s work without further substrate change). Two-part fix: notify-step = immediate channel-inbox signal; pipeline-activate.py amendment = persistent board surfacing on owner''s next boot.'
v1_48_0_changes:
  - '2026-05-20 by argus-a77: Stream C + Stream D substrate-resident discipline codification. Two NEW dev-pipeline step entries added: (1) pre-author-release-entry [674af8fe] at step-5.5 position between generate-release-notes [804e339e] + produce-release-folder [8654900a] — formalizes the release-entry-stub authoring discipline that was memory-resident Argus behavior across v1.43-v1.46 (V48 gap-flag 2026-05-20); (2) cold-boot-walk [c6b61fb9] at step-7.5 position between external-test [bc6b17ec] + git-commit [3e0bb81e] — formalizes Block 4 close-criterion empirical-validation discipline that was memory-resident Vela behavior across v1.41-v1.46 (Mike-V48 directive 2026-05-20 verbatim ''next release we will extend our pipeline one more step and it will be formal!'' via [89a25cfe]); verification_class:true with 5 exit_criteria (per-persona ≥8 + aggregate ≥8.0 + all binary gates 9/9). Deploy stage [3a7dbdda] children: array extended from 4 → 6 entries. 804e339e.next_steps amended from [a5554670
    hanging-step] → [674af8fe] (canonical chain wired; a5554670 stays hanging for v1.50 grooming). 8654900a.depends_on_steps amended [804e339e] → [674af8fe]. bc6b17ec.next_steps amended [3e0bb81e] → [c6b61fb9]. 3e0bb81e.depends_on_steps amended [bc6b17ec] → [c6b61fb9]. Release-cold-boot-walk.playbook [6f3d2a18] gained dev_pipeline_step: substrate-link to c6b61fb9. Dev-pipeline grows from 9 steps → 11 steps total (10 leaf steps + 1 hanging a5554670 pending v1.50 disposition). Per cycle brief [c184b781 v0.3 LOCKED] Stream C + Stream D MUST-SHIP #6a + #6b. Substrate originally authored under v1.47.0 cycle label; numbering shifted v1.47 → v1.48 per Mike-V49 chain-mutability override 2026-05-21 (Vela V49''s substrate-discipline interrupt cycle took v1.47.0 release tag at 3dbc7d88; Argus''s Cycle B + C + D substrate shifted +1).'
relationships:
  - rel: derived_from
    uid: e1c47a9f
  - rel: governed_by
    uid: e4c8a6b2
  - rel: member_of
    uid: b8e5f3a2
schema_version: 2
extraction_scope: ship
v1_6_changes:
  - '2026-05-04: folder renamed agents/dev.pipeline → agents/dev-pipeline (v1.6 Stream B.1, capsule-vs-instance naming convention enforcement per b6f1e9c4 Decision 5)'
  - '2026-05-05: reparented under tropo-work L0 (b8e5f3a2) per v1.6 Stream B.2'
v1_9_2_changes:
  - '2026-05-07: build stage (3bd8f5b6) gained child step update-subsystem-canonical-docs (9d4f7e21) per v1.9.2 Stream A4. Build stage now has 2-step linear chain: 24f16afc → 9d4f7e21. Pipeline structure goes from 8 steps to 9. v1.9.2 Stream A3 amends pipeline.capsule v2.3 → v2.4 to activate the v2.3 pre-doc §Sub-pattern entry.'
---

# dev-pipeline

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → **dev-pipeline**
<!-- nav-block:end -->

## Purpose

Governs **development** work from a locked dev-spec to a verified tested SHA. The three stages are
**Specify → Build → Test**. Ignition is the dev-spec lock; the terminal act is
`verify-dev-spec` passing. Closure is a journaled side effect of that pass — there is no close
WorkflowNode in this graph by design.

**This pipeline produces no release artifacts.** No release-plan generation, no packaging, no
release folder, no zip, no publish, no deploy, no doc/test trigger legs. All of that belongs to
[release-pipeline `634913c2`](634913c2.md), which is ignited only by a locked *release-plan* and
closed only by verified publication. `"build complete"` is an ordinary **done** dev-spec; a release
fans in done specs by explicit list. There is no park state between the two.

Does NOT govern: ideation or design-brief authoring (that happens in the inbox before the spec
exists); release engineering of any kind (see above); research- or content-only cycles that yield no
committed substrate (use a domain-specific pipeline).

## Structure

```
dev-pipeline (cd1fcd25) — v2.0.0
├── specify (03624b7a)
│   └── confirm-dev-spec-snapshot (0c6518ef)      verification-class
├── build (3bd8f5b6)
│   ├── implement-dev-spec (fa3a49c8)
│   └── update-subsystem-canonical-docs (9d4f7e21) verification-class · terminal in stage
└── test (74945d48)
    └── verify-dev-spec (0b6b244c)                 verification-class · TERMINAL
```

Flow: specify → build → test, linear and forward-only. **Three stages, four leaf steps.**

*(v1.x had a fourth stage, Deploy, and nine steps. It was deprecated on 2026-08-09 in the
two-pipeline split. The v1 nodes are archived rather than deleted — seven historical activations
hold those UIDs in their own immutable snapshots, and retiring a definition must not make the past
unresolvable. If you are reading an old run journal, resolve those UIDs through the archive index.)*

## Nodes

| UID | Name | Role | Children | Next |
|-----|------|------|----------|------|
| [03624b7a](03624b7a.md) | specify | stage | 1 | `[3bd8f5b6]` |
| [3bd8f5b6](3bd8f5b6.md) | build | stage | 2 | `[74945d48]` |
| [74945d48](74945d48.md) | test | stage | 1 | `[]` terminal |
| [0c6518ef](0c6518ef.md) | confirm-dev-spec-snapshot | step | 0 | `[fa3a49c8]` |
| [fa3a49c8](fa3a49c8.md) | implement-dev-spec | step | 0 | `[9d4f7e21]` |
| [9d4f7e21](9d4f7e21.md) | update-subsystem-canonical-docs | step | 0 | `[]` terminal in stage |
| [0b6b244c](0b6b244c.md) | verify-dev-spec | step | 0 | `[]` **terminal** |

Every node above is `owner: argus`. No node in this table belongs to another pipeline; if you find
one that does, that is a defect — report it rather than following it.

## Flow Rules

Execution is linear and forward-only. A stage completes when all its steps are done; the stage's
`next_steps:` carries the advance. Within a stage, each step's `next_steps:` carries the advance,
and the last step in a stage is terminal within it (`next_steps: []`).

**Ignition.** A run exists because a dev-spec was locked. The lock is atomic with pipeline-activation
registration (ADR-052), so the chain dev-spec ↔ activation ↔ build ↔ tested SHA is complete by
construction rather than by discipline. The Specify stage authors nothing and re-pins nothing — it
*confirms* the snapshot the lock already wrote.

**Verification class.** Three of the four steps are `verification_class: true` and carry their own
`verification_command:`. A verification-class step reaches `verified` only on a real verification
receipt; an executor's attestation cannot promote it, and the approver may not be the executor.

**Terminal and closure.** `verify-dev-spec` binds every acceptance criterion and mutation obligation
to ONE unchanged 40-hex tested-tree SHA. Closure is journaled when it passes. There is no close node
to run.

**Branching.** None. This is a fully linear graph.

## Cold-Boot Walk-Through

*You are a stranger. You have a Studio, a dev-spec you wrote, and no other context. This is the
whole cycle.*

**Before you start**, your dev-spec must declare `acceptance_criteria:` in its **frontmatter** —
each with an `id`, a `behavior`, and a `verify:` block naming a real command. The lock refuses a spec
without them, and it is right to: a lock with no criteria the machine can find is a close nobody can
judge. `committed_substrate:` may be empty at lock time — a spec is locked *before* it is built, so
that warns and proceeds.

**Step 0 — ignite.** Lock the spec. This is one gesture and it both locks and opens the run:

```
python3 vault/tools/tropo-lock-dev-spec.py --dev-spec-uid <your-spec-uid> --locked-by <you>
```

It writes the activation, the run root, and the declaration snapshot in one transaction. If it
refuses, nothing partial is left behind. Note the activation UID it prints — every command below
takes it.

**Step 1 — confirm-dev-spec-snapshot (`0c6518ef`).** Specify's only step. Confirm the run's snapshot
matches what was locked: `run.snapshot.dev_spec_sha256` equals the locked spec's content hash, and
the snapshot's declarations cover every leaf step of the pinned definition. The snapshot GOVERNS the
run as executable content — recovery recomputes the digest it checks, so a forged green does not
survive.

```
python3 vault/tools/9e7003b1.py --activation-uid <act> step-start 0c6518ef
python3 -m pytest -q vault/tools/tests/test_ac2_dev_lock_snapshot_transaction.py
python3 vault/tools/9e7003b1.py --activation-uid <act> verify-step 0c6518ef
```

**Step 2 — implement-dev-spec (`fa3a49c8`).** Build the thing. The exit criterion is that **every**
`committed_substrate` target named in the spec has a machine-readable artifact link. Not a claim
that you built it — a link.

```
python3 vault/tools/9e7003b1.py --activation-uid <act> step-start fa3a49c8
python3 vault/tools/9e7003b1.py --activation-uid <act> step-complete fa3a49c8 --artifact-links <paths>
```

**Step 3 — update-subsystem-canonical-docs (`9d4f7e21`).** Terminal within Build. Update the
canonical documentation for every subsystem this cycle touched. Verification is the executor's own
exit code:

```
python3 vault/tools/9e7003b1.py --activation-uid <act> step-start 9d4f7e21
python3 vault/tools/6342d0ca.py
python3 vault/tools/9e7003b1.py --activation-uid <act> verify-step 9d4f7e21
```

When this passes, Build is complete and the stage advances to Test.

**Step 4 — verify-dev-spec (`0b6b244c`). TERMINAL.** Every acceptance criterion and every mutation
obligation must bind to ONE unchanged 40-hex tested-tree SHA. One SHA, not several; unchanged, not
re-measured after a fix.

```
python3 vault/tools/9e7003b1.py --activation-uid <act> step-start 0b6b244c
python3 -m pytest -q vault/tools/tests/test_two_pipeline_split_0a0a6777.py
python3 vault/tools/9e7003b1.py --activation-uid <act> terminal-verify --tested-sha <40-hex>
```

**There is no step 5.** When terminal-verify passes, dev closure is journaled as a side effect. Your
dev-spec is now **done**. If this work is going to ship, a release-plan will fan it in by explicit
list and the [release-pipeline](634913c2.md) takes over from there — that is a separate ignition, a
separate run, and a separate human decision.

## Known Enforcement Gaps

*Honest and current as of 2026-08-24. Each is a real thing a stranger can hit.*

| Gap | Consequence | Owner |
|---|---|---|
| **The terminal step's verification command runs the whole two-pipeline contract, including release-pipeline acceptance criteria.** `0b6b244c` declares `pytest test_two_pipeline_split_0a0a6777.py`, which exercises release ACs as well as dev ones. A dev cycle's verdict therefore depends on release-pipeline tests being green. It is red today on AC07, whose delegated suites assert on refusal *wording* that has since been rewritten. **Being cured:** AC6 of the Stream 2 spec `1a478c48` makes this verdict dev-scoped (run-own evidence completeness + close integrity); the split suite stays a studio/release-side check. Talos builds; Argus pairs as non-author verifier at close. | A stranger studio that has never cut a release can fail its dev-pipeline's final step for reasons unrelated to its own work. **This is the gap that most directly threatens the stranger bar.** | talos (build) / metis (spec) |
| **~~Lock snapshot vs. runtime activation contract~~ RESOLVED 2026-08-24.** G111 measured this 2026-08-23 (`step not in activation contract` refusals on a lock-opened run) against the pre-repair tree. Talos T50 re-ran the exact repro against the current definition (real lock, real bootstrap, real step-start, all four declared steps) and it no longer reproduces — zero refusals. Metis G112 ruled on the finding (`ac_premise_correction`, run 8098be20): the measurement was pre-repair; argus-a156's 2.0.1 dev-graph fix (below, same day) already cured it. Permanent guard: `vault/tools/tests/test_lock_snapshot_declares_live_contract_v192.py`. | *(Historical — kept so a reader who found the old claim elsewhere isn't left thinking it's still open.)* | — |
| **`lib/release_events.py`'s `_snapshot_step_uids()` doesn't recognise the `declared_steps` key.** Found auditing AC2's second named reader (`AuthorizationContext.observe`): the helper checks for `steps`/`children`/`nodes` list-keys, but the real snapshot's field is `declared_steps` — it silently reads zero steps off every real run, dev or release. Not this pipeline's own file to fix (Stream 1 substrate); reported to Argus A156 2026-08-24. | `AuthorizationContext.observe()`'s `snapshot_step_uids` is empty on every real run until fixed — anything gating on it is blind. | argus |
| **`804e339e` (generate-release-notes) is a draft orphan.** A v1 node that was neither archived with its siblings nor adopted by either pipeline; `member_of` is empty. | Resolves to nothing meaningful; will confuse anyone auditing the v1→v2 migration. | argus |

*Gaps are listed because they are true, not because they are scheduled. If you are reading this in a
customer Studio and one of them bites you, that is our defect and we would rather you saw it coming.*

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-03 | Initial draft, scaffolded from design brief e1c47a9f. Three stages (specify/build/deploy), eight steps. | argus-a42 |
| 1.0.1 | 2026-05-04 | Folder rename `agents/dev.pipeline` → `agents/dev-pipeline`; reparented under tropo-work (b8e5f3a2). No structural change. | argus-a44 |
| 1.1.0 | 2026-05-07 | Build stage gained `update-subsystem-canonical-docs` (9d4f7e21). 8 → 9 leaf steps. | argus-a49 |
| — | 2026-05-20 → 2026-05-24 | v1.46 / v1.48 / v1.51 / v1.52 amendments — per-step rich schema, pre-author-release-entry, cold-boot-walk, doc/test trigger legs, notify-triggered-pipeline-owners. All landed in the Deploy stage, all subsequently relocated or archived by v2.0.0. Detail preserved in this entry's frontmatter. | argus-a76/a77/a80/a82 |
| **2.0.0** | **2026-08-09** | **The two-pipeline constitutional split** (Mike-locked dev-spec 0a0a6777, built by talos-t40, owner argus preserved per standing authorization). Root children are now exactly Specify / Build / Test. The Deploy stage 3a7dbdda is deprecated and its release-class nodes move to release-pipeline 634913c2. Dev work ends at Test: no release-plan generation, packaging, doc/test trigger, deploy, publish or release-close node remains in this graph (AC1). Seven v1 nodes archived, not deleted, so historical activations stay resolvable. | talos-t40 |
| 2.0.3 | 2026-08-24 | **Known Enforcement Gaps table corrected.** The "lock snapshot vs. runtime activation contract" gap row was stale: G111's 2026-08-23 measurement predated argus-a156's same-day 2.0.1 body/graph repair, which already cured it. Talos T50 re-ran the exact repro against the current tree (real lock, bootstrap, and step-start, zero refusals) while building v1.92 Stream 2's AC2 (`1a478c48`) and found the row claiming otherwise. Replaced with the resolution and with the ACTUAL remaining AC2 finding: `lib/release_events.py`'s `_snapshot_step_uids()` doesn't recognise the `declared_steps` key (Argus A156's lane, reported same day). | talos-t50 |
| 2.0.2 | 2026-08-24 | **The seven nodes under this active root flipped `draft` → `active`.** They were minted draft at the split build and never flipped when the split shipped in v1.88 and then closed four production cycles — the automatic-half/manual-half class. The runtime ignores the field at step-start, so `draft` here meant minted-draft-never-flipped, not unfinished-design. Decided by metis-g112 on A156's put-to-me (correlation `evt_b51c083be28ac6fe_00000146`); executed by argus-a156. The record now says what is true: the constitution is live. | argus-a156 |
| 2.0.1 | 2026-08-24 | **Body reconciled to the v2.0.0 graph.** Every section above described the v1.x machine — a Deploy stage, nine steps, `generate-release-notes` / `produce-release-folder` / `external-test` / `git-commit`, and a cold-boot walk-through that instructed the reader to author a release-plan and produce a zip from a dev run. The 2.0.0 amendment changed three lines of frontmatter and left the prose whole, so for fifteen days the shipped definition taught the shape the split had just removed. Of the ten node UIDs the old §Nodes table claimed, six were archived, two were draft, and two — `8654900a`, `bc6b17ec` — were live steps of the **release** pipeline. Found by metis-g112 (body) and argus-a156 (nodes) on the same day. Companion repairs: `9d4f7e21.next_steps` no longer flows into the release graph; the AC6-relocated trigger legs' stale parent back-pointers now name release Assemble; `0c6518ef`'s verification command is runnable as written. | argus-a156 |

---

*dev-pipeline | WorkflowNode root | v2.0.0 graph, body at 2.0.1 | argus-a42 (v1.0.0) → argus-a49 (v1.1.0) → talos-t40 (v2.0.0 graph) → argus-a156 (v2.0.1 body)*
*Derived from: [dev-pipeline + vault inbox primitive (e1c47a9f)](e1c47a9f.md) · governed by [pipeline.capsule (e4c8a6b2)](e4c8a6b2.md)*
*"Dev work ends at Test. If it ships, that is a different pipeline, a different ignition, and a human's decision."*
