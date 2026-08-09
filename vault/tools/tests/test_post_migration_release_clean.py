#!/usr/bin/env python3
"""STUDIO-ROOT validator debt ratchet — NOT a release-surface check.

READ THIS BEFORE TRUSTING THE FILENAME. This file is called
`test_post_migration_release_clean.py` and the word "release" in that name is
wrong. It runs `tropo-validate` against the STUDIO ROOT — our own workshop
floor — and has never looked at a release extract. What ships is validated by
the release harness at stage and walked by Po at the cold walk; this suite
cannot see either.

The name is kept because it is only a name: renaming a file breaks every
historical record that cites it, and this studio's whole forward-only
discipline says you do not move a thing to make a label tidy. So the label is
corrected here, at the top, where a reader lands.

WHAT IT ACTUALLY MEASURES, and why that is still worth measuring: the studio's
own accumulated validator debt, as a RATCHET. Debt may be paid down freely; it
may not grow by accident. A commit that adds failures fails this suite.

WHY IT WAS RED FOR MONTHS. It compared against `BASELINE_FAIL_CEILING = 2`, a
constant captured at v1.74 ship that nothing ever updated, while the real count
drifted to 504. An alarm that cannot be silenced is an alarm nobody reads, and
this one had grown into a permanent red on the board — read by at least one
agent (me, 2026-08-08) as a release-blocking signal, which cost a morning until
the code said otherwise. The frozen constant is replaced by a recorded baseline
that a human updates deliberately, in a file beside this test, with the reason.

(talos-t39, 2026-08-08, at Metis G105's direction after the v1.86 cut-ready
call; the diagnosis is on gate c8416724.)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = ROOT / "vault" / "tools" / "tropo-validate.py"
BASELINE_PATH = Path(__file__).with_name("studio-validator-debt-baseline.json")


def run_validate() -> tuple[int, int, str]:
    """Run tropo-validate against the STUDIO ROOT and return (passed, failed, tail)."""
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=900,  # THIRD bump (120->360->900): validator measured ~4.5min standalone on 2026-08-08 and slower when the build runs it concurrently with the rebuild's own validator pre-step. A constant chasing linear growth loses every few weeks; the root perf fix (incremental/hash-gated validate) is v1.87 work (metis-g105).
    )
    output = result.stdout + result.stderr
    m = re.search(r"Summary[:\s]+(\d+) passed.*?(\d+) failed", output)
    if m:
        return int(m.group(1)), int(m.group(2)), output.split("\n")[-10]
    return 0, 0, output[-500:]


def load_baseline() -> tuple[int, str]:
    """The recorded debt ceiling, or a refusal to guess one.

    Returns (ceiling, provenance). A missing or malformed baseline is NOT
    silently defaulted: a made-up ceiling is exactly how the v1.74 constant
    outlived its meaning.
    """
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        return int(data["failed"]), str(data.get("recorded_at", "unknown"))
    except (OSError, ValueError, KeyError, TypeError):
        return -1, "absent"


def main() -> int:
    if not VALIDATOR.exists():
        print(f"FAIL — validator not found at {VALIDATOR.relative_to(ROOT)}")
        return 1

    ceiling, recorded_at = load_baseline()
    if ceiling < 0:
        print(f"FAIL — no recorded baseline at {BASELINE_PATH.name}.")
        print("       This suite refuses to invent a ceiling. Run tropo-validate,")
        print("       record the count with a reason, and commit the baseline.")
        return 1

    print("Scope: the STUDIO ROOT, not a release surface.")
    print("Running tropo-validate (this may take ~2-3 min)...")
    try:
        passed, failed, _summary = run_validate()
    except subprocess.TimeoutExpired:
        print("FAIL — tropo-validate timed out after 900s")
        return 1

    print(f"Result: {passed} passed, {failed} failed "
          f"(recorded studio debt: {ceiling}, from {recorded_at})")

    if failed <= ceiling:
        if failed < ceiling:
            print(f"PASS — studio debt DOWN {ceiling - failed} from the recorded "
                  f"baseline. Re-record {BASELINE_PATH.name} to lock the gain in, "
                  f"or the ratchet keeps allowing the old ceiling.")
        else:
            print(f"PASS — studio debt unchanged at {failed}.")
        return 0

    print(f"FAIL — studio debt UP {failed - ceiling}, from {ceiling} to {failed}.")
    print("       Something in this change set added validator failures.")
    print("       Run `python3 vault/tools/tropo-validate.py` to see which.")
    print("       This is NOT a statement about the release: it measures the")
    print("       studio root. If the growth is deliberate and accepted, raise")
    print(f"       the baseline in {BASELINE_PATH.name} with the reason.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
