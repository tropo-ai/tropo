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
import json
import re
import sys
import posixpath
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.governed_path import UID_HEX_PATTERN  # the ONE home for the uid shape

try:
    from lib.package_state_exclusions import PER_STUDIO_BOOT_DERIVATIONS  # the build's own declaration
except Exception as _exc:  # noqa: BLE001 — a skip that cannot load must say so, never silently shrink
    PER_STUDIO_BOOT_DERIVATIONS = ()
    print("[WARN] tropo-check-doc-currency: lib/package_state_exclusions not loadable (%s); "
          "links to the per-studio boot derivations will read as absent" % _exc, file=sys.stderr)

# A reference worth checking looks like a path with a directory part. Bare
# filenames are excluded: too many false hits from prose naming a file.
INSTRUCTABLE_EXT = ("md", "py", "json", "jsonl", "yaml", "yml", "sh", "html")
PATH_RE = re.compile(
    r"(?<![\w./-])((?:\.?[\w][\w.-]*/)+[\w][\w.-]*\.(?:%s))(?![\w.-])"
    % "|".join(INSTRUCTABLE_EXT))

RETIRED_RE = re.compile(
    r"\b(retired|superseded|deprecated|no longer|replaced by|removed in|"
    r"used to|formerly|legacy)\b", re.IGNORECASE)

#: A governed uid as this Studio mints them, from the ONE home: the shape lives
#: in lib/governed_path and this module imports it rather than re-deriving the
#: hex lengths (test_uid_shape_has_one_home). UID_HEX_PATTERN is the authority's
#: own EXTRACTION form -- its docstring names this exact job, "finding uid-shaped
#: text inside a larger document", where a loose match is correct because every
#: hit is then filtered against the source Studio's governed set. Word-bounded
#: here so a longer hex run (a git sha) is not sliced into a uid.
#:
#: The literal this replaces predates the one-home landing: it entered with the
#: uid arm at e7c716dd2 and the ratchet at 1a067533d has read this module red
#: since, which the pre-landing file reproduces (talos-t63, 2026-09-06).
UID_RE = re.compile(r"(?<![0-9a-zA-Z])(%s)(?![0-9a-zA-Z])" % UID_HEX_PATTERN)

LINK_RE = re.compile(r"\]\(([^)]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")
STEP_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

INSTRUCTION, RETIRED, PROSE = "instruction", "retired", "prose"

#: A reference whose ROOT is a shell/runbook variable ($GEN/..., $STUDIO_ROOT/...)
#: or an out-of-studio staging root is a PARAMETER, not a path in the box. The
#: gate cannot decide it and must not report it: metis-g121 + argus-a172,
#: 2026-09-05, from the v1.94 box run — same shape as the <...> placeholder skip
#: on lock-verify-commands-runnable, and emitted for the same reason. A skip that
#: does not announce itself turns a gate that evaluated nothing into a gate that
#: passed.
PARAMETERISED = "parameterised"
CREATED = "created-by-this-file"

#: A runbook legitimately READS a path that an EARLIER step of the same runbook
#: created — `.tropo-studio/join-bundles/step5-principals.json` is written by the
#: ceremony at step 5 and read at steps 6 and 7. A fresh box carries none of
#: them, by construction, and reporting them dead is the documentation working
#: being scored as the documentation failing.
#:
#: No verb heuristic can decide this: most of those lines are `open(...)` READS,
#: and the creator is usually a TOOL the playbook runs, not a literal write in
#: its text. So the author declares it, once per path, in a form the gate reads:
#:
#:     <!-- doc-currency: creates .tropo-studio/join-bundles/step5-principals.json -->
#:
#: Declared paths are exempt for that file ONLY, and the declaration is visible
#: in the source rather than hidden in a skip list this tool maintains — a skip
#: list is how a gate quietly stops covering things (metis-g121: "never widen
#: the skip list").
CREATES_RE = re.compile(r"<!--\s*doc-currency:\s*creates\s+(\S+?)\s*-->")
EXTERNAL_ROOTS = ("STAGING/",)


def is_parameterised(line: str, start: int, ref: str) -> bool:
    """True when the reference is rooted in a variable or outside the box."""
    if start > 0 and line[start - 1] == "$":
        return True
    # `${GEN}/x` needs NO branch here: PATH_RE's lookbehind (?<![\w./-])
    # already refuses a path preceded by "/", so the braced form yields no
    # reference at all. I wrote a brace branch first and the test proved it dead
    # — an unreachable guard is the declared-but-not-wired family, so it is gone
    # rather than kept "just in case".
    return ref.startswith(EXTERNAL_ROOTS)


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


def scan_uids(text: str, known: set):
    """Yield (lineno, uid, form) for every reference to a KNOWN governed uid."""
    if not known:
        return
    in_fence = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        # One uid can appear twice on a line — a markdown link writes it in the
        # label AND in the path: `[the inbox (2d5f9b04)](../files/2d5f9b04.md)`.
        # That is ONE reference to a reader, and reporting it twice inflates the
        # gate's count and makes a fixed item look half-fixed.
        seen = set()
        for m in UID_RE.finditer(line):
            uid = m.group(1)
            if uid in known and uid not in seen:
                seen.add(uid)
                yield n, uid, classify(line, uid, in_fence)


def declared_creations(text: str) -> set:
    """Paths this file declares that it creates."""
    return set(CREATES_RE.findall(text))


def scan_text(text: str):
    """Yield (lineno, ref, form) for every path-shaped reference."""
    created = declared_creations(text)
    in_fence = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if CREATES_RE.search(line):
            # The declaration names the path; it is metadata ABOUT a reference,
            # not a reference a reader follows. Counting it inflated the emitted
            # created-count by one per declaration (12 reported for 8 real
            # references) — caught by the test that expected one entry.
            continue
        for m in PATH_RE.finditer(line):
            ref = m.group(1)
            if is_parameterised(line, m.start(1), ref):
                yield n, ref, PARAMETERISED
                continue
            if ref in created:
                yield n, ref, CREATED
                continue
            yield n, ref, classify(line, ref, in_fence)


class Box:
    """The thing we check against: an extracted tree or a .zip, read alike."""

    def __init__(self, target: Path):
        self.target = target
        self.zip = None
        self._uid_cache = {}
        self._names_cache = None
        self._declared_cache = None
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

    def has_uid(self, uid: str) -> bool:
        """Does the box carry the governed entry this uid names?

        Two ways, because both are true of a real box: an index row, and a
        FILENAME carrying the uid — the lock gesture re-slugs governed files to
        `<slug>-<uid>.md`, so `vault/files/<uid>.md` is not the only shape and
        checking only that would report every locked spec missing.
        """
        if uid in self._uid_cache:
            return self._uid_cache[uid]
        found = any(uid in name for name in self._all_names())
        if not found:
            # A BOX HAS NO INDEX. vault/00-index.jsonl is a per-machine derived
            # product a fresh box legitimately does not carry, and the shipped
            # entry's FILENAME does not always contain its uid — a governed file
            # keeps the slug it was minted or locked under while the uid lives
            # only in its frontmatter. Checking name-then-index therefore
            # reported six shipped entries missing from the v1.94 candidate that
            # were sitting in it (argus-a172 + metis-g122, 2026-09-06).
            # So: read the uids the box's own files DECLARE, once, cached.
            found = uid in self._declared_uids()
        if not found:
            try:
                index = self.read("vault/00-index.jsonl")
            except Exception:
                index = ""
            found = ('"%s"' % uid) in index
        self._uid_cache[uid] = found
        return found

    def _declared_uids(self) -> set:
        """Every `uid:` a governed file in the box declares. Built once."""
        if self._declared_cache is not None:
            return self._declared_cache
        uids = set()
        for name in self._all_names():
            if not name.endswith(".md"):
                continue
            try:
                text = self.read(name)
            except Exception:  # noqa: BLE001
                continue
            if not text.startswith("---"):
                continue
            head = text.split("---", 2)
            if len(head) < 3:
                continue
            m = re.search(r"^uid:\s*['\"]?([A-Za-z0-9]+)['\"]?", head[1], re.MULTILINE)
            if m:
                uids.add(m.group(1))
        self._declared_cache = uids
        return uids

    def _all_names(self):
        if self._names_cache is None:
            if self.zip is not None:
                self._names_cache = list(self.names)
            else:
                self._names_cache = [str(q.relative_to(self.target))
                                     for q in self.target.rglob("*") if q.is_file()]
        return self._names_cache

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


def normalised_ref(ref: str, relative_to: str = "") -> str:
    """The box path a reference names, resolved the way Box.exists resolves it:
    from the referencing file's own directory when the ref is relative, `..`
    segments collapsed. `vault/playbooks/x.md` linking
    `../../.tropo/boot-fast-path.md` names `.tropo/boot-fast-path.md`."""
    ref = ref.strip()
    while ref.startswith("./"):
        ref = ref[2:]
    if relative_to and "/" in relative_to and (ref.startswith("../") or not ref.startswith((".tropo/", "vault/", "agents/", "docs/", "boards/"))):
        base = relative_to.rsplit("/", 1)[0]
        joined = posixpath.normpath(base + "/" + ref)
        if not joined.startswith(".."):
            return joined
    return posixpath.normpath(ref)


def is_generated_at_boot(ref: str, relative_to: str = "") -> bool:
    """A reference to something the receiving studio renders for itself: the
    index family (GENERATED_AT_BOOT) and the two per-studio boot derivations the
    build excludes by declaration (PER_STUDIO_BOOT_DERIVATIONS, one home in
    lib/package_state_exclusions). Matched on the NORMALISED box path, not the
    raw ref: the raw match let `../../.tropo/boot-fast-path.md` through as dead
    even when the derivation was listed (v1.95 candidate #1, 99341618.md:58)."""
    if ref in GENERATED_AT_BOOT or ref in PER_STUDIO_BOOT_DERIVATIONS:
        return True
    norm = normalised_ref(ref, relative_to)
    return norm in GENERATED_AT_BOOT or norm in PER_STUDIO_BOOT_DERIVATIONS

DEFAULT_GLOBS = ("vault/playbooks/*.md", ".tropo/playbooks/*.md",
                 ".tropo/playbooks/concierge-paths/*.md")


def governed_uids(source: Path) -> set:
    """The uids the SOURCE Studio knows are governed entries.

    This set is the whole reason the uid check is decidable. A shipped document
    is full of hex that is NOT a uid — git short shas above all — and flagging
    every unresolved 8-hex token would report the documentation working as the
    documentation failing, which is the exact error this tool's docstring says
    it was built to avoid. So: only a token the source Studio can name as a
    governed entry is a reference a reader could follow, and only then does the
    box's not carrying it mean anything.
    """
    uids = set()
    index = Path(source) / "vault" / "00-index.jsonl"
    if index.is_file():
        for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            uid = row.get("uid")
            if isinstance(uid, str):
                uids.add(uid)
    return uids


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", default=".",
                    help="the Studio to check: a directory or a release .zip")
    ap.add_argument("--glob", action="append", default=None,
                    help="instruction-file glob (repeatable; defaults cover playbooks)")
    ap.add_argument("--show-prose", action="store_true",
                    help="also list advisory prose/historical references")
    ap.add_argument("--source", default=".",
                    help="the Studio whose index says which uids are governed "
                         "(default: cwd). Passed explicitly rather than derived "
                         "from this file's location: a tool that resolves its "
                         "own Studio from __file__ reads the wrong tree the "
                         "moment it is run from anywhere else.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    box = Box(Path(args.target).expanduser())
    globs = args.glob or list(DEFAULT_GLOBS)
    known_uids = governed_uids(Path(args.source).expanduser())

    dead_instructions, dead_prose, retired_ok, generated = [], [], 0, 0
    parameterised = []
    created_by_file = []
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
            if is_generated_at_boot(ref, relative_to=rel):
                generated += 1
                continue
            if form == PARAMETERISED:
                parameterised.append((rel, lineno, ref))
            elif form == CREATED:
                created_by_file.append((rel, lineno, ref))
            elif form == RETIRED:
                retired_ok += 1
            elif form == INSTRUCTION:
                dead_instructions.append(
                    (rel, lineno, ref, box.locate_elsewhere(ref)))
            else:
                dead_prose.append((rel, lineno, ref))

        # v1.95 Spine B (f015997f8d8e committed_substrate, AMENDED): a uid is a
        # reference a reader follows exactly as a path is, and Spine A's
        # reachability row (a) needs this tool to judge one over the box.
        for lineno, uid, form in scan_uids(text, known_uids):
            if box.has_uid(uid):
                continue
            if form == RETIRED:
                retired_ok += 1
            elif form == INSTRUCTION:
                dead_instructions.append((rel, lineno, uid, ""))
            else:
                dead_prose.append((rel, lineno, uid))

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
            "parameterised_skipped": [
                {"file": f, "line": n, "ref": r} for f, n, r in parameterised],
            "created_by_the_referring_file": [
                {"file": f, "line": n, "ref": r} for f, n, r in created_by_file],
        }, indent=2))
        return 1 if dead_instructions else 0

    print("doc-currency: %s" % box.target)
    print("  instruction files scanned: %d" % files_scanned)
    print("  retirement notices naming a gone path (correct, not a defect): %d"
          % retired_ok)
    print("  references to declared build-at-first-boot artifacts (correct): %d"
          % generated)
    print("  advisory prose/historical references to gone paths: %d" % len(dead_prose))
    # EMIT THE SKIP. A gate that quietly evaluated nothing must not read as a
    # gate that passed — the rule the manual-criteria and <...> placeholder
    # skips already follow on lock-verify-commands-runnable.
    print("  variable-rooted or out-of-studio references (parameters, not "
          "checkable): %d" % len(parameterised))
    print("  references to paths the referring file declares it CREATES "
          "(correct): %d" % len(created_by_file))
    if parameterised and args.show_prose:
        for f, n, r in parameterised:
            print("      %s:%d  ->  %s   [PARAMETER — root is a variable or "
                  "outside the box]" % (f, n, r))
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
