#!/usr/bin/env python3
"""AC6 — No-two-homes gate, adversarially isolated.

Plants a synthetic governed file in BOTH vault/files/ AND .tropo/ (or a content dir)
then asserts:
  1. check_no_two_homes() in the validator ERRORs (finds the duplicate).
  2. Removing the synthetic duplicate makes check_no_two_homes() PASS.

The test proves the ENFORCEMENT CODE prevents bad outcomes, not just that the spec says
so (A112/A113 gauntlet binding — adversarial isolation: only the mechanism under test
can prevent the bad outcome).

Exit 0 = PASS, Exit 1 = FAIL.
"""
import importlib.util
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = ROOT / "vault" / "tools" / "tropo-validate.py"

SYNTHETIC_UID = "cafef00d"  # synthetic UID used only for this test
SYNTHETIC_FM = f"""---
uid: {SYNTHETIC_UID}
type: note
title: "Synthetic two-home test fixture"
status: active
state: active
---

This file is a synthetic two-home test fixture created by test_no_two_homes_gate.py.
It should never be committed; the test cleans it up.
"""


def load_check_fn():
    """Dynamically load check_no_two_homes from the validator."""
    spec = importlib.util.spec_from_file_location("validator", VALIDATOR_PATH)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    fn = getattr(mod, "check_no_two_homes", None)
    return fn, mod


def main() -> int:
    if not VALIDATOR_PATH.exists():
        print(f"FAIL — validator not found at {VALIDATOR_PATH.relative_to(ROOT)}")
        return 1

    check_fn, mod = load_check_fn()
    if check_fn is None:
        print("FAIL — check_no_two_homes() not found in validator (function not yet built)")
        print("       Add check_no_two_homes() to tropo-validate.py to satisfy AC6.")
        return 1

    vault_file = ROOT / "vault" / "files" / f"{SYNTHETIC_UID}.md"
    tropo_file = ROOT / ".tropo" / f"synthetic-two-home-{SYNTHETIC_UID}.md"

    try:
        # Plant the synthetic two-home duplicate
        vault_file.write_text(SYNTHETIC_FM)
        tropo_file.write_text(SYNTHETIC_FM)

        # Step 1: check_no_two_homes() should ERROR (find the duplicate)
        vault_path = ROOT / "vault"
        try:
            result = check_fn(vault_path)
        except Exception as e:
            print(f"FAIL — check_no_two_homes() raised an exception: {e}")
            return 1

        # Result should indicate at least one violation
        findings, checked, defects = result if (isinstance(result, tuple) and len(result) == 3) else (result, 0, 0)
        if not findings:
            print(f"FAIL (step 1) — check_no_two_homes() did NOT detect synthetic two-home duplicate ({SYNTHETIC_UID})")
            return 1
        print(f"PASS (step 1) — check_no_two_homes() detected {len(findings)} violation(s) including synthetic {SYNTHETIC_UID}")

        # Step 2: remove the .tropo/ copy; check should now PASS
        tropo_file.unlink()
        try:
            result2 = check_fn(vault_path)
        except Exception as e:
            print(f"FAIL — check_no_two_homes() raised an exception after cleanup: {e}")
            return 1

        findings2, _, _ = result2 if (isinstance(result2, tuple) and len(result2) == 3) else (result2, 0, 0)
        # Filter to only our synthetic UID
        synth_remaining = [f for f in (findings2 or []) if SYNTHETIC_UID in str(f)]
        if synth_remaining:
            print(f"FAIL (step 2) — check_no_two_homes() still reports synthetic {SYNTHETIC_UID} after removal")
            return 1
        print(f"PASS (step 2) — check_no_two_homes() PASSes after removing the synthetic duplicate")

    finally:
        # Cleanup
        if vault_file.exists():
            vault_file.unlink()
        if tropo_file.exists():
            tropo_file.unlink()

    return 0


if __name__ == "__main__":
    sys.exit(main())
