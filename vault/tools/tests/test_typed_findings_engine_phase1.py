"""Law-12 plants for Engine Phase-1 typed validator findings."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


findings = _load(
    "tropo_engine_findings_test",
    ROOT / "vault" / "tools" / "lib" / "findings.py",
)
event_validators = _load(
    "tropo_event_validators_test",
    ROOT / ".tropo" / "scripts" / "lib" / "event_validators.py",
)


class TypedFindingTests(unittest.TestCase):
    def test_tally_ignores_misleading_message_prefixes(self) -> None:
        planted = [
            findings.Finding(
                findings.Severity.ERROR,
                "plant",
                "error",
                "[WARN] deliberately wrong prose prefix",
            ),
            findings.Finding(
                findings.Severity.WARN,
                "plant",
                "warn",
                "[FAIL] deliberately wrong prose prefix",
            ),
            findings.Finding(
                findings.Severity.INFO,
                "plant",
                "info",
                "prefixless",
            ),
        ]
        tally = findings.FindingTally()
        typed = tally.extend(planted)
        self.assertEqual((tally.errors, tally.warnings, tally.infos), (1, 1, 1))
        self.assertTrue(str(typed[0]).lstrip().startswith("[ERROR]"))
        self.assertTrue(str(typed[1]).lstrip().startswith("[WARN]"))

    def test_crashed_check_family_becomes_counted_error(self) -> None:
        def crash():
            raise RuntimeError("planted family crash")

        raw, checked, defects = findings.run_check_family("crash-plant", crash)
        tally = findings.FindingTally()
        typed = tally.extend(raw, check_id="crash-plant")
        self.assertEqual(checked, 0)
        self.assertEqual(defects, 1)
        self.assertEqual(tally.errors, 1)
        self.assertIn("CRASHED", str(typed[0]))

    def test_event_check_22_true_severity_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events_dir = root / "vault" / "events"
            agents_dir = root / "vault" / "agents"
            events_dir.mkdir(parents=True)
            agents_dir.mkdir(parents=True)
            party_uid = "aaaaaaaa"
            (agents_dir / "11111111.md").write_text(
                f"---\nuid: '11111111'\nparty_uid: {party_uid}\n---\n",
                encoding="utf-8",
            )

            base = {
                "id": "00000001",
                "specversion": "1.0",
                "type": "tropo.message.sent",
                "source": "/agents/test",
                "time": "2026-07-15T00:00:00Z",
                "source_uid": "deadbeef",
                "lifecycle": "ephemeral",
            }
            event_path = events_dir / "00-events.jsonl"
            event_path.write_text(json.dumps(base) + "\n", encoding="utf-8")

            planted, checked, defects = event_validators.run_all_event_checks(root)
            self.assertEqual(checked, 1)
            self.assertEqual(defects, 1)
            self.assertTrue(
                any(
                    finding.check_id == "event-22"
                    and finding.severity == event_validators.Severity.ERROR
                    for finding in planted
                )
            )

            honest = dict(base, source_uid=party_uid)
            event_path.write_text(json.dumps(honest) + "\n", encoding="utf-8")
            clean, checked, defects = event_validators.run_all_event_checks(root)
            self.assertEqual(checked, 1)
            self.assertEqual(defects, 0)
            self.assertFalse(
                any(finding.severity == event_validators.Severity.ERROR for finding in clean)
            )

if __name__ == "__main__":
    unittest.main()
