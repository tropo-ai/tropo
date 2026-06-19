#!/usr/bin/env python3
"""test_emit_event_concurrent.py — v1.55 Behavior 2 regression: concurrent emit contention.

Fires 10 parallel emit-event invocations and verifies:
- All 10 land in JSONL (no lost writes under concurrent access)
- All 10 land in SQLite (dual-write integrity)
- IDs are sequential with no gaps
- No duplicate IDs (fcntl.flock exclusive-lock prevents concurrent corruption)
"""
from __future__ import annotations
import json, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
EMIT = VAULT_ROOT / "vault" / "tools" / "ca90f098.py"
QUERY = VAULT_ROOT / "vault" / "tools" / "1545ac97.py"
JSONL = VAULT_ROOT / "vault" / "events" / "00-events.jsonl"
SQLITE = VAULT_ROOT / "vault" / "events" / "00-events-index.sqlite"

N_CONCURRENT = 10


def emit_one(i: int) -> dict:
    result = subprocess.run(
        [sys.executable, str(EMIT),
         "--type", "tropo.message.sent",
         "--source", "/agents/test",
         "--source-uid", "123e12e7",
         "--lifecycle", "ephemeral",
         "--data", f'{{"body": "concurrent-test-{i}"}}'],
        cwd=str(VAULT_ROOT),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip(), "index": i}
    return json.loads(result.stdout.strip())


def count_jsonl_events() -> int:
    if not JSONL.exists():
        return 0
    count = 0
    for line in JSONL.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                json.loads(line)
                count += 1
            except json.JSONDecodeError:
                pass
    return count


def count_sqlite_events() -> int:
    if not SQLITE.exists():
        return 0
    import sqlite3
    conn = sqlite3.connect(str(SQLITE))
    n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()
    return n


def main() -> int:
    pre_jsonl = count_jsonl_events()
    pre_sqlite = count_sqlite_events()

    print(f"Pre-test: JSONL={pre_jsonl} SQLite={pre_sqlite}")
    print(f"Firing {N_CONCURRENT} concurrent emits...")

    results = []
    with ThreadPoolExecutor(max_workers=N_CONCURRENT) as pool:
        futures = [pool.submit(emit_one, i) for i in range(N_CONCURRENT)]
        for f in as_completed(futures):
            results.append(f.result())

    errors = [r for r in results if "error" in r]
    successes = [r for r in results if "id" in r]

    post_jsonl = count_jsonl_events()
    post_sqlite = count_sqlite_events()

    ids = sorted(int(r["id"]) for r in successes)
    has_gaps = ids != list(range(min(ids), max(ids) + 1)) if ids else False
    has_duplicates = len(ids) != len(set(ids))

    print(f"Post-test: JSONL={post_jsonl} SQLite={post_sqlite}")
    print(f"Successes: {len(successes)} Errors: {len(errors)}")
    if errors:
        for e in errors:
            print(f"  Error: {e}")

    passed = True
    checks = [
        ("All 10 emits succeeded", len(errors) == 0),
        ("JSONL gained exactly 10 rows", post_jsonl - pre_jsonl == N_CONCURRENT),
        ("SQLite gained exactly 10 rows", post_sqlite - pre_sqlite == N_CONCURRENT),
        ("No duplicate event IDs", not has_duplicates),
        ("No ID gaps in emitted sequence", not has_gaps),
    ]
    for label, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}")
        if not ok:
            passed = False

    print(f"\n{'PASS' if passed else 'FAIL'} — concurrent emit contention test")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
