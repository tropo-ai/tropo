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
cli_command: "python3 vault/tools/tropo-recycle.py"
script_path: vault/tools/tropo-recycle.py
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
belt_invocation: "python3 vault/tools/tropo-recycle.py <uid>"
belt_example: "python3 vault/tools/tropo-recycle.py 8f6ea459 --reason \"superseded\""
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
import json
import re
import sys
import time
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
VAULT_SESSION_AGENTS = VAULT_ROOT / "vault" / "session-agents"
RECYCLE_ROOT = VAULT_ROOT / "recycle"
INDEX = VAULT_ROOT / "vault" / "00-index.jsonl"
TODAY = time.strftime("%Y-%m-%d")
NOW = time.strftime("%Y-%m-%dT%H:%M:%S")

# Ordered search paths: vault/files/ first (canonical), vault/session-agents/ second (v1.62 Lane S-migrate).
# Extended per Vela V56 event 00000504 finding: tropo-recycle only covered vault/files/;
# vault/session-agents/ retirement has no canonical gesture without this extension.
VAULT_SEARCH_PATHS = [VAULT_FILES, VAULT_SESSION_AGENTS]

_UID_RE = re.compile(r'\b([0-9a-f]{8})\b')


def _find_inbound_refs(target_uid: str) -> list[str]:
    """S7 (2784b2d8, v1.80): scan vault/00-index.jsonl for any entry whose `refs`
    list contains target_uid. Returns list of referencing paths (relative to vault root).
    Used by the inbound-ref guard to refuse recycling a referenced node.
    """
    if not INDEX.exists():
        return []
    refs: list[str] = []
    for raw_line in INDEX.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        rec_uid = rec.get("uid", "")
        if rec_uid == target_uid:
            continue  # skip the entry's own row
        ref_list = rec.get("refs") or []
        if isinstance(ref_list, str):
            ref_list = [ref_list]
        if target_uid in [str(r) for r in ref_list]:
            path = rec.get("path") or f"vault/files/{rec_uid}.md"
            title = rec.get("title", rec_uid)[:60]
            refs.append(f"{path} ({title!r})")
    return refs


def recycle_uid(uid: str, reason: str, dest_dir: Path) -> tuple[bool, str]:
    """Soft-delete by UID — searches VAULT_SEARCH_PATHS for <uid>.md.

    S6 fix (v1.80): also accepts an explicit path argument when ``uid`` contains
    a path separator. This lets callers outside vault/files/ (e.g. vault/playbooks/,
    vault/tools/, templated folders) use the same soft-delete discipline without
    requiring the file to live in one of the predefined search directories.
    The ``uid`` token in that case is the full or relative-to-vault-root path;
    the UID is extracted from the filename stem for the log entry.
    """
    # S6: if the argument looks like a path (contains '/' or '.md'), resolve it directly.
    if "/" in uid or uid.endswith(".md"):
        # Explicit path mode
        raw_path = uid.rstrip("/")
        if raw_path.endswith(".md"):
            raw_path = raw_path
        else:
            raw_path = raw_path + ".md"
        src = None
        # S6(b) fix (v1.80): also try the canonical search dirs (vault/files/,
        # vault/session-agents/) as bases — so a bare `<uid>.md` arg with no directory
        # component (which is path-shaped per the `.md` suffix, and therefore no longer
        # pre-stripped in main()) still resolves the same way it always has.
        for base in [VAULT_ROOT, Path.cwd(), *VAULT_SEARCH_PATHS]:
            candidate = base / raw_path if not Path(raw_path).is_absolute() else Path(raw_path)
            if candidate.exists():
                src = candidate
                break
        if src is None:
            return False, f"  SKIP {uid}: explicit path not found on disk"
        # Use the stem as the UID token for the log entry
        uid = src.stem
    else:
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
    parser.add_argument("--force", action="store_true",
                        help="Skip inbound-ref guard and recycle even if referenced (use with care)")
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
        # S6(b) fix (v1.80): do NOT reduce path-shaped args ('/' or trailing '.md') to a
        # bare UID stem here — recycle_uid()'s explicit-path branch (S6 fix) needs the
        # original path intact to detect and resolve it. The prior pre-strip stripped
        # every such arg down to a bare stem BEFORE recycle_uid ever saw it, so that
        # branch (recycle_uid lines ~105-132) was permanently unreachable dead code:
        # `agents/sa/foo/foo.md` became `foo`, which then fails recycle_uid's bare-UID
        # lookup (VAULT_SEARCH_PATHS has no `foo.md`) instead of resolving the real path.
        #
        # `uid_str` below is a SEPARATE bare-UID derivation used only for the inbound-ref
        # guard (which needs an 8-hex UID to look up in the index) and for event logging;
        # it does not affect what gets passed to recycle_uid.
        uid_str = raw.rsplit("/", 1)[-1]
        if uid_str.endswith(".md"):
            uid_str = uid_str[:-3]

        # S7 (2784b2d8, v1.80): inbound-ref guard — refuse to recycle a node that other
        # vault entries reference. The guard is fail-loud (lists the referencing entries)
        # so the caller can resolve the references before recycling, preserving lineage.
        # Bypass with --force if the references have already been resolved / are stale.
        if not args.force:
            # Only check 8-hex UIDs (not explicit paths whose stem isn't itself a UID)
            if re.fullmatch(r"[0-9a-f]{8}", uid_str):
                inbound = _find_inbound_refs(uid_str)
                if inbound:
                    print(f"  REFUSED {uid_str}: referenced by {len(inbound)} vault entry/entries "
                          f"(S7 inbound-ref guard). Resolve references before recycling, or use --force.",
                          file=sys.stderr)
                    for ref in inbound[:5]:
                        print(f"    → {ref}", file=sys.stderr)
                    if len(inbound) > 5:
                        print(f"    ... and {len(inbound) - 5} more", file=sys.stderr)
                    failures += 1
                    continue

        ok, msg = recycle_uid(raw, args.reason, dest_dir)
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
                          data={"uid": uid_str, "reason": args.reason})
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
