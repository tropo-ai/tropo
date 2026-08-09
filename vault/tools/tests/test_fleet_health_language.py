#!/usr/bin/env python3
"""Does the fleet-health check describe a consequence that is actually true?

WHY THIS EXISTS (metis-g101, 2026-08-04). This check ran at boot step 5.1.9 in
front of a human and announced that a lineage "CANNOT produce a successor".
That had stopped being true when G100 converted birth from
refuse-on-failed-check to record-and-proceed. Argus was reported as unable to
be reborn all morning; a probe birth against that exact lineage succeeded.

Then the FIRST correction was wrong too, in the other direction. It claimed the
successor would be "born provisional" -- true for argus, but on a lineage whose
predecessor carried an unknown agent_class the mint issued a completely CLEAN
entry with no findings. The check's walk is stricter than birth's, and some of
what it reports birth does not consult at all.

The lesson underneath is the one this whole arc keeps paying for: THE REPORT AND
THE BEHAVIOUR ARE TWO HALVES OF ONE THING, and when only one half is
machine-guaranteed the other drifts. So this file refuses to let them drift
apart -- the same test that asserts what the check SAYS also runs the mint and
asserts what actually HAPPENS.

WHAT IS PINNED, and deliberately nothing more:

  * the check never tells a human a birth is blocked
  * a lineage the check flags can, in fact, still be born
  * "hard deletion" is never asserted as a cause (see
    test_history_only_diagnosis.py for the other end of that same defect)

What is NOT pinned: whether the successor comes out provisional. That is the
mint's business to report, not this check's to predict, and pinning it here is
exactly the over-claim that made the first correction wrong.
"""

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
VALIDATOR = REPO / "vault" / "tools" / "tropo-validate.py"
MINT = REPO / "vault" / "tools" / "tropo-activate.py"
REAL_LIB = REPO / "vault" / "tools" / "lib"


def _load_validator():
    spec = importlib.util.spec_from_file_location("tv_under_test", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except SystemExit:
        pass
    return module


def _git(repo: pathlib.Path, *argv: str) -> None:
    subprocess.run(["git", *argv], cwd=str(repo), capture_output=True, check=True)


class FleetHealthFixture(unittest.TestCase):
    """A scratch studio carrying one deliberately defective lineage."""

    def setUp(self):
        self.studio = pathlib.Path(tempfile.mkdtemp(prefix="fleethealth-"))
        (self.studio / "vault" / "files").mkdir(parents=True)
        (self.studio / "vault" / "agents").mkdir(parents=True)
        (self.studio / "vault" / "tools").mkdir(parents=True)
        # The check imports lib.authority_chain from the studio it is pointed at.
        (self.studio / "vault" / "tools" / "lib").symlink_to(REAL_LIB)

        # A predecessor whose agent_class is not a real class. The lineage walk
        # rejects it; the mint does not consult it. That divergence is the point.
        (self.studio / "vault" / "files" / "aaaa1111.md").write_text(
            "\n".join(
                [
                    "---",
                    "uid: aaaa1111",
                    "type: activation",
                    "agent: probeagent",
                    "generation: P3",
                    "status: retired",
                    "agent_class: notaclass",
                    "activated_by: mike",
                    "activated_at: 2026-07-01T09:00:00Z",
                    "---",
                    "",
                    "# probeagent P3",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        _git(self.studio, "init", "-q", "-b", "main")
        _git(self.studio, "config", "user.email", "test@example.invalid")
        _git(self.studio, "config", "user.name", "test")
        _git(self.studio, "add", "-A")
        _git(self.studio, "commit", "-qm", "seed")

        self.findings, self.checked, self.blocked = _load_validator(
        ).check_every_agent_can_still_boot(self.studio)

    def tearDown(self):
        shutil.rmtree(self.studio, ignore_errors=True)


class TestTheCheckDoesNotOverstate(FleetHealthFixture):
    def test_the_fixture_actually_produces_a_finding(self):
        """Guard the guard. A silent fixture would make every test below vacuous."""
        self.assertEqual(self.blocked, 1, self.findings)
        self.assertTrue(self.findings)

    def test_no_finding_claims_the_birth_is_blocked(self):
        """The regression that put a false alarm in a human's startup signal."""
        for finding in self.findings:
            lowered = finding.lower()
            self.assertNotIn("cannot boot", lowered, finding)
            self.assertNotIn("cannot produce a successor", lowered, finding)

    def test_no_finding_asserts_hard_deletion(self):
        """Paired with test_history_only_diagnosis.py — same defect, other end."""
        for finding in self.findings:
            self.assertNotIn("hard deletion", finding.lower(), finding)

    def test_a_flagged_lineage_can_still_actually_be_born(self):
        """The half that keeps the report welded to reality.

        If this ever fails, the check has become right and the language wrong,
        and the fix is to restore the alarm — not to soften this assertion.
        """
        proc = subprocess.run(
            [
                sys.executable, str(MINT),
                "--agent", "probeagent",
                "--authorized-by", "mike",
                "--agent-class", "executive",
                "--vault-root", str(self.studio),
            ],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        issued = json.loads(proc.stdout.strip())
        self.assertTrue(issued.get("activation_uid"), issued)
        self.assertEqual(issued.get("generation"), "P4", issued)


if __name__ == "__main__":
    unittest.main(verbosity=2)
