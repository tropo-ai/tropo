#!/usr/bin/env python3
"""v1.91 S1 AC5 (0a0e94d1) — a bypassed build says so in its own provenance.

v1.90 shipped with TROPO_SKIP_ENFORCEMENT_GATE=1 on the record (G109's
ruling, provenance note a76da7b4) — but the build's own build-provenance.json
never recorded it: a bypassed build and a clean build carried identical
provenance. The AC closes that: the enforcement-bypass state is part of the
build's permanent record. Red at birth: the writer records no such field.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
STUDIO = TOOLS.parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "builder_ac5", TOOLS / "tropo-build-release.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["builder_ac5"] = module
    spec.loader.exec_module(module)
    return module


class BypassRecordedTests(unittest.TestCase):
    def _write_provenance(self, builder, tmp, bypassed: bool) -> dict:
        releases = Path(tmp) / "releases"
        with mock.patch.object(builder.tropo_roots, "RELEASES_DIR",
                               str(releases)), \
             mock.patch.object(builder, "DRY_RUN", False):
            builder._write_build_provenance(
                "1.91.0", enforcement_bypassed=bypassed,
                _publish_state_provenance={"publish_state": "TEST"})
        return json.loads(
            (releases / "v1.91.0" / "build-provenance.json").read_text())

    def test_bypassed_build_records_the_bypass(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            prov = self._write_provenance(builder, tmp, bypassed=True)
        self.assertTrue(
            prov.get("enforcement_bypass", {}).get("skipped"),
            "a bypassed build's own provenance must record the bypass — "
            "identical provenance for bypassed and clean builds is the "
            "v1.90 gap this AC closes")

    def test_clean_build_records_clean_enforcement(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            prov = self._write_provenance(builder, tmp, bypassed=False)
        self.assertIn(
            "enforcement_bypass", prov,
            "clean builds record the field too (skipped:false) — a MISSING "
            "field must be detectable drift, never ambiguous silence")

    def test_the_gate_state_reaches_the_writer(self) -> None:
        src = (TOOLS / "tropo-build-release.py").read_text(encoding="utf-8")
        self.assertIn(
            "enforcement_bypassed=",
            src,
            "the build must derive the bypass state at the enforcement gate "
            "and pass it into the provenance writer")


if __name__ == "__main__":
    unittest.main()
