"""Most-restricted capture-segment ordering and refusal properties."""
from __future__ import annotations

import itertools
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.capture_segment import (  # noqa: E402
    CaptureSegmentError,
    CaptureSegmentErrorCode,
    SegmentAttestation,
    derive_capture_segment,
)
from lib.group_registry import GroupResolver, Result  # noqa: E402


TEAM = "a0000001"
PRIVATE_ALICE = "a0000002"
PRIVATE_BOB = "a0000003"
UNKNOWN = "afffffff"


def resolver() -> GroupResolver:
    return GroupResolver(
        {
            TEAM: {
                "group_uid": TEAM,
                "direct_member_uids": ("11111111", "22222222"),
                "effective_member_uids": ("11111111", "22222222"),
                "wider_group_uids": (),
            },
            PRIVATE_ALICE: {
                "group_uid": PRIVATE_ALICE,
                "direct_member_uids": ("11111111",),
                "effective_member_uids": ("11111111",),
                "wider_group_uids": (TEAM,),
            },
            PRIVATE_BOB: {
                "group_uid": PRIVATE_BOB,
                "direct_member_uids": ("22222222",),
                "effective_member_uids": ("22222222",),
                "wider_group_uids": (TEAM,),
            },
        },
        revision="fixture",
    )


class CaptureSegmentTests(unittest.TestCase):
    def test_team_only_and_duplicate_segment_values_choose_team(self) -> None:
        attestation = derive_capture_segment(
            ("chunk-a", "chunk-b"),
            {"chunk-a": TEAM, "chunk-b": TEAM},
            resolver(),
        )
        self.assertIsInstance(attestation, SegmentAttestation)
        self.assertEqual(attestation.segment, TEAM)
        self.assertEqual(attestation.ranked_chunk_uids, ("chunk-a", "chunk-b"))
        with self.assertRaises(TypeError):
            SegmentAttestation(("chunk-a",), TEAM)
        with self.assertRaises(Exception):
            attestation.segment = PRIVATE_ALICE

    def test_comparable_team_private_always_chooses_private(self) -> None:
        expected_uids = {"team-chunk", "private-chunk"}
        for order in itertools.permutations(expected_uids):
            with self.subTest(order=order):
                attestation = derive_capture_segment(
                    order,
                    {
                        "team-chunk": TEAM,
                        "private-chunk": PRIVATE_ALICE,
                    },
                    resolver(),
                )
                self.assertEqual(attestation.segment, PRIVATE_ALICE)
                self.assertEqual(attestation.ranked_chunk_uids, order)

    def test_incomparable_private_leaves_refuse_in_every_order(self) -> None:
        codes = set()
        for order in itertools.permutations(("alice-chunk", "bob-chunk")):
            with self.assertRaises(CaptureSegmentError) as raised:
                derive_capture_segment(
                    order,
                    {
                        "alice-chunk": PRIVATE_ALICE,
                        "bob-chunk": PRIVATE_BOB,
                    },
                    resolver(),
                )
            codes.add(raised.exception.code)
        self.assertEqual(
            codes,
            {CaptureSegmentErrorCode.MOST_RESTRICTED_NOT_UNIQUE},
        )

    def test_missing_malformed_unknown_and_resolver_errors_are_typed(self) -> None:
        cases = (
            (
                ("chunk-a",),
                {},
                resolver(),
                CaptureSegmentErrorCode.SEGMENT_LOOKUP_FAILED,
            ),
            (
                ("chunk-a",),
                {"chunk-a": ""},
                resolver(),
                CaptureSegmentErrorCode.SEGMENT_INVALID,
            ),
            (
                ("chunk-a",),
                {"chunk-a": UNKNOWN},
                resolver(),
                CaptureSegmentErrorCode.RESOLVER_FAILED,
            ),
        )
        for ranked, mapping, authority, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(CaptureSegmentError) as raised:
                    derive_capture_segment(ranked, mapping, authority)
                self.assertEqual(raised.exception.code, code)

        class BrokenResolver:
            def is_equal_or_wider(self, wider: str, narrower: str) -> Result:
                raise RuntimeError("authority offline")

        with self.assertRaises(CaptureSegmentError) as raised:
            derive_capture_segment(
                ("chunk-a",),
                {"chunk-a": TEAM},
                BrokenResolver(),
            )
        self.assertEqual(
            raised.exception.code,
            CaptureSegmentErrorCode.RESOLVER_FAILED,
        )

    def test_empty_duplicate_and_multiple_candidates_refuse(self) -> None:
        for ranked, code in (
            ((), CaptureSegmentErrorCode.EMPTY_CAPTURE),
            (
                ("chunk-a", "chunk-a"),
                CaptureSegmentErrorCode.CHUNK_UID_DUPLICATE,
            ),
        ):
            with self.subTest(code=code):
                with self.assertRaises(CaptureSegmentError) as raised:
                    derive_capture_segment(
                        ranked,
                        {"chunk-a": TEAM},
                        resolver(),
                    )
                self.assertEqual(raised.exception.code, code)

        class CyclicResolver:
            def is_equal_or_wider(self, wider: str, narrower: str) -> Result:
                return Result.success(True)

        with self.assertRaises(CaptureSegmentError) as raised:
            derive_capture_segment(
                ("chunk-a", "chunk-b"),
                {"chunk-a": TEAM, "chunk-b": PRIVATE_ALICE},
                CyclicResolver(),
            )
        self.assertEqual(
            raised.exception.code,
            CaptureSegmentErrorCode.MOST_RESTRICTED_NOT_UNIQUE,
        )


if __name__ == "__main__":
    unittest.main()
