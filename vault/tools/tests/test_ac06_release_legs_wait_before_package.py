"""AC6 — release legs, the wait before package freeze, and dev-never-triggers.

"Release Assemble opens doc/test branches from release-run provenance and
package freeze refuses until each leg is terminal or independently attested; dev
runs never trigger them."

Named success evidence from the paired contract, each with a test below:
  dev trigger count is zero
  either incomplete release leg blocks package creation
  independent attestation is a first-class alternative, both paths mutation-proved
  package freeze happens only after the wait, never before

Every refusal has a positive control beside it. A gate that refuses everything
passes a refusal test perfectly and protects nothing.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_ac06_release_legs_wait_before_package
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

sys.path.insert(0, str(Path(__file__).resolve().parent))

import temp_studio  # noqa: E402
from lib import release_legs as legs  # noqa: E402

RELEASE_ROOT = "634913c2"
DEV_ROOT = "cd1fcd25"
RUN = "0bb00001"
SHA = "a1b2c3d4" * 5


def _attestation(**overrides) -> dict:
    body = {
        "uid": "a77e5701", "type": legs.ATTESTATION_TYPE,
        "attester": "mike-maziarz", "leg": "doc",
        "release_pipeline_run_uid": RUN, "tested_commit_sha": SHA,
        "rationale": "doc work deferred to the following cycle by explicit decision",
    }
    body.update(overrides)
    return {"frontmatter": body}


def _reader(entries: dict):
    return lambda uid: entries.get(uid)


class DevRunsNeverOpenLegs(unittest.TestCase):
    """"Dev trigger count is zero" — enforced, not counted.

    Counting dev triggers after the fact tells you it happened. Refusing means
    it cannot.
    """

    def test_a_release_run_may_open_a_leg(self) -> None:
        """The control. Without it the refusals below pass for a gate that
        blocks every trigger, which would be a broken release pipeline rather
        than a protected one."""
        run = {"uid": RUN, "pipeline": RELEASE_ROOT}
        self.assertEqual(
            legs.assert_release_run_provenance(run, RELEASE_ROOT), RUN)

    def test_a_DEV_run_is_refused(self) -> None:
        run = {"uid": "0bb0dead", "pipeline": DEV_ROOT}
        with self.assertRaises(legs.TriggerProvenanceRefusal) as caught:
            legs.assert_release_run_provenance(run, RELEASE_ROOT)
        self.assertIn("Dev runs never open", str(caught.exception))

    def test_no_parent_run_at_all_is_refused(self) -> None:
        """A leg with no provenance is a leg no release can cite."""
        with self.assertRaises(legs.TriggerProvenanceRefusal) as caught:
            legs.assert_release_run_provenance(None, RELEASE_ROOT)
        self.assertIn("no provenance", str(caught.exception))

    def test_a_run_with_no_resolvable_uid_is_refused(self) -> None:
        with self.assertRaises(legs.TriggerProvenanceRefusal):
            legs.assert_release_run_provenance(
                {"uid": "not-a-uid", "pipeline": RELEASE_ROOT}, RELEASE_ROOT)

    def test_the_dev_graph_no_longer_declares_the_triggers(self) -> None:
        """Topology and runtime, not either alone (argus-a148).

        The engine belt stops a leftover call path. The graph telling the truth
        is what stops the path existing.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location("eng", TOOLS / "9e7003b1.py")
        eng = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eng)

        dev_steps = set(eng.collect_step_nodes(eng.resolve_workflow_node_tree(DEV_ROOT)))
        release_steps = set(eng.collect_step_nodes(
            eng.resolve_workflow_node_tree(RELEASE_ROOT)))

        for trigger in ("0cf86ea5", "4f64ec3c", "37996741"):
            with self.subTest(node=trigger):
                self.assertNotIn(trigger, dev_steps,
                                 "a doc/test trigger is still in the dev graph")
                self.assertIn(trigger, release_steps,
                              "the trigger was removed from dev but never landed "
                              "on the release graph")


class ReleaseTriggerProvenanceChain(unittest.TestCase):
    """The trigger binds to the release identity that already owns AC6 legs."""

    ACTIVATION = "ac700001"
    PLAN = "b1a00001"

    def _activation(self, **overrides) -> dict:
        fm = {
            "uid": self.ACTIVATION,
            "type": "activation",
            "pipeline_uid": RELEASE_ROOT,
            "pipeline_run_uid": RUN,
            "release_plan_uid": self.PLAN,
        }
        fm.update(overrides)
        return fm

    def _run(self, **overrides) -> dict:
        fm = {
            "uid": RUN,
            "type": "pipeline-run",
            "pipeline": RELEASE_ROOT,
            "activation": self.ACTIVATION,
            "release_plan_uid": self.PLAN,
        }
        fm.update(overrides)
        return fm

    def _plan(self, **overrides) -> dict:
        fm = {
            "uid": self.PLAN,
            "type": "release-plan",
            "release_activation_uid": self.ACTIVATION,
            "release_pipeline_run_uid": RUN,
        }
        fm.update(overrides)
        return {"frontmatter": fm}

    def test_the_complete_activation_run_plan_chain_resolves(self) -> None:
        provenance = legs.resolve_release_trigger_provenance(
            self._activation(), self._run(), RELEASE_ROOT,
            _reader({self.PLAN: self._plan()}),
        )
        self.assertEqual(provenance.activation_uid, self.ACTIVATION)
        self.assertEqual(provenance.release_plan_uid, self.PLAN)
        self.assertEqual(provenance.release_run_uid, RUN)

    def test_every_cross_link_is_load_bearing(self) -> None:
        mutations = (
            ("activation run", self._activation(pipeline_run_uid="0bb0ffff"),
             self._run(), self._plan()),
            ("run activation", self._activation(),
             self._run(activation="ac70ffff"), self._plan()),
            ("activation plan", self._activation(release_plan_uid="b1a0ffff"),
             self._run(), self._plan()),
            ("plan activation", self._activation(), self._run(),
             self._plan(release_activation_uid="ac70ffff")),
            ("plan run", self._activation(), self._run(),
             self._plan(release_pipeline_run_uid="0bb0ffff")),
        )
        for label, activation, run, plan in mutations:
            with self.subTest(link=label):
                with self.assertRaises(legs.TriggerProvenanceRefusal):
                    legs.resolve_release_trigger_provenance(
                        activation, run, RELEASE_ROOT,
                        _reader({self.PLAN: plan}),
                    )


class TheRealTriggerRefusesADevRun(unittest.TestCase):
    """The belt, through the PRODUCTION entry point.

    A mutation removing the engine's provenance call survived every test above,
    because they all exercised `assert_release_run_provenance` directly. The
    helper was proven; nothing proved the runtime called it — which is precisely
    the seam failure I pinned as a2ef8240 hours before writing this suite, and it
    recurred immediately. So this drives `action_trigger_step` itself, in a
    TempStudio with a fresh interpreter, and asserts the live Studio is
    untouched.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac06-trigger-")).resolve()
        self.studio = temp_studio.TempStudio(self.tmp / "studio").build()
        self.before = temp_studio.production_fingerprint()

    def tearDown(self) -> None:
        after = temp_studio.production_fingerprint()
        changes = temp_studio.diff_fingerprints(self.before, after)
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertEqual(changes, {},
                         f"an AC6 trigger test wrote into the production Studio: {changes}")

    def _seed(self, pipeline_uid: str) -> None:
        activation_lines = [
            "type: activation", "title: cascade parent", "status: active",
            "activation_class: pipeline", "dev_spec_uid: '5ec00001'",
            f"pipeline_uid: {pipeline_uid}", "pipeline_run_uid: '0bb00001'",
        ]
        run_lines = [
            "type: pipeline-run", "title: parent run", "status: active",
            f"pipeline: {pipeline_uid}", "substrate_authored_by: 'ac700001'",
            "activation: 'ac700001'", "pipeline_version: '2.0.0'",
            "run_folder: 'vault/pipeline-runs/parent-run'",
        ]
        if pipeline_uid == RELEASE_ROOT:
            activation_lines.append("release_plan_uid: 'b1a00001'")
            run_lines.append("release_plan_uid: 'b1a00001'")
            self.studio.write_entry("b1a00001", [
                "type: release-plan", "title: release plan", "status: locked",
                "release_activation_uid: 'ac700001'",
                "release_pipeline_run_uid: '0bb00001'",
            ])
        self.studio.write_entry("ac700001", activation_lines)
        self.studio.write_entry("0bb00001", run_lines)
        folder = self.studio.runs / "parent-run"
        folder.mkdir(parents=True, exist_ok=True)
        event = {
            "event": "step_declared", "step": None, "span_id": "fixture-span",
            "trace_id": "ac700001", "ts": "2026-08-14T00:00:00Z",
            "data": {
                "step_id": "0cf86ea5", "depends_on_steps": [],
                "trust_level": "auto-with-verification",
            },
        }
        (folder / "run.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
        self.studio.write_entry("5ec00001", [
            "type: dev-spec", "title: the spec", "status: locked"])

    def _fire(self) -> subprocess.CompletedProcess:
        script = self.studio.root / "fire_trigger.py"
        script.write_text(
            "import sys, importlib.util\n"
            f"sys.path.insert(0, {str(self.studio.tools)!r})\n"
            f"spec = importlib.util.spec_from_file_location('eng', {str(self.studio.tools / '9e7003b1.py')!r})\n"
            "eng = importlib.util.module_from_spec(spec); spec.loader.exec_module(eng)\n"
            "from lib import release_legs\n"
            "try:\n"
            "    eng.action_trigger_step('ac700001', '0cf86ea5', 'd0c00001',\n"
            "        '---\\nuid: d0c00001\\ntype: doc-spec\\n---\\n\\nbody\\n',\n"
            "        '5a4337ff', 'doc-pipeline', 'talos')\n"
            "    print('TRIGGER-FIRED')\n"
            "except release_legs.TriggerProvenanceRefusal as exc:\n"
            "    print('REFUSED', exc)\n"
            "except Exception as exc:\n"
            "    print('OTHER', type(exc).__name__, exc)\n",
            encoding="utf-8")
        return subprocess.run([sys.executable, str(script)],
                              capture_output=True, text=True, timeout=120)

    def test_a_dev_parent_run_is_refused_by_the_real_entry_point(self) -> None:
        self._seed(DEV_ROOT)
        result = self._fire()
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        self.assertIn("REFUSED", result.stdout,
                      f"the real trigger opened a cascade from a DEV run: {result.stdout}")
        self.assertIn("Dev runs never open", result.stdout)
        cascades = [p.stem for p in self.studio.files.glob("*.md")
                    if "type: activation" in p.read_text() and p.stem != "ac700001"]
        self.assertEqual(cascades, [], f"a cascade activation was created: {cascades}")

    def test_a_release_parent_run_gets_past_the_provenance_gate(self) -> None:
        """Positive control. Without it the refusal above passes for a trigger
        that is simply broken, which would be a broken release pipeline rather
        than a protected one.

        It need not SUCCEED — the fixture has no real cascade pipeline — only
        get past provenance, which is the gate under test.
        """
        self._seed(RELEASE_ROOT)
        result = self._fire()
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        self.assertNotIn("Dev runs never open", result.stdout,
                         f"a RELEASE run was refused by the dev gate: {result.stdout}")


class GovernedLifecycleIsAuthoritative(unittest.TestCase):
    """Archived/cancelled frontmatter outranks an incomplete historical event log."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac06-lifecycle-")).resolve()
        self.studio = temp_studio.TempStudio(self.tmp / "studio").build()
        self.before = temp_studio.production_fingerprint()
        self.runtime = self.studio.load("9e7003b1.py", "ac06_lifecycle_runtime")
        self.studio.assert_tools_are_rooted_here(self.runtime)

        self.studio.write_entry(RELEASE_ROOT, [
            "type: pipeline", "title: release root", "status: active",
            "version: 1.0.0", "children:", "  - 0cf86ea5",
        ])
        self.studio.write_entry("0cf86ea5", [
            "type: pipeline", "subtype: workflow-node", "title: trigger doc",
            "status: active", "children: []",
        ])
        self.studio.write_entry("b1a00001", [
            "type: release-plan", "title: cancelled release", "status: cancelled",
            "state: archived", "release_activation_uid: 'ac700001'",
            "release_pipeline_run_uid: '0bb00001'",
        ])
        self.studio.write_entry("ac700001", [
            "type: activation", "title: retired release activation",
            "activation_class: pipeline", "status: retired", "state: archived",
            f"pipeline_uid: {RELEASE_ROOT}", "pipeline_run_uid: '0bb00001'",
            "release_plan_uid: 'b1a00001'",
        ])
        self.studio.write_entry("0bb00001", [
            "type: pipeline-run", "title: cancelled release run",
            "status: cancelled", "state: archived", f"pipeline: {RELEASE_ROOT}",
            "substrate_authored_by: 'ac700001'", "release_plan_uid: 'b1a00001'",
            "run_folder: 'vault/pipeline-runs/cancelled-release'",
        ])
        folder = self.studio.runs / "cancelled-release"
        folder.mkdir(parents=True)
        event = self.runtime.make_event(
            "step_declared", "fixture", trace_id="ac700001",
            parent_span_id=None, data={
                "step_id": "0cf86ea5", "depends_on_steps": [],
                "trust_level": "auto-with-verification",
            },
        )
        (folder / "run.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        after = temp_studio.production_fingerprint()
        changes = temp_studio.diff_fingerprints(self.before, after)
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertEqual(changes, {},
                         f"a lifecycle regression test touched production: {changes}")

    def test_resume_reports_cancelled_with_no_eligible_steps(self) -> None:
        report = self.runtime.action_resume_from_log("ac700001")
        self.assertEqual(report["run_status"], "cancelled")
        self.assertEqual(report["eligible_steps"], [])

    def test_real_mutation_refuses_to_advance_the_cancelled_run(self) -> None:
        with self.assertRaises(self.runtime.ContractError) as caught:
            self.runtime.action_step_start(
                "ac700001", "0cf86ea5", "talos", dry_run=False)
        self.assertIn("cancelled", str(caught.exception))

    def test_dry_run_refuses_without_advancing_the_cancelled_run(self) -> None:
        run_log = self.studio.runs / "cancelled-release" / "run.jsonl"
        before = run_log.read_bytes()
        with self.assertRaises(self.runtime.ContractError) as caught:
            self.runtime.action_step_start(
                "ac700001", "0cf86ea5", "talos", dry_run=True)
        self.assertIn("cancelled", str(caught.exception))
        self.assertEqual(run_log.read_bytes(), before)


class ThePackageFreezeWaits(unittest.TestCase):

    def _records(self, doc=None, test=None) -> dict:
        return {"doc": doc, "test": test}

    def test_both_legs_terminal_allows_the_freeze(self) -> None:
        """Positive control for the whole gate."""
        entries = {"act00doc": {"frontmatter": {"status": "done"}},
                   "act0test": {"frontmatter": {"status": "closed"}}}
        states = legs.assert_ready_to_freeze(
            RUN,
            self._records({"activation_uid": "act00doc"}, {"activation_uid": "act0test"}),
            _reader(entries))
        self.assertEqual([s.basis for s in states], ["terminal", "terminal"])

    def test_EITHER_incomplete_leg_blocks_the_freeze(self) -> None:
        """The contract says "either incomplete release leg", so test both
        sides. A gate that only checks the first leg passes a one-sided test."""
        for incomplete in ("doc", "test"):
            with self.subTest(incomplete=incomplete):
                entries = {"act00doc": {"frontmatter": {"status": "done"}},
                           "act0test": {"frontmatter": {"status": "done"}}}
                entries["act00doc" if incomplete == "doc" else "act0test"] = {
                    "frontmatter": {"status": "active"}}
                with self.assertRaises(legs.LegRefusal) as caught:
                    legs.assert_ready_to_freeze(
                        RUN,
                        self._records({"activation_uid": "act00doc"},
                                      {"activation_uid": "act0test"}),
                        _reader(entries))
                self.assertIn("package freeze refused", str(caught.exception))
                self.assertIn(incomplete, str(caught.exception))

    def test_an_unreadable_leg_refuses_rather_than_warning(self) -> None:
        """argus-a148 answer 3, Mike-locked. "I cannot see" is normally a third
        answer — but the question here is not "did it pass", it is "may I
        freeze", and an unproved yes is a no."""
        entries = {"act0test": {"frontmatter": {"status": "done"}}}
        with self.assertRaises(legs.LegRefusal) as caught:
            legs.assert_ready_to_freeze(
                RUN,
                self._records({"activation_uid": "act00doc"},
                              {"activation_uid": "act0test"}),
                _reader(entries))
        self.assertIn("does not resolve", str(caught.exception))

    def test_a_leg_that_was_never_opened_refuses(self) -> None:
        entries = {"act0test": {"frontmatter": {"status": "done"}}}
        with self.assertRaises(legs.LegRefusal) as caught:
            legs.assert_ready_to_freeze(
                RUN, self._records(None, {"activation_uid": "act0test"}),
                _reader(entries))
        self.assertIn("records no doc leg", str(caught.exception))


class TheWaitGateHasAProductionCaller(unittest.TestCase):
    """The defect I shipped in the same commit that fixed its twin.

    I wired the trigger belt into the engine and left `assert_ready_to_freeze` as
    a library only the tests invoked. Half of AC6 — "package freeze refuses until
    each leg is terminal or independently attested" — was therefore unenforced
    while its suite was fully green, which is precisely the failure A148 caught
    on the other half and precisely what memory pin a2ef8240 describes.

    Found by self-review before the reviewer had to, using the question that pin
    tells me to ask: does anything in production actually CALL this?
    """

    ENGINE = TOOLS / "9e7003b1.py"

    def test_the_engine_invokes_the_gate_not_merely_the_library(self) -> None:
        source = self.ENGINE.read_text(encoding="utf-8")
        self.assertIn("_assert_release_legs_settled(", source)
        body = source[source.index("def action_step_complete("):]
        body = body[: body.index("\ndef ", 1)]
        self.assertIn("_assert_release_legs_settled(", body,
                      "the wait gate is defined but action_step_complete never "
                      "calls it — a helper nobody calls is not a gate")

    def test_the_gate_reaches_assert_ready_to_freeze(self) -> None:
        """The call chain, end to end in source. A caller that invokes a
        different function than the one under test would satisfy the check
        above and enforce nothing."""
        source = self.ENGINE.read_text(encoding="utf-8")
        body = source[source.index("def _assert_release_legs_settled("):]
        body = body[: body.index("\ndef ", 1)]
        self.assertIn("assert_ready_to_freeze", body)

    def test_the_gate_is_scoped_to_the_wait_step_on_a_release_run(self) -> None:
        """A gate on every step of every run is the cost deb77758 warns about.

        Both guards must be present, or completing any dev step would consult
        release legs that do not exist.
        """
        source = self.ENGINE.read_text(encoding="utf-8")
        body = source[source.index("def _assert_release_legs_settled("):]
        body = body[: body.index("\ndef ", 1)]
        self.assertIn("RELEASE_WAIT_STEP_UID", body)
        self.assertIn("RELEASE_PIPELINE_ROOT_UID", body)

    def test_leg_records_are_read_from_the_RUNS_events(self) -> None:
        """AC6 moves the legs onto the release graph, so the release run owns
        them — not the dev-spec frontmatter the v1 trigger wrote to."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("eng", self.ENGINE)
        eng = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eng)

        events = [
            {"event": "triggered", "data": {"pipeline_class": "doc-pipeline",
                                            "triggered_activation_uid": "ac700d0c"}},
            {"event": "triggered", "data": {"pipeline_class": "test-pipeline",
                                            "triggered_activation_uid": "ac700e57"}},
        ]
        records = eng._release_leg_records(events)
        self.assertEqual(records["doc"]["activation_uid"], "ac700d0c")
        self.assertEqual(records["test"]["activation_uid"], "ac700e57")

    def test_an_attestation_recorded_on_the_run_is_picked_up(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("eng", self.ENGINE)
        eng = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eng)

        events = [{"event": "leg_attested",
                   "data": {"attested_leg": "doc", "attestation_uid": "a77e5701"}}]
        self.assertEqual(eng._release_leg_records(events)["doc"]["attestation_uid"],
                         "a77e5701")

    def test_real_step_complete_changes_verdict_when_the_weld_is_removed(self) -> None:
        """A148 independent review: production entry point + mutation.

        Source reachability is useful, but it cannot prove the caller changes
        runtime behavior. Drive `action_step_complete` with an incomplete leg,
        then remove only the weld in-memory and require the same call to proceed.
        If both calls have the same verdict, AC6 is green for another reason.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location("eng_ac6_weld", self.ENGINE)
        eng = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eng)

        step_uid = eng.RELEASE_WAIT_STEP_UID
        events = [
            {"event": "triggered",
             "data": {"pipeline_class": "doc-pipeline",
                      "triggered_activation_uid": "ac700d0c"}},
            {"event": "triggered",
             "data": {"pipeline_class": "test-pipeline",
                      "triggered_activation_uid": "ac700e57"}},
        ]
        entries = {
            "ac700d0c": {"frontmatter": {"status": "active"}},
            "ac700e57": {"frontmatter": {"status": "done"}},
        }
        run = {"frontmatter": {"uid": RUN, "pipeline": RELEASE_ROOT}}
        state = {"step_status": {step_uid: "started"}}

        eng.load_run = lambda *_a, **_k: ({}, run, Path("/tmp/ac6-review"), events, state)
        eng.read_vault_entry = lambda uid: entries.get(uid)
        eng.find_event_span = lambda *_a, **_k: {"span_id": "review-parent"}
        eng.get_step_declarations = lambda _events: {}

        with self.assertRaises(legs.LegRefusal) as caught:
            eng.action_step_complete("ac700001", step_uid, [], "argus-a148",
                                     dry_run=True)
        self.assertIn("package freeze refused", str(caught.exception))

        original_weld = eng._assert_release_legs_settled
        try:
            eng._assert_release_legs_settled = lambda *_a, **_k: None
            report = eng.action_step_complete(
                "ac700001", step_uid, [], "argus-a148", dry_run=True)
        finally:
            eng._assert_release_legs_settled = original_weld

        self.assertIn("step-complete", report)

    def test_real_step_complete_positive_control_opens_after_both_legs_settle(self) -> None:
        """The real entry point is usable, not merely a refusal machine."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("eng_ac6_control", self.ENGINE)
        eng = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eng)

        step_uid = eng.RELEASE_WAIT_STEP_UID
        events = [
            {"event": "triggered",
             "data": {"pipeline_class": "doc-pipeline",
                      "triggered_activation_uid": "ac700d0c"}},
            {"event": "triggered",
             "data": {"pipeline_class": "test-pipeline",
                      "triggered_activation_uid": "ac700e57"}},
        ]
        entries = {
            "ac700d0c": {"frontmatter": {"status": "done"}},
            "ac700e57": {"frontmatter": {"status": "closed"}},
        }
        run = {"frontmatter": {"uid": RUN, "pipeline": RELEASE_ROOT}}
        state = {"step_status": {step_uid: "started"}}

        eng.load_run = lambda *_a, **_k: ({}, run, Path("/tmp/ac6-control"), events, state)
        eng.read_vault_entry = lambda uid: entries.get(uid)
        eng.find_event_span = lambda *_a, **_k: {"span_id": "control-parent"}
        eng.get_step_declarations = lambda _events: {}

        report = eng.action_step_complete(
            "ac700001", step_uid, [], "argus-a148", dry_run=True)
        self.assertIn("step-complete", report)


class AttestationIsFirstClass(unittest.TestCase):
    """Not a bypass. A gate with no honest path for legitimately-skipped work is
    a gate the crew learns to route around."""

    def test_an_attested_leg_settles_the_same_as_a_terminal_one(self) -> None:
        entries = {"a77e5701": _attestation(),
                   "act0test": {"frontmatter": {"status": "done"}}}
        states = legs.assert_ready_to_freeze(
            RUN,
            {"doc": {"attestation_uid": "a77e5701"},
             "test": {"activation_uid": "act0test"}},
            _reader(entries))
        self.assertEqual(sorted(s.basis for s in states), ["attested", "terminal"])

    def test_an_attestation_naming_another_run_is_refused(self) -> None:
        """The dangerous case: it resolves, it is typed, and it attests to
        different work."""
        entries = {"a77e5701": _attestation(release_pipeline_run_uid="0bb0ffff")}
        with self.assertRaises(legs.LegRefusal) as caught:
            legs.resolve_leg("doc", RUN, {"attestation_uid": "a77e5701"},
                             _reader(entries))
        self.assertIn("attests to other work", str(caught.exception))

    def test_an_attestation_for_another_leg_is_refused(self) -> None:
        entries = {"a77e5701": _attestation(leg="test")}
        with self.assertRaises(legs.LegRefusal):
            legs.resolve_leg("doc", RUN, {"attestation_uid": "a77e5701"},
                             _reader(entries))

    def test_an_untyped_attestation_is_refused(self) -> None:
        """One evidence language for "done enough to freeze" (argus-a148
        answer 1). An arbitrary note carries no verdict."""
        entries = {"a77e5701": _attestation(type="note")}
        with self.assertRaises(legs.LegRefusal) as caught:
            legs.resolve_leg("doc", RUN, {"attestation_uid": "a77e5701"},
                             _reader(entries))
        self.assertIn(legs.ATTESTATION_TYPE, str(caught.exception))

    def test_every_binding_is_load_bearing(self) -> None:
        for field in legs.ATTESTATION_FIELDS:
            with self.subTest(dropped=field):
                body = _attestation()
                body["frontmatter"].pop(field)
                with self.assertRaises(legs.LegRefusal) as caught:
                    legs.resolve_leg("doc", RUN, {"attestation_uid": "a77e5701"},
                                     _reader({"a77e5701": body}))
                self.assertIn(field, str(caught.exception))

    def test_an_attestation_with_no_tested_tree_is_refused(self) -> None:
        entries = {"a77e5701": _attestation(tested_commit_sha="HEAD")}
        with self.assertRaises(legs.LegRefusal) as caught:
            legs.resolve_leg("doc", RUN, {"attestation_uid": "a77e5701"},
                             _reader(entries))
        self.assertIn("not a 40-hex commit", str(caught.exception))

    def test_a_missing_attestation_entry_is_refused(self) -> None:
        with self.assertRaises(legs.LegRefusal) as caught:
            legs.resolve_leg("doc", RUN, {"attestation_uid": "a77e5701"},
                             _reader({}))
        self.assertIn("does not resolve", str(caught.exception))

    def test_the_resolved_state_records_WHICH_basis_allowed_the_freeze(self) -> None:
        """"Both legs terminal" and "one attested" are different facts, and a
        release should be able to say which it froze on."""
        entries = {"a77e5701": _attestation(),
                   "act0test": {"frontmatter": {"status": "done"}}}
        states = legs.assert_ready_to_freeze(
            RUN,
            {"doc": {"attestation_uid": "a77e5701"},
             "test": {"activation_uid": "act0test"}},
            _reader(entries))
        by_leg = {s.leg: s for s in states}
        self.assertEqual(by_leg["doc"].attestation_uid, "a77e5701")
        self.assertEqual(by_leg["test"].activation_uid, "act0test")


if __name__ == "__main__":
    unittest.main()
