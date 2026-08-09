"""Governed Autonomy S1 (ef65fccd/ace391d4) — acceptance gauntlet for the retirement
substance gates R-1..R-4, per f67fe144.

THE A129 REPLAY IS THE ACCEPTANCE (spec's own words): reconstruct A129's exact move —
invented "Signal Secured"/"Transfer Written" milestone events in run.jsonl, no RETIRING
transition, no fold-boundary, no forward transfer — and prove op_close's substance gates
refuse it, naming every missing item individually. Then perform the real retirement work
and prove it passes. Both directions proven, not asserted (T-1..T-4 below cover R-1..R-4
individually; T-5 is the full integrated replay in both directions).

Self-running (python3 test_close_tool_substance_gates_ef65fccd.py) and pytest-compatible.
"""
from __future__ import annotations
import importlib.util
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_VAULT_TOOLS = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("closetool", str(_VAULT_TOOLS / "40b2f455.py"))
closetool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(closetool)


def _args(**overrides):
    base = dict(retirement_run_folder="", reflection_path="", retiring_flip_recorded_at="")
    base.update(overrides)
    return types.SimpleNamespace(**base)


class _SandboxedCloseToolTest(unittest.TestCase):
    """Patches closetool's module-level VAULT_ROOT/VAULT_FILES so nothing touches the
    real vault. Mirrors the pattern established in test_v1_84_1_closeout_hardening_8c8ca68c.py
    for the pipeline-runtime engine."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="close-gates-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.files.mkdir(parents=True)
        self.agents_dir = self.tmp / "vault" / "agents"
        self.agents_dir.mkdir(parents=True)
        self._orig_root = closetool.VAULT_ROOT
        self._orig_files = closetool.VAULT_FILES
        self._orig_agents = closetool.VAULT_AGENTS
        closetool.VAULT_ROOT = self.tmp
        closetool.VAULT_FILES = self.files
        closetool.VAULT_AGENTS = self.agents_dir

    def tearDown(self):
        closetool.VAULT_ROOT = self._orig_root
        closetool.VAULT_FILES = self._orig_files
        closetool.VAULT_AGENTS = self._orig_agents
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def _seed_identity(self, slug: str, agent_uid: str, status: str):
        """Activation thin-pointer (declares agent_uid) + unified identity entry.
        Unified entry lives at vault/agents/<uid>.md — a sibling of vault/files/,
        not inside it (T28 caught this the hard way: a self-consistent fixture
        that seeded the unified entry under vault/files/ made R-1 pass against
        the fixture's own wrong assumption while the real resolver 404'd against
        real substrate)."""
        self._write(
            self.tmp / "agents" / slug / f"{slug}-activation.md",
            f"---\nagent_uid: {agent_uid}\n---\n\n# {slug} activation\n",
        )
        self._write(
            self.agents_dir / f"{agent_uid}.md",
            f"---\nuid: {agent_uid}\ntype: agent\nagent: {slug}\nstatus: {status}\n---\n\n# {slug}\n",
        )

    def _seed_memory(self, slug: str, *, last_curated: str, top_of_mind_count: int,
                      transfer_status: str, transfer_names_successor: str | None):
        top_lines = "\n".join(f"- [entry{i}](entries/entry{i}.md) score=0.9 · procedural · x"
                               for i in range(top_of_mind_count))
        transfer_body = (f"## §Living-Transfer-from-Predecessor\n\nHanding off to "
                          f"{transfer_names_successor}.\n" if transfer_names_successor
                          else "")
        self._write(
            self.tmp / "agents" / slug / ".tropo-capsule" / "memory" / "agent-memory.md",
            f"---\nlast_curated: {last_curated}\ntransfer_status: {transfer_status}\n---\n\n"
            f"# Agent Memory\n\n## §Top-of-Mind\n\n{top_lines}\n\n{transfer_body}\n"
            f"## §History\n\nptr\n",
        )


class TestR1Signal(_SandboxedCloseToolTest):
    """T-1: R-1 must read the identity file's CURRENT status, not any claim about it."""

    def test_status_active_refuses(self):
        self._seed_identity("scratchgen", "aaaaaaaa", status="active")
        self.assertIsNotNone(closetool._gate_r1_signal("scratchgen"),
                              "status:active (never transitioned) must refuse")

    def test_status_retiring_passes(self):
        self._seed_identity("scratchgen", "aaaaaaaa", status="retiring")
        self.assertIsNone(closetool._gate_r1_signal("scratchgen"))

    def test_status_already_retired_refuses(self):
        """A129's actual failure mode is subtler than 'active' — replaying his exact
        move: the identity file was never touched at all (still whatever it was), while
        a fake milestone event claims the transition happened. Any non-RETIRING value
        must refuse, not just 'active' specifically."""
        self._seed_identity("scratchgen", "aaaaaaaa", status="retired")
        self.assertIsNotNone(closetool._gate_r1_signal("scratchgen"))

    def test_no_identity_file_refuses(self):
        self.assertIsNotNone(closetool._gate_r1_signal("nonexistent-agent"))


class TestR2Preserve(_SandboxedCloseToolTest):
    """T-2: R-2 must read the memory surface's real freshness stamp + entry bound."""

    def test_stale_last_curated_refuses(self):
        self._seed_memory("scratchgen", last_curated="2020-01-01", top_of_mind_count=3,
                           transfer_status="FINAL/RETIRING", transfer_names_successor="X2")
        self.assertIsNotNone(closetool._gate_r2_preserve("scratchgen"),
                              "a fold that never ran this session must refuse")

    def test_fresh_fold_within_bound_passes(self):
        self._seed_memory("scratchgen", last_curated=closetool.TODAY, top_of_mind_count=8,
                           transfer_status="FINAL/RETIRING", transfer_names_successor="X2")
        self.assertIsNone(closetool._gate_r2_preserve("scratchgen"))

    def test_fresh_fold_over_bound_refuses(self):
        self._seed_memory("scratchgen", last_curated=closetool.TODAY, top_of_mind_count=20,
                           transfer_status="FINAL/RETIRING", transfer_names_successor="X2")
        self.assertIsNotNone(closetool._gate_r2_preserve("scratchgen"),
                              "over the memory.capsule A1 bound (>15) must refuse per the "
                              "IN-LINE FOLD BOUND rule")

    def test_no_memory_surface_refuses(self):
        self.assertIsNotNone(closetool._gate_r2_preserve("nonexistent-agent"))


class TestR3TransferWasRemoved(_SandboxedCloseToolTest):
    """T-3 RETIRED 2026-08-04 in the lifecycle cutover (metis-g101, Mike-approved).

    R-3 read the transfer section of `agent-memory.md` and refused a close whose
    letter was unsealed or did not name the successor. It was correct about what
    it checked. It was also the constraint that welded the transfer's new home to
    the old close path: while it existed, moving the letter would have bricked
    every executive retirement.

    It is not replaced by a weaker check; it is replaced by a STRUCTURAL one.
    `tropo-retire.py` cannot complete without writing the letter, because writing
    the letter IS the state flip. R-3 verified after the fact a property the
    mechanism now makes impossible to violate — and this gate is the shape that
    cost G98 and T37 their clean closes, both discovering at their final step
    that they could not close.

    The three deleted tests asserted `_gate_r3_transfer` returned/withheld a
    refusal. There is no function to call. What replaces them is the assertion
    that it stayed gone, so a later generation cannot quietly reintroduce the
    weld while the letter lives somewhere else.
    """

    def test_the_r3_gate_is_gone(self):
        self.assertFalse(
            hasattr(closetool, "_gate_r3_transfer"),
            "_gate_r3_transfer is back. If the transfer gate is genuinely needed "
            "again, it must read the per-generation letter at "
            "agents/<slug>/transfers/<GEN>.md — never the memory surface section, "
            "which is a bridge that retires once every Tier-3 contract moves.",
        )

    def test_the_remaining_substance_gates_are_intact(self):
        """Removing one gate must not quietly remove its neighbours."""
        for gate in ("_gate_r1_signal", "_gate_r2_preserve", "_gate_r4_update"):
            self.assertTrue(hasattr(closetool, gate), f"{gate} disappeared")


class TestR4Update(_SandboxedCloseToolTest):
    """T-4: R-4 must read a live event-log drain + the crew brief's real freshness, not a
    claimed 'Threads Clear' milestone. subprocess.run is mocked (the drain itself is
    tropo-check-events.py's own well-tested job, not this gate's); the crew-brief
    freshness check stays fully real against the sandbox."""

    def _mock_drain(self, unanswered):
        return patch.object(
            closetool.subprocess, "run",
            return_value=types.SimpleNamespace(
                stdout=json.dumps({"unanswered_reply_required": unanswered}), returncode=0),
        )

    def test_dangling_threads_refuse(self):
        (self.tmp / "vault" / "tools").mkdir(parents=True, exist_ok=True)
        (self.tmp / "vault" / "tools" / "tropo-check-events.py").write_text("# stub\n")
        with self._mock_drain([{"id": "00001111"}]):
            result = closetool._gate_r4_update("scratchgen")
        self.assertIsNotNone(result, "a real dangling reply_required must refuse")

    def test_zero_threads_and_fresh_brief_pass(self):
        (self.tmp / "vault" / "tools").mkdir(parents=True, exist_ok=True)
        (self.tmp / "vault" / "tools" / "tropo-check-events.py").write_text("# stub\n")
        self._write(self.tmp / "00-crew-brief.md", f"updated {closetool.TODAY}\n")
        with self._mock_drain([]):
            result = closetool._gate_r4_update("scratchgen")
        self.assertIsNone(result)

    def test_zero_threads_but_stale_brief_refuses(self):
        (self.tmp / "vault" / "tools").mkdir(parents=True, exist_ok=True)
        (self.tmp / "vault" / "tools" / "tropo-check-events.py").write_text("# stub\n")
        self._write(self.tmp / "00-crew-brief.md", "updated 2020-01-01\n")
        with self._mock_drain([]):
            result = closetool._gate_r4_update("scratchgen")
        self.assertIsNotNone(result, "a crew brief never re-rendered today must refuse")


class TestT5FullReplay(_SandboxedCloseToolTest):
    """T-5: THE ACCEPTANCE. Reconstruct A129's exact move via _check_retirement_invariants
    (the composed function op_close actually calls) — invented milestones, no real work —
    and prove it refuses naming every missing item. Then do the real work and prove it
    passes. Both directions, same fixture family, same entry point op_close uses."""

    def _fm(self, slug="scratchgen", generation="X1", agent_class="executive"):
        return {"agent": slug, "generation": generation, "agent_class": agent_class}

    def test_a129_exact_fake_is_refused_naming_every_gap(self):
        # Replay: run folder + run.jsonl exist with INVENTED milestone events (A129's
        # actual move) — but NONE of the real work behind them happened.
        run_folder = self.tmp / "playbook-runs" / "agent-retire-scratchgen-x1-2026-07-12"
        run_folder.mkdir(parents=True)
        (run_folder / "run.jsonl").write_text(
            json.dumps({"event": "milestone_fired", "milestone": "Signal Secured",
                        "group": "Group 0", "timestamp": closetool.TODAY}) + "\n"
            + json.dumps({"event": "milestone_fired", "milestone": "Transfer Written",
                          "group": "Group 2", "timestamp": closetool.TODAY}) + "\n"
        )
        # Identity file never touched — still 'active', not 'retiring'.
        self._seed_identity("scratchgen", "aaaaaaaa", status="active")
        # No memory fold ran — stale last_curated.
        self._seed_memory("scratchgen", last_curated="2020-01-01", top_of_mind_count=3,
                           transfer_status="draft", transfer_names_successor=None)
        # No reflection authored.
        args = _args(retirement_run_folder=str(run_folder.relative_to(self.tmp)))

        with patch.object(closetool.subprocess, "run", side_effect=Exception("no drain in fake path")):
            failures = closetool._check_retirement_invariants(self._fm(), args)

        self.assertTrue(failures, "the invented-milestone fake must be refused")
        joined = "\n".join(failures)
        self.assertIn("R-1", joined, "must name the missing RETIRING signal")
        self.assertIn("R-2", joined, "must name the missing memory fold")
        self.assertIn("REFLECT", joined, "must name the missing reflection")
        # R-3 was removed 2026-08-04 in the lifecycle cutover, so it is no longer
        # among the gaps this replay can name. The test's actual subject is
        # unchanged and is the reason it exists: A129 fired a milestone event for
        # every claim and did none of the work. That fake is still refused, and
        # still refused BY SUBSTANCE, on every gate that remains.
        self.assertNotIn(
            "R-3", joined,
            "R-3 is retired — writing the letter is now the state flip in "
            "tropo-retire.py, not a gate checked afterwards. If it is back, the "
            "cutover has been partially reverted.",
        )
        # The critical proof: a milestone_fired event exists for every claim, and it
        # satisfies NONE of the gates — presence is not substance.
        for gate_name in ("R-1", "R-2"):
            self.assertTrue(any(gate_name in f for f in failures),
                             f"{gate_name} must fire despite the matching milestone_fired "
                             f"event existing in run.jsonl")

    def test_real_work_passes_every_gate(self):
        run_folder = self.tmp / "playbook-runs" / "agent-retire-scratchgen-x1-2026-07-12"
        run_folder.mkdir(parents=True)
        (run_folder / "run.jsonl").write_text("{}\n")
        # The real work, in order: identity actually transitioned to RETIRING.
        self._seed_identity("scratchgen", "aaaaaaaa", status="retiring")
        # A real fold ran this session, within bound, transfer sealed and named.
        self._seed_memory("scratchgen", last_curated=closetool.TODAY, top_of_mind_count=8,
                           transfer_status="FINAL/RETIRING", transfer_names_successor="X2")
        # A real reflection with File Manifest.
        self._write(
            self.tmp / "agents" / "scratchgen" / "reflections" / "x1-reflection.md",
            "# Reflection\n\n## File Manifest\n\n- created foo.md\n",
        )
        # Threads clear, crew brief fresh.
        (self.tmp / "vault" / "tools").mkdir(parents=True, exist_ok=True)
        (self.tmp / "vault" / "tools" / "tropo-check-events.py").write_text("# stub\n")
        self._write(self.tmp / "00-crew-brief.md", f"updated {closetool.TODAY}\n")
        args = _args(retirement_run_folder=str(run_folder.relative_to(self.tmp)),
                     reflection_path="agents/scratchgen/reflections/x1-reflection.md")

        with patch.object(closetool.subprocess, "run",
                           return_value=types.SimpleNamespace(
                               stdout=json.dumps({"unanswered_reply_required": []}),
                               returncode=0)):
            failures = closetool._check_retirement_invariants(self._fm(), args)

        self.assertEqual(failures, [], f"real work must pass every gate; got: {failures}")


class TestStruct1CaseSlugFix(_SandboxedCloseToolTest):
    """T-6 (Talos T29, Argus A130 GO 2026-07-13): STRUCT-1's default run-folder
    path must use the RAW-CASE generation string (e.g. "T28"), matching every
    real run folder on disk -- never the lowercased gen_slug used elsewhere in
    this file for reflection paths. Found while verify-then-fixing an Argus
    finding that turned out to be a false alarm on his own instrument (a
    tail-windowed ls pipeline); this case-slug mismatch was the real, smaller,
    separate bug underneath it. A gen_slug default would silently mask on
    case-insensitive filesystems (macOS/APFS, this dev machine) but false-
    REFUSE a genuine, correctly-created retirement on a case-sensitive one
    (Linux) -- the opposite direction from a fakeable gate, but still a real
    portability bug in the gate meant to be un-fakeable."""

    def test_default_path_preserves_source_case(self):
        # Pure string-level assertion -- deterministic regardless of the host
        # filesystem's case-(in)sensitivity, unlike an is_dir() check.
        path = closetool._default_retirement_run_folder("talos", "T28")
        self.assertIn("agent-retire-talos-T28-", path,
                      "default run-folder path must preserve the source-case generation")
        self.assertNotIn("agent-retire-talos-t28-", path,
                          "must NOT lowercase the generation -- that was the bug")

    def test_mixed_case_generation_preserved(self):
        # Not just upper/lower -- whatever case the caller's generation string
        # actually carries should pass through untouched (data, not normalized).
        path = closetool._default_retirement_run_folder("scratchgen", "gEn7")
        self.assertIn("agent-retire-scratchgen-gEn7-", path)

    def test_real_work_with_raw_case_default_folder_passes(self):
        """Integration proof: a genuine retirement, folder created under the
        REAL raw-case convention, with NO --retirement-run-folder override --
        the gate must resolve it via the (fixed) default computation."""
        expected_default = closetool._default_retirement_run_folder("scratchgen", "X1")
        run_folder = self.tmp / expected_default
        run_folder.mkdir(parents=True)
        (run_folder / "run.jsonl").write_text("{}\n")
        self._seed_identity("scratchgen", "aaaaaaaa", status="retiring")
        self._seed_memory("scratchgen", last_curated=closetool.TODAY, top_of_mind_count=8,
                           transfer_status="FINAL/RETIRING", transfer_names_successor="X2")
        self._write(
            self.tmp / "agents" / "scratchgen" / "reflections" / "x1-reflection.md",
            "# Reflection\n\n## File Manifest\n\n- created foo.md\n",
        )
        (self.tmp / "vault" / "tools").mkdir(parents=True, exist_ok=True)
        (self.tmp / "vault" / "tools" / "tropo-check-events.py").write_text("# stub\n")
        self._write(self.tmp / "00-crew-brief.md", f"updated {closetool.TODAY}\n")
        # Deliberately NOT passing retirement_run_folder -- exercising the default path.
        args = _args(reflection_path="agents/scratchgen/reflections/x1-reflection.md")

        with patch.object(closetool.subprocess, "run",
                           return_value=types.SimpleNamespace(
                               stdout=json.dumps({"unanswered_reply_required": []}),
                               returncode=0)):
            failures = closetool._check_retirement_invariants(
                {"agent": "scratchgen", "generation": "X1", "agent_class": "executive"}, args)

        self.assertEqual(failures, [], f"real work under the raw-case default folder must "
                                        f"pass every gate; got: {failures}")


if __name__ == "__main__":
    unittest.main()
