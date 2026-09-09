#!/usr/bin/env python3
"""f0150176e435: final readiness requires executed checks, through both callers."""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PUB = load('preflight_skip_publisher', TOOLS / 'tropo-publish-release.py')
PREFLIGHT = PUB._load_release_preflight()


class PublisherReadiness(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(PUB.tropo_roots, 'RELEASES_DIR', self.root))
        self.stack.enter_context(patch.object(PUB, '_load_release_preflight', return_value=PREFLIGHT))
        self.stack.enter_context(patch.object(PUB.subprocess, 'run', side_effect=AssertionError('unexpected subprocess')))
        self.stack.enter_context(patch.object(PUB.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')))
        self.stack.enter_context(patch.object(PUB, '_confirm_tty', side_effect=AssertionError('unexpected confirm')))
        self.out, self.err = io.StringIO(), io.StringIO()
        self.stack.enter_context(contextlib.redirect_stdout(self.out))
        self.stack.enter_context(contextlib.redirect_stderr(self.err))
        self.state = {'version': '9.8.7', 'activation_uid': 'fixture-activation',
                      'staged_sha': 'fixture-commit', 'clone_dir': str(self.root),
                      'remote': 'fixture-remote'}
        # Keep the production roster, computed phases, context builder,
        # missing-input branch, aggregate and evidence writer. Only the
        # external judgments are replaced with deterministic fixture answers.
        self.verifiers = {
            gate_id: (lambda ctx, gate_id=gate_id:
                      PREFLIGHT.GateOutcome(gate_id, PREFLIGHT.VERDICT_PASS, 'fixture passed'))
            for gate_id, *_ in PREFLIGHT.PRE_OUTWARD_FIRE_ROSTER
        }
        self.stack.enter_context(patch.object(PUB, '_pre_outward_fire_verifiers',
                                             return_value=self.verifiers))

    def run_preflight(self):
        return PUB.run_fire_preflight('9.8.7', self.state)

    def rows(self):
        path = PUB._state_path('9.8.7').parent / 'preflight.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_real_registry_all_pass_is_green_with_one_evidence_row_per_gate(self):
        self.assertEqual(self.run_preflight(), 0)
        self.assertIn('PREFLIGHT GREEN', self.out.getvalue())
        self.assertEqual({row['gate_id'] for row in self.rows()}, set(self.verifiers))
        self.assertTrue(all(row['verdict'] == PREFLIGHT.VERDICT_PASS for row in self.rows()))

    def test_missing_staged_inputs_are_incomplete_and_evidence_stays_skipped(self):
        self.state = {'version': '9.8.7'}
        self.assertEqual(self.run_preflight(), 3)
        self.assertNotIn('PREFLIGHT GREEN', self.out.getvalue())
        self.assertIn('INCOMPLETE', self.err.getvalue())
        skipped = [row for row in self.rows() if row['verdict'] == PREFLIGHT.VERDICT_SKIPPED]
        self.assertTrue(skipped)
        for row in skipped:
            self.assertIn(row['gate_id'], self.err.getvalue())
        self.assertIn('--activation-uid', self.err.getvalue())

    def test_refusal_precedes_simultaneous_skip(self):
        gate_id = 'fire-gh-auth'
        self.verifiers[gate_id] = lambda ctx: PREFLIGHT.GateOutcome(gate_id, PREFLIGHT.VERDICT_REFUSED, 'fixture refusal')
        self.state.pop('staged_sha')
        self.assertEqual(self.run_preflight(), 2)
        self.assertIn('PREFLIGHT RED', self.err.getvalue())
        self.assertTrue(any(row['verdict'] == PREFLIGHT.VERDICT_SKIPPED for row in self.rows()))

    def test_operational_error_is_incomplete(self):
        gate_id = 'fire-staged-state'
        self.verifiers[gate_id] = lambda ctx: PREFLIGHT.GateOutcome(gate_id, PREFLIGHT.VERDICT_ERROR, 'fixture unavailable')
        self.assertEqual(self.run_preflight(), 3)
        self.assertIn('INCOMPLETE', self.err.getvalue())

    def test_missing_verifier_is_operational_and_names_binding(self):
        self.verifiers.pop('fire-staged-state')
        self.assertEqual(self.run_preflight(), 3)
        self.assertIn('fire-staged-state', self.err.getvalue())
        self.assertIn('binding', self.err.getvalue())
        self.assertNotIn('PREFLIGHT GREEN', self.out.getvalue())

    def test_empty_final_execution_cannot_certify_readiness(self):
        # Empty registry is a distinct failure from missing input or a
        # missing verifier on a declared roster row.
        with patch.object(PREFLIGHT, 'build_registry', return_value=PREFLIGHT.GateRegistry()):
            self.assertEqual(self.run_preflight(), 3)
        self.assertIn('No final-fire gates executed', self.err.getvalue())
        self.assertNotIn('PREFLIGHT GREEN', self.out.getvalue())

    def test_fire_preserves_operational_classification_and_stops_before_actions(self):
        with patch.object(PUB, 'require_ac7_receipt_set', side_effect=AssertionError('unexpected downstream action')):
            result = PUB.cmd_fire(SimpleNamespace(version='9.8.7'), preflight_rc=3, prepared_state=self.state)
        self.assertEqual(result, 3)
        self.assertIn('OPERATIONALLY INCOMPLETE', self.err.getvalue())
        self.assertNotIn('REFUSED', self.err.getvalue())

    def test_fire_preserves_determinate_refusal(self):
        self.assertEqual(PUB.cmd_fire(SimpleNamespace(version='9.8.7'), preflight_rc=2, prepared_state=self.state), 2)
        self.assertIn('REFUSED', self.err.getvalue())


class StandaloneReadiness(unittest.TestCase):
    def run_phase(self, phase, *extra):
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as root, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), patch.object(PREFLIGHT.gate_inputs, 'build_context', return_value={}):
            rc = PREFLIGHT.main(['--phase', phase, '--vault', root, *extra])
        return rc, out.getvalue(), err.getvalue()

    def test_final_without_publisher_context_is_operational(self):
        rc, out, err = self.run_phase('pre-outward-fire')
        self.assertEqual(rc, 3)
        self.assertIn('tropo-publish-release.py preflight', err)
        self.assertIn('--activation-uid', err)

    def test_all_cannot_hide_unexecuted_final_phase(self):
        rc, out, err = self.run_phase('all')
        self.assertEqual(rc, 3)
        self.assertIn('Final-fire checks did not all execute', err)

    def test_candidate_skip_semantics_are_unchanged(self):
        rc, out, err = self.run_phase('candidate')
        self.assertEqual(rc, 0)
        self.assertIn('SKIPPED-INPUTS-ABSENT', out)

    def test_final_list_is_read_only_success_not_execution(self):
        rc, out, err = self.run_phase('pre-outward-fire', '--list')
        self.assertEqual(rc, 0)
        self.assertIn('runs via:', out)


if __name__ == '__main__':
    unittest.main()
