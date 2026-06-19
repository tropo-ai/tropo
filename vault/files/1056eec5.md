#!/usr/bin/env python3
"""
---
uid: 1056eec5
name: tropo-register-template
type: tool
title: tropo-register-template
description: Register a user-uploaded .docx as a governed template for use with tropo-export.py --template <uid>. Validates slug regex; discriminates 3-state slug collision (clean / registered / binary-present-but-unregistered); copies binary to .tropo-studio/templates/<slug>.docx; extracts style metadata via shared office_styles library; authors docx-template entry with full §3.3 + §3.4 schema; inline index sync; supersession chain on --force.
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
domain: Register a user-uploaded Word template as a governed docx-template. The format-reference half of the v1.28.0 export gesture — pairs with tropo-export.py --template <uid> for transformation export.
spawnable_by:
- all-executives
- user
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/1056eec5.py --path <path-to-docx> --name <slug> [--description "..."] [--use-case "..."] [--force]
script_path: vault/tools/1056eec5.py
language: python
version: 1.0.0
destructive: 'true'
audit_required: 'true'
writes_scope:
- .tropo-studio/templates/**
- vault/files/**
- vault/00-index.jsonl
- .tropo-studio/reconciler/journal.jsonl
reads_scope:
- '**/*.docx'
governance_category: lifecycle
domain_tags:
- template
- registration
- docx
- format-reference
- user-uploaded
- v1.28.0-stream-b
- mcp-aligned
trigger_description: 'Reach for this when a user wants to register a Word template for transformation-export use. The user supplies the .docx path + a lowercase-hyphenated slug ([a-z0-9-]+). Tool copies the binary to .tropo-studio/templates/<slug>.docx, extracts style metadata via the shared office_styles library, and authors a governed docx-template entry. Slug-collision discrimination: ''registered'' (refuse unless --force; predecessor flips state:archived with supersedes: chain), ''binary-present-but-unregistered'' (refuse unless --force = overwrite), ''clean'' (proceed). Templates are USER-uploaded only — Tropo doesn''t author templates per Mike-A55 LOAD-BEARING ''don''t substrate-engineer creative-class authoring'' pin.'
governed_by: d5e1b4a3
capsule_version: '2.5'
informs_capsules:
- 7273cc6f
aligned_with:
- 5a89297a
tags:
- tool
- cli
- python
- tropo-register-template
- template-registration
- docx-format-reference
- user-facing
- mcp-aligned
- v1.28.0-stream-b
file_ext: md
subsystem_hub:
- 76bab75f
---
"""
from __future__ import annotations

"""Tropo template registration — user-facing CLI for Word template governance.

Registers a user-uploaded .docx as a governed docx-template per arch-spec
[5a89297a v0.5](../../vault/files/5a89297a.md) §3.3 + §3.4 + §3.6 + §3.10 + §3.11 item 2.

Usage:
    tropo-register-template.py --path <path-to-docx> --name <slug> \\
        [--description "..."] [--force] [--template-uid <uid>] \\
        [--run-uid <uid>] [--executive <slug>]

Behavior:
  1. Validates preconditions (path resolves to .docx; slug regex; collision discrimination).
  2. Acquires reconciler lock (library-mode composition per arch-spec §3.12).
  3. Copies source .docx to .tropo-studio/templates/<slug>.docx (overwrite on --force).
  4. SHA-256 the copy.
  5. Calls extract_office_styles() from .tropo/scripts/office_styles.py (v0.5: shared module).
  6. Mints template UID (or uses --template-uid override).
  7. Authors template entry at vault/files/<template-uid>.md per docx-template.capsule v1.0.
  8. Inline-syncs vault/00-index.jsonl per arch-spec §3.10 check 4.
  9. Appends `template_registered` journal event.
 10. Releases lock; emits stdout the template UID + slug.

Author: argus-a62
Owner: argus
Spec: vault/files/5a89297a.md (Working-Copy + Template Registration + Format-Only Export Arch-Spec v0.5 LOCKED)
v1.28.0 Stream B deliverable.
"""


import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path


TOOL_NAME = 'tropo-register-template'
TOOL_VERSION = '1.0.1'   # v1.0.0 = v1.28.0 ship; v1.0.1 = v1.32.0 Stream E P1-5
                          # closure (extracted_styles body-table N more count; capsule
                          # docx-template body convention amended per spec [900d41e0]
                          # §3.4 v0.4 LOCKED)

SLUG_RE = re.compile(r'^[a-z0-9-]+$')

# Substrate paths
LOCK_RELPATH = '.tropo-studio/reconciler/.lock'
JOURNAL_RELPATH = '.tropo-studio/reconciler/journal.jsonl'
TEMPLATES_RELPATH = '.tropo-studio/templates'
VAULT_INDEX_RELPATH = 'vault/00-index.jsonl'
LOCK_STALE_SECONDS = 3600


# Shared modules — same .tropo/scripts/ directory
# v1.56 Lane S: script relocated to vault/tools/; lib/ imports from .tropo/scripts/
_SCRIPT_DIR = Path(__file__).resolve().parents[2] / '.tropo' / 'scripts'
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# office_styles migrated to vault/tools/d1f2420d.py at the v1.56 script migration;
# the bare same-name import broke (fixed in export ce9dbcc2 + walker bf886f30 by
# metis-g62 2026-05-27; this tool was missed — fixed metis-g77 2026-06-12 on
# first real use, surfaced by Mike's template-library test).
import importlib.util as _importlib_util  # noqa: E402
_os_path = Path(__file__).parent / 'd1f2420d.py'
if not _os_path.exists():
    raise ImportError(f"office_styles not present at {_os_path} (UID d1f2420d per v1.56 migration)")
_os_spec = _importlib_util.spec_from_file_location('office_styles', _os_path)
office_styles = _importlib_util.module_from_spec(_os_spec)
_os_spec.loader.exec_module(office_styles)


# ==========================================================================
# Helpers
# ==========================================================================

def resolve_studio_root(arg_path=None):
    """Find Studio root: explicit arg, or walk up from cwd looking for .tropo/."""
    if arg_path:
        p = Path(arg_path).resolve()
        if (p / '.tropo').exists():
            return p
        raise SystemExit(f"--studio-root {arg_path} is not a Studio root (no .tropo/)")
    p = Path.cwd().resolve()
    while p != p.parent:
        if (p / '.tropo').exists():
            return p
        p = p.parent
    raise SystemExit("Not inside a Tropo Studio (no .tropo/ found walking up from cwd)")


def now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def now_date():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def generate_uid():
    """Mint an 8-hex UID."""
    return secrets.token_hex(4)


def _yaml_str(s):
    """Quote a string for YAML safety. Mirrors import-walker.py convention."""
    if s is None:
        return '""'
    s = str(s)
    if any(c in s for c in '\n\t:"\'#&*!|>%@`'):
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if s in ('true', 'false', 'null', 'yes', 'no', '~') or s == '' or s[0].isdigit():
        return '"' + s + '"'
    return '"' + s + '"'


# ==========================================================================
# Reconciler lock — library-mode composition per arch-spec §3.12
# ==========================================================================

class ReconcilerLock:
    """Acquire the shared reconciler lock per arch-spec §3.12.

    Single in-process acquisition; internal library calls do NOT re-acquire.
    Stale locks (mtime > LOCK_STALE_SECONDS) are overridden with a WARN.
    Lock file contents: pid + iso-timestamp + executive_slug.
    """
    def __init__(self, studio_root, executive='cli-user'):
        self.studio_root = studio_root
        self.lock_path = studio_root / LOCK_RELPATH
        self.executive = executive

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Stale-lock check
        if self.lock_path.exists():
            try:
                age = (datetime.now().timestamp() -
                       self.lock_path.stat().st_mtime)
                if age > LOCK_STALE_SECONDS:
                    print(f"WARN: overriding stale reconciler lock "
                          f"(age {age:.0f}s, holder: {self.lock_path.read_text().strip()})",
                          file=sys.stderr)
                    self.lock_path.unlink()
                else:
                    raise SystemExit(
                        f"Reconciler lock held: {self.lock_path.read_text().strip()} "
                        f"(age {age:.0f}s; stale threshold {LOCK_STALE_SECONDS}s). "
                        f"Wait + retry, or override manually."
                    )
            except OSError:
                pass
        # Acquire
        try:
            fd = os.open(str(self.lock_path),
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {now_iso()} {self.executive}".encode())
            os.close(fd)
        except FileExistsError:
            raise SystemExit(f"Reconciler lock race detected at {self.lock_path}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.lock_path.unlink()
        except OSError:
            pass


# ==========================================================================
# Slug-collision discrimination per arch-spec §3.6 precondition 3
# ==========================================================================

def discriminate_slug_state(studio_root, slug):
    """Return one of: 'clean' / 'registered' / 'binary-present-but-unregistered'.

    Per arch-spec §3.6 precondition 3:
    - 'registered' — vault/files/<uid>.md with type:docx-template AND slug:<slug> exists
    - 'binary-present-but-unregistered' — .tropo-studio/templates/<slug>.docx exists BUT
      no registry entry references the slug
    - 'clean' — neither registry entry nor binary present

    Returns tuple (state, existing_uid_or_none).
    """
    binary_path = studio_root / TEMPLATES_RELPATH / f'{slug}.docx'

    # Walk vault/files/ for an active docx-template entry with this slug
    vault_files = studio_root / 'vault' / 'files'
    existing_uid = None
    if vault_files.exists():
        for md_file in vault_files.glob('*.md'):
            try:
                with md_file.open('r') as f:
                    head = f.read(2048)
                if (f'type: docx-template' in head
                        and f'slug: "{slug}"' in head
                        and 'state: active' in head):
                    existing_uid = md_file.stem
                    break
                # Also handle unquoted slug
                if (f'type: docx-template' in head
                        and re.search(rf'^slug:\s*{re.escape(slug)}\s*$', head, re.MULTILINE)
                        and 'state: active' in head):
                    existing_uid = md_file.stem
                    break
            except (OSError, UnicodeDecodeError):
                continue

    if existing_uid:
        return ('registered', existing_uid)
    if binary_path.exists():
        return ('binary-present-but-unregistered', None)
    return ('clean', None)


# ==========================================================================
# .docx validation per arch-spec §3.6 Failure modes
# ==========================================================================

def validate_docx(path):
    """Validate a file is a well-formed .docx (ZIP + word/document.xml present).

    Per arch-spec §3.6 Failure modes: "Source file not a .docx (validated by
    ZIP signature + word/document.xml presence) → fail with explicit
    'not a valid Word document' message."

    Returns True on valid; raises SystemExit on invalid.
    """
    if not path.exists():
        raise SystemExit(f"Source file does not exist: {path}")
    if not path.is_file():
        raise SystemExit(f"Source is not a regular file: {path}")
    if path.suffix.lower() != '.docx':
        raise SystemExit(f"Source is not a .docx (suffix mismatch): {path}")
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            if 'word/document.xml' not in zf.namelist():
                raise SystemExit(
                    f"Source is not a valid Word document (missing word/document.xml): {path}"
                )
    except zipfile.BadZipFile:
        raise SystemExit(f"Source is not a valid Word document (corrupt ZIP): {path}")
    return True


# ==========================================================================
# Author docx-template vault entry per arch-spec §3.3 + §3.4
# ==========================================================================

def _render_extracted_styles_yaml(styles_dict):
    """Render extracted_styles dict as indented YAML for frontmatter.

    Mirrors the shape import-walker.py uses for original_styles (same §3.4 schema;
    different field name per arch-spec v0.5 RC-2 semantics-driven asymmetry).
    """
    lines = ['extracted_styles:']
    page = styles_dict.get('page', {})
    lines.append('  page:')
    lines.append(f'    width_dxa: {page.get("width_dxa", 12240)}')
    lines.append(f'    height_dxa: {page.get("height_dxa", 15840)}')
    lines.append(f'    orientation: {_yaml_str(page.get("orientation", "portrait"))}')
    lines.append('    margins_dxa:')
    margins = page.get('margins_dxa', {})
    for k in ('top', 'bottom', 'left', 'right'):
        lines.append(f'      {k}: {margins.get(k, 1440)}')
    df = styles_dict.get('default_font', {})
    lines.append('  default_font:')
    lines.append(f'    family: {_yaml_str(df.get("family", "Calibri"))}')
    lines.append(f'    size_half_pt: {df.get("size_half_pt", 22)}')
    lines.append(f'    color: {_yaml_str(df.get("color", "000000"))}')
    theme = styles_dict.get('theme', {})
    lines.append('  theme:')
    lines.append(f'    primary_color: {_yaml_str(theme.get("primary_color", "1F497D"))}')
    lines.append(f'    secondary_color: {_yaml_str(theme.get("secondary_color", "4F81BD"))}')
    named = styles_dict.get('named_styles') or []
    lines.append('  named_styles:')
    if not named:
        lines.append('    []')
    else:
        for s in named:
            lines.append(f'    - id: {_yaml_str(s.get("id", ""))}')
            if 'name' in s:
                lines.append(f'      name: {_yaml_str(s["name"])}')
            if 'font_family' in s:
                lines.append(f'      font_family: {_yaml_str(s["font_family"])}')
            if 'font_size_half_pt' in s:
                lines.append(f'      font_size_half_pt: {s["font_size_half_pt"]}')
            if 'bold' in s:
                lines.append(f'      bold: {"true" if s["bold"] else "false"}')
            if 'color' in s:
                lines.append(f'      color: {_yaml_str(s["color"])}')
            if 'spacing_before' in s:
                lines.append(f'      spacing_before: {s["spacing_before"]}')
            if 'spacing_after' in s:
                lines.append(f'      spacing_after: {s["spacing_after"]}')
    hf = styles_dict.get('headers_footers', {})
    lines.append('  headers_footers:')
    lines.append(f'    has_header: {"true" if hf.get("has_header") else "false"}')
    lines.append(f'    has_footer: {"true" if hf.get("has_footer") else "false"}')
    htp = hf.get('header_text_preview')
    ftp = hf.get('footer_text_preview')
    lines.append(f'    header_text_preview: {_yaml_str(htp) if htp else "null"}')
    lines.append(f'    footer_text_preview: {_yaml_str(ftp) if ftp else "null"}')
    lines.append(f'  sections_count: {styles_dict.get("sections_count", 1)}')
    sf = styles_dict.get('special_features', {})
    lines.append('  special_features:')
    lines.append(f'    has_macros: {"true" if sf.get("has_macros") else "false"}')
    lines.append(f'    has_embedded_fonts: {"true" if sf.get("has_embedded_fonts") else "false"}')
    lines.append(f'    has_custom_xml: {"true" if sf.get("has_custom_xml") else "false"}')
    lines.append(f'    has_watermark: {"true" if sf.get("has_watermark") else "false"}')
    return '\n'.join(lines)


def _render_extracted_styles_body_table(styles_dict):
    """Render extracted_styles as a human-readable body table per
    docx-template.capsule v1.0 §Required Body Sections."""
    page = styles_dict.get('page', {})
    margins = page.get('margins_dxa', {})
    df = styles_dict.get('default_font', {})
    hf = styles_dict.get('headers_footers', {})
    sf = styles_dict.get('special_features', {})
    theme = styles_dict.get('theme', {})
    named = styles_dict.get('named_styles') or []
    style_names = [s.get('name', s.get('id', '')) for s in named[:10]]
    # P1-5 closure (v1.32.0 spec [900d41e0] §3.4 v0.4 LOCKED): emit "; N more"
    # (no nested parens — cell content already inside parens) instead of bare
    # "; list truncated" when len(named) > 10. Gives the reader a quantitative
    # sense of what was omitted.
    extra = len(named) - 10
    truncation_clause = f'; {extra} more' if extra > 0 else ''
    style_summary = (f"{len(named)} styles "
                     f"({', '.join(style_names)}{truncation_clause})")
    htp = hf.get('header_text_preview') or '(none)'
    ftp = hf.get('footer_text_preview') or '(none)'
    feat_flags = []
    for k, label in (('has_macros', 'macros'), ('has_embedded_fonts', 'embedded_fonts'),
                     ('has_custom_xml', 'custom_xml'), ('has_watermark', 'watermarks')):
        if sf.get(k):
            feat_flags.append(label)
    features = ', '.join(feat_flags) if feat_flags else '(none)'

    return (
        "| Property | Value |\n"
        "|---|---|\n"
        f"| Page size | {page.get('width_dxa', 12240)} × {page.get('height_dxa', 15840)} DXA ({page.get('orientation', 'portrait')}) |\n"
        f"| Margins | top={margins.get('top', 1440)} · bottom={margins.get('bottom', 1440)} · left={margins.get('left', 1440)} · right={margins.get('right', 1440)} DXA |\n"
        f"| Default font | {df.get('family', 'Calibri')} @ {df.get('size_half_pt', 22) / 2:.1f}pt (color: {df.get('color', '000000')}) |\n"
        f"| Theme | primary={theme.get('primary_color', '1F497D')}; secondary={theme.get('secondary_color', '4F81BD')} |\n"
        f"| Named styles | {style_summary} |\n"
        f"| Header preview | {htp} |\n"
        f"| Footer preview | {ftp} |\n"
        f"| Sections | {styles_dict.get('sections_count', 1)} |\n"
        f"| Special features | {features} |\n"
    )


def author_template_entry(studio_root, template_uid, slug, title, description,
                          template_binary_relpath, template_binary_hash,
                          styles_dict, use_cases=None, executive='cli-user'):
    """Author the vault/files/<uid>.md entry per docx-template.capsule v1.0."""
    entry_path = studio_root / 'vault' / 'files' / f'{template_uid}.md'
    entry_path.parent.mkdir(parents=True, exist_ok=True)

    body_title = title.replace('`', "'").replace('\n', ' ')
    extracted_styles_block = _render_extracted_styles_yaml(styles_dict)
    body_table = _render_extracted_styles_body_table(styles_dict)

    use_cases_yaml = ''
    use_cases_body = ''
    if use_cases:
        use_cases_yaml = 'use_cases:\n' + '\n'.join(f'  - {_yaml_str(u)}' for u in use_cases) + '\n'
        use_cases_body = '\n## Use Cases\n\n' + '\n'.join(f'- {u}' for u in use_cases) + '\n'

    content = f"""---
uid: {template_uid}
type: docx-template
status: active
state: active
title: {_yaml_str(title)}
slug: {_yaml_str(slug)}
description: {_yaml_str(description)}
owner: {TOOL_NAME}-v{TOOL_VERSION}
template_binary_path: {_yaml_str(template_binary_relpath)}
template_binary_hash: {template_binary_hash}
registration_tool_version: {TOOL_NAME}-v{TOOL_VERSION}
extraction_scope: argo-private
{use_cases_yaml}{extracted_styles_block}
member_of:
  - "2d083137"
relations: []
created: {now_date()}
created_by: {TOOL_NAME}-v{TOOL_VERSION}
modified: {now_date()}
modified_by: {TOOL_NAME}-v{TOOL_VERSION}
schema_version: 2
---

# {body_title} — Tropo docx-template

{description}

## Format Reference

Binary at `{template_binary_relpath}`. Registered as a governed `docx-template` entry
per arch-spec [5a89297a v0.5](5a89297a.md) §3.3 + §3.4 + §3.6.
{use_cases_body}
## Extracted Style Metadata

{body_table}
(Above is the human-readable surface of the `extracted_styles:` frontmatter for
template-selection context. The structured frontmatter is authoritative; the
body table is rendered for human readability at registration time. Manual edits
to either are overwritten on `--force` re-registration.)

---

*Authored by `{TOOL_NAME}` v{TOOL_VERSION} ({executive}) on {now_date()}. Composes with [docx-template.capsule v1.0](../../.tropo/capsules/docx-template.capsule.md).*
"""
    entry_path.write_text(content)
    return entry_path


def append_template_index_row(studio_root, template_uid, slug, title, description,
                              template_binary_relpath, template_binary_hash,
                              use_cases=None):
    """Inline-sync vault/00-index.jsonl per arch-spec §3.10 check 4."""
    index_path = studio_root / VAULT_INDEX_RELPATH
    if not index_path.exists():
        return

    # Idempotency
    try:
        with index_path.open('r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get('uid') == template_uid:
                    return
    except OSError:
        return

    row = {
        'uid': template_uid,
        'type': 'docx-template',
        'title': title,
        'slug': slug,
        'description': description,
        'state': 'active',
        'status': 'active',
        'owner': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'template_binary_path': template_binary_relpath,
        'template_binary_hash': template_binary_hash,
        'registration_tool_version': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'extraction_scope': 'argo-private',
        'member_of': ['2d083137'],
        'use_cases': use_cases or [],
        'created': now_date(),
        'modified': now_date(),
        'created_by': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'modified_by': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'schema_version': 2,
        'file_ext': 'md',
    }
    with index_path.open('a') as f:
        f.write(json.dumps(row, separators=(',', ':')) + '\n')
        f.flush()
        os.fsync(f.fileno())


def append_journal(studio_root, event):
    """Append a journal event row per arch-spec §3.6 step 8 + §3.8."""
    journal_path = studio_root / JOURNAL_RELPATH
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with journal_path.open('a') as f:
        f.write(json.dumps(event, separators=(',', ':')) + '\n')
        f.flush()
        os.fsync(f.fileno())


def archive_predecessor_template(studio_root, predecessor_uid, successor_uid):
    """When --force re-registers an existing slug: flip predecessor to state:archived.

    Per docx-template.capsule v1.0 Governance Rule 4 (multiple versions via
    supersedes: chain). Predecessor entry's state field flips to 'archived'
    atomically; the successor entry declares `supersedes: <predecessor-uid>`.
    """
    entry_path = studio_root / 'vault' / 'files' / f'{predecessor_uid}.md'
    if not entry_path.exists():
        return
    text = entry_path.read_text()
    text = re.sub(r'^status: \S+', 'status: archived', text, flags=re.MULTILINE)
    text = re.sub(r'^state: \S+', 'state: archived', text, flags=re.MULTILINE)
    text = re.sub(r'^modified: \S+', f'modified: {now_date()}', text, flags=re.MULTILINE)
    text = re.sub(r'^modified_by: \S+', f'modified_by: {TOOL_NAME}-v{TOOL_VERSION}', text, flags=re.MULTILINE)
    # Add superseded_by note if not already present
    if 'superseded_by:' not in text:
        text = text.replace('schema_version: 2\n---',
                            f'superseded_by: {successor_uid}\nschema_version: 2\n---')
    entry_path.write_text(text)
    # Also update the index row's state
    _update_index_row_state(studio_root, predecessor_uid, 'archived')


def _update_index_row_state(studio_root, uid, new_state):
    """Update an index row's state + status fields by UID (line-by-line rewrite)."""
    index_path = studio_root / VAULT_INDEX_RELPATH
    if not index_path.exists():
        return
    new_lines = []
    try:
        with index_path.open('r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    new_lines.append(line)
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    new_lines.append(line)
                    continue
                if row.get('uid') == uid:
                    row['state'] = new_state
                    row['status'] = new_state
                    row['modified'] = now_date()
                    row['modified_by'] = f'{TOOL_NAME}-v{TOOL_VERSION}'
                    new_lines.append(json.dumps(row, separators=(',', ':')))
                else:
                    new_lines.append(line)
    except OSError:
        return
    with index_path.open('w') as f:
        f.write('\n'.join(new_lines) + '\n')
        f.flush()
        os.fsync(f.fileno())


# ==========================================================================
# CLI entry point
# ==========================================================================

def main():
    parser = argparse.ArgumentParser(
        prog='tropo-register-template.py',
        description=__doc__.split('\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--path', required=True,
                        help="Path to the .docx file to register as a template.")
    parser.add_argument('--name', required=True,
                        help="Slug identifier ([a-z0-9-]+). Becomes the binary's filename "
                             "at .tropo-studio/templates/<slug>.docx.")
    parser.add_argument('--description', default='',
                        help="Free-form description (≤ 500 chars).")
    parser.add_argument('--use-case', action='append', default=[],
                        help="Optional use-case description; repeat for multiple.")
    parser.add_argument('--force', action='store_true',
                        help="Override slug collision: re-register a new template at "
                             "this slug; predecessor flips to state:archived with "
                             "supersedes: chain.")
    parser.add_argument('--template-uid', default=None,
                        help="Override UID minting (advanced; for backfill/migration).")
    parser.add_argument('--studio-root', default=None,
                        help="Studio root (default: walk up from cwd).")
    parser.add_argument('--run-uid', default='cli-standalone',
                        help="Activation run UID for audit log.")
    parser.add_argument('--executive', default='cli-user',
                        help="Executive persona for audit log.")
    args = parser.parse_args()

    studio_root = resolve_studio_root(args.studio_root)

    # Precondition 2: slug regex
    if not SLUG_RE.match(args.name):
        raise SystemExit(
            f"Slug invalid: '{args.name}' does not match {SLUG_RE.pattern} "
            f"(per arch-spec §3.6 precondition 2). Slugs are lowercase-hyphenated "
            f"[a-z0-9-]+; rename and retry."
        )

    # Precondition 1: .docx validation
    source_path = Path(args.path).resolve()
    validate_docx(source_path)

    # Precondition 3: slug-collision discrimination
    slug_state, existing_uid = discriminate_slug_state(studio_root, args.name)
    predecessor_uid = None
    if slug_state == 'registered':
        if not args.force:
            raise SystemExit(
                f"Slug collision: template with slug '{args.name}' is already registered "
                f"(UID {existing_uid}). Use --force to overwrite (predecessor will flip to "
                f"state:archived with supersedes: chain), OR pick a different --name slug. "
                f"Per arch-spec §3.6 precondition 3."
            )
        predecessor_uid = existing_uid
        print(f"WARN: --force overrides registered slug '{args.name}' (predecessor: {existing_uid})",
              file=sys.stderr)
    elif slug_state == 'binary-present-but-unregistered':
        if not args.force:
            raise SystemExit(
                f"Slug collision: binary at .tropo-studio/templates/{args.name}.docx exists "
                f"but no registry entry references this slug (per arch-spec §3.6 precondition 3 "
                f"recoverable-warning state). Options: (a) ADOPT — author a fresh registry entry "
                f"against the existing binary; (b) OVERWRITE — replace the binary AND author the entry; "
                f"(c) RENAME — pick a different --name slug. "
                f"--force selects (b) overwrite. To adopt instead, manually mv the binary first."
            )
        print(f"WARN: --force overrites binary-present-but-unregistered slug '{args.name}'",
              file=sys.stderr)

    # Acquire lock + execute
    with ReconcilerLock(studio_root, executive=args.executive):
        # Step 2: Copy source binary
        templates_dir = studio_root / TEMPLATES_RELPATH
        templates_dir.mkdir(parents=True, exist_ok=True)
        target_binary = templates_dir / f'{args.name}.docx'
        target_binary_rel = str(target_binary.relative_to(studio_root))
        shutil.copy2(source_path, target_binary)

        # Step 3: SHA-256 the copy
        h = hashlib.sha256()
        with target_binary.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        template_binary_hash = h.hexdigest()

        # Step 4: Extract style metadata via shared module
        # (Per arch-spec v0.5 §3.5.5 Amendment 2 + §3.6 step 4 v0.5 amendment:
        # call extract_office_styles() — do NOT re-implement the XML walk inline.)
        styles_dict = office_styles.extract_office_styles(target_binary)
        if styles_dict is None:
            raise SystemExit(
                f"Style extraction failed on '{source_path}' — corrupt .docx or "
                f"the binary lacks required parts (word/document.xml). The binary copy "
                f"at {target_binary_rel} has been written but no template entry was authored. "
                f"Inspect the source binary and retry."
            )

        # Step 5: Mint or use overridden template UID
        template_uid = args.template_uid or generate_uid()
        title = source_path.stem

        # Step 6: Author template entry
        entry_path = author_template_entry(
            studio_root=studio_root,
            template_uid=template_uid,
            slug=args.name,
            title=title,
            description=args.description,
            template_binary_relpath=target_binary_rel,
            template_binary_hash=template_binary_hash,
            styles_dict=styles_dict,
            use_cases=args.use_case,
            executive=args.executive,
        )

        # Step 7: Inline-sync the index per arch-spec §3.10 check 4
        append_template_index_row(
            studio_root=studio_root,
            template_uid=template_uid,
            slug=args.name,
            title=title,
            description=args.description,
            template_binary_relpath=target_binary_rel,
            template_binary_hash=template_binary_hash,
            use_cases=args.use_case,
        )

        # If --force overrode a predecessor: flip its state to archived
        slug_collision_resolution = None
        if predecessor_uid:
            archive_predecessor_template(studio_root, predecessor_uid, template_uid)
            slug_collision_resolution = 'overwritten'
        elif slug_state == 'binary-present-but-unregistered':
            slug_collision_resolution = 'overwritten'

        # Step 8: Append journal event per arch-spec §3.6 step 8
        append_journal(studio_root, {
            'event': 'template_registered',
            'template_uid': template_uid,
            'slug': args.name,
            'source_path': str(source_path.relative_to(studio_root))
                if source_path.is_relative_to(studio_root) else str(source_path),
            'template_binary_path': target_binary_rel,
            'template_hash': template_binary_hash,
            'registration_tool_version': f'{TOOL_NAME}-v{TOOL_VERSION}',
            'predecessor_uid': predecessor_uid,
            'slug_collision_resolution': slug_collision_resolution,
            'timestamp': now_iso(),
            'executive': args.executive,
            'run_uid': args.run_uid,
            'extracted_styles_named_count': len(styles_dict.get('named_styles', []) or []),
        })

    # Step 9: Emit stdout
    print(f"Template registered: {template_uid} (slug: {args.name})")
    print(f"Binary:  {target_binary_rel}", file=sys.stderr)
    print(f"Entry:   vault/files/{template_uid}.md", file=sys.stderr)
    print(f"Styles:  {len(styles_dict.get('named_styles', []) or [])} named styles extracted", file=sys.stderr)
    if predecessor_uid:
        print(f"Superseded predecessor: {predecessor_uid} (state: archived)", file=sys.stderr)


if __name__ == '__main__':
    main()
