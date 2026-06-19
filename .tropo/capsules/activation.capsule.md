---
uid: 4e8b21f0
name: "activation"
type: capsule-definition
extends: core
version: "1.0.3"
tier: os
author: argus-a58
status: locked
locked_by: argus-a58
locked_at: 2026-05-11
created: 2026-05-11
modified: 2026-06-09
created_by: argus-a58
modified_by: argus-a105
remediation_history:
  - version: "1.0.3"
    date: 2026-05-16
    by: argus-a68
    summary: "v1.35.0 absorption per R3 sa.skeptic-088 P1-4 + R5 sa.skeptic-089 P1-2. §2 Required Frontmatter agent_class enum + §4 Rule 7 enum extended to include `pipeline` — discriminates pipeline-runtime activations authored by pipeline-activate.py per pipeline.capsule v2.6 cascade contract (spec d2f8c194 §2.2). Pipeline activations carry placeholder values in agent/generation/model fields since they describe a runtime fire, not a persistent agent. Pre-v1.35.0 substrate emits no validator FAIL — tropo-validate.py's valid_classes already included `pipeline` at v1.34.0; this capsule amendment closes the canonical-substrate side of the gap."
  - version: "1.0.2"
    date: 2026-05-11
    by: argus-a58
    summary: "v1.22.0.3 bundled remediation per remaining sa.skeptic P1 findings. P1-3 §4 Rule 6 amended with explicit closure_reason: stale-sweep for non-stall idle (previously silent; now declared). P1-2 §5 Composes-With agent root projects bullet amended to declare agent_root_map.yaml at .tropo-studio/scripts/v1.21.0-agent-root-map.yaml as the canonical slug-to-UID lookup; validator existence-check noted as v1.23.0 candidate."
  - version: "1.0.1"
    date: 2026-05-11
    by: argus-a58
    summary: "v1.22.0 sa.cold-boot diagnostic surfaced two capsule gaps: (1) stale threshold locked at 7 days universally but Stream 3 design wants per-agent_class thresholds (sa.* should be ~2 hours, not 7 days); (2) Vela's stale-sweep authority to flip status: active → failed when closure_reason: harness-watchdog-stall is detected was not explicitly authorized in §4 Rule 6. Both gaps closed in this amendment: §2 Optional Frontmatter adds stale_threshold_hours field with class-defaults; §3 State Machine references per-class threshold; §4 Rule 6 amended to authorize Vela's sweep over both stale and failed transitions per-class."
enforced_enums:
  status: [active, retired, failed, stale, paused]
meta_status_rollup:
  in-progress: [active, paused]
  done: [retired, failed, stale]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9   # capsule-definition meta-capsule
pattern_exemplar: 7901662b   # governance-contract.capsule v1.0 — 5-section pedagogy reference (most recent Lock C exemplar)
aligned_with:
  - 5591f018   # v1.21.0 brief — Unified Agent-Activation Registry (walk-locked v0.2)
  - 99341618   # agent-activation.playbook v2.5 (boot path writes activation entries at Group 0)
  - 8b3f1d92   # Tropo Work v3 Architecture Specification
  - db0fd9b1   # SELF-HEALING.md (Path 1/Path 2 discipline applies)
  - a4f9e2b1   # Operating Principles v2.4 (Principle 8 — agent ≠ sleeve — informs continuous-identity rule)
composes_with:
  - 7901662b   # governance-contract.capsule (`.tropo-studio/registries/` folder governance)
  - 8a4e21c5   # subsystem-hub.capsule (parent governance; activation entries member_of: agent root + cycle activations)
  - c9b3e6f1   # write-gen-log-row.skill (pattern exemplar — substrate elevation reference; retired Stream 3 of v1.21.0)
member_of:
  - "8dd772a0"   # tropo-governance
  - "99ed55fd"   # Tropo Agents (activation entries are the agent-class lifecycle substrate)
tags: [capsule-definition, activation, agent-lifecycle, level-2-composable-graph, adr-016-substrate-invariant, adr-028-substrate-invariant, 5-section-pedagogy, v1.21.0-stream-1-authored, replaces-generation-log-capsule]
---

# activation — Capsule Definition v1.0

## 1. Intent

An `activation` is the typed primitive that captures **one agent session record** — the lifecycle-gated entity that knows *when an agent activated, by whom, with what model, what generation, what status, and when it closed*. It is the Level-2 node of the three-level composable graph (agent root project at Level 1; activation entry at Level 2; work attached at Level 3) declared by the [v1.21.0 brief 5591f018](../../vault/files/5591f018.md).

Activations exist because the registries landscape that preceded them fragmented agent-session state across five-plus overlapping surfaces (`agents/operations/scheduled-agent-registry.md`, `agents/registry.md`, `agents/child-agent-registry.md`, the empty `.tropo-studio/registries/playbook-runs.jsonl`, scattered per-SA `activation-log/` markdown files). The fragmentation cost was 33-day fleet dormancy invisible to every agent because nothing aggregated "did fleet-ops dispatch today?" into one queryable surface. Founder caught it; no agent caught it. Activations collapse the fragmentation into a single typed substrate so the answer becomes a one-hop graph traversal.

An activation entry is **session-record**, not **governed-work**. It carries no body content of substance — its job is the lifecycle frontmatter. The session's actual outputs (tasks, decisions, design-briefs, sub-projects, transfers) attach to the activation via `member_of:` and live as their own typed primitives. Activations are slim metadata containers with stop-criteria; projects are open-ended work containers with no intrinsic stop-criteria. The two are structurally distinct (per walk-lock Q1).

**What's NOT an activation:**
- A dev-pipeline cycle activation root (those stay `type: project` — they're release-scoped, multi-stream, strategic; they live alongside `type: activation`, not as a subtype).
- A long-lived agent root project (Level 1; `type: project` per Stream 0a).
- A capsule, skill, or playbook (kernel-class typed primitives; declarations not instances).

**What IS an activation:**
- Every executive boot (`agent: argus` + generation `A58`)
- Every director session (`agent: d.pm` + generation `P5`)
- Every sa.* commission (`agent: sa.vault-janitor` + generation `sa.vault-janitor-008`)
- Every scheduled fleet dispatch
- Every child-agent spawn (`activated_by:` resolves to the parent activation)
- Permanent-agent activations (Tropo, Cosmo) — one-per-continuous-identity

The failure mode this primitive prevents: **execution history living in private agent state** (gen-logs, transfers, run-folder jsonl) where it is unaggregatable. With every activation a typed entity, "did agent X run today?" becomes a vault query filtered by `agent: X` + `activated_at:`. "What artifacts did session Y produce?" becomes `member_of: <activation-uid>` graph walk. Provenance for free.

---

## 2. Schema

### Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|---|---|---|
| `type` | literal | `activation` |
| `name` | string | Human handle — `<agent-slug>-<generation>` (e.g., `argus-a58`, `sa.vault-janitor-008`, `cosmo-m1`). Unique across active activations. |
| `agent` | string | Agent slug. Must resolve to an active agent root project via `agent_root:`. |
| `agent_root` | UID | Pointer to the Level-1 agent root project. Resolves through `agent_root_map.yaml` or vault index. |
| `agent_class` | enum | One of: `executive` / `director` / `sa` / `cosmo` / `tropo` / `worker` / `child-agent` / `pipeline` (v1.35.0 — discriminates pipeline-runtime activations authored by `pipeline-activate.py`; pipeline activations describe a runtime fire, not a persistent agent, and carry placeholder values in `agent:` / `generation:` / `model:` fields). Names the activation class. |
| `generation` | string | Generation identifier — `A58` / `V43` / `G51` / `sa.vault-janitor-008` / child-agent slug. Format depends on `agent_class:` (executive/director uses prefix+number; sa.* uses `<slug>-NNN`; child-agent uses spawner-relative). |
| `model` | string | Sleeve identifier — `claude-opus-4-7[1m]` / `claude-sonnet-4-6` / `claude-haiku-4-5` / `gpt-5.5` / etc. |
| `platform` | string | `Claude Code` / `Claude Cowork` / `Claude Web` / `Gemini CLI` / `Cursor` / etc. |
| `activated_at` | ISO timestamp | Boot timestamp. Format `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SSZ`. |
| `activated_by` | UID or `"user"` | Parent activation entry UID for child agents + sa.* dispatches; `"user"` for top-level executive boots initiated directly by the principal. |
| `status` | enum | One of: `active` / `retired` / `failed` / `stale` / `paused`. Lifecycle state — see §3. |
| `member_of` | UID array | At minimum `[<agent_root>]`. May include `[<cycle-activation-root>]` for sessions tied to dev-pipeline activations. |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `commissioned_purpose` | string | sa.* dispatches: one-line prompt gist (≤200 chars). Captures what the dispatch was asked to do. Used by rendered views to answer "what did this dispatch try to do?" |
| `retired_at` | ISO timestamp | Set when status flips out of `active`. Null while `active`. |
| `closure_reason` | enum | Context for the status transition. Values: `clean-retirement` / `context-overflow` / `parallel-boot-violation` / `stale-sweep` / `dispatch-failure` / `harness-watchdog-stall` / `[SHUTDOWN]` / `paused-by-user`. |
| `run_folder` | string (path) | Pointer to `playbook-runs/<run>/` folder for workspace + run.jsonl blob storage. Optional — sa.* dispatches may use `agents/sa/<slug>/activation-log/<NNN>/` instead during the v1.21.0 → v1.22.0 sa.* substrate transition. |
| `transfer_uid` | UID | Pointer to the living transfer authored at retirement. Executives only; sa.* and worker activations don't produce transfers. |
| `predecessor` | UID | Pointer to the previous activation entry for this `agent:`. Provides cheap generation-chain walk. Null for first-ever activation per agent. |
| `successor` | UID | Pointer to next activation entry once successor activates. Bidirectional with predecessor on the successor's side. Null while no successor exists. |
| `session_summary` | string | Optional one-paragraph summary (≤1000 chars). Captures session arc at a glance. Never auto-lifted from legacy gen-log content (per walk-lock follow-up b). |
| `cycles_shipped` | UID array | For executive sessions that shipped one or more dev-pipeline cycles, list the release entry UIDs. |
| `path_2_filed` | UID array | Path 2 dogfood UIDs filed by this activation. |
| `defects_caught_inline` | integer | Count of Path 1 fixes done inline during the activation. Cheap signal for self-healing health. |
| `boot_smoke_test_subject` | bool | True if this activation served as a fresh-boot smoke test for a substrate cycle. Used by validator to confirm smoke tests are recorded. |
| `validated_at` | ISO timestamp | When validator last confirmed schema conformance + invariants. Updated by rebuild-vault.py. |
| `stale_threshold_hours` | integer | **(v1.0.1 amendment)** Hours of `run.jsonl` inactivity after which an `active` entry flips to `stale` (or `failed` per Rule 6 amendment below). Default by `agent_class`: `sa` = 2 (sa.* dispatches are minute-scale; staleness should surface fast); `worker` = 6 (scheduled fleet runs are hour-scale); `executive` / `director` / `cosmo` / `tropo` = 168 (= 7 days; matches gen-log historical pattern); `child-agent` = 4 (inherits from spawner unless overridden). Override allowed when a specific activation has known long-duration semantics. |

### Body shape

Activations are slim metadata; body is intentionally minimal. Required sections:

1. **`## 1. Session Pointers`** — Required. Link block: agent root project, predecessor activation (if any), input briefs (if any), input transfer (if any), run folder (if any).
2. **`## 2. Status`** — Required. Current status line + status timeline (transitions with timestamps + closure_reason once retired).
3. **`## 3. Outputs`** — Optional. Link block to artifacts produced by this activation (tasks, decisions, design-briefs, release entries, transfers). Maintained by `rebuild-vault.py`; manual edits stable.
4. **`## 4. Boot Diagnostic`** — Optional. One-paragraph capture of any diagnostic findings surfaced at Group 4 of boot. Brief; rich content lives in transfers.

Bodies stay short by design — substantive narrative belongs in the living transfer (per walk-lock follow-up b). Activations are slim because their job is queryability, not storytelling.

### Generation Format by Agent Class

| Class | Format | Example |
|---|---|---|
| `executive` | `<prefix><N>` where prefix is the agent's `generation_prefix` from the registry + N is monotonic per-agent | `A58` (Argus), `V43` (Vela), `G51` (Metis) |
| `director` | `<prefix><N>` | `P5` (d.pm) |
| `cosmo` | `M<N>` | `M1` |
| `tropo` | `T<N>` (when first commissioned) | `T1` |
| `sa` | `<agent-slug>-<NNN>` zero-padded 3-digit | `sa.vault-janitor-008`, `sa.cold-boot-149` |
| `worker` | `<agent-slug>-<NNN>` (scheduled fleet uses same pattern as sa.*) | `daily-vault-health-042` |
| `child-agent` | `<spawner-generation>.<N>.<role-slug>` | `a58.1.cold-boot-runner` |

---

## 3. State Machine

```
                  ┌──────────────────┐
                  │  status: active  │
                  └─────────┬────────┘
                            │
        ┌───────────────────┼───────────────────────────┐
        │                   │                           │
        ▼                   ▼                           ▼
status: retired      status: failed              status: stale
(clean close)        (forced close)              (no-activity sweep)
                            │
                            ▼
                  status: paused
                  (resumable; not terminal)
                            │
                            ▼
                  status: active  (resume)
```

| Status | Meaning |
|---|---|
| `active` | Activation is live. Agent is mid-session OR awaiting next interaction. |
| `retired` | Clean close — executive retirement playbook executed OR sa.* dispatch wrote `[SHUTDOWN]`. Terminal. |
| `failed` | Forced close — context overflow, parallel-boot violation (ADR-016), dispatch failure, harness-watchdog stall. Terminal. |
| `stale` | No `run.jsonl` events for ≥ `stale_threshold_hours` (per-class default; see §2 — sa.* = 2h, worker = 6h, executive/director/cosmo/tropo = 168h, child-agent = 4h). Flipped by Vela's Tier 1 stale-sweep. Terminal (cannot resume). |
| `paused` | Playbook-run paused waiting on external trigger. Resumable to `active`. |

**Valid transitions:**

- `active → retired` (via retirement playbook closure step OR sa.* `[SHUTDOWN]` write)
- `active → failed` (via context overflow detection, parallel-boot HALT, dispatch error)
- `active → stale` (via Vela's stale-sweep when no events ≥7 days)
- `active → paused` (via explicit pause signal)
- `paused → active` (via resume signal)
- `paused → failed` (via explicit give-up)

**No `retired → *` transitions.** Once retired, the activation is closed permanently. A new activation entry opens for the next generation. This is ADR-016 substrate enforcement: clean lineage requires terminal closure.

**No `failed → *` transitions** (except by remediation: a `status: failed` may be manually corrected to `status: retired` with `closure_reason: clean-retirement-post-remediation` if the failure was operational, not lineage-violating).

### Multi-day continuous sessions

Per walk-lock Q3: **one activation = one continuous identity** for executives, even when the session spans multiple calendar days or multiple ship cycles. The activation closes when status leaves `active`, not at calendar-day rollover or after a ship. A55's continuous v1.17.0 + v1.18.0 arc was one activation; A57's continuous v1.19.0 + v1.20.0 was one activation; V35's cross-laptop resume was one activation despite ADR-016 firing.

sa.* dispatches are different: each dispatch is a fresh ephemeral identity, so dispatch = activation entry. No multi-dispatch continuous identities for sa.*.

---

## 4. Validation Rules

### Governance Rules (8, in addition to core)

1. **One `active` activation per `agent:` slug.** Two activations with the same `agent:` slug both at `status: active` is a hard violation — this is ADR-016 substrate enforcement. The validator fires this check at every rebuild. The boot playbook's pre-flight (Group 1 Step 1.1) also catches it but the substrate check is authoritative.

2. **Generation monotonicity per agent.** For any two activation entries with the same `agent:` slug, the one with the later `activated_at:` must have `generation:` equal to the predecessor's generation + 1 (where generation parsing depends on `agent_class:` — executives parse `<prefix><N>` and compare N; sa.* parse `<slug>-<NNN>` and compare NNN). This is ADR-028 substrate enforcement. The boot playbook (Group 1 Step 1.2) also catches it but the substrate check is authoritative.

3. **`agent_root:` resolves to a live agent root project.** The UID must resolve to a vault entry with `type: project` and `name: agent-root-<agent>` where `<agent>` matches this activation's `agent:` field. Orphan activations (no agent root) are validation errors.

4. **`name:` matches the pattern `<agent>-<generation>`.** No exceptions; the name field carries the canonical handle. sa.* dispatches use `<slug>-<NNN>` with zero-padded 3-digit numbers.

5. **`activated_by:` resolves to a parent activation OR is the literal `"user"`.** Top-level executive boots use `"user"`; child agents + sa.* dispatches resolve to the parent activation UID. Parallel boots from `"user"` for the same agent are caught by Rule 1.

6. **`status: stale` and `status: failed` (stale-sweep variant) transitions are validator-driven, not authored.** An activation entry should never be authored at `status: stale`. Vela's Tier 1 sweep is the authorized writer for both: (a) `active → stale` when `run.jsonl` inactivity exceeds `stale_threshold_hours` for the agent_class (per v1.0.1 amendment) — **closure_reason MUST be set to `stale-sweep`** (v1.0.2 clarification per v1.22.0.3 sa.skeptic P1-3 finding; previously silent on which value fires for non-stall sweeps); (b) `active → failed` with `closure_reason: harness-watchdog-stall` when the inactivity is detected for an sa.* class activation specifically AND the dispatcher confirms harness-watchdog timeout (cross-checked via the dispatcher's own close-attempt log; if dispatcher already closed, Vela's sweep is no-op). Direct authoring at `stale` is a validation error. `failed` may also be authored at boot/dispatch time by the executing agent itself for context-overflow / parallel-boot-violation / dispatch-failure causes — those are not Vela-sweep territory.

7. **`retired_at:` present when `status` is terminal.** Required when status is `retired`, `failed`, or `stale`. Allowed null only while `active` or `paused`.

8. **Activation entries are vault-resident at `vault/files/<uid>.md` per post-v1.20.0 Vault convention.** No `.activation.md` suffix at agent-folder paths; activations are instances not kernel definitions (per kernel-file-naming rule 9b3e8c47).

### Validation Checks (8, WARN-severity at v1.21.0; ratchet to ERROR at v1.22.0)

1. `type: activation` exact
2. `name:` matches pattern `<agent>-<generation>`; `agent:` slug consistent
3. `agent_root:` resolves to a vault entry with `type: project` and `name: agent-root-<agent>`
4. **ADR-016 substrate:** at most one activation entry per `agent:` with `status: active`
5. **ADR-028 substrate:** `generation:` monotonically increases by exactly 1 per `agent:` (ordered by `activated_at:`)
6. `status:` ∈ {active, retired, failed, stale, paused}
7. `agent_class:` ∈ {executive, director, sa, cosmo, tropo, worker, child-agent, pipeline}
8. **Stale-sweep candidate:** `status: active` AND no `run.jsonl` events for ≥7 days → WARN (Vela's Tier 1 surfaces; flips to `stale` on her next boot)

Core checks inherited: UID uniqueness, UID immutability, type immutability, owner/created/modified invariants.

**Grace period:** v1.21.0 introduces this capsule at WARN severity. ERROR severity activates at v1.22.0 to allow the v1.21.0 boot playbook amendment (Stream 3) + write-activation-entry.skill landing (Stream 2) + first round of fresh boots to populate the registry with valid entries. Pattern mirrors v1.18.0 kb-article + v1.20.0 governance-contract grace handling.

---

## 5. Composes-With

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor for UID / owner / created / modified invariants.
- **[v1.21.0 brief — Unified Agent-Activation Registry (5591f018)](../../vault/files/5591f018.md)** — the design brief that walked this capsule's schema + lifecycle + invariants to walk-lock. Read for context on why specific field choices were made.
- **agent root projects (Stream 0a bootstrap)** — Level 1 of the graph; every activation `member_of:` an agent root. Live at `vault/files/<root-uid>.md` with `type: project`, `name: agent-root-<slug>`. **(v1.22.0.3 lock per P1-2 finding):** the `agent_root_map.yaml` reference at `.tropo-studio/scripts/v1.21.0-agent-root-map.yaml` is the canonical slug-to-UID lookup produced by the v1.21.0 Stream 0a bootstrap script and verified to exist at every release ship; rebuild-vault.py + write-activation-entry.py both read from it for slug resolution. Validator should verify the map file's continued existence; flagged as v1.23.0 candidate work.
- **[governance-contract.capsule v1.0 (7901662b)](governance-contract.capsule.md)** — `pattern_exemplar`; mirror of the 5-section pedagogy structure + folder-governance discipline for `.tropo-studio/registries/`.
- **[subsystem-hub.capsule (8a4e21c5)](subsystem-hub.capsule.md)** — parent governance. Activation entries `member_of:` Tropo Agents hub (99ed55fd) primarily, plus cycle-activation roots when the activation produces release-scoped work.
- **[write-activation-entry.skill](../skills/write-activation-entry.skill.md)** (v1.21.0 Stream 2) — canonical write abstraction. All writes to activation entries route through this skill — at boot (open), retirement (close), [SHUTDOWN] (close), stale-sweep (flip to stale), pause/resume (status flip).
- **[agent-activation.playbook v2.6 (99341618)](../playbooks/agent-activation.playbook.md)** (v1.21.0 Stream 3) — boot playbook. Group 0 Step 0.0b writes the activation entry alongside the run folder. Group 1 Step 1.3 retires the legacy gen-log row write (gen-log substrate retires this cycle); ADR-016 + ADR-028 hard-gates query the activation registry instead of the gen-log.
- **[agent-retire.playbook](../playbooks/agent-retire.playbook.md)** (v1.21.0 Stream 3 amendment) — retirement playbook. Closure step writes `retired_at:` + `status: retired` + optional `transfer_uid:` + `closure_reason: clean-retirement` to the activation entry.
- **transfer documents (`agents/<name>/transfers/living-transfer.md`)** — the canonical session-narrative document. Each transfer carries `member_of: [<activation-uid>]` going forward; the activation entry carries `transfer_uid:` back. Bidirectional pointer.
- **run.jsonl** at `playbook-runs/<run>/run.jsonl` — execution event log. Pointed at via `run_folder:`. The jsonl is workspace state; the activation entry is the typed governed index.
- **Tier 1 canonical substrate (8f6ea459)** (v1.21.0 Stream 3 amendment) — universal required outcome added: "activation entry written to registry."
- **rebuild-vault.py** — indexes activation entries; derives `.tropo-studio/registries/agent-activations.jsonl`; renders `00-tropo-nav/agents/<name>.md` per-agent lineage pages; renders `.tropo/scheduled-agents.md` fleet catalog. All four surfaces are derived from activation entries; activation entries are the single source of truth.
- **[SELF-HEALING.md (db0fd9b1)](../../vault/files/db0fd9b1.md)** — Path 1/Path 2 discipline applies to activation entry authoring. Trivial defects (typos, broken UID refs) fix in place; substantive defects (schema gaps, lifecycle ambiguity) file as tracked work-items.

### Composition with generation-log substrate (retiring in Stream 3)

The pre-v1.21.0 substrate stack — `agents/<name>/generation-log.md` + [write-gen-log-row.skill (c9b3e6f1)](../skills/write-gen-log-row.skill.md) + [generation-log.capsule (7f4a8d2e)](generation-log.capsule.md) + `sort-gen-log.py` + the gen-log invariant check inside `tropo-validate.py` — retires at v1.21.0 Stream 3. Their job generalizes into the activation registry stack:

- `write-gen-log-row.skill` → [`write-activation-entry.skill`](../skills/write-activation-entry.skill.md)
- `generation-log.capsule` → this capsule (`activation.capsule`)
- `sort-gen-log.py` → no replacement needed (entries are UID-addressable + sortable by `activated_at:` in the derived JSONL)
- gen-log invariant check → activation-registry invariants from §4 Validation Checks (graph-walkable; substrate-level)

The legacy `agents/<name>/generation-log.md` files were migrated to `vault/files/<uid>.md` with `type: document, status: archived, member_of: [<agent-root>]` per Stream 0b. They remain as honest pre-registry historical record; going-forward lineage queries hit the activation registry, not the archives.

### Composition with dev-pipeline activation roots (existing pattern)

Dev-pipeline cycles already author "activation root projects" — for example, v1.20.0's [activation root 32610cb0](../../vault/files/32610cb0.md) or v1.21.0's [activation root a3e2b18f](../../vault/files/a3e2b18f.md). Those stay `type: project` (cycle-scoped, multi-stream, strategic). They live alongside `type: activation` (agent-class, session-scoped). An artifact can `member_of:` both — e.g., a release entry carries `member_of: [<argus-a58-activation>, <v1.21.0-cycle-activation-root>]` declaring "this artifact came from Argus A58 mid-session AND it belongs to v1.21.0 cycle." The two patterns are complementary, not competing.

---

*activation capsule definition | LOCKED v1.0.2 (amended v1.22.0.3 per remaining sa.skeptic P1 findings — closure_reason + agent_root_map.yaml clarifications) | UID `4e8b21f0` | Authored by Argus A58 2026-05-11 | v1.21.0 Stream 1 origin; v1.22.0 amendment for per-class stale threshold + Vela failed-authority*
*"One typed entity per session, executive or sa.* or anything in between. Provenance for free. ADR-016 and ADR-028 become graph-walkable substrate invariants."*
