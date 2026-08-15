#!/usr/bin/env python3
"""Compact-Continue Phase 1 — production-path contract (d5f8fe55 / 408c158c).

Every case runs the real tool against a TempStudio with a scratch Git remote and
an isolated event tree. Nothing here drains a real agent, mutates production
lineage, emits to the production event union, or touches the live worktree.

The contract this file defends, in one line the fixtures all restate:

    Continue means this same agent session keeps going. Nothing is born,
    retired, or added to permanent lineage.

Each named weld carries a mutation that changes the verdict when removed, per
the paired test contract; source-text checks never stand alone where the
production entry point can be executed instead.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
TOOL = TOOLS / "tropo-compact-continue.py"

SPEC = importlib.util.spec_from_file_location("tropo_compact_continue", TOOL)
CC = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = CC
SPEC.loader.exec_module(CC)

SLUG = "talos"
GEN = "T41"


def git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )


def tree_fingerprint(root: Path, *, skip: tuple = ()) -> dict:
    """Hash every file under root except declared operational outputs."""
    out = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".git/") or any(rel.startswith(s) for s in skip):
            continue
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


class ContinueFixture:
    """A TempStudio carrying the real tools, a live lineage, and a Git remote."""

    TOOL_SET = (
        "tropo-compact-continue.py",
        "tropo-lineage.py",
        "tropo-check-events.py",
        "tropo-emit-event.py",
    )

    def __init__(self, *, gen: str = GEN, retired: bool = False,
                 with_run: bool = True, run_complete: bool = True):
        self.tmp = Path(tempfile.mkdtemp(prefix="compact-continue-")).resolve()
        self.root = self.tmp / "studio"
        self.remote = self.tmp / "remote.git"
        self.gen = gen
        (self.root / "vault" / "tools" / "lib").mkdir(parents=True)
        (self.root / "vault" / "events" / "streams").mkdir(parents=True)
        (self.root / "vault" / "events" / "receipts").mkdir(parents=True)
        (self.root / "vault" / "agents").mkdir(parents=True)
        (self.root / "agents" / SLUG).mkdir(parents=True)
        (self.root / ".tropo-studio" / "registries").mkdir(parents=True)
        (self.root / "playbook-runs").mkdir(parents=True)

        for name in self.TOOL_SET:
            shutil.copy2(TOOLS / name, self.root / "vault" / "tools" / name)
        if (TOOLS / "lib").is_dir():
            shutil.copytree(
                TOOLS / "lib", self.root / "vault" / "tools" / "lib", dirs_exist_ok=True
            )

        self.write_lineage(gen=gen, retired=retired)
        if with_run:
            self.write_activation_run(gen=gen, complete=run_complete)
        self.write_registry()
        (self.root / "vault" / "events" / "00-events.jsonl").write_text(
            "", encoding="utf-8"
        )
        self.init_git()

    # -- fixture parts -------------------------------------------------- #
    def write_lineage(self, *, gen: str, retired: bool) -> None:
        rows = [
            {
                "t": "born",
                "gen": gen,
                "at": "2026-08-12T09:44:02Z",
                "by": "mike",
                "model": "fixture",
            }
        ]
        if retired:
            rows.append(
                {"t": "retired", "gen": gen, "at": "2026-08-12T10:00:00Z", "by": "mike"}
            )
        (self.root / "agents" / SLUG / "lineage.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
        )

    def write_activation_run(self, *, gen: str, complete: bool = True,
                             suffix: str = "2026-08-12", run_uid: str = "run-aaaa") -> Path:
        folder = self.root / "playbook-runs" / f"agent-activation-{SLUG}-{gen}-{suffix}"
        folder.mkdir(parents=True, exist_ok=True)
        rows = [
            {"event": "run_started", "run_uid": run_uid, "agent": SLUG, "gen": gen},
            {"event": "milestone_fired", "milestone": "Operationally Grounded"},
        ]
        if complete:
            rows.append(
                {
                    "event": "milestone_fired",
                    "milestone": "Talos Active",
                    "run_uid": run_uid,
                    "run_status": "complete",
                }
            )
        (folder / "run.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
        )
        return folder

    def write_registry(self) -> None:
        (self.root / ".tropo-studio" / "registries" / "agent-registry.yaml").write_text(
            "agents:\n"
            f"  - name: {SLUG}\n"
            "    party_uid: 34cf0f1c\n"
            "    agent_uid: 123e12e7\n",
            encoding="utf-8",
        )
        (self.root / "vault" / "agents").mkdir(parents=True, exist_ok=True)
        (self.root / "vault" / "agents" / "3031ffa3.md").write_text(
            "---\nuid: 3031ffa3\ntype: agent\nagent: talos\nparty_uid: 34cf0f1c\n"
            "agent_root_uid: 123e12e7\n---\n\n# talos\n",
            encoding="utf-8",
        )

    def init_git(self) -> None:
        git(["init", "--bare", "-b", "main", str(self.remote)], self.tmp)
        git(["init", "-b", "main"], self.root)
        git(["config", "user.email", "fixture@example.com"], self.root)
        git(["config", "user.name", "fixture"], self.root)
        git(["remote", "add", "origin", str(self.remote)], self.root)
        git(["add", "-A"], self.root)
        git(["commit", "-m", "fixture base"], self.root)
        git(["push", "-u", "origin", "main"], self.root)

    def commit(self, subject: str) -> None:
        marker = self.root / "work.txt"
        marker.write_text(subject + "\n", encoding="utf-8")
        git(["add", "work.txt"], self.root)
        git(["commit", "-m", subject], self.root)

    def break_remote(self) -> None:
        shutil.rmtree(self.remote, ignore_errors=True)

    # -- invocation ------------------------------------------------------ #
    def run_tool(self, *extra: str, agent: str = SLUG) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(self.root / "vault" / "tools" / "tropo-compact-continue.py"),
                "--agent",
                agent,
                "--json",
                *extra,
            ],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=False,
        )

    def packet(self, *extra: str, agent: str = SLUG) -> dict:
        proc = self.run_tool(*extra, agent=agent)
        try:
            return json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:  # pragma: no cover - diagnostic path
            raise AssertionError(
                f"tool stdout was not JSON (rc={proc.returncode}):\n"
                f"{proc.stdout}\n{proc.stderr}"
            )

    def lineage_bytes(self) -> bytes:
        return (self.root / "agents" / SLUG / "lineage.jsonl").read_bytes()

    def events(self) -> list:
        out = []
        for path in sorted((self.root / "vault" / "events").rglob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return out

    def broadcasts(self) -> list:
        return [
            event
            for event in self.events()
            if event.get("type") == "tropo.broadcast.crew"
        ]

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


class ContinueCase(unittest.TestCase):
    def fixture(self, **kwargs) -> ContinueFixture:
        fx = ContinueFixture(**kwargs)
        self.addCleanup(fx.close)
        return fx


class IdentityAndSessionTests(ContinueCase):
    """AC1 — the live agent and generation survive; born is unreachable."""

    def test_continue_preserves_generation_and_writes_no_lineage(self):
        fx = self.fixture()
        before = fx.lineage_bytes()

        packet = fx.packet()

        self.assertIn(packet["status"], ("continued", "continued-degraded"))
        self.assertEqual(packet["agent"], SLUG)
        self.assertEqual(packet["generation"], GEN)
        self.assertTrue(packet["same_session"])
        self.assertTrue(packet["same_generation"])
        self.assertFalse(packet["lineage_written"])
        self.assertEqual(fx.lineage_bytes(), before, "lineage bytes changed")
        rows = [
            json.loads(line)
            for line in before.decode().splitlines()
            if line.strip()
        ]
        self.assertEqual(
            len([r for r in rows if r.get("t") == "born"]),
            1,
            "a second birth row exists — Continue minted a phantom generation",
        )

    def test_retired_generation_is_refused_without_mutation(self):
        fx = self.fixture(retired=True)
        before = tree_fingerprint(fx.root)

        proc = fx.run_tool()

        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout or "{}")
        self.assertEqual(payload["status"], "refused")
        self.assertIn("RETIRED", payload["reason"])
        self.assertEqual(tree_fingerprint(fx.root), before)

    def test_agent_with_no_live_generation_is_refused(self):
        fx = self.fixture()
        (fx.root / "agents" / SLUG / "lineage.jsonl").write_text("", encoding="utf-8")
        before = tree_fingerprint(fx.root)

        proc = fx.run_tool()

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["status"], "refused")
        self.assertEqual(tree_fingerprint(fx.root), before)

    def test_the_tool_has_no_path_to_born(self):
        """P0 mechanism check: not one call site, import, or string.

        Executable cases above prove lineage does not change on the paths they
        walk. This closes the remaining shape: a `born` call reachable from a
        branch no fixture happens to take.
        """
        source = TOOL.read_text(encoding="utf-8")
        code = source.split('"""', 2)[-1]
        self.assertNotIn('"born"', code)
        self.assertNotIn("'born'", code)
        self.assertNotIn("lineage.py born", code)
        self.assertNotIn("tropo-retire", code)
        # `who` is the only lineage subcommand the tool may invoke.
        self.assertIn('"who"', code)


class ActivationRunResolutionTests(ContinueCase):
    """AC2 — only the exact completed run for this agent/generation counts."""

    def test_completed_run_for_this_generation_is_selected(self):
        fx = self.fixture()
        packet = fx.packet()
        self.assertEqual(packet["activation_run"]["run_uid"], "run-aaaa")
        self.assertIn(f"{SLUG}-{GEN}", packet["activation_run"]["path"])

    def test_missing_run_refuses_and_never_births(self):
        fx = self.fixture(with_run=False)
        before = fx.lineage_bytes()

        proc = fx.run_tool()

        self.assertEqual(proc.returncode, 2)
        reason = json.loads(proc.stdout)["reason"]
        self.assertIn("no completed activation run", reason)
        self.assertEqual(fx.lineage_bytes(), before)

    def test_incomplete_run_is_not_a_current_session(self):
        fx = self.fixture(run_complete=False)
        proc = fx.run_tool()
        self.assertEqual(proc.returncode, 2)
        reason = json.loads(proc.stdout)["reason"]
        self.assertIn("no completed activation run", reason)
        self.assertIn("Incomplete run(s) present", reason)

    def test_wrong_generation_run_does_not_corroborate(self):
        fx = self.fixture(with_run=False)
        fx.write_activation_run(gen="T40", complete=True)
        proc = fx.run_tool()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no completed activation run", json.loads(proc.stdout)["reason"])

    def test_two_distinct_complete_runs_refuse_as_ambiguous(self):
        fx = self.fixture()
        fx.write_activation_run(
            gen=GEN, complete=True, suffix="2026-08-13", run_uid="run-bbbb"
        )
        proc = fx.run_tool()
        self.assertEqual(proc.returncode, 2)
        reason = json.loads(proc.stdout)["reason"]
        self.assertIn("ambiguous", reason)
        self.assertIn("run-aaaa", reason)
        self.assertIn("run-bbbb", reason)

    def test_same_run_uid_twice_resolves_rather_than_refusing(self):
        fx = self.fixture()
        fx.write_activation_run(
            gen=GEN, complete=True, suffix="2026-08-13", run_uid="run-aaaa"
        )
        packet = fx.packet()
        self.assertEqual(packet["activation_run"]["run_uid"], "run-aaaa")


class ReanchorPacketTests(ContinueCase):
    """AC3 — repository and event truth, reported without mutating anything."""

    def test_dirty_ahead_worktree_is_reported_and_left_alone(self):
        fx = self.fixture()
        fx.commit("talos-t41: local work")
        (fx.root / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
        before = tree_fingerprint(fx.root, skip=(".tropo-studio/", "vault/events/"))

        packet = fx.packet()

        self.assertEqual(packet["git"]["fetch_status"], "fetched")
        self.assertEqual(packet["git"]["branch"], "main")
        self.assertEqual(packet["git"]["ahead"], 1)
        self.assertEqual(packet["git"]["behind"], 0)
        self.assertIn("dirty.txt", packet["git"]["untracked"])
        self.assertEqual(
            tree_fingerprint(fx.root, skip=(".tropo-studio/", "vault/events/")),
            before,
            "the re-anchor changed the working tree",
        )

    def test_failed_fetch_degrades_to_local_only_not_false_clean(self):
        fx = self.fixture()
        fx.break_remote()

        packet = fx.packet()

        self.assertEqual(packet["git"]["fetch_status"], "failed-local-only")
        self.assertTrue(packet["git"]["fetch_error"])
        self.assertEqual(
            packet["events"]["state"],
            "local-only",
            "offline drain must not present remote debt as authoritative",
        )

    def test_fetch_precedes_drain(self):
        """Ordering is the contract, not an implementation detail.

        A drain that runs before fetch reports yesterday's event union as
        current. Proven by call order, not by reading the source.
        """
        fx = self.fixture()
        order = []
        real_git_state = CC.git_state
        real_drain = CC.drain_events

        def spy_git_state(root):
            order.append("fetch")
            return real_git_state(root)

        def spy_drain(root, slug, *, local_only):
            order.append("drain")
            return real_drain(root, slug, local_only=local_only)

        CC.git_state = spy_git_state
        CC.drain_events = spy_drain
        try:
            CC.continue_session(fx.root, SLUG)
        finally:
            CC.git_state = real_git_state
            CC.drain_events = real_drain

        self.assertEqual(order[:2], ["fetch", "drain"])

    def test_unanswered_reply_required_debts_are_counted_and_named(self):
        fx = self.fixture()
        stream = fx.root / "vault" / "events" / "streams" / "aaaa000000000001.jsonl"
        stream.write_text(
            json.dumps(
                {
                    "specversion": "1.0",
                    "type": "tropo.message.sent",
                    "source": "/agents/argus",
                    "time": "2026-08-12T10:00:00Z",
                    "source_uid": "cdf9b3ad",
                    "lifecycle": "evergreen",
                    "subject": "34cf0f1c",
                    "id": "evt_aaaa000000000001_00000001",
                    "event_uid": "evt_aaaa000000000001_00000001",
                    "data": {
                        "from": "argus-a148",
                        "to": "talos-t41",
                        "reply_required": True,
                        "headline": "a real debt",
                        "body": "answer me",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        packet = fx.packet()

        self.assertGreaterEqual(packet["events"]["unanswered_reply_required"], 1)
        headlines = [d["headline"] for d in packet["events"]["debts"]]
        self.assertIn("a real debt", headlines)


class RecentCommitSafetyTests(ContinueCase):
    """AC4 — commit subjects are data; uncertain authorship is labelled."""

    HOSTILE = "talos-t41: `touch /tmp/pwned-by-continue` and $(echo nope)"

    def test_hostile_subject_renders_intact_and_executes_nothing(self):
        fx = self.fixture()
        canary = Path(tempfile.gettempdir()) / "pwned-by-continue"
        if canary.exists():
            canary.unlink()
        fx.commit(self.HOSTILE)

        packet = fx.packet()

        subjects = [c["subject"] for c in packet["recent_commits"]]
        self.assertIn(self.HOSTILE, subjects, "the subject was not rendered verbatim")
        self.assertFalse(
            canary.exists(), "a commit subject reached a shell and executed"
        )

    def test_commits_from_this_generation_are_claimed(self):
        fx = self.fixture()
        fx.commit("talos-t41: mine")
        packet = fx.packet()
        mine = [c for c in packet["recent_commits"] if c["subject"] == "talos-t41: mine"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["ownership"], "self")

    def test_unowned_history_is_labelled_unresolved_rather_than_claimed(self):
        fx = self.fixture()
        fx.commit("someone-else: not mine")
        packet = fx.packet()
        self.assertTrue(packet["recent_commits"])
        self.assertTrue(
            all(c["ownership"] == "unresolved" for c in packet["recent_commits"]),
            "commits with no generation prefix were claimed as self-authored",
        )

    def test_every_subprocess_is_an_argument_array(self):
        """The mechanism behind the two runtime cases above."""
        source = TOOL.read_text(encoding="utf-8")
        code = source.split('"""', 2)[-1]
        self.assertNotIn("shell=True", code)
        self.assertNotIn("os.system", code)
        self.assertIn("shell=False", code)


class BroadcastAndRetryTests(ContinueCase):
    """AC5 — one continuation UID, at most one crew event, ever."""

    def test_one_continue_emits_exactly_one_broadcast(self):
        fx = self.fixture()
        packet = fx.packet()

        self.assertEqual(packet["broadcast"], "emitted")
        self.assertEqual(packet["status"], "continued")
        broadcasts = fx.broadcasts()
        self.assertEqual(len(broadcasts), 1)
        data = broadcasts[0]["data"]
        self.assertEqual(data["continuation_uid"], packet["continuation_uid"])
        self.assertEqual(data["t"], "continued")
        self.assertEqual(data["agent"], SLUG)
        self.assertEqual(data["gen"], GEN)
        self.assertFalse(
            CC.journal_path(fx.root, SLUG, GEN).exists(),
            "pending state survived a successful broadcast",
        )

    def test_emitter_failure_is_warn_safe_and_retry_emits_once(self):
        fx = self.fixture()
        emitter = fx.root / "vault" / "tools" / "tropo-emit-event.py"
        saved = emitter.read_bytes()
        emitter.write_text(
            "import sys\nsys.stderr.write('injected emitter failure\\n')\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )

        first = fx.packet()

        self.assertEqual(first["broadcast"], "pending")
        self.assertEqual(first["status"], "continued-degraded")
        self.assertEqual(fx.broadcasts(), [])
        pending = CC.journal_path(fx.root, SLUG, GEN)
        self.assertTrue(pending.is_file(), "degraded run kept no retry state")
        journal = json.loads(pending.read_text(encoding="utf-8"))
        self.assertEqual(journal["continuation_uid"], first["continuation_uid"])

        emitter.write_bytes(saved)
        second = fx.packet()

        self.assertEqual(
            second["continuation_uid"],
            first["continuation_uid"],
            "retry started a new continuation instead of resuming the pending one",
        )
        self.assertEqual(second["broadcast"], "emitted")
        self.assertEqual(len(fx.broadcasts()), 1)

    def test_crash_after_emit_never_duplicates(self):
        fx = self.fixture()
        first = fx.packet()
        self.assertEqual(len(fx.broadcasts()), 1)
        # Re-plant the pending record exactly as a crash between emit and
        # cleanup would leave it.
        CC.save_journal(
            fx.root,
            SLUG,
            GEN,
            {
                "continuation_uid": first["continuation_uid"],
                "agent": SLUG,
                "generation": GEN,
                "activation_run_uid": "run-aaaa",
                "started": "2026-08-12T00:00:00Z",
                "phases": ["git", "events"],
            },
        )

        second = fx.packet()

        self.assertEqual(second["continuation_uid"], first["continuation_uid"])
        self.assertEqual(second["broadcast"], "emitted")
        self.assertEqual(
            len(fx.broadcasts()), 1, "crash-after-emit retry duplicated the crew event"
        )

    def test_dedupe_requires_the_payload_field_not_a_lookalike(self):
        """Mutation guard: a headline or top-level field must not satisfy it."""
        fx = self.fixture()
        uid = "0" * 32
        stream = fx.root / "vault" / "events" / "streams" / "bbbb000000000001.jsonl"
        stream.write_text(
            json.dumps(
                {
                    "specversion": "1.0",
                    "type": "tropo.broadcast.crew",
                    "source": "/agents/talos",
                    "time": "2026-08-12T10:00:00Z",
                    "source_uid": "34cf0f1c",
                    "lifecycle": "ephemeral",
                    "id": "evt_bbbb000000000001_00000001",
                    "event_uid": "evt_bbbb000000000001_00000001",
                    "continuation_uid": uid,
                    "data": {"headline": f"continuation_uid {uid}"},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertFalse(
            CC.broadcast_exists(fx.root, uid),
            "a top-level lookalike field or headline substring satisfied dedupe",
        )


class PacketContractTests(ContinueCase):
    """AC6 — the packet says what it must, and only writes what it declares."""

    REQUIRED = {
        "status",
        "agent",
        "generation",
        "same_session",
        "same_generation",
        "continuation_uid",
        "activation_run",
        "git",
        "events",
        "recent_commits",
        "refresh",
        "broadcast",
        "lineage_written",
        "pointers",
    }

    def test_packet_schema_and_headline_fields(self):
        fx = self.fixture()
        packet = fx.packet()
        self.assertEqual(set(packet), self.REQUIRED)
        self.assertIn(packet["broadcast"], ("emitted", "pending"))
        self.assertRegex(packet["continuation_uid"], r"^[0-9a-f]{32}$")
        self.assertEqual(
            packet["pointers"]["retirement_playbook"], CC.RETIREMENT_PLAYBOOK
        )
        self.assertIn("check-events", packet["pointers"]["event_mechanics"])

    def test_human_report_states_same_session_and_generation(self):
        fx = self.fixture()
        proc = subprocess.run(
            [
                sys.executable,
                str(fx.root / "vault" / "tools" / "tropo-compact-continue.py"),
                "--agent",
                SLUG,
            ],
            cwd=str(fx.root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("same session, same generation", proc.stdout)
        self.assertIn("Lineage:       unchanged", proc.stdout)

    def test_only_declared_operational_surfaces_change(self):
        fx = self.fixture()
        before = tree_fingerprint(fx.root)

        fx.packet()

        after = tree_fingerprint(fx.root)
        changed = {
            path
            for path in set(before) | set(after)
            if before.get(path) != after.get(path)
        }
        for path in changed:
            self.assertTrue(
                path.startswith("vault/events/")
                or path.startswith(".tropo-studio/compact-continue/"),
                f"Continue wrote outside its declared surfaces: {path}",
            )


class NonGoalsAndIsolationTests(ContinueCase):
    """AC9 — no boot replay, milestone, memory, voice edit, or Git mutation."""

    def test_no_milestone_memory_or_voice_file_is_touched(self):
        fx = self.fixture()
        memory = fx.root / "agents" / SLUG / ".tropo-capsule" / "memory"
        memory.mkdir(parents=True)
        entry = memory / "entries.jsonl"
        entry.write_text('{"seed": true}\n', encoding="utf-8")
        voice = fx.root / "vault" / "agents" / "3031ffa3.md"
        run_file = next((fx.root / "playbook-runs").rglob("run.jsonl"))
        before = {
            "memory": entry.read_bytes(),
            "voice": voice.read_bytes(),
            "run": run_file.read_bytes(),
        }

        fx.packet()

        self.assertEqual(entry.read_bytes(), before["memory"])
        self.assertEqual(voice.read_bytes(), before["voice"])
        self.assertEqual(run_file.read_bytes(), before["run"], "an activation run was re-fired")

    def test_no_new_activation_run_folder_is_created(self):
        fx = self.fixture()
        before = sorted(p.name for p in (fx.root / "playbook-runs").iterdir())
        fx.packet()
        self.assertEqual(
            sorted(p.name for p in (fx.root / "playbook-runs").iterdir()), before
        )

    def test_head_and_dirty_work_survive(self):
        fx = self.fixture()
        fx.commit("talos-t41: precious")
        head = git(["rev-parse", "HEAD"], fx.root).stdout.strip()
        dirty = fx.root / "in-progress.txt"
        dirty.write_text("half-written\n", encoding="utf-8")

        fx.packet()

        self.assertEqual(git(["rev-parse", "HEAD"], fx.root).stdout.strip(), head)
        self.assertEqual(dirty.read_text(encoding="utf-8"), "half-written\n")

    def test_no_worktree_mutation_verb_exists_in_the_call_graph(self):
        source = TOOL.read_text(encoding="utf-8")
        code = source.split('"""', 2)[-1]
        for verb in ("pull", "merge", "rebase", "checkout", "reset", "clean", "push"):
            self.assertNotIn(
                f'"{verb}"',
                code,
                f"a Git {verb} appears in a tool that must only read",
            )
        self.assertIn('"fetch"', code)


class RefreshInterfaceTests(ContinueCase):
    """AC10 — Phase-2 seam only; absent and stale both mandate full reads."""

    def refresh_path(self, fx: ContinueFixture) -> Path:
        return fx.root / "agents" / SLUG / f"{SLUG}-compact-continue-activation.md"

    def test_absent_refresh_mandates_full_source_reads(self):
        fx = self.fixture()
        packet = fx.packet()
        self.assertEqual(packet["refresh"]["status"], "absent")
        self.assertIsNone(packet["refresh"]["path"])
        self.assertTrue(packet["pointers"]["refresh_full_reads"])

    def test_phase_1_never_authors_the_refresh_file(self):
        fx = self.fixture()
        fx.packet()
        self.assertFalse(
            self.refresh_path(fx).exists(),
            "Phase 1 authored a Phase-2 self-summary",
        )

    def test_stale_refresh_is_distinct_and_still_mandates_full_reads(self):
        fx = self.fixture()
        self.refresh_path(fx).write_text(
            "---\nstatus: active\n---\n\nsource: agents/talos/missing-source.md\n",
            encoding="utf-8",
        )
        packet = fx.packet()
        self.assertEqual(packet["refresh"]["status"], "stale")
        self.assertTrue(packet["pointers"]["refresh_full_reads"])

    def test_fresh_refresh_drops_the_full_read_mandate(self):
        fx = self.fixture()
        source_rel = "agents/talos/present-source.md"
        (fx.root / source_rel).write_text("body\n", encoding="utf-8")
        digest = hashlib.sha256(b"body\n").hexdigest()
        self.refresh_path(fx).write_text(
            f"---\nstatus: active\n---\n\nsource: {source_rel}\n"
            f"sources_fingerprint: {digest}\n",
            encoding="utf-8",
        )
        packet = fx.packet()
        self.assertEqual(packet["refresh"]["status"], "fresh")
        self.assertEqual(packet["pointers"]["refresh_full_reads"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
