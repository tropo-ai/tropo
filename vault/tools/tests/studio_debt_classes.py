#!/usr/bin/env python3
"""Split a `tropo-validate` run into named classes, so a delta can be itemized.

talos-t40, 2026-08-09, velocity item 3 of the v1.86 retrospective.

WHAT THIS FIXES. The debt ratchet printed one number. When it refused, it said
"studio debt UP 5, from 504 to 509" and told the reader to go run the validator
and find the five themselves — roughly 2,000 lines of output and about an hour
of archaeology on release night. A gate that knows something is wrong and will
not say what makes the human redo the work the machine already did.

THE CLASS KEY IS THE VALIDATOR'S OWN SECTION HEADING. `tropo-validate` already
prints `--- Name ---` before every check, so the grouping is not invented here:
it is the tool's existing structure, read back. That matters for curation — the
list a human maintains is a list of names they have already seen in the output,
not a taxonomy this file made up.

WHY CLASSES AND NOT JUST A TOTAL. Mike, during the v1.86 stage, verbatim:
"I honestly do not care if there is an open file in an inbox. This is an example
of overkill for doing a vault rebuild." A single total cannot express that. It
makes an inbox-hygiene finding and a UID collision the same event, so the only
way to stop being blocked by the one you do not care about is to raise the
ceiling for the one you do.
"""

from __future__ import annotations

import re
from typing import Iterable

#: `--- Section Name ---`, the heading tropo-validate prints before each check.
SECTION_RE = re.compile(r"^-{3}\s+(.*?)\s+-{3}\s*$")

#: A finding line. Severity in brackets, optionally indented under its check.
FINDING_RE = re.compile(r"^(\s*)\[(FAIL|ERROR|WARN|INFO|PASS)\]\s*(.*)$")

#: Severities that count as debt. WARN and INFO are reported but never gate:
#: the ratchet has always measured `failed`, and widening what counts while
#: changing how it is grouped would make one change look like the other.
DEBT_SEVERITIES = frozenset({"FAIL", "ERROR"})

#: A section name can carry a version tag that churns ("v1.68 S2", a UID). The
#: stable part is the prose before the first parenthesis, which is what a human
#: curating the list would recognise and type.
def class_key(section: str) -> str:
    """The durable half of a section heading.

    `Inbox Transition Protocol (v1.68 S2; 344607e4; HARD=...)` becomes
    `Inbox Transition Protocol`. Without this, curating a class would pin it to
    a version tag and the entry would silently stop matching at the next bump —
    the stale-constant shape this studio keeps paying for (velocity item 4).
    """
    head = section.split("(", 1)[0]
    return " ".join(head.split()).rstrip(" -;:") or section.strip()


def classify(output: str) -> dict[str, int]:
    """Count debt findings per class across a whole validator run.

    Lines before the first heading are attributed to `(preamble)` rather than
    dropped: a finding with nowhere to go is exactly the one that would slip
    through a per-class gate unnoticed.
    """
    counts: dict[str, int] = {}
    section = "(preamble)"
    for line in output.splitlines():
        heading = SECTION_RE.match(line)
        if heading:
            section = class_key(heading.group(1))
            continue
        finding = FINDING_RE.match(line)
        if finding and finding.group(2) in DEBT_SEVERITIES:
            counts[section] = counts.get(section, 0) + 1
    return counts


def findings_for(output: str, wanted: Iterable[str]) -> dict[str, list[str]]:
    """The actual finding lines for named classes — the itemized half."""
    want = set(wanted)
    out: dict[str, list[str]] = {name: [] for name in want}
    section = "(preamble)"
    for line in output.splitlines():
        heading = SECTION_RE.match(line)
        if heading:
            section = class_key(heading.group(1))
            continue
        finding = FINDING_RE.match(line)
        if finding and finding.group(2) in DEBT_SEVERITIES and section in want:
            out[section].append(line.strip())
    return out


def delta(baseline: dict[str, int], current: dict[str, int]) -> dict[str, tuple[int, int]]:
    """Every class whose count moved, as {class: (was, now)}.

    Includes classes absent from either side, because a class that DISAPPEARS is
    as interesting as one that grows: a check that stopped running reports zero
    findings and looks like progress.
    """
    moved: dict[str, tuple[int, int]] = {}
    for name in sorted(set(baseline) | set(current)):
        was, now = baseline.get(name, 0), current.get(name, 0)
        if was != now:
            moved[name] = (was, now)
    return moved
