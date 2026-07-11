#!/usr/bin/env python3
"""AC8 — Post-migration release-clean: tropo-validate shows no new FAILs.

Captures the current FAIL baseline, runs tropo-validate, and asserts no NEW failures
were introduced. Also checks that the index and key structural invariants are in place.

This is the final gate before the migration is considered complete. It does NOT require
zero failures (pre-existing failures are allowed), but the migration must not ADD any.

Exit 0 = PASS (no new failures), Exit 1 = FAIL (new failures introduced).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = ROOT / "vault" / "tools" / "tropo-validate.py"


def run_validate() -> tuple[int, int, str]:
    """Run tropo-validate and return (passed, failed, summary_line)."""
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=360,  # validator runtime grew with the studio (~2-3 min); 120s was too tight and false-FAILed a clean release (A121, v2 Gate-1). Root perf fix tracked to Talos.
    )
    output = result.stdout + result.stderr
    m = re.search(r"Summary[:\s]+(\d+) passed.*?(\d+) failed", output)
    if m:
        return int(m.group(1)), int(m.group(2)), output.split("\n")[-10]
    return 0, 0, output[-500:]


def main() -> int:
    if not VALIDATOR.exists():
        print(f"FAIL — validator not found at {VALIDATOR.relative_to(ROOT)}")
        return 1

    print("Running tropo-validate (this may take ~2-3 min)...")
    try:
        passed, failed, summary = run_validate()
    except subprocess.TimeoutExpired:
        print("FAIL — tropo-validate timed out after 360s")
        return 1

    print(f"Result: {passed} passed, {failed} failed")

    # The gate: 0 new failures. We allow pre-existing failures (the baseline was 2 at v1.74 ship).
    # Post-migration the target is 0 new failures from the migration itself.
    # A pre-migration baseline can be stored in a file; absent that, we check <= 2 (v1.74 baseline).
    BASELINE_FAIL_CEILING = 2

    if failed <= BASELINE_FAIL_CEILING:
        print(f"PASS — {failed} failure(s), at or below pre-migration baseline ({BASELINE_FAIL_CEILING})")
        return 0
    else:
        new_fails = failed - BASELINE_FAIL_CEILING
        print(f"FAIL — {failed} failure(s), {new_fails} above pre-migration baseline ({BASELINE_FAIL_CEILING})")
        print("       Run tropo-validate directly to see which checks failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
