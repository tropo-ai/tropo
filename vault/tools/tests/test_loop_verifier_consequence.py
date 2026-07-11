import unittest
from pathlib import Path
import sys

vault_root = Path(__file__).resolve().parents[3]

class TestLoopVerifierConsequence(unittest.TestCase):
    def setUp(self):
        self.loop_capsule_path = vault_root / '.tropo' / 'capsules' / 'loop.capsule.md'

    def test_verifier_declares_stack(self):
        content = self.loop_capsule_path.read_text(encoding='utf-8')
        
        # AC4 requirement: assert verifier declares the 5-property stack
        self.assertIn("Independent", content)
        self.assertIn("Frozen precondition", content)
        self.assertIn("Multi-lens adversarial", content)
        self.assertIn("Machine-attested", content)
        self.assertIn("Outcome-not-proxy", content)
        
    def test_consequence_enum_and_rule(self):
        content = self.loop_capsule_path.read_text(encoding='utf-8')
        
        # Check consequence typed enum
        self.assertIn("low", content)
        self.assertIn("medium", content)
        self.assertIn("high", content)
        self.assertIn("critical", content)
        
        # Check rule forbidding a write-scope loop self-declaring 'low'
        # Rule 4: consequence is not freely self-declared
        self.assertIn("may not declare `consequence: low` without a human-signed classification", content)

if __name__ == '__main__':
    unittest.main()
