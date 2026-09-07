#!/usr/bin/env python3
"""4e9ce4cc row 2/9 — the D6 per-row URL dialect, A4 lift collapse, A6
catalog-kept, and the frozen live-package set, pinned.

The URL shape is ONE FACT with five readers (generator, publish verifier,
build resolver, fresh-box pin, this suite) — the one-commit rule plus these
pins are the tripwire. Every url this suite asserts is built by the REAL
build_manifest against a synthetic base; no network, no fixtures that could
drift from the code under test.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "update_manifest_under_test", TOOLS / "tropo-generate-update-manifest.py"
)
assert _spec and _spec.loader
umm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(umm)

BASE = "https://example.supabase.co/storage/v1/object/public/releases/updates"
ROOT = "https://example.supabase.co/storage/v1/object/public/releases"


def _rel(version: str) -> dict:
    return {"release_version": version, "description": f"release {version}"}


class SyntheticCatalog:
    """The catalog slice that exercises every row class: live-package
    (1.85.1, 1.86.0), dead-package pre-box (1.87.0, 1.90.0–1.93.0), and the
    box era (1.94.0+). min_compatible follows the default stepwise rule."""

    RELEASES = [
        _rel("1.85.1"),
        _rel("1.86.0"),
        _rel("1.87.0"),
        _rel("1.90.0"),
        _rel("1.91.0"),
        _rel("1.92.0"),
        _rel("1.93.0"),
        _rel("1.94.0"),
        _rel("1.94.1"),
    ]

    @classmethod
    def manifest(cls) -> dict:
        return umm.build_manifest(list(cls.RELEASES), package_url_base=BASE)

    @classmethod
    def row(cls, version: str) -> dict:
        return next(u for u in cls.manifest()["updates"] if u["version"] == version)


class BoxUrlDialect(unittest.TestCase):
    """D6: box urls only for box releases (v1.94+); legacy live-package rows
    keep old urls; DEAD rows carry NO url (the gate skips url-less)."""

    def test_box_releases_carry_the_box_url(self) -> None:
        for version in ("1.94.0", "1.94.1"):
            with self.subTest(version=version):
                self.assertEqual(
                    SyntheticCatalog.row(version)["url"],
                    f"{ROOT}/v{version}/tropo-os-v{version}.zip",
                )

    def test_legacy_live_package_rows_keep_the_package_url(self) -> None:
        for version in ("1.85.1", "1.86.0"):
            with self.subTest(version=version):
                self.assertEqual(
                    SyntheticCatalog.row(version)["url"],
                    f"{BASE}/tropo-update-v{version}.zip",
                )

    def test_dead_rows_carry_no_url_at_all(self) -> None:
        """1.87–1.93: dead package (never back-filled — 4e9ce4cc OUT of
        scope), box present but not yet advertised (cutover ordering). A dead
        link here was the shipped defect — 92 of 94 urls were dead."""
        for version in ("1.87.0", "1.90.0", "1.91.0", "1.92.0", "1.93.0"):
            with self.subTest(version=version):
                self.assertNotIn("url", SyntheticCatalog.row(version))

    def test_the_frozen_live_package_set_is_the_bucket_verified_pair(self) -> None:
        """The constant and this pin change TOGETHER. Bucket truth was
        measured 2026-08-30 by HEADing every union-catalog package url:
        exactly 1.85.1 and 1.86.0 answered 200. If you are updating this
        because you shipped a new package, regenerate the measurement — do
        not add a version on faith."""
        self.assertEqual(umm.FROZEN_LIVE_PACKAGES, frozenset({"1.85.1", "1.86.0"}))

    def test_the_box_root_derives_from_the_package_base(self) -> None:
        self.assertEqual(umm._public_releases_root(BASE), ROOT)
        # A base without the /updates suffix passes through unchanged — the
        # helper must not mangle a root it does not recognize.
        self.assertEqual(umm._public_releases_root(ROOT), ROOT)


class LiftCollapse(unittest.TestCase):
    """A4: pending collapses to ONE lift entry with the OLDEST pending row's
    min_compatible — chained and lift end states are IDENTICAL (fleet-computed
    from real image manifests), so the chain is false precision."""

    def test_a_mid_chain_client_gets_exactly_one_entry(self) -> None:
        rendered = umm.render_for_client(SyntheticCatalog.manifest(), "1.90.0")
        self.assertEqual(len(rendered["updates"]), 1)
        lift = rendered["updates"][0]
        self.assertEqual(lift["version"], "1.94.1")
        # The oldest pending row for a 1.90.0 client is 1.91.0, whose
        # stepwise min_compatible is 1.90.0 — the lift inherits THAT floor,
        # not 1.94.0's own 1.94.0, or every mid-chain client would be told to
        # install intermediates that the lift just made unnecessary.
        self.assertEqual(lift["min_compatible"], "1.90.0")

    def test_a_current_client_gets_an_empty_pending_list(self) -> None:
        rendered = umm.render_for_client(SyntheticCatalog.manifest(), "1.94.1")
        self.assertEqual(rendered["updates"], [])

    def test_a_client_below_the_span_still_gets_migration_required(self) -> None:
        rendered = umm.render_for_client(
            SyntheticCatalog.manifest(), "1.80.0"
        )
        self.assertIn("migration_required", rendered)
        self.assertNotIn("updates", rendered)

    def test_malformed_client_version_stays_graceful(self) -> None:
        rendered = umm.render_for_client(SyntheticCatalog.manifest(), "not-semver")
        self.assertEqual(rendered["updates"], [])


class CatalogKept(unittest.TestCase):
    """A6: the catalog is NOT pruned by box-liveness — dead-box live-package
    releases stay with their package url, and minimum_supported stays put or
    old clients get retired-mechanism instructions."""

    def test_every_catalog_row_is_present(self) -> None:
        manifest = SyntheticCatalog.manifest()
        self.assertEqual(
            sorted(u["version"] for u in manifest["updates"]),
            sorted(r["release_version"] for r in SyntheticCatalog.RELEASES),
        )

    def test_minimum_supported_is_the_oldest_catalog_row(self) -> None:
        self.assertEqual(SyntheticCatalog.manifest()["minimum_supported"], "1.85.1")
        self.assertEqual(SyntheticCatalog.manifest()["current"], "1.94.1")

    def test_every_row_still_explains_its_compatibility(self) -> None:
        for row in SyntheticCatalog.manifest()["updates"]:
            with self.subTest(version=row["version"]):
                self.assertIn("min_compatible", row)
                self.assertIn(row["type"], ("release", "feature", "patch", "lift"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
