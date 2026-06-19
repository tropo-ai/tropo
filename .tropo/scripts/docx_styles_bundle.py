"""docx_styles_bundle.py — minimal word/styles.xml bundling for tropo-export P2 path.

NEW shared module shipping in v1.31.0 per arch-spec [c5e2f8a3 v0.6 LOCKED].
Consumed by tropo-export.py v1.0.2's _build_minimal_docx_from_scratch (the P2
reconstruction path; fires when the source binary is missing and no --template
is provided).

Public API:
    build_styles_xml(original_styles: dict) -> str
        Construct minimal word/styles.xml from the original_styles projection
        dict (shape per office_styles.py:_extract_named_styles output;
        arch-spec 5a89297a §3.4 schema, shared via §3.5.5 Amendment 2
        naming-asymmetry).

    write_styles_to_docx(docx_path: Path, original_styles: dict) -> None
        Bundle the styles XML into a .docx ZIP at docx_path, registering
        the part in [Content_Types].xml and the relationship in
        word/_rels/document.xml.rels. Idempotent via content-comparison.

Module-boundary defensive validation per v0.5 D0 absorption — degrades
gracefully on field-level invalidity rather than emitting malformed OOXML.
XML construction uses xml.etree.ElementTree exclusively per v0.6 P1-6
hardening; f-string concatenation of XML strings is FORBIDDEN.

Stdlib-only.
"""

from __future__ import annotations

import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


# --------- OOXML constants -----------------------------------------------------

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
MC_NS = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'
REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'

CONTENT_TYPE_STYLES = (
    'application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml'
)
CONTENT_TYPE_DOCUMENT = (
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
)
REL_TYPE_STYLES = (
    'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles'
)

STYLES_REL_ID = 'rIdStyles'  # canonical id for the styles relationship

# Floor values when default_font is partial or absent (Calibri 11pt) per §3.1.3
DEFAULT_FONT_FAMILY = 'Calibri'
DEFAULT_FONT_SIZE_HALF_PT = 22

# 6-char hex color validation pattern per §3.1.4 P1-1 absorption
COLOR_HEX_PATTERN = re.compile(r'^[0-9A-Fa-f]{6}$')

# Register w:/mc: namespace prefixes once at module import. ET.register_namespace
# is a process-global registry, and the empty-prefix ('') can only hold one URI
# at a time — so CT_NS and REL_NS (both default-namespace consumers) must be
# registered INSIDE their respective helper functions immediately before
# tostring(). See _build_content_types_xml + _build_document_rels_xml.
# (v0.7 R2 D2-1 absorption — comment documents the load-bearing pattern that
# can't be hoisted; cold-boot-170 caught the visibility gap.)
ET.register_namespace('w', W_NS)
ET.register_namespace('mc', MC_NS)


# --------- helpers -------------------------------------------------------------

def _w(tag: str) -> str:
    """Namespaced w: tag for ET (Clark notation)."""
    return f'{{{W_NS}}}{tag}'


def _mc(tag: str) -> str:
    """Namespaced mc: tag for ET (Clark notation)."""
    return f'{{{MC_NS}}}{tag}'


def _normalize_style_id(style_id: str) -> str:
    """Strip whitespace + non-alphanumeric (except `-` and `_`); preserve case.

    Per spec §3.1.5 — OOXML w:styleId cannot contain whitespace; Word
    normalizes 'Heading 1' → 'Heading1'. This function does the same.
    """
    if not isinstance(style_id, str):
        return ''
    return ''.join(c for c in style_id if c.isalnum() or c in '-_')


def _is_valid_color(value) -> bool:
    """True if value is a 6-char hex string. Per §3.1.4 P1-1 absorption."""
    return isinstance(value, str) and bool(COLOR_HEX_PATTERN.match(value))


def _is_positive_int(value) -> bool:
    """True if value is a positive integer (>0).

    Per §3.1.4 P1-2 absorption. Note: rejects bool (isinstance(True, int) is
    True in Python, so we strip it explicitly).
    """
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


# --------- public API: build_styles_xml ----------------------------------------

def build_styles_xml(original_styles: dict) -> str:
    """Construct minimal word/styles.xml from original_styles projection dict.

    Per arch-spec [c5e2f8a3 v0.6 LOCKED] §3.1. Input shape per
    office_styles.py:_extract_named_styles + _extract_default_font output
    (5a89297a §3.4 schema; shared via §3.5.5 Amendment 2 naming-asymmetry).

    Module-boundary validation per §3.1 v0.5 D0 absorption + §3.1.4 field-level
    skip semantics — degrades gracefully on invalid field values rather than
    emitting malformed OOXML.

    Args:
        original_styles: dict with optional keys:
            - default_font: {family: str, size_half_pt: int, color: str (hex)}
            - named_styles: list of dicts each carrying id (req),
              name, font_family, font_size_half_pt, bold, color,
              spacing_before, spacing_after (all optional).
            - other keys (theme, page, headers_footers) are ignored by this fn.

    Returns:
        Well-formed XML string for word/styles.xml conforming to OOXML
        WordprocessingML schema.

    Raises:
        TypeError if original_styles is not a dict.
        TypeError if named_styles is a dict (pre-v1.28.0 legacy shape).
    """
    # Module-boundary validation per v0.5 D0 absorption
    if not isinstance(original_styles, dict):
        raise TypeError(
            f'expected dict, got {type(original_styles).__name__}'
        )

    named_styles = original_styles.get('named_styles', [])
    if isinstance(named_styles, dict):
        raise TypeError(
            'named_styles must be a list of dicts per '
            'office_styles.py:_extract_named_styles output; got dict — '
            'pre-v1.28.0 legacy shape; re-import the source .docx'
        )
    if named_styles is None:
        named_styles = []

    # Root <w:styles>. mc:Ignorable attribute is intentionally empty — the value
    # is irrelevant for our use case; the attribute's PRESENCE forces ET to emit
    # `xmlns:mc="..."` on the root, satisfying spec §3.1.3 namespace requirement.
    # (v0.7 R2 D1 absorption — disambiguate from "missing value to populate".)
    root = ET.Element(_w('styles'))
    root.set(_mc('Ignorable'), '')

    # --- <w:docDefaults> per spec §3.1.3 ---
    doc_defaults = ET.SubElement(root, _w('docDefaults'))
    rpr_default = ET.SubElement(doc_defaults, _w('rPrDefault'))
    rpr_default_rpr = ET.SubElement(rpr_default, _w('rPr'))

    default_font = original_styles.get('default_font')
    if not isinstance(default_font, dict):
        default_font = {}

    family = default_font.get('family')
    size_half_pt = default_font.get('size_half_pt')
    default_color = default_font.get('color')

    # Fallback floor per §3.1.3 v0.2 P1-5 absorption (Calibri 22hp)
    if not isinstance(family, str) or not family:
        family = DEFAULT_FONT_FAMILY
    if not _is_positive_int(size_half_pt):
        size_half_pt = DEFAULT_FONT_SIZE_HALF_PT

    ET.SubElement(rpr_default_rpr, _w('rFonts'), {
        _w('ascii'): family,
        _w('hAnsi'): family,
    })
    ET.SubElement(rpr_default_rpr, _w('sz'), {_w('val'): str(size_half_pt)})
    if _is_valid_color(default_color):
        ET.SubElement(rpr_default_rpr, _w('color'), {_w('val'): default_color.upper()})

    # Empty pPrDefault required per OOXML schema
    ppr_default = ET.SubElement(doc_defaults, _w('pPrDefault'))
    ET.SubElement(ppr_default, _w('pPr'))

    # --- <w:latentStyles> minimal floor per spec §3.1.3 ---
    ET.SubElement(root, _w('latentStyles'), {
        _w('defLockedState'): '0',
        _w('defUIPriority'): '99',
        _w('defSemiHidden'): '0',
        _w('defUnhideWhenUsed'): '0',
        _w('defQFormat'): '0',
        _w('count'): '0',
    })

    # --- per-style emission per spec §3.1.4 ---
    emitted_style_ids: set[str] = set()  # protect against normalized-id collisions

    for entry in named_styles:
        if not isinstance(entry, dict):
            continue  # defensive: skip non-dict entries

        entry_id = entry.get('id')
        if not entry_id or not isinstance(entry_id, str):
            continue  # entry-level skip per §3.1.4: missing id

        normalized_id = _normalize_style_id(entry_id)
        if not normalized_id:
            continue  # entry-level skip per §3.1.4: empty after normalization
        if normalized_id in emitted_style_ids:
            continue  # collision protection — Word rejects duplicate styleIds
        emitted_style_ids.add(normalized_id)

        style_attrs = {
            _w('type'): 'paragraph',
            _w('styleId'): normalized_id,
        }
        # v0.7.1 R3 P1-066-A absorption: mark the Normal paragraph style as default
        # per ECMA-376 §17.7.4.17 — every well-formed Word document MUST have exactly
        # one paragraph style with w:default="1" so unstyled <w:p> elements resolve.
        # Without this, python-docx + strict OOXML validators reject the document
        # (Word tolerates via built-in fallback). Detection: normalized id is
        # "Normal" case-insensitively.
        if normalized_id.lower() == 'normal':
            style_attrs[_w('default')] = '1'
        style_elem = ET.SubElement(root, _w('style'), style_attrs)

        # <w:name> — carry original entry.name faithfully; fall back to entry.id
        name_val = entry.get('name')
        if not isinstance(name_val, str) or not name_val:
            name_val = entry_id
        ET.SubElement(style_elem, _w('name'), {_w('val'): name_val})

        # --- <w:rPr> field-level emission (skip-or-default per §3.1.4) ---
        font_family = entry.get('font_family')
        font_size = entry.get('font_size_half_pt')
        bold = entry.get('bold')
        color = entry.get('color')

        has_any_rpr_field = (
            (isinstance(font_family, str) and font_family) or
            _is_positive_int(font_size) or
            bold is True or  # strict bool check (rejects truthy non-bool)
            _is_valid_color(color)
        )

        if has_any_rpr_field:
            style_rpr = ET.SubElement(style_elem, _w('rPr'))
            if isinstance(font_family, str) and font_family:
                ET.SubElement(style_rpr, _w('rFonts'), {
                    _w('ascii'): font_family,
                    _w('hAnsi'): font_family,
                })
            if _is_positive_int(font_size):
                ET.SubElement(style_rpr, _w('sz'), {_w('val'): str(font_size)})
            if bold is True:
                ET.SubElement(style_rpr, _w('b'))
            if _is_valid_color(color):
                ET.SubElement(style_rpr, _w('color'), {_w('val'): color.upper()})

        # --- <w:pPr> spacing emission ---
        spacing_before = entry.get('spacing_before')
        spacing_after = entry.get('spacing_after')
        if _is_positive_int(spacing_before) or _is_positive_int(spacing_after):
            style_ppr = ET.SubElement(style_elem, _w('pPr'))
            spacing_attrs = {}
            if _is_positive_int(spacing_before):
                spacing_attrs[_w('before')] = str(spacing_before)
            if _is_positive_int(spacing_after):
                spacing_attrs[_w('after')] = str(spacing_after)
            ET.SubElement(style_ppr, _w('spacing'), spacing_attrs)

    # Serialize with XML declaration; ET auto-emits xmlns:w + xmlns:mc on root
    return ET.tostring(
        root, encoding='utf-8', xml_declaration=True
    ).decode('utf-8')


# --------- private: canonical Content_Types + rels -----------------------------

def _build_content_types_xml() -> str:
    """Build canonical [Content_Types].xml per spec §3.1.1.

    NO <Default Extension="xml"> (creates non-conformant conflict with the
    styles Override per v0.2 P0-3 absorption). Default for rels + two Overrides
    for document.xml + styles.xml.
    """
    # Register default namespace (empty prefix) once; harmless on re-call
    ET.register_namespace('', CT_NS)
    root = ET.Element(f'{{{CT_NS}}}Types')
    ET.SubElement(root, f'{{{CT_NS}}}Default', {
        'Extension': 'rels',
        'ContentType': 'application/vnd.openxmlformats-package.relationships+xml',
    })
    ET.SubElement(root, f'{{{CT_NS}}}Override', {
        'PartName': '/word/document.xml',
        'ContentType': CONTENT_TYPE_DOCUMENT,
    })
    ET.SubElement(root, f'{{{CT_NS}}}Override', {
        'PartName': '/word/styles.xml',
        'ContentType': CONTENT_TYPE_STYLES,
    })
    return ET.tostring(
        root, encoding='utf-8', xml_declaration=True
    ).decode('utf-8')


def _build_document_rels_xml(existing_rels_bytes: Optional[bytes] = None) -> str:
    """Build canonical word/_rels/document.xml.rels per spec §3.1.2.

    If existing_rels_bytes is supplied, preserves non-styles relationships
    and ensures the styles relationship is present (idempotent).
    Otherwise emits a fresh rels file containing only the styles relationship.
    """
    ET.register_namespace('', REL_NS)
    preserved_rels = []
    if existing_rels_bytes:
        try:
            existing_root = ET.fromstring(existing_rels_bytes)
            for child in existing_root:
                # Strip namespace prefix for tag comparison
                tag_local = child.tag.split('}')[-1]
                if tag_local != 'Relationship':
                    continue
                rel_type = child.get('Type', '')
                if rel_type == REL_TYPE_STYLES:
                    continue  # drop existing styles rel; we re-emit canonical
                preserved_rels.append(child)
        except ET.ParseError:
            # Existing rels malformed; rebuild from scratch (defensive)
            preserved_rels = []

    root = ET.Element(f'{{{REL_NS}}}Relationships')
    for rel in preserved_rels:
        root.append(rel)
    ET.SubElement(root, f'{{{REL_NS}}}Relationship', {
        'Id': STYLES_REL_ID,
        'Type': REL_TYPE_STYLES,
        'Target': 'styles.xml',
    })
    return ET.tostring(
        root, encoding='utf-8', xml_declaration=True
    ).decode('utf-8')


# --------- public API: write_styles_to_docx ------------------------------------

def write_styles_to_docx(docx_path: Path, original_styles: dict) -> None:
    """Bundle word/styles.xml + canonical [Content_Types].xml + amended
    word/_rels/document.xml.rels into the .docx ZIP at docx_path.

    Per arch-spec [c5e2f8a3 v0.6 LOCKED] §3.1.

    Uses the rebuild-the-ZIP + atomic-rename pattern per v0.5 P0-2 absorption
    — stdlib zipfile cannot overwrite entries in place; append mode produces
    ghost duplicates.

    Idempotency is content-comparison (NOT presence-check) per v0.5 P0-1
    absorption: existing word/styles.xml + [Content_Types].xml +
    word/_rels/document.xml.rels are byte-compared against the canonical
    shapes; rewrites only when content differs. Avoids unnecessary ZIP
    rebuilds when the bundle is already canonical.

    Args:
        docx_path: Path to an existing .docx file.
        original_styles: dict per build_styles_xml input contract.

    Raises:
        FileNotFoundError if docx_path does not exist.
        zipfile.BadZipFile if docx_path is not a valid ZIP.
        TypeError propagated from build_styles_xml on invalid original_styles
        or pre-v1.28.0 legacy named_styles dict shape.
        OSError if the atomic rename fails.
    """
    if not docx_path.exists():
        raise FileNotFoundError(f'docx_path does not exist: {docx_path}')

    target_styles_xml = build_styles_xml(original_styles)
    target_content_types_xml = _build_content_types_xml()

    # Read all existing entries into memory (small files; .docx are typically <10MB)
    existing_entries: dict[str, bytes] = {}
    with zipfile.ZipFile(docx_path, 'r') as zf:
        for info in zf.infolist():
            existing_entries[info.filename] = zf.read(info.filename)

    # Build canonical rels (preserving any non-styles relationships)
    existing_rels_bytes = existing_entries.get('word/_rels/document.xml.rels')
    target_rels_xml = _build_document_rels_xml(existing_rels_bytes)

    # Content-comparison idempotency check per v0.5 P0-1
    target_styles_bytes = target_styles_xml.encode('utf-8')
    target_content_types_bytes = target_content_types_xml.encode('utf-8')
    target_rels_bytes = target_rels_xml.encode('utf-8')

    needs_rewrite = (
        existing_entries.get('word/styles.xml') != target_styles_bytes or
        existing_entries.get('[Content_Types].xml') != target_content_types_bytes or
        existing_entries.get('word/_rels/document.xml.rels') != target_rels_bytes
    )
    if not needs_rewrite:
        return  # idempotent: byte-identical content already present

    # Rebuild ZIP with updated entries; atomic rename on success
    tmp_path = docx_path.with_suffix(docx_path.suffix + '.tmp')
    try:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf_out:
            # Copy entries we're not overwriting
            for name, data in existing_entries.items():
                if name in (
                    'word/styles.xml',
                    '[Content_Types].xml',
                    'word/_rels/document.xml.rels',
                ):
                    continue
                zf_out.writestr(name, data)
            # Write canonical replacements
            zf_out.writestr('word/styles.xml', target_styles_xml)
            zf_out.writestr('[Content_Types].xml', target_content_types_xml)
            zf_out.writestr('word/_rels/document.xml.rels', target_rels_xml)
        # Atomic rename (os.replace is atomic on POSIX; near-atomic on Windows)
        os.replace(tmp_path, docx_path)
    except Exception:
        # Clean up tmp on any failure to avoid orphan files
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


# --------- CLI smoke-test entry point ------------------------------------------

if __name__ == '__main__':
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description=(
            'Smoke-test docx_styles_bundle against a JSON original_styles file '
            'and a .docx target. Production use: import this module from '
            'tropo-export.py.'
        )
    )
    parser.add_argument(
        '--styles-json', required=True,
        help='Path to a JSON file containing the original_styles dict.',
    )
    parser.add_argument(
        '--docx', required=False,
        help='Optional path to a .docx file; if supplied, write the styles '
             'bundle into it (in place via rebuild + atomic rename).',
    )
    parser.add_argument(
        '--print-xml', action='store_true',
        help='Print the generated word/styles.xml to stdout (no .docx write).',
    )
    args = parser.parse_args()

    styles_path = Path(args.styles_json).resolve()
    if not styles_path.exists():
        print(f'ERROR: styles-json does not exist: {styles_path}', file=sys.stderr)
        sys.exit(1)

    try:
        original_styles = json.loads(styles_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        print(f'ERROR: styles-json malformed: {e}', file=sys.stderr)
        sys.exit(1)

    try:
        if args.print_xml:
            print(build_styles_xml(original_styles))
        elif args.docx:
            write_styles_to_docx(Path(args.docx).resolve(), original_styles)
            print(f'Styles bundle written to: {args.docx}')
        else:
            # Default: just print the XML for inspection
            print(build_styles_xml(original_styles))
    except TypeError as e:
        print(f'ERROR: validation failed: {e}', file=sys.stderr)
        sys.exit(2)
