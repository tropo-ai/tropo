#!/usr/bin/env python3
"""Fresh Studio infrastructure is quiet; real source input remains visible."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

TOOL = Path(__file__).resolve().parents[1] / 'tropo-scan-import-state.py'
BOX_ENV = 'TROPO_IMPORT_TEST_BOX'


class ImportStateBootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tropo-import-boot-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.tropo').mkdir()

    def scan(self):
        proc = subprocess.run([sys.executable, str(TOOL), '--studio-root', str(self.root), '--json'],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_first_party_instructions_are_not_imports(self):
        (self.root / 'README.md').write_text('Start here.\n')
        (self.root / 'LICENSE').write_text('Studio license.\n')
        (self.root / 'docs').mkdir()
        (self.root / '.claude').mkdir()
        result = self.scan()
        self.assertFalse(result['anomaly_detected'], result['orphan_paths'])
        self.assertEqual(result['trigger_recommendation'], 'no-action')

    def write_scaffold_manifest(self, readme):
        raw = readme.read_bytes()
        (self.root / 'tropo-image-manifest.json').write_text(json.dumps({
            'files': {'04-external-work/README.md': {
                'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            }},
        }))

    def test_empty_watch_surface_and_its_readme_are_quiet(self):
        watch = self.root / '04-external-work'
        watch.mkdir()
        self.assertFalse(self.scan()['anomaly_detected'])
        (watch / 'README.md').write_text('Place external work here.\n')
        self.write_scaffold_manifest(watch / 'README.md')
        self.assertFalse(self.scan()['anomaly_detected'])

    def test_customer_readme_is_visible_even_at_the_scaffold_path(self):
        watch = self.root / '04-external-work'
        watch.mkdir()
        readme = watch / 'README.md'
        readme.write_text('Shipped instructions.\n')
        self.write_scaffold_manifest(readme)
        # Same byte length: the digest, not just size or filename, must decide.
        readme.write_bytes(b'X' * readme.stat().st_size)
        result = self.scan()
        self.assertTrue(result['anomaly_detected'])
        self.assertEqual(result['orphan_paths'], ['04-external-work/'])

    def test_readme_without_readable_ship_evidence_is_visible(self):
        watch = self.root / '04-external-work'
        watch.mkdir()
        (watch / 'README.md').write_text('Customer project.\n')
        self.assertTrue(self.scan()['anomaly_detected'])
        for broken in ('not json', '{}', '[]'):
            (self.root / 'tropo-image-manifest.json').write_text(broken)
            self.assertTrue(self.scan()['anomaly_detected'])

    def test_populated_watch_surface_still_requests_reconciliation(self):
        watch = self.root / '04-external-work'
        watch.mkdir()
        (watch / 'README.md').write_text('Place external work here.\n')
        (watch / 'customer-research.md').write_text('Real user work.\n')
        result = self.scan()
        self.assertTrue(result['anomaly_detected'])
        self.assertEqual(result['orphan_paths'], ['04-external-work/'])

    def test_unrecognized_user_file_and_folder_are_not_suppressed(self):
        (self.root / 'customer-notes.md').write_text('Real user work.\n')
        (self.root / 'Client Research').mkdir()
        result = self.scan()
        self.assertTrue(result['anomaly_detected'])
        self.assertEqual(set(result['orphan_paths']), {'customer-notes.md', 'Client Research/'})

    @unittest.skipUnless(os.environ.get(BOX_ENV), 'Set TROPO_IMPORT_TEST_BOX to the actual release zip for box acceptance')
    def test_actual_release_zip_is_quiet_and_new_user_input_is_visible(self):
        box = Path(os.environ[BOX_ENV])
        self.assertTrue(box.is_file(), str(box))
        with zipfile.ZipFile(box) as archive:
            archive.extractall(self.root)
        result = self.scan()
        self.assertFalse(result['anomaly_detected'], result['orphan_paths'])
        self.assertEqual(result['orphan_paths'], [])
        watch = self.root / '04-external-work'
        self.assertTrue(watch.is_dir())
        (watch / 'customer-research.md').write_text('New input after unzipping.\n')
        result = self.scan()
        self.assertTrue(result['anomaly_detected'])
        self.assertEqual(result['orphan_paths'], ['04-external-work/'])
        (watch / 'customer-research.md').unlink()
        (watch / 'README.md').write_text('# Customer project\n\nMy only imported file.\n')
        result = self.scan()
        self.assertTrue(result['anomaly_detected'])
        self.assertEqual(result['orphan_paths'], ['04-external-work/'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
