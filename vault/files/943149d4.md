#!/usr/bin/env python3
"""
---
uid: 943149d4
name: vault-search
type: tool
status: active
owner: talos
domain: "vault-search.py — Multi-field vault index search for crew agents."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/943149d4.py"
script_path: vault/tools/943149d4.py
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
trigger_description: "The lookup verb. Find any tool/skill/entry not on the belt."
belt: true
extraction_scope: ship
title: "vault-search — Multi-field vault index search"
belt_invocation: "python3 vault/tools/943149d4.py \"<query>\""
belt_example: "python3 vault/tools/943149d4.py \"argus soul\""
---
"""

"""
vault-search.py — Multi-field vault index search for crew agents.

Searches vault/00-index.jsonl across ALL fields in each entry (title, uid,
type, agent, document_type, subtype, description, tags, name, etc.).
Naturally broad — like grep on the full JSON line, but ranked by relevance.

Usage:
  python3 .tropo/scripts/vault-search.py "query terms" [--limit N] [--json]

Output (default): human-readable ranked list
Output (--json):  JSON array for programmatic use by agents / API routes

Examples:
  python3 .tropo/scripts/vault-search.py "metis soul"
  python3 .tropo/scripts/vault-search.py "published kb-article" --limit 5 --json
  python3 .tropo/scripts/vault-search.py "argus architecture spec" --json
"""

import json
import sys
import os
import argparse
from pathlib import Path

# Resolve vault root from this script's location (.tropo/scripts/ → vault root)
SCRIPT_DIR   = Path(__file__).resolve().parent
VAULT_ROOT   = SCRIPT_DIR.parent.parent  # argo-os/
INDEX_PATH   = VAULT_ROOT / "vault" / "00-index.jsonl"
FILES_DIR    = VAULT_ROOT / "vault" / "files"


def build_haystack(entry: dict) -> str:
    """Flatten all string-valued fields in a vault index entry into one searchable string."""
    parts = []
    for v in entry.values():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            parts.extend(str(i) for i in v if i)
    return " ".join(parts).lower()


def search(query: str, limit: int = 10) -> list[dict]:
    terms = query.lower().split()
    if not terms:
        return []

    if not INDEX_PATH.exists():
        print(f"ERROR: vault index not found at {INDEX_PATH}", file=sys.stderr)
        sys.exit(1)

    scored = []
    with open(INDEX_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not entry.get("uid"):
                continue
            if entry.get("status") == "archived":
                continue

            hay = build_haystack(entry)
            score = sum(1 for t in terms if t in hay)
            if score == 0:
                continue

            scored.append({
                "uid":           entry.get("uid"),
                "title":         entry.get("title") or entry.get("name") or entry["uid"],
                "type":          entry.get("type"),
                "agent":         entry.get("agent"),
                "document_type": entry.get("document_type"),
                "status":        entry.get("status"),
                "score":         score,
                "path":          str(FILES_DIR / f"{entry['uid']}.md"),
            })

    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


def main():
    parser = argparse.ArgumentParser(description="Search the Tropo vault index.")
    parser.add_argument("query", help="Search terms")
    parser.add_argument("--limit", type=int, default=10, help="Max results (default 10)")
    parser.add_argument("--json", action="store_true", help="Output JSON array")
    args = parser.parse_args()

    results = search(args.query, args.limit)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print(f"No results for: {args.query}")
            return
        print(f"\n{len(results)} result(s) for \"{args.query}\":\n")
        for i, r in enumerate(results, 1):
            meta = " | ".join(filter(None, [r["type"], r["agent"], r["document_type"], r["status"]]))
            print(f"  {i}. [{r['score']}/{len(args.query.split())}] {r['title']}")
            if meta:
                print(f"       {meta}")
            print(f"       {r['path']}")
        print()


if __name__ == "__main__":
    main()
