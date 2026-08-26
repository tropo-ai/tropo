"""AC2 (cee5190f, v1.92): a shipped release whose derivation reaches zero
hubs produces exactly one WARN naming the release uid and version, and the
run completes normally -- warn-safe (deb77758), never a refusal.

Measured motivation: v1.90.0 derived zero hubs and the loop over the empty
set recorded nothing anywhere; the absence surfaced only when a downstream
validator check (R11) fired at the next strict run.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_deriver_zero_hub_warn_v192
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import importlib.util

_spec = importlib.util.spec_from_file_location("deriver_ac2", TOOLS / "6342d0ca.py")
deriver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deriver)

HUB = "8dd772a0"
HUBS_MAP = {HUB: "tropo-governance"}


def _release(uid: str, version: str, declared_subsystems=None) -> dict:
    return {
        "file": None,
        "uid": uid,
        "version": version,
        "shipped_at": "",
        "capabilities_touched": [],
        "hub_summaries": {},
        "declared_subsystems": declared_subsystems or [],
        "title": f"Tropo-OS v{version}",
    }


class ZeroHubWarn(unittest.TestCase):

    def test_a_zero_hub_release_produces_one_named_warn_and_no_row(self) -> None:
        release = _release("rel19000", "1.90.0")  # nothing resolves -- v1.90.0's own shape
        rows, notes = deriver.build_registry_rows(
            [release], Path("."), HUBS_MAP, existing={}, published_by_version={}
        )
        self.assertEqual(rows, [])
        zero_hub_notes = [n for n in notes if "rel19000" in n and "zero" in n]
        self.assertEqual(len(zero_hub_notes), 1, "expected exactly one note, not none or many")
        self.assertTrue(zero_hub_notes[0].startswith("[WARN]"))
        self.assertIn("1.90.0", zero_hub_notes[0])

    def test_exit_code_unchanged_from_the_normal_path(self) -> None:
        """WARN-safe pins the criterion: it records, it does not refuse.
        build_registry_rows itself never raises or signals failure for a
        zero-hub release -- there is no exception path to assert against,
        which is the point."""
        release = _release("rel19001", "1.90.0")
        try:
            deriver.build_registry_rows(
                [release], Path("."), HUBS_MAP, existing={}, published_by_version={}
            )
        except Exception as exc:  # noqa: BLE001 - the assertion IS "nothing raises"
            self.fail(f"a zero-hub release must not raise: {exc}")

    def test_the_run_completes_normally_a_zero_hub_release_never_blocks_others(self) -> None:
        release_ok = _release("relok0001", "1.91.0", declared_subsystems=[HUB])
        release_zero = _release("relzero01", "1.90.0")
        rows, _notes = deriver.build_registry_rows(
            [release_zero, release_ok], Path("."), HUBS_MAP,
            existing={}, published_by_version={},
        )
        self.assertEqual(len(rows), 1, "the zero-hub release must not block the good one")
        self.assertEqual(rows[0]["release_uid"], "relok0001")

    def test_making_the_warn_a_refusal_would_also_fail_this(self) -> None:
        """The criterion pins warn-safe, not just noise: a mutation that
        turned the zero-hub branch into a raise (refusal) instead of a
        recorded note would be caught by test_exit_code_unchanged; a
        mutation that silenced the note entirely is caught here."""
        release = _release("relbare01", "1.90.0")
        _rows, notes = deriver.build_registry_rows(
            [release], Path("."), HUBS_MAP, existing={}, published_by_version={}
        )
        self.assertTrue(
            any("relbare01" in n for n in notes),
            "a zero-hub release must be named in a note, not silently skipped",
        )


if __name__ == "__main__":
    unittest.main()
