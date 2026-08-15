"""AC8 closure saga: public-but-open, never falsely closed.

P6, P7, P8, P13, P14 and P15 of the preflight matrix. The property under test
is not that closure works — it is what happens when it doesn't. Publication
cannot be rolled back, so a crash after the receipt must leave records that are
incomplete rather than wrong, and a retry must converge on exactly one closed
state without duplicating the things that happen once.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_closure as rc  # noqa: E402

RUN = "abcdef12"
RECEIPT = "9" * 64
TX = "tx-1987"


def published(receipt=RECEIPT):
    return {"type": rc.PUBLISHED_EVENT, "data": {"receipt_sha256": receipt}}


def closed(receipt=RECEIPT):
    return {"type": rc.CLOSED_EVENT, "data": {"receipt_sha256": receipt}}


class TheJournalIsWrittenBeforeAnythingMoves(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ac8-closure-")).resolve()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_opening_writes_the_intent_to_disk(self):
        rc.open_or_resume_journal(self.root, RUN, RECEIPT, TX)
        path = rc.journal_path(self.root, RUN)
        self.assertTrue(path.is_file())
        self.assertEqual(json.loads(path.read_text())["receipt_sha256"], RECEIPT)

    def test_each_step_persists_as_it_completes(self):
        """A journal written only at the end records nothing about crashes."""
        journal = rc.open_or_resume_journal(self.root, RUN, RECEIPT, TX)
        rc.record_step(self.root, journal, "receipt_verified", verify=lambda: True)
        reread = rc.read_journal(self.root, RUN)
        self.assertEqual(reread.completed, ["receipt_verified"])
        self.assertFalse(reread.is_complete())

    def test_the_journal_marks_complete_only_when_every_step_is_done(self):
        journal = rc.open_or_resume_journal(self.root, RUN, RECEIPT, TX)
        for step in rc.STEPS[:-1]:
            rc.record_step(self.root, journal, step, verify=lambda: True)
            self.assertNotEqual(rc.read_journal(self.root, RUN).state, "complete")
        rc.record_step(self.root, journal, rc.STEPS[-1], verify=lambda: True)
        self.assertEqual(rc.read_journal(self.root, RUN).state, "complete")

    def test_an_unreadable_journal_refuses_rather_than_starting_fresh(self):
        rc.open_or_resume_journal(self.root, RUN, RECEIPT, TX)
        rc.journal_path(self.root, RUN).write_text("{not json", encoding="utf-8")
        with self.assertRaises(rc.ClosureRefusal) as caught:
            rc.read_journal(self.root, RUN)
        self.assertIn("half closed", str(caught.exception))


class AStepCannotBeRecordedWithoutReadingTheWorldBack(unittest.TestCase):
    """The machine for the mistake I kept making.

    Four times in two days a step got marked done because its code path
    finished rather than because its effect landed: reservations recorded as
    released without releasing them, substrate recorded as closed over a hook
    that closed one record of five, a closure event journalled with no emitter,
    and a mount marked ADOPTED over a file with no sidecar.

    This constrains the implementer, not the operator. It adds no denial to any
    user-facing path — it makes the false claim unrepresentable in the saga.
    """

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ac8-verify-")).resolve()
        self.journal = rc.open_or_resume_journal(self.root, RUN, RECEIPT, TX)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_recording_without_a_verifier_refuses(self):
        with self.assertRaises(rc.ClosureRefusal) as caught:
            rc.record_step(self.root, self.journal, "receipt_verified")
        self.assertIn("reads the world back", str(caught.exception))

    def test_a_verifier_that_reads_false_blocks_the_record(self):
        with self.assertRaises(rc.ClosureRefusal) as caught:
            rc.record_step(self.root, self.journal, "substrate_closed",
                           verify=lambda: False)
        self.assertIn("did not take effect", str(caught.exception))
        self.assertEqual(
            rc.read_journal(self.root, RUN).completed, [],
            "the step was journalled despite the world disagreeing",
        )

    def test_a_verifier_that_reads_true_records_normally(self):
        rc.record_step(self.root, self.journal, "receipt_verified",
                       verify=lambda: True)
        self.assertEqual(rc.read_journal(self.root, RUN).completed,
                         ["receipt_verified"])


class RetryConvergesAndNeverDuplicates(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ac8-retry-")).resolve()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_a_retry_owes_only_the_missing_steps(self):
        """P7: converge, do not redo. Re-emitting a once-only record is harm."""
        journal = rc.open_or_resume_journal(self.root, RUN, RECEIPT, TX)
        rc.record_step(self.root, journal, "receipt_verified", verify=lambda: True)
        rc.record_step(self.root, journal, "published_event_verified", verify=lambda: True)
        self.assertEqual(
            rc.resume_point(rc.read_journal(self.root, RUN)),
            ["substrate_closed", "reservations_released", "closure_event_emitted"],
        )

    def test_a_crash_at_every_point_leaves_a_replayable_journal(self):
        """P6: whatever step we die on, the remainder is knowable."""
        for stop_after in range(len(rc.STEPS)):
            with self.subTest(crashed_after=rc.STEPS[stop_after]):
                shutil.rmtree(self.root, ignore_errors=True)
                journal = rc.open_or_resume_journal(self.root, RUN, RECEIPT, TX)
                for step in rc.STEPS[:stop_after + 1]:
                    rc.record_step(self.root, journal, step, verify=lambda: True)
                recovered = rc.read_journal(self.root, RUN)
                self.assertEqual(
                    rc.resume_point(recovered),
                    list(rc.STEPS[stop_after + 1:]),
                )

    def test_a_fresh_run_with_no_journal_owes_everything(self):
        self.assertEqual(rc.resume_point(None), list(rc.STEPS))

    def test_a_second_receipt_for_one_run_refuses(self):
        """P8: two receipts is a contradiction, not a retry."""
        rc.open_or_resume_journal(self.root, RUN, RECEIPT, TX)
        with self.assertRaises(rc.ClosureRefusal) as caught:
            rc.open_or_resume_journal(self.root, RUN, "1" * 64, TX)
        self.assertIn("contradiction", str(caught.exception))
        self.assertEqual(
            rc.read_journal(self.root, RUN).receipt_sha256, RECEIPT,
            "the refusal modified the journal it refused over",
        )

    def test_a_different_transaction_id_refuses(self):
        rc.open_or_resume_journal(self.root, RUN, RECEIPT, TX)
        with self.assertRaises(rc.ClosureRefusal) as caught:
            rc.open_or_resume_journal(self.root, RUN, RECEIPT, "tx-other")
        self.assertIn("second closure", str(caught.exception))


class ExactlyOnceIsCheckedAgainstTheEventStream(unittest.TestCase):

    def test_one_published_event_resolves(self):
        self.assertEqual(
            rc.assert_one_published_event([published()], RECEIPT)["type"],
            rc.PUBLISHED_EVENT)

    def test_no_published_event_refuses(self):
        with self.assertRaises(rc.ClosureRefusal) as caught:
            rc.assert_one_published_event([], RECEIPT)
        self.assertIn("nothing to record", str(caught.exception))

    def test_two_published_events_refuse(self):
        """P13: two means it fired twice and this cannot say which."""
        with self.assertRaises(rc.ClosureRefusal) as caught:
            rc.assert_one_published_event([published(), published()], RECEIPT)
        self.assertIn("fired twice", str(caught.exception))

    def test_a_published_event_for_another_receipt_does_not_count(self):
        with self.assertRaises(rc.ClosureRefusal):
            rc.assert_one_published_event([published("7" * 64)], RECEIPT)


class ReadersAcceptEitherEventKey(unittest.TestCase):
    """A148 addendum evt_a9360f18f56fe472_00000026 item 2.

    Pipeline run JSONL writes the type under `event`; the vault event streams
    write it under `type`. Every reader here checked only `type`, so against a
    run folder they found nothing and reported a clean empty set — the gate
    passing because it saw no events at all, which is the worst way for a gate
    to succeed. Planted both spellings so a future reader cannot regress to one.
    """

    def test_a_run_shaped_published_event_is_found(self):
        run_shaped = {"event": rc.PUBLISHED_EVENT, "data": {"receipt_sha256": RECEIPT}}
        self.assertEqual(
            rc.assert_one_published_event([run_shaped], RECEIPT)["event"],
            rc.PUBLISHED_EVENT)

    def test_a_stream_shaped_published_event_is_still_found(self):
        self.assertEqual(
            rc.assert_one_published_event([published()], RECEIPT)["type"],
            rc.PUBLISHED_EVENT)

    def test_mixed_spellings_in_one_stream_both_count(self):
        """Two spellings of one publication is still two publications."""
        both = [published(), {"event": rc.PUBLISHED_EVENT,
                              "data": {"receipt_sha256": RECEIPT}}]
        with self.assertRaises(rc.ClosureRefusal) as caught:
            rc.assert_one_published_event(both, RECEIPT)
        self.assertIn("fired twice", str(caught.exception))


class TheSagaResumesRatherThanReplays(unittest.TestCase):
    """Blocker 8: world-ahead-of-journal is recovery, not contradiction.

    The commonest real crash is between doing a thing and journalling it. The
    previous saga replayed from the top and treated that state as a conflict,
    so the most likely recovery path was the one it refused. Only the reverse —
    journal claiming done over a world that disagrees — is a genuine
    contradiction.

    Exercised against the engine's own step shape rather than the engine (which
    needs a full run), because what is under test is the branching rule.
    """

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ac8-resume-")).resolve()
        self.journal = rc.open_or_resume_journal(self.root, RUN, RECEIPT, TX)
        self.performed = []

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _walk(self, world: dict):
        """The engine's branching rule, over a mutable fake world."""
        journal = rc.read_journal(self.root, RUN)
        recovered = []
        for name in rc.STEPS:
            verify = lambda n=name: world.get(n, False)
            if name in journal.completed:
                if not verify():
                    raise AssertionError(f"journal claims {name}, world disagrees")
                continue
            if verify():
                recovered.append(name)
                journal = rc.record_step(self.root, journal, name, verify=verify)
                continue
            self.performed.append(name)
            world[name] = True
            journal = rc.record_step(self.root, journal, name, verify=verify)
        return recovered

    def test_an_effect_that_landed_before_the_crash_is_recovered_not_redone(self):
        world = {"receipt_verified": True, "published_event_verified": True}
        recovered = self._walk(world)
        self.assertIn("receipt_verified", recovered)
        self.assertNotIn(
            "receipt_verified", self.performed,
            "a step whose effect already landed was performed again; for the "
            "closure event that would mean emitting a second one",
        )

    def test_the_remaining_steps_are_still_performed(self):
        self._walk({"receipt_verified": True})
        self.assertIn("substrate_closed", self.performed)
        self.assertIn("closure_event_emitted", self.performed)

    def test_a_second_pass_performs_nothing(self):
        world: dict = {}
        self._walk(world)
        self.performed.clear()
        self._walk(world)
        self.assertEqual(
            self.performed, [],
            "the saga replayed steps it had already completed",
        )

    def test_a_journal_claiming_done_over_a_disagreeing_world_refuses(self):
        journal = rc.read_journal(self.root, RUN)
        rc.record_step(self.root, journal, "substrate_closed", verify=lambda: True)
        with self.assertRaises(AssertionError):
            self._walk({"receipt_verified": True, "published_event_verified": True})


class ReservationAuthorityIsPlanStatusNotAField(unittest.TestCase):
    """A148's addendum evt_a9360f18f56fe472_00000024.

    I was one step from adding a `dev_spec.reserved_by` field and clearing it
    on closure. There is no such field, and inventing one would have created a
    second definition of "reserved" alongside the real one — where the real one
    is DERIVED from live release-plan status via find_conflicting_reservation.

    So making the owning plan terminal IS the release. There is nothing to
    clear, and the honest check is whether the canonical function now reports
    every member free.
    """

    def setUp(self):
        sys.path.insert(0, str(TOOLS))
        from lib import fan_in
        self.fan_in = fan_in

    def _plan(self, uid, status, members):
        return {"uid": uid, "status": status, "dev_spec_uids": list(members)}

    def test_a_live_plan_holds_its_members(self):
        plans = [self._plan("c0000001", "locked", ["aaaaaaaa"])]
        self.assertEqual(
            self.fan_in.find_conflicting_reservation("aaaaaaaa", plans, ""),
            "c0000001")

    def test_making_the_plan_terminal_releases_them(self):
        """`done` is in RESERVATION_RELEASING_STATUSES — closure IS the release."""
        plans = [self._plan("c0000001", "done", ["aaaaaaaa"])]
        self.assertIsNone(
            self.fan_in.find_conflicting_reservation("aaaaaaaa", plans, ""),
            "the plan is terminal but its members still read as reserved",
        )

    def test_a_plan_left_live_keeps_blocking_future_reservations(self):
        """The mutation A148 named: leave the plan live, future locks block."""
        for still_live in ("locked", "active", "build"):
            with self.subTest(status=still_live):
                plans = [self._plan("c0000001", still_live, ["aaaaaaaa"])]
                self.assertIsNotNone(
                    self.fan_in.find_conflicting_reservation("aaaaaaaa", plans, ""),
                    f"a plan left {still_live} should still hold its members",
                )

    def test_no_reserved_by_field_was_invented_anywhere(self):
        """Guards against the second definition I nearly created."""
        # Checks USE, not mentions: the comment explaining that this field
        # does not exist necessarily contains its name, and the first version
        # of this test failed on its own documentation.
        engine = (TOOLS / "9e7003b1.py").read_text(encoding="utf-8")
        used = re.findall(r'reserved_by["\']?\s*[:=\)]|get\(["\']reserved_by', engine)
        self.assertTrue(
            not used,
            f"the engine USES a reserved_by field ({len(used)} sites); "
            f"reservation authority is live plan status, and a second "
            f"definition of reserved is worse than none",
        )


class ReservationsAndDisagreement(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ac8-res-")).resolve()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

