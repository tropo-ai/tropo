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
cli_command: "python3 vault/tools/tropo-vault-search.py"
script_path: vault/tools/tropo-vault-search.py
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
trigger_description: "The lookup verb. Find any tool/skill/entry not on the belt."
belt: true
extraction_scope: ship
title: "vault-search — Multi-field vault index search"
belt_invocation: "python3 vault/tools/tropo-vault-search.py \"<query>\""
belt_example: "python3 vault/tools/tropo-vault-search.py \"argus soul\""
---
"""

"""
vault-search.py — Multi-field vault index search for crew agents.

Searches vault/00-index.jsonl across ALL fields in each entry (title, uid,
type, agent, document_type, subtype, description, tags, name, etc.).
Naturally broad — like grep on the full JSON line, but ranked by relevance.

Usage:
  python3 vault/tools/tropo-vault-search.py "query terms" [--limit N] [--json]

Output (default): human-readable ranked list
Output (--json):  JSON array for programmatic use by agents / API routes

Examples:
  python3 vault/tools/tropo-vault-search.py "metis soul"
  python3 vault/tools/tropo-vault-search.py "published kb-article" --limit 5 --json
  python3 vault/tools/tropo-vault-search.py "argus architecture spec" --json
"""

import json
import sys
import argparse
from pathlib import Path

# Resolve vault root from this script's location (.tropo/scripts/ → vault root)
SCRIPT_DIR   = Path(__file__).resolve().parent
VAULT_ROOT   = SCRIPT_DIR.parent.parent  # argo-os/
INDEX_PATH   = VAULT_ROOT / "vault" / "00-index.jsonl"
FILES_DIR    = VAULT_ROOT / "vault" / "files"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from lib import index_surfaces  # noqa: E402


def build_haystack(entry: dict) -> str:
    """Flatten all string-valued fields in a vault index entry into one searchable string."""
    parts = []
    for v in entry.values():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            parts.extend(str(i) for i in v if i)
    return " ".join(parts).lower()


SQLITE_PATH = VAULT_ROOT / "vault" / "00-index.sqlite"


def search_content(query: str, limit: int = 10) -> list[dict]:
    """Full-text search over entry BODIES via the SQLite FTS index.

    The default search flattens an entry's index FIELDS (title, type, tags...)
    and never sees body text. That is fine for studio artifacts, whose titles
    describe them, and useless for a mounted notes corpus, where the words you
    remember are in the body and the filename is a date.

    The FTS table has always been built and, until now, nothing ever queried it
    (metis-g99 2026-08-02) -- a full-text index with no consumer. This is that
    consumer. Falls back to returning nothing (not an error) when the SQLite
    surface is absent, so callers can degrade to field search.
    """

    import sqlite3

    if not SQLITE_PATH.exists():
        return []
    terms = query.strip()
    if not terms:
        return []
    try:
        conn = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        # FTS5 MATCH treats bare punctuation as syntax; quote each term so a
        # user searching for "greg-cole" or "C++" gets a search, not a crash.
        quoted = " ".join('"' + t.replace('"', '""') + '"' for t in terms.split())
        rows = conn.execute(
            "SELECT f.uid, f.title, e.type, e.status, e.state, "
            "snippet(entries_fts, 2, '[', ']', ' ... ', 12) "
            "FROM entries_fts f LEFT JOIN entries e ON e.uid = f.uid "
            "WHERE entries_fts MATCH ? ORDER BY rank LIMIT ?",
            (quoted, limit),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    out = []
    for uid, title, etype, status, state, snip in rows:
        # The SQLite index unions BOTH surfaces (3,086 current + 1,798 archive
        # at time of writing), so a content hit may be archived or superseded
        # history. Label it with the same ADR-047 predicate the JSONL path uses
        # -- mislabelling a superseded doc as current is how a reader acts on
        # retired guidance. (Fixed same-day by metis-g99 after shipping this
        # hardcoded to "current".)
        archived = (state == "archived") or (status == "superseded")
        out.append({
            "uid": uid,
            "title": title or uid,
            "type": etype,
            "status": status,
            "state": state,
            "surface": "archive" if archived else "current",
            "score": 1,
            "snippet": " ".join((snip or "").split()),
            "path": str(FILES_DIR / f"{uid}.md"),
        })
    return out


def search(query: str, limit: int = 10, *, include_archive: bool = False) -> list[dict]:
    terms = query.lower().split()
    if not terms:
        return []

    if not INDEX_PATH.exists():
        print(f"ERROR: vault index not found at {INDEX_PATH}", file=sys.stderr)
        sys.exit(1)

    scored = []
    for entry in index_surfaces.load_index_records(
        VAULT_ROOT, include_archive=include_archive
    ):
        if not entry.get("uid"):
            continue

        hay = build_haystack(entry)
        score = sum(1 for t in terms if t in hay)
        if score == 0:
            continue

        source_path = entry.get("path")
        scored.append({
            "uid":           entry.get("uid"),
            "title":         entry.get("title") or entry.get("name") or entry["uid"],
            "type":          entry.get("type"),
            "agent":         entry.get("agent"),
            "document_type": entry.get("document_type"),
            "status":        entry.get("status"),
            "state":         entry.get("state"),
            "surface":       "archive" if index_surfaces.is_archive_record(entry) else "current",
            "score":         score,
            "path":          str(VAULT_ROOT / source_path) if source_path else str(
                FILES_DIR / f"{entry['uid']}.md"
            ),
        })

    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


def main():
    parser = argparse.ArgumentParser(description="Search the Tropo vault index.")
    parser.add_argument("query", help="Search terms")
    parser.add_argument("--limit", type=int, default=10, help="Max results (default 10)")
    parser.add_argument("--json", action="store_true", help="Output JSON array")
    parser.add_argument(
        "--include-archive",
        action="store_true",
        help="Opt in to history by unioning vault/00-archive-index.jsonl",
    )
    parser.add_argument(
        "--content",
        action="store_true",
        help="Full-text search entry BODIES via the SQLite FTS index "
             "(finds words inside notes; default searches index fields only)",
    )
    args = parser.parse_args()

    if args.content:
        results = search_content(args.query, args.limit)
    else:
        results = search(args.query, args.limit, include_archive=args.include_archive)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print(f"No results for: {args.query}")
            return
        print(f"\n{len(results)} result(s) for \"{args.query}\":\n")
        for i, r in enumerate(results, 1):
            meta = " | ".join(filter(None, [
                r.get("type"), r.get("agent"), r.get("document_type"),
                r.get("status"), r.get("surface"),
            ]))
            print(f"  {i}. [{r['score']}/{len(args.query.split())}] {r['title']}")
            if meta:
                print(f"       {meta}")
            if r.get("snippet"):
                print(f"       …{r['snippet']}…")
            print(f"       {r['path']}")
        print()


if __name__ == "__main__":
    main()
