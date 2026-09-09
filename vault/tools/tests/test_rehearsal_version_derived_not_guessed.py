"""The rehearsal's --version defaults to the run's OWN version, never a typed
literal.

v1.95 close (talos-t64, 2026-09-07). `cmd_rehearse`'s `--version` argument
defaulted to the hard-coded string `"v1.89.0"`. An operator who ran the
rehearsal without pinning a version -- the normal case, since the run already
knows its own version -- got that stale literal written into the scorecard.
G123's third fire paste hit exactly this on the real v1.95.0 run: the card
named v1.89.0, the fire compared it against the candidate it was actually
firing, and refused.

The realistic shape matters: a rehearsal runs BEFORE any fire, so there is no
`tropo.release.published` receipt yet and no `release_version`/`version`
field stamped onto any journal row. The one thing that exists from the
moment the run opens is `release_entry_uid` on the `run_created` row (proven
against the real v1.95 run: it is on row 1, written 2026-09-06T02:02:08Z,
almost 33 hours before the fire) -- which resolves to the release entry's own
`release_version:` frontmatter. These fixtures reproduce exactly that shape:
`run_created` + `release_entry_uid`, nothing else, matching the real run and
not a friendlier fixture.

`--vault` names a STUDIO ROOT (a `vault/files/` subdir plus a sibling
`.tropo/`), not a `vault/` folder itself -- `load_refusal_baseline` and the
release-entry resolver both read paths relative to it. The refusal baseline
carries a self-consistent digest, so each fixture root gets a byte-for-byte
copy of the real one rather than a hand-built stand-in that would have to
recompute the hash.
"""

from __future__ import annotations

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

REAL_BASELINE = STUDIO_ROOT / ".tropo" / "release-refusal-baseline.json"
REAL_SCHEMA_DIR = STUDIO_ROOT / "vault" / "schema"


def _load_facade():
    spec = importlib.util.spec_from_file_location(
        "tropo_release_facade_version_default_under_test", TOOLS / "tropo-release.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FixtureStudioCase(unittest.TestCase):
    """A minimal studio root: enough for cmd_rehearse to run against fakes,
    nothing borrowed from the real one except the self-verifying baseline."""

    def setUp(self) -> None:
        self.facade = _load_facade()
        self.tmp = Path(tempfile.mkdtemp(prefix="rehearsal-version-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "vault" / "files").mkdir(parents=True)
        (self.tmp / ".tropo").mkdir()
        shutil.copy(REAL_BASELINE, self.tmp / ".tropo" / "release-refusal-baseline.json")
        shutil.copytree(REAL_SCHEMA_DIR, self.tmp / "vault" / "schema")
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()

    def _write_release_entry(self, uid: str, version: str) -> None:
        (self.tmp / "vault" / "files" / f"{uid}.md").write_text(
            "---\nuid: %s\ntype: release\nrelease_version: %s\n---\n# release\n"
            % (uid, version),
            encoding="utf-8",
        )

    def _write_run_created(self, run_uid: str, entry_uid: str | None = None) -> None:
        # The real shape: only run_created carries release_entry_uid, and it
        # is the FIRST row -- no published receipt, no explicit version field
        # anywhere, because nothing has fired yet.
        data = {"saga_id": f"release:{run_uid}", "pipeline_run_uid": run_uid}
        if entry_uid is not None:
            data["release_entry_uid"] = entry_uid
        (self.run_dir / "run.jsonl").write_text(
            json.dumps({"event": "run_created", "data": data}) + "\n",
            encoding="utf-8",
        )

    def _rehearse(self, extra_args: list[str] | None = None) -> int:
        return self.facade.main(
            ["--vault", str(self.tmp), "rehearse", "--run-dir", str(self.run_dir)]
            + (extra_args or []))

    def _card(self) -> dict:
        return json.loads(
            (self.run_dir / "one-prompt-rehearsal-scorecard.json").read_text())


class PreFireRehearsalDerivesFromTheReleaseEntry(_FixtureStudioCase):
    """The path G123 actually hit: rehearsing before any fire has happened."""

    def test_omitted_version_resolves_to_the_release_entrys_own_version(self) -> None:
        self._write_release_entry("f0159bee0000", "1.95.0")
        self._write_run_created("f015af000abc", "f0159bee0000")

        rc = self._rehearse()
        self.assertEqual(rc, self.facade.EXIT_OK)

        version = self._card()["release_version"]
        self.assertEqual(
            version, "1.95.0",
            "the omitted --version must resolve to the run's OWN release, "
            "not a typed-in guess; got %r" % (version,))

    def test_it_is_not_the_old_hard_coded_literal(self) -> None:
        """The literal shape of the original defect: a DIFFERENT real version
        must not come back as v1.89.0 by construction."""
        self._write_release_entry("f0159bee0001", "2.3.1")
        self._write_run_created("f015af000abd", "f0159bee0001")

        self.assertEqual(self._rehearse(), self.facade.EXIT_OK)
        version = self._card()["release_version"]
        self.assertNotEqual(version, "v1.89.0")
        self.assertEqual(version, "2.3.1")


class ExplicitVersionStillOverrides(_FixtureStudioCase):
    """An operator who DOES pin --version keeps that power; only the omitted
    case changed."""

    def test_explicit_flag_wins_over_a_derivable_but_different_version(self) -> None:
        # A release entry present but naming a DIFFERENT version, so a pass
        # here proves the explicit flag wins over derivation, not that
        # derivation happened to agree with it.
        self._write_release_entry("f0159bee0002", "9.9.9")
        self._write_run_created("f015af000abe", "f0159bee0002")

        rc = self._rehearse(["--version", "5.5.5"])
        self.assertEqual(rc, self.facade.EXIT_OK)
        self.assertEqual(self._card()["release_version"], "5.5.5")


class NothingDerivableFallsToALoudPlaceholder(_FixtureStudioCase):
    """No release entry, no journal fact: the rehearsal must not silently
    invent a number that could pass for a real version."""

    def test_fallback_is_unmistakably_not_a_real_version(self) -> None:
        self._write_run_created("f015af000abf")  # no release_entry_uid at all

        rc = self._rehearse()
        self.assertEqual(rc, self.facade.EXIT_OK)
        version = self._card()["release_version"]
        self.assertEqual(version, self.facade._UNBOUND_REHEARSAL_VERSION)
        self.assertIn("unbound", version)


if __name__ == "__main__":
    unittest.main()
