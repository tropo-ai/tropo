#!/usr/bin/env python3
"""The gate registry decides when a gate runs; the gate does not.

Dev-spec 2fae6312 step 3. The property under test is narrow and load-bearing:
a failing gate must not be able to pass by moving itself after the act it was
meant to prevent. Everything else here supports that one claim.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.release_gates import (  # noqa: E402
    FAILURE_OPERATIONAL,
    FAILURE_REFUSAL,
    INPUT_FIRST_AVAILABLE,
    PHASES,
    VERDICT_ERROR,
    VERDICT_PASS,
    VERDICT_REFUSED,
    VERDICT_SKIPPED,
    Gate,
    GateOutcome,
    GateRegistry,
    ReleaseGateError,
    first_evaluable_phase,
    write_evidence,
)


def passing(gate_id: str):
    return lambda context: GateOutcome(gate_id=gate_id, verdict=VERDICT_PASS)


def refusing(gate_id: str, detail: str = "the world says no"):
    return lambda context: GateOutcome(
        gate_id=gate_id, verdict=VERDICT_REFUSED, detail=detail
    )


class PhaseIsComputedTests(unittest.TestCase):
    """The anti-gaming core."""

    def test_a_gate_cannot_declare_its_own_phase(self):
        with self.assertRaises(TypeError):
            Gate(
                gate_id="wishful",
                refusal_class="test",
                required_inputs=("release_plan",),
                verifier=passing("wishful"),
                first_evaluable_phase="post-publication-reconcile",
            )

    def test_the_phase_is_the_latest_input_not_the_earliest(self):
        gate = Gate(
            gate_id="mixed",
            refusal_class="test",
            required_inputs=("release_plan", "candidate_bytes"),
            verifier=passing("mixed"),
        )
        self.assertEqual(gate.first_evaluable_phase, "candidate")

    def test_a_gate_with_only_planning_inputs_runs_at_the_first_boundary(self):
        gate = Gate(
            gate_id="static",
            refusal_class="test",
            required_inputs=("release_plan", "version_string"),
            verifier=passing("static"),
        )
        self.assertEqual(gate.first_evaluable_phase, PHASES[0])

    def test_inventing_an_input_is_refused(self):
        """The move this table exists to block.

        A gate that could name a new input could name one the table happens to
        place late, and thereby schedule itself after the push it should have
        preceded. Unknown inputs are therefore a registration error, not a
        licence to pick a phase.
        """
        with self.assertRaises(ReleaseGateError) as caught:
            Gate(
                gate_id="smuggler",
                refusal_class="test",
                required_inputs=("a_convenient_late_fact",),
                verifier=passing("smuggler"),
            )
        self.assertIn("unknown release input", str(caught.exception))

    def test_the_same_declared_need_always_yields_the_same_phase(self):
        """Two gates, same inputs, no way for one to sit later than the other."""
        a = Gate("a", "test", ("frozen_package",), passing("a"))
        b = Gate("b", "test", ("frozen_package",), passing("b"))
        self.assertEqual(a.first_evaluable_phase, b.first_evaluable_phase)
        self.assertEqual(a.first_evaluable_phase, "pre-outward-fire")

    def test_revalidation_cannot_precede_the_inputs(self):
        with self.assertRaises(ReleaseGateError):
            Gate(
                gate_id="early-bird",
                refusal_class="test",
                required_inputs=("frozen_package",),
                verifier=passing("early-bird"),
                mandatory_revalidation_phase="lock-static",
            )

    def test_every_table_entry_names_a_real_phase(self):
        for name, phase in INPUT_FIRST_AVAILABLE.items():
            with self.subTest(input=name):
                self.assertIn(phase, PHASES)

    def test_a_known_input_resolves_and_an_unknown_phase_does_not(self):
        self.assertEqual(first_evaluable_phase(("release_plan",)), "lock-static")
        with self.assertRaises(ReleaseGateError):
            GateRegistry().gates_for_phase("whenever-convenient")


class SchedulingTests(unittest.TestCase):
    def registry(self) -> GateRegistry:
        registry = GateRegistry()
        registry.register(Gate("plan", "planning", ("release_plan",), passing("plan")))
        registry.register(
            Gate("bytes", "packaging", ("candidate_bytes",), passing("bytes"))
        )
        registry.register(
            Gate(
                "remote",
                "provider",
                ("remote_identity",),
                passing("remote"),
                mandatory_revalidation_phase="post-publication-reconcile",
            )
        )
        return registry

    def test_a_gate_speaks_at_its_earliest_boundary(self):
        registry = self.registry()
        self.assertEqual(
            [g.gate_id for g in registry.gates_for_phase("lock-static")], ["plan"]
        )
        self.assertEqual(
            [g.gate_id for g in registry.gates_for_phase("candidate")], ["bytes"]
        )

    def test_a_settled_gate_does_not_repeat_at_every_later_phase(self):
        registry = self.registry()
        self.assertNotIn(
            "plan", [g.gate_id for g in registry.gates_for_phase("pre-freeze")]
        )

    def test_a_declared_revalidation_runs_again(self):
        registry = self.registry()
        later = [
            g.gate_id
            for g in registry.gates_for_phase("post-publication-reconcile")
        ]
        self.assertIn("remote", later)

    def test_a_registered_gate_that_no_phase_reaches_is_reported(self):
        """Coverage for the registry itself.

        Removing a gate from the schedule does not fail anything — it makes the
        release quieter. This is the count that turns that silence into a
        finding.
        """
        registry = self.registry()
        self.assertEqual(registry.unreached_gates(PHASES), [])

        unreached = registry.unreached_gates(["lock-static"])
        self.assertEqual(
            sorted(g.gate_id for g in unreached), ["bytes", "remote"]
        )

    def test_a_duplicate_gate_id_is_refused(self):
        registry = self.registry()
        with self.assertRaises(ReleaseGateError):
            registry.register(Gate("plan", "planning", ("release_plan",), passing("plan")))


class FailureTaxonomyTests(unittest.TestCase):
    """A refusal and an operational error are different facts."""

    def context(self):
        return {name: object() for name in INPUT_FIRST_AVAILABLE}

    def test_a_refusal_is_typed_as_a_refusal(self):
        registry = GateRegistry()
        registry.register(Gate("no", "member-state", ("release_plan",), refusing("no")))
        outcome = registry.run_phase("lock-static", self.context())[0]
        self.assertEqual(outcome.verdict, VERDICT_REFUSED)
        self.assertEqual(outcome.failure_kind, FAILURE_REFUSAL)
        self.assertFalse(outcome.ok)

    def test_a_raising_verifier_becomes_an_operational_error(self):
        """Not a crash, and emphatically not a refusal.

        A provider timeout that presents as a refusal fails a release nobody
        judged; a refusal that presents as operational invites a retry loop
        around a real defect.
        """

        def explode(context):
            raise TimeoutError("provider did not answer")

        registry = GateRegistry()
        registry.register(Gate("flaky", "provider", ("release_plan",), explode))

        outcome = registry.run_phase("lock-static", self.context())[0]

        self.assertEqual(outcome.verdict, VERDICT_ERROR)
        self.assertEqual(outcome.failure_kind, FAILURE_OPERATIONAL)
        self.assertIn("TimeoutError", outcome.detail)

    def test_absent_inputs_skip_rather_than_pass(self):
        registry = GateRegistry()
        registry.register(Gate("plan", "planning", ("release_plan",), passing("plan")))

        outcome = registry.run_phase("lock-static", {"release_plan": None})[0]

        self.assertEqual(outcome.verdict, VERDICT_SKIPPED)
        self.assertIn("inputs absent", outcome.detail)

    def test_a_verifier_returning_the_wrong_type_is_a_defect(self):
        registry = GateRegistry()
        registry.register(
            Gate("sloppy", "planning", ("release_plan",), lambda ctx: True)
        )
        with self.assertRaises(ReleaseGateError):
            registry.run_phase("lock-static", self.context())

    def test_a_verifier_cannot_answer_for_another_gate(self):
        registry = GateRegistry()
        registry.register(
            Gate(
                "honest",
                "planning",
                ("release_plan",),
                lambda ctx: GateOutcome(gate_id="somebody-else", verdict=VERDICT_PASS),
            )
        )
        with self.assertRaises(ReleaseGateError):
            registry.run_phase("lock-static", self.context())

    def test_a_gate_without_a_refusal_class_is_refused(self):
        with self.assertRaises(ReleaseGateError):
            Gate("nameless", "", ("release_plan",), passing("nameless"))


class EvidenceTests(unittest.TestCase):
    def scratch(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="release-gate-evidence-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        return tmp

    def test_evidence_records_the_computed_phase_not_a_claimed_one(self):
        run_dir = self.scratch() / "run"
        registry = GateRegistry()
        registry.register(
            Gate(
                "remote",
                "provider",
                ("remote_identity",),
                refusing("remote", "remote head moved"),
                mandatory_revalidation_phase="post-publication-reconcile",
            )
        )
        context = {"remote_identity": "abc123"}

        outcomes = registry.run_phase("pre-outward-fire", context)
        path = write_evidence(run_dir, "pre-outward-fire", outcomes, registry)

        row = json.loads(path.read_text(encoding="utf-8").strip())
        self.assertEqual(row["gate_id"], "remote")
        self.assertEqual(row["verdict"], VERDICT_REFUSED)
        self.assertEqual(row["failure_kind"], FAILURE_REFUSAL)
        self.assertEqual(row["refusal_class"], "provider")
        self.assertEqual(row["first_evaluable_phase"], "pre-outward-fire")
        self.assertEqual(
            row["mandatory_revalidation_phase"], "post-publication-reconcile"
        )
        self.assertEqual(row["required_inputs"], ["remote_identity"])

    def test_evidence_appends_across_phases(self):
        run_dir = self.scratch() / "run"
        registry = GateRegistry()
        registry.register(Gate("plan", "planning", ("release_plan",), passing("plan")))
        registry.register(
            Gate("bytes", "packaging", ("candidate_bytes",), passing("bytes"))
        )
        context = {"release_plan": "p", "candidate_bytes": b"zip"}

        for phase in ("lock-static", "candidate"):
            write_evidence(run_dir, phase, registry.run_phase(phase, context), registry)

        rows = [
            json.loads(line)
            for line in (run_dir / "preflight.jsonl").read_text().splitlines()
        ]
        self.assertEqual([r["phase"] for r in rows], ["lock-static", "candidate"])


class InputTableTests(unittest.TestCase):
    def test_outward_facts_are_not_available_before_the_fire(self):
        """The table must not quietly grant a late fact an early phase.

        If `published_refs` were ever listed as lock-static, every gate reading
        it would schedule before the push and read nothing, passing vacuously.
        """
        for name in (
            "published_refs",
            "public_asset_observations",
            "publication_receipt",
            "site_endpoint_observation",
        ):
            with self.subTest(input=name):
                self.assertEqual(
                    INPUT_FIRST_AVAILABLE[name], "post-publication-reconcile"
                )

    def test_authorization_is_not_a_planning_fact(self):
        self.assertEqual(INPUT_FIRST_AVAILABLE["fire_authorization"], "pre-outward-fire")

    def test_candidate_bytes_are_not_available_at_lock(self):
        self.assertEqual(INPUT_FIRST_AVAILABLE["candidate_bytes"], "candidate")


class PreflightCliTests(unittest.TestCase):
    """The CLI's exit code carries the classification, not just failure."""

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "tropo_release_preflight_under_test", TOOLS / "tropo-release-preflight.py"
        )
        cls.cli = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.cli
        spec.loader.exec_module(cls.cli)

    def scratch_vault(self, tool_body: str) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="preflight-cli-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        tools = tmp / "vault" / "tools"
        tools.mkdir(parents=True)
        (tools / "tropo-probe.py").write_text(tool_body, encoding="utf-8")
        return tmp

    HEADER = '#!/usr/bin/env python3\n"""---\nuid: deadbeef\ntype: tool\nstatus: active\nextraction_scope: ship\n---\n"""\n'

    def test_a_clean_tree_exits_zero(self):
        vault = self.scratch_vault(
            self.HEADER
            + "\nfrom __future__ import annotations\n\n\ndef probe(v: str | None = None):\n    return v\n"
        )
        code = self.cli.main(["--phase", "lock-static", "--vault", str(vault)])
        self.assertEqual(code, self.cli.EXIT_OK)

    def test_a_refusal_exits_two_and_is_not_the_operational_code(self):
        vault = self.scratch_vault(
            self.HEADER + "\n\ndef probe(v: str | None = None):\n    return v\n"
        )
        code = self.cli.main(["--phase", "lock-static", "--vault", str(vault)])
        self.assertEqual(code, self.cli.EXIT_REFUSED)
        self.assertNotEqual(self.cli.EXIT_REFUSED, self.cli.EXIT_OPERATIONAL)

    def test_the_first_production_gate_is_scheduled_before_any_outward_act(self):
        """It reads the source tree, so there is no honest late placement."""
        registry = self.cli.build_registry()
        gate = registry.get("ship-python-floor")
        self.assertEqual(gate.first_evaluable_phase, "lock-static")
        self.assertEqual(
            registry.unreached_gates(["lock-static"]),
            [],
            "the only registered gate was not scheduled at the boundary it belongs to",
        )

    def test_evidence_is_written_to_the_release_run(self):
        vault = self.scratch_vault(
            self.HEADER
            + "\nfrom __future__ import annotations\n\n\ndef probe(v: str | None = None):\n    return v\n"
        )
        run_dir = Path(tempfile.mkdtemp(prefix="preflight-cli-run-"))
        self.addCleanup(shutil.rmtree, run_dir, True)

        self.cli.main(
            [
                "--phase",
                "lock-static",
                "--vault",
                str(vault),
                "--run-dir",
                str(run_dir),
            ]
        )

        # AMENDED 2026-08-24 by argus-a156 (Stream 1 5b608d28 AC1; Mike verbatim
        # "1 yes, 2 yes, 3 yes"; routed by metis-g112). This read preflight.jsonl
        # with json.loads() on the WHOLE FILE and asserted the single row was
        # ship-python-floor. That only ever worked because lock-static held
        # exactly ONE gate — it encoded the BOUNDARY'S EMPTINESS as its contract,
        # so it could not survive a second gate. AC1 registers six governance
        # gates there, and the file is JSONL, as its own name says.
        rows = [
            json.loads(line)
            for line in (run_dir / "preflight.jsonl").read_text().splitlines()
            if line.strip()
        ]
        self.assertIn(
            "ship-python-floor", {r["gate_id"] for r in rows},
            "the gate that ran must appear in the run's evidence",
        )
        # MUTATION GUARD (metis-g112's condition): evidence must be written per
        # gate, not once per run. If a change collapses the evidence to a single
        # row, this goes red instead of silently recording one gate of many.
        self.assertGreater(
            len(rows), 1,
            "lock-static carries the governance gates now; one row means the "
            "evidence writer stopped recording per gate",
        )
        floor = next(r for r in rows if r["gate_id"] == "ship-python-floor")
        self.assertEqual(floor["first_evaluable_phase"], "lock-static")


if __name__ == "__main__":
    unittest.main(verbosity=2)
