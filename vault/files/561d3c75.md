#!/usr/bin/env python3
"""
---
uid: 561d3c75
type: tool
name: tropo-extract.py
title: tropo-extract.py — Extract markdown working-copy from imported .docx
description: Extract a markdown working-copy from a v1.25.0 external-artifact projection. Opens the source .docx via the docx skill's bundled unpack pattern; produces text + structural markdown (headings, lists, tables, footnotes, inline bold/italic/underline); records extraction stats in the journal; surfaces a plain-language extraction summary at stdout. The first gesture of the v1.28.0 import → work → export loop.
version: 1.0.0
status: active
state: active
stage: build
schema_version: 2
extraction_scope: ship
author: argus
owner: argus
language: python
path: .tropo/scripts/tropo-extract.py
script_path: vault/tools/561d3c75.py
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/561d3c75.py --projection <uid> [--force] [--working-uid <uid>]
spawnable_by:
- all-executives
- user
destructive: 'false'
audit_required: 'true'
writes_scope:
- vault/files/<working-copy-uid>.md
- vault/00-index.jsonl
- .tropo-studio/reconciler/journal.jsonl
reads_scope:
- external-work/**/*.docx
governance_category: lifecycle
domain: Extract a markdown working-copy from an imported .docx. The bridge between v1.25.0 binary governance and v1.28.0 agent-native editing — opens the .docx, unpacks word/document.xml, walks paragraphs producing structured markdown, surfaces extraction stats.
domain_tags:
- tropo-extract
- working-copy
- docx-extraction
- agent-native-editing
- v1.26.0-stream-b
- user-facing
- mcp-aligned
trigger_description: 'Reach for this when a user or agent wants to read + edit the content of an imported .docx in markdown. Resolve the projection UID first (via the imported folder''s mirror, or `grep type:external-artifact vault/00-index.jsonl`); then run `tropo-extract.py --projection <uid>`. Tool acquires the reconciler lock, hashes the source binary, opens it via the docx skill, walks paragraphs (heading-shift convention: source Heading1 → markdown ##; H1 reserved for title), authors a working-copy at vault/files/<working-uid>.md with full lineage chain to the projection, surfaces a plain-language extraction summary at stdout (e.g., ''83 paragraphs + 7 headings + 2 tables; dropped 3 inline drawings + 1 equation + 2 custom paragraph styles''), inline-syncs the index. Refuses if a working-copy already exists for the projection unless --force. After extraction: agent reads + edits the working-copy in markdown; reconciler monitors source-binary drift; export back via tropo-export.py.'
governed_by: d5e1b4a3
capsule_version: '2.5'
informs_capsules:
- a2bc3e16
aligned_with:
- 5a89297a
created: 2026-05-13
modified: 2026-05-14
created_by: argus-a61
modified_by: argus-a62
member_of:
- 1a750ad2
tags:
- tool
- cli
- python
- tropo-extract
- working-copy-extraction
- docx
- user-facing
- mcp-aligned
- v1.26.0-stream-b
file_ext: md
subsystem_hub:
- 76bab75f
---
"""

"""tropo-extract.py — extract a markdown working-copy from an external-artifact projection.

Per [arch-spec 5a89297a §3.5](vault/files/5a89297a.md) — the v1.26.0 user-facing CLI gesture
that converts an imported `.docx` (governed as a v1.25.0 external-artifact projection) into
an agent-editable markdown working-copy at `vault/files/<working-uid>.md`.

User-facing surface (per arch-spec §5.3 walk-lock): this is a standalone script with its own
argparse interface. Internally composes with `import-walker.py` library functions for hash
chain, lock acquisition, journal append, UID minting. Library-mode lock semantics per §3.12
(single in-process acquisition; subprocess invocation would re-acquire and deadlock — not the
v1.26.0 design intent).

UID minted at arch-spec v0.3 lock: see arch-spec.frontmatter.informs_capsules.

v1.26.0 Stream B deliverable.
Authored 2026-05-13 by argus-a61.
"""

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path


TOOL_NAME = 'tropo-extract'
TOOL_VERSION = '1.1.0'   # v1.0.0 = v1.26.0 ship; v1.1.0 = v1.70 S1.3 per-block provenance anchors


def _sha8(text: str) -> str:
    """SHA-256 of text → first 8 hex chars. Used for per-block content hashes."""
    return hashlib.sha256(text.encode()).hexdigest()[:8]

# OOXML namespace for Word document.xml + Office docProps
W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
DC_NS = '{http://purl.org/dc/elements/1.1/}'

# ==========================================================================
# Library import — load import-walker.py functions in-process per §3.12
# ==========================================================================

def _load_import_walker():
    """Load import-walker.py as an in-process module so we can reuse its library
    functions (compute_hash, append_journal, generate_uid, acquire_lock, etc.).

    Per arch-spec §3.12 library-mode composition: single in-process acquisition;
    we hold the lock at our entry point and import-walker.py functions operate
    within the held lock's scope without re-acquiring.
    """
    # v1.56 Tools-in-Vault Pillar 1 Reshape: import-walker moved to vault/tools/<uid>.py
    # per single-file-truth doctrine. UID bf886f30 per .tropo-studio/registries/registry.jsonl.
    # Lane S sweep inline fix by metis-g62 2026-05-27 (was: 'import-walker.py' same-dir lookup;
    # broke after Pillar 1 migration moved bodies to UID-named files).
    iw_path = Path(__file__).parent / 'bf886f30.py'
    if not iw_path.exists():
        raise SystemExit(f"FATAL: required substrate {iw_path} not present (import-walker UID bf886f30 per v1.56 migration)")
    spec = importlib.util.spec_from_file_location('import_walker', iw_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IW = _load_import_walker()


# ==========================================================================
# Frontmatter parsing for projection lookups
# ==========================================================================

def find_projection_file(studio_root, projection_uid):
    """Return path to vault/files/<projection_uid>.md or raise."""
    p = studio_root / 'vault' / 'files' / f'{projection_uid}.md'
    if not p.exists():
        raise SystemExit(f"Projection UID {projection_uid!r} does not resolve "
                         f"({p} not found)")
    return p


def find_active_working_copy(studio_root, projection_uid):
    """Return path of any existing active working-copy with derived_from = projection_uid.
    Returns None if no active working-copy exists. Per arch-spec §3.5 precondition 4
    + §3.1 governance rule 2 (one-working-copy-per-projection in v1.0)."""
    vault_files = studio_root / 'vault' / 'files'
    if not vault_files.exists():
        return None
    for p in vault_files.glob('*.md'):
        try:
            fm = IW.parse_frontmatter(p)
            if (fm.get('type') == 'working-copy'
                    and fm.get('state') == 'active'
                    and projection_uid in str(fm.get('derived_from', ''))):
                return p
        except Exception:
            continue
    return None


# ==========================================================================
# .docx extraction — text + structure → markdown
# ==========================================================================

class ExtractionResult:
    """Container for extraction output + stats per arch-spec §3.5 step 7."""
    def __init__(self):
        self.markdown_body = ''
        self.stats = {
            'text_paragraphs_extracted': 0,
            'headings_extracted': 0,
            'lists_extracted': 0,
            'tables_extracted': 0,
            'footnotes_extracted': 0,
            'dropped_drawings': 0,
            'dropped_equations': 0,
            'dropped_section_breaks': 0,
            'dropped_custom_styles': 0,
            'comments_dropped': 0,
            'embedded_images_placeholder': 0,
            'tracked_changes_accepted': 0,
            'tracked_changes_rejected': 0,   # v1.26.0.1 P1-4 — runs inside <w:del> get dropped per "silently accept" semantics
            'dropped_title_paragraphs': 0,   # v1.26.0.1 P1-1 — source Title pStyle paragraphs (frontmatter title is canonical H1)
            'headings_via_outline_level': 0,  # F1 fix 2026-06-12 — custom-named styles mapped by w:outlineLvl (96b7d233)
            'hyperlinks_extracted': 0,        # F4 fix 2026-06-12 — w:hyperlink -> [text](url) (96b7d233)
        }
        # First-seen source Title pStyle text — captured for optional title override
        self.source_title_text = None
        # Per-block provenance for diff-aware export (S1.3): list of {'idx', 'md_hash'}
        self.provenance = []


# Heading style mapping per arch-spec §3.5 step 3 — source heading levels SHIFT DOWN
# by one at extraction. H1 (`#`) reserved for the document title; source `Heading1` → `##`.
# Reverse shift happens at export (v1.27.0 tropo-export.py §3.7 step 4).
#
# v1.26.0.1 P1-1 remediation: 'Title' deliberately NOT mapped to '#'. The frontmatter
# title-from-filename emits `# {title}` as the body's first line; if a source .docx has
# a Title pStyle paragraph too, mapping it to `#` would produce two H1 headings + violate
# the "H1 reserved for the document title" rule. Title-pStyle paragraphs are counted in
# stats['dropped_title_paragraphs'] (see _process_title_paragraph) and may be reflected
# in the frontmatter title at extraction (one-time override during step 5).
_HEADING_STYLE_TO_MD = {
    'Heading1': '##',
    'Heading2': '###',
    'Heading3': '####',
    'Heading4': '#####',
    'Heading5': '######',
    'Heading6': '######',   # markdown caps at 6
}

# Standard Word built-in styles we recognize cleanly (others map to Normal + counted dropped)
_KNOWN_STANDARD_STYLES = {
    'Normal', 'NoSpacing', 'BodyText',
    'Title', 'Subtitle',
    'Heading1', 'Heading2', 'Heading3', 'Heading4', 'Heading5', 'Heading6',
    'ListParagraph', 'ListBullet', 'ListNumber',
    'Quote', 'IntenseQuote', 'BlockQuote',
    'Code', 'CodeBlock',
    'Caption', 'Footer', 'Header',
    'FootnoteText', 'FootnoteReference',
    'Hyperlink',
}


R_NS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def _wrap_inline(text, opener, closer):
    """Wrap text in inline markers, keeping whitespace OUTSIDE the markers.

    F6 fix (96b7d233): Word runs routinely carry trailing/leading spaces
    ('Ottawa, ON — '), and `**Ottawa, ON — **` is invalid CommonMark — it
    renders literal asterisks. Whitespace moves outside; empty cores pass
    through unwrapped.
    """
    core = text.strip()
    if not core:
        return text
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return f'{lead}{opener}{core}{closer}{trail}'


def _text_of_paragraph(p_elem, stats=None, rels=None):
    """Concatenate <w:t> text content from a paragraph, with inline formatting.

    Tracked-change semantics (v1.26.0.1 P1-4 remediation):
    - Runs INSIDE <w:ins> (tracked insertion) are INCLUDED (per spec §3.5 "tracked changes silently accepted" — accepting an insertion means keeping it).
    - Runs INSIDE <w:del> (tracked deletion) are EXCLUDED (accepting a deletion means dropping the deleted text). Increments stats['tracked_changes_rejected'] when caller passes stats.

    Hyperlinks (F4 fix, 96b7d233): runs inside <w:hyperlink> collapse to one
    markdown link `[text](url)` — URL from the rels map (r:id, external) or
    `#anchor` for internal w:anchor links. Without a resolvable target the
    runs flow through as plain formatted text (previous behavior).
    """
    parts = []
    # Build set of run elements that are descendants of any <w:del> ancestor — those get excluded.
    excluded_runs = set()
    for del_elem in p_elem.iter(W_NS + 'del'):
        for r in del_elem.iter(W_NS + 'r'):
            excluded_runs.add(id(r))

    # F4: pre-pass hyperlinks — first run of each link emits the whole link;
    # sibling runs of that link are consumed silently.
    link_first_run = {}   # id(first run) -> markdown
    link_member_runs = set()
    for h in p_elem.iter(W_NS + 'hyperlink'):
        h_runs = [r for r in h.iter(W_NS + 'r') if id(r) not in excluded_runs]
        if not h_runs:
            continue
        link_text = ''.join(t.text or '' for r in h_runs for t in r.iter(W_NS + 't')).strip()
        if not link_text:
            continue
        rid = h.get(R_NS + 'id')
        anchor = h.get(W_NS + 'anchor')
        url = (rels or {}).get(rid) if rid else (f'#{anchor}' if anchor else None)
        if not url:
            continue
        link_first_run[id(h_runs[0])] = f'[{link_text}]({url})'
        for r in h_runs:
            link_member_runs.add(id(r))

    for run in p_elem.iter(W_NS + 'r'):
        if id(run) in excluded_runs:
            if stats is not None:
                stats['tracked_changes_rejected'] = stats.get('tracked_changes_rejected', 0) + 1
            continue

        if id(run) in link_member_runs:
            md = link_first_run.get(id(run))
            if md:
                parts.append(md)
                if stats is not None:
                    stats['hyperlinks_extracted'] = stats.get('hyperlinks_extracted', 0) + 1
            continue

        # Inline formatting
        rpr = run.find(W_NS + 'rPr')
        bold = rpr is not None and rpr.find(W_NS + 'b') is not None
        italic = rpr is not None and rpr.find(W_NS + 'i') is not None
        underline = rpr is not None and rpr.find(W_NS + 'u') is not None

        # Collect text
        run_text = ''.join(t.text or '' for t in run.iter(W_NS + 't'))
        if not run_text:
            continue

        # Wrap in markdown formatting (order: bold > italic > underline)
        # F6: whitespace stays outside the markers (_wrap_inline).
        if bold and italic:
            run_text = _wrap_inline(run_text, '***', '***')
        elif bold:
            run_text = _wrap_inline(run_text, '**', '**')
        elif italic:
            run_text = _wrap_inline(run_text, '_', '_')
        if underline:
            run_text = _wrap_inline(run_text, '<u>', '</u>')

        parts.append(run_text)
    return ''.join(parts)


def _paragraph_style(p_elem):
    """Return the paragraph's pStyle val, or None if no style declared."""
    p_pr = p_elem.find(W_NS + 'pPr')
    if p_pr is None:
        return None
    p_style = p_pr.find(W_NS + 'pStyle')
    if p_style is None:
        return None
    return p_style.get(W_NS + 'val')


def _is_list_item(p_elem):
    """Return ('bullet'|'numbered', level) if paragraph is a list item, else None."""
    p_pr = p_elem.find(W_NS + 'pPr')
    if p_pr is None:
        return None
    num_pr = p_pr.find(W_NS + 'numPr')
    if num_pr is None:
        return None
    ilvl = num_pr.find(W_NS + 'ilvl')
    level = int(ilvl.get(W_NS + 'val')) if ilvl is not None else 0
    # Heuristic: bullets vs numbered — we don't fully resolve numId → numbering.xml
    # in v1.0. Default to bullet; agent can fix at edit time.
    return ('bullet', level)


def _extract_table(tbl_elem, result, rels=None):
    """Extract a Word table as markdown GFM table."""
    rows = []
    for tr in tbl_elem.iter(W_NS + 'tr'):
        cells = []
        for tc in tr.iter(W_NS + 'tc'):
            cell_text = ''
            for p in tc.iter(W_NS + 'p'):
                cell_text += _text_of_paragraph(p, result.stats, rels=rels) + ' '
            cells.append(cell_text.strip() or ' ')
        if cells:
            rows.append(cells)
    if not rows:
        return ''

    # Build GFM table: first row as header
    out = ['| ' + ' | '.join(rows[0]) + ' |']
    out.append('| ' + ' | '.join(['---'] * len(rows[0])) + ' |')
    for row in rows[1:]:
        # Pad/trim to match header column count
        while len(row) < len(rows[0]):
            row.append(' ')
        out.append('| ' + ' | '.join(row[:len(rows[0])]) + ' |')

    result.stats['tables_extracted'] += 1
    return '\n'.join(out)


def _extract_footnotes_section(zf, result):
    """Extract footnotes.xml if present; return appended markdown footnote section."""
    try:
        if 'word/footnotes.xml' not in zf.namelist():
            return ''
        with zf.open('word/footnotes.xml') as f:
            tree = ET.parse(f)
    except (zipfile.BadZipFile, ET.ParseError):
        return ''

    notes = []
    for fn in tree.getroot().iter(W_NS + 'footnote'):
        fn_id = fn.get(W_NS + 'id')
        # Skip separator/continuationSeparator notes (id <= 0 usually)
        try:
            if int(fn_id) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        text_parts = []
        for p in fn.iter(W_NS + 'p'):
            t = _text_of_paragraph(p, result.stats)
            if t.strip():
                text_parts.append(t.strip())
        if text_parts:
            notes.append(f'[^{fn_id}]: ' + ' '.join(text_parts))
            result.stats['footnotes_extracted'] += 1

    if not notes:
        return ''
    return '\n\n' + '\n\n'.join(notes)


def _count_comments(zf, result):
    """Count comments in comments.xml (dropped at extraction per arch-spec §3.5)."""
    try:
        if 'word/comments.xml' not in zf.namelist():
            return
        with zf.open('word/comments.xml') as f:
            tree = ET.parse(f)
        result.stats['comments_dropped'] = len(list(
            tree.getroot().iter(W_NS + 'comment')))
    except (zipfile.BadZipFile, ET.ParseError):
        pass


def _count_drawings_and_special(p_elem, result):
    """Count drawings, equations, embedded images, tracked changes in a paragraph."""
    # Drawings
    result.stats['dropped_drawings'] += len(list(p_elem.iter(W_NS + 'drawing')))
    # Equations (OMML namespace)
    omml_count = sum(1 for _ in p_elem.iter('{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath'))
    omml_count += sum(1 for _ in p_elem.iter('{http://schemas.openxmlformats.org/officeDocument/2006/math}oMathPara'))
    result.stats['dropped_equations'] += omml_count
    # Tracked changes
    result.stats['tracked_changes_accepted'] += len(list(p_elem.iter(W_NS + 'ins')))


def _style_outline_levels(zf):
    """Map styleId -> w:outlineLvl from word/styles.xml (F1 fix, 96b7d233).

    Agency/corporate template styles carry custom NAMES ('heading 10') that the
    _HEADING_STYLE_TO_MD name map can never enumerate, but Word's own authority
    on heading-ness is the style's declared outline level. Levels 0-5 only
    (Word's heading range); body styles carry no outlineLvl and stay unmapped.
    """
    levels = {}
    try:
        with zf.open('word/styles.xml') as f:
            styles_tree = ET.parse(f)
    except (KeyError, ET.ParseError):
        return levels
    for style_el in styles_tree.getroot().findall(W_NS + 'style'):
        sid = style_el.get(W_NS + 'styleId')
        if not sid:
            continue
        p_pr = style_el.find(W_NS + 'pPr')
        if p_pr is None:
            continue
        outline = p_pr.find(W_NS + 'outlineLvl')
        if outline is None:
            continue
        try:
            lvl = int(outline.get(W_NS + 'val'))
        except (TypeError, ValueError):
            continue
        if 0 <= lvl <= 5:
            levels[sid] = lvl
    return levels


def extract_docx(file_path):
    """Extract .docx content into markdown + stats. Returns ExtractionResult."""
    result = ExtractionResult()

    with zipfile.ZipFile(file_path, 'r') as zf:
        # Count comments (we drop them but record the count)
        _count_comments(zf, result)

        # F1 fix (2026-06-12): styleId -> outlineLvl, the authority for headings
        # whose names the built-in map can't know.
        outline_levels = _style_outline_levels(zf)

        # F4 fix (2026-06-12): rId -> external URL map for hyperlink extraction.
        rels = {}
        try:
            with zf.open('word/_rels/document.xml.rels') as f:
                rels_tree = ET.parse(f)
            for rel in rels_tree.getroot():
                rid, tgt = rel.get('Id'), rel.get('Target')
                if rid and tgt and rel.get('TargetMode') == 'External':
                    rels[rid] = tgt
        except (KeyError, ET.ParseError):
            pass

        with zf.open('word/document.xml') as f:
            tree = ET.parse(f)

        body = tree.getroot().find(W_NS + 'body')
        if body is None:
            return result

        md_parts = []
        body_elem_idx = 0  # S1.3: global index over all body elements (p, tbl, sectPr)
        for child in body:
            _idx = body_elem_idx   # capture before any continue
            body_elem_idx += 1
            tag = child.tag
            if tag == W_NS + 'p':
                _count_drawings_and_special(child, result)

                # Detect images (drawings WITH a blip-fill = embedded image)
                blip_count = len(list(child.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}blip')))
                if blip_count:
                    result.stats['embedded_images_placeholder'] += blip_count

                # Section breaks (sectPr in this paragraph)
                p_pr = child.find(W_NS + 'pPr')
                if p_pr is not None and p_pr.find(W_NS + 'sectPr') is not None:
                    result.stats['dropped_section_breaks'] += 1

                style = _paragraph_style(child)
                text = _text_of_paragraph(child, result.stats, rels=rels)

                # Skip empty paragraphs (no provenance anchor — no content to preserve)
                if not text.strip():
                    # Add image placeholder line if there's an embedded image here
                    if blip_count:
                        for i in range(blip_count):
                            md_parts.append(f'![image]({{#image-{result.stats["embedded_images_placeholder"]}-not-extracted}})')
                    continue

                # Title pStyle — NOT a heading; captured for frontmatter override + counted as dropped
                # (v1.26.0.1 P1-1 anti-double-emit rule)
                if style == 'Title':
                    if result.source_title_text is None:
                        result.source_title_text = text
                    result.stats['dropped_title_paragraphs'] += 1
                    continue

                # Heading
                if style in _HEADING_STYLE_TO_MD:
                    _md = f'{_HEADING_STYLE_TO_MD[style]} {text}'
                    _h = _sha8(_md)
                    result.provenance.append({'idx': _idx, 'md_hash': _h})
                    md_parts.append(f'<!-- tropo:block idx={_idx} hash={_h} -->\n{_md}')
                    result.stats['headings_extracted'] += 1
                    continue

                # Heading via declared outline level (F1 fix, 96b7d233): custom
                # template styles ('heading 10') that the name map can't know.
                # Same shift-down convention: outlineLvl 0 -> '##' (H1 reserved).
                if style and style in outline_levels:
                    _md = f'{"#" * min(outline_levels[style] + 2, 6)} {text}'
                    _h = _sha8(_md)
                    result.provenance.append({'idx': _idx, 'md_hash': _h})
                    md_parts.append(f'<!-- tropo:block idx={_idx} hash={_h} -->\n{_md}')
                    result.stats['headings_extracted'] += 1
                    result.stats['headings_via_outline_level'] += 1
                    continue

                # List item
                list_info = _is_list_item(child)
                if list_info:
                    kind, level = list_info
                    indent = '  ' * level
                    marker = '-' if kind == 'bullet' else '1.'
                    _md = f'{indent}{marker} {text}'
                    _h = _sha8(_md)
                    result.provenance.append({'idx': _idx, 'md_hash': _h})
                    md_parts.append(f'<!-- tropo:block idx={_idx} hash={_h} -->\n{_md}')
                    result.stats['lists_extracted'] += 1
                    continue

                # Quote style
                if style and 'Quote' in style:
                    _md = f'> {text}'
                    _h = _sha8(_md)
                    result.provenance.append({'idx': _idx, 'md_hash': _h})
                    md_parts.append(f'<!-- tropo:block idx={_idx} hash={_h} -->\n{_md}')
                    result.stats['text_paragraphs_extracted'] += 1
                    continue

                # Code style
                if style and 'Code' in style:
                    _md = f'```\n{text}\n```'
                    _h = _sha8(_md)
                    result.provenance.append({'idx': _idx, 'md_hash': _h})
                    md_parts.append(f'<!-- tropo:block idx={_idx} hash={_h} -->\n{_md}')
                    result.stats['text_paragraphs_extracted'] += 1
                    continue

                # Custom (non-standard) style — flag in stats but emit as plain
                if style and style not in _KNOWN_STANDARD_STYLES:
                    result.stats['dropped_custom_styles'] += 1

                # Default: plain paragraph
                _h = _sha8(text)
                result.provenance.append({'idx': _idx, 'md_hash': _h})
                md_parts.append(f'<!-- tropo:block idx={_idx} hash={_h} -->\n{text}')
                result.stats['text_paragraphs_extracted'] += 1

            elif tag == W_NS + 'tbl':
                table_md = _extract_table(child, result, rels=rels)
                if table_md:
                    _h = _sha8(table_md)
                    result.provenance.append({'idx': _idx, 'md_hash': _h})
                    md_parts.append(f'<!-- tropo:block idx={_idx} hash={_h} -->\n{table_md}')

            elif tag == W_NS + 'sectPr':
                # Top-level section properties — counted as a section break
                result.stats['dropped_section_breaks'] += 1

        result.stats['provenance_blocks'] = len(result.provenance)

        # Join paragraphs with blank lines
        result.markdown_body = '\n\n'.join(md_parts)

        # Append footnotes section if any
        footnotes_md = _extract_footnotes_section(zf, result)
        if footnotes_md:
            result.markdown_body += footnotes_md

    return result


# ==========================================================================
# Working-copy authoring
# ==========================================================================

def write_working_copy(studio_root, uid, projection_uid, title, source_filename,
                      source_hash, hash_function, member_of_uid, owner, body,
                      description='', source_titled=False):
    """Author the working-copy markdown file at vault/files/<uid>.md."""
    wc_path = studio_root / 'vault' / 'files' / f'{uid}.md'
    wc_path.parent.mkdir(parents=True, exist_ok=True)

    if member_of_uid:
        member_block = f'member_of:\n  - "{member_of_uid}"'
    else:
        member_block = 'member_of: []'

    desc_field = f'description: {IW._yaml_str(description)}\n' if description else ''

    # F2 fix (2026-06-12, 96b7d233): the body H1 exists IFF the source document
    # had a real Title paragraph. A filename-derived H1 round-trips into a Title
    # paragraph the source never had (export tokenizes '# ...' -> Title).
    title_h1 = f'# {title}\n\n' if source_titled else ''

    content = f"""---
uid: {uid}
type: working-copy
title: {IW._yaml_str(title)}
state: active
derived_from:
  - "{projection_uid}"
source_filename: {IW._yaml_str(source_filename)}
source_had_title: {'true' if source_titled else 'false'}
source_hash_at_extraction: {source_hash}
last_source_hash_seen: {source_hash}
hash_function: {hash_function}
extraction_tool_version: {TOOL_NAME}-v{TOOL_VERSION}
owner: {owner}
extraction_scope: argo-private
{desc_field}{member_block}
relationships: []
created: {IW.now_date()}
created_by: {TOOL_NAME}-v{TOOL_VERSION}
modified: {IW.now_date()}
modified_by: {TOOL_NAME}-v{TOOL_VERSION}
provenance_version: 1
schema_version: 2
---

{title_h1}{body}
"""
    wc_path.write_text(content)
    return wc_path


# ==========================================================================
# Inline vault index sync — closes v1.25.0 fa026415 sibling defect
# ==========================================================================

def _flip_index_row_state(studio_root, uid, new_state):
    """Rewrite the index row for `uid` so its `state` field matches `new_state`.

    v1.26.0.1 P1-3 remediation: when `tropo-extract.py --force` archives a previous
    working-copy by flipping its frontmatter state, the inline-index-sync contract
    requires we also update the index row. Otherwise the index disagrees with the
    file and queries see a stale "active" state. Operates within the held reconciler
    lock per the caller's contract.
    """
    index_path = studio_root / 'vault' / '00-index.jsonl'
    if not index_path.exists():
        return

    lines = index_path.read_text().splitlines()
    updated = False
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line.rstrip(','))
        except json.JSONDecodeError:
            continue
        if row.get('uid') == uid:
            row['state'] = new_state
            row['modified'] = IW.now_date()
            lines[i] = json.dumps(row, separators=(',', ':'))
            updated = True
            break

    if updated:
        with index_path.open('w') as f:
            f.write('\n'.join(lines) + '\n')
            f.flush()
            os.fsync(f.fileno())


def append_index_row(studio_root, uid, title, owner, working_copy_path,
                    member_of_uid, source_filename):
    """Append a row to vault/00-index.jsonl for the new working-copy.

    Per arch-spec §3.5 step 6 + §3.10 check 4: extraction MUST sync index inline
    (not defer to rebuild-index.py). Concurrency: serializes on the same reconciler
    lock already held at script entry per §3.12.

    The index row schema matches what rebuild-index.py emits so re-runs of
    rebuild-index don't replace inconsistent fields.
    """
    index_path = studio_root / 'vault' / '00-index.jsonl'
    if not index_path.exists():
        return  # First-gen Studio? Skip silently; rebuild-index will catch.

    # Build the row payload — minimal subset matching rebuild-index.py output
    row = {
        'uid': uid,
        'type': 'working-copy',
        'title': title,
        'owner': owner,
        'state': 'active',
        'created': IW.now_date(),
        'modified': IW.now_date(),
        'created_by': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'modified_by': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'extraction_scope': 'argo-private',
        'schema_version': 2,
        'member_of': [member_of_uid] if member_of_uid else [],
        'source_filename': source_filename,
        'path': f'vault/files/{uid}.md',
    }

    # Append + fsync per §3.5 step 6 concurrency rule
    with index_path.open('a') as f:
        f.write(json.dumps(row, separators=(',', ':')) + '\n')
        f.flush()
        os.fsync(f.fileno())


# ==========================================================================
# User-facing summary — closes research concern #1 (extraction losses visible)
# ==========================================================================

def format_extraction_summary(working_copy_uid, working_copy_path, stats):
    """Build the user-facing summary printed at extract completion."""
    lines = [
        f'Working-copy authored: {working_copy_uid}',
        f'Path: {working_copy_path}',
        '',
    ]

    # Lead with what got extracted
    extracted_items = [
        ('paragraphs', stats['text_paragraphs_extracted']),
        ('headings', stats['headings_extracted']),
        ('lists items', stats['lists_extracted']),
        ('tables', stats['tables_extracted']),
        ('footnotes', stats['footnotes_extracted']),
    ]
    extracted_line = '  '.join(f'{n} {label}' for label, n in extracted_items if n)
    if extracted_line:
        lines.append(f'Extracted: {extracted_line}')

    # Then what got dropped (surface so user knows what they lost)
    dropped_items = [
        ('inline drawings', stats['dropped_drawings']),
        ('equations', stats['dropped_equations']),
        ('section breaks', stats['dropped_section_breaks']),
        ('custom paragraph styles', stats['dropped_custom_styles']),
        ('comments', stats['comments_dropped']),
        ('embedded images', stats['embedded_images_placeholder']),
    ]
    dropped_line = ', '.join(f'{n} {label}' for label, n in dropped_items if n)
    if dropped_line:
        lines.append(f'Dropped (not extracted): {dropped_line}')
        lines.append('  → see journal for full extraction_stats; '
                     'edge-case extraction is a v1.X enhancement')

    # Tracked changes silently accepted (per spec)
    if stats['tracked_changes_accepted']:
        lines.append(f'Tracked changes accepted: {stats["tracked_changes_accepted"]}')

    # S1.3 provenance anchors
    if stats.get('provenance_blocks', 0):
        lines.append(f'Provenance anchors: {stats["provenance_blocks"]} blocks indexed for diff-aware re-export (v1.70 S1.3)')

    return '\n'.join(lines)


# ==========================================================================
# Main extraction flow
# ==========================================================================

def main():
    parser = argparse.ArgumentParser(
        prog='tropo-extract',
        description='Extract a markdown working-copy from a Tropo external-artifact projection. '
                    'Per arch-spec 5a89297a §3.5. UID a2bc3e16 capsule.')
    parser.add_argument('--projection', required=True,
                        help='UID of the external-artifact projection to derive from')
    parser.add_argument('--force', action='store_true',
                        help='Overwrite existing working-copy for this projection')
    parser.add_argument('--working-uid', default=None,
                        help='Override UID minting; default mints fresh')
    parser.add_argument('--studio-root', default=None,
                        help='Explicit Studio root (default: find from cwd)')
    parser.add_argument('--executive', default=None,
                        help='Override executive slug for journal (default: argus-cli)')
    parser.add_argument('--run-uid', default=None,
                        help='Override run UID for journal correlation')
    parser.add_argument('--skip-lock', action='store_true',
                        help='Skip acquiring the reconciler lock (use only if caller holds it)')
    args = parser.parse_args()

    # Resolve Studio root
    studio_root = IW.resolve_studio_root(args.studio_root)

    # Precondition 1 — projection MUST resolve
    projection_path = find_projection_file(studio_root, args.projection)
    proj_fm = IW.parse_frontmatter(projection_path)
    if proj_fm.get('type') != 'external-artifact':
        raise SystemExit(f"Projection {args.projection} is type {proj_fm.get('type')!r}, "
                         f"not 'external-artifact'")

    # Precondition 2 — source binary MUST resolve + be readable
    source_rel = proj_fm.get('source_path') or proj_fm.get('original_path')
    if not source_rel:
        raise SystemExit(f"Projection {args.projection} has no source_path or original_path")
    source_path = (studio_root / source_rel).resolve()
    if not source_path.exists() or not source_path.is_file():
        raise SystemExit(f"Source binary not readable: {source_path}")

    # Precondition 3 — extension MUST be supported (v1.26.0: .docx only)
    if source_path.suffix.lower() != '.docx':
        raise SystemExit(f"Extension {source_path.suffix!r} not yet supported for "
                         f"extraction; v1.26.0 ship scope: .docx only")

    # Precondition 4 — refuse if active working-copy exists (unless --force)
    existing = find_active_working_copy(studio_root, args.projection)
    if existing and not args.force:
        raise SystemExit(f"Active working-copy already exists for projection "
                         f"{args.projection} at {existing.relative_to(studio_root)}. "
                         f"Use --force to overwrite (warns about losing agent edits).")
    if existing and args.force:
        print(f"WARNING: --force overwriting existing working-copy at "
              f"{existing.relative_to(studio_root)}. Agent edits since last "
              f"extract will be lost.", file=sys.stderr)

    # Acquire lock per §3.12 library-mode composition
    lock_ctx = IW.ReconcilerLock(studio_root) if not args.skip_lock else contextlib.nullcontext()
    with lock_ctx:
        # v1.26.0.1 P1-2 + P1-3 remediation: archive-flip happens INSIDE the lock
        # (so it doesn't race with reconciler or concurrent --force runs); AND we
        # symmetrically update the index row for the archived working-copy (so
        # index queries don't see two active working-copies for one projection).
        existing_archived_uid = None
        if existing and args.force:
            existing_content = existing.read_text()
            archived_content = existing_content.replace('state: active', 'state: archived', 1)
            with existing.open('w') as f:
                f.write(archived_content)
                f.flush()
                os.fsync(f.fileno())
            # Extract the archived working-copy's UID for index correction
            m = re.search(r'^uid:\s*([a-f0-9]{8})', existing_content, re.MULTILINE)
            if m:
                existing_archived_uid = m.group(1)
                _flip_index_row_state(studio_root, existing_archived_uid, 'archived')

        # Step 2 — hash the source binary
        source_hash, hash_function = IW.compute_hash(source_path)

        # Step 3 — extract content
        result = extract_docx(source_path)

        # Step 4 — mint working-copy UID
        if args.working_uid:
            uid = args.working_uid
        else:
            uid = IW.generate_uid()

        # Step 5 — Determine title + member_of
        # F2 fix (2026-06-12, 96b7d233): the document's own Title paragraph wins;
        # the filename stem is display-fallback only and never enters the body.
        source_titled = result.source_title_text is not None
        title = result.source_title_text or source_path.stem
        member_of_uid = None
        proj_member_of = proj_fm.get('member_of')
        if isinstance(proj_member_of, list) and proj_member_of:
            member_of_uid = proj_member_of[0]
        elif isinstance(proj_member_of, str):
            match = re.search(r'([a-f0-9]{8})', proj_member_of)
            if match:
                member_of_uid = match.group(1)

        # Step 6 — Auto-extract description from source if available (composes with v1.25.0
        # _extract_office_description). Optional; null/empty if not in source.
        description = IW._extract_office_description(source_path) or ''

        # Step 7 — author working-copy
        wc_path = write_working_copy(
            studio_root=studio_root,
            uid=uid,
            projection_uid=args.projection,
            title=title,
            source_filename=source_path.name,
            source_hash=source_hash,
            hash_function=hash_function,
            member_of_uid=member_of_uid,
            owner=args.executive or 'argus-cli',
            body=result.markdown_body,
            description=description,
            source_titled=source_titled,
        )

        # Step 8 — inline vault/00-index.jsonl sync (closes fa026415 sibling)
        append_index_row(
            studio_root=studio_root,
            uid=uid,
            title=title,
            owner=args.executive or 'argus-cli',
            working_copy_path=wc_path.relative_to(studio_root),
            member_of_uid=member_of_uid,
            source_filename=source_path.name,
        )

        # Step 9 — journal append with full extraction_stats schema per §3.5 step 7
        IW.append_journal(studio_root, {
            'event': 'working_copy_extracted',
            'working_copy_uid': uid,
            'projection_uid': args.projection,
            'source_hash': source_hash,
            'hash_function': hash_function,
            'extraction_tool_version': f'{TOOL_NAME}-v{TOOL_VERSION}',
            'timestamp': IW.now_iso(),
            'executive': args.executive or 'argus-cli',
            'run_uid': args.run_uid or 'cli-standalone',
            'extraction_stats': result.stats,
        })

        # Step 10 — user-facing summary surfaced at extract time (research concern #1)
        summary = format_extraction_summary(uid, wc_path.relative_to(studio_root), result.stats)
        print(summary)

        return 0


if __name__ == '__main__':
    sys.exit(main())
