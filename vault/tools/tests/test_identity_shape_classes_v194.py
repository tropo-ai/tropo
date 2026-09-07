"""3d430852 step 5 fixture suite (test-spec 5119356e): one known-positive per
failure class, both directions where a ghost can be injected.

Class proofs work against the LIVE module source: shape constants are called
directly; function-local patterns are extracted verbatim from the module text
(the extraction itself is pinned to expected occurrence counts, so a reverted
or drifted pattern fails the pin AND the behavior -- revert-sensitive by
construction, the discipline 5119356e requires).
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = STUDIO_ROOT / "vault" / "tools" / "tropo-validate.py"

COMPOSITE = "1a2b3c4d5e6f"          # re-ruled composite shape (prefix+local)
COMPOSITE_PREFIX = "1a2b"
COMPOSITE_LOCAL = "3c4d5e6f"
LEGACY = "1a2b3c4d"
GHOST_HEAD = "1a2b3c4d"             # first-8 of COMPOSITE (never minted alone)
GHOST_TAIL = "3c4d5e6f"             # last-8 of COMPOSITE (never minted alone)


def load_validator():
    # exec-loaded tools need vault/tools FIRST on sys.path (studio pin f0158f934b60):
    # tropo-validate.py does `from lib import governed_path`, and from the repo root
    # `lib` resolves to a namespace package elsewhere ("unknown location"), so the
    # suite errored in setUpClass on any clone run via `python3 -m unittest` from
    # the root (Metis G121, 2026-09-05, suite-health 015 new-red triage).
    tools_dir = str(Path(VALIDATOR).resolve().parent)
    if sys.path[0] != tools_dir:
        sys.path.insert(0, tools_dir)
    for _stale in [m for m in list(sys.modules) if m == "lib" or m.startswith("lib.")]:
        if not str(getattr(sys.modules[_stale], "__file__", "") or "").startswith(tools_dir):
            del sys.modules[_stale]
    spec = importlib.util.spec_from_file_location("shape_validator_under_test", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def extract_pattern(source: str, literal: str, expect: int, flags: int = 0) -> re.Pattern:
    """Compile a pattern literal verbatim out of the live module source,
    pinning its occurrence count: a drift in the module fails here first."""
    n = source.count(literal)
    if n != expect:
        raise AssertionError(
            f"pattern pin failed: expected {expect} occurrences of {literal[:50]}..., "
            f"found {n} -- the module drifted; update the pin deliberately")
    return re.compile(literal, flags)


class ShapeClassFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = load_validator()
        cls.src = VALIDATOR.read_text(encoding="utf-8")

    # CLASS 1: REFUSE -- a valid composite uid passes the module gate.
    def test_class_refuse_composite_passes_the_module_gate(self):
        self.assertTrue(self.v.UID_RE.match(COMPOSITE))
        self.assertTrue(self.v.UID_RE.match(LEGACY))
        self.assertFalse(self.v.UID_RE.match("1a2b3c4d5e"))     # 9 hex: neither shape
        self.assertFalse(self.v.UID_RE.match("1A2B3C4D"))       # case

    # CLASS 2: SKIP (D8 cure, 00d776ae-era finding; the numbering gap named it):
    # a check that stops running is indistinguishable from one that passes --
    # the suite gets QUIETER, not louder. A163 shipped that exact hole in his
    # own gate. The known-positive here proves the skip is DELIBERATE and
    # BOUNDED both directions: the enumerated floor skips exactly what it
    # names, and everything else is still CHECKED -- so a silent skip-all
    # (the quiet failure) fails this pin by total_checked going to zero.
    def test_class_skip_is_enumerated_and_bounded(self):
        # occurrence pins (plain substrings -- the literal carries regex
        # metacharacters, so the count is the pin, not a compiled pattern)
        self.assertEqual(self.src.count("BOOTSTRAP_FLOOR = frozenset({"), 1,
                         "the enumerated floor is ONE declaration")
        # the floor is an ENUMERATION, not a predicate: pinned membership
        for member in ("'boot-config.md'", "'AGENTS.md'", "'version.md'"):
            self.assertIn(member, self.src,
                          "%s left the enumerated floor -- a floor that stops "
                          "naming its members became a pattern, and patterns "
                          "over-skip silently" % member)
        # the skip path consults the floor BY NAME (the visible opt-out) in
        # BOTH .tropo/ scan loops
        self.assertEqual(self.src.count("if f.name in BOOTSTRAP_FLOOR:"), 2,
                         "both .tropo/ scan loops must keep the bounded skip")

    def test_class_skip_still_checks_everything_else(self):
        # the QUIET half of the class: drive the real sweep on a temp vault
        # where one floor-named file and one normal file both live under a
        # scanned .tropo/ dir. The floor file is skipped; the normal file is
        # CHECKED -- and a check that silently skipped everything would
        # return zero checked and fail here.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            v = Path(tmp)
            (v / '.tropo').mkdir()
            scanned = v / '.tropo' / 'templates'
            scanned.mkdir()
            (scanned / 'AGENTS.md').write_text('floor-named: skipped\n', encoding='utf-8')
            (scanned / 'deadbeef.md').write_text(
                '---\nuid: deadbeef\ntitle: x\n---\nbody\n', encoding='utf-8')
            findings, checked, violations = self.v.check_no_two_homes(v)
            self.assertGreater(checked, 0,
                               "checked==0 is the QUIET failure: the sweep "
                               "skipped everything and reported silence")
            self.assertTrue(any('deadbeef' in f for f in findings) or checked >= 1,
                            "the non-floor file was not exercised")

    # CLASS 3: TRUNCATE-FROM-HEAD -- derived_from extracts the FULL uid and
    # the head-8 ghost never appears. Both directions.
    def test_class_truncate_head_derived_from_extracts_full(self):
        pat_yaml = extract_pattern(
            self.src,
            r'derived_from:\s*\n\s*-\s*"?((?<![a-f0-9])[a-f0-9]{8}|(?<![a-f0-9])[a-f0-9]{12})(?![a-f0-9])"?',
            3)
        fm = f'derived_from:\n  - "{COMPOSITE}"'
        got = pat_yaml.search(fm).group(1)
        self.assertEqual(got, COMPOSITE)                 # full uid present
        self.assertNotEqual(got, GHOST_HEAD)             # head ghost absent
        self.assertEqual(pat_yaml.search('derived_from:\n  - "%s"' % LEGACY).group(1), LEGACY)

    # CLASS 4: TRUNCATE-FROM-TAIL -- the run-folder authority pattern captures
    # the full uid; the tail ghost can never enter the set. Both directions.
    def test_class_truncate_tail_authority_set_captures_full(self):
        pat = extract_pattern(
            self.src,
            r'(?:^|[^0-9a-f])([0-9a-f]{8}|[0-9a-f]{12})$',
            1)
        name = f"agent-activation-talos-t53-{COMPOSITE}"
        got = pat.search(name).group(1)
        self.assertEqual(got, COMPOSITE)                 # full uid
        self.assertNotEqual(got, GHOST_TAIL)             # tail ghost absent
        # 13-hex malformed tail adds NOTHING (the old pattern added its last 8)
        self.assertIsNone(pat.search("x-" + COMPOSITE + "9"))
        self.assertEqual(pat.search("run-8654900a").group(1), "8654900a")

    # CLASS 5: INVERTED POLARITY -- the fixture-pollution gate accepts both
    # legal shapes and still refuses junk, both ways.
    def test_class_inverted_polarity_gate_both_ways(self):
        # THREE anchored accepts-both constants now live in the module
        # (UID_RE, UID_STEM, and this gate) -- the pin holds all of them.
        pat = extract_pattern(
            self.src,
            r'^(?:[0-9a-f]{8}|[0-9a-f]{12})$',
            3)
        self.assertTrue(pat.match(LEGACY))               # legal legacy
        self.assertTrue(pat.match(COMPOSITE))            # legal composite: NOT pollution
        self.assertFalse(pat.match("agent-talos-t53"))   # junk: still pollution

    # CLASS 6: SILENT-FALLBACK -- the frontmatter capture matches composite
    # uids so the stem fallback never fires for them.
    def test_class_silent_fallback_capture_matches_composite(self):
        # Pin updated deliberately 2026-09-05 (argus-a171): 00db97c39 made the
        # frontmatter capture QUOTE-tolerant (the mint writes uid: 'xxxx'), so
        # the literal grew optional quote groups; the class it proves — composite
        # matches, the stem fallback never fires — is unchanged, and the pin
        # still fails first if the capture drifts again.
        pat = extract_pattern(
            self.src,
            r'^uid:\s*[\'"]?([0-9a-f]{8}|[0-9a-f]{12})[\'"]?\s*$',
            1,
            flags=re.MULTILINE)
        self.assertEqual(pat.search(f"---\nuid: {COMPOSITE}\n---").group(1), COMPOSITE)
        self.assertEqual(pat.search(f"---\nuid: {LEGACY}\n---").group(1), LEGACY)

    # THE RE-RULED COMPOSITE SHAPE itself: prefix+local, greppable halves.
    def test_composite_shape_contract(self):
        self.assertEqual(COMPOSITE[:4], COMPOSITE_PREFIX)
        self.assertEqual(COMPOSITE[-8:], COMPOSITE_LOCAL)  # D7 emission half
        self.assertTrue(self.v.UID_RE.match(COMPOSITE))
        # the governed_path authority agrees (one shape authority per vector)
        gp_spec = importlib.util.spec_from_file_location(
            "shape_gp_under_test", STUDIO_ROOT / "vault" / "tools" / "lib" / "governed_path.py")
        gp = importlib.util.module_from_spec(gp_spec)
        sys.modules[gp_spec.name] = gp
        gp_spec.loader.exec_module(gp)
        self.assertEqual(gp.uid_shape(COMPOSITE), 12)
        self.assertEqual(gp.parse_anchored_uid(f"weekly-report-{COMPOSITE_LOCAL}.md"),
                         ("weekly-report", COMPOSITE_LOCAL))


if __name__ == "__main__":
    unittest.main()
