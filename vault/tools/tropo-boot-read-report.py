#!/usr/bin/env python3
"""
---
uid: f015773d317d
title: Boot read report
name: boot-read-report
type: tool
status: active
owner: argus
created: '2026-09-08'
description: Warn-safe current activation Read observation; never certifies comprehension.
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/tropo-boot-read-report.py
script_path: vault/tools/tropo-boot-read-report.py
extraction_scope: ship
destructive: false
audit_required: false
writes_scope:
- .tropo/flags/boot-read-receipt-*.jsonl
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
domain: Report declared file reads observed in the current activation, or explicit
  unobservability.
trigger_description: Run begin before declared boot reads and report before the greeting,
  with the same explicit window token; unsupported harnesses report unobservable.
input:
  type: object
  properties:
    vault-root:
      type: string
      description: Resolved Studio root; defaults to the script installation.
    manifest:
      type: string
    agent:
      type: string
    session-id:
      type: string
    receipt:
      type: string
    harness:
      type: string
    window-id:
      type: string
    begin:
      type: boolean
    audit:
      type: boolean
    json:
      type: boolean
---

## Intent
Report declared file reads observed in the current activation, or explicit unobservability. This reports evidence, never comprehension or complete boot correctness.

## Invocation Protocol
Use `python3 vault/tools/tropo-boot-read-report.py --begin --agent darin --harness claude`, then report with `--window-id` and that exact returned token. Use `--harness codex` or `gemini` for explicit unsupported-harness output.

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
from lib.boot_reads import report_main

if __name__ == '__main__':
    raise SystemExit(report_main(Path(__file__).resolve().parents[2]))
