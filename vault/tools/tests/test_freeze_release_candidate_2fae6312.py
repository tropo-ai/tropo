#!/usr/bin/env python3
"""The freeze is decided on the bytes and the receipts, or it is refused.

Dev-spec 2fae6312 step 4's verdict producer. This is the command named in
`verification_command:` on node 7de2c49f, so these cases are the difference
between that node's verdict being a measurement and being whatever the
operator typed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"

_spec = importlib.util.spec_from_file_location(
    "tropo_freeze_release_candidate", TOOLS / "tropo-freeze-release-candidate.py"
)
freeze = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = freeze
_spec.loader.exec_module(freeze)

RUN = "934436ca"
SAGA = "release:934436ca"


class FreezeDecisionTests(unittest.TestCase):
    def build(self, *, receipts=None, invalidate=False, already_frozen=False,
              mutate_bytes=False, wrong_run=False) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="freeze-"))
        self.addCleanup(shutil.rmtree, tmp, True)

        candidate = tmp / "tropo-1.89.0.zip"
        candidate.write_bytes(b"pretend package bytes")
        sha = hashlib.sha256(candidate.read_bytes()).hexdigest()

        rows = [
            {"event": "tropo.release.scope_locked",
             "data": {"saga_id": SAGA, "pipeline_run_uid": RUN}},
            {"event": "tropo.release.candidate_built",
             "data": {"pipeline_run_uid": RUN, "candidate_sha256": sha,
                      "candidate_path": str(candidate)}},
        ]
        for step in (receipts if receipts is not None else list(freeze.INSTRUMENTS)):
            rows.append({
                "event": "verification_receipt", "step": step,
                "data": {
                    "pipeline_run_uid": "somebody-else" if wrong_run else RUN,
                    "candidate_sha256": sha,
                    "instrument_step_uid": step,
                    "verdict": "pass",
                    "receipt_uid": "r-" + step,
                },
            })
        if invalidate:
            rows.append({"event": "tropo.release.candidate_invalidated",
                         "data": {"pipeline_run_uid": RUN, "candidate_sha256": sha,
                                  "reason": "prose fix"}})
        if already_frozen:
            rows.append({"event": "tropo.release.package_frozen",
                         "data": {"pipeline_run_uid": RUN, "package_sha256": sha}})

        (tmp / "run.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        if mutate_bytes:
            candidate.write_bytes(b"pretend package bytes, edited after the walk")
        return tmp

    def decide(self, run_dir: Path):
        return freeze.decide(run_dir, run_dir / "tropo-1.89.0.zip")

    def test_four_receipts_and_unchanged_bytes_earn_the_freeze(self):
        payload, refusal = self.decide(self.build())
        self.assertIsNone(refusal)
        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual(len(payload["instrument_receipts"]), 4)

    def test_a_byte_change_after_the_instruments_ran_refuses(self):
        """The defect the node exists to prevent, exercised end to end."""
        payload, refusal = self.decide(self.build(mutate_bytes=True))
        self.assertIsNotNone(refusal)
        self.assertIn("recorded", refusal)
        self.assertEqual(payload["verdict"], "fail")
        self.assertNotEqual(payload["rehashed_sha256"], payload["candidate_sha256"])

    def test_three_receipts_is_a_fail_not_a_rounding_error(self):
        for absent in freeze.INSTRUMENTS:
            with self.subTest(absent=absent):
                present = [u for u in freeze.INSTRUMENTS if u != absent]
                payload, refusal = self.decide(self.build(receipts=present))
                self.assertIsNotNone(refusal)
                self.assertIn(absent, refusal)
                self.assertEqual(payload["verdict"], "fail")

    def test_a_live_invalidation_blocks_the_freeze(self):
        _, refusal = self.decide(self.build(invalidate=True))
        self.assertIsNotNone(refusal)
        self.assertIn("invalidation", refusal)

    def test_a_second_freeze_is_a_supersession_not_a_freeze(self):
        _, refusal = self.decide(self.build(already_frozen=True))
        self.assertIsNotNone(refusal)
        self.assertIn("supersession", refusal)

    def test_receipts_from_another_run_do_not_count(self):
        _, refusal = self.decide(self.build(wrong_run=True))
        self.assertIsNotNone(refusal)
        self.assertIn("absent", refusal)

    def test_a_missing_candidate_refuses(self):
        run_dir = self.build()
        (run_dir / "tropo-1.89.0.zip").unlink()
        _, refusal = self.decide(run_dir)
        self.assertIn("no candidate", refusal)

    def test_the_four_instruments_are_the_declared_four(self):
        self.assertEqual(
            sorted(freeze.INSTRUMENTS),
            sorted(["4262d5fa", "a0f2bea8", "bc6b17ec", "c6b61fb9"]),
        )


class ExitCodeTests(unittest.TestCase):
    def test_earned_freeze_exits_zero_and_refusal_exits_one(self):
        helper = FreezeDecisionTests("run")
        helper.addCleanup = lambda *a, **k: None

        earned = helper.build()
        self.assertEqual(
            freeze.main(["--run-dir", str(earned),
                         "--candidate", str(earned / "tropo-1.89.0.zip")]),
            freeze.EXIT_FROZEN,
        )

        refused = helper.build(mutate_bytes=True)
        self.assertEqual(
            freeze.main(["--run-dir", str(refused), "--candidate",
                         str(refused / "tropo-1.89.0.zip"), "--quiet"]),
            freeze.EXIT_REFUSED,
        )
        shutil.rmtree(earned, ignore_errors=True)
        shutil.rmtree(refused, ignore_errors=True)

    def test_a_missing_run_directory_is_misuse(self):
        self.assertEqual(
            freeze.main(["--run-dir", "/tmp/not-a-run", "--candidate", "/tmp/x.zip"]),
            freeze.EXIT_MISUSE,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
