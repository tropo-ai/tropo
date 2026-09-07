"""AC1-AC4 of 61f3153a (v1.92 Stream 3): the governance preflight gets a
producer, the corpus root is corrected, the lock runs its own boundary, and one
command reports every boundary.

Measured motivation: v1.91 produced ~20 refusals in one night, every one
correct, and not one knowable before the run started. Stream 1 registered seven
gates at `lock-static` and shipped nothing to feed them, so the command exited 0
with six of seven reporting SKIPPED-INPUTS-ABSENT, and the tool performing the
gesture that boundary governs referenced the preflight zero times.

Test names carry the words the spec's verify commands select on — producer,
corpus, lock, report — so `-k producer` and its siblings resolve. That coupling
is deliberate and fragile in one direction only: renaming a test can silently
narrow an acceptance command to zero tests, and pytest reports selecting nothing
as success. `TheSelectorsResolve` guards exactly that.

    python3 -m pytest -q vault/tools/tests/test_release_gate_inputs_v192.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
# The fixture-Studio helper lives beside this file (same gesture as
# test_release_plan_lock_end_to_end.py:25).
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import temp_studio  # noqa: E402

from lib import release_gate_inputs as gate_inputs  # noqa: E402
from lib.release_gates import VERDICT_PASS, VERDICT_REFUSED  # noqa: E402

PREFLIGHT_PATH = TOOLS / "tropo-release-preflight.py"
LOCK_PATH = TOOLS / "tropo-lock-release-plan.py"
LIVE_PLAN = "088e21aa"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TheProducerFeedsEveryGate(unittest.TestCase):
    """AC1. The measurement that was six-of-seven skipped."""

    def test_producer_supplies_every_declared_input(self) -> None:
        context = gate_inputs.build_context(
            STUDIO_ROOT, LIVE_PLAN, version_string="1.92.0"
        )
        for key in ("release_plan", "fan_in_manifest", "member_states",
                    "governed_index", "version_string", "source_tree",
                    "shipped_tool_corpus"):
            with self.subTest(input=key):
                self.assertIn(key, context)

    def test_producer_leaves_no_gate_skipped_for_absent_inputs(self) -> None:
        """The whole point. Every gate must reach a verdict."""
        preflight = _load("pf_ac1", PREFLIGHT_PATH)
        context = gate_inputs.build_context(
            STUDIO_ROOT, LIVE_PLAN, version_string="1.92.0"
        )
        outcomes = preflight.build_registry().run_phase("lock-static", context)
        skipped = [o for o in outcomes if "SKIPPED" in o.verdict.upper()
                   or "inputs absent" in (o.detail or "")]
        # v1.95 Spine B (f015997f8d8e): build-activation-key declares
        # pipeline_run — a per-ACTIVATION fact no plan can supply. The producer
        # feeds every plan-derivable input; the one honest skip is a gate whose
        # declared input is the activation, when no activation is in hand.
        registry = preflight.build_registry()
        self.assertEqual(
            [o.gate_id for o in skipped
             if "pipeline_run" not in registry.get(o.gate_id).required_inputs],
            [],
            "a plan-derivable input was left unfed: " + ", ".join(o.gate_id for o in skipped))
        self.assertTrue(outcomes)

    def test_producer_reads_member_states_from_entries_not_the_index(self) -> None:
        """The index is a derived surface this Studio has measured disagreeing
        with the files it describes. A lock decision rests on the entry."""
        context = gate_inputs.build_context(STUDIO_ROOT, LIVE_PLAN)
        for uid, state in context["member_states"].items():
            with self.subTest(uid=uid):
                text = (STUDIO_ROOT / "vault" / "files" / f"{uid}.md").read_text(
                    errors="replace"
                )
                self.assertIn(f"status: {state}", text)

    def test_producer_folds_acceptance_criteria_from_the_entry(self) -> None:
        """THE FIRST VERSION OF THIS TEST COULD NOT DETECT ITS OWN SUBJECT.

        It asserted every member's index row carries acceptance criteria — and
        the live index already carries them, so the assertion passed whether or
        not the fold existed. Removing the fold entirely left it green; the
        mutation surfaced on an unrelated test instead. I had also written into
        the module docstring that the index does not carry the field at all,
        which was an assumption I never checked and which is false.

        What the fold actually defends is a STALE index: a criterion added or
        reworded between rebuilds is invisible to the projection, and a gate
        reading a lagging row reports a spec as carrying no criteria. So this
        now builds exactly that — an index row with the field stripped — and
        asserts the entry wins.
        """
        members = ["5b608d28"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vault" / "files").mkdir(parents=True)
            # A real entry, and an index that has gone stale about it.
            source = STUDIO_ROOT / "vault" / "files" / "5b608d28.md"
            (root / "vault" / "files" / "5b608d28.md").write_text(
                source.read_text(errors="replace")
            )
            (root / "vault" / "00-index.jsonl").write_text(
                '{"uid": "5b608d28", "type": "dev-spec", "status": "locked"}\n'
            )
            rows = gate_inputs.governed_index(root, members)
        self.assertTrue(
            (rows.get("5b608d28") or {}).get("acceptance_criteria"),
            "the index row carried no criteria and the entry does; the entry "
            "must win, because the entry is the world and the index is a "
            "projection of it",
        )

    def test_producer_reports_an_unreadable_plan_as_operational(self) -> None:
        """'I cannot see' is never 'you are wrong'."""
        with self.assertRaises(gate_inputs.GateInputError):
            gate_inputs.build_context(STUDIO_ROOT, "deadbeef")

    def test_producer_refuses_a_non_plan_entry(self) -> None:
        with self.assertRaises(gate_inputs.GateInputError):
            gate_inputs.build_context(STUDIO_ROOT, "5b608d28")  # a dev-spec

    def test_producer_without_a_plan_still_returns_the_path_inputs(self) -> None:
        """A caller with no plan in hand must not be newly refused."""
        context = gate_inputs.build_context(STUDIO_ROOT)
        self.assertIn("source_tree", context)
        self.assertNotIn("release_plan", context)


class TheCorpusRootIsTheStudioRoot(unittest.TestCase):
    """AC2. The gate that had no refusal-direction test at all."""

    def _gate(self, corpus_root, members, index):
        preflight = _load("pf_ac2", PREFLIGHT_PATH)
        return preflight._lock_verify_commands_runnable({
            "fan_in_manifest": members,
            "governed_index": index,
            "shipped_tool_corpus": str(corpus_root),
        })

    def test_corpus_root_makes_real_targets_resolve(self) -> None:
        context = gate_inputs.build_context(STUDIO_ROOT, LIVE_PLAN)
        outcome = self._gate(
            context["shipped_tool_corpus"],
            context["fan_in_manifest"],
            context["governed_index"],
        )
        self.assertEqual(
            outcome.verdict, VERDICT_PASS,
            f"every v1.92 member's verify targets exist: {outcome.detail}",
        )

    def test_corpus_root_is_not_the_tools_directory(self) -> None:
        """The defect, pinned. Rooted at vault/tools the gate looks for
        <studio>/vault/tools/vault/tools/... and refuses on files that exist —
        the most expensive kind of false refusal, because it is specific and
        credible."""
        context = gate_inputs.build_context(STUDIO_ROOT, LIVE_PLAN)
        outcome = self._gate(
            STUDIO_ROOT / "vault" / "tools",
            context["fan_in_manifest"],
            context["governed_index"],
        )
        self.assertEqual(
            outcome.verdict, VERDICT_REFUSED,
            "if this ever passes, the paths changed shape and the producer's "
            "corpus root needs re-deriving rather than trusting",
        )

    def test_corpus_gate_refuses_a_planted_missing_target(self) -> None:
        """The refusal direction. This gate has only ever been observed
        passing; a probe that cannot fail protects nothing."""
        context = gate_inputs.build_context(STUDIO_ROOT, LIVE_PLAN)
        members = list(context["fan_in_manifest"])
        index = dict(context["governed_index"])
        victim = members[0]
        index[victim] = dict(index[victim], acceptance_criteria=[{
            "id": "AC-PLANT",
            "verify": {"command": "python3 vault/tools/tests/test_not_there.py"},
        }])
        outcome = self._gate(context["shipped_tool_corpus"], members, index)
        self.assertEqual(outcome.verdict, VERDICT_REFUSED)
        self.assertIn("test_not_there.py", outcome.detail)


class TheLockRunsItsOwnBoundary(unittest.TestCase):
    """AC3. The tool referenced the preflight zero times.

    These two tests stood on the LIVE plan 088e21aa until 2026-09-03. It was
    cancelled, and a cancelled plan is refused for its STATUS several checks
    before the preconditions are ever consulted -- so both tests failed on a
    message about lockable statuses while asserting on precondition text. The
    plan's identity was never the subject: what is under test is that the lock
    consults the lock-static boundary at all, and names every unmet gate.

    Repointing at the one currently-lockable live plan (301dce9d, v1.94) was the
    obvious move and is the wrong one -- that is precisely the plan the crew is
    working to make lockable, so the fix would re-arm the same trap and go red
    the moment the release succeeds. A precondition-refusal test needs a subject
    that is PERMANENTLY refusable, which no live plan can promise.

    So the subject is a fixture Studio: a plan in a lockable status whose single
    member is not terminal, which makes lock-members-terminal refuse by
    construction and keeps doing so no matter what the real vault does next.
    """

    #: Two governed uids that exist only inside the fixture Studio.
    FIXTURE_PLAN = "0dd0f1a7"
    FIXTURE_SPEC = "0dd0f1a8"

    def _fixture_studio(self):
        """A Studio whose plan is lockable and whose member is not done.

        `plan_release_lock` derives its studio root as
        `files_dir.parent.parent`, and loads the preflight from
        `<studio>/vault/tools/`. TempStudio copies the tool set, so the
        lock-static gates really run here rather than falling to warn-safe --
        which is the difference between this test asserting something and
        asserting nothing.
        """
        tmp = Path(tempfile.mkdtemp(prefix="gate-inputs-v192-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        studio = temp_studio.TempStudio(tmp).build()
        # Opt IN to live lock-static gates for this fixture only. This is not in
        # TempStudio's shared tool set on purpose: putting it there turns the
        # preconditions on for every consumer, and the one time it was tried it
        # broke test_release_plan_lock_end_to_end in five places. See the
        # PREFLIGHT_TOOL note in temp_studio.py.
        shutil.copy2(temp_studio.REAL_TOOLS / temp_studio.PREFLIGHT_TOOL,
                     studio.tools / temp_studio.PREFLIGHT_TOOL)
        (studio.files / f"{self.FIXTURE_PLAN}.md").write_text(
            "---\n"
            f"uid: {self.FIXTURE_PLAN}\n"
            "type: release-plan\n"
            "title: 'Fixture plan — permanently refusable by construction'\n"
            "status: design\n"
            "release_version: '9.99.0'\n"
            "ratchet_targets:\n"
            "  - fixture-ratchet\n"
            "dev_spec_uids:\n"
            f"  - {self.FIXTURE_SPEC}\n"
            "---\n\n# Fixture plan\n",
            encoding="utf-8",
        )
        # The member is deliberately NOT `done`: that is what keeps
        # lock-members-terminal refusing for as long as this fixture exists.
        (studio.files / f"{self.FIXTURE_SPEC}.md").write_text(
            "---\n"
            f"uid: {self.FIXTURE_SPEC}\n"
            "type: dev-spec\n"
            "title: 'Fixture member — not terminal'\n"
            "status: locked\n"
            "---\n\n# Fixture member\n",
            encoding="utf-8",
        )
        return studio

    def test_lock_refuses_a_plan_with_unmet_preconditions(self) -> None:
        studio = self._fixture_studio()
        lock = _load("lk_ac3", LOCK_PATH)
        with self.assertRaises(lock.LockRefused) as caught:
            lock.plan_release_lock(self.FIXTURE_PLAN, "test-principal",
                                   files_dir=studio.files)
        message = str(caught.exception)
        self.assertIn("unmet governance precondition", message)
        self.assertIn("lock-members-terminal", message)

    def test_lock_names_every_unmet_precondition_not_only_the_first(self) -> None:
        """An operator who fixes the named one only to meet the next is being
        drip-fed a truth the check already had."""
        studio = self._fixture_studio()
        lock = _load("lk_ac3b", LOCK_PATH)
        preflight = _load("pf_ac3", PREFLIGHT_PATH)
        context = gate_inputs.build_context(
            studio.root, self.FIXTURE_PLAN, version_string="9.99.0"
        )
        outcomes = preflight.build_registry().run_phase("lock-static", context)
        refused = [o for o in outcomes if o.verdict == VERDICT_REFUSED]
        self.assertTrue(refused, "fixture must produce at least one refusal, "
                                 "or this test asserts over an empty list")
        with self.assertRaises(lock.LockRefused) as caught:
            lock.plan_release_lock(self.FIXTURE_PLAN, "test-principal",
                                   files_dir=studio.files)
        for outcome in refused:
            with self.subTest(gate=outcome.gate_id):
                self.assertIn(outcome.gate_id, str(caught.exception))

    def test_lock_proceeds_when_the_check_itself_cannot_run(self) -> None:
        """Warn-safe on its own failure: a gate that cannot reach an answer must
        not refuse the lock. Verified by pointing the loader at nothing."""
        lock = _load("lk_ac3c", LOCK_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            empty_files = Path(tmp) / "vault" / "files"
            empty_files.mkdir(parents=True)
            # No preflight reachable from this root, and no plan either: the
            # precondition check must fail operationally, and the lock must
            # refuse for its OWN reason (plan does not resolve), not for the
            # check's.
            with self.assertRaises(lock.LockRefused) as caught:
                lock.plan_release_lock(LIVE_PLAN, "p", files_dir=empty_files)
            self.assertIn("does not resolve", str(caught.exception))
            self.assertNotIn("unmet governance precondition",
                             str(caught.exception))


class OneCommandReportsEveryBoundary(unittest.TestCase):
    """AC4. `--phase` was required, so 'all of them, once' was five commands."""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(PREFLIGHT_PATH), *args],
            capture_output=True, text=True, cwd=str(STUDIO_ROOT), timeout=180,
        )

    def test_report_covers_every_boundary_in_one_invocation(self) -> None:
        result = self._run("--phase", "all", "--plan-uid", LIVE_PLAN,
                           "--version-string", "1.92.0")
        for boundary in ("lock-static", "candidate", "pre-freeze",
                         "pre-outward-fire", "post-publication-reconcile"):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, result.stdout)

    def test_report_still_says_so_for_an_empty_boundary(self) -> None:
        """Preserved, not removed: printing nothing is ambiguous between 'no
        gates here' and 'the listing broke', and three boundaries stood empty
        for months behind that blank."""
        result = self._run("--phase", "all", "--plan-uid", LIVE_PLAN)
        # v1.95 Spine B (f015997f8d8e, 2026-09-05): candidate is no longer empty —
        # the build's guards register there; pre-freeze still is.
        self.assertIn("(0 gates registered at pre-freeze)", result.stdout)

    def test_report_exit_code_follows_the_existing_contract(self) -> None:
        refused = self._run("--phase", "all", "--plan-uid", LIVE_PLAN,
                            "--version-string", "1.92.0")
        self.assertEqual(refused.returncode, 2, "a refusal is a determinate verdict")
        operational = self._run("--phase", "lock-static", "--plan-uid", "deadbeef")
        self.assertEqual(operational.returncode, 3,
                         "an unreadable input is the retryable class, not a verdict")

    def test_report_names_a_refusal_from_a_real_boundary(self) -> None:
        result = self._run("--phase", "all", "--plan-uid", LIVE_PLAN,
                           "--version-string", "1.92.0")
        self.assertIn("REFUSED", result.stdout)


class TheSelectorsResolve(unittest.TestCase):
    """The spec's four verify commands select with -k. A renamed test would
    silently narrow one of them to zero tests, and pytest reports selecting
    nothing as SUCCESS — the same vacuous-pass shape that hid a phantom target
    in the last stream. So the selectors are asserted to match something."""

    def test_every_acceptance_selector_matches_at_least_one_test(self) -> None:
        for selector in ("producer", "corpus", "lock", "report"):
            with self.subTest(selector=selector):
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", "--collect-only",
                     str(Path(__file__)), "-k", selector],
                    capture_output=True, text=True, cwd=str(STUDIO_ROOT),
                    timeout=120,
                )
                self.assertNotIn(
                    "no tests ran", result.stdout,
                    f"-k {selector} selects nothing; the acceptance command for "
                    f"that criterion would pass vacuously",
                )


if __name__ == "__main__":
    unittest.main()
