import unittest
import sys
from pathlib import Path

vault_tools_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(vault_tools_dir))

import importlib.util
spec = importlib.util.spec_from_file_location("f4b8a6e2", str(vault_tools_dir / "tropo-rebuild-index.py"))
index_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(index_module)

class TestGetList(unittest.TestCase):
    def test_column_0_list(self):
        fm = "member_of:\n- 12345678\n- 87654321\n"
        self.assertEqual(index_module.get_list(fm, 'member_of'), ['12345678', '87654321'])
        
    def test_indented_list(self):
        fm = "member_of:\n  - 12345678\n  - 87654321\n"
        self.assertEqual(index_module.get_list(fm, 'member_of'), ['12345678', '87654321'])
        
    def test_inline_list(self):
        fm = "member_of: [12345678, 87654321]\n"
        self.assertEqual(index_module.get_list(fm, 'member_of'), ['12345678', '87654321'])

    def test_multiline_list_items(self):
        fm = '''acceptance_criteria:
  - "Line 1
    Line 2
    Line 3"
  - "Item 2
    Item 2 line 2"
'''
        res = index_module.get_list(fm, 'acceptance_criteria')
        self.assertEqual(len(res), 2)
        self.assertTrue("Line 2" in res[0])
        self.assertTrue("Item 2 line 2" in res[1])

if __name__ == '__main__':
    unittest.main()
