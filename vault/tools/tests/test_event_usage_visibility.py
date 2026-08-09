"""Viewer-safe usage query, validator, and bounded-scope regressions."""
from __future__ import annotations

import ast
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.event_visibility import EventVisibilityError  # noqa: E402
from lib.group_contract import GroupContractError, GroupErrorCode  # noqa: E402
from lib.group_registry import GroupResolver  # noqa: E402
from lib.viewer_projection import (  # noqa: E402
    InMemoryGraphSource,
    Viewer,
    ViewerProjection,
)


USAGE = "tropo.distill.usage.recorded"
TEAM = "a0000001"
PRIVATE_ALICE = "a0000002"
PRIVATE_BOB = "a0000003"
ALICE = "11111111"
BOB = "22222222"
TASK = "b0000001"
WRITER = "1234567890abcdef"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


query_events = _load("usage_visibility_query_test", TOOLS / "tropo-query-events.py")
event_validators = _load(
    "usage_visibility_validator_test",
    ROOT / ".tropo" / "scripts" / "lib" / "event_validators.py",
)
emit_event = _load("usage_visibility_emitter_test", TOOLS / "tropo-emit-event.py")


def _event(sequence: int, event_type: str, *, segment: str | None = None) -> dict:
    event_uid = f"evt_{WRITER}_{sequence:08d}"
    event = {
        "specversion": "1.0",
        "type": event_type,
        "source": "/tools/emit-event",
        "time": f"2026-07-23T00:00:{sequence:02d}Z",
        "source_uid": "ca90f098",
        "lifecycle": "evergreen",
        "subject": TASK,
        "id": event_uid,
        "event_uid": event_uid,
        "writer_instance_uid": WRITER,
        "stream_uid": WRITER,
        "local_seq": sequence,
    }
    if event_type == USAGE:
        event["segment"] = segment
        event["data"] = {
            "task_uid": TASK,
            "viewer_principal_uid": ALICE,
            "index_as_of": "fixture-snapshot-1",
            "operation": "distill",
            "used_chunk_uids": [f"chunk-{sequence}"],
            "unused_chunk_uids": [],
        }
    else:
        event["data"] = {"body": f"old-{sequence}"}
    return event


def _projection() -> ViewerProjection:
    def row(uid: str, members: tuple[str, ...], wider: tuple[str, ...]) -> dict:
        return {
            "group_uid": uid,
            "slug": f"group-{uid}",
            "title": uid,
            "status": "active",
            "version": 1,
            "owner_uid": ALICE,
            "direct_member_uids": members,
            "direct_included_group_uids": (),
            "effective_member_uids": members,
            "wider_group_uids": wider,
            "source_authority_uid": "aaaaaaaa",
            "source_revision": "fixture",
            "source_path": f"vault/files/{uid}.md",
            "source_hash": "0" * 64,
            "principal_directory_revision": "fixture",
        }

    authority = GroupResolver(
        {
            TEAM: row(TEAM, (ALICE, BOB), ()),
            PRIVATE_ALICE: row(PRIVATE_ALICE, (ALICE,), (TEAM,)),
            PRIVATE_BOB: row(PRIVATE_BOB, (BOB,), (TEAM,)),
        },
        revision="fixture",
    )
    graph = InMemoryGraphSource((), {}, {})
    return ViewerProjection.from_resolver(graph, authority)


class EventUsageVisibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = [
            _event(1, "tropo.message.sent"),
            _event(2, USAGE, segment=TEAM),
            _event(3, USAGE, segment=PRIVATE_ALICE),
            _event(4, USAGE, segment=PRIVATE_ALICE),
            _event(5, USAGE, segment=TEAM),
            _event(6, "tropo.message.sent"),
            _event(7, "tropo.message.sent"),
        ]

    def _query_jsonl(self, **kwargs) -> list[dict]:
        events = kwargs.pop("events", self.events)
        return query_events.query_jsonl(
            kwargs.pop("event_type", None),
            None,
            None,
            kwargs.pop("limit", 20),
            kwargs.pop("since_id", None),
            event_union=events,
            **kwargs,
        )

    def _query_sqlite(self, root: Path, **kwargs) -> list[dict]:
        events = kwargs.pop("events", self.events)
        sqlite_path = root / "events.sqlite"
        sqlite_path.unlink(missing_ok=True)
        with sqlite3.connect(sqlite_path) as conn:
            conn.execute(
                "CREATE TABLE events (event_uid TEXT, display_seq INTEGER, raw TEXT)"
            )
            for sequence, event in enumerate(events, start=1):
                conn.execute(
                    "INSERT INTO events VALUES (?,?,?)",
                    (event["event_uid"], sequence, json.dumps(event)),
                )
            conn.commit()
        original = query_events.SQLITE_PATH
        query_events.SQLITE_PATH = sqlite_path
        try:
            return query_events.query_sqlite(
                kwargs.pop("event_type", None),
                None,
                None,
                kwargs.pop("limit", 20),
                kwargs.pop("since_id", None),
                **kwargs,
            )
        finally:
            query_events.SQLITE_PATH = original

    def test_viewerless_preserves_full_union_order_before_filters_and_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for query in (
                self._query_jsonl,
                lambda **kwargs: self._query_sqlite(root, **kwargs),
            ):
                with self.subTest(store=query):
                    viewerless = query(limit=20)
                    self.assertEqual(
                        [event["data"]["body"] for event in viewerless],
                        ["old-7", "old-6", "old-1"],
                    )
                    self.assertEqual(
                        [event["display_seq"] for event in viewerless],
                        [7, 6, 1],
                        "hidden usage must leave canonical display-sequence gaps",
                    )
                    self.assertEqual(
                        [event["display_seq"] for event in query(limit=2)],
                        [7, 6],
                    )
                    self.assertEqual(query(event_type=USAGE, limit=20), [])
                    # --party remains only an address filter. Even a matching
                    # task subject cannot unlock segmented usage.
                    self.assertFalse(
                        any(
                            event["type"] == USAGE
                            for event in query(party_uid=TASK)
                        )
                    )
                    self.assertEqual(
                        [event["display_seq"] for event in query(since_id="5")],
                        [7, 6],
                    )

    def test_appended_hidden_usage_never_changes_old_display_or_cursor_results(self) -> None:
        before = list(self.events)
        after = [*before, _event(8, USAGE, segment=PRIVATE_ALICE)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for query in (
                self._query_jsonl,
                lambda **kwargs: self._query_sqlite(root, **kwargs),
            ):
                with self.subTest(store=query):
                    before_rows = query(events=before)
                    after_rows = query(events=after)
                    self.assertEqual(after_rows, before_rows)
                    self.assertEqual(
                        {
                            event["event_uid"]: event["display_seq"]
                            for event in after_rows
                        },
                        {
                            event["event_uid"]: event["display_seq"]
                            for event in before_rows
                        },
                    )
                    # A party cursor at canonical sequence 6 sees only old-7
                    # both before and after the hidden append; hidden sequence
                    # 8 neither appears nor rewrites the cursor boundary.
                    before_since = query(
                        events=before,
                        party_uid=TASK,
                        since_id="6",
                    )
                    after_since = query(
                        events=after,
                        party_uid=TASK,
                        since_id="6",
                    )
                    self.assertEqual(after_since, before_since)
                    self.assertEqual(
                        [event["display_seq"] for event in after_since],
                        [7],
                    )

    def test_authorized_team_private_and_peer_results_match_both_stores(self) -> None:
        projection = _projection()
        alice = Viewer(ALICE, PRIVATE_ALICE)
        bob = Viewer(BOB, PRIVATE_BOB)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for viewer, expected_usage_sequences in (
                (alice, {2, 3, 4, 5}),
                (bob, {2, 5}),
            ):
                with self.subTest(viewer=viewer):
                    jsonl = self._query_jsonl(
                        viewer=viewer,
                        projection=projection,
                    )
                    sqlite_rows = self._query_sqlite(
                        root,
                        viewer=viewer,
                        projection=projection,
                    )
                    self.assertEqual(sqlite_rows, jsonl)
                    visible_usage = {
                        event["local_seq"]
                        for event in jsonl
                        if event["type"] == USAGE
                    }
                    self.assertEqual(visible_usage, expected_usage_sequences)
                    self.assertTrue(
                        all(
                            event["type"] != USAGE
                            or event["segment"] != PRIVATE_ALICE
                            for event in jsonl
                        )
                        if viewer == bob
                        else True
                    )

    def test_visibility_authority_failure_has_no_partial_result(self) -> None:
        error = GroupContractError(
            GroupErrorCode.GROUP_CORPUS_STALE,
            "fixture authority stale",
        )
        projection = ViewerProjection(
            InMemoryGraphSource((), {}, {}),
            resolver=None,
            resolver_error=error,
        )
        with self.assertRaises(EventVisibilityError):
            self._query_jsonl(
                viewer=Viewer(ALICE, PRIVATE_ALICE),
                projection=projection,
            )

    def test_validator_enforces_closed_usage_and_old_type_segment_contract(self) -> None:
        self.assertIn(USAGE, emit_event.REGISTERED_TYPES)
        self.assertIn(USAGE, event_validators.REGISTERED_TYPES)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events_dir = root / "vault" / "events"
            events_dir.mkdir(parents=True)
            event_path = events_dir / "00-events.jsonl"

            valid = _event(1, USAGE, segment=TEAM)
            event_path.write_text(json.dumps(valid) + "\n", encoding="utf-8")
            findings, checked, defects = event_validators.run_all_event_checks(root)
            self.assertEqual(checked, 1)
            self.assertEqual(defects, 0)
            self.assertFalse(any(item.check_id == "event-24" for item in findings))

            invalid = json.loads(json.dumps(valid))
            invalid["data"]["extra"] = True
            event_path.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
            findings, _, defects = event_validators.run_all_event_checks(root)
            self.assertGreater(defects, 0)
            self.assertTrue(any(item.check_id == "event-24" for item in findings))

            old_segmented = _event(1, "tropo.message.sent")
            old_segmented["segment"] = TEAM
            event_path.write_text(
                json.dumps(old_segmented) + "\n",
                encoding="utf-8",
            )
            findings, _, defects = event_validators.run_all_event_checks(root)
            self.assertGreater(defects, 0)
            self.assertTrue(any(item.check_id == "event-24" for item in findings))

    def test_capsule_cli_and_ast_scope_are_bounded(self) -> None:
        capsule = (ROOT / "vault" / "capsules" / "tropo-events.capsule.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("version: '1.10'", capsule)
        self.assertIn("I approve the bounded events", capsule)
        self.assertIn(USAGE, capsule)

        emitter_tree = ast.parse(
            (TOOLS / "tropo-emit-event.py").read_text(encoding="utf-8")
        )
        cli_flags = {
            node.args[0].value
            for node in ast.walk(emitter_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        self.assertNotIn("--segment", cli_flags)
        self.assertNotIn("--segment-attestation", cli_flags)

        query_tree = ast.parse(
            (TOOLS / "tropo-query-events.py").read_text(encoding="utf-8")
        )
        query_cli_flags = {
            node.args[0].value
            for node in ast.walk(query_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        self.assertNotIn("--viewer-principal-uid", query_cli_flags)
        self.assertNotIn("--viewer-private-segment-uid", query_cli_flags)

        production = (
            TOOLS / "lib" / "capture_segment.py",
            TOOLS / "lib" / "distiller_capture.py",
            TOOLS / "lib" / "event_visibility.py",
        )
        forbidden_import_roots = {
            "anthropic",
            "openai",
            "requests",
            "httpx",
            "urllib",
        }
        for path in production:
            with self.subTest(path=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                imports = {
                    alias.name.split(".", 1)[0]
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names
                }
                calls = {
                    node.func.id
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                }
                self.assertFalse(imports & forbidden_import_roots)
                self.assertNotIn("orient", calls)
                self.assertNotIn("distill", calls)


if __name__ == "__main__":
    unittest.main()
