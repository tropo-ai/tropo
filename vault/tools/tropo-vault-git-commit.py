#!/usr/bin/env python3
"""tropo-vault-git-commit — vault-maintenance commit backstop (Git Beat 1, 98b9610a).

Registered maintenance loop runner: commits uncommitted vault drift when no agent
session is active. Owner: maintenance subsystem / Vela operational lane.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.tropo_git_history import (  # noqa: E402
    commit_message_vault_maintenance,
    is_clean,
    is_git_repo,
    porcelain,
    repo_root,
    set_repo_root,
    stage_then_commit,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Report only; do not commit')
    parser.add_argument('--vault-root', default='', help='Studio root override (tests only)')
    args = parser.parse_args()
    if args.vault_root:
        set_repo_root(Path(args.vault_root).resolve())
    root = repo_root()
    if not is_git_repo(root):
        print('SKIP: no git repository at studio root')
        return 0
    if is_clean(root):
        print('OK: working tree clean')
        return 0
    status = porcelain(root)
    print(f'DIRTY: {len(status.splitlines())} path(s) changed')
    if args.dry_run:
        print(status[:2000])
        return 0
    ok, detail = stage_then_commit(commit_message_vault_maintenance, root)
    if not ok:
        print(f'ERROR: vault-maintenance commit failed: {detail}', file=sys.stderr)
        return 1
    if not is_clean(root):
        print(f'ERROR: tree still dirty after commit:\n{porcelain(root)[:500]}', file=sys.stderr)
        return 1
    print(f'COMMITTED: {detail}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
