"""AC3 (cee5190f, v1.92): a NEW row's shipped_at resolves from the
release's published event on the bus (data.published_at), never from a
frontmatter fallback. Existing rows' shipped_at is untouched by AC1's
preservation rule. Absent a published event, a NEW row's shipped_at is
null-honest, and the sort tolerates it.

Mechanism corrected at gauntlet: the original theory was that shipped_at
fell back to a release-plan's target_date. Measured, the actual source was
the frontmatter fallback (`shipped_at` or `created`) — v1.90.0's row
inherited `created: 2026-08-21`, which merely coincided with a plan's
target_date, while the real publish was 2026-08-22T23:44Z.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_deriver_shipped_at_source_v192
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import importlib.util

_spec = importlib.util.spec_from_file_location("deriver_ac3", TOOLS / "6342d0ca.py")
deriver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deriver)

HUB = "8dd772a0"
HUBS_MAP = {HUB: "tropo-governance"}


def _release(uid: str, version: str, created: str = "2026-08-21") -> dict:
    return {
        "file": None,
        "uid": uid,
        "version": version,
        "shipped_at": created,  # the OLD frontmatter-fallback value; must be ignored for NEW rows
        "capabilities_touched": [],
        "hub_summaries": {},
        "declared_subsystems": [HUB],
        "title": f"Tropo-OS v{version}",
    }


class ShippedAtSource(unittest.TestCase):

    def test_a_new_row_carries_the_published_events_value_not_frontmatter(self) -> None:
        release = _release("rel19002", "1.90.0", created="2026-08-21")
        published = {"1.90.0": "2026-08-22T23:44:19Z"}
        rows, _notes = deriver.build_registry_rows(
            [release], Path("."), HUBS_MAP, existing={}, published_by_version=published
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["shipped_at"], "2026-08-22T23:44:19Z")
        self.assertNotEqual(rows[0]["shipped_at"], "2026-08-21")

    def test_a_new_row_with_no_published_event_is_null_honest_and_notes_it(self) -> None:
        release = _release("rel18900", "1.89.0")
        rows, notes = deriver.build_registry_rows(
            [release], Path("."), HUBS_MAP, existing={}, published_by_version={}
        )
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["shipped_at"])
        self.assertTrue(any("rel18900" in n and "published" in n for n in notes))

    def test_the_sort_does_not_raise_on_a_null_shipped_at(self) -> None:
        release_null = _release("relnull01", "1.89.0")
        release_dated = _release("reldated1", "1.90.0")
        published = {"1.90.0": "2026-08-22T23:44:19Z"}
        try:
            rows, _notes = deriver.build_registry_rows(
                [release_null, release_dated], Path("."), HUBS_MAP,
                existing={}, published_by_version=published,
            )
        except TypeError as exc:
            self.fail(f"the sort raised on a null shipped_at: {exc}")
        self.assertEqual(len(rows), 2)

    def test_existing_rows_shipped_at_bytes_are_preserved_untouched(self) -> None:
        """AC1 preservation wins over AC3 re-resolution: an existing row's
        shipped_at is never rewritten even when a published event now
        exists for a version that didn't have one when the row was first
        minted."""
        existing_row = {
            "registry_uid": "deadbeef",
            "release_uid": "rel19003",
            "release_version": "1.90.0",
            "subsystem_uid": HUB,
            "subsystem_name": HUBS_MAP[HUB],
            "summary": None,
            "derived_from": "capabilities_touched",
            "shipped_at": "2026-08-21",  # the OLD frontmatter-fallback value
        }
        release = _release("rel19003", "1.90.0", created="2026-08-21")
        published = {"1.90.0": "2026-08-22T23:44:19Z"}
        existing = {("rel19003", HUB): existing_row}
        rows, _notes = deriver.build_registry_rows(
            [release], Path("."), HUBS_MAP, existing=existing, published_by_version=published
        )
        self.assertEqual(rows[0]["shipped_at"], "2026-08-21")

    def test_mutation_repointing_at_the_frontmatter_fallback_reds_this(self) -> None:
        """Teeth: if shipped_at were resolved from rel['shipped_at'] (the
        frontmatter fallback) instead of published_by_version, this
        assertion is exactly what catches it."""
        release = _release("relmut002", "1.90.0", created="2026-08-21")
        published = {"1.90.0": "2026-08-22T23:44:19Z"}
        rows, _notes = deriver.build_registry_rows(
            [release], Path("."), HUBS_MAP, existing={}, published_by_version=published
        )
        self.assertEqual(rows[0]["shipped_at"], published["1.90.0"])


class PublishedAtByVersionLoader(unittest.TestCase):
    """Light coverage of the bus-reading half, separate from the pure
    build_registry_rows tests above."""

    def test_absent_events_dir_returns_empty_map(self) -> None:
        result = deriver._load_published_at_by_version(Path("/nonexistent-vault-root-xyz"))
        self.assertEqual(result, {})

    def test_reads_a_real_published_event_shape_from_a_fixture_stream(self) -> None:
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="cee5190f-bus-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        streams = tmp / "vault" / "events" / "streams"
        streams.mkdir(parents=True)
        (streams / "fixture.jsonl").write_text(
            '{"specversion": "1.0", "type": "tropo.release.published", '
            '"source": "/tools/publish-release", "time": "2026-08-22T23:44:59Z", '
            '"source_uid": "15cae798", "lifecycle": "evergreen", '
            '"data": {"version": "1.90.0", "tag": "v1.90.0", '
            '"public_url": "https://example.invalid/v1.90.0", '
            '"published_at": "2026-08-22T23:44:19Z", '
            '"receipt_sha256": "abc123"}, "id": "evt_fixture_00000001"}\n',
            encoding="utf-8",
        )
        result = deriver._load_published_at_by_version(tmp)
        self.assertEqual(result, {"1.90.0": "2026-08-22T23:44:19Z"})


if __name__ == "__main__":
    unittest.main()
