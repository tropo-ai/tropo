"""Strict partition, attestation, append, and immutable-receipt plants."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import event_identity  # noqa: E402
from lib.capture_segment import derive_capture_segment  # noqa: E402
from lib.distiller_capture import (  # noqa: E402
    CaptureReceipt,
    CaptureUsageError,
    USAGE_EVENT_TYPE,
    capture_usage,
)
from lib.group_registry import GroupResolver  # noqa: E402


TEAM = "a0000001"
PRIVATE = "a0000002"
TASK = "b0000001"
VIEWER = "c0000001"


def _load_emitter():
    spec = importlib.util.spec_from_file_location(
        "usage_capture_emitter_test",
        TOOLS / "tropo-emit-event.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolver() -> GroupResolver:
    return GroupResolver(
        {
            TEAM: {
                "group_uid": TEAM,
                "direct_member_uids": (VIEWER,),
                "effective_member_uids": (VIEWER,),
                "wider_group_uids": (),
            },
            PRIVATE: {
                "group_uid": PRIVATE,
                "direct_member_uids": (VIEWER,),
                "effective_member_uids": (VIEWER,),
                "wider_group_uids": (TEAM,),
            },
        },
        revision="fixture",
    )


class CountingEmitter:
    def __init__(self, delegate=None) -> None:
        self.delegate = delegate
        self.calls = 0
        self.arguments: list[dict] = []

    def __call__(self, **kwargs):
        self.calls += 1
        self.arguments.append(kwargs)
        if self.delegate is None:
            return {"id": "00000001"}
        return self.delegate(**kwargs)


class DistillerCaptureTests(unittest.TestCase):
    def _valid(self, emitter):
        return capture_usage(
            TASK,
            VIEWER,
            "fixture-snapshot-1",
            "distill",
            ("chunk-a", "chunk-b", "chunk-c"),
            ("chunk-a", "chunk-c"),
            ("chunk-b",),
            segment_of_chunk={
                "chunk-a": TEAM,
                "chunk-b": PRIVATE,
                "chunk-c": TEAM,
            },
            resolver=_resolver(),
            strict_emitter=emitter,
        )

    def test_partition_and_input_refusals_make_zero_emitter_calls(self) -> None:
        cases = (
            ((), (), ()),
            (("a", "a"), ("a",), ()),
            (("a", "b"), ("a", "a"), ("b",)),
            (("a", "b"), ("a",), ("a", "b")),
            (("a", "b"), ("a",), ()),
            (("a", "b"), ("a",), ("b", "extra")),
            (("a", "b", "c"), ("c", "a"), ("b",)),
            (("a", "b", "c"), ("a",), ("c", "b")),
        )
        for ranked, used, unused in cases:
            with self.subTest(ranked=ranked, used=used, unused=unused):
                emitter = CountingEmitter()
                with self.assertRaises(CaptureUsageError):
                    capture_usage(
                        TASK,
                        VIEWER,
                        "snapshot",
                        "distill",
                        ranked,
                        used,
                        unused,
                        segment_of_chunk={uid: TEAM for uid in ranked},
                        resolver=_resolver(),
                        strict_emitter=emitter,
                    )
                self.assertEqual(emitter.calls, 0)

        malformed = (
            ("bad-task", VIEWER, "snapshot", "distill"),
            (TASK, "bad-viewer", "snapshot", "distill"),
            (TASK, VIEWER, "", "distill"),
            (TASK, VIEWER, "snapshot", "orient"),
        )
        for task, viewer, snapshot, operation in malformed:
            with self.subTest(values=(task, viewer, snapshot, operation)):
                emitter = CountingEmitter()
                with self.assertRaises(CaptureUsageError):
                    capture_usage(
                        task,
                        viewer,
                        snapshot,
                        operation,
                        ("a",),
                        ("a",),
                        (),
                        segment_of_chunk={"a": TEAM},
                        resolver=_resolver(),
                        strict_emitter=emitter,
                    )
                self.assertEqual(emitter.calls, 0)

    def test_every_derivation_refusal_precedes_emitter(self) -> None:
        mappings = (
            {},
            {"chunk-a": ""},
            {"chunk-a": "afffffff"},
        )
        for mapping in mappings:
            with self.subTest(mapping=mapping):
                emitter = CountingEmitter()
                with self.assertRaises(CaptureUsageError):
                    capture_usage(
                        TASK,
                        VIEWER,
                        "snapshot",
                        "distill",
                        ("chunk-a",),
                        ("chunk-a",),
                        (),
                        segment_of_chunk=mapping,
                        resolver=_resolver(),
                        strict_emitter=emitter,
                    )
                self.assertEqual(emitter.calls, 0)

        emitter = CountingEmitter()
        with self.assertRaises(CaptureUsageError):
            capture_usage(
                TASK,
                VIEWER,
                "snapshot",
                "distill",
                ("chunk-a", "chunk-b"),
                ("chunk-a",),
                ("chunk-b",),
                segment_of_chunk={
                    "chunk-a": PRIVATE,
                    "chunk-b": "a0000003",
                },
                resolver=GroupResolver(
                    {
                        PRIVATE: {
                            "wider_group_uids": (TEAM,),
                            "direct_member_uids": (),
                            "effective_member_uids": (),
                        },
                        "a0000003": {
                            "wider_group_uids": (TEAM,),
                            "direct_member_uids": (),
                            "effective_member_uids": (),
                        },
                        TEAM: {
                            "wider_group_uids": (),
                            "direct_member_uids": (),
                            "effective_member_uids": (),
                        },
                    },
                    revision="fixture",
                ),
                strict_emitter=emitter,
            )
        self.assertEqual(emitter.calls, 0)

    def test_forged_missing_extra_and_old_type_segments_refuse_before_write(self) -> None:
        emitter = _load_emitter()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "vault" / "events"
            emitter.VAULT_ROOT = root
            emitter.EVENTS_DIR = events
            emitter.JSONL_PATH = events / "00-events.jsonl"
            emitter.SQLITE_PATH = events / "00-events-index.sqlite"
            emitter.AGENTS_DIR = root / "vault" / "agents"
            attestation = derive_capture_segment(
                ("chunk-a",),
                {"chunk-a": TEAM},
                _resolver(),
            )
            data = {
                "task_uid": TASK,
                "viewer_principal_uid": VIEWER,
                "index_as_of": "snapshot",
                "operation": "distill",
                "used_chunk_uids": ["chunk-a"],
                "unused_chunk_uids": [],
            }
            attempts = (
                dict(segment=PRIVATE, segment_attestation=attestation),
                dict(segment=None, segment_attestation=attestation),
                dict(segment=TEAM, segment_attestation=None),
            )
            for kwargs in attempts:
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(ValueError):
                        emitter.emit(
                            USAGE_EVENT_TYPE,
                            "/tools/emit-event",
                            "ca90f098",
                            "evergreen",
                            subject=TASK,
                            data=data,
                            strict=True,
                            **kwargs,
                        )
                    self.assertFalse(events.exists())

            with self.assertRaises(ValueError):
                emitter.emit(
                    USAGE_EVENT_TYPE,
                    "/tools/emit-event",
                    "ca90f098",
                    "evergreen",
                    subject=TASK,
                    data={**data, "extra": True},
                    strict=True,
                    segment=TEAM,
                    segment_attestation=attestation,
                )
            self.assertFalse(events.exists())

            for old_type in sorted(emitter.REGISTERED_TYPES - {USAGE_EVENT_TYPE}):
                with self.subTest(old_type=old_type):
                    with self.assertRaises(ValueError):
                        emitter.emit(
                            old_type,
                            "/tools/emit-event",
                            "ca90f098",
                            "evergreen",
                            segment=TEAM,
                            segment_attestation=attestation,
                            strict=True,
                        )
                    self.assertFalse(events.exists())

            argv = [
                "tropo-emit-event.py",
                "--type",
                USAGE_EVENT_TYPE,
                "--source",
                "/tools/emit-event",
                "--source-uid",
                "ca90f098",
                "--lifecycle",
                "evergreen",
            ]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(emitter.main(), 1)
            self.assertFalse(events.exists())

    def test_valid_capture_exactly_appends_in_legacy_and_stream_modes(self) -> None:
        for stream_mode in (False, True):
            with self.subTest(stream_mode=stream_mode):
                emitter = _load_emitter()
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    events = root / "vault" / "events"
                    events.mkdir(parents=True)
                    legacy = events / "00-events.jsonl"
                    legacy.write_text("", encoding="utf-8")
                    sqlite_path = events / "00-events-index.sqlite"
                    with sqlite3.connect(sqlite_path) as conn:
                        emitter._ensure_sqlite(conn)
                    emitter.VAULT_ROOT = root
                    emitter.EVENTS_DIR = events
                    emitter.JSONL_PATH = legacy
                    emitter.SQLITE_PATH = sqlite_path
                    emitter.AGENTS_DIR = root / "vault" / "agents"
                    counting = CountingEmitter(emitter.emit)
                    patches = (
                        mock.patch.object(
                            emitter.event_identity,
                            "streams_enabled",
                            return_value=stream_mode,
                        ),
                        mock.patch.object(
                            emitter.event_identity,
                            "derive_writer_instance_uid",
                            return_value="0123456789abcdef",
                        ),
                    )
                    with patches[0], patches[1]:
                        first = self._valid(counting)
                        self.assertIsInstance(first, CaptureReceipt)
                        records = event_identity.load_event_union_records(root)
                        self.assertEqual(len(records), 1)
                        event = records[0]["event"]
                        first_raw = records[0]["raw"]
                        self.assertEqual(first.event_uid, records[0]["event_uid"])
                        self.assertEqual(event["type"], USAGE_EVENT_TYPE)
                        self.assertEqual(event["lifecycle"], "evergreen")
                        self.assertEqual(event["subject"], TASK)
                        self.assertEqual(event["segment"], PRIVATE)
                        self.assertEqual(
                            tuple(event["data"]),
                            (
                                "task_uid",
                                "viewer_principal_uid",
                                "index_as_of",
                                "operation",
                                "used_chunk_uids",
                                "unused_chunk_uids",
                            ),
                        )
                        self.assertEqual(counting.calls, 1)
                        with sqlite3.connect(sqlite_path) as conn:
                            row = conn.execute(
                                "SELECT event_uid, raw FROM events"
                            ).fetchone()
                        self.assertEqual(row, (first.event_uid, first_raw))

                        second = self._valid(counting)
                        self.assertNotEqual(second.event_uid, first.event_uid)
                        records_after = event_identity.load_event_union_records(root)
                        self.assertEqual(len(records_after), 2)
                        self.assertEqual(records_after[0]["raw"], first_raw)
                        self.assertEqual(counting.calls, 2)
                        with sqlite3.connect(sqlite_path) as conn:
                            self.assertEqual(
                                conn.execute(
                                    "SELECT COUNT(*) FROM events"
                                ).fetchone()[0],
                                2,
                            )


if __name__ == "__main__":
    unittest.main()
