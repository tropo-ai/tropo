"""AC1 (cee5190f, v1.92): a subsystem-registry row's registry_uid is STABLE
under (release_uid, subsystem_uid) -- existing rows preserved byte-for-byte
across re-runs, new rows minted once, running the deriver twice in
immediate succession produces a zero diff.

Measured motivation: one new row previously churned 144 existing uids
(metis-g111, 2026-08-23) because the row constructor minted a fresh
registry_uid on every run with no lookup-first step.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_deriver_stable_identity_v192
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import importlib.util

_spec = importlib.util.spec_from_file_location("deriver_ac1", TOOLS / "6342d0ca.py")
deriver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deriver)

HUB = "8dd772a0"
HUBS_MAP = {HUB: "tropo-governance"}


def _release(uid: str, version: str, hub: str = HUB) -> dict:
    return {
        "file": None,
        "uid": uid,
        "version": version,
        "shipped_at": "",
        "capabilities_touched": [],
        "hub_summaries": {},
        "declared_subsystems": [hub],
        "title": f"Tropo-OS v{version}",
    }


class StableIdentity(unittest.TestCase):

    def test_existing_row_is_preserved_byte_for_byte_across_a_rerun(self) -> None:
        releases = [_release("rel00001", "1.90.0")]
        rows1, _notes1 = deriver.build_registry_rows(
            releases, Path("."), HUBS_MAP, existing={}, published_by_version={}
        )
        self.assertEqual(len(rows1), 1)
        first_uid = rows1[0]["registry_uid"]

        existing = {("rel00001", HUB): rows1[0]}
        rows2, _notes2 = deriver.build_registry_rows(
            releases, Path("."), HUBS_MAP, existing=existing, published_by_version={}
        )
        self.assertEqual(rows2, rows1, "a re-run must reproduce the existing row byte-for-byte")
        self.assertEqual(rows2[0]["registry_uid"], first_uid, "must not re-mint an existing pair")

    def test_one_new_release_does_not_churn_existing_rows(self) -> None:
        """The measured motivation, at small scale: one new row must not
        touch any other release's already-minted registry_uid."""
        old_releases = [_release(f"rel{i:05d}", "1.80.0") for i in range(5)]
        rows0, _notes0 = deriver.build_registry_rows(
            old_releases, Path("."), HUBS_MAP, existing={}, published_by_version={}
        )
        existing = {(r["release_uid"], r["subsystem_uid"]): r for r in rows0}
        original_uids = {r["release_uid"]: r["registry_uid"] for r in rows0}

        releases_plus_one = old_releases + [_release("relnewx1", "1.90.0")]
        rows1, _notes1 = deriver.build_registry_rows(
            releases_plus_one, Path("."), HUBS_MAP, existing=existing, published_by_version={}
        )
        self.assertEqual(len(rows1), 6)
        for row in rows1:
            if row["release_uid"] in original_uids:
                self.assertEqual(
                    row["registry_uid"], original_uids[row["release_uid"]],
                    f"{row['release_uid']}'s registry_uid churned on an unrelated new row",
                )

    def test_a_pair_that_no_longer_derives_is_carried_forward_not_dropped(self) -> None:
        """An existing pair the current corpus no longer derives (its
        capability's member_of edge changed, say) must still appear in the
        output — the deriver only ever adds, it never subtracts."""
        stale_row = {
            "registry_uid": "deadbeef",
            "release_uid": "relold001",
            "release_version": "1.70.0",
            "subsystem_uid": HUB,
            "subsystem_name": HUBS_MAP[HUB],
            "summary": None,
            "derived_from": "capabilities_touched",
            "shipped_at": "2026-01-01",
        }
        existing = {("relold001", HUB): stale_row}
        # relold001 is not even in this run's release scan any more.
        rows, _notes = deriver.build_registry_rows(
            [], Path("."), HUBS_MAP, existing=existing, published_by_version={}
        )
        self.assertIn(stale_row, rows)

    def test_immediate_rerun_against_its_own_output_is_a_zero_diff(self) -> None:
        releases = [_release("relzero1", "1.90.0"), _release("relzero2", "1.91.0")]
        rows1, _n1 = deriver.build_registry_rows(
            releases, Path("."), HUBS_MAP, existing={}, published_by_version={}
        )
        existing = {(r["release_uid"], r["subsystem_uid"]): r for r in rows1}
        rows2, _n2 = deriver.build_registry_rows(
            releases, Path("."), HUBS_MAP, existing=existing, published_by_version={}
        )
        self.assertEqual(rows1, rows2)

    def test_mutation_reintroducing_per_run_minting_reds_this(self) -> None:
        """Teeth: the exact class this AC exists to prevent. If the row
        constructor minted a fresh registry_uid on every call instead of
        looking up `existing` first, this assertion is what catches it."""
        releases = [_release("relmut001", "1.90.0")]
        rows1, _n1 = deriver.build_registry_rows(
            releases, Path("."), HUBS_MAP, existing={}, published_by_version={}
        )
        existing = {("relmut001", HUB): rows1[0]}
        rows2, _n2 = deriver.build_registry_rows(
            releases, Path("."), HUBS_MAP, existing=existing, published_by_version={}
        )
        self.assertEqual(
            rows1[0]["registry_uid"], rows2[0]["registry_uid"],
            "a second run minted a NEW registry_uid for an already-registered pair",
        )

    def test_new_mints_still_route_through_the_adr050_chokepoint(self) -> None:
        """Stability comes from lookup-first, never from bypassing the
        minter for genuinely new pairs."""
        releases = [_release("relmint01", "1.90.0")]
        rows, _notes = deriver.build_registry_rows(
            releases, Path("."), HUBS_MAP, existing={}, published_by_version={}
        )
        uid = rows[0]["registry_uid"]
        # Follows the AUTHORITY mint length since the Stage B flip (12-hex
        # composite, 2026-08-31); never a second shape definition.
        from lib.governed_path import MINT_HEX_LEN as _MINT_LEN
        self.assertEqual(len(uid), _MINT_LEN)
        self.assertTrue(all(c in "0123456789abcdef" for c in uid.lower()))


if __name__ == "__main__":
    unittest.main()
