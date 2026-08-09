"""Pure B4a governed-group semantics.

This module accepts already-parsed mappings.  It never parses YAML, reads or
writes the filesystem, publishes a registry, resolves authority, or contacts a
network service.  Callers inject the portable principal directory and complete
group corpus they want evaluated.

Canonical group semantics use the locked v1 key order, compact UTF-8 JSON, and
one trailing LF.  Public validation and resolver operations fail with
``GroupContractError`` carrying a closed ``GroupErrorCode``; errors are never
converted into empty membership or a reason-free ``False``.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any


SEMANTIC_KEYS = (
    "uid",
    "type",
    "slug",
    "title",
    "description",
    "owner",
    "members",
    "includes_groups",
    "status",
    "version",
)

UID_RE = re.compile(r"^[0-9a-f]{8}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
PRINCIPAL_CLASS_RE = re.compile(r"^(?:human|agent-[a-z0-9]+(?:-[a-z0-9]+)*)$")
VALID_STATUSES = frozenset({"draft", "active"})

_KNOWN_PLACEHOLDERS = frozenset(
    {
        "required-lowercase-kebab-case",
        "required-human-title",
        "required-purpose",
        "required-active-principal-uid",
    }
)


class GroupErrorCode(str, Enum):
    """Closed B4a refusal vocabulary.

    The authority and integration codes are included here so later B4a
    libraries can construct errors without opening a sibling vocabulary.
    This pure slice emits only the group/principal/schema subset.
    """

    GROUP_CORPUS_UNAVAILABLE = "GROUP_CORPUS_UNAVAILABLE"
    GROUP_CORPUS_STALE = "GROUP_CORPUS_STALE"
    GROUP_NOT_FOUND = "GROUP_NOT_FOUND"
    GROUP_INACTIVE = "GROUP_INACTIVE"
    GROUP_IMMUTABLE = "GROUP_IMMUTABLE"
    GROUP_SLUG_DUPLICATE = "GROUP_SLUG_DUPLICATE"
    GROUP_MEMBER_DUPLICATE = "GROUP_MEMBER_DUPLICATE"
    GROUP_INCLUDE_DUPLICATE = "GROUP_INCLUDE_DUPLICATE"
    GROUP_PLACEHOLDER = "GROUP_PLACEHOLDER"
    GROUP_SCHEMA_INVALID = "GROUP_SCHEMA_INVALID"
    GROUP_SEMANTIC_HASH_MISMATCH = "GROUP_SEMANTIC_HASH_MISMATCH"
    PRINCIPAL_UNRESOLVED = "PRINCIPAL_UNRESOLVED"
    GROUP_CYCLE = "GROUP_CYCLE"
    PROJECTION_MISMATCH = "PROJECTION_MISMATCH"
    GROUP_RESOLUTION_UNAVAILABLE = "GROUP_RESOLUTION_UNAVAILABLE"
    SEGMENT_BINDING_MISSING = "SEGMENT_BINDING_MISSING"
    AUTHORITY_UNTRUSTED = "AUTHORITY_UNTRUSTED"
    AUTHORITY_FINGERPRINT_MISMATCH = "AUTHORITY_FINGERPRINT_MISMATCH"
    AUTHORITY_SIGNATURE_INVALID = "AUTHORITY_SIGNATURE_INVALID"
    AUTHORITY_TUPLE_MISMATCH = "AUTHORITY_TUPLE_MISMATCH"
    AUTHORITY_ARTIFACT_MISMATCH = "AUTHORITY_ARTIFACT_MISMATCH"
    AUTHORITY_ROLLBACK = "AUTHORITY_ROLLBACK"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class GroupContractError(ValueError):
    """A deterministic, typed group-contract refusal."""

    def __init__(
        self,
        code: GroupErrorCode,
        message: str,
        *,
        group_uid: str | None = None,
        field: str | None = None,
        reference_uid: str | None = None,
        cycle: tuple[str, ...] = (),
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.group_uid = group_uid
        self.field = field
        self.reference_uid = reference_uid
        self.cycle = cycle


def _raise(
    code: GroupErrorCode,
    message: str,
    *,
    group_uid: str | None = None,
    field: str | None = None,
    reference_uid: str | None = None,
    cycle: tuple[str, ...] = (),
) -> None:
    raise GroupContractError(
        code,
        message,
        group_uid=group_uid,
        field=field,
        reference_uid=reference_uid,
        cycle=cycle,
    )


def _contains_lone_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def is_placeholder(value: object) -> bool:
    """Return whether a scalar is an unconsumed group-template placeholder."""

    if not isinstance(value, str):
        return False
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered in _KNOWN_PLACEHOLDERS or lowered.startswith("required-"):
        return True
    if "<<mint:" in lowered:
        return True
    if lowered.startswith("<!--") and "required" in lowered:
        return True
    return bool(
        stripped.startswith("<")
        and stripped.endswith(">")
        and any(token in lowered for token in ("required", "replace", "principal-uid"))
    )


def _require_mapping(value: object, *, subject: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            f"{subject} must be a mapping, got {type(value).__name__}",
        )
    return value


def _require_string(
    group: Mapping[str, Any],
    field: str,
    *,
    group_uid: str | None,
    allow_blank: bool = False,
) -> str:
    if field not in group:
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            f"group is missing required field {field!r}",
            group_uid=group_uid,
            field=field,
        )
    value = group[field]
    if not isinstance(value, str):
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            f"group field {field!r} must be a string, got {type(value).__name__}",
            group_uid=group_uid,
            field=field,
        )
    if _contains_lone_surrogate(value):
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            f"group field {field!r} contains a lone Unicode surrogate",
            group_uid=group_uid,
            field=field,
        )
    if is_placeholder(value):
        _raise(
            GroupErrorCode.GROUP_PLACEHOLDER,
            f"group field {field!r} contains an unconsumed placeholder",
            group_uid=group_uid,
            field=field,
        )
    if not allow_blank and not value.strip():
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            f"group field {field!r} must not be blank",
            group_uid=group_uid,
            field=field,
        )
    return value


def _require_uid(value: str, *, group_uid: str | None, field: str) -> str:
    if not UID_RE.fullmatch(value):
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            f"group field {field!r} must be an 8-character lowercase hexadecimal UID",
            group_uid=group_uid,
            field=field,
            reference_uid=value,
        )
    return value


def _require_uid_list(
    group: Mapping[str, Any],
    field: str,
    *,
    group_uid: str,
    non_empty: bool,
    duplicate_code: GroupErrorCode,
) -> list[str]:
    if field not in group:
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            f"group is missing required field {field!r}",
            group_uid=group_uid,
            field=field,
        )
    raw = group[field]
    if not isinstance(raw, (list, tuple)):
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            f"group field {field!r} must be an array",
            group_uid=group_uid,
            field=field,
        )
    if non_empty and not raw:
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            f"group field {field!r} must be non-empty",
            group_uid=group_uid,
            field=field,
        )

    values: list[str] = []
    seen: set[str] = set()
    for position, value in enumerate(raw):
        if not isinstance(value, str):
            _raise(
                GroupErrorCode.GROUP_SCHEMA_INVALID,
                f"group field {field!r} item {position} must be a string",
                group_uid=group_uid,
                field=field,
            )
        if _contains_lone_surrogate(value):
            _raise(
                GroupErrorCode.GROUP_SCHEMA_INVALID,
                f"group field {field!r} item {position} contains a lone Unicode surrogate",
                group_uid=group_uid,
                field=field,
            )
        if is_placeholder(value):
            _raise(
                GroupErrorCode.GROUP_PLACEHOLDER,
                f"group field {field!r} item {position} contains an unconsumed placeholder",
                group_uid=group_uid,
                field=field,
            )
        _require_uid(value, group_uid=group_uid, field=field)
        if value in seen:
            _raise(
                duplicate_code,
                f"group {group_uid} repeats {value} in {field}",
                group_uid=group_uid,
                field=field,
                reference_uid=value,
            )
        seen.add(value)
        values.append(value)
    return sorted(values)


def canonical_semantic_object(group: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new canonical semantic object without mutating ``group``.

    This performs local semantic shape validation, list sorting, duplicate
    checks, and self-inclusion refusal.  Principal and cross-group resolution
    require injected context and are handled by :func:`validate_group` and
    :func:`build_group_corpus`.
    """

    group = _require_mapping(group, subject="group")
    for key in group:
        if not isinstance(key, str):
            _raise(
                GroupErrorCode.GROUP_SCHEMA_INVALID,
                f"group mapping keys must be strings, got {type(key).__name__}",
            )
    raw_uid = group.get("uid")
    group_uid = raw_uid if isinstance(raw_uid, str) else None

    uid = _require_string(group, "uid", group_uid=group_uid)
    _require_uid(uid, group_uid=uid, field="uid")

    group_type = _require_string(group, "type", group_uid=uid)
    if group_type != "group":
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            "group field 'type' must be literal 'group'",
            group_uid=uid,
            field="type",
        )

    slug = _require_string(group, "slug", group_uid=uid)
    if not SLUG_RE.fullmatch(slug):
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            "group slug must be lowercase kebab-case",
            group_uid=uid,
            field="slug",
        )

    title = _require_string(group, "title", group_uid=uid)
    description = _require_string(group, "description", group_uid=uid)
    owner = _require_string(group, "owner", group_uid=uid)
    _require_uid(owner, group_uid=uid, field="owner")

    members = _require_uid_list(
        group,
        "members",
        group_uid=uid,
        non_empty=True,
        duplicate_code=GroupErrorCode.GROUP_MEMBER_DUPLICATE,
    )
    includes = _require_uid_list(
        group,
        "includes_groups",
        group_uid=uid,
        non_empty=False,
        duplicate_code=GroupErrorCode.GROUP_INCLUDE_DUPLICATE,
    )
    if uid in includes:
        cycle = (uid, uid)
        _raise(
            GroupErrorCode.GROUP_CYCLE,
            f"group {uid} includes itself",
            group_uid=uid,
            field="includes_groups",
            reference_uid=uid,
            cycle=cycle,
        )

    status = _require_string(group, "status", group_uid=uid)
    if status not in VALID_STATUSES:
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            "group status must be 'draft' or 'active'",
            group_uid=uid,
            field="status",
        )

    if "version" not in group:
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            "group is missing required field 'version'",
            group_uid=uid,
            field="version",
        )
    version = group["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            "B4a group version must be integer 1",
            group_uid=uid,
            field="version",
        )

    return {
        "uid": uid,
        "type": group_type,
        "slug": slug,
        "title": title,
        "description": description,
        "owner": owner,
        "members": members,
        "includes_groups": includes,
        "status": status,
        "version": version,
    }


def canonical_semantic_bytes(group: Mapping[str, Any]) -> bytes:
    """Serialize group semantics as compact UTF-8 JSON plus exactly one LF."""

    semantic = canonical_semantic_object(group)
    try:
        encoded = json.dumps(
            semantic,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            f"group semantic object is not canonical UTF-8 JSON: {type(error).__name__}",
            group_uid=semantic["uid"],
        )
    return encoded + b"\n"


def semantic_hash(group: Mapping[str, Any]) -> str:
    """Return lowercase SHA-256 over :func:`canonical_semantic_bytes`."""

    return hashlib.sha256(canonical_semantic_bytes(group)).hexdigest()


def verify_active_semantic_hash(group: Mapping[str, Any]) -> str:
    """Verify an active group's stored hash and return the expected digest."""

    group = _require_mapping(group, subject="group")
    semantic = canonical_semantic_object(group)
    uid = semantic["uid"]
    if semantic["status"] != "active":
        _raise(
            GroupErrorCode.GROUP_INACTIVE,
            f"group {uid} is not active",
            group_uid=uid,
            field="status",
        )
    stored = group.get("semantic_hash")
    expected = semantic_hash(semantic)
    if not isinstance(stored, str) or not HASH_RE.fullmatch(stored) or stored != expected:
        _raise(
            GroupErrorCode.GROUP_SEMANTIC_HASH_MISMATCH,
            f"group {uid} semantic_hash does not match canonical active semantics",
            group_uid=uid,
            field="semantic_hash",
        )
    return expected


def _resolve_principal(
    principal_uid: str,
    principals: Mapping[str, Mapping[str, Any]],
    *,
    group_uid: str,
    field: str,
) -> None:
    record = principals.get(principal_uid)
    if not isinstance(record, Mapping):
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            f"group {group_uid} {field} principal {principal_uid} is not in the portable directory",
            group_uid=group_uid,
            field=field,
            reference_uid=principal_uid,
        )
    if record.get("principal_uid") != principal_uid:
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            f"group {group_uid} {field} principal {principal_uid} has mismatched identity",
            group_uid=group_uid,
            field=field,
            reference_uid=principal_uid,
        )
    principal_class = record.get("principal_class")
    if (
        not isinstance(principal_class, str)
        or not PRINCIPAL_CLASS_RE.fullmatch(principal_class)
        or _contains_lone_surrogate(principal_class)
    ):
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            f"group {group_uid} {field} target {principal_uid} is not a portable principal",
            group_uid=group_uid,
            field=field,
            reference_uid=principal_uid,
        )
    if record.get("status") != "active":
        _raise(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            f"group {group_uid} {field} principal {principal_uid} is not active",
            group_uid=group_uid,
            field=field,
            reference_uid=principal_uid,
        )


def validate_group(
    group: Mapping[str, Any],
    principals: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate one group against an injected portable-principal mapping.

    The returned object is a new canonical semantic mapping.  Cross-group
    references, slug uniqueness, and cycles require :func:`build_group_corpus`.
    """

    principals = _require_mapping(principals, subject="portable principal directory")
    semantic = canonical_semantic_object(group)
    uid = semantic["uid"]

    _resolve_principal(semantic["owner"], principals, group_uid=uid, field="owner")
    for member_uid in semantic["members"]:
        _resolve_principal(member_uid, principals, group_uid=uid, field="members")

    if "semantic_hash" not in group:
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            "group is missing required field 'semantic_hash'",
            group_uid=uid,
            field="semantic_hash",
        )
    stored_hash = group["semantic_hash"]
    if semantic["status"] == "draft":
        if stored_hash is not None:
            _raise(
                GroupErrorCode.GROUP_SCHEMA_INVALID,
                f"draft group {uid} must have semantic_hash null",
                group_uid=uid,
                field="semantic_hash",
            )
    else:
        verify_active_semantic_hash(group)
    return semantic


def immutable_changed_fields(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return semantic fields changed between two canonical group snapshots."""

    before_semantic = canonical_semantic_object(before)
    after_semantic = canonical_semantic_object(after)
    return tuple(
        key
        for key in SEMANTIC_KEYS
        if before_semantic[key] != after_semantic[key]
    )


def assert_active_immutable(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> None:
    """Refuse any semantic change to an active group.

    Freshly recomputing the hash does not authorize mutation.  If semantics are
    unchanged, both stored hashes are still verified.
    """

    before_semantic = canonical_semantic_object(before)
    after_semantic = canonical_semantic_object(after)
    uid = before_semantic["uid"]
    if before_semantic["status"] != "active":
        _raise(
            GroupErrorCode.GROUP_INACTIVE,
            f"immutable comparison requires an active prior group, got {before_semantic['status']}",
            group_uid=uid,
            field="status",
        )
    changed = tuple(
        key
        for key in SEMANTIC_KEYS
        if before_semantic[key] != after_semantic[key]
    )
    if changed:
        _raise(
            GroupErrorCode.GROUP_IMMUTABLE,
            f"active group {uid} changed semantic fields: {', '.join(changed)}",
            group_uid=uid,
        )
    verify_active_semantic_hash(before)
    verify_active_semantic_hash(after)


def assert_group_transition(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    principals: Mapping[str, Mapping[str, Any]],
) -> None:
    """Validate the only B4a lifecycle transition.

    A draft may become active exactly once without changing any other semantic
    field.  An active snapshot may only be compared with an identical active
    snapshot.  Both snapshots are fully validated against the injected
    principal directory, including the active snapshot's semantic hash.
    """

    before_semantic = validate_group(before, principals)
    after_semantic = validate_group(after, principals)
    if before_semantic["status"] == "active":
        assert_active_immutable(before, after)
        return
    if after_semantic["status"] != "active":
        _raise(
            GroupErrorCode.GROUP_SCHEMA_INVALID,
            "B4a permits only the draft-to-active lifecycle transition",
            group_uid=before_semantic["uid"],
            field="status",
        )
    changed = tuple(
        key
        for key in SEMANTIC_KEYS
        if key != "status" and before_semantic[key] != after_semantic[key]
    )
    if changed:
        _raise(
            GroupErrorCode.GROUP_IMMUTABLE,
            "draft finalization changed semantic fields other than status: "
            + ", ".join(changed),
            group_uid=before_semantic["uid"],
        )


def _graph_order(
    groups: Mapping[str, Mapping[str, Any]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(cycle, child_first_order)`` without recursion."""

    state: dict[str, int] = {}
    child_first: list[str] = []

    for root_uid in sorted(groups):
        if state.get(root_uid, 0) != 0:
            continue
        path: list[str] = [root_uid]
        positions: dict[str, int] = {root_uid: 0}
        state[root_uid] = 1
        stack: list[tuple[str, int]] = [(root_uid, 0)]

        while stack:
            uid, child_index = stack[-1]
            children = groups[uid]["includes_groups"]
            if child_index < len(children):
                included_uid = children[child_index]
                stack[-1] = (uid, child_index + 1)
                included_state = state.get(included_uid, 0)
                if included_state == 1:
                    start = positions[included_uid]
                    return tuple(path[start:] + [included_uid]), ()
                if included_state == 0:
                    state[included_uid] = 1
                    positions[included_uid] = len(path)
                    path.append(included_uid)
                    stack.append((included_uid, 0))
                continue

            stack.pop()
            positions.pop(uid)
            path.pop()
            state[uid] = 2
            child_first.append(uid)

    return (), tuple(child_first)


def _freeze_semantic(semantic: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = dict(semantic)
    frozen["members"] = tuple(semantic["members"])
    frozen["includes_groups"] = tuple(semantic["includes_groups"])
    return MappingProxyType(frozen)


def _copy_semantic(semantic: Mapping[str, Any]) -> dict[str, Any]:
    copied = dict(semantic)
    copied["members"] = list(semantic["members"])
    copied["includes_groups"] = list(semantic["includes_groups"])
    return copied


@dataclass(frozen=True)
class GroupCorpus:
    """Validated immutable read model over active groups.

    ``includes_groups`` points from a wider group to groups it includes.
    Therefore strict wider ancestors are calculated through reverse edges,
    while effective members flow down the declared inclusion edges.
    """

    _all_groups: Mapping[str, Mapping[str, Any]]
    _active_groups: Mapping[str, Mapping[str, Any]]
    _effective_members: Mapping[str, tuple[str, ...]]
    _wider_ancestors: Mapping[str, tuple[str, ...]]

    @property
    def active_uids(self) -> tuple[str, ...]:
        """Return active resolver-visible group UIDs in lexical order."""

        return tuple(self._active_groups)

    def _require_active(self, group_uid: str) -> Mapping[str, Any]:
        if not isinstance(group_uid, str) or not UID_RE.fullmatch(group_uid):
            _raise(
                GroupErrorCode.GROUP_NOT_FOUND,
                "group UID is not a valid 8-character lowercase hexadecimal UID",
                reference_uid=group_uid if isinstance(group_uid, str) else None,
            )
        group = self._active_groups.get(group_uid)
        if group is not None:
            return group
        inactive = self._all_groups.get(group_uid)
        if inactive is not None:
            _raise(
                GroupErrorCode.GROUP_INACTIVE,
                f"group {group_uid} is {inactive['status']}, not active",
                group_uid=group_uid,
                field="status",
            )
        _raise(
            GroupErrorCode.GROUP_NOT_FOUND,
            f"group {group_uid} is not in the corpus",
            reference_uid=group_uid,
        )

    def resolve_group(self, group_uid: str) -> dict[str, Any]:
        """Return a detached canonical object for an active group."""

        return _copy_semantic(self._require_active(group_uid))

    def resolve_members(self, group_uid: str) -> tuple[str, ...]:
        """Return sorted, deduplicated transitive effective principal UIDs."""

        self._require_active(group_uid)
        return self._effective_members[group_uid]

    def strict_wider_ancestors(self, group_uid: str) -> tuple[str, ...]:
        """Return strict declared wider ancestors, excluding ``group_uid``."""

        self._require_active(group_uid)
        return self._wider_ancestors[group_uid]

    def is_equal_or_wider(
        self,
        candidate_wider_uid: str,
        candidate_narrower_uid: str,
    ) -> bool:
        """Return true only for equality or declared transitive containment."""

        self._require_active(candidate_wider_uid)
        self._require_active(candidate_narrower_uid)
        return (
            candidate_wider_uid == candidate_narrower_uid
            or candidate_wider_uid in self._wider_ancestors[candidate_narrower_uid]
        )

    def can_reference(
        self,
        from_audience_uid: str,
        to_audience_uid: str,
    ) -> bool:
        """Return true iff the target audience is equal to or wider than source."""

        return self.is_equal_or_wider(to_audience_uid, from_audience_uid)


def build_group_corpus(
    groups: Mapping[str, Mapping[str, Any]],
    principals: Mapping[str, Mapping[str, Any]],
) -> GroupCorpus:
    """Validate a complete corpus and derive its deterministic read model.

    ``groups`` must be keyed by each group's exact UID.  Drafts are validated
    and participate in global slug uniqueness, but are excluded from resolver
    results and may not be included by another group.
    """

    groups = _require_mapping(groups, subject="group corpus")
    principals = _require_mapping(principals, subject="portable principal directory")

    for key in groups:
        if not isinstance(key, str):
            _raise(
                GroupErrorCode.GROUP_SCHEMA_INVALID,
                f"group corpus keys must be strings, got {type(key).__name__}",
            )

    parsed: dict[str, dict[str, Any]] = {}
    for key in sorted(groups):
        raw_group = groups[key]
        semantic = validate_group(raw_group, principals)
        if semantic["uid"] != key:
            _raise(
                GroupErrorCode.GROUP_SCHEMA_INVALID,
                f"group corpus key {key} disagrees with embedded UID {semantic['uid']}",
                group_uid=semantic["uid"],
                field="uid",
                reference_uid=key,
            )
        parsed[key] = semantic

    slug_owner: dict[str, str] = {}
    for uid in sorted(parsed):
        slug = parsed[uid]["slug"]
        prior_uid = slug_owner.get(slug)
        if prior_uid is not None:
            _raise(
                GroupErrorCode.GROUP_SLUG_DUPLICATE,
                f"group slug {slug!r} is shared by {prior_uid} and {uid}",
                group_uid=uid,
                field="slug",
                reference_uid=prior_uid,
            )
        slug_owner[slug] = uid

    for uid in sorted(parsed):
        for included_uid in parsed[uid]["includes_groups"]:
            included = parsed.get(included_uid)
            if included is None:
                _raise(
                    GroupErrorCode.GROUP_NOT_FOUND,
                    f"group {uid} includes unknown group {included_uid}",
                    group_uid=uid,
                    field="includes_groups",
                    reference_uid=included_uid,
                )
            if included["status"] != "active":
                _raise(
                    GroupErrorCode.GROUP_INACTIVE,
                    f"group {uid} includes non-active group {included_uid}",
                    group_uid=uid,
                    field="includes_groups",
                    reference_uid=included_uid,
                )

    cycle, child_first_order = _graph_order(parsed)
    if cycle:
        _raise(
            GroupErrorCode.GROUP_CYCLE,
            "group inclusion cycle: " + " -> ".join(cycle),
            group_uid=cycle[0],
            field="includes_groups",
            reference_uid=cycle[-1],
            cycle=cycle,
        )

    active = {
        uid: parsed[uid]
        for uid in sorted(parsed)
        if parsed[uid]["status"] == "active"
    }

    effective_cache: dict[str, tuple[str, ...]] = {}
    for uid in child_first_order:
        if uid not in active:
            continue
        members = set(active[uid]["members"])
        for included_uid in active[uid]["includes_groups"]:
            members.update(effective_cache[included_uid])
        effective_cache[uid] = tuple(sorted(members))

    immediate_wider: dict[str, set[str]] = {uid: set() for uid in active}
    for wider_uid, semantic in active.items():
        for narrower_uid in semantic["includes_groups"]:
            immediate_wider[narrower_uid].add(wider_uid)

    wider_ancestors: dict[str, tuple[str, ...]] = {}
    for uid in active:
        seen: set[str] = set()
        pending = sorted(immediate_wider[uid], reverse=True)
        while pending:
            wider_uid = pending.pop()
            if wider_uid in seen:
                continue
            seen.add(wider_uid)
            pending.extend(sorted(immediate_wider[wider_uid], reverse=True))
        wider_ancestors[uid] = tuple(sorted(seen))

    frozen_all = MappingProxyType(
        {uid: _freeze_semantic(parsed[uid]) for uid in sorted(parsed)}
    )
    frozen_active = MappingProxyType(
        {uid: frozen_all[uid] for uid in sorted(active)}
    )
    return GroupCorpus(
        _all_groups=frozen_all,
        _active_groups=frozen_active,
        _effective_members=MappingProxyType(
            {uid: effective_cache[uid] for uid in sorted(effective_cache)}
        ),
        _wider_ancestors=MappingProxyType(
            {uid: wider_ancestors[uid] for uid in sorted(wider_ancestors)}
        ),
    )


__all__ = [
    "GroupContractError",
    "GroupCorpus",
    "GroupErrorCode",
    "SEMANTIC_KEYS",
    "assert_active_immutable",
    "assert_group_transition",
    "build_group_corpus",
    "canonical_semantic_bytes",
    "canonical_semantic_object",
    "immutable_changed_fields",
    "is_placeholder",
    "semantic_hash",
    "validate_group",
    "verify_active_semantic_hash",
]
