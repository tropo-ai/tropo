#!/usr/bin/env python3
"""test-harness-l2.py — L2 clean-room extraction + L1 gate for the Stranger-Walk Gate.

Dev-spec 554624e5 (v1.74 Stranger-Walk Gate). Talos lane.

Extracts the SHIPPED zip into a pristine isolated dir (no studio siblings, no network),
runs L1 (test-harness-check.py) inside the extracted tree, and prints the extracted path
so the conductor (Po) can dispatch cold-no-context sub-agents to walk it.

The cold agents are NOT dispatched here — this script is the extraction + L1 mechanical
layer only. Po (the conductor) reads the extracted path, dispatches the stranger sub-agents,
aggregates their verdicts, and writes cold-walk-verdict.json (the ship-gate artifact).

Usage:
  python3 test-harness-l2.py --release-zip <dist/tropo-os-vX.Y.Z.zip> [--work-dir <dir>] [--clean]

Exit codes:
  0  L1 PASS; EXTRACTED_PATH=<path> on the last output line (Po captures it for sub-agent dispatch)
  1  L1 FAIL; release fails its own mechanical regression inside the zip (do not dispatch strangers)
  2  Setup error (zip not found, already extracted without --clean, bad zip structure, etc.)
"""
import sys, os, argparse, shutil, subprocess, zipfile
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(description='L2 cold-room extraction + L1 gate (dev-spec 554624e5)')
    ap.add_argument('--release-zip', required=True,
                    help='Path to the SHIPPED zip (dist/tropo-os-vX.Y.Z.zip)')
    ap.add_argument('--work-dir', default=None,
                    help="Parent dir for extracted content. Default: sibling of the zip named "
                         "'cold-walk-staging' (e.g. tropo-releases/vX.Y.Z/cold-walk-staging/)")
    ap.add_argument('--clean', action='store_true',
                    help='Remove prior extracted dir before extracting (safe re-run)')
    args = ap.parse_args(argv)

    zip_path = Path(args.release_zip).resolve()
    if not zip_path.is_file():
        print(f'  ✗ release-zip not found: {zip_path}', file=sys.stderr)
        sys.exit(2)

    # Work dir: default to a sibling of the dist/ dir, named cold-walk-staging/
    if args.work_dir:
        work_dir = Path(args.work_dir).resolve()
    else:
        work_dir = zip_path.parent.parent / 'cold-walk-staging'

    extract_dir = work_dir / 'extracted'

    print('Step L2.1 — Cold-room extraction:')
    print(f'  zip:     {zip_path}')
    print(f'  extract: {extract_dir}')

    # Guard: don't silently overwrite a prior extraction
    if extract_dir.exists():
        if args.clean:
            shutil.rmtree(extract_dir)
            print('  ✓ Cleared prior extracted dir (--clean)')
        else:
            print(f'  ✗ Extracted dir already exists: {extract_dir}', file=sys.stderr)
            print('    Pass --clean to remove it before re-extracting.', file=sys.stderr)
            sys.exit(2)

    # Extract
    work_dir.mkdir(parents=True, exist_ok=True)
    print('  Extracting...')
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile as e:
        print(f'  ✗ Not a valid zip: {e}', file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f'  ✗ Extraction failed: {e}', file=sys.stderr)
        sys.exit(2)

    # Verify it looks like a Studio root (before running L1 proper)
    if not (extract_dir / 'START-TROPO.md').exists():
        print('  ✗ Extracted dir has no START-TROPO.md — wrong zip structure or wrong path.',
              file=sys.stderr)
        print(f'    Contents of {extract_dir}:', file=sys.stderr)
        entries = sorted(str(p.relative_to(extract_dir)) for p in extract_dir.iterdir())
        for e in entries[:10]:
            print(f'      {e}', file=sys.stderr)
        sys.exit(2)

    print(f'  ✓ Extracted to {extract_dir}')

    # Run L1 (test-harness-check.py) on the extracted dir
    # L1 is self-contained (stdlib-only) and ships inside every release; use the sibling copy.
    harness = Path(__file__).parent / 'test-harness-check.py'
    if not harness.exists():
        print(f'  ✗ test-harness-check.py not found at {harness}', file=sys.stderr)
        sys.exit(2)

    print('\nStep L2.2 — L1 mechanical regression (inside the extracted zip):')
    try:
        result = subprocess.run(
            [sys.executable, str(harness), '--release-dir', str(extract_dir)],
            capture_output=True, text=True, timeout=120
        )
    except subprocess.TimeoutExpired:
        print('  ✗ L1 timed out after 120s. Investigate.', file=sys.stderr)
        sys.exit(2)

    for line in (result.stdout or '').strip().splitlines():
        print(f'  {line}')
    if result.stderr:
        for line in (result.stderr or '').strip().splitlines():
            print(f'  [stderr] {line}', file=sys.stderr)

    if result.returncode != 0:
        print('\n  ✗ L1 FAIL — release fails its own mechanical regression inside the zip.')
        print('    Fix the failures before conducting the stranger walk.')
        print(f'    See test-report.md in {extract_dir}')
        sys.exit(1)

    print('\n  ✓ L1 PASS inside extracted zip.')

    # Step L2.3 — Validator in release-mode (dev-spec f8b51f4d D1, v1.74 Release-Self-Validates).
    # Runs the SHIPPED validator (inside the extracted release) against itself in --release mode.
    # --release mode: outward-refs (UIDs not in the subset index) resolve to [INFO] not [FAIL];
    # safe because the pre-build full-studio pass (0 FAILED) guarantees no genuine broken refs.
    print('\nStep L2.3 — Validator in release-mode (dev-spec f8b51f4d D1):')
    validator_candidates = (
        extract_dir / 'vault' / 'tools' / 'tropo-validate.py',
        extract_dir / 'vault' / 'tools' / 'd2b9c8e6.py',
    )
    shipped_validator = next(
        (candidate for candidate in validator_candidates if candidate.exists()),
        None,
    )
    if shipped_validator is None:
        print('  ✗ Shipped validator not found — L2.3 cannot be skipped.', file=sys.stderr)
        print('    Expected vault/tools/tropo-validate.py (or legacy UID filename d2b9c8e6.py).')
        sys.exit(2)
    else:
        try:
            vresult = subprocess.run(
                [sys.executable, str(shipped_validator), '--vault-path', str(extract_dir), '--release'],
                capture_output=True, text=True, timeout=300
            )
        except subprocess.TimeoutExpired:
            print('  ✗ Validator timed out after 300s. Investigate.', file=sys.stderr)
            sys.exit(2)

        # Print the summary line (last non-empty line of stdout)
        stdout_lines = (vresult.stdout or '').strip().splitlines()
        for line in stdout_lines[-5:]:
            print(f'  {line}')
        if vresult.returncode != 0:
            # Surface the first few FAIL lines for diagnosis
            fail_lines = [l for l in stdout_lines if '[FAIL]' in l]
            if fail_lines:
                print(f'  First failures ({len(fail_lines)} total):')
                for l in fail_lines[:5]:
                    print(f'    {l}')
            print('\n  ✗ L2.3 FAIL — release artifact fails its own validator in release-mode.')
            print('    Fix the FAIL items (these are genuine broken refs, not expected outward-refs).')
            print('    Run: python3 vault/tools/tropo-validate.py --vault-path <build> --release')
            sys.exit(1)
        print('\n  ✓ L2.3 PASS — release validates clean in release-mode (0 FAILED).')

    print('\n  ✓ L1 + L2.3 PASS inside extracted zip — safe to dispatch cold-boot stranger walk.')
    print('\n  Po conductor next steps:')
    print(f'    1. Dispatch cold sub-agents to walk {extract_dir}')
    print(f'       (reuse 6f3d2a18 persona-dispatch; per-persona clone the extracted dir)')
    print(f'    2. Aggregate per-persona verdicts')
    print(f'    3. Write cold-walk-verdict.json at tropo-releases/v<X.Y.Z>/cold-walk-verdict.json')
    print(f'       (shape: schema_version, release_version, walk_date, l1_result, l2_personas, overall)')
    print(f'    4. Re-run build-release.py (ship step) once verdict overall=PASS is on disk.')
    print(f'\nEXTRACTED_PATH={extract_dir}')
    sys.exit(0)


if __name__ == '__main__':
    main()
