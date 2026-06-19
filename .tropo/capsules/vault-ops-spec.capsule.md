---
uid: 8c851a7d
name: "vault-ops-spec"
type: capsule-definition
extends: core
version: "1.0"
tier: os
author: vela-v54
created: 2026-05-27
modified: 2026-06-09
created_by: vela-v54
modified_by: argus-a105
status: active
walk_completed_at: 2026-05-27
walk_walked_by: ["mike-maziarz", "vela-v54"]
walk_locked_by: vela-v54
locked_at: 2026-05-28
locked_via: "First production dogfood completed 2026-05-28 per spec instance [5e824d80] cycle. Schema empirically validated by 3 substrate_touches across 3 verification_method classes (deterministic_assertion + machine_executable_script + scan-only). Capsule flips DRAFT → LOCKED v1.0 alongside vault-ops-pipeline."
schema_version: 2
governed_by: 222873b9   # capsule-definition meta
aligned_with:
  - "c3f68cb5"   # dev-spec.capsule v1.0 - sibling activation-input *-spec capsule
  - "9a7d314a"   # doc-spec.capsule v1.0 - sibling
  - "621824df"   # test-spec.capsule v1.0 - sibling; primary mirror
pattern_family: "spec-family"
member_of:
  - "8dd772a0"   # tropo-governance
meta_status_rollup:
  in-progress: [active]
  done: [done]
meta_status_rollup_note: "argus-a104 2026-06-08 — rollup completion per the unified lifecycle knot (move 2, 9f6a1379); additive lock-break."
---

# vault-ops-spec - Capsule Definition v1.0 (DRAFT)

*A vault-ops-pipeline activation-input commitment - declares what vault maintenance work the activation will exercise. The "ignition key" for vault-ops-pipeline activations.*

*Fourth of the *-spec family alongside dev-spec, doc-spec, test-spec. Each *-spec is the symmetric activation-input for its corresponding pipeline.*

*v1.0 DRAFT authored by Vela V54 2026-05-27 after 4-question Walk Format Doctrine walk with Mike. Locks at v1.0 after first dogfood run validates the schema in production.*

---

## Intent

A `vault-ops-spec` entry is a forward-looking commitment naming what vault maintenance work the activation will exercise, with verifiable acceptance criteria. It answers four questions before a vault-ops-pipeline activation fires:

1. **What run type is this?** Scheduled (recurring fleet-ops cadence) or on-demand (substrate-coherence cycle / repair campaign).
2. **What substrate touches does this cover?** For scheduled runs: the dispatch_list (which sa.* agents fire). For on-demand: the substrate_touches (which vault entries the work modifies).
3. **What is the acceptance criterion for clean close?** Mike-walkable verification per Captain's Briefing v3.0 Requirement 2.
4. **What evidence ratifies acceptance at close?** Run.jsonl events + sa.* activation-log records + post-condition substrate state.

The vault-ops-pipeline engine refuses to activate without a compliant vault-ops-spec entry. The activation cannot close until acceptance_criteria verified + evidence collected.

---

## Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `type` | string | Literal `vault-ops-spec` |
| `run_type` | enum | `scheduled` or `on-demand`. Drives downstream validation per Rule 3. |
| `acceptance_criteria` | string | Non-empty; Mike-walkable verification per Captain's Briefing v3.0 Requirement 2. |
| `dispatch_list` | list of objects | REQUIRED when `run_type: scheduled`. Each object: `sa_class` (string; sa.* class to dispatch), `record_path` (string; activation-log path), `currency_checked` (boolean; was sa.* currency-validated per Mike-V54 directive 2026-05-27). |
| `substrate_touches` | list of objects | REQUIRED when `run_type: on-demand`. Each object: `touch_description` (≤200 chars), `target_substrate_refs` (UID array; entries the touch modifies), `verification_method` (enum; same 5-entry set as test-spec.capsule). |

## Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `triggered_by_cycle` | UID | UID of dev-pipeline activation or scheduled-fleet cadence that triggered this vault-ops-spec. |
| `pipeline_run_uid` | UID | Backreference to the vault-ops-pipeline-run instance (engine writes). |
| `closed_at` | ISO 8601 | When vault-ops-pipeline activation closed clean (engine writes). |
| `acceptance_evidence` | list of UIDs | UIDs of substrate that ratifies acceptance_criteria met (sa.* activation-log records + run.jsonl event UIDs + post-condition substrate state). |
| `fleet_dormancy_at_trigger` | string | For scheduled runs: how long since last fleet-ops dispatch. Captures the V48-V54 dormancy pattern for ongoing observability. |
| `cycle_class` | enum | `fleet-ops-scheduled` / `substrate-coherence` / `channel-grooming` / `repair-campaign`. Drives downstream report-shape conventions. |

---

## State Machine

```
draft -> active -> done -> (superseded: done + state: archived)
```

| Stage | State | Meaning |
|-------|-------|---------|
| `draft` | `active` | Under authoring; engine refuses vault-ops-pipeline activation against it |
| `active` | `active` | LOCKED by owner (Vela); vault-ops-pipeline activation has fired |
| `done` | `active` | Vault-ops-pipeline cycle closed clean; `closed_at` set; acceptance_criteria verified |
| `done` | `archived` | Superseded; requires `superseded_by:` field |

---

## Governance Rules (in addition to core)

1. **Owner locks v1.0** - Vela owns the pipeline + the spec; captain-mode authoring + locking acceptable for routine fleet runs. Substantive substrate-coherence cycles get a 4-question Walk Format Doctrine walk with Mike before lock.

2. **Run-type-conditional fields** - per `run_type:`:
   - `scheduled` requires non-empty `dispatch_list:`; each entry's `currency_checked: true` enforced per Mike-V54 directive 2026-05-27 ("validate ops-agents are updated and relevant to current studio needs")
   - `on-demand` requires non-empty `substrate_touches:`; each entry's `verification_method` declared (5-entry enum mirroring test-spec.capsule)

3. **sa.* currency validation** - for `run_type: scheduled`: each `dispatch_list:` entry's `currency_checked:` must be `true` before lock. Validation checks: last modified date on sa.* activation file vs current capsule versions; spec alignment with present-day vault structure; output path still valid; owner ACL current. Fails currency = sa.* gets a refresh substrate-touch BEFORE the dispatch fires.

4. **Anti-box-checking gate** - `acceptance_criteria` must name concrete post-conditions a reader can verify against the substrate post-run. Not "fleet ran" but "DISPATCH bulletin posted to ops.md + all 7 dispatched sa.* activation-log records show [DONE] + 0 unresolved FLASH in alerts.md."

5. **`acceptance_criteria` Mike-walkable** per Captain's Briefing v3.0 Requirement 2.

6. **Supersession requires bidirectional pointer pair.** Same shape as sibling *-spec capsules.

---

## Validation Checks (run at vault rebuild)

In addition to core checks:

1. `check_vault_ops_spec_required_fields` - type + run_type + acceptance_criteria present (WARN at v1.0; ERROR ratchet at v1.1)
2. `check_vault_ops_spec_run_type_conditional_fields` - if `run_type: scheduled`: dispatch_list non-empty; if `on-demand`: substrate_touches non-empty
3. `check_vault_ops_spec_dispatch_list_currency_checked` - each dispatch_list entry has `currency_checked: true` before lock (Mike-V54 directive)
4. `check_vault_ops_spec_substrate_touches_verification_method` - for on-demand: each substrate_touches entry has verification_method declared
5. `check_vault_ops_spec_acceptance_criteria_present` - non-empty
6. `check_vault_ops_spec_close_invariants` - `stage: done` requires `closed_at` + `acceptance_evidence` populated
7. `check_vault_ops_spec_supersession_bidirectional` - bidirectional pointer pair

Authoring lane: Vela owns + maintains; Argus reviews capsule amendments; Talos engineers validator extensions if/when needed.

---

## Inheritance

Extends `core`. Inherits all core rules.

---

## Studio - Shop Signage

*What's on the wall above this bench. Scan before you author a vault-ops-spec.*

**Tools available:**
- `vault/00-index.jsonl` - grep `type: vault-ops-spec` for live activations
- Companion capsules: [dev-spec (c3f68cb5)](dev-spec.capsule.md); [doc-spec (9a7d314a)](doc-spec.capsule.md); [test-spec (621824df)](test-spec.capsule.md) - sibling *-spec capsules
- Pipeline definition: [vault-ops-pipeline (9dab87a0)](../../vault/files/9dab87a0.md)

**Rules at-a-glance:**
1. Owner locks v1.0 (captain-mode acceptable for routine)
2. Run-type-conditional fields (scheduled vs on-demand)
3. sa.* currency validation before scheduled dispatch
4. Anti-box-checking gate on acceptance_criteria
5. Mike-walkable acceptance_criteria
6. Supersession bidirectional

**Pitfalls:**
- `dispatch_list:` entry without `currency_checked: true` - violates Mike-V54 directive; sa.* may be stale
- `acceptance_criteria: "fleet ran"` - box-checking; name concrete post-conditions
- Skipping `verification_method` on substrate_touches entries for on-demand runs

**Go next:**
- Pipeline definition - [vault-ops-pipeline v1.0 (9dab87a0)](../../vault/files/9dab87a0.md)
- Sibling spec precedent - [test-spec v1.0 (621824df)](test-spec.capsule.md)
- Strategic-frame parent - [Captain's Briefing v3.0 (a5f4b26b)](../../vault/files/a5f4b26b.md)

---

## Changelog

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0-DRAFT | 2026-05-27 | Initial DRAFT authored by Vela V54 after 4-question Walk Format Doctrine walk with Mike. Schema modeled on test-spec.capsule v1.0 precedent. Vault-ops-pipeline scope: scheduled fleet-ops cadence + on-demand substrate-coherence cycles + multi-channel grooming sweeps + vault-wide repair campaigns. sa.* currency validation directive (Mike-V54 2026-05-27) codified at Rule 3. Locks at v1.0 after first dogfood run validates schema in production. | vela-v54 |

---

*vault-ops-spec capsule definition | UID `8c851a7d` | v1.0 DRAFT | Vela V54 | 2026-05-27*
*"The ignition key for vault-ops-pipeline activations. Scheduled fleet cadence + on-demand substrate-coherence cycles + sa.* currency validation before dispatch."*
