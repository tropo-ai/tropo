#!/usr/bin/env python3
"""3d8d4351 AC6 — amend-step-criteria explicit clear, both truncation points.

The writer distinguishes None (key absent, no change) from "" (key present,
CLEAR); the reader removes the declared command on present-and-empty. The
silent-keep at both truncation points is the defect; these pin the cure at
each point separately, plus the docstring-narrowed friction counter.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("engine_amend", TOOLS / "9e7003b1.py")
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

BASE = {"event": "step_declared",
        "data": {"step_id": "s1", "exit_criteria": ["old"],
                 "verification_command": "python3 old.py"}}


class AmendClearReaderTests(unittest.TestCase):
    """The reader's half, through the real get_step_declarations."""

    def test_set_updates_the_command(self) -> None:
        d = engine.get_step_declarations([BASE, {"event": "step_criteria_amended",
            "data": {"step_id": "s1", "exit_criteria": ["new"],
                     "verification_command": "python3 new.py"}}])
        self.assertEqual(d["s1"]["verification_command"], "python3 new.py")

    def test_explicit_empty_REMOVES_the_key(self) -> None:
        d = engine.get_step_declarations([BASE, {"event": "step_criteria_amended",
            "data": {"step_id": "s1", "exit_criteria": ["new"],
                     "verification_command": ""}}])
        self.assertNotIn("verification_command", d["s1"],
                         "a present-and-empty value must CLEAR the command, "
                         "not linger as a command that runs nothing")

    def test_absent_key_leaves_the_command_untouched(self) -> None:
        d = engine.get_step_declarations([BASE, {"event": "step_criteria_amended",
            "data": {"step_id": "s1", "exit_criteria": ["newer"]}}])
        self.assertEqual(d["s1"]["verification_command"], "python3 old.py",
                         "no silent clear in the other direction either")


class AmendClearWriterTests(unittest.TestCase):
    """The writer's half: None vs empty distinguished at the emit point."""

    def test_the_writer_distinguishes_none_from_empty(self) -> None:
        source = (TOOLS / "9e7003b1.py").read_text()
        amend_src = source.split("def action_amend_step_criteria", 1)[1][:2400]
        self.assertIn("if verification_command is not None:", amend_src,
                      "the old `if verification_command:` silently kept the "
                      "previous command on a requested clear")
        self.assertNotIn("if verification_command:\n", amend_src)

    def test_declared_gap_is_named_in_the_docstring(self) -> None:
        source = (TOOLS / "9e7003b1.py").read_text()
        self.assertIn("NO scorecard reader consumes it", source,
                      "the step_redeclare docstring must carry the narrowed "
                      "claim: the wedge is state-folded but unscored")

    def test_the_friction_counter_rides_the_event(self) -> None:
        source = (TOOLS / "9e7003b1.py").read_text()
        self.assertIn('"redeclare_friction_count": _friction', source,
                      "the Nth redeclare of the run is counted at emit so the "
                      "unscored gap is at least visible per-run")


if __name__ == "__main__":
    unittest.main(verbosity=2)
