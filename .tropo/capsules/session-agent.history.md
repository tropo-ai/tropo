---
uid: 709efecd
name: "session-agent-history"
type: capsule-history
governs: b4e2a718
governs_path: .tropo/capsules/session-agent.capsule.md
extracted_at: 2026-05-11
extracted_by: argus-a56
extracted_in_cycle: "v1.19.0 — Convergence Phase 1"
extracted_in_release: pending-v1.19.0
schema_version: 2
governed_by: 5ec083a3
extraction_scope: argo-private
member_of:
  - "8dd772a0"
tags: [capsule-history, extracted-from-session-agent-capsule, v1.19.0-stream-c]
---

# session-agent — Capsule History

*History extracted from session-agent.capsule v1.4 → v1.5 body refactor (v1.19.0 Stream C; 2026-05-11). Active capsule preserves: 8 required frontmatter slots, optional frontmatter, 6 Required Body Sections with synonyms, State Machine, 7 Governance Rules, 18 Validation Checks, 4-Phase Retrofit Rollout, Inheritance-from-core reconciliation. This file preserves: v0.1-v1.4 amendment-block prose, Phase 1 vs Phase 4 framing, relationship-to-existing-sa-infrastructure narrative, 2 worked YAML examples (minimal Phase 1 + full Phase 2+ typed), §Studio quick-ref, Relationship-to-Other-Capsules, Cross-References, full changelog.*

---

## Amendment Blocks (extracted)

### v1.4 (2026-05-09, Argus A53; LOCKED — v1.15 Stream A amendment)

Source brief: [1df4610d](../../vault/files/1df4610d.md); release plan [c7e4f9a2](../../vault/files/c7e4f9a2.md). Additive non-breaking under `capsule_version: "1.4"` opt-in. Added optional `trigger_description:` field — hand-authored agent-facing prose answering "when does an agent reach for this sa.\*?" The Tropo sa.\* Agent Catalog (v1.15 ship at `.tropo/sa-agent-catalog.md` — Mike user-facing filename per mirror-Claude-Code lock 2026-05-09; underlying schema type is `session-agent`) emits this verbatim alongside structural fields per Q2 hybrid catalog generation lock. Added optional `capsule_version:` opt-in marker. 1 new validation check (18) gated on opt-in. A53 OP 11 catch: brief named this capsule as "sa-agent.capsule (new)" — canonical reality is `session-agent.capsule` (codified at v1.0 2026-04-20) so amendment, not authoring.

### v1.3 (2026-04-27, Argus A37 — registry-reference scrub)

Frontmatter `version:` advanced from 1.2 → 1.3 by argus-a37 during the registry-topology consolidation work. Body changelog row was not appended at the time (drift between frontmatter version and body changelog). No semantic contract changes — reference-hygiene only. Backfill row added at v1.4 lock 2026-05-09 by argus-a53.

### v1.2 (2026-04-25, Argus A34)

Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop). Added §Workshop — Shop Signage section. Added Relations Header. Frontmatter `aligned_with: 7d3f9a2c` + `composes_with: a7c3f489` + `pattern_family: a7c3f489` declared. No semantic changes.

### v1.1 (2026-04-20)

Additive non-breaking amendment for cross-capsule discriminator alignment with how-to.capsule v1.0 + tool.capsule v1.0. v1.1 accepts **either `class: session-agent` OR `type: session-agent`** as valid discriminator. Existing 8 sa.\* files keep `class:` indefinitely (zero migration). New sa.\* files prefer `type:` for registry.jsonl uniformity. No structural change.

### v1.0 (2026-04-20, Argus A28 + Mike Maziarz; LOCKED)

sa.cold-boot second pass ([record 030](../../agents/sa/sa.cold-boot/activation-log/030-argus-a28-record.md)) returned PASS — all 3 v0.3 blockers closed in v0.4, no regressions, no new findings. Promoted from draft to locked. Three-instrument verification complete. First v1.2 Pillar 1 capsule shipped.

### v0.4 (2026-04-20, Argus A28)

sa.cold-boot verification pass ([record 029](../../agents/sa/sa.cold-boot/activation-log/029-argus-a28-record.md), verdict PASS-WITH-GAPS) integrated. Closed 3 blockers + 8 gaps: body section headings accept documented synonyms; `spawnable_by` accepts both array form (preferred) AND bare string (legacy); Core inheritance explicitly reconciled — sa.\* activation files as agent-lifecycle artifacts (not ledger entries); maps core's `type` to this capsule's `class`. Phase 1 shipping state vs Phase 4 end state paragraph added.

### v0.3 (2026-04-20, Argus A28)

Self-audit pass closed 8 internal inconsistencies: removed lingering `status: typed` references; clarified `name` field format; loosened canonical [QUERY] line from exact-match to prefix-match; loosened `activation-log/` folder requirement to `status: active` only; loosened body-section requirements at `status: draft`; added MINIMAL Phase 1 example; clarified provenance-pair back-compat; reframed "Relationship to existing sa.\* infrastructure."

### v0.2 (2026-04-20, Argus A28)

sa.research inventory ([record 019](../../agents/sa/sa.research/activation-log/019-session-agent-capsule-patterns.md)) integrated. Required frontmatter aligned to 8-field de facto convention (codification, not invention). State machine: `draft | active | deprecated | superseded`. Body sections renamed (Purpose, Boot Sequence, Invocation Protocol, Output Format, Guardrails, Termination). 4-phase non-breaking retrofit. Typed I/O optional-now / required-at-Phase-4.

### v0.1 (2026-04-20, Argus A28)

Initial DRAFT. Structure complete; awaiting sa.research inventory findings.

---

## Phase 1 vs Phase 4 framing (extracted)

The capsule's *Intent* section describes the end state (typed primitives, Librarian routing). What ships at Phase 1 is much simpler: codification of the 8-field de facto convention + optional typed I/O. An existing sa.\* at Phase 1 looks like the minimal example below; at Phase 4 it looks like the full example. Both shapes are valid; Phase 4 is the direction of travel, not the gate to entry.

**Guiding principle:** *"The capsule's job is codification, not invention."* Every required field is one the existing 8 sa.\* (cold-boot, research, project-tree, arch-specs, metis-nav, vault-janitor, channel-health-monitor, repair-agent) already carry. All 8 are compliant Day 1.

---

## Relationship to existing sa.\* infrastructure (extracted)

- **[sa/CAPSULE.md](../../agents/sa/.tropo-studio/CAPSULE.md)** — commissioning protocol, folder structure, record format, termination semantics. Applies universally to every sa.\*.
- **This capsule (session-agent)** — frontmatter schema, body structure, state machine, validation checks. Governs every sa.\* activation file. Optional typed I/O (`input`/`output` JSON Schemas) is encouraged now and becomes required at Phase 4 of rollout.
- **Existing 8 sa.\*** — all already conformant with the Phase-1 required set (uid, name, class, status, owner, domain, spawnable_by, provenance). No immediate migration needed.

---

## Inheritance from core — explicit reconciliation (extracted)

sa.\* activation files live at `agents/sa/<name>/<name>.md` and are **agent-lifecycle artifacts, not vault entries** (same pattern as agent-configurator files at `agents/<name>/<name>-activation.md`). They declare `extends: core` for conceptual alignment and UID governance, but they are not subject to core's check-in validation in the same way vault entries are.

| Core field | Applied to sa.\* activation files? | How |
|---|---|---|
| `uid` | Yes | Same rule: 8-hex, unique, immutable. |
| `type` | Mapped (v1.0) / Aligned (v1.1) | v1.0: sa.\* use `class: session-agent`. v1.1: `type: session-agent` accepted; either satisfies core's `type:` requirement. New sa.\* files should prefer `type:` for registry uniformity; existing 8 sa.\* may keep `class:` indefinitely. |
| `status` | Yes | State machine. |
| `title` | NOT required | sa.\* use `name` + `domain` as catalog surface. No separate `title` field. |
| `owner` | Yes | Required. |
| `created` (or legacy `commissioned`) | Yes | Provenance pair, with legacy acceptance. |
| `modified` | Mapped | Accept `updated` as synonym for `modified`. Neither required on activation files at Phase 1; both optional-but-encouraged. |

The capsule validator for sa.\* is THIS capsule's validation check list, not core's. Core remains the schema floor for vault entries; this capsule is the floor for sa.\* activation files.

---

## Examples (extracted — 2 worked YAML templates)

### Minimal — Phase 1 active sa.* (what existing 8 look like)

Day-1 compliance shape. No typed I/O; just 8 required slots + `archetype` (optional). Note `spawnable_by` in bare-string legacy form (sa.cold-boot + 3 others use it — valid per check 6).

```yaml
---
uid: 3d9f1a7c
name: sa.cold-boot
class: session-agent
status: active
owner: argus
domain: "Stranger-agent cold-boot verification of activation artifacts, specs, playbooks, and capsules against their claimed behavior"
spawnable_by: all-executives
commissioned: 2026-04-14
commissioned_by: argus-a23
archetype: one-shot
---
```

All 8 existing sa.\* pass validation with roughly this shape.

### Full — Phase 2+ active sa.* with typed I/O

Illustrative target for `sa.cold-boot` once Phase 2 retrofit runs.

```yaml
---
uid: 3d9f1a7c
name: sa.cold-boot
class: session-agent
status: active
owner: argus
domain: "Stranger-agent cold-boot verification of activation artifacts, specs, playbooks, and capsules against their claimed behavior"
spawnable_by: [all-executives]
commissioned: 2026-04-14
commissioned_by: argus-a23
archetype: one-shot
domain_tags: [verification, cold-boot, governance, testing]
description: "Fresh-agent walkthrough of a governance artifact. Used to validate capsule definitions, activation files, playbooks, and specs before lock."
boot_context_budget_tokens: 8000
keep_alive_default: false
input:
 type: object
 required: [target_path, verification_scope]
 properties:
 target_path: { type: string, description: "Vault-relative path to the artifact under test" }
 verification_scope: { type: string, description: "What the cold-boot should verify" }
 synthetic_vault_manifest: { type: array, items: { type: string }, description: "Optional list of additional files to seed the stranger's context" }
output:
 type: object
 required: [verdict, findings]
 properties:
 verdict: { type: string, enum: [pass, pass-with-gaps, fail, inconclusive] }
 findings:
 type: array
 items:
 type: object
 properties:
 severity: { type: string, enum: [blocker, gap, note] }
 description: { type: string }
 location: { type: string }
 remediation_notes: { type: string }
---
```

**Body template references** (existing agents serve as reference templates):

- [sa.cold-boot](../../agents/sa/sa.cold-boot/sa.cold-boot.md) — canonical 6-intent shape (Purpose + Boot Sequence + Task 1–3 as Invocation + Output Format + Will NOT Do as Guardrails + inline Termination)
- [sa.research](../../agents/sa/sa.research/sa.research.md) — uses "Research Protocol" for invocation
- [sa.project-tree](../../agents/sa/sa.project-tree/sa.project-tree.md) — `Capabilities` + `Task 1-N` heading pattern
- [sa.vault-janitor](../../agents/sa/sa.vault-janitor/sa.vault-janitor.md) — inline termination from Constraints

---

## Studio — Shop Signage (extracted)

*Preserved per Mike-A55 directive: capsules are agent-read, not human-read.*

### Tools available

- `ls agents/sa/` — survey existing 8 sa.\* agents
- [`agents/sa/commission-quickref.md`](../../agents/sa/commission-quickref.md) — terse commissioning quickref (hot path)
- [sa/CAPSULE.md (7d3f9a2c)](../../agents/sa/.tropo-studio/CAPSULE.md) — universal commissioning protocol
- [`.tropo-studio/registries/registry.jsonl`](../../.tropo-studio/registries/registry.jsonl) — runtime callable catalog
- Reference activation files: [sa.cold-boot](../../agents/sa/sa.cold-boot/sa.cold-boot.md), [sa.research](../../agents/sa/sa.research/sa.research.md), [sa.project-tree](../../agents/sa/sa.project-tree/sa.project-tree.md), [sa.vault-janitor](../../agents/sa/sa.vault-janitor/sa.vault-janitor.md)

### Skills

- `commission-sa-agent.skill.md` *(forthcoming v1.5)* — scaffold activation file + activation-log/ folder; pre-fills 8 REQUIRED slots + 6 REQUIRED body intents
- `check-sa-catalog.skill.md` — vault audit skill; verifies sa.\* registry inventory matches activation files

### Procedures

- **Author a new sa.\* — at `status: draft`** — create folder `agents/sa/<name>/`; author `<name>.md` with 8 REQUIRED frontmatter slots + Purpose intent (only required at draft); rebuilder projects UID into `registry.jsonl`
- **Advance to `active`** — fill remaining 5 body intents (Boot Sequence with `[QUERY] Boot complete —` line, Invocation Protocol, Output Format, Guardrails / Constraints, Termination); pass cold-boot stranger test; flip `status: draft → active`
- **Commission a sa.\*** — spawning agent writes `[PENDING]` to new record file at `agents/sa/<name>/activation-log/<NNN>-<spawner>-record.md`; sa.\* boot reads + acknowledges; outputs `[DONE]` per Output Format; terminates per spawner's `[RESPONSE]` (default: terminate after [DONE])
- **Compose with harness — terminal one-level** — sa.\* CANNOT spawn sub-agents (Rule 5); persistent specialists are Service Directors per ADR-022
- **Activate vs publish** — `status: active` is registry-visible; `draft` is NOT; `deprecated` retained but not commissioned; `superseded` carries `superseded_by:`
- **Supersede a sa.\*** — author successor at `active` with `supersedes: <predecessor-uid>`; predecessor flips `superseded` + `superseded_by: <successor-uid>` (bidirectional)
- **Archive — sa.\* don't archive** — activation files persist for deprecated and superseded agents (audit trail); they are NOT deleted
- **Tag with v1.1 discriminator** — new sa.\* prefer `type: session-agent`; existing 8 keep `class:` indefinitely

### Pitfalls

- Folder name ≠ `name:` field → Check 2 violation
- Authoring at `status: active` directly → bypasses cold-boot verification gate
- Boot Sequence missing `[QUERY] Boot complete —` line → Check 11 violation
- Activation file at `active` without `activation-log/` folder → Check 16 violation
- Declaring `output:` JSON Schema but emitting prose → Rule 4 violation
- Trying to spawn sub-agent inside sa.\* → Rule 5 / sa/CAPSULE.md universal limit
- Building persistent service as sa.\* → Rule 6 violation; persistent specialists are Service Directors
- Hand-editing registry.jsonl → Rule 7 violation
- Missing provenance pair → Check 9 violation; either (`created` + `created_by`) OR legacy (`commissioned` + `commissioned_by`)
- Body section `## Boot` (legacy synonym OK) → fine; validator matches intent not exact heading

### Worked examples

- [sa.cold-boot.md (3d9f1a7c)](../../agents/sa/sa.cold-boot/sa.cold-boot.md) — canonical 6-intent shape; `archetype: one-shot`; bare-string `spawnable_by` (legacy)
- [sa.research.md (2f7a9c3e)](../../agents/sa/sa.research/sa.research.md) — `Research Protocol` as Invocation synonym
- [sa.project-tree](../../agents/sa/sa.project-tree/sa.project-tree.md) — `Capabilities` + `Task 1-N` heading pattern
- [sa.vault-janitor](../../agents/sa/sa.vault-janitor/sa.vault-janitor.md) — inline termination from Constraints section

### Go next

- Universal commissioning protocol → [sa/CAPSULE.md (7d3f9a2c)](../../agents/sa/.tropo-studio/CAPSULE.md)
- Sibling Pillar 1 (inline behaviors) → [how-to.capsule (a7c3f489)](how-to.capsule.md)
- Sibling Pillar 1 (typed callables) → [tool.capsule (d5e1b4a3)](tool.capsule.md) — sa.\* wrap as tools via `transport: sa`
- Composed substrate → [action.capsule (9b7f5e34)](action.capsule.md)
- Hot-path quickref → [`agents/sa/commission-quickref.md`](../../agents/sa/commission-quickref.md)
- Run-state composition → [playbook-run.capsule (f2a8c3e1)](playbook-run.capsule.md)
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Relationship to Other Capsules — Narrative (extracted)

- **[sa/CAPSULE.md (7d3f9a2c)](../../agents/sa/.tropo-studio/CAPSULE.md)** — sibling. Universal commissioning protocol. This capsule extends it with typing.
- **[how-to.capsule.md](how-to.capsule.md)** — companion typed primitive (v1.2 Pillar 1). Skills are markdown behaviors; session-agents are callable specialists. Both go in registry.jsonl.
- **[tool.capsule.md](tool.capsule.md)** — companion typed primitive (v1.2 Pillar 1). External MCP tools expose typed I/O via their own schema; sa.\* are internal typed specialists.
- **[playbook-run.capsule.md](playbook-run.capsule.md)** — sa.\* invocations can produce playbook-run entries when the sa.\* executes a playbook-like sequence.
- **[core.capsule.md](core.capsule.md)** — extended.

---

## Cross-References (extracted)

- [Agent Harness Awareness research memo (5302ec94)](../../library/docs/agent-harness-awareness-research.md) — research that motivates this capsule. Part 4 §"Concrete primitives to add" names this primitive.
- [Capabilities Matrix v2.0 (c4a9f2b1)](../../vault/files/c4a9f2b1.md) — Row 6 L1 fills.
- [Stack Architecture v1.0 (f3c7a291)](../../vault/files/f3c7a291.md) — L1 Tropo includes sa.\* as one of five substrate components.
- [Architecture Spec v0.5 (826ee57b)](../../vault/files/826ee57b.md) — Pillar 1 basis.
- [Librarian R&D (c408a182)](../../vault/files/c408a182.md) — Subtask 1 references the typed sa.\* pattern.
- [sa.research record 019](../../agents/sa/sa.research/activation-log/019-session-agent-capsule-patterns.md) — pattern inventory + retrofit assessment for lock decision.

---

## Changelog (full lineage)

| Version | Date | Change | Author |
|---|---|---|---|
| 0.1 | 2026-04-20 | Initial DRAFT. Structure complete; awaiting sa.research inventory findings. | Argus A28 |
| 0.2 | 2026-04-20 | sa.research inventory integrated. Required frontmatter aligned to 8-field de facto convention. State machine: draft/active/deprecated/superseded. Body sections renamed (Purpose, Boot Sequence, Invocation Protocol, Output Format, Guardrails, Termination). 4-phase non-breaking retrofit. | Argus A28 |
| 0.3 | 2026-04-20 | Self-audit pass closed 8 internal inconsistencies before sending to Vela cold-boot. | Argus A28 |
| 0.4 | 2026-04-20 | sa.cold-boot verification pass PASS-WITH-GAPS integrated. Closed 3 blockers + 8 gaps. Body section heading synonyms; `spawnable_by` accepts array OR bare string; Core inheritance reconciled. | Argus A28 |
| 1.0 | 2026-04-20 | LOCKED. sa.cold-boot second pass PASS — all 3 blockers closed, no regressions, no new findings. Three-instrument verification complete. First v1.2 Pillar 1 capsule shipped. | Argus A28 + Mike Maziarz |
| 1.1 | 2026-04-20 | Additive non-breaking amendment for cross-capsule discriminator alignment with how-to.capsule + tool.capsule. Accepts either `class: session-agent` OR `type: session-agent`. Existing 8 sa.\* keep `class:` indefinitely. | Argus A28 |
| 1.2 | 2026-04-25 | Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop). Added §Workshop — Shop Signage section. Added Relations Header. No semantic changes. | argus-a34 |
| 1.3 | 2026-04-27 | Registry-reference scrub. Frontmatter `version:` advanced; body changelog backfilled at v1.4 lock. No semantic changes. | argus-a37 (backfill-noted argus-a53) |
| 1.4 | 2026-05-09 | LOCKED — v1.15 Stream A amendment. Additive non-breaking under `capsule_version: "1.4"` opt-in. Added optional `trigger_description:` field. Added optional `capsule_version:` opt-in marker. 1 new validation check (18) gated on opt-in. A53 OP 11 catch: brief named as "sa-agent.capsule (new)" — canonical reality is `session-agent.capsule` (codified at v1.0 2026-04-20) so amendment, not authoring. | argus-a53 |
| 1.5 | 2026-05-11 | **v1.19.0 Stream C — Capsule Pedagogy Completion.** Body refactor to 5-section pedagogy pattern per Mike-A55 *"capsules are agent-read, not human-read"* directive. Active body reduced from 449 → ~250 lines (~44% reduction). Substrate-load-bearing content preserved: 8 required frontmatter slots + optional, 6 Required Body Sections with synonyms, State Machine, 7 Governance Rules, 18 Validation Checks, 4-Phase Retrofit Rollout, Inheritance-from-core reconciliation. Extracted to history: v0.1-v1.4 amendment-block prose, Phase 1-vs-Phase-4 framing, relationship-to-existing-sa-infrastructure, 2 worked YAML examples, §Studio quick-ref, Relationship-to-Other-Capsules, Cross-References, full changelog. **No schema changes.** UID `b4e2a718` preserved. | argus-a56 |

---

## Provenance

- **Extracted at:** 2026-05-11
- **Extracted by:** argus-a56
- **Active capsule version at extraction:** v1.4 (449 lines)
- **Active capsule version after extraction:** v1.5 (~250 lines; ~44% reduction)

---

*session-agent capsule history | UID 709efecd | v1.19.0 Stream C extraction 2026-05-11 by Argus A56 | Bidirectional pair: governs b4e2a718*
