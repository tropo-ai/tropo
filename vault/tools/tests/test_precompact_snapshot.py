#!/usr/bin/env python3
"""precompact-snapshot (f0157a0d3671) — f015fcaf29b9 item 5.

Reuses ContinueFixture from test_compact_continue.py rather than building a
second scratch-studio constructor: this tool is the same-family sibling of
compact-continue and needs the identical shape (lineage, activation pointer,
unified entry, agent-memory.md) to resolve identity through the real
production functions it imports, not a re-derived stand-in.

The one property every other test here exists to protect: this tool must
never call `git fetch`. It is fired from a synchronous PreCompact hook, and
per the Claude Code hooks contract only exit code 2 blocks compaction — but
a hang inside a hook still burns its timeout budget for zero benefit, since
remote truth is safely recoverable at the next boot regardless. That is a
runtime property, not a docstring claim, so it is tested by patching the
tool's own subprocess wrapper and inspecting every call it made.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
TOOL = TOOLS / "tropo-precompact-snapshot.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PCS = _load("tropo_precompact_snapshot_under_test", TOOL)
CC_FIXTURES = _load("cc_fixture_for_precompact", TOOLS / "tests" / "test_compact_continue.py")

ContinueFixture = CC_FIXTURES.ContinueFixture
SLUG = CC_FIXTURES.SLUG
GEN = CC_FIXTURES.GEN


class SnapshotFixtureCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = ContinueFixture()
        self.addCleanup(self.fx.close)

    def snapshot_path(self) -> Path:
        return (self.fx.root / "agents" / SLUG / ".tropo-capsule"
                / "workspace" / "precompact-snapshot.json")

    def run_snapshot(self, *extra: str) -> tuple:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = PCS.main(["--agent", SLUG, "--studio", str(self.fx.root), *extra])
        return rc, buf.getvalue()


class TheSnapshotWritesTheExpectedShape(SnapshotFixtureCase):
    def test_a_valid_snapshot_lands_at_the_workspace_path(self) -> None:
        rc, _ = self.run_snapshot("--trigger", "auto")
        self.assertEqual(rc, 0)
        target = self.snapshot_path()
        self.assertTrue(target.is_file())
        body = json.loads(target.read_text(encoding="utf-8"))
        for key in ("written_by", "written_at", "agent", "generation", "trigger",
                    "identity", "git", "recent_commits", "open_reply_required",
                    "pipeline_work", "origin_watch"):
            self.assertIn(key, body, "missing top-level key %r" % key)
        self.assertEqual(body["agent"], SLUG)
        self.assertEqual(body["trigger"], "auto")

    def test_trigger_is_recorded_verbatim_not_interpreted(self) -> None:
        self.run_snapshot("--trigger", "manual")
        body = json.loads(self.snapshot_path().read_text(encoding="utf-8"))
        self.assertEqual(body["trigger"], "manual")

    def test_default_trigger_is_unknown_not_a_guess(self) -> None:
        self.run_snapshot()
        body = json.loads(self.snapshot_path().read_text(encoding="utf-8"))
        self.assertEqual(body["trigger"], "unknown")

    def test_no_tmp_staging_file_survives_a_normal_write(self) -> None:
        self.run_snapshot()
        workspace = self.snapshot_path().parent
        leftovers = list(workspace.glob(".*.tmp"))
        self.assertEqual(leftovers, [], "atomic write left a staging file behind: %r" % leftovers)


class TheToolNeverTouchesTheNetwork(SnapshotFixtureCase):
    """The core safety property. Patches the tool's own subprocess wrapper —
    not the stdlib's — so a call reaches this probe only if the tool's OWN
    code path issues it, proving the property about THIS tool rather than
    about subprocess in general."""

    def test_git_fetch_is_never_invoked(self) -> None:
        calls: list[list[str]] = []
        real_run = PCS._run

        def spy(args, cwd, timeout=15):
            calls.append(list(args))
            return real_run(args, cwd, timeout=timeout)

        with patch.object(PCS, "_run", side_effect=spy):
            rc, _ = self.run_snapshot("--trigger", "auto")
        self.assertEqual(rc, 0)
        self.assertTrue(calls, "no subprocess calls observed — the spy is not wired")
        fetches = [c for c in calls if len(c) >= 2 and c[0] == "git" and c[1] == "fetch"]
        self.assertEqual(
            fetches, [],
            "git fetch was called from inside a tool that must return fast from "
            "a synchronous hook: %r" % (fetches,))

    def test_the_git_section_says_it_did_not_fetch(self) -> None:
        self.run_snapshot()
        body = json.loads(self.snapshot_path().read_text(encoding="utf-8"))
        self.assertFalse(body["git"]["fetched"])


class ThePhantomAgentGuard(SnapshotFixtureCase):
    def test_an_unresolvable_agent_creates_no_new_agent_folder(self) -> None:
        ghost = self.fx.root / "agents" / "ghost-agent-xyz"
        self.assertFalse(ghost.exists())
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), patch("sys.stderr", err_buf):
            rc2 = PCS.main(["--agent", "ghost-agent-xyz", "--studio", str(self.fx.root)])
        self.assertEqual(rc2, 0, "must still exit 0 -- never the reason a hook blocks")
        self.assertFalse(
            ghost.exists(),
            "a mistyped/unresolvable --agent must never mint a new agents/<slug>/ folder")
        self.assertIn("degraded", err_buf.getvalue())


class AgentSlugDefaultsToResidentFlag(SnapshotFixtureCase):
    """The real PreCompact hook command is written once in .claude/settings.json
    and fires unattended -- it cannot know ahead of time which agent slug is
    resident in this clone (that changes across births/retirements). It must
    resolve from .tropo/flags/resident.json, the same marker the boot topology
    already maintains for exactly this (WAKE-DISCIPLINE v1.2.0 one-agent-one-
    clone). The bare fixture never creates this file, so its absence is the
    default case, not something a test has to construct."""

    def _write_resident(self, agent: str) -> None:
        flags_dir = self.fx.root / ".tropo" / "flags"
        flags_dir.mkdir(parents=True, exist_ok=True)
        (flags_dir / "resident.json").write_text(
            json.dumps({"agent": agent, "generation": GEN}), encoding="utf-8")

    def test_omitting_agent_resolves_from_resident_json(self) -> None:
        self._write_resident(SLUG)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = PCS.main(["--studio", str(self.fx.root), "--trigger", "manual"])
        self.assertEqual(rc, 0)
        body = json.loads(self.snapshot_path().read_text(encoding="utf-8"))
        self.assertEqual(body["agent"], SLUG)

    def test_explicit_agent_flag_wins_over_resident_json(self) -> None:
        self._write_resident("someone-else")
        rc, _ = self.run_snapshot("--trigger", "manual")  # helper passes --agent SLUG
        self.assertEqual(rc, 0)
        body = json.loads(self.snapshot_path().read_text(encoding="utf-8"))
        self.assertEqual(body["agent"], SLUG)

    def test_no_agent_and_no_resident_json_degrades_not_crashes(self) -> None:
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), patch("sys.stderr", err_buf):
            rc = PCS.main(["--studio", str(self.fx.root)])
        self.assertEqual(rc, 0)
        self.assertIn("degraded", err_buf.getvalue())
        self.assertFalse(self.snapshot_path().is_file())


class StdinHookPayloadIsReadSafely(unittest.TestCase):
    """The real hook pipes {session_id, transcript_path, cwd, hook_event_name,
    trigger, custom_instructions} on stdin and closes it immediately. Proven
    with a REAL os.pipe(), not a StringIO stand-in -- StringIO has no fileno()
    for select() to watch, so a mock here would pass regardless of whether the
    function under test actually works (t23: a self-consistent fixture proves
    nothing)."""

    def _closed_pipe_stdin(self, text: str):
        r_fd, w_fd = os.pipe()
        with os.fdopen(w_fd, "w") as w:
            w.write(text)
        stdin = os.fdopen(r_fd, "r")
        self.addCleanup(stdin.close)
        return stdin

    def test_a_real_closed_pipe_with_valid_json_is_parsed(self) -> None:
        stdin = self._closed_pipe_stdin(
            json.dumps({"trigger": "auto", "session_id": "abc"}))
        with patch("sys.stdin", stdin):
            result = PCS._read_stdin_hook_payload()
        self.assertEqual(result.get("trigger"), "auto")

    def test_a_tty_stdin_is_never_read(self) -> None:
        class _TTY:
            def isatty(self) -> bool:
                return True

            def read(self) -> str:
                raise AssertionError("must not read a tty stdin")

        with patch("sys.stdin", _TTY()):
            result = PCS._read_stdin_hook_payload()
        self.assertEqual(result, {})

    def test_garbage_on_stdin_degrades_to_empty_not_a_crash(self) -> None:
        stdin = self._closed_pipe_stdin("not json at all {{{")
        with patch("sys.stdin", stdin):
            result = PCS._read_stdin_hook_payload()
        self.assertEqual(result, {})

    def test_an_empty_but_closed_pipe_degrades_to_empty(self) -> None:
        stdin = self._closed_pipe_stdin("")
        with patch("sys.stdin", stdin):
            result = PCS._read_stdin_hook_payload()
        self.assertEqual(result, {})

    def test_an_open_but_silent_pipe_returns_fast_not_hangs(self) -> None:
        """The actual hang-prevention property, proven on a real pipe that
        is genuinely open with nothing written -- a manual/test invocation
        can leave stdin exactly like this. Bounded by select() inside the
        function; must return in well under the hook's own timeout budget."""
        r_fd, w_fd = os.pipe()
        self.addCleanup(os.close, w_fd)
        stdin = os.fdopen(r_fd, "r")
        self.addCleanup(stdin.close)
        start = time.monotonic()
        with patch("sys.stdin", stdin):
            result = PCS._read_stdin_hook_payload()
        elapsed = time.monotonic() - start
        self.assertEqual(result, {})
        self.assertLess(elapsed, 2.0,
                         "must not hang waiting for stdin that never arrives")


class MainReadsTriggerFromHookStdinEndToEnd(SnapshotFixtureCase):
    """Ties _read_stdin_hook_payload's result all the way through to the
    written snapshot file, over a real pipe -- not just each piece tested
    in isolation."""

    def _closed_pipe_with(self, payload: dict):
        r_fd, w_fd = os.pipe()
        with os.fdopen(w_fd, "w") as w:
            w.write(json.dumps(payload))
        stdin = os.fdopen(r_fd, "r")
        self.addCleanup(stdin.close)
        return stdin

    def test_stdin_trigger_reaches_the_written_snapshot(self) -> None:
        stdin = self._closed_pipe_with(
            {"trigger": "auto", "session_id": "s1", "hook_event_name": "PreCompact"})
        buf = io.StringIO()
        with redirect_stdout(buf), patch("sys.stdin", stdin):
            rc = PCS.main(["--agent", SLUG, "--studio", str(self.fx.root)])
        self.assertEqual(rc, 0)
        body = json.loads(self.snapshot_path().read_text(encoding="utf-8"))
        self.assertEqual(body["trigger"], "auto")

    def test_explicit_trigger_flag_wins_over_stdin(self) -> None:
        stdin = self._closed_pipe_with({"trigger": "auto"})
        buf = io.StringIO()
        with redirect_stdout(buf), patch("sys.stdin", stdin):
            rc = PCS.main(["--agent", SLUG, "--studio", str(self.fx.root),
                            "--trigger", "manual"])
        self.assertEqual(rc, 0)
        body = json.loads(self.snapshot_path().read_text(encoding="utf-8"))
        self.assertEqual(body["trigger"], "manual")


class OpenReplyRequiredDegradesInsteadOfCrashing(unittest.TestCase):
    """Direct function-level test: identity resolution failing must not take
    the whole snapshot down with it."""

    def test_a_resolve_identity_system_exit_is_caught_and_recorded(self) -> None:
        class _ExplodingCheckEvents:
            @staticmethod
            def resolve_identity(_slug):
                raise SystemExit(1)

        result = PCS.open_reply_required(Path("/nonexistent"), "whoever",
                                          _ExplodingCheckEvents())
        self.assertFalse(result["resolved"])
        self.assertEqual(result["count"], 0)
        self.assertIn("note", result)

    def test_a_missing_check_events_module_degrades_cleanly(self) -> None:
        result = PCS.open_reply_required(Path("/nonexistent"), "whoever", None)
        self.assertFalse(result["resolved"])
        self.assertIn("not found", result["note"])


class PipelineWorkFindsTheRightRun(unittest.TestCase):
    """Synthetic pipeline-runs fixture: two run folders, only one names this
    agent as a recent actor. The scan must find that one specifically, not
    just the most-recently-modified folder regardless of actor."""

    def setUp(self) -> None:
        import shutil
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="precompact-pipeline-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        runs = self.tmp / "vault" / "pipeline-runs"
        runs.mkdir(parents=True)

        other = runs / "release-pipeline-other-2026-09-01"
        other.mkdir()
        (other / "run.jsonl").write_text(
            json.dumps({"event": "step_completed", "actor": "someone-else",
                        "ts": "2026-09-01T10:00:00Z"}) + "\n", encoding="utf-8")

        self.mine = runs / "release-pipeline-mine-2026-09-05"
        self.mine.mkdir()
        (self.mine / "run.jsonl").write_text(
            "\n".join(json.dumps(row) for row in [
                {"event": "step_started", "actor": "someone-else",
                 "ts": "2026-09-05T09:00:00Z"},
                {"event": "step_completed", "actor": "talos-t64",
                 "ts": "2026-09-05T09:05:00Z"},
            ]) + "\n", encoding="utf-8")
        (self.mine / "run.state.json").write_text(
            json.dumps({"current_step": "step-b", "eligible_steps": ["step-c"],
                        "run_status": "active"}), encoding="utf-8")

    def test_finds_the_run_naming_this_agents_slug_generation_as_actor(self) -> None:
        result = PCS.current_pipeline_work(self.tmp, "talos", "T64")
        self.assertTrue(result["resolved"])
        self.assertEqual(result["run_folder"],
                          str(self.mine.relative_to(self.tmp)))
        self.assertEqual(result["current_step"], "step-b")
        self.assertEqual(result["eligible_steps"], ["step-c"])

    def test_a_slug_matching_no_actor_resolves_to_nothing(self) -> None:
        result = PCS.current_pipeline_work(self.tmp, "nobody", "N1")
        self.assertFalse(result["resolved"])


class MainAlwaysExitsZero(unittest.TestCase):
    """The tool's own stated contract: whatever goes wrong internally, main()
    must never be the reason a PreCompact hook sees a blocking exit code."""

    def test_an_internal_exception_in_build_snapshot_still_exits_zero(self) -> None:
        with patch.object(PCS, "build_snapshot", side_effect=RuntimeError("boom")):
            buf = io.StringIO()
            with redirect_stdout(io.StringIO()), \
                 patch("sys.stderr", buf):
                rc = PCS.main(["--agent", "talos", "--studio", str(ROOT)])
        self.assertEqual(rc, 0)
        self.assertIn("degraded", buf.getvalue())

    def test_a_systemexit_from_studio_root_resolution_still_exits_zero(self) -> None:
        """resolve_studio_root raises a bare SystemExit (not Exception) when
        --studio names a real directory with no agents/ -- this tool's own
        contract is stricter than that shared helper's other callers, so it
        must degrade here rather than let a SystemExit escape main() with a
        non-zero process exit."""
        with tempfile.TemporaryDirectory() as not_a_studio:
            out_buf, err_buf = io.StringIO(), io.StringIO()
            with redirect_stdout(out_buf), patch("sys.stderr", err_buf):
                rc = PCS.main(["--agent", "talos", "--studio", not_a_studio])
        self.assertEqual(rc, 0)
        self.assertIn("degraded", err_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
