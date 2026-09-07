#!/usr/bin/env python3
"""The loop launcher's run_created row must carry the key the gateway reads.

THE WEDGE. `loop_metering_gateway.py:335` reads `events[0].get("run_uid")` and
raises "run_created.run_uid must be 8 lowercase hex" when it is absent. The
sanctioned launcher, `2e5c81d3.py` (loop-activate, "Activation gate for governed
loops"), wrote a run_created row containing event/time/owner/loop/loop_version
and NO run_uid at all.

So every loop activated through the sanctioned gate refused every metered call,
with an error naming the missing FIELD rather than the launcher that never wrote
it. The value was not missing -- it is minted at :96 and stored in run.state.json
under the key "uid". Only the event row omitted it.

The gateway was right: the Studio's own run_created schema
(.tropo/boot-fast-path.md) spells the key `run_uid`. Two writers of one fact, and
the one the gateway reads had the wrong shape.

This test asserts the launcher's OWN emitted row satisfies the gateway's OWN
predicate -- both read out of the shipped source, neither retyped here.

Argus A165, 2026-09-01.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
sys.path.insert(0, str(TOOLS))

GATEWAY_SRC = (TOOLS / "loop_metering_gateway.py").read_text()
LAUNCHER_SRC = (TOOLS / "2e5c81d3.py").read_text()


def _gateway_run_uid_re() -> "re.Pattern[str]":
    """The gateway's OWN literal, read out of its source rather than retyped.

    It cannot be imported: loop_metering_gateway imports mitmproxy, which is not
    a test-environment dependency. Scraping the constant keeps the one property
    that matters -- if the gateway's shape moves, this test moves with it -- while
    a retyped copy here would be a third reader of the same fact, which is the
    defect this file exists to catch.
    """
    m = re.search(r'^RUN_UID_RE = re\.compile\(r"([^"]+)"\)', GATEWAY_SRC, re.M)
    if not m:
        raise AssertionError(
            "RUN_UID_RE not found in loop_metering_gateway.py -- it was renamed or "
            "reshaped, and this test can no longer read the predicate it asserts "
            "against. Fix the scrape rather than deleting the assertion.")
    return re.compile(m.group(1))


RUN_UID_RE = _gateway_run_uid_re()


class TheLauncherSatisfiesTheGateway(unittest.TestCase):

    def test_the_launcher_emits_run_uid_in_run_created(self) -> None:
        """Structural, via AST -- the KEY in the dict literal, not text in the file.

        My first version of this test scanned the source text for the string
        "run_uid" near the run_created row. It passed with the key REMOVED,
        because the explanatory comment I had written directly above it contains
        the word. A test that asserts a fix-string appears in a file is not a
        test of the fix; it is a test of the documentation about the fix, and I
        flagged exactly that shape in someone else's suite this morning before
        building it here. Parsed keys cannot be satisfied by prose.
        """
        import ast

        tree = ast.parse(LAUNCHER_SRC)
        rows = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            vals = [v.value for v in node.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)]
            if "event" in keys and "run_created" in vals:
                rows.append(keys)

        self.assertTrue(rows, "no run_created dict literal found in the launcher")
        for keys in rows:
            self.assertIn(
                "run_uid", keys,
                "loop-activate's run_created row omits the run_uid KEY. The "
                "gateway reads events[0]['run_uid'] and refuses the whole budget "
                "contract without it, so every metered call from a sanctioned "
                "loop run fails with a message naming the field rather than the "
                "launcher that never wrote it. Keys present: %r" % (keys,),
            )

    def test_a_launcher_shaped_row_passes_the_gateways_own_predicate(self) -> None:
        """Behavioural: the gateway's OWN regex, not a copy, over a row shaped
        like the launcher's."""
        row = {"event": "run_created", "run_uid": "a1b2c3d4", "time": "t",
               "owner": "mike-maziarz", "loop": "d1a4f8e2", "loop_version": "1"}
        ru = row.get("run_uid")
        self.assertTrue(
            isinstance(ru, str) and RUN_UID_RE.fullmatch(ru),
            "the gateway refuses a launcher-shaped run_created row",
        )

    def test_the_control_the_old_shape_is_still_refused(self) -> None:
        """Without this, a gateway that accepted anything would pass the test
        above while being just as broken."""
        old = {"event": "run_created", "time": "t", "owner": "mike-maziarz",
               "loop": "d1a4f8e2", "loop_version": "1"}
        ru = old.get("run_uid")
        self.assertFalse(
            isinstance(ru, str) and RUN_UID_RE.fullmatch(ru or ""),
            "the pre-cure row is accepted, so this suite cannot tell cured from "
            "uncured and proves nothing.",
        )

    def test_the_uid_shape_matches_what_the_launcher_actually_mints(self) -> None:
        """The launcher mints uuid4()[:8]. If either side's shape moves, these
        stop agreeing -- and a run_uid the gateway refuses is the same wedge with
        a different cause."""
        self.assertIn(
            "uuid.uuid4())[:8]", LAUNCHER_SRC,
            "the launcher no longer mints an 8-hex run uid; re-check the "
            "gateway's RUN_UID_RE against whatever it mints now.",
        )
        import uuid
        for _ in range(20):
            self.assertTrue(RUN_UID_RE.fullmatch(str(uuid.uuid4())[:8]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
