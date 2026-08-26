"""AC1 of 5b608d28 — every knowable precondition, reported once, all at once.

v1.91 discovered roughly twenty preconditions one refusal at a time, from inside
the build, after the run had started. Every one was knowable before anything
ran. This suite pins the cure:

  * the governance preconditions are REGISTERED as gates, and the registry
    computes each to lock-static because their inputs are all planning facts —
    a gate cannot choose a later boundary for itself;
  * the report is exhaustive: four unmet preconditions produce ONE report
    naming all four, never a first-failure exit;
  * an empty boundary SAYS it is empty, because three boundaries stood empty
    for months behind an ambiguous blank.

The mutation control is the load-bearing part. A report that still names four
findings when one gate has been removed is not reading the registry.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PREFLIGHT = _load("release_preflight_ac1", "tropo-release-preflight.py")
from lib import release_gates  # noqa: E402


def _unmet_context() -> dict:
    """A release whose four governance preconditions are each unmet, once.

    Deliberately NOT one failure repeated: four DISTINCT preconditions, so a
    report that stops early names fewer than four and the test says which.
    """
    return {
        # 1. the plan declares no ratchet targets
        "release_plan": {"uid": "aaaaaaaa", "status": "locked", "ratchet_targets": []},
        # 2. a member is not done
        "fan_in_manifest": ["bbbbbbbb", "cccccccc"],
        "member_states": {"bbbbbbbb": "done", "cccccccc": "in-progress"},
        # 3. a dev-spec carries no acceptance_criteria where the gesture reads
        # 4. a member targets an already-shipped release
        "governed_index": {
            "bbbbbbbb": {"type": "dev-spec", "acceptance_criteria": [],
                         "target_release": "1.92.0"},
            "cccccccc": {"type": "dev-spec", "target_release": "1.90.0",
                         "acceptance_criteria": [{"id": "AC1", "verify": {}}]},
            "dddddddd": {"type": "release", "status": "shipped",
                         "release_version": "1.90.0"},
        },
        "version_string": "1.92.0",
        "shipped_tool_corpus": str(TOOLS.parent.parent),
        "source_tree": str(TOOLS.parent.parent),
    }


class TheGovernancePreconditionsAreGates(unittest.TestCase):

    def test_they_compute_to_lock_static_and_cannot_choose_later(self):
        """Their inputs are planning facts, so the registry puts them first."""
        registry = PREFLIGHT.build_registry()
        ids = {g.gate_id for g in registry.gates_for_phase("lock-static")}
        for gate_id, _cls, _inputs, _desc in PREFLIGHT.LOCK_STATIC_GOVERNANCE_ROSTER:
            self.assertIn(gate_id, ids, "%s must speak at lock-static" % gate_id)

    def test_declared_inputs_are_all_known_to_the_input_table(self):
        """A gate naming an unknown input would be granted a phase of its choice."""
        for gate_id, _cls, inputs, _desc in PREFLIGHT.LOCK_STATIC_GOVERNANCE_ROSTER:
            for name in inputs:
                self.assertIn(
                    name, release_gates.INPUT_FIRST_AVAILABLE,
                    "%s declares unknown input %r" % (gate_id, name),
                )

    def test_every_roster_row_has_a_verifier_and_no_verifier_is_stray(self):
        roster_ids = {r[0] for r in PREFLIGHT.LOCK_STATIC_GOVERNANCE_ROSTER}
        self.assertEqual(roster_ids, set(PREFLIGHT.GOVERNANCE_VERIFIERS))


class TheReportIsExhaustive(unittest.TestCase):

    def _refusals(self, registry) -> dict:
        outcomes = registry.run_phase("lock-static", _unmet_context())
        return {
            o.gate_id: o for o in outcomes
            if o.verdict == release_gates.VERDICT_REFUSED
        }

    def test_four_unmet_preconditions_produce_one_report_naming_all_four(self):
        refused = self._refusals(PREFLIGHT.build_registry())
        for expected in (
            "lock-ratchet-targets",
            "lock-members-terminal",
            "lock-criteria-readable",
            "lock-target-release-current",
        ):
            self.assertIn(
                expected, refused,
                "the report stopped before %s — first-failure, not exhaustive" % expected,
            )

    def test_a_refusal_names_every_failure_not_only_the_first(self):
        """Within one gate, too: 'names EVERY unresolved target, not the first'."""
        context = _unmet_context()
        context["member_states"] = {"bbbbbbbb": "draft", "cccccccc": "in-progress"}
        refused = {
            o.gate_id: o for o in
            PREFLIGHT.build_registry().run_phase("lock-static", context)
            if o.verdict == release_gates.VERDICT_REFUSED
        }
        detail = refused["lock-members-terminal"].detail
        self.assertIn("bbbbbbbb", detail)
        self.assertIn("cccccccc", detail)
        self.assertEqual(2, refused["lock-members-terminal"].evidence["count"])

    def test_MUTATION_removing_one_gate_loses_exactly_that_finding(self):
        """The control. Lose one gate, lose one finding — not zero, not two."""
        full = set(self._refusals(PREFLIGHT.build_registry()))

        registry = PREFLIGHT.build_registry()
        registry._gates.pop("lock-members-terminal")  # noqa: SLF001 — the mutation
        mutated = set(self._refusals(registry))

        self.assertEqual(
            full - mutated, {"lock-members-terminal"},
            "removing one gate must remove exactly its finding",
        )
        self.assertEqual(mutated - full, set(), "and must not add any")

    def test_cannot_see_is_not_you_are_wrong(self):
        """An unreadable plan is an operational error, never a refusal."""
        context = _unmet_context()
        context["release_plan"] = "not-a-record"
        outcomes = {
            o.gate_id: o for o in
            PREFLIGHT.build_registry().run_phase("lock-static", context)
        }
        self.assertEqual(
            release_gates.VERDICT_ERROR, outcomes["lock-plan-record"].verdict
        )

    def test_a_clean_release_refuses_nothing(self):
        """The known-negative: a gate that always fires protects nothing."""
        context = _unmet_context()
        context["release_plan"] = {"uid": "aaaaaaaa", "status": "locked",
                                   "ratchet_targets": ["debt"]}
        context["member_states"] = {"bbbbbbbb": "done", "cccccccc": "done"}
        context["governed_index"] = {
            "bbbbbbbb": {"type": "dev-spec", "target_release": "1.92.0",
                         "acceptance_criteria": [{"id": "AC1", "verify": {}}]},
            "cccccccc": {"type": "dev-spec", "target_release": "1.92.0",
                         "acceptance_criteria": [{"id": "AC1", "verify": {}}]},
        }
        refused = {
            o.gate_id: o for o in
            PREFLIGHT.build_registry().run_phase("lock-static", context)
            if o.verdict == release_gates.VERDICT_REFUSED
        }
        governance = {r[0] for r in PREFLIGHT.LOCK_STATIC_GOVERNANCE_ROSTER}
        self.assertEqual(
            set(), set(refused) & governance,
            "a clean release must clear every governance gate: %s" % refused,
        )


class AnEmptyBoundarySaysSo(unittest.TestCase):

    def test_zero_gates_prints_an_explicit_line(self):
        import io
        import contextlib
        for phase in ("candidate", "pre-freeze", "post-publication-reconcile"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                PREFLIGHT.main(["--phase", phase, "--list"])
            self.assertIn(
                "0 gates registered at %s" % phase, buf.getvalue(),
                "an empty boundary printed an ambiguous blank",
            )


if __name__ == "__main__":
    unittest.main()
