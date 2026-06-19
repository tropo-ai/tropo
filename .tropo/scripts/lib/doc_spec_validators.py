"""doc-spec.capsule v1.0 validator extensions for tropo-validate.py.

Authored by Argus A80 2026-05-23 captain-mode under v1.51 Phase B per:
- doc-spec.capsule v1.0 LOCKED §Validation Checks (UID 9a7d314a; LOCKED by Mike-A80 + Orpheus O11 walk 2026-05-23)
- v1.51 cycle brief 1feefe68 §Six Artifacts row 2

Matches existing `lib/article_readiness.py` + `lib/dev_spec_validators.py` DRY pattern.
Wired into tropo-validate.py main() at v1.51 ship; 13 checks fire on every vault rebuild.

All checks ship at WARN severity at v1.0 (grace period); ERROR ratchet at v1.51.1+ per
doc-spec.capsule §Validation Checks. v1.10-v1.50 legacy cycles grandfathered per Rule 8
(absence of doc-spec entries does NOT fire checks; checks only run when type=doc-spec
entries are present).

Returns per check function: (findings, total_checked, defects) where
- findings: list of strings prefixed with [WARN] / [FAIL]
- total_checked: count of type=doc-spec entries scanned
- defects: count of findings
"""



from __future__ import annotations

TARGETS_CAPSULE = "doc-spec"  # Lane V Layer 3 M.1 targeting (8e2f1a47)

# V-ratchet v1.60: VALID_* constants for Layer 3 enum-drift detection
VALID_ORPHEUS_DISPOSITION_SIGNOFF = {"PASS", "PASS-with-findings", "FAIL-incomplete"}
from functools import lru_cache
from pathlib import Path

import yaml

# v1.51 perf fix (Argus A80 2026-05-23): @lru_cache on loader functions brings
# per-check cost from O(checks × files × parse) to O(files × parse) once per
# tropo-validate.py invocation. ~10-13x speedup matches dev_spec_validators.py pattern.


def _split_frontmatter(text: str) -> str | None:
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
def _load_doc_specs(vault: Path) -> tuple:
    """Cached: load all type=doc-spec entries once per vault."""
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
        if fm.get('type') != 'doc-spec':
            continue
        out.append((f, fm))
    return tuple(out)


def _iter_doc_specs(vault: Path):
    """Yield cached doc-spec entries."""
    yield from _load_doc_specs(vault)


@lru_cache(maxsize=4)
def _load_vault_index_uids(vault: Path) -> frozenset:
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


@lru_cache(maxsize=4)
def _load_uid_type_map(vault: Path) -> dict:
    """Cached: uid → type map for cross-reference type-checking."""
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
        uid = fm.get('uid') or f.stem
        entry_type = fm.get('type')
        if uid and entry_type:
            type_map[uid] = entry_type
    return type_map


@lru_cache(maxsize=4)
def _load_dev_spec_new_substrate(vault: Path) -> dict:
    """Cached: dev-spec UID → list of committed_substrate NEW target UIDs.

    Returns a regular dict (lru_cache permits mutable returns; just don't mutate).
    Used by Checks 10 (cross-validation) + 13 (per-tier with NEW substrate).
    """
    result: dict[str, list[str]] = {}
    files_dir = vault / 'vault' / 'files'
    if not files_dir.exists():
        return result
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        if fm is None or fm.get('type') != 'dev-spec':
            continue
        uid = fm.get('uid') or f.stem
        cs = fm.get('committed_substrate') or []
        if not isinstance(cs, list):
            continue
        new_targets = []
        for entry in cs:
            if isinstance(entry, dict) and entry.get('change_class') == 'NEW':
                t = entry.get('target')
                if isinstance(t, str):
                    new_targets.append(t)
        result[uid] = new_targets
    return result


@lru_cache(maxsize=4)
def _resolve_subsystem_hub_uids(vault: Path) -> frozenset:
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


# =============================================================================
# 1. check_doc_spec_required_fields
# =============================================================================

def check_doc_spec_required_fields(vault: Path) -> tuple[list[str], int, int]:
    required = ('type', 'target_subsystem', 'target_tier', 'triggered_by_dev_cycle',
                'doc_changes_required', 'acceptance_criteria')
    findings: list[str] = []
    total = 0
    for path, fm in _iter_doc_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        missing = [k for k in required if k not in fm]
        if missing:
            findings.append(
                f'[WARN] {rel} — doc-spec missing required fields: {", ".join(missing)}'
            )
    return findings, total, len(findings)


# =============================================================================
# 2. check_doc_spec_target_subsystem_resolvable
# =============================================================================

def check_doc_spec_target_subsystem_resolvable(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    hub_uids = _resolve_subsystem_hub_uids(vault)
    for path, fm in _iter_doc_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        ts = fm.get('target_subsystem')
        if ts is None:
            continue  # null explicit (cross-subsystem) — OK
        if not isinstance(ts, str):
            findings.append(f'[WARN] {rel} — target_subsystem must be a UID string or null (got {type(ts).__name__})')
            continue
        if ts not in hub_uids:
            findings.append(
                f'[WARN] {rel} — target_subsystem {ts} does not resolve to a subsystem hub (no entry with subsystem_name: field)'
            )
    return findings, total, len(findings)


# =============================================================================
# 3. check_doc_spec_target_tier_valid
# =============================================================================

def check_doc_spec_target_tier_valid(vault: Path) -> tuple[list[str], int, int]:
    valid_tiers = {'summary', 'subsystem', 'spec', 'multi'}
    findings: list[str] = []
    total = 0
    for path, fm in _iter_doc_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        tier = fm.get('target_tier')
        if tier not in valid_tiers:
            findings.append(
                f'[WARN] {rel} — target_tier {tier!r} not in {valid_tiers}'
            )
    return findings, total, len(findings)


# =============================================================================
# 4. check_doc_spec_doc_changes_required_non_empty
# =============================================================================

def check_doc_spec_doc_changes_required_non_empty(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    for path, fm in _iter_doc_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        dcr = fm.get('doc_changes_required')
        if not isinstance(dcr, list):
            findings.append(
                f'[WARN] {rel} — doc_changes_required must be a list (got {type(dcr).__name__ if dcr is not None else "absent"})'
            )
            continue
        if not dcr:
            findings.append(
                f'[WARN] {rel} — doc_changes_required is empty (Rule 2 anti-fuzzy-framing violation)'
            )
    return findings, total, len(findings)


# =============================================================================
# 5. check_doc_spec_doc_changes_paths_resolvable
# =============================================================================

def check_doc_spec_doc_changes_paths_resolvable(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    for path, fm in _iter_doc_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        dcr = fm.get('doc_changes_required') or []
        if not isinstance(dcr, list):
            continue
        for idx, entry in enumerate(dcr):
            if not isinstance(entry, dict):
                findings.append(f'[WARN] {rel} — doc_changes_required[{idx}] must be an object')
                continue
            p = entry.get('path')
            cs = entry.get('change_summary', '')
            if not p:
                findings.append(f'[WARN] {rel} — doc_changes_required[{idx}] missing path')
                continue
            # path exists OR explicit "new-file" marker in change_summary
            target_path = vault / p
            if not target_path.exists() and 'new-file' not in str(cs).lower():
                findings.append(
                    f'[WARN] {rel} — doc_changes_required[{idx}] path {p!r} does not exist (and change_summary lacks "new-file" marker)'
                )
    return findings, total, len(findings)


# =============================================================================
# 6. check_doc_spec_triggered_by_dev_cycle_resolvable
# =============================================================================

def check_doc_spec_triggered_by_dev_cycle_resolvable(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    index_uids = _load_vault_index_uids(vault)
    type_map = _load_uid_type_map(vault)
    for path, fm in _iter_doc_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        tdc = fm.get('triggered_by_dev_cycle')
        if not tdc:
            continue  # required-field check 1 catches absence
        if not isinstance(tdc, str):
            findings.append(f'[WARN] {rel} — triggered_by_dev_cycle must be a UID string')
            continue
        if tdc not in index_uids:
            findings.append(f'[WARN] {rel} — triggered_by_dev_cycle UID {tdc} does not resolve in vault index')
            continue
        # Soft check: target should be type:activation (dev-pipeline run) — informational only
        actual_type = type_map.get(tdc)
        if actual_type and actual_type not in ('activation', 'pipeline-run', 'dev-spec'):
            findings.append(
                f'[WARN] {rel} — triggered_by_dev_cycle {tdc} resolves to type={actual_type} '
                f'(expected activation / pipeline-run / dev-spec)'
            )
    return findings, total, len(findings)


# =============================================================================
# 7. check_doc_spec_acceptance_criteria_present
# =============================================================================

def check_doc_spec_acceptance_criteria_present(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    for path, fm in _iter_doc_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        ac = fm.get('acceptance_criteria')
        if not ac or (isinstance(ac, str) and not ac.strip()):
            findings.append(f'[WARN] {rel} — acceptance_criteria empty (Rule 5 violation)')
    return findings, total, len(findings)


# =============================================================================
# 8. check_doc_spec_voice_review_evidence_present
# =============================================================================

def check_doc_spec_voice_review_evidence_present(vault: Path) -> tuple[list[str], int, int]:
    """Voice review evidence required at close-time for tiers that need it.
    Only fires on closed (stage:done) entries; in-flight entries skipped."""
    findings: list[str] = []
    total = 0
    for path, fm in _iter_doc_specs(vault):
        total += 1
        if fm.get('stage') != 'done':
            continue
        rel = path.relative_to(vault)
        tier = fm.get('target_tier', '')
        # Default voice_review_required: true for summary + subsystem, false for spec
        explicit = fm.get('voice_review_required')
        if explicit is None:
            required = tier in ('summary', 'subsystem', 'multi')
        else:
            required = bool(explicit)
        if not required:
            continue
        evidence = fm.get('acceptance_evidence') or []
        if not evidence:
            findings.append(
                f'[WARN] {rel} — voice_review_required=true at tier={tier} but acceptance_evidence empty at close-time'
            )
    return findings, total, len(findings)


# =============================================================================
# 9. check_doc_spec_cross_reference_check_evidence (EXTENDED v1.0 per Q3 walk lock)
# =============================================================================

def check_doc_spec_cross_reference_check_evidence(vault: Path) -> tuple[list[str], int, int]:
    """Cross-reference audit evidence at close-time for spec-tier (or explicit).

    EXTENDED v1.0 per Q3 walk lock: verifies (a) body-prose UID resolution,
    (b) member_of: frontmatter resolution, (c) nav-block render-clean post-touch.
    For now, this implementation checks the evidence-presence gate; the full
    body-prose + nav-block render verification belongs to the doc-pipeline run
    (Phase C; Orpheus's lane) when each doc-spec activation closes.
    """
    findings: list[str] = []
    total = 0
    for path, fm in _iter_doc_specs(vault):
        total += 1
        if fm.get('stage') != 'done':
            continue
        rel = path.relative_to(vault)
        tier = fm.get('target_tier', '')
        explicit = fm.get('cross_reference_check')
        if explicit is None:
            required = tier in ('spec', 'multi')
        else:
            required = bool(explicit)
        if not required:
            continue
        evidence = fm.get('acceptance_evidence') or []
        if not evidence:
            findings.append(
                f'[WARN] {rel} — cross_reference_check=true at tier={tier} but acceptance_evidence empty at close-time'
            )
    return findings, total, len(findings)


# =============================================================================
# 10. check_doc_spec_cross_validation_against_dev_spec
# =============================================================================

def check_doc_spec_cross_validation_against_dev_spec(vault: Path) -> tuple[list[str], int, int]:
    """For each triggering dev-spec NEW substrate entry, doc-spec must have
    matching doc_changes_required entry referencing it OR explicit no-doc-impact justification."""
    findings: list[str] = []
    total = 0
    dev_spec_new = _load_dev_spec_new_substrate(vault)  # v1.51 perf fix: cached helper

    for path, fm in _iter_doc_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        tdc = fm.get('triggered_by_dev_cycle')
        if not tdc or tdc not in dev_spec_new:
            continue
        new_substrate = dev_spec_new[tdc]
        if not new_substrate:
            continue
        dcr = fm.get('doc_changes_required') or []
        # Render dcr entries as a flat searchable string for substring matching
        dcr_blob = ' '.join(
            str(e.get('path', '')) + ' ' + str(e.get('change_summary', ''))
            for e in dcr if isinstance(e, dict)
        )
        for new_uid in new_substrate:
            if new_uid not in dcr_blob and 'no doc impact' not in dcr_blob.lower():
                findings.append(
                    f'[WARN] {rel} — triggering dev-spec NEW substrate {new_uid} not referenced in '
                    f'doc_changes_required AND no "no doc impact: <rationale>" justification (Rule 4 cross-validation)'
                )
    return findings, total, len(findings)


# =============================================================================
# 11. check_doc_spec_close_invariants
# =============================================================================

def check_doc_spec_close_invariants(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    for path, fm in _iter_doc_specs(vault):
        total += 1
        if fm.get('stage') != 'done' or fm.get('state') != 'active':
            continue
        rel = path.relative_to(vault)
        if not fm.get('closed_at'):
            findings.append(f'[WARN] {rel} — stage:done + state:active requires closed_at field')
    return findings, total, len(findings)


# =============================================================================
# 12. check_doc_spec_supersession_bidirectional
# =============================================================================

def check_doc_spec_supersession_bidirectional(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    doc_spec_fm: dict[str, dict] = {}
    doc_spec_path: dict[str, Path] = {}
    for path, fm in _iter_doc_specs(vault):
        total += 1
        uid = fm.get('uid')
        if uid:
            doc_spec_fm[uid] = fm
            doc_spec_path[uid] = path

    for uid, fm in doc_spec_fm.items():
        rel = doc_spec_path[uid].relative_to(vault)
        sb = fm.get('superseded_by')
        sp = fm.get('supersedes')
        if sb:
            target = doc_spec_fm.get(sb)
            if target and target.get('supersedes') != uid:
                findings.append(
                    f'[WARN] {rel} — superseded_by {sb} but {sb}.supersedes is {target.get("supersedes")!r} (Rule 7 bidirectional pair violation)'
                )
        if sp:
            target = doc_spec_fm.get(sp)
            if target and target.get('superseded_by') != uid:
                findings.append(
                    f'[WARN] {rel} — supersedes {sp} but {sp}.superseded_by is {target.get("superseded_by")!r} (Rule 7 bidirectional pair violation)'
                )
    return findings, total, len(findings)


# =============================================================================
# 13. check_doc_spec_per_tier_with_new_substrate (NEW v1.0 per Q4 walk lock)
# =============================================================================

def check_doc_spec_per_tier_with_new_substrate(vault: Path) -> tuple[list[str], int, int]:
    """Soft WARN: per-tier doc-spec with triggering dev-spec NEW substrate suggests
    multi-tier may be more appropriate. Surfaces the multi-tier-default question at
    authoring time without blocking legitimate per-tier cases."""
    findings: list[str] = []
    total = 0
    # v1.51 perf fix: derive has-NEW map from cached _load_dev_spec_new_substrate
    dev_spec_has_new = {uid: bool(targets) for uid, targets in _load_dev_spec_new_substrate(vault).items()}

    for path, fm in _iter_doc_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        tier = fm.get('target_tier')
        if tier not in ('summary', 'subsystem', 'spec'):
            continue  # multi-tier is the recommended default; skip
        tdc = fm.get('triggered_by_dev_cycle')
        if tdc and dev_spec_has_new.get(tdc):
            # Check if change_summary mentions tier-isolation rationale
            dcr = fm.get('doc_changes_required') or []
            dcr_blob = ' '.join(
                str(e.get('change_summary', '')) for e in dcr if isinstance(e, dict)
            ).lower()
            isolation_markers = ('tier-isolated', 'tier isolated', 'subsystem hubs unchanged',
                                 'specs unchanged', 'summary unchanged')
            if not any(m in dcr_blob for m in isolation_markers):
                findings.append(
                    f'[WARN] {rel} — per-tier doc-spec (tier={tier}) with NEW substrate from triggering '
                    f'dev-spec — is this really tier-isolated? Consider target_tier:multi OR document '
                    f'rationale in change_summary (e.g., "tier-isolated; subsystem hubs unchanged")'
                )
    return findings, total, len(findings)


# =============================================================================
# 14. check_doc_spec_closure_claim_mtime_alignment — E4 v1.53 Lane E
# =============================================================================

def check_doc_spec_closure_claim_mtime_alignment(vault: Path) -> tuple[list[str], int, int]:
    """E4 — verify doc_changes_required cited paths reflect claimed change (mtime alignment).

    Per dev-spec [90ed15fb v1.1 LOCKED] §Lane E item E4:
      validator extension checks doc-spec entries' cited paths reflect claimed change
      (mtime + frontmatter alignment). WARN ratchet at v1.53; ERROR ratchet at v1.54.

    **v1.53 ships the LIGHTER mtime-alignment check.** For each doc_changes_required
    entry citing a target path, this check verifies the target file's filesystem mtime
    is GREATER than the doc-spec's modified timestamp. If the target's mtime is older,
    the closure-claim may be stale (target wasn't actually edited after doc-spec authoring).

    **v1.54 future-target:** frontmatter-alignment check (does target's frontmatter
    actually reflect the change_summary description). Deferred — heavier check requires
    semantic comparison of change_summary text vs target frontmatter content.

    **Skip conditions:**
    - change_summary contains "new-file" marker → mtime check inapplicable
      (new files have mtime ~= doc-spec mtime by construction)
    - path does not exist → existing check_doc_spec_doc_changes_paths_resolvable handles
    - doc-spec modified field missing → WARN about missing modified field
    - mtime parse fails → WARN about parse failure

    WARN at v1.53; ERROR ratchet at v1.54+.
    """
    from datetime import datetime, timezone
    import os

    findings: list[str] = []
    total = 0
    for path, fm in _iter_doc_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        # Get doc-spec authored timestamp (prefer modified, fall back to created)
        ts_str = fm.get('modified') or fm.get('created')
        if not ts_str:
            findings.append(f'[WARN] {rel} — doc-spec missing modified/created field; E4 mtime-alignment check cannot fire')
            continue
        # Parse timestamp — accept ISO 8601 date or datetime
        ts_str = str(ts_str).strip()
        try:
            if 'T' in ts_str:
                doc_spec_ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            else:
                # Date-only; treat as start-of-day UTC
                doc_spec_ts = datetime.strptime(ts_str[:10], '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            findings.append(f'[WARN] {rel} — doc-spec modified/created field unparseable: {ts_str!r}; E4 mtime-alignment check skipped')
            continue
        doc_spec_mtime = doc_spec_ts.timestamp()

        dcr = fm.get('doc_changes_required') or []
        if not isinstance(dcr, list):
            continue
        for idx, entry in enumerate(dcr):
            if not isinstance(entry, dict):
                continue
            p = entry.get('path')
            cs = entry.get('change_summary', '')
            if not p:
                continue
            # Skip new-file markers (mtime check inapplicable by construction)
            if 'new-file' in str(cs).lower() or 'new-files' in str(cs).lower():
                continue
            # Skip change_class:NEW entries when present
            if entry.get('change_class') == 'NEW':
                continue
            target_path = vault / p
            if not target_path.exists():
                # Path doesn't exist; existing check_doc_spec_doc_changes_paths_resolvable handles
                continue
            try:
                target_mtime = os.path.getmtime(target_path)
            except OSError:
                continue
            # Allow 24-hour grace window (doc-spec authored same-day as target edit is common)
            grace_seconds = 86400  # 24h
            if target_mtime < (doc_spec_mtime - grace_seconds):
                from datetime import datetime as dt
                target_dt = dt.fromtimestamp(target_mtime, tz=timezone.utc).strftime('%Y-%m-%d')
                doc_dt = doc_spec_ts.strftime('%Y-%m-%d')
                findings.append(
                    f'[WARN] {rel} — doc_changes_required[{idx}] path {p!r} mtime ({target_dt}) older than doc-spec modified ({doc_dt}) '
                    f'beyond 24h grace; closure-claim may be stale (target not edited after doc-spec authored). '
                    f'E4 mtime-alignment WARN at v1.53; ERROR ratchet at v1.54.'
                )
    return findings, total, len(findings)


# =============================================================================
# Aggregator
# =============================================================================

def check_doc_spec_orpheus_disposition_signoff(vault: Path) -> tuple[list[str], int, int]:
    """E7 (v1.53) — WARN on closed doc-spec entries missing Orpheus disposition signoff.

    Per doc-spec.capsule v1.0.1 §Validation Checks Check 14 (E7 engine wiring):
      if stage: done, frontmatter MUST include orpheus_disposition_signoff: object
      with required subfields: attested_by + attested_at + attestation_text (non-empty)
      + substantive_completeness (enum: PASS / PASS-with-findings / FAIL-incomplete).

    WARN at v1.53 (grace cycle); ERROR ratchet at v1.54+.
    """
    REQUIRED_SUBFIELDS = ('attested_by', 'attested_at', 'attestation_text', 'substantive_completeness')
    VALID_COMPLETENESS = {'PASS', 'PASS-with-findings', 'FAIL-incomplete'}

    findings: list[str] = []
    total = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return [], 0, 0

    for path in sorted(files_dir.glob('*.md')):
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        if 'type: doc-spec' not in text and 'type: "doc-spec"' not in text:
            continue
        if 'stage: done' not in text and 'stage: "done"' not in text:
            continue
        try:
            import yaml as _yaml
            end = text.find('\n---\n', 4)
            fm = _yaml.safe_load(text[4:end]) if end > 0 and text.startswith('---\n') else {}
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get('type') != 'doc-spec' or fm.get('stage') != 'done':
            continue
        total += 1
        rel = path.relative_to(vault)
        signoff = fm.get('orpheus_disposition_signoff')
        if not signoff or not isinstance(signoff, dict):
            findings.append(
                f'  [WARN] {rel} — doc-spec stage:done missing orpheus_disposition_signoff '
                f'(E7 Check 14; WARN at v1.53; ERROR ratchet v1.54+)'
            )
            continue
        missing = [f for f in REQUIRED_SUBFIELDS if not signoff.get(f)]
        if missing:
            findings.append(
                f'  [WARN] {rel} — orpheus_disposition_signoff missing/empty subfields: '
                f'{", ".join(missing)} (E7 Check 14; WARN at v1.53)'
            )
        sc = signoff.get('substantive_completeness', '')
        if sc not in VALID_COMPLETENESS:
            findings.append(
                f'  [WARN] {rel} — orpheus_disposition_signoff.substantive_completeness '
                f'invalid value {sc!r}; expected one of {sorted(VALID_COMPLETENESS)} '
                f'(E7 Check 14; WARN at v1.53)'
            )

    return findings, total, len(findings)


DOC_SPEC_CHECKS = (
    ('check_doc_spec_required_fields', check_doc_spec_required_fields),
    ('check_doc_spec_target_subsystem_resolvable', check_doc_spec_target_subsystem_resolvable),
    ('check_doc_spec_target_tier_valid', check_doc_spec_target_tier_valid),
    ('check_doc_spec_doc_changes_required_non_empty', check_doc_spec_doc_changes_required_non_empty),
    ('check_doc_spec_doc_changes_paths_resolvable', check_doc_spec_doc_changes_paths_resolvable),
    ('check_doc_spec_triggered_by_dev_cycle_resolvable', check_doc_spec_triggered_by_dev_cycle_resolvable),
    ('check_doc_spec_acceptance_criteria_present', check_doc_spec_acceptance_criteria_present),
    ('check_doc_spec_voice_review_evidence_present', check_doc_spec_voice_review_evidence_present),
    ('check_doc_spec_cross_reference_check_evidence', check_doc_spec_cross_reference_check_evidence),
    ('check_doc_spec_cross_validation_against_dev_spec', check_doc_spec_cross_validation_against_dev_spec),
    ('check_doc_spec_close_invariants', check_doc_spec_close_invariants),
    ('check_doc_spec_supersession_bidirectional', check_doc_spec_supersession_bidirectional),
    ('check_doc_spec_per_tier_with_new_substrate', check_doc_spec_per_tier_with_new_substrate),
    ('check_doc_spec_closure_claim_mtime_alignment', check_doc_spec_closure_claim_mtime_alignment),
    ('check_doc_spec_orpheus_disposition_signoff', check_doc_spec_orpheus_disposition_signoff),
)


def run_all_doc_spec_checks(vault: Path) -> tuple[list[str], int, int]:
    all_findings: list[str] = []
    total = 0
    total_defects = 0
    for name, check_fn in DOC_SPEC_CHECKS:
        findings, checked, defects = check_fn(vault)
        all_findings.extend(findings)
        total = max(total, checked)
        total_defects += defects
    return all_findings, total, total_defects
