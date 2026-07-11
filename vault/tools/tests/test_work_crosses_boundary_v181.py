#!/usr/bin/env python3
"""v1.81 Work Crosses the Boundary gauntlets — test-spec d3c7e049 (dev-spec 92093c81).

Six behaviors, one per acceptance criterion. Uses temp Studio fixtures + grep checks.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / 'vault' / 'tools'
sys.path.insert(0, str(TOOLS))


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


IW = _load_module('import_walker', TOOLS / 'tropo-import-walker.py')
EX = _load_module('tropo_extract', TOOLS / 'tropo-extract.py')
EXP = _load_module('tropo_export', TOOLS / 'tropo-export.py')
RTR = importlib.import_module('lib.tropo_round_trip_receipt')


def _minimal_docx(path: Path, body_text: str = 'Hello round-trip'):
    """Minimal valid .docx for gauntlet fixtures."""
    doc_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{body_text}</w:t></w:r></w:p>
  </w:body>
</w:document>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', rels)
        zf.writestr('word/document.xml', doc_xml)


def _docx_body_xml(inner_body: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
{inner_body}
  </w:body>
</w:document>"""


def _docx_paragraph(text: str, *, style: str | None = None, list_item: bool = False) -> str:
    ppr_parts = []
    if style:
        ppr_parts.append(f'<w:pStyle w:val="{style}"/>')
    if list_item:
        ppr_parts.append('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
    ppr = ''
    if ppr_parts:
        ppr = '    <w:pPr>' + ''.join(ppr_parts) + '</w:pPr>\n'
    esc = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return f"""    <w:p>
{ppr}    <w:r><w:t>{esc}</w:t></w:r>
    </w:p>"""


def _docx_table(*rows: tuple[str, ...]) -> str:
    trs = []
    for row in rows:
        tcs = []
        for cell in row:
            esc = cell.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            tcs.append(f"""      <w:tc>
        <w:p><w:r><w:t>{esc}</w:t></w:r></w:p>
      </w:tc>""")
        trs.append('    <w:tr>\n' + '\n'.join(tcs) + '\n    </w:tr>')
    return '    <w:tbl>\n' + '\n'.join(trs) + '\n    </w:tbl>'


def _docx_sdt(inner_paragraphs: list[str]) -> str:
    inner = '\n'.join(_docx_paragraph(t) for t in inner_paragraphs)
    return f"""    <w:sdt>
      <w:sdtContent>
{inner}
      </w:sdtContent>
    </w:sdt>"""

def _docx_nested_sdt(outer_paragraphs: list[str], inner_paragraphs: list[str]) -> str:
    """Outer content control wrapping a nested w:sdt (B5 regression)."""
    outer = '\n'.join(_docx_paragraph(t) for t in outer_paragraphs)
    inner = '\n'.join(_docx_paragraph(t) for t in inner_paragraphs)
    nested = f"""      <w:sdt>
        <w:sdtContent>
{inner}
        </w:sdtContent>
      </w:sdt>"""
    return f"""    <w:sdt>
      <w:sdtContent>
{nested}
{outer}
      </w:sdtContent>
    </w:sdt>"""



def _real_docx(path: Path, body_inner: str):
    """Write a .docx whose word/document.xml body is caller-supplied OOXML."""
    doc_xml = _docx_body_xml(body_inner)
    content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', rels)
        zf.writestr('word/document.xml', doc_xml)


def _docx_user_content_hash(docx_path: Path) -> str:
    result = EX.extract_docx(docx_path)
    return RTR.user_content_hash(result.markdown_body)


def _docx_export_round_trip(scaffold: Path, out_path: Path) -> tuple[str, str]:
    """Extract → body_swap → re-extract; return (source_hash, export_hash)."""
    extracted = EX.extract_docx(scaffold)
    fallback_stats = {}
    EXP.body_swap(
        scaffold_path=scaffold,
        output_path=out_path,
        working_copy_body=extracted.markdown_body,
        template_named_styles={},
        fallback_stats=fallback_stats,
        is_transformation=False,
    )
    source_hash = RTR.user_content_hash(extracted.markdown_body)
    export_hash = RTR.user_content_hash(EX.extract_docx(out_path).markdown_body)
    return source_hash, export_hash


class StudioFixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / '04-external-work').mkdir()
        (self.root / 'vault' / 'files').mkdir(parents=True)
        (self.root / '.tropo-studio' / 'reconciler').mkdir(parents=True)
        (self.root / 'vault' / '00-index.jsonl').write_text('')

    def cleanup(self):
        self.tmp.cleanup()


class TestV181S1NamedDefects(unittest.TestCase):
    """AC2 — fa026415, a2c8ea26, 311c63aa."""

    def test_fa026415_ungoverned_folder_enumeration(self):
        fx = StudioFixture()
        try:
            drop = fx.root / '04-external-work' / 'share-drop'
            drop.mkdir()
            _minimal_docx(drop / 'doc-a.docx')
            _minimal_docx(drop / 'doc-b.docx')
            events = []
            IW._detect_deltas_in_ungoverned_folders(fx.root, IW.parse_tropoignore(fx.root), events)
            paths = {e['path'] for e in events if e['type'] == 'new-uncompanioned-file'}
            self.assertIn('04-external-work/share-drop/doc-a.docx', paths)
            self.assertIn('04-external-work/share-drop/doc-b.docx', paths)
        finally:
            fx.cleanup()

    def test_a2c8ea26_folder_marker_schema_version_2(self):
        fx = StudioFixture()
        try:
            folder = fx.root / '04-external-work' / 'test-folder'
            folder.mkdir()
            IW.write_folder_marker(folder, 'abcd1234', 'test-folder', '04-external-work/test-folder')
            marker = (folder / '.tropo-studio' / '.tropo-folder.md').read_text()
            self.assertIn('schema_version: 2', marker)
            self.assertNotIn('schema_version: 1', marker)
        finally:
            fx.cleanup()

    def test_311c63aa_dual_path_documented(self):
        text = (TOOLS / 'tropo-import-walker.py').read_text()
        self.assertIn('311c63aa', text)
        self.assertIn('Sidecar', text)
        self.assertIn('Vault projection', text)


class TestV181S2FormatGaps(unittest.TestCase):
    """AC3 + AC4 — .md content-copy, .pptx pointer, v-NN versioning."""

    def test_md_content_copy_same_bytes(self):
        fx = StudioFixture()
        try:
            md_path = fx.root / '04-external-work' / 'note.md'
            content = '# Title\n\nSame bytes.\n'
            md_path.write_text(content, encoding='utf-8')
            result = EX.extract_md(md_path)
            self.assertTrue(result.stats.get('content_copy'))
            self.assertEqual(result.markdown_body, content)
            self.assertEqual(result.stats['source_byte_hash'],
                             __import__('hashlib').sha256(content.encode()).hexdigest())
        finally:
            fx.cleanup()

    def test_pptx_pointer_only_skips_working_copy(self):
        fx = StudioFixture()
        try:
            pptx = fx.root / '04-external-work' / 'deck.pptx'
            pptx.write_bytes(b'PK\x03\x04fake-pptx-bytes')
            result = EX.extract_pptx(pptx)
            self.assertTrue(result.stats.get('pptx_pointer_only'))
            self.assertEqual(result.markdown_body, '')
        finally:
            fx.cleanup()

    def test_md_and_pptx_not_hard_refused(self):
        text = (TOOLS / 'tropo-extract.py').read_text()
        self.assertIn("'.md', '.pptx'", text)
        self.assertNotIn('supported: .docx, .pdf (v1.74)', text)

    def test_vnn_output_path(self):
        fx = StudioFixture()
        try:
            src = fx.root / '04-external-work' / 'doc.docx'
            src.write_bytes(b'original')
            (fx.root / '04-external-work' / 'doc v-02.docx').write_bytes(b'v2')
            out = EXP.resolve_vnn_output_path(src)
            self.assertEqual(out.name, 'doc v-03.docx')
        finally:
            fx.cleanup()


class TestV181S3RoundTripReceipt(unittest.TestCase):
    """AC5 — locally-auditable round-trip receipt."""

    def test_receipt_four_properties(self):
        source = '# Hello\n\nUser words.\n'
        export = '# Hello\n\nUser words.\n'
        stats = {'inline_drawings_dropped': 2}
        receipt = RTR.build_round_trip_receipt_markdown(
            run_uid='test0001',
            projection_uid='proj0001',
            working_copy_uid='work0001',
            source_path='04-external-work/x.md',
            export_path='04-external-work/x v-02.md',
            source_pre_hash=RTR.user_content_hash(source),
            export_post_hash=RTR.user_content_hash(export),
            source_byte_hash='aa' * 32,
            export_byte_hash='bb' * 32,
            extraction_stats=stats,
            chrome_disclosure=[],
            generated_at='2026-07-05T00:00:00Z',
        )
        ok, reasons = RTR.verify_round_trip_receipt(receipt, source_text=source, export_text=export,
                                                     extraction_stats=stats)
        self.assertTrue(ok, reasons)
        self.assertIn('inline_drawings_dropped', receipt)
        self.assertIn(RTR.user_content_hash(source), receipt)

    def test_receipt_seal_blocks_post_write(self):
        from lib.tropo_update_receipt import ReceiptSeal, PostReceiptWriteError
        seal = ReceiptSeal()
        seal.seal('receipt.md')
        with self.assertRaises(PostReceiptWriteError):
            seal.record_write('late-write.md')


class TestV181RendererIndependence(unittest.TestCase):
    """AC6 — no /api/docx renderer on export path."""

    def test_export_path_no_api_docx(self):
        text = (TOOLS / 'tropo-export.py').read_text()
        self.assertNotIn('/api/docx', text)
        self.assertNotIn('localhost/api', text)
        self.assertIn('body_swap', text)


class TestV181S1DocxRoundTripSmoke(unittest.TestCase):
    """AC1 — real .docx import → extract smoke (full Word edit out of scope for CI)."""

    def test_docx_import_sidecar_and_extract(self):
        fx = StudioFixture()
        try:
            drop = fx.root / '04-external-work' / 'roundtrip'
            drop.mkdir()
            docx = drop / 'brief.docx'
            _minimal_docx(docx, 'Round trip content')
            studio = fx.root.resolve()
            args = type('A', (), {'source': str(docx.resolve()), 'run_uid': 't', 'executive': 'test'})()
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            import contextlib
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                IW.cmd_create_sidecar(args, studio)
            sidecar = drop / '.tropo-studio' / 'brief.docx.tropo.md'
            self.assertTrue(sidecar.exists())
            fm = IW.parse_frontmatter(sidecar)
            uid = fm['uid']
            proj = studio / 'vault' / 'files' / f'{uid}.md'
            self.assertTrue(proj.exists())
            proj_fm = IW.parse_frontmatter(proj)
            self.assertEqual(proj_fm.get('schema_version'), 2)
        finally:
            fx.cleanup()




class TestV181RealDocxE2E(unittest.TestCase):
    """Argus-requested real-.docx e2e — pipe-table, style-list, sdt, deletion receipt."""

    def test_e2e_pipe_table_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / 'pipe-table.docx'
            body = '\n'.join([
                _docx_table(('Col A', 'Col B'), ('A|B', 'plain')),
            ])
            _real_docx(docx, body)
            result = EX.extract_docx(docx)
            self.assertIn('A\\|B', result.markdown_body)
            self.assertEqual(result.stats.get('tables_extracted'), 1)
            out = Path(tmp) / 'pipe-table-out.docx'
            pre, post = _docx_export_round_trip(docx, out)
            self.assertEqual(pre, post)

    def test_e2e_style_list_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / 'style-list.docx'
            body = '\n'.join([
                _docx_paragraph('List item one', style='ListParagraph', list_item=True),
                _docx_paragraph('List item two', style='ListParagraph', list_item=True),
            ])
            _real_docx(docx, body)
            result = EX.extract_docx(docx)
            self.assertIn('- List item one', result.markdown_body)
            self.assertIn('- List item two', result.markdown_body)
            self.assertGreaterEqual(result.stats.get('lists_extracted', 0), 1)
            out = Path(tmp) / 'style-list-out.docx'
            pre, post = _docx_export_round_trip(docx, out)
            self.assertEqual(pre, post)


    def test_e2e_bare_list_bullet_style_no_numpr(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / 'bare-bullet.docx'
            body = '\n'.join([
                _docx_paragraph('Bullet only', style='ListBullet'),
            ])
            _real_docx(docx, body)
            result = EX.extract_docx(docx)
            self.assertIn('- Bullet only', result.markdown_body)
            self.assertGreaterEqual(result.stats.get('lists_extracted', 0), 1)

    def test_e2e_bare_list_number_style_no_numpr(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / 'bare-number.docx'
            body = '\n'.join([
                _docx_paragraph('Number only', style='ListNumber'),
            ])
            _real_docx(docx, body)
            result = EX.extract_docx(docx)
            self.assertIn('1. Number only', result.markdown_body)
            self.assertGreaterEqual(result.stats.get('lists_extracted', 0), 1)

    def test_edit_then_export_list_round_trip(self):
        """Edited markdown lists must re-extract as markers, not Normal + literal bullet glyph."""
        with tempfile.TemporaryDirectory() as tmp:
            scaffold = Path(tmp) / 'scaffold.docx'
            _real_docx(scaffold, _docx_paragraph('Intro'))
            out = Path(tmp) / 'edited-lists.docx'
            md = "- Alpha item\n- Beta item\n1. Numbered one\n"
            fallback_stats = {}
            EXP.body_swap(
                scaffold_path=scaffold,
                output_path=out,
                working_copy_body=md,
                template_named_styles={},
                fallback_stats=fallback_stats,
                is_transformation=False,
            )
            result = EX.extract_docx(out)
            self.assertIn('- Alpha item', result.markdown_body)
            self.assertIn('- Beta item', result.markdown_body)
            self.assertIn('1. Numbered one', result.markdown_body)
            self.assertNotIn('•', result.markdown_body)
            out2 = Path(tmp) / 'edited-lists-out2.docx'
            pre, post = _docx_export_round_trip(out, out2)
            self.assertEqual(pre, post)

    def test_edit_then_export_nested_list_round_trip(self):
        """Nested/indented markdown lists must survive export with numPr ilvl (B3 cycle 4)."""
        with tempfile.TemporaryDirectory() as tmp:
            scaffold = Path(tmp) / 'scaffold.docx'
            _real_docx(scaffold, _docx_paragraph('Intro'))
            out = Path(tmp) / 'nested-lists.docx'
            md = "- Top item\n  - Nested bullet\n  - Second nested\n1. First numbered\n  1. Nested numbered\n"
            fallback_stats = {}
            EXP.body_swap(
                scaffold_path=scaffold,
                output_path=out,
                working_copy_body=md,
                template_named_styles={},
                fallback_stats=fallback_stats,
                is_transformation=False,
            )
            result = EX.extract_docx(out)
            self.assertIn('- Top item', result.markdown_body)
            self.assertIn('  - Nested bullet', result.markdown_body)
            self.assertIn('  - Second nested', result.markdown_body)
            self.assertIn('1. First numbered', result.markdown_body)
            self.assertIn('  1. Nested numbered', result.markdown_body)
            out2 = Path(tmp) / 'nested-lists-out2.docx'
            pre, post = _docx_export_round_trip(out, out2)
            self.assertEqual(pre, post)

    def test_text_conservation_backstop_unwalked_container(self):
        """B5: body-level unwalked OOXML must disclose via conservation, not silent drop."""
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / 'custom-xml.docx'
            body = """
    <w:customXml>
      <w:customXmlPr><w:placeholder w:val=""/></w:customXmlPr>
      <w:p><w:r><w:t>Unwalked customXml clause</w:t></w:r></w:p>
    </w:customXml>"""
            _real_docx(docx, body)
            result = EX.extract_docx(docx)
            self.assertNotIn('Unwalked customXml clause', result.markdown_body)
            self.assertGreater(result.stats.get('text_conservation_unaccounted_chars', 0), 0)
            self.assertGreater(result.stats.get('dropped_unaccounted_text_chars', 0), 0)
            self.assertTrue(RTR.extraction_stats_break_conservation(result.stats))

    def test_text_conservation_backstop_block_level_tracked_insert(self):
        """B5: block-level w:ins must disclose via conservation backstop."""
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / 'block-ins.docx'
            body = """
    <w:ins w:id="1" w:author="Reviewer" w:date="2026-01-01T00:00:00Z">
      <w:p><w:r><w:t>Block tracked insertion</w:t></w:r></w:p>
    </w:ins>
    <w:p><w:r><w:t>Visible sibling</w:t></w:r></w:p>"""
            _real_docx(docx, body)
            result = EX.extract_docx(docx)
            self.assertIn('Visible sibling', result.markdown_body)
            self.assertNotIn('Block tracked insertion', result.markdown_body)
            self.assertGreater(result.stats.get('text_conservation_unaccounted_chars', 0), 0)
            self.assertTrue(RTR.extraction_stats_break_conservation(result.stats))

    def test_e2e_content_control_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / 'sdt.docx'
            body = '\n'.join([
                _docx_sdt(['Controlled clause text']),
                _docx_paragraph('Outside control'),
            ])
            _real_docx(docx, body)
            result = EX.extract_docx(docx)
            self.assertIn('Controlled clause text', result.markdown_body)
            self.assertIn('Outside control', result.markdown_body)
            self.assertEqual(result.stats.get('dropped_content_controls', 0), 0)


    def test_e2e_nested_content_control_plus_sibling(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / 'nested-sdt.docx'
            body = '\n'.join([
                _docx_nested_sdt([], ['Nested clause text']),
                _docx_paragraph('Kept sibling outside nested control'),
            ])
            _real_docx(docx, body)
            result = EX.extract_docx(docx)
            self.assertIn('Nested clause text', result.markdown_body)
            self.assertIn('Kept sibling outside nested control', result.markdown_body)
            self.assertEqual(result.stats.get('dropped_content_controls', 0), 0)
            self.assertEqual(result.stats.get('text_conservation_unaccounted_chars', 0), 0)

    def test_e2e_deletion_scenario_failing_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / 'source.docx'
            export = tmp_path / 'export.docx'
            _real_docx(source, _docx_paragraph('Keep this paragraph'))
            _real_docx(export, _docx_paragraph(''))
            source_result = EX.extract_docx(source)
            export_result = EX.extract_docx(export)
            source_text = source_result.markdown_body
            export_text = export_result.markdown_body
            stats = {**source_result.stats, **export_result.stats}
            source_pre = RTR.user_content_hash(source_text)
            export_post = RTR.user_content_hash(export_text)
            self.assertNotEqual(source_pre, export_post)
            from lib.tropo_update_receipt import byte_hash
            receipt_md = RTR.build_round_trip_receipt_markdown(
                run_uid='del00001',
                projection_uid='proj0001',
                working_copy_uid='work0001',
                source_path=str(source),
                export_path=str(export),
                source_pre_hash=source_pre,
                export_post_hash=export_post,
                source_byte_hash=byte_hash(source.read_bytes()),
                export_byte_hash=byte_hash(export.read_bytes()),
                extraction_stats=stats,
                chrome_disclosure=[],
                generated_at='2026-07-05T18:00:00Z',
                result='fail',
            )
            self.assertIn('result: "fail"', receipt_md)
            self.assertIn('CONTENT DRIFT', receipt_md)
            ok, reasons = RTR.verify_round_trip_receipt(
                receipt_md,
                source_text=source_text,
                export_text=export_text,
                extraction_stats=stats,
            )
            self.assertFalse(ok, reasons)


class TestV181ReceiptThroughExportPath(unittest.TestCase):
    """Regression guard: the --write-receipt path in tropo-export MUST re-extract real
    .docx binaries through EXP._receipt_inputs. The prior build loaded tropo-extract from
    .tropo/scripts/ (wrong dir) and raised FileNotFoundError on every .docx receipt — while
    the isolated builder tests above stayed green. These drive the real export-side seam."""

    def test_load_tropo_extract_module_resolves(self):
        # Directly guards the path bug: the loader must find tropo-extract.py beside
        # tropo-export.py (vault/tools/), NOT in _SCRIPT_DIR (.tropo/scripts/).
        mod = EXP._load_tropo_extract_module()
        self.assertTrue(hasattr(mod, 'extract_docx'),
                        'tropo-extract module loaded but has no extract_docx')

    def test_receipt_inputs_real_docx_detects_deletion(self):
        # The headline covenant, through the REAL export path (not the isolated builder):
        # _receipt_inputs re-extracts source vs export .docx and must SEE a deletion.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.docx'
            export = Path(tmp) / 'export.docx'
            _real_docx(source, _docx_paragraph('Keep this confidential clause'))
            _real_docx(export, _docx_paragraph(''))  # content deleted
            source_text, export_text, _stats = EXP._receipt_inputs(source, export)
            self.assertNotEqual(source_text.strip(), export_text.strip(),
                                'receipt path failed to detect real .docx content deletion')

    def test_receipt_inputs_real_docx_no_false_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.docx'
            export = Path(tmp) / 'export.docx'
            _real_docx(source, _docx_paragraph('Keep this confidential clause'))
            _real_docx(export, _docx_paragraph('Keep this confidential clause'))
            source_text, export_text, _stats = EXP._receipt_inputs(source, export)
            self.assertEqual(source_text.strip(), export_text.strip(),
                             'receipt path reported false drift on an unchanged round-trip')


class TestV181TableCellBackslashRoundTrip(unittest.TestCase):
    r"""Regression: table-cell backslashes must NOT grow on extract->export round trips.
    The extract escaper (tropo-extract:384) does \ -> \\ then | -> \|; parse_table_row
    must be the EXACT inverse (\\ -> \, \| -> |). A prior build only un-escaped \|, so a
    cell like C:\path\to doubled its backslashes every pass (\\ -> \\\\ -> ... unbounded).
    Drives the REAL extract escaper + parse un-escaper end-to-end. Do NOT weaken: the pipe
    half (B2 fix) must remain a perfect fixed point."""

    def _roundtrip_once(self, cell_text):
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / 'bs.docx'
            _real_docx(docx, _docx_table((cell_text, 'plain')))
            md = EX.extract_docx(docx).markdown_body
            tables = [t for t in EXP.parse_working_copy_body(md) if t.get('kind') == 'table']
            self.assertTrue(tables, 'no table parsed from extracted markdown')
            data_row = tables[0]['rows'][-1]
            return data_row[0], len(data_row)

    def test_backslash_cell_faithful_and_idempotent(self):
        for original in [r'C:\path\to', '\\', r'A\|B', r'regex \d+ end', 'trailing\\']:
            seen, cur = [], original
            for _ in range(4):
                cur, ncols = self._roundtrip_once(cur)
                seen.append(cur)
                self.assertEqual(ncols, 2, f'{original!r}: column count drifted to {ncols}')
            self.assertEqual(seen[0], original,
                             f'{original!r}: not faithful on pass 1 -> {seen[0]!r}')
            self.assertEqual(len(set(seen)), 1,
                             f'{original!r}: not idempotent across round trips -> {seen}')

    def test_plain_pipe_cell_remains_fixed_point(self):
        recovered, ncols = self._roundtrip_once('A|B')
        self.assertEqual(recovered, 'A|B')
        self.assertEqual(ncols, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
