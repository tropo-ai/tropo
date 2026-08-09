"""Two-clone + mixed-mode plants for Event Ledger distributed identity."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


event_identity = _load(
    "distributed_event_identity_test",
    TOOLS / "lib" / "event_identity.py",
)


def _legacy_event(event_id: str = "00000001") -> dict:
    return {
        "id": event_id,
        "specversion": "1.0",
        "type": "tropo.message.sent",
        "source": "/agents/argus",
        "time": "2026-07-15T00:00:00Z",
        "source_uid": "cdf9b3ad",
        "lifecycle": "evergreen",
        "subject": "cdf9b3ad",
        "data": {"body": "legacy"},
    }


def _prepare_clone(root: Path) -> None:
    (root / ".tropo").mkdir(parents=True)
    events = root / "vault" / "events"
    events.mkdir(parents=True)
    (events / "00-events.jsonl").write_text(
        json.dumps(_legacy_event(), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    files = root / "vault" / "files"
    files.mkdir()
    for uid in ("f15a9b85", "5a195c76", "de9ac53c"):
        (files / f"{uid}.md").write_text(f"---\nuid: {uid}\n---\n", encoding="utf-8")
    _write_cutover_marker(root)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_cutover_marker(root: Path) -> None:
    legacy = root / "vault" / "events" / "00-events.jsonl"
    files = root / "vault" / "files"
    legacy_rows = [
        line for line in legacy.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    marker = {
        "schema_id": event_identity.CUTOVER_SCHEMA_ID,
        "enabled": True,
        "enabled_at": "2026-07-18T00:00:00Z",
        "enabled_by": "fixture",
        "dev_spec_uid": "f15a9b85",
        "dev_spec_sha256": _sha256(files / "f15a9b85.md"),
        "test_spec_uid": "5a195c76",
        "test_spec_sha256": _sha256(files / "5a195c76.md"),
        "audit_uid": "de9ac53c",
        "audit_sha256": _sha256(files / "de9ac53c.md"),
        "legacy_epoch_path": "vault/events/00-events.jsonl",
        "legacy_epoch_sha256": _sha256(legacy),
        "legacy_physical_rows": len(legacy_rows),
        "legacy_unique_events": len(legacy_rows),
        "baseline_main_commit": "0" * 40,
    }
    (root / ".tropo" / "event-streams-v2.enabled").write_text(
        json.dumps(marker, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


class DistributedEventIdentityTests(unittest.TestCase):
    def test_two_clones_same_actor_same_local_seq_never_collide(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            origin, clone_a, clone_b, merged = (
                base / "origin",
                base / "a",
                base / "b",
                base / "merged",
            )
            _prepare_clone(origin)
            _git(origin, "init", "-b", "main")
            _git(origin, "config", "user.email", "fixture@tropo.local")
            _git(origin, "config", "user.name", "Fixture")
            _git(origin, "add", ".")
            _git(origin, "commit", "-m", "legacy epoch")
            for root in (clone_a, clone_b, merged):
                subprocess.run(
                    ["git", "clone", str(origin), str(root)],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            worker = r"""
import importlib.util, json, sys
from pathlib import Path
root, module_path, body = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
spec = importlib.util.spec_from_file_location("worker_event_identity", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
writer = module.derive_writer_instance_uid(
    root, "cdf9b3ad", activation_uid="197f05e1"
)
event = module.append_stream_event(
    root,
    writer,
    {
        "specversion": "1.0",
        "type": "tropo.message.sent",
        "source": "/agents/argus",
        "time": "2026-07-15T01:00:00Z",
        "source_uid": "cdf9b3ad",
        "lifecycle": "evergreen",
        "data": {"body": body},
    },
)
print(json.dumps(event))
"""
            module_path = TOOLS / "lib" / "event_identity.py"
            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        worker,
                        str(root),
                        str(module_path),
                        body,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for root, body in ((clone_a, "from a"), (clone_b, "from b"))
            ]
            outputs = [process.communicate(timeout=30) for process in processes]
            for process, (_, stderr) in zip(processes, outputs):
                self.assertEqual(process.returncode, 0, stderr)
            event_a, event_b = [json.loads(stdout) for stdout, _ in outputs]
            self.assertEqual(event_a["local_seq"], event_b["local_seq"])
            self.assertNotEqual(event_a["event_uid"], event_b["event_uid"])
            self.assertNotEqual(
                event_a["writer_instance_uid"],
                event_b["writer_instance_uid"],
            )
            for root, label in ((clone_a, "a"), (clone_b, "b")):
                _git(root, "config", "user.email", "fixture@tropo.local")
                _git(root, "config", "user.name", "Fixture")
                _git(root, "add", "vault/events/streams")
                _git(root, "commit", "-m", f"stream {label}")
            _git(merged, "config", "user.email", "fixture@tropo.local")
            _git(merged, "config", "user.name", "Fixture")
            _git(
                merged,
                "fetch",
                str(clone_a),
                "HEAD:refs/remotes/fixture/a",
            )
            _git(merged, "merge", "--ff-only", "refs/remotes/fixture/a")
            _git(
                merged,
                "fetch",
                str(clone_b),
                "HEAD:refs/remotes/fixture/b",
            )
            merge_result = _git(
                merged,
                "merge",
                "--no-ff",
                "--no-edit",
                "refs/remotes/fixture/b",
            )
            self.assertNotIn("CONFLICT", merge_result.stdout + merge_result.stderr)
            union = event_identity.load_event_union(merged)
            self.assertEqual(len(union), 3)  # one legacy + both clone events
            self.assertEqual(
                len({event_identity.immutable_event_uid(event) for event in union}),
                3,
            )
            before = {
                event_identity.immutable_event_uid(event): json.dumps(
                    event, sort_keys=True, separators=(",", ":")
                )
                for event in union
            }
            event_identity.derive_display_order(union)
            after = {
                event_identity.immutable_event_uid(event): json.dumps(
                    event, sort_keys=True, separators=(",", ":")
                )
                for event in union
            }
            self.assertEqual(before, after)

    def test_identity_conflict_refuses_but_identical_copy_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_clone(root)
            writer = event_identity.derive_writer_instance_uid(
                root, "cdf9b3ad", activation_uid="197f05e1"
            )
            event = event_identity.append_stream_event(
                root,
                writer,
                {
                    "specversion": "1.0",
                    "type": "tropo.message.sent",
                    "source": "/agents/argus",
                    "time": "2026-07-15T01:00:00Z",
                    "source_uid": "cdf9b3ad",
                    "lifecycle": "evergreen",
                },
            )
            duplicate = root / "vault" / "events" / "streams" / "duplicate.jsonl"
            duplicate.write_text(json.dumps(event) + "\n", encoding="utf-8")
            self.assertEqual(len(event_identity.load_event_union(root)), 2)

            conflicting = dict(event)
            conflicting["type"] = "tropo.message.replied"
            duplicate.write_text(json.dumps(conflicting) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "same identity, different content"):
                event_identity.load_event_union(root)

    def test_cutover_marker_is_strict_hash_bound_and_env_cannot_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_clone(root)
            marker = root / ".tropo" / "event-streams-v2.enabled"
            with mock.patch.dict(os.environ, {"TROPO_EVENT_STREAMS_V2": "0"}):
                self.assertTrue(event_identity.streams_enabled(root))

            marker.unlink()
            with mock.patch.dict(os.environ, {"TROPO_EVENT_STREAMS_V2": "1"}):
                self.assertFalse(event_identity.streams_enabled(root))

            marker.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "marker keys mismatch"):
                event_identity.streams_enabled(root)

            _write_cutover_marker(root)
            writer = event_identity.derive_writer_instance_uid(
                root, "cdf9b3ad", activation_uid="197f05e1"
            )
            event_identity.append_stream_event(
                root,
                writer,
                {
                    "specversion": "1.0",
                    "type": "tropo.message.sent",
                    "source": "/agents/argus",
                    "time": "2026-07-18T00:00:00Z",
                    "source_uid": "cdf9b3ad",
                    "lifecycle": "evergreen",
                },
            )
            marker.unlink()
            with self.assertRaisesRegex(RuntimeError, "forward-only"):
                event_identity.streams_enabled(root)

            _write_cutover_marker(root)
            (root / "vault" / "files" / "de9ac53c.md").write_text(
                "tampered\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "evidence hash mismatch"):
                event_identity.streams_enabled(root)

    def test_cutover_evidence_uses_clean_filtered_head_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_clone(root)
            strip_script = root / "strip_nav.py"
            strip_script.write_text(
                "import re,sys\n"
                "data=sys.stdin.buffer.read()\n"
                "data=re.sub(br'<!-- nav-block:start -->\\n.*?<!-- nav-block:end -->\\n',"
                "b'',data,flags=re.S)\n"
                "sys.stdout.buffer.write(data)\n",
                encoding="utf-8",
            )
            (root / ".gitattributes").write_text(
                "vault/files/f15a9b85.md filter=cutover-nav\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "fixture@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Fixture"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "config",
                    "filter.cutover-nav.clean",
                    f"{sys.executable} {strip_script}",
                ],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "filter.cutover-nav.smudge", "cat"],
                cwd=root,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "fixture cutover"],
                cwd=root,
                check=True,
            )

            evidence = root / "vault" / "files" / "f15a9b85.md"
            evidence.write_bytes(
                evidence.read_bytes()
                + b"<!-- nav-block:start -->\nhydrated navigation\n"
                + b"<!-- nav-block:end -->\n"
            )
            working_blob = subprocess.run(
                [
                    "git",
                    "hash-object",
                    "--path=vault/files/f15a9b85.md",
                    str(evidence),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            head_blob = subprocess.run(
                ["git", "rev-parse", "HEAD:vault/files/f15a9b85.md"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            self.assertEqual(working_blob, head_blob)
            marker_value = json.loads(
                (root / ".tropo" / "event-streams-v2.enabled").read_text(
                    encoding="utf-8"
                )
            )
            self.assertNotEqual(
                _sha256(evidence),
                marker_value["dev_spec_sha256"],
                "raw hydrated bytes must differ so the plant exercises Git binding",
            )
            self.assertTrue(event_identity.streams_enabled(root))

            evidence.write_bytes(
                evidence.read_bytes().replace(
                    b"uid: f15a9b85",
                    b"uid: f15a9b85\nchanged: true",
                    1,
                )
            )
            with self.assertRaisesRegex(RuntimeError, "canonical working-tree drift"):
                event_identity.streams_enabled(root)

    def test_stale_branch_refuses_legacy_emit_when_main_has_cut_over(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_clone(root)
            marker = root / ".tropo" / "event-streams-v2.enabled"
            marker.unlink()

            _git(root, "init", "-b", "main")
            _git(root, "config", "user.email", "fixture@tropo.local")
            _git(root, "config", "user.name", "Fixture")
            _git(root, "add", ".")
            _git(root, "commit", "-m", "pre-cutover")
            _git(root, "branch", "stale-writer")

            _write_cutover_marker(root)
            _git(root, "add", ".tropo/event-streams-v2.enabled")
            _git(root, "commit", "-m", "cut over event ledger")
            _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
            _git(root, "checkout", "stale-writer")
            _git(root, "branch", "-D", "main")

            legacy = root / "vault" / "events" / "00-events.jsonl"
            before = legacy.read_bytes()
            with self.assertRaisesRegex(
                RuntimeError,
                "cutover marker exists on main.*merge current main",
            ):
                event_identity.streams_enabled(root)
            self.assertEqual(legacy.read_bytes(), before)

    def test_nonfinal_reply_never_closes_legacy_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_clone(root)
            request = _legacy_event()
            request["data"] = {"reply_required": True, "body": "legacy request"}
            grandfathered_request = _legacy_event("00000002")
            grandfathered_request["time"] = "2026-07-15T00:00:01Z"
            grandfathered_request["data"] = {
                "reply_required": True,
                "body": "legacy grandfather request",
            }
            grandfathered_reply = _legacy_event("00000003")
            grandfathered_reply["type"] = "tropo.message.replied"
            grandfathered_reply["time"] = "2026-07-15T00:00:02Z"
            grandfathered_reply["correlationid"] = "00000002"
            grandfathered_reply["data"] = {
                "body": "historical terminal reply",
                "final": False,
            }
            legacy_path = root / "vault" / "events" / "00-events.jsonl"
            legacy_path.write_text(
                "".join(
                    json.dumps(event, separators=(",", ":")) + "\n"
                    for event in (
                        request,
                        grandfathered_request,
                        grandfathered_reply,
                    )
                ),
                encoding="utf-8",
            )
            _write_cutover_marker(root)
            writer = event_identity.derive_writer_instance_uid(
                root, "cdf9b3ad", activation_uid="197f05e1"
            )
            event_identity.append_stream_event(
                root,
                writer,
                {
                    "specversion": "1.0",
                    "type": "tropo.message.replied",
                    "source": "/agents/argus",
                    "time": "2026-07-18T00:01:00Z",
                    "source_uid": "cdf9b3ad",
                    "lifecycle": "evergreen",
                    "subject": "cdf9b3ad",
                    "correlationid": "legacy_00000001",
                    "data": {"body": "progress", "final": False},
                },
            )
            if str(TOOLS) not in sys.path:
                sys.path.insert(0, str(TOOLS))
            check_events = _load(
                "distributed_check_events_finality_test",
                TOOLS / "tropo-check-events.py",
            )
            check_events.VAULT_ROOT = root
            unanswered = check_events.scan_unanswered_rr("cdf9b3ad", None)
            self.assertEqual(
                [event_identity.immutable_event_uid(event) for event in unanswered],
                ["legacy_00000001"],
            )

            event_identity.append_stream_event(
                root,
                writer,
                {
                    "specversion": "1.0",
                    "type": "tropo.message.replied",
                    "source": "/agents/argus",
                    "time": "2026-07-18T00:02:00Z",
                    "source_uid": "cdf9b3ad",
                    "lifecycle": "evergreen",
                    "subject": "cdf9b3ad",
                    "correlationid": "legacy_00000001",
                    "data": {"body": "done", "final": True},
                },
            )
            self.assertEqual(
                check_events.scan_unanswered_rr("cdf9b3ad", None),
                [],
            )

    def test_moved_studio_preserves_identity_and_contains_no_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source, moved = base / "source", base / "moved"
            _prepare_clone(source)
            writer = event_identity.derive_writer_instance_uid(
                source, "cdf9b3ad", activation_uid="197f05e1"
            )
            event_identity.append_stream_event(
                source,
                writer,
                {
                    "specversion": "1.0",
                    "type": "tropo.message.sent",
                    "source": "/agents/argus",
                    "time": "2026-07-18T00:00:00Z",
                    "source_uid": "cdf9b3ad",
                    "lifecycle": "evergreen",
                    "data": {"body": "portable"},
                },
            )
            before = {
                event_identity.immutable_event_uid(event)
                for event in event_identity.load_event_union(source)
            }
            shutil.copytree(source, moved)
            moved_union = event_identity.load_event_union(moved)
            after = {
                event_identity.immutable_event_uid(event)
                for event in moved_union
            }
            self.assertEqual(before, after)
            raw = json.dumps(moved_union, sort_keys=True)
            self.assertNotIn(str(source), raw)
            self.assertNotIn(str(moved), raw)

    def _prepare_event_cli_sandbox(self, root: Path) -> Path:
        _prepare_clone(root)
        tools = root / "vault" / "tools"
        tools.mkdir()
        for name in (
            "tropo-check-events.py",
            "tropo-emit-event.py",
            "tropo-query-events.py",
            "tropo-rebuild-events-sqlite.py",
        ):
            shutil.copy2(TOOLS / name, tools / name)
        shutil.copytree(TOOLS / "lib", tools / "lib")
        agents = root / "vault" / "agents"
        agents.mkdir()
        (agents / "76f0219f.md").write_text(
            "---\n"
            "uid: 76f0219f\nagent: argus\nparty_uid: cdf9b3ad\n"
            "agent_root_uid: 6dff0111\ncurrent_activation_uid: 197f05e1\n"
            "---\n",
            encoding="utf-8",
        )
        return tools

    def _rebuild_projection(self, root: Path, tools: Path) -> None:
        subprocess.run(
            [sys.executable, str(tools / "tropo-rebuild-events-sqlite.py")],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )

    def _clear_drain_state(self, root: Path) -> None:
        cursor = root / "vault" / "events" / ".cursor-cdf9b3ad.json"
        cursor.unlink(missing_ok=True)
        shutil.rmtree(
            root / "vault" / "events" / "receipts",
            ignore_errors=True,
        )

    def test_query_and_check_events_projection_trust_matrix(self) -> None:
        # v1.10: this case locks the FALLBACK contract — a divergent projection
        # must never become delivery truth. Self-heal is suppressed here so the
        # divergent states stay divergent for the length of the matrix; the
        # heal itself is covered by test_divergent_projection_self_heals_on_read.
        no_heal_env = dict(os.environ)
        no_heal_env[event_identity.AUTOHEAL_DISABLE_ENV] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = self._prepare_event_cli_sandbox(root)
            sqlite_path = root / "vault" / "events" / "00-events-index.sqlite"
            emitted = subprocess.run(
                [
                    sys.executable,
                    str(tools / "tropo-emit-event.py"),
                    "--type", "tropo.message.sent",
                    "--source", "/agents/argus",
                    "--as", "argus",
                    "--lifecycle", "evergreen",
                    "--subject", "cdf9b3ad",
                    "--data", '{"reply_required":true,"body":"canonical-only request"}',
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            request_uid = json.loads(emitted.stdout)["event_uid"]
            self.assertFalse(
                sqlite_path.exists(),
                "emit must not initialize an absent projection from one append",
            )

            forced_jsonl = subprocess.run(
                [
                    sys.executable,
                    str(tools / "tropo-query-events.py"),
                    "--jsonl",
                    "--limit", "10",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )

            def semantics(events: list[dict]) -> list[tuple]:
                return [
                    (
                        event_identity.immutable_event_uid(event),
                        event.get("display_seq"),
                        event.get("type"),
                        event.get("source_uid"),
                        event.get("subject"),
                        event.get("correlationid"),
                        event.get("data"),
                    )
                    for event in events
                ]

            expected_query = semantics(json.loads(forced_jsonl.stdout))
            expected_new = [
                "legacy_00000001",
                request_uid,
            ]
            expected_unanswered = [request_uid]
            divergent_uid = "evt_ffffffffffffffff_99999999"

            for state in (
                "absent",
                "one-row",
                "equal-count-divergent",
                "unreadable",
                "complete",
                "complete-payload-divergent",
            ):
                for suffix in ("", "-wal", "-shm"):
                    Path(str(sqlite_path) + suffix).unlink(missing_ok=True)
                if state == "unreadable":
                    sqlite_path.write_bytes(b"not a sqlite database")
                elif state != "absent":
                    self._rebuild_projection(root, tools)
                    if state == "one-row":
                        with sqlite3.connect(sqlite_path) as conn:
                            conn.execute(
                                "DELETE FROM events WHERE event_uid = ?",
                                (request_uid,),
                            )
                            conn.commit()
                    elif state == "equal-count-divergent":
                        with sqlite3.connect(sqlite_path) as conn:
                            conn.execute(
                                "UPDATE events SET event_uid = ? WHERE event_uid = ?",
                                (divergent_uid, request_uid),
                            )
                            conn.commit()
                    elif state == "complete-payload-divergent":
                        with sqlite3.connect(sqlite_path) as conn:
                            raw = conn.execute(
                                "SELECT raw FROM events WHERE event_uid = ?",
                                (request_uid,),
                            ).fetchone()[0]
                            projected_event = json.loads(raw)
                            projected_event["data"]["body"] = (
                                "sqlite payload must never drive check-events"
                            )
                            conn.execute(
                                "UPDATE events SET raw = ? WHERE event_uid = ?",
                                (json.dumps(projected_event), request_uid),
                            )
                            conn.commit()

                if state == "one-row":
                    with sqlite3.connect(sqlite_path) as conn:
                        self.assertEqual(
                            conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                            1,
                        )
                if state == "equal-count-divergent":
                    with sqlite3.connect(sqlite_path) as conn:
                        projected = {
                            row[0]
                            for row in conn.execute("SELECT event_uid FROM events")
                        }
                    self.assertEqual(len(projected), len(expected_query))
                    self.assertIn(divergent_uid, projected)
                    self.assertNotIn(request_uid, projected)

                query = subprocess.run(
                    [
                        sys.executable,
                        str(tools / "tropo-query-events.py"),
                        "--limit", "10",
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True,
                    env=no_heal_env,
                )
                query_payload = json.loads(query.stdout)
                if state == "complete-payload-divergent":
                    projected_request = next(
                        event for event in query_payload
                        if event_identity.immutable_event_uid(event) == request_uid
                    )
                    self.assertEqual(
                        projected_request["data"]["body"],
                        "sqlite payload must never drive check-events",
                        "query-events may use identity-complete SQLite under the locked contract",
                    )
                else:
                    self.assertEqual(
                        semantics(query_payload),
                        expected_query,
                        f"query mismatch for projection state {state}",
                    )

                self._clear_drain_state(root)
                drain = subprocess.run(
                    [
                        sys.executable,
                        str(tools / "tropo-check-events.py"),
                        "--as", "argus",
                        "--json",
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True,
                    env=no_heal_env,
                )
                payload = json.loads(drain.stdout)
                self.assertEqual(
                    [
                        event_identity.immutable_event_uid(event)
                        for event in payload["new_events"]
                    ],
                    expected_new,
                    f"drain mismatch for projection state {state}",
                )
                self.assertEqual(
                    [
                        event_identity.immutable_event_uid(event)
                        for event in payload["unanswered_reply_required"]
                    ],
                    expected_unanswered,
                    f"false-clear for projection state {state}",
                )
                drained_request = next(
                    event for event in payload["new_events"]
                    if event_identity.immutable_event_uid(event) == request_uid
                )
                self.assertEqual(
                    drained_request["data"]["body"],
                    "canonical-only request",
                    f"SQLite became delivery authority for projection state {state}",
                )
                cursor = json.loads(
                    (
                        root / "vault" / "events" / ".cursor-cdf9b3ad.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(cursor["last_id"], "2")
                receipt_ids = {
                    json.loads(line)["event_id"]
                    for line in (
                        root / "vault" / "events" / "receipts" / "cdf9b3ad.jsonl"
                    ).read_text(encoding="utf-8").splitlines()
                }
                self.assertEqual(receipt_ids, set(expected_new))

                should_warn = state in {
                    "one-row",
                    "equal-count-divergent",
                    "unreadable",
                }
                self.assertEqual(
                    "falling back to canonical JSONL union" in query.stderr,
                    should_warn,
                    f"query warning mismatch for projection state {state}",
                )
                self.assertEqual(
                    "SQLite event projection is incomplete" in drain.stderr,
                    should_warn,
                    f"drain warning mismatch for projection state {state}",
                )

    def test_emit_dual_writes_only_complete_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = self._prepare_event_cli_sandbox(root)
            sqlite_path = root / "vault" / "events" / "00-events-index.sqlite"
            emit = [
                sys.executable,
                str(tools / "tropo-emit-event.py"),
                "--type", "tropo.message.sent",
                "--source", "/agents/argus",
                "--as", "argus",
                "--lifecycle", "evergreen",
                "--subject", "cdf9b3ad",
            ]

            first = subprocess.run(
                emit + ["--data", '{"body":"absent projection"}'],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertFalse(sqlite_path.exists())
            first_uid = json.loads(first.stdout)["event_uid"]

            self._rebuild_projection(root, tools)
            self.assertTrue(
                event_identity.sqlite_projection_complete(
                    sqlite_path,
                    event_identity.load_event_union(root),
                )
            )

            second = subprocess.run(
                emit + ["--data", '{"body":"complete projection"}'],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            second_payload = json.loads(second.stdout)
            self.assertEqual(second_payload["display_seq"], 3)
            with sqlite3.connect(sqlite_path) as conn:
                projected = {
                    row[0]
                    for row in conn.execute("SELECT event_uid FROM events")
                }
            self.assertEqual(
                projected,
                {"legacy_00000001", first_uid, second_payload["event_uid"]},
            )
            self.assertTrue(
                event_identity.sqlite_projection_complete(
                    sqlite_path,
                    event_identity.load_event_union(root),
                )
            )

            with sqlite3.connect(sqlite_path) as conn:
                conn.execute(
                    "DELETE FROM events WHERE event_uid = 'legacy_00000001'"
                )
                conn.commit()
            third = subprocess.run(
                emit + ["--data", '{"body":"partial projection"}'],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            third_payload = json.loads(third.stdout)
            # v1.10 contract (and v1.9's stated intent, which this assertion
            # predated): a divergence detected at emit is REPAIRED, and the
            # emitting event then dual-writes into the healed projection.
            self.assertEqual(third_payload["display_seq"], 4)
            self.assertIn("auto-rebuild succeeded", third.stderr)
            with sqlite3.connect(sqlite_path) as conn:
                projected_after = {
                    row[0]
                    for row in conn.execute("SELECT event_uid FROM events")
                }
            self.assertIn(third_payload["event_uid"], projected_after)
            self.assertIn("legacy_00000001", projected_after)
            self.assertTrue(
                event_identity.sqlite_projection_complete(
                    sqlite_path,
                    event_identity.load_event_union(root),
                )
            )

            # ...and with the heal suppressed, the v1.7 fail-closed path is
            # still exactly intact: never extend a divergent projection.
            no_heal_env = dict(os.environ)
            no_heal_env[event_identity.AUTOHEAL_DISABLE_ENV] = "1"
            with sqlite3.connect(sqlite_path) as conn:
                conn.execute(
                    "DELETE FROM events WHERE event_uid = 'legacy_00000001'"
                )
                conn.commit()
            fourth = subprocess.run(
                emit + ["--data", '{"body":"fail-closed when heal suppressed"}'],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                env=no_heal_env,
            )
            fourth_payload = json.loads(fourth.stdout)
            self.assertIsNone(fourth_payload["display_seq"])
            self.assertIn("self-heal suppressed by environment", fourth.stderr)
            with sqlite3.connect(sqlite_path) as conn:
                projected_suppressed = {
                    row[0]
                    for row in conn.execute("SELECT event_uid FROM events")
                }
            self.assertNotIn(fourth_payload["event_uid"], projected_suppressed)
            self.assertFalse(
                event_identity.sqlite_projection_complete(
                    sqlite_path,
                    event_identity.load_event_union(root),
                )
            )

    def test_divergent_projection_self_heals_on_read(self) -> None:
        """A divergence introduced with NO local emit repairs itself on read.

        This is the v1.10 regression guard. The emit-time heal could only ever
        fire on the write path, but on a multi-agent day the divergence source
        is `git merge`: another agent's stream lands in the canonical union and
        nothing local emits, so the projection stayed behind and every read
        warned until a human ran the rebuild by hand. Reproduced here by
        appending a foreign writer's stream directly — the same shape a merge
        produces — and then only ever READING.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = self._prepare_event_cli_sandbox(root)
            sqlite_path = root / "vault" / "events" / "00-events-index.sqlite"
            cooldown = root / event_identity.AUTOHEAL_COOLDOWN_REL

            subprocess.run(
                [
                    sys.executable, str(tools / "tropo-emit-event.py"),
                    "--type", "tropo.message.sent",
                    "--source", "/agents/argus", "--as", "argus",
                    "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                    "--data", '{"body":"local event"}',
                ],
                cwd=root, capture_output=True, text=True, check=True,
            )
            self._rebuild_projection(root, tools)
            self.assertTrue(
                event_identity.sqlite_projection_complete(
                    sqlite_path, event_identity.load_event_union(root)
                ),
                "precondition: projection starts complete",
            )

            # The merge: a foreign writer's stream file appears in the canonical
            # union with no local emit to trigger the old write-path-only heal.
            merged = {
                "specversion": "1.0",
                "type": "tropo.broadcast.crew",
                "source": "/agents/metis",
                "time": "2026-07-31T05:00:00Z",
                "source_uid": "7c017d1f",
                "lifecycle": "evergreen",
                "data": {"category": "ops", "body": "arrived by merge"},
                "id": "evt_aaaabbbbccccdddd_00000001",
                "event_uid": "evt_aaaabbbbccccdddd_00000001",
                "writer_instance_uid": "aaaabbbbccccdddd",
                "stream_uid": "aaaabbbbccccdddd",
                "local_seq": 1,
            }
            streams = root / event_identity.STREAMS_REL
            streams.mkdir(parents=True, exist_ok=True)
            (streams / "aaaabbbbccccdddd.jsonl").write_text(
                json.dumps(merged) + "\n", encoding="utf-8"
            )
            self.assertFalse(
                event_identity.sqlite_projection_complete(
                    sqlite_path, event_identity.load_event_union(root)
                ),
                "merge must leave the derived projection behind",
            )
            cooldown.unlink(missing_ok=True)

            drain = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-check-events.py"),
                    "--as", "argus", "--json",
                ],
                cwd=root, capture_output=True, text=True, check=True,
            )

            # The read healed it, with no emit and no human in the loop.
            self.assertIn("auto-rebuild succeeded", drain.stderr)
            self.assertTrue(
                event_identity.sqlite_projection_complete(
                    sqlite_path, event_identity.load_event_union(root)
                ),
                "read path must repair a merge-induced divergence",
            )
            # Delivery is unchanged: the merged event is still delivered from
            # the canonical union, exactly as it was before the heal existed.
            delivered = {
                event_identity.immutable_event_uid(event)
                for event in json.loads(drain.stdout)["new_events"]
            }
            self.assertIn("evt_aaaabbbbccccdddd_00000001", delivered)

            # And a second read is quiet — the warning does not repeat forever.
            self._clear_drain_state(root)
            second = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-check-events.py"),
                    "--as", "argus", "--json",
                ],
                cwd=root, capture_output=True, text=True, check=True,
            )
            self.assertNotIn("incomplete, divergent, or unreadable", second.stderr)

    def test_autoheal_is_cooldown_gated_and_never_recurses(self) -> None:
        """One repair per cooldown window, and never a rebuild storm.

        Two independent storm risks: many callers hitting a persistent
        divergence back to back, and the rebuild subprocess re-entering the
        heal through its own import of this library.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = self._prepare_event_cli_sandbox(root)
            sqlite_path = root / "vault" / "events" / "00-events-index.sqlite"
            cooldown = root / event_identity.AUTOHEAL_COOLDOWN_REL

            subprocess.run(
                [
                    sys.executable, str(tools / "tropo-emit-event.py"),
                    "--type", "tropo.message.sent",
                    "--source", "/agents/argus", "--as", "argus",
                    "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                    "--data", '{"body":"seed"}',
                ],
                cwd=root, capture_output=True, text=True, check=True,
            )
            self._rebuild_projection(root, tools)

            # A divergence the rebuild cannot cure, so the cause persists and
            # every subsequent read re-detects it.
            with sqlite3.connect(sqlite_path) as conn:
                conn.execute("DROP TABLE events")
                conn.commit()
            cooldown.unlink(missing_ok=True)

            first = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-query-events.py"),
                    "--limit", "5",
                ],
                cwd=root, capture_output=True, text=True, check=True,
            )
            self.assertTrue(cooldown.is_file(), "first attempt records a cooldown")
            self.assertNotIn("cooldown active", first.stderr)

            second = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-query-events.py"),
                    "--limit", "5",
                ],
                cwd=root, capture_output=True, text=True, check=True,
            )
            self.assertIn("cooldown active", second.stderr)
            # Still correct output despite the unusable cache.
            self.assertIn("falling back to canonical JSONL union", second.stderr)
            self.assertEqual(len(json.loads(second.stdout)), 2)

            # Recursion guard: with the in-rebuild marker set, the heal is inert.
            active_env = dict(os.environ)
            active_env[event_identity.AUTOHEAL_ACTIVE_ENV] = "1"
            cooldown.unlink(missing_ok=True)
            nested = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-query-events.py"),
                    "--limit", "5",
                ],
                cwd=root, capture_output=True, text=True, check=True,
                env=active_env,
            )
            self.assertFalse(
                cooldown.is_file(),
                "a nested call must not even attempt a rebuild",
            )
            self.assertIn("self-heal suppressed by environment", nested.stderr)

    def test_discarded_reply_is_reported_not_silently_dropped(self) -> None:
        """1f29bcfb Case 5: strictness stays, silence goes.

        A correlated reply lacking `final: true` must NOT close the thread, and
        must NOT vanish. The old code dropped it before the correlation lookup
        and only ever read `correlationid`, so a reply sent with `--causationid`
        and no `--final` was reported as no reply at all. Metis was told she had
        zero confirmations while Talos's reply sat correct and pushed on main.
        """
        # the tool resolves its own lib/ via a sibling import
        if str(TOOLS) not in sys.path:
            sys.path.insert(0, str(TOOLS))
        check_events = _load(
            "case5_check_events", TOOLS / "tropo-check-events.py"
        )
        request = {
            "id": "9001", "event_uid": "evt_req_00000001",
            "type": "tropo.message.sent", "source_uid": "7c017d1f",
            "subject": "e97ac0ae", "time": "2026-07-31T03:56:49Z",
            "data": {"reply_required": True, "body": "confirm back"},
        }

        def reply(**over):
            base = {
                "id": "9002", "event_uid": "evt_rep_00000001",
                "type": "tropo.message.replied", "source_uid": "34cf0f1c",
                "subject": "7c017d1f", "time": "2026-07-31T04:01:00Z",
                "data": {"body": "watch armed"},
            }
            base.update(over)
            return base

        # (a) correlated via causationid, no final -> open, but VISIBLE
        via_causation = reply(causationid="evt_req_00000001")
        open_threads = check_events.scan_unanswered_rr(
            "e97ac0ae", None, event_union=[request, via_causation]
        )
        self.assertEqual(len(open_threads), 1, "strictness must be preserved")
        seen = open_threads[0].get("_nonterminal_replies") or []
        self.assertEqual(len(seen), 1, "the discarded reply must be reported")
        self.assertIn("causationid", seen[0][1])
        self.assertIn("no final: flag", seen[0][1])

        # (b) explicit final:false is also visible, with the accurate reason
        explicit = reply(
            correlationid="evt_req_00000001",
            data={"body": "partial", "final": False},
        )
        open_threads = check_events.scan_unanswered_rr(
            "e97ac0ae", None, event_union=[request, explicit]
        )
        self.assertEqual(len(open_threads), 1)
        self.assertEqual(
            open_threads[0]["_nonterminal_replies"][0][1], "final:false"
        )

        # (c) a terminal reply still closes the thread, via EITHER axis
        for axis in ("correlationid", "causationid"):
            terminal = reply(
                data={"body": "done", "final": True}, **{axis: "evt_req_00000001"}
            )
            self.assertEqual(
                check_events.scan_unanswered_rr(
                    "e97ac0ae", None, event_union=[request, terminal]
                ),
                [],
                f"final:true via {axis} must close the thread",
            )

        # (d) the frozen numeric epoch keeps its historical rule: no event_uid
        #     means any correlated answer was terminal, final flag or not.
        legacy_request = {
            "id": "9003", "type": "tropo.message.sent", "source_uid": "7c017d1f",
            "subject": "e97ac0ae", "time": "2026-06-01T00:00:00Z",
            "data": {"reply_required": True, "body": "legacy ask"},
        }
        legacy_reply = {
            "id": "9004", "type": "tropo.message.replied",
            "source_uid": "34cf0f1c", "subject": "7c017d1f",
            "time": "2026-06-01T00:05:00Z", "correlationid": "9003",
            "data": {"body": "legacy answer"},
        }
        self.assertEqual(
            check_events.scan_unanswered_rr(
                "e97ac0ae", None, event_union=[legacy_request, legacy_reply]
            ),
            [],
            "legacy epoch semantics must not regress",
        )

    def test_emit_refuses_untermed_reply_on_either_correlation_axis(self) -> None:
        """The door half of Case 5: refuse rather than accept-then-drop.

        The terminality guard checked only `correlationid`, so a reply carrying
        `--causationid` passed the door with no `final:` flag and became
        invisible hours later. Both axes are correlation sources now, so both
        are held to the same requirement.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = self._prepare_event_cli_sandbox(root)

            asked = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-emit-event.py"),
                    "--type", "tropo.message.sent",
                    "--source", "/agents/argus", "--as", "argus",
                    "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                    "--data", '{"reply_required":true,"body":"confirm back"}',
                ],
                cwd=root, capture_output=True, text=True, check=True,
            )
            request_uid = json.loads(asked.stdout)["event_uid"]

            for axis in ("--correlationid", "--causationid"):
                refused = subprocess.run(
                    [
                        sys.executable, str(tools / "tropo-emit-event.py"),
                        "--type", "tropo.message.replied",
                        "--source", "/agents/argus", "--as", "argus",
                        "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                        axis, request_uid,
                        "--data", '{"body":"reply with no terminality"}',
                    ],
                    cwd=root, capture_output=True, text=True,
                )
                self.assertEqual(
                    refused.returncode, 1,
                    f"{axis} reply without --final must be refused at the door",
                )
                self.assertIn("MUST specify terminality", refused.stderr)

                accepted = subprocess.run(
                    [
                        sys.executable, str(tools / "tropo-emit-event.py"),
                        "--type", "tropo.message.replied",
                        "--source", "/agents/argus", "--as", "argus",
                        "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                        axis, request_uid, "--final",
                        "--data", '{"body":"terminal reply"}',
                    ],
                    cwd=root, capture_output=True, text=True,
                )
                self.assertEqual(
                    accepted.returncode, 0,
                    f"{axis} reply WITH --final must be accepted",
                )

    def test_reply_required_guard_resolves_against_canonical_not_cache(self) -> None:
        """The guard must not fail open just because the derived cache is blind.

        It used to read the SQLite projection and return False on any miss, so
        a request that had not reached the cache yet — or any divergence at all
        — silently disengaged the lock. Same blind-instrument class as the
        finding it serves.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = self._prepare_event_cli_sandbox(root)
            sqlite_path = root / "vault" / "events" / "00-events-index.sqlite"

            asked = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-emit-event.py"),
                    "--type", "tropo.message.sent",
                    "--source", "/agents/argus", "--as", "argus",
                    "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                    "--data", '{"reply_required":true,"body":"confirm back"}',
                ],
                cwd=root, capture_output=True, text=True, check=True,
            )
            request_uid = json.loads(asked.stdout)["event_uid"]
            # No projection exists at all — the old guard's blindest case.
            self.assertFalse(sqlite_path.exists())

            refused = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-emit-event.py"),
                    "--type", "tropo.message.replied",
                    "--source", "/agents/argus", "--as", "argus",
                    "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                    "--correlationid", request_uid,
                    "--data", '{"body":"no terminality, no cache"}',
                ],
                cwd=root, capture_output=True, text=True,
            )
            self.assertEqual(
                refused.returncode, 1,
                "guard must fire from the canonical union with no cache present",
            )

    def test_message_only_terminal_reply_fails_loud_at_emit_and_read(self) -> None:
        """Reject bad writes and keep bypass-planted bad replies visible."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = self._prepare_event_cli_sandbox(root)
            asked = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-emit-event.py"),
                    "--type", "tropo.message.sent",
                    "--source", "/agents/argus", "--as", "argus",
                    "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                    "--data", '{"reply_required":true,"body":"send a visible answer"}',
                ],
                cwd=root, capture_output=True, text=True, check=True,
            )
            request_uid = json.loads(asked.stdout)["event_uid"]
            malformed = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-emit-event.py"),
                    "--type", "tropo.message.replied",
                    "--source", "/agents/argus", "--as", "argus",
                    "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                    "--correlationid", request_uid, "--final",
                    "--data", '{"message":"invisible to body renderer"}',
                ],
                cwd=root, capture_output=True, text=True,
            )
            self.assertEqual(malformed.returncode, 1)
            self.assertIn(
                "requires a non-empty data.body or data.body_file",
                malformed.stderr,
            )
            self.assertEqual(
                len(event_identity.load_event_union(root)),
                2,
                "rejected reply must not append to the canonical event union",
            )

            writer = event_identity.derive_writer_instance_uid(
                root, "cdf9b3ad", activation_uid="197f05e1"
            )
            reply = event_identity.append_stream_event(
                root,
                writer,
                {
                    "specversion": "1.0",
                    "type": "tropo.message.replied",
                    "source": "/agents/argus",
                    "time": "2026-08-02T16:00:00Z",
                    "source_uid": "cdf9b3ad",
                    "lifecycle": "evergreen",
                    "subject": "cdf9b3ad",
                    "correlationid": request_uid,
                    "data": {
                        "message": "invisible to body renderer",
                        "final": True,
                    },
                },
            )
            self.assertEqual(reply["data"]["message"], "invisible to body renderer")
            self.assertTrue(reply["data"]["final"])
            self.assertNotIn("body", reply["data"])
            self.assertNotIn("body_file", reply["data"])

            event_union = event_identity.load_event_union(root)
            if str(TOOLS) not in sys.path:
                sys.path.insert(0, str(TOOLS))
            check_events = _load(
                "blank_reply_defense_check_events",
                TOOLS / "tropo-check-events.py",
            )
            check_events.VAULT_ROOT = root
            unanswered = check_events.scan_unanswered_rr(
                "cdf9b3ad", None, event_union=event_union
            )
            self.assertEqual(len(unanswered), 1)
            self.assertEqual(
                event_identity.immutable_event_uid(unanswered[0]),
                request_uid,
            )
            self.assertEqual(
                unanswered[0]["_nonterminal_replies"][0][1],
                "no renderable body/body_file",
            )

            event_validators = _load(
                "blank_reply_defense_event_validators",
                ROOT / ".tropo" / "scripts" / "lib" / "event_validators.py",
            )
            findings, _, defects = event_validators.run_all_event_checks(root)
            self.assertGreater(defects, 0)
            self.assertTrue(
                any(finding.check_id == "event-11" for finding in findings),
                "validator must detect malformed rows that bypass emit-event",
            )

    def test_terminal_reply_accepts_inline_body_or_body_file(self) -> None:
        for field, value in (
            ("body", "visible inline answer"),
            ("body_file", "vault/events/files/reply.md"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tools = self._prepare_event_cli_sandbox(root)
                if field == "body_file":
                    reply_file = root / value
                    reply_file.parent.mkdir(parents=True)
                    reply_file.write_text("visible file answer\n", encoding="utf-8")
                asked = subprocess.run(
                    [
                        sys.executable, str(tools / "tropo-emit-event.py"),
                        "--type", "tropo.message.sent",
                        "--source", "/agents/argus", "--as", "argus",
                        "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                        "--data", '{"reply_required":true,"body":"answer me"}',
                    ],
                    cwd=root, capture_output=True, text=True, check=True,
                )
                request_uid = json.loads(asked.stdout)["event_uid"]
                payload = json.dumps({field: value})
                replied = subprocess.run(
                    [
                        sys.executable, str(tools / "tropo-emit-event.py"),
                        "--type", "tropo.message.replied",
                        "--source", "/agents/argus", "--as", "argus",
                        "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                        "--correlationid", request_uid, "--final",
                        "--data", payload,
                    ],
                    cwd=root, capture_output=True, text=True,
                )
                self.assertEqual(replied.returncode, 0, replied.stderr)

                event_union = event_identity.load_event_union(root)
                self.assertEqual(event_union[-1]["data"][field], value)
                if str(TOOLS) not in sys.path:
                    sys.path.insert(0, str(TOOLS))
                check_events = _load(
                    f"valid_terminal_{field}_check_events",
                    TOOLS / "tropo-check-events.py",
                )
                check_events.VAULT_ROOT = root
                self.assertEqual(
                    check_events.scan_unanswered_rr(
                        "cdf9b3ad", None, event_union=event_union
                    ),
                    [],
                )
                event_validators = _load(
                    f"valid_terminal_{field}_event_validators",
                    ROOT / ".tropo" / "scripts" / "lib" / "event_validators.py",
                )
                findings, _, _ = event_validators.run_all_event_checks(root)
                self.assertFalse(
                    any(finding.check_id == "event-11" for finding in findings),
                    f"valid {field} terminal reply must remain validator-clean",
                )

    def test_terminal_body_file_requires_renderable_companion(self) -> None:
        cases = (
            ("traversal", "vault/events/files/../../../escape.md", "visible\n", False),
            ("missing", "vault/events/files/missing.md", None, False),
            ("empty", "vault/events/files/empty.md", "", False),
            ("valid", "vault/events/files/reply.md", "visible\n", True),
        )
        for name, body_file, contents, valid in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tools = self._prepare_event_cli_sandbox(root)
                companion = root / body_file
                if contents is not None:
                    companion.parent.mkdir(parents=True, exist_ok=True)
                    companion.write_text(contents, encoding="utf-8")
                asked = subprocess.run(
                    [
                        sys.executable, str(tools / "tropo-emit-event.py"),
                        "--type", "tropo.message.sent",
                        "--source", "/agents/argus", "--as", "argus",
                        "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                        "--data", '{"reply_required":true,"body":"answer me"}',
                    ],
                    cwd=root, capture_output=True, text=True, check=True,
                )
                request_uid = json.loads(asked.stdout)["event_uid"]
                replied = subprocess.run(
                    [
                        sys.executable, str(tools / "tropo-emit-event.py"),
                        "--type", "tropo.message.replied",
                        "--source", "/agents/argus", "--as", "argus",
                        "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                        "--correlationid", request_uid, "--final",
                        "--data", json.dumps({"body_file": body_file}),
                    ],
                    cwd=root, capture_output=True, text=True,
                )
                self.assertEqual(replied.returncode, 0 if valid else 1, replied.stderr)

                if not valid and replied.returncode != 0:
                    writer = event_identity.derive_writer_instance_uid(
                        root, "cdf9b3ad", activation_uid="197f05e1"
                    )
                    event_identity.append_stream_event(
                        root,
                        writer,
                        {
                            "specversion": "1.0",
                            "type": "tropo.message.replied",
                            "source": "/agents/argus",
                            "time": "2026-08-02T16:00:00Z",
                            "source_uid": "cdf9b3ad",
                            "lifecycle": "evergreen",
                            "subject": "cdf9b3ad",
                            "correlationid": request_uid,
                            "data": {"body_file": body_file, "final": True},
                        },
                    )

                event_union = event_identity.load_event_union(root)
                if str(TOOLS) not in sys.path:
                    sys.path.insert(0, str(TOOLS))
                check_events = _load(
                    f"body_file_{name}_check_events",
                    TOOLS / "tropo-check-events.py",
                )
                check_events.VAULT_ROOT = root
                unanswered = check_events.scan_unanswered_rr(
                    "cdf9b3ad", None, event_union=event_union
                )
                self.assertEqual(len(unanswered), 0 if valid else 1)

                event_validators = _load(
                    f"body_file_{name}_event_validators",
                    ROOT / ".tropo" / "scripts" / "lib" / "event_validators.py",
                )
                findings, _, _ = event_validators.run_all_event_checks(root)
                self.assertEqual(
                    any(finding.check_id == "event-11" for finding in findings),
                    not valid,
                )

    def test_cli_query_receipt_and_correlation_dual_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_clone(root)
            tools = root / "vault" / "tools"
            tools.mkdir()
            for name in (
                "tropo-emit-event.py",
                "tropo-rebuild-events-sqlite.py",
                "tropo-check-events.py",
                "tropo-query-events.py",
            ):
                shutil.copy2(TOOLS / name, tools / name)
            shutil.copytree(TOOLS / "lib", tools / "lib")
            agents = root / "vault" / "agents"
            agents.mkdir()
            (agents / "76f0219f.md").write_text(
                "---\n"
                "uid: 76f0219f\nagent: argus\nparty_uid: cdf9b3ad\n"
                "agent_root_uid: 6dff0111\ncurrent_activation_uid: 197f05e1\n"
                "---\n",
                encoding="utf-8",
            )
            env = dict(os.environ)
            legacy_raw = (
                root / "vault" / "events" / "00-events.jsonl"
            ).read_text(encoding="utf-8").splitlines()[0]
            emit = [
                sys.executable, str(tools / "tropo-emit-event.py"),
                "--type", "tropo.message.sent",
                "--source", "/agents/argus", "--as", "argus",
                "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                "--data", '{"reply_required":true,"body":"new request"}',
            ]
            first = subprocess.run(
                emit, cwd=root, env=env, capture_output=True, text=True, check=True
            )
            request = json.loads(first.stdout)
            self.assertTrue(request["event_uid"].startswith("evt_"))
            self.assertEqual(
                (root / "vault" / "events" / "00-events.jsonl").read_text().count("\n"),
                1,
            )

            reply = [
                sys.executable, str(tools / "tropo-emit-event.py"),
                "--type", "tropo.message.replied",
                "--source", "/agents/argus", "--as", "argus",
                "--lifecycle", "evergreen", "--subject", "cdf9b3ad",
                "--correlationid", request["event_uid"], "--final",
                "--data", '{"body":"new reply"}',
            ]
            subprocess.run(
                reply, cwd=root, env=env, capture_output=True, text=True, check=True
            )
            subprocess.run(
                [sys.executable, str(tools / "tropo-rebuild-events-sqlite.py")],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            with sqlite3.connect(root / "vault" / "events" / "00-events-index.sqlite") as conn:
                rows = conn.execute(
                    "SELECT event_uid, display_seq FROM events ORDER BY display_seq"
                ).fetchall()
                rebuilt_legacy_raw = conn.execute(
                    "SELECT raw FROM events WHERE event_uid='legacy_00000001'"
                ).fetchone()[0]
            self.assertEqual(len(rows), 3)
            self.assertEqual([row[1] for row in rows], [1, 2, 3])
            self.assertEqual(rebuilt_legacy_raw, legacy_raw)

            drained = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-check-events.py"),
                    "--as", "argus", "--json",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(drained.stdout)
            self.assertEqual(payload["unanswered_reply_required"], [])
            receipt_path = root / "vault" / "events" / "receipts" / "cdf9b3ad.jsonl"
            receipts = [json.loads(line)["event_id"] for line in receipt_path.read_text().splitlines()]
            self.assertTrue(any(value.startswith("evt_") for value in receipts))

            # AC8 adversarial: merge previously-unread stream events whose
            # timestamps derive behind the saved cursor while deliberately
            # leaving the SQLite projection stale. Receipt-set + canonical
            # union truth must still deliver them.
            writer = event_identity.derive_writer_instance_uid(
                root, "cdf9b3ad", activation_uid="197f05e1"
            )
            late = event_identity.append_stream_event(
                root,
                writer,
                {
                    "specversion": "1.0",
                    "type": "tropo.message.sent",
                    "source": "/agents/argus",
                    "time": "2026-07-15T00:30:00Z",
                    "source_uid": "cdf9b3ad",
                    "lifecycle": "evergreen",
                    "subject": "cdf9b3ad",
                    "data": {"body": "late merged event"},
                },
            )
            untargeted = event_identity.append_stream_event(
                root,
                writer,
                {
                    "specversion": "1.0",
                    "type": "tropo.message.sent",
                    "source": "/agents/argus",
                    "time": "2026-07-15T00:31:00Z",
                    "source_uid": "cdf9b3ad",
                    "lifecycle": "evergreen",
                    "subject": "cdf9b3ad",
                    "data": {"body": "must remain unread after targeted drain"},
                },
            )
            with sqlite3.connect(
                root / "vault" / "events" / "00-events-index.sqlite"
            ) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM events WHERE event_uid IN (?, ?)",
                        (late["event_uid"], untargeted["event_uid"]),
                    ).fetchone()[0],
                    0,
                    "fixture must prove the derived SQLite cache is stale",
                )

            targeted_drain = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-check-events.py"),
                    "--as", "argus", "--id", late["event_uid"], "--json",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            late_payload = json.loads(targeted_drain.stdout)
            self.assertEqual(
                [event["event_uid"] for event in late_payload["new_events"]],
                [late["event_uid"]],
            )
            receipt_ids = {
                json.loads(line)["event_id"]
                for line in receipt_path.read_text().splitlines()
            }
            self.assertIn(late["event_uid"], receipt_ids)
            self.assertNotIn(
                untargeted["event_uid"],
                receipt_ids,
                "an --id drain must not receipt unrelated unseen messages",
            )

            remaining_drain = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-check-events.py"),
                    "--as", "argus", "--json",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            remaining_payload = json.loads(remaining_drain.stdout)
            self.assertEqual(
                [event["event_uid"] for event in remaining_payload["new_events"]],
                [untargeted["event_uid"]],
            )

            queried = subprocess.run(
                [
                    sys.executable, str(tools / "tropo-query-events.py"),
                    "--correlationid", request["event_uid"], "--jsonl",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            query_payload = json.loads(queried.stdout)
            self.assertEqual(len(query_payload), 1)
            self.assertEqual(query_payload[0]["correlationid"], request["event_uid"])


if __name__ == "__main__":
    unittest.main()
