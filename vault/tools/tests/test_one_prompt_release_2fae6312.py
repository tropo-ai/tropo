"""v1.89 one-prompt release — saga state machine (dev-spec 2fae6312, locked).

Commit 1 covers `release_saga`: deterministic identity, the closed checkpoint
enum, dependency ordering, and the observe/intent/act/verify protocol. Every
case drives the production entry point; the observers and actors are fakes
because the module deliberately owns no provider clients, but the ordering,
idempotency and refusal decisions under test are the real ones.

Step 4 adds the graph half at the end of this file: the freeze node and the
edges around it. Those assertions are about the resolved graph rather than
about prose, because this chain has already been wrong twice in ways prose
could not catch.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(STUDIO_ROOT / "vault" / "tools"))

from lib import release_saga as rs  # noqa: E402


class _World:
    """A fake world: absent until acted on, then present. Records every act."""

    def __init__(self, fact=None, conflict=None, present=False):
        self.present = present
        self.fact = fact if fact is not None else {"sha": "abc123"}
        self.conflict = conflict
        self.acts = 0
        self.observations = 0

    def observe(self) -> rs.Observation:
        self.observations += 1
        return rs.Observation(
            present=self.present,
            fact=self.fact if self.present else None,
            conflict=self.conflict,
        )

    def act(self):
        self.acts += 1
        self.present = True
        return self.fact


class SagaIdentityTests(unittest.TestCase):
    def test_the_saga_id_is_derived_not_minted(self) -> None:
        self.assertEqual(rs.saga_id_for("070b6885"), "release:070b6885")
        self.assertEqual(rs.saga_id_for("070b6885"), rs.saga_id_for("070b6885"))

    def test_a_run_without_a_uid_cannot_open_a_saga(self) -> None:
        for empty in ("", "   ", None):
            with self.assertRaises(rs.ReleaseSagaError):
                rs.saga_id_for(empty)

    def test_two_runs_never_share_an_identity(self) -> None:
        self.assertNotEqual(rs.saga_id_for("070b6885"), rs.saga_id_for("934436ca"))


class CheckpointEnumTests(unittest.TestCase):
    def test_the_enum_is_closed(self) -> None:
        journal = _journal(self)
        with self.assertRaises(rs.ReleaseSagaError) as caught:
            rs.run_checkpoint(
                "publish_to_wherever", journal=journal, context={},
                observe=lambda: rs.Observation(present=False), act=lambda: None,
            )
        self.assertIn("unregistered checkpoint", str(caught.exception))

    def test_every_checkpoint_declares_a_named_incomplete_state(self) -> None:
        for checkpoint in rs.CHECKPOINTS:
            self.assertTrue(checkpoint.incomplete_state, checkpoint.checkpoint_id)
            self.assertNotIn(" ", checkpoint.incomplete_state)

    def test_dependencies_resolve_and_never_cycle(self) -> None:
        seen = set()
        for checkpoint in rs.CHECKPOINTS:
            for dependency in checkpoint.depends_on:
                self.assertIn(dependency, rs.CHECKPOINTS_BY_ID, dependency)
                self.assertIn(
                    dependency, seen,
                    "{} depends on {}, which is declared later".format(
                        checkpoint.checkpoint_id, dependency),
                )
            seen.add(checkpoint.checkpoint_id)

    def test_an_idempotency_key_refuses_to_guess_missing_context(self) -> None:
        checkpoint = rs.CHECKPOINTS_BY_ID["github_asset"]
        self.assertEqual(
            checkpoint.idempotency_key({"tag": "v1.89.0", "package_sha": "deadbeef"}),
            "gh-asset:v1.89.0:deadbeef",
        )
        with self.assertRaises(rs.ReleaseSagaError):
            checkpoint.idempotency_key({"tag": "v1.89.0"})


def _journal(case, saga="release:070b6885") -> rs.SagaJournal:
    tmp = tempfile.mkdtemp(prefix="t44-saga-")
    case.addCleanup(shutil.rmtree, tmp, True)
    return rs.SagaJournal.open(Path(tmp) / "run.jsonl", saga)


class ObserveIntentActVerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.journal = _journal(self)
        self.context = {"parent": "p1", "version": "1.89.0", "size": "10"}

    def _prepare(self, world: _World):
        return rs.run_checkpoint(
            "site_prepare", journal=self.journal, context=self.context,
            observe=world.observe, act=world.act,
        )

    def test_an_absent_fact_is_acted_on_once_and_verified(self) -> None:
        world = _World()
        result = self._prepare(world)
        self.assertEqual(result.outcome, rs.OUTCOME_ACTED)
        self.assertEqual(world.acts, 1)
        self.assertGreaterEqual(world.observations, 2, "verification re-reads the world")
        self.assertEqual(result.fact, {"sha": "abc123"})

    def test_intent_is_recorded_before_the_act(self) -> None:
        world = _World()
        self._prepare(world)
        events = [json.loads(l) for l in self.journal.path.read_text().splitlines()]
        kinds = [e["event"] for e in events]
        self.assertEqual(kinds, [rs.INTENT_EVENT, rs.OBSERVED_EVENT])

    def test_a_present_fact_is_never_acted_on_again(self) -> None:
        world = _World(present=True)
        result = self._prepare(world)
        self.assertEqual(result.outcome, rs.OUTCOME_ALREADY_PRESENT)
        self.assertEqual(world.acts, 0, "an outward act must not repeat")
        self.assertEqual(self.journal.intents("site_prepare"), [],
                         "no intent is recorded for an act that is not performed")

    def test_replay_after_a_completed_step_performs_nothing(self) -> None:
        world = _World()
        self._prepare(world)
        self._prepare(world)
        self.assertEqual(world.acts, 1, "replay must not duplicate the outward act")

    def test_a_crash_between_act_and_verification_is_recovered_not_repeated(self) -> None:
        # The world holds the fact but the journal never recorded it: exactly
        # the state a process loss leaves behind. Replay must adopt the fact.
        world = _World()
        world.act()          # the act happened
        world.acts = 0       # but nothing was journalled
        result = self._prepare(world)
        self.assertEqual(result.outcome, rs.OUTCOME_ALREADY_PRESENT)
        self.assertEqual(world.acts, 0, "the act must not be performed twice")

    def test_a_conflict_refuses_and_never_overwrites(self) -> None:
        world = _World(conflict="remote holds an unexpected SHA")
        result = self._prepare(world)
        self.assertEqual(result.outcome, rs.OUTCOME_REFUSED)
        self.assertEqual(world.acts, 0)
        self.assertEqual(result.incomplete_state, "site-prepare-pending")

    def test_an_observation_failure_is_operational_not_a_refusal(self) -> None:
        def boom():
            raise OSError("provider unreachable")

        result = rs.run_checkpoint(
            "site_prepare", journal=self.journal, context=self.context,
            observe=boom, act=lambda: None,
        )
        self.assertEqual(result.outcome, rs.OUTCOME_OPERATIONAL_ERROR)
        self.assertIn("provider unreachable", result.detail)

    def test_an_act_that_does_not_change_the_world_is_not_reported_as_done(self) -> None:
        world = _World()
        world.act = lambda: None  # claims success, changes nothing
        result = rs.run_checkpoint(
            "site_prepare", journal=self.journal, context=self.context,
            observe=world.observe, act=world.act,
        )
        self.assertEqual(result.outcome, rs.OUTCOME_OPERATIONAL_ERROR)
        self.assertIn("does not show the fact", result.detail)
        self.assertIsNone(self.journal.observed("site_prepare"))


class DependencyOrderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.journal = _journal(self)

    def test_a_step_blocks_on_an_unverified_dependency(self) -> None:
        world = _World()
        result = rs.run_checkpoint(
            "git_refs", journal=self.journal, context={"staged_sha": "abc"},
            observe=world.observe, act=world.act,
        )
        self.assertEqual(result.outcome, rs.OUTCOME_BLOCKED)
        self.assertEqual(world.acts, 0, "a blocked step performs no outward act")
        self.assertIn("site_prepare", result.detail)

    def test_the_first_actionable_checkpoint_is_the_first_unverified_one(self) -> None:
        self.assertEqual(rs.next_checkpoint(self.journal).checkpoint_id, "site_prepare")
        world = _World()
        rs.run_checkpoint(
            "site_prepare", journal=self.journal,
            context={"parent": "p", "version": "v", "size": "1"},
            observe=world.observe, act=world.act,
        )
        self.assertEqual(rs.next_checkpoint(self.journal).checkpoint_id, "git_refs")

    def test_state_names_the_exact_pending_checkpoint(self) -> None:
        state = rs.current_state(self.journal)
        self.assertFalse(state["complete"])
        self.assertEqual(state["state"], "site-prepare-pending")
        self.assertEqual(state["completed"], [])

        world = _World()
        rs.run_checkpoint(
            "site_prepare", journal=self.journal,
            context={"parent": "p", "version": "v", "size": "1"},
            observe=world.observe, act=world.act,
        )
        state = rs.current_state(self.journal)
        self.assertEqual(state["completed"], ["site_prepare"])
        self.assertEqual(state["state"], "primary-refs-pending")

    def test_completion_requires_every_checkpoint(self) -> None:
        context = {
            "parent": "p", "version": "1.89.0", "size": "1", "staged_sha": "s",
            "tag": "v1.89.0", "package_sha": "pkg", "release_uid": "rel",
            "site_commit": "site", "run_uid": "070b6885", "receipt_sha": "rcpt",
            "mode": "rehearsal", "scorecard_sha": "score998877",
        }
        for checkpoint in rs.CHECKPOINTS:
            world = _World()
            result = rs.run_checkpoint(
                checkpoint.checkpoint_id, journal=self.journal, context=context,
                observe=world.observe, act=world.act,
            )
            self.assertTrue(result.ok, "{}: {}".format(checkpoint.checkpoint_id, result.detail))
        state = rs.current_state(self.journal)
        self.assertTrue(state["complete"], state)
        self.assertEqual(state["state"], "complete")
        self.assertEqual(len(state["completed"]), len(rs.CHECKPOINTS))


class JournalTests(unittest.TestCase):
    def test_the_journal_survives_a_malformed_line(self) -> None:
        journal = _journal(self)
        journal.path.parent.mkdir(parents=True, exist_ok=True)
        journal.path.write_text("{not json\n", encoding="utf-8")
        journal.reload()
        self.assertEqual(journal.completed_checkpoints(), [])

    def test_another_sagas_entries_are_not_adopted(self) -> None:
        # Two runs writing one file must not read each other's progress as
        # their own; the saga id is what keeps them apart.
        journal = _journal(self, saga="release:070b6885")
        journal.append(rs.OBSERVED_EVENT, "site_prepare", outcome=rs.OUTCOME_ACTED)
        other = rs.SagaJournal.open(journal.path, "release:934436ca")
        self.assertEqual(other.completed_checkpoints(), [])
        self.assertEqual(journal.completed_checkpoints(), ["site_prepare"])


# ---------------------------------------------------------------------------
# Step 4 — the freeze node and the edges around it.
# ---------------------------------------------------------------------------

FILES = STUDIO_ROOT / "vault" / "files"

FREEZE = "7de2c49f"
VERIFY_STAGE = "8a4f802b"
PUBLISH_STAGE = "8e03f8d6"
PUBLISH_STEP = "3dd817cb"
COLD_WALK = "c6b61fb9"

#: The four declared instruments, in chain order.
INSTRUMENTS = ("4262d5fa", "a0f2bea8", "bc6b17ec", "c6b61fb9")


def frontmatter(uid: str) -> str:
    text = (FILES / f"{uid}.md").read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    assert match, f"{uid} has no frontmatter"
    return match.group(1)


def body(uid: str) -> str:
    return (FILES / f"{uid}.md").read_text(encoding="utf-8")


def scalar(uid: str, key: str) -> str:
    match = re.search(r"^%s:[ \t]*(.+)$" % re.escape(key), frontmatter(uid), re.M)
    return match.group(1).strip().strip("'\"") if match else ""


def uid_list(uid: str, key: str) -> list:
    """A YAML list of 8-hex UIDs under `key`, or [] when absent/empty."""
    match = re.search(
        r"^%s:[ \t]*\n((?:[ \t]+-[ \t]*\S+\n)*)" % re.escape(key),
        frontmatter(uid),
        re.M,
    )
    if not match:
        return []
    return re.findall(r"-[ \t]*'?\"?([0-9a-f]{8})", match.group(1))


class FreezeNodeExistsTests(unittest.TestCase):
    def test_the_node_is_where_the_spec_pre_assigned_it(self):
        self.assertTrue(
            (FILES / f"{FREEZE}.md").is_file(),
            "dev-spec 2fae6312 pre-assigns this UID; the node belongs at that path",
        )
        self.assertEqual(scalar(FREEZE, "type"), "pipeline")
        self.assertEqual(scalar(FREEZE, "subtype"), "workflow-node")
        self.assertEqual(scalar(FREEZE, "role"), "step")
        self.assertEqual(scalar(FREEZE, "name"), "release-freeze-verified-package")

    def test_it_is_built_under_the_locked_spec(self):
        self.assertEqual(scalar(FREEZE, "built_under"), "2fae6312")

    def test_it_is_machine_verifiable(self):
        """A re-hash and a receipt count admit no judgement."""
        self.assertEqual(scalar(FREEZE, "verification_class"), "true")
        self.assertEqual(scalar(FREEZE, "trust_level"), "auto-with-verification")


class ChainOrderTests(unittest.TestCase):
    def test_the_verify_stage_claims_the_freeze_node(self):
        """Claimed, not merely pointed at.

        The stage's own rehome note records why this assertion exists: graph
        resolution follows `children`, so a node reachable only through
        `next_steps` is never walked. Four instruments once sat in this stage
        with two of them claimed.
        """
        children = uid_list(VERIFY_STAGE, "children")
        self.assertIn(FREEZE, children)
        for instrument in INSTRUMENTS:
            self.assertIn(instrument, children)
        self.assertEqual(
            children.index(FREEZE),
            max(children.index(i) for i in INSTRUMENTS) + 1,
            "the freeze must be claimed after all four instruments",
        )

    def test_the_freeze_follows_the_fourth_instrument(self):
        self.assertEqual(uid_list(FREEZE, "depends_on_steps"), [COLD_WALK])

    def test_the_fourth_instrument_hands_to_the_freeze(self):
        self.assertEqual(uid_list(COLD_WALK, "next_steps"), [FREEZE])

    def test_publication_depends_on_the_freeze_not_the_cold_walk(self):
        """The regression guard for the exact defect this node closes.

        While publish depended directly on the cold walk, a package could be
        verified, quietly rebuilt, and published, with four passing receipts in
        the run describing bytes nobody shipped.
        """
        depends = uid_list(PUBLISH_STEP, "depends_on_steps")
        self.assertEqual(depends, [FREEZE])
        self.assertNotIn(
            COLD_WALK,
            depends,
            "publication may not be eligible straight off the cold walk",
        )

    def test_the_freeze_hands_to_publication(self):
        self.assertEqual(uid_list(FREEZE, "next_steps"), [PUBLISH_STAGE])

    def test_no_path_reaches_publication_without_passing_the_freeze(self):
        """Every declared route into the publish step goes through the freeze."""
        upstream = uid_list(PUBLISH_STEP, "depends_on_steps")
        self.assertEqual(
            [u for u in upstream if u != FREEZE],
            [],
            "an alternate route into publication would make the freeze optional",
        )


class FreezeContractTests(unittest.TestCase):
    def test_the_evidence_contract_requires_a_receipt_per_instrument(self):
        """Each instrument must be a key in `instrument_receipts`.

        Asserting the UID appears anywhere in the file is not this claim — the
        chain diagram alone would satisfy it, and did, until a mutation that
        dropped an instrument from the contract left the suite green.
        """
        contract = re.search(
            r'"instrument_receipts":\s*\{(.*?)\n  \}', body(FREEZE), re.S
        )
        self.assertIsNotNone(
            contract, "the freeze declares no instrument_receipts contract"
        )
        keys = re.findall(r'"([0-9a-f]{8})"\s*:', contract.group(1))
        self.assertEqual(
            sorted(keys),
            sorted(INSTRUMENTS),
            "the receipts the freeze proves must be exactly the four declared "
            "instruments — three passing and one absent is a fail, not a rounding "
            "error",
        )

    def test_the_binding_tuple_is_stated(self):
        """Receipts bind to bytes, not merely to the run."""
        text = body(FREEZE)
        self.assertIn("candidate_sha256", text)
        self.assertIn("run_uid", text)

    def test_invalidation_and_supersession_stay_distinct(self):
        text = body(FREEZE)
        self.assertIn("tropo.release.candidate_invalidated", text)
        self.assertIn("tropo.release.package_superseded", text)
        self.assertIn("tropo.release.package_frozen", text)

    def test_the_verdict_has_a_runnable_source(self):
        """Check 20: a vc:true step with no verdict source attests to itself.

        The node landed without one and the validator caught it the same day.
        The command it now names must exist and be runnable, not aspirational.
        """
        command = scalar(FREEZE, "verification_command")
        self.assertTrue(command, "vc:true step declares no verification_command")

        import shlex

        parts = shlex.split(command)
        self.assertTrue(parts, "the command is empty after parsing")
        script = next((p for p in parts if p.endswith(".py")), None)
        self.assertIsNotNone(script, command)
        self.assertTrue(
            (STUDIO_ROOT / script).is_file(),
            f"{script} is named as the verdict source but does not exist",
        )

    def test_the_capsule_stamp_matches_the_bound_capsule(self):
        capsule = (
            STUDIO_ROOT / "vault" / "capsules" / "tropo-pipeline.capsule.md"
        ).read_text()
        bound = re.search(r"^version:[ \t]*'?([\d.]+)", capsule, re.M).group(1)
        self.assertEqual(
            scalar(FREEZE, "capsule_version"),
            bound,
            "a new node meets current capsule law, whatever its older siblings carry",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ===========================================================================
# The locked AC verify targets (2fae6312 §Acceptance).
#
# A150's ruling, 2026-08-17: the spec's verify commands are the authority, so
# these class names are not negotiable and each must OWN the production-door
# evidence its AC claims. Shared fixtures are fine; the assertions and the
# failure plants are local, because a class that merely invokes another green
# suite proves that suite runs, not that this AC holds.
#
# I built the coverage first under my own module names and never read the
# verify commands as a contract. Eight of ten named targets did not exist, so
# no AC could be run as written. These classes close that.
# ===========================================================================

import importlib.util as _ilu  # noqa: E402

_TOOLS = STUDIO_ROOT / "vault" / "tools"


def _load_tool(name: str, alias: str):
    """Load a hyphenated production tool by path. Shared fixture, not evidence."""
    spec = _ilu.spec_from_file_location(alias, _TOOLS / name)
    module = _ilu.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


class GatePhaseTests(unittest.TestCase):
    """AC1 — a gate runs at its earliest truthful boundary, never later.

    The production doors are lib.release_gates and tropo-release-preflight.py.
    """

    @classmethod
    def setUpClass(cls):
        from lib import release_gates as rg

        cls.rg = rg
        cls.cli = _load_tool("tropo-release-preflight.py", "ac1_preflight")

    def test_the_phase_is_computed_from_inputs_not_declared(self):
        gate = self.rg.Gate(
            "mixed", "test", ("release_plan", "candidate_bytes"),
            lambda ctx: self.rg.GateOutcome("mixed", self.rg.VERDICT_PASS),
        )
        self.assertEqual(gate.first_evaluable_phase, "candidate")
        with self.assertRaises(TypeError):
            self.rg.Gate(
                "wishful", "test", ("release_plan",),
                lambda ctx: None, first_evaluable_phase="post-publication-reconcile",
            )

    def test_a_gate_cannot_invent_an_input_to_choose_its_boundary(self):
        with self.assertRaises(self.rg.ReleaseGateError) as caught:
            self.rg.Gate("smuggler", "test", ("a_convenient_late_fact",),
                         lambda ctx: None)
        self.assertIn("unknown release input", str(caught.exception))

    def test_revalidation_cannot_precede_the_inputs(self):
        with self.assertRaises(self.rg.ReleaseGateError):
            self.rg.Gate(
                "early", "test", ("frozen_package",),
                lambda ctx: self.rg.GateOutcome("early", self.rg.VERDICT_PASS),
                mandatory_revalidation_phase="lock-static",
            )

    def test_a_registered_gate_no_phase_reaches_is_reported(self):
        registry = self.rg.GateRegistry()
        registry.register(self.rg.Gate(
            "late", "test", ("frozen_package",),
            lambda ctx: self.rg.GateOutcome("late", self.rg.VERDICT_PASS)))
        self.assertEqual(
            [g.gate_id for g in registry.unreached_gates(["lock-static"])], ["late"])

    def test_the_preflight_cli_keeps_refusal_and_operational_distinct(self):
        """Local plant: a violating shipped tool, then a raising verifier."""
        clean = Path(tempfile.mkdtemp(prefix="ac1-clean-"))
        self.addCleanup(shutil.rmtree, clean, True)
        (clean / "vault" / "tools").mkdir(parents=True)
        header = ('#!/usr/bin/env python3\n"""---\nuid: deadbeef\ntype: tool\n'
                  'status: active\nextraction_scope: ship\n---\n"""\n')
        (clean / "vault" / "tools" / "tropo-probe.py").write_text(
            header + "\nfrom __future__ import annotations\n\n\ndef p(v: str | None = None):\n    return v\n",
            encoding="utf-8")
        self.assertEqual(
            self.cli.main(["--phase", "lock-static", "--vault", str(clean)]),
            self.cli.EXIT_OK)

        dirty = Path(tempfile.mkdtemp(prefix="ac1-dirty-"))
        self.addCleanup(shutil.rmtree, dirty, True)
        (dirty / "vault" / "tools").mkdir(parents=True)
        (dirty / "vault" / "tools" / "tropo-probe.py").write_text(
            header + "\n\ndef p(v: str | None = None):\n    return v\n", encoding="utf-8")
        self.assertEqual(
            self.cli.main(["--phase", "lock-static", "--vault", str(dirty)]),
            self.cli.EXIT_REFUSED)

        registry = self.rg.GateRegistry()

        def explode(_ctx):
            raise TimeoutError("provider did not answer")

        registry.register(self.rg.Gate("flaky", "provider", ("release_plan",), explode))
        outcome = registry.run_phase("lock-static", {"release_plan": "p"})[0]
        self.assertEqual(outcome.failure_kind, self.rg.FAILURE_OPERATIONAL)
        self.assertNotEqual(self.cli.EXIT_REFUSED, self.cli.EXIT_OPERATIONAL)


class EvidenceBeforeFreezeTests(unittest.TestCase):
    """AC2 — the freeze follows its evidence, and re-checks the bytes."""

    @classmethod
    def setUpClass(cls):
        cls.freeze = _load_tool(
            "tropo-freeze-release-candidate.py", "ac2_freeze")
        cls.release_verify = _load_tool("lib/release_verify.py", "ac2_release_verify")

    def build(self, *, receipts=None, invalidate=False, frozen=False,
              mutate=False) -> Path:
        import hashlib

        tmp = Path(tempfile.mkdtemp(prefix="ac2-freeze-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        candidate = tmp / "pkg.zip"
        candidate.write_bytes(b"candidate bytes")
        sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
        rows = [
            {"event": "tropo.release.scope_locked",
             "data": {"saga_id": "release:934436ca", "pipeline_run_uid": "934436ca"}},
            {"event": "tropo.release.candidate_built",
             "data": {"pipeline_run_uid": "934436ca", "candidate_sha256": sha,
                      "candidate_path": str(candidate)}},
        ]
        # v1.91 S2 (3fb41c99): the REAL shape release-verification-receipt
        # writes, per Argus A155's ruling -- not the generic dev-pipeline
        # verification_receipt name it collided with.
        for step in (receipts if receipts is not None else list(self.freeze.INSTRUMENTS)):
            rows.append({"event": self.release_verify.RECEIPT_KIND,
                         "data": {"receipt_kind": self.release_verify.RECEIPT_KIND,
                                  "instrument": self.freeze.INSTRUMENTS[step],
                                  "release_run_uid": "934436ca",
                                  "candidate_sha256": sha, "verdict": "pass",
                                  "executor_or_attester": "test",
                                  "execution_mode": "machine",
                                  "evidence_ref": step,
                                  "started_at": "2026-08-23T00:00:00Z",
                                  "completed_at": "2026-08-23T00:00:00Z"}})
        if invalidate:
            rows.append({"event": "tropo.release.candidate_invalidated",
                         "data": {"candidate_sha256": sha, "reason": "prose fix"}})
        if frozen:
            rows.append({"event": "tropo.release.package_frozen",
                         "data": {"package_sha256": sha}})
        (tmp / "run.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        if mutate:
            candidate.write_bytes(b"candidate bytes, edited after the walk")
        return tmp

    def test_four_receipts_on_unchanged_bytes_earn_the_freeze(self):
        run = self.build()
        payload, refusal = self.freeze.decide(run, run / "pkg.zip")
        self.assertIsNone(refusal)
        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual(len(payload["instrument_receipts"]), 4)

    def test_a_byte_change_after_the_instruments_ran_refuses(self):
        run = self.build(mutate=True)
        _payload, refusal = self.freeze.decide(run, run / "pkg.zip")
        self.assertIn("recorded", refusal)

    def test_three_receipts_is_a_fail_not_a_rounding_error(self):
        for absent in self.freeze.INSTRUMENTS:
            with self.subTest(absent=absent):
                run = self.build(
                    receipts=[u for u in self.freeze.INSTRUMENTS if u != absent])
                _p, refusal = self.freeze.decide(run, run / "pkg.zip")
                # v1.91 S2 (3fb41c99): the shared resolver names the
                # INSTRUMENT, not the step uid (Argus A155's ruling part 5).
                self.assertIn(self.freeze.INSTRUMENTS[absent], refusal)

    def test_a_live_invalidation_blocks_the_freeze(self):
        run = self.build(invalidate=True)
        _p, refusal = self.freeze.decide(run, run / "pkg.zip")
        self.assertIn("invalidation", refusal)

    def test_a_second_freeze_is_a_supersession(self):
        run = self.build(frozen=True)
        _p, refusal = self.freeze.decide(run, run / "pkg.zip")
        self.assertIn("supersession", refusal)

    def test_the_freeze_node_names_a_runnable_verdict_source(self):
        command = scalar(FREEZE, "verification_command")
        self.assertTrue(command)
        script = next(p for p in command.split() if p.endswith(".py"))
        self.assertTrue((STUDIO_ROOT / script).is_file())


class SiteTargetSagaTests(unittest.TestCase):
    """AC3 — pinned identity, bounded diff, CAS-only push, observed endpoint."""

    @classmethod
    def setUpClass(cls):
        from lib import release_site as rs_site

        cls.site = rs_site

    def test_a_redirect_refuses_rather_than_being_followed(self):
        verdict = self.site.assert_pinned_identity(
            self.site.SITE_REPO, redirected_to="https://github.com/x/old.git")
        self.assertEqual(verdict.refusal_class, self.site.REFUSAL_IDENTITY)

    def test_a_credential_never_reaches_the_record(self):
        verdict = self.site.assert_pinned_identity(
            "https://user:ghp_secret@github.com/tropo-ai/tropo-app.git")
        self.assertEqual(verdict.refusal_class, self.site.REFUSAL_CREDENTIAL)
        self.assertNotIn("ghp_secret", repr(verdict.evidence) + verdict.detail)

    def test_the_diff_is_bounded_to_the_two_declared_paths(self):
        self.assertFalse(self.site.classify_diff(
            [self.site.BADGE_TARGET, "app/page.tsx"], route_exists=True).ok)
        self.assertFalse(self.site.classify_diff(
            [self.site.BADGE_TARGET, self.site.ROUTE_TARGET], route_exists=True).ok)
        self.assertTrue(self.site.classify_diff(
            [self.site.BADGE_TARGET, self.site.ROUTE_TARGET], route_exists=False).ok)

    def test_a_moved_remote_conflicts_and_is_never_forced(self):
        verdict = self.site.decide_site_push(
            remote_sha="c" * 40, expected_parent="a" * 40, prepared_commit="b" * 40)
        self.assertEqual(verdict.refusal_class, self.site.REFUSAL_CONFLICT)
        for remote in ("a" * 40, "b" * 40, "c" * 40):
            self.assertNotIn("force", self.site.decide_site_push(
                remote_sha=remote, expected_parent="a" * 40,
                prepared_commit="b" * 40).action)

    def test_the_endpoint_must_serve_exactly_this_release(self):
        good = {
            "status": 200, "final_url": self.site.SITE_ENDPOINT,
            "content_type": "application/json",
            "headers": {"cache-control": "no-store"},
            "body": {"version": "v1.89.0", "fileSize": "6.3 MB",
                     "sizeBytes": 10, "releasedAt": "2026-08-16"},
        }
        self.assertTrue(self.site.verify_endpoint(
            good, expected_version="v1.89.0", expected_size_bytes=10).ok)
        stale = json.loads(json.dumps(good))
        stale["body"]["version"] = "v1.88.0"
        self.assertFalse(self.site.verify_endpoint(
            stale, expected_version="v1.89.0", expected_size_bytes=10).ok)
        extra = json.loads(json.dumps(good))
        extra["body"]["schema"] = "tropo.os-release/v1"
        self.assertFalse(self.site.verify_endpoint(
            extra, expected_version="v1.89.0", expected_size_bytes=10).ok)

    def test_the_route_serves_exactly_the_four_fields(self):
        route = STUDIO_ROOT / "tropo-app" / "app" / "api" / "os-release" / "route.ts"
        self.assertTrue(route.is_file())
        text = route.read_text(encoding="utf-8")
        declared = re.search(r"SERVED_FIELDS\s*=\s*\[(.*?)\]", text, re.S)
        self.assertEqual(sorted(re.findall(r'"(\w+)"', declared.group(1))),
                         sorted(self.site.ENDPOINT_FIELDS))
        self.assertNotIn("...parsed", text)


class ReleaseEventVocabularyTests(unittest.TestCase):
    """AC4 — the closed vocabulary, judged against observed substrate."""

    @classmethod
    def setUpClass(cls):
        from lib import release_events as re_events

        cls.ev = re_events

    ACTIVATION = "14b6540e"

    def context(self, **over):
        base = dict(activation_uid=self.ACTIVATION, pipeline_run_uid="934436ca",
                    saga_id="release:934436ca", release_entry_uid="a1b2c3d4",
                    snapshot_step_uids=frozenset({"c6b61fb9"}))
        base.update(over)
        return self.ev.AuthorizationContext(**base)

    def envelope(self, event, data, **over):
        row = {"event": event, "ts": "2026-08-16T21:00:00Z", "actor": "talos-t44",
               "data": data, "schema_version": 2, "trace_id": self.ACTIVATION,
               "span_id": "span-1", "step": None}
        row.update(over)
        return row

    def built(self, **data_over):
        data = {"saga_id": "release:934436ca", "pipeline_run_uid": "934436ca",
                "candidate_sha256": "abc", "candidate_path": "p.zip"}
        data.update(data_over)
        return self.envelope("tropo.release.candidate_built", data)

    def test_an_unregistered_event_refuses(self):
        v = self.ev.authorize(self.envelope("tropo.release.whatever", {}), self.context())
        self.assertEqual(v.refusal_class, self.ev.REFUSAL_UNREGISTERED)

    def test_a_forged_identity_refuses(self):
        v = self.ev.authorize(self.built(pipeline_run_uid="deadbeef"), self.context())
        self.assertEqual(v.refusal_class, self.ev.REFUSAL_IDENTITY)

    def test_an_extra_data_key_refuses(self):
        v = self.ev.authorize(self.built(notes="context"), self.context())
        self.assertEqual(v.refusal_class, self.ev.REFUSAL_DATA_UNKNOWN)

    def test_a_step_outside_the_snapshot_refuses(self):
        data = {"receipt_kind": "release-verification-receipt",
                "pipeline_run_uid": "934436ca", "candidate_sha256": "abc",
                "instrument": "freeze", "instrument_step_uid": "7de2c49f",
                "verdict": "pass", "evidence_sha256": "e1"}
        row = self.envelope("verification_receipt", data, step="7de2c49f")
        self.assertEqual(self.ev.authorize(row, self.context()).refusal_class,
                         self.ev.REFUSAL_STEP)

    def test_a_duplicate_terminal_refuses(self):
        frozen = self.envelope("tropo.release.package_frozen", {
            "saga_id": "release:934436ca", "pipeline_run_uid": "934436ca",
            "package_sha256": "abc", "receipt_set_sha256": "r1"})
        self.assertTrue(self.ev.authorize(frozen, self.context()).authorized)
        again = dict(frozen, span_id="span-2")
        self.assertEqual(
            self.ev.authorize(again, self.context(), [frozen]).refusal_class,
            self.ev.REFUSAL_CARDINALITY)

    def test_the_context_cannot_be_supplied_by_the_event(self):
        """Removing derived context is the mutation the AC names."""
        import inspect

        self.assertEqual(
            [p for p in inspect.signature(self.ev.AuthorizationContext.observe)
             .parameters if p != "cls"], ["run_dir"])
        self.assertEqual(list(inspect.signature(self.ev.authorize).parameters),
                         ["envelope", "context", "prior_events"])


class ReleaseLockTransactionTests(unittest.TestCase):
    """AC5 — the lock authors one correlated triangle, atomically, once.

    Shares the end-to-end module's studio fixture; every assertion here is
    local and about the lock transaction's own post-state.
    """

    @classmethod
    def setUpClass(cls):
        tests_dir = STUDIO_ROOT / "vault" / "tools" / "tests"
        if str(tests_dir) not in sys.path:
            sys.path.insert(0, str(tests_dir))
        import test_release_plan_lock_end_to_end as e2e

        cls.e2e = e2e
        cls.rl = e2e.rl

    def setUp(self):
        self.harness = self.e2e.ReleaseLockEndToEnd("run")
        self.harness.setUp()
        self.addCleanup(self.harness.tearDown)

    def _lock(self):
        code, message = self.harness._lock()
        self.assertEqual(code, 0, message)
        return self.rl.read_entry("b1a00001", self.harness.files)["frontmatter"]

    def test_the_lock_authors_the_whole_triangle(self):
        fm = self._lock()
        for key in ("release_activation_uid", "release_pipeline_run_uid",
                    "release_entry_uid", "activation_root_uid", "saga_id"):
            with self.subTest(field=key):
                self.assertTrue(fm.get(key), f"plan is missing {key} after lock")

    def test_every_named_record_exists_and_none_is_a_placeholder(self):
        fm = self._lock()
        for key in ("release_activation_uid", "release_pipeline_run_uid",
                    "release_entry_uid", "activation_root_uid"):
            uid = fm[key]
            entry = self.rl.read_entry(uid, self.harness.files)
            self.assertIsNotNone(entry, f"{key}={uid} does not resolve")
            raw = entry["raw"]
            self.assertNotIn("<<MINT:", raw)
            self.assertNotIn("TBD", raw)

    def test_the_release_entry_is_born_pre_ship(self):
        fm = self._lock()
        entry = self.rl.read_entry(fm["release_entry_uid"], self.harness.files)
        self.assertEqual(entry["frontmatter"]["status"], "pre-ship")

    def test_the_saga_id_is_derived_from_the_run(self):
        fm = self._lock()
        self.assertEqual(fm["saga_id"], f"release:{fm['release_pipeline_run_uid']}")

    def test_relocking_is_refused_not_repeated(self):
        self._lock()
        before = self.harness._snapshot()
        code, message = self.harness._lock()
        self.assertNotEqual(code, 0)
        self.assertIn("already locked", message)
        self.assertEqual(self.harness._snapshot(), before)

    def test_a_refused_lock_leaves_zero_partial_state(self):
        """Local plant: an unresolvable member, mid-plan."""
        plan = self.rl.read_entry("b1a00001", self.harness.files)
        (self.harness.files / "b1a00001.md").write_text(
            plan["raw"].replace("5ec00002", "ffffffff", 1), encoding="utf-8")
        before = self.harness._snapshot()
        code, message = self.harness._lock()
        self.assertNotEqual(code, 0, message)
        self.assertEqual(self.harness._snapshot(), before,
                         "a refused lock wrote something")


class GestureAndScorecardTests(unittest.TestCase):
    """AC7 — three gestures counted honestly, refusals graded against a baseline."""

    @classmethod
    def setUpClass(cls):
        from lib import release_metrics as rm

        cls.rm = rm
        cls.baseline = rm.load_refusal_baseline(STUDIO_ROOT)
        cls.schema = (STUDIO_ROOT / "vault" / "schema"
                      / "one-prompt-release-scorecard.schema.json")

    INPUTS = [
        {"input": "release_scope_locked", "at": "2026-08-16T20:00:00Z"},
        {"input": "release_orchestrator_invoked", "at": "2026-08-16T20:05:00Z"},
        {"input": "release_fire_authorized", "at": "2026-08-16T20:20:00Z"},
    ]
    STAMPS = {"scope_locked_at": "2026-08-16T20:00:00Z",
              "orchestrator_started_at": "2026-08-16T20:05:00Z",
              "primary_live_at": "2026-08-16T20:25:00Z",
              "all_targets_live_at": "2026-08-16T20:28:00Z"}

    def card(self, **over):
        kwargs = dict(mode=self.rm.REAL_FIRE, saga_id="release:934436ca",
                      pipeline_run_uid="934436ca", release_version="v1.89.0",
                      principal_inputs=self.INPUTS, timestamps=dict(self.STAMPS),
                      active_machine_seconds=1.0, observed_refusals=[],
                      baseline=self.baseline)
        kwargs.update(over)
        return self.rm.build_scorecard(**kwargs)

    def test_exactly_three_principal_inputs_meet_the_target(self):
        card = self.card()
        self.assertTrue(card["gestures"]["met"])
        self.assertEqual(card["verdict"], "pass")

    def test_a_manual_bridge_is_a_fourth_gesture_and_fails(self):
        card = self.card(principal_inputs=self.INPUTS + [
            {"input": "manual_resume", "at": "2026-08-16T20:22:00Z"}])
        self.assertFalse(card["gestures"]["met"])
        self.assertEqual(card["verdict"], "fail")
        # The detail has to NAME the bridge. Asserting only `met` leaves the
        # manual-input tracking untested: a fourth input already breaks the
        # count, so a mutation that stops recognising manual_resume entirely
        # still fails the boolean and survives. What it changes is the
        # explanation — and an operator reading "4 inputs, target 3" without
        # being told which one was a human rescuing the machine cannot act.
        detail = card["gestures"]["detail"]
        self.assertIn("manual_resume", detail)
        self.assertIn("did not continue on its own", detail)

    def test_machine_continuation_cannot_be_recorded_as_a_gesture(self):
        with self.assertRaises(self.rm.ReleaseMetricsError):
            self.rm.count_gestures(self.INPUTS + [
                {"input": "machine_continuation", "at": "x"}])

    def test_elapsed_and_active_time_are_separate_measures(self):
        card = self.card()
        self.assertEqual(card["elapsed"]["lock_to_all_targets_live_seconds"], 1680.0)
        self.assertEqual(card["elapsed"]["active_machine_seconds"], 1.0)

    def test_new_and_repeat_refusal_classes_are_distinguished(self):
        repeat = self.card(observed_refusals=["R188-01-latent-index-debt"] * 3)
        self.assertEqual(repeat["refusals"]["occurrences"], 3)
        self.assertEqual(repeat["refusals"]["distinct_classes"], 1)
        self.assertEqual(repeat["verdict"], "pass")
        new = self.card(observed_refusals=["R188-99-unheard-of"])
        self.assertEqual(new["refusals"]["unknown"], ["R188-99-unheard-of"])
        self.assertEqual(new["verdict"], "fail")

    def test_an_edited_baseline_refuses(self):
        """Local plant: append a class and leave the digest alone."""
        tmp = Path(tempfile.mkdtemp(prefix="ac7-baseline-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".tropo").mkdir()
        edited = json.loads(json.dumps(self.baseline))
        edited["classes"].append({"id": "R188-16-snuck-in", "retrospective_row": "x"})
        (tmp / ".tropo" / "release-refusal-baseline.json").write_text(
            json.dumps(edited), encoding="utf-8")
        with self.assertRaises(self.rm.ReleaseMetricsError):
            self.rm.load_refusal_baseline(tmp)

    def test_the_scorecard_schema_is_closed_and_every_metric_required(self):
        card = self.card()
        self.assertEqual(self.rm.validate_scorecard(card, self.schema), [])
        self.assertTrue(self.rm.validate_scorecard(dict(card, extra=1), self.schema))
        for block in ("gestures", "timestamps", "elapsed", "refusals", "verdict"):
            with self.subTest(missing=block):
                trimmed = {k: v for k, v in card.items() if k != block}
                self.assertTrue(self.rm.validate_scorecard(trimmed, self.schema))

    def test_rehearsal_and_real_fire_never_share_a_path(self):
        run = Path("/tmp/ac7")
        self.assertNotEqual(self.rm.scorecard_path(run, self.rm.REHEARSAL),
                            self.rm.scorecard_path(run, self.rm.REAL_FIRE))


class ResumableSagaTests(unittest.TestCase):
    """AC8 — resume from observed world state, and never report complete early."""

    @classmethod
    def setUpClass(cls):
        from lib import release_completion as rc

        cls.rc = rc

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ac8-saga-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.journal = rs.SagaJournal.open(self.tmp / "saga.jsonl", "release:934436ca")

    CONTEXT = {"parent": "p", "version": "1.89.0", "size": "1", "staged_sha": "s",
               "tag": "v1.89.0", "package_sha": "pkg", "release_uid": "rel",
               "site_commit": "site", "run_uid": "934436ca", "receipt_sha": "rcpt",
               "mode": "rehearsal", "scorecard_sha": "score"}

    def test_an_absent_fact_is_acted_on_once_then_observed(self):
        world = {"present": False}
        acts = []

        def observe():
            return rs.Observation(present=world["present"], fact={"x": 1})

        def act():
            world["present"] = True
            acts.append(1)
            return {"x": 1}

        first = rs.run_checkpoint("site_prepare", journal=self.journal,
                                  context=self.CONTEXT, observe=observe, act=act)
        self.assertEqual(first.outcome, rs.OUTCOME_ACTED)
        second = rs.run_checkpoint("site_prepare", journal=self.journal,
                                   context=self.CONTEXT, observe=observe, act=act)
        self.assertEqual(second.outcome, rs.OUTCOME_ALREADY_PRESENT)
        self.assertEqual(len(acts), 1, "replay performed the act a second time")

    def test_a_conflict_refuses_and_never_overwrites(self):
        def observe():
            return rs.Observation(present=False, conflict="someone else pushed")

        result = rs.run_checkpoint("site_prepare", journal=self.journal,
                                   context=self.CONTEXT, observe=observe,
                                   act=lambda: self.fail("acted through a conflict"))
        self.assertEqual(result.outcome, rs.OUTCOME_REFUSED)

    def test_a_blocked_dependency_names_the_pending_state(self):
        result = rs.run_checkpoint("git_refs", journal=self.journal,
                                   context=self.CONTEXT,
                                   observe=lambda: rs.Observation(present=False),
                                   act=lambda: self.fail("acted while blocked"))
        self.assertEqual(result.outcome, rs.OUTCOME_BLOCKED)
        self.assertEqual(result.incomplete_state, "site-prepare-pending")

    def test_completion_requires_every_bound_fact(self):
        def present(fact):
            return lambda: self.rc.FactObservation(
                fact, True, evidence_sha256=(
                    "receipt" if fact in self.rc.CO_BOUND_FACTS else "score"))

        for missing in self.rc.REQUIRED_FACTS:
            with self.subTest(missing=missing):
                obs = {f: present(f) for f in self.rc.REQUIRED_FACTS}
                obs[missing] = lambda: self.rc.FactObservation(missing, False)
                verdict = self.rc.verify_completion(
                    obs, saga_id="release:934436ca", pipeline_run_uid="934436ca")
                self.assertFalse(verdict.complete)
                self.assertIsNone(verdict.receipt)

    def test_facts_that_bind_different_receipts_refuse(self):
        def present(fact, sha):
            return lambda: self.rc.FactObservation(fact, True, evidence_sha256=sha)

        obs = {f: present(f, "same") for f in self.rc.REQUIRED_FACTS}
        obs["closed_records"] = present("closed_records", "different")
        verdict = self.rc.verify_completion(
            obs, saga_id="release:934436ca", pipeline_run_uid="934436ca")
        self.assertEqual(verdict.partial_state, self.rc.INCOHERENT_STATE)

    def test_completion_verification_is_the_terminal_checkpoint(self):
        self.assertIn("completion_verification", rs.CHECKPOINTS_BY_ID)
        for checkpoint in rs.CHECKPOINTS_BY_ID.values():
            self.assertNotIn("completion_verification", checkpoint.depends_on)
