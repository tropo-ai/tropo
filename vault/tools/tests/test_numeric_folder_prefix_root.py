"""AC1: exercise the real validator/helper seam on isolated Studio fixtures.

Run: python3 vault/tools/tests/test_numeric_folder_prefix_root.py
No production filesystem traversal or complete-validator side effects are needed.
"""
import ast
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


class NumericRootRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='numeric-prefix-test-')
        self.addCleanup(self.temp.cleanup)
        self.outer = Path(self.temp.name)
        self.studio = self.outer / 'studio'
        (self.studio / 'vault').mkdir(parents=True)
        (self.studio / '.tropo').mkdir()
        self.mod = types.ModuleType('numeric_acceptance')
        src = ROOT / '.tropo/scripts/lib/numeric_folder_prefix_validators.py'
        exec(compile(src.read_text(), str(src), 'exec'), self.mod.__dict__)
        tree = ast.parse((ROOT / 'vault/tools/tropo-validate.py').read_text())
        call = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'run_all_numeric_folder_prefix_checks'
        )
        self.code = compile(ast.Expression(call), '<actual-caller>', 'eval')

    def run_family(self):
        return eval(self.code, {
            'vault': self.studio,
            'run_all_numeric_folder_prefix_checks': self.mod.run_all_numeric_folder_prefix_checks,
        })

    def test_actual_caller_detects_target_and_never_enumerates_parent(self):
        (self.studio / '04-misuse').mkdir()
        (self.studio / '10-needs-governance').mkdir()
        (self.outer / '01-private-fixture').mkdir()
        old = Path.iterdir

        def no_outside(path):
            self.assertTrue(path == self.studio or self.studio in path.parents, str(path))
            return old(path)

        with patch.object(Path, 'iterdir', no_outside):
            findings, total, defects = self.run_family()
        self.assertEqual((total, defects), (2, 2))
        self.assertTrue(any('04-misuse' in s for s in findings))
        self.assertTrue(any('10-needs-governance' in s for s in findings))
        self.assertFalse(any('private-fixture' in s for s in findings))

    def test_symlink_directory_not_enumerated(self):
        outside = self.outer / 'outside'
        (outside / '99-private-fixture').mkdir(parents=True)
        (self.studio / '04-linked').symlink_to(outside, target_is_directory=True)
        old = Path.iterdir

        def no_link(path):
            self.assertFalse(path.is_symlink(), 'followed symlink ' + str(path))
            return old(path)

        with patch.object(Path, 'iterdir', no_link):
            findings, total, _ = self.run_family()
        self.assertEqual(total, 0, 'linked directories must not enter the scan count')
        self.assertFalse(any('99-private-fixture' in s for s in findings))

    def test_vault_anchor_symlink_not_enumerated(self):
        # Replace only the empty temporary fixture directory with a link.
        (self.studio / 'vault').rmdir()
        outside = self.outer / 'outside-vault'
        (outside / '05-private-fixture').mkdir(parents=True)
        (self.studio / 'vault').symlink_to(outside, target_is_directory=True)
        old = Path.iterdir

        def no_link(path):
            self.assertFalse(path.is_symlink(), 'followed vault anchor ' + str(path))
            return old(path)

        with patch.object(Path, 'iterdir', no_link):
            findings, _, _ = self.run_family()
        self.assertFalse(any('05-private-fixture' in s for s in findings))
        self.assertTrue(
            any(str(self.studio / 'vault') in s and 'incomplete' in s for s in findings),
            'a linked vault anchor must not produce a clean scan',
        )

    def test_unreadable_in_scope_surfaces_finding_without_crash(self):
        blocked = self.studio / 'unreadable'
        blocked.mkdir()
        old = Path.iterdir

        def denied(path):
            if path == blocked:
                raise PermissionError('fixture-denied')
            return old(path)

        with patch.object(Path, 'iterdir', denied):
            findings, _, _ = self.run_family()
        self.assertTrue(any('unreadable' in s for s in findings), 'incomplete scan must not be clean')

    def test_clean_valid_target_remains_clean(self):
        (self.studio / '00-nav').mkdir()
        (self.studio / '02-outbox').mkdir()
        (self.studio / '10-owned').mkdir()
        (self.studio / '10-owned' / 'AGENTS.md').write_text('fixture governance')
        findings, total, defects = self.run_family()
        self.assertEqual((findings, total, defects), ([], 3, 0))

    def test_direct_check_calls_reject_linked_studio_anchor(self):
        outside = self.outer / 'outside'
        (outside / 'vault' / '05-private-fixture').mkdir(parents=True)
        (outside / '04-private-fixture').mkdir()
        link = self.outer / 'linked-studio'
        link.symlink_to(outside, target_is_directory=True)
        checks = [
            self.mod.check_numeric_folder_prefix_reserved_range,
            self.mod.check_studio_specific_folder_has_agents_md,
            self.mod.check_99_terminal_convention,
            self.mod.check_no_vault_subfolders_numeric_prefix,
        ]
        with patch.object(Path, 'iterdir', side_effect=AssertionError('linked anchor enumerated')):
            for check in checks:
                with self.subTest(check=check.__name__):
                    findings = check(link)
                    self.assertTrue(any('incomplete' in s for s in findings))
                    self.assertFalse(any('private-fixture' in s for s in findings))

    def test_child_metadata_error_is_reported_and_siblings_still_checked(self):
        blocked = self.studio / 'cannot-stat'
        blocked.mkdir()
        (self.studio / '04-misuse').mkdir()
        old = Path.lstat

        def denied(path):
            if path == blocked:
                raise PermissionError('fixture-denied')
            return old(path)

        with patch.object(Path, 'lstat', denied):
            findings, total, defects = self.run_family()
        self.assertEqual(total, 1)
        self.assertEqual(defects, 2)
        self.assertTrue(any('cannot-stat' in s and 'incomplete' in s for s in findings))
        self.assertTrue(any('04-misuse' in s for s in findings))

    def test_root_read_error_is_one_finding_not_clean_or_crash(self):
        with patch.object(Path, 'iterdir', side_effect=PermissionError('fixture-denied')):
            findings, total, defects = self.run_family()
        self.assertEqual((total, defects), (0, 1))
        self.assertIn(str(self.studio), findings[0])
        self.assertIn('incomplete', findings[0])

    def test_governance_read_error_is_reported(self):
        folder = self.studio / '10-owned'
        folder.mkdir()
        target = folder / 'AGENTS.md'
        old = Path.exists

        def denied(path):
            if path == target:
                raise PermissionError('fixture-denied')
            return old(path)

        with patch.object(Path, 'exists', denied):
            findings, total, defects = self.run_family()
        self.assertEqual((total, defects), (1, 1))
        self.assertIn(str(target), findings[0])
        self.assertIn('incomplete', findings[0])

    def test_string_root_and_missing_root_keep_tuple_contract(self):
        self.assertEqual(self.mod.run_all_numeric_folder_prefix_checks(str(self.studio)), ([], 0, 0))
        findings, total, defects = self.mod.run_all_numeric_folder_prefix_checks(self.outer / 'missing')
        self.assertEqual((total, defects), (0, 1))
        self.assertIn('incomplete', findings[0])

    def test_vault_and_terminal_checks_preserve_existing_depth_and_count(self):
        (self.studio / 'vault' / '05-misuse').mkdir()
        (self.studio / 'project' / '99-misuse').mkdir(parents=True)
        (self.studio / 'project' / 'deeper' / '99-beyond-scope').mkdir(parents=True)
        findings, total, defects = self.run_family()
        self.assertEqual((total, defects), (0, 2))
        self.assertTrue(any('05-misuse' in s for s in findings))
        self.assertTrue(any('99-misuse' in s for s in findings))
        self.assertFalse(any('99-beyond-scope' in s for s in findings))


if __name__ == '__main__':
    unittest.main(verbosity=2)

