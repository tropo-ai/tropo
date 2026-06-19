#!/usr/bin/env python3
"""
---
uid: 1545ac97
type: tool
name: query-events
trigger_description: "Query historical event log with advanced filtering."
title: "query-events — CLI Event Log Query Wrapper"
status: active
owner: talos
domain: Historical event query
transport: cli
cli_command: "python3 vault/tools/1545ac97.py"
implementation_kind: python-script
spawnable_by: [talos, argus, vela, orpheus, metis, cosmo]
input:
  type: object
  properties:
    type: {type: string, description: "Filter by event type"}
    source_uid: {type: string, description: "Filter by source_uid"}
    correlationid: {type: string, description: "Filter by correlationid (chain)"}
    limit: {type: integer, description: "Max results (default 20)"}
    since_id: {type: string, description: "Return events with id > since_id"}
output:
  type: array
  items: {type: object, description: "CloudEvents event row"}
write_scope: []
created: 2026-05-26
created_by: talos-t10
version: "1.0"
governed_by: d5e1b4a3
member_of: ["8dd772a0"]
schema_version: 2
extraction_scope: ship
belt: true
belt_invocation: "python3 vault/tools/1545ac97.py"
belt_example: "python3 vault/tools/1545ac97.py --type tropo.broadcast.crew"
---

Thin SQL wrapper over 00-events-index.sqlite so agents can query without SQL knowledge.
Falls back to JSONL scan if SQLite is absent.
"""

from __future__ import annotations
import argparse, json, sqlite3, sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
JSONL_PATH = VAULT_ROOT / "vault" / "events" / "00-events.jsonl"
SQLITE_PATH = VAULT_ROOT / "vault" / "events" / "00-events-index.sqlite"
CURSOR_DIR  = VAULT_ROOT / "vault" / "events"  # .cursor-<party>.json lives here


def _cursor_path(party_uid: str) -> Path:
    return CURSOR_DIR / f".cursor-{party_uid}.json"


def load_cursor(party_uid: str) -> str | None:
    """Load last-seen event ID for a party cursor. Returns None if no cursor yet."""
    p = _cursor_path(party_uid)
    try:
        return json.loads(p.read_text())["last_id"]
    except Exception:
        return None


def save_cursor(party_uid: str, last_id: str) -> None:
    """Persist last-seen event ID for a party cursor."""
    try:
        _cursor_path(party_uid).write_text(json.dumps({"last_id": last_id}))
    except Exception:
        pass


def query_sqlite(event_type: str | None, source_uid: str | None,
                 correlationid: str | None, limit: int, since_id: str | None,
                 party_uid: str | None = None,
                 severity: str | None = None) -> list[dict]:
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    wheres, params = [], []
    if event_type:
        wheres.append("type = ?"); params.append(event_type)
    if source_uid:
        wheres.append("source_uid = ?"); params.append(source_uid)
    if correlationid:
        wheres.append("correlationid = ?"); params.append(correlationid)
    if since_id:
        wheres.append("CAST(id AS INTEGER) > CAST(? AS INTEGER)"); params.append(since_id)
    # V7 v1.59: --party filter: subject OR source_uid matches party_uid
    if party_uid:
        wheres.append("(source_uid = ? OR subject = ?)"); params.extend([party_uid, party_uid])
    # --severity: filter on data.severity field (G77 boot finding; Tier 2 cf8c3be9 documents this)
    if severity:
        wheres.append("json_extract(raw, '$.data.severity') = ?"); params.append(severity)
    sql = "SELECT raw FROM events"
    if wheres:
        sql += " WHERE " + " AND ".join(wheres)
    sql += f" ORDER BY CAST(id AS INTEGER) DESC LIMIT {int(limit)}"
    rows = [json.loads(r["raw"]) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def query_jsonl(event_type: str | None, source_uid: str | None,
                correlationid: str | None, limit: int, since_id: str | None,
                party_uid: str | None = None,
                severity: str | None = None) -> list[dict]:
    results = []
    for line in reversed(JSONL_PATH.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event_type and ev.get("type") != event_type:
            continue
        if source_uid and ev.get("source_uid") != source_uid:
            continue
        if correlationid and ev.get("correlationid") != correlationid:
            continue
        if since_id and int(ev.get("id", "0")) <= int(since_id):
            continue
        # V7: party filter — subject OR source_uid matches
        if party_uid and ev.get("source_uid") != party_uid and ev.get("subject") != party_uid:
            continue
        # --severity: filter on data.severity
        if severity and ev.get("data", {}).get("severity") != severity:
            continue
        results.append(ev)
        if len(results) >= limit:
            break
    return results


def main() -> int:
    p = argparse.ArgumentParser(description="Query vault/events/ event log")
    p.add_argument("--type", default=None)
    p.add_argument("--source-uid", default=None, dest="source_uid")
    p.add_argument("--correlationid", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--since-id", default=None, dest="since_id")
    p.add_argument("--jsonl", action="store_true", help="Force JSONL scan (skip SQLite)")
    # V7 v1.59: --party flag — subject-OR-source filter with cursor state
    p.add_argument("--party", default=None,
                   help="V7: filter events where source_uid OR subject == party UID; "
                        "uses cursor in vault/events/.cursor-<uid>.json for --since-id default")
    p.add_argument("--update-cursor", action="store_true", dest="update_cursor",
                   help="V7: persist last-seen event ID to cursor file after query")
    p.add_argument("--severity", default=None,
                   help="Filter events by data.severity field (e.g. 'flash'); "
                        "documents the Tier 2 cf8c3be9 FLASH-alert read pattern")
    args = p.parse_args()

    # V7: --party implies cursor-based since_id if --since-id not given explicitly
    since_id = args.since_id
    if args.party and since_id is None:
        since_id = load_cursor(args.party)

    if SQLITE_PATH.exists() and not args.jsonl:
        results = query_sqlite(args.type, args.source_uid, args.correlationid,
                               args.limit, since_id, party_uid=args.party,
                               severity=args.severity)
    elif JSONL_PATH.exists():
        results = query_jsonl(args.type, args.source_uid, args.correlationid,
                              args.limit, since_id, party_uid=args.party,
                              severity=args.severity)
    else:
        print("ERROR: no event log found", file=sys.stderr)
        return 1

    # V7: persist cursor if --update-cursor and results non-empty
    if args.party and args.update_cursor and results:
        newest_id = max(r["id"] for r in results)
        save_cursor(args.party, newest_id)

    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
