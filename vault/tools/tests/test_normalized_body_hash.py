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
        # v1.89 271d28d7 AC6: the layout here is the one the renderer actually
        # emits — a blank line before the block and after it. The previous
        # fixture had neither, and that mattered: against the real layout the
        # old unanchored strip left 'Alpha\n\n\n\nOmega\n' and T2 moved on every
        # breadcrumb regeneration. The synthetic fixture was the only shape in
        # which that strip looked neutral, so it passed while the property it
        # claimed was false in production.
        base = self._document("Alpha\n\nOmega\n")
        nav_regenerated = self._document(
            "Alpha\n"
            "\n"
            "<!-- nav-block:start -->\n"
            "**📍 Vault Path:** [parent](uid.md) → **This file's title**\n"
            "<!-- nav-block:end -->\n"
            "\n"
            "Omega\n"
        )
        whitespace_churn = self._document(b"Alpha  \r\n \t\r\nOmega\t\r\n\r\n")

        expected = normalized_body_sha256(base)
        self.assertNotEqual(raw_body_sha256(base), raw_body_sha256(nav_regenerated))
        self.assertEqual(expected, normalized_body_sha256(nav_regenerated))
        self.assertEqual(expected, normalized_body_sha256(whitespace_churn))

    def test_every_production_caller_shares_one_nav_pattern(self) -> None:
        """v1.89 271d28d7 AC6 — no module may own a second nav-block regex.

        This asserts PROVENANCE, not identity, and the difference is the whole
        test. `re.compile` caches: two modules that separately compile the same
        pattern string with the same flags receive the *same object*, so an
        `assertIs` against governed_body passes even for a module that never
        imported it. The first version of this case did exactly that and
        survived a planted local regex.

        So: substitute a unique sentinel into governed_body, re-execute each
        caller, and require the caller to be holding the sentinel. Only a real
        import can produce that.
        """
        import importlib
        import importlib.util
        import re as _re

        tools = Path(__file__).resolve().parents[1]
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        from lib import governed_body

        sentinel_text = _re.compile(r"^SENTINEL-TEXT-DO-NOT-MATCH$")
        sentinel_bytes = _re.compile(rb"^SENTINEL-BYTES-DO-NOT-MATCH$")
        original_text = governed_body._NAV_BLOCK_RE
        original_bytes = governed_body.NAV_BLOCK_BYTES_RE
        governed_body._NAV_BLOCK_RE = sentinel_text
        governed_body.NAV_BLOCK_BYTES_RE = sentinel_bytes
        try:
            for module_name, attribute, expected in (
                ("lib.tropo_round_trip_receipt", "_NAV_BLOCK_RE", sentinel_text),
                ("lib.tropo_update_receipt", "_NAV_BLOCK_RE", sentinel_text),
                ("lib.pruning_contract", "NAV_BLOCK_RE", sentinel_bytes),
            ):
                module = importlib.reload(importlib.import_module(module_name))
                self.assertIs(
                    getattr(module, attribute), expected,
                    "{} compiles its own nav pattern instead of importing "
                    "governed_body".format(module_name),
                )

            spec = importlib.util.spec_from_file_location(
                "_ac6_rebuild_index", tools / "tropo-rebuild-index.py"
            )
            rebuild = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rebuild)
            self.assertIs(
                rebuild._NAV_BLOCK_RE, sentinel_text,
                "tropo-rebuild-index compiles its own FTS nav pattern",
            )
        finally:
            governed_body._NAV_BLOCK_RE = original_text
            governed_body.NAV_BLOCK_BYTES_RE = original_bytes
            for module_name in ("lib.tropo_round_trip_receipt",
                                "lib.tropo_update_receipt",
                                "lib.pruning_contract"):
                importlib.reload(importlib.import_module(module_name))

    def test_no_caller_keeps_a_local_regex_fallback(self) -> None:
        """v1.89 271d28d7 AC6 — unavailability must refuse, not strip locally.

        A fallback that compiles its own pattern satisfies the letter of
        "imports governed_body" while restoring the exact drift the AC removes:
        it is dormant until the import breaks, and then it silently does the
        wrong thing. So the contract is refusal.
        """
        import importlib.util

        engine_path = (
            Path(__file__).resolve().parents[3]
            / ".tropo" / "scripts" / "lib" / "ship_extract" / "cleanup_engine.py"
        )
        spec = importlib.util.spec_from_file_location("_ac6_refusal_engine", engine_path)
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)

        # Force canonical unavailability by pointing the search somewhere with
        # no governed_body.py, and require a loud refusal.
        original_file = engine.__file__
        try:
            engine.__file__ = str(Path(tempfile.mkdtemp()) / "cleanup_engine.py")
            with self.assertRaises(RuntimeError) as caught:
                engine._strip_nav_block("<!-- nav-block:start -->\nx\n<!-- nav-block:end -->\n")
            self.assertIn("governed_body", str(caught.exception))
        finally:
            engine.__file__ = original_file

        # And the source carries no private nav pattern to fall back to.
        tools = Path(__file__).resolve().parents[1]
        rebuild_source = (tools / "tropo-rebuild-index.py").read_text()
        self.assertNotRegex(
            rebuild_source,
            r"_NAV_BLOCK_RE\s*=\s*(?:__import__\('re'\)|re)\.compile",
            "tropo-rebuild-index must not compile its own nav pattern",
        )
        engine_source = engine_path.read_text()
        self.assertNotIn(
            "nav-block:start -->.*?<!-- nav-block:end",
            engine_source,
            "the ship-extract engine must not carry its own nav pattern",
        )

    def test_ship_extraction_does_not_delete_quoted_sentinels(self) -> None:
        """The customer receives this output; eating their prose is worst here."""
        import importlib.util

        engine_path = (
            Path(__file__).resolve().parents[3]
            / ".tropo" / "scripts" / "lib" / "ship_extract" / "cleanup_engine.py"
        )
        spec = importlib.util.spec_from_file_location("_ac6_cleanup_engine", engine_path)
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)

        prose = "# Doc\n\nQuote `<!-- nav-block:start -->` … `<!-- nav-block:end -->` here.\n"
        self.assertEqual(engine._strip_nav_block(prose), prose)

        chrome = "# Doc\n\n<!-- nav-block:start -->\ncrumbs\n<!-- nav-block:end -->\n\nBody.\n"
        stripped = engine._strip_nav_block(chrome)
        self.assertNotIn("crumbs", stripped)
        self.assertIn("Body.", stripped)

    def test_inline_sentinel_prose_is_not_eaten(self) -> None:
        # 132fb547 — the document that DEFINES these transforms — quotes both
        # sentinels inline while explaining them. The unanchored strip deleted
        # the author's sentence from the hashed content, so T2 was hashing a
        # mutilated copy of its own specification.
        prose = (
            "Strip every `<!-- nav-block:start -->` … `<!-- nav-block:end -->` "
            "region before hashing.\n"
        )
        document = self._document(prose)
        self.assertEqual(
            normalized_body_sha256(document),
            normalized_body_sha256(self._document(prose)),
        )
        self.assertIn(
            b"nav-block:start",
            normalized_body_bytes(document),
            "an author's words are not renderer chrome",
        )

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
