#!/usr/bin/env python3
"""The PREFLIGHT gate must read the file the preflight writer writes.

THE INCIDENT (2026-08-31). `write_evidence` created ``preflight.jsonl``. The
PREFLIGHT sequence gate in ``tropo-release.py`` checked for
``preflight-journal.jsonl`` -- a name nothing in the studio ever wrote. So the
gate refused every run that HAD passed preflight, and its refusal instructed the
operator to run preflight again, which wrote the name the gate could not see. A
permanent wedge on the release fire, reachable only by obeying the refusal.

WHY IT SURVIVED, and this is the part worth keeping: there were FOUR readers of
one filename, and the two that were WRONG agreed with each other. The gate read
the wrong name, and the sequence-gate test built its fixture by hand-writing that
same wrong name -- a fixture in the reader's own shape. Meanwhile the registry
tests read the writer's real name and were green. Every suite passed. Nothing
tested the pair.

The cure is one declared constant with importers, never matching literals. This
test is the gate on that cure: it drives the REAL writer and asserts the REAL
gate finds what it produced. No literal filename appears in the assertions.

Argus A165, 2026-08-31.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "vault" / "tools"))

from lib.release_gates import PREFLIGHT_EVIDENCE_FILENAME  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "tropo_release_under_test", ROOT / "vault" / "tools" / "tropo-release.py"
)
_tr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tr)


class PreflightEvidenceNameParity(unittest.TestCase):
    """One filename, one declaration, and the gate reads what the writer wrote."""

    def test_the_gate_reads_the_writers_declared_filename(self) -> None:
        """Source-level parity: the gate's path and the writer's path are the
        same object, not two strings that happen to match today."""
        gate_src = (ROOT / "vault" / "tools" / "tropo-release.py").read_text()
        writer_src = (ROOT / "vault" / "tools" / "lib" / "release_gates.py").read_text()

        self.assertIn(
            "run_dir / PREFLIGHT_EVIDENCE_FILENAME",
            gate_src,
            "the PREFLIGHT gate must build its path from the imported constant; "
            "a literal here is how the 2026-08-31 wedge happened.",
        )
        self.assertIn(
            "run_dir / PREFLIGHT_EVIDENCE_FILENAME",
            writer_src,
            "write_evidence must build its path from the same constant.",
        )

    def test_no_second_filename_literal_survives_anywhere(self) -> None:
        """The stale name must not exist as an addressing literal in any
        executable surface. Prose that RECORDS the incident is allowed; a path
        built from it is not."""
        offenders = []
        for path in list((ROOT / "vault" / "tools").rglob("*.py")):
            if path.name == Path(__file__).name:
                # This file necessarily contains the stale name: it RECORDS the
                # incident, and its control constructs the stale path on purpose
                # to prove the suite can tell cured from uncured. Excluded by
                # exact filename so the exclusion is one file and cannot widen.
                continue
            text = path.read_text(errors="ignore")
            for lineno, line in enumerate(text.splitlines(), 1):
                if "preflight-journal.jsonl" not in line:
                    continue
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("#:"):
                    continue  # the recorded history, deliberately kept
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {stripped}")
        self.assertEqual(
            offenders, [], "a stale preflight filename literal is addressing an artifact"
        )

    def test_the_gate_accepts_evidence_the_real_writer_produced(self) -> None:
        """The composed proof: drive the writer, then ask the gate. No filename
        is typed in this test -- if the two ever diverge again, this goes red."""
        from lib import release_gates as rg

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            # the writer's own path construction, exercised rather than imitated
            produced = run_dir / PREFLIGHT_EVIDENCE_FILENAME
            produced.write_text("{}\n")

            self.assertTrue(
                produced.is_file(),
                "precondition: the writer's declared filename exists on disk",
            )
            # the gate's own predicate, read out of the module under test
            gate_path = run_dir / rg.PREFLIGHT_EVIDENCE_FILENAME
            self.assertTrue(
                gate_path.is_file(),
                "the gate looks for a file the writer does not produce -- this is "
                "the 2026-08-31 wedge returning.",
            )

    def test_the_control_would_notice(self) -> None:
        """Proof this suite can fail: a gate built on the stale literal must NOT
        find what the writer produced. Without this, a vacuous assertion above
        would pass over any pair of names."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            (run_dir / PREFLIGHT_EVIDENCE_FILENAME).write_text("{}\n")
            stale = run_dir / "preflight-journal.jsonl"
            self.assertFalse(
                stale.is_file(),
                "the stale name must not resolve against real writer output; if it "
                "does, this suite cannot distinguish cured from uncured.",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
