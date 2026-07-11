---
uid: d2efcac9
type: playbook
subtype: verification
title: Clean-Update Floor Test — the Gate 2 acceptance proof
description: 'Proves the Gate 2 covenant by construction and demonstration: seed a vault with user content, apply an update replacing tropo-* OS components, assert ZERO user-file churn AND every targeted OS component updated. Runs as a BLOCKING build gate (ADR-049 covenant layer 2) via vault/tools/tests/test_clean_update_floor.py, invoked from vault/tools/tropo-build-release.py Step 10.7.'
author: talos-t23
status: active
state: active
version: '1.0'
maintained_by: talos
extraction_scope: ship
schema_version: 2
governed_by: 8dd772a0
created: 2026-07-02
modified: 2026-07-02
created_by: talos-t23
relationships:
  - kind: governs-protocol-for
    target: fc4874f4
  - kind: implements
    target: 71f186cf
  - kind: grounded-in
    description: ADR-049 (eee2246e) — the update covenant; covenant layer 2 wires this test as a blocking build gate.
tags:
  - playbook
  - verification
  - gate-2
  - clean-self-update
  - covenant
  - floor-test
  - one-home
  - namespace-predicate
  - ship
subsystem_hub:
  - 8dd772a0
---

# Clean-Update Floor Test

*The Gate 2 acceptance proof (dev-spec [fc4874f4](fc4874f4.md), acceptance criterion 9). "A gate that cannot fail when it should is not a gate."*

## Intent

Prove, by construction and by demonstration, that applying a Tropo-OS update never touches a user's own work — only `tropo-*` OS components move. This is the entire property Gate 2 buys (see fc4874f4 §"The outcome this gate buys").

## What it does

The real test is code, not prose — [`vault/tools/tests/test_clean_update_floor.py`](../tools/tests/test_clean_update_floor.py). This playbook is the governance wrapper: it declares the test exists, what it proves, and how it's wired into the build.

1. **Seed** a throwaway vault: user content (`vault/files/<uid>.md`, `vault/files/<slug>-<uid>.md`, `vault/playbooks/<slug>-<uid>.md`) alongside OS components (`vault/tropo-*`, `.tropo/*`). Record each user file's mtime + SHA-256.
2. **Apply** an update plan that replaces every OS component, routed through the real namespace predicate ([`vault/tools/lib/tropo_update_namespace.py`](../tools/lib/tropo_update_namespace.py) — the same module the apply-update playbook v2.0 Step 3 cites as the concrete implementation of its Rule).
3. **Assert** zero user-file churn (mtime + hash unchanged for every seeded user file) AND every targeted OS component landed its new version.
4. **Fails loudly** if either assertion breaks — no soft-pass, no warning-only mode.

## The gauntlet (adversarial isolation)

`python3 vault/tools/tests/test_clean_update_floor.py --gauntlet` plants a covenant-violating write (bypassing the namespace predicate, simulating a buggy/malicious engine) and asserts the test's churn detector catches it. This proves the floor test is a real gate, not a tautology that always prints PASS — the same adversarial-isolation pattern as `test_no_two_homes_gate.py` and `test_one_open_activation_gate.py`.

## Wiring — covenant layer 2 (ADR-049)

[`vault/tools/tropo-build-release.py`](../tools/tropo-build-release.py) Step 10.7 runs three sub-steps before any zip is produced:

1. `--gauntlet` run — must report the planted violation caught (else the gate itself is broken; refuse the build).
2. Normal run — must report zero churn (else a real covenant violation exists in the current update path; refuse the build).
3. Only if both pass: the build proceeds to Step 11 (zip + upload).

A release whose update path would violate zero-user-churn cannot be built, and therefore cannot ship.

## Verification

### Method

Self-executing assertion script, exit code is the verdict (0 = PASS, 1 = FAIL). No self-attestation — the test either detects churn or it doesn't.

### Criteria

- Normal run: zero entries in `churned`, zero entries in `not_updated`.
- Gauntlet run: `churned` is non-empty (the planted violation was caught).
- Both runs exit cleanly (no exceptions) regardless of PASS/FAIL — a crash is itself a FAIL of the harness, not a skip.

---

*Clean-Update Floor Test | UID `d2efcac9` | Talos T23 | 2026-07-02 | Gate 2 (dev-spec fc4874f4)*
*"A gate that cannot fail when it should is not a gate."*
