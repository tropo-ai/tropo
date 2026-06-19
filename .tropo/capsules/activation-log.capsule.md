---
uid: 8406c4f8
name: "activation-log"
type: capsule-definition
extends: core
version: "1.1"
supersedes_version: "1.0"
status: locked
locked_by: argus-a41
locked_at: 2026-05-01
owner: argus
created: 2026-05-01
created_by: argus-a41
modified: 2026-05-11
modified_by: argus-a55
schema_version: 2
governed_by: 222873b9
history_file: 2207c655
enforced_enums:
  status: [dispatched, complete, complete-via-salvage, blocked]
meta_status_rollup:
  in-progress: [dispatched]
  done: [complete, complete-via-salvage, blocked]
last_body_refactor: 2026-05-11
aligned_with: 7d3f9a2c  # sa/CAPSULE.md — universal commissioning protocol
composes_with: b4e2a718 # session-agent.capsule
member_of:
  - 8e4a2c1f   # v1.4.2 Stream 1
  - a4d1bc77   # v1.4.2 Release Plan
  - "99ed55fd"   # tropo-agents
tags: [activation-log, capsule-definition, audit-trail, governance, sa-record-shape]
---

# activation-log — Capsule Definition v1.1

| Relation | Target |
|---|---|
| Governed by | [capsule-definition meta (222873b9)](../../vault/files/222873b9.md) |
| Aligned with | [sa/CAPSULE.md (7d3f9a2c)](../../vault/files/e863a1e0.md) (universal commissioning protocol) |
| Composes with | [session-agent.capsule (b4e2a718)](session-agent.capsule.md) (governs sa.\* activation files) |
| Extends | `core` |

---

## 1. Intent

An activation-log record (`agents/sa/<name>/activation-log/<NNN>-*.md`) is the per-spawn record of a sa.\* commission — both the live IPC channel during the spawn AND the permanent historical record after termination. This capsule governs the shape of every record: required frontmatter, body conventions, state machine, validation checks.

Sibling to [session-agent.capsule (b4e2a718)](session-agent.capsule.md) (governs the activation FILE) and complementary to [sa/CAPSULE.md (7d3f9a2c)](../../vault/files/e863a1e0.md) (governs the commissioning PROTOCOL). This capsule governs the per-commission RECORD shape.

Failure mode prevented: heterogeneous record shapes that cannot be cited cross-document (V36's records had YAML frontmatter; A39's didn't; the `verification_artifacts:` array in release.capsule can't resolve UIDs that don't exist).

**Guiding principle:** the capsule's job is codification, not invention. Every required field is one V36's records already carry. The gap is enforcement, not discovery.

---

## 2. Schema

### Inheritance from core — explicit reconciliation

Activation-log records live at `agents/sa/<name>/activation-log/<NNN>-*.md` and are **per-spawn audit artifacts, not vault entries** (mirroring session-agent.capsule v1.2's pattern for sa.\* activation files). They declare `extends: core` for conceptual alignment + UID governance, but are not subject to core's check-in validation in the same way vault entries are:

| Core field | Applied to activation-log records? | How |
|---|---|---|
| `uid` | Yes | 8-hex, unique, immutable. Required for cross-document citation. |
| `type` | **Not present on records** | Records do not carry `type:`; `agent:` is the discriminator. |
| `status` | Yes | This capsule's 4-state machine (`dispatched / complete / complete-via-salvage / blocked`). |
| `stage` | **Not applicable** | Records are per-spawn audit, not stage-bucket pipeline entries. |
| `state` | **Not applicable** | `status:` covers the lifecycle dimension. |
| `title` | Not required | Header H1 + subtitle serve the catalog role. |
| `owner` | Inferred from `commissioned_by` | Owner is the spawner; explicit `owner:` not required. |
| `created` / `created_by` | Mapped | `commissioned_at` + `commissioned_by` serve the role. |
| `modified` | Records are body-append-only | Body append-only after `[SHUTDOWN]`. Frontmatter spawner-edits tracked via `status:` + `completed_at:`. |

**This reconciliation means:** the validator for activation-log records is this capsule's validation check list (1-24), not core's validation list. Core remains the schema floor for vault entries; this capsule is the floor for activation-log records.

### Required Frontmatter (universal floor)

| Field | Type | Constraint |
|---|---|---|
| `uid` | string (8-hex) | Stable identifier; required for cross-document citation (e.g., release.capsule v3.1's `verification_artifacts:` array). |
| `record` | integer | Sequential per-agent number. MUST equal `<NNN>` prefix in filename (zero-padded compare). |
| `agent` | string | sa.\* agent class — full `sa.<slug>` form. MUST match parent folder name. |
| `mode` | enum | `A-LIVE` / `B-BATCH`. Per [sa/CAPSULE.md (7d3f9a2c)](../../vault/files/e863a1e0.md) §Spawn Modes. |
| `commissioned_by` | string | Spawner's identifier (e.g., `argus-a41`, `vela-v37`, `metis-g48`, `mike`, `fleet-ops`). MUST match `Spawned by:` line in body header. |
| `commissioned_at` | string | YYYY-MM-DD or ISO8601. MUST match (or precede, by date) `Date:` line in body header. |
| `target` | string | Path, UID, or descriptor identifying what the sa.\* was tested against. |
| `status` | enum | `dispatched` / `complete` / `complete-via-salvage` / `blocked`. See §State Machine. |
| `schema_version` | integer | `2` (current). |

**Canonical status enum:** `status:` ∈ {dispatched, complete, complete-via-salvage, blocked}

### Conditional Frontmatter

| Field | When required | Notes |
|---|---|---|
| `verdict` | When `status: complete` or `complete-via-salvage` | **OMITTED while `status: dispatched`** — spawner populates at status transition. Format per agent (per-agent activation file's §Output Format declares allowed values). This capsule does NOT enumerate a universal verdict enum. |
| `findings_source` | When `status: complete-via-salvage` | How findings recovered (e.g., `artifact_inspection_only`, `partial_diary_recovery`). |
| `agent_stall_caveat` | When `status: complete-via-salvage` | One-line description of stall mode + what was lost. |
| `blocked_reason` | When `status: blocked` | Categorical reason (e.g., `independence-violation`, `harness-contamination`, `malformed-pending`, `dispatcher-not-allowed`). |
| `completed_at` | When `status: complete` or `complete-via-salvage` | ISO8601 timestamp the agent wrote `[DONE]` (or spawner closed salvage). |
| `backfilled` + `backfilled_by` + `backfilled_at` | When frontmatter was inferred post-hoc | See history §Backfill Plan. Distinguishes inference-products from origin-authored records. |
| `verdict_resolved_by` + `verdict_resolved_at` | When `verdict_inference_uncertain: true` has been manually reviewed + recovered | Rule 12 + history §Backfill Plan closure protocol. |

### Optional Frontmatter (universal — encouraged)

| Field | Purpose |
|---|---|
| `governed_by` | UID of the spec, capsule, or activation file the record operates under. |
| `relationships` | Per-agent typed edges (`succeeds`, `feeds-into`, `probes`, `informs`, `parallel-to`, `governed-by`, `derives-from`, `succeeds-in-different-class`). **Cross-class linkage MUST use `relationships:` per Rule 10 — NEVER `prior_record:`.** |
| `extraction_scope` | Default per-agent. Walker family typically `argo-private`; verification-record families typically `argo-reference`. |
| `prior_record` | UID of predecessor record in regression chain. **Within-class only** per Rule 10 + Check 20. Cross-class connections use `relationships:`. |
| `verdict_inference_uncertain` | Boolean. Set `true` when backfill couldn't unambiguously infer verdict. **Records flagged true are NOT cite-eligible per Rule 12 + Check 24** until closed. |

### Optional Frontmatter (per-agent extensions — named)

The capsule names extensions used by major sa.\* families. Per-agent activation files declare which extensions a record of that class MUST include.

**Forward-pointer to v1.3 amendment:** machine-checkable per-agent contracts will be declared in [session-agent.capsule v1.3](session-agent.capsule.md) via a new `record_extensions:` frontmatter slot — sibling amendment filed at [task `168fb3f8`](../../vault/files/168fb3f8.md). Until v1.3 lands, per-agent contracts are documented as prose in the agent's body §Output Format.

**Walker family** (sa.first-use-walker, sa.pipeline-walker, forthcoming `sa.user-error-walker`):
- `build_under_test` — release version frozen at dispatch
- `encounters_unprompted` — integer count
- `encounters_strong` — integer count
- `ceremony_load` — integer 1-5 per walker rubric

**Cold-boot family** (sa.cold-boot):
- `basis_artifact` — path/UID of source artifact (e.g., ship-zip)
- `diary_recovery_status` — relevant when `status: complete-via-salvage`

Per-agent activation files MAY declare additional extensions specific to their domain.

### Required Body Sections

Records inherit body shape from [sa/CAPSULE.md §Record File Format (7d3f9a2c)](../../vault/files/e863a1e0.md). Structural requirements:

| Section | Required when | Author |
|---|---|---|
| 1. **Header** — `# sa.<slug> — Activation Record NNN` | always | spawner |
| 2. **Subtitle** — `*Spawned by: <spawner-id> \| Date: YYYY-MM-DD*` + optional context (e.g., `\| Target: ...`) | always | spawner |
| 3. **Separator** — `---` | always | spawner |
| 4. **Commission block** — `[RESPONSE]` (BATCH: pre-populated; LIVE-CHANNEL: written after agent's `[QUERY]`) + `[PENDING]` items. For brand-new sa.\* in bootstrap window, see history §Bootstrapping Case. | always | spawner |
| 5. **Agent ack** — `[QUERY]` (LIVE-CHANNEL only — BATCH skips); `[IN-PROGRESS]` at work start | when work begins | agent |
| 6. **Output** — `[DONE]` block per per-agent §Output Format | when `status: complete*` | agent (or spawner-during-salvage in `complete-via-salvage`) |
| 7. **Termination** — `[SHUTDOWN]` | when `status: complete*` | agent (or spawner-synthetic in `complete-via-salvage`) |
| 8. **Block** — `[BLOCKED]` block with refusal reason | when `status: blocked` | agent |

**Sections 1-4 required regardless of `status:`** (Check 22). Sections 5-8 vary by status.

**Per-agent §Output Format authority:** sa.cold-boot's fixed 5-section format, walker's 7-section format (USER STORY / WALK NARRATIVE / UNPROMPTED ENCOUNTERS / EXPECTED-BUT-MISSING / CEREMONY-LOAD / VERDICT / RECOMMENDATIONS), pipeline-walker's 10-check verification block — declared in each agent's own activation file. This capsule mandates the OUTPUT sections exist; per-agent files specify internal shape.

### Filename Convention

| Pattern | Format | Used by |
|---|---|---|
| **A** (DEFAULT) | `<NNN>-<spawner>-record.md` | sa.cold-boot, sa.skeptic, sa.arch-specs, sa.research, sa.pipeline-walker, ops-fleet sa.\* |
| **B** (release-tied; walker family) | `<NNN>-<dispatcher>-<release-version>.md` | sa.first-use-walker, forthcoming sa.user-error-walker |
| **C** (descriptive; rare) | `<NNN>-<descriptor>.md` | sa.research lineage (long-running investigations); per-agent activation file MUST explicitly declare |

**Pattern C status-disclosure rule:** for Pattern C records with `status ∈ {blocked, complete-via-salvage}`, the descriptor MUST include a status token (e.g., `004-blocked-independence-violation.md`, `099-salvage-stream-watchdog.md`).

**Handle format:** `<NNN>` 3-digit zero-padded sequential; AI dispatchers use `<role>-<gen>` (e.g., `argus-a41`); humans use bare short-handle (e.g., `mike`); ops-fleet uses bare role (`fleet-ops`); no spaces; no full role titles.

**Bootstrapping case** for brand-new sa.\* classes: full detail in [history §Bootstrapping Case](activation-log.history.md). Key rule — record 001 stays bootstrap-shaped even after activation file lands; subsequent records (002+) carry full per-agent contract.

---

## 3. State Machine

```
dispatched ──→ complete                  (agent writes [DONE] cleanly)
           ──→ complete-via-salvage      (agent stalled mid-work; spawner salvaged from artifacts)
           ──→ blocked                   (agent refused dispatch — independence violation, contamination, malformed PENDING)
```

| Status | Meaning |
|---|---|
| `dispatched` | Record created with `[PENDING]` live; agent boot in flight or work in progress. |
| `complete` | Agent wrote `[DONE]` with verdict per per-agent §Output Format. Terminal. |
| `complete-via-salvage` | Agent stalled mid-work — covers (a) stalled with no termination marker, (b) stalled after partial output before `[DONE]`. Spawner inspects artifacts + authors salvage `[DONE]` from evidence. `findings_source` + `agent_stall_caveat` required. Terminal. |
| `blocked` | Agent refused dispatch per its own activation file's refusal rules. `blocked_reason` required. Terminal. |

**Transitions are one-way.** A blocked record stays blocked; a stalled record stays complete-via-salvage; a complete record is not re-opened. Re-dispatch creates a NEW record at the next NNN — never overwrites or transitions the prior record.

**Archival:** records are NEVER archived. They persist permanently as audit trail. No archival trigger; no archival authority delegated. Aligns with [sa/CAPSULE.md (7d3f9a2c)](../../vault/files/e863a1e0.md): *"The record file is permanent. Do not delete it."* Ban on deletion is structural, not policy-overridable.

---

## 4. Validation Rules

### Governance Rules (in addition to core + sa/CAPSULE.md)

1. **One record per spawn.** Each commission creates exactly one record. Re-dispatch creates new record at NNN+1, NEVER overwrites prior. Blocked/salvaged records stay as permanent audit trail.
2. **Filename `<NNN>` matches frontmatter `record:`.** Zero-padded compare.
3. **`agent:` matches parent folder.** A record at `agents/sa/sa.cold-boot/activation-log/...` MUST declare `agent: sa.cold-boot`.
4. **Records persist.** No deletion authority (see §State Machine archival).
5. **Per-agent extensions are per-agent declarations.** Fields named in §Optional Frontmatter (per-agent extensions) are REQUIRED on records IF the per-agent activation file declares them required.
6. **Verdict format authority is per-agent.** The `verdict` field's allowed values are declared by the per-agent activation file's §Output Format. This capsule does NOT enumerate a universal verdict enum.
7. **Cross-record citation uses UID.** When citing another record (e.g., walker 003's `prior_record:` pointing at walker 002), use UID — not NNN. NNNs are unique per agent, not globally.
8. **Dispatcher allowlist/blocklist enforcement is per-agent.** Some agent classes carry `spawnable_by:` allowlists + `spawn_blocklist:` denylists in activation file frontmatter. When dispatch refused per those rules, record's `status: blocked` + `blocked_reason: dispatcher-not-allowed`.
9. **Verdict transcription is universal.** Frontmatter `verdict:` MUST appear verbatim in the `[DONE]` block body (or spawner-authored salvage block). Generalizes [dispatch-walker.playbook v0.2 Rule 7](../playbooks/dispatch-walker.playbook.md) to all sa.\* classes. Check 21.
10. **Cross-class record linkage uses `relationships:`, not `prior_record:`.** Regression chains via `prior_record:` are within-class only (Check 20). Cross-class connections (e.g., walker citing peer cold-boot in parallel BATCH) MUST use `relationships:` with explicit `kind:` (e.g., `parallel-to`, `informs`, `succeeds-in-different-class`).
11. **Frontmatter is authoritative on body-disagreement.** When Check 5/6/13 detect frontmatter-vs-body disagreement on `status: dispatched`, frontmatter is canonical + spawner syncs body. For terminal-status records, spawner's sync is part of lock-in — Check 23 violation at terminal means spawner failed to sync. **Cross-rule precedence:** Rule 11 governs frontmatter-vs-body for `commissioned_by` / `commissioned_at` / H1 (Checks 5/6/13). Rule 9 (verdict transcription) is hard fail outside Rule 11's scope.
12. **Records flagged `verdict_inference_uncertain: true` are NOT cite-eligible until closed.** Backfilled record carrying the flag MUST NOT be cited from `release.capsule.verification_artifacts:` arrays or referenced by active `prior_record:` chains. Closure protocol: (a) verdict recovered via manual review (remove flag; add `verdict_resolved_by:` + `verdict_resolved_at:`) OR (b) reclassify to `status: blocked` + `blocked_reason: verdict_unrecoverable`. Check 24.

### Validation Checks

1. `uid` is 8-hex, unique in registry.
2. `record` is positive integer; matches `<NNN>` prefix in filename (zero-padded compare).
3. `agent` is a registered sa.\* class name (with `sa.` prefix); matches parent folder.
4. `mode` ∈ {`A-LIVE`, `B-BATCH`}.
5. `commissioned_by` is non-empty; matches `Spawned by:` line in body header. (Rule 11 applies.)
6. `commissioned_at` is valid YYYY-MM-DD or ISO8601; date component matches `Date:` line in body header.
7. `target` is non-empty. (v1.1+ hardening — see history §Limitations.)
8. `status` ∈ {`dispatched`, `complete`, `complete-via-salvage`, `blocked`}.
9. `schema_version` equals `2`.
10. If `status: complete` or `complete-via-salvage`: `verdict` field present and non-empty.
11. If `status: complete-via-salvage`: `findings_source` and `agent_stall_caveat` present.
12. If `status: blocked`: `blocked_reason` present.
13. Body contains `# sa.<name> — Activation Record <NNN>` H1 matching frontmatter `agent:` and `record:`.
14. Body contains `---` separator following subtitle.
15. If `status: complete*`: body contains `[DONE]` and `[SHUTDOWN]` markers.
16. If `status: dispatched`: body does NOT contain `[DONE]` or `[SHUTDOWN]`.
17. If `status: blocked`: body contains `[BLOCKED]` marker with refusal reason.
18. If `governed_by:` present: UID resolves to valid spec/decision/capsule/activation file.
19. Filename matches Pattern A (default), B, or C per parent agent's declared convention.
20. If `prior_record:` present: UID resolves to another record **under the same `agent:` class** (within-class regression chain only). Cross-class linkage uses `relationships:` per Rule 10.
21. **If `status: complete*`:** `[DONE]` block contains at least one non-marker, non-whitespace line. Frontmatter `verdict:` text appears verbatim somewhere in `[DONE]` block body. (Closes empty-`[DONE]` + falsified-`verdict` forgery surface.)
22. **Body sections 1-4** (Header, Subtitle, Separator, Commission block) required regardless of `status:`. Sections 5-8 vary by status.
23. **Frontmatter authoritative on body-mismatch.** When Checks 5/6/13 detect disagreement, frontmatter canonical; spawner syncs body (active-dispatch per Rule 11; terminal-status requires sync-at-lock-in).
24. **Cite-eligibility against `verdict_inference_uncertain:`.** If a record is cited from `release.capsule.verification_artifacts:` or referenced by active `prior_record:`, that record MUST NOT carry `verdict_inference_uncertain: true`. Closure protocol per Rule 12.

### Known Limitations (acknowledged — v1.1+ scope)

v1.0+ enforces nominal consistency for honest authors via Checks 1-24 + Rules 1-12. **v1.0 detects only consistent forgery** — cross-field self-consistency. Substantive provenance (proof that `commissioned_by:` reflects actual harness identity) requires out-of-band anchor (e.g., dispatch-time provenance crumb in `dispatches.jsonl`, or harness-identity attestation). v1.1+ concern.

Full limitations + companion-limitations detail in [history §Limitations](activation-log.history.md).

---

## 5. Composes-With

### Extends

- **`core`** — UID immutability, owner semantics, frontmatter invariants (with reconciliation per §2 Inheritance from core).

### Composes With

- **[session-agent.capsule (b4e2a718)](session-agent.capsule.md)** — sibling. Session-agent.capsule governs the sa.\* activation FILE; this capsule governs the per-commission RECORD. The two compose: activation file declares per-agent contract; records satisfy the contract.
- **[sa/CAPSULE.md (7d3f9a2c)](../../vault/files/e863a1e0.md)** — universal commissioning protocol. Governs the 6-step ceremony + spawn modes + prose record body format. This capsule formalizes structural requirements that sa/CAPSULE.md leaves as prose convention.
- **[release.capsule v3.1 (b19e8d43)](release.capsule.md)** — `verification_artifacts:` array cites this capsule's records by UID. Rule 12 + Check 24 cite-eligibility gate ensures cited records carry verdict integrity.
- **[playbook.capsule v2.5 (e7b3c509)](playbook.capsule.md) §Test-Harness subtype** — playbooks that dispatch sa.\* reference activation-log records as their evidence section.
- **[dispatch-walker.playbook v0.2 (`7579f894`)](../playbooks/dispatch-walker.playbook.md)** — Rule 7 (verdict literal-copy) generalizes universally to all sa.\* via this capsule's Rule 9 + Check 21.

### Subsumes

- [sa.first-use-walker/00-README.md](../../agents/sa/sa.first-use-walker/activation-log/00-README.md) — walker-family supplement
- [sa.pipeline-walker/FORMAT.md](../../agents/sa/sa.pipeline-walker/activation-log/FORMAT.md) — pipeline-walker-family supplement; per-agent §Output Format authority preserved

### Triggers sibling amendments

- [sa/CAPSULE.md BATCH-skip-[QUERY] (aa39ff6a)](../../vault/files/aa39ff6a.md) — formalizing the BATCH-mode `[QUERY]` skip rule that Row 5 of §Required Body Sections introduces
- [session-agent.capsule v1.3 `record_extensions:` (168fb3f8)](../../vault/files/168fb3f8.md) — machine-checkable per-agent record contract via new frontmatter slot

---

*activation-log capsule definition | UID `8406c4f8` | v1.1 | history at [2207c655](activation-log.history.md)*
