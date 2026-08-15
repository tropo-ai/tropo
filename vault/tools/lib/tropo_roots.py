"""Canonical filesystem roots for Tropo release and publish tooling."""

from __future__ import annotations

from pathlib import Path


class TropoRootError(RuntimeError):
    """Raised when a path cannot be grounded in a marked Tropo Studio."""


def _has_studio_markers(candidate: Path) -> bool:
    return (candidate / ".tropo").is_dir() and (candidate / "vault").is_dir()


def resolve_studio_root(
    start: str | Path | None = None,
    *,
    override: str | Path | None = None,
) -> Path:
    """Return the nearest ancestor containing both Studio marker directories.

    ``start`` supports fixture trees and defaults to this module's location.
    ``override`` is an explicit root seam: unlike ``start``, it is checked as
    the root itself and is never searched upward.
    """

    if start is not None and override is not None:
        raise ValueError("start and override are mutually exclusive")

    if override is not None:
        candidate = Path(override).expanduser().resolve()
        if _has_studio_markers(candidate):
            return candidate
        raise TropoRootError(
            "explicit Studio root override does not contain both .tropo/ and "
            f"vault/: {candidate}"
        )

    origin = Path(__file__) if start is None else Path(start)
    resolved_origin = origin.expanduser().resolve()
    if not resolved_origin.exists():
        raise TropoRootError(
            f"cannot resolve Studio root from missing start path: {resolved_origin}"
        )
    cursor = resolved_origin.parent if resolved_origin.is_file() else resolved_origin
    for candidate in (cursor, *cursor.parents):
        if _has_studio_markers(candidate):
            return candidate
    raise TropoRootError(
        "could not find a Studio ancestor containing both .tropo/ and vault/ "
        f"from start path: {resolved_origin}"
    )


STUDIO_ROOT = resolve_studio_root()
VAULT_DIR = STUDIO_ROOT / "vault"
STUDIOS_HOME = STUDIO_ROOT.parent
DEV_HOME = STUDIOS_HOME.parent
RELEASES_DIR = DEV_HOME / "tropo-releases"
STAGED_CLONE_DIR = DEV_HOME / "tropo-staged-clone"


__all__ = [
    "DEV_HOME",
    "RELEASES_DIR",
    "STAGED_CLONE_DIR",
    "STUDIOS_HOME",
    "STUDIO_ROOT",
    "TropoRootError",
    "VAULT_DIR",
    "resolve_studio_root",
]
