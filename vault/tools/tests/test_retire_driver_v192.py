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

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("retire_driver", TOOLS / "tropo-retire-driver.py")
driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(driver)

SYNTHETIC_PLAYBOOK = """# Agent Retirement Playbook (fixture)

## Required Practice

1. **Session memories.** Append learnings.
2. **Memory fold.** Fold into agent-memory.md.
3. **The letter.** Author the successor letter.
4. **Reflection.** Write the reflection.
5. **Captain's Log.** Append a personal note.
6. **Event drain.** Answer or flag every open reply_required.
7. **Crew surfaces.** Re-render the crew brief; update Status-Notes.
8. **Retirement notice.** One tropo.broadcast.crew, category retirement.

## Next Section

Unrelated content the section-boundary regex must stop before.
"""

AGENT = "fixture-agent"
GEN = "F1"


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

    def _build_complete_world(self) -> None:
        self._write("vault/playbooks/e2c7d185.md", SYNTHETIC_PLAYBOOK)

        # Step 1: session memories.
        self._write(
            f"agents/{AGENT}/.tropo-capsule/memory/agent-memories.jsonl",
            json.dumps({"learning": "something real"}) + "\n",
        )

        # Step 2: memory fold, in-line branch.
        self._write(
            f"agents/{AGENT}/.tropo-capsule/memory/agent-memory.md",
            f"---\ncurated_by: {AGENT}-{GEN}\n---\n\n# memory\n",
        )

        # Step 3: the letter.
        self._write(f"agents/{AGENT}/transfers/{GEN}.md", "Dear successor,\n\nBuild the ship.\n")

        # Step 4: reflection.
        self._write(
            f"agents/{AGENT}/reflections/{GEN.lower()}-reflection.md",
            "## File Manifest\n\n- one file\n\n## Narrative\n\nWhat mattered.\n",
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
        self.assertEqual(report["open_steps"], ["Session memories."])

    def test_mutation_step_2_memory_fold(self) -> None:
        self._write(
            f"agents/{AGENT}/.tropo-capsule/memory/agent-memory.md",
            "---\ncurated_by: someone-else\n---\n\n# memory\n",
        )
        report = self._run()
        self.assertEqual(report["open_steps"], ["Memory fold."])

    def test_mutation_step_3_the_letter(self) -> None:
        (self.root / f"agents/{AGENT}/transfers/{GEN}.md").unlink()
        report = self._run()
        self.assertEqual(report["open_steps"], ["The letter."])

    def test_mutation_step_4_reflection(self) -> None:
        self._write(
            f"agents/{AGENT}/reflections/{GEN.lower()}-reflection.md",
            "## File Manifest\n\nonly this section exists\n",
        )
        report = self._run()
        self.assertEqual(report["open_steps"], ["Reflection."])

    def test_mutation_step_5_captains_log(self) -> None:
        self._write("library/captains-log.md", "Nothing about this generation at all.\n")
        report = self._run()
        self.assertEqual(report["open_steps"], ["Captain's Log."])

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
        self.assertEqual(report["open_steps"], ["Event drain."])

    def test_mutation_step_7_crew_surfaces(self) -> None:
        self._write("vault/agents/fixture-uid.md", "# fixture agent\n\nno status-notes retirement declaration\n")
        report = self._run()
        self.assertEqual(report["open_steps"], ["Crew surfaces."])

    def test_mutation_step_8_retirement_notice(self) -> None:
        (self.root / "vault/events/streams/fixture-stream.jsonl").unlink()
        report = self._run()
        self.assertEqual(report["open_steps"], ["Retirement notice."])

    # --- Known-negatives for the two weak (token-shaped) observers ---------

    def test_known_negative_captains_log_token_match_is_not_an_observer(self) -> None:
        """The generation number appears in the file, but not as a real
        entry marker (someone else's narrative mentions it in passing)."""
        self._write(
            "library/captains-log.md",
            f"## Someone Else G1 — 2026-08-24\n\nI was helped by {GEN} today.\n",
        )
        report = self._run()
        self.assertIn("Captain's Log.", report["open_steps"])

    def test_known_negative_reflection_bare_mention_is_not_a_real_section(self) -> None:
        """Found live authoring observe_reflection's own test: a case-
        insensitive bare substring search matched "narrative" inside
        ordinary prose ("no narrative section") with no actual heading.
        Fixed to require a real markdown heading; this pins the fix."""
        self._write(
            f"agents/{AGENT}/reflections/{GEN.lower()}-reflection.md",
            "## File Manifest\n\n- one file\n\nI have no narrative to add this time.\n",
        )
        report = self._run()
        self.assertIn("Reflection.", report["open_steps"])

    def test_known_negative_status_notes_generation_string_alone_is_not_an_observer(self) -> None:
        """The generation string appears, but nothing declares it RETIRED."""
        self._write(
            "vault/agents/fixture-uid.md",
            f"# fixture agent\n\n## §Status-Notes\n\n**{GEN} ACTIVE, building v1.92.**\n",
        )
        report = self._run()
        self.assertIn("Crew surfaces.", report["open_steps"])

    # --- Playbook-delta refusal ---------------------------------------------

    def test_a_renamed_step_label_refuses_and_names_it(self) -> None:
        self._write(
            "vault/playbooks/e2c7d185.md",
            SYNTHETIC_PLAYBOOK.replace("**Memory fold.**", "**Memory Consolidation.**"),
        )
        with self.assertRaises(driver.PlaybookDriftError) as caught:
            self._run()
        self.assertIn("Memory Consolidation", str(caught.exception))

    def test_a_missing_step_refuses(self) -> None:
        lines = SYNTHETIC_PLAYBOOK.splitlines()
        mutated = "\n".join(l for l in lines if "Reflection." not in l)
        self._write("vault/playbooks/e2c7d185.md", mutated)
        with self.assertRaises(driver.PlaybookDriftError):
            self._run()

    def test_a_reordered_pair_refuses(self) -> None:
        mutated = SYNTHETIC_PLAYBOOK.replace(
            "5. **Captain's Log.** Append a personal note.\n"
            "6. **Event drain.** Answer or flag every open reply_required.\n",
            "5. **Event drain.** Answer or flag every open reply_required.\n"
            "6. **Captain's Log.** Append a personal note.\n",
        )
        self._write("vault/playbooks/e2c7d185.md", mutated)
        with self.assertRaises(driver.PlaybookDriftError):
            self._run()



class TheMemoryFoldObserverIsAnchored(unittest.TestCase):
    """The branch that carried the LIVE verdict was a bare substring match.

    `observe_memory_fold` branch 2 read `if gen.lower() in child.name.lower()`
    over `memory/history/`. No test in the corpus touched it, and BOTH real
    driver runs (A155 and A153) resolved step 2 through it rather than through
    `curated_by` — so the observer deciding real retirements was matching
    substrings. Measured against the real argus tree before the fix:

        gen 'A155' -> COMPLETE   (correct: a155-agent-memory-snapshot.md)
        gen 'A15'  -> COMPLETE   (WRONG: matched a153-agent-memory-snapshot.md)
        gen 'A1'   -> COMPLETE   (WRONG: same)
        gen '1'    -> COMPLETE   (WRONG: matched a153-... and 1fee9220.md)

    Found by an independent adversarial pass. A generation prefix must not
    inherit a longer generation's fold.
    """

    ROOT = Path(__file__).resolve().parents[3]

    def _observe(self, gen: str):
        return driver.observe_memory_fold(self.ROOT, "argus", gen)[0]

    def test_a_real_generation_still_resolves(self) -> None:
        self.assertTrue(self._observe("A155"))

    def test_a_prefix_of_a_real_generation_does_not_inherit_it(self) -> None:
        for prefix in ("A15", "A1", "1"):
            with self.subTest(gen=prefix):
                self.assertFalse(
                    self._observe(prefix),
                    f"generation {prefix!r} resolved the memory fold complete "
                    f"by matching a longer generation's snapshot filename",
                )

    def test_an_unrelated_token_does_not_resolve(self) -> None:
        self.assertFalse(self._observe("ZZ99"))


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
