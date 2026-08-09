"""Cut 4C daily ledger tamper, reservation, reconciliation, and flock plants."""
from __future__ import annotations

import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from lib import daily_spend


DAY = "2026-07-23"
NEXT_DAY = "2026-07-24"
POLICY_UID = "0c938a95"
POLICY_VERSION = "1.0.0"
LEGACY_VERSION = "1.1.0"
CURRENT_VERSION = "1.2.0"
CEILING = 5_000_000_000


def _reserve_worker(root, barrier, index, amount, output):
    try:
        barrier.wait()
        daily_spend.reserve(
            root,
            day=DAY,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=CEILING,
            reservation_id=f"{index:08x}",
            run_uid=f"{index + 100:08x}",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("private",),
            worst_case_nano_usd=amount,
        )
        output.put(True)
    except Exception:
        output.put(False)


def _cross_version_reserve_worker(
    root,
    barrier,
    index,
    amount,
    policy_version,
    output,
):
    try:
        barrier.wait()
        daily_spend.reserve(
            root,
            day=DAY,
            policy_uid=POLICY_UID,
            policy_version=policy_version,
            daily_ceiling_nano_usd=CEILING,
            reservation_id=f"{index:08x}",
            run_uid=f"{index + 100:08x}",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("os",),
            worst_case_nano_usd=amount,
        )
        output.put(True)
    except Exception:
        output.put(False)


def _reserve_then_wait(root, connection):
    daily_spend.reserve(
        root,
        day=DAY,
        policy_uid=POLICY_UID,
        policy_version=POLICY_VERSION,
        daily_ceiling_nano_usd=CEILING,
        reservation_id="feedbeef",
        run_uid="abcd1234",
        task="distill",
        model="claude-sonnet-4-6",
        segment_classes=("private",),
        worst_case_nano_usd=250_000_000,
    )
    connection.send(True)
    time.sleep(30)


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / ".model-spend"
        self.initialize()

    def initialize(self, day=DAY):
        return daily_spend.initialize_ledger(
            self.root,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=CEILING,
            day=day,
        )

    def reserve(self, reservation_id="a1b2c3d4", amount=250_000_000, day=DAY):
        return daily_spend.reserve(
            self.root,
            day=day,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=CEILING,
            reservation_id=reservation_id,
            run_uid="abcd1234",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("private",),
            worst_case_nano_usd=amount,
        )

    def read(self, day=DAY):
        return daily_spend.read_ledger(
            self.root,
            day=day,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=CEILING,
        )

    def reconcile(self, reservation_id="a1b2c3d4", actual=30_000):
        return daily_spend.reconcile(
            self.root,
            day=DAY,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=CEILING,
            reservation_id=reservation_id,
            run_uid="abcd1234",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("private",),
            actual_nano_usd=actual,
        )


class InitializationAndTamperTests(LedgerCase):
    def test_initialization_is_explicit_and_refuses_overwrite(self):
        with self.assertRaisesRegex(daily_spend.DailySpendError, "already exists"):
            self.initialize()
        missing = Path(self.temp.name) / "missing"
        with self.assertRaises(daily_spend.DailySpendError):
            daily_spend.reserve(
                missing,
                day=DAY,
                policy_uid=POLICY_UID,
                policy_version=POLICY_VERSION,
                daily_ceiling_nano_usd=CEILING,
                reservation_id="a1b2c3d4",
                run_uid="abcd1234",
                task="distill",
                model="claude-sonnet-4-6",
                segment_classes=("private",),
                worst_case_nano_usd=1,
            )
        self.assertFalse((missing / f"{DAY}.json").exists())

    def test_atomic_initialization_race_never_replaces_winning_ledger(self):
        root = Path(self.temp.name) / "execution-day-race"
        ledger_path = daily_spend._ledger_path(root, NEXT_DAY, "1.7.0")
        original_write = daily_spend._write_new_locked
        winning_bytes = {}

        def race(path, ledger):
            original_write(path, dict(ledger))
            winning_bytes["raw"] = path.read_bytes()
            return original_write(path, ledger)

        with mock.patch.object(
            daily_spend,
            "_write_new_locked",
            side_effect=race,
        ):
            with self.assertRaisesRegex(
                daily_spend.DailySpendError,
                "creation failed",
            ):
                daily_spend.initialize_ledger(
                    root,
                    policy_uid=POLICY_UID,
                    policy_version="1.7.0",
                    daily_ceiling_nano_usd=CEILING,
                    day=NEXT_DAY,
                )
        self.assertEqual(ledger_path.read_bytes(), winning_bytes["raw"])
        self.assertEqual(
            daily_spend.read_ledger(
                root,
                day=NEXT_DAY,
                policy_uid=POLICY_UID,
                policy_version="1.7.0",
                daily_ceiling_nano_usd=CEILING,
            )["reservations"],
            {},
        )

    def test_checksum_unknown_boolean_negative_overflow_and_stale_refuse(self):
        path = self.root / f"{DAY}.json"
        pristine = json.loads(path.read_text())
        mutations = (
            lambda value: value.__setitem__("unknown", 1),
            lambda value: value.__setitem__("daily_ceiling_nano_usd", True),
            lambda value: value.__setitem__("actual_total_nano_usd", -1),
            lambda value: value.__setitem__(
                "daily_ceiling_nano_usd", (1 << 63)
            ),
            lambda value: value.__setitem__("utc_date", NEXT_DAY),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                value = json.loads(json.dumps(pristine))
                mutate(value)
                value["checksum"] = daily_spend._checksum(value)
                path.write_text(json.dumps(value, sort_keys=True) + "\n")
                with self.assertRaises(daily_spend.DailySpendError):
                    self.read()
        path.write_text(json.dumps(pristine, sort_keys=True) + "\n")
        value = bytearray(path.read_bytes())
        value[-3] = ord("0") if value[-3] != ord("0") else ord("1")
        path.write_bytes(bytes(value))
        with self.assertRaises(daily_spend.DailySpendError):
            self.read()

    def test_duplicate_key_malformed_utf8_and_symlink_refuse(self):
        path = self.root / f"{DAY}.json"
        path.write_text('{"schema_version":1,"schema_version":1}\n')
        with self.assertRaisesRegex(daily_spend.DailySpendError, "duplicate"):
            self.read()
        path.write_bytes(b"\xff")
        with self.assertRaises(daily_spend.DailySpendError):
            self.read()
        path.unlink()
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text("{}")
        path.symlink_to(outside)
        with self.assertRaisesRegex(daily_spend.DailySpendError, "symlinked"):
            self.read()


class ReservationAndReconciliationTests(LedgerCase):
    def test_reservation_counts_worst_case_then_releases_only_difference(self):
        self.reserve()
        ledger = self.read()
        self.assertEqual(
            daily_spend.effective_committed_nano_usd(ledger),
            250_000_000,
        )
        receipt = self.reconcile(actual=30_000)
        self.assertEqual(receipt["status"], "reconciled")
        ledger = self.read()
        self.assertEqual(ledger["actual_total_nano_usd"], 30_000)
        self.assertEqual(
            daily_spend.effective_committed_nano_usd(ledger),
            30_000,
        )

    def test_claim_binds_gateway_and_replay_refuses(self):
        self.reserve()
        claimed = daily_spend.claim_reservation(
            self.root,
            day=DAY,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=CEILING,
            reservation_id="a1b2c3d4",
            run_uid="abcd1234",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("private",),
            gateway_request_id="flow-1",
            minimum_worst_case_nano_usd=249_000_000,
        )
        self.assertEqual(claimed["status"], "claimed")
        with self.assertRaisesRegex(daily_spend.DailySpendError, "replayed"):
            daily_spend.claim_reservation(
                self.root,
                day=DAY,
                policy_uid=POLICY_UID,
                policy_version=POLICY_VERSION,
                daily_ceiling_nano_usd=CEILING,
                reservation_id="a1b2c3d4",
                run_uid="abcd1234",
                task="distill",
                model="claude-sonnet-4-6",
                segment_classes=("private",),
                gateway_request_id="flow-2",
            )

    def test_double_reconcile_and_overage_poison_future_calls(self):
        self.reserve()
        self.reconcile()
        with self.assertRaises(daily_spend.DailySpendError):
            self.reconcile()
        self.assertTrue(self.read()["poisoned"])
        with self.assertRaisesRegex(daily_spend.DailySpendError, "poisoned"):
            self.reserve("deadbeef", amount=1)

        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / ".model-spend"
        self.initialize()
        self.reserve()
        with self.assertRaisesRegex(daily_spend.DailySpendError, "exceeded"):
            self.reconcile(actual=250_000_001)
        self.assertTrue(self.read()["poisoned"])

    def test_reconciliation_stays_on_start_day_across_midnight(self):
        self.reserve()
        self.initialize(NEXT_DAY)
        self.reconcile(actual=1)
        self.assertEqual(self.read(DAY)["actual_total_nano_usd"], 1)
        self.assertEqual(self.read(NEXT_DAY)["actual_total_nano_usd"], 0)

    def test_provider_unknown_outcome_retains_worst_case(self):
        self.reserve()
        ledger = self.read()
        self.assertEqual(
            ledger["reservations"]["a1b2c3d4"]["status"],
            "reserved",
        )
        self.assertEqual(
            daily_spend.effective_committed_nano_usd(ledger),
            250_000_000,
        )


class CrossVersionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def pair(
        self,
        name="pair",
        *,
        legacy_uid=POLICY_UID,
        legacy_ceiling=CEILING,
        initialize_legacy=True,
    ):
        root = Path(self.temp.name) / name
        if initialize_legacy:
            daily_spend.initialize_ledger(
                root,
                policy_uid=legacy_uid,
                policy_version=LEGACY_VERSION,
                daily_ceiling_nano_usd=legacy_ceiling,
                day=DAY,
            )
        daily_spend.initialize_ledger(
            root,
            policy_uid=POLICY_UID,
            policy_version=CURRENT_VERSION,
            daily_ceiling_nano_usd=CEILING,
            day=DAY,
        )
        return root

    def reserve(
        self,
        root,
        *,
        policy_version,
        reservation_id,
        amount,
    ):
        return daily_spend.reserve(
            root,
            day=DAY,
            policy_uid=POLICY_UID,
            policy_version=policy_version,
            daily_ceiling_nano_usd=CEILING,
            reservation_id=reservation_id,
            run_uid="abcd1234",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("os",),
            worst_case_nano_usd=amount,
        )

    def read(self, root, policy_version):
        return daily_spend.read_ledger(
            root,
            day=DAY,
            policy_uid=POLICY_UID,
            policy_version=policy_version,
            daily_ceiling_nano_usd=CEILING,
        )

    def test_legacy_and_v12_paths_coexist_under_one_stable_lock(self):
        root = self.pair()
        self.assertEqual(
            daily_spend._ledger_path(root, DAY, LEGACY_VERSION),
            root / f"{DAY}.json",
        )
        self.assertEqual(
            daily_spend._ledger_path(root, DAY, CURRENT_VERSION),
            root / f"{DAY}@{CURRENT_VERSION}.json",
        )
        self.assertEqual(
            {path.name for path in daily_spend._day_ledger_paths(root, DAY)},
            {f"{DAY}.json", f"{DAY}@{CURRENT_VERSION}.json"},
        )
        self.assertTrue((root / f"{DAY}.lock").is_file())

    def test_combined_committed_at_ceiling_succeeds_and_over_ceiling_refuses(self):
        success = self.pair("success")
        self.reserve(
            success,
            policy_version=LEGACY_VERSION,
            reservation_id="a0000001",
            amount=4_500_000_000,
        )
        self.reserve(
            success,
            policy_version=CURRENT_VERSION,
            reservation_id="a0000002",
            amount=500_000_000,
        )
        self.assertEqual(
            sum(
                daily_spend.effective_committed_nano_usd(
                    self.read(success, version)
                )
                for version in (LEGACY_VERSION, CURRENT_VERSION)
            ),
            CEILING,
        )

        refused = self.pair("refused")
        self.reserve(
            refused,
            policy_version=LEGACY_VERSION,
            reservation_id="b0000001",
            amount=4_900_000_000,
        )
        current_path = daily_spend._ledger_path(refused, DAY, CURRENT_VERSION)
        before = current_path.read_bytes()
        with self.assertRaises(daily_spend.DailySpendLimitError):
            self.reserve(
                refused,
                policy_version=CURRENT_VERSION,
                reservation_id="b0000002",
                amount=200_000_000,
            )
        self.assertEqual(current_path.read_bytes(), before)

    def test_poisoned_malformed_symlink_and_wrong_identity_peers_refuse(self):
        poisoned = self.pair("poisoned")
        self.reserve(
            poisoned,
            policy_version=LEGACY_VERSION,
            reservation_id="c0000001",
            amount=10,
        )
        with self.assertRaises(daily_spend.DailySpendError):
            daily_spend.reconcile(
                poisoned,
                day=DAY,
                policy_uid=POLICY_UID,
                policy_version=LEGACY_VERSION,
                daily_ceiling_nano_usd=CEILING,
                reservation_id="c0000001",
                run_uid="abcd1234",
                task="distill",
                model="claude-sonnet-4-6",
                segment_classes=("os",),
                actual_nano_usd=11,
            )

        malformed = self.pair("malformed")
        (malformed / f"{DAY}.json").write_text("{bad")

        symlinked = self.pair("symlinked", initialize_legacy=False)
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text("{}")
        (symlinked / f"{DAY}.json").symlink_to(outside)

        wrong_ceiling = self.pair(
            "wrong-ceiling",
            legacy_ceiling=CEILING - 1,
        )
        wrong_uid = self.pair("wrong-uid", legacy_uid="deadbeef")

        for label, root in (
            ("poisoned", poisoned),
            ("malformed", malformed),
            ("symlinked", symlinked),
            ("wrong-ceiling", wrong_ceiling),
            ("wrong-uid", wrong_uid),
        ):
            with self.subTest(label=label):
                current_path = daily_spend._ledger_path(
                    root,
                    DAY,
                    CURRENT_VERSION,
                )
                before = current_path.read_bytes()
                with self.assertRaises(daily_spend.DailySpendError):
                    self.reserve(
                        root,
                        policy_version=CURRENT_VERSION,
                        reservation_id="d0000001",
                        amount=1,
                    )
                self.assertEqual(current_path.read_bytes(), before)

    def test_unknown_or_invalid_same_day_naming_refuses(self):
        for index, name in enumerate(
            (
                f"{DAY}@1.2.json",
                f"{DAY}@01.2.0.json",
                f"{DAY}@1.2.0.json.bak",
                f".{DAY}@1.2.0.json.stale",
            )
        ):
            root = self.pair(f"naming-{index}")
            (root / name).write_text("{}")
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    daily_spend.DailySpendError,
                    "unknown same-day ledger naming",
                ):
                    self.reserve(
                        root,
                        policy_version=CURRENT_VERSION,
                        reservation_id=f"e{index:07x}",
                        amount=1,
                    )

    def test_v12_reserve_claim_reconcile_never_changes_v11_bytes(self):
        root = self.pair()
        self.reserve(
            root,
            policy_version=LEGACY_VERSION,
            reservation_id="f0000001",
            amount=100,
        )
        legacy_path = daily_spend._ledger_path(root, DAY, LEGACY_VERSION)
        before = legacy_path.read_bytes()
        self.reserve(
            root,
            policy_version=CURRENT_VERSION,
            reservation_id="f0000002",
            amount=100,
        )
        daily_spend.claim_reservation(
            root,
            day=DAY,
            policy_uid=POLICY_UID,
            policy_version=CURRENT_VERSION,
            daily_ceiling_nano_usd=CEILING,
            reservation_id="f0000002",
            run_uid="abcd1234",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("os",),
            gateway_request_id="flow-v12",
        )
        daily_spend.reconcile(
            root,
            day=DAY,
            policy_uid=POLICY_UID,
            policy_version=CURRENT_VERSION,
            daily_ceiling_nano_usd=CEILING,
            reservation_id="f0000002",
            run_uid="abcd1234",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("os",),
            actual_nano_usd=10,
        )
        self.assertEqual(legacy_path.read_bytes(), before)
        self.assertEqual(
            self.read(root, CURRENT_VERSION)["reservations"]["f0000002"][
                "status"
            ],
            "reconciled",
        )


class ProcessConcurrencyTests(LedgerCase):
    def test_real_process_flock_race_never_exceeds_daily_ceiling(self):
        context = multiprocessing.get_context("fork")
        contenders = 24
        amount = 250_000_000
        barrier = context.Barrier(contenders)
        output = context.Queue()
        processes = [
            context.Process(
                target=_reserve_worker,
                args=(self.root, barrier, index, amount, output),
            )
            for index in range(contenders)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        admitted = sum(output.get(timeout=1) for _ in processes)
        self.assertEqual(admitted, CEILING // amount)
        ledger = self.read()
        self.assertEqual(
            daily_spend.effective_committed_nano_usd(ledger),
            CEILING,
        )
        self.assertEqual(len(ledger["reservations"]), admitted)

    def test_shared_lock_cross_version_race_never_over_admits(self):
        root = Path(self.temp.name) / "cross-version"
        for version in (LEGACY_VERSION, CURRENT_VERSION):
            daily_spend.initialize_ledger(
                root,
                policy_uid=POLICY_UID,
                policy_version=version,
                daily_ceiling_nano_usd=CEILING,
                day=DAY,
            )
        context = multiprocessing.get_context("fork")
        contenders = 24
        amount = 250_000_000
        barrier = context.Barrier(contenders)
        output = context.Queue()
        processes = [
            context.Process(
                target=_cross_version_reserve_worker,
                args=(
                    root,
                    barrier,
                    index,
                    amount,
                    (
                        LEGACY_VERSION
                        if index % 2 == 0
                        else CURRENT_VERSION
                    ),
                    output,
                ),
            )
            for index in range(contenders)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        admitted = sum(output.get(timeout=1) for _ in processes)
        self.assertEqual(admitted, CEILING // amount)
        committed = 0
        for version in (LEGACY_VERSION, CURRENT_VERSION):
            ledger = daily_spend.read_ledger(
                root,
                day=DAY,
                policy_uid=POLICY_UID,
                policy_version=version,
                daily_ceiling_nano_usd=CEILING,
            )
            committed += daily_spend.effective_committed_nano_usd(ledger)
        self.assertEqual(committed, CEILING)

    def test_killed_process_after_atomic_reservation_stays_charged(self):
        context = multiprocessing.get_context("fork")
        parent, child = context.Pipe()
        process = context.Process(
            target=_reserve_then_wait,
            args=(self.root, child),
        )
        process.start()
        self.assertTrue(parent.recv())
        process.terminate()
        process.join(5)
        self.assertIsNotNone(process.exitcode)
        ledger = self.read()
        self.assertEqual(
            ledger["reservations"]["feedbeef"]["status"],
            "reserved",
        )
        self.assertEqual(
            daily_spend.effective_committed_nano_usd(ledger),
            250_000_000,
        )


class MonthlyBeltTests(unittest.TestCase):
    """D2's $50/month aggregate belt — a real, code-enforced ceiling, not a
    policy-doc number. Read-only aggregate over the already-hardened daily
    ledgers; gated inside the same reservation call as the daily ceiling."""

    MONTH_CEILING = 50_000_000_000  # $50.00

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / ".model-spend"

    def _reserve(self, day, reservation_id, amount, *, monthly_ceiling=None):
        daily_spend.initialize_ledger(
            self.root,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=CEILING,
            day=day,
        )
        return daily_spend.reserve(
            self.root,
            day=day,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=CEILING,
            reservation_id=reservation_id,
            run_uid="abcd1234",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("os",),
            worst_case_nano_usd=amount,
            monthly_ceiling_nano_usd=monthly_ceiling,
        )

    def test_utc_month_derives_calendar_month_from_a_datetime(self):
        from datetime import datetime, timezone

        self.assertEqual(
            daily_spend.utc_month(datetime(2026, 7, 23, tzinfo=timezone.utc)),
            "2026-07",
        )
        with self.assertRaises(daily_spend.DailySpendError):
            daily_spend.utc_month(datetime(2026, 7, 23))  # naive, no tzinfo

    def test_monthly_committed_sums_across_days_in_the_same_month_only(self):
        self._reserve("2026-07-05", "a0000001", 4_000_000_000)
        self._reserve("2026-07-19", "a0000002", 3_000_000_000)
        # A different UTC month must never contribute to July's total.
        self._reserve("2026-06-30", "a0000003", 4_500_000_000)
        committed = daily_spend.monthly_committed_nano_usd(
            self.root,
            "2026-07",
            policy_uid=POLICY_UID,
            daily_ceiling_nano_usd=CEILING,
        )
        self.assertEqual(committed, 7_000_000_000)
        committed_june = daily_spend.monthly_committed_nano_usd(
            self.root,
            "2026-06",
            policy_uid=POLICY_UID,
            daily_ceiling_nano_usd=CEILING,
        )
        self.assertEqual(committed_june, 4_500_000_000)

    def test_reserve_refuses_once_the_monthly_belt_would_be_crossed(self):
        # Ten days at exactly the $5.00 daily ceiling ($50.00 total) — each
        # individually legal — then one more nano-USD on an eleventh day,
        # which only the $50.00 monthly belt can refuse.
        for day_index in range(10):
            self._reserve(
                f"2026-07-{day_index + 1:02d}",
                f"b00000{day_index:02d}",
                CEILING,
                monthly_ceiling=self.MONTH_CEILING,
            )
        with self.assertRaises(daily_spend.MonthlySpendLimitError):
            self._reserve(
                "2026-07-11", "b0000099", 1,
                monthly_ceiling=self.MONTH_CEILING,
            )
        # The refused reservation must never have been written anywhere.
        committed = daily_spend.monthly_committed_nano_usd(
            self.root,
            "2026-07",
            policy_uid=POLICY_UID,
            daily_ceiling_nano_usd=CEILING,
        )
        self.assertEqual(committed, self.MONTH_CEILING)

    def test_reservation_exactly_at_the_monthly_ceiling_is_admitted(self):
        for day_index in range(9):
            self._reserve(
                f"2026-07-{day_index + 1:02d}",
                f"c00000{day_index:02d}",
                CEILING,
                monthly_ceiling=self.MONTH_CEILING,
            )
        # Nine days at $5.00 = $45.00; one more $5.00 reservation lands
        # exactly on the $50.00 belt and must still be admitted.
        record = self._reserve(
            "2026-07-10", "c0000099", CEILING,
            monthly_ceiling=self.MONTH_CEILING,
        )
        self.assertEqual(record["status"], "reserved")
        committed = daily_spend.monthly_committed_nano_usd(
            self.root,
            "2026-07",
            policy_uid=POLICY_UID,
            daily_ceiling_nano_usd=CEILING,
        )
        self.assertEqual(committed, self.MONTH_CEILING)

    def test_monthly_ceiling_none_preserves_exact_pre_d2_behavior(self):
        # Backward compatibility: omitting monthly_ceiling_nano_usd (the
        # default) must apply no monthly gate at all, regardless of spend
        # already committed elsewhere in the month.
        self._reserve("2026-07-01", "d0000001", 4_900_000_000)
        self._reserve("2026-07-02", "d0000002", 4_900_000_000)
        record = self._reserve("2026-07-03", "d0000003", 4_900_000_000)
        self.assertEqual(record["status"], "reserved")

    def test_reconciled_actuals_count_toward_the_monthly_total_not_worst_case(self):
        self._reserve(
            "2026-07-01", "e0000001", CEILING,
            monthly_ceiling=self.MONTH_CEILING,
        )
        daily_spend.reconcile(
            self.root,
            day="2026-07-01",
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=CEILING,
            reservation_id="e0000001",
            run_uid="abcd1234",
            task="distill",
            model="claude-sonnet-4-6",
            segment_classes=("os",),
            actual_nano_usd=1_000_000,
        )
        committed = daily_spend.monthly_committed_nano_usd(
            self.root,
            "2026-07",
            policy_uid=POLICY_UID,
            daily_ceiling_nano_usd=CEILING,
        )
        # Reconciled: the real actual ($0.001) counts, not the released
        # $5.00 worst-case reservation.
        self.assertEqual(committed, 1_000_000)
        # Nine more full $5.00 days now fit comfortably under the $50 belt —
        # if the stale worst-case still counted, the ninth would refuse.
        for day_index in range(1, 10):
            record = self._reserve(
                f"2026-07-{day_index + 1:02d}",
                f"e11111{day_index:02d}",
                CEILING,
                monthly_ceiling=self.MONTH_CEILING,
            )
            self.assertEqual(record["status"], "reserved")


if __name__ == "__main__":
    unittest.main()
