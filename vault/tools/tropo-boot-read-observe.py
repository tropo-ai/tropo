#!/usr/bin/env python3
"""
---
uid: f015d4422c94
title: Boot read observe
name: boot-read-observe
type: tool
status: active
owner: argus
created: '2026-09-08'
description: Warn-safe current activation Read observation; never certifies comprehension.
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/tropo-boot-read-observe.py
script_path: vault/tools/tropo-boot-read-observe.py
extraction_scope: ship
destructive: false
audit_required: false
writes_scope:
- .tropo/flags/boot-read-receipt-*.jsonl
- ${CLAUDE_ENV_FILE}
created_by: argus-a175
modified: '2026-09-08'
modified_by: argus-a175
schema_version: 2
capsule_version: '1.8'
governed_by: 8dd772a0
member_of:
- 99ed55fd
subsystem_hub:
- 99ed55fd
spawnable_by:
- all-executives
- po
governance_category: lifecycle
domain: Record successful native Claude Read coverage in a session-bound activation
  window.
trigger_description: Used by configured Claude SessionStart and PostToolUse Read hooks
  to record content-free evidence; not a manual attestation of what an agent read.
input:
  type: object
  properties:
    vault-root:
      type: string
      description: Resolved Studio root; defaults to the script installation.
    verb:
      type: string
      enum:
      - session-start
      - post-read
    stdin:
      type: object
      description: Native hook envelope with session_id, cwd, hook_event_name; Read
        additionally carries tool_name, tool_input and tool_response.
---

## Intent
Record successful native Claude Read coverage in a session-bound activation window. This reports evidence, never comprehension or complete boot correctness.

## Invocation Protocol
Configured hooks call `python3 vault/tools/tropo-boot-read-observe.py session-start` or `post-read`, with native JSON on stdin.

## Input / Output
The input schema is declared above. Observer prints a recording or unavailable diagnostic. Reporter prints per-item coverage and a summary; --json returns structured status, items and counts. Begin returns its window token.

## Governance
Runtime receipts contain metadata, ranges and hashes, never file content. They are append-only under .tropo/flags. SessionStart additionally appends only its binding to the harness-provided CLAUDE_ENV_FILE. No external event, network request, permission change or public release is performed.

## Verification
Run the appropriate ObserverContract/ReportContract and ShippedContract classes in [contract tests](tests/test_boot_read_report.py). Actual native hook behavior is separately verified on candidate bytes; synthetic envelopes cannot prove a harness ran.

## Failure Modes
Unsupported harness, absent session/window, unavailable locking backend, invalid receipt or unknown coverage prints an explicit diagnostic and exits zero. Argument misuse retains argparse usage errors. No missing evidence becomes done. Historical audit is labeled and cannot substitute for a current greeting.
"""
from pathlib import Path
from lib.boot_reads import observer_main

if __name__ == '__main__':
    raise SystemExit(observer_main(Path(__file__).resolve().parents[2]))
