"""AC7 at the Publish boundary: the receipt set is the sole Verify authority.

V6, V7, V10 and V14 of the preflight matrix. The claim is not that a bundle
resolver works — that is proved next door in the vocabulary suite — but that
the real `cmd_fire` path consults it, that the legacy cold-walk file no longer
authorises anything, and that the gate runs before the first outward byte.

Structural against the real script, for the same reason the AC6-final weld
tests are: firing needs a staged release, a pinned remote, a TTY and live
credentials, and what AC7 actually claims here is checkable without any of
them. The mutations A148 named — remove the gate from cmd_fire, leave
_require_cold_walk_clearance in either path — are what these have to catch.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
PUBLISH = TOOLS / "tropo-publish-release.py"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def source() -> str:
    return PUBLISH.read_text(encoding="utf-8")


def function(name: str):
    for node in ast.walk(ast.parse(source())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def calls_in(name: str) -> set:
    node = function(name)
    if node is None:
        return set()
    found = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            target = inner.func
            if isinstance(target, ast.Name):
                found.add(target.id)
            elif isinstance(target, ast.Attribute):
                found.add(target.attr)
    return found


class FireConsultsTheReceiptSet(unittest.TestCase):

    def test_cmd_fire_calls_the_ac7_gate(self):
        self.assertIn(
            "require_ac7_receipt_set", calls_in("cmd_fire"),
            "the real Fire path does not consult the AC7 receipt set, so "
            "'four instruments passed against the shipping bytes' is a claim "
            "nothing enforces at the only place it matters",
        )

    def test_the_gate_calls_the_bundle_resolver(self):
        self.assertIn("assert_ready_to_publish", calls_in("require_ac7_receipt_set"))

    def test_the_gate_binds_receipts_to_the_frozen_digest(self):
        node = function("require_ac7_receipt_set")
        body = ast.dump(node)
        self.assertIn("package_sha256", body)
        self.assertIn("active_frozen_payload", body)

    def test_the_gate_runs_before_the_remote_is_touched(self):
        """Order is the claim. A refusal after the first push is not a refusal."""
        text = source()
        fire = text.index("def cmd_fire(")
        gate = text.index("require_ac7_receipt_set(state, version)", fire)
        remote = text.index("_require_pinned_remote(state.get(\"remote\"))", fire)
        self.assertLess(
            gate, remote,
            "the AC7 gate is consulted after the remote is resolved; the "
            "verification must precede anything outward-facing",
        )

    def test_a_missing_package_frozen_event_refuses(self):
        node = function("require_ac7_receipt_set")
        body = ast.dump(node)
        self.assertIn("no package_frozen event", body)


class TheLegacyColdWalkFileAuthorisesNothing(unittest.TestCase):

    def test_neither_stage_nor_fire_calls_it(self):
        """V10: the old verdict file is not a parallel authority.

        It was written by build Step 10.6 BEFORE the zip existed, so it
        attested to a walk over an artefact that had not been produced — and
        it was one instrument standing in for four. Two definitions of "walk
        passed" means the weaker one decides, because it is the one that runs
        first.
        """
        for command in ("cmd_stage", "cmd_fire"):
            with self.subTest(command=command):
                self.assertNotIn(
                    "_require_cold_walk_clearance", calls_in(command),
                    f"{command} still consults the legacy cold-walk verdict",
                )

    def test_it_is_called_from_nowhere_at_all(self):
        text = source()
        calls = text.count("_require_cold_walk_clearance(")
        definition = text.count("def _require_cold_walk_clearance(")
        self.assertEqual(
            calls, definition,
            "the legacy clearance is still invoked somewhere; retained for "
            "reading v1 releases is fine, retained as a live authority is not",
        )

    def test_the_retained_definition_says_why_it_is_kept(self):
        node = function("_require_cold_walk_clearance")
        self.assertIsNotNone(node)
        doc = ast.get_docstring(node) or ""
        self.assertIn("SUPERSEDED", doc)
        # Whitespace-insensitive: the phrase wraps across lines in the source,
        # and an assertion that breaks when a docstring is reflowed is testing
        # the formatter rather than the claim.
        self.assertIn("called from nowhere", " ".join(doc.lower().split()))


class TheGateResolvesRealReleaseIdentity(unittest.TestCase):

    def test_it_resolves_the_run_rather_than_trusting_state(self):
        """State is a local file; identity comes from the governed chain."""
        self.assertIn("resolve_release_run", calls_in("require_ac7_receipt_set"))

    def test_it_reads_events_through_the_engine_not_a_second_reader(self):
        calls = calls_in("require_ac7_receipt_set")
        self.assertIn("read_events", calls)
        self.assertIn("_load_pipeline_runtime", calls)


if __name__ == "__main__":
    unittest.main()
