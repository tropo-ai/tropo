#!/usr/bin/env python3
"""Release events are authorized against substrate, not against themselves.

Dev-spec 2fae6312 step 5. The property this suite exists for is narrow: the
identities an event is measured against must come from the run, never from the
event. An emitter that supplies both the claim and the yardstick has written a
check that passes for a run it never read.
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

from lib.release_events import (  # noqa: E402
    ENVELOPE_NULLABLE,
    ENVELOPE_REQUIRED,
    HUMAN_INPUT_EVENTS,
    REFUSAL_CARDINALITY,
    REFUSAL_DATA_MISSING,
    REFUSAL_DATA_UNKNOWN,
    REFUSAL_ENVELOPE,
    REFUSAL_IDENTITY,
    REFUSAL_STEP,
    REFUSAL_UNREGISTERED,
    RELEASE_EVENTS,
    AuthorizationContext,
    authorize,
)

ACTIVATION = "14b6540e"
RUN = "934436ca"
SAGA = "release:934436ca"
ENTRY = "a1b2c3d4"
ROOT_UID = "e5f6a7b8"
PLAN = "c45da26c"
COLD_WALK = "c6b61fb9"


def context(**overrides) -> AuthorizationContext:
    base = dict(
        activation_uid=ACTIVATION,
        pipeline_run_uid=RUN,
        saga_id=SAGA,
        release_entry_uid=ENTRY,
        activation_root_uid=ROOT_UID,
        release_plan_uid=PLAN,
        snapshot_step_uids=frozenset({COLD_WALK, "4262d5fa"}),
    )
    base.update(overrides)
    return AuthorizationContext(**base)


def envelope(event: str, data: dict, **overrides) -> dict:
    row = {
        "event": event,
        "ts": "2026-08-16T21:00:00Z",
        "actor": "talos-t44",
        "data": data,
        "schema_version": 2,
        "trace_id": ACTIVATION,
        "span_id": "span-0001",
        "step": None,
    }
    row.update(overrides)
    return row


def candidate_built(**data_overrides) -> dict:
    data = {
        "saga_id": SAGA,
        "pipeline_run_uid": RUN,
        "candidate_sha256": "abc123",
        "candidate_path": "dist/tropo-1.89.0.zip",
    }
    data.update(data_overrides)
    return envelope("tropo.release.candidate_built", data)


class ContextIsObservedTests(unittest.TestCase):
    """The context comes from the run, or it does not come at all."""

    def scratch_run(self, journal_rows, snapshot=None) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="release-event-ctx-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "run.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in journal_rows), encoding="utf-8"
        )
        if snapshot is not None:
            (tmp / "declaration-snapshot.json").write_text(
                json.dumps(snapshot), encoding="utf-8"
            )
        return tmp

    def test_observe_takes_a_directory_and_nothing_else(self):
        """There is no parameter through which an identity could be supplied."""
        import inspect

        signature = inspect.signature(AuthorizationContext.observe)
        self.assertEqual(
            [p for p in signature.parameters if p != "cls"],
            ["run_dir"],
            "observe() grew a parameter; every one is a way to inject an identity "
            "the substrate never asserted",
        )

    def test_identity_is_read_from_the_journal(self):
        run = self.scratch_run(
            [
                {
                    "event": "tropo.release.scope_locked",
                    "data": {
                        "saga_id": SAGA,
                        "pipeline_run_uid": RUN,
                        "activation_uid": ACTIVATION,
                        "release_entry_uid": ENTRY,
                    },
                }
            ]
        )
        observed = AuthorizationContext.observe(run)
        self.assertEqual(observed.saga_id, SAGA)
        self.assertEqual(observed.pipeline_run_uid, RUN)
        self.assertEqual(observed.activation_uid, ACTIVATION)
        self.assertEqual(observed.release_entry_uid, ENTRY)

    def test_the_step_set_comes_from_the_immutable_snapshot(self):
        run = self.scratch_run([], snapshot={"nodes": [{"uid": COLD_WALK}]})
        self.assertIn(COLD_WALK, AuthorizationContext.observe(run).snapshot_step_uids)

    def test_an_invalidated_candidate_is_not_active(self):
        run = self.scratch_run(
            [
                {
                    "event": "tropo.release.candidate_built",
                    "data": {"candidate_sha256": "abc123"},
                },
                {
                    "event": "tropo.release.candidate_invalidated",
                    "data": {"candidate_sha256": "abc123"},
                },
            ]
        )
        self.assertIsNone(AuthorizationContext.observe(run).active_candidate_sha256)

    def test_the_frozen_package_is_observed(self):
        run = self.scratch_run(
            [
                {
                    "event": "tropo.release.package_frozen",
                    "data": {"package_sha256": "abc123"},
                }
            ]
        )
        self.assertEqual(
            AuthorizationContext.observe(run).frozen_package_sha256, "abc123"
        )


class VocabularyTests(unittest.TestCase):
    def test_an_unregistered_event_refuses(self):
        row = envelope("tropo.release.definitely_fine", {})
        verdict = authorize(row, context())
        self.assertTrue(verdict.refused)
        self.assertEqual(verdict.refusal_class, REFUSAL_UNREGISTERED)

    def test_the_three_human_inputs_map_onto_real_events(self):
        for human, event in HUMAN_INPUT_EVENTS.items():
            with self.subTest(human_input=human):
                self.assertIn(event, RELEASE_EVENTS)

    def test_the_bus_types_are_only_the_two_public_facts(self):
        bus = {c.event for c in RELEASE_EVENTS.values() if c.bus_type}
        self.assertEqual(
            bus, {"tropo.release.published", "tropo.release.closed"}
        )


class EnvelopeTests(unittest.TestCase):
    def test_a_well_formed_event_authorizes(self):
        self.assertTrue(authorize(candidate_built(), context()).authorized)

    def test_a_missing_envelope_field_refuses(self):
        row = candidate_built()
        del row["span_id"]
        verdict = authorize(row, context())
        self.assertEqual(verdict.refusal_class, REFUSAL_ENVELOPE)

    def test_an_unknown_envelope_field_refuses(self):
        row = candidate_built()
        row["priority"] = "high"
        self.assertEqual(authorize(row, context()).refusal_class, REFUSAL_ENVELOPE)

    def test_a_duplicate_span_id_refuses(self):
        prior = [candidate_built()]
        row = candidate_built(candidate_sha256="def456")
        self.assertEqual(
            authorize(row, context(), prior).refusal_class, REFUSAL_ENVELOPE
        )

    def test_the_nullable_fields_are_accepted(self):
        row = candidate_built()
        for key in ENVELOPE_NULLABLE:
            row.setdefault(key, None)
        self.assertTrue(authorize(row, context()).authorized)


class IdentityTests(unittest.TestCase):
    """The half that cannot be satisfied by the emitter."""

    def test_a_foreign_run_uid_refuses(self):
        row = candidate_built(pipeline_run_uid="deadbeef")
        verdict = authorize(row, context())
        self.assertEqual(verdict.refusal_class, REFUSAL_IDENTITY)
        self.assertIn("substrate observes", verdict.detail)

    def test_a_foreign_saga_id_refuses(self):
        row = candidate_built(saga_id="release:somebody-else")
        self.assertEqual(authorize(row, context()).refusal_class, REFUSAL_IDENTITY)

    def test_trace_id_must_be_the_activation(self):
        row = candidate_built()
        row["trace_id"] = "00000000"
        self.assertEqual(authorize(row, context()).refusal_class, REFUSAL_IDENTITY)

    def test_an_event_cannot_supply_the_yardstick_it_is_measured_against(self):
        """The circularity this module exists to prevent.

        The emitter asserts a run UID; the context asserts another. There is no
        argument to authorize() that lets the emitter win, and if one is ever
        added this test is where it shows up.
        """
        row = candidate_built(pipeline_run_uid="deadbeef")
        self.assertTrue(authorize(row, context()).refused)

        import inspect

        params = list(inspect.signature(authorize).parameters)
        self.assertEqual(
            params,
            ["envelope", "context", "prior_events"],
            "authorize() grew a parameter; check it is not an identity override",
        )


class DataShapeTests(unittest.TestCase):
    def test_a_missing_required_key_refuses(self):
        row = candidate_built()
        del row["data"]["candidate_path"]
        self.assertEqual(authorize(row, context()).refusal_class, REFUSAL_DATA_MISSING)

    def test_an_extra_data_key_refuses(self):
        row = candidate_built(notes="just a little context")
        verdict = authorize(row, context())
        self.assertEqual(verdict.refusal_class, REFUSAL_DATA_UNKNOWN)

    def test_every_contract_lists_its_identity_keys_as_required(self):
        """A contract that omits an identity key cannot be identity-checked."""
        # v1.91 S2 (3fb41c99): release-verification-receipt's Receipt
        # dataclass names its run field `release_run_uid`, not
        # `pipeline_run_uid` -- a pre-existing choice in lib/release_verify.py,
        # unrelated to and out of scope for the receipt-shape unification.
        # Same exemption shape as verification_receipt, which also carries no
        # saga_id: a receipt is scoped to the run and the candidate/instrument
        # it tested, not to the saga.
        no_pipeline_run_uid_field = {"verification_receipt", "release-verification-receipt"}
        for event, contract in RELEASE_EVENTS.items():
            with self.subTest(event=event):
                if event in no_pipeline_run_uid_field:
                    self.assertIn(
                        "release_run_uid" if event == "release-verification-receipt"
                        else "pipeline_run_uid",
                        contract.required_data)
                else:
                    self.assertIn("pipeline_run_uid", contract.required_data)
                    self.assertIn("saga_id", contract.required_data)


class SteppedEventTests(unittest.TestCase):
    def receipt(self, **overrides) -> dict:
        data = {
            "receipt_kind": "release-verification-receipt",
            "pipeline_run_uid": RUN,
            "candidate_sha256": "abc123",
            "instrument": "cold-boot-walk",
            "instrument_step_uid": COLD_WALK,
            "verdict": "pass",
            "evidence_sha256": "e1e2e3",
        }
        data.update(overrides)
        return envelope("verification_receipt", data, step=data["instrument_step_uid"])

    def test_a_receipt_naming_a_snapshot_step_authorizes(self):
        self.assertTrue(authorize(self.receipt(), context()).authorized)

    def test_a_step_outside_the_snapshot_refuses(self):
        """Resolving in the live Vault is not the same fact.

        The freeze node landed today. A run whose snapshot predates it must not
        accept receipts naming it — the run declared a different pipeline.
        """
        row = self.receipt(instrument_step_uid="7de2c49f", instrument="freeze")
        verdict = authorize(row, context())
        self.assertEqual(verdict.refusal_class, REFUSAL_STEP)
        self.assertIn("declaration snapshot", verdict.detail)

    def test_a_non_stepped_event_must_set_step_null(self):
        row = candidate_built()
        row["step"] = COLD_WALK
        self.assertEqual(authorize(row, context()).refusal_class, REFUSAL_STEP)

    def test_one_receipt_per_run_candidate_instrument(self):
        prior = [self.receipt()]
        again = self.receipt()
        again["span_id"] = "span-0002"
        verdict = authorize(again, context(), prior)
        self.assertEqual(verdict.refusal_class, REFUSAL_CARDINALITY)

    def test_a_different_instrument_on_the_same_candidate_is_fine(self):
        prior = [self.receipt()]
        other = self.receipt(instrument="external-test", instrument_step_uid="4262d5fa")
        other["span_id"] = "span-0002"
        other["step"] = "4262d5fa"
        self.assertTrue(authorize(other, context(), prior).authorized)


class CardinalityTests(unittest.TestCase):
    def test_a_terminal_event_occurs_once(self):
        frozen = envelope(
            "tropo.release.package_frozen",
            {
                "saga_id": SAGA,
                "pipeline_run_uid": RUN,
                "package_sha256": "abc123",
                "receipt_set_sha256": "r1r2r3",
            },
        )
        self.assertTrue(authorize(frozen, context()).authorized)

        again = dict(frozen, span_id="span-0002")
        verdict = authorize(again, context(), [frozen])
        self.assertEqual(verdict.refusal_class, REFUSAL_CARDINALITY)
        self.assertIn("terminal", verdict.detail)

    def test_one_candidate_built_per_sha_but_a_new_sha_is_allowed(self):
        first = candidate_built()
        repeat = dict(first, span_id="span-0002")
        self.assertEqual(
            authorize(repeat, context(), [first]).refusal_class, REFUSAL_CARDINALITY
        )

        rebuilt = candidate_built(candidate_sha256="def456")
        rebuilt["span_id"] = "span-0003"
        self.assertTrue(authorize(rebuilt, context(), [first]).authorized)


if __name__ == "__main__":
    unittest.main(verbosity=2)
