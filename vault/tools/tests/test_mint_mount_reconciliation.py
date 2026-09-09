#!/usr/bin/env python3
"""Real canonical births under unrelated mount drift (f0155f4a971c)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Support both the Studio's direct-file runner and unittest module discovery.
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from test_identity_layer_v194 import _FlagFixture, mint
from test_mounted_content_phase2 import MountedFixture, _projection_text


class MintMountReconciliation(unittest.TestCase):
    def setUp(self):
        self.fixture = _FlagFixture()
        self.addCleanup(self.fixture.close)
        self.root = self.fixture.root
        self.fixture.set_readable_minting(True)
        external = tempfile.TemporaryDirectory(prefix="mint-unrelated-mount-")
        self.addCleanup(external.cleanup)
        self.mount = Path(external.name).resolve()
        self.mounted = MountedFixture.__new__(MountedFixture)
        self.mounted.root = self.root
        self.mounted.files = self.root / 'vault/files'
        self.mounted.mounts = {}
        self.mounted.records = []
        self.mounted.add_mount('abcddcba', self.mount)
        (self.mount / 'source.md').write_text('Retained quartz body\n')
        self.mounted.add_record('abcd1234', 'abcddcba', 'source.md', title='Mounted sentinel')
        self.sentinel = self.root / 'agents/fixture/refresh-pointer.md'
        self.sentinel.parent.mkdir(parents=True)
        self.sentinel.write_text('---\nuid: 1234abcd\ntype: document\ntitle: Governed sentinel\nstatus: draft\n---\nUnrelated body\n')
        (self.root / 'vault/files/123456ab.md').write_bytes(
            self.sentinel.read_bytes().replace(b'1234abcd', b'123456ab'))
        self.freshener = mint._load_rebuild_index(self.root)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            rc = self.freshener.rebuild_index(self.root, True, reconcile=True)
        self.assertEqual(rc, 0, err.getvalue())
        self.before_manifest = self.manifest()
        self.before_rows = self.rows()
        self.registry = self.root / '.tropo-studio/folder-mounts.json'
        self.counter = self.root / '.tropo-studio/dirty-counter.json'

    def manifest(self):
        return tuple(self.freshener.index_surfaces.load_trusted_derivation_manifest(self.root))

    @staticmethod
    def mount_entries(manifest):
        return tuple(row for row in manifest if row[1] == '.tropo-studio/folder-mounts.json' or row[1].startswith('@mounted-'))

    def rows(self):
        with sqlite3.connect(self.root / 'vault/00-index.sqlite') as db:
            return dict(db.execute('SELECT uid, body FROM entries_fts'))

    def drift(self):
        self.mounted.mounts['abcddcba']['name'] = 'Changed independently'
        self.mounted.write_registry()
        (self.mount / 'source.md').write_text('New source not yet refreshed\n')

    def birth(self, title='Recoverable Mint'):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = mint.mint_file('task', author='fixture-agent', title=title, studio_root=self.root)
        return result, err.getvalue()

    def test_real_mint_preserves_unrelated_rows_and_truthful_mount_manifest(self):
        self.drift()
        # An unrelated governed source lost its UID: a blind global apply would
        # prune it. The canonical birth must not repair or delete that record.
        self.sentinel.write_text('---\ntitle: Governed sentinel\n---\nUID accidentally lost\n')
        self.assertIsNone(self.freshener.process_file(self.sentinel), 'baseline collector must reject the damaged friendly path')
        source_bytes = self.sentinel.read_bytes()
        registry_bytes = self.registry.read_bytes()
        (uid, path), warning = self.birth()
        self.assertEqual(path.name, f'recoverable-mint-{uid}.md')
        self.assertTrue(path.is_file())
        self.assertIn('MINT-INDEX-RECONCILE', warning)
        self.assertIn('mount refresh remains required', warning)
        self.assertEqual(self.sentinel.read_bytes(), source_bytes)
        self.assertEqual(self.registry.read_bytes(), registry_bytes)
        rows = self.rows()
        for old_uid, body in self.before_rows.items():
            self.assertEqual(rows[old_uid], body, old_uid)
        self.assertEqual(self.mount_entries(self.manifest()), self.mount_entries(self.before_manifest))
        receipt = json.loads(self.counter.read_text())['last_mint_reconcile']
        self.assertEqual(receipt['minted_uids'], [uid])
        self.assertEqual(receipt['status'], 'mount-refresh-required')
        self.assertIn('.tropo-studio/folder-mounts.json', receipt['deferred_inputs'])
        with sqlite3.connect(self.root / 'vault/00-index.sqlite') as db:
            found = db.execute("SELECT uid FROM entries_fts WHERE entries_fts MATCH 'Recoverable'").fetchall()
        self.assertIn((uid,), found)
        # A second mint must not misreport that the first refreshed the mount.
        (next_uid, _), next_warning = self.birth('Second Recovery')
        self.assertIn('mount refresh remains required', next_warning)
        self.assertEqual(self.mount_entries(self.manifest()), self.mount_entries(self.before_manifest))
        self.assertEqual(json.loads(self.counter.read_text())['last_mint_reconcile']['minted_uids'], [next_uid])

    def test_clean_mint_needs_no_reconcile_receipt(self):
        (_, _), warning = self.birth()
        self.assertNotIn('MINT-INDEX-RECONCILE', warning)
        self.assertNotIn('last_mint_reconcile', json.loads(self.counter.read_text()))

    def test_code_drift_still_refuses_without_birth_or_receipt(self):
        self.drift()
        code = self.root / 'vault/tools/lib/gardener.py'
        code.write_text(code.read_text() + '\n# semantic input changed\n')
        counter_before = self.counter.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'gardener.py'):
            self.birth()
        self.assertFalse(list((self.root / 'vault/files').glob('recoverable-mint-*')))
        self.assertEqual(self.rows(), self.before_rows)
        self.assertEqual(self.counter.read_bytes(), counter_before)

    def test_generic_batch_does_not_gain_mint_permission(self):
        self.drift()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            rc = self.freshener.freshen_many(('123456ab',), self.root)
        self.assertNotEqual(rc, 0)
        self.assertIn('folder-mounts.json', err.getvalue())
        self.assertEqual(self.rows(), self.before_rows)

    def test_verification_failure_restores_all_surfaces_and_receipt(self):
        self.drift()
        before = {path: path.read_bytes() for path in (
            self.root / 'vault/00-index.jsonl',
            self.root / 'vault/00-archive-index.jsonl',
            self.root / 'vault/00-index.sqlite', self.counter,
        )}
        verified = []

        def reject_after_real_write(root, uid, path, type_name):
            self.assertTrue(path.is_file())
            self.assertIn(uid, self.rows())
            self.assertIn('last_mint_reconcile', json.loads(self.counter.read_text()))
            verified.append(uid)
            raise RuntimeError('injected exact-row verification failure')

        with mock.patch.object(mint, '_verify_minted_index_row', side_effect=reject_after_real_write):
            with self.assertRaisesRegex(RuntimeError, 'all destinations restored byte-identically'):
                self.birth()
        self.assertEqual(len(verified), 1)
        self.assertFalse(list((self.root / 'vault/files').glob('recoverable-mint-*')))
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw, str(path))
        self.assertEqual(self.manifest(), self.before_manifest)
        self.assertEqual(self.rows(), self.before_rows)

    def test_actual_cli_stdout_stays_uid_only_and_mutated_wire_refuses(self):
        script = self.root / 'vault/tools/tropo-mint-id.py'
        env = dict(os.environ)
        env.pop('TROPO_ACTIVATION_UID', None)
        env['TROPO_MINT_STUDIO_ROOT'] = str(self.root)
        cmd = [sys.executable, str(script), '--type', 'task', '--title', 'CLI Recovery', '--author', 'fixture-agent']
        self.drift()
        result = subprocess.run(cmd, cwd=self.root, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'^[0-9a-f]{12}\n$')
        self.assertIn('MINT-INDEX-RECONCILE', result.stderr)
        # Remove the actual canonical minter wire in this isolated tool copy.
        # No fake freshener or mocked success: the CLI now hits the original
        # semantic drift refusal, with no new record or receipt advance.
        script.write_text(script.read_text().replace('reconcile_unrelated_mounts=True,', 'reconcile_unrelated_mounts=False,'))
        before = self.rows()
        counter_before = self.counter.read_bytes()
        result = subprocess.run(cmd, cwd=self.root, env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('folder-mounts.json', result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.counter.read_bytes(), counter_before)

    def test_new_titled_mounted_projection_cannot_defer_its_dependencies(self):
        self.drift()
        # New slug paths are not necessarily found by the dependency resolver;
        # inspect the parsed staged record before granting local-mint recovery.
        uid = 'abcd5678'
        record = dict(self.mounted.records[0], uid=uid, title='New Mounted Record')
        path = self.root / f'vault/files/new-mounted-record-{uid}.md'
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            rc = self.freshener.freshen_many(
                (uid,), self.root, source_replacements={path: _projection_text(record).encode()},
                require_absent_sources=(path,), reconcile_unrelated_mounts=True,
            )
        self.assertNotEqual(rc, 0, err.getvalue())
        self.assertFalse(path.exists())
        self.assertEqual(self.rows(), self.before_rows)


if __name__ == '__main__':
    unittest.main(verbosity=2)
