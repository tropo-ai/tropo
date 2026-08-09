"""Shared spec-family substrate-reference parser and exact identity matcher.

The contract is declared by dev-spec.capsule v1.5 and test-spec.capsule v1.2.
Classification is ordered and disjoint: UID, canonical Studio-relative path,
then opaque planned identifier.  This module is deliberately independent of
either validator so dev/test checks cannot grow different identity rules.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


UID_RE = re.compile(r"^[0-9a-f]{8}$")
ROOT_FILE_RE = re.compile(r"^[A-Za-z0-9._-]+\.[A-Za-z0-9]+$")
OPAQUE_RE = re.compile(r"^[a-z][a-z0-9.-]*$")


class SubstrateRefError(ValueError):
    """A substrate reference is not legal under the shared spec contract."""


@dataclass(frozen=True)
class SubstrateRef:
    kind: str
    value: str
    exists: bool = False


@dataclass(frozen=True)
class IndexIdentities:
    """Current-first current/archive identity projection."""

    uids: frozenset[str]
    uid_to_path: dict[str, str]


def _path_candidate(value: str, vault_root: Path) -> tuple[Path, str]:
    if value.startswith("/") or value.startswith("./"):
        raise SubstrateRefError("path must be Studio-relative with no leading '/' or './'")
    if "\\" in value:
        raise SubstrateRefError("path must use POSIX separators, not backslashes")
    if "\x00" in value:
        raise SubstrateRefError("path may not contain NUL")
    if any(ord(char) < 32 for char in value):
        raise SubstrateRefError("path may not contain control characters")
    if "//" in value:
        raise SubstrateRefError("path may not contain repeated separators")

    trailing_slash = value.endswith("/")
    path_text = value[:-1] if trailing_slash else value
    if not path_text:
        raise SubstrateRefError("path may not be empty")
    parts = path_text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise SubstrateRefError("path may not contain empty, '.' or '..' segments")

    root = Path(vault_root).resolve()
    candidate = root
    for component in parts:
        candidate = candidate / component
        try:
            is_symlink = candidate.is_symlink()
        except (OSError, UnicodeError) as exc:
            raise SubstrateRefError("path cannot be represented by the host filesystem") from exc
        if is_symlink:
            raise SubstrateRefError(
                f"path contains symlink component {component!r}"
            )
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise SubstrateRefError("path escapes the Studio root") from exc
    if resolved != candidate:
        raise SubstrateRefError("path is not a canonical Studio-relative identity")
    try:
        if trailing_slash and candidate.exists() and not candidate.is_dir():
            raise SubstrateRefError(
                "a trailing slash may declare only a directory boundary"
            )
    except (OSError, UnicodeError) as exc:
        raise SubstrateRefError("path cannot be inspected safely") from exc

    canonical = "/".join(parts) + ("/" if trailing_slash else "")
    if canonical != value:
        raise SubstrateRefError("path is not in canonical POSIX form")
    return candidate, canonical


def parse_substrate_ref(value: object, vault_root: Path) -> SubstrateRef:
    """Parse one ordered/disjoint substrate-ref or raise ``SubstrateRefError``."""

    if not isinstance(value, str):
        raise SubstrateRefError(
            f"substrate-ref must be a string, got {type(value).__name__}"
        )
    if not value or value != value.strip():
        raise SubstrateRefError(
            "substrate-ref must be non-empty with no surrounding whitespace"
        )

    if UID_RE.fullmatch(value):
        return SubstrateRef("uid", value)

    if "/" in value or ROOT_FILE_RE.fullmatch(value):
        candidate, canonical = _path_candidate(value, vault_root)
        try:
            exists = candidate.exists()
        except (OSError, UnicodeError) as exc:
            raise SubstrateRefError("path cannot be inspected safely") from exc
        return SubstrateRef("path", canonical, exists)

    if OPAQUE_RE.fullmatch(value):
        return SubstrateRef("opaque", value)

    raise SubstrateRefError(
        "substrate-ref is neither an 8-hex UID, canonical path/root-file, "
        "nor a lowercase opaque planned identifier"
    )


def load_index_identities(vault_root: Path) -> IndexIdentities:
    """Load current/archive UID identities; current rows win impossible duplicates."""

    root = Path(vault_root)
    uids: set[str] = set()
    uid_to_path: dict[str, str] = {}
    for name in ("00-index.jsonl", "00-archive-index.jsonl"):
        index_path = root / "vault" / name
        if not index_path.is_file():
            continue
        try:
            lines = index_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(row, dict):
                continue
            uid = row.get("uid")
            if not isinstance(uid, str) or not UID_RE.fullmatch(uid):
                continue
            uids.add(uid)
            if uid in uid_to_path:
                continue
            path_value = row.get("path")
            try:
                path_ref = parse_substrate_ref(path_value, root)
            except SubstrateRefError:
                continue
            if path_ref.kind == "path":
                uid_to_path[uid] = path_ref.value
    return IndexIdentities(frozenset(uids), uid_to_path)


def refs_match(
    left: SubstrateRef,
    right: SubstrateRef,
    identities: IndexIdentities,
) -> bool:
    """Exact identity only, plus current/archive UID-to-canonical-path equivalence."""

    if left.kind == right.kind:
        return left.value == right.value
    if left.kind == "uid" and right.kind == "path":
        return identities.uid_to_path.get(left.value) == right.value
    if left.kind == "path" and right.kind == "uid":
        return identities.uid_to_path.get(right.value) == left.value
    return False


def matching_declaration(
    ref: SubstrateRef,
    declarations: Iterable[tuple[SubstrateRef, str]],
    identities: IndexIdentities,
) -> tuple[SubstrateRef, str] | None:
    """Return the first exact/equivalent ``(declared_ref, change_class)`` match."""

    for declared_ref, change_class in declarations:
        if refs_match(ref, declared_ref, identities):
            return declared_ref, change_class
    return None
