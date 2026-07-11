import unittest
import yaml
import json
from pathlib import Path
import sys

vault_tools_dir = Path(__file__).resolve().parent.parent
vault_root = vault_tools_dir.parents[1]
sys.path.append(str(vault_root / '.tropo' / 'scripts'))
sys.path.append(str(vault_root))

from lib import loop_validators

class TestLoopDogfoodInstances(unittest.TestCase):
    def test_instances_satisfy_schema(self):
        """Build 3 sample instances (dispatcher/continuous-listen/fleet-ops) + assert each satisfies the schema."""
        
        # 1. Dispatcher
        dispatcher = {
            "uid": "66f7b892", "type": "loop", "name": "Dispatcher", "version": "1.0",
            "author": "argus-a114", "state": "active", "status": "draft",
            "goal": {"exit_criteria": ["booted"], "authored_by": "argus"},
            "trigger": {"kind": "event", "spec": "tropo.cycle"},
            "policy": {"kind": "executive", "ref": "talos"},
            "tools": ["2471edc0"],
            "verifier": {"kind": "validator", "independent": True, "lenses": 1, "attestation": "aspirational"},
            "brakes": {"max_iterations": 5, "max_budget_usd": 0.1, "max_wall_clock_min": 30},
            "consequence": "medium"
        }
        
        # 2. Continuous-listen
        listen = {
            "uid": "91c4e2a7", "type": "loop", "name": "Continuous Listen", "version": "1.0",
            "author": "argus-a114", "state": "active", "status": "draft",
            "goal": {"exit_criteria": ["drained"], "authored_by": "argus"},
            "trigger": {"kind": "schedule", "spec": "every 60s"},
            "policy": {"kind": "executive", "ref": "vela"},
            "tools": ["2471edc0"],
            "verifier": {"kind": "validator", "independent": True, "lenses": 1, "attestation": "aspirational"},
            "brakes": {"max_iterations": 100, "max_budget_usd": 1.0, "max_wall_clock_min": 600},
            "consequence": "low"
        }
        
        # 3. Fleet-ops
        fleet = {
            "uid": "cb7d713a", "type": "loop", "name": "Fleet Ops", "version": "1.0",
            "author": "argus-a114", "state": "active", "status": "draft",
            "goal": {"exit_criteria": ["deployed"], "authored_by": "mike"},
            "trigger": {"kind": "manual", "spec": "operator"},
            "policy": {"kind": "executive", "ref": "argus"},
            "tools": ["1545ac97", "2471edc0", "ca90f098"],
            "verifier": {"kind": "gauntlet", "independent": True, "lenses": 2, "attestation": "signed"},
            "brakes": {"max_iterations": 10, "max_budget_usd": 5.0, "max_wall_clock_min": 120},
            "consequence": "high"
        }
        
        instances = [
            ("vault/files/66f7b892.md", dispatcher),
            ("vault/files/91c4e2a7.md", listen),
            ("vault/files/cb7d713a.md", fleet)
        ]

        def mock_iter_loops(vault_path):
            for path_str, inst in instances:
                yield (Path(vault_path) / path_str, inst)

        def mock_load_tools(vault_path):
            return {
                "2471edc0": {"write_scope": []}, # mock it clean for 'low'
                "1545ac97": {"write_scope": []},
                "ca90f098": {"write_scope": []}
            }

        # Instead of patching inside the loop_validators module namespace, we patch the direct imports if any
        # actually let's just override the functions in the module for this test
        original_iter = loop_validators._iter_loops
        original_load_tools = loop_validators._load_tools
        
        loop_validators._iter_loops = mock_iter_loops
        loop_validators._load_tools = mock_load_tools
        
        try:
            findings, total, defects = loop_validators.check_loop_has_brakes(vault_root)
            self.assertEqual(defects, 0, f"Found defects in brakes: {findings}")
            self.assertEqual(total, 3)

            findings, total, defects = loop_validators.check_loop_goal_independent(vault_root)
            self.assertEqual(defects, 0, f"Found defects in goal independence: {findings}")

            findings, total, defects = loop_validators.check_loop_verifier_independent(vault_root)
            self.assertEqual(defects, 0, f"Found defects in verifier independence: {findings}")

            findings, total, defects = loop_validators.check_loop_consequence_scope(vault_root)
            self.assertEqual(defects, 0, f"Found defects in consequence scope: {findings}")
            
        finally:
            loop_validators._iter_loops = original_iter
            loop_validators._load_tools = original_load_tools

if __name__ == '__main__':
    unittest.main()
