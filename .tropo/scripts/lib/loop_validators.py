"""loop.capsule v1.2 validator extensions for tropo-validate.py.

Authored by Talos T20 2026-06-16 per:
- loop.capsule v1.2 LOCKED §7 Validation Checks (UID 1248583d; LOCKED by Mike-A114 2026-06-14)
- dev-spec 9da979b2 v0.6 §Accepted Criteria #2

Matches existing `lib/doc_spec_validators.py` DRY pattern.
Wired into tropo-validate.py main() at v1.71 build-delta; 7 checks for type:loop.
Legacy artifacts (pre-v1.71) are grandfathered (checks only run when type:loop present).

Returns per check function: (findings, total_checked, defects)
"""

from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import yaml
import json

TARGETS_CAPSULE = "loop"

# Re-use helper from doc_spec_validators (can't easily import without system path mess)
def _parse_frontmatter(f: Path) -> dict | None:
    try:
        text = f.read_text(errors='replace')
        if not text.startswith('---'): return None
        end = text.find('\n---\n', 4)
        if end == -1: return None
        return yaml.safe_load(text[4:end])
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
            findings.append(f'[WARN] {rel} — loop missing required fields: {", ".join(missing)}')
    return findings, total, len(findings)

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
            findings.append(f'[ERROR] {rel} — loop missing brakes object (Check 3)')
            continue
            
        has_iter_brake = 'max_iterations' in brakes or 'human_checkpoint_every' in brakes
        has_hard_floor = 'max_budget_usd' in brakes or 'max_wall_clock_min' in brakes
        
        if not has_iter_brake:
            findings.append(f'[ERROR] {rel} — brakes missing iteration limit (max_iterations or human_checkpoint_every)')
        if not has_hard_floor:
            findings.append(f'[ERROR] {rel} — brakes missing hard floor (max_budget_usd or max_wall_clock_min)')
            
    return findings, total, len(findings)

# =============================================================================
# 4. check_loop_goal_independent
# =============================================================================
def check_loop_goal_independent(vault: Path) -> tuple[list[str], int, int]:
    findings = []
    total = 0
    for path, fm in _iter_loops(vault):
        total += 1
        rel = path.relative_to(vault)
        goal = fm.get('goal', {})
        policy = fm.get('policy', {})
        authored_by = goal.get('authored_by')
        executor = policy.get('ref')
        
        if not authored_by:
            findings.append(f'[ERROR] {rel} — goal missing authored_by')
        elif authored_by == executor:
            findings.append(f'[ERROR] {rel} — goal.authored_by MUST not be the executor {executor}')
            
    return findings, total, len(findings)

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
        
        if not verifier.get('independent'):
            findings.append(f'[ERROR] {rel} — verifier.independent must be true')
            
        v_kind = verifier.get('kind')
        p_kind = policy.get('kind')
        v_ref = verifier.get('ref')
        p_ref = policy.get('ref')
        
        if v_kind == p_kind and (v_ref == p_ref or not v_ref):
             findings.append(f'[ERROR] {rel} — verifier must be distinct from policy agent')
             
    return findings, total, len(findings)

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

def check_loop_consequence_scope(vault: Path) -> tuple[list[str], int, int]:
    findings = []
    total = 0
    tools_db = _load_tools(vault)
    
    for path, fm in _iter_loops(vault):
        total += 1
        rel = path.relative_to(vault)
        consequence = fm.get('consequence')
        
        if consequence not in ('low', 'medium', 'high', 'critical'):
            findings.append(f'[ERROR] {rel} — consequence must be low, medium, high, or critical')
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
                findings.append(f'[ERROR] {rel} — consequence: low but tools include write-scope (tool {violating_tool})')
                
    return findings, total, len(findings)

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
            
    return findings, total, len(findings)

LOOP_CHECKS = (
    ('check_loop_basic_fields', check_loop_basic_fields),
    ('check_loop_has_brakes', check_loop_has_brakes),
    ('check_loop_goal_independent', check_loop_goal_independent),
    ('check_loop_verifier_independent', check_loop_verifier_independent),
    ('check_loop_consequence_scope', check_loop_consequence_scope),
    ('check_loop_run_contract_locked', check_loop_run_contract_locked),
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
