"""loop.capsule validator extensions shared by full validation and check-one.

Authored by Talos T20 2026-06-16 per:
- loop.capsule v1.2 LOCKED §7 Validation Checks (UID 1248583d; LOCKED by Mike-A114 2026-06-14)
- dev-spec 9da979b2 v0.6 §Accepted Criteria #2

Matches existing `lib/doc_spec_validators.py` DRY pattern.
Wired into tropo-validate.py main() at v1.71 build-delta; extended at v1.4
for strict governed birth, Gardener policy uniqueness, and maintenance consent.
Legacy artifacts (pre-v1.71) are grandfathered (checks only run when type:loop present).

Returns per check function: (findings, total_checked, defects)
"""

from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import math
import numbers
import re
import yaml
import json

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


TARGETS_CAPSULE = "loop"
UID_RE = re.compile(r"^[0-9a-f]{8}$")
SA_RUNNER_RE = re.compile(r"^sa\.[a-z0-9][a-z0-9.-]*$")
GARDENER_POLICY_RUNNER = "gardener-body-judge"
FROZEN_LEGACY_LOOP_UIDS = frozenset({
    "03f9a721",
    "be2296f9",
    "c3b9e1a5",
    "d1a4f8e2",
    "f2a7d3c8",
    "f8a2c91d",
})


def _contract_severity(fm: dict) -> str:
    """Strict v1.5 entries ERROR; the immutable cutover cohort remains WARN."""
    return "WARN" if fm.get("uid") in FROZEN_LEGACY_LOOP_UIDS else "ERROR"


def _contract_finding(fm: dict, rel: Path, message: str) -> str:
    return f"[{_contract_severity(fm)}] {rel} — {message}"


def _defect_count(findings: list[str]) -> int:
    return sum(
        "[ERROR]" in finding or "[FAIL]" in finding
        for finding in findings
    )

# Re-use helper from doc_spec_validators (can't easily import without system path mess)
def _parse_frontmatter(f: Path) -> dict | None:
    try:
        text = f.read_text(errors='replace')
        if text.startswith('---\n'):
            start = 4
        else:
            opening = text.find('\n---\n')
            if opening == -1:
                return None
            start = opening + len('\n---\n')
        end = text.find('\n---\n', start)
        if end == -1: return None
        value = _yaml_safe_load(text[start:end])
        return value if isinstance(value, dict) else None
    except Exception:
        return None

@lru_cache(maxsize=1)
def _load_loops(vault: Path) -> tuple:
    out = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.exists(): return tuple()
    for f in files_dir.glob('*.md'):
        fm = _parse_frontmatter(f)
        if fm and fm.get('type') == 'loop':
            out.append((f, fm))
    return tuple(out)

def _iter_loops(vault: Path):
    yield from _load_loops(vault)


def _load_index_records(vault: Path, *, include_archive: bool = False) -> list[dict]:
    """Load exact object rows, with current authority winning archive duplicates."""
    paths = [vault / 'vault' / '00-index.jsonl']
    if include_archive:
        paths.append(vault / 'vault' / '00-archive-index.jsonl')
    records: list[dict] = []
    seen: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding='utf-8', errors='strict').splitlines()
        except (OSError, UnicodeError):
            continue
        for raw in lines:
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(record, dict):
                continue
            uid = record.get('uid')
            if isinstance(uid, str) and uid in seen:
                continue
            if isinstance(uid, str):
                seen.add(uid)
            records.append(record)
    return records

@lru_cache(maxsize=1)
def _load_loop_runs(vault: Path) -> tuple:
    out = []
    runs_dir = vault / 'vault' / 'loop-runs'
    if not runs_dir.exists(): return tuple()
    for d in runs_dir.glob('*'):
        if not d.is_dir(): continue
        run_file = d / 'definition.md'
        if run_file.exists():
            fm = _parse_frontmatter(run_file)
            if fm and fm.get('type') == 'loop-run':
                out.append((d, run_file, fm))
    return tuple(out)

def _iter_loop_runs(vault: Path):
    yield from _load_loop_runs(vault)

# =============================================================================
# 1. check_loop_basic_fields
# =============================================================================
def check_loop_basic_fields(vault: Path) -> tuple[list[str], int, int]:
    required = ('uid', 'name', 'version', 'author', 'state', 'status')
    findings = []
    total = 0
    for path, fm in _iter_loops(vault):
        total += 1
        rel = path.relative_to(vault)
        missing = [k for k in required if k not in fm]
        if missing:
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    f'loop missing required fields: {", ".join(missing)}',
                )
            )
    return findings, total, _defect_count(findings)


# =============================================================================
# 2. check_loop_author_resolvable
# =============================================================================
def check_loop_author_resolvable(vault: Path) -> tuple[list[str], int, int]:
    """The immutable author is an entity UID, not an agent-generation slug."""
    findings = []
    total = 0
    records = _load_index_records(vault, include_archive=True)
    for path, fm in _iter_loops(vault):
        total += 1
        rel = path.relative_to(vault)
        author = fm.get('author')
        if not isinstance(author, str) or not UID_RE.fullmatch(author):
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    'loop author must be an 8-hex resolvable UID',
                )
            )
            continue
        matches = [row for row in records if row.get('uid') == author]
        if len(matches) != 1:
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    f'loop author {author} must resolve exactly once '
                    f'in the current/archive index (found {len(matches)})',
                )
            )
    return findings, total, _defect_count(findings)

# =============================================================================
# 3. check_loop_has_brakes
# =============================================================================
def check_loop_has_brakes(vault: Path) -> tuple[list[str], int, int]:
    findings = []
    total = 0
    for path, fm in _iter_loops(vault):
        total += 1
        rel = path.relative_to(vault)
        brakes = fm.get('brakes')
        if not brakes or not isinstance(brakes, dict):
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    'loop missing brakes object (Check 3)',
                )
            )
            continue
            
        numeric_fields = (
            'max_iterations',
            'human_checkpoint_every',
            'max_budget_usd',
            'max_wall_clock_min',
            'tool_timeout_sec',
        )
        for field in numeric_fields:
            if field not in brakes:
                continue
            value = brakes[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, numbers.Real)
                or not math.isfinite(float(value))
                or value < 0
            ):
                findings.append(
                    _contract_finding(
                        fm,
                        rel,
                        f'brakes.{field} must be a finite nonnegative number',
                    )
                )

        has_iter_brake = (
            'max_iterations' in brakes
            or 'human_checkpoint_every' in brakes
        )
        has_hard_floor = (
            'max_budget_usd' in brakes
            or 'max_wall_clock_min' in brakes
        )
        
        if not has_iter_brake:
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    'brakes missing iteration limit '
                    '(max_iterations or human_checkpoint_every)',
                )
            )
        if not has_hard_floor:
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    'brakes missing hard floor '
                    '(max_budget_usd or max_wall_clock_min)',
                )
            )
            
    return findings, total, _defect_count(findings)

# =============================================================================
# 4. check_loop_goal_independent
# =============================================================================
def check_loop_goal_independent(vault: Path) -> tuple[list[str], int, int]:
    findings = []
    total = 0
    current_records = _load_index_records(vault)
    for path, fm in _iter_loops(vault):
        total += 1
        rel = path.relative_to(vault)
        goal = fm.get('goal', {})
        policy = fm.get('policy', {})
        if not isinstance(goal, dict):
            findings.append(_contract_finding(fm, rel, 'goal must be an object'))
            continue
        if not isinstance(policy, dict):
            policy = {}
        authored_by = goal.get('authored_by')
        executor = policy.get('ref')
        
        if not authored_by:
            findings.append(_contract_finding(fm, rel, 'goal missing authored_by'))
        elif authored_by == executor:
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    f'goal.authored_by MUST not be the executor {executor}',
                )
            )

        matches = [
            row for row in current_records
            if row.get('uid') == authored_by
        ]
        principal = matches[0] if len(matches) == 1 else None
        active_principal = (
            principal is not None
            and principal.get('type') == 'principal'
            and principal.get('status') == 'active'
            and principal.get('state') == 'active'
        )
        high_consequence = fm.get('consequence') in ('high', 'critical')
        if authored_by and high_consequence and (
            not active_principal
            or principal.get('principal_class') != 'human'
        ):
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    f'high/critical goal.authored_by {authored_by!r} must '
                    'resolve to one current active human principal',
                )
            )
        elif authored_by and not active_principal:
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    f'goal.authored_by {authored_by!r} must resolve to one '
                    'current active principal',
                )
            )
            
    return findings, total, _defect_count(findings)

# =============================================================================
# 5. check_loop_verifier_independent
# =============================================================================
def check_loop_verifier_independent(vault: Path) -> tuple[list[str], int, int]:
    findings = []
    total = 0
    for path, fm in _iter_loops(vault):
        total += 1
        rel = path.relative_to(vault)
        verifier = fm.get('verifier', {})
        policy = fm.get('policy', {})
        if not isinstance(verifier, dict):
            findings.append(
                _contract_finding(fm, rel, 'verifier must be an object')
            )
            continue
        if not isinstance(policy, dict):
            policy = {}
        
        if verifier.get('independent') is not True:
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    'verifier.independent must be true',
                )
            )
        lenses = verifier.get('lenses')
        if (
            isinstance(lenses, bool)
            or not isinstance(lenses, int)
            or lenses < 2
        ):
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    'verifier.lenses must be an integer >= 2',
                )
            )
            
        v_kind = verifier.get('kind')
        p_kind = policy.get('kind')
        v_ref = verifier.get('ref')
        p_ref = policy.get('ref')
        
        if (
            (v_ref is not None and p_ref is not None and v_ref == p_ref)
            or (v_kind is not None and v_kind == p_kind)
        ):
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    'verifier must be identity-distinct from policy',
                )
            )
             
    return findings, total, _defect_count(findings)

# =============================================================================
# 6. check_loop_consequence_scope
# =============================================================================
@lru_cache(maxsize=1)
def _load_tools(vault: Path) -> dict[str, dict]:
    tools = {}
    tools_dir = vault / 'vault' / 'tools'
    if not tools_dir.exists(): return tools
    for f in tools_dir.glob('*.py'):
        fm = _parse_frontmatter(f)
        if fm and fm.get('type') == 'tool':
            tools[fm.get('uid', f.stem)] = fm
    for f in tools_dir.glob('*.json'):
        fm = _parse_frontmatter(f)
        if fm and fm.get('type') == 'tool':
            tools[fm.get('uid', f.stem)] = fm
    for f in tools_dir.glob('*.md'):
        fm = _parse_frontmatter(f)
        if fm and fm.get('type') == 'tool':
            tools[fm.get('uid', f.stem)] = fm
    return tools


def _registered_tool_runner_error(
    vault: Path,
    fm: dict,
    runner: str,
) -> str | None:
    """Return why a cadence runner is not the loop's bound active tool."""
    policy = fm.get('policy')
    if not isinstance(policy, dict) or policy.get('kind') != 'agentic-tool':
        return 'non-sa runner requires policy.kind agentic-tool'
    tool_uid = policy.get('ref')
    if not isinstance(tool_uid, str) or not UID_RE.fullmatch(tool_uid):
        return 'non-sa runner requires an 8-hex policy.ref tool UID'
    tools = fm.get('tools')
    if not isinstance(tools, list) or tool_uid not in tools:
        return 'non-sa runner policy.ref must be present in tools'
    matches = [
        row for row in _load_index_records(vault)
        if (
            row.get('uid') == tool_uid
            and row.get('type') == 'tool'
            and row.get('status') == 'active'
            and row.get('state') == 'active'
        )
    ]
    if len(matches) != 1:
        return (
            f'non-sa runner policy.ref {tool_uid} must resolve to exactly one '
            f'current active tool (found {len(matches)})'
        )
    tool = _load_tools(vault).get(tool_uid)
    if tool is None:
        return f'non-sa runner policy.ref {tool_uid} has no registered tool source'
    if tool.get('name') != runner:
        return (
            f'non-sa runner {runner!r} must equal registered tool name '
            f'{tool.get("name")!r}'
        )
    return None


def check_loop_consequence_scope(vault: Path) -> tuple[list[str], int, int]:
    findings = []
    total = 0
    tools_db = _load_tools(vault)
    
    for path, fm in _iter_loops(vault):
        total += 1
        rel = path.relative_to(vault)
        consequence = fm.get('consequence')
        
        if consequence not in ('low', 'medium', 'high', 'critical'):
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    'consequence must be low, medium, high, or critical',
                )
            )
            continue
            
        if consequence == 'low':
            tools_used = fm.get('tools', [])
            if not isinstance(tools_used, list): continue
            
            has_write_scope = False
            violating_tool = None
            for t_uid in tools_used:
                t_uid_str = str(t_uid)
                tool_fm = tools_db.get(t_uid_str)
                if tool_fm:
                    ws = tool_fm.get('write_scope', [])
                    if ws and len(ws) > 0:
                        has_write_scope = True
                        violating_tool = t_uid_str
                        break
            
            if has_write_scope:
                findings.append(
                    _contract_finding(
                        fm,
                        rel,
                        f'consequence: low but tools include write-scope '
                        f'(tool {violating_tool})',
                    )
                )
                
    return findings, total, _defect_count(findings)

# =============================================================================
# LOOP-RUN Checks
# =============================================================================

def check_loop_run_contract_locked(vault: Path) -> tuple[list[str], int, int]:
    findings = []
    total = 0
    for run_dir, definition, fm in _iter_loop_runs(vault):
        total += 1
        run_jsonl = run_dir / 'run.jsonl'
        if not run_jsonl.exists():
            findings.append(f'[ERROR] {run_dir.name} — loop-run missing run.jsonl')
            continue
            
        try:
            with open(run_jsonl, 'r') as f:
                lines = f.readlines()
                if len(lines) < 2:
                    findings.append(f'[ERROR] {run_dir.name} — run.jsonl too short; missing locked contract')
                    continue
                
                # Second event MUST be loop_contract_locked
                ev = json.loads(lines[1])
                if ev.get('event') != 'loop_contract_locked':
                    findings.append(f'[ERROR] {run_dir.name} — 2nd event is {ev.get("event")}, expected loop_contract_locked')
                else:
                    b = ev.get('brakes', {})
                    if not b:
                        findings.append(f'[ERROR] {run_dir.name} — loop_contract_locked missing brakes')
        except Exception as e:
            findings.append(f'[ERROR] {run_dir.name} — failed to parse run.jsonl: {e}')
            
    return findings, total, _defect_count(findings)

# =============================================================================
# 7. check_loop_consent_mode (v1.79 S7)
# =============================================================================
VALID_CONSENT_MODES = ('ask', 'auto', 'disabled')

def check_loop_consent_mode(vault: Path) -> tuple[list[str], int, int]:
    """v1.79 S7 — Registry fields apply only when cadence is declared.

    Non-maintenance loops do not need consent_mode/runner.  Registry-dispatched
    loops must declare both; disabled is a valid explicit no-dispatch posture.
    """
    findings = []
    total = 0
    for path, fm in _iter_loops(vault):
        total += 1
        rel = path.relative_to(vault)
        if 'cadence' not in fm:
            continue
        cadence = fm.get('cadence')
        consent_mode = fm.get('consent_mode')
        runner = fm.get('runner')

        if not isinstance(cadence, str) or not cadence.strip():
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    'declared cadence must be a non-empty string',
                )
            )
        if consent_mode not in VALID_CONSENT_MODES:
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    f'consent_mode {consent_mode!r} not in '
                    f'{VALID_CONSENT_MODES} (v1.79 S7 consent_mode enum)',
                )
            )
        tool_runner_error = (
            _registered_tool_runner_error(vault, fm, runner)
            if isinstance(runner, str)
            and runner != 'boot-inline'
            and not SA_RUNNER_RE.fullmatch(runner)
            else None
        )
        if not isinstance(runner, str) or not (
            runner == 'boot-inline'
            or SA_RUNNER_RE.fullmatch(runner)
            or tool_runner_error is None
        ):
            findings.append(
                _contract_finding(
                    fm,
                    rel,
                    'cadence runner must be boot-inline, an sa.<slug>, or the '
                    'registered active agentic-tool bound by policy.ref/tools'
                    + (
                        f'; {tool_runner_error}'
                        if tool_runner_error is not None
                        else ''
                    ),
                )
            )

    return findings, total, _defect_count(findings)


# =============================================================================
# 8. check_gardener_policy_uniqueness
# =============================================================================
def check_gardener_policy_uniqueness(
    vault: Path,
) -> tuple[list[str], int, int]:
    """Exactly one current active policy; archived authority never counts."""
    candidates: list[dict] = []
    for fm in _load_index_records(vault):
        if (
            fm.get('type') == 'loop'
            and fm.get('status') == 'active'
            and fm.get('state') == 'active'
            and fm.get('runner') == GARDENER_POLICY_RUNNER
        ):
            candidates.append(fm)
    if not candidates:
        return (
            [
                '[WARN] <global> — no active gardener-body-judge loop; '
                'production pruning stamps remain fail-closed'
            ],
            0,
            0,
        )
    if len(candidates) == 1:
        return [], 1, 0
    uids = sorted(str(fm.get('uid', '<missing-uid>')) for fm in candidates)
    return (
        [
            f'[ERROR] active gardener-body-judge policy UIDs '
            f'{", ".join(uids)} are ambiguous; exactly one is allowed'
        ],
        len(candidates),
        1,
    )


LOOP_CHECKS = (
    ('check_loop_basic_fields', check_loop_basic_fields),
    ('check_loop_author_resolvable', check_loop_author_resolvable),
    ('check_loop_has_brakes', check_loop_has_brakes),
    ('check_loop_goal_independent', check_loop_goal_independent),
    ('check_loop_verifier_independent', check_loop_verifier_independent),
    ('check_loop_consequence_scope', check_loop_consequence_scope),
    ('check_loop_run_contract_locked', check_loop_run_contract_locked),
    ('check_loop_consent_mode', check_loop_consent_mode),
    ('check_gardener_policy_uniqueness', check_gardener_policy_uniqueness),
)

def run_all_loop_checks(vault: Path) -> tuple[list[str], int, int]:
    all_findings = []
    total = 0
    total_defects = 0
    for _, fn in LOOP_CHECKS:
        f, t, d = fn(vault)
        all_findings.extend(f)
        total = max(total, t)
        total_defects += d
    return all_findings, total, total_defects
