"""tropo-ship.py: the five ways it must say NO, and the one way it says GO.

Mike, 2026-09-07: "I get deny, deny, deny, deny, deny... Our process is not
reliable." The measurement behind this file: the release machinery is 21,051
lines, of which 1,598 read the world. tropo-ship.py is 167 lines and answers
the only question the fire needs answered, from artifacts that already exist.

Every arm below is a MUTATION of the real v1.95.0 run journal: the fixture is
the thing that actually happened, and each control removes exactly one fact and
asserts the verdict flips. A control that cannot flip proves nothing, which is
the rule this studio has been re-learning all year.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from lib import tropo_roots  # noqa: E402  (after sys.path)
SHIP = TOOLS / "tropo-ship.py"
DIGEST = "97c2aa1d4e48bb6b1192580cf89522597f9e3ea26dbfd5c70146ff9ff09ef334"
RUN_UID = "f015af4a6a0a"


def _rows():
    """A journal with the shape the real run had: one live candidate, four
    passing instrument receipts on it, one signoff by a non-driver."""
    rows = [
        {"event": "tropo.release.candidate_built", "ts": "2026-09-06T16:28:15Z",
         "actor": "a1b8c2d4",
         "data": {"release_run_uid": RUN_UID, "candidate_sha256": DIGEST}},
    ]
    for i, name in enumerate(("full-validator", "release-harness",
                              "external-test", "cold-walk")):
        rows.append({"event": "step_completed", "ts": f"2026-09-06T17:0{i}:00Z",
                     "actor": "metis-g123", "data": {}})
        rows.append({"event": "release-verification-receipt",
                     "ts": f"2026-09-06T17:0{i}:01Z", "actor": "metis-g123",
                     "data": {"receipt_kind": "release-verification-receipt",
                              "instrument": name, "release_run_uid": RUN_UID,
                              "candidate_sha256": DIGEST, "verdict": "pass"}})
    rows.append({"event": "human_signoff", "ts": "2026-09-07T01:46:34Z",
                 "actor": "mike-maziarz", "step": "c6b61fb9",
                 "data": {"verdict": "accepted", "signed_by": "mike-maziarz"}})
    return rows


class ShipDecision(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ship-"))
        self.zip = self.tmp / "tropo-os-v1.95.0.zip"
        # bytes whose sha256 IS the digest the journal names: build the fixture
        # around the real artifact when it is present, else skip the hash arm.
        # Derived, never hard-coded. An absolute machine path in the shipped
        # tool corpus is precisely what build-no-absolute-paths refuses, and
        # this line WAS that refusal: metis-g124 hit it on 2026-09-07 running
        # the gate unattended against the tree, with the leak already on main.
        # TROPO_TEST_RELEASE_ZIP overrides for a checkout whose releases dir
        # resolves elsewhere (see the clone-depth defect, task f0159f5c5663);
        # absent either way the hash arm skips exactly as it always did.
        override = os.environ.get("TROPO_TEST_RELEASE_ZIP")
        self.real = (Path(override) if override else
                     tropo_roots.RELEASES_DIR / "v1.95.0" / "dist" / "tropo-os-v1.95.0.zip")

    def run_ship(self, rows, candidate=None):
        run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=self.tmp))
        (run_dir / "run.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n")
        cand = candidate or self.real
        out = subprocess.run(
            [sys.executable, str(SHIP), "--run-dir", str(run_dir),
             "--candidate", str(cand)],
            capture_output=True, text=True)
        return out.returncode, (out.stdout + out.stderr).strip()

    def test_go_when_all_three_facts_hold(self):
        if not self.real.is_file():
            self.skipTest("the real v1.95.0 artifact is not on this machine")
        rc, out = self.run_ship(_rows())
        self.assertEqual(rc, 0, out)
        self.assertIn("GO", out)
        self.assertIn("mike-maziarz", out)

    def test_no_when_an_instrument_receipt_is_absent(self):
        rows = [r for r in _rows()
                if (r.get("data") or {}).get("instrument") != "cold-walk"]
        rc, out = self.run_ship(rows)
        self.assertEqual(rc, 1)
        self.assertIn("cold-walk", out)
        self.assertIn("no receipt", out)

    def test_no_when_the_latest_receipt_failed(self):
        rows = _rows()
        rows.append({"event": "release-verification-receipt",
                     "ts": "2026-09-06T18:00:00Z", "actor": "metis-g123",
                     "data": {"receipt_kind": "release-verification-receipt",
                              "instrument": "cold-walk", "release_run_uid": RUN_UID,
                              "candidate_sha256": DIGEST, "verdict": "fail"}})
        rc, out = self.run_ship(rows)
        self.assertEqual(rc, 1)
        self.assertIn("'fail'", out)

    def test_a_later_pass_governs_an_earlier_fail(self):
        """The v1.90 lesson: re-running an instrument after a cure is the only
        way a failed one ever passes."""
        if not self.real.is_file():
            self.skipTest("the real v1.95.0 artifact is not on this machine")
        rows = _rows()
        fail = {"event": "release-verification-receipt", "ts": "2026-09-06T16:59:00Z",
                "actor": "metis-g123",
                "data": {"receipt_kind": "release-verification-receipt",
                         "instrument": "cold-walk", "release_run_uid": RUN_UID,
                         "candidate_sha256": DIGEST, "verdict": "fail"}}
        rows.insert(1, fail)
        rc, out = self.run_ship(rows)
        self.assertEqual(rc, 0, out)

    def test_no_when_nobody_independent_said_go(self):
        rows = [r for r in _rows() if r.get("event") != "human_signoff"]
        rc, out = self.run_ship(rows)
        self.assertEqual(rc, 1)
        self.assertIn("did not drive", out)

    def test_no_when_the_signer_also_drove_the_run(self):
        """The independence check: an agent cannot sign off on its own run."""
        rows = [r for r in _rows() if r.get("event") != "human_signoff"]
        rows.append({"event": "human_signoff", "ts": "2026-09-07T01:46:34Z",
                     "actor": "metis-g123", "step": "c6b61fb9",
                     "data": {"verdict": "accepted"}})
        rc, out = self.run_ship(rows)
        self.assertEqual(rc, 1)
        self.assertIn("did not drive", out)

    def test_no_when_the_candidate_was_invalidated(self):
        rows = _rows()
        rows.append({"event": "tropo.release.candidate_invalidated",
                     "ts": "2026-09-07T03:00:00Z", "actor": "metis-g123",
                     "data": {"release_run_uid": RUN_UID,
                              "candidate_sha256": DIGEST, "reason": "rebuild"}})
        rc, out = self.run_ship(rows)
        self.assertEqual(rc, 1)
        self.assertIn("no live candidate", out)

    def test_no_when_the_bytes_are_not_the_bytes(self):
        other = self.tmp / "not-the-package.zip"
        other.write_bytes(b"different bytes entirely")
        rc, out = self.run_ship(_rows(), candidate=other)
        self.assertEqual(rc, 1)
        self.assertIn("not the bytes", out)
        self.assertIn(hashlib.sha256(b"different bytes entirely").hexdigest()[:12], out)

    def test_it_prints_one_reason_not_a_list(self):
        """An operator fixes one thing. Two refusals in one breath is how a
        release becomes a scavenger hunt."""
        rows = [r for r in _rows()
                if (r.get("data") or {}).get("instrument") != "cold-walk"
                and r.get("event") != "human_signoff"]
        rc, out = self.run_ship(rows)
        self.assertEqual(rc, 1)
        self.assertEqual(len([l for l in out.splitlines() if l.strip()]), 1, out)


if __name__ == "__main__":
    unittest.main()
