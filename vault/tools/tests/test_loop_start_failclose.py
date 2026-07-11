# v1.71 S1 loop-primitive test — LOOP-START FAIL-CLOSE (AC2).
# Body authored by argus-a114 (2026-06-16) from the Argus ad-hoc verification battery,
# per Metis G81 cut-bar decision (event 3900, option a). Talos owns/adjusts.
# Verifies vault/tools/1edbee15.py check_loop_run_start_preconditions() refuses bad contracts.
import json
import os
import shutil
import tempfile
import unittest
import importlib.util
from pathlib import Path
from unittest import mock

vault_tools_dir = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("watchdog", str(vault_tools_dir / "1edbee15.py"))
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)

GATEWAY = "http://127.0.0.1:8080"


class TestLoopStartFailClose(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.run_dir = self.root / "run"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def _contract(self, **over):
        c = {
            "event": "loop_contract_locked",
            "brakes": {"max_iterations": 5},
            "goal": {"authored_by": "mike-maziarz"},
            "verifier": {"kind": "gauntlet"},
            "policy": {"ref": "argus"},
        }
        c.update(over)
        with open(self.run_dir / "run.jsonl", "w") as f:
            f.write(json.dumps({"event": "run_created"}) + "\n")
            f.write(json.dumps(c) + "\n")

    def test_valid_contract_accepted(self):
        self._contract()
        self.assertTrue(watchdog.check_loop_run_start_preconditions(self.run_dir))

    def test_missing_brakes_rejected(self):
        self._contract(brakes={})
        self.assertFalse(watchdog.check_loop_run_start_preconditions(self.run_dir))

    def test_missing_goal_rejected(self):
        self._contract(goal=None)
        self.assertFalse(watchdog.check_loop_run_start_preconditions(self.run_dir))

    def test_missing_verifier_rejected(self):
        self._contract(verifier=None)
        self.assertFalse(watchdog.check_loop_run_start_preconditions(self.run_dir))

    def test_self_authored_goal_rejected(self):
        """goal.authored_by must differ from the policy executor (independence of the precondition)."""
        self._contract(goal={"authored_by": "argus"}, policy={"ref": "argus"})
        self.assertFalse(watchdog.check_loop_run_start_preconditions(self.run_dir))

    def test_no_contract_locked_rejected(self):
        with open(self.run_dir / "run.jsonl", "w") as f:
            f.write(json.dumps({"event": "run_created"}) + "\n")
        self.assertFalse(watchdog.check_loop_run_start_preconditions(self.run_dir))

    def test_spend_brake_requires_gateway_route(self):
        """When max_budget_usd is declared, the agent must be routed through the metering gateway."""
        self._contract(brakes={"max_iterations": 5, "max_budget_usd": 1.0})
        with mock.patch.dict(os.environ, {"ANTHROPIC_BASE_URL": ""}, clear=False):
            self.assertFalse(watchdog.check_loop_run_start_preconditions(self.run_dir))
        with mock.patch.dict(os.environ, {"ANTHROPIC_BASE_URL": GATEWAY}, clear=False):
            self.assertTrue(watchdog.check_loop_run_start_preconditions(self.run_dir))


if __name__ == "__main__":
    unittest.main()
