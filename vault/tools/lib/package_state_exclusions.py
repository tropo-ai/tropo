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
    # F7 (5f75c7f3), vela-v73's classification 2026-08-24: 198 DERIVED
    # navigation files. Regenerable by nature and already gitignored as such in
    # this very repo. Excluded rather than replaced because tropo-apply-image.py
    # has no REGENERATED class today (confirmed in e843dedf) — when one exists,
    # these move to it. A prefix, not 198 entries: the nature is uniform.
    "00-tropo-nav/",
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
#: F7 (5f75c7f3) — the customer-state boundary, path -> why.
#:
#: The F1 fix made tropo-image-manifest.json COMPLETE, and apply derives its
#: replace-set from that manifest minus is_studio_state(). Before F1 the
#: incomplete manifest was an accidental shield; after it, a lift-and-replace
#: update would overwrite a recipient's own event log, memory surfaces and
#: registries with our bytes.
#:
#: CLASSIFIED BY vela-v73, 2026-08-24, VERIFIED NOT PATTERN-MATCHED: every path
#: below was diffed against the actual shipped genesis bytes of v1.91.0, never
#: judged by filename. That method is why the list is right. Her first pass read
#: mission-brief.md, operating-principles.md and the top-level CAPSULE.md as
#: generic doctrine — because what she had read earlier was THIS studio's
#: filled-in copy. The shipped ones open `<FILL: Your Studio Name>`, carry
#: `owner: vault-admin`, and carry a different uid entirely. She caught her own
#: reversal by reading the bytes.
#:
#: SIX SIBLINGS ARE DELIBERATELY ABSENT and stay in the replace set as genuine
#: OS doctrine: .tropo-studio/README.md, memory/three-instrument-verification.md,
#: and the directives/ memory/ registries/ runs/ CAPSULE.md files.
#:
#: The dict IS the membership list — STATE_FILES derives from it below. A second
#: list of the same paths is the defect this cycle exists to remove, and the
#: suite requires every excluded path to explain itself anyway.
F7_STATE_REASONS: dict[str, str] = {
    ".tropo-studio/CAPSULE.md":
        "per-studio governance: the customer's real owner, real write-access "
        "list and own uid — ours would overwrite who is allowed to write",
    ".tropo-studio/agent-boot.extension.md":
        "Tier-2 boot configuration, filled in per studio over time; replacing "
        "it silently changes how every one of their agents boots",
    ".tropo-studio/bindings/CAPSULE.md":
        "ships `status: reserved` and 'empty in the skeleton' — the customer "
        "populates it INSIDE the file, so this looks generic and is not (one "
        "of the two capsules that break the */CAPSULE.md pattern)",
    ".tropo-studio/directives/example.directive.md":
        "ships as a reference example whose own text invites 'keep it, amend "
        "it, or replace it' — an amended copy is the customer's content",
    ".tropo-studio/dirty-counter.json":
        "runtime counter of uncommitted files: stateful by nature even on the "
        "days its value happens to match ours",
    ".tropo-studio/gardener-wall-clock.json":
        "ships Argo's own private_ages keyed by Argo UIDs — F7's own finding, "
        "and decay signals about entries the customer does not have",
    ".tropo-studio/memory/MEMORY.md":
        "ships as a one-entry index saying 'add your own memories below'; "
        "replacing it deletes the crew memory index they built on it",
    ".tropo-studio/memory/entries/839a65f9.md":
        "an actual memory entry, not a template — a real pin the customer's "
        "agents read at boot",
    ".tropo-studio/memory/memory-current.md":
        "the customer's accumulated crew memory; overwriting it is the "
        "headline harm this boundary exists to prevent",
    ".tropo-studio/memory/short-term-memory.jsonl":
        "per-studio append-only memory log by nature; an append-only log that "
        "gets replaced has lost history no rebuild can restore",
    ".tropo-studio/mission-brief.md":
        "ships as `# Mission Brief — <FILL: Your Studio Name>`; a filled-in "
        "brief is the customer's own statement of what they are doing",
    ".tropo-studio/operating-principles.md":
        "ships with `owner: vault-admin` and placeholder dates; a studio's "
        "amended principles are governance they authored",
    ".tropo-studio/registries/agent-registry.yaml":
        "the customer's actual agent registry — replacing it unregisters "
        "every agent they commissioned",
    ".tropo-studio/registries/registry.jsonl":
        "the customer's actual registry data",
    ".tropo-studio/scripts/CAPSULE.md":
        "ships generic but the registry grows INLINE, so a studio's real owned "
        "tooling is declared in this file (the second of the two capsules that "
        "break the */CAPSULE.md pattern)",
    ".tropo-studio/shards/index-rebuild-run.json":
        "runtime rebuild state describing a rebuild that happened here",
    "vault/capsules/mint-registry.json":
        "the customer's own mint registry: overwriting it is a UID-COLLISION "
        "surface, which is worse than losing the file",
    "vault/events/00-events.jsonl":
        "the customer's actual event history — the concern F7 is named for, "
        "and append-only by contract",
}


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
        # NEVER-TOUCH (ea09fc6e AC5): harness configs are enumerated, never
        # predicate-derived. A silently reverting harness config is an
        # invisible failure that surfaces days later as unexplained agent
        # behavior — and a predicate ("harness config") would reintroduce
        # exactly the naming-predicate defect this enumeration exists to kill.
        ".claude/settings.json",
        ".gemini/settings.json",
        ".cursorrules",
    }
) | frozenset(F7_STATE_REASONS)


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
    f7 = F7_STATE_REASONS.get(normalised)
    if f7:
        return "customer state (F7, vela-v73 verified against shipped bytes): %s" % f7
    if normalised.startswith("00-tropo-nav/"):
        return (
            "derived navigation, regenerable by nature and gitignored as such "
            "in this very repo; excluded rather than replaced because apply has "
            "no REGENERATED class yet — when one exists these move to it"
        )
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
    if normalised in {".claude/settings.json", ".gemini/settings.json", ".cursorrules"}:
        return (
            "harness configuration owned by the operator, never by the OS: it is "
            "never shipped, never replaced and never deleted, because a silently "
            "reverting harness config is an invisible failure that surfaces days "
            "later as unexplained agent behavior with no event to trace it to "
            "(ea09fc6e never-touch class, Mike-ruled 2026-08-21)"
        )
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
