#!/usr/bin/env python3
"""v1.91 S3 AC7 (176a8995) — the activation carries release_entry_uid at lock time.

v1.88's activation (25648118) carried `release_entry_uid`; the v1.90 lock
gesture never wrote it onto a6ebf96e and `fire` refused for it — metis-g110
hand-added the field on 2026-08-22 (see that entry's own comment). The fire
reads it through _release_entry_uid_for in tropo-publish-release.py:
`activation.frontmatter.release_entry_uid`, refusing when empty.

Grounding in tropo-lock-release-plan.py plan_release_lock: the lock MINTS
release_uid and writes it onto the plan (`release_entry_uid`), the run
(_render_run), the release entry, and the run.jsonl run_created row — but the
activation is rendered by ignition.render_activation(activation_uid, root_uid,
run_uid, pipeline_uid, subject_uid, subject_kind, actor, today), which is never
handed the release uid. tropo-lock-dev-spec.py is not the writer here: the
release lock borrows only its render_lock_run_created, where it already passes
release_entry_uid in `extra`.

CONTRACT THIS TEST DRIVES (red at birth, 2026-08-23): after a clean release-plan
lock, the activation the lock opened carries `release_entry_uid` equal to the
plan's own `release_entry_uid`, in the same transaction (no second writer).
Fixture: the isolated studio from test_release_plan_lock_end_to_end (lock
transaction roots patched to a temp tree; nothing touches the real vault).
Mutation clause: drop the propagation and this goes RED.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_release_plan_lock_end_to_end as e2e  # noqa: E402  (module ref only:
# naming its TestCase here would re-collect its 39 tests under this file)
rl = e2e.rl


class LockWritesEntryUidTests(unittest.TestCase):
    def setUp(self) -> None:
        # Borrow the e2e fixture as an object, not as a base class.
        self.fx = e2e.ReleaseLockEndToEnd("test_a_clean_lock_writes_the_whole_transaction")
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        code, message = self.fx._lock()
        self.assertEqual(code, 0, f"fixture: the lock itself refused: {message}")
        self.plan = rl.read_entry("b1a00001", self.fx.files)["frontmatter"]
        self.activation_uid = str(self.plan["release_activation_uid"])
        self.activation = rl.read_entry(self.activation_uid, self.fx.files)["frontmatter"]

    def test_the_activation_carries_the_plans_release_entry_uid(self) -> None:
        expected = str(self.plan.get("release_entry_uid") or "")
        self.assertTrue(expected, "fixture: the lock wrote no release_entry_uid on the plan")
        actual = str(self.activation.get("release_entry_uid") or "")
        self.assertEqual(
            actual, expected,
            f"activation {self.activation_uid} names release_entry_uid={actual!r} "
            f"but the plan it opened for binds {expected!r} — the lock gesture does "
            f"not propagate the entry uid onto the activation, so fire's "
            f"_release_entry_uid_for refuses after the human said yes (S3 AC7; "
            f"v1.90 a6ebf96e was patched by hand)")

    def test_the_run_and_entry_agree_with_the_activation(self) -> None:
        """The four records the lock authors must name ONE release entry."""
        expected = str(self.plan.get("release_entry_uid") or "")
        run = rl.read_entry(str(self.plan["release_pipeline_run_uid"]), self.fx.files)["frontmatter"]
        entry = rl.read_entry(expected, self.fx.files)
        self.assertIsNotNone(entry, f"release entry {expected} was not authored")
        self.assertEqual(str(run.get("release_entry_uid") or ""), expected,
                         "the run does not bind the plan's release entry")
        self.assertEqual(str(self.activation.get("release_entry_uid") or ""), expected,
                         f"activation {self.activation_uid} disagrees with plan/run/entry "
                         f"on release_entry_uid (S3 AC7)")


if __name__ == "__main__":
    unittest.main()
