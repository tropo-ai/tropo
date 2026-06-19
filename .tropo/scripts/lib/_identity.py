"""Shared principal identity resolver — engine + validator.

Extracted from vault/tools/9e7003b1.py (d996b941 verifier-independence L0c).

IMPORT DISCIPLINE: this module MUST be imported at module level in both engine
and validator. A silent ImportError degrades independence to always-pass —
the exact spoof the whole system prevents. Do NOT wrap in try/except at the
import site.
"""
from __future__ import annotations

from pathlib import Path


def _load_fm(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    try:
        import yaml as _yaml
        fm = _yaml.safe_load(text[4:end])
        return fm if isinstance(fm, dict) else None
    except Exception:
        return None


def _is_active_principal(fm: dict | None) -> bool:
    if not isinstance(fm, dict):
        return False
    if fm.get("type") not in ("principal", "human"):
        return False
    # v1.68 S1 tombstone pre-clear: recognize BOTH legacy shape (status:superseded)
    # AND post-relocation shape (state:archived + superseded_by) as inactive, so
    # relocated entries are correctly excluded after the status-leak migration runs.
    # status:archived removed from this check — post-migration it lives in state:archived.
    status = fm.get("status") or ""
    if status in ("superseded", "tombstone", "retired"):
        return False
    if fm.get("state") == "archived" and fm.get("superseded_by"):
        return False
    return True


def _resolve_principal_uid(actor: str, vault: Path) -> str | None:
    """Resolve an actor label to a canonical active type:principal vault UID.

    Exact name match + slug_aliases + supersedes/superseded_by chain follow.
    Returns the canonical principal UID, or None if unresolvable/superseded/not-registered.

    v1.66 S1: exact match only (no loose prefix); superseded_by chain follow;
    reject status:superseded/tombstone entries. d996b941 L0b: reads slug_aliases
    after exact-name match fails.
    """
    if not actor:
        return None

    files_dir = vault / "vault" / "files"

    # 1. Direct 8-hex UID lookup
    actor_lower = actor.lower()
    if len(actor) == 8 and all(c in "0123456789abcdef" for c in actor_lower):
        path = files_dir / f"{actor}.md"
        fm = _load_fm(path)
        if fm and _is_active_principal(fm):
            canon = fm.get("superseded_by")
            if canon:
                canon_fm = _load_fm(files_dir / f"{canon}.md")
                if canon_fm and _is_active_principal(canon_fm):
                    return str(canon)
            return actor
        return None  # UID present but not an active principal

    # 2. Exact name match + slug_aliases across type:principal vault entries
    for f in sorted(files_dir.glob("*.md")):
        try:
            snippet = f.read_text(encoding="utf-8", errors="replace")[:500]
        except OSError:
            continue
        if "principal" not in snippet:
            continue
        fm = _load_fm(f)
        if not _is_active_principal(fm):
            continue
        name = (fm.get("name") or "").lower()
        aliases = [str(a).lower() for a in (fm.get("slug_aliases") or [])]
        if name != actor_lower and actor_lower not in aliases:
            continue
        uid = fm.get("uid") or f.stem
        canon = fm.get("superseded_by")
        if canon:
            canon_fm = _load_fm(files_dir / f"{canon}.md")
            if canon_fm and _is_active_principal(canon_fm):
                return str(canon)
        return uid

    return None  # unresolvable — not a registered principal


def _get_principal_class(uid: str, vault: Path) -> str | None:
    """Return principal_class for a resolved principal UID, or None.

    Used to distinguish human principals (principal_class: human) from
    agent principals for verifier-independence exemption logic.
    """
    if not uid:
        return None
    path = vault / "vault" / "files" / f"{uid}.md"
    fm = _load_fm(path)
    if fm is None or not _is_active_principal(fm):
        return None
    return fm.get("principal_class")
