#!/usr/bin/env python3
"""test_emit_event_dual_write_atomicity.py — v1.55 Behavior 3: SQLite dual-write atomicity.

Verifies that after a successful emit:
- JSONL and SQLite row counts always match (no split-brain state)
- A recovery round-trip (delete SQLite + rebuild-events-sqlite) restores count parity

Does NOT inject SQLITE failures (emit-event documents SQLite failures as non-blocking;
JSONL is canonical per events.capsule v1.1 §5). Tests the documented failure recovery path.
"""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
EMIT = VAULT_ROOT / "vault" / "tools" / "ca90f098.py"
REBUILD = VAULT_ROOT / "vault" / "tools" / "4d20a322.py"
JSONL = VAULT_ROOT / "vault" / "events" / "00-events.jsonl"
SQLITE = VAULT_ROOT / "vault" / "events" / "00-events-index.sqlite"


def count_jsonl() -> int:
    if not JSONL.exists():
        return 0
    return sum(1 for l in JSONL.read_text().splitlines()
               if l.strip() and not l.strip().startswith("#") and _is_json(l))


def count_sqlite() -> int:
    if not SQLITE.exists():
        return 0
    import sqlite3
    conn = sqlite3.connect(str(SQLITE))
    n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()
    return n


def _is_json(s: str) -> bool:
    try:
        json.loads(s); return True
    except json.JSONDecodeError:
        return False


def emit(data: str = "dual-write-test") -> int:
    r = subprocess.run([sys.executable, str(EMIT),
                        "--type", "tropo.message.sent",
                        "--source", "/agents/test",
                        "--source-uid", "123e12e7",
                        "--lifecycle", "ephemeral",
                        "--data", f'{{"body": "{data}"}}'],
                       cwd=str(VAULT_ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"emit failed: {r.stderr.strip()}")
    return int(json.loads(r.stdout.strip())["id"])


def rebuild_sqlite() -> int:
    r = subprocess.run([sys.executable, str(REBUILD)],
                       cwd=str(VAULT_ROOT), capture_output=True, text=True)
    return r.returncode


def main() -> int:
    passed = True
    checks: list[tuple[str, bool]] = []

    # Step 1: Emit one event; verify JSONL == SQLite immediately
    pre_jsonl = count_jsonl()
    pre_sqlite = count_sqlite()
    emit("dual-write-atomicity-1")
    post_jsonl = count_jsonl()
    post_sqlite = count_sqlite()
    checks.append(("JSONL gained 1 row after emit", post_jsonl == pre_jsonl + 1))
    checks.append(("SQLite gained 1 row after emit", post_sqlite == pre_sqlite + 1))
    checks.append(("JSONL == SQLite after emit", post_jsonl == post_sqlite))

    # Step 2: Delete SQLite; verify JSONL still intact
    if SQLITE.exists():
        SQLITE.unlink()
    checks.append(("JSONL intact after SQLite deletion", count_jsonl() == post_jsonl))
    checks.append(("SQLite gone", not SQLITE.exists()))

    # Step 3: Rebuild SQLite from JSONL; verify parity restored
    rc = rebuild_sqlite()
    checks.append(("rebuild-events-sqlite exit 0", rc == 0))
    rebuilt_jsonl = count_jsonl()
    rebuilt_sqlite = count_sqlite()
    checks.append(("Parity restored after rebuild", rebuilt_jsonl == rebuilt_sqlite))
    checks.append(("SQLite count matches JSONL after rebuild", rebuilt_sqlite == post_jsonl))

    for label, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}")
        if not ok:
            passed = False

    print(f"\n{'PASS' if passed else 'FAIL'} — SQLite dual-write atomicity + recovery test")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
