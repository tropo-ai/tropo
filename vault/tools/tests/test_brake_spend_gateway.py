# v1.71 S1 loop-primitive brake test — SPEND (AC2).
# Body authored by argus-a114 (2026-06-16) from the Argus ad-hoc verification battery,
# per Metis G81 cut-bar decision (event 3900, option a). Talos owns/adjusts to suit the
# engine test conventions. Verifies vault/tools/1edbee15.py (the brakes watchdog).
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


def _seed(run_dir: Path, brakes: dict, iters: int = 1):
    with open(run_dir / "run.jsonl", "w") as f:
        f.write(json.dumps({"event": "run_created"}) + "\n")
        f.write(json.dumps({"event": "loop_contract_locked", "brakes": brakes}) + "\n")
        for n in range(1, iters + 1):
            f.write(json.dumps({"event": "iteration_completed", "iteration_n": n}) + "\n")


def _events(run_dir: Path):
    return [json.loads(l) for l in open(run_dir / "run.jsonl")]


class TestSpendBrake(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.run_dir = self.root / "vault" / "loop-runs" / "r"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_spend_over_budget_trips(self):
        """A run past its per-run $ budget is hard-killed (gateway ground-truth)."""
        _seed(self.run_dir, {"max_budget_usd": 1.0})
        (self.run_dir / "gateway_spend.json").write_text(json.dumps({"spent_usd": 2.5}))
        watchdog.watchdog_scan(self.root)
        self.assertTrue((self.run_dir / ".poison_sentinel").exists())
        ev = _events(self.run_dir)
        self.assertEqual(ev[-2]["event"], "brake_tripped")
        self.assertEqual(ev[-2]["brake"], "max_budget_usd")

    def test_spend_failclosed_on_missing_file(self):
        """FAIL-CLOSED: a missing gateway_spend.json trips, not fail-open."""
        _seed(self.run_dir, {"max_budget_usd": 1.0})
        watchdog.watchdog_scan(self.root)
        self.assertTrue((self.run_dir / ".poison_sentinel").exists(),
                        "missing spend file must fail-closed (trip), not pass")
        self.assertEqual(_events(self.run_dir)[-2]["brake"], "max_budget_usd")

    def test_spend_failclosed_on_unreadable_file(self):
        """FAIL-CLOSED: an unreadable/garbage gateway_spend.json trips."""
        _seed(self.run_dir, {"max_budget_usd": 1.0})
        (self.run_dir / "gateway_spend.json").write_text("{not valid json")
        watchdog.watchdog_scan(self.root)
        self.assertTrue((self.run_dir / ".poison_sentinel").exists())

    def test_spend_under_budget_no_trip(self):
        """A run under budget is NOT killed (no spurious trip)."""
        _seed(self.run_dir, {"max_budget_usd": 5.0})
        (self.run_dir / "gateway_spend.json").write_text(json.dumps({"spent_usd": 1.0}))
        watchdog.watchdog_scan(self.root)
        self.assertFalse((self.run_dir / ".poison_sentinel").exists())


if __name__ == "__main__":
    unittest.main()
