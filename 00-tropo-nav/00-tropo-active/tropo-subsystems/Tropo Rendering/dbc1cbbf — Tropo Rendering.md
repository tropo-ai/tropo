---
uid: dbc1cbbf
type: project
status: evergreen
state: active
title: Tropo Rendering
description: Living history of Tropo Rendering — board-definitions, board-snapshots, prose query vocabulary, render engine, synthesizer. Reframed from the prior layered-graph system to the render-engine subsystem per v1.3 capability matrix.
owner: metis
created: 2026-04-14 00:00:00+00:00
modified: 2026-05-25
modified_by: orpheus-o11
tags:
  - rendering
  - tlgs
  - subsystem-hub
  - build
  - standing
  - p0
subsystem_name: tropo-rendering
subsystem_scope: Board-definition + board-snapshot capsules, prose-query vocabulary v1, render engine, board synthesizer. Historical audit via immutable snapshot chains.
file_ext: md
schema_version: 2
extraction_scope: ship
member_of:
  - aae9a37b
slug: tropo-rendering
primary_collection: a7a69fc1
tasks_collection: c292cd97
lifecycle: standing
created_by: argus-a23
last_release_reflected: 1.55.0
aligned_with: 8a4e21c5
release_history:
  - release_uid: 4920ce3a
    release_version: 1.20.0
    summary: v1.20.0 ship — minor touch. governance-contract instance for collections/ (folder_type:content; owner:vela; primary hub tropo-rendering). Collections are synthesized views grouping vault entries by reference — folder-level governance now typed.
    registry_uid: pending
    derived_from: capabilities_touched
  - release_uid: 8e9d5b3f
    release_version: 1.12.1
    summary: v1.12.1 manifest-driven build mechanism becomes operational — build-release.py rewritten per locked Build-Release Pipeline arch-spec (MVP Phase E). ~225 lines of legacy parallel-mirror handling removed; ~150 lines of manifest-driven Phase 3 added. Build extracts source exclusively from ship-artifact graph rooted at b2e7d4a9. argo-os/starter/ directory retired entirely. RELEASE-NOTES.md relocated from starter/ to vault root. 3 NEW ship-artifact entries + 1 amendment close fresh-user IDE-config coverage gaps. Rendering pipeline substrate restored to V33's 2026-04-22 design intent.
    registry_uid: a0d20667
    derived_from: capabilities_touched
  - release_uid: f604209d
    release_version: 1.9.1
    summary: 'v1.9.1 ship: rename script .tropo-studio/scripts/v1.9.1-stream-a/rename-tropo-vault-to-tropo-studio.py (preservation logic IN pattern set per a47-reflection class-signature pin); build-release.py path constants + ROOT_FILES updated (VAULT.md → STUDIO.md); tropo-validate.py directory checks updated; vault/templates/.tropo-vault-skeleton/ → .tropo-studio-skeleton/ (Round 2 fold).'
    registry_uid: e94f8d40
    derived_from: capabilities_touched
  - release_uid: 1b4bb15a
    release_version: 1.9.0
    summary: build-release.py 5 path-rename patches + NEW member_of pruning at index-write time; rebuild-vault.py + tropo-validate.py source-paths patched for vault/ directory lookup; Round 3 + 5 vocabulary-completion scripts authored at .tropo-studio/scripts/v1.9.0-stream-a/. Hub promoted to ship.
    registry_uid: 1b4bb15a
    derived_from: capabilities_touched
  - release_uid: e8a7c4d2
    release_version: 1.6.0
    summary: v1.4 → v1.6 catch-up. Python rebuilder toolchain port (v1.5; rebuild-vault.py + rehydrate.py); v1.6 role-filter for project-tree pipeline navigation; archived-cascade fix; project-tree.jsonl + 00-tropo-nav regeneration each release.
    registry_uid: 53609453
    derived_from: manual_authoring
  - release_uid: a676a5f2
    release_version: 1.7.0
    summary: 'v1.7 ship: rebuild-vault.py + rehydrate.py + tropo-validate.py exercised across cycle (8+ cycle-internal runs for B1/B2/B3 cohort fixes + final ship build); 00-tropo-nav regenerated from shipped ledger at build (4 active / 5 all / 1 archived); 24-aggregator archive (B2+B3, includes TLGS rendering aggregators); no direct rendering-substrate changes — indirect via cycle''s ledger evolution.'
    registry_uid: 9446bada
    streams_touched:
      - B
    derived_from: manual_authoring
  - release_uid: 14e5f79c
    release_version: 1.8.0
    summary: 'v1.8 ship: 5 rendering-class primitives backfilled with member_of:[dbc1cbbf]; rebuild-ledger executed twice (initial + Round 2); how-boards-work doc retagged from Library placeholder per per-doc judgment.'
    registry_uid: 6c9e3d52
    streams_touched:
      - A
      - B
      - E
      - F
      - K
    derived_from: capabilities_touched
---

# Tropo Rendering

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → **Tropo Rendering**
<!-- nav-block:end -->

*Evergreen subsystem hub. Child of [tropo-subsystems root (aae9a37b)](aae9a37b.md). Never closes.*
*Renamed from "Tropo Layered Graph System (TLGS)" in v1.3 per [capability matrix v1.0](../../TROPO-CAPABILITIES.md) OD2-F. UID preserved. Reframe rationale: the subsystem's operational value is render-engine-on-governed-sources (board-definitions + snapshots + query vocabulary) more than layered-graph-infrastructure (graph primitives moved to [Library hub (1aba710c)](1aba710c.md)). v1.2 shipped Board Reconciliation v0.3 as the rendering pillar — the promotion from "part of Work" to its own subsystem is evidence-driven per sa.research 030.*

## What This Subsystem Covers

*Structured per subsystem-hub.capsule v1.6 §1 (In scope + Not in scope + Edge cases). v1.3 reframed from TLGS to Rendering; v1.7 Stream D1 further moved storage-substrate discovery infrastructure INTO Rendering (from Library, which narrowed to content storage). v1.6 amendment converts free-form prose to structured enumeration.*

### In scope

- **Board-definition + board-snapshot capsules.** [board-definition.capsule (b0d1e4f2)](b0d1e4f2.md) + [board-snapshot.capsule (b5a7c391)](b5a7c391.md) typed primitives. Governs "what a dashboard is" + "what it looked like at a specific moment." 60+ snapshots in vault; immutable historical chains with `taken_at` / `taken_by` / `reason` / `board_definition` provenance.
- **Prose-query vocabulary v1.** Subtree semantics + field predicates + combinators + cascade operators that declare board content in human-legible form. The grammar that lets agents specify boards without writing code.
- **Render engine + board synthesizer.** Composes rendered boards from the Vault in-band; reproducible from governed sources. Render is deterministic from frontmatter + index; same input always yields same output.
- **Discovery infrastructure (per v1.7 Stream D1 reframe).** [`vault/00-index.jsonl`](../../vault/00-index.jsonl) (one JSON record per entry); `00-graph-index.json`; `00-project-tree.jsonl`; subsystem-registry.jsonl; cascade indexes; collections (synthesized views grouping vault entries by reference, e.g. a7a69fc1).
- **Python rendering toolchain at `.tropo/scripts/`.** [rebuild-vault.py](../../vault/tools/tropo-rebuild-vault.py) (5-step canonical: validate → rebuild-index → rehydrate → project-tree → 00-tropo-nav); [rebuild-index.py](../../vault/tools/tropo-rebuild-index.py); [rehydrate.py](../../.tropo/scripts/rehydrate.py); validate-no-absolute-paths.py portability check. Substrate is governed by Playbooks (the script-as-substrate-primitive lives there); *runtime rendering* + the indexes the scripts produce live here.
- **`00-tropo-nav/` navigation surface.** Regenerated every build; renders the canonical project-tree as filesystem-walkable structure for VS Code + chat surfaces. Composes with HUMAN-NAVIGATION OS-tier primitive.
- **The website surface (`app/(web)/`) + KB-render routes.** The Tropo Platform's Next.js app routes that render canonical vault content to readers (KGAE live; `/kb/<uid>` routes; tropo-ai.com site). Cross-repo: code lives in the Platform repo (`tropo-ai/`), but the *concern* — vault → readable surface — is Rendering's lane. v1.49 publish.pipeline operationalizes this.
- **Folder governance for `collections/`.** v1.20 governance-contract instance for collections/ (folder_type:content; primary hub tropo-rendering) — collections ARE rendering primitives (synthesized views).
- **nav-block rendering.** The auto-generated nav-block on every vault entry (📍 Vault Path / 🌳 Tropo-Nav Path / 🔗 This file / ↓ Children / ↔ Siblings / 📥 Cited by). OP-12 HUMAN-NAVIGATION composes here.

### Not in scope

- **Source content + canonical narrative.** What gets rendered (KB articles, handbook, manifesto, KGAE prose) belongs to [Tropo Documentation (f87e33f0)](f87e33f0.md) + [Tropo Library (1aba710c)](1aba710c.md). Rendering delivers; Documentation defines what's canonical; Library stores.
- **Validator rule definitions + capsule schemas + ADRs.** All governance-class substrate — [Tropo Governance (8dd772a0)](8dd772a0.md). Rendering *executes* tropo-validate.py at rebuild-vault.py [1/5] pre-step, but the rules + severity + ratchet schedule belong to Governance.
- **Build-release mechanics + dist/ assembly + ship gating.** [Tropo Capabilities (7a1ca900)](7a1ca900.md) owns the release-artifact construction; Rendering produces the *indexes* the build consumes.
- **Per-cycle release authoring.** Briefs, specs, release plans, activation roots — owned by Talos/Argus per cycle under Tropo Capabilities; Documentation hub owns the canonical record.
- **Agent identity substrate.** Charters, soul letters, transfers, status cards — [Tropo Agents (99ed55fd)](99ed55fd.md).
- **Playbook substrate + script substrate primitives.** [Tropo Playbooks (76bab75f)](76bab75f.md) owns the script-class substrate (what the script IS as substrate primitive); Rendering owns the *runtime* (what the script PRODUCES when executed at build).
- **Capsule library at `.tropo/capsules/`.** Schema authority is Governance; Playbooks owns playbook-class capsules. Rendering executes against capsule rules at index time but doesn't author them.
- **The publish lane content + editorial gates.** publish.pipeline substrate at Playbooks; published content at Documentation; Rendering owns the rendering of that content to readers.

### Edge cases (multi-parent / borderline)

- **Python rendering toolchain (`vault/tools/tropo-rebuild-vault.py` + peers)** — substrate-class definition lives at Tropo Playbooks (script-as-substrate-primitive); *runtime + the indexes they produce* live here. Cross-subsystem composition: Playbooks owns the source-of-truth (.py file); Rendering owns the output (`00-index.jsonl` + nav surface).
- **rebuild-vault.py [1/5] pre-step validator execution** — Rendering *runs* validator at rebuild; Governance defines the rules. Operationally co-owned; Rendering executes the gate, Governance owns the gate's logic.
- **`00-tropo-nav/` + `project-tree.jsonl`** — surfaces owned by Rendering but content reflects Work projects + Agents charters + Playbooks scripts + every other subsystem. Rendering as integrator across all subsystems.
- **Collections (`collections/master/*`, `collections/<uid>.md`)** — synthesized views grouping vault entries by reference. Substrate class is Rendering (synthesized = rendering primitive); content reflects whatever subsystem the references point to.
- **The website surface (`app/(web)/`)** — code lives in Platform repo (tropo-ai/) under engineering's lane; the *concern* (vault → readable surface) is Rendering. Cross-repo composition: Engineering builds; Rendering defines what gets rendered + how.
- **nav-block + Cited-By blocks** — auto-generated per entry by rebuild-vault.py; OP-12 HUMAN-NAVIGATION primitive (Governance) declares the requirement; Rendering executes the generation. Composes with every vault entry.

## How Tasks Flow

Tasks created in this subsystem represent decisions and work for Rendering. When a task is ready to build, add the current release UID to its `member_of:` array — one pointer, no extra work. The task appears on both the Rendering board (full history) and the release Drop board (current cycle).

---

## Current State

*(NEW v1.3 REQUIRED section; populated as v1.7 Stream B4 catch-up.)*

As of v1.6 ship (2026-05-05), Tropo Rendering's substrate has migrated to a **Python toolchain** at [`.tropo/scripts/`](../../.tropo/scripts/) — the v1.4 TypeScript rebuilder family was ported for portability + dependency simplification (every Tropo-OS vault ships with `python3` available; `node` is not assumed). The canonical scripts are: [`rebuild-vault.py`](../../vault/tools/tropo-rebuild-vault.py) (regenerates `00-index.jsonl` + `00-graph-index.json` + `00-project-tree.jsonl` from frontmatter), [`rehydrate.py`](../../.tropo/scripts/rehydrate.py) (reverse: writes frontmatter from index for emergency recovery), [`tropo-validate.py`](../../vault/tools/tropo-validate.py) (structural invariants check), and `validate-no-absolute-paths.py` (portability check). Board-definitions + board-snapshots remain as v1.2's locked primitives. The render engine + board synthesizer exercise the prose-query vocabulary v1. v1.6 introduced a role-filter on the project-tree pipeline navigation + archived-cascade fix. Substrate currency at v1.6.

**v1.7 → v1.12 storage substrate consolidation.** v1.7 Stream D1 reframe: discovery infrastructure (rebuilder + cascade indexes + graph index + registry.jsonl + project-tree) moved INTO Rendering scope (from Library, which narrowed to content storage). v1.8 5 rendering-class primitives backfilled with member_of:[dbc1cbbf]. v1.9 path-rename mechanics: build-release.py + rebuild-vault.py + tropo-validate.py source paths swept .tropo-vault/ → .tropo-studio/; rebuild-ledger.ts → rebuild-vault.py canonical (rename + Python port complete). v1.9.1 universal `.tropo-vault/` → `.tropo-studio/` namespace rename (81 active directories) + VAULT.md → STUDIO.md (UID f1a7b3c2 preserved). v1.12 manifest-driven build operational: build-release.py rewritten per locked Build-Release Pipeline arch-spec (MVP Phase E); ~225 lines of legacy parallel-mirror handling removed; ~150 lines of manifest-driven Phase 3 added; argo-os/starter/ directory retired; RELEASE-NOTES.md relocated from starter/ to vault root.

**v1.13 → v1.27 rendering + publish ramp.** v1.13 publish-pipeline (e2f4a8c1) ships as governed playbook-class substrate; the second operational pipeline alongside dev-pipeline; canonical-render path from vault → website starts being formalized. v1.18 + v1.19 capsule-body-as-pedagogy refactor across 14 capsules with .history.md companions (capsule-history.capsule 5ec083a3) — rendering surfaces (capsule body navigation) become canonical. v1.19 KB articles migrate from `.tropo/kb/` to `vault/files/<uid>.md`; subsystem hub member lists become the canonical KB catalog via nav-block rendering. v1.20 governance-contract instance for collections/ folder (folder_type:content; owner:vela; primary hub tropo-rendering) — collections-as-synthesized-views is typed primitive. v1.27 dev-pipeline enforcement hardening — Stream E historical sweep + per-release-retroactive-sweep registry rows; rendering surfaces become structurally enforceable not honor-system.

**v1.28 → v1.37 import-primitive Tier 1 + rendering hygiene.** v1.28 folder-marker mirror substrate (`.tropo-folder.md` + vault mirror dual-residence) per arch-spec §3.5.5 Amendment 1; nav-block-style folder navigation primitive. v1.29 fix-duplicate-yaml-keys.py + shared `_yaml_dup_lib.py` close v1.12 carry-forward defect class (251 files merged); `npm run vault:rebuild` succeeds clean (was failing for weeks). v1.30 Studio-tier rebuild single-gesture: rebuild-vault.py [1/5] tropo-validate.py pre-step + [2/5] rebuild-index.py with --skip-rehydrate composition fix; build-release.py Step 0c pre-flight ship-gate. v1.31 docx_styles_bundle.py NEW (~390 lines stdlib-only) — OOXML WordprocessingML rendering for `.docx` export; v1.31 + v1.32 tropo-export.py P2 + P1 path proper (rendering vault projection → real .docx). v1.33 Cold-Boot Test Harness: tropo-test.py + `npm test` canonical substrate-health gesture documented at orientation; rebuild-vault.py path conventions verified for nested-Studio scenarios. v1.35 pipeline-activate.py + cascade-stress-compare.py + tropo-recycle.py NEW; rebuild-index.py `get_scalar` quote-aware fix (Word/Notepad import path produced UTF-8 BOM'd working copies). v1.36 Hello Tropo first-encounter cycle exercises full render path: cascade-from-activation → 00-tropo-nav regeneration → board render. v1.37 charter.capsule v1.0.1 lands; charter conformance baseline rendered across all charter-bearing agents.

**v1.46 governance-contract sweep.** ~13 governance-contract instances at vault/files/<uid>.md replace legacy per-folder .tropo-studio/CAPSULE.md substrate; folder-governance discoverable via hub Members section + nav-block rendering. Rendering surfaces become the canonical discovery path for folder governance.

**v1.49 publish.pipeline class operationalized + KGAE live.** publish.pipeline class ships as second governed playbook-class typed primitive after dev-pipeline; **KGAE article goes live on tropo-ai.com as first production output** — the canonical render path from vault → website is operational. KB-render routes at `/kb/<uid>` deliver canonical content (canonical-links-render-to-website-not-GitHub doctrine in operation). v1.49 closes the vault → website rendering loop that v1.13 publish-pipeline scaffolded.

**v1.51 Three-Pipeline architecture + *-spec trio.** No direct Rendering substrate touches; pipeline-runtime.py (Governance schema; Playbooks substrate; Rendering at runtime fires for dev-pipeline). The substrate for canonical pipeline-step rendering at boards lands but the rendering surfaces stable.

**v1.52 doc-pipeline + voice review.** [doc-pipeline (5a4337ff)](5a4337ff.md) executes; canonical docs rendered to vault + Documentation hub member lists. voice-review.skill (811856a5) is a Playbooks-substrate skill but its output (voice-consistent prose) is content the rendering surfaces deliver. Workbench Surface Visibility doctrine (3c02f3b7) operationalized: rendered surfaces ARE the workbench Mike sees; rendering quality = workbench quality.

**v1.53 cycle (in flight).** Lane D Pristine Subsystem Documentation. subsystem-hub.capsule v1.6 amendment strengthens §1 to structured In scope + Not in scope + Edge cases enumeration; this hub refresh (orpheus-o11) brings Tropo Rendering §1 to v1.6 shape + Current State currency through v1.52. The rendering substrate is most mature in the OS — it's the medium every other subsystem renders through.

**Substrate currency marker: through v1.52, refreshed 2026-05-25 by orpheus-o11.**

**v1.55 Messaging Foundation (in flight; Block 5 cycle 1 of 5; doc-pipeline activation 66739384).** [vault/events/](../../vault/events/) infrastructure lands as new discovery + storage primitive class — canonical append-only [00-events.jsonl](../../vault/events/00-events.jsonl) + derived [00-events-index.sqlite](../../vault/events/00-events-index.sqlite) materialized view + files/ companion-payloads directory + [AGENTS.md](../../vault/events/AGENTS.md) folder governance contract (append-only invariant + tool-mediated writes; no direct edits). The JSONL is authoritative; SQLite is regenerable via [rebuild-events-sqlite (vault/tools/tropo-rebuild-events-sqlite.py)](../../vault/tools/tropo-rebuild-events-sqlite.py). Sets up Stream B projection renderer at v1.57+ — when the projection renderer ships, the four currently-authored substrates that drift (channels + status cards + activation entries + crew brief) become RENDERED from the event log, not authored. The render-engine-on-governed-sources scope grows by one substrate class: events become the canonical source for the four projections that today are hand-authored. Substrate currency marker: through v1.55.

**v1.57 Stream B Projection Renderer (SHIPPED 2026-05-27 by Vela V54; Block 5 cycle 3 of 6; pristine streak 63 → 64; doc-pipeline activation 4ac35a3a).** Stream B closes the channel-bloat structural fix the v1.55 paragraph foreshadowed. [render-events-as-views.py (vault/tools/71b0a4d8.py)](../../vault/tools/71b0a4d8.py) authored per [tool.capsule v1.6 (d5e1b4a3)](d5e1b4a3.md) §2.5 single-file pattern (Talos T10 lane B.1) — reads `vault/events/00-events.jsonl` via query-events filter (by recipient_uid + source_uid + correlationid) + renders per-channel markdown view; deterministic + idempotent (same input → byte-identical output). [channels/CAPSULE.md](../../channels/CAPSULE.md) v1.2 → v1.5 amendment (Argus A85 lane B.3) introduces the `rendered_from_events: true` opt-in marker + the bidirectional fallback rule (rendered_from_events:true → emit-event via [vault/tools/tropo-emit-event.py](../../vault/tools/tropo-emit-event.py); absent or false → Edit per legacy). 3 argus-* channels migrated empirically (argus-talos + argus-orpheus + argus-vela; pre-Stream-B archives at archive/<channel>/2026-05-27-pre-stream-b.md per Preservation Discipline). [channel-projection-migration.skill v1.1](../../.tropo/skills/channel-projection-migration.skill.md) at .tropo/skills/ (Argus lane B.6) operationalizes the per-channel migration discipline (archive-and-fresh-start default + optional backfill-active-threads + rollback + posting decision protocol). check_channel_render_safety validator at [.tropo/scripts/lib/channel_render_validators.py](../../.tropo/scripts/lib/channel_render_validators.py) (Talos lane B.5; WARN at v1.57 / ERROR ratchet v1.58+) — diff-checks renderer output against on-disk content to catch drift. Stream D progressive migration of remaining channels (ops.md + alerts.md + other bilaterals + agent-directors) lands across v1.58-v1.61. Substrate currency marker: through v1.57.

**v1.58 Messaging Arc Operational Completeness (in flight; Block 5 cycle 4 of 7; doc-pipeline activation 0aeb121a).** Rendering-class landings at v1.58: **Stream C substrate-write auto-emission at 7 choke-point tools** retrofitted with [emit-event (vault/tools/tropo-emit-event.py)](../../vault/tools/tropo-emit-event.py) auto-emission per dev-spec C.1-C.7 — [rebuild-vault](../../vault/tools/tropo-rebuild-vault.py) emits `tropo.substrate.modified` per indexed entry; [write-activation-entry](../../vault/tools/40b2f455.py) emits `tropo.substrate.created` + `.modified`; [tropo-recycle](../../vault/tools/tropo-recycle.py) emits `tropo.substrate.recycled`; [pipeline-activate](../../vault/tools/e337f1dd.py) emits `tropo.pipeline.activated`; [pipeline-runtime](../../vault/tools/9e7003b1.py) emits `.step_completed` + `.bootstrapped` + `.closed`; [build-release](../../vault/tools/tropo-build-release.py) emits `tropo.release.shipped`; [tropo-validate](../../vault/tools/tropo-validate.py) emits `tropo.validator.run.completed`. Eliminates manual emit-event calls for substrate-mutation cases by construction. [render-events-as-views.py](../../vault/tools/71b0a4d8.py) AGENT_NAMES dict updated with Po entry (T.3) for readable channel rendering of the concierge-class agent. Harness trigger-detection (Talos lane per L.3) lives at .tropo/scripts/lib/trigger_detection.py (or harness-integration equivalent) + auto-fires ScheduleWakeup on agent emit/receive of `reply_required:true` messages per the Tier 2 §Continuous-Listen Polling Protocol cadence; may defer impl to v1.58.1 per dev-spec R1 with manual ScheduleWakeup fallback documented. Substrate currency marker: through v1.58.

**v1.59 Structural-Discipline Amendment Cycle (in flight; Block 5 cycle 5 of 7; doc-pipeline activation 213076c5; ship-gate window READY-TO-FIRE per Argus event 00000154).** Rendering-class landings at v1.59. **Lane B — build-release.py V2+V3 ship-step amendment.** [vault/tools/tropo-build-release.py](../../vault/tools/tropo-build-release.py) pre-flip checks REFUSE `status: shipped` if (a) `derive-subsystem-registry.py` + STRICT validator return any ERRORs, OR (b) doc-pipeline or test-pipeline cascade activations are not `status: retired`, OR (c) any release.capsule `required_at_ship:` field is unpopulated (TBD or empty). **Closes the 3-cycle-recurring R11+R12 substrate-population-residue defect class** (v1.56 + v1.57 + v1.58 ship gates each caught the same family at validate-evidence; v1.58 specifically saw V54's premature ship-status-flip before my doc-pipeline cascade closed — captured in my v1.58 disposition_signoff as Tier 2 cross-pipeline-coherence finding; v1.59 Lane B IS the structural fix). **Lane C R2 — trigger_detection.py emit-side wakeup extension.** [.tropo/scripts/lib/trigger_detection.py](../../.tropo/scripts/lib/trigger_detection.py) extended to fire ScheduleWakeup on agent EMIT of `reply_required:true` events (not just receive); closes stm-a87-002 architect-doesn't-fire-own-schedulewakeup defect structurally. emit-event tool gains `--strict-mode` flag at v1.59 (default-ERROR ratchet at v1.60+). **Lane D V6 — ops.md migrated to rendered_from_events:true.** Per Talos V6 (event 00000147): 8-party crew list + anchor markers + pre-Stream-B content archived at `channels/archive/ops/2026-05-28-pre-stream-b.md`. Stream D progressive migration ratchets — first non-argus channel to flip. **Lane D V7 — query-events --party + cursor state.** [vault/tools/tropo-query-events.py](../../vault/tools/tropo-query-events.py) gains `--party <uid>` filter + cursor-state persistence for incremental polling; composes with continuous-listen polling protocol for efficient event-tail consumption. Substrate currency marker: through v1.59.

**v1.60 Pillar 1 Closes at Three Surfaces (SHIPPED 2026-05-29 by Vela V55; Block 5 cycle 6 of 7; pristine streak 67; doc-pipeline activation [c94663a9](c94663a9.md)).** Rendering-class landings at v1.60: the callable-surface migrations give the index two new single-file content classes. 16 session-agents (`vault/session-agents/`) and 10 actions (`vault/actions/`) now live at single-file-truth locations; [rebuild-index.py (vault/tools/tropo-rebuild-index.py)](../../vault/tools/tropo-rebuild-index.py) is extended to walk them, and pipeline-runtime invocation-path resolution updates so actions resolve at their vault locations rather than the prior `.tropo/actions/` paths. (Substrate-honest note: the first-class `vault/session-agents/` index-source carries a v1.61 Lane S-migrate marker in the tool — the indexing wiring completed as the migration finished across the v1.60 → v1.61 boundary.) Substrate currency marker: through v1.60.

**v1.61 Messaging-Substrate Completion + Po Executive Identity + Fleet-Ops Trigger-Wire (SHIPPED 2026-05-29 by Vela V55; Block 5 cycle 7 of 7 — CLOSES BLOCK 5; pristine streak 68; doc-pipeline activation [69e1341c](69e1341c.md)).** Rendering-class landing at v1.61: **channel retirement at scale**. The Stream B/D progressive migration completes — 16 crew-internal channels retire entirely (substantive content archived to `channels/archive/<channel>/2026-05-29-pre-retire.md` per Preservation Discipline; ~107 archived channel files now), and `query-events` against the canonical log becomes the canonical crew-internal coordination surface. The renderer ([render-events-as-views.py](../../vault/tools/71b0a4d8.py)) retains only the **two user-facing surfaces** as event-projections per the Mike-A88 by-AUDIENCE distinction: `channels/tropo.md` (the Studio-activity feed) and `channels/releases.md` (the release/news feed). Crew-internal rendering retires; user-facing rendering persists. Substrate currency marker: through v1.61.

**v1.76 ADR-045 One Home — the index-builder + catalog generators scan `vault/` exclusively.** With governed content converged on `vault/`, the rendering pipeline repoints to read there and only there. The index-builder ([rebuild-index](../../vault/tools/tropo-rebuild-index.py)) sets `capsules_dir = vault/capsules/` (was `.tropo/capsules/`) and scans templates at `vault/templates/`; the capsule scan path was updated across the rendering python tools (six). The capability-catalog generators ([generate-capability-catalogs](../../vault/tools/tropo-generate-capability-catalogs.py)) regenerate the **skill-catalog, sa-agent-catalog, tool-catalog, and toolbelt** from the new vault paths — the catalogs themselves remain at `.tropo/` as generated read-surfaces, but their source of truth is now `vault/`. To keep documentation coherent with the relocated tools, capsule/template path references in **340 authored `.md` files (98 + 242)** were swept to the vault paths in the same pass. The rendering tools are themselves human-named under ADR-048 (`vault/tools/tropo-rebuild-*.py`, `tropo-generate-capability-catalogs.py`). *(This paragraph documents the v1.76 One Home repoint specifically; the broad rendering sweep above is current through v1.61.)*

**v1.77 Ship-Artifact Path Preservation — the shipped extract now mirrors the studio One-Home layout.** One Home (ADR-045) was source-complete but artifact-incomplete until v1.77: the build tool's copy step ([tropo-build-release.py](../../vault/tools/tropo-build-release.py) `step_4_copy_ship_entries`) special-cased only `vault/agents/` for path preservation, so every other ship-scope entry — whatever its real home — flattened into `vault/files/<uid>.md`. Six of the eight One-Home directories (`vault/skills/`, `vault/capsules/`, `vault/templates/`, `vault/entities/`, `vault/actions/`, `vault/session-agents/`) therefore shipped **zero files** in v1.75.0 and v1.76.0 (214 source files across them), and relative links into those directories — a playbook citing `vault/skills/...`, a skill citing `vault/capsules/...` — resolved in studio source but broke in every shipped extract. v1.77 replaces the special-case with a **general rule** (dev-spec [ba454e56](ba454e56.md), locked): the destination directory AND filename are derived from each entry's real path (`vault/<subdir>/` + the real basename); only entries whose actual home is `vault/files/` flatten there, and the old `vault/agents/` special-case collapses into the general rule. The basename half matters as much as the directory half — skills, capsules, templates, and tools carry readable `tropo-<name>.md` filenames, not `<uid>.md`, so reconstructing UID filenames would have preserved the directory while still breaking every link. **There is no per-directory list to maintain:** a seventh canonical directory added tomorrow ships correctly by construction, which is precisely the recurrence class (agents/ was special-cased once; six dirs later broke the same way) the generalization retires. Verified on the real v1.77.0 artifact, not the dry-run: all six directories ship populated at source-matching counts, the shipped `00-index.jsonl` `path:` fields match on-disk locations, the v1.76-broken sample links resolve, `check_no_two_homes` stays clean, and the artifact **self-validates 84 passed / 0 failed — the first release in Tropo history to do so** — with the 6-point bar passed twice independently and a conducted six-turn cold stranger-walk PASS. Substrate currency marker: through v1.77, refreshed 2026-07-02 by orpheus-o26.

---

## Change Log

### v1.77.0 — 2026-07-02 — Ship-Artifact Path Preservation SHIPPED

*Dev-spec: [ba454e56](ba454e56.md) LOCKED | Doc-spec: [06552e01](06552e01.md) | Gate 1 (v2 floor) closed artifact-true*

- **Path preservation generalized in the build** — `step_4_copy_ship_entries` derives destination subdir + real basename from each entry's actual path; flatten only for true `vault/files/` residents; the `vault/agents/`-only special-case retired into the general rule. No hardcoded directory list — future One-Home dirs ship correctly by construction.
- **The 6 previously-empty One-Home dirs ship populated** — skills / capsules / templates / entities / actions / session-agents land at their real paths with their real (readable, ADR-048) filenames; relative links between shipped files resolve in the extract (broken in v1.75.0 + v1.76.0).
- **Proof ladder** — artifact self-validates 84/0 (first in Tropo history) · 6-point artifact bar (test-spec [e1ede9b4](e1ede9b4.md)) passed twice independently · conducted cold stranger-walk PASS, zero bail-points · Mike independent walk GREEN, signed verbatim.

### v1.76.0 — 2026-06-27 — ADR-045 One Home — rendering contributions SHIPPED

*Dev-spec: [e8d49d3a](e8d49d3a.md) LOCKED | Doc-spec: [7e95a974](7e95a974.md) | a HARD v2.0 gate blocker*

- **Index-builder + catalog generators repointed to `vault/`** — `capsules_dir = vault/capsules/` (was `.tropo/capsules/`); templates scan `vault/templates/`; the capsule scan path updated across six python tools. `skill-catalog` + `sa-agent-catalog` + `tool-catalog` + `toolbelt` regenerate from the new vault paths (catalogs stay at `.tropo/` as generated read-surfaces; their source is `vault/`).
- **Doc↔tool coherence sweep** — capsule/template path references in 340 authored `.md` files (98 + 242) rewritten to the vault paths in the same pass, so the documentation matches the relocated tools (no second drift source).
- **Rendering tools human-named (ADR-048)** — `vault/tools/tropo-rebuild-index.py`, `tropo-rebuild-vault.py`, `tropo-rebuild-project-index.py`, `tropo-generate-capability-catalogs.py`, `tropo-rebuild-events-sqlite.py`.

### v1.2 — 2026-04-20 — No direct changes; indirect enrichment

TLGS was not a first-order v1.2 work surface. The graph layer received indirect enrichment from adjacent ship work:

- **[rebuild-vault.py extended](../../../`vault/tools/tropo-rebuild-vault.py`)** — ADR-035 Surface 1 fix. Type-specific field projection for new types (board-definition, board-snapshot) and new named-field references (status_board / grooming_board / sprint_board / portfolio_board) — the graph index now surfaces these as queryable fields, improving declared-presence checks and subtree navigation.
- **Registry.jsonl Design Spec locked** (Stream 1, A28): [e2f7d195](e2f7d195.md) + 30-record catalog + [scripts/rebuild-registry.ts](../../../scripts/rebuild-registry.ts) (730 lines). Registry is the runtime catalog complementary to the graph index — graph for edge traversal, registry for typed-primitive discovery.
- **Cascade index coverage** — v1.2 added entries to [00-cascade-aae9a37b.jsonl](../00-cascade-aae9a37b.jsonl) (subsystem subtree, now 87 entries) as this session's new capsules + ADRs + matrix + v1.3 project landed.

**Impact:** graph + registry are more discoverable at sub-second. Governance fields reachable from index without opening source files. No structural graph changes.

**Next:** sa.research 028 + 030 proposed TLGS may fold into the renamed **Library** subsystem post-v1.3 Stream A (graph + cascade + registry + index are discovery infrastructure ON the governed document store — not a separate "layered graph" subsystem). Decision falls to A30 + Mike during Stream A matrix lock. If TLGS consolidates into Library, this hub archives with `superseded_by:` pointing at the new Library hub UID.

---

*Tropo Layered Graph System (TLGS) | tropo-layered-graph-system | Owner: metis | Created 2026-04-14 | Change log added 2026-04-20 by Argus A29*
*Board: [[22cffd73]] | All: [[a7a69fc1]] | Tasks: [[c292cd97]]*

---

## Verification Contribution (per matrix v1.0 footer)

A board isn't a screenshot; it's a query declared in prose + a snapshot filed in the Vault + a regeneration any executive can run in-band. Because the render is deterministic from governed sources, an auditor can re-run last Tuesday's board today and get the same answer — or see exactly what changed. Dashboards become evidence, not status theater.

<!-- v1.3 entry nested under original §Change Log above per arch-specs 007 P1-2 remediation. -->

### v1.3 — 2026-04-21 — Rename + reframe + verification-thesis footer
- Renamed TLGS → Tropo Rendering per [capability matrix v1.0 OD2-F](../../TROPO-CAPABILITIES.md). UID preserved.
- **Reframe rationale documented** (per arch-specs 007 P2 concern): the subsystem's operational value at v1.2 already shifted to render-engine-on-governed-sources (board-definitions + snapshots + query vocabulary shipped as Board Reconciliation v0.3). Graph primitives (edge log, traversal index, edge vocabulary) moved to [Library hub (1aba710c)](1aba710c.md) where they belong structurally. The rename with UID preservation reflects the evolution that already happened in v1.2 — not a silent identity swap.
- `subsystem_name` field updated from `tropo-layered-graph-system` → `tropo-rendering`.
- `last_release_reflected` bumped to 1.3.0.
- `aligned_with` reference bumped to subsystem-hub.capsule v1.1.
- Verification-thesis footer added per matrix v1.0 OD2-D.
- Body heading §What This Covers → §What This Subsystem Covers (canonical form).

### v1.4 → v1.6 — 2026-05-05 — Forward-only catch-up consolidated (v1.7 Stream B4)

*Per [Decision 3 of v1.7 brief 6b5f7886](6b5f7886.md): single consolidated entry. Registry pair: row [`53609453`](../../subsystem-registry.jsonl).*

- **Python toolchain port** (v1.5): TypeScript rebuilder family ported to Python for portability — [`rebuild-vault.py`](../../vault/tools/tropo-rebuild-vault.py), [`rehydrate.py`](../../.tropo/scripts/rehydrate.py), [`tropo-validate.py`](../../vault/tools/tropo-validate.py). Every Tropo-OS vault ships with `python3` available; node was not a portable assumption.
- **v1.6 role-filter for project-tree pipeline navigation** (Round 3 in-cycle remediation): rebuild-vault.py role-filter prevents transitive-membership pollution in pipeline-navigation surfaces.
- **Archived-cascade fix** (v1.6 Round 4): rehydrate.py archived-cascade edge case fixed (cascade entries with archived state were leaking into active queries).
- **project-tree.jsonl + 00-tropo-nav regeneration**: every release regenerates these surfaces from current frontmatter; no hand-maintained drift.
- **Board-definition + board-snapshot capsules** locked since v1.2 (UID `b0d1e4f2` + `b5a7c391`); 60+ snapshots in vault; render engine deterministic + reproducible.

**Impact:** the rendering layer is now Python-native, reproducible, and structurally sound. Pre-Python-port edge cases closed in v1.6.

**Next:** v1.7 ship adds a v1.7 release_history row at Gate 6 dogfood. v1.8+ Self-Doc Discipline may surface render-time validation hooks.

