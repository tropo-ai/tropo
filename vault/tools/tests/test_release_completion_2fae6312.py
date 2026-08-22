#!/usr/bin/env python3
"""Completion is observed, and refusing it never undoes anything.

Dev-spec 2fae6312 step 6. Two properties carry this file:

  * the verifier believes observations, not the journal, so a run that thinks
    it published but did not stays incomplete; and
  * an incomplete run reports a NAMED partial state from the spec's own
    vocabulary, because "the release broke" is not a resumable instruction.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.release_completion import (  # noqa: E402
    CO_BOUND_FACTS,
    COMPLETION_EVENT,
    INCOHERENT_STATE,
    PARTIAL_STATE_BY_FACT,
    REQUIRED_FACTS,
    FactObservation,
    ReleaseCompletionError,
    completion_receipt_sha256,
    verify_completion,
)
from lib.release_saga import CHECKPOINTS_BY_ID  # noqa: E402

SAGA = "release:934436ca"
RUN = "934436ca"


#: The one publication receipt a coherent release's facts all bind.
RECEIPT_SHA = "publication-receipt-sha"
SCORECARD_SHA = "scorecard-sha"


def default_evidence(fact: str) -> str:
    """A coherent release: the co-bound facts agree, the scorecard is its own."""
    return RECEIPT_SHA if fact in CO_BOUND_FACTS else SCORECARD_SHA


def present(fact: str, sha: str = None):
    return lambda: FactObservation(
        fact=fact, present=True, evidence_sha256=sha or default_evidence(fact)
    )


def absent(fact: str, detail: str = "not observed"):
    return lambda: FactObservation(fact=fact, present=False, detail=detail)


def all_present(**overrides):
    observers = {f: present(f) for f in REQUIRED_FACTS}
    observers.update(overrides)
    return observers


def run(observers):
    return verify_completion(observers, saga_id=SAGA, pipeline_run_uid=RUN)


class TheHappyPathTests(unittest.TestCase):
    def test_all_facts_observed_is_complete(self):
        verdict = run(all_present())
        self.assertTrue(verdict.complete)
        self.assertIsNone(verdict.partial_state)
        self.assertEqual(verdict.exit_code, 0)

    def test_the_receipt_binds_every_fact(self):
        receipt = run(all_present()).receipt
        self.assertEqual(
            sorted(receipt["verified_facts"]), sorted(REQUIRED_FACTS)
        )
        self.assertEqual(receipt["saga_id"], SAGA)
        self.assertEqual(receipt["pipeline_run_uid"], RUN)

    def test_the_receipt_hash_is_deterministic(self):
        first = run(all_present()).receipt
        second = run(all_present()).receipt
        self.assertEqual(
            first["completion_receipt_sha256"], second["completion_receipt_sha256"]
        )

    def test_a_different_fact_hash_changes_the_receipt(self):
        baseline = run(all_present()).receipt["completion_receipt_sha256"]
        altered = run(
            all_present(scorecard=present("scorecard", "a-different-scorecard"))
        ).receipt["completion_receipt_sha256"]
        self.assertNotEqual(
            baseline,
            altered,
            "the receipt does not actually bind the evidence it lists",
        )


class ObservationBeatsBeliefTests(unittest.TestCase):
    """The circularity this module exists to remove."""

    def test_one_absent_fact_blocks_completion(self):
        for fact in REQUIRED_FACTS:
            with self.subTest(missing=fact):
                verdict = run(all_present(**{fact: absent(fact)}))
                self.assertFalse(verdict.complete)
                self.assertIn(fact, verdict.missing)
                self.assertEqual(verdict.exit_code, 1)

    def test_an_unreachable_observer_is_incomplete_not_a_crash(self):
        def explode():
            raise ConnectionError("provider unreachable")

        verdict = run(all_present(scorecard=explode))
        self.assertFalse(verdict.complete)
        self.assertIn("scorecard", verdict.missing)
        self.assertIn("ConnectionError", verdict.detail)

    def test_a_fact_claimed_present_without_evidence_is_refused(self):
        """Presence with no hash is an assertion, not an observation."""
        with self.assertRaises(ReleaseCompletionError):
            FactObservation(fact="scorecard", present=True)

    def test_a_missing_observer_is_not_silent_success(self):
        observers = all_present()
        del observers["closed_records"]
        with self.assertRaises(ReleaseCompletionError) as caught:
            run(observers)
        self.assertIn("verified by omission", str(caught.exception))

    def test_every_observer_runs_even_after_the_first_absence(self):
        calls = []

        def tracking(fact, is_present):
            def observe():
                calls.append(fact)
                return FactObservation(
                    fact=fact,
                    present=is_present,
                    evidence_sha256="sha-" + fact if is_present else "",
                )

            return observe

        observers = {
            f: tracking(f, f not in ("publication_receipt", "scorecard"))
            for f in REQUIRED_FACTS
        }
        verdict = run(observers)

        self.assertEqual(calls, list(REQUIRED_FACTS))
        self.assertEqual(
            sorted(verdict.missing), ["publication_receipt", "scorecard"],
            "stopping at the first absence drip-feeds an operator one pending "
            "edge at a time",
        )

    def test_an_observer_cannot_answer_for_another_fact(self):
        observers = all_present(scorecard=present("closed_records"))
        with self.assertRaises(ReleaseCompletionError):
            run(observers)


class NamedPartialStateTests(unittest.TestCase):
    def test_each_absent_fact_names_its_state(self):
        for fact, expected in PARTIAL_STATE_BY_FACT.items():
            with self.subTest(fact=fact):
                verdict = run(all_present(**{fact: absent(fact)}))
                self.assertEqual(verdict.partial_state, expected)

    def test_the_first_absent_fact_in_order_names_the_state(self):
        """Replay attempts the earliest unfinished edge, so it names the state."""
        verdict = run(
            all_present(
                bus_published_event=absent("bus_published_event"),
                scorecard=absent("scorecard"),
            )
        )
        self.assertEqual(verdict.partial_state, "event-mirror-pending")

    def test_the_partial_vocabulary_matches_the_saga_checkpoints(self):
        """One vocabulary, so two surfaces cannot describe one state differently."""
        saga_states = {c.incomplete_state for c in CHECKPOINTS_BY_ID.values()}
        for state in PARTIAL_STATE_BY_FACT.values():
            with self.subTest(state=state):
                self.assertIn(state, saga_states)


class CoherenceTests(unittest.TestCase):
    """Four present facts are not four facts about the same release."""

    def test_facts_binding_different_receipts_refuse(self):
        verdict = run(
            all_present(
                closed_records=present("closed_records", "a-different-receipt")
            )
        )
        self.assertFalse(verdict.complete)
        self.assertEqual(verdict.partial_state, INCOHERENT_STATE)
        self.assertIn("one release", verdict.detail)
        self.assertIsNone(verdict.receipt)

    def test_agreement_across_all_co_bound_facts_is_required(self):
        for fact in CO_BOUND_FACTS:
            with self.subTest(divergent=fact):
                verdict = run(all_present(**{fact: present(fact, "odd-one-out")}))
                self.assertFalse(
                    verdict.complete,
                    f"{fact} bound a different receipt and completion still passed",
                )

    def test_the_scorecard_is_not_co_bound(self):
        """It hashes itself, not the publication receipt."""
        self.assertNotIn("scorecard", CO_BOUND_FACTS)
        verdict = run(all_present())
        self.assertTrue(verdict.complete)

    def test_the_shared_binding_is_what_the_receipt_records(self):
        receipt = run(all_present()).receipt
        bound = {receipt["verified_facts"][f] for f in CO_BOUND_FACTS}
        self.assertEqual(len(bound), 1)


class NoUndoTests(unittest.TestCase):
    """Refusing completion may never reach for an outward fact."""

    def test_the_verdict_exposes_no_mutation(self):
        verdict = run(all_present(closed_records=absent("closed_records")))
        for attribute in dir(verdict):
            if attribute.startswith("_"):
                continue
            with self.subTest(attribute=attribute):
                self.assertNotIn(
                    attribute,
                    ("undo", "rollback", "delete", "revert", "retract"),
                    "post-publication reconciliation may refuse completion and "
                    "nothing else",
                )

    def test_an_incomplete_run_produces_no_receipt(self):
        verdict = run(all_present(scorecard=absent("scorecard")))
        self.assertIsNone(
            verdict.receipt,
            "a completion receipt for an incomplete run is the false fact the "
            "whole checkpoint exists to prevent",
        )


class SagaIntegrationTests(unittest.TestCase):
    def test_completion_verification_is_a_registered_checkpoint(self):
        self.assertIn("completion_verification", CHECKPOINTS_BY_ID)

    def test_it_depends_on_the_scorecard(self):
        checkpoint = CHECKPOINTS_BY_ID["completion_verification"]
        self.assertEqual(checkpoint.depends_on, ("scorecard",))

    def test_its_idempotency_key_is_the_scorecard_hash(self):
        checkpoint = CHECKPOINTS_BY_ID["completion_verification"]
        self.assertEqual(
            checkpoint.idempotency_key({"scorecard_sha": "abc123"}),
            "completion:abc123",
        )

    def test_it_is_terminal_in_the_enum(self):
        """Nothing may depend on completion; it is the last fact."""
        for checkpoint in CHECKPOINTS_BY_ID.values():
            with self.subTest(checkpoint=checkpoint.checkpoint_id):
                self.assertNotIn("completion_verification", checkpoint.depends_on)

    def test_the_completion_event_is_named(self):
        self.assertEqual(COMPLETION_EVENT, "tropo.release.completion_verified")


class LiveVerifierCliTests(unittest.TestCase):
    """The production observers, against a run folder on disk."""

    RSHA = "recpt0011223344"

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "tropo_verify_release_live_under_test",
            TOOLS / "tropo-verify-release-live.py",
        )
        cls.cli = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.cli
        spec.loader.exec_module(cls.cli)

    def finished_run(self, **omit) -> Path:
        import json as _json
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="release-live-"))
        self.addCleanup(shutil.rmtree, tmp, True)

        rows = [
            {"event": "tropo.release.scope_locked",
             "data": {"saga_id": SAGA, "pipeline_run_uid": RUN}},
        ]
        if not omit.get("run_event"):
            rows.append({
                "event": "tropo.release.published",
                "data": {"saga_id": SAGA, "pipeline_run_uid": RUN,
                         "publication_receipt_sha256": self.RSHA},
            })
        if not omit.get("closure"):
            rows.append({
                "event": "tropo.release.closed",
                "data": {"pipeline_run_uid": RUN,
                         "publication_receipt_sha256": self.RSHA,
                         "closed_uids": omit.get("closed_uids", ["c45da26c"])},
            })
        (tmp / "run.jsonl").write_text(
            "".join(_json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        if not omit.get("receipt"):
            (tmp / "publication-receipt.json").write_text(
                _json.dumps({"publication_receipt_sha256": self.RSHA}), encoding="utf-8"
            )
        if not omit.get("scorecard"):
            (tmp / "scorecard.json").write_text(
                _json.dumps({"scorecard_sha256": "score998877"}), encoding="utf-8"
            )
        bus = tmp / "bus.jsonl"
        if not omit.get("bus"):
            bus.write_text(
                _json.dumps({"type": "tropo.release.published",
                             "data": {"publication_receipt_sha256": self.RSHA}}) + "\n",
                encoding="utf-8",
            )
        else:
            bus.write_text("", encoding="utf-8")
        return tmp

    def test_a_finished_run_verifies_and_writes_a_receipt(self):
        run_dir = self.finished_run()
        code = self.cli.main([
            "--run-dir", str(run_dir),
            "--bus-events", str(run_dir / "bus.jsonl"),
            "--write-receipt",
        ])
        self.assertEqual(code, self.cli.EXIT_OK)
        self.assertTrue((run_dir / "completion-receipt.json").is_file())

    def test_an_unobserved_bus_is_absent_not_fine(self):
        """The failure mode of every verifier that trusts its own reach.

        Asserting only the exit code is not enough here: an observer that
        crashed would also read as incomplete, and incomplete-because-it-broke
        is a different fact from incomplete-because-the-bus-is-empty. The
        detail has to say which.
        """
        run_dir = self.finished_run()
        observers = self.cli.build_observers(run_dir, [])  # bus unobserved
        observation = observers["bus_published_event"]()

        self.assertFalse(observation.present)
        self.assertIn(
            "found 0",
            observation.detail,
            "the bus was reported absent, but not because the guard counted "
            "zero events — an accidental crash would look the same",
        )

        code = self.cli.main(["--run-dir", str(run_dir)])  # no --bus-events
        self.assertEqual(code, self.cli.EXIT_INCOMPLETE)

    def test_a_bus_event_that_binds_nothing_is_absent(self):
        """Present-shaped is not the same as evidential."""
        run_dir = self.finished_run()
        observers = self.cli.build_observers(
            run_dir, [{"type": "tropo.release.published", "data": {}}]
        )
        observation = observers["bus_published_event"]()
        self.assertFalse(observation.present)
        self.assertIn("does not bind", observation.detail)

    def test_two_bus_events_are_not_one(self):
        """Exactly one, per the spec's cardinality; duplicates are a defect."""
        run_dir = self.finished_run()
        duplicate = {
            "type": "tropo.release.published",
            "data": {"publication_receipt_sha256": self.RSHA},
        }
        observers = self.cli.build_observers(run_dir, [duplicate, dict(duplicate)])
        observation = observers["bus_published_event"]()
        self.assertFalse(observation.present)
        self.assertIn("found 2", observation.detail)

    def test_an_empty_closure_closes_nothing(self):
        run_dir = self.finished_run(closed_uids=[])
        code = self.cli.main([
            "--run-dir", str(run_dir), "--bus-events", str(run_dir / "bus.jsonl"),
        ])
        self.assertEqual(code, self.cli.EXIT_INCOMPLETE)

    def test_each_missing_artifact_is_incomplete(self):
        for omission in ("receipt", "scorecard", "run_event", "closure", "bus"):
            with self.subTest(missing=omission):
                run_dir = self.finished_run(**{omission: True})
                code = self.cli.main([
                    "--run-dir", str(run_dir),
                    "--bus-events", str(run_dir / "bus.jsonl"),
                ])
                self.assertEqual(code, self.cli.EXIT_INCOMPLETE)

    def test_an_incomplete_run_writes_no_receipt(self):
        run_dir = self.finished_run(scorecard=True)
        self.cli.main([
            "--run-dir", str(run_dir), "--bus-events", str(run_dir / "bus.jsonl"),
            "--write-receipt",
        ])
        self.assertFalse((run_dir / "completion-receipt.json").exists())

    def test_a_missing_run_directory_is_misuse_not_incomplete(self):
        code = self.cli.main(["--run-dir", "/tmp/definitely-not-a-release-run"])
        self.assertEqual(code, self.cli.EXIT_MISUSE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
