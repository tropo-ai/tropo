#!/usr/bin/env python3
"""A slug-named composite dev-spec must be lockable through the REAL entry point.

THE INCIDENT, IN TWO ROUNDS, which is why this test exists at the locker rather
than at the planner.

Round 1: `tropo-lock-dev-spec.py` built the dev-spec's path as `<uid>.md`. Once
readable filenames flipped on, every newly minted dev-spec was born un-lockable,
and the refusal read "does not resolve" -- which sounds like a missing spec, not a
naming seam. The paired TEST-spec path in the same file had already been cured for
this exact bug, ~370 lines below.

Round 2: the cure routed `plan_dev_snapshot_transaction` -- THE PLANNER -- and left
`lock_dev_spec` -- THE LOCKER -- building its own bare path. `main()` calls the
locker, so the refusal fired before the cured code was ever reached and the fix
never ran on the real path. Caught by metis-g115 on the diff.

Her observation is the reusable one: *the fix lands where you are looking and not
one line over.* It was three-for-three that night across two agents. So this test
does not check a helper; it drives the LOCKER, the function `main()` actually
calls, with a real slug-named composite spec.

Argus A165, 2026-09-01.
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "vault" / "tools"))

_spec = importlib.util.spec_from_file_location(
    "lock_dev_spec_under_test", ROOT / "vault" / "tools" / "tropo-lock-dev-spec.py"
)
LOCK = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LOCK)

#: The refusal that means "I could not find the file", as opposed to any later
#: refusal about pipeline state. Matched on substring so unrelated wording drift
#: does not silently turn this test green.
NOT_FOUND = "does not resolve"


def _a_slug_named_spec() -> Path:
    """A real one from the corpus, never a hand-built fixture.

    A fixture named by hand would be a file in the shape the TEST expects rather
    than the shape the MINT produces -- the fixtures-in-the-reader's-own-shape
    defect that let round 1 survive its own suite.
    """
    files = ROOT / "vault" / "files"
    for p in sorted(files.glob("*-*.md")):
        stem = p.stem
        tail = stem.rsplit("-", 1)[-1]
        if len(tail) == 12 and all(c in "0123456789abcdef" for c in tail):
            return p
    raise unittest.SkipTest("no slug-named composite governed file in the corpus yet")


class TheLockerResolvesSlugNamedSpecs(unittest.TestCase):

    def test_the_locker_finds_a_slug_named_composite_spec(self) -> None:
        real = _a_slug_named_spec()
        uid = real.stem.rsplit("-", 1)[-1]
        with tempfile.TemporaryDirectory() as tmp:
            files_dir = Path(tmp) / "vault" / "files"
            files_dir.mkdir(parents=True)
            shutil.copy2(real, files_dir / real.name)

            code, message = LOCK.lock_dev_spec(uid, "regression-test", files_dir=files_dir)

            self.assertNotIn(
                NOT_FOUND, str(message),
                "the LOCKER could not find a slug-named composite dev-spec. This is "
                "round 2 of the bare-path defect returning: check whether a NEW bare "
                "`files_dir / f\"{uid}.md\"` has appeared beside a cured one.",
            )
            # It will still refuse -- the fixture holds one file and no pipeline
            # root. That is correct and is not what this test measures.
            self.assertNotEqual(
                code, 0, "a one-file fixture must not produce a real lock",
            )

    def test_a_genuinely_absent_uid_still_refuses_as_not_found(self) -> None:
        """THE CONTROL. Without it, a locker that never emitted this refusal at all
        would pass the assertion above while being just as broken."""
        with tempfile.TemporaryDirectory() as tmp:
            files_dir = Path(tmp) / "vault" / "files"
            files_dir.mkdir(parents=True)
            code, message = LOCK.lock_dev_spec(
                "ffffffffffff", "regression-test", files_dir=files_dir)
            self.assertIn(
                NOT_FOUND, str(message),
                "an absent uid must still be refused as not-found, or the assertion "
                "in the first test proves nothing.",
            )
            self.assertNotEqual(code, 0)

    def test_every_read_path_in_the_tool_routes_through_the_resolver(self) -> None:
        """The structural half: no bare `files_dir / f"{uid}.md"` READ survives.

        Creates are excluded -- `plan.create(...)` names a file that does not exist
        yet, so there is nothing to resolve.
        """
        src = (ROOT / "vault" / "tools" / "tropo-lock-dev-spec.py").read_text()
        offenders = []
        for lineno, line in enumerate(src.split("\n"), 1):
            if 'files_dir / f"{' not in line:
                continue
            stripped = line.strip()
            if stripped.startswith("#") or "plan.create" in line:
                continue
            if "bare = files_dir" in line or "bare_pair = files_dir" in line:
                continue  # the resolver's own bare-first attempt
            offenders.append(f"{lineno}: {stripped}")
        self.assertEqual(
            offenders, [],
            "a bare path is being used to READ a governed file; route it through "
            "_governed_path:\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
