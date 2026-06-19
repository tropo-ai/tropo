#!/usr/bin/env python3
"""
---
uid: c9b7d4e2
title: validate-no-absolute-paths — Tool
name: validate-no-absolute-paths
type: tool
status: active
owner: argus
domain: Vault portability validator — fails if any committed file contains absolute machine paths (/Users/.../, ~/...).
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/c9b7d4e2.py [--strict] [vault-root]
script_path: vault/tools/c9b7d4e2.py
input:
  type: object
  properties:
    vault-root:
      type: string
      description: Optional positional arg
    strict:
      type: boolean
destructive: false
audit_required: false
writes_scope: []
governance_category: query
description: 'Vault portability validator. Fails the build if any committed file contains an absolute machine path (e.g., /Users/<account>/..., ~/..., shell-anchored paths) outside an explicit allowlist of historical/append-only/runtime-forensic directories. Background: discovered 2026-04-24 when the vault was moved between machines and 134 files turned out to contain old-account paths — a multi-generation discipline failure. The vault''s architectural rule (settings/env.md A17) forbids hardcoded path prefixes; this validator enforces it.'
domain_tags:
- validator
- portability
- absolute-paths
- build-gate
- v1.5-substrate
trigger_description: 'Reach for this whenever verifying vault portability — that no committed file has absolute machine paths leaking in (typical contamination: log artifacts, cached output, agent output that captured a /Users/<account>/ prefix). Run as part of build-release.py pre-flight (the build is supposed to ship a portable artifact). Also useful before commits that touched generated content. The vault''s own settings/env.md A17 (March 2026) forbids hardcoded path prefixes; this is the enforcement substrate. Allowlist exists for historical / append-only / runtime-forensic directories.'
created: 2026-05-09
created_by: argus-a53
modified: 2026-05-09
modified_by: argus-a53
governed_by: d5e1b4a3
capsule_version: '2.5'
schema_version: 2
extraction_scope: ship
member_of:
- c7e4f9a2
tags:
- tool
- cli
- validator
- portability
- build-gate
- v1.15-stream-b
subsystem_hub:
- 8dd772a0
---
"""
from __future__ import annotations

"""validate-no-absolute-paths.py — Python port of scripts/validate-no-absolute-paths.ts (v1.5 S5/A6).

Vault portability validator — fails the build if any committed file in the vault
contains an absolute machine path (e.g., `/Users/<account>/...`, `~/...`,
shell-anchored paths) outside of an explicit allowlist of historical / append-only /
runtime-forensic directories.

Background: discovered 2026-04-24 when the vault was moved between machines
and 134 vault files turned out to contain `/Users/<old-account>/...` paths
(portability:exempt — anonymized to avoid this script flagging itself) — a
multi-generation discipline failure. The vault's own architectural rule
(settings/env.md, A17 March 2026) forbids hardcoded path prefixes; this
validator enforces that rule.

Usage:
    python3 .tropo/scripts/validate-no-absolute-paths.py [vault-root]
    python3 .tropo/scripts/validate-no-absolute-paths.py --strict [vault-root]

Default vault root: walks up from script location to find a directory with
`vault/` + `.tropo/`; falls back to current working directory.

Exit code: 0 if clean, 1 if any forbidden paths found in non-allowlisted files.

Flags:
    --strict   Release-time gate. Disables ALLOWLIST_SEGMENTS and
               ALLOWLIST_FILENAME_PATTERNS — every absolute path anywhere
               under the given root is a finding. Per-line
               `<!-- portability:exempt -->` markers are still respected so
               pedagogical content can ship if explicitly marked. Use this
               against extracted release artifacts (e.g.,
               `releases/vN.n.n/dist/...`), where no historical/forensic
               exemption applies.

Per-line exempt marker: any line containing the literal string
`portability:exempt` is exempt from scanning. Convention: use
`<!-- portability:exempt -->` HTML comment in markdown.

No third-party dependencies. Targets Python 3.8+.

Author: vela-v40
Owner: vela
Domain: vault-portability; v1.5 Truthful Ship vault-maintenance toolchain.
"""

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Forbidden path patterns. Each pattern matches an absolute / shell-anchored
# path that must not appear in vault content.
#
# The /Users/ pattern requires an alphanumeric account-name character after
# the slash so that the symbolic placeholder /Users/<account>/... (used in
# documentation about this rule) is NOT flagged.
FORBIDDEN_PATTERNS = [
    ('macOS user-account path', re.compile(r'/Users/[a-zA-Z][a-zA-Z0-9_-]*/')),
    ('Linux home-account path', re.compile(r'/home/[a-zA-Z][a-zA-Z0-9_-]*/')),
    ('Shell home-anchored path', re.compile(r'(^|[\s`\'"(])~/[a-zA-Z]')),
]

# Files / directories where forbidden patterns are tolerated because the
# content is by definition a historical, append-only, or runtime-forensic
# record. Any path containing one of these segments is exempt.
#
# The exemption is for FACTUAL historical content (what happened, on what
# machine). It is not a license to add new absolute paths to active files.
ALLOWLIST_SEGMENTS = [
    '/playbook-runs/',                           # runtime activation/retirement logs
    '/channels/archive/',                        # frozen channel archives
    '/agents/sa/',                               # sub-agent activation records (logs)
    '/transfers/living-transfer-history/',       # frozen transfer history
    '/releases/',                                # frozen shipped release artifacts
    '/tab - the agentic builders/',              # book primary-source domain
    '/tropo-business/',                                   # historical pre-Tropo content
    '/recycle/',                                 # explicit recycle bin
    '/.tropo-capsule/workspace/',                # agent ephemeral scratch
    '/.tropo-capsule/memory/history/',           # frozen memory history files
    '/.tropo-capsule/memory/short-term-memory.jsonl',  # ephemeral session-bound memory
    '/operations/daily-vault-health/reports/',   # frozen daily reports
    '/agents/argus/archive/',                    # superseded agent versions
    '/agents/metis/archive/',
    '/agents/orpheus/archive/',
    '/agents/talos/archive/',
    '/agents/vela/archive/',
    '/agents/vela/transfers/',                   # includes living-transfer + history
    '/agents/metis/transfers/',
    '/agents/orpheus/transfers/',
    '/agents/argus/transfers/',
    '/agents/talos/transfers/',
    '/workspace/',                               # any agent's workspace directory (ephemeral)
]

# Filename patterns tolerated regardless of directory. Used for
# dated execution scripts (e.g., `rehome-v14-orphans-2026-04-24.py`) which
# are forensic execution records frozen at run-date.
ALLOWLIST_FILENAME_PATTERNS = [
    re.compile(r'-\d{4}-\d{2}-\d{2}\.(py|ts|js|sh)$'),  # dated execution scripts
]

# Per-line escape marker. A line containing this string is exempt — for use
# in pedagogical content that legitimately needs to *show* a forbidden
# pattern as an example of what NOT to do.
PER_LINE_EXEMPT_MARKER = 'portability:exempt'

# File extensions to scan. Anything else is skipped.
SCAN_EXTENSIONS = {'.md', '.jsonl', '.json', '.ts', '.tsx', '.js', '.py', '.yaml', '.yml'}

# Skip these directories outright
SKIP_DIRS = {'node_modules', '.git'}


# ---------------------------------------------------------------------------
# Vault root resolution
# ---------------------------------------------------------------------------

def resolve_vault_root(explicit) -> Path:
    """Resolve vault root from explicit arg, walk-up, or cwd. Returns absolute Path."""
    if explicit:
        return Path(explicit).resolve()

    # Walk up from script location
    script_path = Path(__file__).resolve()
    for candidate in [script_path.parent.parent.parent, *script_path.parents]:
        if (candidate / 'ledger').is_dir() and (candidate / '.tropo').is_dir():
            return candidate

    return Path.cwd().resolve()


# ---------------------------------------------------------------------------
# File walk
# ---------------------------------------------------------------------------

def walk_files(root: Path):
    """Yield Path objects for every scannable file under root."""
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except (PermissionError, FileNotFoundError):
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                stack.append(entry)
            elif entry.is_file():
                if entry.suffix in SCAN_EXTENSIONS:
                    yield entry


def is_allowlisted(filepath: Path, strict: bool) -> bool:
    if strict:
        return False
    posix_path = filepath.as_posix()
    if any(seg in posix_path for seg in ALLOWLIST_SEGMENTS):
        return True
    if any(p.search(filepath.name) for p in ALLOWLIST_FILENAME_PATTERNS):
        return True
    return False


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def scan_file(filepath: Path):
    """Return list of (line_number, pattern_name, excerpt) findings for one file."""
    findings = []
    try:
        contents = filepath.read_text(errors='replace')
    except Exception:
        return findings
    lines = contents.split('\n')
    for i, line in enumerate(lines, start=1):
        if PER_LINE_EXEMPT_MARKER in line:
            continue
        for name, regex in FORBIDDEN_PATTERNS:
            if regex.search(line):
                findings.append((i, name, line.strip()[:160]))
                # Continue: a single line could match multiple patterns; report all
    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Vault portability validator — flag absolute machine paths in committed content.',
    )
    parser.add_argument('vault_root', nargs='?', default=None,
                        help='Vault root path (default: walk up from script or use cwd).')
    parser.add_argument('--strict', action='store_true',
                        help='Disable allowlist (release-gate mode).')
    args = parser.parse_args()

    resolved_root = resolve_vault_root(args.vault_root)
    if not resolved_root.is_dir():
        print(f'Vault root not found: {resolved_root}', file=sys.stderr)
        return 2

    all_findings = []  # list of (filepath, [findings])
    scanned = 0
    exempt = 0

    for f in walk_files(resolved_root):
        if is_allowlisted(f, args.strict):
            exempt += 1
            continue
        scanned += 1
        findings = scan_file(f)
        if findings:
            all_findings.append((f, findings))

    print()
    print('=== Vault Portability Validator ===')
    print(f'Vault root: {resolved_root}')
    mode = 'STRICT (release gate — no allowlist)' if args.strict else 'vault (allowlist active)'
    print(f'Mode: {mode}')
    print(f'Files scanned: {scanned} ({exempt} allowlisted as historical/runtime/ephemeral)')

    total_findings = sum(len(f) for _, f in all_findings)
    if total_findings == 0:
        print()
        print('Result: CLEAN — no forbidden absolute paths in active vault content.')
        return 0

    print()
    print(f'Result: {total_findings} forbidden path(s) found in active vault content:')
    print()

    for fpath, findings in all_findings:
        try:
            rel = fpath.relative_to(Path.cwd())
        except ValueError:
            rel = fpath
        print(f'  {rel}')
        for line_num, pattern, excerpt in findings:
            print(f'    L{line_num}  [{pattern}]  {excerpt}')
        print()

    print('Fix: replace absolute machine paths with vault-root-relative paths')
    print("     (e.g., 'agents/...', 'channels/...') or, when a root anchor is")
    print("     genuinely needed in prose, use 'tropo-ai/argo-os/...' or '<vault-root>/...'.")
    print('     For legitimate pedagogical examples, append `<!-- portability:exempt -->` to the line.')
    print('     See settings/env.md "Forbidden pattern" rule.')
    print()

    return 1


if __name__ == '__main__':
    sys.exit(main())
