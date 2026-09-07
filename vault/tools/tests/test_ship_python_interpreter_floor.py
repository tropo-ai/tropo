#!/usr/bin/env python3
"""Ship-scoped Python must run on the oldest interpreter a Studio presents.

The field failure: `tropo-import-walker.py` gained `mount_uid: str | None` with
no postponed annotations, silently raising its floor to 3.10. Every machine in
this build runs 3.12, so the defect surfaced only when the tool ran on Mike's
Mac during the gate-1 manual walk — stock macOS python3 is 3.9.6 and the walk
stopped dead.

The mutation that matters is therefore the real one: remove the future import
that fixed the walker and require the gate to go red.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    # exec_module below loads tropo-validate.py in-process; it inherits THIS
    # sys.path and does `from lib.work_item_types import ...` at top level
    # since 2026-08-31. pytest's package-root walk masked this; the standalone
    # runner (the loop's instrument) did not. (suite-health 2026-09-03)
    sys.path.insert(0, str(TOOLS))

SPEC = importlib.util.spec_from_file_location(
    "tropo_validate_for_python_floor", TOOLS / "tropo-validate.py"
)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)

WALKER = Path("vault/tools/tropo-import-walker.py")

SHIP_FRONTMATTER = '''#!/usr/bin/env python3
"""
---
uid: {uid}
type: tool
status: active
extraction_scope: ship
{extra}---
"""
{future}
from pathlib import Path


def probe(value{annotation}):
    return value
'''


class ShipPythonFloorTests(unittest.TestCase):
    def scratch(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="ship-python-floor-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "vault" / "tools").mkdir(parents=True)
        return tmp

    def plant(self, root: Path, name: str, *, annotation: str, future: bool,
              extra: str = "") -> Path:
        path = root / "vault" / "tools" / name
        path.write_text(
            SHIP_FRONTMATTER.format(
                uid=name.replace("-", "")[:8].ljust(8, "0"),
                extra=extra,
                future="from __future__ import annotations\n" if future else "",
                annotation=annotation,
            ),
            encoding="utf-8",
        )
        return path

    def test_the_live_tree_is_clean(self):
        findings, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(ROOT)
        self.assertGreater(checked, 0, "no ship-scoped tools were checked")
        self.assertEqual(defects, 0, f"ship tools would fail on py3.9: {findings}")

    def test_pep604_annotation_without_postponement_is_a_defect(self):
        root = self.scratch()
        self.plant(root, "tropo-probe.py", annotation=": str | None = None", future=False)

        findings, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

        self.assertEqual(checked, 1)
        self.assertEqual(defects, 1)
        self.assertIn("PEP-604", findings[0])
        self.assertIn("Python 3.9", findings[0])

    def test_postponed_annotations_clear_it(self):
        root = self.scratch()
        self.plant(root, "tropo-probe.py", annotation=": str | None = None", future=True)
        _, _, defects = VALIDATOR.check_ship_python_interpreter_floor(root)
        self.assertEqual(defects, 0)

    def test_an_explicitly_declared_higher_floor_clears_it(self):
        """A tool may require 3.10 — it just may not do so silently."""
        root = self.scratch()
        self.plant(
            root,
            "tropo-probe.py",
            annotation=": str | None = None",
            future=False,
            extra="python_floor: '3.11'\n",
        )
        _, _, defects = VALIDATOR.check_ship_python_interpreter_floor(root)
        self.assertEqual(defects, 0)

    def test_non_ship_tools_are_out_of_scope(self):
        root = self.scratch()
        path = self.plant(root, "tropo-probe.py", annotation=": str | None = None", future=False)
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "extraction_scope: ship", "extraction_scope: argo-private"
            ),
            encoding="utf-8",
        )
        _, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)
        self.assertEqual((checked, defects), (0, 0))

    def test_removing_the_walker_future_import_turns_the_gate_red(self):
        """The real mutation: undo metis-g107's fix and require a defect.

        Runs against a copy. The live walker is never modified.
        """
        root = self.scratch()
        shutil.copy2(ROOT / WALKER, root / WALKER)

        _, _, before = VALIDATOR.check_ship_python_interpreter_floor(root)
        self.assertEqual(before, 0, "the copied walker did not start clean")

        target = root / WALKER
        text = target.read_text(encoding="utf-8")
        mutated = text.replace("from __future__ import annotations", "", 1)
        self.assertNotEqual(mutated, text, "the walker no longer carries the fix")
        target.write_text(mutated, encoding="utf-8")

        findings, _, after = VALIDATOR.check_ship_python_interpreter_floor(root)

        self.assertGreater(
            after,
            0,
            "removing the postponed-annotations fix did not fail the gate — the "
            "exact defect that broke the gate-1 walk would ship again",
        )
        self.assertTrue(any("tropo-import-walker.py" in f for f in findings))


SHAPES = {
    # The shape the gate was written against.
    "newline": '#!/usr/bin/env python3\n"""\n---\n{fm}---\n"""\n',
    # The shape it could not see: fence shares the docstring's opening line.
    "same_line": '#!/usr/bin/env python3\n"""---\n{fm}---\n"""\n',
    # Same, with no shebang, so the docstring starts at byte zero.
    "byte_zero": '"""---\n{fm}---\n"""\n',
    # Triple-single quotes are legal and appear in the tree.
    "triple_single": "#!/usr/bin/env python3\n'''---\n{fm}---\n'''\n",
}

FRONTMATTER = "uid: {uid}\ntype: tool\nstatus: active\nextraction_scope: ship\n"

# A module with an ordinary prose docstring that renders frontmatter for some
# OTHER file further down. `tropo-lock-release-plan.py` is really shaped like
# this. A file-wide fence regex claims it; a docstring-anchored parser does not.
PROSE_DECOY = '''#!/usr/bin/env python3
"""A tool that writes governed headers for other files.

It has no frontmatter of its own.
"""

TEMPLATE = """---
uid: aaaaaaaa
type: tool
status: active
extraction_scope: ship
---
"""


def render(value: str | None = None):
    return TEMPLATE
'''


def _parser():
    """THE parser object the validator actually uses.

    Deliberately not `import lib.python_tool_frontmatter`. That import
    succeeds here only when something has already put vault/tools on sys.path,
    and reaching for it in the test would prove a module the production code
    might never load. Taking the validator's own attribute means a regression
    in how the validator loads its parser fails these tests too.
    """
    return VALIDATOR.python_tool_frontmatter


class ParserIsLoadedTheWayTheValidatorLoadsItTests(unittest.TestCase):
    """The gate must run under a bare `python3 -m unittest`, not only here.

    The first wiring of this parser used `from lib.python_tool_frontmatter
    import ...` inside the check. It passed locally because other functions in
    the validator insert vault/tools into sys.path, and one of them had run
    first. Under a clean invocation that insert has not happened, `lib`
    resolves to .tropo/scripts/lib alone, and the check raised instead of
    running — 18 errors on A150's box against 16 green on mine.
    """

    def test_the_validator_owns_a_path_loaded_parser(self):
        self.assertTrue(
            hasattr(VALIDATOR, "python_tool_frontmatter"),
            "the validator no longer holds its parser as a module attribute; a "
            "function-local `from lib.` import is the shape that broke",
        )
        self.assertTrue(
            hasattr(VALIDATOR.python_tool_frontmatter, "iter_shipped_tools")
        )

    def test_the_check_runs_without_vault_tools_on_sys_path(self):
        """The exact condition that failed, reproduced rather than described."""
        import importlib.util

        tools = str(TOOLS)
        removed = [p for p in sys.path if p == tools]
        for path in removed:
            sys.path.remove(path)
        stashed = {
            name: sys.modules.pop(name)
            for name in [n for n in sys.modules if n == "lib" or n.startswith("lib.")]
        }
        try:
            spec = importlib.util.spec_from_file_location(
                "tropo_validate_clean_import_probe", TOOLS / "tropo-validate.py"
            )
            probe = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = probe
            spec.loader.exec_module(probe)

            findings, checked, defects = probe.check_ship_python_interpreter_floor(ROOT)
        finally:
            sys.modules.update(stashed)
            for path in removed:
                if path not in sys.path:
                    sys.path.insert(0, path)

        self.assertGreater(
            checked,
            0,
            "the floor check examined nothing when vault/tools was absent from "
            "sys.path — the import defect is back",
        )
        self.assertEqual(defects, 0, findings)


class ShipFloorCoverageTests(unittest.TestCase):
    """The corpus the gate examines must equal the corpus that ships.

    Two prior wirings of this gate were green while blind — one examined zero
    tools, one silently skipped three. Neither could have been caught by asking
    whether the gate passed. Both are caught by asking what it opened.
    """

    def independent_expectation(self) -> set:
        """Ship-scoped tools, derived WITHOUT the parser under test.

        A plain textual scan for the declaration line over raw bytes. It shares
        no code with the AST docstring anchoring, so agreement between the two
        is evidence rather than tautology.
        """
        import re

        found = set()
        for path in sorted(TOOLS.glob("*.py")):
            text = path.read_text(errors="replace")
            if re.search(r"^extraction_scope:[ \t]*ship[ \t]*$", text, re.M):
                found.add(path.name)
        return found

    def test_independent_expectation_equals_the_checked_corpus(self):
        expected = self.independent_expectation()
        actual = {p.name for p in _parser().shipped_tool_paths(TOOLS)}

        self.assertEqual(
            actual,
            expected,
            "the parser's corpus and an independent scan disagree; one of them "
            "is wrong and the gate's verdict does not cover what ships",
        )
        _, checked, _ = VALIDATOR.check_ship_python_interpreter_floor(ROOT)
        self.assertEqual(
            checked,
            len(_parser().shipped_census(TOOLS)),
            "the gate examined a different number of files than the census. The "
            "census is tools PLUS their helper chain; the independent scan above "
            "covers the tool half, and this line covers the whole",
        )
        self.assertGreater(
            checked,
            len(expected),
            "the census is no larger than the tool corpus, so the helper chain "
            "is not being examined",
        )

    def test_the_three_same_line_tools_are_in_the_corpus(self):
        """Named because they were invisible, not because they were failing."""
        corpus = {p.name for p in _parser().shipped_tool_paths(TOOLS)}
        for name in (
            "tropo-distiller-model-edge.py",
            "tropo-distiller-metered-canary.py",
            "tropo-release-validation-gate.py",
        ):
            self.assertIn(
                name,
                corpus,
                f"{name} declares extraction_scope: ship and opens its "
                f"frontmatter on the docstring line; the retired regex skipped it",
            )

    def test_a_discovered_tool_that_is_never_examined_fails(self):
        """Coverage is a defect class, not a statistic."""
        mod = _parser()
        ghost = TOOLS / "tool-that-does-not-exist.py"

        with mock.patch.object(
            mod, "iter_shipped_tools", lambda _dir: iter([(ghost, "extraction_scope: ship")])
        ):
            findings, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(ROOT)

        self.assertEqual(checked, 0)
        self.assertGreater(defects, 0)
        self.assertTrue(
            any("coverage" in f for f in findings),
            f"a discovered-but-unexamined tool did not raise coverage: {findings}",
        )


class FenceShapeTests(unittest.TestCase):
    def scratch(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="ship-fence-shape-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "vault" / "tools").mkdir(parents=True)
        return tmp

    def test_every_observed_fence_shape_is_discovered_and_checked(self):
        for shape, template in SHAPES.items():
            with self.subTest(shape=shape):
                root = self.scratch()
                body = template.format(fm=FRONTMATTER.format(uid="deadbeef"))
                # PEP-604 with no postponement: a defect the gate must report,
                # which it can only do if the shape parsed at all.
                body += "\n\ndef probe(value: str | None = None):\n    return value\n"
                (root / "vault" / "tools" / "tropo-probe.py").write_text(body, encoding="utf-8")

                findings, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

                self.assertEqual(checked, 1, f"{shape} was not discovered")
                self.assertEqual(defects, 1, f"{shape} parsed but was not checked: {findings}")

    def test_a_rendered_template_is_not_frontmatter(self):
        """The decoy half of the same defect: precision, not just recall."""
        root = self.scratch()
        (root / "vault" / "tools" / "tropo-renderer.py").write_text(PROSE_DECOY, encoding="utf-8")

        _, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

        self.assertEqual(
            (checked, defects),
            (0, 0),
            "a fence inside a template string was mistaken for the module's own "
            "frontmatter, so a tool that ships nothing was judged as shipping",
        )

    def test_a_tool_that_does_not_parse_is_still_discovered(self):
        """A broken shipped tool must be reported, never silently dropped."""
        root = self.scratch()
        body = SHAPES["same_line"].format(fm=FRONTMATTER.format(uid="deadbeef"))
        body += "\n\ndef broken(:\n    pass\n"
        (root / "vault" / "tools" / "tropo-broken.py").write_text(body, encoding="utf-8")

        findings, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

        self.assertEqual(checked, 1)
        self.assertEqual(defects, 1)
        self.assertTrue(any("does not parse" in f for f in findings), findings)


class AnnotationPositionTests(unittest.TestCase):
    """Every position where a PEP-604 union can raise the floor."""

    POSITIONS = {
        "positional_arg": "def probe(value: str | None):\n    return value\n",
        "keyword_only_arg": "def probe(*, value: str | None = None):\n    return value\n",
        "positional_only_arg": "def probe(value: str | None, /):\n    return value\n",
        "return_annotation": "def probe(value) -> str | None:\n    return value\n",
        "module_variable": "CACHE: dict | None = None\n",
        "async_function": "async def probe(value: int | None):\n    return value\n",
    }

    def scratch(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="ship-annotation-position-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "vault" / "tools").mkdir(parents=True)
        return tmp

    def test_each_annotation_position_is_caught(self):
        for name, snippet in self.POSITIONS.items():
            with self.subTest(position=name):
                root = self.scratch()
                body = SHAPES["same_line"].format(fm=FRONTMATTER.format(uid="deadbeef"))
                (root / "vault" / "tools" / "tropo-probe.py").write_text(
                    body + "\n\n" + snippet, encoding="utf-8"
                )

                findings, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

                self.assertEqual(checked, 1)
                self.assertEqual(defects, 1, f"{name} was not caught: {findings}")

    def test_each_position_clears_with_postponed_annotations(self):
        for name, snippet in self.POSITIONS.items():
            with self.subTest(position=name):
                root = self.scratch()
                body = SHAPES["same_line"].format(fm=FRONTMATTER.format(uid="deadbeef"))
                body += "\nfrom __future__ import annotations\n\n" + snippet
                (root / "vault" / "tools" / "tropo-probe.py").write_text(body, encoding="utf-8")

                _, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

                self.assertEqual((checked, defects), (1, 0), f"{name} false-positived")


class HelperChainCensusTests(unittest.TestCase):
    """A shipped tool's helpers ship with it.

    A150's ruling, 2026-08-16: the release orchestrator, preflight and
    lock-release-plan are product surfaces, and their Python helper chain is
    covered by the floor census. The reason is mechanical — a 3.10-only
    annotation in `lib/x.py` breaks a 3.9 Studio at import just as surely as
    one in the tool, so a census of tools alone reports a floor the shipped
    code does not meet.
    """

    def scratch(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="ship-helper-chain-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "vault" / "tools" / "lib").mkdir(parents=True)
        return tmp

    HEADER = '#!/usr/bin/env python3\n"""---\nuid: deadbeef\ntype: tool\nstatus: active\nextraction_scope: ship\n---\n"""\n'

    def test_the_live_census_covers_tools_and_helpers(self):
        mod = _parser()
        tools = mod.shipped_tool_paths(TOOLS)
        helpers = mod.shipped_helper_chain(TOOLS)
        census = mod.shipped_census(TOOLS)

        self.assertGreater(len(helpers), 0, "no helper is reachable from any ship tool")
        self.assertEqual(set(census), set(tools) | set(helpers))
        for helper in helpers:
            self.assertEqual(helper.parent.name, "lib")

    def test_the_ruled_product_surfaces_are_in_the_census(self):
        names = {p.name for p in _parser().shipped_census(TOOLS)}
        for tool in (
            "tropo-release-preflight.py",
            "tropo-verify-release-live.py",
            "tropo-lock-release-plan.py",
        ):
            self.assertIn(tool, names, f"{tool} was ruled a product surface")

    def test_a_helper_with_a_bare_union_fails_the_gate(self):
        root = self.scratch()
        (root / "vault" / "tools" / "tropo-probe.py").write_text(
            self.HEADER + "\nfrom lib.helper import work\n", encoding="utf-8"
        )
        (root / "vault" / "tools" / "lib" / "helper.py").write_text(
            "def work(value: str | None = None):\n    return value\n", encoding="utf-8"
        )

        findings, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

        self.assertEqual(checked, 2, "the helper was not censused with its tool")
        self.assertEqual(defects, 1)
        self.assertTrue(any("helper.py" in f for f in findings), findings)

    def test_a_path_loaded_helper_is_reached_too(self):
        """The validator's own mechanism, not just ordinary imports."""
        root = self.scratch()
        (root / "vault" / "tools" / "tropo-probe.py").write_text(
            self.HEADER
            + '\nimport importlib.util\n'
            + 'spec = importlib.util.spec_from_file_location("h", "lib/helper.py")\n',
            encoding="utf-8",
        )
        (root / "vault" / "tools" / "lib" / "helper.py").write_text(
            "def work(value: str | None = None):\n    return value\n", encoding="utf-8"
        )

        _, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

        self.assertEqual(checked, 2, "a path-loaded helper escaped the census")
        self.assertEqual(defects, 1)

    def test_the_chain_is_transitive(self):
        root = self.scratch()
        (root / "vault" / "tools" / "tropo-probe.py").write_text(
            self.HEADER + "\nfrom lib.first import a\n", encoding="utf-8"
        )
        (root / "vault" / "tools" / "lib" / "first.py").write_text(
            "from lib.second import b\n\n\ndef a():\n    return b()\n", encoding="utf-8"
        )
        (root / "vault" / "tools" / "lib" / "second.py").write_text(
            "def b(value: str | None = None):\n    return value\n", encoding="utf-8"
        )

        _, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

        self.assertEqual(checked, 3, "the chain stopped at the first hop")
        self.assertEqual(defects, 1)

    def test_a_helper_no_ship_tool_imports_is_not_censused(self):
        """Scope stays bounded: unreferenced helpers are not shipped code."""
        root = self.scratch()
        (root / "vault" / "tools" / "tropo-probe.py").write_text(
            self.HEADER + "\nfrom __future__ import annotations\n", encoding="utf-8"
        )
        (root / "vault" / "tools" / "lib" / "orphan.py").write_text(
            "def work(value: str | None = None):\n    return value\n", encoding="utf-8"
        )

        _, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

        self.assertEqual((checked, defects), (1, 0))


class RetiredCheckerTests(unittest.TestCase):
    def test_the_duplicate_check_is_gone(self):
        """Two implementations of one rule is how the wrong one stays wired."""
        self.assertFalse(
            hasattr(VALIDATOR, "check_shipped_python_floor"),
            "the retired duplicate floor check is back; only one may exist",
        )

    def test_restoring_the_retired_discovery_regex_turns_the_gate_red(self):
        """The named mutation: put the old line-anchored regex back.

        It does not fail loudly — it quietly returns a smaller corpus. The
        independent expectation is what converts that silence into a red test.
        """
        import re

        mod = _parser()
        retired = re.compile(r"^---\n(.*?)\n---\s*$", re.S | re.M)

        def retired_frontmatter(text: str):
            match = retired.search(text)
            return match.group(1) if match else None

        expected = ShipFloorCoverageTests().independent_expectation()

        with mock.patch.object(mod, "tool_frontmatter", retired_frontmatter):
            mutated = {p.name for p in mod.shipped_tool_paths(TOOLS)}

        self.assertNotEqual(
            mutated,
            expected,
            "restoring the retired regex did not change the corpus — this test "
            "is not measuring what it claims to measure",
        )
        lost = expected - mutated
        self.assertTrue(
            {
                "tropo-distiller-model-edge.py",
                "tropo-distiller-metered-canary.py",
                "tropo-release-validation-gate.py",
            }.issubset(lost),
            "the retired regex did not lose the three same-line headers it is "
            f"known to miss; it lost {sorted(lost)}",
        )
        for name in lost:
            with self.subTest(lost=name):
                self.assertRegex(
                    (TOOLS / name).read_text(errors="replace"),
                    r"(\"\"\"|''')[ \t]*---",
                    "the retired regex lost a tool for some reason OTHER than a "
                    "same-line fence, which is not the defect under test",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
