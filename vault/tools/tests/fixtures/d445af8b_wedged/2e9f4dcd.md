---
uid: "2e9f4dcd"
type: activation
title: "Activation — release-plan 2e15ef76"
description: "Opened atomically by the lock gesture as one indivisible act with the root, the run and the spec flip (0a0a6777 AC2/AC4)."
status: active
state: active
owner: "mike"
agent_class: pipeline
# action_bootstrap gates on THIS field; without it the runtime refuses
# the activation the lock just opened.
activation_class: pipeline
agent_root: "634913c2"
pipeline: "634913c2"
pipeline_uid: "634913c2"
pipeline_run_uid: 'd445af8b'
activation_root_project: 'd230a426'
release_plan_uid: '2e15ef76'
release_entry_uid: "64b10a96"
activated_by: "mike"
activated_at: '2026-08-27'
member_of:
  - "d230a426"
author: lock-gesture
created: '2026-08-27'
modified: '2026-08-27'
created_by: "mike"
schema_version: 2
governed_by: 8dd772a0
tags: [activation, pipeline-class]
---

# Activation — release-plan 2e15ef76

Authored inside the lock transaction, not by a subprocess ahead of it. The
activation, its root, its run and the subject's own status flip are one plan:
either all of them land or none of them do.
