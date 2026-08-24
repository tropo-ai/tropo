#!/usr/bin/env python3
"""S4 AC4(b) (29506520), argus-a154 2026-08-23 — the retirement notice carries
the category the playbook mandates, measured on the emitted event.

Playbook e2c7d185 Required Practice step 8 requires `category: retirement` on
the retirement notice. `tropo.broadcast.crew`'s `category` enum did not
declare it, and `tropo-lineage.py`'s `announce()` emitted `crew-state` from
one payload shared by births and retirements. Measured 2026-08-23 (bus query
+ commit 113dd07d3): not one retirement notice in either agent line carried
the required value, including the tool's own.

Half (a) of the reconciliation — the capsule gaining `retirement` as a
declared enum value — landed at events.capsule v1.12. This test proves half
(b): the WRITER now emits it. Mutation clause: restore the single hard-coded
`crew-state` category for both births and retirements, and this turns RED.

Isolated via temp_studio (argus-a147's AC2 isolation pattern) because
`announce()` shells out to `tropo-emit-event.py`, whose own VAULT_ROOT
resolves from its `__file__` — patching the in-process module leaves that
subprocess writing into the live vault. Only the temp Studio's own copy of
the emitter may run.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from temp_studio import TempStudio, production_fingerprint, diff_fingerprints  # noqa: E402

STUDIO = Path(__file__).resolve().parents[3]
TOOLS = STUDIO / "vault" / "tools"

_spec = importlib.util.spec_from_file_location(
    "tropo_lineage_for_ac4b", TOOLS / "tropo-lineage.py")
lineage = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = lineage
_spec.loader.exec_module(lineage)


def _broadcasts(temp: TempStudio) -> list:
    """Every tropo.broadcast.crew row the temp Studio's emitter wrote.

    A fresh/minimal Studio (no stream-routing registry) falls back to the
    flat `vault/events/00-events.jsonl`; a fully-provisioned one shards into
    `vault/events/streams/*.jsonl`. Read both so this does not silently read
    zero rows if the emitter's routing choice ever changes.
    """
    rows = []
    candidates = [temp.events / "00-events.jsonl"]
    streams = temp.events / "streams"
    if streams.is_dir():
        candidates.extend(sorted(streams.glob("*.jsonl")))
    for path in candidates:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if row.get("type") == "tropo.broadcast.crew":
                rows.append(row)
    return rows


class RetirementNoticeCategoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ac4b-")
        self.addCleanup(self._tmp.cleanup)
        self.temp = TempStudio(Path(self._tmp.name)).build()
        # tropo-emit-event.py --as resolves party_uid from a unified entry;
        # announce() always emits --as <agent>, so the fixture needs one.
        (self.temp.root / "vault" / "agents").mkdir(parents=True, exist_ok=True)
        (self.temp.root / "vault" / "agents" / "t-test-agent.md").write_text(
            "---\nuid: aaaaaaaa\ntype: agent\nagent: t-test-agent\n"
            "party_uid: bbbbbbbb\n---\n\n# t-test-agent\n",
            encoding="utf-8")
        self.before = production_fingerprint()
        self.addCleanup(self._assert_production_untouched)

    def _assert_production_untouched(self):
        after = production_fingerprint()
        changes = diff_fingerprints(self.before, after)
        self.assertEqual(changes, {}, f"production Studio changed: {changes}")

    def test_a_retirement_broadcast_carries_category_retirement(self):
        record = {"t": "retired", "gen": "T99", "letter": "agents/t/transfers/T99.md"}
        error = lineage.announce(self.temp.root, "t-test-agent", record)
        self.assertIsNone(error, f"announce() reported an error: {error}")

        rows = _broadcasts(self.temp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["data"]["category"], "retirement")
        self.assertEqual(rows[0]["data"]["t"], "retired")

    def test_a_birth_broadcast_still_carries_category_crew_state(self):
        """Birth keeps crew-state -- the playbook mandates nothing for a birth.
        Proves the fix is scoped to retirement, not a blanket category swap."""
        record = {"t": "born", "gen": "T100", "model": "test-sleeve"}
        error = lineage.announce(self.temp.root, "t-test-agent", record)
        self.assertIsNone(error, f"announce() reported an error: {error}")

        rows = _broadcasts(self.temp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["data"]["category"], "crew-state")
        self.assertEqual(rows[0]["data"]["t"], "born")

    def test_the_category_is_declared_in_the_capsule_enum(self):
        """Half (a) of the reconciliation: the capsule actually declares the
        value the writer now emits, so a validator reading the enum would not
        immediately flag the tool's own output as undeclared."""
        capsule = (STUDIO / "vault" / "capsules" / "tropo-events.capsule.md").read_text(
            encoding="utf-8")
        self.assertRegex(
            capsule,
            r"category:\s*\"<enum:[^\"]*\bretirement\b[^\"]*>\"",
            "tropo-events.capsule.md does not declare 'retirement' in the "
            "data.category enum for tropo.broadcast.crew",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
