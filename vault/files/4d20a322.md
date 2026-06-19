#!/usr/bin/env python3
"""
---
uid: 4d20a322
type: tool
name: rebuild-events-sqlite
title: "rebuild-events-sqlite — Regenerate SQLite from Canonical JSONL"
status: active
owner: talos
domain: messaging
transport: cli
cli_command: "python3 vault/tools/4d20a322.py"
implementation_kind: python-script
spawnable_by: [talos, vela]
input:
  type: object
  properties:
    dry_run: {type: boolean, description: "Print row count without writing"}
output:
  type: object
  properties:
    rows_written: {type: integer}
write_scope: [vault/events/]
created: 2026-05-26
created_by: talos-t10
version: "1.0"
governed_by: d5e1b4a3
member_of: ["8dd772a0"]
schema_version: 2
extraction_scope: ship
---

Recovery tool: regenerate 00-events-index.sqlite from canonical 00-events.jsonl.
Use when SQLite is deleted, corrupted, or diverged from JSONL.
"""

from __future__ import annotations
import argparse, json, sqlite3, sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
JSONL_PATH = VAULT_ROOT / "vault" / "events" / "00-events.jsonl"
SQLITE_PATH = VAULT_ROOT / "vault" / "events" / "00-events-index.sqlite"


def rebuild(dry_run: bool = False) -> int:
    if not JSONL_PATH.exists():
        print("ERROR: 00-events.jsonl not found", file=sys.stderr)
        return 1

    events = []
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"WARN: skipping malformed line: {e}", file=sys.stderr)

    if dry_run:
        print(f"DRY RUN: {len(events)} event(s) would be written to SQLite")
        return 0

    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()

    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE events (
            id TEXT PRIMARY KEY, specversion TEXT NOT NULL, type TEXT NOT NULL,
            source TEXT NOT NULL, time TEXT NOT NULL, subject TEXT,
            source_uid TEXT NOT NULL, lifecycle TEXT NOT NULL,
            correlationid TEXT, data TEXT, raw TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX idx_type ON events(type)")
    conn.execute("CREATE INDEX idx_source_uid ON events(source_uid)")
    conn.execute("CREATE INDEX idx_correlationid ON events(correlationid)")

    for ev in events:
        conn.execute(
            "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ev.get("id"), ev.get("specversion"), ev.get("type"), ev.get("source"),
             ev.get("time"), ev.get("subject"), ev.get("source_uid"), ev.get("lifecycle"),
             ev.get("correlationid"),
             json.dumps(ev.get("data")) if ev.get("data") else None,
             json.dumps(ev, ensure_ascii=False))
        )
    conn.commit()
    conn.close()
    print(f"Rebuilt: {len(events)} event(s) → {SQLITE_PATH.name}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Rebuild SQLite from canonical JSONL")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    return rebuild(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
