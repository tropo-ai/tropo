"""The completion verifier must read what the publisher actually writes.

Filed 2026-08-24 by argus-a156 while closing the v1.91 saga. Three of the five
bound facts in `tropo-verify-release-live.py` could never be observed on a real
release, and every existing test passed because every existing fixture was
hand-built in the shape the READER wanted rather than the shape the WRITER
emits:

  * the run-journal mirror is written by `_mirror_published_event_to_journal`
    with the key ``type``; `_first` matched only on ``event``
  * the payload hash is written by `_published_event_data` as
    ``receipt_sha256``; three of the four readers demanded
    ``publication_receipt_sha256``, a field NOTHING in this Studio writes
  * the bus check asserted "exactly one published event" over an append-only
    bus, so it got more wrong with every release shipped

These tests bind against the producers themselves, so a future change to either
side turns them red instead of drifting silently. This is the retro's §4 class
(`25c70440`) and the exact reason it was worth writing down: a green test over a
shape the producer never emits proves nothing.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from lib import release_closure  # noqa: E402


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFY = _load("verify_release_live_a156", "tropo-verify-release-live.py")
PUBLISH = _load("publish_release_a156", "tropo-publish-release.py")

RSHA = "7135f9b136827a4be860b61e602c41a3a5ef59f47c7285987724b00fa5d3a35b"


def _producer_event_data(version: str = "1.91.0") -> dict:
    """The payload the publisher really emits, from the publisher itself."""
    return PUBLISH._published_event_data(
        RSHA,
        {
            "version": version,
            "tag": "v%s" % version,
            "public_url": "https://example.invalid/releases/v%s" % version,
            "published_at": "2026-08-24T09:36:51Z",
        },
    )


class ProducerShapeIsReadable(unittest.TestCase):
    """The writer's real output must satisfy the reader's real check."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name)

    def _journal(self, rows) -> None:
        (self.run_dir / "run.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )

    def _mirrored_row(self, version: str = "1.91.0") -> dict:
        """Exactly the row `_mirror_published_event_to_journal` appends."""
        return {
            "type": release_closure.PUBLISHED_EVENT,
            "ts": "2026-08-24T09:40:11Z",
            "source": "/tools/publish-release",
            "data": _producer_event_data(version),
        }

    # --- the producer's own contract -------------------------------------

    def test_publisher_emits_receipt_sha256_not_publication_receipt_sha256(self):
        """If this flips, the reader's fallback is what must change, not this."""
        data = _producer_event_data()
        self.assertIn("receipt_sha256", data)
        self.assertNotIn("publication_receipt_sha256", data)
        self.assertIn("version", data, "version is what binds an event to a release")

    def test_mirror_writes_type_not_event(self):
        """The mirror copies the bus CloudEvent verbatim; `type` is its key."""
        source = (TOOLS / "tropo-publish-release.py").read_text(encoding="utf-8")
        marker = '"type": release_closure.PUBLISHED_EVENT,'
        self.assertIn(
            marker, source,
            "the journal mirror no longer writes `type:` — retire the fallback "
            "in tropo-verify-release-live._event_type if that is deliberate",
        )

    # --- the reader must see it ------------------------------------------

    def test_run_published_event_is_seen_in_the_producers_shape(self):
        self._journal([self._mirrored_row()])
        observers = VERIFY.build_observers(self.run_dir, [], "1.91.0")
        observation = observers["run_published_event"]()
        self.assertTrue(observation.present, observation.detail)
        self.assertEqual(observation.evidence_sha256, RSHA)

    def test_bus_published_event_is_seen_in_the_producers_shape(self):
        self._journal([])
        bus = [{"type": release_closure.PUBLISHED_EVENT, "data": _producer_event_data()}]
        observers = VERIFY.build_observers(self.run_dir, bus, "1.91.0")
        observation = observers["bus_published_event"]()
        self.assertTrue(observation.present, observation.detail)
        self.assertEqual(observation.evidence_sha256, RSHA)

    # --- and must still refuse -------------------------------------------

    def test_a_row_naming_no_event_at_all_is_not_seen(self):
        """The fallback widens which KEY is read, never what counts as a match."""
        self._journal([{"ts": "2026-08-24T09:40:11Z", "data": _producer_event_data()}])
        observers = VERIFY.build_observers(self.run_dir, [], "1.91.0")
        self.assertFalse(observers["run_published_event"]().present)

    def test_a_published_row_carrying_no_receipt_is_not_seen(self):
        row = self._mirrored_row()
        row["data"] = {k: v for k, v in row["data"].items() if k != "receipt_sha256"}
        self._journal([row])
        observers = VERIFY.build_observers(self.run_dir, [], "1.91.0")
        self.assertFalse(observers["run_published_event"]().present)

    def test_another_releases_bus_event_does_not_satisfy_this_release(self):
        """Compare like with like: the bus is append-only and holds them all."""
        self._journal([])
        bus = [
            {"type": release_closure.PUBLISHED_EVENT,
             "data": _producer_event_data("1.90.0")},
        ]
        observers = VERIFY.build_observers(self.run_dir, bus, "1.91.0")
        observation = observers["bus_published_event"]()
        self.assertFalse(observation.present, observation.detail)
        self.assertIn("for v1.91.0", observation.detail)

    def test_the_prior_release_no_longer_double_counts(self):
        """v1.91 read `found 2` because v1.90's event was on the same stream."""
        self._journal([])
        bus = [
            {"type": release_closure.PUBLISHED_EVENT,
             "data": _producer_event_data("1.90.0")},
            {"type": release_closure.PUBLISHED_EVENT,
             "data": _producer_event_data("1.91.0")},
        ]
        observers = VERIFY.build_observers(self.run_dir, bus, "1.91.0")
        self.assertTrue(observers["bus_published_event"]().present)

    def test_one_declared_rule_for_reading_an_event_name(self):
        """The verifier must consult release_closure, not a private copy."""
        self.assertEqual(
            VERIFY._event_type({"type": "x"}), release_closure.event_type({"type": "x"})
        )
        self.assertEqual(
            VERIFY._event_type({"event": "x"}), release_closure.event_type({"event": "x"})
        )


if __name__ == "__main__":
    unittest.main()
