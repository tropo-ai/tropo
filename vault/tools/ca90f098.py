#!/usr/bin/env python3
"""
---
uid: ca90f098
type: tool
name: emit-event
trigger_description: "Emit a CloudEvent (message/broadcast/completion). Resolves party identity."
title: "emit-event — Canonical Event Emission Primitive"
status: active
owner: talos
domain: Canonical event emission
transport: cli
cli_command: "python3 vault/tools/ca90f098.py"
implementation_kind: python-script
spawnable_by:
  - talos
  - argus
  - vela
  - orpheus
  - metis
  - cosmo
input:
  type: object
  required: [type, source, source_uid, lifecycle]
  properties:
    type: {type: string, description: "Event type (e.g. tropo.message.sent)"}
    source: {type: string, description: "URI-shaped source identifier"}
    source_uid: {type: string, description: "8-hex UID of emitting agent/tool/principal"}
    lifecycle: {type: string, enum: [evergreen, ephemeral], description: "Query-filter semantics per events.capsule v1.1 §2: evergreen (preserve indefinitely; in default projections) | ephemeral (excluded from default projections; retained in log for audit). NOT cycle-phase."}
    subject: {type: string, description: "Subject of the event (optional)"}
    data: {type: object, description: "Polymorphic payload per event type schema"}
    correlationid: {type: string, description: "Correlation chain ID for request/reply patterns"}
output:
  type: object
  properties:
    id: {type: string, description: "Sequential event ID (8-digit zero-padded)"}
    ts: {type: string, description: "ISO 8601 emission timestamp"}
write_scope: [vault/events/]
created: 2026-05-26
created_by: talos-t10
modified: 2026-06-13
modified_by: talos-t18
version: "1.5"
v1_5_note: "Talos T18 2026-06-13 S2.4 refresh. Identity resolution moved from agent-registry.yaml to vault/agents/ unified entries. Implemented --final/--not-final enforcement for reply_required replies (spec 2fe61817). Registry parse logic simplified to use the new unified substrate."
v1_4_note: "Talos T16 2026-06-13 per spec 81e52840 (emit-on-party-identity, S2.4 v1.70 queue). Adds --as <name> identity resolver: agent sources (/agents/ or //) MUST use --as to resolve their party_uid from the registry; --source-uid is FORBIDDEN for agent sources so no raw-UID emit path survives by construction. Non-agent sources (tool/script) continue to require --source-uid as before. Optional TROPO_AGENT env var provides default for --as. Registry parse is stdlib-only (_parse_registry_minimal, no yaml dep); registry-unreadable fails hard for agent sources (no fallback raw-UID path — spec 81e52840 forbids it). _resolve_identity_by_name shares the same resolver contract as check-events (2471edc0) so read and send cannot diverge on caller identity."
v1_3_note: "Argus A106 2026-06-09 captain-mode per Mike-A106 directive 'ZERO ambiguity over agent IDs — agent-root vs party' (talos-owned tool; Talos notified per the A95 captain-edit precedent). Adds the ADDRESS-SIDE IDENTITY GUARD (_guard_subject_axis): a DIRECTED message (tropo.message.sent/replied/acked) is now rejected if its `subject` is not a registered PARTY UID — i.e. the recipient addressed on their agent-root (lineage axis) instead of their party (messaging axis). This is the symmetric completion of the v1.2 send-side guard: v1.2 + v1.63 Immutable Identity enforced only that an agent emits FROM its party UID (source_uid); nothing enforced that a message is addressed TO a party UID (subject). The gap let Metis's event 2688 (a reply_required design-review) reach Argus's agent-root 6dff0111 and go unseen — A105 retired blind to it; A106's party-only boot drain missed it; Mike caught it manually. NOTE: this enforces the SUBJECT clause of events.capsule Rule 4 (which ALREADY forbids the agent-root as a live agent's source_uid / subject / recipients / --party) — it was never a contract gap, only an enforcement gap (v1.4 Check 22 + the v1.2 tool guard covered source_uid; subject was unguarded). Broadcasts (no specific recipient), tool/non-agent sources, missing subjects, and non-message types pass untouched; fails OPEN if the registry is unreadable. Tested 8/8 (2688 repro rejected; valid party-UID addressing + broadcast + None-subject + non-message all pass; full emit() rejects before write). events.capsule v1_6 amendment-note records the enforcement completion; validator subject-axis detection (Check 23) is the defense-in-depth follow-up."
v1_2_note: "Argus A95 2026-06-03 captain-mode per Mike-A95 'fix the root cause' directive (talos-owned tool; Talos notified per A93 captain-edit precedent). Adds the SEND-SIDE IDENTITY GUARD: emit() now rejects an AGENT messaging/broadcast emit (tropo.message.* / tropo.broadcast.crew from an /agents/ or // source) whose source_uid is not a registered PARTY UID — i.e. the agent-root / wrong-axis emit (the Talos-invisible-queue, ~205 historical instances at 05ab4861). Party UIDs resolve from the registry party_uid column (A94 Registry Step 3); fails OPEN if the registry is unreadable (never blocks on infra error). Tool emits (source /tools/...) + non-messaging types are unaffected. Operational half of the root-cause fix: prevention at the tool (here) + detection at the validator (events.capsule v1.4 Check 22) + corrected contract (events.capsule v1.4 Rule 4)."
v1_1_note: "Argus A93 2026-06-02 (Mike-A93 directive): added the wake-loop reminder. On a reply_required message to another agent, emit-event now prints a stderr REMINDER suggesting the sender consider a bounded self-wake loop (poll + ~60s + up-to-N + exit-on-arrival). It is a suggestion only — the agent decides whether they are actually blocked-waiting; the wake is harness-bound, so the substrate reminds but does not arm. Closes the recurring gap (agents forget to think about it, per Mike). Captain-mode edit on a talos-owned tool; Talos notified for review."
governed_by: d5e1b4a3
member_of: ["8dd772a0"]
schema_version: 2
extraction_scope: ship
belt: true
belt_invocation: "python3 vault/tools/ca90f098.py --as <name> ..."
belt_example: "python3 vault/tools/ca90f098.py --type tropo.message.sent --as talos --lifecycle ephemeral --subject <party_uid> --data '{\"body\": \"...\"}'"
---

Atomic emit-event primitive for vault/events/00-events.jsonl.
CloudEvents v1.0 envelope. fcntl.flock exclusive lock prevents concurrent corruption.
Dual-write: JSONL canonical + SQLite WAL derived. Exit 0 on success; non-zero on error.

Usage (agent source — --as resolves party_uid from unified entries):
  python3 vault/tools/ca90f098.py \\
    --type tropo.message.sent \\
    --source /agents/talos \\
    --as talos \\
    --lifecycle evergreen \\
    [--subject <party_uid>] \\
    [--data '{"body": "..."}'] \\
    [--correlationid <id>] \\
    [--final | --not-final]

Usage (non-agent source — --source-uid required):
  python3 vault/tools/ca90f098.py \\
    --type tropo.substrate.created \\
    --source /tools/archive \\
    --source-uid 6cc9dcdb \\
    --lifecycle evergreen
"""

from __future__ import annotations
import argparse, fcntl, json, os, re, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
EVENTS_DIR = VAULT_ROOT / "vault" / "events"
JSONL_PATH = EVENTS_DIR / "00-events.jsonl"
SQLITE_PATH = EVENTS_DIR / "00-events-index.sqlite"
AGENTS_DIR = VAULT_ROOT / "vault" / "agents"

REGISTERED_TYPES = {
    # Five Primitive Event Types (per events.capsule v1.1 §3)
    "tropo.message.sent", "tropo.message.acked", "tropo.message.replied",
    "tropo.cycle.opened", "tropo.cycle.closed",
    # Substrate-Write Auto-Emission Family (per events.capsule v1.1 §3; Stream C target shape)
    "tropo.substrate.created", "tropo.substrate.modified",
    "tropo.substrate.recycled", "tropo.substrate.inboxed",
    # Validator run completion (per events.capsule v1.1 §3)
    "tropo.validator.run.completed",
    # Pipeline lifecycle family (v1.58 C.4-C.5)
    "tropo.pipeline.activated", "tropo.pipeline.bootstrapped",
    "tropo.pipeline.step_completed", "tropo.pipeline.closed",
    # Release lifecycle (v1.58 C.6)
    "tropo.release.shipped",
    # Cycle Coordination Family (v1.59 Lane A events.capsule v1.2 §3)
    "tropo.cycle.activated", "tropo.cycle.ship_gate_progress",
    # v1.61 Lane EC events.capsule v1.3 additions
    "tropo.broadcast.crew", "tropo.substrate.archived",
    # Agent Lifecycle Family (events.capsule §3; auto-emitted by write-activation-entry.py)
    "tropo.agent.activated", "tropo.agent.retired",
}

VALID_LIFECYCLE = {"evergreen", "ephemeral"}  # per events.capsule v1.1 §2 (query-filter semantics; NOT cycle-phase)
_MESSAGING_TYPES = {"tropo.message.sent", "tropo.message.replied",
                    "tropo.message.acked", "tropo.broadcast.crew"}
_DIRECTED_MESSAGE_TYPES = {"tropo.message.sent", "tropo.message.replied",
                           "tropo.message.acked"}


def _registered_party_uids() -> set[str] | None:
    """Party UIDs (messaging axis) from the unified agent entries at vault/agents/.
    Returns None if the directory is unreadable or empty — the guard then FAILS OPEN.
    Stdlib-only regex parse (no frontmatter/yaml dependency)."""
    if not AGENTS_DIR.is_dir():
        return None
    uids = set()
    for p in AGENTS_DIR.glob("*.md"):
        try:
            txt = p.read_text(encoding="utf-8")
            # Unified entries carry party_uid: <8-hex>
            m = re.search(r"^party_uid:\s*([0-9a-f]{8})", txt, re.MULTILINE)
            if m:
                uids.add(m.group(1))
        except OSError:
            continue
    return uids if uids else None


def _resolve_identity_by_name(agent_name: str) -> str:
    """Resolve agent name → party_uid for --as <name>.

    Iterates unified entries at vault/agents/*.md. Case-insensitive exact
    match on 'agent:' slug. Same contract as check-events (2471edc0)
    resolver so read and send cannot diverge on caller identity.
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
                if not m_party:
                    print(f"ERROR: agent '{agent_name}' found in {p.name} but has no party_uid",
                          file=sys.stderr)
                    sys.exit(1)
                return m_party.group(1)
        except OSError:
            continue

    print(f"ERROR: --as '{agent_name}' resolves to no unified entry in vault/agents/ "
          f"(check spelling; e.g. --as argus, --as vela, --as talos)",
          file=sys.stderr)
    sys.exit(1)


def _is_reply_required_task(correlationid: str) -> bool:
    """Check if the correlationid refers to a reply_required:true request.
    Queries the derived SQLite index. Returns False if unknown or not required."""
    if not SQLITE_PATH.exists():
        return False
    try:
        conn = sqlite3.connect(str(SQLITE_PATH))
        # Case-insensitive event ID check
        res = conn.execute("SELECT data FROM events WHERE id = ?", (correlationid.zfill(8),)).fetchone()
        conn.close()
        if res and res[0]:
            data = json.loads(res[0])
            return data.get("reply_required") is True
    except Exception:
        pass
    return False


def _guard_party_axis(event_type: str, source: str, source_uid: str) -> None:
    """Reject an AGENT messaging/broadcast emit whose source_uid is not a registered PARTY UID —
    the agent-root / wrong-axis emit (the Talos-invisible-queue). Per events.capsule v1.4 Rule 4.
    Tool-emitted events (source /tools/...) and non-messaging types pass untouched; fails open if
    the registry is unreadable."""
    if event_type not in _MESSAGING_TYPES:
        return
    if not (source.startswith("/agents/") or source.startswith("//")):
        return  # tool / non-agent source — not guarded
    party = _registered_party_uids()
    if not party:
        return  # registry unreadable/empty — fail open
    if source_uid not in party:
        raise ValueError(
            f"wrong identity axis: source_uid {source_uid!r} is not a registered PARTY UID. "
            f"Agents emit messaging/broadcast events from their PARTY UID (messaging axis), NOT "
            f"their agent-root (lineage axis) — per events.capsule v1.4 Rule 4. "
            f"Registered party UIDs: {sorted(party)}."
        )


def _guard_subject_axis(event_type: str, subject: str | None) -> None:
    """Reject a DIRECTED message addressed to a non-party UID — the address-side counterpart
    to _guard_party_axis (which guards the SEND axis, source_uid). A directed message
    (tropo.message.sent/replied/acked) MUST address the recipient's PARTY UID (messaging axis),
    never their agent-root (lineage axis). Closes the gap that let event 2688 reach Argus's
    agent-root 6dff0111 and go unseen at boot: v1.63 Immutable Identity guarded only source_uid,
    so a sender emitting correctly AS itself could still address the recipient on the WRONG axis.
    Fails OPEN if the registry is unreadable; broadcasts + missing subject pass. Enforces the
    SUBJECT clause of events.capsule Rule 4 (which already forbids the agent-root as a live agent's
    subject; v1.4 enforced only the source_uid clause). Argus A106 2026-06-09."""
    if event_type not in _DIRECTED_MESSAGE_TYPES:
        return
    if not subject:
        return  # no recipient to validate — don't block (subject-presence is a separate concern)
    party = _registered_party_uids()
    if not party:
        return  # registry unreadable/empty — fail open (never block on an infra error)
    if subject not in party:
        raise ValueError(
            f"wrong identity axis: subject {subject!r} is not a registered PARTY UID. "
            f"Directed messages ({', '.join(sorted(_DIRECTED_MESSAGE_TYPES))}) must address the "
            f"recipient's PARTY UID (messaging axis), NOT their agent-root (lineage axis) — the "
            f"address-side counterpart to the send-side guard, per events.capsule Rule 4 (subject clause). "
            f"Registered party UIDs: {sorted(party)}."
        )


def _next_id(jsonl_lines: list[str]) -> str:
    """Sequential numeric ID — scan existing events for highest id."""
    max_id = 0
    for line in jsonl_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            ev = json.loads(line)
            n = int(ev.get("id", "0"))
            if n > max_id:
                max_id = n
        except (json.JSONDecodeError, ValueError):
            pass
    return f"{max_id + 1:08d}"


def _ensure_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            specversion TEXT NOT NULL,
            type TEXT NOT NULL,
            source TEXT NOT NULL,
            time TEXT NOT NULL,
            subject TEXT,
            source_uid TEXT NOT NULL,
            lifecycle TEXT NOT NULL,
            correlationid TEXT,
            data TEXT,
            raw TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON events(type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source_uid ON events(source_uid)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_correlationid ON events(correlationid)")
    conn.commit()


def emit(event_type: str, source: str, source_uid: str, lifecycle: str,
         subject: str | None = None, data: dict | None = None,
         correlationid: str | None = None, strict: bool = False) -> dict:
    """Emit one event atomically. Returns the emitted event dict.

    strict=True (R3 v1.59 Lane C): raises ValueError on unregistered event type
    instead of printing WARN. Default WARN at v1.59; ratchet to default-strict at v1.60+.
    """
    if event_type not in REGISTERED_TYPES:
        msg = f"unregistered event type {event_type!r} (not in events.capsule v1.1 §3)"
        if strict:
            raise ValueError(msg)
        print(f"WARN: {msg}", file=sys.stderr)
    if lifecycle not in VALID_LIFECYCLE:
        raise ValueError(f"lifecycle must be one of {sorted(VALID_LIFECYCLE)}")
    if not re.fullmatch(r"[0-9a-f]{8}", source_uid):
        raise ValueError(f"source_uid must be 8-hex; got {source_uid!r}")
    _guard_party_axis(event_type, source, source_uid)  # v1.2 send-side identity guard (events.capsule v1.4 Rule 4)
    _guard_subject_axis(event_type, subject)  # v1.3 address-side identity guard (enforces events.capsule Rule 4 subject clause) — Argus A106

    EVENTS_DIR.mkdir(parents=True, exist_ok=True)

    with open(JSONL_PATH, "a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            lines = f.readlines()
            event_id = _next_id(lines)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ev: dict = {
                "id": event_id,
                "specversion": "1.0",
                "type": event_type,
                "source": source,
                "time": ts,
                "source_uid": source_uid,
                "lifecycle": lifecycle,
            }
            if subject:
                ev["subject"] = subject
            if correlationid:
                ev["correlationid"] = correlationid
            if data:
                ev["data"] = data
            raw = json.dumps(ev, ensure_ascii=False)
            f.write(raw + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    # SQLite WAL dual-write (derived; non-blocking on failure)
    try:
        conn = sqlite3.connect(str(SQLITE_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        _ensure_sqlite(conn)
        conn.execute(
            "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ev["id"], ev["specversion"], ev["type"], ev["source"], ev["time"],
             ev.get("subject"), ev["source_uid"], ev["lifecycle"],
             ev.get("correlationid"), json.dumps(ev.get("data")) if ev.get("data") else None,
             raw)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"WARN: SQLite dual-write failed (JSONL canonical is intact): {e}", file=sys.stderr)

    return ev


def _wake_loop_reminder(source_uid: str, subject: str) -> str:
    """Reminder shown when an agent emits a reply_required to another agent.

    Per Mike-A93 directive 2026-06-02: the substrate REMINDS the sender to consider a
    bounded self-wake loop when they're waiting on another agent's work. It does not arm
    one (the wake is harness-bound — only the agent can self-wake) and does not decide
    (agents make the call well; they just forget to think about it). Reminder, not
    automation. Scope: agent->agent reply_required only; never fires for plain emits.
    """
    bar = "─" * 64
    return (
        f"{bar}\n"
        f"⏰ wake-loop reminder — you emitted a reply_required to {subject}.\n"
        f"If you're now BLOCKED waiting on their work to proceed, consider arming a\n"
        f"bounded self-wake loop so their reply doesn't wait on a human relay:\n"
        f"  • poll : python3 vault/tools/2471edc0.py --as {source_uid}\n"
        f"           (+ --all if checking system telemetry)\n"
        f"  • every: ~60s (agents often turn work in a couple of beats)\n"
        f"  • bound: up to N checks (e.g. 10) — exits early the moment their reply lands\n"
        f"  • arm  : via your harness self-wake (e.g. ScheduleWakeup)\n"
        f"Not blocked — still working, or a human's in the loop? Skip it. Your call;\n"
        f"the substrate only reminds.\n"
        f"{bar}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Emit a CloudEvents v1.0 event to vault/events/")
    p.add_argument("--type", required=True, help="Event type (e.g. tropo.message.sent)")
    p.add_argument("--source", required=True, help="URI-shaped source identifier")
    p.add_argument("--source-uid", default=None, dest="source_uid",
                   help="8-hex emitter UID (non-agent sources only; forbidden for agent sources — use --as instead)")
    p.add_argument("--as", default=None, dest="as_name",
                   help="Agent name to resolve party_uid (agent sources only; mutually exclusive with --source-uid)")
    p.add_argument("--lifecycle", required=True, choices=sorted(VALID_LIFECYCLE))
    p.add_argument("--subject", default=None)
    p.add_argument("--data", default=None, help="JSON string payload")
    p.add_argument("--correlationid", default=None)
    p.add_argument("--final", action="store_true", default=None, help="Mark reply as terminal (data.final:true)")
    p.add_argument("--not-final", action="store_false", dest="final", help="Mark reply as non-terminal (data.final:false)")
    p.add_argument("--no-strict", action="store_true", dest="no_strict",
                   help="R3 v1.60: opt-out of strict mode (default is now ERROR on unregistered type per v1.60 ratchet)")
    args = p.parse_args()

    # S2.4 emit-on-party-identity (spec 81e52840): --as resolves party_uid for agent sources;
    # mutual exclusion enforced here so no raw-UID path remains for agent emits.
    is_agent_source = args.source.startswith("/agents/") or args.source.startswith("//")
    as_name = args.as_name or os.environ.get("TROPO_AGENT")
    if is_agent_source:
        if args.source_uid is not None:
            print("ERROR: --source-uid is forbidden for agent sources — use --as <name> instead "
                  "(spec 81e52840: agent emits resolve identity via registry, not raw UIDs)",
                  file=sys.stderr)
            return 1
        if not as_name:
            print("ERROR: --as <name> is required for agent sources (or set TROPO_AGENT env var); "
                  "--source-uid is forbidden for agent emits (spec 81e52840)",
                  file=sys.stderr)
            return 1
        source_uid = _resolve_identity_by_name(as_name)
    else:
        if as_name:
            print("ERROR: --as is only valid for agent sources (source starting with /agents/ or //); "
                  "use --source-uid for non-agent sources",
                  file=sys.stderr)
            return 1
        if args.source_uid is None:
            print("ERROR: --source-uid is required for non-agent sources", file=sys.stderr)
            return 1
        source_uid = args.source_uid

    data = {}
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"ERROR: --data is not valid JSON: {e}", file=sys.stderr)
            return 1

    # S2.4 emit-on-completion (spec 2fe61817): enforce terminality declaration for reply_required
    if args.correlationid and _is_reply_required_task(args.correlationid):
        if args.final is None:
            print(f"ERROR: correlationid {args.correlationid} is a reply_required request. "
                  "You MUST specify terminality via --final or --not-final (spec 2fe61817).",
                  file=sys.stderr)
            return 1
    
    if args.final is not None:
        if not isinstance(data, dict):
            print("ERROR: data must be a JSON object to support --final/--not-final", file=sys.stderr)
            return 1
        data["final"] = args.final

    try:
        ev = emit(args.type, args.source, source_uid, args.lifecycle,
                  subject=args.subject, data=data, correlationid=args.correlationid,
                  strict=not args.no_strict)  # v1.60 R-ratchet: strict=True is now default
        print(json.dumps({"id": ev["id"], "ts": ev["time"]}))
        # Wake-loop reminder (v1.1 — Mike-A93 directive): when an agent emits a
        # reply_required message to another agent, remind them to consider a bounded
        # self-wake loop. Suggestion only; agent decides. stderr keeps stdout parse-clean.
        if (args.type in ("tropo.message.sent", "tropo.message.replied")
                and isinstance(data, dict) and data.get("reply_required") is True
                and args.subject):
            print(_wake_loop_reminder(source_uid, args.subject), file=sys.stderr)
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
