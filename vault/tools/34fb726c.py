#!/usr/bin/env python3
"""
---
uid: 34fb726c
name: fix-duplicate-yaml-keys
type: tool
status: active
owner: talos
domain: "fix-duplicate-yaml-keys.py — one-shot cleanup for the v1.12 dup-key class."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/34fb726c.py"
script_path: vault/tools/34fb726c.py
spawnable_by:
  - all-executives
input:
  type: object
  description: "See tool usage for argument details"
created: 2026-05-27
created_by: talos-t10
governed_by: d5e1b4a3
member_of:
  - c7e4f9a2
schema_version: 2
---
"""

"""fix-duplicate-yaml-keys.py — one-shot cleanup for the v1.12 dup-key class.

Walks vault/files/*.md, detects duplicate top-level YAML frontmatter keys,
merges values per the v1.29.0 v0.4 spec §3.1 merge semantics, writes back.

Spec: vault/files/81555e45.md v0.4 §3.1.
Stream A of v1.29.0; see vault/files/d4eaf245.md for execution plan.

Detection scope: top-level YAML keys ONLY. Within-list value duplicates
are out of scope per Mike-A63 2026-05-14; filed at vault/files/6ba0e525.md.

Usage:
  python3 .tropo/scripts/fix-duplicate-yaml-keys.py [--dry-run|--apply] [--scope PATH]

Modes:
  --dry-run (default)  Walk + report; do not write. No precondition.
  --apply              Walk + report + write. Requires clean git working tree.

Exit codes:
  0  Success (clean OR dry-run completed OR apply completed)
  1  Other error (file unreadable, etc.)
  3  Scalar conflict on --apply (manual resolution required)
  4  Dirty git working tree on --apply (precondition not met)
  5  --scope path invalid (not a directory under vault root)
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Ensure shared lib is importable when invoked from repo root or vault root
# v1.56 Lane S: script relocated to vault/tools/; lib/ imports from .tropo/scripts/
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / '.tropo' / 'scripts'
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _yaml_dup_lib import (  # noqa: E402
    detect_duplicate_yaml_keys,
    extract_frontmatter,
    merge_duplicate_yaml_keys,
)

# Default scope (relative to vault root)
DEFAULT_SCOPE = 'vault/files'


def _resolve_vault_root() -> Path:
    """Resolve vault root from this script's location.

    Script lives at <vault_root>/.tropo/scripts/fix-duplicate-yaml-keys.py.
    Vault root is two directories up.
    """
    return _SCRIPTS_DIR.parent.parent


def _check_git_clean_tree(vault_root: Path) -> tuple[bool, str]:
    """Check whether the git working tree is clean.

    Returns (is_clean, status_text). is_clean is True if `git status
    --porcelain` returns no output. status_text is the porcelain output
    (empty string if clean, or first 500 chars if not).
    """
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=vault_root,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        # git not available or hung — refuse cautiously, treat as not-clean
        return False, f'git status check failed: {exc}'
    if result.returncode != 0:
        return False, f'git status returned non-zero: {result.stderr[:500]}'
    output = result.stdout
    return output.strip() == '', output[:500]


def _process_file(
    path: Path,
    apply: bool,
) -> tuple[dict[str, int], dict[str, int], list[str], bool]:
    """Process a single file.

    Returns (key_occurrences, values_deduped, errors, wrote).
    - key_occurrences: per-key occurrence count (e.g., {member_of: 2}
      means the key appeared 2 times at top level; collapsed to 1)
    - values_deduped: per-key count of duplicate VALUES dropped during
      dedup (e.g., {member_of: 1} means one value appeared twice and one
      was dropped). May be empty even when key_occurrences is non-empty
      (the case where each key occurrence carried unique values).
    - errors: list of scalar-conflict errors (empty if none)
    - wrote: True only if --apply mode AND file was modified
    """
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        print(f'  WARN: cannot read {path}: {exc}', file=sys.stderr)
        return {}, {}, [], False

    parts = extract_frontmatter(text)
    if parts is None:
        # No frontmatter delimiters — skip
        return {}, {}, [], False
    opening, body, after = parts

    key_occurrences = detect_duplicate_yaml_keys(body)
    if not key_occurrences:
        return {}, {}, [], False

    merged_body, values_deduped, errors = merge_duplicate_yaml_keys(body)
    if errors:
        return key_occurrences, {}, errors, False

    if apply and merged_body != body:
        new_text = opening + merged_body + after
        try:
            path.write_text(new_text, encoding='utf-8')
        except OSError as exc:
            print(f'  WARN: cannot write {path}: {exc}', file=sys.stderr)
            return key_occurrences, values_deduped, [], False
        return key_occurrences, values_deduped, [], True
    return key_occurrences, values_deduped, [], False


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Fix duplicate top-level YAML keys in vault files.',
        epilog='See spec vault/files/81555e45.md v0.4 §3.1 for binding contract.',
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Walk + report; do not write (default).',
    )
    mode_group.add_argument(
        '--apply',
        action='store_true',
        default=False,
        help='Walk + report + write. Requires clean git working tree.',
    )
    parser.add_argument(
        '--scope',
        metavar='PATH',
        default=DEFAULT_SCOPE,
        help=f'Path under vault root to scan (default: {DEFAULT_SCOPE}).',
    )
    parser.add_argument(
        '--allow-dirty',
        action='store_true',
        default=False,
        help=(
            'Bypass the git-clean-tree precondition. Use ONLY when the vault '
            'is intentionally gitignored at a parent repo (e.g., the Studio '
            'inside tropo-ai/) AND you have an alternative rollback substrate '
            '(daily snapshots, separate backup regime, etc.). The precondition '
            "exists to protect rollback safety; this flag declares 'I know "
            "git is not my rollback substrate here; I have my own.'"
        ),
    )
    args = parser.parse_args()
    apply_mode = args.apply

    vault_root = _resolve_vault_root()
    scope_path = (vault_root / args.scope).resolve()

    if not scope_path.is_dir() or (
        vault_root not in scope_path.parents and scope_path != vault_root
    ):
        print(
            f'ERROR: --scope path invalid: {args.scope!r} '
            f'(resolved to {scope_path}; not a directory under vault root '
            f'{vault_root})',
            file=sys.stderr,
        )
        return 5

    print('=' * 70)
    print('fix-duplicate-yaml-keys.py — v1.29.0 Stream A')
    print('Purpose: collapse duplicate top-level YAML frontmatter keys in')
    print('         vault markdown files into single canonical block-style lists.')
    print(f'Vault root: {vault_root}')
    print(f'Scope:      {scope_path.relative_to(vault_root)}/')
    print(f'Mode:       {"APPLY (will write)" if apply_mode else "DRY-RUN (read-only)"}')
    print('=' * 70)

    if apply_mode and not args.allow_dirty:
        is_clean, status = _check_git_clean_tree(vault_root)
        if not is_clean:
            print(
                'ERROR: Refusing to --apply with dirty working tree. '
                "Stream A's recovery substrate IS git-checkout; clean the "
                'tree first OR use --dry-run OR pass --allow-dirty if the '
                'vault is gitignored at a parent repo and you have an '
                'alternative rollback substrate (e.g., daily snapshot backups).',
                file=sys.stderr,
            )
            if status:
                print(f'  git status output (first 500 chars):\n{status}', file=sys.stderr)
            return 4
    elif apply_mode and args.allow_dirty:
        print(
            'NOTICE: --allow-dirty active. Skipping git-clean-tree precondition. '
            'Operator declared alternative rollback substrate (vault is '
            'gitignored at parent or otherwise outside git tracking).'
        )

    # Walk + process
    files_walked = 0
    files_with_dups = 0
    total_key_occurrences_collapsed = 0
    total_values_deduped = 0
    files_written = 0
    files_with_errors: list[tuple[Path, list[str]]] = []

    for md_path in sorted(scope_path.rglob('*.md')):
        if not md_path.is_file():
            continue
        files_walked += 1
        key_occurrences, values_deduped, errors, wrote = _process_file(md_path, apply=apply_mode)
        if errors:
            files_with_errors.append((md_path, errors))
            continue
        if key_occurrences:
            files_with_dups += 1
            # Each key with N occurrences → 1 canonical entry → N-1 collapsed
            for key, count in key_occurrences.items():
                total_key_occurrences_collapsed += (count - 1)
            total_values_deduped += sum(values_deduped.values())
            rel = md_path.relative_to(vault_root)
            for key, count in sorted(key_occurrences.items()):
                action = 'merged' if (apply_mode and wrote) else 'WOULD merge'
                deduped_note = ''
                if key in values_deduped and values_deduped[key] > 0:
                    deduped_note = f'; {values_deduped[key]} duplicate value(s) deduped'
                print(f'  {rel}: {key} ({count} occurrences → 1 canonical entry {action}{deduped_note})')
            if wrote:
                files_written += 1

    # Summary
    print()
    print('=' * 70)
    print(
        f'Walked {files_walked} files; {files_with_dups} had duplicates; '
        f'{total_key_occurrences_collapsed} key occurrences collapsed '
        f'(merged duplicate top-level keys into 1 canonical entry per key); '
        f'{total_values_deduped} duplicate values deduped '
        f'(within-list value duplicates dropped on dedup); '
        f'{files_written} files written (only in --apply mode).'
    )
    if files_with_errors:
        print(f'  {len(files_with_errors)} file(s) requiring MANUAL RESOLUTION '
              f'(scalar-conflict OR in-list-comments — see per-file detail):')
        for path, errs in files_with_errors[:20]:
            rel = path.relative_to(vault_root)
            for err in errs:
                print(f'    {rel}: {err}')
        if len(files_with_errors) > 20:
            print(f'    ... and {len(files_with_errors) - 20} more')
    print('=' * 70)

    # Next-steps guidance — adapts to mode + presence of refuse-merge cases.
    print()
    print('Next steps:')
    if not apply_mode:
        # Dry-run mode
        if files_with_errors:
            print('  1. RESOLVE the manual-resolution files above:')
            print('     - For scalar-conflict: edit the file to retain a single')
            print('       value for the conflicting key, decided by the file owner')
            print('       (when in doubt, ask the principal). Then re-run --dry-run')
            print('       to confirm the file is no longer flagged.')
            print('     - For in-list-comments: either consolidate the duplicate key')
            print('       by hand (preserving the comments in their original')
            print('       positions), OR move the comments above the key so')
            print('       --apply can safely merge.')
            print('  2. RE-RUN this script with --dry-run to confirm 0 manual-resolution')
            print('     cases remain.')
            print('  3. RUN with --apply to mutate the substrate (requires clean git')
            print('     working tree; rollback substrate is git-checkout).')
            print('  4. POST-APPLY: run `npm run vault:rebuild` to confirm the')
            print('     platform-tier rebuild succeeds clean against the cleaned substrate.')
        elif files_with_dups:
            print('  1. RUN with --apply to mutate the substrate (requires clean git')
            print('     working tree; rollback substrate is git-checkout).')
            print('  2. POST-APPLY: run `npm run vault:rebuild` to confirm the')
            print('     platform-tier rebuild succeeds clean against the cleaned substrate.')
        else:
            print('  Substrate is clean — no action needed.')
    else:
        # Apply mode
        if files_with_errors:
            print('  1. The {n} manual-resolution file(s) above were SKIPPED — '
                  'merge would have lost data.'.format(n=len(files_with_errors)))
            print('  2. Resolve them manually (see scalar-conflict / in-list-comment')
            print('     guidance above); re-run --apply to clean the remainder.')
        elif files_written:
            print(f'  {files_written} file(s) written. Run `npm run vault:rebuild`')
            print('  to confirm the platform-tier rebuild succeeds clean.')
        else:
            print('  No changes needed — substrate was already clean.')
    print()

    if files_with_errors and apply_mode:
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
