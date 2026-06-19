"""
---
uid: d1f2420d
name: office_styles
type: tool
title: office_styles
description: Shared library module exposing extract_office_styles() — the single source of truth for how Tropo extracts Office (.docx) style metadata. Imported by import-walker.py create-sidecar, tropo-register-template.py, and tropo-backfill-styles.py.
state: active
status: active
stage: build
owner: argus-a62
member_of:
- e3cde3f4
created: 2026-05-14
modified: 2026-05-14
created_by: argus-a62
modified_by: argus-a62
schema_version: 2
extraction_scope: ship
domain: Extract structured style metadata from .docx binaries — page size + margins, default font, theme colors, named paragraph styles, headers/footers, sections count, special features (macros / embedded fonts / custom XML / watermarks).
spawnable_by:
- import-walker.py
- tropo-register-template.py
- tropo-backfill-styles.py
transport: library
implementation_kind: python-script
script_path: vault/tools/d1f2420d.py
language: python
version: 1.0.0
destructive: 'false'
audit_required: 'false'
writes_scope: []
reads_scope:
- '**/*.docx'
governance_category: library
domain_tags:
- office
- docx
- style-extraction
- shared-library
- v1.28.0-stream-b
trigger_description: 'Reach for this when authoring a script that needs to extract Office style metadata from a .docx binary. Pass an absolute Path; the function returns a dict matching arch-spec 5a89297a §3.4 schema, or None if the file isn''t a recognized .docx or extraction fails. Caller is responsible for resolving relative paths to absolute Paths before invocation (per spec v0.5 sa.cold-boot-007 X3 — function does NOT re-resolve). v1.28.0 scope: .docx only; .xlsx/.pptx defer to their own future cycles per spec §5.6.'
governed_by: d5e1b4a3
capsule_version: '2.5'
aligned_with:
- 5a89297a
tags:
- tool
- library
- python
- office-styles
- docx
- shared-module
- v1.28.0-stream-b
file_ext: md
subsystem_hub:
- 8dd772a0
---
"""
from __future__ import annotations

"""Office style metadata extraction — shared library module.

The single source of truth for "how Tropo extracts Office style metadata."
Used by:
- import-walker.py create-sidecar (populates external-artifact.original_styles per arch-spec 5a89297a §3.5.5 Amendment 2)
- tropo-register-template.py (populates docx-template.extracted_styles per arch-spec 5a89297a §3.6 step 4)
- tropo-backfill-styles.py (migration gesture per arch-spec 5a89297a §3.13)

The output schema is declared in arch-spec 5a89297a §3.4 (extracted_styles structure).
v1.28.0 scope: .docx only. Other Office types (.xlsx, .pptx) defer to their own
future cycles per arch-spec §5.6 cross-binary scope expansion.

Per arch-spec §3.5.5 Amendment 2 + v0.5 closes-sa.cold-boot-007-X3:
- Caller resolves relative paths to absolute Path before calling.
- This function does NOT re-resolve relative paths against any anchor.
- Returns None on non-Office binaries OR extraction failure (fail-soft;
  callers treat None as a non-fatal signal — do NOT fail create-sidecar).
"""


import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Optional


# OOXML namespaces — pinned per the WordprocessingML spec
_NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'pkg': 'http://schemas.microsoft.com/office/2006/xmlPackage',
}

# Required parts inside a well-formed .docx ZIP
_REQUIRED_DOCX_PARTS = ('word/document.xml',)

# Maximum header/footer text preview length per arch-spec §3.4
_MAX_PREVIEW_CHARS = 200


def extract_office_styles(file_path: Path) -> Optional[dict]:
    """Extract style metadata from a .docx binary.

    Returns the structured `extracted_styles` dict per arch-spec 5a89297a §3.4 schema,
    or None if the file isn't a recognized Office binary or extraction fails.

    v1.28.0 scope: .docx only. .xlsx/.pptx defer to their own future cycles.

    Path resolution (v0.5 per arch-spec §3.5.5 Amendment 2 — closes sa.cold-boot-007 X3):
    the caller MUST resolve relative paths to an absolute Path before invocation;
    this function does NOT re-resolve relative paths against any anchor.

    Args:
        file_path: Absolute Path to the .docx file.

    Returns:
        Dict matching §3.4 schema (page / default_font / theme / named_styles /
        headers_footers / sections_count / special_features), OR None.
    """
    # Scope-discipline guard per arch-spec §3.5.5 Amendment 2:
    # if extension is NOT .docx, skip silently (return None).
    if file_path.suffix.lower() != '.docx':
        return None

    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            names = set(zf.namelist())
            # Validate it's a well-formed .docx (has word/document.xml)
            if not all(p in names for p in _REQUIRED_DOCX_PARTS):
                return None

            return {
                'page': _extract_page(zf, names),
                'default_font': _extract_default_font(zf, names),
                'theme': _extract_theme(zf, names),
                'named_styles': _extract_named_styles(zf, names),
                'headers_footers': _extract_headers_footers(zf, names),
                'sections_count': _extract_sections_count(zf, names),
                'special_features': _extract_special_features(zf, names),
            }
    except (zipfile.BadZipFile, ET.ParseError, OSError):
        # Per arch-spec §3.5.5 Amendment 2 failure modes:
        # corrupted XML or unreadable binary → return None; caller logs + omits.
        return None


# -------- per-section extractors --------------------------------------------

def _extract_page(zf: zipfile.ZipFile, names: set) -> dict:
    """Extract page size + margins from section properties in word/document.xml.

    Defaults if not declared: US Letter (8.5" × 11" = 12240 × 15840 DXA),
    1" margins (1440 DXA), portrait orientation.
    """
    page = {
        'width_dxa': 12240,
        'height_dxa': 15840,
        'orientation': 'portrait',
        'margins_dxa': {'top': 1440, 'bottom': 1440, 'left': 1440, 'right': 1440},
    }
    try:
        with zf.open('word/document.xml') as f:
            tree = ET.parse(f)
            # Find the first sectPr (final section's properties typically govern overall layout)
            for sectPr in tree.iter('{%s}sectPr' % _NS['w']):
                pgSz = sectPr.find('w:pgSz', _NS)
                if pgSz is not None:
                    w = pgSz.get('{%s}w' % _NS['w'])
                    h = pgSz.get('{%s}h' % _NS['w'])
                    orient = pgSz.get('{%s}orient' % _NS['w'])
                    if w and w.isdigit():
                        page['width_dxa'] = int(w)
                    if h and h.isdigit():
                        page['height_dxa'] = int(h)
                    if orient in ('portrait', 'landscape'):
                        page['orientation'] = orient
                pgMar = sectPr.find('w:pgMar', _NS)
                if pgMar is not None:
                    for k_xml, k_out in (('top', 'top'), ('bottom', 'bottom'),
                                         ('left', 'left'), ('right', 'right')):
                        v = pgMar.get('{%s}%s' % (_NS['w'], k_xml))
                        if v and v.lstrip('-').isdigit():
                            page['margins_dxa'][k_out] = int(v)
                break  # first sectPr is sufficient for v1.28.0 scope
    except (ET.ParseError, KeyError, OSError):
        pass  # fall through with defaults
    return page


def _extract_default_font(zf: zipfile.ZipFile, names: set) -> dict:
    """Extract default font family + size from word/styles.xml docDefaults.

    Defaults if not declared: Calibri 11pt (22 half-points), black (000000).
    """
    font = {'family': 'Calibri', 'size_half_pt': 22, 'color': '000000'}
    if 'word/styles.xml' not in names:
        return font
    try:
        with zf.open('word/styles.xml') as f:
            tree = ET.parse(f)
            root = tree.getroot()
            docDefaults = root.find('w:docDefaults', _NS)
            if docDefaults is not None:
                rPrDefault = docDefaults.find('w:rPrDefault/w:rPr', _NS)
                if rPrDefault is not None:
                    rFonts = rPrDefault.find('w:rFonts', _NS)
                    if rFonts is not None:
                        family = (rFonts.get('{%s}ascii' % _NS['w'])
                                  or rFonts.get('{%s}hAnsi' % _NS['w']))
                        if family:
                            font['family'] = family
                    sz = rPrDefault.find('w:sz', _NS)
                    if sz is not None:
                        val = sz.get('{%s}val' % _NS['w'])
                        if val and val.isdigit():
                            font['size_half_pt'] = int(val)
                    color = rPrDefault.find('w:color', _NS)
                    if color is not None:
                        val = color.get('{%s}val' % _NS['w'])
                        if val and val.lower() != 'auto':
                            font['color'] = val.upper()
    except (ET.ParseError, KeyError, OSError):
        pass
    return font


def _extract_theme(zf: zipfile.ZipFile, names: set) -> dict:
    """Extract primary + secondary theme colors from word/theme/theme1.xml.

    Defaults if not declared: Office 2013+ default theme colors.
    """
    theme = {'primary_color': '1F497D', 'secondary_color': '4F81BD'}
    theme_part = 'word/theme/theme1.xml'
    if theme_part not in names:
        return theme
    try:
        with zf.open(theme_part) as f:
            tree = ET.parse(f)
            root = tree.getroot()
            # Theme color scheme: a:clrScheme contains a:accent1 (primary) + a:accent2 (secondary)
            clrScheme = root.find('.//a:clrScheme', _NS)
            if clrScheme is not None:
                for accent_tag, out_key in (('a:accent1', 'primary_color'),
                                            ('a:accent2', 'secondary_color')):
                    accent = clrScheme.find(accent_tag, _NS)
                    if accent is not None:
                        srgb = accent.find('a:srgbClr', _NS)
                        if srgb is not None:
                            val = srgb.get('val')
                            if val:
                                theme[out_key] = val.upper()
                        else:
                            # Fall back to a:sysClr lastClr attribute (system color resolved value)
                            sysClr = accent.find('a:sysClr', _NS)
                            if sysClr is not None:
                                last = sysClr.get('lastClr')
                                if last:
                                    theme[out_key] = last.upper()
    except (ET.ParseError, KeyError, OSError):
        pass
    return theme


def _extract_named_styles(zf: zipfile.ZipFile, names: set) -> list:
    """Extract named styles from word/styles.xml.

    Captures each <w:style w:type="paragraph"> with type-paragraph + non-default
    properties. Surfaces id, name, font family, font size, bold, color, and
    paragraph spacing-before/after when declared. Order: as encountered in the
    styles.xml document order (stable across rebuilds).
    """
    styles = []
    if 'word/styles.xml' not in names:
        return styles
    try:
        with zf.open('word/styles.xml') as f:
            tree = ET.parse(f)
            root = tree.getroot()
            for style in root.findall('w:style', _NS):
                stype = style.get('{%s}type' % _NS['w'])
                if stype != 'paragraph':
                    # v1.28.0 scope: paragraph styles only (character/table/numbering defer)
                    continue
                sid = style.get('{%s}styleId' % _NS['w'])
                if not sid:
                    continue
                entry = {'id': sid}
                name_el = style.find('w:name', _NS)
                if name_el is not None:
                    val = name_el.get('{%s}val' % _NS['w'])
                    if val:
                        entry['name'] = val
                rPr = style.find('w:rPr', _NS)
                if rPr is not None:
                    rFonts = rPr.find('w:rFonts', _NS)
                    if rFonts is not None:
                        family = (rFonts.get('{%s}ascii' % _NS['w'])
                                  or rFonts.get('{%s}hAnsi' % _NS['w']))
                        if family:
                            entry['font_family'] = family
                    sz = rPr.find('w:sz', _NS)
                    if sz is not None:
                        val = sz.get('{%s}val' % _NS['w'])
                        if val and val.isdigit():
                            entry['font_size_half_pt'] = int(val)
                    b = rPr.find('w:b', _NS)
                    if b is not None:
                        # Default w:b with no val attribute means true
                        val = b.get('{%s}val' % _NS['w'])
                        entry['bold'] = val != '0' and val != 'false'
                    color = rPr.find('w:color', _NS)
                    if color is not None:
                        val = color.get('{%s}val' % _NS['w'])
                        if val and val.lower() != 'auto':
                            entry['color'] = val.upper()
                pPr = style.find('w:pPr', _NS)
                if pPr is not None:
                    spacing = pPr.find('w:spacing', _NS)
                    if spacing is not None:
                        before = spacing.get('{%s}before' % _NS['w'])
                        after = spacing.get('{%s}after' % _NS['w'])
                        if before and before.lstrip('-').isdigit():
                            entry['spacing_before'] = int(before)
                        if after and after.lstrip('-').isdigit():
                            entry['spacing_after'] = int(after)
                styles.append(entry)
    except (ET.ParseError, KeyError, OSError):
        pass
    return styles


def _extract_headers_footers(zf: zipfile.ZipFile, names: set) -> dict:
    """Extract presence + text preview of headers and footers.

    Scans word/header*.xml + word/footer*.xml. Returns boolean presence flags
    plus up-to-200-char text preview per arch-spec §3.4 (null if no static text).
    """
    info = {
        'has_header': False,
        'has_footer': False,
        'header_text_preview': None,
        'footer_text_preview': None,
    }
    for name in names:
        if name.startswith('word/header') and name.endswith('.xml'):
            info['has_header'] = True
            preview = _read_part_text_preview(zf, name)
            # Use the FIRST non-empty preview encountered
            if preview and not info['header_text_preview']:
                info['header_text_preview'] = preview
        elif name.startswith('word/footer') and name.endswith('.xml'):
            info['has_footer'] = True
            preview = _read_part_text_preview(zf, name)
            if preview and not info['footer_text_preview']:
                info['footer_text_preview'] = preview
    return info


def _read_part_text_preview(zf: zipfile.ZipFile, part: str) -> Optional[str]:
    """Read a header/footer XML part and return concatenated text up to 200 chars."""
    try:
        with zf.open(part) as f:
            tree = ET.parse(f)
            root = tree.getroot()
            texts = []
            for t in root.iter('{%s}t' % _NS['w']):
                if t.text:
                    texts.append(t.text)
            combined = ' '.join(texts).strip()
            if not combined:
                return None
            combined = re.sub(r'\s+', ' ', combined)
            if len(combined) > _MAX_PREVIEW_CHARS:
                combined = combined[:_MAX_PREVIEW_CHARS - 3].rstrip() + '...'
            return combined
    except (ET.ParseError, KeyError, OSError):
        return None


def _extract_sections_count(zf: zipfile.ZipFile, names: set) -> int:
    """Count <w:sectPr> elements in word/document.xml — number of sections."""
    if 'word/document.xml' not in names:
        return 1
    try:
        with zf.open('word/document.xml') as f:
            tree = ET.parse(f)
            sectPrs = list(tree.iter('{%s}sectPr' % _NS['w']))
            return max(len(sectPrs), 1)
    except (ET.ParseError, KeyError, OSError):
        return 1


def _extract_special_features(zf: zipfile.ZipFile, names: set) -> dict:
    """Detect macros, embedded fonts, custom XML, watermarks via namespace scan.

    Detection heuristics:
    - has_macros: presence of word/vbaProject.bin
    - has_embedded_fonts: presence of any word/fonts/*.{ttf,otf,eot,woff,woff2}
    - has_custom_xml: presence of customXml/ entries
    - has_watermark: scan word/header*.xml content for w:pict with watermark VML
    """
    features = {
        'has_macros': False,
        'has_embedded_fonts': False,
        'has_custom_xml': False,
        'has_watermark': False,
    }
    embedded_font_ext = ('.ttf', '.otf', '.eot', '.woff', '.woff2')
    for name in names:
        lower = name.lower()
        if name == 'word/vbaProject.bin':
            features['has_macros'] = True
        elif name.startswith('word/fonts/') and lower.endswith(embedded_font_ext):
            features['has_embedded_fonts'] = True
        elif name.startswith('customXml/'):
            features['has_custom_xml'] = True
    # Watermark detection: look in headers for VML pict with id "PowerPlusWaterMarkObject"
    # OR for w:pict elements containing v:shape with type "_x0000_t75" — heuristic; not exhaustive
    if any(n.startswith('word/header') and n.endswith('.xml') for n in names):
        for name in names:
            if not (name.startswith('word/header') and name.endswith('.xml')):
                continue
            try:
                with zf.open(name) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    if 'WaterMark' in content or 'watermark' in content.lower():
                        features['has_watermark'] = True
                        break
            except (KeyError, OSError):
                continue
    return features


# -------- CLI smoke-test entry point ----------------------------------------

if __name__ == '__main__':
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Smoke-test extract_office_styles() against a .docx file. "
                    "Production use: import this module from other scripts."
    )
    parser.add_argument('path', help="Absolute path to a .docx file")
    args = parser.parse_args()

    p = Path(args.path).resolve()
    if not p.exists():
        print(f"ERROR: file does not exist: {p}", file=sys.stderr)
        sys.exit(1)

    result = extract_office_styles(p)
    if result is None:
        print(f"NULL — file is not a recognized .docx or extraction failed: {p}", file=sys.stderr)
        sys.exit(2)

    print(json.dumps(result, indent=2, default=str))
