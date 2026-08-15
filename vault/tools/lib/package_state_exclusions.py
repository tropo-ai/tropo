"""What is STATE and must never travel in a box or an update package.

talos-t40, 2026-08-09, velocity item 8 of the v1.86 retrospective ("state-files
exclusion rule"), grounded in cold-walk findings ae5e743c.

THE DISTINCTION THIS FILE EXISTS TO MAKE. A shipped file is one of two things:
the OS (the customer should get ours) or the studio's own state (the customer
must get theirs, or none). Nothing in the build knew the difference, so state
travelled — and state that travels does not merely leak, it OPERATES. A flag is
read by the machinery that wrote it, and it means the same thing in the
customer's studio as it did in ours.

MEASURED IN THE SHIPPED v1.86.0 PACKAGE, not hypothesised:

  - `.tropo/flags/attendant-mode-offered.flag` — the gate whose documented
    meaning (e9c2a7b3) is "the offer was made; do NOT repeat it". Shipping ours
    tells a brand-new studio that its owner has already been through onboarding,
    so Po never makes the offer. The newcomer path dies silently, which is the
    exact class ae5e743c was raised about.
  - `.tropo/flags/attendant-mode-enabled.flag` — Attendant Mode is ACTIVE.
    Shipping ours transplants a consent decision the customer never made, and
    their agents announce "Attendant Mode active" in the startup signal on the
    strength of it.
  - 22 dated `update-check-YYYY-MM-DD.flag` files — the daily update-discovery
    gate. A dated flag present for today makes the first agent of the day skip
    the remote manifest fetch. Ours are all past dates, so the live harm is
    bounded, but the mechanism is the same one and the dates are only past until
    a clock somewhere disagrees.
  - `vault/updates/updates-manifest.json` — the discovery manifest as a DEV copy
    that always names its own version current, so a box carrying it can conclude
    it is up to date without ever reaching the network. Named in ae5e743c
    finding 4 as compounding the missing update-source address.

THE RULE IS PATH-SHAPED, NOT NAME-SHAPED, and that is why it lives here rather
than in the build's existing basename exclusion list. `KERNEL_EXCLUDE_PATTERNS`
matches basenames, which cannot express "everything under .tropo/flags/" without
also matching any file anywhere that happens to contain the word.

WHAT IS DELIBERATELY NOT HERE. Derived index surfaces are already handled and
better: they are REGENERATED-class under the D9 apply rules, meaning the
post-apply rebuild is their sole writer. That is a stronger contract than
exclusion, so duplicating it here would be a second place for the same decision
to live and drift.
"""

from __future__ import annotations

from pathlib import PurePosixPath

#: Directory prefixes, relative to the studio root, that are wholly per-studio
#: runtime state.
STATE_DIR_PREFIXES: tuple[str, ...] = (
    ".tropo/flags/",
)

#: Path SEGMENTS that are machine-local build artifacts wherever they appear.
#: `__pycache__` is here on evidence: the shipped v1.86.0 manifest carries 26
#: operations adding `.tropo/scripts/**/__pycache__/*.cpython-313.pyc`, whose
#: source files are not in the package at all — so those operations could only
#: fail or no-op. They should never have been listed, and if a future package
#: were built from a tree that DID contain them, a customer would receive
#: bytecode compiled for someone else's interpreter version.
ARTIFACT_SEGMENTS: frozenset[str] = frozenset({"__pycache__", ".pytest_cache"})

#: Individual files that are per-studio state despite living beside OS content.
STATE_FILES: frozenset[str] = frozenset(
    {
        # Discovery manifest: a dev copy that names its own version current, so
        # a box carrying it can decide it is up to date offline (ae5e743c §4).
        "vault/updates/updates-manifest.json",
        # Argo's v2 event-cutover marker. Excluded from the kernel copy by
        # basename too (punch-list item 6); named here as well because the two
        # paths into a package are different code and only one of them had it.
        ".tropo/event-streams-v2.enabled",
        # Genesis identity: a box shipping ours makes customer genesis a silent
        # no-op, because mint is idempotent by design.
        ".tropo/studio-identity.md",
        # Build/publish handoff state, meaningless and misleading elsewhere.
        ".tropo/publish-pending.json",
    }
)


def _normalise(relative_path: str) -> str:
    """Drop a leading `./` and nothing else.

    Written as an explicit prefix strip because `lstrip("./")` strips CHARACTERS,
    not a prefix — it turns `.tropo/flags/x.flag` into `tropo/flags/x.flag`, and
    every rule below then misses. That was the first version of this function and
    the classification table caught it on the first run.
    """
    parts = [
        part
        for part in PurePosixPath(str(relative_path)).as_posix().split("/")
        if part not in ("", ".")
    ]
    return "/".join(parts)


def is_studio_state(relative_path: str) -> bool:
    """True when `relative_path` is this studio's state rather than the OS.

    `relative_path` is POSIX-style and relative to the studio root, matching how
    both the box builder and the update packager address files.
    """
    normalised = _normalise(relative_path)
    if normalised in STATE_FILES:
        return True
    if any(normalised.startswith(prefix) for prefix in STATE_DIR_PREFIXES):
        return True
    if ARTIFACT_SEGMENTS.intersection(normalised.split("/")):
        return True
    return normalised.endswith(".pyc")


def why_excluded(relative_path: str) -> str:
    """A reason a human can act on, for the manifest and for build output."""
    normalised = _normalise(relative_path)
    if normalised.startswith(".tropo/flags/"):
        return (
            "per-studio runtime flag: these are READ by the machinery that wrote "
            "them, so ours would operate in the customer's studio (the "
            "attendant-mode offer gate suppresses onboarding; a dated "
            "update-check flag suppresses discovery)"
        )
    if normalised == "vault/updates/updates-manifest.json":
        return (
            "dev copy of the discovery manifest that always names its own version "
            "current — a box carrying it can conclude it is up to date offline"
        )
    if normalised == ".tropo/event-streams-v2.enabled":
        return (
            "Argo's v2 cutover marker; its presence is an authenticated local "
            "contract pinned to entries that do not ship, so it BLOCKS customer "
            "emits rather than enabling them"
        )
    if normalised == ".tropo/studio-identity.md":
        return "genesis identity — shipping ours makes customer genesis a silent no-op"
    if normalised == ".tropo/publish-pending.json":
        return "build/publish handoff state, meaningless outside the studio that wrote it"
    if ARTIFACT_SEGMENTS.intersection(normalised.split("/")) or normalised.endswith(".pyc"):
        return (
            "machine-local build artifact: bytecode is compiled for one "
            "interpreter version, and the shipped v1.86.0 manifest already "
            "carried 26 operations pointing at .pyc sources the package did not "
            "contain"
        )
    return "per-studio state"
