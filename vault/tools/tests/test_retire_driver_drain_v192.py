"""AC3 (b1e78abb, v1.92): the driver reports unanswered reply_required on
EITHER axis (party + agent-root) as an open step, or records an explicit
flag-and-proceed that NAMES each open thread with its event id.

Fixture bus under --root, never the live stream (per the spec's own
§Acceptance: "a test that emits a real retirement broadcast... or drains the
live receipt ledger, writes governed substrate as a side effect of being
run"). Reuses observe_event_drain, already built for AC1's step 6.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_retire_driver_drain_v192
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("retire_driver_ac3", TOOLS / "tropo-retire-driver.py")
driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(driver)

PARTY_UID = "aaaaaaaa"
AGENT_ROOT_UID = "bbbbbbbb"


def _rr_event(evt_id: str, subject: str) -> dict:
    return {
        "specversion": "1.0", "type": "tropo.message.sent",
        "source": "/agents/someone", "time": "2026-08-24T00:00:00Z",
        "source_uid": "cccccccc", "lifecycle": "evergreen",
        "subject": subject,
        "data": {"reply_required": True, "body": "please answer"},
        "id": evt_id, "event_uid": evt_id,
        "writer_instance_uid": "unanswered", "stream_uid": "unanswered", "local_seq": 1,
    }


def _reply_event(evt_id: str, correlation_id: str) -> dict:
    return {
        "specversion": "1.0", "type": "tropo.message.replied",
        "source": "/agents/retiring-agent", "time": "2026-08-24T00:01:00Z",
        "source_uid": PARTY_UID, "lifecycle": "evergreen",
        "correlationid": correlation_id,
        "data": {"body": "answered", "final": True},
        "id": evt_id, "event_uid": evt_id,
        "writer_instance_uid": "replies", "stream_uid": "replies", "local_seq": 1,
    }


class EventDrainFixture(unittest.TestCase):

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="retire-driver-drain-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "vault" / "events" / "streams").mkdir(parents=True, exist_ok=True)
        (self.root / "vault" / "events" / "receipts").mkdir(parents=True, exist_ok=True)

    def _write_stream(self, name: str, events: list) -> None:
        p = self.root / "vault" / "events" / "streams" / f"{name}.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    def test_an_unanswered_thread_on_the_party_axis_reports_open(self) -> None:
        self._write_stream("party-unanswered", [_rr_event("evt_a_1", PARTY_UID)])
        ok, evidence = driver.observe_event_drain(self.root, "agent", "F1", PARTY_UID, AGENT_ROOT_UID)
        self.assertFalse(ok, evidence)
        self.assertIn("evt_a_1", evidence)

    def test_an_unanswered_thread_on_the_agent_root_axis_reports_open(self) -> None:
        self._write_stream("root-unanswered", [_rr_event("evt_b_1", AGENT_ROOT_UID)])
        ok, evidence = driver.observe_event_drain(self.root, "agent", "F1", PARTY_UID, AGENT_ROOT_UID)
        self.assertFalse(ok, evidence)
        self.assertIn("evt_b_1", evidence)

    def test_the_same_thread_answered_by_a_correlated_reply_reports_closed(self) -> None:
        self._write_stream("answered", [
            _rr_event("evt_c_1", PARTY_UID),
            _reply_event("evt_c_2", "evt_c_1"),
        ])
        ok, evidence = driver.observe_event_drain(self.root, "agent", "F1", PARTY_UID, AGENT_ROOT_UID)
        self.assertTrue(ok, evidence)

    def test_zero_threads_reports_closed(self) -> None:
        """Control: an empty bus must not be mistaken for an unscannable
        one — no threads at all is legitimately clean, not unknown."""
        ok, evidence = driver.observe_event_drain(self.root, "agent", "F1", PARTY_UID, AGENT_ROOT_UID)
        self.assertTrue(ok, evidence)

    def test_an_explicit_flag_and_proceed_naming_the_thread_reports_closed(self) -> None:
        self._write_stream("flagged", [_rr_event("evt_d_1", PARTY_UID)])
        ok, evidence = driver.observe_event_drain(
            self.root, "agent", "F1", PARTY_UID, AGENT_ROOT_UID,
            flagged_thread_ids=["evt_d_1"],
        )
        self.assertTrue(ok, evidence)
        self.assertIn("evt_d_1", evidence)

    def test_a_flag_naming_the_wrong_thread_still_reports_the_real_one_open(self) -> None:
        """Mutation, run rather than asserted: a flag must name the SPECIFIC
        thread it clears, not blanket-silence every open thread."""
        self._write_stream("partially-flagged", [_rr_event("evt_e_1", PARTY_UID)])
        ok, evidence = driver.observe_event_drain(
            self.root, "agent", "F1", PARTY_UID, AGENT_ROOT_UID,
            flagged_thread_ids=["evt_wrong_id"],
        )
        self.assertFalse(ok, evidence)
        self.assertIn("evt_e_1", evidence)


if __name__ == "__main__":
    unittest.main()
