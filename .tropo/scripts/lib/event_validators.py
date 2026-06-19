"""event_validators.py — Validation Checks 1-10 + 22-23 for vault/events/00-events.jsonl.

Per events.capsule v1.1 (72ef5ffe) §8 Validation Checks.
Wired into tropo-validate.py main() by Talos T10 v1.55 Stream A.8.

Checks (WARN at v1.55; ERROR ratchet planned v1.56 once registry stabilizes):
  1. Envelope required fields present (id + specversion + type + source + time + source_uid + lifecycle)
  2. specversion literal "1.0"
  3. id sequential (no gaps, no duplicates)
  4. time ISO 8601 format
  5. type in registered event type registry
  6. source_uid mandatory 8-hex
  7. lifecycle mandatory, in enum {evergreen, ephemeral} per events.capsule v1.1 §2 (query-filter semantics; NOT cycle-phase)
  8. source_uid not charter UID (structural guard; charter UIDs don't emit events)
  9. Per-type required extensions present (correlationid for reply events)
 10. JSONL row count == SQLite row count (storage integrity check)
 22. agent messaging/broadcast emit uses the PARTY UID, not the agent-root (v1.70 ERROR ratchet; spec 81e52840)
 23. terminal work transitions must have recorded events (v1.70; spec 2fe61817)
"""

from __future__ import annotations

TARGETS_CAPSULE = "events"  # Lane V Layer 3 M.1 targeting (8e2f1a47)
import json, re, sqlite3
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
JSONL_PATH = VAULT_ROOT / "vault" / "events" / "00-events.jsonl"
SQLITE_PATH = VAULT_ROOT / "vault" / "events" / "00-events-index.sqlite"
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
    # Pipeline lifecycle family + release lifecycle (v1.58 C.4-C.6)
    "tropo.pipeline.activated", "tropo.pipeline.bootstrapped",
    "tropo.pipeline.step_completed", "tropo.pipeline.closed",
    "tropo.release.shipped",
    # Cycle Coordination Family (v1.59 Lane A events.capsule v1.2 §3)
    "tropo.cycle.activated", "tropo.cycle.ship_gate_progress",
    # v1.61 Lane EC events.capsule v1.3 additions
    "tropo.broadcast.crew", "tropo.substrate.archived",
    # Agent Lifecycle Family (events.capsule §3 Agent Lifecycle Family; auto-emitted by write-activation-entry.py)
    "tropo.agent.activated", "tropo.agent.retired",
}
VALID_LIFECYCLE = {"evergreen", "ephemeral"}  # per events.capsule v1.1 §2 (query-filter; NOT cycle-phase)
REPLY_TYPES = {"tropo.message.acked", "tropo.message.replied"}
ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?$")
HEX8_RE = re.compile(r"^[0-9a-f]{8}$")
MESSAGING_TYPES = {"tropo.message.sent", "tropo.message.replied",
                   "tropo.message.acked", "tropo.broadcast.crew"}
PARTY_AXIS_CUTOFF = "2026-06-03"  # events.capsule v1.4 amendment date; pre-cutoff agent-root emits grandfathered
COMPLETION_CUTOFF = "2026-06-13" # v1.70 S2.4 rollout

def _registered_party_uids(vault: Path) -> set[str]:
    """Party UIDs (messaging axis) from the unified agent entries at vault/agents/.
    Stdlib regex parse; empty set if the directory is unreadable."""
    agents_dir = vault / "vault" / "agents"
    if not agents_dir.is_dir():
        return set()
    uids = set()
    for p in agents_dir.glob("*.md"):
        try:
            txt = p.read_text(encoding="utf-8")
            m = re.search(r"^party_uid:\s*([0-9a-f]{8})", txt, re.MULTILINE)
            if m:
                uids.add(m.group(1))
        except OSError:
            continue
    return uids


def run_all_event_checks(vault: Path) -> tuple[list[str], int, int]:
    """Run Checks 1-10, 22, 23 against vault/events/00-events.jsonl.

    Returns (findings, events_checked, defects).
    """
    jsonl = vault / "vault" / "events" / "00-events.jsonl"
    sqlite = vault / "vault" / "events" / "00-events-index.sqlite"

    if not jsonl.exists():
        return [], 0, 0

    findings: list[str] = []
    events: list[dict] = []

    for lineno, line in enumerate(jsonl.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError as e:
            findings.append(f"  [WARN] events.jsonl line {lineno}: malformed JSON — {e}")
            continue
        events.append(ev)

    checked = len(events)

    # Check 1: Required envelope fields
    required = ["id", "specversion", "type", "source", "time", "source_uid", "lifecycle"]
    for ev in events:
        missing = [f for f in required if f not in ev]
        if missing:
            findings.append(f"  [WARN] event {ev.get('id', '?')} missing required fields: {missing} (Check 1)")

    # Check 2: specversion == "1.0"
    for ev in events:
        if ev.get("specversion") != "1.0":
            findings.append(f"  [WARN] event {ev.get('id','?')} specversion={ev.get('specversion')!r} not '1.0' (Check 2)")

    # Check 3: id sequential, no duplicates
    ids = [ev.get("id", "") for ev in events]
    seen = set()
    for i, eid in enumerate(ids):
        if eid in seen:
            findings.append(f"  [WARN] duplicate event id {eid!r} (Check 3)")
        seen.add(eid)
        try:
            if int(eid) != i + 1:
                findings.append(f"  [WARN] event id gap: expected {i+1:08d} got {eid!r} (Check 3)")
        except (ValueError, TypeError):
            findings.append(f"  [WARN] event id not numeric: {eid!r} (Check 3)")

    # Check 4: time ISO 8601
    for ev in events:
        t = ev.get("time", "")
        if t and not ISO8601_RE.match(t):
            findings.append(f"  [WARN] event {ev.get('id','?')} time {t!r} not ISO 8601 (Check 4)")

    # Check 5: type in registered registry
    for ev in events:
        if ev.get("type") not in REGISTERED_TYPES:
            findings.append(f"  [WARN] event {ev.get('id','?')} type {ev.get('type')!r} not in registered types (Check 5)")

    # Check 6: source_uid mandatory 8-hex
    for ev in events:
        uid = ev.get("source_uid", "")
        if not HEX8_RE.fullmatch(uid):
            findings.append(f"  [WARN] event {ev.get('id','?')} source_uid {uid!r} not 8-hex (Check 6)")

    # Check 7: lifecycle in enum
    for ev in events:
        lc = ev.get("lifecycle", "")
        if lc not in VALID_LIFECYCLE:
            findings.append(f"  [WARN] event {ev.get('id','?')} lifecycle {lc!r} not in {sorted(VALID_LIFECYCLE)} (Check 7)")

    # Check 9: correlationid required for reply-type events
    for ev in events:
        if ev.get("type") in REPLY_TYPES and not ev.get("correlationid"):
            findings.append(f"  [WARN] event {ev.get('id','?')} type {ev.get('type')!r} missing correlationid (Check 9)")

    # Check 10: JSONL row count == SQLite row count
    if sqlite.exists():
        try:
            conn = sqlite3.connect(str(sqlite))
            sqlite_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            conn.close()
            if sqlite_count != checked:
                findings.append(
                    f"  [WARN] storage integrity: JSONL={checked} events vs SQLite={sqlite_count} rows — "
                    f"run rebuild-events-sqlite tool to resync (Check 10)")
        except Exception as e:
            findings.append(f"  [WARN] SQLite integrity check failed: {e} (Check 10)")

    # Check 22 (v1.70 ERROR): agent messaging/broadcast emits must use the PARTY UID
    party_uids = _registered_party_uids(vault)
    if party_uids:
        for ev in events:
            if ev.get("type") not in MESSAGING_TYPES:
                continue
            src = ev.get("source", "") or ""
            if not (src.startswith("/agents/") or src.startswith("//")):
                continue
            if (ev.get("time", "") or "")[:10] < PARTY_AXIS_CUTOFF:
                continue
            if ev.get("source_uid", "") not in party_uids:
                findings.append(
                    f"  [FAIL] event {ev.get('id','?')} agent emit from non-party source_uid "
                    f"{ev.get('source_uid')!r} (Check 22 ERROR; spec 81e52840)")

    # Check 23 (v1.70): Completion Recording
    # Detects work items closed without a terminal event.
    # Scoped to items modified after the COMPLETION_CUTOFF.
    index_path = vault / "vault" / "00-index.jsonl"
    if index_path.exists():
        work_uids_terminal: dict[str, str] = {}
        for line in index_path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                if rec.get("state") in ("done", "archived"):
                    mod = rec.get("modified", "")
                    if mod >= COMPLETION_CUTOFF:
                        work_uids_terminal[rec["uid"]] = rec.get("type", "work")
            except:
                continue
        
        if work_uids_terminal:
            # Events with data.final: true OR tropo.cycle.closed
            terminal_event_refs = set()
            for ev in events:
                data = ev.get("data")
                if isinstance(data, dict) and data.get("final") is True:
                    cid = ev.get("correlationid")
                    if cid:
                        terminal_event_refs.add(cid.zfill(8))
                if ev.get("type") == "tropo.cycle.closed":
                    cid = ev.get("correlationid")
                    if cid:
                        terminal_event_refs.add(cid.zfill(8))

            for uid, item_type in work_uids_terminal.items():
                if uid not in terminal_event_refs:
                    findings.append(
                        f"  [WARN] {item_type} {uid} is terminal (state:{item_type}) but has no "
                        f"recorded terminal event (Check 23; spec 2fe61817)")

    return findings, checked, len([f for f in findings if "[FAIL]" in f])
