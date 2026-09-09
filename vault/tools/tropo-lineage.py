#!/usr/bin/env python3
"""
---
uid: 5b2e91c7
name: tropo-lineage
type: tool
title: "tropo-lineage — an agent's whole lifecycle, in one file it can read"
status: active
owner: metis
domain: "Agent birth and retirement. Append a line, read a line. Nothing else."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-lineage.py"
script_path: vault/tools/tropo-lineage.py
created: '2026-08-06'
created_by: metis-g102
version: "0.3"
version_note: '0.3 (argus-a175, f015f176a9d4): a first live birth claims the sole unretired studio-genesis placeholder once; original lineage is preserved and later generations advance normally. Prior 0.2 (talos-t46, 5fffbbe9 AC6): best-effort lifecycle-field sync onto the unified entry after the append — status/generation/predecessor/last_session/last_updated/born_at/retired_at, frontmatter only, body and voice untouched, every failure a swallowed warning. The lineage line remains the only record; the card is a convenience surface.'
schema_version: 2
extraction_scope: ship
---

THE WHOLE LIFECYCLE:

    born    read the file, take the highest number, add one, append a line
    retire  place the letter, append a line
    who     read the last line

That is it. There is no index, no mint, no card, no registry, no transaction,
no lock file, no journal, no receipt. Nothing here can refuse an agent. The
only thing that stops a birth is a disk that cannot be written to, and that is
not a refusal, it is the world saying no.

One crew broadcast IS emitted, on both born and retire, and it is swallowed
whole: a broken emitter, a missing tool or a malformed event costs the crew a
notification and costs the lineage nothing. See announce() below.
(This paragraph said "no event" from ad3afaf0 until 2026-08-06. 81ba7a55 added
announce() twelve lines down and did not revisit the sentence above it. Talos
T39 read the claim at Group 0, believed it, and then found his own birth
broadcast in his event drain twenty minutes later.)

WHY THIS FILE IS SHORT ON PURPOSE. The design it replaces grew through seven
adversarial reviews into an operation journal, receipt records, a resumption
scan, a canonical request hash and a seven-point crash matrix. Every finding
behind that machinery was correct. Nobody ever asked what the failure actually
COST. It cost a duplicate line in an append-only file: visible, harmless, and
fixed by appending a correction. We specified a two-phase commit to protect a
log whose defining property is that it does not need one.

THE THREE THINGS THAT DO REAL DAMAGE, and they are the only defences here:

  1. Overwriting a predecessor's letter. It cannot be reconstructed. So a
     letter is placed with link(), which fails if the name is taken.
  2. Guessing a number out of a file we cannot read. So an unreadable file
     stops the birth instead of inventing a generation.
  3. Reaching the index. Every birth failure this studio has ever had came
     from the index being on this path. This file imports nothing but the
     standard library. That is the whole defence, and it is enforced by a test.

Everything else is allowed to go wrong, because everything else is repairable
by a human reading a text file.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.governed_path import UID_HEX_PATTERN, is_governed_uid_shape  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GEN_RE = re.compile(r"^([A-Za-z.\-_]*?)(\d+)$")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lineage_path(root, agent):
    return root / "agents" / agent / "lineage.jsonl"


def read_lines(path):
    """Every valid line, in order. An unreadable line stops us; see reason 2."""
    if not path.exists():
        return []
    out = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw))
        except ValueError:
            raise SystemExit(
                f"cannot read {path} line {n}: it is not valid JSON.\n"
                f"Refusing to guess a generation number from a file I cannot read. "
                f"Nothing was written. Fix or remove that line by hand."
            )
    return out


def split_gen(gen):
    m = GEN_RE.match(str(gen or ""))
    return (m.group(1), int(m.group(2))) if m else ("G", 0)


def next_generation(lines, default_prefix="G"):
    births = [l for l in lines if l.get("t") == "born"]
    if not births:
        return f"{default_prefix}1"
    prefix, highest = default_prefix, 0
    for b in births:
        p, n = split_gen(b.get("gen"))
        if n > highest:
            prefix, highest = (p or default_prefix), n
    return f"{prefix}{highest + 1}"


def append(path, record):
    """One complete line, appended and flushed to disk. Never a rewrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _retirement_body(root, agent, record, headline):
    """Build the retirement notice body playbook e2c7d185 step 7 specifies.

    Two to four sentences, and pointers to the letter and (if written) the
    reflection. Every lookup here is a plain existence check on a path this
    tool already knows, because announce() runs AFTER the lineage line is on
    disk and nothing in it may turn a completed close into a failure.

    The letter is resolved two ways on purpose. `--letter` records its
    destination on the record, but an agent who authors the letter directly at
    its canonical home closes WITHOUT that flag (the tool refuses to place over
    an existing slot), which is the documented path and is how metis-g115
    closed. So a missing `letter` key is not evidence of a missing letter:
    fall back to the canonical `transfers/<GEN>.md` home and check the disk.
    """
    gen = str(record.get("gen") or "")
    sentences = [f"{headline}."]

    note = str(record.get("note") or "").strip()
    if note:
        # The retiring agent's own one-line summary of the generation. This is
        # the substance the crew actually wants in a drain, and it is already
        # on the record; the old body threw it away.
        sentences.append(note if note.endswith(".") else note + ".")

    letter_rel = record.get("letter")
    if not letter_rel and gen:
        candidate = root / "agents" / agent / "transfers" / f"{gen}.md"
        if candidate.is_file():
            letter_rel = f"agents/{agent}/transfers/{gen}.md"
    if letter_rel:
        sentences.append(f"Letter: {letter_rel}")

    if gen:
        reflection_rel = f"agents/{agent}/reflections/{gen.lower()}-reflection.md"
        if (root / reflection_rel).is_file():
            sentences.append(f"Reflection: {reflection_rel}")

    sentences.append(f"Lineage: agents/{agent}/lineage.jsonl")
    return " ".join(sentences)


def announce(root, agent, record):
    """Tell the crew. AFTER the line is on disk, and it can never affect the birth.

    Mike's requirement, 2026-08-05: one gesture writes both homes. The lineage
    file answers "who is this agent and what is their history". The event log
    answers "what happened across the crew, in order". Different questions, so
    they are two purposes rather than two copies — the event carries only
    identifiers and points at the lineage.

    Everything here is swallowed. A broken emitter, a missing tool, a malformed
    marker: none of them may turn a completed birth into a failure. The line is
    already on disk before this runs, so the worst case is a crew that has not
    heard yet, which a human can see and re-send.
    """
    tool = root / "vault" / "tools" / "tropo-emit-event.py"
    if not tool.is_file():
        return None
    import subprocess  # deliberately local: unreachable until after the append
    verb = "was born" if record["t"] == "born" else "retired"
    # A broadcast with no readable line renders as a BLANK ROW in every agent's
    # drain (metis-g102, seen in my own inbox from talos's retirement, 2026-08-06).
    # The crew reads this in a list; give them the sentence, not just the fields.
    headline = f"{agent} {record['gen']} {verb}"
    # S4 AC4(b) (29506520), argus-a154 2026-08-23. This payload is shared by BIRTH and
    # RETIREMENT, and it hard-coded `crew-state` for both. Playbook e2c7d185 §Required
    # Practice step 8 requires the retirement notice carry `category: retirement`, so the
    # tool satisfied the events capsule and broke the playbook — and every agent who
    # followed its output inherited the wrong value. Measured 2026-08-23 across both agent
    # lines: not ONE retirement notice carried the required value, including the tool's.
    # `retirement` became a declared value at events.capsule v1.12 (same spec's lock as
    # authority); this is the writer half landing behind that reconciliation, never ahead
    # of it. Birth keeps crew-state: the playbook mandates nothing for a birth.
    category = "retirement" if record["t"] == "retired" else "crew-state"
    # metis-g116, 2026-09-01. The `category` half of this payload was cured by
    # argus-a154 above; the BODY one line below it was not, and it is the half
    # playbook e2c7d185 step 7 actually specifies: "body 2-4 sentences, pointers
    # to the letter (and reflection if you wrote one)". The hard-coded body
    # pointed at the lineage file and named neither. Measured across the whole
    # event log at G116's boot: of 101 retirement broadcasts ever emitted, 37
    # carried a pointer to the letter; seven of the last ten named retirements
    # (A164, O36, T55, O37, T56, A165, G115) shipped this boilerplate alone.
    # The two that met the step (T54, T57) did it by hand-emitting a SECOND
    # broadcast beside the tool's. So the tool and the playbook were two writers
    # of one fact, the tool made the step LOOK done (right type, right category,
    # legal headline), and the letter — the artifact the playbook says to spend
    # most of retirement on — was the one thing the announcement never linked.
    # Same defect family, same function, one line apart, sixteen days later.
    body = f"{headline}. Lineage: agents/{agent}/lineage.jsonl"
    if record["t"] == "retired":
        body = _retirement_body(root, agent, record, headline)
    payload = {"category": category, "agent": agent, "gen": record["gen"],
               "t": record["t"], "headline": headline,
               "body": body,
               "lineage": f"agents/{agent}/lineage.jsonl"}
    # A11 (00d776ae W1): birth/retirement broadcasts rendered as BLANK rows in
    # every drain — the emit carried no --subject, so the crew's list surfaces
    # showed `subj=` with nothing anchoring the row. The subject is the
    # announcing agent's OWN party UID (the retire-tool's own broadcast already
    # carries it; announce() is the straggler). Unresolvable party → emit as
    # before (subject-less): the broadcast itself must never fail on this.
    subject_args = []
    entry = resolve_entry(root, agent)
    if entry:
        pm = re.search(r"^party_uid:\s*(%s)\s*$" % UID_HEX_PATTERN,
                       entry.read_text(encoding="utf-8"), re.MULTILINE)
        if pm:
            subject_args = ["--subject", pm.group(1)]
    try:
        r = subprocess.run(
            [sys.executable, str(tool), "--type", "tropo.broadcast.crew",
             "--source", f"/agents/{agent}", "--as", agent,
             "--lifecycle", "evergreen"] + subject_args +
            ["--data", json.dumps(payload)],
            capture_output=True, text=True, timeout=30, cwd=str(root))
        return None if r.returncode == 0 else "crew broadcast failed; lineage is unaffected"
    except Exception:
        return "crew broadcast could not run; lineage is unaffected"


def unmerged_note(root):
    """Say so when this line lands somewhere the crew cannot read.

    Vela V72 was born correctly on a Cursor Cloud branch on 2026-08-05 and the
    commit never reached main. The tool worked, the record was right, and for
    two hours the crew brief and every other agent saw V71 RETIRED. Not a
    refusal and not a duplicate -- a correct record nobody could see. An agent
    cannot act on something it was never told, so we tell it.

    Swallowed exactly like announce(), and for the same reason: the line is
    already on disk. A missing git, a detached HEAD, a worktree that is not a
    repo -- none of them may turn a completed birth into a failure. This only
    ever ADDS a sentence to the notes an agent already prints.
    """
    import subprocess  # deliberately local: unreachable until after the append
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=str(root))
        if r.returncode != 0:
            return None
        branch = r.stdout.strip()
    except Exception:
        return None
    if not branch or branch in ("main", "HEAD"):
        return None
    return (f"this line is on branch '{branch}', not main. The crew reads main "
            f"-- push or merge it, or to everyone else you were never born.")


def current(lines):
    """The live generation, or None. The last birth wins; a later retirement closes it."""
    live = None
    for l in lines:
        if l.get("t") == "born":
            live = dict(l, retired=False)
        elif l.get("t") == "retired" and live and l.get("gen") == live.get("gen"):
            live["retired"] = True
    return live


def resolve_entry(root, agent):
    """The unified entry at vault/agents/<uid>.md, via the activation pointer's
    agent_uid:. None when the pointer or the entry is absent — an agent without
    a card still has a complete lifecycle in the lineage file."""
    pointer = root / "agents" / agent / f"{agent}-activation.md"
    if not pointer.is_file():
        return None
    # THE SHAPE COMES FROM THE AUTHORITY, never a literal. This read
    # ``[0-9a-fA-F]{8}`` until 2026-09-01, so resolve_entry() returned None for
    # ANY agent minted after the Stage B flip -- the lineage tool could not find
    # that agent's own identity entry. Cal and Darin are minted composite at
    # genesis, so this would have bitten the companions on their first boot.
    m = re.search(r"^agent_uid:\s*(%s)\s*$" % UID_HEX_PATTERN,
                  pointer.read_text(encoding="utf-8"), re.MULTILINE)
    # UID_HEX_PATTERN's [0-9a-fA-F] accepts uppercase; is_governed_uid_shape
    # (the predicate, not the embedded regex) is lowercase-only. A case-
    # mismatched agent_uid must not resolve at all -- on a case-insensitive
    # filesystem it could otherwise open a DIFFERENT-cased path that happens
    # to be the same file, reading real content under an unverified name.
    if not m or not is_governed_uid_shape(m.group(1)):
        return None
    entry = root / "vault" / "agents" / f"{m.group(1)}.md"
    return entry if entry.is_file() else None


def sync_entry(root, agent, fields):
    """Best-effort lifecycle-field sync onto the unified entry (5fffbbe9 AC6).

    Runs AFTER the lineage line is durably appended, so a card that is missing,
    malformed, or read-only can only cost a warning on stderr — never the
    lineage, never the exit code, and never a rollback. Touches the frontmatter
    lifecycle fields only; body and voice are preserved byte-for-byte, because
    the card is a convenience surface and the lineage file is the record.
    """
    entry = resolve_entry(root, agent)
    if entry is None:
        print(f"note: no unified entry resolved for {agent}; lifecycle fields "
              f"not synced — lineage is the record and is unaffected",
              file=sys.stderr)
        return False
    try:
        if not os.access(entry, os.W_OK):
            raise ValueError("entry is not writable")
        text = entry.read_text(encoding="utf-8")
        fm = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
        if not fm:
            raise ValueError("entry has no frontmatter block")
        out, seen = [], set()
        for line in fm.group(1).split("\n"):
            key = line.split(":", 1)[0].strip() if ":" in line else None
            if key in fields:
                # A None value REMOVES the field (S3 f0153e0eb53e, 2026-09-05):
                # born clears the predecessor's retired_at, so an active entry
                # never reads retired-before-born — one fact, two fields, both
                # updated.
                if fields[key] is not None:
                    out.append(f"{key}: {fields[key]}")
                seen.add(key)
            else:
                out.append(line)
        for key, val in fields.items():
            if key not in seen and val is not None:
                out.append(f"{key}: {val}")
        new_text = "---\n" + "\n".join(out) + "\n---\n" + text[fm.end():]
        tmp = entry.with_suffix(".md.tmp")
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, entry)
        return True
    except (OSError, ValueError) as e:
        print(f"note: lifecycle field sync skipped for {agent} ({e}); "
              f"lineage is the record and is unaffected", file=sys.stderr)
        return False


def today():
    return now()[:10]


def cmd_born(args):
    root = Path(args.root).resolve()
    path = lineage_path(root, args.agent)
    lines = read_lines(path)
    births = [row for row in lines if row.get("t") == "born"]
    claim = (len(births) == 1 and births[0].get("by") == "studio-genesis"
             and GEN_RE.fullmatch(str(births[0].get("gen") or "")) is not None
             and args.by != "studio-genesis"
             and not any(row.get("t") == "retired"
                         and row.get("gen") == births[0].get("gen") for row in lines))
    gen = births[0]["gen"] if claim else next_generation(lines, args.prefix)

    open_gen = current(lines)
    notes = []
    if claim:
        notes.append("claimed unlived genesis placeholder; generation unchanged")
    elif open_gen and not open_gen["retired"]:
        notes.append(f"{open_gen['gen']} never retired; recorded, not blocked")

    prev = None
    for l in lines:
        if l.get("t") == "born":
            prev = l.get("gen")

    record = {"t": "born", "gen": gen, "at": now(), "by": args.by}
    if args.model:
        record["model"] = args.model
    if notes:
        record["notes"] = notes
    append(path, record)
    born_fields = {"status": "active", "generation": gen,
                   "last_session": f"'{today()}'",
                   "last_updated": f"'{today()}'",
                   "born_at": f"'{record['at']}'",
                   # S3 (f0153e0eb53e): retire wrote retired_at; a birth must clear
                   # it or the active entry reads retired-before-born forever.
                   "retired_at": None}
    if claim:
        born_fields["predecessor"] = None
    elif prev:
        born_fields["predecessor"] = prev
    if args.model:
        # metis-g111 2026-08-23: the sleeve is a lifecycle fact the lineage line already
        # carries; without this the entry's model: goes stale on every sleeve change.
        born_fields["model"] = args.model
    sync_entry(root, args.agent, born_fields)
    told = announce(root, args.agent, record)
    if told:
        notes.append(told)
    stranded = unmerged_note(root)
    if stranded:
        notes.append(stranded)

    print(json.dumps({"generation": gen, "agent": args.agent, "notes": notes}))
    for n in notes:
        print(f"note: {n}", file=sys.stderr)
    return 0


def cmd_retire(args):
    root = Path(args.root).resolve()
    path = lineage_path(root, args.agent)
    lines = read_lines(path)
    live = current(lines)
    if not live:
        raise SystemExit(f"{args.agent} has no recorded birth; nothing to retire.")
    gen = live["gen"]

    letter_ref = None
    if args.letter:
        src = Path(args.letter)
        if not src.is_file():
            raise SystemExit(f"letter not found: {src}")
        # An empty source is a bad source, and it must be refused BEFORE the
        # placement: the destination slot is create-only because a letter
        # cannot be reconstructed, so placing a truncated letter permanently
        # consumes the irreplaceable slot — the exact harm refusal exists for
        # (A152 review pass 1, F1; sanctioned by AC2's "bad letter source").
        if not src.read_text(encoding="utf-8", errors="replace").strip():
            raise SystemExit(
                f"letter source is empty: {src}. Nothing was placed — an empty "
                f"letter would permanently consume the create-only slot at "
                f"transfers/{gen}.md. Write the real letter and re-run.")
        dest = root / "agents" / args.agent / "transfers" / f"{gen}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)

        # AC4 (b1e78abb, v1.92): a letter already authored IN PLACE at its
        # own create-only destination is not a collision to refuse — it is
        # the retirement's actual letter, and refusing it is the defect
        # A154, A155 and T49 each hand-worked around. The occupied
        # destination is accepted ONLY when it IS this source: identity by
        # samefile() (the ordinary in-place case — one file, one inode) or
        # by equal content (a defensive fallback if inode identity doesn't
        # hold for some reason but the bytes are the same letter). A
        # DIFFERENT source against an occupied destination still refuses
        # unconditionally — this is idempotent-accept, never overwrite; the
        # create-only guarantee (a letter can never be reconstructed) is
        # untouched.
        if dest.exists():
            same = False
            try:
                same = os.path.samefile(src, dest)
            except OSError:
                same = False
            if not same:
                same = (
                    dest.read_text(encoding="utf-8", errors="replace")
                    == src.read_text(encoding="utf-8", errors="replace")
                )
            if not same:
                raise SystemExit(
                    f"{dest} already exists and was not replaced. "
                    f"{gen}'s letter is already written; nothing was changed."
                )
            # Identity confirmed: dest already correctly holds this letter.
            # Nothing to write — writing identical bytes over an existing
            # create-only file would be a no-op at best and a needless
            # mtime/inode churn at worst.
        else:
            tmp = dest.with_suffix(".md.tmp")
            tmp.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            try:
                # link() fails if the name is taken. Reason 1: a letter is
                # never overwritten, because it cannot be reconstructed.
                # rename() would silently replace it.
                os.link(tmp, dest)
            except FileExistsError:
                # A concurrent writer placed dest between our check above
                # and this call — same refusal, not a crash. Idempotent-
                # accept is handled by the branch above; a fresh race here
                # is exactly the collision that guard exists to catch.
                tmp.unlink(missing_ok=True)
                raise SystemExit(
                    f"{dest} already exists and was not replaced. "
                    f"{gen}'s letter is already written; nothing was changed."
                )
            finally:
                tmp.unlink(missing_ok=True)
        letter_ref = str(dest.relative_to(root))

    record = {"t": "retired", "gen": gen, "at": now()}
    if letter_ref:
        record["letter"] = letter_ref
    if args.note:
        record["note"] = args.note
    append(path, record)
    sync_entry(root, args.agent,
               {"status": "retired",
                "last_session": f"'{today()}'",
                "last_updated": f"'{today()}'",
                "retired_at": f"'{record['at']}'"})
    notes = []
    told = announce(root, args.agent, record)
    if told:
        notes.append(told)
    stranded = unmerged_note(root)
    if stranded:
        notes.append(stranded)
    for n in notes:
        print(f"note: {n}", file=sys.stderr)

    print(json.dumps({"generation": gen, "agent": args.agent,
                      "letter": letter_ref, "notes": notes}))
    return 0


def cmd_who(args):
    lines = read_lines(lineage_path(Path(args.root).resolve(), args.agent))
    live = current(lines)
    print(json.dumps(live or {}, sort_keys=True))
    return 0


def cmd_log(args):
    root = Path(args.root).resolve()
    for l in read_lines(lineage_path(root, args.agent)):
        mark = "born   " if l.get("t") == "born" else "retired"
        extra = l.get("letter") or l.get("note") or ""
        print(f"{l.get('at','?')}  {mark}  {l.get('gen','?'):<6} {extra}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="tropo-lineage.py",
        description="An agent's lifecycle: append a line to be born, append a line to retire.",
    )
    p.add_argument("--root", default=str(ROOT), help="studio root")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("born", help="issue the next generation and record it")
    b.add_argument("--agent", required=True)
    b.add_argument("--by", required=True, help="who authorised this")
    b.add_argument("--model", default=None)
    b.add_argument("--prefix", default="G", help="generation prefix for a first birth")
    b.set_defaults(fn=cmd_born)

    r = sub.add_parser("retire", help="place the letter and close the generation")
    r.add_argument("--agent", required=True)
    r.add_argument("--letter", default=None, help="path to the letter for the successor")
    r.add_argument("--note", default=None)
    r.set_defaults(fn=cmd_retire)

    w = sub.add_parser("who", help="the live generation")
    w.add_argument("--agent", required=True)
    w.set_defaults(fn=cmd_who)

    g = sub.add_parser("log", help="the whole lineage")
    g.add_argument("--agent", required=True)
    g.set_defaults(fn=cmd_log)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
