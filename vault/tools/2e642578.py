#!/usr/bin/env python3
"""
---
uid: 2e642578
name: publish
type: tool
status: active
owner: talos
domain: "publish.py — Thin shared runner for publish.pipeline definitions."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/2e642578.py"
script_path: vault/tools/2e642578.py
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
from __future__ import annotations

"""
publish.py — Thin shared runner for publish.pipeline definitions.

Class core: load pipeline definition → extract + cleanup content from vault →
dispatch to target module stage() → call target publish() if defined.

Usage:
    python3 .tropo/scripts/publish.py <pipeline-uid-or-path> [options]

Arguments:
    pipeline-uid-or-path  8-hex vault UID (looked up via 00-index.jsonl) or direct file path

Options:
    --dry-run       Do not write files, commit, or push; print what would happen
    --verbose, -v   Print per-entry trace
    --no-publish    Skip target publish() (rsync + commit + push for web; no-op for docx)
    --cycle-context TEXT  One-line context for git commit message (web target)

Exit codes:
    0  Success
    1  Validation or extraction failure
    2  No entries found for selection_rules
    3  Target module not found
    4  Pipeline definition not found or invalid

v1.49.0 S2 — publish.pipeline class thin runner.
"""


import argparse
import importlib
import json
import os
import re
import sys

import yaml

# ─── Engine imports ──────────────────────────────────────────────────────────
# v1.56 Lane S: script relocated to vault/tools/; lib/ + publish_targets/ are under .tropo/scripts/
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))      # vault/tools/
VAULT_ROOT = os.path.dirname(os.path.dirname(_TOOLS_DIR))    # argo-os/
_SCRIPTS_DIR = os.path.join(VAULT_ROOT, '.tropo', 'scripts') # argo-os/.tropo/scripts/
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib.ship_extract import (
    load_manifest_entries,
    resolve_source_path,
    apply_cleanup_rules,
    validate_manifest_basic,
)
from publish_types import StageResult, PublishResult, PublishTargetError
INDEX_PATH = os.path.join(VAULT_ROOT, 'vault', '00-index.jsonl')


# ─── Pipeline definition loading ─────────────────────────────────────────────

def _parse_frontmatter(text: str) -> dict:
    """Extract and parse YAML frontmatter from a markdown file."""
    m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not m:
        raise ValueError('No YAML frontmatter found')
    return yaml.safe_load(m.group(1)) or {}


def _find_in_index(uid: str) -> str | None:
    """Look up a UID in 00-index.jsonl and return its vault file path."""
    if not os.path.exists(INDEX_PATH):
        return None
    with open(INDEX_PATH, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get('uid') == uid:
                    path = entry.get('path', '')
                    if path:
                        return os.path.join(VAULT_ROOT, path)
            except json.JSONDecodeError:
                continue
    return None


def load_pipeline_def(arg: str) -> dict:
    """
    Load a publish.pipeline.md definition from a vault UID or direct file path.
    Returns parsed frontmatter dict, validated for required fields.
    """
    # Determine file path
    if re.fullmatch(r'[0-9a-f]{8}', arg):
        # UID lookup
        file_path = _find_in_index(arg)
        if not file_path:
            # Fallback: try vault/files/<uid>.md directly
            file_path = os.path.join(VAULT_ROOT, 'vault', 'files', f'{arg}.md')
        if not os.path.exists(file_path):
            print(f'Error: pipeline UID {arg!r} not found in vault index or vault/files/', file=sys.stderr)
            sys.exit(4)
    else:
        # Direct path
        file_path = os.path.abspath(arg) if not os.path.isabs(arg) else arg
        if not os.path.exists(file_path):
            print(f'Error: pipeline file not found: {file_path}', file=sys.stderr)
            sys.exit(4)

    with open(file_path, encoding='utf-8') as f:
        text = f.read()

    try:
        pipeline_def = _parse_frontmatter(text)
    except ValueError as e:
        print(f'Error parsing pipeline definition at {file_path}: {e}', file=sys.stderr)
        sys.exit(4)

    # Validate required fields
    for required in ('target', 'source', 'selection_rules'):
        if required not in pipeline_def:
            print(f'Error: pipeline definition missing required field: {required!r}', file=sys.stderr)
            sys.exit(4)

    pipeline_def['_file_path'] = file_path
    return pipeline_def


# ─── Target module loading ────────────────────────────────────────────────────

def load_target_module(target_name: str):
    """
    Import and return the target module from publish_targets/<target>.py.
    Exit 3 with a clear message if not found.
    """
    module_path = os.path.join(_SCRIPTS_DIR, 'publish_targets', f'{target_name}.py')
    if not os.path.exists(module_path):
        print(
            f'Error: target module not found for target {target_name!r}\n'
            f'  Expected: {module_path}',
            file=sys.stderr,
        )
        sys.exit(3)

    try:
        return importlib.import_module(f'publish_targets.{target_name}')
    except ImportError as e:
        print(f'Error loading target module publish_targets.{target_name}: {e}', file=sys.stderr)
        sys.exit(3)


# ─── Class core: extract + cleanup ───────────────────────────────────────────

_PARENT_TO_SUBDIR = {
    '4938b65a': 'articles',
    '62823771': 'kb',
    'b72bd718': 'explainers',
    '432d1f56': 'legal',
}


def _derive_output_path(entry: dict) -> str:
    """Derive output path from entry's parent category when not explicitly declared."""
    parent = entry.get('parent', '')
    uid = entry['uid']
    subdir = _PARENT_TO_SUBDIR.get(parent)
    if not subdir:
        return ''
    mode = entry.get('source_mode', 'direct-copy')
    if mode in ('structure-only', 'explicit-children'):
        return f'{subdir}/'
    if subdir in ('articles', 'explainers'):
        return f'{subdir}/{uid}/index.md'
    return f'{subdir}/{uid}.md'


def _load_cross_target_uids() -> set[str]:
    """Load release-target UIDs for cross-target broken-link detection (P1-c preservation)."""
    try:
        from lib.ship_extract import load_manifest_entries, read_manifest_root_uid
        capsule_path = os.path.join(VAULT_ROOT, '.tropo', 'capsules', 'ship-artifact.capsule.md')
        release_root = read_manifest_root_uid(capsule_path, target='release')
        release_entries = load_manifest_entries(INDEX_PATH, VAULT_ROOT, release_root, target='release')
        return {e['uid'] for e in release_entries}
    except Exception:
        return set()


def extract_manifest_root(pipeline_def: dict, verbose: bool = False) -> dict[str, str | None]:
    """
    Extract content via manifest-root walk (web target pattern).

    Uses load_manifest_entries engine against the UID in selection_rules.manifest_root
    (or source if not set). Applies cleanup_rules per entry.

    Returns: {output_path: cleaned_content} where None = create this directory.
    """
    selection = pipeline_def.get('selection_rules', {})
    manifest_uid = selection.get('manifest_root') or pipeline_def.get('source')
    target_name = pipeline_def['target']

    entries = load_manifest_entries(INDEX_PATH, VAULT_ROOT, manifest_uid, target=target_name)
    if not entries:
        return {}

    validate_manifest_basic(entries, VAULT_ROOT, target=target_name)

    # Track wrapper UIDs for publication_state update (Gap 1 fix)
    published_uids: list[str] = pipeline_def.setdefault('_published_uids', [])

    target_uids = {e['uid'] for e in entries} | _load_cross_target_uids()
    if verbose:
        print(f'  Target UIDs for cleanup_engine: {len(target_uids)} (web + cross-target release)')

    extracted: dict[str, str | None] = {}
    skipped = 0

    for entry in entries:
        # Map canonical_source → path (Phase A entries use canonical_source, not path)
        if not entry.get('path') and entry.get('canonical_source'):
            cs = entry['canonical_source']
            entry['path'] = cs[len('argo-os/'):] if cs.startswith('argo-os/') else cs

        mode = entry.get('source_mode', '')
        output_path = entry.get('output_path', '') or _derive_output_path(entry)

        if not output_path or mode == 'skip':
            skipped += 1
            continue

        # Directory entries (structure-only or folder with explicit-children)
        if mode == 'structure-only':
            extracted[output_path] = None
            continue

        if entry.get('kind') == 'folder':
            if mode == 'explicit-children':
                extracted[output_path] = None
            continue

        # File entries
        if entry.get('kind') == 'file':
            src = resolve_source_path(entry, VAULT_ROOT)
            if not os.path.exists(src):
                cs = entry.get('canonical_source', '')
                src_alt = os.path.join(VAULT_ROOT, cs[len('argo-os/'):] if cs.startswith('argo-os/') else cs)
                src = src_alt if os.path.exists(src_alt) else src
            if not os.path.exists(src):
                if verbose:
                    print(f'  ✗ {entry["uid"]} — source not found: {src}')
                skipped += 1
                continue

            with open(src, encoding='utf-8') as f:
                content = f.read()

            cleaned = apply_cleanup_rules(content, entry, target=target_name, target_uids=target_uids)
            extracted[output_path] = cleaned
            published_uids.append(entry['uid'])

            if verbose:
                print(f'  [extract] {output_path}')

    return extracted


def extract_by_uids(pipeline_def: dict, uids: list[str], verbose: bool = False) -> dict[str, str | None]:
    """
    Extract specific vault files by UID list (docx target pattern).
    Reads raw markdown; applies basic nav-block + relations-table stripping.

    v1.49.0+ extension (per stress-test b3e9c4a7 finding 2026-05-24, metis-g60):
    For type:external-artifact entries, the vault projection is a STUB pointing at
    a source file (per import primitive Tier 1 — sidecar-canonical). Follow the
    source_path to read the actual source content; the projection body is not the
    canonical content for these entries. Composes import primitive with publish
    primitive — both v1.25.0 + v1.49.0 designed in different cycles; this is their
    first shared-substrate composition.
    """
    extracted: dict[str, str | None] = {}
    for uid in uids:
        file_path = os.path.join(VAULT_ROOT, 'vault', 'files', f'{uid}.md')
        if not os.path.exists(file_path):
            if verbose:
                print(f'  ✗ {uid} — vault file not found')
            continue
        with open(file_path, encoding='utf-8') as f:
            content = f.read()

        # Detect external-artifact projections + follow source_path for actual content.
        type_match = re.search(r'^type:\s*external-artifact\s*$', content, re.MULTILINE)
        source_match = re.search(r'^source_path:\s*["\']?([^"\'\n]+)["\']?\s*$', content, re.MULTILINE)
        external_artifact_followed = False
        if type_match and source_match:
            source_relpath = source_match.group(1).strip()
            source_fullpath = os.path.join(VAULT_ROOT, source_relpath)
            if os.path.exists(source_fullpath):
                with open(source_fullpath, encoding='utf-8') as f:
                    source_content = f.read()
                # Strip YAML frontmatter if the source file has it (most markdown sources do not, but be defensive).
                source_content = re.sub(r'^---\n.*?\n---\n+', '', source_content, count=1, flags=re.DOTALL)
                content = source_content
                external_artifact_followed = True
                if verbose:
                    print(f'  [extract] {uid}.md → external-artifact; source_path: {source_relpath}')
            elif verbose:
                print(f'  ✗ {uid} — source file not found at {source_fullpath}; falling back to projection body')

        # Strip vault substrate noise (nav-blocks + relations table); applies to both projection bodies + source content.
        content = re.sub(r'<!-- nav-block:start -->.*?<!-- nav-block:end -->\n*', '', content, flags=re.DOTALL)
        content = re.sub(r'\*\*Relations\*\*\n\n\|.*?\n(\n|$)', '', content, flags=re.DOTALL)
        extracted[f'{uid}.md'] = content
        if verbose and not external_artifact_followed:
            print(f'  [extract] {uid}.md')
    return extracted


def extract_by_type(pipeline_def: dict, types: list[str], verbose: bool = False) -> dict[str, str | None]:
    """
    Extract vault files matching given types (all matching, regardless of project).
    Basic cleanup applied. For richer filtering, use explicit_uids instead.
    """
    matching: list[str] = []
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get('type') in types and entry.get('status') not in ('archived', 'retracted'):
                        matching.append(entry['uid'])
                except json.JSONDecodeError:
                    continue
    if verbose:
        print(f'  Found {len(matching)} entries matching types {types}')
    return extract_by_uids(pipeline_def, matching, verbose=verbose)


def extract_content(pipeline_def: dict, verbose: bool = False) -> dict[str, str | None]:
    """
    Class core: extract and clean content from vault per pipeline definition.

    Dispatches to the appropriate extraction strategy based on selection_rules:
    - manifest_root: walk ship-artifact graph (web target pattern)
    - explicit_uids: load specific files by UID
    - all_files_of_type: query vault index by type

    Returns: {output_path: cleaned_content_or_None}
    where None signals a directory to create (no file content).
    """
    selection = pipeline_def.get('selection_rules', {})

    if 'manifest_root' in selection or (not selection and pipeline_def.get('source')):
        return extract_manifest_root(pipeline_def, verbose=verbose)
    elif 'explicit_uids' in selection:
        return extract_by_uids(pipeline_def, selection['explicit_uids'], verbose=verbose)
    elif 'all_files_of_type' in selection:
        return extract_by_type(pipeline_def, selection['all_files_of_type'], verbose=verbose)
    else:
        print(f'Error: unknown selection_rules shape: {list(selection.keys())}', file=sys.stderr)
        sys.exit(1)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='publish.py — shared runner for publish.pipeline definitions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('pipeline', metavar='pipeline-uid-or-path',
                        help='8-hex vault UID or direct path to publish.pipeline.md')
    parser.add_argument('--dry-run', action='store_true',
                        help='Do not write, commit, or push; print what would happen')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print per-entry extraction trace')
    parser.add_argument('--no-publish', action='store_true',
                        help='Skip target publish() (extraction + stage only)')
    parser.add_argument('--cycle-context', default='',
                        help='One-line context for git commit message (web target)')
    parser.add_argument('--mode', choices=['strict', 'standard', 'express'], default='standard',
                        help='Activation mode: strict (all gates), standard (default), express (minimum)')
    parser.add_argument('--target', default='',
                        help='Comma-separated target override (default: wrapper.target list)')
    parser.add_argument('--template', default='',
                        help='Template name override (default: pipeline_def.template)')
    args = parser.parse_args()

    dry_label = ' [DRY RUN]' if args.dry_run else ''
    print(f'=== publish.py{dry_label} ===\n')

    # Load pipeline definition
    pipeline_def = load_pipeline_def(args.pipeline)
    title = pipeline_def.get('title', pipeline_def.get('uid', args.pipeline))

    # Resolve target list — --target override OR wrapper.target (scalar or list)
    wrapper_targets = pipeline_def.get('target', [])
    if isinstance(wrapper_targets, str):
        wrapper_targets = [wrapper_targets]
    active_targets = (
        [t.strip() for t in args.target.split(',') if t.strip()]
        if args.target else wrapper_targets
    )
    if not active_targets:
        print('Error: no targets resolved — set target: in pipeline or pass --target', file=sys.stderr)
        return 1

    print(f'Pipeline: {title}')
    print(f'Mode:     {args.mode}')
    print(f'Targets:  {", ".join(active_targets)}')
    if args.template:
        print(f'Template: {args.template}')
    print()

    # Shared timestamp for this publish run (used by dated-source packaging across all targets)
    import time as _time
    publish_run_ts = _time.strftime('%Y-%m-%dT%H%M%S', _time.gmtime())

    # Inject shared runtime options into pipeline_def
    pipeline_def['_dry_run'] = args.dry_run
    pipeline_def['_verbose'] = args.verbose
    pipeline_def['_cycle_context'] = args.cycle_context
    pipeline_def['_mode'] = args.mode
    pipeline_def['_template'] = args.template or pipeline_def.get('template', '')
    pipeline_def['_publish_run_ts'] = publish_run_ts

    overall_exit = 0

    for target_name in active_targets:
        if len(active_targets) > 1:
            print(f'\n{"=" * 50}')
            print(f'Target: {target_name}')
            print(f'{"=" * 50}')

        # Per-target pipeline_def copy with target overridden
        tdef = dict(pipeline_def)
        tdef['target'] = target_name

        # Load target module
        target_module = load_target_module(target_name)

        # Class core: extract + cleanup
        print('--- Class core: extract ---')
        extracted = extract_content(tdef, verbose=args.verbose)

        if not extracted:
            print(f'\n⚠ No content extracted for target {target_name!r} — check selection_rules and vault index.')
            if len(active_targets) > 1:
                print(f'[{target_name}] Skipping — no content')
                overall_exit = max(overall_exit, 2)
                continue
            return 2

        file_entries = {k: v for k, v in extracted.items() if v is not None}
        dir_entries = {k for k, v in extracted.items() if v is None}
        print(f'Extracted: {len(file_entries)} files, {len(dir_entries)} directories\n')

        # Mode gate orchestrator (strict/standard/express — c8a47e91 v1.1)
        try:
            from publish_targets._gate_orchestrator import run_mode_gates
            if not run_mode_gates(extracted, tdef):
                if len(active_targets) > 1:
                    overall_exit = max(overall_exit, 1)
                    continue
                return 1
        except ImportError:
            pass  # gate orchestrator not available; proceed without gates

        # Stage (target design+format)
        print('--- Target: stage ---')
        try:
            stage_result = target_module.stage(extracted, tdef)
        except PublishTargetError as e:
            print(f'Stage error [{target_name}]: {e}', file=sys.stderr)
            if len(active_targets) > 1:
                overall_exit = max(overall_exit, 1)
                continue
            return 1

        if not stage_result.success:
            for err in stage_result.errors:
                print(f'  Error: {err}', file=sys.stderr)
            if len(active_targets) > 1:
                overall_exit = max(overall_exit, 1)
                continue
            return 1

        for warn in stage_result.warnings:
            print(f'  Warning: {warn}')
        print(f'Stage complete: {stage_result.extracted_count} entries written')

        # Publish (target extension, optional)
        if not args.no_publish and hasattr(target_module, 'publish'):
            print('\n--- Target: publish ---')
            try:
                publish_result = target_module.publish(stage_result, tdef)
            except PublishTargetError as e:
                print(f'Publish error [{target_name}]: {e}', file=sys.stderr)
                if len(active_targets) > 1:
                    overall_exit = max(overall_exit, 1)
                    continue
                return 1

            if not publish_result.success:
                for err in publish_result.errors:
                    print(f'  Error: {err}', file=sys.stderr)
                if len(active_targets) > 1:
                    overall_exit = max(overall_exit, 1)
                    continue
                return 1
        elif args.no_publish:
            print('\n[--no-publish] Skipping publish step')
        elif not hasattr(target_module, 'publish'):
            print(f'\n[{target_name}] No publish() defined — target stops at stage')

    print('\n=== Done ===')
    return overall_exit


if __name__ == '__main__':
    sys.exit(main())
