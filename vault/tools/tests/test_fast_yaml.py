#!/usr/bin/env python3
"""The YAML loader swap: equivalence, and the fallback that protects a box.

talos-t40, 2026-08-09, velocity item 1 of the v1.86 retrospective.

Two claims are load-bearing and neither may be taken on trust:

1. `fast_yaml.safe_load` returns exactly what `yaml.safe_load` returned, on THIS
   vault's real frontmatter — not on a fixture that happens to be easy.
2. A machine with no libyaml still works. `CSafeLoader` exists only when PyYAML
   was built against the C library, and a customer studio is a zip on a machine
   we have never seen. A hard import would have turned a speedup into a boot
   failure for every box without it.
"""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

import yaml

TOOLS_DIR = Path(__file__).resolve().parents[1]
ROOT = TOOLS_DIR.parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib import fast_yaml  # noqa: E402


def _frontmatter(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    return text[4:end] if end > 0 else None


class FastYamlIsTheSameParser(unittest.TestCase):
    def test_it_agrees_with_pyyaml_on_the_whole_live_corpus(self) -> None:
        """The equivalence claim, measured against the real vault, not a fixture.

        4,717 frontmatter blocks agreed exactly when this was written. Kept as a
        test rather than a one-off measurement so it is re-answered against
        tomorrow's corpus: a parser swap is only as safe as the last document
        anyone actually fed through both sides.
        """
        checked = 0
        for directory in ("files", "capsules", "agents", "playbooks", "skills"):
            source = ROOT / "vault" / directory
            if not source.is_dir():
                continue
            for path in sorted(source.glob("*.md")):
                block = _frontmatter(path.read_text(errors="ignore"))
                if block is None:
                    continue
                checked += 1
                try:
                    expected = yaml.load(block, Loader=yaml.SafeLoader)
                    expected_error = None
                except Exception as exc:  # noqa: BLE001 - the comparison IS the point
                    expected, expected_error = None, type(exc).__name__
                try:
                    actual = fast_yaml.safe_load(block)
                    actual_error = None
                except Exception as exc:  # noqa: BLE001
                    actual, actual_error = None, type(exc).__name__
                self.assertEqual(
                    expected_error,
                    actual_error,
                    f"{path}: loaders disagree on whether this document parses",
                )
                self.assertEqual(expected, actual, f"{path}: parsed values differ")

        # Control: without this the test above passes on an empty corpus, which
        # is the failure mode it exists to rule out.
        self.assertGreater(
            checked, 1000, "the live corpus was not found — this proved nothing"
        )

    def test_the_shapes_that_actually_bite_frontmatter(self) -> None:
        """Named edge cases, so a corpus that loses one still covers it."""
        cases = [
            "uid: 00123456\n",                      # all-digit scalar -> int
            "title: 'it''s quoted'\n",              # doubled single quote
            "title: \"a — dash\"\n",                # non-ascii
            "n: 1\nlist:\n  - a\n  - b\n",          # block sequence
            "inline: [a, b]\n",                     # flow sequence
            "block: |\n  line one\n  line two\n",   # literal block scalar
            "folded: >\n  one\n  two\n",            # folded block scalar
            "empty:\n",                             # null value
            "nested:\n  a:\n    b: 1\n",            # nested mapping
            "yes_like: yes\nno_like: no\n",         # YAML 1.1 booleans
            "when: 2026-08-09\n",                   # date
        ]
        for text in cases:
            with self.subTest(document=text[:24]):
                self.assertEqual(
                    yaml.safe_load(text), fast_yaml.safe_load(text)
                )

    def test_it_is_still_a_SAFE_loader(self) -> None:
        """C or not, no Python object construction may be reachable."""
        with self.assertRaises(yaml.YAMLError):
            fast_yaml.safe_load("!!python/object/apply:os.system ['echo unsafe']\n")


class TheParseMemoIsTransparent(unittest.TestCase):
    """Repeat parses are memoized. That must change speed and nothing else.

    MEASURED 2026-08-09: one `tropo-validate` run parsed 108,000+ documents of
    which ~91% were byte-identical repeats — eight validator modules each carried
    a private frontmatter parser and re-read the same files. Routing them through
    one memoized helper took the validator from 176.7s to 40.4s with byte-identical
    findings.

    Memoizing a PURE parse is deliberately a different lever from the incremental
    validation brief (5d192c3c). Skipping requires classifying every check as
    per-entry or relational and the brief is explicit that getting it wrong
    reproduces the instrument-blindness it exists to kill. Nothing is skipped
    here: every check still runs against every file.
    """

    def test_a_repeat_parse_returns_an_equal_result(self) -> None:
        doc = "uid: 'abc12345'\ntitle: 'a doc'\ntags:\n  - one\n  - two\n"
        first = fast_yaml.safe_load(doc)
        second = fast_yaml.safe_load(doc)
        self.assertEqual(first, second)
        self.assertEqual(first, yaml.safe_load(doc))

    def test_callers_cannot_poison_each_other(self) -> None:
        """The deep copy IS the safety argument, not an optimisation to remove.

        Parsed frontmatter is a mutable dict and ~30 checks mutate what they are
        handed. `index_surfaces._load_surface_meta` hands back a shared reference
        and carries a comment PROVING no caller mutates it — a proof that expires
        the next time someone adds a caller. This does not need that proof.
        """
        doc = "uid: 'abc12345'\nnested:\n  key: original\n"
        first = fast_yaml.safe_load(doc)
        first["uid"] = "MUTATED"
        first["nested"]["key"] = "MUTATED"
        second = fast_yaml.safe_load(doc)
        self.assertEqual(second["uid"], "abc12345")
        self.assertEqual(second["nested"]["key"], "original", "nested state leaked")
        self.assertIsNot(first, second)

    def test_a_failing_document_raises_every_time(self) -> None:
        """A refusal must never be memoized — it has to refuse on every call."""
        bad = "uid: 'x'\n  bad: [indent\n"
        for attempt in range(3):
            with self.subTest(attempt=attempt):
                with self.assertRaises(yaml.YAMLError):
                    fast_yaml.safe_load(bad)

    def test_one_memo_per_process_however_it_is_imported(self) -> None:
        """Two `lib` packages exist, so this module can load twice.

        The memo is anchored to the `yaml` module rather than to this one,
        because `yaml` is imported once per process by definition. The first
        attempt anchored it here and produced two half-empty caches — both
        reported one entry after being handed the same document.
        """
        kernel_pointer = ROOT / ".tropo" / "scripts" / "lib" / "fast_yaml.py"
        if not kernel_pointer.is_file():
            self.skipTest("kernel-tree pointer not present")
        spec = importlib.util.spec_from_file_location(
            "fast_yaml_second_copy", kernel_pointer
        )
        assert spec and spec.loader
        other = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(other)
        self.assertIs(other._existing._PARSE_MEMO, fast_yaml._PARSE_MEMO)

    def test_it_is_transparent_across_a_real_corpus_sample(self) -> None:
        """Same answers as an unmemoized parse, on real files, twice each."""
        checked = 0
        for path in sorted((ROOT / "vault" / "files").glob("*.md"))[:400]:
            block = _frontmatter(path.read_text(errors="ignore"))
            if block is None:
                continue
            checked += 1
            expected = yaml.load(block, Loader=yaml.SafeLoader)
            self.assertEqual(fast_yaml.safe_load(block), expected, str(path))
            self.assertEqual(fast_yaml.safe_load(block), expected, f"{path} (memo hit)")
        self.assertGreater(checked, 100, "no corpus read — this proved nothing")


class ACustomLoaderMustNotBeRoutedThroughHere(unittest.TestCase):
    def test_pruning_contract_keeps_its_duplicate_key_detector(self) -> None:
        """Deliberately NOT converted, despite being 6,652 parses per run.

        `pruning_contract` parses with its own `_UniqueKeyLoader`, which REFUSES
        duplicate mapping keys. `fast_yaml` is a plain safe loader and would
        silently accept them, so routing it here would trade a real guard for
        speed — the same bargain as skipping relational checks to look fast.
        """
        module = ROOT / "vault" / "tools" / "lib" / "pruning_contract.py"
        source = module.read_text(encoding="utf-8")
        self.assertIn("_UniqueKeyLoader", source)
        self.assertNotIn("fast_yaml", source)


class TheFallbackKeepsABoxWithoutLibyamlWorking(unittest.TestCase):
    def test_this_machine_reports_which_scanner_it_got(self) -> None:
        self.assertIn(fast_yaml.loader_name(), ("libyaml (C)", "pure-Python"))
        self.assertEqual(
            fast_yaml.USING_C_LOADER, fast_yaml.Loader is not yaml.SafeLoader
        )

    def test_the_module_imports_and_parses_with_no_CSafeLoader(self) -> None:
        """Simulate the box PyYAML was built without libyaml on.

        Re-imports the module with `from yaml import CSafeLoader` forced to
        raise, then asserts it still loaded, fell back, said so, and parses.
        Without this the fallback branch is a comment: it cannot be reached on a
        machine that has the C loader, which is every machine we develop on —
        and therefore exactly the branch that would ship broken.
        """
        real_import = builtins.__import__

        def refuse_c_loader(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "yaml" and fromlist and "CSafeLoader" in fromlist:
                raise ImportError("simulated: PyYAML built without libyaml")
            return real_import(name, globals, locals, fromlist, level)

        spec = importlib.util.spec_from_file_location(
            "fast_yaml_no_libyaml", TOOLS_DIR / "lib" / "fast_yaml.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        builtins.__import__ = refuse_c_loader
        try:
            spec.loader.exec_module(module)
        finally:
            builtins.__import__ = real_import

        self.assertFalse(module.USING_C_LOADER)
        self.assertIs(module.Loader, yaml.SafeLoader)
        self.assertEqual(module.loader_name(), "pure-Python")
        parsed = module.safe_load("uid: 00123456\ntitle: 'it''s fine'\n")
        # 0o123456 == 42798, not 123456: a leading zero makes this YAML 1.1
        # OCTAL. Surprising enough that I asserted the decimal first and this
        # test caught me. Both loaders agree on it, which is the point — the
        # fallback must reproduce PyYAML's quirks, not a tidier parser.
        self.assertEqual(parsed, {"uid": 0o123456, "title": "it's fine"})
        self.assertEqual(parsed, yaml.safe_load("uid: 00123456\ntitle: 'it''s fine'\n"))

    def test_mutation_a_hard_import_would_fail_that_box(self) -> None:
        """Teeth: prove the guard is what makes the fallback work.

        Runs the same simulated no-libyaml import against an UNGUARDED copy of
        the module and asserts it raises. If this ever stops raising, the
        try/except above has stopped being what protects the box.
        """
        source = (TOOLS_DIR / "lib" / "fast_yaml.py").read_text()
        self.assertIn("except ImportError:", source)
        unguarded = "from yaml import CSafeLoader as _Loader\nUSING_C_LOADER = True\n"
        real_import = builtins.__import__

        def refuse_c_loader(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "yaml" and fromlist and "CSafeLoader" in fromlist:
                raise ImportError("simulated: PyYAML built without libyaml")
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = refuse_c_loader
        try:
            with self.assertRaises(ImportError):
                exec(compile(unguarded, "unguarded_fast_yaml", "exec"), {})
        finally:
            builtins.__import__ = real_import


if __name__ == "__main__":
    unittest.main(verbosity=2)
