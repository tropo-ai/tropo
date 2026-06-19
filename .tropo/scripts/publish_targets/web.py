"""
publish_targets/web.py — Web target implementation for publish.pipeline class.

stage():   Write extracted content to output directory + mirror to kb-content/
publish(): rsync → sentinel commit (pipeline-bot@argo-os) → git push → Vercel hook

Extracted from build-web-content.py steps 4-7 (Talos T9, 2026-05-22).
Parallel-run discipline: build-web-content.py remains operational until equivalence
is confirmed across a full publish run.

Sentinel convention (S0.1, Argus+Talos pair-call resolved 2026-05-22):
- Commit author = pipeline-bot@argo-os IS the publish-act event for web target
- Validator Check 27 v1.5 detects hand-edits via git-blame against this sentinel
- publication_state.web: live is written post-push as a derivative of the sentinel act

v1.49.0 S3 — web target implementation.
"""

from __future__ import annotations

import glob as _glob
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

_TARGETS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TARGETS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from publish_types import StageResult, PublishResult, PublishTargetError
from publish_targets._shared import ensure_dated_slot

# ─── Paths ───────────────────────────────────────────────────────────────────
VAULT_ROOT = os.path.dirname(os.path.dirname(_SCRIPTS_DIR))
PLATFORM_ROOT = os.path.dirname(VAULT_ROOT)

DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(PLATFORM_ROOT), 'tropo-ai-website-content')

VERCEL_DEPLOY_HOOK = (
    'https://api.vercel.com/v1/integrations/deploy/'
    'prj_wc43DbRDmWdCBWlQITc6CXTXt1BP/CY0jkfpW27'
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _resolve_output_dir(pipeline_def: dict) -> str:
    """Return output directory — from pipeline_def output_path or default."""
    output_path = pipeline_def.get('output_path', '')
    if output_path:
        return os.path.expanduser(output_path) if output_path.startswith('~') else output_path
    return DEFAULT_OUTPUT_DIR


def _source_uid_from_file(filepath: str) -> str | None:
    """Read the uid: field from a file's frontmatter — the canonical source UID."""
    try:
        with open(filepath, encoding='utf-8') as fh:
            content = fh.read()
        m = re.search(r'^uid:\s*([0-9a-f]{8})\s*$', content, re.MULTILINE)
        return m.group(1) if m else None
    except Exception:
        return None


def _bio_composition_field(wrapper_uid: str) -> str:
    """Read bio_composition field from wrapper vault entry frontmatter.
    Returns 'section_default' | 'custom_inline' | 'opt_out'. Defaults to section_default.

    Strips YAML inline `#` comments (per YAML spec). Prior regex captured the
    comment-tail as part of the value, breaking opt_out detection on wrappers
    carrying provenance comments (e.g. `opt_out   # per b7e4f192 ...`).
    Defect surfaced by metis-g61 2026-05-25 on Tropo Work + Studio Manifesto
    kb-content (both opt_out wrappers were getting bios appended).
    """
    wrapper_path = os.path.join(VAULT_ROOT, 'vault', 'files', f'{wrapper_uid}.md')
    try:
        with open(wrapper_path, encoding='utf-8') as fh:
            content = fh.read()
        m = re.search(r'^bio_composition:\s*([^\s#]+)', content, re.MULTILINE)
        return m.group(1).strip().strip('"\'') if m else 'section_default'
    except Exception:
        return 'section_default'


def _load_section_bio() -> str | None:
    """Load canonical bio text from 02-outbox/web/agentic-builders/03-design/bio.md.
    Returns the bio paragraph text (without surrounding blank lines), or None if not found.
    """
    bio_path = os.path.join(VAULT_ROOT, '02-outbox', 'web', 'agentic-builders', '03-design', 'bio.md')
    try:
        with open(bio_path, encoding='utf-8') as fh:
            content = fh.read()
        m = re.search(r'## Current bio[^\n]*\n\n(.+?)(?:\n\n---|\n\n##)', content, re.DOTALL)
        return m.group(1).strip() if m else None
    except Exception:
        return None


def _slug_from_file(filepath: str) -> str | None:
    """Read the slug: field from a file's frontmatter."""
    try:
        with open(filepath, encoding='utf-8') as fh:
            content = fh.read()
        m = re.search(r'^slug:\s*(.+?)\s*$', content, re.MULTILINE)
        return m.group(1).strip().strip('"\'') if m else None
    except Exception:
        return None


def _run_git(repo_path: str, args: list[str], capture: bool = False):
    """Run a git command in repo_path. Raises RuntimeError on non-zero exit."""
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


# ─── stage() ─────────────────────────────────────────────────────────────────

def stage(extracted_content: dict, pipeline_def: dict) -> StageResult:
    """
    Write extracted + cleaned content to output directory.

    extracted_content: {output_path: content_or_None}
    where None = create this directory (no file content).

    Also mirrors extracted content to platform repo's app/(web)/kb-content/
    so Vercel can read it without cross-repo cloning.

    Returns StageResult with output_paths and metadata['output_dir'].
    """
    dry_run: bool = pipeline_def.get('_dry_run', False)
    verbose: bool = pipeline_def.get('_verbose', False)

    output_dir = _resolve_output_dir(pipeline_def)

    if not dry_run:
        os.makedirs(output_dir, exist_ok=True)

    print(f'  Output dir: {output_dir}')

    output_paths: list[str] = []
    extracted_count = 0
    warnings: list[str] = []

    for output_path, content in extracted_content.items():
        dst = os.path.join(output_dir, output_path.lstrip('/'))

        if content is None:
            # Directory entry
            if not dry_run:
                os.makedirs(dst, exist_ok=True)
            if verbose:
                print(f'  [mkdir] {output_path}')
            extracted_count += 1
            continue

        # File entry
        if not dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'w', encoding='utf-8') as f:
                f.write(content)
        output_paths.append(dst)
        if verbose:
            print(f'  [write] {output_path}')
        extracted_count += 1

    # Mirror to platform repo kb-content/ (Vercel reads from here)
    kb_content_dir = os.path.join(PLATFORM_ROOT, 'app', '(web)', 'kb-content')
    if os.path.isdir(kb_content_dir) and not dry_run:
        # Single timestamp for this publish run — shared across all articles in the run.
        # Format: YYYY-MM-DDTHHMMSS (compact ISO 8601, no colons in time for filename safety).
        publish_run_ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%S')

        # Articles: articles/<wrapper-uid>/index.md → kb-content/<source-uid>.md
        # Also copies adjacent 03-design/ asset folder → public/agentic-builders/<slug>/03-design/
        # so SVG image refs (relative to the article URL) resolve correctly in Next.js.
        # Also writes dated-source package per 2f5e8c1a §The Folder Shape.
        # Also appends section-scope bio per b7e4f192 design lock (opt-out via bio_composition: opt_out).
        public_ab_dir = os.path.join(PLATFORM_ROOT, 'public', 'agentic-builders')
        section_bio = _load_section_bio()
        for idx in _glob.glob(os.path.join(output_dir, 'articles', '*', 'index.md')):
            wrapper_uid = os.path.basename(os.path.dirname(idx))
            uid = _source_uid_from_file(idx) or wrapper_uid
            # Sweep kb-content for stale files claiming the same slug (dual-write bug class).
            # Any file with matching slug but different UID-filename is a stale artifact
            # from a prior pipeline (e.g. build-web-content.py wrapper-uid naming).
            slug = _slug_from_file(idx)
            if slug:
                for existing in _glob.glob(os.path.join(kb_content_dir, '*.md')):
                    existing_name = os.path.basename(existing)
                    if existing_name == f'{uid}.md':
                        continue  # same file we're about to write — skip
                    existing_slug = _slug_from_file(existing)
                    if existing_slug == slug:
                        os.remove(existing)
                        if verbose:
                            print(f'  [sweep] removed stale {existing_name} (slug collision: {slug})')
            dst = os.path.join(kb_content_dir, f'{uid}.md')
            shutil.copy2(idx, dst)
            if verbose:
                print(f'  [mirror] articles/.../index.md → kb-content/{uid}.md')
            # Bio composition — append section-scope bio unless wrapper opts out (b7e4f192).
            bio_mode = _bio_composition_field(wrapper_uid)
            if bio_mode != 'opt_out' and section_bio:
                with open(dst, 'a', encoding='utf-8') as fh:
                    fh.write(f'\n\n---\n\n{section_bio}\n')
                if verbose:
                    print(f'  [bio] appended section bio → kb-content/{uid}.md')
            slug = _slug_from_file(idx)
            if slug:
                # Copy 03-design/ assets from outbox → public/agentic-builders/<slug>/03-design/
                outbox_design = os.path.join(
                    VAULT_ROOT, '02-outbox', 'web', 'agentic-builders', slug, '03-design'
                )
                if os.path.isdir(outbox_design):
                    pub_design = os.path.join(public_ab_dir, slug, '03-design')
                    if os.path.isdir(pub_design):
                        shutil.rmtree(pub_design)
                    shutil.copytree(outbox_design, pub_design)
                    asset_count = len([
                        f for f in os.listdir(pub_design)
                        if os.path.isfile(os.path.join(pub_design, f))
                    ])
                    if verbose:
                        print(f'  [assets] 03-design/ → public/agentic-builders/{slug}/03-design/ ({asset_count} files)')

                # Dated-source packaging: write cleaned extracted markdown to outbox
                # with run timestamp; archive any prior dated set to /versions/.
                # Per 2f5e8c1a §The Folder Shape — one dated .md per publish run.
                ab_folder = os.path.join(
                    VAULT_ROOT, '02-outbox', 'web', 'agentic-builders', slug
                )
                if os.path.isdir(ab_folder):
                    dated_path = ensure_dated_slot(ab_folder, slug, publish_run_ts, 'md')
                    with open(idx, 'r', encoding='utf-8') as fh:
                        cleaned = fh.read()
                    with open(dated_path, 'w', encoding='utf-8') as fh:
                        fh.write(cleaned)
                    if verbose:
                        print(f'  [dated-source] {os.path.basename(dated_path)} → 02-outbox/web/agentic-builders/{slug}/')
        # KB + legal: <subdir>/<uid>.md → kb-content/<uid>.md
        for subdir in ('kb', 'legal'):
            for f in _glob.glob(os.path.join(output_dir, subdir, '*.md')):
                uid = _source_uid_from_file(f) or os.path.basename(f).replace('.md', '')
                shutil.copy2(f, os.path.join(kb_content_dir, f'{uid}.md'))
                if verbose:
                    print(f'  [mirror] {subdir}/{os.path.basename(f)} → kb-content/{uid}.md')
    elif dry_run:
        print('  [stage] DRY RUN — would mirror to kb-content/')

    return StageResult(
        success=True,
        output_paths=output_paths,
        extracted_count=extracted_count,
        warnings=warnings,
        metadata={
            'output_dir': output_dir,
            'published_uids': pipeline_def.get('_published_uids', []),
        },
    )


# ─── publish() ───────────────────────────────────────────────────────────────

def _rsync(source_dir: str, repo_path: str, dry_run: bool = False, verbose: bool = False) -> None:
    """Rsync extracted content to repo_path with non-destructive invariants."""
    if not os.path.isdir(source_dir):
        print(f'  [rsync] Source dir missing: {source_dir} — skipping')
        return

    os.makedirs(repo_path, exist_ok=True)

    cmd = [
        'rsync', '-avr',
        '--delete',
        '--exclude=assets/',
        '--exclude=.git',
        '--exclude=_sync-state.jsonl',
        source_dir.rstrip('/') + '/',
        repo_path.rstrip('/') + '/',
    ]
    if dry_run:
        cmd.insert(2, '--dry-run')

    if verbose or dry_run:
        print(f'  [rsync] {" ".join(cmd)}')

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise PublishTargetError(f'rsync failed (exit {result.returncode})')

    print(f'  [rsync] Complete → {repo_path}')


def _git_commit(repo_path: str, extracted_count: int, cycle_context: str = '',
                dry_run: bool = False) -> bool:
    """Stage all changes and commit with sentinel identity. Returns True if committed."""
    if dry_run:
        print(f'  [commit] DRY RUN — would commit {extracted_count} article(s)')
        return False

    _run_git(repo_path, ['add', '--all'])

    status = _run_git(repo_path, ['status', '--porcelain'], capture=True)
    if not status.stdout.strip():
        print('  [commit] Nothing to commit — working tree clean')
        return False

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    subject = f'publish: {extracted_count} article(s) extracted {now}'
    body_lines = [
        'Extracted by: publish.py web target (pipeline-bot)',
        f'Articles: {extracted_count}',
        f'Timestamp: {now}',
    ]
    if cycle_context:
        body_lines.append(f'Context: {cycle_context}')

    _run_git(repo_path, [
        '-c', 'user.name=pipeline-bot',
        '-c', 'user.email=pipeline-bot@argo-os',
        'commit', '-m', subject + '\n\n' + '\n'.join(body_lines),
    ])
    print(f'  [commit] Sentinel commit: {subject}')
    return True


def _git_push_website(repo_path: str, dry_run: bool = False) -> None:
    """Push website-content sentinel to origin."""
    if dry_run:
        print('  [push] DRY RUN — would push website-content to origin')
        return
    print('  [push] Pushing website-content to origin...')
    _run_git(repo_path, ['push', 'origin', 'HEAD'])
    print('  [push] Pushed ✓')


def _fire_vercel_hook(dry_run: bool = False) -> None:
    """Fire Vercel deploy hook. Runs after platform repo is pushed so Vercel reads current content."""
    if dry_run:
        print('  [vercel] DRY RUN — would fire Vercel deploy hook')
        return
    print('  [vercel] Firing deploy hook...')
    result = subprocess.run(
        ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '-X', 'POST', VERCEL_DEPLOY_HOOK],
        capture_output=True, text=True,
    )
    status = result.stdout.strip()
    if status == '201':
        print('  [vercel] Deploy triggered ✓')
    else:
        print(f'  [vercel] Hook returned HTTP {status} — check Vercel dashboard')


def _update_publication_state(vault_file_path: str, target: str, state: str) -> None:
    """Update or add publication_state.<target>: <state> in vault file frontmatter."""
    with open(vault_file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    target_line = f'  {target}: {state}'

    if re.search(r'^publication_state:', content, re.MULTILINE):
        if re.search(rf'^  {target}:', content, re.MULTILINE):
            content = re.sub(
                rf'^(  {target}: ).*$',
                rf'\g<1>{state}',
                content, flags=re.MULTILINE,
            )
        else:
            content = re.sub(
                r'^(publication_state:)',
                rf'\1\n{target_line}',
                content, flags=re.MULTILINE,
            )
    else:
        content = re.sub(r'\n---\n', f'\npublication_state:\n{target_line}\n---\n', content, count=1)

    with open(vault_file_path, 'w', encoding='utf-8') as f:
        f.write(content)


def _platform_commit(
    published_uids: list[str],
    extracted_count: int,
    cycle_context: str = '',
    dry_run: bool = False,
    verbose: bool = False,
) -> bool:
    """
    Commit platform repo changes after a successful web publish.

    Gap 2 fix: stages app/(web)/kb-content/ changes written by stage().
    Gap 1 fix: updates publication_state.web: live on each wrapper UID file.

    Both go in one sentinel commit to PLATFORM_ROOT, then pushed.
    Returns True if a commit was made.
    """
    vault_files_dir = os.path.join(PLATFORM_ROOT, 'argo-os', 'vault', 'files')

    if dry_run:
        print(f'  [platform] DRY RUN — would update publication_state on {len(published_uids)} wrapper(s)')
        print('  [platform] DRY RUN — would commit + push platform repo (kb-content + wrappers)')
        return False

    # Update publication_state on each wrapper file (Gap 1)
    updated_wrappers: list[str] = []
    for uid in published_uids:
        wrapper_path = os.path.join(vault_files_dir, f'{uid}.md')
        if os.path.exists(wrapper_path):
            try:
                _update_publication_state(wrapper_path, 'web', 'live')
                updated_wrappers.append(f'argo-os/vault/files/{uid}.md')
                if verbose:
                    print(f'  [platform] publication_state.web = live -> {uid}.md')
            except Exception as e:
                print(f'  [platform] Warning: could not update {uid}.md: {e}')
        elif verbose:
            print(f'  [platform] Skipping {uid} — wrapper file not found')

    # Stage kb-content/ changes (Gap 2)
    _run_git(PLATFORM_ROOT, ['add', 'app/(web)/kb-content/'])

    # Stage article SVG assets (03-design/ folders copied by stage())
    _run_git(PLATFORM_ROOT, ['add', 'public/agentic-builders/'])

    # Stage updated wrapper files (Gap 1)
    for rel_path in updated_wrappers:
        _run_git(PLATFORM_ROOT, ['add', rel_path])

    status = _run_git(PLATFORM_ROOT, ['status', '--porcelain'], capture=True)
    if not status.stdout.strip():
        print('  [platform] Nothing to commit — platform repo already in sync')
        return False

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    subject = f'publish: sync kb-content + publication_state {now}'
    body_lines = [
        'Committed by: publish.py web target (pipeline-bot)',
        f'Articles: {extracted_count}',
        f'Timestamp: {now}',
        f'Wrappers updated: {len(updated_wrappers)}',
    ]
    if cycle_context:
        body_lines.append(f'Context: {cycle_context}')

    _run_git(PLATFORM_ROOT, [
        '-c', 'user.name=pipeline-bot',
        '-c', 'user.email=pipeline-bot@argo-os',
        'commit', '-m', subject + '\n\n' + '\n'.join(body_lines),
    ])
    print(f'  [platform] Committed: {subject}')

    print('  [platform] Pushing platform repo...')
    _run_git(PLATFORM_ROOT, ['push', 'origin', 'HEAD'])
    print('  [platform] Pushed ✓')

    return True


def publish(stage_result: StageResult, pipeline_def: dict) -> PublishResult:
    """
    Web target publish extension.

    Sequence (order is load-bearing — Vercel reads from platform repo):
    1. rsync — enforce non-destructive invariants (assets/ preserved)
    2. Sentinel commit to website-content repo (pipeline-bot@argo-os)
    3. Push website-content to origin (canonical archive)
    4. Platform commit — kb-content mirror + publication_state wrappers (Gaps 1+2 fix)
    5. Push platform repo (tropo-ai/tropo-ai)
    6. Fire Vercel deploy hook (reads from platform repo; must come after step 5)
    """
    dry_run: bool = pipeline_def.get('_dry_run', False)
    verbose: bool = pipeline_def.get('_verbose', False)
    cycle_context: str = pipeline_def.get('_cycle_context', '')
    output_dir: str = stage_result.metadata.get('output_dir', DEFAULT_OUTPUT_DIR)
    published_uids: list[str] = stage_result.metadata.get('published_uids', [])

    # 1. rsync
    try:
        _rsync(output_dir, output_dir, dry_run=dry_run, verbose=verbose)
    except PublishTargetError as e:
        return PublishResult(success=False, errors=[str(e)])

    # 2. Sentinel commit to website-content
    try:
        committed = _git_commit(
            output_dir,
            extracted_count=stage_result.extracted_count,
            cycle_context=cycle_context,
            dry_run=dry_run,
        )
    except RuntimeError as e:
        return PublishResult(success=False, errors=[str(e)])

    if not committed:
        print('  [publish] Skipped — nothing committed to website-content')
        return PublishResult(success=True, committed=False)

    # 3. Push website-content
    try:
        _git_push_website(output_dir, dry_run=dry_run)
    except RuntimeError as e:
        return PublishResult(success=False, committed=committed, errors=[str(e)])

    # 4+5. Platform commit (kb-content + publication_state) and push
    try:
        _platform_commit(
            published_uids=published_uids,
            extracted_count=stage_result.extracted_count,
            cycle_context=cycle_context,
            dry_run=dry_run,
            verbose=verbose,
        )
    except RuntimeError as e:
        print(f'\n  [platform] ERROR: platform commit/push failed: {e}')
        print('  [platform] Proceeding to Vercel hook — kb-content or publication_state may be stale')

    # 6. Vercel deploy hook (after platform push)
    _fire_vercel_hook(dry_run=dry_run)

    return PublishResult(success=True, committed=committed)
