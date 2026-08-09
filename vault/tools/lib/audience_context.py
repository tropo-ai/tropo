"""B4a contextual audience resolution — the sole audience-policy adapter.

This module builds the verified segment/vault-to-manifest/audience bindings the
locked dev-spec (uid ``0bfa771d``) requires and exposes the *single* audience
policy adapter that replaces the production ``GroupLattice`` and
``default_two_segment_lattice()`` authority in every caller (mount, full
validation, check-one, Gardener, and cross-vault ``member_of``).

It is a pure library.  It parses no argv, opens no network connection, reads or
writes no filesystem, and hardcodes no absolute path.  Every input is injected:

* the verified compose-lock ``group_authority`` tuple (schema v2),
* the verified authority envelope / trust result
  (:class:`lib.group_authority.VerifiedAuthority`),
* per-mount ``manifest_sha256`` + ``resolved_audience_group_uid`` pins,
* the explicit legacy ``private -> mike`` binding, and
* the signed reserved ``os`` constant.

The three sibling libraries are composed, never reimplemented:

* :mod:`lib.group_contract` — ``GroupErrorCode`` / ``GroupContractError`` house
  error style and the closed refusal vocabulary;
* :mod:`lib.group_registry` — ``GroupResolver`` (``resolve_group`` /
  ``resolve_members`` / ``is_equal_or_wider`` / ``can_reference``) and the
  ``Result`` type;
* :mod:`lib.group_authority` — the verified authority tuple/envelope result,
  the fixed tuple/envelope key order, and the canonical audience-policy digest.

Two layers are kept deliberately separate, exactly as the dev-spec's
"Registry, resolver, and contextual audience" section states:

* :func:`validate_manifest_audience_shape` is a pure, independently-callable
  shape check: a manifest audience must be a single group UID and never an
  inline member list, a slug, ``team``/``team-def``, or a legacy alias.
* :class:`AudiencePolicy` performs *contextual* resolution, which additionally
  requires the manifest path, an :class:`AudienceContext`, and a
  ``GroupResolver``.

Every refusal is a typed :class:`~lib.group_contract.GroupContractError` drawn
from the closed vocabulary and is never degraded into empty membership or a
reason-free ``False``.  Missing or unverified bindings refuse; a default
lattice is never synthesized.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

# Ensure the shared ``lib`` namespace package resolves whether this module is
# imported as ``lib.audience_context`` (callers put ``vault/tools`` on the path)
# or loaded by file path (the paired unit test does this via importlib).  This
# uses only ``__file__``-relative resolution, never a hardcoded absolute path.
_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from lib.group_contract import GroupContractError, GroupErrorCode
from lib.group_registry import GroupResolver, Result
from lib.group_authority import (
    ENVELOPE_KEY_ORDER,
    TUPLE_KEY_ORDER,
    VerifiedAuthority,
    audience_policy_sha256,
    build_audience_policy,
    sha256_hex,
)


# ---------------------------------------------------------------------------
# Signed reserved constants and grammars
# ---------------------------------------------------------------------------
OS_AUDIENCE = "os"
PRIVATE_ALIAS = "private"

# Group UIDs are 8 lowercase hex (v1 identity, kept for governed groups).  Vault
# UIDs are the ADR-050 vault-code grammar ``^[a-z0-9]{4,6}$`` (locked
# architecture choice 1); the two grammars are length-disjoint.
GROUP_UID_RE = re.compile(r"^[0-9a-f]{8}$")
VAULT_UID_RE = re.compile(r"^[a-z0-9]{4,6}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")

# Audience shapes B4a removes: ``group`` extends ``core``, never ``team``,
# ``team-def``, or ``entity`` (dev-spec "Group contract"); ``team`` and
# unknown-UID acceptance are removed from the vault capsule.
REMOVED_AUDIENCE_TOKENS = frozenset(
    {"team", "team-def", "team_def", "teamdef", "entity", "core", "group"}
)


def _error(
    code: GroupErrorCode,
    message: str,
    *,
    field: str | None = None,
    reference_uid: str | None = None,
) -> GroupContractError:
    return GroupContractError(
        code, message, field=field, reference_uid=reference_uid
    )


def _raise(
    code: GroupErrorCode,
    message: str,
    *,
    field: str | None = None,
    reference_uid: str | None = None,
) -> None:
    raise _error(code, message, field=field, reference_uid=reference_uid)


# ---------------------------------------------------------------------------
# Per-mount audience binding
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MountAudienceBinding:
    """One mounted vault row's pinned audience binding.

    Per locked architecture choice 5, each mounted vault row pins
    ``manifest_sha256`` over exact manifest bytes at ``resolved_commit`` and
    ``resolved_audience_group_uid``.  ``vault_uid`` is the compose-lock map key
    (ADR-050 grammar); ``manifest_path`` is the corpus-root-relative POSIX path
    of that vault's manifest.
    """

    vault_uid: str
    manifest_path: str
    manifest_sha256: str
    resolved_audience_group_uid: str

    @classmethod
    def coerce(cls, value: "MountAudienceBinding | Mapping[str, Any]") -> "MountAudienceBinding":
        if isinstance(value, cls):
            binding = value
        elif isinstance(value, Mapping):
            required = (
                "vault_uid",
                "manifest_path",
                "manifest_sha256",
                "resolved_audience_group_uid",
            )
            missing = [key for key in required if key not in value]
            if missing:
                _raise(
                    GroupErrorCode.SEGMENT_BINDING_MISSING,
                    f"mount binding is missing required field(s) {', '.join(missing)}",
                )
            binding = cls(
                vault_uid=value["vault_uid"],
                manifest_path=value["manifest_path"],
                manifest_sha256=value["manifest_sha256"],
                resolved_audience_group_uid=value["resolved_audience_group_uid"],
            )
        else:
            _raise(
                GroupErrorCode.SEGMENT_BINDING_MISSING,
                "mount binding must be a MountAudienceBinding or a mapping",
            )
        binding._validate()  # type: ignore[union-attr]
        return binding

    def _validate(self) -> None:
        if not isinstance(self.vault_uid, str) or not VAULT_UID_RE.fullmatch(self.vault_uid):
            _raise(
                GroupErrorCode.SEGMENT_BINDING_MISSING,
                "mount vault_uid must match the ADR-050 vault-code grammar ^[a-z0-9]{4,6}$",
                reference_uid=self.vault_uid if isinstance(self.vault_uid, str) else None,
            )
        if (
            not isinstance(self.manifest_path, str)
            or not self.manifest_path
            or self.manifest_path.startswith("/")
            or "\\" in self.manifest_path
        ):
            _raise(
                GroupErrorCode.SEGMENT_BINDING_MISSING,
                f"mount {self.vault_uid} manifest_path must be a non-empty corpus-root-relative POSIX path",
                field="manifest_path",
            )
        if not isinstance(self.manifest_sha256, str) or not HASH_RE.fullmatch(self.manifest_sha256):
            _raise(
                GroupErrorCode.SEGMENT_BINDING_MISSING,
                f"mount {self.vault_uid} manifest_sha256 must be a 64-character lowercase hex digest",
                field="manifest_sha256",
            )
        if not isinstance(self.resolved_audience_group_uid, str) or not GROUP_UID_RE.fullmatch(
            self.resolved_audience_group_uid
        ):
            _raise(
                GroupErrorCode.SEGMENT_BINDING_MISSING,
                f"mount {self.vault_uid} resolved_audience_group_uid must be an 8-hex group UID",
                field="resolved_audience_group_uid",
                reference_uid=self.resolved_audience_group_uid
                if isinstance(self.resolved_audience_group_uid, str)
                else None,
            )


# ---------------------------------------------------------------------------
# A resolved audience
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolvedAudience:
    """A record's declared audience resolved to an active group or reserved OS.

    ``kind`` is ``"group"`` (``group_uid`` set to an active group) or ``"os"``
    (the signed reserved, always-readable top constant; ``group_uid`` is
    ``None``).  A refusal is never represented here — it is a typed
    :class:`~lib.group_registry.Result` failure.
    """

    declared: str
    kind: str
    group_uid: str | None


# ---------------------------------------------------------------------------
# Pure manifest-shape validation (no context, no resolver)
# ---------------------------------------------------------------------------
def validate_manifest_audience_shape(audience: object) -> str:
    """Check a manifest audience is a single group UID and return it.

    This is the pure, independently-callable shape layer.  It refuses — with
    ``GROUP_RESOLUTION_UNAVAILABLE`` — an inline member list, an inline object,
    a slug, a legacy alias (``private``/``os`` are record-level policy aliases,
    never a manifest's own audience), ``team``/``team-def``, or any other
    non-UID shape.  Contextual resolution (pin, freshness, active-group
    lookup) is handled separately by :class:`AudiencePolicy`.
    """

    if isinstance(audience, (list, tuple, set, frozenset)):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            "manifest audience must be a single group UID, not an inline member list",
            field="audience",
        )
    if isinstance(audience, Mapping):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            "manifest audience must be a single group UID, not an inline object",
            field="audience",
        )
    if not isinstance(audience, str):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"manifest audience must be a string group UID, got {type(audience).__name__}",
            field="audience",
        )
    token = audience.strip()
    if not token:
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            "manifest audience must not be blank",
            field="audience",
        )
    if token in (PRIVATE_ALIAS, OS_AUDIENCE):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"manifest audience must be a group UID, not the legacy alias {token!r}",
            field="audience",
        )
    if token in REMOVED_AUDIENCE_TOKENS:
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"manifest audience {token!r} is a removed audience shape (team/team-def/entity)",
            field="audience",
        )
    if not GROUP_UID_RE.fullmatch(token):
        _raise(
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            f"manifest audience {token!r} is not a single group UID (slug, unknown shape, or inline value)",
            field="audience",
            reference_uid=token,
        )
    return token


# ---------------------------------------------------------------------------
# The verified AudienceContext
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AudienceContext:
    """Immutable, verified audience bindings for one Studio compose lock.

    Constructed ONLY from verified inputs via :meth:`build`.  A missing or
    unverified binding refuses at construction; there is no default lattice.
    """

    authority_uid: str
    authority_generation: int
    corpus_revision: str
    corpus_sha256: str
    principal_directory_revision: str
    audience_policy_sha256: str
    private_alias_group_uid: str
    reserved_os_always_readable: bool
    _mounts_by_vault: Mapping[str, MountAudienceBinding]
    _mounts_by_path: Mapping[str, MountAudienceBinding]

    @classmethod
    def build(
        cls,
        *,
        group_authority: Mapping[str, Any],
        verified: VerifiedAuthority,
        private_alias_group_uid: str | None,
        reserved_os_always_readable: bool | None = None,
        mount_bindings: "object" = (),
    ) -> "AudienceContext":
        """Build a verified :class:`AudienceContext` or refuse.

        Refusals (each a typed :class:`~lib.group_contract.GroupContractError`):

        * ``AUTHORITY_UNTRUSTED`` — ``verified`` is not a verified authority
          result, or the compose-lock ``group_authority`` tuple disagrees with
          it (unexpected keys, a missing/mismatched tuple field, or a mismatched
          signature), or the reconstructed audience policy does not match the
          authority's signed ``audience_policy_sha256``;
        * ``SEGMENT_BINDING_MISSING`` — the legacy ``private -> group`` binding
          or the signed reserved ``os`` constant is missing/invalid, or a
          per-mount binding is malformed/duplicated.
        """

        if not isinstance(verified, VerifiedAuthority):
            _raise(
                GroupErrorCode.AUTHORITY_UNTRUSTED,
                "AudienceContext requires a verified authority envelope/trust result",
            )

        # The compose-lock group_authority tuple must be exactly the verified
        # envelope (schema v2 pins one tuple per Studio compose lock).
        if not isinstance(group_authority, Mapping):
            _raise(
                GroupErrorCode.AUTHORITY_UNTRUSTED,
                "compose-lock group_authority must be a mapping",
            )
        extra = set(group_authority.keys()) - set(ENVELOPE_KEY_ORDER)
        if extra:
            _raise(
                GroupErrorCode.AUTHORITY_UNTRUSTED,
                f"compose-lock group_authority has unexpected key(s): {', '.join(sorted(extra))}",
            )
        for key in TUPLE_KEY_ORDER:
            if key not in group_authority:
                _raise(
                    GroupErrorCode.AUTHORITY_UNTRUSTED,
                    f"compose-lock group_authority is missing tuple field {key!r}",
                )
            if group_authority[key] != getattr(verified, key):
                _raise(
                    GroupErrorCode.AUTHORITY_UNTRUSTED,
                    f"compose-lock group_authority field {key!r} disagrees with the verified authority",
                )
        if "signature" in group_authority and group_authority["signature"] != verified.signature:
            _raise(
                GroupErrorCode.AUTHORITY_UNTRUSTED,
                "compose-lock group_authority signature disagrees with the verified authority",
            )

        # The explicit legacy private -> mike binding and the signed reserved os
        # constant.  Omission refuses; a present-but-wrong binding is caught by
        # digest-matching it against the verified authority below.
        if private_alias_group_uid is None:
            _raise(
                GroupErrorCode.SEGMENT_BINDING_MISSING,
                "AudienceContext is missing the legacy private -> group binding",
            )
        if not isinstance(private_alias_group_uid, str) or not GROUP_UID_RE.fullmatch(
            private_alias_group_uid
        ):
            _raise(
                GroupErrorCode.SEGMENT_BINDING_MISSING,
                "legacy private binding must be an 8-hex group UID",
                reference_uid=private_alias_group_uid
                if isinstance(private_alias_group_uid, str)
                else None,
            )
        if reserved_os_always_readable is not True:
            _raise(
                GroupErrorCode.SEGMENT_BINDING_MISSING,
                "AudienceContext is missing the signed reserved os constant "
                "(reserved_os.always_readable must be true)",
            )

        # Bind the policy to the verified authority: reconstruct the exact
        # canonical audience-policy bytes and require the digest the signed
        # authority attests.  A binding the authority never signed is untrusted.
        policy_bytes = build_audience_policy(
            private_group_uid=private_alias_group_uid,
            reserved_os_always_readable=reserved_os_always_readable,
        )
        if audience_policy_sha256(policy_bytes) != verified.audience_policy_sha256:
            _raise(
                GroupErrorCode.AUTHORITY_UNTRUSTED,
                "reconstructed audience policy does not match the verified "
                "authority's signed audience_policy_sha256",
            )

        # Per-mount manifest_sha256 + resolved_audience_group_uid bindings.
        if isinstance(mount_bindings, Mapping):
            raw_bindings = list(mount_bindings.values())
        else:
            try:
                raw_bindings = list(mount_bindings)
            except TypeError:
                _raise(
                    GroupErrorCode.SEGMENT_BINDING_MISSING,
                    "mount_bindings must be an iterable of bindings or a mapping",
                )
        by_vault: dict[str, MountAudienceBinding] = {}
        by_path: dict[str, MountAudienceBinding] = {}
        for raw in raw_bindings:
            binding = MountAudienceBinding.coerce(raw)
            if binding.vault_uid in by_vault:
                _raise(
                    GroupErrorCode.SEGMENT_BINDING_MISSING,
                    f"duplicate mount binding for vault {binding.vault_uid}",
                    reference_uid=binding.vault_uid,
                )
            if binding.manifest_path in by_path:
                _raise(
                    GroupErrorCode.SEGMENT_BINDING_MISSING,
                    f"duplicate mount binding for manifest path {binding.manifest_path}",
                )
            by_vault[binding.vault_uid] = binding
            by_path[binding.manifest_path] = binding

        return cls(
            authority_uid=verified.authority_uid,
            authority_generation=verified.authority_generation,
            corpus_revision=verified.corpus_revision,
            corpus_sha256=verified.corpus_sha256,
            principal_directory_revision=verified.principal_directory_revision,
            audience_policy_sha256=verified.audience_policy_sha256,
            private_alias_group_uid=private_alias_group_uid,
            reserved_os_always_readable=True,
            _mounts_by_vault=MappingProxyType(by_vault),
            _mounts_by_path=MappingProxyType(by_path),
        )

    def mount_for_vault(self, vault_uid: object) -> MountAudienceBinding | None:
        if not isinstance(vault_uid, str):
            return None
        return self._mounts_by_vault.get(vault_uid)

    def mount_for_manifest_path(self, manifest_path: object) -> MountAudienceBinding | None:
        if not isinstance(manifest_path, str):
            return None
        return self._mounts_by_path.get(manifest_path)

    @property
    def mounts(self) -> tuple[MountAudienceBinding, ...]:
        return tuple(self._mounts_by_vault[key] for key in sorted(self._mounts_by_vault))

    def adapter(self, resolver: GroupResolver) -> "AudiencePolicy":
        """Bind this verified context to a resolver, producing the adapter."""

        return AudiencePolicy(self, resolver)


# ---------------------------------------------------------------------------
# The single audience-policy adapter
# ---------------------------------------------------------------------------
class AudiencePolicy:
    """The sole audience-policy adapter for all callers.

    Replaces the production ``GroupLattice`` / ``default_two_segment_lattice()``
    authority in mount, full validation, check-one, Gardener, and cross-vault
    ``member_of``.  Binds one verified :class:`AudienceContext` to one
    :class:`~lib.group_registry.GroupResolver` and answers every caller with the
    same typed :class:`~lib.group_registry.Result`.

    Every operation fails closed: an unavailable context/resolver refuses with
    ``GROUP_RESOLUTION_UNAVAILABLE`` and a resolver whose revision does not
    match the pinned corpus refuses with ``GROUP_CORPUS_STALE``, before any
    lookup.  A refusal is never an empty membership set or a bare ``False``.
    """

    __slots__ = ("_context", "_resolver")

    def __init__(self, context: AudienceContext, resolver: GroupResolver) -> None:
        self._context = context
        self._resolver = resolver

    @property
    def context(self) -> AudienceContext:
        return self._context

    @property
    def resolver(self) -> GroupResolver:
        return self._resolver

    # -- guards -------------------------------------------------------------
    def _guard(self) -> GroupContractError | None:
        if not isinstance(self._context, AudienceContext):
            return _error(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                "audience context is unavailable",
            )
        if not isinstance(self._resolver, GroupResolver):
            return _error(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                "group resolver is unavailable",
            )
        if self._resolver.revision != self._context.corpus_revision:
            return _error(
                GroupErrorCode.GROUP_CORPUS_STALE,
                f"registry revision {self._resolver.revision!r} does not match "
                f"pinned corpus revision {self._context.corpus_revision!r}",
            )
        return None

    def _resolve_group_uid(self, declared: str, group_uid: str) -> Result:
        outcome = self._resolver.resolve_group(group_uid)
        if not outcome.ok:
            # The resolver only holds active groups; an absent UID is unknown.
            return Result.failure(outcome.error)
        row = outcome.value
        status = row.get("status") if isinstance(row, Mapping) else None
        if status != "active":
            return Result.failure(
                _error(
                    GroupErrorCode.GROUP_INACTIVE,
                    f"group {group_uid} is {status!r}, not active",
                    reference_uid=group_uid,
                )
            )
        return Result.success(
            ResolvedAudience(declared=declared, kind="group", group_uid=group_uid)
        )

    # -- public adapter surface --------------------------------------------
    def resolve_audience(self, declared: object) -> Result:
        """Resolve a record's declared audience to an active group or reserved OS.

        A record's declared audience is a signed policy alias or a group UID.
        Per locked architecture choice 1, ``private`` and ``os`` are signed
        aliases, *not* vault UIDs, and a vault code is never itself a declared
        audience — a mounted vault's own audience is resolved separately by
        :meth:`resolve_vault_audience`.  Legacy ``private`` resolves to the
        pinned Mike group; the reserved ``os`` constant resolves to the
        always-readable top; an 8-hex group UID resolves directly.  Inline
        values, slugs, ``team``/``team-def``, unknown UIDs, inactive groups,
        stale authority, and unavailable context each refuse with a typed code.
        """

        err = self._guard()
        if err is not None:
            return Result.failure(err)
        if not isinstance(declared, str):
            return Result.failure(
                _error(
                    GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                    "audience must be a single group UID or signed alias, not an inline value",
                )
            )
        token = declared.strip()
        if not token:
            return Result.failure(
                _error(GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE, "audience must not be blank")
            )
        if token == OS_AUDIENCE:
            if self._context.reserved_os_always_readable is not True:
                return Result.failure(
                    _error(
                        GroupErrorCode.SEGMENT_BINDING_MISSING,
                        "reserved os constant is unavailable",
                    )
                )
            return Result.success(
                ResolvedAudience(declared=declared, kind="os", group_uid=None)
            )
        if token == PRIVATE_ALIAS:
            target = self._context.private_alias_group_uid
            if not target:
                return Result.failure(
                    _error(
                        GroupErrorCode.SEGMENT_BINDING_MISSING,
                        "legacy private binding is unavailable",
                    )
                )
            return self._resolve_group_uid(declared, target)
        if token in REMOVED_AUDIENCE_TOKENS:
            return Result.failure(
                _error(
                    GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                    f"audience {token!r} is a removed shape (team/team-def/entity)",
                )
            )
        if GROUP_UID_RE.fullmatch(token):
            return self._resolve_group_uid(declared, token)
        return Result.failure(
            _error(
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                f"audience {token!r} is not a group UID or signed alias "
                "(inline member, slug, vault code, or unknown shape)",
                reference_uid=token,
            )
        )

    def resolve_vault_audience(self, vault_uid: object) -> Result:
        """Resolve a mounted vault's own pinned audience to an active group.

        Distinct from :meth:`resolve_audience`: a vault code is not a record's
        declared audience but an identifier for a mounted vault whose audience
        is pinned per locked architecture choice 5
        (``resolved_audience_group_uid``).  This is the single place the
        cross-vault lane derives a vault's segment, so callers never restitch
        :meth:`AudienceContext.mount_for_vault` with :meth:`resolve_audience`
        and drift.  A code outside the ADR-050 grammar refuses with
        ``GROUP_RESOLUTION_UNAVAILABLE``; a mounted-but-unpinned vault refuses
        with ``SEGMENT_BINDING_MISSING``; an unknown or inactive pinned group
        refuses with ``GROUP_NOT_FOUND`` / ``GROUP_INACTIVE``.
        """

        err = self._guard()
        if err is not None:
            return Result.failure(err)
        code = vault_uid.strip() if isinstance(vault_uid, str) else vault_uid
        if not isinstance(code, str) or not VAULT_UID_RE.fullmatch(code):
            return Result.failure(
                _error(
                    GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                    "vault code must match the ADR-050 vault-code grammar ^[a-z0-9]{4,6}$",
                    reference_uid=code if isinstance(code, str) else None,
                )
            )
        binding = self._context.mount_for_vault(code)
        if binding is None:
            return Result.failure(
                _error(
                    GroupErrorCode.SEGMENT_BINDING_MISSING,
                    f"vault {code!r} has no pinned audience binding (unpinned)",
                    reference_uid=code,
                )
            )
        return self._resolve_group_uid(code, binding.resolved_audience_group_uid)

    def can_reference(self, source_audience: object, target_audience: object) -> Result:
        """Answer ``can_reference(source, target)`` via the injected resolver.

        True exactly when the target audience is equal to, or declared wider
        than, the source audience.  The reserved ``os`` top is wider than every
        audience (always readable), so any source may reference ``os`` and
        ``os`` may reference only ``os``.  Both audiences are resolved first, so
        a malformed or unresolvable side refuses rather than silently returning
        ``False``.
        """

        err = self._guard()
        if err is not None:
            return Result.failure(err)
        src = self.resolve_audience(source_audience)
        if not src.ok:
            return Result.failure(src.error)
        tgt = self.resolve_audience(target_audience)
        if not tgt.ok:
            return Result.failure(tgt.error)
        if tgt.value.kind == "os":
            return Result.success(True)
        if src.value.kind == "os":
            return Result.success(False)
        return self._resolver.can_reference(src.value.group_uid, tgt.value.group_uid)

    def resolve_manifest_audience(
        self,
        manifest_path: object,
        declared_audience: object,
        *,
        manifest_bytes: bytes | bytearray | None = None,
    ) -> Result:
        """Contextually resolve a manifest's declared audience to an active group.

        Requires the manifest path, this :class:`AudienceContext`, and a
        ``GroupResolver`` (the full contextual layer).  Returns the active group
        UID on success.  Refuses with the typed code for: shape violations
        (inline list, slug, ``team``/``team-def``) -> ``GROUP_RESOLUTION_UNAVAILABLE``;
        an unpinned manifest or a declared audience that is not the pinned
        ``resolved_audience_group_uid`` -> ``SEGMENT_BINDING_MISSING``; manifest
        bytes that do not match the pinned ``manifest_sha256`` or a stale
        resolver -> ``GROUP_CORPUS_STALE``; an unknown UID -> ``GROUP_NOT_FOUND``;
        an inactive group -> ``GROUP_INACTIVE``.
        """

        err = self._guard()
        if err is not None:
            return Result.failure(err)
        try:
            group_uid = validate_manifest_audience_shape(declared_audience)
        except GroupContractError as shape_error:
            return Result.failure(shape_error)

        binding = self._context.mount_for_manifest_path(manifest_path)
        if binding is None:
            return Result.failure(
                _error(
                    GroupErrorCode.SEGMENT_BINDING_MISSING,
                    f"manifest {manifest_path!r} has no pinned audience binding (unpinned)",
                )
            )
        if manifest_bytes is not None:
            if not isinstance(manifest_bytes, (bytes, bytearray)):
                return Result.failure(
                    _error(
                        GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                        "manifest bytes must be bytes for the manifest_sha256 pin check",
                    )
                )
            if sha256_hex(bytes(manifest_bytes)) != binding.manifest_sha256:
                return Result.failure(
                    _error(
                        GroupErrorCode.GROUP_CORPUS_STALE,
                        "manifest bytes do not match the pinned manifest_sha256",
                    )
                )
        if group_uid != binding.resolved_audience_group_uid:
            return Result.failure(
                _error(
                    GroupErrorCode.SEGMENT_BINDING_MISSING,
                    f"manifest audience {group_uid} is not the pinned "
                    f"resolved_audience_group_uid {binding.resolved_audience_group_uid}",
                    reference_uid=group_uid,
                )
            )
        resolved = self._resolve_group_uid(group_uid, group_uid)
        if not resolved.ok:
            return Result.failure(resolved.error)
        return Result.success(resolved.value.group_uid)


def resolve_manifest_audience(
    manifest_path: object,
    declared_audience: object,
    context: AudienceContext,
    resolver: GroupResolver,
    *,
    manifest_bytes: bytes | bytearray | None = None,
) -> Result:
    """Functional form of contextual manifest resolution.

    Mirrors the dev-spec's "Contextual validation requires manifest path,
    ``AudienceContext``, and ``GroupResolver``"; delegates to the single
    :class:`AudiencePolicy` adapter so callers cannot diverge.
    """

    return AudiencePolicy(context, resolver).resolve_manifest_audience(
        manifest_path, declared_audience, manifest_bytes=manifest_bytes
    )


__all__ = [
    "OS_AUDIENCE",
    "PRIVATE_ALIAS",
    "GROUP_UID_RE",
    "VAULT_UID_RE",
    "REMOVED_AUDIENCE_TOKENS",
    "MountAudienceBinding",
    "ResolvedAudience",
    "AudienceContext",
    "AudiencePolicy",
    "validate_manifest_audience_shape",
    "resolve_manifest_audience",
]
