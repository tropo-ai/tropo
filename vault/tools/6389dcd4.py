"""---
uid: '6389dcd4'
name: distiller-model-edge
type: tool
title: "distiller-model-edge — policy-bound Distiller model executor"
description: "Delegates locked Distiller production and attempt-7 exact-response OS canary tasks through one fail-closed metered_model gate."
status: active
state: active
owner: talos
domain: "On-demand, policy- and reservation-bound execution for Distiller parse-query and distill calls"
spawnable_by:
  - all-executives
transport: library
implementation_kind: library
input:
  oneOf:
    - type: object
      description: "Production call shape."
      required: [task, messages, segment_classes, run_binding, max_tokens]
      properties:
        task:
          type: string
          enum: [parse-query, distill]
        messages:
          type: array
        segment_classes:
          type: array
          items:
            type: string
            enum: [os, team, private]
        run_binding:
          type: object
        max_tokens:
          type: integer
          minimum: 1
        system:
          type: [string, 'null']
      additionalProperties: false
    - type: object
      description: "Code-fixed canary call shape."
      required: [task, run_binding]
      properties:
        task:
          type: string
          enum: [parse-query, distill]
        run_binding:
          type: object
          required:
            - run_uid
            - gateway_url
            - virtual_key
            - studio_root
            - run_dir
          properties:
            run_uid:
              type: string
              pattern: '^[0-9a-f]{8}$'
            gateway_url:
              type: string
              const: 'http://127.0.0.1:8080'
            virtual_key:
              type: string
            studio_root:
              type: string
            run_dir:
              type: string
          additionalProperties: false
      additionalProperties: false
output:
  type: object
  description: "MeteredModelResult on success or typed ModelRefusal on any closed gate."
destructive: false
audit_required: false
writes_scope:
  - vault/loop-runs/.model-spend/*.json
  - vault/loop-runs/.model-spend/*.lock
  - vault/loop-runs/.model-spend/distiller-canary-0c938a95-1.8.0-claim.json
  - vault/loop-runs/.model-spend/distiller-canary-0c938a95-1.8.0-claim.lock
governance_category: query
created: '2026-07-23'
created_by: talos-build-worker
modified: '2026-07-24'
modified_by: talos
schema_version: 2
capsule_version: '1.8'
governed_by: d5e1b4a3
member_of:
  - 8dd772a0
extraction_scope: ship
---

## Intent

Run only Distiller's exact `parse-query` or `distill` task through the canonical
metered gate. `parse-query` is pinned to fixed snapshot
`claude-haiku-4-5-20251001`; `distill` remains `claude-sonnet-4-6`. It is
on-demand only and does not schedule, boot-dispatch,
construct a second provider client, or infer production egress from the
separate canary authority.

## Invocation Protocol

Import this module by its registered UID and call `call(...)` for production or
`call_canary(...)` for the separately approved OS-only canary. Neither function
has a model, policy path, policy UID, reservation, daily total, consent, ledger
path, or admission-mode override. `call_canary` accepts only the task and exact
run binding; its messages, system prompt, output bound, segment, and request
hash are code-locked in `lib.metered_model`. Both production and canary requests
derive controls from one immutable per-task table: `parse-query` sends only
`service_tier=standard_only`, while `distill` additionally sends
`inference_geo=global`. Callers cannot override either task capability.
Response usage requires standard tier for both routes. The locked OS-only path
accepts and records any exact nonempty response geo string through 128
characters without normalization or character-set restrictions. Sonnet still
requests `global`; only the exact reported value `us` receives 11/10 pricing.
The attempt-7 scorer accepts raw JSON or one exact lowercase JSON fence within
the closed 4,096-byte response bound. It parses only a temporary unwrapped body;
the result, scorecard, and gateway receipt preserve original response text and
SHA-256.

## Input / Output

Production inputs are the closed task, messages, trusted segment classes, run
binding to a canonical absolute Studio root, positive output-token bound, and
optional system prompt. Canary input is only task plus run binding. The gate derives
`<studio_root>/vault/loop-runs/.model-spend`; callers cannot supply that path.
Output is exactly `MeteredModelResult` or `ModelRefusal` from
`lib.metered_model`.

## Governance

The canonical policy `0c938a95` remains the authority. This executor cannot
change spend limits or consent, and its delegated ledger writes are restricted
to the bound Studio's exact `vault/loop-runs/.model-spend` runtime folder. The
Studio marker, path components, and ledger folder must be regular,
non-symlinked, and canonical. It emits no event.

Mixed-binary deployment requires every prior-version gateway process to be
stopped before v1.8 attempt preparation. Preparation creates no daily ledger;
after readiness, execution binds the current UTC day and exact initial ledger
hash before the first reservation. The current library sums the legacy v1.1
and every versioned same-day peer under one lock and denies a new reservation
after any mixed over-ceiling state. Only the v1.8 gateway may bind
`127.0.0.1:8080`; execution requires its exact v1.8 readiness and
execution-ledger identities plus strict task-aware response usage.

## Verification

The Cut 4J exact-response suite plus Cut 4I lifecycle and amended Cut 4H
pricing, policy, metered-runtime, gateway, adapter, and orient suites prove
exact admission, strict usage refusal, zero-call refusal, and deterministic
fallback.

## Failure Modes

Unknown task, disabled policy, ask consent, bad run binding, absent/tampered
ledger, exceeded budget, provider failure, model substitution, malformed usage,
or reconciliation drift returns a typed refusal without escalation.
"""
from __future__ import annotations

from lib import metered_model


def call(
    task: str,
    messages: list[dict],
    *,
    segment_classes,
    run_binding,
    max_tokens: int,
    system: str | None = None,
):
    """Delegate to the sole production model gate without authority overrides."""
    return metered_model.call(
        task,
        messages,
        segment_classes=segment_classes,
        run_binding=run_binding,
        max_tokens=max_tokens,
        system=system,
    )


def call_canary(
    task: str,
    *,
    run_binding,
):
    """Delegate one fixed OS-only canary request without content overrides."""
    return metered_model.call_canary(
        task,
        run_binding=run_binding,
    )


__all__ = ["call", "call_canary"]
