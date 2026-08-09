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
version: "0.1"
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
    payload = {"category": "crew-state", "agent": agent, "gen": record["gen"],
               "t": record["t"], "headline": headline,
               "body": f"{headline}. Lineage: agents/{agent}/lineage.jsonl",
               "lineage": f"agents/{agent}/lineage.jsonl"}
    try:
        r = subprocess.run(
            [sys.executable, str(tool), "--type", "tropo.broadcast.crew",
             "--source", f"/agents/{agent}", "--as", agent,
             "--lifecycle", "evergreen", "--data", json.dumps(payload)],
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


def cmd_born(args):
    root = Path(args.root).resolve()
    path = lineage_path(root, args.agent)
    lines = read_lines(path)
    gen = next_generation(lines, args.prefix)

    open_gen = current(lines)
    notes = []
    if open_gen and not open_gen["retired"]:
        notes.append(f"{open_gen['gen']} never retired; recorded, not blocked")

    record = {"t": "born", "gen": gen, "at": now(), "by": args.by}
    if args.model:
        record["model"] = args.model
    if notes:
        record["notes"] = notes
    append(path, record)
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
        dest = root / "agents" / args.agent / "transfers" / f"{gen}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".md.tmp")
        tmp.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            # link() fails if the name is taken. Reason 1: a letter is never
            # overwritten, because it cannot be reconstructed. rename() would
            # silently replace it.
            os.link(tmp, dest)
        except FileExistsError:
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
