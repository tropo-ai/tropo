#!/usr/bin/env python3
"""Git Beat 1 gauntlets — dev-spec 98b9610a acceptance criteria."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / 'vault' / 'tools'
sys.path.insert(0, str(TOOLS))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GIT = _load('tropo_git_history', TOOLS / 'lib' / 'tropo_git_history.py')


def _git(cwd, *args):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, timeout=60)


class StudioFixture:
    """Minimal studio tree for isolated git tests."""

    def __init__(self):
        test_root = ROOT / '.tmp-git-beat1-tests'
        test_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=str(test_root))
        self.root = Path(self.tmp.name)
        (self.root / 'vault' / 'files').mkdir(parents=True)
        (self.root / 'vault' / 'events').mkdir(parents=True)
        (self.root / 'playbook-runs' / 'test-run').mkdir(parents=True)
        (self.root / '.tropo-studio' / 'registries').mkdir(parents=True)
        (self.root / 'vault' / 'events' / '00-events.jsonl').write_text('')
        (self.root / 'playbook-runs' / 'test-run' / 'run.jsonl').write_text('{"event":"test"}\n')
        gi = ROOT / '.gitignore'
        if gi.exists():
            shutil.copy(gi, self.root / '.gitignore')

    def init_repo(self):
        template = self.root / '_git-empty-template'
        template.mkdir(exist_ok=True)
        r = _git(self.root, 'init', '--template', str(template))
        if r.returncode != 0:
            raise unittest.SkipTest(f'git init unavailable in this environment: {r.stderr or r.stdout}')
        _git(self.root, 'config', 'user.email', 'test@tropo.local')
        _git(self.root, 'config', 'user.name', 'Tropo Test')
        r = _git(self.root, 'add', '.gitignore')
        if r.returncode != 0:
            raise unittest.SkipTest(f'git add unavailable: {r.stderr}')
        r = _git(self.root, 'commit', '-m', 'init: .gitignore')
        if r.returncode != 0:
            raise unittest.SkipTest(f'git commit unavailable: {r.stderr}')

    def cleanup(self):
        self.tmp.cleanup()


class TestGitBeat1Core(unittest.TestCase):
    def test_commit_message_close_shape(self):
        import lib.tropo_git_history as gh
        msg = gh.commit_message_close(
            {'agent': 'talos', 'generation': 'T25'},
            '4a43ab81', 'retired', 'clean-retirement', 'abc12345', 'talos-t25',
        )
        self.assertIn('4a43ab81', msg)
        self.assertIn('talos', msg)
        self.assertIn('clean-retirement', msg)
        self.assertNotIn('hand-typed', msg)

    def test_commit_message_reconcile_shape(self):
        import lib.tropo_git_history as gh
        msg = gh.commit_message_reconcile(
            {'agent': 'talos', 'generation': 'T24', 'uid': '268f662c'},
            'talos', 'T25',
        )
        self.assertIn('reconcile', msg.lower())
        self.assertIn('T24', msg)
        self.assertIn('268f662c', msg)

    def test_find_prior_activation_prefers_active(self):
        import lib.tropo_git_history as gh
        entries = [
            ('aaaa1111', {'agent': 'talos', 'generation': 'T23', 'status': 'retired', 'activated_at': '2026-07-01'}),
            ('bbbb2222', {'agent': 'argus', 'generation': 'A126', 'status': 'active', 'activated_at': '2026-07-05'}),
        ]
        prior = gh.find_prior_activation_for_reconcile(entries)
        self.assertEqual(prior['uid'], 'bbbb2222')

    def test_tropo_restore_script_exists(self):
        self.assertTrue((TOOLS / 'tropo-restore.py').exists())
        self.assertTrue((TOOLS / 'tropo-vault-git-commit.py').exists())
        self.assertTrue((TOOLS / 'lib' / 'tropo_git_history.py').exists())

    def test_loop_registry_entry_exists(self):
        self.assertTrue((ROOT / 'vault' / 'files' / 'f8a2c91d.md').exists())
        text = (ROOT / 'vault' / 'files' / 'f8a2c91d.md').read_text()
        self.assertIn('tropo-vault-git-commit.py', text)
        self.assertIn('98b9610a', text)

    def test_op_open_wires_boot_reconcile(self):
        text = (TOOLS / '40b2f455.py').read_text()
        self.assertIn('boot_reconcile_if_dirty', text)

    def test_op_close_wires_activation_commit(self):
        text = (TOOLS / '40b2f455.py').read_text()
        self.assertIn('activation_close_commit', text)
        gi = ROOT / '.gitignore'
        self.assertTrue(gi.exists())
        text = gi.read_text()
        self.assertIn('vault/00-index.jsonl', text)
        self.assertIn('00-tropo-nav/', text)
        self.assertIn('vault/events/00-events.jsonl', text, 'events jsonl must NOT be ignored')

    def test_gitignore_covers_full_derived_index_sibling_family(self):
        """00005787 followup: only 00-index.jsonl was ignored; its siblings churned live."""
        text = (ROOT / '.gitignore').read_text()
        for sibling in (
            'vault/00-graph.jsonl',
            'vault/00-graph-registry.jsonl',
            'vault/00-index-boards.jsonl',
            'vault/00-index-decisions.jsonl',
            'vault/00-index-design-specs.jsonl',
            'vault/00-index-documents.jsonl',
            'vault/00-index-projects.jsonl',
            'vault/00-index-tasks.jsonl',
            'vault/00-integrity.json',
            'vault/00-pm-state.json',
        ):
            self.assertIn(sibling, text, f'{sibling} must be gitignored (00005787 finding)')
        self.assertIn('.bak-', text)

    def test_gitignore_covers_activation_locks(self):
        """00005787 followup: op_close commits the transient PID lock, then release_lock
        deletes it in `finally` — dirty tree at rest. Ignoring the whole locks/ dir closes it."""
        text = (ROOT / '.gitignore').read_text()
        self.assertIn('.tropo-studio/locks/', text)

    def test_lock_file_never_dirties_tree_after_ignore(self):
        fx = StudioFixture()
        try:
            fx.init_repo()
            lock_dir = fx.root / '.tropo-studio' / 'locks'
            lock_dir.mkdir(parents=True)
            lock_file = lock_dir / 'agent-activation.talos.lock'
            lock_file.write_text('12345')
            r = _git(fx.root, 'add', '-A')
            self.assertEqual(r.returncode, 0, r.stderr)
            porc = _git(fx.root, 'status', '--porcelain').stdout
            self.assertNotIn('locks/', porc, 'lock file leaked into git status despite .gitignore')
            lock_file.unlink()
            porc_after_delete = _git(fx.root, 'status', '--porcelain').stdout
            self.assertEqual(porc_after_delete.strip(), '', 'deleting an ignored lock must never dirty the tree')
        finally:
            fx.cleanup()

    def test_derived_index_ignored_after_rebuild_simulation(self):
        fx = StudioFixture()
        try:
            fx.init_repo()
            derived = fx.root / 'vault' / '00-index.jsonl'
            derived.write_text('{"uid":"deadbeef"}\n')
            source = fx.root / 'vault' / 'files' / 'deadbeef.md'
            source.write_text('---\nuid: deadbeef\ntype: note\n---\n\n# Source\n')
            _git(fx.root, 'add', '-A')
            porc = _git(fx.root, 'status', '--porcelain').stdout
            self.assertIn('vault/files/deadbeef.md', porc)
            self.assertNotIn('vault/00-index.jsonl', porc)
        finally:
            fx.cleanup()

    def test_close_commit_leaves_clean_tree(self):
        fx = StudioFixture()
        try:
            fx.init_repo()
            entry = fx.root / 'vault' / 'files' / 'aabbccdd.md'
            entry.write_text('---\nuid: aabbccdd\ntype: activation\nagent: talos\ngeneration: T99\nstatus: retired\n---\n\n# T99\n')
            # Patch repo root for lib
            import lib.tropo_git_history as gh
            gh.set_repo_root(fx.root)
            try:
                fm = {'agent': 'talos', 'generation': 'T99', 'status': 'retired'}
                ok, detail = gh.activation_close_commit(fm, 'aabbccdd', 'retired', 'clean-retirement')
                self.assertTrue(ok, detail)
                self.assertTrue(gh.is_clean(fx.root), gh.porcelain(fx.root))
                log = _git(fx.root, 'log', '-1', '--format=%B').stdout
                self.assertIn('talos', log.lower())
                self.assertIn('aabbccdd', log)
            finally:
                gh.set_repo_root(ROOT)
        finally:
            fx.cleanup()

    def test_close_commit_message_lists_staged_files(self):
        """00005787 cosmetic followup: staged_names() was called BEFORE `git add -A`,
        so the commit message's `files:` list was always empty. Must be populated now."""
        fx = StudioFixture()
        try:
            fx.init_repo()
            entry = fx.root / 'vault' / 'files' / 'aabbccdd.md'
            entry.write_text('---\nuid: aabbccdd\ntype: activation\nagent: talos\ngeneration: T99\nstatus: retired\n---\n\n# T99\n')
            import lib.tropo_git_history as gh
            gh.set_repo_root(fx.root)
            try:
                fm = {'agent': 'talos', 'generation': 'T99', 'status': 'retired'}
                ok, detail = gh.activation_close_commit(fm, 'aabbccdd', 'retired', 'clean-retirement')
                self.assertTrue(ok, detail)
                log = _git(fx.root, 'log', '-1', '--format=%B').stdout
                self.assertIn('files:', log)
                self.assertIn('vault/files/aabbccdd.md', log)
            finally:
                gh.set_repo_root(ROOT)
        finally:
            fx.cleanup()

    def test_boot_reconcile_attributes_prior_activation(self):
        fx = StudioFixture()
        try:
            fx.init_repo()
            entry = fx.root / 'vault' / 'files' / '11223344.md'
            entry.write_text('---\nuid: 11223344\ntype: activation\nagent: talos\ngeneration: T98\nstatus: retired\nretired_at: 2026-07-04\nactivated_at: 2026-07-04\n---\n\n# T98\n')
            _git(fx.root, 'add', 'vault/files/11223344.md')
            _git(fx.root, 'commit', '-m', 'prior activation')
            # Simulate ungraceful exit — mutate without commit
            entry.write_text(entry.read_text() + '\nOrphan drift.\n')
            import lib.tropo_git_history as gh
            gh.set_repo_root(fx.root)
            try:
                def _scan():
                    return [('11223344', {
                        'agent': 'talos', 'generation': 'T98', 'status': 'retired',
                        'retired_at': '2026-07-04', 'activated_at': '2026-07-04',
                    })]
                ok, detail = gh.boot_reconcile_if_dirty('talos', 'T99', _scan)
                self.assertTrue(ok, detail)
                log = _git(fx.root, 'log', '-1', '--format=%B').stdout
                self.assertIn('reconcile', log.lower())
                self.assertIn('T98', log)
            finally:
                gh.set_repo_root(ROOT)
        finally:
            fx.cleanup()

    def test_vault_maintenance_runner_commits_drift(self):
        fx = StudioFixture()
        try:
            fx.init_repo()
            drift = fx.root / 'vault' / 'files' / 'ccddeeff.md'
            drift.write_text('---\nuid: ccddeeff\ntype: note\n---\n\nDrift\n')
            script = TOOLS / 'tropo-vault-git-commit.py'
            import lib.tropo_git_history as gh
            gh.set_repo_root(fx.root)
            try:
                r = subprocess.run(
                    [sys.executable, str(script), '--vault-root', str(fx.root)],
                    cwd=str(fx.root), capture_output=True, text=True,
                )
                self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
                self.assertTrue(gh.is_clean(fx.root), gh.porcelain(fx.root))
                log = _git(fx.root, 'log', '-1', '--format=%B').stdout
                self.assertIn('vault-maintenance', log.lower())
            finally:
                gh.set_repo_root(ROOT)
        finally:
            fx.cleanup()

    def test_commit_failure_writes_flag(self):
        fx = StudioFixture()
        try:
            fx.init_repo()
            import lib.tropo_git_history as gh
            gh.set_repo_root(fx.root)
            try:
                gh.signal_commit_failure('abcd1234', 'simulated failure')
                flag = fx.root / '.tropo' / 'flags' / 'uncommitted-abcd1234.flag'
                self.assertTrue(flag.exists())
                self.assertIn('simulated failure', flag.read_text())
            finally:
                gh.set_repo_root(ROOT)
        finally:
            fx.cleanup()

    def test_tropo_restore_requires_reason(self):
        script = TOOLS / 'tropo-restore.py'
        r = subprocess.run(
            [sys.executable, str(script), 'deadbeef', '--to', 'abc1234', '--reason', ''],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        self.assertNotEqual(r.returncode, 0)

    def test_no_push_in_beat1_tools(self):
        for name in ('tropo-restore.py', 'tropo-vault-git-commit.py', 'lib/tropo_git_history.py'):
            text = (TOOLS / name).read_text()
            self.assertNotIn('git push', text)
            self.assertNotIn('remote add', text)

    def test_write_provenance_preserves_frontmatter_body_blank_line(self):
        """00005787 cosmetic followup: write_provenance's regex previously collapsed the
        blank line between the closing `---` and the body on every restore."""
        RESTORE = _load('tropo_restore', TOOLS / 'tropo-restore.py')
        fx = StudioFixture()
        try:
            fp = fx.root / 'vault' / 'files' / 'aaaaaaaa.md'
            original = '---\nuid: aaaaaaaa\ntype: note\n---\n\n# Title\n\nBody text.\n'
            fp.write_text(original, encoding='utf-8')
            parsed = RESTORE.parse_frontmatter(fp)
            self.assertIsNotNone(parsed)
            fm, fm_str, body = parsed
            RESTORE.write_provenance(fp, fm_str, body, 'deadbeef1234', 'talos-t25')
            result = fp.read_text(encoding='utf-8')
            self.assertNotIn('---\n# Title', result, 'blank line between frontmatter and body was collapsed')
            self.assertIn('---\n\n# Title', result)
        finally:
            fx.cleanup()

    def test_close_and_rebuild_leaves_clean_tree_end_to_end(self):
        """Argus 00005787 ask: a gauntlet asserting a clean tree after a close+rebuild —
        exercises the exact live-repo sequence that was dirtying at rest (tracked derived
        siblings + the transient PID lock both present at close time)."""
        fx = StudioFixture()
        try:
            fx.init_repo()
            import lib.tropo_git_history as gh
            gh.set_repo_root(fx.root)
            try:
                # Simulate the PID lock present during close (real op_close shape:
                # lock exists at commit time, deleted afterward in `finally`).
                lock_dir = fx.root / '.tropo-studio' / 'locks'
                lock_dir.mkdir(parents=True)
                lock_file = lock_dir / 'agent-activation.talos.lock'
                lock_file.write_text('99999')

                # Simulate a rebuild-index pass writing the derived-sibling family.
                for name in ('00-graph.jsonl', '00-integrity.json', '00-pm-state.json'):
                    (fx.root / 'vault' / name).write_text('{}')

                entry = fx.root / 'vault' / 'files' / 'aabbccdd.md'
                entry.write_text('---\nuid: aabbccdd\ntype: activation\nagent: talos\ngeneration: T99\nstatus: retired\n---\n\n# T99\n')

                fm = {'agent': 'talos', 'generation': 'T99', 'status': 'retired'}
                ok, detail = gh.activation_close_commit(fm, 'aabbccdd', 'retired', 'clean-retirement')
                self.assertTrue(ok, detail)

                # The op_close `finally: release_lock()` deletes the lock AFTER commit —
                # simulate that here; an ignored file's deletion must never dirty the tree.
                lock_file.unlink()

                self.assertTrue(gh.is_clean(fx.root), f'dirty after close+rebuild: {gh.porcelain(fx.root)}')
            finally:
                gh.set_repo_root(ROOT)
        finally:
            fx.cleanup()


class TestGitBeat1StudioIntegration(unittest.TestCase):
    """Live studio checks — skip if not a git repo yet."""

    def test_studio_git_or_pending_init(self):
        r = subprocess.run(['git', 'rev-parse', '--git-dir'], cwd=str(ROOT), capture_output=True)
        # Before sequencing init may fail — after build init should pass
        if r.returncode != 0:
            self.skipTest('studio git not initialized yet')
        self.assertTrue((ROOT / '.gitignore').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
