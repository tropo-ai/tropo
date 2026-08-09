"""Closed relation-predicate registry for Contract C0.

This module is deliberately data-only.  C0 record codecs, graph adapters, and
index consumers must import this one registry instead of maintaining parallel
predicate lists.
"""
from __future__ import annotations

from typing import Final


REGISTRY_ID: Final = "tropo.relation-registry/c0-v1"

# Order is the order locked in dev-spec 372ffdda.  It is registry order, not
# record order: records sort relation pairs by predicate and then target UID.
RELATION_PREDICATES: Final[tuple[str, ...]] = (
    "member_of",
    "refs",
    "governed_by",
    "composes_with",
    "superseded_by",
    "aligned_with",
    "calls",
    "subsystem_hub",
    "depends_on",
    "derived_from",
    "supersedes",
    "related_to",
)
RELATION_PREDICATE_SET: Final[frozenset[str]] = frozenset(
    RELATION_PREDICATES
)


def is_registered(predicate: object) -> bool:
    """Return whether *predicate* is one of the shipped C0 predicates."""

    return isinstance(predicate, str) and predicate in RELATION_PREDICATE_SET


def require_registered(predicate: object) -> str:
    """Return a registered predicate or raise ``ValueError``.

    The sidecar codec translates this small registry-level exception into its
    stable ``C0_RELATION_INVALID`` refusal.  Keeping this module independent of
    the codec avoids a dependency cycle.
    """

    if not is_registered(predicate):
        raise ValueError(f"unregistered C0 relation predicate: {predicate!r}")
    return predicate


__all__ = [
    "REGISTRY_ID",
    "RELATION_PREDICATES",
    "RELATION_PREDICATE_SET",
    "is_registered",
    "require_registered",
]
