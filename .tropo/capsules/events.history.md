---
uid: 63bf7487
name: "events-history"
type: capsule-history
governs: 72ef5ffe
governs_path: .tropo/capsules/events.capsule.md
extracted_at: 2026-06-11
extracted_by: argus-a110
extracted_in_cycle: "v1.69 — Agent + Playbook Unification (S3 token-performance SPLIT)"
extracted_in_release: pending-v1.69.0
schema_version: 2
governed_by: 5ec083a3
extraction_scope: argo-private
member_of:
  - "8dd772a0"   # tropo-governance
tags: [capsule-history, extracted-from-events-capsule, v1.69-s3-split]
---

# events — Capsule History

*History extracted from events.capsule v1.6 at the v1.69 S3 token-performance split (2026-06-11, Argus A110; capsule was 76,507 bytes vs the 51,200 write-time budget — the largest over-budget write-time primitive per Talos T15's measure table). Active capsule preserves: §1 Intent, §2 Schema (live two-axis identity table + rules), §3 Event Type Registry (all families), §5 Storage Primitive, §6 State Machine, §7 Governance Rules 1–13, §8 Validation Checks, §9 Inheritance, §10 Composes-With, compressed §11/§12 stubs, current + v1.4 frontmatter amendment notes. This file preserves: v1.3 / v1.2 / v1.1 / v1.0 frontmatter amendment notes + the A86 amend-history note, the §2 Po founding-case narrative, the retired §4 Script Identifier Registry narrative + examples, §7 Rule 4 version history, §10 History subsection, the full §11 Studio Shop Signage, §12 v1.55 acceptance tests, and the full §13 Changelog.*

---

## Frontmatter Amendment Notes (extracted; the v1.6 note remains in the active capsule — current+previous fold rule, v1.5 carried no note)

**v1_4_amendment_note:** "v1.3 → v1.4 amendment 2026-06-03 by Argus A95 per Mike-A95 directive 'fix the root cause' (Mike authorized 2026-06-03; status stays locked per this capsule's amend-in-place precedent — v1.1/v1.2/v1.3 were all amended under principal authorization with an amendment-note, not a status flip). ROOT-CAUSE FIX of the addressing incoherence (the Talos-invisible-queue class; ~205 wrong-axis emits measured at 05ab4861). Generalizes the v1.3 Po-only party-UID exception to the WHOLE crew, completing v1.63 Immutable Identity (e85d2d2c, closed 2026-06-02; A94 minted crew party_uids + the registry party_uid column). The canonical agent source_uid / recipients / subject is now the PARTY UID (type:principal, messaging axis); the agent-root UID is the LINEAGE axis only (member_of + generation queries) and must NOT appear as a live agent's source_uid. Verified two-axis map (root/party): Vela 25f5a0b9/e97ac0ae · Argus 6dff0111/cdf9b3ad · Talos 123e12e7/34cf0f1c · Metis 775697b1/7c017d1f · Orpheus c0b3301f/c387a949 · Cosmo 4c4b403e/085bd59a · Po 68830153/d70ae4cb. Changes: §2 source_uid category (a) + Agent-identification section + table + Po-section reframe; §7 Rule 4 flipped; §8 Check 6 spec updated + NEW Check 22 (check_no_agent_emit_from_root_uid, WARN→ERROR at v1.66); §11 signage Rule 4 + pitfall. Substantive event architecture (CloudEvents envelope + storage + families) unchanged — this corrects the identity AXIS the contract names canonical. Companion fixes same session: emit-event tool guard (ca90f098 — rejects wrong-axis agent emits at the tool) + validator Check 22. Composes with the v1.66 messaging cluster (read=dabe7c64 / send=81e52840 / complete=2fe61817)."

**v1_3_amendment_note:** "v1.2 → v1.3 amendment 2026-05-29 by Argus A88 captain-mode (sleeve claude-opus-4-8[1m]) per v1.61 dev-spec 643b441d Lane EC. Closes the messaging-substrate completion (Block 5 cycle 7 of 7). Four categories of change. (1) §3 NEW Broadcast Family — registers tropo.broadcast.crew (crew-wide broadcast event; replaces ops.md crew-broadcast pattern retired in v1.61 Lane D'1 per Q1 retire-all lock; subject anchors at broadcast-target descriptor; lifecycle:evergreen; recipients = all crew party UIDs OR omitted for all-crew). Distinct from tropo.cycle.activated (cycle-coordination-specific) — broadcast.crew is the general crew-wide announcement primitive that ops.md served. (2) §2 severity extension enum extended info/warn/error/fatal → info/warn/error/fatal/flash; §3 NEW severity:flash semantics subsection (FLASH alerts replace alerts.md retired in v1.61 Lane D'2 per Q2 lock; L.3 trigger_detection.py auto-fires continuous-listen polling curve on severity:flash receipt per dev-spec D'2). (3) §3 Substrate-Write Auto-Emission Family NEW type tropo.substrate.archived (bulk/path-based archival-to-99-recycle of substrate NOT covered by tropo.substrate.recycled's vault/files-uid data shape — channels, tools, folders moved to 99-recycle/ per Preservation Discipline; empirically demanded at v1.61 D'4 close where 3 channels + 1 tool archived; ship-primitives-empirical-use-demands not speculation). (4) §7 NEW Rule 13 (all-channels-retired-by-v1.61): channels/ substrate fully retired at v1.61; rendered_from_events Rule 8 becomes historical — no channel files remain; agents query event log directly via V7 doctrine (query-events --party). Substantive architecture (CloudEvents envelope + 2 universal mandatory extensions + storage primitive + L2/L3 readiness + validation discipline) unchanged from v1.2 — additive type + extension registrations + channel-retirement rule. Validator extension at .tropo/scripts/lib/event_validators.py covers new schema (Talos lane per dev-spec EC)."

**v1_2_amendment_note:** "v1.1 → v1.2 amendment 2026-05-28 by Argus A87 captain-mode per v1.59 dev-spec d8c3f1b7 A2 + R3 (composes; same amendment lands both). Two categories of change. (1) §3 Event Type Registry — NEW Cycle Coordination Family section between Release Lifecycle Family and Extending-the-registry. Two types registered: tropo.cycle.activated (cycle activation broadcast; replaces ops.md edit pattern per stm-a87-003 doctrine pin candidate; subject anchors at cycle brief UID; lifecycle:evergreen) + tropo.cycle.ship_gate_progress (cross-lane ship-gate-status signal; cycle-coordinating-agent to ship-firing-agent; subject = ship-firing-agent party UID; lifecycle:ephemeral). Both empirically authored at v1.58 + v1.59 cycles (event 88 ship_gate_progress; event 123 cycle.activated); registration eliminates Path 2 carry (c3b9e2f8) + WARN-at-emit operational noise. (2) §3 NEW Emit-time Strictness Rule subsection (Rule 11). emit-event.py SHOULD reject unregistered event types — WARN at v1.59 default + opt-in --strict-mode flag ERRORs; default ratchets to ERROR at v1.60+ after audit. Composes with Lane V Layer 3 meta-validator (M.1 at 8e2f1a47) as two-tier defense (Layer 3 = validation-time; Rule 11 = emit-time). Substantive architecture (CloudEvents envelope + 2 universal mandatory extensions + 5 primitive event types + hybrid JSONL+SQLite storage + L2/L3 deployment-readiness) unchanged from v1.1 - only Cycle Coordination Family added + Rule 11 added at §3."

**amend_history_2026_05_27_a86:** "Substrate-coherence row updates per v1.58 T.2 by Argus A86 captain-mode 2026-05-27 per Mike-A86 walk authorization. (a) §2 Agent identification table row 'Tropo' → 'Po' with UID d70ae4cb populated (was TBD); closes T.2 dev-spec scope. (b) §2 'Mike's principal UID - registration pending v1.0 implementation' paragraph rewritten to 'Principal UIDs - registered' reflecting that both Mike (3f58b5c5; v1.55 Stream A.2) + Po (d70ae4cb; v1.58 T.1) are now registered; pending-language retired per substrate-honesty. No version bump per fewer-living-documents doctrine cosmetic-edits clause (Mike-A80 Captain's Briefing v3.0 rename precedent applies — schema unchanged; row content + paragraph framing updated to current operational truth). Pattern: stm-a79-004 multi-doc amendment cascade fires from upstream principal-entry LOCK (Po) → downstream events.capsule row update; Argus-lane captain-mode."

**v1_1_amendment_note:** "v1.0 → v1.1 amendment 2026-05-26 by Argus A84 captain-mode per Mike-A84 taxonomy walk Pillar 1 reconciliation. Three categories of change. (1) §3 Event Type Registry - substrate-write event type family renamed to use 'tool' vocabulary not 'script' (per Pillar 1 canonical taxonomy where tools are the typed primitive; scripts are one implementation_kind via transport:cli). source_uid references TOOL UIDs (vault citizens per tool.capsule v1.6 single-file truth at vault/tools/<uid>.{ext}) directly, not 'script:' prefix strings. (2) §4 Script Identifier Registry RETIRED entirely - replaced by vault graph queries for tool UIDs via 00-index.jsonl; tools have proper member_of: graph citizenship per tool.capsule v1.6 + the v1.56 Pillar 1 single-file-truth migration cycle. (3) §10 Composes-With expanded to include tool.capsule v1.6 (canonical relationship - tools as event sources) + how-to.capsule v1.4 + action.capsule v1.1 + session-agent.capsule v1.5 + kernel.capsule v2.0 + sibling Pillar 1 capsules. Composes with v1.56 cycle scope (tools-in-vault single-file reshape + registration completion) which makes the source_uid pattern operational. v1.55 Stream A ships events.capsule v1.1 + emit-event.py + log infrastructure + 5 primitive types + validator extensions; emit-event.py itself will be a tool registered per tool.capsule v1.6 single-file pattern + v1.56 cycle picks up its migration alongside the other ~22 existing tool entries. Substantive architecture (CloudEvents envelope + 2 universal mandatory extensions + 5 primitive event types + hybrid JSONL+SQLite storage + L2/L3 deployment-readiness + 17 validation checks + append-only invariant) unchanged from v1.0 - only the source-identification vocabulary + composability references reconciled to canonical Pillar 1 taxonomy."

**v1_0_authoring_note:** "v1.0 LOCKED 2026-05-26 by Argus A84 captain-mode. Formalizes 9fc86533 v0.2 architectural decisions into typed-primitive capsule definition. Five primitive event types registered: tropo.message.sent + tropo.message.acked + tropo.message.replied + tropo.cycle.opened + tropo.cycle.closed (per 9fc86533 §5 minimum-viable-set decision). Envelope per CloudEvents v1.0 (W3C / CNCF industry standard; per 'check vendor + industry standards' Mike-pin). Two universal mandatory extensions (source_uid + lifecycle) per Decision H; rest per-type-required. Storage primitive hybrid JSONL canonical + SQLite derived per Decision E; synchronous dual-write under single fcntl lock; zero query lag by design. Sharding-capable from v1.0; single shard initially per Decision A. Sibling to pipeline-runtime run.jsonl at v1.0 per Decision G; merge committed later. Composes with publish.pipeline + doc-pipeline + test-pipeline + dev-pipeline cascade discipline. Composes with substrate-verify-twice defect class (substrate-write-as-event auto-emission per Stream C closes the disease structurally; this capsule is the schema substrate Stream C composes against). Mike walks v1.0 → v1.x lock with Argus at next walk; substantive amendments via amendment-note pattern. SUPERSEDED at v1.1 by Pillar 1 taxonomy reconciliation (source_uid vocabulary + §4 retirement + §10 expansion)."

---

## §2 — Po Founding-Case Narrative (extracted; the live crew-wide two-axis rule + table stay in the capsule)

**Agent-class-principal event-identity — the crew-wide pattern (v1.4 generalized the v1.3 Po carve-out).** As of v1.4, EVERY crew agent's event party-UID is a `type:principal` party UID, not the `type:project` agent-root UID — the two-axis shape is the rule for all agents, not an exception. Po (carved at v1.3) was the FIRST instance; v1.63 Immutable Identity minted party UIDs for the whole crew + populated the registry `party_uid` column, and v1.4 makes the party UID canonical for everyone. The Po-specific detail below is retained as the founding case + the reason a party UID can predate an agent-root. Po was originally carved at v1.61 when elevated concierge → executive with a dual-identity (per v1.61 Lane P-shell + Mike-A87 Q2 lock).

Po has **two** UIDs on two distinct axes:

| Axis | Po's UID | Used for |
|---|---|---|
| **Messaging / party axis** | `d70ae4cb` (`type:principal`, `principal_class:agent-concierge`) | `source_uid` when Po **emits**; `subject` / `recipients` when Po is **addressed**; `query-events --party d70ae4cb` returns Po's full event history. THE canonical event identity. |
| **Lineage / identity axis** | `68830153` (`type:project`, agent-root) | `member_of` parent for Po's charter / soul / status card / boot-extension; generation-lineage queries (find Po's activations) walk this. NOT a party UID; NEVER appears as `source_uid` / `subject` / `--party`. |

**Why the exception (rather than migrating Po to emit under `68830153`):** Po's principal entry `d70ae4cb` is the established event-addressing identity — events.capsule §2 has listed it since v1.58, and all prior event references anchor on it. (Note: prior references use `d70ae4cb` as `subject`/`data.uid` — the *affected resource* — never yet as `source_uid`, because Po had not emitted as of v1.61 Lane P-shell. The exception fixes the rule *before* Po's first emit, so provenance is consistent from event #1.) Migrating to `68830153` would orphan those references and split Po's history. One canonical party UID; the cheap-migration + coherent answer is `d70ae4cb`.

---

## §4 — Tool-Sourced Event Identification: v1.1 Retirement Narrative + Examples (extracted)

**v1.1 supersedes v1.0 §4.** Pre-v1.1 this section maintained a `script:` prefixed-string identifier registry for script-sourced events. v1.1 retires the registry entirely because tools are now vault graph citizens with proper 8-hex UIDs per tool.capsule v1.6 single-file-truth at `vault/tools/<uid>.{py|md|json}`.

**Examples (post-v1.56 single-file-truth migration; existing v1.5 sidecar UIDs preserve):**

| Tool name | source_uid value (illustrative; resolves via vault index) |
|---|---|
| rebuild-vault | UID per vault/tools/<uid>.py entry |
| write-activation-entry | UID per vault/tools/<uid>.py entry (currently sidecar at v1.5; migrates v1.56) |
| tropo-recycle | UID per vault/tools/<uid>.py entry |
| pipeline-activate | UID per vault/tools/<uid>.py entry |
| pipeline-runtime | UID per vault/tools/<uid>.py entry |
| build-release | UID per existing vault/files/<uid>.md sidecar (a1b8c2d4); migrates to vault/tools/a1b8c2d4.py v1.56 |
| tropo-validate | UID per existing sidecar (resolves via 00-index lookup) |
| emit-event | UID per vault/tools/<uid>.py entry (NEW tool at v1.55; authored per tool.capsule v1.6 single-file pattern from start) |
| render-events-as-views | UID per vault/tools/<uid>.py entry (NEW tool at v1.55) |

**Composes with v1.56 cycle scope:** all ~22 existing sidecar-pattern tool entries migrate to single-file pattern; their UIDs preserve; events emitted reference unchanged UIDs across the migration. Migration is transparent to event consumers.

---

## §7 Rule 4 — Version History (extracted)

**History (v1.3 → v1.4):** v1.3 carved a single exception for Po (party UID `d70ae4cb` over agent-root `68830153`) because Po's event-addressing identity predated its agent-root. v1.63 minted party UIDs for the whole crew + populated the registry `party_uid` column (A94 Registry Step 3), so v1.4 generalizes that carve-out into the crew-wide rule; the pre-v1.63 "agent-root UID over generation UIDs" framing is superseded.

---

## §10 — History Subsection (extracted)

This capsule is v1.1 (v1.0 LOCKED 2026-05-26 → v1.1 amendment same day for Pillar 1 taxonomy reconciliation). Amendment history will accumulate as the registry extends + storage primitive matures + L2/L3 transitions land. Companion `events.history.md` may be authored at v1.2+ if amendment density warrants per capsule-history.capsule pattern. *(Authored at v1.6 — this file.)*

---

## §11 — Studio Shop Signage (extracted in full)

*What's on the wall above this bench. Scan before you author an event.*

**Tools available:**
- `vault/events/00-events.jsonl` — canonical append-only log; query via `query-events.py` CLI
- `vault/events/00-events-index.sqlite` — derived SQLite materialized-view + index
- `vault/events/files/` — companion file payloads for long-body events
- `.tropo/scripts/emit-event.py` — canonical emit primitive (atomic dual-write under fcntl lock; ~80 LOC stdlib; Talos T10 lane)
- `.tropo/scripts/rebuild-events-sqlite.py` — regenerate SQLite from canonical JSONL on demand (~50 LOC; Talos T10 lane)
- `.tropo/scripts/query-events.py` — thin CLI wrapper so agents query without SQL knowledge (~30 LOC; Talos T10 lane)
- `.tropo/scripts/render-events-as-views.py` — projection renderer engine (Stream B; reads event log; writes channel/status-card/crew-brief projections; Talos T10 lane)

**Skills (forthcoming v1.55+):**
- `author-event-message.skill.md` — scaffold a `tropo.message.sent` event with correlationid + recipients
- `query-active-cycles.skill.md` — query SQLite for active polling cycles + open correlations
- `read-channel-as-projection.skill.md` — substrate-native read pattern for rendered channels

**Rules (at-a-glance):**
1. Append-only (events NEVER edited or deleted; lifecycle is query filter)
2. `source_uid` mandatory (PARTY UID for agents / tool UID for tools / principal UID for humans — agent-root is lineage-only; v1.4)
3. `lifecycle` mandatory (evergreen OR ephemeral)
4. PARTY UID is the canonical agent `source_uid`; agent-root is lineage-only (v1.4; supersedes the pre-v1.63 agent-root rule)
5. Author-vs-emitter split via `author_uid` extension (Mike-as-channel)
6. `correlationid` load-bearing for chains (request-reply + polling cycles + sa.* dispatch)
7. Substrate-writes-as-events composability (seven choke-points auto-emit)
8. Per-channel `rendered_from_events:` marker for migration
9. Pipeline-runtime sibling at v1.0 (merge committed later)
10. JSONL canonical for machine portability
11. JSONL bulletproof recovery (SQLite regenerable)
12. Studio sovereignty composes (federation at L3 via Studio-prefix)

**Pitfalls:**
- **Emitting from the agent-root UID instead of the PARTY UID** — Check 22 violation (v1.4); the message is invisible to a party-UID reader (the Talos-invisible-queue). Use your party UID as `source_uid`. (Charter / status-card UID as source = Check 8 violation.)
- **Omitting `lifecycle` field** — Validation Check 7 violation; default projections require the filter
- **Editing JSONL directly** — Rule 1 governance failure; events are append-only via emit-event.py only
- **Forgetting `correlationid` on replies** — Validation Check 10 WARN at v1.0; ERROR ratchet v1.1+
- **Substrate-write tools that don't emit** — Validation Check 13 WARN at v1.0; ERROR ratchet v1.X+ once retrofit complete

**Worked examples (forthcoming v1.55 Phase D):**
- Mike-V52's "ask Talos to review brief; poll every 2 minutes for reply" pattern as event chain (5 events; 2 correlationids; full pattern at 9fc86533 §5)
- Three sparse-shape examples (different types; different data shapes) at 9fc86533 §4

**Go next:**
- Sibling typed-primitive → doc-spec.capsule v1.0.2 (9a7d314a) — pattern_exemplar structural reference
- Sibling typed-primitive → activation.capsule v1.0 (4e8b21f0) — substrate Stream C auto-emits for
- Design brief parent → Messaging System Reframe v0.2 LOCKED (9fc86533) — architectural rationale + decisions
- Strategic frame parent → Captain's Briefing v3.0 (a5f4b26b) — v2.0.0 ship thesis composition

---

## §12 — How to Validate: v1.55 Acceptance Tests (extracted; shipped + passed)

v1.55 acceptance test (the capsule is shipped when these pass):

1. Mike + Argus walk this capsule v1.0 LOCKED-pending-walk → v1.x lock; substantive amendments via amendment-note pattern
2. Stream A foundation ships: `emit-event.py` + `vault/events/00-events.jsonl` + `vault/events/AGENTS.md` + five primitive event types operational + first event rows queryable
3. Validator extensions ship (Validation Checks 1-10 minimum); event log validates clean at first rebuild-vault.py run
4. Stream A regression test passes: emit-event under concurrent contention; SQLite query lag = 0; recovery from mid-write crash; rebuild-events-sqlite.py round-trips clean

v1.56+ acceptance tests (deferred to later cycles):
- Stream B (projection renderer) ships
- Stream C (substrate-write auto-emission retrofits) ships at the seven choke-points
- Stream D (legacy channel deprecation) ships

---

## §13 — Changelog (extracted in full)

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.4 | 2026-06-03 | **v1.4 amendment** by Argus A95 per Mike-A95 "fix the root cause" directive (status stays locked per this capsule's amend-in-place precedent). Root-cause fix of the addressing incoherence (the Talos-invisible-queue; ~205 wrong-axis emits at 05ab4861): generalizes the v1.3 Po-only party-UID exception to the WHOLE crew, completing v1.63 Immutable Identity (A94 minted crew party_uids + the registry party_uid column). The canonical agent `source_uid` / `recipients` / `subject` is now the PARTY UID (`type:principal`, messaging axis); the agent-root UID is the LINEAGE axis only. Changes: §2 Agent-identification section + table (both axes) + Po-section reframe; §7 Rule 2 + Rule 4 flipped; §8 Check 6 spec updated + NEW Check 22 (`check_no_agent_emit_from_root_uid`, WARN→ERROR at v1.66); §11 signage Rule 2/4 + pitfall. Substantive event architecture (CloudEvents envelope + storage + families) unchanged. Companion fixes same session: emit-event tool guard (`ca90f098` — rejects wrong-axis agent emits at write-time) + validator Check 22. Composes with the v1.66 messaging cluster (read=`dabe7c64` / send=`81e52840` / complete=`2fe61817`). | argus-a95 |
| 1.3 | 2026-05-29 | **v1.3 amendment** by Argus A88 captain-mode (sleeve claude-opus-4-8[1m]) per v1.61 dev-spec 643b441d Lane EC — closes messaging-substrate completion (Block 5 cycle 7 of 7). Four changes: (1) §3 NEW Broadcast Family registers `tropo.broadcast.crew` (replaces ops.md crew-broadcast pattern retired v1.61 D'1); (2) §2 severity enum extended with `flash` + §3 severity:flash semantics subsection (replaces alerts.md FLASH channel retired v1.61 D'2; L.3 trigger_detection.py auto-fires continuous-listen curve on receipt); (3) §3 Substrate-Write Auto-Emission Family NEW `tropo.substrate.archived` (bulk/path-based archival-to-99-recycle not covered by recycled's vault/files-uid shape; empirically demanded at v1.61 D'4 close); (4) §7 NEW Rule 13 — crew-internal channels become queries; user-facing surfaces (tropo.md activity + releases.md news) stay as event-projections (corrected same-day per Mike-A88 keep-the-two-surfaces lock from an initial "all-channels-retired" over-claim; the by-audience distinction is the accurate close). Additive type + extension + rule registrations; substantive architecture unchanged from v1.2. Validator extension at event_validators.py covers new schema (Talos lane). | argus-a88 |
| 1.1 | 2026-05-26 | **v1.1 amendment** by Argus A84 captain-mode per Mike-A84 taxonomy walk Pillar 1 reconciliation. Three categories of change: (1) §3 Event Type Registry substrate-write event-type family renamed to use 'tool' vocabulary not 'script' (per Pillar 1 canonical taxonomy where tools are the typed primitive; scripts are one implementation_kind via transport:cli); (2) §4 Script Identifier Registry RETIRED entirely - replaced by vault graph queries for tool UIDs via 00-index.jsonl; tool UIDs at vault/tools/<uid>.{ext} per tool.capsule v1.6 single-file truth are valid source_uid values directly; (3) §10 Composes-With expanded with Pillar 1 sibling capsule references (tool + how-to + session-agent + action + kernel). Substantive architecture (CloudEvents envelope + 2 universal mandatory extensions + 5 primitive event types + hybrid JSONL+SQLite storage + L2/L3 deployment-readiness + 17 validation checks + append-only invariant) unchanged from v1.0 - only source-identification vocabulary + composability references reconciled. Composes with v1.56 cycle (tools-in-vault Pillar 1 single-file-truth migration) which operationalizes the source_uid pattern. | argus-a84 |
| 1.0 | 2026-05-26 | **LOCKED v1.0** by Argus A84 captain-mode per Mike-A84 Option A walk-posture. Translates 9fc86533 v0.2 LOCKED architectural decisions (9 decisions A-I; Vela V52 + Mike-V52 walked 2026-05-24) into typed-primitive capsule schema + governance + validation. Five primitive event types registered (tropo.message.sent + acked + replied + tropo.cycle.opened + closed). Substrate-write auto-emission family + agent lifecycle family + sub-agent dispatch family + pipeline lifecycle family + release lifecycle family registered. Two universal mandatory extensions (source_uid + lifecycle) per Decision H; rest per-type-required. Hybrid storage primitive (JSONL canonical + SQLite derived; synchronous dual-write under single fcntl lock; zero query lag) per Decision E. CloudEvents v1.0 envelope alignment. correlationid extension adopted directly from CloudEvents Correlation extension per Decision I. Sharding-capable from v1.0 per Decision A. Sibling to pipeline-runtime run.jsonl at v1.0 per Decision G. L2/L3 deployment-ready by design constraint. Composes with publish.pipeline + doc-pipeline + test-pipeline + dev-pipeline cascade discipline. Composes with substrate-verify-twice + Workbench Surface Visibility + Self-Healing + Captain's Briefing v3.0 + Federation Foundation. v1.0 LOCKED-pending-walk; Mike walks v1.0 → v1.x lock at next walk; substantive amendments via amendment-note pattern. SUPERSEDED at v1.1 by Pillar 1 taxonomy reconciliation. | argus-a84 |

---

## Footer (pre-split version line, extracted)

*events capsule definition | UID `72ef5ffe` | v1.3 LOCKED | v1.3 amendment 2026-05-29 by Argus A88 captain-mode (v1.61 Lane EC — Broadcast Family + severity:flash + tropo.substrate.archived + Rule 13 crew-channels-become-queries-user-surfaces-stay-projections [corrected same-day per Mike-A88 keep-the-two-surfaces lock]; closes messaging-substrate reframe). v1.2 amendment 2026-05-28 by Argus A87 (Cycle Coordination Family + emit-time strictness). v1.1 amendment 2026-05-26 by Argus A84 (Pillar 1 taxonomy reconciliation). v1.0 LOCKED 2026-05-26 per Mike-A84 Option A walk-posture.*

*(Note: the pre-split footer's "v1.3 LOCKED" lagged the actual v1.6 frontmatter version — a drift instance preserved here honestly; the post-split active footer states the current version.)*

---

*events — Capsule History | UID `63bf7487` | extracted 2026-06-11 by Argus A110 at the v1.69 S3 token-performance split | governs: events.capsule (72ef5ffe)*
*"The capsule carries the contract; the companion carries the becoming."*
