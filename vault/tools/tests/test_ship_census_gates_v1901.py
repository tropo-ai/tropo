#!/usr/bin/env python3
"""v1.90.1 ship-census gates — F1 red-baseline (G110 assignment, Mike-directed).

Three properties, each red at birth because the fixes do not exist yet:
1. vault/schema/ ships wholesale (the import-time registry the shipped libs
   and suites need — measured absent 0-of-1029 by sa.release-test-harness).
2. Every shipped test module COLLECTS in-box — an import-time dependency
   that ships missing refuses the build instead of dying silently in a
   customer studio (G110: "silent is the part that matters").
3. The Step-10 identity sanitiser spares its own source — the shipped copy
   self-rewrote its pattern constants into no-ops (r'the Studio' ->
   'the Studio'), a sanitiser that cannot sanitise.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "builder_v1901", TOOLS / "tropo-build-release.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["builder_v1901"] = module
    spec.loader.exec_module(module)
    return module


class SchemaShipsTests(unittest.TestCase):
    """F1 part 1 — vault/schema/ enters the ship census wholesale."""

    def test_schema_step_copies_the_directory(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp) / "studio"
            schema = studio / "vault" / "schema"
            schema.mkdir(parents=True)
            (schema / "tool-telemetry-registry.json").write_text("{}\n")
            (schema / "one-prompt-release-scorecard.schema.json").write_text("{}\n")
            build_dir = Path(tmp) / "build"
            (build_dir / "vault").mkdir(parents=True)
            with mock.patch.object(builder.tropo_roots, "VAULT_DIR",
                                   str(studio / "vault")):
                with mock.patch.object(builder, "DRY_RUN", False):
                    copied = builder.step_3j_copy_vault_schema(str(build_dir))
            shipped = sorted(p.name for p in (build_dir / "vault" / "schema").glob("*.json"))
            self.assertEqual(
                shipped,
                ["one-prompt-release-scorecard.schema.json",
                 "tool-telemetry-registry.json"],
                "vault/schema did not ship wholesale — F1, the import-time "
                "registry the shipped suites need")
            self.assertEqual(copied, 2)

    def test_absent_source_schema_dir_refuses_loudly(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp) / "studio"
            (studio / "vault").mkdir(parents=True)
            with mock.patch.object(builder.tropo_roots, "VAULT_DIR",
                                   str(studio / "vault")):
                with self.assertRaises(SystemExit) as caught:
                    builder.step_3j_copy_vault_schema(str(Path(tmp) / "build"))
            self.assertIn("vault/schema", str(caught.exception))


class ShippedTestsCollectGateTests(unittest.TestCase):
    """F1 part 2 — an unimportable shipped test module refuses the build."""

    def _gate(self, builder, build_dir):
        with mock.patch.object(builder, "DRY_RUN", False):
            return builder.step_10b_assert_shipped_tests_collect(str(build_dir))

    def test_missing_import_dependency_refuses_naming_module(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp) / "build"
            tests = build / "vault" / "tools" / "tests"
            tests.mkdir(parents=True)
            (tests / "test_broken_v1901.py").write_text(
                "import lib.tool_telemetry  # needs vault/schema at import\n")
            (build / "vault" / "tools" / "lib").mkdir(parents=True)
            with mock.patch.object(builder.tropo_roots, "VAULT_DIR",
                                   str(build / "vault")):
                with self.assertRaises(SystemExit) as caught:
                    self._gate(builder, build)
            self.assertIn("test_broken_v1901.py", str(caught.exception),
                          "the refusal must name the module that cannot collect")

    def test_importable_module_passes(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp) / "build"
            tests = build / "vault" / "tools" / "tests"
            tests.mkdir(parents=True)
            (tests / "test_fine_v1901.py").write_text(
                "X = 1\n")
            with mock.patch.object(builder.tropo_roots, "VAULT_DIR",
                                   str(build / "vault")):
                result = self._gate(builder, build)
            self.assertTrue(result)


class SanitiserSparesItselfTests(unittest.TestCase):
    """The Step-10 identity sanitiser must not rewrite its own pattern block."""

    def test_sanitiser_does_not_degenerate_its_own_source(self) -> None:
        builder = _load_builder()
        source_text = (TOOLS / "tropo-build-release.py").read_text(encoding="utf-8")
        needle = "(re.compile(r'the Studio', re.I), 'the Studio')"
        self.assertIn(needle, source_text,
                      "the SOURCE patterns must be intact for this test to mean anything")
        with tempfile.TemporaryDirectory() as tmp:
            victim = Path(tmp) / "tropo-build-release.py"
            victim.write_text(source_text, encoding="utf-8")
            with mock.patch.object(builder, "DRY_RUN", False):
                builder.step_10_sanitize_argo_identity(str(tmp))
            shipped = victim.read_text(encoding="utf-8")
            self.assertIn(
                needle, shipped,
                "the sanitiser rewrote its own pattern constants — the shipped "
                "tool degenerates into no-ops (G110 morning measurement)")


if __name__ == "__main__":
    unittest.main()
