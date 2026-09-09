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
modified: '2026-07-05'
modified_by: vela-v63
v0_1_fix_note: "vela-v63, 2026-07-05 — run_validator() now passes --customer to the tropo-validate.py subprocess. Without it, this tool ALWAYS reported RED inside any shipped box: every reference to non-shipped source-studio-only content (the expected 'vendor outward-ref' class, ~200+ in a typical release) was being counted as a real FAIL instead of downgraded to INFO. Confirmed by direct comparison on the built v1.80.0 box: plain invocation = 89 passed/214 failed/199 UID-cross-ref FAIL; --customer = 91 passed/0 failed. This tool's whole purpose is running INSIDE an adopted customer studio (per its own description below) — it should never have been checking with source-studio strictness. Found because Step 10.5a (S2 shipped self-test in-box gate, v1.80) is a hard build-refusing gate and this bug meant NO release could ever pass it."
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
cli_command: "python3 vault/tools/tropo-test.py [--quick] [--json] [--verbose]"
file_ext: md
script_path: vault/tools/tropo-test.py
script_version: '1.0'
subsystem_hub:
- 76bab75f
- 8dd772a0
trigger_description: "Single-gesture green/yellow/red substrate health verdict."
capsule_version: '2.5'
belt: true
belt_invocation: "python3 vault/tools/tropo-test.py"
belt_example: "python3 vault/tools/tropo-test.py --quick"
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
    3 — precondition error (Python below 3.9 or not in a Tropo Studio), and
        NOT-INITIALIZED: a correct Studio that has not built its index yet
    4 — substrate-degraded (validator subprocess timeout >VALIDATOR_TIMEOUT_SECONDS)
    5 — script-error (validator subprocess crashed; not a substrate-defect)
    6 — argparse / CLI usage error (REMAPPED from default 2 to avoid RED collision)
    7 — initialization failed (auto-init ran and the index would not build;
        NO health verdict was produced)

WRITES: this tool is no longer read-only. When the validator reports the Studio
has no index, it runs the index build (Mike-ruled 2026-09-08) — which on a Studio
with no identity also mints one, because the build does. Pass --no-auto-init for
the read-only behaviour; every programmatic caller should.

THREE OUTCOMES THAT WERE TWO (f0152b4c4ef4, 2026-09-08). A freshly unzipped box
ships without its index by design and builds it on first use. Until 2026-09-08
that state was indistinguishable here from a crashed validator: the guard below
rewrote every code outside {0,1} into script-error 5, so `npm test` in a perfect
box printed "validator subprocess failed (path missing or crash)" and swallowed
the validator's own correct answer and the one command that fixes it. Worse in
the other direction, exit 1 is BOTH the validator's "at least one check failed"
AND CPython's code for an uncaught exception, so a validator that died before
printing its Summary parsed to all-zero counts and reported GREEN.

Not-initialized, healthy and aborted are now three separate things, and neither
of the two silent conversions can happen: a missing `Summary:` line is never a
verdict, and the no-index answer is never a crash.

MACHINE READERS MUST NOT READ THE EXIT CODE (see NOT_INITIALIZED_STATUS below).
Whatever a human's terminal shows, programmatic consumers read the status line or
the JSON `status` field. That is what lets the stranger-facing exit code be a
one-line decision rather than a contract every gate depends on.

Author: argus-a65 (v1.0); argus-a66 (v1.0.1 — R3 absorption)
Owner: argus
Domain: substrate-health verification; v1.33.0 Stream H deliverable.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


TOOL_NAME = 'tropo-test'
TOOL_VERSION = '1.0.2'  # v0.5 R3 RE-RUN cold-boot-182 D0-1 absorption: returncode-non-substrate-verdict reclassified as script-error
MIN_PYTHON_VERSION = (3, 9)
_VERSION_COMPONENT = r'(?:0|[1-9][0-9]*)'
_SEMANTIC_VERSION = (
    rf'{_VERSION_COMPONENT}\.{_VERSION_COMPONENT}\.{_VERSION_COMPONENT}'
)
BARE_VERSION_RE = re.compile(
    rf'^v({_SEMANTIC_VERSION})$'
)
LEGACY_VERSION_RE = re.compile(
    rf'^\*\*Current:\*\*[ \t]+v({_SEMANTIC_VERSION})$',
    re.MULTILINE,
)
CURRENT_MARKER_RE = re.compile(r'\*\*Current\s*:\s*\*\*')
VERSION_LIKE_RE = re.compile(r'(?<![A-Za-z0-9])v[^\s]*\.[^\s]*\.[^\s]*')

# Absolute path to the validator (sibling script in .tropo/scripts/) — per spec
# v0.2 §3.3 skeptic-075 P0-4 absorption (cwd-relative was fragile when invoked
# from subdirectory). Matches rebuild-vault.py:155 pattern.
SCRIPT_DIR = Path(__file__).resolve().parent
# v1.56 relocation repair (argus-a111 2026-06-12): this script moved from
# .tropo/scripts/ to vault/tools/, breaking the sibling lookup. Canonical
# validator IS the sibling d2b9c8e6.py here; legacy shim path kept as fallback
# (vault/tools-first + legacy fallback, the rebuild-vault.py A96 repair pattern).
VALIDATOR_PATH = SCRIPT_DIR / 'tropo-validate.py'
if not VALIDATOR_PATH.is_file():
    VALIDATOR_PATH = SCRIPT_DIR.parents[1] / '.tropo' / 'scripts' / 'tropo-validate.py'

# Subprocess timeout for validator invocation. Validator typically runs 2-3 min
# on Argo-sized Studios. Default 600s; override via TROPO_VALIDATE_TIMEOUT env var.
VALIDATOR_TIMEOUT_SECONDS = int(os.environ.get('TROPO_VALIDATE_TIMEOUT', '600'))

# ── The not-initialized outcome (f0152b4c4ef4) ───────────────────────────────
#: The stable, greppable signal a MACHINE reads. Deliberately not the exit code:
#: `build-box-self-test` used to judge one integer and nothing else, so the exit
#: code was a contract every gate depended on and no gate could see anything
#: else. Readers key on this line (or the JSON `status` field); the exit code
#: below is then purely the stranger's terminal, and can change without touching
#: a single gate.
NOT_INITIALIZED_STATUS = 'STATUS: NOT INITIALIZED'

#: The validator's own recognizable answer for the same state. Matched on its
#: OUTPUT, never on its exit code alone — exit 2 is also its "operational error",
#: and conflating the two is how this state became a crash report.
NOT_INITIALIZED_MARKER = 'This Studio has no index yet'

#: The one command that resolves it. Printed verbatim to the human, and kept here
#: rather than re-typed at each site so the message and the gate cannot drift.
NOT_INITIALIZED_CURE = 'python3 vault/tools/tropo-rebuild-index.py --apply --vault-path .'

#: DECISION 4 (v1.96 board), open at time of writing and one line to change.
#: Argus A175 ruled a distinct non-zero as the record's owner; Metis G126 moved
#: her lean to it as release driver; Mike's word settles it. Set to 0 for the
#: other option — nothing else in this file or in any gate changes, which is the
#: whole point of NOT_INITIALIZED_STATUS above.
NOT_INITIALIZED_EXIT = 3

#: Internal sentinel for the not-initialized outcome as it travels out of
#: run_validator. Deliberately not a real exit code: the exit code is decision
#: 4's to change, and this must keep meaning the same thing if it does.
_OUTCOME_NOT_INITIALIZED = 'not-initialized'

#: AUTO-INITIALIZE (Mike-ruled 2026-09-08, in session). Decision 4 asked which
#: exit code a stranger should get on a correct-but-unbuilt box. Mike dissolved
#: the question instead of answering it: build the index and ask again, so the
#: state a stranger is asked to interpret stops existing. Decision 4's constant
#: above is retained and still governs the --no-auto-init path.
#:
#: ONE SOURCE. The argv is DERIVED from NOT_INITIALIZED_CURE — the same string
#: printed to the human — so the command we run and the command we would have
#: told them to run can never drift into two readers of one fact. Only the
#: interpreter is substituted, so a venv/py3.9 box runs the same one it is on.
#: test_the_auto_init_command_is_the_printed_cure enforces the derivation.
AUTO_INIT_ARGV = ([sys.executable] + NOT_INITIALIZED_CURE.split()[1:]
                  + ['--no-genesis'])

#: WHY THE DELTA, and why the cure itself is NOT changed to match.
#:
#: Without --no-genesis the rebuild also mints .tropo/studio-identity.md and a
#: starter vault-entity pair (tropo-rebuild-index.py:7555-7568). Measured on a
#: real box: a 1,184-byte identity file appeared where none existed, created by
#: running the health check. That is the wrong owner for that act. The boot
#: contract halts on a Studio with no identity and routes to Po, who mints it at
#: her first greeting; an executive boot never mints identity, and neither
#: should `npm test`. Mike, to Metis, ~18:20Z the same day: "I expect most users
#: will initialize their studio with Po." It would also arm build-no-studio-
#: identity on any tree this ran against.
#:
#: The printed cure is deliberately left alone. That exact string is not ours
#: alone — tropo-validate.py:14189 prints it, tropo-studio-status.py:319 holds
#: it as GENESIS_CURE, and tropo-genesis-companions.py:714 quotes it. Editing
#: our copy to match this argv would put four readers of one fact out of step to
#: fix a problem that only exists on the automated path. A HUMAN typing that
#: command is making a choice and may well want genesis; a MACHINE doing it as a
#: side effect of a health check must not. So the delta lives here, exactly one
#: flag wide, and a test asserts it is exactly that.

#: Machine-readable signal that initialization itself failed. This is the one
#: question that MOVED rather than disappeared: an unbuilt box is no longer a
#: state a stranger must interpret, but a box whose index will not build is.
#: Loud, non-zero, and it names the command so the human can run it by hand.
#: The auto-init command as a human would retype it. A failure message must name
#: what ACTUALLY RAN, not the cure: the two differ by --no-genesis, so telling the
#: human to run the cure to "see the full error" would hand them a command that
#: may not reproduce the failure AND that mints the very identity this tool just
#: declined to mint, unwarned. Derived from the argv, so it cannot drift from it.
AUTO_INIT_COMMAND_DISPLAY = ' '.join(['python3'] + AUTO_INIT_ARGV[1:])

AUTO_INIT_FAILED_STATUS = 'STATUS: INITIALIZATION FAILED'
#: 7, not 6. 6 is already the argparse/CLI-usage-error code (see the table above
#: and _ArgparseRemap.error), which itself exists because argparse's default of 2
#: collided with substrate-RED. Shipping 6 here would have rebuilt that exact
#: collision one layer up: `--bogus-flag` and "your index would not build" would
#: have been the same integer. Caught in adversarial review, verified by hand.
AUTO_INIT_FAILED_EXIT = 7

#: Seconds allowed for the index build. A large Studio takes ~46s; the release
#: box is far smaller. Generous, and bounded so a wedged build cannot hang CI.
AUTO_INIT_TIMEOUT_SECONDS = int(os.environ.get('TROPO_INDEX_BUILD_TIMEOUT', '900'))


def build_index(studio_root: Path) -> "tuple[bool, str, str]":
    """Run the index build a not-initialized Studio needs. Returns (ok, out, err).

    This is the auto-initialize half of Mike's 2026-09-08 ruling. It runs
    AUTO_INIT_ARGV, which is derived from NOT_INITIALIZED_CURE, so it is by
    construction the same command this tool would otherwise have printed and
    asked the human to run.

    It is NOT called unless the validator itself answered not-initialized. That
    matters: this tool does not decide whether a Studio is initialized. The
    validator owns that question and already answers it (NOT_INITIALIZED_MARKER),
    and a second file-existence test here would be two readers of one fact — an
    index that exists but is empty would then be called initialized by one reader
    and not the other. Reuse over re-derivation, deliberately.
    """
    # THE RESIDUE PROBLEM (found in adversarial review, reproduced by hand before
    # fixing). A build that writes some rows and then dies leaves a partial index
    # on disk. The validator's question is "is there an index", not "is it whole",
    # so the NEXT run answers yes, skips auto-init, and prints GREEN — substrate
    # healthy, having repaired nothing. That is the precise false-GREEN class this
    # tool was cured of on 2026-09-08, and auto-init would have rebuilt it one
    # layer up: before this change a human ran the build and watched it fail, so
    # the half-state was never created unattended.
    #
    # The cure is to leave the Studio in the honest state it was in before we
    # touched it. Only files this build CREATED are removed — an artifact that
    # already existed is the user's and is never ours to delete. Derived,
    # gitignored, per-machine products only; nothing governed is touched, so the
    # deletion discipline (soft-delete via tropo-recycle.py) is not in play.
    derived = [studio_root / 'vault' / name for name in (
        '00-index.jsonl', '00-archive-index.jsonl',
        '00-index.sqlite', '00-project-tree.jsonl')]
    pre_existing = {d for d in derived if d.exists()}

    try:
        result = subprocess.run(
            AUTO_INIT_ARGV,
            capture_output=True,
            text=True,
            timeout=AUTO_INIT_TIMEOUT_SECONDS,
            cwd=str(studio_root),
        )
        ok = result.returncode == 0
        out, err = result.stdout or '', result.stderr or ''
    except subprocess.TimeoutExpired:
        ok, out, err = False, '', ('index build exceeded %ds'
                                   % AUTO_INIT_TIMEOUT_SECONDS)
    except OSError as exc:
        ok, out, err = False, '', '%s: %s' % (type(exc).__name__, exc)

    if not ok:
        removed = []
        for d in derived:
            if d in pre_existing or not d.exists():
                continue
            try:
                d.unlink()
                removed.append(d.name)
            except OSError:
                # Could not clean up. Say so — a partial index we FAILED to
                # remove is exactly the state that reads GREEN next run, and
                # silence here would be the whole defect back again.
                err += ('\nWARNING: a partial %s was left behind and could not '
                        'be removed; the next health check may read it as a '
                        'built index.' % d.name)
        if removed:
            err += ('\nPartial output removed so the next run reports the truth '
                    'rather than reading it as a built index: %s'
                    % ', '.join(removed))
    return (ok, out, err)


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

    Accept the canonical bare ``vMAJOR.MINOR.PATCH`` stamp and the legacy
    ``**Current:** vMAJOR.MINOR.PATCH`` line. Return "unknown" otherwise.
    """
    version_md = studio_root / '.tropo' / 'version.md'
    if not version_md.is_file():
        return 'unknown'
    try:
        text = version_md.read_text()
    except OSError:
        return 'unknown'
    content_lines = [line.strip() for line in text.splitlines() if line.strip()]
    canonical = (
        BARE_VERSION_RE.fullmatch(content_lines[0])
        if len(content_lines) == 1
        else None
    )
    if canonical:
        return canonical.group(1)
    legacy_matches = [
        match
        for line in content_lines
        if (match := LEGACY_VERSION_RE.fullmatch(line)) is not None
    ]
    legacy = (
        legacy_matches[0]
        if len(legacy_matches) == 1
        and len(CURRENT_MARKER_RE.findall(text)) == 1
        and len(VERSION_LIKE_RE.findall(text)) == 1
        else None
    )
    return legacy.group(1) if legacy else 'unknown'


def python_version_preflight(
    version_info=None,
    executable: Optional[str] = None,
) -> bool:
    """Fail loudly before health work when the interpreter is below the L1 floor."""
    actual_info = sys.version_info if version_info is None else version_info
    actual_executable = sys.executable if executable is None else executable
    if tuple(actual_info[:2]) >= MIN_PYTHON_VERSION:
        return True
    actual_version = '.'.join(str(part) for part in actual_info[:3])
    print(
        'ERROR: Tropo L1 tooling requires Python >= 3.9; '
        f'actual interpreter: {actual_executable}; actual version: Python {actual_version}',
        file=sys.stderr,
    )
    return False


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
             '--vault-path', str(studio_root), '--customer'],
            capture_output=True,
            text=True,
            timeout=VALIDATOR_TIMEOUT_SECONDS,
            cwd=str(studio_root),
        )
        # Validator exit-code semantics (from vault/tools/tropo-validate.py docstring):
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
        #
        # THREE OUTCOMES, NOT TWO (f0152b4c4ef4, talos-t65 2026-09-08). The
        # {0,1} whitelist above was added for a real defect and is kept; what it
        # could not do is tell the two NON-verdict states apart from each other.
        #
        # (a) NOT INITIALIZED. The validator answers this correctly and kindly,
        #     and exits 2 — the same code it uses for an operational error, which
        #     is why the code alone can never decide it. Matched on the
        #     validator's own OUTPUT, so a future exit-code change cannot silently
        #     turn this back into a crash report.
        if NOT_INITIALIZED_MARKER in (result.stdout or ''):
            return result.stdout, result.stderr, _OUTCOME_NOT_INITIALIZED
        # (b) ABORTED, including the case the old guard could not see at all:
        #     exit 1 is BOTH "at least one check failed" and CPython's uncaught
        #     exception, and tropo-validate.py has no excepthook. A validator that
        #     died mid-run reached parse_validator_output with no `Summary:` line,
        #     parsed to all-zero counts, and reported GREEN. The Summary check
        #     lives in main() where the counts are; here we only refuse the codes
        #     that were never verdicts.
        if result.returncode not in (0, 1):
            return None, result.stderr, 5
        # (c) A real verdict — 0 or 1 with output to parse.
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
        'summary_present': False,
        'validator_passed': 0,
        'validator_failed': 0,
        'validator_warnings': 0,
        'uid_cross_references': 'unknown',
        'uid_cross_references_defect_count': 0,
        'uid_cross_references_stale_count': 0,
        'version_consistency': 'unknown',
    }

    # SUMMARY PRESENCE IS RECORDED, NOT ASSUMED (f0152b4c4ef4, talos-t65).
    # Every count below defaults to 0, so output with no `Summary:` line — a
    # validator that aborted before printing one — used to parse as "0 passed,
    # 0 failed, 0 warnings" and compute GREEN. Zero defects and no answer are
    # not the same claim. Callers must refuse a verdict when this is False.
    m = SUMMARY_RE.search(stdout)
    parsed['summary_present'] = bool(m)
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

    GREEN REQUIRES A COMPLETED CHECK (f0152b4c4ef4, talos-t65 2026-09-08). Argus
    A175's direction, in his words: "no crash/empty output can look like
    successful initialization." Without the guard below, a validator that died
    before printing its `Summary:` line produced all-zero counts here and this
    function answered GREEN, exit 0 — a pass having examined nothing, which is
    the case Mike ruled earned fail-closed at the outward boundary. `aborted` is
    a non-verdict and carries the script-error code, because that is what it is.
    """
    if not parsed.get('summary_present', False):
        return 'aborted', 5
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
    if not python_version_preflight():
        return 3

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
    parser.add_argument(
        '--warn-ok',
        action='store_true',
        help=(
            'CI mode: exit 0 on GREEN or YELLOW; only RED (real failures) exits '
            'non-zero. Warnings are the normal state of a healthy shipped Studio, '
            'so a CI gate that fails on them fails on everything.'
        ),
    )
    parser.add_argument(
        '--no-auto-init',
        action='store_true',
        help=(
            'Do not build the index when the Studio has no index yet; report '
            'NOT INITIALIZED and stop. EVERY programmatic caller wants this. '
            'Argus A175 ruled on the record (f0152b4c4ef4): "Do not silently '
            'initialize a customer\'s live Studio as a diagnostic side effect" '
            '— and a build gate that ran the default would mutate the very box '
            'it is sealing, and arm build-no-studio-identity on the same tree. '
            'Auto-init is for a human who typed `npm test`; gates opt out.'
        ),
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

    # AUTO-INITIALIZE — Mike's ruling, 2026-09-08. The validator (not this tool)
    # said the Studio has no index. Build it, then ask the validator again, ONCE.
    # No loop: if it still says not-initialized after a successful build, that is
    # a real failure and gets reported, not retried.
    #
    # Progress goes to STDERR on purpose. The human running `npm test` still sees
    # it, and `--json` stdout stays a single parseable object for CI.
    if return_code == _OUTCOME_NOT_INITIALIZED and not args.no_auto_init:
        print('This Studio has no index yet. Building it now — this happens once.',
              file=sys.stderr)
        print(f'    {NOT_INITIALIZED_CURE}', file=sys.stderr)
        ok, build_out, build_err = build_index(studio_root)
        if not ok:
            # The status line goes to STDOUT as well as stderr. This tool's own
            # contract tells machine readers to key on the status line, and the
            # sibling NOT INITIALIZED state prints to stdout; a consumer reading
            # stdout for this state was getting zero bytes.
            # stdout copy for machine readers keying on the status line, but
            # NEVER in --json mode: that payload must stay a single parseable
            # object. The NOT INITIALIZED branch has the same shape.
            if not args.json:
                print(AUTO_INIT_FAILED_STATUS)
            print(AUTO_INIT_FAILED_STATUS, file=sys.stderr)
            print(file=sys.stderr)
            print('The index build failed, so NO HEALTH VERDICT HAS BEEN PRODUCED.',
                  file=sys.stderr)
            print('Run it by hand from the Studio root to see the full error.',
                  file=sys.stderr)
            print('This is the exact command that failed — note --no-genesis, '
                  'which keeps identity minting with Po:', file=sys.stderr)
            print(file=sys.stderr)
            print(f'    {AUTO_INIT_COMMAND_DISPLAY}', file=sys.stderr)
            # BOTH streams. The sibling branch below already prints stdout's
            # tail; this one printed only stderr, so a rebuilder that explains
            # itself on stdout ("REFUSED: index shrink floor violated…") had its
            # reason captured and thrown away, leaving the human told that
            # something failed but not what.
            if build_out:
                tail = [ln for ln in build_out.splitlines() if ln.strip()][-8:]
                if tail:
                    print(file=sys.stderr)
                    print('--- last lines of the index build ---', file=sys.stderr)
                    for ln in tail:
                        print(ln, file=sys.stderr)
            if build_err:
                print(file=sys.stderr)
                print('--- index build stderr ---', file=sys.stderr)
                print(build_err, file=sys.stderr)
            if args.json:
                print(json.dumps({
                    'tool': TOOL_NAME,
                    'tool_version': TOOL_VERSION,
                    'tropo_os_version': read_studio_version(studio_root),
                    'status': 'initialization-failed',
                    'verdict': 'none',
                    'health_verdict_produced': False,
                    'cure': NOT_INITIALIZED_CURE,
                    'exit_code': AUTO_INIT_FAILED_EXIT,
                    'timestamp': datetime.now(timezone.utc).strftime(
                        '%Y-%m-%dT%H:%M:%SZ'),
                }, separators=(',', ':')))
            return AUTO_INIT_FAILED_EXIT

        print('Index built. Re-running the health check.', file=sys.stderr)
        stdout, stderr, return_code = run_validator(studio_root)

        if return_code == 4:
            print(f'ERROR: validator subprocess timeout '
                  f'(>{VALIDATOR_TIMEOUT_SECONDS}s) after the index build; '
                  f'substrate may be degraded', file=sys.stderr)
            if stderr:
                print(stderr, file=sys.stderr)
            return 4

        if return_code == _OUTCOME_NOT_INITIALIZED:
            # The build reported success and the Studio still has no index. That
            # is not the stranger's problem to interpret and it is not a retry
            # case — something is wrong with the build itself.
            # stdout copy for machine readers keying on the status line, but
            # NEVER in --json mode: that payload must stay a single parseable
            # object. The NOT INITIALIZED branch has the same shape.
            if not args.json:
                print(AUTO_INIT_FAILED_STATUS)
            print(AUTO_INIT_FAILED_STATUS, file=sys.stderr)
            print(file=sys.stderr)
            print('The index build reported success, but the Studio still has no '
                  'index. NO HEALTH VERDICT HAS BEEN PRODUCED.', file=sys.stderr)
            print('Run it by hand from the Studio root — this is the exact '
                  'command that ran:', file=sys.stderr)
            print(file=sys.stderr)
            print(f'    {AUTO_INIT_COMMAND_DISPLAY}', file=sys.stderr)
            if build_out:
                tail = [ln for ln in build_out.splitlines() if ln.strip()][-8:]
                if tail:
                    print(file=sys.stderr)
                    print('--- last lines of the index build ---', file=sys.stderr)
                    for ln in tail:
                        print(ln, file=sys.stderr)
            if args.json:
                print(json.dumps({
                    'tool': TOOL_NAME,
                    'tool_version': TOOL_VERSION,
                    'tropo_os_version': read_studio_version(studio_root),
                    'status': 'initialization-failed',
                    'verdict': 'none',
                    'health_verdict_produced': False,
                    'cure': NOT_INITIALIZED_CURE,
                    'exit_code': AUTO_INIT_FAILED_EXIT,
                    'timestamp': datetime.now(timezone.utc).strftime(
                        '%Y-%m-%dT%H:%M:%SZ'),
                }, separators=(',', ':')))
            return AUTO_INIT_FAILED_EXIT

    # NOT INITIALIZED — a correct Studio that has not built its index yet
    # (f0152b4c4ef4). This is a diagnostic, not a claim that the box is
    # defective, and it says so. The status line is what machines read; see
    # NOT_INITIALIZED_STATUS.
    #
    # REACHED ONLY UNDER --no-auto-init since 2026-09-08 (Mike's ruling). For a
    # human this state is now built through rather than reported. It is kept
    # whole, not deleted, because every gate opts out and this is the answer they
    # read — build_guards.box_self_test_problems keys on NOT_INITIALIZED_STATUS
    # to detect that it has been pointed at shipped bytes. Decision 4's exit code
    # still governs here and is still one constant.
    if return_code == _OUTCOME_NOT_INITIALIZED:
        studio_version = read_studio_version(studio_root)
        if args.json:
            print(json.dumps({
                'tool': TOOL_NAME,
                'tool_version': TOOL_VERSION,
                'tropo_os_version': studio_version,
                'status': 'not-initialized',
                'verdict': 'none',
                'health_verdict_produced': False,
                'cure': NOT_INITIALIZED_CURE,
                'exit_code': NOT_INITIALIZED_EXIT,
                'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            }, separators=(',', ':')))
        else:
            print(NOT_INITIALIZED_STATUS)
            print()
            print('This Studio has not built its index yet. Nothing is wrong: a release')
            print('box ships the source files and derives its index on first use.')
            print()
            print('NO HEALTH VERDICT HAS BEEN PRODUCED. Run this once, from the Studio root:')
            print()
            print(f'    {NOT_INITIALIZED_CURE}')
            print()
            print('then run this check again.')
            if args.verbose and stdout:
                print()
                print(stdout)
        return NOT_INITIALIZED_EXIT

    if stdout is None:
        # Script error — validator crashed or path missing. STDERR IS SHOWN: it
        # was already printed here, and that is the half Argus found missing at
        # the OTHER exit (a validator that died at exit 1 never reached this
        # branch at all, so nobody saw its traceback). The Summary guard below
        # is what routes that case here in spirit, via verdict 'aborted'.
        print('ERROR: validator subprocess failed (path missing or crash)', file=sys.stderr)
        if stderr:
            print(stderr, file=sys.stderr)
        return 5

    # Parse + compute verdict
    studio_version = read_studio_version(studio_root)
    parsed = parse_validator_output(stdout)
    verdict, exit_code = compute_verdict(parsed)

    # ABORTED — the validator returned a verdict-shaped exit code but never
    # printed a Summary, so there is no verdict to report. Loud, and it shows
    # the stderr the old path discarded (f0152b4c4ef4): this is exactly the
    # false GREEN argus-a175 measured, where an uncaught PermissionError inside
    # the validator exited 1 and was reported as "0 passed, 0 failed" GREEN.
    if verdict == 'aborted':
        print('ERROR: the validator produced no Summary line — it aborted before '
              'finishing. NO HEALTH VERDICT HAS BEEN PRODUCED; this is not a '
              'clean substrate.', file=sys.stderr)
        if stderr:
            print(stderr, file=sys.stderr)
        if not args.verbose and stdout:
            tail = [ln for ln in stdout.splitlines() if ln.strip()][-8:]
            if tail:
                print('--- last lines of validator output ---', file=sys.stderr)
                for ln in tail:
                    print(ln, file=sys.stderr)
        if args.json:
            print(json.dumps({
                'tool': TOOL_NAME,
                'tool_version': TOOL_VERSION,
                'tropo_os_version': studio_version,
                'status': 'aborted',
                'verdict': 'none',
                'health_verdict_produced': False,
                'exit_code': exit_code,
                'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            }, separators=(',', ':')))
        elif args.verbose and stdout:
            print(stdout)
        return exit_code

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

    # --warn-ok (v1.93, argus-a161; Mike-ruled after the cold-boot walk).
    # The three-state code is deliberate and stays: 0 GREEN / 1 YELLOW / 2 RED.
    # But YELLOW is the NORMAL state of a healthy shipped box — 103 passed,
    # 0 failed, 94 warnings on a pristine v1.93 install — and package.json
    # chained this tool with `&&`, so a customer's first `npm test` short-
    # circuited on a warning and the second half never ran. The engineer
    # persona's day-one act is wiring that into CI; he got a red build with
    # nothing wrong and concluded the product was unmaintained.
    # Collapsing the codes would destroy a real signal, so CI opts in instead:
    # warnings pass, failures do not.
    if args.warn_ok and exit_code == 1:
        return 0

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
