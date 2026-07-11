import unittest
from unittest.mock import patch
import sys
from pathlib import Path

vault_tools_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(vault_tools_dir))

import importlib.util
spec = importlib.util.spec_from_file_location("activate", str(vault_tools_dir / "2e5c81d3.py"))
activate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activate)

class TestLaunchPrompt(unittest.TestCase):
    @patch('builtins.input')
    def test_prompts_match_locked_contract(self, mock_input):
        """Verifies the activation gate asks for the 4 expected ceilings."""
        # 1. max_iters (default 5)
        mock_input.return_value = ""
        self.assertEqual(activate.prompt_int("Stop after how many iterations?", 5), 5)
        
        # 2. max_budget
        mock_input.return_value = "1.50"
        self.assertEqual(activate.prompt_float("Dollar ceiling for this run?", 0.50), 1.50)

if __name__ == '__main__':
    unittest.main()
