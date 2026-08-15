"""AC7 receipt vocabulary: one shape, four instruments, exactly once.

A148's Q3 answer is the design under test: a single canonical receipt for
machine and human instruments alike, distinguished by `execution_mode` rather
than by a second schema. These cases exercise the refusals that make the AC7
claim mean something -- wrong run, wrong digest, missing instrument, failing
verdict, and the one that is easy to get wrong, agreeing duplicates.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_verify as rv  # noqa: E402

RUN = "a1b2c3d4"
DIGEST = "a" * 64


def receipt(instrument, **over):
    base = {
        "receipt_kind": rv.RECEIPT_KIND,
        "instrument": instrument,
        "release_run_uid": RUN,
        "package_sha256": DIGEST,
        "verdict": "pass",
        "executor_or_attester": "talos-t40",
        "execution_mode": "machine",
        "evidence_ref": f"vault/pipeline-runs/r/{instrument}.md",
        "started_at": "2026-08-11T14:00:00Z",
        "completed_at": "2026-08-11T14:05:00Z",
    }
    base.update(over)
    return base


def full_set(**per_instrument):
    return [receipt(name, **per_instrument.get(name, {})) for name in rv.INSTRUMENTS]


class OneShapeForEveryInstrument(unittest.TestCase):

    def test_all_four_instruments_share_one_receipt_kind(self):
        for name in rv.INSTRUMENTS:
            with self.subTest(instrument=name):
                parsed = rv.validate_receipt(receipt(name))
                self.assertEqual(parsed.as_dict()["receipt_kind"], rv.RECEIPT_KIND)

    def test_a_human_instrument_uses_the_same_shape_not_a_second_one(self):
        """Q3: execution_mode carries the difference, not a separate schema."""
        parsed = rv.validate_receipt(receipt(
            "cold-walk", execution_mode="human", executor_or_attester="mike"))
        self.assertEqual(parsed.execution_mode, "human")
        self.assertEqual(parsed.as_dict()["receipt_kind"], rv.RECEIPT_KIND)

    def test_an_unknown_instrument_is_refused(self):
        with self.assertRaises(rv.VerifyRefusal) as caught:
            rv.validate_receipt(receipt("smoke-test"))
        self.assertIn("four instruments", str(caught.exception))

    def test_every_required_field_is_required(self):
        for field in rv.RECEIPT_FIELDS:
            with self.subTest(missing=field):
                raw = receipt("full-validator")
                raw[field] = ""
                with self.assertRaises(rv.VerifyRefusal):
                    rv.validate_receipt(raw)

    def test_an_unrecognised_verdict_is_not_a_pass(self):
        with self.assertRaises(rv.VerifyRefusal):
            rv.validate_receipt(receipt("full-validator", verdict="probably"))

    def test_a_malformed_digest_is_refused(self):
        with self.assertRaises(rv.VerifyRefusal):
            rv.validate_receipt(receipt("full-validator", package_sha256="deadbeef"))


class TheBundleIsOneDigestOrNothing(unittest.TestCase):

    def test_four_passing_receipts_resolve(self):
        resolved = rv.assert_ready_to_publish(full_set(), RUN, DIGEST)
        self.assertEqual(set(resolved), set(rv.INSTRUMENTS))

    def test_a_missing_instrument_refuses_and_names_it(self):
        partial = [r for r in full_set() if r["instrument"] != "cold-walk"]
        with self.assertRaises(rv.VerifyRefusal) as caught:
            rv.assert_ready_to_publish(partial, RUN, DIGEST)
        self.assertIn("cold-walk", str(caught.exception))

    def test_a_failing_verdict_blocks_even_though_the_receipt_exists(self):
        with self.assertRaises(rv.VerifyRefusal) as caught:
            rv.assert_ready_to_publish(
                full_set(**{"external-test": {"verdict": "fail"}}), RUN, DIGEST)
        self.assertIn("failing verdict", str(caught.exception))

    def test_a_receipt_from_another_run_does_not_transfer(self):
        with self.assertRaises(rv.VerifyRefusal) as caught:
            rv.assert_ready_to_publish(
                full_set(**{"release-harness": {"release_run_uid": "f9f9f9f9"}}),
                RUN, DIGEST)
        self.assertIn("does not transfer", str(caught.exception))

    def test_a_receipt_for_other_bytes_refuses(self):
        with self.assertRaises(rv.VerifyRefusal) as caught:
            rv.assert_ready_to_publish(
                full_set(**{"full-validator": {"package_sha256": "b" * 64}}),
                RUN, DIGEST)
        self.assertIn("not this artefact", str(caught.exception))

    def test_agreeing_duplicates_still_refuse(self):
        """The one that is easy to wave through.

        Two identical receipts look harmless and are not: two receipts mean
        two executions, and if they agree we still cannot say which one the
        evidence reference describes or why a second was needed. Deduplicating
        silently is how an unexplained re-run disappears.
        """
        doubled = full_set() + [receipt("cold-walk")]
        with self.assertRaises(rv.VerifyRefusal) as caught:
            rv.assert_ready_to_publish(doubled, RUN, DIGEST)
        self.assertIn("even when they agree", str(caught.exception))

    def test_an_empty_set_refuses_rather_than_vacuously_passing(self):
        with self.assertRaises(rv.VerifyRefusal):
            rv.assert_ready_to_publish([], RUN, DIGEST)


class TheEmitterActuallyProducesReceipts(unittest.TestCase):
    """A148 addendum 26 item 3: the vocabulary had no producer.

    Every refusal next door was well-formed and unreachable, because nothing in
    production ever wrote one of these. The Publish gate would have read an
    empty receipt set forever and refused every release for the wrong reason —
    or, worse, if the set had been optional, passed every release having
    checked nothing.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ac7-emit-")).resolve()
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir(parents=True)
        sys.path.insert(0, str(TOOLS))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ac7_engine", TOOLS / "9e7003b1.py")
        self.engine = importlib.util.module_from_spec(spec)
        sys.modules["ac7_engine"] = self.engine
        spec.loader.exec_module(self.engine)
        self.engine.VAULT_ROOT = self.tmp

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _release_run(self, uid="a1b2c3d4"):
        return {"frontmatter": {"uid": uid,
                                "pipeline": self.engine.RELEASE_PIPELINE_ROOT_UID}}

    def _freeze(self, digest=DIGEST):
        self.engine.append_event(self.run_dir, self.engine.make_event(
            "tropo.release.package_frozen", "a1b8c2d4",
            data={"package_sha256": digest}, trace_id="a1b2c3d4"))

    def _receipts(self):
        return [e for e in self.engine.read_events(self.run_dir)
                if (e.get("data") or {}).get("receipt_kind") == rv.RECEIPT_KIND]

    def test_an_instrument_node_writes_one_canonical_receipt(self):
        self._freeze()
        wrote = self.engine.emit_release_verification_receipt(
            self.run_dir, self._release_run(), "c6b61fb9", "po", "pass",
            execution_mode="human")
        self.assertTrue(wrote)
        receipts = self._receipts()
        self.assertEqual(len(receipts), 1)
        parsed = rv.validate_receipt(receipts[0]["data"])
        self.assertEqual(parsed.instrument, "cold-walk")
        self.assertEqual(parsed.package_sha256, DIGEST)
        self.assertEqual(parsed.execution_mode, "human")

    def test_a_non_instrument_step_writes_nothing(self):
        """The gate stays off every path it does not belong to."""
        self._freeze()
        self.assertFalse(self.engine.emit_release_verification_receipt(
            self.run_dir, self._release_run(), "deadbeef", "talos", "pass"))
        self.assertEqual(self._receipts(), [])

    def test_a_dev_run_writes_nothing_even_for_an_instrument_uid(self):
        self._freeze()
        dev = {"frontmatter": {"uid": "a1b2c3d4", "pipeline": "74945d48"}}
        self.assertFalse(self.engine.emit_release_verification_receipt(
            self.run_dir, dev, "c6b61fb9", "talos", "pass"))
        self.assertEqual(self._receipts(), [])

    def test_an_instrument_with_no_frozen_package_refuses(self):
        """A receipt has to name the bytes it tested."""
        with self.assertRaises(Exception) as caught:
            self.engine.emit_release_verification_receipt(
                self.run_dir, self._release_run(), "4262d5fa", "talos", "pass")
        self.assertIn("no frozen package", str(caught.exception))

    def test_a_failing_verdict_is_recorded_as_fail_not_dropped(self):
        self._freeze()
        self.engine.emit_release_verification_receipt(
            self.run_dir, self._release_run(), "4262d5fa", "talos", "fail")
        self.assertEqual(
            rv.validate_receipt(self._receipts()[0]["data"]).verdict, "fail")

    def test_the_emitted_receipts_satisfy_the_publish_gate(self):
        """End of the chain: what the emitter writes is what the gate reads."""
        self._freeze()
        for node in rv.INSTRUMENT_NODES.values():
            self.engine.emit_release_verification_receipt(
                self.run_dir, self._release_run(), node, "talos", "pass")
        bundle = rv.assert_ready_to_publish(
            [r["data"] for r in self._receipts()], "a1b2c3d4", DIGEST)
        self.assertEqual(set(bundle), set(rv.INSTRUMENTS))


class InstrumentsMapToTheGraph(unittest.TestCase):

    def test_each_instrument_names_its_verify_node(self):
        self.assertEqual(set(rv.INSTRUMENT_NODES), set(rv.INSTRUMENTS))
        self.assertEqual(rv.instrument_for_node("c6b61fb9"), "cold-walk")
        self.assertIsNone(rv.instrument_for_node("deadbeef"))

    def test_the_nodes_are_the_ones_verify_actually_claims(self):
        """Guards the vocabulary against the graph drifting out from under it."""
        import yaml
        files = TOOLS.parent / "files"
        text = (files / "8a4f802b.md").read_text(encoding="utf-8")
        verify = yaml.safe_load(text[3:text.find("\n---", 3)])
        claimed = {str(c) for c in (verify.get("children") or [])}
        self.assertTrue(
            set(rv.INSTRUMENT_NODES.values()) <= claimed,
            f"instrument nodes {sorted(set(rv.INSTRUMENT_NODES.values()) - claimed)} "
            f"are not claimed by Verify, so this vocabulary describes a graph "
            f"that no longer exists",
        )


if __name__ == "__main__":
    unittest.main()
