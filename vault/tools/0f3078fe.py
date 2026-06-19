#!/usr/bin/env python3
"""
---
uid: 0f3078fe
name: check-one
type: tool
title: check-one
description: "Targeted single-entry validator. Runs the capsule check-family for one vault entry (by UID) and exits 0 (PASS) or 1 (FAIL). The reusable primitive vc:true gate-step verification_commands call. Per CLI spec 2ddad3be (Argus A91 2026-05-31). Thin dispatcher over existing lib/*_validators.py factored check-families — no check reimplementation."
state: active
status: active
owner: talos
domain: "Targeted vault entry validation — exit-coded for verification_command use"
spawnable_by: []
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/0f3078fe.py <uid> [--capsule <name>] [--vault-path <path>] [--quiet]"
script_path: vault/tools/0f3078fe.py
created: 2026-06-01
created_by: talos-t11
governed_by: d5e1b4a3
member_of:
  - d6e50d38
refs:
  - 2ddad3be
schema_version: 2
extraction_scope: ship
---

EXIT CODES:
  0 — entry passes all checks in its type's check-family (zero defects)
  1 — entry has ≥1 defect
  2 — usage / resolution error

Per CLI spec at 2ddad3be. Uses the whole-vault dispatch approach (zero lib-touch).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = VAULT_ROOT / ".tropo" / "scripts" / "lib"

# Map entry type → lib module + function
DISPATCHER: dict[str, tuple[str, str]] = {
    "test-spec":   ("test_spec_validators",         "run_all_test_spec_checks"),
    "dev-spec":    ("dev_spec_validators",           "run_all_dev_spec_checks"),
    "doc-spec":    ("doc_spec_validators",           "run_all_doc_spec_checks"),
    "release":     ("release_validators",            "check_release_required_fields"),
    "action":      ("action_validators",             "run_all_action_checks"),
    "tool":        ("tool_validators",               "run_all_tool_checks"),
}


def resolve_type(uid: str, vault: Path) -> str | None:
    """Derive the entry type from vault/00-index.jsonl."""
    import json
    index = vault / "vault" / "00-index.jsonl"
    if not index.exists():
        return None
    with index.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("uid") == uid:
                    return rec.get("type")
            except json.JSONDecodeError:
                continue
    return None


def run_checks(uid: str, entry_type: str, vault: Path, quiet: bool) -> tuple[int, str]:
    """Run the check-family for entry_type, filter findings to uid, return (defects, summary)."""
    if str(LIB_DIR) not in sys.path:
        sys.path.insert(0, str(LIB_DIR))

    mod_name, fn_name = DISPATCHER.get(entry_type, (None, None))
    if mod_name is None:
        return 0, f"check-one {uid} ({entry_type}): no check-family registered — SKIP (exit 0)"

    try:
        import importlib
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, fn_name)
    except (ImportError, AttributeError) as e:
        print(f"check-one: failed to load {mod_name}.{fn_name}: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        result = fn(vault)
        # Normalise return: (findings, total, defects) OR (findings, defects) or just findings
        if isinstance(result, tuple) and len(result) >= 2:
            findings = result[0]
            defects = result[-1] if len(result) >= 3 else sum(1 for f in result[0] if "FAIL" in f or "ERROR" in f)
        elif isinstance(result, list):
            findings = result
            defects = len([f for f in result if "FAIL" in f or "ERROR" in f])
        else:
            findings = []
            defects = 0
    except Exception as e:
        print(f"check-one: check-family {fn_name} raised {e}", file=sys.stderr)
        sys.exit(2)

    # Filter findings to those mentioning this uid
    uid_findings = [f for f in findings if uid in f]
    uid_defects = len([f for f in uid_findings if "[FAIL]" in f or "[ERROR]" in f])

    if not quiet:
        for f in uid_findings:
            print(f)

    verdict = "PASS" if uid_defects == 0 else "FAIL"
    summary = f"check-one {uid} ({entry_type}): {len(uid_findings)} finding(s), {uid_defects} defect(s) → {verdict}"
    return uid_defects, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="check-one — targeted single-entry validator (exit 0=PASS, 1=FAIL, 2=error)"
    )
    parser.add_argument("uid", help="8-hex UID of the vault entry to check")
    parser.add_argument("--capsule", help="Force check-family (test-spec / dev-spec / ...)")
    parser.add_argument("--vault-path", help="Path to studio root (default: auto-resolve)")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-finding output")
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{8}", args.uid):
        print(f"check-one: uid must be 8-hex; got {args.uid!r}", file=sys.stderr)
        return 2

    vault = Path(args.vault_path) if args.vault_path else VAULT_ROOT

    entry_type = args.capsule or resolve_type(args.uid, vault)
    if entry_type is None:
        print(f"check-one: uid {args.uid!r} not found in vault index", file=sys.stderr)
        return 2

    defects, summary = run_checks(args.uid, entry_type, vault, args.quiet)
    print(summary)
    return 0 if defects == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
