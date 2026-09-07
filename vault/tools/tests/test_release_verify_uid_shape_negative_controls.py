#!/usr/bin/env python3
"""Argus's standing ask (release-gate negative controls): the accepts-both
widening (`UID_SHAPES={8,12}` in `lib/governed_path.py`) made
`lib.release_verify.validate_receipt`'s `release_run_uid` check accept a
12-hex composite uid it used to wrongly refuse. A widened FINDER is
unambiguously correct; a widened REFUSER also stops refusing whatever the
narrow pattern happened to exclude, and nobody wrote those exclusions down.
`VerifyRefusal` here is fail-closed on the one act that cannot be taken back
(deb77758) -- exactly the class of gate this ask is about.

NOT added to `test_ac07_verify_receipt_vocabulary.py`: that file's fixture
uses a stale `package_sha256` key against the current `candidate_sha256`
field (pre-existing, unrelated rot -- 13 of its 21 tests are already red on
a clean stash baseline) and is not the place to anchor a new regression pin.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_verify as rv  # noqa: E402

RUN = "a1b2c3d4"
DIGEST = "a" * 64


def receipt(**over):
    base = {
        "receipt_kind": rv.RECEIPT_KIND,
        "instrument": "full-validator",
        "release_run_uid": RUN,
        "candidate_sha256": DIGEST,
        "verdict": "pass",
        "executor_or_attester": "talos-t58",
        "execution_mode": "machine",
        "evidence_ref": "vault/pipeline-runs/r/full-validator.md",
        "started_at": "2026-09-01T14:00:00Z",
        "completed_at": "2026-09-01T14:05:00Z",
    }
    base.update(over)
    return base


class SanityFixtureIsValid(unittest.TestCase):
    """If this fails, every test below is meaningless -- confirm the fixture
    itself parses before trusting any refusal it produces."""

    def test_the_baseline_receipt_validates(self) -> None:
        parsed = rv.validate_receipt(receipt())
        self.assertEqual(parsed.release_run_uid, RUN)


class UidShapeNegativeControls(unittest.TestCase):
    MALFORMED_RUN_UIDS = (
        # "" excluded: an empty release_run_uid is caught by the earlier
        # missing-required-field guard, not the shape check -- a real
        # refusal, just a different one than this class pins.
        "a1b2c3d",       # 7 hex
        "a1b2c3d4e",     # 9 hex
        "a1b2c3d4e5f6a", # 13 hex
        "a1b2c3dz",      # 8 chars, not hex
        "A1B2C3D4",      # valid length, uppercase -- the shared predicate
                         # (is_governed_uid_shape) is lowercase-only
        "../../etc/passwd",
        "a1b2 c3d4",     # embedded whitespace
    )

    def test_malformed_release_run_uids_are_refused(self) -> None:
        for bad in self.MALFORMED_RUN_UIDS:
            with self.subTest(uid=bad):
                with self.assertRaises(rv.VerifyRefusal) as caught:
                    rv.validate_receipt(receipt(release_run_uid=bad))
                self.assertIn("not a governed uid", str(caught.exception))

    def test_a_valid_12_hex_composite_run_uid_is_accepted_by_the_uid_gate(self) -> None:
        """Positive control: a 12-hex run uid must clear the shape check --
        proves accepts-both is real here, not that the gate refuses
        everything. It still fails the FIELD-CONSISTENCY check downstream in
        assert_ready_to_publish (a receipt naming a different run than the
        one being verified), which is a separate, correct refusal -- so this
        asserts only that validate_receipt itself (parse + shape) succeeds."""
        composite = "a1b2c3d4e5f6"
        self.assertEqual(len(composite), 12)
        parsed = rv.validate_receipt(receipt(release_run_uid=composite))
        self.assertEqual(parsed.release_run_uid, composite)


if __name__ == "__main__":
    unittest.main()
