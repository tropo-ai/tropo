#!/usr/bin/env python3
"""
---
uid: 11f3ebd4
name: build-web-content
type: tool
status: active
owner: talos
domain: "Build the Tropo website-content extraction from the Argo vault."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/11f3ebd4.py"
script_path: vault/tools/11f3ebd4.py
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

"""
Build the Tropo website-content extraction from the Argo vault.

Reads ship-artifact entries with `target: [..., 'web', ...]` from the vault index
and extracts them to the tropo-ai-website-content repo working copy. The web target's
manifest root is `4a99638d` (Tropo Website Content Structure) per ship-artifact.capsule v1.3.

This is the WEB-TARGET equivalent of `build-release.py`:

- build-release.py extracts target='release' entries → release zip artifact
- build-web-content.py extracts target='web' entries → website-content repo working copy

Both scripts are THIN orchestrators over the shared engine at `.tropo/scripts/lib/ship_extract/`:

- manifest_walker (read_manifest_root_uid + load_manifest_entries) — walks the graph
- source_mode_dispatch (resolve_source_path + should_exclude_kernel) — applies source modes
- cleanup_engine (apply_cleanup_rules + apply_uid_rewrite_template) — transforms content
- validator (validate_manifest_basic) — verifies canonical_source resolves
- output_writer (sha256_file + copy_file + write_content) — writes to output target

v1.43.0 Stream D deliverable per brief [c47b9d82](../../vault/files/c47b9d82.md).
Authored 2026-05-18 by argus-a72 under Mike-A72 captain-mode authorization.

Usage:
    python3 .tropo/scripts/build-web-content.py [--output-dir PATH] [--dry-run] [--verbose]

Default --output-dir: ../tropo-ai-website-content/ (sibling-to-platform-repo convention;
the actual repo path is established by Talos web-deploy-3 operational lane post-v1.43 ship).

Exit codes:
    0  Success — content extracted to output dir
    1  Validation failure (engine validator FAIL on canonical_source resolution)
    2  No web-target ship-artifact entries found (substrate not yet authored for web target;
       expected pre-web-deploy-3; emit informative message + exit cleanly)
    3  Output directory error (missing, permission, etc.)
    64 EX_USAGE — capsule resolution failure (TBD manifest_root_uid, missing capsule)
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

# ─── lib/ship_extract/ engine (v1.43.0 Stream C; substrate UID c47b9d82) ────
# v1.56 Lane S: script relocated to vault/tools/; lib/ imports from .tropo/scripts/
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2] / '.tropo' / 'scripts')
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from lib.ship_extract import (
    read_manifest_root_uid,
    load_manifest_entries,
    resolve_source_path,
    apply_cleanup_rules,
    validate_manifest_basic,
    copy_file,
)
from lib.ship_extract.output_writer import write_content


# ─── Configuration ───────────────────────────────────────────────────────────

VAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLATFORM_ROOT = os.path.dirname(VAULT_ROOT)
INDEX_PATH = os.path.join(VAULT_ROOT, 'vault', '00-index.jsonl')
CAPSULE_PATH = os.path.join(VAULT_ROOT, '.tropo', 'capsules', 'ship-artifact.capsule.md')

# Default output: tropo-ai-website-content repo working copy (sibling to platform repo)
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(PLATFORM_ROOT), 'tropo-ai-website-content')

# Web target name (per ship-artifact.capsule v1.3 enum)
WEB_TARGET = 'web'


# ─── Pipeline Steps ──────────────────────────────────────────────────────────

def step_1_resolve_manifest_root():
    """Resolve the web target's manifest root UID via the engine."""
    web_root = read_manifest_root_uid(CAPSULE_PATH, target=WEB_TARGET)
    print(f'Web manifest root: {web_root}')
    return web_root


def step_2_load_entries(manifest_root_uid):
    """Load all web-target ship-artifact entries via the engine."""
    entries = load_manifest_entries(INDEX_PATH, VAULT_ROOT, manifest_root_uid, target=WEB_TARGET)
    print(f'Web entries loaded: {len(entries)}')
    return entries


def step_2b_load_cross_target_uids():
    """Load release-target UIDs for cross-target broken-link detection.

    P1-c absorption (sa.skeptic-108 R3 production-failure lens 2026-05-18):
    web-target ship-artifact entries may reference release-target UIDs (e.g., a web
    /kb/<uid> page citing a release-target capsule entry). cleanup_engine's
    broken_link_policy needs to know about cross-target UIDs so it doesn't
    false-positive on legitimate cross-target citations.

    Returns:
        Set of release-target UIDs to pass alongside web-target UIDs in target_uids set.
    """
    try:
        release_root = read_manifest_root_uid(CAPSULE_PATH, target='release')
        release_entries = load_manifest_entries(INDEX_PATH, VAULT_ROOT, release_root, target='release')
        return {e['uid'] for e in release_entries}
    except SystemExit:
        # If release manifest unresolvable, return empty set (graceful degradation)
        return set()


def step_3_validate(entries):
    """Validate canonical_source resolves for all extractable entries."""
    if not entries:
        return  # Nothing to validate; will emit informative message in main
    validate_manifest_basic(entries, VAULT_ROOT, target=WEB_TARGET)
    print(f'  ✓ Validation PASS — {len(entries)} entries resolved')


def step_4_extract(entries, output_dir, target_uids, dry_run=False, verbose=False):
    """Extract entries to output_dir, applying cleanup_engine transforms per entry.

    Source modes:
    - `direct-copy` — read source → apply cleanup → write content
    - `recursive-ship-all` — copy directory recursively (no per-file cleanup applied — file-level
       transformations happen on individual file entries that override under the folder)
    - `structure-only` — create directory; no file copy
    - `skip` — no-op
    - `explicit-children` — folder entry signals children ship; children resolved separately

    For web target: most entries are `direct-copy` of single markdown files; folder-tier
    entries are `explicit-children` or `structure-only` to scaffold the output tree.
    """
    # Category parent → output subdirectory (derived when output_path not in frontmatter)
    # Phase A entries were authored before output_path field was required — derive from parent.
    PARENT_TO_SUBDIR = {
        '4938b65a': 'articles',   # Web Category: Articles
        '62823771': 'kb',         # Web Category: KB Articles
        'b72bd718': 'explainers', # Web Category: Explainers
        '432d1f56': 'legal',      # Web Category: Legal
    }

    def derive_output_path(entry):
        """Derive output_path from parent category + uid when not explicitly set."""
        parent = entry.get('parent', '')
        uid = entry['uid']
        subdir = PARENT_TO_SUBDIR.get(parent)
        if not subdir:
            return ''
        mode = entry.get('source_mode', 'direct-copy')
        if mode in ('structure-only', 'explicit-children'):
            return f'{subdir}/'
        # Articles and explainers get a per-article subfolder with index.md
        if subdir in ('articles', 'explainers'):
            return f'{subdir}/{uid}/index.md'
        # KB and legal get a flat uid.md
        return f'{subdir}/{uid}.md'

    extracted = 0
    skipped = 0
    for entry in entries:
        # Map canonical_source → path so resolve_source_path finds the actual article file.
        # Wrappers store the source in canonical_source (e.g. "argo-os/vault/files/fbb13cca.md")
        # but the engine's resolve_source_path reads the `path` field. Without this mapping
        # the engine falls back to vault/files/<wrapper-uid>.md (the wrapper, not the article).
        if not entry.get('path') and entry.get('canonical_source'):
            cs = entry['canonical_source']
            entry['path'] = cs[len('argo-os/'):] if cs.startswith('argo-os/') else cs

        mode = entry.get('source_mode', '')
        output_path = entry.get('output_path', '') or derive_output_path(entry)
        if not output_path:
            if verbose:
                print(f'  ⚠ {entry["uid"]} — missing output_path; skipping')
            skipped += 1
            continue
        dst = os.path.join(output_dir, output_path.lstrip('/'))

        if mode == 'skip':
            skipped += 1
            continue

        if mode == 'structure-only':
            if not dry_run:
                os.makedirs(dst, exist_ok=True)
            if verbose:
                print(f'  [structure] {output_path}')
            extracted += 1
            continue

        # File-tier modes need source resolution + content transformation
        if entry.get('kind') == 'file':
            src = resolve_source_path(entry, VAULT_ROOT)
            if not os.path.exists(src):
                # Fallback to canonical_source directly if entry doesn't have uid-matched vault file
                cs = entry.get('canonical_source', '')
                if cs.startswith('argo-os/'):
                    src = os.path.join(VAULT_ROOT, cs[len('argo-os/'):])
                else:
                    src = os.path.join(VAULT_ROOT, cs)
            if not os.path.exists(src):
                if verbose:
                    print(f'  ✗ {entry["uid"]} — source not found: {src}')
                skipped += 1
                continue
            # Read + transform + write
            with open(src, 'r', encoding='utf-8') as f:
                content = f.read()
            transformed = apply_cleanup_rules(content, entry, target=WEB_TARGET, target_uids=target_uids)
            write_content(transformed, dst, dry_run=dry_run)
            if verbose:
                print(f'  [direct-copy] {output_path}')
            extracted += 1
        elif entry.get('kind') == 'folder':
            # Folder entries with explicit-children scaffold the tree; children land via their own entries
            if mode == 'explicit-children' and not dry_run:
                os.makedirs(dst, exist_ok=True)
            if verbose:
                print(f'  [folder/{mode}] {output_path}')
            extracted += 1

    print(f'\nExtracted: {extracted} entries')
    print(f'Skipped:   {skipped} entries')
    return extracted, skipped


# ─── Steps 5-7: Git publish ops (Stream B, v1.47.0) ─────────────────────────

def _run_git(repo_path: str, args: list[str], capture: bool = False):
    """Run a git command in repo_path. Raises on non-zero exit."""
    result = subprocess.run(
        ['git'] + args,
        cwd=repo_path,
        capture_output=capture,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() if capture else '(see above)'
        raise RuntimeError(f'git {args[0]} failed: {stderr}')
    return result


def step_5_rsync(source_dir: str, repo_path: str, dry_run: bool = False, verbose: bool = False) -> int:
    """
    Rsync extracted content from source_dir → repo_path.

    Non-destructive invariants:
    - assets/ subfolders are never overwritten by extraction (--exclude='assets/')
    - Files removed from source (retracted articles) are deleted in repo (--delete)
    - Dry-run mode uses rsync --dry-run for a safe preview
    """
    if not os.path.isdir(source_dir):
        print(f'  [step_5] Source dir does not exist: {source_dir} — skipping rsync')
        return 0

    os.makedirs(repo_path, exist_ok=True)

    cmd = [
        'rsync', '-avr',
        '--delete',                        # remove files retracted from web target
        '--exclude=assets/',               # preserve manual graphics / layout assets
        '--exclude=.git',
        '--exclude=_sync-state.jsonl',
        source_dir.rstrip('/') + '/',      # trailing slash = sync contents, not dir
        repo_path.rstrip('/') + '/',
    ]
    if dry_run:
        cmd.insert(2, '--dry-run')
    if not verbose:
        cmd = [c for c in cmd if c != '-av'] + ['--quiet'] if not dry_run else cmd

    if verbose or dry_run:
        print(f'  [step_5] rsync: {" ".join(cmd)}')

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f'rsync failed with exit code {result.returncode}')

    changed = result.returncode == 0
    print(f'  [step_5] Rsync complete → {repo_path}')
    return 1 if changed else 0


def step_6_git_commit(repo_path: str, extracted_count: int, cycle_context: str = '',
                      dry_run: bool = False) -> bool:
    """
    Stage all changes in repo_path and commit with a structured message.
    Returns True if a commit was made, False if nothing changed.

    Sentinel pattern: author is 'pipeline-bot' (build-web-content.py pipeline identity).
    Validator Check 27 (v1.5 ratchet) detects hand-edits via git-blame against this sentinel.
    """
    if dry_run:
        print(f'  [step_6] DRY RUN — would commit {extracted_count} article(s) to {repo_path}')
        return False

    # Stage everything
    _run_git(repo_path, ['add', '--all'])

    # Check if there's anything to commit
    status = _run_git(repo_path, ['status', '--porcelain'], capture=True)
    if not status.stdout.strip():
        print('  [step_6] Nothing to commit — working tree clean')
        return False

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    subject = f'publish: {extracted_count} article(s) extracted {now}'
    body_lines = [
        f'Extracted by: build-web-content.py (pipeline-bot)',
        f'Articles: {extracted_count}',
        f'Timestamp: {now}',
    ]
    if cycle_context:
        body_lines.append(f'Context: {cycle_context}')

    commit_msg = subject + '\n\n' + '\n'.join(body_lines)

    _run_git(repo_path, [
        '-c', 'user.name=pipeline-bot',
        '-c', 'user.email=pipeline-bot@argo-os',
        'commit', '-m', commit_msg,
    ])
    print(f'  [step_6] Committed: {subject}')
    return True


VERCEL_DEPLOY_HOOK = "https://api.vercel.com/v1/integrations/deploy/prj_wc43DbRDmWdCBWlQITc6CXTXt1BP/CY0jkfpW27"


def step_7_git_push(repo_path: str, dry_run: bool = False) -> None:
    """Push committed changes to origin then fire the Vercel deploy hook."""
    if dry_run:
        print('  [step_7] DRY RUN — would push to origin and trigger Vercel deploy')
        return

    print('  [step_7] Pushing to origin…')
    _run_git(repo_path, ['push', 'origin', 'HEAD'])
    print('  [step_7] Pushed')

    print('  [step_7] Firing Vercel deploy hook…')
    result = subprocess.run(
        ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '-X', 'POST', VERCEL_DEPLOY_HOOK],
        capture_output=True, text=True,
    )
    status = result.stdout.strip()
    if status == '201':
        print('  [step_7] Vercel deploy triggered ✓')
    else:
        print(f'  [step_7] Deploy hook returned HTTP {status} — check Vercel dashboard')


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Build web-target content extraction from Argo vault.')
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR,
                        help=f'Output directory / website-content working copy (default: {DEFAULT_OUTPUT_DIR})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Do not write files or commit; print what would happen')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print per-entry extraction trace')
    # Stream B flags (steps 5-7)
    parser.add_argument('--no-publish', action='store_true',
                        help='Skip steps 5-7 (rsync + git commit + push); extraction only')
    parser.add_argument('--cycle-context', default='',
                        help='One-line context string for the git commit message (e.g. "web-deploy-5 KG article")')
    args = parser.parse_args()

    print('=== Tropo Web-Content Build' + (' [DRY RUN]' if args.dry_run else '') + ' ===\n')

    # Step 1 — resolve manifest root
    web_root = step_1_resolve_manifest_root()

    # Step 2 — load entries
    entries = step_2_load_entries(web_root)

    if not entries:
        print('\n⚠ No web-target ship-artifact entries found in vault index.')
        print('   This is expected pre-web-deploy-3 — substrate authors web-target entries')
        print('   after v1.43 Stream D ships. The engine is ready; awaiting substrate.')
        return 2

    # Step 3 — validate
    step_3_validate(entries)

    # Step 4 — extract
    if not args.dry_run:
        os.makedirs(args.output_dir, exist_ok=True)
    print(f'\nOutput dir: {args.output_dir}\n')

    # Build target_uids set for broken_link_policy + uid_rewrite filtering
    # P1-c absorption (sa.skeptic-108 R3): include cross-target (release) UIDs so legitimate
    # web-→-release citations aren't false-positive-flagged broken.
    target_uids = {e['uid'] for e in entries}
    cross_target_uids = step_2b_load_cross_target_uids()
    target_uids = target_uids | cross_target_uids
    print(f'Target UIDs available for cleanup_engine: {len(target_uids)} (web + cross-target release)')

    extracted, _ = step_4_extract(entries, args.output_dir, target_uids, dry_run=args.dry_run, verbose=args.verbose)

    # Step 4b: mirror extracted content into platform repo's app/(web)/kb-content/
    # so Vercel can read it at build time without cross-repo cloning.
    # Transition pattern: website-content is canonical; kb-content is the Vercel mirror.
    kb_content_dir = os.path.join(PLATFORM_ROOT, 'app', '(web)', 'kb-content')
    if os.path.isdir(kb_content_dir):
        import shutil, glob as _glob, re as _re

        def source_uid_from_file(filepath):
            """Read the uid: field from frontmatter — this is the canonical source UID."""
            try:
                with open(filepath) as fh:
                    content = fh.read()
                m = _re.search(r'^uid:\s*([0-9a-f]{8})\s*$', content, _re.MULTILINE)
                return m.group(1) if m else None
            except Exception:
                return None

        def slug_from_file(filepath):
            """Read the slug: field from frontmatter."""
            try:
                with open(filepath) as fh:
                    content = fh.read()
                m = _re.search(r'^slug:\s*(.+?)\s*$', content, _re.MULTILINE)
                return m.group(1).strip().strip('"\'') if m else None
            except Exception:
                return None

        # Articles: articles/<wrapper-uid>/index.md → kb-content/<source-uid>.md
        # Also copies adjacent 03-design/ asset folder → public/agentic-builders/<slug>/03-design/
        # so SVG image refs (relative to the article URL) resolve correctly in Next.js.
        public_ab_dir = os.path.join(PLATFORM_ROOT, 'public', 'agentic-builders')
        for idx in _glob.glob(os.path.join(args.output_dir, 'articles', '*', 'index.md')):
            uid = source_uid_from_file(idx) or os.path.basename(os.path.dirname(idx))
            dst = os.path.join(kb_content_dir, f'{uid}.md')
            shutil.copy2(idx, dst)
            print(f'  [mirror] articles/…/index.md → kb-content/{uid}.md')
            # Copy 03-design/ assets from outbox → public/agentic-builders/<slug>/03-design/
            slug = slug_from_file(idx)
            if slug:
                outbox_design = os.path.join(
                    VAULT_ROOT, '02-outbox', 'web', 'agentic-builders', slug, '03-design'
                )
                if os.path.isdir(outbox_design):
                    pub_design = os.path.join(public_ab_dir, slug, '03-design')
                    if os.path.isdir(pub_design):
                        shutil.rmtree(pub_design)
                    shutil.copytree(outbox_design, pub_design)
                    asset_count = len([f for f in os.listdir(pub_design) if os.path.isfile(os.path.join(pub_design, f))])
                    print(f'  [assets] 03-design/ → public/agentic-builders/{slug}/03-design/ ({asset_count} files)')
        # KB: kb/<uid>.md → kb-content/<uid>.md
        for f in _glob.glob(os.path.join(args.output_dir, 'kb', '*.md')):
            uid = source_uid_from_file(f) or os.path.basename(f)
            dst_name = uid if uid.endswith('.md') else f'{uid}.md'
            shutil.copy2(f, os.path.join(kb_content_dir, dst_name))
            print(f'  [mirror] kb/{os.path.basename(f)} → kb-content/{dst_name}')
        # Legal: legal/<uid>.md → kb-content/<uid>.md
        for f in _glob.glob(os.path.join(args.output_dir, 'legal', '*.md')):
            uid = source_uid_from_file(f) or os.path.basename(f)
            dst_name = uid if uid.endswith('.md') else f'{uid}.md'
            shutil.copy2(f, os.path.join(kb_content_dir, dst_name))
            print(f'  [mirror] legal/{os.path.basename(f)} → kb-content/{dst_name}')

    # Steps 5-7: publish (rsync → commit → push)
    # Skipped if --no-publish, --dry-run stops at step 5 rsync preview.
    if not args.no_publish:
        print('\n─── Publish pipeline (steps 5-7) ───')

        # Step 5 — rsync extracted content to website-content working copy
        # (When output-dir IS the working copy, rsync is a no-op sync pass that
        #  enforces non-destructive invariants: no clobbering assets/, removes retractions.)
        step_5_rsync(args.output_dir, args.output_dir, dry_run=args.dry_run, verbose=args.verbose)

        # Step 6 — commit
        committed = step_6_git_commit(
            args.output_dir,
            extracted_count=extracted,
            cycle_context=args.cycle_context,
            dry_run=args.dry_run,
        )

        # Step 7 — push
        if committed:
            step_7_git_push(args.output_dir, dry_run=args.dry_run)
        else:
            print('  [step_7] Skipped — nothing committed')

    print('\n=== Build complete ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
