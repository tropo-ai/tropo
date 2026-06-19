---
uid: 72ef5ffe
name: "events"
title: "events — Canonical Event Log Primitive"
type: capsule-definition
extends: core
version: "1.7"
v1_7_amendment_note: "v1.6 → v1.7 amendment 2026-06-13 by Talos T19 per the Mike-locked v1.70 MindBridge MUST-set (dev-spec c036dd4b §S2.3). Registers the receipt-ledger contract: delivered→read→answered three-state. Composes with the recently shipped check-events v1.1 and its per-reader receipt at vault/events/receipts/<party-uid>.jsonl. This is a documentation catch-up in the locked capsule; functional state already matches the contract. Space freed by folding v1.6 + history_split frontmatter into the history companion 63bf7487 (recreated this session)."
v1_4_amendment_note: "v1.3 → v1.4 amendment 2026-06-03 by Argus A95 captain-mode per Mike-A95 'fix the root cause' directive (closes 05ab4861 failure mode 1, send-side). Adds the AGENT IDENTITY GUARD (Rule 4): an AGENT messaging/broadcast emit (tropo.message.* / tropo.broadcast.crew from an /agents/ or // source) MUST use the agent's PARTY UID as its source_uid — emits from the agent-root UID are now REJECTED. Closes the addressing incoherence (the Talos-invisible-queue). Composes with emit-event v1.2 tool-guard + validator Check 22 (ratchet to ERROR planned v1.66). v1.3 Po-exception generalized to the whole crew."
supersedes_version: "1.6"
history_companion: "63bf7487"
tier: os
author: argus-a84
created: 2026-05-26
modified: 2026-06-13
created_by: argus-a84
modified_by: talos-t19
status: locked
locked_by: mike-maziarz
locked_at: 2026-06-14
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
pattern_exemplar: 9a7d314a
aligned_with:
  - 9fc86533
  - 4e8b21f0
  - 8a46cb6f
  - c3f68cb5
  - 9a7d314a
  - 621824df
  - 99341618
  - a5f4b26b
  - 3c02f3b7
  - 7cac6473
member_of:
  - "8dd772a0"
tags: [capsule-definition, events, event-sourced-architecture, cloudevents-aligned, messaging-substrate, append-only-log, projection-renderer-source, v1.55-stream-a-foundation, l2-l3-deployment-ready, mike-v52-walked-vela-v52-authored, argus-a84-formalized]
---

# events — Capsule Definition v1.7 (LOCKED)

**Relations**

| Relation | Target |
|---|---|
| Governed by | [capsule-definition meta (222873b9)](../../vault/files/222873b9.md) |
| Pattern exemplar | [doc-spec.capsule v1.0.2 (9a7d314a)](doc-spec.capsule.md) — sibling typed-primitive structural shape |
| Aligned with | [9fc86533 Messaging System Reframe v0.2 LOCKED](../../vault/files/9fc86533.md) — design brief that informs this capsule |
| Aligned with | [activation.capsule (4e8b21f0)](activation.capsule.md) — substrate that Stream C auto-emits events for |
| Aligned with | [channels/CAPSULE.md (8a46cb6f)](../../channels/CAPSULE.md) — substrate that becomes regenerated projection per Stream B |
| Extends | `core` |

*A typed-primitive capsule definition for messaging events. Specifies the schema, governance, and validation discipline for entries in `vault/events/00-events.jsonl` (the canonical append-only event log) plus derived projections (channels, status cards, crew brief, ops bulletins, activity feeds).*

*One canonical event log. Every agent action, every substrate write, every status transition, every pipeline-runtime event emits one row. The log is immutable; events are never edited or deleted, only appended. Channels + status cards + crew brief + ops bulletins become regenerated projections.*

---

## 1. Intent

Tropo's messaging substrate today is fragmented across four authoring surfaces (channels, status cards, activation entries, crew brief) that each claim authority over "what happened in this Studio and when." They drift silently. The visible failures (agents missing messages; cross-substrate state contradictions; ScheduleWakeup invisibility; coordination cycles that should be substrate-visible) are all symptoms of one disease: there is no single source of truth.

The events capsule defines the typed-primitive substrate for a single canonical append-only event log at `vault/events/00-events.jsonl` from which every messaging surface is projected. The envelope aligns with CloudEvents v1.0 (W3C / CNCF industry standard) per Mike's "check vendor + industry standards" discipline. Five primitive event types plus the `correlationid` extension cover messaging, request-response, acknowledgment, and polling-cycle patterns.

**Coherence by construction.** There is only one source of truth. Projections cannot lie because they are derived, not authored. Drift becomes structurally impossible.

**L2/L3 deployment-readiness from v1.0.** Designed so federation (L3 multi-Studio) lands without rewrite. Only the storage layer changes (JSONL → database → message bus); envelope semantics + agent identity model + correlation pattern stay constant.

Failure mode prevented: cross-substrate drift between authored surfaces that lie to each other as they age; coordination invisible to architecture; per-surface discipline enforcement.

---

## 2. Schema

### Required Frontmatter (envelope; per CloudEvents v1.0 spec)

Every event entry has a CloudEvents-compliant envelope. Sparse on disk per CloudEvents convention - optional fields omitted when not used.

| Field | Required | Source | Constraint / Purpose |
|---|---|---|---|
| `id` | yes | CloudEvents core | Sequential numeric ID within Studio (`00000001`, `00000002`, ...). At L3 federation, Studio-prefix prepends. |
| `specversion` | yes | CloudEvents core | Literal `"1.0"`. v1.x of CloudEvents spec; if upstream amends, this capsule amends in tandem. |
| `type` | yes | CloudEvents core | Event type identifier in dotted-namespace shape (e.g., `tropo.message.sent`, `tropo.agent.activated`, `tropo.substrate.modified`). Per-type schema for `data` field declared in §3 Event Type Registry. |
| `source` | yes | CloudEvents core | URI-shaped source identifier (e.g., `/agents/vela`, `/scripts/build-release`, `/pipeline-runtime`). Identifies the emitting tool or agent path. |
| `time` | recommended | CloudEvents core | ISO 8601 timestamp at emission. Recommended-not-required per CloudEvents; this capsule requires for all Tropo events. |
| `subject` | optional | CloudEvents core | Subject of the event (recipient identifier or affected resource short-form). |
| `datacontenttype` | optional | CloudEvents core | Defaults to `application/json`. |
| `data` | optional | CloudEvents core | Polymorphic payload (schema per `type` value per §3 Event Type Registry). |

### Universal Mandatory Tropo Extensions (per Decision H)

Two extensions present on every event regardless of type:

| Field | Required | Purpose |
|---|---|---|
| `source_uid` | yes | Canonical UID of the event emitter. Three valid categories: (a) **PARTY UID** for agent-emitted events — the agent's `type:principal` messaging-axis UID, stable across all generations (examples: `e97ac0ae` Vela, `cdf9b3ad` Argus, `34cf0f1c` Talos; per Rule 4 the agent-root / charter / soul / status-card / activation-entry UIDs are NEVER source identifiers). (b) **Tool UID** for tool-emitted events — the canonical tool entry's 8-hex UID per tool.capsule single-file truth at `vault/tools/<uid>.{py\|md\|json}`. (c) **Principal UID** for human-emitted events. **No prefixed-string convention.** All source identifiers resolve as vault graph citizens via `vault/00-index.jsonl` lookup. |
| `lifecycle` | yes | Enum: `evergreen` (preserve indefinitely; included in default projections) OR `ephemeral` (excluded from default projections; retained in log for audit). Lifecycle is a query filter, NOT a deletion trigger (per Decision C). |

### Per-Type Required Tropo Extensions (per Decision H)

Each per-type schema in §3 Event Type Registry declares which extensions the type requires. Common per-type extensions:

| Field | Required by types | Purpose |
|---|---|---|
| `source_display` | optional all | Human-readable display name (e.g., `"Vela V52"`). Renderers can resolve from UID; convenience field for projection performance. |
| `author_uid` | per-type | Agent-root or principal UID of authorship when different from emitter (Mike-as-channel pattern per Decision F). For agent-authored events, equals `source_uid`. For Mike-authored events relayed by an agent, `source_uid` = agent emitter; `author_uid` = Mike's principal UID. |
| `author_display` | optional | Author's display name. |
| `recipients` | per-type (directed-message types) | Array of recipient UIDs. One-to-many native; single-recipient is a one-element array. Project UIDs valid as recipients (inbox semantics per Stream C). |
| `correlationid` | per-type (chain-participating) | CloudEvents Correlation extension (W3C draft adopted directly per Decision I; no prefix; no underscore). Ties related events into a chain (request-reply pairs; polling cycles awaiting correlated response). |
| `subsystem_hub` | optional | Subsystem hub UIDs for the event **(v1.5 member_of DISAMBIGUATE: hub membership moved here from `member_of`)**. |
| `member_of` | optional | Project / true-parent UIDs (non-hub). |
| `vault_refs` | optional | Array of vault UIDs the event references. |
| `generation` | per-type (agent-sourced) | Generation marker (V52, A84, T10, O11, G61, C6, etc.). Not present on script-sourced events. |
| `severity` | per-type (alert/flag types) | Enum: `info` / `warn` / `error` / `fatal` / `flash`. `flash` (v1.3) is the highest-urgency tier — replaces the retired alerts.md FLASH-channel pattern; L.3 `trigger_detection.py` auto-fires the continuous-listen polling curve on receipt of any event carrying `severity: flash` (per v1.61 Lane D'2). |
| `session_id` | per-type (chat-session) | Ties events in one chat-session chain. |

### Polymorphic `data` schema per event type

The `data` field's schema is determined by the `type` value. Each registered event type declares its own data shape in §3 Event Type Registry. Validator extensions enforce per-type schema (WARN at v1.0; ERROR ratchet planned v1.1 once registry stabilizes).

### Agent identification — use the PARTY UID (messaging axis); agent-root is lineage-only (v1.4)

Every agent has two event-relevant axes. **The PARTY UID (`type:principal`, messaging axis) is the canonical identifier for `source_uid`, `author_uid`, `subject`, and `recipients`** — what an agent emits *from* and is addressed *at*. The **agent-root UID** (`type:project`, lineage axis) is for `member_of` parentage + generation-lineage queries ONLY; it MUST NOT appear as a live agent's `source_uid` / `subject` / `recipients` / `--party`. This is the v1.63 Immutable Identity doctrine (e85d2d2c), made canonical crew-wide at v1.4 — it closes the addressing incoherence (the Talos-invisible-queue: a message sent from the agent-root is invisible to a reader polling the party UID). Live registry (both axes):

| Agent | **Party UID** — `source_uid` / `recipients` / `subject` (messaging axis) | Agent-root — `member_of` / generation only (lineage axis) | Role |
|---|---|---|---|
| Vela | `e97ac0ae` | `25f5a0b9` | Chief of Staff |
| Argus | `cdf9b3ad` | `6dff0111` | Chief Architect |
| Talos | `34cf0f1c` | `123e12e7` | Lead Engineering Swarm |
| Metis | `7c017d1f` | `775697b1` | Tropo Strategist |
| Orpheus | `c387a949` | `c0b3301f` | Keeper of Lore |
| Cosmo | `085bd59a` | `4c4b403e` | Hybrid Chief of Staff (Argo-private) |
| Po | `d70ae4cb` | `68830153` | Studio Concierge (Executive) — founding agent-class principal |

### Agent-class-principal event-identity — the crew-wide pattern (v1.4)

**Every crew agent's event party-UID is a `type:principal` party UID, not the `type:project` agent-root UID** — the two-axis shape is the rule for all agents. The `source_uid` validator allows a `type:principal` UID with `principal_class != human` as a valid emitter identity; future agent-class principals (federated-Studio concierges, marketplace agent-principals) follow the same shape — principal UID on the messaging axis, agent-root UID on the lineage axis. *(Founding case: Po's v1.3 carve-out, generalized crew-wide at v1.4 via v1.63 Immutable Identity — full narrative in the [history companion (63bf7487)](events.history.md).)*

### Principal UIDs - registered

Mike Maziarz: `type:principal` + `principal_class:human` at [3f58b5c5](../../vault/files/3f58b5c5.md). Po: `type:principal` + `principal_class:agent-concierge` at [d70ae4cb](../../vault/files/d70ae4cb.md). The `principal_class:` discriminator differentiates human vs agent-class; L3 federation extends additional principal classes through the same slot — schema-coherent, no new type families.

---

## 3. Event Type Registry — Five Primitives + Substrate-Write Auto-Emission Family

### Five Primitive Event Types (messaging vocabulary per Decision §5 of 9fc86533)

Earn-the-abstraction-strict: start with the minimum viable set. Expand as concrete use cases emerge in production.

**`tropo.message.sent`** - general agent-to-agent or agent-to-project messaging. Fire-and-forget by default.

```yaml
type: tropo.message.sent
data:
  body: "<short message string OR null if body_file populated>"   # ≤500 chars inline; else use body_file
  body_file: "vault/events/files/<id>.md"   # optional; companion file path for long bodies
  reply_required: false   # boolean; default false; true declares reply expected
  deadline: "<ISO 8601>"   # optional; meaningful when reply_required:true
required_extensions: [recipients, correlationid (when reply_required:true)]
```

**`tropo.message.acked`** - explicit receipt confirmation correlated via `correlationid` to the original message. Useful for "received; substantive reply coming later" signals when deadline matters.

```yaml
type: tropo.message.acked
data:
  ack_note: "<optional short note>"
required_extensions: [recipients, correlationid]
```

**`tropo.message.replied`** - response with content correlated to original message via `correlationid`. Set `data.final: true` to mark end-of-conversation (no separate `conversation.closed` event needed; lifecycle composes into data).

```yaml
type: tropo.message.replied
data:
  body: "<short reply string OR null if body_file populated>"
  body_file: "vault/events/files/<id>.md"   # optional
  final: false   # boolean; default false; true marks end-of-conversation
required_extensions: [recipients, correlationid]
```

**`tropo.cycle.opened`** - declares an active polling / wakeup cycle. Active cycles become substrate-visible per Decision §5.

```yaml
type: tropo.cycle.opened
data:
  purpose: "<short description>"
  interval_seconds: 120
  max_iterations: 15
  awaits_correlation_id: "req-00000010"   # optional; when set, cycle auto-closes when awaited event lands
required_extensions: [correlationid]
```

**`tropo.cycle.closed`** - terminates a cycle with reason.

```yaml
type: tropo.cycle.closed
data:
  reason: "<enum: correlated_response_received / timeout / manual_terminate / max_iterations_reached>"
  correlated_event: "<event id of correlated response when reason:correlated_response_received>"
required_extensions: [correlationid]
```

### Substrate-Write Auto-Emission Family (per Stream C; Decision G composability piece)

Every governed-substrate write auto-emits an event as a side-effect of the substrate-write infrastructure. Agents don't manually emit; the tooling does. The five canonical substrate-write event types:

**`tropo.substrate.created`** - new vault entry authored.

```yaml
type: tropo.substrate.created
data:
  uid: "<8-hex UID>"
  vault_type: "<entry type: note / design-brief / capsule-definition / activation / pipeline-run / etc.>"
  vault_path: "vault/files/<uid>.md"   # OR kernel substrate path
required_extensions: [vault_refs (single-element array containing uid)]
```

**`tropo.substrate.modified`** - existing vault entry amended.

```yaml
type: tropo.substrate.modified
data:
  uid: "<8-hex UID>"
  vault_path: "vault/files/<uid>.md"   # OR kernel substrate path
  fields_changed: ["<field name>", ...]   # optional; populated when known
required_extensions: [vault_refs]
```

**`tropo.substrate.recycled`** - vault entry soft-deleted via tropo-recycle.py (per Preservation Discipline).

```yaml
type: tropo.substrate.recycled
data:
  uid: "<8-hex UID>"
  reason: "<short rationale>"
required_extensions: [vault_refs]
```

**`tropo.substrate.archived`** (v1.3) - bulk or path-based substrate archived to `99-recycle/` per Preservation Discipline. Distinct from `tropo.substrate.recycled`: that type covers single vault/files/<uid>.md soft-delete via tropo-recycle.py; this type covers path-based or bulk archival of substrate without a single vault/files UID (channels, tools at vault/tools/, folders) moved to a dated `99-recycle/<descriptor>-<date>/` directory with a README.

```yaml
type: tropo.substrate.archived
data:
  paths: ["<archived path>", ...]   # one or more source paths archived
  recycle_path: "99-recycle/<descriptor>-<date>/"   # destination folder
  readme_path: "99-recycle/<descriptor>-<date>/README.md"   # archival rationale doc
  reason: "<short rationale>"
  cycle: "<version string when archived as part of a cycle>"   # optional
required_extensions: [lifecycle (evergreen — archival is a durable record)]
```

**`tropo.substrate.inboxed`** - vault entry filed at an inbox project via `member_of:` (composes Mike-V52's "01-inbox convention becomes an event" insight per Stream C).

```yaml
type: tropo.substrate.inboxed
data:
  uid: "<8-hex UID>"
  inbox_uid: "<project UID of the inbox>"   # e.g., 0a1a36fe for dev-pipeline 01-inbox
required_extensions: [vault_refs, recipients (one-element array containing inbox_uid)]
```

**`tropo.validator.run.completed`** - validator run finished (auto-emitted by tropo-validate.py).

```yaml
type: tropo.validator.run.completed
data:
  passed: 45
  failed: 0
  warnings: 348
required_extensions: [severity (info if failed:0; warn if failed>0)]
```

### Agent Lifecycle Family (auto-emitted by write-activation-entry.py per Stream C)

**`tropo.agent.activated`** - agent boot opened activation entry.

```yaml
type: tropo.agent.activated
data:
  agent: "argus"
  generation: "A84"
  activation_uid: "<8-hex>"
  predecessor: "A83"
  model: "claude-opus-4-7"
required_extensions: [vault_refs (single-element array containing activation_uid)]
```

**`tropo.agent.retired`** - agent retirement closed activation entry.

```yaml
type: tropo.agent.retired
data:
  agent: "argus"
  generation: "A84"
  activation_uid: "<8-hex>"
  closure_reason: "<enum from activation.capsule>"
  transfer_uid: "<8-hex of living-transfer; optional>"
required_extensions: [vault_refs]
```

### Sub-Agent Dispatch Family (per Decision D; sa.* commission encompassed in messaging substrate)

**`tropo.sub_agent.commissioned`** - sa.* dispatched.

```yaml
type: tropo.sub_agent.commissioned
data:
  sub_agent_class: "sa.skeptic"
  activation_log_path: "agents/sa/sa.skeptic/activation-log/<NNN>-<spawner>-record.md"
  commissioned_purpose: "<short description>"
required_extensions: [correlationid (ties to subsequent sub_agent events)]
```

**`tropo.sub_agent.acked`** - sa.* boot complete + [QUERY] posted.

**`tropo.sub_agent.work_assigned`** - parent agent posted [RESPONSE] with work scope.

**`tropo.sub_agent.work_completed`** - sa.* posted [DONE] with deliverable.

**`tropo.sub_agent.terminated`** - parent agent posted [SHUTDOWN].

### Pipeline Lifecycle Family (auto-emitted by pipeline-activate + pipeline-runtime tools per Stream C; sibling to existing run.jsonl per Decision G)

**`tropo.pipeline.activated`** / **`tropo.pipeline.bootstrapped`** / **`tropo.pipeline.step_completed`** / **`tropo.pipeline.closed`** - covers dev-pipeline + doc-pipeline + test-pipeline + publish.pipeline lifecycle visibility.

### Release Lifecycle Family

**`tropo.release.shipped`** - auto-emitted by the build-release tool at clean-ship.

```yaml
type: tropo.release.shipped
data:
  version: "v1.54.0"
  release_uid: "<8-hex>"
  pristine_streak: 61
  validator_state: {passed: 45, failed: 0, warnings: 348}
required_extensions: [vault_refs, severity (info)]
```

### Cycle Coordination Family (v1.2)

Cross-lane ship-gate coordination + cycle-activation broadcast events. Cycle-coordinating agent (typically Argus) emits to ship-firing agent (typically Vela) as ship gates close incrementally; cycle-activation broadcast emitted at cycle activation moment to crew via party-UID-addressable broadcast.

**`tropo.cycle.activated`** - cycle activation broadcast event. Subject anchors at cycle brief UID; lifecycle:evergreen.

```yaml
type: tropo.cycle.activated
data:
  cycle: "v1.59.0"   # version string
  title: "<cycle title>"
  block: "<Block 5 cycle 5 of 7 OR Block 6 cycle X of Y>"
  brief_uid: "<8-hex cycle brief UID>"
  dev_spec_uid: "<8-hex dev-spec UID>"
  activation_entry_uid: "<8-hex activation entry UID>"
  pipeline_run_uid: "<8-hex pipeline-run UID>"
  candidates_count: "<int>"   # optional; substrate items absorbed
  total_estimate: "<wall-clock string e.g. 14-18h; 1.5-day arc>"
  composes_with: ["<source-substrate UID descriptions>"]   # optional
  broadcast_intent: "<short string for human-readable context>"
required_extensions: [vault_refs (single-element array containing brief_uid)]
```

**`tropo.cycle.ship_gate_progress`** - cross-lane ship-gate-status signal. Emitted by cycle-coordinating agent to ship-firing agent as ship gates close incrementally. Reports closed-vs-open gates + ship-gate-window-status.

```yaml
type: tropo.cycle.ship_gate_progress
data:
  cycle: "v1.59.0"
  gates_closed: ["<list of closed-gate descriptions>"]
  gates_open: ["<list of open-gate descriptions>"]
  ship_gate_window_status: "<enum: ALL-OPEN | ONE-LANE-PENDING | READY-TO-FIRE>"
  next_signal: "<description of next event-class addressed agent will receive>"
  validator_state_target: "<expected validator pass/fail/warn at ship>"
required_extensions: [recipients (party UID of ship-firing agent)]
```

### Broadcast Family (v1.3)

Crew-wide announcement events. Where the Cycle Coordination Family's `tropo.cycle.activated` is cycle-activation-specific, `tropo.broadcast.crew` is the general crew-wide announcement primitive (it replaced the retired ops.md + alerts.md channel surfaces at v1.61).

**`tropo.broadcast.crew`** - crew-wide broadcast announcement. Subject anchors at a short broadcast-target descriptor; lifecycle:evergreen (crew announcements are durable record). FLASH-urgency broadcasts carry `severity: flash` (see severity:flash semantics below).

```yaml
type: tropo.broadcast.crew
data:
  headline: "<one-line broadcast headline>"
  body: "<short broadcast body string OR null if body_file populated>"   # ≤500 chars inline; else body_file
  body_file: "vault/events/files/<id>.md"   # optional; for prose-heavy broadcasts
  category: "<enum: ship | cycle-state | ops | governance | crew-state | alert>"
required_extensions: [lifecycle (evergreen)]
optional_extensions: [recipients (omit for all-crew; populate for targeted subset), severity (flash for FLASH-urgency)]
```

**severity:flash semantics (v1.3) — the alerts.md replacement path.** Any event (broadcast or otherwise) carrying `severity: flash` is the highest-urgency tier, replacing the retired alerts.md FLASH channel. On receipt of a `severity: flash` event addressed to (or broadcast inclusive of) an agent's party UID, `.tropo/scripts/lib/trigger_detection.py` (L.3) auto-fires that agent's continuous-listen polling curve — the structural close on "FLASH alerts need immediate attention" without a dedicated channel file. A FLASH crew alert is `tropo.broadcast.crew` + `category: alert` + `severity: flash`. A FLASH directed alert is `tropo.message.sent` + `severity: flash` + `recipients`.

### Emit-time Strictness Rule (v1.2 amendment per Argus A87 captain-mode 2026-05-28; closes v1.59 R3 component)

**Rule 11 (emit-time strictness) — v1.2 addition.** emit-event.py rejects unregistered event types — ERROR by default since the v1.60 ratchet (`--no-strict` opts out). Composes with Lane V Layer 3 meta-validator (M.1 at 8e2f1a47) — Layer 3 catches schema-vs-implementation drift at validation-time; this Rule catches type-registration drift at emit-time. Two-tier defense. *(Empirical justification — the v1.58/v1.59 unregistered-type catches — in the companion's v1_2 amendment note.)*

### Extending the registry

New event types extend the registry per the standard amendment pattern. Registry-extension cycles author additional `type` entries with their `data` schema + required extensions + lifecycle defaults. Sparse on disk by construction; old events stay readable forever; new consumers know to expect new types; older consumers skip unknown types gracefully.

---

## 4. Tool-Sourced Event Identification

**Tool-sourced events use the emitting tool's vault UID directly in `source_uid`.** Lookup via `vault/00-index.jsonl` graph query: `grep '"name":"<tool-name>"' vault/00-index.jsonl` → returns tool entry with UID + implementation path. No prefixed-string convention; no separate registry to maintain; the tool registry IS the vault graph.

**New tools that emit events:** register as tool entries per tool.capsule v1.6 single-file-truth pattern at `vault/tools/<uid>.{py\|md\|json}`. Their UIDs become valid `source_uid` values automatically via vault index. *(The v1.0 `script:` prefixed-string identifier registry was RETIRED at v1.1; retirement narrative + examples table in the [history companion (63bf7487)](events.history.md).)*

---

## 5. Storage Primitive — Hybrid JSONL Canonical + SQLite Derived (per Decision E)

### Canonical layout

```
vault/events/
├── 00-events.jsonl                   # canonical append-only event log (single shard initial; sharding-capable per Decision A)
├── 00-events-index.sqlite            # derived materialized-view + index (regenerable from JSONL)
├── receipts/                         # per-reader read-receipt ledger (v1.7)
│   ├── <party-uid>.jsonl
├── files/                            # companion file payloads for long-body events
│   ├── 00000001.md
│   ├── 00000002.md
│   └── ...
└── AGENTS.md                         # folder governance contract (authored at Stream A ship)
```

### emit-event mechanics (zero query lag by design)

The canonical emit primitive at `.tropo/scripts/emit-event.py` does dual-write inside a single lock:

1. Acquire `fcntl.flock` on the JSONL file (matches pipeline-runtime atomic-append pattern)
2. Open SQLite connection in WAL mode
3. Compute next `event_id` (single read from SQLite max)
4. BEGIN SQLite transaction
5. Append JSONL row + `fsync()` to disk (durable JSONL write)
6. INSERT into SQLite events table + COMMIT
7. Release file lock

End-to-end about 1-5 ms on local SSD. Both substrates land together OR neither does (lock prevents partial state). WAL mode means SQLite readers query while writers commit. The moment emit-event returns success, the row is queryable in SQLite. Zero query lag.

### SQLite schema (derived; regenerable)

```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  specversion TEXT NOT NULL,
  type TEXT NOT NULL,
  source TEXT NOT NULL,
  time TEXT NOT NULL,
  subject TEXT,
  datacontenttype TEXT,
  data TEXT,
  source_uid TEXT NOT NULL,
  lifecycle TEXT NOT NULL,
  source_display TEXT,
  author_uid TEXT,
  author_display TEXT,
  correlationid TEXT,
  generation TEXT,
  severity TEXT,
  session_id TEXT,
  member_of TEXT,
  vault_refs TEXT,
  raw_jsonl_line TEXT NOT NULL
);

CREATE TABLE event_recipients (
  event_id INTEGER NOT NULL REFERENCES events(id),
  recipient_uid TEXT NOT NULL,
  PRIMARY KEY (event_id, recipient_uid)
);

CREATE INDEX idx_events_type ON events(type);
CREATE INDEX idx_events_source_uid ON events(source_uid);
CREATE INDEX idx_events_correlationid ON events(correlationid);
CREATE INDEX idx_events_time ON events(time);
CREATE INDEX idx_events_lifecycle ON events(lifecycle);
CREATE INDEX idx_event_recipients_recipient ON event_recipients(recipient_uid);
```

Multi-recipient events normalize into one row in `events` + N rows in `event_recipients` for efficient recipient-filter queries.

### Receipt Ledger — S2.1/S2.2 v1.70 (v1.7 addition; claims 69edec91)

The receipt ledger provides **order-independent, gap-proof event reads** by replacing cursor-based subtraction with set-difference. 

1. **Storage:** Per-reader append-only ledger at `vault/events/receipts/<party-uid>.jsonl`.
2. **Schema:** One JSON object per read event: `{"event_id": "<8-digit id>", "read_at": "<ISO ts>", "reader": "<party-uid>"}`.
3. **Idempotency:** Tooling skips any `event_id` already present in the reader's ledger.
4. **Semantics:** "New" events = (addressed-to-me ∪ broadcasts) − my-receipt-set.
5. **Observability:** A message's state is **delivered** (in log) → **read** (in recipient's receipt ledger) → **answered** (reply with correlated ID).

### Failure modes + recovery

- **SQLite corrupts or schema needs migration:** blow it away; regenerate from canonical JSONL via `rebuild-events-sqlite.py`. JSONL is bulletproof.
- **Mid-write crash:** fcntl auto-releases on process death. Trailing partial JSONL line gets truncated by next vault-rebuild. Idempotent recovery.
- **Concurrent agents emitting:** fcntl serializes writers (~5ms tail latency under contention; imperceptible). Readers never block (WAL mode).

### L2 / L3 transition path

**L2 (database-backed Studio):** SQLite flips from derived to canonical naturally. JSONL becomes the export/backup format. Same schema; same query interface; just a flip on which is the source.

**L3 (federated multi-Studio):** CloudEvents-compliant message bus (NATS / Kafka / Pulsar speak CloudEvents directly). Studio identity prefixes per [federation foundation (7cac6473)](../../vault/files/7cac6473.md) carry through to event IDs; agent references include their home Studio.

The L2/L3 path is design-constrained from v1.0 forward - the storage primitive can swap without rewriting envelope semantics or agent identity model.

### Performance characteristics

Peak Studio pace ≈ 50 events/sec; SQLite WAL + fcntl handles this with two orders of magnitude headroom. Event substrate overhead is structurally below LLM work overhead by 100x.

---

## 6. State Machine

```
(birth) → active → archived (rare; only on shard rotation)
```

Events have minimal state machine - they are born, they exist forever, optionally an archive-shard rotation moves them off the hot shard.

| State | Meaning |
|-------|---------|
| `active` | Event is in the current shard; queryable via standard projections. |
| `archived` | Event has been moved to an archive shard (per Decision A sharding policy). Still queryable via federated query across all shards; excluded from default hot-shard projections. |

**Valid transitions:**

- `(birth) → active` — emit-event.py writes the row
- `active → archived` — shard rotation tool moves the row to archive shard
- `archived → archived` — terminal

**Forbidden transitions:**

- `active → (deletion)` — events are NEVER deleted (per Decision C immutable-forever); soft-removal via `lifecycle: ephemeral` filter is the only "deletion" mechanism, and the event row stays in the log
- `archived → active` — terminal; events do not un-archive

---

## 7. Governance Rules

### Append-only invariant (Rule 1; Decision C immutable-forever)

The event log is append-only. Events are NEVER edited or deleted once written. `lifecycle: ephemeral` is a query filter (events excluded from default projections) - NOT a deletion trigger. Storage growth is bounded by shard rotation (Decision A), not by deletion. This is the load-bearing structural invariant; violation = governance failure requiring principal escalation.

### Source-uid mandatory (Rule 2; Decision H)

Every event MUST carry `source_uid`. For AGENT-emitted events it is the agent's PARTY UID (`type:principal`, messaging axis — per §2 + Rule 4); for TOOL-emitted events the tool's UID; for HUMAN-emitted events the principal UID. Charter UIDs, status-card UIDs, activation-entry UIDs, and — for live agents — agent-root UIDs are NEVER used as source identifiers. Validator extension enforces (Check 6 + Check 22).

### Lifecycle mandatory (Rule 3; Decision H + C)

Every event MUST carry `lifecycle` ∈ {`evergreen`, `ephemeral`}. Default projections filter `lifecycle:evergreen`; cross-cycle query uses both. Validator extension enforces.

### Party UID is the canonical agent source_uid; agent-root is lineage-only (Rule 4; v1.4 refreshed v1.7)

The PARTY UID (`type:principal`, messaging axis) is the canonical agent identifier for `source_uid` / `author_uid` / `subject` / `recipients`. The agent-root UID (`type:project`) is the LINEAGE axis: `member_of` parentage + generation-lineage queries ONLY; it MUST NOT appear as a live agent's `source_uid` / `author_uid`. 

**Addressing Union:** directed messages (`subject` axis) SHOULD address the recipient's party UID for messaging-axis convergence. However, to ensure no message is missed, readers (`check-events`) scan for their ID on BOTH the party-UID and the agent-root-UID axes. This union is a robustness provision for READERS; senders remain disciplined to the party-UID.

*(Rule 4 version history — the v1.3 Po carve-out → v1.4 crew-wide generalization → v1.7 addressing-union — in the [history companion (63bf7487)](events.history.md).)*

### Author-vs-emitter split (Rule 5; Decision F)

When `author_uid:` differs from `source_uid:`, the event captures a Mike-as-channel-or-relay-pattern (active agent emits both sides of human-agent chat). For agent-authored events, `source_uid` = `author_uid` (omit `author_uid` for sparseness). For Mike-authored events relayed by an agent, `source_uid` = agent emitter; `author_uid` = Mike's principal UID.

### Correlationid load-bearing for chains (Rule 6; per §5 of 9fc86533)

Any event participating in a request-reply chain, polling cycle, or sub-agent dispatch chain MUST carry `correlationid` (CloudEvents Correlation extension; per Decision I no prefix; no underscore). Active cycles + open conversations become substrate-visible by querying `WHERE correlationid = <id>`. Validator extension fires WARN if a `tropo.message.replied` lacks `correlationid` (replies SHOULD always correlate).

### Substrate-writes-as-events composability (Rule 7; Stream C)

Every governed-substrate write tool MUST auto-emit an event as a side-effect (no agent-discipline burden). Rebuild-vault.py + write-activation-entry.py + tropo-recycle.py + pipeline-activate.py + pipeline-runtime.py + build-release.py + tropo-validate.py are the seven choke-points; new substrate-write tools added in future cycles MUST emit events. Validator extension enforces (WARN at v1.0; ERROR ratchet v1.X+ once retrofit complete).

### Per-channel rendered-from-events marker (Rule 8; Decision B; Stream D)

Each channel file's frontmatter declares `rendered_from_events: true` (or absent/false for legacy manual channels). The renderer reads all channel files; only marked channels get regenerated from events. Agent posting to a channel reads target frontmatter; calls `emit-event.py` if marked; falls back to `Edit` if absent. Migration is incremental (per-channel flip) OR big-bang (all channels at once). Implementation path lives in cycle briefs.

### Pipeline-runtime sibling at v1.0 (Rule 9; Decision G)

Pipeline-runtime's `run.jsonl` substrate stays separate at v1.0. Architectural intent is unification (pipeline-runtime events become a category in the canonical event log eventually); deferred until messaging substrate has stabilized in production. The merge is a future substrate-coherence cleanup; this capsule does not fight it.

### No human-readability at canonical layer (Rule 10; per 9fc86533 §9 L2/L3 readiness)

JSONL is canonical because it's machine-portable across L1 (filesystem) → L2 (database) → L3 (message bus). Markdown bodies live in companion files (`vault/events/files/<id>.md`). Channels render to markdown as projections, not as source. Body inline (`data.body`) is acceptable for short content; spill to `data.body_file` when prose-heavy or evergreen-candidate.

### Bulletproof recovery via canonical-JSONL (Rule 11; Decision E)

JSONL is the substrate of truth. SQLite is derived; regenerable via `rebuild-events-sqlite.py` if corrupted. No mechanism deletes JSONL rows; backup discipline preserves JSONL files; SQLite is rebuildable from JSONL alone.

### Studio sovereignty composes with events (Rule 12; aligns with Mike-A83 stm-a83-004)

Event substrate stays Studio-bounded at L1. Cross-Studio events require explicit federation handshake at L3 (per [federation foundation (7cac6473)](../../vault/files/7cac6473.md)). Studio identity prefixes carry through to event IDs at L3; agent references include their home Studio. Studio Sovereignty doctrine binds: container-level (Studio) bounds federation/portability, not substrate-level.

### Crew channels become queries; user-facing surfaces stay as projections (Rule 13; v1.3 + Mike-A88 keep-the-two-surfaces lock)

**The distinction is by AUDIENCE.** Crew-internal coordination channels are retired (archived to `99-recycle/` at v1.61); agents query the event log directly via `query-events --party <uid>` (V7 "check /events" doctrine). Crew-wide announcements emit `tropo.broadcast.crew`; FLASH alerts carry `severity: flash`; bilateral coordination emits `tropo.message.sent`/`replied` with `recipients`. Rule 8's `rendered_from_events:` marker is historical for crew traffic.

**Two user-facing surfaces are KEPT** because their audience is the human principal, who does not run `query-events`: `channels/tropo.md` (Studio-activity feed) + `channels/releases.md` (release/news). They survive as **user-facing projections of the event log** — rendered, auto-updated, never stale. The user-facing projection renderer (distinct from the retired crew-channel renderer) is a booked follow-on; until it ships, the two files are maintained as-is.

One canonical event log; crew channels become queries (zero intermediary); user surfaces become projections (rendered intermediary, because users read, not query). Drift is structurally impossible either way. *(The rule's original "all channels gone" over-claim + same-day Mike-A88 correction, and the v1.61 per-lane retirement inventory, are preserved in the [history companion (63bf7487)](events.history.md) v1_3 note.)*

---

## 8. Validation Checks

In addition to core checks, the events.capsule §8 declares the following validator extensions (implemented in `.tropo/scripts/lib/event_validators.py`; fired at every vault rebuild).

### Universal envelope checks (fire on every event row)

1. **`check_event_envelope_required`** — `id` + `specversion` + `type` + `source` + `time` + `data` (if non-empty) present. FAIL severity.
2. **`check_event_specversion_literal`** — `specversion == "1.0"` literal. FAIL severity (CloudEvents spec amendment requires capsule amendment in tandem).
3. **`check_event_id_sequential`** — `id` is sequential integer; no gaps in current shard; no duplicates. FAIL severity. (Shard boundary tolerance: gap at shard rotation boundary is acceptable + documented in shard manifest.)
4. **`check_event_time_iso8601`** — `time` is ISO 8601 with timezone offset (UTC or local). WARN severity.
5. **`check_event_type_registered`** — `type` value is registered in §3 Event Type Registry. WARN at v1.0 (registry-extension cycles add types); ERROR ratchet v1.1+ once registry stabilizes.

### Universal extension checks (per Decision H)

6. **`check_event_source_uid_mandatory`** — `source_uid` field present + non-empty + 8-hex + resolves to a valid emitter: a `type:principal` PARTY UID (agents + humans) OR a tool UID (tool-emitted events). FAIL severity (Rule 2 enforcement). NOTE (v1.4): historical events carry agent-root `source_uid`s (pre-v1.63); Check 6 accepts any resolvable 8-hex emitter so the append-only log does not retro-fail — the agent-root drift is caught going-forward by Check 22 (WARN), not by failing history.
7. **`check_event_lifecycle_mandatory`** — `lifecycle` field present + value ∈ {`evergreen`, `ephemeral`}. FAIL severity (Rule 3 enforcement).
8. **`check_event_source_uid_not_charter`** — `source_uid` value is NOT a charter UID / soul UID / status card UID / activation entry UID for the agent (catches the common drift class where authors use the wrong UID flavor). WARN at v1.0; ERROR ratchet v1.1+.
22. **`check_no_agent_emit_from_root_uid` (v1.4 NEW; Check 22 per spec [81e52840](../../vault/files/81e52840.md); checks 18–21 reserved by sibling v1.66 cluster specs)** — for any agent-source messaging/broadcast event (`tropo.message.sent` / `tropo.message.replied` / `tropo.message.acked` / `tropo.broadcast.crew` whose `source` is an agent path), `source_uid` MUST be a registered PARTY UID, NOT an agent-root UID. **WARN at v1.4; ERROR ratchet with the v1.66 messaging cluster.** The Disciplinary→Structural send-side enforcement — the wrong-axis emit (the Talos-invisible-queue, ~205 historical instances at 05ab4861) becomes catch-on-write. Implemented in `.tropo/scripts/lib/event_validators.py`; the emit-event tool (`ca90f098`) ALSO rejects wrong-axis agent emits at write-time (defense in depth — prevention at the tool + detection at the validator).

### Per-type extension checks (Rule per type schema)

9. **`check_event_per_type_required_extensions`** — for each event row, look up `type` in §3 Event Type Registry; verify all per-type required extensions are present. WARN at v1.0; ERROR ratchet v1.1+ once registry stabilizes.
10. **`check_event_correlationid_for_replies`** — every `tropo.message.replied` event MUST carry `correlationid`. WARN at v1.0; ERROR ratchet v1.1+ (Rule 6 enforcement).

### Data schema checks

11. **`check_event_data_schema_per_type`** — for each event row, validate `data` field against the registered schema for `type` (per §3 Event Type Registry). WARN at v1.0; ERROR ratchet v1.1+ once registry stabilizes.
12. **`check_event_body_file_path_resolves`** — when `data.body_file` is populated, the path exists at vault root. WARN severity.

### Substrate-write auto-emission checks (Rule 7; Stream C)

13. **`check_substrate_write_auto_emission_coverage`** — each of the seven canonical substrate-write scripts (rebuild-vault.py + write-activation-entry.py + tropo-recycle.py + pipeline-activate.py + pipeline-runtime.py + build-release.py + tropo-validate.py) has an event emission integration. Validator reads script source; checks for `emit-event.py` invocation or equivalent. WARN at v1.0 (retrofit in flight); ERROR ratchet v1.X+ once retrofit complete.
14. **`check_substrate_write_event_temporal_correlation`** — for vault entries with recent `modified:` timestamps, verify a `tropo.substrate.modified` event exists in the event log with matching `vault_refs:` and time near the `modified:` timestamp (within configurable tolerance). WARN severity (catches missing-event gaps). v1.X+ planned once Stream C retrofit completes.

### Channel projection checks (Rule 8; Stream D)

15. **`check_rendered_channel_no_manual_edits`** — channels with frontmatter `rendered_from_events: true` are not manually edited (validator checks Git diff or last-modified discipline). WARN at v1.0; ERROR ratchet v1.X+ once render-events-as-views engine ships.

### Storage primitive consistency checks

16. **`check_jsonl_sqlite_consistency`** — SQLite event count matches JSONL row count + every JSONL row has a corresponding SQLite row. INFO severity at v1.0 (rebuilds frequent during stabilization); WARN ratchet v1.X+ once stable.
17. **`check_jsonl_append_only_invariant`** — no `id` collision; no row mutation; no row deletion. FAIL severity (Rule 1 load-bearing structural invariant).

### Validation Check authoring lane

Validator implementation: Argus (schema + check spec authoring); Talos T10 (Python implementation in `.tropo/scripts/lib/event_validators.py` or extensions to `tropo-validate.py`). Phase D ratchet at cycle close per substrate maturity signal.

---

## 9. Inheritance

Extends `core`. Inherits all core rules + frontmatter floor:

- UID uniqueness (one event per `id` in the shard)
- Schema version (this capsule = `schema_version: 2`)
- Author/created/modified invariants (capsule-definition level; per-event rows do not carry these fields — they are inherent to events)

Note: events are NOT vault entries at `vault/files/<uid>.md`. They are rows in `vault/events/00-events.jsonl`. Core inheritance applies to the capsule-definition itself, not to event rows. Per-event-row schema is governed by §2 + §3 above.

---

## 10. Composes-With

### Pillar 1 callable surfaces (canonical composition per v1.1 Pillar 1 taxonomy reconciliation)

- **[tool.capsule v1.6 (d5e1b4a3)](tool.capsule.md)** — CANONICAL composition relationship. Tools are the typed primitive that emits substrate-write events; tool UIDs at `vault/tools/<uid>.{py\|md\|json}` per single-file-truth are valid `source_uid` values directly. emit-event itself is a tool registered per tool.capsule v1.6 from inception.
- **[how-to.capsule v1.4 (a7c3f489)](how-to.capsule.md)** — sibling Pillar 1 callable surface (inline behavior bundles). Tool invocations within a how-to emit events the same way standalone tool invocations do.
- **[session-agent.capsule v1.5 (b4e2a718)](session-agent.capsule.md)** — sibling Pillar 1 callable surface (session-resident specialists). sa.* dispatch family event types per §3 capture sa.* lifecycle.
- **[action.capsule v1.1 (9b7f5e34)](action.capsule.md)** — sibling Pillar 1 callable surface (kernel-tier compound operations). Action invocations emit substrate-write events (actions mint typed vault entries → tropo.substrate.created events).
- **[kernel.capsule v2.0 (7c0e314a)](kernel.capsule.md)** — kernel infrastructure governance; events shipping at v1.55 are vault-tier substrate (not kernel-tier; events live at vault/events/ not .tropo/events/); composes for the kernel/vault boundary discipline.

### Other composability

- **[9fc86533 Messaging System Reframe v0.2 LOCKED (9fc86533)](../../vault/files/9fc86533.md)** — design brief that this capsule formalizes. v0.2 architectural decisions A-I translated into this capsule's schema + governance + validation.
- **[activation.capsule v1.0 (4e8b21f0)](activation.capsule.md)** — agent lifecycle substrate; `tropo.agent.activated` / `tropo.agent.retired` event types auto-emit at boot/retire per Stream C retrofit of write-activation-entry tool.
- **[channels/CAPSULE.md v1.2 (8a46cb6f)](../../channels/CAPSULE.md)** — channel substrate that becomes regenerated projection per Stream B. Channel frontmatter `rendered_from_events:` marker enables incremental migration (Rule 8).
- **[doc-spec.capsule v1.0.2 (9a7d314a)](doc-spec.capsule.md)** — sibling typed-primitive structural shape; pattern_exemplar. doc-spec authoring auto-emits `tropo.substrate.created` per Stream C.
- **[dev-spec.capsule v1.0 (c3f68cb5)](dev-spec.capsule.md)** — same as doc-spec composition.
- **[test-spec.capsule v1.0 (621824df)](test-spec.capsule.md)** — same as doc-spec composition.
- **[release.capsule (b19e8d43)](release.capsule.md)** — `tropo.release.shipped` event type auto-emits at build-release tool clean-ship.
- **[publish.pipeline.capsule (e5b3f2c7)](publish.pipeline.capsule.md)** — `tropo.pipeline.*` event types auto-emit per pipeline lifecycle per Stream C retrofit of pipeline-runtime tool.
- **[agent-activation.playbook v2.12 (99341618)](../playbooks/agent-activation.playbook.md)** — boot chain emits `tropo.agent.activated` at Group 0 Step 0.0b per Stream C retrofit.
- **[Self-Healing OS-tier primitive (db0fd9b1)](../SELF-HEALING.md)** — composes with substrate-verify-twice (Path 0 verify-before-author via events.capsule schema discipline; Path 1 fix-on-see for catch-side; together close the messaging-substrate disease structurally per 9fc86533 §2).
- **[substrate-verify-twice defect-class brief (83af4ac1)](../../vault/files/83af4ac1.md)** — composes architecturally; events-as-canonical-truth removes the disease that substrate-verify-twice patches as a symptom.
- **[Workbench Surface Visibility Doctrine (3c02f3b7)](../../vault/files/3c02f3b7.md)** — composes; event log is the workbench. Active cycles + open conversations + in-flight substrate writes all become queryable surfaces.
- **[Captain's Briefing v3.0 (a5f4b26b)](../../vault/files/a5f4b26b.md)** — strategic frame; messaging substrate reframe is on the path to v2.0.0 "full lifecycle around a vault."
- **[Federation Foundation (7cac6473)](../../vault/files/7cac6473.md)** — L3 readiness composes; event substrate carries Studio-prefix identity at federation.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — this capsule's own governance; capsule amendments per meta-capsule discipline.
- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.

### History

Authored at the [history companion (63bf7487)](events.history.md) — v1.69 S3 split. Current + previous amendment notes stay in this file's frontmatter; older notes, the changelog, and extracted narratives live there.

---

## 11. Studio — Shop Signage

**Hot pitfalls (the two that recur):** emit + address agents at the PARTY UID, never the agent-root (Check 22; the message is otherwise invisible to a party-UID reader) · never edit the JSONL directly (Rule 1; append via the emit-event tool only).

Full signage — tools list, rules at-a-glance, all pitfalls, worked-example pointers — in the [history companion (63bf7487)](events.history.md). The live rules are §7; the live checks are §8.

---

## 12. How to Validate

*Required per pattern_exemplar (doc-spec.capsule.md §How to Validate).*

The capsule shipped at v1.55 and its acceptance tests passed (evidence in the [history companion (63bf7487)](events.history.md)). Current validation = the §8 checks live in `.tropo/scripts/lib/event_validators.py`, fired at every vault rebuild; emit-time enforcement = the emit-event tool guards (Rule 11 strictness + the Rule 4 axis guards).

---

## 13. Changelog

Full changelog (v1.0 → v1.4 rows verbatim) lives in the [history companion (63bf7487)](events.history.md). Current + previous version provenance: the `v1_7_amendment_note` + `v1_4_amendment_note` frontmatter fields above. v1.5 = member_of DISAMBIGUATE (hub membership moved to `subsystem_hub`; see §2 field table).

---

*events capsule definition | UID `72ef5ffe` | v1.7 LOCKED | v1.7 amendment 2026-06-13 by Talos T19 (receipt-ledger contract). History → companion `63bf7487`.*

*"One canonical event log. Drift becomes structurally impossible."*
