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
  - 8dd772a0
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
from typing import Optional

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
RECYCLE_ROOT = VAULT_ROOT / "recycle"
INDEX = VAULT_ROOT / "vault" / "00-index.jsonl"
ARCHIVE_INDEX = VAULT_ROOT / "vault" / "00-archive-index.jsonl"
TODAY = time.strftime("%Y-%m-%d")
NOW = time.strftime("%Y-%m-%dT%H:%M:%S")

_UID_RE = re.compile(r'\b([0-9a-f]{8})\b')


def uid_search_paths(vault_root: Optional[Path] = None) -> "list":
    # Optional[...] rather than PEP-604 `Path | None`: this tool SHIPS, and the
    # supported floor is Python 3.9 (the stock macOS interpreter), where `X | None`
    # in a signature raises at import. `from __future__ import annotations` is the
    # usual cure and is not available here — the module carries a second docstring
    # before the imports, so a __future__ import is a SyntaxError. Caught by the
    # release build's ship-floor gate, which I had broken this morning.
    """Directories a bare ``<uid>`` may resolve in — discovered, not enumerated.

    This was a hardcoded pair (vault/files/, vault/session-agents/) and each entry
    on it was added after someone hit the gap: V56 added session-agents when a
    retirement had no gesture, and 2c6afe9e was filed when a Green City agent entry
    SKIPped as "source not found". At that point vault/agents/, vault/capsules/,
    vault/entities/ and vault/playbooks/ all held UID-named entries the gesture
    could not reach, so adding the one directory the finding named would have left
    three instances of the same bug behind it.

    "Never rm; always the gesture" has no carve-out for a directory nobody thought
    of, so the lookup asks a question instead of consulting a list: every immediate
    subdirectory of vault/ is a candidate root. A directory added next year is
    covered the day it exists. vault/files/ stays first — it holds ~99% of entries,
    so the common case resolves on the first probe, and the order is deterministic.
    """
    root = (vault_root or VAULT_ROOT) / "vault"
    files_dir = root / "files"
    if not root.is_dir():
        return [files_dir]
    others = sorted(p for p in root.iterdir() if p.is_dir() and p != files_dir)
    return [files_dir, *others]


def _find_inbound_refs(target_uid: str) -> list[str]:
    """Scan the current+archive union for entries referencing ``target_uid``.

    ADR-047 hides history from default retrieval, never from preservation
    guards.  An archived reference still makes destructive recycling unsafe.
    """
    if not INDEX.exists() and not ARCHIVE_INDEX.exists():
        return []
    refs: list[str] = []
    seen_referrers: set[str] = set()
    for index_path in (INDEX, ARCHIVE_INDEX):
        if not index_path.exists():
            continue
        for raw_line in index_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            rec_uid = rec.get("uid", "")
            if rec_uid == target_uid or rec_uid in seen_referrers:
                continue  # skip self + impossible cross-surface duplicates
            ref_list = rec.get("refs") or []
            if isinstance(ref_list, str):
                ref_list = [ref_list]
            if target_uid in [str(r) for r in ref_list]:
                path = rec.get("path") or f"vault/files/{rec_uid}.md"
                title = rec.get("title", rec_uid)[:60]
                refs.append(f"{path} ({title!r})")
                seen_referrers.add(rec_uid)
    return refs


def _remove_from_index(uid: str):
    """Governed Autonomy S2 (bba40cd7): write-owns-its-update, deletion side --
    soft-deleted entries must not linger as live index rows until the next full
    rebuild. Calls `rebuild --remove` (the deletion counterpart to `--only`,
    since recycle's whole point is that the source file no longer exists to
    re-derive from). Best-effort but loud on failure."""
    rebuild_script = VAULT_ROOT / "vault" / "tools" / "tropo-rebuild-index.py"
    if not rebuild_script.is_file():
        return
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(rebuild_script), "--remove", uid],
            cwd=str(VAULT_ROOT), capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(
                f"ERROR: {uid}'s index removal failed (exit {result.returncode}): "
                f"{result.stderr.strip()}\nRun 'python3 vault/tools/tropo-rebuild-index.py "
                f"--remove {uid}' by hand.",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"ERROR: {uid}'s index removal crashed: {e}", file=sys.stderr)


def recycle_uid(uid: str, reason: str, dest_dir: Path) -> tuple[bool, str]:
    """Soft-delete by UID — searches uid_search_paths() for <uid>.md.

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
        # S6(c) fix (v1.85, 66b6f3e8): try the path exactly as given FIRST — a caller
        # may name a non-.md governed artifact directly (e.g. vault/00-graph-registry.jsonl,
        # a vault/tools/*.py script). Pre-fix, this branch unconditionally forced a `.md`
        # suffix onto every non-.md arg, so `foo.jsonl` was searched for as `foo.jsonl.md`
        # (never exists) and silently SKIPped — "never rm, always tropo-recycle.py" has no
        # markdown-only carve-out (SELF-HEALING.md), so any governed file must resolve.
        # Only fall back to appending `.md` for a genuinely bare/extension-less path (the
        # original S6 convenience: `agents/sa/foo/foo` -> `agents/sa/foo/foo.md`).
        path_variants = [raw_path]
        if not raw_path.endswith(".md") and not Path(raw_path).suffix:
            path_variants.append(raw_path + ".md")
        src = None
        # S6(b) fix (v1.80): also try the canonical search dirs as bases — so a bare
        # `<uid>.md` arg with no directory component (which is path-shaped per the `.md`
        # suffix, and therefore no longer pre-stripped in main()) still resolves the same
        # way it always has.
        for base in [VAULT_ROOT, Path.cwd(), *uid_search_paths()]:
            for variant in path_variants:
                candidate = base / variant if not Path(variant).is_absolute() else Path(variant)
                if candidate.exists():
                    src = candidate
                    break
            if src is not None:
                break
        if src is None:
            return False, f"  SKIP {uid}: explicit path not found on disk"
        # Use the stem as the UID token for the log entry
        uid = src.stem
    else:
        search_paths = uid_search_paths()
        matches = [d / f"{uid}.md" for d in search_paths if (d / f"{uid}.md").exists()]
        if len(matches) > 1:
            # UIDs are unique by OS invariant, so two homes for one UID is drift, and
            # picking the first silently would soft-delete a file the caller did not name.
            where = ", ".join(str(m.relative_to(VAULT_ROOT)) for m in matches)
            return False, (
                f"  REFUSED {uid}: resolves in {len(matches)} directories ({where}). "
                f"Pass the explicit path of the one you mean."
            )
        if not matches:
            searched = ", ".join(str(p.relative_to(VAULT_ROOT)) for p in search_paths)
            return False, f"  SKIP {uid}: source not found (searched: {searched})"
        src = matches[0]
    # Non-.md governed artifacts keep their real extension in the recycle bin (a .jsonl
    # file silently renamed to .md would misrepresent its own type); the existing <uid>.md
    # convention is unchanged for the primary markdown case (both explicit-path .md hits
    # and every bare-UID lookup, which only ever resolves a <uid>.md candidate above).
    dest_name = f"{uid}.md" if src.suffix == ".md" else src.name
    dest = dest_dir / dest_name
    if dest.exists():
        suffix = time.strftime("%H%M%S")
        dest = dest_dir / f"{Path(dest_name).stem}.{suffix}{Path(dest_name).suffix}"
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
        # lookup (no search dir has `foo.md`) instead of resolving the real path.
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
            if re.fullmatch(r"[0-9a-f]{8}", uid_str):
                _remove_from_index(uid_str)
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
