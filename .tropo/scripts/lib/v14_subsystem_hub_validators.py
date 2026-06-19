"""v1.14 schema split validator extensions for tropo-validate.py.

Authored by Argus A80 2026-05-23 captain-mode under v1.51 cycle per:
- project.capsule v2.5 §Validation Checks 10-11
- Vela V51 Path 2 finding [fb395501]
- Mike-A80 directive 2026-05-23 verbatim "B. let's do it right"

WHAT THIS DOES:

Two validator extensions ship at WARN severity at v1.51 ship; ERROR ratchet at v1.52+
once migration is fully verified + stable in production-use.

1. check_subsystem_hub_resolves
   For every vault/files/<uid>.md entry that declares `subsystem_hub:`, verify each
   UID in the array resolves to a vault entry with `subsystem_name:` field set
   (i.e., IS actually a subsystem hub).

2. check_no_hub_uids_in_member_of
   For every vault/files/<uid>.md entry, verify `member_of:` array does NOT contain
   any subsystem hub UIDs. Hub UIDs belong in `subsystem_hub:` field per v1.14 schema
   split. This is THE structural-enforcement gate that prevents v1.12-era ambiguity
   from recurring.

Lib module matches the existing `lib/article_readiness.py` + `lib/dev_spec_validators.py`
DRY pattern. Rule logic in lib/; tropo-validate.py imports + invokes.

Talos wires the import in tropo-validate.py at next pair-call per the WIRE_UP_REFERENCE
block at module bottom.
"""

from __future__ import annotations
from functools import lru_cache
from pathlib import Path

import yaml

# v1.51 perf fix (Argus A80 2026-05-23): @lru_cache on loader functions.
# _iter_entries is especially expensive (scans ALL vault files); cache critical.


def _split_frontmatter(text: str) -> str | None:
    """Extract raw YAML frontmatter block (between leading --- delimiters)."""
    if not text.startswith('---'):
        return None
    lines = text.split('\n')
    if lines[0].strip() != '---':
        return None
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == '---':
            end_idx = i
            break
    if end_idx is None:
        return None
    return '\n'.join(lines[1:end_idx])


def _parse_frontmatter(text: str) -> dict | None:
    raw = _split_frontmatter(text)
    if raw is None:
        return None
    try:
        parsed = yaml.safe_load(raw)
        return parsed if isinstance(parsed, dict) else None
    except yaml.YAMLError:
        return None


@lru_cache(maxsize=4)
def _discover_hub_uids(vault: Path) -> frozenset:
    """Cached: subsystem hub UIDs (entries with subsystem_name: field)."""
    hubs: set[str] = set()
    files_dir = vault / 'vault' / 'files'
    if not files_dir.exists():
        return frozenset(hubs)
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        if fm is None:
            continue
        if fm.get('subsystem_name'):
            uid = fm.get('uid') or f.stem
            if isinstance(uid, str):
                hubs.add(uid)
    return frozenset(hubs)


@lru_cache(maxsize=4)
def _load_all_entries(vault: Path) -> tuple:
    """Cached: every vault/files/*.md entry. Tuple of (path, fm) so cache holds.

    HEAVY scan — without caching, this runs twice per validator pass (once per check)
    × 2329 files × YAML parse. With caching, runs once per validator invocation.
    """
    out = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.exists():
        return tuple()
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        if fm is None:
            continue
        out.append((f, fm))
    return tuple(out)


def _iter_entries(vault: Path):
    """Yield cached entries."""
    yield from _load_all_entries(vault)


# =============================================================================
# 1. check_subsystem_hub_resolves
# =============================================================================

def check_subsystem_hub_resolves(vault: Path) -> tuple[list[str], int, int]:
    """Verify each subsystem_hub: UID resolves to an entry with subsystem_name: set.

    Per project.capsule v2.5 §Validation Checks Check 10.
    WARN at v1.51; ERROR ratchet at v1.52+.
    """
    hub_uids = _discover_hub_uids(vault)
    findings: list[str] = []
    total_checked = 0

    for path, fm in _iter_entries(vault):
        subsystem_hub = fm.get('subsystem_hub')
        if not subsystem_hub:
            continue
        if not isinstance(subsystem_hub, list):
            rel = path.relative_to(vault)
            findings.append(
                f'[WARN] {rel} — subsystem_hub must be a list (got {type(subsystem_hub).__name__})'
            )
            continue
        total_checked += 1
        rel = path.relative_to(vault)
        for hub_uid in subsystem_hub:
            if not isinstance(hub_uid, str):
                findings.append(
                    f'[WARN] {rel} — subsystem_hub entry must be a string UID (got {type(hub_uid).__name__})'
                )
                continue
            if hub_uid not in hub_uids:
                findings.append(
                    f'[WARN] {rel} — subsystem_hub entry {hub_uid} does not resolve to a vault entry with subsystem_name: set (not a subsystem hub)'
                )

    defects = len(findings)
    return findings, total_checked, defects


# =============================================================================
# 2. check_no_hub_uids_in_member_of
# =============================================================================

def check_no_hub_uids_in_member_of(vault: Path) -> tuple[list[str], int, int]:
    """Verify member_of: arrays do not contain subsystem hub UIDs.

    Per project.capsule v2.5 §Validation Checks Check 11. THE structural-enforcement
    gate. Hub UIDs belong in subsystem_hub:, not member_of:.

    ERROR at v1.15+ (migration complete; drift=0 confirmed 2026-06-06). All entries
    evaluated; hub-self-exemption preserved. capsule_version gate removed at v1.15
    once migration landed clean.
    """
    hub_uids = _discover_hub_uids(vault)
    findings: list[str] = []
    total_checked = 0

    for path, fm in _iter_entries(vault):
        member_of = fm.get('member_of') or []
        if not isinstance(member_of, list):
            continue

        # Skip subsystem hubs themselves (their own uid would be in hub_uids; their
        # member_of: legitimately doesn't reference other hubs but might in edge cases)
        own_uid = fm.get('uid') or path.stem
        if own_uid in hub_uids:
            continue

        total_checked += 1
        rel = path.relative_to(vault)
        hub_edges_in_member_of = [m for m in member_of if isinstance(m, str) and m in hub_uids]
        if hub_edges_in_member_of:
            findings.append(
                f'[ERROR] {rel} — member_of contains hub UIDs {hub_edges_in_member_of}; '
                f'move to subsystem_hub: field per project.capsule v2.5 Rule 8'
            )

    defects = len(findings)
    return findings, total_checked, defects


# =============================================================================
# Aggregator — convenience for tropo-validate.py wiring
# =============================================================================

V14_SUBSYSTEM_HUB_CHECKS = (
    ('check_subsystem_hub_resolves', check_subsystem_hub_resolves),
    ('check_no_hub_uids_in_member_of', check_no_hub_uids_in_member_of),
)


def run_all_v14_subsystem_hub_checks(vault: Path) -> tuple[list[str], int, int]:
    """Run both v1.14 schema split validators; return aggregated findings."""
    all_findings: list[str] = []
    total = 0
    total_defects = 0

    for name, check_fn in V14_SUBSYSTEM_HUB_CHECKS:
        findings, checked, defects = check_fn(vault)
        all_findings.extend(findings)
        total = max(total, checked)
        total_defects += defects

    return all_findings, total, total_defects


# =============================================================================
# Talos wire-up reference (paste into tropo-validate.py main())
# =============================================================================

WIRE_UP_REFERENCE = """
# in tropo-validate.py, near the existing pipeline-class checks:

from lib.v14_subsystem_hub_validators import run_all_v14_subsystem_hub_checks

# In main(), after existing project-class checks fire:
v14_findings, v14_total, v14_defects = run_all_v14_subsystem_hub_checks(vault)
if v14_findings:
    print(f'\\nchecking v1.14 subsystem-hub schema split ({v14_total} migrated entries)...')
    for finding in v14_findings[:10]:
        print(f'  {finding}')
    if len(v14_findings) > 10:
        remaining = len(v14_findings) - 10
        total_warnings += remaining
        print(f'  ... and {remaining} more (run with -v for full list)')
    total_warnings += min(10, len(v14_findings))
"""
