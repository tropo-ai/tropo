"""trigger_detection.py — L.3 harness trigger-detection for continuous-listen polling.

Per v1.58 dev-spec 9a3c5e84 L.3. Recognizes when an agent has unanswered
reply_required:true messages or unhandled severity:flash alerts in the event log
and returns the appropriate ScheduleWakeup polling curve cadence.

v1.61 Lane D'2 amendment: severity:flash auto-fire. Any event carrying severity:flash
addressed to the agent's party UID (direct subject match) OR broadcast-inclusive
(tropo.broadcast.crew with no specific subject or subject matching agent) triggers
the tight-phase curve immediately — highest-urgency tier per events.capsule v1.3.

Usage at session start (in agent boot or first-message handler):
    from lib.trigger_detection import get_schedule_wakeup_args
    schedule_args = get_schedule_wakeup_args(my_agent_uid)
    if schedule_args:
        # Emit ScheduleWakeup with schedule_args['delay_seconds'] + schedule_args['reason']

Polling curves (per pin-a85-008 / L.1 Tier 2 continuous-listen protocol):
    tight:   1m × 5   (unanswered reply_required within last 30min OR severity:flash)
    medium:  5m × 6   (unanswered reply_required within last 6h)
    ambient: 20m × 3  (any outstanding; older)
    none:    no wake needed
"""
from __future__ import annotations
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

VAULT_ROOT = Path(__file__).resolve().parents[3]
JSONL_PATH = VAULT_ROOT / "vault" / "events" / "00-events.jsonl"

# Polling curve delays in seconds
CURVE_TIGHT   = 60    # 1 minute  (tight phase)
CURVE_MEDIUM  = 300   # 5 minutes (medium phase)
CURVE_AMBIENT = 1200  # 20 minutes (ambient)


def _read_recent_events(since_minutes: int = 360) -> list[dict]:
    """Read events from the last N minutes."""
    if not JSONL_PATH.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    events = []
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            ev = json.loads(line)
            ts_str = ev.get("time", "")
            # Parse ISO timestamp
            ts_str = ts_str.rstrip("Z")
            ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                events.append(ev)
        except (json.JSONDecodeError, ValueError):
            continue
    return events


def has_pending_flash_alert(agent_uid: str, since_minutes: int = 60) -> dict | None:
    """v1.61 Lane D'2 — Check for unhandled severity:flash events.

    A flash alert is directed at the agent if:
    - Any event with severity:flash where subject == agent_uid (direct)
    - tropo.broadcast.crew with severity:flash (crew-wide; inclusive of all agents)

    Returns the most recent unhandled flash event, or None.
    Flash alerts are considered "handled" if the agent has emitted any event
    with correlationid == flash_event_id (i.e., acknowledged the flash).
    """
    events = _read_recent_events(since_minutes)

    flash_events: dict[str, dict] = {}
    for ev in events:
        if ev.get("severity") != "flash":
            continue
        ev_type = ev.get("type", "")
        subj = ev.get("subject", "")
        # Direct flash: subject is this agent's uid
        if subj == agent_uid:
            flash_events[ev["id"]] = ev
        # Crew-wide flash broadcast: tropo.broadcast.crew with no specific subject
        # OR subject is a broadcast descriptor (not a specific agent uid)
        elif ev_type == "tropo.broadcast.crew":
            flash_events[ev["id"]] = ev

    if not flash_events:
        return None

    # Consider acknowledged if agent has replied with correlationid matching
    acknowledged: set[str] = set()
    for ev in events:
        corr = ev.get("correlationid")
        if corr and ev.get("source_uid") == agent_uid:
            acknowledged.add(corr)

    unhandled = {k: v for k, v in flash_events.items() if k not in acknowledged}
    if not unhandled:
        return None

    return sorted(unhandled.values(), key=lambda e: e["id"], reverse=True)[0]


def has_unanswered_reply_required(agent_uid: str, since_minutes: int = 360) -> dict | None:
    """Check if agent has unanswered reply_required:true messages.

    Returns the most recent unanswered message dict, or None.
    """
    events = _read_recent_events(since_minutes)

    # Find reply_required messages sent TO this agent
    pending: dict[str, dict] = {}  # event_id → event
    for ev in events:
        data = ev.get("data") or {}
        if not isinstance(data, dict):
            continue
        if ev.get("subject") == agent_uid and data.get("reply_required") is True:
            pending[ev["id"]] = ev

    # Remove any that have been replied to (correlationid matches)
    replied_to: set[str] = set()
    for ev in events:
        corr = ev.get("correlationid")
        if corr and ev.get("source_uid") == agent_uid:
            replied_to.add(corr)

    unanswered = {k: v for k, v in pending.items() if k not in replied_to}
    if not unanswered:
        return None

    # Return the most recent
    return sorted(unanswered.values(), key=lambda e: e["id"], reverse=True)[0]


def get_schedule_wakeup_args(
    agent_uid: str,
    loop_prompt: str = "<<autonomous-loop-dynamic>>",
) -> dict | None:
    """Determine if a ScheduleWakeup should fire and with what delay.

    Returns a dict with 'delay_seconds', 'reason', 'prompt' if a wake is needed.
    Returns None if no outstanding triggers — no wake needed.
    """
    # Check severity:flash first — highest urgency; always fires tight curve (v1.61 Lane D'2)
    flash = has_pending_flash_alert(agent_uid, since_minutes=60)
    if flash:
        src = flash.get("source_uid", "?")[:8]
        ev_type = flash.get("type", "?")
        return {
            "delay_seconds": CURVE_TIGHT,
            "reason": f"unhandled severity:flash event from {src} ({ev_type}) — tight-phase 1m curve",
            "prompt": loop_prompt,
        }

    # Check tight window (last 30 min)
    recent = has_unanswered_reply_required(agent_uid, since_minutes=30)
    if recent:
        sender = recent.get("source_uid", "?")[:8]
        return {
            "delay_seconds": CURVE_TIGHT,
            "reason": f"unanswered reply_required from {sender} (tight-phase 1m curve)",
            "prompt": loop_prompt,
        }

    # Check medium window (last 6h)
    medium = has_unanswered_reply_required(agent_uid, since_minutes=360)
    if medium:
        sender = medium.get("source_uid", "?")[:8]
        return {
            "delay_seconds": CURVE_MEDIUM,
            "reason": f"unanswered reply_required from {sender} (medium-phase 5m curve)",
            "prompt": loop_prompt,
        }

    return None  # No outstanding triggers; no wake needed


def summarize_trigger_state(agent_uid: str) -> str:
    """Return a one-line summary of trigger state for boot logging."""
    args = get_schedule_wakeup_args(agent_uid)
    if args is None:
        return "trigger_detection: no outstanding triggers (no flash alerts, no reply_required) — ambient mode"
    return f"trigger_detection: {args['reason']} → ScheduleWakeup {args['delay_seconds']}s"


def _read_tier3_fleet_ops_schedule(tier3_path: Path) -> dict | None:
    """Read fleet_ops_schedule from an agent's Tier 3 boot extension file.

    Returns the fleet_ops_schedule dict (with 'daily' and/or 'weekly' keys)
    or None if no schedule declared or file unreadable.
    """
    if not _HAS_YAML or not tier3_path.exists():
        return None
    try:
        content = tier3_path.read_text(encoding="utf-8")
        # Extract YAML frontmatter
        match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
        if not match:
            return None
        fm = _yaml.safe_load(match.group(1)) or {}
        schedule = fm.get("fleet_ops_schedule")
        if isinstance(schedule, dict):
            return schedule
        return None
    except Exception:
        return None


def _fleet_ops_last_fired_today(agent_uid: str) -> bool:
    """Check if a fleet-ops dispatch event was emitted by this agent today.

    Looks for tropo.broadcast.crew events from the agent with category:ops
    in the last 24h as proxy for fleet-ops having fired today.
    """
    events = _read_recent_events(since_minutes=24 * 60)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for ev in events:
        if ev.get("source_uid") != agent_uid:
            continue
        if ev.get("type") != "tropo.broadcast.crew":
            continue
        data = ev.get("data") or {}
        if isinstance(data, dict) and data.get("category") == "ops":
            # Fleet-ops dispatch events emit tropo.broadcast.crew category:ops
            ts_str = ev.get("time", "")
            if ts_str.startswith(today_str):
                return True
    return False


def get_fleet_ops_wakeup_args(
    agent_uid: str,
    tier3_path: Path,
    loop_prompt: str = "<<autonomous-loop-dynamic>>",
) -> dict | None:
    """v1.61 Lane F — Fleet-ops schedule ScheduleWakeup trigger.

    Reads the agent's Tier 3 fleet_ops_schedule: declaration. If a daily
    schedule is declared and fleet-ops hasn't fired today, returns ScheduleWakeup
    args with dispatch_fleet_ops_daily payload.

    This is the harness wire that closes the V44-V53 fleet-ops dormancy class
    per Tier 2 cf8c3be9 §Fleet-Ops Schedule Protocol v2.3 + Mike-V49 binding directive 3.

    Args:
        agent_uid: The agent's party UID (for last-fired check)
        tier3_path: Path to the agent's Tier 3 boot extension .md file
        loop_prompt: /loop prompt to fire on wake

    Returns:
        dict with 'delay_seconds', 'reason', 'prompt' if fleet-ops is overdue; else None
    """
    schedule = _read_tier3_fleet_ops_schedule(tier3_path)
    if not schedule:
        return None  # No fleet_ops_schedule declared — skip

    if _fleet_ops_last_fired_today(agent_uid):
        return None  # Already fired today — no wake needed

    # Daily schedule overdue — fire tight-phase wake for fleet-ops dispatch
    if "daily" in schedule:
        daily = schedule["daily"]
        cadence = daily.get("cadence", "07:00") if isinstance(daily, dict) else "07:00"
        agent_list = daily.get("agents", []) if isinstance(daily, dict) else []
        agent_count = len(agent_list)
        return {
            "delay_seconds": CURVE_TIGHT,
            "reason": f"fleet-ops daily schedule overdue (cadence: {cadence}; {agent_count} agents) — dispatch_fleet_ops_daily",
            "prompt": "dispatch_fleet_ops_daily",
        }

    return None


def get_emit_side_wakeup_args(
    emitted_event: dict,
    emitting_agent_uid: str,
    loop_prompt: str = "<<autonomous-loop-dynamic>>",
) -> dict | None:
    """R2 v1.59 Lane C: emit-side ScheduleWakeup trigger detection.

    When an agent emits a reply_required:true message, they should also schedule
    a wakeup to poll for the response. Closes stm-a87-002 (architect-doesn-t-fire-own-schedulewakeup).

    Returns ScheduleWakeup args dict if a wakeup should be scheduled, else None.
    Call this from emit-event.py post-emit hook when data.reply_required is True.
    """
    data = emitted_event.get("data") or {}
    if not isinstance(data, dict):
        return None
    if not data.get("reply_required"):
        return None
    if emitted_event.get("source_uid") != emitting_agent_uid:
        return None

    recipient = emitted_event.get("subject", "?")[:8]
    return {
        "delay_seconds": CURVE_TIGHT,
        "reason": f"emitted reply_required to {recipient} — polling tight-phase for response",
        "prompt": loop_prompt,
    }
