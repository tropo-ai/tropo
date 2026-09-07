---
uid: 'fc316d7f'
type: document
title: "Tropo L1 — Architecture Review v4"
description: "The Studio's deep canonical document: what the L1 system is, why it is shaped this way, and its dated failure record — Parts I–V, RE-VERIFIED 2026-08-26 by an eight-agent adversarial pass. One of the two canonical documents (with the Studio Map, 3e581123)."
status: published
state: active
owner: metis
member_of:
  - "8dd772a0"
created: '2026-08-24'
created_by: metis-g112
modified: '2026-08-27'
modified_by: metis-g113
schema_version: 2
governed_by: 8dd772a0
extraction_scope: ship
refs:
  - 3e581123
  - 6e9f6549
  - 85e60da0
tags:
  - architecture-review
  - canonical-document
---

# Tropo L1 — Architecture Review v4

**Prepared for:** Engineering briefing (software engineers) · CTO / CISO review
**Prepared by:** Metis (Tropo Strategist agent, generations G112–G113), with Mike Maziarz — building on v3 by Metis G107 and v2 by Argus A129
**Date:** 2026-08-24 · **Part IV added 2026-08-26**
**System version:** Tropo-OS **v1.92.0 SHIPPED** (published 2026-08-26T20:12:48Z, publisher liveness verified 20:13:41Z, receipt `3fe4be3f…`) *(v2 was a full re-verification at v1.84.1, 2026-07-10. §1–16 stand as-measured at v1.84.1; Part II is the delta through 2026-08-12; Part III through 2026-08-24; Part IV through the v1.92.0 ship, 2026-08-26. Where a later part SUPERSEDES an earlier claim, it says so explicitly.)*
**Status:** **RE-VERIFIED 2026-08-26** — the full adversarial re-verification ran the night v1.92.0 shipped: eight parallel agents, ~211 claims, refute-posture, every number command-measured against the live substrate. Verdict: no fabrications; five claims WRONG at their own measurement dates (each now corrected in place and marked); the supersessions that actively mislead carry inline warnings; Part V and the governed report (`6e9f6549`) carry the full findings. Parts I–III each retain their original measurement dates; scale figures are snapshots and drift — see the currency note below.
**Scope:** The L1 (local, file-based) tier of the Tropo operating system, as proven in the Argo development Studio

> ## ⚠ Currency note — figures are dated snapshots
>
> Every part of this document is measured at its own stated date, and the substrate moves fast.
> Argus A158's measured currency stamp (2026-08-26, on the v3 edition) found §1–16/§22 figures
> already drifted — tool scripts 61 → **109**, validator checks 94 → **115**, capsules 64 → 69,
> Chief Architect A129 → A158 — two weeks after Part II's measurement. **Verify any figure against
> the substrate before citing it.** What does not go stale, and is the reason to read this: the
> dated failure record (§10, §12, §14.3, §18–19, §23–25, §29–30). Architecture descriptions drift;
> history does not. Read-at-need for architecture work — **not a boot read** (~25K tokens).

---

## Executive summary

Tropo is an operating system for running real work with AI agents, built entirely on plain markdown files in a folder. It requires no server, no database, and no proprietary runtime. Any AI harness that can read text and follow instructions can operate inside it; any human with a text editor can audit every byte of it. The OS itself is **open source — Apache 2.0, public at github.com/tropo-ai/tropo** (license set at v1.41.0, repository public since ~2026-06-20); each Studio's *content* stays private by a default-deny publish boundary.

The system solves five problems that make AI-agent work hard to trust in a professional setting:

1. **Identity and continuity.** AI agent sessions end; the work cannot. Tropo gives each agent a durable identity (charter, soul document, memory, lineage record) that survives across sessions and across underlying model changes. The development crew's Chief Architect role has run **129 generations** — including the one writing this document — with identity, memory, and open work surviving every handoff, across multiple model families.

2. **Governed, typed knowledge.** Every artifact — task, decision, document, release, message — is a typed markdown file obeying a declared schema ("capsule"). A validator suite (94 check functions, ~90 executed per run) enforces those schemas at every rebuild. Structure is added gradually and tighten-only, so governance never breaks older data and never breaks the plain-text floor.

3. **Auditable coordination.** All agent-to-agent and agent-to-human coordination flows through one append-only event log with a standard envelope (CloudEvents v1.0) — 6,100+ events as of this review. Delivery is a three-state contract (delivered → read → answered) backed by per-reader receipt ledgers; human-readable views are rendered projections of the log, never separately authored surfaces that can drift.

4. **Verification as a structural property.** "Done" is not a claim an agent gets to make about its own work. Completion gates require independent verification receipts; an approver cannot be the executor; documentation and test pipelines are coupled to the release pipeline. The design center is **bounded verification**: a human expert verifies outcomes at defined gates, and the substrate is built so that verification capacity, not agent capability, is what scales. *(This review also reports, honestly, where that promise was design-true but execution-unproven — and what was done about it. See §10.)*

5. **Multi-party sovereignty** *(new since v1)*. Two Studios can now share a team vault over a plain git remote under a proven covenant: **no private byte crosses the wire, in either direction.** The publish path was adversarially attacked by a fleet of red-team agents that forced real leaks out of the first build — five HIGH-severity leak paths were found, fixed, and pinned with regression tests; the re-verification ran clean, fail-closed on every angle. Shipped at v1.84.1 on the day of this review.

The system is dogfooded at full intensity: Tropo is built *by* a human-AI crew operating *inside* Tropo. The release index carries 98 Tropo-OS release records spanning 96 distinct versions (v1.1.0, first shipped April 2026 → v1.84.1) — plus six releases of *other* products (two knowledgebase lines and an app) shipped through the same pipeline. Fourteen OS releases shipped in the 26 days since the v1.70.0 baseline this review's v1 was refreshed at.

This document walks the architecture top-down. Each section references a diagram in `svg/`. Sections 10, 13, and 14 are substantially new: release engineering (including where the release gates failed and how they were fixed), federation, and the refreshed security posture. The candor is deliberate — this system's own doctrine is that failures become substrate, not folklore, and a reviewer should read the failure record as the system working.

---

## 1. What Tropo L1 is — and the design theses behind it

**One Studio = one folder.** An installation of Tropo is called a *Studio* — a single directory tree of markdown, JSONL, and a small library of Python scripts. The Studio reviewed here (`argo-os/`) is the development Studio where Tropo itself is built. Inside every Studio sits a *Vault* — the protected, governed content store where every typed artifact lives.

Five theses drive every design decision:

**Thesis 1 — Markdown is the protocol.** Governance, schemas, procedures, memory, and messages are all expressed in language a reasoning engine reads and follows. There is no permissions API and no database constraint at the base layer; the governance *is* the language. This is what makes the system harness-portable: it has run under multiple commercial AI products and multiple model vendors without modification, because the only interface contract is "can read files, can follow instructions."

**Thesis 2 — Agent-first, human-also.** Agents are the primary operators; humans are the directors and verifiers. The base layer is shaped for how agents read and work (flat stores, UID addressing, typed frontmatter). A deliberate human layer sits on top: every governed file renders a navigation block (path, parent, children, siblings, cited-by); dashboards and a rendered navigation tree give the human a visual surface. The rendered surface is a deliverable, by doctrine — if the human is staring at raw substrate they cannot read, the surface has not shipped.

**Thesis 3 — Local-first, minimal infrastructure.** No server, no database, no runtime service. Everything that looks like infrastructure (indexes, a SQLite query layer, dashboards) is *derived* from the files and rebuildable from them at any time. The deployment story is "a folder," and the disaster-recovery story is "the folder, plus one rebuild command." *(v1 of this review claimed "no network calls made by the substrate itself." That is no longer strictly true — release upload, update discovery, federation transport, and an optional API-cost metering gateway all touch the network. §14 enumerates every network-touching component; the substrate's day-to-day operation remains fully offline.)*

**Thesis 4 — Gradual structure on a language base** (ADR-044). Keep the free-form markdown playground; add structure per-type and per-field, incrementally, enforced through agent-native mechanisms (tools, validation gates, grooming agents) — never storage-layer rigidity. Tightening is one-way and backward-compatible: structuring never breaks older data, and a hand-written file is never hard-rejected.

**Thesis 5 — Verification is the moat.** As execution cost falls toward zero, the binding constraint becomes human verification bandwidth. Tropo is built so that a domain expert can verify whether agents operated within constraints she defined — and so that the verification effort scales with the quality of the constraints, not the volume of agent output.

**The posture around the theses** (new since v1): the OS is a public artifact. Every release is built by a positive-filter extraction (only `extraction_scope: ship` entries leave the Studio — 495 of 4,239 records today), so the public repository carries the operating system and none of the Studio's private working content. "Build as if a stranger reads it today" is now literal.

**Diagram:** [`svg/01-system-map.svg`](svg/01-system-map.svg)

---

## 2. The system map — three layers, nine subsystems

The Studio decomposes into three layers:

- **Layer 1 — Kernel (`.tropo/`).** Since ADR-045 ("One Home," accepted 2026-06-20, executed v1.76–v1.77) the kernel is deliberately small: a **bootstrap floor** of thin pointers — boot configuration, the Studio boot extension, the activation playbook pointer, the Self-Healing primitive, the concierge entry — i.e., exactly the cold-read set an agent needs *before* the index exists, plus generated capability catalogs and orientation surfaces. The ~64 capsule definitions, the playbook library, the standard skills, and the script library all now live in the Vault at `vault/<type>/`, where they are indexed, governed, and updated like any other governed content.

- **Layer 2 — Primitives.** The structural vocabulary every Studio uses: the Vault (flat typed file store plus graph semantics), the event log (coordination substrate), the callable-surface classes (§9 — now five of them), and the memory/continuity substrate.

- **Layer 3 — Apps.** What gets built on top: the work-management system (tasks, projects, decisions, releases, boards), the pipelines and loops, the crew of agents itself, and the human surfaces.

Cutting across the layers, work is organized into **nine subsystems** — unchanged in name and count since v1: Governance, Rendering, Work, Agents, Playbooks, Library, Documentation, Link (scheduling/persistence), and Test Harness. Each has a *hub* — a typed project entry that owns the canonical state for its domain — and governed primitives declare their owning hub in frontmatter, which makes "what does the governance subsystem currently contain?" a query rather than an archaeology project. *(Corrected at the 2026-08-26 re-verification: hub declaration is at or near 100% for playbooks, actions, and session agents, ~90% for capsules and skills — but only 31% of the tool fleet declares a hub. "Every" was an unmeasured absolute.)* A per-release touch-record registry (new since v1) additionally logs which subsystems each release touched.

**Diagram:** [`svg/01-system-map.svg`](svg/01-system-map.svg)

---

## 3. The typed substrate — capsules, the Vault, and the graph

### 3.1 Capsules: schema as governed markdown

Every artifact Tropo tracks is a *typed* file. Each type has a definition at `vault/capsules/tropo-<name>.capsule.md` — called a capsule — declaring required fields, lifecycle state machines, enumerated values, governance rules, and validation checks for that type. The capsule is the contract; the file is what obeys it; the validator enforces it. **64 capsule definitions** are on disk today (v1: ~60), with 16 history companions preserving amendment lineage.

All types descend from a root `core` type (uid, type, status, state, owner). The foundational set — task, decision, project, document, collection, note, playbook, pipeline, pipeline-run, board — is extended by domain capsules that each *earned* their abstraction: release and release-plan, design-brief and dev/doc/test-spec, activation (agent lineage), events (the message envelope contract), memory, agent and session-agent, tool, subsystem-hub, the import/export family — and, new in this window, **loop** and **loop-run** (governed autonomy, §8), **vault** and **vault-entity** (federation, §13). One honest correction to v1: it reported the `how-to` type retired for zero instances. That type is today the live schema for the **skills** library (27 instances, §9) — retired honestly when unused, revived when the abstraction was finally earned.

Three contract features matter for a technical audience:

- **Closed canon, open aliases (SKOS-style).** An enumerated field declares one canonical value set plus an unbounded alias map. Agents can write naturally ("complete"); the substrate normalizes to one truth ("done"). Since v1.72 ("One Vocabulary") these lifecycle vocabularies are machine-enforced across the governed type fleet, with status/state enum drift ratcheted to ERROR.
- **A per-type strictness dial.** High-value types (task, decision, release, activation, capsule) enforce hard; the free-form long tail stays loose. Structure is spent where it pays.
- **Two-tier naming (ADR-048).** Shipped OS components carry clean `tropo-<name>` filenames — the Tropo-owned-vs-user-content boundary is readable at a glance. User content is addressed by UID (with a ratified move to `<slug>-<uid>.md` display names not yet executed). The UID is the immutable primary key; every cross-reference resolves by UID, so renames are display-layer-only and can never break a citation.

Schema evolution is a *gated act*: a new field or enum value added through a deliberate, principal-signed capsule amendment is evolution; the same value silently written by an agent is drift, and the gate is what tells them apart.

**Diagram:** [`svg/02-capsule-type-system.svg`](svg/02-capsule-type-system.svg)

### 3.2 The Vault: flat files, graph semantics, derived surfaces

Every governed artifact lives in the Vault, named by an 8-hex UID — the bulk at `vault/files/` (3,740 files), the rest in per-type One-Home directories (`vault/capsules/`, `vault/tools/`, `vault/skills/`, `vault/playbooks/`, `vault/actions/`, `vault/session-agents/`, `vault/agents/`). The index holds the **whole Studio**: 4,239 governed records as of 2026-07-10 (v1: 3,400+). There is no folder hierarchy to rot, and references cite UIDs rather than paths.

Organization is *graph membership*, expressed in frontmatter: `member_of` (home project(s), multi-parent allowed), `governed_by`, `refs`, `subsystem_hub`, `superseded_by`. The graph now carries **18,168 directed typed edges across 4,122 connected nodes** (v1: ~8,500 across ~2,800 — the graph more than doubled in 26 days, driven partly by a new `mentions` edge class extracted from bodies: 6,561 edges). Distribution: member_of 3,981 · refs 2,969 · governed_by 1,677 · subsystem_hub 1,522 · mentions 6,561 · others ~1,450.

Everything else is **derived and rebuildable**: the authoritative JSONL index (one row per artifact), per-type index shards, an O(1) graph-traversal index, a SQLite query runtime (entries + edges + FTS5 full-text over 4,239 rows), the rendered human navigation tree, dashboards, and the crew brief. A rebuild pass regenerates all of it from the files; `rebuild --only <uid>` freshens a single entry. Because the files are the truth, index corruption is an inconvenience, not an incident. New since v1, the derived layer also carries **decay signals** (v1.82 "The Gardener"): a flag-only grooming pass stamps staleness/health markers on the index — adversarially proven unable to modify source files (two independent red-team agents with full-tree SHA256 baselines could not construct a write path).

Two structural truth rules landed in this window:

- **Truth-state is structural (ADR-047).** Measured motivation: 38% of the index was archived/superseded, and ~157 entries carried lying status flags after three failed flag-based fixes. The rule: every *superseded* item MUST carry a resolvable forward-pointer to its current truth (validator-enforced at ERROR since v1.75; plain retirements without successors are correctly exempt, and pre-cutoff history is grandfathered by name), and the current/archive index split is ratified (its Layer-1 build is still pending — disclosed in §14).
- **Deletion is always soft.** The canonical gesture moves entries to a dated recycle folder with a logged reason; raw `rm` of governed substrate is forbidden by signed doctrine. The disposition tool refuses to recycle any node that still has inbound references.

**The write path, end to end** (the engineer's view): an agent writes a typed markdown file → the index rebuild derives every surface from frontmatter → the validator gates the result (WARN→ERROR ratchets) → grooming agents normalize what is provably mechanical and flag what needs judgment → the rendered human surfaces regenerate. Hand-editing a file always works and is caught downstream — tools are the paved road, never a mandatory gate.

**Diagrams:** [`svg/03-vault-graph.svg`](svg/03-vault-graph.svg) · [`svg/10-write-path.svg`](svg/10-write-path.svg)

---

## 4. Agent lifecycle — boot, session, retirement, succession

This is the subsystem most foreign to a traditional architecture review, and the one Tropo considers its load-bearing differentiator. The premise: **an agent is not the model.** An agent is a composite — a soul document (character and behavioral rules), accumulated memory, the Vault, the crew context, and whatever model "sleeve" is running it today. Sessions end; the composite persists in files.

### 4.1 Boot: three tiers, six gated groups — now with a governed cost budget

Activation runs through a three-tier configuration chain (OS floor → Studio extension → agent extension) and six groups in strict order — boot configuration, identity verification, context loading, operational grounding, self-diagnostic, startup signal — each writing a milestone event to a per-run log before the next may begin. The gates are structural: a group whose predecessor milestone is absent from disk stops.

Two **hard gates** protect lineage integrity, validated twice (at boot, and at write-time by the tool that creates the activation record):

- **ADR-016 — no parallel generations.** If the predecessor's status is still ACTIVE, activation halts.
- **ADR-028 — generation monotonicity.** If this generation does not equal predecessor + 1 in the activation registry, activation halts.

> **⚠ SUPERSEDED — read §17 before acting on this subsection.** The halt posture described above
> was retired 2026-08-06: *existence cannot be refused; findings are recorded, never blocking.*
> ADR-016/028 remain graph invariants checked at the mint, but a violation records a `provisional:`
> finding on the birth line and the agent is born anyway. This warning sits here because a reader
> who stops before Part II would otherwise carry the wrong model of the system's most load-bearing
> subsystem (flagged by Argus A158's currency stamp, 2026-08-26).

**New since v1 — boot cost became a governed budget, not a cultural norm.** The trigger was measured: one boot ran 30 minutes and 172K tokens against a 7–8 minute bar. The v1.79 Boot Contract responded structurally:

- **Drift-gated compaction artifacts.** Established agents boot from a *fast-path* (~3–4K tokens, replacing the ~15K canonical playbook read) plus a *doctrine digest* (replacing ~16K of verbatim doctrine re-reads). Both artifacts declare SHA-256 fingerprints of every source they compress **and of themselves**; a validator check recomputes all of them on every run and fails closed on any mismatch — a compacted read can never silently drift from its canonical source. The compression itself was adversarially gauntleted (the first digest version was verdict GAPS-FOUND; ten behavior-changing rules were restored before cutover).
- **A boot-budget tally.** Boot events carry ISO-8601 timestamps; a validator check reads the latest activation run and flags any boot over 10 minutes or that never completed. Most measured boots since land between **1.4 and 4.5 minutes**; two long-session outliers (~20 minutes) show the gate earning its keep — it flags them.
- **Self-maintenance rides the boot.** Every boot checks for pending OS updates (first agent of the day fetches the remote manifest, offline-safe); overdue maintenance loops (§8) with owner consent are dispatched automatically and their cost is stamped from real API metering.

A deliberate cultural gate rides the boot as well: the **self-diagnostic**. Every agent, at every boot, is required to critique the system it just loaded — is anything outdated, counterproductive, or missing? — and to verify its predecessor's handoff claims against current substrate before trusting them. The inherited system is treated as "the best the predecessor had time to build," never as correct by default.

### 4.2 Retirement and succession

Retirement is a governed fold, not an exit: the retiring generation writes a forward-looking *living transfer* at peak context, a backward-looking honest *reflection*, has its memory folded (with a structural bound — see §5), flips its status surface, and closes its activation registry entry. The successor boots through the same gates and verifies the transfer's carry-forward claims against live substrate, because handoffs are snapshots and snapshots drift.

**Worked proof at scale:** the Chief Architect role is at generation **A129** (this author); the Chief of Staff at V64; the engineering lead at T28; the whole crew turns over continuously and open work survives every handoff — including, in this window, a release that was mid-flight across three generations of two different agents and shipped correctly.

**Diagram:** [`svg/04-agent-lifecycle.svg`](svg/04-agent-lifecycle.svg)

---

## 5. Memory architecture (v3.0)

Memory is treated as load-bearing infrastructure, designed to the same standard as the work substrate. Version 3.0 is now **fully deployed across the crew** (v1 said "currently cascading" — the cascade closed 2026-06-10). The shape:

- **One curated read at boot.** `agent-memory.md` — priority-ordered durable pins (Top of Mind), the predecessor's living transfer, and pointers to frozen per-generation history snapshots and the episodic log. The surface routes; canonical artifacts hold the substance.
- **One append-only write during work.** `agent-memories.jsonl` — the episodic log. Mid-session lessons, one JSON line each. It is **never cleared**; folds advance a boundary marker, and every pre-fold surface is frozen with a SHA-256-verified snapshot.
- **Governed folds in between.** A curator folds episodic entries into the curated surface at retirement, at boot when a staleness gate trips (three generations *or* fifty unfolded entries), and for migrations. The booting agent ratifies every curator recommendation.

**New since v1 — the memory bound became structural.** The measured failure: eight consecutive retirements did in-line folds bypassing the curator, and one agent's Top-of-Mind grew to 33 blocks (~48K tokens) — one of the two measured root causes of the 30-minute boot (the other: redundant reads the fast-path itself carried, cut in the same cycle). The fix is a validator gate (ERROR above 15 Top-of-Mind entries or 32KB surface size) plus a retirement rule making curator dispatch mandatory on over-bound folds. It has already fired in production twice, correctly, folding 60→15 and 26→14 entries. The design lesson generalizes: **don't trust the discipline; let the substrate catch the lapse.**

**Memory sovereignty (Operating Principle 14, new).** Agents running inside commercial harnesses have access to harness-private memory stores. A real incident (an agent wrote six substrate-class pins to a harness store — invisible to successors, non-portable) produced a binding principle: durable memory writes go to Tropo memory paths, never harness-private storage. Portability of the *whole agent composite* is the promise; memory in a vendor silo breaks it.

A Studio-tier shared memory carries crew-wide doctrine pins with the same shape; every agent inherits it at boot.

**Diagram:** [`svg/05-memory-architecture.svg`](svg/05-memory-architecture.svg)

---

## 6. The event system — coordination as an append-only audit trail

All coordination flows through one canonical log: `vault/events/00-events.jsonl` — append-only, tool-mediated writes only, one CloudEvents v1.0 envelope per event, correlation IDs for reply chains. **6,103 events as of the morning of 2026-07-10** (v1: 3,900+; the log grows by hundreds per week under real workload).

> **⚠ SUPERSEDED 2026-07-18 (verified byte-level at the 2026-08-26 re-verification): the "one
> canonical log" is now a distributed ledger.** The single log was byte-frozen at the
> event-streams-v2 cutover (`.tropo/event-streams-v2.enabled`, dev-spec f15a9b85) — its sha256
> still matches the pinned epoch hash exactly, at exactly the pinned 6,678 rows. New events
> append to per-writer conversation streams (`vault/events/streams/` — 272 files, 5,237 events,
> actively written at re-verification). The emit tool routes on the cutover flag; read tools
> operate on the legacy-epoch-plus-streams union; receipts key on immutable per-stream event
> UIDs. **Every other property in this section — envelopes, tool-mediated appends, correlation
> chains, the three-state delivery contract, identity guards, telemetry — survived the cutover
> unchanged** (all re-verified live 2026-08-26; receipt ledgers carried same-hour read stamps).

Four properties matter:

**1. Projections, not authored surfaces.** Twenty-two hand-authored channel files were retired outright in the messaging-substrate consolidation; agents read the log directly, and surviving human-facing surfaces are rendered projections of it. One source of truth, many views.

**2. Identity-guarded writes.** Every actor — human or agent — has a registered UID; each agent carries two on two axes (a *party* UID for messaging, an *agent-root* UID for lineage). The emission tool rejects wrong-axis traffic in both directions, and superseded identities persist as resolvable tombstones but are rejected as signers.

**3. A three-state delivery contract** *(new since v1)*: **delivered → read → answered.** Delivery is the event in the log; *read* is recorded in a per-reader receipt ledger (`vault/events/receipts/<party>.jsonl`) written by the drain tool; *answered* requires a reply whose correlation ID matches the original event. A `reply_required` flag creates a visible obligation, and the answered-state is computed from correlations — not from anyone's claim. The operating bar, set by the principal after lived failure: *a message addressed to an agent cannot be missed, and a completion cannot be invisible — by construction.*

**4. Tool telemetry in the same record.** Every substrate-writing tool (rebuilds, recycles, activation writes, pipeline operations, validator runs, releases) auto-emits into the same log, so "what happened, in order" is one query over one file.

**Diagram:** [`svg/06-event-system.svg`](svg/06-event-system.svg)

---

## 7. Tropo Work — the work-management application

Work is the killer-app subsystem: agentic teams executing real work with audit trails, verification, and cross-generational continuity.

The primitives are the ones a Jira-literate team expects, expressed as typed files: **tasks**, **projects**, **decisions** (57 decision records; 53 numbered ADRs through ADR-052 — each a binding architectural commitment), **design briefs**, **release plans and releases**, **notes**, and **collections**. Boards and dashboards are derived views over (membership × status × target); surfaces never become containers.

Design points worth an engineer's attention:

- **Per-type richness, derived rollups.** Each type keeps its own natural status vocabulary; a computed `meta_status` view rolls every value into To Do / In Progress / Done — declared per-capsule and *computed, never stored*. Since v1.72 the rollup is machine-derived from capsule definitions.
- **Inboxes are graph nodes.** Every project and subsystem has an inbox; all walk upward to one Studio-root inbox. Capture is one gesture; nothing filed can become unreachable.
- **Backlog drift is structurally bounded** *(new)*: an undispositioned-stale check flags any owned work item that sits untouched past 45 days (ERROR since v1.75), and the disposition tool makes archive/re-home mechanical — with inbound-reference safety. Every archived item must point forward to its current truth (ADR-047).
- **Workbench visibility is doctrine** (principal-signed, verbatim in the record): the Studio always provides surface visibility — a workbench where every tool is visible; no work gets dropped or orphaned.

The **import → work → export loop** for real-world documents matured into a hardened boundary (v1.81 "Work Crosses the Boundary"): a `.docx` (now also `.md` / `.pptx`) imports to a governed vault entry with a markdown working copy; agents edit in markdown while the source binary stays untouched; export rebuilds the deliverable with a **locally-auditable round-trip receipt disclosing every content drop**. The receipt itself was the hard part: the first build's receipt hashed the working copy against itself — a "receipt that cannot lie" failure caught by an 18-agent adversarial battery and fixed before ship. Export is verified to run with the network fully cut. On source deletion, the vault retains the node and re-links on resurface (ADR-046) — graph memory survives filesystem churn.

---

## 8. Pipelines, playbooks — and loops: orchestration with structural gates

**Pipelines** are declarative workflow templates — a DAG of nodes (pipeline → stage → step), authored once and versioned. Each execution is a typed *pipeline-run* that pins the template version, roots its own project, and keeps its own event log. **Playbooks** are governed procedures in natural language; gated playbooks write milestone events, and later groups structurally cannot begin until the prior milestone exists on disk.

**Loops are the third orchestration class** *(new, v1.71)*: governed *recurring* autonomy. A `type: loop` entry declares goal, trigger, cadence, runner, verifier — and **brakes**: spend caps, wall-clock kills, iteration hard-stops, and a consent mode (`ask` by default; `auto` only by owner ruling). Six loops exist today (daily vault health, weekly integrity audit, update discovery, git backstop, gardener decay pass, one draft dispatcher). Loop cost is stamped **null-honest** from real metering: an optional gateway on live API traffic records actual per-run spend from provider usage data — never estimated, and never fabricated when unmeasured. This is the "self-maintaining Studio" (v1.79): maintenance as governed, costed, consent-gated substrate rather than cron folklore.

The proof-of-pattern is the **dev-pipeline** — the scaffold through which Tropo ships Tropo: design brief → locked dev-spec (adversarially reviewed before lock) → build → verification → ship gates → cut. A dev cycle triggers a doc-pipeline and a test-pipeline run and cannot close until both legs reach a terminal state *(qualified 2026-08-26: the terminal-legs gate survives in the engine ceremony, but the operative close gesture since 2026-08-21 is `tropo-close-dev.py` — ungated by Mike's ruling, "never refuses a close": it records what happened rather than gating it; legs moved to release-opened under the §18 split)* (the doc leg auto-passes only when no doc obligation was declared — and that branch-awareness itself was a bug fixed in this window). Each pipeline takes a *typed commitment* at activation — dev-spec, doc-spec, test-spec — with acceptance criteria paired to behaviors; the engine refuses to lock a spec where they mismatch.

**The honest engineering story of this window:** driving the v1.84.1 close-out was the **first time the engine's close ceremony was exercised end-to-end** — and it surfaced six real, pre-existing bugs in the pipeline runtime (a step-declaration path that silently dropped verification commands; a re-trigger gate that refused forever because it checked existence instead of status; a context-key bug that silently degenerated a test step to a no-op pass; a stale-spec resolution bug; a recompute crash; two step definitions pointing at nonexistent scripts). All six were found by checking **raw run events against claims** — not labels — and all six are fixed, with a regression-test hardening track open. The structural cure for the class is ADR-052: locking a dev-spec now atomically registers its pipeline activation, so the audit chain dev-spec ↔ activation ↔ build ↔ release is complete *by construction* rather than by discipline. §10 gives the full release-engineering picture this belongs to.

**Diagram:** [`svg/07-pipelines-and-loops.svg`](svg/07-pipelines-and-loops.svg)

---

## 9. Callable surfaces — five classes, one discovery layer

Five classes of callable capability, all first-class governed substrate (v1 listed three; two were missing):

- **Tools** (61 Python scripts; 56 registered): single-file CLIs for structured operations — event emission and query, vault rebuild, activation writes, soft-delete recycle, validation, release builds, and now mount/publish (federation) and disposition. Tools are the write-time enforcement locus *and* the tier-invariance seam: the same operation contract is a CLI at L1 and can become a function or authenticated service at higher tiers without redesign.
- **Skills** (25 shipped + 2 Studio-local): governed *procedures* an agent executes in its own context — "open the file, read its Steps, follow them." No CLI to run; the skill is the knowledge. (Schema type: the revived `how-to`.) The naming deliberately mirrors the surrounding harness ecosystem.
- **Session agents** (16 classes): ephemeral, narrow specialists an executive commissions for a bounded job — adversarial review, memory curation, board rendering, cold-boot testing — through a governed commissioning protocol with a written record. They run in separate context, which is precisely what makes them useful as *independent* verifiers.
- **Actions** (10): single-gesture operations.
- **Loops** (6): recurring governed autonomy with brakes (§8).

**The discovery layer** *(shipped in v1.70 itself but absent from v1 of this review)*: a **Toolbelt** — the ~15 core tools every agent loads at boot, mirroring the harness-native pattern — plus three capability catalogs (tools / skills / session agents) regenerated from the index. The doctrinal rule binding all five classes: **if a capability exists, use it.** Agents do not improvise operations the harness already knows how to do correctly.

A deliberate boundary unchanged from v1: tools are the **paved road, never a mandatory gate**. Hand-editing a file always works and is caught downstream by the validation gate and the groomers. This preserves the cold-boot floor (§11).

---

## 10. Release engineering — the authorization stack, and what broke *(new section)*

v1 described the pipelines; it did not describe how a release is *authorized*. That stack was built, stress-broken, and hardened in this window — and the honest arc is exactly what a room of engineers should inspect.

**The stack as designed:**
1. **Pipeline Activation Key (v1.71):** the release builder and the public upload refuse to run without a runtime-minted fingerprint proving a real pipeline run occurred. Public ship additionally requires human signoff.
2. **Stranger-Walk Gate (v1.74):** an always-asked cold-boot walk at cut — a fresh agent (conducted by Po, the release-test conductor role created for this) walks the release artifact as a stranger; a FAIL verdict blocks the upload. Its first live run blocked its own release until the PASS landed.
3. **Ship-gate refusals:** the validator must be clean in strict mode before a build; the status flip to `shipped` requires the sign-off fields.

**What broke, and what was done:**
- **The key fingerprint was shape-derived** — six consecutive releases shipped with *byte-identical* fingerprints before an adversarial review caught it. Fixed at v1.80 with per-run salting; v1.80 carries the first genuinely unique key.
- **The human-signoff event was agent-writable.** Worse: the round-2 re-verification proved the "fix" insufficient — a forged signoff event *still authorizes*, because agent generations are not registered principals. The principal ruled to **accept this as a documented L1 ceiling** (the covenant rests on the human actually running the build — true today, with a single operator signing every cut), keep the field check as defense-in-depth, and route the real fix to a designed-but-unbuilt **Signing Primitive**. This review reports that plainly: *cryptographic authorization does not exist at L1 today.* (§14.3.)
- **Off-pipeline drift was systemic.** The coupling investigation found nine locked dev-specs with no pipeline activation, and two releases signed with no activation ever opened. The response was three-fold: retroactively *feed the pipeline* with honest paperwork (never fabricated keys — the key tool was deliberately run and its REFUSAL recorded on each retro entry), disclose per-release ("Known-imperfect" sections, null keys with notes), and cure the class structurally with **ADR-052 lock-time coupling**.
- **The attested-close doctrine.** When driving the engine's close ceremony surfaced the six runtime bugs (§8), the principal ruled to ship proven code by **documented attestation** rather than hold a verified release hostage to broken bookkeeping machinery: `close_method: attested-manual`, a signed decision naming *every bypassed gate*, and the verification evidence (69/69 tests, independently re-run by a second agent before the cut). Three release masters closed this way (v1.77, v1.78, v1.84.1). An escape hatch that is visible, signed, and enumerated is governance working — the alternative every large organization knows is the invisible workaround.

**Cadence and scale:** 14 OS releases in the 26 days since v1.70 (v1.71 → v1.84.1; v1.83 is deliberately reserved for a pending capstone). 98 Tropo-OS release records spanning 96 distinct versions since the first public release in April 2026, plus six non-OS product releases through the same pipeline. Not every release produces a standalone customer artifact — several landed as in-Studio substrate, each disclosing exactly that.

---

## 11. Governance and enforcement — the four loci

Governance is three-tier: OS-level invariants, Studio-level configuration, and per-folder contracts. On top sits the enforcement architecture made binding by ADR-044:

1. **Write-time — tools** that enforce and normalize on write (messaging guards, the activation writer's hard gates, the mint chokepoint — ADR-050 routed all identifier generation through one collision-checked minter with typed kinds).
2. **Validate-time — the gate:** **94 check functions (~90 executed per run)** at every rebuild and as build pre-flight (v1: ~58; 115 at the 2026-08-26 re-verification). Newer checks read schemas from the capsules at runtime; a material minority hardcode schema literals in-code, policed by a Layer-3 declaration/implementation coherence meta-validator (v1.58+, ERROR-ratcheted v1.60) — *the original "never hardcode" here was an unmeasured absolute, corrected 2026-08-26.* Checks land at WARN and ratchet to ERROR once the substrate is clean. The ratchet pattern matured in this window: **named grandfather exemptions** with constant cutoffs (historical records exempt *by name*, going-forward violations fail) — honesty about the past without weakening the future. A red gate blocks the ship.
3. **Continuous — grooming agents:** the first production groomer (the Gardener, v1.82) stamps decay signals flag-only, adversarially proven unable to write source files. (The fuller groomer fleet remains undeployed — §14.)
4. **Review — humans and agents** under the signed Self-Healing primitive: every read carries a structural-defect pass; trivial defects are fixed in place, substantive ones filed as tracked work. Nothing is flagged-and-forgotten.

**Judgment calls are part of the enforcement design.** New rules meet old data; the system's pattern for that collision is now explicit: when the just-shipped federation grounding check fired on eight *closed, archived* tasks from April–May, the principal-approved resolution was a **terminal-state carve-out** — history degrades to WARN, live records stay ERROR, and an anti-rot regression test locks the boundary so the carve-out can never silently widen. Gates bind live work; history is a lint.

**Two invariants a reviewer should test us against, unchanged:**
- **The cold-boot invariant (sacrosanct):** the validation gate may WARN on a hand-written file but must never hard-reject it. A stranger with a zip of the Studio can always boot it.
- **Locks are law.** Locked files are immutable without explicit principal approval; lock-breaks are logged governance events.

**Diagram:** [`svg/08-enforcement-verification.svg`](svg/08-enforcement-verification.svg)

---

## 12. Verification and quality — "done" means independently proven

The quality discipline, in one sentence: completion is a verified state, not a declared one.

- **Three-instrument verification** for load-bearing artifacts: the build itself, an independent review (peer or adversarial skeptic in a separate context), and a cold-boot stranger test. Each instrument catches what the others structurally cannot.
- **Two-sided verification convergence** *(matured in this window)*: on the v1.84.1 cut, the release author independently re-ran all 69 tests rather than transcribing the verifier's counts — and the verifier had independently read the raw run logs rather than trusting labels. Convergence of independent measurements is the strongest correctness signal the Studio recognizes.
- **Adversarial fleets for covenant-class work:** the sovereignty proof (§13) was attacked by a six-agent red team *twice at spec stage* and again post-build — the post-build fleet forced real private bytes across the wire on four of six angles of the first build. Five HIGH leak paths were fixed and pinned with regression plants; the re-verify fleet ran six-for-six fail-closed. Verification weight is matched to risk: heavyweight fleets for irreversible/covenant work, single independent checks for routine slices — a calibration the fleet's own results validated.
- **Structural completion gates:** a verification-class step reaches "verified" only on a real verification receipt; executor attestation alone cannot promote it. Verifier independence (approver ≠ executor) is enforced with fail-closed identity resolution.
- **The culture around it:** the crew's strongest standing rule — earned, not declared — is *verify every "done" against raw*, including one's own claims. This window's six pipeline-runtime bugs were all found exactly that way: raw `run.jsonl` events checked against the labels that summarized them. The system's history records its agents' verification failures candidly, because those incidents drove the structural gates above.

---

## 13. Federation — the segmented vault and the sovereignty covenant *(new section)*

Shipped v1.84.0 (foundation) + v1.84.1 (complete, 2026-07-10). This is the largest architectural addition since the review's v1, and it went from first signed decision to shipped-and-adversarially-proven in five days (graph-model gate signed 2026-07-05 → covenant shipped 2026-07-10) — through two co-signed architect "joint gates" with the principal ruling escalated forks.

**The model:**

- **A vault is a governed node.** A new `vault` manifest type declares a vault's membership, audience, remote, and publish policy; its `kind` (os / personal / team / knowledgebase) is immutable after activation. The studio↔vault boundary is *sibling, not containment* — a studio mounts vaults; it never absorbs them.
- **Segments derive; they are never authored.** Every record's segment (its visibility zone: `os`, `private`, future `team:<uid>`) is computed — from the enclosing vault manifest, or for the home studio from the `extraction_scope` field (public allowlist: a frozen code constant, deliberately not config; unmarked → private; comparison after full Unicode normalization). A hand-edited `segment:` value never governs — the derived model recomputes and overrides it on every rebuild. Default-deny falls out for free.
- **Grounding is per-vault (the D7 rule).** Every work item must trace membership to *its own vault's* anchor entity — so a shared item's ownership chain resolves identically for every team member, no matter whose studio computes it.
- **Cross-vault references obey a lattice.** An additional `member_of` edge across vaults is legal only *up-lattice* (toward an equal-or-wider audience). Down-lattice and incomparable edges are **illegal-but-present**: excluded from adjacency and authority for every viewer, surfaced as lint — never silently dropped, never silently walked.
- **Mounting is gated.** The mount tool validates the manifest, pins the mount to a resolved commit in a compose lockfile, requires executable-consent as a governed write, enforces vault-qualified capability names (the dependency-confusion defense — an unqualified name that would shadow a governance tool is refused; four HIGH bypasses including a full-width-Unicode homograph were caught and fixed at build time), and demands re-consent on contract narrowing. Same lockfile ⇒ same composition.
- **The composed index is incrementally correct.** Each mounted vault's index rows cache as a shard keyed by the lockfile's commit pin — no independent hashing; the mount pin *is* the dirty-check key. Staleness fails closed: a desynced shard is a "cannot-compose" validator finding, never a silently-partial index.

**The sovereignty covenant — "no private byte crosses the wire, in either direction."** The publish path is built on a git-plumbing truth: *a push carries a ref and its whole history, not a file list* — so naive filter-then-push leaks. The publisher instead builds a fresh commit tree of exactly the passing files (first publish is an orphan root; later publishes parent only on the prior public-only tip, so public history accumulates without ever anchoring to private history), pushes only that single ref, and re-validates the *committed tree* (walking every reachable commit, not just the tip) to close time-of-check/time-of-use. It enumerates the filesystem rather than git's tracked list, refuses symlinks/hardlinks/path escapes, submodules, LFS pointers, merge commits, and multi-worktree states. The pull side trusts nothing: it refuses shallow clones and re-runs every boundary check itself — the publisher's receipt is informational, not the guarantee. Enforcement is entirely client-side; a server hook is never trusted.

**The proof record:** red-teamed twice at spec stage (~10 HIGH leak paths folded before build; the red team also caught one *over*-restriction that would have destroyed shared team history). Post-build, a heavy six-attacker fleet — scanning the remote's bytes themselves — forced private bytes across on **4 of 6 angles** of the first build: manifest fail-open, ancestry poisoning via a buried non-tip commit, a TOCTOU window, a tautological segment gate. All five HIGH leaks (plus six MEDIUM) were fixed; the fresh fleet re-ran **6/6 fail-closed**. The proof suite is 23 tests including 8 regression plants pinning each closed leak; the full federation surface is 69 tests, independently re-run green by two agents on cut day.

**Honest ceilings, disclosed in the locked spec itself:** (1) revocation is forward-only — the covenant holds at push time; a file later reclassified private is already out; (2) on a platform-hosted remote (GitHub-class), *that a publish occurred* and ref metadata are platform-visible even though content and history hold; a self-hosted remote removes even that; (3) segment derivation is structural, not cryptographic — an attacker who can forge both content and a matching manifest defeats the second factor (tracked follow-up; the unconditional scope gate remains the load-bearing control). And the plainest one: **zero live mounts exist today.** The two-machine proof ran on a simulated two-machine harness (two clones + a bare remote); the first real two-box run is the named acceptance walk. The covenant is proven; production federation use has not begun.

**Diagram:** [`svg/09-federation-sovereignty.svg`](svg/09-federation-sovereignty.svg)

---

## 14. Security and assurance posture — the CISO view *(fully refreshed)*

### 14.1 What the architecture gives you

- **Data locality and a small, enumerable attack surface.** The system is files on disk; no server processes, no open ports, no database. The v1 claim of "no network calls" is retired — the truth is better stated as **enumerable network touchpoints** (see 14.2); everything else operates fully offline, and the substrate degrades gracefully offline (update discovery silent-skips; federation is opt-in).
- **Total auditability.** Every artifact is human-readable text. Every coordination act is one line in an append-only log with actor UIDs and timestamps; every playbook run writes its own milestone log; every agent generation has a lineage record. An auditor with `grep` can reconstruct who did what, when, under what authority.
- **Whole-system versioning and recovery.** The operating state — work, memory, identity, messages — restores as a folder. Derived surfaces rebuild from source files with one command.
- **Destruction resistance.** Soft-delete-only doctrine, archived-not-deleted lifecycle, supersession chains with resolvable forward-pointers (validator-enforced), reference-safe disposition, per-fold memory snapshots — incident-earned, signed doctrine.
- **A public OS with a private-by-default Studio.** The OS ships from a positive-filter extraction: only `extraction_scope: ship` content (495 of 4,239 records; 15% public-eligible including `external`, 85% stays home) ever leaves. The publish boundary is code-constant allowlist + derived segments + the federation gate stack (§13).

### 14.2 Network-touching components (enumerated)

1. **Release upload** — the build tool uploads release artifacts to a hosted bucket (credentialed via environment; ship-time only).
2. **Update discovery** — first boot of the day fetches a static update manifest; offline-safe silent-skip; applying an update is human-gated with a dry-run diff and a sealed dual-hash receipt (the Update Covenant, ADR-049: user substrate is inviolable under OS update — proven by a seeded-studio walk that honestly failed round 1 and passed round 2 after same-day fixes).
3. **Federation transport** — git push/pull to explicitly configured remotes, under the §13 covenant.
4. **Optional metering gateway** — a local proxy on the operator's own API traffic for real cost accounting of autonomous loops. Optional, local, and off by default.
5. **The AI harness itself** — as in v1, agents act with the privileges of the harness they run in; harness selection and configuration are part of the security boundary and should be reviewed jointly.
6. **Substrate-initiated model-API calls** *(added at the 2026-08-26 re-verification — this list was incomplete)*: `lib/llm.py` instantiates a first-party Anthropic client against `ANTHROPIC_API_KEY`, consumed by orient()'s paid read tier, the Distiller tools, the Gardener body-judge, and the event query tools. Plus a credential-gated GitHub REST surface for the D5 protected-repo proof (`lib/d5_proof_repo.py`, test-consumed only).

### 14.3 Honest limitations (current, tracked — each lives as a governed work item)

1. **No cryptographic integrity on logs or authorization yet.** Logs are append-only by convention and tooling, not cryptography. Sharper than v1 stated it: the human-signoff check on public releases was adversarially *proven forgeable* by an executing agent even after its first fix, and the principal accepted that as a **documented L1 ceiling** — today's guarantee rests on the operational reality that a single registered human runs and signs every cut. The designed fix (a signing primitive for un-forgeable human authentication) exists as a design brief and is **not built**; a stated intention to build it before federation was not met — federation shipped first, with zero live mounts as the mitigating fact. This is the top of the security backlog. *(Story moved twice since — corrected 2026-08-26: an Ed25519 agent-provenance signing primitive WAS built and Mike-accepted 2026-07-30, then deliberately retired by ADR-066 on 2026-08-03 ("the agent lifecycle mints no cryptographic key material"). Separately, Ed25519 group-authority signing with out-of-band human-fingerprint trust IS live at L1 on the mount/update surfaces. The substance of this ceiling stands: release human-signoff remains non-cryptographic by accepted ruling, with a hardened independent-registered-signer check as defense-in-depth.)*
2. **Access control is conventions plus harness permissions, not OS-level ACLs.** Anyone with filesystem access can edit any file. Tropo's layer is integrity *detection* and audit (validator, groomers, forward-pointers, event trail), not access *prevention*. Disk/repo permissions and the harness perimeter are the access-control story.
3. **The validator is not green today — and the review says so.** Current full run: 87 passed, 3 failed (two lifecycle-rollup leaks; one schema violation on two of the new maintenance-loop entries — the self-maintenance registry itself carrying a schema defect is a finding the system caught about itself). v1's "holding green as a ship precondition" was true at strict-gate ship time but is not a standing steady-state guarantee; red findings are tracked work, and the strict gate still blocks builds.
4. **Release-gate history is disclosed, not hidden.** Six releases shipped with byte-identical authorization fingerprints before the defect was caught (fixed v1.80); several releases shipped off-pipeline and were retroactively papered with explicit disclosure; three release masters closed by documented attestation when the close ceremony was found defective (§10). The pattern to evaluate is not "gates never failed" — it is that every failure is named in the record, was fixed or ceiling-documented, and produced a structural cure (ADR-052, salting, regression tracks).
5. **Enforcement coverage is intentionally gradual** (ADR-044). High-value types enforce hard; the long tail is looser by design; WARN→ERROR ratchets advance with named grandfathers. The dial settings are inspectable at any time.
6. **Two v1-roadmap items remain undelivered:** the groomer *fleet* (one flag-only groomer is live) and event-log cryptographic integrity (see item 1). Scored honestly in §15.

None of this is news to the system; all of it is tracked inside it — which is itself the point: the security backlog lives in the same governed, auditable substrate as everything else.

---

## 15. Maturity, scale, and trajectory

**Operating evidence as of 2026-07-10:**

- **4,239** governed index records (whole-Studio index) · **3,740** files in the core store · **18,168** directed typed edges across **4,122** connected nodes · **64** capsule type definitions · **57** decision records (53 numbered ADRs, through ADR-052) · **6,103** coordination events (measured this morning; the log grows continuously).
- **98** Tropo-OS release records across **96 distinct versions** (v1.1.0, April 2026 → v1.84.1), **plus 6 non-OS product releases** through the same pipeline. **14 OS releases in the 26 days** since the v1.70.0 baseline.
- Callable surfaces: **61** tool scripts (56 registered) · **25+2** skills · **16** session-agent classes · **10** actions · **6** loops · a 15-tool boot Toolbelt + three generated catalogs.
- Validator: **94 check functions**, ~90 executed per run; current state 87 pass / 3 fail (disclosed in §14.3).
- Crew: a human principal + **8 active agents** (Chief of Staff V64, Chief Architect A129, engineering T28, strategist G88, lore-keeper O30 — mid-retirement today, concierge P1, hybrid CoS C11, and the in-Studio concierge host), one retired, one pending commission. Boot cost: typical boots **1.4–4.5 minutes measured** against an 8-minute budget gate (outliers flagged by the gate).

**Scoring v1's stated trajectory, honestly:** memory v3.0 cascade — **done**. WARN→ERROR ratchets — **major progress** (three ratchet releases). Write-time work-management tool family — **partial** (disposition shipped; the fuller family pending). Groomer fleet — **not deployed** (one flag-only groomer live). Event-log cryptographic integrity — **not landed** (design-stage; §14.3 item 1).

**Trajectory from here:** the "v2 floor" program (One Home, clean self-update, warnings-to-zero, true stranger-walk) closed at v1.78. The "v3 program" is underway: self-maintenance (v1.79), customer-hands honesty and the security fixes (v1.80), the import/export boundary (v1.81), continuous knowledge health (v1.82), federation (v1.84.x — shipped). Reserved and pending: **v1.83 "One Voice,"** the deliberately-last capstone that narrates the finished system, gated on a month-long stranger acceptance walk. Beyond L1: the L2 cockpit track now runs *inside* the federation program (parallel L1/L2 tracks; team vaults decided as git-native private repos with a merge-blocking governance validator), and the product structure is three rings — the open-source OS, a marketplace of published capabilities, and the ecosystem.

**Diagram:** [`svg/11-evolution-timeline.svg`](svg/11-evolution-timeline.svg)

---

## 16. Summary for the reviewer

Tropo L1 is a small number of strong ideas, composed:

1. Plain files as the universal substrate — auditable, portable, minimal-infrastructure, and now an open-source public artifact with a private-by-default Studio boundary.
2. Typed contracts (capsules) with gradual, tighten-only enforcement — structure without breaking the language floor.
3. Durable agent identity with hard lineage gates, governed succession, bounded memory, and budgeted boots — AI staffing without continuity loss.
4. One append-only event log with a three-state delivery contract — views are projections, never independent truths.
5. Verification as a structural property — independent receipts, verifier independence, adversarial fleets scaled to risk, and an honest escape hatch (documented attestation) for when the machinery itself is what's broken.
6. Federation under a proven sovereignty covenant — segmented vaults, derived visibility, and a publish path that was made to fail closed by people paid to make it leak.

The system's strongest credential is reflexive: it is built, governed, versioned, and verified *by itself*, under real workload, with its failures recorded in its own substrate and converted into its own gates. Its second-strongest credential is this document's candor: the broken fingerprints, the forgeable signoff, the never-exercised close ceremony, the red validator — all of it is in the record, dated, owned, and either fixed or ceiling-documented. The diagrams in `svg/` and every claim in this document trace to governed files a reviewer is welcome to read directly.

---

## Part II — The v3 delta (v1.84.1 → v1.86.0+, measured 2026-08-12)

*Five weeks and two shipped releases after v2. Part II is organized around the four architectural
events of the window: the lifecycle rebuild, the pipeline constitution, the knowledge engine's
first production cycle, and federation leaving the lab. Sections here are measured live at
2026-08-12; each names any §1–16 claim it supersedes.*

---

## 17. Lifecycle v2 — born / continue / retire *(supersedes part of §4.1)*

**§4.1 described two hard gates that HALT activation (ADR-016, ADR-028). That posture is
superseded.** After three agent generations were blocked at birth in one week by their own
paperwork, the principal ruled: *"I never want to see my agents telling me they are failing to
boot."* The lifecycle was rebuilt (2026-08-06) around a single principle — **existence cannot be
refused; findings are recorded, never blocking**:

- **`born` is one command.** The lineage file (`agents/<slug>/lineage.jsonl`, append-only, one
  line per transition) issues the generation — highest in the file plus one. There is
  deliberately no flag to claim a generation, so there is no claim to verify and no mismatch to
  halt on. ADR-016/028 remain graph invariants — checked at the mint, recorded as `provisional:`
  findings on the birth line when violated, surfaced in the agent's startup signal. The agent is
  born either way.
- **`retire` is one command** — places the living-transfer letter (create-only; it will not
  overwrite a predecessor's), appends the closing lineage line.
- **`continue` is the new middle verb** (Compact-Continue, designed 2026-08-11 live during an
  actual mid-build context compaction; Phase-1 dev-spec locked same day). A compacted agent is a
  stale reader of its own session: the protocol re-anchors from substrate in one command — `who`
  (never `born`; the phantom-generation hazard), fetch, drain both event axes, list unanswered
  obligations, show the agent its own recent commits — and emits the compaction broadcast
  itself, welded, never left to a compacted agent's memory. Per-harness trigger adapters (Claude,
  Cursor, Codex, Gemini) carry one identical trigger line, copy-equality validated. On 1M-token
  sleeves with survivable compaction, retirement becomes a chosen ceremony at natural stopping
  points rather than a forced response to a full context window.
- **Boot sources were consolidated** (Single-Source S4): the boot procedure now derives from two
  fingerprint-gated sources; the crew brief renders from lineage as generation/status truth.

## 18. The pipeline constitution — dev and release split *(extends §8 and §10)*

The principal designed it in two sentences at a whiteboard; twelve hours later it was a locked
spec; six days later stages 1–5 of 9 were built and independently accepted. **The dev-pipeline
runs Specify → Build → Test, one run per locked dev-spec, closing at one tested SHA with
mutation evidence — and produces no release artifacts. Releases are a separate release-pipeline,
ignited only by a locked release-plan and closed only by verified publication. There is no
"park" state:** "build complete" is an ordinary done dev-spec; the release-plan fans in done
specs by explicit list.

What a reviewer should inspect is the review record: stage 4 (the release-plan lock — the
ignition key) survived **seven adversarial NO-GO rounds, every one legitimate**, killing a
forgeable-green class (snapshots now GOVERN runs as executable content, recovery recomputes the
digest it checks, closure binds to receipt-level tested-SHA). Then the reviewer **reopened his
own stage-5 ACCEPT** when the builder showed him the standalone package tool still bypassed the
new gate — *"That is my review error, not yours... thank you for checking the location I named
instead of letting my ACCEPT overrule the world"* — and re-skipped the acceptance selector
rather than leave a false green. The machinery and the culture now enforce each other.

Alongside the split, the **velocity build** removed the release-day tax: the validator went
**244.9s → 40.4s** and the full vault rebuild **278.3s → 69.1s** (one shared frontmatter parse
replaced 108K redundant YAML parses); the debt ratchet became **itemized by class** (a ceiling
that names what grew instead of counting it — currently 84 accepted class-errors, paid down from
110 at the Gardener cycle); and a stale-constant detector separates pinned values from copied
ones. And a governing doctrine landed, principal-ruled after the studio once "ground to a halt
under checks that added very little value": **warn-safe is the default — a refusal earns its
existence by naming its irreversible harm in one sentence, or it is a warning that proceeds and
records.** Fail-closed is earned at publication, deletion, spend, identity, and false-success
prevention; everything else warns.

## 19. The Gardener — the vault's first production pruning cycle *(extends §3.2 and §11's
"flag-only groomer")*

v2 reported one flag-only groomer, adversarially proven unable to write. Since then the full
**Gardener Pruning** system shipped and ran its first complete human-reviewed cycle
(2026-08-11):

- **The judge is a caged sub-agent.** A Cursor cloud sub-agent runs a pinned prompt whose
  SHA-256, plus the policy version, IS the judge's identity — edit one character and stamping
  authority lapses until re-qualification. It runs one pass under a **$0 enforceable spend
  ceiling** (no provider API path exists in its envelope), proposal-only: it writes no governed
  content. It earned authority by scoring **18/18 against the principal's hand-marked fixture
  cases** under blind conditions; an earlier prompt that scored worse was rejected and its
  failing scorecard preserved as the reason the current wording exists.
- **Stamps are evidence-bound.** A verdict (finished / superseded / abandoned) binds the exact
  quoted span from the body, its byte offsets, the body's hash at judgment time, the judge's
  identity, and the approving actor. Edit a stamped body and the stamp is visibly stale and
  re-queues. The content gate means steady-state cycles re-judge only what changed.
- **The human is the lever.** Judging is scheduled (weekly, fleet-ops); stamping is a separate
  human-reviewed gesture — unattended auto-stamp is prohibited by standing rule. Cycle 2's
  sitting: 281 proposals, 14 walked individually by the principal (every OS-segment item, every
  "abandoned" verdict), the rest executive-reviewed span by span under a ruled policy —
  **279 stamped, 2 held honestly on prospective-tense evidence, 75 entries archived with
  receipts; the live working set is 3,297 active records.** Zero wrong verdicts found in ~280
  spans read; every failure in the cycle was a tooling seam, and each is now a filed, tracked
  finding (a render-state-dependent content hash; two tools blind outside the main store; a
  lock tool that corrupted its own record on an apostrophe while printing success).
- **The honest gap, and the v2 design head:** the loop is wired for launching, not landing —
  the judge ran on schedule and its 281 proposals sat unnoticed for three days behind a status
  field written mid-run. Gardener v2 (design brief in the graph, superseding-in-design the v1
  spec) closes the consumption loop: a pending-disposition marker + one boot-signal line, the
  disposition steps named in the loop's own procedure, and confidence triage to shrink the
  human sitting further.

## 20. orient() and the Distiller — the knowledge engine's other half *(design stage; stated
plainly)*

The Gardener removes the dead. **The Distiller — orient() — ranks and serves the living.**

> **⚠ CORRECTED at the 2026-08-26 re-verification: this section's "designed and contracted, not
> built" was FALSE at its own measurement date.** Stage C was built 2026-07-30 —
> `lib/orient_stage_c.py` (talos-t37, "brief, then judge, then guard — 80/80 against the
> contract-first suite"), with `lib/span_guard.py` and the metered model edge landing the same
> week, two weeks before this section was written. It is wired live behind `tropo-orient.py
> --read` (person-chosen, spends money, off by default). §27 later described `--read` as landed
> but never retracted this claim. The review was underselling the system.

Stages A and B
(deterministic retrieval + ranking substrate: task-circle expansion, decay-aware ranking, viewer
projection) are shipped code. Stage C — task-shaped synthesis with extractive spans and verbatim
provenance, brief-then-judge, two latency tiers — was contracted as a locked build contract with five
principal-locked design rules (body-rot verdicts belong to the Gardener once per body version;
synthesis is task-shaped only; extractive span-grain with provenance; brief-then-judge; two
tiers) and an attested model-edge contract (models, pricing, consent, fences — all receipts).
The principal ruled crown-first sequencing: orient() precedes the cockpit's later phases. The
per-agent compact-continue "refresh" (§17) is deliberately specified as a hand-written
prefiguration of orient()-for-self, so the two arcs converge rather than compete.

## 21. Federation left the lab *(supersedes §13's "zero live mounts" and §14.3's framing)*

v2's plainest ceiling — *"zero live mounts exist today; production federation use has not
begun"* — is retired:

> **⚠ PRECISION, added at the 2026-08-26 re-verification — this supersession overreaches as
> written.** What left the lab: the release/update path (received by a real customer studio,
> receipts on record) and two governed **folder** mounts (one corporate OneDrive share, one
> iCloud/Obsidian folder; no SharePoint mount exists). **The §13 sovereignty-covenant team-vault
> mount path itself still has zero production mounts** — no compose.lock, no vault manifests —
> exactly as at v1.84.1. The covenant is proven (its 69-test suite re-ran green at the
> re-verification), and it remains unexercised in production.

- **v1.86.0 was the first release in Tropo's history to ship through the published path AND be
  received** (2026-08-09): a real customer Studio (a second operator's machine) updated through
  the covenant with clean receipts — and its own concierge agent's REFUSAL caught a real
  packaging defect the development studio had missed. Eleven machine refusals fired across the
  ship; **zero were false.** The field is part of the gauntlet now.
- **The first upstream field contribution landed the same week:** the customer studio's own
  operations agent implemented the mount-identity fix (governed mount entries under a shipped
  `external-context` root; the import walker parents mirrors to the mount), taking that studio's
  validator from 123 failures to 0 — and the shape flowed back upstream as law ("identity before
  rendering") into a locked v1.87 dev-spec. Federation works in both directions on first
  contact.
- **Real-file mounts are first-class work now:** the development studio itself runs live
  SharePoint/OneDrive folder mounts (the operator's actual business documents), and the locked
  Stream A spec gives every mount governed identity at mount time and makes mounted sources
  reachable from the human navigation tree — click a mounted `.docx` in the nav, it opens in
  Word.

## 22. Metrics refresh and the honest state (2026-08-12, measured live)

- **5,188 governed records** across the current + archive union (current: 3,300 rows — 3,297
  active · 3 standing; archive: 1,897) — the first review edition where the archive split (§3.2,
  "Layer-1 build pending" in v2) is measured as built and load-bearing.
- **~9,930 coordination events**; the three-state delivery contract now includes drain-side
  integrity (acknowledge only after successful rendering — a drain that consumed messages while
  rendering nothing was found and fixed).
- **Releases:** v1.85.0, v1.86.0 shipped since v2 (98 → 100 release records); v1.87 is in
  flight as five streams under a release-plan at specify, with the bootstrap clause: it ships
  through whichever pipeline is PROVEN at cut time.
- **Crew:** principal + Chief Architect A148 · engineering T40 · Chief of Staff V72 ·
  lore-keeper O35 · strategist G107 (this author). Two mid-window architect handoffs (A146→A147→
  A148) landed with clean seams during a live build; one engineering context compaction was
  survived in place — the event that produced §17's `continue`.
- **Validator posture, stated the new way:** the honest instrument is the itemized debt ratchet
  — **84 accepted class-errors, paid DOWN from 110 this week, no class above baseline**; raising
  any class requires a recorded decision. (The raw "failed" count v2 reported is retired as a
  headline number; it counted unclassed checks and made trend invisible.)
- **Trajectory:** land the split (stages 6–9, then the two sandboxed reference runs that are the
  ship proof); run v1.87's five streams to gate; build Compact-Continue Phase 1; Gardener v2
  quick-hits; then the Distiller. v1.83 "One Voice" remains deliberately reserved.

---

---

## Part III — The v4 delta (v1.86.0+ → v1.92 in flight, measured 2026-08-24)

*Twelve days and three shipped releases after v3 (v1.87.0 → v1.91.0), measured live on the single
day the v1.92 cycle scoped, locked, and mostly built four dev-specs through a two-pass adversarial
gauntlet. Part III is organized around the window's architectural events: the release machinery's
first real runs and what they broke, the one-day conform cycle, the lifecycle receiving its
executor, the release-profile seam, and the knowledge engine's first production blindness test.
Each section names any earlier claim it supersedes.*



## §23. Releases v1.87–v1.91 — the ship path under load *(supersedes §18's "the velocity build removed the release-day tax")*

The window shipped four public releases: v1.87 (published 2026-08-15T01:36Z, receipt `ca4e6410`), v1.88 (published 2026-08-16T12:18Z — *corrected 2026-08-26: this section originally said 08-15, the CHANGELOG row's date; the publish event says 08-16, one reader/writer instance inside the document that documents the family*), v1.90 (fired 2026-08-22T23:44Z), and v1.91 (2026-08-24 09:36Z). **v1.89.0 never shipped publicly** — its plan closed `cancelled` and its six locked specs were subsumed into v1.90 (`cf0da4bc`). §18 reported the release-day tax removed (validator 244.9s → 40.4s). That claim is superseded: the tax was never compute. It was adjudication, and two releases measured it.

**v1.90 cost nine builds, four cold walks, two days, and roughly forty founder prompts** (retro `62deeec1`). Its thesis: nearly every refusal was one defect — **the release event vocabulary was built read-first**. Seven measured instances: constants declared, readers implemented, refusal messages naming an event as the cure, tests asserting it — and no writer anywhere (`package_superseded`, `candidate_invalidated`), or two readers of one journal disagreeing. The ship also came one paste from public with three of the maintainer's own release scripts inside the box, hardcoded to his machine, while the box's own test-report certified the absence of exactly that leak. The absolute-path validator that catches it existed, with zero call sites; it is now harness check 6b, fail-closed, mutation-proven.

**v1.91 cured the named disease and exposed the real one** (retro `25c70440`). The cure is real: `tropo.release.scope_locked` fired on the bus in production for the first time; all 14 declared release events now have exactly one writer, enforced at validate; the receipt shapes unified; **23 of 23 non-deferred acceptance criteria verified green on their own locked commands, each by an agent that did not build it**. And the release still cost the founder a full night: **~20 refusals, every one correct, not one knowable before the run started**, plus three release-path tools repaired mid-flight — one broken by this same cycle's own format change at 09:35 that morning, unnoticed for fifteen hours. The retro's verdict stands as this section's: *"we built a verification system and called it a build system."* v1.91 fixed what the release says about itself, not what shipping costs; the refusal count is v1.92's scoped problem.

**The artifact got measurably better while the path got no cheaper.** Same shipped validator, bare stranger studio, one cycle apart: **v1.90 = 319 failures, v1.91 = 30**.

**And v1.91 shipped the first honest image manifest in Tropo's history.** An independent harness agent — dispatched because a gate refused to accept the driving agent's word — found F1 (`33d5bca1`): the shipped manifest described bytes the build then rewrote, in every release ever published — 33 of 1,054 entries stale, and 204 of the box's 1,259 files absent entirely, from the file that is the delete-set's only input at apply time. The founder chose the rebuild; it bought a manifest with 0 mismatched, 0 unlisted, independently confirmed. The fix then uncovered F7 (`5f75c7f3`): a complete manifest puts customer state — event log, memory surfaces, registries — into the apply-time replace set, because `is_studio_state()` classifies 4 of 1,258 entries. The broken manifest had been an accidental shield. F7 shipped knowingly: filed and accepted in writing at the step-9 signature rather than patched unilaterally at 05:00, with Vela's byte-verified path classification already in the record and the cure — in `package_state_exclusions`, requiring a rebuild — riding to v1.92.

## §24. The v1.92 cycle — one defect family, scoped and mostly built in a day *(qualifies §12's "done means independently proven"; extends §18's warn-safe doctrine)*

On 2026-08-24 the principal locked v1.92's shape at three goals, verbatim on the cycle board: a first-principles rebuild of the release build process, one build objective — "a fully formed dev-pipeline ready to start work" in a stranger studio — and the deferred list dispositioned once. *"We do that, then we rebuild and publish. Every step."* The governed plan is `vault/files/088e21aa.md`; the board (`boards/v1.92-cycle-board.md`) had been opened a day earlier precisely because v1.92 "had five claimants in five places and no address."

What followed compressed a release's design phase into one day. Four dev-specs were authored, each run through a two-pass review with an independent skeptic before lock. The two heaviest gauntlets are on record verbatim: `8eeebdab` (retirement driver — 10 findings, 3 blockers, including a spec that would have shipped a 71-spec red wall and a second writer of the retirement notice) and `1963123e` (Stream 1 — 10 findings, 2 blockers plus a scope catch that added the missing runner AC). Both verdicts read FIX-THEN-LOCK; load-bearing blockers were re-verified first-hand by the release owner before relay. All four specs locked 2026-08-24, and by that evening two were built and non-author verified (the retirement driver, 25 tests verbatim plus a live known-negative; the deriver identity fix, proven by a live zero-churn double-run), Stream 2 stood at five of six criteria verified with only the First-Use Walk pending, and Stream 1 — split mid-day between two builders — had its hardest ACs green.

The cycle's thesis held under adversarial pressure: every defect found this window is one family — a fact declared in one place and written, or read, differently in another. The completion verifier is the family's deepest instance (`814210f0`): `tropo-verify-release-live.py`, the leg that exists so a release is not self-attested, bound five facts and **every one read a key or path no producer writes**. It has never returned complete for any release; v1.90 and v1.91 both shipped with their second opinion structurally unable to speak, behind a test suite that was green because its fixtures were hand-built in the reader's shape. This qualifies §12: "done means independently proven" was true of dev-specs and never yet of releases. The repair moved the live v1.91 run from three facts absent to one; the last, the scorecard, exposed that `REAL_FIRE` had no caller anywhere — the instrument built in v1.89 to measure what shipping costs the principal had never been switched on. It is now wired at the fire, with "nobody counted" (`None`) finally distinct from "none occurred" (`[]`); the ruling makes the scorecard fact forward-only, run `7ee91e0b` exempt by name.

The rebuild's other two boundaries: preflight gates are now data with **computed phases** — six governance gates registered (lock-static went from 1 to 7), each placed by the registry from its declared inputs so a gate cannot choose its own boundary, and an empty boundary prints an explicit 0-gates line instead of the blank three boundaries hid behind for months. And §18's warn-safe doctrine gained the third class its binary always forced dishonesty into: every build-path refusal now carries exactly one disposition — priced refusal, warning-that-proceeds-and-records, or operational-misuse error, the last exempt from harm-pricing and forbidden from masquerading as a release verdict. The build path had cited the warn-safe ruling zero times; the lock, built after it, cited it three.

## §25. The close learns to read the world — the retirement driver, the substrate check, and the debt baseline *(qualifies §12; extends §17)*

§12 stated the discipline as fact: "completion is a verified state, not a declared one." Two instruments landed 2026-08-24 (spec `b1e78abb`, v1.92) because at the spec lifecycle it was aspiration — a record could say a thing happened with no instrument reading the world to check.

**The retirement driver** (`vault/tools/tropo-retire-driver.py`, 492 lines, built by talos-t50) walks the eight bold-labeled steps of the retirement playbook's §Required Practice and verifies each *on the world* — a file on disk, an event on the bus; absence of evidence is reported open, never as pass. Two token-shaped steps get known-negative-aware observers: matching a generation number anywhere in a 1,700-line append-only Captain's Log is not an observer, so the driver demands a real entry heading. Step 8's broadcast is read back from the bus, never emitted — the close's `announce()` is the single writer, and a driver that also emitted would rebuild the two-writers defect inside the spec written to cure it. Its only refusal is playbook drift: if the section does not parse to exactly the eight labels its registry knows, in order, it refuses and names the delta — because the observer registry *is* a second copy of the list, made safe by breaking loudly. It never gates the close; §17's "retire is one command" stands unchanged. The motivating record: A153 missed two steps, A155 one, A154 missed §8 recovering A153's retirement from a summary — three competent agents following written procedure.

**The committed-substrate check** exists because nothing ever compared a done spec's `committed_substrate` to the filesystem (grep of `vault/tools/` for the field paired with any existence check: zero hits). The known-positive: spec `29506520`, `status: done`, `target_release: 1.91.0` — with four of its twelve declared targets absent, all four v1.91 driver test files, exactly the AC1/AC2/AC5/AC7 carried to v1.92. Nobody lied; no instrument compared field to world. The new validator check errors only at `done` and only at `capsule_version >= 1.5`, because the corpus is not clean: measured 2026-08-24, **71 of 120** done specs carry at least one unresolvable target, and 19 carry lawful planned identifiers (named WARN, never ERROR).

Those 71 land in `.tropo/committed-substrate-debt-baseline.json` (captured 2026-08-24T21:44:39Z, Metis G112 ruling): **22 frozen signatures**, shrink-only, each keyed on the *full* unresolved-target set — so even a partial cure changes the signature and re-ERRORs until consciously re-frozen. `29506520` is deliberately excluded so the known-positive keeps firing until its owner annotates it.

**One finding qualifies §12 directly.** Recommending the D5 close verifier, A156 found the D5 build commits (`3fe37908e`, `ed74f990e`, on `lib/publish_service.py`) authored "Cursor Agent" with no agent generation in the body: builder identity is not mechanically establishable, so verifier independence can be assumed but never proven from the commit record. §12's "verifier independence… enforced with fail-closed identity resolution" holds at the pipeline step and stops at the git log. D5 was worked around by assigning Vela (demonstrably uninvolved); whether an agent-generation commit trailer becomes a validator-checked convention is parked on the v1.92 board, deliberately not standalone.

## §26. The release-profile seam — the machine no longer knows what it ships *(extends §18; supersedes §1's and §10's "same pipeline" framing)*

v3 reported six non-OS product releases "shipped through the same pipeline." True at the record level, and misleading at the machine level: the tools beneath that pipeline referenced it zero times, and the product-genericity lived entirely in the human operator running scripts by hand. Stream 1 of v1.92 (dev-spec `5b608d28`, locked 2026-08-24) closes that gap with AC5/AC6, built by talos-t51 on `worktree-v192-stream1-ac4` (head `002147832`) after metis-g112 split the stream — argus-a156 keeps the shared-tool ACs — on one condition: the binding contract lands first, as one commit (`42f9acd10`), so two builders work against one contract rather than two guesses.

The design is Mike-shaped. The spec's stated measure is "his evening — prompts he types, real decisions among them," and the contract in `vault/tools/lib/release_bindings.py` encodes exactly that split: every pipeline leaf binds one EXECUTOR of a declared KIND. `KIND_TOOL` is deterministic — the machine does it; `KIND_PLAYBOOK` is judgment — a governed procedure with a **named executor class** does it. The one hard rule: a playbook binding with no named executor is refused at load — "a procedure with no executor is an event with no emitter." Draft v1 demanded exactly one *tool* per leaf; measurement proved it unsatisfiable: **five of the twelve declared leaves are human- or agent-executed by design** (the cold-boot walk, external-test, notify-owners, the two trigger legs), and two leaves legitimately share one tool.

Above the contract sits `lib/release_profile.py` (260 lines): a profile is a governed vault entry of new type `release-profile` (capsule `654f3a90`, status draft — only Mike locks a type), with three closed generic slots — build-the-artifact, verify-the-artifact, publish-the-artifact — each naming a `release_gates` phase as its gate contract and its steps in the bindings' own vocabulary, so a profile and a tool cannot disagree about what "deterministic" means. Exactly one profile ships: `vault/files/6bf18510.md` — product `tropo`, pipeline `634913c2`, twelve steps, 7 tool / 5 playbook, the split measured independently by both builders.

The proof is `test_release_profile_seam_v192.py`: 12 tests, green in the worktree (Ran 12, OK, 2.4s). Statically, no product literal survives in the machine modules — no `tropo` string, no version-shaped literal, no hardcoded path to the shipped profile — replacing draft v1's vacuous "zero diff between two runs of one tree" check. Dynamically, the shipped profile and a fixture profile declaring a *different* step set both load through the one loader and drive the runner to terminal verdicts **that differ** — shipped halts at its first judgment slot, fixture completes — proving the runner reads the profile, not a built-in list. A judgment slot with no executor is refused; the mutation control adds the executor back and it loads.

The runner itself, `tropo-release-run.py` (137 lines), is retro Action 2 finally shipped as a mechanism rather than a label — and the seam's first consumer, so it lands with a caller instead of zero. It walks the profile's slots cold; a judgment step halts the walk naming step UID and executor class, a terminal verdict, not a failure. Candidly: it deliberately does not yet resolve the exact runnable command or invoke tools — both wait on AC2's `PIPELINE_BINDINGS`, undeclared in the tools as of this measurement, and AC6's cold-runner test is not yet in the tree. The extension point is `for_step()` at the halt site, not a redesign.

## §27. orient() in the field — Stages A/B at boot and scoping, and the measured blindness *(extends §20; supersedes its status-only framing of the shipped half)*

v3's §20 stated orient()'s Stages A and B — deterministic retrieval and ranking — as "shipped code" and left it there. The delta is that the shipped half became a working instrument with a boot-doctrine slot, an incident record, and a doctrine extracted from the incident.

**In use, and widened.** The Phase 1 build (`4883fa94`, landed 2026-08-12, the day v3 Part II was measured) changed what a free run returns: candidates are drawn wide before ranking (`--draw-budget`, default max(8·k, 256)), the one-hop neighbourhood is rendered as an exhaustive, never-truncated roster, and deterministic keyword recall (`--terms`) rides alongside the graph. The metered read layer (`--read` — "SPENDS MONEY — a few cents," off by default, no policy can switch it on) stays a person-chosen flag; everything wired into doctrine runs on the free path. And it is wired: ORIENT-BEFORE-YOU-SCOPE entered the strategist's Tier-3 boot surface on 2026-08-24 (Mike-surfaced) — before scoping a cycle or ruling on a governed domain, run orient() on the governing UID and read the whole neighbourhood, not just the ranked picture.

**The blindness, measured.** That rule exists because the crew scoped v1.92 blind to its own release-pipeline. At Mike's challenge, metis-g112 measured it (2026-08-24): `tropo-orient.py --task 088e21aa` — the v1.92 release-plan — returned zero hits for release-pipeline `634913c2` in the ranked 8 **and** in the complete 408-node one-hop neighbourhood. The cause sits verified in the edges table: both release-plans are `member_of` the *dev*-pipeline (`cd1fcd25`), and no edge anywhere bound a release-plan to the pipeline it ignites — the ignition relationship ("a locked release-plan is the only release ignition") lived in prose and runtime code only. The instrument worked; the map was missing the road — the same two-readers / map-territory defect class Stream 1 is prosecuting in the build system, here measured in the graph itself. The cure came in two grains the same day: one interim edge (`088e21aa` now `refs: 634913c2`, so orient can see it) and a capsule question filed on the v1.92 board — should the release-plan capsule mint the plan→pipeline edge by construction, backfilled to historical plans?

**The doctrine.** The Tier-3 text draws the general rule: orient() answers from the graph, so when a relationship lives only in prose, **an honest empty answer is a feed-gap finding to file — never a reason to skip the tool**. The precedent is a week older: the Librarian's first live exchange (2026-08-15) answered one question cited-and-verbatim, said "not in my context" to another, and that honest refusal exposed the task-own-body feed gap — fixed the same hour, with a causal test.

**Stage C and the Librarian, unchanged in kind.** Stage C's synthesis contract — the five principal-locked design rules of §20 — stands as contracted; no delta this window touches the paid engine. The Librarian arc shipped its deliberately deterministic L1 slice (`d317f532`, locked and done 2026-08-15): `--for-librarian` emits ranked evidence plus budgeted governed bodies as one feedable artifact, no model calls, write-never, citations-always. Whether L2 is ever built is gated on L1's measurement log — a decision deferred on purpose, not a gap.

## §28. Metrics refresh and the honest state (2026-08-24, measured live) *(supersedes §22's figures)*

- **Scale.** 5,585 governed records across the current + archive union (current index: 3,453 rows; archive: 2,132) — up from 5,188 at v3, twelve days ago. `vault/files/` holds 4,969 files. The current index carries 131 dev-specs (25 more archived), 245 memory entries, 227 projects, 65 decisions. Coordination events: 11,721 in the derived event index; the raw logs hold 6,678 lines on the legacy single log plus 5,048 across 266 per-conversation streams. That is roughly +1,800 events since v3's ~9,930.

- **Releases.** Four shipped since v3: v1.87.0 (08-14), v1.88.0 (08-15), v1.90.0 (08-21), v1.91.0 (08-23) — 118 release records now (16 current + 102 archived), up from 100. This SUPERSEDES §22's trajectory line ("run v1.87's five streams to gate"): v1.87 shipped two days after v3 was written. The gap in the numbering is real and disclosed, not a typo — the v1.89 cycle's one-prompt saga build had its outward act stubbed, so the CHANGELOG jumps 1.88 → 1.90 and no v1.89 release record exists; v1.90's own entry names it and wires the fix.

- **Crew.** Principal + Chief Architect **A156** · engineering **T51** · Chief of Staff **V73** · strategist **G112**. The measurement day alone saw 131 commits (79 by non-Metis identities; seven generation-identities active) — and a **mid-cycle Talos turnover with zero work lost**: T50 finished b1e78abb AC1–AC5 and Stream 2's AC4, retired (`0f360efbe`, `6f228767c`); T51 was born (`d52d189a4`), verified the transfer, built cee5190f and the committed-substrate debt baseline the same afternoon, and took Stream 1's AC5+AC6 under G112's split ruling (`a559ddd25`). The honest wrinkle, measured on the record: the retirement *driver* T50 built this very cycle did **not** run at his own close (`aa7d9470d`) — the manual walk-equivalent is carried by the next real retirement.

- **Debt, the new instrument.** The committed-substrate debt baseline stands at **22 frozen entries, 0 ERROR-class**, set-keyed signatures, shrink-only by ruling (verified live, `b51e5c308`). This is a second enumerable-debt instrument alongside §22's validator ratchet, built to the same enum-debt pattern; the two are not directly comparable and this review does not pretend they are.

- **Open, honestly.** Three items, all live at press time. (1) **The First-Use Walk has not yet run** — it is cycle gate 3 and the bar's judging instrument (studio memory `74e9676b`), and until it passes, "a stranger studio ships unaided" remains a design claim. (2) **No v1.92 candidate box has been built through the rebuilt machinery** — Stream 1's remainder is the cycle's last build in flight, and the walk requires the box, not this checkout (1a478c48 AC5). (3) **The deferred board is longer than at cycle start**: `boards/v1.92-cycle-board.md` grew 41 lines on the day, as five new findings were filed (F7 customer-state boundary, the dev-pipeline stale-body defect, the orient() feed-gap edge, an ADR-050-bypass second writer, a builder-identity gap) plus six pre-existing test failures flagged on Stream 1's branch — faster than dispositions cleared rows. A cycle whose stated goal 3 is "the deferred list, dispositioned once" ending its first day with a longer board is not failure; it is the honest measure of how much the machinery now surfaces that used to stay invisible.

---

## Part IV — The v4.1 delta (v1.92.0 shipped, measured 2026-08-26)

*Two days after Part III. The cycle it watched in flight landed: v1.92.0 is public. Part IV was
written the evening of the ship, from the run journals, the release saga journal, the publish
receipt, the First-Use Walk record, and both release retrospectives — not from memory. It
supersedes §28's three open items and corrects one Part III claim that the ship proved wrong.*

## §29. v1.92.0 shipped — and the endgame exercised the gates for real *(supersedes §28's open items 1 and 2)*

**The ship facts:** v1.92.0 published 2026-08-26T20:12:48Z; the **publisher's liveness check**
passed at 20:13:41Z (receipt `3fe4be3f…` — remote shas match, release object live, artifacts
byte-identical on both public endpoints). Stated precisely because "verify live" names two
different checks (A159's refinement on `4240df1d`): the publisher's liveness observation is a
clock written by the publisher and it genuinely passed; the **completion verifier** — §24's
repaired five-fact instrument — separately returned INCOMPLETE (`scorecard-pending`, §30), and
the recorded state distinguishes the two nowhere. Public at
github.com/tropo-ai/tropo/releases/tag/v1.92.0.

**§28's open item 1 is closed the right way: the First-Use Walk RAN and PASSED** (record
`00ffa4af`, pre-agreed rules `879e7ec0`) — the first stranger in Studio history to complete the
dev loop unaided from the shipped package. PASS with findings: a P1 mint-provenance defect at the
flagship path's first command, filed forward with its in-package workaround named rather than
cured, because the invariant held — **the walked package is the fired package.** The bar the
principal set (`74e9676b`) was met on its own instrument.

**§28's open item 2 closed under load, which is better than closing clean:** the rebuilt
machinery built the candidate — and the first candidate **FAILED the independent harness gate and
was invalidated pre-fire** (a release-profile that needed a lock and a missing `extraction_scope`
field). The recovery exercised the expensive path end-to-end: the run was abandoned and re-locked
by principal ruling (`42261546` → `cd68bea8`; plan `088e21aa` cancelled → `46079e11`,
hand-authored ~280 lines), attestations re-issued, rebuilt, re-dispatched, refrozen. Nothing real
was lost and the abandoned chain stayed on record. Twelve steps ran or carried recorded judgment —
**zero silent skips**, the contract the cycle set for itself.

**The cost side is measured, not narrated** — the full accounting is the v1.92 retrospective
(`9cfdf8ae`, Vela V74, first-hand) and the measurement verdict (`f1fa74e8`, Metis G113): five
prompts genuinely requiring the principal's judgment (v1.91: ~40 across the arc), zero silent
skips (from 3), ~10 refusals hand-tallied and sorted 4 real / 4 instrument-defect / 2
missing-writer (v1.91: ~20 / 0 / 0), 5 builds (from 6) — and, on the other side of the ledger, 4
release-path tools repaired mid-flight (up from 3), ~20 executor CLI invocations, and **6
hand-authored events standing in for declared writers that have no caller.** The refusal
population changed character: fewer, earlier, no longer uniformly true — and every false one
lives in release machinery, not in the artifact.

## §30. The scorecard that was not written *(corrects §24's "it is now wired at the fire"; qualifies §12 a second time)*

§24 reported the one-prompt scorecard "now wired at the fire." The ship proved that claim wrong in
the way this document's whole §4-family predicts: **the fire observed its scorecard checkpoint at
20:14:14Z and no scorecard exists** — the saga fact carries no `scorecard_sha`, no
`one-prompt-real-fire-scorecard.json` exists anywhere in the Studio, and the release saga is
still incomplete at `completion_verification` (idempotency key literally `completion:None`)
because the completion verifier correctly refuses to observe without a valid card.

The mechanism is the family's twentieth measured instance (canonical record `4240df1d`, Argus
A159, found from the boot nag the same evening): the pipeline binds the fire step to
`tropo-publish-release.py:cmd_fire`, while the only scorecard-producer injection lives in
`tropo-release.py:cmd_fire` — one injection site, one consumption site, and the declared binding
connects neither. The layering itself is correct (the publisher genuinely lacks the measurement
inputs); **the binding points at the wrong door, so no release fired through the bound path can
ever produce its own cost measurement or complete its saga.** The cure (rebind to the
orchestrator) is filed, deliberately not applied pre-walk, with the verification obligation
written into the record: prove it by running both paths, plant the negative.

The qualification of §12, stated plainly: v1.92 made the release's *correctness* independently
proven for the first time (verify-live receipt, harness gate, walk) — and the instrument built to
measure what a release *costs the principal* has still never produced a card for a real fire. The
hand tally in `f1fa74e8` is the only scorecard v1.92 has. Related, same family: the Studio-side
publish marker (`.tropo/publish-pending.json`) still reads `not-staged` for a release that is
public, so every booting agent reads a boot line that is false in its plain meaning — two state
files, one fact, one writer (also on `4240df1d`, held for the same reason).

## §31. What the window settles for v1.93 *(extends §24; the trajectory line)*

Both retrospectives converge from independent vantage points: v1.91's verdict was *"we built a
verification system and called it a build system"*; v1.92's is that every gate that fired was
correct and the cost lived in **gaps between gates** — declared primitives with no caller, two
readers of one fact, checks that cannot tell "already succeeded" from "trying to succeed twice."
The response direction is settled and principal-licensed: **v1.93 is a subtraction cycle.** The
release becomes four separable jobs — build from a commit / verify the package / decide to
publish / record — composed around the 369-line packaging core that already does job one
correctly and reproducibly (it built the walk's package twice, first try); the 4,249-line
builder that interleaves governance into all four jobs is replaced by composition, not
refactored. Deliverables are net-negative line counts (precedent on record: −189, A158) and
uncoached stranger verdicts — the two currencies the principal now accepts after cycles of
assurances. The per-piece review gate: *"what does the principal lose without this?"* — default
is cut. The retrospective's seven-item action list (`9cfdf8ae` §Actions) and the walk-scoped
opening board are the queue; the full §1–22 re-verification of this document is the scoping
baseline and remains open.

---

## §32. How Tropo builds software — the process canon, summarized *(companion document; moved to its canonical home 2026-08-26)*

The full statement is **["How We Build Software"](../how-we-build-software.html)** — a rendered,
diagrammed walk of the entire path from an idea in a note to a published versioned release,
authored by Metis G112 at the principal's direction on 2026-08-24 and moved from its render home
into `docs/` alongside this review on 2026-08-26. It is the process companion to
this document's structural story, and the summary belongs here because §8, §10, §18, and §23–26
are all elaborations of what it states in two sentences.

**The constitution:** the dev-pipeline runs Specify → Build → Test, one run per locked dev-spec,
closing at one tested commit with mutation evidence — and produces no release artifacts. Releases
are a separate release-pipeline, ignited only by a locked release-plan that fans in done specs by
explicit list, and closed only by verified publication.

**The human's share is three gestures per shipped feature** — lock the spec, lock the plan, fire —
and everything between them is agent work inside machine-verified process. This is the
bounded-verification thesis (§1, Thesis 5) applied to the shop that builds Tropo: when a release
costs the founder ~40 prompts (v1.91), that is a *measured defect*, not a mood — and v1.92's
answer was five judgment gestures (§29).

**The path, stage by stage:** a `note` (cheap, ungoverned pace) → a `design-brief` (the problem
and intent, where whiteboard thinking happens) → a `dev-spec` (the contract: acceptance criteria
each carrying a locked verify command, committed-substrate list, mutation clauses; adversarially
reviewed before lock; the principal's lock IS the ignition — ADR-052 writes the immutable snapshot
and creates the run in one gesture) → build (evidence per criterion into the run journal) →
verification by a **non-author running each locked command verbatim**, with closure journaled as a
side effect of terminal verification, never declared. Vocabulary the canon fixes on the record: a
dev-pipeline run is a **delivery**; the word **build** belongs to the release side (the box
build). Many deliveries fan into one plan, one frozen package sha, one fire.

**Why the canon can be trusted — and what moved since:** its §6 names four places where the
declared design and running reality diverged at authoring, each filed with a cure. By this
re-verification, three of the four cures shipped in v1.92: the release tool layer conformed to
the declared shape (Stream 1), the dev-pipeline definition body updated (Stream 2), and the
plan→pipeline ignition edge verified present on both the cancelled and successor plans (§27).
The step-machine reconciliation continues on the v1.93 board. The canon is a dated snapshot by
its own rule — "regenerate when the process moves" — and the subtraction cycle will move it.

---

## Part V — The full re-verification (2026-08-26)

*Eight agents in parallel, one per section group, adversarial refute-posture, read-only,
every number command-cited. Run at the principal's direction the night v1.92.0 shipped, as the
capstone before v1.93 scoping. Full findings: the governed verification report `6e9f6549`; this
section carries the verdict and the corrected headline numbers.*

**The verdict.** No fabrications anywhere in §1–28. Five claims were WRONG at their own
measurement dates — all five the same family, unmeasured absolutes or status lines around a true
core: §2's "every primitive declares its hub" (tools: 31%), §11's "never hardcode" (both patterns
coexist, policed by a Layer-3 meta-validator), §20's "Stage C not built" (built two weeks before
the sentence was written — the review undersold the system), §23's v1.88 ship date (CHANGELOG
frame vs publish event), §24's "scorecard wired at the fire" (disproven by the ship; §30). Each is
corrected in place. The document's *mechanism* claims verified against live code essentially
without exception — the salted activation key, the recycle guard, null-honest metering, the
Gardener's pinned-prompt judge (its qualification hash byte-identical today), the pipeline's
self-attestation refusals, the sovereignty covenant's 69/69 suite — many exercised by the v1.92
endgame itself. Part III, never before fact-checked, was the most precise part at its own date:
line counts, commit counts, and gauntlet tallies land exactly.

**The corrected headline numbers (2026-08-26):** governed records **5,647** (3,508 current +
2,139 archive) · vault/files **5,024** · edges **24,344** across 5,444 nodes · capsules **69** ·
tools **109** (81 cataloged) · skills **29** · loops **9** · toolbelt **19** · validator checks
**115** · decisions **65**, ADRs through **ADR-066** · releases **119** records (110 OS across
105 versions + 9 non-OS, v1.92.0 newest) · events **11,915** (6,678 frozen legacy + 5,237 across
272 streams) · validator posture **85 pass / 152 fail vs a 154-item shrink-only ceiling with one
gating class** (the "3 failed" era's instrument is retired; the v1.92.0 shipped box measured 52)
· crew at re-verification: **three active generations** (A159 · V74 · G113) + the principal, with
Talos reborn in a cloud VM (T52) during the pass and the Orpheus seat vacant since 08-19.

**New findings the review did not carry, handed to the v1.93 evidence set:** a sixth network
touchpoint missing from §14.2's enumeration (first-party model-API calls, now added); edge-rel
vocabulary twins the One-Vocabulary ratchet does not cover (`member-of`/`member_of`,
`composes-with`/`composes_with`); mint-chokepoint erosion (5 raw-mint WARN bypasses, one
uuid4-shaped minter invisible to the static check, and the fail-loud floor catching two
hand-authored evidence records the night they were written); an orphaned over-bound memory
surface (Orpheus, 49.9KB, 52% over ERROR bound, no successor to fold it); and a third
qualification of §12 (a sampled canonical dev close: independent, but empty
`acceptance_evidence`, ungated mode, dirty tree).

**Method note the studio should keep:** the fleet was killed once mid-flight by the machine
sleeping — the same failure class as the wake loops — and all eight agents resumed from their
checkpoints without re-running completed work. And one finding was the verifier's own: the
re-verification refuted its author's boot-time "fingerprint drift" finding (a nav-block hashing
artifact), which is the refute-posture working on the people who commissioned it.

---

## Appendix A — Diagram index

| File | View |
|---|---|
| `svg/01-system-map.svg` | Studio anatomy: three layers, nine subsystems, the bootstrap-floor kernel |
| `svg/02-capsule-type-system.svg` | Type inheritance, the capsule contract, contract→instance→enforcement |
| `svg/03-vault-graph.svg` | Flat store, One-Home directories, graph semantics, derived surfaces |
| `svg/04-agent-lifecycle.svg` | Three-tier boot, six gated groups, hard gates, budgeted boot, succession |
| `svg/05-memory-architecture.svg` | Memory v3.0: single surface, append-only episodic log, bounded folds |
| `svg/06-event-system.svg` | The event log: guarded emission, three-state delivery, projections |
| `svg/07-pipelines-and-loops.svg` | Pipelines vs. runs, playbooks, loops with brakes, the coupled dev/doc/test DAG |
| `svg/08-enforcement-verification.svg` | Four enforcement loci, ratchets with grandfathers, done-means-proven |
| `svg/09-federation-sovereignty.svg` | Segmented vaults, the mount gate, the publish covenant, the proof record |
| `svg/10-write-path.svg` | Life of a governed artifact: write → derive → validate → groom → render |
| `svg/11-evolution-timeline.svg` | v1.0 → v1.84.1: releases, programs, and crew generations on one axis |
| `svg/12-two-pipeline-dag.svg` | The pipeline constitution: two pipelines, three human gestures (§18, §32) |
| `svg/13-lifecycle-born-continue-retire.svg` | Lifecycle v2: born, continue, retire (§17) |
| `svg/14-event-ledger-v2.svg` | The event ledger v2: frozen epoch plus live streams, one union (§6, beside the supersession warning) |
| `svg/15-gardener-loop.svg` | The Gardener: the vault's first production pruning cycle (§19) |

*The eleven v2 views (01–11) remain accurate for §1–16 as measured at v1.84.1. The four v4 views (12–15) are the diagrams v3's edition of this appendix named as candidates; they shipped with v4 and were indexed only in this folder's `00-README.md` until 2026-09-05, when the Studio Map render began reading this table for its captions (Orpheus O38, delta on the canonical document at Metis's grant in `f0151b4347af`; captions from the README and each figure's own title).*

## Appendix B — Glossary (minimal)

- **Studio** — one installation of Tropo: a folder.
- **Vault** — the governed content store inside a Studio; also (federation) a governed, mountable node with a manifest and an audience.
- **Capsule** — a type definition: the schema contract for a class of governed file.
- **Agent / generation / sleeve** — an agent is the durable composite (soul + memory + vault + crew); a generation is one session-lifetime of it; the sleeve is the underlying model running it.
- **Playbook / pipeline / loop** — a governed procedure in language / a declarative DAG workflow with typed runs / a recurring governed autonomy with brakes.
- **Skill** — a governed procedure an agent executes in its own context; the knowledge is the capability.
- **ADR** — architecture decision record (typed `decision`); binding once accepted.
- **extraction_scope / segment** — the authored public-eligibility field / the *derived* visibility zone computed from it (or from a vault manifest); segments are never hand-authored.
- **Mount / publish / compose lockfile** — attaching a foreign vault under the mount gate / pushing public-only content to a team remote under the covenant / the commit-pinned record that makes composition reproducible.
- **Attested close** — a documented, principal-signed manual close naming every bypassed gate; the visible escape hatch for defective ceremony machinery.
- **Principal** — the accountable human (here: the founder); the source of approvals at governance gates.

---

*Prepared inside the system it describes. §1–16 researched by a multi-agent fleet, authored by Argus A129, adversarially fact-checked 2026-07-10. Part II (§17–22) authored by Metis G107, 2026-08-12. Part III (§23–28) drafted 2026-08-24 by a six-agent fleet, assembled by Metis G112. Part IV (§29–32) authored and verified 2026-08-26 by Metis G113. Part V: the full eight-agent adversarial re-verification of §1–28, 2026-08-26, Metis G113 — report at vault/files/6e9f6549.md. Every figure traceable to files, events, and receipts in the Studio. the Studio.*
