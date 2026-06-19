#!/usr/bin/env python3
"""
---
uid: 4beff0d6
name: publish-check
type: tool
status: active
owner: talos
domain: "publish-check.py — Pre-publish readiness check for articles + ship-artifact wrappers."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/4beff0d6.py"
script_path: vault/tools/4beff0d6.py
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
publish-check.py — Pre-publish readiness check for articles + ship-artifact wrappers.

Composes the validator checks authored in tropo-validate.py + the publish.py
manifest-walker logic into a single user-facing command that answers:
"is this article ready to publish, and if not, what specifically is missing?"

Catches the source + wrapper substrate-coherence defect classes at preflight time
instead of production-404 time (Fires 1 + 3 from the v1.49.0 KGAE retrospective at
c5a7e391 §13.2). Fire 2 (publish.py platform-commit gap) is a runtime defect in
publish_targets/web.py covered by Talos's v1.49.0.1 patch; this script does NOT
verify Fire 2 at preflight.

Usage:
    publish-check.py <article-uid>           # check by source UID
    publish-check.py --slug <url-slug>       # check by slug (auto-resolves UID)
    publish-check.py <article-uid> --target web   # filter wrappers to one target

Exit codes:
    0  Article is ready to publish (all checks pass)
    1  Article has blocking defects (output names specific fixes + where to apply them)
    2  Article UID or slug not found in vault
    3  No wrapper found for article (script outputs a ready-to-paste wrapper scaffold)
"""


import argparse
import json
import os
import re
import sys

import yaml

# ─── Paths ───────────────────────────────────────────────────────────────────
# v1.56 Lane S: script relocated to vault/tools/; lib/ imports from .tropo/scripts/
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2] / '.tropo' / 'scripts')
VAULT_ROOT = os.path.dirname(os.path.dirname(_SCRIPTS_DIR))
VAULT_FILES = os.path.join(VAULT_ROOT, 'vault', 'files')
INDEX_PATH = os.path.join(VAULT_ROOT, 'vault', '00-index.jsonl')
PUBLISH_TARGETS_DIR = os.path.join(_SCRIPTS_DIR, 'publish_targets')

# Make lib/ importable (sibling of this script)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Shared rule logic per c5a7e391 §13.3 DRY-refactor (R1 paired-walk P1 absorption 2026-05-22)
from lib.article_readiness import (
    check_source_article_required_fields as _shared_source_check,
    check_wrapper_required_fields as _shared_wrapper_check,
)

# Known category UIDs for the web target — used in the wrapper-scaffold output
# so the user can copy-paste a working wrapper instead of guessing placeholder values.
# Per the live web manifest (4a99638d Tropo Website Content Structure):
WEB_CATEGORIES = {
    'articles':   ('4938b65a', 'Web Category: Articles (long-form posts; one folder per UID; index.md inside)'),
    'kb':         ('62823771', 'Web Category: KB Articles (knowledge-base entries; flat at kb/<uid>.md)'),
    'explainers': ('b72bd718', 'Web Category: Explainers (how-to guides; one folder per UID)'),
    'legal':      ('432d1f56', 'Web Category: Legal (terms / privacy; aggressive cleanup_rules)'),
}
WEB_MANIFEST_ROOT = '4a99638d'  # Tropo Website Content Structure manifest root


# ─── Output helpers (ANSI-color-when-tty + text-prefix-always) ───────────────

_IS_TTY = sys.stdout.isatty()

def _ok(msg: str) -> str:
    """Green checkmark in tty; [OK] prefix always."""
    if _IS_TTY:
        return f'\033[32m✓\033[0m [OK]   {msg}'
    return f'[OK]   {msg}'

def _fail(msg: str) -> str:
    if _IS_TTY:
        return f'\033[31m✗\033[0m [FAIL] {msg}'
    return f'[FAIL] {msg}'

def _warn(msg: str) -> str:
    if _IS_TTY:
        return f'\033[33m⚠\033[0m [WARN] {msg}'
    return f'[WARN] {msg}'


# ─── Frontmatter + index helpers ────────────────────────────────────────────

def _read_frontmatter(uid: str) -> dict | None:
    """Read vault/files/<uid>.md frontmatter; return parsed dict or None if not found.

    Distinguishes file-not-found (returns None) from malformed-YAML (returns sentinel
    {'_yaml_error': str}) so callers can give specific user feedback.
    """
    path = os.path.join(VAULT_FILES, f'{uid}.md')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        text = f.read()
    m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return {'_yaml_error': f'No YAML frontmatter found between --- markers in vault/files/{uid}.md'}
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        return fm if isinstance(fm, dict) else {'_yaml_error': 'Frontmatter parsed but not a dict'}
    except yaml.YAMLError as e:
        return {'_yaml_error': f'Malformed YAML: {e}'}


def _find_source_by_slug(slug: str) -> str | None:
    """Walk vault/00-index.jsonl for a subtype:article entry with matching slug."""
    if not os.path.exists(INDEX_PATH):
        return None
    with open(INDEX_PATH, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get('subtype') != 'article':
                continue
            if entry.get('slug') == slug:
                return entry['uid']
    return None


def _find_wrappers_for_source(source_uid: str, target: str | None = None) -> list[dict]:
    """Walk index for type=ship-artifact entries; read each frontmatter for canonical_source resolution.

    canonical_source: format accepts both "argo-os/vault/files/<uid>.md" and "vault/files/<uid>.md".
    Returns list of {'uid', 'fm'} dicts. If target is specified, filters to wrappers including that target.
    """
    matches = []
    if not os.path.exists(INDEX_PATH):
        return matches

    candidates = []
    with open(INDEX_PATH, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get('type') != 'ship-artifact':
                continue
            candidates.append(entry['uid'])

    for cand_uid in candidates:
        fm = _read_frontmatter(cand_uid)
        if fm is None or '_yaml_error' in fm:
            continue
        cs = fm.get('canonical_source', '')
        if not cs:
            continue
        m = re.search(r'([0-9a-f]{8})\.md$', cs)
        if not m or m.group(1) != source_uid:
            continue
        if target is not None:
            wrapper_target = fm.get('target', [])
            if isinstance(wrapper_target, str):
                wrapper_target = [wrapper_target]
            if target not in wrapper_target:
                continue
        matches.append({'uid': cand_uid, 'fm': fm})

    return matches


def _find_pipeline_for_wrapper(wrapper_fm: dict) -> str | None:
    """Find a publish-pipeline.md definition whose source matches this wrapper's manifest_root.

    Returns the pipeline UID if found, otherwise None. The success path uses this to name
    the next concrete command for the user instead of saying "find pipeline UID via index."
    """
    if not os.path.exists(INDEX_PATH):
        return None

    # Wrapper's manifest_root is the first member_of UID (per ship-artifact.capsule convention)
    member_of = wrapper_fm.get('member_of', [])
    if isinstance(member_of, str):
        member_of = [member_of]
    if not member_of:
        return None
    wrapper_manifest_root = member_of[0]

    with open(INDEX_PATH, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get('type') != 'publish-pipeline':
                continue
            # Read pipeline definition's selection_rules.manifest_root or source
            pipe_fm = _read_frontmatter(entry['uid'])
            if pipe_fm is None or '_yaml_error' in pipe_fm:
                continue
            sel = pipe_fm.get('selection_rules', {}) or {}
            sel_root = sel.get('manifest_root') or pipe_fm.get('source')
            if sel_root == wrapper_manifest_root:
                return entry['uid']

    return None


def _slug_collisions(slug: str, exclude_uid: str) -> list[str]:
    """Find other subtype:article entries with the same slug. Returns list of UIDs."""
    collisions = []
    if not os.path.exists(INDEX_PATH):
        return collisions
    with open(INDEX_PATH, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get('subtype') != 'article':
                continue
            if entry['uid'] == exclude_uid:
                continue
            if entry.get('slug') == slug:
                collisions.append(entry['uid'])
    return collisions


# ─── Check functions ────────────────────────────────────────────────────────

def check_source_article(source_uid: str, source_fm: dict) -> tuple[list[str], list[str]]:
    """Run article source required-fields checks via shared lib (v1.49.0.2 DRY refactor).

    Returns (findings, blocking). Field-presence rules live in lib/article_readiness.py
    (`check_source_article_required_fields`); this function adds CLI-output formatting
    (_fail/_warn/_ok glyphs + file-path hints).
    """
    findings = []
    blocking = []
    status = source_fm.get('status', '(unset)')

    # Informational WARN for drafts BEFORE shared check (shared check skips drafts silently;
    # CLI surfaces the WARN for user clarity)
    if status in ('draft', 'archived', 'recycled'):
        findings.append(_warn(
            f'source {source_uid} status:{status!r} — article is NOT in publish-ready state. '
            f'Publish-ready states: status:locked or status:active. (skipping publish-field checks)'
        ))

    result = _shared_source_check(source_uid, source_fm)

    if result.skipped:
        return findings, blocking  # shared check skipped; only WARN above stays

    for finding in result.findings:
        findings.append(_fail(finding + f' — fix at vault/files/{source_uid}.md'))

    blocking.extend(result.blocking)
    return findings, blocking


def check_wrapper(wrapper: dict) -> tuple[list[str], list[str]]:
    """Run ship-artifact wrapper required-fields checks via shared lib (v1.49.0.2 DRY refactor).

    Returns (findings, blocking). Delegates to lib/article_readiness.py.
    """
    findings = []
    wrapper_uid = wrapper['uid']
    result = _shared_wrapper_check(wrapper_uid, wrapper['fm'])

    for finding in result.findings:
        findings.append(_fail(finding + f' — fix at vault/files/{wrapper_uid}.md'))

    return findings, result.blocking


def check_target_module(target: str) -> tuple[list[str], list[str]]:
    """Verify the target's publish module exists."""
    findings = []
    blocking = []
    module_path = os.path.join(PUBLISH_TARGETS_DIR, f'{target}.py')
    if not os.path.exists(module_path):
        findings.append(_fail(
            f'target {target!r} has no module at .tropo/scripts/publish_targets/{target}.py — '
            f'publish.py will exit 3 at runtime. Author the target module before publishing.'
        ))
        blocking.append(f'target-module-{target}')
    return findings, blocking


def check_slug_collision(source_uid: str, source_fm: dict) -> list[str]:
    """Find other articles with the same slug (would collide at canonical URL)."""
    findings = []
    slug = source_fm.get('slug')
    if not slug:
        return findings
    collisions = _slug_collisions(str(slug), exclude_uid=source_uid)
    if collisions:
        findings.append(_fail(
            f'slug {slug!r} collides with other article(s): {", ".join(collisions)} — '
            f'change slug at vault/files/{source_uid}.md to a unique value'
        ))
    return findings


# ─── Main ────────────────────────────────────────────────────────────────────

def _print_wrapper_scaffold(source_uid: str, target: str, suggested_uid: str) -> None:
    """Print a ready-to-paste wrapper scaffold with actual category UIDs."""
    print()
    print(f'  To author a wrapper, create vault/files/{suggested_uid}.md with:')
    print()
    print(f'    ---')
    print(f'    uid: {suggested_uid}')
    print(f'    type: ship-artifact')
    print(f'    title: "Ship ({target}): <article title>"')
    print(f'    kind: file')
    print(f'    target: [{target}]')
    print(f'    canonical_source: argo-os/vault/files/{source_uid}.md')
    print(f'    source_mode: direct-copy')
    if target == 'web':
        print(f'    parent: 4938b65a   # Web Category: Articles (or one of:')
        for slug, (uid, desc) in WEB_CATEGORIES.items():
            print(f'                       #   {uid} = {desc}')
        print(f'    member_of:')
        print(f'      - "{WEB_MANIFEST_ROOT}"   # Tropo Website Content Structure (web manifest root)')
        print(f'      - "4938b65a"   # Web Category: Articles')
    else:
        print(f'    parent: <category-uid>  (target-specific; see capsule for valid categories)')
        print(f'    member_of: [<manifest-root-uid>, <category-uid>]')
    print(f'    ---')
    print(f'    # <article title>')
    print()
    print(f'  Then re-run: publish-check.py {source_uid} --target {target}')
    print()
    print(f'  Or skip the manual step entirely: publish-check.py {source_uid} --target {target} --create-wrapper')


def _create_wrapper(source_uid: str, source_fm: dict, target: str, category_uid: str,
                    category_name: str, manifest_root: str, force: bool) -> str | None:
    """Auto-author a ship-artifact wrapper for the source article.

    Returns the new wrapper UID on success, None on failure (e.g., user declined interactive
    confirm, or write fails). Mirrors the shape of working wrappers (89a649b5, 5404b989) per
    publish.pipeline.capsule v1.1 §3 + §5.

    The user-facing close-the-loop for the P4 polish item per c5a7e391 §13.3 — removes the
    manual wrapper-authoring gesture for the common case.

    Source-readiness gate (R1 paired-walk P0 absorption): refuses to auto-author when source
    article is NOT publish-ready (status not in {locked, active}). Prevents accidentally
    publishing draft articles by composing wrapper-auto-author + vault rebuild + publish.py.
    Per c5a7e391 §13.3 P4 spec verbatim: "when source has subtype:article + published_at."
    """
    import secrets
    from datetime import date

    # Source-readiness gate (P0 absorption from R1 paired-walk 2026-05-22)
    source_status = source_fm.get('status', '(unset)')
    if source_status not in ('locked', 'active'):
        print(f'  {_fail(f"Refusing to auto-author wrapper: source {source_uid} status:{source_status!r} is not publish-ready")}')
        print(f'  Per c5a7e391 §13.3 P4 spec: auto-author requires source `status: locked` or `status: active`.')
        print(f'  Fix source first at vault/files/{source_uid}.md, then re-run --create-wrapper.')
        return None
    if not source_fm.get('slug'):
        print(f'  {_fail(f"Refusing to auto-author wrapper: source {source_uid} missing required field `slug:`")}')
        print(f'  Per c5a7e391 §13.3 P4 spec: auto-author requires source has slug + published_at.')
        print(f'  Add slug to vault/files/{source_uid}.md, then re-run --create-wrapper.')
        return None
    if not source_fm.get('published_at'):
        print(f'  {_fail(f"Refusing to auto-author wrapper: source {source_uid} missing required field `published_at:`")}')
        print(f'  Per c5a7e391 §13.3 P4 spec: auto-author requires source has slug + published_at.')
        print(f'  Add published_at (YYYY-MM-DD) to vault/files/{source_uid}.md, then re-run --create-wrapper.')
        return None

    # Non-tty deadlock prevention (P1 absorption from R1 paired-walk)
    if not force and not sys.stdin.isatty():
        print(f'  {_fail("Refusing to prompt: stdin is not a tty + --force not set")}')
        print(f'  Re-run with --force to skip the interactive confirm in non-tty contexts (CI, pipelines, etc.).')
        return None

    new_uid = secrets.token_hex(4)
    title = source_fm.get('title', '(no title)')
    wrapper_path = os.path.join(VAULT_FILES, f'{new_uid}.md')
    today = date.today().isoformat()

    # Interactive confirm unless --force
    if not force:
        print()
        print(f'  About to author wrapper at vault/files/{new_uid}.md:')
        print(f'    title:            Ship ({target}): {title}')
        print(f'    canonical_source: argo-os/vault/files/{source_uid}.md')
        print(f'    target:           [{target}]')
        print(f'    parent:           {category_uid} ({category_name})')
        print(f'    member_of:        [{manifest_root}, {category_uid}]')
        try:
            response = input(f'  Proceed? [y/N]: ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            print('\n  Cancelled.')
            return None
        if response not in ('y', 'yes'):
            print('  Cancelled.')
            return None

    # Build frontmatter dict; serialize via yaml.safe_dump to handle YAML-special characters
    # in title/description (P0 absorption from R1 paired-walk — titles with " or : would
    # silently produce malformed YAML under f-string interpolation, recreating the silent-drop
    # class P4 was designed to close).
    frontmatter_dict = {
        'uid': new_uid,
        'type': 'ship-artifact',
        'title': f'Ship ({target}): {title}',
        'description': f'{target} extraction wrapper for source article {source_uid} ({title}). Authored by publish-check.py --create-wrapper.',
        'status': 'draft',
        'state': 'active',
        'owner': 'argus',
        'author': 'argus-a78',
        'created': today,
        'modified': today,
        'created_by': 'argus-a78',
        'modified_by': 'argus-a78',
        'schema_version': 2,
        'extraction_scope': 'argo-reference',
        'governed_by': 'eeb59ddf',
        'kind': 'file',
        'target': [target],
        'canonical_source': f'argo-os/vault/files/{source_uid}.md',
        'source_mode': 'direct-copy',
        'parent': category_uid,
        'member_of': [manifest_root, category_uid],
        'cleanup_rules': {
            'strip_nav_blocks': True,
            'strip_relations_table': True,
            'rewrite_uid_refs': True,
            'uid_rewrite_template': '/kb/<uid>',
            'broken_link_policy': 'strip',
        },
        'tags': ['ship-artifact', target, 'article', 'auto-authored-by-publish-check'],
    }
    # publication_state intentionally OMITTED here per R1 paired-walk P1 absorption — publish.py's
    # _platform_commit() (Talos v1.49.0.1 patch) authors it fresh at publish-time with the correct
    # `<target>: live` value. Pre-seeding `draft` would be benign but creates misleading "half-published"
    # appearance on disk. Aligns scaffold with working-wrapper shape (89a649b5 + 5404b989).

    frontmatter_yaml = yaml.safe_dump(frontmatter_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)
    content = f'''---
{frontmatter_yaml}---

# Ship ({target}): {title}

Wrapper for source article [{source_uid}](argo-os/vault/files/{source_uid}.md) — auto-authored by `publish-check.py --create-wrapper` on {today}. Body is a thin pointer; the publish.py extraction reads from `canonical_source` per ship-artifact.capsule v1.4 + publish.pipeline.capsule v1.1.
'''

    try:
        with open(wrapper_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f'  {_fail(f"Failed to write wrapper at {wrapper_path}: {e}")}')
        return None

    print()
    print(f'  {_ok(f"Wrapper authored at vault/files/{new_uid}.md")}')
    print(f'  Note: vault index rebuild required before publish.py can see the new wrapper.')
    print(f'  Run the Studio-native vault rebuild gesture (typically one of):')
    print(f'    python3 .tropo-studio/scripts/rebuild-vault.py        # canonical Tropo-native')
    print(f'    npm run vault:rebuild                                 # platform-dev alternate (if package.json available)')
    print(f'  Then re-run: publish-check.py {source_uid}')

    return new_uid


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Pre-publish readiness check for articles + ship-artifact wrappers. '
                    'Catches source + wrapper substrate-coherence defects at preflight time.',
    )
    parser.add_argument('source_uid', nargs='?', default=None,
                        help='8-hex UID of the source article to check (or use --slug)')
    parser.add_argument('--slug', default=None,
                        help='Look up source UID by article slug instead of supplying UID directly')
    parser.add_argument('--target', default=None,
                        help='Filter wrappers to a specific target (e.g., `web`)')
    parser.add_argument('--create-wrapper', action='store_true',
                        help='When no wrapper exists for the article, author one automatically '
                             '(interactive confirm unless --force; per c5a7e391 §13.3 P4)')
    parser.add_argument('--category', default=None,
                        help='Category UID for --create-wrapper (defaults to articles for target=web). '
                             'For target=web, valid choices: articles, kb, explainers, legal')
    parser.add_argument('--force', action='store_true',
                        help='With --create-wrapper, skip interactive confirm + write unconditionally')
    args = parser.parse_args()

    # Resolve source UID — by --slug lookup OR direct argument
    source_uid = args.source_uid
    if args.slug:
        if source_uid:
            print(f'Error: pass either source_uid OR --slug, not both', file=sys.stderr)
            return 2
        source_uid = _find_source_by_slug(args.slug)
        if not source_uid:
            print(f'{_fail(f"No subtype:article entry found with slug={args.slug!r} in vault/00-index.jsonl")}', file=sys.stderr)
            return 2

    if not source_uid:
        print(f'Error: must provide either source_uid argument or --slug <slug>', file=sys.stderr)
        parser.print_help(sys.stderr)
        return 2

    # Sanity-check UID shape
    if not re.fullmatch(r'[0-9a-f]{8}', source_uid):
        print(f'Error: {source_uid!r} is not an 8-hex UID — '
              f'find your article\'s UID by `grep -i "title-keyword" vault/00-index.jsonl` '
              f'or use --slug <slug>', file=sys.stderr)
        return 2

    # Read source article frontmatter
    source_fm = _read_frontmatter(source_uid)
    if source_fm is None:
        print(_fail(f'Source article {source_uid} not found at vault/files/{source_uid}.md'), file=sys.stderr)
        return 2
    if '_yaml_error' in source_fm:
        print(_fail(f'Source article {source_uid} frontmatter is malformed: {source_fm["_yaml_error"]}'), file=sys.stderr)
        print(f'  Fix the YAML at vault/files/{source_uid}.md and re-run.', file=sys.stderr)
        return 2

    print(f'\n=== publish-check.py — preflight for {source_uid} ===\n')
    print(f'Source: vault/files/{source_uid}.md')
    print(f'Title:  {source_fm.get("title", "(missing)")}')
    print(f'Status: {source_fm.get("status", "(unset)")}')
    print()

    all_blocking = []

    # Check 1: source article required fields
    print('--- Source article required fields ---')
    src_findings, src_blocking = check_source_article(source_uid, source_fm)
    if not src_findings:
        print(_ok('subtype:article + title + slug + published_at all present'))
    else:
        for line in src_findings:
            print(f'  {line}')
    all_blocking.extend(src_blocking)

    # Check 1b: slug collision (only if slug is present)
    slug_collision_findings = check_slug_collision(source_uid, source_fm)
    if slug_collision_findings:
        for line in slug_collision_findings:
            print(f'  {line}')
        all_blocking.append('slug-collision')

    # Check 2: find wrappers for this source
    print('\n--- Wrappers pointing at this source ---')
    wrappers = _find_wrappers_for_source(source_uid, target=args.target)
    if not wrappers:
        target_note = f' (filtered to target: {args.target})' if args.target else ''
        print(_fail(f'No ship-artifact wrapper found pointing at this source{target_note}'))

        target_for_action = args.target or 'web'

        # --create-wrapper path: author the wrapper automatically (interactive confirm unless --force)
        if args.create_wrapper:
            # Resolve category UID + human-readable name (used in interactive prompt)
            if args.category:
                # User passed --category; can be a slug ('articles') OR raw UID
                if args.category in WEB_CATEGORIES:
                    category_uid, category_desc = WEB_CATEGORIES[args.category]
                    category_name = category_desc.split('(')[0].strip()  # e.g., "Web Category: Articles"
                elif re.fullmatch(r'[0-9a-f]{8}', args.category):
                    category_uid = args.category
                    # Try to resolve human-readable name from one of the known categories
                    matched = [name for slug, (uid, name) in WEB_CATEGORIES.items() if uid == args.category]
                    category_name = matched[0].split('(')[0].strip() if matched else '(unknown category — verify UID is correct)'
                else:
                    print(_fail(f'--category {args.category!r} not a valid slug or 8-hex UID'))
                    print(f'  Valid slugs for target=web: {", ".join(WEB_CATEGORIES.keys())}')
                    return 1
            elif target_for_action == 'web':
                category_uid, category_desc = WEB_CATEGORIES['articles']
                category_name = category_desc.split('(')[0].strip()
            else:
                print(_fail(f'--category required for --create-wrapper when target!=web (got target={target_for_action})'))
                return 1

            # Manifest root — for web target, known; for other targets, --create-wrapper
            # not yet supported (use the scaffold output + hand-edit per fresh-reader R1 P1 absorption)
            if target_for_action == 'web':
                manifest_root = WEB_MANIFEST_ROOT
            else:
                print(_fail(f'--create-wrapper only supports target=web at v1.49.0.2'))
                print(f'  For target={target_for_action!r}: copy the scaffold output (re-run without --create-wrapper)')
                print(f'  and edit by hand. Future cycles (per c5a7e391 §13.6 maturity arc) extend --create-wrapper to other targets.')
                return 1

            new_wrapper_uid = _create_wrapper(source_uid, source_fm, target_for_action,
                                              category_uid, category_name, manifest_root, force=args.force)
            if new_wrapper_uid:
                return 0  # success; user must rebuild vault index + re-run check
            else:
                return 1  # source not publish-ready OR user declined OR write failed

        # No --create-wrapper: print scaffold + exit 3
        import secrets
        suggested_uid = secrets.token_hex(4)
        _print_wrapper_scaffold(source_uid, target_for_action, suggested_uid)
        return 3

    for w in wrappers:
        target_list = w['fm'].get('target', [])
        target_str = ', '.join(target_list) if isinstance(target_list, list) else str(target_list)
        print(_ok(f'Wrapper {w["uid"]} (target: {target_str})'))

    # Check 3: wrapper required fields
    print('\n--- Wrapper required fields ---')
    for w in wrappers:
        wrapper_findings, wrapper_blocking = check_wrapper(w)
        if not wrapper_findings:
            print(_ok(f'wrapper {w["uid"]} — all required fields present'))
        else:
            for line in wrapper_findings:
                print(f'  {line}')
        all_blocking.extend(wrapper_blocking)

    # Check 4: target module exists for each wrapper's target
    print('\n--- Target module presence ---')
    targets_seen = set()
    for w in wrappers:
        target_list = w['fm'].get('target', [])
        if isinstance(target_list, str):
            target_list = [target_list]
        if not isinstance(target_list, list):
            continue
        for t in target_list:
            if t in targets_seen:
                continue
            targets_seen.add(t)
            mod_findings, mod_blocking = check_target_module(t)
            if not mod_findings:
                print(_ok(f'target {t!r} module present at publish_targets/{t}.py'))
            else:
                for line in mod_findings:
                    print(f'  {line}')
            all_blocking.extend(mod_blocking)

    # Summary
    print('\n=== Summary ===')
    if not all_blocking:
        # Resolve pipeline UID for the user
        pipeline_uid = _find_pipeline_for_wrapper(wrappers[0]['fm'])
        print(_ok(f'READY — article {source_uid} can publish'))
        if pipeline_uid:
            print(f'\nTo publish (your specific pipeline UID resolved):')
            print(f'  python3 .tropo/scripts/publish.py {pipeline_uid}')
            print(f'\nDry-run first (recommended):')
            print(f'  python3 .tropo/scripts/publish.py {pipeline_uid} --dry-run')
        else:
            print(f'\nNo matching publish-pipeline.md definition found for the wrapper\'s manifest_root.')
            print(f'Author one or check vault/00-index.jsonl for `type:publish-pipeline` entries.')
        return 0
    else:
        unique_defects = sorted(set(all_blocking))
        print(_fail(f'NOT READY — {len(unique_defects)} blocking defect(s): {", ".join(unique_defects)}'))
        print(f'\nFix the items above (each line names the exact file + frontmatter field), then re-run.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
