#!/usr/bin/env python3
"""
---
uid: b7e4a2c9
type: tool
name: tropo-restore
title: "tropo-restore — governance-aware git checkout + re-index"
status: active
owner: talos
domain: "Git Beat 1 governed undo (dev-spec 98b9610a)"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-restore.py <uid> --to <commit> --reason <text>"
script_path: vault/tools/tropo-restore.py
spawnable_by:
  - all-executives
write_scope: [vault/files/, vault/agents/]
created: 2026-07-05
created_by: talos-t25
version: "1.0"
governed_by: d5e1b4a3
member_of:
  - 8dd772a0
schema_version: 2
extraction_scope: ship
trigger_description: "Restore a governed artifact to a prior git commit with mandatory re-index."
belt: false
belt_note: "Self-heal (Talos T25, 2026-07-06, ADR-050/796d9330 build): demoted from belt:true — pushed the belt cap (15) to 16, blocking capability-catalog regeneration. tropo-restore is an occasional governed-undo escape hatch, not a reach-for-this-constantly tool; the full tool-catalog.md entry (unaffected by belt status) remains discoverable."
---

Governance-aware restore: git checkout → rebuild-index --only → governed event → provenance.
Forward-only; reason required; preserves source bytes (never rewrites extraction_scope).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / 'vault' / 'files'
TOOLS = VAULT_ROOT / 'vault' / 'tools'
TODAY = datetime.now(timezone.utc).strftime('%Y-%m-%d')
UID_RE = re.compile(r'^[0-9a-f]{8}$')
COMMIT_RE = re.compile(r'^[0-9a-f]{7,40}$')


def _split_frontmatter(text: str):
    m = re.match(r'^---\r?\n(.*?\r?\n)---\r?\n?', text, re.DOTALL)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def resolve_uid_path(uid: str) -> Path | None:
    candidates = [
        VAULT_ROOT / 'vault' / 'files' / f'{uid}.md',
        VAULT_ROOT / 'vault' / 'agents' / f'{uid}.md',
    ]
    for p in candidates:
        if p.exists():
            return p
    # Fallback: scan vault/agents + vault/files
    for base in (VAULT_ROOT / 'vault' / 'agents', VAULT_ROOT / 'vault' / 'files'):
        if not base.exists():
            continue
        fp = base / f'{uid}.md'
        if fp.exists():
            return fp
    return None


def parse_frontmatter(path: Path) -> tuple[dict, str, str] | None:
    text = path.read_text(encoding='utf-8', errors='replace')
    fm_str, body = _split_frontmatter(text)
    if fm_str is None:
        return None
    fm = {}
    for line in fm_str.splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, fm_str, body


def write_provenance(path: Path, fm_str: str, body: str, commit: str, actor: str) -> None:
    lines = fm_str.splitlines()
    out = []
    skip_keys = {'restored_at', 'restored_by', 'restored_from_commit', 'modified'}
    for line in lines:
        key = line.split(':', 1)[0].strip() if ':' in line else ''
        if key in skip_keys:
            continue
        out.append(line)
    out.append(f'restored_at: {TODAY}')
    out.append(f'restored_by: {actor}')
    out.append(f'restored_from_commit: {commit}')
    out.append(f'modified: {TODAY}')
    # v1.81-followup fix (Argus A126, 00005787): body already carries its own
    # leading blank-line newline post-split — omitting the explicit \n here
    # silently collapsed the frontmatter/body blank line on every restore.
    path.write_text('---\n' + '\n'.join(out) + '\n---\n' + body, encoding='utf-8')


def emit_restore_event(uid: str, commit: str, reason: str, actor: str, path: Path) -> None:
    emit = TOOLS / 'tropo-emit-event.py'
    if not emit.exists():
        return
    data = json.dumps({
        'uid': uid,
        'commit': commit,
        'reason': reason,
        'actor': actor,
        'path': str(path.relative_to(VAULT_ROOT)),
        'action': 'tropo-restore',
    })
    subprocess.run(
        [
            sys.executable, str(emit),
            '--type', 'tropo.substrate.modified',
            '--source', '/tools/tropo-restore',
            '--source-uid', 'b7e4a2c9',
            '--lifecycle', 'evergreen',
            '--subject', uid,
            '--data', data,
        ],
        cwd=str(VAULT_ROOT),
        capture_output=True,
        timeout=15,
    )


def rebuild_only(uid: str) -> int:
    script = TOOLS / 'tropo-rebuild-index.py'
    r = subprocess.run(
        [sys.executable, str(script), '--only', uid, '--apply'],
        cwd=str(VAULT_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        print(r.stderr or r.stdout, file=sys.stderr)
    return r.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('uid', help='8-hex governed entry UID')
    parser.add_argument('--to', dest='commit', required=True, help='Git commit SHA')
    parser.add_argument('--reason', required=True, help='Why this restore (required)')
    parser.add_argument('--actor', default='talos-t25', help='Who performed the restore')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    uid = args.uid.strip().lower()
    commit = args.commit.strip().lower()
    reason = args.reason.strip()
    if not UID_RE.match(uid):
        print(f'ERROR: invalid uid {uid!r}', file=sys.stderr)
        return 1
    if not COMMIT_RE.match(commit):
        print(f'ERROR: invalid commit {commit!r}', file=sys.stderr)
        return 1
    if not reason:
        print('ERROR: --reason is required', file=sys.stderr)
        return 1

    fp = resolve_uid_path(uid)
    if fp is None:
        print(f'ERROR: no governed file for uid {uid}', file=sys.stderr)
        return 1

    rel = fp.relative_to(VAULT_ROOT)
    parsed = parse_frontmatter(fp)
    if parsed is None:
        print(f'ERROR: {fp} has no frontmatter', file=sys.stderr)
        return 1

    if args.dry_run:
        print(f'DRY RUN: would restore {rel} to {commit} — {reason}')
        return 0

    # Verify commit exists
    verify = subprocess.run(
        ['git', 'cat-file', '-e', f'{commit}^{{commit}}'],
        cwd=str(VAULT_ROOT),
        capture_output=True,
        timeout=15,
    )
    if verify.returncode != 0:
        print(f'ERROR: commit {commit} not found in repo', file=sys.stderr)
        return 1

    checkout = subprocess.run(
        ['git', 'checkout', commit, '--', str(rel)],
        cwd=str(VAULT_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if checkout.returncode != 0:
        print(checkout.stderr or checkout.stdout, file=sys.stderr)
        return 1

    parsed2 = parse_frontmatter(fp)
    if parsed2 is None:
        print(f'ERROR: restored file unreadable', file=sys.stderr)
        return 1
    fm_str, body = parsed2[1], parsed2[2]
    write_provenance(fp, fm_str, body, commit, args.actor)

    rc = rebuild_only(uid)
    if rc != 0:
        print(f'ERROR: rebuild-index --only {uid} failed (exit {rc})', file=sys.stderr)
        return rc

    emit_restore_event(uid, commit, reason, args.actor, fp)
    print(f'RESTORED: {uid} @ {commit[:8]} — {reason}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
