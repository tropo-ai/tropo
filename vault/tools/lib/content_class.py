"""One origin-evidence classifier for governed content admission and backfill."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional


CONTENT_CLASSES = frozenset(
    {
        "os-substrate",
        "studio-work",
        "imported-external",
        "federated-team",
        "unclassified",
    }
)


def infer_content_class(
    frontmatter: Mapping[str, Any],
    source_path: Path,
    vault_root: Path,
    *,
    local_studio_uid: Optional[str] = None,
) -> str:
    """Classify only from explicit origin evidence; unknown stays honest."""

    existing = frontmatter.get("content_class")
    if existing is not None:
        if not isinstance(existing, str) or existing not in CONTENT_CLASSES:
            raise ValueError(
                f"content_class must be one of {sorted(CONTENT_CLASSES)}"
            )
        return existing

    if (
        frontmatter.get("type") == "external-artifact"
        or str(frontmatter.get("extraction_scope") or "").casefold() == "external"
        or frontmatter.get("source_hash") not in (None, "")
    ):
        return "imported-external"

    foreign_studio = (
        frontmatter.get("source_studio_uid") or frontmatter.get("origin_studio")
    )
    if (
        isinstance(foreign_studio, str)
        and local_studio_uid is not None
        and foreign_studio != local_studio_uid
    ):
        return "federated-team"

    try:
        relative = source_path.resolve().relative_to(Path(vault_root).resolve())
    except ValueError:
        relative = source_path
    if relative.as_posix().startswith(
        (
            ".tropo/",
            "vault/tools/",
            "vault/capsules/",
            "vault/actions/",
            "vault/playbooks/",
            "vault/skills/",
            "vault/session-agents/",
        )
    ):
        return "os-substrate"

    if any(
        isinstance(frontmatter.get(field), str)
        and bool(str(frontmatter.get(field)).strip())
        for field in ("author", "created_by", "created_by_agent")
    ):
        return "studio-work"
    return "unclassified"
