import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

# Add vault/tools to path to import 1edbee15
vault_tools_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(vault_tools_dir))

import importlib.util
spec = importlib.util.spec_from_file_location("watchdog", str(vault_tools_dir / "1edbee15.py"))
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)

class TestTerminalIterationStop(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.vault_root = self.test_dir
        self.runs_dir = self.vault_root / 'vault' / 'loop-runs'
        self.runs_dir.mkdir(parents=True)
        
        self.run_dir = self.runs_dir / 'test-run-123'
        self.run_dir.mkdir()
        self.run_jsonl = self.run_dir / 'run.jsonl'

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        
    def test_brake_holds_and_halts_runaway(self):
        """CUT-GATE PROOF: The terminal-stop brake actually HALTS a runaway loop under test."""
        # 1. Setup a loop-run contract with max_iterations = 3
        with open(self.run_jsonl, 'w') as f:
            f.write(json.dumps({"event": "run_created"}) + '\n')
            f.write(json.dumps({
                "event": "loop_contract_locked",
                "brakes": {"max_iterations": 3}
            }) + '\n')
            # 2. Simulate a runaway loop hitting 3 iterations
            f.write(json.dumps({"event": "iteration_completed", "iteration_n": 1}) + '\n')
            f.write(json.dumps({"event": "iteration_completed", "iteration_n": 2}) + '\n')
            f.write(json.dumps({"event": "iteration_completed", "iteration_n": 3}) + '\n')
            
        # 3. Run the watchdog
        watchdog.watchdog_scan(self.vault_root)
        
        # 4. Assert the brake HELD and HALTED the runaway
        # A. Poison sentinel must exist to kill the agent process
        self.assertTrue((self.run_dir / '.poison_sentinel').exists(), "Watchdog did not write poison sentinel")
        
        # B. run.jsonl must contain brake_tripped + terminal state: done
        with open(self.run_jsonl, 'r') as f:
            lines = [json.loads(line) for line in f.readlines()]
            
        self.assertEqual(lines[-2]['event'], 'brake_tripped')
        self.assertEqual(lines[-2]['brake'], 'max_iterations')
        
        self.assertEqual(lines[-1]['event'], 'workflow_complete')
        self.assertEqual(lines[-1]['terminal_state'], 'done')

if __name__ == '__main__':
    unittest.main()
