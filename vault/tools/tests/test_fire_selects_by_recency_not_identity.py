#!/usr/bin/env python3
"""Permanent named-selection guard; all records and outward boundaries are disposable."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('_named_publisher', TOOLS / 'tropo-publish-release.py')
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class FireSelection(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for key, value in [('RELEASES_DIR', self.root / 'releases'),
                           ('STUDIO_ROOT', self.root), ('VAULT_DIR', self.root / 'vault')]:
            self.stack.enter_context(patch.object(pub.tropo_roots, key, value))
        self.stack.enter_context(patch.object(pub.subprocess, 'run', side_effect=AssertionError('unexpected subprocess')))
        self.stack.enter_context(patch.object(pub, '_run', side_effect=AssertionError('unexpected outward command')))
        self.stack.enter_context(patch.object(pub.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.good = {'version': '9.8.7', 'activation_uid': 'aaaaaaaaaaaa'}
        self.bad = {'version': '9.8.6', 'activation_uid': 'bbbbbbbbbbbb', 'published_at': 'yesterday'}
        for state, timestamp in [(self.good, 1), (self.bad, 9999999999)]:
            path = pub._state_path(state['version'])
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(state))
            os.utime(path, (timestamp, timestamp))
        self.args = SimpleNamespace(version='9.8.7', activation_uid='aaaaaaaaaaaa', reason='fixture')

    def test_named_record_wins_over_newest_published_record(self):
        self.assertEqual(pub._require_named_record(self.args.version, self.args.activation_uid), self.good)
        self.assertFalse(hasattr(pub, '_latest_staged_version'))

    def test_every_command_resolves_named_record(self):
        for command in [pub.cmd_preflight, pub.cmd_fire, pub.cmd_promote, pub.cmd_defer]:
            with self.subTest(command=command.__name__), patch.object(pub, '_require_named_record', side_effect=RuntimeError('named resolution')) as resolve:
                with self.assertRaisesRegex(RuntimeError, 'named resolution'):
                    command(self.args)
                resolve.assert_called_once_with('9.8.7', 'aaaaaaaaaaaa')
        with patch.object(pub, 'run_fire_preflight', return_value=0) as preflight:
            self.assertEqual(pub.cmd_preflight(self.args), 0)
            preflight.assert_called_once_with('9.8.7', self.good)

    def test_mismatch_prints_both_uids_and_working_remedy(self):
        for command in [pub.cmd_preflight, pub.cmd_fire, pub.cmd_promote, pub.cmd_defer]:
            with self.subTest(command=command.__name__), self.assertRaisesRegex(pub.PublishError, 'bbbbbbbbbbbb.*aaaaaaaaaaaa.*--activation-uid aaaaaaaaaaaa'):
                command(SimpleNamespace(version='9.8.7', activation_uid='bbbbbbbbbbbb'))

    def test_missing_identity_or_record_refuses(self):
        for version, activation in [(None, 'a'), ('9.8.7', None), ('0.0.0', 'aaaaaaaaaaaa')]:
            with self.subTest(version=version, activation=activation), self.assertRaises(pub.PublishError):
                pub._require_named_record(version, activation)

    def test_cli_requires_both_names_on_all_four_commands(self):
        for command in ['fire', 'preflight', 'defer', 'promote']:
            for names in [[], ['--version', '9.8.7'], ['--activation-uid', 'aaaaaaaaaaaa']]:
                argv = ['publisher', command] + names + (['--reason', 'fixture'] if command == 'defer' else [])
                with self.subTest(argv=argv), patch.object(sys, 'argv', argv), self.assertRaises(SystemExit) as error:
                    pub.main()
                self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
