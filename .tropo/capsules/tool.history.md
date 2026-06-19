---
uid: 3dd22ace
name: "tool-history"
type: capsule-history
governs: d5e1b4a3
governs_path: .tropo/capsules/tool.capsule.md
extracted_at: 2026-05-11
extracted_by: argus-a56
extracted_in_cycle: "v1.19.0 — Convergence Phase 1"
extracted_in_release: pending-v1.19.0
schema_version: 2
governed_by: 5ec083a3
extraction_scope: argo-private
member_of:
  - "8dd772a0"
tags: [capsule-history, extracted-from-tool-capsule, v1.19.0-stream-c]
---

# tool — Capsule History

*History extracted from tool.capsule v1.4 → v1.5 body refactor (v1.19.0 Stream C; 2026-05-11). Active capsule preserves: 10-slot Required Frontmatter + conditional-required per transport (6 transports: mcp/action/http/platform/sa/cli), Required Body Sections (6) with synonyms, State Machine, 7 Governance Rules, 17 Validation Checks, Audit Record Shape. This file preserves: v0.1/v0.2/v1.0/v1.1/v1.3/v1.4 amendment-block prose, "why renamed" + "relationship to existing actions" + "relationship to siblings" + Inheritance-from-core narratives, 4-Phase Retrofit Rollout, all §Examples (3 worked YAMLs), §Studio Shop Signage, Relationship-to-Other-Capsules, Cross-References, full changelog.*

---

## Amendment Blocks (extracted)

### v1.4 (2026-05-09, Argus A53; LOCKED — v1.15 Stream A second cascade)

A53 OP 11 second-pass catch at Stream B start. Additive, non-breaking. Added `cli` transport enum value covering kernel scripts at `.tropo/scripts/<name>.py` invoked via subprocess. New conditionally-required fields under `transport: cli`: `cli_command:` (executable invocation string) + `script_path:` (vault-relative path). Validation Checks 4-6 updated to include cli transport. Why the cascade: Stream A's v1.3 amendment landed `trigger_description:` for catalog substrate, but Stream B's intent (kernel scripts get vault entries per Mike point #6 "scripts ARE tools") required a transport value that didn't exist in the v1.3 enum. Caught at first Stream B authoring attempt before any vault entry written. Same OP 11 discipline that produced the v1.3 amendment: brief authored without grepping the canonical capsule's transport enum; canonical wins. Locks atomically with v1.3 — no partial state.

### v1.3 (2026-05-09, Argus A53; LOCKED — v1.15 Stream A amendment)

Source brief: [1df4610d](../../vault/files/1df4610d.md); release plan [c7e4f9a2](../../vault/files/c7e4f9a2.md). Additive, non-breaking under `capsule_version: "1.3"` opt-in. Added optional `trigger_description:` field — hand-authored agent-facing prose answering "when does an agent reach for this tool?" The Tropo Tool Catalog (v1.15 ship at `.tropo/tool-catalog.md`) emits this verbatim alongside structural fields. Added optional `capsule_version:` opt-in marker. 1 new validation check (17) gated on opt-in: trigger_description ≥ 50 chars AND ≤ 600 chars. Pre-v1.3 tool entries grandfathered; v1.15 catalog generator filters on presence-of-trigger_description and emits WARNING for entries lacking it. A53 OP 11 catch: brief named this capsule as "new" — canonical reality is amend, not author.

### v1.1 (2026-04-25, Argus A34)

Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop). Added §Workshop — Shop Signage section per v3 capsule shop-signage pattern. Added Relations Header. Frontmatter `aligned_with: a7c3f489` + `composes_with: 9b7f5e34` + `pattern_family: a7c3f489` declared. No semantic changes.

### v1.0 (2026-04-20, Argus A28 + Mike Maziarz; LOCKED)

sa.cold-boot second pass ([record 034](../../agents/sa/sa.cold-boot/activation-log/034-argus-a28-record.md)) returned PASS — all 5 priority edits (G2, G5, G4, G6, G7) closed cleanly, zero regressions, zero new findings. Three-instrument verification complete. Third v1.2 Pillar 1 capsule shipped — Stream 1 Step 2 complete.

### v0.2 (2026-04-20, Argus A28)

sa.cold-boot first pass ([record 032](../../agents/sa/sa.cold-boot/activation-log/032-argus-a28-record.md), verdict PASS-WITH-GAPS — 0 blockers, 8 gaps, 3 notes) Priority-1 + Priority-2 remediation integrated. Priority 1: (G2) provenance-pair-is-one-slot clarification; (G5) scope preamble to Validation Checks stating checks apply only to `type: tool` files. Priority 2: (G4) Check 6 expanded with explicit per-transport `name` format expectations; (G6) `last_updated:` added to accepted-synonyms list; (G7) new §Audit Record Shape subsection.

### v0.1 (2026-04-20, Argus A28)

Initial DRAFT. Renamed from `mcp-tool.capsule.md` → `tool.capsule.md` per sa.research 021 recommendation + Mike approval 2026-04-20. One capsule, five transports (mcp/action/http/platform/sa). 10-slot required + conditional-required per transport. Tropo governance extensions (audit, writes_scope, destructive, spawnable_by at tool-level) beyond MCP schema. 4-phase non-breaking retrofit.

---

## "Why renamed from mcp-tool.capsule.md" (extracted)

sa.research's Record 021 (MIXED verdict, 2026-04-20) challenged the original naming: *"Naming the primitive after MCP concedes the moat. MCP is plumbing; Tropo is governance. The capsule should be `tool.capsule`, with MCP as one `transport:` value."* Approved by Mike 2026-04-20. Name updated before any draft locked.

---

## "Relationship to existing .tropo/actions/ infrastructure" (extracted)

- **10 existing action files** continue to function as kernel-tier verbs. They don't carry UIDs today (glob-discovered, path-addressed).
- **This capsule does not force-retrofit them.** Phase 1 keeps all 10 in their current state. Phase 3 opts high-value actions into first-class `tool` capsule entries with UID + registry presence.
- **The action file remains authoritative** for its six-section body; a `tool` capsule entry (when created) points at the action via `action_id:` and `target_capsule:` — it does NOT replace the action file.

---

## "Relationship to sibling Pillar 1 capsules" (extracted)

Three sibling typed primitives in Pillar 1:

| Capsule | What it governs | Invocation surface | I/O shape |
|---------|-----------------|---------------------|-----------|
| **session-agent** | Callable specialists (sa.\*) | `[PENDING]` in a record file | JSON via `input`/`output` schemas |
| **how-to** | Inline behavior bundles (skills) | Agent reads + executes in own context | Filesystem via `reads`/`writes` |
| **tool** (this) | Typed callables (any transport) | Varies by transport: MCP client, direct action invoke, HTTP request | JSON Schema `input`/`output` (MCP-compatible) |

Registry.jsonl treats all three as homogeneous rows distinguished by `type:` discriminator.

---

## Inheritance from core — explicit reconciliation (extracted)

Tool capsule entries live in the ledger at `vault/files/<uid>.md` when they're first-class tool entries (new pattern). Existing action files at `.tropo/actions/` remain kernel-tier artifacts, not ledger entries. Tool entries for external MCP tools and HTTP endpoints are ledger entries from creation.

Same core-field reconciliation as session-agent.capsule and how-to.capsule: `type` discriminator applies, `title` not required (name + domain serve the catalog), `updated` accepted as synonym for `modified`. **`last_updated:` is also accepted as a legacy synonym for `modified`** (v0.2 addition) — used by existing `.tropo/actions/*.action.md` files. **The validator for `tool` entries is THIS capsule's validation check list**, not core's.

---

## Retrofit Rollout — Phased, Non-Breaking (extracted)

### Phase 1 — Capsule ships, zero-break (v1.2)

- Publish this capsule.
- Existing 10 `.tropo/actions/*.action.md` continue to function as kernel-tier artifacts. No UIDs assigned. No `tool` entries created for them.
- No MCP tools registered yet (registry.jsonl not yet live).
- **Outcome:** capsule ready; no live tool entries; no breaking change.

### Phase 2 — Registry activation (2–4 weeks after lock)

- registry.jsonl populated from session-agent + how-to + tool frontmatter.
- First external MCP server registered in `.mcp.json` + first tool entries created with `transport: mcp`.

### Phase 3 — Opt-in action retrofit

- High-value actions (e.g., `create-project`, `commit-and-sync`) get first-class tool entries: UID assigned, tool capsule entry created with `transport: action` and `action_id` pointing at the existing action file.
- Low-value actions stay kernel-tier indefinitely.

### Phase 4 — Cut-over

- `output` JSON Schema + `audit_required` + `destructive` become REQUIRED for `status: active` tools in safety-sensitive categories.
- Any new tool born with full governance declarations.

---

## Examples (extracted — 3 worked YAML templates)

### Minimal — MCP tool

```yaml
---
uid: 1a2b3c4d
name: "linear.create_issue"
type: tool
status: active
owner: vela
domain: "Create a Linear issue in a specified team"
spawnable_by: [all-executives]
transport: mcp
mcp_server: linear
mcp_tool_name: create_issue
input: { $ref: ".tropo/schema/tool-linear-create_issue.input.json" }
created: 2026-04-20
created_by: vela-v31
---
```

### Minimal — Internal action (retrofit)

```yaml
---
uid: 2e4b6f8a
name: create-project
type: tool
status: active
owner: argus
domain: "Create a new project entry in the Vault with capsule-governed frontmatter"
spawnable_by: [all-executives]
transport: action
action_id: create-project
target_capsule: project
input:
 type: object
 required: [title, slug, owner]
 properties:
 title: { type: string }
 slug: { type: string }
 owner: { type: string }
 description: { type: string }
 member_of: { type: array, items: { type: string } }
writes_scope: ["vault/files/**"]
governance_category: create
created: 2026-04-20
created_by: argus-a28
---
```

### Full — MCP tool with Tropo governance

```yaml
---
uid: 3f5c8d1e
name: "slack.post_message"
type: tool
status: active
owner: vela
domain: "Post a message to a Slack channel via the organization's Slack workspace"
spawnable_by: [vela, fleet-ops]
transport: mcp
mcp_server: slack
mcp_tool_name: post_message
input:
 type: object
 required: [channel, text]
 properties:
 channel: { type: string, description: "Slack channel ID or name" }
 text: { type: string, description: "Message body" }
 thread_ts: { type: string, description: "Parent thread timestamp for replies" }
output:
 type: object
 properties:
 ts: { type: string }
 channel: { type: string }
destructive: true
audit_required: true
audit_redact: []
writes_scope: []
governance_category: create
domain_tags: [messaging, external, slack, communication]
description: "Posts a message to Slack. External side effect. Audit logged. spawnable_by is narrowed to Vela + fleet-ops to prevent uncontrolled external posts."
created: 2026-04-20
created_by: vela-v31
---
```

---

## Studio — Shop Signage (extracted)

*Preserved per Mike-A55 directive: capsules are agent-read, not human-read.*

### Tools available

- `ls .tropo/actions/*.action.md` — survey internal actions
- `cat .mcp.json` — list registered MCP servers
- `vault/00-index.jsonl` — grep `type: tool` to enumerate registered tool entries
- `.tropo-studio/registries/registry.jsonl` — tool registry projection for sub-second lookups
- `.tropo/schema/tool-<name>.input.json` / `tool-<name>.output.json` — JSON Schema files for `$ref:` references

### Skills

- `register-tool.skill.md` *(forthcoming v1.5)* — scaffold tool vault entry with 10 REQUIRED slots + transport-conditional fields
- `audit-tool-invocations.skill.md` *(forthcoming v1.5)* — verify `audit_required: true` tools are emitting audit records

### Procedures

- **Register an external MCP tool** — confirm server in `.mcp.json`; assign UID; author tool entry with `transport: mcp` + `mcp_server` + `mcp_tool_name`; `name:` follows `<mcp_server>.<mcp_tool_name>` convention OR re-namespaces; `input:` `$ref`s MCP server's inputSchema
- **Register an internal action as a tool** — author with `transport: action` + `action_id` + `target_capsule`; `name:` MUST equal `action_id`; tool entry POINTS at action file (Rule 6)
- **Register an HTTP endpoint** — `transport: http` + `http_endpoint:` URL + `http_method:` verb; `name:` recommended `<domain>.<operation>`
- **Register a platform endpoint** — `transport: platform` + `platform_route:`; `name:` matches route intent
- **Register a sa.\* dispatch** — `transport: sa` + `sa_name:` (resolves to active sa.\*)
- **Verify required body sections** — 6 sections (Intent / Invocation Protocol / Input/Output / Governance / Verification / Failure Modes) or synonyms
- **Activate — `draft → active`** — Phase 1 governance: only `active` tools are registry-visible
- **Compose with `audit_required:`** — every invocation MUST emit audit record per §Audit Record Shape; append-only
- **Compose with `destructive: true`** — drives confirmation prompts in interactive harnesses
- **Migrate / supersede** — author successor at `active` with `supersedes:`; predecessor flips `superseded` + `superseded_by:` (bidirectional)

### Pitfalls

- MCP tool with `name` not matching `<mcp_server>.<mcp_tool_name>` AND no explicit re-namespace → Check 6 violation
- Tool with conditional-required field missing for declared `transport:` → Check 5 violation
- `audit_required: true` without §Governance documenting the audit trail → Check 14 violation
- `destructive: true` without §Governance explaining side effects → Check 15 violation
- Tool `writes_scope:` outside target folder's AGENTS.md → Rule 4 / Check 13 violation
- Hand-editing `registry.jsonl` → Rule 7 violation; rebuild from frontmatter
- Confusing tool with action — `type: tool, transport: action` SURFACES an action as a typed callable; `type: action-definition` IS the action substrate (governed by action.capsule)
- Treating MCP as the primitive — naming concedes the moat
- Tool entry missing UID registration → Check 10 violation
- Tool at `active` without all 6 body sections → Check 12 violation

### Worked examples (see history §Examples)

- Minimal MCP tool — `linear.create_issue` template
- Minimal Internal action retrofit — `create-project` with `transport: action`
- Full MCP tool with Tropo governance — `slack.post_message` with `destructive: true`, `audit_required: true`

### Go next

- Sibling Pillar 1 callable specialists → [session-agent.capsule (b4e2a718)](session-agent.capsule.md)
- Sibling Pillar 1 inline behaviors → [how-to.capsule (a7c3f489)](how-to.capsule.md)
- Composed substrate → [action.capsule (9b7f5e34)](action.capsule.md)
- MCP integration → `.mcp.json` + Tropo platform's MCP registry
- Harness-awareness research → [(5302ec94)](../../library/docs/agent-harness-awareness-research.md) Part 5
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Relationship to Other Capsules — Narrative (extracted)

- **[session-agent.capsule (b4e2a718)](session-agent.capsule.md)** — sibling typed primitive (internal specialists). ~70% frontmatter overlap. Cross-capsule discriminator alignment planned for v1.1 (session-agent gains `type: session-agent` alongside `class:` as legacy synonym).
- **[how-to.capsule (a7c3f489)](how-to.capsule.md)** — sibling typed primitive (inline skill). Same three-primitive Pillar 1 ensemble. Skills CAN invoke tools; tools do not invoke skills.
- **[core.capsule.md](core.capsule.md)** — extended with explicit reconciliation.
- **Existing `.tropo/actions/*.action.md`** — not governed by this capsule. Action files stay kernel-tier. Tool entries with `transport: action` point at them but don't replace them.

---

## Cross-References (extracted)

- [Agent Harness Awareness research memo (5302ec94)](../../library/docs/agent-harness-awareness-research.md) — Part 2 (MCP convergence) and Part 5 ("Tropo sits above MCP")
- [Capabilities Matrix v2.0 (c4a9f2b1)](../../vault/files/c4a9f2b1.md) — Row 8 L1
- [Stack Architecture v1.0 (f3c7a291)](../../vault/files/f3c7a291.md) — tools are part of L1 Tropo's Tool plane
- [sa.research record 021](../../agents/sa/sa.research/activation-log/021-mcp-tool-capsule-patterns.md) — inventory + one-capsule-many-transports recommendation
- Full inventory at [workspace/021-mcp-tool-inventory.md](../../agents/sa/sa.research/workspace/021-mcp-tool-inventory.md)

---

## Changelog (full lineage)

| Version | Date | Change | Author |
|---|---|---|---|
| 0.1 | 2026-04-20 | Initial DRAFT. Renamed from `mcp-tool.capsule.md` → `tool.capsule.md` per sa.research 021 + Mike approval. One capsule, five transports (mcp/action/http/platform/sa). 10-slot required + conditional-required per transport. Tropo governance extensions. 4-phase non-breaking retrofit. | Argus A28 |
| 0.2 | 2026-04-20 | sa.cold-boot first pass PASS-WITH-GAPS — Priority-1 + Priority-2 remediation integrated. G2, G5, G4, G6, G7 closed. Priority-3 polish deferred. | Argus A28 |
| 1.0 | 2026-04-20 | LOCKED. sa.cold-boot second pass PASS — all 5 priority edits closed cleanly, zero regressions. Three-instrument verification complete. Stream 1 Step 2 complete. | Argus A28 + Mike Maziarz |
| 1.1 | 2026-04-25 | Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop). Added §Workshop — Shop Signage section. Added Relations Header. Frontmatter `aligned_with: a7c3f489` + `composes_with: 9b7f5e34` + `pattern_family: a7c3f489`. No semantic changes. | argus-a34 |
| 1.3 | 2026-05-09 | LOCKED — v1.15 Stream A amendment (source brief 1df4610d). Additive non-breaking under `capsule_version: "1.3"` opt-in. Added optional `trigger_description:` field. Added optional `capsule_version:` opt-in marker. 1 new validation check (17) gated on opt-in. A53 OP 11 catch: brief named as "new" — canonical reality is amend. | argus-a53 |
| 1.4 | 2026-05-09 | LOCKED — v1.15 Stream A second cascade. Additive non-breaking. Added `cli` transport enum value. New conditionally-required fields under `transport: cli`: `cli_command:` + `script_path:`. Validation Checks 4-6 updated. A53 OP 11 second-pass catch. Locks atomically with v1.3. | argus-a53 |
| 1.5 | 2026-05-11 | **v1.19.0 Stream C — Capsule Pedagogy Completion.** Body refactor to 5-section pedagogy pattern (Intent → Schema → State Machine → Validation Rules → Composes-With) per Mike-A55 *"capsules are agent-read, not human-read"* directive. Active body reduced from 503 → ~260 lines (~48% reduction). Substrate-load-bearing content preserved in active: 10-slot Required Frontmatter + conditional-required per 6 transports, Required Body Sections (6) with synonyms, State Machine, 7 Governance Rules, 17 Validation Checks, Audit Record Shape. Extracted to history: amendment-block opener prose, why-renamed narrative, relationship-to-actions narrative, sibling-Pillar-1 narrative, Inheritance-from-core reconciliation, 4-Phase Retrofit Rollout, all §Examples (3 worked YAMLs), §Studio quick-ref, Relationship-to-Other-Capsules narrative, Cross-References, full changelog. **No schema changes.** UID `d5e1b4a3` preserved. | argus-a56 |

---

## Provenance

- **Extracted at:** 2026-05-11
- **Extracted by:** argus-a56
- **Active capsule version at extraction:** v1.4 (503 lines)
- **Active capsule version after extraction:** v1.5 (~260 lines; ~48% reduction)

---

*tool capsule history | UID 3dd22ace | v1.19.0 Stream C extraction 2026-05-11 by Argus A56 | Bidirectional pair: governs d5e1b4a3*
