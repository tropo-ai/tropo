#!/usr/bin/env python3
"""test_validator_negative_cases.py — v1.55 Behaviors 11+12+13+14: validator negative tests.

Verifies that event_validators.run_all_event_checks() fires the expected WARNs
when events violate events.capsule v1.1 §8 checks:

  Check 1 (Behavior 11): Missing required envelope field → WARN
  Check 5 (Behavior 12): Unregistered event type → WARN
  Check 7 (Behavior 13): Invalid lifecycle value → WARN (empirically proven via
                           v1.55 substrate-verify-twice case study; test formalizes)
  Check 9 (Behavior 14): Missing correlationid on reply-type event → WARN
"""
from __future__ import annotations
import json, sys, tempfile
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(VAULT_ROOT / '.tropo' / 'scripts'))
from lib.event_validators import run_all_event_checks

# Minimal valid event (Check 1 baseline)
VALID_EVENT = {
    "id": "00000001",
    "specversion": "1.0",
    "type": "tropo.message.sent",
    "source": "/agents/test",
    "time": "2026-05-27T00:00:00Z",
    "source_uid": "123e12e7",
    "lifecycle": "evergreen",
}


def write_events(events: list[dict], tmpdir: Path) -> Path:
    vault = tmpdir / "vault"
    events_dir = vault / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    jsonl = events_dir / "00-events.jsonl"
    lines = ["# test log"]
    for ev in events:
        lines.append(json.dumps(ev, ensure_ascii=False))
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmpdir


def check_fires(label: str, events: list[dict], expected_check: str) -> bool:
    with tempfile.TemporaryDirectory() as td:
        vault = write_events(events, Path(td))
        findings, checked, defects = run_all_event_checks(vault)
    matched = any(expected_check in f for f in findings)
    status = "PASS" if matched else "FAIL"
    print(f"  [{status}] {label}")
    if not matched:
        print(f"    Expected finding containing {expected_check!r}")
        print(f"    Got: {findings}")
    return matched


def main() -> int:
    passed = True

    # Behavior 11 — Check 1: missing required envelope field (remove 'source')
    ev_missing_field = {**VALID_EVENT}
    del ev_missing_field["source"]
    if not check_fires("Check 1 fires on missing 'source' field", [ev_missing_field], "Check 1"):
        passed = False

    # Behavior 12 — Check 5: unregistered event type
    ev_unregistered = {**VALID_EVENT, "type": "tropo.unregistered.unknown"}
    if not check_fires("Check 5 fires on unregistered type", [ev_unregistered], "Check 5"):
        passed = False

    # Behavior 13 — Check 7: invalid lifecycle (v1.55 substrate-verify-twice case study)
    ev_bad_lifecycle = {**VALID_EVENT, "lifecycle": "active"}  # was the bug value
    if not check_fires("Check 7 fires on lifecycle='active' (not {evergreen,ephemeral})", [ev_bad_lifecycle], "Check 7"):
        passed = False

    # Also verify 'open' and 'closed' (the other wrong values from the case study)
    for bad_val in ("open", "closed"):
        ev = {**VALID_EVENT, "lifecycle": bad_val}
        if not check_fires(f"Check 7 fires on lifecycle={bad_val!r}", [ev], "Check 7"):
            passed = False

    # Behavior 14 — Check 9: reply-type event missing correlationid
    ev_no_correlationid = {**VALID_EVENT, "type": "tropo.message.replied"}
    if not check_fires("Check 9 fires on tropo.message.replied without correlationid", [ev_no_correlationid], "Check 9"):
        passed = False

    # Bonus: Check 9 for tropo.message.acked without correlationid
    ev_acked_no_corr = {**VALID_EVENT, "type": "tropo.message.acked"}
    if not check_fires("Check 9 fires on tropo.message.acked without correlationid", [ev_acked_no_corr], "Check 9"):
        passed = False

    print(f"\n{'PASS' if passed else 'FAIL'} — validator negative cases (Checks 1+5+7+9)")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
