#!/usr/bin/env python3
"""The kernel's UID shape regex and the vault's shape authority must agree.

WHY THIS EXISTS. `vault/tools/lib/governed_path.py` declares the authority:
`UID_SHAPES = frozenset({8, 12})`. `.tropo/scripts/lib/spec_substrate_refs.py`
carries `UID_RE`, a length literal that the test-spec validator gates
`triggered_by_dev_cycle` on. Two readers of one fact.

That pairing already failed once, on 2026-08-31: the Stage B flip moved the
authority to 12-hex and `UID_RE` stayed `^[0-9a-f]{8}$`, so the check would have
refused the activation uid the lock had just minted. It was found by hand, by
creating the first real governed file after the flip, and cured by talos-t55 the
same day.

A RUNTIME IMPORT IS THE WRONG CURE. The kernel (`.tropo/`) must not take a
runtime dependency on the vault tree -- that is the location contract, not a
style preference. So the two stay separate and THIS TEST is the gate that
notices when they disagree, the same shape as the boot-derivation fingerprints:
one fact, two readers, and something that fails loud on drift.

Add a shape to UID_SHAPES and this test goes red until UID_RE learns it.

Argus A165, 2026-08-31.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "vault" / "tools"))
sys.path.insert(0, str(ROOT / ".tropo" / "scripts"))

from lib import governed_path as authority  # noqa: E402
from lib import spec_substrate_refs as kernel  # noqa: E402


class UidShapeAuthorityParity(unittest.TestCase):
    """The declared authority and the kernel's regex describe the same shapes."""

    def test_every_authority_shape_is_accepted_by_the_kernel_regex(self) -> None:
        for length in sorted(authority.UID_SHAPES):
            sample = "a" * length
            self.assertTrue(
                kernel.UID_RE.fullmatch(sample),
                f"UID_SHAPES declares {length}-hex governed, but the kernel's "
                f"UID_RE ({kernel.UID_RE.pattern}) refuses it. This is the "
                f"2026-08-31 flip defect returning: the authority moved and the "
                f"regex did not.",
            )

    def test_the_kernel_regex_accepts_nothing_the_authority_does_not_declare(self) -> None:
        """The other direction. A regex looser than the authority silently
        admits a uid shape nothing mints, which is how a never-minted id enters
        an authority set (the TRUNCATE-FROM-TAIL class)."""
        for length in range(1, 25):
            if length in authority.UID_SHAPES:
                continue
            sample = "a" * length
            self.assertIsNone(
                kernel.UID_RE.fullmatch(sample),
                f"the kernel's UID_RE accepts {length}-hex, which UID_SHAPES "
                f"does not declare governed.",
            )

    def test_non_hex_is_refused_at_every_declared_length(self) -> None:
        for length in sorted(authority.UID_SHAPES):
            self.assertIsNone(kernel.UID_RE.fullmatch("z" * length))
            self.assertIsNone(kernel.UID_RE.fullmatch("A" * length))

    def test_the_control_would_notice(self) -> None:
        """Proof this test can fail: a regex bound to the wrong length must be
        refused by the same assertion the first test makes. Without this, a
        vacuous UID_RE (say, ``.*``) would pass everything above."""
        import re

        stale = re.compile(r"^[0-9a-f]{8}$")  # the pre-cure shape
        missed = [n for n in sorted(authority.UID_SHAPES) if not stale.fullmatch("a" * n)]
        self.assertTrue(
            missed,
            "the stale 8-only regex accepts every declared shape, so this "
            "parity test cannot distinguish cured from uncured and proves "
            "nothing.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
