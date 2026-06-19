"""validator — Runs validation checks on ship-artifact manifest entries (target-aware).

v1.43.0 Stream C extraction from build-release.py. Authored 2026-05-18 by argus-a72.

Per ship-artifact.capsule v1.3 (substrate UID eeb59ddf), entries must satisfy
validation invariants before build extraction proceeds:

- `canonical_source` resolves on disk (except for `skip` + `structure-only` modes)
- `parent` chain terminates at the manifest root for the target
- `target` array contains valid enum values (per Check 24 added in v1.42)
- Per-target subgraphs are acyclic (Rule 10 target-aware restatement)

This module exposes the MVP-level basic validator used by build-release.py.
The full 24-check validator lives at `.tropo/scripts/validate-release-manifest.py`
and `.tropo/scripts/tropo-validate.py`; this module wraps the canonical_source-resolution
check as the MVP gate for extraction.

v1.42 capsule v1.3 amendment: target-aware checks. The validator accepts `target`
parameter (default 'release') to filter target-appropriate validation rules.
"""

import os
import sys


def validate_manifest_basic(entries, vault_root, target='release'):
    """Phase 1 (basic) — verify canonical_source resolves for non-skip entries.

    MVP Phase E validation only. Full 23+1-check validator at
    .tropo/scripts/validate-release-manifest.py and .tropo/scripts/tropo-validate.py.
    Halts the calling script with sys.exit on any unresolved canonical_source.

    Args:
        entries: List of hydrated ship-artifact entries (from manifest_walker.load_manifest_entries).
        vault_root: Absolute path to the Studio root.
        target: Target key for target-aware filtering (currently informational; full
                target-aware checks live in tropo-validate.py).

    Returns:
        True if all entries pass basic validation. On failure, prints failures to stderr
        and exits the calling script with code 1 (consistent with pre-Stream-C behavior).
    """
    failures = []
    for e in entries:
        mode = e.get('source_mode', '')
        # skip + structure-only don't read from canonical_source — skip resolution check
        if mode in ('skip', 'structure-only'):
            continue
        cs = e.get('canonical_source', '')
        if not cs:
            failures.append(f'{e["uid"]}: missing canonical_source (source_mode={mode})')
            continue
        # Resolve argo-os/-prefixed path against vault_root
        path = cs[len('argo-os/'):] if cs.startswith('argo-os/') else cs
        abs_path = os.path.join(vault_root, path)
        if not os.path.exists(abs_path):
            failures.append(f'{e["uid"]}: canonical_source not found: {cs}')
    if failures:
        print(f'  ✗ Phase 1 validation FAILED ({len(failures)} canonical_source failures):', file=sys.stderr)
        for f in failures:
            print(f'    - {f}', file=sys.stderr)
        sys.exit(1)
    return True
