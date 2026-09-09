"""AC1 (b1e78abb, v1.92): the retirement driver walks e2c7d185's eight
required-practice steps IN ORDER, verifies each artifact actually landed,
and cannot report completion while one is open.

Fixture-only, isolated via --root (per the driver's own design and the
spec's own §Acceptance: no live-vault dependency for pytest evidence). A
synthetic minimal playbook fixture stands in for e2c7d185 -- it carries the
same eight bold step labels in the same order and nothing else, which both
keeps the fixture small and lets the playbook-delta-refusal tests mutate it
freely without touching the real governed file.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_retire_driver_v192
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import git_env  # noqa: E402  (contained git for the one-commit fixture)

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("retire_driver", TOOLS / "tropo-retire-driver.py")
driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(driver)

SYNTHETIC_PLAYBOOK = """# Agent Retirement Playbook (fixture)

## Required Practice

1. **Append session memories** Append learnings.
2. **Write the letter** Author the successor letter.
3. **Reflection — optional; research-grade short form.** Write the reflection.
4. **Captain's Log** Append a personal note.
5. **Drain events** Answer or flag every open reply_required.
6. **Crew surfaces** Re-render the crew brief; update Status-Notes.
7. **Retirement broadcast** One tropo.broadcast.crew, category retirement.
8. **One commit.** The artifacts land together.

## Next Section

Unrelated content the section-boundary regex must stop before.
"""

AGENT = "fixture-agent"
GEN = "F1"


class OptionalCrewBrief(unittest.TestCase):
    def test_absent_brief_does_not_run_renderer_or_create_a_brief(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(driver.subprocess, "run") as run:
                ok, detail = driver.perform_crew_brief_rerender(root)
            self.assertIsNone(ok)
            self.assertIn("not applicable", detail)
            run.assert_not_called()
            self.assertFalse((root / "00-crew-brief.md").exists())
            for notes_ok in (True, False):
                with patch.object(driver, "observe_status_notes", return_value=(notes_ok, "fixture notes")):
                    step_ok, evidence = driver.observe_crew_surfaces(root, "fixture", "F1", None)
                    self.assertEqual(step_ok, notes_ok)
                    self.assertIn("not applicable", evidence)

    def test_existing_brief_retains_renderer_success_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "00-crew-brief.md").write_text("# Crew\n")
            renderer = root / driver.CREW_BRIEF_RENDERER_RELATIVE_PATH
            renderer.parent.mkdir(parents=True)
            renderer.write_text("# fixture renderer\n")
            for rc in (0, 1):
                with self.subTest(returncode=rc), patch.object(
                    driver.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], rc, "rendered", "fixture error"),
                ) as run:
                    ok, detail = driver.perform_crew_brief_rerender(root)
                    self.assertEqual(ok, rc == 0)
                    run.assert_called_once()
                    self.assertEqual(run.call_args.kwargs["cwd"], str(root))
                    if rc:
                        self.assertIn("fixture error", detail)

    def test_broken_brief_link_is_not_mistaken_for_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "00-crew-brief.md").symlink_to(root / "missing-target")
            ok, detail = driver.perform_crew_brief_rerender(root)
            self.assertFalse(ok)
            self.assertIn("cannot re-render", detail)


class RetireDriverFixture(unittest.TestCase):
    """Builds a COMPLETE world (all eight steps satisfied) once per test,
    so each test can break exactly one thing and assert exactly one step
    goes open — the mutation-per-step discipline AC1's own verify command
    names."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="retire-driver-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self._build_complete_world()

    def _write(self, relative: str, content: str) -> Path:
        p = self.root / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def _commit_world(self) -> None:
        """Step 8 reads git, so the complete world is a real repository.

        Contained through tests/git_env.py: an inherited GIT_DIR beats cwd, and
        a fixture that ran `git init` on the caller's environment is how the
        real studio was once re-initialised as bare.
        """
        git_env.init_repo(self.root)
        git_env.git_run("add", "-A", cwd=self.root)
        git_env.git_run("commit", "-q", "-m", "fixture retirement, one commit", cwd=self.root)

    def _build_complete_world(self) -> None:
        self._write("vault/playbooks/e2c7d185.md", SYNTHETIC_PLAYBOOK)

        # Step 1: session memories.
        self._write(
            f"agents/{AGENT}/.tropo-capsule/memory/agent-memories.jsonl",
            json.dumps({"learning": "something real"}) + "\n",
        )

        # Step 3: the letter.
        self._write(f"agents/{AGENT}/transfers/{GEN}.md", "Dear successor,\n\nBuild the ship.\n")

        # Step 4: reflection.
        self._write(
            f"agents/{AGENT}/reflections/{GEN.lower()}-reflection.md",
            "- **Mistake** — one reusable failure mode.\n"
            "- **Surprise** — what violated the model.\n"
            "- **Studio change** — one concrete improvement.\n",
        )

        # Step 5: Captain's Log, real entry marker.
        self._write(
            "library/captains-log.md",
            f"## {AGENT} {GEN} — 2026-08-24, at retirement\n\nA personal note.\n",
        )

        # Step 6: event drain — no bus files at all means load_event_union
        # returns empty, which scan_unanswered_rr correctly reports as zero
        # unanswered (nothing to be unanswered about).
        (self.root / "vault" / "events" / "streams").mkdir(parents=True, exist_ok=True)
        (self.root / "vault" / "events" / "receipts").mkdir(parents=True, exist_ok=True)

        # Step 7: crew surfaces — Status-Notes half (re-render is skipped via
        # --no-act in these tests; only the observed half is fixture-driven).
        self._write(
            f"vault/agents/fixture-uid.md",
            f"# fixture agent\n\n## §Status-Notes\n\n**{GEN} RETIRED 2026-08-24.** All done.\n",
        )

        # Step 8: retirement notice, on the fixture bus.
        self._write(
            "vault/events/streams/fixture-stream.jsonl",
            json.dumps({
                "specversion": "1.0",
                "type": "tropo.broadcast.crew",
                "source": f"/agents/{AGENT}",
                "time": "2026-08-24T00:00:00Z",
                "source_uid": "aaaaaaaa",
                "lifecycle": "evergreen",
                "data": {"category": "retirement", "agent": AGENT, "gen": GEN,
                          "t": "retired", "headline": f"{AGENT} {GEN} retired"},
                "id": "evt_fixturestream_00000001",
                "event_uid": "evt_fixturestream_00000001",
                "writer_instance_uid": "fixturestream",
                "stream_uid": "fixturestream",
                "local_seq": 1,
            }) + "\n",
        )

        self._commit_world()

    def _run(self):
        return driver.run_driver(
            self.root, AGENT, GEN,
            party_uid="aaaaaaaa", agent_root_uid="bbbbbbbb",
            unified_entry_uid="fixture-uid", perform_acts=False,
        )

    def test_the_complete_world_reports_complete(self) -> None:
        """Control: without this, every mutation test below could pass for
        a driver that always reports incomplete."""
        report = self._run()
        self.assertEqual(report["overall"], "complete", report["open_steps"])
        self.assertEqual(report["open_steps"], [])

    # --- Mutation per step: remove exactly one artifact, assert exactly
    # that step (and only that step) goes open. -----------------------------

    def test_mutation_step_1_session_memories(self) -> None:
        (self.root / f"agents/{AGENT}/.tropo-capsule/memory/agent-memories.jsonl").unlink()
        report = self._run()
        self.assertEqual(report["open_steps"], ["Append session memories"])

    def test_mutation_step_8_one_commit_split_across_two(self) -> None:
        """The step Mike's 2026-09-04 ruling added: the artifacts land together.

        The complete world commits everything once. Re-committing the letter on
        its own is exactly the split this step exists to catch, and it is the
        shape A169 and A171 actually retired in (measured on the real tree)."""
        letter = self.root / f"agents/{AGENT}/transfers/{GEN}.md"
        letter.write_text("Dear successor,\n\nBuild the ship. Then sail it.\n", encoding="utf-8")
        git_env.git_run("add", "-A", cwd=self.root)
        git_env.git_run("commit", "-q", "-m", "letter, on its own", cwd=self.root)
        report = self._run()
        self.assertEqual(report["open_steps"], ["One commit"])
        self.assertIn("split across commits", report["steps"]["One commit"]["evidence"])

    def test_mutation_step_3_the_letter(self) -> None:
        (self.root / f"agents/{AGENT}/transfers/{GEN}.md").unlink()
        report = self._run()
        self.assertEqual(report["open_steps"], ["Write the letter"])

    def test_mutation_step_4_reflection(self) -> None:
        """One of the three required headings is not the three."""
        self._write(
            f"agents/{AGENT}/reflections/{GEN.lower()}-reflection.md",
            "- **Mistake** — only one of the three headings is here.\n",
        )
        report = self._run()
        self.assertEqual(report["open_steps"], ["Reflection"])

    def test_an_absent_reflection_is_a_skip_the_playbook_authorises(self) -> None:
        """"Write it only if you have something a future researcher could use;
        otherwise skip." An absent reflection is not a missed step — reporting
        it open would push agents to write filler to satisfy an instrument."""
        (self.root / f"agents/{AGENT}/reflections/{GEN.lower()}-reflection.md").unlink()
        report = self._run()
        self.assertNotIn("Reflection", report["open_steps"])
        self.assertIn("optional", report["steps"]["Reflection"]["evidence"])

    def test_mutation_step_5_captains_log(self) -> None:
        self._write("library/captains-log.md", "Nothing about this generation at all.\n")
        report = self._run()
        self.assertEqual(report["open_steps"], ["Captain's Log"])

    def test_mutation_step_6_event_drain(self) -> None:
        self._write(
            "vault/events/streams/unanswered-stream.jsonl",
            json.dumps({
                "specversion": "1.0", "type": "tropo.message.sent",
                "source": "/agents/someone", "time": "2026-08-24T00:00:00Z",
                "source_uid": "cccccccc", "lifecycle": "evergreen",
                "subject": "aaaaaaaa",
                "data": {"reply_required": True, "body": "please answer"},
                "id": "evt_unansweredstream_00000001",
                "event_uid": "evt_unansweredstream_00000001",
                "writer_instance_uid": "unansweredstream",
                "stream_uid": "unansweredstream", "local_seq": 1,
            }) + "\n",
        )
        report = self._run()
        self.assertEqual(report["open_steps"], ["Drain events"])

    def test_mutation_step_7_crew_surfaces(self) -> None:
        self._write("vault/agents/fixture-uid.md", "# fixture agent\n\nno status-notes retirement declaration\n")
        report = self._run()
        self.assertEqual(report["open_steps"], ["Crew surfaces"])

    def test_mutation_step_8_retirement_notice(self) -> None:
        (self.root / "vault/events/streams/fixture-stream.jsonl").unlink()
        report = self._run()
        self.assertEqual(report["open_steps"], ["Retirement broadcast"])

    # --- Known-negatives for the two weak (token-shaped) observers ---------

    def test_known_negative_captains_log_token_match_is_not_an_observer(self) -> None:
        """The generation number appears in the file, but not as a real
        entry marker (someone else's narrative mentions it in passing)."""
        self._write(
            "library/captains-log.md",
            f"## Someone Else G1 — 2026-08-24\n\nI was helped by {GEN} today.\n",
        )
        report = self._run()
        self.assertIn("Captain's Log", report["open_steps"])

    def test_known_negative_reflection_bare_mention_is_not_a_real_section(self) -> None:
        """Found live authoring observe_reflection's own test: a case-
        insensitive bare substring search matched "narrative" inside
        ordinary prose ("no narrative section") with no actual heading.
        Fixed to require a real markdown heading; this pins the fix."""
        self._write(
            f"agents/{AGENT}/reflections/{GEN.lower()}-reflection.md",
            "# Reflection\n\nI made a mistake and had a surprise, but wrote no headings.\n",
        )
        report = self._run()
        self.assertIn("Reflection", report["open_steps"])

    def test_known_negative_status_notes_generation_string_alone_is_not_an_observer(self) -> None:
        """The generation string appears, but nothing declares it RETIRED."""
        self._write(
            "vault/agents/fixture-uid.md",
            f"# fixture agent\n\n## §Status-Notes\n\n**{GEN} ACTIVE, building v1.92.**\n",
        )
        report = self._run()
        self.assertIn("Crew surfaces", report["open_steps"])

    # --- Playbook-delta refusal ---------------------------------------------

    def test_a_renamed_step_label_refuses_and_names_it(self) -> None:
        self._write(
            "vault/playbooks/e2c7d185.md",
            SYNTHETIC_PLAYBOOK.replace("**One commit.**", "**Memory Consolidation.**"),
        )
        with self.assertRaises(driver.PlaybookDriftError) as caught:
            self._run()
        self.assertIn("Memory Consolidation", str(caught.exception))

    def test_a_missing_step_refuses(self) -> None:
        lines = SYNTHETIC_PLAYBOOK.splitlines()
        mutated = "\n".join(l for l in lines if "Reflection" not in l)
        self._write("vault/playbooks/e2c7d185.md", mutated)
        with self.assertRaises(driver.PlaybookDriftError):
            self._run()

    def test_a_reordered_pair_refuses(self) -> None:
        """Known-negative: swap two steps and the driver must refuse.

        This control silently stopped mutating when the fixture playbook was
        re-pinned on 2026-09-05: its .replace() named the OLD numbering, matched
        nothing, and the test passed by asserting a refusal that a no-op
        mutation happened to still produce. The assert below is the cure — a
        mutation that does not change the text is not a control."""
        before = "4. **Captain's Log** Append a personal note.\n5. **Drain events** Answer or flag every open reply_required.\n"
        after = "4. **Drain events** Answer or flag every open reply_required.\n5. **Captain's Log** Append a personal note.\n"
        mutated = SYNTHETIC_PLAYBOOK.replace(before, after)
        self.assertNotEqual(mutated, SYNTHETIC_PLAYBOOK,
                            "the mutation matched nothing — this control is not controlling")
        self._write("vault/playbooks/e2c7d185.md", mutated)
        with self.assertRaises(driver.PlaybookDriftError):
            self._run()

    def test_a_renamed_step_refuses_but_a_punctuation_tweak_does_not(self) -> None:
        """The tolerance is exactly as wide as the task asked and no wider."""
        tweaked = SYNTHETIC_PLAYBOOK.replace("**Captain's Log**", "**Captain's Log.**")
        self.assertNotEqual(tweaked, SYNTHETIC_PLAYBOOK)
        self._write("vault/playbooks/e2c7d185.md", tweaked)
        self._run()   # a trailing dot is not drift

        renamed = SYNTHETIC_PLAYBOOK.replace("**Captain's Log**", "**Skipper's Log**")
        self.assertNotEqual(renamed, SYNTHETIC_PLAYBOOK)
        self._write("vault/playbooks/e2c7d185.md", renamed)
        with self.assertRaises(driver.PlaybookDriftError):
            self._run()



class TheDeclaredCommandsActuallyRun(unittest.TestCase):
    """The tool's own frontmatter declared two invocations and BOTH exited 2.

    `--generation` is required and appeared in neither `cli_command` nor
    `belt_invocation`, so anyone copying the tool's own documented command got
    an argparse usage error. No test invoked `main()` at all — `subprocess` was
    imported by this suite and never used.

    This is the same class argus-a157 had to fix twice elsewhere in this cycle:
    a declared command that cannot run, and a suite that only ever calls
    functions so it cannot notice.
    """

    TOOL = Path(__file__).resolve().parents[1] / "tropo-retire-driver.py"
    ROOT = Path(__file__).resolve().parents[3]

    def _declared(self, field: str) -> str:
        for line in self.TOOL.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{field}:"):
                return line.split(":", 1)[1].strip().strip('"')
        self.fail(f"{field} is not declared in the tool's frontmatter")

    def _run(self, argv):
        import subprocess as sp
        return sp.run([sys.executable, str(self.TOOL), *argv],
                      capture_output=True, text=True,
                      cwd=str(self.ROOT), timeout=120)

    def test_the_declared_cli_command_is_runnable(self) -> None:
        declared = self._declared("cli_command")
        argv = [a for a in declared.split()[2:]]  # drop 'python3 <tool>'
        argv = [{"<slug>": "argus", "<GEN>": "A156",
                 "<studio-root>": str(self.ROOT)}.get(a, a) for a in argv]
        result = self._run(argv)
        self.assertNotEqual(
            result.returncode, 2,
            f"the tool's own declared cli_command exits 2 (argparse usage): "
            f"{declared!r}\n{result.stderr[-300:]}",
        )

    def test_the_declared_belt_invocation_names_every_required_flag(self) -> None:
        declared = self._declared("belt_invocation")
        for required in ("--agent", "--generation"):
            self.assertIn(
                required, declared,
                f"belt_invocation omits {required}, which argparse requires",
            )

    def test_main_honours_the_exit_code_contract(self) -> None:
        """0 complete / 1 incomplete / 3 refused — never asserted before."""
        result = self._run(["--agent", "argus", "--generation", "A156",
                            "--root", str(self.ROOT)])
        self.assertIn(result.returncode, (0, 1),
                      f"unexpected exit {result.returncode}: {result.stderr[-300:]}")

if __name__ == "__main__":
    unittest.main()


class TheRegistryTracksTheLivePlaybook(unittest.TestCase):
    """The regression the task asked for (f0150b2a4678 item 5).

    The driver refused every invocation from 2026-09-04 to 2026-09-05 because
    the playbook was amended and this registry was not — and NOTHING went red,
    because every existing test asserted against the suite's own synthetic
    fixture. Three homes for one list, and the two that agreed were both copies.

    This reads the LIVE playbook. The next amendment goes red here, in the
    suite, instead of silently at the next agent's retirement.
    """

    def test_registry_equals_the_live_playbook_labels(self) -> None:
        root = Path(__file__).resolve().parents[3]
        parsed = driver.parse_required_steps(root)   # raises on drift
        self.assertEqual(parsed, list(driver.REQUIRED_STEP_LABELS))

    def test_the_refusal_names_the_cure_not_only_the_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vault" / "playbooks").mkdir(parents=True)
            (root / "vault" / "playbooks" / "e2c7d185.md").write_text(
                SYNTHETIC_PLAYBOOK.replace("**One commit.**", "**Two commits.**"),
                encoding="utf-8")
            with self.assertRaises(driver.PlaybookDriftError) as cm:
                driver.parse_required_steps(root)
        self.assertIn("CURE:", str(cm.exception))
        self.assertIn("REQUIRED_STEP_LABELS", str(cm.exception))
