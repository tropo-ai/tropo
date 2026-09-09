#!/usr/bin/env python3
"""Governed filenames and index-free UID resolution (dev-spec 74f85939).

A governed Markdown file is named `<slug>-<uid>.md` when it has a usable title
and `<uid>.md` when it does not. The UID is always the anchored suffix; the slug
in front of it is decoration for humans and markdown viewers, and nothing may
treat it as identity.

WHY RESOLUTION IS A DIRECTORY SCAN AND NEVER THE INDEX.

The boot digest has promised for months that "the UID is the address, so renames
never break links." For a markdown relative link that is false: the FILENAME is
the address, so a retitle breaks every inbound link. This module is what makes
the promise true — it finds a file by its UID whatever the slug in front of it
says, so a rename costs nothing.

Doing that through the index would be the wrong trade. On 2026-08-07 this
studio's index refused every write for hours (P0 254a360b); if opening a
governed file had required it, there would have been no vault left to repair it
with. So resolution reads directories, and both the suite and `tropo-validate`
enforce that this file imports nothing from the index.

THE NAME PROPOSES; THE FRONTMATTER DECIDES. Every candidate — literal, exact
`<uid>.md`, or anchored `<slug>-<uid>.md` — must declare the requested UID in
valid CLOSED frontmatter before it is returned. A filename is a claim, and the
one place a governed file states its own identity is its frontmatter.
(Argus A145 review, 2026-08-08: the exact-match path skipped this and was a P0.)

RESOLUTION IS PATH-CONTAINED. UID shape is validated, `home` must be a declared
governed home, and every candidate is canonicalized and confirmed to sit inside
the home it was found in. Symlinks that escape are refused. Platform routes will
pass user-controlled identifiers into this function, and without containment
that is a local-file-disclosure surface rather than a resolver.

The TypeScript adapter at tropo-app/lib/governed-path.ts implements the same
observable behaviour. Neither is the other's oracle: both execute
vault/tools/tests/fixtures/governed-path-vectors.json.
"""

from __future__ import annotations

import json
import re
import secrets
from pathlib import Path

#: Every governed home with an active writer. Existing files never move; these
#: are the directories a UID may be found in, and the only values `home` accepts.
GOVERNED_HOMES: tuple[str, ...] = (
    "vault/files",
    "vault/agents",
    "vault/playbooks",
    "vault/skills",
    "vault/session-agents",
)

SLUG_MAX = 60

#: Portable, fail-closed. Writers consult it; resolvers never do.
FLAG_PATH = ".tropo-studio/readable-filenames.json"

#: Whitespace is enumerated rather than delegated to `\s`, because the two
#: languages disagree about it. Python's `\s` matches U+0085 (NEL); JavaScript's
#: also matches U+FEFF. `str.strip()` and `String.trim()` differ again. Any of
#: those divergences would make one adapter slug a title differently from the
#: other while both suites stayed green on every ASCII vector — so the class is
#: written out once, identically, in both files. (Argus A145 review.)
_WS = r"[ \t\n\r\f\v\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"

_TO_HYPHEN = re.compile(rf"(?:{_WS}|_)+")
_DROP = re.compile(r"[^a-z0-9-]+")
_COLLAPSE = re.compile(r"-{2,}")

#: A UID is an identifier, never a path fragment. This shape admits bare hex and
#: federated `<studio>-<hex>` and admits no separator, dot, or traversal.
_UID_OK = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")
_UID_MAX = 64


# --------------------------------------------------------------------------- #
# The shape authority (3d430852; width flexibility f015b5322af8).
#
# History is append-only: existing identities remain first-class forever.
# The last entry controls new mints; every entry remains readable. A future
# width change also needs the kernel/TypeScript parity gates to pass before
# rollout. This change leaves the production width at 12.
# --------------------------------------------------------------------------- #

MINT_HEX_HISTORY: tuple[int, ...] = (8, 12)
MINT_HEX_LEN = MINT_HEX_HISTORY[-1]
UID_SHAPES: frozenset[int] = frozenset(MINT_HEX_HISTORY)

_BARE_HEX_RE = re.compile(r"^[0-9a-f]+$")


def uid_shape(uid: str) -> int | None:
    """Which governed flat-hex shape a UID takes, or None.

    Federated `studio-hex` identities resolve through the anchored-suffix rule
    (the hex tail carries the shape), so they are handled by
    `parse_anchored_uid`, not by this predicate.
    """
    if not isinstance(uid, str) or not _BARE_HEX_RE.fullmatch(uid):
        return None
    return len(uid) if len(uid) in UID_SHAPES else None


#: The governed-uid HEX PATTERN, derived from UID_SHAPES rather than written.
#: For the regex sites that must capture a uid inside a larger expression and
#: therefore cannot call ``is_governed_uid_shape``. Interpolate this instead of
#: typing a length -- a regex site is still a reader of the shape fact, and the
#: whole point of the authority is that the fact has exactly one home.
#:
#: THIS IS FOR EXTRACTION, NOT ADMISSION: use it to find uid-shaped text
#: inside a larger document (a frontmatter field, a log line, a directory
#: name) where a false positive is safe because the caller validates the
#: captured value downstream. Its case-insensitive ``[0-9a-fA-F]`` is
#: correct for that job. Never use it to DECIDE whether a value already in
#: hand is a governed uid -- that is admission, and admission belongs to
#: ``is_governed_uid_shape`` below, whose exact (lowercase-only) match a
#: case-mismatched uid must fail. Added 2026-09-01 by talos-t58, after two
#: admission sites that had wrongly reused this pattern instead of the
#: predicate each resolved an uppercase uid to a real file via a case-
#: insensitive filesystem -- confirmed live, not theoretical (argus-a166's
#: release-gate negative-control ask).
#:
#: Added 2026-09-01 by argus-a165, after tropo-lineage.py was found carrying
#: ``[0-9a-fA-F]{8}`` in resolve_entry(): any agent minted after the Stage B flip
#: has a composite agent_uid, so resolve_entry returned None and the lineage tool
#: could not find that agent's own identity entry at all. Cal and Darin are
#: minted exactly that way at genesis.
UID_HEX_PATTERN = "|".join(
    "[0-9a-fA-F]{%d}" % n for n in sorted(UID_SHAPES, reverse=True)
)

def is_governed_uid_shape(uid: str) -> bool:
    """Accepts-both: the predicate every enumerated reader, gate, and writer
    routes through from Stage A. Local hex-length literals die here.

    THIS IS FOR ADMISSION, NOT EXTRACTION: call it to decide whether a value
    already in hand IS a governed uid -- an identity check, a dict-key
    lookup, a file resolution. Its exact (lowercase-only) match is the
    point: a case-mismatched value must fail here, never be treated as the
    same identity as its real lowercase-minted form. Use UID_HEX_PATTERN
    above instead when the job is finding uid-shaped text inside a larger
    document; its looser, case-insensitive match is correct there because a
    false positive gets validated downstream, which admission cannot afford.
    """
    return uid_shape(uid) is not None


def is_legacy_uid(uid: str) -> bool:
    """The legacy 8-hex shape — first-class forever, never migrated."""
    return uid_shape(uid) == 8


def new_uid_is_valid_shape(uid: str) -> bool:
    """What a FRESHLY MINTED uid must satisfy: the current generation shape.
    Stage A this equals legacy (len == MINT_HEX_LEN == 8); Stage B it is 12.
    Existing records never pass through this gate — only new mints do."""
    return (isinstance(uid, str) and _BARE_HEX_RE.fullmatch(uid) is not None
            and len(uid) == MINT_HEX_LEN)


# --------------------------------------------------------------------------- #
# The composite split (3d430852 Stage B; active since 2026-08-31).
#
# At the 12-hex flip every new governed mint becomes COMPOSITE: the
# studio-identity manifest's 4-hex mint_prefix concatenated with 8 random
# local hex, NO separator (shape-amended 2026-08-30, Mike-authorized; ADR-067
# amended to match). The prefix is ISSUED once at genesis and READ from the
# manifest at every mint — a studio must never self-assign a random prefix
# (Metis-ruled; refuse-if-absent is the caller's contract, enforced in
# tropo-mint-id.py where the manifest read lives). Existing 8-hex UIDs are
# untouched and first-class forever.
# --------------------------------------------------------------------------- #

#: The issued prefix stays fixed when the local random portion grows.
COMPOSITE_PREFIX_HEX_LEN = 4


def is_composite_mint_prefix(prefix: str) -> bool:
    """Exactly 4 lowercase hex — the only prefix shape a composite mint
    accepts. The issued prefix has a fixed width; future generation widths
    grow the local random portion without changing the Studio namespace."""
    return (isinstance(prefix, str)
            and _BARE_HEX_RE.fullmatch(prefix) is not None
            and len(prefix) == COMPOSITE_PREFIX_HEX_LEN)


def mint_is_composite() -> bool:
    """Every generation after the original flat-hex shape carries a prefix."""
    return MINT_HEX_LEN > MINT_HEX_HISTORY[0]


def composite_uid(mint_prefix: str, token_hex=None) -> str:
    """Issued prefix + random local hex, at the current mint width.

    The local portion must contain at least four whole bytes. Refuse partial
    configurations before asking for randomness; never round down an odd width.
    The caller reads the issued prefix from the Studio identity manifest.
    """
    local_hex_len = MINT_HEX_LEN - COMPOSITE_PREFIX_HEX_LEN
    if local_hex_len < 8 or local_hex_len % 2:
        raise RuntimeError(
            f"MINT_HEX_LEN {MINT_HEX_LEN} cannot mint a composite UID: "
            f"the {COMPOSITE_PREFIX_HEX_LEN}-hex prefix requires at least "
            "8 local hex characters and an even local width")
    if not is_composite_mint_prefix(mint_prefix):
        raise ValueError(
            f"mint_prefix {mint_prefix!r} is not the composite prefix shape "
            f"(exactly {COMPOSITE_PREFIX_HEX_LEN} lowercase hex)")
    th = token_hex if token_hex is not None else secrets.token_hex
    return mint_prefix + th(local_hex_len // 2)


def parse_anchored_uid(filename: str) -> tuple[str | None, str] | None:
    """Split a governed basename into (slug, uid); the uid is the anchored tail.

    `example-task-1a2b3c4d5e6f.md` -> ("example-task", "1a2b3c4d5e6f");
    `1a2b3c4d.md` -> (None, "1a2b3c4d"); anything whose anchored tail is not a
    governed shape -> None (a filename is a claim, and this refuses claims the
    authority does not recognize). THE NAME PROPOSES; THE FRONTMATTER DECIDES —
    callers must still frontmatter-confirm before treating the uid as identity
    (resolve_governed_path already does; rebuild's full-walk derivation will).
    """
    if not filename.endswith(".md"):
        return None
    stem = filename[:-3]
    if _BARE_HEX_RE.fullmatch(stem) and len(stem) in UID_SHAPES:
        return (None, stem)
    head, sep, tail = stem.rpartition("-")
    if sep and head and _BARE_HEX_RE.fullmatch(tail) and len(tail) in UID_SHAPES:
        return (head, tail)
    return None


def _validate_uid(uid: str) -> None:
    """The single UID gate, called by every public entry point in this module.

    It lived only in the resolver, so `governed_filename("../../secret", t)`
    happily returned `../../secret.md` and a writer would have created it.
    A validator on one of two doors is a validator on neither.
    (Argus A145 review, 2026-08-08.)
    """
    if not uid or len(uid) > _UID_MAX or not _UID_OK.match(uid):
        raise UnsafeGovernedPath(
            f"{uid!r} is not a UID shape. A UID identifies; it is never a path "
            f"fragment, and one carrying a separator or '..' is a traversal."
        )


class AmbiguousGovernedPath(Exception):
    """More than one file claims one UID.

    Raised rather than resolved. Every silent choice here attaches a wrong body
    to a right identity, and the reader has no way to notice. Ambiguity is
    across exact AND slugged shapes and across ALL searched homes: letting the
    bare name win, or the first home win, is a silent choice wearing a rule.
    """


class UnsafeGovernedPath(Exception):
    """The request or the candidate would leave the governed homes."""


def slug_from_title(title: str | None) -> str | None:
    """The human-readable half of a governed filename, or None if there isn't one.

    Lowercase; whitespace (explicit class above) and underscores become hyphens;
    anything outside [a-z0-9-] is DROPPED rather than transliterated — guessing
    which ASCII letter an accent meant is a different feature the spec excludes.
    Hyphens collapse and trim. Truncate to 60 characters at a word boundary, or
    hard-truncate when no boundary exists at or before 60.

    Dropping rather than transliterating means a title with no Latin characters
    yields None and the file is named for its UID. That is correct: a slug is a
    convenience, and a convenience that cannot be produced is absent, not
    approximated.

    No `.strip()` anywhere: whitespace has already become hyphens by then, and
    the hyphen trim below does the work identically in both languages.
    """
    if title is None:
        return None
    slug = _COLLAPSE.sub("-", _DROP.sub("", _TO_HYPHEN.sub("-", title.lower()))).strip("-")
    if not slug:
        return None
    if len(slug) > SLUG_MAX:
        head = slug[:SLUG_MAX]
        cut = head.rfind("-")
        slug = (head[:cut] if cut > 0 else head).strip("-")
    return slug or None


def governed_filename(uid: str, title: str | None) -> str:
    """`<slug>-<uid>.md`, or `<uid>.md` when the title yields no slug.

    The UID is appended whole. A federated `mbaz-b7c2d491` stays whole, because
    the anchored suffix IS the identity and truncating it to the final eight hex
    would make two studios' records collide by construction.
    """
    _validate_uid(uid)
    slug = slug_from_title(title)
    return f"{slug}-{uid}.md" if slug else f"{uid}.md"


def mint_basename(uid: str, title: str | None, studio_root: Path | str) -> str:
    """THE writer entry point: the basename a new governed file should take.

    This is the only place the flag and the filename rule meet. Writers call
    this rather than reading the flag themselves, so Phase 2 is one flag flip
    and not a hunt through every writer for a forgotten branch.
    """
    if readable_minting_enabled(studio_root):
        return governed_filename(uid, title)
    _validate_uid(uid)
    return f"{uid}.md"


def _reject_nonstandard(token: str):
    raise ValueError(f"non-standard JSON constant {token!r}")


def readable_minting_enabled(studio_root: Path | str) -> bool:
    """The one flag reader, fail-closed.

    Missing, unreadable, malformed, or non-boolean all mean False. Writers
    consult this; resolvers never do, because a resolver that stopped
    understanding readable names when the flag went false would strand every
    file already minted under it — the flag disables MINTING, never resolution.
    """
    try:
        text = (Path(studio_root) / FLAG_PATH).read_text(encoding="utf-8")
        # parse_constant fires on NaN/Infinity, which json.loads accepts by
        # default in Python and rejects in JSON.parse. Left alone, the two
        # adapters would disagree about a malformed flag.
        raw = json.loads(text, parse_constant=_reject_nonstandard)
    except (OSError, ValueError):
        return False
    if not isinstance(raw, dict):
        return False
    schema = raw.get("schema_version")
    # Reject bool explicitly: `True == 1` in Python because bool subclasses
    # int, so a plain `== 1` accepts `schema_version: true` where TypeScript's
    # `=== 1` rejects it. That was a genuine divergence.
    #
    # But `type(schema) is int` would create a NEW one in the other direction.
    # JSON has a single number type, so `1.0` and `1` are the same value in
    # JavaScript and cannot be told apart there at all. Python can tell them
    # apart and TypeScript cannot, so the strictest rule BOTH languages can
    # actually implement is: a number equal to 1, and never a boolean.
    # (Argus A145 asked for an integer type check; caught by the 1.0 vector
    # failing in TypeScript, which is the shared-vector file doing its job.)
    if isinstance(schema, bool) or not isinstance(schema, (int, float)):
        return False
    return raw.get("enabled") is True and schema == 1


def _frontmatter_uid(path: Path) -> str | None:
    """The declared UID from CLOSED frontmatter, or None.

    An unterminated `---` block is not frontmatter, it is a truncated or
    corrupt file, and reading identity out of one means trusting a fragment
    that may be mid-write. Refused rather than parsed.
    """
    try:
        # 64KB: real spec frontmatter (fixture-row test-specs among them)
        # exceeds 8KB, and a resolver that cannot see a real record's uid
        # reports blindness as an empty result (Metis's Gap-1 trace,
        # 2026-08-31). The closed-fence requirement inside the window is
        # unchanged: an unterminated block is still a fragment, not
        # frontmatter.
        head = path.read_text(encoding="utf-8", errors="replace")[:65536]
    except OSError:
        return None
    lines = head.splitlines()
    # A fence is a line that is EXACTLY three hyphens. `----` does not open a
    # block and `---junk` does not close one; treating either as a fence means
    # reading identity out of something that is not frontmatter.
    if not lines or lines[0].rstrip("\r") != "---":
        return None
    body: list[str] = []
    for line in lines[1:]:
        if line.rstrip("\r") == "---":
            match = re.search(
                r"^uid:\s*['\"]?([^'\"\s]+)['\"]?\s*$",
                "\n".join(body), re.MULTILINE,
            )
            return match.group(1) if match else None
        body.append(line)
    return None  # never closed: a truncated file, not frontmatter


def _canonical(path: Path) -> Path | None:
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None


def _contained(candidate: Path, home: Path) -> bool:
    """Is the REAL candidate inside the REAL home?

    Resolved on both sides, so a symlink pointing out of the home fails here
    rather than handing back whatever it aimed at.
    """
    real_home, real_candidate = _canonical(home), _canonical(candidate)
    if real_home is None or real_candidate is None:
        return False
    return real_home == real_candidate or real_home in real_candidate.parents


def _homes(studio_root: Path, home: str | None) -> list[tuple[str, Path]]:
    """The governed homes that are real directories INSIDE the real Studio root.

    Checking that a candidate sits under its home is not enough if the home
    itself escaped: symlink `vault/files` at `/etc` and every candidate under
    it passes containment while every byte returned is outside the Studio. So
    the home is canonicalized first and must still be under the canonical root.
    (Argus A145 review, 2026-08-08 — P0-2, second half.)
    """
    if home is not None:
        if home not in GOVERNED_HOMES:
            raise UnsafeGovernedPath(
                f"{home!r} is not a governed home. Accepting an arbitrary "
                f"directory here turns a resolver into a file-disclosure API "
                f"the moment a route passes a user-supplied value."
            )
        wanted = (home,)
    else:
        wanted = GOVERNED_HOMES

    real_root = _canonical(studio_root)
    if real_root is None:
        return []
    homes: list[tuple[str, Path]] = []
    for rel in wanted:
        directory = studio_root / rel
        if not directory.is_dir():
            continue
        real_home = _canonical(directory)
        if real_home is None:
            continue
        # The home must BE the declared directory, not merely resolve to
        # somewhere under the root. "Under the root" still admits
        # `vault/files -> vault/agents`, which exposes every agent record as a
        # vault/files candidate and quietly merges two homes into one. A
        # governed home is a location, not a pointer to one.
        # (Argus A145 third review, 2026-08-08.)
        if real_home != real_root / rel:
            continue
        homes.append((rel, directory))
    return homes


def resolve_governed_path(
    uid: str,
    studio_root: Path,
    *,
    home: str | None = None,
    literal: str | Path | None = None,
) -> Path | None:
    """Find the file that carries `uid`, whatever it is called today.

    A supplied literal is used only when it exists, sits inside a governed home,
    and declares `uid` in closed frontmatter. Otherwise every governed home is
    scanned for exact `<uid>.md` and anchored `*-<uid>.md`, every candidate is
    frontmatter-verified and containment-checked, and the collected set must
    hold exactly one file. Zero is None; more than one raises.

    The literal is verified rather than trusted because a caller's remembered
    path is a claim about the past: after a rename it names either nothing or,
    worse, some other record's file.
    """
    _validate_uid(uid)

    root = _canonical(Path(studio_root))
    if root is None:
        return None
    homes = _homes(root, home)

    suffix = f"-{uid}.md"
    found: list[Path] = []

    # The literal JOINS the candidate set; it does not short-circuit it.
    # Returning early would mean a caller's remembered path silently wins a
    # collision that the scan would have refused — the same silent-choice
    # shape as letting the bare name or the first home win.
    if literal is not None:
        candidate = Path(literal)
        if not candidate.is_absolute():
            candidate = root / candidate
        if (candidate.is_file()
                and _frontmatter_uid(candidate) == uid
                and any(_contained(candidate, hp) for _, hp in homes)):
            real = _canonical(candidate)
            if real is not None:
                found.append(real)
    for _, directory in homes:
        candidates = [directory / f"{uid}.md"]
        # Anchored on the hyphen. Unanchored, `xxxx<uid>.md` — a different
        # record's file — would bind to this UID.
        candidates += [
            p for p in directory.glob(f"*{suffix}")
            if p.name.endswith(suffix) and len(p.name) > len(suffix)
        ]
        for candidate in candidates:
            if not candidate.is_file():
                continue
            if _frontmatter_uid(candidate) != uid:
                continue
            if not _contained(candidate, directory):
                continue
            real = _canonical(candidate)
            if real is not None and real not in found:
                found.append(real)

    if not found:
        return None
    if len(found) > 1:
        raise AmbiguousGovernedPath(
            f"{len(found)} files claim uid {uid}: "
            + ", ".join(str(p) for p in sorted(found))
        )
    return found[0]
