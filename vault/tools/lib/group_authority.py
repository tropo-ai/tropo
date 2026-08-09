"""Strict B4a authenticated group-authority verification (pure library).

This module implements the authority half of B4a per the locked dev-spec
(uid ``0bfa771d``): canonical authority-artifact serialization, the domain
separated Ed25519 signature over the fixed ``group_authority`` tuple, out-of-band
fingerprint trust, freshness/high-water anti-rollback, the portable principal
directory, and the closed refusal vocabulary.

It is pure: it accepts already-loaded ``bytes`` and mappings and returns
``bytes``, mappings, and frozen results.  It never parses argv, reads or writes
the filesystem, opens a network connection, or hardcodes an absolute path.  The
CLI (``tropo-group-authority.py``) and mount/update surfaces wire this library
to disk, journals, and the machine-local trust file; none of that lives here.

Trust is never manufactured: verification consults only an out-of-band accepted
key and the caller-supplied expected fingerprint.  There is no trust-on-first
use, ``--yes``, wildcard, self-accept, or local-principal fallback.  Every
refusal is a typed :class:`GroupAuthorityError` carrying a closed
``GroupErrorCode``; a refusal is never converted into empty membership, an empty
result, or a reason-free ``False``.

The private signing key is externally supplied and never persisted by a Studio
or an update.  :func:`sign_authority_tuple` exists for the ``build`` gesture and
for oracle tests; production verification consumes only public keys, expected
fingerprints, and signatures.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import importlib.util
import json
import re
import sys
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


# ---------------------------------------------------------------------------
# Closed refusal vocabulary — reused from the sibling ``group_contract`` so the
# whole B4a slice shares one enum (that module already declares the authority
# codes for exactly this reuse).  The sibling is loaded by file path so this
# module works regardless of how a caller placed ``vault/tools/lib`` on
# ``sys.path`` (the paired test loads modules by path via importlib).
# ---------------------------------------------------------------------------
_LIB_DIR = Path(__file__).resolve().parent


def _load_sibling(module_name: str, file_name: str):
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, _LIB_DIR / file_name)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot locate sibling module {file_name!r}")
    module = importlib.util.module_from_spec(spec)
    # Register before executing so decorators that inspect ``sys.modules`` by the
    # module's own ``__module__`` name (e.g. ``@dataclass``) resolve correctly.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


try:  # Production: share the one ``lib.group_contract`` vocabulary module.
    import lib.group_contract as _group_contract  # type: ignore
except Exception:  # Isolated load (tests import this module by file path).
    _group_contract = _load_sibling("_group_authority_group_contract", "group_contract.py")

GroupErrorCode = _group_contract.GroupErrorCode
GroupContractError = _group_contract.GroupContractError


class GroupAuthorityError(GroupContractError):
    """A deterministic, typed authority refusal.

    Subclasses :class:`GroupContractError` so a caller may catch the whole B4a
    house error type, while carrying authority-specific context.  The ``code``
    is drawn from the shared, closed :class:`GroupErrorCode` vocabulary.
    """

    def __init__(
        self,
        code: "GroupErrorCode",
        message: str,
        *,
        authority_uid: str | None = None,
        key_uid: str | None = None,
        generation: int | None = None,
        field: str | None = None,
        reference_uid: str | None = None,
    ) -> None:
        super().__init__(
            code,
            message,
            field=field,
            reference_uid=reference_uid,
        )
        self.authority_uid = authority_uid
        self.key_uid = key_uid
        self.generation = generation


def _raise(
    code: "GroupErrorCode",
    message: str,
    *,
    authority_uid: str | None = None,
    key_uid: str | None = None,
    generation: int | None = None,
    field: str | None = None,
    reference_uid: str | None = None,
) -> "None":
    raise GroupAuthorityError(
        code,
        message,
        authority_uid=authority_uid,
        key_uid=key_uid,
        generation=generation,
        field=field,
        reference_uid=reference_uid,
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CANONICALIZATION_VERSION = 1
DOMAIN_SEPARATOR = b"tropo.group-authority.v1\n"
ARTIFACT_MANIFEST_SCHEMA_ID = "tropo.group-authority-artifacts/v1"

CORPUS_ARTIFACT = "groups.jsonl"
PRINCIPAL_ARTIFACT = "principals.jsonl"
AUDIENCE_POLICY_ARTIFACT = "audience-policy.json"
ARTIFACT_MANIFEST_ARTIFACT = "artifact-manifest.json"
SIGNED_ENVELOPE_ARTIFACT = "signed-envelope.json"

# The tuple key order is fixed and explicit (dev-spec 0bfa771d).  It is NEVER
# sorted; ``signature`` follows the tuple to form the signed envelope object.
TUPLE_KEY_ORDER: tuple[str, ...] = (
    "authority_uid",
    "corpus_revision",
    "corpus_sha256",
    "principal_directory_revision",
    "principal_directory_sha256",
    "audience_policy_sha256",
    "authority_generation",
    "previous_envelope_sha256",
    "canonicalization_version",
    "artifact_identity",
    "signing_key_uid",
)
ENVELOPE_KEY_ORDER: tuple[str, ...] = TUPLE_KEY_ORDER + ("signature",)

# Portable principal directory claim order.  ``source_hash`` is derived over the
# first five fields only; the sixth (``source_hash``) is appended to form a row.
PRINCIPAL_CLAIM_KEYS: tuple[str, ...] = (
    "principal_uid",
    "principal_class",
    "status",
    "source_authority_uid",
    "source_revision",
)
PRINCIPAL_ROW_KEYS: tuple[str, ...] = PRINCIPAL_CLAIM_KEYS + ("source_hash",)

# Accepted-key row: exactly the design-brief fields (design-brief 252534fe).
ACCEPTED_KEY_KEYS: tuple[str, ...] = (
    "authority_uid",
    "key_uid",
    "algorithm",
    "public_key",
    "sha256_fingerprint",
    "accepted_by",
    "accepted_at",
    "acceptance",
)
HIGH_WATER_KEYS: tuple[str, ...] = ("authority_generation", "envelope_sha256")

SUPPORTED_ALGORITHM = "ed25519"
ACCEPTANCE_MODE = "human-fingerprint"

# Trust must never fall back to a wildcard, self, or synthetic local principal.
_FORBIDDEN_KEY_UIDS = frozenset(
    {"", "*", "self", "any", "all", "wildcard", "local", "local-principal", "default"}
)
_FORBIDDEN_ACCEPTANCE = frozenset(
    {
        "trust-on-first-use",
        "tofu",
        "auto",
        "--yes",
        "yes",
        "self",
        "self-accept",
        "wildcard",
        "local",
        "local-principal",
        "assumed",
    }
)

UID_RE = re.compile(r"^[0-9a-f]{8}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PRINCIPAL_CLASS_RE = re.compile(r"^(?:human|agent-[a-z0-9]+(?:-[a-z0-9]+)*)$")
_B64_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")

_PUBLIC_KEY_RAW_LEN = 32
_SIGNATURE_RAW_LEN = 64
_MAX_JSON_INTEGER = 9007199254740991  # 2**53 - 1 (JSON-safe), matches the schema
_VALID_PRINCIPAL_STATUS = frozenset({"active", "inactive", "superseded"})


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------
class CanonicalJSONError(ValueError):
    """A canonical-JSON violation (duplicate key, lone surrogate, float, ...)."""


def _contains_lone_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _reject_lone_surrogates(obj: Any) -> None:
    if isinstance(obj, str):
        if _contains_lone_surrogate(obj):
            raise CanonicalJSONError("string contains a lone Unicode surrogate")
    elif isinstance(obj, Mapping):
        for key, value in obj.items():
            if isinstance(key, str) and _contains_lone_surrogate(key):
                raise CanonicalJSONError("object key contains a lone Unicode surrogate")
            _reject_lone_surrogates(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _reject_lone_surrogates(value)


def _reject_floats(obj: Any) -> None:
    # ``bool`` is an ``int`` subclass and is permitted (JSON true/false).
    if isinstance(obj, float):
        raise CanonicalJSONError("floats are forbidden in authority JSON")
    if isinstance(obj, Mapping):
        for value in obj.values():
            _reject_floats(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _reject_floats(value)


def canonical_json_bytes(obj: Any, *, sort_keys: bool = False) -> bytes:
    """Serialize ``obj`` as canonical compact UTF-8 JSON with no trailing LF.

    RFC 8785-style primitive/string encoding with compact ``(",", ":")``
    separators and no ASCII escaping.  Object key order follows insertion order
    (``sort_keys=False``, the authority default, so the fixed tuple/artifact
    orders are preserved) unless ``sort_keys=True`` is requested for a context
    the dev-spec states is sorted.  Floats and lone surrogates are rejected.
    """

    _reject_floats(obj)
    _reject_lone_surrogates(obj)
    try:
        text = json.dumps(
            obj,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=sort_keys,
        )
    except (TypeError, ValueError) as error:
        raise CanonicalJSONError(
            f"object is not canonical JSON: {type(error).__name__}: {error}"
        ) from error
    return text.encode("utf-8")


def canonical_json_line(obj: Any, *, sort_keys: bool = False) -> bytes:
    """:func:`canonical_json_bytes` plus exactly one trailing LF."""

    return canonical_json_bytes(obj, sort_keys=sort_keys) + b"\n"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalJSONError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_float_literal(_: str) -> Any:
    raise CanonicalJSONError("floats are forbidden in authority JSON")


def parse_canonical_json(data: bytes | bytearray | str) -> Any:
    """Parse authority JSON, rejecting non-canonical inputs.

    Rejects non-UTF-8 bytes, duplicate object keys, floats, and lone Unicode
    surrogates (including ``\\uXXXX``-escaped surrogates that survive decoding).
    Unicode is otherwise preserved without normalization.
    """

    if isinstance(data, (bytes, bytearray)):
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError as error:
            raise CanonicalJSONError("input is not valid UTF-8") from error
    elif isinstance(data, str):
        text = data
    else:
        raise CanonicalJSONError(
            f"expected bytes or str, got {type(data).__name__}"
        )
    try:
        obj = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float_literal,
        )
    except CanonicalJSONError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as error:
        raise CanonicalJSONError(f"invalid JSON: {error}") from error
    _reject_lone_surrogates(obj)
    return obj


# ---------------------------------------------------------------------------
# Digests / revisions
# ---------------------------------------------------------------------------
def sha256_hex(data: bytes | bytearray) -> str:
    """Lowercase SHA-256 hex over the exact bytes."""

    return hashlib.sha256(bytes(data)).hexdigest()


def content_revision(digest_hex: str) -> str:
    """Return ``sha256:<digest>`` for a 64-hex digest."""

    if not isinstance(digest_hex, str) or not HASH_RE.fullmatch(digest_hex):
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "content revision requires a 64-character lowercase hex digest",
        )
    return f"sha256:{digest_hex}"


def corpus_sha256(groups_jsonl: bytes) -> str:
    """SHA-256 over the exact ``groups.jsonl`` bytes."""

    return sha256_hex(groups_jsonl)


def principal_directory_sha256(principals_jsonl: bytes) -> str:
    """SHA-256 over the exact ``principals.jsonl`` bytes."""

    return sha256_hex(principals_jsonl)


def audience_policy_sha256(audience_policy_json: bytes) -> str:
    """SHA-256 over the exact ``audience-policy.json`` bytes."""

    return sha256_hex(audience_policy_json)


def artifact_identity(artifact_manifest_json: bytes) -> str:
    """SHA-256 over the exact ``artifact-manifest.json`` bytes."""

    return sha256_hex(artifact_manifest_json)


def previous_envelope_sha256(prior_signed_envelope: bytes | None) -> str | None:
    """SHA-256 over prior signed-envelope bytes, or ``None`` for the first gen."""

    if prior_signed_envelope is None:
        return None
    return sha256_hex(prior_signed_envelope)


# ---------------------------------------------------------------------------
# Ed25519 keys, fingerprints, signatures
# ---------------------------------------------------------------------------
def _b64decode_strict(value: str, *, subject: str, code: "GroupErrorCode") -> bytes:
    if (
        not isinstance(value, str)
        or not _B64_RE.fullmatch(value)
        or len(value) % 4 != 0
        or len(value) == 0
    ):
        _raise(code, f"{subject} is not canonical padded base64")
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        _raise(code, f"{subject} is not canonical padded base64")
    if base64.b64encode(raw).decode("ascii") != value:
        _raise(code, f"{subject} is not canonically encoded base64")
    return raw


def public_key_raw_bytes(public_key_b64: str, *, code: "GroupErrorCode | None" = None) -> bytes:
    """Return the raw 32 bytes of a base64 Ed25519 public key."""

    code = code or GroupErrorCode.AUTHORITY_UNTRUSTED
    raw = _b64decode_strict(public_key_b64, subject="public key", code=code)
    if len(raw) != _PUBLIC_KEY_RAW_LEN:
        _raise(code, f"public key must be {_PUBLIC_KEY_RAW_LEN} raw bytes")
    return raw


def load_public_key(public_key_b64: str, *, code: "GroupErrorCode | None" = None) -> Ed25519PublicKey:
    """Load an :class:`Ed25519PublicKey` from raw 32-byte base64."""

    raw = public_key_raw_bytes(public_key_b64, code=code)
    return Ed25519PublicKey.from_public_bytes(raw)


def fingerprint(public_key_b64: str, *, code: "GroupErrorCode | None" = None) -> str:
    """Lowercase SHA-256 hex over the raw public-key bytes."""

    return sha256_hex(public_key_raw_bytes(public_key_b64, code=code))


def public_key_base64(public_key: Ed25519PublicKey) -> str:
    """Serialize a public key to canonical raw-32-byte base64."""

    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _coerce_private_key(private_key: Ed25519PrivateKey | bytes | bytearray) -> Ed25519PrivateKey:
    if isinstance(private_key, Ed25519PrivateKey):
        return private_key
    if isinstance(private_key, (bytes, bytearray)):
        if len(private_key) != 32:
            _raise(
                GroupErrorCode.AUTHORITY_SIGNATURE_INVALID,
                "Ed25519 private seed must be 32 bytes",
            )
        return Ed25519PrivateKey.from_private_bytes(bytes(private_key))
    _raise(
        GroupErrorCode.AUTHORITY_SIGNATURE_INVALID,
        f"unsupported private key type {type(private_key).__name__}",
    )


def sign_authority_tuple(
    tuple_fields: Mapping[str, Any],
    private_key: Ed25519PrivateKey | bytes | bytearray,
) -> str:
    """Sign the domain-separated canonical tuple; return base64 signature.

    Provided for the ``build`` gesture and oracle tests only.  The private key
    is externally supplied and never persisted by the library.
    """

    message = signature_input(tuple_fields)
    signer = _coerce_private_key(private_key)
    signature = signer.sign(message)
    return base64.b64encode(signature).decode("ascii")


# ---------------------------------------------------------------------------
# Portable principal directory
# ---------------------------------------------------------------------------
def _require_str(value: Any, *, subject: str, code: "GroupErrorCode") -> str:
    if not isinstance(value, str):
        _raise(code, f"{subject} must be a string")
    if _contains_lone_surrogate(value):
        _raise(code, f"{subject} contains a lone Unicode surrogate")
    return value


def principal_source_hash(claim: Mapping[str, Any]) -> str:
    """Hash compact JSON+LF of exactly the first five ordered claim fields.

    ``source_hash`` is excluded from the hashed bytes and no private principal
    body text is ever consumed.
    """

    if not isinstance(claim, Mapping):
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            "principal claim must be a mapping",
        )
    ordered: "OrderedDict[str, Any]" = OrderedDict()
    for key in PRINCIPAL_CLAIM_KEYS:
        if key not in claim:
            _raise(
                GroupErrorCode.PRINCIPAL_UNRESOLVED,
                f"principal claim is missing required field {key!r}",
                field=key,
            )
        ordered[key] = claim[key]
    try:
        line = canonical_json_line(ordered, sort_keys=False)
    except CanonicalJSONError as error:
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            f"principal claim is not canonical JSON: {error}",
        )
    return sha256_hex(line)


def _validate_principal_claim(claim: Mapping[str, Any]) -> None:
    principal_uid = _require_str(
        claim.get("principal_uid"),
        subject="principal_uid",
        code=GroupErrorCode.PRINCIPAL_UNRESOLVED,
    )
    if not UID_RE.fullmatch(principal_uid):
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            "principal_uid must be an 8-character lowercase hex UID",
            reference_uid=principal_uid,
        )
    principal_class = _require_str(
        claim.get("principal_class"),
        subject="principal_class",
        code=GroupErrorCode.PRINCIPAL_UNRESOLVED,
    )
    if not PRINCIPAL_CLASS_RE.fullmatch(principal_class):
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            f"principal {principal_uid} class is not a portable principal class",
            reference_uid=principal_uid,
        )
    status = _require_str(
        claim.get("status"),
        subject="status",
        code=GroupErrorCode.PRINCIPAL_UNRESOLVED,
    )
    if status not in _VALID_PRINCIPAL_STATUS:
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            f"principal {principal_uid} has unknown status {status!r}",
            reference_uid=principal_uid,
        )
    source_authority_uid = _require_str(
        claim.get("source_authority_uid"),
        subject="source_authority_uid",
        code=GroupErrorCode.PRINCIPAL_UNRESOLVED,
    )
    if not UID_RE.fullmatch(source_authority_uid):
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            "source_authority_uid must be an 8-character lowercase hex UID",
            reference_uid=principal_uid,
        )
    _require_str(
        claim.get("source_revision"),
        subject="source_revision",
        code=GroupErrorCode.PRINCIPAL_UNRESOLVED,
    )
    if not claim["source_revision"]:
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            f"principal {principal_uid} source_revision must be non-empty",
            reference_uid=principal_uid,
        )


def build_principal_row(claim: Mapping[str, Any]) -> "OrderedDict[str, Any]":
    """Validate a claim and return a full portable directory row.

    The returned row has exactly the six ordered keys; ``source_hash`` is
    derived from the first five fields.
    """

    _validate_principal_claim(claim)
    row: "OrderedDict[str, Any]" = OrderedDict()
    for key in PRINCIPAL_CLAIM_KEYS:
        row[key] = claim[key]
    row["source_hash"] = principal_source_hash(claim)
    return row


def build_principals_jsonl(claims: Sequence[Mapping[str, Any]]) -> bytes:
    """Build canonical ``principals.jsonl`` from claims, sorted by UID.

    Each row is compact UTF-8 JSON in the exact directory key order plus one LF.
    """

    if not isinstance(claims, Sequence) or isinstance(claims, (str, bytes)):
        _raise(GroupErrorCode.PRINCIPAL_UNRESOLVED, "claims must be a sequence")
    rows: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for claim in claims:
        row = build_principal_row(claim)
        uid = row["principal_uid"]
        if uid in seen:
            _raise(
                GroupErrorCode.PRINCIPAL_UNRESOLVED,
                f"portable principal directory repeats {uid}",
                reference_uid=uid,
            )
        seen.add(uid)
        rows.append((uid, canonical_json_line(row, sort_keys=False)))
    rows.sort(key=lambda item: item[0])
    return b"".join(line for _, line in rows)


def verify_principal_directory(principals_jsonl: bytes) -> "OrderedDict[str, OrderedDict[str, Any]]":
    """Parse and verify a ``principals.jsonl`` artifact.

    Every row must contain exactly the six ordered claim fields, sort by UID,
    and carry a ``source_hash`` that matches the recomputed hash of its first
    five claim fields.  Any deviation is a ``PRINCIPAL_UNRESOLVED`` refusal.
    """

    if not isinstance(principals_jsonl, (bytes, bytearray)):
        _raise(GroupErrorCode.PRINCIPAL_UNRESOLVED, "principals.jsonl must be bytes")
    text = bytes(principals_jsonl)
    if text and not text.endswith(b"\n"):
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            "principals.jsonl must end with a trailing LF",
        )
    directory: "OrderedDict[str, OrderedDict[str, Any]]" = OrderedDict()
    previous_uid: str | None = None
    for number, raw_line in enumerate(text.split(b"\n")):
        if number == len(text.split(b"\n")) - 1:
            if raw_line == b"":
                continue
            _raise(
                GroupErrorCode.PRINCIPAL_UNRESOLVED,
                "principals.jsonl has content after the final LF",
            )
        try:
            parsed = parse_canonical_json(raw_line)
        except CanonicalJSONError as error:
            _raise(
                GroupErrorCode.PRINCIPAL_UNRESOLVED,
                f"principals.jsonl row {number} is not canonical JSON: {error}",
            )
        if not isinstance(parsed, dict):
            _raise(
                GroupErrorCode.PRINCIPAL_UNRESOLVED,
                f"principals.jsonl row {number} must be a JSON object",
            )
        if tuple(parsed.keys()) != PRINCIPAL_ROW_KEYS:
            _raise(
                GroupErrorCode.PRINCIPAL_UNRESOLVED,
                f"principals.jsonl row {number} keys/order are not the exact directory shape",
            )
        _validate_principal_claim(parsed)
        stored_hash = parsed["source_hash"]
        if not isinstance(stored_hash, str) or not HASH_RE.fullmatch(stored_hash):
            _raise(
                GroupErrorCode.PRINCIPAL_UNRESOLVED,
                f"principals.jsonl row {number} source_hash is not a 64-hex digest",
                reference_uid=parsed.get("principal_uid"),
            )
        expected = principal_source_hash(parsed)
        if stored_hash != expected:
            _raise(
                GroupErrorCode.PRINCIPAL_UNRESOLVED,
                f"principal {parsed['principal_uid']} source_hash does not match its claim",
                reference_uid=parsed["principal_uid"],
            )
        uid = parsed["principal_uid"]
        if previous_uid is not None and uid <= previous_uid:
            _raise(
                GroupErrorCode.PRINCIPAL_UNRESOLVED,
                "principals.jsonl rows must be unique and sorted by principal_uid",
                reference_uid=uid,
            )
        previous_uid = uid
        row: "OrderedDict[str, Any]" = OrderedDict()
        for key in PRINCIPAL_ROW_KEYS:
            row[key] = parsed[key]
        directory[uid] = row
    return directory


def resolve_principal(
    principal_uid: str,
    directory: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Resolve an active principal from a verified directory or refuse."""

    record = directory.get(principal_uid) if isinstance(directory, Mapping) else None
    if not isinstance(record, Mapping) or record.get("principal_uid") != principal_uid:
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            f"principal {principal_uid} is not in the portable directory",
            reference_uid=principal_uid,
        )
    if record.get("status") != "active":
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            f"principal {principal_uid} is not active",
            reference_uid=principal_uid,
        )
    return record


# ---------------------------------------------------------------------------
# Canonical authority artifacts
# ---------------------------------------------------------------------------
def build_groups_jsonl(groups: Sequence[Mapping[str, Any]]) -> bytes:
    """Build canonical ``groups.jsonl`` from group objects, sorted by UID.

    Group semantic canonicalization (the fixed v1 key order, sorted UID lists,
    compact JSON+LF) is delegated to the shared ``group_contract`` library.
    """

    if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)):
        _raise(GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH, "groups must be a sequence")
    rows: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for group in groups:
        semantic = _group_contract.canonical_semantic_object(group)
        uid = semantic["uid"]
        if semantic["status"] != "active":
            _raise(
                GroupErrorCode.GROUP_INACTIVE,
                f"authority corpus group {uid} is not active",
                reference_uid=uid,
            )
        if uid in seen:
            _raise(
                GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
                f"authority corpus repeats group {uid}",
                reference_uid=uid,
            )
        seen.add(uid)
        rows.append((uid, _group_contract.canonical_semantic_bytes(semantic)))
    rows.sort(key=lambda item: item[0])
    return b"".join(line for _, line in rows)


def build_audience_policy(
    *,
    private_group_uid: str,
    reserved_os_always_readable: bool = True,
) -> bytes:
    """Build canonical ``audience-policy.json`` bytes (compact JSON + LF).

    The legacy ``private`` alias binds to the Mike group UID; ``private`` is
    never parsed as a vault UID.  Key order is fixed: ``legacy_aliases`` then
    ``reserved_os``.
    """

    if not isinstance(private_group_uid, str) or not UID_RE.fullmatch(private_group_uid):
        _raise(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            "audience policy requires an 8-hex private-group UID",
        )
    if not isinstance(reserved_os_always_readable, bool):
        _raise(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            "reserved_os.always_readable must be a boolean",
        )
    policy: "OrderedDict[str, Any]" = OrderedDict()
    policy["legacy_aliases"] = OrderedDict((("private", private_group_uid),))
    policy["reserved_os"] = OrderedDict(
        (("always_readable", reserved_os_always_readable),)
    )
    return canonical_json_line(policy, sort_keys=False)


def verify_audience_policy(audience_policy_json: bytes) -> "OrderedDict[str, Any]":
    """Parse ``audience-policy.json`` and require its mandatory bindings.

    The explicit legacy ``private`` alias and the reserved ``os`` semantics must
    both be present; a missing binding is a ``SEGMENT_BINDING_MISSING`` refusal.
    """

    if not isinstance(audience_policy_json, (bytes, bytearray)):
        _raise(GroupErrorCode.SEGMENT_BINDING_MISSING, "audience-policy.json must be bytes")
    try:
        parsed = parse_canonical_json(bytes(audience_policy_json))
    except CanonicalJSONError as error:
        _raise(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            f"audience-policy.json is not canonical JSON: {error}",
        )
    if not isinstance(parsed, dict) or tuple(parsed.keys()) != ("legacy_aliases", "reserved_os"):
        _raise(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            "audience-policy.json must have exactly legacy_aliases and reserved_os",
        )
    legacy = parsed["legacy_aliases"]
    if not isinstance(legacy, dict) or "private" not in legacy:
        _raise(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            "audience policy is missing the legacy private -> group binding",
        )
    private_uid = legacy["private"]
    if not isinstance(private_uid, str) or not UID_RE.fullmatch(private_uid):
        _raise(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            "audience policy legacy private binding must be an 8-hex group UID",
        )
    reserved = parsed["reserved_os"]
    if not isinstance(reserved, dict) or "always_readable" not in reserved:
        _raise(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            "audience policy is missing the reserved os semantics",
        )
    if not isinstance(reserved["always_readable"], bool):
        _raise(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            "reserved_os.always_readable must be a boolean",
        )
    result: "OrderedDict[str, Any]" = OrderedDict()
    result["legacy_aliases"] = OrderedDict((("private", private_uid),))
    result["reserved_os"] = OrderedDict(
        (("always_readable", reserved["always_readable"]),)
    )
    return result


def build_artifact_manifest(artifacts: Mapping[str, bytes]) -> bytes:
    """Build canonical ``artifact-manifest.json`` bytes (compact JSON + LF).

    Rows use the exact key order ``path,byte_length,sha256`` and sort by path;
    the manifest lists exactly the three corpus artifacts and never itself, the
    envelope, trust/high-water state, or projections.
    """

    required = {CORPUS_ARTIFACT, PRINCIPAL_ARTIFACT, AUDIENCE_POLICY_ARTIFACT}
    if not isinstance(artifacts, Mapping) or set(artifacts) != required:
        _raise(
            GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
            "artifact manifest must cover exactly the three corpus artifacts",
        )
    rows: list["OrderedDict[str, Any]"] = []
    for path in sorted(required):
        payload = artifacts[path]
        if not isinstance(payload, (bytes, bytearray)):
            _raise(
                GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
                f"artifact {path} must be bytes",
            )
        row: "OrderedDict[str, Any]" = OrderedDict()
        row["path"] = path
        row["byte_length"] = len(payload)
        row["sha256"] = sha256_hex(payload)
        rows.append(row)
    manifest: "OrderedDict[str, Any]" = OrderedDict()
    manifest["schema_id"] = ARTIFACT_MANIFEST_SCHEMA_ID
    manifest["artifacts"] = rows
    return canonical_json_line(manifest, sort_keys=False)


# ---------------------------------------------------------------------------
# The authority tuple, signature input, and signed envelope
# ---------------------------------------------------------------------------
def _tuple_key_view(fields: Mapping[str, Any]) -> list[str]:
    return [key for key in fields.keys() if key != "signature"]


def canonical_tuple_bytes(fields: Mapping[str, Any]) -> bytes:
    """Serialize the tuple (without ``signature``) in the fixed key order.

    Accepts either an 11-field tuple or a 12-field signed envelope (the
    ``signature`` is stripped).  The remaining keys must be exactly
    :data:`TUPLE_KEY_ORDER` in order.  No trailing LF.
    """

    if not isinstance(fields, Mapping):
        _raise(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH, "tuple must be a mapping")
    present = _tuple_key_view(fields)
    if present != list(TUPLE_KEY_ORDER):
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "authority tuple keys/order do not match the fixed tuple key order",
        )
    ordered: "OrderedDict[str, Any]" = OrderedDict((key, fields[key]) for key in TUPLE_KEY_ORDER)
    try:
        return canonical_json_bytes(ordered, sort_keys=False)
    except CanonicalJSONError as error:
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            f"authority tuple is not canonical JSON: {error}",
        )


def signature_input(fields: Mapping[str, Any]) -> bytes:
    """Return the exact Ed25519 signature input.

    ``b"tropo.group-authority.v1\\n" + <canonical tuple without signature> +
    b"\\n"``.
    """

    return DOMAIN_SEPARATOR + canonical_tuple_bytes(fields) + b"\n"


def _validate_tuple_types(fields: Mapping[str, Any]) -> None:
    """Validate field types well enough to canonicalize deterministically."""

    for key in (
        "authority_uid",
        "corpus_revision",
        "corpus_sha256",
        "principal_directory_revision",
        "principal_directory_sha256",
        "audience_policy_sha256",
        "artifact_identity",
        "signing_key_uid",
    ):
        if not isinstance(fields.get(key), str):
            _raise(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH, f"tuple field {key!r} must be a string")
    for key in ("authority_generation", "canonicalization_version"):
        value = fields.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            _raise(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH, f"tuple field {key!r} must be an integer")
        if not (0 <= value <= _MAX_JSON_INTEGER):
            _raise(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH, f"tuple field {key!r} is out of range")
    prev = fields.get("previous_envelope_sha256")
    if prev is not None and not isinstance(prev, str):
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "tuple field 'previous_envelope_sha256' must be a string or null",
        )


def _validate_tuple_fields(fields: Mapping[str, Any]) -> None:
    """Validate full tuple semantics (formats + cross-field consistency)."""

    _validate_tuple_types(fields)
    authority_uid = fields["authority_uid"]
    if not UID_RE.fullmatch(authority_uid):
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "authority_uid must be an 8-character lowercase hex UID",
            authority_uid=authority_uid,
        )
    for key in (
        "corpus_sha256",
        "principal_directory_sha256",
        "audience_policy_sha256",
        "artifact_identity",
    ):
        if not HASH_RE.fullmatch(fields[key]):
            _raise(
                GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
                f"tuple field {key!r} must be a 64-character lowercase hex digest",
                authority_uid=authority_uid,
            )
    if fields["corpus_revision"] != content_revision(fields["corpus_sha256"]):
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "corpus_revision must equal sha256:<corpus_sha256>",
            authority_uid=authority_uid,
        )
    if fields["principal_directory_revision"] != content_revision(
        fields["principal_directory_sha256"]
    ):
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "principal_directory_revision must equal sha256:<principal_directory_sha256>",
            authority_uid=authority_uid,
        )
    if fields["canonicalization_version"] != CANONICALIZATION_VERSION:
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            f"canonicalization_version must be {CANONICALIZATION_VERSION}",
            authority_uid=authority_uid,
        )
    generation = fields["authority_generation"]
    if generation < 1:
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "authority_generation must be a positive integer",
            authority_uid=authority_uid,
            generation=generation,
        )
    prev = fields["previous_envelope_sha256"]
    if generation == 1:
        if prev is not None:
            _raise(
                GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
                "generation 1 must have previous_envelope_sha256 null",
                authority_uid=authority_uid,
                generation=generation,
            )
    else:
        if not isinstance(prev, str) or not HASH_RE.fullmatch(prev):
            _raise(
                GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
                "every generation after the first must bind previous_envelope_sha256",
                authority_uid=authority_uid,
                generation=generation,
            )
    if not UID_RE.fullmatch(fields["signing_key_uid"]):
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "signing_key_uid must be an 8-character lowercase hex UID",
            authority_uid=authority_uid,
        )


def build_authority_tuple(
    *,
    authority_uid: str,
    groups_jsonl: bytes,
    principals_jsonl: bytes,
    audience_policy_json: bytes,
    artifact_manifest_json: bytes,
    authority_generation: int,
    signing_key_uid: str,
    previous_envelope_sha256: str | None = None,
) -> "OrderedDict[str, Any]":
    """Derive the canonical unsigned tuple from exact artifact bytes."""

    corpus = corpus_sha256(groups_jsonl)
    directory = principal_directory_sha256(principals_jsonl)
    policy = audience_policy_sha256(audience_policy_json)
    identity = artifact_identity(artifact_manifest_json)

    tuple_fields: "OrderedDict[str, Any]" = OrderedDict()
    tuple_fields["authority_uid"] = authority_uid
    tuple_fields["corpus_revision"] = content_revision(corpus)
    tuple_fields["corpus_sha256"] = corpus
    tuple_fields["principal_directory_revision"] = content_revision(directory)
    tuple_fields["principal_directory_sha256"] = directory
    tuple_fields["audience_policy_sha256"] = policy
    tuple_fields["authority_generation"] = authority_generation
    tuple_fields["previous_envelope_sha256"] = previous_envelope_sha256
    tuple_fields["canonicalization_version"] = CANONICALIZATION_VERSION
    tuple_fields["artifact_identity"] = identity
    tuple_fields["signing_key_uid"] = signing_key_uid
    _validate_tuple_fields(tuple_fields)
    return tuple_fields


def build_signed_envelope(
    tuple_fields: Mapping[str, Any],
    signature_b64: str,
) -> "OrderedDict[str, Any]":
    """Return the 12-field signed envelope object (tuple order + signature)."""

    present = _tuple_key_view(tuple_fields)
    if present != list(TUPLE_KEY_ORDER):
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "cannot build an envelope: tuple keys/order are wrong",
        )
    if not isinstance(signature_b64, str):
        _raise(GroupErrorCode.AUTHORITY_SIGNATURE_INVALID, "signature must be a string")
    envelope: "OrderedDict[str, Any]" = OrderedDict()
    for key in TUPLE_KEY_ORDER:
        envelope[key] = tuple_fields[key]
    envelope["signature"] = signature_b64
    return envelope


def canonical_envelope_bytes(envelope: Mapping[str, Any]) -> bytes:
    """Serialize the signed envelope artifact: compact JSON + one trailing LF."""

    if not isinstance(envelope, Mapping) or list(envelope.keys()) != list(ENVELOPE_KEY_ORDER):
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "signed envelope keys/order do not match the fixed envelope key order",
        )
    ordered: "OrderedDict[str, Any]" = OrderedDict((key, envelope[key]) for key in ENVELOPE_KEY_ORDER)
    try:
        return canonical_json_line(ordered, sort_keys=False)
    except CanonicalJSONError as error:
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            f"signed envelope is not canonical JSON: {error}",
        )


def envelope_sha256(signed_envelope_bytes: bytes) -> str:
    """SHA-256 over the exact signed-envelope artifact bytes (including LF)."""

    return sha256_hex(signed_envelope_bytes)


# ---------------------------------------------------------------------------
# Trust: out-of-band fingerprint acceptance (no TOFU / self-accept / wildcard)
# ---------------------------------------------------------------------------
def accept_authority_key(
    *,
    authority_uid: str,
    key_uid: str,
    public_key_b64: str,
    expected_fingerprint: str,
    accepted_by: str,
    accepted_at: str,
    algorithm: str = SUPPORTED_ALGORITHM,
    acceptance: str = ACCEPTANCE_MODE,
) -> "OrderedDict[str, Any]":
    """Produce an accepted-key row after an out-of-band fingerprint match.

    Refuses unsupported algorithms, wildcard/self/local key identities, any
    acceptance mode other than an explicit human fingerprint comparison, and any
    fingerprint that does not equal the exact out-of-band expected value.  There
    is no trust-on-first-use or self-accept path.
    """

    if acceptance in _FORBIDDEN_ACCEPTANCE or acceptance != ACCEPTANCE_MODE:
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            "acceptance must be an explicit out-of-band human fingerprint match",
            authority_uid=authority_uid,
            key_uid=key_uid,
        )
    if algorithm != SUPPORTED_ALGORITHM:
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            f"unsupported signing algorithm {algorithm!r}",
            authority_uid=authority_uid,
            key_uid=key_uid,
        )
    if not isinstance(key_uid, str) or key_uid in _FORBIDDEN_KEY_UIDS or not UID_RE.fullmatch(key_uid):
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            "accepted key_uid must be a concrete 8-hex UID (no wildcard/self/local)",
            authority_uid=authority_uid,
            key_uid=key_uid if isinstance(key_uid, str) else None,
        )
    if not isinstance(authority_uid, str) or not UID_RE.fullmatch(authority_uid):
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            "authority_uid must be an 8-hex UID",
            key_uid=key_uid,
        )
    if not isinstance(accepted_by, str) or not UID_RE.fullmatch(accepted_by):
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            "accepted_by must be an 8-hex principal UID",
            authority_uid=authority_uid,
            key_uid=key_uid,
        )
    if not isinstance(accepted_at, str) or not accepted_at:
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            "accepted_at must be a non-empty timestamp",
            authority_uid=authority_uid,
            key_uid=key_uid,
        )
    if not isinstance(expected_fingerprint, str) or not HASH_RE.fullmatch(expected_fingerprint):
        _raise(
            GroupErrorCode.AUTHORITY_FINGERPRINT_MISMATCH,
            "expected fingerprint must be a 64-hex digest compared out of band",
            authority_uid=authority_uid,
            key_uid=key_uid,
        )
    computed = fingerprint(public_key_b64, code=GroupErrorCode.AUTHORITY_UNTRUSTED)
    if computed != expected_fingerprint:
        _raise(
            GroupErrorCode.AUTHORITY_FINGERPRINT_MISMATCH,
            "public-key fingerprint does not equal the out-of-band expected value",
            authority_uid=authority_uid,
            key_uid=key_uid,
        )
    row: "OrderedDict[str, Any]" = OrderedDict()
    row["authority_uid"] = authority_uid
    row["key_uid"] = key_uid
    row["algorithm"] = SUPPORTED_ALGORITHM
    row["public_key"] = public_key_b64
    row["sha256_fingerprint"] = computed
    row["accepted_by"] = accepted_by
    row["accepted_at"] = accepted_at
    row["acceptance"] = ACCEPTANCE_MODE
    return row


def _validate_accepted_key_row(row: Mapping[str, Any], *, key_uid: str) -> None:
    if not isinstance(row, Mapping) or tuple(row.keys()) != ACCEPTED_KEY_KEYS:
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            "accepted key row is not the exact design-brief shape",
            key_uid=key_uid,
        )
    if row["acceptance"] != ACCEPTANCE_MODE:
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            "accepted key was not accepted via an out-of-band human fingerprint",
            key_uid=key_uid,
        )
    if row["algorithm"] != SUPPORTED_ALGORITHM:
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            f"accepted key uses unsupported algorithm {row['algorithm']!r}",
            key_uid=key_uid,
        )
    stored_key_uid = row["key_uid"]
    if (
        not isinstance(stored_key_uid, str)
        or stored_key_uid in _FORBIDDEN_KEY_UIDS
        or not UID_RE.fullmatch(stored_key_uid)
    ):
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            "accepted key_uid must be a concrete 8-hex UID (no wildcard/self/local)",
            key_uid=key_uid,
        )


def _find_accepted_key(
    trust_record: Mapping[str, Any],
    signing_key_uid: str,
) -> Mapping[str, Any]:
    if not isinstance(trust_record, Mapping):
        _raise(GroupErrorCode.AUTHORITY_UNTRUSTED, "trust record must be a mapping")
    accepted_keys = trust_record.get("accepted_keys")
    if not isinstance(accepted_keys, (list, tuple)):
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            "trust record has no accepted_keys list",
            key_uid=signing_key_uid,
        )
    matches = [
        candidate
        for candidate in accepted_keys
        if isinstance(candidate, Mapping) and candidate.get("key_uid") == signing_key_uid
    ]
    if not matches:
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            f"signing key {signing_key_uid} is not an accepted key",
            key_uid=signing_key_uid,
        )
    if len(matches) > 1:
        _raise(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            f"signing key {signing_key_uid} is ambiguous in the trust record",
            key_uid=signing_key_uid,
        )
    row = matches[0]
    _validate_accepted_key_row(row, key_uid=signing_key_uid)
    return row


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VerifiedAuthority:
    """The immutable outcome of a successful authority verification."""

    authority_uid: str
    authority_generation: int
    corpus_revision: str
    corpus_sha256: str
    principal_directory_revision: str
    principal_directory_sha256: str
    audience_policy_sha256: str
    previous_envelope_sha256: str | None
    canonicalization_version: int
    artifact_identity: str
    signing_key_uid: str
    signature: str
    envelope_sha256: str


def _verify_ed25519_signature(
    tuple_fields: Mapping[str, Any],
    signature_b64: str,
    public_key_b64: str,
) -> None:
    message = signature_input(tuple_fields)
    public_key = load_public_key(
        public_key_b64, code=GroupErrorCode.AUTHORITY_UNTRUSTED
    )
    signature = _b64decode_strict(
        signature_b64,
        subject="signature",
        code=GroupErrorCode.AUTHORITY_SIGNATURE_INVALID,
    )
    if len(signature) != _SIGNATURE_RAW_LEN:
        _raise(
            GroupErrorCode.AUTHORITY_SIGNATURE_INVALID,
            f"Ed25519 signature must be {_SIGNATURE_RAW_LEN} raw bytes",
        )
    try:
        public_key.verify(signature, message)
    except InvalidSignature:
        _raise(
            GroupErrorCode.AUTHORITY_SIGNATURE_INVALID,
            "Ed25519 signature does not verify against the accepted key",
        )


def _verify_artifacts(
    tuple_fields: Mapping[str, Any],
    artifacts: Mapping[str, bytes],
) -> None:
    if not isinstance(artifacts, Mapping):
        _raise(GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH, "artifacts must be a mapping")
    for name in (
        CORPUS_ARTIFACT,
        PRINCIPAL_ARTIFACT,
        AUDIENCE_POLICY_ARTIFACT,
        ARTIFACT_MANIFEST_ARTIFACT,
    ):
        if not isinstance(artifacts.get(name), (bytes, bytearray)):
            _raise(
                GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
                f"missing authority artifact {name!r}",
            )
    checks = (
        (CORPUS_ARTIFACT, "corpus_sha256"),
        (PRINCIPAL_ARTIFACT, "principal_directory_sha256"),
        (AUDIENCE_POLICY_ARTIFACT, "audience_policy_sha256"),
        (ARTIFACT_MANIFEST_ARTIFACT, "artifact_identity"),
    )
    for name, field in checks:
        digest = sha256_hex(artifacts[name])
        if digest != tuple_fields[field]:
            _raise(
                GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
                f"artifact {name} digest does not match tuple {field}",
            )
    # Cross-check the manifest contents against the actual corpus artifact bytes.
    try:
        manifest = parse_canonical_json(bytes(artifacts[ARTIFACT_MANIFEST_ARTIFACT]))
    except CanonicalJSONError as error:
        _raise(
            GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
            f"artifact manifest is not canonical JSON: {error}",
        )
    if (
        not isinstance(manifest, dict)
        or tuple(manifest.keys()) != ("schema_id", "artifacts")
        or manifest["schema_id"] != ARTIFACT_MANIFEST_SCHEMA_ID
        or not isinstance(manifest["artifacts"], list)
    ):
        _raise(
            GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
            "artifact manifest shape is invalid",
        )
    listed = {CORPUS_ARTIFACT, PRINCIPAL_ARTIFACT, AUDIENCE_POLICY_ARTIFACT}
    seen: set[str] = set()
    previous_path: str | None = None
    for row in manifest["artifacts"]:
        if not isinstance(row, dict) or tuple(row.keys()) != ("path", "byte_length", "sha256"):
            _raise(
                GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
                "artifact manifest row shape is invalid",
            )
        path = row["path"]
        if path not in listed or path in seen:
            _raise(
                GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
                f"artifact manifest lists an unexpected or duplicate path {path!r}",
            )
        if previous_path is not None and path <= previous_path:
            _raise(
                GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
                "artifact manifest rows must sort by path",
            )
        previous_path = path
        seen.add(path)
        payload = artifacts[path]
        if row["byte_length"] != len(payload) or row["sha256"] != sha256_hex(payload):
            _raise(
                GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
                f"artifact manifest row {path} does not match the artifact bytes",
            )
    if seen != listed:
        _raise(
            GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
            "artifact manifest does not list exactly the three corpus artifacts",
        )


def verify_authority(
    *,
    signed_envelope: bytes,
    artifacts: Mapping[str, bytes],
    trust_record: Mapping[str, Any],
    expected_fingerprint: str,
) -> VerifiedAuthority:
    """Verify a signed authority envelope against out-of-band trust.

    Order of refusals (each a typed :class:`GroupAuthorityError`):

    1. non-canonical envelope JSON (duplicate key, lone surrogate, float,
       non-UTF-8) or wrong key set/order -> ``AUTHORITY_TUPLE_MISMATCH``;
    2. signing key not accepted / unsupported algorithm / wildcard-self-local
       fallback -> ``AUTHORITY_UNTRUSTED``;
    3. recomputed fingerprint != out-of-band expected value ->
       ``AUTHORITY_FINGERPRINT_MISMATCH``;
    4. Ed25519 signature fails against the accepted key ->
       ``AUTHORITY_SIGNATURE_INVALID``;
    5. internally inconsistent signed tuple -> ``AUTHORITY_TUPLE_MISMATCH``;
    6. artifact bytes disagree with the pinned digests / manifest ->
       ``AUTHORITY_ARTIFACT_MISMATCH``.
    """

    if not isinstance(signed_envelope, (bytes, bytearray)):
        _raise(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH, "signed envelope must be bytes")
    envelope_bytes = bytes(signed_envelope)

    try:
        parsed = parse_canonical_json(envelope_bytes)
    except CanonicalJSONError as error:
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            f"signed envelope is not canonical JSON: {error}",
        )
    if not isinstance(parsed, dict):
        _raise(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH, "signed envelope must be a JSON object")
    if list(parsed.keys()) != list(ENVELOPE_KEY_ORDER):
        _raise(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            "signed envelope keys/order do not match the fixed envelope key order",
        )

    signature_b64 = parsed["signature"]
    if not isinstance(signature_b64, str):
        _raise(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH, "signature must be a string")
    tuple_fields: "OrderedDict[str, Any]" = OrderedDict(
        (key, parsed[key]) for key in TUPLE_KEY_ORDER
    )
    _validate_tuple_types(tuple_fields)
    signing_key_uid = tuple_fields["signing_key_uid"]

    accepted = _find_accepted_key(trust_record, signing_key_uid)
    public_key_b64 = accepted["public_key"]
    computed_fingerprint = fingerprint(public_key_b64, code=GroupErrorCode.AUTHORITY_UNTRUSTED)

    if not isinstance(expected_fingerprint, str) or not HASH_RE.fullmatch(expected_fingerprint):
        _raise(
            GroupErrorCode.AUTHORITY_FINGERPRINT_MISMATCH,
            "expected fingerprint must be a 64-hex digest compared out of band",
            key_uid=signing_key_uid,
        )
    if computed_fingerprint != expected_fingerprint:
        _raise(
            GroupErrorCode.AUTHORITY_FINGERPRINT_MISMATCH,
            "accepted key fingerprint does not equal the out-of-band expected value",
            key_uid=signing_key_uid,
        )
    if accepted.get("sha256_fingerprint") != computed_fingerprint:
        _raise(
            GroupErrorCode.AUTHORITY_FINGERPRINT_MISMATCH,
            "stored trust fingerprint disagrees with the accepted key material",
            key_uid=signing_key_uid,
        )

    _verify_ed25519_signature(tuple_fields, signature_b64, public_key_b64)

    _validate_tuple_fields(tuple_fields)
    _verify_artifacts(tuple_fields, artifacts)

    return VerifiedAuthority(
        authority_uid=tuple_fields["authority_uid"],
        authority_generation=tuple_fields["authority_generation"],
        corpus_revision=tuple_fields["corpus_revision"],
        corpus_sha256=tuple_fields["corpus_sha256"],
        principal_directory_revision=tuple_fields["principal_directory_revision"],
        principal_directory_sha256=tuple_fields["principal_directory_sha256"],
        audience_policy_sha256=tuple_fields["audience_policy_sha256"],
        previous_envelope_sha256=tuple_fields["previous_envelope_sha256"],
        canonicalization_version=tuple_fields["canonicalization_version"],
        artifact_identity=tuple_fields["artifact_identity"],
        signing_key_uid=signing_key_uid,
        signature=signature_b64,
        envelope_sha256=sha256_hex(envelope_bytes),
    )


# ---------------------------------------------------------------------------
# Install / high-water freshness (anti-rollback, anti-replay)
# ---------------------------------------------------------------------------
class InstallStatus(str, Enum):
    """Outcome of an install evaluation."""

    INSTALLED = "installed"
    IDEMPOTENT = "idempotent"


def _validate_high_water_entry(entry: Mapping[str, Any]) -> tuple[int, str]:
    if not isinstance(entry, Mapping) or tuple(entry.keys()) != HIGH_WATER_KEYS:
        _raise(GroupErrorCode.RECOVERY_REQUIRED, "high-water entry shape is invalid")
    generation = entry["authority_generation"]
    envelope = entry["envelope_sha256"]
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        _raise(GroupErrorCode.RECOVERY_REQUIRED, "high-water generation is invalid")
    if not isinstance(envelope, str) or not HASH_RE.fullmatch(envelope):
        _raise(GroupErrorCode.RECOVERY_REQUIRED, "high-water envelope digest is invalid")
    return generation, envelope


def evaluate_install(
    *,
    verified: VerifiedAuthority,
    high_water_entry: Mapping[str, Any] | None,
    pending_recovery: bool = False,
) -> InstallStatus:
    """Decide whether a verified authority may be installed.

    * A dirty/unfinished install surface refuses with ``RECOVERY_REQUIRED``:
      the dev-spec makes even an exact-digest reinstall idempotent *only* after
      recovering and verifying every install surface.
    * The first install (no stored generation) is accepted as the baseline.
    * Same generation, same envelope digest -> idempotent.
    * Same generation, different digest -> ``AUTHORITY_ROLLBACK``.
    * Any older generation -> ``AUTHORITY_ROLLBACK``.
    * A newer generation must chain: ``previous_envelope_sha256`` must equal the
      stored envelope digest, otherwise ``AUTHORITY_ROLLBACK`` (a mis-chained
      "successor" is a replay/fork of the installed lineage).
    """

    if not isinstance(verified, VerifiedAuthority):
        _raise(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH, "verified authority is required to install")
    if pending_recovery:
        _raise(
            GroupErrorCode.RECOVERY_REQUIRED,
            "an unfinished install transaction must be recovered before install",
            authority_uid=verified.authority_uid,
            generation=verified.authority_generation,
        )

    generation = verified.authority_generation
    envelope = verified.envelope_sha256

    if high_water_entry is None:
        return InstallStatus.INSTALLED

    stored_generation, stored_envelope = _validate_high_water_entry(high_water_entry)

    if generation == stored_generation:
        if envelope == stored_envelope:
            return InstallStatus.IDEMPOTENT
        _raise(
            GroupErrorCode.AUTHORITY_ROLLBACK,
            "same generation presented with a different envelope digest",
            authority_uid=verified.authority_uid,
            generation=generation,
        )
    if generation < stored_generation:
        _raise(
            GroupErrorCode.AUTHORITY_ROLLBACK,
            f"generation {generation} is older than installed generation {stored_generation}",
            authority_uid=verified.authority_uid,
            generation=generation,
        )
    if verified.previous_envelope_sha256 != stored_envelope:
        _raise(
            GroupErrorCode.AUTHORITY_ROLLBACK,
            "newer envelope does not chain onto the installed envelope",
            authority_uid=verified.authority_uid,
            generation=generation,
        )
    return InstallStatus.INSTALLED


def install_authority(
    trust_record: Mapping[str, Any],
    verified: VerifiedAuthority,
    *,
    pending_recovery: bool = False,
) -> tuple[dict[str, Any], InstallStatus]:
    """Return a new trust record with advanced high-water, plus the status.

    Pure: the input ``trust_record`` is not mutated.  Persisting the returned
    record under the journaled multi-surface swap is the caller's job.
    """

    if not isinstance(trust_record, Mapping):
        _raise(GroupErrorCode.AUTHORITY_UNTRUSTED, "trust record must be a mapping")
    high_water = trust_record.get("high_water")
    if high_water is None:
        high_water = {}
    if not isinstance(high_water, Mapping):
        _raise(GroupErrorCode.RECOVERY_REQUIRED, "trust high_water is not a mapping")

    entry = high_water.get(verified.authority_uid)
    status = evaluate_install(
        verified=verified,
        high_water_entry=entry,
        pending_recovery=pending_recovery,
    )

    new_high_water: dict[str, Any] = {
        uid: dict(value) if isinstance(value, Mapping) else value
        for uid, value in high_water.items()
    }
    new_high_water[verified.authority_uid] = {
        "authority_generation": verified.authority_generation,
        "envelope_sha256": verified.envelope_sha256,
    }
    new_trust: dict[str, Any] = dict(trust_record)
    accepted = new_trust.get("accepted_keys", [])
    new_trust["accepted_keys"] = list(accepted) if isinstance(accepted, (list, tuple)) else []
    new_trust["high_water"] = new_high_water
    return new_trust, status


__all__ = [
    "ACCEPTANCE_MODE",
    "ARTIFACT_MANIFEST_SCHEMA_ID",
    "AUDIENCE_POLICY_ARTIFACT",
    "ARTIFACT_MANIFEST_ARTIFACT",
    "CANONICALIZATION_VERSION",
    "CORPUS_ARTIFACT",
    "CanonicalJSONError",
    "DOMAIN_SEPARATOR",
    "ENVELOPE_KEY_ORDER",
    "GroupAuthorityError",
    "GroupContractError",
    "GroupErrorCode",
    "InstallStatus",
    "PRINCIPAL_ARTIFACT",
    "PRINCIPAL_CLAIM_KEYS",
    "PRINCIPAL_ROW_KEYS",
    "SIGNED_ENVELOPE_ARTIFACT",
    "SUPPORTED_ALGORITHM",
    "TUPLE_KEY_ORDER",
    "VerifiedAuthority",
    "accept_authority_key",
    "artifact_identity",
    "audience_policy_sha256",
    "build_artifact_manifest",
    "build_audience_policy",
    "build_authority_tuple",
    "build_groups_jsonl",
    "build_principal_row",
    "build_principals_jsonl",
    "build_signed_envelope",
    "canonical_envelope_bytes",
    "canonical_json_bytes",
    "canonical_json_line",
    "canonical_tuple_bytes",
    "content_revision",
    "corpus_sha256",
    "envelope_sha256",
    "evaluate_install",
    "fingerprint",
    "install_authority",
    "load_public_key",
    "parse_canonical_json",
    "previous_envelope_sha256",
    "principal_directory_sha256",
    "principal_source_hash",
    "public_key_base64",
    "public_key_raw_bytes",
    "resolve_principal",
    "sha256_hex",
    "sign_authority_tuple",
    "signature_input",
    "verify_audience_policy",
    "verify_authority",
    "verify_principal_directory",
]
