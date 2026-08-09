"""G2 Stage 1 provenance and authority-chain primitives.

The module keeps the two cryptographic claims deliberately separate:

* an activation-bound agent key proves provenance only;
* a principal key may prove authority only when its custody is declared and a
  live reachability probe did not reproduce use of that key.

Git verification material is derived in memory from activation entries on each
call.  The only allowed-signers file is a short-lived file in a system
temporary directory, removed before the call returns.
"""
from __future__ import annotations

import base64
import binascii
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


SESSION_KEY_ROOT_ENV = "TROPO_AGENT_KEY_ROOT"
SESSION_KEY_DIRNAME = f"tropo-agent-key-sessions-{os.getuid()}"
SYSTEM_TEMPORARY_ROOT = Path("/private/tmp" if sys.platform == "darwin" else "/tmp")
HARNESS_HELPER_NAME = "cursor-git-ssh-keygen"
DEFAULT_FORGE_NAME = "Forger"
DEFAULT_FORGE_EMAIL = "forge@test.local"
AUTHORITY_PUBLIC_KEY_FIELD = "authority_public_key"
KEY_CUSTODY_FIELD = "key_custody"
ORPHAN_KEY_GRACE_SECONDS = 3600
BROKER_METADATA_NAME = "broker.json"
BROKER_SOCKET_NAME = "agent.sock"


class AuthorityErrorCode(str, Enum):
    """Closed, machine-readable refusal vocabulary."""

    PUBLIC_KEY_INVALID = "PUBLIC_KEY_INVALID"
    KEY_MINT_FAILED = "KEY_MINT_FAILED"
    KEY_SESSION_EXISTS = "KEY_SESSION_EXISTS"
    KEY_ROOT_UNSAFE = "KEY_ROOT_UNSAFE"
    KEY_BROKER_UNAVAILABLE = "KEY_BROKER_UNAVAILABLE"
    KEY_BROKER_STOP_FAILED = "KEY_BROKER_STOP_FAILED"
    GIT_COMMAND_FAILED = "GIT_COMMAND_FAILED"
    GIT_CONFIG_MUTATED = "GIT_CONFIG_MUTATED"
    GIT_INDEX_RESTORE_FAILED = "GIT_INDEX_RESTORE_FAILED"
    GIT_REF_RACE = "GIT_REF_RACE"
    SIGNATURE_MISSING = "SIGNATURE_MISSING"
    SIGNATURE_MALFORMED = "SIGNATURE_MALFORMED"
    SIGNATURE_UNSUPPORTED = "SIGNATURE_UNSUPPORTED"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    SIGNING_KEY_MISMATCH = "SIGNING_KEY_MISMATCH"
    ACTIVATION_KEY_UNBOUND = "ACTIVATION_KEY_UNBOUND"
    ACTIVATION_RETIRED = "ACTIVATION_RETIRED"
    ACTIVATION_GATE_INVALID = "ACTIVATION_GATE_INVALID"
    ACTIVATION_AMBIGUOUS = "ACTIVATION_AMBIGUOUS"
    ACTIVATION_KEY_REUSE = "ACTIVATION_KEY_REUSE"
    # Compatibility name only; enforcement is lifecycle-wide and order-free.
    CROSS_GENERATION_KEY_REUSE = "ACTIVATION_KEY_REUSE"
    ACTIVATION_GENERATION_INVALID = "ACTIVATION_GENERATION_INVALID"
    ACTIVATION_HISTORY_UNPARSEABLE = "ACTIVATION_HISTORY_UNPARSEABLE"
    ACTIVATION_HISTORY_IDENTITY_CONFLICT = "ACTIVATION_HISTORY_IDENTITY_CONFLICT"
    ACTIVATION_LINEAGE_INCOMPLETE = "ACTIVATION_LINEAGE_INCOMPLETE"
    ACTIVATION_PREDECESSOR_INVALID = "ACTIVATION_PREDECESSOR_INVALID"
    ACTIVATION_IDENTITY_CONFLICT = "ACTIVATION_IDENTITY_CONFLICT"
    ACTIVATION_CLASS_MISMATCH = "ACTIVATION_CLASS_MISMATCH"
    ACTIVATION_CLASS_UNREGISTERED = "ACTIVATION_CLASS_UNREGISTERED"
    ACTIVATION_KEY_MISSING = "ACTIVATION_KEY_MISSING"
    CANONICAL_AGENT_CLASS_CONFLICT = "CANONICAL_AGENT_CLASS_CONFLICT"
    CANONICAL_AGENT_GENERATION_CONFLICT = "CANONICAL_AGENT_GENERATION_CONFLICT"
    ACTIVATOR_UNRESOLVED = "ACTIVATOR_UNRESOLVED"
    TWO_KEYS_ONE_SLUG = "TWO_KEYS_ONE_SLUG"
    ONE_KEY_MANY_SLUGS = "ONE_KEY_MANY_SLUGS"
    ONE_KEY_MANY_AUTHORS = "ONE_KEY_MANY_AUTHORS"
    AUTHOR_IDENTITY_MISMATCH = "AUTHOR_IDENTITY_MISMATCH"
    AGENT_KEY_PROVENANCE_ONLY = "AGENT_KEY_PROVENANCE_ONLY"
    HARNESS_KEY_PROVENANCE_ONLY = "HARNESS_KEY_PROVENANCE_ONLY"
    HARNESS_SIGNER_UNAVAILABLE = "HARNESS_SIGNER_UNAVAILABLE"
    ANCHOR_REACHABLE = "ANCHOR_REACHABLE"
    ANCHOR_UNREACHABLE = "ANCHOR_UNREACHABLE"
    ANCHOR_PROBE_FAILED = "ANCHOR_PROBE_FAILED"
    KNOWN_REACHABLE_ANCHOR_NOT_REACHED = "KNOWN_REACHABLE_ANCHOR_NOT_REACHED"
    KEY_CUSTODY_MISSING = "KEY_CUSTODY_MISSING"
    CUSTODY_STAGE_INVALID = "CUSTODY_STAGE_INVALID"
    CUSTODY_EVIDENCE_INVALID = "CUSTODY_EVIDENCE_INVALID"
    CLAIM_SCHEMA_INVALID = "CLAIM_SCHEMA_INVALID"
    AUTHORITY_PRINCIPAL_INELIGIBLE = "AUTHORITY_PRINCIPAL_INELIGIBLE"
    AUTHORITY_ANCHOR_UNTRUSTED = "AUTHORITY_ANCHOR_UNTRUSTED"
    AUTHORITY_REACHABILITY_UNPROVEN = "AUTHORITY_REACHABILITY_UNPROVEN"
    CANONICAL_ROOT_INVALID = "CANONICAL_ROOT_INVALID"


class AnchorClassification(str, Enum):
    """Whether a candidate uses the known agent-reachable harness surface."""

    CANDIDATE = "candidate"
    KNOWN_HARNESS_KEY = "known-harness-key"
    KNOWN_HARNESS_PROGRAM = "known-harness-program"
    KNOWN_HARNESS_KEY_AND_PROGRAM = "known-harness-key-and-program"


class AuthorityChainError(RuntimeError):
    """Typed, fail-closed authority-chain refusal."""

    def __init__(
        self,
        code: AuthorityErrorCode,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": self.code.value,
            "message": self.message,
            "details": self.details,
        }


def _fail(
    code: AuthorityErrorCode,
    message: str,
    **details: Any,
) -> "None":
    raise AuthorityChainError(code, message, details=details)


@dataclass(frozen=True)
class Finding:
    code: AuthorityErrorCode
    message: str
    activation_uids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "activation_uids": list(self.activation_uids),
        }


@dataclass(frozen=True)
class OpenSSHPublicKey:
    algorithm: str
    blob: bytes
    key_point: bytes
    canonical: str
    fingerprint: str


@dataclass(frozen=True)
class MintedAgentKey:
    activation_uid: str
    public_key: str
    broker_socket: Path
    broker_pid: int


@dataclass(frozen=True)
class ActivationSigningBroker:
    activation_uid: str
    socket_path: Path
    pid: int
    public_key: str


@dataclass(frozen=True)
class ActivationRecord:
    uid: str
    agent: str
    generation: str
    status: str
    activated_by: str
    activated_at: str
    agent_public_key: str | None
    name: str
    agent_class: str = ""
    agent_root: str = ""
    source_path: Path | None = None
    canonical_agent_class: str = ""
    canonical_generation: str = ""
    canonical_current_activation_uid: str = ""
    class_registry_checked: bool = False
    history_invalid: bool = False
    history_invalid_reason: str = ""
    history_invalid_code: AuthorityErrorCode = (
        AuthorityErrorCode.ACTIVATION_HISTORY_UNPARSEABLE
    )
    history_affected_agents: tuple[str, ...] = ()
    history_affected_uids: tuple[str, ...] = ()
    agent_key_declared: bool = False
    agent_key_voided: bool = False
    agent_public_key_voided: str | None = None
    immutable_amendments: tuple[tuple[str, str, str], ...] = ()
    predecessor_activation_uid: str | None = None
    predecessor_link_declared: bool = False
    uid_declared: bool = True
    activation_type: str = "activation"
    type_declared: bool = True
    history_only: bool = False
    snapshot_lineage: str = ""

    @property
    def public_key(self) -> OpenSSHPublicKey | None:
        if not self.agent_public_key:
            return None
        return parse_openssh_public_key(self.agent_public_key)


@dataclass(frozen=True)
class ActivationAnalysis:
    records: tuple[ActivationRecord, ...]
    invalid_reasons: Mapping[str, tuple[Finding, ...]]
    findings: tuple[Finding, ...]

    def is_gate_valid(self, uid: str) -> bool:
        return not self.invalid_reasons.get(uid)

    def reasons_for(self, uid: str) -> tuple[Finding, ...]:
        return self.invalid_reasons.get(uid, ())


@dataclass(frozen=True)
class CommitSignature:
    commit: str
    public_key: str
    key_blob: bytes = field(repr=False)
    key_fingerprint: str
    author_name: str
    author_email: str
    namespace: str
    hash_algorithm: str

    @property
    def author_identity(self) -> str:
        return f"{self.author_name} <{self.author_email}>"

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit": self.commit,
            "public_key": self.public_key,
            "key_fingerprint": self.key_fingerprint,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "author_identity": self.author_identity,
            "namespace": self.namespace,
            "hash_algorithm": self.hash_algorithm,
        }


@dataclass(frozen=True)
class SignedCommit:
    commit: str
    signature: CommitSignature
    activation_uid: str


@dataclass(frozen=True)
class ChainResult:
    commit: str
    signature_key: str
    key_fingerprint: str
    author_identity: str
    provenance: str
    authority: bool
    activation_uid: str | None = None
    agent: str | None = None
    generation: str | None = None
    activated_by: str | None = None
    activator_type: str | None = None
    activator_uid: str | None = None
    principal_uid: str | None = None
    key_custody: str | None = None
    findings: tuple[Finding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "commit": self.commit,
            "signature_key": self.signature_key,
            "key_fingerprint": self.key_fingerprint,
            "author_identity": self.author_identity,
            "provenance": self.provenance,
            "authority": self.authority,
            "activation_uid": self.activation_uid,
            "agent": self.agent,
            "generation": self.generation,
            "activated_by": self.activated_by,
            "activator_type": self.activator_type,
            "activator_uid": self.activator_uid,
            "principal_uid": self.principal_uid,
            "key_custody": self.key_custody,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class ReachabilityProbeResult:
    attempted: bool
    reachable: bool
    authority_accepted: bool
    positive_control_passed: bool
    finding: AuthorityErrorCode
    candidate_public_key: str
    signing_program: str
    fabricated_author: str
    commit: str | None = None
    signature: CommitSignature | None = None
    detail: str = ""
    candidate_classification: AnchorClassification = AnchorClassification.CANDIDATE
    positive_control_key: str | None = None
    positive_control_commit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "reachable": self.reachable,
            "authority_accepted": self.authority_accepted,
            "positive_control_passed": self.positive_control_passed,
            "finding": self.finding.value,
            "candidate_public_key": self.candidate_public_key,
            "signing_program": self.signing_program,
            "fabricated_author": self.fabricated_author,
            "commit": self.commit,
            "signature": self.signature.to_dict() if self.signature else None,
            "detail": self.detail,
            "candidate_classification": self.candidate_classification.value,
            "positive_control_key": self.positive_control_key,
            "positive_control_commit": self.positive_control_commit,
        }


@dataclass(frozen=True)
class AuthorityClaim:
    commit: str
    principal_uid: str
    principal_slug: str
    signature_key: str
    key_fingerprint: str
    key_custody: str
    authority: bool = True

    def to_dict(self) -> dict[str, Any]:
        # key_custody is intentionally inseparable from the rendered claim.
        return {
            "commit": self.commit,
            "principal_uid": self.principal_uid,
            "principal_slug": self.principal_slug,
            "signature_key": self.signature_key,
            "key_fingerprint": self.key_fingerprint,
            "key_custody": self.key_custody,
            "authority": self.authority,
        }


@dataclass(frozen=True)
class CustodyStageImplementation:
    stage: str
    key_custody: str
    required_proof: str


AUTHORITY_CLAIM_SCHEMA = (
    "commit",
    "principal_uid",
    "principal_slug",
    "signature_key",
    "key_fingerprint",
    "key_custody",
    "authority",
)

CUSTODY_STAGE_IMPLEMENTATIONS: Mapping[str, CustodyStageImplementation] = {
    "stage-1": CustodyStageImplementation(
        "stage-1",
        "ephemeral",
        "activation-bound-runtime-key",
    ),
    "stage-2": CustodyStageImplementation(
        "stage-2",
        "file",
        "principal-file-key",
    ),
    "stage-3": CustodyStageImplementation(
        "stage-3",
        "fido2",
        "user-presence-hardware-key",
    ),
}


@dataclass(frozen=True)
class SkippedCommitSignature:
    commit: str
    code: AuthorityErrorCode
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "commit": self.commit,
            "classification": self.code.value,
            "detail": self.detail,
        }


class CommitSignatureAudit(list[CommitSignature]):
    """List-compatible audit result with named unsupported-signature skips."""

    def __init__(
        self,
        signatures: Iterable[CommitSignature],
        skipped: Iterable[SkippedCommitSignature],
    ) -> None:
        super().__init__(signatures)
        self.skipped = tuple(skipped)


def _read_ssh_string(data: bytes, offset: int, subject: str) -> tuple[bytes, int]:
    if offset + 4 > len(data):
        _fail(
            AuthorityErrorCode.SIGNATURE_MALFORMED,
            f"{subject} is truncated before an SSH string length",
        )
    length = struct.unpack(">I", data[offset : offset + 4])[0]
    start = offset + 4
    end = start + length
    if end > len(data):
        _fail(
            AuthorityErrorCode.SIGNATURE_MALFORMED,
            f"{subject} is truncated inside an SSH string",
        )
    return data[start:end], end


def parse_openssh_public_key(value: str) -> OpenSSHPublicKey:
    """Strictly parse and canonicalize a supported OpenSSH public-key line."""

    if not isinstance(value, str):
        _fail(AuthorityErrorCode.PUBLIC_KEY_INVALID, "public key must be a string")
    parts = value.strip().split()
    if len(parts) < 2:
        _fail(
            AuthorityErrorCode.PUBLIC_KEY_INVALID,
            "public key must contain an algorithm and base64 key blob",
        )
    algorithm, encoded = parts[:2]
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        _fail(AuthorityErrorCode.PUBLIC_KEY_INVALID, "public-key blob is not strict base64")
    canonical_b64 = base64.b64encode(blob).decode("ascii")
    if encoded != canonical_b64:
        _fail(
            AuthorityErrorCode.PUBLIC_KEY_INVALID,
            "public-key blob base64 is noncanonical or has trailing padding/data",
        )
    if algorithm not in {"ssh-ed25519", "sk-ssh-ed25519@openssh.com"}:
        _fail(
            AuthorityErrorCode.PUBLIC_KEY_INVALID,
            f"unsupported public-key algorithm {algorithm!r}",
        )
    try:
        blob_algorithm, offset = _read_ssh_string(blob, 0, "public-key blob")
        decoded_algorithm = blob_algorithm.decode("ascii")
        key_material, offset = _read_ssh_string(blob, offset, "public-key blob")
        application = None
        if algorithm == "sk-ssh-ed25519@openssh.com":
            application, offset = _read_ssh_string(blob, offset, "public-key blob")
    except (UnicodeDecodeError, AuthorityChainError):
        _fail(
            AuthorityErrorCode.PUBLIC_KEY_INVALID,
            "public-key blob has invalid or truncated SSH wire strings",
        )
    if decoded_algorithm != algorithm:
        _fail(
            AuthorityErrorCode.PUBLIC_KEY_INVALID,
            "public-key line algorithm does not match its SSH key blob",
        )
    if len(key_material) != 32:
        _fail(
            AuthorityErrorCode.PUBLIC_KEY_INVALID,
            "Ed25519 public-key material must be exactly 32 bytes",
            key_length=len(key_material),
        )
    if application is not None:
        if not application:
            _fail(
                AuthorityErrorCode.PUBLIC_KEY_INVALID,
                "security-key Ed25519 application string must not be empty",
            )
        try:
            application_text = application.decode("utf-8")
        except UnicodeDecodeError:
            _fail(
                AuthorityErrorCode.PUBLIC_KEY_INVALID,
                "security-key Ed25519 application string must be valid UTF-8",
            )
        if "\x00" in application_text or any(
            ord(character) < 0x20 for character in application_text
        ):
            _fail(
                AuthorityErrorCode.PUBLIC_KEY_INVALID,
                "security-key Ed25519 application string contains control bytes",
            )
    if offset != len(blob):
        _fail(
            AuthorityErrorCode.PUBLIC_KEY_INVALID,
            "public-key blob contains trailing SSH wire data",
            trailing_bytes=len(blob) - offset,
        )
    return OpenSSHPublicKey(
        algorithm=algorithm,
        blob=blob,
        key_point=key_material,
        canonical=f"{algorithm} {canonical_b64}",
        fingerprint=hashlib.sha256(key_material).hexdigest(),
    )


def public_key_from_blob(blob: bytes) -> OpenSSHPublicKey:
    try:
        algorithm_raw, offset = _read_ssh_string(blob, 0, "public-key blob")
        algorithm = algorithm_raw.decode("ascii")
    except (UnicodeDecodeError, AuthorityChainError):
        _fail(AuthorityErrorCode.PUBLIC_KEY_INVALID, "SSHSIG contains an invalid key blob")
    if offset >= len(blob):
        _fail(AuthorityErrorCode.PUBLIC_KEY_INVALID, "SSHSIG key blob has no key material")
    return parse_openssh_public_key(
        f"{algorithm} {base64.b64encode(blob).decode('ascii')}"
    )


def _validate_activation_uid(activation_uid: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{8}", activation_uid):
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            "activation UID is not safe for session-key containment",
            activation_uid=activation_uid,
        )


def _reject_external_key_root(key_root: Path | None) -> None:
    configured = os.environ.get(SESSION_KEY_ROOT_ENV)
    if key_root is not None or configured:
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            (
                "agent key roots are system-selected; arbitrary paths and the legacy "
                f"{SESSION_KEY_ROOT_ENV} override are refused"
            ),
            supplied_root=str(key_root or configured),
        )


def _validate_owned_directory(path: Path, *, subject: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        _fail(AuthorityErrorCode.KEY_ROOT_UNSAFE, f"cannot inspect {subject}: {error}")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail(AuthorityErrorCode.KEY_ROOT_UNSAFE, f"{subject} is not a real directory")
    if metadata.st_uid != os.geteuid():
        _fail(AuthorityErrorCode.KEY_ROOT_UNSAFE, f"{subject} is not owned by this user")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            f"{subject} permissions must be exactly 0700",
            mode=oct(stat.S_IMODE(metadata.st_mode)),
        )


def session_key_root() -> Path:
    """Return the system-selected 0700 parent for random session directories."""

    _reject_external_key_root(None)
    try:
        temporary_root = SYSTEM_TEMPORARY_ROOT.resolve(strict=True)
    except OSError as error:
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            f"fixed system temporary root is unavailable: {error}",
        )
    if temporary_root != SYSTEM_TEMPORARY_ROOT:
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            "fixed system temporary root resolves somewhere unexpected",
            resolved=str(temporary_root),
        )
    root = temporary_root / SESSION_KEY_DIRNAME
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError as error:
        _fail(AuthorityErrorCode.KEY_ROOT_UNSAFE, f"cannot create session-key root: {error}")
    _validate_owned_directory(root, subject="session-key root")
    if root.parent != temporary_root:
        _fail(AuthorityErrorCode.KEY_ROOT_UNSAFE, "session-key root escaped system temporary root")
    return root


def _session_directories(activation_uid: str) -> list[Path]:
    _validate_activation_uid(activation_uid)
    root = session_key_root()
    matches: list[Path] = []
    try:
        children = list(root.iterdir())
    except OSError as error:
        _fail(AuthorityErrorCode.KEY_ROOT_UNSAFE, f"cannot enumerate session-key root: {error}")
    for child in children:
        if not child.name.startswith(f"{activation_uid}-"):
            continue
        _validate_owned_directory(child, subject="activation session-key directory")
        if child.parent != root:
            _fail(AuthorityErrorCode.KEY_ROOT_UNSAFE, "activation key directory escaped containment")
        matches.append(child)
    return matches


def _validate_broker_metadata(path: Path) -> Mapping[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as error:
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            f"cannot inspect activation signing-broker metadata: {error}",
        )
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            "activation signing-broker metadata must be an owned 0600 regular file",
            path=str(path),
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            f"activation signing-broker metadata is unreadable: {error}",
        )
    if not isinstance(payload, dict) or set(payload) != {
        "activation_uid",
        "pid",
        "socket",
        "version",
    }:
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            "activation signing-broker metadata has an unexpected schema",
        )
    return payload


def _validate_broker_process(pid: int) -> None:
    if pid <= 1 or pid == os.getpid():
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            "activation signing-broker PID is not safe",
            pid=pid,
        )
    try:
        os.kill(pid, 0)
    except OSError as error:
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            f"activation signing broker is not running: {error}",
            pid=pid,
        )
    inspected = subprocess.run(
        ["ps", "-p", str(pid), "-o", "comm="],
        capture_output=True,
        text=True,
        timeout=10,
    )
    executable_name = Path(inspected.stdout.strip()).name
    if executable_name != "ssh-agent":
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            "activation signing-broker PID does not identify ssh-agent",
            pid=pid,
            executable=executable_name,
        )


def _broker_process_state(pid: int) -> str | None:
    inspected = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat="],
        capture_output=True,
        text=True,
        timeout=10,
    )
    state = inspected.stdout.strip()
    return state or None


def _broker_environment(socket_path: Path, pid: int) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "SSH_AUTH_SOCK": str(socket_path),
            "SSH_AGENT_PID": str(pid),
        }
    )
    return environment


def _write_broker_metadata(
    session_dir: Path,
    activation_uid: str,
    pid: int,
) -> None:
    metadata_path = session_dir / BROKER_METADATA_NAME
    descriptor = os.open(
        metadata_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(
            {
                "activation_uid": activation_uid,
                "pid": pid,
                "socket": BROKER_SOCKET_NAME,
                "version": 1,
            },
            stream,
            sort_keys=True,
        )
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def activation_signing_broker(
    activation_uid: str,
    *,
    expected_public_key: str | None = None,
    key_root: Path | None = None,
) -> ActivationSigningBroker:
    """Resolve and attest one activation's process-held signing capability."""

    _reject_external_key_root(key_root)
    matches = _session_directories(activation_uid)
    if len(matches) != 1:
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            "activation does not resolve to exactly one random signing-broker directory",
            activation_uid=activation_uid,
            matches=len(matches),
        )
    directory = matches[0]
    payload = _validate_broker_metadata(directory / BROKER_METADATA_NAME)
    try:
        pid = int(payload["pid"])
    except (TypeError, ValueError):
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            "activation signing-broker PID is malformed",
        )
    if payload["activation_uid"] != activation_uid or payload["version"] != 1:
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            "activation signing-broker metadata does not bind this activation",
            activation_uid=activation_uid,
        )
    if payload["socket"] != BROKER_SOCKET_NAME:
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            "activation signing-broker socket escaped its random directory",
        )
    socket_path = directory / BROKER_SOCKET_NAME
    try:
        socket_metadata = socket_path.lstat()
    except OSError as error:
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            f"activation signing-broker socket is unavailable: {error}",
        )
    if (
        stat.S_ISLNK(socket_metadata.st_mode)
        or not stat.S_ISSOCK(socket_metadata.st_mode)
        or socket_metadata.st_uid != os.geteuid()
    ):
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            "activation signing-broker endpoint is not an owned Unix socket",
            path=str(socket_path),
        )
    _validate_broker_process(pid)
    ssh_add = shutil.which("ssh-add")
    if not ssh_add:
        _fail(AuthorityErrorCode.KEY_BROKER_UNAVAILABLE, "ssh-add is unavailable")
    listed = subprocess.run(
        [ssh_add, "-L"],
        capture_output=True,
        text=True,
        timeout=30,
        env=_broker_environment(socket_path, pid),
    )
    if listed.returncode != 0:
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            "activation signing broker did not expose its public identity",
            stderr=(listed.stderr or listed.stdout).strip(),
        )
    keys = [
        parse_openssh_public_key(line).canonical
        for line in listed.stdout.splitlines()
        if line.strip()
    ]
    if len(keys) != 1:
        _fail(
            AuthorityErrorCode.KEY_BROKER_UNAVAILABLE,
            "activation signing broker must contain exactly one key",
            key_count=len(keys),
        )
    if (
        expected_public_key
        and parse_openssh_public_key(expected_public_key).key_point
        != parse_openssh_public_key(keys[0]).key_point
    ):
        _fail(
            AuthorityErrorCode.SIGNING_KEY_MISMATCH,
            "activation signing broker does not hold the activation-bound public key",
        )
    return ActivationSigningBroker(activation_uid, socket_path, pid, keys[0])


def _validate_removable_key_directory(directory: Path, activation_uid: str) -> None:
    """Reject links, foreign ownership, and unexpected files before deletion."""

    _validate_owned_directory(directory, subject="activation session-key directory")
    allowed_names = {BROKER_METADATA_NAME, BROKER_SOCKET_NAME}
    try:
        children = list(directory.iterdir())
    except OSError as error:
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            f"cannot inspect activation key directory: {error}",
            activation_uid=activation_uid,
        )
    for child in children:
        if child.name not in allowed_names:
            _fail(
                AuthorityErrorCode.KEY_ROOT_UNSAFE,
                "activation key directory contains an unexpected entry",
                activation_uid=activation_uid,
                path=str(child),
            )
        try:
            metadata = child.lstat()
        except OSError as error:
            _fail(
                AuthorityErrorCode.KEY_ROOT_UNSAFE,
                f"cannot inspect activation key entry: {error}",
                activation_uid=activation_uid,
                path=str(child),
            )
        expected_kind = (
            stat.S_ISREG(metadata.st_mode)
            if child.name == BROKER_METADATA_NAME
            else stat.S_ISSOCK(metadata.st_mode)
        )
        if stat.S_ISLNK(metadata.st_mode) or not expected_kind or metadata.st_uid != os.geteuid():
            _fail(
                AuthorityErrorCode.KEY_ROOT_UNSAFE,
                "activation signing-broker entry has an unsafe type or owner",
                activation_uid=activation_uid,
                path=str(child),
            )
        if (
            child.name == BROKER_METADATA_NAME
            and stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail(
                AuthorityErrorCode.KEY_ROOT_UNSAFE,
                "activation signing-broker metadata must remain owner-only (0600)",
                activation_uid=activation_uid,
                mode=oct(stat.S_IMODE(metadata.st_mode)),
            )


def mint_agent_keypair(
    activation_uid: str,
    agent: str,
    generation: str,
    *,
    key_root: Path | None = None,
) -> MintedAgentKey:
    """Mint into a dedicated ssh-agent; private bytes never enter the filesystem."""

    _reject_external_key_root(key_root)
    _validate_activation_uid(activation_uid)
    root = session_key_root()
    if _session_directories(activation_uid):
        _fail(
            AuthorityErrorCode.KEY_SESSION_EXISTS,
            "refusing to reuse an existing per-activation key directory",
            activation_uid=activation_uid,
            path=str(root),
        )
    try:
        session_dir = Path(tempfile.mkdtemp(prefix=f"{activation_uid}-", dir=str(root)))
        os.chmod(session_dir, 0o700)
        _validate_owned_directory(session_dir, subject="activation session-key directory")
    except (OSError, AuthorityChainError) as error:
        if isinstance(error, AuthorityChainError):
            raise
        _fail(AuthorityErrorCode.KEY_ROOT_UNSAFE, f"cannot create random session directory: {error}")
    ssh_agent = shutil.which("ssh-agent")
    ssh_add = shutil.which("ssh-add")
    if not ssh_agent or not ssh_add:
        shutil.rmtree(session_dir, ignore_errors=True)
        _fail(
            AuthorityErrorCode.KEY_MINT_FAILED,
            "ssh-agent and ssh-add are required for process-held activation keys",
        )
    socket_path = session_dir / BROKER_SOCKET_NAME
    started = subprocess.run(
        [ssh_agent, "-a", str(socket_path), "-s"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    pid_match = re.search(r"SSH_AGENT_PID=(\d+)", started.stdout)
    if started.returncode != 0 or pid_match is None:
        shutil.rmtree(session_dir, ignore_errors=True)
        _fail(
            AuthorityErrorCode.KEY_MINT_FAILED,
            "ssh-agent could not start the per-activation signing broker",
            stderr=(started.stderr or started.stdout).strip(),
        )
    broker_pid = int(pid_match.group(1))
    environment = _broker_environment(socket_path, broker_pid)
    private_buffer: bytearray | None = None
    try:
        _write_broker_metadata(session_dir, activation_uid, broker_pid)
        private_key = Ed25519PrivateKey.generate()
        serialized = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption(),
        )
        private_buffer = bytearray(serialized)
        del serialized
        public_key = parse_openssh_public_key(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.OpenSSH,
                format=serialization.PublicFormat.OpenSSH,
            ).decode("ascii")
        ).canonical
        del private_key
        loaded = subprocess.run(
            [ssh_add, "-"],
            input=bytes(private_buffer),
            capture_output=True,
            timeout=30,
            env=environment,
        )
        for index in range(len(private_buffer)):
            private_buffer[index] = 0
        private_buffer = None
        if loaded.returncode != 0:
            _fail(
                AuthorityErrorCode.KEY_MINT_FAILED,
                "ssh-add could not transfer the generated key into the signing broker",
                stderr=(loaded.stderr or loaded.stdout).decode(errors="replace").strip(),
            )
        broker = activation_signing_broker(
            activation_uid,
            expected_public_key=public_key,
        )
    except Exception as error:
        if private_buffer is not None:
            for index in range(len(private_buffer)):
                private_buffer[index] = 0
        try:
            os.kill(broker_pid, signal.SIGTERM)
        except OSError:
            pass
        shutil.rmtree(session_dir, ignore_errors=True)
        if isinstance(error, AuthorityChainError):
            raise
        _fail(AuthorityErrorCode.KEY_MINT_FAILED, f"could not finalize signing broker: {error}")
    return MintedAgentKey(activation_uid, public_key, broker.socket_path, broker.pid)


def remove_agent_keypair(
    activation_uid: str,
    *,
    key_root: Path | None = None,
) -> bool:
    """Stop and remove one terminal activation's process-held signing broker."""

    _reject_external_key_root(key_root)
    matches = _session_directories(activation_uid)
    if not matches:
        return False
    if len(matches) != 1:
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            "refusing ambiguous session-key destruction",
            activation_uid=activation_uid,
            matches=len(matches),
        )
    target = matches[0]
    _validate_removable_key_directory(target, activation_uid)
    metadata_path = target / BROKER_METADATA_NAME
    if metadata_path.exists():
        broker = activation_signing_broker(activation_uid)
        stopped = subprocess.run(
            [shutil.which("ssh-agent") or "ssh-agent", "-k"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_broker_environment(broker.socket_path, broker.pid),
        )
        if stopped.returncode != 0:
            _fail(
                AuthorityErrorCode.KEY_BROKER_STOP_FAILED,
                "could not stop the activation signing broker",
                activation_uid=activation_uid,
                stderr=(stopped.stderr or stopped.stdout).strip(),
            )
        for _attempt in range(20):
            state = _broker_process_state(broker.pid)
            if state is None or state.startswith("Z"):
                break
            time.sleep(0.05)
        else:
            _fail(
                AuthorityErrorCode.KEY_BROKER_STOP_FAILED,
                "activation signing broker remained live after terminal stop",
                activation_uid=activation_uid,
                pid=broker.pid,
                process_state=state,
            )
    try:
        shutil.rmtree(target)
    except OSError as error:
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            f"could not remove activation session key: {error}",
            activation_uid=activation_uid,
            path=str(target),
        )
    return True


def cleanup_stale_agent_keypairs(
    activation_records: Sequence[ActivationRecord],
    *,
    orphan_activation_uids: Iterable[str] = (),
    orphan_grace_seconds: int = ORPHAN_KEY_GRACE_SECONDS,
    now: float | None = None,
) -> tuple[str, ...]:
    """Remove terminal keys and old orphaned crash residue at a safe boundary.

    Active and paused activation keys are process-independent runtime state and
    survive CLI process exit. A directory with no activation entry is removed
    only after a grace period so concurrent opens cannot delete one another's
    freshly minted key before the activation entry lands.
    """

    if orphan_grace_seconds < 0:
        _fail(
            AuthorityErrorCode.KEY_ROOT_UNSAFE,
            "orphan key grace period cannot be negative",
        )
    current_time = now if now is not None else time.time()
    records_by_uid: dict[str, list[ActivationRecord]] = defaultdict(list)
    for record in activation_records:
        records_by_uid[record.uid].append(record)
    orphan_scope = set(orphan_activation_uids)
    for activation_uid in orphan_scope:
        _validate_activation_uid(activation_uid)
    removed: list[str] = []
    root = session_key_root()
    try:
        children = list(root.iterdir())
    except OSError as error:
        _fail(AuthorityErrorCode.KEY_ROOT_UNSAFE, f"cannot enumerate key runtime root: {error}")
    for directory in children:
        match = re.fullmatch(r"([0-9a-f]{8})-[A-Za-z0-9_-]+", directory.name)
        if not match:
            continue
        activation_uid = match.group(1)
        _validate_owned_directory(directory, subject="activation session-key directory")
        records = records_by_uid.get(activation_uid, [])
        preserve = any(record.status in {"active", "paused"} for record in records)
        terminal = bool(records) and not preserve
        try:
            age = max(0.0, current_time - directory.stat().st_mtime)
        except OSError as error:
            _fail(
                AuthorityErrorCode.KEY_ROOT_UNSAFE,
                f"cannot inspect activation key age: {error}",
                activation_uid=activation_uid,
            )
        orphan_expired = (
            not records
            and activation_uid in orphan_scope
            and age >= orphan_grace_seconds
        )
        if not terminal and not orphan_expired:
            continue
        remove_agent_keypair(activation_uid)
        removed.append(activation_uid)
    return tuple(sorted(removed))


def parse_frontmatter(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    try:
        parsed = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    return dict(parsed) if isinstance(parsed, Mapping) else None


def _raw_frontmatter_bytes(raw: bytes) -> bytes | None:
    opening = re.match(rb"\A---[ \t]*\r?\n", raw)
    if opening is None:
        return None
    closing = re.search(
        rb"(?m)^---[ \t]*(?:#[^\r\n]*)?\r?$",
        raw[opening.end() :],
    )
    if closing is None:
        return raw[opening.end() :]
    return raw[opening.end() : opening.end() + closing.start()]


def _raw_frontmatter_declares_agent_key(frontmatter: bytes) -> bool:
    return bool(
        re.search(
            rb"""(?mx)
            ^[ \t]*
            (?:
                agent_public_key
                | "agent_public_key"
                | 'agent_public_key'
            )
            [ \t]*:
            """,
            frontmatter,
        )
    )


def _raw_frontmatter_scalar(frontmatter: bytes, key: str) -> str:
    encoded_key = re.escape(key.encode("ascii"))
    matched = re.search(
        rb"(?m)^[ \t]*(?:"
        + encoded_key
        + rb'|"'
        + encoded_key
        + rb'"|\''
        + encoded_key
        + rb"\')[ \t]*:[ \t]*(?P<value>[^\r\n]*)",
        frontmatter,
    )
    if matched is None:
        return ""
    raw_value = matched.group("value").strip()
    if not raw_value or raw_value[:1] in {b"|", b">"}:
        return ""
    try:
        value_text = raw_value.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    if value_text[:1] in {'"', "'"}:
        try:
            decoded = yaml.safe_load(value_text)
        except yaml.YAMLError:
            return ""
        return str(decoded).strip() if isinstance(decoded, str) else ""
    return value_text.split("#", 1)[0].strip()


def _activation_record_from_bytes(
    raw: bytes,
    path: Path,
    *,
    history_only: bool = False,
    snapshot_lineage: str = "",
    include_non_activation: bool = False,
) -> ActivationRecord | None:
    frontmatter = _raw_frontmatter_bytes(raw)
    fm: dict[str, Any] | None = None
    if frontmatter is not None:
        try:
            parsed = yaml.safe_load(frontmatter.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError):
            parsed = None
        if isinstance(parsed, Mapping):
            fm = dict(parsed)
    if fm is None:
        if (
            frontmatter is not None
            and _raw_frontmatter_declares_agent_key(frontmatter)
        ):
            return ActivationRecord(
                uid=_raw_frontmatter_scalar(frontmatter, "uid") or path.stem,
                agent=_raw_frontmatter_scalar(frontmatter, "agent"),
                generation=normalize_generation_label(
                    _raw_frontmatter_scalar(frontmatter, "generation")
                ),
                status="history-invalid",
                activated_by=_raw_frontmatter_scalar(frontmatter, "activated_by"),
                activated_at=_raw_frontmatter_scalar(frontmatter, "activated_at"),
                # Read raw rather than discarded: an unparseable file can still
                # be COMPARED against the canonical entry, and that comparison
                # is what distinguishes a broken formatting line from a genuine
                # identity claim we cannot account for.
                agent_public_key=_raw_frontmatter_scalar(
                    frontmatter, "agent_public_key"
                )
                or None,
                name=_raw_frontmatter_scalar(frontmatter, "name"),
                agent_class=_raw_frontmatter_scalar(frontmatter, "agent_class"),
                agent_root=_raw_frontmatter_scalar(frontmatter, "agent_root"),
                source_path=path,
                history_invalid=True,
                history_invalid_reason=(
                    "frontmatter is unparseable and syntactically declares "
                    "agent_public_key"
                ),
                agent_key_declared=True,
                history_only=history_only,
                snapshot_lineage=snapshot_lineage,
            )
        return None
    if not fm:
        return None
    activation_type = str(fm.get("type") or "")
    if activation_type != "activation":
        looks_like_activation_snapshot = all(
            str(fm.get(field) or "").strip()
            for field in ("uid", "agent", "generation", "activated_at")
        )
        if not include_non_activation or not looks_like_activation_snapshot:
            return None
    return ActivationRecord(
        uid=str(fm.get("uid") or path.stem),
        agent=str(fm.get("agent") or ""),
        generation=normalize_generation_label(str(fm.get("generation") or "")),
        status=str(fm.get("status") or ""),
        activated_by=str(fm.get("activated_by") or ""),
        activated_at=str(fm.get("activated_at") or ""),
        agent_public_key=(
            None
            if "agent_public_key" not in fm
            else str(fm.get("agent_public_key") or "")
        ),
        name=str(fm.get("name") or ""),
        agent_class=str(fm.get("agent_class") or ""),
        agent_root=str(fm.get("agent_root") or ""),
        source_path=path,
        agent_key_declared="agent_public_key" in fm,
        agent_key_voided=_frontmatter_declares_governed_void(fm),
        immutable_amendments=_frontmatter_immutable_amendments(fm),
        agent_public_key_voided=(
            str(fm.get("agent_public_key_void") or "")
            if _frontmatter_declares_governed_void(fm)
            else None
        ),
        predecessor_activation_uid=(
            None
            if fm.get("predecessor_activation_uid") is None
            else str(fm.get("predecessor_activation_uid")).strip()
        ),
        predecessor_link_declared="predecessor_activation_uid" in fm,
        uid_declared="uid" in fm and bool(str(fm.get("uid") or "").strip()),
        activation_type=activation_type,
        type_declared="type" in fm,
        history_only=history_only,
        snapshot_lineage=snapshot_lineage,
    )


def _activation_record_from_path(
    path: Path,
    *,
    snapshot_lineage: str = "",
    include_non_activation: bool = False,
) -> ActivationRecord | None:
    try:
        raw = path.read_bytes()
    except OSError as error:
        _fail(
            AuthorityErrorCode.CANONICAL_ROOT_INVALID,
            f"canonical/preserved entry is unreadable: {error}",
            path=str(path),
        )
    return _activation_record_from_bytes(
        raw,
        path,
        snapshot_lineage=snapshot_lineage,
        include_non_activation=include_non_activation,
    )


def load_activation_entries(vault_files: Path) -> list[ActivationRecord]:
    records: list[ActivationRecord] = []
    for path in sorted(vault_files.glob("*.md")):
        record = _activation_record_from_path(path)
        if record is not None:
            records.append(record)
    return records


def _preserved_activation_roots(repo: Path) -> tuple[Path, ...]:
    candidates = (
        repo / "recycle",
        repo / "99-recycle",
        repo / "archive",
        repo / "archives",
        repo / "vault" / "archive",
        repo / "vault" / "archives",
    )
    roots: list[Path] = []
    for path in candidates:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            _fail(
                AuthorityErrorCode.CANONICAL_ROOT_INVALID,
                f"preserved activation root is unavailable: {error}",
                path=str(path),
            )
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail(
                AuthorityErrorCode.CANONICAL_ROOT_INVALID,
                "preserved activation root must be a real directory",
                path=str(path),
            )
        roots.append(path)
    return tuple(roots)


def _walk_preserved_activation_paths(root: Path) -> Iterable[Path]:
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory_name in directory_names:
            directory = current_path / directory_name
            if directory.is_symlink():
                _fail(
                    AuthorityErrorCode.CANONICAL_ROOT_INVALID,
                    "symlinked directory cannot hide preserved activation history",
                    path=str(directory),
                )
        for file_name in file_names:
            if not file_name.endswith(".md"):
                continue
            path = current_path / file_name
            if path.is_symlink():
                _fail(
                    AuthorityErrorCode.CANONICAL_ROOT_INVALID,
                    "symlinked preserved activation entry is not authoritative",
                    path=str(path),
                )
            yield path


def _activation_identity(record: ActivationRecord) -> tuple[str, ...]:
    return (
        record.uid,
        record.agent,
        record.generation,
        record.status,
        record.activated_by,
        record.activated_at,
        record.agent_public_key or "",
        record.name,
        record.agent_class,
        record.agent_root,
        record.canonical_current_activation_uid,
        str(record.history_invalid),
        record.history_invalid_reason,
        str(record.agent_key_declared),
        record.predecessor_activation_uid or "",
        str(record.predecessor_link_declared),
        str(record.uid_declared),
        record.activation_type,
        str(record.type_declared),
        str(record.history_only),
        record.snapshot_lineage,
    )


GOVERNED_G2_KEY_MIGRATIONS: Mapping[str, str] = {
    "d37aeeb4": "1a04bf0e",
    "f3b263b3": "1a04bf0e",
}


def _immutable_snapshot_fields(record: ActivationRecord) -> dict[str, Any]:
    return {
        "uid": record.uid,
        "uid_declared": record.uid_declared,
        "type": record.activation_type,
        "type_declared": record.type_declared,
        "agent": record.agent,
        "agent_class": record.agent_class.strip().lower(),
        "generation": record.generation,
        "activated_at": record.activated_at,
        "activated_by": record.activated_by,
        "predecessor_link_declared": record.predecessor_link_declared,
        "predecessor_activation_uid": record.predecessor_activation_uid,
        "agent_root": record.agent_root,
    }


AMENDABLE_IMMUTABLE_FIELDS: frozenset[str] = frozenset({"activated_at"})
"""Immutable fields a GOVERNED amendment may correct.

Deliberately narrow. Identity and lineage position -- uid, type, agent,
generation, agent_root, predecessor_activation_uid -- are never amendable: an
entry that changes those is not correcting a fact, it is becoming a different
entry. `activated_at` records an observation of a clock, and a clock can be
wrong (orpheus O31: the boot shell read a slow machine clock, so both the entry
AND its commit were stamped three days early; the true date was confirmed out of
band from live event timestamps).
"""


def _frontmatter_immutable_amendments(
    fm: Mapping[str, Any],
) -> tuple[tuple[str, str, str], ...]:
    """Declared, reasoned corrections to amendable immutable fields.

    Machine-readable sibling of a prose correction note: `<field>_amended_from`
    plus `<field>_amendment_reason`. Both are required -- a value with no stated
    reason is an undocumented edit, which is exactly what the gate exists to
    catch.
    """

    amendments: list[tuple[str, str, str]] = []
    for field in sorted(AMENDABLE_IMMUTABLE_FIELDS):
        prior = str(fm.get(f"{field}_amended_from") or "").strip()
        reason = str(fm.get(f"{field}_amendment_reason") or "").strip()
        if prior and reason:
            amendments.append((field, prior, reason))
    return tuple(amendments)


def _frontmatter_declares_governed_void(fm: Mapping[str, Any]) -> bool:
    """True when an entry records a GOVERNED key void rather than a bare absence.

    A generation's signing broker can die inside its own activation lifetime
    (activation lifetime exceeds broker lifetime). When the principal authorizes
    an unsigned close, the close path renames `agent_public_key` aside and
    preserves the original material for audit. That is a documented, terminal
    retirement of the key -- NOT drift, and NOT a re-key. It is self-describing
    in the entry, so the chain reads the markers instead of an allowlist.
    """

    return "agent_public_key_void" in fm and (
        str(fm.get("agent_public_key_lost_original_field") or "").strip()
        == "agent_public_key"
    )


def _snapshot_key_state(record: ActivationRecord) -> tuple[str, bytes | str | None]:
    if record.agent_key_voided:
        try:
            voided_point = parse_openssh_public_key(
                record.agent_public_key_voided or ""
            ).key_point
        except AuthorityChainError:
            return "invalid", record.agent_public_key_voided or ""
        return "voided", voided_point
    declared = record.agent_key_declared or record.agent_public_key is not None
    if not declared:
        return "absent", None
    try:
        key_point = parse_openssh_public_key(record.agent_public_key or "").key_point
    except AuthorityChainError:
        return "invalid", record.agent_public_key or ""
    return "present", key_point


_UNPARSEABLE_RECONCILED_REASON = (
    "frontmatter was unparseable in this superseded snapshot, but every "
    "readable identity field and the declared key agree with the canonical "
    "entry; the break is in a non-identity field"
)


def _reconciled_unparseable(
    record: ActivationRecord,
    canonical: ActivationRecord,
) -> ActivationRecord:
    """Clear unparseable poison when the snapshot AGREES with the canonical entry.

    An unparseable key-bearing snapshot is refused because we cannot account for
    what it claims -- it might name a different agent, generation, or key. That
    is right when the snapshot is the only evidence. It conflates two different
    things when a later, parseable revision of the SAME entry exists: an
    unparseable file is not automatically an UNACCOUNTABLE one.

    So compare what is readable rather than assuming the worst. A YAML break in
    a descriptive field (an unquoted timestamp in a prose note, vela-v71
    2026-07-31) leaves every identity field and the key intact and scannable. If
    all of them agree with the canonical entry, the snapshot carries no
    contradictory claim and must not block the lineage -- the poison is retained
    the moment anything readable disagrees, or anything needed is missing.

    Deliberately NOT "a superseded snapshot is exempt": that would excuse a
    snapshot without reading it. This reads it.
    """

    if (
        not record.history_invalid
        or record.history_invalid_code
        != AuthorityErrorCode.ACTIVATION_HISTORY_UNPARSEABLE
        or canonical.history_invalid
        or canonical.uid != record.uid
    ):
        return record

    comparable = (
        ("uid", record.uid, canonical.uid),
        ("agent", record.agent, canonical.agent),
        ("agent_class", record.agent_class, canonical.agent_class),
        ("generation", record.generation, canonical.generation),
        ("agent_root", record.agent_root, canonical.agent_root),
        ("activated_at", record.activated_at, canonical.activated_at),
        ("activated_by", record.activated_by, canonical.activated_by),
        ("agent_public_key", record.agent_public_key, canonical.agent_public_key),
    )
    for _field, snapshot_value, canonical_value in comparable:
        # Anything unreadable is a field we cannot vouch for; keep the poison.
        if not str(snapshot_value or "").strip():
            return record
        if str(snapshot_value).strip() != str(canonical_value or "").strip():
            return record

    return replace(
        record,
        history_invalid=False,
        history_invalid_reason=_UNPARSEABLE_RECONCILED_REASON,
        history_invalid_code=None,
    )


def _snapshot_identity_conflicts(
    snapshots: Sequence[ActivationRecord],
) -> tuple[str, ...]:
    conflicts: list[str] = []
    parseable = [record for record in snapshots if not record.history_invalid]
    if len(parseable) < 2:
        return ()
    live_records = [record for record in parseable if not record.history_only]
    declared_amendments: dict[str, set[str]] = defaultdict(set)
    for record in live_records:
        for field_name, prior_value, _reason in record.immutable_amendments:
            declared_amendments[field_name].add(prior_value)

    baseline = _immutable_snapshot_fields(parseable[0])
    for field_name, expected in baseline.items():
        observed = {
            _immutable_snapshot_fields(record)[field_name]
            for record in parseable
        }
        if len(observed) <= 1:
            continue
        # A governed amendment is a DECLARED correction, not a licence to drift:
        # the field must be amendable at all, the live snapshots must agree on a
        # single current value, and every other value ever observed must be
        # named in an amended_from declaration carrying a reason. An undeclared
        # value anywhere in history still fails.
        live_values = {
            _immutable_snapshot_fields(record)[field_name]
            for record in live_records
        }
        governed_amendment = (
            field_name in AMENDABLE_IMMUTABLE_FIELDS
            and len(live_values) == 1
            and (observed - live_values) <= declared_amendments[field_name]
        )
        if not governed_amendment:
            conflicts.append(
                f"immutable field {field_name} changed across snapshots"
            )

    key_states = [_snapshot_key_state(record) for record in parseable]
    present_points = {
        value for state, value in key_states if state == "present"
    }
    voided_points = {
        value for state, value in key_states if state == "voided"
    }
    invalid_values = {
        value for state, value in key_states if state == "invalid"
    }
    has_absent = any(state == "absent" for state, _value in key_states)
    has_key = any(
        state in {"present", "voided"} for state, _value in key_states
    )
    uids = {record.uid for record in parseable}
    governed_migration = (
        len(uids) == 1 and next(iter(uids)) in GOVERNED_G2_KEY_MIGRATIONS
    )
    if len(present_points) > 1:
        conflicts.append("normalized Ed25519 public key point changed")
    if invalid_values and (
        present_points or voided_points or len(invalid_values) > 1
    ):
        conflicts.append("public key changed to or from malformed key material")
    if voided_points:
        # A governed void RETIRES the key it preserves. It may not swap it for
        # another, and it may not be undone: these two checks are what keep the
        # void from becoming a re-key laundering path.
        if len(present_points | voided_points) > 1:
            conflicts.append(
                "governed key void does not preserve the key it retires"
            )
        if any(
            _snapshot_key_state(record)[0] == "present"
            for record in parseable
            if not record.history_only
        ):
            conflicts.append("key re-declared live after a governed key void")
    if has_absent and has_key and not governed_migration:
        conflicts.append(
            "agent_public_key changed from absent to present without governed "
            "G2 migration evidence"
        )
    return tuple(conflicts)


def _activation_snapshot_components(
    snapshots: Sequence[ActivationRecord],
) -> list[list[ActivationRecord]]:
    parents = list(range(len(snapshots)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = root(left)
        right_root = root(right)
        if left_root != right_root:
            parents[right_root] = left_root

    by_uid: dict[str, int] = {}
    by_lineage: dict[str, int] = {}
    for index, record in enumerate(snapshots):
        if record.uid in by_uid:
            union(index, by_uid[record.uid])
        else:
            by_uid[record.uid] = index
        if record.snapshot_lineage:
            if record.snapshot_lineage in by_lineage:
                union(index, by_lineage[record.snapshot_lineage])
            else:
                by_lineage[record.snapshot_lineage] = index

    components: dict[int, list[ActivationRecord]] = defaultdict(list)
    for index, record in enumerate(snapshots):
        components[root(index)].append(record)
    return list(components.values())


def _consolidate_activation_snapshots(
    snapshots: Sequence[ActivationRecord],
) -> list[ActivationRecord]:
    consolidated: list[ActivationRecord] = []
    for component in _activation_snapshot_components(snapshots):
        if not any(
            record.activation_type == "activation" or record.history_invalid
            for record in component
        ):
            continue
        selected = next(
            (
                record
                for record in component
                if not record.history_only and not record.history_invalid
            ),
            next(
                (record for record in component if not record.history_invalid),
                component[0],
            ),
        )
        consolidated.append(selected)
        consolidated.extend(
            _reconciled_unparseable(record, selected)
            for record in component
            if record.history_invalid and record is not selected
        )
        conflicts = _snapshot_identity_conflicts(component)
        if conflicts:
            affected_agents = tuple(
                sorted({record.agent for record in component if record.agent})
            )
            affected_uids = tuple(
                sorted({record.uid for record in component if record.uid})
            )
            consolidated.append(
                replace(
                    selected,
                    status="history-invalid",
                    history_invalid=True,
                    history_invalid_reason="; ".join(conflicts),
                    history_invalid_code=(
                        AuthorityErrorCode.ACTIVATION_HISTORY_IDENTITY_CONFLICT
                    ),
                    history_affected_agents=affected_agents,
                    history_affected_uids=affected_uids,
                    history_only=True,
                )
            )
    return consolidated


def canonical_vault_files(repo: Path) -> Path:
    """Resolve the only verifier-authoritative entry root for a repository."""

    root = Path(_git_required(repo, "rev-parse", "--show-toplevel")).resolve(strict=True)
    vault = root / "vault"
    files = vault / "files"
    for path, subject in ((vault, "canonical vault"), (files, "canonical vault/files")):
        try:
            metadata = path.lstat()
        except OSError as error:
            _fail(
                AuthorityErrorCode.CANONICAL_ROOT_INVALID,
                f"{subject} is unavailable: {error}",
            )
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail(
                AuthorityErrorCode.CANONICAL_ROOT_INVALID,
                f"{subject} must be a real in-repository directory",
                path=str(path),
            )
    if files.resolve(strict=True).parent != vault.resolve(strict=True):
        _fail(
            AuthorityErrorCode.CANONICAL_ROOT_INVALID,
            "canonical vault/files escaped the repository vault",
        )
    return files


def load_canonical_agent_classes(repo: Path) -> dict[str, str]:
    """Resolve slug→class from unified agent entries and agent-root registries."""

    vault_files = canonical_vault_files(repo)
    repository_root = vault_files.parents[1]
    unified_candidates: list[tuple[str, str, Path]] = []
    root_candidates: list[tuple[str, str, Path]] = []
    unified_root = repository_root / "vault" / "agents"
    if unified_root.exists():
        try:
            metadata = unified_root.lstat()
        except OSError as error:
            _fail(
                AuthorityErrorCode.CANONICAL_ROOT_INVALID,
                f"canonical unified-agent root is unavailable: {error}",
            )
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail(
                AuthorityErrorCode.CANONICAL_ROOT_INVALID,
                "canonical unified-agent root must be a real directory",
            )
        for path in sorted(unified_root.glob("*.md")):
            fm = parse_frontmatter(path)
            if not fm or fm.get("type") != "agent":
                continue
            slug = str(fm.get("agent") or fm.get("slug") or "").strip()
            agent_class = str(fm.get("agent_class") or "").strip().lower()
            if slug and agent_class:
                unified_candidates.append((slug, agent_class, path))
    for path in sorted(vault_files.glob("*.md")):
        fm = parse_frontmatter(path)
        if not fm:
            continue
        slug = str(fm.get("agent_slug") or "").strip()
        agent_class = str(fm.get("agent_class") or "").strip().lower()
        if slug and agent_class:
            root_candidates.append((slug, agent_class, path))

    grouped_roots: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    grouped_unified: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for slug, agent_class, path in root_candidates:
        grouped_roots[slug].append((agent_class, path))
    for slug, agent_class, path in unified_candidates:
        grouped_unified[slug].append((agent_class, path))

    classes: dict[str, str] = {}
    for slug in sorted(set(grouped_roots) | set(grouped_unified)):
        roots = grouped_roots.get(slug, [])
        unified = grouped_unified.get(slug, [])
        root_classes = {agent_class for agent_class, _path in roots}
        unified_classes = {agent_class for agent_class, _path in unified}
        if len(root_classes) > 1 or (not root_classes and len(unified_classes) > 1):
            _fail(
                AuthorityErrorCode.CANONICAL_AGENT_CLASS_CONFLICT,
                "canonical agent entries disagree about one slug's class",
                agent=slug,
                classes=sorted(root_classes | unified_classes),
                sources=[str(path) for _agent_class, path in roots + unified],
            )
        selected = next(iter(root_classes or unified_classes))
        allowed_unified = _activation_compatible_classes(selected)
        if any(agent_class not in allowed_unified for agent_class in unified_classes):
            _fail(
                AuthorityErrorCode.CANONICAL_AGENT_CLASS_CONFLICT,
                "unified and agent-root classes are not activation-compatible",
                agent=slug,
                selected_class=selected,
                unified_classes=sorted(unified_classes),
            )
        classes[slug] = selected
    return classes


def load_canonical_agent_generations(repo: Path) -> dict[str, str]:
    """Resolve current lineage markers from unified status cards and roots."""

    vault_files = canonical_vault_files(repo)
    repository_root = vault_files.parents[1]
    candidates: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    unified_root = repository_root / "vault" / "agents"
    if unified_root.is_dir() and not unified_root.is_symlink():
        for path in sorted(unified_root.glob("*.md")):
            fm = parse_frontmatter(path)
            if not fm or fm.get("type") != "agent":
                continue
            slug = str(fm.get("agent") or fm.get("slug") or "").strip()
            generation = str(fm.get("generation") or "").strip()
            if slug and generation:
                candidates[slug].append((generation, path))
    for path in sorted(vault_files.glob("*.md")):
        fm = parse_frontmatter(path)
        if not fm or fm.get("type") != "project":
            continue
        slug = str(fm.get("agent_slug") or "").strip()
        generation = str(
            fm.get("current_generation")
            or fm.get("current_agent_generation")
            or fm.get("agent_generation")
            or ""
        ).strip()
        if slug and generation:
            candidates[slug].append((generation, path))

    generations: dict[str, str] = {}
    for slug, entries in candidates.items():
        values = {generation for generation, _path in entries}
        if len(values) != 1:
            _fail(
                AuthorityErrorCode.CANONICAL_AGENT_GENERATION_CONFLICT,
                "canonical status-card/root lineage markers disagree",
                agent=slug,
                generations=sorted(values),
                sources=[str(path) for _generation, path in entries],
            )
        generations[slug] = next(iter(values))
    return generations


def load_canonical_current_activation_uids(repo: Path) -> dict[str, str]:
    """Resolve each agent root's durable latest-activation pointer."""

    vault_files = canonical_vault_files(repo)
    repository_root = vault_files.parents[1]
    candidates: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    unified_root = repository_root / "vault" / "agents"
    if unified_root.is_dir() and not unified_root.is_symlink():
        for path in sorted(unified_root.glob("*.md")):
            fm = parse_frontmatter(path)
            if not fm or fm.get("type") != "agent":
                continue
            slug = str(fm.get("agent") or fm.get("slug") or "").strip()
            activation_uid = str(fm.get("current_activation_uid") or "").strip()
            if slug and activation_uid:
                candidates[slug].append((activation_uid, path))
    for path in sorted(vault_files.glob("*.md")):
        fm = parse_frontmatter(path)
        if not fm or fm.get("type") != "project":
            continue
        slug = str(fm.get("agent_slug") or "").strip()
        activation_uid = str(fm.get("current_activation_uid") or "").strip()
        if slug and activation_uid:
            candidates[slug].append((activation_uid, path))

    pointers: dict[str, str] = {}
    for slug, entries in candidates.items():
        values = {activation_uid for activation_uid, _path in entries}
        if len(values) != 1:
            _fail(
                AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                "canonical status-card/root latest-activation pointers disagree",
                agent=slug,
                activation_uids=sorted(values),
                sources=[str(path) for _uid, path in entries],
            )
        pointer = next(iter(values))
        if not re.fullmatch(r"[0-9a-f]{8}", pointer):
            _fail(
                AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                "canonical current activation UID is malformed",
                agent=slug,
                activation_uids=[pointer],
            )
        pointers[slug] = pointer
    return pointers


def _load_git_historical_activation_entries(
    repo: Path,
) -> list[ActivationRecord]:
    """Load unavailable activation identities as negative Git-history evidence."""

    history = _git(
        repo,
        "log",
        "--all",
        "--format=%x1e%H %P",
        "--name-status",
        "--diff-filter=ADM",
        "--",
        "vault/files",
        "recycle",
        "99-recycle",
        "archive",
        "archives",
        "vault/archive",
        "vault/archives",
        timeout=120,
    )
    if history.returncode != 0:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "cannot inspect durable Git activation history",
            stderr=history.stderr.strip(),
        )
    object_requests: list[tuple[str, str, str]] = []
    requested_specs: set[str] = set()
    for section in history.stdout.split("\x1e"):
        lines = [line.strip() for line in section.splitlines() if line.strip()]
        if not lines:
            continue
        ancestry = lines[0].split()
        commit = ancestry[0]
        parents = ancestry[1:]
        if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            continue
        for changed in lines[1:]:
            status_and_path = changed.split("\t", 1)
            if len(status_and_path) != 2:
                continue
            status, relative_path = status_and_path
            if status not in {"A", "M", "D"} or not relative_path.endswith(".md"):
                continue
            if status == "D":
                if not parents:
                    _fail(
                        AuthorityErrorCode.GIT_COMMAND_FAILED,
                        "deleted Git path has no readable parent",
                        commit=commit,
                        path=relative_path,
                    )
                objectish = parents[0]
            else:
                objectish = commit
            spec = f"{objectish}:{relative_path}"
            if spec in requested_specs:
                continue
            requested_specs.add(spec)
            object_requests.append((spec, commit, relative_path))

    snapshots: list[ActivationRecord] = []
    if not object_requests:
        return []
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=str(repo),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        if process.stdin is None or process.stdout is None:
            _fail(
                AuthorityErrorCode.GIT_COMMAND_FAILED,
                "cannot open Git object batch streams",
            )
        for spec, commit, relative_path in object_requests:
            process.stdin.write(spec.encode("utf-8") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().decode("utf-8", errors="replace").strip()
            header_parts = header.split()
            if len(header_parts) != 3 or header_parts[1] != "blob":
                _fail(
                    AuthorityErrorCode.GIT_COMMAND_FAILED,
                    "historical activation path cannot be read from Git",
                    commit=commit,
                    path=relative_path,
                    response=header,
                )
            size = int(header_parts[2])
            raw = process.stdout.read(size)
            if len(raw) != size or process.stdout.read(1) != b"\n":
                _fail(
                    AuthorityErrorCode.GIT_COMMAND_FAILED,
                    "historical activation Git blob is truncated",
                    commit=commit,
                    path=relative_path,
                )
            record = _activation_record_from_bytes(
                raw,
                Path(".git-history") / commit / relative_path,
                history_only=True,
                snapshot_lineage=relative_path,
                include_non_activation=True,
            )
            if record is None:
                continue
            snapshots.append(record)
        process.stdin.close()
        return_code = process.wait(timeout=60)
        if return_code != 0:
            stderr = (
                process.stderr.read().decode("utf-8", errors="replace")
                if process.stderr is not None
                else ""
            )
            _fail(
                AuthorityErrorCode.GIT_COMMAND_FAILED,
                "Git object batch failed while reading activation history",
                stderr=stderr.strip(),
            )
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        process.kill()
        process.wait()
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            f"cannot read durable Git activation history: {error}",
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
    return snapshots


def load_canonical_activation_entries(repo: Path) -> list[ActivationRecord]:
    vault_files = canonical_vault_files(repo)
    repository_root = vault_files.parents[1]
    records: list[ActivationRecord] = []
    for path in sorted(vault_files.glob("*.md")):
        record = _activation_record_from_path(
            path,
            snapshot_lineage=str(path.relative_to(repository_root)),
        )
        if record is not None:
            records.append(record)
    for preserved_root in _preserved_activation_roots(repository_root):
        for path in _walk_preserved_activation_paths(preserved_root):
            record = _activation_record_from_path(
                path,
                snapshot_lineage=str(path.relative_to(repository_root)),
                include_non_activation=True,
            )
            if record is not None:
                records.append(record)
    records.extend(_load_git_historical_activation_entries(repository_root))
    consolidated = _consolidate_activation_snapshots(records)
    canonical_classes = load_canonical_agent_classes(repo)
    canonical_generations = load_canonical_agent_generations(repo)
    canonical_pointers = load_canonical_current_activation_uids(repo)
    class_bound = [
        replace(
            record,
            canonical_agent_class=canonical_classes.get(record.agent, ""),
            canonical_generation=canonical_generations.get(record.agent, ""),
            canonical_current_activation_uid=canonical_pointers.get(
                record.agent,
                "",
            ),
            class_registry_checked=True,
        )
        for record in consolidated
    ]
    return sorted(
        class_bound,
        key=lambda record: (
            record.agent,
            record.activated_at,
            record.generation,
            record.uid,
        ),
    )


EXECUTIVE_GENERATION_CLASSES = frozenset({"executive", "director", "cosmo", "tropo"})
NONTERMINAL_ACTIVATION_STATUSES = frozenset({"active", "paused"})
TERMINAL_ACTIVATION_STATUSES = frozenset({"retired", "stale", "failed"})
VALID_ACTIVATION_STATUSES = (
    NONTERMINAL_ACTIVATION_STATUSES | TERMINAL_ACTIVATION_STATUSES
)
# The only keyed activations that predate predecessor_activation_uid rollout.
# Compatibility is bound to these canonical identities, never to a record flag.
FROZEN_PRE_LINK_ACTIVATION_UIDS = frozenset({"d37aeeb4", "f3b263b3"})
VALID_AGENT_CLASSES = frozenset(
    {
        "executive",
        "director",
        "sa",
        "cosmo",
        "tropo",
        "worker",
        "child-agent",
        "pipeline",
    }
)
KEY_REQUIRED_AGENT_CLASSES = VALID_AGENT_CLASSES - {"pipeline"}
REGISTRATION_REQUIRED_OPAQUE_CLASSES = frozenset({"sa", "pipeline"})

# Two agents carry a role-specific class on their agent root while their
# activations are written under the general class they actually boot as.
# The pairing is ONE fact; it previously lived only inside
# load_canonical_agent_classes, so the resolver tolerated these agents and the
# predecessor gate refused them -- making cosmo and tropo the only two agents
# in the Studio that could never be born (vela-v71, 2026-07-31). Declared once
# here so the two readers cannot disagree again.
ACTIVATION_CLASS_EQUIVALENTS: dict = {
    "cosmo": "executive",
    "tropo": "concierge",
}


def _activation_compatible_classes(agent_class: str) -> set:
    """Every class this one may legitimately appear as on an activation."""

    normalized = str(agent_class or "").strip().lower()
    allowed = {normalized}
    partner = ACTIVATION_CLASS_EQUIVALENTS.get(normalized)
    if partner:
        allowed.add(partner)
    for role, general in ACTIVATION_CLASS_EQUIVALENTS.items():
        if general == normalized:
            allowed.add(role)
    return allowed


def _classes_activation_compatible(left: str, right: str) -> bool:
    """True when two declared classes name the same activation lineage."""

    return str(right or "").strip().lower() in _activation_compatible_classes(left)


def canonical_executive_generation(value: str) -> tuple[str, int] | None:
    """Parse an executive generation label into (PREFIX, number).

    Canonical *form* is an uppercase letter prefix + positive integer with no
    leading zero and no suffix (`A67`, `G98`). Historical substrate sometimes
    stored the same identity in lowercase (`a67`). Letter-case is not identity —
    normalize on read so lineage gates fail closed on real malformations
    (`""`, `A1-resume`, `A01`) without treating a casing typo as poison.
    """

    match = re.fullmatch(r"([A-Za-z]+)([1-9]\d*)", str(value or "").strip())
    if not match:
        return None
    return match.group(1).upper(), int(match.group(2))


# Private alias retained for in-module call sites.
_canonical_executive_generation = canonical_executive_generation


def normalize_generation_label(value: str) -> str:
    """Return the canonical label when parseable; otherwise the original string."""

    parsed = canonical_executive_generation(value)
    if parsed is None:
        return str(value or "")
    return f"{parsed[0]}{parsed[1]}"


def _numeric_generation(value: str) -> tuple[str, int] | None:
    matched = re.fullmatch(r"(.*?)([0-9]+)", value.strip())
    if matched is None:
        return None
    number = int(matched.group(2))
    if number < 1:
        return None
    prefix = matched.group(1)
    if prefix.isalpha():
        prefix = prefix.upper()
    return prefix, number


def _generation_edge_problem(
    successor_generation: str,
    predecessor_generation: str,
) -> str | None:
    successor = _numeric_generation(successor_generation)
    if successor is None:
        return None
    predecessor = _numeric_generation(predecessor_generation)
    if predecessor is None:
        return (
            f"numeric successor generation {successor_generation!r} has "
            f"nonnumeric predecessor generation {predecessor_generation!r}"
        )
    if successor[0] != predecessor[0] or successor[1] != predecessor[1] + 1:
        return (
            f"numeric successor generation {successor_generation!r} requires "
            f"immediate N-1 predecessor, not {predecessor_generation!r}"
        )
    return None


def _is_nonterminal(record: ActivationRecord) -> bool:
    return (
        not record.history_only
        and record.status.strip().lower() in NONTERMINAL_ACTIVATION_STATUSES
    )


def _record_is_key_bearing(record: ActivationRecord) -> bool:
    return record.agent_key_declared or record.agent_public_key is not None


def _record_carries_key_evidence(record: ActivationRecord) -> bool:
    """Is there positive evidence this generation held a provenance key?

    A voided key counts. The close path renames `agent_public_key` aside on a
    governed unsigned close, so the generation stops being key-BEARING while
    remaining proof the lineage WAS keyed.
    """

    return _record_is_key_bearing(record) or record.agent_key_voided


def _walk_terminates_at_void(
    record: ActivationRecord, parsed_keys: Mapping[str, OpenSSHPublicKey]
) -> bool:
    """Does the lineage walk end here, because this generation is a governed void?

    A governed broker-loss void is a generation whose signing key provably
    existed and provably died: the close path renames `agent_public_key` aside
    under principal authorization and leaves the public half behind as
    `agent_public_key_void`, self-describing, in the record. There is no
    signature to verify here and no link to follow past it -- not because we
    excuse a gap, but because the thing that would sign is gone and no later
    generation can bring it back.

    So the walk STOPS, wherever the void appears. Every generation behind it had
    its own anchor adjudicated at its own birth; re-litigating that through a key
    that no longer exists is a demand only fabrication can satisfy.

    This does NOT weaken the two protections it is often confused with, and both
    are enforced elsewhere, independently of the walk:

    * A void may never be the ORIGIN of keying. `_lineage_key_origin` refuses a
      terminus while any unvisited record carries key evidence, and
      `_record_carries_key_evidence` counts a void. Broker loss therefore cannot
      manufacture a pre-G2 anchor.
    * A keyed lineage may never RATCHET BACK to the unkeyed path.
      `_lineage_ever_keyed` counts a void as positive evidence the lineage was
      keyed, so losing a broker cannot buy back the permissive rule.

    Terminating a walk at a void touches neither. The three concerns were welded
    together by one test; Mike's ruling of 2026-08-02 separated them.
    """

    return record.agent_key_voided and record.uid not in parsed_keys


KEY_RETIREMENT_DATE = "2026-08-03"
"""ADR-066 (ff7dd221), accepted by Mike 2026-08-03, verbatim "Option 1"."""


def _minted_after_key_retirement(record: ActivationRecord) -> bool:
    """Was this activation minted by a lifecycle that issues no key?

    ADR-066: "The agent lifecycle mints no cryptographic key material.
    Attribution rests on the immutable activation UID plus event provenance. Any
    future signing capability is separate and optional, and NEVER a dependency
    of birth or of retirement."

    WHY THIS GUARD EXISTS (metis-g101, 2026-08-04). ADR-066 was accepted on
    2026-08-03 and `tropo-activate.py` correctly stopped minting keys. This
    module was never told. Nothing broke, because the boot path still ran the
    OLD mint, which still issued keys -- so a Mike-accepted decision and the code
    that contradicts it sat side by side for a day, invisible.

    The 2026-08-04 cutover pointed birth at the new mint, and the contradiction
    surfaced on the very first agent through it: Orpheus O35 was born clean, and
    the fleet-health walk immediately reported her as her own successor's birth
    blocker for lacking a key she is not supposed to have. She declined to
    hand-patch her own activation record -- correctly; that is the durable-history
    poison class -- and routed it up instead.

    So the requirement is scoped by WHEN the record was minted rather than
    deleted outright. Pre-ADR-066 activations still carry keys and are still
    checked, because for them a missing key means something really was lost.
    Post-ADR-066 activations are not required to carry one, because the lifecycle
    that made them does not issue one.

    A record with an UNPARSEABLE date is treated as key-required -- the
    conservative direction. Claiming exemption is the permissive answer, and an
    unreadable date should never buy it.
    """
    activated = str(getattr(record, "activated_at", "") or "").strip()
    if len(activated) < 10:
        return False
    day = activated[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return False
    return day >= KEY_RETIREMENT_DATE


def _history_only_cause(record: ActivationRecord) -> str:
    """WHY is this record only in Git history? Ask, instead of asserting.

    The message this replaces said "after hard deletion" unconditionally. On
    2026-08-04 it said that about argus A145, whose record had never been
    deleted by anyone: it was written by a Cursor cloud agent on the branch
    `cursor/activate-argus-a145-c85b` and that branch was simply never merged
    to main. The check reported a destructive act that did not happen, named no
    branch, and offered no remedy -- so the reader's next move was to hunt for a
    vandal instead of typing `git merge`.

    That is this session's recurring shape in miniature: an instrument
    reporting success or failure CONFIDENTLY AND WRONGLY. The cause is
    cheap to establish -- the loader already stamps the source commit into
    `source_path` as `.git-history/<commit>/<path>` -- so the honest thing is to
    look it up and, when we cannot, say that instead of guessing.

    Returns a clause completing "... is available only in Git history <clause>".
    """

    commit = ""
    path = record.source_path
    if path is not None:
        parts = Path(path).parts
        if len(parts) >= 2 and parts[0] == ".git-history":
            commit = parts[1]
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit or ""):
        return "and its origin commit could not be identified"

    def _git(*argv: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", *argv],
                cwd=str(_repo_root_for(record)),
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout if done.returncode == 0 else None

    # Reachable from main => the file really was removed from the working tree.
    reachable = _git("merge-base", "--is-ancestor", commit, "main")
    if reachable is not None:
        return (
            f"after deletion from the working tree (last present in {commit[:8]}, "
            "which IS on main; restore with `git checkout "
            f"{commit[:8]} -- <path>`)"
        )

    branches = _git("branch", "-a", "--contains", commit) or ""
    named = [
        line.strip().lstrip("* ").strip()
        for line in branches.splitlines()
        if line.strip() and "->" not in line
    ]
    where = f" on {named[0]}" if named else ""
    return (
        f"because commit {commit[:8]}{where} was never merged into main "
        "-- the record was written on a branch and left there, not deleted. "
        f"Land it with `git checkout {commit[:8]} -- <path>`"
    )


def _repo_root_for(record: ActivationRecord) -> Path:
    """Best-effort repo root for a history-only record's provenance lookup."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    return here.parent


def _lineage_ever_keyed(records: Iterable[ActivationRecord]) -> bool:
    """Has this agent's lineage ever held a provenance key?

    The predecessor-key requirement ratchets on this. A voided key counts: it is
    positive evidence the lineage WAS keyed, so a broker loss can never be used
    to walk a keyed lineage back to the unkeyed legacy path.
    """

    return any(_record_carries_key_evidence(record) for record in records)


def _lineage_key_origin(
    predecessor: ActivationRecord,
    slug_records: Sequence[ActivationRecord],
    visited: set[str],
) -> bool:
    """Is the walk standing on the oldest generation this lineage ever keyed?

    Keys began at G2, so every lineage crosses the unkeyed->keyed transition
    exactly once and the generation immediately before that crossing can never
    bear a key. Its first keyed generation is therefore a terminus alongside
    explicit genesis and the frozen rollout cohort: its adequacy as an anchor
    was adjudicated when it was born, and re-opening that on every later birth
    brings the lineage to a permanent halt.

    The terminus is reachable only when the walk has already accounted for every
    generation of this lineage carrying key evidence -- the candidate itself
    included, since it is never in `visited`. A break in a chain that should be
    fully keyed always strands at least one such generation, the one the unkeyed
    record displaced, so the strict refusal still fires there. A VOIDED key is
    evidence, so broker loss cannot manufacture an origin either.
    """

    return not any(
        _record_carries_key_evidence(record) and record.uid not in visited
        for record in (predecessor, *slug_records)
    )


def _candidate_predecessors(
    lineage: Sequence[ActivationRecord],
) -> list[ActivationRecord]:
    """Which of a lineage's records may be OFFERED as the predecessor?

    Consolidation emits one record per identity plus any superseded Git snapshot
    whose unparseable poison was cleared -- cleared precisely BECAUSE the
    snapshot agreed with the live entry on every identity field and on the key.
    Such a snapshot is the same identity, not a rival one, so counting it as a
    second resolution of its own UID makes an entry ambiguous against itself.

    A UID with no live entry is left exactly as it is: hard deletion still
    resolves to the Git-history record and still refuses at the anchor check.
    """

    live_uids = {record.uid for record in lineage if not record.history_only}
    return [
        record
        for record in lineage
        if not record.history_only or record.uid not in live_uids
    ]


def _activation_key_matches(record: ActivationRecord, key_blob: bytes) -> bool:
    if not _record_is_key_bearing(record):
        return False
    try:
        return (
            parse_openssh_public_key(record.agent_public_key or "").key_point
            == public_key_from_blob(key_blob).key_point
        )
    except AuthorityChainError:
        return False


def _lineage_anchor_problem(
    predecessor: ActivationRecord,
    *,
    successor_uid: str,
    successor_agent: str,
    successor_class: str,
    successor_generation: str,
    successor_activated_at: str,
    successor_canonical_class: str,
    parsed_keys: Mapping[str, OpenSSHPublicKey],
    require_predecessor_key: bool = True,
    allow_voided_anchor: bool = False,
) -> str | None:
    """Validate one predecessor->successor link.

    `require_predecessor_key` is False only on the boot path for a lineage that
    has never been keyed (pre-G2). Every other caller keeps it True, so a keyed
    lineage is never walked back to an unkeyed anchor.

    `allow_voided_anchor` is True wherever a governed broker-loss void may be
    the link's predecessor -- at a pending birth and inside the chain walk
    alike. It drops the key demand and NOTHING else: the void must still be a
    declared activation record, still belong to the same agent, still carry a
    compatible class, still be terminal. See `_walk_terminates_at_void` for why
    a void ends a walk, and for the two protections that are enforced
    independently of it.

    History, because this parameter has been narrowed twice and both narrowings
    bricked a birth. Metis G98 ruled "rescue for BIRTH, never for chain
    CONTINUITY," which G99 implemented as a rescue scoped to the walk's starting
    point. But the walk's start advances every generation while a void stays
    fixed, so G98's void was G99's start (accepted) and G100's interior
    (refused) -- and would have refused every Metis after her. Mike ruled it on
    2026-08-02: "A birth must never be refused by ceremony that protects
    nothing." A void is a link we stop at, not a link we refuse at.
    """

    if predecessor.history_only:
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} is "
            f"available only in Git history {_history_only_cause(predecessor)}"
        )
    if not predecessor.uid_declared or not re.fullmatch(
        r"[0-9a-f]{8}", predecessor.uid
    ):
        return (
            f"activation {successor_uid} predecessor {predecessor.uid!r} "
            "does not declare a canonical activation UID"
        )
    if (
        not predecessor.type_declared
        or predecessor.activation_type != "activation"
    ):
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} "
            "is not a declared activation record"
        )
    if not predecessor.agent or predecessor.agent != successor_agent:
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} belongs "
            f"to {predecessor.agent!r}, not {successor_agent!r}"
        )
    predecessor_class = predecessor.agent_class.strip().lower()
    normalized_successor_class = successor_class.strip().lower()
    if normalized_successor_class not in VALID_AGENT_CLASSES:
        return (
            f"activation {successor_uid} has missing or unknown successor "
            f"agent_class {normalized_successor_class!r}"
        )
    if not predecessor_class or predecessor_class not in VALID_AGENT_CLASSES:
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} has "
            f"missing or unknown agent_class {predecessor_class!r}"
        )
    if not _classes_activation_compatible(
        predecessor_class, normalized_successor_class
    ):
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} class "
            f"{predecessor_class!r} does not match successor class "
            f"{normalized_successor_class!r}; no class transition is governed"
        )
    predecessor_canonical_class = (
        predecessor.canonical_agent_class.strip().lower()
    )
    if (
        predecessor.class_registry_checked
        and predecessor_canonical_class
        and not _classes_activation_compatible(
            predecessor_class, predecessor_canonical_class
        )
    ):
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} class "
            f"{predecessor_class!r} conflicts with canonical class "
            f"{predecessor_canonical_class!r}"
        )
    normalized_successor_canonical = successor_canonical_class.strip().lower()
    if (
        normalized_successor_canonical
        and not _classes_activation_compatible(
            predecessor_class, normalized_successor_canonical
        )
    ):
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} class "
            f"{predecessor_class!r} does not match successor canonical class "
            f"{normalized_successor_canonical!r}"
        )
    if (
        normalized_successor_canonical
        and predecessor_canonical_class
        and predecessor_canonical_class != normalized_successor_canonical
    ):
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} canonical "
            f"class {predecessor_canonical_class!r} does not match successor "
            f"canonical class {normalized_successor_canonical!r}"
        )
    predecessor_status = predecessor.status.strip().lower()
    if predecessor_status not in VALID_ACTIVATION_STATUSES:
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} has "
            f"missing or invalid activation status {predecessor_status!r}"
        )
    if predecessor_status not in TERMINAL_ACTIVATION_STATUSES:
        return (
            f"live activation {successor_uid} predecessor {predecessor.uid} "
            f"must be terminal, not {predecessor_status!r}"
        )
    if not predecessor.generation.strip():
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} has "
            "no generation identity"
        )
    generation_problem = _generation_edge_problem(
        successor_generation,
        predecessor.generation,
    )
    if generation_problem is not None:
        return (
            f"activation {successor_uid} predecessor {predecessor.uid}: "
            f"{generation_problem}"
        )
    if (
        successor_activated_at
        and predecessor.activated_at
        and predecessor.activated_at > successor_activated_at
    ):
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} was "
            "activated after its declared successor"
        )
    if not _record_is_key_bearing(predecessor):
        if not require_predecessor_key:
            return None
        if allow_voided_anchor and predecessor.agent_key_voided:
            # Birth-only rescue. The key material is preserved verbatim at
            # `agent_public_key_void`, the void is principal-authorized, and
            # the markers are self-describing, so this is honest evidence the
            # lineage was keyed. The ratchet is untouched: _lineage_ever_keyed
            # still counts the void, so broker loss can never downgrade this
            # lineage to the unkeyed path. Continuity is unaffected because
            # voided records stay out of `parsed_keys` and the walk never sets
            # this flag.
            return None
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} has no "
            "agent_public_key"
        )
    if predecessor.uid not in parsed_keys:
        return (
            f"activation {successor_uid} predecessor {predecessor.uid} has an "
            "empty or malformed public key"
        )
    return None


def _predecessor_lineage_problem(
    start: ActivationRecord,
    slug_records: Sequence[ActivationRecord],
    parsed_keys: Mapping[str, OpenSSHPublicKey],
    all_records: Sequence[ActivationRecord] | None = None,
) -> tuple[str, tuple[str, ...]] | None:
    """Follow one key lineage to a terminus.

    The termini are: explicit genesis, the frozen rollout cohort, the lineage's
    first keyed generation, and a governed broker-loss void. See
    `_walk_terminates_at_void` for the last one -- it is checked at the top of
    every iteration, so it holds at the walk's start and at any interior link
    alike. A void that terminates the walk is deliberately NOT subject to the
    `skipped_keyed_history` check below: that check enforces continuity across a
    chain we can still traverse, and past a void we cannot.
    """

    by_uid = {
        record.uid: record
        for record in (all_records if all_records is not None else slug_records)
    }
    visited = {start.uid}
    current = start
    while True:
        if _walk_terminates_at_void(current, parsed_keys):
            return None
        # ADR-066 terminates the walk the same way a void does, and for the same
        # reason (metis-g101, 2026-08-04). Past a generation the lifecycle never
        # issued a key to, there is no key evidence to traverse and there never
        # will be -- demanding continuity through it is a demand only fabrication
        # could satisfy. This mirrors the ruling Mike gave on 2026-08-02 for
        # voided keys: a link we STOP at, not a link we refuse at.
        #
        # Without this the release is incomplete in a way the live fleet-health
        # probe does not show: the earlier gates stop reporting the missing key,
        # the walk then reaches this record anyway, and it fails here instead
        # with a confusing "key-bearing activation has an empty or malformed
        # public key" about a record that is not key-bearing at all. Found by
        # test_keyless_lifecycle_adr066.py, not by the probe going green.
        if not _record_carries_key_evidence(current) and (
            _minted_after_key_retirement(current)
        ):
            return None
        current_key = parsed_keys.get(current.uid)
        if current_key is None:
            return (
                f"key-bearing activation {current.uid} has an empty or malformed public key",
                tuple(sorted(visited)),
            )
        if (
            current.uid in FROZEN_PRE_LINK_ACTIVATION_UIDS
            and not current.predecessor_link_declared
        ):
            break
        if not current.predecessor_link_declared:
            return (
                f"key-bearing activation {current.uid} has no predecessor_activation_uid field",
                tuple(sorted(visited)),
            )
        predecessor_uid = current.predecessor_activation_uid
        if predecessor_uid is None:
            unvisited_history = [
                record.uid for record in slug_records if record.uid not in visited
            ]
            if unvisited_history:
                return (
                    (
                        f"activation {current.uid} declares genesis despite established "
                        f"history {sorted(unvisited_history)}"
                    ),
                    tuple(sorted(visited | set(unvisited_history))),
                )
            numeric_generation = _numeric_generation(current.generation)
            if numeric_generation is not None and numeric_generation[1] != 1:
                return (
                    (
                        f"activation {current.uid} declares first-ever genesis at "
                        f"numeric generation {current.generation!r}, not generation one"
                    ),
                    tuple(sorted(visited)),
                )
            break
        if not re.fullmatch(r"[0-9a-f]{8}", predecessor_uid):
            return (
                (
                    f"activation {current.uid} declares malformed predecessor "
                    f"UID {predecessor_uid!r}"
                ),
                tuple(sorted(visited)),
            )
        if predecessor_uid in visited:
            return (
                f"activation predecessor chain cycles at {predecessor_uid}",
                tuple(sorted(visited)),
            )
        predecessor = by_uid.get(predecessor_uid)
        if predecessor is None:
            return (
                (
                    f"activation {current.uid} references unavailable predecessor "
                    f"{predecessor_uid}"
                ),
                tuple(sorted(visited | {predecessor_uid})),
            )
        key_origin = _lineage_key_origin(predecessor, slug_records, visited)
        anchor_problem = _lineage_anchor_problem(
            predecessor,
            successor_uid=current.uid,
            successor_agent=current.agent,
            successor_class=current.agent_class,
            successor_generation=current.generation,
            successor_activated_at=current.activated_at,
            successor_canonical_class=current.canonical_agent_class,
            parsed_keys=parsed_keys,
            require_predecessor_key=not key_origin,
            allow_voided_anchor=True,
        )
        if anchor_problem is not None:
            return (
                anchor_problem,
                tuple(sorted(visited | {predecessor_uid})),
            )
        if _walk_terminates_at_void(predecessor, parsed_keys):
            # Every other property of this link was just checked -- same agent,
            # compatible class, declared activation record, terminal. Only the
            # key demand is dropped, onto a generation whose key provably died.
            # Stepping ONTO it and re-testing at the loop top would be
            # equivalent; terminating here keeps the key-reuse comparison below
            # from dereferencing a key that no longer exists.
            visited.add(predecessor_uid)
            return None
        if key_origin:
            # Every other property of this last link was just checked; only the
            # key demand is dropped, and only onto a pre-G2 generation that never
            # held the private half and so could satisfy it only by fabrication.
            break
        predecessor_key = parsed_keys[predecessor_uid]
        if predecessor_key.key_point == current_key.key_point:
            return (
                (
                    f"activation {current.uid} reuses predecessor {predecessor_uid}'s "
                    "public key"
                ),
                tuple(sorted(visited | {predecessor_uid})),
            )
        visited.add(predecessor_uid)
        current = predecessor

    skipped_keyed_history = [
        record.uid
        for record in slug_records
        if _record_is_key_bearing(record) and record.uid not in visited
    ]
    if skipped_keyed_history:
        return (
            (
                f"activation {start.uid} predecessor chain skips key-bearing history "
                f"{sorted(skipped_keyed_history)}"
            ),
            tuple(sorted(visited | set(skipped_keyed_history))),
        )
    return None


def derive_new_activation_predecessor(
    records: Sequence[ActivationRecord],
    agent: str,
    agent_class: str,
    generation: str,
    expected_predecessor_uid: str | None = None,
) -> str | None:
    """Resolve and validate the predecessor before a new key is minted."""

    poison = [
        record
        for record in records
        if record.history_invalid
        and (
            not record.agent
            or record.agent == agent
            or agent in record.history_affected_agents
        )
    ]
    if poison:
        poison_code = (
            AuthorityErrorCode.ACTIVATION_HISTORY_IDENTITY_CONFLICT
            if any(
                record.history_invalid_code
                == AuthorityErrorCode.ACTIVATION_HISTORY_IDENTITY_CONFLICT
                for record in poison
            )
            else AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID
        )
        _fail(
            poison_code,
            "durable activation-history poison prevents predecessor derivation",
            agent=agent,
            activation_uids=sorted(
                {
                    record.uid
                    for record in poison
                }
                | {
                    uid
                    for record in poison
                    for uid in record.history_affected_uids
                }
            ),
        )
    matching = [
        record
        for record in records
        if not record.history_invalid and record.agent == agent
    ]
    if not matching:
        if expected_predecessor_uid:
            _fail(
                AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                (
                    f"canonical current activation {expected_predecessor_uid} for "
                    f"{agent!r} is unavailable from canonical/recycled/archive history"
                ),
                agent=agent,
                activation_uids=[expected_predecessor_uid],
            )
        return None
    candidates = _candidate_predecessors(matching)
    if expected_predecessor_uid:
        if not re.fullmatch(r"[0-9a-f]{8}", expected_predecessor_uid):
            _fail(
                AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                "canonical current activation UID is malformed",
                agent=agent,
                activation_uids=[expected_predecessor_uid],
            )
        expected = [
            record for record in candidates if record.uid == expected_predecessor_uid
        ]
        if len(expected) != 1:
            _fail(
                AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                (
                    f"canonical current activation {expected_predecessor_uid} for "
                    f"{agent!r} does not resolve exactly once"
                ),
                agent=agent,
                activation_uids=[expected_predecessor_uid],
                matches=len(expected),
            )
        predecessor = expected[0]
    else:
        predecessor = max(
            candidates,
            key=lambda record: (
                record.activated_at,
                record.generation,
                record.uid,
            ),
        )
    lineage_keyed = _lineage_ever_keyed(matching)
    if not _record_carries_key_evidence(predecessor):
        # Keys began at G2. A generation that ended before then cannot have one,
        # and demanding it would either brick the lineage forever or force a
        # fabricated key onto a generation that never held the private half.
        # So the requirement RATCHETS off the substrate: strict the moment this
        # lineage has ever been keyed, and permanently strict thereafter. A
        # VOIDED key still counts as proof the lineage was keyed, so the
        # broker-loss path cannot be used to walk a lineage back to unkeyed.
        #
        # Tests key EVIDENCE, not key BEARING: voiding removes
        # `agent_public_key`, so a voided predecessor is not key-bearing while
        # _lineage_ever_keyed() counts it as keyed by design. Testing bearing
        # here made both conditions true on exactly the voided case, so a
        # governed void deterministically bricked the successor it existed to
        # rescue (metis-g99 2026-08-01, second broker loss in five days).
        # ...and the ratchet RELEASES at ADR-066 (metis-g101, 2026-08-04).
        #
        # The ratchet's purpose was to stop a broker loss buying back the
        # permissive unkeyed rule. That purpose is spent: ADR-066 retired key
        # material from the lifecycle entirely, so there is no private half to
        # lose and nothing to buy back. Left as it stood, the ratchet does the
        # opposite of its intent — every lineage in the fleet has been keyed at
        # some point, so the FIRST keyless generation each one mints becomes a
        # permanent blocker on its own successor.
        #
        # That is not hypothetical. Orpheus O35 was the first agent born through
        # the new mint, four hours after the cutover: born clean, zero findings,
        # and instantly reported as her own successor's birth blocker for
        # lacking a key ADR-066 says she must not be issued. She declined to
        # hand-patch her activation record and routed it up instead, which is
        # exactly right — the record is durable history.
        #
        # Scoped by mint date, not deleted: a PRE-ADR-066 predecessor with no key
        # still fails here, because for those generations a missing key means one
        # really was lost, and that is the case the ratchet was built for.
        if _lineage_ever_keyed(matching) and not _minted_after_key_retirement(
            predecessor
        ):
            _fail(
                AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                (
                    f"established predecessor {predecessor.uid} has no "
                    "agent_public_key"
                ),
                agent=agent,
                activation_uids=[predecessor.uid],
            )
    parsed_keys: dict[str, OpenSSHPublicKey] = {}
    for record in records:
        if not _record_is_key_bearing(record):
            continue
        try:
            if record.agent_public_key is not None:
                parsed_keys[record.uid] = parse_openssh_public_key(
                    record.agent_public_key
                )
        except AuthorityChainError:
            pass
    anchor_problem = _lineage_anchor_problem(
        predecessor,
        successor_uid="<pending>",
        successor_agent=agent,
        successor_class=agent_class,
        successor_generation=generation,
        successor_activated_at="",
        successor_canonical_class=predecessor.canonical_agent_class,
        parsed_keys=parsed_keys,
        # ADR-066 (metis-g101, 2026-08-04): the THIRD key gate on this path, and
        # the one a fleet-health probe does not necessarily reach — real lineages
        # can satisfy the anchor through an older keyed record, so this fires
        # only for some shapes. It was found by a synthetic two-record lineage in
        # test_keyless_lifecycle_adr066.py, not by the live probe going green.
        # A keyless predecessor minted after key retirement cannot be required to
        # produce a key it was never issued.
        require_predecessor_key=(
            lineage_keyed and not _minted_after_key_retirement(predecessor)
        ),
        allow_voided_anchor=True,
    )
    if anchor_problem is not None:
        _fail(
            AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
            anchor_problem,
            agent=agent,
            activation_uids=[predecessor.uid],
        )
    if not lineage_keyed:
        # Pre-G2 lineage: there is no key chain to walk yet. This boot mints the
        # first key, and every later boot of this agent is strict.
        return predecessor.uid
    problem = _predecessor_lineage_problem(
        predecessor,
        matching,
        parsed_keys,
        records,
    )
    if problem is not None:
        message, activation_uids = problem
        _fail(
            AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
            message,
            agent=agent,
            activation_uids=list(activation_uids),
        )
    return predecessor.uid


def analyze_activations(records: Sequence[ActivationRecord]) -> ActivationAnalysis:
    """Evaluate ADR-016/028 key bindings and both slug/key collapse directions."""

    invalid: dict[str, list[Finding]] = defaultdict(list)
    findings: list[Finding] = []
    by_slug: dict[str, list[ActivationRecord]] = defaultdict(list)
    by_key: dict[bytes, list[ActivationRecord]] = defaultdict(list)
    parsed_keys: dict[str, OpenSSHPublicKey] = {}
    poisoned_history: list[ActivationRecord] = []

    for record in records:
        if record.history_invalid:
            poisoned_history.append(record)
            continue
        actual_class = record.agent_class.strip().lower()
        expected_class = record.canonical_agent_class.strip().lower()
        key_bearing = _record_is_key_bearing(record)
        identity_error = None
        if key_bearing and (
            not record.agent or not actual_class or not record.generation
        ):
            identity_error = (
                "key-bearing activation must declare agent, agent_class, and generation"
            )
        elif actual_class and actual_class not in VALID_AGENT_CLASSES:
            identity_error = f"activation declares unknown agent class {actual_class!r}"
        if identity_error:
            finding = Finding(
                AuthorityErrorCode.ACTIVATION_GENERATION_INVALID,
                identity_error,
                (record.uid,),
            )
            findings.append(finding)
            if _is_nonterminal(record):
                invalid[record.uid].append(finding)
        if record.class_registry_checked:
            if expected_class and actual_class != expected_class:
                finding = Finding(
                    AuthorityErrorCode.ACTIVATION_CLASS_MISMATCH,
                    (
                        f"activation class {actual_class!r} does not match canonical "
                        f"class {expected_class!r} for {record.agent!r}"
                    ),
                    (record.uid,),
                )
                findings.append(finding)
                if _is_nonterminal(record):
                    invalid[record.uid].append(finding)
            elif (
                actual_class in REGISTRATION_REQUIRED_OPAQUE_CLASSES
                and not expected_class
            ):
                finding = Finding(
                    AuthorityErrorCode.ACTIVATION_CLASS_UNREGISTERED,
                    (
                        f"{actual_class}-class activation slug {record.agent!r} has "
                        "no canonical class registration"
                    ),
                    (record.uid,),
                )
                findings.append(finding)
                if _is_nonterminal(record):
                    invalid[record.uid].append(finding)
        if (
            actual_class in KEY_REQUIRED_AGENT_CLASSES
            and not key_bearing
            and not _minted_after_key_retirement(record)
        ):
            finding = Finding(
                AuthorityErrorCode.ACTIVATION_KEY_MISSING,
                "key-required activation has no agent_public_key",
                (record.uid,),
            )
            findings.append(finding)
            if _is_nonterminal(record):
                invalid[record.uid].append(finding)
        if record.agent:
            by_slug[record.agent].append(record)
        if key_bearing:
            try:
                key = parse_openssh_public_key(record.agent_public_key or "")
            except AuthorityChainError as error:
                finding = Finding(
                    AuthorityErrorCode.PUBLIC_KEY_INVALID,
                    f"activation {record.uid} public key is invalid: {error.message}",
                    (record.uid,),
                )
                findings.append(finding)
                if _is_nonterminal(record):
                    invalid[record.uid].append(finding)
            else:
                parsed_keys[record.uid] = key
                by_key[key.key_point].append(record)

    nonterminal_records = [
        record
        for record in records
        if not record.history_invalid and _is_nonterminal(record)
    ]
    for poison in poisoned_history:
        affected_agents = set(poison.history_affected_agents)
        if poison.agent:
            affected_agents.add(poison.agent)
        matching_lineage = [
            record
            for record in nonterminal_records
            if record.agent in affected_agents
        ]
        affected = matching_lineage or nonterminal_records
        affected_uids = tuple(
            sorted(
                {
                    poison.uid,
                    *poison.history_affected_uids,
                    *(record.uid for record in affected),
                }
            )
        )
        finding = Finding(
            poison.history_invalid_code,
            (
                f"durable activation history for {poison.uid} has "
                f"{poison.history_invalid_reason}; "
                + (
                    f"no nonterminal holder for {sorted(affected_agents)!r} can prove lineage"
                    if matching_lineage
                    else "its lineage is unreadable, so no nonterminal holder can prove lineage"
                )
            ),
            affected_uids,
        )
        findings.append(finding)
        invalid[poison.uid].append(finding)
        for record in affected:
            invalid[record.uid].append(finding)

    for slug, slug_records in sorted(by_slug.items()):
        live = [record for record in slug_records if _is_nonterminal(record)]
        if len(live) > 1:
            live_keys = {
                parsed_keys[record.uid].key_point
                for record in live
                if record.uid in parsed_keys
            }
            code = (
                AuthorityErrorCode.TWO_KEYS_ONE_SLUG
                if len(live_keys) > 1
                else AuthorityErrorCode.ACTIVATION_AMBIGUOUS
            )
            uids = tuple(sorted(record.uid for record in live))
            finding = Finding(
                code,
                (
                    f"ADR-016 collision: {slug} has {len(live)} simultaneous "
                    "nonterminal activations; none is gate-valid"
                ),
                uids,
            )
            findings.append(finding)
            for record in live:
                invalid[record.uid].append(finding)

        for record in live:
            if not _record_is_key_bearing(record):
                continue
            latest_pointer = record.canonical_current_activation_uid
            allowed_pointers = {
                record.uid,
                *(
                    (record.predecessor_activation_uid,)
                    if record.predecessor_activation_uid
                    else ()
                ),
            }
            if latest_pointer and latest_pointer not in allowed_pointers:
                finding = Finding(
                    AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                    (
                        f"nonterminal activation {record.uid} does not continue "
                        f"canonical current_activation_uid {latest_pointer}"
                    ),
                    tuple(sorted({record.uid, latest_pointer})),
                )
                findings.append(finding)
                invalid[record.uid].append(finding)
            problem = _predecessor_lineage_problem(
                record,
                slug_records,
                parsed_keys,
                records,
            )
            if problem is None:
                continue
            message, activation_uids = problem
            finding = Finding(
                AuthorityErrorCode.ACTIVATION_PREDECESSOR_INVALID,
                message,
                activation_uids,
            )
            findings.append(finding)
            invalid[record.uid].append(finding)

        malformed_opaque_key_history = [
            record
            for record in slug_records
            if _record_is_key_bearing(record)
            and record.agent_class.strip().lower()
            not in EXECUTIVE_GENERATION_CLASSES
            and not record.generation
        ]
        if malformed_opaque_key_history and live:
            malformed_uids = tuple(
                sorted(record.uid for record in malformed_opaque_key_history)
            )
            affected_uids = tuple(
                sorted({record.uid for record in live} | set(malformed_uids))
            )
            finding = Finding(
                AuthorityErrorCode.ACTIVATION_LINEAGE_INCOMPLETE,
                (
                    f"key-bearing opaque-class history for {slug!r} has missing "
                    f"generation on {list(malformed_uids)}; no nonterminal holder "
                    "can prove identity lineage"
                ),
                affected_uids,
            )
            findings.append(finding)
            for record in live:
                invalid[record.uid].append(finding)

        executive_records = [
            record
            for record in slug_records
            if record.agent_class.strip().lower() in EXECUTIVE_GENERATION_CLASSES
        ]
        parsed_by_uid: dict[str, tuple[str, int]] = {}
        by_generation: dict[tuple[str, int], list[ActivationRecord]] = defaultdict(list)
        malformed_key_history: list[ActivationRecord] = []
        for record in executive_records:
            parsed = _canonical_executive_generation(record.generation)
            if parsed is None:
                finding = Finding(
                    AuthorityErrorCode.ACTIVATION_GENERATION_INVALID,
                    (
                        f"executive-class activation {record.uid} has noncanonical "
                        f"generation {record.generation!r}"
                    ),
                    (record.uid,),
                )
                findings.append(finding)
                if _is_nonterminal(record):
                    invalid[record.uid].append(finding)
                if _record_is_key_bearing(record):
                    malformed_key_history.append(record)
                continue
            parsed_by_uid[record.uid] = parsed
            by_generation[parsed].append(record)

        if malformed_key_history and live:
            malformed_uids = tuple(
                sorted(record.uid for record in malformed_key_history)
            )
            affected_uids = tuple(
                sorted({record.uid for record in live} | set(malformed_uids))
            )
            finding = Finding(
                AuthorityErrorCode.ACTIVATION_LINEAGE_INCOMPLETE,
                (
                    f"key-bearing history for {slug!r} has unparseable or missing "
                    f"generation on {list(malformed_uids)}; no nonterminal holder "
                    "can prove lineage"
                ),
                affected_uids,
            )
            findings.append(finding)
            for record in live:
                invalid[record.uid].append(finding)

        for generation, generation_records in by_generation.items():
            if len({record.uid for record in generation_records}) < 2:
                continue
            uids = tuple(sorted(record.uid for record in generation_records))
            finding = Finding(
                AuthorityErrorCode.ACTIVATION_GENERATION_INVALID,
                (
                    f"agent {slug} has more than one activation identity for "
                    f"generation {generation[0]}{generation[1]}"
                ),
                uids,
            )
            findings.append(finding)
            for record in generation_records:
                if _is_nonterminal(record):
                    invalid[record.uid].append(finding)

        available_generations = set(by_generation)
        canonical_markers = {
            record.canonical_generation
            for record in slug_records
            if record.canonical_generation
        }
        canonical_generation = (
            _canonical_executive_generation(next(iter(canonical_markers)))
            if len(canonical_markers) == 1
            else None
        )
        if canonical_markers and canonical_generation is None:
            uids = tuple(sorted(record.uid for record in live))
            finding = Finding(
                AuthorityErrorCode.ACTIVATION_GENERATION_INVALID,
                (
                    f"canonical status-card/root generation for {slug!r} is "
                    f"missing, conflicting, or noncanonical: {sorted(canonical_markers)}"
                ),
                uids,
            )
            findings.append(finding)
            for record in live:
                invalid[record.uid].append(finding)
        elif canonical_generation is not None:
            canonical_prefix, canonical_number = canonical_generation
            for record in live:
                parsed = parsed_by_uid.get(record.uid)
                if parsed is None or parsed in {
                    canonical_generation,
                    (canonical_prefix, canonical_number + 1),
                }:
                    continue
                finding = Finding(
                    AuthorityErrorCode.ACTIVATION_LINEAGE_INCOMPLETE,
                    (
                        f"nonterminal activation {record.uid} generation "
                        f"{record.generation!r} resets or skips canonical lineage "
                        f"from {canonical_prefix}{canonical_number}"
                    ),
                    (record.uid,),
                )
                findings.append(finding)
                invalid[record.uid].append(finding)
        for record in live:
            parsed = parsed_by_uid.get(record.uid)
            if parsed is None:
                continue
            prefix, number = parsed
            if number == 1 or (prefix, number - 1) in available_generations:
                continue
            finding = Finding(
                AuthorityErrorCode.ACTIVATION_LINEAGE_INCOMPLETE,
                (
                    f"nonterminal activation {record.uid} expects preserved predecessor "
                    f"{prefix}{number - 1}, but no canonical/recycled/archive identity exists"
                ),
                (record.uid,),
            )
            findings.append(finding)
            invalid[record.uid].append(finding)

    for key_blob, key_records in by_key.items():
        identities = {record.uid: record for record in key_records}
        identity_records = list(identities.values())
        if len(identity_records) > 1:
            uids = tuple(sorted(identities))
            finding = Finding(
                AuthorityErrorCode.ACTIVATION_KEY_REUSE,
                (
                    "one public key is bound to more than one activation identity; "
                    "every nonterminal holder is invalid regardless of generation labels"
                ),
                uids,
            )
            findings.append(finding)
            for record in identity_records:
                if _is_nonterminal(record):
                    invalid[record.uid].append(finding)

        slugs = sorted({record.agent for record in identity_records})
        if len(slugs) > 1:
            uids = tuple(sorted(identities))
            finding = Finding(
                AuthorityErrorCode.ONE_KEY_MANY_SLUGS,
                (
                    "one signing key resolves to more than one agent slug: "
                    f"{slugs}"
                ),
                uids,
            )
            findings.append(finding)
            for record in identity_records:
                if _is_nonterminal(record):
                    invalid[record.uid].append(finding)

    return ActivationAnalysis(
        records=tuple(records),
        invalid_reasons={uid: tuple(items) for uid, items in invalid.items()},
        findings=tuple(findings),
    )


def canonical_git_identity(record: ActivationRecord) -> tuple[str, str]:
    handle = record.name or f"{record.agent}-{record.generation.lower()}"
    return handle, f"{handle}@agents.tropo.local"


def derive_allowed_signers(
    records: Sequence[ActivationRecord],
) -> str:
    """Render active, gate-valid activation keys in memory.

    No caller-facing file is produced.  Retiring an activation removes its key
    from the next rendering with no hand-maintained artifact.
    """

    analysis = analyze_activations(records)
    lines: list[str] = []
    for record in sorted(records, key=lambda item: (item.agent, item.generation, item.uid)):
        if (
            record.status != "active"
            or not record.agent_public_key
            or not analysis.is_gate_valid(record.uid)
        ):
            continue
        _, email = canonical_git_identity(record)
        lines.append(f"{email} {record.public_key.canonical}")
    return "\n".join(lines) + ("\n" if lines else "")


def derive_canonical_allowed_signers(repo: Path) -> str:
    """Render signer material from a fresh canonical-root read."""

    with authority_state_lock(repo):
        return derive_allowed_signers(load_canonical_activation_entries(repo))


def _git(
    repo: Path,
    *args: str,
    timeout: int = 60,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=dict(env) if env is not None else None,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        _fail(AuthorityErrorCode.GIT_COMMAND_FAILED, f"git invocation failed: {error}")


def _git_required(
    repo: Path,
    *args: str,
    timeout: int = 60,
    env: Mapping[str, str] | None = None,
) -> str:
    result = _git(repo, *args, timeout=timeout, env=env)
    if result.returncode != 0:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            f"git {' '.join(args)} failed",
            stderr=(result.stderr or result.stdout).strip(),
        )
    return result.stdout.strip()


def _git_common_dir(repo: Path) -> Path:
    common = _git_required(repo, "rev-parse", "--git-common-dir")
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = repo / common_path
    return common_path.resolve()


def _repo_config_path(repo: Path) -> Path:
    return _git_common_dir(repo) / "config"


def _config_bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


@contextlib.contextmanager
def _commit_lock(repo: Path):
    lock_path = _git_common_dir(repo) / "tropo-authority-signing.lock"
    handle = lock_path.open("a+b")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


@contextlib.contextmanager
def authority_state_lock(repo: Path, *, exclusive: bool = False):
    """Lock canonical activation/principal state across load and verification.

    The lock file intentionally persists inside the Git common directory.
    Unlinking an advisory lock after release creates an inode-replacement race
    where a third process can bypass a waiter holding the old inode.
    """

    lock_path = _git_common_dir(repo) / "tropo-authority-state.lock"
    handle = lock_path.open("a+b")
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    try:
        fcntl.flock(handle.fileno(), operation)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


@contextlib.contextmanager
def activation_state_lock(
    repo: Path,
    activation_uid: str,
    *,
    exclusive: bool = False,
):
    """Coordinate one activation's verification and lifecycle transition."""

    _validate_activation_uid(activation_uid)
    lock_path = _git_common_dir(repo) / f"tropo-activation-{activation_uid}.lock"
    handle = lock_path.open("a+b")
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    try:
        fcntl.flock(handle.fileno(), operation)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _decode_signature_armor(armor: str) -> tuple[bytes, str, str]:
    begin = "-----BEGIN SSH SIGNATURE-----"
    end = "-----END SSH SIGNATURE-----"
    if begin not in armor or end not in armor:
        signature_kind = (
            "openpgp"
            if "-----BEGIN PGP SIGNATURE-----" in armor
            else "unsupported"
        )
        _fail(
            AuthorityErrorCode.SIGNATURE_UNSUPPORTED,
            f"commit carries a non-SSHSIG signature ({signature_kind})",
            signature_kind=signature_kind,
        )
    encoded = "".join(
        line.strip()
        for line in armor.splitlines()
        if line.strip() and line.strip() not in {begin, end}
    )
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        _fail(AuthorityErrorCode.SIGNATURE_MALFORMED, "SSHSIG armor is not strict base64")
    if not raw.startswith(b"SSHSIG") or len(raw) < 10:
        _fail(AuthorityErrorCode.SIGNATURE_MALFORMED, "signature is not SSHSIG v1")
    version = struct.unpack(">I", raw[6:10])[0]
    if version != 1:
        _fail(
            AuthorityErrorCode.SIGNATURE_MALFORMED,
            f"unsupported SSHSIG version {version}",
        )
    key_blob, offset = _read_ssh_string(raw, 10, "SSHSIG public key")
    namespace, offset = _read_ssh_string(raw, offset, "SSHSIG namespace")
    _, offset = _read_ssh_string(raw, offset, "SSHSIG reserved field")
    hash_algorithm, offset = _read_ssh_string(raw, offset, "SSHSIG hash algorithm")
    _, offset = _read_ssh_string(raw, offset, "SSHSIG signature")
    if offset != len(raw):
        _fail(AuthorityErrorCode.SIGNATURE_MALFORMED, "SSHSIG has trailing bytes")
    try:
        return key_blob, namespace.decode("ascii"), hash_algorithm.decode("ascii")
    except UnicodeDecodeError:
        _fail(
            AuthorityErrorCode.SIGNATURE_MALFORMED,
            "SSHSIG namespace or hash algorithm is not ASCII",
        )


def extract_commit_signature(repo: Path, commit: str = "HEAD") -> CommitSignature:
    """Decode the exact SSHSIG key blob from a commit object."""

    result = subprocess.run(
        ["git", "cat-file", "commit", commit],
        cwd=str(repo),
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            f"cannot read commit {commit}",
            stderr=result.stderr.decode(errors="replace").strip(),
        )
    header = result.stdout.split(b"\n\n", 1)[0]
    lines = header.splitlines()
    armor_lines: list[bytes] = []
    for index, line in enumerate(lines):
        if line.startswith(b"gpgsig "):
            armor_lines.append(line[len(b"gpgsig ") :])
            cursor = index + 1
            while cursor < len(lines) and lines[cursor].startswith(b" "):
                armor_lines.append(lines[cursor][1:])
                cursor += 1
            break
    if not armor_lines:
        _fail(
            AuthorityErrorCode.SIGNATURE_MISSING,
            f"commit {commit} carries no gpgsig SSH signature",
        )
    try:
        armor = b"\n".join(armor_lines).decode("ascii")
    except UnicodeDecodeError:
        _fail(AuthorityErrorCode.SIGNATURE_MALFORMED, "SSH signature armor is not ASCII")
    key_blob, namespace, hash_algorithm = _decode_signature_armor(armor)
    key = public_key_from_blob(key_blob)
    identity = _git_required(repo, "show", "-s", "--format=%an%x00%ae", commit)
    if "\x00" not in identity:
        _fail(AuthorityErrorCode.GIT_COMMAND_FAILED, "could not resolve commit author identity")
    author_name, author_email = identity.split("\x00", 1)
    resolved = _git_required(repo, "rev-parse", commit)
    return CommitSignature(
        commit=resolved,
        public_key=key.canonical,
        key_blob=key.blob,
        key_fingerprint=key.fingerprint,
        author_name=author_name,
        author_email=author_email,
        namespace=namespace,
        hash_algorithm=hash_algorithm,
    )


def _verify_commit_with_signers(repo: Path, commit: str, signers: str) -> None:
    if not signers:
        _fail(
            AuthorityErrorCode.SIGNATURE_INVALID,
            "verification has no freshly-derived allowed signers",
        )
    with tempfile.TemporaryDirectory(prefix="tropo-allowed-signers-") as temporary:
        allowed = Path(temporary) / "allowed_signers"
        allowed.write_text(signers, encoding="utf-8")
        result = _git(
            repo,
            "-c",
            f"gpg.ssh.allowedSignersFile={allowed}",
            "verify-commit",
            commit,
        )
    if result.returncode != 0:
        _fail(
            AuthorityErrorCode.SIGNATURE_INVALID,
            f"SSH signature on commit {commit} did not verify",
            stderr=(result.stderr or result.stdout).strip(),
        )


def _normalize_explicit_paths(
    repo: Path,
    paths: Sequence[str | Path],
) -> list[str]:
    root = Path(_git_required(repo, "rev-parse", "--show-toplevel")).resolve(strict=True)
    normalized: list[str] = []
    for raw in paths:
        candidate = Path(raw)
        absolute = candidate if candidate.is_absolute() else root / candidate
        resolved = absolute.resolve(strict=False)
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            _fail(
                AuthorityErrorCode.GIT_COMMAND_FAILED,
                "explicit staging path escapes the repository",
                path=str(raw),
            )
        if relative == Path("."):
            _fail(
                AuthorityErrorCode.GIT_COMMAND_FAILED,
                "whole-repository staging is forbidden",
            )
        if absolute.exists() and absolute.is_dir():
            _fail(
                AuthorityErrorCode.GIT_COMMAND_FAILED,
                "explicit signing paths must name files, not directories",
                path=str(raw),
            )
        value = relative.as_posix()
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "explicit lifecycle signing requires at least one intended path",
        )
    return normalized


def _git_index_path(repo: Path) -> Path:
    value = _git_required(repo, "rev-parse", "--git-path", "index")
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    return path.resolve(strict=False)


def _index_environment(index_path: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment["GIT_INDEX_FILE"] = str(index_path)
    return environment


def _index_entry(
    repo: Path,
    path: str,
    *,
    environment: Mapping[str, str] | None = None,
) -> tuple[str, str] | None:
    result = _git(repo, "ls-files", "--stage", "--", path, env=environment)
    if result.returncode != 0:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "could not inspect an explicit path in the index",
            path=path,
            stderr=(result.stderr or result.stdout).strip(),
        )
    lines = [line for line in result.stdout.splitlines() if line]
    if len(lines) > 1:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "refusing explicit signing with an unmerged or expanded path",
            path=path,
        )
    if not lines:
        return None
    try:
        metadata, indexed_path = lines[0].split("\t", 1)
        mode, object_id, stage = metadata.split()
    except ValueError:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "malformed index entry for explicit signing path",
            path=path,
        )
    if indexed_path != path or stage != "0":
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "unexpected index entry for explicit signing path",
            path=path,
        )
    return mode, object_id


@contextlib.contextmanager
def _index_write_lock(repo: Path):
    """Hold Git's conventional index lock across snapshot and ref publication."""

    index_path = _git_index_path(repo)
    lock_path = index_path.with_name(f"{index_path.name}.lock")
    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_CLOEXEC,
            0o600,
        )
    except FileExistsError:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "repository index is locked by another operation",
            path=str(lock_path),
        )
    except OSError as error:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            f"could not acquire repository index lock: {error}",
            path=str(lock_path),
        )
    try:
        yield index_path
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # HEAD and the index may already be atomically published. Never
            # turn lock-file cleanup into a post-commit rollback attempt.
            pass


def _prepare_signing_tree(
    repo: Path,
    expected_old: str,
    explicit_paths: Sequence[str],
    signing_index: Path,
    *,
    allow_empty: bool,
) -> tuple[str, Mapping[str, str]]:
    environment = _index_environment(signing_index)
    read_tree = _git(repo, "read-tree", expected_old, env=environment)
    if read_tree.returncode != 0:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "could not initialize detached signing index from HEAD",
            stderr=(read_tree.stderr or read_tree.stdout).strip(),
        )
    for path in explicit_paths:
        _index_entry(repo, path)
    if explicit_paths:
        staged = _git(repo, "add", "--", *explicit_paths, env=environment)
        if staged.returncode != 0:
            _fail(
                AuthorityErrorCode.GIT_COMMAND_FAILED,
                "could not add explicit paths to detached signing index",
                stderr=(staged.stderr or staged.stdout).strip(),
            )
    tree = _git_required(repo, "write-tree", env=environment)
    old_tree = _git_required(repo, "rev-parse", f"{expected_old}^{{tree}}")
    if not allow_empty and tree == old_tree:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "explicit paths contain no commit-worthy change",
            paths=list(explicit_paths),
        )
    return tree, environment


def _prepare_published_index(
    repo: Path,
    expected_old: str,
    current_index: Path,
    signing_environment: Mapping[str, str],
    explicit_paths: Sequence[str],
    prepared_index: Path,
) -> None:
    if current_index.exists():
        shutil.copyfile(current_index, prepared_index)
        os.chmod(prepared_index, stat.S_IMODE(current_index.stat().st_mode))
    else:
        initialized = _git(
            repo,
            "read-tree",
            expected_old,
            env=_index_environment(prepared_index),
        )
        if initialized.returncode != 0:
            _fail(
                AuthorityErrorCode.GIT_COMMAND_FAILED,
                "could not initialize replacement repository index",
                stderr=(initialized.stderr or initialized.stdout).strip(),
            )
    prepared_environment = _index_environment(prepared_index)
    for path in explicit_paths:
        entry = _index_entry(repo, path, environment=signing_environment)
        if entry is None:
            updated = _git(
                repo,
                "update-index",
                "--force-remove",
                "--",
                path,
                env=prepared_environment,
            )
        else:
            mode, object_id = entry
            updated = _git(
                repo,
                "update-index",
                "--add",
                "--cacheinfo",
                f"{mode},{object_id},{path}",
                env=prepared_environment,
            )
        if updated.returncode != 0:
            _fail(
                AuthorityErrorCode.GIT_COMMAND_FAILED,
                "could not prepare explicit path in replacement index",
                path=path,
                stderr=(updated.stderr or updated.stdout).strip(),
            )


def _restore_exact_index(
    index_path: Path,
    *,
    existed: bool,
    content: bytes,
    mode: int,
    transaction_directory: Path,
) -> None:
    try:
        if not existed:
            index_path.unlink(missing_ok=True)
            return
        restore_path = transaction_directory / "restore.index"
        restore_path.write_bytes(content)
        os.chmod(restore_path, mode)
        os.replace(restore_path, index_path)
    except OSError as error:
        _fail(
            AuthorityErrorCode.GIT_INDEX_RESTORE_FAILED,
            f"could not restore exact pre-operation index after ref refusal: {error}",
            path=str(index_path),
        )


def _publish_verified_commit(
    repo: Path,
    commit: str,
    expected_old: str,
    index_path: Path,
    prepared_index: Path,
    transaction_directory: Path,
) -> None:
    index_existed = index_path.exists()
    index_content = index_path.read_bytes() if index_existed else b""
    index_mode = (
        stat.S_IMODE(index_path.stat().st_mode)
        if index_existed
        else 0o644
    )
    try:
        os.replace(prepared_index, index_path)
    except OSError as error:
        _fail(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            f"could not atomically install prepared repository index: {error}",
        )
    try:
        updated = _git(repo, "update-ref", "HEAD", commit, expected_old)
    except AuthorityChainError as error:
        _restore_exact_index(
            index_path,
            existed=index_existed,
            content=index_content,
            mode=index_mode,
            transaction_directory=transaction_directory,
        )
        _fail(
            AuthorityErrorCode.GIT_REF_RACE,
            "verified commit publication could not complete",
            expected_old=expected_old,
            detached_commit=commit,
            cause=error.to_dict(),
        )
    if updated.returncode == 0:
        return
    _restore_exact_index(
        index_path,
        existed=index_existed,
        content=index_content,
        mode=index_mode,
        transaction_directory=transaction_directory,
    )
    _fail(
        AuthorityErrorCode.GIT_REF_RACE,
        "HEAD changed before the verified signed commit could be published",
        expected_old=expected_old,
        detached_commit=commit,
        stderr=(updated.stderr or updated.stdout).strip(),
    )


def sign_commit(
    repo: Path,
    activation: ActivationRecord,
    message: str,
    *,
    signing_program: str | None = None,
    author_name: str | None = None,
    author_email: str | None = None,
    allow_empty: bool = True,
    stage_paths: Sequence[str | Path] | None = None,
    authority_lock_held: bool = False,
) -> SignedCommit:
    """Verify a detached signed object before atomically publishing it to HEAD."""

    state_context = (
        contextlib.nullcontext()
        if authority_lock_held
        else authority_state_lock(repo, exclusive=True)
    )
    with state_context:
        if not authority_lock_held:
            canonical_records = load_canonical_activation_entries(repo)
            matches = [
                record
                for record in canonical_records
                if record.uid == activation.uid
            ]
            if len(matches) != 1:
                _fail(
                    AuthorityErrorCode.ACTIVATION_KEY_UNBOUND,
                    "activation UID does not resolve exactly once from canonical state",
                    activation_uid=activation.uid,
                    matches=len(matches),
                )
            activation = matches[0]
            analysis = analyze_activations(canonical_records)
            if not analysis.is_gate_valid(activation.uid):
                _fail(
                    AuthorityErrorCode.ACTIVATION_GATE_INVALID,
                    "activation is not gate-valid for signing",
                    activation_uid=activation.uid,
                    reasons=[
                        finding.to_dict()
                        for finding in analysis.reasons_for(activation.uid)
                    ],
                )
        else:
            canonical_records = load_canonical_activation_entries(repo)
            canonical_matches = [
                record
                for record in canonical_records
                if record.uid == activation.uid
                and activation.agent_public_key
                and _activation_key_matches(record, activation.public_key.blob)
            ]
            if len(canonical_matches) != 1:
                _fail(
                    AuthorityErrorCode.ACTIVATION_KEY_UNBOUND,
                    "locked lifecycle signer no longer matches canonical activation state",
                    activation_uid=activation.uid,
                    matches=len(canonical_matches),
                )
            analysis = analyze_activations(canonical_records)
            if not analysis.is_gate_valid(activation.uid):
                _fail(
                    AuthorityErrorCode.ACTIVATION_GATE_INVALID,
                    "locked lifecycle activation is not gate-valid for signing",
                    activation_uid=activation.uid,
                    reasons=[
                        finding.to_dict()
                        for finding in analysis.reasons_for(activation.uid)
                    ],
                )
        if activation.status != "active":
            _fail(
                AuthorityErrorCode.ACTIVATION_RETIRED,
                f"activation {activation.uid} is not active",
            )
        if not activation.agent_public_key:
            _fail(
                AuthorityErrorCode.ACTIVATION_KEY_UNBOUND,
                f"activation {activation.uid} has no agent_public_key",
            )
        expected_key = activation.public_key
        broker = activation_signing_broker(
            activation.uid,
            expected_public_key=expected_key.canonical,
        )
        program = signing_program or shutil.which("ssh-keygen")
        if not program:
            _fail(AuthorityErrorCode.GIT_COMMAND_FAILED, "ssh-keygen is unavailable")
        canonical_name, canonical_email = canonical_git_identity(activation)
        name = author_name or canonical_name
        email = author_email or canonical_email
        config_path = _repo_config_path(repo)
        config_before = _config_bytes(config_path)
        explicit_paths = (
            _normalize_explicit_paths(repo, stage_paths)
            if stage_paths is not None
            else []
        )
        command = [
            "-c",
            f"user.name={name}",
            "-c",
            f"user.email={email}",
            "-c",
            f"user.signingkey=key::{expected_key.canonical}",
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={program}",
            "-c",
            "commit.gpgsign=true",
            "commit-tree",
            "-S",
            "-p",
        ]
        with _commit_lock(repo), _index_write_lock(repo) as index_path:
            expected_old = _git_required(repo, "rev-parse", "HEAD")
            git_directory = _git_common_dir(repo)
            transaction_directory = Path(
                tempfile.mkdtemp(
                    prefix="tropo-detached-sign-",
                    dir=str(git_directory),
                )
            )
            try:
                signing_index = transaction_directory / "signing.index"
                tree, signing_environment = _prepare_signing_tree(
                    repo,
                    expected_old,
                    explicit_paths,
                    signing_index,
                    allow_empty=allow_empty,
                )
                message_path = transaction_directory / "message"
                message_path.write_text(message, encoding="utf-8")
                commit_environment = dict(os.environ)
                commit_environment.update(
                    {
                        "GIT_AUTHOR_NAME": name,
                        "GIT_AUTHOR_EMAIL": email,
                        "GIT_COMMITTER_NAME": name,
                        "GIT_COMMITTER_EMAIL": email,
                        "SSH_AUTH_SOCK": str(broker.socket_path),
                        "SSH_AGENT_PID": str(broker.pid),
                    }
                )
                result = _git(
                    repo,
                    *command,
                    expected_old,
                    "-F",
                    str(message_path),
                    tree,
                    timeout=120,
                    env=commit_environment,
                )
                config_after = _config_bytes(config_path)
                if config_after != config_before:
                    _fail(
                        AuthorityErrorCode.GIT_CONFIG_MUTATED,
                        "per-command signing changed repository .git/config",
                    )
                if result.returncode != 0:
                    _fail(
                        AuthorityErrorCode.GIT_COMMAND_FAILED,
                        "detached activation-signed commit creation failed",
                        stderr=(result.stderr or result.stdout).strip(),
                    )
                commit = result.stdout.strip()
                if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
                    _fail(
                        AuthorityErrorCode.GIT_COMMAND_FAILED,
                        "git commit-tree did not return one commit object ID",
                        output=commit,
                    )
                signature = extract_commit_signature(repo, commit)
                if (
                    public_key_from_blob(signature.key_blob).key_point
                    != expected_key.key_point
                ):
                    _fail(
                        AuthorityErrorCode.SIGNING_KEY_MISMATCH,
                        "decoded SSHSIG key is not the activation's minted key",
                        expected_fingerprint=expected_key.fingerprint,
                        actual_fingerprint=signature.key_fingerprint,
                    )
                if signature.author_name != name or signature.author_email != email:
                    _fail(
                        AuthorityErrorCode.AUTHOR_IDENTITY_MISMATCH,
                        "detached commit author does not match requested signing identity",
                        expected=f"{name} <{email}>",
                        actual=signature.author_identity,
                    )
                _verify_one_key(repo, signature, canonical_email)
                if _config_bytes(config_path) != config_before:
                    _fail(
                        AuthorityErrorCode.GIT_CONFIG_MUTATED,
                        "detached commit verification changed repository .git/config",
                    )
                prepared_index = transaction_directory / "published.index"
                _prepare_published_index(
                    repo,
                    expected_old,
                    index_path,
                    signing_environment,
                    explicit_paths,
                    prepared_index,
                )
                _publish_verified_commit(
                    repo,
                    commit,
                    expected_old,
                    index_path,
                    prepared_index,
                    transaction_directory,
                )
            finally:
                shutil.rmtree(transaction_directory, ignore_errors=True)
    return SignedCommit(commit, signature, activation.uid)


def discover_harness_signer(repo: Path) -> tuple[str, str]:
    """Resolve the known Cursor harness helper and public key from global config."""

    program = _git(repo, "config", "--global", "--get", "gpg.ssh.program")
    key = _git(repo, "config", "--global", "--get", "user.signingkey")
    if program.returncode != 0 or key.returncode != 0:
        _fail(
            AuthorityErrorCode.HARNESS_SIGNER_UNAVAILABLE,
            "global harness signing program/key is not configured",
        )
    program_value = program.stdout.strip()
    key_value = parse_openssh_public_key(key.stdout.strip()).canonical
    if Path(program_value).name != HARNESS_HELPER_NAME:
        _fail(
            AuthorityErrorCode.HARNESS_SIGNER_UNAVAILABLE,
            f"configured signing program is not {HARNESS_HELPER_NAME}",
            configured_program=program_value,
        )
    if not Path(program_value).is_file():
        _fail(
            AuthorityErrorCode.HARNESS_SIGNER_UNAVAILABLE,
            "configured harness signing helper does not exist",
            configured_program=program_value,
        )
    return key_value, program_value


def probe_anchor_reachability(
    candidate_public_key: str,
    *,
    signing_program: str,
    signing_key: str | Path | None = None,
    temporary_parent: Path | None = None,
    candidate_classification: AnchorClassification = AnchorClassification.CANDIDATE,
) -> ReachabilityProbeResult:
    """Attempt a real forged-author commit against a candidate anchor."""

    candidate = parse_openssh_public_key(candidate_public_key)
    key_argument = str(signing_key) if signing_key is not None else candidate.canonical
    temporary = tempfile.TemporaryDirectory(
        prefix="tropo-anchor-probe-",
        dir=str(temporary_parent) if temporary_parent else None,
    )
    repo = Path(temporary.name)
    try:
        initialized = _git(repo, "init", "--quiet")
        if initialized.returncode != 0:
            _fail(
                AuthorityErrorCode.ANCHOR_PROBE_FAILED,
                "reachability probe could not initialize its scratch repository",
                stderr=(initialized.stderr or initialized.stdout).strip(),
            )
        config_path = _repo_config_path(repo)
        config_before = _config_bytes(config_path)
        result = _git(
            repo,
            "-c",
            f"user.name={DEFAULT_FORGE_NAME}",
            "-c",
            f"user.email={DEFAULT_FORGE_EMAIL}",
            "-c",
            f"user.signingkey={key_argument}",
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={signing_program}",
            "-c",
            "commit.gpgsign=true",
            "commit",
            "--allow-empty",
            "-S",
            "-m",
            "Tropo authority-anchor reachability probe",
            timeout=120,
        )
        if _config_bytes(config_path) != config_before:
            _fail(
                AuthorityErrorCode.GIT_CONFIG_MUTATED,
                "reachability probe changed scratch .git/config",
            )
        if result.returncode != 0:
            return ReachabilityProbeResult(
                attempted=True,
                reachable=False,
                authority_accepted=False,
                positive_control_passed=False,
                finding=AuthorityErrorCode.ANCHOR_UNREACHABLE,
                candidate_public_key=candidate.canonical,
                signing_program=signing_program,
                fabricated_author=f"{DEFAULT_FORGE_NAME} <{DEFAULT_FORGE_EMAIL}>",
                detail=(result.stderr or result.stdout).strip(),
                candidate_classification=candidate_classification,
            )
        commit = _git_required(repo, "rev-parse", "HEAD")
        signature = extract_commit_signature(repo, commit)
        if (
            public_key_from_blob(signature.key_blob).key_point
            != candidate.key_point
        ):
            _fail(
                AuthorityErrorCode.SIGNING_KEY_MISMATCH,
                "probe produced a signature, but not from the candidate anchor",
                candidate_fingerprint=candidate.fingerprint,
                actual_fingerprint=signature.key_fingerprint,
            )
        _verify_commit_with_signers(
            repo,
            commit,
            f"{DEFAULT_FORGE_EMAIL} {candidate.canonical}\n",
        )
        if (
            signature.author_name != DEFAULT_FORGE_NAME
            or signature.author_email != DEFAULT_FORGE_EMAIL
        ):
            _fail(
                AuthorityErrorCode.ANCHOR_PROBE_FAILED,
                "probe signature did not carry the fabricated author identity",
            )
        return ReachabilityProbeResult(
            attempted=True,
            reachable=True,
            authority_accepted=False,
            positive_control_passed=False,
            finding=AuthorityErrorCode.ANCHOR_REACHABLE,
            candidate_public_key=candidate.canonical,
            signing_program=signing_program,
            fabricated_author=signature.author_identity,
            commit=commit,
            signature=signature,
            detail=(
                "candidate signed a valid commit under a fabricated author; "
                "refused as an authority anchor"
            ),
            candidate_classification=candidate_classification,
        )
    finally:
        temporary.cleanup()


def probe_harness_anchor(
    repo: Path,
    *,
    temporary_parent: Path | None = None,
) -> ReachabilityProbeResult:
    """Positive control: the known harness helper/key MUST forge successfully."""

    key, program = discover_harness_signer(repo)
    result = probe_anchor_reachability(
        key,
        signing_program=program,
        temporary_parent=temporary_parent,
        candidate_classification=AnchorClassification.KNOWN_HARNESS_KEY_AND_PROGRAM,
    )
    if not result.reachable or result.signature is None:
        _fail(
            AuthorityErrorCode.KNOWN_REACHABLE_ANCHOR_NOT_REACHED,
            (
                "known-positive harness reachability plant did not produce a signature; "
                "an unreachable result is not accepted as proof"
            ),
            probe=result.to_dict(),
        )
    return replace(
        result,
        positive_control_passed=True,
        positive_control_key=key,
        positive_control_commit=result.commit,
    )


def probe_anchor_with_positive_control(
    repo: Path,
    candidate_public_key: str,
    *,
    signing_program: str,
    signing_key: str | Path | None = None,
    temporary_parent: Path | None = None,
) -> ReachabilityProbeResult:
    """Probe a candidate only after proving the instrument on the harness key.

    A bare "unreachable" result is never authority-bearing: the same instrument
    must first reproduce the known reachable harness forgery in this call.
    """

    harness_key, harness_program = discover_harness_signer(repo)
    positive = probe_harness_anchor(repo, temporary_parent=temporary_parent)
    candidate = parse_openssh_public_key(candidate_public_key)
    known_key = (
        candidate.key_point
        == parse_openssh_public_key(harness_key).key_point
    )
    requested_program = Path(signing_program)
    known_program = (
        requested_program.name == HARNESS_HELPER_NAME
        or (
            requested_program.exists()
            and Path(harness_program).exists()
            and requested_program.resolve() == Path(harness_program).resolve()
        )
    )
    if known_key:
        classification = (
            AnchorClassification.KNOWN_HARNESS_KEY_AND_PROGRAM
            if known_program
            else AnchorClassification.KNOWN_HARNESS_KEY
        )
        return ReachabilityProbeResult(
            attempted=True,
            reachable=True,
            authority_accepted=False,
            positive_control_passed=True,
            finding=AuthorityErrorCode.HARNESS_KEY_PROVENANCE_ONLY,
            candidate_public_key=candidate.canonical,
            signing_program=signing_program,
            fabricated_author=positive.fabricated_author,
            commit=positive.commit,
            signature=positive.signature,
            detail=(
                "candidate is the explicitly known agent-reachable harness key; "
                "a failing alternate program cannot reclassify it as authority"
            ),
            candidate_classification=classification,
            positive_control_key=harness_key,
            positive_control_commit=positive.commit,
        )
    if known_program:
        return ReachabilityProbeResult(
            attempted=True,
            reachable=False,
            authority_accepted=False,
            positive_control_passed=True,
            finding=AuthorityErrorCode.HARNESS_KEY_PROVENANCE_ONLY,
            candidate_public_key=candidate.canonical,
            signing_program=signing_program,
            fabricated_author=positive.fabricated_author,
            detail=(
                "candidate probe uses the known harness signing program; "
                "that program cannot prove an authority key unreachable"
            ),
            candidate_classification=AnchorClassification.KNOWN_HARNESS_PROGRAM,
            positive_control_key=harness_key,
            positive_control_commit=positive.commit,
        )
    result = probe_anchor_reachability(
        candidate.canonical,
        signing_program=signing_program,
        signing_key=signing_key,
        temporary_parent=temporary_parent,
    )
    return replace(
        result,
        positive_control_passed=True,
        # Stage 1 never turns a failed/negative reachability attempt into
        # authority. The positive control proves only that the instrument can
        # detect the known reachable harness key.
        authority_accepted=False,
        positive_control_key=harness_key,
        positive_control_commit=positive.commit,
    )


def detect_key_author_collapse(signatures: Iterable[CommitSignature]) -> None:
    """Refuse one SSH signing key observed under multiple author identities."""

    authors_by_key: dict[bytes, set[str]] = defaultdict(set)
    commits_by_key: dict[bytes, list[str]] = defaultdict(list)
    public_by_key: dict[bytes, str] = {}
    for signature in signatures:
        key_point = public_key_from_blob(signature.key_blob).key_point
        authors_by_key[key_point].add(signature.author_identity)
        commits_by_key[key_point].append(signature.commit)
        public_by_key[key_point] = signature.public_key
    for key_blob, authors in authors_by_key.items():
        if len(authors) > 1:
            key = parse_openssh_public_key(public_by_key[key_blob])
            _fail(
                AuthorityErrorCode.ONE_KEY_MANY_AUTHORS,
                "one signing key appears under more than one author identity",
                key_fingerprint=key.fingerprint,
                authors=sorted(authors),
                commits=commits_by_key[key_blob],
            )


def collect_commit_signatures(
    repo: Path,
    commits: Iterable[str],
) -> CommitSignatureAudit:
    """Collect supported signatures while naming mixed-history skips."""

    signatures: list[CommitSignature] = []
    skipped: list[SkippedCommitSignature] = []
    for commit in commits:
        try:
            signatures.append(extract_commit_signature(repo, commit))
        except AuthorityChainError as error:
            if error.code not in {
                AuthorityErrorCode.SIGNATURE_MISSING,
                AuthorityErrorCode.SIGNATURE_UNSUPPORTED,
            }:
                raise
            skipped.append(
                SkippedCommitSignature(commit, error.code, error.message)
            )
    return CommitSignatureAudit(signatures, skipped)


def audit_commits_for_identity_collapse(
    repo: Path,
    commits: Iterable[str],
) -> CommitSignatureAudit:
    audited = collect_commit_signatures(repo, commits)
    detect_key_author_collapse(audited)
    return audited


def _harness_public_key(repo: Path) -> OpenSSHPublicKey | None:
    try:
        key, _ = discover_harness_signer(repo)
        return parse_openssh_public_key(key)
    except AuthorityChainError as error:
        if error.code == AuthorityErrorCode.HARNESS_SIGNER_UNAVAILABLE:
            return None
        raise


def _verify_one_key(repo: Path, signature: CommitSignature, principal: str) -> None:
    _verify_commit_with_signers(
        repo,
        signature.commit,
        f"{principal} {signature.public_key}\n",
    )


def _principal_identifiers(principal: Mapping[str, Any]) -> set[str]:
    values: list[Any] = [
        principal.get("uid"),
        principal.get("slug"),
        principal.get("name"),
        principal.get("principal"),
    ]
    aliases = principal.get("slug_aliases")
    if isinstance(aliases, list):
        values.extend(aliases)
    return {str(value).strip().lower() for value in values if str(value or "").strip()}


def _principal_is_active(principal: Mapping[str, Any]) -> bool:
    status = str(principal.get("status") or "").strip().lower()
    state = str(principal.get("state") or "").strip().lower()
    revoked = (
        principal.get("revoked") is True
        or bool(principal.get("revoked_at"))
        or status in {"revoked", "retired", "superseded", "archived", "inactive"}
        or state in {"revoked", "retired", "superseded", "archived", "inactive"}
    )
    declared_active = status == "active" or state == "active"
    return declared_active and not revoked


def resolve_activation_activator(
    activation: ActivationRecord,
    activation_records: Sequence[ActivationRecord],
    principal_records: Sequence[Mapping[str, Any]],
) -> tuple[str, str]:
    """Resolve activated_by to one eligible canonical principal or activation."""

    reference = activation.activated_by.strip().lower()
    if not reference:
        _fail(
            AuthorityErrorCode.ACTIVATOR_UNRESOLVED,
            f"activation {activation.uid} has no activated_by link",
        )
    principal_matches = [
        principal
        for principal in principal_records
        if reference in _principal_identifiers(principal) and _principal_is_active(principal)
    ]
    analysis = analyze_activations(activation_records)
    activation_matches: list[ActivationRecord] = []
    for candidate in activation_records:
        identifiers = {
            candidate.uid.lower(),
            candidate.name.lower(),
            f"{candidate.agent}-{candidate.generation.lower()}".lower(),
        }
        eligible_status = candidate.status in {"active", "retired", "paused"}
        not_after_child = (
            not activation.activated_at
            or not candidate.activated_at
            or candidate.activated_at <= activation.activated_at
        )
        if (
            reference in identifiers
            and eligible_status
            and not_after_child
            and analysis.is_gate_valid(candidate.uid)
        ):
            activation_matches.append(candidate)
    match_count = len(principal_matches) + len(activation_matches)
    if match_count != 1:
        _fail(
            AuthorityErrorCode.ACTIVATOR_UNRESOLVED,
            "activated_by does not resolve to exactly one eligible principal/activation",
            activation_uid=activation.uid,
            activated_by=activation.activated_by,
            eligible_principals=[
                str(principal.get("uid") or "") for principal in principal_matches
            ],
            eligible_activations=[record.uid for record in activation_matches],
        )
    if principal_matches:
        return "principal", str(principal_matches[0].get("uid") or "")
    return "activation", activation_matches[0].uid


def resolve_commit_chain(
    repo: Path,
    commit: str,
    *,
    require_authority: bool = False,
) -> ChainResult:
    """Resolve from one fresh canonical snapshot held through verification."""

    with authority_state_lock(repo):
        return _resolve_commit_chain_locked(
            repo,
            commit,
            require_authority=require_authority,
        )


def _resolve_commit_chain_locked(
    repo: Path,
    commit: str,
    *,
    require_authority: bool = False,
) -> ChainResult:
    """Resolve a commit from fresh canonical entries; caller snapshots are forbidden."""

    signature = extract_commit_signature(repo, commit)
    harness = _harness_public_key(repo)
    if (
        harness is not None
        and public_key_from_blob(signature.key_blob).key_point
        == harness.key_point
    ):
        _verify_one_key(repo, signature, "harness-provenance")
        finding = Finding(
            AuthorityErrorCode.HARNESS_KEY_PROVENANCE_ONLY,
            (
                "the harness-provided key is agent-reachable and carries provenance only, "
                "regardless of the commit author"
            ),
        )
        if require_authority:
            _fail(
                AuthorityErrorCode.HARNESS_KEY_PROVENANCE_ONLY,
                "harness signatures never satisfy an authority gate",
                commit=signature.commit,
                author=signature.author_identity,
            )
        return ChainResult(
            commit=signature.commit,
            signature_key=signature.public_key,
            key_fingerprint=signature.key_fingerprint,
            author_identity=signature.author_identity,
            provenance="harness-provenance-only",
            authority=False,
            findings=(finding,),
        )

    activation_records = load_canonical_activation_entries(repo)
    principal_records = load_principal_records(canonical_vault_files(repo))
    analysis = analyze_activations(activation_records)
    matches = [
        record
        for record in activation_records
        if _activation_key_matches(record, signature.key_blob)
    ]
    if not matches:
        _fail(
            AuthorityErrorCode.ACTIVATION_KEY_UNBOUND,
            "commit signing key does not resolve to an activation entry",
            commit=signature.commit,
            key_fingerprint=signature.key_fingerprint,
        )
    valid_active = [
        record
        for record in matches
        if record.status == "active" and analysis.is_gate_valid(record.uid)
    ]
    if not valid_active:
        invalid_live = [
            record
            for record in matches
            if _is_nonterminal(record) and not analysis.is_gate_valid(record.uid)
        ]
        if invalid_live:
            _fail(
                AuthorityErrorCode.ACTIVATION_GATE_INVALID,
                "the matching nonterminal activation is not lifecycle/lineage gate-valid",
                activation_uids=[record.uid for record in invalid_live],
                reasons=[
                    finding.to_dict()
                    for record in invalid_live
                    for finding in analysis.reasons_for(record.uid)
                ],
            )
        _fail(
            AuthorityErrorCode.ACTIVATION_RETIRED,
            "the signing key is bound only to a retired/non-active activation",
            activation_uids=[record.uid for record in matches],
        )
    if len(valid_active) != 1:
        _fail(
            AuthorityErrorCode.ACTIVATION_AMBIGUOUS,
            "signing key resolves to more than one gate-valid active activation",
            activation_uids=[record.uid for record in valid_active],
        )
    activation_snapshot = valid_active[0]
    with activation_state_lock(repo, activation_snapshot.uid):
        fresh_records = load_canonical_activation_entries(repo)
        fresh_matches = [
            record
            for record in fresh_records
            if record.uid == activation_snapshot.uid
            and _activation_key_matches(record, signature.key_blob)
        ]
        if len(fresh_matches) != 1:
            _fail(
                AuthorityErrorCode.ACTIVATION_KEY_UNBOUND,
                "activation changed while acquiring its verification lock",
                activation_uid=activation_snapshot.uid,
                matches=len(fresh_matches),
            )
        activation = fresh_matches[0]
        fresh_analysis = analyze_activations(fresh_records)
        if activation.status != "active":
            _fail(
                AuthorityErrorCode.ACTIVATION_RETIRED,
                "activation retired before signature verification completed",
                activation_uid=activation.uid,
            )
        if not fresh_analysis.is_gate_valid(activation.uid):
            _fail(
                AuthorityErrorCode.ACTIVATION_GATE_INVALID,
                "activation became gate-invalid before signature verification completed",
                activation_uid=activation.uid,
                reasons=[
                    finding.to_dict()
                    for finding in fresh_analysis.reasons_for(activation.uid)
                ],
            )
        return _finish_activation_chain_verification(
            repo,
            signature,
            activation,
            fresh_records,
            principal_records,
            require_authority=require_authority,
        )


def _finish_activation_chain_verification(
    repo: Path,
    signature: CommitSignature,
    activation: ActivationRecord,
    activation_records: Sequence[ActivationRecord],
    principal_records: Sequence[Mapping[str, Any]],
    *,
    require_authority: bool,
) -> ChainResult:

    _require_activation_author_identity(signature, activation)
    activator_type, activator_uid = resolve_activation_activator(
        activation,
        activation_records,
        principal_records,
    )
    # The verifier receives no persistent allowed-signers file.  This rendering
    # is fresh from the supplied activation entries and exists only in a system
    # temporary directory for the duration of git verify-commit.
    allowed_signers = derive_allowed_signers(activation_records)
    _verify_commit_with_signers(repo, signature.commit, allowed_signers)
    if require_authority:
        _fail(
            AuthorityErrorCode.AGENT_KEY_PROVENANCE_ONLY,
            "activation-bound agent keys prove provenance and never satisfy authority gates",
            activation_uid=activation.uid,
            agent=activation.agent,
            generation=activation.generation,
        )
    finding = Finding(
        AuthorityErrorCode.AGENT_KEY_PROVENANCE_ONLY,
        "activation-bound key proves provenance only; authority remains false",
        (activation.uid,),
    )
    return ChainResult(
        commit=signature.commit,
        signature_key=signature.public_key,
        key_fingerprint=signature.key_fingerprint,
        author_identity=signature.author_identity,
        provenance="agent-activation",
        authority=False,
        activation_uid=activation.uid,
        agent=activation.agent,
        generation=activation.generation,
        activated_by=activation.activated_by,
        activator_type=activator_type,
        activator_uid=activator_uid,
        principal_uid=activator_uid if activator_type == "principal" else None,
        findings=(finding,),
    )


def _require_activation_author_identity(
    signature: CommitSignature,
    activation: ActivationRecord,
) -> None:
    expected_name, expected_email = canonical_git_identity(activation)
    if (
        signature.author_name != expected_name
        or signature.author_email != expected_email
    ):
        _fail(
            AuthorityErrorCode.AUTHOR_IDENTITY_MISMATCH,
            "commit author does not match the activation-derived identity",
            expected=f"{expected_name} <{expected_email}>",
            actual=signature.author_identity,
        )


def load_principal_records(vault_files: Path) -> list[dict[str, Any]]:
    principals: list[dict[str, Any]] = []
    for path in sorted(vault_files.glob("*.md")):
        fm = parse_frontmatter(path)
        if fm and fm.get("type") == "principal":
            principals.append(fm)
    return principals


def validate_authority_principals(
    principal_records: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Return only active, non-revoked principals explicitly eligible to sign."""

    authority_principals: list[Mapping[str, Any]] = []
    seen_keys: dict[bytes, str] = {}
    for principal in principal_records:
        public_value = principal.get(AUTHORITY_PUBLIC_KEY_FIELD)
        may_sign = principal.get("may_sign_authority") is True
        if not may_sign or not _principal_is_active(principal):
            continue
        if not public_value:
            _fail(
                AuthorityErrorCode.AUTHORITY_ANCHOR_UNTRUSTED,
                "eligible principal has no authority_public_key",
                principal_uid=principal.get("uid"),
            )
        key = parse_openssh_public_key(str(public_value))
        slug = str(principal.get("slug") or principal.get("name") or principal.get("uid") or "")
        prior = seen_keys.get(key.key_point)
        if prior and prior != slug:
            _fail(
                AuthorityErrorCode.ONE_KEY_MANY_SLUGS,
                "one authority key resolves to more than one principal identity",
                principal_slugs=[prior, slug],
                key_fingerprint=key.fingerprint,
            )
        seen_keys[key.key_point] = slug
        custody = principal.get(KEY_CUSTODY_FIELD)
        if not isinstance(custody, str) or not custody.strip():
            _fail(
                AuthorityErrorCode.KEY_CUSTODY_MISSING,
                "principal with an authority_public_key must declare key_custody",
                principal_uid=principal.get("uid"),
                principal_slug=principal.get("slug"),
            )
        authority_principals.append(principal)
    return authority_principals


def _principal_key_matches(
    principal: Mapping[str, Any],
    key_blob: bytes,
) -> bool:
    public_value = principal.get(AUTHORITY_PUBLIC_KEY_FIELD)
    if not public_value:
        return False
    try:
        return (
            parse_openssh_public_key(str(public_value)).key_point
            == public_key_from_blob(key_blob).key_point
        )
    except AuthorityChainError:
        if principal.get("may_sign_authority") is True and _principal_is_active(principal):
            raise
        return False


def verify_authority_claim(
    repo: Path,
    commit: str,
    reachability_probe: ReachabilityProbeResult,
) -> AuthorityClaim:
    """Verify under one state lock; Stage 1 never grants negative-probe authority."""

    with authority_state_lock(repo):
        return _verify_authority_claim_locked(repo, commit, reachability_probe)


def _verify_authority_claim_locked(
    repo: Path,
    commit: str,
    reachability_probe: ReachabilityProbeResult,
) -> AuthorityClaim:
    signature = extract_commit_signature(repo, commit)
    harness_key, harness_program = discover_harness_signer(repo)
    harness = parse_openssh_public_key(harness_key)
    if (
        public_key_from_blob(signature.key_blob).key_point
        == harness.key_point
    ):
        _fail(
            AuthorityErrorCode.HARNESS_KEY_PROVENANCE_ONLY,
            "the known harness key is explicitly non-authoritative regardless of probe outcome",
        )
    activation_records = load_canonical_activation_entries(repo)
    activation_matches = [
        record
        for record in activation_records
        if _activation_key_matches(record, signature.key_blob)
    ]
    if activation_matches:
        _fail(
            AuthorityErrorCode.AGENT_KEY_PROVENANCE_ONLY,
            "an activation-bound key can never satisfy authority, regardless of custody labels",
            activation_uids=sorted(record.uid for record in activation_matches),
        )
    principal_records = load_principal_records(canonical_vault_files(repo))
    principals = validate_authority_principals(principal_records)
    raw_matches = [
        principal
        for principal in principal_records
        if _principal_key_matches(principal, signature.key_blob)
    ]
    matches = [
        principal
        for principal in principals
        if _principal_key_matches(principal, signature.key_blob)
    ]
    if len(matches) != 1:
        if raw_matches:
            _fail(
                AuthorityErrorCode.AUTHORITY_PRINCIPAL_INELIGIBLE,
                "signature key belongs only to a principal not eligible to sign authority",
                principal_uids=[
                    str(principal.get("uid") or "") for principal in raw_matches
                ],
            )
        _fail(
            AuthorityErrorCode.AUTHORITY_ANCHOR_UNTRUSTED,
            "signature key does not resolve to exactly one authority principal",
            matches=len(matches),
        )
    principal = matches[0]
    _verify_one_key(
        repo,
        signature,
        f"authority-{str(principal.get('uid') or 'principal')}",
    )

    # Never trust caller-populated positive_control_* or authority_accepted
    # fields. Execute the known-positive harness plant in this verifier call.
    positive = probe_harness_anchor(repo)
    if (
        not positive.reachable
        or positive.signature is None
        or public_key_from_blob(positive.signature.key_blob).key_point
        != harness.key_point
    ):
        _fail(
            AuthorityErrorCode.AUTHORITY_REACHABILITY_UNPROVEN,
            "independently executed harness positive control did not prove reachability",
        )
    try:
        claimed_candidate = parse_openssh_public_key(
            reachability_probe.candidate_public_key
        )
    except AuthorityChainError:
        _fail(
            AuthorityErrorCode.AUTHORITY_REACHABILITY_UNPROVEN,
            "caller probe does not name a valid candidate key",
        )
    if (
        claimed_candidate.key_point
        != public_key_from_blob(signature.key_blob).key_point
    ):
        _fail(
            AuthorityErrorCode.AUTHORITY_REACHABILITY_UNPROVEN,
            "caller probe candidate does not match the authority-bearing commit",
        )
    probe_program = reachability_probe.signing_program
    if not probe_program:
        _fail(
            AuthorityErrorCode.AUTHORITY_REACHABILITY_UNPROVEN,
            "candidate reachability program is absent",
        )
    requested_program = Path(probe_program)
    if (
        requested_program.name == HARNESS_HELPER_NAME
        or (
            requested_program.exists()
            and Path(harness_program).exists()
            and requested_program.resolve() == Path(harness_program).resolve()
        )
    ):
        _fail(
            AuthorityErrorCode.HARNESS_KEY_PROVENANCE_ONLY,
            "the known harness signing program cannot establish authority",
        )
    independent_candidate = probe_anchor_reachability(
        signature.public_key,
        signing_program=probe_program,
    )
    if independent_candidate.reachable:
        _fail(
            AuthorityErrorCode.ANCHOR_REACHABLE,
            "candidate anchor produced a fabricated-author signature and is refused",
            probe=independent_candidate.to_dict(),
        )
    _fail(
        AuthorityErrorCode.AUTHORITY_REACHABILITY_UNPROVEN,
        (
            "a failed/unreachable Stage-1 candidate probe is not proof of "
            "authority; custody advancement requires a future attested stage"
        ),
        independent_positive_commit=positive.commit,
        candidate_probe=independent_candidate.to_dict(),
    )


def _custody_stage_implementation(stage: str) -> CustodyStageImplementation:
    implementation = CUSTODY_STAGE_IMPLEMENTATIONS.get(stage)
    if implementation is None:
        _fail(
            AuthorityErrorCode.CUSTODY_STAGE_INVALID,
            "unknown authority custody stage",
            stage=stage,
            allowed=sorted(CUSTODY_STAGE_IMPLEMENTATIONS),
        )
    return implementation


def validate_authority_claim_output(payload: Mapping[str, Any]) -> None:
    """Enforce one exact external claim schema across all custody stages."""

    actual_fields = set(payload)
    expected_fields = set(AUTHORITY_CLAIM_SCHEMA)
    if actual_fields != expected_fields:
        _fail(
            AuthorityErrorCode.CLAIM_SCHEMA_INVALID,
            "authority claim fields do not match the external contract",
            missing=sorted(expected_fields - actual_fields),
            extra=sorted(actual_fields - expected_fields),
        )
    required_strings = (
        "commit",
        "principal_uid",
        "principal_slug",
        "signature_key",
        "key_fingerprint",
        "key_custody",
    )
    if any(not isinstance(payload.get(field), str) or not payload[field] for field in required_strings):
        _fail(
            AuthorityErrorCode.CLAIM_SCHEMA_INVALID,
            "authority claim scalar fields must be non-empty strings",
        )
    if not isinstance(payload.get("authority"), bool):
        _fail(
            AuthorityErrorCode.CLAIM_SCHEMA_INVALID,
            "authority claim authority field must be boolean",
        )


def verify_stage_authority_claim(
    repo: Path,
    commit: str,
    principal_record: Mapping[str, Any],
    *,
    stage: str,
    custody_evidence: Mapping[str, str],
) -> AuthorityClaim:
    """Verify one custody-stage claim against fresh canonical principal state."""

    with authority_state_lock(repo):
        return _verify_stage_authority_claim_locked(
            repo,
            commit,
            principal_record,
            stage=stage,
            custody_evidence=custody_evidence,
        )


def _require_stage_signature_key_match(
    signature: CommitSignature,
    public_key: OpenSSHPublicKey,
    stage: str,
) -> None:
    if (
        public_key_from_blob(signature.key_blob).key_point
        != public_key.key_point
    ):
        _fail(
            AuthorityErrorCode.SIGNING_KEY_MISMATCH,
            "custody-stage commit was not signed by the principal key",
            stage=stage,
            expected_fingerprint=public_key.fingerprint,
            actual_fingerprint=signature.key_fingerprint,
        )


def _verify_stage_authority_claim_locked(
    repo: Path,
    commit: str,
    principal_record: Mapping[str, Any],
    *,
    stage: str,
    custody_evidence: Mapping[str, str],
) -> AuthorityClaim:
    """Exercise one real custody implementation without granting Stage-1 authority.

    This verifies the exact commit and principal key, then emits the stable
    consumer contract. Reachability/authority policy remains the responsibility
    of verify_authority_claim; this seam proves custody-stage invariance only.
    """

    implementation = _custody_stage_implementation(stage)
    signature = extract_commit_signature(repo, commit)
    activation_matches = [
        record
        for record in load_canonical_activation_entries(repo)
        if _activation_key_matches(record, signature.key_blob)
    ]
    if activation_matches:
        _fail(
            AuthorityErrorCode.AGENT_KEY_PROVENANCE_ONLY,
            "an activation-bound key cannot be relabeled as a custody-stage authority key",
            activation_uids=sorted(record.uid for record in activation_matches),
            stage=stage,
        )
    if set(custody_evidence) != {"stage", "proof"}:
        _fail(
            AuthorityErrorCode.CUSTODY_EVIDENCE_INVALID,
            "custody evidence must contain exactly stage and proof",
            stage=stage,
        )
    if (
        custody_evidence.get("stage") != stage
        or custody_evidence.get("proof") != implementation.required_proof
    ):
        _fail(
            AuthorityErrorCode.CUSTODY_EVIDENCE_INVALID,
            "custody evidence does not satisfy the selected stage implementation",
            stage=stage,
            expected_proof=implementation.required_proof,
        )
    supplied_uid = str(principal_record.get("uid") or "")
    canonical_matches = [
        principal
        for principal in load_principal_records(canonical_vault_files(repo))
        if str(principal.get("uid") or "") == supplied_uid
    ]
    if len(canonical_matches) != 1:
        _fail(
            AuthorityErrorCode.AUTHORITY_PRINCIPAL_INELIGIBLE,
            "custody-stage principal must resolve exactly once from canonical state",
            principal_uid=supplied_uid,
            matches=len(canonical_matches),
        )
    principal = canonical_matches[0]
    for field_name in (AUTHORITY_PUBLIC_KEY_FIELD, KEY_CUSTODY_FIELD):
        if principal_record.get(field_name) != principal.get(field_name):
            _fail(
                AuthorityErrorCode.CUSTODY_EVIDENCE_INVALID,
                "caller principal labels do not match canonical principal state",
                field=field_name,
                principal_uid=supplied_uid,
            )
    eligible = validate_authority_principals([principal])
    if len(eligible) != 1:
        _fail(
            AuthorityErrorCode.AUTHORITY_PRINCIPAL_INELIGIBLE,
            "custody-stage claim requires one eligible authority principal",
            stage=stage,
        )
    principal = eligible[0]
    if principal.get(KEY_CUSTODY_FIELD) != implementation.key_custody:
        _fail(
            AuthorityErrorCode.CUSTODY_EVIDENCE_INVALID,
            "principal custody does not match selected stage implementation",
            stage=stage,
            expected=implementation.key_custody,
            actual=principal.get(KEY_CUSTODY_FIELD),
        )
    public_key = parse_openssh_public_key(
        str(principal.get(AUTHORITY_PUBLIC_KEY_FIELD) or "")
    )
    _require_stage_signature_key_match(signature, public_key, stage)
    _verify_one_key(
        repo,
        signature,
        f"custody-{stage}-{str(principal.get('uid') or 'principal')}",
    )
    claim = AuthorityClaim(
        commit=signature.commit,
        principal_uid=str(principal.get("uid") or ""),
        principal_slug=str(
            principal.get("slug")
            or principal.get("name")
            or principal.get("uid")
            or ""
        ),
        signature_key=signature.public_key,
        key_fingerprint=signature.key_fingerprint,
        key_custody=implementation.key_custody,
        authority=False,
    )
    validate_authority_claim_output(claim.to_dict())
    return claim


def authority_claim_shape(principal_record: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the consumer shape shared by Stage 1/2/3 custody configurations."""

    validate_authority_principals([principal_record])
    return AUTHORITY_CLAIM_SCHEMA


__all__ = [
    "AUTHORITY_PUBLIC_KEY_FIELD",
    "AUTHORITY_CLAIM_SCHEMA",
    "AnchorClassification",
    "AuthorityChainError",
    "AuthorityClaim",
    "AuthorityErrorCode",
    "ActivationAnalysis",
    "ActivationRecord",
    "ActivationSigningBroker",
    "ChainResult",
    "CommitSignature",
    "CommitSignatureAudit",
    "CUSTODY_STAGE_IMPLEMENTATIONS",
    "CustodyStageImplementation",
    "Finding",
    "FROZEN_PRE_LINK_ACTIVATION_UIDS",
    "KEY_CUSTODY_FIELD",
    "MintedAgentKey",
    "OpenSSHPublicKey",
    "ReachabilityProbeResult",
    "SignedCommit",
    "activation_state_lock",
    "activation_signing_broker",
    "analyze_activations",
    "audit_commits_for_identity_collapse",
    "authority_claim_shape",
    "authority_state_lock",
    "canonical_git_identity",
    "canonical_vault_files",
    "cleanup_stale_agent_keypairs",
    "collect_commit_signatures",
    "derive_new_activation_predecessor",
    "derive_canonical_allowed_signers",
    "derive_allowed_signers",
    "detect_key_author_collapse",
    "discover_harness_signer",
    "extract_commit_signature",
    "load_activation_entries",
    "load_canonical_agent_classes",
    "load_canonical_agent_generations",
    "load_canonical_activation_entries",
    "load_principal_records",
    "mint_agent_keypair",
    "parse_frontmatter",
    "parse_openssh_public_key",
    "probe_anchor_reachability",
    "probe_anchor_with_positive_control",
    "probe_harness_anchor",
    "public_key_from_blob",
    "remove_agent_keypair",
    "resolve_commit_chain",
    "resolve_activation_activator",
    "session_key_root",
    "sign_commit",
    "validate_authority_principals",
    "validate_authority_claim_output",
    "verify_stage_authority_claim",
    "verify_authority_claim",
]
