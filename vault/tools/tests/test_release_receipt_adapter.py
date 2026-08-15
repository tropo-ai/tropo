"""Hostile plants for the lean verify-live public release receipt cycle.

All writes use temporary roots and all publisher network-facing behavior is
mocked.  Content hashes provide tamper evidence inside governed-main write
access; these tests make no cryptographic-authentication claim.
"""

from __future__ import annotations

import copy
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
sys.path.insert(0, str(TOOLS))


def _load_publisher():
    spec = importlib.util.spec_from_file_location(
        "release_receipt_test_publisher", TOOLS / "tropo-publish-release.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load release publisher")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


publisher = _load_publisher()
from lib import public_snapshot, release_receipt  # noqa: E402


VERSION = "9.8.7"
TAG = f"v{VERSION}"
PUBLIC_URL = f"https://github.com/tropo-ai/tropo/releases/tag/{TAG}"
REMOTE_SHA = "c" * 40
PUBLISHED_AT = "2026-07-18T01:02:03Z"


def _receipt(**overrides) -> dict:
    values = {
        "version": VERSION,
        "tag": TAG,
        "public_url": PUBLIC_URL,
        "remote_main_sha": REMOTE_SHA,
        "remote_tag_sha": REMOTE_SHA,
        "release_object_tag": TAG,
        "release_object_url": PUBLIC_URL,
        "release_object_published_at": PUBLISHED_AT,
        "release_object_is_draft": False,
        "published_at": PUBLISHED_AT,
        "verify_live_at": PUBLISHED_AT,
    }
    values.update(overrides)
    return release_receipt.make_release_receipt(**values)


def _write_raw_receipt(root: Path, payload: bytes, *, filename: str | None = None) -> Path:
    directory = root / release_receipt.RECEIPTS_RELATIVE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    path = directory / (filename or f"{digest}.json")
    path.write_bytes(payload)
    return path


def _release_observation(**overrides) -> dict:
    value = {
        "release_object_tag": TAG,
        "release_object_url": PUBLIC_URL,
        "release_object_published_at": PUBLISHED_AT,
        "release_object_is_draft": False,
    }
    value.update(overrides)
    return value


def _append_mock_event(root: Path, data: dict, *, event_id: int = 1, **overrides) -> None:
    event = {
        "id": f"{event_id:08d}",
        "specversion": "1.0",
        "type": "tropo.release.published",
        "source": release_receipt.PUBLISHER_TOOL_SOURCE,
        "time": "2026-07-18T01:03:00Z",
        "source_uid": release_receipt.PUBLISHER_TOOL_UID,
        "lifecycle": "evergreen",
        "data": data,
    }
    event.update(overrides)
    path = root / "vault" / "events" / "00-events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def _event(
    receipt: dict,
    digest: str,
    *,
    event_id: int = 1,
    source_uid: str = release_receipt.PUBLISHER_TOOL_UID,
    event_type: str = "tropo.release.published",
    data_overrides: dict | None = None,
    envelope_overrides: dict | None = None,
) -> dict:
    data = {
        "version": receipt["version"],
        "tag": receipt["tag"],
        "public_url": receipt["public_url"],
        "published_at": receipt["published_at"],
        "receipt_sha256": digest,
    }
    data.update(data_overrides or {})
    value = {
        "id": f"{event_id:08d}",
        "specversion": "1.0",
        "type": event_type,
        "source": release_receipt.PUBLISHER_TOOL_SOURCE,
        "time": f"2026-07-18T01:03:{event_id:02d}Z",
        "source_uid": source_uid,
        "lifecycle": "evergreen",
        "data": data,
    }
    value.update(envelope_overrides or {})
    return value


def _records(events: list[dict]) -> list[dict]:
    return [
        {
            "event_uid": public_snapshot.event_identity.immutable_event_uid(event),
            "event": event,
            "source_path": "vault/events/test.jsonl",
        }
        for event in events
    ]


def _snapshot(events: list[dict], receipts: dict[str, dict]):
    return public_snapshot.build_public_snapshot(
        _records(events),
        {},
        source_commit="a" * 40,
        generated_at="2026-07-18T02:00:00Z",
        release_receipts=receipts,
    )


class ReleaseReceiptPrimitiveTests(unittest.TestCase):
    def test_canonical_content_address_and_idempotent_atomic_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = _receipt()
            digest = release_receipt.write_release_receipt(root, receipt)
            target = (
                root
                / release_receipt.RECEIPTS_RELATIVE_DIR
                / f"{digest}.json"
            )
            payload = target.read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)
            self.assertEqual(
                payload,
                release_receipt.canonical_json_bytes(receipt),
            )
            self.assertTrue(payload.endswith(b"\n"))
            self.assertNotIn("receipt_id", receipt)
            first_stat = target.stat()
            self.assertEqual(
                release_receipt.write_release_receipt(root, copy.deepcopy(receipt)),
                digest,
            )
            second_stat = target.stat()
            self.assertEqual(first_stat.st_ino, second_stat.st_ino)
            self.assertEqual(first_stat.st_mtime_ns, second_stat.st_mtime_ns)
            self.assertEqual(
                release_receipt.load_release_receipts(root),
                {digest: receipt},
            )

    def test_exact_schema_constants_and_strict_proof_values(self) -> None:
        valid = _receipt()
        mutations = {
            "unknown/private field": lambda value: value.update(
                {"staged_sha": "PRIVATE_CANARY"}
            ),
            "wrong uid": lambda value: value.update(
                {"publisher_tool_uid": "123e12e7"}
            ),
            "wrong source": lambda value: value.update(
                {"publisher_tool_source": "/tools/spoof"}
            ),
            "wrong repository": lambda value: value.update(
                {"repository": "attacker/repo"}
            ),
            "wrong kind": lambda value: value.update({"receipt_kind": "other"}),
            "tag target mismatch": lambda value: value.update(
                {"remote_tag_sha": "d" * 40}
            ),
            "wrong release tag": lambda value: value.update(
                {"release_object_tag": "v1.0.0"}
            ),
            "wrong release URL": lambda value: value.update(
                {
                    "release_object_url": (
                        "https://github.com/tropo-ai/tropo/releases/tag/v1.0.0"
                    )
                }
            ),
            "draft release": lambda value: value.update(
                {"release_object_is_draft": True}
            ),
            "non-boolean draft": lambda value: value.update(
                {"release_object_is_draft": 0}
            ),
            "release publishedAt mismatch": lambda value: value.update(
                {"release_object_published_at": "2026-07-18T01:02:02Z"}
            ),
            "leading-v version": lambda value: value.update({"version": f"v{VERSION}"}),
            "wrong tag": lambda value: value.update({"tag": VERSION}),
            "wrong url": lambda value: value.update(
                {"public_url": PUBLIC_URL + "?private=1"}
            ),
            "uppercase sha": lambda value: value.update(
                {"remote_main_sha": REMOTE_SHA.upper()}
            ),
            "offset timestamp": lambda value: value.update(
                {"published_at": "2026-07-18T01:02:03+00:00"}
            ),
            "stale proof": lambda value: value.update(
                {
                    "published_at": "2026-07-18T01:02:04Z",
                    "verify_live_at": "2026-07-18T01:02:03Z",
                }
            ),
        }
        for label, mutate in mutations.items():
            candidate = copy.deepcopy(valid)
            mutate(candidate)
            with self.subTest(label=label):
                with self.assertRaises(release_receipt.ReleaseReceiptError):
                    release_receipt.validate_release_receipt(candidate)

    def test_duplicate_keys_noncanonical_bytes_hash_drift_and_wrong_filename_refuse(
        self,
    ) -> None:
        valid_payload = release_receipt.canonical_json_bytes(_receipt())
        duplicate_payload = (
            valid_payload[:-2]
            + b',"schema_version":"1.0.0"}\n'
        )
        plants = [
            (duplicate_payload, None),
            (json.dumps(_receipt(), indent=2).encode("utf-8") + b"\n", None),
            (valid_payload + b" ", None),
            (valid_payload, f"{'0' * 64}.json"),
        ]
        for index, (payload, filename) in enumerate(plants):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _write_raw_receipt(root, payload, filename=filename)
                with self.assertRaises(release_receipt.ReleaseReceiptError):
                    release_receipt.load_release_receipts(root)

    def test_conflicting_receipt_for_same_version_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = _receipt()
            release_receipt.write_release_receipt(root, first)
            conflict = _receipt(
                remote_main_sha="d" * 40,
                remote_tag_sha="d" * 40,
            )
            with self.assertRaisesRegex(
                release_receipt.ReleaseReceiptError, "version conflict"
            ):
                release_receipt.write_release_receipt(root, conflict)
            self.assertEqual(len(release_receipt.load_release_receipts(root)), 1)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for candidate in (
                _receipt(),
                _receipt(
                    remote_main_sha="d" * 40,
                    remote_tag_sha="d" * 40,
                ),
            ):
                _write_raw_receipt(
                    root,
                    release_receipt.canonical_json_bytes(candidate),
                )
            with self.assertRaisesRegex(
                release_receipt.ReleaseReceiptError, "version conflict"
            ):
                release_receipt.load_release_receipts(root)

    def test_symlink_hardlink_fifo_and_directory_aliases_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            digest = release_receipt.write_release_receipt(root, _receipt())
            target = (
                root / release_receipt.RECEIPTS_RELATIVE_DIR / f"{digest}.json"
            )
            os.link(target, root / "receipt-hardlink")
            with self.assertRaisesRegex(
                release_receipt.ReleaseReceiptError, "unlinked regular file"
            ):
                release_receipt.load_release_receipts(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = release_receipt.canonical_json_bytes(_receipt())
            external = root / "external.json"
            external.write_bytes(payload)
            directory = root / release_receipt.RECEIPTS_RELATIVE_DIR
            directory.mkdir(parents=True)
            digest = hashlib.sha256(payload).hexdigest()
            (directory / f"{digest}.json").symlink_to(external)
            with self.assertRaises(release_receipt.ReleaseReceiptError):
                release_receipt.load_release_receipts(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / release_receipt.RECEIPTS_RELATIVE_DIR
            directory.mkdir(parents=True)
            os.mkfifo(directory / f"{'0' * 64}.json")
            with self.assertRaises(release_receipt.ReleaseReceiptError):
                release_receipt.load_release_receipts(root)

        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "root"
            root.mkdir()
            external = parent / "external-receipts"
            external.mkdir()
            events = root / "vault" / "events"
            events.mkdir(parents=True)
            (events / "release-receipts").symlink_to(
                external, target_is_directory=True
            )
            with self.assertRaisesRegex(
                release_receipt.ReleaseReceiptError, "aliases|real directories"
            ):
                release_receipt.load_release_receipts(root)

        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            real_root = parent / "real-root"
            real_root.mkdir()
            alias = parent / "root-alias"
            alias.symlink_to(real_root, target_is_directory=True)
            with self.assertRaisesRegex(
                release_receipt.ReleaseReceiptError, "aliases"
            ):
                release_receipt.load_release_receipts(alias)

    def test_writer_recovers_its_strict_pre_and_post_link_crash_temporaries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = _receipt()
            payload = release_receipt.canonical_json_bytes(receipt)
            digest = release_receipt.receipt_sha256(receipt)
            directory = root / release_receipt.RECEIPTS_RELATIVE_DIR
            directory.mkdir(parents=True)
            pre_link = directory / f".{digest}.999.{'a' * 16}.tmp"
            pre_link.write_bytes(payload)
            self.assertEqual(
                release_receipt.write_release_receipt(root, receipt),
                digest,
            )
            self.assertFalse(pre_link.exists())

            target = directory / f"{digest}.json"
            post_link = directory / f".{digest}.999.{'b' * 16}.tmp"
            os.link(target, post_link)
            self.assertEqual(target.stat().st_nlink, 2)
            self.assertEqual(
                release_receipt.write_release_receipt(root, receipt),
                digest,
            )
            self.assertFalse(post_link.exists())
            self.assertEqual(target.stat().st_nlink, 1)


class PublisherObservationTests(unittest.TestCase):
    def _completed(self, value: dict | None = None, *, error: str = ""):
        if value is None:
            return types.SimpleNamespace(
                returncode=1,
                stdout="",
                stderr=error,
            )
        return types.SimpleNamespace(
            returncode=0,
            stdout=json.dumps(value),
            stderr="",
        )

    def test_release_view_is_repo_pinned_and_returns_exact_observations(self) -> None:
        value = {
            "tagName": TAG,
            "url": PUBLIC_URL,
            "isDraft": False,
            "publishedAt": PUBLISHED_AT,
        }
        with patch.object(
            publisher.subprocess,
            "run",
            return_value=self._completed(value),
        ) as run:
            observed = publisher._view_release_object(
                TAG,
                Path("/temporary/mock-clone"),
                allow_missing=False,
            )
        self.assertEqual(observed, _release_observation())
        self.assertEqual(
            run.call_args.args[0],
            [
                "gh",
                "release",
                "view",
                TAG,
                "--repo",
                "github.com/tropo-ai/tropo",
                "--json",
                "tagName,url,isDraft,publishedAt",
            ],
        )

    def test_hostile_gh_host_cannot_change_view_or_create_command_target(
        self,
    ) -> None:
        value = {
            "tagName": TAG,
            "url": PUBLIC_URL,
            "isDraft": False,
            "publishedAt": PUBLISHED_AT,
        }
        with (
            patch.dict(os.environ, {"GH_HOST": "attacker.example.invalid"}),
            patch.object(
                publisher.subprocess,
                "run",
                side_effect=[
                    self._completed(value),
                    self._completed({}),
                ],
            ) as run,
        ):
            publisher._view_release_object(
                TAG,
                Path("/temporary/mock-clone"),
                allow_missing=False,
            )
            publisher._create_release_object(
                TAG,
                Path("/temporary/release.zip"),
                VERSION,
                Path("/temporary/mock-clone"),
            )
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(
            commands[0][commands[0].index("--repo") + 1],
            "github.com/tropo-ai/tropo",
        )
        self.assertEqual(
            commands[1][commands[1].index("--repo") + 1],
            "github.com/tropo-ai/tropo",
        )
        self.assertNotIn("attacker.example.invalid", json.dumps(commands))
        self.assertEqual(publisher.CANONICAL_REPOSITORY, "tropo-ai/tropo")
        self.assertEqual(
            publisher.CANONICAL_GH_REPOSITORY,
            "github.com/tropo-ai/tropo",
        )

    def test_release_view_rejects_draft_wrong_tag_url_or_published_at(self) -> None:
        valid = {
            "tagName": TAG,
            "url": PUBLIC_URL,
            "isDraft": False,
            "publishedAt": PUBLISHED_AT,
        }
        plants = [
            {**valid, "tagName": "v1.0.0"},
            {**valid, "url": PUBLIC_URL + "?draft=1"},
            {**valid, "isDraft": True},
            {**valid, "publishedAt": ""},
            {key: value for key, value in valid.items() if key != "publishedAt"},
        ]
        for value in plants:
            with self.subTest(value=value), patch.object(
                publisher.subprocess,
                "run",
                return_value=self._completed(value),
            ):
                with self.assertRaises(publisher.PublishError):
                    publisher._view_release_object(
                        TAG,
                        Path("/temporary/mock-clone"),
                        allow_missing=False,
                    )

    def test_missing_release_is_only_tolerated_for_explicit_create_probe(self) -> None:
        missing = self._completed(error="release not found")
        with patch.object(publisher.subprocess, "run", return_value=missing):
            self.assertIsNone(
                publisher._view_release_object(
                    TAG,
                    Path("/temporary/mock-clone"),
                    allow_missing=True,
                )
            )
            with self.assertRaises(publisher.PublishError):
                publisher._view_release_object(
                    TAG,
                    Path("/temporary/mock-clone"),
                    allow_missing=False,
                )

    def test_wrong_remote_and_existing_clone_origin_refuse(self) -> None:
        with self.assertRaises(publisher.PublishError):
            publisher._require_pinned_remote(
                "https://github.com/attacker/tropo.git"
            )
        with patch.object(
            publisher,
            "_git",
            return_value=types.SimpleNamespace(
                returncode=0,
                stdout="https://github.com/attacker/tropo.git\n",
            ),
        ):
            with self.assertRaisesRegex(publisher.PublishError, "origin"):
                publisher._require_clone_origin(
                    Path("/temporary/existing-clone"),
                    publisher.DEFAULT_REMOTE,
                )


class PublisherReceiptTests(unittest.TestCase):
    def _proof(self, **overrides) -> dict:
        value = {
            "status": "verified",
            "expect": VERSION,
            "tag": TAG,
            "expected_sha": REMOTE_SHA,
            "remote_main_sha": REMOTE_SHA,
            "remote_tag_sha": REMOTE_SHA,
        }
        value.update(overrides)
        return value

    def _state(self) -> dict:
        return {
            "version": VERSION,
            "tag": TAG,
            "staged_sha": REMOTE_SHA,
        }

    def _patches(self, root: Path):
        return (
            patch.multiple(
                publisher.tropo_roots,
                STUDIO_ROOT=root,
                VAULT_DIR=root / "vault",
            ),
            patch.object(
                publisher.tropo_roots,
                "RELEASES_DIR",
                root / "private-releases",
            ),
            patch.object(
                publisher,
                "_find_release_entry",
                return_value=(root / "vault/files/release.md", {"uid": "deadbeef"}),
            ),
            patch.object(publisher, "_utc_timestamp", return_value=PUBLISHED_AT),
        )

    def test_partial_proof_has_no_receipt_event_or_private_state_side_effect(self) -> None:
        cases = [
            (self._proof(status="not_verified"), True),
            (self._proof(remote_tag_sha="d" * 40), True),
            (self._proof(remote_main_sha="d" * 40), True),
            (self._proof(expected_sha="d" * 40), True),
            (self._proof(), False),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patch.object(publisher, "_emit_published_event") as emit,
            ):
                for proof, release_object_present in cases:
                    with self.subTest(proof=proof, release=release_object_present):
                        with self.assertRaises(publisher.PublishError):
                            publisher._finalize_verified_publication(
                                VERSION,
                                self._state(),
                                proof,
                                release_observation=(
                                    _release_observation()
                                    if release_object_present
                                    else _release_observation(
                                        release_object_is_draft=True
                                    )
                                ),
                            )
            self.assertFalse(
                (root / release_receipt.RECEIPTS_RELATIVE_DIR).exists()
            )
            self.assertFalse((root / "private-releases").exists())
            emit.assert_not_called()

    def test_full_green_emits_public_only_data_and_refire_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self._state()
            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patch.dict(os.environ, {"USER": "PRIVATE_FIRED_BY_CANARY"}),
                patch.object(
                    publisher,
                    "_emit_published_event",
                    side_effect=lambda data: _append_mock_event(root, data),
                ) as emit,
            ):
                receipt, digest, _ = publisher._finalize_verified_publication(
                    VERSION,
                    state,
                    self._proof(),
                    release_observation=_release_observation(),
                )
                again, again_digest, _ = publisher._finalize_verified_publication(
                    VERSION,
                    state,
                    self._proof(),
                    release_observation=_release_observation(),
                )
            self.assertEqual((again, again_digest), (receipt, digest))
            emit.assert_called_once()
            event_data = emit.call_args.args[0]
            self.assertEqual(
                set(event_data),
                {"version", "tag", "public_url", "published_at", "receipt_sha256"},
            )
            self.assertEqual(event_data["receipt_sha256"], digest)
            serialized_event = json.dumps(event_data)
            for private_canary in (
                "deadbeef",
                REMOTE_SHA,
                "PRIVATE_FIRED_BY_CANARY",
                "staged_sha",
                "release_uid",
                "fired_by",
            ):
                self.assertNotIn(private_canary, serialized_event)
            private_state = json.loads(
                (
                    root
                    / "private-releases"
                    / f"v{VERSION}"
                    / publisher.STATE_FILE_NAME
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(private_state["release_uid"], "deadbeef")
            self.assertEqual(private_state["staged_sha"], REMOTE_SHA)
            self.assertEqual(
                private_state["fired_by"], "PRIVATE_FIRED_BY_CANARY"
            )
            self.assertEqual(private_state["receipt_sha256"], digest)
            self.assertEqual(
                release_receipt.load_release_receipts(root),
                {digest: receipt},
            )

    def test_rerun_days_later_reuses_github_timestamp_and_receipt_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self._state()
            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patch.object(
                    publisher,
                    "_utc_timestamp",
                    side_effect=[
                        "2026-07-18T02:00:00Z",
                        "2026-07-21T02:00:00Z",
                    ],
                ),
                patch.object(
                    publisher,
                    "_emit_published_event",
                    side_effect=lambda data: _append_mock_event(root, data),
                ) as emit,
            ):
                first, first_digest, _ = publisher._finalize_verified_publication(
                    VERSION,
                    state,
                    self._proof(),
                    release_observation=_release_observation(),
                )
                second, second_digest, _ = (
                    publisher._finalize_verified_publication(
                        VERSION,
                        state,
                        self._proof(),
                        release_observation=_release_observation(),
                    )
                )
            self.assertEqual(first_digest, second_digest)
            self.assertEqual(first, second)
            self.assertEqual(first["published_at"], PUBLISHED_AT)
            self.assertEqual(first["verify_live_at"], "2026-07-18T02:00:00Z")
            emit.assert_called_once()

    def test_append_then_emitter_error_is_recovered_without_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self._state()
            patches = self._patches(root)

            def append_then_raise(data):
                _append_mock_event(root, data)
                raise RuntimeError("crash after append")

            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patch.object(
                    publisher,
                    "_emit_published_event",
                    side_effect=append_then_raise,
                ) as emit,
            ):
                receipt, digest, _ = publisher._finalize_verified_publication(
                    VERSION,
                    state,
                    self._proof(),
                    release_observation=_release_observation(),
                )
                _, rerun_digest, _ = publisher._finalize_verified_publication(
                    VERSION,
                    state,
                    self._proof(),
                    release_observation=_release_observation(),
                )
            self.assertEqual(rerun_digest, digest)
            self.assertEqual(receipt["published_at"], PUBLISHED_AT)
            emit.assert_called_once()
            lines = (
                root / "vault" / "events" / "00-events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

    def test_state_write_failure_recovers_existing_event_without_reemit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_state = self._state()
            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patch.object(
                    publisher,
                    "_emit_published_event",
                    side_effect=lambda data: _append_mock_event(root, data),
                ) as emit,
                patch.object(
                    publisher,
                    "_write_state",
                    side_effect=OSError("planted state failure"),
                ),
            ):
                with self.assertRaisesRegex(publisher.PublishError, "private state"):
                    publisher._finalize_verified_publication(
                        VERSION,
                        first_state,
                        self._proof(),
                        release_observation=_release_observation(),
                    )
            emit.assert_called_once()

            fresh_state = self._state()
            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patch.object(publisher, "_emit_published_event") as emit_again,
            ):
                _, digest, _ = publisher._finalize_verified_publication(
                    VERSION,
                    fresh_state,
                    self._proof(),
                    release_observation=_release_observation(),
                )
            emit_again.assert_not_called()
            self.assertEqual(
                fresh_state["published_event_receipt_sha256"],
                digest,
            )

    def test_conflicting_or_duplicate_receipt_events_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self._state()
            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patch.object(
                    publisher,
                    "_emit_published_event",
                    side_effect=lambda data: _append_mock_event(root, data),
                ),
            ):
                receipt, digest, _ = publisher._finalize_verified_publication(
                    VERSION,
                    state,
                    self._proof(),
                    release_observation=_release_observation(),
                )
                _append_mock_event(
                    root,
                    publisher._published_event_data(digest, receipt),
                    event_id=2,
                )
                with self.assertRaisesRegex(
                    publisher.PublishError, "more than one event"
                ):
                    publisher._finalize_verified_publication(
                        VERSION,
                        state,
                        self._proof(),
                        release_observation=_release_observation(),
                    )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = _receipt()
            digest = release_receipt.write_release_receipt(root, receipt)
            _append_mock_event(
                root,
                publisher._published_event_data(digest, receipt),
                source_uid="123e12e7",
            )
            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
            ):
                with self.assertRaisesRegex(
                    publisher.PublishError, "conflicting data or labels"
                ):
                    publisher._finalize_verified_publication(
                        VERSION,
                        self._state(),
                        self._proof(),
                        release_observation=_release_observation(),
                    )

    def test_concurrent_threads_serialize_to_one_receipt_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patch.object(
                    publisher,
                    "_emit_published_event",
                    side_effect=lambda data: _append_mock_event(root, data),
                ) as emit,
            ):
                def finalize():
                    return publisher._finalize_verified_publication(
                        VERSION,
                        self._state(),
                        self._proof(),
                        release_observation=_release_observation(),
                    )

                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(lambda _index: finalize(), range(2)))
            self.assertEqual(results[0][1], results[1][1])
            emit.assert_called_once()
            self.assertEqual(
                len(
                    (
                        root / "vault" / "events" / "00-events.jsonl"
                    ).read_text(encoding="utf-8").splitlines()
                ),
                1,
            )

    def test_receipt_failure_prevents_event_and_event_failure_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self._state()
            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patch.object(
                    publisher.release_receipt,
                    "write_release_receipt",
                    side_effect=release_receipt.ReleaseReceiptError("planted"),
                ),
                patch.object(publisher, "_emit_published_event") as emit,
            ):
                with self.assertRaises(release_receipt.ReleaseReceiptError):
                    publisher._finalize_verified_publication(
                        VERSION,
                        state,
                        self._proof(),
                        release_observation=_release_observation(),
                    )
            emit.assert_not_called()
            self.assertNotIn("published_event_receipt_sha256", state)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self._state()
            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patch.object(
                    publisher,
                    "_emit_published_event",
                    side_effect=RuntimeError("planted emit failure"),
                ),
            ):
                with self.assertRaises(publisher.PublishError):
                    publisher._finalize_verified_publication(
                        VERSION,
                        state,
                        self._proof(),
                        release_observation=_release_observation(),
                    )
            committed = release_receipt.load_release_receipts(root)
            self.assertEqual(len(committed), 1)
            self.assertNotIn("published_event_receipt_sha256", state)

            patches = self._patches(root)
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patch.object(
                    publisher,
                    "_emit_published_event",
                    side_effect=lambda data: _append_mock_event(root, data),
                ) as emit,
            ):
                _, recovered_digest, _ = publisher._finalize_verified_publication(
                    VERSION,
                    state,
                    self._proof(),
                    release_observation=_release_observation(),
                )
            emit.assert_called_once()
            self.assertEqual(recovered_digest, next(iter(committed)))

    def test_canonical_emitter_writes_only_to_temporary_event_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / "vault" / "tools"
            lib = tools / "lib"
            lib.mkdir(parents=True)
            shutil.copy2(TOOLS / "tropo-emit-event.py", tools)
            shutil.copy2(TOOLS / "lib" / "event_identity.py", lib)
            receipt = _receipt()
            digest = release_receipt.receipt_sha256(receipt)
            data = publisher._published_event_data(digest, receipt)
            with patch.multiple(
                publisher.tropo_roots,
                STUDIO_ROOT=root,
                VAULT_DIR=root / "vault",
            ):
                publisher._emit_published_event(data)
            lines = (
                root / "vault" / "events" / "00-events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            event = json.loads(lines[0])
            self.assertEqual(event["type"], "tropo.release.published")
            self.assertEqual(
                event["source_uid"], release_receipt.PUBLISHER_TOOL_UID
            )
            self.assertEqual(event["data"], data)

    def test_cmd_fire_receipt_failure_returns_nonzero_before_live_stamps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = {
                **self._state(),
                "activation_uid": "deadbeef",
                "clone_dir": str(root / "staged-clone"),
                "remote": publisher.DEFAULT_REMOTE,
            }

            def fake_git(arguments, cwd, check=True, timeout=120):
                if arguments == ["rev-parse", "HEAD"]:
                    stdout = f"{REMOTE_SHA}\n"
                elif arguments == ["remote", "get-url", "origin"]:
                    stdout = f"{publisher.DEFAULT_REMOTE}\n"
                else:
                    stdout = ""
                return types.SimpleNamespace(stdout=stdout, returncode=0)

            completed = types.SimpleNamespace(returncode=0, stdout="", stderr="")
            with (
                patch.multiple(
                    publisher.tropo_roots,
                    STUDIO_ROOT=root,
                    VAULT_DIR=root / "vault",
                ),
                patch.object(
                    publisher.tropo_roots,
                    "RELEASES_DIR",
                    root / "private-releases",
                ),
                patch.object(publisher, "_read_state", return_value=state),
                patch.object(publisher, "_confirm_tty", return_value=True),
                patch.object(
                    publisher,
                    "_require_cold_walk_clearance",
                    return_value={
                        "release_version": VERSION,
                        "overall": "PASS",
                    },
                ),
                patch.object(publisher, "require_release_authorization"),
                patch.object(publisher, "_git", side_effect=fake_git),
                patch.object(publisher.subprocess, "run", return_value=completed),
                patch.object(publisher, "_upload_supabase_zip"),
                patch.object(publisher, "_upload_update_manifest"),
                patch.object(
                    publisher,
                    "_verify_published_update_manifest",
                    return_value={
                        "current": VERSION,
                        "updates": [{"version": VERSION}],
                    },
                ) as verify_manifest,
                patch.object(publisher, "_run_publish_state", return_value=self._proof()),
                patch.object(
                    publisher,
                    "_view_release_object",
                    return_value=_release_observation(),
                ),
                patch.object(
                    publisher,
                    "_find_release_entry",
                    return_value=(root / "release.md", {"uid": "deadbeef"}),
                ),
                patch.object(
                    publisher.release_receipt,
                    "write_release_receipt",
                    side_effect=publisher.release_receipt.ReleaseReceiptError(
                        "planted receipt failure"
                    ),
                ),
                patch.object(publisher, "_emit_published_event") as emit,
                patch.object(publisher, "_stamp_release_entry") as stamp,
                # Stage 6 put the AC7 receipt-set gate ahead of everything in
                # cmd_fire, so without this every fire test refuses at the gate
                # and stops exercising its own subject. This case is about what
                # happens when the RECEIPT WRITE fails much later; that the gate
                # is wired at all is proved in test_ac07_publish_receipt_gate,
                # and asserting it twice here would only mean this test fails
                # for two unrelated reasons.
                # Stage 6: cmd_fire now CONSUMES what this gate returns — the
                # identity chain and frozen digest go into the v2 receipt — so
                # patching it to a bare mock makes the fire fail early on the
                # context rather than on this test's subject. Returns a usable
                # context; that the gate is wired is proved in
                # test_ac07_publish_receipt_gate.
                patch.object(publisher, "require_ac7_receipt_set",
                             return_value={
                                 "identity": types.SimpleNamespace(
                                     activation_uid="acc00001",
                                     run_uid="b0000001",
                                     plan_uid="c0000001",
                                     root_uid="d0000001",
                                     fan_in_digest="d" * 64),
                                 "package_sha256": "c" * 64,
                                 "receipts": {}}),
                patch.object(publisher, "_release_entry_uid_for",
                             return_value="e0000001"),
            ):
                result = publisher.cmd_fire(types.SimpleNamespace(version=VERSION))
            self.assertEqual(result, 14)
            verify_manifest.assert_called_once_with(VERSION)
            emit.assert_not_called()
            stamp.assert_not_called()
            self.assertFalse((root / ".tropo" / "version.md").exists())


class ReceiptBackedSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = _receipt()
        self.digest = release_receipt.receipt_sha256(self.receipt)
        self.receipts = {self.digest: self.receipt}

    def test_exact_label_spoof_without_receipt_and_wrong_labels_yield_zero(self) -> None:
        valid_event = _event(self.receipt, self.digest)
        candidates = [
            (valid_event, {}),
            (
                _event(
                    self.receipt,
                    self.digest,
                    source_uid="123e12e7",
                ),
                self.receipts,
            ),
            (
                _event(
                    self.receipt,
                    self.digest,
                    event_type="tropo.release.shipped",
                ),
                self.receipts,
            ),
            (
                _event(
                    self.receipt,
                    "0" * 64,
                ),
                self.receipts,
            ),
            (
                _event(
                    self.receipt,
                    self.digest,
                    envelope_overrides={"specversion": "0.3"},
                ),
                self.receipts,
            ),
        ]
        for event, receipts in candidates:
            with self.subTest(event=event):
                self.assertEqual(_snapshot([event], receipts).release_facts["facts"], [])

    def test_matching_event_projects_only_receipt_fields(self) -> None:
        first = _event(self.receipt, self.digest, event_id=1)
        bundle = _snapshot([first], self.receipts)
        self.assertEqual(len(bundle.release_facts["facts"]), 1)
        fact = bundle.release_facts["facts"][0]
        self.assertEqual(
            fact,
            {
                "public_fact_id": public_snapshot.derive_public_fact_id(
                    {
                        "type": "tropo.release.published",
                        "occurred_at": PUBLISHED_AT,
                        "version": VERSION,
                        "tag": TAG,
                        "public_url": PUBLIC_URL,
                    }
                ),
                "type": "tropo.release.published",
                "occurred_at": PUBLISHED_AT,
                "version": VERSION,
                "tag": TAG,
                "public_url": PUBLIC_URL,
            },
        )
        self.assertEqual(public_snapshot.EXPORTER_VERSION, "1.1.0")
        public_bytes = b"".join(bundle.files.values()).decode("utf-8")
        for private_canary in (
            REMOTE_SHA,
            self.digest,
            "source_uid",
            "event_uid",
            "receipt_sha256",
        ):
            self.assertNotIn(private_canary, public_bytes)

    def test_two_events_for_one_receipt_refuse_instead_of_deduping(self) -> None:
        first = _event(self.receipt, self.digest, event_id=1)
        second = _event(self.receipt, self.digest, event_id=2)
        for events in ([second, first], [copy.deepcopy(first), first]):
            with self.subTest(events=events), self.assertRaisesRegex(
                public_snapshot.SnapshotContractError,
                "more than one event points",
            ):
                _snapshot(events, self.receipts)

    def test_event_receipt_mismatch_and_private_fields_withhold(self) -> None:
        plants = [
            _event(
                self.receipt,
                self.digest,
                data_overrides={"version": "1.0.0"},
            ),
            _event(
                self.receipt,
                self.digest,
                data_overrides={"published_at": "2026-07-18T01:02:04Z"},
            ),
            _event(
                self.receipt,
                self.digest,
                data_overrides={"private_canary": "PRIVATE_EVENT_CANARY"},
            ),
            _event(
                self.receipt,
                self.digest,
                envelope_overrides={"subject": "PRIVATE_SUBJECT_CANARY"},
            ),
        ]
        for event in plants:
            with self.subTest(event=event):
                bundle = _snapshot([event], self.receipts)
                self.assertEqual(bundle.release_facts["facts"], [])
                output = b"".join(bundle.files.values()).decode("utf-8")
                self.assertNotIn("PRIVATE_EVENT_CANARY", output)
                self.assertNotIn("PRIVATE_SUBJECT_CANARY", output)

    def test_invalid_mapping_and_malformed_committed_receipt_fail_closed(self) -> None:
        with self.assertRaises(public_snapshot.SnapshotContractError):
            _snapshot([_event(self.receipt, self.digest)], {"0" * 64: self.receipt})

        conflict = _receipt(
            remote_main_sha="d" * 40,
            remote_tag_sha="d" * 40,
        )
        conflict_digest = release_receipt.receipt_sha256(conflict)
        with self.assertRaises(public_snapshot.SnapshotContractError):
            _snapshot(
                [_event(self.receipt, self.digest)],
                {
                    self.digest: self.receipt,
                    conflict_digest: conflict,
                },
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = root / "vault" / "events"
            events.mkdir(parents=True)
            (events / "00-events.jsonl").write_text("", encoding="utf-8")
            _write_raw_receipt(
                root,
                release_receipt.canonical_json_bytes(self.receipt) + b"drift",
            )
            with self.assertRaisesRegex(
                public_snapshot.SnapshotContractError,
                "committed release receipts are invalid",
            ):
                public_snapshot.discover_public_snapshot(
                    root,
                    source_commit="a" * 40,
                    generated_at="2026-07-18T02:00:00Z",
                )

    def test_raw_candidate_event_duplicate_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            digest = release_receipt.write_release_receipt(root, self.receipt)
            events = root / "vault" / "events"
            events.mkdir(parents=True, exist_ok=True)
            raw = (
                '{"id":"00000001","type":"tropo.release.published",'
                '"source":"/tools/publish-release","source_uid":"15cae798",'
                '"lifecycle":"evergreen","data":{'
                f'"receipt_sha256":"{digest}",'
                f'"receipt_sha256":"{digest}"'
                "}}\n"
            )
            (events / "00-events.jsonl").write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(
                public_snapshot.SnapshotContractError,
                "duplicate key",
            ):
                public_snapshot.discover_public_snapshot(
                    root,
                    source_commit="a" * 40,
                    generated_at="2026-07-18T02:00:00Z",
                )

    def test_same_pointer_event_repeated_across_event_sources_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            digest = release_receipt.write_release_receipt(root, self.receipt)
            event = _event(self.receipt, digest)
            raw = json.dumps(event, separators=(",", ":")) + "\n"
            events = root / "vault" / "events"
            streams = events / "streams"
            streams.mkdir(parents=True, exist_ok=True)
            (events / "00-events.jsonl").write_text(raw, encoding="utf-8")
            (streams / "writer.jsonl").write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(
                public_snapshot.SnapshotContractError,
                "duplicate release receipt pointer event",
            ):
                public_snapshot.discover_public_snapshot(
                    root,
                    source_commit="a" * 40,
                    generated_at="2026-07-18T02:00:00Z",
                )


class LeanTrustBoundaryDocumentationTests(unittest.TestCase):
    def test_governed_docs_name_schema_and_deny_crypto_authentication(self) -> None:
        required_fields = sorted(release_receipt.RECEIPT_FIELDS)
        for uid in (
            "756eceab",
            "79e40093",
            "7832274c",
            "20495aaf",
            "eb8e65c8",
        ):
            text = (ROOT / "vault" / "files" / f"{uid}.md").read_text(
                encoding="utf-8"
            )
            with self.subTest(uid=uid):
                self.assertIn("not cryptographic authentication", text.lower())
                self.assertIn(
                    "governance-authorized, hash-consistent publisher assertion "
                    "given trusted main checkout",
                    text.lower(),
                )
                for field in required_fields:
                    self.assertIn(f"`{field}`", text)


if __name__ == "__main__":
    unittest.main()

