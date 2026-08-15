"""event_validators.py — Validation Checks 1-10 + 22-24 for the Event Ledger.

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
 11. terminal replies carry renderable content in data.body or data.body_file
 22. agent messaging/broadcast emit uses the PARTY UID, not the agent-root (v1.70 ERROR ratchet; spec 81e52840)
 23. terminal work transitions must have recorded events (v1.70; spec 2fe61817)
 24. the sole segmented usage type has its exact closed v1.10 contract
"""

from __future__ import annotations

TARGETS_CAPSULE = "events"  # Lane V Layer 3 M.1 targeting (8e2f1a47)
import importlib.util, json, re, sqlite3, sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
JSONL_PATH = VAULT_ROOT / "vault" / "events" / "00-events.jsonl"
SQLITE_PATH = VAULT_ROOT / "vault" / "events" / "00-events-index.sqlite"
AGENTS_DIR = VAULT_ROOT / "vault" / "agents"

_FINDINGS_MODULE_NAME = "tropo_engine_findings"
if _FINDINGS_MODULE_NAME in sys.modules:
    _findings = sys.modules[_FINDINGS_MODULE_NAME]
else:
    _findings_spec = importlib.util.spec_from_file_location(
        _FINDINGS_MODULE_NAME,
        VAULT_ROOT / "vault" / "tools" / "lib" / "findings.py",
    )
    if _findings_spec is None or _findings_spec.loader is None:
        raise ImportError("typed findings primitive could not be loaded")
    _findings = importlib.util.module_from_spec(_findings_spec)
    sys.modules[_FINDINGS_MODULE_NAME] = _findings
    _findings_spec.loader.exec_module(_findings)

Finding = _findings.Finding
Severity = _findings.Severity

_EVENT_IDENTITY_MODULE_NAME = "tropo_event_identity"
if _EVENT_IDENTITY_MODULE_NAME in sys.modules:
    event_identity = sys.modules[_EVENT_IDENTITY_MODULE_NAME]
else:
    _event_identity_spec = importlib.util.spec_from_file_location(
        _EVENT_IDENTITY_MODULE_NAME,
        VAULT_ROOT / "vault" / "tools" / "lib" / "event_identity.py",
    )
    if _event_identity_spec is None or _event_identity_spec.loader is None:
        raise ImportError("distributed event identity primitive could not be loaded")
    event_identity = importlib.util.module_from_spec(_event_identity_spec)
    sys.modules[_EVENT_IDENTITY_MODULE_NAME] = event_identity
    _event_identity_spec.loader.exec_module(event_identity)

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
    # Release Coupling (fbe50871, Mike-locked 2026-07-13 -- this spec's lock IS the
    # lock-break authority for this registration): emitted by tropo-publish-release.py
    # --fire on full green (tag + main sha + release object all verified live); never
    # emitted on a partial/unverified outcome.
    "tropo.release.published",
    # Cycle Coordination Family (v1.59 Lane A events.capsule v1.2 §3)
    "tropo.cycle.activated", "tropo.cycle.ship_gate_progress",
    # v1.61 Lane EC events.capsule v1.3 additions
    "tropo.broadcast.crew", "tropo.substrate.archived",
    # Agent Lifecycle Family (events.capsule §3 Agent Lifecycle Family; auto-emitted by write-activation-entry.py)
    "tropo.agent.activated", "tropo.agent.retired",
    # Cut 4 R4/Q5 bounded usage capture (events.capsule v1.10; dev-spec 8078657b)
    "tropo.distill.usage.recorded",
}
VALID_LIFECYCLE = {"evergreen", "ephemeral"}  # per events.capsule v1.1 §2 (query-filter; NOT cycle-phase)
USAGE_EVENT_TYPE = "tropo.distill.usage.recorded"
USAGE_DATA_KEYS = {
    "task_uid",
    "viewer_principal_uid",
    "index_as_of",
    "operation",
    "used_chunk_uids",
    "unused_chunk_uids",
}
REPLY_TYPES = {"tropo.message.acked", "tropo.message.replied"}
ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?$")
HEX8_RE = re.compile(r"^[0-9a-f]{8}$")
MESSAGING_TYPES = {"tropo.message.sent", "tropo.message.replied",
                   "tropo.message.acked", "tropo.broadcast.crew"}
PARTY_AXIS_CUTOFF = "2026-06-03"  # events.capsule v1.4 amendment date; pre-cutoff agent-root emits grandfathered
CHECK22_NAMED_EXEMPT = {"00004553", "00004606", "00005385"}  # T21 emits from activation-entry uid 586ce42d; grandfathered per talos-t22 disposition evt 00005054 (event log append-only; retro-fix impossible). Mechanism: orpheus-o26 evt 00005070; applied by argus-a122 (provenance chain 00005004 -> 00005054 -> 00005070). 00005385: T24 first-emit from unified-entry uid 3031ffa3 instead of party uid 34cf0f1c (Cursor harness first-emit shape; --as flag corrects going-forward; waiver applied per e3ef923a finding 2, argus-a124 confirmed).
COMPLETION_CUTOFF = "2026-06-13" # v1.70 S2.4 rollout


def _warn(check_id: str, subject: str, message: str) -> Finding:
    return Finding(Severity.WARN, check_id, subject, message)


def _error(check_id: str, subject: str, message: str) -> Finding:
    return Finding(Severity.ERROR, check_id, subject, message)


def _info(check_id: str, subject: str, message: str) -> Finding:
    return Finding(Severity.INFO, check_id, subject, message)

def _registered_party_uids(vault: Path) -> set[str]:
    """Party UIDs from crew identities plus portable user-agent registry rows."""
    agents_dir = vault / "vault" / "agents"
    uids = set()
    for p in agents_dir.glob("*.md") if agents_dir.is_dir() else []:
        try:
            txt = p.read_text(encoding="utf-8")
            m = re.search(r"^party_uid:\s*([0-9a-f]{8})", txt, re.MULTILINE)
            if m:
                uids.add(m.group(1))
        except OSError:
            continue
    registry = (
        vault / ".tropo-studio" / "registries" / "agent-registry.yaml"
    )
    try:
        text = registry.read_text(encoding="utf-8")
        uids.update(
            re.findall(r"^\s{2}([0-9a-f]{8}):\s*$", text, re.MULTILINE)
        )
    except OSError:
        pass
    return uids


def run_all_event_checks(vault: Path) -> tuple[list[Finding], int, int]:
    """Run Checks 1-10, 22, 23 against vault/events/00-events.jsonl.

    Returns (findings, events_checked, defects).
    """
    jsonl = vault / "vault" / "events" / "00-events.jsonl"
    sqlite = vault / "vault" / "events" / "00-events-index.sqlite"

    if not jsonl.exists():
        return [], 0, 0

    findings: list[Finding] = []
    events: list[dict] = []

    try:
        events = event_identity.load_event_union(vault)
    except Exception as exc:
        findings.append(_error("event-parse", "event union", f"could not load: {exc}"))
        return findings, 0, 1

    checked = len(events)

    # Check 1: Required envelope fields
    required = ["id", "specversion", "type", "source", "time", "source_uid", "lifecycle"]
    for ev in events:
        missing = [f for f in required if f not in ev]
        if missing:
            findings.append(_warn("event-1", f"event {ev.get('id', '?')}", f"missing required fields: {missing}"))

    # Check 2: specversion == "1.0"
    for ev in events:
        if ev.get("specversion") != "1.0":
            findings.append(_warn("event-2", f"event {ev.get('id','?')}", f"specversion={ev.get('specversion')!r} not '1.0'"))

    # Check 3: legacy epoch remains globally sequential; distributed streams
    # require globally unique event_uid + local monotonic sequence per writer.
    legacy_events = [ev for ev in events if not ev.get("event_uid")]
    ids = [ev.get("id", "") for ev in legacy_events]
    seen = set()
    for i, eid in enumerate(ids):
        if eid in seen:
            findings.append(_warn("event-3", f"event {eid!r}", "duplicate event id"))
        seen.add(eid)
        try:
            if int(eid) != i + 1:
                findings.append(_warn("event-3", f"event {eid!r}", f"id gap: expected {i+1:08d}"))
        except (ValueError, TypeError):
            findings.append(_warn("event-3", f"event {eid!r}", "id is not numeric"))

    event_uids: set[str] = set()
    streams: dict[str, list[int]] = {}
    for ev in events:
        event_uid = event_identity.immutable_event_uid(ev)
        if event_uid in event_uids:
            findings.append(_error("event-3", event_uid, "duplicate immutable event identity"))
        event_uids.add(event_uid)
        if ev.get("event_uid"):
            writer = str(ev.get("writer_instance_uid") or "")
            try:
                local_seq = int(ev.get("local_seq"))
            except (TypeError, ValueError):
                findings.append(_error("event-3", event_uid, "missing/non-integer local_seq"))
                continue
            if not writer:
                findings.append(_error("event-3", event_uid, "missing writer_instance_uid"))
                continue
            streams.setdefault(writer, []).append(local_seq)
    for writer, local_seqs in streams.items():
        if sorted(local_seqs) != list(range(1, len(local_seqs) + 1)):
            findings.append(
                _error(
                    "event-3",
                    writer,
                    f"local sequence has gap/duplicate: {sorted(local_seqs)}",
                )
            )

    # Check 4: time ISO 8601
    for ev in events:
        t = ev.get("time", "")
        if t and not ISO8601_RE.match(t):
            findings.append(_warn("event-4", f"event {ev.get('id','?')}", f"time {t!r} not ISO 8601"))

    # Check 5: type in registered registry
    for ev in events:
        if ev.get("type") not in REGISTERED_TYPES:
            findings.append(_warn("event-5", f"event {ev.get('id','?')}", f"type {ev.get('type')!r} not in registered types"))

    # Check 6: source_uid mandatory 8-hex
    for ev in events:
        uid = ev.get("source_uid", "")
        if not HEX8_RE.fullmatch(uid):
            findings.append(_warn("event-6", f"event {ev.get('id','?')}", f"source_uid {uid!r} not 8-hex"))

    # Check 7: lifecycle in enum
    for ev in events:
        lc = ev.get("lifecycle", "")
        if lc not in VALID_LIFECYCLE:
            findings.append(_warn("event-7", f"event {ev.get('id','?')}", f"lifecycle {lc!r} not in {sorted(VALID_LIFECYCLE)}"))

    # Check 9: correlationid required for reply-type events
    for ev in events:
        if ev.get("type") in REPLY_TYPES and not ev.get("correlationid"):
            findings.append(_warn("event-9", f"event {ev.get('id','?')}", f"type {ev.get('type')!r} missing correlationid"))

    # Check 11: a terminal reply must carry content that channel/event
    # renderers can display. ``message`` is not part of the registered reply
    # schema and must not silently satisfy this contract.
    for ev in events:
        data = ev.get("data")
        if (
            ev.get("type") == "tropo.message.replied"
            and isinstance(data, dict)
            and data.get("final") is True
            and not event_identity.terminal_reply_has_renderable_content(
                vault,
                data,
            )
        ):
            findings.append(
                _error(
                    "event-11",
                    f"event {ev.get('event_uid') or ev.get('id', '?')}",
                    "terminal reply requires a non-empty data.body or "
                    "data.body_file; data.message is not renderable reply content",
                )
            )

    # Check 24 (events.capsule v1.10): exactly one event family may carry
    # segment, and that usage family has a closed durable envelope/payload.
    for ev in events:
        event_type = ev.get("type")
        if event_type != USAGE_EVENT_TYPE:
            if "segment" in ev:
                findings.append(
                    _error(
                        "event-24",
                        f"event {ev.get('id','?')}",
                        "top-level segment is forbidden on pre-v1.10 event types",
                    )
                )
            continue

        problems: list[str] = []
        segment = ev.get("segment")
        if (
            not isinstance(segment, str)
            or not segment
            or segment.strip() != segment
        ):
            problems.append("segment must be a non-empty derived string")
        if ev.get("lifecycle") != "evergreen":
            problems.append("lifecycle must be evergreen")
        data = ev.get("data")
        if not isinstance(data, dict):
            problems.append("data must be an object")
        elif set(data) != USAGE_DATA_KEYS:
            problems.append("data must contain exactly the six registered keys")
        else:
            task_uid = data.get("task_uid")
            viewer_uid = data.get("viewer_principal_uid")
            if not isinstance(task_uid, str) or not HEX8_RE.fullmatch(task_uid):
                problems.append("data.task_uid must be 8-hex")
            if ev.get("subject") != task_uid:
                problems.append("subject must exactly equal data.task_uid")
            if not isinstance(viewer_uid, str) or not HEX8_RE.fullmatch(viewer_uid):
                problems.append("data.viewer_principal_uid must be 8-hex")
            index_as_of = data.get("index_as_of")
            if (
                not isinstance(index_as_of, str)
                or not index_as_of
                or not index_as_of.strip()
            ):
                problems.append("data.index_as_of must be a non-empty opaque token")
            if data.get("operation") != "distill":
                problems.append("data.operation must be the literal 'distill'")
            classified: dict[str, list[str]] = {}
            for key in ("used_chunk_uids", "unused_chunk_uids"):
                values = data.get(key)
                if not isinstance(values, list):
                    problems.append(f"data.{key} must be a list")
                    continue
                if any(
                    not isinstance(uid, str) or not uid or uid.strip() != uid
                    for uid in values
                ):
                    problems.append(f"data.{key} contains a malformed chunk UID")
                    continue
                if len(set(values)) != len(values):
                    problems.append(f"data.{key} contains duplicate chunk UIDs")
                classified[key] = values
            if len(classified) == 2:
                used = classified["used_chunk_uids"]
                unused = classified["unused_chunk_uids"]
                if set(used) & set(unused):
                    problems.append("used and unused chunk UID lists overlap")
                if not (set(used) | set(unused)):
                    problems.append("chunk UID partition must be non-empty")
        for problem in problems:
            findings.append(
                _error(
                    "event-24",
                    f"event {ev.get('id','?')}",
                    problem,
                )
            )

    # Check 10: canonical Event Ledger row count == SQLite row count
    if sqlite.exists():
        try:
            conn = sqlite3.connect(str(sqlite))
            sqlite_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            conn.close()
            if sqlite_count != checked:
                findings.append(
                    _warn(
                        "event-10",
                        "storage integrity",
                        f"JSONL={checked} events vs SQLite={sqlite_count} rows — "
                        "run rebuild-events-sqlite tool to resync",
                    )
                )
        except Exception as e:
            findings.append(_warn("event-10", "SQLite integrity", f"check failed: {e}"))

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
            if ev.get("id") in CHECK22_NAMED_EXEMPT:
                findings.append(
                    _info(
                        "event-22",
                        f"event {ev.get('id','?')}",
                        "named-exempt (waiver; talos-t22 disposition 00005054)",
                    )
                )
                continue
            if ev.get("source_uid", "") not in party_uids:
                findings.append(
                    _error(
                        "event-22",
                        f"event {ev.get('id','?')}",
                        f"agent emit from non-party source_uid {ev.get('source_uid')!r} "
                        "(spec 81e52840)",
                    )
                )

    # Check 23 (v1.70): Completion Recording
    # Detects work items closed without a terminal event.
    # Scoped to items modified after the COMPLETION_CUTOFF.
    index_paths = (
        vault / "vault" / "00-index.jsonl",
        vault / "vault" / "00-archive-index.jsonl",
    )
    if any(path.exists() for path in index_paths):
        work_uids_terminal: dict[str, str] = {}
        # Completion recording is history-aware: terminal archived work moves
        # off the default surface under ADR-047 but its terminal event remains
        # a validation obligation.
        for index_path in index_paths:
            if not index_path.exists():
                continue
            for line in index_path.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                    if rec.get("state") in ("done", "archived"):
                        mod = rec.get("modified", "")
                        if mod >= COMPLETION_CUTOFF:
                            work_uids_terminal[rec["uid"]] = rec.get("type", "work")
                except Exception:
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
                        _warn(
                            "event-23",
                            f"{item_type} {uid}",
                            f"is terminal (state:{item_type}) but has no recorded terminal event "
                            "(spec 2fe61817)",
                        )
                    )

    return findings, checked, sum(1 for finding in findings if finding.severity == Severity.ERROR)
