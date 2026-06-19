#!/usr/bin/env python3
"""View vault entries grouped by tag.

Per [v1.4 Stream 2 §D2.4 (d9f3b8c1)](argo-os/ledger/files/d9f3b8c1.md). Each
entry appears in every group its tags include. Sorted by tag-count descending
(most-used tags first).

Usage:
    # All tags:
    python3 .tropo/scripts/view/view-by-tag.py

    # Single tag (substring match):
    python3 .tropo/scripts/view/view-by-tag.py --tag v1.4

    # Filter to a specific entry type:
    python3 .tropo/scripts/view/view-by-tag.py --type task

    # Markdown output:
    python3 .tropo/scripts/view/view-by-tag.py --format markdown

    # Top-N tags (default: all):
    python3 .tropo/scripts/view/view-by-tag.py --top 20
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


def render(entries: list[dict], tag_filter: str | None, top_n: int | None, format_: str) -> str:
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        tags = e.get("tags", [])
        if not isinstance(tags, list):
            continue
        for tag in tags:
            tag_str = str(tag).strip().lower()
            if tag_filter and tag_filter.lower() not in tag_str:
                continue
            by_tag[tag_str].append(e)

    lines = []
    if format_ == "markdown":
        lines.append("# Ledger by Tag\n")
    else:
        lines.append("=== Ledger by Tag ===\n")

    sorted_tags = sorted(by_tag.keys(), key=lambda t: (-len(by_tag[t]), t))
    if top_n:
        sorted_tags = sorted_tags[:top_n]

    if not sorted_tags:
        lines.append("(no tags matched)")
        return "\n".join(lines) + "\n"

    for tag in sorted_tags:
        items = by_tag[tag]
        if format_ == "markdown":
            lines.append(f"## #{tag}  ({len(items)} entries)")
        else:
            lines.append(f"\n[#{tag}]  {len(items)} entries")
        for e in sorted(items, key=lambda x: x.get("title", "")):
            uid = e.get("uid", "?")
            typ = e.get("type", "?")
            title = e.get("title", "")[:65]
            if format_ == "markdown":
                lines.append(f"- [{uid}](vault/files/{uid}.md)  `{typ}`  {title}")
            else:
                lines.append(f"  {uid}  {typ:14s} {title}")

    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="View ledger by tag")
    p.add_argument("--vault-path", help="Path to vault root (default: script-relative)")
    p.add_argument("--tag", help="Filter by tag substring (case-insensitive)")
    p.add_argument("--type", help="Filter by entry type")
    p.add_argument("--top", type=int, help="Show only top-N tags by frequency")
    p.add_argument("--format", choices=["terminal", "markdown"], default="terminal",
                   help="Output format (default: terminal)")
    args = p.parse_args()

    vault_root = resolve_vault_root(args.vault_path)
    entries = load_index(vault_root)

    if args.type:
        entries = [e for e in entries if e.get("type") == args.type]

    print(render(entries, args.tag, args.top, args.format))
    return 0


if __name__ == "__main__":
    sys.exit(main())
