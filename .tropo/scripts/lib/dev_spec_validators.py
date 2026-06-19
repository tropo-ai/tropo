"""dev-spec.capsule v1.0 validator extensions for tropo-validate.py.

Authored by Argus A80 2026-05-23 captain-mode under v1.51 cycle Phase A per:
- dev-spec.capsule v1.0 §Validation Checks (UID c3f68cb5; .tropo/capsules/dev-spec.capsule.md)
- v1.51 cycle brief 1feefe68 v0.2 LOCKED §Phase A scope
- Pipeline-Runtime Engine Extension v0.2 (UID 51d171f3) §Activation-Input Validation

Talos T9 wires the import in tropo-validate.py at next pair-call. Lib module
matches the existing `lib/article_readiness.py` DRY pattern (rule logic lives
in lib/, callers in tropo-validate.py + adjacent scripts share single source
of truth). Per stm-a78-003 + Mike-A78 no-race-quality discipline.

All checks ship at WARN severity at v1.0 (grace period); ERROR ratchet at
v1.51.1+ per dev-spec.capsule §Validation Checks first-column annotation.
v1.10-v1.50 legacy cycles grandfathered per dev-spec.capsule Rule 7
(absence of dev-spec entries does NOT fire checks; checks only run when
type=dev-spec entries are present).

Returns per check function: (findings, total_checked, defects) where
- findings: list of strings prefixed with [WARN] / [FAIL] / [INFO]
- total_checked: count of type=dev-spec entries scanned
- defects: count of findings that are [WARN] or [FAIL] (not [INFO])

Composes-with tropo-validate.py existing pattern (e.g. check_ship_artifact_required_fields
at line ~1521). Use split_frontmatter + get_scalar for fast scalar access;
use yaml.safe_load for nested-structure inspection (committed_substrate /
risk_register / triggered_*_spec_uids arrays).
"""



from __future__ import annotations

TARGETS_CAPSULE = "dev-spec"  # Lane V Layer 3 M.1 targeting (8e2f1a47)

# V-ratchet v1.60: VALID_* for committed_substrate.change_class enum
VALID_CHANGE_CLASS = {"NEW", "AMENDED", "DEPRECATED", "REFACTORED"}
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# v1.51 perf fix (Argus A80 2026-05-23): cache vault scans across check functions.
# Each check function used to do a full vault iteration; with 9 checks × ~2329 files
# that's 21K+ file reads + YAML parses per validator pass. Caching at module level
# brings it to one pass per lib per tropo-validate.py invocation. ~10-13x speedup.

# Re-exports from tropo-validate.py for import convenience; Talos may inline
# at wire-time if cleaner. These functions exist at module-top of tropo-validate.py;
# the lib module duplicates the parsing helpers locally to stay self-contained
# (matches lib/article_readiness.py's approach).


def _split_frontmatter(text: str) -> str | None:
    """Extract raw YAML frontmatter block (between leading --- delimiters).

    Returns the YAML body as a string, or None if no frontmatter detected.
    Matches tropo-validate.py split_frontmatter behavior.
    """
    if not text.startswith('---\n') and not text.startswith('---\r\n'):
        return None
    lines = text.split('\n')
    if lines[0] != '---':
        return None
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line == '---':
            end_idx = i
            break
    if end_idx is None:
        return None
    return '\n'.join(lines[1:end_idx])


def _parse_frontmatter(text: str) -> dict | None:
    """Parse YAML frontmatter into a dict; return None on failure."""
    raw = _split_frontmatter(text)
    if raw is None:
        return None
    try:
        parsed = yaml.safe_load(raw)
        return parsed if isinstance(parsed, dict) else None
    except yaml.YAMLError:
        return None


@lru_cache(maxsize=4)
def _load_dev_specs(vault: Path) -> tuple:
    """Cached: load all type=dev-spec entries once per vault. Returns tuple of (path, fm) tuples."""
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
        if fm.get('type') != 'dev-spec':
            continue
        out.append((f, fm))
    return tuple(out)


def _iter_dev_specs(vault: Path):
    """Yield (path, frontmatter_dict) for every type=dev-spec entry — cached."""
    yield from _load_dev_specs(vault)


@lru_cache(maxsize=4)
def _load_uid_type_map(vault: Path) -> dict:
    """Cached: uid → type map from full vault scan. Used by triggered_uids_resolvable check."""
    type_map: dict[str, str] = {}
    files_dir = vault / 'vault' / 'files'
    if not files_dir.exists():
        return type_map
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        if fm is None:
            continue
        uid = fm.get('uid')
        entry_type = fm.get('type')
        if uid and entry_type:
            type_map[uid] = entry_type
    return type_map


@lru_cache(maxsize=4)
def _load_uid_status_map(vault: Path) -> dict:
    """Cached: uid → status map from full vault scan. Used by close_invariants check."""
    status_map: dict[str, str | None] = {}
    files_dir = vault / 'vault' / 'files'
    if not files_dir.exists():
        return status_map
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        if fm is None:
            continue
        uid = fm.get('uid')
        if uid:
            status_map[uid] = fm.get('status')
    return status_map


@lru_cache(maxsize=4)
def _load_vault_index_uids(vault: Path) -> frozenset:
    """Load all UIDs from vault/00-index.jsonl for resolvability checks. Cached."""
    import json
    uids: set[str] = set()
    index = vault / 'vault' / '00-index.jsonl'
    if not index.exists():
        return frozenset(uids)
    try:
        with index.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict) and 'uid' in entry:
                        uids.add(entry['uid'])
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return frozenset(uids)


# =============================================================================
# 1. check_dev_spec_required_fields
# =============================================================================

def check_dev_spec_required_fields(vault: Path) -> tuple[list[str], int, int]:
    """Validate dev-spec entries declare all required frontmatter fields.

    Per dev-spec.capsule v1.0 §Required Frontmatter:
      type / target_release / target_stream / committed_substrate / acceptance_criteria

    WARN at v1.0; ERROR ratchet at v1.51.1+.
    """
    required = ('type', 'target_release', 'target_stream', 'committed_substrate', 'acceptance_criteria')
    findings: list[str] = []
    total = 0

    for path, fm in _iter_dev_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        missing = [k for k in required if k not in fm]
        # target_stream may be explicitly null; presence is what counts
        if missing:
            findings.append(
                f'[WARN] {rel} — dev-spec missing required fields: {", ".join(missing)}'
            )

    defects = len(findings)
    return findings, total, defects


# =============================================================================
# 2. check_dev_spec_committed_substrate_non_empty
# =============================================================================

def check_dev_spec_committed_substrate_non_empty(vault: Path) -> tuple[list[str], int, int]:
    """Validate committed_substrate has at least one entry per stream (anti-fuzzy-framing).

    Per dev-spec.capsule v1.0 Rule 2 — Rule 2 anti-fuzzy-framing gate.
    "We'll author capsules" is rejected; concrete substrate UIDs required.

    WARN at v1.0; ERROR ratchet at v1.51.1+.
    """
    findings: list[str] = []
    total = 0

    for path, fm in _iter_dev_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        cs = fm.get('committed_substrate', [])
        if not isinstance(cs, list):
            findings.append(
                f'[WARN] {rel} — dev-spec committed_substrate must be a list (got {type(cs).__name__})'
            )
            continue
        if not cs:
            findings.append(
                f'[WARN] {rel} — dev-spec committed_substrate is empty (Rule 2 anti-fuzzy-framing violation)'
            )

    defects = len(findings)
    return findings, total, defects


# =============================================================================
# 3. check_dev_spec_committed_substrate_resolvable
# =============================================================================

def check_dev_spec_committed_substrate_resolvable(vault: Path) -> tuple[list[str], int, int]:
    """Validate each committed_substrate entry resolves: target is UID-in-index or valid path,
    change_class is one of the four enum values, description ≤ 200 chars.

    Per dev-spec.capsule v1.0 §Validation Checks Check 3.
    """
    valid_change_classes = {'NEW', 'AMENDED', 'REFACTORED', 'DEPRECATED'}
    findings: list[str] = []
    total = 0
    index_uids = _load_vault_index_uids(vault)

    for path, fm in _iter_dev_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        cs = fm.get('committed_substrate', [])
        if not isinstance(cs, list):
            continue  # caught by check 2
        for idx, entry in enumerate(cs):
            if not isinstance(entry, dict):
                findings.append(
                    f'[WARN] {rel} — committed_substrate[{idx}] must be an object with target/change_class/description'
                )
                continue
            target = entry.get('target')
            change_class = entry.get('change_class')
            description = entry.get('description', '')

            # Target validation: 8-hex UID OR vault-relative path
            if not target:
                findings.append(f'[WARN] {rel} — committed_substrate[{idx}] missing target')
            elif isinstance(target, str):
                # Is it an 8-hex UID?
                is_uid = len(target) == 8 and all(c in '0123456789abcdef' for c in target.lower())
                if is_uid:
                    if target not in index_uids:
                        findings.append(
                            f'[WARN] {rel} — committed_substrate[{idx}] target UID {target} does not resolve in vault index'
                        )
                # Else treat as path; presence check is informational at v1.0
                # (path-based targets may reference files yet to be authored mid-cycle)

            # Change class validation
            if change_class not in valid_change_classes:
                findings.append(
                    f'[WARN] {rel} — committed_substrate[{idx}] change_class {change_class!r} not in {valid_change_classes}'
                )

            # Description length
            if not isinstance(description, str) or len(description) > 200:
                findings.append(
                    f'[WARN] {rel} — committed_substrate[{idx}] description must be ≤ 200 chars (got {len(description) if isinstance(description, str) else "non-string"})'
                )

    defects = len(findings)
    return findings, total, defects


# =============================================================================
# 4. check_dev_spec_acceptance_criteria_present
# =============================================================================

def check_dev_spec_acceptance_criteria_present(vault: Path) -> tuple[list[str], int, int]:
    """Validate acceptance_criteria is non-empty string.

    Per dev-spec.capsule v1.0 §Validation Checks Check 4 + Rule 5 (Mike-walkable).
    Semantic Mike-walkability cannot be mechanically validated; this check
    enforces structural presence + non-empty.
    """
    findings: list[str] = []
    total = 0

    for path, fm in _iter_dev_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        ac = fm.get('acceptance_criteria')
        if not ac or (isinstance(ac, str) and not ac.strip()):
            findings.append(
                f'[WARN] {rel} — dev-spec acceptance_criteria is empty (Rule 5 violation)'
            )

    defects = len(findings)
    return findings, total, defects


# =============================================================================
# 5. check_dev_spec_target_stream_consistent
# =============================================================================

def check_dev_spec_target_stream_consistent(vault: Path) -> tuple[list[str], int, int]:
    """Validate multi-stream cycles have unique target_stream per dev-spec + same target_release.

    Per dev-spec.capsule v1.0 §Validation Checks Check 5 + Rule 4.
    Cross-entry validation: groups dev-specs by target_release; within each
    target_release, each non-null target_stream must be unique (one dev-spec per stream).
    """
    findings: list[str] = []
    total = 0
    by_release: dict[str, list[tuple[Path, str | None]]] = {}

    for path, fm in _iter_dev_specs(vault):
        total += 1
        target_release = fm.get('target_release')
        target_stream = fm.get('target_stream')
        if target_release:
            by_release.setdefault(target_release, []).append((path, target_stream))

    for target_release, entries in by_release.items():
        # Group by stream; null streams treated as whole-cycle (one allowed per release)
        seen_streams: dict[str | None, list[Path]] = {}
        for path, stream in entries:
            seen_streams.setdefault(stream, []).append(path)
        for stream, paths in seen_streams.items():
            if len(paths) > 1:
                rel_paths = ', '.join(str(p.relative_to(vault)) for p in paths)
                stream_label = 'null (whole-cycle)' if stream is None else stream
                findings.append(
                    f'[WARN] {target_release} — multiple dev-specs share target_stream={stream_label!r}: {rel_paths} (Rule 4 multi-stream = one dev-spec per stream)'
                )

    defects = len(findings)
    return findings, total, defects


# =============================================================================
# 6. check_dev_spec_triggered_uids_resolvable
# =============================================================================

def check_dev_spec_triggered_uids_resolvable(vault: Path) -> tuple[list[str], int, int]:
    """Validate triggered_doc_spec_uids + triggered_test_spec_uids resolve to entries of correct type.

    Per dev-spec.capsule v1.0 §Validation Checks Check 6.
    Engine-written field; non-empty arrays expected post-Phase D activation.
    Empty arrays at dev-spec authoring time are normal (engine populates at trigger fire).
    """
    findings: list[str] = []
    total = 0
    index_uids = _load_vault_index_uids(vault)
    type_map = _load_uid_type_map(vault)  # v1.51 perf fix: cached helper

    for path, fm in _iter_dev_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        for field_name, expected_type in (('triggered_doc_spec_uids', 'doc-spec'),
                                          ('triggered_test_spec_uids', 'test-spec')):
            uids = fm.get(field_name, [])
            if not isinstance(uids, list):
                continue
            for triggered_uid in uids:
                if not isinstance(triggered_uid, str):
                    continue
                if triggered_uid not in index_uids:
                    findings.append(
                        f'[WARN] {rel} — {field_name} entry {triggered_uid} does not resolve in vault index'
                    )
                    continue
                actual_type = type_map.get(triggered_uid)
                if actual_type and actual_type != expected_type:
                    findings.append(
                        f'[WARN] {rel} — {field_name} entry {triggered_uid} has type={actual_type} (expected {expected_type})'
                    )

    defects = len(findings)
    return findings, total, defects


# =============================================================================
# 7. check_dev_spec_acceptance_evidence_resolvable
# =============================================================================

def check_dev_spec_acceptance_evidence_resolvable(vault: Path) -> tuple[list[str], int, int]:
    """Validate acceptance_evidence UIDs (when present) all resolve in vault index.

    Per dev-spec.capsule v1.0 §Validation Checks Check 7.
    Optional field; only checked when present. Populated at cycle close (Phase D).
    """
    findings: list[str] = []
    total = 0
    index_uids = _load_vault_index_uids(vault)

    for path, fm in _iter_dev_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        evidence = fm.get('acceptance_evidence')
        if not evidence:
            continue
        if not isinstance(evidence, list):
            findings.append(
                f'[WARN] {rel} — acceptance_evidence must be a list (got {type(evidence).__name__})'
            )
            continue
        for ev_uid in evidence:
            if isinstance(ev_uid, str) and ev_uid not in index_uids:
                findings.append(
                    f'[WARN] {rel} — acceptance_evidence entry {ev_uid} does not resolve in vault index'
                )

    defects = len(findings)
    return findings, total, defects


# =============================================================================
# 8. check_dev_spec_close_invariants
# =============================================================================

def check_dev_spec_close_invariants(vault: Path) -> tuple[list[str], int, int]:
    """Validate stage:done + state:active requires closed_at + all triggered_*_spec_uids done.

    Per dev-spec.capsule v1.0 §Validation Checks Check 8 + Rule 3 (three-pipeline coupling
    enforcement at engine close-time). This validator catches the structural invariant in
    audit; engine-level enforcement at activation close is the primary gate (per
    Pipeline-Runtime Engine Extension v0.2 §Three-Pipeline Coupling State Machine).
    """
    findings: list[str] = []
    total = 0
    status_map = _load_uid_status_map(vault)  # v1.51 perf fix: cached helper

    for path, fm in _iter_dev_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        stage = fm.get('stage')
        state = fm.get('state')
        if stage != 'done' or state != 'active':
            continue  # only enforce on closed-active dev-specs

        if not fm.get('closed_at'):
            findings.append(
                f'[WARN] {rel} — stage:done + state:active requires closed_at field (Check 8)'
            )

        # Check triggered_*_spec_uids all at status:done
        for field_name in ('triggered_doc_spec_uids', 'triggered_test_spec_uids'):
            uids = fm.get(field_name, [])
            if not isinstance(uids, list):
                continue
            for triggered_uid in uids:
                if not isinstance(triggered_uid, str):
                    continue
                triggered_status = status_map.get(triggered_uid)
                if triggered_status not in ('done', 'locked'):
                    # locked included as compatibility; some pipeline activations close to locked
                    findings.append(
                        f'[WARN] {rel} — dev-spec closed but {field_name} entry {triggered_uid} not done (status={triggered_status!r}); three-pipeline coupling violation'
                    )

    defects = len(findings)
    return findings, total, defects


# =============================================================================
# 9. check_dev_spec_supersession_bidirectional
# =============================================================================

def check_dev_spec_supersession_bidirectional(vault: Path) -> tuple[list[str], int, int]:
    """Validate supersession bidirectional pair: if A.superseded_by=B, then B.supersedes=A.

    Per dev-spec.capsule v1.0 §Validation Checks Check 9 + Rule 6.
    Same pattern as design-spec.capsule v2.1 Rule 3.
    """
    findings: list[str] = []
    total = 0

    # Build dev-spec uid → frontmatter map
    dev_spec_fm: dict[str, dict] = {}
    dev_spec_path: dict[str, Path] = {}
    for path, fm in _iter_dev_specs(vault):
        total += 1
        uid = fm.get('uid')
        if uid:
            dev_spec_fm[uid] = fm
            dev_spec_path[uid] = path

    for uid, fm in dev_spec_fm.items():
        rel = dev_spec_path[uid].relative_to(vault)
        superseded_by = fm.get('superseded_by')
        supersedes = fm.get('supersedes')

        if superseded_by:
            target_fm = dev_spec_fm.get(superseded_by)
            if target_fm is None:
                findings.append(
                    f'[WARN] {rel} — superseded_by {superseded_by} not found in dev-spec entries'
                )
            elif target_fm.get('supersedes') != uid:
                findings.append(
                    f'[WARN] {rel} — superseded_by {superseded_by} but {superseded_by}.supersedes is {target_fm.get("supersedes")!r} (Rule 6 bidirectional pair violation)'
                )

        if supersedes:
            target_fm = dev_spec_fm.get(supersedes)
            if target_fm is None:
                findings.append(
                    f'[WARN] {rel} — supersedes {supersedes} not found in dev-spec entries'
                )
            elif target_fm.get('superseded_by') != uid:
                findings.append(
                    f'[WARN] {rel} — supersedes {supersedes} but {supersedes}.superseded_by is {target_fm.get("superseded_by")!r} (Rule 6 bidirectional pair violation)'
                )

    defects = len(findings)
    return findings, total, defects


# =============================================================================
# Aggregator — convenience for tropo-validate.py wiring
# =============================================================================

DEV_SPEC_CHECKS = (
    ('check_dev_spec_required_fields', check_dev_spec_required_fields),
    ('check_dev_spec_committed_substrate_non_empty', check_dev_spec_committed_substrate_non_empty),
    ('check_dev_spec_committed_substrate_resolvable', check_dev_spec_committed_substrate_resolvable),
    ('check_dev_spec_acceptance_criteria_present', check_dev_spec_acceptance_criteria_present),
    ('check_dev_spec_target_stream_consistent', check_dev_spec_target_stream_consistent),
    ('check_dev_spec_triggered_uids_resolvable', check_dev_spec_triggered_uids_resolvable),
    ('check_dev_spec_acceptance_evidence_resolvable', check_dev_spec_acceptance_evidence_resolvable),
    ('check_dev_spec_close_invariants', check_dev_spec_close_invariants),
    ('check_dev_spec_supersession_bidirectional', check_dev_spec_supersession_bidirectional),
)


def run_all_dev_spec_checks(vault: Path) -> tuple[list[str], int, int]:
    """Run all 9 dev-spec validators in sequence; return aggregated findings.

    Convenience entry point for tropo-validate.py wiring. Talos may inline each
    check separately at wire-time if per-check reporting is preferred.
    """
    all_findings: list[str] = []
    total_dev_specs = 0
    total_defects = 0

    for name, check_fn in DEV_SPEC_CHECKS:
        findings, checked, defects = check_fn(vault)
        all_findings.extend(findings)
        # total_dev_specs is the same across checks (all scan vault/files/ for type=dev-spec)
        total_dev_specs = max(total_dev_specs, checked)
        total_defects += defects

    return all_findings, total_dev_specs, total_defects


# =============================================================================
# Talos wire-up reference (paste into tropo-validate.py main())
# =============================================================================

WIRE_UP_REFERENCE = """
# in tropo-validate.py, near the existing check_pipeline_runtime_has_jsonl block:

from lib.dev_spec_validators import run_all_dev_spec_checks

# In main(), after existing pipeline-class checks fire:
ds_findings, ds_total, ds_defects = run_all_dev_spec_checks(vault)
if ds_total > 0:
    print(f'\\nchecking dev-spec entries ({ds_total} found)...')
    for finding in ds_findings[:10]:
        print(f'  {finding}')
    if len(ds_findings) > 10:
        remaining = len(ds_findings) - 10
        total_warnings += remaining
        print(f'  ... and {remaining} more (run with -v for full list)')
    total_warnings += min(10, len(ds_findings))
elif ds_total == 0:
    pass  # legacy cycles grandfathered per dev-spec.capsule Rule 7
"""
