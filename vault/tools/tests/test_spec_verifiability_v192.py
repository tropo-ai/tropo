"""The spec-verifiability checker must fire on the two real stoppages of
2026-08-25, and must NOT fire on the one that looked like them.

Built by argus-a157 on Mike's standing direction that every stoppage leave the
machinery stronger. A new governance instrument is worth nothing until it has
been shown to go red against the substrate that motivated it — a green check
over a blind mechanism is worse than no check, because it converts an open
question into a false answer.

So the two known-positives are replayed here from their real historical text,
not from a fixture authored in the checker's shape:

  STOPPAGE 1  a committed test target that never existed, whose runner reports
              success on a missing path (5b608d28 AC4, pre-2026-08-25).
  STOPPAGE 2  a criterion verifiable only against the release artifact that
              would contain its own spec (1a478c48 AC5, retired 2026-08-25).

And the known-NEGATIVE, which matters just as much: 1a478c48 AC4 says
"copy-pasteable in a bare shipped box" and is NOT release-coupled, because its
verification is automated and resolves at dev scope. The checker's first version
flagged it, and a false finding in a governance check teaches people to skip the
check.

    python3 -m pytest -q vault/tools/tests/test_spec_verifiability_v192.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location(
    "spec_verifiability", TOOLS / "tropo-check-spec-verifiability.py"
)
sv = importlib.util.module_from_spec(_spec)
# Registered before exec: @dataclass resolves annotations through
# sys.modules[cls.__module__], and an unregistered module makes that None.
sys.modules["spec_verifiability"] = sv
_spec.loader.exec_module(sv)


def _write_spec(root: Path, uid: str, criteria) -> Path:
    """A locked dev-spec on disk, in the real frontmatter shape."""
    (root / "vault" / "files").mkdir(parents=True, exist_ok=True)
    import yaml

    body = yaml.safe_dump(
        {
            "uid": uid,
            "type": "dev-spec",
            "status": "locked",
            "title": "fixture",
            "acceptance_criteria": criteria,
        },
        sort_keys=False,
    )
    path = root / "vault" / "files" / f"{uid}.md"
    path.write_text("---\n" + body + "---\n\n# fixture\n")
    return path


class StoppageOneThePhantomTarget(unittest.TestCase):
    """A committed test target that never existed."""

    def test_a_missing_pytest_target_is_found_and_named_silent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_spec(root, "aaaaaaaa", [{
                "id": "AC4",
                "behavior": "every REQUIRED_FACT SEEN on the live run",
                "verify": {
                    "method": "automated",
                    "command": "python3 -m pytest -q vault/tools/tests/"
                               "test_completion_reads_producers_v192.py",
                    "evidence": "every fact SEEN, exit 0",
                },
            }])
            reports = sv.run(root)
        kinds = [f.kind for r in reports for f in r.findings]
        self.assertIn(
            "PHANTOM-TARGET-SILENT", kinds,
            "a pytest command naming a file that does not exist must be found, "
            "and must be marked as the SILENT variant — pytest exits 0 on a "
            "missing path, which is why this went unnoticed",
        )

    def test_the_finding_says_the_criterion_passes_vacuously(self) -> None:
        """Naming the mechanism is the point; 'file missing' understates it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_spec(root, "aaaaaaaa", [{
                "id": "AC4",
                "verify": {"method": "automated",
                           "command": "python3 -m pytest -q vault/tools/tests/nope.py"},
            }])
            detail = [f.detail for r in sv.run(root) for f in r.findings][0]
        self.assertIn("vacuously", detail)

    def test_a_target_that_exists_is_not_flagged(self) -> None:
        """The other direction, against the real corpus."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = "vault/tools/tests/test_spec_verifiability_v192.py"
            (root / "vault" / "tools" / "tests").mkdir(parents=True)
            (root / real).write_text("# present\n")
            _write_spec(root, "aaaaaaaa", [{
                "id": "AC1",
                "verify": {"method": "automated",
                           "command": f"python3 -m pytest -q {real}"},
            }])
            self.assertEqual([], [f for r in sv.run(root) for f in r.findings])

    def test_a_non_vacuous_runner_is_reported_but_not_marked_silent(self) -> None:
        """`python3 <missing>` exits nonzero, so it fails loudly rather than
        passing — a real finding, but a different and lesser one."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_spec(root, "aaaaaaaa", [{
                "id": "AC1",
                "verify": {"method": "automated",
                           "command": "python3 vault/tools/tests/nope.py"},
            }])
            kinds = [f.kind for r in sv.run(root) for f in r.findings]
        self.assertIn("PHANTOM-TARGET", kinds)
        self.assertNotIn("PHANTOM-TARGET-SILENT", kinds)


class StoppageTwoTheLayerCycle(unittest.TestCase):
    """A criterion verifiable only against the release containing its spec."""

    #: The retired 1a478c48 AC5, verbatim from the substrate before removal.
    RETIRED_AC5 = {
        "id": "AC5",
        "behavior": "THE FIRST-USE WALK PASSES — the ship gate and the bar's "
                    "instrument (studio memory 74e9676b). A stranger agent in a "
                    "customer-shaped studio (built from the v1.92 candidate box, "
                    "not this checkout) takes one trivial spec through the entire "
                    "loop unaided.",
        "verify": {
            "method": "manual",
            "command": "conducted First-Use Walk — customer-shaped studio "
                       "extracted from the v1.92 candidate (sha named on the "
                       "record); conductor independent of builder and author",
            "evidence": "Walk record with verdict PASS naming the candidate sha.",
        },
    }

    def test_the_retired_ac5_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_spec(root, "bbbbbbbb", [self.RETIRED_AC5])
            kinds = [f.kind for r in sv.run(root) for f in r.findings]
        self.assertIn(
            "RELEASE-COUPLED", kinds,
            "the criterion that deadlocked the v1.92 endgame must be caught: "
            "lock needs done needs walk needs box needs lock",
        )

    def test_the_finding_tells_the_author_where_to_put_it_instead(self) -> None:
        """A governance finding that names no remedy is a complaint."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_spec(root, "bbbbbbbb", [self.RETIRED_AC5])
            detail = [f.detail for r in sv.run(root)
                      for f in r.findings if f.kind == "RELEASE-COUPLED"][0]
        self.assertIn("ship criterion", detail)

    def test_the_known_negative_is_not_flagged(self) -> None:
        """1a478c48 AC4 — automated, dev-scope, resolves — says 'shipped box'
        in its prose. The checker's FIRST version flagged it. It must not."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = "vault/tools/tests/test_stranger_dev_chain_ships_v192.py"
            (root / "vault" / "tools" / "tests").mkdir(parents=True)
            (root / target).write_text("# present\n")
            _write_spec(root, "cccccccc", [{
                "id": "AC4",
                "behavior": "THE STRANGER'S COLD ENTRY POINT EXISTS IN THE BOX. "
                            "Every fenced command is copy-pasteable in a bare "
                            "shipped box.",
                "verify": {"method": "automated",
                           "command": f"python3 {target} --skill",
                           "evidence": "asserts the skill file exists at ship scope"},
            }])
            findings = [f for r in sv.run(root) for f in r.findings]
        self.assertEqual(
            [], findings,
            "prose mentioning a release artifact must not trip the check when "
            "the criterion is automated and resolves at dev scope; a false "
            "finding in a governance check teaches people to skip it",
        )

    def test_a_manual_criterion_without_release_language_is_not_flagged(self) -> None:
        """Manual alone is not the defect. Manual AND unverifiable-here is."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_spec(root, "dddddddd", [{
                "id": "AC1",
                "verify": {"method": "manual",
                           "command": "a reviewer reads the ADR and signs off",
                           "evidence": "signoff recorded"},
            }])
            kinds = [f.kind for r in sv.run(root) for f in r.findings]
        self.assertNotIn("RELEASE-COUPLED", kinds)


class EachCheckFiresAtTheMomentItIsMeaningful(unittest.TestCase):
    """A locked spec legitimately names targets that do not exist yet.

    Ten of 5b608d28's eighteen committed-substrate entries were `change_class:
    NEW` at lock time. Running the existence check at lock would therefore flag
    every freshly-locked spec — the false-finding generator this tool's own
    comments warn against, built into the tool an hour after those comments were
    written. Found by asking what the checker would have said about a spec on
    the day it was LOCKED rather than today.

    The two checks answer different questions at different moments:
      AT LOCK   is any criterion unsatisfiable in principle? Release-coupling is
                knowable the moment it is written; no amount of building fixes it.
      AT CLOSE  does every named target exist? The question that matters when a
                spec claims done, and the one that catches a phantom target.
    """

    def _freshly_locked(self, root: Path) -> None:
        _write_spec(root, "aaaaaaaa", [
            {"id": "AC1", "verify": {
                "method": "automated",
                "command": "python3 -m pytest -q vault/tools/tests/test_not_built_yet.py"}},
            {"id": "AC2", "behavior": "walk it", "verify": {
                "method": "manual",
                "command": "walk the v1.92 candidate box",
                "evidence": "the record names the candidate sha"}},
        ])

    def test_at_lock_a_not_yet_built_target_is_not_a_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._freshly_locked(root)
            kinds = [f.kind for r in sv.run(root, at=sv.AT_LOCK) for f in r.findings]
        self.assertNotIn(
            "PHANTOM-TARGET-SILENT", kinds,
            "at lock, a target that is not built yet is the normal state; "
            "flagging it would make this check noise on every new spec",
        )

    def test_at_lock_an_unsatisfiable_criterion_IS_a_finding(self) -> None:
        """Structural impossibility does not wait for the build."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._freshly_locked(root)
            kinds = [f.kind for r in sv.run(root, at=sv.AT_LOCK) for f in r.findings]
        self.assertIn("RELEASE-COUPLED", kinds)

    def test_at_close_the_phantom_target_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._freshly_locked(root)
            kinds = [f.kind for r in sv.run(root, at=sv.AT_CLOSE) for f in r.findings]
        self.assertIn("PHANTOM-TARGET-SILENT", kinds)

    def test_the_two_phases_are_not_the_same_check(self) -> None:
        """Guards the distinction itself: if both phases ever return identical
        findings, one of them has silently stopped meaning anything."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._freshly_locked(root)
            at_lock = {f.kind for r in sv.run(root, at=sv.AT_LOCK) for f in r.findings}
            at_close = {f.kind for r in sv.run(root, at=sv.AT_CLOSE) for f in r.findings}
        self.assertTrue(at_lock < at_close, f"lock={at_lock} close={at_close}")


class TheCheckerDoesNotOverstateItsCoverage(unittest.TestCase):
    """The instrument's own blindness must be visible in its output."""

    def test_prose_shaped_criteria_are_counted_not_silently_skipped(self) -> None:
        """Nine real locked specs hold 87 criteria in the older shape — a bare
        list of strings. The first version skipped them silently and printed
        'clean', which is the defect this whole instrument exists to catch,
        committed inside the instrument."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_spec(root, "eeeeeeee",
                        ["GOVERNED BIRTH: the locked capsule mints one draft",
                         "AGENT UX UNCHANGED: an agent invokes the command"])
            reports = sv.run(root)
        self.assertEqual(reports[0].unreadable_shape, 2)
        self.assertEqual(reports[0].criteria, 0)

    def test_the_real_corpus_reports_uninspected_criteria(self) -> None:
        """Against the live vault, not a fixture: the count must be nonzero and
        surfaced, so no reader mistakes partial coverage for full coverage."""
        reports = sv.run(STUDIO_ROOT)
        self.assertGreater(
            sum(r.unreadable_shape for r in reports), 0,
            "the corpus is known to contain prose-shaped criteria; reporting "
            "zero means the counter stopped working",
        )

    def test_only_locked_dev_specs_are_in_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import yaml
            (root / "vault" / "files").mkdir(parents=True)
            (root / "vault" / "files" / "ffffffff.md").write_text(
                "---\n" + yaml.safe_dump({
                    "uid": "ffffffff", "type": "dev-spec", "status": "draft",
                    "acceptance_criteria": [{
                        "id": "AC1",
                        "verify": {"method": "automated",
                                   "command": "python3 -m pytest -q nope/x.py"},
                    }],
                }, sort_keys=False) + "---\n"
            )
            self.assertEqual([], sv.run(root),
                             "a draft spec is not yet a commitment")


class TheRealCorpusIsCleanOverWhatWasInspected(unittest.TestCase):
    """Regression guard: today's repair must stay repaired."""

    #: Findings that PRE-DATE this check and are not this cycle's to fix.
    #: Named individually rather than counted, so a new one cannot hide inside
    #: a tolerance — the same discipline as the six baselined release-suite
    #: failures. Widening the scope to closed specs is what surfaced them:
    #:
    #:   29506520  four acceptance commands name *_v191.py test files that were
    #:             renamed to _v192 and never updated here. Its committed
    #:             substrate was amended; its acceptance commands were not, so
    #:             four criteria on a DONE spec cannot be re-run as written.
    #:   8affeac0  a done dev-spec whose acceptance_criteria is None.
    #:   d996b941  the same.
    BASELINE = {
        ("29506520", "PHANTOM-TARGET"),
        ("8affeac0", "NO-CRITERIA"),
        ("d996b941", "NO-CRITERIA"),
    }

    def test_no_new_phantom_target_outside_the_baseline(self) -> None:
        findings = [
            f for r in sv.run(STUDIO_ROOT) for f in r.findings
            if f.kind.startswith("PHANTOM-TARGET")
            and (f.uid, "PHANTOM-TARGET") not in self.BASELINE
        ]
        self.assertEqual(
            [], findings,
            "new phantom target(s) outside the recorded baseline:\n  "
            + "\n  ".join(f.render() for f in findings),
        )

    def test_the_baseline_is_still_real_and_not_quietly_fixed(self) -> None:
        """A baseline nobody re-checks becomes a tolerance. If these are fixed,
        this test says so and the entry should be removed rather than carried."""
        seen = {(f.uid, f.kind.split("-SILENT")[0].replace("PHANTOM-TARGET", "PHANTOM-TARGET"))
                for r in sv.run(STUDIO_ROOT) for f in r.findings}
        seen = {(uid, "PHANTOM-TARGET" if k.startswith("PHANTOM-TARGET") else k)
                for uid, k in seen}
        stale = sorted(self.BASELINE - seen)
        self.assertEqual(
            [], stale,
            f"these baseline entries no longer reproduce and should be removed "
            f"from BASELINE rather than carried as permanent tolerance: {stale}",
        )

    def test_no_locked_spec_is_release_coupled(self) -> None:
        findings = [
            f for r in sv.run(STUDIO_ROOT) for f in r.findings
            if f.kind == "RELEASE-COUPLED"
        ]
        self.assertEqual(
            [], findings,
            "\n  " + "\n  ".join(f.render() for f in findings),
        )


if __name__ == "__main__":
    unittest.main()
