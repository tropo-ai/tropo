"""Every public library function is wired, or is declared unwired with a reason.

THE PATTERN THIS EXISTS TO STOP (talos-t40, 2026-08-10)
-------------------------------------------------------
Three times in one assignment I added a component and its gate, wired the
component, and left the gate as a library function that only its own tests
called. Each time the suite was fully green and the claim was unenforced:

  the trigger belt        caught by argus-a148 in review
  the wait-before-package caught by my own self-review, in the very commit that
                          fixed the trigger belt
  mutation_evidence_fields caught by the sweep that produced this file

I pinned the lesson (a2ef8240), cited it in the commit that repeated it, and
repeated it again four hours later. Writing it down demonstrably does not work.
I told Argus a third occurrence would need a structural answer rather than more
attention; this is that answer.

WHAT IT CHECKS
--------------
For each public function in the libraries this build added, either something
outside the module and outside `tests/` calls it, or it appears in
`DECLARED_UNWIRED` with a reason. The declaration is deliberate: "not yet wired,
and here is why" is a legitimate state during a staged build, while "silently
unwired" is the defect. The difference is whether a human decided.

WHY THIS IS A TEST AND NOT A LINT
---------------------------------
It has to fail the suite the moment it becomes untrue. A lint nobody runs is
exactly the same failure as a gate nobody calls.
"""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]

#: Libraries added or substantially extended by the two-pipeline split. Scoped
#: to this build rather than every lib in the studio: a sweep that reds on
#: pre-existing helpers would be permanently red, and a permanently-red check
#: teaches the crew to ignore all checks (deb77758).
WATCHED_LIBS = (
    "release_legs.py",
    "fan_in.py",
    "ignition.py",
    "lock_transaction.py",
    "tested_tree.py",
    "release_package.py",
    "release_verify.py",
    "release_closure.py",
)

#: Public functions that are intentionally not wired yet, with the reason and
#: the stage that will wire them. Adding an entry here is a decision on the
#: record; leaving one out is the defect this file catches.
DECLARED_UNWIRED = {
    "mutation_evidence_fields": (
        "Boundary-3 ruling requires mutation evidence to carry baseline SHA, "
        "mutant diff hash, and red/green verdicts. Nothing EMITS mutation "
        "evidence yet — that arrives with the Stage-7 crash/mutation suites — so "
        "the shape exists and has no producer. Declared rather than deleted "
        "because the ruling specifies it and Stage 7 will consume it; declared "
        "rather than left silent because a silently-unwired gate is exactly the "
        "defect this file exists to catch."
    ),
}

#: Not gates: pure formatting and construction helpers whose only job is to
#: return a value to a caller in the same module.
EXEMPT_PREFIXES = ("render_",)


def _public_functions(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.name for n in tree.body
            if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]


def _called_outside(name: str, defining_lib: str) -> bool:
    """Called from production code that is neither its own module nor a test."""
    pattern = re.compile(rf"\b{re.escape(name)}\s*\(")
    for base in (TOOLS, ROOT / ".tropo"):
        if not base.is_dir():
            continue
        for candidate in base.rglob("*.py"):
            if "tests" in candidate.parts or candidate.name == defining_lib:
                continue
            try:
                if pattern.search(candidate.read_text(encoding="utf-8", errors="replace")):
                    return True
            except OSError:
                continue
    return False


def _internal_call_graph(path: Path) -> dict:
    """Which functions each function in this module calls."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    graph: dict = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        called = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                func = inner.func
                if isinstance(func, ast.Name):
                    called.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called.add(func.attr)
        graph[node.name] = called
    return graph


def _import_time_references(path: Path) -> set:
    """Function names referenced outside any function body — decorators,
    default factories, module-level tables. These run at import."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    inside_functions = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for inner in ast.walk(node):
                inside_functions.add(id(inner))
    referenced = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and id(node) not in inside_functions:
            referenced.add(node.id)
    return referenced


def _has_production_caller(name: str, defining_lib: str) -> bool:
    """Is this function REACHABLE from production?

    Directly called from outside, or called — possibly transitively — by
    something in its own module that is. Internal composition is not the defect
    this file hunts: `resolve_leg` being invoked only by the wired
    `assert_ready_to_freeze` is good design, not a dangling gate. What matters is
    whether any production path reaches it at all.

    My first version asked "is it called outside its own module", which flagged
    eight correctly-wired functions. A check that reds on correct code is worse
    than none — it is the permanently-red check deb77758 warns teaches the crew
    to ignore every check.
    """
    if _called_outside(name, defining_lib):
        return True
    path = TOOLS / "lib" / defining_lib
    if not path.is_file():
        return False

    graph = _internal_call_graph(path)
    entry_points = {fn for fn in graph if _called_outside(fn, defining_lib)}
    # Names referenced at MODULE or CLASS level are roots too: they execute at
    # import. `current_lock_token` is a dataclass `default_factory=` — a
    # reference, never a call inside a function body — so a call-graph alone
    # reported it unwired when it runs on every LockPlan construction.
    entry_points |= _import_time_references(path)
    seen, frontier = set(), list(entry_points)
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(graph.get(current, ()))
    return name in seen


class EveryGateIsWiredOrDeclared(unittest.TestCase):

    def test_no_public_function_is_silently_unwired(self) -> None:
        unwired = []
        for lib_name in WATCHED_LIBS:
            path = TOOLS / "lib" / lib_name
            if not path.is_file():
                continue
            for name in _public_functions(path):
                if name.startswith(EXEMPT_PREFIXES) or name in DECLARED_UNWIRED:
                    continue
                if not _has_production_caller(name, lib_name):
                    unwired.append(f"{lib_name}::{name}")

        self.assertEqual(
            unwired, [],
            "these public functions have no production caller — only tests "
            f"invoke them: {unwired}. A helper nobody calls is not a gate, "
            "however well tested. Either wire it, or add it to DECLARED_UNWIRED "
            "with the reason and the stage that will.")

    def test_the_declared_exceptions_are_still_actually_unwired(self) -> None:
        """A declaration that outlives its reason is a lie in the record.

        Once something IS wired, its entry must go — otherwise the list drifts
        into a permanent excuse and stops meaning anything.
        """
        stale = []
        for name in DECLARED_UNWIRED:
            for lib_name in WATCHED_LIBS:
                path = TOOLS / "lib" / lib_name
                if path.is_file() and name in _public_functions(path):
                    if _has_production_caller(name, lib_name):
                        stale.append(f"{lib_name}::{name}")
        self.assertEqual(
            stale, [],
            f"these are declared unwired but now HAVE production callers: {stale}. "
            "Remove them from DECLARED_UNWIRED.")

    def test_every_declaration_carries_a_real_reason(self) -> None:
        """An entry with an empty or perfunctory reason is a checkbox."""
        for name, reason in DECLARED_UNWIRED.items():
            with self.subTest(function=name):
                self.assertGreater(
                    len(reason), 120,
                    f"{name}'s declaration does not explain why it is unwired or "
                    "what will wire it")

    def test_the_check_can_actually_fail(self) -> None:
        """The control, and the one that matters most here.

        This whole file guards against a check that passes while proving
        nothing — so it must demonstrate it can detect the condition. A name
        that exists nowhere in production must read as unwired.
        """
        self.assertFalse(
            _has_production_caller("a_function_that_does_not_exist_anywhere", "none.py"),
            "the caller-detection returns True for a name that does not exist; "
            "it would pass everything")
        self.assertTrue(
            _has_production_caller("assert_ready_to_freeze", "release_legs.py"),
            "the caller-detection cannot see a function that IS wired; it would "
            "red on correct code")


if __name__ == "__main__":
    unittest.main()
