#!/usr/bin/env python3
"""No test may assert a COPY of a limit its tool already defines.

talos-t40, 2026-08-09, velocity item 4 of the v1.86 retrospective.

THE CLASS, not an instance. The retrospective costed this at "one ~30-min stall
per stale constant" and named three: the rebuild step-0 timeout (300s against a
25-minute reality), the ratchet's validator timeout (bumped three times), and a
`BASELINE_FAIL_CEILING = 2` frozen at v1.74 that went on being compared against
a real count that had drifted to 504.

They share one shape. A limit lives in a tool; a test states the same number
again; the tool's number moves; the test's copy does not. Nothing reports it,
because both files are individually correct — the defect exists only in the
space between them. metis-g105 bumped a build wrapper 420 -> 1080 the night of
the v1.86 stage and left its test asserting 420, red on the release path the
bump was for. That is the third generation of the same shape.

Fixing instances does not kill a class; the next one is already scheduled.
So this is a detector. It reads every module-level limit constant out of the
tools, then reads every test's assertions, and refuses any test that compares
against a bare literal equal to one of those values. The cure it prints is the
one that ends the shape rather than patching it: read the constant.

DELIBERATELY NARROW. It looks only at limit-shaped NAMED constants
(`*_TIMEOUT_S`, `*_CEILING`, `*_BUDGET`, `*_MAX`, `*_LIMIT`, `*_SECONDS`) and
only at equality assertions. A broad "no duplicated numbers anywhere" check
would flag hundreds of unrelated literals, and a guard that cries wolf is a
guard people learn to skip — which is how the v1.74 ceiling survived for months
in the first place.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
TESTS = TOOLS / "tests"

#: Names that denote a LIMIT — the class of constant that gets bumped.
LIMIT_NAME_RE = re.compile(
    r"(_TIMEOUT(_S|_SECONDS)?|_CEILING|_BUDGET(_SECONDS)?|_MAX|_LIMIT|_SECONDS)$"
)

#: Values too common to attribute. `1`, `2`, `10` appear everywhere for reasons
#: that have nothing to do with the constant that happens to share them, and
#: flagging those is how a guard becomes noise.
MIN_ATTRIBUTABLE_VALUE = 20

#: Known-good exceptions, each with the reason it is not the shape. Empty, and
#: intended to stay that way: an exemption list is a record of everything that
#: ever confused a guard (metis-g105), so if this fills up the guard is wrong.
EXEMPT: dict[tuple[str, int], str] = {}


def _module_limit_constants() -> dict[int, list[str]]:
    """{value: ["TOOL.CONSTANT", ...]} for every limit-shaped module constant."""
    found: dict[int, list[str]] = {}
    for path in sorted(TOOLS.rglob("*.py")):
        if TESTS in path.parents:
            continue
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            value = node.value
            if not isinstance(target, ast.Name) or not isinstance(value, ast.Constant):
                continue
            if not isinstance(value.value, (int, float)) or isinstance(value.value, bool):
                continue
            name = target.id
            if not name.isupper() or not LIMIT_NAME_RE.search(name):
                continue
            if value.value < MIN_ATTRIBUTABLE_VALUE:
                continue
            found.setdefault(int(value.value), []).append(f"{path.name}.{name}")
    return found


def _referenced_tools(path: Path) -> set[str]:
    """Which tool files this test actually loads, by filename in its source.

    Ownership by VALUE alone is not ownership. `assertEqual(len(digest), 64)` is
    a sha256 length that happens to equal `governed_path._UID_MAX`, and flagging
    it would make this guard noise. A test can only strand a constant it is
    actually exercising.
    """
    text = path.read_text(errors="ignore")
    return {m.group(0) for m in re.finditer(r"[A-Za-z0-9_\-]+\.py", text)}


def _names_in(node: ast.AST) -> set[str]:
    return {
        child.attr if isinstance(child, ast.Attribute) else child.id
        for child in ast.walk(node)
        if isinstance(child, (ast.Attribute, ast.Name))
    }


def _literal_copy_assertions(path: Path, constant_names: set[str]):
    """Yield (lineno, value) for assertions that state a bare limit COPY.

    A PIN is allowed and is not the defect. `assertEqual(smoke.TIME_BUDGET_SECONDS,
    120)` names the constant on one side, so the two cannot drift apart: change
    the constant and this fires, which is a ratchet asking someone to justify the
    new number. `test_tropo_smoke` does exactly that, with the measurement in the
    docstring above it, and it should keep doing it.

    The defect is a copy with NO reference to the constant at all — an assertion
    about observed behaviour measured against a number retyped by hand, like
    `assertEqual(run.call_args.kwargs["timeout"], 420)` while the build had moved
    to 1080. Nothing connects the two, so nothing reports when they diverge.
    """
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in ("assertEqual", "assertEquals"):
            continue
        if len(node.args) < 2:
            continue
        mentioned: set[str] = set()
        for arg in node.args[:2]:
            mentioned |= _names_in(arg)
        if mentioned & constant_names:
            continue  # a pin, not a copy
        for arg in node.args[:2]:
            if (
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, (int, float))
                and not isinstance(arg.value, bool)
            ):
                yield node.lineno, int(arg.value)


class NoTestRestatesALimitItsToolAlreadyOwns(unittest.TestCase):
    def test_the_detector_can_see_the_constants_at_all(self) -> None:
        """Control. Without it, an empty scan passes everything silently.

        This is the same failure the guard exists to prevent, one level up: a
        check that stopped checking reports clean.
        """
        constants = _module_limit_constants()
        self.assertGreaterEqual(
            len(constants),
            5,
            "no limit constants found — the scan is broken, not the studio clean",
        )
        flat = {n for names in constants.values() for n in names}
        self.assertIn(
            "tropo-build-release.py.STUDIO_DEBT_RATCHET_TIMEOUT_S",
            flat,
            "the constant introduced by this very class of fix is not being seen",
        )

    def test_no_test_asserts_a_copy_of_a_tool_limit(self) -> None:
        constants = _module_limit_constants()
        constant_names = {
            owner.split(".", 1)[1] for owners in constants.values() for owner in owners
        }
        offenders: list[str] = []
        for test_path in sorted(TESTS.glob("test_*.py")):
            if test_path.name == Path(__file__).name:
                continue
            referenced = _referenced_tools(test_path)
            for lineno, value in _literal_copy_assertions(test_path, constant_names):
                owners = [
                    owner
                    for owner in constants.get(value, [])
                    if owner.split(".", 1)[0] in referenced
                ]
                if not owners:
                    continue
                if (test_path.name, value) in EXEMPT:
                    continue
                offenders.append(
                    f"{test_path.name}:{lineno} asserts the bare literal {value}, "
                    f"which is the value of {' / '.join(owners)}"
                )
        self.assertEqual(
            offenders,
            [],
            "A test is holding a COPY of a limit its tool owns. When the tool's "
            "value moves, this test strands — the exact shape that cost three "
            "stalls before v1.86 and left a build wrapper's test red on the "
            "release path its bump was for.\n"
            "CURE: import the constant and assert against it, so there is one "
            "definition and two readers.\n" + "\n".join(f"  - {o}" for o in offenders),
        )

    def test_mutation_it_catches_the_bug_that_motivated_it(self) -> None:
        """Teeth, against the real historical defect rather than a toy.

        Replays metis-g105's stranding verbatim: a test asserting the OBSERVED
        subprocess timeout against a hand-typed number, while the build had
        moved on. Written to a temp file and put through the same two functions
        the real scan uses, so this exercises the detector rather than a
        restatement of it.

        Then the same assertion rewritten as a PIN — naming the constant — must
        NOT be flagged, because that form cannot strand. A guard that fails to
        tell those two apart would either miss the bug or condemn the cure.
        """
        constants = _module_limit_constants()
        constant_names = {
            owner.split(".", 1)[1] for owners in constants.values() for owner in owners
        }
        owners = constants[1080]
        self.assertIn("tropo-build-release.py.STUDIO_DEBT_RATCHET_TIMEOUT_S", owners)

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            planted = Path(tmp) / "test_planted.py"

            # The defect, as it actually shipped.
            planted.write_text(
                "# loads vault/tools/tropo-build-release.py\n"
                "class T:\n"
                "    def test_x(self):\n"
                "        self.assertEqual(run.call_args.kwargs['timeout'], 1080)\n",
                encoding="utf-8",
            )
            copies = list(_literal_copy_assertions(planted, constant_names))
            self.assertEqual([v for _, v in copies], [1080])
            self.assertIn("tropo-build-release.py", _referenced_tools(planted))

            # The cure. Same claim, named constant, cannot drift.
            planted.write_text(
                "# loads vault/tools/tropo-build-release.py\n"
                "class T:\n"
                "    def test_x(self):\n"
                "        self.assertEqual(run.call_args.kwargs['timeout'],\n"
                "                         build.STUDIO_DEBT_RATCHET_TIMEOUT_S)\n",
                encoding="utf-8",
            )
            self.assertEqual(
                list(_literal_copy_assertions(planted, constant_names)),
                [],
                "the pinned form must not be flagged — it is the fix, not the bug",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
