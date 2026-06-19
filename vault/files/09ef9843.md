#!/usr/bin/env python3
"""
---
uid: 09ef9843
name: tropo-backfill-styles
type: tool
title: tropo-backfill-styles
description: 'Migration gesture for pre-v1.28.0 substrate. Three modes: --projection <uid> (single backfill of original_styles), --all (sweep all external-artifact entries without original_styles), --folder-markers (NEW v0.5 — sweep on-disk markers without vault mirrors; co-author with retro-fill semantics). Sweep modes require --yes to bypass TTY prompt.'
state: active
status: active
stage: build
owner: argus-a62
member_of:
- 76bb8b41
created: 2026-05-14
modified: 2026-05-14
created_by: argus-a62
modified_by: argus-a62
schema_version: 2
extraction_scope: ship
domain: 'Backfill v1.28.0 substrate fields onto pre-v1.28.0 entries: original_styles: on external-artifact projections + missing folder-marker mirrors. Closes the migration gap for pre-existing imports.'
spawnable_by:
- all-executives
- user
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/09ef9843.py (--projection <uid> | --all | --folder-markers) [--yes] [--force]
script_path: vault/tools/09ef9843.py
language: python
version: 1.0.0
destructive: 'false'
audit_required: 'true'
writes_scope:
- vault/files/**
- vault/00-index.jsonl
- .tropo-studio/reconciler/journal.jsonl
reads_scope:
- vault/files/**
- '**/.tropo-folder.md'
- external-work/**/*.docx
governance_category: lifecycle
domain_tags:
- backfill
- migration
- original-styles
- folder-marker-mirror
- retro-fill
- v1.28.0-stream-b
- v0.5-extended
trigger_description: 'Reach for this when migrating pre-v1.28.0 substrate up to v1.28.0+ shape. THREE modes: (a) `--projection <uid>` backfills original_styles: on a single external-artifact entry. (b) `--all --yes` sweeps all external-artifact entries without original_styles:; populates them by opening the source binary + calling office_styles.extract_office_styles(). (c) `--folder-markers --yes` (v0.5 NEW) sweeps on-disk .tropo-folder.md markers without matching vault mirrors at vault/files/<marker-uid>.md; co-authors the missing mirror using retro-fill semantics per arch-spec §3.5.5 Amendment 1 v0.5. Sweep modes require --yes to bypass TTY prompt; bare sweep on non-TTY refuses (per spec §3.13 v0.5 precondition 4). Idempotent unless --force. Mike''s 3 David files (d63bf867 / 8c62a820 / ec5c4748) imported 2026-05-13 under v1.25.0/v1.26.0 substrate are the load-bearing test subjects — `--all --yes` populated original_styles: on all 3.'
governed_by: d5e1b4a3
capsule_version: '2.5'
aligned_with:
- 5a89297a
tags:
- tool
- cli
- python
- tropo-backfill-styles
- migration
- retro-fill
- original-styles
- folder-marker-mirror
- v1.28.0-stream-b
file_ext: md
subsystem_hub:
- 76bab75f
---
"""
from __future__ import annotations

"""Tropo style + folder-mirror backfill — migration gesture for pre-v1.28.0 substrate.

Per arch-spec [5a89297a v0.5](../../vault/files/5a89297a.md) §3.13 (NEW + extended):

  - `--projection <uid>`: backfill `original_styles:` on a single external-artifact entry
  - `--all`: sweep all external-artifact entries without `original_styles:` (closes
    the gap for Mike's 3 David files imported 2026-05-13 under v1.25.0/v1.26.0 substrate)
  - `--folder-markers` (v0.5 NEW): sweep pre-v0.4 on-disk folder markers; co-author
    missing vault mirrors with retro-fill semantics (closes asymmetric migration gap
    per spec §3.5.5 Amendment 1 v0.5)

Sweep modes require `--yes` to proceed without TTY prompt (bare --all on TTY prompts;
non-TTY refuses bare --all per arch-spec §3.13 v0.5 precondition 4).

Author: argus-a62
Owner: argus
v1.28.0 Stream B deliverable.
"""


import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml as _yaml_lib
    _HAS_YAML = True
except ImportError:
    _yaml_lib = None
    _HAS_YAML = False


TOOL_NAME = 'tropo-backfill-styles'
TOOL_VERSION = '1.0.1'   # v1.0.0 = v1.28.0 ship; v1.0.1 = v1.32.0 Stream E P1-3
                          # closure (--folder-markers skip-set narrowed to kernel-
                          # managed + system trees only; agents/channels/playbooks/
                          # shared subtrees now reachable by backfill sweep per
                          # spec [900d41e0] §3.3 v0.4 LOCKED)

LOCK_RELPATH = '.tropo-studio/reconciler/.lock'
JOURNAL_RELPATH = '.tropo-studio/reconciler/journal.jsonl'
VAULT_INDEX_RELPATH = 'vault/00-index.jsonl'
LOCK_STALE_SECONDS = 3600

# Shared modules
# v1.56 Lane S: script relocated to vault/tools/; lib/ imports from .tropo/scripts/
_SCRIPT_DIR = Path(__file__).resolve().parents[2] / '.tropo' / 'scripts'
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
import office_styles  # noqa: E402

# Import import-walker.py as a library to reuse write_folder_mirror, append_folder_mirror_index_row, etc.
import importlib.util
_iw_spec = importlib.util.spec_from_file_location('import_walker', _SCRIPT_DIR / 'import-walker.py')
import_walker = importlib.util.module_from_spec(_iw_spec)
_iw_spec.loader.exec_module(import_walker)


# ==========================================================================
# Common helpers
# ==========================================================================

def resolve_studio_root(arg_path=None):
    if arg_path:
        p = Path(arg_path).resolve()
        if (p / '.tropo').exists():
            return p
        raise SystemExit(f"--studio-root {arg_path} is not a Studio root")
    p = Path.cwd().resolve()
    while p != p.parent:
        if (p / '.tropo').exists():
            return p
        p = p.parent
    raise SystemExit("Not inside a Tropo Studio")


def now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def now_date():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def parse_frontmatter(file_path):
    """Read a markdown file's YAML frontmatter. Uses PyYAML when available."""
    if not file_path.exists():
        return {}
    text = file_path.read_text()
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    if _HAS_YAML:
        try:
            parsed = _yaml_lib.safe_load(block)
            return parsed if isinstance(parsed, dict) else {}
        except _yaml_lib.YAMLError:
            return {}
    # Fallback: minimal flat parser
    fm = {}
    for line in block.split('\n'):
        if not line.strip() or line.strip().startswith('#'):
            continue
        m_kv = re.match(r'^(\w+):\s*(.+)$', line)
        if m_kv:
            fm[m_kv.group(1)] = m_kv.group(2).strip().strip('"')
    return fm


class ReconcilerLock:
    """Same shape as import-walker.py + tropo-register-template.py per spec §3.12."""
    def __init__(self, studio_root, executive='cli-user'):
        self.lock_path = studio_root / LOCK_RELPATH
        self.executive = executive

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            try:
                age = datetime.now().timestamp() - self.lock_path.stat().st_mtime
                if age > LOCK_STALE_SECONDS:
                    print(f"WARN: overriding stale reconciler lock (age {age:.0f}s)",
                          file=sys.stderr)
                    self.lock_path.unlink()
                else:
                    raise SystemExit(
                        f"Reconciler lock held: {self.lock_path.read_text().strip()}")
            except OSError:
                pass
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {now_iso()} {self.executive}".encode())
            os.close(fd)
        except FileExistsError:
            raise SystemExit("Reconciler lock race")
        return self

    def __exit__(self, *a):
        try:
            self.lock_path.unlink()
        except OSError:
            pass


def append_journal(studio_root, event):
    journal_path = studio_root / JOURNAL_RELPATH
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    def _default(o):
        if hasattr(o, 'isoformat'):
            return o.isoformat()
        raise TypeError(f"Type {type(o).__name__} not JSON serializable")

    with journal_path.open('a') as f:
        f.write(json.dumps(event, separators=(',', ':'), default=_default) + '\n')
        f.flush()
        os.fsync(f.fileno())


# ==========================================================================
# Backfill original_styles on a single projection
# ==========================================================================

def backfill_projection_styles(studio_root, projection_uid, force=False, executive='cli-user'):
    """Backfill original_styles on a single external-artifact projection.

    Returns dict with keys: status (one of 'updated' / 'skipped_already_populated' /
    'skipped_non_office' / 'failed'), reason (str), styles_dict (dict|None).
    """
    proj_path = studio_root / 'vault' / 'files' / f'{projection_uid}.md'
    if not proj_path.exists():
        return {'status': 'failed',
                'reason': f'projection vault/files/{projection_uid}.md does not exist',
                'styles_dict': None}

    fm = parse_frontmatter(proj_path)
    if fm.get('type') != 'external-artifact':
        return {'status': 'failed',
                'reason': f"entry type is {fm.get('type')!r}, not external-artifact",
                'styles_dict': None}

    if fm.get('original_styles') and not force:
        return {'status': 'skipped_already_populated',
                'reason': 'original_styles already present (use --force to re-extract)',
                'styles_dict': None}

    source_path_rel = fm.get('source_path')
    if not source_path_rel:
        return {'status': 'failed',
                'reason': 'projection has no source_path',
                'styles_dict': None}

    # Per spec v0.5 sa.cold-boot-007 X3: caller resolves to absolute Path
    source_path_abs = (studio_root / source_path_rel).resolve()
    if not source_path_abs.exists():
        return {'status': 'failed',
                'reason': f'source binary not found at {source_path_rel}',
                'styles_dict': None}

    styles = office_styles.extract_office_styles(source_path_abs)
    if styles is None:
        return {'status': 'skipped_non_office',
                'reason': f'source binary is not a recognized .docx (extension or content)',
                'styles_dict': None}

    # Update the projection: rewrite frontmatter with original_styles inserted before created:
    text = proj_path.read_text()
    block_yaml = import_walker._serialize_original_styles_yaml(styles)

    # Strip any existing original_styles block first (--force re-extract case)
    text = re.sub(r'\noriginal_styles:.*?(?=\n[a-z_]+:|\n---)', '\n', text, count=1, flags=re.DOTALL)

    # Insert new block before `created:` line.
    # Use a lambda for the replacement to avoid re.sub interpreting backslash
    # escapes in block_yaml (e.g. \u from quoted special chars in style names).
    if '\noriginal_styles:' not in text:
        replacement = f'\n{block_yaml}\ncreated:'
        text = re.sub(r'\ncreated:', lambda _m: replacement, text, count=1)

    text = re.sub(r'^modified: \S+', f'modified: {now_date()}', text, flags=re.MULTILINE)
    text = re.sub(r'^modified_by: \S+', f'modified_by: {TOOL_NAME}-v{TOOL_VERSION}',
                  text, flags=re.MULTILINE)

    proj_path.write_text(text)

    return {'status': 'updated',
            'reason': f'extracted {len(styles.get("named_styles", []))} named styles',
            'styles_dict': styles}


def find_projections_without_original_styles(studio_root):
    """Walk vault/files/ for type:external-artifact entries lacking original_styles.

    Uses parse_frontmatter to check the actual `type` field (not a head-text
    substring scan, which false-matches files that mention 'external-artifact'
    in their body — e.g. the arch-spec).
    """
    candidates = []
    vault_files = studio_root / 'vault' / 'files'
    if not vault_files.exists():
        return candidates
    for md_file in vault_files.glob('*.md'):
        try:
            fm = parse_frontmatter(md_file)
            if fm.get('type') != 'external-artifact':
                continue
            if fm.get('original_styles'):
                continue
            candidates.append(md_file.stem)
        except (OSError, UnicodeDecodeError):
            continue
    return sorted(candidates)


# ==========================================================================
# Backfill folder-mirror — v0.5 NEW per arch-spec §3.13 + §3.5.5 Amendment 1
# ==========================================================================

def find_markers_without_mirrors(studio_root):
    """Walk for .tropo-studio/.tropo-folder.md files; return [(marker_path, folder_uid, ...)]
    for each marker that lacks a vault/files/<uid>.md mirror."""
    candidates = []
    # Walk filesystem for .tropo-folder.md files (skip kernel-managed dirs).
    # P1-3 closure (v1.32.0 spec [900d41e0] §3.3 v0.4 LOCKED): skip_dirs narrowed
    # from v1.0.0 to only kernel + system trees. Previously skipped agents/
    # channels/playbooks/shared/templates entirely; folder markers under those
    # subtrees were unreachable. Now reachable; backfill sweep covers user-
    # imported folders placed under any work-subdirectory in the crew/channels/
    # playbooks substrates + the shared/ Studio-root surface. (templates/ at
    # Studio root is no-op-but-harmless per spec v0.2 skeptic-069 P2-F: kernel-
    # managed docx templates live at .tropo-studio/templates/ which stays skipped
    # via .tropo-studio ancestor; a Studio-root templates/ folder is unconventional
    # but reachable for symmetry.)
    skip_dirs = {'.tropo', '.tropo-studio', 'vault', '.git', 'archive', 'recycle', 'updates'}
    for root, dirs, files in os.walk(studio_root):
        # Prune kernel dirs
        rel = Path(root).relative_to(studio_root)
        if rel.parts and rel.parts[0] in skip_dirs:
            dirs[:] = []
            continue
        # Look for .tropo-studio child
        if '.tropo-studio' in dirs:
            marker = Path(root) / '.tropo-studio' / '.tropo-folder.md'
            if marker.exists():
                fm = parse_frontmatter(marker)
                folder_uid = fm.get('uid')
                if not folder_uid:
                    continue
                mirror_path = studio_root / 'vault' / 'files' / f'{folder_uid}.md'
                if not mirror_path.exists():
                    folder_path = Path(root)
                    candidates.append({
                        'marker_path': marker,
                        'folder_uid': folder_uid,
                        'folder_name': folder_path.name,
                        'folder_rel': str(folder_path.relative_to(studio_root)),
                        'marker_rel': str(marker.relative_to(studio_root)),
                    })
    return candidates


def backfill_folder_mirror(studio_root, candidate, executive='cli-user'):
    """Author the missing vault mirror for a marker via retro-fill semantics."""
    folder_uid = candidate['folder_uid']
    try:
        mirror_tmp, mirror_final = import_walker.write_folder_mirror(
            studio_root=studio_root,
            folder_uid=folder_uid,
            folder_name=candidate['folder_name'],
            original_path=candidate['folder_rel'],
            folder_marker_path_rel=candidate['marker_rel'],
        )
        os.replace(mirror_tmp, mirror_final)
        import_walker.append_folder_mirror_index_row(
            studio_root=studio_root,
            folder_uid=folder_uid,
            folder_name=candidate['folder_name'],
            original_path=candidate['folder_rel'],
            folder_marker_path_rel=candidate['marker_rel'],
        )
        return {'status': 'updated', 'reason': f"mirror authored for marker uid {folder_uid}"}
    except Exception as e:
        return {'status': 'failed', 'reason': f'{type(e).__name__}: {e}'}


# ==========================================================================
# Sweep-mode confirmation gate per spec §3.13 v0.5 precondition 4
# ==========================================================================

def confirm_sweep(count, mode_label, yes_flag):
    """Return True if sweep should proceed; False if user aborts."""
    if yes_flag:
        return True
    if not sys.stdin.isatty():
        raise SystemExit(
            f"Non-interactive {mode_label} sweep requires --yes (per arch-spec §3.13 v0.5 "
            f"precondition 4). Pass --yes to proceed without prompt."
        )
    answer = input(f"Backfill {count} candidates ({mode_label})? [y/N] ").strip().lower()
    return answer == 'y'


# ==========================================================================
# CLI entry point
# ==========================================================================

def main():
    parser = argparse.ArgumentParser(
        prog='tropo-backfill-styles.py',
        description=__doc__.split('\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--projection', help="Backfill a single projection by UID")
    mode_group.add_argument('--all', action='store_true',
                            help="Sweep mode: backfill all external-artifact entries without "
                                 "original_styles. Requires --yes (or TTY-prompt).")
    mode_group.add_argument('--folder-markers', action='store_true',
                            help="v0.5 NEW: sweep on-disk folder markers; co-author missing "
                                 "vault mirrors with retro-fill semantics. Requires --yes (or TTY-prompt).")

    parser.add_argument('--force', action='store_true',
                        help="Re-extract even if original_styles already populated "
                             "(--projection or --all only).")
    parser.add_argument('--yes', '-y', action='store_true',
                        help="Skip TTY confirmation for sweep modes.")
    parser.add_argument('--studio-root', default=None)
    parser.add_argument('--run-uid', default='cli-standalone')
    parser.add_argument('--executive', default='cli-user')
    args = parser.parse_args()

    studio_root = resolve_studio_root(args.studio_root)

    with ReconcilerLock(studio_root, executive=args.executive):
        if args.projection:
            # Single-projection mode
            result = backfill_projection_styles(
                studio_root, args.projection, force=args.force, executive=args.executive)
            append_journal(studio_root, {
                'event': 'original_styles_backfilled',
                'projection_uid': args.projection,
                'status': result['status'],
                'reason': result['reason'],
                'named_styles_count': len(result['styles_dict'].get('named_styles', []))
                                       if result['styles_dict'] else 0,
                'timestamp': now_iso(),
                'executive': args.executive,
                'run_uid': args.run_uid,
            })
            if result['status'] == 'failed':
                print(f"FAILED {args.projection}: {result['reason']}", file=sys.stderr)
                sys.exit(2)
            elif result['status'] == 'skipped_already_populated':
                print(f"SKIPPED {args.projection}: already populated (use --force to override)")
            elif result['status'] == 'skipped_non_office':
                print(f"SKIPPED {args.projection}: {result['reason']}", file=sys.stderr)
            else:
                print(f"BACKFILLED {args.projection}: {result['reason']}")

        elif args.all:
            # Sweep mode for projections
            candidates = find_projections_without_original_styles(studio_root)
            print(f"Found {len(candidates)} projections without original_styles.")
            if not candidates:
                return
            if not confirm_sweep(len(candidates), '--all (style backfill)', args.yes):
                print("Aborted.", file=sys.stderr)
                sys.exit(1)
            counts = {'updated': 0, 'skipped_already_populated': 0,
                     'skipped_non_office': 0, 'failed': 0}
            for uid in candidates:
                result = backfill_projection_styles(
                    studio_root, uid, force=args.force, executive=args.executive)
                counts[result['status']] = counts.get(result['status'], 0) + 1
                append_journal(studio_root, {
                    'event': 'original_styles_backfilled',
                    'projection_uid': uid,
                    'status': result['status'],
                    'reason': result['reason'],
                    'named_styles_count': len(result['styles_dict'].get('named_styles', []))
                                           if result['styles_dict'] else 0,
                    'timestamp': now_iso(),
                    'executive': args.executive,
                    'run_uid': args.run_uid,
                })
                if result['status'] in ('failed', 'skipped_non_office'):
                    print(f"  {result['status'].upper()} {uid}: {result['reason']}", file=sys.stderr)
                elif result['status'] == 'updated':
                    print(f"  BACKFILLED {uid}: {result['reason']}")
            print(f"\nSummary: backfilled {counts['updated']} of {len(candidates)} candidates; "
                  f"{counts['skipped_already_populated']} skipped (already populated); "
                  f"{counts['skipped_non_office']} skipped (non-Office); "
                  f"{counts['failed']} failed.")

        elif args.folder_markers:
            # Sweep mode for folder markers (v0.5 NEW)
            candidates = find_markers_without_mirrors(studio_root)
            print(f"Found {len(candidates)} folder markers without vault mirrors.")
            if not candidates:
                return
            if not confirm_sweep(len(candidates), '--folder-markers (mirror backfill)', args.yes):
                print("Aborted.", file=sys.stderr)
                sys.exit(1)
            counts = {'updated': 0, 'failed': 0}
            for cand in candidates:
                result = backfill_folder_mirror(studio_root, cand, executive=args.executive)
                counts[result['status']] = counts.get(result['status'], 0) + 1
                append_journal(studio_root, {
                    'event': 'folder_mirror_backfilled',
                    'folder_uid': cand['folder_uid'],
                    'folder_path': cand['folder_rel'],
                    'marker_path': cand['marker_rel'],
                    'status': result['status'],
                    'reason': result['reason'],
                    'timestamp': now_iso(),
                    'executive': args.executive,
                    'run_uid': args.run_uid,
                })
                if result['status'] == 'failed':
                    print(f"  FAILED {cand['folder_uid']} ({cand['folder_rel']}): {result['reason']}",
                          file=sys.stderr)
                else:
                    print(f"  BACKFILLED mirror for {cand['folder_uid']} ({cand['folder_rel']})")
            print(f"\nSummary: backfilled {counts['updated']} of {len(candidates)} markers; "
                  f"{counts['failed']} failed.")


if __name__ == '__main__':
    main()
