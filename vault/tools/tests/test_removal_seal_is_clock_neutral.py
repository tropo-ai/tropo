"""A removal must not freeze the next incremental index write (c0a47f6b).

`--remove` writes a seal. Every other write path stamps two virtual manifest
inputs into that seal — `@repo-clock` and `@wall-clock-date` — but `remove_one`
passed empty strings, and `_finalize_derivation_manifest` omits a virtual whose
value is falsy. So a removal produced a seal that was *missing* two entries the
next `--only` would compute and compare against.

`_incremental_manifest_blockers` allows deltas only in
`{source, source-absence, symlink-target}`. `virtual` is not in that set and can
never be exempted, so the next mint refused, naming clocks nobody had touched —
studio-wide, for everyone in the checkout. `tropo-recycle.py` drives `--remove`
and `tropo-mint-id.py` drives `--only`, so in practice: every recycle froze the
next mint.

These tests pin the invariant at the seam where it broke, rather than trying to
re-stage the whole end-to-end freeze — a full sandbox rebuild leaves untracked
derived artifacts that trip an earlier preflight and mask the property under
test.

Run: python3 vault/tools/tests/test_removal_seal_is_clock_neutral.py
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location(
    "rebuild_index_clock", str(TOOLS / "tropo-rebuild-index.py")
)
rebuild = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rebuild)

VIRTUAL_CLOCKS = {"@repo-clock", "@wall-clock-date"}


def _manifest_paths(manifest) -> set[str]:
    return {path for _kind, path, _mode, _sha in manifest}


class RemovalSealIsClockNeutralTests(unittest.TestCase):

    def _snapshot(self):
        return {"manifest": [("source", "vault/files/00000001.md", "100644", "a" * 64)]}

    def test_falsy_clocks_silently_drop_the_virtual_entries(self):
        """The mechanism itself: an empty clock value is omitted, not recorded.

        This is the behaviour that made a removal's seal structurally different
        from every other seal.
        """
        manifest = rebuild._finalize_derivation_manifest(
            self._snapshot(), [], repo_clock="", wall_clock_date=""
        )
        self.assertFalse(
            VIRTUAL_CLOCKS & _manifest_paths(manifest),
            "empty clocks must be understood to DROP the entries — if this ever "
            "starts recording them, the fix below is no longer load-bearing",
        )

    def test_real_clocks_are_recorded(self):
        manifest = rebuild._finalize_derivation_manifest(
            self._snapshot(), [], repo_clock="2026-08-01", wall_clock_date="2026-08-01"
        )
        self.assertTrue(VIRTUAL_CLOCKS <= _manifest_paths(manifest))

    def test_removal_supplies_real_clock_values(self):
        """The fix: a removal has clocks to stamp, so its seal is comparable."""
        entries = rebuild._derivation_clock_entries(ROOT)
        self.assertTrue(
            entries["repo_clock"].strip(),
            "a removal must record a repo clock or it drops the virtual entry",
        )
        self.assertTrue(
            entries["wall_clock_date"].strip(),
            "a removal must record a wall clock or it drops the virtual entry",
        )

    def test_clock_values_are_raw_not_prehashed(self):
        """Guards the mistake I nearly shipped.

        The manifest stores sha256(value). Carrying the SEALED entry forward
        would hash an already-hashed value, producing a fresh delta on every
        removal — the same freeze wearing different clothes. Both values must be
        raw ISO dates, exactly what the gardener hands the full path.
        """
        import re
        entries = rebuild._derivation_clock_entries(ROOT)
        for name, value in entries.items():
            self.assertIsNotNone(
                re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
                f"{name} must be a raw ISO date, got {value!r}",
            )
            self.assertIsNone(
                re.fullmatch(r"[0-9a-f]{64}", value),
                f"{name} looks like a sha256 — it must be the raw value",
            )

    def test_removal_seal_matches_what_the_next_read_expects(self):
        """End to end at the seam: no virtual delta between the two paths.

        A removal's manifest and a normal derivation's manifest must agree on
        the virtual inputs, because `_incremental_manifest_blockers` treats any
        virtual difference as unexemptable.
        """
        snapshot = self._snapshot()
        removal = rebuild._finalize_derivation_manifest(
            snapshot, [], **rebuild._derivation_clock_entries(ROOT)
        )
        normal = rebuild._finalize_derivation_manifest(
            snapshot, [],
            repo_clock=rebuild._derivation_clock_entries(ROOT)["repo_clock"],
            wall_clock_date=rebuild._derivation_clock_entries(ROOT)["wall_clock_date"],
        )
        removal_virtuals = {
            (path, sha) for kind, path, _m, sha in removal if kind == "virtual"
        }
        normal_virtuals = {
            (path, sha) for kind, path, _m, sha in normal if kind == "virtual"
        }
        self.assertEqual(
            removal_virtuals, normal_virtuals,
            "a removal's virtual inputs must be identical to a normal "
            "derivation's, or the next --only refuses on a clock delta",
        )
        self.assertTrue(VIRTUAL_CLOCKS <= {p for p, _ in removal_virtuals})


class ClockRolloverMustNotFreezeMintingTests(unittest.TestCase):
    """A day rolling over must not freeze every incremental write (c0a47f6b).

    `@wall-clock-date` was a COMPARED manifest entry, so the first mint after
    midnight refused with nothing edited by anyone, naming a clock. This fired
    live at 2026-08-02T00:20Z while minting an unrelated brief — four hours
    after it was documented and consciously deferred.

    Time passing is not a semantic input change: a date advancing does not make
    previously derived rows wrong, it only means age-derived fields are due a
    refresh. The clocks are still RECORDED for provenance, just not compared.
    """

    def test_clock_deltas_are_not_blockers(self):
        prior = (
            ("source", "vault/files/00000001.md", "100644", "a" * 64),
            ("virtual", "@wall-clock-date", "virtual", "b" * 64),
            ("virtual", "@repo-clock", "virtual", "c" * 64),
        )
        current = (
            ("source", "vault/files/00000001.md", "100644", "a" * 64),
            ("virtual", "@wall-clock-date", "virtual", "d" * 64),  # midnight
            ("virtual", "@repo-clock", "virtual", "e" * 64),
        )
        with unittest.mock.patch.object(
            rebuild.index_surfaces, "load_trusted_derivation_manifest",
            return_value=prior,
        ):
            blockers = rebuild._incremental_manifest_blockers(
                ROOT, current, {"vault/files/00000001.md"}
            )
        self.assertEqual(
            blockers, [],
            "a clock advancing must never freeze an incremental write",
        )

    def test_runtime_change_is_still_a_blocker(self):
        """The exemption is scoped. A different interpreter genuinely can parse
        sources differently, so @python-runtime stays a blocker."""
        prior = (("virtual", "@python-runtime", "virtual", "a" * 64),)
        current = (("virtual", "@python-runtime", "virtual", "b" * 64),)
        with unittest.mock.patch.object(
            rebuild.index_surfaces, "load_trusted_derivation_manifest",
            return_value=prior,
        ):
            blockers = rebuild._incremental_manifest_blockers(ROOT, current, set())
        self.assertEqual(blockers, ["@python-runtime"])

    def test_real_source_change_is_still_a_blocker(self):
        """The protection this gate exists for is untouched: --only must not
        certify rows it did not re-derive."""
        prior = (("source", "vault/files/00000002.md", "100644", "a" * 64),)
        current = (("source", "vault/files/00000002.md", "100644", "b" * 64),)
        with unittest.mock.patch.object(
            rebuild.index_surfaces, "load_trusted_derivation_manifest",
            return_value=prior,
        ):
            blockers = rebuild._incremental_manifest_blockers(
                ROOT, current, {"vault/files/00000001.md"}
            )
        self.assertEqual(blockers, ["vault/files/00000002.md"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
