import unittest
import yaml
import re
from pathlib import Path
import sys

vault_root = Path(__file__).resolve().parents[3]

class TestLoopCapsuleSchema(unittest.TestCase):
    def setUp(self):
        self.loop_capsule_path = vault_root / 'vault' / 'capsules' / 'tropo-loop.capsule.md'
        self.loop_run_capsule_path = vault_root / 'vault' / 'capsules' / 'tropo-loop-run.capsule.md'

    def test_loop_capsule_exists_and_declares_fields(self):
        self.assertTrue(self.loop_capsule_path.exists(), "loop.capsule.md must exist")
        
        content = self.loop_capsule_path.read_text(encoding='utf-8')
        
        # Parse the Markdown table to extract field keys
        # The table starts with | Field | Type | Constraint |
        field_keys = set()
        in_table = False
        for line in content.splitlines():
            if line.startswith('| `uid` |'):
                in_table = True
            
            if in_table:
                if not line.startswith('|'):
                    break
                # Extract the field name from the first column: | `field_name` |
                m = re.match(r'\|\s*`([^`]+)`\s*\|', line)
                if m:
                    field_keys.add(m.group(1))

        # Test for all 6 required fields via actual parsed keys
        self.assertIn("goal", field_keys)
        self.assertIn("trigger", field_keys)
        self.assertIn("policy", field_keys)
        self.assertIn("tools", field_keys)
        self.assertIn("verifier", field_keys)
        self.assertIn("brakes", field_keys)
        
        # Test for tier-invariance statement (one mechanism, every tier)
        self.assertIn("one mechanism, every tier", content.lower())
        
    def test_loop_run_capsule_records_iterations(self):
        self.assertTrue(self.loop_run_capsule_path.exists(), "loop-run.capsule.md must exist")
        content = self.loop_run_capsule_path.read_text(encoding='utf-8')
        
        self.assertIn("iteration_n", content)

if __name__ == '__main__':
    unittest.main()
