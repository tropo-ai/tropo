#!/usr/bin/env python3
"""The freeze is decided on the bytes and the receipts, or it is refused.

Dev-spec 2fae6312 step 4's verdict producer. This is the command named in
`verification_command:` on node 7de2c49f, so these cases are the difference
between that node's verdict being a measurement and being whatever the
operator typed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"

_spec = importlib.util.spec_from_file_location(
    "tropo_freeze_release_candidate", TOOLS / "tropo-freeze-release-candidate.py"
)
freeze = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = freeze
_spec.loader.exec_module(freeze)

_rv_spec = importlib.util.spec_from_file_location(
    "release_verify_for_freeze_test", TOOLS / "lib" / "release_verify.py"
)
release_verify = importlib.util.module_from_spec(_rv_spec)
sys.modules[_rv_spec.name] = release_verify
_rv_spec.loader.exec_module(release_verify)

RUN = "934436ca"
SAGA = "release:934436ca"


class FreezeDecisionTests(unittest.TestCase):
    def build(self, *, receipts=None, invalidate=False, already_frozen=False,
              mutate_bytes=False, wrong_run=False, frozen_sha=None) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="freeze-"))
        self.addCleanup(shutil.rmtree, tmp, True)

        candidate = tmp / "tropo-1.89.0.zip"
        candidate.write_bytes(b"pretend package bytes")
        sha = hashlib.sha256(candidate.read_bytes()).hexdigest()

        rows = [
            {"event": "tropo.release.scope_locked",
             "data": {"saga_id": SAGA, "pipeline_run_uid": RUN}},
            {"event": "tropo.release.candidate_built",
             "data": {"pipeline_run_uid": RUN, "candidate_sha256": sha,
                      "candidate_path": str(candidate)}},
        ]
        # v1.91 S2 (3fb41c99): the REAL shape release-verification-receipt
        # writes (9e7003b1.py's emit_release_verification_receipt), not the
        # generic dev-pipeline verification_receipt name -- that collision
        # is exactly what Argus A155's ruling exists to remove.
        for step in (receipts if receipts is not None else list(freeze.INSTRUMENTS)):
            rows.append({
                "event": release_verify.RECEIPT_KIND, "step": step,
                "data": {
                    "receipt_kind": release_verify.RECEIPT_KIND,
                    "instrument": freeze.INSTRUMENTS[step],
                    "release_run_uid": "somebody-else" if wrong_run else RUN,
                    "candidate_sha256": sha,
                    "verdict": "pass",
                    "executor_or_attester": "test",
                    "execution_mode": "machine",
                    "evidence_ref": step,
                    "started_at": "2026-08-23T00:00:00Z",
                    "completed_at": "2026-08-23T00:00:00Z",
                },
            })
        if invalidate:
            rows.append({"event": "tropo.release.candidate_invalidated",
                         "data": {"pipeline_run_uid": RUN, "candidate_sha256": sha,
                                  "reason": "prose fix"}})
        if already_frozen:
            rows.append({"event": "tropo.release.package_frozen",
                         "data": {"pipeline_run_uid": RUN,
                                  "package_sha256": frozen_sha or sha}})

        (tmp / "run.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        if mutate_bytes:
            candidate.write_bytes(b"pretend package bytes, edited after the walk")
        return tmp

    def decide(self, run_dir: Path):
        return freeze.decide(run_dir, run_dir / "tropo-1.89.0.zip")

    def test_four_receipts_and_unchanged_bytes_earn_the_freeze(self):
        payload, refusal = self.decide(self.build())
        self.assertIsNone(refusal)
        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual(len(payload["instrument_receipts"]), 4)

    def test_a_byte_change_after_the_instruments_ran_refuses(self):
        """The defect the node exists to prevent, exercised end to end."""
        payload, refusal = self.decide(self.build(mutate_bytes=True))
        self.assertIsNotNone(refusal)
        self.assertIn("recorded", refusal)
        self.assertEqual(payload["verdict"], "fail")
        self.assertNotEqual(payload["rehashed_sha256"], payload["candidate_sha256"])

    def test_three_receipts_is_a_fail_not_a_rounding_error(self):
        for absent in freeze.INSTRUMENTS:
            with self.subTest(absent=absent):
                present = [u for u in freeze.INSTRUMENTS if u != absent]
                payload, refusal = self.decide(self.build(receipts=present))
                self.assertIsNotNone(refusal)
                # v1.91 S2 (3fb41c99): the shared resolver names the
                # INSTRUMENT, not the step uid -- ONE vocabulary, per Argus
                # A155's ruling part 5.
                self.assertIn(freeze.INSTRUMENTS[absent], refusal)
                self.assertEqual(payload["verdict"], "fail")

    def test_a_live_invalidation_blocks_the_freeze(self):
        _, refusal = self.decide(self.build(invalidate=True))
        self.assertIsNotNone(refusal)
        self.assertIn("invalidation", refusal)

    def test_a_freeze_on_different_bytes_is_a_supersession_not_a_freeze(self):
        other = hashlib.sha256(b"some other package").hexdigest()
        payload, refusal = self.decide(self.build(already_frozen=True, frozen_sha=other))
        self.assertIsNotNone(refusal)
        self.assertIn("supersession", refusal)
        self.assertEqual(payload["verdict"], "fail")

    def test_a_freeze_already_bound_to_these_bytes_is_the_post_state_pass(self):
        """The verification re-run AFTER the act (talos-t63, v1.95 post-lock inclusion).

        The runner executes this command as the step's verification after the
        step has emitted its freeze. Criterion 4 reads "exactly one active
        package_frozen exists for this run after the step", so a freeze that
        binds these same bytes is that criterion satisfied — not the refusal
        that made v1.90, v1.93 and v1.94 amend the step to a hand script.
        RED without the change: decide() refused every active freeze flat.
        """
        payload, refusal = self.decide(self.build(already_frozen=True))
        self.assertIsNone(refusal, refusal)
        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual(payload["frozen_event_uid"], "existing")
        self.assertIn("post-state", payload["rationale"])
        self.assertEqual(len(payload["instrument_receipts"]), 4,
                         "the four receipts are still checked on the post-state pass")

    def test_the_post_state_pass_still_needs_the_bytes_and_the_receipts(self):
        """Idempotence is on the digest, not a bypass of criteria 1 to 3."""
        _, refusal = self.decide(self.build(already_frozen=True, mutate_bytes=True))
        self.assertIsNotNone(refusal)
        self.assertIn("recorded", refusal)
        present = [u for u in freeze.INSTRUMENTS][:3]
        _, refusal = self.decide(self.build(already_frozen=True, receipts=present))
        self.assertIsNotNone(refusal)

    def test_emit_on_the_post_state_pass_writes_no_second_freeze(self):
        run_dir = self.build(already_frozen=True)
        before = (run_dir / "run.jsonl").read_text()
        code = freeze.main(["--run-dir", str(run_dir),
                            "--candidate", str(run_dir / "tropo-1.89.0.zip"), "--emit"])
        self.assertEqual(code, freeze.EXIT_FROZEN)
        after = (run_dir / "run.jsonl").read_text()
        self.assertEqual(before, after, "a second identical freeze was written")
        self.assertEqual(after.count("package_frozen"), 1)

    def test_receipts_from_another_run_do_not_count(self):
        _, refusal = self.decide(self.build(wrong_run=True))
        self.assertIsNotNone(refusal)
        self.assertIn("no receipt for", refusal)

    def test_a_missing_candidate_refuses(self):
        run_dir = self.build()
        (run_dir / "tropo-1.89.0.zip").unlink()
        _, refusal = self.decide(run_dir)
        self.assertIn("no candidate", refusal)

    def test_the_four_instruments_are_the_declared_four(self):
        self.assertEqual(
            sorted(freeze.INSTRUMENTS),
            sorted(["4262d5fa", "a0f2bea8", "bc6b17ec", "c6b61fb9"]),
        )


class AuthorizedSkipTests(FreezeDecisionTests):
    """An authorized skip is the fourth receipt, disclosed, never silent.

    Mike-ruled 2026-09-09 on the v1.96 run: the runtime honored his authorized
    skip of the harness for step dependencies while this tool and the fire
    counted receipts and refused on three. The excusal now lives in the same
    receipt set (verdict `skipped` + `authorized_by`), so one reader change
    fixes every reader. Each test here has a mutation partner: strip the
    signature and it refuses; excuse a pass and it refuses; a later real pass
    governs and nothing stays excused.
    """

    HARNESS_STEP = "a0f2bea8"

    def build_with_excusal(self, *, signed=True, authorized_by="mike-maziarz",
                           after_pass=False, then_pass=False) -> Path:
        present = (list(freeze.INSTRUMENTS) if after_pass
                   else [u for u in freeze.INSTRUMENTS if u != self.HARNESS_STEP])
        tmp = self.build(receipts=present)
        sha = hashlib.sha256((tmp / "tropo-1.89.0.zip").read_bytes()).hexdigest()

        def receipt(verdict, completed_at, **extra):
            data = {
                "receipt_kind": release_verify.RECEIPT_KIND,
                "instrument": freeze.INSTRUMENTS[self.HARNESS_STEP],
                "release_run_uid": RUN,
                "candidate_sha256": sha,
                "verdict": verdict,
                "executor_or_attester": "user",
                "execution_mode": "human",
                "evidence_ref": "skip_authorization@auth1",
                "started_at": completed_at,
                "completed_at": completed_at,
            }
            data.update(extra)
            return json.dumps({"event": release_verify.RECEIPT_KIND,
                               "step": self.HARNESS_STEP, "data": data}) + "\n"

        rows = receipt("skipped", "2026-09-09T15:40:08Z",
                       **({"authorized_by": authorized_by} if signed else {}))
        if then_pass:
            rows += receipt("pass", "2026-09-10T00:00:00Z")
        with (tmp / "run.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(rows)
        return tmp

    def test_an_authorized_skip_is_the_fourth_receipt_and_is_disclosed(self):
        payload, refusal = self.decide(self.build_with_excusal())
        self.assertIsNone(refusal, refusal)
        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual(len(payload["instrument_receipts"]), 4)
        harness = payload["instrument_receipts"][self.HARNESS_STEP]
        self.assertEqual(harness["verdict"], "skipped")
        self.assertEqual(harness["authorized_by"], "mike-maziarz")
        self.assertEqual(len(payload["excused_instruments"]), 1)
        self.assertIn("release-harness", payload["excused_instruments"][0])
        self.assertIn("mike-maziarz", payload["excused_instruments"][0])
        self.assertIn("EXCUSED", payload["rationale"])

    def test_a_skipped_receipt_nobody_signed_still_refuses(self):
        """The mutation direction: strip the signature, the excusal is a gap."""
        payload, refusal = self.decide(self.build_with_excusal(signed=False))
        self.assertIsNotNone(refusal)
        self.assertIn("authorized_by", refusal)
        self.assertEqual(payload["verdict"], "fail")

    def test_three_receipts_and_no_excusal_still_refuse(self):
        """The skip must be a receipt; an absent instrument stays a fail."""
        present = [u for u in freeze.INSTRUMENTS if u != self.HARNESS_STEP]
        payload, refusal = self.decide(self.build(receipts=present))
        self.assertIsNotNone(refusal)
        self.assertIn("release-harness", refusal)

    def test_excusing_an_instrument_that_already_passed_refuses(self):
        payload, refusal = self.decide(self.build_with_excusal(after_pass=True))
        self.assertIsNotNone(refusal)
        self.assertIn("excused afterwards", refusal)

    def test_a_real_pass_after_an_excusal_governs_and_nothing_stays_excused(self):
        payload, refusal = self.decide(self.build_with_excusal(then_pass=True))
        self.assertIsNone(refusal, refusal)
        self.assertEqual(payload["instrument_receipts"][self.HARNESS_STEP]["verdict"], "pass")
        self.assertEqual(payload["excused_instruments"], [])
        self.assertNotIn("EXCUSED", payload["rationale"])

    def test_the_emitted_freeze_carries_the_excusal(self):
        """A reader of package_frozen alone must not see four verified instruments."""
        tmp = self.build_with_excusal()
        code = freeze.main(["--run-dir", str(tmp), "--candidate",
                            str(tmp / "tropo-1.89.0.zip"), "--emit"])
        self.assertEqual(code, 0)
        rows = [json.loads(l) for l in (tmp / "run.jsonl").read_text().splitlines()]
        frozen = [r for r in rows if r.get("event") == "tropo.release.package_frozen"]
        self.assertEqual(len(frozen), 1)
        data = frozen[0]["data"]
        self.assertEqual(len(data["excused_instruments"]), 1)
        self.assertIn("release-harness", data["excused_instruments"][0])
        self.assertIn("EXCUSED", data["note"])


class ExitCodeTests(unittest.TestCase):
    def test_earned_freeze_exits_zero_and_refusal_exits_one(self):
        helper = FreezeDecisionTests("run")
        helper.addCleanup = lambda *a, **k: None

        earned = helper.build()
        self.assertEqual(
            freeze.main(["--run-dir", str(earned),
                         "--candidate", str(earned / "tropo-1.89.0.zip")]),
            freeze.EXIT_FROZEN,
        )

        refused = helper.build(mutate_bytes=True)
        self.assertEqual(
            freeze.main(["--run-dir", str(refused), "--candidate",
                         str(refused / "tropo-1.89.0.zip"), "--quiet"]),
            freeze.EXIT_REFUSED,
        )
        shutil.rmtree(earned, ignore_errors=True)
        shutil.rmtree(refused, ignore_errors=True)

    def test_a_missing_run_directory_is_misuse(self):
        self.assertEqual(
            freeze.main(["--run-dir", "/tmp/not-a-run", "--candidate", "/tmp/x.zip"]),
            freeze.EXIT_MISUSE,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
