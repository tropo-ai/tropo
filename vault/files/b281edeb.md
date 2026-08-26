---
uid: b281edeb
title: 'Ship: vault/tools/lib/ (tool dependency closure)'
type: ship-artifact
kind: folder
target:
  - release
canonical_source: argo-os/vault/tools/lib
source_mode: recursive-ship-all
extraction_scope: ship
parent: 79cca015
output_path: vault/tools/lib/
member_of:
  - b2e7d4a9
description: 'Shared modules every shipped tool imports. canonical_source: `argo-os/vault/tools/lib`. Same output path — imports resolve unchanged.'
status: active
state: active
owner: talos
author: talos-t41
created: 2026-08-13
created_by: talos-t41
modified: 2026-08-24
modified_by: talos-t50
ac1_activated: 'v1.92 Stream 2 AC1 (1a478c48), 2026-08-24: flipped draft->active and argo-reference->ship. Designed correctly at authoring (Metis AC8 walk finding) but never wired live -- this build is the first real ship gate to depend on it (the dev-pipeline ignition, aeb2df3d, ships alongside it in the same change; without this closure the ignition ships with zero lib modules, the exact ModuleNotFoundError this artifact exists to prevent).'
governed_by: eeb59ddf
schema_version: 2
refs:
  - e52826c5
  - 62a22664
---

# Ship: vault/tools/lib/

<!-- nav-block:start -->
**📍 Vault Path:** [b2e7d4a9](b2e7d4a9.md) → **Ship: vault/tools/lib/ (tool dependency closure)**
<!-- nav-block:end -->

## Purpose

The shared modules the shipped tools import. Without them the box carries 70 executables that
cannot run.

## Description

Recursive copy to the same path, so every `from lib.x import y` resolves in the recipient exactly
as it does here. One explicit package surface rather than dozens of individually tagged modules.

## Why it ships

Found by Metis's AC8 cold walk (verdict 62a22664): the box shipped 70 tool scripts and ZERO lib
modules, so the documented first rebuild — a stranger's first command — died on
`ModuleNotFoundError`.

The cause is structural, not an oversight in tagging. `lib/` is ungoverned substrate: its modules
carry no UID, so the governed-entry path that ships tools could never carry them, and no amount of
per-file tagging inside `vault/` would have helped. A shipped tool must ship its imports, which
needs a surface of its own.
