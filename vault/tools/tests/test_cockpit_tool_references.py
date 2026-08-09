#!/usr/bin/env python3
"""Every vault tool the cockpit shells out to must actually exist.

WHAT HAPPENED (metis-g101, 2026-08-04). Mike's milestone is "the dashboard and
orient usable". Asked what to do with a fresh session, I ran the cockpit instead
of reading about it, and enumerated what it reads from the vault. Three of the
five paths did not exist:

    vault/tools/561d3c75.py   ->  renamed to tropo-extract.py
    vault/tools/bf886f30.py   ->  renamed to tropo-import-walker.py
    vault/tools/ce9dbcc2.py   ->  renamed to tropo-export.py

Nobody deleted anything. They were renamed under the shipped-component
convention (`tropo-<name>.py`, per the orientation doc's naming rule), and four
call sites across the import and export routes kept the old UID paths. The
routes build `path.join(studioRoot(), TOOL)` and spawn it, so **the entire
import/export pipeline in the cockpit failed at the shell**, silently, until
someone tried to use it.

This is the same shape as everything else that day: A READER STILL POINTED AT A
SHAPE THE SUBSTRATE MOVED AWAY FROM. The agent playbooks pointed at a retired
mint; identity documents pointed at a retired tool; the cockpit's agent picker
reads `type: charter` entries that v1.69 superseded in June. Renames are the
cheapest possible version of that class and the easiest to catch — so catch it.

WHY THIS TEST AND NOT A CAREFUL REVIEW. The four call sites were correct when
they were written. Nothing in the cockpit fails at build time when a spawned
path is wrong: TypeScript type-checks a string, and the failure surfaces only in
a subprocess exit code at runtime, in a feature nobody exercised. A convention
that says "shipped tools are named tropo-*" needs an enforcement that says "and
every caller was updated" — otherwise the convention is a rule in prose, which
this studio has learned is probabilistic. This lives in `vault/tools/tests/` so
it runs under `npm test`, the command Mike already runs, rather than behind a
new verb nobody types.
"""

import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
COCKPIT = REPO / "tropo-app"
SEARCH_DIRS = ("app", "lib", "components", "scripts")

# ANY python script path in a quoted string — not just vault/tools/.
#
# WIDENED 2026-08-05, one day after this suite was written, because its first
# regex could not see the defect that mattered most. It matched only
# `vault/tools/<name>.py`, so `.tropo/scripts/vault-search.py` — invoked by the
# item agent and by author/search — was invisible to it. That path HAS NEVER
# EXISTED, every call threw, and a `catch { return [] }` turned it into "the
# vault has no results" for every query the agent ever ran.
#
# Talos T38 named this the same week: an audit inherits the shape of its
# instrument. I wrote an instrument shaped like the bug I had just found, and it
# was blind to the same bug one directory over. The fix is not a better guess at
# directories — it is to stop guessing which directories count.
_TOOL_REF = re.compile(
    r"""["'`]((?:[A-Za-z0-9_.\-]+/)*[A-Za-z0-9_.\-]+\.py)["'`]""")

# path.join(studioRoot(), ".tropo", "scripts", "vault-search.py") — the SAME
# defect written as separate segments, which the single-string regex above
# cannot see.
#
# Found by mutation-testing this file on 2026-08-05: I restored the known-broken
# path and the suite stayed GREEN. Third order of the same lesson in three days —
# a regex shaped like the last bug is blind to the next one written differently.
# A suite that cannot fail on the defect that prompted it is decoration, so the
# mutation test is the acceptance here, not the green run.
_JOINED_REF = re.compile(
    r"""path\.join\(\s*[A-Za-z0-9_.()]+\s*,\s*((?:["'`][A-Za-z0-9_.\- ]+["'`]\s*,\s*)*["'`][A-Za-z0-9_.\-]+\.py["'`])\s*\)""")
_SEGMENT = re.compile(r"""["'`]([A-Za-z0-9_.\- ]+)["'`]""")


def _joined_paths(text: str):
    """Reconstruct repo-relative paths from path.join(root, "a", "b", "c.py")."""
    for match in _JOINED_REF.finditer(text):
        segments = _SEGMENT.findall(match.group(1))
        if segments:
            yield "/".join(segments)

# Path fragments that are joined at runtime rather than being repo-relative, or
# that name a file relative to its own module. Listed explicitly so a reader can
# see what is deliberately not checked instead of wondering why.
_RUNTIME_JOINED = {
    "board-query.py",   # lib/boards/engine.ts joins it to process.cwd()/lib/boards
    "render-board.py",  # board-query.py joins it to the studio root itself
}


def _cockpit_sources():
    for rel in SEARCH_DIRS:
        root = COCKPIT / rel
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix not in {".ts", ".tsx", ".mjs", ".js"}:
                continue
            if "node_modules" in path.parts:
                continue
            yield path


class TestCockpitToolReferences(unittest.TestCase):
    @unittest.skipUnless(COCKPIT.is_dir(), "no tropo-app/ in this studio")
    def test_every_referenced_vault_tool_exists(self):
        """The regression. A renamed tool must not strand its callers."""
        missing = []
        for path in _cockpit_sources():
            text = path.read_text(encoding="utf-8", errors="replace")
            refs = [r for r in _TOOL_REF.findall(text) if "/" in r]
            refs += list(_joined_paths(text))
            for ref in refs:
                if ref in _RUNTIME_JOINED or ref.split("/")[-1] in _RUNTIME_JOINED:
                    continue
                candidates = [REPO / ref, COCKPIT / ref]
                if not any(c.is_file() for c in candidates):
                    missing.append(f"{path.relative_to(REPO)} -> {ref}")
        self.assertEqual(
            sorted(set(missing)), [],
            "the cockpit spawns vault tools that do not exist. These fail at the "
            "shell at runtime, not at build time — TypeScript only sees a string:\n  "
            + "\n  ".join(sorted(set(missing))),
        )

    @unittest.skipUnless(COCKPIT.is_dir(), "no tropo-app/ in this studio")
    def test_the_scanner_actually_sees_the_call_sites(self):
        """Guard the guard.

        If the regex or the search dirs ever stop matching, the test above goes
        vacuously green and reports safety it did not check — which is the exact
        failure this suite exists to catch, wearing the tester's hat. The four
        known call sites are import, import/extract, import/export and docx.
        """
        found = set()
        for path in _cockpit_sources():
            text = path.read_text(encoding="utf-8", errors="replace")
            found.update(_TOOL_REF.findall(text))
        self.assertGreaterEqual(
            len(found), 3,
            "the scanner found almost no vault-tool references, which means it "
            "has stopped working rather than that the cockpit stopped spawning "
            f"tools. Found: {sorted(found)}",
        )

    @unittest.skipUnless(COCKPIT.is_dir(), "no tropo-app/ in this studio")
    def test_no_live_call_site_uses_a_uid_named_tool(self):
        """The convention itself, enforced rather than described.

        Shipped OS components are `tropo-<name>.py`; UIDs are addresses, not
        filenames. A UID-named path in a live call site is either already broken
        or one rename away from it, so it fails here while it is still cheap.
        """
        offenders = []
        uid_named = re.compile(r"""["'`]vault/tools/[0-9a-f]{8}\.py["'`]""")
        for path in _cockpit_sources():
            for i, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("*") or stripped.startswith("//"):
                    continue  # a comment recording history is not a call site
                if uid_named.search(line):
                    offenders.append(f"{path.relative_to(REPO)}:{i}")
        self.assertEqual(
            sorted(offenders), [],
            "live call sites still name tools by UID instead of the shipped "
            "`tropo-<name>.py` convention:\n  " + "\n  ".join(sorted(offenders)),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
