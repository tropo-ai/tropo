"""Pure Contract-C0 folder-sidecar codec, verifier, and graph adapter.

The module owns the closed record shape, exact canonical JSON bytes, hashes,
payload/record bijection checks, and deterministic graph projection.  It never
writes the filesystem.  Host portability policy and registered payload-type
lifecycle policy are dependency-injected so this module does not duplicate the
authorities that own those rules.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Container, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Optional, Protocol, Union

try:
    from .relation_registry import (
        RELATION_PREDICATES,
        RELATION_PREDICATE_SET,
        is_registered as is_registered_relation,
    )
except ImportError:  # direct path loading
    from relation_registry import (  # type: ignore
        RELATION_PREDICATES,
        RELATION_PREDICATE_SET,
        is_registered as is_registered_relation,
    )


if sys.version_info < (3, 9):  # pragma: no cover - portability floor guard
    raise RuntimeError(
        "Tropo Contract-C0 (folder_sidecar) requires Python >= 3.9; found "
        f"{sys.version_info.major}.{sys.version_info.minor}. Provision a 3.9+ "
        "interpreter before using the folder-sidecar toolchain."
    )


SCHEMA_ID: Final = "tropo.folder-sidecar/v1"
SCHEMA_VERSION: Final = 1
RECORD_NAMESPACE: Final = ".tropo/folder-sidecars/v1/records"
GRAPH_HASH_DOMAIN: Final[bytes] = b"tropo.c0-graph.v1\n"

FILE_UID_RE: Final = re.compile(
    r"^(?:[0-9a-f]{8}|[a-z0-9]{4,6}-[0-9a-f]{8})$"
)
VAULT_CODE_RE: Final = re.compile(r"^[a-z0-9]{4,6}$")
HASH_RE: Final = re.compile(r"^[0-9a-f]{64}$")
PAYLOAD_TYPE_RE: Final = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
BASE64_RE: Final = re.compile(
    r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$"
)

PAYLOAD_PROFILES: Final[frozenset[str]] = frozenset(
    {"directory", "text", "office", "image", "archive", "binary"}
)
EXTRACTION_SCOPES: Final[frozenset[str]] = frozenset(
    {"ship", "argo-reference", "argo-private", "external"}
)
RECORD_KINDS: Final[frozenset[str]] = frozenset({"file", "directory"})
STATES: Final[frozenset[str]] = frozenset({"active", "archived"})
INT64_MIN: Final = -(2**63)
INT64_MAX: Final = 2**63 - 1

# Profile-independent payload-path floor (dev-spec 372ffdda §Canonical layout +
# §Portability path rules 1-2/6). These components and shapes are NEVER legal in a
# payload path on any host, so the codec rejects them unconditionally — the optional
# PortabilityValidator layers host-specific Unicode/casefold/device policy on top and
# never substitutes for this floor.
RESERVED_PATH_COMPONENTS: Final[frozenset[str]] = frozenset(
    {".git", ".tropo", ".tropo-studio"}
)
DRIVE_PREFIX_RE: Final = re.compile(r"^[A-Za-z]:(?:/|$)")

C0_SCHEMA_INVALID: Final = "C0_SCHEMA_INVALID"
C0_NONCANONICAL_SERIALIZATION: Final = "C0_NONCANONICAL_SERIALIZATION"
C0_PAYLOAD_ORPHAN: Final = "C0_PAYLOAD_ORPHAN"
C0_SIDECAR_ORPHAN: Final = "C0_SIDECAR_ORPHAN"
C0_DIRECTORY_MISSING: Final = "C0_DIRECTORY_MISSING"
C0_HASH_MISMATCH: Final = "C0_HASH_MISMATCH"
C0_DUPLICATE_UID: Final = "C0_DUPLICATE_UID"
C0_DUPLICATE_PATH: Final = "C0_DUPLICATE_PATH"
C0_DUPLICATE_PROJECTION: Final = "C0_DUPLICATE_PROJECTION"
C0_PARENT_MISMATCH: Final = "C0_PARENT_MISMATCH"
C0_RELATION_INVALID: Final = "C0_RELATION_INVALID"
C0_PATH_INVALID: Final = "C0_PATH_INVALID"
C0_PORTABILITY_COLLISION: Final = "C0_PORTABILITY_COLLISION"
C0_SPECIAL_FILE: Final = "C0_SPECIAL_FILE"
C0_HARDLINK: Final = "C0_HARDLINK"


@dataclass(frozen=True)
class C0Finding:
    """One deterministic C0 refusal finding."""

    code: str
    path: str
    message: str


class C0Refusal(ValueError):
    """Base exception carrying a stable Contract-C0 refusal code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: str | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message
        rendered = f"{code}: {message}"
        if path is not None:
            rendered = f"{code}: {path}: {message}"
        super().__init__(rendered)


class C0ValidationError(C0Refusal):
    """A JSON value or sidecar record violates the C0 record contract."""


class C0VerificationError(C0Refusal):
    """An inventory fails C0 payload/record bijection."""

    def __init__(self, findings: Sequence[C0Finding]) -> None:
        if not findings:
            raise ValueError("C0VerificationError requires at least one finding")
        self.findings = tuple(findings)
        first = self.findings[0]
        super().__init__(first.code, first.message, path=first.path)


class PortabilityValidator(Protocol):
    """Injected path-policy adapter.

    It receives ``(payload_path, declared_portability_key, is_root)``.  It may
    raise, return ``False``, return the expected key, or return ``None``/``True``
    after successful validation.
    """

    def __call__(
        self,
        payload_path: str,
        declared_portability_key: str,
        is_root: bool,
        /,
    ) -> bool | str | None:
        ...


class PortabilityKey(Protocol):
    """Injected canonical portability-key derivation used by tree scanning."""

    def __call__(self, payload_path: str, is_root: bool, /) -> str:
        ...


class LifecycleValidator(Protocol):
    """Injected registered-capsule lifecycle validator."""

    def __call__(
        self,
        payload_type: str,
        status: str,
        state: str,
        stage: str | None,
        /,
    ) -> bool | None:
        ...


@dataclass(frozen=True)
class LifecycleRule:
    """Optional pure lifecycle rule carried by a payload-type registry entry."""

    statuses: frozenset[str] | None = None
    states: frozenset[str] = STATES
    stages: frozenset[str] | None = None
    stage_required: bool = False
    stage_allowed: bool = True


PayloadTypeRegistry = Union[
    Mapping[str, Optional[LifecycleRule]],
    Container[str],
    Callable[[str], Union[bool, LifecycleRule, None]],
]
_REGISTRY_REQUIRED = object()


@dataclass(frozen=True)
class Provenance:
    at: str
    precision: str
    by: str

    def to_mapping(self) -> dict[str, str]:
        return {"at": self.at, "precision": self.precision, "by": self.by}


@dataclass(frozen=True, order=True)
class Relation:
    predicate: str
    target_uid: str

    def to_mapping(self) -> dict[str, str]:
        return {"predicate": self.predicate, "target_uid": self.target_uid}


JsonScalar = Union[None, bool, int, str]
JsonValue = Union[JsonScalar, tuple["JsonValue", ...], Mapping[str, "JsonValue"]]


@dataclass(frozen=True)
class FolderSidecarRecord:
    schema_id: str
    schema_version: int
    record_kind: str
    uid: str
    parent_uid: str
    payload_path: str
    payload_path_bytes_b64: str
    payload_portability_key: str
    payload_profile: str
    payload_type: str
    status: str
    state: str
    owner_uid: str
    audience_group_uid: str
    extraction_scope: str
    relations: tuple[Relation, ...]
    created: Provenance
    modified: Provenance
    payload_sha256: str | None = None
    stage: str | None = None
    source_projection_uid: str | None = None
    source_projection_sha256: str | None = None
    extensions: Mapping[str, JsonValue] | None = None

    @property
    def is_root(self) -> bool:
        return self.payload_path == ""

    @property
    def payload_path_bytes(self) -> bytes:
        return self.payload_path.encode("utf-8", errors="strict")

    @property
    def record_filename(self) -> str:
        return f"{self.uid}.json"

    @property
    def record_path(self) -> str:
        return f"{RECORD_NAMESPACE}/{self.record_filename}"

    def to_mapping(self) -> dict[str, Any]:
        """Return a fresh mutable JSON-domain mapping."""

        result: dict[str, Any] = {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "record_kind": self.record_kind,
            "uid": self.uid,
            "parent_uid": self.parent_uid,
            "payload_path": self.payload_path,
            "payload_path_bytes_b64": self.payload_path_bytes_b64,
            "payload_portability_key": self.payload_portability_key,
            "payload_profile": self.payload_profile,
            "payload_type": self.payload_type,
            "status": self.status,
            "state": self.state,
            "owner_uid": self.owner_uid,
            "audience_group_uid": self.audience_group_uid,
            "extraction_scope": self.extraction_scope,
            "relations": [relation.to_mapping() for relation in self.relations],
            "created": self.created.to_mapping(),
            "modified": self.modified.to_mapping(),
        }
        if self.record_kind == "file":
            result["payload_sha256"] = self.payload_sha256
        if self.stage is not None:
            result["stage"] = self.stage
        if self.source_projection_uid is not None:
            result["source_projection_uid"] = self.source_projection_uid
            result["source_projection_sha256"] = self.source_projection_sha256
        if self.extensions is not None:
            result["extensions"] = _thaw_json(self.extensions)
        return result


@dataclass(frozen=True)
class RecordEnvelope:
    """A validated canonical record plus its exact bytes and digest."""

    record: FolderSidecarRecord
    raw_bytes: bytes
    sha256: str
    filename: str | None = None


@dataclass(frozen=True)
class PayloadEntry:
    """One trusted/scanned physical payload inventory row."""

    payload_path: str
    record_kind: str
    payload_path_bytes: bytes
    payload_portability_key: str
    payload_sha256: str | None = None

    @property
    def payload_path_bytes_b64(self) -> str:
        return base64.b64encode(self.payload_path_bytes).decode("ascii")

    @classmethod
    def directory(
        cls,
        payload_path: str,
        payload_portability_key: str,
        *,
        payload_path_bytes: bytes | None = None,
    ) -> "PayloadEntry":
        path_bytes = (
            payload_path.encode("utf-8", errors="strict")
            if payload_path_bytes is None
            else bytes(payload_path_bytes)
        )
        return cls(
            payload_path,
            "directory",
            path_bytes,
            payload_portability_key,
            None,
        )

    @classmethod
    def file(
        cls,
        payload_path: str,
        payload_bytes: bytes,
        payload_portability_key: str,
        *,
        payload_path_bytes: bytes | None = None,
    ) -> "PayloadEntry":
        path_bytes = (
            payload_path.encode("utf-8", errors="strict")
            if payload_path_bytes is None
            else bytes(payload_path_bytes)
        )
        return cls(
            payload_path,
            "file",
            path_bytes,
            payload_portability_key,
            payload_sha256(payload_bytes),
        )

    @classmethod
    def file_hash(
        cls,
        payload_path: str,
        digest: str,
        payload_portability_key: str,
        *,
        payload_path_bytes: bytes | None = None,
    ) -> "PayloadEntry":
        path_bytes = (
            payload_path.encode("utf-8", errors="strict")
            if payload_path_bytes is None
            else bytes(payload_path_bytes)
        )
        return cls(
            payload_path,
            "file",
            path_bytes,
            payload_portability_key,
            digest,
        )


@dataclass(frozen=True)
class VerificationResult:
    records: tuple[RecordEnvelope, ...]
    payloads: tuple[PayloadEntry, ...]
    record_sha256_by_uid: Mapping[str, str]
    payload_sha256_by_uid: Mapping[str, str | None]


PROJECTION_ROW_KEYS: Final[tuple[str, ...]] = (
    "uid",
    "type",
    "title",
    "status",
    "state",
    "stage",
    "created",
    "modified",
    "created_by",
    "modified_by",
    "path",
    "record_kind",
    "parent_uid",
    "owner_uid",
    "audience_group_uid",
    "extraction_scope",
    "record_sha256",
    "payload_sha256",
    "hash_function",
    "governance",
    "source_sidecar",
    "vault_uid",
    "segment",
)
PROJECTION_EDGE_KEYS: Final[tuple[str, ...]] = (
    "source_uid",
    "predicate",
    "target_uid",
    "vault_uid",
)


@dataclass(frozen=True)
class GraphProjection:
    rows: tuple[Mapping[str, Any], ...]
    edges: tuple[Mapping[str, Any], ...]
    row_jsonl: bytes
    edge_jsonl: bytes
    sha256: str


class _DuplicateKeyError(ValueError):
    pass


class _JsonDomainError(ValueError):
    pass


def _strict_utf8(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise C0ValidationError(C0_SCHEMA_INVALID, f"{field} must be a string")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field} must contain only Unicode scalar values",
        ) from exc
    return value


def _contains_control(value: str) -> bool:
    return any(ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F for char in value)


def _bounded_text(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
    no_controls: bool = False,
) -> str:
    text = _strict_utf8(value, field)
    if len(text) < minimum or (maximum is not None and len(text) > maximum):
        bound = f"{minimum}..{maximum}" if maximum is not None else f">={minimum}"
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field} length must be {bound} characters",
        )
    if no_controls and _contains_control(text):
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field} may not contain control characters",
        )
    return text


def is_file_uid(value: object) -> bool:
    return isinstance(value, str) and FILE_UID_RE.fullmatch(value) is not None


def is_vault_code(value: object) -> bool:
    return isinstance(value, str) and VAULT_CODE_RE.fullmatch(value) is not None


def require_file_uid(value: object, field: str = "uid") -> str:
    if not is_file_uid(value):
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field} must be private 8-lowercase-hex or "
            "team <4-6 lowercase-alphanumeric>-<8hex>",
        )
    return value


def require_vault_code(value: object, field: str = "vault_uid") -> str:
    if not is_vault_code(value):
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field} must be 4-6 lowercase alphanumeric characters",
        )
    return value


def _require_hash(value: object, field: str) -> str:
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field} must be exactly 64 lowercase hexadecimal characters",
        )
    return value


def _validate_json_domain(
    value: object,
    *,
    field: str = "$",
    active: set[int] | None = None,
) -> None:
    if value is None or isinstance(value, (bool, str)):
        if isinstance(value, str):
            _strict_utf8(value, field)
        return
    if isinstance(value, int):
        if not INT64_MIN <= value <= INT64_MAX:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"{field} integer is outside signed 64-bit range",
            )
        return
    if isinstance(value, float):
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field} floats are prohibited",
        )

    if active is None:
        active = set()
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise C0ValidationError(C0_SCHEMA_INVALID, f"{field} contains a cycle")
        active.add(identity)
        try:
            try:
                items = list(value.items())
            except Exception as exc:
                raise C0ValidationError(
                    C0_SCHEMA_INVALID,
                    f"{field} is not a stable JSON object",
                ) from exc
            for key, child in items:
                if not isinstance(key, str):
                    raise C0ValidationError(
                        C0_SCHEMA_INVALID,
                        f"{field} object keys must be strings",
                    )
                _strict_utf8(key, f"{field} object key")
                _validate_json_domain(
                    child,
                    field=f"{field}.{key}",
                    active=active,
                )
        finally:
            active.remove(identity)
        return

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            raise C0ValidationError(C0_SCHEMA_INVALID, f"{field} contains a cycle")
        active.add(identity)
        try:
            for index, child in enumerate(value):
                _validate_json_domain(
                    child,
                    field=f"{field}[{index}]",
                    active=active,
                )
        finally:
            active.remove(identity)
        return

    raise C0ValidationError(
        C0_SCHEMA_INVALID,
        f"{field} contains non-JSON value {type(value).__name__}",
    )


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _parse_json_int(token: str) -> int:
    value = int(token, 10)
    if not INT64_MIN <= value <= INT64_MAX:
        raise _JsonDomainError(f"integer {token} is outside signed 64-bit range")
    return value


def _reject_json_float(token: str) -> Any:
    raise _JsonDomainError(f"floating-point value {token} is prohibited")


def _reject_json_constant(token: str) -> Any:
    raise _JsonDomainError(f"non-JSON numeric constant {token} is prohibited")


def decode_json_strict(raw: bytes | bytearray | memoryview) -> Any:
    """Decode strict UTF-8 JSON with duplicate keys and floats rejected."""

    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            "JSON input must be bytes",
        )
    source = bytes(raw)
    if source.startswith(b"\xef\xbb\xbf"):
        raise C0ValidationError(C0_SCHEMA_INVALID, "UTF-8 BOM is prohibited")
    try:
        text = source.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_int=_parse_json_int,
            parse_float=_reject_json_float,
            parse_constant=_reject_json_constant,
        )
        _validate_json_domain(value)
        return value
    except C0ValidationError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateKeyError,
        _JsonDomainError,
        RecursionError,
        ValueError,
    ) as exc:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"invalid strict JSON: {exc}",
        ) from exc


def _escape_json_string(value: str) -> str:
    _strict_utf8(value, "JSON string")
    parts = ['"']
    named = {
        '"': r"\"",
        "\\": r"\\",
        "\b": r"\b",
        "\t": r"\t",
        "\n": r"\n",
        "\f": r"\f",
        "\r": r"\r",
    }
    for char in value:
        escaped = named.get(char)
        if escaped is not None:
            parts.append(escaped)
        elif ord(char) <= 0x1F:
            parts.append(f"\\u00{ord(char):02x}")
        else:
            parts.append(char)
    parts.append('"')
    return "".join(parts)


def _encode_json_text(
    value: object,
    *,
    sort_objects: bool,
    active: set[int] | None = None,
) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if not INT64_MIN <= value <= INT64_MAX:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                "integer is outside signed 64-bit range",
            )
        return str(value)
    if isinstance(value, float):
        raise C0ValidationError(C0_SCHEMA_INVALID, "floats are prohibited")
    if isinstance(value, str):
        return _escape_json_string(value)

    if active is None:
        active = set()
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise C0ValidationError(C0_SCHEMA_INVALID, "JSON object contains a cycle")
        active.add(identity)
        try:
            items = list(value.items())
            for key, _child in items:
                if not isinstance(key, str):
                    raise C0ValidationError(
                        C0_SCHEMA_INVALID,
                        "JSON object keys must be strings",
                    )
                _strict_utf8(key, "JSON object key")
            if sort_objects:
                items.sort(key=lambda item: item[0].encode("utf-8"))
            encoded = (
                _escape_json_string(key)
                + ":"
                + _encode_json_text(
                    child,
                    sort_objects=sort_objects,
                    active=active,
                )
                for key, child in items
            )
            return "{" + ",".join(encoded) + "}"
        finally:
            active.remove(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            raise C0ValidationError(C0_SCHEMA_INVALID, "JSON array contains a cycle")
        active.add(identity)
        try:
            return "[" + ",".join(
                _encode_json_text(
                    child,
                    sort_objects=sort_objects,
                    active=active,
                )
                for child in value
            ) + "]"
        finally:
            active.remove(identity)

    raise C0ValidationError(
        C0_SCHEMA_INVALID,
        f"non-JSON value {type(value).__name__}",
    )


def canonical_json_bytes(value: object, *, trailing_lf: bool = True) -> bytes:
    """Encode C0 canonical JSON.

    Object keys sort by unsigned UTF-8 bytes.  Strings follow RFC-8785
    primitive escaping, Unicode is otherwise unescaped, integers are signed
    64-bit shortest decimal, and floats are prohibited.
    """

    try:
        rendered = _encode_json_text(value, sort_objects=True)
        return rendered.encode("utf-8") + (b"\n" if trailing_lf else b"")
    except C0ValidationError:
        raise
    except (RecursionError, RuntimeError, UnicodeError, ValueError) as exc:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"value cannot be encoded as canonical C0 JSON: {exc}",
        ) from exc


def _ordered_json_bytes(value: Mapping[str, Any], *, trailing_lf: bool) -> bytes:
    try:
        rendered = _encode_json_text(value, sort_objects=False)
        return rendered.encode("utf-8") + (b"\n" if trailing_lf else b"")
    except C0ValidationError:
        raise
    except (RecursionError, RuntimeError, UnicodeError, ValueError) as exc:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"value cannot be encoded as ordered C0 JSON: {exc}",
        ) from exc


def _freeze_json(value: Any) -> JsonValue:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json(child) for key, child in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value: JsonValue) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


_COMMON_REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_id",
        "schema_version",
        "record_kind",
        "uid",
        "parent_uid",
        "payload_path",
        "payload_path_bytes_b64",
        "payload_portability_key",
        "payload_profile",
        "payload_type",
        "status",
        "state",
        "owner_uid",
        "audience_group_uid",
        "extraction_scope",
        "relations",
        "created",
        "modified",
    }
)
_OPTIONAL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "payload_sha256",
        "stage",
        "source_projection_uid",
        "source_projection_sha256",
        "extensions",
    }
)
_ALLOWED_KEYS: Final = _COMMON_REQUIRED_KEYS | _OPTIONAL_KEYS
_PROVENANCE_KEYS: Final = frozenset({"at", "precision", "by"})
_RELATION_KEYS: Final = frozenset({"predicate", "target_uid"})


def _closed_mapping(
    value: object,
    *,
    field: str,
    required: frozenset[str],
    allowed: frozenset[str],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise C0ValidationError(C0_SCHEMA_INVALID, f"{field} must be an object")
    keys = list(value.keys())
    if any(not isinstance(key, str) for key in keys):
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field} keys must all be strings",
        )
    key_set = frozenset(keys)
    missing = sorted(required - key_set)
    unknown = sorted(key_set - allowed)
    if missing or unknown:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field} has missing={missing}, unknown={unknown}",
        )
    return value


def _validate_provenance(value: object, field: str) -> Provenance:
    block = _closed_mapping(
        value,
        field=field,
        required=_PROVENANCE_KEYS,
        allowed=_PROVENANCE_KEYS,
    )
    at = _strict_utf8(block["at"], f"{field}.at")
    precision = block["precision"]
    if precision not in {"day", "second"}:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field}.precision must be 'day' or 'second'",
        )
    try:
        if precision == "day":
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", at) is None:
                raise ValueError("wrong day shape")
            date.fromisoformat(at)
        else:
            if re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                at,
            ) is None:
                raise ValueError("wrong second shape")
            datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, ValueError) as exc:
        expected = "YYYY-MM-DD" if precision == "day" else "YYYY-MM-DDTHH:MM:SSZ"
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{field}.at must be a real UTC {expected} value",
        ) from exc
    by = _bounded_text(
        block["by"],
        f"{field}.by",
        minimum=1,
        maximum=200,
        no_controls=True,
    )
    return Provenance(at=at, precision=precision, by=by)


def _reference_uid(value: object, field: str) -> str:
    if not isinstance(value, str) or not (
        is_file_uid(value) or is_vault_code(value)
    ):
        raise C0ValidationError(
            C0_RELATION_INVALID,
            f"{field} must be a canonical file UID or vault code",
        )
    return value


def _validate_relations(value: object) -> tuple[Relation, ...]:
    if not isinstance(value, (list, tuple)):
        raise C0ValidationError(
            C0_RELATION_INVALID,
            "relations must be an array",
        )
    relations: list[Relation] = []
    for index, candidate in enumerate(value):
        block = _closed_mapping(
            candidate,
            field=f"relations[{index}]",
            required=_RELATION_KEYS,
            allowed=_RELATION_KEYS,
        )
        predicate = block["predicate"]
        if not is_registered_relation(predicate):
            raise C0ValidationError(
                C0_RELATION_INVALID,
                f"relations[{index}].predicate is not in the shipped registry",
            )
        target_uid = _reference_uid(
            block["target_uid"],
            f"relations[{index}].target_uid",
        )
        relations.append(Relation(predicate, target_uid))

    pairs = [(relation.predicate, relation.target_uid) for relation in relations]
    if len(set(pairs)) != len(pairs):
        raise C0ValidationError(
            C0_RELATION_INVALID,
            "relation predicate/target pairs must be unique",
        )
    expected = sorted(
        relations,
        key=lambda relation: (
            relation.predicate.encode("utf-8"),
            relation.target_uid.encode("utf-8"),
        ),
    )
    if relations != expected:
        raise C0ValidationError(
            C0_RELATION_INVALID,
            "relations must sort by predicate and then target UID",
        )
    return tuple(relations)


def _decode_path_bytes(path: str, encoded: object) -> str:
    text = _strict_utf8(encoded, "payload_path_bytes_b64")
    if BASE64_RE.fullmatch(text) is None:
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload_path_bytes_b64 is not canonical padded RFC 4648 base64",
        )
    try:
        decoded = base64.b64decode(text.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload_path_bytes_b64 cannot be decoded as strict base64",
        ) from exc
    canonical = base64.b64encode(decoded).decode("ascii")
    if canonical != text:
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload_path_bytes_b64 has noncanonical padding or pad bits",
        )
    if decoded != path.encode("utf-8", errors="strict"):
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload_path_bytes_b64 does not encode payload_path's UTF-8 bytes",
        )
    return text


def _resolve_payload_type(
    payload_type: str,
    registry: PayloadTypeRegistry | object,
) -> LifecycleRule | None:
    if registry is _REGISTRY_REQUIRED or registry is None:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            "a pinned registered_payload_types authority is required",
        )
    try:
        if isinstance(registry, Mapping):
            if payload_type not in registry:
                raise C0ValidationError(
                    C0_SCHEMA_INVALID,
                    f"payload_type {payload_type!r} is not registered",
                )
            rule = registry[payload_type]
            if rule is not None and not isinstance(rule, LifecycleRule):
                raise C0ValidationError(
                    C0_SCHEMA_INVALID,
                    f"payload type registry entry {payload_type!r} is malformed",
                )
            return rule
        if callable(registry):
            result = registry(payload_type)
            if isinstance(result, LifecycleRule):
                return result
            if result is True:
                return None
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"payload_type {payload_type!r} is not registered",
            )
        if isinstance(registry, (str, bytes)):
            raise TypeError("registry cannot be a string")
        if payload_type not in registry:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"payload_type {payload_type!r} is not registered",
            )
        return None
    except C0ValidationError:
        raise
    except Exception as exc:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"payload type registry could not validate {payload_type!r}: {exc}",
        ) from exc


def _validate_lifecycle(
    *,
    payload_type: str,
    status: object,
    state: object,
    stage: object,
    stage_present: bool,
    rule: LifecycleRule | None,
    validator: LifecycleValidator | None,
) -> tuple[str, str, str | None]:
    status_text = _bounded_text(
        status,
        "status",
        minimum=1,
        maximum=200,
        no_controls=True,
    )
    state_text = _bounded_text(
        state,
        "state",
        minimum=1,
        maximum=200,
        no_controls=True,
    )
    if state_text not in STATES:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"state must be one of {sorted(STATES)}",
        )
    stage_text = (
        _bounded_text(
            stage,
            "stage",
            minimum=1,
            maximum=200,
            no_controls=True,
        )
        if stage_present
        else None
    )

    if rule is not None:
        if rule.statuses is not None and status_text not in rule.statuses:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"status {status_text!r} is invalid for payload_type {payload_type!r}",
            )
        if state_text not in rule.states:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"state {state_text!r} is invalid for payload_type {payload_type!r}",
            )
        if rule.stage_required and stage_text is None:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"stage is required for payload_type {payload_type!r}",
            )
        if not rule.stage_allowed and stage_text is not None:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"stage is prohibited for payload_type {payload_type!r}",
            )
        if (
            stage_text is not None
            and rule.stages is not None
            and stage_text not in rule.stages
        ):
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"stage {stage_text!r} is invalid for payload_type {payload_type!r}",
            )

    if validator is not None:
        try:
            outcome = validator(payload_type, status_text, state_text, stage_text)
        except C0Refusal:
            raise
        except Exception as exc:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"lifecycle authority refused {payload_type!r}: {exc}",
            ) from exc
        if outcome is False:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"lifecycle fields are invalid for payload_type {payload_type!r}",
            )
    return status_text, state_text, stage_text


def _validate_core_path_syntax(value: str, *, field: str) -> None:
    """Enforce the profile-independent payload-path grammar unconditionally.

    Closes the P0 where a record validated with ``portability_validator=None``
    accepted traversal, absolute, backslash, drive, empty-segment, dot/dot-dot,
    and reserved-namespace paths — the injected validator was the ONLY gate and
    it is optional. This floor holds on every host; the injected authority adds
    NFKC casefold collision keys, device stems, and Windows-forbidden characters
    on top of it, never in place of it. The empty root path is validated by the
    caller and never reaches this function.
    """

    if _contains_control(value):
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"{field} may not contain NUL or control characters",
            path=value,
        )
    if value.startswith("/"):
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"{field} must be payload-root-relative (no leading slash)",
            path=value,
        )
    if "\\" in value:
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"{field} may not contain a backslash",
            path=value,
        )
    if DRIVE_PREFIX_RE.match(value):
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"{field} may not carry a drive-letter prefix",
            path=value,
        )
    for segment in value.split("/"):
        if segment == "":
            raise C0ValidationError(
                C0_PATH_INVALID,
                f"{field} may not contain an empty or repeated separator",
                path=value,
            )
        if segment in (".", ".."):
            raise C0ValidationError(
                C0_PATH_INVALID,
                f"{field} may not contain a dot or dot-dot segment",
                path=value,
            )
        if segment in RESERVED_PATH_COMPONENTS:
            raise C0ValidationError(
                C0_PATH_INVALID,
                f"{field} may not include reserved component {segment!r}",
                path=value,
            )


def _validate_portability(
    path: str,
    key: str,
    is_root: bool,
    validator: PortabilityValidator | None,
) -> None:
    if not is_root:
        _validate_core_path_syntax(path, field="payload_path")
        _validate_core_path_syntax(key, field="payload_portability_key")
    if validator is None:
        return
    try:
        outcome = validator(path, key, is_root)
    except C0Refusal:
        raise
    except Exception as exc:
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"portability authority refused {path!r}: {exc}",
        ) from exc
    if outcome is False:
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"portability authority refused {path!r}",
        )
    if isinstance(outcome, str) and outcome != key:
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"payload_portability_key does not match authority for {path!r}",
        )


def _validate_record_inner(
    value: object,
    *,
    registered_payload_types: PayloadTypeRegistry | object,
    lifecycle_validator: LifecycleValidator | None,
    portability_validator: PortabilityValidator | None,
    record_filename: str | None,
) -> FolderSidecarRecord:
    block = _closed_mapping(
        value,
        field="record",
        required=_COMMON_REQUIRED_KEYS,
        allowed=_ALLOWED_KEYS,
    )
    if block["schema_id"] != SCHEMA_ID:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"schema_id must be {SCHEMA_ID!r}",
        )
    version = block["schema_version"]
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"schema_version must be integer {SCHEMA_VERSION}",
        )
    kind = block["record_kind"]
    if kind not in RECORD_KINDS:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"record_kind must be one of {sorted(RECORD_KINDS)}",
        )
    uid = require_file_uid(block["uid"])
    if record_filename is not None:
        filename = _strict_utf8(record_filename, "record filename")
        if "/" in filename or "\\" in filename or filename != f"{uid}.json":
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"record filename must be exactly {uid}.json",
            )

    path = _strict_utf8(block["payload_path"], "payload_path")
    is_root = path == ""
    if is_root and kind != "directory":
        raise C0ValidationError(
            C0_PATH_INVALID,
            "the empty payload path is legal only for the directory root record",
        )
    encoded_path = _decode_path_bytes(path, block["payload_path_bytes_b64"])
    portability_key = _strict_utf8(
        block["payload_portability_key"],
        "payload_portability_key",
    )
    if is_root:
        if encoded_path != "" or portability_key != "":
            raise C0ValidationError(
                C0_PATH_INVALID,
                "root path, path base64, and portability key must all be empty",
            )
    elif portability_key == "":
        raise C0ValidationError(
            C0_PATH_INVALID,
            "non-root payload_portability_key must be non-empty",
        )
    _validate_portability(path, portability_key, is_root, portability_validator)

    parent_uid = block["parent_uid"]
    if is_root:
        try:
            parent_uid = require_vault_code(parent_uid, "parent_uid")
        except C0ValidationError as exc:
            raise C0ValidationError(
                C0_PARENT_MISMATCH,
                "root parent_uid must be the canonical 4-6 character vault code",
            ) from exc
    else:
        try:
            parent_uid = require_file_uid(parent_uid, "parent_uid")
        except C0ValidationError as exc:
            raise C0ValidationError(
                C0_PARENT_MISMATCH,
                "non-root parent_uid must be a canonical file UID",
            ) from exc

    profile = block["payload_profile"]
    if profile not in PAYLOAD_PROFILES:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"payload_profile must be one of {sorted(PAYLOAD_PROFILES)}",
        )
    if kind == "directory" and profile != "directory":
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            "directory records require payload_profile 'directory'",
        )
    if kind == "file" and profile == "directory":
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            "file records prohibit payload_profile 'directory'",
        )

    has_payload_hash = "payload_sha256" in block
    if kind == "file":
        if not has_payload_hash:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                "file records require payload_sha256",
            )
        payload_hash = _require_hash(block["payload_sha256"], "payload_sha256")
    else:
        if has_payload_hash:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                "directory records prohibit payload_sha256",
            )
        payload_hash = None

    payload_type = _bounded_text(
        block["payload_type"],
        "payload_type",
        minimum=1,
        maximum=200,
        no_controls=True,
    )
    if PAYLOAD_TYPE_RE.fullmatch(payload_type) is None:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            "payload_type must be a lowercase capsule-type slug",
        )
    type_rule = _resolve_payload_type(payload_type, registered_payload_types)
    status, state, stage = _validate_lifecycle(
        payload_type=payload_type,
        status=block["status"],
        state=block["state"],
        stage=block.get("stage"),
        stage_present="stage" in block,
        rule=type_rule,
        validator=lifecycle_validator,
    )

    owner_uid = require_file_uid(block["owner_uid"], "owner_uid")
    audience_group_uid = require_file_uid(
        block["audience_group_uid"],
        "audience_group_uid",
    )
    scope = block["extraction_scope"]
    if scope not in EXTRACTION_SCOPES:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"extraction_scope must be one of {sorted(EXTRACTION_SCOPES)}",
        )

    relations = _validate_relations(block["relations"])
    if Relation("member_of", parent_uid) not in relations:
        raise C0ValidationError(
            C0_PARENT_MISMATCH,
            "relations must contain member_of targeting parent_uid",
        )

    created = _validate_provenance(block["created"], "created")
    modified = _validate_provenance(block["modified"], "modified")

    source_uid_present = "source_projection_uid" in block
    source_hash_present = "source_projection_sha256" in block
    if source_uid_present != source_hash_present:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            "source_projection_uid and source_projection_sha256 must occur together",
        )
    source_uid = (
        require_file_uid(block["source_projection_uid"], "source_projection_uid")
        if source_uid_present
        else None
    )
    source_hash = (
        _require_hash(
            block["source_projection_sha256"],
            "source_projection_sha256",
        )
        if source_hash_present
        else None
    )

    extensions: Mapping[str, JsonValue] | None = None
    if "extensions" in block:
        extension_value = block["extensions"]
        if not isinstance(extension_value, Mapping):
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                "extensions must be an object",
            )
        _validate_json_domain(extension_value, field="extensions")
        extensions = _freeze_json(extension_value)  # type: ignore[assignment]

    return FolderSidecarRecord(
        schema_id=SCHEMA_ID,
        schema_version=SCHEMA_VERSION,
        record_kind=kind,
        uid=uid,
        parent_uid=parent_uid,
        payload_path=path,
        payload_path_bytes_b64=encoded_path,
        payload_portability_key=portability_key,
        payload_profile=profile,
        payload_type=payload_type,
        status=status,
        state=state,
        owner_uid=owner_uid,
        audience_group_uid=audience_group_uid,
        extraction_scope=scope,
        relations=relations,
        created=created,
        modified=modified,
        payload_sha256=payload_hash,
        stage=stage,
        source_projection_uid=source_uid,
        source_projection_sha256=source_hash,
        extensions=extensions,
    )


def validate_record(
    value: object,
    *,
    registered_payload_types: PayloadTypeRegistry | object = _REGISTRY_REQUIRED,
    lifecycle_validator: LifecycleValidator | None = None,
    portability_validator: PortabilityValidator | None = None,
    record_filename: str | None = None,
) -> FolderSidecarRecord:
    """Validate a decoded record without mutating it."""

    try:
        return _validate_record_inner(
            value,
            registered_payload_types=registered_payload_types,
            lifecycle_validator=lifecycle_validator,
            portability_validator=portability_validator,
            record_filename=record_filename,
        )
    except C0Refusal:
        raise
    except Exception as exc:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"record validation failed closed: {exc}",
        ) from exc


def canonical_record_bytes(
    record: FolderSidecarRecord | Mapping[str, Any],
    *,
    registered_payload_types: PayloadTypeRegistry | object = _REGISTRY_REQUIRED,
    lifecycle_validator: LifecycleValidator | None = None,
    portability_validator: PortabilityValidator | None = None,
    record_filename: str | None = None,
) -> bytes:
    """Return exact canonical UTF-8 record bytes ending in one LF."""

    if isinstance(record, FolderSidecarRecord):
        validated = record
    else:
        validated = validate_record(
            record,
            registered_payload_types=registered_payload_types,
            lifecycle_validator=lifecycle_validator,
            portability_validator=portability_validator,
            record_filename=record_filename,
        )
    return canonical_json_bytes(validated.to_mapping())


def parse_record(
    raw: bytes | bytearray | memoryview,
    *,
    registered_payload_types: PayloadTypeRegistry | object = _REGISTRY_REQUIRED,
    lifecycle_validator: LifecycleValidator | None = None,
    portability_validator: PortabilityValidator | None = None,
    record_filename: str | None = None,
    require_canonical: bool = True,
) -> FolderSidecarRecord:
    """Decode and totally validate one C0 sidecar record."""

    source = bytes(raw) if isinstance(raw, (bytes, bytearray, memoryview)) else raw
    decoded = decode_json_strict(source)  # type: ignore[arg-type]
    record = validate_record(
        decoded,
        registered_payload_types=registered_payload_types,
        lifecycle_validator=lifecycle_validator,
        portability_validator=portability_validator,
        record_filename=record_filename,
    )
    canonical = canonical_record_bytes(record)
    if require_canonical and source != canonical:
        raise C0ValidationError(
            C0_NONCANONICAL_SERIALIZATION,
            "valid record bytes do not equal canonical compact JSON plus one LF",
        )
    return record


def envelope_record(
    record: FolderSidecarRecord,
    *,
    filename: str | None = None,
) -> RecordEnvelope:
    """Wrap a validated record in a canonical exact-byte envelope."""

    raw = canonical_record_bytes(record)
    if filename is not None and filename != record.record_filename:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"record filename must be exactly {record.record_filename}",
        )
    return RecordEnvelope(
        record=record,
        raw_bytes=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
        filename=filename,
    )


def parse_record_envelope(
    raw: bytes | bytearray | memoryview,
    *,
    registered_payload_types: PayloadTypeRegistry | object = _REGISTRY_REQUIRED,
    lifecycle_validator: LifecycleValidator | None = None,
    portability_validator: PortabilityValidator | None = None,
    record_filename: str | None = None,
) -> RecordEnvelope:
    """Parse a canonical record and retain its exact bytes/digest."""

    source = bytes(raw)
    record = parse_record(
        source,
        registered_payload_types=registered_payload_types,
        lifecycle_validator=lifecycle_validator,
        portability_validator=portability_validator,
        record_filename=record_filename,
        require_canonical=True,
    )
    return RecordEnvelope(
        record=record,
        raw_bytes=source,
        sha256=hashlib.sha256(source).hexdigest(),
        filename=record_filename,
    )


def payload_sha256(payload: bytes | bytearray | memoryview) -> str:
    """Plain SHA-256 over exact payload bytes."""

    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload_sha256 requires bytes")
    return hashlib.sha256(bytes(payload)).hexdigest()


def record_sha256(
    record_or_bytes: RecordEnvelope
    | FolderSidecarRecord
    | Mapping[str, Any]
    | bytes
    | bytearray
    | memoryview,
    *,
    registered_payload_types: PayloadTypeRegistry | object = _REGISTRY_REQUIRED,
    lifecycle_validator: LifecycleValidator | None = None,
    portability_validator: PortabilityValidator | None = None,
) -> str:
    """SHA-256 over exact sidecar bytes or a record's canonical bytes."""

    if isinstance(record_or_bytes, RecordEnvelope):
        _validated_envelope(record_or_bytes)
        return record_or_bytes.sha256
    if isinstance(record_or_bytes, (bytes, bytearray, memoryview)):
        return hashlib.sha256(bytes(record_or_bytes)).hexdigest()
    raw = canonical_record_bytes(
        record_or_bytes,
        registered_payload_types=registered_payload_types,
        lifecycle_validator=lifecycle_validator,
        portability_validator=portability_validator,
    )
    return hashlib.sha256(raw).hexdigest()


def _validated_envelope(envelope: RecordEnvelope) -> RecordEnvelope:
    canonical = canonical_record_bytes(envelope.record)
    expected_hash = hashlib.sha256(envelope.raw_bytes).hexdigest()
    if envelope.raw_bytes != canonical:
        raise C0ValidationError(
            C0_NONCANONICAL_SERIALIZATION,
            f"envelope for {envelope.record.uid} does not carry canonical bytes",
        )
    if envelope.sha256 != expected_hash:
        raise C0ValidationError(
            C0_HASH_MISMATCH,
            f"envelope digest for {envelope.record.uid} is inconsistent",
        )
    if (
        envelope.filename is not None
        and envelope.filename != envelope.record.record_filename
    ):
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"record filename must be exactly {envelope.record.record_filename}",
        )
    return envelope


def parse_record_inventory(
    sources: Mapping[str, bytes] | Iterable[tuple[str, bytes]],
    *,
    registered_payload_types: PayloadTypeRegistry | object = _REGISTRY_REQUIRED,
    lifecycle_validator: LifecycleValidator | None = None,
    portability_validator: PortabilityValidator | None = None,
) -> tuple[RecordEnvelope, ...]:
    """Parse an injected filename/bytes inventory in deterministic order."""

    items = list(sources.items()) if isinstance(sources, Mapping) else list(sources)
    normalized: list[tuple[str, bytes]] = []
    seen_filenames: set[str] = set()
    for candidate in items:
        if not isinstance(candidate, tuple) or len(candidate) != 2:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                "record inventory entries must be (filename, bytes) pairs",
            )
        filename = _strict_utf8(candidate[0], "record filename")
        if filename in seen_filenames:
            raise C0ValidationError(
                C0_DUPLICATE_UID,
                f"duplicate record inventory filename {filename!r}",
            )
        seen_filenames.add(filename)
        raw = candidate[1]
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"{filename} record content must be bytes",
            )
        normalized.append((filename, bytes(raw)))
    normalized.sort(key=lambda item: item[0].encode("utf-8"))
    return tuple(
        parse_record_envelope(
            raw,
            registered_payload_types=registered_payload_types,
            lifecycle_validator=lifecycle_validator,
            portability_validator=portability_validator,
            record_filename=filename,
        )
        for filename, raw in normalized
    )


def _stable_regular_bytes(path: Path, *, hardlink_code: str = C0_HARDLINK) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise C0ValidationError(
            C0_SIDECAR_ORPHAN,
            f"cannot stat {path}: {exc}",
        ) from exc
    if not stat.S_ISREG(before.st_mode):
        raise C0ValidationError(
            C0_SPECIAL_FILE,
            f"{path} is not a regular file",
        )
    if before.st_nlink != 1:
        raise C0ValidationError(
            hardlink_code,
            f"{path} has {before.st_nlink} hard links",
        )
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after_open = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after_path = path.lstat()
    except OSError as exc:
        raise C0ValidationError(
            C0_SIDECAR_ORPHAN,
            f"cannot read stable regular file {path}: {exc}",
        ) from exc
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_opened = (
        opened.st_dev,
        opened.st_ino,
        opened.st_mode,
        opened.st_size,
        opened.st_mtime_ns,
    )
    identity_after_open = (
        after_open.st_dev,
        after_open.st_ino,
        after_open.st_mode,
        after_open.st_size,
        after_open.st_mtime_ns,
    )
    identity_after_path = (
        after_path.st_dev,
        after_path.st_ino,
        after_path.st_mode,
        after_path.st_size,
        after_path.st_mtime_ns,
    )
    if not (
        identity_before
        == identity_opened
        == identity_after_open
        == identity_after_path
    ):
        raise C0ValidationError(
            C0_HASH_MISMATCH,
            f"{path} changed during read-only verification",
        )
    return b"".join(chunks)


def scan_record_inventory(
    records_directory: str | os.PathLike[str],
    *,
    registered_payload_types: PayloadTypeRegistry | object = _REGISTRY_REQUIRED,
    lifecycle_validator: LifecycleValidator | None = None,
    portability_validator: PortabilityValidator | None = None,
) -> tuple[RecordEnvelope, ...]:
    """Read-only scan of the flat C0 ``records/`` directory."""

    directory = Path(records_directory)
    try:
        root_stat = directory.lstat()
    except OSError as exc:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"cannot stat record directory {directory}: {exc}",
        ) from exc
    if not stat.S_ISDIR(root_stat.st_mode):
        raise C0ValidationError(
            C0_SPECIAL_FILE,
            f"record inventory root {directory} is not a directory",
        )
    try:
        entries = list(os.scandir(directory))
    except OSError as exc:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"cannot scan record directory {directory}: {exc}",
        ) from exc
    entries.sort(key=lambda entry: entry.name.encode("utf-8", errors="strict"))
    sources: list[tuple[str, bytes]] = []
    for entry in entries:
        name = _strict_utf8(entry.name, "record filename")
        try:
            entry_stat = entry.stat(follow_symlinks=False)
        except OSError as exc:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"cannot stat record entry {name}: {exc}",
            ) from exc
        if not stat.S_ISREG(entry_stat.st_mode):
            raise C0ValidationError(
                C0_SPECIAL_FILE,
                f"record namespace entry {name!r} is not a regular file",
            )
        sources.append((name, _stable_regular_bytes(Path(entry.path))))
    return parse_record_inventory(
        sources,
        registered_payload_types=registered_payload_types,
        lifecycle_validator=lifecycle_validator,
        portability_validator=portability_validator,
    )


def _stable_file_digest(path: Path, expected_stat: os.stat_result) -> str:
    raw = _stable_regular_bytes(path)
    digest = hashlib.sha256(raw).hexdigest()
    try:
        after = path.lstat()
    except OSError as exc:
        raise C0ValidationError(
            C0_HASH_MISMATCH,
            f"payload {path} vanished after hashing: {exc}",
        ) from exc
    expected_identity = (
        expected_stat.st_dev,
        expected_stat.st_ino,
        expected_stat.st_mode,
        expected_stat.st_size,
        expected_stat.st_mtime_ns,
    )
    actual_identity = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    )
    if expected_identity != actual_identity:
        raise C0ValidationError(
            C0_HASH_MISMATCH,
            f"payload {path} changed during hashing",
        )
    return digest


def scan_payload_inventory(
    payload_root: str | os.PathLike[str],
    *,
    portability_key: PortabilityKey,
) -> tuple[PayloadEntry, ...]:
    """Read-only physical payload scan using an injected portability oracle.

    This scanner supplies regular-file/directory identity and exact hashes.  It
    deliberately does not implement Unicode normalization, collision keys, or
    reserved-name policy; the injected C0 portability owner does that.
    """

    root = Path(payload_root)
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise C0ValidationError(
            C0_DIRECTORY_MISSING,
            f"cannot stat payload root {root}: {exc}",
        ) from exc
    if not stat.S_ISDIR(root_stat.st_mode):
        raise C0ValidationError(
            C0_DIRECTORY_MISSING,
            f"payload root {root} is not a physical directory",
        )

    def key_for(path: str, is_root: bool) -> str:
        try:
            key = portability_key(path, is_root)
        except C0Refusal:
            raise
        except Exception as exc:
            raise C0ValidationError(
                C0_PATH_INVALID,
                f"portability key derivation refused {path!r}: {exc}",
            ) from exc
        key = _strict_utf8(key, f"portability key for {path!r}")
        if is_root and key != "":
            raise C0ValidationError(
                C0_PATH_INVALID,
                "payload-root portability key must be empty",
            )
        if not is_root and key == "":
            raise C0ValidationError(
                C0_PATH_INVALID,
                f"non-root portability key is empty for {path!r}",
            )
        return key

    rows: list[PayloadEntry] = [PayloadEntry.directory("", key_for("", True))]

    def walk(directory: Path, relative: str) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise C0ValidationError(
                C0_DIRECTORY_MISSING,
                f"cannot scan payload directory {directory}: {exc}",
            ) from exc
        try:
            entries.sort(
                key=lambda entry: entry.name.encode("utf-8", errors="strict")
            )
        except UnicodeEncodeError as exc:
            raise C0ValidationError(
                C0_PATH_INVALID,
                f"payload directory {directory} contains a non-UTF-8 name",
            ) from exc
        for entry in entries:
            name = _strict_utf8(entry.name, "payload path component")
            child_relative = f"{relative}/{name}" if relative else name
            child_path = Path(entry.path)
            try:
                child_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise C0ValidationError(
                    C0_SPECIAL_FILE,
                    f"cannot lstat payload {child_relative!r}: {exc}",
                ) from exc
            if child_stat.st_dev != root_stat.st_dev:
                raise C0ValidationError(
                    C0_SPECIAL_FILE,
                    f"payload {child_relative!r} crosses a mount boundary",
                )
            key = key_for(child_relative, False)
            path_bytes = child_relative.encode("utf-8", errors="strict")
            if stat.S_ISDIR(child_stat.st_mode):
                rows.append(
                    PayloadEntry.directory(
                        child_relative,
                        key,
                        payload_path_bytes=path_bytes,
                    )
                )
                walk(child_path, child_relative)
            elif stat.S_ISREG(child_stat.st_mode):
                if child_stat.st_nlink != 1:
                    raise C0ValidationError(
                        C0_HARDLINK,
                        f"payload {child_relative!r} has {child_stat.st_nlink} links",
                    )
                rows.append(
                    PayloadEntry.file_hash(
                        child_relative,
                        _stable_file_digest(child_path, child_stat),
                        key,
                        payload_path_bytes=path_bytes,
                    )
                )
            else:
                raise C0ValidationError(
                    C0_SPECIAL_FILE,
                    f"payload {child_relative!r} is not a regular file or directory",
                )

    walk(root, "")
    return tuple(
        sorted(rows, key=lambda row: row.payload_path_bytes)
    )


def _coerce_envelope(
    value: object,
    *,
    registered_payload_types: PayloadTypeRegistry | object,
    lifecycle_validator: LifecycleValidator | None,
    portability_validator: PortabilityValidator | None,
) -> RecordEnvelope:
    if isinstance(value, RecordEnvelope):
        return _validated_envelope(value)
    if isinstance(value, FolderSidecarRecord):
        return envelope_record(value)
    if isinstance(value, Mapping):
        record = validate_record(
            value,
            registered_payload_types=registered_payload_types,
            lifecycle_validator=lifecycle_validator,
            portability_validator=portability_validator,
        )
        return envelope_record(record)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return parse_record_envelope(
            value,
            registered_payload_types=registered_payload_types,
            lifecycle_validator=lifecycle_validator,
            portability_validator=portability_validator,
        )
    if isinstance(value, tuple) and len(value) == 2:
        filename, raw = value
        if not isinstance(filename, str) or not isinstance(
            raw,
            (bytes, bytearray, memoryview),
        ):
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                "record tuple must be (filename, bytes)",
            )
        return parse_record_envelope(
            raw,
            registered_payload_types=registered_payload_types,
            lifecycle_validator=lifecycle_validator,
            portability_validator=portability_validator,
            record_filename=filename,
        )
    raise C0ValidationError(
        C0_SCHEMA_INVALID,
        f"unsupported record inventory value {type(value).__name__}",
    )


def _coerce_payload(value: object) -> PayloadEntry:
    if isinstance(value, PayloadEntry):
        entry = value
    elif isinstance(value, Mapping):
        path = _strict_utf8(value.get("payload_path"), "payload payload_path")
        kind = value.get("record_kind", value.get("kind"))
        key = _strict_utf8(
            value.get("payload_portability_key"),
            "payload payload_portability_key",
        )
        path_bytes_value = value.get("payload_path_bytes")
        if path_bytes_value is None and "payload_path_bytes_b64" in value:
            encoded = _strict_utf8(
                value["payload_path_bytes_b64"],
                "payload payload_path_bytes_b64",
            )
            if BASE64_RE.fullmatch(encoded) is None:
                raise C0ValidationError(
                    C0_PATH_INVALID,
                    "injected payload path base64 is noncanonical",
                )
            try:
                path_bytes_value = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise C0ValidationError(
                    C0_PATH_INVALID,
                    "injected payload path base64 is invalid",
                ) from exc
        if path_bytes_value is None:
            path_bytes_value = path.encode("utf-8")
        if not isinstance(path_bytes_value, (bytes, bytearray, memoryview)):
            raise C0ValidationError(
                C0_PATH_INVALID,
                "injected payload path bytes must be bytes",
            )
        if "payload_bytes" in value:
            content = value["payload_bytes"]
            if not isinstance(content, (bytes, bytearray, memoryview)):
                raise C0ValidationError(
                    C0_SCHEMA_INVALID,
                    "injected payload_bytes must be bytes",
                )
            digest = payload_sha256(content)
        else:
            digest = value.get("payload_sha256")
        entry = PayloadEntry(
            path,
            kind,  # type: ignore[arg-type]
            bytes(path_bytes_value),
            key,
            digest,  # type: ignore[arg-type]
        )
    else:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"unsupported payload inventory value {type(value).__name__}",
        )

    path = _strict_utf8(entry.payload_path, "payload inventory path")
    if entry.record_kind not in RECORD_KINDS:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            "payload inventory kind must be file or directory",
        )
    if not isinstance(entry.payload_path_bytes, bytes):
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"payload inventory path bytes for {path!r} must be bytes",
        )
    if entry.payload_path_bytes != path.encode("utf-8"):
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"payload inventory path bytes disagree for {path!r}",
        )
    _strict_utf8(
        entry.payload_portability_key,
        f"payload portability key for {path!r}",
    )
    if path == "" and entry.record_kind != "directory":
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload inventory root must be a directory",
        )
    if path == "" and entry.payload_portability_key != "":
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload inventory root portability key must be empty",
        )
    if path != "" and entry.payload_portability_key == "":
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"payload inventory key is empty for non-root {path!r}",
        )
    if entry.record_kind == "file":
        _require_hash(entry.payload_sha256, f"payload hash for {path!r}")
    elif entry.payload_sha256 is not None:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"directory payload {path!r} may not carry a hash",
        )
    return entry


_FINDING_PRIORITY: Final[dict[str, int]] = {
    C0_DUPLICATE_UID: 10,
    C0_DUPLICATE_PATH: 20,
    C0_PORTABILITY_COLLISION: 30,
    C0_DUPLICATE_PROJECTION: 40,
    C0_PAYLOAD_ORPHAN: 50,
    C0_SIDECAR_ORPHAN: 60,
    C0_DIRECTORY_MISSING: 61,
    C0_PATH_INVALID: 70,
    C0_HASH_MISMATCH: 80,
    C0_PARENT_MISMATCH: 90,
}


def _finding_sort_key(finding: C0Finding) -> tuple[int, bytes, bytes, bytes]:
    return (
        _FINDING_PRIORITY.get(finding.code, 999),
        finding.path.encode("utf-8", errors="backslashreplace"),
        finding.code.encode("ascii", errors="replace"),
        finding.message.encode("utf-8", errors="backslashreplace"),
    )


def bijection_findings(
    records: Iterable[object],
    payloads: Iterable[object],
    *,
    vault_uid: str,
    duplicate_projection_uids: Iterable[str] = (),
    registered_payload_types: PayloadTypeRegistry | object = _REGISTRY_REQUIRED,
    lifecycle_validator: LifecycleValidator | None = None,
    portability_validator: PortabilityValidator | None = None,
) -> tuple[C0Finding, ...]:
    """Return every deterministic payload/sidecar bijection finding."""

    vault_code = require_vault_code(vault_uid)
    envelopes = tuple(
        _coerce_envelope(
            record,
            registered_payload_types=registered_payload_types,
            lifecycle_validator=lifecycle_validator,
            portability_validator=portability_validator,
        )
        for record in records
    )
    payload_rows = tuple(_coerce_payload(payload) for payload in payloads)
    findings: list[C0Finding] = []

    records_by_uid: dict[str, list[RecordEnvelope]] = {}
    records_by_path: dict[str, list[RecordEnvelope]] = {}
    records_by_key: dict[str, list[RecordEnvelope]] = {}
    for envelope in envelopes:
        record = envelope.record
        records_by_uid.setdefault(record.uid, []).append(envelope)
        records_by_path.setdefault(record.payload_path, []).append(envelope)
        records_by_key.setdefault(record.payload_portability_key, []).append(envelope)

    for uid, matches in sorted(records_by_uid.items()):
        if len(matches) > 1:
            findings.append(
                C0Finding(
                    C0_DUPLICATE_UID,
                    uid,
                    f"{len(matches)} sidecars declare UID {uid}",
                )
            )
    for path, matches in sorted(
        records_by_path.items(),
        key=lambda item: item[0].encode("utf-8"),
    ):
        if len(matches) > 1:
            findings.append(
                C0Finding(
                    C0_DUPLICATE_PATH,
                    path,
                    f"{len(matches)} sidecars declare the same payload path",
                )
            )
    for key, matches in sorted(
        records_by_key.items(),
        key=lambda item: item[0].encode("utf-8"),
    ):
        distinct_paths = {match.record.payload_path for match in matches}
        if len(distinct_paths) > 1:
            findings.append(
                C0Finding(
                    C0_PORTABILITY_COLLISION,
                    key,
                    "sidecar portability key aliases paths "
                    + ", ".join(sorted(distinct_paths)),
                )
            )

    payloads_by_path: dict[str, list[PayloadEntry]] = {}
    payloads_by_key: dict[str, list[PayloadEntry]] = {}
    for payload in payload_rows:
        payloads_by_path.setdefault(payload.payload_path, []).append(payload)
        payloads_by_key.setdefault(payload.payload_portability_key, []).append(payload)
    for path, matches in sorted(
        payloads_by_path.items(),
        key=lambda item: item[0].encode("utf-8"),
    ):
        if len(matches) > 1:
            findings.append(
                C0Finding(
                    C0_DUPLICATE_PATH,
                    path,
                    f"{len(matches)} physical inventory rows declare the same path",
                )
            )
    for key, matches in sorted(
        payloads_by_key.items(),
        key=lambda item: item[0].encode("utf-8"),
    ):
        distinct_paths = {match.payload_path for match in matches}
        if len(distinct_paths) > 1:
            findings.append(
                C0Finding(
                    C0_PORTABILITY_COLLISION,
                    key,
                    "physical portability key aliases paths "
                    + ", ".join(sorted(distinct_paths)),
                )
            )

    projection_set: set[str] = set()
    for value in duplicate_projection_uids:
        projection_set.add(require_file_uid(value, "projection UID"))
    for uid in sorted(set(records_by_uid) & projection_set):
        findings.append(
            C0Finding(
                C0_DUPLICATE_PROJECTION,
                uid,
                f"canonical vault/files/{uid}.md duplicates a C0 source",
            )
        )

    for path, physical_matches in sorted(
        payloads_by_path.items(),
        key=lambda item: item[0].encode("utf-8"),
    ):
        record_matches = records_by_path.get(path, [])
        if not record_matches:
            findings.append(
                C0Finding(
                    C0_PAYLOAD_ORPHAN,
                    path,
                    "physical payload has no sidecar",
                )
            )
            continue
        if len(physical_matches) != 1 or len(record_matches) != 1:
            continue
        physical = physical_matches[0]
        record = record_matches[0].record
        if record.record_kind != physical.record_kind:
            code = (
                C0_DIRECTORY_MISSING
                if record.record_kind == "directory"
                else C0_SIDECAR_ORPHAN
            )
            findings.append(
                C0Finding(
                    code,
                    path,
                    f"sidecar kind {record.record_kind!r} disagrees with "
                    f"physical kind {physical.record_kind!r}",
                )
            )
        if record.payload_path_bytes != physical.payload_path_bytes:
            findings.append(
                C0Finding(
                    C0_PATH_INVALID,
                    path,
                    "sidecar and physical raw UTF-8 path bytes disagree",
                )
            )
        if record.payload_portability_key != physical.payload_portability_key:
            findings.append(
                C0Finding(
                    C0_PATH_INVALID,
                    path,
                    "sidecar and physical portability keys disagree",
                )
            )
        if (
            record.record_kind == "file"
            and physical.record_kind == "file"
            and record.payload_sha256 != physical.payload_sha256
        ):
            findings.append(
                C0Finding(
                    C0_HASH_MISMATCH,
                    path,
                    f"sidecar hash {record.payload_sha256} != physical hash "
                    f"{physical.payload_sha256}",
                )
            )

    for path, record_matches in sorted(
        records_by_path.items(),
        key=lambda item: item[0].encode("utf-8"),
    ):
        if path in payloads_by_path:
            continue
        for envelope in record_matches:
            code = (
                C0_DIRECTORY_MISSING
                if envelope.record.record_kind == "directory"
                else C0_SIDECAR_ORPHAN
            )
            findings.append(
                C0Finding(code, path, "sidecar resolves to no physical payload")
            )

    unique_records_by_path = {
        path: matches[0].record
        for path, matches in records_by_path.items()
        if len(matches) == 1
    }
    unique_records_by_uid = {
        uid: matches[0].record
        for uid, matches in records_by_uid.items()
        if len(matches) == 1
    }
    root_record = unique_records_by_path.get("")
    if root_record is not None and root_record.parent_uid != vault_code:
        findings.append(
            C0Finding(
                C0_PARENT_MISMATCH,
                "",
                f"root parent_uid {root_record.parent_uid!r} != vault UID {vault_code!r}",
            )
        )

    for path, record in sorted(
        unique_records_by_path.items(),
        key=lambda item: item[0].encode("utf-8"),
    ):
        if path == "":
            continue
        expected_parent_path = path.rpartition("/")[0]
        expected_parent = unique_records_by_path.get(expected_parent_path)
        if expected_parent is None:
            findings.append(
                C0Finding(
                    C0_PARENT_MISMATCH,
                    path,
                    f"physical parent path {expected_parent_path!r} has no unique sidecar",
                )
            )
            continue
        if expected_parent.record_kind != "directory":
            findings.append(
                C0Finding(
                    C0_PARENT_MISMATCH,
                    path,
                    f"physical parent {expected_parent_path!r} is not a directory",
                )
            )
        if record.parent_uid != expected_parent.uid:
            findings.append(
                C0Finding(
                    C0_PARENT_MISMATCH,
                    path,
                    f"parent_uid {record.parent_uid!r} != physical parent UID "
                    f"{expected_parent.uid!r}",
                )
            )
        resolved_parent = unique_records_by_uid.get(record.parent_uid)
        if resolved_parent is None:
            findings.append(
                C0Finding(
                    C0_PARENT_MISMATCH,
                    path,
                    f"parent_uid {record.parent_uid!r} does not resolve exactly once",
                )
            )
        elif resolved_parent.payload_path != expected_parent_path:
            findings.append(
                C0Finding(
                    C0_PARENT_MISMATCH,
                    path,
                    f"parent_uid {record.parent_uid!r} resolves at "
                    f"{resolved_parent.payload_path!r}, not {expected_parent_path!r}",
                )
            )

    deduplicated = {
        (finding.code, finding.path, finding.message): finding
        for finding in findings
    }
    return tuple(sorted(deduplicated.values(), key=_finding_sort_key))


def verify_bijection(
    records: Iterable[object],
    payloads: Iterable[object],
    *,
    vault_uid: str,
    duplicate_projection_uids: Iterable[str] = (),
    registered_payload_types: PayloadTypeRegistry | object = _REGISTRY_REQUIRED,
    lifecycle_validator: LifecycleValidator | None = None,
    portability_validator: PortabilityValidator | None = None,
) -> VerificationResult:
    """Prove one-to-one physical payload/sidecar identity or raise."""

    envelope_rows = tuple(
        _coerce_envelope(
            record,
            registered_payload_types=registered_payload_types,
            lifecycle_validator=lifecycle_validator,
            portability_validator=portability_validator,
        )
        for record in records
    )
    payload_rows = tuple(_coerce_payload(payload) for payload in payloads)
    findings = bijection_findings(
        envelope_rows,
        payload_rows,
        vault_uid=vault_uid,
        duplicate_projection_uids=duplicate_projection_uids,
        registered_payload_types=registered_payload_types,
        lifecycle_validator=lifecycle_validator,
        portability_validator=portability_validator,
    )
    if findings:
        raise C0VerificationError(findings)
    ordered_records = tuple(
        sorted(
            envelope_rows,
            key=lambda envelope: envelope.record.uid.encode("utf-8"),
        )
    )
    ordered_payloads = tuple(
        sorted(payload_rows, key=lambda payload: payload.payload_path_bytes)
    )
    record_hashes = MappingProxyType(
        {
            envelope.record.uid: envelope.sha256
            for envelope in ordered_records
        }
    )
    payload_hashes = MappingProxyType(
        {
            envelope.record.uid: envelope.record.payload_sha256
            for envelope in ordered_records
        }
    )
    return VerificationResult(
        records=ordered_records,
        payloads=ordered_payloads,
        record_sha256_by_uid=record_hashes,
        payload_sha256_by_uid=payload_hashes,
    )


def derive_projection_row(
    record: RecordEnvelope | FolderSidecarRecord,
    *,
    vault_uid: str,
    payload_root: str,
) -> dict[str, Any]:
    """Derive one closed graph row in the locked key order."""

    vault_code = require_vault_code(vault_uid)
    payload_root_text = _bounded_text(
        payload_root,
        "payload_root",
        minimum=1,
        maximum=1024,
        no_controls=True,
    )
    envelope = (
        _validated_envelope(record)
        if isinstance(record, RecordEnvelope)
        else envelope_record(record)
    )
    source = envelope.record
    title = (
        payload_root_text
        if source.is_root
        else source.payload_path.rsplit("/", 1)[-1]
    )
    return {
        "uid": source.uid,
        "type": source.payload_type,
        "title": title,
        "status": source.status,
        "state": source.state,
        "stage": source.stage,
        "created": source.created.at,
        "modified": source.modified.at,
        "created_by": source.created.by,
        "modified_by": source.modified.by,
        "path": source.payload_path,
        "record_kind": source.record_kind,
        "parent_uid": source.parent_uid,
        "owner_uid": source.owner_uid,
        "audience_group_uid": source.audience_group_uid,
        "extraction_scope": source.extraction_scope,
        "record_sha256": envelope.sha256,
        "payload_sha256": (
            source.payload_sha256 if source.record_kind == "file" else None
        ),
        "hash_function": "sha256",
        "governance": "folder-sidecar-v1",
        "source_sidecar": source.record_path,
        "vault_uid": vault_code,
        "segment": vault_code,
    }


def derive_projection_edges(
    record: RecordEnvelope | FolderSidecarRecord,
    *,
    vault_uid: str,
) -> tuple[dict[str, str], ...]:
    """Derive closed edge rows for one record."""

    vault_code = require_vault_code(vault_uid)
    source = record.record if isinstance(record, RecordEnvelope) else record
    if isinstance(record, RecordEnvelope):
        _validated_envelope(record)
    return tuple(
        {
            "source_uid": source.uid,
            "predicate": relation.predicate,
            "target_uid": relation.target_uid,
            "vault_uid": vault_code,
        }
        for relation in source.relations
    )


def _ordered_projection_mapping(
    value: Mapping[str, Any],
    keys: tuple[str, ...],
    label: str,
) -> dict[str, Any]:
    actual_keys = frozenset(value.keys())
    expected_keys = frozenset(keys)
    if actual_keys != expected_keys:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            f"{label} keys must be exactly {list(keys)}",
        )
    ordered = {key: value[key] for key in keys}
    _validate_json_domain(ordered, field=label)
    return ordered


def projection_row_bytes(row: Mapping[str, Any]) -> bytes:
    """Encode one graph row with exact locked key order plus LF."""

    return _ordered_json_bytes(
        _ordered_projection_mapping(row, PROJECTION_ROW_KEYS, "projection row"),
        trailing_lf=True,
    )


def projection_edge_bytes(edge: Mapping[str, Any]) -> bytes:
    """Encode one graph edge with exact locked key order plus LF."""

    ordered = _ordered_projection_mapping(
        edge,
        PROJECTION_EDGE_KEYS,
        "projection edge",
    )
    if not is_registered_relation(ordered["predicate"]):
        raise C0ValidationError(
            C0_RELATION_INVALID,
            f"projection predicate {ordered['predicate']!r} is unregistered",
        )
    return _ordered_json_bytes(ordered, trailing_lf=True)


def graph_jsonl(
    rows: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
) -> tuple[bytes, bytes]:
    """Return deterministic UID-sorted row and tuple-sorted edge JSONL."""

    row_list = [
        _ordered_projection_mapping(row, PROJECTION_ROW_KEYS, "projection row")
        for row in rows
    ]
    edge_list = [
        _ordered_projection_mapping(edge, PROJECTION_EDGE_KEYS, "projection edge")
        for edge in edges
    ]
    for edge in edge_list:
        if not is_registered_relation(edge["predicate"]):
            raise C0ValidationError(
                C0_RELATION_INVALID,
                f"projection predicate {edge['predicate']!r} is unregistered",
            )
    row_list.sort(key=lambda row: _strict_utf8(row["uid"], "row uid").encode("utf-8"))
    edge_list.sort(
        key=lambda edge: tuple(
            _strict_utf8(edge[key], f"edge {key}").encode("utf-8")
            for key in PROJECTION_EDGE_KEYS
        )
    )
    row_uids = [row["uid"] for row in row_list]
    if len(set(row_uids)) != len(row_uids):
        raise C0ValidationError(
            C0_DUPLICATE_UID,
            "graph rows contain duplicate UIDs",
        )
    edge_tuples = [
        tuple(edge[key] for key in PROJECTION_EDGE_KEYS)
        for edge in edge_list
    ]
    if len(set(edge_tuples)) != len(edge_tuples):
        raise C0ValidationError(
            C0_RELATION_INVALID,
            "graph edges contain duplicate tuples",
        )
    return (
        b"".join(projection_row_bytes(row) for row in row_list),
        b"".join(projection_edge_bytes(edge) for edge in edge_list),
    )


def graph_sha256(
    rows: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
) -> str:
    """Domain-separated C0 graph SHA-256."""

    row_jsonl, edge_jsonl = graph_jsonl(rows, edges)
    return hashlib.sha256(
        GRAPH_HASH_DOMAIN + row_jsonl + b"\n" + edge_jsonl
    ).hexdigest()


def derive_graph_projection(
    records: Iterable[RecordEnvelope | FolderSidecarRecord],
    *,
    vault_uid: str,
    payload_root: str,
) -> GraphProjection:
    """Derive sorted rows, edges, JSONL, and graph hash without mutation."""

    envelopes = tuple(
        _validated_envelope(record)
        if isinstance(record, RecordEnvelope)
        else envelope_record(record)
        for record in records
    )
    rows = [
        derive_projection_row(
            envelope,
            vault_uid=vault_uid,
            payload_root=payload_root,
        )
        for envelope in envelopes
    ]
    edges = [
        edge
        for envelope in envelopes
        for edge in derive_projection_edges(envelope, vault_uid=vault_uid)
    ]
    row_jsonl, edge_jsonl = graph_jsonl(rows, edges)
    digest = hashlib.sha256(
        GRAPH_HASH_DOMAIN + row_jsonl + b"\n" + edge_jsonl
    ).hexdigest()
    sorted_rows = sorted(rows, key=lambda row: row["uid"].encode("utf-8"))
    sorted_edges = sorted(
        edges,
        key=lambda edge: tuple(
            edge[key].encode("utf-8") for key in PROJECTION_EDGE_KEYS
        ),
    )
    return GraphProjection(
        rows=tuple(MappingProxyType(dict(row)) for row in sorted_rows),
        edges=tuple(MappingProxyType(dict(edge)) for edge in sorted_edges),
        row_jsonl=row_jsonl,
        edge_jsonl=edge_jsonl,
        sha256=digest,
    )


# Clear compatibility names for consumers that prefer codec/verifier verbs.
serialize_record = canonical_record_bytes
parse_sidecar = parse_record
verify_inventory = verify_bijection
derive_graph_hash = graph_sha256


__all__ = [
    "BASE64_RE",
    "C0_DIRECTORY_MISSING",
    "C0_DUPLICATE_PATH",
    "C0_DUPLICATE_PROJECTION",
    "C0_DUPLICATE_UID",
    "C0_HASH_MISMATCH",
    "C0_HARDLINK",
    "C0_NONCANONICAL_SERIALIZATION",
    "C0_PARENT_MISMATCH",
    "C0_PATH_INVALID",
    "C0_PAYLOAD_ORPHAN",
    "C0_PORTABILITY_COLLISION",
    "C0_RELATION_INVALID",
    "C0_SCHEMA_INVALID",
    "C0_SIDECAR_ORPHAN",
    "C0_SPECIAL_FILE",
    "C0Finding",
    "C0Refusal",
    "C0ValidationError",
    "C0VerificationError",
    "EXTRACTION_SCOPES",
    "FILE_UID_RE",
    "FolderSidecarRecord",
    "GRAPH_HASH_DOMAIN",
    "GraphProjection",
    "HASH_RE",
    "INT64_MAX",
    "INT64_MIN",
    "LifecycleRule",
    "PAYLOAD_PROFILES",
    "PROJECTION_EDGE_KEYS",
    "PROJECTION_ROW_KEYS",
    "PayloadEntry",
    "Provenance",
    "RECORD_KINDS",
    "RECORD_NAMESPACE",
    "RELATION_PREDICATES",
    "RELATION_PREDICATE_SET",
    "RecordEnvelope",
    "Relation",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "STATES",
    "VAULT_CODE_RE",
    "VerificationResult",
    "bijection_findings",
    "canonical_json_bytes",
    "canonical_record_bytes",
    "decode_json_strict",
    "derive_graph_hash",
    "derive_graph_projection",
    "derive_projection_edges",
    "derive_projection_row",
    "envelope_record",
    "graph_jsonl",
    "graph_sha256",
    "is_file_uid",
    "is_vault_code",
    "parse_record",
    "parse_record_envelope",
    "parse_record_inventory",
    "parse_sidecar",
    "payload_sha256",
    "projection_edge_bytes",
    "projection_row_bytes",
    "record_sha256",
    "require_file_uid",
    "require_vault_code",
    "scan_payload_inventory",
    "scan_record_inventory",
    "serialize_record",
    "validate_record",
    "verify_bijection",
    "verify_inventory",
]
