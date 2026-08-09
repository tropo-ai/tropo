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
cli_command: "python3 vault/tools/tropo-emit-event.py"
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
    id: {type: string, description: "Immutable event identity (legacy epoch remains 8-digit numeric)"}
    event_uid: {type: string, description: "Immutable event join key"}
    display_seq: {type: integer, description: "Derived human-friendly global order"}
    ts: {type: string, description: "ISO 8601 emission timestamp"}
write_scope: [vault/events/]
created: 2026-05-26
created_by: talos-t10
modified: 2026-07-31
modified_by: vela-v71
version: "1.11"
v1_11_note: "1f29bcfb Case 5, door half — Talos-consented, vela-v71. The terminality guard checked ONLY correlationid, so a reply carrying --causationid passed the door with no final: flag and was then silently discarded by check-events hours later. Talos's own watch confirmation was lost exactly this way. Both flags are correlation sources now, on the read side and here, so both are held to the same requirement — his framing: either read it or refuse it at the door, never accept silently and drop silently. This build does both (check-events v1.7 reads causationid; this guard refuses an untermed reply on either axis). ALSO: _is_reply_required_task() now resolves against the CANONICAL event union instead of the derived SQLite cache. The cache version returned False on any miss — a request emitted minutes earlier, or any divergence — so the lock quietly disengaged and the guard never fired. A door whose lock fails open in silence is not a door, and it was the same blind-instrument class as the finding it serves. It still fails open on a genuine read error, but it now says so on stderr instead of deciding in silence."
v1_10_note: "Captain-mode edit (talos-owned tool; Talos notified per the A95/A106 captain-edit precedent), Mike-directed 'I want it fixed permanently' 2026-07-31. Closes the trigger gap left by v1.9: the self-heal existed only on the WRITE path, so it could only fire when something emitted. On a multi-agent day the dominant divergence source is `git merge` — another agent's stream lands in the canonical union with NO local emit — so nothing triggered the heal and every read warned until a human ran tropo-rebuild-events-sqlite.py by hand. Observed live 2026-07-31: the projection diverged three times in 40 minutes purely from integrating crew pushes. THE FIX MOVES THE TRIGGER FROM A COMMAND TO A CONDITION: event_identity.ensure_sqlite_projection() pairs detection with repair in one shared gesture, and emit / check-events / query-events all call it, so ANY touch of the log repairs a divergence regardless of what caused it — merge, fresh clone, manual copy, or emit. Safety posture is unchanged and deliberately so: still only the sanctioned full rebuild (never an incremental patch), still cooldown-gated at 300s via a marker now SHARED across all callers so concurrent agents cannot storm it, plus a subprocess-env recursion guard (TROPO_SQLITE_AUTOHEAL_ACTIVE) and an operator escape hatch (TROPO_NO_SQLITE_AUTOHEAL) for a provably side-effect-free read. Delivery semantics are untouched: the canonical JSONL union is loaded before any repair and remains the sole delivery truth, so a heal can speed up later reads but can never change what a drain delivers. Regression-pinned by test_divergent_projection_self_heals_on_read (merge shape, read-only) and test_autoheal_is_cooldown_gated_and_never_recurses. In this tool specifically, _maybe_autorebuild_sqlite() is now a thin alias over the shared implementation so the private copy cannot drift from the read path's."
v1_9_note: "Captain-mode edit (talos-owned tool; Talos notified per the A95/A106 captain-edit precedent), Mike-directed 'fix the root cause' 2026-07-25. The SQLite dual-write projection had sat silently diverged for ~2 days (6625/7578 events, ~953 missing) because the v1.7 fail-closed gate has no self-heal: it correctly refuses to extend a divergent projection, but nothing then repairs it — a human has to notice the stderr warning and run tropo-rebuild-events-sqlite.py by hand, which nobody had. v1.9 adds `_maybe_autorebuild_sqlite()`: on gate failure, attempt ONE full rebuild via the same sanctioned recovery script (never an incremental patch — same safety posture as v1.7), rate-limited by a cooldown marker (`.sqlite-autorebuild-cooldown.json`, 300s window) so a recurring divergence cause can't trigger a rebuild storm. If the rebuild lands, the projection is re-checked so the SAME emit call can still dual-write. Paired with a backstop check in sa.daily-vault-health.md (Event-Log Health) that verifies projection completeness independent of any emit call — needed because if nothing emits for a while, this auto-heal never gets a chance to fire. Root cause of the ORIGINAL divergence not identified (the SQLite file is gitignored, no history to inspect, multiple concurrent writers active in the window) — this closes the 'nobody notices for days' gap, not the single race that first caused it."
v1_8_note: "Cut 4 R4/Q5 bounded usage capture under locked dev-spec 8078657b: registers only tropo.distill.usage.recorded; its required segment is accepted solely with the internal frozen derivation attestation, while CLI usage emission and segment/attestation on every older type are refused before append."
v1_7_note: "Projection initialization hardening: emission uses event_identity's exact canonical coverage contract, dual-writes only to a complete initialized SQLite cache, and never creates or extends an absent/partial/divergent projection; canonical JSONL remains authoritative and rebuild-events-sqlite remains the only initialization/recovery path."
v1_6_note: "Event Ledger distributed-identity implementation under dev-spec f15a9b85. Behind disabled cutover marker: default behavior remains legacy numeric append while active old-writer branches exist. When enabled, the unchanged CLI writes immutable event_uid + writer/local sequence to a per-writer stream and updates the dual-read SQLite projection."
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
belt_invocation: "python3 vault/tools/tropo-emit-event.py --as <name> ..."
belt_example: "python3 vault/tools/tropo-emit-event.py --type tropo.message.sent --as talos --lifecycle ephemeral --subject <party_uid> --data '{\"body\": \"...\"}'"
---

Atomic emit-event primitive for vault/events/00-events.jsonl.
CloudEvents v1.0 envelope. fcntl.flock exclusive lock prevents concurrent corruption.
Dual-write: JSONL canonical + SQLite WAL derived. Exit 0 on success; non-zero on error.

Usage (agent source — --as resolves party_uid from unified entries):
  python3 vault/tools/tropo-emit-event.py \\
    --type tropo.message.sent \\
    --source /agents/talos \\
    --as talos \\
    --lifecycle evergreen \\
    [--subject <party_uid>] \\
    [--data '{"body": "..."}'] \\
    [--correlationid <id>] \\
    [--final | --not-final]

Usage (non-agent source — --source-uid required):
  python3 vault/tools/tropo-emit-event.py \\
    --type tropo.substrate.created \\
    --source /tools/archive \\
    --source-uid 6cc9dcdb \\
    --lifecycle evergreen
"""

from __future__ import annotations
import argparse, fcntl, json, os, re, sqlite3, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

from lib import event_identity
from lib.capture_segment import verify_segment_attestation

VAULT_ROOT = Path(__file__).resolve().parents[2]
EVENTS_DIR = VAULT_ROOT / "vault" / "events"
JSONL_PATH = EVENTS_DIR / "00-events.jsonl"
SQLITE_PATH = EVENTS_DIR / "00-events-index.sqlite"
AGENTS_DIR = VAULT_ROOT / "vault" / "agents"
# v1.10: derived from the shared lib rather than restated, so the emit path and
# the read path can never drift onto different rebuild scripts or cooldowns.
REBUILD_SCRIPT_PATH = VAULT_ROOT / event_identity.REBUILD_SCRIPT_REL
AUTOREBUILD_COOLDOWN_PATH = VAULT_ROOT / event_identity.AUTOHEAL_COOLDOWN_REL
AUTOREBUILD_COOLDOWN_SECONDS = event_identity.AUTOHEAL_COOLDOWN_SECONDS

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
    # Release Coupling (fbe50871, Mike-locked 2026-07-13 -- this spec's lock IS the
    # lock-break authority for this registration): emitted by tropo-publish-release.py
    # --fire on full green (tag + main sha + release object all verified live); never
    # emitted on a partial/unverified outcome.
    "tropo.release.published",
    # Cycle Coordination Family (v1.59 Lane A events.capsule v1.2 §3)
    "tropo.cycle.activated", "tropo.cycle.ship_gate_progress",
    # v1.61 Lane EC events.capsule v1.3 additions
    "tropo.broadcast.crew", "tropo.substrate.archived",
    # Agent Lifecycle Family (events.capsule §3; auto-emitted by write-activation-entry.py)
    "tropo.agent.activated", "tropo.agent.retired",
    # Cut 4 R4/Q5 bounded usage capture (events.capsule v1.10; dev-spec 8078657b)
    "tropo.distill.usage.recorded",
}

VALID_LIFECYCLE = {"evergreen", "ephemeral"}  # per events.capsule v1.1 §2 (query-filter semantics; NOT cycle-phase)
USAGE_EVENT_TYPE = "tropo.distill.usage.recorded"
USAGE_DATA_KEYS = {
    "task_uid",
    "viewer_principal_uid",
    "index_as_of",
    "operation",
    "used_chunk_uids",
    "unused_chunk_uids",
}
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
    """Whether the correlation target is a reply_required:true request.

    v1.11: resolved against the CANONICAL event union, not the derived SQLite
    cache. The cache version failed open in silence — a request emitted minutes
    ago, or any divergence at all, simply returned False and the terminality
    guard never fired. A door whose lock quietly disengages when it cannot see
    is not a door, and it is the same blind-instrument class as 1f29bcfb.

    Still fails open on a genuine read error (never block an emit on infra
    trouble), but it now says so rather than deciding in silence.
    """
    try:
        for event in event_identity.load_event_union(VAULT_ROOT):
            identities = {
                str(event.get("id", "")),
                str(event.get("id", "")).zfill(8),
                event_identity.immutable_event_uid(event),
            }
            if correlationid in identities or correlationid.zfill(8) in identities:
                data = event.get("data") or {}
                return isinstance(data, dict) and data.get("reply_required") is True
    except Exception as exc:
        print(
            f"WARN: could not resolve {correlationid} against the canonical event "
            f"union ({exc}); the reply-terminality guard is failing OPEN for this "
            f"emit — if this is a reply, pass --final or --not-final explicitly",
            file=sys.stderr,
        )
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


def _validate_segment_contract(
    event_type: str,
    lifecycle: str,
    subject: str | None,
    data: dict | None,
    segment: object,
    segment_attestation: object,
) -> None:
    """Enforce the sole v1.10 segmented type before any storage is touched."""

    if event_type != USAGE_EVENT_TYPE:
        if segment is not None or segment_attestation is not None:
            raise ValueError(
                "segment and segment_attestation are forbidden for every "
                "pre-v1.10 event type"
            )
        return
    if lifecycle != "evergreen":
        raise ValueError("usage events require lifecycle='evergreen'")
    if not isinstance(segment, str) or not segment or segment.strip() != segment:
        raise ValueError("usage events require a derived non-empty top-level segment")
    if not isinstance(data, dict) or set(data) != USAGE_DATA_KEYS:
        raise ValueError(
            "usage event data must contain exactly the six registered keys"
        )
    task_uid = data.get("task_uid")
    viewer_uid = data.get("viewer_principal_uid")
    if not isinstance(task_uid, str) or not re.fullmatch(r"[0-9a-f]{8}", task_uid):
        raise ValueError("usage data.task_uid must be an 8-hex UID")
    if subject != task_uid:
        raise ValueError("usage event subject must exactly equal data.task_uid")
    if not isinstance(viewer_uid, str) or not re.fullmatch(r"[0-9a-f]{8}", viewer_uid):
        raise ValueError("usage data.viewer_principal_uid must be an 8-hex UID")
    index_as_of = data.get("index_as_of")
    if (
        not isinstance(index_as_of, str)
        or not index_as_of
        or not index_as_of.strip()
    ):
        raise ValueError("usage data.index_as_of must be a non-empty opaque token")
    if data.get("operation") != "distill":
        raise ValueError("usage data.operation must be the literal 'distill'")
    for key in ("used_chunk_uids", "unused_chunk_uids"):
        values = data.get(key)
        if not isinstance(values, list):
            raise ValueError(f"usage data.{key} must be a list")
        if any(
            not isinstance(uid, str) or not uid or uid.strip() != uid
            for uid in values
        ):
            raise ValueError(f"usage data.{key} contains a malformed chunk UID")
        if len(set(values)) != len(values):
            raise ValueError(f"usage data.{key} contains duplicate chunk UIDs")
    used = data["used_chunk_uids"]
    unused = data["unused_chunk_uids"]
    if set(used) & set(unused) or not (set(used) | set(unused)):
        raise ValueError(
            "usage chunk lists must be disjoint with a non-empty union"
        )
    verify_segment_attestation(
        segment_attestation,
        segment=segment,
        used_chunk_uids=used,
        unused_chunk_uids=unused,
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
    columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    additions = {
        "event_uid": "TEXT",
        "display_seq": "INTEGER",
        "writer_instance_uid": "TEXT",
        "stream_uid": "TEXT",
        "local_seq": "INTEGER",
        "causationid": "TEXT",
    }
    for name, sql_type in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE events ADD COLUMN {name} {sql_type}")
    conn.execute(
        "UPDATE events SET event_uid = 'legacy_' || id WHERE event_uid IS NULL"
    )
    conn.execute(
        "UPDATE events SET display_seq = CAST(id AS INTEGER) WHERE display_seq IS NULL"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_event_uid ON events(event_uid)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_display_seq ON events(display_seq)")
    conn.commit()


def _insert_sqlite_event(
    ev: dict,
    raw: str,
    *,
    projection_complete: bool,
) -> int | None:
    """Insert either legacy or distributed event into the derived projection."""
    if not projection_complete or not SQLITE_PATH.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{SQLITE_PATH}?mode=rw", uri=True)
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'"
        ).fetchone() is None:
            conn.close()
            print(
                "WARN: SQLite dual-write skipped because the derived projection "
                "has not been initialized by a canonical rebuild",
                file=sys.stderr,
            )
            return None
        conn.execute("PRAGMA journal_mode=WAL")
        _ensure_sqlite(conn)
        display_seq = conn.execute(
            "SELECT COALESCE(MAX(display_seq), 0) + 1 FROM events"
        ).fetchone()[0]
        event_uid = event_identity.immutable_event_uid(ev)
        conn.execute(
            """
            INSERT OR IGNORE INTO events (
                id, specversion, type, source, time, subject, source_uid,
                lifecycle, correlationid, data, raw, event_uid, display_seq,
                writer_instance_uid, stream_uid, local_seq, causationid
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ev["id"], ev["specversion"], ev["type"], ev["source"], ev["time"],
                ev.get("subject"), ev["source_uid"], ev["lifecycle"],
                ev.get("correlationid"),
                json.dumps(ev.get("data")) if ev.get("data") else None,
                raw, event_uid, display_seq, ev.get("writer_instance_uid"),
                ev.get("stream_uid"), ev.get("local_seq"), ev.get("causationid"),
            ),
        )
        conn.commit()
        conn.close()
        return int(display_seq)
    except Exception as exc:
        print(f"WARN: SQLite dual-write failed (canonical event is intact): {exc}", file=sys.stderr)


def _maybe_autorebuild_sqlite() -> bool:
    """Thin alias kept for callers/tests that reference the v1.9 entry point.

    v1.10: the implementation moved to ``event_identity.heal_sqlite_projection``
    so the read path shares one heal with the write path instead of each tool
    carrying a private copy. See the v1_10_note.
    """
    return event_identity.heal_sqlite_projection(VAULT_ROOT)


def emit(event_type: str, source: str, source_uid: str, lifecycle: str,
         subject: str | None = None, data: dict | None = None,
         correlationid: str | None = None, causationid: str | None = None,
         strict: bool = False, *, segment: str | None = None,
         segment_attestation: object = None) -> dict:
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
    _validate_segment_contract(
        event_type,
        lifecycle,
        subject,
        data,
        segment,
        segment_attestation,
    )
    _guard_party_axis(event_type, source, source_uid)  # v1.2 send-side identity guard (events.capsule v1.4 Rule 4)
    _guard_subject_axis(event_type, subject)  # v1.3 address-side identity guard (enforces events.capsule Rule 4 subject clause) — Argus A106

    if (
        event_type == "tropo.message.replied"
        and isinstance(data, dict)
        and data.get("final") is True
        and not event_identity.terminal_reply_has_renderable_content(
            VAULT_ROOT,
            data,
        )
    ):
        raise ValueError(
            "terminal tropo.message.replied requires a non-empty data.body "
            "or data.body_file; data.message is not renderable reply content"
        )
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    projection_complete = False
    if SQLITE_PATH.is_file():
        # v1.10: detect-and-heal is one shared gesture in event_identity, so an
        # emit and a read repair the same divergence the same way.
        projection_complete = event_identity.ensure_sqlite_projection(
            VAULT_ROOT,
            event_identity.load_event_union(VAULT_ROOT),
            sqlite_path=SQLITE_PATH,
            context="emit dual-write",
        )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ev: dict = {
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
    if causationid:
        ev["causationid"] = causationid
    if segment is not None:
        ev["segment"] = segment
    if data:
        ev["data"] = data

    if event_identity.streams_enabled(VAULT_ROOT):
        activation_uid = ""
        if isinstance(data, dict):
            for key in ("activation_uid", "pipeline_run_uid"):
                candidate = str(data.get(key) or "")
                if re.fullmatch(r"[0-9a-f]{8}", candidate):
                    activation_uid = candidate
                    break
        writer_uid = event_identity.derive_writer_instance_uid(
            VAULT_ROOT,
            source_uid,
            activation_uid=activation_uid,
        )
        ev = event_identity.append_stream_event(VAULT_ROOT, writer_uid, ev)
        raw = json.dumps(ev, ensure_ascii=False)
    else:
        with open(JSONL_PATH, "a+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                lines = f.readlines()
                event_id = _next_id(lines)
                ev["id"] = event_id
                raw = json.dumps(ev, ensure_ascii=False)
                f.write(raw + "\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    display_seq = _insert_sqlite_event(
        ev,
        raw,
        projection_complete=projection_complete,
    )
    if display_seq is not None:
        ev["display_seq"] = display_seq

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
        f"  • poll : python3 vault/tools/tropo-check-events.py --as {source_uid}\n"
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
    p.add_argument("--causationid", default=None)
    p.add_argument("--final", action="store_true", default=None, help="Mark reply as terminal (data.final:true)")
    p.add_argument("--not-final", action="store_false", dest="final", help="Mark reply as non-terminal (data.final:false)")
    p.add_argument("--no-strict", action="store_true", dest="no_strict",
                   help="R3 v1.60: opt-out of strict mode (default is now ERROR on unregistered type per v1.60 ratchet)")
    args = p.parse_args()

    if args.type == USAGE_EVENT_TYPE:
        print(
            "ERROR: tropo.distill.usage.recorded is internal-only and cannot be "
            "emitted through the CLI; use distiller_capture.capture_usage",
            file=sys.stderr,
        )
        return 1

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
    # v1.11 (1f29bcfb Case 5): the terminality guard used to check ONLY
    # correlationid, so a reply sent with --causationid sailed through the door
    # with no final: flag and was then silently discarded by check-events hours
    # later. Both flags are correlation sources now — on the read side and here
    # — so both are held to the same requirement. Refuse at the door rather
    # than let a well-formed reply become invisible.
    reply_target = args.correlationid or args.causationid
    if reply_target and _is_reply_required_task(reply_target):
        if args.final is None:
            via = "correlationid" if args.correlationid else "causationid"
            print(f"ERROR: {via} {reply_target} is a reply_required request. "
                  "You MUST specify terminality via --final or --not-final (spec 2fe61817). "
                  "Without it your reply is emitted but never closes the thread, and the "
                  "asker is told they were not answered.",
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
                  causationid=args.causationid,
                  strict=not args.no_strict)  # v1.60 R-ratchet: strict=True is now default
        print(json.dumps({
            "id": ev["id"],
            "event_uid": event_identity.immutable_event_uid(ev),
            "display_seq": ev.get("display_seq"),
            "ts": ev["time"],
        }))
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
