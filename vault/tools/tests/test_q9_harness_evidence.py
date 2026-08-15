"""Q9: the harness node validates evidence and never runs the harness.

A148's ruling, evt_a9360f18f56fe472_00000027. `sa.release-test-harness` is a
session-agent Mike activates, not a tool, so `a0f2bea8` cannot execute it — and
must not synthesize a verdict on its behalf, because an engine that writes its
own evidence has verified nothing.

The load-bearing half is the second hop. Anything that can append to a run can
write a receipt claiming the harness passed, so the receipt is a claim; the gate
is only real if `evidence_ref` resolves to a record the harness agent actually
owns, whose own identity agrees.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location(
    "q9_checker", TOOLS / "tropo-check-harness-receipt.py")
q9 = importlib.util.module_from_spec(_spec)
sys.modules["q9_checker"] = q9
_spec.loader.exec_module(q9)

from lib import release_verify as rv  # noqa: E402

RUN = "a1b2c3d4"
DIGEST = "b" * 64


def receipt(**over):
    base = {
        "receipt_kind": rv.RECEIPT_KIND,
        "instrument": "release-harness",
        "release_run_uid": RUN,
        "package_sha256": DIGEST,
        "verdict": "pass",
        "executor_or_attester": q9.HARNESS_AGENT_NAME,
        "execution_mode": "agent",
        "evidence_ref": "cafe0001",
        "started_at": "2026-08-11T23:00:00Z",
        "completed_at": "2026-08-11T23:30:00Z",
    }
    base.update(over)
    return base


def event(data):
    return {"event": rv.RECEIPT_KIND, "data": data}


def reader(entries):
    def read(uid):
        return entries.get(uid)
    return read


class TheGateFindsExactlyOnePassingAgentReceipt(unittest.TestCase):

    def test_a_clean_receipt_resolves(self):
        found = q9.find_harness_receipt([event(receipt())], RUN, DIGEST)
        self.assertEqual(found["instrument"], "release-harness")

    def test_no_receipt_refuses_and_does_not_run_the_harness(self):
        with self.assertRaises(q9.HarnessEvidenceRefusal) as caught:
            q9.find_harness_receipt([], RUN, DIGEST)
        message = str(caught.exception)
        self.assertIn("has not run", message)
        self.assertIn("will not run it", message,
                      "the refusal should say the gate does not execute the "
                      "harness; that is the whole design")

    def test_two_receipts_refuse(self):
        with self.assertRaises(q9.HarnessEvidenceRefusal) as caught:
            q9.find_harness_receipt([event(receipt()), event(receipt())],
                                    RUN, DIGEST)
        self.assertIn("exactly one is legal", str(caught.exception))

    def test_a_machine_mode_receipt_refuses(self):
        """Harness evidence is agent-produced; machine mode means synthesized."""
        with self.assertRaises(q9.HarnessEvidenceRefusal) as caught:
            q9.find_harness_receipt([event(receipt(execution_mode="machine"))],
                                    RUN, DIGEST)
        self.assertIn("synthesized", str(caught.exception))

    def test_a_failing_verdict_refuses(self):
        with self.assertRaises(q9.HarnessEvidenceRefusal):
            q9.find_harness_receipt([event(receipt(verdict="fail"))], RUN, DIGEST)

    def test_a_receipt_for_another_run_or_package_refuses(self):
        with self.assertRaises(q9.HarnessEvidenceRefusal):
            q9.find_harness_receipt([event(receipt(release_run_uid="f0f0f0f0"))],
                                    RUN, DIGEST)
        with self.assertRaises(q9.HarnessEvidenceRefusal):
            q9.find_harness_receipt([event(receipt(package_sha256="c" * 64))],
                                    RUN, DIGEST)

    def test_another_instrument_does_not_satisfy_the_harness_gate(self):
        with self.assertRaises(q9.HarnessEvidenceRefusal):
            q9.find_harness_receipt([event(receipt(instrument="cold-walk"))],
                                    RUN, DIGEST)


class TheReceiptIsNotSelfAuthorizing(unittest.TestCase):
    """The second hop, which is the part that makes this a gate at all."""

    def _evidence(self, **over):
        fm = {"uid": "cafe0001", "type": "test-run",
              "owner": q9.HARNESS_AGENT_UID,
              "release_pipeline_run_uid": RUN, "package_sha256": DIGEST}
        fm.update(over)
        return {"cafe0001": {"frontmatter": fm}}

    def test_real_agent_owned_evidence_resolves(self):
        got = q9.resolve_evidence(receipt(), reader(self._evidence()))
        self.assertEqual(got["uid"], "cafe0001")

    def test_evidence_that_does_not_exist_refuses(self):
        with self.assertRaises(q9.HarnessEvidenceRefusal) as caught:
            q9.resolve_evidence(receipt(), reader({}))
        self.assertIn("claim, not", str(caught.exception))

    def test_evidence_owned_by_anyone_else_refuses(self):
        """Anything can append a receipt; only the agent can own its record."""
        with self.assertRaises(q9.HarnessEvidenceRefusal) as caught:
            q9.resolve_evidence(receipt(), reader(self._evidence(owner="talos")))
        self.assertIn("cannot show the harness ran", str(caught.exception))

    def test_evidence_naming_another_run_refuses(self):
        with self.assertRaises(q9.HarnessEvidenceRefusal) as caught:
            q9.resolve_evidence(
                receipt(), reader(self._evidence(release_pipeline_run_uid="f0f0f0f0")))
        self.assertIn("not describe the same run", str(caught.exception))

    def test_evidence_naming_another_package_refuses(self):
        with self.assertRaises(q9.HarnessEvidenceRefusal):
            q9.resolve_evidence(
                receipt(), reader(self._evidence(package_sha256="c" * 64)))

    def test_evidence_naming_no_run_refuses(self):
        """A148 fix 2: absence was reading as agreement.

        `if recorded and recorded != expected` let an ABSENT field pass, so a
        test-run naming neither a release run nor a package could authorize a
        release — the weakest possible evidence satisfying the strongest check.
        """
        entries = self._evidence()
        del entries["cafe0001"]["frontmatter"]["release_pipeline_run_uid"]
        with self.assertRaises(q9.HarnessEvidenceRefusal) as caught:
            q9.resolve_evidence(receipt(), reader(entries))
        self.assertIn("absence is not agreement", str(caught.exception))

    def test_evidence_naming_no_package_refuses(self):
        entries = self._evidence()
        del entries["cafe0001"]["frontmatter"]["package_sha256"]
        with self.assertRaises(q9.HarnessEvidenceRefusal) as caught:
            q9.resolve_evidence(receipt(), reader(entries))
        self.assertIn("names no package", str(caught.exception))

    def test_evidence_naming_neither_refuses(self):
        """The exact case A148 named: a record that commits to nothing."""
        entries = self._evidence()
        for field in ("release_pipeline_run_uid", "package_sha256"):
            del entries["cafe0001"]["frontmatter"][field]
        with self.assertRaises(q9.HarnessEvidenceRefusal):
            q9.resolve_evidence(receipt(), reader(entries))

    def test_a_receipt_with_no_evidence_ref_refuses(self):
        with self.assertRaises(q9.HarnessEvidenceRefusal):
            q9.resolve_evidence(receipt(evidence_ref=""), reader({}))

    def test_executed_by_is_accepted_as_ownership(self):
        """Some records name the runner rather than the owner."""
        entries = self._evidence(owner="vela", executed_by=q9.HARNESS_AGENT_UID)
        self.assertEqual(q9.resolve_evidence(receipt(), reader(entries))["uid"],
                         "cafe0001")


class TheNodePointsAtThisChecker(unittest.TestCase):

    def test_a0f2bea8_runs_the_checker_not_a_test_of_itself(self):
        """V9: the harness gate must not be able to self-authorize.

        It previously ran AC7's own contract test, then briefly the sandbox
        reference run — which synthesizes all four receipts, so the harness
        instrument would have been verified by a fixture that fabricates
        harness evidence.
        """
        import yaml
        text = (TOOLS.parent / "files" / "a0f2bea8.md").read_text(encoding="utf-8")
        node = yaml.safe_load(text[3:text.find("\n---", 3)])
        command = str(node.get("verification_command") or "")
        self.assertIn("tropo-check-harness-receipt.py", command)
        self.assertNotIn("test_two_pipeline_split", command)
        self.assertNotIn("sandbox_release", command)


if __name__ == "__main__":
    unittest.main()
