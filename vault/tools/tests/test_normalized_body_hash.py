#!/usr/bin/env python3
"""Focused adversarial plants for the Gardener Pruning hash slice."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Union


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "vault" / "tools"))

from lib.normalized_body_hash import (  # noqa: E402
    BodyBoundaryError,
    normalized_body_bytes,
    normalized_body_sha256,
    raw_body_sha256,
)


Body = Union[str, bytes]


class TestNormalizedBodyHash(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._counter = 0

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _document(self, body: Body, frontmatter: str = "uid: deadbeef\n") -> Path:
        self._counter += 1
        path = self.root / f"plant-{self._counter}.md"
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        path.write_bytes(
            b"---\n"
            + frontmatter.encode("utf-8")
            + b"---\n"
            + body_bytes
        )
        return path

    def test_identical_body_has_identical_hash(self) -> None:
        first = self._document("# Same thought\n\nUnchanged.\n")
        second = self._document("# Same thought\n\nUnchanged.\n")

        self.assertEqual(
            normalized_body_sha256(first),
            normalized_body_sha256(second),
        )

    def test_frontmatter_only_pruning_write_is_neutral(self) -> None:
        body = "# Governed body\n\nThe judged prose stays byte-identical.\n"
        before = self._document(body, "uid: deadbeef\nstatus: active\n")
        after = self._document(
            body,
            "uid: deadbeef\nstatus: active\n"
            "pruning:\n"
            "  verdict: finished\n"
            "  normalized_body_hash_judged: abc123\n",
        )

        self.assertEqual(raw_body_sha256(before), raw_body_sha256(after))
        self.assertEqual(
            normalized_body_sha256(before),
            normalized_body_sha256(after),
        )

    def test_declared_maintenance_edits_are_neutral(self) -> None:
        base = self._document("Alpha\n\nOmega\n")
        nav_regenerated = self._document(
            "Alpha\n"
            "<!-- nav-block:start -->\n"
            "**Relations**\n"
            "<!-- nav-block:end -->\n"
            "Omega\n"
        )
        whitespace_churn = self._document(b"Alpha  \r\n \t\r\nOmega\t\r\n\r\n")

        expected = normalized_body_sha256(base)
        self.assertNotEqual(raw_body_sha256(base), raw_body_sha256(nav_regenerated))
        self.assertEqual(expected, normalized_body_sha256(nav_regenerated))
        self.assertEqual(expected, normalized_body_sha256(whitespace_churn))

    def test_unicode_canonical_equivalents_are_neutral(self) -> None:
        composed = self._document("Caf\u00e9\n")
        decomposed = self._document("Cafe\u0301\n")

        self.assertNotEqual(raw_body_sha256(composed), raw_body_sha256(decomposed))
        self.assertEqual(
            normalized_body_sha256(composed),
            normalized_body_sha256(decomposed),
        )

    def test_real_body_edits_change_hash(self) -> None:
        original = self._document("The body is live.\n")
        prose_edit = self._document("The body is done.\n")
        em_dash = self._document("Meaning\u2014with a pause.\n")
        hyphen = self._document("Meaning-with a pause.\n")

        self.assertNotEqual(
            normalized_body_sha256(original),
            normalized_body_sha256(prose_edit),
        )
        self.assertNotEqual(
            normalized_body_sha256(em_dash),
            normalized_body_sha256(hyphen),
        )

    def test_ambiguous_frontmatter_body_boundary_fails_closed(self) -> None:
        missing_open = self.root / "missing-open.md"
        missing_open.write_bytes(b"# Prose\n\n---\n\nNot frontmatter.\n")
        missing_close = self.root / "missing-close.md"
        missing_close.write_bytes(b"---\nuid: deadbeef\n# Body without close\n")

        for plant in (missing_open, missing_close):
            with self.subTest(plant=plant.name):
                with self.assertRaisesRegex(BodyBoundaryError, "cure:"):
                    normalized_body_sha256(plant)

    def test_invalid_utf8_replacement_is_deterministic(self) -> None:
        invalid = self._document(b"Broken byte: \xff\n")
        explicit_replacement = self._document("Broken byte: \ufffd\n")

        first = normalized_body_sha256(invalid)
        self.assertEqual(first, normalized_body_sha256(invalid))
        self.assertEqual(first, normalized_body_sha256(explicit_replacement))
        self.assertIn("\ufffd".encode("utf-8"), normalized_body_bytes(invalid))


if __name__ == "__main__":
    unittest.main()
