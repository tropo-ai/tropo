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
cli_command: "python3 vault/tools/tropo-query-events.py"
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
modified: 2026-07-31
modified_by: vela-v71
version: "1.4"
v1_4_note: "Captain-mode edit (talos-owned tool; Talos notified per the A95/A106 captain-edit precedent), Mike-directed 'I want it fixed permanently' 2026-07-31. Closes the trigger gap left by v1.9: the self-heal existed only on the WRITE path, so it could only fire when something emitted. On a multi-agent day the dominant divergence source is `git merge` — another agent's stream lands in the canonical union with NO local emit — so nothing triggered the heal and every read warned until a human ran tropo-rebuild-events-sqlite.py by hand. Observed live 2026-07-31: the projection diverged three times in 40 minutes purely from integrating crew pushes. THE FIX MOVES THE TRIGGER FROM A COMMAND TO A CONDITION: event_identity.ensure_sqlite_projection() pairs detection with repair in one shared gesture, and emit / check-events / query-events all call it, so ANY touch of the log repairs a divergence regardless of what caused it — merge, fresh clone, manual copy, or emit. Safety posture is unchanged and deliberately so: still only the sanctioned full rebuild (never an incremental patch), still cooldown-gated at 300s via a marker now SHARED across all callers so concurrent agents cannot storm it, plus a subprocess-env recursion guard (TROPO_SQLITE_AUTOHEAL_ACTIVE) and an operator escape hatch (TROPO_NO_SQLITE_AUTOHEAL) for a provably side-effect-free read. Delivery semantics are untouched: the canonical JSONL union is loaded before any repair and remains the sole delivery truth, so a heal can speed up later reads but can never change what a drain delivers. Regression-pinned by test_divergent_projection_self_heals_on_read (merge shape, read-only) and test_autoheal_is_cooldown_gated_and_never_recurses. In this tool specifically, a divergence used to force every subsequent query onto the JSONL scan until a human intervened; detection now repairs, so the fast path returns on its own."
v1_3_note: "Cut 4 R4/Q5 viewer-safe usage query under locked dev-spec 8078657b: public CLI queries are viewerless and omit usage after full-union display order derivation but before since/filter/limit/cursor update; canonical display_seq is preserved. Authorized visibility is trusted in-process only through a prevalidated Viewer + ViewerProjection; no public viewer identity or private-segment assertion flags exist. --party remains only address/cursor state."
v1_2_note: "Projection trust hardening: default queries use event_identity's shared exact event-identity coverage contract before using SQLite and warn/fall back to the canonical legacy-plus-stream JSONL union when the derived projection is partial, divergent, or unreadable."
v1_1_note: "Distributed Event Ledger dual-read: query uses immutable event_uid/correlation and derived display_seq across legacy epoch + per-writer streams."
governed_by: d5e1b4a3
member_of: ["8dd772a0"]
schema_version: 2
extraction_scope: ship
belt: true
belt_invocation: "python3 vault/tools/tropo-query-events.py"
belt_example: "python3 vault/tools/tropo-query-events.py --type tropo.broadcast.crew"
---

Thin SQL wrapper over 00-events-index.sqlite so agents can query without SQL knowledge.
Falls back to the canonical JSONL union if SQLite is absent or incomplete.
"""

from __future__ import annotations
import argparse, json, sqlite3, sys
from pathlib import Path

from lib import event_identity
from lib.distiller_capture import USAGE_EVENT_TYPE
from lib.event_visibility import (
    EventVisibilityError,
    EventVisibilityErrorCode,
    filter_usage_events,
)
from lib.viewer_projection import Viewer, ViewerProjection

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


def _apply_visibility(
    events: list[dict],
    *,
    viewer: Viewer | None,
    projection: ViewerProjection | None,
) -> list[dict]:
    """Apply secrecy to already canonically ordered, sequence-stamped events."""

    if viewer is None:
        return [
            event
            for event in events
            if event.get("type") != USAGE_EVENT_TYPE and "segment" not in event
        ]
    if projection is None:
        raise EventVisibilityError(
            code=EventVisibilityErrorCode.AUTHORITY_UNRESOLVED,
            message="an explicit viewer requires a ViewerProjection",
        )
    return filter_usage_events(events, viewer=viewer, projection=projection)


def _query_events(
    event_union: list[dict],
    event_type: str | None,
    source_uid: str | None,
    correlationid: str | None,
    limit: int,
    since_id: str | None,
    *,
    party_uid: str | None,
    severity: str | None,
    viewer: Viewer | None,
    projection: ViewerProjection | None,
) -> list[dict]:
    full_order = [
        {**event, "display_seq": display_seq}
        for display_seq, event in event_identity.derive_display_order(
            [dict(event) for event in event_union]
        )
    ]
    visible = _apply_visibility(
        full_order,
        viewer=viewer,
        projection=projection,
    )
    results: list[dict] = []
    for source_event in reversed(visible):
        event = dict(source_event)
        display_seq = int(event["display_seq"])
        if event_type and event.get("type") != event_type:
            continue
        if source_uid and event.get("source_uid") != source_uid:
            continue
        if correlationid and event.get("correlationid") != correlationid:
            continue
        if since_id and display_seq <= int(since_id):
            continue
        if (
            party_uid
            and event.get("source_uid") != party_uid
            and event.get("subject") != party_uid
        ):
            continue
        data = event.get("data")
        if severity and (
            not isinstance(data, dict) or data.get("severity") != severity
        ):
            continue
        results.append(event)
        if len(results) >= limit:
            break
    return results


def query_sqlite(event_type: str | None, source_uid: str | None,
                 correlationid: str | None, limit: int, since_id: str | None,
                 party_uid: str | None = None,
                 severity: str | None = None,
                 viewer: Viewer | None = None,
                 projection: ViewerProjection | None = None) -> list[dict]:
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    has_v2 = "display_seq" in columns and "event_uid" in columns
    selected = "raw, event_uid" if has_v2 else "raw"
    event_union: list[dict] = []
    for row in conn.execute(f"SELECT {selected} FROM events").fetchall():
        event = json.loads(row["raw"])
        if has_v2:
            event.setdefault("event_uid", row["event_uid"])
        event_union.append(event)
    conn.close()
    return _query_events(
        event_union,
        event_type,
        source_uid,
        correlationid,
        limit,
        since_id,
        party_uid=party_uid,
        severity=severity,
        viewer=viewer,
        projection=projection,
    )


def query_jsonl(event_type: str | None, source_uid: str | None,
                correlationid: str | None, limit: int, since_id: str | None,
                party_uid: str | None = None,
                severity: str | None = None,
                event_union: list[dict] | None = None,
                viewer: Viewer | None = None,
                projection: ViewerProjection | None = None) -> list[dict]:
    if event_union is None:
        event_union = event_identity.load_event_union(VAULT_ROOT)
    return _query_events(
        event_union,
        event_type,
        source_uid,
        correlationid,
        limit,
        since_id,
        party_uid=party_uid,
        severity=severity,
        viewer=viewer,
        projection=projection,
    )


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

    try:
        if SQLITE_PATH.exists() and not args.jsonl:
            event_union = event_identity.load_event_union(VAULT_ROOT)
            # v1.3: detection heals (shared, cooldown-gated) instead of only
            # warning, so a merge-induced divergence does not force every
            # subsequent query onto the slow path until a human rebuilds.
            if event_identity.ensure_sqlite_projection(
                VAULT_ROOT,
                event_union,
                sqlite_path=SQLITE_PATH,
                context="query-events",
            ):
                results = query_sqlite(
                    args.type,
                    args.source_uid,
                    args.correlationid,
                    args.limit,
                    since_id,
                    party_uid=args.party,
                    severity=args.severity,
                )
            else:
                # ensure_sqlite_projection already reported the divergence and
                # the repair outcome; this line only records the consequence.
                print(
                    "WARN: projection still not usable after the repair attempt; "
                    "falling back to canonical JSONL union",
                    file=sys.stderr,
                )
                results = query_jsonl(
                    args.type,
                    args.source_uid,
                    args.correlationid,
                    args.limit,
                    since_id,
                    party_uid=args.party,
                    severity=args.severity,
                    event_union=event_union,
                )
        elif JSONL_PATH.exists():
            results = query_jsonl(
                args.type,
                args.source_uid,
                args.correlationid,
                args.limit,
                since_id,
                party_uid=args.party,
                severity=args.severity,
            )
        else:
            # Fresh vault — no event log yet. Return empty results, exit clean.
            print("[]")
            return 0
    except EventVisibilityError as exc:
        print(f"ERROR: segment visibility refused: {exc}", file=sys.stderr)
        return 1

    # V7: persist cursor if --update-cursor and results non-empty
    if args.party and args.update_cursor and results:
        newest_id = max(int(r.get("display_seq", 0)) for r in results)
        save_cursor(args.party, str(newest_id))

    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
