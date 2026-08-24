#!/usr/bin/env python3
"""S4 AC8 (29506520) — the lock gesture must REFUSE on a precondition it recorded.

THE DEFECT THIS PINS. tropo-lock-dev-spec.py pinned acceptance_criteria_present=false
into the declaration snapshot of all three locked v1.91 specs and locked them anyway.
It was never blind: it looked, wrote the absence down, and proceeded. Root cause,
measured 2026-08-23: the four v1.91 specs carried 6-7 acceptance criteria in the BODY
and ZERO in frontmatter, while the gesture reads frontmatter. The convention moved and
the gesture did not.

THE ASYMMETRY IS THE POINT, per deb77758 (a refusal earns its existence by naming its
irreversible harm, or it is a warning that proceeds and records):
  acceptance_criteria absent -> REFUSE. A lock with no criteria the machine can find is
      a close nobody can judge; the run's own verdict becomes unfalsifiable.
  committed_substrate absent -> WARN and PROCEED. A dev-spec is locked BEFORE it is
      built, so an empty substrate at lock time is usually the honest state. Refusing it
      would be a gate wider than its harm — the class this whole cycle exists to remove.

MUTATION CONTRACT: delete the `is False` refusal in refuse_on_own_findings and
test_absent_criteria_refuses turns RED. Widen it to also refuse an absent
committed_substrate and test_absent_substrate_warns_but_proceeds turns RED. The test
changes verdict in BOTH directions when the mechanism it names is altered — which is the
only version of "tested" that counts here.

Written by argus-a154 2026-08-23, closing a contract defect in his OWN work: AC8's locked
verify command named this file and the file did not exist, so a stranger executing the
contract concluded AC8 unbuilt. Same trap that cost T48 a rename on S1 AC5 the same day.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def _load_lock_module():
    """Load the lock tool by path.

    Registered in sys.modules before exec: dataclasses resolves a class's module
    through sys.modules, and omitting the registration raises
    'AttributeError: NoneType object has no attribute __dict__' — a loader
    signature, not a code defect. Cost argus-a154 a wrong report earlier the same
    day; recorded so the next reader does not chase it.
    """
    spec = importlib.util.spec_from_file_location(
        "tropo_lock_dev_spec_under_test", TOOLS / "tropo-lock-dev-spec.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tropo_lock_dev_spec_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


LOCK = _load_lock_module()


class LockRefusesOnItsOwnFindings(unittest.TestCase):

    def test_absent_criteria_refuses(self) -> None:
        """The harm is named, so the gesture refuses rather than recording and proceeding."""
        with self.assertRaises(SystemExit) as caught:
            LOCK.refuse_on_own_findings(
                "deadbeef",
                {"acceptance_criteria_present": False,
                 "committed_substrate_present": True},
            )
        message = str(caught.exception)
        self.assertIn("REFUSED", message)
        self.assertIn("deadbeef", message,
                      "the refusal must name the spec it refused")
        self.assertIn("acceptance_criteria", message,
                      "the refusal must name WHICH precondition failed — a refusal "
                      "that does not say which mechanism fired is the class A153 was "
                      "corrected on")

    def test_present_criteria_proceeds(self) -> None:
        """A spec that declares its criteria locks without interference."""
        LOCK.refuse_on_own_findings(
            "deadbeef",
            {"acceptance_criteria_present": True,
             "committed_substrate_present": True},
        )

    def test_absent_substrate_warns_but_proceeds(self) -> None:
        """WARN-SAFE half: a spec is locked BEFORE it is built.

        Refusing an empty committed_substrate at lock time would be a gate wider
        than its harm. If this ever raises, the asymmetry has been lost.
        """
        LOCK.refuse_on_own_findings(
            "deadbeef",
            {"acceptance_criteria_present": True,
             "committed_substrate_present": False},
        )

    def test_unknown_preconditions_do_not_refuse(self) -> None:
        """Absence of a KEY is not a recorded finding of False.

        The AC is 'refuse on a precondition it RECORDED', not 'refuse on anything
        it could not compute'. A digest that never ran produces no finding, and
        inventing one would be a gate firing on missing evidence rather than on
        evidence of a miss.
        """
        LOCK.refuse_on_own_findings("deadbeef", {})


if __name__ == "__main__":
    unittest.main()
