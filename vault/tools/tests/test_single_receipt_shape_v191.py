#!/usr/bin/env python3
"""v1.91 S2 AC4 (3fb41c99) — ONE receipt shape for the four instruments.

Argus A155's scope ruling (2026-08-23), correcting his own first read: this
is not a new AC or a v1.92 candidate. AC4's own locked behaviour clause
names both shapes verbatim -- "v1.90 required both a verification_receipt
{step, candidate_sha256} AND a release-verification-receipt {receipt_kind,
package_sha256, ten fields} for the same four instruments; satisfying one
left the other blind" -- and this locked file is AC4's own declared verify
command. It never existed; that absence was the defect (the same class as
S4's AC4/AC8: a locked command naming a file nobody wrote).

WHY THIS TEST DRIVES PRODUCTION ENTRY POINTS, NOT HAND-BUILT RECEIPTS. Every
prior freeze-tool test (test_freeze_release_candidate_2fae6312,
test_one_prompt_release_2fae6312, test_q9_harness_evidence, this spec's own
test_single_reader_v191) hand-constructed the receipt dict its fixture
needed. That is precisely how the producer/consumer mismatch survived: the
freeze gate's own tests always passed because they fed it exactly the shape
it expected, never the shape the real writer (9e7003b1.py's
emit_release_verification_receipt) actually produces. Mike's ruling: AC4 is
built to completion, not to green, and the instrument is a test that proves
the two sides were ever run together for real.

This test calls the REAL writer for all four instruments, then the REAL
freeze tool's decide() on the receipts THAT WRITER produced -- nothing here
constructs a receipt dict by hand. Mutation clause: revert either side to
its pre-unification shape (the writer's old package_sha256 binding, or the
freeze tool's old instrument_step_uid-keyed verification_receipt read) and
this test goes RED, because the two would disagree again exactly as they did
in production.
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
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load("ac4_runtime", "9e7003b1.py")
release_verify = _load("ac4_release_verify", "lib/release_verify.py")
freeze = _load("ac4_freeze", "tropo-freeze-release-candidate.py")

RUN = "934436ca"


class ProductionDoorReceiptShapeTests(unittest.TestCase):
    """Drives candidate -> four real verify receipts -> freeze, end to end."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ac4-receipt-shape-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

        self.candidate = self.tmp / "tropo-1.91.0.zip"
        self.candidate.write_bytes(b"AC4 production-door proof bytes")
        self.sha = hashlib.sha256(self.candidate.read_bytes()).hexdigest()

        (self.tmp / "run.jsonl").write_text(
            json.dumps({
                "event": "tropo.release.candidate_built",
                "data": {"pipeline_run_uid": RUN, "candidate_sha256": self.sha,
                         "candidate_path": str(self.candidate)},
            }) + "\n",
            encoding="utf-8",
        )

        # The minimal pr dict emit_release_verification_receipt actually
        # reads: frontmatter.pipeline gates it to release runs only,
        # frontmatter.uid is the run identity bound onto every receipt.
        self.pr = {"frontmatter": {"pipeline": runtime.RELEASE_PIPELINE_ROOT_UID,
                                   "uid": RUN}}

    def _write_all_four_receipts(self, verdict="pass"):
        written = []
        for step_uid in sorted(release_verify.INSTRUMENT_NODES.values()):
            wrote = runtime.emit_release_verification_receipt(
                self.tmp, self.pr, step_uid, "sa.test-harness", verdict)
            written.append((step_uid, wrote))
        return written

    def test_the_real_writer_and_the_real_freeze_gate_agree(self):
        """The production door, closed: write four real receipts, freeze."""
        for step_uid, wrote in self._write_all_four_receipts():
            self.assertTrue(wrote, f"emit_release_verification_receipt did not "
                                   f"write for step {step_uid}")

        # Prove the writer used the ONE declared name, not the dev-pipeline's
        # generic collision.
        rows = [json.loads(l) for l in (self.tmp / "run.jsonl").read_text().splitlines()]
        receipt_rows = [r for r in rows if r.get("event") == release_verify.RECEIPT_KIND]
        self.assertEqual(len(receipt_rows), 4)
        self.assertTrue(
            all(r.get("event") != "verification_receipt" for r in rows),
            "a receipt landed under the dev-pipeline's generic name",
        )
        for row in receipt_rows:
            data = row.get("data") or {}
            self.assertEqual(data.get("candidate_sha256"), self.sha)
            self.assertNotIn(
                "package_sha256", data,
                "the receipt still carries package_sha256 -- the pre-unification "
                "field survived",
            )

        # The real freeze tool, on exactly the receipts the real writer
        # produced -- no fixture stands between them.
        payload, refusal = freeze.decide(self.tmp, self.candidate)
        self.assertIsNone(refusal, f"freeze refused against real receipts: {refusal!r}")
        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual(len(payload["instrument_receipts"]), 4)

    def test_the_writer_refuses_before_any_candidate_exists(self):
        """No active candidate, no receipt -- the honest refusal, not a crash."""
        empty = Path(tempfile.mkdtemp(prefix="ac4-no-candidate-"))
        self.addCleanup(shutil.rmtree, empty, True)
        (empty / "run.jsonl").write_text("", encoding="utf-8")
        step_uid = next(iter(release_verify.INSTRUMENT_NODES.values()))
        with self.assertRaises(runtime.ContractError):
            runtime.emit_release_verification_receipt(
                empty, self.pr, step_uid, "sa.test-harness", "pass")

    def test_a_non_release_run_is_untouched(self):
        """Every other step and every dev run: a cost with no matching harm."""
        pr = {"frontmatter": {"pipeline": "not-the-release-pipeline", "uid": RUN}}
        step_uid = next(iter(release_verify.INSTRUMENT_NODES.values()))
        wrote = runtime.emit_release_verification_receipt(
            self.tmp, pr, step_uid, "sa.test-harness", "pass")
        self.assertFalse(wrote)
        rows = [json.loads(l) for l in (self.tmp / "run.jsonl").read_text().splitlines()]
        self.assertEqual(
            len(rows), 1,
            "a non-release pipeline run still got a receipt written",
        )

    def test_a_failing_instrument_still_writes_and_still_blocks_the_freeze(self):
        instruments = sorted(release_verify.INSTRUMENT_NODES.values())
        for step_uid in instruments[:-1]:
            self.assertTrue(runtime.emit_release_verification_receipt(
                self.tmp, self.pr, step_uid, "sa.test-harness", "pass"))
        self.assertTrue(runtime.emit_release_verification_receipt(
            self.tmp, self.pr, instruments[-1], "sa.test-harness", "fail"))

        payload, refusal = freeze.decide(self.tmp, self.candidate)
        self.assertIsNotNone(refusal)
        self.assertEqual(payload["verdict"], "fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
