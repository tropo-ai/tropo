# v1.71 S1 loop-primitive brake test — WALL-CLOCK (AC2).
# Body authored by argus-a114 (2026-06-16) from the Argus ad-hoc verification battery,
# per Metis G81 cut-bar decision (event 3900, option a). Talos owns/adjusts.
# Verifies vault/tools/1edbee15.py reads the run-FOLDER ctime (not the agent-appended jsonl).
import json
import shutil
import tempfile
import time
import unittest
import importlib.util
from pathlib import Path
from unittest import mock

vault_tools_dir = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("watchdog", str(vault_tools_dir / "1edbee15.py"))
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


def _seed(run_dir: Path, brakes: dict):
    with open(run_dir / "run.jsonl", "w") as f:
        f.write(json.dumps({"event": "run_created"}) + "\n")
        f.write(json.dumps({"event": "loop_contract_locked", "brakes": brakes}) + "\n")
        f.write(json.dumps({"event": "iteration_completed", "iteration_n": 1}) + "\n")


class TestWallClockBrake(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.run_dir = self.root / "vault" / "loop-runs" / "r"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_walltime_exceeded_trips(self):
        """A run older than max_wall_clock_min is killed (ground-truth: run-folder ctime)."""
        _seed(self.run_dir, {"max_wall_clock_min": 60})
        # Make the folder appear ~1666 min old by advancing the watchdog's clock.
        with mock.patch.object(watchdog.time, "time", return_value=time.time() + 100000):
            watchdog.watchdog_scan(self.root)
        self.assertTrue((self.run_dir / ".poison_sentinel").exists())
        ev = [json.loads(l) for l in open(self.run_dir / "run.jsonl")]
        self.assertEqual(ev[-2]["event"], "brake_tripped")
        self.assertEqual(ev[-2]["brake"], "max_wall_clock_min")

    def test_walltime_fresh_no_trip(self):
        """A fresh run (age < limit) is NOT killed (no spurious trip)."""
        _seed(self.run_dir, {"max_wall_clock_min": 60})
        watchdog.watchdog_scan(self.root)
        self.assertFalse((self.run_dir / ".poison_sentinel").exists())

    def test_walltime_uses_folder_ctime_not_jsonl(self):
        """Appending to run.jsonl does NOT reset the age clock (folder ctime is the source)."""
        _seed(self.run_dir, {"max_wall_clock_min": 60})
        # An agent appending fresh events cannot dodge the brake once the folder is old.
        with open(self.run_dir / "run.jsonl", "a") as f:
            f.write(json.dumps({"event": "iteration_completed", "iteration_n": 2}) + "\n")
        with mock.patch.object(watchdog.time, "time", return_value=time.time() + 100000):
            watchdog.watchdog_scan(self.root)
        self.assertTrue((self.run_dir / ".poison_sentinel").exists())


if __name__ == "__main__":
    unittest.main()
