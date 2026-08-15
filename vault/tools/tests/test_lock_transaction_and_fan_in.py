"""Stage 4 substrate: the shared lock transaction and the fan-in/reservation gate.

Covers 0a0a6777 AC4 ("lock atomically reserves every member and opens one
immutable release run ... malformed/duplicate/partial-write cases leave zero
partial state") and AC5 (the seven row bindings and the reservation gate).

Every refusal here has a negative control, because a test that only asserts
"this raises" passes just as well against a function that raises on everything.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from lib import fan_in, lock_transaction as lt  # noqa: E402


def _row(**overrides) -> dict:
    row = {
        "dev_spec_uid": "aaaaaaaa",
        "dev_spec_sha256": "a" * 64,
        "activation_uid": "bbbbbbbb",
        "pipeline_run_uid": "cccccccc",
        "tested_final_commit": "d" * 40,
        "completion_receipt_sha256": "e" * 64,
        "acceptance_evidence_sha256": "f" * 64,
    }
    row.update(overrides)
    return row


class TheTransactionIsPureUntilItIsNot(unittest.TestCase):
    """AC4's "zero partial state", as a property of the shape rather than of care."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="lock-txn-")).resolve()
        self._orig_journal = lt.LOCK_JOURNAL_DIR
        self._orig_lock = lt.WORKSPACE_LOCK_PATH
        self._orig_root = lt.VAULT_ROOT
        lt.LOCK_JOURNAL_DIR = self.tmp / "journal"
        lt.WORKSPACE_LOCK_PATH = self.tmp / "journal" / "ignition.lock"
        # The containment check measures against VAULT_ROOT, so the fixture's
        # own tmp tree has to BE the root for these paths to be legal.
        lt.VAULT_ROOT = self.tmp

    def tearDown(self) -> None:
        lt.LOCK_JOURNAL_DIR = self._orig_journal
        lt.WORKSPACE_LOCK_PATH = self._orig_lock
        lt.VAULT_ROOT = self._orig_root

    def _apply(self, build, **kwargs):
        """Build AND commit inside one exclusive span, which is the contract.

        Takes a FACTORY, not a ready-made plan. A plan carries the acquisition
        its reads were taken under, so constructing outside the span and
        applying inside is a shape production does not have — and papering over
        it with a binding hatch is exactly what argus-a147 ruled out.
        """
        with lt.exclusive_workspace_lock():
            plan = build() if callable(build) else build
            if plan.lock_token is None:
                self.fail(
                    "this fixture built its plan OUTSIDE the span. Pass a factory "
                    "so construction happens inside, the way both ignitions do — "
                    "there is no binding escape hatch any more, by argus-a147's "
                    "ruling, and there should not be.")
            return lt.apply_plan(plan, **kwargs)

    def _plan(self) -> lt.LockPlan:
        """A FACTORY, called inside the span by `_apply`.

        Returning a ready-made plan is what the removed binding hatch existed to
        paper over. Constructing here, under the caller's lock, is what both
        ignitions do.
        """
        plan = lt.LockPlan(kind="release-plan-lock", subject_uid="12345678", actor="talos")
        plan.create(self.tmp / "a.md", "alpha\n")
        plan.create(self.tmp / "b.md", "beta\n")
        return plan

    def test_a_clean_plan_applies_every_operation_and_journals_applied(self) -> None:
        """The control. Without it, every refusal below passes for a no-op."""
        journal = self._apply(self._plan, recycle=None)
        self.assertEqual((self.tmp / "a.md").read_text(), "alpha\n")
        self.assertEqual((self.tmp / "b.md").read_text(), "beta\n")
        body = json.loads(journal.read_text())
        self.assertEqual(body["state"], "applied")
        self.assertEqual(len(body["operations"]), 2)

    def test_a_duplicate_target_refuses_before_writing_anything(self) -> None:
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
            plan.create(self.tmp / "same.md", "one\n")
            plan.create(self.tmp / "same.md", "two\n")
            return plan
        with self.assertRaises(lt.LockRefusal) as caught:
            self._apply(build, recycle=None)
        self.assertIn("twice", str(caught.exception))
        self.assertFalse((self.tmp / "same.md").exists())
        # The directory itself now exists because the workspace lock lives in
        # it, so the probe is the journals, not the folder. The claim is
        # unchanged: a refusal must not journal, because nothing was attempted.
        self.assertEqual(
            sorted(p.name for p in lt.LOCK_JOURNAL_DIR.glob("*.json")), [],
            "a refusal wrote a journal; nothing was attempted",
        )

    def test_a_conflict_in_the_LAST_operation_stops_the_FIRST_one(self) -> None:
        """The claim two-phase design exists to make.

        A validate-as-you-write design would have written a.md before noticing
        the collision on b.md, and 'zero partial state' would depend on an
        unwind path being remembered. Here there is nothing to unwind.
        """
        (self.tmp / "b.md").write_text("i am already here\n")
        with self.assertRaises(lt.LockRefusal):
            self._apply(self._plan, recycle=None)
        self.assertFalse((self.tmp / "a.md").exists(),
                         "the first operation landed before the last was checked")
        self.assertEqual((self.tmp / "b.md").read_text(), "i am already here\n")

    def test_a_patch_refuses_when_the_file_moved_after_planning(self) -> None:
        target = self.tmp / "spec.md"
        target.write_text("original\n")
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
            plan.patch(target, "original\n", "locked\n")
            return plan

        target.write_text("someone else got here first\n")

        with self.assertRaises(lt.LockRefusal) as caught:
            self._apply(build, recycle=None)
        self.assertIn("changed after this lock was planned", str(caught.exception))
        self.assertEqual(target.read_text(), "someone else got here first\n",
                         "the concurrent write was overwritten")

    def test_the_patch_guard_control_an_unchanged_file_applies(self) -> None:
        target = self.tmp / "spec.md"
        target.write_text("original\n")
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
            plan.patch(target, "original\n", "locked\n")
            return plan
        self._apply(build, recycle=None)
        self.assertEqual(target.read_text(), "locked\n")

    def test_a_partial_write_unwinds_and_says_what_it_could_not_unwind(self) -> None:
        """The only failure that needs the journal, exercised as a real failure.

        b.md is planned into a path that cannot be created (a.md is a file, so
        a.md/child is not a valid parent), so the second write fails after the
        first has landed.
        """
        def build():
            plan = lt.LockPlan(kind="release-plan-lock", subject_uid="12345678", actor="talos")
            plan.create(self.tmp / "a.md", "alpha\n")
            plan.create(self.tmp / "a.md" / "child.md", "unreachable\n")
            return plan

        with self.assertRaises(lt.LockApplyFailure) as caught:
            self._apply(build, recycle=None)

        self.assertFalse((self.tmp / "a.md").exists(),
                         "the landed write was not unwound")
        self.assertIn(str(self.tmp / "a.md"), caught.exception.undone)
        journal = lt.LOCK_JOURNAL_DIR / "release-plan-lock-12345678.json"
        self.assertEqual(json.loads(journal.read_text())["state"], "rolled-back")

    def test_the_journal_is_written_before_the_first_byte_of_effect(self) -> None:
        """Ordering is the recovery guarantee, so it is asserted, not assumed."""
        order: list[str] = []
        real_write = lt._atomic_write

        def watched(path: Path, content: str) -> None:
            order.append("journal" if path.parent == lt.LOCK_JOURNAL_DIR else "effect")
            real_write(path, content)

        lt._atomic_write = watched
        try:
            self._apply(self._plan, recycle=None)
        finally:
            lt._atomic_write = real_write
        self.assertEqual(order[0], "journal", f"effects preceded the journal: {order}")

    def test_a_governed_entry_is_recycled_on_undo_and_never_unlinked(self) -> None:
        """Principle 13 holds inside rollback, which is where it was broken before."""
        recycled: list[str] = []
        def build():
            plan = lt.LockPlan(kind="release-plan-lock", subject_uid="12345678", actor="talos")
            plan.create(self.tmp / "gov.md", "governed\n", governed=True)
            plan.create(self.tmp / "gov.md" / "child.md", "unreachable\n")
            return plan

        def fake_recycle(path: Path, reason: str) -> bool:
            recycled.append(path.name)
            path.unlink()
            return True

        with self.assertRaises(lt.LockApplyFailure):
            self._apply(build, recycle=fake_recycle)
        self.assertEqual(recycled, ["gov.md"],
                         "the governed entry was removed without going through recycle")

    def test_a_recycle_that_fails_strands_the_entry_rather_than_deleting_it(self) -> None:
        """The A82 defect, pinned: a rollback that cannot recycle must NOT unlink."""
        def build():
            plan = lt.LockPlan(kind="release-plan-lock", subject_uid="12345678", actor="talos")
            plan.create(self.tmp / "gov.md", "governed\n", governed=True)
            plan.create(self.tmp / "gov.md" / "child.md", "unreachable\n")
            return plan

        with self.assertRaises(lt.LockApplyFailure) as caught:
            self._apply(build, recycle=lambda path, reason: False)
        self.assertTrue((self.tmp / "gov.md").is_file(),
                        "a failed recycle hard-deleted a governed entry")
        self.assertIn(str(self.tmp / "gov.md"), caught.exception.stranded)

    def test_idempotence_compares_the_plan_digest_not_just_the_subject(self) -> None:
        """A second lock that would write DIFFERENT bytes is a conflict, not a retry."""
        applied_plan = {}

        def build():
            applied_plan["plan"] = self._plan()
            return applied_plan["plan"]

        self._apply(build, recycle=None)
        self.assertTrue(
            lt.already_applied("release-plan-lock", "12345678", applied_plan["plan"]))

        divergent = lt.LockPlan(kind="release-plan-lock", subject_uid="12345678", actor="talos")
        divergent.create(self.tmp / "a.md", "DIFFERENT\n")
        self.assertFalse(
            lt.already_applied("release-plan-lock", "12345678", divergent),
            "a conflicting lock was waved through as an idempotent retry",
        )


class ExactlyOneIgnitionWins(unittest.TestCase):
    """NO-GO item 1: the reservation race.

    Two processes that each re-scan reservations before either commits will both
    see the same member unclaimed. The lock has to span the whole
    gather-plan-commit sequence, not just the write.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ignition-lock-")).resolve()
        self.lock = self.tmp / "ignition.lock"

    def test_a_second_holder_is_refused_immediately_rather_than_hanging(self) -> None:
        with lt.exclusive_workspace_lock(path=self.lock):
            with self.assertRaises(lt.LockContention):
                # A different fd for the same file, which is what a second
                # process gets. flock is per-open-file-description.
                with lt.exclusive_workspace_lock(path=self.lock):
                    pass

    def test_two_real_processes_produce_exactly_one_winner(self) -> None:
        """The claim, exercised across process boundaries rather than fds."""
        script = self.tmp / "contend.py"
        script.write_text(
            "import sys, time\n"
            f"sys.path.insert(0, {str(TOOLS)!r})\n"
            "from lib import lock_transaction as lt\n"
            "from pathlib import Path\n"
            "try:\n"
            f"    with lt.exclusive_workspace_lock(path=Path({str(self.lock)!r})):\n"
            "        print('WON'); time.sleep(1.5)\n"
            "except lt.LockContention:\n"
            "    print('REFUSED')\n"
        )
        first = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True)
        time.sleep(0.5)
        second = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        first_out = first.communicate()[0].strip()
        self.assertEqual(first_out, "WON")
        self.assertEqual(second.stdout.strip(), "REFUSED",
                         "two processes both entered the ignition critical section")

    def test_the_lock_is_released_even_when_the_body_raises(self) -> None:
        """Otherwise one failed ignition wedges every later one."""
        with self.assertRaises(RuntimeError):
            with lt.exclusive_workspace_lock(path=self.lock):
                raise RuntimeError("boom")
        with lt.exclusive_workspace_lock(path=self.lock):
            pass  # acquiring again is the assertion

    def test_a_plan_from_a_previous_acquisition_cannot_apply(self) -> None:
        """NO-GO item 1's token, doing the thing a depth counter cannot.

        The lock was held, released, and retaken. A depth counter is positive
        again and would wave this through, but the plan's reads were taken under
        the earlier span and the world may have moved since.
        """
        with lt.exclusive_workspace_lock(path=self.lock):
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678",
                               actor="talos")
            plan.create(self.tmp / "x.md", "x\n")
            stale_token = plan.lock_token
            self.assertIsNotNone(stale_token)

        with lt.exclusive_workspace_lock(path=self.lock):
            self.assertNotEqual(lt.current_lock_token(), stale_token,
                                "a new acquisition reused the old token")
            with self.assertRaises(lt.LockRefusal) as caught:
                lt.apply_plan(plan, recycle=None)
        self.assertIn("built under lock acquisition", str(caught.exception))
        self.assertFalse((self.tmp / "x.md").exists())

    def test_the_acquisition_witness_cannot_be_reassigned(self) -> None:
        """argus-a147 residual 2: removing the named helper was not enough.

        While `lock_token` was a public writable attribute,
        `plan.lock_token = current_lock_token()` under a later acquisition
        laundered a stale plan exactly as well as the helper did — and with less
        to notice in review. Both the public name and the private one refuse
        after construction.
        """
        plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
        for attribute in ("lock_token", "_lock_token"):
            with self.subTest(attribute=attribute):
                with self.assertRaises(lt.LockRefusal):
                    setattr(plan, attribute, "forged-token")
        self.assertIsNone(plan.lock_token, "the witness was overwritten")

    def test_a_stale_plan_stays_refused_even_after_an_assignment_attempt(self) -> None:
        """The property that matters, not just the exception.

        A guard that raises while still mutating would be worse than none.
        """
        plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
        plan.create(self.tmp / "x.md", "x\n")
        with lt.exclusive_workspace_lock(path=self.lock):
            try:
                plan.lock_token = lt.current_lock_token()
            except lt.LockRefusal:
                pass
            with self.assertRaises(lt.LockRefusal) as caught:
                lt.apply_plan(plan, recycle=None)
        self.assertIn("built under lock acquisition", str(caught.exception))
        self.assertFalse((self.tmp / "x.md").exists())

    def test_no_binding_escape_hatch_exists_at_all(self) -> None:
        """argus-a147 ruled the affordance out, and he was right.

        I had added `bind_to_current_acquisition()` so fixture plans assembled
        from literals could bind inside the span, and guarded it with a test
        that production never called it. That guard protected today and not
        tomorrow: a public method on LockPlan that re-binds WITHOUT re-reading
        is a laundering primitive sitting in the library, one careless call away
        from blessing a stale plan. I flagged it for a ruling rather than
        deciding alone; the ruling was to delete it.

        Fixtures now build their plans inside the span, the way both ignitions
        do — which is also a truer fixture, since it exercises the shape
        production has.
        """
        source = (TOOLS / "lib" / "lock_transaction.py").read_text(encoding="utf-8")
        self.assertNotIn("def bind_to_current_acquisition", source)
        self.assertFalse(hasattr(lt.LockPlan, "bind_to_current_acquisition"))

    def test_apply_refuses_outside_the_span(self) -> None:
        """A caller that forgets the lock must not be trusted to have held it."""
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
            plan.create(self.tmp / "x.md", "x\n")
            return plan
        with self.assertRaises(lt.LockRefusal) as caught:
            lt.apply_plan(build(), recycle=None)
        self.assertIn("without the workspace lock", str(caught.exception))


class TheJournalCanActuallyPutItBack(unittest.TestCase):
    """NO-GO item 2: a journal of hashes is a diagnostic, not a recovery."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="journal-recovery-")).resolve()
        self._orig = (lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT)
        lt.LOCK_JOURNAL_DIR = self.tmp / "journal"
        lt.WORKSPACE_LOCK_PATH = self.tmp / "journal" / "ignition.lock"
        lt.VAULT_ROOT = self.tmp

    def tearDown(self) -> None:
        lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT = self._orig

    def _crashed_plan(self) -> None:
        """Apply a plan and leave the journal saying 'applying', as a crash would."""
        target = self.tmp / "spec.md"
        target.write_text("before\n")
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="deadbeef", actor="talos")
            plan.create(self.tmp / "new.md", "created\n")
            plan.patch(target, "before\n", "after\n")
            return plan
        with lt.exclusive_workspace_lock():
            lt.apply_plan(build(), recycle=None)
        journal = lt.LOCK_JOURNAL_DIR / "dev-spec-lock-deadbeef.json"
        body = json.loads(journal.read_text())
        body["state"] = "applying"
        journal.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")

    def test_the_journal_carries_enough_to_reconstruct_both_sides(self) -> None:
        self._crashed_plan()
        body = json.loads((lt.LOCK_JOURNAL_DIR / "dev-spec-lock-deadbeef.json").read_text())
        patch_op = next(o for o in body["operations"] if o["op"] == "patch")
        self.assertEqual(patch_op["pre_content"], "before\n")
        self.assertEqual(patch_op["post_content"], "after\n")

    def test_replay_rolls_a_crashed_transaction_all_the_way_back(self) -> None:
        self._crashed_plan()
        self.assertEqual((self.tmp / "spec.md").read_text(), "after\n")
        self.assertTrue((self.tmp / "new.md").is_file())

        reports = lt.recover_incomplete()

        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["outcome"], "rolled-back")
        self.assertEqual((self.tmp / "spec.md").read_text(), "before\n",
                         "the patch was not reverted")
        self.assertFalse((self.tmp / "new.md").exists(),
                         "the created file was not removed")

    def test_recovery_stops_rather_than_guessing_when_a_file_diverged(self) -> None:
        """Someone edited it after the crash. Guessing here is how a recovery
        becomes the corruption it was called to fix."""
        self._crashed_plan()
        (self.tmp / "spec.md").write_text("a human fixed this by hand\n")

        reports = lt.recover_incomplete()

        self.assertEqual(reports[0]["outcome"], "needs-operator")
        # The report explains rather than just naming, so match on containment.
        self.assertTrue(
            any(str(self.tmp / "spec.md") in problem for problem in reports[0]["diverged"]),
            f"the diverged file is not named in the report: {reports[0]['diverged']}")
        # And nothing was rolled back: classification now happens for the WHOLE
        # journal before any mutation, so one divergence means zero changes
        # rather than a partial undo that stopped where it got confused.
        self.assertEqual(reports[0]["recovered"], [])
        self.assertTrue((self.tmp / "new.md").is_file(),
                        "a created file was removed despite the refusal to recover")
        self.assertEqual((self.tmp / "spec.md").read_text(),
                         "a human fixed this by hand\n",
                         "recovery overwrote a hand edit it did not understand")

    def test_recovery_recycles_a_governed_create_and_never_unlinks_it(self) -> None:
        """Principle 13 holds inside RECOVERY, not just inside rollback.

        A mutation making recovery unlink governed creates survived the suite:
        every recovery test used non-governed files, so the governed branch was
        never executed. A recovery that hard-deletes governed substrate is worse
        than the crash it is cleaning up after.
        """
        governed = self.tmp / "gov.md"
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="deadbeef", actor="talos")
            plan.create(governed, "governed body\n", governed=True)
            return plan
        with lt.exclusive_workspace_lock():
            lt.apply_plan(build(), recycle=None)

        journal = lt.LOCK_JOURNAL_DIR / "dev-spec-lock-deadbeef.json"
        body = json.loads(journal.read_text())
        body["state"] = "applying"
        journal.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")

        recycled: list = []

        def spy(path, reason):
            recycled.append(path.name)
            path.unlink()
            return True

        reports = lt.recover_incomplete(recycle=spy)

        self.assertEqual(reports[0]["outcome"], "rolled-back")
        self.assertEqual(recycled, ["gov.md"],
                         "the governed entry was removed without going through recycle")

    def test_recovery_strands_a_governed_create_when_recycle_fails(self) -> None:
        """The other half: it must NOT escalate to unlink."""
        governed = self.tmp / "gov.md"
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="deadbeef", actor="talos")
            plan.create(governed, "governed body\n", governed=True)
            return plan
        with lt.exclusive_workspace_lock():
            lt.apply_plan(build(), recycle=None)

        journal = lt.LOCK_JOURNAL_DIR / "dev-spec-lock-deadbeef.json"
        body = json.loads(journal.read_text())
        body["state"] = "applying"
        journal.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")

        reports = lt.recover_incomplete(recycle=lambda path, reason: False)

        self.assertTrue(governed.is_file(),
                        "recovery hard-deleted a governed entry when recycle failed")
        self.assertTrue(any("recycle unavailable" in note
                            for note in reports[0]["untouched"]),
                        f"the stranded entry was not reported: {reports[0]}")

    def test_a_completed_transaction_is_not_rolled_back_by_recovery(self) -> None:
        """The control. Without it, replay that undoes everything would pass."""
        target = self.tmp / "spec.md"
        target.write_text("before\n")
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="deadbeef", actor="talos")
            plan.patch(target, "before\n", "after\n")
            return plan
        with lt.exclusive_workspace_lock():
            lt.apply_plan(build(), recycle=None)

        self.assertEqual(lt.recover_incomplete(), [])
        self.assertEqual(target.read_text(), "after\n")


class WritesStayInsideTheWorkspace(unittest.TestCase):
    """NO-GO item 6. Harm named: a write that escapes damages substrate the
    studio does not govern and the rollback cannot restore."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="path-safety-")).resolve()
        self.outside = Path(tempfile.mkdtemp(prefix="outside-")).resolve()
        self._orig = (lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT)
        lt.LOCK_JOURNAL_DIR = self.tmp / "journal"
        lt.WORKSPACE_LOCK_PATH = self.tmp / "journal" / "ignition.lock"
        lt.VAULT_ROOT = self.tmp

    def tearDown(self) -> None:
        lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT = self._orig

    def _apply(self, build):
        """Factory, for the same reason as the helper above."""
        with lt.exclusive_workspace_lock():
            return lt.apply_plan(build() if callable(build) else build, recycle=None)

    def test_a_traversal_target_is_refused(self) -> None:
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
            plan.create(self.tmp / ".." / "escaped.md", "nope\n")
            return plan
        with self.assertRaises(lt.LockRefusal) as caught:
            self._apply(build)
        self.assertIn("outside the studio", str(caught.exception))

    def test_a_symlinked_parent_that_leaves_the_workspace_is_refused(self) -> None:
        (self.tmp / "bridge").symlink_to(self.outside, target_is_directory=True)
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
            plan.create(self.tmp / "bridge" / "escaped.md", "nope\n")
            return plan
        with self.assertRaises(lt.LockRefusal) as caught:
            self._apply(build)
        self.assertIn("outside the studio", str(caught.exception))
        self.assertFalse((self.outside / "escaped.md").exists())

    def test_a_symlink_AT_the_target_is_not_followed(self) -> None:
        """Planting a symlink where the plan will write must not redirect it."""
        victim = self.outside / "victim.md"
        victim.write_text("original\n")
        (self.tmp / "decoy.md").symlink_to(victim)
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
            plan.patch(self.tmp / "decoy.md", "original\n", "overwritten\n")
            return plan
        with self.assertRaises(lt.LockRefusal) as caught:
            self._apply(build)
        self.assertIn("symlink", str(caught.exception))
        self.assertEqual(victim.read_text(), "original\n")

    def test_a_symlink_planted_AFTER_preflight_is_still_not_followed(self) -> None:
        """NO-GO item 6: path safety at WRITE time, not only preflight.

        Preflight runs once over the whole plan and the writes happen
        afterwards. That gap is a TOCTOU window — a symlink planted at a target
        in between would be followed, and the transaction would modify a file it
        never named and cannot roll back.
        """
        victim = self.outside / "victim.md"
        victim.write_text("original\n")
        target = self.tmp / "later.md"

        real_preflight = lt._preflight

        def plant_then_preflight(plan):
            real_preflight(plan)          # passes: target is an ordinary path
            target.symlink_to(victim)     # the window

        lt._preflight = plant_then_preflight
        try:
            def build():
                plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
                plan.create(target, "payload\n")
                return plan
            # LockApplyFailure, not LockRefusal: by write time the journal is
            # already committed, so this is a mid-apply abort that unwinds —
            # which is the honest classification. A refusal means nothing was
            # attempted, and here something was.
            with self.assertRaises(lt.LockApplyFailure) as caught:
                self._apply(build)
        finally:
            lt._preflight = real_preflight

        self.assertIn("became a symlink", str(caught.exception))
        self.assertEqual(victim.read_text(), "original\n",
                         "the write followed a symlink planted after preflight")

    def test_two_spellings_of_one_target_are_one_target(self) -> None:
        """Alias canonicalisation before duplicate detection (item 6).

        My first version of this used `a/b.md` and `a/./b.md` and was VACUOUS:
        pathlib normalises `.` away at construction, so both were already the
        same object and the duplicate check passed with or without
        canonicalisation. A mutation removing the canonicalisation survived it.

        A symlinked directory INSIDE the workspace is a real alias — two
        genuinely different path strings reaching one file — and it is the shape
        that actually occurs, since a workspace may contain internal symlinks.
        """
        real_dir = self.tmp / "vault" / "files"
        real_dir.mkdir(parents=True)
        (self.tmp / "alias").symlink_to(real_dir, target_is_directory=True)

        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
            plan.create(real_dir / "dup.md", "one\n")
            plan.create(self.tmp / "alias" / "dup.md", "two\n")
            return plan
        with self.assertRaises(lt.LockRefusal) as caught:
            self._apply(build)
        self.assertIn("twice", str(caught.exception))
        self.assertFalse((real_dir / "dup.md").exists())

    def test_the_control_an_ordinary_path_inside_is_allowed(self) -> None:
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678", actor="talos")
            plan.create(self.tmp / "vault" / "files" / "ok.md", "fine\n")
            return plan
        self._apply(build)
        self.assertEqual((self.tmp / "vault" / "files" / "ok.md").read_text(), "fine\n")


class TheRecyclePathIsReal(unittest.TestCase):
    """The bug my own tests could not see, because they injected a fake.

    `_default_recycle` pointed at .tropo/scripts/tropo-recycle.py, which does not
    exist — so `is_file()` was always False, rollback NEVER recycled, and every
    governed entry took the stranded branch. Principle 13 held for the wrong
    reason. Found by argus-a147's review.
    """

    def test_the_default_recycle_script_actually_exists(self) -> None:
        script = lt.VAULT_ROOT / "vault" / "tools" / "tropo-recycle.py"
        self.assertTrue(script.is_file(), f"recycle script not at {script}")

    def test_the_source_does_not_name_the_retired_location(self) -> None:
        body = (TOOLS / "lib" / "lock_transaction.py").read_text(encoding="utf-8")
        function = body[body.index("def _default_recycle"):]
        function = function[: function.index("\ndef ", 1)]
        self.assertIn('"vault" / "tools"', function)
        self.assertNotIn('".tropo" / "scripts" / "tropo-recycle.py"', function)


class TheFanInRowBindsAllSeven(unittest.TestCase):

    def test_a_complete_row_validates(self) -> None:
        """Control: without it, every missing-field test below proves nothing."""
        row = fan_in.validate_row(_row())
        self.assertEqual(row.dev_spec_uid, "aaaaaaaa")

    def test_every_single_binding_is_load_bearing(self) -> None:
        """Drop each field in turn. AC5 names seven; seven must be required."""
        for field_name in fan_in.REQUIRED_ROW_FIELDS:
            with self.subTest(dropped=field_name):
                broken = _row()
                del broken[field_name]
                with self.assertRaises(fan_in.FanInRefusal) as caught:
                    fan_in.validate_row(broken)
                self.assertIn(field_name, str(caught.exception))

    def test_a_present_but_unbinding_value_is_still_refused(self) -> None:
        """The failure a presence-only check would pass.

        `tested_final_commit: HEAD` has the field and identifies no tree; an
        abbreviated SHA identifies a prefix. Both render as a filled row.
        """
        for bad in ("HEAD", "d" * 7, "main", "d" * 39, "D" * 40):
            with self.subTest(commit=bad):
                with self.assertRaises(fan_in.FanInRefusal):
                    fan_in.validate_row(_row(tested_final_commit=bad))

    def test_the_digest_is_order_sensitive_because_the_member_list_is_ordered(self) -> None:
        first = fan_in.validate_row(_row(dev_spec_uid="11111111"))
        second = fan_in.validate_row(_row(dev_spec_uid="22222222"))
        self.assertNotEqual(
            fan_in.manifest_digest([first, second]),
            fan_in.manifest_digest([second, first]),
            "two different plans share a fan-in digest",
        )

    def test_the_digest_is_stable_for_the_same_rows(self) -> None:
        rows = [fan_in.validate_row(_row())]
        self.assertEqual(fan_in.manifest_digest(rows), fan_in.manifest_digest(rows))


class TheReservationGate(unittest.TestCase):

    DONE = {"uid": "aaaaaaaa", "status": "done"}

    def test_a_done_unreserved_spec_passes(self) -> None:
        """Control."""
        fan_in.assert_member_is_fannable(self.DONE, [], "plan0001")

    def test_an_unfinished_spec_is_refused(self) -> None:
        for status in ("active", "locked", "draft", "in-progress", ""):
            with self.subTest(status=status):
                with self.assertRaises(fan_in.FanInRefusal) as caught:
                    fan_in.assert_member_is_fannable(
                        {"uid": "aaaaaaaa", "status": status}, [], "plan0001")
                self.assertIn("not 'done'", str(caught.exception))

    def test_a_spec_claimed_by_another_live_plan_is_refused(self) -> None:
        other = {"uid": "plan0002", "status": "locked", "dev_spec_uids": ["aaaaaaaa"]}
        with self.assertRaises(fan_in.FanInRefusal) as caught:
            fan_in.assert_member_is_fannable(self.DONE, [other], "plan0001")
        self.assertIn("plan0002", str(caught.exception))

    def test_a_plan_that_holds_no_reservation_does_not_block(self) -> None:
        """The control that keeps the gate from being a permanent lockout.

        Without this, cancelling a release would strand its members forever and
        the only cure would be editing history. `design` and `specify` are
        pre-lock, so they have claimed nothing yet even when they list members.
        """
        for status in ("design", "specify", "done", "cancelled"):
            with self.subTest(status=status):
                released = {"uid": "plan0002", "status": status,
                            "dev_spec_uids": ["aaaaaaaa"]}
                fan_in.assert_member_is_fannable(self.DONE, [released], "plan0001")

    def test_every_releasing_status_is_a_real_capsule_enum_value(self) -> None:
        """The guard on my own worst habit.

        I first wrote this set as {locked, active, in-progress, building}; the
        last two are not in the release-plan capsule's enforced_enums. Inventing
        enum values is exactly what argus-a147 corrected hours earlier, so the
        set is now checked against the capsule instead of my memory of it.
        """
        capsule = (TOOLS.parent / "capsules" / "tropo-release-plan.capsule.md")
        text = capsule.read_text(encoding="utf-8")
        block = text[text.index("enforced_enums:"):text.index("meta_status_rollup:")]
        declared = {line.strip("- ").strip()
                    for line in block.splitlines() if line.strip().startswith("- ")}
        declared.add("locked")  # added by 0a0a6777 §3
        unknown = fan_in.RESERVATION_RELEASING_STATUSES - declared
        self.assertEqual(unknown, set(),
                         f"invented status value(s) not in the capsule enum: {unknown}")

    def test_an_unrecognized_status_fails_CLOSED_and_keeps_the_reservation(self) -> None:
        """A typo must not silently release a claim.

        Refusing a claim is recoverable; two live releases both attesting to the
        same work is not. Same direction as the manifest-unreadable correction.
        """
        typo = {"uid": "plan0002", "status": "lockd", "dev_spec_uids": ["aaaaaaaa"]}
        with self.assertRaises(fan_in.FanInRefusal):
            fan_in.assert_member_is_fannable(self.DONE, [typo], "plan0001")

    def test_re_locking_the_same_plan_is_a_retry_not_a_self_conflict(self) -> None:
        itself = {"uid": "plan0001", "status": "locked", "dev_spec_uids": ["aaaaaaaa"]}
        fan_in.assert_member_is_fannable(self.DONE, [itself], "plan0001")

    def test_a_duplicate_member_is_refused_by_build_rows(self) -> None:
        member = {"dev_spec": self.DONE, "row": _row()}
        with self.assertRaises(fan_in.FanInRefusal) as caught:
            fan_in.build_rows([member, member], [], "plan0001")
        self.assertIn("twice", str(caught.exception))

    def test_an_empty_plan_is_refused(self) -> None:
        with self.assertRaises(fan_in.FanInRefusal) as caught:
            fan_in.build_rows([], [], "plan0001")
        self.assertIn("nothing to fan in", str(caught.exception))

    def test_build_rows_is_all_or_nothing(self) -> None:
        """One bad member stops the plan rather than silently shrinking the release."""
        good = {"dev_spec": self.DONE, "row": _row()}
        bad = {"dev_spec": {"uid": "bbbbbbbb", "status": "active"},
               "row": _row(dev_spec_uid="bbbbbbbb")}
        with self.assertRaises(fan_in.FanInRefusal):
            fan_in.build_rows([good, bad], [], "plan0001")

    def test_the_rendered_manifest_carries_its_own_digest(self) -> None:
        rows = fan_in.build_rows([{"dev_spec": self.DONE, "row": _row()}], [], "plan0001")
        body = json.loads(fan_in.render_manifest(rows, "plan0001"))
        self.assertEqual(body["fan_in_digest"], fan_in.manifest_digest(rows))
        self.assertEqual(body["row_count"], 1)


class TheCapsuleAmendmentIsActuallyAdditive(unittest.TestCase):
    """v1.6 on a3f1e7b2, authorized by 0a0a6777's committed_substrate.

    "Additive, non-breaking" is the claim every capsule amendment in this
    studio's history makes, and it is worth exactly as much as the check behind
    it. These assert the two things that would make it false.
    """

    CAPSULE = TOOLS.parent / "capsules" / "tropo-release-plan.capsule.md"

    def test_every_locked_instance_satisfies_the_new_requirements(self) -> None:
        """The additive amendment remains true after the first real ignition.

        The original migration assertion required that no plan was locked. That
        was useful only on the amendment's landing tree and became guaranteed to
        fail as soon as the release pipeline did its job. The durable invariant
        is that every locked instance carries the complete lock contract.
        """
        import yaml
        files = TOOLS.parent / "files"
        plans: list[str] = []
        locked: list[tuple[str, dict]] = []
        for path in files.glob("*.md"):
            parts = path.read_text(encoding="utf-8", errors="replace").split("---")
            if len(parts) < 3:
                continue
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except Exception:
                continue
            if isinstance(fm, dict) and fm.get("type") == "release-plan":
                plans.append(path.stem)
                if str(fm.get("status")) == "locked":
                    locked.append((path.stem, fm))
        self.assertGreater(len(plans), 0, "no release-plans found; the corpus scan is broken")
        required = {
            "dev_spec_uids",
            "fan_in_manifest_ref",
            "fan_in_digest",
            "release_activation_uid",
            "release_pipeline_run_uid",
        }
        for uid, fm in locked:
            self.assertFalse(
                missing := sorted(key for key in required if not fm.get(key)),
                f"locked release-plan {uid} is missing its lock contract: {missing}",
            )

    def test_the_amendment_records_its_authorization(self) -> None:
        """A lock-break with no recorded authority is indistinguishable from an
        unauthorized edit six months later."""
        text = self.CAPSULE.read_text(encoding="utf-8")
        self.assertIn("v1_6_amendment_note:", text)
        note = text[text.index("v1_6_amendment_note:"):]
        note = note[: note.index("\nv1_5_amendment_note:")]
        self.assertIn("0a0a6777", note, "the authorizing spec is not named")
        self.assertIn("committed_substrate", note)
        self.assertIn("ADDITIVE", note, "the amendment does not state its blast radius")
        # And the authorization is real: the spec must actually name this capsule.
        spec = (TOOLS.parent / "files" / "0a0a6777.md").read_text(encoding="utf-8")
        self.assertIn("vault/capsules/tropo-release-plan.capsule.md", spec)

    def test_the_lifecycle_is_coherent_across_enum_table_and_transitions(self) -> None:
        """argus-a147: reconcile the lifecycle completely.

        The enforced enum has always been on `status:` while the lifecycle table
        and the transition list said `stage:`. They were the same lifecycle
        spoken two ways, which is survivable right up until a value is added to
        one and not the other — which is what my v1.6 did with `locked`, leaving
        the enum and the table disagreeing about which states exist.

        This asserts the three surfaces agree, so the next person to add a state
        cannot land it in only one of them.
        """
        text = self.CAPSULE.read_text(encoding="utf-8")

        enum_block = text[text.index("enforced_enums:"):text.index("meta_status_rollup:")]
        enum_values = {line.strip("- ").strip()
                       for line in enum_block.splitlines()
                       if line.strip().startswith("- ")}

        table = text[text.index("| `status:` | Meaning |"):text.index("**Valid transitions:**")]
        table_values = set(re.findall(r"^\| `([a-z]+)` \|", table, re.M))

        self.assertEqual(
            enum_values, table_values,
            f"the enum and the lifecycle table disagree: only in enum "
            f"{sorted(enum_values - table_values)}, only in table "
            f"{sorted(table_values - enum_values)}")

        transitions = text[text.index("**Valid transitions:**"):text.index("## 4. Validation Rules")]
        self.assertIn("`specify → locked`", transitions,
                      "the lock transition is not in the transition list")
        self.assertIn("no transition OUT of `locked`", transitions,
                      "nothing states that a locked plan cannot be unlocked")

    def test_status_is_declared_canonical_over_the_legacy_stage_spelling(self) -> None:
        """Two spellings for one lifecycle is how they drifted apart.

        Renaming `stage:` in existing instances would be a migration nobody
        asked for, so the capsule declares which one is canonical and reads the
        other as a synonym instead.
        """
        text = self.CAPSULE.read_text(encoding="utf-8")
        self.assertIn("The canonical field is **`status:`**", text)
        self.assertIn("legacy spelling", text)

    def test_all_five_contract_fields_and_the_new_enum_value_landed(self) -> None:
        text = self.CAPSULE.read_text(encoding="utf-8")
        for field_name in ("dev_spec_uids", "fan_in_manifest_ref", "fan_in_digest",
                           "release_activation_uid", "release_pipeline_run_uid"):
            with self.subTest(field=field_name):
                self.assertIn(f"`{field_name}`", text)
        enum_block = text[text.index("enforced_enums:"):text.index("meta_status_rollup:")]
        self.assertIn("- locked", enum_block)


if __name__ == "__main__":
    unittest.main()
