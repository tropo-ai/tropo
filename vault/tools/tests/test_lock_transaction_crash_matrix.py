"""Crash and failure injection at every write and finalization point.

argus-a147, stage-4 NO-GO item 2: "Add actual release-lock crash/retry plants at
every write/finalization, symlink swap, alias duplicate, malicious journal path,
semantic corruption, recycle/fsync failure."

The suites next door prove the transaction's happy paths and its refusals. This
one breaks it on purpose at each point where a crash is possible, and asserts the
studio is left in a state an operator can act on — which is a different claim
from "the code raises".

WHAT COUNTS AS ACCEPTABLE AFTER A CRASH, stated once so every test below can be
read against it:

  applied      every effect landed and the journal says so
  rolled-back  no effect survives and the journal says so
  recoverable  effects partially landed, the journal is `applying`, and
               recover_incomplete() can reach one of the two states above

The state that must never occur is a fourth one: effects on disk with no journal
that describes them, or a journal whose replay would make things worse. A crash
between the journal write and the first effect is SAFE precisely because the
journal is committed first.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_lock_transaction_crash_matrix
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from lib import lock_transaction as lt  # noqa: E402


class Boom(Exception):
    """A crash that is not one of the transaction's own exception types.

    Deliberately foreign: if the code only survives failures it already knows
    about, it has been written to its own tests rather than to reality.
    """


class CrashAtEveryPoint(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="crash-matrix-")).resolve()
        self._orig = (lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT,
                      lt._atomic_write, lt._finish_journal)
        lt.LOCK_JOURNAL_DIR = self.tmp / "journal"
        lt.WORKSPACE_LOCK_PATH = self.tmp / "journal" / "ignition.lock"
        lt.VAULT_ROOT = self.tmp
        self.subject = self.tmp / "subject.md"
        self.subject.write_text("before\n")

    def tearDown(self) -> None:
        (lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT,
         lt._atomic_write, lt._finish_journal) = self._orig

    def _plan(self) -> lt.LockPlan:
        plan = lt.LockPlan(kind="release-plan-lock", subject_uid="12345678",
                           actor="talos")
        plan.create(self.tmp / "one.md", "one\n")
        plan.create(self.tmp / "two.md", "two\n", governed=True)
        plan.patch(self.subject, "before\n", "after\n")
        return plan

    def _apply(self, build, **kwargs):
        """Factory: the plan is constructed inside the span, like production."""
        with lt.exclusive_workspace_lock():
            return lt.apply_plan(build() if callable(build) else build, **kwargs)

    def _journal(self) -> dict:
        path = lt.LOCK_JOURNAL_DIR / "release-plan-lock-12345678.json"
        return json.loads(path.read_text()) if path.is_file() else {}

    def _assert_recoverable_or_clean(self) -> None:
        """The invariant: whatever happened, an operator has a coherent story."""
        journal = self._journal()
        self.assertIn(journal.get("state"), {"applying", "rolled-back", "applied"},
                      f"journal left in an uninterpretable state: {journal.get('state')!r}")
        if journal.get("state") == "applying":
            reports = lt.recover_incomplete(recycle=lambda p, r: (p.unlink(), True)[1])
            self.assertTrue(reports, "an applying journal was not picked up by recovery")
            self.assertIn(reports[0]["outcome"], {"rolled-back", "needs-operator"})

    # ------------------------------------------------------- crash at each write

    def test_a_crash_at_each_successive_write_is_recoverable(self) -> None:
        """Walk the failure point across every effect in the plan.

        Crashing only at the first write proves the easiest case. The
        interesting ones are later, where earlier effects have already landed
        and the unwind has real work to do.
        """
        # The plan has three effects, so the crash points are before each of
        # them. "After the last write" is not a gap — it is the finalization
        # crash, which has its own test below because its safe outcome is
        # different (the journal stays `applying` and replay is a no-op undo).
        effect_count = len(self._plan().operations)
        for crash_after in range(0, effect_count):
            with self.subTest(crash_after_writes=crash_after):
                self.tearDown()
                self.setUp()
                real_write = lt._atomic_write
                calls = {"n": 0}

                def crashing(path: Path, content: str) -> None:
                    # The journal write goes through the same helper; only count
                    # and interrupt EFFECT writes.
                    if path.parent == lt.LOCK_JOURNAL_DIR:
                        return real_write(path, content)
                    if calls["n"] >= crash_after:
                        raise Boom(f"crash before effect #{calls['n']}")
                    calls["n"] += 1
                    return real_write(path, content)

                lt._atomic_write = crashing
                try:
                    with self.assertRaises((lt.LockApplyFailure, Boom)):
                        self._apply(self._plan, recycle=lambda p, r: (p.unlink(), True)[1])
                finally:
                    lt._atomic_write = real_write

                self._assert_recoverable_or_clean()
                self.assertEqual(
                    self.subject.read_text(), "before\n",
                    "the patched subject survived a crashed transaction")

    def test_a_crash_while_finalizing_the_journal_still_leaves_it_replayable(self) -> None:
        """Finalization is a write too, and the last one nobody thinks about.

        If the effects landed but the journal could not be flipped to `applied`,
        it stays `applying` — so recovery will look at it. That is the SAFE
        direction: replay compares disk against intent and finds everything
        matching post-state, which is a no-op undo rather than a corruption.
        """
        def refuse_to_finalize(path, state, extra):
            raise Boom("crash while finalizing the journal")

        lt._finish_journal = refuse_to_finalize
        try:
            with self.assertRaises(Boom):
                self._apply(self._plan, recycle=None)
        finally:
            lt._finish_journal = self._orig[4]

        self.assertEqual(self._journal().get("state"), "applying")
        self.assertTrue((self.tmp / "one.md").is_file(),
                        "effects were expected to have landed before finalization")

        reports = lt.recover_incomplete(recycle=lambda p, r: (p.unlink(), True)[1])
        self.assertEqual(reports[0]["outcome"], "rolled-back")
        self.assertEqual(self.subject.read_text(), "before\n")

    def test_a_crash_before_the_journal_leaves_nothing_at_all(self) -> None:
        """The reason the journal is written first.

        No journal means no effects, so there is nothing to recover and nothing
        to explain. This is the one crash point that needs no recovery machinery.
        """
        real_write = lt._atomic_write

        def crash_on_journal(path: Path, content: str) -> None:
            if path.parent == lt.LOCK_JOURNAL_DIR:
                raise Boom("crash before the journal lands")
            return real_write(path, content)

        lt._atomic_write = crash_on_journal
        try:
            with self.assertRaises(Boom):
                self._apply(self._plan, recycle=None)
        finally:
            lt._atomic_write = real_write

        self.assertFalse((self.tmp / "one.md").exists())
        self.assertEqual(self.subject.read_text(), "before\n")
        self.assertEqual(self._journal(), {})

    # ------------------------------------------------------ injected sub-failures

    def test_a_post_rename_dir_fsync_failure_is_POSSIBLY_APPLIED(self) -> None:
        """Blocker 2, stated precisely.

        The rename has already happened; only the directory fsync failed. The
        effect may well be on disk. Reporting "rolled back" is the single most
        harmful thing to say, because it is the report an operator acts on and
        the one we cannot substantiate. The journal must say possibly-applied,
        and nothing must be unwound on the assumption it did not land.
        """
        real_fsync = os.fsync
        seen = {"dirs": 0}
        # Only EFFECT directories. The journal is written through the same
        # atomic writer, so failing every directory fsync would break the
        # journal write first and test a different (also real) case.
        journal_ino = None
        lt.LOCK_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        journal_ino = lt.LOCK_JOURNAL_DIR.stat().st_ino

        def fail_on_dir_fsync(fd):
            try:
                info = os.fstat(fd)
                is_dir = bool(info.st_mode & 0o040000)
                is_journal = info.st_ino == journal_ino
            except OSError:
                is_dir, is_journal = False, False
            if is_dir and not is_journal:
                seen["dirs"] += 1
                raise OSError("simulated post-rename directory fsync failure")
            return real_fsync(fd)

        os.fsync = fail_on_dir_fsync
        try:
            with self.assertRaises(lt.LockApplyFailure) as caught:
                self._apply(self._plan, recycle=None)
        finally:
            os.fsync = real_fsync

        self.assertGreater(seen["dirs"], 0, "no directory fsync was attempted")
        self.assertIn("POSSIBLY APPLIED", str(caught.exception))
        self.assertEqual(
            self._journal().get("state"), "possibly-applied",
            "a possibly-applied transaction was recorded as something definite")
        self.assertNotEqual(self._journal().get("state"), "rolled-back")

    def test_a_rollback_that_strands_substrate_is_not_called_rolled_back(self) -> None:
        """Blocker 2: a failed governed recycle leaves the entry on disk.

        Recording "rolled-back" then says the transaction never happened while
        its substrate is still there.
        """
        real_write = lt._atomic_write

        def crash_on_subject(path: Path, content: str) -> None:
            if path.parent == lt.LOCK_JOURNAL_DIR:
                return real_write(path, content)
            if path.name == "subject.md":
                raise Boom("crash after the governed create landed")
            return real_write(path, content)

        lt._atomic_write = crash_on_subject
        try:
            with self.assertRaises(lt.LockApplyFailure):
                self._apply(self._plan, recycle=lambda p, r: False)
        finally:
            lt._atomic_write = real_write

        self.assertEqual(self._journal().get("state"), "needs-operator")
        self.assertTrue((self.tmp / "two.md").is_file(),
                        "the governed entry was hard-deleted")

    def test_rollback_removes_the_directories_it_emptied(self) -> None:
        """Blocker 2: an undone transaction left its run folder behind, which is
        enough for a later reader to believe a run existed."""
        nested = self.tmp / "vault" / "pipeline-runs" / "dev-pipeline-abc-2026-08-10"

        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678",
                               actor="talos")
            plan.create(nested / "declaration-snapshot.json", "{}\n")
            plan.create(self.tmp / "boom.md" / "impossible.md", "unreachable\n")
            return plan

        (self.tmp / "boom.md").write_text("i am a file\n")
        with self.assertRaises(lt.LockApplyFailure):
            self._apply(build, recycle=None)

        self.assertFalse(nested.exists(),
                         f"the emptied run folder survived rollback: {nested}")

    def test_a_journal_whose_recorded_content_does_not_match_its_hash_is_refused(self) -> None:
        """Blocker 2: replay trusted pre_content as given.

        If the journal's own bytes disagree with its own digests, the journal is
        corrupt — and restoring from it would write bytes nobody committed while
        reporting a clean recovery.
        """
        target = self.tmp / "tampered.md"
        target.write_text("current\n")
        lt.LOCK_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        (lt.LOCK_JOURNAL_DIR / "dev-spec-lock-tamper.json").write_text(
            json.dumps({
                "kind": "dev-spec-lock", "subject_uid": "tamper",
                "state": "applying", "plan_digest": "d" * 64,
                "operations": [{
                    "op": "patch", "path": str(target),
                    "expected_sha256": "0" * 64,          # does not match pre_content
                    "sha256": lt.sha256_text("current\n"),
                    "pre_existed": True,
                    "pre_content": "attacker supplied\n",
                    "post_content": "current\n",
                }],
            }) + "\n")

        reports = lt.recover_incomplete(recycle=None)

        self.assertEqual(reports[0]["outcome"], "needs-operator")
        self.assertEqual(target.read_text(), "current\n",
                         "recovery wrote attacker-supplied bytes")
        self.assertTrue(any("does not hash" in p for p in reports[0]["diverged"]),
                        f"the hash mismatch was not named: {reports[0]['diverged']}")

    def test_a_PARENT_swapped_for_a_symlink_mid_apply_cannot_redirect_the_write(self) -> None:
        """Argus's "parent symlink swap still escapes", closed by an anchored fd.

        Checking the target is not a symlink says nothing about its PARENT. Swap
        the parent directory for a link between preflight and the write and a
        path-based writer follows it straight out of the workspace. The write is
        now anchored to a directory descriptor opened O_NOFOLLOW before any of
        this, so a later swap cannot redirect it — the fd already names the
        directory that existed at open time.
        """
        outside = Path(tempfile.mkdtemp(prefix="outside-")).resolve()
        real_dir = self.tmp / "target-dir"
        real_dir.mkdir()
        victim = real_dir / "entry.md"

        real_write = lt._atomic_write
        swapped = {"done": False}

        def swap_parent_then_write(path: Path, content: str) -> None:
            if not swapped["done"] and path == victim:
                swapped["done"] = True
                real_dir.rmdir()
                real_dir.symlink_to(outside, target_is_directory=True)
            return real_write(path, content)

        lt._atomic_write = swap_parent_then_write
        try:
            def build():
                plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="12345678",
                                   actor="talos")
                plan.create(victim, "payload\n")
                return plan

            with self.assertRaises((lt.LockRefusal, lt.LockApplyFailure)):
                self._apply(build, recycle=None)
        finally:
            lt._atomic_write = real_write

        self.assertTrue(swapped["done"], "the parent swap never happened")
        self.assertEqual(list(outside.iterdir()), [],
                         f"the write escaped into {outside} through a swapped parent")

    def test_recovery_also_removes_the_directories_it_empties(self) -> None:
        """The rollback path and the recovery path are different code.

        A mutation removing the cleanup from RECOVERY survived, because my only
        empty-directory test exercised rollback. Two call sites, two tests.
        """
        nested = self.tmp / "vault" / "pipeline-runs" / "dev-pipeline-xyz-2026-08-10"

        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="recdirs",
                               actor="talos")
            plan.create(nested / "declaration-snapshot.json", "{}\n")
            return plan

        self._apply(build, recycle=None)
        journal = lt.LOCK_JOURNAL_DIR / "dev-spec-lock-recdirs.json"
        body = json.loads(journal.read_text())
        body["state"] = "applying"
        journal.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")

        lt.recover_incomplete(recycle=None)

        self.assertFalse(nested.exists(),
                         f"recovery emptied {nested} and left the directory")

    def test_a_journal_whose_post_content_does_not_match_its_hash_is_refused(self) -> None:
        """The other half of the digest check.

        I tested a tampered `pre_content` and not a tampered `post_content`, so
        a mutation removing the post-side validation survived. Post matters just
        as much: replay compares disk against `post_content` to decide whether a
        write LANDED, so corrupting it makes recovery reach the wrong verdict.
        """
        target = self.tmp / "posthash.md"
        target.write_text("on disk\n")
        lt.LOCK_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        (lt.LOCK_JOURNAL_DIR / "dev-spec-lock-posthash.json").write_text(
            json.dumps({
                "kind": "dev-spec-lock", "subject_uid": "posthash",
                "state": "applying", "plan_digest": "d" * 64,
                "operations": [{
                    "op": "create", "path": str(target),
                    "sha256": "0" * 64,               # does not match post_content
                    "pre_existed": False,
                    "post_content": "on disk\n",
                }],
            }) + "\n")

        reports = lt.recover_incomplete(recycle=None)

        self.assertEqual(reports[0]["outcome"], "needs-operator")
        self.assertTrue(target.is_file(), "recovery acted on a corrupt journal")
        self.assertTrue(any("does not hash" in p for p in reports[0]["diverged"]))

    def _valid_journal(self, target: Path) -> dict:
        """A journal that passes every check, so a plant can corrupt one thing."""
        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="digest01",
                               actor="talos")
            plan.create(target, "authentic\n")
            return plan

        self._apply(build, recycle=None)
        path = lt.LOCK_JOURNAL_DIR / "dev-spec-lock-digest01.json"
        body = json.loads(path.read_text())
        body["state"] = "applying"
        return body

    def test_a_semantically_changed_journal_with_a_valid_LENGTH_digest_is_refused(self) -> None:
        """argus-a147: recompute the digest, do not shape-check it.

        Accepting any 64-character string checks that a digest is PRESENT, which
        is a statement about formatting. Rewrite an operation, leave the digest
        untouched — still 64 hex, still "valid" — and a shape check waves it
        through. The digest exists so the journal's contents can be compared
        against it; not doing the comparison makes it decoration.
        """
        target = self.tmp / "digest-plant.md"
        body = self._valid_journal(target)

        # Semantic change: repoint the operation at a different file. The digest
        # is left exactly as written, and is a perfectly well-formed 64-hex.
        victim = self.tmp / "somewhere-else.md"
        victim.write_text("do not touch\n")
        body["operations"][0]["path"] = str(victim)
        self.assertEqual(len(body["plan_digest"]), 64,
                         "the plant must keep a well-formed digest or it proves nothing")
        (lt.LOCK_JOURNAL_DIR / "dev-spec-lock-digest01.json").write_text(
            json.dumps(body, indent=2, sort_keys=True) + "\n")

        reports = lt.recover_incomplete(recycle=None)

        self.assertEqual(reports[0]["outcome"], "needs-operator")
        self.assertTrue(any("does not match the digest recomputed" in p
                            for p in reports[0]["diverged"]),
                        f"the digest was not recomputed: {reports[0]['diverged']}")
        self.assertEqual(victim.read_text(), "do not touch\n",
                         "recovery acted on a repointed operation")

    def test_a_forged_pre_content_with_a_valid_digest_is_refused(self) -> None:
        """The other plant Argus named, combined with a well-formed digest.

        Corrupting `pre_content` alone is what a rollback would restore, so this
        is the path that writes attacker-chosen bytes while reporting a clean
        recovery.
        """
        target = self.tmp / "forged-pre.md"
        target.write_text("original\n")

        def build():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="digest02",
                               actor="talos")
            plan.patch(target, "original\n", "patched\n")
            return plan

        self._apply(build, recycle=None)
        path = lt.LOCK_JOURNAL_DIR / "dev-spec-lock-digest02.json"
        body = json.loads(path.read_text())
        body["state"] = "applying"
        body["operations"][0]["pre_content"] = "attacker chosen\n"
        path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")

        reports = lt.recover_incomplete(recycle=None)

        self.assertEqual(reports[0]["outcome"], "needs-operator")
        self.assertEqual(target.read_text(), "patched\n",
                         "recovery restored attacker-chosen bytes")

    def test_the_control_an_untampered_journal_still_recovers(self) -> None:
        """Without this, both plants above pass for a recovery that refuses all."""
        target = self.tmp / "clean-digest.md"
        body = self._valid_journal(target)
        (lt.LOCK_JOURNAL_DIR / "dev-spec-lock-digest01.json").write_text(
            json.dumps(body, indent=2, sort_keys=True) + "\n")

        reports = lt.recover_incomplete(recycle=None)

        self.assertEqual(reports[0]["outcome"], "rolled-back",
                         f"a valid journal was refused: {reports[0]}")
        self.assertFalse(target.exists())

    def test_the_recomputation_agrees_with_the_plan_that_wrote_it(self) -> None:
        """If these two ever disagree, every journal is refused as tampered.

        A guard that rejects authentic input is worse than none: it teaches the
        crew to bypass recovery.
        """
        with lt.exclusive_workspace_lock():
            plan = lt.LockPlan(kind="dev-spec-lock", subject_uid="agree01",
                               actor="talos")
            plan.create(self.tmp / "a.md", "alpha\n")
            body = dict(plan.describe(reconstructable=True),
                        plan_digest=plan.digest())
        self.assertEqual(lt.journal_plan_digest(body), plan.digest())

    def test_a_journal_with_no_plan_digest_is_refused(self) -> None:
        lt.LOCK_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        (lt.LOCK_JOURNAL_DIR / "dev-spec-lock-nodigest.json").write_text(
            json.dumps({"kind": "dev-spec-lock", "subject_uid": "nodigest",
                        "state": "applying", "operations": []}) + "\n")
        reports = lt.recover_incomplete(recycle=None)
        self.assertEqual(reports[0]["outcome"], "needs-operator")
        self.assertTrue(any("plan_digest" in p for p in reports[0]["diverged"]))

    def test_an_unreadable_journal_at_finalize_time_propagates(self) -> None:
        """Blocker 2: `_finish_journal` used to swallow a read failure.

        The terminal state is the one fact recovery reads to decide whether to
        act. Skipping the update silently leaves a COMPLETED transaction looking
        in-flight forever, so the next lock refuses on a phantom.
        """
        real_write = lt._atomic_write

        def eat_the_journal(path: Path, content: str) -> None:
            result = real_write(path, content)
            if path.parent == lt.LOCK_JOURNAL_DIR:
                path.write_text("{ truncated")  # corrupt it after it is written
            return result

        lt._atomic_write = eat_the_journal
        try:
            with self.assertRaises(lt.LockApplyFailure) as caught:
                self._apply(self._plan, recycle=None)
        finally:
            lt._atomic_write = real_write

        self.assertIn("terminal state", str(caught.exception))

    def test_an_fsync_failure_does_not_report_a_false_rollback(self) -> None:
        """A post-rename fsync failure is POSSIBLY-APPLIED, never cleanly failed.

        The rename may well have hit the disk. Reporting "rolled back" would tell
        an operator the transaction did not happen when it may have — which is
        worse than saying nothing, because they would act on it.
        """
        real_fsync = os.fsync
        state = {"writes": 0}

        def flaky(fd):
            state["writes"] += 1
            if state["writes"] > 3:
                raise OSError("simulated fsync failure")
            return real_fsync(fd)

        os.fsync = flaky
        try:
            with self.assertRaises((lt.LockApplyFailure, OSError)):
                self._apply(self._plan, recycle=lambda p, r: (p.unlink(), True)[1])
        finally:
            os.fsync = real_fsync

        journal = self._journal()
        self.assertNotEqual(
            journal.get("state"), "applied",
            "a transaction whose fsync failed was recorded as cleanly applied")
        self._assert_recoverable_or_clean()

    def test_a_recycle_failure_during_rollback_is_reported_not_escalated(self) -> None:
        real_write = lt._atomic_write

        def crash_on_third(path: Path, content: str) -> None:
            if path.parent == lt.LOCK_JOURNAL_DIR:
                return real_write(path, content)
            if path.name == "subject.md":
                raise Boom("crash after the governed create landed")
            return real_write(path, content)

        lt._atomic_write = crash_on_third
        try:
            with self.assertRaises(lt.LockApplyFailure) as caught:
                self._apply(self._plan, recycle=lambda p, r: False)
        finally:
            lt._atomic_write = real_write

        self.assertTrue((self.tmp / "two.md").is_file(),
                        "a failed recycle hard-deleted a governed entry")
        self.assertTrue(caught.exception.stranded,
                        "the stranded governed entry was not reported")

    # ------------------------------------------------------- hostile journal input

    def test_a_journal_pointing_outside_the_workspace_is_refused(self) -> None:
        """A journal is a file on disk. If replay trusted its paths it would be a
        write primitive aimed wherever the file says."""
        outside = Path(tempfile.mkdtemp(prefix="outside-")) / "victim.md"
        outside.write_text("do not touch\n")
        lt.LOCK_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        (lt.LOCK_JOURNAL_DIR / "release-plan-lock-badpath.json").write_text(
            json.dumps({
                "kind": "release-plan-lock", "subject_uid": "badpath",
                "state": "applying", "operations": [{
                    "op": "create", "path": str(outside), "governed": False,
                    "pre_existed": False, "post_content": "do not touch\n",
                }],
            }) + "\n")

        reports = lt.recover_incomplete(recycle=None)

        self.assertEqual(reports[0]["outcome"], "needs-operator")
        self.assertTrue(outside.is_file(), "recovery deleted a file outside the workspace")
        self.assertEqual(outside.read_text(), "do not touch\n")

    def test_a_journal_with_no_subject_is_refused(self) -> None:
        """Semantic corruption: it parses as JSON and describes nothing trustworthy."""
        lt.LOCK_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        (lt.LOCK_JOURNAL_DIR / "release-plan-lock-nosubject.json").write_text(
            json.dumps({"state": "applying", "operations": []}) + "\n")
        reports = lt.recover_incomplete(recycle=None)
        self.assertEqual(reports[0]["outcome"], "needs-operator")

    def test_a_journal_predating_reconstructable_effects_is_refused(self) -> None:
        """An old hash-only journal cannot be replayed, and must say so rather
        than being treated as an empty transaction and marked resolved."""
        target = self.tmp / "legacy.md"
        target.write_text("content\n")
        lt.LOCK_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        (lt.LOCK_JOURNAL_DIR / "release-plan-lock-legacy.json").write_text(
            json.dumps({
                "kind": "release-plan-lock", "subject_uid": "legacy",
                "state": "applying", "operations": [{
                    "op": "create", "path": str(target), "sha256": "a" * 64,
                }],
            }) + "\n")
        reports = lt.recover_incomplete(recycle=None)
        self.assertEqual(reports[0]["outcome"], "needs-operator")
        self.assertTrue(target.is_file())
        # Assert the REASON, not just the outcome. Removing the hash-only guard
        # still yields needs-operator — the file then matches neither the absent
        # pre- nor post-content — so an outcome-only assertion passed with the
        # guard deleted. A refusal for the wrong reason is a refusal that will
        # stop happening when the wrong reason goes away.
        self.assertTrue(
            any("hashes only" in problem or "cannot be replayed" in problem
                for problem in reports[0]["diverged"]),
            f"the refusal did not name the unreplayable journal: {reports[0]['diverged']}")

    def test_an_unreadable_journal_is_reported_not_skipped(self) -> None:
        lt.LOCK_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        (lt.LOCK_JOURNAL_DIR / "release-plan-lock-garbage.json").write_text("{ not json")
        reports = lt.recover_incomplete(recycle=None)
        self.assertEqual(reports[0]["outcome"], "unreadable")

    def test_the_control_a_clean_transaction_still_applies(self) -> None:
        """Without this, every test above passes for a transaction that never works."""
        self._apply(self._plan, recycle=None)
        self.assertEqual(self.subject.read_text(), "after\n")
        self.assertTrue((self.tmp / "one.md").is_file())
        self.assertEqual(self._journal().get("state"), "applied")
        self.assertEqual(lt.recover_incomplete(recycle=None), [],
                         "recovery touched a completed transaction")


if __name__ == "__main__":
    unittest.main()
