#!/usr/bin/env python3
"""View vault entries grouped by `owner:` (or optionally `requested_of:`).

Per [v1.4 Stream 2 §D2.4 (d9f3b8c1)](argo-os/ledger/files/d9f3b8c1.md): renders
ledger projected by ownership. Resolves entity UIDs to their declared
titles when the UID is a `type: entity` vault entry (post-Phase-2 backfill
2026-04-28: 8 crew agents + Mike + argo-vault all resolve).

Usage:
    # All entries grouped by owner:
    python3 .tropo/scripts/view/view-by-owner.py

    # Group by requested_of instead (v3 task request-lifecycle):
    python3 .tropo/scripts/view/view-by-owner.py --by requested_of

    # Filter to tasks only:
    python3 .tropo/scripts/view/view-by-owner.py --type task

    # Markdown output:
    python3 .tropo/scripts/view/view-by-owner.py --format markdown
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def resolve_vault_root(arg: str | None) -> Path:
    if arg:
        p = Path(arg).resolve()
    else:
        p = Path(__file__).resolve().parent.parent.parent.parent
    if not (p / "ledger" / "00-index.jsonl").exists():
        raise SystemExit(f"No vault/00-index.jsonl found at {p}")
    return p


def load_index(vault_root: Path) -> list[dict]:
    out = []
    with (vault_root / "ledger" / "00-index.jsonl").open() as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def build_entity_titles(entries: list[dict]) -> dict[str, str]:
    """Map entity UIDs to their human-readable title from type:entity entries."""
    out: dict[str, str] = {}
    for e in entries:
        if e.get("type") == "entity":
            uid = e.get("uid", "")
            title = e.get("title", e.get("name", ""))
            if uid:
                out[uid] = title
    return out


def render(entries: list[dict], group_field: str, entity_titles: dict[str, str], format_: str) -> str:
    by_owner: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        owner = e.get(group_field) or e.get("owner") or "<no-owner>"
        # If the field is a list (member_of-style), take first; else string
        if isinstance(owner, list):
            owner = owner[0] if owner else "<no-owner>"
        by_owner[str(owner)].append(e)

    lines = []
    if format_ == "markdown":
        lines.append(f"# Ledger by {group_field}\n")
    else:
        lines.append(f"=== Ledger by {group_field} ===\n")

    # Sort owners by entry count descending (most-active first)
    sorted_owners = sorted(by_owner.keys(), key=lambda o: -len(by_owner[o]))

    for owner in sorted_owners:
        items = by_owner[owner]
        # Resolve UID to title if it's a known entity
        resolved = entity_titles.get(owner, "")
        owner_display = f"{owner}  ({resolved})" if resolved else owner
        if format_ == "markdown":
            lines.append(f"## {owner_display}  ({len(items)} entries)")
        else:
            lines.append(f"\n[{owner_display}]  {len(items)} entries")
        for e in sorted(items, key=lambda x: x.get("title", "")):
            uid = e.get("uid", "?")
            typ = e.get("type", "?")
            status = e.get("status", e.get("stage", ""))
            title = e.get("title", "")[:60]
            if format_ == "markdown":
                lines.append(f"- [{uid}](vault/files/{uid}.md)  `{typ}` `{status}`  {title}")
            else:
                lines.append(f"  {uid}  {typ:14s} {status:10s} {title}")

    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="View ledger by owner / requested_of")
    p.add_argument("--vault-path", help="Path to vault root (default: script-relative)")
    p.add_argument("--by", choices=["owner", "requested_of", "requested_by"], default="owner",
                   help="Group-by field (default: owner)")
    p.add_argument("--type", help="Filter by entry type")
    p.add_argument("--format", choices=["terminal", "markdown"], default="terminal",
                   help="Output format (default: terminal)")
    args = p.parse_args()

    vault_root = resolve_vault_root(args.vault_path)
    all_entries = load_index(vault_root)
    entity_titles = build_entity_titles(all_entries)

    entries = all_entries
    if args.type:
        entries = [e for e in entries if e.get("type") == args.type]

    print(render(entries, args.by, entity_titles, args.format))
    return 0


if __name__ == "__main__":
    sys.exit(main())
