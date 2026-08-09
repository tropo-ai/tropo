---
uid: dac91126
title: accept-vault-ops-spec - vault-ops-pipeline step 1
type: pipeline
subtype: workflow-node
name: accept-vault-ops-spec
version: '1.0'
author: vela-v54
owner: vela
status: draft
state: active
role: step
created: 2026-05-27
created_by: vela-v54
modified: 2026-05-27
modified_by: vela-v54
schema_version: 2
extraction_scope: ship
governed_by: e4c8a6b2
children: []
step_owner_role: vela
step_verifier_role: same-as-executor
verification_class: true
verification_command: python3 vault/tools/tropo-validate.py
depends_on_steps: []
exit_criteria:
  - vault-ops-spec entry referenced at activation time exists in vault
  - vault-ops-spec passes all vault-ops-spec.capsule v1.0 [8c851a7d] validation checks at ERROR ratchet level
  - vault-ops-spec.status = active
  - 'If run_type = scheduled: dispatch_list non-empty AND every entry has currency_checked = true'
  - 'If run_type = on-demand: substrate_touches non-empty AND every entry has verification_method declared'
trust_level: auto
next_steps:
  - bd298097
relationships:
  - rel: member_of
    uid: 9dab87a0
member_of:
  - 9dab87a0
tags:
  - pipeline
  - workflow-node
  - vault-ops-pipeline
  - step
  - activation-input-validation
---

# accept-vault-ops-spec - vault-ops-pipeline step 1

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-work](b8e5f3a2.md) → [vault-ops-pipeline](9dab87a0.md) → **accept-vault-ops-spec - vault-ops-pipeline step 1**
<!-- nav-block:end -->

*Entry step. Activation-input validation per vault-ops-spec.capsule v1.0.*

Engine refuses vault-ops-pipeline activation if any exit criterion fails. No partial activations.

**What it does:**
1. Reads vault-ops-spec entry referenced at activation invocation
2. Runs vault-ops-spec.capsule v1.0 [8c851a7d] validation checks
3. Branches on `run_type:`:
   - `scheduled`: confirms `dispatch_list:` non-empty + every entry's `currency_checked: true` (sa.* currency validation pre-condition per Mike-V54 directive 2026-05-27)
   - `on-demand`: confirms `substrate_touches:` non-empty + every entry's `verification_method:` declared

**Failure modes:**
- vault-ops-spec missing - activation refused; reason logged
- vault-ops-spec validation FAIL - activation refused; specific failing checks logged
- run_type = scheduled but dispatch_list empty or any entry currency_checked = false - activation refused; stale sa.* enumerated for refresh substrate-touch
- run_type = on-demand but substrate_touches empty or any entry verification_method unset - activation refused

**Hands off to:** [step 2 plan-vault-ops (bd298097)](bd298097.md) when all exit criteria PASS.
