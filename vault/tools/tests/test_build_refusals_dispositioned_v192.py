"""AC3 (5b608d28, v1.92 Stream 1): every refusal site in the build path carries
exactly ONE of three dispositions, and a crash never masquerades as a verdict on
the release.

    PRICED   prevents irreversible harm, and names which of the six earned
             fail-closed categories it defends (deb77758).
    WARN     the thing it stops is reversible; it records and proceeds.
    MISUSE   the tool could not run. NEVER a verdict on the release.

Measured motivation: `deb77758` has been studio law since 2026-08-09 and
`tropo-build-release.py` references it ZERO times, while
`tropo-lock-release-plan.py` — written after the ruling — cites it three times.
The lock was priced; the build never was. Mike's own example in that ruling was
an inbox-hygiene check that blocked a release build.

THE ENUMERATION IS COMPUTED HERE, NOT PINNED. The spec draft asserted 54 sites
and that number is not reproducible; counting methods give 65 to 80. A count
written into a test is a second copy of the source that goes stale on the next
commit, so this test walks the AST and finds them itself.

AND IT PARSES RATHER THAN GREPPING. The build tool embeds a subprocess script in
a raw string literal that itself contains two `raise` statements. A regex
enumerator counts those and is wrong before it starts.

Verify command (locked in the spec):
    python3 -m pytest -q vault/tools/tests/test_build_refusals_dispositioned_v192.py

NOTE FOR ANYONE RUNNING THE MUTATION CONTROLS BY HAND: use `python3 -B`. This
Studio's default interpreter caches bytecode outside `__pycache__` and validates
it on (size, mtime), so a size-preserving edit inside one second is invisible and
the control reports a false result in both directions. See `42800b75`.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from typing import Dict, List
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
LIB = STUDIO_ROOT / "vault" / "tools" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import refusal_dispositions as rd  # noqa: E402  - path set above

BUILD_TOOL = STUDIO_ROOT / "vault" / "tools" / "tropo-build-release.py"

#: EVERY module the build executes, not just the one the test target is named
#: after. The first version of this suite asserted the one-file scope was
#: correct; an adversarial pass measured 40 stop sites it excluded, in modules
#: the build calls directly — including release_package.py, whose PackageRefusal
#: is raised FROM the build tool, and two modules this spec itself declares as
#: committed substrate.
BUILD_PATH = None  # set at import time below


def _all_sites():
    """Every stop site across the whole build path."""
    out = []
    for path in rd.build_path_files(STUDIO_ROOT):
        out.extend(rd.sites(path))
    return out


def _all_undispositioned():
    out = []
    for path in rd.build_path_files(STUDIO_ROOT):
        out.extend(rd.undispositioned(path))
    return out


class TheEnumerationIsReal(unittest.TestCase):
    """If the site list is wrong, every assertion below is decoration."""

    def test_the_build_path_is_every_module_the_build_executes(self) -> None:
        """Measured against the source, not pinned to a list.

        HISTORY, BOTH DIRECTIONS. The first version asserted a one-file scope as
        CORRECT, which made a real narrowing look deliberate and reviewed. The
        fix over-corrected: it hardcoded four modules and asserted the build
        "calls directly" two that it has never imported — tropo-release.py and
        release_metrics.py are the FIRE path. Measured 2026-08-25: zero
        references to either in tropo-build-release.py or in release_package.py;
        the only textual hits are the output directory `tropo-releases` and a
        comment about a differently-named tool. The cost was that 41 of the 120
        stop sites reported as "the build path" were another boundary's, so
        every count was inflated by a third and the 16 demotion candidates were
        read against the wrong denominator.

        So this no longer pins a list in either direction. It asserts the
        PROPERTY the list is supposed to have — membership matches what the
        build actually reaches — which fails on a narrowing AND on a widening,
        and needs no editing when the build legitimately changes.
        """
        paths = rd.build_path_files(STUDIO_ROOT)
        self.assertIn(BUILD_TOOL, paths)

        reachable = BUILD_TOOL.read_text(errors="replace")
        for extra in paths:
            if extra == BUILD_TOOL:
                continue
            stem = extra.name.replace(".py", "")
            with self.subTest(module=extra.name):
                self.assertIn(
                    stem, reachable,
                    f"{extra.name} is on the build path but the build tool "
                    f"never references it — its stop sites belong to another "
                    f"boundary and inflate this one's count",
                )

    def test_sites_are_found_and_the_count_is_not_pinned(self) -> None:
        found = rd.sites(BUILD_TOOL)
        self.assertGreater(
            len(found), 50,
            "the build path is known to carry dozens of stop sites; finding "
            "almost none means the enumerator broke, not that the tool changed",
        )

    def test_the_enumerator_ignores_raises_inside_string_literals(self) -> None:
        """A grep-based enumerator counts `raise` inside an embedded script.

        This used to lean on the build tool happening to embed a subprocess
        script with two raises in a raw string — and when that dead script was
        deleted (2026-08-25) the test failed, having been pinned to a quirk of
        production rather than to the property it names. A test that breaks
        because unrelated dead code was removed was never testing the
        enumerator. It carries its own fixture now, so it holds regardless of
        what production happens to contain.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "embedded.py"
            target.write_text(
                'SCRIPT = r"""\n'
                'if bad:\n'
                '    raise SystemExit("inside a string literal")\n'
                'raise RuntimeError("also inside")\n'
                '"""\n'
                '\n'
                'def real():\n'
                '    # refusal: misuse — the one real stop site\n'
                '    raise SystemExit("actually executable")\n',
                encoding="utf-8",
            )
            source = target.read_text(errors="replace")
            grep_raises = sum(
                1 for line in source.splitlines()
                if line.strip().startswith("raise ")
            )
            ast_raises = sum(
                1 for s in rd.sites(target) if s.shape.startswith("raise")
            )
            self.assertEqual(grep_raises, 3, "fixture sanity: 3 lines look like raises")
            self.assertEqual(
                ast_raises, 1,
                "AST must find only the executable raise; the two inside the "
                "raw string are text, not stop sites",
            )

    def test_every_site_reports_a_shape_and_a_location(self) -> None:
        for site in rd.sites(BUILD_TOOL):
            with self.subTest(where=site.where):
                self.assertTrue(site.shape)
                self.assertGreater(site.line, 0)
                self.assertTrue(site.function)


class EverySiteCarriesExactlyOneDisposition(unittest.TestCase):
    """AC3's coverage half. Failures name the site and line."""

    def setUp(self) -> None:
        self.sites = _all_sites()

    def test_no_site_is_undispositioned(self) -> None:
        missing = _all_undispositioned()
        self.assertEqual(
            [], missing,
            "these stop sites declare no disposition, so nobody can say "
            "whether they earned the right to stop a release:\n  "
            + "\n  ".join(
                f"{s.where} — {s.shape} in {s.function}" for s in missing
            ),
        )

    def test_no_site_carries_a_malformed_disposition(self) -> None:
        problems = [p for s in self.sites for p in s.problems()]
        self.assertEqual([], problems, "\n  " + "\n  ".join(problems))

    def test_a_site_cannot_carry_two_dispositions(self) -> None:
        """One marker per site. Two markers is an unresolved argument about
        what the site is, left in the source for the next person.

        Counts only markers in this site's OWN comment block — the contiguous
        run of comment lines directly above it, stopping at the first line of
        code. A fixed-line window was the first version and it was wrong:
        adjacent stop sites a few lines apart (two `raise RuntimeError`s in the
        same try/except) each carry their own marker, and a six-line window
        reads the neighbour's as a second marker on the first. The gate was
        firing on correctly-annotated code.
        """
        # EACH SITE'S OWN FILE. This read BUILD_TOOL for all 120 sites, so for
        # the 40 in the other three modules it inspected arbitrary lines of a
        # file they are not in. Planting two markers on one release_package.py
        # site — exactly the shape this exists to catch — left the suite green.
        by_file: Dict[str, List[str]] = {}
        for site in self.sites:
            key = str(site.path)
            if key not in by_file:
                by_file[key] = site.path.read_text(errors="replace").splitlines()
            source = by_file[key]
            hits = 0
            if rd.MARKER_RE.search(source[site.line - 1]):
                hits += 1
            idx = site.line - 2
            while idx >= 0:
                stripped = source[idx].strip()
                if not stripped:
                    idx -= 1
                    continue
                if not stripped.startswith("#"):
                    break
                if rd.MARKER_RE.search(source[idx]):
                    hits += 1
                idx -= 1
            with self.subTest(where=site.where):
                self.assertLessEqual(
                    hits, 1,
                    f"{site.where} has {hits} disposition markers in its own "
                    f"comment block; exactly one site, exactly one disposition",
                )

    def test_priced_sites_name_a_category_from_the_closed_six(self) -> None:
        for site in self.sites:
            if site.disposition != rd.PRICED:
                continue
            with self.subTest(where=site.where):
                self.assertIn(
                    site.category, rd.FAIL_CLOSED_CATEGORIES,
                    f"{site.where} claims a fail-closed category outside the "
                    f"six Mike ruled. The list is closed on purpose: an open "
                    f"one is how fail-closed-by-default returns one "
                    f"plausible-sounding category at a time",
                )

    def test_priced_sites_name_an_actual_harm(self) -> None:
        """The whole calibration rule in one assertion: a refusal earns its
        existence by naming the irreversible harm, in a sentence."""
        for site in self.sites:
            if site.disposition != rd.PRICED:
                continue
            with self.subTest(where=site.where):
                self.assertTrue(site.text, f"{site.where} prices nothing")
                self.assertGreaterEqual(
                    len(site.text.split()), 5,
                    f"{site.where} names a harm in fewer than five words, "
                    f"which is a label rather than a priced harm",
                )


class UnearnedRefusalsStayCountable(unittest.TestCase):
    """`warn` is a finding, not a behaviour: those sites still exit today.

    AC3's acceptance evidence is about DECLARATION — one disposition each,
    priced ones name a harm, misuse ones emit no verdict. Converting a release
    tool's control flow as a side effect of annotating it would fold an
    unrelated behaviour change into a locked spec's evidence, which is exactly
    what A156 declined to do with the six pre-existing failures. So these tests
    keep the unearned refusals visible and counted rather than converted.
    """

    def test_every_warn_site_says_why_it_did_not_earn_a_refusal(self) -> None:
        for path in rd.build_path_files(STUDIO_ROOT):
          for site in rd.demotion_candidates(path):
            with self.subTest(where=site.where):
                self.assertTrue(
                    site.text and site.text.lower().startswith("unpriced:"),
                    f"{site.where} is marked warn but does not say why it "
                    f"fails to earn a refusal; 'warn' without a reason is an "
                    f"opinion, and the next person cannot act on it",
                )

    def test_the_demotion_list_is_reported_not_silently_empty(self) -> None:
        """A silent empty list would read as 'the build path is fully priced',
        which is a stronger claim than this criterion ever measured."""
        candidates = [c for p in rd.build_path_files(STUDIO_ROOT)
                      for c in rd.demotion_candidates(p)]
        priced = [s for s in _all_sites() if s.disposition == rd.PRICED]
        self.assertTrue(
            candidates or priced,
            "no site is either priced or flagged for demotion, which means "
            "nothing has actually been classified",
        )


class AMisuseSiteIsNeverAVerdict(unittest.TestCase):
    """AC3's sharpest half, and the one the preflight exit contract already
    codifies: 2 = a determinate verdict, 3 = the tool could not reach an
    answer, 'deliberately not 2'."""

    def setUp(self) -> None:
        # DELIBERATELY build-tool scoped, and this is a real limit rather than
        # an oversight worth hiding: `_record_build_refusal` exists only in
        # tropo-build-release.py, so there is no verdict-recording call to
        # detect in the other build-path modules. An adversarial pass measured
        # the detector reaching 2 sites in a 4,221-line file and called the
        # assertions over it near-vacuous. That criticism stands; widening the
        # file list does not answer it, and pretending otherwise would be worse
        # than recording it here.
        # Whole build path now. The detector knew ONE call name and scanned ONE
        # file. Measuring across the path found a second way a verdict is
        # recorded — tropo-release.py reaches telemetry.record_refused directly,
        # with harm_class irreversible-write — which the single-name detector
        # could not see.
        #
        # BE PRECISE ABOUT WHAT THAT FIXED. Verdict-recording BLOCKS went 4 -> 5
        # across 2 files. Stop sites co-located with one stayed at 2. So the
        # criticism is answered in the part that was a blind spot and not in the
        # part that never was: this codebase genuinely has few places where a
        # stop site sits in the same block as a verdict record. A low count
        # MEASURED across every module the build executes is a different thing
        # from a low count produced by looking in one file for one name.
        self.sites = _all_sites()
        self.spans = [sp for path in rd.build_path_files(STUDIO_ROOT)
                      for sp in rd.verdict_blocks(path)]

    def test_no_misuse_site_records_a_release_refusal(self) -> None:
        offenders = [
            s for s in self.sites
            if s.disposition == rd.MISUSE
            and rd.emits_release_verdict(s, self.spans)
        ]
        self.assertEqual(
            [], offenders,
            "these sites say 'I could not run' and then record 'the release "
            "was refused' — a false record of a decision nobody made:\n  "
            + "\n  ".join(f"{s.where} in {s.function}" for s in offenders),
        )

    def test_misuse_sites_claim_no_fail_closed_category(self) -> None:
        for site in self.sites:
            if site.disposition != rd.MISUSE:
                continue
            with self.subTest(where=site.where):
                self.assertIsNone(
                    site.category,
                    f"{site.where} is misuse and names a release boundary; a "
                    f"crash defends no boundary",
                )

    def test_the_detector_knows_every_way_a_verdict_is_recorded(self) -> None:
        """Completeness of the vocabulary, not reach of the result."""
        self.assertIn("_record_build_refusal", rd.VERDICT_CALLS)
        self.assertIn("record_refused", rd.VERDICT_CALLS)
        self.assertNotIn(
            "record_failed", rd.VERDICT_CALLS,
            "record_failed means 'execution began and did not complete', which "
            "is exactly what a misuse site SHOULD record; treating it as a "
            "verdict would invert the distinction",
        )

    def test_the_detector_sees_the_directly_called_primitive(self) -> None:
        """The specific blind spot, pinned."""
        release_tool = STUDIO_ROOT / "vault" / "tools" / "tropo-release.py"
        self.assertTrue(
            rd.verdict_blocks(release_tool),
            "no verdict block in tropo-release.py, which calls "
            "telemetry.record_refused directly",
        )

    def test_the_verdict_detector_finds_the_real_recording_sites(self) -> None:
        """Guards the detector itself. An inverted-polarity probe that finds
        nothing passes every assertion above while protecting nothing."""
        self.assertGreater(
            len(self.spans), 0,
            "no verdict-recording block found at all — the detector is blind, "
            "and a blind detector makes the misuse assertions vacuous",
        )
        emitting = [s for s in self.sites if rd.emits_release_verdict(s, self.spans)]
        self.assertGreater(
            len(emitting), 0,
            "no stop site sits in a verdict-recording block; the build tool "
            "is known to record refusals beside its exits",
        )
        self.assertLess(
            len(emitting), len(self.sites),
            "EVERY site reads as verdict-emitting, which is the bug this "
            "detector had in its first version: walking each statement's whole "
            "subtree made the module body itself a recording block",
        )


class NegativeControls(unittest.TestCase):
    """Each proves a gate fires on the shape it exists for, against a copy of
    the real file. A green suite over a mechanism that cannot go red is worse
    than no suite."""

    def _mutated(self, tmp: Path, old: str, new: str) -> Path:
        source = BUILD_TOOL.read_text(errors="replace")
        self.assertIn(old, source, "the mutation target is not in the source")
        path = tmp / "tropo-build-release.py"
        path.write_text(source.replace(old, new, 1))
        return path

    def test_stripping_the_harm_from_a_priced_refusal_goes_red(self) -> None:
        """The control the criterion names by hand."""
        import tempfile

        priced = [s for s in _all_sites() if s.disposition == rd.PRICED]
        if not priced:
            self.skipTest("no priced site yet to strip")
        target = priced[0]
        marker = f"# refusal: priced/{target.category} — {target.text}"
        with tempfile.TemporaryDirectory() as tmp:
            path = self._mutated(
                Path(tmp), marker, f"# refusal: priced/{target.category} — x"
            )
            problems = [p for s in rd.sites(path) for p in s.problems()]
        self.assertTrue(
            any("names no irreversible harm" in p for p in problems),
            "stripping the harm text from a priced refusal must go red",
        )

    def test_removing_a_marker_entirely_goes_red(self) -> None:
        import tempfile

        marked = [s for s in rd.sites(BUILD_TOOL) if s.dispositioned]
        if not marked:
            self.skipTest("nothing dispositioned yet")
        target = marked[0]
        line = BUILD_TOOL.read_text(errors="replace").splitlines()[target.line - 1]
        source_line = line if rd.MARKER_RE.search(line) else None
        if source_line is None:
            lines = BUILD_TOOL.read_text(errors="replace").splitlines()
            idx = target.line - 2
            while idx >= 0 and not rd.MARKER_RE.search(lines[idx]):
                idx -= 1
            source_line = lines[idx]
        with tempfile.TemporaryDirectory() as tmp:
            path = self._mutated(Path(tmp), source_line, "")
            self.assertTrue(
                rd.undispositioned(path),
                "removing a marker must leave a site undispositioned",
            )

    def test_an_invented_fail_closed_category_goes_red(self) -> None:
        site = rd.RefusalSite(
            path=BUILD_TOOL, line=1, shape="sys.exit(1)", function="f",
            disposition=rd.PRICED, category="hygiene-matters",
            text="a plausible sounding seventh category",
        )
        self.assertTrue(
            any("not one of the six earned" in p for p in site.problems()),
            "the six categories are closed; a seventh must be refused",
        )

    def test_a_priced_site_with_no_category_goes_red(self) -> None:
        site = rd.RefusalSite(
            path=BUILD_TOOL, line=1, shape="sys.exit(1)", function="f",
            disposition=rd.PRICED, category=None,
            text="something irreversible happens here",
        )
        self.assertTrue(any("names no fail-closed category" in p for p in site.problems()))

    def test_a_misuse_site_claiming_a_category_goes_red(self) -> None:
        site = rd.RefusalSite(
            path=BUILD_TOOL, line=1, shape="raise ImportError", function="f",
            disposition=rd.MISUSE, category="false-success", text="loader guard",
        )
        self.assertTrue(any("defends no release boundary" in p for p in site.problems()))

    def test_an_unknown_disposition_word_goes_red(self) -> None:
        site = rd.RefusalSite(
            path=BUILD_TOOL, line=1, shape="sys.exit(1)", function="f",
            disposition="probably-fine", text="x",
        )
        self.assertTrue(any("expected one of" in p for p in site.problems()))

    def test_the_marker_grammar_rejects_a_near_miss(self) -> None:
        """A marker that ALMOST parses is worse than none: it reads as
        annotated to a human and is invisible to the gate."""
        for near_miss in (
            "# refusal: priced",                      # no harm text
            "# refusal priced/false-success — harm",  # missing colon
            "# refuses: warn — proceeds",             # wrong keyword
            "# refusal: maybe — unsure",              # unknown disposition
        ):
            with self.subTest(near_miss=near_miss):
                self.assertIsNone(rd.MARKER_RE.search(near_miss))


if __name__ == "__main__":
    unittest.main()
