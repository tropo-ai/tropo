#!/usr/bin/env python3
"""View vault entries grouped by intrinsic v3 `status:`.

Renders work-items (tasks, design-briefs, decisions, documents, notes, builds,
releases) projected by their v3 task.capsule status field. For each status,
shows count + per-entry summary line.

For tasks specifically, also surfaces the bucket-as-status projection per the
Tropo Work Innovation Pipeline §Idea 1 (77b4d361) four-bucket model:

    inbox    = requested + accepted   (filed; not yet active work)
    active   = active                  (work in progress)
    next     = blocked + accepted-pending  (queued)
    archive  = done + cancelled + rejected (terminal)

Per [v1.4 Stream 2 §D2.4 (d9f3b8c1)](argo-os/ledger/files/d9f3b8c1.md). Pattern
precedent: rehydrate.py + build-release.py already in .tropo/scripts/.

Usage:
    # All work-items grouped by status:
    python3 .tropo/scripts/view/view-by-status.py

    # Tasks only:
    python3 .tropo/scripts/view/view-by-status.py --type task

    # Specific vault path:
    python3 .tropo/scripts/view/view-by-status.py --vault-path /path/to/vault

    # Markdown output (for piping to a file):
    python3 .tropo/scripts/view/view-by-status.py --format markdown
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# v3 status enum vocabulary union (across task / pipeline-run / design-brief / etc.)
V3_STATUS_BUCKET = {
    # Tasks (8-state vocabulary per task.capsule v3.0)
    "requested": "inbox",
    "accepted":  "inbox",
    "active":    "active",
    "verify":    "active",
    "blocked":   "next",
    "done":      "archive",
    "rejected":  "archive",
    "cancelled": "archive",
    # Pipeline-runs / pipelines / documents
    "paused":    "next",
    "complete":  "archive",
    "draft":     "active",
    "locked":    "archive",
    "archived":  "archive",
    "published": "archive",
    "design":    "active",
    "specify":   "active",
}

WORK_ITEM_TYPES = {
    "task", "design-brief", "decision", "document", "note",
    "build", "release", "arch-spec",
}


def resolve_vault_root(arg: str | None) -> Path:
    if arg:
        p = Path(arg).resolve()
    else:
        # Default: script-relative — script lives at <vault>/.tropo/scripts/view/
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


def render(entries: list[dict], format_: str) -> str:
    by_status: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        status = e.get("status", "<no-status>")
        by_status[status].append(e)

    lines = []
    if format_ == "markdown":
        lines.append("# Ledger by Status\n")
    else:
        lines.append("=== Ledger by Status ===\n")

    # Sort by bucket order (active first, then inbox, next, archive, no-status last)
    bucket_order = {"active": 0, "inbox": 1, "next": 2, "archive": 3, None: 4}
    sorted_statuses = sorted(
        by_status.keys(),
        key=lambda s: (bucket_order.get(V3_STATUS_BUCKET.get(s)), s),
    )

    for status in sorted_statuses:
        items = by_status[status]
        bucket = V3_STATUS_BUCKET.get(status, "<unknown>")
        header = f"## {status}  ({len(items)} entries, bucket: {bucket})" if format_ == "markdown" \
                 else f"\n[{status}]  {len(items)} entries  (bucket: {bucket})"
        lines.append(header)
        for e in sorted(items, key=lambda x: x.get("title", "")):
            uid = e.get("uid", "?")
            typ = e.get("type", "?")
            title = e.get("title", "")[:70]
            if format_ == "markdown":
                lines.append(f"- [{uid}](vault/files/{uid}.md)  `{typ}`  {title}")
            else:
                lines.append(f"  {uid}  {typ:14s} {title}")

    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="View ledger by intrinsic v3 status")
    p.add_argument("--vault-path", help="Path to vault root (default: script-relative)")
    p.add_argument("--type", help="Filter by entry type (e.g. task, design-brief)")
    p.add_argument("--format", choices=["terminal", "markdown"], default="terminal",
                   help="Output format (default: terminal)")
    args = p.parse_args()

    vault_root = resolve_vault_root(args.vault_path)
    entries = load_index(vault_root)

    if args.type:
        entries = [e for e in entries if e.get("type") == args.type]
    else:
        entries = [e for e in entries if e.get("type") in WORK_ITEM_TYPES]

    print(render(entries, args.format))
    return 0


if __name__ == "__main__":
    sys.exit(main())
