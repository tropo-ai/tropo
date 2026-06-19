#!/usr/bin/env python3
"""
---
uid: 3086287a
type: tool
name: tropo-test
title: tropo-test — Substrate Health CLI
description: 'User-facing CLI v1.0 — thin UX wrapper over `tropo-validate.py` that produces a single-gesture green/yellow/red substrate-health verdict in 3-5 lines. Modes: --quick (default), --json (CI/programmatic), --verbose (full validator output). Invoked via canonical `npm test` from the Studio root + `python3 .tropo/scripts/tropo-test.py` for users without node installed. Ships in v1.33.0 Stream H per arch-spec [f294f70b v0.3 LOCKED](f294f70b.md) §3.3.'
status: active
state: active
owner: argus
author: argus-a65
created: 2026-05-15
created_by: argus-a65
modified: 2026-05-15
modified_by: argus-a65
schema_version: 2
extraction_scope: ship
governed_by: 8dd772a0
member_of: []
aligned_with:
- f294f70b
- d2b9c8e6
tags:
- tool
- tropo-test
- substrate-health-check
- single-gesture-verdict
- npm-test-gesture
- v1.33.0-stream-h
- ships-in-v1.33.0
transport: cli
cli_command: "python3 vault/tools/3086287a.py [--quick] [--json] [--verbose]"
file_ext: md
script_path: vault/tools/3086287a.py
script_version: '1.0'
subsystem_hub:
- 76bab75f
- 8dd772a0
trigger_description: "Single-gesture green/yellow/red substrate health verdict."
capsule_version: '2.5'
belt: true
belt_invocation: "python3 vault/tools/3086287a.py"
belt_example: "python3 vault/tools/3086287a.py --quick"
---
"""
from __future__ import annotations

"""tropo-test.py — Tropo-OS substrate-health CLI.

Thin UX wrapper over `tropo-validate.py`. Produces a single-gesture green/yellow/red
substrate-health verdict in 3-5 lines. The canonical `npm test` gesture for the
Tropo-OS Studio.

Per v1.33.0 arch-spec [f294f70b v0.5 LOCKED] §3.3 (Stream H).

Usage:
    python3 .tropo/scripts/tropo-test.py                # --quick (default)
    python3 .tropo/scripts/tropo-test.py --quick        # explicit (same as default)
    python3 .tropo/scripts/tropo-test.py --json         # JSON output
    python3 .tropo/scripts/tropo-test.py --verbose      # TL;DR + full validator output
    python3 .tropo/scripts/tropo-test.py --json --verbose  # JSON with full output embedded

Flag composition (v0.5 — R3 sa.cold-boot-181 D0-1 absorption):
    The three flags are mutually compatible orthogonal switches per spec §3.3.
      --quick    — default mode; check substrate health via validator
      --json     — output shape: JSON (otherwise human-readable)
      --verbose  — content: include full validator output (otherwise TL;DR only)

Exit codes:
    0 — GREEN (validator passes; zero warnings)
    1 — YELLOW (validator passes; warnings present)
    2 — RED (validator failures; ship-blocker)
    3 — precondition error (not in a Tropo Studio)
    4 — substrate-degraded (validator subprocess timeout >120s)
    5 — script-error (validator subprocess crashed; not a substrate-defect)
    6 — argparse / CLI usage error (REMAPPED from default 2 to avoid RED collision)

Author: argus-a65 (v1.0); argus-a66 (v1.0.1 — R3 absorption)
Owner: argus
Domain: substrate-health verification; v1.33.0 Stream H deliverable.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


TOOL_NAME = 'tropo-test'
TOOL_VERSION = '1.0.2'  # v0.5 R3 RE-RUN cold-boot-182 D0-1 absorption: returncode-non-substrate-verdict reclassified as script-error

# Absolute path to the validator (sibling script in .tropo/scripts/) — per spec
# v0.2 §3.3 skeptic-075 P0-4 absorption (cwd-relative was fragile when invoked
# from subdirectory). Matches rebuild-vault.py:155 pattern.
SCRIPT_DIR = Path(__file__).resolve().parent
# v1.56 relocation repair (argus-a111 2026-06-12): this script moved from
# .tropo/scripts/ to vault/tools/, breaking the sibling lookup. Canonical
# validator IS the sibling d2b9c8e6.py here; legacy shim path kept as fallback
# (vault/tools-first + legacy fallback, the rebuild-vault.py A96 repair pattern).
VALIDATOR_PATH = SCRIPT_DIR / 'd2b9c8e6.py'
if not VALIDATOR_PATH.is_file():
    VALIDATOR_PATH = SCRIPT_DIR.parents[1] / '.tropo' / 'scripts' / 'tropo-validate.py'

# Subprocess timeout for validator invocation. Validator typically runs 5-10s
# on Argo-sized Studios; 120s envelope is generous.
VALIDATOR_TIMEOUT_SECONDS = 120


def resolve_studio_root() -> Optional[Path]:
    """Walk up from cwd looking for a `.tropo/` directory.

    Returns the resolved Studio root, or None if not in a Studio.
    """
    p = Path.cwd().resolve()
    while p != p.parent:
        if (p / '.tropo').is_dir():
            return p
        p = p.parent
    return None


def read_studio_version(studio_root: Path) -> str:
    """Read current Tropo-OS version from .tropo/version.md.

    Returns "unknown" if the file is missing or the Current-line isn't parseable.
    """
    version_md = studio_root / '.tropo' / 'version.md'
    if not version_md.is_file():
        return 'unknown'
    try:
        text = version_md.read_text()
    except OSError:
        return 'unknown'
    m = re.search(r'^\*\*Current:\*\*\s*v([\d.]+)', text, re.MULTILINE)
    return m.group(1) if m else 'unknown'


def run_validator(studio_root: Path) -> tuple[Optional[str], Optional[str], int]:
    """Invoke tropo-validate.py via subprocess; return (stdout, stderr, returncode).

    Passes `--vault-path <studio_root>` explicitly so the validator validates the
    Studio tropo-test resolved — not whichever Studio the validator's own
    SCRIPT_DIR walk-up finds (R3 sa.cold-boot-181 D1-1 absorption: nested or
    symlinked `.tropo/` directories caused tropo-test to lock onto one Studio
    while the validator subprocess locked onto a different one, producing
    silently-wrong cross-Studio verdicts).

    Returns (None, None, exit_code) on substrate-degraded or script-error class
    failures — exit_code is set by the caller's verdict logic.
    """
    if not VALIDATOR_PATH.is_file():
        return None, None, 5  # script-error: validator not found
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH),
             '--vault-path', str(studio_root)],
            capture_output=True,
            text=True,
            timeout=VALIDATOR_TIMEOUT_SECONDS,
            cwd=str(studio_root),
        )
        # Validator exit-code semantics (from .tropo/scripts/tropo-validate.py docstring):
        #   0 — all checks passed
        #   1 — at least one check failed (normal RED outcome; stdout has FAIL details)
        #   2 — could not resolve vault root or other operational error
        # tropo-test treats 0/1 as substrate verdicts; anything else (notably 2)
        # is a validator-internal failure that must not be silently classified
        # as GREEN. R3 RE-RUN sa.cold-boot-182 D0-1 absorption: previously
        # `run_validator` returned the empty-stdout + exit 2 verbatim;
        # `parse_validator_output('')` returned all-zero counts; `compute_verdict`
        # returned GREEN exit 0 on fake/empty/symlinked-empty Studios. Fix: any
        # validator returncode outside {0, 1} is reclassified as script-error.
        if result.returncode not in (0, 1):
            return None, result.stderr, 5
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as e:
        return e.stdout, e.stderr, 4  # substrate-degraded
    except Exception:
        return None, None, 5  # script-error


# Regex patterns for parsing validator output
SUMMARY_RE = re.compile(r'Summary:\s*(\d+)\s*passed,\s*(\d+)\s*failed,\s*(\d+)\s*warnings')
UID_XREF_SECTION_RE = re.compile(
    r'---\s*UID Cross-References.*?---\s*\n(.*?)(?=\n---|\Z)',
    re.DOTALL,
)
VERSION_CONSISTENCY_SECTION_RE = re.compile(
    r'---\s*Version Consistency.*?---\s*\n(.*?)(?=\n---|\Z)',
    re.DOTALL,
)


def parse_validator_output(stdout: str) -> dict:
    """Extract pass/fail/warnings counts + the two v1.33.0 check status indicators.

    R3 absorption (sa.skeptic-078 P1-4): pure-enum status strings; counts in
    separate integer fields. Per spec §3.3 v0.5 JSON shape contract.
    """
    parsed = {
        'validator_passed': 0,
        'validator_failed': 0,
        'validator_warnings': 0,
        'uid_cross_references': 'unknown',
        'uid_cross_references_defect_count': 0,
        'uid_cross_references_stale_count': 0,
        'version_consistency': 'unknown',
    }

    m = SUMMARY_RE.search(stdout)
    if m:
        parsed['validator_passed'] = int(m.group(1))
        parsed['validator_failed'] = int(m.group(2))
        parsed['validator_warnings'] = int(m.group(3))

    # Checks-fail-loud fix (v1.70; talos-t15 2026-06-13 per A111 finding):
    # Some validator blocks report [ERROR]-severity sub-items but are counted as
    # warnings at the Summary level (the [FAIL/WARN] block pattern). This makes
    # tropo-test report YELLOW when there are visible [ERROR] lines — a misleading
    # green-ish verdict for red-class findings.
    # Fix: if the Summary says 0 failed but [ERROR] lines exist in the output,
    # count them and treat them as failures so the verdict flips to RED.
    if parsed['validator_failed'] == 0:
        error_lines = [ln for ln in stdout.splitlines()
                       if re.match(r'\s*\[ERROR\]', ln)]
        if error_lines:
            parsed['validator_failed'] = len(error_lines)
            parsed['_error_lines_promoted'] = error_lines  # for verbose/json consumers

    xref = UID_XREF_SECTION_RE.search(stdout)
    if xref:
        section = xref.group(1)
        # Defect-count (FAIL class) — section-header [FAIL] line carries it.
        count_m = re.search(r'\[FAIL\]\s*(\d+)\s*unresolved', section)
        if count_m:
            parsed['uid_cross_references_defect_count'] = int(count_m.group(1))
        # Stale-index count (INFO class) — summary line at end of section.
        stale_m = re.search(r'\[INFO\]\s*(\d+)\s*cross-reference', section)
        if stale_m:
            parsed['uid_cross_references_stale_count'] = int(stale_m.group(1))
        # Status enum: FAIL > PASS (FAIL wins if both present, which shouldn't happen)
        if '[FAIL]' in section:
            parsed['uid_cross_references'] = 'FAIL'
        elif '[PASS]' in section:
            parsed['uid_cross_references'] = 'PASS'

    ver = VERSION_CONSISTENCY_SECTION_RE.search(stdout)
    if ver:
        section = ver.group(1)
        if '[WARN]' in section:
            parsed['version_consistency'] = 'WARN'
        elif '[PASS]' in section:
            parsed['version_consistency'] = 'PASS'
        elif '[INFO]' in section:
            parsed['version_consistency'] = 'INFO'

    return parsed


def compute_verdict(parsed: dict) -> tuple[str, int]:
    """Compute green/yellow/red verdict + exit code from parsed validator output.

    Returns (verdict_str, exit_code).
    """
    if parsed['validator_failed'] > 0:
        return 'red', 2
    if parsed['validator_warnings'] > 0:
        return 'yellow', 1
    return 'green', 0


def _xref_human_summary(parsed: dict) -> str:
    """Format the UID-cross-references TL;DR line (status + count + stale-context)."""
    status = parsed['uid_cross_references']
    defects = parsed['uid_cross_references_defect_count']
    stale = parsed['uid_cross_references_stale_count']
    if status == 'FAIL':
        defect_word = 'defect' if defects == 1 else 'defects'
        suffix = f' (also {stale} index-stale)' if stale else ''
        return f'FAIL ({defects} {defect_word}){suffix}'
    if status == 'PASS':
        if stale:
            stale_word = 'reference' if stale == 1 else 'references'
            return f'PASS ({parsed["validator_passed"]} checks; {stale} index-stale {stale_word} — run `npm run vault:rebuild`)'
        return 'PASS'
    return status  # unknown


def format_human(studio_version: str, parsed: dict, verdict: str) -> str:
    """Format the TL;DR substrate-health output (3-5 lines)."""
    color_map = {
        'green': 'GREEN — substrate healthy.',
        'yellow': 'YELLOW — substrate has warnings.',
        'red': 'RED — substrate has failures.',
    }
    lines = [
        f'Tropo-OS Substrate Health Check — v{studio_version}',
        '',
        f"  Validator: {parsed['validator_passed']} passed, "
        f"{parsed['validator_failed']} failed, "
        f"{parsed['validator_warnings']} warnings",
        f"  UID cross-references: {_xref_human_summary(parsed)}",
        f"  Version consistency: {parsed['version_consistency']}",
        '',
        color_map.get(verdict, f'{verdict.upper()} — verdict unknown.'),
        '',
        'Run --verbose for full validator output. Run --json for machine-readable format.',
    ]
    return '\n'.join(lines)


def format_json(studio_version: str, parsed: dict, verdict: str,
                exit_code: int, full_output: Optional[str] = None) -> str:
    """Format machine-readable JSON output per spec §3.3 v0.5 shape contract.

    R3 absorption (sa.skeptic-078 P1-4): status fields are pure enums; counts
    are separate integers. `tool` + `tool_version` retained per spec §3.3 v0.5
    amendment (operationally useful for CI debugging; small additive widening
    of the contract).
    """
    payload = {
        'tool': TOOL_NAME,
        'tool_version': TOOL_VERSION,
        'tropo_os_version': studio_version,
        'validator_passed': parsed['validator_passed'],
        'validator_failed': parsed['validator_failed'],
        'validator_warnings': parsed['validator_warnings'],
        'uid_cross_references': parsed['uid_cross_references'],
        'uid_cross_references_defect_count': parsed['uid_cross_references_defect_count'],
        'uid_cross_references_stale_count': parsed['uid_cross_references_stale_count'],
        'version_consistency': parsed['version_consistency'],
        'verdict': verdict,
        'exit_code': exit_code,
        'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    if full_output is not None:
        payload['full_validator_output'] = full_output
    return json.dumps(payload, separators=(',', ':'))


class _ArgparseRemap(argparse.ArgumentParser):
    """argparse.ArgumentParser subclass that remaps usage-error exits from 2 to 6.

    R3 absorption (sa.cold-boot-181 D0-1 / sa.skeptic-078 P1-1): argparse's default
    failure exit code is 2, which collides with substrate-RED. CI scripts running
    `npm test -- --bad-flag` would see exit 2 and report "substrate RED" when
    actually argparse refused the args. Remap to exit 6 (CLI usage error class)
    so substrate-verdict codes 0/1/2 stay reserved for verdict signaling.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f'{self.prog}: error: {message}', file=sys.stderr)
        sys.exit(6)


def main() -> int:
    parser = _ArgparseRemap(
        prog='tropo-test',
        description='Tropo-OS substrate-health check. One gesture. One verdict.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Flags are orthogonal and mutually compatible:\n'
            '  --quick    default mode; check substrate health\n'
            '  --json     output shape: JSON (otherwise human-readable)\n'
            '  --verbose  content: include full validator output (otherwise TL;DR only)\n'
            'Combinations: --json --verbose embeds full output as a JSON field.\n'
        ),
    )
    # All three flags are orthogonal switches; spec §3.3 v0.5 "mutually compatible".
    # --quick is the default mode; passing it explicitly is a no-op (kept for
    # CLI symmetry + script-readability).
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Default mode; check substrate health (no-op flag for symmetry).',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output shape: JSON (machine-readable for CI/programmatic consumers).',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Content: include full validator output (otherwise TL;DR only).',
    )
    args = parser.parse_args()

    # Resolve Studio root
    studio_root = resolve_studio_root()
    if studio_root is None:
        print('ERROR: not inside a Tropo Studio (no .tropo/ directory found '
              'walking up from cwd)', file=sys.stderr)
        return 3

    # Run validator
    stdout, stderr, return_code = run_validator(studio_root)

    if return_code == 4:
        print(f'ERROR: validator subprocess timeout (>{VALIDATOR_TIMEOUT_SECONDS}s); '
              f'substrate may be degraded', file=sys.stderr)
        if stderr:
            print(stderr, file=sys.stderr)
        return 4

    if stdout is None:
        # Script error — validator crashed or path missing
        print('ERROR: validator subprocess failed (path missing or crash)', file=sys.stderr)
        if stderr:
            print(stderr, file=sys.stderr)
        return 5

    # Parse + compute verdict
    studio_version = read_studio_version(studio_root)
    parsed = parse_validator_output(stdout)
    verdict, exit_code = compute_verdict(parsed)

    # Format + emit per orthogonal flag composition (v0.5):
    #   --json alone               → JSON output, TL;DR data only
    #   --verbose alone            → human output: TL;DR + full validator stdout
    #   --json --verbose           → JSON output with full_validator_output field
    #   default / --quick alone    → human output: TL;DR only
    if args.json:
        full_for_json = stdout if args.verbose else None
        print(format_json(studio_version, parsed, verdict, exit_code, full_for_json))
    elif args.verbose:
        print(format_human(studio_version, parsed, verdict))
        print()
        print('=' * 70)
        print('Full validator output:')
        print('=' * 70)
        print(stdout)
    else:  # --quick (default)
        print(format_human(studio_version, parsed, verdict))

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
