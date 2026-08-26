"""AC6 (5b608d28, v1.92 Stream 1): ONE command walks the release order
cold — the executable order retro Action 2 requires.

Three assertions, matching the locked criterion's evidence exactly:
  1. From a clean fixture studio with no prior run state, the runner
     reports the first action without any other command having been run.
  2. At a judgment slot it halts and names both the executor class and a
     runnable command string.
  3. Driven by the fixture profile it walks that profile's different
     order, proving it reads the profile rather than a built-in list.

Plus the behavior the criterion names alongside these — "deterministic
slots execute" — proven via a real side effect, not a trusted boolean, and
the safety boundary that makes an opt-in `execute` flag defensible at all.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_release_runner_cold_v192
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.release_profile import load_profile, load_profile_from_frontmatter  # noqa: E402

RELEASE_RUN_SCRIPT = TOOLS / "tropo-release-run.py"


def _load_release_run_module():
    name = "release_run_ac6_cold_test"
    spec = importlib.util.spec_from_file_location(name, RELEASE_RUN_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Same registration Argus A156 warned about for dataclasses on py3.9
    # when a module is loaded by path rather than by normal import.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_profile_to_studio(studio_root: Path, frontmatter: dict) -> Path:
    """Write a fixture profile to an actual `vault/files/<uid>.md` under a
    temp studio, so a disk-reading test exercises the real `load_profile`
    path rather than a hand-built in-memory dict."""
    files_dir = studio_root / "vault" / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    uid = frontmatter["uid"]
    text = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n\n# fixture\n"
    path = files_dir / f"{uid}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _profile_frontmatter(order_first="tool"):
    """A minimal, valid fixture profile. `order_first` controls whether the
    build slot's first step is deterministic or a judgment step, so two
    calls with different values produce two DIFFERENTLY-ORDERED profiles
    from the same helper."""
    if order_first == "tool":
        build_steps = [
            {
                "step_uid": "10000001",
                "kind": "tool",
                "entry": "fixture_ops.py:do_build",
                "description": "build the fixture artifact",
            },
            {
                "step_uid": "10000002",
                "kind": "playbook",
                "entry": "some-procedure-uid",
                "executor": "human",
                "description": "a human reviews the build",
            },
        ]
    else:
        build_steps = [
            {
                "step_uid": "10000002",
                "kind": "playbook",
                "entry": "some-procedure-uid",
                "executor": "human",
                "description": "a human reviews the build",
            },
            {
                "step_uid": "10000001",
                "kind": "tool",
                "entry": "fixture_ops.py:do_build",
                "description": "build the fixture artifact",
            },
        ]
    return {
        "uid": "20000003",
        "type": "release-profile",
        "product": "fixture-product",
        "pipeline_uid": "30000004",
        "slots": [
            {"slot": "build-the-artifact", "gate_contract": "candidate", "steps": build_steps},
            {
                "slot": "verify-the-artifact",
                "gate_contract": "pre-freeze",
                "steps": [
                    {
                        "step_uid": "10000005",
                        "kind": "tool",
                        "entry": "fixture_ops.py:do_verify",
                        "description": "verify the fixture artifact",
                    }
                ],
            },
            {
                "slot": "publish-the-artifact",
                "gate_contract": "pre-outward-fire",
                "steps": [
                    {
                        "step_uid": "10000006",
                        "kind": "tool",
                        "entry": "fixture_ops.py:do_publish",
                        "description": "publish the fixture artifact",
                    }
                ],
            },
        ],
    }


class ColdWalkReportsFirstActionWithNothingElseRun(unittest.TestCase):
    """AC6 evidence, assertion 1.

    Loads through the REAL disk path (`load_profile` against a temp
    studio), not a hand-built in-memory dict. An independent adversarial
    pass found the original version of this test built its profile from a
    Python dict and never touched the temp directory it asserted was
    still empty afterward — the code under test could not possibly have
    written to a directory it never received, so the assertion was
    structurally incapable of failing. Loading from disk makes "no new
    files appeared" a claim about something the code actually does.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac6-cold-studio-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.release_run = _load_release_run_module()
        self.declared_leaves = ("10000001", "10000002", "10000005", "10000006")
        _write_profile_to_studio(self.tmp, _profile_frontmatter())

    def _snapshot(self):
        return sorted(str(p.relative_to(self.tmp)) for p in self.tmp.rglob("*") if p.is_file())

    def test_clean_fixture_studio_reports_first_action_with_no_new_files(self) -> None:
        before = self._snapshot()
        self.assertEqual(len(before), 1, "the fixture studio must start with only the profile file")

        profile = load_profile(self.tmp, "20000003", declared_leaves=self.declared_leaves)
        action = self.release_run.first_action(profile)

        self.assertIsNotNone(action)
        self.assertEqual(action.step_uid, "10000001")
        after = self._snapshot()
        self.assertEqual(
            before, after,
            "loading the profile from disk and reporting the first action must "
            "create no new files in the fixture studio",
        )

    def test_first_action_is_stable_across_repeated_cold_calls(self) -> None:
        """A clean walk is not stateful: asking twice reports the same
        first action both times, proving nothing was consumed the first
        time."""
        profile = load_profile(self.tmp, "20000003", declared_leaves=self.declared_leaves)
        first = self.release_run.first_action(profile)
        second = self.release_run.first_action(profile)
        self.assertEqual(first.step_uid, second.step_uid)
        self.assertEqual(first, second)

    def test_a_different_disk_file_produces_a_different_first_action(self) -> None:
        """Teeth for the disk-reading claim itself: a second temp studio
        with a DIFFERENT profile on disk must report a DIFFERENT first
        action, proving `load_profile` reads what is actually there
        rather than a cached or hardcoded value."""
        other = Path(tempfile.mkdtemp(prefix="ac6-cold-studio-b-"))
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        _write_profile_to_studio(other, _profile_frontmatter(order_first="judgment"))

        profile_a = load_profile(self.tmp, "20000003", declared_leaves=self.declared_leaves)
        profile_b = load_profile(other, "20000003", declared_leaves=self.declared_leaves)
        action_a = self.release_run.first_action(profile_a)
        action_b = self.release_run.first_action(profile_b)
        self.assertNotEqual(action_a.step_uid, action_b.step_uid)


class JudgmentHaltNamesExecutorAndACommand(unittest.TestCase):
    """AC6 evidence, assertion 2."""

    def setUp(self) -> None:
        self.release_run = _load_release_run_module()

    def test_halt_names_executor_class_and_a_runnable_command(self) -> None:
        profile = load_profile_from_frontmatter(_profile_frontmatter(order_first="judgment"))
        outcome = self.release_run.walk(profile)
        self.assertEqual(outcome.status, "halted")
        halt = outcome.halted_at
        self.assertIsNotNone(halt)
        self.assertEqual(halt.executor, "human")
        self.assertIsInstance(halt.command, str)
        self.assertTrue(halt.command, "the halt must name a non-empty runnable command")
        self.assertIn("some-procedure-uid", halt.command)
        self.assertIn("human", halt.command)

    def test_a_deterministic_step_never_carries_a_halt(self) -> None:
        """Control: only a judgment step produces halted_at; an
        all-deterministic walk completes instead."""
        fm = _profile_frontmatter()
        fm["slots"][0]["steps"] = [fm["slots"][0]["steps"][0]]  # drop the judgment step
        profile = load_profile_from_frontmatter(fm)
        outcome = self.release_run.walk(profile)
        self.assertEqual(outcome.status, "complete")
        self.assertIsNone(outcome.halted_at)


class DrivenByAFixtureProfileItWalksThatProfilesOrder(unittest.TestCase):
    """AC6 evidence, assertion 3 — the SAME profile-loading path, two
    genuinely different declared orders, two different verdicts."""

    def setUp(self) -> None:
        self.release_run = _load_release_run_module()

    def test_tool_first_profile_reports_a_tool_as_the_first_action(self) -> None:
        profile = load_profile_from_frontmatter(_profile_frontmatter(order_first="tool"))
        action = self.release_run.first_action(profile)
        self.assertTrue(action.deterministic)
        self.assertEqual(action.step_uid, "10000001")

    def test_judgment_first_profile_reports_a_playbook_as_the_first_action(self) -> None:
        profile = load_profile_from_frontmatter(_profile_frontmatter(order_first="judgment"))
        action = self.release_run.first_action(profile)
        self.assertFalse(action.deterministic)
        self.assertEqual(action.step_uid, "10000002")

    def test_two_profiles_through_the_same_loader_produce_different_verdicts(self) -> None:
        """The control that gives the other two assertions teeth: if the
        runner ignored the profile, both orderings would report the same
        first action."""
        tool_first = load_profile_from_frontmatter(_profile_frontmatter(order_first="tool"))
        judgment_first = load_profile_from_frontmatter(
            _profile_frontmatter(order_first="judgment")
        )
        first_a = self.release_run.first_action(tool_first)
        first_b = self.release_run.first_action(judgment_first)
        self.assertNotEqual(first_a.step_uid, first_b.step_uid)
        self.assertNotEqual(first_a.deterministic, first_b.deterministic)


class DeterministicStepsExecute(unittest.TestCase):
    """The criterion's other named behavior: "deterministic slots
    execute" — proven by a real side effect, not by trusting a boolean."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac6-execute-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.release_run = _load_release_run_module()
        self.marker = self.tmp / "build_ran.marker"
        fixture_module = self.tmp / "fixture_ops.py"
        fixture_module.write_text(
            "from pathlib import Path\n"
            f"MARKER = Path(r'{self.marker}')\n"
            "def do_build():\n"
            "    MARKER.write_text('built')\n",
            encoding="utf-8",
        )

    def _all_tool_profile(self):
        return {
            "uid": "40000007",
            "type": "release-profile",
            "product": "execute-fixture",
            "pipeline_uid": "30000004",
            "slots": [
                {
                    "slot": "build-the-artifact",
                    "gate_contract": "candidate",
                    "steps": [
                        {
                            "step_uid": "10000001",
                            "kind": "tool",
                            "entry": "fixture_ops.py:do_build",
                            "description": "build the fixture artifact",
                        }
                    ],
                },
                {"slot": "verify-the-artifact", "gate_contract": "pre-freeze", "steps": []},
                {"slot": "publish-the-artifact", "gate_contract": "pre-outward-fire", "steps": []},
            ],
        }

    def test_execute_true_actually_invokes_the_resolved_callable(self) -> None:
        self.assertFalse(self.marker.exists())
        profile = load_profile_from_frontmatter(self._all_tool_profile())
        outcome = self.release_run.walk(profile, base_dir=self.tmp, execute=True)
        self.assertEqual(outcome.status, "complete")
        self.assertTrue(outcome.actions[0].invoked)
        self.assertTrue(self.marker.exists(), "the fixture callable must have actually run")
        self.assertEqual(self.marker.read_text(), "built")

    def test_execute_false_is_the_default_and_invokes_nothing(self) -> None:
        """Safety control: the same profile, the same walk, no flag —
        nothing happens. This is the property that makes an opt-in
        `execute` capability defensible on a runner whose profile can
        name an irreversible outward act."""
        self.assertFalse(self.marker.exists())
        profile = load_profile_from_frontmatter(self._all_tool_profile())
        outcome = self.release_run.walk(profile, base_dir=self.tmp)
        self.assertEqual(outcome.status, "complete")
        self.assertFalse(outcome.actions[0].invoked)
        self.assertFalse(self.marker.exists(), "the default walk must not have run anything")

    def test_a_bare_command_entry_is_reported_not_invoked_even_with_execute_true(self) -> None:
        """A tool entry with no `<path>:<callable>` shape (most of today's
        real bindings) cannot be resolved to a callable — it is reported,
        never guessed at as something importable."""
        fm = self._all_tool_profile()
        fm["slots"][0]["steps"][0]["entry"] = "some-real-cli-tool.py --flag"
        profile = load_profile_from_frontmatter(fm)
        outcome = self.release_run.walk(profile, base_dir=self.tmp, execute=True)
        self.assertFalse(outcome.actions[0].invoked)
        self.assertEqual(outcome.actions[0].command, "some-real-cli-tool.py --flag")


class MainIsInvokedAsASubprocess(unittest.TestCase):
    """A test that only ever calls functions cannot notice broken CLI
    wiring. An independent adversarial pass named this gap explicitly —
    `main()` was never invoked by any test here — and pointed at
    `TheOperatorPathReachesCompleteAndExitsZero` in
    `test_completion_reads_producers_v192.py` as the pattern that already
    closed the same class of gap on AC4. Driven against the real Studio
    root and the real shipped profile, same as that pattern, rather than
    a synthetic fixture: a fixture studio would need its own fake
    634913c2 pipeline tree for `release_bindings.declared_leaves()` to
    walk, and the real one already exists.

    The adversarial pass also found that a stranger could not run this
    cold at all — `profile_uid` was a required positional and nothing
    discovered it, while AC5's own behavior promises a profile is
    discovered by uid and type like every other governed record. Fixed
    via `iter_release_profile_uids`; the auto-discovery test below is
    that fix's proof.
    """

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(RELEASE_RUN_SCRIPT), *args, "--vault-path", str(REPO)],
            capture_output=True, text=True, cwd=str(REPO), timeout=60,
        )

    def test_the_cli_exits_zero_against_the_real_shipped_profile(self) -> None:
        result = self._run("6bf18510")
        self.assertEqual(
            result.returncode, 0,
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )
        self.assertIn("HALTED", result.stdout)

    def test_auto_discovery_with_no_positional_argument(self) -> None:
        """A stranger who does not already know the uid can still run
        this cold — the exact gap the adversarial pass named."""
        result = self._run()
        self.assertEqual(
            result.returncode, 0,
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )
        self.assertIn("6bf18510", result.stdout)

    def test_a_nonexistent_uid_exits_nonzero_naming_the_problem(self) -> None:
        result = self._run("deadbeef")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR", result.stderr)
        self.assertIn("deadbeef", result.stderr)


if __name__ == "__main__":
    unittest.main()
