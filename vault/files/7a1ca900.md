---
uid: 7a1ca900
lifecycle: standing
type: document
title: "Tropo Capabilities"
description: "The capability matrix — what Tropo does, organized by 7 subsystems (6 v1.7-anchored + Documentation NEW v1.8). L1 shipped + L2/L3 futures (Tropo-built + ecosystem). Anchor document for first-contact readers."
stage: specify
state: active
status: locked
owner: argus
priority: p0
created: 2026-04-20
modified: 2026-04-21
created_by: argus-a29
modified_by: argus-a31
locked_by: argus-a31
locked_at: 2026-04-21
supersedes: c41a5bf0
member_of: [aae9a37b, d1aa6e47, 17e70a00]
tags: [capability-matrix, subsystems, documentation, anchor, architecture, verification-first, v1.3, locked, p0]
file_ext: md
schema_version: 2
extraction_scope: ship
refs:
 - aae9a37b # tropo-subsystems root
 - c41a5bf0 # Matrix v0.1 first-cut (superseded by this v1.0)
 - a7c4e5b2 # ADR-035 Declared-Presence — Governance anchor
 - e6c3f410 # ADR-032 Three-Layer Boot — Agents anchor
 - 74fd9b61 # Board Reconciliation v0.3 — Rendering anchor
---

# Tropo Capabilities

*What Tropo does, organized by subsystem. If you just landed, this is the document that answers **"what is this and what can it do?"** in one scroll. Every cell links to a hub you can navigate to for detail. Every cell is labeled **[committed]** or **[speculative]** so you can tell what's shipping from what's being explored.*

*v1.0 — LOCKED 2026-04-21. Supersedes first-cut v0.1 [c41a5bf0](vault/files/c41a5bf0.md).*

---

## How to read this document

**Seven subsystems** (6 v1.7-anchored + Documentation promoted v1.8 mid-cycle per Mike-A46 pair-design 2026-05-05). Each has a table with four columns:

- **Market Capability.** How a buyer, partner, or practitioner would describe what Tropo does here. Outside-in framing.
- **Tropo L1.** What's shipped today in the markdown-only zip. No database, no cloud, any LLM, any platform.
- **L2 Futures.** Pro tier — local brain (reasoning kernel on Apple Silicon) + Tropo-hosted services. Includes both **Tropo-built** additions and **Ecosystem** tech we compose with.
- **L3 Futures.** Scale / Enterprise tier — framework bridges, compliance integrations, federation, marketplace. Same Tropo-built + Ecosystem split.

**Commitment labels.** Every L2/L3 cell is labeled:

- `[committed]` — the capability exists today at L1 OR has a named roadmap artifact (brief, ADR, design-spec, release plan) driving it. A reader can trace it to a vault entry.
- `[speculative]` — plausible fit we're watching. Not a commitment; calibration of the possibility space. May become committed when a roadmap artifact is authored.

**Discipline.** A cell earns `[committed]` ONLY when there's a traceable roadmap artifact or an already-shipped L1 capability behind it. Aspirational features without a named brief stay `[speculative]` until the brief lands. The labels matter because vision sells the speculative and buyers pay for the committed — being honest about which is which is the credibility signal. v1.0 locked with most L2/L3 cells at `[speculative]` reflecting v1.3 state; future releases will promote cells to `[committed]` as roadmap artifacts land.

**Each subsystem also carries a verification footer** — one short paragraph naming how that subsystem specifically contributes to Tropo's verification-first identity. The thesis Tropo locks at v1.3: *as AI drives execution costs toward zero, the binding constraint on economic growth shifts from intelligence to human verification bandwidth.* Every subsystem earns its place by contributing verification surface.

---

## 1. Tropo Library

*The governed graph document store — storage, addressing, schema, discovery, federation.*

| Market Capability | Tropo L1 | L2 Futures | L3 Futures |
|---|---|---|---|
| **Portable team knowledge graph** — own it, grep it, audit it, ship it in a zip. | Schemaless markdown document store with stable UID identity (ADR-029), type-safe capsules, bidirectional graph index (1,257+ edges), schema-floor invariants (core.capsule). No database required; any filesystem, any LLM, any platform. | **Tropo `[speculative]`:** Semantic search + auto-categorization across the full ledger via the local brain.<br>**Ecosystem `[speculative]`:** Ollama + Llama 3.x / Mistral for local embeddings; Chroma / Qdrant for vector stores at Pro tier — local-first so sensitive knowledge never leaves the machine. | **Tropo `[speculative]`:** Hosted team instances; marketplace for published capsule extensions *(Cross-vault federation covered separately in row 3 below; all federation primitives are speculative at v1.3).* <br>**Ecosystem `[speculative]`:** AGENTS.md ecosystem compatibility (emerging standard); LangChain / LlamaIndex bridges for existing RAG pipelines; Git-native collaboration — the vault IS a repo (`[committed]` — already true today at L1). |
| **Typed artifact discovery in sub-second** — find any agent, skill, tool, or decision without reading every file. | [registry.jsonl](.tropo-studio/registries/registry.jsonl) runtime catalog (31+ records, growing), [cascade indexes](vault/00-cascade-roots.jsonl) (8 subtree dumps, 4–350 entries each), type-sharded indexes (tasks / projects / decisions / etc.). One grep returns canonical answer. | **Tropo `[speculative]`:** Continuous registry watch — brain auto-indexes as files change; NL query layer over the registry.<br>**Ecosystem `[speculative]`:** MCP (Model Context Protocol) as one transport in the tool.capsule — Tropo registers above MCP, wraps any MCP server as a governed tool. | **Tropo `[speculative]`:** Federated registry across vaults; marketplace index of published agents / skills / playbooks.<br>**Ecosystem `[speculative]`:** A2A (Agent-to-Agent) protocol compatibility once stable; OpenAPI spec export for hosted integrations; Weaviate or Pinecone for enterprise-scale semantic search across federated vaults. |
| **Cross-vault federation without central authority** — your team's vault stays yours; federation is opt-in, UID-addressed, and cryptographically verifiable. | UID-stable addressing survives renames and moves (ADR-029); every governed file is a node in the graph; cross-vault references today are prose-linked. No central registry; no forced sync; federation primitives waiting on L2. | **Tropo `[speculative]`:** Selective subtree-sharing between vaults (opt-in, UID-keyed); federated cascade queries across partnered vaults.<br>**Ecosystem `[speculative]`:** Nostr / ATProto-style identity for vault authorship; IPFS / Pinata for content-addressable vault snapshots at Pro tier. | **Tropo `[speculative]`:** Marketplace-mediated inter-vault trade — verified playbooks, skills, agents move between governed vaults with audit trail.<br>**Ecosystem `[speculative]`:** Sigstore for cryptographic signing of federated artifacts; DIDs / verifiable credentials for cross-vault agent identity. |

**Verification footer — Library.** Verification starts with addressability: you can't audit what you can't locate. The Library gives every governed artifact a stable UID that survives renames, a queryable index, and a cascade that lets a reviewer traverse a decision's full provenance in seconds. No claim in any other Tropo subsystem holds up if the Library can't produce the receipt on demand. This subsystem is the substrate verification runs on.

---

## 2. Tropo Work

*Typed work primitives — tasks, projects, decisions, specs, collections. Work semantics applied to the Library.*

| Market Capability | Tropo L1 | L2 Futures | L3 Futures |
|---|---|---|---|
| **Human–AI work management without a SaaS** — typed tasks, projects, and decisions that humans and agents both read and write. | 13+ typed primitive capsules (task, project, decision, design-spec, design-brief, note, collection, research, concept, arch-spec, build, release, project-plan). Owner/verifier separation on every task. Project graph composes via `member_of:`. Parameterized constructor actions (create-task, create-project, create-decision, etc.). | **Tropo `[speculative]`:** AI-assisted work creation — brain suggests owners, verifiers, dependencies from the cascade; auto-drafts tasks from meeting notes / Slack threads.<br>**Ecosystem `[speculative]`:** Whisper for voice capture; Granola / Otter for meeting transcription feeding the create-task pipeline; local embedding similarity for deduplication. | **Tropo `[speculative]`:** Hosted teams dashboard; verified professional Playbooks as productized workflows; cross-team portfolio rollups.<br>**Ecosystem `[speculative]`:** Jira / Linear / GitHub Issues import + sync bridges; Slack / MS Teams notification channels; SOC 2 audit-trail export (see [Tropo × Vanta/Drata integration brief (c01c0003)](vault/files/c01c0003.md) for the roadmap); RBAC via enterprise SSO (Okta / Entra). |
| **Governed decision records with verifiable history** — every ADR, spec, and supersession is queryable and auditable. | 35+ ADRs indexed in [00-index-decisions.jsonl](vault/00-index-decisions.jsonl), bidirectional supersede chains, immutable once accepted (decision.capsule v2.0), required "Alternatives Considered" bodies. Full audit of who-decided-what-when with UID stability across renames. | **Tropo `[speculative]`:** Brain surfaces conflicting ADRs, flags drift between ADR and practice, auto-drafts "Alternatives Considered" from research memos.<br>**Ecosystem `[speculative]`:** tree-sitter-based code analysis to verify ADR claims against actual repo state (closes the spec-vs-fleet gap). | **Tropo `[speculative]`:** Compliance-pack generation (SOC 2 / ISO 27001 evidence pulled from ADR chain + test runs + cold-boot records).<br>**Ecosystem `[speculative]`:** Vanta / Drata integration — ADRs become controls; cold-boot records become audit artifacts. Tropo is the substrate, Vanta is the framework. |

**Verification footer — Work.** Every task has an owner and a verifier who are not the same person. Every decision carries its alternatives and its supersession chain. Every project composes from typed primitives whose shape is legible before you read the content. Work in Tropo isn't just tracked — it's shaped into artifacts a reviewer can verify without asking the author what it means. The types are the verification surface.

---

## 3. Tropo Agents

*Agent lifecycle, identity, memory, retirement — plus the session-agent catalog of specialists. Covers boot (formerly TBS) as a phase of agent lifecycle, not a sibling subsystem.*

| Market Capability | Tropo L1 | L2 Futures | L3 Futures |
|---|---|---|---|
| **Durable AI agents that remember who they are** — across sessions, generations, models, platforms. | Three-tier boot config ([ADR-032 e6c3f410](vault/files/e6c3f410.md)), soul letter (primacy + sandwich anchor), v2 three-tier memory (current + short-term + rolling history), generation log (ADR-028 self-contained identity), parallel-generation halt (ADR-016), clean retirement with living transfer. 6+ modern executives running this pattern. | **Tropo `[speculative]`:** Memory compaction via brain (richer rolling-window synthesis); automatic detection of context drift; brain-assisted briefing-package generation.<br>**Ecosystem `[speculative]`:** Claude Memory, ChatGPT Memory, and other vendor memory stores wrap cleanly as alternative Tier-3 sources; mem0 for long-term memory retrieval. | **Tropo `[speculative]`:** Marketplace of pre-built executive agent profiles (Chief of Staff, Strategist, Architect) as turnkey hires; cross-vault agent portability.<br>**Ecosystem `[speculative]`:** OAuth-based agent identity; A2A for inter-company agent interaction; Claude Code / Cursor / Cowork as harnesses the same agent-configurator targets — the loader is harness-agnostic. |
| **Multi-generational memory that accumulates** — what one agent-generation learned, the next inherits, compacted and current. | v2 memory protocol — single `memory-current.md` per agent (procedural / relationship / architectural sections); `short-term-memory.jsonl` for mid-session capture; rolling 3-generation history window compacted at every boot. Vault-level `MEMORY.md` indexes cross-agent patterns. Soul letter + lineage log preserve identity across model and platform changes. | **Tropo `[speculative]`:** Brain-powered memory compaction with semantic deduplication; automatic pin-promotion of patterns that recur across generations; cross-agent memory sync for shared contexts.<br>**Ecosystem `[speculative]`:** Vector-store-backed long-term memory (mem0 / Chroma) as opt-in Tier-4; LangGraph / LlamaIndex memory adapters (see [Tropo × LangGraph integration brief (c01c0004)](vault/files/c01c0004.md) for the LangGraph composition roadmap). | **Tropo `[speculative]`:** Team-level memory federation — knowledge that crosses agent boundaries and accumulates at the org level; verifiable memory provenance (which generation learned what).<br>**Ecosystem `[speculative]`:** Cryptographic memory attestation for regulated industries (who knew what, when). |
| **Specialist AI helpers on demand** — spawn a cold-boot verifier, a backlog analyst, an adversarial reviewer for a specific job; terminate when done. | 18+ [session-agent registry](.tropo-studio/registries/registry.jsonl) — cold-boot testers, research agents, backlog analysts, navigators, auditors, skeptics. Commissioning protocol governs spawn; typed inputs / outputs; activation-log preserves every invocation. | **Tropo `[speculative]`:** Brain-scheduled session agents (run cold-boot nightly on changed files, run backlog-analyst weekly on sprint close) — cron-like but reasoning-aware. *(ADR-037 "Triggers as Embedded Governance" is the proposed roadmap artifact; stays speculative until locked.)*<br>**Ecosystem `[speculative]`:** Apple Silicon MLX for local sub-agent compute; Temporal / Inngest as optional backends when teams want managed background execution. | **Tropo `[speculative]`:** Marketplace for professional session-agent Playbooks ("a verified compliance reviewer," "a verified RFP responder").<br>**Ecosystem `[speculative]`:** Anthropic sub-agent API; Google A2A; Microsoft Agent Framework — published sa.* agents deploy across any conformant harness. |

**Verification footer — Agents.** Every agent carries its own proof-of-identity: a soul letter that re-anchors at boot, a generation log the agent itself maintains, a memory file the next generation inherits. Every sub-agent commission is recorded; every retirement is a governed act. An auditor can reconstruct who did what across a multi-generation project from the agent files alone. Agents ship with their own audit trail baked in.

---

## 4. Tropo Playbooks

*Multi-group, multi-session process orchestration + the inline reflex layer (actions + skills). Playbooks carry Groups + milestone gates + run.jsonl; skills are short how-tos; actions are parameterized constructors.*

| Market Capability | Tropo L1 | L2 Futures | L3 Futures |
|---|---|---|---|
| **Your process as executable markdown** — write how your team does a thing once; any agent can run it without rewiring. | Playbook spec v2.2 with Groups + milestone gates + run.jsonl state anchor; playbook-run capsule governs resumable executions; 19+ shipped playbook definitions (lifecycle, onboarding, migration, operations); typed pipeline subtype (pipeline.capsule v1.0) declares stages + positions + typed-artifact-per-stage. Human-and-agent readers; multi-session resumability. | **Tropo `[speculative]`:** Brain drafts playbooks from observed behavior (watches a human do X three times, proposes a playbook). AI-assisted compensation logic for interrupted runs.<br>**Ecosystem `[speculative]`:** n8n, Temporal, and Langflow as alternate execution backends when teams want managed runtimes; Tropo playbooks export as deployable workflows. | **Tropo `[speculative]`:** Professional-playbook marketplace — a compliance officer publishes her SOC 2 review playbook; another team subscribes and runs it with their data. Revenue share on verified outcomes.<br>**Ecosystem `[speculative]`:** LangGraph for stateful multi-agent orchestration (see [Tropo × LangGraph integration brief (c01c0004)](vault/files/c01c0004.md) for the composition roadmap); CrewAI for agent team definitions that compose into Tropo Playbooks; workflow-standards conformance (BPMN-lite export). |
| **Reflex-level AI operations** — short how-tos that fire on recognizable triggers ("regenerate the board," "archive stale entries," "create a snapshot before shipping"). | 13+ how-to skills governed by how-to.capsule, 10+ kernel actions (constructors) — light-touch bundles invoked inline without a playbook run-folder. Each carries purpose / when / params; registry-discoverable. | **Tropo `[speculative]`:** Brain matches user intent to the right skill or action automatically — "I want to ship" fires build-release.playbook.md + snapshot-creation + release-entry.<br>**Ecosystem `[speculative]`:** OpenAI function-calling and Anthropic tool-use map skills / actions to vendor tool-use APIs transparently; Zapier / n8n as external trigger sources. | **Tropo `[speculative]`:** Marketplace of verified reflexes — "the Stripe team's customer-win playbook," "the YC startup-triage reflex pack."<br>**Ecosystem `[speculative]`:** MCP-wrapped reflexes deployable across any MCP-compatible harness; IFTTT / Zapier enterprise integrations for edge triggers. |

**Verification footer — Playbooks.** A playbook is a process written down in a form a stranger can execute and a reviewer can verify. Every run leaves a run folder with a `thread.md` (what the agent thought), a `run.jsonl` (what fired when), and verification receipts (what passed / what didn't). The playbook is the intent; the run is the evidence. Together they answer *"did the process actually happen, correctly, once?"* — which is what verification infrastructure has to prove.

---

## 5. Tropo Rendering

*Board-definitions + board-snapshots + prose query vocabulary + render engine + synthesizer. Shipped as v0.3 in v1.2 — evidence-driven promotion from "part of Work" to its own subsystem.*

| Market Capability | Tropo L1 | L2 Futures | L3 Futures |
|---|---|---|---|
| **Live status dashboards without a dashboard tool** — any project, any scope, any time, generated from governed sources against live data. | Board-definition templates + board-snapshot historical captures + prose-query vocabulary v1 (subtree semantics, field predicates, combinators, cascade operators); kernel `project-board` default inherited by every project (60+ existing snapshots migrated, 85+ projects wired). Any executive can regenerate any board in-band; explicit snapshots for historical captures. | **Tropo `[speculative]`:** Brain-powered NL-to-query compilation ("show me everything Vela shipped last week grouped by subsystem" → valid query). Streaming board regeneration for large projects.<br>**Ecosystem `[speculative]`:** Observable Plot / D3 for rich visual rendering when a brain is available; Kibana-style dashboards where the vault is the data source; Excalidraw for visual board layouts. | **Tropo `[speculative]`:** Marketplace of professional board-definitions ("a SaaS product-health board," "a professional-services utilization board").<br>**Ecosystem `[speculative]`:** Metabase / Looker as the read-side over SQLite snapshots; Notion / Linear as render-only alternate surfaces that read from the vault. |
| **Historical audit trail for every project state** — *"what did project X look like on 2026-04-15?"* answered from immutable ledger, not memory. | board-snapshot ledger entries with `taken_at` / `taken_by` / `reason` / `board_definition` provenance. Immutable once written; closest-before semantics for historical queries; deletion deferred until schemaless-store ADR locks. 60+ migrated snapshots + growing. | **Tropo `[speculative]`:** Brain-generated narrative summaries over snapshot deltas ("here's what changed between Tuesday and Friday"). Automatic snapshot scheduling per project cadence.<br>**Ecosystem `[committed]`:** Git-native time travel — the vault IS a repo; `git log` over `vault/files/<uid>.md` returns full artifact history. **`[speculative]`:** Datasette for SQL querying over snapshot JSON. | **Tropo `[speculative]`:** Compliance-grade audit reports (SOC 2 change-log evidence) generated from snapshot chains (see [Tropo × Vanta/Drata integration brief (c01c0003)](vault/files/c01c0003.md) for the roadmap).<br>**Ecosystem `[speculative]`:** SIEM integration (Splunk / Datadog); FedRAMP-tier immutable storage (S3 Object Lock, Azure Immutable Blob) as the backing store for snapshots at enterprise tier. |

**Verification footer — Rendering.** A board isn't a screenshot; it's a query declared in prose + a snapshot filed in the Vault + a regeneration any executive can run in-band. Because the render is deterministic from governed sources, an auditor can re-run last Tuesday's board today and get the same answer — or see exactly what changed. Dashboards become evidence, not status theater.

---

## 6. Tropo Governance

*Invariants + verification instruments + the kernel validator. sa.research 029 confirmed: governance and verification are one subsystem — Vela's accountability spans both.*

| Market Capability | Tropo L1 | L2 Futures | L3 Futures |
|---|---|---|---|
| **Governance without overhead** — architectural invariants enforced at the moment of action, not in an enforcement meeting. | 35+ ADRs, 7 operating principles, [ADR-035 Declared-Presence (a7c4e5b2)](vault/files/a7c4e5b2.md) (fail-loud on unreachable references across 5 surfaces), ADR-032 three-tier boot, channel capsule, directive pull pattern (ADR-024). Governance lives in the capsules that govern artifacts; agents read the rules at the point of action. | **Tropo `[speculative]`:** Brain continuously validates the full vault against ADR surface checks; surfaces drift before it compounds. Auto-generated governance reports.<br>**Ecosystem `[speculative]`:** OPA (Open Policy Agent) for policy-as-code bridges; Rego-compiled surface checks for enterprise policy frameworks (see [Tropo × OPA integration brief (c01c0002)](vault/files/c01c0002.md) for the hot-path compile-down roadmap). | **Tropo `[speculative]`:** Compliance-pack generator (SOC 2, ISO 27001, HIPAA) — each framework is a mapping from ADRs to controls. Marketplace of compliance-pack Playbooks.<br>**Ecosystem `[speculative]`:** Vanta / Drata / Secureframe — Tropo produces the evidence; these vendors produce the certification (see [Tropo × Vanta/Drata integration brief (c01c0003)](vault/files/c01c0003.md) for the roadmap). In-Q-Tel / FedRAMP integrations for regulated industries. |
| **Verification built into the system** — every spec, capsule, and activation file is proven cold-boot executable by a stranger before it locks. | sa.cold-boot (60+ invocations this vault), sa.research (25+), sa.arch-specs, sa.skeptic (adversarial review), `scripts/tropo-validate.ts` (6 structural checks, vault-dev-only — not shipped in the release zip), three-instrument verification pattern (build + research + cold-boot). Every locked artifact carries verification provenance. | **Tropo `[speculative]`:** Brain-driven continuous cold-boot — on every commit, the brain spawns stranger verifiers against changed files; nightly drift reports.<br>**Ecosystem `[committed]`:** GitHub Actions / GitLab CI for cold-boot CI/CD; Dagger for reproducible verification pipelines (see [Tropo × CI/CD integration brief (c01c0001)](vault/files/c01c0001.md) for the composition roadmap). **`[speculative]`:** tree-sitter for deeper code-level verification. | **Tropo `[speculative]`:** Third-party verification services — publish a playbook; a certified Tropo verifier signs it. Verified professionals become a marketplace credential.<br>**Ecosystem `[speculative]`:** Sigstore for cryptographic signing of verified artifacts; EAS or similar for on-chain attestations if that becomes material. Trust-as-a-service model. |

**Verification footer — Governance.** This is the subsystem that makes the whole thesis operational. Every other subsystem produces artifacts; Governance is where those artifacts get checked against the rules that govern them — at the moment of action, not after the fact. The three-instrument discipline (build + independent review + cold-boot stranger test) is the mechanism; the ADRs and principles are the rules; the sa.* verifiers are the runtime. Tropo isn't verification-first because we say so — it's verification-first because every load-bearing artifact has its own receipt.

---

## The Meta-Thesis

Tropo exists because *as AI drives execution costs toward zero, the binding constraint on economic growth shifts from intelligence to human verification bandwidth.* The seven subsystems above (the v1.7-anchored 6 + Documentation promoted v1.8) aren't just a product taxonomy — they're the verification stack.

- **Library** provides addressability (you can't verify what you can't locate).
- **Work** provides typed artifacts (the shape is legible before you read the content).
- **Agents** carry their own audit trail (who did what across generations is recoverable from the files alone).
- **Playbooks** turn processes into evidence (the run is the proof).
- **Rendering** makes state re-queryable (dashboards are evidence, not theater).
- **Governance** is where the rules meet the artifacts (verification-first by construction, not by policy).

Each subsystem contributes a piece; the stack is what the verification infrastructure claim rests on.

---

## Navigation

Each subsystem links to a hub that hosts its living history — what's shipped, what's active, what's queued. The hubs are where you go for detail.

| Subsystem | Hub | Scope |
|---|---|---|
| 1. Library | [Library hub (1aba710c)](vault/files/1aba710c.md) *(NEW in v1.3; authored alongside Stream A hub-realignment)* | Ledger + registry + cascade indexes + UID stability + schemaless document store + cross-vault federation primitives |
| 2. Work | [Work hub (2d083137)](vault/files/2d083137.md) *(renamed from TWS in v1.3)* | Typed primitives: tasks, projects, decisions, specs, collections, concept→release chain |
| 3. Agents | [Agents hub (99ed55fd)](vault/files/99ed55fd.md) *(renamed from TAS; absorbs TBS boot content)* | Executive lifecycle + boot + session agents (sa.*) + v2 three-tier memory + retirement |
| 4. Playbooks | [Playbooks hub (76bab75f)](vault/files/76bab75f.md) *(renamed from TPS in v1.3)* | Playbook spec v2.2 + playbook.capsule v2.0 + pipeline subtype + skills + actions |
| 5. Rendering | [Rendering hub (dbc1cbbf)](vault/files/dbc1cbbf.md) *(renamed from TLGS in v1.3; reframed from layered-graph to render-engine)* | Board-definitions + board-snapshots + prose query vocabulary + render engine + synthesizer |
| 6. Governance | [Governance hub (8dd772a0)](vault/files/8dd772a0.md) *(renamed from TVS in v1.3)* | ADRs + operating principles + verification instruments + three-instrument discipline |

All hubs govern by [subsystem-hub.capsule v1.1 (8a4e21c5)](.tropo/capsules/subsystem-hub.capsule.md).

---

## Provenance

- **v0.1 first cut:** Argus A29 + Mike Maziarz, 2026-04-20. 7 parallel sa.research agents (records 024–030) evidence-based the L1 column; Mike shaped the L2/L3 framing. Lived at [vault/files/c41a5bf0.md](vault/files/c41a5bf0.md).
- **v1.0 LOCKED:** Argus A31, 2026-04-21. Six Mike-approved ODs from Session 2 project-plan a3a7e131 resolved:
 - OD2-A ship at vault-root (this file).
 - OD2-B `[committed]` / `[speculative]` labels on every L2/L3 cell.
 - OD2-C 12-row baseline + 2 additional rows per OD2-E = 14 rows total.
 - OD2-D verification-thesis footer per subsystem.
 - OD2-E 2 missing rows added: Library federation row + Agents memory row.
 - OD2-F new subsystem naming locked (Library / Work / Agents / Playbooks / Rendering / Governance).
- **Member of:** v1.3 Release Scope + v1.3 historical reference + [tropo-subsystems root (aae9a37b)](vault/files/aae9a37b.md).
- **Shipped as:** v1.3 release deliverable per Tropo-OS v1.3.0 Release Plan.

---

*Tropo Capabilities | v1.0 LOCKED | Argus A31 + Mike Maziarz | 2026-04-21*
*"A new user opens this file and can navigate to every component. That's the bar."*
*Supersedes v0.1 first cut [c41a5bf0](vault/files/c41a5bf0.md). Matrix is the anchor; hubs are the rooms. First-contact readers start here.*
