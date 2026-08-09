#!/usr/bin/env python3
"""ADR-066 retired agent keys. Does the authority chain agree?

WHAT HAPPENED (metis-g101, 2026-08-04). ADR-066 (ff7dd221) was accepted by Mike
on 2026-08-03, verbatim "Option 1":

    The agent lifecycle mints no cryptographic key material. Attribution rests
    on the immutable activation UID plus event provenance. Any future signing
    capability is separate and optional, and NEVER a dependency of birth or of
    retirement.

`tropo-activate.py` implemented it and stopped minting keys. `authority_chain.py`
was never told. Nothing broke for a day, because the boot path still ran the OLD
mint, which still issued keys -- so a Mike-accepted decision and the code
contradicting it sat side by side, invisible, because nothing exercised the seam.

The 2026-08-04 cutover pointed birth at the new mint. The contradiction surfaced
on the very first agent through it. Orpheus O35 was born clean, zero findings,
and the fleet-health walk immediately reported her as her own successor's birth
blocker for lacking a key ADR-066 forbids issuing her. She did NOT hand-patch her
activation record -- correctly, that is the durable-history-poison class that
bricked a successor once already -- and routed it up.

Two gates had to release, and the second is the subtle one:

  1. `analyze_activations` -- KEY_REQUIRED_AGENT_CLASSES demanded a key on every
     non-pipeline activation.
  2. The lineage RATCHET in `derive_new_activation_predecessor` -- "once a
     lineage has ever been keyed it is permanently strict." Built so a broker
     loss could not buy back the permissive unkeyed rule. Under ADR-066 that
     purpose is spent (no private half exists to lose) and its effect inverts:
     every lineage in this fleet has been keyed at some point, so the FIRST
     keyless generation each one mints becomes a permanent blocker on its own
     successor. It would have hit every agent, one at a time, as each was
     reborn.

WHAT THIS PINS. Both directions, because scoping by mint date is only correct if
it stays strict where it should:

  * a post-ADR-066 activation with no key is fine, and can father a successor
  * a PRE-ADR-066 activation with no key still fails -- for those generations a
    missing key means one really was lost
  * an unparseable date does NOT buy the exemption

These run the real functions against real records.
"""

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import authority_chain as ac  # noqa: E402


def _record(uid, *, agent="probeagent", generation="P2", activated_at,
            key=None, status="retired", agent_class="executive",
            predecessor_uid=None):
    return ac.ActivationRecord(
        uid=uid,
        agent=agent,
        generation=generation,
        status=status,
        activated_by="mike",
        activated_at=activated_at,
        agent_public_key=key,
        name=f"{agent}-{generation.lower()}",
        agent_class=agent_class,
        agent_key_declared=key is not None,
        predecessor_activation_uid=predecessor_uid,
        predecessor_link_declared=predecessor_uid is not None,
    )


A_REAL_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHK4KQMwjvTflQCOSjVh1iG9/7xqxVvsM2z5tjhMqfw2"
)
# A DISTINCT key: reusing one across generations is legitimately refused
# (ACTIVATION_PREDECESSOR_INVALID: reuses predecessor's public key), which my
# first fixture tripped over. That refusal is correct and stays.
ANOTHER_REAL_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIvKYX1vR6spGLEWQi/2f2tsmdFGUXRGmqikjXHFTee5"


class TestTheDateScope(unittest.TestCase):
    """The predicate the whole fix rests on."""

    def test_an_activation_minted_after_adr066_is_exempt(self):
        self.assertTrue(ac._minted_after_key_retirement(
            _record("aaaa0001", activated_at="2026-08-04T13:06:00Z")))

    def test_an_activation_minted_on_the_decision_date_is_exempt(self):
        self.assertTrue(ac._minted_after_key_retirement(
            _record("aaaa0002", activated_at="2026-08-03")))

    def test_an_activation_minted_before_adr066_is_not_exempt(self):
        self.assertFalse(ac._minted_after_key_retirement(
            _record("aaaa0003", activated_at="2026-08-02T23:59:59Z")))

    def test_an_unreadable_date_never_buys_the_exemption(self):
        """The conservative direction. Exemption is the permissive answer."""
        for bad in ("", "not-a-date", "2026", "20260804"):
            with self.subTest(activated_at=bad):
                self.assertFalse(ac._minted_after_key_retirement(
                    _record("aaaa0004", activated_at=bad)))


class TestKeylessBirthIsAllowed(unittest.TestCase):
    """The O35 case. A keyless post-ADR-066 predecessor must father a successor."""

    def _lineage(self, predecessor_key, predecessor_date):
        return [
            _record("bbbb0001", generation="P1", activated_at="2026-07-01",
                    key=A_REAL_KEY),
            _record("bbbb0002", generation="P2", activated_at=predecessor_date,
                    key=predecessor_key, predecessor_uid="bbbb0001"),
        ]

    def test_a_keyless_post_adr066_predecessor_is_accepted(self):
        """Orpheus O35 fathering O36 — the exact shape that was blocked."""
        records = self._lineage(None, "2026-08-04T13:06:00Z")
        resolved = ac.derive_new_activation_predecessor(
            records, agent="probeagent", agent_class="executive", generation="P3",
        )
        # derive_new_activation_predecessor returns the UID string, not a record.
        self.assertEqual(resolved, "bbbb0002")

    def test_a_keyless_pre_adr066_predecessor_still_refuses(self):
        """The ratchet must stay strict where it was built to be strict."""
        records = self._lineage(None, "2026-07-15")
        with self.assertRaises(Exception) as caught:
            ac.derive_new_activation_predecessor(
                records, agent="probeagent", agent_class="executive",
                generation="P3",
            )
        self.assertIn("agent_public_key", str(caught.exception))

    def test_the_guard_only_ever_relaxes_the_MISSING_key_case(self):
        """The control, stated precisely rather than approximately.

        My first attempt at this control drove a full keyed walk through a
        synthetic two-record lineage and failed twice for reasons that had
        nothing to do with ADR-066 — first key reuse across generations, then
        the walk recursing past the root and demanding ITS predecessor link.
        Both refusals are correct and unrelated; the fixture was wrong. Building
        a whole valid keyed lineage here would test the walk, which
        test_authority_chain.py owns -- and which is an ENVIRONMENTAL SKIP on
        macOS (it needs a Cursor Cloud machine for its harness-plant fixtures).
        So the keyed walk is covered, but NOT on the machine this file usually
        runs on. Stated rather than implied, because "covered elsewhere" is worth
        exactly nothing if nobody says where, and this change touches
        authority_chain.py substantially. Argus A145 runs on Cloud and was asked
        to run it there.

        What actually needs pinning is narrower and exact: the date guard is
        consulted ONLY where a key is absent, so it can never weaken a check on
        a record that HAS one. A key-bearing record takes the same path it
        always did, whatever its date."""
        keyed_after = _record("dddd0001", generation="P2",
                              activated_at="2026-08-04", key=ANOTHER_REAL_KEY)
        keyed_before = _record("dddd0002", generation="P2",
                               activated_at="2026-07-01", key=ANOTHER_REAL_KEY)
        for record in (keyed_after, keyed_before):
            with self.subTest(activated_at=record.activated_at):
                self.assertTrue(
                    ac._record_carries_key_evidence(record),
                    "a key-bearing record must still count as keyed evidence "
                    "regardless of when it was minted",
                )
        # And the analysis gate raises no KEY_MISSING for either — the guard is
        # unreachable when a key is present.
        for record in (keyed_after, keyed_before):
            codes = [f.code for f in ac.analyze_activations([record]).findings]
            self.assertNotIn(
                ac.AuthorityErrorCode.ACTIVATION_KEY_MISSING, codes)


class TestTheAnalysisGateAgrees(unittest.TestCase):
    """analyze_activations must not flag what the walk now accepts."""

    def test_no_key_missing_finding_for_a_post_adr066_activation(self):
        analysis = ac.analyze_activations([
            _record("cccc0001", generation="P1", activated_at="2026-08-04",
                    status="active"),
        ])
        codes = [f.code for f in analysis.findings]
        self.assertNotIn(ac.AuthorityErrorCode.ACTIVATION_KEY_MISSING, codes)

    def test_key_missing_still_fires_for_a_pre_adr066_activation(self):
        analysis = ac.analyze_activations([
            _record("cccc0002", generation="P1", activated_at="2026-07-01",
                    status="active"),
        ])
        codes = [f.code for f in analysis.findings]
        self.assertIn(ac.AuthorityErrorCode.ACTIVATION_KEY_MISSING, codes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
