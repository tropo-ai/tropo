---
uid: a0f2bea8
title: release-harness-gate — release-pipeline step
type: pipeline
subtype: workflow-node
name: release-harness-gate
version: 1.0.0
status: active
state: active
role: step
children: []
next_steps:
  - bc6b17ec
step_owner_role: vela
step_verifier_role: argus
verification_class: true
verification_command: python3 vault/tools/tropo-check-harness-receipt.py --activation-uid {activation}
depends_on_steps:
  - 4262d5fa
exit_criteria:
  - harness verdict binds to the frozen package_sha256
verdict_source_note: 'AC7 is this step''s named verifier: each instrument runs once against one frozen package_sha256. Added 2026-08-09 by talos-t40: pipeline.capsule Check 20 refuses a vc:true step with no verdict source, and it was right to — a verification step that attests to itself verifies nothing.'
relationships:
  - rel: member_of
    uid: 8a4f802b
member_of: []
stage6_ac7_rehome_note: 'Talos T40 2026-08-11 (Stage-6 GO, A148 evt_a9360f18f56fe472_00000018; preflight §3). next_steps changed from 3dd817cb (Publish) to bc6b17ec: the harness jumped straight to Publish, so external test and cold walk could never run even once they were filed under Verify. Amended in place, never deleted and recreated: the uid is referenced by completed runs and reissuing it would orphan every record that points here.'
stage6_q9_ruling_note: 'Talos T40 2026-08-11 (A148 Q9 ruling evt_a9360f18f56fe472_00000027). Now points at the evidence checker. Pointing it at the sandbox reference run was worse than the original defect: that fixture SYNTHESIZES all four receipts, so the harness instrument would have been verified by something that fabricates harness evidence. sa.release-test-harness is a session-agent Mike activates; this node checks that its evidence exists and resolves, and never executes it.'
stage6_v9_harness_note: 'Talos T40 2026-08-11 (Stage-6 V9). verification_command was pytest over this AC''s OWN contract test, so the release harness gate verified the test that checks the harness — a green verdict meant the assertions ran, not that a harness exercised a release. Repointed at the release reference run, which walks package -> Verify -> Publish -> receipt -> closure against a scratch remote and fails when any of those refuse. Deferred from step 3 because the instrument vocabulary did not exist yet; it does now.'
schema_version: 2
extraction_scope: ship
capsule_version: '2.5'
subsystem_hub:
  - 76bab75f
author: argus-a147
owner: argus
built_by: talos-t40
built_under: '0a0a6777'
build_authorization: 'evt_a2267930c7a21c90_00000020'
created: '2026-08-09'
created_by: talos-t40
modified: '2026-08-13'
modified_by: argus-a148
activated_under: '0a0a6777'
activated_by: mike
activated_at: '2026-08-13'
---

# release-harness-gate

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Playbooks](76bab75f.md) → **release-harness-gate — release-pipeline step**
<!-- nav-block:end -->

The release test harness, run against the exact frozen package digest.

Deliberately distinct from the external test and the cold stranger walk (§AC7). Three
instruments that answer different questions were previously folded together; when they
disagree, a single verdict cannot say which one was wrong.
