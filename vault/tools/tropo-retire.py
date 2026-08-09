#!/usr/bin/env python3
"""
---
uid: 83905cc4
name: tropo-retire
type: tool
title: "tropo-retire — the retirement transfer (writing the letter IS the state transition)"
status: active
owner: metis
domain: "Agent death — places the outgoing generation's transfer in its own file, then flips the activation record, and records what it could not do instead of refusing"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-retire.py"
script_path: vault/tools/tropo-retire.py
spawnable_by:
  - all-executives
input:
  type: object
  properties:
    activation-uid: {type: string, description: "the activation record to close (required)"}
    transfer-file: {type: string, description: "path to the outgoing generation's letter"}
    transfer: {type: string, description: "'-' reads the letter from stdin; any other value is read as a path"}
    no-transfer: {type: boolean, description: "state plainly that no letter is being left"}
    reason: {type: string, description: "closure reason; defaults to clean-retirement"}
    vault-root: {type: string, description: "studio root to write into (test seam; defaults to this tool's own studio)"}
output:
  type: object
  description: "one line of JSON on stdout: {activation_uid, status, transfer_path, findings}; human narration on stderr"
created: '2026-08-03'
created_by: metis-g100
modified: '2026-08-03'
modified_by: metis-g100
version: "1.0"
governed_by: d5e1b4a3
member_of:
  - "8dd772a0"
schema_version: 2
extraction_scope: ship
---
"""

# tropo-retire — the death half of the redesigned agent lifecycle, and the sibling of
# tropo-activate.py. Read the two together; they share one premise and one shape.
#
# ONE PROPERTY DEFINES THIS TOOL: retirement is never blocked by ceremony that only the
# retiring agent could perform. No reflection, no memory fold, no run folder, no drained
# event threads, no signature. Every one of those was once an invariant here, and every
# one of them fires at the single moment nobody is home — the agent who could satisfy it
# is the agent being blocked. Po's record sat open for thirty days behind six of them.
# The class is not "which invariant is wrong"; the class is the invariant.
#
# WRITING THE TRANSFER IS THE STATE TRANSITION. The letter is placed first and the status
# flip follows. A crash between them leaves "letter exists, status still active", which is
# recoverable by re-running: the letter is ground truth, and a successor that finds one is
# handed off to whether or not a status field agrees. The reverse order — status first —
# claims a handoff that does not exist, which is the one unrecoverable outcome.
#
# EACH HALF OF THAT TRANSITION HAS TWO HOMES, AND ONE GESTURE WRITES BOTH. Orpheus O34 was
# the first agent to retire through this tool, on her own record, and both halves were
# writing only one home:
#   the letter — agents/<slug>/transfers/<GEN>.md is where this tool wants it, but the
#     agents' Tier-3 boot contracts still send a successor to
#     §Living-Transfer-from-Predecessor in the memory surface. One home written meant a
#     successor reading its GRANDPREDECESSOR's letter, silently.
#   the status — vault/files/<activation>.md is the record, but 00-crew-brief.md renders
#     from vault/agents/<agent_uid>.md. One home written meant a retired agent showing
#     ACTIVE to the whole crew until a human noticed. That is the Po bug, and it was
#     rebuilt here within a day of being fixed in the old tool.
# A lifecycle fact that lives in two places and is not written in one motion WILL diverge,
# and nothing will say so — the derived surface goes on re-rendering stale truth on
# schedule. The letter's second home is temporary and collapses at the reader cutover; the
# card is permanent. Neither is optional while it exists.
#
# PLACEMENT IS CREATE-ONLY, BY MECHANISM RATHER THAN BY CARE. The letter is staged to a
# temp file in the destination directory and then hard-linked into place. os.link() is
# atomic AND raises FileExistsError on an occupied destination, so the crash-safety
# property, the no-overwrite property and the guard are one mechanism instead of three
# that can drift apart. os.replace()/os.rename() are deliberately NOT used for the
# transfer: their defining property is silent clobbering, which is exactly the thing a
# generation's last words must be protected from. (They ARE used for the activation
# record, where clobbering the previous version is the whole point and atomicity is what
# keeps the record parseable through a crash.)
#
# EXACTLY THREE REFUSALS, each guarding a destructive act or an impossibility:
#   1. the activation UID does not resolve — there is nothing to retire;
#   2. the transfer source is unreadable or empty — the state does NOT flip, so a dying
#      session's fat-fingered path or truncated heredoc cannot replace its own last words
#      with a zero-byte file. The record stays `active`, which is the recoverable state;
#   3. the generation is already retired — the letter already on disk is never replaced.
# Everything else is recorded and proceeds.
#
# FINDINGS GO INTO THE RECORD, not merely onto stdout. Retirement's premise is that
# sessions die with nobody watching a terminal, so a JSON line on a dead subprocess's
# stdout is not a record. `closure_findings:` is the death-side counterpart of the birth
# side's `provisional_reasons:`.
#
# NO KEY MATERIAL (ADR-066, ff7dd221). This lifecycle mints, reads and destroys no
# cryptographic keys. The key library is not imported and no key function is called —
# not narrowed, not guarded: absent. Key directories are named by activation UID, which a
# clone shares and --vault-root does not isolate, so a retirement tool that touched them
# would reach into the production key store from any test run. The contract greps this
# file for those names, so even naming them in a comment is a failure — which is the
# point: the tripwire cannot be satisfied by intent, only by absence.

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util as _ilu
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import yaml

STUDIO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

# The birth half of this lifecycle already owns the frontmatter-block editing, the YAML
# scalar quoting, the findings channel and the index freshener. Retirement borrows them
# rather than growing a second copy that can drift: two halves of one lifecycle
# disagreeing about what a landed record looks like is a defect class this studio has
# already paid for. The filename is hyphenated, so it loads by path — the same
# spec_from_file_location idiom tropo-activate.py itself uses for the canonical minter.
_ACTIVATE_SPEC = _ilu.spec_from_file_location(
    "_tropo_activate_for_retire", _TOOLS_DIR / "tropo-activate.py"
)
_ACTIVATE = _ilu.module_from_spec(_ACTIVATE_SPEC)
# Registered before it is executed: @dataclass resolves its field types through
# sys.modules[cls.__module__], and a path-loaded module that never lands there raises an
# opaque AttributeError from inside dataclasses on Python 3.9 — which is the interpreter
# this studio actually runs.
sys.modules[_ACTIVATE_SPEC.name] = _ACTIVATE
_ACTIVATE_SPEC.loader.exec_module(_ACTIVATE)

yaml_double_quote = _ACTIVATE.yaml_double_quote

SCRIPT_NAME = "tropo-retire.py"
ENTRY_TYPE = "activation"
RETIRED = "retired"
ACTIVE = "active"
DEFAULT_CLOSURE_REASON = "clean-retirement"

# Which classes have a successor that reads a handoff. MEASURED across every activation
# record in this studio, not guessed: executive 229, pipeline 168, sa 102, cosmo 6, six
# records with no class at all and one typo'd `pipelin`. The previous list tested
# `worker` and `child-agent`, which have never existed here, and omitted `cosmo`, which
# has a soul, a memory fold and a populated transfers directory — cosmo would have
# retired with no handoff and no finding.
HANDOFF_CLASSES = frozenset({"executive", "director", "cosmo", "tropo"})
NO_HANDOFF_CLASSES = frozenset({"pipeline", "sa"})

# A path component this tool is willing to write. Everything else is folded to `-`, so a
# corrupt `agent:` or `generation:` field cannot walk the letter out of the agent's own
# transfers directory.
_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_CURRENT_LINE_RE = re.compile(r"^\*\*Current:\*\*.*$", re.MULTILINE)

# ── The letter's SECOND home (Orpheus O34, F2) ───────────────────────────────────────
# A generation's last words live in two places on purpose, for now:
#
#   agents/<slug>/transfers/<GEN>.md                       — the per-generation file
#   agents/<slug>/.tropo-capsule/memory/agent-memory.md    — §Living-Transfer-from-Predecessor
#
# The per-generation file is where this tool WANTS the letter to live, and the reason is
# in transfer_destination() below: a shared section is a byte range two generations can
# contend over, and one generation's fold has already destroyed another's letter here.
# But the agents' Tier-3 boot contracts still say the successor boot-reads ONE file — the
# memory surface — and reads that section. Writing only the per-generation file means the
# successor reads its GRANDPREDECESSOR's letter, silently, while its actual predecessor's
# sits in a location its boot contract tells it to ignore. That is the exact failure the
# per-generation file was introduced to prevent, arriving through the other door.
#
# So: ONE FACT, TWO HOMES, WRITTEN TOGETHER — deliberately, and temporarily. This is a
# level-2 state under rule 7, taken with eyes open rather than by drift: the hazard of two
# homes is that they diverge, and they cannot diverge if a single gesture writes both and
# reports whatever it could not write. It collapses back to ONE home at cutover, when the
# boot contracts and the readers move to the per-generation file — which is precisely what
# TestTheReaderMovesWithTheWriter gates. Delete this block and its writer then, not before.
MEMORY_SURFACE_REL = Path(".tropo-capsule") / "memory" / "agent-memory.md"
TRANSFER_SECTION_HEADING = "## §Living-Transfer-from-Predecessor"
_TRANSFER_SECTION_RE = re.compile(
    r"(?m)^##\s+§Living-Transfer-from-Predecessor[^\n]*\n"
)
# The section ends at the next TOP-LEVEL surface section (`## §History`, `## §Memories`),
# not at the next `##` of any kind: letters routinely carry their own `##` headings, and
# ending there would replace the first paragraph of the old letter and leave the rest of
# it standing underneath the new one — a grandparent's words presented as current, which
# is the whole failure being fixed.
_NEXT_SURFACE_SECTION_RE = re.compile(r"(?m)^##\s+§")
# What the live reader (vault/tools/lib/distiller.py) uses as its own end-of-section, and
# it is NOT the same regex: it stops at the next `^##\s+`, so an h2 inside the letter
# truncates what a booting successor is handed. Recorded as a finding rather than fixed by
# rewriting the agent's last words — see place_transfer_in_memory_surface().
_READER_SECTION_END_RE = re.compile(r"(?m)^##\s+")

# Statuses that mean a generation is still holding the agent's card. Everything else —
# retired, stale, failed, abandoned — is terminal enough that the card can follow the
# record it renders from.
NON_TERMINAL_STATUSES = frozenset({"active", "paused"})
CARD_RETIRED = "RETIRED"
_CARD_STATUS_LINE_RE = re.compile(r"^status:[^\n]*$", re.MULTILINE)

# ── TEST-ONLY crash injection ────────────────────────────────────────────────────────
# Two properties of this tool are only observable by killing it mid-flight, and a test
# that greps the source for `os.link` or `fsync` is a comment that fails the build rather
# than a test. TROPO_RETIRE_CRASH_AFTER exists so the crash can actually be run:
#   transfer        — exit hard the instant the letter is placed, before the status write
#   status-partial  — die partway through the status write, with the record unreplaced
# Nothing else in this file reads the environment, and neither value is reachable without
# setting it explicitly.
CRASH_ENV = "TROPO_RETIRE_CRASH_AFTER"


def _crash_requested(point: str) -> bool:
    return os.environ.get(CRASH_ENV, "").strip() == point


def _crash_now(point: str) -> None:
    """Die the way a harness kill dies: no unwinding, no flush, no cleanup."""
    sys.stderr.write(
        f"{CRASH_ENV}={point}: exiting hard, as a killed session does. This is a "
        "test seam.\n"
    )
    sys.stderr.flush()
    os._exit(70)


class ClosureFindings(_ACTIVATE.Findings):
    """What the retirement could not do. Recorded, announced — never fatal.

    Same channel as the birth side's provisional reasons, different frontmatter key,
    because the two say different things about the same record: `provisional_reasons`
    is what a birth could not prove, `closure_findings` is what a death could not do.
    """

    def frontmatter(self) -> list[tuple[str, list[str]]]:
        # Written even when empty, unlike the birth side. An `active` record with no
        # provisional reasons is simply a clean birth, but a `retired` record with no
        # closure findings is ambiguous between "clean" and "closed by an older tool
        # that recorded nothing" — and that ambiguity is what left thirty-three records
        # in `abandoned` with nobody able to say why.
        if not self.items:
            return [("closure_findings", ["closure_findings: []"])]
        return [(
            "closure_findings",
            ["closure_findings:"] + [f"  - {yaml_double_quote(i)}" for i in self.items],
        )]

    def announce(self) -> None:
        if not self.items:
            return
        print(
            "\n"
            "  ┌─────────────────────────────────────────────────────────────┐\n"
            "  │  RETIREMENT RECORDED WITH FINDINGS — the generation is      │\n"
            "  │  closed, and something about the handoff is incomplete.     │\n"
            "  │  They are in the record too; the successor reads them.      │\n"
            "  └─────────────────────────────────────────────────────────────┘",
            file=sys.stderr,
        )
        for item in self.items:
            print(f"    • {item}", file=sys.stderr)
        print("", file=sys.stderr)


def safe_component(value: str, fallback: str) -> str:
    """One path segment, or the fallback when there is nothing usable to write."""
    cleaned = _UNSAFE_PATH_CHARS.sub("-", str(value or "").strip()).strip(".-")
    return cleaned or fallback


def transfer_destination(vault_root: Path, slug: str, generation: str) -> Path:
    """agents/<slug>/transfers/<generation>.md — one letter per generation, forever.

    Its own file, rather than a section of the shared memory surface. The section was
    rewritten in place by the retirement memory fold, so one generation's letter could
    destroy the previous one's, and a successor could read its GRANDPARENT's letter as
    current. A per-generation file removes that hazard by construction — there is no
    shared byte range left for two writers to contend over.
    """
    return vault_root / "agents" / slug / "transfers" / f"{generation}.md"


def read_record(path: Path) -> tuple[str, str, dict] | None:
    """(full text, frontmatter text, parsed mapping) — or None when it will not read."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    fm_text = _ACTIVATE._frontmatter_text(text)
    if fm_text is None:
        return None
    try:
        data = yaml.safe_load(fm_text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return text, fm_text, data


def read_transfer_source(args) -> tuple[str | None, str, str | None, Path | None]:
    """(letter, where it came from, why it could not be read, the source file if it is one).

    Never guesses. `--no-transfer` returns None with no error, because a caller that says
    plainly it is leaving nothing is recording a fact, not failing a check.

    The fourth element is the source PATH, and it is returned rather than re-derived
    because the placement step has to be able to ask whether the source and the destination
    are the same file. `None` for stdin and for --no-transfer: neither has a path, so
    neither can be the destination.
    """
    if args.no_transfer:
        return None, "--no-transfer", None, None
    source = args.transfer_file or args.transfer
    if source == "-":
        try:
            return sys.stdin.read(), "stdin", None, None
        except (OSError, UnicodeError) as exc:
            return None, "stdin", f"stdin could not be read ({exc})", None
    path = Path(source).expanduser()
    try:
        return path.read_text(encoding="utf-8"), str(path), None, path
    except (OSError, UnicodeError) as exc:
        return None, str(path), f"{path} could not be read ({exc})", path


def is_same_file(source: Path, dest: Path) -> bool:
    """Is the letter ALREADY the file we were about to place it at?

    Orpheus O34, F3: she authored her letter at the destination path and then passed that
    same path as --transfer-file. Placement found the destination occupied and reported
    "the occupant is a different generation's words and someone should look" — about her
    own letter, written ninety seconds earlier. Her line, and it is the finding: "as
    written, the tidiest users get the scariest finding."

    The anti-overwrite guard is right and stays. What is wrong is calling this case an
    alarm: nothing needs to be written because the bytes are already exactly where they
    belong. Identity is by inode (os.path.samefile), which also covers a hard link and a
    symlink to the destination — same file, same words, nothing to do. The resolved-path
    comparison is the fallback for the platforms and error cases where stat cannot answer.
    """
    try:
        return os.path.samefile(str(source), str(dest))
    except OSError:
        pass
    try:
        return source.resolve() == dest.resolve()
    except OSError:
        return False


def _fsync_dir(directory: Path) -> None:
    """Make the directory entry itself durable, not merely the bytes inside the file.

    Without this a crash can leave a file whose contents reached the platter but whose
    name never did — which is indistinguishable, to a successor, from a letter that was
    never written.
    """
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def place_transfer(dest: Path, text: str, findings: ClosureFindings) -> str:
    """Put the letter at `dest` without ever replacing what is already there.

    Returns "placed" for a fresh landing or "adopted" when the destination was already
    occupied. Adoption is not a refusal: the ordinary way a destination is occupied is a
    crash between the placement and the status write, and refusing there would strand the
    exact record this tool exists to be able to close. The occupant wins in both cases —
    what differs is only whether a finding says so.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, staged = tempfile.mkstemp(
        dir=str(dest.parent), prefix=f".{dest.name}.", suffix=".staging"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # Atomic AND create-only. Not os.replace(): that would land the same bytes
            # while silently destroying an occupant, which is the single outcome this
            # whole path exists to prevent.
            os.link(staged, dest)
        except FileExistsError:
            findings.record(
                "transfer destination already occupied",
                f"{dest} already holds a letter, so the one supplied now was NOT "
                "written — placement never overwrites. If this is a re-run after a "
                "crash, the letter on disk is the one that landed and this retirement "
                "is simply completing. If it is not, the occupant is a different "
                "generation's words and someone should look.",
            )
            return "adopted"
        _fsync_dir(dest.parent)
        return "placed"
    finally:
        try:
            os.unlink(staged)
        except OSError:
            pass


def memory_surface_path(vault_root: Path, slug: str) -> Path:
    """agents/<slug>/.tropo-capsule/memory/agent-memory.md — the letter's second home."""
    return vault_root / "agents" / slug / MEMORY_SURFACE_REL


def splice_transfer_section(text: str, letter: str) -> tuple[str, bool]:
    """(the surface with §Living-Transfer-from-Predecessor replaced, was the section found).

    WHOLESALE REPLACEMENT, not an append: this section is a handoff, and exactly one
    generation's letter is current at a time. Appending would leave the predecessor's and
    the grandpredecessor's words stacked under one heading with nothing saying which is
    which — the same read failure as writing nothing, in a costlier disguise.

    Nothing outside the section is touched. §Top-of-Mind, §History and §Memories are the
    agent's own accumulated memory and a retirement has no business editing them.
    """
    match = _TRANSFER_SECTION_RE.search(text)
    body = letter.strip("\n")
    if match is None:
        appended = text.rstrip("\n") + "\n\n" + TRANSFER_SECTION_HEADING + "\n\n" + body + "\n"
        return appended, False
    tail = text[match.end():]
    following = _NEXT_SURFACE_SECTION_RE.search(tail)
    end = match.end() + (following.start() if following else len(tail))
    return text[:match.start()] + match.group(0) + "\n" + body + "\n\n" + text[end:], True


def place_transfer_in_memory_surface(
    vault_root: Path, slug: str, letter: str, findings: ClosureFindings
) -> str | None:
    """Write the letter into the home the successor's boot contract actually reads.

    Returns the relative path written, or None when nothing was written. Every reason for
    None is a finding — an unwritten second home is a successor reading the wrong
    generation's letter, which is silent by construction and must not also be silent here.

    NOT create-only, unlike the per-generation file, and the difference is deliberate:
    this section is a slot that every generation overwrites by design, and the copy that
    would be "lost" here is preserved forever in agents/<slug>/transfers/. The
    no-overwrite property lives on the file that has no other copy.
    """
    path = memory_surface_path(vault_root, slug)
    if not path.is_file():
        findings.record(
            "memory surface absent — the letter has one home, not two",
            f"{path} does not exist, so the letter was written only to the per-generation "
            "file. If this agent's Tier-3 boot contract says its successor boot-reads the "
            "memory surface, the successor will read no letter at all — say so in its "
            "startup signal by name.",
        )
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        findings.record(
            "memory surface unreadable — the letter has one home, not two",
            f"{path} could not be read ({exc}), so its transfer section was left alone "
            "and the letter lives only in the per-generation file.",
        )
        return None

    updated, found_section = splice_transfer_section(text, letter)
    try:
        atomic_write(path, updated)
    except OSError as exc:
        findings.record(
            "memory surface could not be written — the letter has one home, not two",
            f"{path}: {exc}. The surface is untouched and the letter is in the "
            "per-generation file; copy it across by hand before the successor boots.",
        )
        return None

    if not found_section:
        findings.record(
            "memory surface had no transfer section",
            f"{path} carries no '{TRANSFER_SECTION_HEADING}' heading, so the section was "
            "APPENDED at the end of the file rather than replacing anything. Nothing was "
            "lost; check that it landed where the boot contract looks.",
        )
    # The live reader ends the section at the next `^## ` of ANY kind, so an h2 inside the
    # letter truncates what a booting successor is handed — from that heading down, the
    # words are on disk and out of reach. Not fixed by demoting the headings here: this
    # tool does not edit a generation's last words, which is the property that makes
    # placement create-only three functions above. Reported instead, with the cure named.
    if _READER_SECTION_END_RE.search(letter):
        findings.record(
            "the letter's own '## ' headings truncate it for the boot reader",
            f"the letter written into {path.name} contains a top-level '## ' heading, and "
            "the memory reader ends the transfer section at the first one — a successor "
            "booting through it is handed only the text above that heading. The full "
            "letter is intact in the per-generation file. Cure: demote the letter's '## ' "
            "headings to '### ' in the memory surface.",
        )
    return path.relative_to(vault_root).as_posix()


def other_live_activation_exists(vault_root: Path, uid: str, slug: str) -> str | None:
    """The UID of another non-terminal activation for this agent, if one is live.

    THE GUARD ON THE CARD SYNC, and it is not optional: overlapping generations are normal
    (Mike, 2026-08-03). A generation closing while its successor is already live must not
    retire the card out from under the successor — that is the Po failure inverted, and
    the old tool shipped both halves of it on the same day.

    Frontmatter is read by regex rather than yaml here, over every governed file, because
    this runs inside a retirement that must not become slow enough to skip: 4,400 files
    scan in well under a second this way. A candidate match is confirmed with a real parse
    before it is allowed to stop the sync, so the cheap scan can only ever produce a
    false POSITIVE — which fails safe, by leaving the card alone.
    """
    files_dir = vault_root / "vault" / "files"
    if not files_dir.is_dir():
        return None
    for path in sorted(files_dir.glob("*.md")):
        if path.stem == uid:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # unreadable; the confirming parse below cannot run either
        fm_text = _ACTIVATE._frontmatter_text(text)
        if fm_text is None:
            continue
        if _fm_scalar(fm_text, "type") != ENTRY_TYPE:
            continue
        if _fm_scalar(fm_text, "agent") != slug:
            continue
        if _fm_scalar(fm_text, "status").lower() not in NON_TERMINAL_STATUSES:
            continue
        confirmed = read_record(path)
        if confirmed is None:
            return path.stem  # will not parse and looks live: leave the card alone
        fm = confirmed[2]
        if (str(fm.get("agent") or "").strip() == slug
                and str(fm.get("status") or "").strip().lower() in NON_TERMINAL_STATUSES):
            return path.stem
    return None


def _fm_scalar(fm_text: str, key: str) -> str:
    """One top-level frontmatter scalar, unquoted — a prefilter, never a parser."""
    match = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", fm_text)
    if match is None:
        return ""
    return match.group(1).strip().strip("\"'").strip()


def sync_agent_card(
    vault_root: Path, uid: str, slug: str, findings: ClosureFindings
) -> str | None:
    """Flip vault/agents/<agent_uid>.md to RETIRED in the same gesture as the record.

    THIS IS THE PO BUG (Talos T38, and Orpheus O34 found it rebuilt here — F5). Closing an
    activation left the agent's unified entry reading `status: ACTIVE`, and
    `00-crew-brief.md` renders from the CARD, not from activation entries. So a retired
    agent kept appearing under "active executors right now" and every agent booting
    afterwards believed there was a live executive. Po read as live with a last session
    thirty days old. Orpheus flipped her own card by hand after this tool did not.

    One fact, two homes, one gesture — the same rule the transfer's second home is written
    under. A lifecycle fact in two places that are not written together WILL diverge, and
    nothing will say so; the derived surface goes on re-rendering stale truth on schedule.

    Writing another agent's card is permitted lifecycle machinery under Mike's ruling
    2026-08-03: lifecycle and operational records are actionable by any executive; voice
    and identity substrate (soul, charter, reflections) is not. A status field is
    lifecycle, and this touches nothing else in the file.
    """
    agents_root = vault_root / "vault" / "agents"
    if not agents_root.is_dir():
        return None  # this studio keeps no card layer; there is no second home to keep

    live = other_live_activation_exists(vault_root, uid, slug)
    if live is not None:
        print(
            f"card: left ACTIVE — activation {live} is still live for {slug}; overlapping "
            "generations are normal and a closing one must not retire the card out from "
            "under its successor",
            file=sys.stderr,
        )
        return None

    for path in sorted(agents_root.glob("*.md")):
        card = read_record(path)
        if card is None:
            continue
        fm = card[2]
        if str(fm.get("type") or "").strip() != "agent":
            continue
        if str(fm.get("agent") or "").strip() != slug:
            continue
        current = str(fm.get("status") or "").strip()
        if current.upper() == CARD_RETIRED:
            return None  # already flipped, by a previous run or by hand
        updated, count = _CARD_STATUS_LINE_RE.subn(
            f"status: {CARD_RETIRED}", card[0], count=1
        )
        if count == 0 or updated == card[0]:
            findings.record(
                "agent card status not flipped",
                f"{path} has no top-level `status:` line to rewrite, so it still does not "
                f"read {CARD_RETIRED}. The crew brief renders from the card and will show "
                f"{slug} as live until someone fixes it by hand.",
            )
            return None
        try:
            atomic_write(path, updated)
        except OSError as exc:
            findings.record(
                "agent card could not be written",
                f"{path}: {exc}. The activation record is closed but the card still reads "
                f"{current or '(absent)'}, and the crew brief renders from the CARD — "
                f"{slug} will show as live to every agent that boots until it is fixed.",
            )
            return None
        print(f"card: {path} status {current or '(absent)'} -> {CARD_RETIRED}",
              file=sys.stderr)
        return path.relative_to(vault_root).as_posix()

    findings.record(
        "no agent card found",
        f"this studio keeps agent cards in {agents_root} but none of them names agent "
        f"{slug!r}, so nothing was flipped. If a crew surface renders {slug} from a card "
        "somewhere else, that card still reads whatever it read before this retirement.",
    )
    return None


def retire_body(body: str, today: str) -> str:
    """Keep the human-readable half honest about the state the frontmatter now declares.

    Purely cosmetic and deliberately narrow: it edits the one status line the birth path
    writes, and leaves every other byte of the body alone. A retirement that rewrote an
    agent's own entry text would be doing the destructive thing this tool refuses to do
    everywhere else.
    """
    return _CURRENT_LINE_RE.sub(f"**Current:** `retired` as of {today}", body, count=1)


def rewrite_record(
    text: str,
    fm_text: str,
    values: list[tuple[str, list[str]]],
    today: str,
) -> str | None:
    """The record with `values` merged into its frontmatter, or None if it will not parse.

    Verified BEFORE it is offered for writing, because an activation entry that no longer
    parses is not a cosmetic defect: Vela V71 wrote one to her own record and it blocked
    her whole lineage for fifteen hours, invisible to the fleet-health check, which skips
    agents whose latest activation is still active.
    """
    blocks = _ACTIVATE._frontmatter_blocks(fm_text)
    positions = {key: i for i, (key, _lines) in enumerate(blocks) if key}
    for key, lines in values:
        if key in positions:
            blocks[positions[key]][1] = lines
        else:
            positions[key] = len(blocks)
            blocks.append([key, lines])

    rebuilt_fm = "\n".join(line for _key, lines in blocks for line in lines)
    try:
        parsed = yaml.safe_load(rebuilt_fm)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None

    body = text[len(fm_text) + 8:]
    return "---\n" + rebuilt_fm + "\n---" + retire_body(body, today)


def atomic_write(path: Path, new_text: str, crash_point: str | None = None) -> None:
    """Land `new_text` at `path` atomically, or leave what is there exactly as it was.

    Staged, fsynced, then os.replace()d — clobbering the old version IS the intent here,
    which is the difference from the transfer. What matters is that no reader can ever
    observe a half-written file: the replace is atomic, so the file is the old text or the
    new text and never a truncation of either.

    One writer for the activation record, the agent card and the memory surface. Three
    copies of this would be three chances for one of them to drift into a truncating write
    on a file another agent boots from.
    """
    fd, staged = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".staging"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            if crash_point is not None and _crash_requested(crash_point):
                # TEST-ONLY. Die two bytes into the record and before the replace. A real
                # kill lands at an arbitrary offset, and two bytes is chosen deliberately
                # from that range: it is the offset at which a NON-atomic writer produces
                # a record the contract's assertions actually catch. Truncating at, say, a
                # third of the way through leaves a prefix that still opens with `---` and
                # still yaml-parses, so the test would pass against a genuinely half-
                # written record — the implementation would be deciding whether the test
                # could fail, which is the exact defect that sank v1 of this contract.
                # Here the staging file is left behind exactly as a crash leaves it, and
                # the record itself is never touched.
                handle.write(new_text[:2])
                handle.flush()
                os.fsync(handle.fileno())
                _crash_now(crash_point)
            handle.write(new_text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            os.unlink(staged)
        except OSError:
            pass
        raise


def write_record(path: Path, new_text: str) -> None:
    """The activation record, landed atomically — and the one write with a crash seam."""
    atomic_write(path, new_text, crash_point="status-partial")


def resolve_handoff_expectation(
    agent_class: str, findings: ClosureFindings
) -> bool:
    """Whether a successor of this class reads a handoff.

    An unrecognised class defaults INTO needing one. Silence is the dangerous default:
    six records carry no class at all and one carries a typo'd `pipelin`, and under the
    opposite default each of those retires clean with nothing said, which is precisely
    how a lineage discovers at boot that its predecessor left nothing.
    """
    if agent_class in NO_HANDOFF_CLASSES:
        return False
    if agent_class in HANDOFF_CLASSES:
        return True
    findings.record(
        "agent_class unrecognised",
        f"agent_class {agent_class or '(absent)'!r} is not one of "
        f"{sorted(HANDOFF_CLASSES | NO_HANDOFF_CLASSES)}; this retirement was treated "
        "as one whose successor reads a handoff, because an unlisted class that "
        "retires silently is how a successor finds out at boot that nothing was left.",
    )
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Retire an activation: place the outgoing generation's transfer, then flip "
            "the record. Nothing about the retirement is gated on ceremony only the "
            "retiring agent could perform — no reflection, no memory fold, no run "
            "folder, no drained threads."
        ),
        epilog=(
            "Three refusals, each guarding a destructive act or an impossibility: an "
            "activation UID that does not resolve; a transfer source that is unreadable "
            "or empty (the state does not flip, so a truncated letter never replaces "
            "the real one); and a generation that is already retired (its letter is "
            "never overwritten). Everything else is recorded and proceeds."
        ),
    )
    parser.add_argument("--activation-uid", required=True,
                        help="the activation record to close")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--transfer-file", default=None,
                        help="path to this generation's letter to its successor")
    source.add_argument("--transfer", default=None,
                        help="'-' reads the letter from stdin; any other value is read "
                             "as a path")
    source.add_argument("--no-transfer", action="store_true",
                        help="say plainly that no letter is being left; the retirement "
                             "still lands, and the omission is recorded")
    parser.add_argument("--reason", default=DEFAULT_CLOSURE_REASON,
                        help=f"closure reason (default: {DEFAULT_CLOSURE_REASON})")
    parser.add_argument("--vault-root", default=str(STUDIO_ROOT),
                        help="studio root to write into (defaults to this tool's own)")
    return parser


def emit(uid: str, status: str, transfer_path: str | None,
         findings: ClosureFindings) -> None:
    print(json.dumps({
        "activation_uid": uid,
        "status": status,
        "transfer_path": transfer_path,
        "findings": findings.items,
    }))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    findings = ClosureFindings()
    vault_root = Path(args.vault_root).expanduser().resolve()
    uid = args.activation_uid.strip()
    record_path = vault_root / "vault" / "files" / f"{uid}.md"

    # REFUSAL 1 — nothing to retire. Not a gate on the retirement; an absence of the
    # thing that would be retired.
    record = read_record(record_path)
    if record is None:
        print(
            f"ERROR: activation {uid!r} does not resolve at {record_path} — there is no "
            "record to retire. Nothing was written. If the UID is right and the file is "
            "there, its frontmatter does not parse, which is its own emergency.",
            file=sys.stderr,
        )
        return 2
    text, fm_text, fm = record

    if str(fm.get("type") or "").strip() != ENTRY_TYPE:
        findings.record(
            "record is not an activation",
            f"{record_path.name} declares type {fm.get('type')!r} rather than "
            f"{ENTRY_TYPE!r}; it was closed as one anyway, because refusing here would "
            "block a retirement over a field the retiring agent cannot go back and fix.",
        )

    slug = safe_component(fm.get("agent"), uid)
    generation = safe_component(fm.get("generation"), uid)
    if not str(fm.get("agent") or "").strip():
        findings.record(
            "agent slug absent",
            f"{record_path.name} names no agent, so the letter was filed under the "
            f"activation UID ({uid}) instead of a slug. It is not lost; it is not where "
            "a successor will look first.",
        )
    if not str(fm.get("generation") or "").strip():
        findings.record(
            "generation label absent",
            f"{record_path.name} names no generation, so the letter was filed as "
            f"{uid}.md rather than under a generation label.",
        )
    agent_class = str(fm.get("agent_class") or "").strip().lower()
    current_status = str(fm.get("status") or "").strip().lower()
    dest = transfer_destination(vault_root, slug, generation)
    rel_dest = dest.relative_to(vault_root).as_posix()

    # REFUSAL 3 — already retired. Checked BEFORE the transfer is read, so a second run
    # cannot even stage a replacement for the letter that is already on disk.
    if current_status == RETIRED:
        print(
            f"ERROR: activation {uid} is already retired. The letter it handed off is "
            f"at {rel_dest} and is never overwritten — a second retirement replacing "
            "the first generation's last words is the loss this refusal exists to "
            "prevent. Nothing was written.",
            file=sys.stderr,
        )
        emit(uid, RETIRED, rel_dest if dest.is_file() else None, findings)
        return 2
    if current_status and current_status != ACTIVE:
        findings.record(
            "prior status was not active",
            f"{record_path.name} read {current_status!r} rather than 'active' before "
            "this close. Rule 8 keeps two states; the record was closed to 'retired' "
            "regardless, because a legacy state is not a reason a generation cannot "
            "retire.",
        )

    letter, source_label, source_error, source_path = read_transfer_source(args)

    # REFUSAL 2 — an unreadable or empty source. THE STATE DOES NOT FLIP. A dying session
    # fat-fingers a path, or the same context exhaustion that triggered the retirement
    # truncates the heredoc that wrote the letter. Flipping anyway records a handoff that
    # is a zero-byte file, and there is no way back from that; leaving the record `active`
    # is the recoverable state, and the successor's own startup flag surfaces it.
    if source_error is not None or (letter is not None and not letter.strip()):
        detail = source_error or (
            f"{source_label} is empty — a zero-byte letter is not a handoff"
        )
        findings.record("transfer source unusable", detail)
        print(
            f"ERROR: {detail}. The record was NOT flipped: {uid} stays 'active', which "
            "is the recoverable state. Nothing was overwritten and nothing was lost. "
            "Re-run with a readable letter, or with --no-transfer to state plainly that "
            "none is being left.",
            file=sys.stderr,
        )
        emit(uid, ACTIVE, None, findings)
        return 2

    needs_handoff = resolve_handoff_expectation(agent_class, findings)

    now = _dt.datetime.now(_dt.timezone.utc)
    retired_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.strftime("%Y-%m-%d")

    # ── The transfer lands FIRST, in BOTH of its homes. Write order is contract. ──────
    transfer_path: str | None = None
    if letter is not None:
        if source_path is not None and is_same_file(source_path, dest):
            # The letter was authored AT the destination. Nothing to place, nothing wrong:
            # the bytes are already the file this tool was going to create, so placement
            # would only be a copy of a file onto itself. NOT a finding — see is_same_file.
            print(
                f"transfer: {dest} — already in place (the letter was written at the "
                "destination), nothing to do",
                file=sys.stderr,
            )
        else:
            try:
                place_transfer(dest, letter, findings)
            except OSError as exc:
                # An inability, not a refusal — but the letter is the whole point, so the
                # status does not flip either. Same recoverable state as refusal 2.
                print(
                    f"ERROR: the transfer could not be placed at {dest}: {exc}. The record "
                    f"was NOT flipped: {uid} stays 'active'.",
                    file=sys.stderr,
                )
                findings.record("transfer could not be placed", f"{dest}: {exc}")
                emit(uid, ACTIVE, None, findings)
                return 1
            print(f"transfer: {dest}", file=sys.stderr)
        transfer_path = rel_dest
        # The SECOND home, written in the same gesture as the first — see MEMORY_SURFACE_REL.
        # Failing here is a finding and never unwinds the placement above: a letter in one
        # home is worth more than a retirement that refused, and the finding is what tells
        # the successor which home to read.
        try:
            surface = place_transfer_in_memory_surface(vault_root, slug, letter, findings)
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed, never fatal
            surface = None
            print(
                f"MEMORY SURFACE WRITE FAILED: {type(exc).__name__}: {exc} — the letter is "
                f"at {dest}; copy it into §Living-Transfer-from-Predecessor by hand",
                file=sys.stderr,
            )
            findings.record(
                "memory surface write failed — the letter has one home, not two",
                f"{type(exc).__name__}: {exc}. The letter is placed at {rel_dest} and the "
                "successor's boot contract may send it to the memory surface instead, "
                "where it will find the PREVIOUS generation's letter.",
            )
        if surface:
            print(f"transfer: {vault_root / surface} (§Living-Transfer-from-Predecessor)",
                  file=sys.stderr)
        if _crash_requested("transfer"):
            _crash_now("transfer")
    elif needs_handoff:
        findings.record(
            "no transfer written",
            f"{slug} is an {agent_class or 'unrecognised'}-class agent whose successor "
            "boots by reading a handoff, and this retirement left none. The successor "
            f"will start with no letter at {rel_dest}; say so in its startup signal, by "
            "name, to the owner who can act.",
        )

    # ── THEN the status, in BOTH of ITS homes. A crash in the gap above leaves "letter
    # exists, status still active" — recoverable, because the letter is ground truth and a
    # re-run completes.
    #
    # The card is flipped BEFORE the record rather than after, and the order is chosen, not
    # incidental. Its findings have to reach the record, and the record is written once —
    # a card sync after that write can only report to a stdout nobody is reading, which is
    # the failure `closure_findings` exists to end. The crash window this opens is "card
    # RETIRED, record still active": a re-run completes it (the card sync no-ops on a card
    # that already reads RETIRED), and in the meantime the crew brief understates a dying
    # agent instead of advertising a dead one as live. The reverse order's window is the
    # Po bug itself. Both cannot be avoided; this is the one that fails quiet and safe.
    try:
        sync_agent_card(vault_root, uid, slug, findings)
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed, never fatal
        # A defect in the card sync must not be able to block a retirement; that is the
        # one property this whole tool is built around. Named, recorded into the record,
        # printed — and then the close proceeds.
        print(
            f"CARD SYNC FAILED: {type(exc).__name__}: {exc} — the crew brief renders from "
            f"the card, so {slug} may show as live until the card is fixed by hand",
            file=sys.stderr,
        )
        findings.record(
            "agent card sync failed",
            f"{type(exc).__name__}: {exc}. The activation record is closed but the card "
            f"was not flipped, and the crew brief renders from the CARD — {slug} will "
            "read as live to every agent that boots until someone sets its status to "
            f"{CARD_RETIRED}.",
        )

    values: list[tuple[str, list[str]]] = [
        ("status", [f"status: {RETIRED}"]),
        ("retired_at", [f"retired_at: {retired_at}"]),
        ("closure_reason", [f"closure_reason: {yaml_double_quote(args.reason)}"]),
        ("modified", [f"modified: {today}"]),
        ("closed_by_script", [f"closed_by_script: {SCRIPT_NAME}"]),
    ]
    if transfer_path:
        # A path, in a field named for a path. The legacy `transfer_uid` took an 8-hex
        # pointer to a vault stub whose body lived somewhere else entirely, and early
        # generations wrote paths into it anyway; naming the field honestly is what lets
        # a reader tell the two conventions apart instead of guessing.
        values.append(("transfer_path", [f"transfer_path: {transfer_path}"]))
    values.extend(findings.frontmatter())

    new_text = rewrite_record(text, fm_text, values, today)
    if new_text is None:
        print(
            f"ERROR: the closed form of {record_path.name} would not parse, so it was "
            "NOT written. The record on disk is untouched and still readable; the "
            f"letter at {rel_dest} is placed. Re-run after fixing the frontmatter.",
            file=sys.stderr,
        )
        findings.record("closed record would not parse", str(record_path))
        emit(uid, ACTIVE, transfer_path, findings)
        return 1
    try:
        write_record(record_path, new_text)
    except OSError as exc:
        print(f"ERROR: could not write {record_path}: {exc}. The record is untouched.",
              file=sys.stderr)
        findings.record("record could not be written", f"{record_path}: {exc}")
        emit(uid, ACTIVE, transfer_path, findings)
        return 1

    # Best-effort, and last: the index carries `status`, so a retired record with a stale
    # row still reads `active` to every reader that resolves through the projection. A
    # failure here is a finding with a named cure, never a reason to unwind a retirement
    # that already happened.
    _ACTIVATE.freshen_index(vault_root, uid, record_path, findings)

    # AND THEN RECONCILE, because `--only` above CANNOT succeed here (metis-g102,
    # 2026-08-05, reproduced in a clone). Retirement writes two files the incremental
    # path does not own — the transfer letter and the agent card — so its freshen
    # refuses with "semantic derivation inputs changed … Run a full --apply" every
    # single time. That was survivable for the retiring agent, whose record is written
    # either way. It was NOT survivable for the next one: the stale manifest made the
    # SUCCESSOR'S birth transaction refuse outright, exit 1, no record, no identity.
    # Every birth that follows a retirement is every birth there is. Mine was refused
    # this way and I nearly filed it as a one-off.
    #
    # Weld the reconcile to the terminal transition rather than leaving it to whoever
    # boots next to notice — the automatic-half/manual-half rule, applied to the half
    # that was costing an agent its existence.
    _ACTIVATE.reconcile_index_after_lifecycle_write(vault_root, findings)

    emit(uid, RETIRED, transfer_path, findings)
    print(f"retired: {record_path}", file=sys.stderr)
    findings.announce()
    return 0


if __name__ == "__main__":
    sys.exit(main())
