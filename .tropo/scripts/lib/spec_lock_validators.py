"""Spec LOCK-signoff validator extensions for tropo-validate.py — Lane E E3.

Authored by Argus A83 2026-05-25 captain-mode under v1.53 cycle Lane E per:
- v1.53 dev-spec [90ed15fb v1.1 LOCKED] §Lane E item E3
- v1.53 cycle brief [17881ea9 v0.3 LOCKED] §3 Lane E E3
- dev-spec.capsule v1.0.1 + doc-spec.capsule v1.0 + test-spec.capsule v1.0
  §Required Frontmatter sections (canonical source-of-truth for required-field lists)

**Purpose:** structurally close the substrate-verify-twice defect class
(stm-a82-004 + stm-a83-001) at LOCK-signoff time. Existing per-capsule lib
modules (dev_spec_validators.py + doc_spec_validators.py + test_spec_validators.py)
fire required-field checks at WARN severity for ALL entries; this module
adds a STRICT ERROR ratchet that ONLY fires on entries at status:locked.

**Behavior:**
- Iterates *-spec entries (dev-spec / doc-spec / test-spec)
- ONLY checks entries with status:locked (draft / active / superseded entries SKIPPED)
- Returns [FAIL] for missing required fields → rebuild halts → LOCK refused
- Composes with existing per-capsule WARN-class checks (does NOT replace)

**E3 cycle position:** v1.53 ships this at ERROR ratchet (not WARN). When wired
into tropo-validate.py main() by Talos T10, any *-spec entry that achieves
status:locked with missing required fields will halt rebuild — substrate-discipline
becomes structurally enforced at the LOCK moment.

**Wired by Talos T10 at:** tropo-validate.py main() — see argus-talos bilateral
channel for wiring instructions (function signature + import location).

Composes-with:
- lib/dev_spec_validators.py (existing WARN-class; v1.51 Argus A80)
- lib/doc_spec_validators.py (existing WARN-class; v1.51 Argus A80)
- lib/test_spec_validators.py (existing WARN-class; v1.51 Argus A80)
- check_engine_no_direct_vault_unlink wiring pattern (v1.52 T10 reference)
- check_kb_content_no_slug_collisions wiring pattern (Cycle 4 reference)
"""



from __future__ import annotations

TARGETS_CAPSULE = "dev-spec"  # Lane V Layer 3 M.1 targeting (8e2f1a47)
from pathlib import Path
from typing import Any

import yaml


def _split_frontmatter(text: str) -> str | None:
    """Extract raw YAML frontmatter block (between leading --- delimiters)."""
    if not text.startswith('---\n'):
        return None
    end = text.find('\n---\n', 4)
    if end == -1:
        return None
    return text[4:end]


def _iter_locked_specs(vault: Path, spec_type: str):
    """Yield (path, frontmatter_dict) for vault entries of given type at status:locked.

    spec_type: one of 'dev-spec' / 'doc-spec' / 'test-spec'.
    Only entries with status:locked are yielded; all other status values are skipped.
    Parse failures are silently skipped (logged elsewhere by existing checks).
    """
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return
    for path in sorted(files_dir.glob('*.md')):
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        fm_text = _split_frontmatter(text)
        if not fm_text:
            continue
        # Fast pre-filter: skip files that don't mention both fields at all
        if f'type: {spec_type}' not in fm_text and f'type: "{spec_type}"' not in fm_text and f"type: '{spec_type}'" not in fm_text:
            continue
        if 'status: locked' not in fm_text and 'status: "locked"' not in fm_text and "status: 'locked'" not in fm_text:
            continue
        try:
            fm = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get('type') != spec_type or fm.get('status') != 'locked':
            continue
        yield path, fm


# =============================================================================
# E3.1 — dev-spec LOCK-strict required fields
# =============================================================================

DEV_SPEC_REQUIRED = ('type', 'target_release', 'target_stream', 'committed_substrate', 'acceptance_criteria')


def check_dev_spec_locked_required_fields_strict(vault: Path) -> tuple[list[str], int, int]:
    """E3 — FAIL on locked dev-spec entries missing required frontmatter fields.

    Required fields per dev-spec.capsule v1.0.1 §Required Frontmatter:
      type / target_release / target_stream / committed_substrate / acceptance_criteria

    target_stream MAY be explicitly null (presence is what counts); other fields MUST be populated.

    LOCK signoff ratchet: missing required field on a status:locked dev-spec = [FAIL].
    Drafts + active-unlocked entries are skipped (existing WARN-class check handles those).
    """
    findings: list[str] = []
    total = 0
    for path, fm in _iter_locked_specs(vault, 'dev-spec'):
        total += 1
        rel = path.relative_to(vault)
        missing = [k for k in DEV_SPEC_REQUIRED if k not in fm]
        if missing:
            findings.append(
                f'[FAIL] {rel} — dev-spec LOCKED missing required fields: {", ".join(missing)} '
                f'(E3 LOCK-signoff strict; refuses LOCK transition with missing required-field gap)'
            )
        # Also catch fields that are present but empty/null when they shouldn't be
        if 'committed_substrate' in fm:
            cs = fm.get('committed_substrate')
            if not isinstance(cs, list) or not cs:
                findings.append(
                    f'[FAIL] {rel} — dev-spec LOCKED committed_substrate empty or non-list '
                    f'(E3 LOCK-signoff strict; Rule 2 anti-fuzzy-framing enforced at LOCK)'
                )
        if 'acceptance_criteria' in fm:
            ac = fm.get('acceptance_criteria')
            if not ac or (isinstance(ac, str) and not ac.strip()):
                findings.append(
                    f'[FAIL] {rel} — dev-spec LOCKED acceptance_criteria empty '
                    f'(E3 LOCK-signoff strict; must be populated at LOCK)'
                )
    return findings, total, len(findings)


# =============================================================================
# E3.2 — doc-spec LOCK-strict required fields
# =============================================================================

DOC_SPEC_REQUIRED = ('type', 'target_subsystem', 'target_tier', 'triggered_by_dev_cycle',
                    'doc_changes_required', 'acceptance_criteria')


def check_doc_spec_locked_required_fields_strict(vault: Path) -> tuple[list[str], int, int]:
    """E3 — FAIL on locked doc-spec entries missing required frontmatter fields.

    Required fields per doc-spec.capsule v1.0 §Required Frontmatter:
      type / target_subsystem / target_tier / triggered_by_dev_cycle /
      doc_changes_required / acceptance_criteria

    target_subsystem MAY be explicitly null for multi-tier cross-cutting work.

    LOCK signoff ratchet: missing required field on a status:locked doc-spec = [FAIL].
    """
    findings: list[str] = []
    total = 0
    for path, fm in _iter_locked_specs(vault, 'doc-spec'):
        total += 1
        rel = path.relative_to(vault)
        missing = [k for k in DOC_SPEC_REQUIRED if k not in fm]
        if missing:
            findings.append(
                f'[FAIL] {rel} — doc-spec LOCKED missing required fields: {", ".join(missing)} '
                f'(E3 LOCK-signoff strict; refuses LOCK transition with missing required-field gap)'
            )
        # doc_changes_required must be non-empty list at LOCK
        if 'doc_changes_required' in fm:
            dcr = fm.get('doc_changes_required')
            if not isinstance(dcr, list) or not dcr:
                findings.append(
                    f'[FAIL] {rel} — doc-spec LOCKED doc_changes_required empty or non-list '
                    f'(E3 LOCK-signoff strict; must enumerate concrete doc changes at LOCK)'
                )
    return findings, total, len(findings)


# =============================================================================
# E3.3 — test-spec LOCK-strict required fields
# =============================================================================

TEST_SPEC_REQUIRED = ('type', 'target_substrate', 'target_subsystem', 'triggered_by_dev_cycle',
                     'behaviors_covered', 'coverage_class', 'acceptance_criteria')


def check_test_spec_locked_required_fields_strict(vault: Path) -> tuple[list[str], int, int]:
    """E3 — FAIL on locked test-spec entries missing required frontmatter fields.

    Required fields per test-spec.capsule v1.0 §Required Frontmatter:
      type / target_substrate / target_subsystem / triggered_by_dev_cycle /
      behaviors_covered / coverage_class / acceptance_criteria

    target_subsystem MAY be explicitly null for multi-subsystem cross-cutting work.

    LOCK signoff ratchet: missing required field on a status:locked test-spec = [FAIL].
    """
    findings: list[str] = []
    total = 0
    for path, fm in _iter_locked_specs(vault, 'test-spec'):
        total += 1
        rel = path.relative_to(vault)
        missing = [k for k in TEST_SPEC_REQUIRED if k not in fm]
        if missing:
            findings.append(
                f'[FAIL] {rel} — test-spec LOCKED missing required fields: {", ".join(missing)} '
                f'(E3 LOCK-signoff strict; refuses LOCK transition with missing required-field gap)'
            )
        # behaviors_covered must be non-empty list at LOCK
        if 'behaviors_covered' in fm:
            bc = fm.get('behaviors_covered')
            if not isinstance(bc, list) or not bc:
                findings.append(
                    f'[FAIL] {rel} — test-spec LOCKED behaviors_covered empty or non-list '
                    f'(E3 LOCK-signoff strict; must enumerate concrete behaviors at LOCK)'
                )
    return findings, total, len(findings)


# =============================================================================
# Wrapper — run all three LOCK-strict checks; aggregated result for tropo-validate.py main()
# =============================================================================

def run_all_spec_lock_checks(vault: Path) -> tuple[list[str], int, int]:
    """Run all E3 *-spec LOCK-strict required-field checks; aggregated result.

    Returns (findings, total_locked_specs_checked, defects).

    Wired by Talos T10 in tropo-validate.py main() as a new check section.
    Section header (canonical pattern matching existing v1.51 sections):

      --- Spec LOCK-signoff Required Fields (v1.53 Lane E E3; ERROR ratchet) ---
      run_all_spec_lock_checks(vault)

    Composes-with the existing per-capsule WARN-class required-field checks at:
      - lib/dev_spec_validators.py::check_dev_spec_required_fields (WARN)
      - lib/doc_spec_validators.py::check_doc_spec_required_fields (WARN)
      - lib/test_spec_validators.py::check_test_spec_required_fields (WARN)

    The WARN checks fire on ALL entries; this LOCK-strict family fires ONLY on
    status:locked entries with FAIL severity. The pairing means:
      - Draft *-spec authoring: WARN guides authors to required-field shape
      - LOCK *-spec transition: FAIL enforces required-field completeness structurally
    """
    all_findings: list[str] = []
    total_locked = 0
    total_defects = 0

    dev_findings, dev_total, dev_defects = check_dev_spec_locked_required_fields_strict(vault)
    all_findings.extend(dev_findings)
    total_locked += dev_total
    total_defects += dev_defects

    doc_findings, doc_total, doc_defects = check_doc_spec_locked_required_fields_strict(vault)
    all_findings.extend(doc_findings)
    total_locked += doc_total
    total_defects += doc_defects

    test_findings, test_total, test_defects = check_test_spec_locked_required_fields_strict(vault)
    all_findings.extend(test_findings)
    total_locked += test_total
    total_defects += test_defects

    return all_findings, total_locked, total_defects
