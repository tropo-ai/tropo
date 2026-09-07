#!/usr/bin/env python3
"""AC runner for dev-spec f5790777 — the Seam Rule (v1.94 Stream 5).

Executes AC1-AC4 of the Mike-locked spec. AC5 is the composed-path criterion and
lives in test_dev_spec_composed_path_ac.py; AC6 is two shell invocations of the
mint-registry generator and needs no runner.

DESIGN NOTE, learned the expensive way in this spec's own session (argus-a163):
every version assertion here is an ANCHORED EXACT REGEX MATCH, never a substring
`in` test. Bumping this capsule to 1.10 first landed as an unquoted YAML float
that parsed as 1.1, and the author's own substring check reported OK -- because
"v1.1" is a substring of "v1.10". The same author then mis-read a second result
for the same reason inside the same hour. Substring containment is satisfied by
the wrong answer for every X.1 vs X.10 pair. Do not "simplify" these back.

Usage:  python3 vault/tools/tests/check_seam_rule_amendment.py --ac {1,2,3,4}
        python3 vault/tools/tests/check_seam_rule_amendment.py --all
Exit 0 on pass, 1 on failure.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("[SKIP] pyyaml unavailable", file=sys.stderr)
    sys.exit(0)

ROOT = Path(__file__).resolve().parents[3]
CAPSULE = ROOT / "vault" / "capsules" / "tropo-dev-spec.capsule.md"
VALIDATOR = ROOT / "vault" / "tools" / "tropo-validate.py"
BEFORE = Path("/tmp/seam-before.txt")
AFTER = Path("/tmp/seam-after.txt")

EXPECTED_VERSION = "1.10"


def _fail(msg: str) -> None:
    print(f"  FAIL: {msg}")


def _frontmatter(path: Path) -> dict:
    text = path.read_text(errors="replace")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise SystemExit(f"[MISUSE] {path} has no parseable frontmatter")
    return yaml.safe_load(match.group(1)) or {}


def ac1() -> bool:
    """The amendment landed: version, note, marker field, and the new check."""
    text = CAPSULE.read_text(errors="replace")
    fm = _frontmatter(CAPSULE)
    ok = True

    version = fm.get("version")
    if not isinstance(version, str):
        _fail(
            f"version is {version!r} ({type(version).__name__}) -- it MUST be a quoted "
            f"string. Unquoted, YAML reads 1.10 as the float 1.1, a silent version "
            f"regression. capsule-of-capsules 38c63381 requires a quoted semver-ish string."
        )
        ok = False
    elif version != EXPECTED_VERSION:
        _fail(f"version is {version!r}, expected {EXPECTED_VERSION!r}")
        ok = False

    if "v1_10_amendment_note" not in fm:
        _fail("v1_10_amendment_note absent from frontmatter (meta-capsule Rule 2)")
        ok = False

    if "Composed-path AC for shared-lifecycle surfaces" not in text:
        _fail("Governance Rule 10 not found in the capsule body")
        ok = False

    if "`composed_path` (on an `acceptance_criteria` entry)" not in text:
        _fail("the composed_path field is not documented in Optional Frontmatter")
        ok = False

    if "check_dev_spec_composed_path_ac" not in text:
        _fail("the new validation check is not named in the capsule")
        ok = False

    surfaces = _surfaces(text)
    if len(surfaces) < 2:
        _fail(f"the SHARED-LIFECYCLE-SURFACES block declares {len(surfaces)} paths")
        ok = False
    missing = sorted(p for p in surfaces if not (ROOT / p).exists())
    if missing:
        _fail(f"declared surfaces that do not exist on disk: {missing}")
        ok = False

    return ok


def _surfaces(text: str) -> list[str]:
    match = re.search(
        r"SHARED-LIFECYCLE-SURFACES:BEGIN -->\n(.*?)<!-- SHARED-LIFECYCLE-SURFACES:END",
        text,
        re.S,
    )
    if not match:
        return []
    return [
        line.strip()
        for line in match.group(1).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def ac2() -> bool:
    """The six drift defects left by the under-applied v1.9 bump are cured."""
    text = CAPSULE.read_text(errors="replace")
    version = _frontmatter(CAPSULE).get("version")
    ok = True

    # D1 / D2 -- anchored exact matches, never `in`. See module docstring.
    h1 = re.search(r"^# dev-spec — Capsule Definition v([0-9.]+)$", text, re.M)
    if not h1:
        _fail("D1: no H1 of the expected shape")
        ok = False
    elif h1.group(1) != version:
        _fail(f"D1: H1 declares v{h1.group(1)}, frontmatter declares v{version}")
        ok = False

    footer = re.search(r"LOCKED v([0-9.]+) \|", text)
    if not footer:
        _fail("D2: no footer version stamp found")
        ok = False
    elif footer.group(1) != version:
        _fail(f"D2: footer declares v{footer.group(1)}, frontmatter declares v{version}")
        ok = False

    rows = re.findall(r"^\| (\d+\.\d+) \|", text, re.M)
    for needed in ("1.9", "1.10"):
        if needed not in rows:
            _fail(f"D3: changelog has no {needed} row")
            ok = False

    parsed = [tuple(int(p) for p in r.split(".")) for r in rows]
    if parsed != sorted(parsed, reverse=True):
        _fail(f"D4: changelog rows are not strict-descending: {rows}")
        ok = False

    if "check_cascade_disposition_required" not in text:
        _fail("D5: Rule 8's validator check is still absent from the Validation Checks list")
        ok = False

    glance = re.search(r"\*\*Rules \(at-a-glance\):\*\*\n(.*?)\n\n", text, re.S)
    if not glance:
        _fail("D6: the at-a-glance rules block was not found")
        ok = False
    else:
        listed = set(re.findall(r"^(\d+)\. ", glance.group(1), re.M))
        missing = {"8", "9", "10"} - listed
        if missing:
            _fail(f"D6: at-a-glance omits rule(s) {sorted(missing)}")
            ok = False

    return ok


def ac3() -> bool:
    """The check exists, has the house shape, and ships NON-EMPTY (so: WARN)."""
    text = VALIDATOR.read_text(errors="replace")
    ok = True

    if "def check_dev_spec_composed_path_ac(" not in text:
        _fail("check_dev_spec_composed_path_ac is not defined")
        return False

    match = re.search(
        r"DEV_SPEC_COMPOSED_PATH_ALLOWLIST\s*=\s*frozenset\(\{(.*?)\}\)", text, re.S
    )
    if not match:
        _fail("DEV_SPEC_COMPOSED_PATH_ALLOWLIST constant not found")
        return False

    seeded = re.findall(r"'([0-9a-f]{8})'", match.group(1))
    if not seeded:
        _fail(
            "the allowlist is seeded EMPTY. The sibling precedent derives "
            "ratchet_is_error = (len(ALLOWLIST) == 0), so an empty seed ships ERROR on "
            "day one against every shared-surface dev-spec and breaks the validator "
            "for the crew. This assertion is the whole point of AC3."
        )
        ok = False

    if text.count("check_dev_spec_composed_path_ac(") < 2:
        _fail("the check is defined but never invoked from main()")
        ok = False

    # The check must refuse, not silently pass, when it cannot read its subject.
    if "CANNOT RUN" not in text:
        _fail("no loud refusal path found -- a check that cannot see its subject must refuse")
        ok = False

    return ok


def ac4() -> bool:
    """A full validator run fails no previously-passing check."""
    if not (BEFORE.is_file() and AFTER.is_file()):
        _fail(
            f"need both a pre-amendment baseline at {BEFORE} and a post run at {AFTER}. "
            f"Capture the baseline BEFORE the amendment lands, or this AC is unfalsifiable."
        )
        return False

    pattern = re.compile(r"Summary: (\d+) passed, (\d+) failed, (\d+) warnings")
    before = pattern.search(BEFORE.read_text(errors="replace"))
    after = pattern.search(AFTER.read_text(errors="replace"))
    if not (before and after):
        _fail("could not parse a Summary line from one of the runs")
        return False

    b_pass, b_fail = int(before.group(1)), int(before.group(2))
    a_pass, a_fail = int(after.group(1)), int(after.group(2))
    print(f"  baseline: {b_pass} passed, {b_fail} failed")
    print(f"  current:  {a_pass} passed, {a_fail} failed")

    ok = True
    if a_fail > b_fail:
        _fail(f"failures grew {b_fail} -> {a_fail}")
        ok = False
    if a_pass < b_pass:
        _fail(f"passes shrank {b_pass} -> {a_pass}")
        ok = False
    return ok


ACS = {1: ac1, 2: ac2, 3: ac3, 4: ac4}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ac", type=int, choices=sorted(ACS))
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if not args.all and args.ac is None:
        parser.error("pass --ac N or --all")

    targets = sorted(ACS) if args.all else [args.ac]
    failures = []
    for number in targets:
        if ACS[number]():
            print(f"AC{number} PASS")
        else:
            print(f"AC{number} FAIL")
            failures.append(number)

    if failures:
        print(f"\n{len(failures)} of {len(targets)} criteria FAILED: {failures}")
        return 1
    print(f"\nall {len(targets)} criteria PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
