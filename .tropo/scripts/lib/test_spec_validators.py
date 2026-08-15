"""test-spec.capsule validator extensions for full and targeted validation.

Authored by Argus A80 2026-05-23 captain-mode under v1.51 Phase B per:
- test-spec.capsule v1.0 LOCKED §Validation Checks (UID 621824df; LOCKED by Mike-V51 + Vela V51 walk 2026-05-23)
- v1.51 cycle brief 1feefe68 §Six Artifacts row 3

Updated for v1.2 with one shared spec-family substrate-ref parser, activation
traversal, exact Rule 3 pairing, normalized coverage sets, and deterministic
strict/legacy severity.  The 14-check public family remains stable.
"""



from __future__ import annotations

TARGETS_CAPSULE = "test-spec"  # Lane V Layer 3 M.1 targeting (8e2f1a47)
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

import yaml

# Shared, memoized YAML parse (talos-t40 2026-08-09). One `tropo-validate` run
# parsed 108,000+ documents of which ~91% were byte-identical repeats, because
# each validator module carried its own private frontmatter parser. Routing them
# through one helper gets libyaml's C scanner AND one shared memo; a miss here
# would put this module back on the pure-Python path with a private cache.
try:
    from . import fast_yaml as _fast_yaml
except Exception:  # pragma: no cover - exercised by test_fast_yaml_shared_memo
    _fast_yaml = None


def _yaml_safe_load(_text):
    if _fast_yaml is not None:
        return _fast_yaml.safe_load(_text)
    return yaml.safe_load(_text)


try:
    from . import dev_spec_validators, spec_substrate_refs
except ImportError:  # check-one imports validator modules directly from this directory
    import dev_spec_validators
    import spec_substrate_refs

# v1.51 perf fix (Argus A80 2026-05-23): @lru_cache on loader functions.
# Pattern matches dev_spec_validators.py + doc_spec_validators.py.

# Verification method enum (5 entries per Walk Lock Decision SQ2; agentic_review NEW v1.0)
VALID_VERIFICATION_METHODS = frozenset({
    'machine_executable_script', 'deterministic_assertion', 'structural_check',
    'agentic_review', 'manual_walk'
})
RELEASE_PROVENANCE_FIELDS = (
    'triggered_by_release_pipeline',
    'release_plan_uid',
    'release_pipeline_run_uid',
)

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
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")
# Immutable cutover snapshot mandated by test-spec.capsule v1.2 ruling
# f123ea01.  Cohort authority comes only from this set: authored dates and
# historical generic capsule_version values have no effect.
FROZEN_LEGACY_TEST_SPEC_UIDS = frozenset({
    'f000241b', 'ac6e3792', 'c5ff0091', '7935333b', 'f317fb4a',
    '1fee7e4b', 'dcf2163e', '50ce4b13', '1cbbba56', '04881aa8',
    '010c52fc', '778bdca5', '05bd5e63', '18627ea6', 'd3c7e049',
    '9160d9e5', '8e1d7b95', 'c220d66f', '501c769f', 'd25c23e7',
    'd4e4edcf', 'c831c7a3', 'd436446c', 'e84c764a', '616c032b',
    '46f538a2', '2c281ded', 'b59f9e42', '93f2ca23', 'cb4ab049',
    'c4b3c86e', '700b01c7', '5a195c76', '460a6907', '6183301b',
    'e739a5d2', 'd3e8c5f7', '5046b725', '2cedb6a7', '9f1d3a85',
    '314b3329', '07f21597', 'ea352a6b', '0c9dbe07', 'e1ede9b4',
    'e1e67e07',
})


@dataclass(frozen=True)
class _ContractMode:
    legacy: bool
    version_error: str | None = None

    @property
    def severity(self) -> str:
        return "WARN" if self.legacy else "ERROR"


def _version_value(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = SEMVER_RE.fullmatch(value)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _contract_mode(frontmatter: dict, vault: Path) -> _ContractMode:
    """Return the deterministic v1.2 strict/legacy cohort classification."""

    del vault  # Cohort authority is the immutable UID set, never mutable state.
    uid = frontmatter.get('uid')
    if isinstance(uid, str) and uid in FROZEN_LEGACY_TEST_SPEC_UIDS:
        return _ContractMode(True)

    raw_version = frontmatter.get("capsule_version")
    version = _version_value(raw_version)
    if raw_version is None:
        return _ContractMode(
            False,
            "capsule_version is required for every UID outside the frozen v1.2 cohort",
        )
    if version is None:
        return _ContractMode(
            False,
            f"capsule_version {raw_version!r} must be a semver string",
        )
    if version < (1, 2, 0):
        return _ContractMode(
            False,
            f"capsule_version {raw_version!r} is back-level for a strict v1.2 UID",
        )
    return _ContractMode(False)


def _finding(mode: _ContractMode, rel: Path, message: str) -> str:
    return f"[{mode.severity}] {rel} — {message}"


def _behavior_shape_findings(
    mode: _ContractMode,
    rel: Path,
    behaviors: object,
) -> list[str]:
    """Report malformed behavior containers before Rule 3 treats them as empty."""

    if not isinstance(behaviors, list):
        return [
            _finding(
                mode,
                rel,
                'behaviors_covered must be a list; malformed value is '
                'evaluated as empty for Rule 3.a/3.b',
            )
        ]
    findings: list[str] = []
    if not behaviors:
        findings.append(
            _finding(mode, rel, 'behaviors_covered is empty (Rule 2 floor)')
        )
    for idx, behavior in enumerate(behaviors):
        if not isinstance(behavior, dict):
            findings.append(
                _finding(
                    mode,
                    rel,
                    f'behaviors_covered[{idx}] must be an object; malformed '
                    'entry contributes no Rule 3.a/3.b coverage',
                )
            )
    return findings


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
        parsed = _yaml_safe_load(raw)
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
def _load_spec_records(vault: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    """Load dev-spec and activation source records for linkage traversal."""

    dev_specs: dict[str, dict] = {}
    activations: dict[str, dict] = {}
    files_dir = vault / 'vault' / 'files'
    if not files_dir.exists():
        return dev_specs, activations
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        if fm is None:
            continue
        uid = fm.get('uid') or f.stem
        if not isinstance(uid, str):
            continue
        if fm.get('type') == 'dev-spec':
            dev_specs[uid] = fm
        elif fm.get('type') == 'activation':
            activations[uid] = fm
    return dev_specs, activations


@lru_cache(maxsize=4)
def _load_target_metadata(
    vault: Path,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Load exact UID/path metadata from current+archive index and source."""

    by_uid: dict[str, dict] = {}
    by_path: dict[str, dict] = {}
    for name in ('00-index.jsonl', '00-archive-index.jsonl'):
        index_path = vault / 'vault' / name
        if not index_path.is_file():
            continue
        try:
            lines = index_path.read_text(encoding='utf-8').splitlines()
        except OSError:
            continue
        for raw in lines:
            try:
                row = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(row, dict):
                continue
            uid = row.get('uid')
            path_value = row.get('path')
            if isinstance(uid, str) and uid not in by_uid:
                by_uid[uid] = dict(row)
            if isinstance(path_value, str) and path_value not in by_path:
                by_path[path_value] = dict(row)

    source_paths = list((vault / 'vault' / 'files').glob('*.md'))
    source_paths.extend((vault / 'vault' / 'capsules').glob('*.md'))
    for source_path in source_paths:
        if source_path.is_symlink():
            continue
        try:
            fm = _parse_frontmatter(source_path.read_text(errors='replace'))
            relative = source_path.relative_to(vault).as_posix()
        except (OSError, ValueError):
            continue
        if fm is None:
            continue
        uid = fm.get('uid')
        prior = by_uid.get(uid, {}) if isinstance(uid, str) else {}
        metadata = {**prior, **fm, 'path': relative}
        if isinstance(uid, str):
            by_uid[uid] = metadata
        by_path[relative] = metadata
    return by_uid, by_path


def _metadata_for_ref(
    ref: spec_substrate_refs.SubstrateRef,
    vault: Path,
) -> dict:
    by_uid, by_path = _load_target_metadata(vault)
    if ref.kind == 'uid':
        return by_uid.get(ref.value, {})
    if ref.kind == 'path':
        return by_path.get(ref.value.rstrip('/'), by_path.get(ref.value, {}))
    return {}


def _metadata_tags(metadata: dict) -> frozenset[str]:
    tags = metadata.get('tags')
    if isinstance(tags, str):
        return frozenset({tags})
    if isinstance(tags, list):
        return frozenset(tag for tag in tags if isinstance(tag, str))
    return frozenset()


def _is_engine_extension_target(
    ref: spec_substrate_refs.SubstrateRef,
    vault: Path,
) -> bool:
    metadata = _metadata_for_ref(ref, vault)
    return (
        metadata.get('type') == 'engine-extension'
        or 'engine-extension' in _metadata_tags(metadata)
    )


def _is_os_tier_target(
    ref: spec_substrate_refs.SubstrateRef,
    vault: Path,
) -> bool:
    if ref.kind == 'path':
        parts = PurePosixPath(ref.value.rstrip('/')).parts
        if len(parts) >= 2 and parts[:2] == ('vault', 'capsules'):
            return True
    metadata = _metadata_for_ref(ref, vault)
    entry_type = metadata.get('type')
    tags = _metadata_tags(metadata)
    return (
        (
            isinstance(entry_type, str)
            and entry_type in {
                'capsule-definition', 'engine-extension', 'os-primitive'
            }
        )
        or metadata.get('tier') == 'os'
        or 'engine-extension' in tags
        or 'os-primitive' in tags
    )


def _conditional_coverage_requirements(
    vault: Path,
    dev_spec: dict | None,
    cycle_class: str,
) -> set[str]:
    """Derive conditional class floors from exact paired-dev declarations."""

    requirements: set[str] = set()
    committed = dev_spec.get('committed_substrate', []) if dev_spec else []
    if not isinstance(committed, list):
        return requirements

    if any(
        isinstance(item, dict)
        and item.get('change_class') in {'AMENDED', 'REFACTORED'}
        for item in committed
    ):
        # The coverage floor is declared by change_class itself.  Identity
        # parsing below is only for metadata-driven gauntlet classification;
        # a malformed target may not erase the regression requirement.
        requirements.add('regression')

    parsed: list[
        tuple[spec_substrate_refs.SubstrateRef, str]
    ] = []
    for item in committed:
        if not isinstance(item, dict):
            continue
        change_class = item.get('change_class')
        if not isinstance(change_class, str):
            continue
        try:
            ref = spec_substrate_refs.parse_substrate_ref(
                item.get('target'), vault
            )
        except spec_substrate_refs.SubstrateRefError:
            continue
        parsed.append((ref, change_class))

    if cycle_class == 'substrate' and any(
        _is_os_tier_target(ref, vault) for ref, _ in parsed
    ):
        requirements.add('gauntlet')
    if cycle_class == 'engine-runtime' and any(
        _is_engine_extension_target(ref, vault) for ref, _ in parsed
    ):
        requirements.add('gauntlet')
    return requirements


def _resolve_triggering_dev_spec(
    vault: Path,
    frontmatter: dict,
) -> tuple[str | None, dict | None, str | None]:
    """Resolve activation→dev_spec_uid, with bounded legacy direct-dev support."""

    mode = _contract_mode(frontmatter, vault)
    declared = frontmatter.get('triggered_by_dev_cycle')
    release_values = {
        field: frontmatter.get(field) for field in RELEASE_PROVENANCE_FIELDS
    }
    if any(release_values.values()):
        if declared:
            return None, None, (
                'test-spec declares both dev-cycle and release trigger provenance'
            )
        missing = [
            field for field, value in release_values.items()
            if not isinstance(value, str)
            or not spec_substrate_refs.UID_RE.fullmatch(value)
        ]
        if missing:
            return None, None, (
                'release-triggered test-spec missing valid provenance fields: '
                + ', '.join(missing)
            )
        return None, None, None
    if not isinstance(declared, str) or not spec_substrate_refs.UID_RE.fullmatch(declared):
        return None, None, (
            f"triggered_by_dev_cycle must be an 8-hex UID, got {declared!r}"
        )

    dev_specs, activations = _load_spec_records(vault)
    if declared in activations:
        dev_uid = activations[declared].get('dev_spec_uid')
        if (
            not isinstance(dev_uid, str)
            or not spec_substrate_refs.UID_RE.fullmatch(dev_uid)
            or dev_uid not in dev_specs
        ):
            return None, None, (
                f"triggered_by_dev_cycle activation {declared} has missing or "
                f"unresolvable dev_spec_uid {dev_uid!r}"
            )
    elif declared in dev_specs:
        if not mode.legacy:
            return None, None, (
                f"triggered_by_dev_cycle {declared} is a direct dev-spec UID; "
                "v1.2+ requires a dev-pipeline activation UID"
            )
        dev_uid = declared
    else:
        return None, None, (
            f"triggered_by_dev_cycle {declared} resolves to neither an activation "
            "nor a compatible legacy dev-spec"
        )

    convenience = frontmatter.get('triggering_dev_spec')
    if convenience is not None and convenience != dev_uid:
        return dev_uid, dev_specs[dev_uid], (
            f"triggering_dev_spec {convenience!r} does not equal resolved "
            f"dev-spec UID {dev_uid}"
        )
    return dev_uid, dev_specs[dev_uid], None


def _dev_declarations(
    vault: Path,
    dev_spec: dict | None,
) -> list[tuple[spec_substrate_refs.SubstrateRef, str]]:
    declarations: list[tuple[spec_substrate_refs.SubstrateRef, str]] = []
    committed = dev_spec.get('committed_substrate', []) if dev_spec else []
    if not isinstance(committed, list):
        return declarations
    for item in committed:
        if not isinstance(item, dict):
            continue
        try:
            ref = spec_substrate_refs.parse_substrate_ref(item.get('target'), vault)
        except spec_substrate_refs.SubstrateRefError:
            continue
        change_class = item.get('change_class')
        if isinstance(change_class, str):
            declarations.append((ref, change_class))
    return declarations


def _ref_resolution_problem(
    ref: spec_substrate_refs.SubstrateRef,
    identities: spec_substrate_refs.IndexIdentities,
    declarations: list[tuple[spec_substrate_refs.SubstrateRef, str]],
) -> tuple[str | None, bool]:
    """Return ``(problem, missing_legal_new_path)`` for a test-side ref."""

    if ref.kind == 'uid' and ref.value not in identities.uids:
        return (
            f"UID {ref.value} does not resolve in the current/archive index",
            False,
        )
    match = spec_substrate_refs.matching_declaration(ref, declarations, identities)
    if ref.kind == 'opaque' and match is None:
        return (
            f"opaque identifier {ref.value!r} is not an exact paired dev-spec declaration",
            False,
        )
    if ref.kind == 'path' and not ref.exists:
        if match is not None and match[1] == 'NEW':
            return None, True
        return (
            f"path {ref.value!r} does not exist and is not an exact NEW declaration",
            False,
        )
    return None, False


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
    required = ('type', 'target_substrate', 'target_subsystem',
                'behaviors_covered', 'coverage_class', 'acceptance_criteria')
    findings: list[str] = []
    total = 0
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        mode = _contract_mode(fm, vault)
        missing = [k for k in required if k not in fm]
        if missing:
            findings.append(f'[WARN] {rel} — test-spec missing required fields: {", ".join(missing)}')
        has_dev = bool(fm.get('triggered_by_dev_cycle'))
        release_values = [fm.get(field) for field in RELEASE_PROVENANCE_FIELDS]
        has_release = all(release_values)
        if has_dev and has_release:
            findings.append(_finding(
                mode, rel,
                'test-spec declares both dev-cycle and release trigger provenance',
            ))
        elif not has_dev and any(release_values) and not has_release:
            missing_release = [
                field for field in RELEASE_PROVENANCE_FIELDS if not fm.get(field)
            ]
            findings.append(_finding(
                mode, rel,
                'release-triggered test-spec missing provenance fields: '
                + ', '.join(missing_release),
            ))
        elif not has_dev and not has_release:
            findings.append(_finding(
                mode, rel,
                'test-spec requires triggered_by_dev_cycle or the complete '
                'release activation/plan/run triplet',
            ))
        if mode.version_error:
            findings.append(f'[ERROR] {rel} — {mode.version_error}')
        # cycle_class was WARN-if-absent at v1.0 and is strict for v1.2+.
        if 'cycle_class' not in fm:
            findings.append(
                _finding(
                    mode,
                    rel,
                    'cycle_class absent (legacy inference fallback; required for v1.2+)',
                )
            )
    return findings, total, len(findings)


# =============================================================================
# 2. check_test_spec_target_substrate_resolvable
# =============================================================================

def check_test_spec_target_substrate_resolvable(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    identities = spec_substrate_refs.load_index_identities(vault)
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        mode = _contract_mode(fm, vault)
        _, dev_spec, _ = _resolve_triggering_dev_spec(vault, fm)
        declarations = _dev_declarations(vault, dev_spec)
        ts = fm.get('target_substrate')
        if not isinstance(ts, list):
            findings.append(
                _finding(mode, rel, 'target_substrate must be a substrate-ref list')
            )
            continue
        if not ts:
            findings.append(_finding(mode, rel, 'target_substrate must be non-empty'))
        for idx, value in enumerate(ts):
            try:
                ref = spec_substrate_refs.parse_substrate_ref(value, vault)
            except spec_substrate_refs.SubstrateRefError as exc:
                findings.append(
                    _finding(
                        mode,
                        rel,
                        f'target_substrate[{idx}] {value!r} is invalid: {exc}',
                    )
                )
                continue
            problem, planned_new = _ref_resolution_problem(
                ref, identities, declarations
            )
            if problem:
                findings.append(
                    _finding(mode, rel, f'target_substrate[{idx}] {problem}')
                )
            elif planned_new:
                findings.append(
                    f'[WARN] {rel} — target_substrate[{idx}] NEW path '
                    f'{ref.value!r} does not exist yet (legal mid-cycle)'
                )
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
        mode = _contract_mode(fm, vault)
        findings.extend(
            _behavior_shape_findings(
                mode, rel, fm.get('behaviors_covered')
            )
        )
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
                continue
            vm = entry.get('verification_method')
            if not vm:
                findings.append(f'[WARN] {rel} — behaviors_covered[{idx}] missing verification_method')
                continue
            if (
                not isinstance(vm, str)
                or vm not in VALID_VERIFICATION_METHODS
            ):
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
    """Enforce Rule 3.a substrate identity and Rule 3.b AC coverage together."""

    findings: list[str] = []
    total = 0
    identities = spec_substrate_refs.load_index_identities(vault)
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        mode = _contract_mode(fm, vault)
        raw_behaviors = fm.get('behaviors_covered')
        findings.extend(_behavior_shape_findings(mode, rel, raw_behaviors))
        behaviors = raw_behaviors if isinstance(raw_behaviors, list) else []
        dev_uid, dev_spec, link_error = _resolve_triggering_dev_spec(vault, fm)
        if dev_spec is None or link_error:
            # Check 9 owns linkage findings. Pairing cannot be evaluated without
            # an unambiguous paired dev-spec.
            continue

        declarations = _dev_declarations(vault, dev_spec)
        committed = dev_spec.get('committed_substrate', [])
        if isinstance(committed, list):
            for committed_idx, committed_item in enumerate(committed):
                if not isinstance(committed_item, dict):
                    continue
                raw_target = committed_item.get('target')
                try:
                    spec_substrate_refs.parse_substrate_ref(raw_target, vault)
                except spec_substrate_refs.SubstrateRefError as exc:
                    change_class = committed_item.get('change_class')
                    rule_suffix = (
                        ' and cannot satisfy Rule 3.a'
                        if change_class == 'NEW'
                        else ''
                    )
                    findings.append(
                        _finding(
                            mode,
                            rel,
                            f'dev-spec {dev_uid} {change_class or "<missing>"} '
                            f'target at '
                            f'committed_substrate[{committed_idx}] '
                            f'{raw_target!r} is an invalid substrate-ref'
                            f'{rule_suffix}: {exc}',
                        )
                    )
        new_declarations = [
            declaration for declaration in declarations if declaration[1] == 'NEW'
        ]

        behavior_refs: list[spec_substrate_refs.SubstrateRef] = []
        covered_acs: set[int | str] = set()
        dev_acs = dev_spec.get('acceptance_criteria')
        stable_ac_ids = dev_spec_validators.is_v18_dev_spec(dev_spec)
        if stable_ac_ids and isinstance(dev_acs, list):
            acceptance_criteria: list[int | str] = [
                criterion.get("id")
                for criterion in dev_acs
                if isinstance(criterion, dict)
                and isinstance(criterion.get("id"), str)
                and dev_spec_validators.AC_ID_RE.fullmatch(criterion["id"])
            ]
        elif isinstance(dev_acs, list):
            acceptance_criteria = list(range(1, len(dev_acs) + 1))
        elif dev_acs and not stable_ac_ids:
            acceptance_criteria = [1]
        else:
            acceptance_criteria = []

        for behavior_idx, behavior in enumerate(behaviors):
            if not isinstance(behavior, dict):
                continue
            raw_refs = behavior.get('target_substrate_refs')
            if not isinstance(raw_refs, list):
                findings.append(
                    _finding(
                        mode,
                        rel,
                        f'behaviors_covered[{behavior_idx}].target_substrate_refs '
                        'must be a substrate-ref list',
                    )
                )
                raw_refs = []
            for ref_idx, raw_ref in enumerate(raw_refs):
                try:
                    parsed_ref = spec_substrate_refs.parse_substrate_ref(
                        raw_ref, vault
                    )
                except spec_substrate_refs.SubstrateRefError as exc:
                    findings.append(
                        _finding(
                            mode,
                            rel,
                            f'behaviors_covered[{behavior_idx}].'
                            f'target_substrate_refs[{ref_idx}] {raw_ref!r} '
                            f'is invalid: {exc}',
                        )
                    )
                    continue
                problem, _ = _ref_resolution_problem(
                    parsed_ref, identities, declarations
                )
                if problem:
                    findings.append(
                        _finding(
                            mode,
                            rel,
                            f'behaviors_covered[{behavior_idx}].'
                            f'target_substrate_refs[{ref_idx}] {problem}',
                        )
                    )
                    continue
                behavior_refs.append(parsed_ref)

            pointer = behavior.get('verifies_acceptance_criterion')
            if pointer is None:
                continue  # optional per behavior; completeness is aggregate
            if stable_ac_ids:
                if (
                    not isinstance(pointer, str)
                    or not dev_spec_validators.AC_ID_RE.fullmatch(pointer)
                ):
                    findings.append(
                        _finding(
                            mode,
                            rel,
                            f'behaviors_covered[{behavior_idx}].'
                            f'verifies_acceptance_criterion {pointer!r} must be a '
                            'stable AC ID string such as AC1',
                        )
                    )
                    continue
                if pointer not in acceptance_criteria:
                    findings.append(
                        _finding(
                            mode,
                            rel,
                            f'behaviors_covered[{behavior_idx}] verifies '
                            f'{pointer}, but dev-spec {dev_uid} does not declare '
                            'that acceptance ID',
                        )
                    )
                    continue
                covered_acs.add(pointer)
                continue
            if mode.legacy and isinstance(pointer, list):
                pointers = pointer
            elif isinstance(pointer, int) and not isinstance(pointer, bool):
                pointers = [pointer]
            else:
                findings.append(
                    _finding(
                        mode,
                        rel,
                        f'behaviors_covered[{behavior_idx}].'
                        f'verifies_acceptance_criterion {pointer!r} must be a '
                        '1-based integer',
                    )
                )
                continue
            for pointer_value in pointers:
                if (
                    not isinstance(pointer_value, int)
                    or isinstance(pointer_value, bool)
                ):
                    findings.append(
                        _finding(
                            mode,
                            rel,
                            f'behaviors_covered[{behavior_idx}].'
                            f'verifies_acceptance_criterion {pointer_value!r} '
                            'must be an integer',
                        )
                    )
                elif pointer_value not in acceptance_criteria:
                    findings.append(
                        _finding(
                            mode,
                            rel,
                            f'behaviors_covered[{behavior_idx}] verifies AC '
                            f'#{pointer_value}, but dev-spec {dev_uid} has '
                            f'{len(acceptance_criteria)} acceptance criteria',
                        )
                    )
                else:
                    covered_acs.add(pointer_value)

        for new_ref, _ in new_declarations:
            if not any(
                spec_substrate_refs.refs_match(new_ref, behavior_ref, identities)
                for behavior_ref in behavior_refs
            ):
                findings.append(
                    _finding(
                        mode,
                        rel,
                        f'dev-spec {dev_uid} NEW target {new_ref.value!r} has '
                        'no exact behaviors_covered.target_substrate_refs match '
                        '(Rule 3.a; no structural exemption)',
                    )
                )

        for acceptance_id in acceptance_criteria:
            if acceptance_id not in covered_acs:
                label = (
                    acceptance_id
                    if stable_ac_ids
                    else f"#{acceptance_id}"
                )
                findings.append(
                    _finding(
                        mode,
                        rel,
                        f'dev-spec {dev_uid} acceptance criterion {label} '
                        'has no covering behavior (Rule 3.b)',
                    )
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
        coverage = fm.get('coverage_class')
        coverage_set = {coverage} if isinstance(coverage, str) else set(
            item for item in coverage if isinstance(item, str)
        ) if isinstance(coverage, list) else set()
        default_ceiling = (
            100 if 'cold-boot' in coverage_set else DEFAULT_MANUAL_WALK_CEILING
        )
        ceiling = fm.get('manual_walk_ceiling_override') or fm.get(
            'manual_walk_percentage_ceiling', default_ceiling
        )
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
    """Normalize scalar/list coverage and enforce the locked cycle-class floors."""
    findings: list[str] = []
    total = 0

    floor: dict[str, set[str]] = {
        'substrate': {'smoke'},
        'ux': {'smoke', 'cold-boot'},
        'engine-runtime': {'smoke', 'property'},
    }

    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        mode = _contract_mode(fm, vault)
        cycle_class = fm.get('cycle_class')
        if cycle_class is None:
            continue  # Check 1 emits the cohort-appropriate finding.
        if (
            not isinstance(cycle_class, str)
            or cycle_class not in VALID_CYCLE_CLASSES
        ):
            findings.append(
                _finding(
                    mode,
                    rel,
                    f'cycle_class {cycle_class!r} not in '
                    f'{sorted(VALID_CYCLE_CLASSES)}',
                )
            )
            continue
        _, dev_spec, linkage_problem = _resolve_triggering_dev_spec(vault, fm)

        coverage = fm.get('coverage_class')
        if isinstance(coverage, str):
            raw_classes = [coverage]
        elif isinstance(coverage, list):
            raw_classes = coverage
            if not raw_classes:
                findings.append(
                    _finding(mode, rel, 'coverage_class list must be non-empty')
                )
        else:
            raw_classes = []
            findings.append(
                _finding(
                    mode,
                    rel,
                    'coverage_class must be an enum string or non-empty unique list',
                )
            )

        coverage_set: set[str] = set()
        for idx, coverage_class in enumerate(raw_classes):
            if not isinstance(coverage_class, str):
                findings.append(
                    _finding(
                        mode,
                        rel,
                        f'coverage_class[{idx}] must be a string, got '
                        f'{type(coverage_class).__name__}',
                    )
                )
                continue
            if coverage_class in coverage_set:
                findings.append(
                    _finding(
                        mode,
                        rel,
                        f'coverage_class contains duplicate {coverage_class!r}',
                    )
                )
                continue
            coverage_set.add(coverage_class)
            if coverage_class not in VALID_COVERAGE_CLASSES:
                findings.append(
                    _finding(
                        mode,
                        rel,
                        f'coverage_class value {coverage_class!r} not in '
                        f'{sorted(VALID_COVERAGE_CLASSES)}',
                    )
                )

        required = floor[cycle_class] | (
            _conditional_coverage_requirements(vault, dev_spec, cycle_class)
            if linkage_problem is None
            else set()
        )
        missing = required - coverage_set
        if missing:
            findings.append(
                _finding(
                    mode,
                    rel,
                    f'cycle_class={cycle_class} requires coverage_class minima '
                    f'{sorted(required)} (missing: {sorted(missing)})',
                )
            )
        if cycle_class == 'substrate':
            behaviors = fm.get('behaviors_covered')
            has_structural = isinstance(behaviors, list) and any(
                isinstance(behavior, dict)
                and behavior.get('verification_method') == 'structural_check'
                for behavior in behaviors
            )
            if not has_structural:
                findings.append(
                    _finding(
                        mode,
                        rel,
                        'cycle_class=substrate requires at least one '
                        'structural_check behavior',
                    )
                )
    return findings, total, len(findings)


# =============================================================================
# 9. check_test_spec_triggered_by_dev_cycle_resolvable
# =============================================================================

def check_test_spec_triggered_by_dev_cycle_resolvable(vault: Path) -> tuple[list[str], int, int]:
    findings: list[str] = []
    total = 0
    for path, fm in _iter_test_specs(vault):
        total += 1
        rel = path.relative_to(vault)
        mode = _contract_mode(fm, vault)
        _, _, problem = _resolve_triggering_dev_spec(vault, fm)
        if problem:
            findings.append(_finding(mode, rel, problem))
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


def run_all_test_spec_checks(
    vault: Path,
    *,
    include_pairing: bool = True,
    include_behavior_floor: bool = True,
) -> tuple[list[str], int, int]:
    all_findings: list[str] = []
    total = 0
    total_defects = 0
    for name, check_fn in TEST_SPEC_CHECKS:
        if name == 'check_test_spec_behaviors_covered_non_empty':
            if include_pairing or not include_behavior_floor:
                # The Rule 3 evaluator owns the same shape finding whenever it
                # runs; avoid duplicate full/check-one substance.
                continue
        if not include_pairing and name == 'check_test_spec_cross_validation_against_dev_spec':
            continue
        findings, checked, defects = check_fn(vault)
        all_findings.extend(findings)
        total = max(total, checked)
        total_defects += defects
    return all_findings, total, total_defects
