#!/usr/bin/env python3
"""The four memory-surface filenames, in one place, tolerant of both names.

Phase 2 of the memory rebuild (dev-spec f0153a6df07f, Orpheus O38 → Talos)
renames four live surfaces so that one name means one thing at both scopes:

    agents/<slug>/.tropo-capsule/memory/agent-memory.md     -> memory.md
    agents/<slug>/.tropo-capsule/memory/agent-memories.jsonl -> memories.jsonl
    .tropo-studio/memory/memory-current.md                   -> memory.md
    .tropo-studio/memory/agent-memories.jsonl                -> memories.jsonl

The spec measured 171 call sites across 53 files, 38 of them not plain string
literals. Its step 1 is "teach every reader to resolve the new name and fall
back to the old, land it, tests green — nothing has moved yet, so nothing can
break." This module is where that resolution lives, once.

WHY A MODULE AND NOT A FALLBACK PER SITE. Thirty independent two-name fallbacks
are thirty places to update at step 5 and thirty chances to leave one behind —
the second-source-of-truth shape this rename exists to end, recreated inside the
rename itself. The spec names that trap twice (the two curator copies; the
absent key in the exclusion list). One producer, many callers.

WHAT STEP 5 DOES TO THIS FILE. Delete every *_LEGACY constant and the fallback
arm of `resolve`, leaving the canonical name. Every caller keeps working because
none of them names a file directly. That deletion is the commit that makes the
rename real and it is revertible on its own.

READERS ONLY, THROUGH STEP 1. Sites that CREATE a surface keep writing the
legacy name until step 2 moves the existing files, so the tree carries exactly
one convention at every commit. Those sites reference the *_LEGACY constants
explicitly and say so, which makes them greppable when step 2 flips them.

talos-t65, 2026-09-08.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

__all__ = [
    "AGENT_INDEX",
    "AGENT_INDEX_LEGACY",
    "AGENT_LOG",
    "AGENT_LOG_LEGACY",
    "STUDIO_INDEX",
    "STUDIO_INDEX_LEGACY",
    "STUDIO_LOG",
    "STUDIO_LOG_LEGACY",
    "AGENT_INDEX_NAMES",
    "AGENT_LOG_NAMES",
    "STUDIO_INDEX_NAMES",
    "STUDIO_LOG_NAMES",
    "ALL_INDEX_NAMES",
    "ALL_LOG_NAMES",
    "resolve",
    "agent_index",
    "agent_log",
    "studio_index",
    "studio_log",
    "agent_memory_dir",
    "is_index_name",
    "is_log_name",
]

# ── The canonical names, and the ones they replace ───────────────────────────
#: Boot-read at both scopes: an index of scored lines, each linking to a body.
AGENT_INDEX = "memory.md"
AGENT_INDEX_LEGACY = "agent-memory.md"
#: Append-only mid-session; never boot-read, at either scope.
AGENT_LOG = "memories.jsonl"
AGENT_LOG_LEGACY = "agent-memories.jsonl"

#: Studio scope lands on the SAME two names — that symmetry is the whole point
#: of the rename. Only the legacy names differ, and `memory-current.md` is why:
#: the same word meant "live" at studio scope and "retired" at agent scope,
#: which cost this crew a binding ruling for eight days and 35 dropped pins.
STUDIO_INDEX = AGENT_INDEX
STUDIO_INDEX_LEGACY = "memory-current.md"
STUDIO_LOG = AGENT_LOG
STUDIO_LOG_LEGACY = "agent-memories.jsonl"

#: Preference order: canonical first. Callers that match a filename against a
#: set (gates, matchers, scope rules) use these rather than a literal.
AGENT_INDEX_NAMES: tuple = (AGENT_INDEX, AGENT_INDEX_LEGACY)
AGENT_LOG_NAMES: tuple = (AGENT_LOG, AGENT_LOG_LEGACY)
STUDIO_INDEX_NAMES: tuple = (STUDIO_INDEX, STUDIO_INDEX_LEGACY)
STUDIO_LOG_NAMES: tuple = (STUDIO_LOG, STUDIO_LOG_LEGACY)

#: Every name that is an index / a log, at either scope. Order is preference,
#: and duplicates are collapsed while keeping it.
def _ordered_unique(names: Iterable) -> tuple:
    seen: list = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return tuple(seen)


ALL_INDEX_NAMES: tuple = _ordered_unique(AGENT_INDEX_NAMES + STUDIO_INDEX_NAMES)
ALL_LOG_NAMES: tuple = _ordered_unique(AGENT_LOG_NAMES + STUDIO_LOG_NAMES)


# ── Resolution ───────────────────────────────────────────────────────────────
def resolve(directory, names: Iterable, default: Optional[str] = None) -> Path:
    """The first name in `names` that EXISTS in `directory`.

    Existence decides, in preference order — deliberately not try-then-except,
    so a caller that counts reads sees the same number of them either way (the
    shape talos-t64 chose for the distiller's boot-blocking read, and the reason
    its pinned provenance fixture needed no edit).

    When neither exists the CANONICAL name comes back, so a caller reporting an
    absence names the file the studio is moving to rather than the one it is
    leaving. Nothing here creates anything.
    """
    directory = Path(directory)
    names = tuple(names)
    if not names:
        raise ValueError("resolve() needs at least one candidate name")
    for name in names:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return directory / (default if default is not None else names[0])


def agent_memory_dir(root, slug: str) -> Path:
    """`agents/<slug>/.tropo-capsule/memory/` — the folder is NOT renamed."""
    return Path(root) / "agents" / slug / ".tropo-capsule" / "memory"


def agent_index(root, slug: str) -> Path:
    return resolve(agent_memory_dir(root, slug), AGENT_INDEX_NAMES)


def agent_log(root, slug: str) -> Path:
    return resolve(agent_memory_dir(root, slug), AGENT_LOG_NAMES)


def studio_index(root) -> Path:
    return resolve(Path(root) / ".tropo-studio" / "memory", STUDIO_INDEX_NAMES)


def studio_log(root) -> Path:
    return resolve(Path(root) / ".tropo-studio" / "memory", STUDIO_LOG_NAMES)


def is_index_name(name) -> bool:
    """True for a memory INDEX filename at either scope, either era.

    For gates and scope rules that classify a path they were handed rather than
    resolving one. `name` may be a bare filename or a path.
    """
    return Path(str(name)).name in ALL_INDEX_NAMES


def is_log_name(name) -> bool:
    """True for a memory LOG filename at either scope, either era."""
    return Path(str(name)).name in ALL_LOG_NAMES
