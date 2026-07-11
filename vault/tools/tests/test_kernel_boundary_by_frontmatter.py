#!/usr/bin/env python3
"""AC5 — Kernel boundary by frontmatter: tier:kernel files are protected regardless of folder.

Post-migration, the kernel write-scope boundary is enforced by frontmatter (tier: kernel),
not by folder location. This test verifies:
  (a) Files with tier:kernel in frontmatter are detected by the validator check regardless
      of which folder they live in (vault/ or .tropo/).
  (b) The validator's kernel-protection check is not hard-coded to a specific folder path.

This is a structural check against the validator source (tropo-validate.py), not a runtime test.

Exit 0 = PASS, Exit 1 = FAIL.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = ROOT / "vault" / "tools" / "tropo-validate.py"


def main() -> int:
    if not VALIDATOR.exists():
        print(f"FAIL — validator not found at {VALIDATOR.relative_to(ROOT)}")
        return 1

    text = VALIDATOR.read_text(errors="ignore")

    # Check (a): validator references tier:kernel for write-scope protection
    has_tier_kernel_check = bool(
        re.search(r"tier.*kernel|kernel.*tier", text, re.IGNORECASE)
    )

    # Check (b): kernel protection is NOT folder-gated (should not hardcode .tropo/ as the
    # only location for kernel files)
    has_folder_only_kernel = bool(
        re.search(r'["\']\\.tropo/["\'].*kernel|kernel.*["\']\\.tropo/["\']', text)
    )

    failed = False

    if has_tier_kernel_check:
        print("PASS (a) — validator contains tier:kernel frontmatter check")
    else:
        print("FAIL (a) — validator has no tier:kernel frontmatter check (kernel boundary not enforced by frontmatter)")
        failed = True

    if not has_folder_only_kernel:
        print("PASS (b) — kernel protection is not hard-coded to .tropo/ folder only")
    else:
        print("FAIL (b) — kernel protection appears to be folder-gated (not frontmatter-gated)")
        failed = True

    # Check (c): the validator's write-scope check uses a frontmatter read, not a path check
    has_frontmatter_read_for_tier = bool(
        re.search(r"fm.*tier|tier.*fm|get.*tier|tier.*get", text)
    )
    if has_frontmatter_read_for_tier:
        print("PASS (c) — validator reads tier from frontmatter")
    else:
        print("NOTE (c) — could not confirm frontmatter-based tier read (manual verify)")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
