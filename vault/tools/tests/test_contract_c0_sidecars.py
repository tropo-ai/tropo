"""Focused Contract-C0 folder-sidecar codec plants.

Center of gravity: the mandatory, profile-independent payload-path floor. The
staged codec delegated ALL path-syntax checks to an OPTIONAL PortabilityValidator,
so validating a record with ``portability_validator=None`` accepted traversal,
absolute, backslash, drive, reserved-namespace, empty-segment, and dot/dot-dot
paths (the P0). These plants prove the floor now refuses unconditionally while
the injected authority still layers host policy on top, plus canonical round-trip,
base64 integrity, root emptiness, and a bijection orphan plant.
"""

from __future__ import annotations

import base64
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "vault" / "tools" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import folder_sidecar as fs  # noqa: E402


REGISTRY = {"document"}
PAYLOAD_SHA = hashlib.sha256(b"payload-body").hexdigest()


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _file_record(
    path: str = "docs/report.md",
    *,
    key: str | None = None,
    bytes_b64: str | None = None,
) -> dict:
    return {
        "schema_id": fs.SCHEMA_ID,
        "schema_version": fs.SCHEMA_VERSION,
        "record_kind": "file",
        "uid": "aaaaaaaa",
        "parent_uid": "bbbbbbbb",
        "payload_path": path,
        "payload_path_bytes_b64": _b64(path) if bytes_b64 is None else bytes_b64,
        "payload_portability_key": path if key is None else key,
        "payload_profile": "text",
        "payload_type": "document",
        "status": "active",
        "state": "active",
        "owner_uid": "cccccccc",
        "audience_group_uid": "dddddddd",
        "extraction_scope": "argo-reference",
        "relations": [{"predicate": "member_of", "target_uid": "bbbbbbbb"}],
        "created": {"at": "2026-07-18", "precision": "day", "by": "argus-a134"},
        "modified": {"at": "2026-07-18", "precision": "day", "by": "argus-a134"},
        "payload_sha256": PAYLOAD_SHA,
    }


def _root_record(*, key: str = "") -> dict:
    return {
        "schema_id": fs.SCHEMA_ID,
        "schema_version": fs.SCHEMA_VERSION,
        "record_kind": "directory",
        "uid": "aaaaaaaa",
        "parent_uid": "ab12",
        "payload_path": "",
        "payload_path_bytes_b64": "",
        "payload_portability_key": key,
        "payload_profile": "directory",
        "payload_type": "document",
        "status": "active",
        "state": "active",
        "owner_uid": "cccccccc",
        "audience_group_uid": "dddddddd",
        "extraction_scope": "argo-reference",
        "relations": [{"predicate": "member_of", "target_uid": "ab12"}],
        "created": {"at": "2026-07-18", "precision": "day", "by": "argus-a134"},
        "modified": {"at": "2026-07-18", "precision": "day", "by": "argus-a134"},
    }


def _validate(record: dict, **kwargs):
    return fs.validate_record(
        record,
        registered_payload_types=REGISTRY,
        **kwargs,
    )


class MandatoryPathFloorTests(unittest.TestCase):
    """The floor refuses illegal paths even with NO injected validator."""

    ILLEGAL_PATHS = (
        "../escape",          # traversal
        "a/../b",             # embedded dot-dot
        "/etc/passwd",        # absolute
        "a\\b",               # backslash
        "c:/x",               # drive prefix
        ".git/config",        # reserved namespace
        ".tropo/x",           # reserved namespace
        ".tropo-studio/x",    # legacy reserved namespace
        "a//b",               # empty/repeated separator
        "a/./b",              # dot segment
        "a/",                 # trailing separator
        "a\x00b",             # NUL
        "\x1fname",           # control character
    )

    def test_illegal_paths_refuse_without_portability_validator(self) -> None:
        for path in self.ILLEGAL_PATHS:
            with self.subTest(path=path):
                record = _file_record(path)
                with self.assertRaises(fs.C0ValidationError) as ctx:
                    _validate(record, portability_validator=None)
                self.assertEqual(ctx.exception.code, fs.C0_PATH_INVALID)

    def test_illegal_portability_key_refuses(self) -> None:
        # A valid path but a traversal-bearing portability key still refuses;
        # the key is subject to the same floor because it feeds path joins.
        record = _file_record("docs/report.md", key="../escape")
        with self.assertRaises(fs.C0ValidationError) as ctx:
            _validate(record, portability_validator=None)
        self.assertEqual(ctx.exception.code, fs.C0_PATH_INVALID)


class Base64AndRootIntegrityTests(unittest.TestCase):
    def test_base64_must_encode_the_declared_path(self) -> None:
        record = _file_record("docs/report.md", bytes_b64=_b64("other/path.md"))
        with self.assertRaises(fs.C0ValidationError) as ctx:
            _validate(record, portability_validator=None)
        self.assertEqual(ctx.exception.code, fs.C0_PATH_INVALID)

    def test_root_record_requires_empty_key(self) -> None:
        record = _root_record(key="x")
        with self.assertRaises(fs.C0ValidationError) as ctx:
            _validate(record, portability_validator=None)
        self.assertEqual(ctx.exception.code, fs.C0_PATH_INVALID)


class PositivePathTests(unittest.TestCase):
    def test_valid_file_record_passes_without_validator(self) -> None:
        record = _validate(_file_record("docs/report.md"), portability_validator=None)
        self.assertEqual(record.payload_path, "docs/report.md")

    def test_valid_root_record_passes(self) -> None:
        record = _validate(_root_record(), portability_validator=None)
        self.assertTrue(record.is_root)

    def test_canonical_round_trip_is_byte_stable(self) -> None:
        record = _validate(_file_record("docs/report.md"), portability_validator=None)
        raw = fs.canonical_record_bytes(record)
        reparsed = fs.parse_record(raw, registered_payload_types=REGISTRY)
        self.assertEqual(reparsed.payload_path, "docs/report.md")
        self.assertEqual(fs.canonical_record_bytes(reparsed), raw)


class InjectedValidatorStillLayeredTests(unittest.TestCase):
    """The floor does not replace the injected authority — both run."""

    def test_injected_validator_can_still_refuse_a_syntactically_valid_path(self) -> None:
        def reject(_path: str, _key: str, _is_root: bool) -> bool:
            return False

        record = _file_record("docs/report.md")
        with self.assertRaises(fs.C0ValidationError) as ctx:
            _validate(record, portability_validator=reject)
        self.assertEqual(ctx.exception.code, fs.C0_PATH_INVALID)

    def test_injected_validator_key_mismatch_refuses(self) -> None:
        def expect_other(_path: str, _key: str, _is_root: bool) -> str:
            return "different-key"

        record = _file_record("docs/report.md")
        with self.assertRaises(fs.C0ValidationError) as ctx:
            _validate(record, portability_validator=expect_other)
        self.assertEqual(ctx.exception.code, fs.C0_PATH_INVALID)

    def test_illegal_path_refuses_before_injected_validator_runs(self) -> None:
        calls: list[str] = []

        def record_calls(path: str, _key: str, _is_root: bool) -> bool:
            calls.append(path)
            return True

        record = _file_record("../escape")
        with self.assertRaises(fs.C0ValidationError):
            _validate(record, portability_validator=record_calls)
        self.assertEqual(calls, [])


class BijectionOrphanTests(unittest.TestCase):
    def test_physical_payload_without_a_sidecar_is_an_orphan(self) -> None:
        orphan = fs.PayloadEntry.file_hash("stray.md", PAYLOAD_SHA, "stray.md")
        with self.assertRaises(fs.C0VerificationError) as ctx:
            fs.verify_bijection(
                records=[],
                payloads=[orphan],
                vault_uid="ab12",
                registered_payload_types=REGISTRY,
            )
        self.assertTrue(
            any(finding.code == fs.C0_PAYLOAD_ORPHAN for finding in ctx.exception.findings)
        )


if __name__ == "__main__":
    unittest.main()
