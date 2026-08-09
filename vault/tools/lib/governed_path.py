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
        head = path.read_text(encoding="utf-8", errors="replace")[:8192]
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
