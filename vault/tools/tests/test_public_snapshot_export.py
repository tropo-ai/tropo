"""Adversarial coverage for web-v4 public snapshot dev-spec 148dd9cc."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
CLI_SOURCE = TOOLS / "1a8be354.py"
VALIDATOR_SOURCE = TOOLS / "tropo-validate.py"
sys.path.insert(0, str(TOOLS))

from lib import public_snapshot  # noqa: E402


SOURCE_COMMIT = "a" * 40
GENERATED_AT = "2026-07-17T12:00:00Z"
PARTY_UID = "abcdef12"
PUBLISHER_UID = "123e12e7"
PUBLISHER_TOOL_UID = "15cae798"
PUBLISHER_SOURCE = "/tools/publish-release"
FIXTURE_SENTINEL = "tropo-public-snapshot-fixture-v1\n"
FIXTURE_ENV_NAME = "TROPO_PUBLIC_SNAPSHOT_TEST_FIXTURE"
IDENTITIES = {
    PARTY_UID: public_snapshot.AgentIdentity(name="Vela", generation="V7")
}


def _legacy_event(
    event_id: int,
    *,
    event_type: str = "tropo.release.published",
    version: object = "v1.2.3",
    source: str = PUBLISHER_SOURCE,
    source_uid: str = PUBLISHER_UID,
    data_extra: dict | None = None,
    envelope_extra: dict | None = None,
) -> dict:
    data = {"version": version}
    data.update(data_extra or {})
    event = {
        "id": f"{event_id:08d}",
        "specversion": "1.0",
        "type": event_type,
        "source": source,
        "time": f"2026-07-17T12:00:{event_id:02d}Z",
        "source_uid": source_uid,
        "lifecycle": "evergreen",
        "data": data,
    }
    event.update(envelope_extra or {})
    return event


def _stream_event(local_seq: int, **kwargs) -> dict:
    event = _legacy_event(local_seq, **kwargs)
    event_uid = f"evt_0123456789abcdef_{local_seq:08d}"
    event.update(
        {
            "id": event_uid,
            "event_uid": event_uid,
            "writer_instance_uid": "0123456789abcdef",
            "stream_uid": "fedcba9876543210",
            "local_seq": local_seq,
        }
    )
    return event


def _records(events: list[dict]) -> list[dict]:
    return [
        {
            "event_uid": public_snapshot.event_identity.immutable_event_uid(event),
            "event": event,
            "source_path": "vault/events/fixture.jsonl",
        }
        for event in events
    ]


def _build(
    events: list[dict],
    *,
    identities=IDENTITIES,
    validated_overrides=(),
    release_receipts=None,
) -> public_snapshot.SnapshotBundle:
    return public_snapshot.build_public_snapshot(
        _records(events),
        identities,
        source_commit=SOURCE_COMMIT,
        generated_at=GENERATED_AT,
        validated_overrides=validated_overrides,
        release_receipts=release_receipts,
    )


def _receipt(
    version: str = "1.2.3",
    *,
    published_at: str = GENERATED_AT,
) -> tuple[str, dict]:
    tag = f"v{version}"
    value = public_snapshot.release_receipt.make_release_receipt(
        version=version,
        tag=tag,
        public_url=f"https://github.com/tropo-ai/tropo/releases/tag/{tag}",
        remote_main_sha="b" * 40,
        remote_tag_sha="b" * 40,
        release_object_tag=tag,
        release_object_url=f"https://github.com/tropo-ai/tropo/releases/tag/{tag}",
        release_object_published_at=published_at,
        release_object_is_draft=False,
        published_at=published_at,
        verify_live_at=published_at,
    )
    digest = public_snapshot.release_receipt.receipt_sha256(value)
    return digest, value


def _receipt_event(event_id: int = 1, *, version: str = "1.2.3") -> tuple[dict, dict]:
    digest, receipt = _receipt(version)
    event = _legacy_event(
        event_id,
        version=version,
        source_uid=PUBLISHER_TOOL_UID,
        data_extra={
            "tag": receipt["tag"],
            "public_url": receipt["public_url"],
            "published_at": receipt["published_at"],
            "receipt_sha256": digest,
        },
    )
    return event, {digest: receipt}


def _project(
    event: dict,
    *,
    identities=IDENTITIES,
) -> tuple[dict | None, set[str]]:
    return public_snapshot._project_release_fact(_records([event])[0], identities)


def _write_agent(root: Path) -> None:
    agents = root / "vault" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / "agent.md").write_text(
        "---\n"
        "uid: 11112222\n"
        "type: agent\n"
        "title: Vela — Chief of Staff\n"
        "agent: vela\n"
        "generation: V7\n"
        f"party_uid: {PARTY_UID}\n"
        "---\n",
        encoding="utf-8",
    )


def _write_event_union(
    root: Path,
    legacy_events: list[dict],
    stream_files: dict[str, list[dict]] | None = None,
) -> None:
    events_dir = root / "vault" / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / "00-events.jsonl").write_text(
        "".join(
            json.dumps(event, separators=(",", ":")) + "\n"
            for event in legacy_events
        ),
        encoding="utf-8",
    )
    if stream_files:
        streams = events_dir / "streams"
        streams.mkdir(exist_ok=True)
        for name, events in stream_files.items():
            (streams / name).write_text(
                "".join(
                    json.dumps(event, separators=(",", ":")) + "\n"
                    for event in events
                ),
                encoding="utf-8",
            )


def _write_policy_sources(root: Path) -> None:
    files = root / "vault" / "files"
    files.mkdir(parents=True, exist_ok=True)
    (files / "20495aaf.md").write_text("fixture policy\n", encoding="utf-8")
    (files / "eb8e65c8.md").write_text("fixture contract\n", encoding="utf-8")


def _tree_hash(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _tree_state(root: Path) -> dict[str, tuple[int, int, int, int, str]]:
    state = {}
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if path.is_symlink():
            payload = f"link:{os.readlink(path)}"
        elif path.is_file():
            payload = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            payload = "directory"
        state[str(path.relative_to(root))] = (
            metadata.st_mode,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ino,
            payload,
        )
    return state


def _file_state(path: Path) -> tuple[bytes, int, int, int]:
    metadata = path.stat()
    return (
        path.read_bytes(),
        metadata.st_mtime_ns,
        metadata.st_ino,
        metadata.st_size,
    )


def _copy_cli_fixture(
    root: Path,
    events: list[dict] | None = None,
    *,
    release_receipts: dict[str, dict] | None = None,
) -> Path:
    subprocess.run(
        ["git", "init", "-q"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / ".tropo-public-snapshot-fixture").write_text(
        FIXTURE_SENTINEL,
        encoding="utf-8",
    )
    tools = root / "vault" / "tools"
    lib = tools / "lib"
    lib.mkdir(parents=True)
    (root / ".tropo").mkdir()
    shutil.copy2(CLI_SOURCE, tools / CLI_SOURCE.name)
    for name in ("tropo-publish-release.py", "tropo-check-publish-state.py"):
        shutil.copy2(TOOLS / name, tools / name)
    for name in (
        "public_snapshot.py",
        "event_identity.py",
        "release_receipt.py",
        "tropo_roots.py",
    ):
        shutil.copy2(TOOLS / "lib" / name, lib / name)
    _write_agent(root)
    _write_event_union(
        root,
        events
        if events is not None
        else [
            _legacy_event(1),
            _legacy_event(2, event_type="tropo.message.sent"),
        ],
    )
    _write_policy_sources(root)
    for expected_sha, receipt in (release_receipts or {}).items():
        actual_sha = public_snapshot.release_receipt.write_release_receipt(root, receipt)
        if actual_sha != expected_sha:
            raise AssertionError("fixture receipt hash did not re-derive")
    return tools / CLI_SOURCE.name


def _fixture_command(cli: Path, output: Path) -> list[str]:
    return [
        sys.executable,
        str(cli),
        "--out",
        str(output),
        "--fixture-mode",
        "--source-commit",
        SOURCE_COMMIT,
    ]


def _run(
    command: list[str],
    cwd: Path,
    *,
    seed: str | None = None,
    fixture_env: bool = True,
    environment_overrides: dict[str, str] | None = None,
):
    environment = dict(os.environ)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    if fixture_env:
        environment[FIXTURE_ENV_NAME] = "1"
    else:
        environment.pop(FIXTURE_ENV_NAME, None)
    if seed is not None:
        environment["PYTHONHASHSEED"] = seed
    if environment_overrides:
        environment.update(environment_overrides)
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _write_bundle(directory: Path, bundle: public_snapshot.SnapshotBundle) -> None:
    directory.mkdir(parents=True)
    for name, payload in bundle.files.items():
        (directory / name).write_bytes(payload)


def _rehash_bundle_values(
    release: dict,
    manifest: dict,
    receipt: dict,
) -> dict[str, bytes]:
    release_payload = public_snapshot.canonical_json_bytes(release)
    release_descriptor = {
        "path": public_snapshot.RELEASE_FACTS_NAME,
        "sha256": hashlib.sha256(release_payload).hexdigest(),
        "bytes": len(release_payload),
        "records": len(release["facts"]),
    }
    receipt["crossed"]["release_facts"] = {
        "count": len(release["facts"]),
        "sha256": release_descriptor["sha256"],
    }
    receipt["data_bundle_sha256"] = public_snapshot.bundle_descriptor_sha256(
        [release_descriptor]
    )
    receipt_payload = public_snapshot.canonical_json_bytes(receipt)
    receipt_descriptor = {
        "path": public_snapshot.PRIVACY_RECEIPT_NAME,
        "sha256": hashlib.sha256(receipt_payload).hexdigest(),
        "bytes": len(receipt_payload),
        "records": 1,
    }
    manifest["artifacts"] = [release_descriptor, receipt_descriptor]
    manifest["bundle_sha256"] = public_snapshot.bundle_descriptor_sha256(
        manifest["artifacts"]
    )
    return {
        public_snapshot.RELEASE_FACTS_NAME: release_payload,
        public_snapshot.MANIFEST_NAME: public_snapshot.canonical_json_bytes(manifest),
        public_snapshot.PRIVACY_RECEIPT_NAME: receipt_payload,
    }


def _independent_validator_probe(bundle: Path) -> subprocess.CompletedProcess:
    code = (
        "import importlib.util,sys; from pathlib import Path; "
        "p=Path(sys.argv[1]); s=importlib.util.spec_from_file_location('tv',p); "
        "m=importlib.util.module_from_spec(s); sys.modules['tv']=m; "
        "s.loader.exec_module(m); "
        "m._validate_public_snapshot_independent(Path(sys.argv[2]))"
    )
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-c", code, str(VALIDATOR_SOURCE), str(bundle)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _independent_url_matrix_probe(urls: list[str]) -> subprocess.CompletedProcess:
    code = (
        "import importlib.util,json,sys; from pathlib import Path; "
        "p=Path(sys.argv[1]); s=importlib.util.spec_from_file_location('tvu',p); "
        "m=importlib.util.module_from_spec(s); sys.modules['tvu']=m; "
        "s.loader.exec_module(m); "
        "bad=[]; "
        "\nfor u in json.loads(sys.argv[2]):\n"
        " try: m._ps_public_url(u,'1.2.3')\n"
        " except ValueError: continue\n"
        " bad.append(u)\n"
        "\nif bad: raise SystemExit('accepted invalid URLs: '+repr(bad))"
    )
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(VALIDATOR_SOURCE),
            json.dumps(urls),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _full_validator_contract_probe(vault: Path) -> subprocess.CompletedProcess:
    code = (
        "import importlib.util,json,sys; from pathlib import Path; "
        "p=Path(sys.argv[1]); s=importlib.util.spec_from_file_location('tvf',p); "
        "m=importlib.util.module_from_spec(s); sys.modules['tvf']=m; "
        "s.loader.exec_module(m); "
        "findings,checks,defects=m.check_public_snapshot_contract(Path(sys.argv[2])); "
        "print(json.dumps({'checks':checks,'defects':defects,"
        "'messages':[f.message for f in findings]})); "
        "raise SystemExit(1 if defects else 0)"
    )
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return subprocess.run(
        [sys.executable, "-c", code, str(VALIDATOR_SOURCE), str(vault)],
        cwd=vault,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


class ProjectionPrivacyTests(unittest.TestCase):
    def test_unknown_fields_withhold_entire_safe_type_before_body_parsing(self) -> None:
        clean = _legacy_event(
            1,
            data_extra={
                "tag": "v1.2.3",
                "public_url": (
                    "https://github.com/tropo-ai/tropo/releases/tag/v1.2.3"
                ),
            },
        )
        safe_type_private_body = _legacy_event(
            2,
            data_extra={"body": "PRIVATE_BODY_CANARY_620f"},
        )
        body_only = _legacy_event(3)
        body_only["data"] = {"body": "release-next PRIVATE_VERSION_CANARY_6210"}
        poisoned_invalid_version = _legacy_event(
            4,
            version="definitely-not-semver",
            data_extra={"body": "unknown-field-short-circuits-value-parsing"},
        )
        private_class = _legacy_event(
            5,
            event_type="tropo.message.sent",
            data_extra={"body": "PRIVATE_MESSAGE_CANARY_6211"},
        )

        bundle = _build(
            [
                private_class,
                poisoned_invalid_version,
                body_only,
                safe_type_private_body,
                clean,
            ]
        )
        self.assertEqual(bundle.release_facts["facts"], [])
        self.assertEqual(
            bundle.privacy_receipt["crossed"]["release_facts"]["count"],
            0,
        )
        self.assertEqual(
            {row["bucket"] for row in bundle.privacy_receipt["held_back"]},
            {
                "private-default",
                "unverified-release-emitter",
            },
        )
        output = b"".join(bundle.files.values()).decode("utf-8")
        for canary in (
            "PRIVATE_BODY_CANARY_620f",
            "PRIVATE_VERSION_CANARY_6210",
            "PRIVATE_MESSAGE_CANARY_6211",
        ):
            self.assertNotIn(canary, output)

    def test_projection_machinery_remains_ready_but_cannot_authorize_an_event(
        self,
    ) -> None:
        candidate = _legacy_event(
            1,
            data_extra={
                "tag": "v1.2.3",
                "public_url": (
                    "https://github.com/tropo-ai/tropo/releases/tag/v1.2.3"
                ),
            },
        )
        fact, projection_buckets = _project(candidate)
        self.assertIsNotNone(fact)
        assert fact is not None
        self.assertRegex(fact["public_fact_id"], r"^rf_[0-9a-f]{64}$")
        self.assertEqual(
            fact["public_fact_id"],
            public_snapshot.derive_public_fact_id(
                {key: value for key, value in fact.items() if key != "public_fact_id"}
            ),
        )
        self.assertEqual(projection_buckets, {"unresolved-public-signer"})

        bundle = _build([candidate])
        self.assertEqual(bundle.release_facts["facts"], [])
        self.assertEqual(
            {row["bucket"] for row in bundle.privacy_receipt["held_back"]},
            {"unverified-release-emitter"},
        )

    def test_only_matching_receipt_projects_fact_from_receipt_fields(self) -> None:
        event, receipts = _receipt_event()
        event["time"] = "2026-07-18T23:59:59Z"
        bundle = _build([event], release_receipts=receipts)
        self.assertEqual(
            bundle.release_facts["facts"],
            [
                {
                    "public_fact_id": public_snapshot.derive_public_fact_id(
                        {
                            "type": "tropo.release.published",
                            "occurred_at": GENERATED_AT,
                            "version": "1.2.3",
                            "tag": "v1.2.3",
                            "public_url": (
                                "https://github.com/tropo-ai/tropo/releases/tag/v1.2.3"
                            ),
                        }
                    ),
                    "type": "tropo.release.published",
                    "occurred_at": GENERATED_AT,
                    "version": "1.2.3",
                    "tag": "v1.2.3",
                    "public_url": (
                        "https://github.com/tropo-ai/tropo/releases/tag/v1.2.3"
                    ),
                }
            ],
        )
        self.assertNotIn("agent_name", bundle.release_facts["facts"][0])

        wrong_uid = copy.deepcopy(event)
        wrong_uid["source_uid"] = PUBLISHER_UID
        shipped = copy.deepcopy(event)
        shipped["type"] = "tropo.release.shipped"
        mismatch = copy.deepcopy(event)
        mismatch["data"]["published_at"] = "2026-07-18T00:00:00Z"
        for candidate, candidate_receipts in (
            (event, {}),
            (wrong_uid, receipts),
            (shipped, receipts),
            (mismatch, receipts),
        ):
            with self.subTest(candidate=candidate):
                self.assertEqual(
                    _build(
                        [candidate], release_receipts=candidate_receipts
                    ).release_facts["facts"],
                    [],
                )

    def test_bundle_roots_exclude_governed_policy_uid_and_bound_commit(self) -> None:
        bundle = _build([_legacy_event(1)])
        self.assertEqual(
            set(bundle.release_facts),
            {"schema_version", "facts"},
        )
        self.assertEqual(
            set(bundle.manifest),
            {
                "schema_version",
                "policy",
                "policy_version",
                "generated_at",
                "artifacts",
                "bundle_sha256",
            },
        )
        self.assertEqual(bundle.manifest["policy"], "public-crew-snapshot")
        self.assertEqual(
            set(bundle.privacy_receipt),
            {
                "schema_version",
                "policy",
                "policy_version",
                "exporter_version",
                "data_bundle_sha256",
                "crossed",
                "held_back",
                "overrides_consumed",
            },
        )
        self.assertEqual(
            bundle.privacy_receipt["policy"], "public-crew-snapshot"
        )
        self.assertEqual(bundle.bound_source_commit, SOURCE_COMMIT)
        public_bytes = b"".join(bundle.files.values()).decode("utf-8")
        self.assertNotIn("20495aaf", public_bytes)
        self.assertNotIn(SOURCE_COMMIT, public_bytes)
        self.assertNotIn("policy_uid", public_bytes)
        self.assertNotIn("source_commit", public_bytes)

    def test_private_event_identity_and_join_canaries_never_cross(self) -> None:
        event = _stream_event(1)
        event["source"] = "/private/source/IDENTITY_PATH_CANARY"
        record = {
            "event_uid": event["event_uid"],
            "event": event,
            "source_path": "vault/events/streams/PRIVATE_PATH_CANARY.jsonl",
        }
        bundle = public_snapshot.build_public_snapshot(
            [record],
            IDENTITIES,
            source_commit=SOURCE_COMMIT,
            generated_at=GENERATED_AT,
        )
        output = b"".join(bundle.files.values()).decode("utf-8")
        for canary in (
            event["event_uid"],
            "0123456789abcdef",
            "fedcba9876543210",
            PARTY_UID,
            PUBLISHER_UID,
            "20495aaf",
            SOURCE_COMMIT,
            "IDENTITY_PATH_CANARY",
            "PRIVATE_PATH_CANARY",
            "legacy_00000001",
        ):
            self.assertNotIn(canary, output)
        self.assertNotIn("event_uid", output)
        self.assertNotIn("writer_instance_uid", output)
        self.assertNotIn("stream_uid", output)
        self.assertNotIn("local_seq", output)

    def test_projection_can_omit_unresolved_signer_but_v1_withholds_event(
        self,
    ) -> None:
        unresolved = _legacy_event(1)
        fact, projection_buckets = _project(unresolved)
        self.assertIsNotNone(fact)
        assert fact is not None
        self.assertNotIn("agent_name", fact)
        self.assertNotIn("agent_generation", fact)
        self.assertEqual(projection_buckets, {"unresolved-public-signer"})

        bundle = _build([unresolved])
        self.assertEqual(bundle.release_facts["facts"], [])
        self.assertNotIn(
            PUBLISHER_UID, b"".join(bundle.files.values()).decode("utf-8")
        )
        self.assertIn(
            {
                "bucket": "unverified-release-emitter",
                "reason": public_snapshot.HELD_BACK_POLICY[
                    "unverified-release-emitter"
                ],
            },
            bundle.privacy_receipt["held_back"],
        )

    def test_v1_empty_provenance_set_withholds_every_publisher_label_shape(
        self,
    ) -> None:
        actual_data = {
            "release_uid": "deadbeef",
            "tag": "v1.2.3",
            "staged_sha": "b" * 40,
            "fired_by": "mike-maziarz",
            "published_at": "2026-07-17T12:00:00Z",
        }
        candidates = {
            "exact-spoof-labels": _legacy_event(1),
            "canonical-tool-uid": _legacy_event(
                2,
                source_uid=PUBLISHER_TOOL_UID,
            ),
            "actual-publisher-payload": _legacy_event(
                3,
                data_extra=actual_data,
            ),
            "registry-required-extensions": _legacy_event(
                4,
                data_extra=actual_data,
                envelope_extra={
                    "vault_refs": ["deadbeef"],
                    "severity": "info",
                },
            ),
        }
        self.assertEqual(public_snapshot.VERIFIED_RELEASE_EMITTERS, frozenset())
        for label, candidate in candidates.items():
            with self.subTest(label=label):
                bundle = _build([candidate])
                self.assertEqual(bundle.release_facts["facts"], [])
                self.assertEqual(
                    bundle.privacy_receipt["crossed"]["release_facts"]["count"],
                    0,
                )
                self.assertEqual(
                    {row["bucket"] for row in bundle.privacy_receipt["held_back"]},
                    {"unverified-release-emitter"},
                )
                public_bytes = b"".join(bundle.files.values()).decode("utf-8")
                for private_value in (
                    PUBLISHER_SOURCE,
                    PUBLISHER_UID,
                    PUBLISHER_TOOL_UID,
                    "deadbeef",
                    "mike-maziarz",
                    "staged_sha",
                    "vault_refs",
                    "severity",
                ):
                    self.assertNotIn(private_value, public_bytes)

    def test_invalid_semver_tag_and_urls_refuse(self) -> None:
        base = "https://github.com/tropo-ai/tropo/releases/tag/v1.2.3"
        invalid_urls = [
            "http://github.com/tropo-ai/tropo/releases/tag/v1.2.3",
            "https://github.com/tropo-ai/tropo/issues/1",
            "https://github.com:443/tropo-ai/tropo/releases/tag/v1.2.3",
            "https://user@github.com/tropo-ai/tropo/releases/tag/v1.2.3",
            "https://github.com/tropo-ai/tropo/releases/tag/v9.9.9",
            f"{base}?x=1",
            f"{base}#fragment",
            f"{base}?",
            f"{base}#",
            f" {base}",
            f"{base} ",
            f"{base}\n",
            f"{base}\r",
            f"{base}\t",
            f"{base}\x1f",
            f"{base}\x7f",
            "https://github.com/tropo-ai/tropo/releases/tag/v1.2 .3",
            "https://github.com.evil/tropo-ai/tropo/releases/tag/v1.2.3",
            "https://github．com/tropo-ai/tropo/releases/tag/v1.2.3",
            "HTTPS://github.com/tropo-ai/tropo/releases/tag/v1.2.3",
        ]
        cases = [
            _legacy_event(1, version="release-next"),
            _legacy_event(2, version="01.2.3"),
            _legacy_event(3, data_extra={"tag": "v9.9.9"}),
        ] + [
            _legacy_event(index + 4, data_extra={"public_url": url})
            for index, url in enumerate(invalid_urls)
        ]
        for event in cases:
            with self.subTest(event=event["id"]):
                with self.assertRaises(public_snapshot.SnapshotContractError):
                    _project(event)
                self.assertEqual(_build([event]).release_facts["facts"], [])
        independent = _independent_url_matrix_probe(invalid_urls)
        self.assertEqual(independent.returncode, 0, independent.stderr)

    def test_public_fact_id_matches_identical_dormant_public_projection(self) -> None:
        first = _legacy_event(1)
        second = _legacy_event(2)
        second["time"] = first["time"]
        first_fact, _ = _project(first)
        second_fact, _ = _project(second)
        self.assertEqual(first_fact, second_fact)
        self.assertIsNotNone(first_fact)
        bundle = _build([first, second])
        self.assertEqual(bundle.release_facts["facts"], [])
        self.assertEqual(
            bundle.privacy_receipt["crossed"]["release_facts"]["count"], 0
        )

    def test_input_order_is_byte_deterministic(self) -> None:
        events = [
            _legacy_event(3, event_type="tropo.message.sent"),
            _stream_event(2, event_type="tropo.release.published", version="2.1.0"),
            _legacy_event(1, data_extra={"private": "withheld"}),
        ]
        forward = _build(events)
        reverse = _build(list(reversed(events)))
        rotated = _build(events[1:] + events[:1])
        self.assertEqual(forward.files, reverse.files)
        self.assertEqual(forward.files, rotated.files)


class EventUnionTests(unittest.TestCase):
    def test_mixed_legacy_stream_union_dedupes_private_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_agent(root)
            legacy = _legacy_event(1)
            stream = _stream_event(
                2, event_type="tropo.release.published", version="2.0.0"
            )
            _write_event_union(
                root,
                [legacy],
                {"writer-a.jsonl": [stream], "writer-b.jsonl": [copy.deepcopy(stream)]},
            )
            bundle = public_snapshot.discover_public_snapshot(
                root, source_commit=SOURCE_COMMIT, generated_at=GENERATED_AT
            )
            self.assertEqual(bundle.release_facts["facts"], [])
            self.assertEqual(
                {row["bucket"] for row in bundle.privacy_receipt["held_back"]},
                {"unverified-release-emitter"},
            )
            self.assertEqual(
                set(bundle.source_event_paths),
                {
                    "vault/events/00-events.jsonl",
                    "vault/events/streams/writer-a.jsonl",
                },
            )

    def test_source_rederivation_uses_only_out_of_band_bound_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_agent(root)
            _write_event_union(root, [_legacy_event(1)])
            bundle = public_snapshot.discover_public_snapshot(
                root,
                source_commit=SOURCE_COMMIT,
                generated_at=GENERATED_AT,
            )
            with self.assertRaisesRegex(
                public_snapshot.SnapshotContractError,
                "out-of-band bound source commit",
            ):
                public_snapshot.validate_bundle_bytes(
                    bundle.files,
                    source_root=root,
                )
            result = public_snapshot.validate_bundle_bytes(
                bundle.files,
                source_root=root,
                bound_source_commit=SOURCE_COMMIT,
            )
            self.assertNotIn("source_commit", result)
            self.assertEqual(result["policy"], "public-crew-snapshot")

    def test_dual_read_identity_conflict_refuses_before_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_agent(root)
            stream = _stream_event(1, data_extra={"body": "private-a"})
            conflict = copy.deepcopy(stream)
            conflict["data"]["body"] = "private-b"
            _write_event_union(
                root,
                [],
                {"writer-a.jsonl": [stream], "writer-b.jsonl": [conflict]},
            )
            with self.assertRaisesRegex(
                public_snapshot.SnapshotContractError,
                "same identity, different content",
            ):
                public_snapshot.discover_public_snapshot(
                    root, source_commit=SOURCE_COMMIT, generated_at=GENERATED_AT
                )


class ReceiptAndOverrideTests(unittest.TestCase):
    def test_manifest_and_fixed_bucket_receipt_rederive(self) -> None:
        unresolved = _legacy_event(3)
        bundle = _build(
            [
                _legacy_event(1, data_extra={"private": "held"}),
                _legacy_event(2, event_type="tropo.message.sent"),
                unresolved,
            ]
        )
        summary = public_snapshot.validate_bundle_bytes(bundle.files)
        release_hash = hashlib.sha256(bundle.release_facts_bytes).hexdigest()
        artifact = bundle.manifest["artifacts"][0]
        self.assertEqual(
            artifact,
            {
                "path": "release-facts.json",
                "sha256": release_hash,
                "bytes": len(bundle.release_facts_bytes),
                "records": 0,
            },
        )
        receipt_descriptor = bundle.manifest["artifacts"][1]
        self.assertEqual(
            receipt_descriptor,
            {
                "path": "privacy-receipt.json",
                "sha256": hashlib.sha256(
                    bundle.privacy_receipt_bytes
                ).hexdigest(),
                "bytes": len(bundle.privacy_receipt_bytes),
                "records": 1,
            },
        )
        self.assertEqual(
            bundle.manifest["bundle_sha256"],
            public_snapshot.bundle_descriptor_sha256(
                bundle.manifest["artifacts"]
            ),
        )
        self.assertEqual(
            bundle.privacy_receipt["data_bundle_sha256"],
            public_snapshot.bundle_descriptor_sha256([artifact]),
        )
        self.assertEqual(bundle.privacy_receipt["policy_version"], "1.0.0")
        self.assertEqual(bundle.privacy_receipt["exporter_version"], "1.1.0")
        self.assertEqual(
            bundle.privacy_receipt["crossed"]["release_facts"],
            {"count": 0, "sha256": release_hash},
        )
        self.assertEqual(summary["release_facts_sha256"], release_hash)
        self.assertEqual(summary["overrides_consumed"], [])
        rows = bundle.privacy_receipt["held_back"]
        self.assertEqual(
            {row["bucket"] for row in rows},
            {
                "private-default",
                "unverified-release-emitter",
            },
        )
        for row in rows:
            self.assertEqual(set(row), {"bucket", "reason"})
            self.assertEqual(
                row["reason"], public_snapshot.HELD_BACK_POLICY[row["bucket"]]
            )
        receipt_text = bundle.privacy_receipt_bytes.decode("utf-8")
        self.assertNotIn('"class"', receipt_text)
        self.assertNotIn("tropo.message.sent", receipt_text)
        self.assertNotIn('"count":2', receipt_text)

    def test_detached_receipt_edit_and_deletion_fail_standalone(self) -> None:
        bundle = _build(
            [_legacy_event(1), _legacy_event(2, event_type="tropo.message.sent")]
        )
        edited_receipt = copy.deepcopy(bundle.privacy_receipt)
        edited_receipt["held_back"].append(
            {
                "bucket": "malformed-public-candidate",
                "reason": public_snapshot.HELD_BACK_POLICY[
                    "malformed-public-candidate"
                ],
            }
        )
        edited_receipt["held_back"].sort(key=lambda row: row["bucket"])
        edited_files = dict(bundle.files)
        edited_files[public_snapshot.PRIVACY_RECEIPT_NAME] = (
            public_snapshot.canonical_json_bytes(edited_receipt)
        )
        with self.assertRaisesRegex(
            public_snapshot.SnapshotContractError,
            "artifact descriptors do not match",
        ):
            public_snapshot.validate_bundle_bytes(edited_files)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            edited_dir = root / "edited"
            edited_dir.mkdir()
            for name, payload in edited_files.items():
                (edited_dir / name).write_bytes(payload)
            self.assertNotEqual(
                _independent_validator_probe(edited_dir).returncode,
                0,
            )

            deleted_dir = root / "deleted"
            _write_bundle(deleted_dir, bundle)
            (deleted_dir / public_snapshot.PRIVACY_RECEIPT_NAME).unlink()
            with self.assertRaises(public_snapshot.SnapshotContractError):
                public_snapshot.validate_bundle_directory(deleted_dir)
            self.assertNotEqual(
                _independent_validator_probe(deleted_dir).returncode,
                0,
            )

    def test_bundle_metadata_check_is_python39_safe_and_rejects_symlinks(self) -> None:
        bundle = _build([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle_dir = root / "bundle"
            _write_bundle(bundle_dir, bundle)

            original_stat = Path.stat

            def python39_stat(path, *args, **kwargs):
                if "follow_symlinks" in kwargs:
                    raise TypeError(
                        "Path.stat() got an unexpected keyword argument "
                        "'follow_symlinks'"
                    )
                return original_stat(path, *args, **kwargs)

            def python39_lstat(path):
                return os.lstat(path)

            def python39_is_symlink(path):
                try:
                    return stat.S_ISLNK(path.lstat().st_mode)
                except OSError:
                    return False

            with mock.patch.object(
                Path, "stat", python39_stat
            ), mock.patch.object(
                Path, "lstat", python39_lstat
            ), mock.patch.object(
                Path, "is_symlink", python39_is_symlink
            ):
                summary = public_snapshot.validate_bundle_directory(bundle_dir)
            self.assertEqual(summary["records"], 0)

            manifest = bundle_dir / public_snapshot.MANIFEST_NAME
            external_manifest = root / "external-manifest.json"
            external_manifest.write_bytes(manifest.read_bytes())
            manifest.unlink()
            manifest.symlink_to(external_manifest)
            with self.assertRaisesRegex(
                public_snapshot.SnapshotContractError,
                "unlinked regular files",
            ):
                public_snapshot.validate_bundle_directory(bundle_dir)

    def _valid_override(self) -> tuple[dict, str, str]:
        source_hash = hashlib.sha256(b"exact source bytes").hexdigest()
        selection_hash = hashlib.sha256(b'{"title":"public"}').hexdigest()
        descriptor = {
            "override_id": "1234abcd",
            "source": {
                "path_or_uid": "vault/files/1234abcd.md",
                "git_commit": SOURCE_COMMIT,
                "sha256": source_hash,
            },
            "selection": {"mode": "exact-fields", "fields": ["title"]},
            "approved_by": "mike-maziarz",
            "approved_at": GENERATED_AT,
            "reason": "Named public example",
            "public_destination": "02-outbox/web-v4/example.json",
            "privacy_review": {
                "reviewer": "argus-a132",
                "verdict": "pass",
                "checked_sha256": selection_hash,
            },
        }
        return descriptor, source_hash, selection_hash

    def _validate_override(
        self, descriptor: dict, source_hash: str, selection_hash: str
    ):
        return public_snapshot.validate_override_descriptor(
            descriptor,
            expected_source_commit=SOURCE_COMMIT,
            actual_source_sha256=source_hash,
            actual_selection_sha256=selection_hash,
            expected_destination="02-outbox/web-v4/example.json",
            verified_approver="mike-maziarz",
            verified_reviewer=descriptor["privacy_review"]["reviewer"],
        )

    def test_descriptor_shape_validates_but_v1_consumption_refuses(self) -> None:
        descriptor, source_hash, selection_hash = self._valid_override()
        validated = self._validate_override(descriptor, source_hash, selection_hash)
        with self.assertRaisesRegex(
            public_snapshot.SnapshotContractError,
            "refuses all non-empty override",
        ):
            _build([_legacy_event(1)], validated_overrides=[validated])

        full = copy.deepcopy(descriptor)
        full["selection"] = {"mode": "full-artifact"}
        full["privacy_review"]["checked_sha256"] = source_hash
        self._validate_override(full, source_hash, source_hash)

        excerpt = copy.deepcopy(descriptor)
        excerpt["selection"] = {
            "mode": "exact-excerpt",
            "excerpt_sha256": selection_hash,
        }
        self._validate_override(excerpt, source_hash, selection_hash)

    def test_invalid_override_evidence_refuses(self) -> None:
        descriptor, source_hash, selection_hash = self._valid_override()
        mutations = {
            "forged-approver": lambda item: item.update(
                {"approved_by": "mike-agent"}
            ),
            "mutable-source": lambda item: item["source"].update(
                {"git_commit": "main"}
            ),
            "wildcard-source": lambda item: item["source"].update(
                {"path_or_uid": "vault/files/*.md"}
            ),
            "source-drift": lambda item: item["source"].update(
                {"sha256": "0" * 64}
            ),
            "selection-drift": lambda item: item["privacy_review"].update(
                {"checked_sha256": "1" * 64}
            ),
            "destination-drift": lambda item: item.update(
                {"public_destination": "02-outbox/web-v4/other.json"}
            ),
            "self-approved": lambda item: item["privacy_review"].update(
                {"reviewer": "mike-maziarz"}
            ),
            "wildcard-field": lambda item: item["selection"].update(
                {"fields": ["*"]}
            ),
        }
        for label, mutate in mutations.items():
            candidate = copy.deepcopy(descriptor)
            mutate(candidate)
            with self.subTest(label=label):
                with self.assertRaises(public_snapshot.SnapshotContractError):
                    self._validate_override(candidate, source_hash, selection_hash)

        with self.assertRaises(public_snapshot.SnapshotContractError):
            public_snapshot.validate_override_descriptor(
                descriptor,
                expected_source_commit=SOURCE_COMMIT,
                actual_source_sha256=source_hash,
                actual_selection_sha256=selection_hash,
                expected_destination="02-outbox/web-v4/example.json",
                verified_approver="orpheus-o32",
                verified_reviewer="argus-a132",
            )

    def test_nonempty_override_receipt_is_invalid(self) -> None:
        bundle = _build([_legacy_event(1)])
        receipt = copy.deepcopy(bundle.privacy_receipt)
        receipt["overrides_consumed"] = ["1234abcd"]
        files = _rehash_bundle_values(
            copy.deepcopy(bundle.release_facts),
            copy.deepcopy(bundle.manifest),
            receipt,
        )
        with self.assertRaisesRegex(
            public_snapshot.SnapshotContractError, "cannot consume overrides"
        ):
            public_snapshot.validate_bundle_bytes(files)


class CliFilesystemAndBindingTests(unittest.TestCase):
    def test_dry_run_zero_writes_real_bundle_and_fixture_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = _copy_cli_fixture(root)
            output = root / "02-outbox" / "web-v4" / "public-snapshot-v1"
            command = _fixture_command(cli, output)
            before = _tree_hash(root)
            dry = _run(command + ["--dry-run"], root)
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertEqual(before, _tree_hash(root))
            self.assertFalse(output.exists())
            self.assertTrue(json.loads(dry.stdout)["dry_run"])

            real = _run(command, root)
            self.assertEqual(real.returncode, 0, real.stderr)
            self.assertEqual(json.loads(real.stdout)["source_commit"], SOURCE_COMMIT)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                public_snapshot.BUNDLE_FILENAMES,
            )
            public_bytes = b"".join(
                (output / name).read_bytes()
                for name in sorted(public_snapshot.BUNDLE_FILENAMES)
            ).decode("utf-8")
            self.assertNotIn(SOURCE_COMMIT, public_bytes)
            self.assertNotIn("20495aaf", public_bytes)
            before_preview = _tree_hash(root)
            preview = _run(command + ["--dry-run", "--force"], root)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertEqual(before_preview, _tree_hash(root))

            validated = _run(
                command
                + [
                    "--validate",
                ],
                root,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertTrue(json.loads(validated.stdout)["valid"])

    def test_clean_head_offline_receipt_rederivation_exports_one_fact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event, receipts = _receipt_event()
            cli = _copy_cli_fixture(
                root,
                [event],
                release_receipts=receipts,
            )
            self._init_git(root)
            output = root / "02-outbox" / "web-v4" / "receipt-bundle"
            command = [sys.executable, str(cli), "--out", str(output)]
            exported = _run(command, root)
            self.assertEqual(exported.returncode, 0, exported.stderr)
            self.assertEqual(json.loads(exported.stdout)["records"], 1)
            release_facts = json.loads(
                (output / "release-facts.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(release_facts["facts"]), 1)
            self.assertEqual(
                release_facts["facts"][0]["occurred_at"],
                receipts[next(iter(receipts))]["published_at"],
            )
            validated = _run(command + ["--validate"], root)
            self.assertEqual(validated.returncode, 0, validated.stderr)

    def test_source_commit_override_requires_explicit_fixture_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = _copy_cli_fixture(root)
            output = root / "02-outbox" / "web-v4" / "bundle"
            refused = _run(
                [
                    sys.executable,
                    str(cli),
                    "--out",
                    str(output),
                    "--source-commit",
                    SOURCE_COMMIT,
                    "--dry-run",
                ],
                root,
            )
            self.assertEqual(refused.returncode, 2)
            self.assertIn("fixture-only", refused.stderr)
            self.assertFalse(output.exists())

    def test_fixture_mode_requires_sentinel_env_and_no_origin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = _copy_cli_fixture(root)
            output = root / "02-outbox" / "web-v4" / "bundle"
            command = _fixture_command(cli, output) + ["--dry-run"]

            no_environment = _run(command, root, fixture_env=False)
            self.assertEqual(no_environment.returncode, 2)
            self.assertIn("environment opt-in", no_environment.stderr)

            sentinel = root / ".tropo-public-snapshot-fixture"
            sentinel.write_text("wrong fixture sentinel\n", encoding="utf-8")
            wrong_sentinel = _run(command, root)
            self.assertEqual(wrong_sentinel.returncode, 2)
            self.assertIn("sentinel", wrong_sentinel.stderr)

            sentinel.write_text(FIXTURE_SENTINEL, encoding="utf-8")
            subprocess.run(
                ["git", "remote", "add", "origin", "https://example.invalid/repo.git"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            with_origin = _run(command, root)
            self.assertEqual(with_origin.returncode, 2)
            self.assertIn("repository with origin", with_origin.stderr)
            self.assertFalse(output.exists())

        real_output = (
            ROOT / "02-outbox" / "web-v4" / "fixture-seam-must-not-write"
        )
        self.assertFalse(real_output.exists())
        real_checkout = _run(
            _fixture_command(CLI_SOURCE, real_output) + ["--dry-run"],
            ROOT,
        )
        self.assertEqual(real_checkout.returncode, 2)
        self.assertFalse(real_output.exists())

    def test_fixture_mode_sanitizes_git_routing_before_origin_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "origin-repository"
            decoy = parent / "decoy-repository"
            root.mkdir()
            decoy.mkdir()
            cli = _copy_cli_fixture(root)
            subprocess.run(
                ["git", "remote", "add", "origin", "https://example.invalid/repo.git"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "init", "-q"],
                cwd=decoy,
                check=True,
                capture_output=True,
            )
            output = root / "02-outbox" / "web-v4" / "bundle"
            hostile_git_environment = {
                "GIT_DIR": str(decoy / ".git"),
                "GIT_WORK_TREE": str(decoy),
                "GIT_INDEX_FILE": str(decoy / "attacker-index"),
            }
            result = _run(
                _fixture_command(cli, output) + ["--dry-run"],
                root,
                environment_overrides=hostile_git_environment,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("repository with origin", result.stderr)
            self.assertFalse(output.exists())
            self.assertFalse((decoy / "attacker-index").exists())

    def test_fixture_mode_refuses_gitfile_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = _copy_cli_fixture(root)
            (root / ".git").rename(root / "fixture-git-dir")
            (root / ".git").write_text(
                "gitdir: fixture-git-dir\n",
                encoding="utf-8",
            )
            output = root / "02-outbox" / "web-v4" / "bundle"
            result = _run(
                _fixture_command(cli, output) + ["--dry-run"],
                root,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("real local .git directory", result.stderr)
            self.assertFalse(output.exists())

    def test_in_repo_output_scope_and_symlink_plants_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = _copy_cli_fixture(root)
            unsafe = root / "other" / "bundle"
            refused = _run(_fixture_command(cli, unsafe) + ["--dry-run"], root)
            self.assertEqual(refused.returncode, 2)
            self.assertFalse(unsafe.exists())

            governed_alias = (
                root / "02-outbox" / "web-v4" / ".." / ".." / "vault" / "bundle"
            )
            refused = _run(
                _fixture_command(cli, governed_alias) + ["--dry-run"], root
            )
            self.assertEqual(refused.returncode, 2)

            external = root / "external-target"
            external.mkdir()
            parent = root / "02-outbox" / "web-v4"
            parent.mkdir(parents=True)
            (parent / "linked-parent").symlink_to(external, target_is_directory=True)
            linked_output = parent / "linked-parent" / "bundle"
            refused = _run(
                _fixture_command(cli, linked_output) + ["--dry-run"], root
            )
            self.assertEqual(refused.returncode, 2)
            self.assertEqual(list(external.iterdir()), [])

            output_link = parent / "output-link"
            output_link.symlink_to(external, target_is_directory=True)
            refused = _run(
                _fixture_command(cli, output_link) + ["--dry-run"], root
            )
            self.assertEqual(refused.returncode, 2)

    def test_out_of_repo_output_is_refused_even_without_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as source_temporary:
            with tempfile.TemporaryDirectory() as output_temporary:
                root = Path(source_temporary)
                cli = _copy_cli_fixture(root)
                output = Path(output_temporary) / "bundle"
                result = _run(_fixture_command(cli, output), root)
                self.assertEqual(result.returncode, 2)
                self.assertIn(
                    "only below repository 02-outbox/web-v4",
                    result.stderr,
                )
                self.assertFalse(output.exists())
                validation = _run(
                    _fixture_command(cli, output) + ["--validate"],
                    root,
                )
                self.assertEqual(validation.returncode, 2)
                self.assertIn(
                    "only below repository 02-outbox/web-v4",
                    validation.stderr,
                )

    def test_hardlinked_bundle_file_and_unsafe_force_contents_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = _copy_cli_fixture(root)
            output = root / "02-outbox" / "web-v4" / "bundle"
            command = _fixture_command(cli, output)
            self.assertEqual(_run(command, root).returncode, 0)
            os.link(output / "manifest.json", root / "manifest-hardlink")
            hardlink_refusal = _run(command + ["--force"], root)
            self.assertEqual(hardlink_refusal.returncode, 2)
            self.assertIn("unlinked", hardlink_refusal.stderr)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = _copy_cli_fixture(root)
            output = root / "02-outbox" / "web-v4" / "bundle"
            output.mkdir(parents=True)
            (output / "attacker.txt").write_text("plant", encoding="utf-8")
            refused = _run(
                _fixture_command(cli, output) + ["--force", "--dry-run"], root
            )
            self.assertEqual(refused.returncode, 2)
            self.assertEqual((output / "attacker.txt").read_text(), "plant")

    def _init_git(self, root: Path) -> str:
        commands = [
            ["git", "init", "-q"],
            ["git", "config", "user.email", "snapshot-test@example.invalid"],
            ["git", "config", "user.name", "Snapshot Test"],
            ["git", "add", "."],
            ["git", "commit", "-qm", "fixture"],
            ["git", "branch", "-M", "main"],
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://example.invalid/public-snapshot-fixture.git",
            ],
            [
                "git",
                "update-ref",
                "refs/remotes/origin/main",
                "HEAD",
            ],
        ]
        for command in commands:
            subprocess.run(command, cwd=root, check=True, capture_output=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_normal_cli_binds_clean_head_and_refuses_dirty_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = _copy_cli_fixture(root)
            head = self._init_git(root)
            output = root / "02-outbox" / "web-v4" / "bundle"
            normal = [
                sys.executable,
                str(cli),
                "--out",
                str(output),
                "--dry-run",
            ]
            index = root / ".git" / "index"
            index_before = _file_state(index)
            tree_before = _tree_state(root)
            clean = _run(normal, root)
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertEqual(json.loads(clean.stdout)["source_commit"], head)
            self.assertEqual(index_before, _file_state(index))
            self.assertEqual(tree_before, _tree_state(root))
            with (root / "vault" / "events" / "00-events.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write("\n")
            dirty = _run(normal, root)
            self.assertEqual(dirty.returncode, 2)
            self.assertIn("must be clean", dirty.stderr)
            self.assertFalse(output.exists())

    def test_normal_cli_binds_authority_code_and_receipt_bytes(self) -> None:
        plants = ("authority-code", "root-authority-code", "receipt")
        for plant in plants:
            with self.subTest(plant=plant), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                if plant == "receipt":
                    event, receipts = _receipt_event()
                    cli = _copy_cli_fixture(
                        root,
                        [event],
                        release_receipts=receipts,
                    )
                else:
                    cli = _copy_cli_fixture(root)
                self._init_git(root)
                if plant == "authority-code":
                    target = root / "vault" / "tools" / "lib" / "release_receipt.py"
                elif plant == "root-authority-code":
                    target = root / "vault" / "tools" / "lib" / "tropo_roots.py"
                else:
                    target = next(
                        (
                            root
                            / public_snapshot.release_receipt.RECEIPTS_RELATIVE_DIR
                        ).glob("*.json")
                    )
                with target.open("ab") as handle:
                    handle.write(b"\n")
                output = root / "02-outbox" / "web-v4" / "bundle"
                result = _run(
                    [
                        sys.executable,
                        str(cli),
                        "--out",
                        str(output),
                        "--dry-run",
                    ],
                    root,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("must be clean", result.stderr)
                self.assertFalse(output.exists())

    def test_normal_cli_requires_main_attached_and_equal_origin_main(self) -> None:
        for plant in ("feature", "detached", "ahead"):
            with self.subTest(plant=plant), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                cli = _copy_cli_fixture(root)
                self._init_git(root)
                if plant == "feature":
                    subprocess.run(
                        ["git", "switch", "-q", "-c", "feature"],
                        cwd=root,
                        check=True,
                        capture_output=True,
                    )
                elif plant == "detached":
                    subprocess.run(
                        ["git", "checkout", "-q", "--detach", "HEAD"],
                        cwd=root,
                        check=True,
                        capture_output=True,
                    )
                else:
                    (root / "ahead.txt").write_text("ahead\n", encoding="utf-8")
                    subprocess.run(
                        ["git", "add", "ahead.txt"],
                        cwd=root,
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "commit", "-qm", "ahead of origin"],
                        cwd=root,
                        check=True,
                        capture_output=True,
                    )
                output = root / "02-outbox" / "web-v4" / "bundle"
                result = _run(
                    [
                        sys.executable,
                        str(cli),
                        "--out",
                        str(output),
                        "--dry-run",
                    ],
                    root,
                )
                self.assertEqual(result.returncode, 2)
                if plant == "ahead":
                    self.assertIn("HEAD to equal origin/main", result.stderr)
                else:
                    self.assertIn("checked-out branch main", result.stderr)
                self.assertFalse(output.exists())

    def test_normal_source_binding_ignores_hostile_inherited_git_routing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "source-repository"
            decoy = parent / "decoy-repository"
            root.mkdir()
            decoy.mkdir()
            cli = _copy_cli_fixture(root)
            head = self._init_git(root)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=decoy,
                check=True,
                capture_output=True,
            )
            decoy_before = _tree_state(decoy)
            output = root / "02-outbox" / "web-v4" / "bundle"
            result = _run(
                [
                    sys.executable,
                    str(cli),
                    "--out",
                    str(output),
                    "--dry-run",
                ],
                root,
                environment_overrides={
                    "GIT_DIR": str(decoy / ".git"),
                    "GIT_WORK_TREE": str(decoy),
                    "GIT_INDEX_FILE": str(decoy / "attacker-index"),
                    "GIT_OBJECT_DIRECTORY": str(decoy / "objects-decoy"),
                    "GIT_CEILING_DIRECTORIES": str(root),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["source_commit"], head)
            self.assertEqual(decoy_before, _tree_state(decoy))
            self.assertFalse(output.exists())

    def test_post_discovery_source_state_check_detects_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli_path = _copy_cli_fixture(root)
            self._init_git(root)
            spec = importlib.util.spec_from_file_location("fixture_snapshot_cli", cli_path)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            sys.modules["fixture_snapshot_cli"] = module
            spec.loader.exec_module(module)
            binding = module._capture_source_binding()
            with (root / "vault" / "agents" / "agent.md").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write("race-canary\n")
            with self.assertRaisesRegex(
                public_snapshot.SnapshotContractError, "must be clean|changed"
            ):
                module._verify_source_binding(binding)

    def test_hash_seed_and_event_order_do_not_change_public_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = [
                _legacy_event(2, event_type="tropo.release.published", version="2.0.0"),
                _legacy_event(1),
                _legacy_event(3, event_type="tropo.message.sent"),
            ]
            cli = _copy_cli_fixture(root, events)
            output = root / "02-outbox" / "web-v4" / "bundle"
            command = _fixture_command(cli, output) + ["--dry-run"]
            first = _run(command, root, seed="1")
            self.assertEqual(first.returncode, 0, first.stderr)
            _write_event_union(root, list(reversed(events)))
            second = _run(command, root, seed="777")
            self.assertEqual(second.returncode, 0, second.stderr)
            first_summary = json.loads(first.stdout)
            second_summary = json.loads(second.stdout)
            self.assertEqual(
                (
                    first_summary["bundle_sha256"],
                    first_summary["release_facts_sha256"],
                    first_summary["held_back_buckets"],
                ),
                (
                    second_summary["bundle_sha256"],
                    second_summary["release_facts_sha256"],
                    second_summary["held_back_buckets"],
                ),
            )


class IndependentValidatorTests(unittest.TestCase):
    def test_tampered_and_rehashed_forbidden_field_fails_independent_check(self) -> None:
        bundle = _build([_legacy_event(1)])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "bundle"
            _write_bundle(directory, bundle)
            release = copy.deepcopy(bundle.release_facts)
            dormant_fact, _ = _project(_legacy_event(1))
            self.assertIsNotNone(dormant_fact)
            assert dormant_fact is not None
            release["facts"].append(
                {**dormant_fact, "event_uid": "legacy_00000001"}
            )
            manifest = copy.deepcopy(bundle.manifest)
            receipt = copy.deepcopy(bundle.privacy_receipt)
            files = _rehash_bundle_values(release, manifest, receipt)
            for name, payload in files.items():
                (directory / name).write_bytes(payload)
            probe = _independent_validator_probe(directory)
            self.assertNotEqual(probe.returncode, 0)
            self.assertIn("forbidden private metadata", probe.stderr)

    def test_rehashed_policy_uid_and_source_commit_metadata_fail(self) -> None:
        bundle = _build([_legacy_event(1)])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "bundle"
            _write_bundle(directory, bundle)

            release = copy.deepcopy(bundle.release_facts)
            release["source_commit"] = SOURCE_COMMIT
            manifest = copy.deepcopy(bundle.manifest)
            manifest["policy_uid"] = "20495aaf"
            receipt = copy.deepcopy(bundle.privacy_receipt)
            receipt["source_commit"] = SOURCE_COMMIT
            files = _rehash_bundle_values(release, manifest, receipt)
            for name, payload in files.items():
                (directory / name).write_bytes(payload)

            with self.assertRaises(public_snapshot.SnapshotContractError):
                public_snapshot.validate_bundle_bytes(files)
            probe = _independent_validator_probe(directory)
            self.assertNotEqual(probe.returncode, 0)
            self.assertIn("forbidden private metadata", probe.stderr)

    def test_valid_bundle_passes_independent_check(self) -> None:
        bundle = _build([_legacy_event(1)])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "bundle"
            _write_bundle(directory, bundle)
            probe = _independent_validator_probe(directory)
            self.assertEqual(probe.returncode, 0, probe.stderr)

    def test_full_validator_tolerates_dirty_private_event_but_detects_public_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_agent(root)
            _write_policy_sources(root)
            _write_event_union(
                root,
                [
                    _legacy_event(
                        1,
                        event_type="tropo.validator.run.completed",
                    ),
                ],
            )
            for command in (
                ["git", "init", "-q"],
                ["git", "config", "user.email", "snapshot-test@example.invalid"],
                ["git", "config", "user.name", "Snapshot Test"],
                ["git", "add", "."],
                ["git", "commit", "-qm", "source fixture"],
            ):
                subprocess.run(command, cwd=root, check=True, capture_output=True)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            bundle = public_snapshot.discover_public_snapshot(
                root,
                source_commit=head,
                generated_at=GENERATED_AT,
            )
            sample = (
                root / "02-outbox" / "web-v4" / "public-snapshot-v1"
            )
            _write_bundle(sample, bundle)

            event_path = root / "vault" / "events" / "00-events.jsonl"
            with event_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        _legacy_event(
                            2,
                            event_type="tropo.validator.run.completed",
                        ),
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            private_only = _full_validator_contract_probe(root)
            self.assertEqual(private_only.returncode, 0, private_only.stderr)
            self.assertEqual(json.loads(private_only.stdout)["defects"], 0)

            with event_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        _legacy_event(3, version="2.0.0"),
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            public_change = _full_validator_contract_probe(root)
            self.assertNotEqual(public_change.returncode, 0)
            self.assertGreater(json.loads(public_change.stdout)["defects"], 0)

    def test_missing_exporter_helper_is_error_when_sample_exists(self) -> None:
        bundle = _build([_legacy_event(1)])
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            directory = (
                vault / "02-outbox" / "web-v4" / "public-snapshot-v1"
            )
            _write_bundle(directory, bundle)
            code = (
                "import importlib.util,sys; from pathlib import Path; "
                "p=Path(sys.argv[1]); s=importlib.util.spec_from_file_location('tv2',p); "
                "m=importlib.util.module_from_spec(s); sys.modules['tv2']=m; "
                "s.loader.exec_module(m); "
                "m._load_public_snapshot_contract=lambda: "
                "(_ for _ in ()).throw(ImportError('missing helper')); "
                "f,c,d=m.check_public_snapshot_contract(Path(sys.argv[2])); "
                "print(c,d,str(f[0]) if f else '')"
            )
            environment = dict(os.environ)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    code,
                    str(VALIDATOR_SOURCE),
                    str(vault),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1 1", result.stdout)
            self.assertIn("ImportError", result.stdout)

    def test_default_sample_has_no_partial_stale_files_or_rederives(self) -> None:
        sample = ROOT / "02-outbox" / "web-v4" / "public-snapshot-v1"
        expected = set(public_snapshot.BUNDLE_FILENAMES)
        present = {path.name for path in sample.iterdir()} if sample.is_dir() else set()
        if not present:
            return
        self.assertEqual(present, expected, "partial stale sample bundle must be removed")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        public_snapshot.validate_bundle_directory(
            sample,
            source_root=ROOT,
            bound_source_commit=head,
        )
        probe = _independent_validator_probe(sample)
        self.assertEqual(probe.returncode, 0, probe.stderr)


if __name__ == "__main__":
    unittest.main()
