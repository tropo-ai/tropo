#!/usr/bin/env python3
"""v1.91 S1 AC3 (0a0e94d1) — validator findings are ENUMERABLE.

Argus F-01: the summary counted 166 failures while 66 lines printed; 100
failures emitted nothing. A debt number you cannot enumerate is a number you
cannot disposition — the ratchet argues with a ghost.

The contract: every failure the summary counts appears as a printed [FAIL]
line, and the summary count is DERIVED from the printed lines, not maintained
as a parallel counter. Red at birth (2026-08-23: 166 counted, 66 printed).
Mutation clause: suppress any single finding line and this test goes RED.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

STUDIO = Path(__file__).resolve().parents[3]
VALIDATOR = STUDIO / "vault" / "tools" / "tropo-validate.py"

# ONE definition, shared semantics with the validator's _EnumerableTee:
# a line is a printed failure iff, ignoring leading whitespace, it starts
# with [FAIL] or [ERROR]. The tee and this test must never disagree about
# what counts -- two instruments, one definition.
_FAIL_LINE_FUNC = lambda line: line.lstrip().startswith(("[FAIL]", "[ERROR]"))
_SUMMARY = re.compile(
    r"(?:Result|Summary):\s*(\d+) passed,\s*(\d+) failed",
    re.IGNORECASE)


def _validator_output() -> str:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=str(STUDIO), capture_output=True, text=True, timeout=1800)
    return (proc.stdout or "") + (proc.stderr or "")


class DebtEnumerableTests(unittest.TestCase):
    def test_summary_failed_equals_printed_fail_lines(self) -> None:
        output = _validator_output()
        m = _SUMMARY.search(output)
        self.assertIsNotNone(
            m, f"no summary line in validator output — cannot enumerate")
        counted_failed = int(m.group(2))
        printed_fail_lines = sum(1 for l in output.splitlines() if _FAIL_LINE_FUNC(l))
        self.assertEqual(
            counted_failed, printed_fail_lines,
            f"summary counts {counted_failed} failed but {printed_fail_lines} "
            f"[FAIL] lines printed — {counted_failed - printed_fail_lines} "
            f"failures emit nothing and cannot be dispositioned (S1 AC3, "
            f"Argus F-01)")

    def test_suppressing_one_finding_line_reds_the_count(self) -> None:
        """The mutation clause at the deriver level: the count comes FROM the
        lines, so a line that never prints is a failure that never counts.
        (Text-level mutation of a captured run cannot prove this -- the
        summary is baked into the captured text. The deriver unit can.)"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("tv191", VALIDATOR)
        tv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tv)
        import io
        tee = tv._EnumerableTee(io.StringIO())
        for i in range(5):
            tee.write(f"  [ERROR] finding {i}\n")
        tee.write("[PASS] fine\n")
        self.assertEqual(tee.counts(), (1, 5, 0))
        # the mutation: one finding line suppressed -> one fewer failure counted
        tee2 = tv._EnumerableTee(io.StringIO())
        for i in range(4):
            tee2.write(f"  [ERROR] finding {i}\n")
        tee2.write("[PASS] fine\n")
        self.assertEqual(tee2.counts(), (1, 4, 0),
                         "a suppressed finding line must not count -- the "
                         "summary is derived from printed lines, not a "
                         "parallel counter")


if __name__ == "__main__":
    unittest.main()
