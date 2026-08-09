#!/usr/bin/env python3
"""Birth must write the agent card, because retirement does.

THE HALF-WELDED PO BUG (found by Vela V71, 2026-08-05, fixed by metis-g101).

`tropo-retire.py` has had `sync_agent_card()` since the 2026-08-04 cutover and
correctly flips `vault/agents/<uid>.md` from ACTIVE to RETIRED in the same
gesture as closing the record. **Birth had no counterpart** — not one reference
to `vault/agents` anywhere in `tropo-activate.py`. So immediately after a
successful birth the card still read `status: RETIRED`, the predecessor's
`generation:` and the predecessor's `current_activation_uid:`, while the new
activation sat live in `vault/files/`.

One fact, two homes, written by only ONE of the two gestures. That is the
automatic-half/manual-half family in its purest form, and it is the failure this
studio has paid for repeatedly: Po read as live with a thirty-day-old session,
Orpheus flipped her own card by hand, and every Metis generation including G101
hand-edited this field at boot without recording it as a defect.

WHY IT WAS WORSE THAN A STALE FIELD, and why V71's proof mattered. On 2026-08-04
G101 added a crew-brief re-render at birth, because newborn agents were showing
as their retired predecessor for up to an hour. But `00-crew-brief.md` renders
FROM THE CARD. So the re-render is downstream of the field nobody wrote: it
faithfully republished the predecessor and made the staleness look freshly
confirmed. V71 demonstrated exactly that in a throwaway clone — a brief rendered
the way birth renders it, reading `Vela V71 RETIRED` while V72 was alive.
**A fix that improves the report of a wrong fact is worse than no fix.**

V71 found it by cloning the studio and running a REAL retire-then-birth cycle
rather than asserting the tools worked. These tests do the same thing at unit
scale: they run the actual mint against a scratch studio and read the card back.
"""

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
MINT = REPO / "vault" / "tools" / "tropo-activate.py"


class BirthCardFixture(unittest.TestCase):
    """A scratch studio with one retired agent card and a closed predecessor."""

    SLUG = "probeagent"

    def setUp(self):
        self.studio = pathlib.Path(tempfile.mkdtemp(prefix="birthcard-")).resolve()
        (self.studio / "vault" / "files").mkdir(parents=True)
        (self.studio / "vault" / "agents").mkdir(parents=True)
        self.card = self.studio / "vault" / "agents" / "cccc0001.md"
        self.card.write_text(
            "---\n"
            "uid: cccc0001\n"
            "type: agent\n"
            f"agent: {self.SLUG}\n"
            "status: RETIRED\n"
            "generation: P1\n"
            "current_activation_uid: aaaa0001\n"
            "---\n\n# probeagent\n\n## §Status-Notes\n\nP1 retired.\n",
            encoding="utf-8",
        )
        (self.studio / "vault" / "files" / "aaaa0001.md").write_text(
            "---\nuid: aaaa0001\ntype: activation\n"
            f"agent: {self.SLUG}\ngeneration: P1\nstatus: retired\n"
            "agent_class: executive\nactivated_by: mike\n"
            "activated_at: 2026-08-01T09:00:00Z\n---\n\n# P1\n",
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.studio, ignore_errors=True)

    def birth(self):
        proc = subprocess.run(
            [sys.executable, str(MINT), "--agent", self.SLUG,
             "--authorized-by", "mike", "--agent-class", "executive",
             "--vault-root", str(self.studio)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout.strip()), proc.stderr

    def field(self, key):
        m = re.search(rf"(?m)^{key}:[ \t]*(.*)$", self.card.read_text(encoding="utf-8"))
        return m.group(1).strip() if m else None


class TestBirthWritesTheCard(BirthCardFixture):
    def test_status_flips_to_active(self):
        """The regression. A born agent must not read RETIRED."""
        self.birth()
        self.assertEqual(self.field("status"), "ACTIVE")

    def test_generation_advances_to_the_issued_one(self):
        issued, _ = self.birth()
        self.assertEqual(self.field("generation"), issued["generation"])
        self.assertEqual(issued["generation"], "P2")

    def test_current_activation_uid_points_at_the_new_record(self):
        """The field that made a thirty-day-old session read as live."""
        issued, _ = self.birth()
        self.assertEqual(self.field("current_activation_uid"),
                         issued["activation_uid"])
        self.assertNotEqual(self.field("current_activation_uid"), "aaaa0001")

    def test_an_absent_activation_uid_is_ADDED_not_merely_flagged(self):
        """Vela V71's fleet sweep, 2026-08-05: orpheus was ACTIVE with no
        current_activation_uid line at all. agent.capsule lists the field as
        optional, but its purpose is "the open activation entry, WHEN ONE
        EXISTS" — and at a birth one always exists. A sync that only rewrites
        existing lines would flag that card on every future birth and never
        repair it: a gate that reports forever and fixes nothing."""
        text = self.card.read_text(encoding="utf-8")
        self.card.write_text(
            re.sub(r"(?m)^current_activation_uid:.*\n", "", text), encoding="utf-8")
        self.assertIsNone(self.field("current_activation_uid"), "fixture guard")

        issued, _ = self.birth()

        self.assertEqual(self.field("current_activation_uid"),
                         issued["activation_uid"])
        self.assertEqual(
            issued["findings"], [],
            "the field was repaired, so nothing should be reported as unfixed",
        )

    def test_the_card_still_parses_after_an_insert(self):
        """An inserted line must not break the frontmatter it lands in."""
        import yaml
        text = self.card.read_text(encoding="utf-8")
        self.card.write_text(
            re.sub(r"(?m)^current_activation_uid:.*\n", "", text), encoding="utf-8")
        self.birth()
        fm = self.card.read_text(encoding="utf-8").split("---", 2)[1]
        parsed = yaml.safe_load(fm)
        self.assertEqual(parsed["status"], "ACTIVE")
        self.assertEqual(parsed["agent"], self.SLUG)
        self.assertTrue(parsed["current_activation_uid"])

    def test_the_card_body_is_untouched(self):
        """Lifecycle fields only. §Status-Notes is the agent's voice, not ours."""
        self.birth()
        self.assertIn("P1 retired.", self.card.read_text(encoding="utf-8"))

    def test_birth_still_succeeds_when_there_is_no_card_layer(self):
        """A studio with no vault/agents/ must still be able to birth."""
        shutil.rmtree(self.studio / "vault" / "agents")
        issued, _ = self.birth()
        self.assertTrue(issued["activation_uid"])

    def test_a_missing_card_is_a_finding_not_a_silent_pass(self):
        """If the card cannot be found, say so — do not report a clean birth."""
        self.card.unlink()
        issued, _ = self.birth()
        self.assertTrue(
            issued["findings"],
            "no card was updated and nothing was recorded — that is the silent "
            "half-weld this fix exists to remove",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
