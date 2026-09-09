"""Publication journal compatibility: real producer, refusal controls, raw history.

All writes belong to temporary directories. The publisher append is intercepted;
no fire, preflight, network publication, or live bus emitter is invoked.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(ROOT / '.tropo/scripts'))
from lib import release_authorization as ra
from lib import release_closure, release_events, release_metrics, release_package
from lib.journal_event import run_journal_event_type


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PUBLISH = load('publish_journal_compatibility', 'tropo-publish-release.py')
SUPERSEDE = load('supersede_journal_compatibility', 'tropo-supersede-release-package.py')
VERIFY = load('verify_journal_compatibility', 'tropo-verify-release-live.py')
PUBLISHED = 'tropo.release.published'
RSHA = 'a' * 64


class JournalCompatibility(unittest.TestCase):
    def test_key_resolution_is_strict_and_shared(self):
        cases = [
            ({'event': PUBLISHED}, PUBLISHED), ({'type': PUBLISHED}, PUBLISHED),
            ({'event': None, 'type': PUBLISHED}, PUBLISHED),
            ({'event': '', 'type': PUBLISHED}, PUBLISHED),
            ({'event': 'unknown', 'type': PUBLISHED}, 'unknown'),
            ({'event': [], 'type': PUBLISHED}, ''),
            ({'event': {}, 'type': PUBLISHED}, ''),
            ({'event': False, 'type': PUBLISHED}, ''),
            ({'event': 0, 'type': PUBLISHED}, ''),
            ({'type': []}, ''), ({}, ''), (None, ''),
        ]
        for row, expected in cases:
            with self.subTest(row=row):
                for reader in (run_journal_event_type, release_closure.event_type,
                               release_package.event_type):
                    self.assertEqual(reader(row), expected)

    def test_post_mint_refusals_survive_alias_support(self):
        for row in (
            {'type': 'unknown'}, {'event': 'unknown', 'type': PUBLISHED},
            {'event': [], 'type': PUBLISHED}, {'type': PUBLISHED, 'step': '../bad'},
            {'type': PUBLISHED, 'step': 'not-a-step'},
            {'type': 'step_completed', 'step': ra.PRODUCE_STEP_UID,
             'data': {'natural_verdict': 'fail'}},
        ):
            with self.subTest(row=row):
                self.assertFalse(ra._post_mint_event_allowed(row))

    def test_alias_completion_cannot_hide_executor_from_signoff(self):
        for spelling in ('event', 'type'):
            with self.subTest(spelling=spelling):
                rows = [
                    {spelling: 'step_completed', 'step': ra.PRODUCE_STEP_UID,
                     'actor': 'test-executor', 'data': {'natural_verdict': 'pass'}},
                    {'event': 'human_signoff', 'actor': 'test-executor',
                     'data': {'verdict': 'accepted'}},
                ]
                with patch.object(ra, '_read_run_events', return_value=rows), \
                     patch.object(ra, '_resolve_principal_uid', return_value='f015abcdef56'):
                    admitted = ra._post_mint_event_allowed(rows[0])
                    independent = ra._has_human_signoff(Path('/tmp/unused-journal-fixture'))
                self.assertFalse(admitted and independent,
                                 'alias admission must not bypass canonical executor exclusion')
                if spelling == 'type':
                    self.assertFalse(admitted)
                else:
                    self.assertTrue(admitted)
                    self.assertFalse(independent)

    def test_actual_producer_and_legacy_rows_pass_and_removal_flips(self):
        runtime = PUBLISH._load_pipeline_runtime()
        identity = SimpleNamespace(activation_uid='f01512345678', run_uid='f015abcdef12')
        data = PUBLISH._published_event_data(RSHA, {
            'version': '1.95.0', 'tag': 'v1.95.0',
            'public_url': 'https://example.invalid/releases/v1.95.0',
            'published_at': '2026-09-07T00:00:00Z',
        })
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(PUBLISH, '_run_journal_folder', return_value=Path(temp)), \
                 patch.object(PUBLISH, '_load_pipeline_runtime', return_value=runtime), \
                 patch.object(runtime, 'read_events', return_value=[]), \
                 patch.object(runtime, 'append_event') as append:
                PUBLISH._mirror_published_event_to_journal({'identity': identity}, data, RSHA)
            row = append.call_args.args[1]
        self.assertTrue(ra._post_mint_event_allowed(row))
        historical = {'type': PUBLISHED, 'data': data}
        self.assertTrue(ra._post_mint_event_allowed(historical))
        with patch.object(ra, 'run_journal_event_type', side_effect=lambda row: row.get('event')):
            self.assertFalse(ra._post_mint_event_allowed(historical))

    def test_prior_publication_counts_but_new_envelopes_stay_canonical(self):
        runtime = PUBLISH._load_pipeline_runtime()
        ctx = release_events.AuthorizationContext(
            activation_uid='f01512345678', pipeline_run_uid='f015abcdef12',
            saga_id='release-test', release_entry_uid='f015abcdef34',
        )
        data = dict(saga_id=ctx.saga_id, pipeline_run_uid=ctx.pipeline_run_uid,
                    package_sha256='b' * 64, release_entry_uid=ctx.release_entry_uid,
                    publication_receipt_sha256=RSHA)
        envelope = runtime.make_event(PUBLISHED, 'f015abcdef56', data=data,
                                      trace_id=ctx.activation_uid)
        self.assertTrue(release_events.authorize(envelope, ctx, []).authorized)
        verdict = release_events.authorize(envelope, ctx, [{'type': PUBLISHED, 'data': data}])
        self.assertEqual(verdict.refusal_class, release_events.REFUSAL_CARDINALITY)
        legacy_proposal = dict(envelope)
        legacy_proposal['type'] = legacy_proposal.pop('event')
        self.assertFalse(release_events.authorize(legacy_proposal, ctx, []).authorized)

    def test_observer_reads_historical_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'run.jsonl').write_text(json.dumps({
                'type': PUBLISHED, 'data': {'receipt_sha256': RSHA},
            }) + '\n')
            context = release_events.AuthorizationContext.observe(folder)
            self.assertEqual(context.publication_receipt_sha256, RSHA)

    def test_metrics_reports_the_same_event_it_counted(self):
        fire = release_metrics.FIRE_AUTHORIZED_EVENT
        rows = [{'type': fire, 'actor': 'principal', 'span_id': 's1'},
                {'type': PUBLISHED, 'data': {'receipt_sha256': RSHA}}]
        result = release_metrics.derive_real_fire_verdict(rows, {'principal'})
        self.assertEqual(result['verdict'], 'fired-one-gesture')
        self.assertEqual(result['principal_gesture_rows'][0]['event'], fire)
        counts = release_metrics.count_gestures_v2(rows, {'principal'}, release_metrics.REAL_FIRE)
        self.assertEqual(counts['principal_inputs'][0]['event'], fire)

    def test_supersession_still_refuses_after_historical_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = Path(temp) / 'run.jsonl'
            journal.write_text(json.dumps({'type': PUBLISHED, 'data': {
                'pipeline_run_uid': 'f015abcdef12', 'receipt_sha256': RSHA,
            }}) + '\n')
            original = journal.read_bytes()
            argv = ['supersede', '--run-dir', temp, '--old-sha', 'b' * 64, '--reason', 'test']
            error = io.StringIO()
            with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(error):
                self.assertEqual(SUPERSEDE.main(), SUPERSEDE.EXIT_REFUSED)
            self.assertIn('already published', error.getvalue())
            self.assertEqual(journal.read_bytes(), original)

    def test_completion_dedup_sees_historical_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            journal = folder / 'run.jsonl'
            journal.write_text(json.dumps({'type': VERIFY.COMPLETION_EVENT, 'data': {
                'pipeline_run_uid': 'f015abcdef12',
            }}) + '\n')
            original = journal.read_bytes()
            self.assertFalse(VERIFY._emit_completion_verified(
                folder, {'pipeline_run_uid': 'f015abcdef12'}, {}))
            self.assertEqual(journal.read_bytes(), original)

    def test_historical_run_and_key_authorize_without_rewriting(self):
        source = ROOT / 'vault/pipeline-runs/release-pipeline-f015af4a6a0a-2026-09-05'
        if not (source / ra.KEY_FILENAME).is_file():
            self.skipTest('Studio v1.95 integration snapshot is not installed')
        def hashes(folder):
            return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*') if p.is_file()}
        original = hashes(source)
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / source.name
            shutil.copytree(source, copied)
            with patch.object(ra, 'find_run_folder', return_value=copied):
                key = ra.require_release_authorization(
                    'f015637f34b1', require_human_signoff=True, version='1.95.0')
                self.assertEqual(key['fingerprint'], ra.compute_fingerprint(
                    copied, ra.GATE_PRODUCE, event_limit=key['minted_at_event']))
            self.assertEqual(hashes(copied), original)
        self.assertEqual(hashes(source), original)


if __name__ == '__main__':
    unittest.main()
