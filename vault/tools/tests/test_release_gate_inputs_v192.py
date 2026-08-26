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
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

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
        self.assertEqual(
            [], skipped,
            "these gates still cannot fire: "
            + ", ".join(o.gate_id for o in skipped),
        )
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
    """AC3. The tool referenced the preflight zero times."""

    def test_lock_refuses_a_plan_with_unmet_preconditions(self) -> None:
        lock = _load("lk_ac3", LOCK_PATH)
        with self.assertRaises(lock.LockRefused) as caught:
            lock.plan_release_lock(LIVE_PLAN, "test-principal")
        message = str(caught.exception)
        self.assertIn("unmet governance precondition", message)
        self.assertIn("lock-members-terminal", message)

    def test_lock_names_every_unmet_precondition_not_only_the_first(self) -> None:
        """An operator who fixes the named one only to meet the next is being
        drip-fed a truth the check already had."""
        lock = _load("lk_ac3b", LOCK_PATH)
        preflight = _load("pf_ac3", PREFLIGHT_PATH)
        context = gate_inputs.build_context(
            STUDIO_ROOT, LIVE_PLAN, version_string="1.92.0"
        )
        outcomes = preflight.build_registry().run_phase("lock-static", context)
        refused = [o for o in outcomes if o.verdict == VERDICT_REFUSED]
        with self.assertRaises(lock.LockRefused) as caught:
            lock.plan_release_lock(LIVE_PLAN, "test-principal")
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
        self.assertIn("(0 gates registered at candidate)", result.stdout)

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
