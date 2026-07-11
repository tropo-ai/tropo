"""Git Beat 1 — local history-of-record helpers (dev-spec 98b9610a).

Per-vault git commits: activation-close, boot-reconcile, vault-maintenance backstop.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_VAULT_ROOT = Path(__file__).resolve().parents[3]


def repo_root() -> Path:
    return _VAULT_ROOT


def set_repo_root(path: Path) -> None:
    """Test hook — repoint studio root."""
    global _VAULT_ROOT
    _VAULT_ROOT = path


def flags_dir() -> Path:
    return repo_root() / '.tropo' / 'flags'


def is_git_repo(root: Path | None = None) -> bool:
    root = root or repo_root()
    try:
        r = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            cwd=root, capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def porcelain(root: Path | None = None) -> str:
    root = root or repo_root()
    if not is_git_repo(root):
        return ''
    try:
        r = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return r.stderr or r.stdout or 'git status failed'
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return str(exc)


def is_clean(root: Path | None = None) -> bool:
    return porcelain(root).strip() == ''


def staged_names(root: Path | None = None) -> list[str]:
    root = root or repo_root()
    try:
        r = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return []
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _git_run(args: list[str], root: Path | None = None) -> tuple[int, str, str]:
    root = root or repo_root()
    r = subprocess.run(
        ['git', *args],
        cwd=root, capture_output=True, text=True, timeout=120,
    )
    return r.returncode, r.stdout, r.stderr


def stage_all(root: Path | None = None) -> tuple[bool, str]:
    code, out, err = _git_run(['add', '-A'], root)
    if code != 0:
        return False, err or out or 'git add failed'
    return True, ''


def commit_message_close(
    fm: dict,
    activation_uid: str,
    target_status: str,
    closure_reason: str = '',
    transfer_uid: str = '',
    closer: str = '',
) -> str:
    agent = fm.get('agent', 'unknown')
    generation = fm.get('generation', '?')
    closer = closer or f"{agent}-{str(generation).lower()}"
    lines = [
        f"tropo: close activation {agent} {generation} ({activation_uid}) → {target_status}",
        '',
        f'agent: {agent}',
        f'generation: {generation}',
        f'activation: {activation_uid}',
        f'status: {target_status}',
        f'closer: {closer}',
    ]
    if closure_reason:
        lines.append(f'closure_reason: {closure_reason}')
    if transfer_uid:
        lines.append(f'transfer_uid: {transfer_uid}')
    names = staged_names()
    if names:
        lines.append('files:')
        lines.extend(f'  - {n}' for n in names[:200])
        if len(names) > 200:
            lines.append(f'  … and {len(names) - 200} more')
    return '\n'.join(lines)


def commit_message_reconcile(prior_fm: dict | None, boot_agent: str, boot_generation: str) -> str:
    if prior_fm:
        agent = prior_fm.get('agent', 'unknown')
        generation = prior_fm.get('generation', '?')
        activation = prior_fm.get('uid') or prior_fm.get('activation_uid') or 'unknown'
        lines = [
            f'tropo: boot-reconcile orphaned drift → prior activation {agent} {generation} ({activation})',
            '',
            'trigger: boot-reconcile',
            f'prior_agent: {agent}',
            f'prior_generation: {generation}',
            f'prior_activation: {activation}',
            f'booting_agent: {boot_agent}',
            f'booting_generation: {boot_generation}',
            'reconcile: true',
        ]
    else:
        lines = [
            'tropo: boot-reconcile orphaned drift → system-reconcile',
            '',
            'trigger: boot-reconcile',
            f'booting_agent: {boot_agent}',
            f'booting_generation: {boot_generation}',
            'reconcile: true',
            'attribution: system-reconcile',
        ]
    names = staged_names()
    if names:
        lines.append('files:')
        lines.extend(f'  - {n}' for n in names[:200])
    return '\n'.join(lines)


def commit_message_vault_maintenance() -> str:
    lines = [
        'tropo: vault-maintenance commit backstop',
        '',
        'trigger: vault-maintenance-loop',
        'attribution: vault-maintenance',
    ]
    names = staged_names()
    if names:
        lines.append('files:')
        lines.extend(f'  - {n}' for n in names[:200])
    return '\n'.join(lines)


def stage_and_commit(message: str, root: Path | None = None, *, allow_empty: bool = False) -> tuple[bool, str]:
    root = root or repo_root()
    if not is_git_repo(root):
        return False, 'not a git repository'
    if is_clean(root) and not allow_empty:
        return True, 'clean (nothing to commit)'
    ok, err = stage_all(root)
    if not ok:
        return False, err
    if not staged_names(root) and not allow_empty:
        return True, 'nothing staged'
    code, out, err = _git_run(['commit', '-m', message], root)
    if code != 0:
        combined = (err or out or '').strip()
        if 'nothing to commit' in combined.lower():
            return True, 'nothing to commit'
        return False, combined or 'git commit failed'
    sha = out.strip().split()[-1] if out.strip() else ''
    return True, sha or 'committed'


def stage_then_commit(build_message, root: Path | None = None, *, allow_empty: bool = False) -> tuple[bool, str]:
    """Stage FIRST, then build the commit message (so staged_names() sees reality).

    v1.81-followup fix (Argus A126, 00005787): the *_commit callers previously built
    the commit message via commit_message_close/reconcile/vault_maintenance BEFORE
    staging ran, so their `files:` list read staged_names() against an empty index —
    always empty. `build_message` is a zero-arg callable invoked only after `git add -A`.
    """
    root = root or repo_root()
    if not is_git_repo(root):
        return False, 'not a git repository'
    if is_clean(root) and not allow_empty:
        return True, 'clean (nothing to commit)'
    ok, err = stage_all(root)
    if not ok:
        return False, err
    if not staged_names(root) and not allow_empty:
        return True, 'nothing staged'
    message = build_message()
    code, out, err = _git_run(['commit', '-m', message], root)
    if code != 0:
        combined = (err or out or '').strip()
        if 'nothing to commit' in combined.lower():
            return True, 'nothing to commit'
        return False, combined or 'git commit failed'
    sha = out.strip().split()[-1] if out.strip() else ''
    return True, sha or 'committed'


def signal_commit_failure(activation_uid: str, reason: str) -> None:
    """Visible failure: flash broadcast + flag file (98b9610a — never silent)."""
    fd = flags_dir()
    fd.mkdir(parents=True, exist_ok=True)
    flag = fd / f'uncommitted-{activation_uid}.flag'
    flag.write_text(
        f"activation_uid: {activation_uid}\n"
        f"reason: {reason}\n"
        f"at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n",
        encoding='utf-8',
    )
    emit = repo_root() / 'vault' / 'tools' / 'tropo-emit-event.py'
    if not emit.exists():
        return
    import json
    body = (
        f'Git Beat 1 commit FAILED for activation {activation_uid}: {reason}. '
        f'Flag: .tropo/flags/uncommitted-{activation_uid}.flag'
    )
    data = json.dumps({
        'category': 'ops',
        'severity': 'flash',
        'headline': f'Uncommitted activation close: {activation_uid}',
        'body': body,
    })
    try:
        subprocess.run(
            [
                sys.executable, str(emit),
                '--type', 'tropo.broadcast.crew',
                '--source', '/tools/write-activation-entry',
                '--source-uid', '40b2f455',
                '--lifecycle', 'ephemeral',
                '--data', data,
            ],
            cwd=str(repo_root()),
            capture_output=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def find_prior_activation_for_reconcile(entries: list[tuple[str, dict]]) -> dict | None:
    """Pick attribution target for boot-reconcile: active first, else latest terminal."""
    active = [(u, fm) for u, fm in entries if fm.get('status') == 'active']
    if active:
        active.sort(key=lambda p: (p[1].get('activated_at', ''), p[1].get('generation', '')), reverse=True)
        u, fm = active[0]
        return {**fm, 'uid': u}

    terminal = [(u, fm) for u, fm in entries
                if fm.get('status') in ('retired', 'failed', 'stale', 'paused')]
    if not terminal:
        return None
    terminal.sort(key=lambda p: (p[1].get('retired_at', ''), p[1].get('activated_at', ''), p[1].get('generation', '')),
                  reverse=True)
    u, fm = terminal[0]
    return {**fm, 'uid': u}


def boot_reconcile_if_dirty(boot_agent: str, boot_generation: str, scan_activations_fn) -> tuple[bool, str]:
    """Group 0 boot-reconcile: commit orphaned drift before new activation work."""
    root = repo_root()
    if not is_git_repo(root):
        return True, 'no git repo (skip)'
    if is_clean(root):
        return True, 'clean'
    entries = scan_activations_fn()
    prior = find_prior_activation_for_reconcile(entries)
    ok, detail = stage_then_commit(lambda: commit_message_reconcile(prior, boot_agent, boot_generation), root)
    if not ok:
        uid = (prior or {}).get('uid', 'boot-reconcile')
        signal_commit_failure(uid, f'boot-reconcile: {detail}')
        return False, detail
    if not is_clean(root):
        uid = (prior or {}).get('uid', 'boot-reconcile')
        signal_commit_failure(uid, f'boot-reconcile left dirty tree: {porcelain(root)[:300]}')
        return False, 'tree still dirty after reconcile'
    return True, detail


def activation_close_commit(
    fm: dict,
    activation_uid: str,
    target_status: str,
    closure_reason: str = '',
    transfer_uid: str = '',
    closer: str = '',
) -> tuple[bool, str]:
    root = repo_root()
    if not is_git_repo(root):
        return True, 'no git repo (skip)'
    agent = fm.get('agent', 'unknown')
    gen = str(fm.get('generation', '?')).lower()
    closer = closer or f'{agent}-{gen}'
    ok, detail = stage_then_commit(
        lambda: commit_message_close(fm, activation_uid, target_status, closure_reason, transfer_uid, closer),
        root,
    )
    if not ok:
        signal_commit_failure(activation_uid, detail)
        return False, detail
    if not is_clean(root):
        signal_commit_failure(activation_uid, f'close left dirty tree: {porcelain(root)[:300]}')
        return False, 'tree still dirty after close commit'
    return True, detail
