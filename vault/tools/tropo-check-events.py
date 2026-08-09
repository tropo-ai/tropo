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
cli_command: "python3 vault/tools/tropo-check-events.py --as <name>"
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
write_scope: ["vault/events/.cursor-<party_uid>.json", "vault/events/receipts/<party_uid>.jsonl"]
created: 2026-06-11
created_by: talos.director
modified: 2026-07-31
modified_by: vela-v71
version: "1.7"
v1_7_note: "1f29bcfb Case 5, found by Talos T37, fixed by vela-v71 with Talos's explicit owner consent ('YES ON CASE 5. Take it.'). An instrument whose entire job is reporting whether you were answered was reporting 'no answer' while a correlated reply sat correct and pushed on main. Two causes, both closed: (1) a reply lacking final:true was discarded BEFORE the correlation lookup and never mentioned again; (2) only correlationid was read, though the emit tool accepts --causationid on the same command line, so a reply correlated that way was invisible. Metis G98 spent hours reporting zero confirmations from nine directives and drew a conclusion about the crew from a silence that was partly manufactured by this code. THE STRICTNESS IS UNCHANGED AND DELIBERATELY SO — terminal-reply semantics are defensible and only final:true closes a thread. What changed is the SILENCE: a discarded reply is now reported as '1 correlated reply seen, NOT terminal (<reason>)' naming what was discarded AND why on one line, so the asker knows to go read it and the sender learns what was missing. causationid is now accepted as a correlation source alongside correlationid and reply_to_id. The frozen numeric epoch keeps its historical rule (no event_uid: any correlated answer was terminal). Per Rule 1b: an instrument that discards an input must say so."
v1_6_note: "Captain-mode edit (talos-owned tool; Talos notified per the A95/A106 captain-edit precedent), Mike-directed 'I want it fixed permanently' 2026-07-31. Closes the trigger gap left by v1.9: the self-heal existed only on the WRITE path, so it could only fire when something emitted. On a multi-agent day the dominant divergence source is `git merge` — another agent's stream lands in the canonical union with NO local emit — so nothing triggered the heal and every read warned until a human ran tropo-rebuild-events-sqlite.py by hand. Observed live 2026-07-31: the projection diverged three times in 40 minutes purely from integrating crew pushes. THE FIX MOVES THE TRIGGER FROM A COMMAND TO A CONDITION: event_identity.ensure_sqlite_projection() pairs detection with repair in one shared gesture, and emit / check-events / query-events all call it, so ANY touch of the log repairs a divergence regardless of what caused it — merge, fresh clone, manual copy, or emit. Safety posture is unchanged and deliberately so: still only the sanctioned full rebuild (never an incremental patch), still cooldown-gated at 300s via a marker now SHARED across all callers so concurrent agents cannot storm it, plus a subprocess-env recursion guard (TROPO_SQLITE_AUTOHEAL_ACTIVE) and an operator escape hatch (TROPO_NO_SQLITE_AUTOHEAL) for a provably side-effect-free read. Delivery semantics are untouched: the canonical JSONL union is loaded before any repair and remains the sole delivery truth, so a heal can speed up later reads but can never change what a drain delivers. Regression-pinned by test_divergent_projection_self_heals_on_read (merge shape, read-only) and test_autoheal_is_cooldown_gated_and_never_recurses. In this tool specifically, the v1.5 projection gate was explicitly diagnostic-only — it could SEE a divergence it had no way to fix. It now heals. The v1.5 delivery guarantee is preserved verbatim: the union is read before the repair and is what the drain returns."
v1_5_note: "Projection trust hardening: cursor/drain delivery always uses the canonical legacy-plus-stream union; event_identity's shared exact identity-coverage gate is diagnostic-only and warns for an existing incomplete, divergent, or unreadable SQLite projection without changing receipt, cursor, or unanswered-thread semantics."
v1_4_note: "Correctness hardening: the canonical append-only event union is always authoritative for delivery, so a stale SQLite projection cannot hide a newly merged message. --id/--type filters now apply before receipt writes and cannot silently mark unrelated unread messages as read."
v1_3_note: "Distributed Event Ledger dual-read under f15a9b85: receipts use immutable event_uid for new events while accepting legacy numeric IDs; cursor stores derived display sequence only; unanswered scan unions legacy epoch + per-writer streams and resolves both correlation forms."
v1_2_note: "Talos T18 2026-06-13 S2.4 refresh. Identity resolution moved to vault/agents/ unified entries. agent_root_uid now read directly from frontmatter rather than inferred from index titles. Aligned with emit-event v1.5."
v1_1_note: "S2.1/S2.2 v1.70 — receipt ledger + set-difference semantics. Per-reader receipt at vault/events/receipts/<uid>.jsonl. new_events = (union) - receipt_set. Cursor retained as scan-start performance hint only; correctness never depends on it."
test_spec: "c831c7a3"
dev_spec: "dabe7c64"
governed_by: 8dd772a0
member_of: ["8dd772a0"]
schema_version: 2
extraction_scope: ship
belt: true
belt_invocation: "python3 vault/tools/tropo-check-events.py --as <name>"
belt_example: "python3 vault/tools/tropo-check-events.py --as talos"
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

from lib import event_identity

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


def _event_key(event: dict) -> str:
    return event_identity.immutable_event_uid(event)


def _display_seq(event: dict) -> int:
    raw = event.get("_display_seq", event.get("display_seq"))
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    event_id = str(event.get("id", ""))
    return int(event_id) if event_id.isdigit() else 0


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
                value = str(eid)
                ids.add(value)
                if value.isdigit():
                    ids.add(f"legacy_{value.zfill(8)}")
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
            eid = _event_key(ev)
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

def _canonical_event_union_with_projection_warning() -> list[dict]:
    """Load delivery truth, and repair the derived projection if it diverged.

    v1.6: this was diagnostic-only, which left the read path able to SEE a
    divergence it could not fix. On a multi-agent day the divergence source is
    `git merge` — new canonical events arrive with no local emit — so the
    emit-time heal never fired and the warning repeated on every read until a
    human intervened. Detection now heals, via the shared cooldown-gated
    rebuild in event_identity.

    Delivery semantics are unchanged and deliberately so: the canonical union
    below is loaded BEFORE any repair and is what gets returned. Receipt,
    cursor, and unanswered-thread behaviour never depend on the cache, so a
    heal can speed up later reads but can never alter what this drain delivers.
    """
    event_union = event_identity.load_event_union(VAULT_ROOT)
    if not SQLITE_PATH.exists():
        return event_union
    event_identity.ensure_sqlite_projection(
        VAULT_ROOT,
        event_union,
        sqlite_path=SQLITE_PATH,
        context="check-events drain",
    )
    return event_union


def _query_new_events(since_id: str | None, party_uid: str, agent_root_uid: str | None,
                      include_telemetry: bool,
                      event_union: list[dict] | None = None) -> list[dict]:
    # Receipt-set difference—not cursor position or cache freshness—is the
    # delivery contract. SQLite coverage is only a diagnostic snapshot: a
    # stream can merge after that check and before any subsequent cache read.
    # Therefore even a complete projection can never become delivery truth.
    if event_union is None:
        event_union = _canonical_event_union_with_projection_warning()
    return _query_jsonl(
        since_id,
        party_uid,
        agent_root_uid,
        include_telemetry,
        event_union=event_union,
    )


def _query_sqlite(since_id: str | None, party_uid: str, agent_root_uid: str | None,
                  include_telemetry: bool) -> list[dict]:
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row

    columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    has_v2 = "display_seq" in columns and "event_uid" in columns
    since_column = "display_seq" if has_v2 else "CAST(id AS INTEGER)"
    since_clause = f"AND {since_column} > CAST(? AS INTEGER)" if since_id else ""
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
        selected = "raw, display_seq, event_uid" if has_v2 else "raw"
        order = "display_seq" if has_v2 else "CAST(id AS INTEGER)"
        sql = f"SELECT {selected} FROM events WHERE {where} ORDER BY {order} ASC LIMIT 1000"
        try:
            for row in conn.execute(sql, params).fetchall():
                ev = json.loads(row["raw"])
                if has_v2:
                    ev.setdefault("event_uid", row["event_uid"])
                    ev["_display_seq"] = row["display_seq"]
                eid = _event_key(ev)
                if eid not in seen:
                    seen.add(eid)
                    results.append(ev)
        except Exception:
            pass

    _run(f"({dir_clause}) {since_clause} {type_filter}", dir_params + since_param)
    _run(f"type = 'tropo.broadcast.crew' {since_clause}", since_param)

    conn.close()
    results.sort(key=_display_seq)
    return results


def _query_jsonl(since_id: str | None, party_uid: str, agent_root_uid: str | None,
                 include_telemetry: bool,
                 event_union: list[dict] | None = None) -> list[dict]:
    results = []
    seen: set[str] = set()
    if event_union is None:
        event_union = event_identity.load_event_union(VAULT_ROOT)
    ordered = event_identity.derive_display_order(
        event_union
    )
    for display_seq, ev in ordered:
        ev["_display_seq"] = display_seq
        eid = _event_key(ev)
        if since_id and display_seq <= int(since_id):
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
    results.sort(key=_display_seq)
    return results


# ---------------------------------------------------------------------------
# Unanswered reply_required — UNBOUNDED scan, BOTH axes
# ---------------------------------------------------------------------------

def scan_unanswered_rr(
    party_uid: str,
    agent_root_uid: str | None,
    event_union: list[dict] | None = None,
) -> list[dict]:
    if event_union is None:
        event_union = event_identity.load_event_union(VAULT_ROOT)
    ordered = event_identity.derive_display_order(
        event_union
    )
    all_events = []
    for display_seq, event in ordered:
        event["_display_seq"] = display_seq
        all_events.append(event)

    answered_ids: set[str] = set()
    # v1.7 (Case 5): a discarded reply is now RECORDED rather than dropped in
    # silence. Strictness is unchanged — only final:true closes a thread — but
    # a correlated reply that failed the terminal test is kept here so the
    # report can say what exists and what is missing from it.
    discarded: dict[str, list[tuple[dict, str]]] = {}
    for ev in all_events:
        if ev.get("type") in ANSWERED_TYPES:
            data = ev.get("data", {})
            if not isinstance(data, dict):
                continue
            # v1.7: causationid is accepted as a correlation source. The emit
            # tool takes --correlationid and --causationid on the same command
            # line; reading only the first made a well-formed reply invisible
            # with no signal to either side.
            corr = (
                ev.get("correlationid")
                or ev.get("causationid")
                or data.get("reply_to_id")
            )
            if (
                ev.get("type") == "tropo.message.replied"
                and data.get("final") is True
                and not event_identity.terminal_reply_has_renderable_content(
                    VAULT_ROOT,
                    data,
                )
            ):
                if corr:
                    discarded.setdefault(str(corr), []).append(
                        (ev, "no renderable body/body_file")
                    )
                continue
            if ev.get("event_uid") and data.get("final") is not True:
                # The frozen numeric epoch retains its historical rule: any
                # correlated answer was terminal, even when final:false was
                # present. Every distributed-stream reply requires explicit
                # final:true.
                if corr:
                    reason = (
                        "final:false" if data.get("final") is False
                        else "no final: flag"
                    )
                    if not ev.get("correlationid") and (
                        ev.get("causationid") or data.get("reply_to_id")
                    ):
                        reason += ", correlated via causationid"
                    discarded.setdefault(str(corr), []).append((ev, reason))
                continue
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
        identities = {_event_key(ev), str(ev.get("id", ""))}
        if identities.isdisjoint(answered_ids):
            # Attach any correlated-but-non-terminal replies so the caller can
            # report "seen, not terminal" instead of a bare, misleading zero.
            near = []
            for identity in identities:
                near.extend(discarded.get(identity, []))
            if near:
                ev["_nonterminal_replies"] = near
            unanswered.append(ev)

    return unanswered


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _fmt(ev: dict, prefix: str = "") -> str:
    eid = ev.get("event_uid") or ev.get("id", "?")
    display = _display_seq(ev)
    display_label = f"#{display} " if display else ""
    etype = ev.get("type", "?")
    ts = ev.get("time", "")[:16]
    data = ev.get("data", {})
    from_f = data.get("from") or ev.get("source_uid", "?")
    subj = ev.get("subject", "")
    rr = " [reply_required]" if data.get("reply_required") else ""
    content = data.get("headline") or data.get("subject_text") or str(data.get("body", ""))[:120]
    return (f"{prefix}{display_label}[{eid}] {ts} {etype} from={from_f} subj={subj}{rr}\n"
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
            # v1.7 (Case 5): never report a bare zero when a correlated reply
            # exists. Say what was seen AND what is missing from it, on one
            # line, so the asker knows to go read it and the sender learns why
            # their reply did not count.
            for reply, reason in ev.get("_nonterminal_replies", []):
                rid = reply.get("event_uid") or reply.get("id", "?")
                sender = (reply.get("data", {}) or {}).get("from") \
                    or reply.get("source_uid", "?")
                when = reply.get("time", "")[:16]
                print(
                    f"      ↳ 1 correlated reply seen, NOT terminal "
                    f"({reason}) — [{rid}] {when} from={sender}. "
                    f"The thread stays open, but it was answered: read it."
                )
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
    event_union = _canonical_event_union_with_projection_warning()
    # Correctness is receipt-set difference, never cursor position. A newly
    # merged stream event may derive a display_seq behind the reader's prior
    # cursor; querying only "after cursor" would hide it forever (Talos T32
    # AC8 break). Cursor remains an output/performance hint for future indexed
    # optimization, not a filter on the authoritative scan.
    candidate_events = _query_new_events(
        None,
        party_uid,
        agent_root_uid,
        include_telemetry,
        event_union=event_union,
    )
    new_events = [ev for ev in candidate_events if _event_key(ev) not in receipt_set]

    if candidate_events:
        save_cursor(party_uid, str(max(_display_seq(ev) for ev in candidate_events)))

    if filter_type:
        new_events = [ev for ev in new_events if ev.get("type") == filter_type]
    if filter_id:
        new_events = [
            ev for ev in new_events
            if ev.get("id") == filter_id or _event_key(ev) == filter_id
        ]
    # Targeted drains must not acknowledge unrelated unseen messages. Filters
    # narrow both output and durable receipt writes; the cursor is only a hint,
    # so unreceipted messages remain discoverable on the next full scan.
    append_receipts(party_uid, new_events, receipt_set)

    unanswered = scan_unanswered_rr(
        party_uid,
        agent_root_uid,
        event_union=event_union,
    )

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
        event_union = _canonical_event_union_with_projection_warning()
        candidate_events = _query_new_events(
            None,
            party_uid,
            agent_root_uid,
            include_telemetry,
            event_union=event_union,
        )
        new_events = [ev for ev in candidate_events if _event_key(ev) not in receipt_set]
        append_receipts(party_uid, new_events, receipt_set)
        if candidate_events:
            save_cursor(party_uid, str(max(_display_seq(ev) for ev in candidate_events)))

        unanswered = scan_unanswered_rr(
            party_uid,
            agent_root_uid,
            event_union=event_union,
        )

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
