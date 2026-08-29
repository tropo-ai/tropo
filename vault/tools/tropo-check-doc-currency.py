#!/usr/bin/env python3
"""Check that every path a shipped instruction file tells a reader to use exists.

WHY THIS EXISTS
---------------
A stranger concierge ("Po") read a shipped v1.92.0 playbook and recommended a
coordination model retired at v1.61 — quoting our own documentation correctly.
Its self-diagnosis named the rule this tool mechanises:

    "A playbook being present and readable is not the same as a playbook being
     current."
    "When a playbook's stated rule and a governed folder's actual contents
     disagree, the folder wins."

Every instrument this Studio built to check itself reads its own substrate. This
one reads what we SHIP and asks a question with a world-state answer: does the
path this file tells a reader to open actually exist there?

WHAT IT DOES NOT DO
-------------------
It does not count keyword hits. A first cut of this measurement reported 61 dead
`channels/` references across 14 shipped playbooks; inspection showed a large
share were RETIREMENT NOTICES — prose correctly telling the reader the path is
gone — which is the documentation working, not failing. Counting those as
defects is the same error as a grep reporting 211 files carrying a retired
nav-block when the renderer's own detector found 2.

So references are classified by FORM, mechanically, and only the forms a reader
actually follows can fail the check:

    instruction  a markdown link target, a fenced-code line, or an imperative
                 step/bullet naming the path            -> ERROR when dead
    retired      the same line marks it retired/superseded/replaced
                                                        -> OK, this is correct
    prose        any other mention (history, examples)   -> advisory only

argus-a159, 2026-08-26. Findings b69415b1 (the measurement) and 2abcdf03 (the
walk that made looking outward the cycle's opening act).
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

# A reference worth checking looks like a path with a directory part. Bare
# filenames are excluded: too many false hits from prose naming a file.
INSTRUCTABLE_EXT = ("md", "py", "json", "jsonl", "yaml", "yml", "sh", "html")
PATH_RE = re.compile(
    r"(?<![\w./-])((?:\.?[\w][\w.-]*/)+[\w][\w.-]*\.(?:%s))(?![\w.-])"
    % "|".join(INSTRUCTABLE_EXT))

RETIRED_RE = re.compile(
    r"\b(retired|superseded|deprecated|no longer|replaced by|removed in|"
    r"used to|formerly|legacy)\b", re.IGNORECASE)

LINK_RE = re.compile(r"\]\(([^)]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")
STEP_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

INSTRUCTION, RETIRED, PROSE = "instruction", "retired", "prose"


def classify(line: str, ref: str, in_fence: bool) -> str:
    """Which form is this reference in? Mechanical, no judgment."""
    if RETIRED_RE.search(line):
        return RETIRED
    if in_fence:
        return INSTRUCTION
    if any(ref in target for target in LINK_RE.findall(line)):
        return INSTRUCTION
    in_code = any(ref in span for span in CODE_RE.findall(line))
    if in_code and STEP_RE.match(line):
        return INSTRUCTION
    if in_code:
        return PROSE
    return PROSE


def scan_text(text: str):
    """Yield (lineno, ref, form) for every path-shaped reference."""
    in_fence = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        for m in PATH_RE.finditer(line):
            ref = m.group(1)
            yield n, ref, classify(line, ref, in_fence)


class Box:
    """The thing we check against: an extracted tree or a .zip, read alike."""

    def __init__(self, target: Path):
        self.target = target
        self.zip = None
        if target.is_file() and target.suffix == ".zip":
            self.zip = zipfile.ZipFile(target)
            names = self.zip.namelist()
            roots = {n.split("/", 1)[0] for n in names if "/" in n}
            # A box may or may not carry a single top-level folder.
            self.prefix = (roots.pop() + "/") if len(roots) == 1 else ""
            self.names = {n[len(self.prefix):] for n in names
                          if n.startswith(self.prefix)}
        elif not target.is_dir():
            raise SystemExit("[MISUSE] not a directory or .zip: %s" % target)

    def exists(self, rel: str, relative_to: str = "") -> bool:
        """True if the path resolves from the box root OR from the
        referencing file's own directory. Instruction files write sibling
        references constantly; root-only resolution called four shipped
        concierge paths missing."""
        if self._exists_at(rel):
            return True
        if relative_to and "/" in relative_to:
            base = relative_to.rsplit("/", 1)[0]
            return self._exists_at(base + "/" + rel.lstrip("/"))
        return False

    def locate_elsewhere(self, rel: str) -> str:
        """Where a dead reference's file actually lives in this box, if it
        lives anywhere. `vault/playbooks/x.md` naming
        `concierge-paths/create-an-agent.playbook.md` is not a MISSING file —
        the file ships, at `.tropo/playbooks/concierge-paths/...`. A reader
        still cannot follow it, but 'we shipped it to the wrong path' and
        'we never shipped it' have different cures, and reporting them as
        one number overstates the second."""
        tail = rel.lstrip('./')
        names = self.names if self.zip is not None else (
            str(q.relative_to(self.target))
            for q in self.target.rglob('*') if q.is_file())
        for name in names:
            if name.endswith('/' + tail):
                return name
        return ''

    def _exists_at(self, rel: str) -> bool:
        # NOT lstrip("./") — that strips CHARACTERS, so ".tropo/version.md"
        # became "tropo/version.md" and every dotfile path read as ABSENT.
        # Caught by checking one suspicious hit against the filesystem
        # instead of reporting it (argus-a159, first run of this tool).
        while rel.startswith("./"):
            rel = rel[2:]
        if self.zip is not None:
            return rel in self.names or (rel + "/") in self.names
        return (self.target / rel).exists()

    def read(self, rel: str) -> str:
        if self.zip is not None:
            return self.zip.read(self.prefix + rel).decode("utf-8", "replace")
        return (self.target / rel).read_text(errors="replace")

    def instruction_files(self, globs):
        for pattern in globs:
            if self.zip is not None:
                rx = re.compile(pattern.replace(".", r"\.").replace("*", "[^/]*"))
                for name in sorted(self.names):
                    if rx.fullmatch(name):
                        yield name
            else:
                for p in sorted(self.target.glob(pattern)):
                    yield str(p.relative_to(self.target))


GENERATED_AT_BOOT = (
    "vault/00-index.jsonl",
    "vault/00-index.sqlite",
    "vault/00-project-tree.jsonl",
    "vault/00-archive-index.jsonl",
    "shared/orientation/daily-health-report.md",
)

DEFAULT_GLOBS = ("vault/playbooks/*.md", ".tropo/playbooks/*.md",
                 ".tropo/playbooks/concierge-paths/*.md")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", default=".",
                    help="the Studio to check: a directory or a release .zip")
    ap.add_argument("--glob", action="append", default=None,
                    help="instruction-file glob (repeatable; defaults cover playbooks)")
    ap.add_argument("--show-prose", action="store_true",
                    help="also list advisory prose/historical references")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    box = Box(Path(args.target).expanduser())
    globs = args.glob or list(DEFAULT_GLOBS)

    dead_instructions, dead_prose, retired_ok, generated = [], [], 0, 0
    files_scanned = 0

    for rel in box.instruction_files(globs):
        files_scanned += 1
        try:
            text = box.read(rel)
        except Exception:
            continue
        for lineno, ref, form in scan_text(text):
            if box.exists(ref, relative_to=rel):
                continue
            if ref in GENERATED_AT_BOOT:
                generated += 1
                continue
            if form == RETIRED:
                retired_ok += 1
            elif form == INSTRUCTION:
                dead_instructions.append(
                    (rel, lineno, ref, box.locate_elsewhere(ref)))
            else:
                dead_prose.append((rel, lineno, ref))

    if args.json:
        import json
        print(json.dumps({
            "target": str(box.target),
            "files_scanned": files_scanned,
            "dead_instructions": [
                {"file": f, "line": n, "ref": r,
                 "ships_at": e or None, "class": "misrouted" if e else "absent"}
                for f, n, r, e in dead_instructions],
            "dead_prose_count": len(dead_prose),
            "retired_notices_ok": retired_ok,
            "generated_at_boot": generated,
        }, indent=2))
        return 1 if dead_instructions else 0

    print("doc-currency: %s" % box.target)
    print("  instruction files scanned: %d" % files_scanned)
    print("  retirement notices naming a gone path (correct, not a defect): %d"
          % retired_ok)
    print("  references to declared build-at-first-boot artifacts (correct): %d"
          % generated)
    print("  advisory prose/historical references to gone paths: %d" % len(dead_prose))
    print()
    if dead_instructions:
        absent = sum(1 for row in dead_instructions if not row[3])
        print("DEAD INSTRUCTIONS — a reader cannot follow these (%d: %d absent "
              "from the box, %d shipped at another path):"
              % (len(dead_instructions), absent, len(dead_instructions) - absent))
        for f, n, r, elsewhere in dead_instructions:
            if elsewhere:
                print("  %s:%d  ->  %s   [MISROUTED: ships at %s]"
                      % (f, n, r, elsewhere))
            else:
                print("  %s:%d  ->  %s   [ABSENT from the box]" % (f, n, r))
    else:
        print("No dead instructions. Every path an instruction file tells a "
              "reader to use exists in this box.")
    if args.show_prose and dead_prose:
        print()
        print("advisory (not failing):")
        for f, n, r in dead_prose:
            print("  %s:%d  ->  %s" % (f, n, r))
    return 1 if dead_instructions else 0


if __name__ == "__main__":
    sys.exit(main())
