#!/usr/bin/env python3
"""
---
uid: ce9dbcc2
name: tropo-export
type: tool
title: tropo-export
description: 'Export a markdown working-copy to a .docx via dual-path body-swap. Default = preservation export (P1 source-binary scaffold → P2 original_styles reconstruction → fail loud). Override --template <uid> = transformation export. Both paths: heading-anti-collision rule, tracked-changes orphan-marker detection, journal export_generated event.'
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
domain: 'Export an agent-edited markdown working-copy back to a .docx deliverable. The deliverable side of the v1.28.0 import → work → export loop. Two paths: preservation (source binary as scaffold; max fidelity) vs transformation (registered template as scaffold).'
spawnable_by:
- all-executives
- user
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/ce9dbcc2.py --working-copy <uid> [--template <uid>] [--output-path <path>] [--title <string>] [--accept-binary-drift]
script_path: vault/tools/ce9dbcc2.py
language: python
version: 1.0.0
destructive: 'false'
audit_required: 'true'
writes_scope:
- 02-outbox/docx/**
- vault/files/<working-copy-uid>.md (last_exported_* fields only)
- .tropo-studio/reconciler/journal.jsonl
reads_scope:
- vault/files/<working-copy-uid>.md
- vault/files/<projection-uid>.md
- vault/files/<template-uid>.md
- .tropo-studio/templates/**
- external-work/**/*.docx
governance_category: lifecycle
domain_tags:
- export
- docx
- preservation
- transformation
- body-swap
- ooxml
- user-facing
- v1.28.0-stream-b
- mcp-aligned
trigger_description: 'Reach for this when a user wants to ship an agent-edited working-copy back as a .docx deliverable. Default invocation (no --template flag) = PRESERVATION export: open the working-copy''s source binary as scaffold, swap body content, save to 02-outbox/docx/. Preserves header/footer/theme/custom-XML/macros/embedded-fonts/watermarks/section-properties — max fidelity because nothing is reconstructed. Override (--template <uid>) = TRANSFORMATION export: open registered template binary as scaffold; same body-swap mechanism. Use case for preservation: ''send David''s review back to David in his own format.'' Use case for transformation: ''convert this content to MindBridge house style.'' Mutual exclusion: --template skips P1/P2 entirely; the flag is the path-selector. Tracked-changes orphan-marker check (§3.7 step 5.5 v0.5) on P1 path: preserves source markers + warns at export time (per RC-1 walk Mike-A62 2026-05-14 preserve+warn doctrine).'
governed_by: d5e1b4a3
capsule_version: '2.5'
aligned_with:
- 5a89297a
tags:
- tool
- cli
- python
- tropo-export
- docx-export
- preservation-export
- transformation-export
- body-swap
- ooxml
- user-facing
- mcp-aligned
- v1.28.0-stream-b
file_ext: md
subsystem_hub:
- 76bab75f
---
"""
from __future__ import annotations

"""Tropo working-copy → .docx export — user-facing CLI for the deliverable side of the loop.

Exports a markdown working-copy to a .docx via one of two paths per arch-spec
[5a89297a v0.5](../../vault/files/5a89297a.md) §3.7 (v0.4 amendment + v0.5 closures):

  - Default (no --template): PRESERVATION EXPORT
      P1: source-binary as scaffold (max fidelity) — preserves header/footer/theme/
          custom-XML/macros/embedded-fonts/watermarks/section-properties; replaces body.
      P2: original_styles-based reconstruction (if source binary missing) — lower fidelity.
      Fail loud if both missing.
  - --template <uid>: TRANSFORMATION EXPORT
      Registered template binary as scaffold; same body-swap mechanism as P1.

Usage:
    tropo-export.py --working-copy <uid> [--template <uid>] \\
        [--output-path <path>] [--title <string>] [--run-uid <uid>] [--executive <slug>]

Author: argus-a62
Owner: argus
Spec: vault/files/5a89297a.md
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

# Co-located in .tropo/scripts/ — provides write_styles_to_docx for P2 path
# (v1.31.0 amendment per spec [c5e2f8a3 v0.6] §3.2 Edit 2; v0.7 R2 D2-3
# absorption — hoisted from inside _build_minimal_docx_from_scratch).
# v1.56 Lane S inline fix by metis-g62 2026-05-27: import deferred to after
# sys.path setup (lines ~155+) because docx_styles_bundle stays at .tropo/scripts/
# under partial v1.56 migration (not yet moved to vault/tools/<uid>.py).
# See deferred import below at "Shared modules" block.

try:
    import yaml as _yaml_lib
    _HAS_YAML = True
except ImportError:
    _yaml_lib = None
    _HAS_YAML = False


TOOL_NAME = 'tropo-export'
TOOL_VERSION = '1.1.0'   # v1.0.0 = v1.28.0 ship; v1.0.1 = v1.28.0.1 bundled remediation
                          # (closes sa.skeptic-009 ship-time gauntlet P0-1 markdown table support
                          # + P0-2 mc:Ignorable namespace preservation via targeted body splice
                          # + P1-4 live-scaffold style re-extraction for P1 path);
                          # v1.0.2 = v1.31.0 Stream D ship (P2 styles-bundle proper; closes
                          # v1.28.0.1 known-gap — constant was NOT bumped at ship per substrate-
                          # honesty observation in v1.32.0 spec [900d41e0] v0.4);
                          # v1.0.3 = v1.32.0 Stream E P1 bundle (P1-1 P1-path heading anti-collision
                          # degeneracy guard + P1-2 update_working_copy_export_fields final-fallback
                          # insert + caller emits working_copy_frontmatter_malformed event)

# Substrate paths
LOCK_RELPATH = '.tropo-studio/reconciler/.lock'
JOURNAL_RELPATH = '.tropo-studio/reconciler/journal.jsonl'
VAULT_INDEX_RELPATH = 'vault/00-index.jsonl'
LOCK_STALE_SECONDS = 3600

# OOXML namespaces
_W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
_NS = {'w': _W_NS}
# Register so ET.tostring emits 'w:' prefix instead of expanded ns0:
ET.register_namespace('w', _W_NS)
ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')


# Shared modules
# v1.56 Lane S: script relocated to vault/tools/; lib/ imports from .tropo/scripts/
_SCRIPT_DIR = Path(__file__).resolve().parents[2] / '.tropo' / 'scripts'
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# v1.56 Lane S inline fix by metis-g62 2026-05-27: deferred docx_styles_bundle import
# (was at line ~118 pre-fix; relocated here so sys.path setup above runs first).
import docx_styles_bundle  # noqa: E402


# ==========================================================================
# Helpers (lock, studio root, frontmatter, UID, time)
# ==========================================================================

def resolve_studio_root(arg_path=None):
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
    return secrets.token_hex(4)


def parse_frontmatter(file_path):
    """Parse a markdown file's YAML frontmatter into a dict.

    Uses PyYAML if available (handles nested lists-of-dicts cleanly under
    extracted_styles/original_styles). Falls back to a minimal hand-rolled parser
    for environments without PyYAML — the fallback handles top-level scalars +
    flat lists but degrades gracefully on nested structures.
    """
    if not file_path.exists():
        return {}
    text = file_path.read_text()
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)

    # Prefer PyYAML when available — handles nested list-of-dict structures
    # under extracted_styles.named_styles correctly. v0.5.1 fix surfaced
    # during Stream B transformation-export smoke-test 2026-05-14.
    if _HAS_YAML:
        try:
            parsed = _yaml_lib.safe_load(block)
            if isinstance(parsed, dict):
                return parsed
        except _yaml_lib.YAMLError:
            pass  # fall through to hand-rolled parser

    fm = {}
    # Simple line-by-line parse — handles flat scalars + simple lists + nested blocks for original_styles
    current_key = None
    current_list = None
    nested_block_key = None
    nested_block_lines = []
    indent_level = 0

    for line in block.split('\n'):
        if not line.strip() or line.strip().startswith('#'):
            if nested_block_key is not None and (line.strip() == '' or line.startswith('  ')):
                nested_block_lines.append(line)
            continue

        # Detect end of a nested block
        if nested_block_key is not None and not line.startswith(' '):
            fm[nested_block_key] = _try_parse_nested_styles_block('\n'.join(nested_block_lines))
            nested_block_key = None
            nested_block_lines = []

        if nested_block_key is not None:
            nested_block_lines.append(line)
            continue

        # Top-level key
        m_kv = re.match(r'^(\w+):\s*(.*)$', line)
        if m_kv:
            key, value = m_kv.group(1), m_kv.group(2).strip()
            if not value:
                # Could be the start of a list OR a nested block
                if key in ('original_styles', 'extracted_styles'):
                    nested_block_key = key
                    continue
                current_key = key
                current_list = []
                fm[key] = current_list
            else:
                fm[key] = _parse_scalar(value)
                current_key = None
                current_list = None
        elif line.startswith('  - ') and current_list is not None:
            current_list.append(_parse_scalar(line[4:].strip()))

    # Close out any pending nested block
    if nested_block_key is not None:
        fm[nested_block_key] = _try_parse_nested_styles_block('\n'.join(nested_block_lines))

    return fm


def _try_parse_nested_styles_block(text):
    """Best-effort parse of an indented original_styles or extracted_styles block.

    Returns a dict (possibly partial). Used to read the §3.4 schema content back from
    a projection or template entry without external YAML dependency.
    """
    result = {}
    stack = [result]
    indents = [0]
    # Process line-by-line
    current_list = None
    last_indent = 0

    for raw in text.split('\n'):
        if not raw.strip() or raw.strip().startswith('#'):
            continue
        # Indent depth (in 2-space units)
        stripped = raw.lstrip(' ')
        indent = (len(raw) - len(stripped)) // 2

        # Pop stack to match indent
        while indents and indents[-1] >= indent and len(indents) > 1:
            stack.pop()
            indents.pop()
            current_list = None

        if stripped.startswith('- '):
            # List item — either start of list or continuation
            if current_list is None:
                # Need to attach a new list to the parent at this indent
                # The previous key would be the list anchor; we lost it though
                # Fall back: append as bare items at this indent level
                pass
            # Parse the item — may be `- key: value`
            item_body = stripped[2:]
            if ':' in item_body:
                # Start of a dict item in a list
                k, _, v = item_body.partition(':')
                v = v.strip()
                if v:
                    item = {k.strip(): _parse_scalar(v)}
                else:
                    item = {k.strip(): {}}
                if current_list is not None:
                    current_list.append(item)
            else:
                if current_list is not None:
                    current_list.append(_parse_scalar(item_body))
            continue

        m = re.match(r'^(\w+):\s*(.*)$', stripped)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()

        if value == '':
            # Could be dict-start or list-start
            new_dict = {}
            stack[-1][key] = new_dict
            stack.append(new_dict)
            indents.append(indent)
            current_list = None
        elif value == '[]':
            stack[-1][key] = []
            current_list = None
        else:
            stack[-1][key] = _parse_scalar(value)
            current_list = None

    return result


def _parse_scalar(value):
    """Parse a YAML scalar value — string, int, bool, null."""
    value = value.strip()
    if value == '':
        return ''
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value == 'true':
        return True
    if value == 'false':
        return False
    if value == 'null' or value == '~':
        return None
    if re.match(r'^-?\d+$', value):
        return int(value)
    if re.match(r'^-?\d+\.\d+$', value):
        return float(value)
    return value


# ==========================================================================
# Reconciler lock
# ==========================================================================

class ReconcilerLock:
    def __init__(self, studio_root, executive='cli-user'):
        self.studio_root = studio_root
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
                        f"Reconciler lock held: {self.lock_path.read_text().strip()} "
                        f"(age {age:.0f}s)"
                    )
            except OSError:
                pass
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {now_iso()} {self.executive}".encode())
            os.close(fd)
        except FileExistsError:
            raise SystemExit(f"Reconciler lock race at {self.lock_path}")
        return self

    def __exit__(self, *a):
        try:
            self.lock_path.unlink()
        except OSError:
            pass


# ==========================================================================
# Working-copy + template + projection resolution
# ==========================================================================

def load_entry(studio_root, uid):
    """Load a vault entry's frontmatter + body. Returns (fm_dict, body_str, path)."""
    p = studio_root / 'vault' / 'files' / f'{uid}.md'
    if not p.exists():
        raise SystemExit(f"vault/files/{uid}.md not found")
    fm = parse_frontmatter(p)
    text = p.read_text()
    m = re.match(r'^---\s*\n.*?\n---\s*\n(.*)$', text, re.DOTALL)
    body = m.group(1) if m else text
    return fm, body, p


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


# ==========================================================================
# S1.3 diff-aware preservation helpers
# ==========================================================================

def _sha8(text: str) -> str:
    """SHA-256 of text → first 8 hex chars (matches tropo-extract v1.1.0 contract)."""
    import hashlib as _hl
    return _hl.sha256(text.encode()).hexdigest()[:8]


_ANCHOR_RE = re.compile(r'<!--\s*tropo:block\s+idx=(\d+)\s+hash=([0-9a-f]{8})\s*-->\n?')


def _parse_anchored_body(body):
    """Split body on tropo:block anchor comments.

    Returns [(anchor_dict|None, text)] pairs. anchor is None for content before
    the first anchor or content between anchor blocks added by the user (new paragraphs).
    anchor_dict = {'idx': int, 'hash': str}.
    """
    parts = _ANCHOR_RE.split(body)
    segments = []
    if parts[0].strip():
        segments.append((None, parts[0].strip()))
    i = 1
    while i + 2 <= len(parts):
        anchor = {'idx': int(parts[i]), 'hash': parts[i + 1]}
        text = parts[i + 2].strip()
        segments.append((anchor, text))
        i += 3
    return segments


def _extract_blocks_from_xml(xml_bytes):
    """Parse document.xml bytes → list of serialized XML strings, one per body element.

    Returns all body children (p, tbl, sectPr) in order — the list index matches
    the tropo:block idx= value written by tropo-extract v1.1.0+. Returns [] on failure
    (graceful fallback → full regeneration).
    """
    try:
        root = ET.fromstring(xml_bytes.decode('utf-8'))
        body = root.find(f'{{{_W_NS}}}body')
        if body is None:
            return []
        return [ET.tostring(child, encoding='unicode', short_empty_elements=False)
                for child in body]
    except Exception:
        return []


# ==========================================================================
# Working-copy markdown → OOXML paragraph tokens
# ==========================================================================

# Heading anti-collision rule per arch-spec §3.7 step 4 v0.3:
# - working-copy `# Title` (H1) maps to template Title OR fallback (bold-Normal-center
#   on collision-avoidance OR safe-promote-Heading1)
# - working-copy `## H2`   → template Heading1
# - working-copy `### H3`  → template Heading2
# - working-copy `#### H4` → template Heading3

def parse_working_copy_body(body):
    """Tokenize working-copy markdown body into a flat list of paragraph-dicts.

    Each token: {'kind': 'title'|'h2'|'h3'|'h4'|'p'|'ul'|'ol'|'table',
                 'text': str (or 'rows': list-of-list for tables)}

    Inline formatting is preserved in 'text' as marker tokens for the body builder.

    v1.28.0.1 (closes sa.skeptic-009 P0-1): table support added — markdown table
    rows starting with `|` accumulate into a 'table' token with structured rows.
    Without this, tables silently flattened into one prose paragraph.

    v1.31.0 v0.7.3 (closes R4 cold-boot-172 D1.2): nav-block sentinels (rendered
    by .tropo/scripts/generate-relations-header.py per OP-12 human-navigation
    doctrine) are stripped BEFORE tokenization. The block is vault-internal
    navigation chrome — path/UID/siblings/cited-by — NOT document content. It
    should not appear in exported .docx output. Pattern matches the canonical
    sentinel pair `<!-- nav-block:start --> ... <!-- nav-block:end -->`.
    """
    # v0.7.3 R4 D1.2 absorption — strip nav-block regions
    body = re.sub(
        r'<!--\s*nav-block:start\s*-->.*?<!--\s*nav-block:end\s*-->\s*',
        '', body, flags=re.DOTALL,
    )
    tokens = []
    lines = body.split('\n')
    in_list = None  # 'ul' or 'ol' or None
    current_paragraph_lines = []
    current_table_rows = []  # list of [cell, cell, ...] when accumulating a table

    def flush_paragraph():
        nonlocal current_paragraph_lines
        if current_paragraph_lines:
            text = ' '.join(l.strip() for l in current_paragraph_lines).strip()
            if text:
                tokens.append({'kind': 'p', 'text': text})
            current_paragraph_lines = []

    def flush_table():
        nonlocal current_table_rows
        if current_table_rows:
            tokens.append({'kind': 'table', 'rows': current_table_rows})
            current_table_rows = []

    def parse_table_row(s):
        """Split a `| col1 | col2 |` row into cells. Strip leading/trailing |
        + leading/trailing whitespace per cell. Returns list of cell strings."""
        s = s.strip()
        if s.startswith('|'):
            s = s[1:]
        if s.endswith('|'):
            s = s[:-1]
        return [cell.strip() for cell in s.split('|')]

    def is_table_separator(s):
        """True if line is a `|---|---|` separator row."""
        s = s.strip()
        if not (s.startswith('|') and s.endswith('|')):
            return False
        cells = parse_table_row(s)
        return all(re.match(r'^:?-+:?$', c) for c in cells if c)

    def is_table_row(s):
        """True if line looks like a markdown table row (starts + ends with `|`)."""
        s = s.strip()
        return s.startswith('|') and s.endswith('|') and s.count('|') >= 2

    for line in lines:
        stripped = line.rstrip()

        if not stripped:
            flush_paragraph()
            flush_table()
            in_list = None
            continue

        # Markdown table row (header / separator / data)
        if is_table_row(stripped):
            flush_paragraph()
            in_list = None
            if is_table_separator(stripped):
                # Skip separator rows; they don't carry data
                continue
            current_table_rows.append(parse_table_row(stripped))
            continue
        else:
            # Non-table line — flush any in-progress table first
            flush_table()

        # Headings
        m = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if m:
            flush_paragraph()
            in_list = None
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1:
                tokens.append({'kind': 'title', 'text': text})
            elif level == 2:
                tokens.append({'kind': 'h2', 'text': text})
            elif level == 3:
                tokens.append({'kind': 'h3', 'text': text})
            elif level == 4:
                tokens.append({'kind': 'h4', 'text': text})
            else:
                # H5 + H6 → treat as plain paragraph (with bold) since template
                # mapping only goes to Heading3. v1.28.0 scope.
                tokens.append({'kind': 'p', 'text': f'**{text}**'})
            continue

        # Bulleted list
        m = re.match(r'^[-*+]\s+(.+)$', stripped)
        if m:
            flush_paragraph()
            in_list = 'ul'
            tokens.append({'kind': 'ul', 'text': m.group(1).strip()})
            continue

        # Numbered list
        m = re.match(r'^\d+\.\s+(.+)$', stripped)
        if m:
            flush_paragraph()
            in_list = 'ol'
            tokens.append({'kind': 'ol', 'text': m.group(1).strip()})
            continue

        # Plain paragraph continuation
        current_paragraph_lines.append(line)

    flush_paragraph()
    flush_table()
    return tokens


# ==========================================================================
# Token → OOXML <w:p> element builder
# ==========================================================================

def _w(tag):
    """Build an Element with the w: namespace."""
    return ET.Element(f'{{{_W_NS}}}{tag}')


def _w_sub(parent, tag):
    return ET.SubElement(parent, f'{{{_W_NS}}}{tag}')


# F4 fix (96b7d233, 2026-06-12): hyperlinks rebuilt at export. _build_run
# collects (rid, url) here while building <w:hyperlink> wrappers; the zip
# writers patch word/_rels/document.xml.rels with the matching Relationship
# entries. Reset per export run in main(). rIdTropoHL<n> ids cannot collide
# with any scaffold's conventional rId<n> ids by construction.
_EXPORT_HYPERLINKS = []

# 5b844b8a G2: the table style id markdown tables should reference, so they
# inherit the template's branded table look (header fill, banding) via a NAMED
# style — not hand-applied cell fills (markdown can't carry those). Set per
# export run in main(); read in _build_table. None ⇒ TableGrid/generic fallback.
_ACTIVE_TABLE_STYLE = None


def _pick_table_style(scaffold_path, override=None):
    """Choose the table style id for this export.

    Priority: explicit override > a branded accent grid table in the scaffold's
    own styles.xml > 'TableGrid' > None. Reads the scaffold live so it works for
    templates registered before default_table_style capture existed.
    """
    if override:
        return override
    if scaffold_path is None:
        return None
    try:
        import zipfile as _zip
        with _zip.ZipFile(scaffold_path) as z:
            styles = z.read('word/styles.xml').decode('utf-8', 'replace')
    except Exception:
        return None
    table_ids = re.findall(r'<w:style [^>]*w:type="table"[^>]*w:styleId="([^"]+)"', styles)
    if not table_ids:
        return None
    # Prefer a colored accent grid table (the branded look); fall back gracefully.
    for pat in (r'GridTable\d.*Accent1$', r'GridTable\d.*Accent', r'^GridTable', r'^TableGrid$'):
        for sid in table_ids:
            if re.search(pat, sid):
                return sid
    return None
_R_NS_URI = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_LINK_MD_RE = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')


def _patch_word_rels(rels_bytes):
    """Append hyperlink Relationship entries to a word/_rels/document.xml.rels blob."""
    if not _EXPORT_HYPERLINKS:
        return rels_bytes
    from xml.sax.saxutils import escape
    adds = ''.join(
        f'<Relationship Id="{rid}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        f'Target="{escape(url, {chr(34): "&quot;"})}" TargetMode="External"/>'
        for rid, url in _EXPORT_HYPERLINKS
    )
    text = rels_bytes.decode('utf-8')
    return text.replace('</Relationships>', adds + '</Relationships>').encode('utf-8')


def _build_run(text):
    """Build a <w:r><w:t>text</w:t></w:r> with inline bold/italic from markdown markers.

    Splits text on `[text](url)`, `**bold**` and `_italic_` markers; emits
    separate runs (links as <w:hyperlink> wrappers, F4) with rPr formatting.
    Preserves leading/trailing spaces via xml:space="preserve".
    """
    runs = []
    # Tokenize on link + bold + italic markers (simple non-overlapping pass)
    pattern = re.compile(r'(\[[^\]]+\]\([^)\s]+\)|\*\*[^*]+\*\*|_[^_]+_)')
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            runs.append(('plain', text[pos:m.start()], None))
        marker = m.group(0)
        if marker.startswith('['):
            link = _LINK_MD_RE.fullmatch(marker)
            if link:
                runs.append(('link', link.group(1), link.group(2)))
            else:
                runs.append(('plain', marker, None))
        elif marker.startswith('**'):
            runs.append(('bold', marker[2:-2], None))
        elif marker.startswith('_'):
            runs.append(('italic', marker[1:-1], None))
        pos = m.end()
    if pos < len(text):
        runs.append(('plain', text[pos:], None))
    if not runs:
        runs.append(('plain', text, None))

    elements = []
    for kind, run_text, url in runs:
        if not run_text:
            continue
        if kind == 'link':
            rid = f'rIdTropoHL{len(_EXPORT_HYPERLINKS) + 1}'
            _EXPORT_HYPERLINKS.append((rid, url))
            h = ET.Element(f'{{{_W_NS}}}hyperlink')
            h.set(f'{{{_R_NS_URI}}}id', rid)
            r = ET.SubElement(h, f'{{{_W_NS}}}r')
            rPr = ET.SubElement(r, f'{{{_W_NS}}}rPr')
            rStyle = ET.SubElement(rPr, f'{{{_W_NS}}}rStyle')
            rStyle.set(f'{{{_W_NS}}}val', 'Hyperlink')
            t = ET.SubElement(r, f'{{{_W_NS}}}t')
            t.text = run_text
            elements.append(h)
            continue
        r = _w('r')
        if kind in ('bold', 'italic'):
            rPr = _w_sub(r, 'rPr')
            if kind == 'bold':
                _w_sub(rPr, 'b')
            else:
                _w_sub(rPr, 'i')
        t = _w_sub(r, 't')
        # Preserve whitespace if leading/trailing spaces matter
        if run_text != run_text.strip() or '  ' in run_text:
            t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        t.text = run_text
        elements.append(r)
    return elements


def _build_paragraph(style_id, text, fallback_stats):
    """Build a <w:p> with optional pStyle pointer + the body text as runs."""
    p = _w('p')
    if style_id:
        pPr = _w_sub(p, 'pPr')
        pStyle = _w_sub(pPr, 'pStyle')
        pStyle.set(f'{{{_W_NS}}}val', style_id)
    for run in _build_run(text):
        p.append(run)
    return p


def _build_title_paragraph(title_text, template_named_styles, has_h2_content, fallback_stats):
    """Build a title paragraph per arch-spec §3.7 step 4 heading-anti-collision rule v0.3.

    - If template has Title style → use it.
    - Else if template has Heading1 AND working-copy has any ## H2 → bold-Normal-center
      (avoid collapsing semantic distinction).
    - Else if template has Heading1 AND no ## H2 → safe to promote to Heading1.
    - Else → bold-Normal-center.
    """
    available = {s.get('id'): s for s in template_named_styles or []}
    has_title = 'Title' in available
    has_heading1 = 'Heading1' in available

    if has_title:
        # P1-1 closure (v1.32.0 spec [900d41e0] §3.1 v0.4 LOCKED): when Heading1
        # ALSO exists AND is visually indistinguishable from Title (same font_family
        # + size + bold), record the degeneracy in the journal via boolean field
        # parallel to P2 path's p2_heading_indistinguishable_from_title (line 1066).
        # Title style still used; diagnostic only; title_fallback_reason stays None
        # for Title-clean case (existing semantic preserved).
        fallback_stats['title_fallback_reason'] = None
        if has_heading1:
            title_style = available['Title']
            h1_style = available['Heading1']
            if (title_style.get('font_family') == h1_style.get('font_family')
                    and title_style.get('font_size_half_pt') == h1_style.get('font_size_half_pt')
                    and title_style.get('bold') == h1_style.get('bold')):
                fallback_stats['p1_heading_indistinguishable_from_title'] = True
        return _build_paragraph('Title', title_text, fallback_stats)
    elif has_heading1 and has_h2_content:
        # Bold-Normal-center
        fallback_stats['title_fallback_reason'] = 'no_title_style_collision_avoidance'
        p = _w('p')
        pPr = _w_sub(p, 'pPr')
        jc = _w_sub(pPr, 'jc')
        jc.set(f'{{{_W_NS}}}val', 'center')
        for run in _build_run(f'**{title_text}**'):
            p.append(run)
        return p
    elif has_heading1 and not has_h2_content:
        fallback_stats['title_fallback_reason'] = 'no_title_style_safe_promotion'
        return _build_paragraph('Heading1', title_text, fallback_stats)
    else:
        fallback_stats['title_fallback_reason'] = 'no_heading_styles_available'
        p = _w('p')
        pPr = _w_sub(p, 'pPr')
        jc = _w_sub(pPr, 'jc')
        jc.set(f'{{{_W_NS}}}val', 'center')
        for run in _build_run(f'**{title_text}**'):
            p.append(run)
        return p


def _build_table(rows, template_named_styles, fallback_stats):
    """Build a minimum-viable <w:tbl> from a list of [cell, cell, ...] rows.

    v1.28.0.1 (closes sa.skeptic-009 P0-1): emits OOXML table with structured
    rows + cells. First row is treated as the header row (bold). Cell content
    runs through _build_run for inline bold/italic. Width is auto-set; column
    widths default to equal split. Uses template TableGrid style if present in
    template_named_styles, else default.
    """
    if not rows:
        return None

    available = {s.get('id') for s in (template_named_styles or [])}
    # 5b844b8a G2: prefer the run's resolved branded table style; fall back to
    # TableGrid (if the template defines it), else generic borders.
    table_style = _ACTIVE_TABLE_STYLE or ('TableGrid' if 'TableGrid' in available else None)
    if not table_style:
        fallback_stats['used_word_default_table'] = True

    n_cols = max(len(r) for r in rows)

    tbl = _w('tbl')

    # Table properties — auto width + optional table style
    tblPr = _w_sub(tbl, 'tblPr')
    if table_style:
        tblStyle = _w_sub(tblPr, 'tblStyle')
        tblStyle.set(f'{{{_W_NS}}}val', table_style)
    tblW = _w_sub(tblPr, 'tblW')
    tblW.set(f'{{{_W_NS}}}w', '0')
    tblW.set(f'{{{_W_NS}}}type', 'auto')
    # Add basic borders so the table is visible even without a template style
    if not table_style:
        tblBorders = _w_sub(tblPr, 'tblBorders')
        for border_kind in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
            b = _w_sub(tblBorders, border_kind)
            b.set(f'{{{_W_NS}}}val', 'single')
            b.set(f'{{{_W_NS}}}sz', '4')
            b.set(f'{{{_W_NS}}}color', 'auto')

    # Table grid — equal column widths totalling 9000 DXA (~6.25 inches)
    tblGrid = _w_sub(tbl, 'tblGrid')
    col_width = max(1000, 9000 // n_cols)
    for _ in range(n_cols):
        gridCol = _w_sub(tblGrid, 'gridCol')
        gridCol.set(f'{{{_W_NS}}}w', str(col_width))

    # Rows
    for row_idx, row in enumerate(rows):
        is_header = (row_idx == 0)
        tr = _w_sub(tbl, 'tr')
        # Mark header row for repeat-on-page-break
        if is_header:
            trPr = _w_sub(tr, 'trPr')
            _w_sub(trPr, 'tblHeader')

        # Pad short rows to n_cols
        cells = list(row) + [''] * (n_cols - len(row))
        for cell_text in cells:
            tc = _w_sub(tr, 'tc')
            tcPr = _w_sub(tc, 'tcPr')
            tcW = _w_sub(tcPr, 'tcW')
            tcW.set(f'{{{_W_NS}}}w', str(col_width))
            tcW.set(f'{{{_W_NS}}}type', 'dxa')

            # Cell content as a paragraph.
            # F17 fix (96b7d233, 2026-06-12): extraction ALREADY encodes the
            # source's header bold as markdown (**Field**). The old code wrapped
            # AGAIN -> ****Field****, and _build_run's tokenizer leaks the outer
            # ** as literal text into the cell. Build from the cell's own
            # markdown; for a header row whose cells carry no bold of their own
            # (e.g. a hand-typed plain markdown table), force bold via run
            # properties instead of re-wrapping the text.
            p = _w('p')
            cell_text = (cell_text or '').strip()
            run_elems = _build_run(cell_text)
            if is_header and cell_text and not _has_bold_run(run_elems):
                _force_bold_runs(run_elems)
            for run in run_elems:
                p.append(run)
            tc.append(p)
    return tbl


def _has_bold_run(elems):
    """True if any built run already carries <w:b/>."""
    for el in elems:
        for r in el.iter(f'{{{_W_NS}}}r'):
            rPr = r.find(f'{{{_W_NS}}}rPr')
            if rPr is not None and rPr.find(f'{{{_W_NS}}}b') is not None:
                return True
    return False


def _force_bold_runs(elems):
    """Add <w:b/> to every run, inserting rPr as the required first child."""
    for el in elems:
        for r in el.iter(f'{{{_W_NS}}}r'):
            rPr = r.find(f'{{{_W_NS}}}rPr')
            if rPr is None:
                rPr = ET.Element(f'{{{_W_NS}}}rPr')
                r.insert(0, rPr)  # OOXML: rPr must precede w:t
            if rPr.find(f'{{{_W_NS}}}b') is None:
                ET.SubElement(rPr, f'{{{_W_NS}}}b')


def build_body_paragraphs(tokens, template_named_styles, fallback_stats):
    """Convert tokens → list of OOXML <w:p> + <w:tbl> elements per arch-spec §3.7 step 4."""
    has_h2_content = any(t['kind'] == 'h2' for t in tokens)
    elements = []
    for tok in tokens:
        if tok['kind'] == 'title':
            elements.append(_build_title_paragraph(
                tok['text'], template_named_styles, has_h2_content, fallback_stats))
        elif tok['kind'] == 'h2':
            elements.append(_build_paragraph('Heading1', tok['text'], fallback_stats))
        elif tok['kind'] == 'h3':
            elements.append(_build_paragraph('Heading2', tok['text'], fallback_stats))
        elif tok['kind'] == 'h4':
            elements.append(_build_paragraph('Heading3', tok['text'], fallback_stats))
        elif tok['kind'] == 'p':
            elements.append(_build_paragraph(None, tok['text'], fallback_stats))
        elif tok['kind'] == 'table':
            tbl = _build_table(tok.get('rows') or [], template_named_styles, fallback_stats)
            if tbl is not None:
                elements.append(tbl)
        elif tok['kind'] == 'ul':
            # Use ListParagraph style if template has it; else default bullet via direct formatting
            available = {s.get('id') for s in (template_named_styles or [])}
            style = 'ListParagraph' if 'ListParagraph' in available else None
            elements.append(_build_paragraph(style, '• ' + tok['text'], fallback_stats))
            if style != 'ListParagraph':
                fallback_stats['used_word_default_list'] = True
        elif tok['kind'] == 'ol':
            available = {s.get('id') for s in (template_named_styles or [])}
            style = 'ListParagraph' if 'ListParagraph' in available else None
            elements.append(_build_paragraph(style, tok['text'], fallback_stats))
            if style != 'ListParagraph':
                fallback_stats['used_word_default_list'] = True
    return elements


# ==========================================================================
# Tracked-changes detection per arch-spec §3.7 step 5.5 v0.5
# ==========================================================================

def detect_tracked_changes_in_scaffold(scaffold_path):
    """Return True if the scaffold's body contains tracked changes / comments / revisions.

    Per arch-spec §3.7 step 5.5 (v0.5 — RC-1 preserve+warn doctrine): detect
    <w:ins>, <w:del>, <w:moveFrom>, <w:moveTo> elements in document.xml, OR
    comments.xml referencing body content.
    """
    try:
        with zipfile.ZipFile(scaffold_path, 'r') as zf:
            names = zf.namelist()
            if 'word/document.xml' in names:
                with zf.open('word/document.xml') as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    for tag in ('<w:ins ', '<w:ins>', '<w:del ', '<w:del>',
                                '<w:moveFrom ', '<w:moveFrom>',
                                '<w:moveTo ', '<w:moveTo>'):
                        if tag in content:
                            return True
            if 'word/comments.xml' in names:
                with zf.open('word/comments.xml') as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    if '<w:comment ' in content or '<w:comment>' in content:
                        return True
    except (zipfile.BadZipFile, OSError):
        pass
    return False


# ==========================================================================
# Body-swap mechanism — open scaffold, swap body, save
# ==========================================================================

def body_swap(scaffold_path, output_path, working_copy_body, template_named_styles, fallback_stats):
    """Open scaffold .docx as ZIP, replace word/document.xml's body, repack.

    Preserves all other parts (header*.xml, footer*.xml, styles.xml, theme1.xml,
    settings.xml, vbaProject.bin, fonts/*, customXml/*, etc.) — the P1 max-fidelity
    contract per arch-spec §3.7 step 5 preservation semantics.

    Per arch-spec §3.7 step 4: replaces body paragraphs but preserves the final
    <w:sectPr> (section properties: page size, margins, etc.).

    v1.28.0.1 (closes sa.skeptic-009 P0-2): preserves the source root's full
    namespace map + mc:Ignorable attribute by doing TARGETED body-substring
    replacement instead of full XML re-serialization. Strict OOXML consumers
    (Open-XML SDK validation, LibreOffice strict mode, corporate validators)
    require every prefix listed in mc:Ignorable to be a declared xmlns on the
    element where Ignorable lives. ET.tostring after register_namespace only
    declared 'w' + 'r', dropping w14/w15/w16*/wp14/etc. — the rewritten document
    became technically invalid but desktop Word tolerated. The targeted-replace
    path leaves the root element + everything outside <w:body> byte-identical
    to the source, which is also a stronger expression of the §3.7 step 5
    preservation semantics ("nothing is reconstructed").

    v1.1.0 (S1.3 v1.70): diff-aware preservation — if the working copy body
    contains tropo:block anchor comments (written by tropo-extract v1.1.0+),
    unchanged blocks are spliced from source XML directly rather than regenerated
    from markdown. Changed blocks + all new/unanchored content regenerate as before.
    Anchor matching: _sha8(current_segment_text) == anchor.hash → unchanged → preserve.
    Fallback: any parse failure → full regeneration (safe degradation).
    """
    # Read source document.xml as bytes (preserves byte-identity for everything
    # outside the body region we're replacing).
    with zipfile.ZipFile(scaffold_path, 'r') as zf:
        document_xml_bytes = zf.read('word/document.xml')
        all_names = zf.namelist()

    document_text = document_xml_bytes.decode('utf-8')

    # Find the body region — locate <w:body...> opening tag + </w:body> closing tag.
    body_open_match = re.search(r'<w:body(\s[^>]*)?>', document_text)
    body_close_match = re.search(r'</w:body>', document_text)
    if not body_open_match or not body_close_match:
        raise SystemExit(f"Scaffold {scaffold_path} has no <w:body> in word/document.xml")

    body_open_end = body_open_match.end()
    body_close_start = body_close_match.start()
    body_inner = document_text[body_open_end:body_close_start]

    # Extract the final <w:sectPr> from the body's existing content (preserves
    # section properties: page size, margins, headers/footers references).
    sectPr_match = re.search(r'<w:sectPr(\s[^>]*)?>.*?</w:sectPr>', body_inner, re.DOTALL)
    sectPr_xml = sectPr_match.group(0) if sectPr_match else ''
    # Also handle self-closing variant
    if not sectPr_xml:
        self_closing = re.search(r'<w:sectPr(\s[^>]*)?/>', body_inner)
        if self_closing:
            sectPr_xml = self_closing.group(0)

    # v1.1.0 S1.3: diff-aware path when working copy has provenance anchors
    anchored_segments = _parse_anchored_body(working_copy_body)
    has_anchors = any(a is not None for a, _ in anchored_segments)

    new_body_parts = []
    if has_anchors:
        # Build source block index once (parallel to extractor's body_elem_idx)
        source_blocks = _extract_blocks_from_xml(document_xml_bytes)
        preserved = 0
        regenerated = 0
        for anchor, segment_text in anchored_segments:
            if anchor is not None and source_blocks:
                idx = anchor['idx']
                expected_hash = anchor['hash']
                current_hash = _sha8(segment_text)
                if current_hash == expected_hash and 0 <= idx < len(source_blocks):
                    # Unchanged block — splice source XML directly (max fidelity)
                    new_body_parts.append(source_blocks[idx])
                    preserved += 1
                    continue
            # Changed, unanchored, or index out-of-range — regenerate from markdown
            if segment_text:
                seg_tokens = parse_working_copy_body(segment_text)
                for elem in build_body_paragraphs(seg_tokens, template_named_styles, fallback_stats):
                    new_body_parts.append(ET.tostring(elem, encoding='unicode', short_empty_elements=False))
            regenerated += 1
        fallback_stats['diff_preserved_blocks'] = preserved
        fallback_stats['diff_regenerated_blocks'] = regenerated
    else:
        # No anchors — full regeneration (pre-v1.1.0 working copies or --force re-extract)
        tokens = parse_working_copy_body(working_copy_body)
        new_paragraphs = build_body_paragraphs(tokens, template_named_styles, fallback_stats)
        for elem in new_paragraphs:
            # Serialize each element. ET.tostring with short_empty_elements=False keeps
            # readability; we rely on the fact that w: prefix is registered globally.
            new_body_parts.append(ET.tostring(elem, encoding='unicode', short_empty_elements=False))

    if sectPr_xml:
        new_body_parts.append(sectPr_xml)
    new_body_inner = ''.join(new_body_parts)

    # Splice: keep [start of doc → body opening tag end] + new_body_inner +
    # [body closing tag → end of doc]. This preserves:
    #   - XML declaration
    #   - root element + all xmlns declarations + mc:Ignorable attribute
    #   - any pre-body element (extremely rare; defends against weird scaffolds)
    #   - everything after </w:body> (very rare; mostly nothing, but preserve it)
    new_document_text = (
        document_text[:body_open_end]
        + new_body_inner
        + document_text[body_close_start:]
    )
    new_document_xml = new_document_text.encode('utf-8')

    # Write a new ZIP at output_path. Preserve everything from the source EXCEPT
    # replace word/document.xml with our modified version.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(scaffold_path, 'r') as zf_in, \
         zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf_out:
        for name in all_names:
            if name == 'word/document.xml':
                data = new_document_xml
            elif name == 'word/_rels/document.xml.rels':
                # F4: register the rebuilt hyperlinks' Relationship entries
                data = _patch_word_rels(zf_in.read(name))
            else:
                data = zf_in.read(name)
            zf_out.writestr(name, data)


# ==========================================================================
# Slug-safe title for output paths
# ==========================================================================

def slugify_title(title, max_len=60):
    s = title.lower()
    s = re.sub(r'[^a-z0-9-]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s[:max_len] or 'export'


# ==========================================================================
# Journal + audit
# ==========================================================================

def _json_default(obj):
    """JSON serializer fallback for date/datetime objects (returned by PyYAML
    when frontmatter contains ISO date scalars)."""
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def append_journal(studio_root, event):
    journal_path = studio_root / JOURNAL_RELPATH
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with journal_path.open('a') as f:
        f.write(json.dumps(event, separators=(',', ':'), default=_json_default) + '\n')
        f.flush()
        os.fsync(f.fileno())


# ==========================================================================
# Working-copy frontmatter convenience-field updates per arch-spec §3.7 step 7
# ==========================================================================

def update_working_copy_export_fields(working_copy_path, output_path_rel,
                                       template_uid_or_none):
    """Update last_exported_at/path/template fields on the working-copy entry.

    v1.32.0 spec [900d41e0] §3.2 v0.4 LOCKED (P1-2 closure): adds a third-path
    fallback insert bounded to the frontmatter region only (cannot collide with
    markdown HR `---` lines in body). Returns a status dict so the caller can
    emit a `working_copy_frontmatter_malformed` journal event in BOTH the
    fallback-succeeded case AND the fence-finding-failed case (substrate-defect
    signal reaches operator even when insertion couldn't complete).

    Returns: {
        'fallback_fired': bool,          # any per-key fell through to 3rd-path insert
        'fallback_keys': list[str],      # the keys that fell through
        'frontmatter_malformed': bool,   # text lacked a closing --- in the leading region
    }
    """
    text = working_copy_path.read_text()
    fields_set = {
        'last_exported_at': now_iso(),
        'last_exported_path': output_path_rel,
        'last_exported_template': template_uid_or_none or 'null',
    }

    # v0.4 fence-tightening (skeptic P1-B): bound fence-finding to the leading
    # frontmatter block only. The frontmatter region is the text from the first
    # --- at byte 0 to the second --- at column 0; HR rules in the body cannot match.
    def _resolve_fm_block_end(t):
        # v1.32.0 spec [900d41e0] §3.2 v0.5 absorption (R3 production-failure
        # skeptic-073 S1): BOM-aware opener match — Word/Notepad export path
        # produces UTF-8 BOM-prefixed files; \A---\s*\n alone fails on BOM'd
        # working-copies and emits spurious working_copy_frontmatter_malformed
        # events. \A﻿? allows the optional BOM before the opener; file
        # contents (including BOM) preserved on write-back.
        first_fm = re.search(r'\A﻿?---\s*\n', t)
        if not first_fm:
            return -1
        second_fm = re.search(r'^---\s*$', t[first_fm.end():], flags=re.MULTILINE)
        if not second_fm:
            return -1
        return first_fm.end() + second_fm.start()

    fm_block_end = _resolve_fm_block_end(text)
    fallback_keys = []

    for key, val in fields_set.items():
        if val == 'null':
            replacement = f'{key}: null'
        else:
            replacement = f'{key}: "{val}"'
        # Existing-field replace — scoped to frontmatter region
        scope = text[:fm_block_end] if fm_block_end > 0 else text
        if re.search(rf'^{key}:.*$', scope, re.MULTILINE):
            new_scope = re.sub(rf'^{key}:.*$', replacement, scope, flags=re.MULTILINE)
            if fm_block_end > 0:
                text = new_scope + text[fm_block_end:]
                # Offset preserved (replace is in-place); no re-resolve needed
            else:
                text = new_scope
            continue
        # Pattern A: insert before schema_version: 2 closing (preserves v1.0.2 behavior)
        if 'schema_version: 2\n---' in text:
            text = text.replace('schema_version: 2\n---',
                                f'{replacement}\nschema_version: 2\n---', 1)
            fm_block_end = _resolve_fm_block_end(text)
            continue
        # Pattern B: insert before schema_version: 1 closing
        if 'schema_version: 1\n---' in text:
            text = text.replace('schema_version: 1\n---',
                                f'{replacement}\nschema_version: 1\n---', 1)
            fm_block_end = _resolve_fm_block_end(text)
            continue
        # P1-2 closure (v1.32.0 spec [900d41e0] §3.2 v0.4): final fallback —
        # insert before the closing --- of the frontmatter block (bounded;
        # cannot collide with HR rules in body). Track that the fallback fired
        # so the caller can emit a working_copy_frontmatter_malformed journal event.
        if fm_block_end > 0:
            text = text[:fm_block_end] + f'{replacement}\n' + text[fm_block_end:]
            fallback_keys.append(key)
            fm_block_end = _resolve_fm_block_end(text)
        # else: frontmatter has no closing fence; record but cannot insert.

    frontmatter_malformed = (fm_block_end <= 0) or bool(fallback_keys)

    text = re.sub(r'^modified: \S+', f'modified: {now_date()}', text, flags=re.MULTILINE)
    text = re.sub(r'^modified_by: \S+', f'modified_by: {TOOL_NAME}-v{TOOL_VERSION}', text, flags=re.MULTILINE)
    working_copy_path.write_text(text)
    return {
        'fallback_fired': bool(fallback_keys),
        'fallback_keys': fallback_keys,
        'frontmatter_malformed': frontmatter_malformed,
    }


# ==========================================================================
# CLI entry point
# ==========================================================================

def main():
    _EXPORT_HYPERLINKS.clear()  # F4: fresh hyperlink registry per export run
    parser = argparse.ArgumentParser(
        prog='tropo-export.py',
        description=__doc__.split('\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--working-copy', default=None,
                        help="Working-copy UID (registered, with source lineage). "
                             "Mutually exclusive with --markdown.")
    parser.add_argument('--markdown', default=None,
                        help="Path to a raw markdown file (vault-born content, no source "
                             "binary). REQUIRES --template (transformation only). 5b844b8a G1.")
    parser.add_argument('--table-style', default=None,
                        help="Override the named table style markdown tables reference "
                             "(default: a branded accent grid table from the template). 5b844b8a G2.")
    parser.add_argument('--json', action='store_true',
                        help="Emit a single JSON line {ok, output_path, export_path_type, warnings} "
                             "to stdout instead of prose (for L2 callers). 5b844b8a G3.")
    parser.add_argument('--source-label', default=None,
                        help="Provenance label recorded in the journal when the markdown is "
                             "ephemeral (e.g. an L2 download). Overrides the temp-file path. 5b844b8a.")
    parser.add_argument('--template', default=None,
                        help="Template UID (if provided: TRANSFORMATION export — "
                             "skips P1/P2 entirely per §3.7 mutual exclusion). "
                             "If omitted: PRESERVATION export (P1 source-binary → P2 fallback).")
    parser.add_argument('--output-path', default=None,
                        help="Override default 02-outbox/docx/<date>-<title>.docx path")
    parser.add_argument('--title', default=None,
                        help="Override title derivation from working-copy")
    parser.add_argument('--accept-binary-drift', action='store_true',
                        help="Per §3.7 precondition 3: if template binary hash mismatches "
                             "the registered hash, accept the drift + update the registered hash. "
                             "Without this flag, drift surfaces as an error.")
    parser.add_argument('--studio-root', default=None)
    parser.add_argument('--run-uid', default='cli-standalone')
    parser.add_argument('--executive', default='cli-user')
    args = parser.parse_args()

    studio_root = resolve_studio_root(args.studio_root)

    # Input mode (5b844b8a G1): exactly one of --working-copy (registered, lineage)
    # or --markdown (raw vault-born content, transformation-only).
    if bool(args.working_copy) == bool(args.markdown):
        raise SystemExit("Provide exactly one of --working-copy <uid> or --markdown <path>")

    wc_fm = None
    wc_path = None
    projection_uid = None

    if args.markdown:
        # RAW MARKDOWN MODE — vault-born content has no source binary, so there is
        # nothing to preserve; a template (mold) is required. The transformation
        # branch below pours this body into the template.
        if not args.template:
            raise SystemExit(
                "--markdown requires --template (no source binary ⇒ transformation only)")
        md_path = Path(args.markdown).resolve()
        if not md_path.exists():
            raise SystemExit(f"--markdown {args.markdown}: file not found")
        raw_md = md_path.read_text()
        m = re.match(r'^---\s*\n.*?\n---\s*\n(.*)$', raw_md, re.DOTALL)
        wc_body = m.group(1) if m else raw_md
        if not args.title:
            h1 = re.search(r'^#\s+(.+)$', wc_body, re.MULTILINE)
            args_title_resolved = h1.group(1).strip() if h1 else md_path.stem
        else:
            args_title_resolved = args.title
        source_label = md_path.stem
        source_markdown_rel = (str(md_path.relative_to(studio_root))
                               if md_path.is_relative_to(studio_root) else str(md_path))
    else:
        # WORKING-COPY MODE (existing path).
        # Precondition 1: working-copy resolves + state:active
        wc_fm, wc_body, wc_path = load_entry(studio_root, args.working_copy)
        if wc_fm.get('type') != 'working-copy':
            raise SystemExit(
                f"--working-copy {args.working_copy}: entry is type:{wc_fm.get('type', '?')}, "
                f"not type:working-copy")
        if wc_fm.get('state') != 'active':
            raise SystemExit(
                f"--working-copy {args.working_copy}: state is {wc_fm.get('state')}, not active")

        # Precondition 4 (v0.5): single-parent working-copy
        derived_from = wc_fm.get('derived_from') or []
        if not isinstance(derived_from, list) or len(derived_from) != 1:
            raise SystemExit(
                f"--working-copy {args.working_copy}: derived_from has "
                f"{len(derived_from) if isinstance(derived_from, list) else 'invalid'} entries; "
                f"v1.0 working-copy contract is single-parent (per arch-spec §3.7 precondition 4)."
            )
        projection_uid = derived_from[0]
        args_title_resolved = args.title or wc_fm.get('title') or wc_path.stem
        source_label = wc_path.stem
        source_markdown_rel = None

    # Resolve scaffold + path
    export_path_type = None  # 'preservation_p1' / 'preservation_p2' / 'transformation_template'
    scaffold_path = None
    template_uid = None
    template_named_styles = []
    template_binary_drift_accepted = False
    template_hash = None
    fallback_reason = None

    if args.template:
        # TRANSFORMATION path per §3.7 v0.4 amendment + v0.5 mutual exclusion
        export_path_type = 'transformation_template'
        tmpl_fm, _, _ = load_entry(studio_root, args.template)
        if tmpl_fm.get('type') != 'docx-template':
            raise SystemExit(
                f"--template {args.template}: entry is type:{tmpl_fm.get('type', '?')}, "
                f"not type:docx-template")
        if tmpl_fm.get('state') != 'active':
            raise SystemExit(
                f"--template {args.template}: state is {tmpl_fm.get('state')}, not active")
        template_uid = args.template
        binary_rel = tmpl_fm.get('template_binary_path')
        if not binary_rel:
            raise SystemExit(f"--template {args.template}: template_binary_path missing")
        scaffold_path = (studio_root / binary_rel).resolve()
        if not scaffold_path.exists():
            raise SystemExit(
                f"--template {args.template}: template_binary_path {binary_rel} does not exist")
        recorded_hash = tmpl_fm.get('template_binary_hash')
        current_hash = sha256_file(scaffold_path)
        template_hash = current_hash
        if recorded_hash and recorded_hash != current_hash:
            # Per §3.7 precondition 3 v0.3: prompt-then-proceed; the user authorizes via flag
            if not args.accept_binary_drift:
                raise SystemExit(
                    f"--template {args.template}: template binary at {binary_rel} has been modified "
                    f"off-tool (hash {current_hash} != recorded {recorded_hash}). Three resolution paths "
                    f"per arch-spec §3.7 precondition 3: (a) re-run with --accept-binary-drift to record "
                    f"the new hash + export; (b) re-register via tropo-register-template.py --force to "
                    f"refresh styles; (c) abort + resolve manually."
                )
            template_binary_drift_accepted = True
            # Update the template entry's recorded hash (per §3.7 precondition 3 path (a))
            _update_template_hash(studio_root, template_uid, current_hash)
        template_named_styles = tmpl_fm.get('extracted_styles', {}).get('named_styles', []) or []
    else:
        # PRESERVATION path per §3.7 v0.4 amendment
        # P1: source binary as scaffold
        # P2: original_styles reconstruction fallback
        # Fail loud if both missing
        proj_fm, _, _ = load_entry(studio_root, projection_uid)
        source_rel = proj_fm.get('source_path')  # relative-to-Studio-root per §C.3
        if not source_rel:
            raise SystemExit(
                f"Projection {projection_uid}: source_path missing — cannot resolve P1 scaffold")
        source_abs = (studio_root / source_rel).resolve()
        if source_abs.exists():
            scaffold_path = source_abs
            export_path_type = 'preservation_p1'
            # v1.28.0.1 (closes sa.skeptic-009 P1-4): re-extract styles from the LIVE
            # scaffold instead of trusting the projection's recorded original_styles.
            # If the user edited the source .docx after import (legitimate; preservation
            # export's whole point is that the source binary IS the format), the recorded
            # styles list may be stale — using it for heading-anti-collision decisions
            # would map titles to styles that no longer exist or pick the wrong fallback.
            # The body-swap reads word/styles.xml from the live binary anyway; pulling
            # named_styles from the live binary makes the heading-mapping consistent
            # with what'll actually render in Word.
            try:
                # v1.56 Lane S inline fix by metis-g62 2026-05-27: office_styles migrated to
                # vault/tools/<uid>.py (UID d1f2420d per registry); old same-name import failed.
                # Same pattern as import-walker.py (bf886f30) office_styles load.
                import importlib.util as _importlib_util
                _os_path = Path(__file__).parent / 'd1f2420d.py'
                if not _os_path.exists():
                    raise ImportError(
                        f"office_styles not present at {_os_path} "
                        "(UID d1f2420d per v1.56 migration)"
                    )
                _os_spec = _importlib_util.spec_from_file_location('office_styles', _os_path)
                _office_styles = _importlib_util.module_from_spec(_os_spec)
                _os_spec.loader.exec_module(_office_styles)
                live_styles = _office_styles.extract_office_styles(scaffold_path)
                if live_styles is not None:
                    template_named_styles = live_styles.get('named_styles', []) or []
                else:
                    # Live extraction failed (corrupt source?); fall back to recorded
                    template_named_styles = proj_fm.get('original_styles', {}).get('named_styles', []) or []
            except Exception:
                template_named_styles = proj_fm.get('original_styles', {}).get('named_styles', []) or []
        else:
            # P2 reconstruction path — proper implementation per v1.31.0 spec [c5e2f8a3].
            # Source binary missing; reconstruct .docx from projection's original_styles
            # via docx_styles_bundle module. Pre-v1.28.0 working-copy edge case is
            # handled by the inline guard inside _build_minimal_docx_from_scratch below.
            export_path_type = 'preservation_p2'

    # Resolve output path — destination follows the content's HOME (80617f6c D2,
    # Mike-G77 2026-06-13): a revision of a real external doc lands back in its
    # own folder versioned ` v-NN` (original bytes untouched); vault-born exports
    # + downloads go to the 02-outbox/ deliverable surface.
    if args.output_path:
        output_path = Path(args.output_path).resolve()
    elif export_path_type == 'preservation_p1' and scaffold_path is not None:
        # Preservation round-trip of a real external doc: write next to the source,
        # versioned. The original is never overwritten — the version loop only ever
        # picks a name that doesn't yet exist.
        src = Path(scaffold_path)
        n = 2
        candidate = src.with_name(f'{src.stem} v-{n:02d}{src.suffix}')
        while candidate.exists():
            n += 1
            candidate = src.with_name(f'{src.stem} v-{n:02d}{src.suffix}')
        output_path = candidate
    else:
        # vault-born (--markdown) / transformation / P2 reconstruction → the outbox.
        # 02-outbox/ is the studio's designed deliverable surface (numerical-prefix
        # convention; Mike-G77 FYI 2026-06-12).
        exports_dir = studio_root / '02-outbox' / 'docx'
        exports_dir.mkdir(parents=True, exist_ok=True)
        slug = slugify_title(args_title_resolved or source_label)
        candidate = exports_dir / f'{now_date()}-{slug}.docx'
        n = 1
        while candidate.exists():
            n += 1
            candidate = exports_dir / f'{now_date()}-{slug}-{n}.docx'
        output_path = candidate
    output_rel = str(output_path.relative_to(studio_root)) if output_path.is_relative_to(studio_root) else str(output_path)

    fallback_stats = {
        'title_fallback_reason': None,
        'used_word_default_list': False,
        'used_word_default_table': False,
        'used_word_default_footnote': False,
        'direct_inline_formatting_count': 0,
        'direct_code_formatting_used': False,
        'direct_blockquote_formatting_used': False,
        'direct_hyperlink_formatting_used': False,
        'direct_hrule_formatting_used': False,
        # v1.31.0 (v0.7 R2 P2-2 absorption): default ensures the key appears
        # in journal events even on non-P2 paths. P2 path overwrites with
        # the actual detection result in _build_minimal_docx_from_scratch.
        'p2_heading_indistinguishable_from_title': False,
        # v1.32.0 spec [900d41e0] §3.1 v0.4 LOCKED (P1-1 closure): boolean default
        # for P1-path heading anti-collision degeneracy detection (parallel to
        # p2_heading_indistinguishable_from_title above). Set True by
        # _build_title_paragraph when Title and Heading1 are visually
        # indistinguishable (same font_family + size + bold). Journal-only;
        # Title style still applied; no behavior change.
        'p1_heading_indistinguishable_from_title': False,
        # v1.1.0 S1.3 diff-aware preservation counters (0 when no anchors present)
        'diff_preserved_blocks': 0,
        'diff_regenerated_blocks': 0,
    }

    # 5b844b8a G2: resolve the branded table style for this run (arg > template
    # default_table_style > live scan of the scaffold > generic). Set the module
    # global the table builder reads.
    global _ACTIVE_TABLE_STYLE
    _table_default = None
    if args.template:
        _tmpl_fm_for_tbl, _, _ = load_entry(studio_root, args.template)
        _table_default = _tmpl_fm_for_tbl.get('default_table_style')
    _ACTIVE_TABLE_STYLE = _pick_table_style(scaffold_path, args.table_style or _table_default)

    # Tracked-changes detection (§3.7 step 5.5 v0.5) — only relevant on P1 path
    tracked_changes_detected = False
    if export_path_type == 'preservation_p1':
        tracked_changes_detected = detect_tracked_changes_in_scaffold(scaffold_path)

    # Acquire lock + execute body-swap
    with ReconcilerLock(studio_root, executive=args.executive):
        if export_path_type == 'preservation_p2':
            # P2 reconstruction: build a minimal .docx + bundle canonical styles via
            # docx_styles_bundle (per v1.31.0 spec [c5e2f8a3] §3.2 Edit 2).
            _build_minimal_docx_from_scratch(
                output_path=output_path,
                tokens=parse_working_copy_body(wc_body),
                original_styles=proj_fm.get('original_styles'),
                fallback_stats=fallback_stats,
                projection_uid=projection_uid,
            )
        else:
            # P1 + transformation: body-swap on the chosen scaffold
            body_swap(
                scaffold_path=scaffold_path,
                output_path=output_path,
                working_copy_body=wc_body,
                template_named_styles=template_named_styles,
                fallback_stats=fallback_stats,
            )

        # Tracked-changes warning per §3.7 step 5.5
        if tracked_changes_detected:
            print(
                "WARN: Source .docx contains tracked changes / comments anchored to body content. "
                "The body has been replaced with the working-copy; orphaned review markers may "
                "appear when Word opens the export. Resolve via Word's tracked-changes UI "
                "(Review tab → Accept/Reject) as you normally would.",
                file=sys.stderr,
            )

        # Update working-copy convenience fields (§3.7 step 7).
        # 5b844b8a G1: skip in raw-markdown mode — there is no working-copy entry.
        wc_update_result = (update_working_copy_export_fields(wc_path, output_rel, template_uid)
                            if wc_path is not None
                            else {'fallback_fired': False, 'frontmatter_malformed': False, 'fallback_keys': []})

        # v1.32.0 spec [900d41e0] §3.2 v0.4 (P1-2 closure): emit
        # working_copy_frontmatter_malformed event in BOTH the fallback-fired
        # AND the fence-finding-failed cases (substrate-defect signal reaches
        # operator even when insertion couldn't complete).
        if wc_update_result['fallback_fired'] or wc_update_result['frontmatter_malformed']:
            append_journal(studio_root, {
                'event': 'working_copy_frontmatter_malformed',
                'working_copy_uid': args.working_copy,
                'fallback_fired': wc_update_result['fallback_fired'],
                'fallback_keys': wc_update_result['fallback_keys'],
                'frontmatter_malformed': wc_update_result['frontmatter_malformed'],
                'timestamp': now_iso(),
                'executive': args.executive,
                'run_uid': args.run_uid,
            })

        # Append journal event (§3.7 step 6 — full schema per v0.5)
        append_journal(studio_root, {
            'event': 'export_generated',
            'working_copy_uid': args.working_copy,
            'source_markdown': args.source_label or source_markdown_rel,   # 5b844b8a G1: label overrides ephemeral temp path
            'table_style': _ACTIVE_TABLE_STYLE,        # 5b844b8a G2
            'template_uid': template_uid,
            'output_path': output_rel,
            'export_path_type': export_path_type,
            'working_copy_modified': wc_fm.get('modified') if wc_fm else None,
            'template_hash': template_hash,
            'template_binary_drift_accepted': template_binary_drift_accepted,
            'tracked_changes_in_source_scaffold': tracked_changes_detected,
            'fallback_reason': fallback_reason,
            'timestamp': now_iso(),
            'executive': args.executive,
            'run_uid': args.run_uid,
            'fallback_stats': fallback_stats,
        })

    # Build warnings list (shared by prose + JSON output)
    warnings = []
    if tracked_changes_detected:
        warnings.append("tracked-changes/comments in source; export may show orphaned markers")
    if fallback_stats.get('title_fallback_reason'):
        warnings.append(f"title fallback: {fallback_stats['title_fallback_reason']}")
    if fallback_stats.get('used_word_default_list'):
        warnings.append("used Word default list style (template lacks ListParagraph)")
    if fallback_stats.get('used_word_default_table'):
        warnings.append("used generic table borders (no named table style resolved)")

    # S1.3 diff-aware summary
    diff_info = None
    if fallback_stats.get('diff_preserved_blocks') or fallback_stats.get('diff_regenerated_blocks'):
        diff_info = (f"{fallback_stats['diff_preserved_blocks']} blocks preserved from source, "
                     f"{fallback_stats['diff_regenerated_blocks']} regenerated")

    # 5b844b8a G3: JSON output for L2 callers — one line on stdout, nothing else.
    if args.json:
        print(json.dumps({
            'ok': True,
            'output_path': output_rel,
            'export_path_type': export_path_type,
            'table_style': _ACTIVE_TABLE_STYLE,
            'warnings': warnings,
        }))
        return

    # Emit user-facing summary (§3.7 step 8)
    print(f"Export written: {output_rel}")
    print(f"Path: {export_path_type}", file=sys.stderr)
    if diff_info:
        print(f"Diff-aware: {diff_info}", file=sys.stderr)
    for w in warnings:
        print(w, file=sys.stderr)


def _update_template_hash(studio_root, template_uid, new_hash):
    """Update a docx-template entry's template_binary_hash field after accept-drift."""
    p = studio_root / 'vault' / 'files' / f'{template_uid}.md'
    if not p.exists():
        return
    text = p.read_text()
    text = re.sub(r'^template_binary_hash:.*$', f'template_binary_hash: {new_hash}',
                  text, flags=re.MULTILINE)
    text = re.sub(r'^modified: \S+', f'modified: {now_date()}', text, flags=re.MULTILINE)
    text = re.sub(r'^modified_by: \S+', f'modified_by: {TOOL_NAME}-v{TOOL_VERSION}',
                  text, flags=re.MULTILINE)
    p.write_text(text)


def _tokenize_inline_runs(text):
    """Tokenize XML-escaped text into a list of {text, bold, italic} run dicts.

    Supports markdown inline emphasis:
    - `**bold**` → {bold: True}
    - `_italic_` → {italic: True} (word-boundary aware to avoid splitting
      identifiers like `Mo_OS_user_guide`)
    - Combinations: italic nested inside bold (most common pattern)

    NOT supported in v1.31.0 (Path 2 for v1.32.0+):
    - `[text](url)` hyperlinks (require rels machinery)
    - Triple-asterisk bold+italic combo `***...***` (collapses oddly today;
      most authors use `**_..._**` instead which IS handled correctly)
    - Strikethrough, code spans, etc.

    Input text MUST already be XML-escaped (& → &amp;, < → &lt;, > → &gt;).
    XML-escape characters do not overlap with markdown markers (*, _) so the
    order is escape-then-tokenize.

    v1.31.0 v0.7.4 R4 D1.3 absorption — closes the literal-markup leakage
    that cold-boot-172 caught against CFO whitepaper + the round-trip test
    against competitive brief (53 literal ** + 3 literal _).
    """
    if not text:
        return []
    # Pass 1: split by **bold**
    bold_pat = re.compile(r'\*\*(.+?)\*\*')
    pieces = []  # list of (text, is_bold)
    pos = 0
    for m in bold_pat.finditer(text):
        if m.start() > pos:
            pieces.append((text[pos:m.start()], False))
        pieces.append((m.group(1), True))
        pos = m.end()
    if pos < len(text):
        pieces.append((text[pos:], False))
    if not pieces:
        pieces = [(text, False)]

    # Pass 2: within each piece, split by _italic_ with word-boundary guards
    # so identifiers like Mo_OS_user_guide don't get parsed as italic.
    italic_pat = re.compile(r'(?<!\w)_([^_\n]{1,200}?)_(?!\w)')
    runs = []
    for piece_text, is_bold in pieces:
        ppos = 0
        for m in italic_pat.finditer(piece_text):
            if m.start() > ppos:
                runs.append({'text': piece_text[ppos:m.start()],
                             'bold': is_bold, 'italic': False})
            runs.append({'text': m.group(1),
                         'bold': is_bold, 'italic': True})
            ppos = m.end()
        if ppos < len(piece_text):
            runs.append({'text': piece_text[ppos:],
                         'bold': is_bold, 'italic': False})

    return [r for r in runs if r['text']]  # drop empty runs


def _emit_inline_runs(text):
    """Build one or more <w:r> elements from markdown-inline-emphasis text.

    Returns concatenated XML string. Input MUST already be XML-escaped.
    See _tokenize_inline_runs for supported patterns.

    Empty input → empty string (caller emits empty <w:p> if needed).
    """
    runs = _tokenize_inline_runs(text)
    if not runs:
        return ''
    parts = []
    for r in runs:
        rpr = []
        if r['bold']:
            rpr.append('<w:b/>')
        if r['italic']:
            rpr.append('<w:i/>')
        rpr_xml = f'<w:rPr>{"".join(rpr)}</w:rPr>' if rpr else ''
        parts.append(f'<w:r>{rpr_xml}<w:t xml:space="preserve">{r["text"]}</w:t></w:r>')
    return ''.join(parts)


def _build_minimal_docx_from_scratch(output_path, tokens, original_styles, fallback_stats, projection_uid):
    """P2 reconstruction: build a minimal .docx + bundle canonical styles.

    v1.0.2 amendment per v1.31.0 spec [c5e2f8a3 v0.6 LOCKED] §3.2 Edit 2:
    - Inline guard for pre-v1.28.0 working copies missing original_styles
      (v0.5 P1-6 + v0.6 D1-cheap absorption — echoes projection_uid)
    - Lower-strip heading anti-collision detection lands in fallback_stats
      (v0.5 P1-2 + P1-B + v0.6 P1-B absorption)
    - Canonical [Content_Types].xml + word/_rels/document.xml.rels per
      spec §3.1.1 + §3.1.2 (replaces v1.0.1 non-conformant Default Extension="xml")
    - Styles bundled via docx_styles_bundle.write_styles_to_docx

    Lower fidelity than P1 — loses macros, embedded fonts, custom XML.
    Preserves named styles + theme + margins from original_styles dict.
    """
    # --- Inline guard: pre-v1.28.0 working copy edge case (v0.6 D1-cheap absorption) ---
    if not original_styles or not isinstance(original_styles, dict):
        raise SystemExit(
            f"P2 reconstruction failed: working copy projection {projection_uid} "
            f"has no original_styles (predates v1.28.0).\n\n"
            f"Two recovery paths:\n"
            f"  (a) IF source binary exists, run:\n"
            f"      python3 .tropo/scripts/tropo-backfill-styles.py --projection {projection_uid}\n"
            f"      to backfill original_styles on the projection, then re-run this command.\n"
            f"  (b) IF source binary is also gone, re-import via:\n"
            f"      python3 .tropo/scripts/import-walker.py create-sidecar <source-path>"
        )

    # --- Heading anti-collision detection (v0.5 P1-2 + v0.6 P1-B lower-strip) ---
    named_styles = original_styles.get('named_styles', []) or []

    def _norm(sid):
        return (sid or '').strip().lower() if isinstance(sid, str) else ''

    titles = [s for s in named_styles
              if isinstance(s, dict) and _norm(s.get('id')) == 'title']
    h1s = [s for s in named_styles
           if isinstance(s, dict) and _norm(s.get('id')) in ('heading1', 'heading 1')]
    fallback_stats['p2_heading_indistinguishable_from_title'] = (
        len(titles) > 0
        and len(h1s) > 0
        and titles[0].get('font_family') == h1s[0].get('font_family')
        and titles[0].get('font_size_half_pt') == h1s[0].get('font_size_half_pt')
        and titles[0].get('bold') == h1s[0].get('bold')
    )

    # Set title_fallback_reason per the existing convention
    if titles:
        fallback_stats['title_fallback_reason'] = None  # Title style available
    elif h1s:
        fallback_stats['title_fallback_reason'] = 'no_title_style_safe_promotion'
    else:
        fallback_stats['title_fallback_reason'] = 'no_heading_styles_available'

    # --- Build document.xml from tokens (preserved from v1.0.1 verbatim) ---
    body_parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                  '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
                  '<w:body>']

    # v0.7.3 R4 D1.1 absorption — use Title style for title tokens when the
    # source had a Title style. Previously v1.0.1 lumped title+h2 → "Heading1",
    # collapsing the document cover into a section heading. The `titles` list
    # was already computed above for heading-anti-collision detection.
    title_pstyle = 'Title' if titles else 'Heading1'

    for tok in tokens:
        # v0.7.2 R4 P0 absorption: defensive read for tokens without 'text' key
        # (table tokens carry 'rows', code/hr tokens may carry other shapes).
        # The v1.0.1 P2 body assembly assumed every token had 'text' — latent
        # KeyError surfaced when v1.31.0 unlocked the P2 path. Spec §3.2 Edit 2's
        # "preserve verbatim" instruction is amended to permit this defensive read
        # per v0.7.2 amendment (§7 Known Gaps now records tables as P2 lower-fidelity).
        text = tok.get('text', '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # v0.7.4 R4 D1.3 absorption — text becomes one-or-more <w:r> runs with
        # bold/italic flags derived from markdown inline emphasis (`**bold**`,
        # `_italic_`). Previous v0.7.3 emitted the raw text as a single run,
        # which made literal `**` and `_` markers visible to the user — every
        # heading in the competitive brief had `**Heading text**` visible.
        runs_xml = _emit_inline_runs(text)
        # v0.7.3 R4 D1.1 absorption — title uses Title pStyle (when Title style
        # is available in source); h2 still uses Heading1. Splits the prior
        # v1.0.1 collapse that made the document cover render as a section header.
        if tok['kind'] == 'title':
            body_parts.append(f'<w:p><w:pPr><w:pStyle w:val="{title_pstyle}"/></w:pPr>{runs_xml}</w:p>')
        elif tok['kind'] == 'h2':
            body_parts.append(f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>{runs_xml}</w:p>')
        elif tok['kind'] == 'h3':
            body_parts.append(f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>{runs_xml}</w:p>')
        elif tok['kind'] == 'h4':
            body_parts.append(f'<w:p><w:pPr><w:pStyle w:val="Heading3"/></w:pPr>{runs_xml}</w:p>')
        elif tok['kind'] in ('ul', 'ol'):
            # Bullet glyph emits as plain run; markdown emphasis inside list text
            # tokenizes normally via runs_xml.
            body_parts.append(f'<w:p><w:r><w:t xml:space="preserve">• </w:t></w:r>{runs_xml}</w:p>')
        elif tok['kind'] == 'table':
            # v0.7.3 R4 D1.4 absorption — informative placeholder text replaces
            # silent <w:p/> blank gap. Tells the user what happened + names
            # the recovery path. Aligns with §3.7 P2 lower-fidelity contract
            # while keeping the user-encounter honest. v0.7.2 emitted blank
            # <w:p/> per spec compliance; R4 production review caught this
            # was non-obvious to stakeholders. Full table reconstruction
            # remains Path 2 for v1.32.0+.
            body_parts.append('<w:p><w:r><w:t xml:space="preserve">[Table content not preserved in P2 fallback — re-export with the original source .docx to restore]</w:t></w:r></w:p>')
        else:
            body_parts.append(f'<w:p>{runs_xml}</w:p>')
    body_parts.append('</w:body></w:document>')
    document_xml = '\n'.join(body_parts)

    # --- Canonical [Content_Types].xml per spec §3.1.1 (v0.2 P0-3 absorption) ---
    # NO <Default Extension="xml"> — that created the non-conformant conflict
    # with the styles Override that v1.0.1 silently shipped. Two Overrides only.
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''

    # Package-level rels — unchanged from v1.0.1 (relates package to word/document.xml)
    package_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''

    # --- Canonical word/_rels/document.xml.rels per spec §3.1.2 ---
    # Declares the styles relationship; write_styles_to_docx is idempotent if
    # this is already canonical (content-comparison per v0.5 P0-1 absorption).
    word_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

    # --- Write the .docx skeleton ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', package_rels)
        zf.writestr('word/document.xml', document_xml)
        # F4: P2 path registers rebuilt hyperlinks too
        zf.writestr('word/_rels/document.xml.rels', _patch_word_rels(word_rels.encode('utf-8')))

    # --- Bundle styles via the new shared module (final step) ---
    # docx_styles_bundle is imported at module-top (v0.7 R2 D2-3 absorption).
    # write_styles_to_docx is content-comparison idempotent; we just wrote
    # canonical Content_Types/rels so its only work is to add word/styles.xml.
    # TypeError propagates if original_styles shape is invalid.
    docx_styles_bundle.write_styles_to_docx(output_path, original_styles)


if __name__ == '__main__':
    main()
