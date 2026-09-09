#!/usr/bin/env python3
"""Morning status behavior at real producer/reader seams, with isolated IO.

GitHub and verify-channel subprocess results are fixtures. The status function,
cache writer/reader, and main() signature calculation are actual production code.
No real credentials, events, or network are used.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'tropo-studio-status.py'


class NightlyStatus(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('nightly_status_subject', SCRIPT)
        self.status = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.status)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.version = self.root / '.tropo/version.md'
        self.version.parent.mkdir()
        self.version.write_text('1.95.0\n')
        self.cache = self.root / '.tropo/flags/nightly-status.json'
        self.status.ROOT = str(self.root)
        self.status.NOW = dt.datetime(2026, 9, 7, 12, tzinfo=dt.timezone.utc)
        self.calls = []
        self.conclusion = 'success'
        self.run_status = 'completed'
        self.sha = 'abcdef1234567890'
        self.no_runs = False
        self.channel = subprocess.CompletedProcess([], 0, '', '')
        self.process_patch = patch.object(self.status.subprocess, 'run', side_effect=self._process)
        self.process_patch.start()
        self.addCleanup(self.process_patch.stop)

    def _process(self, command, **kwargs):
        self.calls.append(command)
        if command[:3] == ['gh', 'run', 'list']:
            runs = [] if self.no_runs else [dict(conclusion=self.conclusion, status=self.run_status,
                createdAt='2026-09-07T10:00:00Z', headSha=self.sha, url='https://example.invalid/run/1')]
            return subprocess.CompletedProcess(command, 0, json.dumps(runs), '')
        if 'verify-channel' in command:
            return self.channel
        raise AssertionError(f'unexpected subprocess: {command}')

    def _credentials(self):
        path = self.root / 'tropo-app/.env.local'
        path.parent.mkdir()
        path.write_text('NEXT_PUBLIC_SUPABASE_URL=fixture\nSUPABASE_SECRET_KEY=fixture\n')

    def _lines(self):
        title, lines = self.status.section_nightly()
        self.assertEqual(title, 'nightly candidate lane')
        return '\n'.join(lines)

    def test_unexpired_cache_avoids_repeat_query(self):
        self._lines()
        self.status.NOW += dt.timedelta(hours=2, minutes=59)
        self.assertIn('cached', self._lines())
        self.assertEqual(len(self.calls), 1)

    def test_cache_expires_at_three_hours(self):
        self._lines()
        self.status.NOW += dt.timedelta(hours=3)
        self.conclusion = 'failure'
        self.assertIn('FAILURE', self._lines())
        self.assertEqual(len(self.calls), 2)

    def test_future_dated_cache_is_a_miss(self):
        self._lines()
        record = json.loads(self.cache.read_text())
        record['at'] = (self.status.NOW + dt.timedelta(days=1)).isoformat()
        self.cache.write_text(json.dumps(record))
        self.conclusion = 'failure'
        self.assertIn('FAILURE', self._lines())
        self.assertEqual(len(self.calls), 2)

    def test_version_change_invalidates_cache_and_checks_new_version(self):
        self._credentials()
        self.assertIn('v1.95.0', self._lines())
        self.version.write_text('1.96.0\n')
        self.calls.clear()
        self.assertIn('v1.96.0', self._lines())
        channel_calls = [call for call in self.calls if 'verify-channel' in call]
        self.assertEqual(len(channel_calls), 1)
        self.assertEqual(channel_calls[0][-2:], ['--version', '1.96.0'])

    def test_legacy_cache_without_version_key_is_refreshed(self):
        self._lines()
        record = json.loads(self.cache.read_text())
        record.pop('version', None)
        self.cache.write_text(json.dumps(record))
        self.conclusion = 'failure'
        self.assertIn('FAILURE', self._lines())

    def test_never_run_still_reports_local_checks_and_caches(self):
        self.no_runs = True
        lines = self._lines()
        self.assertIn('NEVER RUN', lines)
        self.assertIn('fire credentials: NOT FOUND', lines)
        self.assertIn('live channel: skipped', lines)
        self.assertTrue(self.cache.is_file())
        self._lines()
        self.assertEqual(len(self.calls), 1)

    def test_never_run_with_credentials_still_checks_live_channel(self):
        self.no_runs = True
        self._credentials()
        lines = self._lines()
        self.assertIn('NEVER RUN', lines)
        self.assertIn('live channel: ok', lines)
        self.assertEqual(len(self.calls), 2)

    def test_failure_reason_on_stderr_survives_stdout_banner(self):
        self._credentials()
        self.channel = subprocess.CompletedProcess([], 1, 'Verifying release channel\n',
                                                   'RED: published manifest cannot be fetched\n')
        lines = self._lines()
        self.assertIn('published manifest cannot be fetched', lines)
        self.assertNotIn('see verify-channel', lines)

    def test_unknown_network_result_never_becomes_green(self):
        with patch.object(self.status.subprocess, 'run', side_effect=subprocess.TimeoutExpired('gh', 8)):
            self.assertIn('candidate lane: UNKNOWN', self._lines())
        self.assertNotIn('last build green', self._lines())

    def _main_report(self):
        ss = self.status
        ops = self.root / 'vault/studio-ops'
        ops.mkdir(parents=True, exist_ok=True)
        ss.OPS, ss.ROSTER, ss.LOG = str(ops), str(ops / 'roster.json'), str(ops / 'log.jsonl')
        Path(ss.ROSTER).write_text(json.dumps({'items': [{'runner': 'fixture', 'cadence': 'daily'}]}))
        Path(ss.LOG).write_text(json.dumps({'runner': 'fixture', 'event': 'run_complete',
                                          'at': '2026-09-07T11:00:00Z'}) + '\n')
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', ['status', '--no-emit', '--json']))
            for name in ('section_crew', 'section_git', 'section_work', 'section_meta', 'section_identity', 'section_bus'):
                stack.enter_context(patch.object(ss, name, return_value=(name, ['stable fixture fact'])))
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.assertEqual(ss.main(), 0)
            return json.loads(output.getvalue())

    def test_actual_report_signature_ignores_cache_age_and_candidate_age(self):
        first = self._main_report()
        self.status.NOW += dt.timedelta(hours=1)
        cached = self._main_report()
        self.assertNotEqual(first['sections'], cached['sections'])
        self.assertEqual(first['signature'], cached['signature'])
        self.status.NOW += dt.timedelta(hours=2)  # real refresh at TTL, older display age
        refreshed = self._main_report()
        self.assertEqual(first['signature'], refreshed['signature'])

    def test_actual_report_signature_changes_with_result(self):
        first = self._main_report()
        self.status.NOW += dt.timedelta(hours=3)
        self.conclusion = 'failure'
        changed = self._main_report()
        self.assertNotEqual(first['signature'], changed['signature'])

    def test_actual_report_signature_changes_with_commit(self):
        first = self._main_report()
        self.status.NOW += dt.timedelta(hours=3)
        self.sha = '123456789abcdef0'
        changed = self._main_report()
        self.assertNotEqual(first['signature'], changed['signature'])

    def test_running_candidate_signature_ignores_age_but_tracks_status_and_commit(self):
        self.conclusion = None
        self.run_status = 'queued'
        first = self._main_report()
        self.status.NOW += dt.timedelta(hours=3)
        older = self._main_report()
        self.assertEqual(first['signature'], older['signature'])
        self.status.NOW += dt.timedelta(hours=3)
        self.run_status = 'in_progress'
        running = self._main_report()
        self.assertNotEqual(older['signature'], running['signature'])
        self.status.NOW += dt.timedelta(hours=3)
        self.sha = '123456789abcdef0'
        next_commit = self._main_report()
        self.assertNotEqual(running['signature'], next_commit['signature'])

    def test_unreadable_version_keeps_report_available_and_channel_unknown(self):
        self._credentials()
        for data in (b'\xff', b''):
            with self.subTest(version_bytes=data):
                self.version.write_bytes(data)
                if self.cache.exists():
                    self.cache.unlink()
                self.calls.clear()
                lines = self._lines()
                self.assertIn('candidate lane: ok', lines)
                self.assertIn('live channel: UNKNOWN (installed version unavailable)', lines)
                self.assertFalse(any('verify-channel' in call for call in self.calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
