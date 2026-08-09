#!/usr/bin/env python3
"""
---
uid: 39f6f96d
name: tropo-activate
type: tool
title: "tropo-activate — the activation mint (birth issues the identity, and never refuses it)"
status: active
owner: metis
domain: "Agent birth — issues the generation number, writes the activation record, and records what it could not prove instead of refusing"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-activate.py"
script_path: vault/tools/tropo-activate.py
spawnable_by:
  - all-executives
input:
  type: object
  properties:
    agent: {type: string, description: "agent slug (required)"}
    authorized-by: {type: string, description: "authorizing principal, or the parent activation UID (required)"}
    agent-class: {type: string, description: "executive|director|sa|cosmo|tropo|worker|child-agent|pipeline; resolved from the agent's own history when omitted. A MALFORMED value is the one refusal."}
    agent-root: {type: string, description: "Level-1 agent root project UID"}
    model: {type: string, description: "sleeve identifier"}
    platform: {type: string, description: "harness the session runs in"}
    member-of: {type: string, description: "comma-separated UIDs"}
    run-folder: {type: string, description: "playbook-runs/<run>/ path"}
    vault-root: {type: string, description: "studio root to write into (test seam; defaults to this tool's own studio)"}
output:
  type: object
  description: "one line of JSON on stdout: {activation_uid, generation, provisional, findings}; human narration on stderr"
created: '2026-08-03'
created_by: metis-g100
modified: '2026-08-05'
modified_by: metis-g102
version: "1.1"
governed_by: d5e1b4a3
member_of:
  - "8dd772a0"
schema_version: 2
extraction_scope: ship
---
"""

# tropo-activate — the birth half of the redesigned agent lifecycle (eleven rules, 40b13b5b).
#
# ONE PROPERTY DEFINES THIS TOOL: it does not refuse. Every identity check that used to
# gate a boot still runs and every failure is still recorded — loudly, on stderr and in
# the record — but the consequence is a finding, not a halt. The reason is not
# philosophical. A gate on the boot path fires at the one moment nobody is home: the
# agent who could clear it is the agent being refused. Three consecutive Metis
# generations plus Po deadlocked that way, each on a different check, and each fix
# addressed only the check it hit. The class is not "which check is wrong" — the class
# is refusal itself. A provisional agent that can speak is strictly better than a
# correct refusal nobody is present to read.
#
# THE ONE SURVIVING REFUSAL is a malformed --agent-class, because without a class there
# is no identity to record — a provisional entry would have nothing to say.
#
# THE MINT OWNS THE NUMBER (rule 1, Mike-locked). There is no flag for it. The agent asks
# to activate and is TOLD what it is, so there is no claim to verify and the whole
# generation-mismatch family disappears rather than being relaxed. The counter is
# "highest known locally for this slug, plus one": no network, no shared authority,
# offline-correct, and a gap in history does not stall it. Unreadable history yields a
# best guess and a finding — never a refusal. The known cost, named in Argus's ruling O1
# and accepted: two machines minting offline can both issue the same number. That is a
# post-merge renumbering, which is survivable precisely because the durable reference is
# the activation UID, not the label — artifacts carry `created_by_activation_uid`, so a
# renumbering renames no file, no filename and no Git object.
#
# NO KEY MATERIAL. This lifecycle mints, reads and destroys no cryptographic keys
# (Argus ruling O2). That REMOVES the shared key-root destruction family rather than
# relocating it: there is no key store for a clone to reach into. Attribution rests on
# the activation UID and event provenance, which is the bar Mike's standing identity
# ruling actually sets — attribution and continuity, never security.
#
# BIRTH ONLY CREATES (rule 3). No sweep, no close, no edit of any existing record. The
# stale-sweep that used to run here is a separate step the boot playbook calls BEFORE
# activating; a skipped sweep corrupts nothing, whereas birth-as-closer produced 31 of
# the studio's 33 `abandoned` records.

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import importlib.util as _ilu
import io
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

STUDIO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from lib import template_leg  # noqa: E402 -- must follow the sys.path insert above

# The canonical minter's module name starts with a digit-free but hyphenated filename,
# so it cannot be imported by name; this is the same spec_from_file_location idiom the
# other six chokepoint callers use.
_MINT_SPEC = _ilu.spec_from_file_location(
    "_tropo_mint_id_for_activate", _TOOLS_DIR / "tropo-mint-id.py"
)
_MINT = _ilu.module_from_spec(_MINT_SPEC)
_MINT_SPEC.loader.exec_module(_MINT)

SCRIPT_NAME = "tropo-activate.py"
ENTRY_TYPE = "activation"

# activation.capsule §2 §4 Rule 7 — the class enum, and the one refusal's whole surface.
VALID_CLASSES = (
    "executive", "director", "sa", "cosmo", "tropo", "worker", "child-agent", "pipeline",
)
FALLBACK_CLASS = "executive"

# Rule 8 keeps two states, `active` and `retired`. `paused` is deleted as a state anything
# may WRITE, but records already carrying it read as still-open, and so do the legacy
# `stale`/`failed` pair's opposite — a record is open when no handoff has been written.
OPEN_STATUSES = frozenset({"active", "paused"})

# activation.capsule §2 (v1.0.1 amendment) declares these per-class defaults. Written into
# the record so staleness stays COMPUTED against the record's own declared threshold —
# a stored staleness needs a writer, and that writer always lags, because nothing is
# running at the moment a session dies.
STALE_THRESHOLD_DEFAULTS = {
    "sa": 2, "worker": 6, "child-agent": 4,
    "executive": 168, "director": 168, "cosmo": 168, "tropo": 168, "pipeline": 6,
}
DEFAULT_STALE_THRESHOLD_HOURS = 168

# A lineage's label prefix is cosmetic — the NUMBER is the identity — but a lineage that
# renames itself mid-chain creates exactly the two-records-disagreeing divergence rule 7
# is about. So: inherit the predecessor's prefix and digit width, else the agent's
# registered prefix, else the shape activation.capsule §2 declares for the class.
DEFAULT_GENERATION_PREFIX = "G"
# §Generation Format by Agent Class: these three number off the slug (`sa.cold-boot-149`,
# `daily-vault-health-042`); executives and directors carry a registered letter prefix.
SLUG_NUMBERED_CLASSES = frozenset({"sa", "worker", "child-agent"})
SLUG_NUMBERED_WIDTH = 3

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
# Longest trailing digit run is the number; everything before it is the prefix. Covers
# every shape the capsule declares: G100, A58, sa.cold-boot-149, daily-vault-health-042.
_GENERATION_RE = re.compile(r"^(?P<prefix>.*?)(?P<number>\d+)$")
_FM_KEY_RE = re.compile(r"^(?P<key>[A-Za-z_][\w.-]*):")
_PLACEHOLDER_RE = re.compile(r"<!--\s*(?:REQUIRED|OPTIONAL)\s*:")
_LOOKS_LIKE_ACTIVATION_RE = re.compile(r"""^type:\s*["']?activation["']?\s*$""", re.MULTILINE)
_DECLARES_AGENT_SLUG_RE = re.compile(r"^agent_slug:", re.MULTILINE)
_HEX8_RE = re.compile(r"^[0-9a-f]{8}$")
_FRESHEN_TIMEOUT_SECONDS = 120
# A full --apply over ~4,900 records is ~30-50s on this studio; give it real headroom.
_RECONCILE_TIMEOUT_SECONDS = 600


def yaml_double_quote(value: str) -> str:
    """A YAML double-quoted scalar for free text.

    `json.dumps` emits exactly the double-quoted-scalar escaping YAML defines, so this
    borrows it rather than growing a fifth hand-rolled quoter in this tools directory.
    `ensure_ascii=False` keeps em dashes readable in the record rather than \\u-escaped.
    """
    return json.dumps(str(value), ensure_ascii=False)


class Findings:
    """What the birth could not prove. Recorded, announced — never fatal.

    Nothing here is swallowed: every entry is printed to stderr the moment it is
    recorded, repeated in the closing banner, returned on stdout as JSON, and (for the
    ones known before the write) carried in the record itself as `provisional_reasons`.
    """

    def __init__(self) -> None:
        self.items: list[str] = []

    def record(self, code: str, message: str) -> None:
        self.items.append(f"{code}: {message}")
        print(f"FINDING: {code} — {message}", file=sys.stderr)

    def resolve(self, code: str, note: str) -> bool:
        """Drop a finding that a LATER step in the same run actually repaired.

        Not cosmetic (metis-g102, 2026-08-05). Retirement's `--only` freshen cannot
        succeed by construction — it runs after the transfer letter and the card are
        written, and neither is owned by that incremental target — so it recorded
        "index freshen failed" on EVERY retirement. The full reconcile that follows
        then fixes precisely that, and leaving the alarm standing marks a clean
        retirement `provisional: true` and hands the successor a scary finding whose
        named cure has already been run.

        A check that fires every time and is immediately self-healed is a check the
        crew learns to scroll past, which is how the fleet-health output sat correct
        and unread for a week. Resolve it out loud instead of suppressing it: the
        repair is announced, so the record shows the sequence rather than hiding it.
        """
        prefix = f"{code}: "
        kept = [i for i in self.items if not i.startswith(prefix)]
        if len(kept) == len(self.items):
            return False
        self.items[:] = kept
        print(f"RESOLVED: {code} — {note}", file=sys.stderr)
        return True

    def __bool__(self) -> bool:
        return bool(self.items)

    def frontmatter(self) -> list[tuple[str, list[str]]]:
        if not self.items:
            return []
        return [
            ("provisional", ["provisional: true"]),
            ("provisional_reasons",
             ["provisional_reasons:"] + [f"  - {yaml_double_quote(i)}" for i in self.items]),
        ]

    def announce(self) -> None:
        if not self.items:
            return
        print(
            "\n"
            "  ┌─────────────────────────────────────────────────────────────┐\n"
            "  │  PROVISIONAL ACTIVATION — you are born, and something is    │\n"
            "  │  wrong with your lineage record. You are expected to work.  │\n"
            "  │  Surface these in your startup signal; a human decides.     │\n"
            "  └─────────────────────────────────────────────────────────────┘",
            file=sys.stderr,
        )
        for item in self.items:
            print(f"    • {item}", file=sys.stderr)
        print("", file=sys.stderr)


@dataclass
class History:
    """Everything the local records say about one agent slug."""

    highest_number: int = 0
    prefix: str | None = None
    number_width: int = 0
    predecessor_uid: str | None = None
    predecessor_class: str | None = None
    registered_prefix: str | None = None
    registered_class: str | None = None
    open_records: list[str] = field(default_factory=list)
    known_uids: set[str] = field(default_factory=set)


def _frontmatter_text(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    return text[4:end]


def _raw_frontmatter(path: Path, findings: Findings) -> str | None:
    """One file's frontmatter block, or None when there is none to read."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        findings.record(
            "history unreadable",
            f"{path.name} could not be read ({exc}); if it carried lineage for this "
            "agent, the identity issued below is a best guess.",
        )
        return None
    return _frontmatter_text(text)


def _parse_frontmatter(raw: str, name: str, findings: Findings) -> dict | None:
    """The mapping, or None plus a finding — a malformed record never halts a birth.

    The finding is deliberate: silence here is how a corrupt predecessor becomes an
    understated generation nobody ever hears about.
    """
    try:
        data = yaml.safe_load(raw)
    except Exception as exc:  # any parser failure at all; none of them is fatal here
        findings.record(
            "history unreadable",
            f"{name} carries lineage for this agent but its frontmatter will not parse "
            f"({exc}); it went uncounted, so the identity issued below is a best guess "
            "rather than a proven successor.",
        )
        return None
    if not isinstance(data, dict):
        findings.record(
            "history unreadable",
            f"{name} carries lineage for this agent but its frontmatter is not a "
            "mapping; it went uncounted, so the identity issued below is a best guess.",
        )
        return None
    return data


def read_history(vault_root: Path, slug: str, findings: Findings) -> History:
    """Read every local record once and answer everything birth needs to know.

    One pass, because the alternative is four scans of the same directory and this runs
    on the boot path. No `git log`, no network, no shared counter — Argus ruling O1: the
    number has to be issuable on a plane, from a fresh clone, with nobody else reachable.
    """
    history = History()
    files_dir = vault_root / "vault" / "files"
    best_sort_key: tuple | None = None

    if files_dir.is_dir():
        for path in sorted(files_dir.glob("*.md")):
            if _HEX8_RE.match(path.stem):
                history.known_uids.add(path.stem)
            raw = _raw_frontmatter(path, findings)
            if raw is None:
                continue
            # Parse only what this birth could possibly care about. A full YAML parse of
            # every governed file costs seconds ON THE BOOT PATH — the surface this whole
            # redesign exists to make cheap — and this vault has 4,400 of them. The cost
            # of the shortcut is stated plainly: a record whose own `type:` line is the
            # corrupted part reads as "not an activation" and goes unmentioned.
            if not (_LOOKS_LIKE_ACTIVATION_RE.search(raw)
                    or _DECLARES_AGENT_SLUG_RE.search(raw)):
                continue
            data = _parse_frontmatter(raw, path.name, findings)
            if data is None:
                continue
            # An agent root project carries the lineage's declared label prefix.
            if str(data.get("agent_slug") or "").strip() == slug:
                history.registered_prefix = (
                    str(data.get("generation_prefix") or "").strip()
                    or history.registered_prefix
                )
                history.registered_class = (
                    str(data.get("agent_class") or "").strip() or history.registered_class
                )
            if data.get("type") != ENTRY_TYPE:
                continue
            if str(data.get("agent") or "").strip() != slug:
                continue
            if str(data.get("status") or "").strip() in OPEN_STATUSES:
                history.open_records.append(path.stem)
            label = str(data.get("generation") or "").strip()
            if not label:
                # Rule 11's migration finding: the earliest records simply never recorded
                # this. Absence is "not recorded", not an error, and not a finding either.
                continue
            match = _GENERATION_RE.match(label)
            if not match:
                findings.record(
                    "generation label unreadable",
                    f"{path.name} records generation {label!r} for {slug!r}, which "
                    "carries no number to count from; it is not counted, so the number "
                    "issued below may be lower than this lineage has already reached.",
                )
                continue
            number = int(match.group("number"))
            sort_key = (number, str(data.get("activated_at") or ""), path.stem)
            if best_sort_key is None or sort_key > best_sort_key:
                best_sort_key = sort_key
                history.highest_number = number
                history.prefix = match.group("prefix") or None
                history.number_width = len(match.group("number"))
                history.predecessor_uid = path.stem
                history.predecessor_class = (
                    str(data.get("agent_class") or "").strip() or None
                )

    agents_dir = vault_root / "vault" / "agents"
    if agents_dir.is_dir():
        for path in sorted(agents_dir.glob("*.md")):
            raw = _raw_frontmatter(path, findings)
            if raw is None:
                continue
            data = _parse_frontmatter(raw, path.name, findings)
            if data is None or data.get("type") != "agent":
                continue
            if str(data.get("agent") or data.get("slug") or "").strip() != slug:
                continue
            history.registered_prefix = (
                str(data.get("generation_prefix") or "").strip() or history.registered_prefix
            )
            history.registered_class = (
                str(data.get("agent_class") or "").strip() or history.registered_class
            )

    return history


def resolve_agent_class(supplied: str | None, history: History, findings: Findings) -> str:
    """The class the record will carry.

    A supplied-but-malformed class already refused before this is reached. An OMITTED
    class is resolvable — the lineage's own last record knows it — and resolving beats
    demanding, because a demand on the boot path is the failure mode this tool exists to
    delete.
    """
    if supplied:
        return supplied
    for candidate, source in ((history.predecessor_class, "its predecessor activation"),
                              (history.registered_class, "its registered agent record")):
        if candidate and candidate in VALID_CLASSES:
            findings.record(
                "agent_class not supplied",
                f"no class was given; read {candidate!r} from {source}. Pass "
                "--agent-class to state it rather than have it inferred.",
            )
            return candidate
        if candidate:
            findings.record(
                "agent_class unrecognised in history",
                f"{source} records agent_class {candidate!r}, which is not one of "
                f"{list(VALID_CLASSES)}; it was not used.",
            )
    findings.record(
        "agent_class not supplied",
        f"no class was given and this agent's records name none; recorded as "
        f"{FALLBACK_CLASS!r}. Per-class behaviour (stale threshold, transfer "
        "obligation) will follow that assumption until corrected.",
    )
    return FALLBACK_CLASS


def issue_generation(history: History, slug: str, agent_class: str) -> str:
    """Highest known locally, plus one. Not a contiguity check — a gap is not a stall.

    A brand-new lineage starts at 1: genesis has no predecessor, and the flag that asks
    a successor about a missing transfer must never fire for it, because "your
    predecessor left no transfer" is false when there is no predecessor.

    The label wrapped around that number follows the lineage first (prefix AND digit
    width, so `sa.cold-boot-008` succeeds to `-009` rather than `-9`), then the agent's
    registered prefix, then the shape the capsule declares for the class.
    """
    genesis_prefix, genesis_width = (
        (f"{slug}-", SLUG_NUMBERED_WIDTH) if agent_class in SLUG_NUMBERED_CLASSES
        else (DEFAULT_GENERATION_PREFIX, 1)
    )
    prefix = history.prefix or history.registered_prefix or genesis_prefix
    width = history.number_width or genesis_width
    return f"{prefix}{history.highest_number + 1:0{width}d}"


def load_leg(vault_root: Path, findings: Findings) -> template_leg.TemplateLeg | None:
    """The activation capsule's §Template leg — the record shape's one authored home.

    Tried at the target studio first (a studio governs its own types), then at the studio
    this tool ships inside, which is what a scratch or fixture root falls back to. Only
    total failure is a finding: birth proceeds on the built-in field order below, because
    a missing capsule is a governance gap, not a reason an agent does not exist.
    """
    attempts: list[str] = []
    for root in dict.fromkeys((vault_root.resolve(), STUDIO_ROOT)):
        try:
            return template_leg.load_template_leg(root, ENTRY_TYPE)
        except (template_leg.TemplateLegError, OSError, UnicodeError) as exc:
            attempts.append(f"{root}: {exc}")
    findings.record(
        "template leg unavailable",
        "the activation capsule's §Template leg could not be loaded, so this record was "
        "written from the mint's own field order instead of the governed scaffold — "
        + " | ".join(attempts),
    )
    return None


def _frontmatter_blocks(fm_text: str) -> list[list]:
    """[[key, [lines]]] — each top-level key with its indented continuation lines."""
    blocks: list[list] = []
    for line in fm_text.splitlines():
        match = _FM_KEY_RE.match(line)
        if match and not line[:1].isspace():
            blocks.append([match.group("key"), [line]])
        elif blocks:
            blocks[-1][1].append(line)
        else:
            blocks.append([None, [line]])  # nothing precedes the first key in a valid leg
    return blocks


def render_record(
    leg: template_leg.TemplateLeg | None,
    uid: str,
    values: list[tuple[str, list[str]]],
    pointers: list[str],
    today: str,
    entry_name: str,
    findings: Findings,
) -> str:
    """Stamp the leg, fill in what the mint owns, and drop what nothing filled.

    The leg declares the shape and the order; this fills the values. A `<!-- REQUIRED -->`
    or `<!-- OPTIONAL -->` line still holding its placeholder after the fill is DELETED
    rather than carried, because a field nobody could fill should read as absent — rule
    11's reader contract is "absence means not recorded", and a surviving placeholder is
    a deterministic INCOMPLETE to every verifier in the studio.
    """
    stamped = None
    if leg is not None:
        try:
            # activation_uid became REQUIRED on 2026-08-03 (commit ece7b3a5,
            # the cross-agent dev-spec work) after this tool shipped green.
            # For an activation entry the answer is its own uid: the record IS
            # the activation, so it is its own provenance. Caught by rehearsing
            # a real retirement in a clone, not by any suite — nothing runs
            # these tools automatically, which is the same gap that let the
            # fleet-health check be right and unread for a week.
            stamped = template_leg.stamp(
                leg, uid=uid, date=today, author=entry_name, activation_uid=uid
            )
        except template_leg.TemplateLegError as exc:
            findings.record(
                "template leg malformed",
                f"the activation §Template leg could not be stamped ({exc}); this record "
                "was written from the mint's own field order instead.",
            )

    if stamped is None:
        blocks: list[list] = []
        body_lines = [
            f"# {entry_name} — Activation Entry", "",
            "## 1. Session Pointers", "",
            "<!-- placeholder -->", "",
            "## 2. Status", "",
            f"**Current:** `active` as of {today}", "",
        ]
    else:
        fm_text = _frontmatter_text(stamped) or ""
        blocks = _frontmatter_blocks(fm_text)
        body_lines = stamped[len(fm_text) + 8:].splitlines()

    positions = {key: i for i, (key, _) in enumerate(blocks) if key}
    for key, lines in values:
        if key in positions:
            blocks[positions[key]][1] = lines
        else:
            positions[key] = len(blocks)
            blocks.append([key, lines])
    kept = [
        block for block in blocks
        if not any(_PLACEHOLDER_RE.search(line) for line in block[1])
    ]

    filled_body: list[str] = []
    pointer_block_written = False
    for line in body_lines:
        if _PLACEHOLDER_RE.search(line) or line.strip() == "<!-- placeholder -->":
            if not pointer_block_written:
                filled_body.extend(pointers)
                pointer_block_written = True
            continue
        filled_body.append(line)
    if not pointer_block_written:
        filled_body.extend(["", "## 1. Session Pointers", ""] + pointers)

    while filled_body and not filled_body[0].strip():
        filled_body.pop(0)

    out = ["---"]
    for _key, lines in kept:
        out.extend(lines)
    out.extend(["---", ""])
    out.extend(filled_body)
    out.extend(["", "---", "",
                f"*{entry_name} — activation entry | UID `{uid}` | minted {today} by "
                f"{SCRIPT_NAME}*", ""])
    return "\n".join(out)


# Outcomes of the indexed birth transaction. Three, not two, because "the index
# would not take it" and "the record cannot be written at all" are different
# facts about the world and only the second one may cost an agent its existence.
COMMIT_INDEXED = "indexed"          # source + index row landed together
COMMIT_SOURCE_ONLY = "source-only"  # index refused twice; write the source, born provisional
COMMIT_IMPOSSIBLE = "impossible"    # the record itself cannot be written

_INDEX_REFUSED_CODE = "index refused the birth transaction"


def _attempt_indexed_commit(
    freshener,
    vault_root: Path,
    uid: str,
    out_path: Path,
    record_text: str,
) -> tuple[bool, str]:
    """One staged, create-only attempt. Returns ``(ok, diagnostic)``.

    Separated from the retry policy above it so the policy is readable on its own
    and so a test can drive a refusal without reaching into the transaction.
    """
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = freshener.freshen_many(
                (uid,),
                vault_root,
                source_replacements={
                    out_path: record_text.encode("utf-8"),
                },
                require_absent_sources=(out_path,),
            )
    except Exception as exc:
        return False, f"raised {exc}"
    diagnostic = (stderr.getvalue() or stdout.getvalue()).strip()
    if code != 0:
        return False, (f"exited {code}" + (f": {diagnostic}" if diagnostic else ""))
    return True, diagnostic


def commit_indexed_activation(
    vault_root: Path,
    uid: str,
    out_path: Path,
    record_text: str,
    findings: Findings,
) -> str:
    """Commit a canonical activation source and its index row as one gesture.

    Canonical governed birth must not place the source first and ask ``--only``
    to catch up afterward: a valid incremental refusal then leaves a real
    activation that every index-backed reader reports as nonexistent. Reuse the
    same staged, create-only transaction as the generic governed mint so either
    the source plus every derived participant lands, or none of them does.

    RECONCILE AND RETRY ONCE, THEN BE BORN ANYWAY (talos-t38, 2026-08-05, on
    Metis G102's ruling; reproduced four times against copies of this studio).
    ``reconcile_index_after_lifecycle_write`` closed retire -> birth, because it
    runs AFTER a transaction that succeeded — so it can tidy up and it cannot
    rescue. Retirement only ever worked because it refreshes the manifest as a
    side effect on its way past. Nothing refreshes it when the predecessor simply
    STOPPED, and unclean shutdown is the normal case. Worse, the drift does not
    need a retirement upstream at all: a plain ``git pull`` moves enough semantic
    inputs to refuse the next birth, which for a cloud agent booting from a fresh
    clone is the ordinary path rather than an edge.

    Measured, one variable at a time:

        stale manifest + predecessor RETIRED      -> born clean
        stale manifest + predecessor STILL ACTIVE -> REFUSED, exit 1, NO IDENTITY
        fresh manifest + predecessor STILL ACTIVE -> born, provisional, correctly

    So the identity checks were innocent; the INDEX was refusing births that no
    gate would have refused. The order here is the fix: refuse once, reconcile,
    retry. A refusal is a stale projection, and a stale projection is repairable.

    AND A SECOND REFUSAL STILL DOES NOT COST AN AGENT ITS EXISTENCE (Metis's
    boundary, and the whole point). The birth proceeds source-only as a recorded
    finding — ``provisional: true``, never ``exit 1`` with nothing issued. Only an
    INABILITY to write the record at all is fatal, and that word is used
    deliberately: a refusal is a policy declining, an inability is the world
    saying no, and conflating them is how the ruled-out class kept coming back.
    """
    try:
        freshener = _MINT._load_rebuild_index(vault_root)
    except Exception as exc:
        # Not a refusal: with no transaction to run there is nothing to retry.
        # The caller still writes the source — the fallback path exists for
        # exactly this shape of studio.
        findings.record(
            _INDEX_REFUSED_CODE,
            f"the canonical index transaction could not be loaded for {out_path}: "
            f"{exc}. The activation record is written and this birth stands; the "
            f"index row is not derived until someone runs `python3 "
            f"vault/tools/tropo-rebuild-index.py --apply` from {vault_root}.",
        )
        return COMMIT_SOURCE_ONLY

    ok, diagnostic = _attempt_indexed_commit(
        freshener, vault_root, uid, out_path, record_text
    )
    if not ok:
        findings.record(
            _INDEX_REFUSED_CODE,
            f"the birth transaction for {out_path} {diagnostic}. Reconciling the "
            "index and retrying once — a refusal here is a stale projection, not a "
            "verdict on this agent.",
        )
        reconcile_index_after_lifecycle_write(vault_root, findings)
        ok, diagnostic = _attempt_indexed_commit(
            freshener, vault_root, uid, out_path, record_text
        )
        if ok:
            findings.resolve(
                _INDEX_REFUSED_CODE,
                "the index had drifted since the last full manifest; the reconcile "
                "derived it and the retried transaction committed. Birth is clean.",
            )
        else:
            # Deliberately NOT a return-1. The record is still written by the
            # caller and the agent is still born; the index simply lags, and the
            # finding says so with the command that closes it.
            findings.record(
                _INDEX_REFUSED_CODE,
                f"the birth transaction still {diagnostic} after a reconcile. The "
                "activation record is written and this birth stands, but its index "
                "row is not derived, so index-backed readers will not see it until "
                "someone runs `python3 vault/tools/tropo-rebuild-index.py --apply` "
                f"from {vault_root}.",
            )
            return COMMIT_SOURCE_ONLY

    try:
        _MINT._verify_minted_index_row(
            vault_root,
            uid,
            out_path,
            ENTRY_TYPE,
        )
    except Exception as exc:
        rollback_error = _MINT._rollback_minted_birth(
            freshener,
            vault_root,
            uid,
            out_path,
        )
        # Also not a return-1, for the same reason as a second refusal: an
        # inconsistent projection is a fact about the index, not about whether
        # this agent exists. The rollback removed the staged record; the caller
        # writes it back and the birth stands, provisional and loudly so.
        if rollback_error:
            findings.record(
                "index row could not be verified after the birth transaction",
                f"exact-row verification failed ({exc}) AND the rollback is "
                f"incomplete: {rollback_error}. The activation record is written "
                "and this birth stands, but the index is in a state a human should "
                "look at — run `python3 vault/tools/tropo-rebuild-index.py --apply` "
                f"from {vault_root} and check for a stray row under {uid}.",
            )
        else:
            findings.record(
                "index row could not be verified after the birth transaction",
                f"exact-row verification failed ({exc}); the staged birth was rolled "
                "back cleanly. The activation record is written and this birth "
                "stands, but its index row is not derived until someone runs "
                f"`python3 vault/tools/tropo-rebuild-index.py --apply` from "
                f"{vault_root}.",
            )
        return COMMIT_SOURCE_ONLY
    return COMMIT_INDEXED


CARD_ACTIVE = "ACTIVE"
_CARD_STATUS_RE = re.compile(r"(?m)^status:[ \t]*.*$")
_CARD_GENERATION_RE = re.compile(r"(?m)^generation:[ \t]*.*$")
_CARD_ACTIVATION_UID_RE = re.compile(r"(?m)^current_activation_uid:[ \t]*.*$")


def sync_agent_card(
    vault_root: Path, uid: str, slug: str, generation: str, findings: Findings
) -> None:
    """Flip vault/agents/<agent_uid>.md to ACTIVE in the same gesture as the record.

    THE PO BUG, HALF-WELDED (Vela V71, 2026-08-05, proven by a full retire-then-birth
    rehearsal in a throwaway clone). `tropo-retire.py` has had `sync_agent_card()` since
    the cutover and correctly flips ACTIVE -> RETIRED. Birth had NO counterpart — not one
    reference to `vault/agents` anywhere in this file. So immediately after a successful
    birth the card still read `status: RETIRED`, the predecessor's `generation:` and the
    predecessor's `current_activation_uid:`, while the new activation sat live in
    `vault/files/`. One fact, two homes, written by only ONE of the two gestures.

    WHY IT IS WORSE THAN A STALE FIELD. `00-crew-brief.md` renders FROM THE CARD. On
    2026-08-04 I added a re-render at birth because newborn agents were showing as their
    retired predecessor for up to an hour — but that fix is DOWNSTREAM of the field nobody
    wrote, so it faithfully republishes the predecessor and makes the staleness look
    freshly confirmed. V71 demonstrated exactly that in the clone: a brief rendered the
    way birth renders it, reading `Vela V71 RETIRED` while V72 was alive. A fix that
    improves the report of a wrong fact is worse than no fix.

    This is the automatic-half/manual-half family in its purest form: retirement welded,
    birth left to the agent's memory. Every Metis generation including mine hand-edited
    this card at boot and none of us recorded it as a defect — I did it myself hours
    before writing the render fix that could not work.

    Writing an agent's card is permitted lifecycle machinery under Mike's 2026-08-03
    ruling: lifecycle and operational records are actionable, voice and identity substrate
    is not. This touches three lifecycle fields and nothing else.
    """
    agents_root = vault_root / "vault" / "agents"
    if not agents_root.is_dir():
        return  # this studio keeps no card layer; there is no second home to keep

    for path in sorted(agents_root.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        head = text[:4000]
        if not re.search(r"(?m)^type:[ \t]*agent[ \t]*$", head):
            continue
        if not re.search(rf"(?m)^agent:[ \t]*{re.escape(slug)}[ \t]*$", head):
            continue

        updated, status_n = _CARD_STATUS_RE.subn(f"status: {CARD_ACTIVE}", text, count=1)
        updated, gen_n = _CARD_GENERATION_RE.subn(
            f"generation: {generation}", updated, count=1)
        updated, act_n = _CARD_ACTIVATION_UID_RE.subn(
            f"current_activation_uid: {uid}", updated, count=1)

        if status_n == 0:
            findings.record(
                "agent card status not flipped",
                f"{path} has no top-level `status:` line to rewrite, so the card still "
                f"does not read {CARD_ACTIVE}. The crew brief renders from the CARD — "
                f"{slug} will show as its retired predecessor to every agent that boots "
                "until someone fixes it by hand.",
            )
            return
        if act_n == 0:
            # ADD it rather than only complain. agent.capsule (2f8b4e3d) lists
            # current_activation_uid as OPTIONAL, but its purpose line is "the open
            # type: activation entry, WHEN ONE EXISTS" — and at a birth one always
            # exists, because we just wrote it. Absent-while-active is therefore a
            # divergence from the field's own contract even though it passes schema.
            #
            # Not hypothetical: Vela V71's fleet card sweep on 2026-08-05 found exactly
            # one live divergence — orpheus, ACTIVE with no current_activation_uid at
            # all. A sync that only rewrites existing lines would flag that card on every
            # future birth and never repair it, which is a gate that reports forever and
            # fixes nothing: the shape this studio keeps paying for.
            anchor = _CARD_GENERATION_RE.search(updated)
            insert_at = anchor.end() if anchor else None
            if insert_at is None:
                close = re.search(r"(?m)^---[ \t]*$", updated[4:])
                insert_at = (close.start() + 4 - 1) if close else None
            if insert_at is not None:
                updated = (updated[:insert_at]
                           + f"\ncurrent_activation_uid: {uid}"
                           + updated[insert_at:])
                act_n = 1
        if gen_n == 0 or act_n == 0:
            findings.record(
                "agent card partially updated",
                f"{path}: status flipped to {CARD_ACTIVE}, but "
                f"{'generation' if gen_n == 0 else 'current_activation_uid'} could be "
                "neither rewritten nor inserted. The card now claims this generation is "
                "active while still naming its predecessor — say so in your startup "
                "signal.",
            )
        try:
            path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            findings.record(
                "agent card could not be written",
                f"{path}: {exc}. The activation record exists but the card still reads "
                f"the predecessor, and the crew brief renders from the CARD.",
            )
            return
        print(f"card: {path} -> status {CARD_ACTIVE}, generation {generation}, "
              f"current_activation_uid {uid}", file=sys.stderr)
        return

    findings.record(
        "no agent card found",
        f"no `type: agent` entry with `agent: {slug}` under {agents_root}. The activation "
        "record is written, but the crew brief renders from the card and has nothing to "
        f"show for {slug}.",
    )


def freshen_index(vault_root: Path, uid: str, out_path: Path, findings: Findings) -> None:
    """Make the new record visible to the readers, or say why it is not.

    Rule 11's safety argument ("its worst failure is recording something odd") covers
    WRITERS only — Argus ruling O4. The crew brief, the cockpit and the 3,784-line reader
    all resolve activations through the index, so a record with no row is a record that
    silently is not there. Best-effort by construction: a failure here is a finding with a
    named cure, never a refusal, and never a reason to unwind a birth that already
    happened.
    """
    index = vault_root / "vault" / "00-index.jsonl"
    script = vault_root / "vault" / "tools" / "tropo-rebuild-index.py"
    if not index.is_file() or not script.is_file():
        return  # no projection lives here to keep honest (a scratch or fixture studio)
    # THE CURE IS THE FULL APPLY, NOT THE INCREMENTAL ONE — Orpheus O34, F4, on the first
    # real retirement run through this lifecycle. `--only <uid>` is what this function
    # ATTEMPTS, and the dominant reason that attempt fails is a source inventory the
    # incremental path refuses to derive from ("source inventory incomplete … Run a full
    # --apply"), which fires whenever unrelated files have moved. Naming `--only` as the
    # cure sends the reader straight back into the refusal that produced the finding; the
    # freshener's own refusal text already names the answer, and this is it. A stranger who
    # runs the suggestion and hits the same wall concludes the retirement is broken.
    cure = f"run `python3 vault/tools/tropo-rebuild-index.py --apply` from {vault_root}"
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--only", uid],
            cwd=str(vault_root), capture_output=True, text=True,
            timeout=_FRESHEN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        findings.record("index freshen failed",
                        f"{out_path.name} is written but its index row is not: {exc}. {cure}.")
        return
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        findings.record(
            "index freshen failed",
            f"{out_path.name} is written but the freshener exited {proc.returncode}"
            + (f": {detail[-1]}" if detail else "") + f". {cure}.",
        )
        return
    try:
        # Same exact-row check the generic governed birth runs ("the write is not done
        # until its row is") — reused rather than re-derived, so the two births cannot
        # come to different conclusions about what a landed record looks like.
        _MINT._verify_minted_index_row(vault_root, uid, out_path, ENTRY_TYPE)
    except Exception as exc:
        findings.record("index row unverified",
                        f"{out_path.name} is written and the freshener succeeded, but its "
                        f"row did not verify: {exc}. {cure}.")


def reconcile_index_after_lifecycle_write(vault_root: Path, findings: Findings) -> None:
    """Leave the index consistent, so the NEXT lifecycle event is not refused.

    THE BIRTH REFUSAL THIS EXISTS TO KILL (metis-g102, 2026-08-05, reproduced in a
    clone). Both halves of the lifecycle write files that are semantic derivation
    inputs and are NOT owned by their own index transaction: retirement writes the
    transfer letter and flips the card; birth flips the card. The incremental paths
    (`--only` and the batch transaction) refuse whenever such an input has moved
    since the last full manifest, and the cure they name is a full `--apply`.
    NOTHING IN THE LIFECYCLE RAN ONE. So:

        retire  -> writes card + letter -> its `--only` freshen REFUSES (a finding;
                   retirement correctly proceeds) -> manifest is now stale
        birth   -> batch transaction REFUSES, exit 1, no record, NO IDENTITY ISSUED

    That is not intermittent. Every birth that follows a retirement was refused, which
    is every birth there is. Mine was. I cleared it by hand with a full `--apply` and
    very nearly wrote it up as a one-off.

    IT IS THE RULED-OUT CLASS WEARING A DIFFERENT HAT. The identity gates were made
    incapable of refusing a birth — a failed check marks the entry provisional and the
    agent is BORN. The INDEX layer was never brought under that ruling, and it refuses
    harder than the gates ever did: a provisional birth still writes a record and issues
    a number, while this writes nothing at all. Mike's bar, verbatim: "I NEVER EVER want
    to see my agents telling me they are failing to boot. Denied because of ceremony
    that protects nothing."

    THE SHAPE IS PIN 13's, EXACTLY: weld the reconcile to the terminal transition rather
    than leaving it to whoever booted next to notice. Best-effort by construction — a
    failure here is a finding with a named cure, never a refusal, and never a reason to
    unwind a lifecycle event that already landed.
    """
    script = vault_root / "vault" / "tools" / "tropo-rebuild-index.py"
    index = vault_root / "vault" / "00-index.jsonl"
    if not script.is_file() or not index.is_file():
        return  # no projection lives here to keep consistent
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--apply"],
            cwd=str(vault_root), capture_output=True, text=True,
            timeout=_RECONCILE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        findings.record(
            "index left stale for the next lifecycle event",
            f"the post-write full rebuild did not run: {exc}. This event landed, but the "
            "NEXT birth or retirement in this studio will be refused by the index "
            f"transaction until someone runs `python3 vault/tools/tropo-rebuild-index.py "
            f"--apply` from {vault_root}.",
        )
        return
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        findings.record(
            "index left stale for the next lifecycle event",
            f"the post-write full rebuild exited {proc.returncode}"
            + (f": {detail[-1]}" if detail else "")
            + ". This event landed, but the NEXT birth or retirement in this studio will "
            "be refused by the index transaction until it succeeds: run "
            f"`python3 vault/tools/tropo-rebuild-index.py --apply` from {vault_root}.",
        )
        return
    # The incremental freshen above this call cannot succeed at a retirement, and its
    # failure is exactly what this rebuild just repaired. Say so rather than leaving a
    # cured alarm standing on a clean record.
    findings.resolve(
        "index freshen failed",
        "the incremental freshen could not own the card and the transfer letter; the "
        "full rebuild that followed derived them. The index is current.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Mint an activation: issue this agent's identity and write its record. "
            "Records every check it could not pass and proceeds anyway; the single "
            "refusal is a malformed --agent-class, because without a class there is no "
            "identity to record."
        ),
        epilog=(
            "The number is issued here, never claimed by the caller: it is the highest "
            "known locally for this slug plus one. There is deliberately no flag for it "
            "— an agent asks to activate and is told what it is, so there is no claim to "
            "verify and no mismatch to halt on."
        ),
    )
    parser.add_argument("--agent", required=True, help="agent slug")
    parser.add_argument("--authorized-by", required=True,
                        help="authorizing principal, or the parent activation UID")
    parser.add_argument("--agent-class", default=None,
                        help="one of " + " / ".join(VALID_CLASSES)
                             + "; read from this agent's own history when omitted")
    parser.add_argument("--agent-root", default="", help="Level-1 agent root project UID")
    parser.add_argument("--model", default="", help="sleeve identifier")
    parser.add_argument("--platform", default="", help="harness this session runs in")
    parser.add_argument("--member-of", default="", help="comma-separated UIDs")
    parser.add_argument("--run-folder", default="", help="playbook-runs/<run>/ path")
    parser.add_argument("--vault-root", default=str(STUDIO_ROOT),
                        help="studio root to write into (defaults to this tool's own)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # THE ONE REFUSAL. Everything below this line records and proceeds.
    if args.agent_class is not None and args.agent_class not in VALID_CLASSES:
        print(
            f"ERROR: agent_class {args.agent_class!r} is not one of {list(VALID_CLASSES)}. "
            "This is the only refusal this tool has: a provisional entry can record a "
            "broken lineage, an unreachable predecessor or an unreadable history, but "
            "without a class there is no identity for it to record at all.",
            file=sys.stderr,
        )
        return 2

    findings = Findings()
    vault_root = Path(args.vault_root).expanduser().resolve()
    now = _dt.datetime.now(_dt.timezone.utc)
    # A full instant, never a bare date. A bare local date read as midnight UTC
    # over-stated record age by a whole timezone offset, which made every sub-agent
    # activation sweepable AT BIRTH; and an hourly threshold (sa.* is 2h) cannot be
    # computed against a date at all.
    activated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.strftime("%Y-%m-%d")

    slug = args.agent.strip()
    if not _SLUG_RE.match(slug):
        findings.record(
            "agent slug shape",
            f"{slug!r} is not the studio's slug shape (lowercase alphanumeric, then any "
            "of . _ -); the record is written as given, and readers keyed on the slug "
            "may not find it.",
        )

    history = read_history(vault_root, slug, findings)
    agent_class = resolve_agent_class(args.agent_class, history, findings)
    generation = issue_generation(history, slug, agent_class)

    if history.open_records:
        # ADR-016 used to HALT here. Rule 2 makes overlap normal — a new generation is a
        # child, not a replacement, and a parent is normally alive when the child is — so
        # this is a finding now. It stays loud because the usual cause is not a live
        # sibling but a predecessor whose session died without writing its handoff, and
        # the successor is the only one who can act on that.
        findings.record(
            "predecessor still open",
            f"agent {slug!r} has {len(history.open_records)} activation record(s) with "
            f"no handoff written: {history.open_records}. Overlap is legal; a session "
            "that ended without a transfer is not. Confirm which it is, and if the "
            "predecessor never retired, say so to the owner by name in your startup "
            "signal — that is the party who can act.",
        )

    entry_name = (
        generation.lower() if generation.lower().startswith(f"{slug.lower()}-")
        else f"{slug}-{generation.lower()}"
    )
    member_of: list[str] = []
    for candidate in [args.agent_root] + args.member_of.split(","):
        candidate = candidate.strip()
        if candidate and candidate not in member_of:
            member_of.append(candidate)

    try:
        uid = _MINT.mint(1, kind="file", extra_existing=history.known_uids)[0]
    except Exception as exc:
        # No identifier means no record and no identity — an inability, not a refusal.
        print(f"ERROR: could not mint an activation UID: {exc}", file=sys.stderr)
        return 1

    values: list[tuple[str, list[str]]] = [
        ("uid", [f"uid: {uid}"]),
        ("type", [f"type: {ENTRY_TYPE}"]),
        ("name", [f"name: {entry_name}"]),
        ("title", [f"title: {yaml_double_quote(f'{entry_name} — Activation ({today})')}"]),
        ("agent", [f"agent: {slug}"]),
        ("agent_class", [f"agent_class: {agent_class}"]),
        ("generation", [f"generation: {generation}"]),
        ("activated_at", [f"activated_at: {activated_at}"]),
        ("activated_by", [f"activated_by: {args.authorized_by}"]),
        ("status", ["status: active"]),
        # The durable reference an artifact carries is this UID, not the label. A
        # post-merge renumbering therefore renames no file, no filename, no Git object.
        ("created_by_activation_uid", [f"created_by_activation_uid: {uid}"]),
    ]

    # Optional context. Nothing is invented for what the caller did not say: an absent
    # field reads as "not recorded", which is rule 11's reader contract.
    for key, supplied in (("agent_root", args.agent_root), ("model", args.model),
                          ("platform", args.platform), ("run_folder", args.run_folder)):
        if supplied.strip():
            values.append((key, [f"{key}: {yaml_double_quote(supplied.strip())}"]))
    if history.predecessor_uid:
        # Omitted entirely at genesis: there is no predecessor, and an absent field says
        # that where a `null` reads like a link somebody lost.
        values.append(("predecessor_activation_uid",
                       [f"predecessor_activation_uid: {history.predecessor_uid}"]))
    values.append(("stale_threshold_hours", [
        "stale_threshold_hours: "
        + str(STALE_THRESHOLD_DEFAULTS.get(agent_class, DEFAULT_STALE_THRESHOLD_HOURS))
    ]))
    values.append((
        "member_of",
        ["member_of: []"] if not member_of
        else ["member_of:"] + [f"  - {yaml_double_quote(m)}" for m in member_of],
    ))
    values.extend(findings.frontmatter())

    pointers = [
        f"- **Activation UID:** `{uid}` — the durable reference; artifacts cite this, "
        "never the generation label.",
    ]
    if args.agent_root.strip():
        root_uid = args.agent_root.strip()
        pointers.append(f"- **Agent root project:** [`{root_uid}`]({root_uid}.md)")
    if history.predecessor_uid:
        pred = history.predecessor_uid
        pointers.append(f"- **Predecessor activation:** [`{pred}`]({pred}.md)")
    else:
        pointers.append("- **Predecessor activation:** none — genesis, the first "
                        "generation of this lineage.")
    if args.run_folder.strip():
        pointers.append(f"- **Run folder:** `{args.run_folder.strip()}`")

    leg = load_leg(vault_root, findings)
    record_text = render_record(leg, uid, values, pointers, today, entry_name, findings)

    files_dir = vault_root / "vault" / "files"
    out_path = files_dir / f"{uid}.md"
    index = vault_root / "vault" / "00-index.jsonl"
    freshener_script = vault_root / "vault" / "tools" / "tropo-rebuild-index.py"
    if index.is_file() and freshener_script.is_file():
        try:
            files_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(
                f"ERROR: could not prepare the activation source home at "
                f"{files_dir}: {exc}",
                file=sys.stderr,
            )
            return 1
        outcome = commit_indexed_activation(
            vault_root,
            uid,
            out_path,
            record_text,
            findings,
        )
        if outcome == COMMIT_SOURCE_ONLY and not out_path.exists():
            # The index declined; the agent does not. Place the record so an
            # identity exists, and let the finding carry the lag. Only a failure
            # HERE is fatal, because only here is the record itself unwritable.
            try:
                out_path.write_text(record_text, encoding="utf-8")
            except OSError as exc:
                print(
                    f"ERROR: the activation record at {out_path} cannot be written: "
                    f"{exc}. This is an inability, not a refusal — with no record "
                    "there is no identity to issue.",
                    file=sys.stderr,
                )
                return 1
        # THE GOVERNED PATH IS THE ONE REAL STUDIOS TAKE, AND IT WAS MISSING THE WELD
        # (metis-g102, 2026-08-05, found at my own birth). `sync_agent_card()` was added
        # below, on the fallback branch — which is only reached when `vault/00-index.jsonl`
        # is absent. That file is GITIGNORED, so it is absent in exactly one kind of
        # studio: a fresh throwaway clone. Vela V71 proved the Po-bug fix by cloning the
        # studio and running a real retire-then-birth, and the clone took the fallback
        # branch, so the fix worked there and has never once run in this studio. My own
        # card still read `status: RETIRED`, `generation: G101` after a clean,
        # non-provisional birth — and the crew brief renders FROM THE CARD.
        #
        # The author's environment is a kind of mock. Here it was the mock: the proof
        # environment was structurally the only branch the fix lived on.
        sync_agent_card(vault_root, uid, slug, generation, findings)
        reconcile_index_after_lifecycle_write(vault_root, findings)
        print(json.dumps({
            "activation_uid": uid,
            "generation": generation,
            "provisional": bool(findings),
            "findings": findings.items,
        }))
        print(f"activation: {out_path}", file=sys.stderr)
        findings.announce()
        return 0

    try:
        files_dir.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            raise FileExistsError(f"{out_path} already exists — impossible post-mint")
        out_path.write_text(record_text, encoding="utf-8")
    except OSError as exc:
        # Not a refusal — an inability. Nothing was recorded, so nothing was issued.
        print(f"ERROR: could not write the activation record at {out_path}: {exc}",
              file=sys.stderr)
        return 1

    # Everything above only created. Nothing here closes, sweeps, edits or deletes any
    # existing record — that is rule 3's premise, made true by construction rather than
    # by care.
    freshen_index(vault_root, uid, out_path, findings)
    # One fact, two homes, ONE gesture — the same rule the transfer's second home is
    # written under, and the half that birth was missing until 2026-08-05.
    sync_agent_card(vault_root, uid, slug, generation, findings)
    reconcile_index_after_lifecycle_write(vault_root, findings)

    print(json.dumps({
        "activation_uid": uid,
        "generation": generation,
        "provisional": bool(findings),
        "findings": findings.items,
    }))
    print(f"activation: {out_path}", file=sys.stderr)
    findings.announce()
    return 0


if __name__ == "__main__":
    sys.exit(main())
