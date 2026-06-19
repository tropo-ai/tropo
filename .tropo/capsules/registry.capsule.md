---
uid: 55a57893
name: "registry"
type: capsule-definition
extends: core
version: 1.1
tier: os
author: argus
created: 2026-05-22
created_by: argus-a79
modified: 2026-06-06
modified_by: argus-a101
v1_1_completion_note: "v1.1 member_of DISAMBIGUATE completed 2026-06-06 by Argus A101 per spec 6f5bb2cb (Mike-A100-approved 9 lock-breaks) + core.capsule v1.5 Rule 9. The v1.1 §2 table swap (subsystem_hub MUST include tropo-governance 8dd772a0 + Registries hub 7e93ed75; member_of = optional true parent) was applied but §3 Rule 2, the §4 check_registry_required_fields field list, and the §4 check_registry_member_of_hub check were left keyed on member_of-as-hub. A101 finished the reconciliation: Rule 2 + the required-field list + the hub check (renamed check_registry_subsystem_hub) now read subsystem_hub. No version re-bump: same v1.1 logical change, two-pass application (table prior gen; rules+checks A101)."
status: draft
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
composes_with: 34e4cb0b   # project.capsule — registries ARE typed projects
pattern_family: 34e4cb0b
member_of:
  - "8dd772a0"   # tropo-governance
  - "7e93ed75"   # Registries hub
tags: [capsule-definition, registry, governance, typed-data-substrate, v1-50-0]
---

# registry — Capsule Definition v1.0

| Relation | Target |
|---|---|
| Governed by | [capsule-definition meta (222873b9)](../../vault/files/222873b9.md) |
| Extends | `core` |
| Composes with | [project.capsule (34e4cb0b)](project.capsule.md); [release.capsule (b19e8d43)](release.capsule.md) Rule 11/12 (subsystem-registry-specific consumer) |
| Pattern family | [project.capsule (34e4cb0b)](project.capsule.md) |
| Member of | [Tropo Governance (8dd772a0)](../../vault/files/8dd772a0.md); [Registries hub (7e93ed75)](../../vault/files/7e93ed75.md) |

---

## 1. Intent

A `registry` is a **typed governed wrapper around a data file** (JSONL/YAML/etc.) that stores a relationship-table the substrate needs to query as a graph.

Registries exist for **one reader question:** *"give me the relationships of class X."* Examples:
- *"which release touched which subsystem, when?"* → `subsystem-registry.jsonl`
- *"which UID resolves to which file?"* → `registry.jsonl` (main vault UID index)
- *"which projects are canonical L0?"* → `canonical-l0-projects.yaml`
- *"which agents are on the crew, and how do they activate?"* → `agent-registry.yaml`
- *"which pipeline-runs have happened?"* → `playbook-runs.jsonl`

A registry is a **data file** (the JSONL/YAML at `.tropo-studio/registries/<name>.<ext>`) paired with a **typed wrapper vault entry** (`vault/files/<uid>.md` with `type: registry`) that declares the registry's identity, schema, derivation method, governance, and consumers.

**Failure mode prevented:** registries living as free-floating data files outside the substrate-as-graph model — invisible to queries, ungoverned, no lineage, no consumer-traceability. The 10-cycle `TROPO_SKIP_ENFORCEMENT_GATE=1` bypass pattern (v1.40-v1.49) happened because `subsystem-registry.jsonl` was specified across capsules but never built as governed substrate. This capsule structures the type so future registries can't drift the same way.

---

## 2. Schema

### Required Frontmatter (beyond `project.capsule`)

| Field | Type | Constraint |
|---|---|---|
| `type` | literal | Must be `registry` |
| `registry_name` | string | Canonical short name (e.g., `subsystem-registry`, `main-vault`, `canonical-l0-projects`). Lowercase, hyphens. |
| `data_path` | string | Path (relative to vault root) of the data file this entry wraps (e.g., `.tropo-studio/registries/subsystem-registry.jsonl`). |
| `data_format` | literal | One of: `jsonl`, `yaml`, `json`, `markdown-table`. Drives parser selection for consumers. |
| `derivation_method` | literal | One of: `derived_at_rebuild` (rebuild-vault.py writes), `hand_authored` (Mike or executive maintains by hand), `appended_at_runtime` (runtime script writes incrementally; e.g., playbook-runs.jsonl). |
| `schema_pointer` | string | UID of canonical schema source (capsule UID, or `inline` if schema declared in this entry's body §Schema section). |
| `consumers` | array of UIDs | Substrate UIDs that READ from this registry (capsules, scripts, validators, hubs). May be empty `[]` for new registries; populates as consumers wire up. |
| `subsystem_hub` | array | MUST include `8dd772a0` (tropo-governance) + the Registries hub `7e93ed75` **(v1.1 member_of DISAMBIGUATE: subsystem membership moved here from `member_of`)**. |
| `member_of` | array | optional; true organizational parent (the registries collection / non-hub). |

### Optional Frontmatter

| Field | Type | Constraint |
|---|---|---|
| `producers` | array of UIDs | Substrate UIDs that WRITE to this registry. For derived-at-rebuild: typically `[<rebuild-vault.py-related-UID>]`. For hand-authored: typically `[<owner-agent-UID>]`. For appended-at-runtime: typically `[<runtime-script-UID>]`. |
| `row_count_at_last_rebuild` | integer | Optional; rebuild-vault.py may populate at derivation time for derived registries. Honest current-state signal. |
| `last_derived_at` | timestamp | Optional; for `derived_at_rebuild` registries — when rebuild last wrote this. |
| `grandfathered_releases` | array | For `subsystem-registry` specifically: list of release UIDs that pre-date Rule 11 enforcement and skip validation. Inherits from existing grandfathering list. |

---

## 3. Rules

1. **Wrapper-entry-required.** Every data file at `.tropo-studio/registries/*.{jsonl,yaml,json}` MUST have a corresponding `type: registry` vault entry. Free-floating data files violate this rule; v1.50+ retrofit pass closes existing gaps.

2. **subsystem_hub-includes-Registries-hub.** Every registry's wrapper entry MUST include `7e93ed75` (Registries hub) + `8dd772a0` (tropo-governance) in `subsystem_hub:` (v1.1 member_of DISAMBIGUATE — was `member_of:` pre-v1.1; `member_of:` is now the optional true organizational parent per core.capsule v1.5 Rule 9). This makes the registry queryable via the hub's cascade + collections rendering.

3. **derivation_method-honesty.** The declared `derivation_method:` must match actual production reality. If a registry claims `derived_at_rebuild` but is also hand-edited, that's substrate-dishonest; fix by either (a) stopping hand edits, or (b) flipping to `appended_at_runtime` if runtime + rebuild both write.

4. **data_path-resolution.** The `data_path:` MUST resolve to an existing file at vault rebuild time. Missing data file with active wrapper entry is a substrate-coherence violation (ERROR at v1.52+ once retrofit pass closes existing gaps).

5. **consumers-as-traceability.** When a new consumer wires up to a registry (e.g., a new validator reads it), the consumer's UID should be added to the registry wrapper's `consumers:` array. Honor-system v1.50-v1.51; mechanical enforcement at v1.52+ via a validator that scans consumer-side `reads_from:` declarations.

---

## 4. Validation Checks

| Check | Description | Severity |
|---|---|---|
| `check_registry_required_fields` | All required frontmatter fields present (type, registry_name, data_path, data_format, derivation_method, schema_pointer, consumers, subsystem_hub). | ERROR |
| `check_registry_data_path_exists` | `data_path` resolves to an existing file under vault root. | ERROR |
| `check_registry_subsystem_hub` | `subsystem_hub:` includes `7e93ed75` (Registries hub) + `8dd772a0` (tropo-governance). Renamed from `check_registry_member_of_hub` at v1.1 member_of DISAMBIGUATE. | WARN → ERROR at v1.52 |
| `check_registry_derivation_consistency` | If `derivation_method: derived_at_rebuild`, registry's `last_derived_at` should be ≤ 24h old (stale registries indicate rebuild-vault.py gap). | WARN |
| `check_registry_consumers_traceability` | Substrate-wide grep for files that read `data_path` should have UIDs matching `consumers:` array. | WARN at v1.51 → ERROR at v1.52 |

---

## 5. Composition

### With `release.capsule` v3.4 (Rule 11+12)

`subsystem-registry.jsonl` (the registry created by this capsule's first instance) IS the substrate Rule 11 + Rule 12 enforce against. Before v1.50, the registry was specified-but-never-built; release.capsule v3.4 Rule 11 was bypass-only-enforced. After v1.50: registry exists; Rule 11/12 enforces clean; `TROPO_SKIP_ENFORCEMENT_GATE=1` retires to emergency-only use.

### With `subsystem-hub.capsule` v1.5

Each subsystem hub's `release_history:` field is bidirectional pair with `subsystem-registry.jsonl` rows. The hub-side records per-release `summary:` + `registry_uid:`; the registry-side records the cross-cut. Same shape captured twice for different reader-question access patterns.

### With `pipeline.capsule` v2.4

Dev-pipeline step 4 (`update-subsystem-canonical-docs`, UID 9d4f7e21) writes to `subsystem-registry.jsonl` at ship-time via its executor module. The registry IS the substrate this step produces; the registry-typed wrapper entry is the governance shell.

### With `project.capsule`

Registries are typed projects (lifecycle: standing; standing-evergreen registries that ship across cycles). Inherit owner/status/state from project.capsule.

---

## 6. Lifecycle

- **Creation:** Author the `type: registry` wrapper entry at `vault/files/<uid>.md`. Create the data file at `data_path` (or, for derived registries, run the deriving script). Update `consumers:` as consumers wire up.

- **Update:** For `derived_at_rebuild` registries: just edit the deriver (rebuild-vault.py). For `hand_authored`: edit the data file directly. For `appended_at_runtime`: rows append via runtime scripts.

- **Retirement:** A registry retires when its consumers all retire OR when its data is absorbed into a different registry. Wrapper entry flips to `state: archived` + `status: retired`; data file may be preserved as honest historical record or recycled per Deletion Discipline.

---

## 7. Provenance

- **v1.0 authored 2026-05-22 by Argus A79** as part of v1.50.0 Phase 1 grooming sweep registry primitive establishment work. Per Mike-A79 directive 2026-05-22 verbatim: *"i say fix it all while you have all the context - it's way more efficient. v1.49 is shipped, this is not a blocker."* — scope absorbed full retrofit into v1.50 (registry primitive + Registries hub + subsystem-registry + 4 existing retrofit wrappers).
- **Architectural trigger:** Mike-A79 framing 2026-05-22: *"we are a graph, after all. each registry should have some sort of member_of: a master registry collection or object, and link to tropo-subsystems, probably under governance."* The capsule structures the type so registries become first-class substrate.
- **Companion artifacts:** [Registries hub (7e93ed75)](../../vault/files/7e93ed75.md); [subsystem-registry wrapper (880a9e5a)](../../vault/files/880a9e5a.md); 4 retrofit registry wrappers (3a1fa720 + 57476b03 + 6dbcd7c8 + ce068ba4).

---

*registry capsule | v1.0 | UID `55a57893` | Authored Argus A79 2026-05-22 | v1.50.0 registry primitive establishment*
*"Free-floating data files are invisible to the graph. Typed wrappers make them substrate."*
