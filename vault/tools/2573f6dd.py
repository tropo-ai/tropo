#!/usr/bin/env python3
"""
---
uid: 2573f6dd
name: tropo-recycle
type: tool
status: active
owner: talos
domain: "Soft-delete gesture for vault/files/ entries."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/2573f6dd.py"
script_path: vault/tools/2573f6dd.py
spawnable_by:
  - all-executives
input:
  type: object
  description: "See tool usage for argument details"
created: 2026-05-27
created_by: talos-t10
governed_by: d5e1b4a3
member_of:
  - c7e4f9a2
schema_version: 2
trigger_description: "Soft-delete governed entries (mv to recycle/). Never use rm."
belt: true
extraction_scope: ship
title: "tropo-recycle — Soft-delete governed vault entries"
belt_invocation: "python3 vault/tools/2573f6dd.py <uid>"
belt_example: "python3 vault/tools/2573f6dd.py 8f6ea459 --reason \"superseded\""
---
"""

"""Soft-delete gesture for vault/files/ entries.

Mvs target UIDs from vault/files/<uid>.md to
recycle/agent-deletions/<YYYY-MM-DD>/<uid>.md with a one-line log entry.

Discipline: never `rm` files in vault/files/; always use this gesture.
Recovery is `mv` back. Surfaced by the v1.35.0 critical incident — bash
`grep -l <keyword> | xargs rm` cleanup pattern deleted load-bearing brief
and spec because they described the feature the keyword named.

Usage:
  python3 tropo-recycle.py <uid> [<uid> ...] [--reason <text>]
  cat uids.txt | python3 tropo-recycle.py --stdin [--reason <text>]

Exit codes:
  0  All targets recycled
  1  Partial — some targets failed (missing or unwritable); see stderr
  2  Usage error
"""
import argparse
import sys
import time
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
VAULT_SESSION_AGENTS = VAULT_ROOT / "vault" / "session-agents"
RECYCLE_ROOT = VAULT_ROOT / "recycle"
TODAY = time.strftime("%Y-%m-%d")
NOW = time.strftime("%Y-%m-%dT%H:%M:%S")

# Ordered search paths: vault/files/ first (canonical), vault/session-agents/ second (v1.62 Lane S-migrate).
# Extended per Vela V56 event 00000504 finding: tropo-recycle only covered vault/files/;
# vault/session-agents/ retirement has no canonical gesture without this extension.
VAULT_SEARCH_PATHS = [VAULT_FILES, VAULT_SESSION_AGENTS]


def recycle_uid(uid: str, reason: str, dest_dir: Path) -> tuple[bool, str]:
    src = None
    for search_dir in VAULT_SEARCH_PATHS:
        candidate = search_dir / f"{uid}.md"
        if candidate.exists():
            src = candidate
            break
    if src is None:
        searched = ", ".join(str(p.relative_to(VAULT_ROOT)) for p in VAULT_SEARCH_PATHS)
        return False, f"  SKIP {uid}: source not found (searched: {searched})"
    dest = dest_dir / f"{uid}.md"
    if dest.exists():
        suffix = time.strftime("%H%M%S")
        dest = dest_dir / f"{uid}.{suffix}.md"
    try:
        src.rename(dest)
    except OSError as e:
        return False, f"  FAIL {uid}: {e}"
    log_entry = (
        f"{NOW}\tuid:{uid}\treason:{reason}"
        f"\tmoved_from:{src.relative_to(VAULT_ROOT)}"
        f"\tmoved_to:{dest.relative_to(VAULT_ROOT)}\n"
    )
    log_path = dest_dir / "recycle.log"
    with log_path.open("a") as f:
        f.write(log_entry)
    return True, f"  RECYCLED {uid} → {dest.relative_to(VAULT_ROOT)}"


def main():
    parser = argparse.ArgumentParser(
        description="Soft-delete vault/files/<uid>.md entries to recycle/agent-deletions/<date>/.",
        epilog="Vault deletion discipline: never `rm` files in vault/files/; "
               "always use this gesture. Recovery is mv back.",
    )
    parser.add_argument("uids", nargs="*", help="8-hex UID(s) to recycle (one or more)")
    parser.add_argument("--stdin", action="store_true", help="Read UIDs from stdin (one per line)")
    parser.add_argument("--reason", default="agent-cleanup",
                        help="Free-text reason for the log entry")
    args = parser.parse_args()

    uids = list(args.uids)
    if args.stdin:
        uids.extend(line.strip() for line in sys.stdin if line.strip())
    if not uids:
        parser.error("provide UIDs as args, --stdin, or both")

    dest_dir = RECYCLE_ROOT / "agent-deletions" / TODAY
    dest_dir.mkdir(parents=True, exist_ok=True)

    successes = 0
    failures = 0
    for raw in uids:
        uid = raw
        if uid.endswith(".md"):
            uid = uid[:-3]
        if "/" in uid:
            uid = uid.rsplit("/", 1)[-1]
        ok, msg = recycle_uid(uid, args.reason, dest_dir)
        print(msg, file=(sys.stdout if ok else sys.stderr))
        if ok:
            successes += 1
            # C.3 — Stream C auto-emission: tropo.substrate.recycled (v1.58)
            try:
                _scripts = Path(__file__).resolve().parents[2] / ".tropo" / "scripts"
                if str(_scripts) not in sys.path:
                    sys.path.insert(0, str(_scripts))
                from lib.event_emitter import auto_emit
                auto_emit("tropo.substrate.recycled", "/tools/tropo-recycle", "123e12e7",
                          lifecycle="evergreen",
                          data={"uid": uid, "reason": args.reason})
            except Exception:
                pass
        else:
            failures += 1

    print(
        f"\nRecycled {successes}/{len(uids)} UIDs to "
        f"{dest_dir.relative_to(VAULT_ROOT)}",
        file=sys.stderr,
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
