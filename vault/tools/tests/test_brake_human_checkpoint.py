# v1.71 S1 loop-primitive brake test — HUMAN CHECKPOINT (AC2).
# Body authored by argus-a114 (2026-06-16) from the Argus ad-hoc verification battery,
# per Metis G81 cut-bar decision (event 3900, option a). Talos owns/adjusts.
# Verifies vault/tools/1edbee15.py PAUSES (does not kill) at human_checkpoint_every.
import json
import shutil
import tempfile
import unittest
import importlib.util
from pathlib import Path

vault_tools_dir = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("watchdog", str(vault_tools_dir / "1edbee15.py"))
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


def _seed(run_dir: Path, brakes: dict, iters: int, extra=None):
    with open(run_dir / "run.jsonl", "w") as f:
        f.write(json.dumps({"event": "run_created"}) + "\n")
        f.write(json.dumps({"event": "loop_contract_locked", "brakes": brakes}) + "\n")
        for n in range(1, iters + 1):
            f.write(json.dumps({"event": "iteration_completed", "iteration_n": n}) + "\n")
            if extra and n in extra:
                f.write(json.dumps(extra[n]) + "\n")


def _events(run_dir: Path):
    return [json.loads(l) for l in open(run_dir / "run.jsonl")]


class TestHumanCheckpoint(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.run_dir = self.root / "vault" / "loop-runs" / "r"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_pauses_at_N_not_killed(self):
        """At human_checkpoint_every iterations the loop PAUSES for a human — it is not killed."""
        _seed(self.run_dir, {"human_checkpoint_every": 3}, iters=3)
        watchdog.watchdog_scan(self.root)
        self.assertTrue((self.run_dir / ".paused_sentinel").exists(), "must pause at N")
        self.assertFalse((self.run_dir / ".poison_sentinel").exists(), "pause is NOT a kill")
        ev = _events(self.run_dir)
        self.assertTrue(any(e.get("event") == "human_checkpoint_required" for e in ev))
        self.assertTrue(any(e.get("event") == "status_changed" and e.get("to") == "paused" for e in ev))

    def test_no_pause_below_N(self):
        """Below the checkpoint cadence the loop runs on (no spurious pause)."""
        _seed(self.run_dir, {"human_checkpoint_every": 5}, iters=3)
        watchdog.watchdog_scan(self.root)
        self.assertFalse((self.run_dir / ".paused_sentinel").exists())

    def test_cadence_resets_after_human_continue(self):
        """After an explicit human_continue, the cadence counts from there (pauses again at +N)."""
        # iters 1..6 with a human_continue recorded right after iter 3.
        extra = {3: {"event": "human_continue"}}
        _seed(self.run_dir, {"human_checkpoint_every": 3}, iters=6, extra=extra)
        watchdog.watchdog_scan(self.root)
        # 6 - 3 (last_continue) == 3 >= 3 -> pauses again.
        self.assertTrue((self.run_dir / ".paused_sentinel").exists())


if __name__ == "__main__":
    unittest.main()
