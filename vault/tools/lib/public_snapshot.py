"""Deterministic, deny-by-default public snapshot projection and validation.

This module owns the policy mechanics only.  It performs no writes, reads no
clock, invokes no network operation, and requires the caller to supply the
source commit and generation timestamp.  Event discovery is delegated to the
canonical mixed-ledger implementation in :mod:`event_identity`.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlsplit

import yaml


def _load_event_identity():
    """Load the co-located canonical event identity module unambiguously."""
    module_name = "tropo_public_snapshot_event_identity"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).resolve().with_name("event_identity.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load canonical event_identity module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


event_identity = _load_event_identity()


def _load_release_receipt():
    """Load the co-located receipt contract without relying on ``lib`` paths."""
    module_name = "tropo_public_snapshot_release_receipt"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).resolve().with_name("release_receipt.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load canonical release_receipt module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


release_receipt = _load_release_receipt()


SCHEMA_VERSION = "1.0.0"
POLICY_NAME = "public-crew-snapshot"
POLICY_VERSION = "1.0.0"
EXPORTER_VERSION = "1.1.0"

RELEASE_FACTS_NAME = "release-facts.json"
MANIFEST_NAME = "manifest.json"
PRIVACY_RECEIPT_NAME = "privacy-receipt.json"
BUNDLE_FILENAMES = frozenset(
    {MANIFEST_NAME, RELEASE_FACTS_NAME, PRIVACY_RECEIPT_NAME}
)

ALLOWED_EVENT_TYPES = frozenset(
    {"tropo.release.shipped", "tropo.release.published"}
)
# Labels in the event envelope remain caller-controlled. Receipt-backed
# projection does not turn a label tuple into an authenticated emitter.
VERIFIED_RELEASE_EMITTERS: frozenset[tuple[str, str, str]] = frozenset()
EVENT_SOURCE_FIELD_ALLOWLIST = frozenset(
    {
        "id",
        "event_uid",
        "writer_instance_uid",
        "stream_uid",
        "local_seq",
        "specversion",
        "type",
        "source",
        "time",
        "source_uid",
        "lifecycle",
        "data",
    }
)
DATA_SOURCE_FIELD_ALLOWLIST = frozenset(
    {"version", "tag", "public_url", "published_at", "receipt_sha256"}
)
RELEASE_FACT_REQUIRED_FIELDS = frozenset(
    {
        "public_fact_id",
        "type",
        "occurred_at",
        "version",
    }
)
RELEASE_FACT_OPTIONAL_FIELDS = frozenset(
    {"tag", "public_url", "agent_name", "agent_generation"}
)
RELEASE_FACT_FIELDS = RELEASE_FACT_REQUIRED_FIELDS | RELEASE_FACT_OPTIONAL_FIELDS

HELD_BACK_POLICY = {
    "private-default": "input is private unless explicitly allowlisted",
    "unverified-release-emitter": "candidate emitter is not the governed verify-live publisher",
    "malformed-public-candidate": "candidate lacks valid required public fields",
    "unresolved-public-signer": "optional signer attribution could not be resolved safely",
    "unknown-input-fields": "candidate contains fields outside the public input allowlist",
}

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UID8_RE = re.compile(r"^[0-9a-f]{8}$")
PUBLIC_FACT_ID_RE = re.compile(r"^rf_[0-9a-f]{64}$")
AGENT_SLUG_RE = re.compile(r"^[a-z][a-z0-9.-]{0,63}$")
AGENT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 .'-]{0,79}$")
GENERATION_RE = re.compile(r"^[A-Z][0-9]+$")
FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
PRINCIPAL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")

_SEMVER_CORE = r"(?:0|[1-9][0-9]*)"
_SEMVER_IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER_RE = re.compile(
    rf"^{_SEMVER_CORE}\.{_SEMVER_CORE}\.{_SEMVER_CORE}"
    rf"(?:-{_SEMVER_IDENTIFIER}(?:\.{_SEMVER_IDENTIFIER})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class SnapshotContractError(ValueError):
    """The input or bundle violates the public snapshot contract."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses ambiguous duplicate identity fields."""


def _construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing agent identity",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class AgentIdentity:
    """The only public projection of a party-to-agent lookup."""

    name: str
    generation: str


@dataclass(frozen=True)
class ValidatedOverride:
    """Evidence that one exact override descriptor passed all v1 checks."""

    override_id: str
    source_sha256: str
    selection_sha256: str
    public_destination: str


@dataclass(frozen=True)
class SnapshotBundle:
    """A completely built in-memory bundle."""

    release_facts: dict[str, Any]
    manifest: dict[str, Any]
    privacy_receipt: dict[str, Any]
    release_facts_bytes: bytes
    manifest_bytes: bytes
    privacy_receipt_bytes: bytes
    bound_source_commit: str
    source_event_paths: tuple[str, ...] = ()

    @property
    def files(self) -> dict[str, bytes]:
        return {
            MANIFEST_NAME: self.manifest_bytes,
            RELEASE_FACTS_NAME: self.release_facts_bytes,
            PRIVACY_RECEIPT_NAME: self.privacy_receipt_bytes,
        }


def _canonical_payload(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SnapshotContractError(f"value is not canonical JSON: {exc}") from exc
    return encoded.encode("utf-8")


def canonical_json_bytes(value: Any) -> bytes:
    """Return the contract's canonical UTF-8 JSON file representation."""
    return _canonical_payload(value) + b"\n"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def bundle_descriptor_sha256(artifacts: Sequence[Mapping[str, Any]]) -> str:
    """Hash canonical artifact descriptors, excluding non-deterministic metadata."""
    return sha256_bytes(_canonical_payload(list(artifacts)))


def validate_source_commit(value: Any) -> str:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise SnapshotContractError("source_commit must be an immutable 40-hex commit")
    return value


def normalize_semver(value: Any) -> str:
    if not isinstance(value, str):
        raise SnapshotContractError("release version must be a SemVer string")
    candidate = value[1:] if value.startswith("v") else value
    if not SEMVER_RE.fullmatch(candidate):
        raise SnapshotContractError(f"release version is not SemVer: {value!r}")
    return candidate


def normalize_timestamp(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotContractError(f"{field} must be an ISO-8601 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise SnapshotContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SnapshotContractError(f"{field} must include a timezone")
    parsed = parsed.astimezone(timezone.utc)
    timespec = "microseconds" if parsed.microsecond else "seconds"
    return parsed.isoformat(timespec=timespec).replace("+00:00", "Z")


def validate_public_url(value: Any, *, version: Optional[str] = None) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotContractError("public_url must be a non-empty HTTPS URL")
    if (
        value != value.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        or any(character.isspace() for character in value)
    ):
        raise SnapshotContractError(
            "public_url cannot contain whitespace or control characters"
        )
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError as exc:
        raise SnapshotContractError("public_url is malformed") from exc
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed_port is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/tropo-ai/tropo/releases/tag/")
        or parsed.path.endswith("/")
        or "//" in parsed.path
        or "%" in parsed.path
        or any(part in {".", ".."} for part in PurePosixPath(parsed.path).parts)
        or value != f"https://github.com{parsed.path}"
    ):
        raise SnapshotContractError(
            "public_url must be an exact https://github.com/tropo-ai/tropo/ path"
        )
    url_tag = parsed.path[len("/tropo-ai/tropo/releases/tag/") :]
    try:
        url_version = normalize_semver(url_tag)
    except SnapshotContractError as exc:
        raise SnapshotContractError("public_url must identify one SemVer release tag") from exc
    if version is not None and url_version != version:
        raise SnapshotContractError("public_url release tag does not match version")
    return value


def _validate_tag(value: Any, version: str) -> str:
    if not isinstance(value, str) or value not in {version, f"v{version}"}:
        raise SnapshotContractError("tag must exactly match the normalized release version")
    return value


def _frontmatter(path: Path) -> Optional[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SnapshotContractError(f"could not read agent identity {path.name}") from exc
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SnapshotContractError(f"agent identity has unterminated frontmatter: {path.name}")
    try:
        parsed = yaml.load(text[4:end], Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise SnapshotContractError(f"agent identity has invalid YAML: {path.name}") from exc
    if parsed is None:
        return None
    if not isinstance(parsed, dict):
        raise SnapshotContractError(f"agent identity frontmatter is not a map: {path.name}")
    return parsed


def _public_agent_name(frontmatter: Mapping[str, Any], path: Path) -> str:
    slug = frontmatter.get("agent")
    if not isinstance(slug, str) or not AGENT_SLUG_RE.fullmatch(slug):
        raise SnapshotContractError(f"agent identity has no safe agent slug: {path.name}")
    title = frontmatter.get("title")
    if not isinstance(title, str):
        raise SnapshotContractError(f"agent identity has no public title: {path.name}")
    name = title.split("—", 1)[0].strip()
    if name.casefold() != slug.casefold() or not AGENT_NAME_RE.fullmatch(name):
        raise SnapshotContractError(f"agent identity has no safe public display name: {path.name}")
    return name


def load_agent_identities(vault_root: Path) -> dict[str, AgentIdentity]:
    """Resolve explicit party UIDs to public agent name/generation only."""
    identities: dict[str, AgentIdentity] = {}
    agents_dir = Path(vault_root) / "vault" / "agents"
    if not agents_dir.is_dir():
        raise SnapshotContractError("vault/agents identity directory is missing")
    for path in sorted(agents_dir.glob("*.md")):
        frontmatter = _frontmatter(path)
        if not frontmatter or frontmatter.get("type") != "agent":
            continue
        party_uid = frontmatter.get("party_uid")
        if party_uid is None or party_uid == "" or party_uid == "null":
            continue
        if not isinstance(party_uid, str) or not UID8_RE.fullmatch(party_uid):
            raise SnapshotContractError(f"agent has malformed party_uid: {path.name}")
        generation = frontmatter.get("generation")
        if not isinstance(generation, str) or not GENERATION_RE.fullmatch(generation):
            raise SnapshotContractError(f"agent has no public generation: {path.name}")
        identity = AgentIdentity(
            name=_public_agent_name(frontmatter, path),
            generation=generation,
        )
        existing = identities.get(party_uid)
        if existing is not None:
            raise SnapshotContractError(
                f"party_uid maps to more than one agent identity: {party_uid}"
            )
        identities[party_uid] = identity
    return identities


def _canonical_event(event: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            event,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SnapshotContractError(f"event is not canonical JSON data: {exc}") from exc


def _dedupe_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Defensively preserve event_identity's identity/content invariant."""
    by_uid: dict[str, dict[str, Any]] = {}
    for record in records:
        event_value = record.get("event")
        event = event_value if isinstance(event_value, dict) else record
        if not isinstance(event, dict):
            raise SnapshotContractError("event union record is not an object")
        derived_uid = event_identity.immutable_event_uid(event)
        record_uid = record.get("event_uid", derived_uid)
        if not isinstance(record_uid, str) or record_uid != derived_uid:
            raise SnapshotContractError("event union record identity disagrees with event_identity")
        canonical = _canonical_event(event)
        existing = by_uid.get(derived_uid)
        if existing is not None:
            if existing["canonical"] != canonical:
                raise SnapshotContractError(
                    f"event identity conflict {derived_uid}: same identity, different content"
                )
            continue
        by_uid[derived_uid] = {
            "event_uid": derived_uid,
            "event": event,
            "canonical": canonical,
            "source_path": str(record.get("source_path", "")),
        }
    return [by_uid[uid] for uid in sorted(by_uid)]


def _extract_version(data: Mapping[str, Any]) -> Optional[str]:
    present = [key for key in ("version", "release") if key in data]
    if not present:
        return None
    normalized = [normalize_semver(data[key]) for key in present]
    if len(set(normalized)) != 1:
        raise SnapshotContractError("version and release fields disagree")
    return normalized[0]


def derive_public_fact_id(projected_fields: Mapping[str, Any]) -> str:
    """Derive a non-correlatable identity from public projected fields only."""
    if "public_fact_id" in projected_fields:
        raise SnapshotContractError("public_fact_id cannot be part of its own hash input")
    if not set(projected_fields) <= (RELEASE_FACT_FIELDS - {"public_fact_id"}):
        raise SnapshotContractError("public fact identity input contains non-public fields")
    return f"rf_{sha256_bytes(_canonical_payload(dict(projected_fields)))}"


def _validated_receipt_map(
    receipts: Optional[Mapping[str, Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    try:
        return release_receipt.validate_receipt_mapping(receipts or {})
    except release_receipt.ReleaseReceiptError as exc:
        raise SnapshotContractError(f"release receipt set is invalid: {exc}") from exc


def _pointed_release_receipt(
    record: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
) -> Optional[dict[str, Any]]:
    """Resolve a receipt pointer after checking the canonical event label tuple.

    The tuple is a required cross-check, never authority by itself.  Authority
    comes from exact content-addressed receipt bytes in governed source.
    """
    event = record["event"]
    if (
        event.get("specversion") != "1.0"
        or event.get("type") != "tropo.release.published"
        or event.get("source") != release_receipt.PUBLISHER_TOOL_SOURCE
        or event.get("source_uid") != release_receipt.PUBLISHER_TOOL_UID
        or event.get("lifecycle") != "evergreen"
    ):
        return None
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    digest = data.get("receipt_sha256")
    if (
        not isinstance(digest, str)
        or not SHA256_RE.fullmatch(digest)
        or digest not in receipts
    ):
        return None
    return dict(receipts[digest])


def _event_matches_release_receipt(
    event: Mapping[str, Any], receipt: Mapping[str, Any]
) -> bool:
    data = event.get("data")
    if not isinstance(data, dict) or set(data) != DATA_SOURCE_FIELD_ALLOWLIST:
        return False
    expected = {
        "version": receipt["version"],
        "tag": receipt["tag"],
        "public_url": receipt["public_url"],
        "published_at": receipt["published_at"],
        "receipt_sha256": release_receipt.receipt_sha256(receipt),
    }
    return data == expected


def _has_unknown_input_fields(
    event: Mapping[str, Any], data: Any
) -> bool:
    return bool(
        set(event) - EVENT_SOURCE_FIELD_ALLOWLIST
        or (
            isinstance(data, Mapping)
            and set(data) - DATA_SOURCE_FIELD_ALLOWLIST
        )
    )


def _project_release_fact(
    record: Mapping[str, Any],
    identities: Mapping[str, AgentIdentity],
) -> tuple[Optional[dict[str, Any]], set[str]]:
    event = record["event"]
    data = event.get("data")
    if not isinstance(data, dict):
        return None, {"malformed-public-candidate"}

    version = _extract_version(data)
    if version is None:
        return None, {"malformed-public-candidate"}

    occurred_at = normalize_timestamp(event.get("time"), field="event time")
    tag = _validate_tag(data["tag"], version) if "tag" in data else None
    public_url = (
        validate_public_url(data["public_url"], version=version)
        if "public_url" in data
        else None
    )

    party_uid = event.get("source_uid")
    identity = identities.get(party_uid) if isinstance(party_uid, str) else None
    projected: dict[str, Any] = {
        "type": event["type"],
        "occurred_at": occurred_at,
        "version": version,
    }
    if tag is not None:
        projected["tag"] = tag
    if public_url is not None:
        projected["public_url"] = public_url

    held_buckets: set[str] = set()
    if identity is None:
        held_buckets.add("unresolved-public-signer")
    else:
        if (
            not isinstance(identity, AgentIdentity)
            or not AGENT_NAME_RE.fullmatch(identity.name)
            or not GENERATION_RE.fullmatch(identity.generation)
        ):
            raise SnapshotContractError("resolved agent attribution is malformed")
        projected["agent_name"] = identity.name
        projected["agent_generation"] = identity.generation

    fact = {"public_fact_id": derive_public_fact_id(projected), **projected}
    return fact, held_buckets


def _project_receipt_release_fact(
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Project only receipt fields; event labels and timestamps never cross."""
    projected = {
        "type": "tropo.release.published",
        "occurred_at": receipt["published_at"],
        "version": receipt["version"],
        "tag": receipt["tag"],
        "public_url": receipt["public_url"],
    }
    return {"public_fact_id": derive_public_fact_id(projected), **projected}


def build_public_snapshot(
    records: Iterable[Mapping[str, Any]],
    identities: Mapping[str, AgentIdentity],
    *,
    source_commit: str,
    generated_at: str,
    policy: str = POLICY_NAME,
    policy_version: str = POLICY_VERSION,
    schema_version: str = SCHEMA_VERSION,
    validated_overrides: Sequence[ValidatedOverride] = (),
    release_receipts: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> SnapshotBundle:
    """Classify and reconstruct a complete snapshot entirely in memory."""
    bound_source_commit = validate_source_commit(source_commit)
    if policy != POLICY_NAME or policy_version != POLICY_VERSION:
        raise SnapshotContractError("unknown public snapshot policy")
    if schema_version != SCHEMA_VERSION:
        raise SnapshotContractError("unknown public snapshot schema version")
    if validated_overrides:
        raise SnapshotContractError(
            "v1 refuses all non-empty override input until a trusted principal adapter exists"
        )
    generated_at = normalize_timestamp(generated_at, field="generated_at")

    receipts = _validated_receipt_map(release_receipts)
    input_records = list(records)
    receipt_pointer_counts: dict[str, int] = {}
    for record in input_records:
        event_value = record.get("event")
        event = event_value if isinstance(event_value, dict) else record
        data = event.get("data") if isinstance(event, Mapping) else None
        digest = data.get("receipt_sha256") if isinstance(data, dict) else None
        if isinstance(digest, str) and digest in receipts:
            receipt_pointer_counts[digest] = (
                receipt_pointer_counts.get(digest, 0) + 1
            )
            if receipt_pointer_counts[digest] > 1:
                raise SnapshotContractError(
                    f"more than one event points to release receipt {digest}"
                )
    normalized_records = _dedupe_records(input_records)
    facts_by_id: dict[str, dict[str, Any]] = {}
    held_buckets: set[str] = set()

    for record in normalized_records:
        event = record["event"]
        event_type = event.get("type")
        if event_type not in ALLOWED_EVENT_TYPES:
            held_buckets.add("private-default")
            continue
        receipt = _pointed_release_receipt(record, receipts)
        if receipt is None:
            held_buckets.add("unverified-release-emitter")
            continue

        data = event.get("data")
        if _has_unknown_input_fields(event, data):
            held_buckets.add("unknown-input-fields")
            continue
        if not _event_matches_release_receipt(event, receipt):
            held_buckets.add("malformed-public-candidate")
            continue
        fact = _project_receipt_release_fact(receipt)
        public_fact_id = fact["public_fact_id"]
        existing = facts_by_id.get(public_fact_id)
        if existing is not None:
            if existing != fact:
                raise SnapshotContractError(
                    "public_fact_id collision: same identity, different public content"
                )
            continue
        facts_by_id[public_fact_id] = fact

    facts = sorted(
        facts_by_id.values(),
        key=lambda fact: (fact["occurred_at"], fact["public_fact_id"]),
    )
    release_facts = {
        "schema_version": schema_version,
        "facts": facts,
    }
    release_facts_bytes = canonical_json_bytes(release_facts)
    release_hash = sha256_bytes(release_facts_bytes)

    release_descriptor = {
        "path": RELEASE_FACTS_NAME,
        "sha256": release_hash,
        "bytes": len(release_facts_bytes),
        "records": len(facts),
    }

    held_back = [
        {"bucket": bucket, "reason": HELD_BACK_POLICY[bucket]}
        for bucket in sorted(held_buckets)
    ]
    privacy_receipt = {
        "schema_version": schema_version,
        "policy": policy,
        "policy_version": policy_version,
        "exporter_version": EXPORTER_VERSION,
        "data_bundle_sha256": bundle_descriptor_sha256([release_descriptor]),
        "crossed": {
            "release_facts": {"count": len(facts), "sha256": release_hash}
        },
        "held_back": held_back,
        "overrides_consumed": [],
    }
    privacy_receipt_bytes = canonical_json_bytes(privacy_receipt)
    receipt_descriptor = {
        "path": PRIVACY_RECEIPT_NAME,
        "sha256": sha256_bytes(privacy_receipt_bytes),
        "bytes": len(privacy_receipt_bytes),
        "records": 1,
    }
    artifact_descriptors = [release_descriptor, receipt_descriptor]
    manifest = {
        "schema_version": schema_version,
        "policy": policy,
        "policy_version": policy_version,
        "generated_at": generated_at,
        "artifacts": artifact_descriptors,
        "bundle_sha256": bundle_descriptor_sha256(artifact_descriptors),
    }

    source_paths = tuple(
        sorted(
            {
                record["source_path"]
                for record in normalized_records
                if record.get("source_path")
            }
        )
    )
    return SnapshotBundle(
        release_facts=release_facts,
        manifest=manifest,
        privacy_receipt=privacy_receipt,
        release_facts_bytes=release_facts_bytes,
        manifest_bytes=canonical_json_bytes(manifest),
        privacy_receipt_bytes=privacy_receipt_bytes,
        bound_source_commit=bound_source_commit,
        source_event_paths=source_paths,
    )


def discover_public_snapshot(
    vault_root: Path,
    *,
    source_commit: str,
    generated_at: str,
    validated_overrides: Sequence[ValidatedOverride] = (),
) -> SnapshotBundle:
    """Discover the canonical mixed event union and build its public projection."""
    root = Path(vault_root)
    try:
        records = event_identity.load_event_union_records(root)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SnapshotContractError(f"canonical event union is invalid: {exc}") from exc
    try:
        receipts = release_receipt.load_release_receipts(root)
    except release_receipt.ReleaseReceiptError as exc:
        raise SnapshotContractError(f"committed release receipts are invalid: {exc}") from exc
    identities = load_agent_identities(root)
    return build_public_snapshot(
        records,
        identities,
        source_commit=source_commit,
        generated_at=generated_at,
        validated_overrides=validated_overrides,
        release_receipts=receipts,
    )


def _exact_keys(value: Any, expected: set[str], *, subject: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnapshotContractError(f"{subject} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise SnapshotContractError(
            f"{subject} fields differ from contract (missing={missing}, unknown={unknown})"
        )
    return value


def _validate_exact_source(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SnapshotContractError("override source.path_or_uid must be exact")
    if any(char in value for char in "*?[]{}") or "\\" in value:
        raise SnapshotContractError("wildcard override sources are forbidden")
    if UID8_RE.fullmatch(value):
        return value
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value.endswith("/")
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise SnapshotContractError("override source must be one exact repository path or UID")
    return value


def _validate_destination(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SnapshotContractError("public_destination must be exact")
    if any(ord(char) < 32 or char.isspace() for char in value):
        raise SnapshotContractError("public_destination contains unsafe whitespace")
    if any(char in value for char in "*?[]{}") or "\\" in value:
        raise SnapshotContractError("wildcard public destinations are forbidden")
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError as exc:
        raise SnapshotContractError("public_destination is malformed") from exc
    if parsed.scheme:
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed_port is not None
            or parsed.query
            or parsed.fragment
        ):
            raise SnapshotContractError("public_destination URL must be exact HTTPS")
        return value
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value.endswith("/")
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise SnapshotContractError(
            "public_destination must be one exact repository path or HTTPS URL"
        )
    return value


def _require_hash(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise SnapshotContractError(f"{field} must be an exact lowercase sha256")
    return value


def validate_override_descriptor(
    descriptor: Mapping[str, Any],
    *,
    expected_source_commit: str,
    actual_source_sha256: str,
    actual_selection_sha256: str,
    expected_destination: str,
    verified_approver: str,
    verified_reviewer: str,
) -> ValidatedOverride:
    """Validate one Mike-approved descriptor against independently computed evidence.

    The descriptor cannot establish its own truth: callers must supply hashes of
    the bytes they actually read and selected, plus the destination being built.
    This is what makes source, selection, review, and destination drift fail closed.
    """
    top = _exact_keys(
        descriptor,
        {
            "override_id",
            "source",
            "selection",
            "approved_by",
            "approved_at",
            "reason",
            "public_destination",
            "privacy_review",
        },
        subject="override descriptor",
    )
    override_id = top["override_id"]
    if not isinstance(override_id, str) or not UID8_RE.fullmatch(override_id):
        raise SnapshotContractError("override_id must be an 8-hex UID")

    source = _exact_keys(
        top["source"],
        {"path_or_uid", "git_commit", "sha256"},
        subject="override source",
    )
    _validate_exact_source(source["path_or_uid"])
    descriptor_commit = validate_source_commit(source["git_commit"])
    expected_commit = validate_source_commit(expected_source_commit)
    if descriptor_commit != expected_commit:
        raise SnapshotContractError("override source commit drifted")
    descriptor_source_hash = _require_hash(source["sha256"], field="source.sha256")
    evidence_source_hash = _require_hash(
        actual_source_sha256, field="actual_source_sha256"
    )
    if descriptor_source_hash != evidence_source_hash:
        raise SnapshotContractError("override source content drifted")

    selection_value = top["selection"]
    if not isinstance(selection_value, dict):
        raise SnapshotContractError("override selection must be an object")
    mode = selection_value.get("mode")
    if mode == "full-artifact":
        selection = _exact_keys(
            selection_value, {"mode"}, subject="full-artifact selection"
        )
    elif mode == "exact-fields":
        selection = _exact_keys(
            selection_value, {"mode", "fields"}, subject="exact-fields selection"
        )
        fields = selection["fields"]
        if (
            not isinstance(fields, list)
            or not fields
            or not all(
                isinstance(field, str) and FIELD_NAME_RE.fullmatch(field)
                for field in fields
            )
            or fields != sorted(set(fields))
        ):
            raise SnapshotContractError(
                "exact-fields selection must be a sorted, unique, non-wildcard field list"
            )
    elif mode == "exact-excerpt":
        selection = _exact_keys(
            selection_value,
            {"mode", "excerpt_sha256"},
            subject="exact-excerpt selection",
        )
        _require_hash(selection["excerpt_sha256"], field="selection.excerpt_sha256")
    else:
        raise SnapshotContractError("override selection mode is unknown")

    if (
        top["approved_by"] != "mike-maziarz"
        or verified_approver != "mike-maziarz"
    ):
        raise SnapshotContractError("override approval must be by mike-maziarz")
    approved_at = normalize_timestamp(top["approved_at"], field="approved_at")
    if approved_at != top["approved_at"]:
        raise SnapshotContractError("approved_at must be canonical UTC ISO-8601")
    reason = top["reason"]
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or reason != reason.strip()
        or len(reason) > 500
        or any(ord(char) < 32 for char in reason)
    ):
        raise SnapshotContractError("override reason must be bounded, exact text")

    destination = _validate_destination(top["public_destination"])
    if destination != _validate_destination(expected_destination):
        raise SnapshotContractError("override public destination drifted")

    review = _exact_keys(
        top["privacy_review"],
        {"reviewer", "verdict", "checked_sha256"},
        subject="override privacy_review",
    )
    reviewer = review["reviewer"]
    if not isinstance(reviewer, str) or not PRINCIPAL_RE.fullmatch(reviewer):
        raise SnapshotContractError("privacy reviewer must be an exact principal")
    if (
        not isinstance(verified_reviewer, str)
        or verified_reviewer != reviewer
        or not PRINCIPAL_RE.fullmatch(verified_reviewer)
    ):
        raise SnapshotContractError("privacy reviewer identity is not independently verified")
    if reviewer == top["approved_by"] or verified_reviewer == verified_approver:
        raise SnapshotContractError("self-approved privacy review is forbidden")
    if review["verdict"] != "pass":
        raise SnapshotContractError("override privacy review must pass")

    selection_hash = _require_hash(
        actual_selection_sha256, field="actual_selection_sha256"
    )
    checked_hash = _require_hash(
        review["checked_sha256"], field="privacy_review.checked_sha256"
    )
    if mode == "full-artifact" and selection_hash != evidence_source_hash:
        raise SnapshotContractError("full-artifact selection does not cover source bytes")
    if mode == "exact-excerpt" and selection["excerpt_sha256"] != selection_hash:
        raise SnapshotContractError("override excerpt selection drifted")
    if checked_hash != selection_hash:
        raise SnapshotContractError("privacy review covers different selection bytes")

    return ValidatedOverride(
        override_id=override_id,
        source_sha256=evidence_source_hash,
        selection_sha256=selection_hash,
        public_destination=destination,
    )


def _strict_json_loads(payload: bytes, *, name: str) -> Any:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SnapshotContractError(f"{name} is not UTF-8") from exc

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SnapshotContractError(f"{name} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=no_duplicates,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                SnapshotContractError(f"{name} contains non-finite number {constant}")
            ),
        )
    except SnapshotContractError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise SnapshotContractError(f"{name} is not valid JSON") from exc
    if canonical_json_bytes(value) != payload:
        raise SnapshotContractError(f"{name} is not canonical JSON")
    return value


def _validate_release_facts(value: Any) -> tuple[dict[str, Any], int]:
    release = _exact_keys(
        value,
        {"schema_version", "facts"},
        subject=RELEASE_FACTS_NAME,
    )
    if release["schema_version"] != SCHEMA_VERSION:
        raise SnapshotContractError("release-facts schema_version is unknown")
    facts = release["facts"]
    if not isinstance(facts, list):
        raise SnapshotContractError("release-facts facts must be an array")
    previous: Optional[tuple[str, str]] = None
    seen_ids: set[str] = set()
    for index, fact_value in enumerate(facts):
        if not isinstance(fact_value, dict):
            raise SnapshotContractError(f"release fact {index} must be an object")
        keys = set(fact_value)
        if (
            not RELEASE_FACT_REQUIRED_FIELDS <= keys
            or not keys <= RELEASE_FACT_FIELDS
        ):
            raise SnapshotContractError(f"release fact {index} fields violate allowlist")
        public_fact_id = fact_value["public_fact_id"]
        if (
            not isinstance(public_fact_id, str)
            or not PUBLIC_FACT_ID_RE.fullmatch(public_fact_id)
        ):
            raise SnapshotContractError("release fact public_fact_id is malformed")
        if public_fact_id in seen_ids:
            raise SnapshotContractError("release facts contain duplicate public_fact_id")
        seen_ids.add(public_fact_id)
        if fact_value["type"] not in ALLOWED_EVENT_TYPES:
            raise SnapshotContractError("release fact type is not allowlisted")
        occurred_at = normalize_timestamp(
            fact_value["occurred_at"], field="occurred_at"
        )
        if occurred_at != fact_value["occurred_at"]:
            raise SnapshotContractError("occurred_at is not canonical UTC ISO-8601")
        version = normalize_semver(fact_value["version"])
        if version != fact_value["version"]:
            raise SnapshotContractError("release fact version is not normalized")
        has_name = "agent_name" in fact_value
        has_generation = "agent_generation" in fact_value
        if has_name != has_generation:
            raise SnapshotContractError("optional attribution fields must appear together")
        if has_name:
            name = fact_value["agent_name"]
            generation = fact_value["agent_generation"]
            if not isinstance(name, str) or not AGENT_NAME_RE.fullmatch(name):
                raise SnapshotContractError("release fact agent_name is malformed")
            if not isinstance(generation, str) or not GENERATION_RE.fullmatch(generation):
                raise SnapshotContractError("release fact agent_generation is malformed")
        if "tag" in fact_value:
            _validate_tag(fact_value["tag"], version)
        if "public_url" in fact_value:
            validate_public_url(fact_value["public_url"], version=version)
        projected = {
            key: value
            for key, value in fact_value.items()
            if key != "public_fact_id"
        }
        if derive_public_fact_id(projected) != public_fact_id:
            raise SnapshotContractError(
                "public_fact_id does not derive from projected public fields"
            )
        order_key = (occurred_at, public_fact_id)
        if previous is not None and order_key <= previous:
            raise SnapshotContractError("release facts are not strictly sorted")
        previous = order_key
    return release, len(facts)


def _validate_manifest(
    value: Any,
    *,
    release_payload: bytes,
    receipt_payload: bytes,
    record_count: int,
) -> dict[str, Any]:
    manifest = _exact_keys(
        value,
        {
            "schema_version",
            "policy",
            "policy_version",
            "generated_at",
            "artifacts",
            "bundle_sha256",
        },
        subject=MANIFEST_NAME,
    )
    if (
        manifest["schema_version"] != SCHEMA_VERSION
        or manifest["policy"] != POLICY_NAME
        or manifest["policy_version"] != POLICY_VERSION
    ):
        raise SnapshotContractError("manifest policy or schema version is unknown")
    generated_at = normalize_timestamp(manifest["generated_at"], field="generated_at")
    if generated_at != manifest["generated_at"]:
        raise SnapshotContractError("manifest generated_at is not canonical UTC ISO-8601")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise SnapshotContractError(
            "manifest must describe release-facts.json and privacy-receipt.json"
        )
    normalized_artifacts = [
        _exact_keys(
            artifact,
            {"path", "sha256", "bytes", "records"},
            subject="manifest artifact",
        )
        for artifact in artifacts
    ]
    if any(
        not isinstance(artifact["path"], str)
        or not isinstance(artifact["sha256"], str)
        or not SHA256_RE.fullmatch(artifact["sha256"])
        or type(artifact["bytes"]) is not int
        or artifact["bytes"] < 0
        or type(artifact["records"]) is not int
        or artifact["records"] < 0
        for artifact in normalized_artifacts
    ):
        raise SnapshotContractError("manifest artifact descriptor fields are malformed")
    expected_artifacts = [
        {
            "path": RELEASE_FACTS_NAME,
            "sha256": sha256_bytes(release_payload),
            "bytes": len(release_payload),
            "records": record_count,
        },
        {
            "path": PRIVACY_RECEIPT_NAME,
            "sha256": sha256_bytes(receipt_payload),
            "bytes": len(receipt_payload),
            "records": 1,
        },
    ]
    if normalized_artifacts != expected_artifacts:
        raise SnapshotContractError("manifest artifact descriptors do not match bytes")
    expected_bundle_hash = bundle_descriptor_sha256(artifacts)
    if manifest["bundle_sha256"] != expected_bundle_hash:
        raise SnapshotContractError("manifest bundle_sha256 does not re-derive")
    return manifest


def _validate_privacy_receipt(
    value: Any,
    *,
    release_descriptor: Mapping[str, Any],
    record_count: int,
) -> dict[str, Any]:
    receipt = _exact_keys(
        value,
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
        subject=PRIVACY_RECEIPT_NAME,
    )
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["policy"] != POLICY_NAME
        or receipt["policy_version"] != POLICY_VERSION
        or receipt["exporter_version"] != EXPORTER_VERSION
    ):
        raise SnapshotContractError("privacy receipt policy or schema is unknown")
    if receipt["data_bundle_sha256"] != bundle_descriptor_sha256(
        [release_descriptor]
    ):
        raise SnapshotContractError(
            "privacy receipt data_bundle_sha256 does not re-derive"
        )
    crossed = _exact_keys(
        receipt["crossed"], {"release_facts"}, subject="privacy receipt crossed"
    )
    release_crossed = _exact_keys(
        crossed["release_facts"],
        {"count", "sha256"},
        subject="privacy receipt release_facts",
    )
    if (
        type(release_crossed["count"]) is not int
        or release_crossed["count"] != record_count
        or release_crossed["sha256"] != release_descriptor["sha256"]
    ):
        raise SnapshotContractError("privacy receipt crossed facts do not re-derive")

    held_back = receipt["held_back"]
    if not isinstance(held_back, list):
        raise SnapshotContractError("privacy receipt held_back must be an array")
    previous_bucket: Optional[str] = None
    for row_value in held_back:
        row = _exact_keys(
            row_value, {"bucket", "reason"}, subject="held-back row"
        )
        bucket = row["bucket"]
        if (
            not isinstance(bucket, str)
            or bucket not in HELD_BACK_POLICY
            or row["reason"] != HELD_BACK_POLICY[bucket]
        ):
            raise SnapshotContractError("held-back row is not a fixed policy bucket")
        if previous_bucket is not None and bucket <= previous_bucket:
            raise SnapshotContractError("held-back rows are not strictly sorted")
        previous_bucket = bucket

    overrides = receipt["overrides_consumed"]
    if overrides != []:
        raise SnapshotContractError("v1 privacy receipt cannot consume overrides")
    return receipt


def validate_bundle_bytes(
    files: Mapping[str, bytes],
    *,
    source_root: Optional[Path] = None,
    bound_source_commit: Optional[str] = None,
) -> dict[str, Any]:
    """Validate public bytes and optionally re-derive from an out-of-band source."""
    if set(files) != BUNDLE_FILENAMES:
        raise SnapshotContractError("bundle layout must contain exactly the three v1 files")
    if not all(isinstance(payload, bytes) for payload in files.values()):
        raise SnapshotContractError("bundle payloads must be bytes")

    release_value = _strict_json_loads(
        files[RELEASE_FACTS_NAME], name=RELEASE_FACTS_NAME
    )
    manifest_value = _strict_json_loads(files[MANIFEST_NAME], name=MANIFEST_NAME)
    receipt_value = _strict_json_loads(
        files[PRIVACY_RECEIPT_NAME], name=PRIVACY_RECEIPT_NAME
    )

    release, record_count = _validate_release_facts(release_value)
    manifest = _validate_manifest(
        manifest_value,
        release_payload=files[RELEASE_FACTS_NAME],
        receipt_payload=files[PRIVACY_RECEIPT_NAME],
        record_count=record_count,
    )
    release_hash = sha256_bytes(files[RELEASE_FACTS_NAME])
    release_descriptor = {
        "path": RELEASE_FACTS_NAME,
        "sha256": release_hash,
        "bytes": len(files[RELEASE_FACTS_NAME]),
        "records": record_count,
    }
    receipt = _validate_privacy_receipt(
        receipt_value,
        release_descriptor=release_descriptor,
        record_count=record_count,
    )

    if source_root is not None:
        if bound_source_commit is None:
            raise SnapshotContractError(
                "source re-derivation requires an out-of-band bound source commit"
            )
        bound_source_commit = validate_source_commit(bound_source_commit)
        expected = discover_public_snapshot(
            Path(source_root),
            source_commit=bound_source_commit,
            generated_at=manifest["generated_at"],
        )
        for name, expected_payload in expected.files.items():
            if files[name] != expected_payload:
                raise SnapshotContractError(
                    f"{name} does not match independent source re-derivation"
                )

    return {
        "policy": manifest["policy"],
        "records": record_count,
        "release_facts_sha256": release_hash,
        "bundle_sha256": manifest["bundle_sha256"],
        "held_back_buckets": [row["bucket"] for row in receipt["held_back"]],
        "overrides_consumed": list(receipt["overrides_consumed"]),
    }


def validate_bundle_directory(
    bundle_dir: Path,
    *,
    source_root: Optional[Path] = None,
    bound_source_commit: Optional[str] = None,
) -> dict[str, Any]:
    """Read and independently validate one on-disk v1 bundle."""
    directory = Path(bundle_dir)
    if not directory.is_dir() or directory.is_symlink():
        raise SnapshotContractError("bundle path must be a real directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILENAMES:
        raise SnapshotContractError("bundle directory has missing or extra entries")
    files: dict[str, bytes] = {}
    for entry in entries:
        entry_metadata = entry.lstat()
        if (
            not stat.S_ISREG(entry_metadata.st_mode)
            or entry_metadata.st_nlink != 1
        ):
            raise SnapshotContractError(
                "bundle entries must be unlinked regular files"
            )
        try:
            files[entry.name] = entry.read_bytes()
        except OSError as exc:
            raise SnapshotContractError(f"could not read {entry.name}") from exc
    return validate_bundle_bytes(
        files,
        source_root=source_root,
        bound_source_commit=bound_source_commit,
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _reject_symlink_chain(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise SnapshotContractError(
                "output path and all existing parents must not be symbolic links"
            )
        if not current.exists():
            break


def assert_safe_output_path(
    vault_root: Path,
    output_path: Path,
    *,
    source_event_paths: Sequence[str] = (),
) -> Path:
    """Return a lexical absolute output path or refuse aliases and unsafe scope."""
    root = Path(vault_root).resolve()
    output = Path(
        os.path.abspath(os.path.expanduser(str(Path(output_path))))
    )
    _reject_symlink_chain(output)
    resolved_output = output.resolve(strict=False)
    if resolved_output != output:
        raise SnapshotContractError("output path resolves through an unsafe alias")
    if output == root:
        raise SnapshotContractError("output cannot be the vault root")
    public_output_root = root / "02-outbox" / "web-v4"
    if output == public_output_root or not _is_relative_to(
        output, public_output_root
    ):
        raise SnapshotContractError(
            "output is allowed only below repository 02-outbox/web-v4/"
        )
    protected = [
        root / "vault",
        root / "agents",
        root / ".tropo",
        root / ".tropo-studio",
    ]
    for relative in source_event_paths:
        source = Path(relative)
        if source.is_absolute():
            protected.append(source.resolve())
        else:
            protected.append((root / source).resolve())
    for blocked in protected:
        blocked = blocked.resolve()
        if _is_relative_to(output, blocked) or _is_relative_to(blocked, output):
            raise SnapshotContractError(
                "output overlaps governed, agent-private, or source-event paths"
            )
    return output
