#!/usr/bin/env python3
"""
---
uid: d7170a1d
title: validate-package-links — Tool
name: validate-package-links
type: tool
status: active
owner: talos
domain: Package link integrity — fails if shipped markdown links to files the recipient does not receive.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/tropo-validate-package-links.py [--strict] [--first-hour-only] [--json] <box-root>
script_path: vault/tools/tropo-validate-package-links.py
extraction_scope: ship
created: '2026-08-14'
created_by: talos-t41
modified: '2026-08-14'
modified_by: talos-t41
schema_version: 2
governed_by: 8dd772a0
refs:
- 62a22664
---

Shipped text that cites files a recipient does not have.

Five v1.87 packages were superseded in one evening, each on one instance of this
class found by one cold walk: a missing first-rebuild instruction, an
unresolvable governance reference, a stale template, an absent changelog. A
sweep of the built box then found 430 dead links across 47 shipped files, so the
class was never going to be exhausted by walking — at one finding per walk it is
another forty packages.

This converts the class from "each walk finds one" into "the build can refuse
until zero", which is the move the portable-package guards already made for
machine-dependent bytes.

WHAT COUNTS AS DEAD. A relative markdown link, from a file inside the box, whose
target resolves inside the box and does not exist. Three things deliberately do
NOT count, because calling them defects would train people to ignore the report:

  placeholders   `[agent-name]`, `<uid>`, `<channel-name>` — instructions to a
                 reader, not addresses.
  directories    `boards/`, `decisions/` — folders a recipient creates by
                 working, absent because they have not started yet.
  outside links  http(s), mailto, and anything resolving outside the box, which
                 is someone else's business.

Findings are CLASSIFIED, because the classes have different cures and lumping
them produces a number nobody can act on:

  producing-studio-record   vault/files/<uid>.md that correctly never ships —
                            the text should state the UID, not link to it
  producing-studio-agent    agents/... from the Studio that built the release
  wrong-relative-path       the target ships, at a different path; the link is
                            wrong, not the package
  unshipped-path            everything else

`--first-hour-only` narrows to what a newcomer meets before they have done
anything: the root docs, the concierge, playbooks, skills and templates. That is
the subset Mike triaged to v1.88 when he accepted the full inventory as
non-blocking for v1.87.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
UID_RECORD = re.compile(r"vault/files/[0-9a-f]{8}\.md$")
PLACEHOLDER = re.compile(r"[\[<]")

#: What a recipient meets before they have done anything.
FIRST_HOUR = (
    "START-TROPO.md", "AGENT-ORIENTATION.md", "README.md", "CLAUDE.md",
    "GEMINI.md", "AGENTS.md", "TROPO-CAPABILITIES.md",
    ".tropo/concierge", ".tropo/playbooks", "vault/skills", "vault/templates",
)


def is_first_hour(rel: str) -> bool:
    return any(rel == surface or rel.startswith(surface + "/") for surface in FIRST_HOUR)


def classify(box: Path, target_rel: str) -> str:
    if UID_RECORD.search(target_rel):
        return "producing-studio-record"
    if target_rel.startswith("agents/") or "/agents/" in target_rel:
        return "producing-studio-agent"
    # The target may ship somewhere else entirely, which is a broken link rather
    # than absent content — a distinction worth making, because one is a text
    # fix and the other is a packaging fix.
    name = Path(target_rel).name
    if name and any(box.rglob(name)):
        return "wrong-relative-path"
    return "unshipped-path"


def scan(box: Path, first_hour_only: bool = False) -> list:
    findings = []
    for path in sorted(box.rglob("*.md")):
        rel = path.relative_to(box).as_posix()
        if first_hour_only and not is_first_hour(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in LINK.findall(text):
            link = raw.split("#")[0].strip()
            if not link or link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if PLACEHOLDER.search(link) or link.endswith("/"):
                continue
            target = (path.parent / link).resolve()
            try:
                target_rel = target.relative_to(box.resolve()).as_posix()
            except ValueError:
                continue  # points outside the package; not this checker's business
            if target.exists():
                continue
            findings.append({
                "source": rel,
                "link": link,
                "target": target_rel,
                "class": classify(box, target_rel),
                "first_hour": is_first_hour(rel),
            })
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when shipped markdown cites files the recipient does not receive.")
    parser.add_argument("box", help="root of the built box (or a Studio to check in place)")
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero on any finding (build-gate mode)")
    parser.add_argument("--first-hour-only", action="store_true",
                        help="only the surfaces a newcomer meets before doing anything")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    box = Path(args.box).resolve()
    if not box.is_dir():
        print(f"ERROR: not a directory: {box}", file=sys.stderr)
        return 2

    findings = scan(box, first_hour_only=args.first_hour_only)
    if args.json:
        print(json.dumps({"box": str(box), "count": len(findings),
                          "findings": findings}, indent=2))
    else:
        by_class: dict = {}
        for f in findings:
            by_class.setdefault(f["class"], []).append(f)
        scope = "first-hour surfaces" if args.first_hour_only else "all shipped markdown"
        print(f"package link integrity — {scope} under {box}")
        if not findings:
            print("  ✓ every relative link resolves inside the package")
            return 0
        for cls in sorted(by_class, key=lambda c: -len(by_class[c])):
            rows = by_class[cls]
            print(f"\n  {len(rows):4}  {cls}")
            for row in rows[:8]:
                mark = "!" if row["first_hour"] else " "
                print(f"      {mark} {row['source']} -> {row['link']}")
            if len(rows) > 8:
                print(f"        … and {len(rows) - 8} more")
        first = sum(1 for f in findings if f["first_hour"])
        print(f"\n  {len(findings)} dead link(s); {first} on first-hour surfaces.")
        print("  A recipient who follows one of these lands on a file they were never sent.")
    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
