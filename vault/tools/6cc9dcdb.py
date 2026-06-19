#!/usr/bin/env python3
"""
---
uid: 6cc9dcdb
name: archive
type: tool
title: "archive() — flip entry state active↔archived with provenance + event"
description: "The Option-A decision's TOOLS locus (4bd03620): archive(uid, --reason, [--superseded-by], [--unarchive]) flips state active↔archived + writes archived_at/archived_by provenance + emits tropo.entry.archived or tropo.entry.unarchived. Honors per-type one-way archival rules. PAVED ROAD, not a gate — hand-edits remain legal and are caught by the ERROR-ratcheted validator. Idempotent."
status: active
state: active
owner: talos
domain: "Lifecycle — the canonical gesture for archiving governed vault entries (Option-A state discipline, 99e52c18)"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/6cc9dcdb.py <uid> --reason <reason> [--superseded-by <uid>] [--unarchive] [--force-with-reason <reason>] [--actor <label>]"
script_path: vault/tools/6cc9dcdb.py
spawnable_by:
  - all-executives
input:
  type: object
  properties:
    uid: {type: string, description: "8-hex UID of the entry to archive or unarchive"}
    reason: {type: string, description: "Why this entry is being archived (required unless unarchiving)"}
    superseded_by: {type: string, description: "UID of the entry that supersedes this one (optional)"}
    unarchive: {type: boolean, description: "Reverse a prior archive — flip state:archived → active"}
    force_with_reason: {type: string, description: "Force-unarchive a one-way-archival type with an explicit reason"}
    actor: {type: string, description: "Who is doing the archiving (default: talos-t14)"}
output:
  type: object
  description: "Exit 0 on success; non-zero on error. Prints action taken to stdout."
created: 2026-06-10
created_by: talos-t14
modified: 2026-06-10
modified_by: talos-t14
version: "1.0"
governed_by: "d5e1b4a3"
member_of:
  - "8e298cc2"   # v1.68 root
composes_with:
  - "4bd03620"   # Option-A Mike-decided brief
  - "f6c54d3f"   # events-vs-state rule
  - "99e52c18"   # state pin (archived_at/archived_by are the KEPT provenance fields)
refs:
  - "1b55f05e"   # v1.68 S1 dev-spec (this tool is its TOOLS locus)
schema_version: 2
extraction_scope: ship
trigger_description: "Flip entry state active↔archived with provenance and event."
tags: [tool, archive, lifecycle, option-a, state-active-archived, paved-road, idempotent, talos-t14]
belt: true
belt_invocation: "python3 vault/tools/6cc9dcdb.py <uid> --reason <reason>"
belt_example: "python3 vault/tools/6cc9dcdb.py 8f6ea459 --reason \"superseded\""
---
"""

import argparse
import json
import re
import sys
from pathlib import Path
import importlib.util as _ilu

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
TODAY = __import__("datetime").date.today().isoformat()

# Per-type archival rules (v1.68 S1; one-way = refuse --unarchive without --force-with-reason)
ONE_WAY_TYPES = frozenset({"working-copy", "document", "ship-artifact"})

UID_RE = re.compile(r"^[0-9a-f]{8}$")

# ── YAML helpers ──────────────────────────────────────────────────────────────

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


def _split_frontmatter(text: str):
    m = re.match(r"^---\r?\n(.*?\r?\n)---\r?\n?", text, re.DOTALL)
    return (m.group(1), text[m.end():]) if m else (None, text)


def _read_entry(uid: str):
    fp = VAULT_FILES / f"{uid}.md"
    if not fp.exists():
        return None, None, None
    text = fp.read_text(encoding="utf-8", errors="replace")
    fm_str, body = _split_frontmatter(text)
    if fm_str is None:
        return None, None, fp
    try:
        fm = yaml.safe_load(fm_str)
    except Exception as e:
        print(f"ERROR: could not parse frontmatter of {uid}: {e}", file=sys.stderr)
        return None, None, fp
    return fm, body, fp


def _write_entry(fp: Path, fm: dict, body: str):
    fm_yaml = yaml.safe_dump(fm, default_flow_style=False, sort_keys=False,
                              allow_unicode=True, width=200)
    fp.write_text(f"---\n{fm_yaml}---\n{body}", encoding="utf-8")


# ── Event emission ─────────────────────────────────────────────────────────────

def _emit(event_type: str, uid: str, actor: str, reason: str, superseded_by=None):
    try:
        _spec = _ilu.spec_from_file_location(
            "_emit_tool", VAULT_ROOT / "vault" / "tools" / "ca90f098.py"
        )
        # Fall back to direct event log append if emitter unavailable
        events_path = VAULT_ROOT / "vault" / "events.jsonl"
        import secrets, time
        event = {
            "id": f"archive-{secrets.token_hex(4)}",
            "type": event_type,
            "source": "/tools/archive",
            "source_uid": "6cc9dcdb",
            "time": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lifecycle": "evergreen",
            "subject": uid,
            "data": {"actor": actor, "uid": uid, "reason": reason},
        }
        if superseded_by:
            event["data"]["superseded_by"] = superseded_by
        if events_path.exists():
            with events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        # Also try the canonical emitter tool
        import subprocess
        data_json = json.dumps(event["data"])
        subprocess.run(
            [sys.executable, str(VAULT_ROOT / "vault" / "tools" / "ca90f098.py"),
             "--type", event_type,
             "--source", "/tools/archive",
             "--source-uid", "6cc9dcdb",
             "--lifecycle", "evergreen",
             "--subject", uid,
             "--data", data_json],
            capture_output=True, timeout=10,
            cwd=str(VAULT_ROOT),
        )
    except Exception:
        pass  # event emission is best-effort; archival still succeeds


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="archive() — flip entry state active↔archived with provenance + event"
    )
    parser.add_argument("uid", help="8-hex UID of the entry to archive or unarchive")
    parser.add_argument("--reason", help="Why this entry is being archived")
    parser.add_argument("--superseded-by", metavar="UID", help="UID of the superseding entry")
    parser.add_argument("--unarchive", action="store_true", help="Reverse: state:archived → active")
    parser.add_argument("--force-with-reason", metavar="REASON",
                        help="Force-unarchive a one-way type with explicit justification")
    parser.add_argument("--actor", default="talos-t14", help="Who is performing the action")
    args = parser.parse_args()

    uid = args.uid.strip()
    if not UID_RE.match(uid):
        print(f"ERROR: {uid!r} is not a valid 8-hex UID", file=sys.stderr)
        return 1

    fm, body, fp = _read_entry(uid)
    if fm is None or fp is None:
        print(f"ERROR: vault entry {uid!r} not found or unreadable", file=sys.stderr)
        return 1

    entry_type = str(fm.get("type") or "document")
    current_state = str(fm.get("state") or "")
    title = str(fm.get("title") or fm.get("name") or uid)

    if args.unarchive:
        # ── Unarchive path ────────────────────────────────────────────────────
        if current_state != "archived":
            print(f"[WARN] {uid} ({title!r}) — state is {current_state!r}, not archived; no-op")
            return 0

        if entry_type in ONE_WAY_TYPES and not args.force_with_reason:
            print(
                f"ERROR: {uid} is type:{entry_type} (one-way archival type). "
                f"Pass --force-with-reason to override.",
                file=sys.stderr,
            )
            return 1

        fm["state"] = "active"
        fm.pop("archived_at", None)
        fm.pop("archived_by", None)
        fm["modified"] = TODAY
        fm["modified_by"] = args.actor
        _write_entry(fp, fm, body or "")
        _emit("tropo.entry.unarchived", uid, args.actor,
              args.force_with_reason or "unarchive requested")
        force_note = f" (forced: {args.force_with_reason!r})" if args.force_with_reason else ""
        print(f"[DONE] {uid} ({title!r}) — unarchived{force_note}")
        return 0

    # ── Archive path ──────────────────────────────────────────────────────────
    if not args.reason:
        print("ERROR: --reason is required for archiving", file=sys.stderr)
        return 1

    if current_state == "archived":
        print(f"[WARN] {uid} ({title!r}) — already state:archived; no-op")
        return 0

    superseded_by = args.superseded_by
    if superseded_by and not UID_RE.match(superseded_by.strip()):
        print(f"ERROR: --superseded-by {superseded_by!r} is not a valid 8-hex UID", file=sys.stderr)
        return 1

    fm["state"] = "archived"
    fm["archived_at"] = TODAY
    fm["archived_by"] = args.actor
    if superseded_by:
        fm["superseded_by"] = superseded_by.strip()
    fm["modified"] = TODAY
    fm["modified_by"] = args.actor
    _write_entry(fp, fm, body or "")
    _emit("tropo.entry.archived", uid, args.actor, args.reason, superseded_by)

    sup_note = f" (superseded_by: {superseded_by})" if superseded_by else ""
    print(f"[DONE] {uid} ({title!r}) — archived{sup_note}: {args.reason!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
