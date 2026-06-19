---
uid: 3210818a
name: "agent-configurator"
type: capsule-definition
extends: core
version: 2.2
tier: os
author: tropo
created: 2026-04-17
modified: 2026-04-27
created_by: argus-a27
modified_by: argus-a37
status: locked
supersedes_version: "2.1"
schema_version: 2
extraction_scope: ship
governed_by: e6d373bc
aligned_with: e6c3f410 # ADR-032 — Three-Layer Boot Configuration Model
member_of:
  - "99ed55fd"   # tropo-agents (v1.8 Stream B1 backfill)

---

# agent-configurator — Capsule Definition v2.1

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Tropo Playbook Specification v2.2 (e6d373bc)](../../vault/files/e6d373bc.md) |
| Aligned with | [ADR-032 — Three-Layer Boot Configuration Model (e6c3f410)](../../vault/files/e6c3f410.md) |
| Extends | `core` |

*The per-agent activation artifact. The single file Mike attaches to boot an agent. Self-executing on first read.*

---

## Version Note

**v2.1 (2026-04-20, Argus A29)** — Cold-boot 039 remediation. Closes gaps found by [sa.cold-boot 039 stranger test](../../agents/sa/sa.cold-boot/activation-log/039-argus-a29-record.md) against v2.0: adds §Authoring Protocol (UID minting + registry update), expands §Optional: Compiled Output with no-filesystem-access branch + compiled-artifact frontmatter schema + build-activation.playbook forward-spec, adds §Validation tier-unreachable halt semantics, adds §Migration Protocol for existing monolithic files, clarifies §State Machine scope (instances, not capsule file), pins §One Per Agent Rule to per-vault. ADR-035 ([a7c4e5b2](../../vault/files/a7c4e5b2.md)) is now `status: accepted`, so the capsule's citation is compliant with Surface 4.

**v2.0 (2026-04-20, Argus A29, superseded)** — Reframed the canonical artifact as a **thin loader** that reads the three-tier boot configuration chain (ADR-032) at boot time, instead of a monolith with inlined Groups. Compiled output demoted to an **optional export** for attach-only deployments (marketplace, cold Claude.ai pastes, tester distribution). Metis G44 greenlight: 2026-04-19 in [channels/metis-argus.md](../../channels/metis-argus.md).

**v1.0 (2026-04-17, Argus A27, superseded)** described the canonical artifact as a monolithic compiled file that inlined Groups 0–5 with hardcoded paths. That framing contradicted what Vela V31 shipped on 2026-04-19 — thin loaders executing the ADR-032 three-tier chain at boot time. v2.0 named the shipped reality as canonical; v2.1 hardened the spec.

---

## Intent

The agent-configurator is the activation artifact for one specific agent — the single file Mike attaches to boot that agent. It lives at `agents/<name>/<name>-activation.md`.

**The canonical form is a thin loader.** The loader:
- Declares agent identity and soul-letter path
- Delegates the activation sequence to [`.tropo/playbooks/agent-activation.playbook.md` (99341618)](../playbooks/agent-activation.playbook.md)
- Points at the three-tier boot configuration chain (ADR-032 — [e6c3f410](../../vault/files/e6c3f410.md)) so the playbook can resolve vault-specific and agent-specific extensions
- Contains a pre-response directive block that halts the agent until Groups 0–5 complete

The loader does NOT inline the activation sequence. It does NOT hardcode tier content. It names pointers; the playbook and tier extensions do the work.

**Why thin loader, not monolith:** the three-tier chain (Tier 1 OS, Tier 2 vault, Tier 3 agent) is the governance model. Inlining Groups into the configurator re-copies Tier 1 and Tier 2 content into every agent's activation file, creating a drift surface that updates to Tier 1 or Tier 2 do not automatically close. The thin loader reads live tiers at boot; updates to any tier land for every agent on the next boot.

**Why the name stays `agent-configurator`:** the artifact identity — *"the file Mike attaches to boot an agent"* — is unchanged. Only the internal structure changed. Renaming to `activation-loader` would churn `type:` fields across six activation files and the fresh vault for purity with no functional win. Per [crew scope lock](../../.tropo-studio/memory/crew-scope-lock-gtm-focus.md) discipline: less ceremony, more work.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `type` | string | Must be `agent-configurator` |
| `version` | semver | e.g., `"2.0"` |
| `agent` | string | The agent this configures (e.g., `vela`, `metis`, `argus`) |
| `role` | string | The agent's role title |
| `governs` | uid | The activation playbook this loader delegates to (typically `99341618`) |
| `aligned_with` | uid | The boot-configuration ADR (`e6c3f410` for ADR-032) |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `supersedes` | string | The prior version's UID or filename |
| `compiled_output` | path | If an optional compiled export has been generated, the path to it |
| `cold_boot_verified` | boolean | `true` once verified by sa.cold-boot or equivalent stranger test |
| `cold_boot_record` | string | Path to the sa.cold-boot activation record that verified this |

---

## State Machine

**Scope:** this state machine governs agent-configurator **instances** (one per agent, per vault). The capsule file itself has its own versioning — see §Version Note above. Do not confuse the two.

```
draft → active → superseded
```

| State | Meaning |
|-------|---------|
| `draft` | Being written or not yet cold-boot verified. Do not attach to a live session. |
| `active` | Cold-boot tested and approved. Mike attaches this at every boot. |
| `superseded` | Replaced by a newer version. Keep in `agents/<name>/` for history — do not delete. |

**Transition rules:**
- `draft` → `active` requires a passing cold-boot test (sa.cold-boot PASS, or architect walk PASS with explicit approval).
- Only one agent-configurator per agent per vault may be `active` at any time (see §One Per Agent Rule below).

---

## Required Structure

Every agent-configurator is a thin loader and must contain the following sections, in this order:

### 1. Frontmatter

Per the Required Frontmatter table above. `governs:` points at the playbook UID; `aligned_with:` points at ADR-032.

### 2. Pre-response directive block

An HTML comment at the top of the body:

```
<!--
FOR THE AGENT READING THIS:

DO NOT RESPOND TO THE HUMAN YET.
DO NOT SAY HELLO. DO NOT ACKNOWLEDGE THE PROMPT.

Execute the activation playbook and the three-tier boot chain before responding.
You are not [Agent Name] until Group 5 fires and you deliver the startup signal.
-->
```

This block is the enforcement gate. An agent reading the loader must see this directive before any other content.

### 3. Identity section

Short (under 200 words). Names:
- Role and charter path
- Soul letter path (loads first in Group 2 per Tier 3 extension)
- Status card path
- Generation log path
- Briefing package path

This section is the human-readable description. It does NOT inline Groups — it names pointers the playbook resolves.

### 4. Activation Procedure section

Declares, in one short paragraph:
- The playbook file path (typically `.tropo/playbooks/agent-activation.playbook.md`) and version (v2.2 or later)
- The three tiers the playbook will read, each named with its UID:
 - Tier 1: `.tropo/boot-config.md` (OS floor)
 - Tier 2: `.tropo-studio/agent-boot.extension.md` (vault defaults)
 - Tier 3: `agents/<name>/agent-boot.extension.md` (agent-specific)
- The halt-until-milestone rule ("Do not respond to Mike until the `[Agent] Active` milestone fires in `run.jsonl`.")

This section is 5–15 lines. It does NOT copy playbook steps or tier content.

### 5. Retirement pointer

A one-paragraph section pointing at `.tropo/playbooks/agent-retire.playbook.md` and stating the hard rule: never ask the human if the session is ending.

### 6. Migration / Change-log notes (optional)

For loaders that replaced older monolithic activation files, include a short migration note identifying the prior version, the restructuring author, and the archive path. Example pattern: [agents/argus/argus-activation.md](../../agents/argus/argus-activation.md) v2.0 migration note.

---

## File Location

Agent-configurators live at:

```
agents/<name>/<name>-activation.md
```

They do NOT live in:
- `vault/files/` — agent-configurators are not ledger entries
- `.tropo/playbooks/` — agent-configurators are not OS playbooks
- Any shared location — each configurator is agent-specific

---

## One Per Agent Rule

**Within a vault,** only one agent-configurator per agent may have `state: active` at any time. When a new version is published, update the old one's state to `superseded` before marking the new one `active`. Cross-vault scope: the same agent name MAY have distinct `active` configurators in different vaults (marketplace distribution, forks, parallel deployments) — this is expected, not a violation.

## Authoring Protocol

When a new agent-configurator is written (new agent or new version of an existing agent):

1. **Generate the UID.** Use the core UID primitive (8-hex random, verified unique against the vault index). For Argo vault authoring, this is `scripts/generate-uid` or equivalent; agents writing directly must ensure the UID does not collide.
2. **Update [`.tropo-studio/registries/agent-registry.yaml`](../../.tropo-studio/registries/agent-registry.yaml)** with the new agent's UID, path, class, and identity per the matched-primitives topology ([adac1f10](../../vault/files/adac1f10.md)) — agent-configurators are governed identity records per [ADR-032 (e6c3f410)](../../vault/files/e6c3f410.md).
3. **Run `python3 .tropo/scripts/rebuild-vault.py --apply`** to propagate any vault entries into `vault/00-index.jsonl`. Note: agent-configurators live at `agents/<name>/<name>-activation.md`, discoverable via folder listing — the agent's identity record in `agent-registry.yaml` is the canonical lookup surface.
4. **Dispatch cold-boot verification** (see §Validation) before marking `state: active`.

A stranger agent authoring a new executive cannot complete these steps from the capsule alone — registry update is a vault-operations task. Coordinate with the vault administrator (or Vela as delegate in Argo).

## Soul Letter and Charter Authoring

A complete new-agent authoring workflow requires more than the activation file. The loader names five pointers (charter, soul, status, generation log, briefing) that each need their own governed artifacts:

- **Soul letter** (`agents/<name>/<name>-soul.md`) — read first in Group 2; establishes character before context. No dedicated capsule yet; pattern lives in existing soul letters (see [vault/files/bfd441f1.md](../../vault/files/bfd441f1.md)).
- **Charter** (`agents/<name>/<name>-charter.md`) — declares scope, write access, operational parameters. Pattern lives in existing charters.
- **Status card** (`agents/<name>/<name>-status.md`) — generation tracker. Pattern in existing status cards.
- **Generation log** (`agents/<name>/generation-log.md`) — tabular append-only identity record per [ADR-028](../../vault/files/3e8f1a9c.md).
- **Briefing** (`agents/<name>/transfers/living-transfer.md`) — predecessor handoff; written at retirement.

These artifacts are not governed by this capsule. Authoring a new executive is a multi-artifact operation; agent-configurator is one component.

---

## The Tier Chain This Loader Delegates To

The activation playbook reads three tiers in Group 0 (Step 0.1 → 0.3), per [ADR-032 (e6c3f410)](../../vault/files/e6c3f410.md):

- **Tier 1 (OS floor):** `.tropo/boot-config.md` — universal Group structure and hard gates. Cannot be overridden. A failed read HALTS activation in established vaults (Tier Reachability rule, ADR-032 amendment 2026-04-19).
- **Tier 2 (vault defaults):** `.tropo-studio/agent-boot.extension.md` — vault-wide required reads, channel defaults, fleet-ops requirement. Composes with Tier 1.
- **Tier 3 (agent-specific):** `agents/<name>/agent-boot.extension.md` — soul loading declaration, harness orientation, sa.* commissioning list, pre-design checks, write scope, conditionalized channel reads. Composes with Tiers 1 and 2.

The loader does not duplicate any tier's content. It names the playbook; the playbook reads the tiers.

---

## Optional: Compiled Output (attach-only deployment)

**When compilation is needed.** The thin-loader pattern assumes a harness that can chain-read the tier files (Claude Code + filesystem, Cursor + filesystem, Cowork, etc.). In three deployment contexts the harness cannot chain-read:

1. **Cold Claude.ai pastes.** A user pastes one file into a fresh web chat. The tier files are not in the LLM's context.
2. **Starter-vault tester shipments.** A tester runs a fresh download with no harness wiring. The tier files exist on disk but the LLM has not been given filesystem access yet.
3. **Marketplace distribution.** Published Playbooks and governed agents run in contexts Tropo does not control.

In these contexts, a compiled single-file export of Tier 1 + Tier 2 + Tier 3 + the playbook is required.

**Compilation is OPTIONAL and is NOT the canonical form.** It is an export from the canonical thin loader + live tier files. The compiled artifact is a snapshot; if the tiers change, the compiled artifact goes stale and must be regenerated.

**Compilation vehicle.** A dedicated playbook, `.tropo/playbooks/build-activation.playbook.md`, is the compilation vehicle. As of 2026-04-20, this playbook is deferred (v1.3+ scope per Metis G44 greenlight). The v2.1 capsule specifies its required behavior so a future author can implement it against this spec alone.

**Compilation algorithm (build-activation.playbook.md forward-spec):**

1. **Read source loader** at `agents/<name>/<name>-activation.md`. Verify its `type: agent-configurator` and `version: ≥2.0`.
2. **Resolve the three tiers** per [ADR-032 (e6c3f410)](../../vault/files/e6c3f410.md). Tier 1 at `.tropo/boot-config.md`, Tier 2 at `.tropo-studio/agent-boot.extension.md`, Tier 3 at `agents/<name>/agent-boot.extension.md`. Capture each file's UID and last-modified timestamp.
3. **Resolve the activation playbook** via the loader's `governs:` field. Capture UID and last-modified.
4. **Assemble the compiled output** as a single markdown file with the following section order:
 - Frontmatter (schema below)
 - Pre-response directive block (verbatim from source loader)
 - `# [Agent Name] — Compiled Activation Artifact` heading
 - `## Identity` (verbatim from source loader)
 - `## Activation Procedure (inlined)` — replaces the thin-loader's pointer. Inline the playbook's Groups 0–5 content here, followed by three subsections: `### Tier 1 — OS Boot Config`, `### Tier 2 — Vault Extension`, `### Tier 3 — Agent Extension`, each containing the full body of the corresponding tier file.
 - `## Retirement` (verbatim from source loader + inline retirement playbook body if used)
 - `## Compilation Provenance` — auto-generated section naming source UIDs, timestamps, compile agent, and staleness instructions.
5. **Write output** to `agents/<name>/<name>-activation.compiled.md` (convention) or a caller-specified path.
6. **Write back to source loader** two fields: `compiled_from: <compiled-artifact-path>` and `compiled_at: <ISO-8601 timestamp>`.

**Compiled artifact frontmatter schema (required fields on the output):**

| Field | Type | Semantics |
|-------|------|-----------|
| `type` | literal | `"agent-configurator-compiled"` — distinct from `agent-configurator` to prevent confusion with source loaders |
| `source_loader_uid` | UID | UID of the thin loader this was compiled from |
| `source_tier_1_uid` | UID | `b7e3a291` (or vault's Tier 1 UID) at `compiled_at` |
| `source_tier_1_modified` | ISO 8601 | Tier 1's `modified:` timestamp at `compiled_at` |
| `source_tier_2_uid` | UID | Vault Tier 2 UID at `compiled_at` |
| `source_tier_2_modified` | ISO 8601 | Tier 2's `modified:` timestamp at `compiled_at` |
| `source_tier_3_uid` | UID | Agent Tier 3 UID at `compiled_at` |
| `source_tier_3_modified` | ISO 8601 | Tier 3's `modified:` timestamp at `compiled_at` |
| `source_playbook_uid` | UID | Activation playbook UID (`99341618` for v2.2) at `compiled_at` |
| `compiled_at` | ISO 8601 | When the compilation ran |
| `compiled_by` | string | Agent that ran the compilation |
| `agent` | string | Same as source loader |
| `role` | string | Same as source loader |

These eight source-UID + timestamp fields are the evidence that the staleness rule below operates against. Without them, staleness cannot be checked.

**Staleness rule — two branches.**

- **If the reader HAS filesystem access:** per [ADR-035 Declared-Presence Validation Rule (a7c4e5b2)](../../vault/files/a7c4e5b2.md), the reader MUST verify that each `source_tier_*_modified` and `source_playbook_*_modified` timestamp matches the current on-disk file. Any mismatch means the compiled artifact is stale. HALT, surface the staleness, and regenerate before proceeding.
- **If the reader HAS NO filesystem access** (the defining case for compiled artifacts — cold Claude.ai pastes, marketplace distributions): the staleness check cannot be performed by the reader. Responsibility for freshness falls to the **distributor** (the party who generated and published the compiled file). The distributor MUST regenerate before publishing. The reader accepts the artifact as-provided; no check is attempted. This preserves the primary use case of compiled artifacts (self-contained attach-only boot) without violating ADR-035, because Surface 2 reachability is satisfied by the compilation itself — the tiers were reachable at `compiled_at`, captured inline, and no further external resolution is required by the reader.

Until `build-activation.playbook.md` lands, no compiled artifacts ship in v1.2. The v2.1 spec above is sufficient for a v1.3+ author to implement against.

---

## Validation

Before marking `state: active`, the agent-configurator must pass a cold-boot test against the **thin loader + live tiers**:

1. Spawn `sa.cold-boot` (or equivalent stranger-agent).
2. Target: `agents/<name>/<name>-activation.md` plus the declared Tier 1, Tier 2, Tier 3 files.
3. Context: *"This is the activation artifact for [Agent Name] plus its tier chain. Could a stranger agent, reading only these files, correctly execute the full boot sequence including soul loading, identity gates, memory compaction, and startup signal per the activation playbook v2.2?"*
4. Task: mental walkthrough of Groups 0–5, flag any gap where a path is missing, a tier reference is unreachable (per [ADR-035 (a7c4e5b2)](../../vault/files/a7c4e5b2.md)), or a step is ambiguous.
5. Verdict must be PASS (or PASS-WITH-GAPS where only P2 polish remains) before `state: active` is assigned.

**Tier unreachability during cold-boot testing.**

A cold-boot test differs from a runtime boot in what "unreachable" means. At runtime, ADR-035 Surface 1 halts activation on an unreachable tier. During cold-boot testing, the test is verifying whether the artifact *describes* a reachable chain — not whether the chain is reachable at test time.

- **Permanently missing tier file** (file never existed, path typo in loader, tier file deleted): the artifact under test is defective. Test verdict FAIL on this gap.
- **Temporarily unreachable tier file** (permission error, network mount stutter, file lock, I/O error): the test itself is unreliable, not the artifact. The test retries up to 3 times with 5-second backoff. If still unreachable after 3 attempts, test result is INCONCLUSIVE (distinct from PASS/FAIL) — the stranger agent reports which tier was unreachable and the test is re-dispatched later. An INCONCLUSIVE result does NOT permit `state: active` transition.
- **Tier reachable but inconsistent with loader's declaration** (e.g., loader says `governs: 99341618` but target has a different UID): artifact defective. Test verdict FAIL.

The distinction matters because transient test-time failures should not prevent a correct artifact from locking; permanent structural failures must block the lock.

For compiled artifacts (optional export), an additional test validates that the compiled file alone produces the same boot behavior as the thin loader + live tiers — the compilation is lossless.

---

## Migration Protocol (existing monolithic v1.0 files → v2.0+ thin loaders)

When an existing monolithic activation file (v1.0 pattern — inlined Groups 0–5) is migrated to a thin loader:

1. **Archive the monolith.** Copy `agents/<name>/<name>-activation.md` (the v1.0 monolith) to `agents/<name>/archive/<name>-activation-v1.0-monolith.md`. Preserve frontmatter exactly; add `archived_at:` and `archived_by:` fields to the archive copy.
2. **Draft the thin loader.** Write the new `agents/<name>/<name>-activation.md` per §Required Structure. Minimum body is identity pointers + Activation Procedure + Retirement — roughly 60 lines vs. the 200–300 lines the monolith carried.
3. **State transition order (atomic within a single operation):**
 - Mark the archived copy's frontmatter `state: superseded` and add `superseded_by:` pointing at the new loader's UID.
 - Write the new loader at `state: draft`.
 - Dispatch cold-boot verification against the new loader + live tiers.
 - On PASS: transition new loader to `state: active`.
4. **Reference example.** The [argus-activation.md](../../agents/argus/argus-activation.md) file is the canonical reference: Argus A27's 287-line monolith was restructured to a 60-line thin loader by Vela V31 on 2026-04-19; the archive lives at `agents/argus/archive/argus-activation-v1.0-monolith.md`. Use this pattern verbatim for other agents.
5. **Registry update.** Per §Authoring Protocol, update `.tropo-studio/registries/agent-registry.yaml` with the new loader's UID. The archived monolith remains in the registry with `state: superseded`; do not remove.

Monolithic files at `state: active` in a vault today should be migrated as soon as capacity allows. There is no hard deadline — ADR-032 is back-compatible with existing monoliths until they are opportunistically migrated. But NEW agents MUST be authored as thin loaders; no new monoliths are permitted under v2.0+.

## Template

See `.tropo/templates/agent-configurator.template.md` for the blank thin-loader template. Use it when creating a new agent's configurator.

---

## Example — valid agent-configurator frontmatter (v2.0 thin loader)

```yaml
---
uid: d04ed94e
type: agent-configurator
version: "2.0"
agent: argus
role: "Chief Architect"
created: 2026-04-18
modified: 2026-04-19
created_by: argus-a27
modified_by: vela-v31
governs: 99341618 # Agent Activation Playbook v2.2
aligned_with: e6c3f410 # ADR-032 — Three-Layer Boot Configuration Model
supersedes: argus-activation-v1.0-monolith
---
```

(This is the actual frontmatter from [agents/argus/argus-activation.md](../../agents/argus/argus-activation.md) — the reference implementation shipped by Vela V31 on 2026-04-19.)

---

## Cross-References

- [ADR-032 — Three-Layer Boot Configuration Model (e6c3f410)](../../vault/files/e6c3f410.md) — the governance model this loader delegates to.
- [Agent Activation Playbook v2.2 (99341618)](../playbooks/agent-activation.playbook.md) — the execution engine the loader hands off to.
- [Tier 1 boot-config v1.1 (b7e3a291)](../boot-config.md) — OS floor.
- [Tier 2 vault extension (8a83579e)](../../.tropo-studio/agent-boot.extension.md) — vault defaults.
- [ADR-035 — Declared-Presence Validation Rule (a7c4e5b2)](../../vault/files/a7c4e5b2.md) — governs tier-chain reachability and compiled-artifact staleness checks.
- [channels/metis-argus.md](../../channels/metis-argus.md) — Metis G44 greenlight for the v2.0 amendment (2026-04-19).

---

*agent-configurator Capsule Definition | v2.1 | Argus A29 | 2026-04-20*
*v2.1 supersedes v2.0 (same session) — cold-boot 039 remediation: authoring protocol, compiled-artifact schema, build-activation forward-spec, tier-unreachable semantics, migration protocol, state-machine scope, one-per-vault scope.*
*v2.0 superseded v1.0 (Argus A27, 2026-04-17) — monolithic framing retired in favor of thin loader (ADR-032 three-tier chain canonical).*
*"The loader attaches. The tiers compose. The agent becomes itself."*
