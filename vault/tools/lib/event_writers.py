"""v1.91 S2 (3fb41c99) — the ONE writer-enumerator for declared release events.

Shared by the AC1 test (test_one_writer_per_event_v191) and the AC2 validator
floor (check_release_event_writers). One question, one reader: "which lines in
the shipped tree EMIT this event?" Reference counting is not writer detection —
a file can read one event and write another (the freeze tool), and emitters
pass constants (INTENT_EVENT, PACKAGE_FROZEN_EVENT) rather than literals, so a
literal grep misses real writers while counting readers as them. A154 proved
the reference form blind by mutation against real history, same day.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

_WRITE_MARKERS = re.compile(
    r'make_event|append_event|\.append\(|handle\.write|\.write\(|'
    r'emit-event|write_event|\.emit\(|subprocess\.run\(|'
    r'["\']event["\']\s*:', re.IGNORECASE)
_WINDOW = 4  # lines around an event reference that may carry the write call

#: v1.91 S2 (3fb41c99): `subprocess.run(` added as a marker after
#: tropo-lock-release-plan.py's scope_locked emitter (a genuine, correctly-
#: shaped subprocess call to tropo-emit-event.py) went undetected -- ordinary
#: argument-list construction (the data dict, the is_file() guard) put more
#: than 4 lines between "tropo-emit-event.py" (which already matches
#: emit-event) and the event-type literal passed as a CLI argument. The
#: literal `emit-event` marker only fires when the tool's own filename sits
#: in the window; the call itself did not. Reshaping working code to fit a
#: line-distance heuristic is backwards -- the detector's job is to find
#: real emit sites, not to reward a particular indentation.

#: v1.91 S2 (3fb41c99): the value class excluded the hyphen character, so a
#: hyphenated event name's declared constant could never resolve as an
#: alias -- every OTHER declared event uses dots or underscores, so this
#: never fired until the first hyphenated one (release_verify.RECEIPT_KIND)
#: was declared. Found by running the detector against a real new
#: declaration, not by reading the regex.
_CONSTANT_ASSIGN = re.compile(
    r'^\s*([A-Z][A-Z0-9_]+)\s*(?::\s*str\s*)?=\s*["\']([a-z0-9._-]+)["\']',
    re.MULTILINE)


def _scan_files(roots: List[Path], registry: Path):
    for root in roots:
        if not root.is_dir():
            continue
        for py in sorted(root.rglob("*.py")):
            if py == registry:
                continue
            # tests/ directories are excluded wholesale: fixture generators
            # and reference-run scripts (e.g. sandbox_release_v1_reference_run)
            # are not shipped emitters even when the filename lacks test_.
            if "tests" in py.relative_to(root).parts[:-1]:
                continue
            try:
                yield py, py.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue


def emit_sites(event_name: str, studio_root: Path) -> List[Tuple[str, int]]:
    """(relative-file, 1-indexed-line) pairs where event_name is emitted.

    Resolves constant indirection: any module-level CONSTANT = "event.name"
    assignment anywhere in the scanned tree makes that constant a reference
    alias for the event. A site counts when a literal or alias reference sits
    within the write-marker window of an append/make_event/write call.
    """
    tools = studio_root / "vault" / "tools"
    registry = tools / "lib" / "release_events.py"
    roots = [tools, studio_root / ".tropo" / "scripts"]

    aliases = {event_name}
    files = list(_scan_files(roots, registry))
    for _py, lines in files:
        text = "\n".join(lines)
        for match in _CONSTANT_ASSIGN.finditer(text):
            if match.group(2) == event_name:
                aliases.add(match.group(1))

    sites: List[Tuple[str, int]] = []
    alias_pat = re.compile(
        r"\b(" + "|".join(re.escape(a) for a in sorted(aliases)) + r")\b")
    for py, lines in files:
        hits = [i for i, line in enumerate(lines) if alias_pat.search(line)]
        for i in hits:
            line = lines[i]
            # A comparison against the event (`event == X`) is a READ; reader
            # loops legitimately sit near append calls in the same library and
            # must not count as writers (found live: release_saga's observed()
            # reader flagged as 4 writers). `(\w+\.)?` because a QUALIFIED
            # comparison (`== release_verify.RECEIPT_KIND`) is still a read —
            # found live: tropo-publish-release.py's own frozen-payload lookup
            # read RECEIPT_KIND through its module alias and the bare-name
            # version of this regex missed the qualifier, so a read counted as
            # a second writer.
            if re.search(r"[!=]=\s*(\w+\.)?" + alias_pat.pattern, line):
                continue
            window = lines[max(0, i - _WINDOW):i + _WINDOW + 1]
            if any(_WRITE_MARKERS.search(l) for l in window):
                sites.append((str(py.relative_to(studio_root)), i + 1))
    return sites
