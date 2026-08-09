#!/usr/bin/env python3
"""Cut 4A section-first exact-body and stable-anchor plants."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import lib.distiller_content as dc


class WholeEntryTests(unittest.TestCase):
    def test_below_and_exact_utf8_byte_limit_return_one_exact_span(self):
        cases = (("hé", 4), ("éééé", 8))
        for body, limit in cases:
            with self.subTest(body=body):
                spans = dc.chunk_body("entry001", body, max_chunk_bytes=limit)
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].text, body)
                self.assertTrue(spans[0].span_anchor.whole_entry)
                self.assertEqual(spans[0].span_anchor.paragraph_start, 1)
                self.assertGreaterEqual(spans[0].span_anchor.paragraph_end, 1)

    def test_empty_body_has_a_deterministic_whole_entry_anchor(self):
        span = dc.chunk_body("entry001", "", max_chunk_bytes=8)[0]
        self.assertEqual(span.text, "")
        self.assertEqual(span.span_anchor.canonical(), "entry:p1-p1")


class HeadingPathAndDuplicateTests(unittest.TestCase):
    def test_preamble_and_nested_headings_get_section_local_paths(self):
        body = (
            "root paragraph long enough\n\n"
            "# Parent\n\nparent paragraph long enough\n\n"
            "## Child\n\nchild paragraph long enough\n"
        )
        spans = dc.chunk_body("entry001", body, max_chunk_bytes=24)
        paths = [span.span_anchor.heading_path for span in spans]
        self.assertIn((), paths)
        self.assertTrue(
            any(tuple(part.text for part in path) == ("Parent",) for path in paths)
        )
        self.assertTrue(
            any(
                tuple(part.text for part in path) == ("Parent", "Child")
                for path in paths
            )
        )
        self.assertEqual("".join(span.text for span in spans), body)

    def test_duplicate_sibling_headings_have_distinct_occurrences(self):
        body = (
            "# Same\n\nfirst paragraph is long\n\n"
            "# Same\n\nsecond paragraph is long\n"
        )
        spans = dc.chunk_body("entry001", body, max_chunk_bytes=20)
        same_parts = [
            span.span_anchor.heading_path[-1]
            for span in spans
            if span.span_anchor.heading_path
            and span.span_anchor.heading_path[-1].text == "Same"
        ]
        self.assertEqual({part.occurrence for part in same_parts}, {1, 2})
        self.assertEqual(
            len({span.span_anchor.canonical() for span in spans}), len(spans)
        )

    def test_duplicate_nested_heading_occurrence_resets_under_new_parent(self):
        body = (
            "# Parent\n\n## Child\n\nfirst child text\n\n"
            "# Parent\n\n## Child\n\nsecond child text\n"
        )
        spans = dc.chunk_body("entry001", body, max_chunk_bytes=18)
        child_paths = {
            tuple((part.text, part.occurrence) for part in span.span_anchor.heading_path)
            for span in spans
            if span.span_anchor.heading_path
            and span.span_anchor.heading_path[-1].text == "Child"
        }
        self.assertIn((("Parent", 1), ("Child", 1)), child_paths)
        self.assertIn((("Parent", 2), ("Child", 1)), child_paths)


class ParagraphPackingAndFenceTests(unittest.TestCase):
    def test_oversized_section_packs_whole_paragraphs_in_source_order(self):
        paragraphs = (
            "alpha alpha alpha",
            "beta beta beta",
            "gamma gamma gamma",
        )
        body = "\n\n".join(paragraphs)
        spans = dc.chunk_body("entry001", body, max_chunk_bytes=22)
        self.assertGreater(len(spans), 1)
        self.assertEqual("".join(span.text for span in spans), body)
        for paragraph in paragraphs:
            containing = [span for span in spans if paragraph in span.text]
            self.assertEqual(len(containing), 1)
        ranges = [
            (span.span_anchor.paragraph_start, span.span_anchor.paragraph_end)
            for span in spans
        ]
        self.assertEqual(ranges[0][0], 1)
        self.assertEqual(ranges[-1][1], 3)

    def test_fenced_block_is_atomic_and_hash_heading_inside_does_not_split(self):
        fence = "```\n# not a heading\n" + ("code-line\n" * 4) + "```\n\n"
        body = "intro paragraph\n\n" + fence + "outro paragraph"
        spans = dc.chunk_body("entry001", body, max_chunk_bytes=24)
        fence_spans = [span for span in spans if "```" in span.text]
        self.assertEqual(len(fence_spans), 1)
        self.assertIn(fence, fence_spans[0].text)
        self.assertFalse(
            any(
                any(part.text == "not a heading" for part in span.span_anchor.heading_path)
                for span in spans
            )
        )
        self.assertEqual("".join(span.text for span in spans), body)

    def test_single_oversized_paragraph_is_never_split(self):
        paragraph = "é" * 40
        spans = dc.chunk_body("entry001", paragraph, max_chunk_bytes=16)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].text, paragraph)
        self.assertGreater(len(spans[0].text.encode("utf-8")), 16)
        self.assertEqual(
            (
                spans[0].span_anchor.paragraph_start,
                spans[0].span_anchor.paragraph_end,
            ),
            (1, 1),
        )


class IndexedBodyLoaderTests(unittest.TestCase):
    def test_sqlite_loader_reads_entries_fts_body_exactly(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "index.sqlite"
        body = "# Indexed\n\nexact body"
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE VIRTUAL TABLE entries_fts USING fts5(uid UNINDEXED, title, body)"
        )
        conn.execute("INSERT INTO entries_fts VALUES (?,?,?)", ("entry001", "t", body))
        conn.commit()
        conn.close()

        loader = dc.SqliteContentLoader(
            path, index_as_of="snapshot-content-1", max_chunk_bytes=1024
        )
        spans = loader.load_spans("entry001")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].text, body)
        self.assertTrue(spans[0].span_anchor.whole_entry)


if __name__ == "__main__":
    unittest.main()
