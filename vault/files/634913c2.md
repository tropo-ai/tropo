---
uid: 634913c2
title: release-pipeline
type: pipeline
subtype: workflow-node
name: release-pipeline
version: 1.0.1
status: active
state: active
role: root
children:
  - 471dd767
  - 8a4f802b
  - 8e03f8d6
next_steps: []
member_of: []
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
modified: '2026-08-14'
modified_by: cursor-agent-11ab
v1_0_1_amendment_note: '2026-08-14 runtime regression fix. The Verify root leaf 4262d5fa now depends on Assemble terminal leaf 8654900a, and Publish root leaf 3dd817cb now depends on Verify terminal leaf c6b61fb9. Runtime eligibility is leaf-DAG based, so these explicit cross-stage barriers make the declared Assemble -> Verify -> Publish sequence executable without either later stage becoming eligible early.'
activated_under: '0a0a6777'
activated_by: mike
activated_at: '2026-08-13'
---

# release-pipeline

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Playbooks](76bab75f.md) → **release-pipeline**
<!-- nav-block:end -->

Ignition is a **locked release-plan**; the terminal is a **published official release**
(Mike's ruling, quoted in 0a0a6777).

`Assemble → Verify → Publish`.

Symmetric with dev-pipeline v2: the dev-spec lock is the only dev ignition and the
release-plan lock is the only release ignition. Both write a complete immutable snapshot
transaction at lock time, and neither has a close WorkflowNode — closure is a journaled
side effect of terminal verification and public receipt respectively.

## Purpose and the proportionality norm

A bounded change should cost bounded work. Dev work ends at Test; only a deliberate
release-plan pays release-class cost.

Work done outside this pipeline must cite a governed review artifact naming the reviewer
and the accepted rationale. A silent skip is not an exception — it is an unreviewed one,
and it fails the static policy check (AC11).
