---
uid: 9b7f5e34
name: "action"
type: capsule-definition
extends: core
version: 1.2
supersedes_version: "1.1"
v1_2_amendment_note: "v1.1 → v1.2 amendment 2026-05-29 by Argus A87 captain-mode per v1.60 dev-spec e2a8b5d1 Lane A-migrate (action.capsule version bump per v1.56 tool.capsule v1.6 single-file-truth pattern precedent). NEW §Canonical File Layout subsection — action definitions migrate from .tropo/actions/<name>.action.md to vault/actions/<uid>.{md|json} single-file-truth pattern. Action class-definition is the single canonical source at vault/actions/<uid>.{ext}; .tropo/actions/ retires going forward. Engine invocation paths updated to resolve actions via vault/actions/<uid>.{ext} pattern (pipeline-runtime + rebuild-index Source 6 amendments per Talos Lane A-migrate work event 190). Migration scope: 10 actions migrated by Talos 2026-05-29 (per Talos event 190 substantive ship; the 11th in dev-spec count was non-canonical sidecar that didn't migrate). action_validators.py at .tropo/scripts/lib/ extended to cover new schema. Composes with v1.60 Lane A-migrate Talos ship + v1.56 tool.capsule v1.6 precedent + Mike-A87 Pillar 1 closes-at-three-surfaces walk lock 2026-05-29. Substantive architecture (action protocol + invocation pattern + governance rules) unchanged from v1.1 — only path pattern + single-file-truth layout amended."
tier: os
author: tropo
created: 2026-04-20
modified: 2026-05-29
modified_by: argus-a87
historical_modified: 2026-04-25
historical_modified_by: argus-a34
created_by: argus-a29
status: active
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
aligned_with: a7c3f489 # how-to.capsule (parallel Pillar 1 pattern)
composes_with: d5e1b4a3 # tool.capsule — actions can be wrapped as tools with `transport: action`
pattern_family: a7c3f489 # how-to / tool / session-agent / action — Pillar 1 callable surfaces
member_of:
  - "76bab75f"   # tropo-playbooks (v1.8 Stream B1 backfill)

---

# action — Capsule Definition v1.1

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Ledger Schema v2 — Architecture Specification (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [how-to.capsule (a7c3f489)](how-to.capsule.md) |
| Pattern family | [how-to.capsule (a7c3f489)](how-to.capsule.md) |
| Extends | `core` |
| Composes with | [tool.capsule (d5e1b4a3)](tool.capsule.md) |

*The governance contract for Tropo actions — compound OS-level operations with typed inputs, verification checklists, and atomic multi-artifact outcomes. Parallel pattern to how-to (skills) and tool (callables), filling the meta-capsule gap flagged by sa.research 025.*

*v1.1 (2026-04-25, Argus A34) adds §Studio — Shop Signage + Relations Header per Stream 3 D3.2 of v1.4. v1.0 by Argus A29 (2026-04-20) preserved. UID `9b7f5e34` preserved across the amendment.*

---

## Intent

An **action** is a kernel-tier, compound operation that mints new governed artifacts or performs multi-file vault operations with an atomic outcome. Actions sit alongside skills (how-to), session agents (sa.*), and tools — the four Pillar 1 callable surfaces.

Actions differ from skills:
- **Skills** (how-to) — lightweight, inline behaviors. Single-file focus. Invoked reflexively.
- **Actions** — compound, multi-artifact, atomic. Mint typed vault entries. Invoked deliberately.

Actions differ from playbooks:
- **Playbooks** — multi-group, multi-session orchestration with run.jsonl state. Resumable. Long-running.
- **Actions** — single-session, single-operation, deterministic. One invocation, one outcome.

Before this capsule, Tropo shipped 10 actions (verified by sa.research 025) none of which carried `governed_by:` pointers. Action governance existed in [.tropo/actions/00-index.md](../actions/00-index.md) prose — not in a capsule the actions themselves conform to. This capsule closes that gap: every action now has a governance contract it must satisfy to be valid.

**Retrofit philosophy: zero forced migration.** The 10 existing actions conform to the shape this capsule declares (they just never declared it). Setting `governed_by: 9b7f5e34` on each action is the one-line retrofit. No rewrites required.

---

## Required Frontmatter

| Field | Type | Constraint |
|---|---|---|
| `title` | string | Human-readable title (e.g., `"Create a Project"`) |
| `action_id` | string | Machine-readable stable identifier. Format: `act-<slug>` (e.g., `act-create-project`). Immutable once set. |
| `version` | semver | Action version. Bumps on any structural change. |
| `status` | enum | One of: `draft` / `published` / `superseded`. |
| `tier` | literal | Must be `os` — actions are kernel-tier. |
| `target_capsule` | string OR UID | The capsule whose instances this action mints or modifies. E.g., `project` for `create-project`, `collection` for `create-collection`. Optional for actions that don't mint governed entries (e.g., `refresh-view`). |
| `author` | string | Author or authoring group. `tropo` for OS-shipped actions. |
| `created` | ISO date | First-authored date. |
| `reads` | array of paths or UIDs | Files + capsules the action reads at runtime. ADR-035 Surface reachability check enforces these. |
| `writes` | array of paths or patterns | Files + directories the action produces or modifies. Informs rollback semantics on failure. |

## Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `collection_note` | string | Clarifying note about multi-file patterns (e.g., two-write collection pattern). |
| `supersedes` | string | action_id of the prior action this one replaces. |
| `superseded_by` | string | action_id of the replacement action (set on retirement). |
| `last_updated` | ISO date | Most recent version bump date. |
| `updated_by` | string | Author of most recent update. |
| `aligned_with` | UID | Governance ADR this action is designed against (common for actions shaped by specific ADRs). |

---

## Required Body Structure

Actions use a six-section body shape. This parallels how most existing actions are already written (sa.research 025 confirmed the pattern) — the capsule formalizes it.

### 1. `## 1. Intent`

One short paragraph naming what the action does and why it exists. The "reader who just learned this action exists" opens here.

### 2. `## 2. Prerequisites`

List of vault preconditions the invoker must have satisfied. Example: valid parent project UID, writeable ledger, registered owner. Failure of a prerequisite aborts the action before any write.

### 3. `## 3. Inputs`

All parameters the invoker must supply. Split into `### Required inputs` and `### Optional inputs`. Each input: name, type, constraint, semantic purpose.

### 4. `## 4. Process`

Ordered list of steps. Every step:
- Names what it does
- Declares what it reads + writes
- Names failure semantics (halt + rollback, or skip + note)
- Each write step MUST cite the governing capsule for the artifact being written

### 5. `## 5. Templates`

Inline frontmatter + body templates for every governed artifact the action mints. These are the authoritative artifact-creation templates — no separate template files.

### 6. `## 6. Verification`

Numbered checklist the invoker runs after completion to confirm success. Every item: concrete shell command or grep check the agent can execute, expected result, remediation if failed.

### 7. `## 7. Failure Modes` (optional but strongly recommended)

Table of anticipated failure modes with remediation actions. Turns "what went wrong" into a runbook.

### Footer

Standard footer: `*<Title> | v<version> | Tropo OS | <date>*` + version-history one-liners for legacy trace.

---

## Relationship to `tool.capsule`

A subtlety worth naming: the [tool.capsule (d5e1b4a3)](tool.capsule.md) accepts `action` as one of its five transport values (`mcp | action | http | platform | sa`). This creates apparent overlap — is an "action" just a tool with `transport: action`?

**No.** The distinction:

- **`type: tool`, `transport: action`** — a tool entry in the registry that SURFACES an action as a typed callable with JSON Schema I/O. Enables cross-harness invocation (the tool-wrapping perspective).
- **`type: action-definition`** (this capsule) — the ACTION itself as a governed kernel artifact with templates, process, verification. Governs HOW the action is authored and structured.

Actions can BE wrapped as tools. The tool entry references the action. The action is the substrate; the tool entry is one invocation surface. Parallel to how session-agent artifacts can be wrapped as tools with `transport: sa`.

---

## State Machine

```
draft → published → superseded
```

- **`draft`** — being authored or under cold-boot verification. Do not invoke in production.
- **`published`** — cold-boot verified, approved for invocation. Default state for shipped actions.
- **`superseded`** — replaced by a newer action (often a version bump). Retained for lineage; `superseded_by:` points at the replacement.

Actions should NOT have a `ready` or `staging` intermediate state. Two states is enough: authored (draft) → shipped (published) → retired (superseded).

---

## Governance Rules

1. **Every action carries `governed_by: 9b7f5e34`.** Retrofit for the 10 existing actions is a one-line frontmatter addition. No rewrites.
2. **action_id is immutable.** Once an action is published, its `action_id:` cannot change. Breaking that identity breaks every caller.
3. **Version bumps on structural changes.** Adding/removing inputs, changing output artifact types, altering step order = minor version bump at minimum. Capsule-contract-breaking changes = supersession (new action_id).
4. **Failure is atomic.** Actions that mint multiple artifacts MUST declare rollback semantics in §7 Failure Modes. Partial success is not success; a failed action leaves the vault in its pre-invocation state.
5. **Verification is non-optional.** §6 Verification is a required section. An action without a verification checklist cannot be published — only drafted.
6. **Reads and writes declared honestly.** The `reads:` and `writes:` frontmatter fields MUST list every file path or UID the action actually touches. ADR-035 Declared-Presence applies: declared reads must resolve; declared writes must be within the action's write scope.

---

## Validation Checks (run at check-in)

1. `action_id:` present, matches format `act-<slug>`, lowercase-hyphen.
2. `version:` present, valid semver.
3. `status:` in enum `{draft, published, superseded}`.
4. `tier: os` present.
5. `reads:` array present (may be empty for pure-compute actions).
6. `writes:` array present (must be non-empty for actions that mint artifacts).
7. `governed_by: 9b7f5e34` present (post-retrofit).
8. Body contains all six required sections + optional seventh.
9. If `superseded`, `superseded_by:` present.
10. `action_id` unique across active actions.

---

## Retrofit Path (one-time)

The 10 existing actions ([create-task](../actions/create-task.action.md), [create-project v3.1](../actions/create-project.action.md), [create-design-brief](../actions/create-design-brief.action.md), [create-design-spec](../actions/create-design-spec.action.md), [create-collection](../actions/create-collection.action.md), [create-decision](../actions/create-decision.action.md), [create-note](../actions/create-note.action.md), [generate-view](../actions/generate-view.action.md), [refresh-view](../actions/refresh-view.action.md), [delete-entry](../actions/delete-entry.action.md)) each need:

1. **Add `governed_by: 9b7f5e34`** to frontmatter.
2. **Verify body conforms to 6-section shape.** sa.research 025 spot-checked; all conform to convention. Confirming requires reading each once — ~15 min total.
3. **Index refresh:** capsule rules auto-propagate via `rebuild-registry.ts` since the registry schema matches this capsule's required fields (see registry.jsonl Design Spec).

Retrofit is a v1.3 Stream D item (D5 in the residual cleanup list).

---

## Relationship to Other Capsules

- **Parallels [how-to.capsule (a7c3f489)](how-to.capsule.md)** — both are callable-surface governance. Actions are compound; skills are inline.
- **Parallels [session-agent.capsule (b4e2a718)](session-agent.capsule.md)** — actions are turn-bound; session agents are lifecycle-bound.
- **Parallels [tool.capsule (d5e1b4a3)](tool.capsule.md)** — actions can be surfaced as tools with `transport: action`.
- **Reads [core.capsule (ee814120)](core.capsule.md)** — floor rules apply.

Together, these four capsules (action + how-to + session-agent + tool) form the complete Pillar 1 callable-surface governance.

---

## Current Instances (at capsule-author time)

All 10 active actions governed by this capsule on retrofit. Source of truth remains the individual action files; the registry surfaces them for discovery.

| action_id | File | Purpose |
|---|---|---|
| `act-create-task` | [create-task.action.md](../actions/create-task.action.md) | Create one task entry |
| `act-create-project` | [create-project.action.md](../actions/create-project.action.md) | Compound: project + 2 collections + navigation folder |
| `act-create-design-brief` | [create-design-brief.action.md](../actions/create-design-brief.action.md) | Create one exploratory design-brief |
| `act-create-design-spec` | [create-design-spec.action.md](../actions/create-design-spec.action.md) | Create one design-spec as draft |
| `act-create-collection` | [create-collection.action.md](../actions/create-collection.action.md) | Two-file write: manifest + ledger collection-ref |
| `act-create-decision` | [create-decision.action.md](../actions/create-decision.action.md) | Create one ADR as proposed |
| `act-create-note` | [create-note.action.md](../actions/create-note.action.md) | Create one governed note |
| `act-generate-view` | [generate-view.action.md](../actions/generate-view.action.md) | Create a new folder hierarchy of collections |
| `act-refresh-view` | [refresh-view.action.md](../actions/refresh-view.action.md) | Refresh collection memberships in an existing view |
| `act-delete-entry` | [delete-entry.action.md](../actions/delete-entry.action.md) | Retire/destroy a vault entry (draft) |

---

## Studio — Shop Signage

*What's on the wall above this bench. Scan before you author or invoke an action.*

**Tools available:**
- `ls .tropo/actions/*.action.md` — survey the 10 shipped actions before authoring a duplicate
- [`.tropo/actions/00-index.md`](../actions/00-index.md) — action catalog with semantic groupings
- `vault/00-index.jsonl` — grep `governed_by: 9b7f5e34` to enumerate retrofit-compliant actions
- `.tropo-studio/registries/registry.jsonl` — once seeded (Phase 2 of tool.capsule), tool entries with `transport: action` surface here
- Reference instances: [create-project.action.md](../actions/create-project.action.md) (compound multi-artifact, atomic), [create-collection.action.md](../actions/create-collection.action.md) (two-file write — manifest + ledger ref), [create-task.action.md](../actions/create-task.action.md) (single-artifact baseline)

**Skills:**
- `author-action.skill.md` *(forthcoming v1.5)* — scaffold the 6 REQUIRED body sections + minimum frontmatter (`action_id`, `version`, `status: draft`, `tier: os`, `target_capsule`, `reads`, `writes`); pre-fills `governed_by: 9b7f5e34`
- `verify-action.skill.md` *(forthcoming v1.5)* — runs §6 Verification checklist for an action; reports pass/fail with remediation pointers

**Procedures:**
- **Author a new action — start at `draft`** — declare `action_id: act-<slug>` (immutable per Rule 2); fill 6 REQUIRED body sections (Intent / Prerequisites / Inputs / Process / Templates / Verification); declare `reads:` + `writes:` honestly per Rule 6
- **Add §Failure Modes (strongly recommended)** — table of anticipated failures + remediation; mandatory in spirit per Rule 4 atomic-failure invariant
- **Publish — move `draft → published`** — only after cold-boot verification passes §6 Verification; verification checklist is non-optional per Rule 5
- **Invoke an action** — caller satisfies all `Prerequisites`; supplies all REQUIRED inputs per `## 3. Inputs`; runs the action; runs §6 Verification post-execution
- **Verify the invocation** — execute every checklist item in §6; on any failure, follow §7 Failure Modes remediation; partial success is NOT success per Rule 4
- **Compose with tool.capsule** — to wrap an action as a registry-discoverable tool, create a `type: tool` vault entry with `transport: action` + `action_id: <this-id>` + `target_capsule:` (per tool.capsule v1.0 conditional-required fields); the action file remains the authoritative body
- **Compose with capsules being minted** — every write step in §4 Process MUST cite the governing capsule for the artifact; a write to `vault/files/` minting a project cites [project.capsule v2.1 (34e4cb0b)](project.capsule.md), etc.
- **Supersede an action** — author successor with new `action_id` (NOT a version bump — capsule-contract-breaking changes need new identity per Rule 3); set `superseded_by:` on predecessor + `supersedes:` on successor (Validation Check 9)
- **Archive (no separate state)** — no `archived` state; supersession + retirement combined: predecessor moves to `superseded`, successor active

**Rules (at-a-glance):**
1. **Every action carries `governed_by: 9b7f5e34`** — one-line retrofit; no rewrites required for the 10 existing actions
2. **`action_id:` is immutable** — once published, breaking that identity breaks every caller
3. **Version bumps on structural changes** — input/output/step changes = minor bump minimum; capsule-contract-breaking changes = supersession (new action_id)
4. **Failure is atomic** — multi-artifact actions MUST declare rollback semantics in §7 Failure Modes; partial success leaves the vault inconsistent
5. **Verification is non-optional** — §6 Verification required for `published` status
6. **Reads + writes declared honestly** — `reads:` MUST list every file read; `writes:` MUST list every file written; ADR-035 Declared-Presence applies
7. **`tier: os`** — actions are kernel-tier; the literal is required

**Pitfalls:**
- **Authoring an action without `governed_by: 9b7f5e34`** — Rule 1 / Validation Check 7 violation; one-line frontmatter retrofit closes it
- **Publishing without §6 Verification** — Rule 5 / Validation Check 8 violation; an action that can't verify its own outcome is unpublishable
- **Compound action without §7 Failure Modes** — Rule 4 spirit violation; multi-artifact mints without rollback semantics leave the vault in indeterminate state on partial failure
- **Bumping `action_id:` on a contract change** — Rule 2 violation; supersede instead (new `action_id`, bidirectional `supersedes:` / `superseded_by:` pair)
- **Action file with `writes:` outside the folder's AGENTS.md write-scope** — Rule 6 + ADR-035 violation; either narrow writes or update the target folder's AGENTS.md
- **Action minting an artifact without citing the governing capsule** — §4 Process discipline violation; every write step must cite its capsule for traceability
- **Confusing actions with playbooks** — actions are single-session, deterministic, one-invocation-one-outcome; playbooks are multi-group, multi-session, resumable. If the work needs `run.jsonl` state, it's a playbook
- **Confusing actions with skills** — skills (how-to) are inline, lightweight, single-file focus; actions are compound, multi-artifact, atomic. If multiple typed artifacts mint atomically, it's an action

**Worked examples:**
- [create-project.action.md](../actions/create-project.action.md) v3.1 — compound: project + 2 collections + navigation folder; canonical multi-artifact atomic action; references all 6 REQUIRED body sections + §7 Failure Modes
- [create-collection.action.md](../actions/create-collection.action.md) — two-file write (manifest + ledger collection-ref); pairs with [collection.capsule (c04e7a91)](collection.capsule.md) + [collection-ref.capsule v3.0 (c01ec700)](collection-ref.capsule.md)
- [create-task.action.md](../actions/create-task.action.md) — single-artifact baseline; the simplest shape

**Go next:**
- Sibling Pillar 1 (inline behaviors) → [how-to.capsule v1.0 (a7c3f489)](how-to.capsule.md)
- Sibling Pillar 1 (typed callables, 5 transports) → [tool.capsule v1.0 (d5e1b4a3)](tool.capsule.md) — actions can wrap as tools with `transport: action`
- Sibling Pillar 1 (callable specialists) → [session-agent.capsule v1.2 (b4e2a718)](session-agent.capsule.md)
- Action catalog → [`.tropo/actions/00-index.md`](../actions/00-index.md)
- Folder governance → `.tropo/actions/AGENTS.md` (when authored)
- Governance meta → [capsule-definition (222873b9)](../../vault/files/222873b9.md)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-04-20 | Initial version. Codifies the 6-section action body shape and 10-slot frontmatter convention already in use across the 10 shipped actions. Retrofit philosophy: zero forced migration; setting `governed_by: 9b7f5e34` is the one-line frontmatter retrofit. Closes the meta-capsule gap flagged by sa.research 025. | argus-a29 |
| 1.1 | 2026-04-25 | **Stream 3 D3.2 uplift (v1.4 Craftsman's Workshop).** Added §Workshop — Shop Signage section (Tools / Skills / Procedures / Rules-at-a-glance / Pitfalls / Worked examples / Go next) per the v3 capsule shop-signage pattern. Added Relations Header right after H1 — clickable navigation surface mirroring frontmatter (governed_by, aligned_with how-to, composes_with tool, sibling Pillar 1 primitives, pattern_family, action body folder). Frontmatter `composes_with: d5e1b4a3` + `pattern_family: a7c3f489` declared. No semantic changes to §Required Frontmatter / §Required Body Structure / §Validation Checks / §Governance Rules / §State Machine. UID preserved at 9b7f5e34. | argus-a34 |

---

*action Capsule Definition | v1.1 | Argus A34 | 2026-04-25 (Stream 3 D3.2 — §Studio + Relations Header); v1.0 by Argus A29 (2026-04-20) preserved in git history*
*"Actions are the compound writes. One invocation, one atomic outcome, one verification checklist."*
