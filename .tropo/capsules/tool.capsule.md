---
uid: d5e1b4a3
name: "tool"
type: capsule-definition
extends: core
version: "1.7"
supersedes_version: "1.6"
tier: os
author: argus
created: 2026-04-20
modified: 2026-06-01
modified_by: talos-t12
created_by: argus-a28
status: locked
locked_by: argus-a53
locked_at: 2026-05-09
enforced_enums:
  status: [draft, active, deprecated, superseded]
meta_status_rollup:
  to-do: [draft]
  in-progress: [active]
  done: [deprecated, superseded]
last_body_refactor: 2026-05-26
history_file: 3dd22ace
v1_7_amendment_note: "v1.6 → v1.7 amendment 2026-06-01 by Talos T12 per dev-spec b7d4f1a9 (tool-discovery-l1 cycle). Two new validation checks: (1) name != uid — a tool MUST carry a logical name, not just repeat its UID as the name field; WARN at v1.64, ERROR-ratchet at v1.65. (2) cli_command non-empty for transport:cli — refines Check 5 (field-presence) to value-non-empty; same ratchet. Also adds transport:library as a valid transport enum value (for pure shared-library modules like office_styles that are imported, not invoked). Triggered by: 5 uid-only tools identified by tropo.py doctor (09ef9843, 0f3078fe, 1056eec5, ce9dbcc2, d1f2420d) — all backfilled with logical name: fields this cycle, clearing the doctor's uid-only backlog to 0. These checks make the findable-surface discipline structural: a tool with name==uid shows up as a validator WARN, not just a doctor advisory."
v1_6_amendment_note: "v1.5 → v1.6 amendment 2026-05-26 by Argus A84 captain-mode per Mike-A84 taxonomy walk + Pillar 1 single-file-truth reshape decision. Adds canonical file-layout pattern at vault/tools/<uid>.{py|md|json} (single-file truth: tool entry IS the implementation; YAML frontmatter embedded in leading docstring/comment block for Python; standalone .md or .json for non-python implementation_kinds). Deprecates sidecar pattern (vault/files/<uid>.md + script_path: pointer at .tropo/scripts/) for new tool authoring; v1.56 cycle migrates ~22 existing sidecar-pattern instances to single-file at vault/tools/<uid>.{py|md|json}. Composes with v1.56 cycle scope: registration completion (~15-20 unregistered .tropo/scripts/) + single-file reshape migration + Rule 14 retirement in release.capsule v3.7. Pillar 1 sibling cycles (v1.57 how-tos-in-vault + v1.58 session-agents-in-vault + v1.59 actions-in-vault) follow same single-file pattern per their respective capsules' v1.X amendments. No schema field changes beyond canonical-file-layout codification + deprecation note on sidecar pattern. v1.5 transport enum + 10 required slots + 17 validation checks unchanged - existing entries migrate by file-relocation only, not schema rewrite."
schema_version: 2
governed_by: 222873b9
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — 5-section pedagogy
aligned_with: a7c3f489       # how-to.capsule — sibling Pillar 1
composes_with: 9b7f5e34      # action.capsule — actions wrappable as tools via transport: action
pattern_family: a7c3f489     # Pillar 1 callable surfaces
member_of:
  - "8dd772a0"
tags: [capsule-definition, tool, pillar-1, 5-section-pedagogy, v1.19.0-stream-c-refactored, v1.6-single-file-truth, v1.56-foundation]
---

# tool — Capsule Definition v1.5

## 1. Intent

A tool is a typed callable with JSON Schema I/O and explicit invocation transport. Tropo's universal tool primitive — governs internal `.tropo/actions/`, external MCP tools, HTTP endpoints, platform APIs, sa.* dispatches, and kernel scripts uniformly.

Tools can be:

- **Internal actions** (existing `.tropo/actions/*.action.md`) — kernel-tier verbs that create vault artifacts
- **External MCP tools** — exposed by MCP servers registered in `.mcp.json`
- **HTTP endpoints** — external REST/GraphQL APIs Tropo reaches over HTTP
- **Platform endpoints** — Tropo's own platform (Next.js application) exposing capabilities
- **sa.\* dispatches** — callable session agents, invoked via the sa.\* protocol
- **CLI scripts** — kernel scripts at `.tropo/scripts/<name>.py` invoked via subprocess

All six share every governance concern: UID addressing, permission scope, audit hooks, JSON Schema I/O, registry discovery. They differ only in `transport:` — how invocation reaches the implementation. **One capsule. One registry row shape. Six transports.**

**Guiding principle:** *"Codification, not invention. Tropo sits above MCP."* MCP is one transport value; Tropo is the governance layer above. The capsule adds Tropo's governance (UID, permissioning, audit, per-tool scope) over MCP's transport-only surface.

Failure mode prevented: callable substrate fragmenting across multiple typed surfaces (mcp-tool / action / http-endpoint / sa.-dispatch each as a separate capsule) with parallel governance + drift; or callable substrate accreting under MCP's transport-only schema and losing the Tropo moat (UID, audit, write_scope, governance_category).

---

## 2. Schema

### Required Frontmatter (10 slots, in addition to core)

The 10 slots: `uid`, `name`, `type`, `status`, `owner`, `domain`, `spawnable_by`, `transport`, `input`, provenance-pair (`created`+`created_by` OR legacy `commissioned`+`commissioned_by`).

| Field | Type | Constraint |
|---|---|---|
| `uid` | string (8-hex) | Registry key. Tropo moat. |
| `name` | string | Dispatch name. Format depends on transport (see Check 6). |
| `type` | string | Must be `"tool"`. Type discriminator for registry filtering. |
| `status` | enum | `draft` / `active` / `deprecated` / `superseded` |
| `owner` | string | Executive/role who registered the tool. Even for external MCP tools, ownership is Tropo-side. |
| `domain` | string | One-sentence "what this tool does." ≤160 chars. Human-readable catalog entry. |
| `spawnable_by` | YAML array | Who can invoke the tool. Values: `["all-executives"]`, specific agents, role tags. Array form preferred. |
| `transport` | enum | `mcp` / `action` / `http` / `platform` / `sa` / `cli`. Drives conditional-required fields below. **(v1.4 addition):** `cli` covers kernel scripts at `.tropo/scripts/<name>.py` invoked via subprocess. |
| `input` | JSON Schema (inline or `$ref`) | Structured input. May reference `.tropo/schema/tool-<name>.input.json`. MCP tools: can `$ref` the MCP server's `inputSchema` directly. |
| provenance-pair | date + string | `created` + `created_by` OR legacy `commissioned` + `commissioned_by` OR legacy `last_updated` for `.tropo/actions/*` retrofit. |

### Conditionally Required Frontmatter (by transport)

| Transport | Required fields |
|---|---|
| `mcp` | `mcp_server` (server name from `.mcp.json`) + `mcp_tool_name` (server-side tool name) |
| `action` | `action_id` (links to `.tropo/actions/<id>.action.md`) + `target_capsule` (which capsule type this action instantiates) |
| `http` | `http_endpoint` (URL) + `http_method` (HTTP verb) |
| `platform` | `platform_route` (path into Tropo platform; e.g., `/api/research/run`) |
| `sa` | `sa_name` (e.g., `sa.cold-boot`; MUST resolve to registered sa.* with `status: active`) |
| `cli` | `cli_command` (executable invocation string with vault-relative path) + `script_path` (vault-relative path to implementation; e.g., `.tropo/scripts/validate-canonical-l0.py`) |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `output` | JSON Schema | Structured output. SHOULD include `verdict` or `status` enum field. Phase 4 target: required. |
| `destructive` | boolean | True if invocation has side effects that can't be easily reversed. Drives confirmation prompts. |
| `writes_scope` | path-glob array | Declarative side-effect manifest — paths this tool may write. Cross-checked against AGENTS.md write-scope. |
| `audit_required` | boolean | Tropo-only extension. When true, every invocation emits an audit line. For security-sensitive operations. |
| `audit_redact` | string array | Input field names to redact from audit records. |
| `governance_category` | enum | `create` / `read` / `update` / `delete` / `lifecycle` / `query`. Registry filter. |
| `description` | string | One-paragraph expansion for registry display. ≤400 chars. |
| `domain_tags` | string array | Machine-readable tags for discovery. |
| `version` | semver | For versioned tools. |
| `triggers` | string array | When this tool should be suggested/auto-invoked. |
| `supersedes` / `superseded_by` | UID | Bidirectional pair for supersession. |
| `invocation_examples` | object array | `{input, expected_output}` pairs for cold-boot verification. |
| `mcp_server_capabilities` | object | For MCP tools, the server's declared capabilities (cached). |
| `trigger_description` | string | **v1.3 — required under `capsule_version: "1.3"` opt-in.** Hand-authored agent-facing prose answering "when does an agent reach for this tool?" Distinct from `domain:` (shorthand what-it-does) and `description:` (registry-display expansion). Min 50 chars, max 600 chars. Catalog generator emits verbatim. |
| `capsule_version` | string | **v1.3 opt-in marker.** Values: `"1.3"`. When absent, instance treated as MIGRATION-PENDING pre-v1.3 (Check 17 does NOT fire). |

### Required Body Sections (6, with synonyms)

Every `status: active` tool entry MUST document these intents. Synonyms accepted per the sibling Pillar 1 pattern.

1. **Intent** (synonym: Purpose) — one paragraph. What the tool does, when to invoke, when NOT to invoke.
2. **Invocation Protocol** (synonym: Usage) — how the tool is called. For MCP: `input` JSON Schema + MCP server connection. For action: Process/Template from action file. For http: request construction.
3. **Input / Output** (synonym: Schema) — canonical schema + example calls. If frontmatter `input`/`output` inline, may cross-reference; otherwise documents in prose.
4. **Governance** (synonym: Permissions) — permission scope, audit behavior, `writes_scope` rationale, destructive-flag reasoning. **THIS IS THE TROPO-SPECIFIC SECTION** — MCP has no equivalent.
5. **Verification** (synonym: Success) — how caller confirms successful invocation.
6. **Failure Modes** (synonym: Errors) — failure table.

For `status: draft`: only Intent required.

### Audit Record Shape

When `audit_required: true`, the harness or Librarian MUST emit an audit record on each invocation. Minimum fields:

| Field | Type | Purpose |
|---|---|---|
| `timestamp` | ISO 8601 datetime | When invocation occurred |
| `tool_uid` | 8-hex string | The tool's UID (registry key) |
| `tool_name` | string | Dispatch name (for human readability) |
| `invoker` | string | Agent ID that invoked |
| `input_digest` | string | SHA-256 hash of input AFTER `audit_redact` field removal |
| `outcome` | enum | `success` / `failure` / `timeout` / `denied` |

Audit destination: append-only vault audit log (canonical location: `channels/audit.md` or structured `audit.jsonl`; final destination TBD by Vela during Librarian implementation in v1.3+). Until Librarian ships, `audit_required: true` tools SHOULD emit a line to `channels/ops.md` as placeholder.

---

## 2.5 Canonical File Layout (v1.6 NEW)

Tool entries follow single-file-truth at `vault/tools/<uid>.{py|md|json}`. The tool entry file IS BOTH the governance entry AND the implementation. UID-as-filename indexed in `vault/00-index.jsonl` per Pillar 1 vault-citizenship pattern. Cold-boot agent invocation pattern: query 00-index for tool by name → get UID + path → invoke per `implementation_kind`. Composes with v1.56 cycle's Pillar 1 single-file-truth migration; replicated by sibling Pillar 1 cycles (v1.57 how-to + v1.58 session-agent + v1.59 action) per same canonical-file-layout discipline.

### File extension per implementation_kind

| `implementation_kind` | Canonical path | Format |
|---|---|---|
| `python-script` (`transport: cli` with Python script) | `vault/tools/<uid>.py` | Python file; YAML frontmatter in leading docstring block (`"""---\n...\n---\n"""`) parsed by rebuild-vault.py extension; Python implementation follows below closing `---` |
| `external-cli` (`transport: cli` without Python wrapper) | `vault/tools/<uid>.md` | Standard markdown frontmatter; body documents `cli_command`, `arg_spec` examples, governance notes |
| `mcp-tool` (`transport: mcp`) | `vault/tools/<uid>.json` | JSON manifest with embedded `tropo_metadata:` field carrying capsule-required frontmatter fields; remainder is canonical MCP server tool descriptor |
| `transport: action` | `vault/tools/<uid>.md` | Standard markdown frontmatter pointing at action via `action_id:` (action body remains at `.tropo/actions/<id>.action.md` until v1.59 action-in-vault cycle) |
| `transport: http` | `vault/tools/<uid>.md` | Standard markdown frontmatter with `http_endpoint:` + `http_method:` |
| `transport: platform` | `vault/tools/<uid>.md` | Standard markdown frontmatter with `platform_route:` |
| `transport: sa` | `vault/tools/<uid>.md` | Standard markdown frontmatter with `sa_name:` (session-agent activation file remains at `agents/sa/sa.<slug>/sa.<slug>.md` until v1.58 session-agent-in-vault cycle) |

### Python-script docstring frontmatter format

For `python-script` entries, the leading docstring carries YAML frontmatter between fenced `---` markers, parsed by rebuild-vault.py extension (v1.56 Talos engineering scope):

```python
"""---
uid: a3f1b829
name: rebuild-vault
type: tool
transport: cli
implementation_kind: python-script
... (full capsule v1.6 frontmatter)
---"""

# Python implementation follows below
import sys
...
```

Frontmatter parser convention: extract text between first `"""---` and matching `---"""`; parse as YAML; remaining file content is Python implementation. rebuild-vault.py extension specified in v1.56 dev-spec.

### Sidecar pattern - DEPRECATED for new authoring (v1.6)

Pre-v1.6 tool entries used a sidecar pattern: vault entry at `vault/files/<uid>.md` with `script_path: .tropo/scripts/<name>.py` pointing at kernel-tier implementation. ~22 existing instances follow this pattern.

**v1.6 deprecates sidecar pattern for new tool authoring.** New tools authored at v1.6+ use single-file-truth at `vault/tools/<uid>.{ext}` per the table above. v1.56 cycle migrates the ~22 existing sidecar instances to single-file via path-relocation + frontmatter embedding (mechanical migration; no schema rewrite needed).

**Why deprecate:** sidecar pattern creates drift class (vault entry frontmatter vs script implementation can desync; validator must cross-check). Single-file truth eliminates the drift by construction. Composes with Self-Healing OS-tier primitive + substrate-discipline-becomes-structurally-enforced thesis at the mechanical-capability layer.

**Migration discipline (v1.56 cycle scope):**
1. Move `.tropo/scripts/<name>.py` → `vault/tools/<uid>.py` (UID matches the existing vault/files/<uid>.md sidecar's UID)
2. Embed sidecar frontmatter into Python docstring at top of relocated `.py` file
3. Recycle the sidecar entry at `vault/files/<uid>.md` via tropo-recycle.py per Preservation Discipline
4. Update all invocation paths across capsules + playbooks + how-tos + agent docs that reference `.tropo/scripts/<name>.py`
5. Update `script_path:` field semantics in vault index renderer to point at `vault/tools/<uid>.py` if preserved as historical/audit attribute; OR retire the field entirely
6. Composes with Rule 14 retirement in release.capsule v3.7 → v3.8 (Rule 14 path-pattern table becomes redundant once tools have proper `member_of:` graph citizenship at canonical vault location)

### Agent invocation pattern (cold-boot-friendly)

```
1. grep '"name":"<tool-name>"' vault/00-index.jsonl  → get UID
2. read vault/tools/<uid>.{py|md|json}              → get implementation kind + path/command
3. invoke per implementation_kind:
   - python-script:  python3 vault/tools/<uid>.py [args]
   - external-cli:   <cli_command with arg substitution>
   - mcp-tool:       MCP invocation via mcp_server + mcp_tool_name
   - http:           HTTP request to <http_endpoint>
   - platform:       Tropo platform route invocation
   - sa:             sa.* commissioning per sa/CAPSULE.md protocol
```

Optional thin CLI wrapper at `vault/tools/<uid>.py` named `tropo-tool` (v1.57+ candidate; not v1.0 scope) reduces typing for human + script use: `tropo-tool <name> [args]` resolves UID + invokes per implementation_kind without manual lookup.

---

## 3. State Machine

```
draft → active → deprecated → superseded
```

Canonical status enum: `status:` ∈ {draft, active, deprecated, superseded}

Mirrors session-agent.capsule and how-to.capsule.

| Status | Meaning |
|---|---|
| `draft` | Tool being authored. Only Intent body section required. |
| `active` | Tool committed. All 6 required body sections present. Registry-visible. |
| `deprecated` | Tool no longer recommended; legacy callers still work but new callers should use successor. |
| `superseded` | Tool retired; `superseded_by:` set; bidirectional pair with successor's `supersedes:`. |

---

## 4. Validation Rules

**Scope preamble:** Validation checks apply only to files with `type: tool` frontmatter — i.e., vault entries that are formal tool-capsule instances. Existing `.tropo/actions/*.action.md` files without `type: tool` frontmatter are kernel-tier infrastructure and out of scope; governed by their folder's AGENTS.md. When an action opts into first-class tool entry at Phase 3, a new vault entry with `type: tool` is created — that entry is then subject to these checks.

### Governance Rules (7, in addition to core)

1. **One tool entry per (transport, name) pair.** Duplicates are violations.
2. **`audit_required: true` is enforceable.** Harness/Librarian MUST emit audit record on each invocation. Agents may not skip.
3. **`destructive: true` requires explicit caller intent.** Harness prompts, playbook declarations, or similar. Capsule is governance-declarative; enforcement is harness-side.
4. **`writes_scope:` declarations are governance-validated.** Cross-checked against AGENTS.md write-scope of target folders at check-in. A tool that writes outside its declared scope is a violation.
5. **MCP tools require a registered `mcp_server`.** Server must appear in `.mcp.json` (or platform's MCP registry) for the tool to be `status: active`.
6. **Action tools point at, but do not replace, action files.** `.tropo/actions/<id>.action.md` remains authoritative body; tool entry is the registry face.
7. **Registry writes are generated, not hand-edited.** `registry.jsonl` entries are produced by the registry builder.

### Validation Checks (17, ERROR-severity at check-in)

1. All 10 required frontmatter slots present with correct types
2. `type` equals `"tool"`
3. `status` ∈ {`draft`, `active`, `deprecated`, `superseded`}
4. `transport` ∈ {`mcp`, `action`, `http`, `platform`, `sa`, `cli`}
5. Conditional required fields present based on `transport`:
   - `mcp` → `mcp_server` + `mcp_tool_name`
   - `action` → `action_id` + `target_capsule`
   - `http` → `http_endpoint` + `http_method`
   - `platform` → `platform_route`
   - `sa` → `sa_name` (resolves to registered sa.* with `status: active`)
   - `cli` → `cli_command` + `script_path` (path resolves to existing file)
6. `name` format validation per transport:
   - `mcp` → `name` matches `<mcp_server>.<mcp_tool_name>` OR explicit re-namespace via distinct `name:` (`mcp_tool_name:` preserves upstream identifier)
   - `action` → `name` equals `action_id`
   - `http` → caller-chosen; recommended `<domain>.<operation>`
   - `platform` → matches route intent (e.g., `platform.research.run`)
   - `sa` → `name` equals `sa_name` (`sa.<slug>` form)
   - `cli` → `name` equals script filename stem (no `.py`/`.sh` extension)
7. `input` is valid JSON Schema (inline or resolvable `$ref`)
8. If `output` present: valid JSON Schema; `verdict`/`status` enum recommended
9. `spawnable_by` is YAML array or bare string; values resolve
10. `uid` registered in `registry.jsonl`; reverse lookup matches `name`
11. Provenance pair present
12. For `status: active`: body contains all 6 required sections (Intent / Invocation Protocol / Input-Output / Governance / Verification / Failure Modes) or synonyms
13. If `writes_scope` present: paths exist or are well-formed globs; no conflict with target folder AGENTS.md write-scope
14. If `audit_required: true`: §Governance body section documents what gets audited
15. If `destructive: true`: §Governance body section explains side effects
16. If `supersedes` / `superseded_by` present: referenced UIDs resolve
17. **(v1.3; gated on `capsule_version: "1.3"`)** `trigger_description:` present, ≥50 chars, ≤600 chars. Pre-v1.3 entries grandfathered.

Core checks inherited: UID uniqueness + immutability, type immutability, provenance invariants.

---

## 5. Composes-With

- **[session-agent.capsule (b4e2a718)](session-agent.capsule.md)** — sibling Pillar 1 typed primitive (internal specialists). ~70% frontmatter overlap. sa.* surface as tools via `transport: sa`.
- **[how-to.capsule (a7c3f489)](how-to.capsule.md)** — sibling Pillar 1 typed primitive (inline skill). `pattern_family` reference. Skills CAN invoke tools; tools do not invoke skills.
- **[action.capsule (9b7f5e34)](action.capsule.md)** — composed substrate. Actions surface as tools via `transport: action`. Tool entry POINTS at action file via `action_id:`; does not replace action file (Rule 6).
- **[core.capsule (ee814120)](core.capsule.md)** — extended (with `last_updated:` accepted as legacy synonym for `modified:` for `.tropo/actions/*` retrofit).
- **Existing `.tropo/actions/*.action.md`** — not governed by this capsule. Action files stay kernel-tier (Phase 1). Tool entries with `transport: action` point at them but don't replace them.
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.
- **`.mcp.json` + Tropo platform's MCP registry** — runtime sources for `transport: mcp` tools. Server must be registered for the tool to be `status: active` (Rule 5).
- **`.tropo-studio/registries/registry.jsonl`** — runtime callable catalog. Tools project here per [e2f7d195](../../vault/files/e2f7d195.md). Registry writes generated, not hand-edited (Rule 7).
- **[`.tropo/tool-catalog.md`](../tool-catalog.md)** — v1.15 ship surface. Catalog generator emits `trigger_description:` (v1.3 field) verbatim alongside structural fields.

### History

The v0.1/v0.2/v1.0/v1.1/v1.3/v1.4 amendment-block opener prose, the "why renamed from mcp-tool.capsule.md" narrative, the "relationship to existing .tropo/actions/" narrative, the "relationship to sibling Pillar 1 capsules" narrative, the Inheritance-from-core explicit reconciliation, the 4-Phase Retrofit Rollout, all three §Examples worked YAMLs (minimal MCP / minimal action retrofit / full MCP+governance), the full §Studio — Shop Signage authoring procedure, the Relationship-to-Other-Capsules narrative, the Cross-References block, and the full changelog are preserved in the companion [tool.history.md (3dd22ace)](tool.history.md) governed by `capsule-history.capsule` (5ec083a3).

---

*tool capsule definition | LOCKED v1.6 | history at [tool.history.md](tool.history.md) | v1.6 amendment 2026-05-26 by Argus A84 captain-mode (v1.56 Pillar 1 single-file-truth reshape foundation - adds §2.5 Canonical File Layout specifying vault/tools/<uid>.{py|md|json} pattern + Python docstring frontmatter format + sidecar deprecation for new authoring + migration discipline; pairs with Mike-A84 taxonomy walk decisions during 2026-05-26 walk-period; composes with Pillar 1 sibling cycle pattern v1.57 how-to + v1.58 session-agent + v1.59 action). v1.5 body refactor 2026-05-11 by Argus A56 (v1.19.0 Stream C — 5-section pedagogy pattern; agent-read-not-human-read per Mike-A55). Prior v0.1–v1.4 locks preserved in history. UID `d5e1b4a3` preserved.*
*"One capsule. Six transports. Tropo sits above MCP. Single-file truth in the vault graph."*
