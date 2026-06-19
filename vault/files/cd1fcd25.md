---
uid: cd1fcd25
title: "dev-pipeline"
type: pipeline
subtype: workflow-node
name: "dev-pipeline"
version: "1.2.0"
author: argus-a42
owner: argus
domain: tropo-development
status: active
state: active
role: root
created: 2026-05-03
modified: 2026-05-23
modified_by: argus-a80
dev_spec_input_required: true   # NEW v1.51.0 Phase A: dev-pipeline activations require dev-spec.capsule v1.0 entry as activation input; engine refuses activation without compliant dev-spec per Pipeline-Runtime Engine Extension v0.1 [51d171f3] §Activation-Input Validation. Pre-v1.51 cycles grandfathered per dev-spec.capsule Rule 7 (engine WARN, not ERROR, during v1.51 grandfather period).
v1_51_0_changes:
  - "2026-05-23 by argus-a80: Three-Pipeline Substrate-Engineering Phase A retrofit. (1) dev-pipeline now requires dev-spec.capsule v1.0 entry as activation input — engine validates per Pipeline-Runtime Engine Extension v0.1 [51d171f3]. (2) Two NEW step entries inserted in deploy stage [3a7dbdda] between step-5.5 [674af8fe pre-author-release-entry] and step-6 [8654900a produce-release-folder]: step-4.5 trigger-doc-pipeline-activation [0cf86ea5] + step-4.6 trigger-test-pipeline-activation [4f64ec3c]. Both fire in parallel after step-4 [9d4f7e21 update-subsystem-canonical-docs] close; both must complete before step-6 produce-release-folder becomes eligible (multi-input convergence per pipeline.capsule v3.0 DAG primitive). (3) Engine-level enforcement at activation close: dev-pipeline activation cannot close (status → done) until BOTH triggered_doc_spec_uid + triggered_test_spec_uid activations at status:done per [51d171f3 §Three-Pipeline Coupling State Machine]. (4) New chain: 0 → 1 → 2 → 3 → 5 → 5.5 → 4 → [4.5, 4.6 parallel] → 6 → 7 → 7.5 → 8. Dev-pipeline grows from 11 steps + 1 hanging → 13 steps + 1 hanging. Per cycle brief [1feefe68 v0.2 LOCKED] Phase A scope. Mike-A80 trigger-timing walk 2026-05-23 ratified slot placement; Mike-A80 ignition-key amendment walked rename of activation-input capsule from `design-spec` → `dev-spec` (collision-fix with locked design-spec.capsule v2.1 at UID de5160c0). Companion edits at 9d4f7e21 (next_steps fan-out) + 8654900a (multi-input convergence) + 3a7dbdda (deploy stage children) + dev-spec.capsule v1.0 [c3f68cb5] + engine extension spec [51d171f3]. Talos T9 implements engine extension at runway per argus-talos pair-call channel."
member_of:
  - "b8e5f3a2"   # tropo-work L0 root (NEW v1.6 reparent per Stream B.2)
children:
  - 03624b7a   # specify stage
  - 3bd8f5b6   # build stage
  - 3a7dbdda   # deploy stage
next_steps: []
default_trust_gradient: auto-with-verification
default_retry_policy:
  max_retries: 0
  backoff: linear
default_timeout_hours: 24
v1_46_0_changes:
  - "2026-05-20 by argus-a76: pipeline.capsule v2.6 → v3.0 retrofit. 9 leaf step entries gained per-step rich schema (step_owner_role + step_verifier_role + verification_class + depends_on_steps + exit_criteria). Root pipeline gained default_trust_gradient + default_retry_policy + default_timeout_hours. Reference example for the v3.0 schema; first pipeline to retrofit through setup-new-pipeline.playbook (45d21cd8). exit_criteria arrays ship empty; future cycles populate detailed DSL assertions as each step's verification contract crisps."
v1_52_0_changes:
  - "2026-05-24 by argus-a82: NEW dev-pipeline step entry added — notify-triggered-pipeline-owners [37996741] at step-4.7 position between trigger-step pair (0cf86ea5 + 4f64ec3c) and produce-release-folder [8654900a]. Authored captain-mode per Mike-A82 directive to close owner-awareness gap surfaced when v1.52 first production cycle showed doc-pipeline + test-pipeline activations spawning silently. Step body: agent posts direct surface to each triggered pipeline's owner's bilateral channel naming the activation UID + spec UID + cycle context + 'awaiting your processing'. Deploy stage [3a7dbdda] children: array extended from 8 → 9 entries (notify slotted between 4.6 and 5). 0cf86ea5.next_steps amended [8654900a] → [37996741]. 4f64ec3c.next_steps amended [8654900a] → [37996741]. 8654900a.depends_on_steps amended [0cf86ea5, 4f64ec3c] → [37996741]. New chain: 3 → 5 → 5.5 → 4 → [4.5, 4.6 parallel] → 4.7 → 6 → 7 → 7.5 → 8. Companion pipeline-activate.py amendment same session writes owner + assigned_to fields on activation entries from pipeline def owner field (board-surfacing enabler — sa.board-agent filter on assigned_to_prefix catches activation as owner's work without further substrate change). Two-part fix: notify-step = immediate channel-inbox signal; pipeline-activate.py amendment = persistent board surfacing on owner's next boot."
v1_48_0_changes:
  - "2026-05-20 by argus-a77: Stream C + Stream D substrate-resident discipline codification. Two NEW dev-pipeline step entries added: (1) pre-author-release-entry [674af8fe] at step-5.5 position between generate-release-notes [804e339e] + produce-release-folder [8654900a] — formalizes the release-entry-stub authoring discipline that was memory-resident Argus behavior across v1.43-v1.46 (V48 gap-flag 2026-05-20); (2) cold-boot-walk [c6b61fb9] at step-7.5 position between external-test [bc6b17ec] + git-commit [3e0bb81e] — formalizes Block 4 close-criterion empirical-validation discipline that was memory-resident Vela behavior across v1.41-v1.46 (Mike-V48 directive 2026-05-20 verbatim 'next release we will extend our pipeline one more step and it will be formal!' via [89a25cfe]); verification_class:true with 5 exit_criteria (per-persona ≥8 + aggregate ≥8.0 + all binary gates 9/9). Deploy stage [3a7dbdda] children: array extended from 4 → 6 entries. 804e339e.next_steps amended from [a5554670 hanging-step] → [674af8fe] (canonical chain wired; a5554670 stays hanging for v1.50 grooming). 8654900a.depends_on_steps amended [804e339e] → [674af8fe]. bc6b17ec.next_steps amended [3e0bb81e] → [c6b61fb9]. 3e0bb81e.depends_on_steps amended [bc6b17ec] → [c6b61fb9]. Release-cold-boot-walk.playbook [6f3d2a18] gained dev_pipeline_step: substrate-link to c6b61fb9. Dev-pipeline grows from 9 steps → 11 steps total (10 leaf steps + 1 hanging a5554670 pending v1.50 disposition). Per cycle brief [c184b781 v0.3 LOCKED] Stream C + Stream D MUST-SHIP #6a + #6b. Substrate originally authored under v1.47.0 cycle label; numbering shifted v1.47 → v1.48 per Mike-V49 chain-mutability override 2026-05-21 (Vela V49's substrate-discipline interrupt cycle took v1.47.0 release tag at 3dbc7d88; Argus's Cycle B + C + D substrate shifted +1)."
relationships:
  - rel: derived_from
    uid: e1c47a9f   # dev-pipeline + vault inbox primitive (design brief)
  - rel: governed_by
    uid: e4c8a6b2   # pipeline.capsule v2.4 (v1.9.2 Stream A3 amendment)
  - rel: member_of
    uid: b8e5f3a2   # tropo-work L0 (v1.6 reparenting)
schema_version: 2
extraction_scope: ship
v1_6_changes:
  - "2026-05-04: folder renamed agents/dev.pipeline → agents/dev-pipeline (v1.6 Stream B.1, capsule-vs-instance naming convention enforcement per b6f1e9c4 Decision 5)"
  - "2026-05-05: reparented under tropo-work L0 (b8e5f3a2) per v1.6 Stream B.2"
v1_9_2_changes:
  - "2026-05-07: build stage (3bd8f5b6) gained child step update-subsystem-canonical-docs (9d4f7e21) per v1.9.2 Stream A4. Build stage now has 2-step linear chain: 24f16afc → 9d4f7e21. Pipeline structure goes from 8 steps to 9. v1.9.2 Stream A3 amends pipeline.capsule v2.3 → v2.4 to activate the v2.3 pre-doc §Sub-pattern entry."
---

# dev-pipeline

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → **dev-pipeline**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/tropo-work/dev-pipeline/cd1fcd25 — dev-pipeline.md](../../00-tropo-nav/00-tropo-active/tropo-work/dev-pipeline/cd1fcd25%20%E2%80%94%20dev-pipeline.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-active/tropo-work/dev-pipeline/cd1fcd25 — dev-pipeline.md](argo-os/00-tropo-nav/00-tropo-active/tropo-work/dev-pipeline/cd1fcd25%20%E2%80%94%20dev-pipeline.md)

**🔗 This file** — UID `cd1fcd25` · type `pipeline` · state `active` · status `active`

**↓ Children (457):**
  - **board-snapshot:** [dev-pipeline — Project Board (2026-05-15 snapshot)](779fe4f2.md)
  - **decision:** [ADR-042 — Permanent Removal of starter/ Folder ...](9275b15e.md)
  - **design-brief (87):** [AFO Manifesto Stress Test — Real-World Pressure...](b3e9c4a7.md) · [Agent-Activation Hardening — Testing Sweep + Pl...](9e33c886.md) · [Agentic Placement Protocol for the Import Primi...](e8d2f3a1.md) · [Bind verification_class:true steps to a real ma...](f0ae00bf.md) · [Bring Your Work In — Import Primitive Design Brief](cfc99baa.md) · [Case-Study Piece (6c4a8e21) - Full Publish-Pipe...](4f8c2a91.md) · [check-one.py — targeted single-entry validator ...](2ddad3be.md) · [core.capsule amendment — require `title:` (disp...](ec6bac83.md) · + 79 more
  - **design-spec (11):** [Enforce-First — Per-Type Field-Enum Enforcement...](addc4490.md) · [member_of DISAMBIGUATE — finish the v2.5 parent...](6f5bb2cb.md) · [pipeline-runtime.py — v1.46.0 Design Spec (Sequ...](2b809e0f.md) · [pipeline.capsule v3.0 + pipeline-run.capsule v2...](8e5b3c47.md) · [state: active → current — Archive-Flag Value Re...](2360da33.md) · [Studio Query Runtime (SQLite over /vault/files/...](fc114e57.md) · [Tropo-OS v1.35.0 — Cascade Capability + Minimal...](d2f8c194.md) · [Tropo-OS v1.36.0 — Design Spec: Hello Tropo Tut...](079052d9.md) · + 3 more
  - **dev-spec (11):** [check-events — one identity-resolved gesture th...](dabe7c64.md) · [emit-on-completion — a completed unit of work c...](2fe61817.md) · [emit-on-party-identity — an agent cannot send f...](81e52840.md) · [Immutable Agent Identity — one canonical party-...](e85d2d2c.md) · [Tropo-OS v1.69 — Agent + Playbook Unification +...](0c61a52b.md) · [Tropo-OS v1.70 — Publish-Proven + Bulletproof C...](c036dd4b.md) · [Tropo-OS v1.72 Move 1 — ENFORCE the declared st...](8082aad0.md) · [Tropo-OS v1.72 Move 4 — DISAMBIGUATE the 6 over...](ca349830.md) · + 3 more
  - **doc-spec (9):** [v1.53.0 — Three-Pipeline Discipline Compounding...](c660ec29.md) · [v1.54.0 — Engine-Discipline Hardening Triad — D...](cae8ae05.md) · [v1.55.0 — Messaging Foundation — Doc-Spec (even...](c2f4e8a1.md) · [v1.56.0 — Tools-in-Vault Pillar 1 Single-File R...](4a3f2e8c.md) · [v1.57.0 — Stream B Projection Renderer — Doc-Spec](2c8e4b71.md) · [v1.58.0 — Messaging Arc Operational Completenes...](7b4f1a92.md) · [v1.59.0 — Structural-Discipline Amendment Cycle...](e4da5b14.md) · [v1.60.0 — Pillar 1 Closes at Three Surfaces — D...](08699c6f.md) · + 1 more
  - **document (9):** [Captain](a5f4b26b.md) · [Orpheus Standing Plan — Closed Cycle Archive (v...](a7c3f1d9.md) · [Setup New Pipeline](45d21cd8.md) · [Tropo-OS Dev-Pipeline Roadmap](b2c4f01e.md) · [Tropo-OS v1.49.0 — Release Notes](9cd33847.md) · [Tropo-OS v1.50.0 — Release Notes](cbc05278.md) · [v1.70 Build-Backlog Disposition — drive-to-zero...](d370f34d.md) · [We Built a Company With AI Agents Who Die Every...](a42503e9.md) · + 1 more
  - **note (125):** [A85-stub schema-drift pattern — fourth consecut...](a7e1b5c4.md) · [ADR-040 enforcement gap — 21 argo-os/ files git...](8f2e1a47.md) · [ADR-040 vault-tracking doctrine drift — enginee...](d8a3b7f2.md) · [Agent root project per agent — Level-1 trunk en...](328a6471.md) · [agent-retire.playbook v2.6 → v2.7 — drop or nar...](3e433fa4.md) · [agent-retire.playbook — symmetric structural en...](360a5a55.md) · [the Studio — Master Work Board (Mike-V48 direc...](7c351d76.md) · [Argus L1 v2.0 queue — new + required work (orga...](9a19e277.md) · + 117 more
  - **pipeline:** [groom-subsystems — dev-pipeline step (NEW v1.7)](a5554670.md)
  - **project (114):** [01-inbox](0a1a36fe.md) · [dev-pipeline — Activation Root (2026-05-19)](90426792.md) · [dev-pipeline — Activation Root (2026-05-20)](102604e5.md) · [dev-pipeline — Activation Root (2026-05-20)](5274f77f.md) · [dev-pipeline — Activation Root (2026-05-20)](559281f2.md) · [dev-pipeline — Activation Root (2026-05-22)](6c3a329d.md) · [dev-pipeline — Activation Root (2026-05-22)](ee0e0755.md) · [dev-pipeline — Activation Root (2026-05-24)](83db7c7e.md) · + 106 more
  - **publish-pipeline (5):** [afo-manifesto-v0.1](a4e1b7c3.md) · [Publish AFO Manifesto to docx (MindBridge stres...](f2c8a4e1.md) · [Publish agent work to docx (example)](e0a3d9c7.md) · [Publish Tropo website content (web target)](f1b4c8d2.md) · [vault-memory-system-spec-v3](b8d2c5a4.md)
  - **release (56):** [Tropo-OS v1.16.0 — First-User Readiness Pass](9149b649.md) · [Tropo-OS v1.21.0 — Unified Agent-Activation Reg...](c7d1f0a4.md) · [Tropo-OS v1.22.0 — sa.* Dispatch Reliability + ...](1d8a2904.md) · [Tropo-OS v1.23.0 — Unmigrated Agents Identity M...](db32a917.md) · [Tropo-OS v1.24.0 — Agent-Activation Hardening](6823f75d.md) · [Tropo-OS v1.25.0 — Import Primitive Tier 1](8031a74a.md) · [Tropo-OS v1.26.0 — Memory Subsystem v2 → v3](bcdf390c.md) · [Tropo-OS v1.26.0 — Working-Copy Primitive](a95421fe.md) · + 48 more
  - **release-plan (16):** [Generic Target Extract-and-Publish — Release Pl...](6e4a8c91.md) · [Tropo-OS v1.25.0 — Release Plan](b55a395f.md) · [Tropo-OS v1.26.0 — Release Plan](f54f8415.md) · [Tropo-OS v1.28.0 — Release Plan](55e1e537.md) · [Tropo-OS v1.29.0 — Release Plan](dac467f5.md) · [Tropo-OS v1.30.0 — Release Plan](6f33d2e3.md) · [Tropo-OS v1.31.0 — Release Plan](a9d3c1b6.md) · [Tropo-OS v1.32.0 — Release Plan](a50f66eb.md) · + 8 more
  - **research:** [How frontier models consume GitHub for training...](e07bc98a.md)
  - **task (8):** [Backlog — adac1f10 (Registry Topology Consolida...](3e9b5a7d.md) · [Backlog — Argo-internal ledger content leakage ...](2c8f4d6a.md) · [Backlog — argo-os/starter/ folder deprecation (...](5e9c4a7d.md) · [Backlog — Build script copy starter/agents/sa/s...](4d7c6f1e.md) · [Backlog — Capsule worked-examples (ship) regres...](5a4e9c2b.md) · [Backlog — Verification toolkit KB stub at .trop...](9d0f7e3b.md) · [Execute starter/ purge — content reconciliation...](c19ac3af.md) · [v1.4.4 ship-time: task v3.0 → v4.0 schema migra...](52420470.md)
  - **test-spec (2):** [v1.54.0 — Engine-Discipline Hardening Triad — T...](1fee7e4b.md) · [Verification-Command Hardening (v1.64) — Test-S...](d436446c.md)

**↔ Siblings (14):**
  - **under [tropo-work](b8e5f3a2.md):** [01-inbox](c5d8f1e3.md) · [app-pipeline](2918e3b4.md) · [doc-pipeline](5a4337ff.md) · [Hello Tropo — 2026 Customer Event Plan](e8d1a4f6.md) · [kb-pipeline](19a5f12c.md) · [legacy-work-pipeline (deprecated 2026-05-04)](020274e0.md) · + 8 more

**📥 Cited by (46):**
- [dev-pipeline Activation — 2026-05-24](07ea7ac6.md) — `07ea7ac6` (type `activation`, via `agent_root`)
- [dev-pipeline Activation — 2026-05-27](0f1fb5f3.md) — `0f1fb5f3` (type `activation`, via `agent_root`)
- [Tropo-OS v1.48.0 — Cycle B Extraction-and-Publish Engineering ...](1d25e142.md) — `1d25e142` (type `release`, via `member_of`, `capabilities_touched`)
- [dev-pipeline Activation — 2026-06-01](2774e472.md) — `2774e472` (type `activation`, via `agent_root`)
- [dev-pipeline Activation — 2026-05-29](280ad91b.md) — `280ad91b` (type `activation`, via `agent_root`)
- *+ 41 more — full back-link sweep via `grep -l "cd1fcd25" vault/files/*.md`*
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Member of | [tropo-work (b8e5f3a2)](b8e5f3a2.md) |

## Purpose

Governs development work from acceptance through deployment. Accepts a work-item at status `accepted`, transitions it to `active`, and orchestrates specify → build → deploy. The pipeline ends when a deployable artifact has been produced, externally tested, and committed.

Does NOT govern: ideation, design-brief authoring, or pre-acceptance grooming (those happen in the inbox while the work-item is `new` or `accepted` under requester ownership). Does not govern post-ship release archiving (that is release.capsule territory). Does not govern work that does not yield a deployable artifact (use a domain-specific pipeline for research-only or content-only cycles).

## Structure

```
dev-pipeline (cd1fcd25)
├── specify (03624b7a)
│   ├── step-0: accept-work-item (71a7d016)
│   ├── step-1: generate-release-plan (180e9108)
│   └── step-2: spawn-arch-specs (e1b819c4)
├── build (3bd8f5b6)
│   ├── step-3: author-arch-spec-artifacts (24f16afc)
│   └── step-4: update-subsystem-canonical-docs (9d4f7e21) — NEW v1.9.2 Stream A4
└── deploy (3a7dbdda)
    ├── step-5: generate-release-notes (804e339e)
    ├── step-6: produce-release-folder (8654900a)
    ├── step-7: external-test (bc6b17ec)
    └── step-8: git-commit (3e0bb81e)
```

Flow: specify → build → deploy (linear, forward-only). 9 leaf steps total (was 8 pre-v1.9.2).

## Nodes

| UID | Name | Role | Children | Next Steps |
|-----|------|------|----------|------------|
| [03624b7a](03624b7a.md) | specify | stage | 3 | [3bd8f5b6] |
| [3bd8f5b6](3bd8f5b6.md) | build | stage | 2 | [3a7dbdda] |
| [3a7dbdda](3a7dbdda.md) | deploy | stage | 4 | [] |
| [71a7d016](71a7d016.md) | accept-work-item | step | 0 | [180e9108] |
| [180e9108](180e9108.md) | generate-release-plan | step | 0 | [e1b819c4] |
| [e1b819c4](e1b819c4.md) | spawn-arch-specs | step | 0 | [] |
| [24f16afc](24f16afc.md) | author-arch-spec-artifacts | step | 0 | [9d4f7e21] |
| [9d4f7e21](9d4f7e21.md) | update-subsystem-canonical-docs | step | 0 | [] |
| [804e339e](804e339e.md) | generate-release-notes | step | 0 | [8654900a] |
| [8654900a](8654900a.md) | produce-release-folder | step | 0 | [bc6b17ec] |
| [bc6b17ec](bc6b17ec.md) | external-test | step | 0 | [3e0bb81e] |
| [3e0bb81e](3e0bb81e.md) | git-commit | step | 0 | [] |

## Flow Rules

Execution is linear and forward-only. Stages advance in order: specify → build → deploy. Within each stage, steps advance in `next_steps:` order.

**Stage transitions:** each stage's `next_steps:` points to the next stage. The pipeline-run executor completes a stage (all its steps at `done`) before starting the next.

**Step transitions:** within a stage, each step's `next_steps:` points to the next step. The executor advances when the prior step reaches `done`.

**Terminal nodes:** deploy stage (`next_steps: []`) and git-commit step (`next_steps: []`) are terminal. Pipeline-run closes when git-commit completes.

**Branching:** none at v1.0.0. This is a fully linear pipeline. Branching behavior (v2.1 schema) is not exercised here.

**Human pause point:** step-1 (generate-release-plan) requires user confirmation of the release number before the release-plan instance is committed. Implemented via `restart_strategy: manual` on the pipeline-run at that step. See Known Enforcement Gaps — the exact pause-at-step mechanism is not fully specified at v2.0.

## Cold-Boot Walk-Through

A pipeline-run has been started against dev-pipeline v1.0.0. The work-item is a design-brief at `status: accepted`.

**Step 0 — accept-work-item:** The executor reads the work-item's current status (`accepted`). It writes an acceptance record onto the work-item's `accepted_by:` array: `accepted_by_uid: <this-run-uid>, date_accepted: <today>`. It sets the work-item's `status:` to `active`. The work-item is now in flight.

**Step 1 — generate-release-plan:** The executor (or the agent driving the run) checks the registry for the next incremental release number. It authors a `release-plan.capsule` instance naming the release number, intent, completion outcome, and sub-systems to be touched. The user reviews and confirms the release number. The release-plan is committed to the Vault.

**Step 2 — spawn-arch-specs:** For every sub-system declared in the release-plan, the executor authors a numbered, registered `arch-spec.capsule` instance. Each arch-spec is 1:1 with a sub-system. The arch-specs are committed to the Vault and referenced from the release-plan. *(Capsule-fire-time auto-spawn is a Known Enforcement Gap — at v1.0.0 this step is hand-executed by the agent running the pipeline.)*

**Step 3 — author-arch-spec-artifacts:** For each arch-spec authored in step 2, the agent produces the spec's three required artifacts: (a) a research node documenting background context, (b) one or more sprint plans each with a testing plan, (c) a documentation node updating the master tropo-subsystems documentation. When all arch-specs have their artifacts, step 3 closes; build stage continues to step 4.

**Step 4 — update-subsystem-canonical-docs (v1.9.2 NEW):** The executor reads the release-plan's `capabilities_touched:` and `hub_summaries:` (NEW v1.3 field) and derives `subsystems_touched:` via 1-hop `member_of:` traversal. For each touched subsystem hub: prepends a `release_history:` row, bumps `last_release_reflected:`, writes a row to `subsystem-registry.jsonl`. Frontmatter only — hub body sections (Change Log narrative, Current State) stay manual per Q7 walk reframe. Closes the manual-substitute pattern (v1.8 + v1.9.0 + v1.9.1 each ran a hand-written `append-v1-X-hub-rows.py` script). On completion, build stage advances to deploy.

**Step 5 — generate-release-notes:** The executor reads all closed sprint plans and arch-spec deltas. It authors the release notes document summarizing what shipped.

**Step 6 — produce-release-folder:** The executor produces the release folder structure and `.zip` artifact at the locked schema. The artifact is registered.

**Step 7 — external-test:** The `.zip` artifact is run against external test execution. Results are recorded on the pipeline-run.

**Step 8 — git-commit:** The release-marked state is committed to git. Pipeline-run closes.

## Known Enforcement Gaps

| Gap | What closes it | Target release | Owner |
|-----|----------------|----------------|-------|
| Work-item status transition on pipeline-run start (step-0 writes `accepted_by:` + sets `status: active`) — no pipeline.capsule v2.0 mechanism for pipeline-run-to-work-item status writes | Inbox primitive capsule amendments (note v3.2, task v3.x, design-brief v3.x) ship `accepted_by:` array + status enum; pipeline-run.capsule gets a "write acceptance record on run-start" behavior rule | v1.4.4 | argus |
| Capsule-fire-time auto-spawn of child vault entries (step-2 auto-spawns arch-specs from release-plan) — no v2.0 mechanism for this | pipeline.capsule v2.1 + release-plan.capsule amendment: "on release-plan commit, spawn one arch-spec per declared sub-system" | v1.4.4 | argus |
| User confirmation pause at step-1 — step-level pause semantics not specified; v2.0 only has `restart_strategy: manual` at run level | pipeline-run.capsule amendment: step-level pause with `requires_confirmation: true` flag; executor pauses at that step for human approval | v1.4.4 | argus |
| sprint-plan capsule type does not exist — step-3 references sprint plans as arch-spec artifacts | Author sprint-plan.capsule as part of arch-spec.capsule design in v1.4.4 specify | v1.4.4 | argus |
| 1:1 sub-system / arch-spec constraint (step-2: "one sub-system per arch-spec — strict 1:1") not enforced by pipeline.capsule | release-plan.capsule amendment: validation rule checks each declared sub-system maps to exactly one arch-spec | v1.4.4 | argus |

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-03 | Initial draft. Scaffolded from design brief e1c47a9f per Specify handoff. Three stages (specify/build/deploy), eight steps including runtime-first-step transition mechanism. Known Enforcement Gaps document five v2.0 schema limits surfaced by scaffolding. | argus-a42 |
| 1.0.1 | 2026-05-04 | Folder rename agents/dev.pipeline → agents/dev-pipeline (v1.6 Stream B.1; capsule-vs-instance naming convention) + reparented under tropo-work L0 (b8e5f3a2) per v1.6 Stream B.2. No structural changes to children or steps. | argus-a44 |
| 1.1.0 | 2026-05-07 | **v1.9.2 Stream A4 amendment.** Build stage (3bd8f5b6) gained child step `update-subsystem-canonical-docs` (9d4f7e21) — NEW v1.9.2 dev-pipeline step that auto-fires Rule 12 hub release_history derivation. Pipeline structure goes from 8 leaf steps to 9. Step-3 (24f16afc) `next_steps:` updated from `[]` to `[9d4f7e21]`; step-4 (9d4f7e21) is terminal in build; build stage `next_steps: [3a7dbdda]` unchanged. Closes the manual-substitute pattern v1.8 + v1.9.0 + v1.9.1. UID preserved at cd1fcd25; structural edit per pipeline.capsule Rule 3 triggered minor version bump. governed_by: e4c8a6b2 unchanged (pipeline.capsule v2.4 amendment Stream A3 lands alongside; UID preserved across v2.3 → v2.4). | argus-a49 |

---

*dev-pipeline | WorkflowNode root | pipeline.capsule v2.4 (post-v1.9.2 Stream A3) | argus-a42 (v1.0.0) → argus-a44 (v1.0.1) → argus-a49 (v1.1.0) | 2026-05-03 → 2026-05-07*
*Derived from: [dev-pipeline + vault inbox primitive (e1c47a9f)](e1c47a9f.md)*
*"v1.9.2 ships the rule + the executor that fires it. The cycle's own ship is the dogfood gate."*
