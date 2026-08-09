"""Canonical raw-body and normalized-content hashes for Gardener Pruning.

The three text transforms are defined by vault entry 132fb547.  This module
implements only T1 (by wrapping the existing validator helper) and T2.  T3
match canonicalization is intentionally a separate Stage-C concern.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Union


PathLike = Union[str, Path]

_OPENING_FENCE = b"---\n"
_CLOSING_FENCE = b"\n---\n"
_NAV_BLOCK_RE = re.compile(
    rb"<!-- nav-block:start -->.*?<!-- nav-block:end -->",
    re.DOTALL,
)


class BodyBoundaryError(ValueError):
    """The governed Markdown frontmatter/body boundary is not unambiguous."""


@lru_cache(maxsize=1)
def _validator_module() -> ModuleType:
    """Load the existing T1 implementation without duplicating its transform."""
    validator_path = Path(__file__).resolve().parents[1] / "tropo-validate.py"
    spec = importlib.util.spec_from_file_location(
        "_tropo_validate_for_normalized_body_hash",
        validator_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Cannot load canonical T1 body hash from {validator_path}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "body_sha256", None)):
        raise RuntimeError(
            f"Canonical T1 body_sha256() is missing from {validator_path}"
        )
    return module


def raw_body_sha256(path: PathLike) -> str:
    """Return T1: the validator's canonical raw post-fence body hash."""
    return _validator_module().body_sha256(Path(path))


def _post_fence_body_bytes(path: PathLike) -> bytes:
    """Read post-frontmatter-fence bytes, refusing an ambiguous boundary."""
    file_path = Path(path)
    raw = file_path.read_bytes()
    if not raw.startswith(_OPENING_FENCE):
        raise BodyBoundaryError(
            f"{file_path}: no unambiguous opening frontmatter fence; "
            "cure: begin governed Markdown with an exact '---\\n' fence"
        )

    boundary = raw.find(_CLOSING_FENCE, len(_OPENING_FENCE) - 1)
    if boundary < 0:
        raise BodyBoundaryError(
            f"{file_path}: no unambiguous closing frontmatter fence; "
            "cure: terminate frontmatter with an exact '\\n---\\n' fence"
        )
    return raw[boundary + len(_CLOSING_FENCE):]


def normalized_body_bytes(path: PathLike) -> bytes:
    """Return T2 normalized content bytes, before SHA-256.

    Ordered pipeline (132fb547): post-fence bytes; nav-block strip; UTF-8
    decode with replacement; NFC; line-ending fold; per-line trailing
    whitespace strip; and exactly one trailing newline.
    """
    body = _post_fence_body_bytes(path)
    body = _NAV_BLOCK_RE.sub(b"", body)
    text = body.decode("utf-8", errors="replace")
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = text.rstrip("\n") + "\n"
    return text.encode("utf-8")


def normalized_body_sha256(path: PathLike) -> str:
    """Return T2: SHA-256 of canonical normalized content bytes."""
    return hashlib.sha256(normalized_body_bytes(path)).hexdigest()


__all__ = [
    "BodyBoundaryError",
    "normalized_body_bytes",
    "normalized_body_sha256",
    "raw_body_sha256",
]
