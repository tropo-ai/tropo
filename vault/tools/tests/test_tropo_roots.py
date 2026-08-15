"""Executable semantics and source guards for the release-tool root vocabulary."""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


STUDIO = Path(__file__).resolve().parents[3]
TOOLS = STUDIO / "vault" / "tools"
ROOTS_SOURCE = TOOLS / "lib" / "tropo_roots.py"
CONSUMERS = (
    "tropo-build-release.py",
    "tropo-publish-release.py",
    "tropo-check-publish-state.py",
    "tropo-publish-scope-gate.py",
    "tropo-validate-release-manifest.py",
    "tropo-generate-update-manifest.py",
)
LOCAL_ROOT_NAMES = {
    "DEV_HOME",
    "PLATFORM_ROOT",
    "RELEASES_DIR",
    "STAGED_CLONE_DIR",
    "STUDIOS_HOME",
    "STUDIO_ROOT",
    "VAULT_DIR",
    "VAULT_ROOT",
}


def _load_roots(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_semantics(paths, expected_studio: Path) -> None:
    names = (
        "STUDIO_ROOT",
        "VAULT_DIR",
        "STUDIOS_HOME",
        "DEV_HOME",
        "RELEASES_DIR",
        "STAGED_CLONE_DIR",
    )
    for name in names:
        value = getattr(paths, name)
        if not isinstance(value, Path):
            raise AssertionError(f"{name} is not a Path: {value!r}")

    expected = {
        "STUDIO_ROOT": expected_studio,
        "VAULT_DIR": paths.STUDIO_ROOT / "vault",
        "STUDIOS_HOME": paths.STUDIO_ROOT.parent,
        "DEV_HOME": paths.STUDIOS_HOME.parent,
        "RELEASES_DIR": paths.DEV_HOME / "tropo-releases",
        "STAGED_CLONE_DIR": paths.DEV_HOME / "tropo-staged-clone",
    }
    for name, expected_value in expected.items():
        actual = getattr(paths, name)
        if actual != expected_value:
            raise AssertionError(
                f"{name} has {actual!r}; expected {expected_value!r}"
            )


def _target_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return {
            name
            for element in target.elts
            for name in _target_names(element)
        }
    return set()


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {
        name
        for target in targets
        for name in _target_names(target)
    }


class TropoRootsSemanticsTests(unittest.TestCase):
    def test_live_studio_paths_are_path_typed_and_exact(self) -> None:
        roots = _load_roots(ROOTS_SOURCE, "_tropo_roots_live_test")
        _assert_semantics(roots, STUDIO)

    def test_nested_fixture_uses_nearest_marked_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outer = Path(temporary) / "outer-studio"
            inner = outer / "work" / "inner-studio"
            for studio in (outer, inner):
                (studio / ".tropo").mkdir(parents=True)
                (studio / "vault").mkdir()
            fixture_source = inner / "vault" / "tools" / "lib" / "tropo_roots.py"
            fixture_source.parent.mkdir(parents=True)
            shutil.copy2(ROOTS_SOURCE, fixture_source)
            nested = fixture_source.parent / "nested" / "deeper"
            nested.mkdir(parents=True)

            roots = _load_roots(fixture_source, "_tropo_roots_nested_test")
            _assert_semantics(roots, inner.resolve())
            self.assertEqual(
                roots.resolve_studio_root(start=nested),
                inner.resolve(),
            )
            self.assertEqual(
                roots.resolve_studio_root(override=inner),
                inner.resolve(),
            )

    def test_resolution_is_cwd_independent_and_never_falls_back_to_cwd(self) -> None:
        roots = _load_roots(ROOTS_SOURCE, "_tropo_roots_cwd_test")
        with tempfile.TemporaryDirectory() as temporary:
            unrelated = Path(temporary) / "unmarked" / "nested"
            unrelated.mkdir(parents=True)
            prior = Path.cwd()
            try:
                os.chdir(unrelated)
                reloaded = _load_roots(ROOTS_SOURCE, "_tropo_roots_cwd_reload")
                _assert_semantics(reloaded, STUDIO)
                with self.assertRaisesRegex(
                    roots.TropoRootError, "could not find a Studio ancestor"
                ):
                    roots.resolve_studio_root(start=unrelated)
            finally:
                os.chdir(prior)

    def test_missing_markers_and_invalid_override_refuse(self) -> None:
        roots = _load_roots(ROOTS_SOURCE, "_tropo_roots_refusal_test")
        with tempfile.TemporaryDirectory() as temporary:
            start = Path(temporary) / "no-markers"
            start.mkdir()
            with self.assertRaisesRegex(
                roots.TropoRootError, str(start.resolve())
            ):
                roots.resolve_studio_root(start=start)
            with self.assertRaisesRegex(
                roots.TropoRootError, "explicit Studio root override"
            ):
                roots.resolve_studio_root(override=start)
            with self.assertRaises(ValueError):
                roots.resolve_studio_root(start=start, override=start)

    def test_semantic_oracle_rejects_a_meaning_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            studio = Path(temporary) / "studio"
            (studio / ".tropo").mkdir(parents=True)
            mutation_source = (
                studio / "vault" / "tools" / "lib" / "tropo_roots.py"
            )
            mutation_source.parent.mkdir(parents=True)
            source = ROOTS_SOURCE.read_text(encoding="utf-8")
            original = (
                'VAULT_DIR = STUDIO_ROOT / "vault"\n'
                "STUDIOS_HOME = STUDIO_ROOT.parent"
            )
            swapped = (
                "VAULT_DIR = STUDIO_ROOT.parent\n"
                'STUDIOS_HOME = STUDIO_ROOT / "vault"'
            )
            self.assertIn(original, source)
            mutation_source.write_text(
                source.replace(original, swapped, 1),
                encoding="utf-8",
            )

            roots = _load_roots(
                mutation_source, "_tropo_roots_meaning_swap_test"
            )
            with self.assertRaises(AssertionError):
                _assert_semantics(roots, studio.resolve())

    def test_spec_loading_survives_preimported_scripts_lib_from_other_cwd(self) -> None:
        code = textwrap.dedent(
            """
            import importlib.util
            import sys
            from pathlib import Path

            studio = Path(sys.argv[1])
            tools = studio / "vault" / "tools"
            scripts = studio / ".tropo" / "scripts"
            sys.path.insert(0, str(scripts))
            import lib
            assert (scripts / "lib").resolve() in {
                Path(entry).resolve() for entry in lib.__path__
            }

            consumers = (
                "tropo-build-release.py",
                "tropo-publish-release.py",
                "tropo-check-publish-state.py",
                "tropo-publish-scope-gate.py",
                "tropo-validate-release-manifest.py",
                "tropo-generate-update-manifest.py",
            )
            for index, filename in enumerate(consumers):
                name = f"_root_consumer_{index}"
                spec = importlib.util.spec_from_file_location(name, tools / filename)
                assert spec is not None and spec.loader is not None
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                assert module.tropo_roots.STUDIO_ROOT == studio
            """
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [sys.executable, "-c", code, str(STUDIO)],
                cwd=temporary,
                capture_output=True,
                text=True,
                timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ReleaseFamilySourceGuardTests(unittest.TestCase):
    def test_every_named_consumer_uses_only_the_shared_root_seam(self) -> None:
        for filename in CONSUMERS:
            path = TOOLS / filename
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=filename)
            with self.subTest(consumer=filename):
                self.assertIn('"tropo_roots.py"', source)
                self.assertTrue(
                    any(
                        isinstance(node, ast.Attribute)
                        and isinstance(node.value, ast.Name)
                        and node.value.id == "tropo_roots"
                        and node.attr in {
                            "RELEASES_DIR",
                            "STAGED_CLONE_DIR",
                            "STUDIO_ROOT",
                            "VAULT_DIR",
                        }
                        for node in ast.walk(tree)
                    ),
                    "consumer never reads a shared semantic root",
                )

                assigned = set()
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Assign, ast.AnnAssign)):
                        assigned.update(_assigned_names(node))
                self.assertEqual(assigned & LOCAL_ROOT_NAMES, set())

                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        module = getattr(node, "module", None) or ""
                        imported = {
                            alias.name
                            for alias in getattr(node, "names", ())
                        }
                        self.assertFalse(
                            module == "lib.tropo_roots"
                            or (
                                module == "lib"
                                and "tropo_roots" in imported
                            ),
                            "the roots module must not resolve through package lib",
                        )

                    if isinstance(node, ast.Attribute) and node.attr in {
                        "parent",
                        "parents",
                    }:
                        self.assertFalse(
                            any(
                                isinstance(child, ast.Name)
                                and child.id == "__file__"
                                for child in ast.walk(node)
                            ),
                            "consumer directly walks upward from __file__",
                        )

                    if isinstance(node, ast.Call):
                        function = node.func
                        function_name = (
                            function.attr
                            if isinstance(function, ast.Attribute)
                            else function.id
                            if isinstance(function, ast.Name)
                            else ""
                        )
                        if function_name in {"getcwd", "cwd"}:
                            self.fail("consumer contains a cwd root fallback")
                        if function_name == "dirname":
                            self.assertFalse(
                                any(
                                    isinstance(child, ast.Name)
                                    and child.id == "__file__"
                                    for child in ast.walk(node)
                                ),
                                "consumer contains a dirname chain from __file__",
                            )


if __name__ == "__main__":
    unittest.main()
