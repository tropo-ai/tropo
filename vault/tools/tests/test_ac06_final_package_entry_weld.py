"""AC6-final: the real package entry point consults the freeze gate.

A148 reopened AC6 after accepting Stage 5 because the weld went into the
engine's wait step while `tropo-build-release.py` — the only thing that
actually produces a package — ran standalone and never consulted
`assert_ready_to_freeze` (evt_a9360f18f56fe472_00000010). The wait suite proved
the helper; nothing proved the package path.

So these tests are deliberately structural against the REAL script rather than
behavioural against an importable seam. Running the build end to end needs a
full studio, a release plan, settled legs and several minutes; what AC6-final
actually claims is narrower and checkable: the production package path resolves
a release run, calls the gate, and cannot be reached without doing so.

The mutation A148 named is the point of the file — removing the production call
must turn these red. A green suite after that plant is a fail.
"""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
BUILD = TOOLS / "tropo-build-release.py"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _source() -> str:
    return BUILD.read_text(encoding="utf-8")


def _function(name: str):
    for node in ast.walk(ast.parse(_source())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _calls_within(node) -> set:
    found = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            target = inner.func
            if isinstance(target, ast.Name):
                found.add(target.id)
            elif isinstance(target, ast.Attribute):
                found.add(target.attr)
    return found


class ThePackagePathConsultsTheFreezeGate(unittest.TestCase):

    def test_the_authority_helper_calls_assert_ready_to_freeze(self):
        node = _function("stage6_package_authority")
        self.assertIsNotNone(
            node, "stage6_package_authority is gone from the build script")
        self.assertIn(
            "assert_ready_to_freeze", _calls_within(node),
            "the package authority no longer calls the freeze gate; AC6's "
            "claim that package freeze refuses until legs settle is false "
            "again, in the same place it was false before",
        )

    def test_the_authority_helper_resolves_the_release_run(self):
        node = _function("stage6_package_authority")
        self.assertIn("resolve_release_run", _calls_within(node))

    def test_main_calls_the_authority_before_it_zips(self):
        """Order is the claim, not merely presence.

        A gate that runs after the zip has already produced the artefact it
        was meant to prevent. This asserts the call sites appear in the right
        order in the real main().
        """
        node = _function("main")
        self.assertIsNotNone(node)
        source = _source()
        # Anchor on the CALL SITE, not the substring: `stage6_package_authority(
        # activation_uid)` also matches the function's own `def` line, which
        # sits earlier in the file than the zip no matter where the call moved.
        # The first version of this test did that and stayed green when the
        # gate was planted after the zip -- measuring the definition's position
        # and calling it ordering.
        gate = source.index(
            "_stage6_identity, _stage6_states = stage6_package_authority(")
        zip_call = source.index("step_11_zip_and_upload(build_dir, new_version, dist_dir, DRY_RUN)")
        self.assertLess(
            gate, zip_call,
            "the freeze gate is consulted after the package is zipped, which "
            "is a refusal that already cost an artefact",
        )

    def test_the_gate_has_no_omission_bypass(self):
        """A148 Q2: no caller boolean, no no-activation fallback.

        The refusal for a missing activation lives in resolve_release_run, so
        what this checks is that the build never routes around it — no branch
        that skips the authority when the activation is absent.
        """
        source = _source()
        self.assertNotIn(
            "if activation_uid and", source,
            "a conditional on activation_uid presence would let a caller skip "
            "the freeze gate by omitting the argument",
        )
        gate_line = re.search(
            r"_stage6_identity, _stage6_states = stage6_package_authority\(activation_uid\)",
            source)
        self.assertIsNotNone(
            gate_line, "the gate is not called with the activation argument")

    def test_a_refusal_exits_nonzero_rather_than_warning(self):
        source = _source()
        window = source[source.index("_stage6_identity = None"):
                        source.index("_key = require_release_authorization")]
        self.assertIn("sys.exit(1)", window)
        self.assertNotIn(
            "continue", window,
            "the freeze gate warns and proceeds somewhere in its refusal path",
        )

    def test_step_10_6_is_disabled_on_the_v2_path_only(self):
        """The legacy walk must not become a second definition of 'walk passed'.

        Not deleted: v1 builds still run it. Skipped when a release identity
        resolved, which is the same predicate the gate uses, so the two cannot
        disagree about which path this is.
        """
        source = _source()
        self.assertIn("if _stage6_identity is None:", source)
        guarded = source.index("if _stage6_identity is None:")
        call = source.index("_build_clean = step_10_6_cold_walk_gate(")
        self.assertLess(
            guarded, call,
            "step 10.6 runs unconditionally, so the v2 path would carry two "
            "definitions of the stranger walk",
        )

    def test_the_v2_path_does_not_run_legacy_close_out(self):
        """P10, A148 blocker 1 (evt_a9360f18f56fe472_00000022).

        Step 12 fired whenever an activation was supplied, so a v2 release
        invoked legacy close-out immediately after packaging — before Verify,
        before Publish, before any receipt existed. The release would close its
        own substrate while the artefact it had just built was unverified and
        unpublished.

        Guarded by the same `_stage6_identity` predicate as step 10.6 so the
        two cannot disagree about which path the build is on.
        """
        source = _source()
        guard = "if not DRY_RUN and activation_uid and _stage6_identity is None:"
        self.assertTrue(
            guard in source,
            "legacy close-out is not guarded off the v2 release path; a v2 "
            "build closes its substrate before the package is verified",
        )
        # The close-out subprocess must sit INSIDE that guard, not merely after
        # it. Checked by indentation rather than by a nearby marker: the first
        # version anchored on a following `step_` call that does not exist, so
        # the test errored instead of measuring containment.
        lines = source.splitlines()
        start = next(i for i, line in enumerate(lines) if line.strip() == guard.strip())
        guard_indent = len(lines[start]) - len(lines[start].lstrip())
        body = []
        for line in lines[start + 1:]:
            if line.strip() and (len(line) - len(line.lstrip())) <= guard_indent:
                break
            body.append(line)
        # assertTrue, not assertIn: assertIn prints the entire haystack on
        # failure, and the haystack here is a 3,000-line build script. A
        # failure nobody can read is a failure nobody acts on.
        self.assertTrue(
            "close-out" in "\n".join(body),
            "the close-out invocation is not inside the v2 guard, so it still "
            "runs on the release path",
        )

    def test_the_freeze_records_one_identity_from_the_shipped_bytes(self):
        node = _function("stage6_freeze_package")
        self.assertIsNotNone(node)
        calls = _calls_within(node)
        self.assertIn("hash_final_zip", calls)
        self.assertIn("reconcile_existing_freeze", calls)
        self.assertIn("package_frozen_payload", calls)

    def test_package_identity_does_not_depend_on_who_built_it(self):
        """A148 blocker 2 (evt_a9360f18f56fe472_00000022).

        The freeze emitter passed `--as talos`, so the same bytes would have
        carried different provenance under Metis or Vela. A package is authored
        by the TOOL that produced it; who was at the keyboard is not part of
        its identity.
        """
        source = _source()
        node = _function("stage6_freeze_package")
        self.assertIsNotNone(node)
        body = ast.dump(node)
        self.assertNotIn(
            "'--as'", body,
            "the package_frozen emitter still stamps an agent identity",
        )
        self.assertIn("BUILD_TOOL_UID", body)
        # Run-local via the runtime's own writer, not a subprocess to
        # tropo-emit-event.py. The subprocess passed --run-folder (not a real
        # flag) and omitted --lifecycle (required), so it would have failed on
        # every real invocation — and never did, because nothing had driven
        # this path end to end.
        self.assertIn("append_event", body)
        self.assertIn("make_event", body)
        self.assertNotIn("tropo-emit-event.py", body)
        self.assertTrue(
            'BUILD_TOOL_UID = "a1b8c2d4"' in source,
            "the tool uid is not this script's registered identity",
        )

    def test_leg_records_come_from_the_shared_derivation(self):
        """The build and the engine must not disagree about leg state.

        Both read `leg_records_from_events`. A second derivation next to the
        build would drift, and the failure mode is a package frozen against
        legs the engine still considers open.
        """
        node = _function("stage6_package_authority")
        self.assertIn("leg_records_from_events", _calls_within(node))
        engine = (TOOLS / "9e7003b1.py").read_text(encoding="utf-8")
        self.assertIn(
            "leg_records_from_events", engine,
            "the engine no longer delegates to the shared derivation, so the "
            "build and the engine can now disagree",
        )


if __name__ == "__main__":
    unittest.main()
