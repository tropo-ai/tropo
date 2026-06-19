---
uid: 7901662b
name: "governance-contract"
type: capsule-definition
extends: core
version: "1.1"
tier: os
author: argus-a57
status: locked
locked_by: argus-a57
locked_at: 2026-05-11
created: 2026-05-11
modified: 2026-06-06
created_by: argus-a57
modified_by: argus-a101
v1_1_completion_note: "v1.1 member_of DISAMBIGUATE completed 2026-06-06 by Argus A101 per spec 6f5bb2cb (Mike-A100-approved 9 lock-breaks) + core.capsule v1.5 Rule 9. Amend-in-place under the approved lock-break (status stays `locked`, per the events.capsule amend-with-note precedent). The v1.1 §2 table swap (subsystem_hub carries hub membership; member_of = true parent only) was applied but Governance Rule 6, Validation Check 9, and the §5 Composes-With line were left keyed on member_of-as-hub. A101 finished the reconciliation so the body matches the table. No version re-bump: same v1.1 logical change, two-pass application (table prior gen; rules+check A101)."
schema_version: 2
extraction_scope: ship
governed_by: 222873b9   # capsule-definition meta-capsule
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — 5-section pedagogy reference
aligned_with:
  - 8b3f1d92   # Tropo Work v3 Architecture Specification
  - db0fd9b1   # SELF-HEALING.md (Path 1/Path 2 discipline; governance-contract authoring is Path 1 fix-class)
  - 99341618   # agent-activation.playbook (boot path reads folder governance during Group 0)
composes_with:
  - 8a4e21c5   # subsystem-hub.capsule (parent governance; every governance-contract subsystem_hub: includes a subsystem hub — v1.1 member_of DISAMBIGUATE)
member_of:
  - "8dd772a0"   # tropo-governance
tags: [capsule-definition, governance-contract, lock-c-layer-2, folder-level-governance, 5-section-pedagogy, v1.20.0-stream-a-authored]
---

# governance-contract — Capsule Definition v1.0

## 1. Intent

A `governance-contract` is the typed primitive that declares folder-level governance: who owns the folder, who may write, who may read, what the folder is for, and what operating rules govern artifacts within. It is the typed replacement for the per-folder `.tropo-studio/CAPSULE.md` pattern that preceded the graph-based vault — same job, but now a UID-addressable vault entry rather than a fixed-path markdown file.

Folder-level governance is needed when a folder holds **heterogeneous content** — content whose individual files don't share a single per-file type contract that covers everything the folder needs to enforce. Examples: `agents/` (per-agent identity stacks with runtime state), `channels/` (markdown communication files), `library/` (reference material). For folders whose content is fully type-governed — `vault/files/` (every file is a typed governed primitive), `.tropo/capsules/`, `.tropo/playbooks/`, `.tropo/skills/` — per-file type contracts handle governance and **no governance-contract is needed**. File-level type governance and folder-level governance compose; neither subsumes the other.

The AGENTS.md file at the folder root remains in place as the commercial-agent compatibility bridge (an external convention honored by Claude Code, Cursor, Aider, and similar tools when they enter a folder); the governance-contract is the canonical source-of-truth that AGENTS.md routes to.

Failure mode prevented: folder-level governance drifting silently across folders because each `CAPSULE.md` is a per-folder markdown file with no schema enforcement, no validator coverage, and no graph-queryable presence. Governance-contract instances are validator-checked at vault-rebuild time and discoverable via the same UID + `member_of:` machinery as every other governed primitive.

---

## 2. Schema

### Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `type` | literal | `governance-contract` |
| `governed_path` | string | The folder path this contract governs. Relative to vault root (e.g., `agents/`, `library/crew-status-reports/`). Must resolve to a real folder. Unique across active governance-contracts. |
| `folder_type` | enum | One of: `governed` / `registry` / `content` / `ledger` / `kernel` / `studio-metadata` / `runtime` / `archive` / `workspace`. Names the folder's structural role. See §Folder Type Enum below. |
| `owner` | UID | The agent or entity that owns this folder. Resolves to an entity. Owner has final write authority over the folder's contents. |
| `write_access` | array | UIDs or role tokens of agents who may write to this folder. Special tokens: `[all-agents]` (every registered agent), `[owner-only]` (only `owner:` may write). |
| `read_access` | array or literal | UIDs of agents who may read, OR the literal `all` (every entity, including unregistered visitors). |
| `purpose` | string | ≤200 chars. One-sentence statement of what the folder is for. |
| `subsystem_hub` | UID array | At least one subsystem hub UID (governance / rendering / work / agents / playbooks / library / documentation) plus tropo-link if applicable **(v1.1 member_of DISAMBIGUATE: moved here from `member_of`)**. |
| `member_of` | UID array | optional; true organizational parent (non-hub). |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `exception_class` | enum | One of: `boot-load-bearing` / `runtime-state` / `frozen-historical` / `kernel-substrate` / `studio-metadata`. When present, marks the folder as a named exception — `CAPSULE.md` + `AGENTS.md` at the folder root may stay in place rather than fully converging to vault-resident typed substrate. Used for `.tropo/`, `.tropo-studio/`, `recycle/`, `archive/`, `playbook-runs/`, `channels/`. |
| `validator_extension` | UID | Link to a validator check (or set of checks) in `.tropo/scripts/tropo-validate.py` that enforces this folder's invariants beyond the schema-level checks. |
| `sub_directories` | array of objects | For folders that have child folders with their own governance contracts. Each object: `{path, governed_by_uid}`. Optional. |
| `violations` | array of objects | For folders with specific violation rules. Each object: `{violation, indicator, action}`. Mirrors the v1.x AGENTS.md / CAPSULE.md violations table pattern. |
| `supersedes` / `superseded_by` | UID | Bidirectional pair for supersession when a governance-contract is amended via successor rather than in-place edit. |
| `governed_by_release` | UID | Release entry UID that locked this governance-contract. Tracks contract history. |
| `legacy_capsule_md_path` | string | Path to the `CAPSULE.md` file this contract supersedes (for migration provenance). Populated during Stream D migrations. |

### Body shape — 4 required sections + 2 optional, in declared order

1. **`## 1. Intent`** — What's in this folder + what's NOT in this folder. The cold-boot answer to "should this artifact live here?"
2. **`## 2. Operating Logic`** — Numbered rules (R1, R2, ...) declaring how the folder operates. Replaces the §Rules section from current CAPSULE.md files. Each rule is a single load-bearing claim with rationale where non-obvious.
3. **`## 3. Sub-directory Map`** — Optional. Table of child folders, their purposes, and what governs each. Required for folders with child folders that have their own governance contracts (e.g., `agents/` has `agents/sa/`, `agents/directors/`, `agents/visitors/`).
4. **`## 4. Violations`** — Optional. Table of violation patterns + indicators + required actions. Used for folders where specific deviations need named handling. Mirrors the v1.x AGENTS.md violations table.
5. **`## 5. Composes-With`** — Required. Cross-references: parent subsystem hub, child folders' governance contracts, related typed primitives, the validator extension (if any).
6. *(optional)* **`## Provenance`** — Historical note tracking authorship + amendments. Required when `supersedes:` is set.

### Folder Type Enum

The `folder_type:` field names the folder's structural role. Recognized values:

| Value | Meaning | Example folders |
|---|---|---|
| `governed` | General governed folder; heterogeneous content with folder-level rules | Studio root `argo-os/` (canonical Tropo Studio) |
| `registry` | Folder is a registry of entries — agents, channels, sessions | `agents/`, `channels/` |
| `content` | Folder holds reference content | `library/` |
| `ledger` | Folder IS the governed vault (the typed-primitive store) | `vault/` |
| `kernel` | Folder is part of the Tropo-OS kernel | `.tropo/`, `.tropo/capsules/`, `.tropo/playbooks/`, `.tropo/skills/` |
| `studio-metadata` | Folder is Studio operational metadata | `.tropo-studio/`, `.tropo-studio/registries/`, `.tropo-studio/scripts/` |
| `runtime` | Folder holds runtime state | `playbook-runs/`, agent workspace folders |
| `archive` | Folder holds frozen historical content | `recycle/`, `archive/` |
| `workspace` | Ungoverned scratch surface | `01-vault-inbox/`, agent `workspace/` subfolders |

The enum is intentionally finite. Adding a new value is a v1.x amendment to this capsule, not a per-instance freedom.

---

## 3. State Machine

```
draft → active → archived (supersession or retirement)
   ↑________↓ (revision during draft)
```

Same pattern as other governance primitives (capsule definitions, subsystem hubs, design specs).

| Status | Meaning |
|---|---|
| `draft` | Contract being authored. Folder may exist; folder-level rules not yet committed. |
| `active` | Contract is live. Folder-level rules govern. Amendments via revision (minor) or supersession (structural). |
| `archived` | Contract retired — either superseded by a successor or the folder itself retired (deleted/merged). |

**Valid transitions:**

- `draft → active` — contract finishes first-draft authoring; goes live
- `active → draft` — revision before formal lock (rare; preserve via successor instead)
- `active → archived (superseded)` — successor contract authored; bidirectional `supersedes:` / `superseded_by:` set atomically
- `active → archived (folder retired)` — folder no longer exists; contract retires; `governed_by_release:` records the cycle that retired

**Required starting state:** every new governance-contract starts at `status: draft`. Direct authoring at `active` or `archived` is a validation error.

---

## 4. Validation Rules

### Governance Rules (8, in addition to core)

1. **One active contract per `governed_path:`.** Two governance-contracts with the same `governed_path:` in `status: active` is a validation error. Use supersession (bidirectional `supersedes:` / `superseded_by:` pair) when amending.
2. **`governed_path:` must resolve to a real folder.** Authoring a governance-contract for a folder that doesn't exist is a validation error. The contract exists to govern; nothing-to-govern is incoherent.
3. **`owner:` resolves to an entity.** The folder must have an accountable owner. Single UID; multi-owner is expressed via `write_access:` not `owner:`.
4. **`write_access:` entries resolve to entities or named tokens.** Special tokens: `[all-agents]`, `[owner-only]`. Other entries must be agent UIDs that resolve through `agent-registry.yaml`.
5. **`exception_class:` (if present) is one of the named values.** Used sparingly; named exceptions should be rare and load-bearing reasons explicit in §Operating Logic.
6. **`subsystem_hub:` includes at least one subsystem hub UID** (v1.1 member_of DISAMBIGUATE — was `member_of:` pre-v1.1; `member_of:` is now the optional true organizational parent per core.capsule v1.5 Rule 9). Per release.capsule Rule 12 alignment: every typed governed primitive declares its subsystem membership. Folder governance belongs to `tropo-governance` (`8dd772a0`) primarily, with cross-cutting hub membership where applicable.
7. **Body sections in declared order.** §1 Intent → §2 Operating Logic → §3 Sub-directory Map (if present) → §4 Violations (if present) → §5 Composes-With. Optional §Provenance appears at end.
8. **AGENTS.md at the folder root remains separate from this contract.** The governance-contract is the source-of-truth for folder governance; AGENTS.md is the commercial-agent compatibility bridge that routes to it. Authoring a governance-contract does NOT retire AGENTS.md; AGENTS.md is preserved as the commercial-agent bridge.

### Validation Checks (10, ERROR-severity at v1.21.0+; WARN through v1.20.0 + early v1.20.x grace window)

1. `type: governance-contract` exact
2. `governed_path:` non-empty string; resolves to a real folder relative to vault root
3. `governed_path:` unique across `state: active` governance-contracts
4. `folder_type:` ∈ {governed, registry, content, ledger, kernel, studio-metadata, runtime, archive, workspace}
5. `owner:` resolves to an entity in `agent-registry.yaml` or the founder
6. `write_access:` non-empty array; each entry is a valid UID or recognized role token
7. `read_access:` is array of UIDs OR the literal `all`
8. `purpose:` present, ≤200 chars
9. `subsystem_hub:` non-empty array; at least one UID resolves to a subsystem hub (in the hub set + tropo-link) — v1.1 member_of DISAMBIGUATE (was `member_of:` pre-v1.1)
10. Body contains §1 Intent + §2 Operating Logic + §5 Composes-With in declared order (§3 + §4 + §Provenance are optional)

Core checks inherited: UID uniqueness, UID immutability, type immutability, owner/created/modified invariants.

**Grace period:** v1.20.0 introduces this capsule at WARN severity. ERROR severity activates at v1.21.0 to give the v1.20.0 migration cycle (Stream D) time to author governance-contract instances for every heterogeneous folder + named exception class. Pattern mirrors v1.18.0's `check_kb_article_typing()` grace handling.

---

## 5. Composes-With

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor for UID/owner/modified invariants.
- **[subsystem-hub.capsule (8a4e21c5)](subsystem-hub.capsule.md)** — parent governance. Every governance-contract instance declares `subsystem_hub:` including at least one subsystem hub UID (v1.1 member_of DISAMBIGUATE — moved from `member_of:`).
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — this capsule's own governance.
- **[playbook.capsule v2.5 (e7b3c509)](playbook.capsule.md)** — `pattern_exemplar`. The 5-section pedagogy structure is patterned on playbook v2.5 (and v1.18.0 kb-article + activation-log + subsystem-hub refactors).
- **AGENTS.md (commercial-agent bridge)** — non-typed external compatibility surface. Uniform across folders; routes commercial agents to the governance-contract instance for the folder. Stays in place when a governance-contract is authored; the two compose (AGENTS.md is the discovery surface; governance-contract is the typed source-of-truth).
- **Per-folder `.tropo-studio/CAPSULE.md`** — pre-v1.20.0 substrate. Stream D migrates content to governance-contract instances; per-folder CAPSULE.md becomes thin pointer or retires for type-governed folders.
- **[SELF-HEALING.md (db0fd9b1)](../../vault/files/db0fd9b1.md)** — Path 1/Path 2 discipline applies during governance-contract authoring and migration: trivial fixes in place; substantive design issues filed as tracked work-items.

### Composition with AGENTS.md (commercial-agent bridge)

AGENTS.md at a folder's root is a uniform boilerplate pointer that satisfies the commercial-agent convention honored by Claude Code, Cursor, Aider, and similar tools. Its content does NOT carry folder-specific governance — it routes the reader to the canonical Tropo-OS substrate (TROPO-CONTROL.md + STUDIO.md + the folder's governance contract).

After v1.20.0 ships, AGENTS.md body updates to add the governance-contract UID as the canonical authority alongside (or replacing) the pre-v1.20.0 reference to `.tropo-studio/CAPSULE.md`. Pattern:

```
This folder is part of a Tropo-OS vault. Before operating, read:

1. .tropo/TROPO-CONTROL.md — OS rules, identity checkpoint, invariants
2. STUDIO.md (vault root) — Organization defaults and constraints
3. vault/files/<governance-contract-uid>.md — Folder governance (this folder's rules)

Do not modify this file. It is maintained by Tropo through the update pipeline.
```

For folders whose content is fully type-governed (vault/files/, .tropo/capsules/, .tropo/playbooks/, .tropo/skills/), AGENTS.md routes to the type contracts rather than a governance-contract instance — no folder-level contract exists or is needed.

### Composition with per-file type contracts

File-level governance via capsule-typed primitives and folder-level governance via governance-contracts are **complementary, not competing**:

- File-level governance answers: "what shape must THIS file have?" (schema + state machine + validation rules per file type)
- Folder-level governance answers: "what shape must THIS FOLDER have?" (heterogeneity rules + write_access + read_access + sub-directory layout + violations)

When a folder's content is fully type-governed (every file in the folder has its own type contract that covers everything the folder needs to enforce), folder-level governance is redundant and a governance-contract instance is NOT authored. When a folder's content is heterogeneous (sub-folders, mixed file types, runtime state), folder-level governance is needed and a governance-contract instance is authored.

---

*governance-contract capsule definition | LOCKED v1.0 | UID `7901662b` | Authored by Argus A57 2026-05-11 | v1.20.0 Stream A — Lock C Layer 2 operationalized*
*"Folder-level governance is the typed primitive that closes the gap between commercial-agent conventions (AGENTS.md) and Tropo's graph-based substrate (capsule-typed files). One contract per folder where folder-level rules are needed; nothing where per-file type contracts already cover."*
