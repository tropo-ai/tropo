"""test-spec.capsule v1.0 validator extensions for tropo-validate.py.

Authored by Argus A80 2026-05-23 captain-mode under v1.51 Phase B per:
- test-spec.capsule v1.0 LOCKED §Validation Checks (UID 621824df; LOCKED by Mike-V51 + Vela V51 walk 2026-05-23)
- v1.51 cycle brief 1feefe68 §Six Artifacts row 3

14 checks per capsule §Validation Checks. WARN at v1.0; ERROR ratchet at v1.51.1+ except
Check 6 cross-validation (ERROR ratchet v1.1 per Walk Lock Decision SQ1 mandate framing).
v1.10-v1.50 legacy cycles grandfathered per Rule 8.
"""



from __future__ import annotations

TARGETS_CAPSULE = "test-spec"  # Lane V Layer 3 M.1 targeting (8e2f1a47)
from functools import lru_cache
from pathlib import Path

import yaml

# v1.51 perf fix (Argus A80 2026-05-23): @lru_cache on loader functions.
# Pattern matches dev_spec_validators.py + doc_spec_validators.py.

# Verification method enum (5 entries per Walk Lock Decision SQ2; agentic_review NEW v1.0)
VALID_VERIFICATION_METHODS = frozenset({
    'machine_executable_script', 'deterministic_assertion', 'structural_check',
    'agentic_review', 'manual_walk'
})

# Machine-side methods (counted against ceiling math complement)
MACHINE_SIDE_METHODS = frozenset({
    'machine_executable_script', 'deterministic_assertion', 'structural_check', 'agentic_review'
})

VALID_COVERAGE_CLASSES = frozenset({
    'regression', 'smoke', 'cold-boot', 'gauntlet', 'property'
})

VALID_CYCLE_CLASSES = frozenset({'substrate', 'ux', 'engine-runtime'})

MANUAL_WALK_HARD_CAP = 50  # Walk Lock Decision SQ3
DEFAULT_MANUAL_WALK_CEILING = 30


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
def _load_test_specs(vault: Path) -> tuple:
    """Cached: all type=test-spec entries."""
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
        if fm.get('type') != 'test-spec':
            continue
        out.append((f, fm))
    return tuple(out)


def _iter_test_specs(vault: Path):
    yield from _load_test_specs(vault)


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
def _load_dev_spec_new_substrate(vault: Path) -> dict:
    """Cached: dev-spec UID → committed_substrate NEW target UIDs."""
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
def _load_sa_class_registry(vault: Path) -> frozenset:
    """Load registered sa.* class names from .tropo-studio/registries/registry.jsonl."""
    import json
    classes: set[str] = set()
    reg = vault / '.tropo-studio' / 'registries' / 'registry.jsonl'
    if not reg.exists():
        return frozenset(classes)
    try:
        with reg.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict) and entry.get('type') == 'session-agent':
                        name = entry.get('name') or entry.get('slug')
                        if isinstance(name, str):
                            classes.add(name)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return frozenset(classes)


# =============================================================================
# 1. check_test_spec_required_fields (+ cycle_class WARN-if-absent)
# =============================================================================

def check_test_spec_required_fields(vault: Path) -> tuple[list[str], int, int]:
    required = ('type', 'target_substrate', 'target_subsystem', 'triggered_by_dev_cycle',
                'behaviors_covered', 'coverage_class', 'acceptance_criteria')
    findings: list[str] = []
    total = 0
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        missing = [k for k in required if k not in fm]
        if missing:
            findings.append(f'[WARN] {rel} — test-spec missing required fields: {", ".join(missing)}')
        # cycle_class WARN-if-absent at v1.0 (ERROR ratchet at v1.1)
        if 'cycle_class' not in fm:
            findings.append(f'[WARN] {rel} — cycle_class absent at v1.0 (optional v1.0 with inference fallback; required v1.1+); inference fires')
    return findings, total, len(findings)


# =============================================================================
# 2. check_test_spec_target_substrate_resolvable
# =============================================================================

def check_test_spec_target_substrate_resolvable(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    index_uids = _load_vault_index_uids(vault)
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        ts = fm.get('target_substrate') or []
        if not isinstance(ts, list):
            findings.append(f'[WARN] {rel} — target_substrate must be a UID list')
            continue
        for t in ts:
            if isinstance(t, str) and t not in index_uids:
                findings.append(f'[WARN] {rel} — target_substrate UID {t} does not resolve in vault index')
    return findings, total, len(findings)


# =============================================================================
# 3. check_test_spec_behaviors_covered_non_empty
# =============================================================================

def check_test_spec_behaviors_covered_non_empty(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        bc = fm.get('behaviors_covered') or []
        if not isinstance(bc, list) or not bc:
            findings.append(f'[WARN] {rel} — behaviors_covered empty (Rule 2 anti-box-checking floor)')
    return findings, total, len(findings)


# =============================================================================
# 4. check_test_spec_verification_method_declared
# =============================================================================

def check_test_spec_verification_method_declared(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        bc = fm.get('behaviors_covered') or []
        if not isinstance(bc, list):
            continue
        for idx, entry in enumerate(bc):
            if not isinstance(entry, dict):
                findings.append(f'[WARN] {rel} — behaviors_covered[{idx}] must be an object')
                continue
            vm = entry.get('verification_method')
            if not vm:
                findings.append(f'[WARN] {rel} — behaviors_covered[{idx}] missing verification_method')
                continue
            if vm not in VALID_VERIFICATION_METHODS:
                findings.append(
                    f'[WARN] {rel} — behaviors_covered[{idx}] verification_method {vm!r} not in {sorted(VALID_VERIFICATION_METHODS)}'
                )
    return findings, total, len(findings)


# =============================================================================
# 5. check_test_spec_verification_method_substrate_resolvable
# =============================================================================

def check_test_spec_verification_method_substrate_resolvable(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    sa_classes = _load_sa_class_registry(vault)
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        bc = fm.get('behaviors_covered') or []
        if not isinstance(bc, list):
            continue
        for idx, entry in enumerate(bc):
            if not isinstance(entry, dict):
                continue
            vm = entry.get('verification_method')
            tsp = entry.get('test_substrate_path', '')
            if vm == 'machine_executable_script':
                target = vault / tsp if tsp else None
                # v1.51 perf fix: accept "new-file" marker in EITHER test_substrate_path OR behavior_description
                # (test scripts Phase D / Talos engineering will author; declaration at test-spec authoring time is correct)
                desc = entry.get('behavior_description', '')
                new_file_marker = 'new-file' in str(tsp).lower() or 'new-file' in str(desc).lower()
                if not target or (not target.exists() and not new_file_marker):
                    findings.append(
                        f'[WARN] {rel} — behaviors_covered[{idx}] machine_executable_script test_substrate_path {tsp!r} '
                        f'does not exist (and no "new-file" marker in test_substrate_path or behavior_description)'
                    )
            elif vm == 'agentic_review':
                dt = entry.get('dispatch_target')
                if not dt:
                    findings.append(
                        f'[WARN] {rel} — behaviors_covered[{idx}] agentic_review requires dispatch_target (sa.* class name)'
                    )
                elif sa_classes and dt not in sa_classes:
                    # Soft check; registry may not enumerate all sa.* classes
                    findings.append(
                        f'[INFO] {rel} — behaviors_covered[{idx}] dispatch_target {dt!r} not found in '
                        f'.tropo-studio/registries/registry.jsonl session-agent entries (may be class not yet registered)'
                    )
            elif vm == 'manual_walk':
                desc = entry.get('behavior_description', '')
                if not isinstance(desc, str) or len(desc) < 50:
                    findings.append(
                        f'[WARN] {rel} — behaviors_covered[{idx}] manual_walk requires behavior_description ≥50 chars (got {len(desc) if isinstance(desc, str) else "non-string"})'
                    )
    return findings, total, len(findings)


# =============================================================================
# 6. check_test_spec_cross_validation_against_dev_spec (MANDATED per SQ1)
# =============================================================================

def check_test_spec_cross_validation_against_dev_spec(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    dev_spec_new = _load_dev_spec_new_substrate(vault)
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        tdc = fm.get('triggered_by_dev_cycle')
        if not tdc or tdc not in dev_spec_new:
            continue
        new_substrate = dev_spec_new[tdc]
        if not new_substrate:
            continue
        bc = fm.get('behaviors_covered') or []
        all_refs: set[str] = set()
        for entry in bc:
            if isinstance(entry, dict):
                refs = entry.get('target_substrate_refs') or []
                if isinstance(refs, list):
                    all_refs.update(r for r in refs if isinstance(r, str))
        for new_uid in new_substrate:
            if new_uid not in all_refs:
                # Structural-only exception per Rule 3
                coverage_class = fm.get('coverage_class')
                if coverage_class == 'structural_check':
                    continue
                findings.append(
                    f'[WARN] {rel} — triggering dev-spec NEW substrate {new_uid} not in any behaviors_covered.target_substrate_refs '
                    f'(Rule 3 cross-validation MANDATED; engine refuses test-pipeline activation on this gap)'
                )
    return findings, total, len(findings)


# =============================================================================
# 7. check_test_spec_manual_walk_ceiling
# =============================================================================

def check_test_spec_manual_walk_ceiling(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        bc = fm.get('behaviors_covered') or []
        if not isinstance(bc, list) or not bc:
            continue
        manual_count = sum(
            1 for e in bc
            if isinstance(e, dict) and e.get('verification_method') == 'manual_walk'
        )
        total_methods = sum(1 for e in bc if isinstance(e, dict) and e.get('verification_method'))
        if total_methods == 0:
            continue
        manual_pct = (manual_count * 100) // total_methods
        ceiling = fm.get('manual_walk_ceiling_override') or fm.get('manual_walk_percentage_ceiling', DEFAULT_MANUAL_WALK_CEILING)
        try:
            ceiling = int(ceiling)
        except (ValueError, TypeError):
            ceiling = DEFAULT_MANUAL_WALK_CEILING
        if manual_pct > ceiling:
            findings.append(
                f'[WARN] {rel} — manual_walk percentage {manual_pct}% exceeds ceiling {ceiling}% '
                f'({manual_count}/{total_methods} behaviors are manual_walk)'
            )
    return findings, total, len(findings)


# =============================================================================
# 8. check_test_spec_coverage_class_completeness
# =============================================================================

def check_test_spec_coverage_class_completeness(vault: Path) -> tuple[list[str], int, int]:
    """Per-cycle-class minima per §Coverage Class Semantics table.
    Checks against cycle_class value (or inferred class at v1.0).
    Conditional flags (gauntlet REQUIRED if OS-tier, regression REQUIRED if AMENDS) are
    informational at v1.0; full conditional check defers to v1.1."""
    findings: list[str] = []
    total = 0

    # Per-cycle-class floor (the unconditional minima):
    # substrate: smoke + structural_check coverage class lens
    # ux: smoke + cold-boot
    # engine-runtime: smoke + property
    floor: dict[str, set[str]] = {
        'substrate': {'smoke'},  # structural_check is a verification_method, not coverage_class; use smoke as the entry
        'ux': {'smoke', 'cold-boot'},
        'engine-runtime': {'smoke', 'property'},
    }

    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        cycle_class = fm.get('cycle_class')
        if cycle_class is None:
            continue  # check 1 catches absence + emits inference WARN
        if cycle_class not in VALID_CYCLE_CLASSES:
            findings.append(f'[WARN] {rel} — cycle_class {cycle_class!r} not in {sorted(VALID_CYCLE_CLASSES)}')
            continue
        coverage = fm.get('coverage_class')
        if isinstance(coverage, str):
            coverage_set = {coverage}
        elif isinstance(coverage, list):
            coverage_set = {c for c in coverage if isinstance(c, str)}
        else:
            coverage_set = set()
        required = floor.get(cycle_class, set())
        missing = required - coverage_set
        if missing:
            findings.append(
                f'[WARN] {rel} — cycle_class={cycle_class} requires coverage_class minima {sorted(required)} '
                f'(missing: {sorted(missing)})'
            )
    return findings, total, len(findings)


# =============================================================================
# 9. check_test_spec_triggered_by_dev_cycle_resolvable
# =============================================================================

def check_test_spec_triggered_by_dev_cycle_resolvable(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    index_uids = _load_vault_index_uids(vault)
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        tdc = fm.get('triggered_by_dev_cycle')
        if not tdc:
            continue
        if isinstance(tdc, str) and tdc not in index_uids:
            findings.append(f'[WARN] {rel} — triggered_by_dev_cycle {tdc} does not resolve in vault index')
    return findings, total, len(findings)


# =============================================================================
# 10. check_test_spec_acceptance_criteria_present
# =============================================================================

def check_test_spec_acceptance_criteria_present(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        ac = fm.get('acceptance_criteria')
        if not ac or (isinstance(ac, str) and not ac.strip()):
            findings.append(f'[WARN] {rel} — acceptance_criteria empty (Rule 5 violation)')
    return findings, total, len(findings)


# =============================================================================
# 11. check_test_spec_close_invariants
# =============================================================================

def check_test_spec_close_invariants(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    for path, fm in _iter_test_specs(vault):
        total += 1
        if fm.get('stage') != 'done' or fm.get('state') != 'active':
            continue
        rel = path.relative_to(vault)
        if not fm.get('closed_at'):
            findings.append(f'[WARN] {rel} — stage:done + state:active requires closed_at')
        evidence = fm.get('acceptance_evidence') or []
        if not evidence:
            findings.append(f'[WARN] {rel} — close requires acceptance_evidence (test-pass + coverage-audit UIDs)')
        # When harness_framework_changes_required:true, ALSO requires harness_extension_landed_evidence
        if fm.get('harness_framework_changes_required'):
            harness_ev = fm.get('harness_extension_landed_evidence') or []
            if not harness_ev:
                findings.append(
                    f'[WARN] {rel} — harness_framework_changes_required=true at close requires harness_extension_landed_evidence (per SQ5 scope-expansion rule)'
                )
    return findings, total, len(findings)


# =============================================================================
# 12. check_test_spec_supersession_bidirectional
# =============================================================================

def check_test_spec_supersession_bidirectional(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    test_spec_fm: dict[str, dict] = {}
    test_spec_path: dict[str, Path] = {}
    for path, fm in _iter_test_specs(vault):
        total += 1
        uid = fm.get('uid')
        if uid:
            test_spec_fm[uid] = fm
            test_spec_path[uid] = path
    for uid, fm in test_spec_fm.items():
        rel = test_spec_path[uid].relative_to(vault)
        sb = fm.get('superseded_by')
        sp = fm.get('supersedes')
        if sb:
            target = test_spec_fm.get(sb)
            if target and target.get('supersedes') != uid:
                findings.append(f'[WARN] {rel} — superseded_by {sb} but back-pointer broken')
        if sp:
            target = test_spec_fm.get(sp)
            if target and target.get('superseded_by') != uid:
                findings.append(f'[WARN] {rel} — supersedes {sp} but back-pointer broken')
    return findings, total, len(findings)


# =============================================================================
# 13. check_test_spec_harness_framework_changes_required_evidence (NEW v1.0 SQ5)
# =============================================================================

def check_test_spec_harness_framework_changes_required_evidence(vault: Path) -> tuple[list[str], int, int]:
    """When harness_framework_changes_required:true, cycle scope must include harness extension authoring."""
    findings: list[str] = []
    total = 0
    for path, fm in _iter_test_specs(vault):
        total += 1
        if not fm.get('harness_framework_changes_required'):
            continue
        if fm.get('stage') != 'done':
            continue
        rel = path.relative_to(vault)
        harness_ev = fm.get('harness_extension_landed_evidence') or []
        if not harness_ev:
            findings.append(
                f'[WARN] {rel} — harness_framework_changes_required=true at close-time but harness_extension_landed_evidence empty (SQ5 violation)'
            )
    return findings, total, len(findings)


# =============================================================================
# 14. check_test_spec_manual_walk_override_valid (NEW v1.0 SQ3)
# =============================================================================

def check_test_spec_manual_walk_override_valid(vault: Path) -> tuple[list[str], int, int]:
    """When manual_walk_ceiling_override set: value ≤ 50 + override_rationale non-empty + ≥100 chars."""
    findings: list[str] = []
    total = 0
    for path, fm in _iter_test_specs(vault):
        total += 1
        override = fm.get('manual_walk_ceiling_override')
        if override is None:
            continue
        rel = path.relative_to(vault)
        try:
            override_int = int(override)
        except (ValueError, TypeError):
            findings.append(f'[WARN] {rel} — manual_walk_ceiling_override must be integer (got {type(override).__name__})')
            continue
        if override_int > MANUAL_WALK_HARD_CAP:
            findings.append(
                f'[FAIL] {rel} — manual_walk_ceiling_override={override_int} exceeds HARD CAP {MANUAL_WALK_HARD_CAP}% '
                f'(per SQ3; use coverage_class:cold-boot for cold-boot-walk cycles instead)'
            )
            continue
        rationale = fm.get('override_rationale', '')
        if not rationale or len(str(rationale)) < 100:
            findings.append(
                f'[FAIL] {rel} — manual_walk_ceiling_override requires override_rationale ≥100 chars '
                f'(got {len(str(rationale))} chars)'
            )
    return findings, total, len(findings)


# =============================================================================
# Aggregator
# =============================================================================

TEST_SPEC_CHECKS = (
    ('check_test_spec_required_fields', check_test_spec_required_fields),
    ('check_test_spec_target_substrate_resolvable', check_test_spec_target_substrate_resolvable),
    ('check_test_spec_behaviors_covered_non_empty', check_test_spec_behaviors_covered_non_empty),
    ('check_test_spec_verification_method_declared', check_test_spec_verification_method_declared),
    ('check_test_spec_verification_method_substrate_resolvable', check_test_spec_verification_method_substrate_resolvable),
    ('check_test_spec_cross_validation_against_dev_spec', check_test_spec_cross_validation_against_dev_spec),
    ('check_test_spec_manual_walk_ceiling', check_test_spec_manual_walk_ceiling),
    ('check_test_spec_coverage_class_completeness', check_test_spec_coverage_class_completeness),
    ('check_test_spec_triggered_by_dev_cycle_resolvable', check_test_spec_triggered_by_dev_cycle_resolvable),
    ('check_test_spec_acceptance_criteria_present', check_test_spec_acceptance_criteria_present),
    ('check_test_spec_close_invariants', check_test_spec_close_invariants),
    ('check_test_spec_supersession_bidirectional', check_test_spec_supersession_bidirectional),
    ('check_test_spec_harness_framework_changes_required_evidence', check_test_spec_harness_framework_changes_required_evidence),
    ('check_test_spec_manual_walk_override_valid', check_test_spec_manual_walk_override_valid),
)


def run_all_test_spec_checks(vault: Path) -> tuple[list[str], int, int]:
    all_findings: list[str] = []
    total = 0
    total_defects = 0
    for name, check_fn in TEST_SPEC_CHECKS:
        findings, checked, defects = check_fn(vault)
        all_findings.extend(findings)
        total = max(total, checked)
        total_defects += defects
    return all_findings, total, total_defects
