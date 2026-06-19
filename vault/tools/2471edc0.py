#!/usr/bin/env python3
"""
---
uid: 2471edc0
type: tool
name: check-events
trigger_description: "Drain your event log (directed + broadcasts; cannot miss a reply_required)."
title: "check-events — identity-resolved event drain (directed + broadcasts; cannot miss a reply_required)"
status: active
owner: talos
domain: Identity-resolved event drain
transport: cli
cli_command: "python3 vault/tools/2471edc0.py --as <name>"
implementation_kind: python-script
spawnable_by: [talos, argus, vela, orpheus, metis, cosmo]
input:
  type: object
  required: [as]
  properties:
    as: {type: string, description: "Caller agent name — resolved to party_uid via registry (no UID argument)"}
    all: {type: boolean, description: "Include telemetry events (default: messaging-only)"}
    raw: {type: boolean, description: "Same as --all"}
    until-answered: {type: boolean, description: "Bounded poll mode with degrading cadence until all reply_required answered"}
    json: {type: boolean, description: "Output raw JSON"}
output:
  type: object
  description: "new_events (cursor-bounded directed+broadcasts) + unanswered_reply_required (unbounded, both axes)"
write_scope: ["vault/events/.cursor-<party_uid>.json"]
created: 2026-06-11
created_by: talos.director
version: "1.2"
v1_2_note: "Talos T18 2026-06-13 S2.4 refresh. Identity resolution moved to vault/agents/ unified entries. agent_root_uid now read directly from frontmatter rather than inferred from index titles. Aligned with emit-event v1.5."
v1_1_note: "S2.1/S2.2 v1.70 — receipt ledger + set-difference semantics. Per-reader receipt at vault/events/receipts/<uid>.jsonl. new_events = (union) - receipt_set. Cursor retained as scan-start performance hint only; correctness never depends on it."
test_spec: "c831c7a3"
dev_spec: "dabe7c64"
governed_by: 8dd772a0
member_of: ["8dd772a0"]
schema_version: 2
extraction_scope: ship
belt: true
belt_invocation: "python3 vault/tools/2471edc0.py --as <name>"
belt_example: "python3 vault/tools/2471edc0.py --as talos"
---

check-events: ONE identity-resolved gesture (--as <name>).

Returns directed-to-me events UNION crew broadcasts (cursor-bounded, race-free), PLUS
EVERY unanswered reply_required by construction — the unbounded scan runs on BOTH the
party UID and the agent-root UID axes so a reply_required addressed to either axis cannot
slip past the cursor.

Closes the five messaging failure modes from dev-spec dabe7c64:
  #1 broadcasts invisible to --party → union result (directed + tropo.broadcast.crew)
  #2 cursor races the index → cursor advances internally, no --update-cursor needed
  #3 reply_required missed by narrow filter / pre-watermark → unbounded unanswered scan, both axes
  #4 hand-rolled poll loops → --until-answered built in (degrading cadence)
  #5 telemetry drowning messages → messaging-only default (--all adds telemetry)

Shared caller-identity resolver: name → party_uid via unified agent entries at vault/agents/*.md,
case-insensitive exact match on 'agent:' slug. Same contract as emit-on-party-identity (81e52840).
"""

from __future__ import annotations
import argparse, json, re, sqlite3, sys, time
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
JSONL_PATH = VAULT_ROOT / "vault" / "events" / "00-events.jsonl"
SQLITE_PATH = VAULT_ROOT / "vault" / "events" / "00-events-index.sqlite"
CURSOR_DIR = VAULT_ROOT / "vault" / "events"
RECEIPTS_DIR = VAULT_ROOT / "vault" / "events" / "receipts"
AGENTS_DIR = VAULT_ROOT / "vault" / "agents"

MESSAGING_TYPES = frozenset([
    "tropo.message.sent",
    "tropo.message.replied",
    "tropo.message.acked",
    "tropo.broadcast.crew",
])

ANSWERED_TYPES = frozenset([
    "tropo.message.replied",
    "tropo.message.acked",
    "tropo.message.sent",
])


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------

def _cursor_path(party_uid: str) -> Path:
    return CURSOR_DIR / f".cursor-{party_uid}.json"


def load_cursor(party_uid: str) -> str | None:
    try:
        return json.loads(_cursor_path(party_uid).read_text())["last_id"]
    except Exception:
        return None


def save_cursor(party_uid: str, last_id: str) -> None:
    try:
        _cursor_path(party_uid).write_text(json.dumps({"last_id": last_id}))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Receipt ledger — S2.1/S2.2 v1.70 (per-reader, append-only, idempotent)
# ---------------------------------------------------------------------------

def _receipt_path(party_uid: str) -> Path:
    return RECEIPTS_DIR / f"{party_uid}.jsonl"


def load_receipt_set(party_uid: str) -> set[str]:
    path = _receipt_path(party_uid)
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            eid = rec.get("event_id")
            if eid:
                ids.add(str(eid))
        except json.JSONDecodeError:
            continue
    return ids


def append_receipts(party_uid: str, events: list[dict], existing: set[str]) -> None:
    if not events:
        return
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = _receipt_path(party_uid)
    with open(path, "a", encoding="utf-8") as fh:
        for ev in events:
            eid = str(ev.get("id", ""))
            if eid and eid not in existing:
                fh.write(json.dumps({"event_id": eid, "read_at": now_ts, "reader": party_uid}) + "\n")
                existing.add(eid)


# ---------------------------------------------------------------------------
# Identity resolver — shared contract with emit-on-party-identity (81e52840)
# ---------------------------------------------------------------------------

def resolve_identity(agent_name: str) -> tuple[str, str | None]:
    """Resolve agent name → (party_uid, agent_root_uid).

    Iterates unified entries at vault/agents/*.md. Case-insensitive exact
    match on 'agent:' slug. Same contract as emit (81e52840) so
    read and send cannot diverge on caller identity.
    """
    if not AGENTS_DIR.is_dir():
        print(f"ERROR: unified agents directory not found at {AGENTS_DIR}", file=sys.stderr)
        sys.exit(1)

    name_lower = agent_name.strip().lower()
    for p in AGENTS_DIR.glob("*.md"):
        try:
            txt = p.read_text(encoding="utf-8")
            # Find the agent slug
            m_slug = re.search(r"^agent:\s*(.+)$", txt, re.MULTILINE)
            if not m_slug:
                continue
            slug = m_slug.group(1).strip().strip('"').strip("'").lower()
            if slug == name_lower:
                m_party = re.search(r"^party_uid:\s*([0-9a-f]{8})", txt, re.MULTILINE)
                m_root = re.search(r"^agent_root_uid:\s*([0-9a-f]{8})", txt, re.MULTILINE)
                if not m_party:
                    print(f"ERROR: agent '{agent_name}' found in {p.name} but has no party_uid",
                          file=sys.stderr)
                    sys.exit(1)
                party_uid = m_party.group(1)
                agent_root_uid = m_root.group(1) if m_root else None
                return party_uid, agent_root_uid
        except OSError:
            continue

    print(f"ERROR: --as '{agent_name}' resolves to no unified entry in vault/agents/ "
          f"(check spelling; known agents: use --as argus, --as vela, etc.)",
          file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Event queries
# ---------------------------------------------------------------------------

def _query_new_events(since_id: str | None, party_uid: str, agent_root_uid: str | None,
                      include_telemetry: bool) -> list[dict]:
    if SQLITE_PATH.exists():
        return _query_sqlite(since_id, party_uid, agent_root_uid, include_telemetry)
    return _query_jsonl(since_id, party_uid, agent_root_uid, include_telemetry)


def _query_sqlite(since_id: str | None, party_uid: str, agent_root_uid: str | None,
                  include_telemetry: bool) -> list[dict]:
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row

    since_clause = "AND CAST(id AS INTEGER) > CAST(? AS INTEGER)" if since_id else ""
    since_param = [since_id] if since_id else []

    if include_telemetry:
        type_filter = ""
    else:
        type_filter = "AND type IN ({})".format(
            ",".join(f"'{t}'" for t in sorted(MESSAGING_TYPES))
        )

    if agent_root_uid:
        dir_clause = f"(subject = ? OR subject = ?)"
        dir_params = [party_uid, agent_root_uid]
    else:
        dir_clause = "subject = ?"
        dir_params = [party_uid]

    results: list[dict] = []
    seen: set[str] = set()

    def _run(where: str, params: list) -> None:
        sql = f"SELECT raw FROM events WHERE {where} ORDER BY CAST(id AS INTEGER) ASC LIMIT 1000"
        try:
            for row in conn.execute(sql, params).fetchall():
                ev = json.loads(row["raw"])
                eid = ev.get("id", "")
                if eid not in seen:
                    seen.add(eid)
                    results.append(ev)
        except Exception:
            pass

    _run(f"({dir_clause}) {since_clause} {type_filter}", dir_params + since_param)
    _run(f"type = 'tropo.broadcast.crew' {since_clause}", since_param)

    conn.close()
    results.sort(key=lambda x: int(x.get("id", "0")))
    return results


def _query_jsonl(since_id: str | None, party_uid: str, agent_root_uid: str | None,
                 include_telemetry: bool) -> list[dict]:
    results = []
    seen: set[str] = set()
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        eid = ev.get("id", "0")
        if since_id and int(eid) <= int(since_id):
            continue
        etype = ev.get("type", "")
        if not include_telemetry and etype not in MESSAGING_TYPES:
            continue
        subj = ev.get("subject", "")
        is_directed = subj == party_uid or (agent_root_uid and subj == agent_root_uid)
        is_broadcast = etype == "tropo.broadcast.crew"
        if (is_directed or is_broadcast) and eid not in seen:
            seen.add(eid)
            results.append(ev)
    results.sort(key=lambda x: int(x.get("id", "0")))
    return results


# ---------------------------------------------------------------------------
# Unanswered reply_required — UNBOUNDED scan, BOTH axes
# ---------------------------------------------------------------------------

def scan_unanswered_rr(party_uid: str, agent_root_uid: str | None) -> list[dict]:
    all_events = []
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            all_events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    answered_ids: set[str] = set()
    for ev in all_events:
        if ev.get("type") in ANSWERED_TYPES:
            data = ev.get("data", {})
            corr = ev.get("correlationid") or data.get("reply_to_id")
            if corr:
                answered_ids.add(str(corr))

    unanswered = []
    for ev in all_events:
        data = ev.get("data", {})
        if not data.get("reply_required"):
            continue
        subj = ev.get("subject", "")
        if subj != party_uid and not (agent_root_uid and subj == agent_root_uid):
            continue
        eid = str(ev.get("id", ""))
        if eid not in answered_ids:
            unanswered.append(ev)

    return unanswered


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _fmt(ev: dict, prefix: str = "") -> str:
    eid = ev.get("id", "?")
    etype = ev.get("type", "?")
    ts = ev.get("time", "")[:16]
    data = ev.get("data", {})
    from_f = data.get("from") or ev.get("source_uid", "?")
    subj = ev.get("subject", "")
    rr = " [reply_required]" if data.get("reply_required") else ""
    content = data.get("headline") or data.get("subject_text") or str(data.get("body", ""))[:120]
    return (f"{prefix}[{eid}] {ts} {etype} from={from_f} subj={subj}{rr}\n"
            f"{prefix}  {content[:120]}")


def _triage_unanswered(unanswered: list[dict], agent_name: str, model: str | None = None) -> str:
    import sys
    from pathlib import Path
    _lib = Path(__file__).resolve().parent / "lib"
    if str(_lib) not in sys.path:
        sys.path.insert(0, str(_lib))

    try:
        from llm import call, model_for
    except ImportError as exc:
        return f"[triage unavailable — lib/llm.py not found: {exc}]"

    lines = []
    for ev in unanswered:
        data = ev.get("data", {})
        headline = (
            data.get("headline") or data.get("subject_text") or
            str(data.get("body", ""))[:100]
        )
        lines.append(
            f"[{ev.get('id','?')}] {ev.get('time','')[:10]} "
            f"from={data.get('from', ev.get('source_uid','?'))} "
            f"| {headline[:120]}"
        )

    resolved = model or model_for("triage")
    prompt = (
        f"You are triaging unanswered reply_required events for agent '{agent_name}'.\n\n"
        f"Classify each event as:\n"
        f"  REPLY — needs a response this session\n"
        f"  DEBT  — pre-discipline correlation debt; operationally handled; no reply owed\n\n"
        f"Output format:\n"
        f"  • 3–5 bullet summary of what you see\n"
        f"  • If any REPLY items exist, list them: [id] one-line reason\n"
        f"  • If all are DEBT, say so in one line\n\n"
        f"Events ({len(unanswered)} total):\n" + "\n".join(lines)
    )

    try:
        return call(
            task="triage",
            messages=[{"role": "user", "content": prompt}],
            model=resolved,
            max_tokens=512,
        )
    except RuntimeError as exc:
        if "NO_API_KEY" in str(exc):
            return (
                "[triage unavailable — ANTHROPIC_API_KEY not set in this environment]\n"
                "Fallback: read the list above and classify each item manually as\n"
                "  REPLY (needs action this session) or DEBT (pre-discipline, no reply owed)."
            )
        return f"[triage error: {exc} — read the list above manually]"


def _print_result(agent_name: str, party_uid: str, agent_root_uid: str | None,
                  new_events: list[dict], unanswered: list[dict],
                  triage: bool = False, triage_model: str | None = None) -> None:
    root_tag = f", root={agent_root_uid}" if agent_root_uid else ""
    print(f"=== check-events for {agent_name} (party={party_uid}{root_tag}) ===\n")
    if not new_events and not unanswered:
        print("✓ Inbox clear. No new events; no unanswered reply_required.")
        return
    if new_events:
        print(f"NEW EVENTS ({len(new_events)}):")
        for ev in new_events:
            print(_fmt(ev, prefix="  "))
        print()
    if unanswered:
        print(f"UNANSWERED reply_required ({len(unanswered)}) — unbounded scan, both axes:")
        for ev in unanswered:
            print(_fmt(ev, prefix="  ⚠ "))
        print()
        if triage:
            print("--- TRIAGE ---")
            print(_triage_unanswered(unanswered, agent_name, model=triage_model))
            print()


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

def run_once(agent_name: str, party_uid: str, agent_root_uid: str | None,
             include_telemetry: bool, json_output: bool,
             triage: bool = False, triage_model: str | None = None,
             filter_type: str | None = None, filter_id: str | None = None) -> int:
    receipt_set = load_receipt_set(party_uid)
    since_id = load_cursor(party_uid)
    candidate_events = _query_new_events(since_id, party_uid, agent_root_uid, include_telemetry)
    new_events = [ev for ev in candidate_events if str(ev.get("id", "")) not in receipt_set]
    append_receipts(party_uid, new_events, receipt_set)

    if candidate_events:
        newest_id = max(ev.get("id", "0") for ev in candidate_events)
        save_cursor(party_uid, newest_id)

    if filter_type:
        new_events = [ev for ev in new_events if ev.get("type") == filter_type]
    if filter_id:
        new_events = [ev for ev in new_events if ev.get("id") == filter_id]

    unanswered = scan_unanswered_rr(party_uid, agent_root_uid)

    if json_output:
        print(json.dumps({
            "agent": agent_name,
            "party_uid": party_uid,
            "agent_root_uid": agent_root_uid,
            "new_events": new_events,
            "unanswered_reply_required": unanswered,
        }, indent=2, ensure_ascii=False))
        return 0

    _print_result(agent_name, party_uid, agent_root_uid, new_events, unanswered,
                  triage=triage, triage_model=triage_model)
    return 0


def run_until_answered(agent_name: str, party_uid: str, agent_root_uid: str | None,
                       include_telemetry: bool, json_output: bool) -> int:
    cadence = [15, 15, 15, 15, 30, 30, 60, 60, 120]
    attempt = 0
    while True:
        receipt_set = load_receipt_set(party_uid)
        since_id = load_cursor(party_uid)
        candidate_events = _query_new_events(since_id, party_uid, agent_root_uid, include_telemetry)
        new_events = [ev for ev in candidate_events if str(ev.get("id", "")) not in receipt_set]
        append_receipts(party_uid, new_events, receipt_set)
        if candidate_events:
            newest_id = max(ev.get("id", "0") for ev in candidate_events)
            save_cursor(party_uid, newest_id)

        unanswered = scan_unanswered_rr(party_uid, agent_root_uid)

        if not unanswered:
            if json_output:
                print(json.dumps({"status": "answered", "new_events": new_events}))
            else:
                print("✓ All reply_required answered.")
            return 0

        if not json_output:
            print(f"[poll {attempt + 1}] {len(unanswered)} unanswered — "
                  f"{new_events and len(new_events) or 0} new events:")
            _print_result(agent_name, party_uid, agent_root_uid, new_events, unanswered)

        delay = cadence[min(attempt, len(cadence) - 1)]
        time.sleep(delay)
        attempt += 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _sanitize_id(id_str: str) -> str:
    return id_str.zfill(8) if id_str.isdigit() else id_str

def main() -> int:
    p = argparse.ArgumentParser(
        description="check-events — identity-resolved event drain (directed + broadcasts; cannot miss a reply_required)"
    )
    p.add_argument("--as", dest="as_name", required=True,
                   help="Caller agent name (resolves party_uid from unified entry; no UID argument needed)")
    p.add_argument("--all", action="store_true",
                   help="Include telemetry/substrate events (default: messaging-only)")
    p.add_argument("--raw", action="store_true",
                   help="Same as --all")
    p.add_argument("--until-answered", action="store_true", dest="until_answered",
                   help="Poll with degrading cadence until all reply_required are answered")
    p.add_argument("--json", action="store_true", dest="json_output",
                   help="Output raw JSON")
    p.add_argument("--triage", action="store_true",
                   help="After listing unanswered events, call the LLM to classify...")
    p.add_argument("--triage-model", dest="triage_model", default=None)
    p.add_argument("--type", dest="filter_type")
    p.add_argument("--id", dest="filter_id")
    p.add_argument("--party", dest="party_override")
    args = p.parse_args()

    include_telemetry = args.all or args.raw

    party_uid, agent_root_uid = resolve_identity(args.as_name)

    if args.until_answered:
        return run_until_answered(args.as_name, party_uid, agent_root_uid,
                                  include_telemetry, args.json_output)

    fid = _sanitize_id(args.filter_id) if args.filter_id else None
    puid = args.party_override if args.party_override else party_uid

    return run_once(args.as_name, puid, agent_root_uid,
                    include_telemetry, args.json_output,
                    triage=args.triage, triage_model=args.triage_model,
                    filter_type=args.filter_type, filter_id=fid)


if __name__ == "__main__":
    sys.exit(main())
