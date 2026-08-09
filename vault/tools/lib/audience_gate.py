"""B4a strict-audience gate — the single on-disk integration seam.

The pure audience-policy *adapter* lives in :mod:`lib.audience_context`
(:class:`~lib.audience_context.AudiencePolicy`); the deterministic projector /
resolver live in :mod:`lib.group_registry`; the signed-authority verifier lives
in :mod:`lib.group_authority`.  Those three are already built and unit-tested.

What was missing — and what this module supplies — is the *glue* that lets every
production caller (``tropo-mount.py``, ``tropo-validate.py`` full + incremental,
``tropo-check-one.py``, the Gardener, and cross-vault ``member_of``) obtain the
*same* verified adapter from the Studio's on-disk state and route every audience
decision through it.  Without this glue each caller either reimplemented a
private lattice (the fail-open) or could not resolve at all.  This module is that
seam, so there is exactly ONE place the on-disk authority/registry become the
adapter and exactly ONE audience-policy authority (dev-spec ``0bfa771d`` §
"Registry, resolver, and contextual audience"; brief ``252534fe`` §4/§5).

Layout it reads (all corpus-root-relative POSIX, machine-local; written by
``tropo-group-authority install`` and ``tropo-rebuild-group-registry``):

* ``.tropo-studio/authorities/group-authority/installed.json`` — the pin;
* ``.tropo-studio/authorities/group-authority/generations/<uid>/<gen>/`` — the
  immutable signed generation (envelope + four canonical artifacts);
* ``.tropo-studio/trust/group-authorities.json`` — machine-local trust;
* ``.tropo-studio/registries/group-registry.jsonl`` — the canonical resolver
  query surface (this module also *projects* it), with the committed
  ``vault/00-group-registry.jsonl`` accepted as a fallback source.

Every refusal is a typed :class:`~lib.group_contract.GroupContractError` from the
closed vocabulary; a missing/unpinned/stale/tampered authority refuses and never
falls back to a synthesized lattice.  ``cutover_active`` lets callers keep their
pre-B4a behaviour until the named authority-installing update pins a tuple — the
dev-spec's "activate the strict cutover only in the named update that installs
its authority" mitigation — while :func:`check_manifest_audience` and
:class:`B4aLattice` are strict whenever a context exists.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Sequence

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from lib.audience_context import (  # noqa: E402
    OS_AUDIENCE,
    PRIVATE_ALIAS,
    AudienceContext,
    AudiencePolicy,
    MountAudienceBinding,
    validate_manifest_audience_shape,
)
from lib.group_authority import (  # noqa: E402
    AUDIENCE_POLICY_ARTIFACT,
    ARTIFACT_MANIFEST_ARTIFACT,
    CORPUS_ARTIFACT,
    PRINCIPAL_ARTIFACT,
    SIGNED_ENVELOPE_ARTIFACT,
    verify_authority,
    verify_principal_directory,
)
from lib.group_contract import (  # noqa: E402
    GroupContractError,
    GroupErrorCode,
    build_group_corpus,
    semantic_hash,
)
from lib.group_registry import (  # noqa: E402
    AuthorityRevisionContext,
    GroupResolver,
    RegistryProjection,
    RegistryWrapper,
    Result,
    build_parity_database,
    check_sqlite_parity,
    parse_registry_jsonl,
    project_registry,
)


# --------------------------------------------------------------------------- #
# On-disk layout (must match tropo-group-authority.py / rebuild tool).        #
# --------------------------------------------------------------------------- #
AUTHORITY_DIR = ".tropo-studio/authorities/group-authority"
INSTALLED_RELATIVE = AUTHORITY_DIR + "/installed.json"
TRUST_RELATIVE = ".tropo-studio/trust/group-authorities.json"

# The canonical resolver query surface this module projects and reads.  It lives
# beside the Studio's other committed registries (agent-registry, subsystem-
# registry) rather than under vault/, per brief 252534fe §4.
STUDIO_REGISTRY_RELATIVE = ".tropo-studio/registries/group-registry.jsonl"
STUDIO_REGISTRY_WRAPPER_RELATIVE = ".tropo-studio/registries/group-registry-wrapper.json"
STUDIO_REGISTRY_SQLITE_RELATIVE = ".tropo-studio/registries/group-registry.sqlite"
STUDIO_REGISTRY_LOCK_RELATIVE = ".tropo-studio/registries/.group-registry.lock"

# The committed portable registry the authority/rebuild tools publish; accepted
# as a fallback resolver source when the studio-local surface is absent.
COMMITTED_REGISTRY_RELATIVE = "vault/00-group-registry.jsonl"
COMMITTED_WRAPPER_RELATIVE = "vault/00-group-registry-wrapper.json"

# The Studio compose lock, sole writer of the pinned group_authority tuple.
COMPOSE_LOCK_RELATIVE = ".tropo-studio/compose.lock"

DEFAULT_SOURCE_DIR = "groups"

# type: registry wrapper record identity for the studio-local surface.
STUDIO_REGISTRY_TYPE = "registry"


def _raise(code: GroupErrorCode, message: str, **kwargs: Any) -> "None":
    raise GroupContractError(code, message, **kwargs)


def _read_bytes(path: Path) -> Optional[bytes]:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _read_json(path: Path) -> Optional[Any]:
    raw = _read_bytes(path)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"{path.name} is not valid JSON: {error}",
        )


# --------------------------------------------------------------------------- #
# Cutover state.                                                              #
# --------------------------------------------------------------------------- #
def cutover_active(root: os.PathLike | str) -> bool:
    """True iff a group authority is installed for this Studio.

    Callers gate strict enforcement on this so a Studio that has not yet applied
    the named authority-installing update keeps its pre-B4a behaviour, exactly as
    the dev-spec's cutover-only-in-the-update mitigation requires.  A malformed or
    partially-written pin counts as *not* active (fail closed to old behaviour,
    never fail open to a synthesized authority).
    """

    root = Path(root)
    pin = _read_bytes(root / INSTALLED_RELATIVE)
    if pin is None:
        return False
    try:
        obj = json.loads(pin.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(obj, dict) and isinstance(obj.get("authority_uid"), str)


# --------------------------------------------------------------------------- #
# The single adapter loader.                                                  #
# --------------------------------------------------------------------------- #
def _find_accepted_fingerprint(trust: Mapping[str, Any], signing_key_uid: str) -> str:
    keys = trust.get("accepted_keys") if isinstance(trust, Mapping) else None
    if isinstance(keys, list):
        for entry in keys:
            if isinstance(entry, Mapping) and entry.get("key_uid") == signing_key_uid:
                fp = entry.get("sha256_fingerprint")
                if isinstance(fp, str):
                    return fp
    _raise(
        GroupErrorCode.AUTHORITY_UNTRUSTED,
        f"no accepted trust fingerprint for signing key {signing_key_uid!r}",
    )


def _load_verified_authority(root: Path) -> "tuple[Any, Mapping[str, Any]]":
    """Return (VerifiedAuthority, signed_envelope_dict) from the installed pin."""

    pin = _read_json(root / INSTALLED_RELATIVE)
    if not isinstance(pin, dict):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            "no installed group authority (missing installed.json); resolution unavailable",
        )
    generation_dir = pin.get("generation_dir")
    if not isinstance(generation_dir, str):
        _raise(GroupErrorCode.AUTHORITY_UNTRUSTED, "installed pin has no generation_dir")
    gen = root / generation_dir

    envelope_bytes = _read_bytes(gen / SIGNED_ENVELOPE_ARTIFACT)
    if envelope_bytes is None:
        _raise(GroupErrorCode.AUTHORITY_UNTRUSTED, "installed generation is missing its signed envelope")
    artifacts: dict[str, bytes] = {}
    for name in (CORPUS_ARTIFACT, PRINCIPAL_ARTIFACT, AUDIENCE_POLICY_ARTIFACT, ARTIFACT_MANIFEST_ARTIFACT):
        data = _read_bytes(gen / name)
        if data is None:
            _raise(GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH, f"installed generation is missing {name}")
        artifacts[name] = data

    trust = _read_json(root / TRUST_RELATIVE)
    if not isinstance(trust, dict):
        _raise(GroupErrorCode.AUTHORITY_UNTRUSTED, "no machine-local trust record; authority is untrusted")

    try:
        envelope = json.loads(envelope_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GroupContractError(
            GroupErrorCode.AUTHORITY_TUPLE_MISMATCH,
            f"signed envelope is not valid JSON: {error}",
        ) from error
    signing_key_uid = envelope.get("signing_key_uid") if isinstance(envelope, dict) else None
    if not isinstance(signing_key_uid, str):
        _raise(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH, "signed envelope has no signing_key_uid")
    expected_fingerprint = _find_accepted_fingerprint(trust, signing_key_uid)

    verified = verify_authority(
        signed_envelope=envelope_bytes,
        artifacts=artifacts,
        trust_record=trust,
        expected_fingerprint=expected_fingerprint,
    )
    return verified, envelope


def _private_alias_from_policy(policy_bytes: bytes) -> str:
    try:
        obj = json.loads(policy_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GroupContractError(
            GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
            f"audience-policy.json is not valid JSON: {error}",
        ) from error
    aliases = obj.get("legacy_aliases") if isinstance(obj, dict) else None
    target = aliases.get(PRIVATE_ALIAS) if isinstance(aliases, Mapping) else None
    if not isinstance(target, str):
        _raise(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            "audience policy has no legacy private -> group binding",
        )
    return target


def _require_projection_derives_from_signed_corpus(root: Path, jsonl: bytes) -> None:
    """Bind the registry projection to the corpus the authority actually signed.

    The wrapper only proves the JSONL matches a digest THE WRAPPER ITSELF
    declares, and `expected_revision` only compares a `source_revision` field
    the same writer supplies. Neither reaches the signature, so appending a row
    and recomputing the wrapper admitted an unsigned group on every consumer --
    including a machine holding a valid trust record, because verifying the
    ENVELOPE never checked that the PROJECTION derived from it (finding
    000d9dad, demonstrated 2026-07-31).

    So re-derive the projection from the installed signed corpus artifact and
    require the surface being read to match it byte-for-byte. Fail closed.

    No installed authority means there is nothing to bind against; that state is
    already refused upstream by `cutover_active`, and this function must not
    invent a second, weaker gate for it.
    """

    pin = _read_json(root / INSTALLED_RELATIVE)
    if not isinstance(pin, dict):
        return
    generation_dir = pin.get("generation_dir")
    if not isinstance(generation_dir, str):
        _raise(GroupErrorCode.AUTHORITY_UNTRUSTED, "installed pin has no generation_dir")
    gen = root / generation_dir

    envelope = _read_json(gen / SIGNED_ENVELOPE_ARTIFACT)
    corpus_bytes = _read_bytes(gen / CORPUS_ARTIFACT)
    principal_bytes = _read_bytes(gen / PRINCIPAL_ARTIFACT)
    if not isinstance(envelope, dict) or corpus_bytes is None or principal_bytes is None:
        _raise(
            GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
            "installed generation is missing the artifacts its projection must derive from",
        )

    # The envelope's own claim about the corpus must hold before it can anchor
    # anything else.
    if hashlib.sha256(corpus_bytes).hexdigest() != envelope.get("corpus_sha256"):
        _raise(
            GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
            "installed signed corpus does not match the envelope's corpus digest",
        )

    groups: dict[str, Any] = {}
    for line in corpus_bytes.split(b"\n"):
        if not line:
            continue
        try:
            obj = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GroupContractError(
                GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
                f"signed corpus row is not valid JSON: {error}",
            ) from error
        if not isinstance(obj, dict) or not isinstance(obj.get("uid"), str):
            _raise(
                GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH,
                "signed corpus row is not a group object",
            )
        restored = dict(obj)
        restored["semantic_hash"] = semantic_hash(obj)
        groups[obj["uid"]] = restored

    corpus = build_group_corpus(groups, verify_principal_directory(principal_bytes))
    expected = project_registry(
        corpus,
        AuthorityRevisionContext(
            source_authority_uid=str(envelope.get("authority_uid") or ""),
            source_revision=str(envelope.get("corpus_revision") or ""),
            principal_directory_revision=str(
                envelope.get("principal_directory_revision") or ""
            ),
            source_paths={
                uid: f"{DEFAULT_SOURCE_DIR}/{uid}.json" for uid in corpus.active_uids
            },
        ),
    )
    if jsonl != expected.jsonl_bytes:
        _raise(
            GroupErrorCode.PROJECTION_MISMATCH,
            "registry projection does not derive from the installed signed corpus; "
            "it was edited, is stale, or belongs to a different authority generation",
        )


def load_resolver(root: os.PathLike | str, *, expected_revision: Optional[str] = None) -> GroupResolver:
    """Build a :class:`GroupResolver` from the canonical registry query surface.

    Reads ``.tropo-studio/registries/group-registry.jsonl`` (this module's
    canonical surface) when present, else the committed
    ``vault/00-group-registry.jsonl``.  The wrapper digest/row-count are verified;
    a stale revision (against ``expected_revision``) refuses ``GROUP_CORPUS_STALE``.
    """

    root = Path(root)
    jsonl = _read_bytes(root / STUDIO_REGISTRY_RELATIVE)
    wrapper_obj = _read_json(root / STUDIO_REGISTRY_WRAPPER_RELATIVE)
    if jsonl is None:
        jsonl = _read_bytes(root / COMMITTED_REGISTRY_RELATIVE)
        wrapper_obj = _read_json(root / COMMITTED_WRAPPER_RELATIVE)
    if jsonl is None:
        _raise(
            GroupErrorCode.GROUP_CORPUS_UNAVAILABLE,
            "no group-registry query surface available; resolution unavailable",
        )
    # The studio surface wraps the flat wrapper in a ``type: registry`` record;
    # the committed surface stores the flat wrapper directly. Accept both.
    wrapper = None
    if isinstance(wrapper_obj, dict):
        flat = wrapper_obj.get("wrapper") if isinstance(wrapper_obj.get("wrapper"), dict) else wrapper_obj
        wrapper = _wrapper_from_obj(flat)
    _require_projection_derives_from_signed_corpus(root, jsonl)
    return GroupResolver.from_jsonl(jsonl, wrapper=wrapper, expected_revision=expected_revision)


def load_policy(
    root: os.PathLike | str,
    *,
    mount_bindings: Sequence[MountAudienceBinding | Mapping[str, Any]] = (),
) -> AudiencePolicy:
    """Load THE audience-policy adapter for this Studio, or refuse.

    Verifies the installed signed authority against machine-local trust, binds the
    verified :class:`AudienceContext` (private->mike alias, reserved os, and any
    per-mount bindings), builds the :class:`GroupResolver` from the canonical
    registry surface pinned to the same corpus revision, and returns the single
    :class:`AudiencePolicy` adapter every caller shares.  Missing/untrusted/stale
    state refuses with a typed error; there is no synthesized fallback.
    """

    root = Path(root)
    verified, envelope = _load_verified_authority(root)

    # Recover the private->mike alias from the signed audience-policy artifact so
    # AudienceContext.build can re-derive and digest-match it to the authority.
    pin = _read_json(root / INSTALLED_RELATIVE) or {}
    generation_dir = pin.get("generation_dir")
    policy_bytes = _read_bytes(root / generation_dir / AUDIENCE_POLICY_ARTIFACT)
    if policy_bytes is None:
        _raise(GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH, "installed generation is missing audience-policy.json")
    private_alias = _private_alias_from_policy(policy_bytes)

    context = AudienceContext.build(
        group_authority=envelope,
        verified=verified,
        private_alias_group_uid=private_alias,
        reserved_os_always_readable=True,
        mount_bindings=mount_bindings,
    )
    resolver = load_resolver(root, expected_revision=verified.corpus_revision)
    return context.adapter(resolver)


# --------------------------------------------------------------------------- #
# Caller-facing strict manifest-audience check (mount + full/incremental        #
# validate + check-one all call THIS).                                         #
# --------------------------------------------------------------------------- #
def check_manifest_audience(
    policy: AudiencePolicy,
    manifest_path: str,
    declared_audience: object,
    *,
    manifest_bytes: bytes | bytearray | None = None,
) -> Result:
    """Contextually resolve a manifest audience through the one adapter.

    Thin, explicit forwarder so every caller resolves identically: shape refusals
    (inline list, slug, ``team``/``team-def``, alias) -> ``GROUP_RESOLUTION_UNAVAILABLE``;
    unpinned/mismatched binding -> ``SEGMENT_BINDING_MISSING``; stale pin/bytes ->
    ``GROUP_CORPUS_STALE``; unknown -> ``GROUP_NOT_FOUND``; inactive ->
    ``GROUP_INACTIVE``.  Returns the resolved active group UID on success.
    """

    if not isinstance(policy, AudiencePolicy):
        return Result.failure(
            GroupContractError(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                "audience policy adapter is unavailable",
            )
        )
    return policy.resolve_manifest_audience(
        manifest_path, declared_audience, manifest_bytes=manifest_bytes
    )


# --------------------------------------------------------------------------- #
# member_of lane: a GroupLattice-shaped, fail-closed adapter over the policy.  #
# --------------------------------------------------------------------------- #
class B4aLattice:
    """Duck-typed replacement for ``cross_vault_member_of.GroupLattice``.

    Presents the same ``is_legal_target`` / ``relation`` surface the member_of
    classifier consumes, but every answer is derived from the single
    :class:`AudiencePolicy` adapter (``can_reference``) — never a synthesized
    ``default_two_segment_lattice()``.  A record's *segment* is a declared audience
    (``private`` / ``os`` / an 8-hex group UID); ``can_reference(A, B)`` decides
    whether an edge from segment ``A`` to segment ``B`` is up-lattice-legal.

    Fail-closed discipline (dev-spec: errors are never a reason-free ``False``):
    an unresolved / inactive / stale / unavailable segment RAISES the typed
    :class:`GroupContractError` rather than silently classifying the edge illegal.
    Callers that must not raise can pre-resolve with :meth:`try_relation`.
    """

    __slots__ = ("_policy",)

    def __init__(self, policy: AudiencePolicy) -> None:
        if not isinstance(policy, AudiencePolicy):
            _raise(GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE, "B4aLattice requires a verified AudiencePolicy")
        self._policy = policy

    def _can_reference(self, source_segment: str, target_segment: str) -> bool:
        outcome = self._policy.can_reference(source_segment, target_segment)
        if not outcome.ok:
            raise outcome.error
        return bool(outcome.value)

    def is_legal_target(self, source_segment: str, target_segment: str) -> bool:
        """True iff ``target_segment`` is equal-or-wider than ``source_segment``."""

        return self._can_reference(source_segment, target_segment)

    def relation(self, source_segment: str, target_segment: str) -> str:
        """Classify the pair: ``'equal' | 'up' | 'down' | 'incomparable'``.

        Both directions are resolved through the adapter; a typed refusal on
        either side propagates (fail closed) rather than degrading to
        ``'incomparable'``.
        """

        if source_segment == target_segment:
            return "equal"
        forward = self._can_reference(source_segment, target_segment)
        backward = self._can_reference(target_segment, source_segment)
        if forward:
            return "up"
        if backward:
            return "down"
        return "incomparable"

    def try_relation(self, source_segment: str, target_segment: str) -> Result:
        """Non-raising form: returns a :class:`Result` carrying the relation string."""

        try:
            return Result.success(self.relation(source_segment, target_segment))
        except GroupContractError as error:
            return Result.failure(error)


# --------------------------------------------------------------------------- #
# Canonical studio-local registry projector (.tropo-studio/registries/).       #
# --------------------------------------------------------------------------- #
def _wrapper_from_obj(obj: Mapping[str, Any]) -> RegistryWrapper:
    try:
        return RegistryWrapper(
            jsonl_sha256=obj["jsonl_sha256"],
            row_count=obj["row_count"],
            canonicalization_version=obj["canonicalization_version"],
            source_authority_uid=obj["source_authority_uid"],
            source_revision=obj["source_revision"],
            principal_directory_revision=obj["principal_directory_revision"],
            producers=tuple(obj["producers"]),
            consumers=tuple(obj["consumers"]),
        )
    except (KeyError, TypeError) as error:
        raise GroupContractError(
            GroupErrorCode.PROJECTION_MISMATCH,
            f"registry wrapper is malformed: {type(error).__name__}",
        ) from error


def _studio_wrapper_record(wrapper: RegistryWrapper, *, last_derived_at: Optional[str]) -> bytes:
    """The governed ``type: registry`` wrapper record for the studio surface.

    A local non-comparison envelope: ``last_derived_at`` is freshness only (brief
    §4 — it never affects projection comparison), wrapped around the exact
    canonical wrapper object so the row-count + digest binding is preserved.
    """

    record = {
        "type": STUDIO_REGISTRY_TYPE,
        "registry": "group-registry",
        "path": STUDIO_REGISTRY_RELATIVE,
        "wrapper": wrapper.canonical_object(),
        "wrapper_sha256": wrapper.wrapper_sha256,
        "last_derived_at": last_derived_at,
    }
    return json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"), indent=2).encode("utf-8") + b"\n"


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


@contextmanager
def _registry_lock(root: Path, *, timeout_seconds: float) -> Iterator[Path]:
    lock_path = root / STUDIO_REGISTRY_LOCK_RELATIVE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    deadline = time.monotonic() + timeout_seconds
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for {lock_path}")
                time.sleep(0.02)
        yield lock_path
    finally:
        if acquired:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _load_active_corpus_from_sources(root: Path, source_dir: str, principals: Mapping[str, Mapping[str, Any]]):
    source_root = root / source_dir
    if not source_root.is_dir():
        _raise(GroupErrorCode.GROUP_CORPUS_UNAVAILABLE, f"group source directory not found: {source_dir}")
    groups: dict[str, dict[str, Any]] = {}
    for entry in sorted(source_root.glob("*.json")):
        obj = _read_json(entry)
        if not isinstance(obj, dict) or not isinstance(obj.get("uid"), str):
            _raise(GroupErrorCode.GROUP_SCHEMA_INVALID, f"group source {entry.name} is not a valid group object")
        uid = obj["uid"]
        if uid in groups:
            _raise(GroupErrorCode.GROUP_SCHEMA_INVALID, f"group uid {uid} appears in more than one source file", reference_uid=uid)
        groups[uid] = obj
    return build_group_corpus(groups, dict(principals))


def project_studio_registry(
    root: os.PathLike | str,
    *,
    source_dir: str = DEFAULT_SOURCE_DIR,
    last_derived_at: Optional[str] = None,
    lock_timeout: float = 60.0,
) -> RegistryProjection:
    """Project the canonical query surface into ``.tropo-studio/registries/``.

    Deterministic projection over the live active group sources under the installed
    authority pin: rows sort by ``group_uid``; every UID list is lexicographic;
    JSONL is canonical UTF-8/LF; the wrapper records row-count + SHA-256; SQLite is
    the row-equivalent acceleration mirror.  JSONL, the ``type: registry`` wrapper,
    and the SQLite mirror are swapped atomically under the registry lock.  Any
    JSONL<->SQLite disagreement refuses ``PROJECTION_MISMATCH`` (fail closed).

    Returns the :class:`RegistryProjection` (byte-identical across repeated runs
    over an unchanged corpus).
    """

    root = Path(root)
    pin = _read_json(root / INSTALLED_RELATIVE)
    if not isinstance(pin, dict):
        _raise(GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE, "no installed authority pin; cannot project registry")
    generation_dir = pin.get("generation_dir")
    if not isinstance(generation_dir, str):
        _raise(GroupErrorCode.AUTHORITY_UNTRUSTED, "installed pin has no generation_dir")
    principals_bytes = _read_bytes(root / generation_dir / PRINCIPAL_ARTIFACT)
    if principals_bytes is None:
        _raise(GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH, "installed generation is missing principals.jsonl")
    principals = {uid: dict(row) for uid, row in verify_principal_directory(principals_bytes).items()}

    authority_uid = pin.get("authority_uid")
    corpus_revision = pin.get("corpus_revision")
    pdr = pin.get("principal_directory_revision")
    for name, value in (
        ("authority_uid", authority_uid),
        ("corpus_revision", corpus_revision),
        ("principal_directory_revision", pdr),
    ):
        if not isinstance(value, str) or not value:
            _raise(GroupErrorCode.AUTHORITY_UNTRUSTED, f"installed pin field {name!r} is missing")

    corpus = _load_active_corpus_from_sources(root, source_dir, principals)
    context = AuthorityRevisionContext(
        source_authority_uid=authority_uid,
        source_revision=corpus_revision,
        principal_directory_revision=pdr,
        source_paths={uid: f"{source_dir}/{uid}.json" for uid in corpus.active_uids},
    )
    projection = project_registry(corpus, context)

    # Build + parity-check the SQLite mirror before publishing anything.
    tmp_db = Path(tempfile.mkdtemp(prefix=".gr-sqlite-")) / "registry.sqlite"
    try:
        connection = sqlite3.connect(str(tmp_db))
        try:
            build_parity_database(projection, connection)
            check_sqlite_parity(projection, connection)
        finally:
            connection.close()
        sqlite_bytes = tmp_db.read_bytes()
    finally:
        if tmp_db.exists():
            tmp_db.unlink()
        try:
            tmp_db.parent.rmdir()
        except OSError:
            pass

    with _registry_lock(root, timeout_seconds=lock_timeout):
        _atomic_write(root / STUDIO_REGISTRY_RELATIVE, projection.jsonl_bytes)
        _atomic_write(root / STUDIO_REGISTRY_SQLITE_RELATIVE, sqlite_bytes)
        _atomic_write(
            root / STUDIO_REGISTRY_WRAPPER_RELATIVE,
            _studio_wrapper_record(projection.wrapper, last_derived_at=last_derived_at),
        )
    return projection


def verify_studio_registry(root: os.PathLike | str) -> dict:
    """Prove the studio JSONL/wrapper/SQLite agree; refuse PROJECTION_MISMATCH."""

    root = Path(root)
    jsonl = _read_bytes(root / STUDIO_REGISTRY_RELATIVE)
    if jsonl is None:
        _raise(GroupErrorCode.GROUP_CORPUS_UNAVAILABLE, "no studio group-registry to verify")
    record = _read_json(root / STUDIO_REGISTRY_WRAPPER_RELATIVE)
    if not isinstance(record, dict) or not isinstance(record.get("wrapper"), dict):
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "studio registry wrapper is missing or malformed")
    wrapper = _wrapper_from_obj(record["wrapper"])
    rows = parse_registry_jsonl(jsonl)
    if hashlib.sha256(jsonl).hexdigest() != wrapper.jsonl_sha256:
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "studio registry JSONL digest disagrees with its wrapper")
    if len(rows) != wrapper.row_count:
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "studio registry row count disagrees with its wrapper")
    projection = RegistryProjection(
        jsonl_bytes=jsonl,
        rows=tuple(rows),
        wrapper=wrapper,
        source_authority_uid=wrapper.source_authority_uid,
        source_revision=wrapper.source_revision,
        principal_directory_revision=wrapper.principal_directory_revision,
    )
    sqlite_path = root / STUDIO_REGISTRY_SQLITE_RELATIVE
    if not sqlite_path.exists():
        _raise(GroupErrorCode.PROJECTION_MISMATCH, "studio registry SQLite mirror is missing")
    connection = sqlite3.connect(str(sqlite_path))
    try:
        check_sqlite_parity(projection, connection)
    finally:
        connection.close()
    return {
        "status": "verified",
        "row_count": wrapper.row_count,
        "registry_jsonl_sha256": wrapper.jsonl_sha256,
        "source_revision": wrapper.source_revision,
        "path": STUDIO_REGISTRY_RELATIVE,
    }


__all__ = [
    "AUTHORITY_DIR",
    "INSTALLED_RELATIVE",
    "TRUST_RELATIVE",
    "STUDIO_REGISTRY_RELATIVE",
    "STUDIO_REGISTRY_WRAPPER_RELATIVE",
    "STUDIO_REGISTRY_SQLITE_RELATIVE",
    "COMMITTED_REGISTRY_RELATIVE",
    "OS_AUDIENCE",
    "PRIVATE_ALIAS",
    "B4aLattice",
    "cutover_active",
    "check_manifest_audience",
    "load_policy",
    "load_resolver",
    "project_studio_registry",
    "verify_studio_registry",
    "validate_manifest_audience_shape",
]
