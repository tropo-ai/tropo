#!/usr/bin/env python3
"""A message the drain cannot render is a message that was not delivered.

talos-t40, 2026-08-09.

FOUND BY LOSING FOUR RULINGS. `check-events` rendered `headline`, then
`subject_text`, then `body`, and nothing else. metis-g106 emits `text`; several
tools emit `summary`. So four substantive rulings addressed to me — the item-1
scope decision, the walk-label ruling, and Mike's no-v1.86.1 call — displayed as
blank lines in my own drain, and I only recovered them by opening the raw stream
because a message from Metis with nothing in it did not match how she writes.

MEASURED ACROSS THE LIVE LOG, not inferred: 394 messages carry `body`, 132
`body`+`headline`, 19 `body`+`summary`, 33 `summary` ONLY, 20 `text` ONLY. That
is 53 messages holding real content that the drain showed as empty, 12 of them
addressed to talos.

AND IT PROBABLY REWRITES A PIECE OF MY OWN LINEAGE. T38 recorded that Metis G99
terminally closed two of T37's dangling threads which "had shipped with EMPTY
BODIES, so there was no substance left to answer". A thread that carried its
content in `summary` would have looked exactly like that to the reader they were
judged by.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]

# check-events imports `lib.event_identity` relative to vault/tools/.
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location(
    "tropo_check_events_under_test", TOOLS / "tropo-check-events.py"
)
assert _spec and _spec.loader
check_events = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_events)


class EveryBodyShapeRenders(unittest.TestCase):
    def test_each_field_a_message_has_ever_used(self) -> None:
        for field in ("headline", "subject_text", "body", "text", "summary"):
            with self.subTest(field=field):
                self.assertEqual(
                    check_events._renderable_body({field: "the content"}),
                    "the content",
                )
                rendered = check_events._fmt({
                    "event_uid": "evt_test_00000001",
                    "type": "tropo.message.sent",
                    "time": "2026-08-09T18:00:00Z",
                    "data": {"from": "tester", field: "the content"},
                })
                self.assertIsInstance(rendered, str)
                self.assertIn("the content", rendered)

    def test_precedence_is_stable_when_several_are_present(self) -> None:
        """Deliberate, not incidental: the most specific field wins.

        `headline` exists to be the short form, so a message carrying both must
        show the headline rather than the first 120 characters of the essay.
        """
        self.assertEqual(
            check_events._renderable_body({"headline": "short", "body": "long"}),
            "short",
        )
        self.assertEqual(
            check_events._renderable_body({"body": "b", "summary": "s"}), "b"
        )

    def test_a_genuinely_empty_message_still_renders_empty(self) -> None:
        """204 messages in the log really do carry nothing. Do not invent text."""
        self.assertEqual(check_events._renderable_body({}), "")
        self.assertEqual(check_events._renderable_body({"from": "x"}), "")
        self.assertEqual(check_events._renderable_body({"body": ""}), "")


class AgainstTheRealLog(unittest.TestCase):
    """The claim is about this event log, so the test reads this event log."""

    def _messages(self):
        streams = ROOT / "vault" / "events" / "streams"
        if not streams.is_dir():
            self.skipTest("no event streams in this tree")
        for path in streams.glob("*.jsonl"):
            for line in path.read_text(errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if str(event.get("type", "")).startswith("tropo.message"):
                    yield event.get("data") or {}

    def test_no_message_carrying_content_renders_blank(self) -> None:
        lost = [
            data
            for data in self._messages()
            if not check_events._renderable_body(data)
            and (data.get("text") or data.get("summary"))
        ]
        self.assertEqual(
            lost,
            [],
            f"{len(lost)} message(s) carry content the drain would show as blank",
        )

    def test_control_the_old_renderer_really_did_lose_them(self) -> None:
        """Without this, the test above passes on a log that never had the shape.

        Reproduces the retired precedence and asserts it loses a positive number
        of real messages — so the fix is measured against a defect that existed
        rather than one I described.
        """
        def old(data):
            return data.get("headline") or data.get("subject_text") or str(data.get("body", ""))

        lost = [
            data
            for data in self._messages()
            if not old(data) and (data.get("text") or data.get("summary"))
        ]
        self.assertGreater(
            len(lost), 20, "the log no longer contains the shape this fix is for"
        )


class ReceiptsFollowRendering(unittest.TestCase):
    def test_renderer_failure_cannot_advance_cursor_or_receipts(self):
        event = {
            "event_uid": "evt_test_00000002",
            "type": "tropo.message.sent",
            "time": "2026-08-09T18:00:00Z",
            "data": {"from": "tester", "text": "must remain unseen"},
        }
        with (
            patch.object(check_events, "load_receipt_set", return_value=set()),
            patch.object(
                check_events,
                "_canonical_event_union_with_projection_warning",
                return_value=[event],
            ),
            patch.object(check_events, "_query_new_events", return_value=[event]),
            patch.object(check_events, "scan_unanswered_rr", return_value=[]),
            patch.object(
                check_events, "_fmt",
                side_effect=RuntimeError("planted renderer failure"),
            ),
            patch.object(check_events, "append_receipts") as receipts,
            patch.object(check_events, "save_cursor") as cursor,
            self.assertRaisesRegex(RuntimeError, "planted renderer failure"),
        ):
            check_events.run_once(
                "vela", "e97ac0ae", None, False, False
            )
        receipts.assert_not_called()
        cursor.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
